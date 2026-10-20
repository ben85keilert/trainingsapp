"""Export: Beiwerk finden, byte-genau zippen, Diagnoseprotokoll neben der Aufnahme —
und die Bluetooth-Adresse bleibt auf dem Gerät (S10)."""

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from hrv_core.recording import Recording, laden, speichern

from trainingsapp.core.forschung import forschung_zip
from trainingsapp.core.hrv_export import (
    adresse_maskieren,
    diagnose_pfad,
    diagnose_text,
    export_zip,
    exportkopie,
    messdatei_ohne_adresse,
    zugehoerige_dateien,
)
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.simulated import SIM_PPI, SimulatedSource


def test_zugehoerige_dateien_rohdatei_zuerst_ohne_fremde(tmp_path) -> None:
    ordner = tmp_path / "Messungen" / "VeritySense"
    ordner.mkdir(parents=True)
    namen = [
        "sensor_2026-10-13_081500.json",
        "sensor_2026-10-13_081500_analyzed.json",
        "sensor_2026-10-13_081500_diagnose.txt",
        "sensor_2026-10-13_081500__c01.json",
        "sensor_2026-10-13_081500_analyzed.json.tmp",  # halbfertig
        "sensor_2026-10-13_091500.json",  # andere Messung
        ".backup_2026-10-13_081500.json",
    ]
    for n in namen:
        (ordner / n).write_text("{}", encoding="utf-8")
    (ordner / "sensor_2026-10-13_081500").mkdir()  # analysis-v3-Ordner

    gefunden = [p.name for p in zugehoerige_dateien(ordner / namen[0])]
    assert gefunden == [
        "sensor_2026-10-13_081500.json",
        "sensor_2026-10-13_081500__c01.json",
        "sensor_2026-10-13_081500_analyzed.json",
        "sensor_2026-10-13_081500_diagnose.txt",
    ]
    assert zugehoerige_dateien(tmp_path / "fehlt" / "sensor_x.json") == []


def test_export_zip_byte_genau_mit_relativen_pfaden(tmp_path) -> None:
    ordner = tmp_path / "Messungen" / "PolarH10"
    ordner.mkdir(parents=True)
    roh = ordner / "sensor_2026-10-13_081500.json"
    roh.write_bytes('{"geraet": "Polar H10 äöü"}\n'.encode())
    fremd = tmp_path.parent / f"{tmp_path.name}_fremd.txt"
    fremd.write_text("außerhalb", encoding="utf-8")

    daten = export_zip([roh, roh, fremd], tmp_path)
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        assert z.namelist() == ["Messungen/PolarH10/sensor_2026-10-13_081500.json", fremd.name]
        assert z.read("Messungen/PolarH10/sensor_2026-10-13_081500.json") == roh.read_bytes()

    with pytest.raises(ValueError):
        export_zip([], tmp_path)


async def _aufnehmen(tmp_path, quelle: SimulatedSource):
    lauf = Messlauf(quelle, backup_basis=tmp_path)
    await lauf.verbinden(SIM_PPI, "Simulator Verity")
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 30:
        await asyncio.sleep(0.01)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    return lauf, ergebnis


@pytest.mark.asyncio
async def test_aufnahme_legt_diagnoseprotokoll_daneben(tmp_path) -> None:
    quelle = SimulatedSource(tempo=60.0, seed=3)
    quelle.protokoll = ["08:15:00 Verbunden (MTU 232)", "08:15:02 Erste PPI-Werte (3 Proben)"]  # type: ignore[attr-defined]
    lauf, ergebnis = await _aufnehmen(tmp_path, quelle)
    assert ergebnis is not None

    text = diagnose_pfad(ergebnis.pfad).read_text(encoding="utf-8")
    assert "Gerät: Simulator Verity [sim:ppi]" in text
    assert f"Aufnahme: {ergebnis.pfad.name}" in text and "PPI-Pakete" in text
    assert text.rstrip().endswith("08:15:02 Erste PPI-Werte (3 Proben)")
    assert [p.name for p in zugehoerige_dateien(ergebnis.pfad)][1].endswith("_diagnose.txt")
    assert lauf.diagnose().startswith("App: Trainingsassistent ")


@pytest.mark.asyncio
async def test_ohne_protokoll_keine_diagnosedatei(tmp_path) -> None:
    lauf, ergebnis = await _aufnehmen(tmp_path, SimulatedSource(tempo=60.0, seed=3))
    assert ergebnis is not None
    assert not diagnose_pfad(ergebnis.pfad).exists()
    assert lauf.diagnose() == ""


# -- S10: Die Bluetooth-Adresse verlässt das Gerät nicht -----------------------------

GOLDEN = Path(__file__).parent / "golden" / "rr"
MAC = "E2:B4:CC:3F:08:44"
UUID = "0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0"


def _mit_adresse(tmp_path: Path, adresse: str | None) -> tuple[Path, Recording]:
    """Eine echte Messung (Golden-Datei) mit ``adresse`` unter ``Messungen/PolarH10``."""
    rec = replace(laden(GOLDEN / "sensor_2026-10-13_000000.json"), adresse=adresse)
    ordner = tmp_path / "Messungen" / "PolarH10"
    return speichern(rec, ordner), rec


