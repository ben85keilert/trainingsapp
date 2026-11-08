"""Plan-Editor mit Reitern und der Reiter „Ablauf“ (Ben, 8.11.2026 abends,
`docs/plan_verzweigungen.md` §8).

Reiter Plan · Uhren immer; der Schalter „Der Reihe nach | Mit Abzweigen“ bringt „Ablauf“. Die
Palette zeigt die Planübungen mit Nummer, Slots nehmen sie auf; unter dem Bild Routing, Neuer
Slot, Beiname, Aus Plan nehmen und Neu anordnen. Das Wege-Blatt stellt alle Wege einer Übung ein
und spiegelt den Hauptweg in ihre Bedingung — dasselbe Formular in „Im Plan einstellen“.
Entfernen fragt nach Lücke oder Nachfolgereihe; die Lagen bleiben stehen bis „Neu anordnen“."""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Seite  # noqa: E402
from trainingsapp.core import ablauf as ab  # noqa: E402
from trainingsapp.core import bedingung as bd  # noqa: E402
from trainingsapp.core.ablauf import Kante  # noqa: E402
from trainingsapp.core.bedingung import WDH, Bedingung  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.ablauf import (  # noqa: E402
    ablauf_view,
    ablauf_zusammenfassung,
    entfernen_fragen,
)
from trainingsapp.ui.views.plan import plan_view  # noqa: E402
from trainingsapp.ui.views.plan_einstellen import plan_einstellen  # noqa: E402


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
        "items",
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


def _menue(c, text: str) -> ft.PopupMenuItem:
    return next(x for x in _alle(c) if isinstance(x, ft.PopupMenuItem) and x.content == text)


def _klick(handler, *args):
    ergebnis = handler(*args)
    if inspect.isawaitable(ergebnis):
        asyncio.run(ergebnis)


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
    uebungen = [Exercise(name=n) for n in ("Wandsitz", "Kniebeuge", "Planke", "Dehnung")]
    for u in uebungen:
        state.uebungen.speichern(u)
    plan = Plan(name="Rumpf", subject_id=state.profil.id)
    plan.items = [PlanItem(exercise_id=u.id) for u in uebungen]
    plan.items[0].bedingung = Bedingung(WDH, 12)
    state.plaene.speichern(plan)
    yield state, state.plaene.laden(plan.id)
    state.schliessen()


def test_reiter_und_schalter_bringen_den_ablauf(umgebung) -> None:
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    editor = plan_view(_Seite(), state, plan, bearbeiten=True, basis=basis)
    reiter = [
        x.data
        for x in _alle(editor)
        if isinstance(x, ft.Container) and isinstance(x.data, tuple) and x.data[:1] == ("reiter",)
    ]
    assert reiter == [("reiter", ""), ("reiter", "uhren")]
    assert ablauf_zusammenfassung(plan).startswith("Der Reihe nach")
    # Nummern an den Übungen der Liste (Frage 5)
    texte = _texte(editor)
    assert {"1", "2", "3", "4"} <= set(texte)
    schalter = next(x for x in _alle(editor) if isinstance(x, ft.SegmentedButton))
    schalter.selected = ["verzweigt"]
    schalter.on_change(SimpleNamespace(control=schalter))
    plan = state.plaene.laden(plan.id)
    iw, ik, ip, id_ = (it.id for it in plan.items)
    assert plan.ablauf.an and plan.ablauf.start == iw
    kanten = [(k.von, k.nach, k.ausloeser, k.n) for k in plan.ablauf.kanten]
    assert kanten == [(iw, ik, ab.WDH, 12), (ik, ip, ab.FREI, 0), (ip, id_, ab.FREI, 0)]
    assert ablauf_zusammenfassung(plan).startswith("Mit Abzweigen: 3 Wege")
    editor = plan_view(_Seite(), state, plan, bearbeiten=True, basis=basis)
    _mit_daten(editor, "reiter", "ablauf")
    # Zurück auf „Der Reihe nach“: die Zeichnung bleibt gespeichert
    schalter = next(x for x in _alle(editor) if isinstance(x, ft.SegmentedButton))
    schalter.selected = ["linear"]
    schalter.on_change(SimpleNamespace(control=schalter))
    plan = state.plaene.laden(plan.id)
    assert not plan.ablauf.an and len(plan.ablauf.kanten) == 3


