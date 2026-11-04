"""Zählen mit dem Beschleunigungssensor als Ablauf der Oberfläche — ohne flet
(``docs/plan_beschleunigung.md`` §4.3; `ui.uebung_lauf`, `ui.einheit`).

Ein Zähllauf ist eine Einheit aus Übung und Zählen, dazu die HRV, die schon aufnimmt. Uhr und
Zählen derselben Übung teilen eine Einheit; eine andere Übung beendet ein Zählen ohne Uhr mit
``andere_uebung`` (Meldung mit „Eintragen“), eine laufende Uhr nie. Eingetragen wird am Ende,
Zeit und Wiederholungen in einen Eintrag — abgehakt sofort, nie doppelt. Der Brustgurt der
Attrappen schickt eine Wiederholung je 2,5 s (`attrappen.Gurt`). Diese Tests laufen auch im
Kindprozess mit gesperrtem flet (`test_import_regel`).
"""

from __future__ import annotations

import asyncio

import pytest

from attrappen import Gurt, Seite, Uhr, ruhe, vorbei
from trainingsapp.core import zaehlen_eintrag as ze
from trainingsapp.core.einheit import Ereignis, Zustand
from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld
from trainingsapp.core.standards import mit_plan_spec
from trainingsapp.core.timer import Abschnitt, TimerProfil
from trainingsapp.core.zaehlen import (
    ENDE_ABBRUCH,
    ENDE_ABGEHAKT,
    ENDE_ANDERE_UEBUNG,
    ENDE_FERTIG,
    ENDE_KEINE_BEWEGUNG,
)
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.profiles import UHR_BROADCAST
from trainingsapp.devices.zaehlen import ZaehlBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import uebung_lauf
from trainingsapp.ui.components import zaehl_stand
from trainingsapp.ui.state import AppState


async def _umgebung(tmp_path, monkeypatch, *, aufnahme: bool):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    if aufnahme:
        lauf.aufnahme_starten()
    return state, uhr, gurt, lauf, lesen


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    """App-Zustand mit verbundenem H10 (Beschleunigung) und laufender HRV-Aufnahme."""
    state, uhr, gurt, lauf, lesen = await _umgebung(tmp_path, monkeypatch, aufnahme=True)
    yield state, uhr, gurt, lauf
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


@pytest.fixture
async def ohne_aufnahme(tmp_path, monkeypatch):
    """Verbunden genügt — eine Aufnahme ist keine Bedingung (§4.1)."""
    state, uhr, gurt, lauf, lesen = await _umgebung(tmp_path, monkeypatch, aufnahme=False)
    yield state, uhr, gurt, lauf
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


def _uebung(state, name: str = "Kniebeuge", *felder: str) -> Exercise:
    keys = felder or ("reps",)
    spec = ResultSpec(layout=Layout.SINGLE, fields=[f for k in keys if (f := vorrat_feld(k))])
    uebung = Exercise(name=name, result_spec=spec)
    state.uebungen.speichern(uebung)
    return uebung


def _profil() -> TimerProfil:
    return TimerProfil(
        name="Halten 2 × 20 s",
        abschnitte=[Abschnitt("Halten", 20), Abschnitt("Pause", 10, zaehlt=False)],
        runden=2,
    )


async def _ticken(state, uhr, gurt, sekunden: int, *, bis_ende: bool = False) -> None:
    """``sekunden`` Sekunden: Schlag, Beschleunigung bis zur Uhr, ein Takt der Einheit."""
    for _ in range(sekunden):
        uhr.t += 1
        gurt.schlag(1000)
        gurt.beschleunigung()
        await ruhe()
        e = state.einheit
        if e is not None and e.laeuft:
            e.takt()
        if bis_ende and (state.einheit is None or not state.einheit.laeuft or vorbei(state)):
            break
    if bis_ende:
        await _warten(lambda: vorbei(state))


async def _warten(bedingung) -> None:
    for _ in range(300):
        if bedingung():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Es geschah nicht")


def _eintraege(state):
    return [x for x, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]


def _personen_eintraege(state, einheit_id: str):
    return [
        x
        for x in state.einheiten.ereignisse(einheit_id)
        if (x.quelle, x.art) == ("person", "eintrag")
    ]


def _nummern_stimmen(state, e) -> None:
    """Alles steht in der Zeitleiste, keine Nummer doppelt (``UNIQUE(einheit_id, nr)``)."""
    assert e.warnung is None
    gespeichert = state.einheiten.ereignisse(e.id)
    assert [(x.quelle, x.art) for x in gespeichert] == [(x.quelle, x.art) for x in e.ereignisse]


