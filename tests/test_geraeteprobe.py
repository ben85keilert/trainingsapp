"""Geräteprobe: Rohmitschnitt eines unbekannten Geräts ohne Messung (Diagnosemodus, Stufe 6).

Kein Gerät: eine Attrappe mit einem Herzfrequenz-Dienst, einem herstellereigenen Dienst und
der Geräteinformation samt Seriennummer, die nie gelesen werden darf. Namen und Adressen
erfunden.
"""

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from datetime import UTC, datetime

from hrv_core import mitschnitt as mt
from hrv_core.geraete import gatt

from trainingsapp.devices.erkundung import Geraeteprobe, probe_loeschen, probe_zip, proben

NAME = "Gurt X 12345678"
MAC = "E2:B4:CC:3F:08:44"
EIGEN = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
EIGEN_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


class Attrappe:
    def __init__(self) -> None:
        self.abos: dict[str, object] = {}
        self.gelesen: list[str] = []
        self.geschrieben: list[bytes] = []
        self.letzte_meta: dict | None = None

    async def connect(self, device_id, bei_trennung) -> int:
        self.bei_trennung = bei_trennung
        return 185

    async def disconnect(self, device_id) -> None:
        self.abos.clear()

    async def discover(self, device_id) -> set[str]:
        return {gatt.HR_SERVICE_UUID, EIGEN, gatt.DEVICE_INFO_SERVICE_UUID}

    async def dienste_abbild(self, device_id) -> list[dict]:
        return [
            {
                "uuid": gatt.HR_SERVICE_UUID,
                "merkmale": [
                    {"uuid": gatt.HR_MEASUREMENT_UUID, "eigenschaften": ["benachrichtigen"]}
                ],
            },
            {
                "uuid": gatt.DEVICE_INFO_SERVICE_UUID,
                "merkmale": [
                    {"uuid": gatt.uuid16(0x2A29), "eigenschaften": ["lesen"]},
                    {"uuid": gatt.SERIENNUMMER_UUID, "eigenschaften": ["lesen"]},
                ],
            },
            {
                "uuid": EIGEN,
                "merkmale": [
                    {"uuid": EIGEN_TX, "eigenschaften": ["benachrichtigen", "schreiben"]},
                ],
            },
        ]

    async def read(self, device_id, service, characteristic) -> bytes:
        self.gelesen.append(characteristic)
        return b"Firma"

    async def write(self, *args, **kwargs) -> None:
        self.geschrieben.append(args[3] if len(args) > 3 else b"")

    async def subscribe(self, device_id, service, characteristic, empfaenger) -> None:
        self.abos[characteristic] = empfaenger

    def senden(self, characteristic: str, daten: bytes) -> None:
        self.abos[characteristic](daten, 0.0)


async def test_probe_liest_abonniert_schreibt_nie_und_legt_ab(tmp_path) -> None:
    innen = Attrappe()
    uhr = {"t": 100.0}
    probe = Geraeteprobe(
        innen,
        tmp_path,
        uhr=lambda: uhr["t"],
        jetzt_utc=lambda: datetime(2026, 11, 4, 6, 15, tzinfo=UTC),
    )
    dienste = await probe.verbinden(MAC, NAME)
    assert [d["name"] for d in dienste] == [
        "Herzfrequenz (0x180D)",
        "Geräteinformation (0x180A)",
        "herstellereigen (6e400001…)",
    ]
    ordner = await probe.starten()
    assert ordner.name == "2026-11-04_061500_Gurt_X" and probe.laeuft
    # Seriennummer nie gelesen, nichts geschrieben, beide Melder abonniert
    assert innen.gelesen == [gatt.uuid16(0x2A29)] and innen.geschrieben == []
    assert set(innen.abos) == {gatt.HR_MEASUREMENT_UUID, EIGEN_TX}
    innen.senden(gatt.HR_MEASUREMENT_UUID, bytes([0x10, 60, 0x00, 0x04]))
    uhr["t"] += 1.0
    innen.senden(EIGEN_TX, bytes([1, 2, 3]))
    assert probe.marke("bewegt")["kontext"] == {"phase": "bewegt"}
    stand = probe.stand()
    assert stand["seit_s"] == 1.0 and stand["pakete"] == {"andere": 1, "hr": 1}
    fertig = await probe.beenden({"hersteller": "Firma X", "vergleich": "Puls laut Uhr 64"})
    assert fertig == ordner and not probe.laeuft
    doc = json.loads((ordner / "probe.json").read_text(encoding="utf-8"))
    assert doc["format"] == "geraeteprobe-v1" and doc["formular"]["vergleich"] == "Puls laut Uhr 64"
    assert doc["zusammenfassung"]["pakete"] == {"hr": 1, EIGEN_TX: 1}
    m = mt.laden(ordner / mt.DATEINAME)
    assert m.kopf["geraet"]["art"] == "unbekannt" and len(m.kopf["dienste"]) == 3
    assert [z["was"] for z in m.art("kontext")] == ["diagnose_start", "diagnose_ende"]
    # Auf dem Gerät gelistet, geteilt bereinigt, gelöscht
    (eintrag,) = proben(tmp_path)
    assert eintrag["fertig"] and eintrag["name"] == "Gurt X"
    with zipfile.ZipFile(io.BytesIO(probe_zip(ordner))) as z:
        text = z.read(f"Diagnose/{ordner.name}/mitschnitt.jsonl").decode()
        kopf = json.loads(z.read(f"Diagnose/{ordner.name}/probe.json"))
    assert MAC not in text and "12345678" not in text and kopf["geraet"]["name"] == "Gurt X"
    probe_loeschen(ordner)
    assert proben(tmp_path) == []


def test_ordner_wird_nicht_ueberschrieben(tmp_path) -> None:
    probe = Geraeteprobe(
        Attrappe(), tmp_path, jetzt_utc=lambda: datetime(2026, 11, 4, 6, 15, tzinfo=UTC)
    )

    async def zweimal() -> tuple:
        await probe.verbinden(MAC, NAME)
        a = await probe.starten()
        await probe.beenden()
        b = await probe.starten()
        await probe.beenden()
        return a, b

    a, b = asyncio.run(zweimal())
    assert a != b and b.name.endswith("_2")
