"""Oberfläche zu Übungspaketen und Tag-Auswahl (Ben, 14.10.2026).

Wie `test_ui_smoke.py`: Ansichten bauen, Handler direkt aufrufen. Läuft nur
mit `flet` (nicht in der CI-Gruppe `ci`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Exercise, Plan  # noqa: E402
from trainingsapp.core.pakete import GRUNDAUSSTATTUNG  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.components.tagwahl import TagWahl  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.pakete import paket_export_view, pakete_view  # noqa: E402
from trainingsapp.ui.views.plan_hinzufuegen import plan_hinzufuegen_view  # noqa: E402
from trainingsapp.ui.views.uebung_detail import uebung_detail  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


@pytest.fixture
def page():
    return SimpleNamespace(route="/", views=[], update=lambda: None, show_dialog=lambda d: None)


@pytest.fixture
def ohne_fenster(monkeypatch):
    """`update()` braucht sonst eine echte Seite."""
    monkeypatch.setattr(ft.Control, "update", lambda self: None)


def alle(wurzel):
    """Alle Controls unter ``wurzel`` (auch in Menüs, Spans und Zeilen)."""
    yield wurzel
    for name in ("content", "controls", "spans", "trailing", "leading"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def texte(ansicht) -> list[str]:
    gefunden: list[str] = []
    for c in (c for v in ansicht.controls for c in alle(v)):
        if isinstance(c, ft.Text | ft.TextSpan):
            gefunden.append(getattr(c, "value", None) or getattr(c, "text", None) or "")
    return gefunden


def test_paketansichten_lassen_sich_bauen(page, state) -> None:
    assert pakete_view(page, state).route == "/pakete"
    ansicht = pakete_view(page, state, "/einstellungen/pakete")
    assert ansicht.route == "/einstellungen/pakete"
    assert "Standard" in texte(ansicht)

    leer = paket_export_view(page, state, "/pakete")
    assert leer.route == "/pakete/export"
    grund = paket_export_view(page, state, "/pakete", GRUNDAUSSTATTUNG)
    assert grund.route == f"/pakete/export/{GRUNDAUSSTATTUNG}"
    knopf = next(c for v in grund.controls for c in alle(v) if isinstance(c, ft.FilledButton))
    n = len(state.uebungen.alle())
    assert knopf.content == f"Exportieren ({n} Übungen)" and not knopf.disabled
    name = next(c for v in grund.controls for c in alle(v) if isinstance(c, ft.TextField))
    assert name.value == "Standard"


def test_herkunft_steht_klein_hinter_der_beschreibung(page, state) -> None:
    """Statt des Abschnitts „Varianten“ und des Hinweises „Mitgelieferte Übung“."""
    browser = ft.UrlLauncher()
    seed = state.uebungen.laden(seed_id("wadenheben"))
    inhalt = texte(uebung_detail(page, state, seed, browser))
    assert "  (Paket „Standard“)" in inhalt
    assert "VARIANTEN" not in inhalt
    assert not any("Mitgelieferte Übung" in t for t in inhalt)

    eigene = Exercise(name="Meine Übung")
    state.uebungen.speichern(eigene)
    assert "  (eigene Übung)" in texte(uebung_detail(page, state, eigene, browser))


def test_tagwahl_uebernimmt_erst_beim_schliessen(ohne_fenster) -> None:
    gemeldet: list[tuple[set[str], set[str]]] = []
    wahl = TagWahl(
        ["Atmung", "Dehnung"],
        ["Bein"],
        {"Dehnung", "gibt es nicht mehr"},
        set(),
        on_change=lambda t, r: gemeldet.append((t, r)),
    )
    assert wahl.typen == {"Dehnung"}  # Verwaistes fällt weg
    typ, region = (
        next(c for c in alle(k) if isinstance(c, ft.SubmenuButton)) for k in wahl.control.controls
    )
    zeilen = {
        c.content.value: c
        for c in alle(typ)
        if isinstance(c, ft.MenuItemButton) and isinstance(c.content, ft.Text)
    }
    zeilen["Atmung"].on_click()
    assert gemeldet == []  # angekreuzt, noch nicht übernommen
    typ.on_close()  # „Akzeptieren“ oder Tipp daneben
    assert gemeldet == [({"Atmung", "Dehnung"}, set())]
    assert typ.content.controls[0].value == "Typ · 2"
    assert typ.content.controls[1].value == "Atmung, Dehnung"

    zeilen["Liste leeren"].on_click()
    typ.on_close()
    assert gemeldet[-1] == (set(), set())
    assert typ.content.controls[1].value == "alle"
    region.on_close()  # nichts geändert → keine Meldung
    assert len(gemeldet) == 2


def test_hinzufuegen_filtert_nach_typ(page, state) -> None:
    plan = Plan(name="Test", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    state.hinzufuegen_typen = {"Atmung", "gibt es nicht mehr"}
    ansicht = plan_hinzufuegen_view(page, state, plan)
    assert state.hinzufuegen_typen == {"Atmung"}
    liste = next(c for v in ansicht.controls for c in alle(v) if isinstance(c, ft.ListView))
    namen = [z.title.value for z in liste.controls if isinstance(z, ft.ListTile)]
    erwartet = [u.name for u in state.uebungen.alle() if "Atmung" in u.typen]
    assert namen and sorted(namen) == sorted(erwartet)
    assert any(isinstance(c, ft.SubmenuButton) for v in ansicht.controls for c in alle(v))


def test_import_ueber_die_oberflaeche(page, state, monkeypatch) -> None:
    """Datei wählen → Rückfrage mit Vorschau → Importieren; die Dateiwahl ist nachgebildet."""
    import asyncio
    import json

    datei = json.dumps(
        {"paket": {"name": "Qigong"}, "exercises": [{"key": "baum", "name": "Baum"}]}
    ).encode()

    class Waehler:
        async def pick_files(self, **_):
            return [SimpleNamespace(bytes=datei, path=None, name="qigong.json")]

    monkeypatch.setattr(ft, "FilePicker", Waehler)
    dialoge: list = []
    page.show_dialog = dialoge.append
    page.pop_dialog = lambda: None
    ansicht = pakete_view(page, state)
    knopf = next(c for v in ansicht.controls for c in alle(v) if isinstance(c, ft.FilledButton))
    asyncio.run(knopf.on_click())

    frage = dialoge[-1]
    assert frage.title.value == "„Qigong“ importieren?"
    assert "• 1 neu" in [c.value for c in frage.content.controls]
    frage.actions[1].on_click()  # „Importieren“
    assert [p.name for p, _ in state.pakete.alle()] == ["Standard", "Qigong"]
    assert "1 neu" in dialoge[-1].content.value


def test_export_ueber_die_oberflaeche(page, state, monkeypatch) -> None:
    import asyncio
    import json

    import trainingsapp.ui.views.pakete as modul

    gesendet: list[tuple[str, bytes]] = []

    async def weitergeben(_page, name, daten, _mime):
        gesendet.append((name, daten))

    monkeypatch.setattr(modul, "weitergeben", weitergeben)
    page.update = lambda: None
    state.uebungen.speichern(Exercise(name="Meine Übung"))
    ansicht = paket_export_view(page, state)  # eigene Übungen sind angehakt
    name = next(c for v in ansicht.controls for c in alle(v) if isinstance(c, ft.TextField))
    knopf = next(c for v in ansicht.controls for c in alle(v) if isinstance(c, ft.FilledButton))

    name.value = "Eigene"  # kein Paketname
    asyncio.run(knopf.on_click())
    assert name.error and not gesendet

    name.value = "Für Anna"
    asyncio.run(knopf.on_click())
    dateiname, daten = gesendet[-1]
    assert dateiname == "uebungspaket_Fuer_Anna.json"
    roh = json.loads(daten)
    assert roh["paket"]["name"] == "Für Anna"
    assert [u["name"] for u in roh["exercises"]] == ["Meine Übung"]


def test_paketmanager_auf_standard_entfernen_wieder_installieren(page, state) -> None:
    import asyncio

    from trainingsapp.ui.views.pakete import paket_view

    dialoge: list = []
    page.show_dialog = dialoge.append
    page.pop_dialog = lambda: None

    async def push_route(route: str) -> None:
        page.route = route

    page.push_route = push_route
    wade = state.uebungen.laden(seed_id("wadenheben"))
    wade.description = "Meine Fassung"
    state.uebungen.speichern(wade)

    ansicht = paket_view(page, state, "/pakete", state.pakete.laden(GRUNDAUSSTATTUNG))
    assert ansicht.route == f"/pakete/{GRUNDAUSSTATTUNG}"
    assert "geändert: Beschreibung" in texte(ansicht)
    zurueck = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.RESTORE
    )
    zurueck.on_click()  # erst die Rückfrage
    assert state.uebungen.laden(wade.id).description == "Meine Fassung"
    dialoge[-1].actions[1].on_click()
    assert state.uebungen.laden(wade.id).description != "Meine Fassung"

    entfernen = next(
        c for v in ansicht.controls for c in alle(v) if isinstance(c, ft.OutlinedButton)
    )
    entfernen.on_click()
    frage = dialoge[-1]
    frage.actions[1].on_click()
    assert state.pakete.alle() == [] and state.uebungen.alle() == []
    asyncio.run(frage.on_dismiss(None))  # Flutter meldet: Dialog zu — erst dann zurück
    assert page.route == "/pakete"

    manager = pakete_view(page, state)
    assert "ENTFERNT" in texte(manager)
    wieder = next(
        c
        for v in manager.controls
        for c in alle(v)
        if isinstance(c, ft.OutlinedButton) and c.content == "Wieder installieren"
    )
    wieder.on_click()
    frage = dialoge[-1]
    assert frage.title.value == "„Standard“ wieder installieren?"
    frage.actions[1].on_click()
    assert [p.name for p, _ in state.pakete.alle()] == ["Standard"]
    assert state.uebungen.laden(wade.id) is not None


def test_uebung_zeigt_geaendert_und_setzt_zurueck(page, state) -> None:
    dialoge: list = []
    page.show_dialog = dialoge.append
    page.pop_dialog = lambda: None
    wade = state.uebungen.laden(seed_id("wadenheben"))
    wade.description = "Meine Fassung"
    state.uebungen.speichern(wade)

    ansicht = uebung_detail(page, state, wade, ft.UrlLauncher())
    assert "  (Paket „Standard“, geändert)" in texte(ansicht)
    knopf = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.TextButton) and c.content == "Auf Paketstand zurücksetzen"
    )
    knopf.on_click()
    dialoge[-1].actions[1].on_click()
    assert state.pakete.abweichungen(state.uebungen.laden(wade.id)) == []
