"""Eine ganze Messung mit dem Simulator: verbinden → live → aufnehmen → speichern → laden."""

from __future__ import annotations

import asyncio
import json

import pytest
from hrv_core.korrektur import anwenden, automatisch, kennzahlen
from hrv_core.recording import laden

from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.simulated import SIM_PPI, SIM_SYNTH, SimulatedSource


async def _messen(tmp_path, device_id: str, sekunden: float) -> tuple[Messlauf, object, list[bool]]:
    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    meldungen: list[bool] = []
    lauf.beobachter = meldungen.append
    await lauf.verbinden(device_id, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < sekunden:
        await asyncio.sleep(0.01)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    return lauf, ergebnis, meldungen


@pytest.mark.asyncio
async def test_messung_mit_simulator_h10(tmp_path) -> None:
    lauf, ergebnis, meldungen = await _messen(tmp_path, SIM_SYNTH, 120)

    assert lauf.status.verbindung == Verbindung.GETRENNT
    assert meldungen and meldungen[-1] is True  # Trennen meldet ein Layout-Ereignis
    assert ergebnis is not None
    # Simulation gehört nach Generator/, nie zwischen echte Messungen
    assert ergebnis.pfad.parent.name == "Generator"
    assert ergebnis.pfad.name.startswith("sensor_")
    assert len(ergebnis.sha1) == 40
    assert ergebnis.dauer_s >= 120

    rec = laden(ergebnis.pfad)
    assert len(rec.beats) > 100
    assert rec.simulation is True
    assert all(b.tw_src in ("m", "r") for b in rec.beats)
    doc = json.loads(ergebnis.pfad.read_text(encoding="utf-8"))
    assert doc["schema"] == "raw-v1" and doc["ppg_aufzeichnung"] is False

    k = lauf.live.kennzahlen()
    assert k.schlaege > 0 and k.rmssd_30s is not None
    # Synthetische Reihe ohne Artefakte: die Automatik findet nichts Gravierendes
    assert kennzahlen(anwenden(rec, [])) is not None
    assert all(kette.art == "interpolieren" for kette in automatisch(rec))
    # Kein Backup bleibt nach dem Speichern liegen
    assert not list(tmp_path.rglob(".backup_*"))


@pytest.mark.asyncio
async def test_messung_mit_simulator_ppi_schreibt_ppi_pakete(tmp_path) -> None:
    _, ergebnis, _ = await _messen(tmp_path, SIM_PPI, 90)
    assert ergebnis is not None
    doc = json.loads(ergebnis.pfad.read_text(encoding="utf-8"))
    assert doc["intervall_quelle"] == "ppg_ppi"
    assert doc["ppi_pakete"], "Verity-Rohpakete fehlen"
    assert set(doc["ppi_pakete"][0]) >= {"t_wall_s", "ppi_ms", "fehler_ms", "blocker", "kontakt"}


@pytest.mark.asyncio
async def test_stoppen_ohne_schlaege_speichert_nichts(tmp_path) -> None:
    quelle = SimulatedSource(tempo=1.0)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    lauf.aufnahme_starten()
    assert lauf.aufnahme_stoppen(tmp_path) is None
    await lauf.trennen()
    assert not list(tmp_path.rglob("sensor_*.json"))


@pytest.mark.asyncio
async def test_timer_abschnitte_entstehen_beim_speichern(tmp_path) -> None:
    """Der Timer markiert Abschnittsanfänge — beim Stoppen stehen sie als Abschnitte im Sidecar."""
    from hrv_core.ausschnitte import zusatz_lesen
    from hrv_core.korrektur import analyse_pfad

    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    marken = [(20, "Timer „T“: Belastung (Runde 1/2)", "Belastung (Runde 1/2)", False)]
    marken += [(50, "Pause (Runde 1/2)", "Pause (Runde 1/2)", False)]
    marken += [(80, "Belastung (Runde 2/2)", "Belastung (Runde 2/2)", False)]
    marken += [(110, "Timer fertig", "Timer fertig", True)]
    # Unter Last (CI) kommt die Abfrage spät — darum zählt die tatsächliche Zeit
    # der Marke, nicht die geplante Sekunde.
    gesetzt: list[float] = []
    for sekunde, text, name, ende in marken:
        while lauf.aufnahme_dauer_s() < sekunde:
            await asyncio.sleep(0.01)
        gesetzt.append(lauf.aufnahme_dauer_s())
        assert lauf.abschnitt_markieren(text, 0.0, name=name, ende=ende) is not None
    while lauf.aufnahme_dauer_s() < 130:
        await asyncio.sleep(0.01)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)

    assert ergebnis is not None and analyse_pfad(ergebnis.pfad).exists()
    rec = laden(ergebnis.pfad)
    assert len(rec.ereignisse) == 4  # die Notizen bleiben Notizen
    _, abschnitte = zusatz_lesen(ergebnis.pfad, float)
    assert [a.name for a in abschnitte] == [
        "Belastung (Runde 1/2)",
        "Pause (Runde 1/2)",
        "Belastung (Runde 2/2)",
    ]
    assert abschnitte[0].von_s == pytest.approx(gesetzt[0], abs=3)
    assert abschnitte[-1].bis_s == pytest.approx(gesetzt[3], abs=3)


# ---------------------------------------------------------------------------
# Crash-Backup wiederherstellen (Ben, 15.10.2026: Akku während 4 h leer, Messung weg)
# ---------------------------------------------------------------------------


async def _abgestuerzt(tmp_path, *, subject_id: str | None = "p1") -> tuple[Messlauf, object]:
    """Aufnahme mit Backup — und dann kein `aufnahme_stoppen` (Prozess-Tod)."""
    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path, subject_id=subject_id)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 10:
        await asyncio.sleep(0.01)
    lauf.abschnitt_markieren("Ruhe beginnt", name="Ruhe")
    while lauf.aufnahme_dauer_s() < 40:
        await asyncio.sleep(0.01)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    return lauf, task


async def test_backup_wiederherstellen_schreibt_messdatei_mit_profil_und_abschnitten(
    tmp_path,
) -> None:
    from hrv_core.ausschnitte import zusatz_lesen

    from trainingsapp.devices.messlauf import backup_wiederherstellen

    lauf, _ = await _abgestuerzt(tmp_path)
    backups = list(tmp_path.rglob(".backup_*.json"))
    assert len(backups) == 1 and backups[0].parent.name == "Generator"
    beats_im_speicher = len(lauf.aufnahme.beats)

    ergebnis = backup_wiederherstellen(backups[0])
    assert ergebnis is not None
    assert ergebnis.subject_id == "p1"
    assert ergebnis.pfad == backups[0].parent / f"sensor_{backups[0].name[8:-5]}.json"
    assert not backups[0].exists() and not list(tmp_path.rglob("*.tmp"))
    rec = laden(ergebnis.pfad)
    # Das Backup kam im 15-s-Takt: mindestens der Stand von vor ≤ 15 s
    assert 0 < len(rec.beats) <= beats_im_speicher
    assert rec.dauer_s >= 15 and ergebnis.dauer_s == rec.dauer_s
    assert len(ergebnis.sha1) == 40 and ergebnis.started_at == rec.start_utc
    assert rec.simulation is True
    assert "_wiederherstellung" not in json.loads(ergebnis.pfad.read_text(encoding="utf-8"))
    # Timer-Abschnitt aus dem Backup im Sidecar, Notiz in der Datei
    assert any("Ruhe" in str(e.get("text", "")) for e in rec.ereignisse)
    _, abschnitte = zusatz_lesen(ergebnis.pfad, float)
    assert any(t.name == "Ruhe" for t in abschnitte)


async def test_backup_ohne_zusatz_und_mit_vorhandener_messdatei(tmp_path) -> None:
    """Älteres Backup (kein `_wiederherstellung`): Profil unbekannt. Liegt die Messdatei
    schon da, bleibt sie Byte für Byte, das Backup geht trotzdem weg."""
    from hrv_core.aufnahme import backup_lesen

    from trainingsapp.devices.messlauf import backup_wiederherstellen

    await _abgestuerzt(tmp_path, subject_id=None)
    backup = next(tmp_path.rglob(".backup_*.json"))
    # Ein Backup von vor dem Journal (28.10.2026): die Schläge stehen im Kopf
    rec, _ = backup_lesen(backup)
    doc = rec.to_dict()
    backup.write_text(json.dumps(doc), encoding="utf-8")
    backup.with_name(backup.name + "l").unlink()

    ergebnis = backup_wiederherstellen(backup)
    assert ergebnis is not None and ergebnis.subject_id is None
    vorher = ergebnis.pfad.read_bytes()

    # Zweites Backup daneben, Messdatei existiert schon
    backup.write_text(json.dumps(doc), encoding="utf-8")
    nochmal = backup_wiederherstellen(backup)
    assert nochmal is not None and nochmal.pfad == ergebnis.pfad
    assert ergebnis.pfad.read_bytes() == vorher and not backup.exists()


def test_leeres_backup_wird_geloescht(tmp_path) -> None:
    from trainingsapp.devices.messlauf import backup_wiederherstellen

    leer = tmp_path / ".backup_2026-10-12_080000.json"
    leer.write_text(json.dumps({"schema": "raw-v1", "messungen": []}), encoding="utf-8")
    assert backup_wiederherstellen(leer) is None
    assert not leer.exists()


