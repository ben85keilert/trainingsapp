"""Einstellungen → Notiz-Tags (Ben, 2.11.2026) — `ui/views/einstellungen_notiz_tags.py`:
anlegen, umbenennen, aus/ein, löschen mit Rückfrage; „Tagebuch“ fest."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.einstellungen import einstellungen  # noqa: E402
from trainingsapp.ui.views.einstellungen_notiz_tags import (  # noqa: E402
    einstellungen_notiz_tags_view,
    notizen_text,
)


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/einstellungen", views=[], platform=None, dialoge=[], routen=[])
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: p.dialoge.pop() if p.dialoge else None
    p.update = lambda: None

    async def push_route(route: str) -> None:
        p.routen.append(route)

    p.push_route = push_route
    return p


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "actions", "appbar", "subtitle"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _zeilen(ansicht) -> dict[str, ft.Row]:
    """Name → Zeile (die Zeilen mit einem Schalter)."""
    return {
        _texte(r)[0]: r
        for r in _alle(ansicht)
        if isinstance(r, ft.Row) and any(isinstance(c, ft.Switch) for c in r.controls)
    }


def test_eintrag_in_den_einstellungen(page, state) -> None:
    ansicht = einstellungen(page, state, SimpleNamespace())
    tile = next(
        x for x in _alle(ansicht) if isinstance(x, ft.ListTile) and _texte(x)[0] == "Notiz-Tags"
    )
    assert "Tagebuch" in _texte(tile)[1]
    import asyncio

    asyncio.run(tile.on_click())
    assert page.routen == ["/einstellungen/notiz-tags"]


def test_anlegen_umbenennen_schalten_loeschen(page, state) -> None:
    profil = state.profil.id
    ansicht = einstellungen_notiz_tags_view(page, state)
    zeilen = _zeilen(ansicht)
    assert list(zeilen) == ["Tagebuch"]
    # Der feste Tag: kein Stift, kein Papierkorb, nur der Schalter
    assert not [c for c in zeilen["Tagebuch"].controls if isinstance(c, ft.IconButton)]
    assert "fest" in _texte(zeilen["Tagebuch"])[1]
    feld = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField))
    feld.value = "Kraft"
    feld.on_submit(None)
    (kraft,) = [t for t in state.notiz_tags.alle(profil) if t.name == "Kraft"]
    zeilen = _zeilen(ansicht)
    assert list(zeilen) == ["Tagebuch", "Kraft"] and _texte(zeilen["Kraft"])[1] == "ungenutzt"
    feld.value = "kraft"
    feld.on_submit(None)
    assert feld.error  # gibt es schon
    # Zwei Notizen mit dem Tag
    state.tagesnotizen.anlegen(profil, state.heute(), "eins", [kraft.id])
    state.tagesnotizen.anlegen(profil, state.heute(), "zwei", [kraft.id])
    ansicht = einstellungen_notiz_tags_view(page, state)
    zeilen = _zeilen(ansicht)
    assert _texte(zeilen["Kraft"])[1] == "2 Notizen"
    stift, schalter, korb = zeilen["Kraft"].controls[1:]
    # Umbenennen
    stift.on_click()
    dialog = page.dialoge[-1]
    eingabe = next(x for x in _alle(dialog) if isinstance(x, ft.TextField))
    eingabe.value = "Krafttraining"
    dialog.actions[-1].on_click()
    assert [t.name for t in state.notiz_tags.alle(profil)] == ["Tagebuch", "Krafttraining"]
    # Ausschalten: wird nicht mehr angeboten, die Notizen behalten ihn
    schalter.on_change(SimpleNamespace(control=SimpleNamespace(value=False)))
    assert [t.name for t in state.notiz_tags.alle(profil, mit_ausgeschalteten=False)] == [
        "Tagebuch"
    ]
    assert state.tagesnotizen.anzahl_mit_tag(kraft.id) == 2
    # Löschen mit Rückfrage: die Notizen verlieren den Tag, die Texte bleiben
    korb.on_click()
    frage = page.dialoge[-1]
    assert "2 Notizen verlieren den Tag" in frage.content.value
    frage.actions[-1].on_click()
    assert [t.name for t in state.notiz_tags.alle(profil)] == ["Tagebuch"]
    assert [n.tag_ids for n in state.tagesnotizen.zum_tag(profil, state.heute())] == [(), ()]
    assert [n.text for n in state.tagesnotizen.zum_tag(profil, state.heute())] == ["eins", "zwei"]
    assert notizen_text(1) == "1 Notiz"