# -- Ein Zähllauf für sich ---------------------------------------------------------------------


async def test_zaehllauf_fertig_traegt_die_wiederholungen_ein(umgebung) -> None:
    state, uhr, gurt, messlauf = umgebung
    u = _uebung(state)
    seite = Seite()
    e, meldung = uebung_lauf.zaehlen_starten(seite, state, uebung_lauf.kontext_fuer(u))
    assert meldung is None and state.zaehl_laeufe[u.id] == e.id
    assert [t.art for t in e.teile] == ["plan", "zaehlen", "hrv"]
    assert e.ende_mit_zaehlen and not e.ende_mit_timer and einheit_ui.titel(e) == "Kniebeuge"
    assert einheit_ui.nur_zaehlen(e) and einheit_ui.platz_frei(state)
    await ruhe()
    oben, unten = einheit_ui.laufzeilen(e)
    assert oben.endswith("Sensor startet …") and "Zählen · Kniebeuge" in unten
    # Ein zweiter Tipp: es zählt schon
    assert uebung_lauf.zaehlen_starten(seite, state, uebung_lauf.kontext_fuer(u)) == (e, None)

    await _ticken(state, uhr, gurt, 30)
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and z.sensor is not None and abs(z.sensor - 12) <= 1
    assert einheit_ui.laufzeilen(e)[0].endswith(f"{z.wert} Wdh.")
    assert zaehl_stand.korrigieren(state, u.id, None, +1)
    sensor = z.sensor
    # „Fertig“ am Zähler: die Einheit endet, eingetragen wird an ihrem Ende
    assert uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_FERTIG) is None
    assert e.zustand is Zustand.BEENDET and messlauf.acc_anforderungen == {}
    await _ticken(state, uhr, gurt, 1, bis_ende=True)

    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.wdh == [sensor + 1] and lauf.eingetragen == {ze.TEIL_ZAEHLEN}
    assert not lauf.abgebrochen and not lauf.zaehl_abgebrochen and not lauf.nachtragbar
    assert lauf.zaehl_texte == [f"Satz 1 · {sensor + 1} Wdh. (Sensor {sensor}, +1)"]
    assert lauf.zaehl_text == lauf.zaehl_texte[0]
    (eintrag,) = _eintraege(state)
    assert eintrag.id == lauf.eintrag_id and eintrag.result == {"reps": [sensor + 1]}
    assert eintrag.ended_at is None  # in den offenen Eintrag wie ein Tipp
    (person,) = _personen_eintraege(state, e.id)
    assert person.daten["teil"] == "zaehlen" and person.daten["werte"] == [sensor + 1]
    _nummern_stimmen(state, e)
    # Die Aufnahme lief weiter und steht wieder für sich da
    assert messlauf.aufnahme is not None


async def test_eine_messung_fuer_sich_macht_platz_und_laeuft_weiter(umgebung) -> None:
    """Steht die Aufnahme als eigene Einheit da, nimmt der Zähllauf sie als „läuft schon“
    mit (wie Uhr und Plan-Ablauf); danach steht sie wieder für sich."""
    from trainingsapp.config import datenverzeichnis
    from trainingsapp.core.einheit import Rolle
    from trainingsapp.devices.einheit import HrvBaustein

    state, uhr, gurt, messlauf = umgebung
    u = _uebung(state)
    seite = Seite()
    messung = einheit_ui.einzeln_starten(
        seite, state, HrvBaustein(messlauf, basis=datenverzeichnis())
    )
    assert messung is not None and einheit_ui.platz_frei(state)
    e, meldung = uebung_lauf.zaehlen_starten(seite, state, uebung_lauf.kontext_fuer(u))
    assert meldung is None and messung.zustand is Zustand.BEENDET
    assert e.hrv is not None and e.hrv.rolle is Rolle.LAEUFT_SCHON
    await _ticken(state, uhr, gurt, 12)
    uebung_lauf.zaehlen_beenden(state, u.id)
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    assert messlauf.aufnahme is not None and [t.art for t in state.einheit.teile] == ["hrv"]
    assert len(_eintraege(state)) == 1