@pytest.mark.parametrize("adresse", [MAC, UUID])
def test_exportkopie_der_messdatei_ohne_adresse_sonst_byteidentisch(tmp_path, adresse) -> None:
    """Die Kopie im ZIP ist die Originaldatei ohne den Schlüssel ``adresse`` — geschrieben
    wie von hrv-core, also byteidentisch zu einer Messung, die nie eine Adresse hatte.
    Die Datei auf dem Gerät behält sie."""
    pfad, rec = _mit_adresse(tmp_path, adresse)
    vorher = pfad.read_bytes()
    assert json.loads(vorher)["adresse"] == adresse
    erwartet = speichern(replace(rec, adresse=None), tmp_path / "ohne").read_bytes()

    daten = export_zip(zugehoerige_dateien(pfad), tmp_path)
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        kopie = z.read("Messungen/PolarH10/" + pfad.name)
    assert kopie == erwartet
    doc = json.loads(kopie)
    assert "adresse" not in doc
    assert doc["geraet"] == rec.geraet and len(doc["messungen"]) == len(rec.beats)
    assert pfad.read_bytes() == vorher  # Original unberührt
    assert laden(pfad).adresse == adresse


def test_messdatei_ohne_adresse_bleibt_byteidentisch(tmp_path) -> None:
    """Keine Adresse, nichts zu entfernen: Golden-Dateien (praxis_gui-Stand) und eine von
    hrv-core geschriebene Messung ohne Adresse kommen Byte für Byte so heraus."""
    pfad, _ = _mit_adresse(tmp_path, None)
    for datei in [*sorted(GOLDEN.glob("*.json")), pfad]:
        roh = datei.read_bytes()
        assert "adresse" not in json.loads(roh)
        assert exportkopie(datei) == roh, datei.name
    # Beiwerk, das keine Messdatei ist, ebenso — auch wenn es tiefer eine Adresse nennt
    beiwerk = pfad.with_name(pfad.stem + "_analyzed.json")
    beiwerk.write_bytes(b'{"x": {"adresse": "' + MAC.encode() + b'"}, "n": NaN}')
    assert exportkopie(beiwerk) == beiwerk.read_bytes()
    assert messdatei_ohne_adresse(b"kein json") == b"kein json"
    assert messdatei_ohne_adresse(b"[1, 2]") == b"[1, 2]"


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        (f"Gerät: Unbekannt [{MAC}]", "Gerät: Unbekannt [E2:B4:CC:xx:xx:xx]"),
        (f"verbunden mit {MAC.lower()}", "verbunden mit e2:b4:cc:xx:xx:xx"),
        (f"Adresse {MAC.replace(':', '-')}", "Adresse E2-B4-CC-xx-xx-xx"),
        (f"Gerät: Polar H10 [{UUID}]", "Gerät: Polar H10 [0F1E2D3C-xxxx-xxxx-xxxx-xxxxxxxxxxxx]"),
        ("08:15:00 Verbunden (MTU 232)", "08:15:00 Verbunden (MTU 232)"),
        ("Stand: 2026-10-13T08:15:00+02:00", "Stand: 2026-10-13T08:15:00+02:00"),
        ("Aufnahme: sensor_2026-10-13_081500.json", "Aufnahme: sensor_2026-10-13_081500.json"),
        ("Polar Sense 1A2B3C4D · Akku 85 %", "Polar Sense 1A2B3C4D · Akku 85 %"),
    ],
)
def test_adresse_maskieren(text, erwartet) -> None:
    assert adresse_maskieren(text) == erwartet


def test_diagnoseprotokoll_im_export_maskiert_alle_adressen(tmp_path) -> None:
    """Gerätezeile und Protokollzeilen: jede MAC/UUID wird maskiert — nur in der Kopie."""
    pfad, _ = _mit_adresse(tmp_path, MAC)
    text = diagnose_text(
        {"App": "Trainingsassistent 0.3.8", "Gerät": f"Unbekannt [{MAC}]", "Profil": "polar_h10"},
        [f"08:15:00 Verbinde mit {MAC} …", f"08:15:01 Gefunden: {UUID}", "08:15:02 Verbunden"],
    )
    diagnose_pfad(pfad).write_text(text, encoding="utf-8")

    daten = export_zip(zugehoerige_dateien(pfad), tmp_path)
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        kopie = z.read("Messungen/PolarH10/" + diagnose_pfad(pfad).name).decode("utf-8")
        assert z.getinfo("Messungen/PolarH10/" + pfad.name).compress_type == zipfile.ZIP_DEFLATED
    assert MAC not in kopie and UUID not in kopie and "3F:08:44" not in kopie
    assert "Gerät: Unbekannt [E2:B4:CC:xx:xx:xx]" in kopie
    assert "Verbinde mit E2:B4:CC:xx:xx:xx …" in kopie
    assert "Gefunden: 0F1E2D3C-xxxx-xxxx-xxxx-xxxxxxxxxxxx" in kopie
    assert kopie.endswith("08:15:02 Verbunden\n")
    assert diagnose_pfad(pfad).read_text(encoding="utf-8") == text  # Original vollständig


def test_forschungsexport_nimmt_denselben_weg(tmp_path) -> None:
    """Auch das ZIP der Einheit (`core.forschung`) trägt keine Adresse."""
    pfad, _ = _mit_adresse(tmp_path, MAC)
    diagnose_pfad(pfad).write_text(f"Gerät: X [{MAC}]\n", encoding="utf-8")
    daten = forschung_zip({"format": "einheit-v1"}, zugehoerige_dateien(pfad), tmp_path)
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        texte = {n: z.read(n).decode("utf-8") for n in z.namelist()}
    assert set(texte) == {
        "einheit-v1.json",
        "Messungen/PolarH10/" + pfad.name,
        "Messungen/PolarH10/" + diagnose_pfad(pfad).name,
    }
    assert not any(MAC in t for t in texte.values())
    assert "adresse" not in json.loads(texte["Messungen/PolarH10/" + pfad.name])
