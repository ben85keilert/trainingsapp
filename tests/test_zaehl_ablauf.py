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


async def test_stoppuhr_dazu_misst_den_laufenden_satz(umgebung) -> None:
    """Die Stoppuhr, gestartet, während der Sensor schon zählt, misst den laufenden Satz: Ein
    Lauf der Stoppuhr ist ein Satz — die große Zahl springt nicht auf 0, und im Tagebuch steht
    einer. Vorher teilte ihr Start den Satz: ``{'duration': 26, 'reps': [4, 10]}`` (Runde 3,
    Befund 6). Ein Intervall-Timer gibt seine Sätze weiter selbst vor (Test oben)."""
    from trainingsapp.core.timer import stoppuhr

    state, uhr, gurt, _ = umgebung
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 12)
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and z.wert > 0
    vorher = z.wert
    assert uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(u), stoppuhr()) is e
    await _ticken(state, uhr, gurt, 1)
    assert len(z.saetze) == 1 and z.wert >= vorher  # vorher: ein neuer Satz, die Zahl bei 0
    await _ticken(state, uhr, gurt, 24)
    assert e.timer is not None
    e.timer.lauf.fertig_machen()
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    await _warten(lambda: bool(_eintraege(state)))
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] == [z.saetze[0].wert]  # vorher: [4, 10]
    assert eintrag.result["duration"] == 25
    _nummern_stimmen(state, e)


async def test_einmal_timer_dazu_misst_den_laufenden_satz(umgebung) -> None:
    """Wie die Stoppuhr: Der Einmal-Timer (ein Abschnitt, eine Runde), gestartet, während der
    Sensor schon zählt, misst den laufenden Satz — vorher teilte er ihn (die Zahl sprang auf 0,
    im Tagebuch ``{'hold': [30], 'reps': [4, 12]}``: zwei Werte für eine Zeit)."""
    from trainingsapp.core.timer import einmal_timer

    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(u)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 12)
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and z.wert > 0
    vorher = z.wert
    assert uebung_lauf.starten(Seite(), state, kontext, einmal_timer(30)) is e
    await _ticken(state, uhr, gurt, 1)
    assert len(z.saetze) == 1 and z.wert >= vorher  # vorher: ein neuer Satz, die Zahl bei 0
    await _ticken(state, uhr, gurt, 40, bis_ende=True)
    await _warten(lambda: bool(_eintraege(state)))
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] == [z.saetze[0].wert]  # vorher: [4, 12]
    assert eintrag.result["hold"] == [30]
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


# -- Befunde der dritten Runde (5.11.2026) -----------------------------------------------------


async def test_eintragen_aus_der_meldung_laesst_die_laufende_uhr_laufen(umgebung) -> None:
    """Endet nur das Zählen von selbst (60 s ohne Bewegung), während die Uhr derselben Übung
    weiterläuft, trägt „Eintragen“ der Meldung nur die Wiederholungen ein — die Zeit der Uhr
    kommt mit ihrem Ende dazu, ganz, in denselben Eintrag. Vorher nahm „Eintragen“ die Uhr mit
    (die Zeit bis jetzt ohne den laufenden Abschnitt), und ihre 120 s fehlten für immer."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(u)
    profil = TimerProfil(name="Halten 2 min", abschnitte=[Abschnitt("Halten", 120)])
    e = uebung_lauf.starten(Seite(), state, kontext, profil)
    await _ticken(state, uhr, gurt, 1)
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 15)
    gurt.bewegung = False
    await _ticken(state, uhr, gurt, 64)
    assert ze.zaehl_ende(e.ereignisse) == ENDE_KEINE_BEWEGUNG and e.laeuft
    meldung = uebung_lauf.meldung_abholen(state)
    assert meldung is not None
    gezaehlt = ze.wiederholungen(e.ereignisse)
    eintrag = uebung_lauf.lauf_eintragen(state, meldung.einheit_id)
    assert eintrag is not None and eintrag.result == {"reps": gezaehlt}
    assert [x.daten["teil"] for x in _personen_eintraege(state, e.id)] == ["zaehlen"]
    assert uebung_lauf.lauf_eintragen(state, e.id) is None  # die Uhr läuft noch
    await _ticken(state, uhr, gurt, 80, bis_ende=True)
    (fertig,) = _eintraege(state)
    assert fertig.result == {"reps": gezaehlt, "hold": [120]}  # vorher: {"reps": [6]}
    teile = {x.daten["teil"]: x.daten["werte"] for x in _personen_eintraege(state, e.id)}
    assert teile == {"zaehlen": gezaehlt, "uhr": [120]}
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert not lauf.nachtragbar
    _nummern_stimmen(state, e)


async def test_uhr_einer_planuebung_ohne_wiederholungen_nimmt_kein_zaehlen_mit(umgebung) -> None:
    """P79 auch, wenn Uhr und Zählen zusammenkommen: Läuft die Uhr für eine Planübung ohne
    Wiederholungsfeld (Wandsitz im Plan nur mit „hold“), tritt ein Zählen von der Übungsseite
    ihr nicht bei — eingetragen würde in diese Planübung, die keine Wiederholungen nimmt.
    Vorher zählte es mit, nichts kam hinein, und „Läufe heute“ bot für immer „Eintragen“ an,
    das nur „Schon eingetragen.“ meldete."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    plan = _plan_mit(state, u, felder=["hold"])
    item = plan.items[0]
    assert not zaehl_stand.sichtbar(state, u, item=item) and zaehl_stand.sichtbar(state, u)
    profil = TimerProfil(name="Halten", abschnitte=[Abschnitt("Halten", 40)])
    e = uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(u, plan, item), profil)
    await _ticken(state, uhr, gurt, 1)
    with pytest.raises(RuntimeError, match="keine Wiederholungen"):
        uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u), uebung=u)
    assert e.teil("zaehlen") is None and state.messlauf.acc_anforderungen == {}
    await _ticken(state, uhr, gurt, 60, bis_ende=True)
    ((eintrag, plan_id),) = _mit_sitzung(state)
    assert eintrag.result == {"hold": [40]} and plan_id == plan.id
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert not lauf.nachtragbar and lauf.nachzutragen == frozenset()


