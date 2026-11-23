"""Netz im Browser (`ui/browsernetz.py`, Ben, 23.11.2026; `docs/plan_web_pakete.md`).

Der echte Zugang (`fetch`, Nachladen von ``cryptography``) läuft nur in Pyodide und ist im
Browser gemessen; hier steht ein nachgebauter. Geprüft wird, was die App selbst entscheidet:
welche Adressen sie holt, welche nie, was der Kern bei einem Fehler sieht — und dass scrypt aus
``cryptography`` dieselben Schlüssel liefert wie `hashlib`.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import urllib.error

import pytest

from trainingsapp.core import privat
from trainingsapp.core.pakete import paket_lesen
from trainingsapp.core.paketquelle import (
    DATEI,
    QuellenFehler,
    ZugangNoetig,
    link_lesen,
    pruefen,
    stand_json,
    stand_url,
)
from trainingsapp.ui import browsernetz
from trainingsapp.ui.browsernetz import MAX_ADRESSEN, NUR_EIGENER, vorab

URSPRUNG = "https://praxis.example"
URL = f"{URSPRUNG}/pakete/p/7Hq3vX9aBcDeFgHiJkLmNo/paket.json"
CODE = "K7QM9XA2"


class Netz:
    """Der Server als Tabelle Adresse → Bytes; merkt, was gefragt wurde."""

    def __init__(self, dateien: dict[str, bytes] | None = None) -> None:
        self.dateien = dateien or {}
        self.gefragt: list[str] = []
        self.krypto = 0
        self.ursprung = URSPRUNG

    async def holen(self, url: str, grenze: int) -> bytes:
        self.gefragt.append(url)
        if url not in self.dateien:
            raise urllib.error.HTTPError(url, 404, "", None, None)  # type: ignore[arg-type]
        if len(self.dateien[url]) > grenze:
            raise OSError(browsernetz.ZU_GROSS)
        return self.dateien[url]

    async def krypto_laden(self) -> None:
        self.krypto += 1


def _paket(version: int = 1, name: str = "Für Max") -> bytes:
    roh = {
        "paket": {"name": name, "version": version},
        "exercises": [{"key": "a", "name": f"Übung v{version}", "description": "Langsam."}],
    }
    return json.dumps(roh, ensure_ascii=False).encode("utf-8")


# -- vorab: erst holen, dann lesen -------------------------------------------------------------


def test_link_lesen_holt_genau_die_eine_adresse() -> None:
    netz = Netz({URL: _paket()})
    art, (eintrag, inhalt) = asyncio.run(vorab(functools.partial(link_lesen, URL), netz))
    assert art == "paket" and inhalt.paket.name == "Für Max"
    assert eintrag.sha256 == hashlib.sha256(_paket()).hexdigest()
    assert netz.gefragt == [URL]  # einmal, nicht je Runde neu


def test_privates_paket_fragt_erst_nach_dem_code_und_oeffnet_dann() -> None:
    netz = Netz({URL: privat.verschluesseln(_paket(), CODE)})
    with pytest.raises(ZugangNoetig):
        asyncio.run(vorab(functools.partial(link_lesen, URL), netz))
    _, (_, inhalt) = asyncio.run(vorab(functools.partial(link_lesen, URL, code=CODE), netz))
    assert inhalt.paket.name == "Für Max" and inhalt.code == CODE


def test_fehlende_datei_ist_ein_quellenfehler_wie_in_der_app() -> None:
    netz = Netz()
    with pytest.raises(QuellenFehler, match="HTTP 404"):
        asyncio.run(vorab(functools.partial(link_lesen, URL), netz))


def test_fremder_server_wird_nie_gefragt() -> None:
    netz = Netz({"https://fremd.example/p.json": _paket()})
    with pytest.raises(QuellenFehler) as fehler:
        asyncio.run(vorab(functools.partial(link_lesen, "https://fremd.example/p.json"), netz))
    assert str(fehler.value) == NUR_EIGENER
    assert netz.gefragt == []


def test_zu_grosse_datei_wird_abgelehnt() -> None:
    netz = Netz({URL: _paket()})
    with pytest.raises(QuellenFehler, match="zu groß für den Browser"):
        asyncio.run(vorab(functools.partial(link_lesen, URL), netz, grenze=10))


def test_pruefen_holt_standdatei_und_bei_fehlender_die_datei_selbst() -> None:
    """Zwei Pakete aus Datei-Links: eines mit Standdatei (wenige Bytes), eines ohne — dort lädt
    der Kern die Datei selbst. Alles in einem Lauf, jede Adresse einmal."""
    url_b = f"{URSPRUNG}/pakete/b.json"
    a = paket_lesen(json.loads(_paket(1))).paket
    a.quelle, a.quelle_art = URL, DATEI
    b = paket_lesen(json.loads(_paket(1, "B"))).paket
    b.quelle, b.quelle_art = url_b, DATEI
    neu_a, neu_b = _paket(2), _paket(3, "B")
    netz = Netz(
        {
            stand_url(URL): stand_json(2, hashlib.sha256(neu_a).hexdigest(), len(neu_a)),
            URL: neu_a,
            url_b: neu_b,
        }
    )
    ergebnis = asyncio.run(vorab(functools.partial(pruefen, [], [a, b]), netz))
    assert ergebnis.fehler == []
    assert {(u.eintrag.name, u.eintrag.version) for u in ergebnis.updates} == {
        ("Für Max", 2),
        ("B", 3),
    }
    # die Datei von A wird für die Prüfung nicht geladen — nur ihre Standdatei
    assert netz.gefragt == [stand_url(URL), stand_url(url_b), url_b]


def test_nach_zu_vielen_adressen_ist_schluss() -> None:
    netz = Netz()

    def gierig(laden) -> None:  # fragt immer weiter
        for n in range(10_000):
            try:
                laden(f"{URSPRUNG}/{n}")
            except OSError as fehler:
                if str(fehler) == browsernetz.ZU_VIELE:
                    raise QuellenFehler(str(fehler)) from fehler

    with pytest.raises(QuellenFehler, match="Zu viele"):
        asyncio.run(vorab(gierig, netz))
    assert len(netz.gefragt) == MAX_ADRESSEN


def test_in_der_app_laeuft_die_funktion_unveraendert_im_thread() -> None:
    """Ohne Browser: kein ``laden=`` — der Kern nimmt seinen eingebauten Lader (`urllib`)."""
    assert browsernetz.zugang() is None
    assert asyncio.run(browsernetz.ausfuehren(lambda **kw: kw)) == {}


def test_im_browser_laeuft_sie_ueber_den_zugang() -> None:
    netz = Netz({URL: _paket()})
    art, _ = asyncio.run(browsernetz.ausfuehren(functools.partial(link_lesen, URL), netz))
    assert art == "paket" and netz.gefragt == [URL]


# -- scrypt ------------------------------------------------------------------------------------


def test_scrypt_wird_erst_geladen_wenn_ein_privates_paket_da_ist(monkeypatch) -> None:
    oeffentlich, geheim = Netz({URL: _paket()}), Netz({URL: privat.verschluesseln(_paket(), CODE)})
    asyncio.run(browsernetz.privat_bereit())  # App: kein Zugang, nichts
    asyncio.run(browsernetz.privat_bereit(geheim))  # scrypt ist da (hashlib)
    assert geheim.krypto == 0
    monkeypatch.setattr(privat, "moeglich", lambda: False)
    asyncio.run(vorab(functools.partial(link_lesen, URL), oeffentlich))
    assert oeffentlich.krypto == 0  # ein öffentliches Paket braucht es nie
    with pytest.raises(ZugangNoetig):
        asyncio.run(vorab(functools.partial(link_lesen, URL), geheim))
    assert geheim.krypto == 1  # schon beim Holen — der Code kommt gleich


def test_scheitert_das_nachladen_sagt_es_der_kern_beim_oeffnen(monkeypatch) -> None:
    netz = Netz()
    geheim = privat.verschluesseln(_paket(), CODE)

    async def kaputt() -> None:
        raise OSError("404")

    netz.krypto_laden = kaputt  # type: ignore[method-assign]
    monkeypatch.setattr(privat, "moeglich", lambda: False)
    asyncio.run(browsernetz.privat_bereit(netz))  # wirft nicht
    with pytest.raises(privat.PrivatNichtMoeglich):
        privat.entschluesseln(geheim, CODE)


def test_scrypt_aus_cryptography_rechnet_wie_hashlib(monkeypatch) -> None:
    """Der Weg des Browsers: `hashlib.scrypt` fehlt dort, ``cryptography`` rechnet dasselbe —
    eine Datei, die das Werkzeug verschlüsselt hat, öffnet sich mit beiden."""
    pytest.importorskip("cryptography")
    geheim = privat.verschluesseln(_paket(), CODE)
    salz = b"0123456789abcdef"
    mit_hashlib = privat._scrypt(CODE.encode(), salz, 2**15, 8, 1)
    monkeypatch.delattr(hashlib, "scrypt")
    assert privat.moeglich()
    assert privat._scrypt(CODE.encode(), salz, 2**15, 8, 1) == mit_hashlib
    assert privat.entschluesseln(geheim, CODE) == _paket()
    with pytest.raises(privat.CodeFalsch):
        privat.entschluesseln(geheim, "AAAAAAAA")


def test_zu_grosse_schluesselparameter_sind_eine_verfaelschte_datei(monkeypatch) -> None:
    """Die Speichergrenze gilt für beide Wege — vor dem Rechnen, nicht erst in `hashlib`."""
    gerufen: list[int] = []
    monkeypatch.setattr(privat, "_scrypt", lambda *a: gerufen.append(1) or b"\0" * 64)
    with pytest.raises(privat.CodeFalsch):
        privat._schluessel(CODE, b"0" * 16, 20, 16, 1)  # 128 · 16 · 2²⁰ = 2 GiB
    assert gerufen == []


# -- Bilder aus Paketen ------------------------------------------------------------------------


def test_bild_aus_dem_paket_in_der_app_als_pfad_im_browser_als_bytes(tmp_path, monkeypatch) -> None:
    """Flutter liest im Browser keine Datei aus Pythons Dateisystem — es fragte den Pfad beim
    Server an (404, gemessen 23.11.2026). Dort bekommt `ft.Image` die Bytes."""
    import sys

    from trainingsapp.ui.components.bildquelle import bildquelle

    datei = tmp_path / "bild.png"
    datei.write_bytes(b"\x89PNG-bytes")
    assert bildquelle(datei) == str(datei)
    monkeypatch.setattr(sys, "platform", "emscripten")
    assert bildquelle(datei) == b"\x89PNG-bytes"
    assert bildquelle(str(datei)) == b"\x89PNG-bytes"
    assert bildquelle(tmp_path / "fehlt.png") == str(tmp_path / "fehlt.png")  # die Ansicht steht