async def test_ohne_aufnahme_und_ohne_geraet(ohne_aufnahme) -> None:
    state, uhr, gurt, messlauf = ohne_aufnahme
    u = _uebung(state)
    planke = _uebung(state, "Planke", "hold")
    with pytest.raises(RuntimeError, match="Beschleunigungssensor aus"):
        uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(planke))
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    assert [t.art for t in e.teile] == ["plan", "zaehlen"]  # ohne Aufnahme keine HRV
    await _ticken(state, uhr, gurt, 15)
    einheit_ui.alle_beenden(state)  # ⏹ in der Laufleiste gilt als „fertig“
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    assert ze.zaehl_ende(e.ereignisse) == ENDE_FERTIG
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] and eintrag.result["reps"][0] >= 4

    # Ohne Gerät mit Beschleunigungssensor gibt es kein Zählen (P118)
    state.messlauf = type("Lauf", (), {"status": messlauf.status, "profil": UHR_BROADCAST})()
    with pytest.raises(RuntimeError, match="Kein Gerät"):
        uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    state.messlauf = messlauf


async def test_abbrechen_bleibt_unter_laeufe_heute_und_laesst_sich_eintragen(umgebung) -> None:
    state, uhr, gurt, _ = umgebung
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 20)
    assert uebung_lauf.zaehlen_beenden(state, u.id, grund=ENDE_ABBRUCH) is None
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.abgebrochen and lauf.zaehl_abgebrochen and lauf.eintrag_id is None
    assert lauf.wdh and lauf.nachtragbar and lauf.nachzutragen == {ze.TEIL_ZAEHLEN}
    assert _eintraege(state) == []
    # „Eintragen“ unter „Läufe heute“ — einmal
    eintrag = uebung_lauf.lauf_eintragen(state, e.id)
    assert eintrag is not None and eintrag.result == {"reps": lauf.wdh}
    assert uebung_lauf.lauf_eintragen(state, e.id) is None
    (wieder,) = uebung_lauf.laeufe_heute(state, u.id)
    assert wieder.eintrag_id == eintrag.id and not wieder.nachtragbar
    assert len(_eintraege(state)) == 1


async def test_keine_bewegung_endet_abgebrochen(umgebung) -> None:
    state, uhr, gurt, messlauf = umgebung
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 15)
    gurt.bewegung = False
    await _ticken(state, uhr, gurt, 80, bis_ende=True)
    assert ze.zaehl_ende(e.ereignisse) == ENDE_KEINE_BEWEGUNG
    assert messlauf.acc_anforderungen == {} and _eintraege(state) == []
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.zaehl_abgebrochen and lauf.nachtragbar


# -- Andere Übung ------------------------------------------------------------------------------


async def test_andere_uebung_beendet_das_zaehlen_mit_meldung(umgebung) -> None:
    """Zählen von Y, dann Zählen von X: Ys Zählen endet mit ``andere_uebung`` (abgebrochen,
    unter „Läufe heute“), die Meldung „Kniebeuge · 8 Wdh. nicht eingetragen“ mit
    „Eintragen“; die Aufnahme läuft weiter. Ebenso, wenn die Uhr von X startet."""
    state, uhr, gurt, messlauf = umgebung
    kniebeuge = _uebung(state)
    liegestuetz = _uebung(state, "Liegestütz")
    e1, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(kniebeuge))
    await _ticken(state, uhr, gurt, 20)
    z1 = e1.teil("zaehlen")
    assert isinstance(z1, ZaehlBaustein)
    gezaehlt = z1.wert
    assert gezaehlt > 0

    e2, meldung = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(liegestuetz))
    assert e2 is not e1 and e1.zustand is Zustand.BEENDET
    assert ze.zaehl_ende(e1.ereignisse) == ENDE_ANDERE_UEBUNG
    assert meldung is not None and meldung.einheit_id == e1.id
    assert meldung.text == f"Kniebeuge · {gezaehlt} Wdh. nicht eingetragen"
    assert uebung_lauf.meldung_abholen(state) is None  # einmal
    assert messlauf.aufnahme is not None and e2.hrv is not None  # die Aufnahme kam mit
    assert messlauf.acc_anforderungen == {"zaehlen": (50, 8)}  # X zählt
    await _ticken(state, uhr, gurt, 2)
    (lauf,) = uebung_lauf.laeufe_heute(state, kniebeuge.id)
    assert lauf.zaehl_abgebrochen and lauf.nachtragbar and _eintraege(state) == []
    # „Eintragen“ in der Meldung
    eintrag = uebung_lauf.lauf_eintragen(state, meldung.einheit_id)
    assert eintrag is not None and eintrag.result == {"reps": [gezaehlt]}

    # Die Uhr von Y startet: das Zählen von X endet ebenso — die Meldung holt die Oberfläche
    await _ticken(state, uhr, gurt, 12)
    profil = _profil()
    e3 = uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(kniebeuge), profil)
    assert e3 is not e2 and e2.zustand is Zustand.BEENDET and e3.timer is not None
    meldung = uebung_lauf.meldung_abholen(state)
    assert meldung is not None and meldung.einheit_id == e2.id
    assert meldung.text.startswith("Liegestütz · ")
    e3.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, 2, bis_ende=True)