async def test_zaehlen_der_uebungsseite_wird_nicht_teil_der_uhr_ohne_wiederholungen(
    umgebung,
) -> None:
    """Umgekehrt: Zählt der Sensor auf der Übungsseite und startet dann die Uhr derselben
    Übung in einem Plan, der keine Wiederholungen nimmt, tritt die Uhr nicht bei — das Zählen
    macht Platz wie für eine andere Übung (Meldung mit „Eintragen“) und bleibt nachtragbar,
    wo es begann (Sitzung ohne Plan). Vorher übernahm die Uhr den Lauf, und die Wiederholungen
    ließen sich nie mehr eintragen."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    plan = _plan_mit(state, u, felder=["hold"])
    item = plan.items[0]
    zaehllauf, _ = uebung_lauf.zaehlen_starten(
        Seite(), state, uebung_lauf.kontext_fuer(u), uebung=u
    )
    await _ticken(state, uhr, gurt, 20)
    profil = TimerProfil(name="Halten", abschnitte=[Abschnitt("Halten", 40)])
    mit_uhr = uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(u, plan, item), profil)
    assert mit_uhr is not zaehllauf and mit_uhr.teil("zaehlen") is None  # vorher: beigetreten
    assert ze.zaehl_ende(zaehllauf.ereignisse) == ENDE_ANDERE_UEBUNG
    gezaehlt = ze.wiederholungen(zaehllauf.ereignisse)
    meldung = uebung_lauf.meldung_abholen(state)
    assert gezaehlt and meldung is not None and meldung.einheit_id == zaehllauf.id
    await _ticken(state, uhr, gurt, 60, bis_ende=True)
    # Die Enden beider Läufe sind eigene Aufgaben — warten, bis die Uhr eingetragen hat
    await _warten(lambda: bool(_personen_eintraege(state, mit_uhr.id)))
    ((eintrag, plan_id),) = _mit_sitzung(state)
    assert eintrag.result == {"hold": [40]} and plan_id == plan.id
    nachgetragen = uebung_lauf.lauf_eintragen(state, zaehllauf.id)
    assert nachgetragen is not None and nachgetragen.result == {"reps": gezaehlt}
    assert {p for _, p in _mit_sitzung(state)} == {plan.id, None}
    assert uebung_lauf.lauf_eintragen(state, zaehllauf.id) is None
    assert not any(lauf.nachtragbar for lauf in uebung_lauf.laeufe_heute(state, u.id))


async def test_eingetragene_saetze_bekommen_ihre_notiz_in_der_aufnahme(umgebung) -> None:
    """Plan §4.1/§5.3: Mit laufender Aufnahme bekommt jeder Satz, den der Sensor einträgt, die
    Notiz zum Satz („Kniebeuge: 11“, Marke ``person/leistung`` wie nach einem Chip) — an der
    Stelle, an der er endete, beim Eintragen. Vorher standen nur „Start“ und „Ende“ da.
    Abgebrochen gibt es keine; mit der Uhr je Satz eine."""
    state, uhr, gurt, lauf = umgebung
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 30)
    uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_FERTIG)
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    await _warten(lambda: bool(_eintraege(state)))
    ((gezaehlt,),) = [x.result["reps"] for x in _eintraege(state)]
    notizen = [x for x in lauf.ereignisse() if (x.get("marke") or {}).get("art") == "leistung"]
    assert [x["text"] for x in notizen] == [f"Kniebeuge: {gezaehlt}"]  # vorher: keine
    m = notizen[0]["marke"]
    assert (m["quelle"], m["feld"], m["wert"]) == ("person", "reps", gezaehlt)
    (leistung,) = [x for x in state.einheiten.ereignisse(e.id) if x.art == "leistung"]
    assert leistung.daten["eintrag"] == _eintraege(state)[0].id
    zaehlungen = [x for x in e.ereignisse if x.art == "zaehlung"]
    assert leistung.t_s == zaehlungen[-1].t_s  # das Ende des Satzes, nicht ein Zwischenstand

    # Abgebrochen: nichts eingetragen, keine Notiz
    uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 20)
    uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABBRUCH)
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    assert (
        len(
            [
                x
                for x in lauf.ereignisse()
                if "Kniebeuge: " in x["text"] and (x.get("marke") or {}).get("art") == "leistung"
            ]
        )
        == 1
    )

    # Mit der Uhr: je zählendem Abschnitt ein Satz, je Satz eine Notiz
    wandsitz = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(wandsitz)
    mit_uhr = uebung_lauf.starten(Seite(), state, kontext, _profil())
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 80, bis_ende=True)
    await _warten(lambda: bool(_personen_eintraege(state, mit_uhr.id)))
    (eintrag,) = [x for x in _eintraege(state) if x.exercise_id == wandsitz.id]
    texte = [
        x["text"]
        for x in lauf.ereignisse()
        if x["text"].startswith("Wandsitz: ") and (x.get("marke") or {}).get("art") == "leistung"
    ]
    assert texte == [f"Wandsitz: {n}" for n in eintrag.result["reps"]]
    _nummern_stimmen(state, mit_uhr)


async def test_funkabriss_und_keine_daten_melden_sich_mit_grund(umgebung) -> None:
    """Endet das Zählen, weil die Verbindung abriss (die Quelle verbindet selbst neu) oder
    weil keine Beschleunigung kam, sagt die Meldung das — nicht „60 s ohne Bewegung“."""
    from trainingsapp.core.zaehlen import KEINE_DATEN_S
    from trainingsapp.devices.base import Verbindung

    state, uhr, gurt, _ = umgebung
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 20)
    z1 = e.teil("zaehlen")
    assert isinstance(z1, ZaehlBaustein)
    gezaehlt = z1.wert
    gurt._status_aendern(verbindung=Verbindung.VERBINDE, meldung="verbinde neu")
    await ruhe()
    uhr.t += 1
    e.takt()
    meldung = uebung_lauf.meldung_abholen(state)
    assert meldung is not None  # vorher: nach 60 s „— 60 s ohne Bewegung“
    assert meldung.text == f"Kniebeuge · {gezaehlt} Wdh. nicht eingetragen — Sensor getrennt"
    gurt._status_aendern(verbindung=Verbindung.VERBUNDEN)
    await _warten(lambda: vorbei(state))

    # Verbunden, aber keine Beschleunigung: nur der Herzschlag kommt
    e2, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    z = e2.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and z.korrigieren(+1)
    for _ in range(int(KEINE_DATEN_S) + 2):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if e2.laeuft:
            e2.takt()
    meldung = uebung_lauf.meldung_abholen(state)
    assert meldung is not None
    assert meldung.text == "Kniebeuge · 1 Wdh. nicht eingetragen — keine Daten vom Sensor"
    await _warten(lambda: vorbei(state))


def _nach_dem_absturz(state, tmp_path, name: str = "absturz.db") -> AppState:
    """Die App stirbt jetzt (Akku, das System beendet sie): die Datenbank, wie sie in diesem
    Augenblick ist — kein ``finally``, kein Ende der Einheit —, und ein Neustart darauf."""
    import sqlite3

    pfad = tmp_path / name
    ziel = sqlite3.connect(pfad)
    state.einheiten.con.backup(ziel)
    ziel.close()
    return AppState.starten(pfad)


async def test_absturz_nach_dem_ende_des_zaehlens_kuerzt_die_uhr_nicht(umgebung, tmp_path) -> None:
    """Uhr „Halten 120 s“, „Wdh. zählen“, nach 20 s „Zählen abbrechen“ — die Person hält
    weiter, bei 91 s stirbt die App. Die letzte ``zaehlung`` ist das Ende des Zählens, nicht
    der Stand der Uhr: Vorher trug „Eintragen“ ``{'hold': [21], 'reps': [7]}`` ein, gehalten
    waren mindestens 91 s. Jetzt fehlt die Haltezeit (lieber eine Lücke als ein falscher Wert),
    die Wiederholungen kommen hinein."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(u)
    profil = TimerProfil(name="Halten 120 s", abschnitte=[Abschnitt("Halten", 120)])
    e = uebung_lauf.starten(Seite(), state, kontext, profil)
    await _ticken(state, uhr, gurt, 1)
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 20)
    uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABBRUCH)  # „Zählen abbrechen“
    await _ticken(state, uhr, gurt, 70)  # die Uhr hält weiter
    assert e.laeuft
    neu = _nach_dem_absturz(state, tmp_path)
    try:
        ereignisse = neu.einheiten.ereignisse(e.id)
        assert ze.uhr_bis(ereignisse) is None  # vorher: das Ende des Zählens
        (lauf,) = uebung_lauf.laeufe_heute(neu, u.id)
        eintrag = uebung_lauf.lauf_eintragen(neu, lauf.einheit_id)
        assert eintrag is not None
        assert "hold" not in eintrag.result and eintrag.result["reps"] == lauf.wdh
    finally:
        neu.schliessen()
    assert e.timer is not None
    e.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, 2, bis_ende=True)


