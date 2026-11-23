"""Pakete per Link in der Web-Fassung, in der Oberfläche (Ben, 23.11.2026;
`docs/plan_web_pakete.md`): Link-Import über den Zugang des Browsers, der Seitenlink
``#/paket/p/<ordner>``, Updates beim Start ohne Quellenliste. Läuft nur mit `flet`.

Der Browser ist hier ein nachgebauter Zugang (`Netz`); der echte Weg — `fetch` hinter der
Content-Security-Policy, scrypt aus ``cryptography`` — ist in Chromium gemessen (Plan §3).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import urllib.error
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.paketquelle import (  # noqa: E402
    DATEI,
    INDEX_FORMAT,
    privat_pfade,
    seitenroute,
    stand_json,
    stand_url,
)
from trainingsapp.core.privat import verschluesseln  # noqa: E402
from trainingsapp.ui import browsernetz  # noqa: E402
from trainingsapp.ui.components import paket_link  # noqa: E402
from trainingsapp.ui.components.paket_link import link_importieren, seitenlink_oeffnen  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views import updates  # noqa: E402

URSPRUNG = "https://praxis.example"
ORDNER = "7Hq3vX9aBcDeFgHiJkLmNo"
URL = f"{URSPRUNG}/pakete/{privat_pfade(ORDNER)[0]}"
URL_ZIP = f"{URSPRUNG}/pakete/{privat_pfade(ORDNER)[1]}"
CODE = "K7QM9XA2"


class Netz:
    """Der Server der Seite als Tabelle Adresse → Bytes; merkt, was gefragt wurde."""

    def __init__(self, dateien: dict[str, bytes] | None = None) -> None:
        self.dateien = dateien or {}
        self.gefragt: list[str] = []
        self.ursprung = URSPRUNG

    async def holen(self, url: str, grenze: int) -> bytes:
        self.gefragt.append(url)
        if url not in self.dateien:
            raise urllib.error.HTTPError(url, 404, "", None, None)  # type: ignore[arg-type]
        return self.dateien[url]

    async def krypto_laden(self) -> None:
        pass


def _klar(version: int = 1) -> bytes:
    roh = {
        "paket": {"name": "Für Max", "version": version, "fuer": "Max"},
        "exercises": [{"key": "a", "name": f"Übung v{version}", "description": "Langsam."}],
    }
    return json.dumps(roh, ensure_ascii=False).encode("utf-8")


def _geheim(version: int = 1) -> bytes:
    return verschluesseln(_klar(version), CODE)


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "actions"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/", views=[], platform=None, web=True, dialoge=[], aufgaben=[])
    p.routen = []
    p.update = lambda: None
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: None
    p.run_task = lambda f, *a: p.aufgaben.append(asyncio.ensure_future(f(*a)))

    async def push_route(route: str) -> None:
        p.routen.append(route)
        p.route = route

    p.push_route = push_route
    return p


@pytest.fixture
def netz(monkeypatch):
    """Die App läuft „im Browser“: Es gibt einen Zugang zum Netz der Seite."""
    n = Netz()
    monkeypatch.setattr(browsernetz, "_zugang", n)
    return n


def _zu(page, dialog) -> None:
    async def lauf() -> None:
        await dialog.on_dismiss(None)
        offen = [t for t in page.aufgaben if isinstance(t, asyncio.Future) and not t.done()]
        if offen:
            await asyncio.gather(*offen)

    asyncio.run(lauf())


def _code_eingeben(page, code: str) -> None:
    dialog = page.dialoge[-1]
    assert dialog.title.value == "Privates Paket"
    feld = next(x for x in _alle(dialog) if getattr(x, "data", None) == "code")
    feld.value = code
    dialog.open = True
    next(x for x in _alle(dialog) if getattr(x, "data", None) == "oeffnen").on_click()
    _zu(page, dialog)


def _importiert(state):
    return [p for p, _ in state.pakete.alle() if p.name == "Für Max"]


# -- Link-Import ---------------------------------------------------------------------------------


def test_link_import_im_browser_holt_vom_eigenen_server_und_fragt_den_code(
    page, state, netz
) -> None:
    netz.dateien[URL] = _geheim()
    asyncio.run(link_importieren(page, state, URL))
    _code_eingeben(page, CODE)
    frage = page.dialoge[-1]
    assert frage.title.value == "„Für Max“ importieren?"
    frage.actions[1].on_click()
    (paket,) = _importiert(state)
    assert paket.quelle == URL and paket.quelle_art == DATEI and paket.zugangscode == CODE
    assert set(netz.gefragt) == {URL}


def test_fremder_link_im_browser_wird_abgelehnt_ohne_anfrage(page, state, netz) -> None:
    asyncio.run(link_importieren(page, state, "https://fremd.example/p.json"))
    (meldung,) = page.dialoge
    assert browsernetz.NUR_EIGENER in meldung.content.value
    assert netz.gefragt == []


def test_paketquelle_per_link_gibt_es_in_der_web_fassung_nicht(
    page, state, netz, monkeypatch
) -> None:
    monkeypatch.setenv("TRAININGSAPP_WEB", "1")
    index = {"format": INDEX_FORMAT, "version": 1, "quelle": {"name": "P"}, "pakete": []}
    netz.dateien[f"{URSPRUNG}/pakete/index.json"] = json.dumps(index).encode()
    asyncio.run(link_importieren(page, state, f"{URSPRUNG}/pakete/index.json"))
    (meldung,) = page.dialoge
    assert isinstance(meldung, ft.SnackBar) and "nur einzelne Pakete" in meldung.content.value
    assert state.paketquellen() == [] or f"{URSPRUNG}/pakete/index.json" not in state.paketquellen()


# -- Der Seitenlink ------------------------------------------------------------------------------


def test_seitenlink_laedt_das_paket_fragt_den_code_und_laesst_die_route_nicht_stehen(
    page, state, netz
) -> None:
    netz.dateien[URL] = _geheim()
    page.route = seitenroute(ORDNER)
    asyncio.run(seitenlink_oeffnen(page, state, ORDNER))
    assert page.routen == ["/pakete"]  # der Ordner bleibt nicht in der Adresszeile
    _code_eingeben(page, CODE)
    page.dialoge[-1].actions[1].on_click()
    (paket,) = _importiert(state)
    assert paket.quelle == URL

    # Noch einmal mit demselben Link: nichts laden, nichts fragen — die Seite des Pakets
    netz.gefragt.clear()
    page.dialoge.clear()
    asyncio.run(seitenlink_oeffnen(page, state, ORDNER))
    assert page.routen[-1] == f"/pakete/{paket.id}"
    assert netz.gefragt == [] and page.dialoge == []


def test_seitenlink_nimmt_die_zip_wenn_es_keine_json_gibt(page, state, netz, monkeypatch) -> None:
    geladen: list[str] = []

    async def merken(_page, _state, url: str, **_) -> None:
        geladen.append(url)

    monkeypatch.setattr(paket_link, "link_importieren", merken)
    asyncio.run(seitenlink_oeffnen(page, state, ORDNER))  # nur die ZIP „liegt“ dort
    assert geladen == [URL_ZIP] and netz.gefragt == [URL]
    netz.dateien[URL] = _geheim()
    asyncio.run(seitenlink_oeffnen(page, state, ORDNER))
    assert geladen[-1] == URL


def test_seitenlink_im_zweiten_tab_importiert_nicht(page, state, netz) -> None:
    state.browserspeicher = SimpleNamespace(aktiv=False)
    netz.dateien[URL] = _geheim()
    asyncio.run(seitenlink_oeffnen(page, state, ORDNER))
    (meldung,) = page.dialoge
    assert "nicht gespeichert" in meldung.content.value
    assert netz.gefragt == [] and _importiert(state) == []


def test_seitenlink_in_der_app_fuehrt_nur_nach_hause(page, state) -> None:
    assert browsernetz.zugang() is None
    asyncio.run(seitenlink_oeffnen(page, state, ORDNER))
    assert page.routen == ["/"] and page.dialoge == []


# -- Updates -------------------------------------------------------------------------------------


def _installiert(page, state, netz):
    netz.dateien[URL] = _geheim(1)
    asyncio.run(link_importieren(page, state, URL))
    _code_eingeben(page, CODE)
    page.dialoge[-1].actions[1].on_click()
    netz.gefragt.clear()
    page.dialoge.clear()
    (paket,) = _importiert(state)
    return paket


def test_beim_start_im_browser_kommt_die_neue_fassung_ohne_quellen_und_ohne_hinweis(
    page, state, netz, monkeypatch
) -> None:
    monkeypatch.setenv("TRAININGSAPP_WEB", "1")
    # ohne Paket aus einem Link fragt die Seite beim Start niemanden
    asyncio.run(updates.beim_start(page, state))
    assert netz.gefragt == [] and page.dialoge == []

    paket = _installiert(page, state, netz)
    assert paket.version == 1
    neu = _geheim(2)
    netz.dateien[URL] = neu
    netz.dateien[stand_url(URL)] = stand_json(2, hashlib.sha256(neu).hexdigest(), len(neu))
    asyncio.run(updates.beim_start(page, state))
    assert page.dialoge == []  # kein „Die App fragt Quellen und GitHub“
    assert netz.gefragt == [stand_url(URL), URL]  # erst die Standdatei, dann die Datei
    (jetzt,) = _importiert(state)
    assert jetzt.version == 2 and jetzt.zugangscode == CODE
    assert [u.name for u in state.uebungen.alle() if u.name.startswith("Übung v")] == ["Übung v2"]


def test_beim_start_abgeschaltet_fragt_auch_im_browser_nicht(
    page, state, netz, monkeypatch
) -> None:
    monkeypatch.setenv("TRAININGSAPP_WEB", "1")
    _installiert(page, state, netz)
    state.update_pruefung_setzen(False)
    asyncio.run(updates.beim_start(page, state))
    assert netz.gefragt == []


def test_updates_seite_im_browser_ohne_quellen_und_mit_eigenem_hinweis(
    page, state, netz, monkeypatch
) -> None:
    browser = SimpleNamespace()
    in_der_app = _texte(updates.updates_view(page, state, browser).controls[0])
    assert "QUELLEN" in [t.upper() for t in in_der_app]
    monkeypatch.setenv("TRAININGSAPP_WEB", "1")
    im_browser = _texte(updates.updates_view(page, state, browser).controls[0])
    assert "QUELLEN" not in [t.upper() for t in im_browser]
    assert any("neu laden genügt" in t for t in im_browser)
    assert not any("von der Praxis" in t for t in im_browser)