async def test_eine_laufende_uhr_wird_nie_still_beendet(umgebung) -> None:
    state, uhr, gurt, _ = umgebung
    planke = _uebung(state, "Planke", "hold")
    kniebeuge = _uebung(state)
    e = uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(planke), _profil())
    assert not einheit_ui.platz_frei(state)
    with pytest.raises(RuntimeError, match="läuft schon"):
        uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(kniebeuge))
    assert e.laeuft and e.teil("zaehlen") is None
    e.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, 2, bis_ende=True)


# -- Uhr und Zählen derselben Übung --------------------------------------------------------------


async def test_zaehlen_tritt_der_uhr_bei_ein_eintrag_mit_zeit_und_wiederholungen(
    umgebung,
) -> None:
    """Die Uhr von X läuft, „Wdh. zählen“ bei X: eine Einheit, sie endet mit der Uhr; jeder
    zählende Abschnitt ist ein Satz. Eingetragen wird einmal — Haltezeit und Wiederholungen
    in einem Eintrag."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(u)
    e = uebung_lauf.starten(Seite(), state, kontext, _profil())
    await _ticken(state, uhr, gurt, 1)
    beigetreten, meldung = uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    assert beigetreten is e and meldung is None
    assert isinstance(e.teil("zaehlen"), ZaehlBaustein) and not e.ende_mit_zaehlen
    assert not einheit_ui.nur_zaehlen(e)
    await _ticken(state, uhr, gurt, 80, bis_ende=True)

    assert ze.zaehl_ende(e.ereignisse) == ENDE_FERTIG
    (eintrag,) = _eintraege(state)
    assert eintrag.result["hold"] == [20, 20]
    reps = eintrag.result["reps"]
    assert len(reps) == 2 and all(6 <= n <= 9 for n in reps)
    teile = sorted(x.daten["teil"] for x in _personen_eintraege(state, e.id))
    assert teile == ["uhr", "zaehlen"]
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.werte == [20, 20] and lauf.wdh == reps and not lauf.nachtragbar
    assert lauf.eingetragen == {"uhr", "zaehlen"}
    _nummern_stimmen(state, e)


async def test_uhr_tritt_dem_zaehllauf_bei_und_bringt_ihre_wahl_mit(umgebung) -> None:
    """Zählen von X läuft, die Uhr von X startet: Sie tritt bei (kein ``andere_uebung``), die
    Einheit endet jetzt mit ihr. Die Wahl der Uhr („zählt“) gilt für den Eintrag."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    e, _ = uebung_lauf.zaehlen_starten(
        Seite(), state, uebung_lauf.kontext_fuer(u, zeit_eintragen=False)
    )
    await _ticken(state, uhr, gurt, 12)
    with pytest.raises(RuntimeError, match="Das Zählen läuft"):
        uebung_lauf.bereitstellen(Seite(), state, uebung_lauf.kontext_fuer(u), _profil())
    mit_uhr = uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(u), _profil())
    assert mit_uhr is e and e.timer is not None
    assert e.ende_mit_timer and not e.ende_mit_zaehlen
    assert uebung_lauf.meldung_abholen(state) is None
    plan_teil = e.teil("plan")
    assert plan_teil is not None and plan_teil.kontext.zeitfeld == "hold"
    await _ticken(state, uhr, gurt, 80, bis_ende=True)

    assert ze.zaehl_ende(e.ereignisse) == ENDE_FERTIG
    (eintrag,) = _eintraege(state)
    assert eintrag.result["hold"] == [20, 20]
    # Der Satz vor der Uhr, dann je zählender Abschnitt einer
    assert len(eintrag.result["reps"]) == 3
    # Die Beteiligung der Übung nennt jetzt das Zeitfeld (für „Eintragen“ später)
    (b,) = [x for x in state.einheiten.beteiligungen(e.id) if x.art == "plan"]
    assert b.daten["zeitfeld"] == "hold"
    _nummern_stimmen(state, e)