async def test_absturz_in_der_pause_verliert_keinen_fertigen_satz(umgebung, tmp_path) -> None:
    """Stirbt die App in der Pause nach Satz 2, stehen beide Sätze in der Zeitleiste — passend
    zu den Zeiten der Uhr. Vorher kam ein Satz erst mit dem nächsten hinein: „Eintragen“ trug
    ``{'hold': [20, 20], 'reps': [7]}`` ein."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(u)
    profil = TimerProfil(
        name="3 × 20 s",
        abschnitte=[Abschnitt("Halten", 20), Abschnitt("Pause", 10, zaehlt=False)],
        runden=3,
    )
    e = uebung_lauf.starten(Seite(), state, kontext, profil)
    await _ticken(state, uhr, gurt, 1)
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 54)  # Satz 2 (30–50 s) ist zu, die Pause läuft
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and [s.bis_s is not None for s in z.saetze] == [True] * 2
    gezaehlt = [s.wert for s in z.saetze]
    neu = _nach_dem_absturz(state, tmp_path)
    try:
        (lauf,) = uebung_lauf.laeufe_heute(neu, u.id)
        assert lauf.wdh == gezaehlt and lauf.nachtragbar  # vorher: nur Satz 1
        eintrag = uebung_lauf.lauf_eintragen(neu, lauf.einheit_id)
        assert eintrag is not None
        assert eintrag.result == {"hold": [20, 20], "reps": gezaehlt}
    finally:
        neu.schliessen()
    z.abbrechen()
    e.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, 2, bis_ende=True)


async def test_absturz_mitten_im_abschnitt_passt_zur_zeit_der_uhr(umgebung, tmp_path) -> None:
    """Stirbt die App mitten in einem zählenden Abschnitt, steht sein Satz schon als
    Zwischenstand da — sein Abschnitt zählt bis dorthin mit, ein Stand für Zeit und
    Wiederholungen. Vorher fehlte der Abschnitt in den Zeiten der Uhr: „Eintragen“ schrieb
    eine Haltezeit weniger als Sätze (Runde 3, Befunde 3 und 13)."""
    from trainingsapp.devices.zaehlen import ZWISCHENSTAND_S

    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    kontext = uebung_lauf.kontext_fuer(u)
    profil = TimerProfil(
        name="3 × 30 s",
        abschnitte=[Abschnitt("Halten", 30), Abschnitt("Pause", 10, zaehlt=False)],
        runden=3,
    )
    e = uebung_lauf.starten(Seite(), state, kontext, profil)
    await _ticken(state, uhr, gurt, 1)
    uebung_lauf.zaehlen_starten(Seite(), state, kontext)
    await _ticken(state, uhr, gurt, 62)  # Halten 2 läuft seit gut 20 s (40–70 s)
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and len(z.saetze) == 2 and z.saetze[-1].bis_s is None
    zwischen = [x for x in e.ereignisse if x.art == "zaehlung" and x.daten["satz"] == 2]
    assert zwischen and zwischen[-1].t_s - z.saetze[-1].von_s >= ZWISCHENSTAND_S
    neu = _nach_dem_absturz(state, tmp_path)
    try:
        (lauf,) = uebung_lauf.laeufe_heute(neu, u.id)
        assert len(lauf.wdh) == 2 and lauf.nachtragbar
        bis = round(zwischen[-1].t_s - z.saetze[-1].von_s)
        assert [round(x.sekunden) for x in lauf.zeiten if x.zaehlt] == [30, bis]
        eintrag = uebung_lauf.lauf_eintragen(neu, lauf.einheit_id)
        assert eintrag is not None
        # vorher: {'hold': [30], 'reps': [n1, n2]} — Satz 2 ohne Haltezeit
        assert eintrag.result == {"hold": [30, bis], "reps": lauf.wdh}
    finally:
        neu.schliessen()
    z.abbrechen()
    e.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, 2, bis_ende=True)


async def test_absturz_mitten_im_zaehllauf_laesst_den_stand_nachtragen(umgebung, tmp_path) -> None:
    """Ein Zähllauf ohne Uhr ist ein Satz — stirbt die App mitten darin, steht sein Stand der
    letzten `ZWISCHENSTAND_S` in der Zeitleiste und lässt sich nachtragen. Vorher stand dort
    nichts, und „Läufe heute“ bot nichts an."""
    from trainingsapp.devices.zaehlen import ZWISCHENSTAND_S

    state, uhr, gurt, _ = umgebung
    u = _uebung(state)
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 50)
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and z.aktiv
    jetzt = z.wert
    neu = _nach_dem_absturz(state, tmp_path)
    try:
        (lauf,) = uebung_lauf.laeufe_heute(neu, u.id)
        assert lauf.nachtragbar and len(lauf.wdh) == 1  # vorher: wdh [] — nichts nachzutragen
        # höchstens die letzten Sekunden fehlen (eine Wiederholung je 2,5 s)
        assert jetzt - ZWISCHENSTAND_S / 2.5 - 1 <= lauf.wdh[0] <= jetzt
        eintrag = uebung_lauf.lauf_eintragen(neu, lauf.einheit_id)
        assert eintrag is not None and eintrag.result == {"reps": lauf.wdh}
    finally:
        neu.schliessen()
    # Lebt die App weiter, gilt am Ende der eine Satz mit seinem ganzen Wert
    uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_FERTIG)
    await _ticken(state, uhr, gurt, 1, bis_ende=True)
    await _warten(lambda: bool(_eintraege(state)))
    ((eintrag, _),) = _mit_sitzung(state)
    assert eintrag.result == {"reps": [z.saetze[0].wert]}
    assert ze.wiederholungen(state.einheiten.ereignisse(e.id)) == [z.saetze[0].wert]


# -- Diagnosemodus: Mitschnitt und Vergleich nach dem Satz -----------------------------------


async def _diagnose_umgebung(tmp_path, monkeypatch):
    """App-Zustand mit H10 im Diagnosemodus (200 Hz Beschleunigung) und laufender Aufnahme."""
    from test_devices import FakeZeit
    from test_diagnose_geraete import _messlauf

    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    zeit = FakeZeit()
    lauf, _quelle, innen = await _messlauf(tmp_path, zeit)
    gemeldet: list[dict] = []
    lauf.diagnose_satz_beobachter = gemeldet.append
    state.messlauf = lauf
    lauf.aufnahme_starten()
    start = asyncio.create_task(lauf.diagnose_starten(ekg=False, acc=(200, 8)))
    await zeit.vorspulen(1.0)
    await start
    assert lauf.diagnose_aktiv
    return state, zeit, lauf, innen, gemeldet


async def _diagnose_aus(state, lauf, zeit=None) -> None:
    """Aufräumen — mit ``zeit`` auch, wenn noch gezählt wird (ein Test scheiterte mitten im
    Lauf): Dann stellt das Ende die Rate um, und die Attrappe des Gurts antwortet erst, wenn
    die Zeit weiterläuft (wie beim Start)."""
    ende = asyncio.create_task(lauf.diagnose_beenden())
    if zeit is not None:
        await zeit.vorspulen(5.0)
    await ende
    lauf.aufnahme = None
    await lauf.trennen()
    state.schliessen()


async def _rahmen(
    lauf,
    innen,
    zeit,
    e,
    k0: int,
    sekunden: float,
    *,
    tipps: int = 0,
    bewegung: bool = True,
    marke=None,
) -> int:
    """``sekunden`` Beschleunigung (200 Hz, eine Kniebeuge je 2 s; ohne ``bewegung`` still)
    und ``tipps`` Marken der Leiste, gleichmäßig verteilt — gibt das nächste ``k`` zurück.
    ``marke``: so wird getippt (Vorgabe: eine Wiederholung direkt in den Mitschnitt)."""
    from hrv_core import mitschnitt as mt

    from test_zaehlen_geraete import _wdh_rahmen
    from trainingsapp.devices import pmd

    n = int(sekunden / 0.18)
    alle = {round((i + 0.5) * n / tipps) for i in range(tipps)} if tipps else set()
    for k in range(k0, k0 + n):
        zeit.t += 0.18
        rahmen = _wdh_rahmen(innen, k, 10**12 + k * 180_000_000, periode=2.0 if bewegung else 1e9)
        innen.senden(pmd.PMD_DATA_UUID, rahmen, zeit.t)
        if k - k0 in alle:
            if marke is None:
                lauf.marke(mt.MARKE_WDH)
            else:
                marke()
        if k % 5 == 0 and e.laeuft:
            e.takt()
        if k % 25 == 0:
            await asyncio.sleep(0)
    if e.laeuft:
        e.takt()
    return k0 + n


def _kontextzeilen(lauf) -> list[dict]:
    from hrv_core import mitschnitt as mt

    lauf.mitschnitt.sichern()
    return [z for z in mt.lesen(lauf.mitschnitt.pfad) if z.get("art") == mt.KONTEXT]


def _eingaben_wie_hrv_research(kontext: list[dict]) -> dict:
    """Wie ``hrv_research.beschleunigung.trainingsapp_diagnose.saetze`` die Eingaben zuordnet:
    die k-te ``satz``-Zeile nach ``uebung_start`` (Dateireihenfolge) ist Satz k, nach
    ``uebung_ende`` gehört sie zu keiner Übung."""
    gruppen: dict = {}
    aktuell, nummer = None, 0
    for z in kontext:
        if z.get("was") == "uebung_start":
            aktuell, nummer = z.get("uebung_id"), 0
        elif z.get("was") == "uebung_ende":
            aktuell = None
        elif z.get("was") == "satz":
            nummer += 1
            gruppen[(aktuell, nummer if aktuell is not None else None)] = z.get("wert")
    return gruppen


async def test_im_diagnosemodus_steht_der_gezaehlte_satz_vor_dem_ende_der_uebung(
    tmp_path, monkeypatch
) -> None:
    """Die Kontextzeile ``satz`` (der eingetragene Satz, Vertrag §14) eines gezählten Satzes
    steht zwischen ``uebung_start`` und ``uebung_ende`` — eingetragen wird erst nach dem Ende
    der Einheit, die Notiz zum Satz kam dahinter: hrv-research legte jeden gezählten Satz in
    eine Gruppe ohne Übung (Runde 3, Befund 1). Ein Satz, eine Zeile; mit der Uhr je Satz eine."""
    from trainingsapp.core.kurzcode import kurzcode

    state, zeit, lauf, innen, gemeldet = await _diagnose_umgebung(tmp_path, monkeypatch)
    try:
        u = _uebung(state)
        e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
        await asyncio.sleep(0)
        k = await _rahmen(lauf, innen, zeit, e, 0, 24.0, tipps=12)
        uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_FERTIG)
        await _warten(lambda: bool(_eintraege(state)))
        await _warten(lambda: vorbei(state))
        ((gezaehlt,),) = [x.result["reps"] for x in _eintraege(state)]
        zeilen = _kontextzeilen(lauf)
        was = [z["was"] for z in zeilen]
        assert was.count("satz") == 1
        assert was.index("uebung_start") < was.index("satz") < was.index("uebung_ende")
        code = kurzcode(u.id)
        assert _eingaben_wie_hrv_research(zeilen) == {(code, 1): gezaehlt}  # vorher (None, None)
        assert [(v["marken"], v["eingetragen"]) for v in gemeldet] == [(12, gezaehlt)]

        # Mit der Uhr (2 × 20 s): je Satz eine Zeile, beide vor dem Ende der Übung
        wandsitz = _uebung(state, "Wandsitz", "hold", "reps")
        kontext = uebung_lauf.kontext_fuer(wandsitz)
        mit_uhr = uebung_lauf.starten(Seite(), state, kontext, _profil())
        k = await _rahmen(lauf, innen, zeit, mit_uhr, k, 0.5)
        uebung_lauf.zaehlen_starten(Seite(), state, kontext)
        for sekunden, tipps in ((20.0, 10), (10.0, 0), (20.0, 10), (12.0, 0)):
            k = await _rahmen(lauf, innen, zeit, mit_uhr, k, sekunden, tipps=tipps)
        await _warten(lambda: bool(_personen_eintraege(state, mit_uhr.id)))
        (eintrag,) = [x for x in _eintraege(state) if x.exercise_id == wandsitz.id]
        zeilen = _kontextzeilen(lauf)
        code2 = kurzcode(wandsitz.id)
        reps = eintrag.result["reps"]
        assert len(reps) == 2
        assert {s: w for s, w in _eingaben_wie_hrv_research(zeilen).items() if s[0] != code} == {
            (code2, 1): reps[0],
            (code2, 2): reps[1],
        }  # vorher: {(None, None): …}
    finally:
        await _diagnose_aus(state, lauf)


async def test_im_diagnosemodus_vergleicht_der_nachtrag_neben_der_uhr_nicht_noch_einmal(
    tmp_path, monkeypatch
) -> None:
    """Endet das Zählen von selbst und die Uhr läuft weiter, ist der Satz beim Vergleich nicht
    eingetragen. „Eintragen“ der Meldung schreibt seine Notiz — sie vergleicht nicht noch
    einmal mit leerem Fenster („Marken 0 · Sensor – · eingetragen 10“ ersetzte den
    richtigen, Runde 3, Befund 2), der Vergleich bekommt den eingetragenen Wert."""
    from trainingsapp.core.diagnose import satz_text

    state, zeit, lauf, innen, gemeldet = await _diagnose_umgebung(tmp_path, monkeypatch)
    try:
        u = _uebung(state, "Wandsitz", "hold", "reps")
        kontext = uebung_lauf.kontext_fuer(u)
        profil = TimerProfil(name="Halten 3 min", abschnitte=[Abschnitt("Halten", 180)])
        e = uebung_lauf.starten(Seite(), state, kontext, profil)
        k = await _rahmen(lauf, innen, zeit, e, 0, 1.0)
        uebung_lauf.zaehlen_starten(Seite(), state, kontext)
        k = await _rahmen(lauf, innen, zeit, e, k, 20.0, tipps=10)
        k = await _rahmen(lauf, innen, zeit, e, k, 70.0, bewegung=False)
        z = e.teil("zaehlen")
        assert isinstance(z, ZaehlBaustein) and z.grund == ENDE_KEINE_BEWEGUNG and e.laeuft
        (vorher,) = gemeldet
        assert vorher["marken"] == 10 and vorher["eingetragen"] is None
        meldung = uebung_lauf.meldung_abholen(state)
        assert meldung is not None
        eintrag = uebung_lauf.lauf_eintragen(state, meldung.einheit_id)
        assert eintrag is not None
        (wert,) = eintrag.result["reps"]
        v = lauf.letzter_satz
        assert v is not None
        assert (v["marken"], v["sensor"], v["eingetragen"]) == (10, vorher["sensor"], wert)
        assert (
            satz_text(v)
            == f"Wandsitz S1: Marken 10 · Sensor {vorher['sensor']} · eingetragen {wert}"
        )
        assert [x["marken"] for x in gemeldet] == [10, 10]  # vorher: [10, 0]
        was = [z["was"] for z in _kontextzeilen(lauf)]
        assert was.count("satz") == 1 and was.index("satz") > was.index("zaehlen_ende")
        assert "uebung_ende" not in was  # die Uhr läuft noch: die Zeile gehört zur Übung
        e.timer.lauf.abbrechen()
        await _rahmen(lauf, innen, zeit, e, k, 2.0)
        await _warten(lambda: vorbei(state))
    finally:
        await _diagnose_aus(state, lauf)


def _tippen(state):
    """Ein Tipp in die Marken-Leiste (`components.marken_stand`, wie ⏯ an der Uhr)."""
    from trainingsapp.ui.components import marken_stand

    return lambda: marken_stand.marke_setzen(state)


def _kopf(state) -> str:
    """Die Kopfzeile der Marken-Leiste: „Wiederholung · Kniebeuge S2“."""
    from trainingsapp.ui.components import marken_stand

    k, art = marken_stand.kontext(state)
    return k.text(art)


def _wdh_marken(lauf) -> list[dict]:
    """Die Wiederholungsmarken im Mitschnitt, mit ihrem Kontext."""
    from hrv_core import mitschnitt as mt

    lauf.mitschnitt.sichern()
    return [
        z
        for z in mt.lesen(lauf.mitschnitt.pfad)
        if z.get("art") == mt.MARKE and z.get("typ") == mt.MARKE_WDH
    ]


def _chip(state, uebung: Exercise, wert: int, saetze: int = 1) -> None:
    """Ein Chip „+wert“ (mit ``saetze`` „Sätze × Wert“) wie `views.plan.anhaengen` (dort mit
    flet): zuerst die Sätze davor, die nur der Sensor zählte (`uebung_lauf.
    vor_dem_satz_von_hand`, ihre Notizen in `zaehl_stand.zaehl_notizen`), dann je Satz der Wert,
    die Notiz zum Satz (`ui.marken.leistung`; ohne Grenze, die Übung klammert) und im
    Diagnosemodus das Ende des Satzes des Sensors (`zaehl_stand.von_hand_eingetragen`)."""
    import contextlib

    from trainingsapp.ui import marken

    vorab = uebung_lauf.vor_dem_satz_von_hand(state, uebung.id, None, "reps")
    session = state.sitzungen.session_fuer(state.profil.id, None, state.heute())
    for i, w in enumerate([*vorab, *[wert] * saetze]):
        gezaehlt = i < len(vorab)
        eintrag = state.sitzungen.satz_anhaengen(
            session, uebung, "reps", float(w), state.heute(), {}
        )
        with zaehl_stand.zaehl_notizen(state) if gezaehlt else contextlib.nullcontext():
            assert marken.leistung(
                state, uebung, eintrag, "reps", float(w), erster=False, grenze=False
            )
        if not gezaehlt:
            zaehl_stand.von_hand_eingetragen(state, uebung.id, None, "reps")


async def test_im_diagnosemodus_tragen_die_marken_den_satz_des_zaehlens(
    tmp_path, monkeypatch
) -> None:
    """Uhr mit drei zählenden Abschnitten und „Wdh. zählen“, ohne einen Chip: Bis zum Ende
    kommt keine Leistung in die Notizen — die Marken trugen alle „S1“, ihre Nummer lief durch,
    Kopfzeile und Seite „Diagnose“ an der Uhr sagten „S1“, und hrv-research legte alle Marken
    zu Satz 1 (Runde 3, Verdacht). Während des Zählens gilt die Nummer des Zähl-Teils: je Satz seine
    Marken ab 1, und Satz k der Marken ist Satz k der Eingaben."""
    from collections import Counter

    from trainingsapp.core.kurzcode import kurzcode
    from trainingsapp.ui.components import marken_stand

    state, zeit, lauf, innen, gemeldet = await _diagnose_umgebung(tmp_path, monkeypatch)
    try:
        u = _uebung(state, "Wandsitz", "hold", "reps")
        kontext = uebung_lauf.kontext_fuer(u)
        profil = TimerProfil(
            name="Halten 3 × 20 s",
            abschnitte=[Abschnitt("Halten", 20), Abschnitt("Pause", 10, zaehlt=False)],
            runden=3,
        )
        e = uebung_lauf.starten(Seite(), state, kontext, profil)
        k = await _rahmen(lauf, innen, zeit, e, 0, 0.5)
        uebung_lauf.zaehlen_starten(Seite(), state, kontext)
        koepfe, uhr = [], []
        for runde in range(3):
            k = await _rahmen(lauf, innen, zeit, e, k, 12.0, tipps=6, marke=_tippen(state))
            koepfe.append(_kopf(state))
            uhr.append(marken_stand.uhr_zeilen(state))
            sekunden = 7.5 if runde == 0 else 8.0
            k = await _rahmen(lauf, innen, zeit, e, k, sekunden, tipps=4, marke=_tippen(state))
            k = await _rahmen(lauf, innen, zeit, e, k, 10.0)
        k = await _rahmen(lauf, innen, zeit, e, k, 3.0)
        await _warten(lambda: bool(_personen_eintraege(state, e.id)))
        await _warten(lambda: vorbei(state))
        assert koepfe == [f"Wiederholung · Wandsitz S{n}" for n in (1, 2, 3)]  # vorher: S1 S1 S1
        assert [z for _, z in uhr] == ["Wandsitz S1", "Wandsitz S2", "Wandsitz S3"]
        marken = _wdh_marken(lauf)
        je_satz = Counter(m["kontext"].get("satz") for m in marken)
        assert set(je_satz) == {1, 2, 3}  # vorher: {1: 21}
        for satz in (1, 2, 3):  # die Nummer im Satz beginnt je Satz bei 1
            assert next(m["nr"] for m in marken if m["kontext"].get("satz") == satz) == 1
        assert [v["satz"] for v in gemeldet] == [1, 2, 3]
        code = kurzcode(u.id)
        assert (
            {(m["kontext"].get("uebung_id"), m["kontext"].get("satz")) for m in marken}
            == set(_eingaben_wie_hrv_research(_kontextzeilen(lauf)))
            == {(code, 1), (code, 2), (code, 3)}
        )
    finally:
        await _diagnose_aus(state, lauf, zeit)


async def test_im_diagnosemodus_zaehlt_ein_satz_von_hand_die_nummer_einmal_weiter(
    tmp_path, monkeypatch
) -> None:
    """Kommt während des Zählens doch eine Notiz zum Satz — ein Chip im Diagnosemodus (P122:
    beide zählen, der Satz von Hand beendet den des Sensors) —, zählt die Nummer einmal
    weiter, nicht für Notiz und Zähl-Teil je einmal. Und tritt das Zählen einer Uhr bei,
    nachdem schon ein Satz von Hand eingetragen war, zählt es von dort weiter, nicht ab S1."""
    state, zeit, lauf, innen, _gemeldet = await _diagnose_umgebung(tmp_path, monkeypatch)
    try:
        u = _uebung(state)
        wandsitz = _uebung(state, "Wandsitz", "hold", "reps")  # vor dem ersten Tipp (Katalog)
        e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
        await asyncio.sleep(0)
        k = await _rahmen(lauf, innen, zeit, e, 0, 12.0, tipps=6, marke=_tippen(state))
        assert _kopf(state) == "Wiederholung · Kniebeuge S1"
        _chip(state, u, 6)
        assert _kopf(state) == "Wiederholung · Kniebeuge S2"  # nicht S3
        k = await _rahmen(lauf, innen, zeit, e, k, 10.0, tipps=5, marke=_tippen(state))
        assert _kopf(state) == "Wiederholung · Kniebeuge S2"
        uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_FERTIG)
        await _warten(lambda: vorbei(state))
        # Auch die ersten Tipps, vor der Notiz „Kniebeuge: Start“ (die 5-s-Regel der Einheit):
        # Der Satz zählt schon — Wiederholungen von Satz 1 (vorher Atemzüge ohne Übung), nach
        # dem Chip alle fünf Satz 2
        satz_je_marke = [m["kontext"].get("satz") for m in _wdh_marken(lauf)]
        assert satz_je_marke == [1] * 6 + [2] * 5

        # Die Uhr läuft, ein Satz von Hand, dann „Wdh. zählen“: der Satz des Sensors ist S2
        kontext = uebung_lauf.kontext_fuer(wandsitz)
        profil = TimerProfil(name="Halten 3 min", abschnitte=[Abschnitt("Halten", 180)])
        mit_uhr = uebung_lauf.starten(Seite(), state, kontext, profil)
        k = await _rahmen(lauf, innen, zeit, mit_uhr, k, 8.0)
        assert _kopf(state) == "Wiederholung · Wandsitz S1"
        _chip(state, wandsitz, 10)
        assert _kopf(state) == "Wiederholung · Wandsitz S2"
        uebung_lauf.zaehlen_starten(Seite(), state, kontext)
        k = await _rahmen(lauf, innen, zeit, mit_uhr, k, 1.0)  # die Anforderung geht durch
        assert _kopf(state) == "Wiederholung · Wandsitz S2"  # nicht wieder S1
        k = await _rahmen(lauf, innen, zeit, mit_uhr, k, 12.0, tipps=6, marke=_tippen(state))
        assert _kopf(state) == "Wiederholung · Wandsitz S2"
        wandsitz_marken = [
            m["kontext"].get("satz")
            for m in _wdh_marken(lauf)
            if m["kontext"].get("uebung") == "Wandsitz"
        ]
        assert wandsitz_marken == [2] * 6
        mit_uhr.timer.lauf.abbrechen()
        await _rahmen(lauf, innen, zeit, mit_uhr, k, 2.0)
        await _warten(lambda: vorbei(state))
    finally:
        await _diagnose_aus(state, lauf, zeit)


# -- Befunde der fünften Runde: Satz von Hand neben dem Sensor, Zeilen ``satz`` ---------------


def _drei_runden(halten: float = 20) -> TimerProfil:
    return TimerProfil(
        name=f"Halten 3 × {halten:g} s",
        abschnitte=[Abschnitt("Halten", halten), Abschnitt("Pause", 10, zaehlt=False)],
        runden=3,
    )


def _wandsitz_marken(lauf) -> dict:
    from collections import Counter

    return dict(
        Counter(
            m["kontext"].get("satz")
            for m in _wdh_marken(lauf)
            if m["kontext"].get("uebung") == "Wandsitz"
        )
    )


async def test_im_diagnosemodus_kommt_ein_chip_neben_der_uhr_nach_den_saetzen_davor(
    tmp_path, monkeypatch
) -> None:
    """Uhr 3 × (20 s / 10 s) mit „Wdh. zählen“; Satz 1 zählt nur der Sensor, für Satz 2 tippt
    die Person in der Pause danach „+15“, Satz 3 wieder nur der Sensor. Vorher stand der Chip
    sofort im Tagebuch und im Mitschnitt, die Sätze des Sensors erst mit dem Ende: Tagebuch
    ``[15.0, 10, 10]``, hrv-research legte 15 zu Satz 1, und der Vergleich des Chips zählte
    die Marken ab dem Start der Übung (14 statt 7). Jetzt kommt Satz 1 vor dem Chip hinein, das
    Zählen läuft weiter. Und die ersten Tipps jedes Abschnitts sind Wiederholungen ihres Satzes,
    nicht Atemzüge (die Notiz des Abschnitts kommt erst nach 5 s)."""
    from trainingsapp.core.kurzcode import kurzcode

    state, zeit, lauf, innen, gemeldet = await _diagnose_umgebung(tmp_path, monkeypatch)
    try:
        u = _uebung(state, "Wandsitz", "hold", "reps")
        kontext = uebung_lauf.kontext_fuer(u)
        e = uebung_lauf.starten(Seite(), state, kontext, _drei_runden())
        k = await _rahmen(lauf, innen, zeit, e, 0, 0.5)
        uebung_lauf.zaehlen_starten(Seite(), state, kontext)
        z = e.teil("zaehlen")
        assert isinstance(z, ZaehlBaustein)
        k = await _rahmen(lauf, innen, zeit, e, k, 19.5, tipps=10, marke=_tippen(state))
        k = await _rahmen(lauf, innen, zeit, e, k, 10.0, bewegung=False)
        k = await _rahmen(lauf, innen, zeit, e, k, 20.0, tipps=10, marke=_tippen(state))
        k = await _rahmen(lauf, innen, zeit, e, k, 2.0, bewegung=False)
        _chip(state, u, 15)
        assert z.aktiv and [s.von_hand for s in z.saetze] == [True, True]  # läuft weiter
        k = await _rahmen(lauf, innen, zeit, e, k, 8.0, bewegung=False)
        k = await _rahmen(lauf, innen, zeit, e, k, 20.0, tipps=10, marke=_tippen(state))
        assert _kopf(state) == "Wiederholung · Wandsitz S3"
        k = await _rahmen(lauf, innen, zeit, e, k, 12.0, bewegung=False)
        await _warten(lambda: bool(_personen_eintraege(state, e.id)))
        await _warten(lambda: vorbei(state))
        s1, _s2, s3 = z.saetze
        (eintrag,) = _eintraege(state)
        assert eintrag.result["reps"] == [s1.wert, 15.0, s3.wert]  # vorher: [15.0, 10, 10]
        assert eintrag.result["hold"] == [20, 20, 20]
        code = kurzcode(u.id)
        assert _eingaben_wie_hrv_research(_kontextzeilen(lauf)) == {
            (code, 1): s1.wert,
            (code, 2): 15.0,
            (code, 3): s3.wert,
        }  # vorher: Satz 1 = 15
        assert _wandsitz_marken(lauf) == {1: 10, 2: 10, 3: 10}  # vorher: je 7 (3 Atemzüge)
        (chip,) = [v for v in gemeldet if v["eingetragen"] == 15.0]
        assert (chip["satz"], chip["marken"]) == (2, 10)  # vorher: S2, Marken 14
        assert [v["satz"] for v in gemeldet] == [1, 2, 3]
    finally:
        await _diagnose_aus(state, lauf, zeit)


@pytest.mark.parametrize(
    ("chip_nach_s", "danach_bewegung"), [(12.0, True), (12.0, False), (2.0, True)]
)
async def test_im_diagnosemodus_beginnt_ein_chip_mitten_im_abschnitt_keinen_satz(
    tmp_path, monkeypatch, chip_nach_s: float, danach_bewegung: bool
) -> None:
    """Mit der Uhr ist jeder zählende Abschnitt ein Satz: Ein Chip mitten in Halten 2 beendet
    dessen Satz, ein neuer beginnt erst mit Halten 3. Vorher begann sofort einer — der Rest
    des Abschnitts kam als eigener Satz ins Tagebuch (``[15.0, 10, 4, 10]`` für drei
    Haltezeiten) oder verbrauchte still eine Nummer (Halten 3 hieß „S4“). Und ein Chip in den
    ersten 5 s (2 s nach dem Signal) verlor sein Kennzeichen mit dem Fehlstart: Der Sensor trug
    alle Sätze ein, zusätzlich zum Chip (``[15.0, 10, 9, 10]``)."""
    from trainingsapp.core.kurzcode import kurzcode

    state, zeit, lauf, innen, gemeldet = await _diagnose_umgebung(tmp_path, monkeypatch)
    try:
        u = _uebung(state, "Wandsitz", "hold", "reps")
        kontext = uebung_lauf.kontext_fuer(u)
        e = uebung_lauf.starten(Seite(), state, kontext, _drei_runden())
        k = await _rahmen(lauf, innen, zeit, e, 0, 0.5)
        uebung_lauf.zaehlen_starten(Seite(), state, kontext)
        z = e.teil("zaehlen")
        assert isinstance(z, ZaehlBaustein)
        k = await _rahmen(lauf, innen, zeit, e, k, 19.5, tipps=10, marke=_tippen(state))
        k = await _rahmen(lauf, innen, zeit, e, k, 10.0, bewegung=False)
        tipps = round(chip_nach_s / 2)
        k = await _rahmen(lauf, innen, zeit, e, k, chip_nach_s, tipps=tipps, marke=_tippen(state))
        _chip(state, u, 15)
        assert len(z.saetze) == 2 and z.saetze[1].von_hand  # kein dritter, der Rest zählt nicht
        rest = 20.0 - chip_nach_s
        k = await _rahmen(lauf, innen, zeit, e, k, rest, bewegung=danach_bewegung)
        k = await _rahmen(lauf, innen, zeit, e, k, 10.0, bewegung=False)
        k = await _rahmen(lauf, innen, zeit, e, k, 20.0, tipps=10, marke=_tippen(state))
        assert _kopf(state) == "Wiederholung · Wandsitz S3"  # vorher: S4
        k = await _rahmen(lauf, innen, zeit, e, k, 12.0, bewegung=False)
        await _warten(lambda: bool(_personen_eintraege(state, e.id)))
        await _warten(lambda: vorbei(state))
        assert [s.von_hand for s in z.saetze] == [True, True, False]
        s1, _s2, s3 = z.saetze
        (eintrag,) = _eintraege(state)
        assert eintrag.result["reps"] == [s1.wert, 15.0, s3.wert]
        assert eintrag.result["hold"] == [20, 20, 20]
        code = kurzcode(u.id)
        assert _eingaben_wie_hrv_research(_kontextzeilen(lauf)) == {
            (code, 1): s1.wert,
            (code, 2): 15.0,
            (code, 3): s3.wert,
        }
        assert _wandsitz_marken(lauf) == {1: 10, 2: tipps, 3: 10}
        assert [v["satz"] for v in gemeldet] == [1, 2, 3]
    finally:
        await _diagnose_aus(state, lauf, zeit)


async def test_im_diagnosemodus_zaehlt_ein_chip_bei_angehaltener_uhr_nichts_doppelt(
    tmp_path, monkeypatch
) -> None:
    """Uhr „Halten 3 min“, „Wdh. zählen“; nach 20 s „Anhalten“, Chip „+10“, „Weiter“. Vorher
    begann der Chip den nächsten Satz, während das Zählen angehalten war, „Weiter“ hängte ein
    zweites offenes Stück an, und der Prototyp zählte dieselben Daten zweimal: Satz 2 kam mit
    20 statt 10 ins Tagebuch. Mit der Uhr ist der Abschnitt ein Satz — der Chip war er."""
    state, zeit, lauf, innen, gemeldet = await _diagnose_umgebung(tmp_path, monkeypatch)
    try:
        u = _uebung(state, "Wandsitz", "hold", "reps")
        kontext = uebung_lauf.kontext_fuer(u)
        profil = TimerProfil(name="Halten 3 min", abschnitte=[Abschnitt("Halten", 180)])
        e = uebung_lauf.starten(Seite(), state, kontext, profil)
        k = await _rahmen(lauf, innen, zeit, e, 0, 0.5)
        uebung_lauf.zaehlen_starten(Seite(), state, kontext)
        z = e.teil("zaehlen")
        assert isinstance(z, ZaehlBaustein)
        k = await _rahmen(lauf, innen, zeit, e, k, 20.0, tipps=10, marke=_tippen(state))
        assert e.timer is not None
        e.timer.lauf.pause()  # „Anhalten“
        k = await _rahmen(lauf, innen, zeit, e, k, 3.0, bewegung=False)
        assert z.angehalten
        _chip(state, u, 10)
        k = await _rahmen(lauf, innen, zeit, e, k, 10.0, bewegung=False)
        e.timer.lauf.fortsetzen()  # „Weiter“
        k = await _rahmen(lauf, innen, zeit, e, k, 20.0, tipps=10, marke=_tippen(state))
        assert [s.von_hand for s in z.saetze] == [True]  # vorher: ein zweiter, zwei Stücke offen
        assert all(bis is not None for _, bis in z.saetze[0].stuecke)
        e.timer.lauf.fertig_machen()
        await _rahmen(lauf, innen, zeit, e, k, 2.0, bewegung=False)
        await _warten(lambda: bool(_personen_eintraege(state, e.id)))
        await _warten(lambda: vorbei(state))
        (eintrag,) = _eintraege(state)
        assert eintrag.result["reps"] == [10.0]  # vorher: [10.0, 20]
        assert len(eintrag.result["hold"]) == 1
        assert [v["eingetragen"] for v in gemeldet] == [10.0]
    finally:
        await _diagnose_aus(state, lauf, zeit)


async def test_im_diagnosemodus_bekommt_jeder_gezaehlte_satz_eine_zeile(
    tmp_path, monkeypatch
) -> None:
    """Sieht der Sensor in Halten 2 keine Wiederholung (die Person tippt 8), wird der Satz
    nicht eingetragen — vorher bekam er auch keine Zeile ``satz``, und hrv-research legte die
    Eingabe von Satz 3 zu Satz 2. Jetzt hat er eine ohne ``feld``/``wert`` („eingetragen –“),
    und die Marken tragen dieselben Nummern."""
    from trainingsapp.core.kurzcode import kurzcode

    state, zeit, lauf, innen, gemeldet = await _diagnose_umgebung(tmp_path, monkeypatch)
    try:
        u = _uebung(state, "Wandsitz", "hold", "reps")
        kontext = uebung_lauf.kontext_fuer(u)
        e = uebung_lauf.starten(Seite(), state, kontext, _drei_runden())
        k = await _rahmen(lauf, innen, zeit, e, 0, 0.5)
        uebung_lauf.zaehlen_starten(Seite(), state, kontext)
        z = e.teil("zaehlen")
        assert isinstance(z, ZaehlBaustein)
        k = await _rahmen(lauf, innen, zeit, e, k, 19.5, tipps=10, marke=_tippen(state))
        k = await _rahmen(lauf, innen, zeit, e, k, 10.0, bewegung=False)
        k = await _rahmen(
            lauf, innen, zeit, e, k, 20.0, tipps=8, bewegung=False, marke=_tippen(state)
        )
        k = await _rahmen(lauf, innen, zeit, e, k, 10.0, bewegung=False)
        k = await _rahmen(lauf, innen, zeit, e, k, 20.0, tipps=10, marke=_tippen(state))
        k = await _rahmen(lauf, innen, zeit, e, k, 12.0, bewegung=False)
        await _warten(lambda: bool(_personen_eintraege(state, e.id)))
        await _warten(lambda: vorbei(state))
        s1, s2, s3 = z.saetze
        assert s2.wert == 0 and s1.wert > 0 and s3.wert > 0
        (eintrag,) = _eintraege(state)
        assert eintrag.result["reps"] == [s1.wert, s3.wert]
        code = kurzcode(u.id)
        zeilen = _kontextzeilen(lauf)
        assert _eingaben_wie_hrv_research(zeilen) == {
            (code, 1): s1.wert,
            (code, 2): None,  # gezählt, nicht eingetragen
            (code, 3): s3.wert,
        }  # vorher: {(code, 1): s1, (code, 2): s3}
        leer = [zz for zz in zeilen if zz.get("was") == "satz" and zz.get("satz") == 2]
        assert len(leer) == 1 and "feld" not in leer[0] and "wert" not in leer[0]
        assert _wandsitz_marken(lauf) == {1: 10, 2: 8, 3: 10}
        assert [(v["satz"], v["eingetragen"]) for v in gemeldet] == [
            (1, s1.wert),
            (2, None),
            (3, s3.wert),
        ]
    finally:
        await _diagnose_aus(state, lauf, zeit)


async def test_im_diagnosemodus_haelt_ein_chip_nach_dem_abbruch_keinen_satz_fuer_den_nachtrag(
    tmp_path, monkeypatch
) -> None:
    """Uhr 3 × (40 s / 10 s), „Wdh. zählen“, nach 20 s „Zählen abbrechen“; danach zählt die
    Person von Hand weiter. Ein Chip mit zufällig demselben Wert wie der abgebrochene Satz galt
    als dessen Nachtrag: Satz 2 wurde nie verglichen, und der Vergleich von Satz 3 nahm Marken
    und Sensor von Satz 2 und 3 zusammen. Nur die Notizen beim Eintragen eines gezählten Satzes
    gehören zu ihm (`Messlauf.zaehl_notizen`)."""
    from trainingsapp.core.kurzcode import kurzcode
    from trainingsapp.core.zaehlen import ENDE_ABBRUCH as ABBRUCH

    state, zeit, lauf, innen, gemeldet = await _diagnose_umgebung(tmp_path, monkeypatch)
    try:
        u = _uebung(state, "Wandsitz", "hold", "reps")
        kontext = uebung_lauf.kontext_fuer(u)
        e = uebung_lauf.starten(Seite(), state, kontext, _drei_runden(40))
        k = await _rahmen(lauf, innen, zeit, e, 0, 0.5)
        uebung_lauf.zaehlen_starten(Seite(), state, kontext)
        z = e.teil("zaehlen")
        assert isinstance(z, ZaehlBaustein)
        k = await _rahmen(lauf, innen, zeit, e, k, 20.0, tipps=10, marke=_tippen(state))
        uebung_lauf.zaehlen_beenden(state, u.id, None, ABBRUCH)
        abgebrochen = z.saetze[0].wert
        assert abgebrochen > 0 and e.laeuft
        k = await _rahmen(lauf, innen, zeit, e, k, 19.5, bewegung=False)
        k = await _rahmen(lauf, innen, zeit, e, k, 10.0, bewegung=False)
        k = await _rahmen(lauf, innen, zeit, e, k, 20.0, tipps=10, marke=_tippen(state))
        vorher = len(gemeldet)
        _chip(state, u, abgebrochen)  # Satz 2 von Hand, zufällig gleich viele
        assert len(gemeldet) == vorher + 1
        satz2 = gemeldet[-1]
        assert satz2["satz"] == 2 and satz2["eingetragen"] == abgebrochen  # vorher: S1, Nachtrag
        assert satz2["marken"] == _wandsitz_marken(lauf)[2]
        k = await _rahmen(lauf, innen, zeit, e, k, 20.0, bewegung=False)
        k = await _rahmen(lauf, innen, zeit, e, k, 10.0, bewegung=False)
        k = await _rahmen(lauf, innen, zeit, e, k, 26.0, tipps=13, marke=_tippen(state))
        _chip(state, u, 13)
        satz3 = gemeldet[-1]
        # vorher: „S2: Marken 15 · Sensor 22“ — Satz 2 und 3 zusammen
        assert satz3["satz"] == 3 and satz3["marken"] == _wandsitz_marken(lauf)[3]
        assert satz3["sensor"] is not None and satz3["sensor"] <= 14
        code = kurzcode(u.id)
        assert _eingaben_wie_hrv_research(_kontextzeilen(lauf)) == {
            (code, 1): None,  # abgebrochen, nicht eingetragen
            (code, 2): float(abgebrochen),
            (code, 3): 13.0,
        }
        assert set(_wandsitz_marken(lauf)) == {1, 2, 3}
        assert e.timer is not None
        e.timer.lauf.abbrechen()
        await _rahmen(lauf, innen, zeit, e, k, 2.0)
        await _warten(lambda: vorbei(state))
    finally:
        await _diagnose_aus(state, lauf, zeit)


async def test_im_diagnosemodus_sind_saetze_mal_wert_mehrere_saetze(tmp_path, monkeypatch) -> None:
    """„Sätze × Wert“ 2 × 6 während des Zählens: zwei Sätze von Hand — der erste ist der des
    Sensors, der zweite einer ohne Sensor. Vorher endete nur einer, die Zeilen ``satz`` zählten
    zwei: Der nächste Satz des Sensors bekam die Eingabe des zweiten, und Satz 1 hatte drei
    Zeilen ``zaehler``."""
    from trainingsapp.core.kurzcode import kurzcode

    state, zeit, lauf, innen, gemeldet = await _diagnose_umgebung(tmp_path, monkeypatch)
    try:
        u = _uebung(state)
        e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
        await asyncio.sleep(0)
        z = e.teil("zaehlen")
        assert isinstance(z, ZaehlBaustein)
        k = await _rahmen(lauf, innen, zeit, e, 0, 12.0, tipps=6, marke=_tippen(state))
        _chip(state, u, 6, saetze=2)
        assert _kopf(state) == "Wiederholung · Kniebeuge S3"  # vorher: S2
        k = await _rahmen(lauf, innen, zeit, e, k, 16.0, tipps=8, marke=_tippen(state))
        uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_FERTIG)
        await _warten(lambda: vorbei(state))
        letzter = z.saetze[-1]
        assert [s.von_hand for s in z.saetze] == [True, True, False]
        (eintrag,) = _eintraege(state)
        assert eintrag.result["reps"] == [6.0, 6.0, letzter.wert]
        assert [(v["satz"], v["marken"]) for v in gemeldet] == [(1, 6), (2, 0), (3, 8)]
        code = kurzcode(u.id)
        zeilen = _kontextzeilen(lauf)
        assert _eingaben_wie_hrv_research(zeilen) == {
            (code, 1): 6.0,
            (code, 2): 6.0,
            (code, 3): letzter.wert,
        }  # vorher: Satz 3 ohne Eingabe, die 8 Marken bei „eingetragen 6“
        zaehler = [zz.get("satz") for zz in zeilen if zz.get("was") == "zaehler"]
        assert zaehler.count(1) == 1  # vorher: drei
        assert _wandsitz_marken(lauf) == {}
        from collections import Counter

        assert dict(Counter(m["kontext"].get("satz") for m in _wdh_marken(lauf))) == {1: 6, 3: 8}
    finally:
        await _diagnose_aus(state, lauf, zeit)


# -- Der Kontext, wenn er mitten im Lauf wechselt ---------------------------------------------


async def test_eintragen_der_meldung_nimmt_den_kontext_der_beigetretenen_uhr(umgebung) -> None:
    """Zählen auf der Übungsseite (ohne Plan), dann tritt die Uhr aus dem Plan „Beine“ bei —
    eingetragen wird, wo die Uhr läuft. Endet das Zählen von selbst und trägt „Eintragen“ der
    Meldung die Wiederholungen ein, gehören sie in denselben Eintrag wie später die Zeit.
    Vorher kamen sie in die Sitzung ohne Plan (der Kontext aus der Datenbank, dort noch der
    alte; Runde 3, Befund 12)."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    plan = _plan_mit(state, u)
    item = plan.items[0]
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 3)
    profil = TimerProfil(name="Halten 120 s", abschnitte=[Abschnitt("Halten", 120)])
    assert uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(u, plan, item), profil) is e
    await _ticken(state, uhr, gurt, 20)
    gurt.bewegung = False
    await _ticken(state, uhr, gurt, 62)
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein) and z.grund == ENDE_KEINE_BEWEGUNG and e.laeuft
    meldung = uebung_lauf.meldung_abholen(state)
    assert meldung is not None
    assert uebung_lauf.lauf_eintragen(state, meldung.einheit_id) is not None
    await _ticken(state, uhr, gurt, 40, bis_ende=True)
    await _warten(lambda: ze.TEIL_UHR in ze.eingetragen(state.einheiten.ereignisse(e.id)))
    ((eintrag, plan_id),) = _mit_sitzung(state)  # vorher: zwei Einträge in zwei Sitzungen
    assert plan_id == plan.id
    assert eintrag.result["hold"] == [120] and eintrag.result["reps"] == ze.wiederholungen(
        e.ereignisse
    )