def test_palette_slot_routing_und_ziel_antippen(umgebung) -> None:
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ik, ip))))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    assert ansicht.route == f"{basis}/ablauf" and ansicht.scroll is None
    # Palette: die Planübungen mit Nummer — die Dehnung ist noch frei (nicht im Bild)
    ziehbar = [x for x in _alle(ansicht) if isinstance(x, ft.Draggable)]
    assert [x.data for x in ziehbar] == [iw, ik, ip, id_]
    assert all(x.affinity == ft.Axis.VERTICAL for x in ziehbar)
    assert "frei" in _texte(ansicht)
    _klick(
        next(
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.IconButton) and x.tooltip == "Übung hinzufügen"
        ).on_click,
        None,
    )
    assert seite.routen[-1] == f"{basis}/hinzufuegen"
    # Ohne Wahl unter dem Bild nur der Hinweis
    assert any(t.startswith("Tipp auf eine Übung im Bild") for t in _texte(ansicht))
    # Planke wählen → Knöpfe; „Neuer Slot“ → Ablage; die Dehnung hinein
    _mit_daten(ansicht, "knoten", ip).content.on_tap(None)
    assert state.ablauf_wahl[plan.id] == ip
    texte = _texte(ansicht)
    assert "3 · Planke" in texte and "Routing" in texte
    for text in ("Neuer Slot", "Beiname", "Aus Plan nehmen", "Neu anordnen"):
        _knopf(ansicht, text)
    _knopf(ansicht, "Neuer Slot").on_click(None)
    assert state.ablauf_slots[plan.id] == [ip]
    ziel = next(x for x in _alle(ansicht) if isinstance(x, ft.DragTarget) and x.on_will_accept)
    ziel.on_accept(SimpleNamespace(src=SimpleNamespace(data=id_)))
    plan = state.plaene.laden(plan.id)
    assert any(k.von == ip and k.nach == id_ for k in plan.ablauf.kanten)
    assert state.ablauf_slots[plan.id] == [] and state.ablauf_wahl[plan.id] == id_
    assert len(plan.items) == 4  # keine neue Planübung — die Nummer ist die feste ID
    # Routing an der Dehnung: ◀ zurück und eine Frage dahinter
    _klick(_menue(ansicht, "◀ Zurück, wo ich herkam").on_click, None)
    _klick(_menue(ansicht, "Frage dahinter").on_click, None)
    plan = state.plaene.laden(plan.id)
    assert any(k.von == id_ and k.zurueck for k in plan.ablauf.kanten)
    (frage,) = plan.ablauf.fragen
    assert any(k.von == id_ and k.nach == frage.id for k in plan.ablauf.kanten)
    assert isinstance(seite.dialoge[-1], ft.BottomSheet)  # das Fragen-Blatt
    # „Weg zu einer Übung im Bild …“ an der Kniebeuge, dann den Wandsitz antippen
    _mit_daten(ansicht, "knoten", ik).content.on_tap(None)
    _klick(_menue(ansicht, "Weg zu einer Übung im Bild …").on_click, None)
    assert any(t.startswith("Ziel im Bild antippen") for t in _texte(ansicht))
    _mit_daten(ansicht, "knoten", iw).content.on_tap(None)
    plan = state.plaene.laden(plan.id)
    assert any(k.von == ik and k.nach == iw for k in plan.ablauf.kanten)
    # Palette antippen mit gewähltem Knoten: ein Weg dorthin
    state.ablauf_wahl[plan.id] = iw
    next(
        x for x in _alle(ansicht) if isinstance(x, ft.Draggable) and x.data == ip
    ).content.on_click(None)
    plan = state.plaene.laden(plan.id)
    assert any(k.von == iw and k.nach == ip for k in plan.ablauf.kanten)