async def test_abbruch_der_uhr_bricht_den_ganzen_lauf_ab(umgebung) -> None:
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(u)
    e = uebung_lauf.starten(Seite(), state, kontext, _profil())
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 25)
    assert e.timer is not None
    e.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, 2, bis_ende=True)
    assert ze.zaehl_ende(e.ereignisse) == ENDE_ABBRUCH and _eintraege(state) == []
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.abgebrochen and lauf.zaehl_abgebrochen and lauf.eintrag_id is None
    assert lauf.nachzutragen == {"uhr", "zaehlen"}
    # Später „Eintragen“: Zeit und Wiederholungen gemeinsam
    eintrag = uebung_lauf.lauf_eintragen(state, e.id)
    assert eintrag is not None and eintrag.result["hold"] == [20] and eintrag.result["reps"]
    assert uebung_lauf.lauf_eintragen(state, e.id) is None
    assert len(_eintraege(state)) == 1


async def test_zaehlen_abbrechen_neben_der_uhr(umgebung) -> None:
    """Die Uhr läuft durch, das Zählen wurde abgebrochen: die Zeit kommt hinein, die
    Wiederholungen lassen sich unter „Läufe heute“ nachtragen — in denselben Eintrag. Ein
    zweites Zählen in diesem Lauf der Uhr gibt es nicht."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(u)
    e = uebung_lauf.starten(Seite(), state, kontext, _profil())
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 15)
    assert uebung_lauf.zaehlen_beenden(state, u.id, grund=ENDE_ABBRUCH) is None
    assert e.laeuft  # die Uhr läuft weiter
    with pytest.raises(RuntimeError, match="schon gezählt"):
        uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 80, bis_ende=True)
    (eintrag,) = _eintraege(state)
    assert eintrag.result == {"hold": [20, 20]}
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.eingetragen == {"uhr"} and lauf.nachzutragen == {"zaehlen"} and lauf.nachtragbar
    nachgetragen = uebung_lauf.lauf_eintragen(state, e.id)
    assert nachgetragen is not None and nachgetragen.result["reps"] == lauf.wdh
    assert nachgetragen.result["hold"] == [20, 20]  # derselbe offene Eintrag
    assert len(_eintraege(state)) == 1
    assert uebung_lauf.lauf_eintragen(state, e.id) is None


# -- Abhaken -----------------------------------------------------------------------------------


async def test_abhaken_traegt_sofort_ein_und_nichts_doppelt(umgebung) -> None:
    """Abgehakt während des Zählens (Leitentscheidung 7): Wiederholungen sofort in den offenen
    Eintrag, den die Oberfläche dann schließt; das Ende der Einheit trägt nichts mehr ein."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 20)
    eintrag = uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABGEHAKT)
    assert eintrag is not None and eintrag.result["reps"] and eintrag.ended_at is None
    geschlossen = state.sitzungen.eintrag_schliessen(eintrag.id)  # wie „Gemacht“ in plan.py
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    assert ze.zaehl_ende(e.ereignisse) == ENDE_ABGEHAKT
    (nur,) = _eintraege(state)
    assert nur.id == geschlossen.id and nur.ended_at is not None
    assert nur.result == {"reps": eintrag.result["reps"]}
    (person,) = _personen_eintraege(state, e.id)
    assert person.daten["teil"] == "zaehlen"
    _nummern_stimmen(state, e)
    # Nichts mehr zu tun
    assert uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABGEHAKT) is None
    assert uebung_lauf.lauf_eintragen(state, e.id) is None


async def test_abhaken_neben_der_uhr_schreibt_ueber_die_einheit(umgebung) -> None:
    """Läuft die Uhr weiter, schreibt ``person/eintrag`` die Einheit selbst
    (`Einheitslauf.nachtragen`) — mit eigener Nummer stieße es mit ihren zusammen. Die Zeit
    kommt mit dem Ende der Uhr dazu, die Wiederholungen nicht noch einmal."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(u)
    e = uebung_lauf.starten(Seite(), state, kontext, _profil())
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 15)
    eintrag = uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABGEHAKT)
    assert eintrag is not None and eintrag.result["reps"] and e.laeuft
    state.sitzungen.eintrag_schliessen(eintrag.id)
    await _ticken(state, uhr, gurt, 80, bis_ende=True)
    teile = sorted(x.daten["teil"] for x in _personen_eintraege(state, e.id))
    assert teile == ["uhr", "zaehlen"]
    eintraege = _eintraege(state)
    assert [x.result.get("reps") for x in eintraege].count(eintrag.result["reps"]) == 1
    assert sum(1 for x in eintraege if "reps" in x.result) == 1
    assert any(x.result.get("hold") == [20, 20] for x in eintraege)
    _nummern_stimmen(state, e)


async def test_abhaken_ohne_gezaehltes_traegt_nichts_ein(umgebung) -> None:
    """Nichts gezählt: das Abhaken stempelt „gemacht“ wie sonst — hier nichts."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 1)
    assert uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABGEHAKT) is None
    assert e.zustand is Zustand.BEENDET
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    assert _eintraege(state) == [] and _personen_eintraege(state, e.id) == []
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert not lauf.nachtragbar


