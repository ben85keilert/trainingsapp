"""Oberfläche zu Übungspaketen und Tag-Auswahl (Ben, 14.10.2026).

Wie `test_ui_smoke.py`: Ansichten bauen, Handler direkt aufrufen. Läuft nur
mit `flet` (nicht in der CI-Gruppe `ci`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.pakete import GRUNDAUSSTATTUNG  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
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
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.OutlinedButton) and c.content == "Paket entfernen"
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


def test_paket_entfernen_fragt_bei_planbezug_und_kopiert(page, state) -> None:
    """Steht eine Paketübung in einem Plan, zeigt die Rückfrage „Teil von Plan …“ mit
    Kästchen „kopieren“; angekreuzt bleibt eine eigene Kopie im Plan (Ben, 15.10.2026)."""
    from trainingsapp.core.models import PlanItem
    from trainingsapp.ui.views.pakete import paket_view

    dialoge: list = []
    page.show_dialog = dialoge.append
    page.pop_dialog = lambda: None
    wade = state.uebungen.laden(seed_id("wadenheben"))
    plan = Plan(name="Rücken", items=[PlanItem(exercise_id=wade.id)])
    state.plaene.speichern(plan)

    ansicht = paket_view(page, state, "/pakete", state.pakete.laden(GRUNDAUSSTATTUNG))
    entfernen = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.OutlinedButton) and c.content == "Paket entfernen"
    )
    entfernen.on_click()
    frage = dialoge[-1]
    kaestchen = [c for c in alle(frage.content) if isinstance(c, ft.Checkbox)]
    assert len(kaestchen) == 1 and "Teil von Plan „Rücken“" in kaestchen[0].label
    assert kaestchen[0].value is True
    frage.actions[1].on_click()
    assert state.pakete.alle() == []
    items = state.plaene.laden(plan.id).items
    assert len(items) == 1 and items[0].exercise_id != wade.id
    kopie = state.uebungen.laden(items[0].exercise_id)
    assert kopie.name == wade.name and kopie.package_id is None

    # Beim Import einer Datei mit der Standard-ID sagt die Rückfrage es deutlich
    from trainingsapp.ui.views.pakete import import_rueckfrage

    state.pakete.importieren(state.pakete.inhalt(GRUNDAUSSTATTUNG))  # wieder installieren
    inhalt = state.pakete.inhalt(GRUNDAUSSTATTUNG)
    dialog = import_rueckfrage(page, state, inhalt, state.pakete.vorschau(inhalt))
    assert any("Ersetzt das mitgelieferte Paket" in t for t in texte(dialog.content))


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


def test_paket_deaktivieren_und_groesse(page, state) -> None:
    """Deaktivieren nimmt alles aus Katalog und Plänen, ohne zu löschen; Zeile nennt die Größe."""
    from trainingsapp.ui.views.pakete import paket_view

    dialoge: list = []
    page.show_dialog = dialoge.append
    gezeichnet: list[int] = []
    state.neu_zeichnen = lambda: gezeichnet.append(1)
    ansicht = paket_view(page, state, "/pakete", state.pakete.laden(GRUNDAUSSTATTUNG))
    assert any("kB" in t for t in texte(ansicht))
    knopf = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.OutlinedButton) and c.content == "Deaktivieren"
    )
    knopf.on_click()
    assert state.uebungen.alle() == [] and gezeichnet == [1]
    assert state.pakete.laden(GRUNDAUSSTATTUNG).deaktiviert is not None
    ansicht = paket_view(page, state, "/pakete", state.pakete.laden(GRUNDAUSSTATTUNG))
    assert "deaktiviert" in " ".join(texte(ansicht))
    aktivieren = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.OutlinedButton) and c.content == "Aktivieren"
    )
    aktivieren.on_click()
    assert len(state.uebungen.alle()) > 0
    liste = pakete_view(page, state)
    assert "Standard" in texte(liste)


def test_entfallene_dialog_uebernimmt_oder_loescht(page, state) -> None:
    import asyncio

    from trainingsapp.core.pakete import paket_lesen
    from trainingsapp.ui.views.pakete import entfallene_dialog, paket_view

    dialoge: list = []
    page.show_dialog = dialoge.append
    page.pop_dialog = lambda: None
    roh = {
        "paket": {"name": "Qigong", "version": 1},
        "exercises": [
            {"key": "baum", "name": "Baum", "spec": "halten"},
            {"key": "lotus", "name": "Lotus", "spec": "halten"},
            {"key": "kranich", "name": "Kranich", "spec": "halten"},
        ],
    }
    inhalt = paket_lesen(roh)
    state.pakete.importieren(inhalt)
    baum, lotus, kranich = inhalt.uebungen
    plan = Plan(name="Morgens", items=[PlanItem(exercise_id=lotus.id)])
    state.plaene.speichern(plan)
    roh["paket"]["version"] = 2
    roh["exercises"] = roh["exercises"][:1]
    state.pakete.importieren(paket_lesen(roh))
    paket = state.pakete.laden(inhalt.paket.id)

    ansicht = paket_view(page, state, "/pakete", paket)
    assert "NICHT MEHR IM PAKET" in texte(ansicht)
    entscheiden = next(
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.FilledButton) and c.content == "Entscheiden"
    )
    entscheiden.on_click()
    frage = dialoge[-1]
    kaestchen = [c for c in alle(frage.content) if isinstance(c, ft.Checkbox)]
    assert [k.label.split(" — ")[0] for k in kaestchen] == ["Kranich", "Lotus"]
    assert "Teil von Plan „Morgens“" in kaestchen[1].label
    kaestchen[0].value = False  # Kranich löschen, Lotus übernehmen
    frage.actions[1].on_click()
    asyncio.run(frage.on_dismiss(None))
    assert state.uebungen.laden(kranich.id) is None  # Papierkorb
    lotus_neu = state.uebungen.laden(lotus.id)
    assert lotus_neu is not None and lotus_neu.package_id is None
    assert [i.exercise_id for i in state.plaene.laden(plan.id).items] == [lotus.id]
    assert state.pakete.entfallene(paket.id) == []
    assert state.uebungen.laden(baum.id).package_id == paket.id

    # Direkt aufrufbar (Start-Dialog), leer bleibt leer
    state.entfallene = [(paket, [], [])]
    dialog = entfallene_dialog(page, state, paket, [], [])
    dialog.actions[1].on_click()
    assert state.entfallene == []
