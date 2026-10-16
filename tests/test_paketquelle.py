"""Paketquellen (`core/paketquelle.py`): Index lesen, Updates finden, Pakete laden."""

from __future__ import annotations

import hashlib
import json
import urllib.error

import pytest

from trainingsapp.core.pakete import Paket, paket_json
from trainingsapp.core.paketquelle import (
    INDEX_FORMAT,
    QUELLE_VORGABE,
    IndexEintrag,
    QuellenFehler,
    index_laden,
    index_lesen,
    paket_laden,
    pruefen,
    updates_finden,
    url_pruefen,
)
from trainingsapp.data.seed import seed_inhalt
from trainingsapp.paket_werkzeug import index


def _index(*pakete: dict) -> dict:
    return {
        "format": INDEX_FORMAT,
        "version": 1,
        "quelle": {"name": "Praxis"},
        "pakete": list(pakete),
    }


def _eintrag(**extra) -> dict:
    return {
        "id": "p1",
        "name": "Dehnung",
        "version": 2,
        "url": "https://x/d.json",
        "sha256": "",
        "bytes": 10,
    } | extra


def test_index_lesen_prueft_format_und_ueberspringt_unvollstaendiges() -> None:
    name, eintraege = index_lesen(_index(_eintrag(), {"name": "ohne id"}, "unsinn"), "https://x/i")
    assert name == "Praxis" and [e.id for e in eintraege] == ["p1"]
    assert eintraege[0].quelle_url == "https://x/i" and eintraege[0].quelle_name == "Praxis"
    with pytest.raises(QuellenFehler, match="kein Paketindex"):
        index_lesen({"format": "anderes"}, "u")
    with pytest.raises(QuellenFehler, match="neuer als diese App"):
        index_lesen(_index() | {"version": 9}, "u")
    with pytest.raises(QuellenFehler, match="keine Paketliste"):
        index_lesen(_index() | {"pakete": "x"}, "u")


def test_index_laden_meldet_netzfehler_und_unsinn() -> None:
    def offline(url: str) -> bytes:
        raise urllib.error.URLError("offline")

    with pytest.raises(QuellenFehler, match="offline"):
        index_laden("https://x/i", offline)

    def vierhundertvier(url: str) -> bytes:
        raise urllib.error.HTTPError(url, 404, "nope", {}, None)  # type: ignore[arg-type]

    with pytest.raises(QuellenFehler, match="HTTP 404"):
        index_laden("https://x/i", vierhundertvier)
    with pytest.raises(QuellenFehler, match="kein JSON"):
        index_laden("https://x/i", lambda url: b"<html>")
    with pytest.raises(QuellenFehler, match="zu groß"):
        index_laden("https://x/i", lambda url: b"x" * 2_000_000)


def test_updates_finden_nur_aktive_und_nur_nach_oben() -> None:
    e_neu = IndexEintrag("p1", "Dehnung", 3, "https://x/d.json", "", 0, "q")
    e_alt = IndexEintrag("p1", "Dehnung", 1, "https://y/d.json", "", 0, "q2")
    e_fremd = IndexEintrag("p9", "Yoga", 1, "https://x/y.json", "", 0, "q")
    installiert = Paket(id="p1", name="Dehnung", version=2)
    updates, neue = updates_finden([e_alt, e_neu, e_fremd], [installiert])
    assert updates == [] and [n.id for n in neue] == ["p9"]  # erste Quelle zählt: 1 < 2
    updates, neue = updates_finden([e_neu, e_alt], [installiert])
    assert [u.eintrag.version for u in updates] == [3]
    from datetime import UTC, datetime

    aus = Paket(id="p1", name="Dehnung", version=2, deaktiviert=datetime.now(UTC))
    assert updates_finden([e_neu], [aus]) == ([], [])
    ohne_version = Paket(id="p1", name="Dehnung", version=None)
    assert [u.eintrag.id for u in updates_finden([e_neu], [ohne_version])[0]] == ["p1"]


def test_paket_laden_prueft_pruefsumme_und_id(tmp_path) -> None:
    datei = paket_json(Paket(id="p1", name="Dehnung", version=2), [seed_inhalt().uebungen[0]])
    gut = IndexEintrag(
        "p1", "Dehnung", 2, "https://x/d.json", hashlib.sha256(datei).hexdigest(), len(datei), "q"
    )
    inhalt = paket_laden(gut, lambda url: datei)
    assert inhalt.paket.id == "p1" and len(inhalt.uebungen) == 1
    falsch = IndexEintrag("p1", "Dehnung", 2, "https://x/d.json", "00" * 32, len(datei), "q")
    with pytest.raises(QuellenFehler, match="Prüfsumme"):
        paket_laden(falsch, lambda url: datei)
    andere = IndexEintrag("p2", "Dehnung", 2, "https://x/d.json", "", 0, "q")
    with pytest.raises(QuellenFehler, match="anderen Paket"):
        paket_laden(andere, lambda url: datei)
    with pytest.raises(QuellenFehler, match="keine Paketdatei"):
        paket_laden(IndexEintrag("p1", "D", 2, "u", "", 0, "q"), lambda url: b"nix")


def test_pruefen_sammelt_fehler_je_quelle_und_passt_zum_werkzeug(tmp_path) -> None:
    """Der Index aus `trainingsapp-paket index` ist genau das, was die App liest."""
    datei = tmp_path / "uebungspaket_Dehnung.json"
    datei.write_bytes(
        paket_json(Paket(id="p1", name="Dehnung", version=2), seed_inhalt().uebungen[:2])
    )
    roh = index([datei], "https://x/pakete", quelle="Praxis")
    antworten = {
        "https://x/pakete/index.json": json.dumps(roh).encode(),
        "https://x/pakete/" + datei.name: datei.read_bytes(),
    }

    def laden(url: str) -> bytes:
        if url not in antworten:
            raise urllib.error.URLError("unbekannt")
        return antworten[url]

    ergebnis = pruefen(
        ["https://kaputt/index.json", "https://x/pakete/index.json"],
        [Paket(id="p1", name="Dehnung", version=1)],
        laden,
    )
    assert ergebnis.fehler == ["https://kaputt/index.json: unbekannt"]
    assert [u.eintrag.version for u in ergebnis.updates] == [2] and ergebnis.neue == []
    inhalt = paket_laden(ergebnis.updates[0].eintrag, laden)
    assert [u.name for u in inhalt.uebungen] == [u.name for u in seed_inhalt().uebungen[:2]]
    assert url_pruefen("ftp://x") and url_pruefen("https://ok.de/i.json") is None


def test_vorgabe_besteht_die_eigene_adresspruefung() -> None:
    # Die App bringt die Quelle mit; eine Adresse, die url_pruefen ablehnt, könnte die
    # Person in den Einstellungen nicht wieder eintragen, nachdem sie sie entfernt hat.
    assert QUELLE_VORGABE.startswith("https://") and url_pruefen(QUELLE_VORGABE) is None