async def test_teil_route_fuehrt_zur_uebung(umgebung) -> None:
    state, uhr, gurt, _ = umgebung
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    assert einheit_ui.teil_route(e.teil("zaehlen")) == f"/training/{u.id}"
    einheit_ui.alle_beenden(state)
    await _ticken(state, uhr, gurt, 1, bis_ende=True)


# -- Befunde der Prüfung (4.11.2026) -----------------------------------------------------------


async def test_planuebung_ohne_wiederholungsfeld_zaehlt_nicht(umgebung) -> None:
    """P79 „keiner = nur abhaken“: Bietet die Planübung kein Wiederholungsfeld an (nur
    abhaken, nur Gewicht), gibt es weder Knopf noch Zählen — sonst landeten die Wiederholungen
    in dem Feld des Katalogs, das die Planübung gar nicht anbietet. Umgekehrt zählt eine
    Planübung mit Wiederholungen nur im Plan (Planke mit „reps“) genau in dieses Feld."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Kniebeuge", "reps", "weight")
    planke = _uebung(state, "Planke", "hold")
    ohne = PlanItem(exercise_id=u.id, felder=["weight"])
    abhaken = PlanItem(exercise_id=u.id, felder=[])
    mit = PlanItem(exercise_id=planke.id, felder=["hold", "reps"])
    plan = Plan(name="P", subject_id=state.profil.id, items=[ohne, abhaken, mit])
    state.plaene.speichern(plan)
    for item in (ohne, abhaken):
        assert not zaehl_stand.sichtbar(state, u, item=item)
        assert zaehl_stand.knopf(u, item) == ""
        with pytest.raises(RuntimeError, match="keine Wiederholungen"):
            uebung_lauf.zaehlen_starten(
                Seite(), state, uebung_lauf.kontext_fuer(u, plan, item), uebung=u, item=item
            )
    assert state.einheit is None or not state.einheit.laeuft
    assert zaehl_stand.sichtbar(state, u)  # die Übung für sich zählt
    assert not zaehl_stand.sichtbar(state, planke)
    assert zaehl_stand.sichtbar(state, planke, item=mit)
    # Eine Zählung ohne Feld kommt nie in ein Feld, das die Planübung nicht anbietet
    zaehlung = Ereignis(20.0, "zaehlen", "zaehlung", "", {"satz": 1, "wert": 7})
    assert uebung_lauf._zaehl_feld(mit_plan_spec(ohne, u), ohne, [zaehlung]) is None
    assert uebung_lauf._zaehl_feld(u, None, [zaehlung]) == "reps"
    # Die Planke im Plan zählt in das „reps“ der Planübung
    e, _ = uebung_lauf.zaehlen_starten(
        Seite(), state, uebung_lauf.kontext_fuer(planke, plan, mit), uebung=planke, item=mit
    )
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and z.wdh and z.feld == "reps"
    await _ticken(state, uhr, gurt, 20)
    gezaehlt = z.wert
    assert gezaehlt > 0
    uebung_lauf.zaehlen_beenden(state, planke.id, mit.id, ENDE_FERTIG)
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    (eintrag,) = _eintraege(state)
    assert eintrag.exercise_id == planke.id and eintrag.result["reps"] == [gezaehlt]


async def test_trennen_beendet_das_zaehlen_und_neu_verbunden_zaehlt_es_wieder(
    tmp_path, monkeypatch
) -> None:
    """Gurt getrennt: Das Zählen endet sofort als abgebrochen (nicht 60 s später als „keine
    Bewegung“), die Wiederholungen bleiben nachtragbar — und mit dem neuen Messlauf zählt es
    wieder, statt „zählt hier schon“ an einem toten Teil."""
    state, uhr, gurt, lauf, lesen = await _umgebung(tmp_path, monkeypatch, aufnahme=False)
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 20)
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein)
    gezaehlt = z.wert
    assert gezaehlt > 0
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    e.takt()
    assert z.grund == ENDE_ABBRUCH and not e.laeuft
    await _warten(lambda: vorbei(state))
    (heute,) = uebung_lauf.laeufe_heute(state, u.id)
    assert heute.zaehl_abgebrochen and heute.nachtragbar and heute.wdh == [gezaehlt]
    # Neu verbunden: ein neuer Messlauf — das Zählen startet dort
    neu = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await neu.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(neu.laufen())
    state.messlauf = neu
    e2, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    z2 = e2.teil("zaehlen")
    assert e2 is not e and isinstance(z2, ZaehlBaustein) and z2.messlauf is neu and z2.aktiv
    assert neu.acc_anforderungen == {"zaehlen": (50, 8)}
    uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABBRUCH)
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    await neu.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


async def test_zaehlen_beenden_zeichnet_nicht_vor_dem_eintragen(umgebung) -> None:
    """Endet das Zählen auf einen Tipp, während die Uhr weiterläuft (hier: abgehakt), baut die
    Einheit die Ansicht nicht mitten im Handler neu: Der Neubau zeigte den Stand vor dem
    Eintrag, und das Auffrischen des Handlers danach träfe die alte, ersetzte Ansicht. Der
    Handler zeichnet selbst — erst nach dem Eintragen."""
    state, uhr, gurt, _ = umgebung
    gezeichnet: list[int] = []
    state.neu_zeichnen = lambda: gezeichnet.append(len(_eintraege(state)))
    u = _uebung(state)
    kontext = uebung_lauf.kontext_fuer(u)
    e = uebung_lauf.starten(Seite(), state, kontext, _profil())
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 15)
    gezeichnet.clear()
    eintrag = uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABGEHAKT)
    assert eintrag is not None and e.laeuft  # die Uhr läuft weiter
    assert gezeichnet == []  # vorher: [0] — neu gebaut, bevor der Eintrag da war
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and z.von_aussen and z.grund == ENDE_ABGEHAKT
    state.sitzungen.eintrag_schliessen(eintrag.id)
    uebung_lauf.zaehlen_beenden(state, u.id)  # nichts mehr zu beenden
    await _ticken(state, uhr, gurt, 80, bis_ende=True)


# -- Lücken der ersten Runde (4.11.2026) -------------------------------------------------------


def _plan_mit(state, *uebungen: Exercise, felder: list[str] | None = None) -> Plan:
    plan = Plan(
        name="Beine",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=u.id, felder=felder) for u in uebungen],
    )
    state.plaene.speichern(plan)
    geladen = state.plaene.laden(plan.id)
    assert geladen is not None
    return geladen


def _mit_sitzung(state):
    """Die Einträge des Tages samt dem Plan ihrer Sitzung."""
    return [
        (x, s.plan_id) for x, s in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    ]


async def test_abhaken_im_plan_nach_dem_start_ohne_plan_landet_im_plan(umgebung) -> None:
    """Zählen auf der Übungsseite (ohne Plan) begonnen, im Plan abgehakt: Der Kontext des
    Abhakens gewinnt — der Eintrag steht in der Sitzung des Plans, nicht in der ohne Plan, und
    nur einmal; die Beteiligungen nennen den Plan (für „Läufe heute“)."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state)
    plan = _plan_mit(state, u)
    item = plan.items[0]
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 20)
    eintrag = uebung_lauf.zaehlen_beenden(
        state, u.id, item.id, ENDE_ABGEHAKT, ort=(plan.id, item.id)
    )
    assert eintrag is not None and eintrag.result["reps"]
    state.sitzungen.eintrag_schliessen(eintrag.id)
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    ((nur, plan_id),) = _mit_sitzung(state)  # vorher: in der Sitzung ohne Plan
    assert plan_id == plan.id and nur.result == {"reps": eintrag.result["reps"]}
    for b in state.einheiten.beteiligungen(e.id):
        if b.art in ("plan", "zaehlen"):
            assert b.daten["plan"] == plan.id and b.daten["planuebung"] == item.id
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert not lauf.nachtragbar
    _nummern_stimmen(state, e)


