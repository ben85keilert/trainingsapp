"""Der Reiter „Ablauf“ (G3, `docs/plan_verzweigungen.md` §8, Skizzen E1–E3): Zeile im Plan-Editor,
Einschalten übersetzt die Bedingungen in Kanten, Palette und Slots legen Planübungen an, das
„+“-Menü legt Frage, Schleife und ◀ zurück an, „Bestehende wählen“ zieht eine Kante zum
angetippten Knoten, das Kanten-Blatt stellt Auslöser und Pflicht ein, „Als Kette“ schaltet ab —
und das Entfernen einer Planübung nimmt ihre Kanten mit."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Seite  # noqa: E402
from trainingsapp.core import ablauf as ab  # noqa: E402
from trainingsapp.core.bedingung import WDH, Bedingung, Weg  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.ui.components.ablaufbild import Slot  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.ablauf import ablauf_view, ablauf_zusammenfassung  # noqa: E402
from trainingsapp.ui.views.plan import plan_view  # noqa: E402
from trainingsapp.ui.views.plan_uhren import plan_uhren_view  # noqa: E402


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "label",
        "leading",
        "appbar",
        "actions",
        "title",
        "subtitle",
        "header",
        "footer",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if isinstance(x, knoepfe):
            beschriftung = x.content.value if isinstance(x.content, ft.Text) else x.content
            if beschriftung == text:
                return x
    raise AssertionError(f"kein Knopf {text!r}")


def _mit_daten(c, *daten):
    return next(x for x in _alle(c) if isinstance(x, ft.Container) and x.data == daten)


def _zeile(dialog, titel: str) -> ft.ListTile:
    return next(
        x
        for x in _alle(dialog)
        if isinstance(x, ft.ListTile) and isinstance(x.title, ft.Text) and x.title.value == titel
    )


class _Seite(Seite):
    """Merkt sich Dialoge und Routen."""

    def __init__(self) -> None:
        super().__init__()
        self.dialoge: list = []
        self.routen: list[str] = []

    def show_dialog(self, d) -> None:
        self.dialoge.append(d)

    async def push_route(self, route: str) -> None:
        self.routen.append(route)


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    w = Exercise(name="Wandsitz")
    k = Exercise(name="Kniebeuge")
    d = Exercise(name="Dehnung Beine")
    for u in (w, k, d):
        state.uebungen.speichern(u)
    plan = Plan(name="Rumpf", subject_id=state.profil.id)
    plan.items = [
        PlanItem(exercise_id=w.id),
        PlanItem(exercise_id=k.id),
        PlanItem(exercise_id=d.id),
    ]
    plan.items[0].bedingung = Bedingung(WDH, 12, wege=(Weg(plan.items[2].id, "krampft"),))
    state.plaene.speichern(plan)
    yield state, state.plaene.laden(plan.id), (w, k, d)
    state.schliessen()


def test_zeile_im_editor_und_einschalten_uebersetzt_bedingungen(umgebung) -> None:
    state, plan, _u = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    editor = plan_view(_Seite(), state, plan, bearbeiten=True, basis=basis)
    zeile = next(
        x for x in _alle(editor) if isinstance(x, ft.ListTile) and x.title.value == "Ablauf"
    )
    assert zeile.subtitle.value == "aus — der Plan läuft als Kette"
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    assert ansicht.route == f"{basis}/ablauf"
    texte = _texte(ansicht)
    assert "ABLAUF ZEICHNEN" in texte  # Titel der Einführung
    assert "Die Bedingungen und Wege von heute werden dabei in Kanten übersetzt." in texte
    _knopf(ansicht, "Ablauf zeichnen").on_click(None)
    plan = state.plaene.laden(plan.id)
    assert plan.ablauf.an and plan.ablauf.start == plan.items[0].id
    kanten = [(k.von, k.nach, k.ausloeser, k.n, k.text) for k in plan.ablauf.kanten]
    iw, ik, id_ = (i.id for i in plan.items)
    assert kanten == [
        (iw, ik, ab.WDH, 12, ""),
        (iw, id_, ab.FREI, 0, "krampft"),
        (ik, id_, ab.FREI, 0, ""),
    ]
    assert ablauf_zusammenfassung(plan) == "3 Kanten"
    # Danach zeigt die Seite Palette, Zeichnung und Reiter; der Uhrenplan den Reiter „Ablauf“
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    texte = _texte(ansicht)
    assert "ÜBUNGEN · NACH UNTEN IN EINEN SLOT ZIEHEN" in texte and "Start" in texte
    # Die Seite scrollt nicht (sonst gewönne das Scrollen gegen das Schieben der Zeichnung),
    # die Palette greift senkrecht und scrollt waagerecht, die Zeichnung füllt den Rest
    assert ansicht.scroll is None
    ziehbar = [x for x in _alle(ansicht) if isinstance(x, ft.Draggable)]
    assert ziehbar and all(x.affinity == ft.Axis.VERTICAL for x in ziehbar)
    viewer = next(x for x in _alle(ansicht) if isinstance(x, ft.InteractiveViewer))
    rahmen = next(x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.content is viewer)
    assert rahmen.expand and viewer.height is None
    _mit_daten(ansicht, "reiter", "ablauf")
    uhren = plan_uhren_view(seite, state, plan, basis)
    _mit_daten(uhren, "reiter", "ablauf")
    # „Als Kette“ schaltet ab, die Kanten bleiben
    _knopf(ansicht, "Als Kette").on_click(None)
    plan = state.plaene.laden(plan.id)
    assert not plan.ablauf.an and len(plan.ablauf.kanten) == 3


def test_plus_menue_slot_frage_schleife_und_bestehende(umgebung) -> None:
    state, plan, (_w, k, _d) = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, id_ = (i.id for i in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.kette([iw, ik, id_]))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    # Knoten wählen → „+“ erscheint
    knoten = next(x for x in _alle(ansicht) if isinstance(x, ft.GestureDetector))
    assert ansicht is not None and knoten is not None
    _mit_daten(ansicht, "knoten", iw).content.on_tap(None)
    assert state.ablauf_wahl[plan.id] == iw
    ansicht = ablauf_view(seite, state, plan, basis)
    _mit_daten(ansicht, "plus", iw).on_click(None)
    dialog = seite.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog)
    # Neuer Slot → ein leerer Platz unter dem Wandsitz; eine Übung fällt hinein
    _zeile(dialog, "Neuer Slot").on_click(None)
    asyncio.run(dialog.on_dismiss(None))
    assert state.ablauf_slots[plan.id] == [iw]
    ansicht = ablauf_view(seite, state, plan, basis)
    ziel = next(x for x in _alle(ansicht) if isinstance(x, ft.DragTarget))
    ziel.on_accept(SimpleNamespace(src=SimpleNamespace(data=k.id)))
    plan = state.plaene.laden(plan.id)
    assert len(plan.items) == 4 and plan.items[-1].exercise_id == k.id
    neu = plan.items[-1].id
    assert any(x.von == iw and x.nach == neu for x in plan.ablauf.kanten)
    assert state.ablauf_slots[plan.id] == [] and state.ablauf_wahl[plan.id] == neu
    # Frage am neuen Knoten
    ansicht = ablauf_view(seite, state, plan, basis)
    _mit_daten(ansicht, "plus", neu).on_click(None)
    dialog = seite.dialoge[-1]
    _zeile(dialog, "Frage (Entscheidung)").on_click(None)
    asyncio.run(dialog.on_dismiss(None))
    plan = state.plaene.laden(plan.id)
    assert len(plan.ablauf.fragen) == 1
    frage = plan.ablauf.fragen[0]
    assert any(x.von == neu and x.nach == frage.id for x in plan.ablauf.kanten)
    assert isinstance(seite.dialoge[-1], ft.BottomSheet)  # das Fragen-Blatt öffnet gleich
    # Schleife und ◀ zurück an der Dehnung
    state.ablauf_wahl[plan.id] = id_
    for titel in ("Noch einmal (Schleife)", "◀ Zurück, wo ich herkam"):
        ansicht = ablauf_view(seite, state, plan, basis)
        _mit_daten(ansicht, "plus", id_).on_click(None)
        dialog = seite.dialoge[-1]
        _zeile(dialog, titel).on_click(None)
        asyncio.run(dialog.on_dismiss(None))
    plan = state.plaene.laden(plan.id)
    assert any(x.schleife and x.von == id_ for x in plan.ablauf.kanten)
    assert any(x.zurueck and x.von == id_ for x in plan.ablauf.kanten)
    # Bestehende wählen: von der Dehnung zum Wandsitz (Rückkante)
    ansicht = ablauf_view(seite, state, plan, basis)
    _mit_daten(ansicht, "plus", id_).on_click(None)
    dialog = seite.dialoge[-1]
    _zeile(dialog, "Bestehende Übung wählen").on_click(None)
    asyncio.run(dialog.on_dismiss(None))
    # dieselbe Ansicht zeichnet sich neu (die Wahl lebt in ihr, wie in der App)
    assert any("Zielknoten antippen" in t for t in _texte(ansicht))
    _mit_daten(ansicht, "knoten", iw).content.on_tap(None)
    plan = state.plaene.laden(plan.id)
    assert any(x.von == id_ and x.nach == iw for x in plan.ablauf.kanten)
    # Entfernen nimmt die Kanten mit
    state.plaene.uebung_entfernen(id_)
    plan = state.plaene.laden(plan.id)
    assert not any(id_ in (x.von, x.nach) for x in plan.ablauf.kanten)
    assert ablauf_zusammenfassung(plan).startswith("3 Kanten")


def test_kanten_blatt_stellt_ausloeser_pflicht_und_ziel_ein(umgebung) -> None:
    state, plan, _u = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, id_ = (i.id for i in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.kette([iw, ik, id_]))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    _mit_daten(ansicht, "kante", iw, ik).on_click(None)
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    texte = _texte(blatt)
    assert "WANN GEHT ES DIESEN WEG?" in texte and "Pflicht" in texte
    chips = {c.label.value: c for c in _alle(blatt) if isinstance(c, ft.Chip)}
    chips["Skala ≥ …"].on_select(None)
    schalter = next(x for x in _alle(blatt) if isinstance(x, ft.Switch))
    schalter.value = True
    schalter.on_change(SimpleNamespace(control=schalter))
    felder = {f.label: f for f in _alle(blatt) if isinstance(f, ft.TextField) and f.label}
    felder["Beschriftung — wann ist dieser Weg gemeint?"].value = "Beine krampfen"
    felder["Beschriftung — wann ist dieser Weg gemeint?"].on_blur(
        SimpleNamespace(control=felder["Beschriftung — wann ist dieser Weg gemeint?"])
    )
    _knopf(blatt, "Übernehmen").on_click(None)
    plan = state.plaene.laden(plan.id)
    kante = plan.ablauf.von(iw)[0]
    assert (kante.ausloeser, kante.n, kante.pflicht, kante.text) == (
        ab.SKALA,
        7,
        True,
        "Beine krampfen",
    )
    # Löschen
    ansicht = ablauf_view(seite, state, plan, basis)
    _mit_daten(ansicht, "kante", iw, ik).on_click(None)
    _knopf(seite.dialoge[-1], "Kante löschen").on_click(None)
    plan = state.plaene.laden(plan.id)
    assert plan.ablauf.von(iw) == []
    texte = _texte(ablauf_view(seite, state, plan, basis))
    assert any(t.startswith("Kniebeuge ist bei Bedarf, aber niemand ruft sie.") for t in texte)
    # Slot-Platzhalter rechnet die Lage ohne Fehler
    assert Slot(iw).von == iw
