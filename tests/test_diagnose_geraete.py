"""Diagnosemodus, Geräteschicht: mithörender Transport, Beschleunigung, Rohmitschnitt im Messlauf.

`docs/plan_diagnosemodus.md` Stufe 2. Kein Gerät: der `FakeTransport` aus ``test_devices``
spielt den BLE-Stack, eine künstliche Uhr den Takt. Bytes synthetisch nach dem PMD-Format.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hrv_core import mitschnitt as mt
from hrv_core.aufnahme import backups_finden

from test_devices import H10_DIENSTE, H10_NAME, FakeTransport, FakeZeit, _ruhe
from trainingsapp.devices import pmd
from trainingsapp.devices.base import HR_MEASUREMENT_UUID, Verbindung
from trainingsapp.devices.messlauf import Messlauf, backup_wiederherstellen
from trainingsapp.devices.mitschnitt import MitschnittTransport, Strom
from trainingsapp.devices.polar import PolarQuelle

H10_MERKMALE = bytes([0x0F, 0b0000_0101])  # EKG und Beschleunigung
OK = {
    pmd.MEAS_ECG: bytes([0xF0, pmd.OP_START, pmd.MEAS_ECG, 0x00, 0x00, 0x00]),
    pmd.MEAS_ACC: bytes([0xF0, pmd.OP_START, pmd.MEAS_ACC, 0x00, 0x00, 0x01]),
}
SERIENNUMMER = "00002a25-0000-1000-8000-00805f9b34fb"


class DiagnoseTransport(FakeTransport):
    """Antwortet je Kommando wie der H10 (Start ok, Einstellungen mit Parametern) und liefert
    Folgenummer und Dart-Zeiten wie ``FletBleTransport.letzte_meta``."""

    def __init__(self) -> None:
        super().__init__(H10_DIENSTE, control_antwort=None, features=H10_MERKMALE)
        self.antworten: dict[bytes, bytes] = {
            pmd.ECG_START: OK[pmd.MEAS_ECG],
            pmd.ACC_START: OK[pmd.MEAS_ACC],
            pmd.acc_start(100, 4): OK[pmd.MEAS_ACC],
            pmd.ACC_EINSTELLUNGEN: bytes([0xF0, 0x01, pmd.MEAS_ACC, 0, 0])
            + pmd.einstellungen_kodieren({"rate_hz": [25, 50, 100, 200], "bereich_g": [2, 4, 8]}),
        }
        self.letzte_meta: dict[str, int] | None = None
        self._seq = 0

    async def write(self, device_id, service, characteristic, data, mit_antwort=True) -> None:
        await super().write(device_id, service, characteristic, data, mit_antwort)
        antwort = self.antworten.get(bytes(data))
        ziel = self.abos.get(pmd.PMD_CONTROL_UUID)
        if characteristic == pmd.PMD_CONTROL_UUID and antwort is not None and ziel is not None:
            ziel(antwort, 0.0)

    def senden(self, characteristic: str, daten: bytes, t: float) -> None:
        self._seq += 1
        self.letzte_meta = {"seq": self._seq, "t_mono_us": round(t * 1e6), "t_wall_us": 7}
        super().senden(characteristic, daten, t)

    def acc_rahmen(self, t_ns: int, n: int = 36) -> bytes:
        return pmd.rahmen_bauen(pmd.MEAS_ACC, t_ns, pmd.acc_kodieren([(1, -2, 1000)] * n), 1)


async def _verbunden(
    zeit: FakeZeit, *, acc: tuple[int, int] | None = None, ekg: bool = False
) -> tuple[PolarQuelle, DiagnoseTransport, MitschnittTransport]:
    innen = DiagnoseTransport()
    transport = MitschnittTransport(innen, uhr=zeit.uhr)
    quelle = PolarQuelle(
        transport,
        uhr=zeit.uhr,
        schlafen=zeit.schlafen,
        ekg=ekg,
        acc=acc,
        protokoll=transport.protokoll,
    )
    aufbau = asyncio.create_task(quelle.connect("AA:BB:CC:DD:EE:FF", H10_NAME))
    await zeit.vorspulen(1.0)
    await aufbau
    return quelle, innen, transport


def _writes(innen: DiagnoseTransport) -> list[bytes]:
    return [a[2] for a in innen.aufrufe if a[0] == "write" and a[1] == pmd.PMD_CONTROL_UUID]


async def test_beschleunigung_startet_nach_dem_ekg_mit_pause_und_wird_gezaehlt() -> None:
    zeit = FakeZeit()
    gesehen: list[tuple[int, int]] = []
    quelle, innen, transport = await _verbunden(zeit, acc=(200, 8), ekg=True)
    try:
        assert _writes(innen) == [pmd.ECG_START, pmd.ACC_START]
        assert quelle.ekg_modus and quelle.acc_modus
        # Die Merkmalsliste wird im Diagnosemodus auch beim benannten H10 gelesen? Nein —
        # erst auf Wunsch (Sensorblatt); beim Aufbau entscheidet das Profil.
        assert quelle.pmd_merkmale is None
        assert await quelle.merkmale_lesen() == frozenset({"ecg", "acc"})
        assert transport.pmd_merkmale == frozenset({"ecg", "acc"})
        quelle.acc_beobachter = lambda t_ns, proben, t: gesehen.append((t_ns, len(proben)))
        innen.senden(pmd.PMD_DATA_UUID, innen.acc_rahmen(5_000_000_000), zeit.t)
        innen.senden(pmd.PMD_DATA_UUID, innen.acc_rahmen(5_180_000_000), zeit.t)
        await _ruhe()
        assert quelle.acc_rahmen == 2 and gesehen == [(5_000_000_000, 36), (5_180_000_000, 36)]
        assert transport.zaehler.stroeme["acc"].proben == 72
        # Die Beschleunigung hält den Watchdog nicht wach (V2): nur 0x2A37 tut das
        assert quelle._letzte_daten < zeit.t or quelle._letzte_daten == quelle._verbunden_seit
    finally:
        await quelle.disconnect()


async def test_beschleunigung_abgelehnt_laeuft_bereits_und_einstellungen() -> None:
    zeit = FakeZeit()
    quelle, innen, _ = await _verbunden(zeit, acc=(200, 8))
    try:
        assert _writes(innen) == [pmd.ACC_START]  # ohne EKG keine Pause, kein EKG-Start
        # „läuft bereits“ → einmal Stopp und neuer Start
        innen.senden(pmd.PMD_CONTROL_UUID, bytes([0xF0, 0x02, 0x02, 0x06, 0x00]), zeit.t)
        await zeit.vorspulen(1.0)
        assert _writes(innen)[-2:] == [pmd.ACC_STOP, pmd.ACC_START]
        # Einstellungen abfragen: die Antwort landet in pmd_einstellungen
        abfrage = asyncio.create_task(quelle.einstellungen_abfragen())
        await zeit.vorspulen(1.0)
        await abfrage
        assert quelle.pmd_einstellungen["acc"]["rate_hz"] == [25, 50, 100, 200]
        assert quelle.pmd_einstellungen["acc"]["bereich_g"] == [2, 4, 8]
        # Eine echte Ablehnung: nur die Beschleunigung geht aus, mit eigener Meldung (V3)
        innen.senden(pmd.PMD_CONTROL_UUID, bytes([0xF0, 0x02, 0x02, 0x09, 0x00]), zeit.t)
        await _ruhe()
        assert not quelle.acc_modus
        assert quelle.aktueller_status.meldung.startswith("Beschleunigung abgelehnt")
        assert quelle.aktueller_status.verbindung is Verbindung.VERBUNDEN
    finally:
        await quelle.disconnect()


async def test_stroeme_zur_laufzeit_an_und_aus_und_nach_dem_neuverbinden() -> None:
    zeit = FakeZeit()
    quelle, innen, _ = await _verbunden(zeit)
    try:
        assert _writes(innen) == []
        umschalten = asyncio.create_task(quelle.stroeme_setzen(ekg=True, acc=(100, 4)))
        await zeit.vorspulen(1.0)
        await umschalten
        assert _writes(innen) == [pmd.ECG_START, pmd.acc_start(100, 4)]
        assert innen.anzahl("subscribe", pmd.PMD_CONTROL_UUID) == 1
        # Nach einer Trennung startet der Aufbau beide wieder
        assert innen.bei_trennung is not None
        innen.bei_trennung("Abriss")
        await zeit.vorspulen(10.0)
        assert quelle.acc_modus and quelle.ekg_modus
        assert _writes(innen)[-2:] == [pmd.ECG_START, pmd.acc_start(100, 4)]
        aus = asyncio.create_task(quelle.stroeme_setzen(ekg=False, acc=None))
        await zeit.vorspulen(1.0)
        await aus
        assert _writes(innen)[-2:] == [pmd.ECG_STOP, pmd.ACC_STOP]
        assert not quelle.acc_modus and not quelle.ekg_modus
    finally:
        await quelle.disconnect()


async def test_transport_schreibt_mit_und_liest_nie_die_seriennummer(tmp_path) -> None:
    zeit = FakeZeit()
    quelle, innen, transport = await _verbunden(zeit)
    try:
        schreiber = mt.Schreiber(tmp_path / "x_mitschnitt.jsonl", {"app": "test"}, uhr_ns=lambda: 1)
        transport.anhaengen(schreiber)
        innen.senden(HR_MEASUREMENT_UUID, bytes([0x10, 60, 0x00, 0x04]), zeit.t)
        with pytest.raises(PermissionError):
            await transport.read("AA:BB:CC:DD:EE:FF", "0000180a", SERIENNUMMER)
        await transport.write(
            "AA:BB:CC:DD:EE:FF", pmd.PMD_SERVICE_UUID, pmd.PMD_CONTROL_UUID, b"\x01\x02"
        )
        assert transport.abhaengen() is schreiber
        innen.senden(HR_MEASUREMENT_UUID, bytes([0x10, 61, 0x00, 0x04]), zeit.t)  # nicht mehr
        schreiber.schliessen()
        zeilen = list(mt.lesen(schreiber.pfad))
        n = [z for z in zeilen if z["art"] == "n"]
        assert len(n) == 1 and n[0]["c"] == "hr" and n[0]["x"] == "103c0004" and n[0]["s"] == 1
        assert n[0]["tw"] == 7 and n[0]["tm"] == round(zeit.t * 1e6)
        assert [z["x"] for z in zeilen if z["art"] == "w"] == ["0102"]
        assert any(z["art"] == "v" and z["text"].startswith("dienste") for z in zeilen)
        assert not any(z.get("c") == SERIENNUMMER for z in zeilen)
        assert transport.zaehler.stroeme["hr"].pakete == 2  # gezählt wird immer
    finally:
        await quelle.disconnect()


def test_rate_ueber_das_fenster() -> None:
    s = Strom()
    for k in range(100):
        s.ankunft(k * 0.1, 7)
    assert s.rate(9.9) == (10.0, 70.0)


# -- Messlauf ---------------------------------------------------------------------------------


async def _messlauf(
    tmp_path: Path, zeit: FakeZeit
) -> tuple[Messlauf, PolarQuelle, DiagnoseTransport]:
    innen = DiagnoseTransport()
    transport = MitschnittTransport(innen, uhr=zeit.uhr)
    quelle = PolarQuelle(
        transport, uhr=zeit.uhr, schlafen=zeit.schlafen, protokoll=transport.protokoll
    )
    # Die Wanduhr folgt der künstlichen Uhr — „Teil speichern“ braucht einen neuen Namen
    t0 = datetime(2026, 11, 4, 6, 0, tzinfo=UTC)
    lauf = Messlauf(quelle, backup_basis=tmp_path, jetzt_utc=lambda: t0 + timedelta(seconds=zeit.t))
    aufbau = asyncio.create_task(lauf.verbinden("AA:BB:CC:DD:EE:FF", H10_NAME))
    await zeit.vorspulen(1.0)
    await aufbau
    return lauf, quelle, innen


def _schlaege(lauf: Messlauf, innen: DiagnoseTransport, zeit: FakeZeit, n: int) -> None:
    for _ in range(n):
        zeit.t += 1.0
        innen.senden(HR_MEASUREMENT_UUID, bytes([0x10, 60, 0xE8, 0x03]), zeit.t)


async def test_messlauf_mitschnitt_vom_backup_zur_messdatei(tmp_path) -> None:
    zeit = FakeZeit()
    lauf, quelle, innen = await _messlauf(tmp_path, zeit)
    leser = asyncio.create_task(lauf.laufen())
    try:
        assert lauf.diagnose_moeglich and not lauf.diagnose_aktiv
        assert await lauf.diagnose_starten(acc=(200, 8)) is None  # ohne Aufnahme nicht
        lauf.aufnahme_starten()
        start = asyncio.create_task(
            lauf.diagnose_starten(ekg=True, acc=(200, 8), kopf={"marken": {"leiste": "unten"}})
        )
        await zeit.vorspulen(1.0)
        journal = await start
        assert journal is not None and journal.name.endswith("_mitschnitt.jsonl")
        assert journal.name.startswith(".backup_") and lauf.diagnose_aktiv
        assert _writes(innen)[-2:] == [pmd.ECG_START, pmd.ACC_START]
        _schlaege(lauf, innen, zeit, 5)
        innen.senden(pmd.PMD_DATA_UUID, innen.acc_rahmen(9_000_000_000), zeit.t)
        await _ruhe()
        # Eine automatische Notiz (Übung beginnt) steht auch als Kontext im Mitschnitt
        lauf.notiz_hinzufuegen(
            "Kniebeuge: Start",
            marke={"quelle": "plan", "art": "uebung_start", "name": "Kniebeuge"},
            uebungen=["KB000001"],
        )
        lauf.notiz_hinzufuegen("frei geschrieben")  # ohne Marke: nur in der Messdatei
        marke = lauf.marke(mt.MARKE_WDH, nr=1, kontext={"uebung": "Kniebeuge", "satz": 1})
        assert marke is not None and marke["id"] == 1
        lauf.kontext("satz", uebung="Kniebeuge", feld="reps", wert=12)
        stand = lauf.diagnose_stand()
        assert stand["aktiv"] and stand["acc"] and stand["ekg"] and stand["bytes"] > 0
        assert stand["stroeme"]["hr"]["pakete"] == 5 and stand["stroeme"]["acc"]["proben"] == 36
        gespeichert = await lauf.aufnahme_stoppen_async(tmp_path)
        assert gespeichert is not None
        ziel = mt.mitschnitt_pfad(gespeichert.pfad)
        assert ziel.exists() and not journal.exists() and not lauf.diagnose_aktiv
        # Die Zusatzströme stehen wieder wie vorher (aus)
        assert not quelle.acc_modus and not quelle.ekg_modus
        m = mt.laden(ziel)
        assert m.kopf["format"] == mt.FORMAT and m.kopf["messdatei"] == gespeichert.pfad.name
        assert m.kopf["geraet"]["name"] == H10_NAME and m.kopf["stroeme"]["acc"]["rate_hz"] == 200
        assert m.kopf["marken"] == {"leiste": "unten"}
        # Marken liegen auf der Wanduhr der Messdatei (Nullpunkt im Kopf)
        (erste,) = m.marken()
        assert m.wanduhr_s(erste["t"]) == pytest.approx(6.0)  # 1 s Start, 5 Schläge
        arten = {z["art"] for z in m.zeilen}
        assert {"kopf", "n", "w", "v", "marke", "kontext"} <= arten
        assert [z["was"] for z in m.art("kontext")] == ["diagnose_start", "uebung_start", "satz"]
        assert m.art("kontext")[1]["uebung_id"] == "KB000001"
        assert mt.zusammenfassen(m)["stroeme"]["acc"]["proben"] == 36
        # t im Mitschnitt ist die Uhr der Quelle (wie t_capture der Messwerte)
        n = m.benachrichtigungen("hr")
        assert n[-1]["t"] == round(zeit.t * 1e9)
    finally:
        await lauf.trennen()
        await asyncio.wait_for(leser, 2.0)


async def test_diagnose_beenden_teilen_und_wiederherstellen(tmp_path) -> None:
    zeit = FakeZeit()
    lauf, quelle, innen = await _messlauf(tmp_path, zeit)
    leser = asyncio.create_task(lauf.laufen())
    try:
        lauf.aufnahme_starten()
        start = asyncio.create_task(lauf.diagnose_starten(ekg=False, acc=(200, 8)))
        await zeit.vorspulen(1.0)
        erster = await start
        _schlaege(lauf, innen, zeit, 3)
        await _ruhe()
        # Teil speichern & weiter: Teil 1 behält seinen Mitschnitt, Teil 2 schreibt einen neuen
        zeit.t += 2.0
        teil1 = await lauf.aufnahme_teilen_async(tmp_path)
        assert teil1 is not None and mt.mitschnitt_pfad(teil1.pfad).exists()
        assert erster is not None and not erster.exists()
        assert lauf.diagnose_aktiv and lauf.mitschnitt is not None
        zweiter = lauf.mitschnitt.pfad
        assert zweiter != erster and zweiter.name.startswith(".backup_")
        _schlaege(lauf, innen, zeit, 3)
        await _ruhe()
        ende = asyncio.create_task(lauf.diagnose_beenden())
        await zeit.vorspulen(1.0)
        await ende
        assert not lauf.diagnose_aktiv and not quelle.acc_modus
        assert zweiter.exists()  # bleibt neben dem Backup, bis gespeichert wird
        # Absturz: Backup und Mitschnitt bleiben liegen — die Wiederherstellung macht beides
        lauf.backup_jetzt()
        (backup,) = backups_finden(tmp_path / "Messungen")
        wieder = backup_wiederherstellen(backup)
        assert wieder is not None
        ziel = mt.mitschnitt_pfad(wieder.pfad)
        assert ziel.exists() and not zweiter.exists()
        assert [z["was"] for z in mt.laden(ziel).art("kontext")] == [
            "diagnose_start",
            "diagnose_ende",
        ]
        assert not list(backup.parent.glob(".backup_*"))
    finally:
        lauf.aufnahme = None
        await lauf.trennen()
        await asyncio.wait_for(leser, 2.0)


async def test_aufnahme_ohne_schlag_verwirft_den_mitschnitt(tmp_path) -> None:
    zeit = FakeZeit()
    lauf, _, _ = await _messlauf(tmp_path, zeit)
    try:
        lauf.aufnahme_starten()
        start = asyncio.create_task(lauf.diagnose_starten(acc=(200, 8)))
        await zeit.vorspulen(1.0)
        journal = await start
        assert journal is not None and journal.exists()
        assert await lauf.aufnahme_stoppen_async(tmp_path) is None
        assert not journal.exists() and lauf.mitschnitt is None
    finally:
        await lauf.trennen()


def test_kopf_ist_json_und_ohne_seriennummer(tmp_path) -> None:
    """Die Kopfzeile steht vorn und ist ein JSON-Objekt (für jeden Leser)."""
    s = mt.Schreiber(tmp_path / "k_mitschnitt.jsonl", {"geraet": {"name": "Polar H10"}})
    s.schliessen()
    erste = (tmp_path / "k_mitschnitt.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(erste)["art"] == "kopf"


def test_export_nimmt_den_mitschnitt_nur_bereinigt_mit(tmp_path) -> None:
    from trainingsapp.core.hrv_export import export_zip, zugehoerige_dateien

    ordner = tmp_path / "Messungen" / "PolarH10"
    ordner.mkdir(parents=True)
    messdatei = ordner / "sensor_2026-11-04_060000.json"
    messdatei.write_text(json.dumps({"schema": "raw-v1", "messungen": []}), encoding="utf-8")
    s = mt.Schreiber(
        mt.mitschnitt_pfad(messdatei),
        {"geraet": {"name": "Polar H10 A1B2C3D4", "id": "E2:B4:CC:3F:08:44"}},
    )
    s.protokoll("Verbinde mit Polar H10 A1B2C3D4 [E2:B4:CC:3F:08:44]", q="polar")
    s.schliessen()
    dateien = zugehoerige_dateien(messdatei)
    assert mt.mitschnitt_pfad(messdatei) in dateien
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(export_zip(dateien, tmp_path))) as z:
        text = z.read("Messungen/PolarH10/sensor_2026-11-04_060000_mitschnitt.jsonl").decode()
    assert "3F:08:44" not in text and "A1B2C3D4" not in text
    assert "Polar H10 [E2:B4:CC:xx:xx:xx]" in text
    # Das Original auf dem Gerät bleibt, wie es ist
    assert "3F:08:44" in mt.mitschnitt_pfad(messdatei).read_text(encoding="utf-8")


async def test_nach_dem_satz_marken_zaehler_und_eingabe(tmp_path) -> None:
    """Stufe 8: Nach dem eingetragenen Satz zählt der Prototyp aus hrv-core die Wiederholungen
    in der gepufferten Beschleunigung — neben den Marken und der Eingabe."""
    import math

    zeit = FakeZeit()
    lauf, quelle, innen = await _messlauf(tmp_path, zeit)
    gemeldet: list[dict] = []
    lauf.diagnose_satz_beobachter = gemeldet.append
    lauf.aufnahme_starten()
    start = asyncio.create_task(lauf.diagnose_starten(ekg=False, acc=(200, 8)))
    await zeit.vorspulen(1.0)
    await start
    lauf.notiz_hinzufuegen(
        "Kniebeuge: Start",
        marke={"quelle": "plan", "art": "uebung_start", "name": "Kniebeuge"},
        uebungen=["KB000001"],
    )
    t0, t_geraet = zeit.t, 10**12
    for k in range(int(24 / 0.18)):  # 24 s, 12 Wiederholungen à 2 s, Rahmen zu 36 Proben
        proben = []
        for i in range(36):
            t = (k * 36 + i) / 200
            hub = 300 * math.sin(2 * math.pi * t / 2.0)
            proben.append((round(0.2 * hub), round(-1000 + hub), 0))
        t_geraet += 180_000_000
        zeit.t = t0 + (k + 1) * 0.18
        innen.senden(
            pmd.PMD_DATA_UUID,
            pmd.rahmen_bauen(pmd.MEAS_ACC, t_geraet, pmd.acc_kodieren(proben), 1),
            zeit.t,
        )
        if k % 11 == 5:  # gut alle 2 s eine Marke
            lauf.marke(mt.MARKE_WDH)
    lauf.notiz_hinzufuegen(
        "Kniebeuge: 12",
        marke={"quelle": "person", "art": "leistung", "feld": "reps", "wert": 12},
        uebungen=["KB000001"],
    )
    (v,) = gemeldet
    assert v["uebung"] == "Kniebeuge" and v["satz"] == 1 and v["eingetragen"] == 12
    assert v["marken"] == 12 and abs(v["zaehler"] - 12) <= 1 and v["art"] == "prototyp"
    # Ohne Zähl-Teil zählt der Prototyp den Puffer selbst — ohne Korrektur (Plan
    # Beschleunigung §6: „Marken · Sensor · Korrektur · eingetragen“)
    assert v["sensor"] == v["zaehler"] and v["korrektur"] == 0
    assert lauf.letzter_satz == v
    zeilen = list(mt.lesen(lauf.mitschnitt.pfad))
    (z,) = [z for z in zeilen if z.get("was") == "zaehler"]
    assert z["wert"] == v["zaehler"] and z["phase"] == "prototyp" and z["feld"] == "reps"
    assert z["satz"] == 1
    await lauf.diagnose_beenden()
    assert quelle.acc_beobachter is None
    lauf.aufnahme = None
    await lauf.trennen()
