"""Die Tag-Auswahl Typ | Region — an allen drei Stellen dieselbe (Ben, 15.10.2026).

Katalogfilter, „Übung hinzufügen“ und Übungs-Editor nutzen
`ui/components/tagwahl.TagWahl`. Die Auswahl wirkt sofort beim Ankreuzen,
nicht erst beim Schließen der Liste.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Exercise  # noqa: E402
from trainingsapp.ui.components.tagwahl import TagWahl  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.katalog import katalog  # noqa: E402
from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


@pytest.fixture
def page():
    dialoge: list = []

    async def push_route(route: str) -> None:
        page_.route = route

    page_ = SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        push_route=push_route,
    )
    return page_


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls", "leading", "trailing", "appbar", "actions"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def kaesten(wurzel) -> tuple[ft.SubmenuButton, ft.SubmenuButton]:
    typ, region = (c for c in alle(wurzel) if isinstance(c, ft.SubmenuButton))
    return typ, region


def zeile(kasten: ft.SubmenuButton, text: str) -> ft.MenuItemButton:
    return next(
        c
        for c in alle(kasten)
        if isinstance(c, ft.MenuItemButton)
        and isinstance(c.content, ft.Text)
        and c.content.value == text
    )


def kasten_text(kasten: ft.SubmenuButton) -> tuple[str, str]:
    beschriftung, wert = kasten.content.controls
    return beschriftung.value, wert.value


def test_auswahl_wirkt_sofort_und_merkt_sich_die_reihenfolge() -> None:
    gemeldet: list[tuple[list[str], list[str]]] = []
    wahl = TagWahl(
        ["Atmung", "Dehnung", "Kräftigung"],
        ["Bein"],
        ["Dehnung", "gibt es nicht mehr"],
        [],
        on_change=lambda t, r: gemeldet.append((t, r)),
    )
    assert wahl.typen == ["Dehnung"]  # Verwaistes fällt weg
    typ, _ = kaesten(wahl.control)
    zeile(typ, "Kräftigung").on_click()
    assert gemeldet == [(["Dehnung", "Kräftigung"], [])]  # sofort, ohne Schließen
    assert kasten_text(typ) == ("Typ · 2", "Dehnung, Kräftigung")
    zeile(typ, "Dehnung").on_click()
    assert gemeldet[-1] == (["Kräftigung"], [])

    zeile(typ, "Liste leeren").on_click()
    assert gemeldet[-1] == ([], [])
    assert kasten_text(typ) == ("Typ", "alle")


def test_neuen_tag_anlegen(page) -> None:
    gemeldet: list[tuple[list[str], list[str]]] = []
    wahl = TagWahl(
        ["Dehnung"],
        ["Bein"],
        [],
        [],
        on_change=lambda t, r: gemeldet.append((t, r)),
        neu_anlegen=True,
        page=page,
    )
    typ, _ = kaesten(wahl.control)

    def anlegen(text: str) -> ft.AlertDialog:
        zeile(typ, "Neuer Typ …").on_click()
        dialog = page.dialoge[-1]
        dialog.content.value = text
        dialog.actions[1].on_click()
        return dialog

    assert anlegen("bein").content.error == "„Bein“ ist schon eine Region."
    assert wahl.typen == []
    anlegen("dehnung")  # Groß/klein egal: der vorhandene
    anlegen("Qigong")
    assert gemeldet[-1] == (["Dehnung", "Qigong"], [])
    assert [c.content.value for c in alle(typ) if isinstance(c, ft.MenuItemButton)][2] == "Qigong"


def test_katalog_filtert_beim_ankreuzen(page, state) -> None:
    ansicht = katalog(page, state)
    typ, _ = kaesten(ansicht)
    zeile(typ, "Atmung").on_click()
    assert state.typ_filter == {"Atmung"}
    liste = next(c for c in alle(ansicht) if isinstance(c, ft.ListView))
    namen = [  # Übungszeilen tragen „Trainieren“ — nicht die Zeile „Paketmanager“
        z.title.value
        for z in liste.controls
        if isinstance(z, ft.ListTile) and isinstance(z.trailing, ft.FilledTonalButton)
    ]
    erwartet = [u.name for u in state.uebungen.alle() if "Atmung" in u.typen]
    assert namen and sorted(namen) == sorted(erwartet)


def test_editor_speichert_die_auswahl(page, state) -> None:
    uebung = Exercise(name="Probe", typen=["Kräftigung"])
    state.uebungen.speichern(uebung)
    ansicht = uebung_bearbeiten(page, state, uebung)
    typ, region = kaesten(ansicht)
    zeile(typ, "Dehnung").on_click()
    zeile(region, "Bein").on_click()
    zeile(region, "Neue Region …").on_click()
    dialog = page.dialoge[-1]
    dialog.content.value = "Knöchel"
    dialog.actions[1].on_click()

    speichern = next(
        c for c in alle(ansicht) if isinstance(c, ft.TextButton) and c.content == "Speichern"
    )
    asyncio.run(speichern.on_click())
    gespeichert = state.uebungen.laden(uebung.id)
    assert gespeichert.typen == ["Kräftigung", "Dehnung"]  # der erste bleibt die Kategorie
    assert gespeichert.regionen == ["Bein", "Knöchel"]
    assert "Knöchel" in state.tags.namen("region")
