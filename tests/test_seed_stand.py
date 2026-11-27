"""Der Seed ist der veröffentlichte Stand von „Standard“ — mit seinen Dateien (Ben, 27.11.2026).

Bis dahin lieferte die App Version 5 aus, auf dem Server lag 0.1.0 mit Dateien: Jede frische
Installation meldete sofort ein Update. Hier ohne Netz: Der Seed lässt sich bauen, der Start legt
die Dateien in die Paketablage, und `scripts/seed_pruefen.py` erkennt gleich und ungleich.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

from trainingsapp.core.models import MediaSource
from trainingsapp.core.paketdatei import medienlisten
from trainingsapp.core.pakete import GRUNDAUSSTATTUNG, PaketFehler
from trainingsapp.core.paketquelle import QUELLE_VORGABE, QuellenFehler
from trainingsapp.data.db import oeffnen
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.paketmedien import Paketablage
from trainingsapp.data.repositories import ExerciseRepo
from trainingsapp.data.seed import SEED_DATEI, seed_einspielen, seed_id, seed_inhalt
from trainingsapp.paket_werkzeug import bauen

SKRIPT = Path(__file__).resolve().parent.parent / "scripts" / "seed_pruefen.py"


@pytest.fixture(scope="module")
def seed_pruefen():
    spec = importlib.util.spec_from_file_location("seed_pruefen", SKRIPT)
    assert spec is not None and spec.loader is not None
    modul = importlib.util.module_from_spec(spec)
    sys.modules["seed_pruefen"] = modul
    spec.loader.exec_module(modul)
    yield modul
    sys.modules.pop("seed_pruefen", None)


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    yield verbindung
    verbindung.close()


@pytest.fixture
def ablage(con, tmp_path):
    return Paketablage(con, tmp_path / "Medien" / "Pakete")


def _genannte_dateien() -> list[str]:
    roh = tomllib.loads(SEED_DATEI.read_text(encoding="utf-8"))
    return [
        str(eintrag["datei"])
        for liste in medienlisten(roh)
        for eintrag in liste
        if isinstance(eintrag, dict) and "datei" in eintrag
    ]


def _aelter(tmp_path: Path) -> Path:
    """„Standard“ in einer älteren Version: ohne Dateien, ohne die Planke."""
    roh = tomllib.loads(SEED_DATEI.read_text(encoding="utf-8"))
    roh["paket"]["version"] = "0.0.5"
    roh["exercises"] = [e for e in roh["exercises"] if e["key"] != "planke"]
    for uebung in roh["exercises"]:
        if any("datei" in m for m in uebung.get("media", [])):
            del uebung["media"]
    datei = tmp_path / "standard_alt.json"
    datei.write_text(json.dumps(roh), encoding="utf-8")
    return datei


def _paketmedien(con, key: str) -> list[str]:
    uebung = ExerciseRepo(con).laden(seed_id(key))
    return [m.uri for m in uebung.media if m.source is MediaSource.PAKET]


# ---------------------------------------------------------------------------
# Die Kopie im Repo
# ---------------------------------------------------------------------------


def test_seed_nennt_dateien_und_sie_liegen_daneben() -> None:
    """Der Seed hat Dateien — sonst prüften die Tests hier nichts —, und jede liegt im Repo."""
    dateien = _genannte_dateien()
    assert dateien
    for rel in dateien:
        assert (SEED_DATEI.parent / rel).is_file(), rel


def test_seed_laesst_sich_bauen_wie_ein_veroeffentlichtes_paket(tmp_path) -> None:
    """Das Werkzeug baut aus dem Seed die ZIP, die auf dem Server liegt — zweimal dieselbe."""
    eins = bauen(SEED_DATEI, tmp_path / "a")
    zwei = bauen(SEED_DATEI, tmp_path / "b")
    assert eins.suffix == ".zip"
    assert eins.read_bytes() == zwei.read_bytes()
    with zipfile.ZipFile(eins) as z:
        namen = z.namelist()
    assert "paket.json" in namen
    assert len([n for n in namen if n.startswith("medien/")]) == len(set(_genannte_dateien()))


# ---------------------------------------------------------------------------
# Der Start
# ---------------------------------------------------------------------------


def test_erster_start_legt_die_dateien_in_die_ablage(con, ablage) -> None:
    seed_einspielen(con, ablage=ablage)
    paket = PaketRepo(con).laden(GRUNDAUSSTATTUNG)
    assert paket is not None and paket.version == seed_inhalt().paket.version
    uris = _paketmedien(con, "kniebeuge")
    assert len(uris) == 2
    assert all(ablage.vorhanden(uri) for uri in uris)
    assert ablage.fehlende(uris) == []


def test_zweiter_start_aendert_nichts_und_holt_fehlendes_zurueck(con, ablage) -> None:
    seed_einspielen(con, ablage=ablage)
    uris = _paketmedien(con, "kniebeuge")
    pfade = [ablage.pfad(uri) for uri in uris]
    zeiten = [p.stat().st_mtime_ns for p in pfade]
    assert seed_einspielen(con, ablage=ablage) == 0
    assert [p.stat().st_mtime_ns for p in pfade] == zeiten  # nicht neu geschrieben
    assert _paketmedien(con, "kniebeuge") == uris
    pfade[0].unlink()  # von außen gelöscht
    assert seed_einspielen(con, ablage=ablage) == 0
    assert pfade[0].is_file()


def test_update_vom_aelteren_seed_bringt_dateien_und_laesst_eigenes(con, ablage, tmp_path) -> None:
    """App-Update: Auf dem Gerät liegt ein älterer „Standard“. Der Start bringt den neuen —
    Dateien und neue Übungen kommen dazu, was die Person geändert hat, bleibt."""
    seed_einspielen(con, _aelter(tmp_path), ablage=ablage)
    repo = ExerciseRepo(con)
    assert _paketmedien(con, "kniebeuge") == []
    assert repo.laden(seed_id("planke")) is None
    knie = repo.laden(seed_id("kniebeuge"))
    knie.name = "Meine Kniebeuge"
    repo.speichern(knie)

    neu = seed_einspielen(con, ablage=ablage)

    assert neu == 1  # die Planke
    assert PaketRepo(con).laden(GRUNDAUSSTATTUNG).version == seed_inhalt().paket.version
    assert repo.laden(seed_id("kniebeuge")).name == "Meine Kniebeuge"
    uris = _paketmedien(con, "kniebeuge")
    assert len(uris) == 2 and all(ablage.vorhanden(uri) for uri in uris)


def test_ohne_ablage_kommt_standard_ohne_dateien(con) -> None:
    """Tests und Werkzeuge ohne Ablage: Die Übungen sind da, die Einträge mit Datei fehlen."""
    seed_einspielen(con)
    assert ExerciseRepo(con).laden(seed_id("kniebeuge")) is not None
    assert _paketmedien(con, "kniebeuge") == []


# ---------------------------------------------------------------------------
# scripts/seed_pruefen.py
# ---------------------------------------------------------------------------


def _index(version: int | None, sha256: str, groesse: int, paket_id: str = GRUNDAUSSTATTUNG):
    daten = json.dumps(
        {
            "format": "trainingsapp-paketindex",
            "version": 1,
            "quelle": {"name": "Probe"},
            "pakete": [
                {
                    "id": paket_id,
                    "name": "Standard",
                    "version": version,
                    "url": QUELLE_VORGABE.replace("index.json", "uebungspaket_Standard.zip"),
                    "sha256": sha256,
                    "bytes": groesse,
                    "format_version": 4,
                }
            ],
        }
    ).encode()
    return lambda url: daten


def test_pruefen_gleich(seed_pruefen) -> None:
    _, version, sha256, groesse = seed_pruefen.seed_stand()
    code, meldung = seed_pruefen.pruefen(laden=_index(version, sha256, groesse))
    assert code == 0, meldung
    assert "Gleich" in meldung


def test_pruefen_andere_version(seed_pruefen) -> None:
    _, version, sha256, groesse = seed_pruefen.seed_stand()
    code, meldung = seed_pruefen.pruefen(laden=_index(version + 1, sha256, groesse))
    assert code == 1
    assert "die Version" in meldung


def test_pruefen_anderer_inhalt_bei_gleicher_version(seed_pruefen) -> None:
    _, version, _, groesse = seed_pruefen.seed_stand()
    code, meldung = seed_pruefen.pruefen(laden=_index(version, "0" * 64, groesse))
    assert code == 1
    assert "der Inhalt" in meldung


def test_pruefen_ohne_netz_ist_nicht_geprueft(seed_pruefen) -> None:
    def kein_netz(url: str) -> bytes:
        raise QuellenFehler("kein Netz")

    code, meldung = seed_pruefen.pruefen(laden=kein_netz)
    assert code == 2
    assert "Nicht geprüft" in meldung


def _quelle(tmp_path: Path, dateien: dict[str, bytes], version: str = "0.2.0") -> Path:
    """Eine kleine Paketdatei „Standard“ mit Dateien daneben, wie im Inhalte-Repo."""
    ordner = tmp_path / "quelle"
    medien = ", ".join(f'{{ datei = "{rel}", title = "Bild" }}' for rel in dateien)
    for rel, daten in dateien.items():
        (ordner / rel).parent.mkdir(parents=True, exist_ok=True)
        (ordner / rel).write_bytes(daten)
    ordner.mkdir(exist_ok=True)
    toml = ordner / "standard.toml"
    toml.write_text(
        'format = "trainingsapp-uebungspaket"\nversion = 1\n\n'
        f'[paket]\nid = "{GRUNDAUSSTATTUNG}"\nname = "Standard"\nversion = "{version}"\n\n'
        '[[exercises]]\nkey = "kniebeuge"\nname = "Kniebeuge"\nspec = "halten"\n'
        f"media = [{medien}]\n",
        encoding="utf-8",
    )
    return toml


def test_uebernehmen_legt_toml_und_dateien_hin_und_raeumt_auf(seed_pruefen, tmp_path) -> None:
    quelle = _quelle(tmp_path, {"medien/standard/a.png": b"a", "medien/standard/b.png": b"b"})
    ziel = tmp_path / "seed" / "standard.toml"
    zeilen = seed_pruefen.uebernehmen(quelle, ziel)
    assert zeilen == [
        "neu: standard.toml",
        "neu: medien/standard/a.png",
        "neu: medien/standard/b.png",
    ]
    assert ziel.read_bytes() == quelle.read_bytes()
    assert (ziel.parent / "medien/standard/b.png").read_bytes() == b"b"
    assert seed_pruefen.uebernehmen(quelle, ziel) == []  # schon gleich

    quelle = _quelle(tmp_path, {"medien/standard/a.png": b"A"}, "0.3.0")  # b fällt weg, a neu
    (tmp_path / "quelle/medien/standard/b.png").unlink()
    zeilen = seed_pruefen.uebernehmen(quelle, ziel)
    assert zeilen == [
        "geändert: standard.toml",
        "geändert: medien/standard/a.png",
        "entfernt: medien/standard/b.png",
    ]
    assert not (ziel.parent / "medien/standard/b.png").exists()


def test_uebernehmen_weist_fremdes_und_fehlendes_ab(seed_pruefen, tmp_path) -> None:
    ziel = tmp_path / "seed" / "standard.toml"
    quelle = _quelle(tmp_path, {"medien/standard/a.png": b"a"})
    (tmp_path / "quelle/medien/standard/a.png").unlink()
    with pytest.raises(PaketFehler, match="Datei fehlt"):
        seed_pruefen.uebernehmen(quelle, ziel)
    quelle = _quelle(tmp_path, {"bilder/a.png": b"a"})
    with pytest.raises(PaketFehler, match="außerhalb von medien/"):
        seed_pruefen.uebernehmen(quelle, ziel)
    quelle.write_text(
        quelle.read_text(encoding="utf-8").replace(
            GRUNDAUSSTATTUNG, "1" * 8 + GRUNDAUSSTATTUNG[8:]
        ),
        encoding="utf-8",
    )
    with pytest.raises(PaketFehler, match="nicht das Paket"):
        seed_pruefen.uebernehmen(quelle, ziel)
    assert not ziel.exists()  # nichts geändert


def test_pruefen_paket_fehlt_im_index(seed_pruefen) -> None:
    _, version, sha256, groesse = seed_pruefen.seed_stand()
    anderes = "11111111-1111-5111-8111-111111111111"
    code, meldung = seed_pruefen.pruefen(laden=_index(version, sha256, groesse, anderes))
    assert code == 2
    assert "nennt das Paket nicht" in meldung
