"""Paketquellen (`core/paketquelle.py`): Index lesen, Updates finden, Pakete laden."""

from __future__ import annotations

import hashlib
import json
import urllib.error

import pytest

from trainingsapp.core.pakete import GRUNDAUSSTATTUNG, Paket, paket_json
from trainingsapp.core.paketquelle import (
    INDEX_FORMAT,
    QUELLE_VORGABE,
    IndexEintrag,
    QuellenFehler,
    datei_eintrag,
    fremde_identitaet,
    gebundene_quelle,
    index_laden,
    index_lesen,
    link_lesen,
    paket_laden,
    pruefen,
    quelle_passt,
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
        "sha256": "0" * 64,
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
    with pytest.raises(QuellenFehler, match="unlesbar"):
        index_lesen(_index() | {"version": "1.0"}, "u")


def test_index_lesen_nimmt_nur_https_und_pruefsumme(tmp_path) -> None:
    """K14: Die Paketdatei kommt nur verschlüsselt und nur mit Prüfsumme — sonst holte
    ein fremder Index ungeprüften Inhalt."""
    roh = _index(
        _eintrag(),
        _eintrag(id="http", url="http://x/d.json"),
        _eintrag(id="datei", url="file:///etc/passwd"),
        _eintrag(id="ohne", sha256=""),
        _eintrag(id="kurz", sha256="ab"),
    )
    _name, eintraege = index_lesen(roh, "https://x/i")
    assert [e.id for e in eintraege] == ["p1"]


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
    e_alt = IndexEintrag("p1", "Dehnung", 1, "https://y/d.json", "", 0, "q")
    e_fremd = IndexEintrag("p9", "Yoga", 1, "https://x/y.json", "", 0, "q")
    installiert = Paket(id="p1", name="Dehnung", version=2, quelle="q")
    updates, neue = updates_finden([e_alt, e_neu, e_fremd], [installiert])
    assert updates == [] and [n.id for n in neue] == ["p9"]  # erster Eintrag zählt: 1 < 2
    updates, neue = updates_finden([e_neu, e_alt], [installiert])
    assert [u.eintrag.version for u in updates] == [3]
    from datetime import UTC, datetime

    aus = Paket(id="p1", name="Dehnung", version=2, deaktiviert=datetime.now(UTC), quelle="q")
    assert updates_finden([e_neu], [aus]) == ([], [])
    ohne_version = Paket(id="p1", name="Dehnung", version=None, quelle="q")
    assert [u.eintrag.id for u in updates_finden([e_neu], [ohne_version])[0]] == ["p1"]


def test_updates_nur_aus_der_gebundenen_quelle() -> None:
    """S3 (a): Eine eingetragene Fremdquelle kann kein installiertes Paket „aktualisieren“."""
    eigene = IndexEintrag("p1", "Dehnung", 3, "https://x/d.json", "", 0, "https://x/i")
    fremde = IndexEintrag("p1", "Dehnung", 9, "https://boese/d.json", "", 0, "https://boese/i")
    gebunden = Paket(id="p1", name="Dehnung", version=2, quelle="https://x/i")
    # Die Fremdquelle steht zuerst — sie zählt trotzdem nicht, auch nicht als „gesehen“
    updates, neue = updates_finden([fremde, eigene], [gebunden])
    assert [u.eintrag.quelle_url for u in updates] == ["https://x/i"] and neue == []
    assert updates_finden([fremde], [gebunden]) == ([], [])
    # Per Datei geholt (keine Bindung): keine Quelle darf, auch nicht die Vorgabe
    per_datei = Paket(id="p1", name="Dehnung", version=2)
    from dataclasses import replace

    vorgabe = replace(eigene, quelle_url=QUELLE_VORGABE)
    assert updates_finden([eigene, fremde, vorgabe], [per_datei]) == ([], [])
    assert gebundene_quelle(per_datei) is None and not quelle_passt(QUELLE_VORGABE, per_datei)
    # „Standard“ ohne Bindung: nur die Vorgabequelle; einmal von dort geholt, ist es gebunden
    standard = Paket(id=GRUNDAUSSTATTUNG, name="Standard", version=1)
    s_fremd = replace(fremde, id=GRUNDAUSSTATTUNG, name="Standard")
    s_vorgabe = replace(vorgabe, id=GRUNDAUSSTATTUNG, name="Standard")
    assert updates_finden([s_fremd], [standard]) == ([], [])
    updates, _ = updates_finden([s_fremd, s_vorgabe], [standard])
    assert [u.eintrag.version for u in updates] == [3]
    assert gebundene_quelle(standard) == QUELLE_VORGABE
    anders = Paket(id=GRUNDAUSSTATTUNG, name="Standard", version=3, quelle="https://x/i")
    assert not quelle_passt(QUELLE_VORGABE, anders) and quelle_passt("https://x/i", anders)
    # Nicht installiert: erscheint als neu — von jeder Quelle, die erste zählt
    assert [n.quelle_url for n in updates_finden([fremde, eigene], [])[1]] == ["https://boese/i"]


def test_fremde_identitaet_beim_dateiimport() -> None:
    """S3 (b): Der Hinweis kommt nur, wenn eine Datei ein Paket anderer Herkunft vorgibt."""
    datei = Paket(id="p1", name="Dehnung (neu)")
    assert fremde_identitaet(datei, None) is None
    assert fremde_identitaet(datei, Paket(id="p1", name="Dehnung")) is None  # Datei → Datei
    assert fremde_identitaet(datei, Paket(id="p2", name="Anderes")) is None
    text = fremde_identitaet(datei, Paket(id="p1", name="Dehnung", quelle="https://x/i"))
    assert text == (
        "Diese Datei gibt sich als „Dehnung“ aus (bisher aus https://x/i). "
        "Nur fortfahren, wenn du der Datei vertraust."
    )  # der installierte Name, nicht der aus der Datei
    standard = Paket(id=GRUNDAUSSTATTUNG, name="Standard")
    assert "(bisher mitgeliefert)" in (fremde_identitaet(standard, standard) or "")
    # Aus der gebundenen Quelle: kein Hinweis; aus einer anderen Quelle: Hinweis auf die Quelle
    assert fremde_identitaet(standard, standard, QUELLE_VORGABE) is None
    gebunden = Paket(id="p1", name="Dehnung", quelle="https://x/i")
    assert fremde_identitaet(datei, gebunden, "https://x/i") is None
    assert (fremde_identitaet(datei, gebunden, "https://y/i") or "").startswith(
        "Dieses Paket gibt sich als „Dehnung“ aus (bisher aus https://x/i). Nur fortfahren, "
        "wenn du der Quelle vertraust."
    )


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
    sha = hashlib.sha256(datei).hexdigest()
    andere = IndexEintrag("p2", "Dehnung", 2, "https://x/d.json", sha, 0, "q")
    with pytest.raises(QuellenFehler, match="anderen Paket"):
        paket_laden(andere, lambda url: datei)
    # K23: Datei und Index nennen verschiedene Versionen — sonst „Update“ ohne Ende
    versatz = IndexEintrag("p1", "Dehnung", 3, "https://x/d.json", sha, 0, "q")
    with pytest.raises(QuellenFehler, match="andere Version"):
        paket_laden(versatz, lambda url: datei)
    nix = hashlib.sha256(b"nix").hexdigest()
    with pytest.raises(QuellenFehler, match="keine Paketdatei"):
        paket_laden(IndexEintrag("p1", "D", 2, "u", nix, 0, "q"), lambda url: b"nix")


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
        [Paket(id="p1", name="Dehnung", version=1, quelle="https://x/pakete/index.json")],
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


# ---------------------------------------------------------------------------
# Datei-Link als Quelle, Links erkennen (Ben, 28.10.2026)
# ---------------------------------------------------------------------------


def test_datei_link_wird_beim_pruefen_wie_ein_index_behandelt() -> None:
    v1 = paket_json(Paket(id="p1", name="Dehnung", version=1), seed_inhalt().uebungen[:1])
    v2 = paket_json(Paket(id="p1", name="Dehnung", version=2), seed_inhalt().uebungen[:2])
    antworten = {"https://x/d.json": v2}

    def laden(url: str) -> bytes:
        if url not in antworten:
            raise urllib.error.URLError("unbekannt")
        return antworten[url]

    eintrag, inhalt = datei_eintrag("https://x/d.json", laden)
    assert (eintrag.id, eintrag.version, eintrag.quelle_url) == ("p1", 2, "https://x/d.json")
    assert eintrag.sha256 == hashlib.sha256(v2).hexdigest() and len(inhalt.uebungen) == 2
    # Installiert aus demselben Link, Version 1 → Update; aus einem Index → nicht
    alt = Paket(id="p1", name="Dehnung", version=1, quelle="https://x/d.json", quelle_art="datei")
    ergebnis = pruefen([], [alt], laden)
    assert [u.eintrag.version for u in ergebnis.updates] == [2] and ergebnis.fehler == []
    assert paket_laden(ergebnis.updates[0].eintrag, laden).paket.version == 2
    fremd = Paket(id="p1", name="Dehnung", version=1, quelle="https://x/d.json")  # Index-Bindung
    assert pruefen([], [fremd], laden).updates == []
    kaputt = Paket(
        id="p1", name="Dehnung", version=1, quelle="https://x/weg.json", quelle_art="datei"
    )
    assert pruefen([], [kaputt], laden).fehler == ["Dehnung (https://x/weg.json): unbekannt"]
    assert v1 != v2


def test_link_lesen_erkennt_index_und_paket() -> None:
    datei = paket_json(Paket(id="p1", name="Dehnung", version=1), seed_inhalt().uebungen[:1])
    roh = _index(_eintrag())
    antworten = {"https://x/i.json": json.dumps(roh).encode(), "https://x/d.json": datei}
    art, (name, eintraege) = link_lesen("https://x/i.json", antworten.__getitem__)
    assert art == "index" and name == "Praxis" and [e.id for e in eintraege] == ["p1"]
    art, (eintrag, inhalt) = link_lesen("https://x/d.json", antworten.__getitem__)
    assert art == "paket" and eintrag.quelle_url == "https://x/d.json" and inhalt.paket.id == "p1"
    with pytest.raises(QuellenFehler):
        link_lesen("http://unsicher/x.json", antworten.__getitem__)
    with pytest.raises(QuellenFehler):
        link_lesen("https://x/t.json", lambda _u: b'{"a": 1}')