def test_wege_blatt_spiegelt_in_die_bedingung_und_im_plan_einstellen(umgebung) -> None:
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ip, id_))))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    _mit_daten(ansicht, "knoten", iw).content.on_tap(None)
    _klick(_menue(ansicht, "Wege einstellen …").on_click, None)
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    texte = _texte(blatt)
    assert "KOMMT VON" in texte and "WEITER ZU" in texte and "Hauptweg" in texte
    assert "Start des Workouts" in texte
    # Ein zweiter Weg: „Rücken tut weh“ → Dehnung
    _knopf(blatt, "Weg").on_click(None)
    blatt_texte = _texte(blatt)
    assert "Weg 2" in blatt_texte
    ziele = [x for x in _alle(blatt) if isinstance(x, ft.Dropdown) and x.label == "Weiter zu"]
    ziele[1].value = id_
    ziele[1].on_select(SimpleNamespace(control=ziele[1]))
    beschriftungen = [
        x
        for x in _alle(blatt)
        if isinstance(x, ft.TextField) and str(x.label).startswith("Beschriftung")
    ]
    beschriftungen[1].value = "Rücken tut weh"
    beschriftungen[1].on_blur(SimpleNamespace(control=beschriftungen[1]))
    # Hauptweg auf Skala ≥ 7, Pflicht
    chips = [x for x in _alle(blatt) if isinstance(x, ft.Chip) and x.label.value == "Skala"]
    chips[0].on_select(None)
    pflicht = next(x for x in _alle(blatt) if isinstance(x, ft.Switch))
    pflicht.value = True
    pflicht.on_change(SimpleNamespace(control=pflicht))
    _klick(blatt.on_dismiss, None)  # Blätter speichern beim Schließen
    plan = state.plaene.laden(plan.id)
    wege = plan.ablauf.von(iw)
    assert [(k.nach, k.ausloeser, k.n, k.pflicht, k.text) for k in wege] == [
        (ik, ab.SKALA, 7, True, ""),
        (id_, ab.FREI, 0, False, "Rücken tut weh"),
    ]
    # Gespiegelt: die Bedingung des Wandsitzes folgt dem Hauptweg
    w = state.plaene.item_laden(iw)
    assert (w.bedingung.art, w.bedingung.n, w.bedingung.hart) == (bd.SKALA, 7, True)
    # Dasselbe in „Im Plan einstellen“ — mit Herkunft und Nummern
    u = state.uebungen.laden(plan.items[3].exercise_id)
    seite2 = plan_einstellen(seite, state, plan, plan.items[3], u, basis=basis)
    texte = _texte(seite2)
    assert "WEGE IM ABLAUF" in texte and "KOMMT VON" in texte
    assert any(t.startswith("1 · Wandsitz") and "Rücken tut weh" in t for t in texte)
    assert any(t.startswith("3 · Planke") for t in texte)


def test_entfernen_fragt_luecke_oder_nachfolgereihe(umgebung) -> None:
    state, plan = umgebung
    iw, ik, ip, id_ = (it.id for it in plan.items)
    state.plaene.ablauf_setzen(
        plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ik, ip), Kante(ip, id_)))
    )
    seite = _Seite()
    neu: list[bool] = []
    entfernen_fragen(seite, state, plan.id, ik, lambda: neu.append(True))
    dialog = seite.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog)
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    assert set(zeilen) == {
        "Lücke schließen",
        "Mit der Nachfolgereihe löschen",
        "Nur diese entfernen",
    }
    assert zeilen["Lücke schließen"].subtitle.value == "1 · Wandsitz → 3 · Planke verbinden"
    _klick(zeilen["Lücke schließen"].on_click, None)
    _klick(dialog.on_dismiss, None)
    plan = state.plaene.laden(plan.id)
    assert [it.id for it in plan.items] == [iw, ip, id_] and neu
    assert [(k.von, k.nach) for k in plan.ablauf.kanten] == [(iw, ip), (ip, id_)]
    # Nachfolgereihe: die Planke nimmt die Dehnung mit
    entfernen_fragen(seite, state, plan.id, ip, lambda: None)
    dialog = seite.dialoge[-1]
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    assert zeilen["Mit der Nachfolgereihe löschen"].subtitle.value == "auch: 3 · Dehnung"
    _klick(zeilen["Mit der Nachfolgereihe löschen"].on_click, None)
    plan = state.plaene.laden(plan.id)
    assert [it.id for it in plan.items] == [iw] and plan.ablauf.kanten == ()


def test_lagen_bleiben_bis_neu_anordnen(umgebung) -> None:
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, _ip, id_ = (it.id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik),)))
    plan = state.plaene.laden(plan.id)
    ansicht = ablauf_view(_Seite(), state, plan, basis)
    vorher = dict(state.ablauf_lagen[plan.id])
    assert vorher[iw] == vorher[ik].__class__(0.0, 0)
    # Neuer Weg vom Wandsitz: Wandsitz und Kniebeuge bleiben, wo sie sind
    state.ablauf_wahl[plan.id] = iw
    next(
        x for x in _alle(ansicht) if isinstance(x, ft.Draggable) and x.data == id_
    ).content.on_click(None)
    nachher = state.ablauf_lagen[plan.id]
    assert nachher[iw] == vorher[iw] and nachher[ik] == vorher[ik] and id_ in nachher
    # „Neu anordnen“: der Wandsitz mittig über seinen zwei Kindern
    _knopf(ansicht, "Neu anordnen").on_click(None)
    neu = state.ablauf_lagen[plan.id]
    assert neu[iw].x == (neu[ik].x + neu[id_].x) / 2
