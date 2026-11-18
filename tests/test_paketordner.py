"""Pakete in Unterordnern (Ben, 18.11.2026: im Inhalte-Repo je Paket ein Ordner,
``pakete/qigong/qigong_basis.toml`` neben ``pakete/standard.toml``): Der Lader am Rechner, die
Verweise auf andere Pakete, das ``braucht`` beim Bauen, ``einlesen`` und die Basis aus der
git-Geschichte finden die Pakete auch dort — ``medien/`` und ``einlesen/`` sind keine Pakete."""

from __future__ import annotations

import json
import subprocess

from trainingsapp.core.paketdatei import nachbar_namen, nachbar_tomls, paketdateien, paketwurzel
from trainingsapp.core.pakete import GRUNDAUSSTATTUNG, paket_id
from trainingsapp.core.paketversion import version_zahl
from trainingsapp.data.db import oeffnen
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.seed import SEED_DATEI, pakete_aus_ordner
from trainingsapp.paket_einlesen import eigenes_ziel
from trainingsapp.paket_werkzeug import _basis_aus_git, bauen, pruefen


def _paket(name: str, version: str = "1.0.0") -> str:
    return (
        f'[paket]\nname = "{name}"\nversion = "{version}"\n\n[[exercises]]\nkey = "baum"\n'
        'name = "Baum"\ntypen = ["Qigong"]\nspec = "halten"\n'
    )


FUER_A = """[paket]
name = "Für A."
version = "1.0.0"

[[exercises]]
key = "kranich"
name = "Kranich"
description = "Auf einem Bein."

[[plaene]]
key = "morgens"
name = "Morgens"
uebungen = [{ uebung = "kranich" }, { uebung = "kniebeuge", paket = "Standard" }]
"""


def _git(ordner, *args: str) -> None:
    subprocess.run(
        [
            *("git", "-C", str(ordner), "-c", "user.name=Test"),
            *("-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args),
        ],
        check=True,
        capture_output=True,
    )


def test_paketwurzel_und_paketdateien(tmp_path) -> None:
    """Unter ``pakete/`` zählt jede Ebene; Medien, Merkdateien, Zugangsdateien und Verstecktes
    nicht. Über die Wurzel eines git-Repos geht die Suche nicht hinaus, und ohne ``pakete/``
    bleibt sie im Ordner der Datei."""
    pakete = tmp_path / "pakete"
    qigong = pakete / "qigong" / "qigong_basis.toml"
    for datei in (
        pakete / "standard.toml",
        qigong,
        pakete / "qigong" / "qigong_basis.zugang.json",
        pakete / "qigong" / "einlesen" / "qigong_basis.json",
        pakete / "qigong" / "medien" / "qigong_basis" / "notiz.toml",
        pakete / ".versteckt" / "alt.toml",
        pakete / "qigong" / "qigong_basis.zugangskarte.txt",
    ):
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text("", encoding="utf-8")
    assert paketwurzel(qigong) == pakete
    assert paketwurzel(pakete / "standard.toml") == pakete
    assert paketdateien(pakete, (".toml", ".json", ".zip")) == [qigong, pakete / "standard.toml"]
    assert nachbar_tomls(qigong) == [qigong, pakete / "standard.toml"]

    repo = pakete / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "entwuerfe").mkdir()
    assert paketwurzel(repo / "entwuerfe" / "vorlage.toml") is None, "nicht über das Repo hinaus"

    downloads = tmp_path / "downloads"
    (downloads / "tief").mkdir(parents=True)
    (downloads / "x.toml").write_text("", encoding="utf-8")
    (downloads / "tief" / "y.toml").write_text("", encoding="utf-8")
    assert paketwurzel(downloads / "x.toml") is None
    assert nachbar_tomls(downloads / "x.toml") == [downloads / "x.toml"]


