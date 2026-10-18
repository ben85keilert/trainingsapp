"""Timer einer Übung als Einheit (Ben, 17.10.2026; Skizzen 12–15): fertig = gemacht und
die gelaufene Zeit im Tagebuch; abgebrochen = nichts, aber unter „Läufe heute“ mit
„Eintragen“; Marken der Übung in einer laufenden HRV-Aufnahme."""

from __future__ import annotations

import asyncio

import pytest

from attrappen import Gurt, Seite, Uhr, ruhe, vorbei
from trainingsapp.core.models import Exercise
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld
from trainingsapp.core.timer import Abschnitt, TimerProfil
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import uebung_lauf
from trainingsapp.ui.state import AppState


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    """App-Zustand mit einer laufenden HRV-Aufnahme auf der Uhr-Attrappe."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    yield state, uhr, gurt, lauf
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


def _planke(state, *felder: str) -> Exercise:
    spec = ResultSpec(layout=Layout.SINGLE, fields=[f for k in felder if (f := vorrat_feld(k))])
    uebung = Exercise(name="Planke", result_spec=spec)
    state.uebungen.speichern(uebung)
    return uebung


def _profil() -> TimerProfil:
    return TimerProfil(
        name="Halten 3 × 10 s",
        abschnitte=[Abschnitt("Halten", 10), Abschnitt("Pause", 5, zaehlt=False)],
        runden=3,
    )


async def _ticken(state, uhr, gurt, e, sekunden: int, *, bis_ende: bool = False) -> None:
    for _ in range(sekunden):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        e.takt()
        if bis_ende and not e.laeuft:
            break
    if bis_ende:
        for _ in range(200):
            if vorbei(state):
                return
            await asyncio.sleep(0.01)
        raise AssertionError("Die Einheit endete nicht")


async def test_fertig_heisst_gemacht_mit_haltezeit_je_satz(umgebung) -> None:
    state, uhr, gurt, messlauf = umgebung
    uebung = _planke(state, "hold")
    seite = Seite()
    kontext = uebung_lauf.kontext_fuer(uebung)
    assert kontext.zeitfeld == "hold"
    e = uebung_lauf.starten(seite, state, kontext, _profil())
    assert e.hrv is not None and einheit_ui.titel(e) == "Planke"
    await _ticken(state, uhr, gurt, e, 60, bis_ende=True)
    (lauf,) = uebung_lauf.laeufe_heute(state, uebung.id)
    assert not lauf.abgebrochen and lauf.eintrag_id is not None and lauf.werte == [10, 10, 10]
    eintrag = state.sitzungen.eintrag_laden(lauf.eintrag_id)
    assert eintrag is not None and eintrag.result == {"hold": [10, 10, 10]}
    assert eintrag.ended_at is not None and eintrag.started_at is not None
    assert (eintrag.ended_at - eintrag.started_at).total_seconds() == pytest.approx(45, abs=1)
    # Die HRV lief weiter und hat die Übung als Abschnitt auf eigener Spur
    assert messlauf.aufnahme is not None
    marken = [x for x in messlauf.aufnahme.ereignisse if x.get("marke", {}).get("spur") == "uebung"]
    assert [x["text"] for x in marken] == ["Planke beginnt", "Planke fertig"]


async def test_abbrechen_traegt_nichts_ein_laeufe_heute_schon(umgebung) -> None:
    state, uhr, gurt, _ = umgebung
    uebung = _planke(state, "hold", "duration")
    seite = Seite()
    kontext = uebung_lauf.kontext_fuer(uebung, feld="duration")
    assert kontext.zeitfeld == "duration"
    e = uebung_lauf.starten(seite, state, kontext, _profil())
    await _ticken(state, uhr, gurt, e, 22)  # Halten 10 s, Pause 5 s, Halten 7 s
    assert e.timer is not None
    e.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, e, 2, bis_ende=True)
    (lauf,) = uebung_lauf.laeufe_heute(state, uebung.id)
    assert lauf.abgebrochen and lauf.eintrag_id is None
    assert lauf.dauer_s == pytest.approx(17, abs=0.01)
    assert state.sitzungen.eintraege_am_tag(state.profil.id, lauf.beginn.astimezone().date()) == []
    # Zwei Tipps (Uhr → „Eintragen“): doch eintragen, mit der Zeit, die er lief
    eintrag = uebung_lauf.lauf_eintragen(state, lauf.einheit_id)
    assert eintrag is not None and eintrag.result == {"duration": 17}
    assert uebung_lauf.lauf_eintragen(state, lauf.einheit_id) is None  # nicht doppelt
    (wieder,) = uebung_lauf.laeufe_heute(state, uebung.id)
    assert wieder.eintrag_id == eintrag.id and wieder.werte == [17]


async def test_ohne_zeit_eintragen_nur_gemacht(umgebung) -> None:
    state, uhr, gurt, _ = umgebung
    uebung = _planke(state, "hold")
    kontext = uebung_lauf.kontext_fuer(uebung, zeit_eintragen=False)
    assert kontext.zeitfeld is None
    e = uebung_lauf.starten(Seite(), state, kontext, _profil())
    await _ticken(state, uhr, gurt, e, 60, bis_ende=True)
    (lauf,) = uebung_lauf.laeufe_heute(state, uebung.id)
    eintrag = state.sitzungen.eintrag_laden(lauf.eintrag_id)
    assert eintrag is not None and eintrag.result == {}  # „gemacht“


async def test_zweite_einheit_waehrend_einer_laeuft_geht_nicht(umgebung) -> None:
    state, uhr, gurt, _ = umgebung
    uebung = _planke(state, "hold")
    kontext = uebung_lauf.kontext_fuer(uebung)
    e = uebung_lauf.starten(Seite(), state, kontext, _profil())
    with pytest.raises(RuntimeError, match="läuft schon"):
        uebung_lauf.starten(Seite(), state, kontext, _profil())
    e.timer.lauf.abbrechen()
    await _ticken(state, uhr, gurt, e, 2, bis_ende=True)


async def test_marken_einer_uebung_nennen_sie_und_den_ablauf(umgebung) -> None:
    """Ben, 18.10.2026 (P54): Jede Marke der Übung trägt ihren Kurzcode, der Text nennt den
    Timer nicht mehr, „Timer fertig“ fällt weg (stille Grenze), die Marke trägt die geplante
    Dauer und welcher Ablauf lief."""
    from trainingsapp.core.kurzcode import kurzcode

    state, uhr, gurt, messlauf = umgebung
    uebung = _planke(state, "hold")
    profil = _profil()
    e = uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(uebung), profil)
    await _ticken(state, uhr, gurt, e, 60, bis_ende=True)
    notizen = messlauf.aufnahme.ereignisse
    texte = [x["text"] for x in notizen]
    assert "Halten (Runde 1/3)" in texte and not any(t.startswith("Timer „") for t in texte)
    assert "Timer fertig" not in texte and "Planke fertig" in texte
    timer = [x for x in notizen if x.get("marke", {}).get("quelle") == "timer"]
    assert timer and all(x.get("uebungen") == [kurzcode(uebung.id)] for x in timer)
    halten = next(x for x in timer if x["text"] == "Halten (Runde 1/3)")
    assert halten["marke"]["soll_s"] == 10.0 and halten["marke"]["profil"] == kurzcode(profil.id)


async def test_stoppuhr_marke_heisst_stoppuhr_ohne_soll(umgebung) -> None:
    from trainingsapp.core.timer import stoppuhr

    state, uhr, gurt, messlauf = umgebung
    uebung = _planke(state, "hold")
    e = uebung_lauf.starten(Seite(), state, uebung_lauf.kontext_fuer(uebung), stoppuhr())
    await _ticken(state, uhr, gurt, e, 20)
    e.timer.lauf.fertig_machen()
    await _ticken(state, uhr, gurt, e, 2, bis_ende=True)
    (marke,) = [
        x["marke"]
        for x in messlauf.aufnahme.ereignisse
        if x.get("marke", {}).get("quelle") == "timer"
    ]
    assert marke["profil"] == "stoppuhr" and "soll_s" not in marke
    (eintrag,) = [x for x, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]
    assert eintrag.result == {"hold": [20]}