async def test_abhaken_im_plan_neben_der_uhr_nimmt_die_uhr_mit(umgebung) -> None:
    """Lief dazu die Uhr (auf der Übungsseite gestartet), trägt auch sie in den Plan ein, in
    dem abgehakt wurde — nichts landet in der Sitzung ohne Plan."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    plan = _plan_mit(state, u)
    item = plan.items[0]
    kontext = uebung_lauf.kontext_fuer(u)
    e = uebung_lauf.starten(Seite(), state, kontext, _profil())
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 15)
    eintrag = uebung_lauf.zaehlen_beenden(
        state, u.id, item.id, ENDE_ABGEHAKT, ort=(plan.id, item.id)
    )
    assert eintrag is not None and e.laeuft
    state.sitzungen.eintrag_schliessen(eintrag.id)
    await _ticken(state, uhr, gurt, 80, bis_ende=True)
    eintraege = _mit_sitzung(state)
    assert eintraege and all(p == plan.id for _, p in eintraege)  # vorher: ohne Plan
    assert sum(1 for x, _ in eintraege if "reps" in x.result) == 1
    assert any(x.result.get("hold") == [20, 20] for x, _ in eintraege)
    _nummern_stimmen(state, e)


async def test_abhaken_in_einer_planuebung_ohne_wiederholungen_bricht_das_zaehlen_ab(
    umgebung,
) -> None:
    """Bietet die Planübung, an der abgehakt wird, keine Wiederholungen an (P79: nur abhaken),
    gehören sie nicht hinein: Das Zählen endet abgebrochen, nichts wird eingetragen (das
    Abhaken stempelt wie sonst), und unter „Läufe heute“ lassen sie sich dort nachtragen, wo
    das Zählen begann — nie doppelt."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Kniebeuge", "reps", "weight")
    plan = _plan_mit(state, u, felder=["weight"])
    item = plan.items[0]
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 20)
    assert (
        uebung_lauf.zaehlen_beenden(state, u.id, item.id, ENDE_ABGEHAKT, ort=(plan.id, item.id))
        is None
    )
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    assert ze.zaehl_ende(e.ereignisse) == ENDE_ABBRUCH and _eintraege(state) == []
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.nachtragbar and lauf.wdh
    nachgetragen = uebung_lauf.lauf_eintragen(state, e.id)
    assert nachgetragen is not None and nachgetragen.result["reps"] == lauf.wdh
    ((_, plan_id),) = _mit_sitzung(state)
    assert plan_id is None  # wo es begann


