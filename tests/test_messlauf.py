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
    assert datei == "Generator/sensor_2026-10-17_080000.json"
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
    assert texte == ["Behandlung: Start", "Behandlung: Ende", "Ruhe: Start", "Ruhe: Ende"]
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
    teil1 = await lauf.aufnahme_teilen_async(tmp_path)
    assert teil1 is not None and teil1.pfad.exists()
    assert lauf.aufnahme is not None and lauf.aufnahme.titel == "Nacht"
    assert lauf.aufnahme_dauer_s() < 5  # die neue zählt von vorn
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


async def test_ohne_einstellung_kein_ekg(tmp_path) -> None:
    from hrv_core.ekg import ekg_pfad

    _, ergebnis, _ = await _messen(tmp_path, SIM_SYNTH, 10)
    assert ergebnis is not None and not ekg_pfad(ergebnis.pfad).exists()
    assert json.loads(ergebnis.pfad.read_text(encoding="utf-8"))["ecg_aufzeichnung"] is False