async def test_nach_dem_absturz_gilt_der_kontext_von_dem_augenblick(umgebung, tmp_path) -> None:
    """Wechselt der Kontext mitten im Lauf (die Uhr tritt bei; abgehakt in einem Plan), steht
    er sofort in der Zeitleiste — stirbt die App danach, trägt „Läufe heute“ mit ihm ein.
    Vorher schrieb ihn erst das Ende der Einheit: Nach dem Absturz landeten die Wiederholungen
    in der Sitzung ohne Plan, und eine Uhr mit „zählt nicht“ trug doch ihre Haltezeit ein
    (Runde 3, Befund 14)."""
    state, uhr, gurt, _ = umgebung
    u = _uebung(state, "Wandsitz", "hold", "reps")
    plan = _plan_mit(state, u)
    item = plan.items[0]
    # (a) die Uhr aus dem Plan tritt dem Zählen der Übungsseite bei
    e, _ = uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 3)
    profil = TimerProfil(name="Halten 120 s", abschnitte=[Abschnitt("Halten", 120)])
    uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(u, plan, item), profil)
    await _ticken(state, uhr, gurt, 20)
    neu = _nach_dem_absturz(state, tmp_path, "a.db")
    try:
        (b,) = [x for x in neu.einheiten.beteiligungen(e.id) if x.art == "plan"]
        assert b.daten.get("plan") == plan.id  # vorher: kein Plan
        eintrag = uebung_lauf.lauf_eintragen(neu, e.id)
        assert eintrag is not None
        ((_, plan_id),) = _mit_sitzung(neu)
        assert plan_id == plan.id  # vorher: ohne Plan
    finally:
        neu.schliessen()
    z = e.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein)
    z.abbrechen()
    e.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, 2, bis_ende=True)

    # (b) die Uhr mit „zählt nicht“ tritt dem Zählen mit „Zeit zählt“ bei
    e2, _ = uebung_lauf.zaehlen_starten(
        Seite(), state, uebung_lauf.kontext_fuer(u, zeit_eintragen=True)
    )
    await _ticken(state, uhr, gurt, 3)
    uebung_lauf.starten(
        Seite(), state, uebung_lauf.kontext_fuer(u, zeit_eintragen=False), _profil()
    )
    await _ticken(state, uhr, gurt, 54)  # in der zweiten Pause
    neu = _nach_dem_absturz(state, tmp_path, "b.db")
    try:
        eintrag = uebung_lauf.lauf_eintragen(neu, e2.id)
        assert eintrag is not None
        assert "hold" not in eintrag.result and eintrag.result["reps"]  # vorher: hold [20, 20]
    finally:
        neu.schliessen()
    z2 = e2.teil("zaehlen")
    assert isinstance(z2, ZaehlBaustein)
    z2.abbrechen()
    e2.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, 2, bis_ende=True)

    # (c) Uhr und Zählen auf der Übungsseite, im Plan abgehakt — die Uhr läuft weiter
    e3 = uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(u), profil)
    uebung_lauf.zaehlen_starten(Seite(), state, uebung_lauf.kontext_fuer(u))
    await _ticken(state, uhr, gurt, 20)
    assert (
        uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABGEHAKT, ort=(plan.id, item.id))
        is not None
    )
    await _ticken(state, uhr, gurt, 10)
    neu = _nach_dem_absturz(state, tmp_path, "c.db")
    try:
        assert uebung_lauf.lauf_eintragen(neu, e3.id) is not None
        assert ze.TEIL_UHR in ze.eingetragen(neu.einheiten.ereignisse(e3.id))
        assert {p for _, p in _mit_sitzung(neu)} == {plan.id}  # vorher: auch ohne Plan
    finally:
        neu.schliessen()
    e3.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, 2, bis_ende=True)
