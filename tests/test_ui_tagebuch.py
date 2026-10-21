"""Der Reiter „Tagebuch“ im Verlauf (Ben, 18.10.2026) — `ui/views/tagebuch.py`.

Alle Notizen (zum Tag, zum Plan, zur Übung) nach Tagen mit mitlaufender Wochenleiste oder
nach Übungen; antippen bearbeitet.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Plan  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.tagebuch import UEBUNGEN, tagebuch  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    dialoge: list = []
    aufgaben: list = []
    return SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        aufgaben=aufgaben,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: aufgaben.append(f),
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "actions"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _welt(state: AppState):
    """Gestern ein Plan mit Notiz und eine Übung mit Notiz, heute die Notiz zum Tag."""
    plan = Plan(name="Kräftigung kurz", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    gestern = state.heute() - timedelta(days=1)
    um = datetime.combine(gestern, time(18)).astimezone()
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, gestern)
    kniebeuge = state.uebungen.laden(seed_id("kniebeuge"))
    state.sitzungen.eintrag_anlegen(
        session, kniebeuge, {"reps": [15]}, "links enger", started_at=um
    )
    state.sitzungen.notiz_setzen(session.id, "zäh heute")
    state.tagesnotizen.setzen(state.profil.id, state.heute(), "Schulter fest")
    return plan, gestern, kniebeuge


def test_nach_tagen_neueste_oben_mit_wochenleiste(page, state) -> None:
    _plan, gestern, _ = _welt(state)
    ansicht = tagebuch(page, state)
    texte = _texte(ansicht)
    heute_kopf = next(t for t in texte if t.startswith("Heute · "))
    gestern_kopf = next(t for t in texte if t.startswith("Gestern · "))
    assert texte.index(heute_kopf) < texte.index(gestern_kopf)  # neuester Tag oben
    assert "Schulter fest" in texte and "Zum Tag" in texte
    # Gestern: Plan und Übung nach der Uhr (beide 18:00 — der Plan zuerst)
    assert texte.index("zäh heute") < texte.index("links enger") and "18:00" in texte
    assert "Plan „Kräftigung kurz“" in texte and "Kniebeuge" in texte
    # Die Wochenleiste zeigt Punkte für Tage mit Notizen (gestern zwei)
    zellen = [x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.tooltip]
    if gestern.isocalendar()[:2] == state.heute().isocalendar()[:2]:
        assert "2 Notizen" in [z.tooltip for z in zellen]
    assert "1 Notiz" in [z.tooltip for z in zellen]


def test_scrollen_nimmt_die_woche_mit(page, state) -> None:
    """Steht ein älterer Tag oben, zeigt die Leiste seine Woche (Höhen gemeldet)."""
    _welt(state)
    vor_zwei_wochen = state.heute() - timedelta(days=15)
    state.tagesnotizen.setzen(state.profil.id, vor_zwei_wochen, "lange her")
    ansicht = tagebuch(page, state)
    liste = next(x for x in _alle(ansicht) if isinstance(x, ft.Column) and x.on_scroll)
    bloecke = [x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.on_size_change]
    assert len(bloecke) == 3
    for b in bloecke:
        b.on_size_change(SimpleNamespace(height=120, width=400))
    liste.on_scroll(SimpleNamespace(pixels=2 * (120 + 14) + 10))  # der dritte Tag oben
    assert state.scroll_offsets["tagebuch-tage"] == 2 * (120 + 14) + 10
    from trainingsapp.core.verlauf import wochen_titel

    beginn = vor_zwei_wochen - timedelta(days=vor_zwei_wochen.weekday())
    assert wochen_titel(beginn) in _texte(ansicht)


def test_nach_uebungen_und_antippen_bearbeitet(page, state) -> None:
    _plan, _gestern, _ = _welt(state)
    state.tagebuch_ordnung = UEBUNGEN
    ansicht = tagebuch(page, state)
    texte = _texte(ansicht)
    assert "Kniebeuge" in texte and "Zum Tag" in texte
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.on_size_change]
    karte = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and "links enger" in _texte(x)
    )
    karte.on_click()  # die Leistungen des Tages als Blatt
    assert isinstance(page.dialoge[-1], ft.BottomSheet)
    tag_karte = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and "Schulter fest" in _texte(x)
    )
    tag_karte.on_click()
    dialog = page.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog) and dialog.content.value == "Schulter fest"
    dialog.content.value = "Schulter frei"
    dialog.actions[-1].on_click()  # Speichern
    assert state.tagesnotizen.lesen(state.profil.id, state.heute()) == "Schulter frei"


def test_leer_und_neue_notiz_zum_tag(page, state) -> None:
    ansicht = tagebuch(page, state)
    assert any(t.startswith("Noch keine Notizen") for t in _texte(ansicht))
    knopf = next(
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.icon == ft.Icons.EDIT_NOTE
    )
    knopf.on_click()
    dialog = page.dialoge[-1]
    dialog.content.value = "erster Eintrag"
    asyncio.run(dialog.on_dismiss(None))  # daneben getippt — gilt als gespeichert
    assert state.tagesnotizen.lesen(state.profil.id, state.heute()) == "erster Eintrag"


def test_der_verlauf_hat_vier_reiter(page, state) -> None:
    """Seit den Tagesfeldern (21.10.2026) steht „Zum Tag“ vor dem Tagebuch."""
    from trainingsapp.ui.views.verlauf import TAGEBUCH, verlauf

    state.verlauf_tab = TAGEBUCH
    reiter = verlauf(page, state)
    leiste = next(x for x in _alle(reiter) if isinstance(x, ft.TabBar))
    assert [t.label for t in leiste.tabs] == ["Tage", "Übungen", "Zum Tag", "Tagebuch"]