def test_verweis_und_braucht_ueber_unterordner(tmp_path) -> None:
    """``paket = "Standard"`` in ``pakete/fuer_a/fuer_a.toml`` findet ``pakete/standard.toml``:
    `pruefen` folgt dem Verweis, `bauen` schreibt, was das Paket braucht."""
    pakete = tmp_path / "pakete"
    (pakete / "fuer_a").mkdir(parents=True)
    (pakete / "standard.toml").write_text(SEED_DATEI.read_text("utf-8"), encoding="utf-8")
    datei = pakete / "fuer_a" / "fuer_a.toml"
    datei.write_text(FUER_A, encoding="utf-8")
    assert nachbar_namen(datei)["standard"] == GRUNDAUSSTATTUNG
    fehler, hinweise = pruefen(datei, symbole=None)
    assert fehler == [] and not any("Verweis" in h or "prüfbar" in h for h in hinweise)
    basis = "https://example.invalid/pakete"
    gebaut = json.loads(bauen(datei, tmp_path / "dist", basis_url=basis).read_text("utf-8"))
    braucht = {v["name"]: v for v in gebaut["paket"]["braucht"]}
    assert braucht["Standard"]["quelle"] == f"{basis}/uebungspaket_Standard.json"


def test_lader_liest_unterordner(tmp_path) -> None:
    """``TRAININGSAPP_PAKETE`` (``./start.sh`` im Inhalte-Repo): Pakete in Unterordnern kommen
    an; die Merkdatei von ``einlesen`` und die Zugangsdatei gehen nicht als Paket durch."""
    ordner = tmp_path / "pakete"
    (ordner / "qigong" / "einlesen").mkdir(parents=True)
    (ordner / "qigong" / "qigong.toml").write_text(_paket("Qigong"), encoding="utf-8")
    (ordner / "qigong" / "qigong.zugang.json").write_text('{"ordner": "a", "code": "b"}', "utf-8")
    (ordner / "qigong" / "einlesen" / "qigong.json").write_text('{"eigenes_paket": "x"}', "utf-8")
    (ordner / "anderes.toml").write_text(_paket("Anderes"), encoding="utf-8")
    con = oeffnen(tmp_path / "app.db")
    try:
        assert pakete_aus_ordner(con, ordner) == []
        ids = {p.id for p, _ in PaketRepo(con).alle()}
    finally:
        con.close()
    assert {paket_id("Qigong"), paket_id("Anderes")} <= ids


def test_basis_aus_git_folgt_dem_umzug(tmp_path) -> None:
    """`uebernehmen` sucht die Fassung eines Exports in der git-Geschichte der TOML — auch aus
    der Zeit, bevor sie in ihren Unterordner umzog (``git mv``)."""
    repo = tmp_path / "inhalte"
    (repo / "pakete" / "qigong").mkdir(parents=True)
    _git(repo, "init", "-q")
    alt = repo / "pakete" / "qigong.toml"
    alt.write_text(_paket("Qigong", "1.0.0"), encoding="utf-8")
    _git(repo, "add", "pakete/qigong.toml")
    _git(repo, "commit", "-q", "-m", "1.0.0")
    _git(repo, "mv", "pakete/qigong.toml", "pakete/qigong/qigong.toml")
    _git(repo, "commit", "-q", "-m", "umgezogen")
    neu = repo / "pakete" / "qigong" / "qigong.toml"
    neu.write_text(_paket("Qigong", "1.1.0"), encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "1.1.0")

    gefunden = _basis_aus_git(neu, version_zahl("1.0.0"), None, {}, tmp_path / "arbeit")
    assert gefunden is not None and "Version 1.0.0" in gefunden[2]
    assert _basis_aus_git(neu, version_zahl("1.1.0"), None, {}, tmp_path / "arbeit2") is not None


def test_einlesen_kennt_entwurf_aus_anderem_unterordner(tmp_path) -> None:
    """Ein Export, der schon nach ``pakete/fuer_a/fuer_a.toml`` eingelesen wurde, wird nicht
    unbemerkt ein zweites Paket in einem anderen Ordner."""
    pakete = tmp_path / "pakete"
    (pakete / "fuer_a" / "einlesen").mkdir(parents=True)
    (pakete / "fuer_a" / "einlesen" / "fuer_a.json").write_text(
        json.dumps({"eigenes_paket": "e1f2"}), encoding="utf-8"
    )
    export = tmp_path / "export.json"
    export.write_text(json.dumps({"paket": {"id": "e1f2", "name": "Für A."}}), encoding="utf-8")
    assert eigenes_ziel(export, pakete / "neu" / "neu.toml") == pakete / "fuer_a" / "fuer_a.toml"