async def test_von_selbst_beendet_meldet_sich_einmal(umgebung) -> None:
    """Endet das Zählen von selbst und bleibt abgebrochen — 60 s ohne Bewegung —, liegt die
    Meldung „… nicht eingetragen — 60 s ohne Bewegung“ bereit (wie bei einer anderen Übung),
    einmal. Endet es auf einen Tipp, gibt es keine."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 15)
    gurt.bewegung = False
    await _ticken(state, uhr, gurt, 80, bis_ende=True)
    assert ze.zaehl_ende(e.ereignisse) == ENDE_KEINE_BEWEGUNG
    gezaehlt = ze.wiederholungen(e.ereignisse)
    assert gezaehlt
    meldung = uebung_lauf.meldung_abholen(state)  # vorher: None
    assert meldung is not None and meldung.einheit_id == e.id
    assert meldung.text == (
        f"Kniebeuge · {sum(gezaehlt)} Wdh. nicht eingetragen — 60 s ohne Bewegung"
    )
    assert uebung_lauf.meldung_abholen(state) is None  # einmal
    eintrag = uebung_lauf.lauf_eintragen(state, meldung.einheit_id)
    assert eintrag is not None and eintrag.result == {"reps": gezaehlt}

    # Auf einen Tipp („Zählen abbrechen“) und mit der Uhr, die abbricht: keine Meldung
    gurt.bewegung = True
    uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 15)
    uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABBRUCH)
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    assert uebung_lauf.meldung_abholen(state) is None
    wandsitz = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(wandsitz)
    mit_uhr = uebung_lauf.starten(Seite(), state, kontext, _profil())
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 15)
    assert mit_uhr.timer is not None
    mit_uhr.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, 2, bis_ende=True)
    assert ze.zaehl_ende(mit_uhr.ereignisse) == ENDE_ABBRUCH
    assert uebung_lauf.meldung_abholen(state) is None


async def test_getrennt_meldet_sich_mit_grund(tmp_path, monkeypatch) -> None:
    """Gurt getrennt: das Zählen endet abgebrochen, die Meldung nennt den Grund."""
    state, uhr, gurt, lauf, lesen = await _umgebung(tmp_path, monkeypatch, aufnahme=False)
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 20)
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein)
    gezaehlt = z.wert
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    e.takt()
    assert z.getrennt and z.grund == ENDE_ABBRUCH
    meldung = uebung_lauf.meldung_abholen(state)
    assert meldung is not None
    assert meldung.text == f"Kniebeuge · {gezaehlt} Wdh. nicht eingetragen — Sensor getrennt"
    await _warten(lambda: vorbei(state))
    state.schliessen()
