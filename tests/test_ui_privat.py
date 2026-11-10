"""Private Pakete in der Oberfläche (U7, Ben 9.11.2026): Datei- und Link-Import fragen nach dem
Code, der Paketmanager zeigt „privat · für …“ und „Zugang anzeigen“. Läuft nur mit `flet`."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.privat import verschluesseln  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402

CODE = "K7QM9XA2"
URL = "https://x.org/pakete/p/7Hq3vX9aBcDeFgHiJkLmNo/paket.json"


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "actions"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _geheim() -> bytes:
    roh = {
        "paket": {"name": "Für Max", "version": 1, "fuer": "Max"},
        "exercises": [{"key": "a", "name": "Übung für Max", "description": "Langsam."}],
    }
    return verschluesseln(json.dumps(roh, ensure_ascii=False).encode("utf-8"), CODE)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/", views=[], platform=None, web=False, dialoge=[], aufgaben=[])
    p.update = lambda: None
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: None
    p.run_task = lambda f, *a: p.aufgaben.append(asyncio.ensure_future(f(*a)))
    return p


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


def test_datei_mit_code_importieren_und_zugang_anzeigen(tmp_path, page, state, monkeypatch) -> None:
    from trainingsapp.ui.views.pakete import paket_view, pakete_view

    datei = tmp_path / "paket.json"
    datei.write_bytes(_geheim())

    class Waehler:
        async def pick_files(self, **_):
            return [SimpleNamespace(path=str(datei), name="paket.json", bytes=None)]

    monkeypatch.setattr(ft, "FilePicker", Waehler)
    ansicht = pakete_view(page, state)
    knopf = next(x for x in _alle(ansicht) if isinstance(x, ft.FilledButton))
    knopf.on_click()
    blatt = page.dialoge[-1]
    next(c for c in _alle(blatt) if isinstance(c, ft.FilledTonalButton)).on_click(None)
    _zu(page, blatt)
    _code_eingeben(page, "k7qm-9xa2")  # klein und mit Bindestrich geht
    frage = page.dialoge[-1]
    assert frage.title.value == "„Für Max“ importieren?"
    # Der Klartext liegt nur, solange die Rückfrage offen ist
    arbeit = tmp_path / "Import"
    assert [p.name[:9] for p in arbeit.iterdir()] == ["klartext_"]
    frage.actions[1].on_click()
    _zu(page, frage)
    assert not list(arbeit.iterdir())
    (paket,) = [p for p, _ in state.pakete.alle() if p.name == "Für Max"]
    assert paket.privat and paket.zugangscode == CODE and paket.fuer == "Max"
    seite = paket_view(page, state, "/pakete", paket)
    assert any(t.startswith("privat · für Max") for t in _texte(seite))
    next(x for x in _alle(seite) if getattr(x, "data", None) == "zugang").on_click()
    assert "K7QM-9XA2" in _texte(page.dialoge[-1])


def test_abbrechen_loescht_den_klartext(tmp_path, page, state, monkeypatch) -> None:
    from trainingsapp.ui.views.pakete import pakete_view

    datei = tmp_path / "paket.json"
    datei.write_bytes(_geheim())

    class Waehler:
        async def pick_files(self, **_):
            return [SimpleNamespace(path=str(datei), name="paket.json", bytes=None)]

    monkeypatch.setattr(ft, "FilePicker", Waehler)
    ansicht = pakete_view(page, state)
    next(x for x in _alle(ansicht) if isinstance(x, ft.FilledButton)).on_click()
    blatt = page.dialoge[-1]
    next(c for c in _alle(blatt) if isinstance(c, ft.FilledTonalButton)).on_click(None)
    _zu(page, blatt)
    _code_eingeben(page, CODE)
    frage = page.dialoge[-1]
    arbeit = tmp_path / "Import"
    assert len(list(arbeit.iterdir())) == 1
    frage.actions[0].on_click()  # Abbrechen
    _zu(page, frage)
    assert not list(arbeit.iterdir())
    assert not [p for p, _ in state.pakete.alle() if p.name == "Für Max"]
    # Was ein früherer Lauf liegen ließ, räumt der Start
    (arbeit / "klartext_alt.zip").write_bytes(b"x")
    state.schliessen()
    neu = AppState.starten(tmp_path / "app.db")
    try:
        assert not list(arbeit.iterdir())
    finally:
        neu.con.close() if hasattr(neu, "con") else None


def test_link_mit_code(page, state, monkeypatch) -> None:
    from trainingsapp.ui.components.paket_link import link_importieren

    geheim = _geheim()
    asyncio.run(link_importieren(page, state, URL, laden=lambda _u: geheim))
    _code_eingeben(page, CODE)
    frage = page.dialoge[-1]
    assert frage.title.value == "„Für Max“ importieren?"
    frage.actions[1].on_click()
    (paket,) = [p for p, _ in state.pakete.alle() if p.name == "Für Max"]
    assert paket.quelle == URL and paket.zugangscode == CODE
