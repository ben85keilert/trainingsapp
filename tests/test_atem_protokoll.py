"""Das Protokollfeld „Atmung“ der Messdatei (`core.atem_protokoll`, Vertrag §5, P125): die
Regel aus den Übungen der Aufnahme, der Platz im Kopf, die Rundreise über `Recording.extra`
und der Messlauf, der es beim Speichern, im Backup und beim Wiederherstellen setzt."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from hrv_core.deid import deidentifizieren_dict
from hrv_core.recording import Recording, laden, speichern

from trainingsapp.core import atem_protokoll as ap
from trainingsapp.devices.messlauf import Messlauf, backup_wiederherstellen
from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource

ATEM, KNIE = "ATEMATEM", "KNIEBEUG"
KATALOG = {ATEM: True, KNIE: False}.get


def test_regel_uebung_spontan_unbekannt() -> None:
    assert ap.protokoll([], KATALOG) == {"art": ap.ART_SPONTAN}
    assert ap.protokoll([{"text": "Box Breathing", "uebungen": [ATEM]}], KATALOG) == {
        "art": ap.ART_UEBUNG,
        "uebung": ATEM,
    }
    # Erst Kniebeugen, dann die Atemübung: die Atemübung zählt
    assert ap.protokoll([{"uebungen": [KNIE]}, {"uebungen": [ATEM]}], KATALOG)["uebung"] == ATEM
    # Nur andere oder unbekannte Übungen: kein Feld (unbekannt — es wird nicht geraten)
    assert ap.protokoll([{"uebungen": [KNIE]}], KATALOG) is None
    assert ap.protokoll([{"uebungen": ["XXXXXXXX"]}], KATALOG) is None
    assert ap.feld_lesen({"atmung": {"art": "uebung", "uebung": ATEM}}) is not None
    assert ap.feld_lesen({"atmung": {"art": "geraten"}}) is None and ap.feld_lesen({}) is None


def test_rundreise_ueber_recording_extra_und_deid(tmp_path) -> None:
    """Das Feld steht hinter ``datenqualitaet``; `Recording` hält es in ``extra`` und schreibt es
    wieder; Altdateien ohne Feld bleiben lesbar; `deid` behält es."""
    rec = Recording(geraet="H10", geraet_profil="polar_h10")
    pfad = speichern(rec, tmp_path)
    ap.kopffeld_schreiben(pfad, {"art": "uebung", "uebung": ATEM})
    schluessel = list(json.loads(pfad.read_text(encoding="utf-8")))
    assert schluessel.index("atmung") == schluessel.index("datenqualitaet") + 1
    geladen = laden(pfad)
    assert geladen.extra["atmung"] == {"art": "uebung", "uebung": ATEM}
    assert ap.feld_lesen(geladen.extra) == {"art": "uebung", "uebung": ATEM}
    wieder = speichern(geladen, tmp_path / "kopie")
    assert laden(wieder).extra["atmung"] == {"art": "uebung", "uebung": ATEM}
    bereinigt, _ = deidentifizieren_dict(json.loads(wieder.read_text(encoding="utf-8")))
    assert bereinigt["atmung"]["uebung"] == ATEM
    # Altdatei: kein Feld, kein Standardwert
    alt = laden(speichern(Recording(geraet="H10", geraet_profil="polar_h10"), tmp_path / "alt"))
    assert "atmung" not in alt.extra and ap.feld_lesen(alt.extra) is None
    assert ap.text({"art": "spontan"}) == "spontan geatmet" and ap.text(None) == ""


# -- Messlauf ----------------------------------------------------------------------------------


async def _lauf(tmp_path: Path, haken) -> tuple[Messlauf, asyncio.Task]:
    lauf = Messlauf(SimulatedSource(tempo=60.0, seed=7), backup_basis=tmp_path)
    lauf.atmung_protokoll = haken
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    return lauf, task


async def _bis(lauf: Messlauf, sekunden: float) -> None:
    while lauf.aufnahme_dauer_s() < sekunden:
        await asyncio.sleep(0.01)


def _doc(pfad: Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


async def test_messlauf_schreibt_uebung_ins_backup_und_in_die_messdatei(tmp_path) -> None:
    """Lief eine Atemübung (Notiz mit ihrem Kurzcode, wie die Einheit sie setzt), trägt die
    Messdatei ``atmung = uebung`` hinter ``datenqualitaet``; das Backup hat das Feld im Block
    ``_wiederherstellung`` — bestimmt im Loop, geschrieben im Thread (`aufnahme_stoppen_async`)."""
    lauf, task = await _lauf(tmp_path, lambda er: ap.protokoll(er, KATALOG))
    await _bis(lauf, 10)
    lauf.notiz_hinzufuegen("Box Breathing", uebungen=[ATEM])
    await _bis(lauf, 20)
    lauf.backup_jetzt()
    backup = next(tmp_path.rglob(".backup_*.json"))
    assert _doc(backup)["_wiederherstellung"]["atmung"] == {"art": "uebung", "uebung": ATEM}
    ergebnis = await lauf.aufnahme_stoppen_async(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None
    doc = _doc(ergebnis.pfad)
    assert doc["atmung"] == {"art": "uebung", "uebung": ATEM}
    schluessel = list(doc)
    assert schluessel.index("atmung") == schluessel.index("datenqualitaet") + 1
    assert laden(ergebnis.pfad).extra["atmung"]["art"] == "uebung"
    assert not list(tmp_path.rglob(".backup_*"))


async def test_messlauf_spontan_ohne_uebung_und_unbekannt_bei_anderer(tmp_path) -> None:
    lauf, task = await _lauf(tmp_path, lambda er: ap.protokoll(er, KATALOG))
    await _bis(lauf, 10)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)  # der synchrone Weg bestimmt das Feld selbst
    assert ergebnis is not None and _doc(ergebnis.pfad)["atmung"] == {"art": "spontan"}
    lauf.aufnahme_starten()
    lauf.notiz_hinzufuegen("Kniebeuge: Start", uebungen=[KNIE])
    await _bis(lauf, 10)
    ergebnis2 = await lauf.aufnahme_stoppen_async(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis2 is not None and "atmung" not in _doc(ergebnis2.pfad)
    assert "atmung" not in laden(ergebnis2.pfad).extra


async def test_ohne_haken_kein_feld_und_fehler_im_haken_kostet_nur_das_feld(tmp_path) -> None:
    lauf, task = await _lauf(tmp_path, None)
    await _bis(lauf, 5)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None and "atmung" not in _doc(ergebnis.pfad)

    def kaputt(_er):
        raise RuntimeError("Katalog weg")

    lauf.atmung_protokoll = kaputt
    lauf.aufnahme_starten()
    await _bis(lauf, 5)
    ergebnis2 = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis2 is not None and "atmung" not in _doc(ergebnis2.pfad)


async def test_wiederherstellen_nimmt_das_feld_aus_dem_backup(tmp_path) -> None:
    lauf, task = await _lauf(tmp_path, lambda er: ap.protokoll(er, KATALOG))
    await _bis(lauf, 10)
    lauf.backup_jetzt()
    # „Absturz“ — nur Kopf und Journal liegen da; ohne Haken weiß das Wiederherstellen nichts
    # über den Katalog und nimmt, was das Backup zuletzt bestimmte
    lauf.aufnahme = None
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    backup = next(tmp_path.rglob(".backup_*.json"))
    ergebnis = backup_wiederherstellen(backup)
    assert ergebnis is not None
    doc = _doc(ergebnis.pfad)
    assert doc["atmung"] == {"art": "spontan"}
    assert list(doc).index("atmung") == list(doc).index("datenqualitaet") + 1
    assert not list(tmp_path.rglob(".backup_*"))