async def test_backup_jetzt_sichert_sofort(tmp_path) -> None:
    """Hintergrundwechsel: sofort sichern, nicht erst nach 15 s."""
    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path, subject_id="p1")
    lauf.backup_jetzt()  # ohne Aufnahme: nichts
    assert not list(tmp_path.rglob(".backup_*"))
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 3:
        await asyncio.sleep(0.01)
    lauf.backup_jetzt()
    backups = list(tmp_path.rglob(".backup_*.json"))
    assert len(backups) == 1
    doc = json.loads(backups[0].read_text(encoding="utf-8"))
    assert doc["_wiederherstellung"] == {"subject_id": "p1", "grenzen": []}
    journal = backups[0].with_name(backups[0].name + "l")  # die Schläge im Journal (28.10.)
    assert len(journal.read_text(encoding="utf-8").splitlines()) == len(lauf.aufnahme.beats)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


# ---------------------------------------------------------------------------
# Notizen vor der Aufnahme, leere Kurven beim Start (Ben, 16.10.2026)
# ---------------------------------------------------------------------------


async def test_notizen_vor_der_aufnahme_kommen_an_ihren_anfang(tmp_path) -> None:
    """Ohne Aufnahme gibt es einen Zeitbezug; beim Start rücken die Notizen auf 0."""
    from hrv_core.ereignisse import notiz

    lauf = Messlauf(SimulatedSource(tempo=60.0, seed=7), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    while lauf.jetzt_s() < 30:
        await asyncio.sleep(0.01)

    zb = lauf.notiz_zeitbezug()  # vor dem Start: Live-Achse, keine Schläge
    assert lauf.notiz_hinzufuegen("Timer ohne Aufnahme") is None  # der Timer schreibt nur in eine
    vorher = notiz("Kaffee getrunken", zb.anker(25.0), zb.start_utc, uebungen=["AB12CD34"])
    assert zb.x(vorher) == pytest.approx(25.0)
    lauf.ereignisse_setzen([vorher])
    assert lauf.ereignisse() == [vorher]
    assert lauf.aufnahme is None

    lauf.titel_notiz_setzen("Abendmessung", "Nach dem Training")  # auch das vorher (17.10.)
    lauf.aufnahme_starten()
    assert lauf.titel_notiz() == ("Abendmessung", "Nach dem Training")
    (e,) = lauf.ereignisse()
    assert e["text"] == "Kaffee getrunken" and e["uebungen"] == ["AB12CD34"]
    assert e["beat_index"] is None and e["t_wall_s"] == 0.0
    assert lauf.notiz_zeitbezug().x(e) == pytest.approx(0.0, abs=0.5)
    while lauf.aufnahme_dauer_s() < 10:
        await asyncio.sleep(0.01)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None
    rec = laden(ergebnis.pfad)
    assert [x["text"] for x in rec.ereignisse] == ["Kaffee getrunken"]
    assert (rec.titel, rec.notiz) == ("Abendmessung", "Nach dem Training")
    assert lauf.ereignisse() == []  # nach dem Stopp: die nächste Aufnahme beginnt leer
    assert lauf.titel_notiz() == ("", "")
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


async def test_aufnahme_beginnt_mit_leeren_kurven(tmp_path) -> None:
    """„Aufnahme starten" leert das Live-Fenster und setzt die Live-Achse auf 0."""
    lauf = Messlauf(SimulatedSource(tempo=60.0, seed=7), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    while lauf.jetzt_s() < 60:
        await asyncio.sleep(0.01)
    assert lauf.live.punkte()

    lauf.aufnahme_starten()
    assert lauf.jetzt_s() < 1.0
    assert all(p.t_s < 1.0 for p in lauf.live.punkte())  # höchstens ein Nachzügler
    while lauf.aufnahme_dauer_s() < 20:
        await asyncio.sleep(0.01)
    punkte = lauf.live.punkte()
    assert punkte and punkte[0].t_s < 3.0
    # Live-Achse und Aufnahme laufen gleich: eine Notiz „jetzt" steht an derselben Stelle
    e = lauf.notiz_hinzufuegen("jetzt")
    assert e is not None
    assert lauf.notiz_zeitbezug().x(e) == pytest.approx(lauf.jetzt_s(), abs=1.0)
    assert lauf.aufnahme_stoppen(tmp_path) is not None
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


# ---------------------------------------------------------------------------
# Spuren, Marken und gemeinsamer Start (Einheit, Ben 17.10.2026)
# ---------------------------------------------------------------------------


async def _laufend(tmp_path) -> tuple[Messlauf, asyncio.Task]:
    lauf = Messlauf(SimulatedSource(tempo=60.0, seed=7), backup_basis=tmp_path, subject_id="p1")
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    return lauf, task


async def _bis(lauf: Messlauf, sekunde: float) -> None:
    while lauf.aufnahme_dauer_s() < sekunde:
        await asyncio.sleep(0.01)


async def test_spuren_schneiden_einander_nicht(tmp_path) -> None:
    """Timer und Kilometer zugleich: Eine km-Grenze teilt keinen Timer-Abschnitt."""
    from hrv_core.ausschnitte import zusatz_lesen

    lauf, task = await _laufend(tmp_path)
    km = {"quelle": "gps", "art": "km", "spur": "km"}

    def bei(sekunde: float) -> float:
        # Die Grenze an die Stelle der Daten, nicht an die Uhr: Unter Last läuft die Uhr
        # des Simulators den Schlägen voraus (CI, 17.10.2026: „Belastung“ bei 30 statt 20 s)
        return lauf.start_mono + sekunde

    await _bis(lauf, 10)
    lauf.abschnitt_markieren("km 1", name="km 1", spur="km", als_notiz=False, bei=bei(10))
    await _bis(lauf, 20)
    lauf.abschnitt_markieren("Belastung", name="Belastung", bei=bei(20))
    await _bis(lauf, 50)
    lauf.abschnitt_markieren("km 1", name="km 2", spur="km", marke=km, bei=bei(50))
    await _bis(lauf, 80)
    lauf.abschnitt_markieren("Timer fertig", name="", ende=True, bei=bei(80))
    await _bis(lauf, 100)
    lauf.abschnitt_markieren("Ende", name="", ende=True, spur="km", als_notiz=False, bei=bei(100))
    await _bis(lauf, 110)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)

    assert ergebnis is not None
    rec = laden(ergebnis.pfad)
    # Stille Grenzen sind keine Notizen; die km-Notiz trägt ihre Marke
    assert [e["text"] for e in rec.ereignisse] == ["Belastung", "km 1", "Timer fertig"]
    assert rec.ereignisse[1]["marke"] == km
    _, teile = zusatz_lesen(ergebnis.pfad, float)
    spannen = {a.name: (a.von_s, a.bis_s) for a in teile}
    assert set(spannen) == {"km 1", "Belastung", "km 2"}
    # „km 2“ beginnt bei 50 s — die Belastung läuft trotzdem bis 80 s
    assert spannen["Belastung"] == (pytest.approx(20, abs=3), pytest.approx(80, abs=3))
    assert spannen["km 1"] == (pytest.approx(10, abs=3), pytest.approx(50, abs=3))
    assert spannen["km 2"][1] == pytest.approx(100, abs=3)


async def test_backup_traegt_alle_spuren(tmp_path) -> None:
    """Die Spur des Timers steht wie bisher unter ``grenzen``, die anderen unter ``spuren``."""
    from hrv_core.ausschnitte import zusatz_lesen

    from trainingsapp.devices.messlauf import backup_wiederherstellen

    lauf, task = await _laufend(tmp_path)
    await _bis(lauf, 10)
    lauf.abschnitt_markieren("Ruhe", name="Ruhe")
    lauf.abschnitt_markieren("km 1", name="km 1", spur="km", als_notiz=False)
    await _bis(lauf, 40)
    lauf.backup_jetzt()
    await lauf.trennen()
    await asyncio.wait_for(task, 5)

    backup = next(tmp_path.rglob(".backup_*.json"))
    zusatz = json.loads(backup.read_text(encoding="utf-8"))["_wiederherstellung"]
    assert [g[1] for g in zusatz["grenzen"]] == ["Ruhe"]
    assert [g[1] for g in zusatz["spuren"]["km"]] == ["km 1"]
    ergebnis = backup_wiederherstellen(backup)
    assert ergebnis is not None
    _, teile = zusatz_lesen(ergebnis.pfad, float)
    assert {a.name for a in teile} == {"Ruhe", "km 1"}


async def test_aufnahme_mit_vorgegebenem_nullpunkt_und_dateiname(tmp_path) -> None:
    """Eine Einheit gibt Nullpunkt und Wanduhr vor; der Dateiname steht schon beim Start fest;
    Notizen kommen an eine genaue Stelle (``bei``), nie in die Zukunft."""
    from datetime import UTC, datetime

    lauf = Messlauf(SimulatedSource(tempo=60.0, seed=7), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    assert lauf.datei_relativ() is None
    t0 = lauf.uhr() - 3.0  # Vorlauf: der Countdown begann 3 s vor dem Start
    utc = datetime(2026, 10, 17, 8, 0, 0, 500000, tzinfo=UTC)
    lauf.aufnahme_starten(start_mono=t0, start_utc=utc)
    assert lauf.aufnahme is not None and lauf.aufnahme.start_mono == t0
    assert lauf.aufnahme.start_utc == utc and lauf.jetzt_s() >= 3.0
    datei = lauf.datei_relativ()
    # Zeitstempel im Namen: Ortszeit des Starts (kompatibilitaet.md §2, seit 13.11.2026) —
    # in Berlin 10:00 Uhr, auf der CI (UTC) 08:00 Uhr
    assert datei == f"Generator/sensor_{utc.astimezone():%Y-%m-%d_%H%M%S}.json"
    await _bis(lauf, 20)
    marke = {"quelle": "timer", "art": "abschnitt", "spur": "timer"}
    e = lauf.notiz_hinzufuegen("genau", bei=t0 + 10.0, marke=marke)
    assert e is not None and e["t_wall_s"] == pytest.approx(10.0, abs=1.0)
    assert e["marke"] == marke
    spaeter = lauf.notiz_hinzufuegen("später", bei=lauf.uhr() + 100.0)
    # Gedeckelt auf „jetzt“ (die Live-Achse), nicht auf den letzten Schlag: Der Simulator
    # läuft 60-fach, auf einem langsamen Runner liegen zwischen beiden ein paar Sekunden
    assert spaeter is not None and spaeter["t_wall_s"] <= lauf.aufnahme_dauer_s() + 5.0
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None
    assert ergebnis.pfad.relative_to(tmp_path / "Messungen").as_posix() == datei
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


@pytest.mark.asyncio
async def test_stoppen_bei_schreibfehler_behaelt_die_aufnahme(tmp_path, monkeypatch) -> None:
    """H24: Scheitert das Speichern, bleibt die Aufnahme im Lauf — ein zweiter Versuch
    (oder das Backup) rettet sie; vorher war sie in dem Moment weg."""
    from hrv_core.aufnahme import Aufnahme

    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 10:
        await asyncio.sleep(0.01)
    original = Aufnahme.speichern

    def kaputt(self, ordner):
        raise OSError("Speicher voll")

    monkeypatch.setattr(Aufnahme, "speichern", kaputt)
    with pytest.raises(OSError):
        lauf.aufnahme_stoppen(tmp_path)
    assert lauf.aufnahme is not None and lauf.aufnahme.beats
    monkeypatch.setattr(Aufnahme, "speichern", original)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None and lauf.aufnahme is None
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


@pytest.mark.asyncio
async def test_kaputte_wiedergabedatei_beendet_den_strom(tmp_path) -> None:
    """H36: Ein Fehler im Simulator-Task endet mit Status und Ende-Signal, nicht still."""
    datei = tmp_path / "sensor_kaputt.json"
    datei.write_text("{nix", encoding="utf-8")
    quelle = SimulatedSource(datei, tempo=60.0)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden("datei", None)
    await asyncio.wait_for(lauf.laufen(), 5)
    assert lauf.status.verbindung == Verbindung.GETRENNT
    assert "abgebrochen" in (lauf.status.meldung or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("device_id", "name", "geraet", "adresse"),
    [
        ("E2:B4:CC:3F:08:44", None, "Unbekannt", "E2:B4:CC:3F:08:44"),
        # H51: „Zuletzt verbunden“ reicht die Adresse als Namen herein
        ("E2:B4:CC:3F:08:44", "E2:B4:CC:3F:08:44", "Unbekannt", "E2:B4:CC:3F:08:44"),
        ("E2:B4:CC:3F:08:44", "TICKR 1A2B", "TICKR 1A2B", "E2:B4:CC:3F:08:44"),
        (SIM_SYNTH, None, "Unbekannt", None),
    ],
)
async def test_name_und_adresse_stehen_getrennt_in_der_messdatei(
    tmp_path, device_id, name, geraet, adresse
) -> None:
    """Ein Gurt ohne Bluetooth-Namen trägt nie die Adresse als Namen (Ben, 19.10.2026):
    `geraet` = Unbekannt, die Adresse im eigenen Feld — bei Simulation gar nicht."""
    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(device_id, name)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 3:
        await asyncio.sleep(0.01)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None
    doc = json.loads(ergebnis.pfad.read_text(encoding="utf-8"))
    assert doc["geraet"] == geraet
    assert doc.get("adresse") == adresse
    assert lauf.geraet_name == (name or device_id)  # Anzeige behält den Notnagel


@pytest.mark.asyncio
async def test_stoppen_im_thread_nimmt_keine_schlaege_mehr_auf(tmp_path, monkeypatch) -> None:
    """H39: `aufnahme_stoppen_async` schreibt die Messdatei in einem Thread. Derweil
    läuft die Live-Anzeige weiter, aber kein Schlag kommt mehr in die Aufnahme, sie bleibt
    bis zum fertigen Schreiben im Lauf (H24), und ein zweiter Stopp speichert nichts
    doppelt. Ein Schreibfehler lässt sie wie bei `aufnahme_stoppen` im Lauf."""
    import threading

    from hrv_core.aufnahme import Aufnahme

    quelle = SimulatedSource(tempo=60.0, seed=7)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 10:
        await asyncio.sleep(0.01)
    aufnahme = lauf.aufnahme
    assert aufnahme is not None
    original = Aufnahme.speichern
    weiter = threading.Event()
    gesehen: dict[str, object] = {}

    def langsam(self, ordner):
        gesehen["schlaege"] = len(self.beats)
        gesehen["im_thread"] = threading.current_thread() is not threading.main_thread()
        weiter.wait(5)  # der Loop empfängt derweil weiter
        return original(self, ordner)

    monkeypatch.setattr(Aufnahme, "speichern", langsam)
    stopp = asyncio.create_task(lauf.aufnahme_stoppen_async(tmp_path))
    while "schlaege" not in gesehen:
        await asyncio.sleep(0.005)
    n = gesehen["schlaege"]
    live_vorher = lauf.live.kennzahlen().schlaege
    for _ in range(20):
        await asyncio.sleep(0.01)
    assert lauf.aufnahme is aufnahme and len(aufnahme.beats) == n  # nichts mehr hinein
    assert lauf.live.kennzahlen().schlaege > live_vorher  # die Anzeige läuft weiter
    assert await lauf.aufnahme_stoppen_async(tmp_path) is None  # ein zweiter Stopp
    assert lauf.aufnahme_stoppen(tmp_path) is None
    assert lauf.aufnahme is aufnahme
    weiter.set()
    ergebnis = await stopp
    assert ergebnis is not None and lauf.aufnahme is None and gesehen["im_thread"] is True
    assert len(laden(ergebnis.pfad).beats) == n
    assert not list(tmp_path.rglob(".backup_*"))

    # Schreibfehler: die Aufnahme bleibt im Lauf und nimmt wieder auf (H24)
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 5:
        await asyncio.sleep(0.01)

    def kaputt(self, ordner):
        raise OSError("Speicher voll")

    monkeypatch.setattr(Aufnahme, "speichern", kaputt)
    with pytest.raises(OSError):
        await lauf.aufnahme_stoppen_async(tmp_path)
    zweite = lauf.aufnahme
    assert zweite is not None and zweite.beats
    m = len(zweite.beats)
    for _ in range(20):
        await asyncio.sleep(0.01)
    assert len(zweite.beats) > m  # nicht mehr gesperrt
    monkeypatch.setattr(Aufnahme, "speichern", original)
    assert await lauf.aufnahme_stoppen_async(tmp_path) is not None and lauf.aufnahme is None
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


@pytest.mark.asyncio
async def test_puffer_laenge_aus_der_einstellung(tmp_path) -> None:
    """Der Live-Puffer ist so lang wie eingestellt (Ben, 26.10.2026) — auch nach dem
    Verbinden, das den Puffer neu anlegt; ohne Angabe gilt die Vorgabe von hrv-core."""
    from hrv_core.constants import LIVE_FENSTER_S

    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path, puffer_s=7200)
    assert lauf.live.max_s == 7200.0
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    assert lauf.live.max_s == 7200.0
    await lauf.trennen()
    assert Messlauf(SimulatedSource(), backup_basis=tmp_path).live.max_s == LIVE_FENSTER_S


async def test_eigener_abschnitt_live_als_notizpaar(tmp_path) -> None:
    """Ben, 27.10.2026: „Abschnitt: Start“ / „… Ende“ sind zwei Grenz-Notizen mit derselben
    Kennung als Spur; die Live-Liste kennt den laufenden, das Sidecar bekommt ihn beim
    Speichern mit Kennung und Rändern — auch wenn die Notizen danach verschoben wurden."""
    import json

    from hrv_core.ausschnitte import zusatz_lesen
    from hrv_core.korrektur import analyse_pfad

    from trainingsapp.core import abschnitte

    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    assert lauf.abschnitt_starten("Behandlung") is None  # ohne Aufnahme keine Grenze
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 12:
        await asyncio.sleep(0.01)
    kennung = lauf.abschnitt_starten("Behandlung", kopf_s=-2, endteil_s=3)
    assert kennung is not None and lauf.offener_abschnitt() == (kennung, "Behandlung")
    while lauf.aufnahme_dauer_s() < 30:
        await asyncio.sleep(0.01)
    (laufend,) = [a for a in lauf.abschnitte() if a.id == kennung]
    assert laufend.name == "Behandlung" and laufend.bis_s == pytest.approx(lauf.jetzt_s(), abs=1)
    # Ein zweiter Start beendet den ersten
    zweite = lauf.abschnitt_starten("Ruhe")
    assert zweite != kennung and lauf.offener_abschnitt() == (zweite, "Ruhe")
    while lauf.aufnahme_dauer_s() < 45:
        await asyncio.sleep(0.01)
    assert lauf.abschnitt_beenden() and lauf.offener_abschnitt() is None
    assert not lauf.abschnitt_beenden()
    texte = [e["text"] for e in lauf.ereignisse()]
    assert texte == [
        "Behandlung: Start (Kopf −0:02 · Endteil +0:03)",
        "Behandlung: Ende",
        "Ruhe: Start",
        "Ruhe: Ende",
    ]
    assert abschnitte.kennung_von(lauf.ereignisse()[0]) == kennung
    assert lauf.ereignisse()[0]["marke"]["kopf_s"] == -2
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None
    _, teile = zusatz_lesen(ergebnis.pfad, float)
    assert [(a.id, a.name, a.kopf_s, a.endteil_s) for a in teile] == [
        (kennung, "Behandlung", -2, 3),
        (zweite, "Ruhe", 0, 0),
    ]
    assert teile[0].bis_s == pytest.approx(teile[1].von_s, abs=0.5)
    doc = json.loads(analyse_pfad(ergebnis.pfad).read_text())
    assert doc["segments"][0]["rand"] == {"kopf_s": -2, "endteil_s": 3}


async def test_teil_speichern_und_weiter_dann_zusammenfuegen(tmp_path) -> None:
    """„Teil speichern & weiter“ (Ben, 28.10.2026): Teil 1 wird Messdatei, die Aufnahme läuft
    ohne Lücke weiter; Backup-Kopf und -Journal von Teil 1 sind weg; `zusammenfuegen` macht
    aus beiden Teilen eine Messung mit durchlaufender Herzuhr."""
    from hrv_core.recording import laden
    from hrv_core.zusammenfuegen import zusammenfuegen

    lauf, task = await _laufend(tmp_path)
    lauf.titel_notiz_setzen("Nacht", "")
    lauf.abschnitt_markieren("Ruhe beginnt", name="Ruhe")
    await _bis(lauf, 10)
    lauf.backup_jetzt()
    assert list(tmp_path.rglob(".backup_*.jsonl"))
    alt = lauf.aufnahme
    teil1 = await lauf.aufnahme_teilen_async(tmp_path)
    assert teil1 is not None and teil1.pfad.exists()
    assert lauf.aufnahme is not None and lauf.aufnahme is not alt
    assert lauf.aufnahme.titel == "Nacht"
    # Die neue zählt von vorn: ihre Uhr beginnt beim Teilen, nicht beim Start von Teil 1.
    # Nicht an ihrer Dauer prüfen — während Teil 1 im Thread geschrieben wird, laufen die
    # Schläge des 60-fach schnellen Simulators schon in die neue (CI, 4.11.2026: 6,1 s).
    assert lauf.aufnahme.start_mono >= alt.start_mono + 10
    assert not list(tmp_path.rglob(".backup_*"))  # Kopf und Journal von Teil 1 sind weg
    await _bis(lauf, 5)
    assert lauf.aufnahme.beats  # der Strom läuft in die neue
    teil2 = await lauf.aufnahme_stoppen_async(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert teil2 is not None and teil2.pfad != teil1.pfad
    a, b = laden(teil1.pfad), laden(teil2.pfad)
    assert a.titel == "Nacht" and b.titel == "Nacht"
    assert any(e.get("text") == "Ruhe beginnt" for e in a.ereignisse) and not b.ereignisse
    ganz = zusammenfuegen([a, b])
    assert len(ganz.beats) == len(a.beats) + len(b.beats)
    herz = [x.t_s for x in ganz.beats]
    assert herz == sorted(herz)  # die Herzuhr läuft durch; die Wanduhr der Naht prüft hrv-core
    assert [e["text"] for e in ganz.ereignisse][-1] == "Teil 2"


# ---------------------------------------------------------------------------
# EKG-Rohsignal mitschreiben (Ben, 30.10.2026)
# ---------------------------------------------------------------------------


async def test_ekg_wird_als_beiwerk_mitgeschrieben(tmp_path) -> None:
    """Mit eingeschaltetem EKG schreibt der Messlauf die Rahmen als ``_ecg.json`` neben die
    Messdatei, die Messdatei trägt ``ecg_aufzeichnung``; gerechnet wird damit nichts."""
    from hrv_core.ekg import ekg_laden, ekg_pfad

    quelle = SimulatedSource(tempo=60.0, seed=7, ekg=True)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 20:
        await asyncio.sleep(0.01)
    lauf.backup_jetzt()
    journal = next(tmp_path.rglob(".backup_*_ecg.jsonl"))
    assert journal.read_text(encoding="utf-8").startswith('["k", 130')
    while lauf.aufnahme_dauer_s() < 40:
        await asyncio.sleep(0.01)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None
    doc = json.loads(ergebnis.pfad.read_text(encoding="utf-8"))
    assert doc["ecg_aufzeichnung"] is True
    beiwerk = ekg_pfad(ergebnis.pfad)
    assert beiwerk.exists() and not journal.exists() and not list(tmp_path.rglob(".backup_*"))
    e = ekg_laden(beiwerk)
    assert (
        e.rate_hz == 130 and e.n > 130 * 30 and len(e.frame_sample_counts) == len(doc["messungen"])
    )
    assert e.gaps == [] and abs(e.dauer_s - e.n / 130) < 0.1
    assert e.t_wall_start_s is not None and -1.0 < e.t_wall_start_s < 2.0
    # Die Messdatei selbst bleibt, wie sie ist (keine Proben darin), das Diagnoseprotokoll
    # nennt das EKG nicht (der Simulator führt keins) — das Beiwerk ist eigenständig lesbar
    assert "uv" not in doc


async def test_ekg_journal_wird_beim_wiederherstellen_zum_beiwerk(tmp_path) -> None:
    from hrv_core.ekg import ekg_laden, ekg_pfad

    from trainingsapp.devices.messlauf import backup_wiederherstellen

    quelle = SimulatedSource(tempo=60.0, seed=3, ekg=True)
    lauf = Messlauf(quelle, backup_basis=tmp_path, subject_id="p1")
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 15:
        await asyncio.sleep(0.01)
    lauf.backup_jetzt()
    n_rahmen = lauf.ekg.n_rahmen
    # „Absturz“: die App ist weg, nur Kopf, Journal und EKG-Journal liegen da
    lauf.aufnahme = None
    lauf.ekg = None
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    backup = next(tmp_path.rglob(".backup_*.json"))
    ergebnis = backup_wiederherstellen(backup)
    assert ergebnis is not None
    e = ekg_laden(ekg_pfad(ergebnis.pfad))
    assert e.n > 0 and len(e.frame_sample_counts) == n_rahmen
    assert not list(tmp_path.rglob(".backup_*"))


async def test_teil_speichern_nimmt_das_ekg_mit(tmp_path) -> None:
    """„Teil speichern & weiter“ mit EKG (V4, `docs/plan_diagnosemodus.md`): Teil 1 bekommt
    sein ``_ecg.json``, Teil 2 ein eigenes mit eigenem Journal und ``ecg_aufzeichnung``; kein
    Journal von Teil 1 bleibt liegen."""
    from hrv_core.ekg import ekg_laden, ekg_pfad

    quelle = SimulatedSource(tempo=60.0, seed=5, ekg=True)
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    await _bis(lauf, 15)
    lauf.backup_jetzt()
    assert list(tmp_path.rglob(".backup_*_ecg.jsonl"))
    alt = lauf.aufnahme
    teil1 = await lauf.aufnahme_teilen_async(tmp_path)
    neu = lauf.aufnahme
    assert teil1 is not None and alt is not None and neu is not None
    assert not list(tmp_path.rglob(".backup_*"))  # auch das EKG-Journal von Teil 1 ist weg
    await _bis(lauf, 15)
    lauf.backup_jetzt()
    journal2 = next(tmp_path.rglob(".backup_*_ecg.jsonl"))
    assert journal2.read_text(encoding="utf-8").startswith('["k", 130')  # eigener Kopf
    teil2 = await lauf.aufnahme_stoppen_async(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert teil2 is not None and teil2.pfad != teil1.pfad
    e1, e2 = ekg_laden(ekg_pfad(teil1.pfad)), ekg_laden(ekg_pfad(teil2.pfad))
    assert e1.n > 130 * 10 and e2.n > 130 * 10
    # Teil 2 rechnet ab seinem eigenen Start und schließt ohne Lücke an Teil 1 an. Geprüft an
    # der Naht, nicht am Wert allein: Hängt die Verarbeitung hinterher, kommen Rahmen von vor
    # dem Teilen erst danach an und beginnen Teil 2 mit negativer Zeit — beim 60-fachen
    # Simulator auf einem langsamen Runner um 20 s (CI, 4.11.2026: −19,8). Bezöge sich Teil 2
    # auf Teil 1, läge die Naht um die Dauer von Teil 1 (≥ 15 s) daneben.
    assert e1.t_wall_start_s is not None and e2.t_wall_start_s is not None
    ende1 = e1.t_wall_start_s + e1.n / e1.rate_hz
    anfang2 = (neu.start_mono - alt.start_mono) + e2.t_wall_start_s
    assert abs(anfang2 - ende1) < 0.5
    for teil in (teil1, teil2):
        assert json.loads(teil.pfad.read_text(encoding="utf-8"))["ecg_aufzeichnung"] is True
    assert not list(tmp_path.rglob(".backup_*"))


async def test_ohne_einstellung_kein_ekg(tmp_path) -> None:
    from hrv_core.ekg import ekg_pfad

    _, ergebnis, _ = await _messen(tmp_path, SIM_SYNTH, 10)
    assert ergebnis is not None and not ekg_pfad(ergebnis.pfad).exists()
    assert json.loads(ergebnis.pfad.read_text(encoding="utf-8"))["ecg_aufzeichnung"] is False


# ---------------------------------------------------------------------------
# Atemphasen als Beiwerk ``_atem.json`` (Ben, 5.11.2026, docs/kompatibilitaet.md §15)
# ---------------------------------------------------------------------------


async def test_atemphasen_werden_als_beiwerk_mitgeschrieben(tmp_path) -> None:
    """Was eine Einheit über `atem_sammler` und die Hüllen meldet, steht nach dem Speichern
    als ``_atem.json`` neben der Messdatei — Läufe, Phasen und Fenster auf der Wanduhr der
    Aufnahme (``t − start_mono``), das Journal nach `backup_jetzt` daneben, nach dem
    Speichern weg; die Messdatei bleibt, wie sie ist."""
    from hrv_core.atem import atem_laden, atem_pfad
    from hrv_core.recording import ist_messdatei

    from trainingsapp.core.hrv_export import diagnose_pfad

    quelle = SimulatedSource(tempo=60.0, seed=7)
    quelle.protokoll = ["08:15:00 Verbunden"]  # type: ignore[attr-defined]
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    aufnahme = lauf.aufnahme
    assert aufnahme is not None
    start = aufnahme.start_mono
    sammler = lauf.atem_sammler(geraet="polar_h10", rate_hz=50)
    assert sammler is not None and lauf.atem is sammler
    assert lauf.atem_sammler(geraet="x", rate_hz=25) is sammler  # einmal je Aufnahme
    # Zeiten auf der Uhr der Quelle — der Messlauf rechnet sie auf die Wanduhr um
    lauf.atem_lauf_beginn(start + 5.0)
    lauf.atem_phase(start + 6.0, "ein")
    lauf.atem_phase(start + 8.5004, "aus")
    lauf.atem_fenster(start + 35.0, 6.0, True)
    lauf.atem_fenster(start + 40.0, None, False, "bewegung")
    await _bis(lauf, 20)
    lauf.backup_jetzt()
    journal = next(tmp_path.rglob(".backup_*_atem.jsonl"))
    zeilen = journal.read_text(encoding="utf-8").splitlines()
    assert json.loads(zeilen[0])[0] == "k" and json.loads(zeilen[0])[1]["schema"] == "atem-v1"
    assert json.loads(zeilen[1]) == ["e", 5.0]
    lauf.atem_lauf_ende(start + 42.0)
    await _bis(lauf, 45)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None and lauf.atem is None
    beiwerk = atem_pfad(ergebnis.pfad)
    assert beiwerk.exists() and not journal.exists() and not list(tmp_path.rglob(".backup_*"))
    assert not ist_messdatei(beiwerk)
    a = atem_laden(beiwerk)
    assert (a.quelle, a.geraet, a.rate_hz, a.art) == ("sensor", "polar_h10", 50, "prototyp")
    assert a.prototyp == "hrv_core.prototyp.atemzuege"
    assert a.erfasst == [(5.0, 42.0)]
    assert a.phasen == [(6.0, "ein"), (8.5, "aus")]
    assert a.fenster == [(35.0, 6.0, True, ""), (40.0, None, False, "bewegung")]
    doc = json.loads(ergebnis.pfad.read_text(encoding="utf-8"))
    assert "phasen" not in doc and "atem" not in doc and "erfasst" not in doc
    text = diagnose_pfad(ergebnis.pfad).read_text(encoding="utf-8")
    assert "Atmung: 2 Phasen, 2 Fenster in 1 Läufen (hrv_core.prototyp.atemzuege)" in text


async def test_atem_journal_wird_beim_wiederherstellen_zum_beiwerk(tmp_path) -> None:
    """Nach einem Absturz macht `backup_wiederherstellen` aus dem Atem-Journal das Beiwerk;
    ein offener Lauf endet mit dem letzten bekannten Zeitpunkt."""
    from hrv_core.atem import atem_laden, atem_pfad

    from trainingsapp.devices.messlauf import backup_wiederherstellen

    lauf, task = await _laufend(tmp_path)
    assert lauf.aufnahme is not None
    start = lauf.aufnahme.start_mono
    assert lauf.atem_sammler(geraet="polar_h10", rate_hz=50) is not None
    lauf.atem_lauf_beginn(start + 2.0)
    lauf.atem_phase(start + 3.0, "ein")
    lauf.atem_fenster(start + 12.0, 7.5, True)
    await _bis(lauf, 15)
    lauf.backup_jetzt()
    assert list(tmp_path.rglob(".backup_*_atem.jsonl"))
    # „Absturz“: die App ist weg, nur Kopf, Journal und Atem-Journal liegen da
    lauf.aufnahme = None
    lauf.atem = None
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    backup = next(tmp_path.rglob(".backup_*.json"))
    ergebnis = backup_wiederherstellen(backup)
    assert ergebnis is not None
    a = atem_laden(atem_pfad(ergebnis.pfad))
    assert a.geraet == "polar_h10" and a.rate_hz == 50
    assert a.erfasst == [(2.0, 12.0)] and a.phasen == [(3.0, "ein")]
    assert a.fenster == [(12.0, 7.5, True, "")]
    assert not list(tmp_path.rglob(".backup_*"))


async def test_teil_speichern_nimmt_die_atemphasen_mit(tmp_path) -> None:
    """„Teil speichern & weiter“: Teil 1 bekommt sein ``_atem.json`` mit dem an der Naht
    geschlossenen Lauf, Teil 2 beginnt den Lauf bei 0 neu und zählt ab seinem Start."""
    from hrv_core.atem import atem_laden, atem_pfad

    lauf, task = await _laufend(tmp_path)
    alt = lauf.aufnahme
    assert alt is not None
    assert lauf.atem_sammler(geraet="polar_h10", rate_hz=50) is not None
    lauf.atem_lauf_beginn(alt.start_mono + 5.0)
    lauf.atem_phase(alt.start_mono + 7.0, "ein")
    await _bis(lauf, 15)
    lauf.backup_jetzt()
    assert list(tmp_path.rglob(".backup_*_atem.jsonl"))
    teil1 = await lauf.aufnahme_teilen_async(tmp_path)
    neu = lauf.aufnahme
    assert teil1 is not None and neu is not None and neu is not alt
    assert not list(tmp_path.rglob(".backup_*"))  # auch das Atem-Journal von Teil 1 ist weg
    naht = round(neu.start_mono - alt.start_mono, 3)
    a1 = atem_laden(atem_pfad(teil1.pfad))
    assert a1.erfasst == [(5.0, naht)] and a1.phasen == [(7.0, "ein")]
    # Teil 2: derselbe Lauf, neu begonnen bei 0 — mit Gerät und Rate von Teil 1
    sammler2 = lauf.atem
    assert sammler2 is not None and sammler2.offen and sammler2.laeufe == [[0.0, None]]
    assert sammler2.geraet == "polar_h10" and sammler2.rate_hz == 50 and not sammler2.phasen
    lauf.atem_phase(neu.start_mono + 3.0, "aus")
    lauf.atem_lauf_ende(neu.start_mono + 8.0)
    await _bis(lauf, 10)
    teil2 = await lauf.aufnahme_stoppen_async(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert teil2 is not None and teil2.pfad != teil1.pfad
    a2 = atem_laden(atem_pfad(teil2.pfad))
    assert a2.erfasst == [(0.0, 8.0)] and a2.phasen == [(3.0, "aus")]
    assert not list(tmp_path.rglob(".backup_*"))


async def test_teil_speichern_ohne_offenen_atem_lauf_beginnt_keinen(tmp_path) -> None:
    """Ist der Lauf vor dem Teilen zu, hat Teil 2 keinen Sammler — und kein Beiwerk."""
    from hrv_core.atem import atem_pfad

    lauf, task = await _laufend(tmp_path)
    alt = lauf.aufnahme
    assert alt is not None
    assert lauf.atem_sammler(geraet="polar_h10", rate_hz=50) is not None
    lauf.atem_lauf_beginn(alt.start_mono + 1.0)
    lauf.atem_lauf_ende(alt.start_mono + 9.0)
    await _bis(lauf, 12)
    teil1 = await lauf.aufnahme_teilen_async(tmp_path)
    neu = lauf.aufnahme
    assert teil1 is not None and neu is not None
    assert atem_pfad(teil1.pfad).exists() and lauf.atem is None
    lauf.atem_phase(neu.start_mono + 1.0, "ein")  # ohne Sammler: nichts
    await _bis(lauf, 8)
    teil2 = await lauf.aufnahme_stoppen_async(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert teil2 is not None and not atem_pfad(teil2.pfad).exists()


async def test_ohne_aufnahme_keine_atemphasen(tmp_path) -> None:
    """Läuft keine Aufnahme, gibt es keinen Sammler und kein Beiwerk — die Hüllen tun
    nichts und werfen nichts (Plan §4.1)."""
    from hrv_core.atem import atem_pfad

    lauf = Messlauf(SimulatedSource(tempo=60.0, seed=7), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    assert lauf.atem_sammler(geraet="polar_h10", rate_hz=50) is None
    t = lauf.start_mono + 1.0
    lauf.atem_lauf_beginn(t)
    lauf.atem_phase(t + 1.0, "ein")
    lauf.atem_fenster(t + 30.0, 6.0, True)
    lauf.atem_lauf_ende(t + 40.0)
    assert lauf.atem is None
    lauf.aufnahme_starten()
    await _bis(lauf, 10)
    assert lauf.atem is None  # nichts von vorher wandert in die Aufnahme
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None and not atem_pfad(ergebnis.pfad).exists()
    assert not list(tmp_path.rglob("*_atem.*"))


async def test_leerer_atem_sammler_schreibt_nichts(tmp_path) -> None:
    """Ein angelegter Sammler ohne Lauf, Phase und Fenster: kein Journal, kein Beiwerk —
    und eine Aufnahme ohne Schlag nimmt ihren Sammler mit ins Nichts."""
    from hrv_core.atem import atem_pfad

    lauf, task = await _laufend(tmp_path)
    assert lauf.atem_sammler(geraet="polar_h10", rate_hz=50) is not None
    await _bis(lauf, 20)
    lauf.backup_jetzt()
    assert list(tmp_path.rglob(".backup_*.json")) and not list(tmp_path.rglob("*_atem.jsonl"))
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None and not atem_pfad(ergebnis.pfad).exists()
    assert not list(tmp_path.rglob("*_atem.*")) and not list(tmp_path.rglob(".backup_*"))
    # Ohne einen einzigen Schlag wird nichts gespeichert — auch keine Atemphasen
    leer = Messlauf(SimulatedSource(tempo=1.0), backup_basis=tmp_path)
    await leer.verbinden(SIM_SYNTH, None)
    leer.aufnahme_starten()
    assert leer.atem_sammler(geraet="polar_h10", rate_hz=50) is not None
    leer.atem_lauf_beginn(leer.start_mono + 1.0)
    assert leer.aufnahme_stoppen(tmp_path) is None and leer.atem is None
    await leer.trennen()
    assert not list(tmp_path.rglob("*_atem.*"))


async def test_aufnahme_waehrend_laufender_atem_spur_bekommt_beiwerk(tmp_path) -> None:
    """Fünfte Prüfrunde, B1: Beginnt die Aufnahme erst, nachdem „Atmung erfassen“ lief, oder
    folgt eine zweite Aufnahme, bekommt jede ihren Sammler mit einem Lauf ab ihrem Start —
    die Spur war die ganze Zeit an (`Messlauf.atem_aktiv`), nur das Beiwerk fehlte."""
    from hrv_core.atem import atem_laden, atem_pfad

    lauf = Messlauf(SimulatedSource(tempo=60.0, seed=7), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, None)
    task = asyncio.create_task(lauf.laufen())
    # Die Spur beginnt ohne Aufnahme: kein Sammler, aber gemerkt
    assert lauf.atem_sammler(geraet="polar_h10", rate_hz=50) is None
    lauf.atem_lauf_beginn(lauf.start_mono + 1.0)
    lauf.atem_phase(lauf.start_mono + 2.0, "ein")
    assert lauf.atem is None and lauf.atem_aktiv
    lauf.aufnahme_starten()
    aufnahme = lauf.aufnahme
    assert aufnahme is not None
    start = aufnahme.start_mono
    assert lauf.atem is not None and lauf.atem.offen and lauf.atem.laeufe == [[0.0, None]]
    assert lauf.atem.geraet == "polar_h10" and lauf.atem.rate_hz == 50
    lauf.atem_phase(start + 3.0, "aus")
    lauf.atem_fenster(start + 30.0, 6.0, True)
    await _bis(lauf, 35)
    erste = lauf.aufnahme_stoppen(tmp_path)
    assert erste is not None
    a1 = atem_laden(atem_pfad(erste.pfad))
    assert a1.phasen == [(3.0, "aus")] and a1.fenster == [(30.0, 6.0, True, "")]
    assert len(a1.erfasst) == 1 and a1.erfasst[0][0] == 0.0 and a1.erfasst[0][1] >= 35.0
    # Die Spur läuft weiter — die zweite Aufnahme bekommt wieder einen Lauf ab 0
    assert lauf.atem is None and lauf.atem_aktiv
    lauf.aufnahme_starten()
    aufnahme2 = lauf.aufnahme
    assert aufnahme2 is not None and lauf.atem is not None and lauf.atem.laeufe == [[0.0, None]]
    lauf.atem_phase(aufnahme2.start_mono + 4.0, "ein")
    lauf.atem_lauf_ende(aufnahme2.start_mono + 9.0)
    assert not lauf.atem_aktiv and not lauf.atem.offen
    await _bis(lauf, 12)
    zweite = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert zweite is not None and zweite.pfad != erste.pfad
    a2 = atem_laden(atem_pfad(zweite.pfad))
    assert a2.erfasst == [(0.0, 9.0)] and a2.phasen == [(4.0, "ein")]
    # Ohne laufende Spur legt eine Aufnahme keinen Sammler an; ein Lauf, der während der
    # Aufnahme beginnt, beginnt an seiner Stelle — nicht bei 0
    lauf2 = Messlauf(SimulatedSource(tempo=60.0, seed=7), backup_basis=tmp_path)
    await lauf2.verbinden(SIM_SYNTH, None)
    task2 = asyncio.create_task(lauf2.laufen())
    lauf2.aufnahme_starten()
    assert lauf2.atem is None
    assert lauf2.atem_sammler(geraet="polar_h10", rate_hz=50) is not None
    assert lauf2.aufnahme is not None
    lauf2.atem_lauf_beginn(lauf2.aufnahme.start_mono + 5.0)
    assert lauf2.atem is not None and lauf2.atem.laeufe == [[5.0, None]]
    await lauf2.trennen()
    await asyncio.wait_for(task2, 5)


async def test_phasen_von_vor_dem_aufnahmestart_fallen_weg(tmp_path) -> None:
    """Fünfte Prüfrunde, B2: Beim Teilen liegt der Ansatz einer Phase vor der Naht, bestätigt
    wird sie danach — sie gehört nicht in Teil 2 und bekommt dort keine negative Zeit; ebenso
    ein Fenster, das vor dem Start endete. Lauf-Grenzen von davor liegen bei 0."""
    from hrv_core.atem import atem_laden, atem_pfad

    lauf, task = await _laufend(tmp_path)
    alt = lauf.aufnahme
    assert alt is not None
    assert lauf.atem_sammler(geraet="polar_h10", rate_hz=50) is not None
    lauf.atem_lauf_beginn(alt.start_mono - 2.0)  # von vor dem Start: ab 0
    assert lauf.atem is not None and lauf.atem.laeufe == [[0.0, None]]
    lauf.atem_phase(alt.start_mono - 0.3, "ein")
    lauf.atem_fenster(alt.start_mono - 1.0, 6.0, True)
    lauf.atem_phase(alt.start_mono + 0.0, "aus")
    assert lauf.atem.phasen == [(0.0, "aus")] and lauf.atem.fenster_liste == []
    await _bis(lauf, 12)
    teil1 = await lauf.aufnahme_teilen_async(tmp_path)
    neu = lauf.aufnahme
    assert teil1 is not None and neu is not None
    lauf.atem_phase(neu.start_mono - 0.31, "ein")  # Ansatz vor der Naht, bestätigt danach
    lauf.atem_phase(neu.start_mono + 4.69, "aus")
    await _bis(lauf, 8)
    teil2 = await lauf.aufnahme_stoppen_async(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert teil2 is not None
    a2 = atem_laden(atem_pfad(teil2.pfad))
    assert a2.phasen == [(4.69, "aus")] and all(t >= 0.0 for t, _ in a2.phasen)
    assert a2.erfasst[0][0] == 0.0


async def test_stopp_schliesst_den_atem_lauf_am_stopp(tmp_path) -> None:
    """Fünfte Prüfrunde, B5: Stoppt die Aufnahme, während die Spur läuft, endet der Lauf im
    Beiwerk am Stopp — nicht am letzten Fenster (bis 5 s früher); die Spur bleibt an."""
    from hrv_core.atem import atem_laden, atem_pfad

    lauf, task = await _laufend(tmp_path)
    aufnahme = lauf.aufnahme
    assert aufnahme is not None
    assert lauf.atem_sammler(geraet="polar_h10", rate_hz=50) is not None
    lauf.atem_lauf_beginn(aufnahme.start_mono + 2.0)
    lauf.atem_fenster(aufnahme.start_mono + 10.0, 6.0, True)
    await _bis(lauf, 20)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None and lauf.atem_aktiv and lauf.atem is None
    a = atem_laden(atem_pfad(ergebnis.pfad))
    assert len(a.erfasst) == 1 and a.erfasst[0][0] == 2.0 and a.erfasst[0][1] >= 20.0
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


async def test_zwischenstand_notizen_kommen_in_die_ganze_aufnahme(tmp_path) -> None:
    """A21 (Ben, 10.11.2026): „Zwischenstand speichern“ schreibt die Aufnahme bis hier als
    eigene Datei, dieselbe Aufnahme läuft weiter. Notizen und Abschnitte, die man am
    Zwischenstand nachträglich ergänzt, kommen beim Speichern der ganzen Aufnahme mit — die
    Anker gelten unverändert, weil seine Schläge der Anfang der Aufnahme sind."""
    import json

    from hrv_core.recording import laden

    lauf = Messlauf(SimulatedSource(tempo=40.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    assert await lauf.aufnahme_zwischenstand_async(tmp_path) is None  # ohne Aufnahme nichts
    lauf.aufnahme_starten()
    while lauf.aufnahme is None or len(lauf.aufnahme.beats) < 30:
        await asyncio.sleep(0.01)
    lauf.notiz_hinzufuegen("vorher")
    aufnahme = lauf.aufnahme
    zwischen = await lauf.aufnahme_zwischenstand_async(tmp_path)
    assert zwischen is not None and zwischen.zwischenstand and lauf.aufnahme is aufnahme
    assert zwischen.pfad.name.endswith("_zwischen.json") and not zwischen.ersetzt
    n = len(zwischen.recording.beats)
    assert [e["text"] for e in laden(zwischen.pfad).ereignisse] == ["vorher"]
    # Das Backup der laufenden Aufnahme bleibt — der Zwischenstand räumt nichts auf
    lauf.backup_jetzt()
    assert list(tmp_path.rglob("*backup*"))

    # Am Zwischenstand nachträglich eine Notiz ergänzt (wie in der Aufzeichnung)
    doc = json.loads(zwischen.pfad.read_text(encoding="utf-8"))
    doc["ereignisse"].append({"beat_index": 5, "t_s": 4.0, "t_wall_s": 4.0, "text": "nachher"})
    zwischen.pfad.write_text(json.dumps(doc), encoding="utf-8")

    while len(lauf.aufnahme.beats) < n + 30:
        await asyncio.sleep(0.01)
    lauf.notiz_hinzufuegen("spät")
    ganz = lauf.aufnahme_stoppen(tmp_path)
    task.cancel()
    assert ganz is not None and ganz.ersetzt == (zwischen.pfad,)
    assert len(ganz.recording.beats) >= n + 30
    texte = [e["text"] for e in laden(ganz.pfad).ereignisse]
    assert texte == ["nachher", "vorher", "spät"] or sorted(texte) == ["nachher", "spät", "vorher"]
    assert texte.count("vorher") == 1  # die Notiz von vor dem Zwischenstand nicht doppelt
    # Die Schläge des Zwischenstands sind der Anfang der ganzen Aufnahme
    assert [b.rr_ms for b in ganz.recording.beats[:n]] == [
        b.rr_ms for b in zwischen.recording.beats
    ]
    # Die nächste Aufnahme beginnt ohne Zwischenstände
    assert lauf._zwischen == []


async def test_teile_zusammenfuegen_ergibt_einen_strom(tmp_path) -> None:
    """Ben, 10.11.2026 (A21): Teile einer langen Aufnahme („Teil speichern, weiter aufnehmen“)
    werden in der App wieder **eine** Messdatei — lange Ströme für VLF und ULF. Die Teile
    bleiben liegen, die neue Datei heißt ``…_zusammen.json``."""
    from hrv_core.recording import laden

    from trainingsapp.devices.messlauf import teile_zusammenfuegen

    lauf = Messlauf(SimulatedSource(tempo=40.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme is None or len(lauf.aufnahme.beats) < 30:
        await asyncio.sleep(0.01)
    lauf.notiz_hinzufuegen("in Teil 1")
    teil1 = await lauf.aufnahme_teilen_async(tmp_path)
    while len(lauf.aufnahme.beats) < 30:
        await asyncio.sleep(0.01)
    lauf.notiz_hinzufuegen("in Teil 2")
    teil2 = lauf.aufnahme_stoppen(tmp_path)
    task.cancel()
    assert teil1 is not None and teil2 is not None

    with pytest.raises(ValueError, match="mindestens zwei"):
        teile_zusammenfuegen([teil1.pfad])
    ganz = teile_zusammenfuegen([teil2.pfad, teil1.pfad])  # die Reihenfolge ist egal
    assert ganz.pfad.name == teil1.pfad.stem + "_zusammen.json"
    assert teil1.pfad.exists() and teil2.pfad.exists()  # die Teile bleiben
    n1, n2 = len(teil1.recording.beats), len(teil2.recording.beats)
    rec = laden(ganz.pfad)
    assert len(rec.beats) == n1 + n2
    assert ganz.started_at == teil1.started_at.replace(microsecond=0)
    assert [b.rr_ms for b in rec.beats[:n1]] == [b.rr_ms for b in teil1.recording.beats]
    texte = [e["text"] for e in rec.ereignisse]
    assert texte.index("in Teil 1") < texte.index("Teil 2") < texte.index("in Teil 2")
    # Die Dauer je Uhr für sich, aus den Dateien: Die Herzuhr zählt weiter, die Wanduhr des
    # zweiten Teils rückt um den Abstand der Startzeiten. Vorher stand hier die Herzuhr der
    # ganzen Datei gegen die Wanduhr der Teile (``Gespeichert.dauer_s`` einer Aufnahme) mit
    # ±2 s — bei ``tempo=40`` sind das 50 ms echte Zeit, unter Last in der CI zu wenig.
    t1, t2 = laden(teil1.pfad), laden(teil2.pfad)
    assert ganz.dauer_s == rec.dauer_s == pytest.approx(t1.dauer_s + t2.dauer_s, abs=0.002)
    assert t1.start_utc is not None and t2.start_utc is not None
    versatz = (t2.start_utc - t1.start_utc).total_seconds()
    assert rec.dauer_wanduhr_s == pytest.approx(versatz + t2.dauer_wanduhr_s, abs=0.002)
    # H52: Was dieselbe Zeit enthält, wird nicht aneinandergehängt (Schläge stünden doppelt)
    with pytest.raises(ValueError, match="überschneiden sich"):
        teile_zusammenfuegen([ganz.pfad, teil1.pfad])
    with pytest.raises(ValueError, match="überschneiden sich"):
        teile_zusammenfuegen([teil1.pfad, teil1.pfad])


# -- Durchsicht 10.11.2026: H60, H61, H65, H89, H90 ------------------------------------------


async def _aufnehmend(tmp_path, schlaege: int = 30) -> tuple[Messlauf, asyncio.Task]:
    lauf = Messlauf(SimulatedSource(tempo=40.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme is None or len(lauf.aufnahme.beats) < schlaege:
        await asyncio.sleep(0.01)
    return lauf, task


async def test_aufnahmestart_beginnt_die_gurt_warnung_neu(tmp_path) -> None:
    """H61: Die Sperrfrist rechnet auf der Live-Achse, die mit der Aufnahme bei 0 beginnt —
    ein Alarm von vorher (bei 29 min) hielte sonst bis 31 min jeden neuen zurück."""
    lauf = Messlauf(SimulatedSource(tempo=40.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    wache = lauf.artefaktwache
    assert wache.pruefen(0.2, 1740.0) is not None and wache.alarme == 1
    lauf.aufnahme_starten()
    assert lauf.artefaktwache is wache and lauf.warnung is None
    assert wache.pruefen(0.2, 200.0) is not None
    assert wache.alarme == 2  # der Zähler läuft weiter (Uhr-Kanal vergleicht ihn)


async def test_backup_neben_fremder_messdatei_derselben_sekunde_bleibt_erhalten(tmp_path) -> None:
    """H65: Liegt unter dem Namen des Backups schon eine **andere** Messung (zwei Aufnahmen
    in derselben Startsekunde), ist das Backup nicht „schon gespeichert“ — es wird unter dem
    nächsten freien Namen gesichert, die fremde Datei bleibt Byte für Byte."""
    from hrv_core.aufnahme import backup_lesen

    from trainingsapp.devices.messlauf import backup_wiederherstellen

    await _abgestuerzt(tmp_path)
    backup = next(tmp_path.rglob(".backup_*.json"))
    rec, _ = backup_lesen(backup)
    fremd = backup.parent / rec.dateiname()
    doc = rec.to_dict()
    doc["messungen"] = doc["messungen"][5:15]  # andere Schläge, derselbe Name
    fremd.write_text(json.dumps(doc), encoding="utf-8")
    vorher = fremd.read_bytes()

    ergebnis = backup_wiederherstellen(backup)
    assert ergebnis is not None and ergebnis.pfad != fremd
    assert ergebnis.pfad.name == fremd.stem + "_1.json"
    assert len(laden(ergebnis.pfad).beats) == len(rec.beats)
    assert fremd.read_bytes() == vorher and not backup.exists()


async def test_teilen_sichert_vorher_den_stand_von_jetzt(tmp_path, monkeypatch) -> None:
    """H89: Scheitert das Schreiben von Teil 1, bleibt nur sein Backup — es muss den Stand
    beim Teilen haben, nicht den von vor bis zu 15 s."""
    from hrv_core.aufnahme import backup_lesen

    lauf, task = await _aufnehmend(tmp_path)
    lauf.notiz_hinzufuegen("kurz vor dem Teilen")
    alt = lauf.aufnahme
    assert alt is not None
    n = len(alt.beats)

    def voll(*_a, **_k):
        raise OSError("Speicher voll")

    monkeypatch.setattr(lauf, "_schreiben", voll)
    with pytest.raises(OSError):
        await lauf.aufnahme_teilen_async(tmp_path)
    task.cancel()
    assert lauf.aufnahme is not alt  # Teil 2 läuft trotzdem
    backup = next(p for p in tmp_path.rglob(".backup_*.json") if alt.backup_name() == p.name)
    rec, _ = backup_lesen(backup)
    assert len(rec.beats) == n
    assert [e["text"] for e in rec.ereignisse] == ["kurz vor dem Teilen"]


async def test_zwei_zwischenstaende_zugleich_schreiben_nur_einen(tmp_path) -> None:
    """H90: Der Schutz gegen den Doppeltipp liegt im Messlauf — zwei gleichzeitige Aufrufe
    wählten im Thread sonst denselben freien Pfad."""
    lauf, task = await _aufnehmend(tmp_path)
    a, b = await asyncio.gather(
        lauf.aufnahme_zwischenstand_async(tmp_path), lauf.aufnahme_zwischenstand_async(tmp_path)
    )
    assert (a is None) != (b is None)
    assert len(lauf._zwischen) == 1 and len(list(tmp_path.rglob("*_zwischen*.json"))) == 1
    # Danach geht wieder einer
    dritter = await lauf.aufnahme_zwischenstand_async(tmp_path)
    task.cancel()
    assert dritter is not None and len(lauf._zwischen) == 2


async def test_am_zwischenstand_verschobene_grenze_ersetzt_die_alte(tmp_path) -> None:
    """H60: Wer am Zwischenstand eine Abschnittsgrenze verschiebt, hat in der ganzen Datei
    **eine** Grenz-Notiz je Kennung — die verschobene; vorher standen beide darin, und
    `grenzen_aus_notizen` nahm die alte. Gelesen werden die Zwischenstände in einem Thread."""
    from trainingsapp.core import abschnitte

    lauf, task = await _aufnehmend(tmp_path)
    kennung = lauf.abschnitt_starten("Behandlung")
    lauf.notiz_hinzufuegen("frei")
    zwischen = await lauf.aufnahme_zwischenstand_async(tmp_path)
    assert zwischen is not None and kennung is not None

    doc = json.loads(zwischen.pfad.read_text(encoding="utf-8"))
    grenze = next(e for e in doc["ereignisse"] if abschnitte.kennung_von(e) == kennung)
    grenze["t_wall_s"] = round(float(grenze["t_wall_s"]) / 2, 2)  # nach vorn geschoben
    grenze["beat_index"] = 2
    zwischen.pfad.write_text(json.dumps(doc), encoding="utf-8")

    ganz = await lauf.aufnahme_stoppen_async(tmp_path)
    task.cancel()
    assert ganz is not None and ganz.ersetzt == (zwischen.pfad,)
    notizen = laden(ganz.pfad).ereignisse
    grenzen = [e for e in notizen if abschnitte.kennung_von(e) == kennung]
    # … und die Ende-Notiz, die der Stopp dem laufenden Abschnitt gibt (Ben, 12.11.2026)
    assert [e["text"] for e in grenzen] == ["Behandlung: Start", "Behandlung: Ende"]
    assert grenzen[0]["beat_index"] == 2
    assert [e["text"] for e in notizen].count("frei") == 1


async def test_getippte_grenzen_und_nachgetragener_abschnitt(tmp_path) -> None:
    """Ben, 12.11.2026: Notizen „X: Start“ / „X: Ende“ ergeben live einen Abschnitt, auch
    getippt; ein Abschnitt lässt sich mit zwei Zeiten nachtragen, ändern und löschen — das
    Paar Grenz-Notizen ist der Abschnitt."""
    from hrv_core.ausschnitte import zusatz_lesen
    from hrv_core.ereignisse import notiz

    lauf, task = await _laufend(tmp_path)
    await _bis(lauf, 40)
    zb = lauf.notiz_zeitbezug()
    anfang = float(zb.wand_versatz or 0.0)
    getippt = [
        notiz("Behandlung: Start", zb.anker(anfang + 5), zb.start_utc),
        notiz("zwischendurch", zb.anker(anfang + 10), zb.start_utc),
        notiz("behandlung: ende", zb.anker(anfang + 25), zb.start_utc),
        notiz("Ruhe: Ende", zb.anker(anfang + 30), zb.start_utc),  # ohne Start: bleibt Notiz
    ]
    lauf.ereignisse_setzen(getippt)
    (a,) = lauf.abschnitte()
    assert (a.name, a.von_s - anfang, a.bis_s - anfang) == pytest.approx(("Behandlung", 5, 25))
    assert ["marke" in e for e in lauf.ereignisse()] == [True, False, True, False]
    assert lauf.offener_abschnitt() is None
    # Nachtragen mit zwei Zeiten, dann ändern
    kennung = lauf.abschnitt_setzen(None, "Belastung", anfang + 28, anfang + 38, kopf_s=5)
    assert kennung is not None
    assert [(b.name, round(b.von_s - anfang)) for b in lauf.abschnitte()] == [
        ("Behandlung", 5),
        ("Belastung", 28),
    ]
    assert lauf.abschnitt_setzen(kennung, "Treppe", anfang + 27, anfang + 39) == kennung
    texte = [e["text"] for e in lauf.ereignisse()]
    assert "Treppe: Start" in texte and "Treppe: Ende" in texte and "Belastung: Start" not in texte
    # Den Text der Start-Notiz ändern benennt um
    liste = lauf.ereignisse()
    liste[0] = dict(liste[0], text="Rücken: Start")
    lauf.ereignisse_setzen(liste)
    assert [b.name for b in lauf.abschnitte()] == ["Rücken", "Treppe"]
    assert "Rücken: Ende" in [e["text"] for e in lauf.ereignisse()]
    # Löschen nimmt das Paar mit; die Notizen von vorher holen ihn zurück
    vorher = lauf.abschnitt_loeschen(kennung)
    assert [b.name for b in lauf.abschnitte()] == ["Rücken"]
    lauf.ereignisse_setzen(vorher)
    assert [b.name for b in lauf.abschnitte()] == ["Rücken", "Treppe"]
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None
    _, teile = zusatz_lesen(ergebnis.pfad, float)
    assert [t.name for t in teile] == ["Rücken", "Treppe"]


async def test_marker_teilt_und_halbe_gruppen_gelten_nicht(tmp_path) -> None:
    """Ben, 12.11.2026: „Rad: Start“ · „Rad: Marker (5 km)“ · „Rad: Ende“ — ein Abschnitt je
    Stück; ein gelöschter Marker nimmt seine Trennung weg. Ein Ende ohne Start bleibt eine
    Notiz ohne Marke; was beim Stopp noch läuft, bekommt seine Ende-Notiz."""
    from hrv_core.ausschnitte import zusatz_lesen
    from hrv_core.recording import laden

    from trainingsapp.core import abschnitte

    lauf, task = await _laufend(tmp_path)
    await _bis(lauf, 10)
    assert not lauf.abschnitt_marker()  # ohne laufenden Abschnitt kein Marker
    lauf.abschnitt_starten("Rad")
    await _bis(lauf, 25)
    assert lauf.abschnitt_marker("5 km")
    await _bis(lauf, 40)
    assert [a.name for a in lauf.abschnitte()] == ["Rad (1)", "Rad (5 km)"]
    assert lauf.offener_abschnitt() is not None
    assert abschnitte.laufende_kennung(lauf.ereignisse()) == lauf.abschnitte()[1].id
    lauf.notiz_hinzufuegen("Ruhe: Ende")  # ohne Start
    lauf.ereignisse_setzen(lauf.ereignisse())
    assert abschnitte.verwaist(lauf.ereignisse()[-1])
    # Den Marker löschen: wieder ein Abschnitt
    ohne = [e for e in lauf.ereignisse() if "Marker" not in e["text"]]
    mit = lauf.ereignisse()
    lauf.ereignisse_setzen(ohne)
    assert [a.name for a in lauf.abschnitte()] == ["Rad"]
    lauf.ereignisse_setzen(mit)
    await _bis(lauf, 55)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)  # „Rad“ läuft noch: der Stopp schließt ihn
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None
    texte = [e["text"] for e in laden(ergebnis.pfad).ereignisse]
    assert texte == ["Rad: Start", "Rad: Marker (5 km)", "Ruhe: Ende", "Rad: Ende"]
    _, teile = zusatz_lesen(ergebnis.pfad, float)
    assert [t.name for t in teile] == ["Rad (1)", "Rad (5 km)"]
    assert teile[0].bis_s == pytest.approx(teile[1].von_s, abs=0.5)
