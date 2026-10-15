"""Schreibregeln der Aufnahme — Vertrag docs/kompatibilitaet.md, Abschnitt 3a/3b/6a.

Die Regeln stammen aus dem Aufnahmepfad von praxis_gui (`widget.py`,
`_on_hr_received`). Weichen wir davon ab, entstehen Dateien, die zwar gelesen
werden, deren Herzuhr aber anders läuft als in der Praxissoftware.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trainingsapp.hrv_core import recording as recording_mod
from trainingsapp.hrv_core.aufnahme import Aufnahme
from trainingsapp.hrv_core.recording import (
    Recording,
    ist_messdatei,
    laden,
    messordner,
    speichern,
)

START_UTC = datetime(2026, 10, 12, 8, 0, 0, tzinfo=UTC)
START_MONO = 5000.0
GOLDEN = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"

#: Kopf-Reihenfolge des praxis_gui-Schreibers (`_save_recording`), plus unsere
#: Erweiterung `datenqualitaet` hinter `intervall_quelle`.
KOPF_H10 = [
    "behandlung_id",
    "patient_id",
    "datum",
    "geraet",
    "geraet_profil",
    "intervall_quelle",
    "datenqualitaet",
    "simulation",
    "generator_config",
    "schema",
    "analyzed",
    "start_utc",
    "batterie_prozent",
    "ecg_aufzeichnung",
    "ppg_aufzeichnung",
    "titel",
    "notiz",
    "ereignisse",
    "messungen",
]


def h10(**kw) -> Aufnahme:
    return Aufnahme(
        geraet="Polar H10 A1B2C3D4",
        geraet_profil="polar_h10",
        intervall_quelle="ekg_rr",
        start_mono=START_MONO,
        start_utc=START_UTC,
        **kw,
    )


def verity() -> Aufnahme:
    return Aufnahme(
        geraet="Polar Sense 1AB84530",
        geraet_profil="verity_sense",
        intervall_quelle="ppg_ppi",
        start_mono=START_MONO,
        start_utc=START_UTC,
        ppi=True,
    )


# ---------------------------------------------------------------------------
# Herzuhr und Wanduhr
# ---------------------------------------------------------------------------


def test_herzuhr_waechst_nur_zwischen_300_und_2000() -> None:
    """Jede Zeile wird geschrieben, aber t_s läuft nur bei plausiblen RR weiter."""
    a = h10()
    rr = [800, 0, 250, 299, 300, 2000, 2001, 900]
    t = START_MONO
    for x in rr:
        t += 1.0
        a.schlag(x, 70, t, "m")

    assert [b.rr_ms for b in a.beats] == rr  # Rohwerte, nichts verworfen
    assert [b.t_s for b in a.beats] == [0.8, 0.8, 0.8, 0.8, 1.1, 3.1, 3.1, 4.0]


def test_herzuhr_rechnet_in_ganzen_millisekunden() -> None:
    """1000 × 333 ms dürfen keinen Gleitkomma-Drift ergeben."""
    a = h10()
    for i in range(1000):
        a.schlag(333, 180, START_MONO + i * 0.333, "m")
    assert a.beats[-1].t_s == 333.0


def test_wanduhr_und_rueckgerechnete_zeitstempel() -> None:
    """Zwei RR in einem Paket: der letzte trägt die Ankunft ("m"), der erste
    ist um das nachfolgende Intervall zurückgerechnet ("r")."""
    a = h10()
    ankunft = START_MONO + 12.3456
    rr = [800, 820]
    for i, x in enumerate(rr):
        versatz = sum(rr[i + 1 :]) / 1000.0
        a.schlag(x, 74, ankunft - versatz, "r" if i < len(rr) - 1 else "m")

    erster, zweiter = a.beats
    assert (erster.t_wall_s, erster.tw_src) == (11.526, "r")
    assert (zweiter.t_wall_s, zweiter.tw_src) == (12.346, "m")
    assert [b.t_s for b in a.beats] == [0.8, 1.62]


def test_wanduhr_darf_negativ_sein() -> None:
    a = h10()
    assert a.schlag(900, 66, START_MONO - 0.899, "m").t_wall_s == -0.899


def test_unbekannte_zeitherkunft_wird_abgelehnt() -> None:
    with pytest.raises(ValueError):
        h10().schlag(800, 70, START_MONO + 1, "x")


def test_start_ohne_zeitzone_wird_abgelehnt() -> None:
    with pytest.raises(ValueError):
        Aufnahme(
            geraet="H10",
            geraet_profil="polar_h10",
            intervall_quelle="ekg_rr",
            start_mono=0.0,
            start_utc=datetime(2026, 10, 12, 8, 0),
        )


# ---------------------------------------------------------------------------
# PPI-Pakete (Verity Sense)
# ---------------------------------------------------------------------------


def test_verity_paket_schreibt_brauchbare_zeilen_und_rohpaket() -> None:
    """So kommt ein PPI-Paket aus der Geräteschicht an: die brauchbaren
    Intervalle als Schläge (zurückgerechnet über ALLE), das Paket roh dazu."""
    a = verity()
    ppi = [812, 830, 845, 0, 820]
    blocker = [0, 0, 1, 1, 0]
    ankunft = START_MONO + 31.2041
    for i, (x, blockiert) in enumerate(zip(ppi, blocker, strict=True)):
        if blockiert or x == 0:
            continue
        versatz = sum(ppi[i + 1 :]) / 1000.0
        a.schlag(x, 73, ankunft - versatz, "m" if i == len(ppi) - 1 else "r")
    a.ppi_paket(ankunft, ppi, [6, 7, 9, 0, 6], blocker, [True] * 5)

    doc = a.recording().to_dict()
    assert [m["rr_ms"] for m in doc["messungen"]] == [812, 830, 820]
    # 812 liegt 830+845+0+820 ms vor der Ankunft — das blockierte 845 zählt mit.
    assert doc["messungen"][0]["t_wall_s"] == round(31.2041 - 2.495, 3)
    assert doc["ppi_pakete"] == [
        {
            "t_wall_s": 31.204,
            "ppi_ms": [812, 830, 845, 0, 820],
            "fehler_ms": [6, 7, 9, 0, 6],
            "blocker": [0, 0, 1, 1, 0],
            "kontakt": [1, 1, 1, 1, 1],
        }
    ]
    assert doc["intervall_quelle"] == "ppg_ppi"


def test_ppi_schluessel_steht_vor_titel_und_auch_leer() -> None:
    doc = verity().recording().to_dict()
    schluessel = list(doc)
    assert doc["ppi_pakete"] == []
    assert schluessel.index("ppi_pakete") == schluessel.index("ppg_aufzeichnung") + 1
    assert schluessel.index("ppi_pakete") + 1 == schluessel.index("titel")


def test_h10_datei_hat_keinen_ppi_schluessel_und_praxis_reihenfolge() -> None:
    a = h10()
    a.schlag(800, 75, START_MONO + 0.8, "m")
    doc = a.recording().to_dict()
    assert "ppi_pakete" not in doc
    assert list(doc) == KOPF_H10
    assert doc["ppg_aufzeichnung"] is False
    assert list(doc["messungen"][0]) == ["t_s", "t_wall_s", "tw_src", "hf_bpm", "rr_ms"]


def test_ppi_spalten_muessen_gleich_lang_sein() -> None:
    with pytest.raises(ValueError):
        verity().ppi_paket(START_MONO + 1, [800, 810], [5], [0, 0], [1, 1])


def test_ppi_paket_ohne_ppi_schalter_geht_nicht_verloren() -> None:
    a = h10()
    a.ppi_paket(START_MONO + 5, [800], [5], [0], [1])
    assert a.ppi
    assert len(a.recording().to_dict()["ppi_pakete"]) == 1


# ---------------------------------------------------------------------------
# Speichern, Backup, Round-Trip
# ---------------------------------------------------------------------------


def _gefuellt(a: Aufnahme, n: int = 20) -> Aufnahme:
    t = START_MONO
    for i in range(n):
        rr = 800 + (i % 5) * 10
        t += rr / 1000.0
        a.schlag(rr, 75, t, "m")
    a.batterie_prozent = 88
    a.titel = "Ruhe"
    return a


def test_dateiname_und_ordner(tmp_path: Path) -> None:
    ordner = messordner(tmp_path, "PolarH10")
    pfad = _gefuellt(h10()).speichern(ordner)

    assert pfad == tmp_path / "Messungen" / "PolarH10" / "sensor_2026-10-12_080000.json"
    assert ist_messdatei(pfad)
    assert messordner(tmp_path, "PolarH10", simulation=True).name == "Generator"


def test_round_trip_speichern_laden(tmp_path: Path) -> None:
    a = verity()
    _gefuellt(a)
    a.ppi_paket(START_MONO + 3.0, [800, 810], [5, 6], [0, 1], [1, 1])
    pfad = a.speichern(tmp_path)

    zurueck = laden(pfad)
    original = a.recording()
    assert [b.to_dict() for b in zurueck.beats] == [b.to_dict() for b in original.beats]
    assert zurueck.ppi_pakete == original.ppi_pakete
    assert zurueck.geraet_profil == "verity_sense"
    assert zurueck.intervall_quelle == "ppg_ppi"
    assert zurueck.batterie_prozent == 88
    assert zurueck.titel == "Ruhe"
    assert zurueck.datum == a.datum
    assert zurueck.start_utc == START_UTC
    # Erneut geschrieben ist die Datei Byte für Byte dieselbe.
    nochmal = speichern(zurueck, tmp_path / "zwei", dateiname=pfad.name)
    assert nochmal.read_bytes() == pfad.read_bytes()


def test_backup_atomar_kompakt_und_nach_speichern_geloescht(tmp_path: Path) -> None:
    a = _gefuellt(h10())
    backup = a.backup(tmp_path)

    assert backup.name == ".backup_2026-10-12_080000.json"
    assert not ist_messdatei(backup)
    text = backup.read_text(encoding="utf-8")
    assert "\n" not in text  # kompakt
    doc = json.loads(text)
    assert doc["schema"] == "raw-v1"
    assert "hrv" not in doc  # Rohdatenrettung, keine Analyse
    assert len(doc["messungen"]) == 20
    assert not list(tmp_path.glob("*.tmp"))

    # Ein zweites Backup ersetzt das erste.
    a.schlag(800, 75, START_MONO + 30, "m")
    a.backup(tmp_path)
    assert len(json.loads(backup.read_text(encoding="utf-8"))["messungen"]) == 21

    pfad = a.speichern(tmp_path)
    assert pfad.exists()
    assert not backup.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [pfad.name]


def test_abgebrochenes_schreiben_laesst_backup_unversehrt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _gefuellt(h10())
    backup = a.backup(tmp_path)
    vorher = backup.read_bytes()

    def kaputt(*_args, **_kw):
        raise OSError("Datenträger voll")

    monkeypatch.setattr(recording_mod.json, "dump", kaputt)
    with pytest.raises(OSError):
        a.backup(tmp_path)
    with pytest.raises(OSError):
        a.speichern(tmp_path)

    assert backup.read_bytes() == vorher
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob("sensor_*"))


def test_leere_aufnahme_wird_nicht_gespeichert(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        h10().speichern(tmp_path)


def test_simulation_wird_gekennzeichnet(tmp_path: Path) -> None:
    a = _gefuellt(h10(simulation=True))
    doc = json.loads(a.speichern(messordner(tmp_path, "PolarH10", simulation=True)).read_text())
    assert doc["simulation"] is True


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="TZ lässt sich nur unter Unix setzen")
def test_datum_ist_lokal_und_bleibt_beim_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """23:30 UTC ist in Berlin schon der nächste Tag — praxis_gui schreibt das lokale Datum."""
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    try:
        a = Aufnahme(
            geraet="H10",
            geraet_profil="polar_h10",
            intervall_quelle="ekg_rr",
            start_mono=0.0,
            start_utc=datetime(2026, 10, 11, 23, 30, tzinfo=UTC),
        )
        a.schlag(800, 75, 0.8, "m")
        pfad = a.speichern(tmp_path)
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()

    doc = json.loads(pfad.read_text(encoding="utf-8"))
    assert doc["datum"] == "2026-10-12"
    assert doc["start_utc"] == "2026-10-11T23:30:00Z"
    # Der Leser übernimmt das Datum, statt es aus start_utc neu abzuleiten.
    assert laden(pfad).to_dict()["datum"] == "2026-10-12"


def test_golden_datei_round_trip_behaelt_datum_und_reihenfolge(tmp_path: Path) -> None:
    original = json.loads(GOLDEN.read_text(encoding="utf-8"))
    rec = laden(GOLDEN)
    doc = json.loads(speichern(rec, tmp_path, dateiname=GOLDEN.name).read_text(encoding="utf-8"))
    assert doc["datum"] == original["datum"]
    assert doc["messungen"] == original["messungen"]


@pytest.mark.parametrize(
    ("name", "erwartet"),
    [
        ("sensor_2026-10-12_080000.json", True),
        ("sensor_2026-10-12_080000_ppg.json", False),
        ("sensor_2026-10-12_080000_ecg.json", False),
        ("sensor_2026-10-12_080000_analyzed.json", False),
        ("sensor_2026-10-12_080000__c02.json", False),
        (".backup_2026-10-12_080000.json", False),
        ("sensor_2026-10-12_080000.json.tmp", False),
    ],
)
def test_ist_messdatei_schliesst_beiwerk_aus(name: str, erwartet: bool) -> None:
    assert ist_messdatei(name) is erwartet


def test_recording_ohne_ppi_bleibt_ohne_schluessel() -> None:
    assert "ppi_pakete" not in Recording().to_dict()


# ---------------------------------------------------------------------------
# Liegengebliebene Backups finden und lesen (Vertrag 6a, Wiederherstellung)
# ---------------------------------------------------------------------------


def test_backup_mit_zusatz_lesen_laesst_messdatei_sauber(tmp_path: Path) -> None:
    from trainingsapp.hrv_core.aufnahme import WIEDERHERSTELLUNG, backup_lesen

    a = _gefuellt(h10())
    zusatz = {"subject_id": "p1", "grenzen": [[{"t": 1.0}, "Ruhe", False]]}
    backup = a.backup(tmp_path, zusatz=zusatz)
    doc = json.loads(backup.read_text(encoding="utf-8"))
    assert doc[WIEDERHERSTELLUNG] == zusatz
    assert list(doc)[-1] == WIEDERHERSTELLUNG  # hinter `messungen`, Kopf unverändert

    rec, gelesen = backup_lesen(backup)
    assert gelesen == zusatz
    assert WIEDERHERSTELLUNG not in rec.extra  # darf nie in die Messdatei
    assert len(rec.beats) == 20 and rec.titel == "Ruhe"
    assert WIEDERHERSTELLUNG not in rec.to_dict()

    # Ohne Zusatz (älteres Backup, praxis_gui): leerer Zusatz, Daten vollständig
    ohne = a.backup(tmp_path / "ohne")
    rec2, leer = backup_lesen(ohne)
    assert leer == {} and len(rec2.beats) == 20


def test_backup_lesen_weist_kaputte_datei_ab(tmp_path: Path) -> None:
    from trainingsapp.hrv_core.aufnahme import backup_lesen

    kaputt = tmp_path / ".backup_2026-10-12_080000.json"
    kaputt.write_text('{"schema": "raw-v1", "messungen": [', encoding="utf-8")
    with pytest.raises(ValueError):
        backup_lesen(kaputt)
    kaputt.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError):
        backup_lesen(kaputt)


def test_backups_finden_nur_in_geraeteordnern(tmp_path: Path) -> None:
    from trainingsapp.hrv_core.aufnahme import backups_finden

    messungen = tmp_path / "Messungen"
    assert backups_finden(messungen) == []  # Verzeichnis fehlt
    b1 = _gefuellt(h10()).backup(messordner(tmp_path, "PolarH10"))
    b2 = _gefuellt(verity()).backup(messordner(tmp_path, "VeritySense", simulation=True))
    fertig = _gefuellt(h10())  # ordentlich gespeichert: Backup wieder weg
    fertig.backup(messordner(tmp_path, "Brustgurt"))
    fertig.speichern(messordner(tmp_path, "Brustgurt"))
    (messungen / "PolarH10" / ".backup_2026-10-12_090000.json.tmp").write_text("{}")
    (messungen / ".backup_2026-10-12_100000.json").write_text("{}")  # falsche Ebene
    assert backups_finden(messungen) == sorted([b1, b2])
    assert all(not ist_messdatei(p) for p in backups_finden(messungen))
