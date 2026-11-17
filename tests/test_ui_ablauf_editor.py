"""Plan-Editor mit Reitern und der Reiter „Ablauf“ (Ben, 8.11.2026 abends,
`docs/plan_verzweigungen.md` §8).

Reiter Plan · Uhren immer; der Schalter „Der Reihe nach | Mit Abzweigen“ bringt „Ablauf“. Die
Palette ist ein Vorrat an Übungen (eine Kachel je Übung, „2×“ bei Mehrfachverwendung — Ben,
16.11.2026), am Ende die Kachel „Frage“. **Bedient wird im Bild** (Ben, 16.11.2026: „Alles, was
sich auslagern lässt vom Routingmenü in die Grafik, wird ausgelagert“): Der Punkt unter einer
Übung, auf eine andere gezogen, ist ein Weg (auf sich selbst: noch einmal; „Ende“ und „zurück“
als Ziele am Rand; von „Start“: der Start), eine Kachel auf eine Übung gezogen eine neue
dahinter; gedrückt halten öffnet das Menü an der Übung; der Punkt eines Wegs zeigt seine Leiste
unter dem Bild. Das Wege-Blatt stellt alle Wege einer Übung ein und spiegelt den Hauptweg in
ihre Bedingung — dasselbe Formular in „Im Plan einstellen“. Entfernen fragt nach Lücke oder
Nachfolgereihe; die Lagen bleiben stehen bis „Neu anordnen“; eine Warnung steht, wenn der Plan
hängen bleiben kann."""

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
from trainingsapp.ui.components import ablaufbild as abbild  # noqa: E402
from trainingsapp.ui.components.ablaufbild import (  # noqa: E402
    GRUPPE_KACHEL,
    GRUPPE_WEG,
    KNOTEN,
    START,
)
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.ablauf import (  # noqa: E402
    FRAGE_KACHEL,
    KACHELN_HOECHSTENS,
    MENUE_NACH_OBEN_AB,
    ablauf_speichern,
    ablauf_view,
    ablauf_zusammenfassung,
    entfernen_fragen,
)
from trainingsapp.ui.views.plan import plan_view  # noqa: E402
from trainingsapp.ui.views.plan_einstellen import plan_einstellen  # noqa: E402
from trainingsapp.ui.views.workout import workout_view  # noqa: E402


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


def _knoten(c, knoten: str) -> ft.Container:
    """Der Knoten im Bild — eine Übung oder eine Frage."""
    return next(
        x
        for x in _alle(c)
        if isinstance(x, ft.Container) and x.data in (("knoten", knoten), ("frage", knoten))
    )


def _gesten(c, knoten: str) -> ft.GestureDetector:
    """Tippen und Gedrückthalten an einem Knoten — er steckt in seinen zwei Ablagen."""
    return next(x for x in _alle(_knoten(c, knoten)) if isinstance(x, ft.GestureDetector))


def _ablage(c, knoten: str, gruppe: str) -> ft.DragTarget:
    """Der Knoten als Ablage für einen Punkt (`GRUPPE_WEG`) oder eine Kachel der Leiste."""
    return next(
        x for x in _alle(_knoten(c, knoten)) if isinstance(x, ft.DragTarget) and x.group == gruppe
    )


def _punkt(c, von: str) -> ft.Draggable:
    """Der Punkt eines Knotens (oder von „Start“) — das, was sich ziehen lässt."""
    punkt = _mit_daten(c, "punkt", von).content
    assert isinstance(punkt, ft.Draggable) and punkt.group == GRUPPE_WEG and punkt.data == von
    return punkt


def _ziel(c, nach: str) -> ft.DragTarget:
    """„Ende“ oder „zurück“ am unteren Rand des Bildes."""
    return next(x for x in _alle(c) if isinstance(x, ft.DragTarget) and x.data == ("ziel", nach))


def _ziehen(c, von: str, nach: str) -> None:
    """Den Punkt von ``von`` ziehen und fallen lassen: auf einen Knoten — oder auf „Ende“ bzw.
    „zurück“ (`core.ablauf.ENDE`, `ZURUECK`)."""
    punkt = _punkt(c, von)
    _klick(punkt.on_drag_start, None)
    ablage = _ziel(c, nach) if nach in (ab.ENDE, ab.ZURUECK) else _ablage(c, nach, GRUPPE_WEG)
    _klick(ablage.on_accept, SimpleNamespace(src=punkt))


def _menue_oeffnen(c, knoten: str) -> list[str]:
    """Gedrückt halten an einem Knoten — zurück: die Einträge seines Menüs."""
    _klick(_gesten(c, knoten).on_long_press, None)
    karte = _mit_daten(c, "menue", knoten)
    return [
        x.data[1]
        for x in _alle(karte)
        if isinstance(x, ft.Container)
        and isinstance(x.data, tuple)
        and x.data[:1] == ("menue_eintrag",)
    ]


def _menue(c, knoten: str, text: str) -> None:
    """Gedrückt halten an einem Knoten und einen Eintrag seines Menüs wählen."""
    assert text in _menue_oeffnen(c, knoten)
    _klick(_mit_daten(c, "menue_eintrag", text).on_click, None)


def _schirm(c) -> ft.GestureDetector:
    """Der Schirm hinter dem offenen Menü — er fängt den Tipp, der es schließt."""
    return next(x for x in _alle(c) if isinstance(x, ft.GestureDetector) and x.data == ("schirm",))


def _leiste(c) -> ft.Container | None:
    """Die Leiste des gewählten Wegs unter dem Bild — ``None``, wenn keiner gewählt ist."""
    return next(
        (x for x in _alle(c) if isinstance(x, ft.Container) and x.data == "weg_leiste"), None
    )


def _in_leiste(c, daten):
    """Ein Bedienteil der Weg-Leiste nach seinem ``data``."""
    leiste = _leiste(c)
    assert leiste is not None, "kein Weg gewählt"
    return next(x for x in _alle(leiste) if getattr(x, "data", None) == daten)


def _meldungen(seite) -> list[str]:
    return [t for d in seite.dialoge if isinstance(d, ft.SnackBar) for t in _texte(d)]


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
    assert ablauf_zusammenfassung(plan).startswith("Liste")
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
    # Workout = Ablauf (Ben, 10.11.2026): der Schalter am Plan geht mit, der Ablauf folgt der
    # Liste — gespeichert ist nur das Zeichen dafür
    assert plan.workout and ablauf_zusammenfassung(plan).startswith("Workout: Übung für Übung")
    assert state.plaene.ablauf_laden(plan.id) == ab.Ablauf(an=True)
    editor = plan_view(_Seite(), state, plan, bearbeiten=True, basis=basis)
    _mit_daten(editor, "reiter", "ablauf")
    # Eine neue Planübung gehört dazu, Umordnen ordnet das Workout um
    neu = state.plaene.uebung_hinzufuegen(plan.id, plan.items[0].exercise_id)
    plan = state.plaene.laden(plan.id)
    assert plan.ablauf.kanten[-1].von == id_ and plan.ablauf.kanten[-1].nach == neu.id
    state.plaene.reihenfolge_setzen(plan.id, [ik, iw, ip, id_, neu.id])
    plan = state.plaene.laden(plan.id)
    assert plan.ablauf.start == ik and [k.von for k in plan.ablauf.kanten] == [ik, iw, ip, id_]
    state.plaene.uebung_entfernen(neu.id)
    state.plaene.reihenfolge_setzen(plan.id, [iw, ik, ip, id_])
    plan = state.plaene.laden(plan.id)
    assert [k.nach for k in plan.ablauf.kanten] == [ik, ip, id_]
    # Zurück auf „Liste“: ein Ablauf, der nur der Liste folgte, wird nicht aufgehoben
    schalter = next(x for x in _alle(editor) if isinstance(x, ft.SegmentedButton))
    schalter.selected = ["linear"]
    schalter.on_change(SimpleNamespace(control=schalter))
    plan = state.plaene.laden(plan.id)
    assert not plan.ablauf.an and not plan.workout and plan.ablauf.kanten == ()
    # Ein eigener Ablauf (ein Abzweig) bleibt beim Ausschalten gespeichert und kommt zurück;
    # eine neue Planübung steht dann nur in der Palette
    schalter.selected = ["verzweigt"]
    schalter.on_change(SimpleNamespace(control=schalter))
    plan = state.plaene.laden(plan.id)
    ablauf_speichern(state, plan.id, plan.ablauf.mit_kante(Kante(iw, ip, text="Abkürzung")))
    plan = state.plaene.laden(plan.id)
    assert ablauf_zusammenfassung(plan).startswith("Workout mit eigenem Ablauf: 4 Wege")
    neu = state.plaene.uebung_hinzufuegen(plan.id, plan.items[0].exercise_id)
    plan = state.plaene.laden(plan.id)
    assert len(plan.ablauf.kanten) == 4 and neu.id not in ab.im_bild(
        plan.ablauf, [iw, ik, ip, id_, neu.id]
    )
    state.plaene.uebung_entfernen(neu.id)
    schalter.selected = ["linear"]
    schalter.on_change(SimpleNamespace(control=schalter))
    plan = state.plaene.laden(plan.id)
    assert not plan.ablauf.an and len(plan.ablauf.kanten) == 4


def test_palette_kachel_auf_uebung_frage_und_punkt_ziehen(umgebung) -> None:
    """Was vorher „Neuer Slot“ und das Menü „Routing“ taten, geht im Bild (Ben, 16.11.2026):
    eine Kachel auf eine Übung = neue dahinter, die Kachel „Frage“, der Punkt einer Übung auf
    eine andere = ein Weg."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    uw, uk, up, ud = (it.exercise_id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ik, ip))))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    assert ansicht.route == f"{basis}/ablauf" and ansicht.scroll is None
    # Palette: eine Kachel je Übung — zuerst die vier des Plans (die Dehnung ist noch frei,
    # nicht im Bild), dahinter der Katalog —, fest daneben die Kachel „Frage“
    ziehbar = [
        x for x in _alle(ansicht) if isinstance(x, ft.Draggable) and x.group == GRUPPE_KACHEL
    ]
    assert [x.data for x in ziehbar[:4]] == [uw, uk, up, ud]
    assert ziehbar[-1].data == FRAGE_KACHEL and len(ziehbar) > 5
    assert all(x.affinity == ft.Axis.VERTICAL for x in ziehbar)
    assert "frei" in _texte(ansicht) and _texte(ziehbar[-1]) == ["Frage"]
    # Das Plus ist weg (Ben, 17.11.2026): an seiner Stelle steht der Filter
    assert not [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.tooltip == "Übung hinzufügen"
    ]
    assert not seite.routen
    # Ohne Wahl nennt die Zeile unter dem Bild die Gesten; „Routing“, „Neuer Slot“ und die
    # Knopfzeile gibt es nicht mehr — und kein Flutter-Menü (es reichte den schließenden Tipp
    # an das Darunter weiter)
    assert any(t.startswith("Zieh den Punkt unter einer Übung") for t in _texte(ansicht))
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.PopupMenuButton)]
    for text in ("Neuer Slot", "Beiname", "Aus dem Ablauf nehmen", "Frage ändern"):
        with pytest.raises(AssertionError, match="kein Knopf"):
            _knopf(ansicht, text)
    assert "Routing" not in _texte(ansicht) and not hasattr(state, "ablauf_slots")
    _knopf(ansicht, "Neu anordnen")
    _knopf(ansicht, "Pfad abspielen")
    # Planke antippen wählt sie: ihr Name steht unter dem Bild
    _gesten(ansicht, ip).on_tap(None)
    assert state.ablauf_wahl[plan.id] == ip and "3 · Planke" in _texte(ansicht)
    # Die Kachel „Dehnung“ auf die Planke gezogen: die freie Dehnung kommt dahinter
    _ablage(ansicht, ip, GRUPPE_KACHEL).on_accept(SimpleNamespace(src=ziehbar[3]))
    plan = state.plaene.laden(plan.id)
    assert [k.nach for k in plan.ablauf.von(ip)] == [id_]
    assert state.ablauf_wahl[plan.id] == id_
    assert len(plan.items) == 4  # keine neue Planübung — die freie Dehnung kam ins Bild
    # Die Kachel „Frage“ antippen (die Dehnung ist gewählt): eine Frage dahinter, ihr Blatt
    frage_kachel = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Draggable) and x.data == FRAGE_KACHEL
    )
    _klick(frage_kachel.content.on_click, None)
    plan = state.plaene.laden(plan.id)
    (frage,) = plan.ablauf.fragen
    assert [k.nach for k in plan.ablauf.von(id_)] == [frage.id]
    assert isinstance(seite.dialoge[-1], ft.BottomSheet)  # das Fragen-Blatt
    assert state.ablauf_wahl[plan.id] == frage.id
    # … oder auf eine Übung ziehen: eine zweite Frage hinter der Kniebeuge
    _ablage(ansicht, ik, GRUPPE_KACHEL).on_accept(SimpleNamespace(src=frage_kachel))
    plan = state.plaene.laden(plan.id)
    zweite = next(f for f in plan.ablauf.fragen if f.id != frage.id)
    assert [k.nach for k in plan.ablauf.von(ik)] == [ip, zweite.id]
    assert isinstance(seite.dialoge[-1], ft.BottomSheet)
    # Auf „Start“ gehört keine Frage — nur eine Meldung
    start = _mit_daten(ansicht, "start").content
    start.on_accept(SimpleNamespace(src=frage_kachel))
    assert len(state.plaene.laden(plan.id).ablauf.fragen) == 2
    assert _meldungen(seite)[-1].startswith("Eine Frage kommt hinter eine Übung")
    # Ohne gewählte Übung sagt die Kachel „Frage“, was fehlt
    state.ablauf_wahl[plan.id] = None
    _klick(frage_kachel.content.on_click, None)
    assert _meldungen(seite)[-1].startswith("Erst eine Übung im Bild antippen — die Frage")
    # Der Punkt der Kniebeuge auf den Wandsitz gezogen: ein Weg zwischen zwei Übungen im Bild
    _ziehen(ansicht, ik, iw)
    plan = state.plaene.laden(plan.id)
    assert [k.nach for k in plan.ablauf.von(ik)] == [ip, zweite.id, iw]
    # Palette antippen mit gewähltem Knoten: ein Weg dorthin — die Planke steht schon im Bild,
    # also entsteht eine neue Planübung derselben Übung (Ben, 16.11.2026)
    state.ablauf_wahl[plan.id] = iw
    _klick(_kacheln(ansicht)[up].content.on_click, None)
    plan = state.plaene.laden(plan.id)
    neu = plan.items[-1]
    assert len(plan.items) == 5 and neu.exercise_id == up and neu.id != ip
    assert any(k.von == iw and k.nach == neu.id for k in plan.ablauf.kanten)
    assert not any(k.von == iw and k.nach == ip for k in plan.ablauf.kanten)
    # Ohne gewählte Übung (und mit Start): die Kachel sagt, wohin sie soll
    state.ablauf_wahl[plan.id] = None
    _klick(_kacheln(ansicht)[up].content.on_click, None)
    assert _meldungen(seite)[-1].startswith("Erst eine Übung im Bild antippen — die neue")
    assert len(state.plaene.laden(plan.id).items) == 5


def test_punkt_ziehen_verbindet(umgebung) -> None:
    """Ben, 16.11.2026: „Ziehen von einem Knoten auf eine Übung zum Verbinden“ — jede Übung
    hat unter sich ihren Punkt; auf eine andere gezogen: ein Weg; auf die eigene: noch einmal;
    auf „Ende“ und „zurück“ am unteren Rand; von „Start“ auf eine Übung: der Start. Der neue
    Weg ist gewählt — seine Leiste steht unter dem Bild."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    # Wandsitz → Kniebeuge, Wandsitz → Planke (Abzweig) · Kniebeuge → Dehnung (ein Punkt) ·
    # Planke und Dehnung ohne Weg
    eigen = ab.Ablauf(True, iw, (Kante(iw, ik), Kante(iw, ip), Kante(ik, id_)))
    state.plaene.ablauf_setzen(plan.id, eigen)
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    # Jeder Knoten hat seinen Punkt — und „Start“: am Abzweig, am einen Griff, unter der Übung
    assert sorted(d[1] for d in _daten(ansicht, "punkt")) == sorted([iw, ik, ip, id_, START])

    def mitte(c) -> tuple[float, float]:
        return (c.left + c.content.content.width / 2, c.top + c.content.content.height / 2)

    def mitte_von(c) -> tuple[float, float]:
        return (c.left + c.width / 2, c.top + c.height / 2)

    assert mitte(_mit_daten(ansicht, "punkt", iw)) == mitte_von(_mit_daten(ansicht, "abzweig", iw))
    griff = _mit_daten(ansicht, "kante", ik, id_)  # ohne Beschriftung: der Punkt allein
    assert mitte(_mit_daten(ansicht, "punkt", ik)) == mitte_von(griff)
    unter_planke = _mit_daten(ansicht, "punkt", ip)
    planke = _mit_daten(ansicht, "knoten", ip)
    assert unter_planke.top > planke.top + KNOTEN  # unter Bild und Namen
    assert abs(mitte(unter_planke)[0] - (planke.left + planke.width / 2)) < 1
    # Jeder Punkt ist zugleich antippbar — der von „Start“ spielt wie die Pille den Pfad ab
    for von in (iw, ik, ip, id_, START):
        assert _punkt(ansicht, von).content.on_click is not None
    assert _punkt(ansicht, START).content.height < _punkt(ansicht, ik).content.height
    # Die Ziele „Ende“ und „zurück“ stehen nur, während gezogen wird — ein Fallenlassen ins
    # Leere fängt die Ablage um die ganze Ansicht (Flet meldet keinen Abbruch)
    ziele = next(x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.data == ("ziele",))
    assert ziele.visible is False
    _klick(_punkt(ansicht, ip).on_drag_start, None)
    assert ziele.visible is True
    netz = next(x for x in _alle(ansicht) if isinstance(x, ft.DragTarget) and x.group == GRUPPE_WEG)
    assert netz.data is None and ansicht.controls[0].content is netz
    _klick(netz.on_accept, SimpleNamespace(src=_punkt(ansicht, ip)))
    assert ziele.visible is False and state.plaene.laden(plan.id).ablauf == eigen
    # Punkt auf eine andere Übung: ein freier Weg — gewählt, mit seiner Leiste
    _ziehen(ansicht, ip, id_)
    plan = state.plaene.laden(plan.id)
    assert plan.ablauf.von(ip) == [Kante(ip, id_)]
    assert state.ablauf_weg[plan.id] == (ip, id_) and state.ablauf_wahl[plan.id] is None
    assert _leiste(ansicht) is not None and ziele.visible is False
    assert [t for t in _texte(_leiste(ansicht)) if "·" in t] == ["3 · Planke", "4 · Dehnung"]
    assert _daten(ansicht, "weg_gewaehlt") == [("weg_gewaehlt", ip, id_)]
    # Noch einmal derselbe Weg: nichts Neues, eine kurze Meldung
    _ziehen(ansicht, ip, id_)
    assert state.plaene.laden(plan.id).ablauf.von(ip) == [Kante(ip, id_)]
    assert _meldungen(seite)[-1] == "Diesen Weg gibt es schon."
    # Auf die eigene Übung: noch einmal (Schleife)
    _ziehen(ansicht, id_, id_)
    plan = state.plaene.laden(plan.id)
    assert plan.ablauf.von(id_) == [Kante(id_, id_, text="noch einmal")]
    assert "noch einmal" in _texte(_leiste(ansicht))
    # Auf „Ende“ und auf „zurück“ — die zwei Ziele am unteren Rand
    _ziehen(ansicht, ip, ab.ENDE)
    _ziehen(ansicht, ik, ab.ZURUECK)
    plan = state.plaene.laden(plan.id)
    assert [k.nach for k in plan.ablauf.von(ip)] == [id_, ab.ENDE]
    assert [k.nach for k in plan.ablauf.von(ik)] == [id_, ab.ZURUECK]
    assert state.ablauf_weg[plan.id] == (ik, ab.ZURUECK)
    assert "◀ zurück" in _texte(_leiste(ansicht))
    # Von „Start“ auf eine Übung: Sie ist der Start (gewählt ist dann sie, kein Weg)
    _ziehen(ansicht, START, ik)
    plan = state.plaene.laden(plan.id)
    assert plan.ablauf.start == ik and len(plan.ablauf.kanten) == 7
    assert state.ablauf_wahl[plan.id] == ik and state.ablauf_weg[plan.id] is None
    assert _meldungen(seite)[-1] == "Neuer Start"
    # … noch einmal, oder auf „Ende“: nichts, mit Meldung
    _ziehen(ansicht, START, ik)
    assert _meldungen(seite)[-1] == "„2 · Kniebeuge“ ist schon der Start."
    _ziehen(ansicht, START, ab.ENDE)
    assert _meldungen(seite)[-1] == "„Start“ gehört auf eine Übung oder Frage."
    assert state.plaene.laden(plan.id).ablauf == plan.ablauf
    # Eine Frage hat denselben Punkt — aber keine Schleife auf sich selbst
    assert state.ablauf_wahl[plan.id] == ik  # die Kniebeuge ist gewählt: die Frage dahinter
    frage_kachel = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Draggable) and x.data == FRAGE_KACHEL
    )
    _klick(frage_kachel.content.on_click, None)
    (frage,) = state.plaene.laden(plan.id).ablauf.fragen
    _ziehen(ansicht, frage.id, frage.id)
    assert _meldungen(seite)[-1] == "Eine Frage führt nicht zu sich selbst."
    _ziehen(ansicht, frage.id, iw)
    assert state.plaene.laden(plan.id).ablauf.von(frage.id) == [Kante(frage.id, iw)]


def test_gedrueckt_halten_oeffnet_das_menue_an_der_uebung(umgebung) -> None:
    """Ben, 16.11.2026: „gedrückt halten von Kachel um ein Menü zu öffnen“ — das Menü steht
    als Karte im Bild an der Übung (kein Flutter-Menü), dahinter ein Schirm, der den
    schließenden Tipp fängt. Was vorher die Knopfzeile und „Routing“ boten, steht dort."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    eigen = ab.Ablauf(True, iw, (Kante(iw, ik), Kante(iw, ip), Kante(ik, id_)))
    state.plaene.ablauf_setzen(plan.id, eigen)
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    assert _daten(ansicht, "menue") == []
    # Gedrückt halten an der Kniebeuge: ihr Menü — und sie ist gewählt
    eintraege = _menue_oeffnen(ansicht, ik)
    assert eintraege == [
        "Übung einstellen …",
        "Beiname …",
        "Nur ihren Weg zeigen",
        "Als Start",
        "Aus dem Ablauf nehmen",
    ]
    assert state.ablauf_menue[plan.id] == ik and state.ablauf_wahl[plan.id] == ik
    # Die Karte liegt in der Fläche an der Übung, der Schirm darunter deckt die ganze Fläche
    schirm = _schirm(ansicht)
    flaeche = next(x for x in _alle(ansicht) if isinstance(x, ft.Stack) and schirm in x.controls)
    karte = _mit_daten(ansicht, "menue", ik)
    knoten = _mit_daten(ansicht, "knoten", ik)
    assert knoten.top < karte.top < knoten.top + KNOTEN  # nach unten, am Bild der Übung
    assert karte.left >= 0 and karte.left + karte.width <= flaeche.width
    assert karte.top + karte.height <= flaeche.height
    assert (schirm.content.width, schirm.content.height) == (flaeche.width, flaeche.height)
    reihe = flaeche.controls
    assert reihe.index(schirm) < reihe.index(knoten) < reihe.index(karte)  # die Übung bleibt klar
    punkte = [x for x in reihe if isinstance(x.data, tuple) and x.data[:1] == ("punkt",)]
    assert len(punkte) == 5 and all(reihe.index(x) < reihe.index(schirm) for x in punkte)
    rot = _mit_daten(ansicht, "menue_eintrag", "Aus dem Ablauf nehmen")
    assert [x.color for x in _alle(rot) if isinstance(x, ft.Text)] == [ft.Colors.ERROR]
    # Ein Tipp daneben (der Schirm) schließt es — sonst geschieht nichts
    _klick(schirm.on_tap, None)
    assert _daten(ansicht, "menue") == [] and state.ablauf_menue[plan.id] is None
    assert state.plaene.laden(plan.id).ablauf == eigen
    # Ein Tipp auf die Übung selbst schließt es ebenso (ohne die Wahl zu ändern)
    _menue_oeffnen(ansicht, ik)
    _gesten(ansicht, ik).on_tap(None)
    assert _daten(ansicht, "menue") == [] and state.ablauf_wahl[plan.id] == ik
    # Die Übung unten im Bild: Das Menü geht nach oben auf — der Finger lag tief auf der Seite
    ort = SimpleNamespace(
        global_position=SimpleNamespace(y=(MENUE_NACH_OBEN_AB + 0.1) * 800),
        page=SimpleNamespace(height=800),
    )
    _klick(_gesten(ansicht, id_).on_long_press_start, ort)
    _klick(_gesten(ansicht, id_).on_long_press, None)
    karte, knoten = _mit_daten(ansicht, "menue", id_), _mit_daten(ansicht, "knoten", id_)
    assert karte.top + karte.height < knoten.top + KNOTEN / 2
    _klick(_schirm(ansicht).on_tap, None)
    # „Übung einstellen …“ führt in „Im Plan einstellen“ — das Menü ist danach zu
    _menue(ansicht, ik, "Übung einstellen …")
    assert seite.routen[-1] == f"{basis}/ziel/{ik}" and _daten(ansicht, "menue") == []
    # „Beiname …“: das Blatt
    _menue(ansicht, ik, "Beiname …")
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet) and "Beiname" in _texte(blatt)
    feld = next(x for x in _alle(blatt) if isinstance(x, ft.TextField))
    feld.value = "leicht"
    _klick(_knopf(blatt, "Übernehmen").on_click, None)
    _klick(blatt.on_dismiss, None)
    assert state.plaene.item_laden(ik).beiname == "leicht"
    assert "leicht" in _texte(_mit_daten(ansicht, "knoten", ik))
    # „Nur ihren Weg zeigen“ — das frühere Gedrückthalten: der Rest wird blass; der Eintrag
    # heißt dann „Alles zeigen“
    _menue(ansicht, ik, "Nur ihren Weg zeigen")
    assert state.ablauf_vernebelt[plan.id] == {ip}
    assert _mit_daten(ansicht, "knoten", ip).opacity == abbild.NEBEL
    assert "Alles zeigen" in _menue_oeffnen(ansicht, ik)
    _klick(_mit_daten(ansicht, "menue_eintrag", "Alles zeigen").on_click, None)
    assert state.ablauf_vernebelt[plan.id] == set()
    # „Als Start“ — an der Startübung fehlt der Eintrag
    assert "Als Start" not in _menue_oeffnen(ansicht, iw)
    _klick(_schirm(ansicht).on_tap, None)
    _menue(ansicht, ik, "Als Start")
    assert state.plaene.laden(plan.id).ablauf.start == ik
    # „Aus dem Ablauf nehmen“ fragt wie bisher (Lücke oder Nachfolgereihe)
    _menue(ansicht, ik, "Aus dem Ablauf nehmen")
    dialog = seite.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert dialog.title.value == "„2 · Kniebeuge · leicht“ aus dem Ablauf nehmen"
    assert _daten(ansicht, "menue") == []  # zu, bevor der Dialog aufgeht
    # Eine Frage: ändern und löschen
    state.ablauf_wahl[plan.id] = ip
    frage_kachel = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Draggable) and x.data == FRAGE_KACHEL
    )
    _klick(frage_kachel.content.on_click, None)
    (frage,) = state.plaene.laden(plan.id).ablauf.fragen
    assert _menue_oeffnen(ansicht, frage.id) == ["Frage ändern …", "Frage löschen"]
    _klick(_mit_daten(ansicht, "menue_eintrag", "Frage ändern …").on_click, None)
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet) and "Frage" in _texte(blatt)
    _menue(ansicht, frage.id, "Frage löschen")
    assert state.plaene.laden(plan.id).ablauf.fragen == ()


def test_weg_leiste_unter_dem_bild_stellt_den_weg_ein(umgebung) -> None:
    """Ben, 16.11.2026: „möglichst ohne die Blätter schon viel machen“ — ein Tipp auf den Punkt
    eines Wegs zeigt unter dem Bild seine Leiste: Marke, von → nach, die Auslöser als Chips,
    die Zahl mit − und +, Pflicht; jede Änderung speichert sofort. „Mehr …“ öffnet das Blatt
    mit nur diesem Weg, „Entfernen“ nimmt ihn heraus."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    eigen = ab.Ablauf(
        True, iw, (Kante(iw, ik, ab.WDH, 12), Kante(iw, ip, text="Rücken tut weh"), Kante(ik, id_))
    )
    state.plaene.ablauf_setzen(plan.id, eigen)
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    assert _leiste(ansicht) is None
    # Der Griff des zweiten Wegs: seine Leiste — „Weg 2“, von → nach, „frei“ gewählt
    _klick(_mit_daten(ansicht, "kante", iw, ip).on_click, None)
    assert not seite.dialoge  # kein Blatt
    leiste = _leiste(ansicht)
    texte = _texte(leiste)
    assert texte[:3] == ["Weg 2", "1 · Wandsitz", "3 · Planke"]
    assert "Wann geht es weiter?" in texte and "Pflicht" in texte
    chips = {x.data[1]: x for x in _alle(leiste) if isinstance(x, ft.Chip)}
    # „antwort“ gibt es nur an einem Weg aus einer Frage mit Antworten
    assert list(chips) == list(ab.AUSLOESER_TEXT)
    assert [a for a, c in chips.items() if c.selected] == [ab.FREI]
    assert all(c.show_checkmark for c in chips.values())
    assert not [
        x for x in _alle(leiste) if isinstance(x, ft.IconButton) and x.data != "weg_entfernen"
    ]
    assert state.ablauf_weg[plan.id] == (iw, ip) and state.ablauf_wahl[plan.id] is None
    assert _daten(ansicht, "weg_gewaehlt") == [("weg_gewaehlt", iw, ip)]
    # Auslöser „Skala“: ab 7, bis offen — gespeichert, ohne Blatt
    _klick(_in_leiste(ansicht, ("ausloeser", ab.SKALA)).on_select, None)
    weg = state.plaene.laden(plan.id).ablauf.von(iw)[1]
    assert (weg.ausloeser, weg.n, weg.bis, weg.text) == (ab.SKALA, 7, None, "Rücken tut weh")
    assert [_in_leiste(ansicht, ("zahl", f)).value for f in ("n", "bis")] == ["7", "offen"]
    # − und +: ab 6, bis 6 … 8
    _klick(_in_leiste(ansicht, ("schritt", "n", -1)).on_click, None)
    for _ in range(3):
        _klick(_in_leiste(ansicht, ("schritt", "bis", 1)).on_click, None)
    weg = state.plaene.laden(plan.id).ablauf.von(iw)[1]
    assert (weg.n, weg.bis) == (6, 8)
    assert "Skala 6–8 · Rücken tut weh" in _texte(_mit_daten(ansicht, "kante", iw, ip))
    # Pflicht
    schalter = _in_leiste(ansicht, "pflicht")
    schalter.value = True
    _klick(schalter.on_change, SimpleNamespace(control=schalter))
    assert state.plaene.laden(plan.id).ablauf.von(iw)[1].pflicht
    # Der Hauptweg (der Griff des ersten Wegs): Marke „Hauptweg“, 12 Wdh. mit − und +
    _klick(_mit_daten(ansicht, "kante", iw, ik).on_click, None)
    assert _texte(_leiste(ansicht))[:3] == ["Hauptweg", "1 · Wandsitz", "2 · Kniebeuge"]
    assert _in_leiste(ansicht, ("zahl", "n")).value == "12 Wdh."
    _klick(_in_leiste(ansicht, ("schritt", "n", 1)).on_click, None)
    assert state.plaene.laden(plan.id).ablauf.von(iw)[0].n == 13
    # … gespiegelt in die Bedingung der Planübung (P108), wie aus dem Blatt
    w = state.plaene.item_laden(iw)
    assert (w.bedingung.art, w.bedingung.n) == (bd.WDH, 13)
    # „in einer Zeit“: die Zahl wandert mit, die Sekunden haben ihr eigenes − und +
    _klick(_in_leiste(ansicht, ("ausloeser", ab.WDH_IN_ZEIT)).on_select, None)
    _klick(_in_leiste(ansicht, ("schritt", "sekunden", 1)).on_click, None)
    weg = state.plaene.laden(plan.id).ablauf.von(iw)[0]
    assert (weg.ausloeser, weg.n, weg.sekunden) == (ab.WDH_IN_ZEIT, 13, 65.0)
    assert _in_leiste(ansicht, ("zahl", "sekunden")).value == "1:05"
    # „Zeit ab“ an einer Übung ohne Timer: der Hinweis aus dem Blatt steht auch hier
    _klick(_in_leiste(ansicht, ("ausloeser", ab.ZEIT)).on_select, None)
    assert any(t.startswith("Die Übung hat keinen Timer") for t in _texte(_leiste(ansicht)))
    # Noch einmal auf den Griff: die Leiste geht zu
    _klick(_mit_daten(ansicht, "kante", iw, ik).on_click, None)
    assert _leiste(ansicht) is None and state.ablauf_weg[plan.id] is None
    # Der eine Punkt eines eindeutigen Wegs (Kniebeuge → Dehnung): auch er zeigt die Leiste —
    # er ist zugleich der Punkt, an dem man zieht
    _klick(_punkt(ansicht, ik).content.on_click, None)
    assert _texte(_leiste(ansicht))[:3] == ["Hauptweg", "2 · Kniebeuge", "4 · Dehnung"]
    # „Mehr …“: das Blatt mit nur diesem Weg (Ziel, Beschriftung, anbieten oder von selbst)
    _klick(_in_leiste(ansicht, "weg_mehr").on_click, None)
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet) and "KOMMT VON" not in _texte(blatt)
    ziele = [x for x in _alle(blatt) if isinstance(x, ft.Dropdown) and x.label == "Weiter zu"]
    assert [z.value for z in ziele] == [id_]
    beschriftung = next(
        x
        for x in _alle(blatt)
        if isinstance(x, ft.TextField) and str(x.label).startswith("Beschriftung")
    )
    beschriftung.value = "locker"
    beschriftung.on_blur(SimpleNamespace(control=beschriftung))
    _klick(blatt.on_dismiss, None)
    assert state.plaene.laden(plan.id).ablauf.von(ik) == [Kante(ik, id_, text="locker")]
    assert _leiste(ansicht) is not None  # der Weg bleibt gewählt
    # „Entfernen“ nimmt den Weg heraus — die Leiste geht zu, eine Meldung sagt es
    _klick(_in_leiste(ansicht, "weg_entfernen").on_click, None)
    assert state.plaene.laden(plan.id).ablauf.von(ik) == []
    assert _leiste(ansicht) is None
    assert _meldungen(seite)[-1] == "Weg 2 · Kniebeuge → 4 · Dehnung entfernt."
    # Ein Tipp auf eine Übung nimmt die Wahl des Wegs zurück
    _klick(_mit_daten(ansicht, "kante", iw, ip).on_click, None)
    _gesten(ansicht, ip).on_tap(None)
    assert _leiste(ansicht) is None and state.ablauf_wahl[plan.id] == ip


def test_schleife_ueber_eine_frage_ende_und_was_der_plan_sagt(umgebung) -> None:
    """Ben, 17.11.2026, am Bildschirmfoto: Planke → drei Übungen → Frage → zurück zur Planke.
    „Nach der Frage ist es nicht möglich, ein Ende zu setzen“ — der einzige Weg der Frage war
    ein Rückweg, ihr Punkt lag weit weg an dessen Griff. Jetzt steht er unter der Frage: von
    dort auf „Ende“ gezogen ist der zweite Weg da. Die Leiste eines Wegs aus einer Frage fragt
    „Bei welcher Antwort?“ (Bereich der Skala · jede andere), zeigt, was der Plan dazu sagt,
    und hat den Schalter „nur vorschlagen“ — je Weg: „Frage soll beides können, von selbst
    weiter + Weg vorschlagen“."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    frage = ab.Frage(text="Wie ist die Belastung?")
    wege = (*(Kante(ip, x) for x in (iw, ik, id_)), *(Kante(x, frage.id) for x in (iw, ik, id_)))
    eigen = ab.Ablauf(True, ip, (*wege, Kante(frage.id, ip)), (frage,))
    state.plaene.ablauf_setzen(plan.id, eigen)
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    # Der Punkt der Frage steht unter ihr — nicht am Griff ihres Rückwegs in der Gasse
    knoten, punkt = _knoten(ansicht, frage.id), _mit_daten(ansicht, "punkt", frage.id)
    mitte_x = knoten.left + knoten.width / 2
    assert abs(punkt.left + abbild.GRIFF / 2 - mitte_x) < 1
    assert 0 < punkt.top - knoten.top < 2 * abbild.FRAGE_H
    griff = _mit_daten(ansicht, "kante", frage.id, ip)
    assert abs(griff.left - punkt.left) > KNOTEN  # der Griff des Rückwegs liegt woanders
    # Vom Punkt auf „Ende“: der zweite Weg — er ist gewählt, seine Leiste steht da
    _ziehen(ansicht, frage.id, ab.ENDE)
    a = state.plaene.laden(plan.id).ablauf
    assert [k.nach for k in a.von(frage.id)] == [ip, ab.ENDE]
    namen = {i: i for i in (iw, ik, ip, id_)}
    assert ab.warnungen(eigen, list(namen), namen)  # vorher: kein Weg hinaus
    assert not ab.warnungen(a, list(namen), namen)  # jetzt gibt es einen
    leiste = _leiste(ansicht)
    assert leiste is not None
    texte = _texte(leiste)
    assert texte[:3] == ["Weg 2", "? · Wie ist die Belastung?", "Ende"]
    assert "Bei welcher Antwort?" in texte and "Pflicht" not in texte
    assert "nur vorschlagen" in texte and not _in_leiste(ansicht, "vorschlagen").value
    chips = {x.data[1]: x for x in _alle(leiste) if isinstance(x, ft.Chip)}
    assert list(chips) == [ab.SKALA, ab.FREI]
    assert [x.label.value for x in chips.values()] == ["Bereich", "jede andere"]
    # „Bereich“: der erste Weg mit Bereich bekommt das obere Stück der Skala …
    _klick(chips[ab.SKALA].on_select, None)
    weg = state.plaene.laden(plan.id).ablauf.von(frage.id)[1]
    assert (weg.ausloeser, weg.n, weg.bis) == (ab.SKALA, 7, None)
    assert [_in_leiste(ansicht, ("zahl", f)).value for f in ("n", "bis")] == ["7", "10"]
    # „nur vorschlagen“ an diesem Weg: 7–10 schlägt das Ende vor — das Etikett sagt es
    schalter = _in_leiste(ansicht, "vorschlagen")
    schalter.value = True
    _klick(schalter.on_change, SimpleNamespace(control=schalter))
    weg = state.plaene.laden(plan.id).ablauf.von(frage.id)[1]
    assert weg.vorschlagen and weg.kurztext() == "Skala ≥ 7 · Vorschlag"
    assert _in_leiste(ansicht, "vorschlagen").value
    # … der andere den Rest darunter
    _klick(_mit_daten(ansicht, "kante", frage.id, ip).on_click, None)
    assert _texte(_leiste(ansicht))[:3] == ["Hauptweg", "? · Wie ist die Belastung?", "3 · Planke"]
    _klick(_in_leiste(ansicht, ("ausloeser", ab.SKALA)).on_select, None)
    weg = state.plaene.laden(plan.id).ablauf.von(frage.id)[0]
    assert (weg.ausloeser, weg.n, weg.bis) == (ab.SKALA, 0, 6)
    # … und geht von selbst weiter (die Vorgabe): Die Frage kann beides
    assert not weg.vorschlagen and not _in_leiste(ansicht, "vorschlagen").value
    # Was der Plan bei dieser Antwort sagt: die Zeile öffnet das Blatt mit nur diesem Weg —
    # ohne „Pflicht“ und ohne „Anbieten | Von selbst“; dafür „Nach dieser Antwort“
    zeile = _in_leiste(ansicht, "weg_text")
    assert "Was sagt der Plan bei dieser Antwort? …" in _texte(zeile)
    _klick(zeile.on_click, None)
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet) and "Bei welcher Antwort?" in _texte(blatt)
    assert not [x for x in _alle(blatt) if isinstance(x, ft.Switch)]
    (wahl,) = [x for x in _alle(blatt) if isinstance(x, ft.SegmentedButton)]
    assert wahl.data == "weg_vorschlagen" and wahl.selected == ["selbst"]
    assert "Nach dieser Antwort" in _texte(blatt)
    assert [x.label.value for x in _alle(blatt) if isinstance(x, ft.Chip)] == [
        "Bereich der Skala",
        "Jede andere Antwort",
    ]
    feld = next(x for x in _alle(blatt) if isinstance(x, ft.TextField) and x.data == "weg_text")
    assert str(feld.label).startswith("Beschriftung — was sagt der Plan")
    feld.value = "Noch eine Runde"
    feld.on_blur(SimpleNamespace(control=feld))
    _klick(blatt.on_dismiss, None)
    assert state.plaene.laden(plan.id).ablauf.von(frage.id)[0].text == "Noch eine Runde"
    assert "„Noch eine Runde“" in _texte(_in_leiste(ansicht, "weg_text"))
    # „Entfernen“ steht ausgeschrieben da (Ben: „mach aus x --> entfernen“)
    entfernen = _in_leiste(ansicht, "weg_entfernen")
    assert isinstance(entfernen, ft.TextButton) and entfernen.content == "Entfernen"
    # Im Blatt der Frage steht die Frage und wie geantwortet wird (Skala · Ja/Nein · Auswahl)
    # — ob ein Weg von selbst geht oder nur vorschlägt, gehört an den Weg
    _menue(ansicht, frage.id, "Frage ändern …")
    blatt = seite.dialoge[-1]
    (art,) = [x for x in _alle(blatt) if isinstance(x, ft.SegmentedButton)]
    assert art.data == "frage_art" and art.selected == [ab.F_SKALA]
    assert [s.label.value for s in art.segments] == ["Skala", "Ja/Nein", "Auswahl"]
    assert any("Eine Frage kann beides." in x for x in _texte(blatt))


def test_frage_ja_nein_auswahl_und_mehrere_im_editor(umgebung) -> None:
    """Ben, 17.11.2026: „Eine Frage lässt bisher nur Skala von x bis y zu. Mehrfachauswahl,
    Ja/Nein usw. geht bisher nicht, wird aber gebraucht.“ Im Blatt der Frage wählt man die Art;
    ihre Wege ziehen mit — der erste gilt bei „Ja“, der zweite bei „Nein“. Ein neuer Weg nimmt
    die nächste freie Antwort; an der Leiste stehen die Antworten als Chips. Fehlt einer
    Antwort der Weg, warnt der Ablauf."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik = (it.id for it in plan.items[:2])
    frage = ab.Frage(text="Noch eine Runde?")
    eigen = ab.Ablauf(
        True,
        iw,
        (Kante(iw, frage.id), Kante(iw, ik), Kante(frage.id, iw, ab.SKALA, 0, 6, text="weiter")),
        (frage,),
    )
    state.plaene.ablauf_setzen(plan.id, eigen)
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)

    def jetzt() -> ab.Ablauf:
        return state.plaene.laden(plan.id).ablauf

    def _feld(c, daten: str):
        return next(x for x in _alle(c) if getattr(x, "data", None) == daten)

    def blatt_der_frage() -> ft.BottomSheet:
        _menue(ansicht, frage.id, "Frage ändern …")
        return seite.dialoge[-1]

    def art_waehlen(blatt, art: str) -> None:
        knopf = _feld(blatt, "frage_art")
        knopf.selected = [art]
        _klick(knopf.on_change, SimpleNamespace(control=knopf))

    def uebernehmen(blatt) -> None:
        _klick(_feld(blatt, "frage_uebernehmen").on_click, None)
        _klick(blatt.on_dismiss, None)

    # Ja/Nein: der vorhandene Weg (Skala 0–6) gilt jetzt bei „Ja“, seine Beschriftung bleibt
    blatt = blatt_der_frage()
    art_waehlen(blatt, ab.F_JA_NEIN)
    assert "Antworten: Ja · Nein" in _texte(blatt)
    uebernehmen(blatt)
    f = jetzt().frage(frage.id)
    assert f.art == ab.F_JA_NEIN and f.wahl == ("Ja", "Nein")
    (weg,) = jetzt().von(frage.id)
    assert (weg.ausloeser, weg.antworten, weg.text) == (ab.ANTWORT, ("Ja",), "weiter")
    assert "Ja · Nein" in _texte(_knoten(ansicht, frage.id))
    # … und „Nein“ führt noch nirgends hin: die Warnung über dem Bild nennt es
    assert any("Bei „Nein“ führt kein Weg weiter" in x for x in _texte(ansicht))
    # Vom Punkt der Frage auf „Ende“: der neue Weg gilt bei „Nein“ — die Warnung ist weg
    _ziehen(ansicht, frage.id, ab.ENDE)
    ende = jetzt().von(frage.id)[1]
    assert (ende.ausloeser, ende.antworten) == (ab.ANTWORT, ("Nein",))
    assert not any("führt kein Weg weiter" in x for x in _texte(ansicht))
    leiste = _leiste(ansicht)
    assert "Bei welcher Antwort?" in _texte(leiste)
    chips = {x.data: x for x in _alle(leiste) if isinstance(x, ft.Chip)}
    assert list(chips) == [("antwort", "Ja"), ("antwort", "Nein"), ("ausloeser", ab.FREI)]
    assert [x.selected for x in chips.values()] == [False, True, False]
    assert "Ende · „Nein“" in _texte(_mit_daten(ansicht, "kante", frage.id, ab.ENDE))
    # „jede andere“ macht den Weg frei; „Nein“ wieder an: zurück
    _klick(chips[("ausloeser", ab.FREI)].on_select, None)
    assert jetzt().von(frage.id)[1].ausloeser == ab.FREI
    chips = {x.data: x for x in _alle(_leiste(ansicht)) if isinstance(x, ft.Chip)}
    _klick(chips[("antwort", "Nein")].on_select, None)
    assert jetzt().von(frage.id)[1].antworten == ("Nein",)

    # Auswahl mit eigenen Antworten, mehrere zum Ankreuzen
    blatt = blatt_der_frage()
    art_waehlen(blatt, ab.F_AUSWAHL)
    felder = [x for x in _alle(blatt) if isinstance(x, ft.TextField) and x.data == "frage_antwort"]
    assert len(felder) == 2  # zwei leere Antworten zum Ausfüllen
    # ohne Antwort wird nichts übernommen — nichts von selbst eingesetzt
    _klick(_feld(blatt, "frage_uebernehmen").on_click, None)
    assert (
        felder[0].error == "Mindestens eine Antwort" and jetzt().frage(frage.id).art == ab.F_JA_NEIN
    )
    _klick(_feld(blatt, "frage_antwort_dazu").on_click, None)
    felder = [x for x in _alle(blatt) if isinstance(x, ft.TextField) and x.data == "frage_antwort"]
    for feld, text in zip(felder, ("Kraft", "Balance", "Ausdauer"), strict=True):
        feld.value = text
    schalter = _feld(blatt, "frage_mehrfach")
    schalter.value = True
    _klick(schalter.on_change, SimpleNamespace(control=schalter))
    uebernehmen(blatt)
    f = jetzt().frage(frage.id)
    assert (f.art, f.antworten, f.mehrere) == (ab.F_AUSWAHL, ("Kraft", "Balance", "Ausdauer"), True)
    # die Art ist neu: die zwei Wege bekommen der Reihe nach die ersten Antworten
    assert [k.antworten for k in jetzt().von(frage.id)] == [("Kraft",), ("Balance",)]
    assert "mehrere: Kraft · Balance · Ausdauer" in _texte(_knoten(ansicht, frage.id))
    # Ein Weg darf bei mehreren Antworten gelten: „Ausdauer“ dazu an den Weg zum Ende
    _klick(_mit_daten(ansicht, "kante", frage.id, ab.ENDE).on_click, None)
    leiste = _leiste(ansicht)
    assert "Wenn eine davon angekreuzt ist:" in _texte(leiste)
    chips = {x.data: x for x in _alle(leiste) if isinstance(x, ft.Chip)}
    _klick(chips[("antwort", "Ausdauer")].on_select, None)
    assert jetzt().von(frage.id)[1].antworten == ("Balance", "Ausdauer")

    # Eine Antwort umbenennen und eine streichen: die Wege ziehen mit
    blatt = blatt_der_frage()
    felder = [x for x in _alle(blatt) if isinstance(x, ft.TextField) and x.data == "frage_antwort"]
    assert [x.value for x in felder] == ["Kraft", "Balance", "Ausdauer"]
    felder[1].value = "Gleichgewicht"
    weg = [x for x in _alle(blatt) if getattr(x, "data", None) == "frage_antwort_weg"]
    _klick(weg[2].on_click, None)  # „Ausdauer“ streichen
    uebernehmen(blatt)
    assert jetzt().frage(frage.id).antworten == ("Kraft", "Gleichgewicht")
    assert [k.antworten for k in jetzt().von(frage.id)] == [("Kraft",), ("Gleichgewicht",)]


def test_gleichwertige_wege_sind_im_bild_kein_bedarf(umgebung) -> None:
    """Ben, 17.11.2026: „Mehrere gleichwertige Wege sollen auch als solche dargestellt werden,
    nicht rot unterbrochen liniert.“ Drei freie Wege aus dem Start: Keine der drei Übungen
    trägt „bei Bedarf“, der Kopf im Reiter „Plan“ zählt keine; erst ein Weg mit Auslöser neben
    dem regulären macht sein Ziel zum Bedarf."""
    state, plan = umgebung
    iw, ik, ip, id_ = (it.id for it in plan.items)
    katalog = {u.id: u for u in state.uebungen.alle()}
    frei = ab.Ablauf(True, iw, (Kante(iw, ik), Kante(iw, ip), Kante(iw, id_)))
    assert "bei Bedarf" not in _texte(abbild.ablaufbild(state, frei, plan.items, katalog).control)
    skala = ab.Ablauf(True, iw, (Kante(iw, ik), Kante(iw, ip), Kante(iw, id_, ab.SKALA, 7)))
    texte = _texte(abbild.ablaufbild(state, skala, plan.items, katalog).control)
    assert texte.count("bei Bedarf") == 1


def test_ohne_rueckrufe_ist_das_bild_wie_bisher(umgebung) -> None:
    """Das Bild zeichnen auch das Workout, der Workout-Eintrag und die Karte „So wächst der
    Plan“ im Kurs-Editor: Ohne die neuen Rückrufe lässt sich nichts ziehen und nichts ablegen,
    es gibt keine Punkte unter den Übungen und kein Menü."""
    state, plan = umgebung
    iw, ik, ip, id_ = (it.id for it in plan.items)
    eigen = ab.Ablauf(True, iw, (Kante(iw, ik), Kante(iw, ip), Kante(ik, id_)))
    katalog = {u.id: u for u in state.uebungen.alle()}

    def arten(z: abbild.Zeichnung) -> set[str]:
        return {c.data[0] for c in z.controls if isinstance(c.data, tuple)}

    def teile(z: abbild.Zeichnung, art: type) -> list:
        return [x for c in z.controls for x in _alle(c) if isinstance(x, art)]

    # ganz ohne Rückruf: nur Anzeige
    z = abbild.zeichnung(state, eigen, plan.items, katalog)
    assert arten(z) == {"start", "knoten", "abzweig", "kante"}
    for art in (ft.Draggable, ft.DragTarget, ft.GestureDetector):
        assert teile(z, art) == []
    assert isinstance(z.knoten[ik].content, ft.Column)  # der Knoten selbst, ohne Hülle
    # wie im Workout (Tippen, Gedrückthalten, Start) und im Kursplan-Bild (Knoten, Kante)
    z = abbild.zeichnung(
        state,
        eigen,
        plan.items,
        katalog,
        on_knoten=lambda k: None,
        on_knoten_lang=lambda k: None,
        on_kante=lambda k: None,
        on_start=lambda: None,
    )
    assert arten(z) == {"start", "knoten", "abzweig", "kante"}
    assert teile(z, ft.Draggable) == [] and teile(z, ft.DragTarget) == []
    geste = z.knoten[ik].content
    assert isinstance(geste, ft.GestureDetector) and geste.on_long_press_start is None
    # Jeder Rückruf schaltet nur das Seine an: Verbinden bringt die Punkte und die Ablage für
    # Punkte, eine Kachel-Ablage gibt es erst mit ``on_kachel_auf``
    gezogen: list[tuple[str, str]] = []
    z = abbild.zeichnung(
        state, eigen, plan.items, katalog, on_verbinden=lambda v, n: gezogen.append((v, n))
    )
    assert arten(z) == {"start", "knoten", "abzweig", "kante", "punkt"}
    assert {x.group for x in teile(z, ft.DragTarget)} == {GRUPPE_WEG}
    punkte = teile(z, ft.Draggable)
    assert sorted(x.data for x in punkte) == sorted([iw, ik, ip, id_, START])
    assert all(x.group == GRUPPE_WEG and x.on_drag_start is None for x in punkte)
    ablage = next(x for x in _alle(z.knoten[ip]) if isinstance(x, ft.DragTarget))
    ablage.on_accept(SimpleNamespace(src=SimpleNamespace(data=ik)))
    ablage.on_accept(SimpleNamespace(src=SimpleNamespace(data=START)))
    assert gezogen == [(ik, ip), (START, ip)]
    z = abbild.zeichnung(
        state, eigen, plan.items, katalog, on_kachel_auf=lambda k, wert: gezogen.append((k, wert))
    )
    assert teile(z, ft.Draggable) == [] and "punkt" not in arten(z)
    assert {x.group for x in teile(z, ft.DragTarget)} == {GRUPPE_KACHEL}
    # Die Ziele „Ende“/„zurück“ sind ein eigenes Teil: Wer sie will, legt sie über sein Bild
    z = abbild.ziele(lambda v, n: gezogen.append((v, n)))
    assert z.control.visible is False
    z.zeigen(True)
    assert z.control.visible is True
    ende, zurueck = (x for x in _alle(z.control) if isinstance(x, ft.DragTarget))
    assert (ende.data, zurueck.data) == (("ziel", ab.ENDE), ("ziel", ab.ZURUECK))
    zurueck.on_accept(SimpleNamespace(src=SimpleNamespace(data=ik)))
    assert gezogen[-1] == (ik, ab.ZURUECK) and z.control.visible is False


def test_wege_blatt_spiegelt_in_die_bedingung_und_im_plan_einstellen(umgebung) -> None:
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ip, id_))))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    # Der eine Punkt des Wandsitzes zeigt die Leiste seines Wegs; „Mehr …“ öffnet das Blatt
    # mit diesem Weg, „Herkunft und neue Wege“ holt alles dazu
    _klick(_punkt(ansicht, iw).content.on_click, None)
    _klick(_in_leiste(ansicht, "weg_mehr").on_click, None)
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    alle = next(x for x in _alle(blatt) if isinstance(x, ft.TextButton) and x.data == "alle_wege")
    assert alle.content == "Herkunft und neue Wege"
    _klick(alle.on_click, None)
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
    dehnung = next(it.exercise_id for it in plan.items if it.id == id_)
    _kacheln(ansicht)[dehnung].content.on_click(None)
    nachher = state.ablauf_lagen[plan.id]
    assert nachher[iw] == vorher[iw] and nachher[ik] == vorher[ik] and id_ in nachher
    # „Neu anordnen“: der Wandsitz mittig über seinen zwei Kindern
    _knopf(ansicht, "Neu anordnen").on_click(None)
    neu = state.ablauf_lagen[plan.id]
    assert neu[iw].x == (neu[ik].x + neu[id_].x) / 2


def test_aus_dem_ablauf_nehmen_laesst_die_uebung_im_plan(umgebung) -> None:
    """Ben, 9.11.2026: „wenn Übungen in einer Kette gelöscht werden, werden diese oben in der
    Auswahl komplett entfernt. Das soll nicht passieren“ — „Aus dem Ablauf nehmen“ (seit
    16.11.2026 im Menü an der Übung) nimmt nur aus dem Ablauf; aus dem Plan nimmt erst
    Gedrückthalten in der Auswahl, mit Rückfrage."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    state.plaene.ablauf_setzen(
        plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ik, ip), Kante(ip, id_)))
    )
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    _menue(ansicht, ik, "Aus dem Ablauf nehmen")
    dialog = seite.dialoge[-1]
    assert dialog.title.value == "„2 · Kniebeuge“ aus dem Ablauf nehmen"
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    assert set(zeilen) == {
        "Lücke schließen",
        "Mit der Nachfolgereihe herausnehmen",
        "Nur diese herausnehmen",
    }
    _klick(zeilen["Lücke schließen"].on_click, None)
    _klick(dialog.on_dismiss, None)
    plan = state.plaene.laden(plan.id)
    assert [it.id for it in plan.items] == [iw, ik, ip, id_]  # bleibt im Plan und in der Auswahl
    assert [(k.von, k.nach) for k in plan.ablauf.kanten] == [(iw, ip), (ip, id_)]
    kniebeuge = next(it.exercise_id for it in plan.items if it.id == ik)
    assert kniebeuge in _kacheln(ansicht)
    # Auch der Start — die Übung bleibt im Plan, aber **nichts rückt nach** (Ben, 16.11.2026:
    # „Start wird selbst verbunden … sonst ändert sich was und man merkt es nicht“)
    _menue(ansicht, iw, "Aus dem Ablauf nehmen")
    dialog = seite.dialoge[-1]
    assert "Sie ist der Start — danach setzt du einen neuen." in _texte(dialog)
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    _klick(zeilen["Nur diese herausnehmen"].on_click, None)
    _klick(dialog.on_dismiss, None)
    plan = state.plaene.laden(plan.id)
    assert (plan.ablauf.start, plan.ablauf.ohne_start) == ("", True)
    assert [(k.von, k.nach) for k in plan.ablauf.kanten] == [(ip, id_)]
    assert iw in [it.id for it in plan.items]
    assert any("Der Ablauf hat jetzt keinen Start." in t for t in _texte(seite.dialoge[-1]))
    # Die rote Karte steht über dem Bild, bis ein Start gesetzt ist — das Workout beginnt nicht
    warnung = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.data == "ablauf_warnung"
    )
    assert _texte(warnung) == [ab.START_FEHLT]
    with pytest.raises(AssertionError, match="kein Knopf"):
        _knopf(workout_view(_Seite(), state, plan, route=f"/plan/{plan.id}"), "Workout starten")
    # Mit dem, was schon da ist: Übung im Bild antippen, „Als Start“ — der Knopf steht nur,
    # solange der Start fehlt (sonst im Menü der Übung)
    with pytest.raises(AssertionError, match="kein Knopf"):
        _knopf(ansicht, "Als Start")  # nichts gewählt: der Hinweis nennt die Wege
    assert any(
        t.startswith("Der Ablauf hat keinen Start — zieh den Punkt von „Start“")
        for t in _texte(ansicht)
    )
    _gesten(ansicht, ip).on_tap(None)
    assert _knopf(ansicht, "Als Start").data == "als_start"
    _klick(_knopf(ansicht, "Als Start").on_click, None)
    plan = state.plaene.laden(plan.id)
    assert (plan.ablauf.start, plan.ablauf.ohne_start) == (ip, False)
    with pytest.raises(AssertionError, match="kein Knopf"):
        _knopf(ansicht, "Als Start")
    assert not [
        x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.data == "ablauf_warnung"
    ]
    # Gedrückt halten in der Auswahl: aus dem Plan — erst nach der Rückfrage
    _klick(_kacheln(ansicht)[kniebeuge].content.on_long_press, None)
    dialog = seite.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert dialog.title.value == "„2 · Kniebeuge“ aus dem Plan entfernen?"
    assert ik in [it.id for it in state.plaene.laden(plan.id).items]
    _klick(_knopf(dialog, "Entfernen").on_click, None)
    assert ik not in [it.id for it in state.plaene.laden(plan.id).items]


def test_mehrfach_verwendete_uebung_herausnehmen(umgebung) -> None:
    """Ben, 17.11.2026 (P224): „Wenn Übungen mehrfach in den Ablauf genommen werden, werden
    diese mit nx oben in der Leiste gelistet. Löscht man eine Übung einmal raus, ist diese noch
    im Plan … Einerseits könnte eine Übung einfach gelöscht werden, wenn sie mehrfach vorhanden
    ist und dann rausgenommen wird, wenn diese aber Einstellungen hat, werden diese
    mitgelöscht.“ — Steht die Übung mehrfach im Plan, geht die herausgenommene Planübung mit
    aus dem Plan; hat sie Eigenes, wird gefragt (Vorgabe: bleibt frei, „1 frei“ an der Kachel).
    Die letzte Planübung einer Übung bleibt immer."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    uk = plan.items[1].exercise_id
    zweite = state.plaene.uebung_hinzufuegen(plan.id, uk)
    dritte = state.plaene.uebung_hinzufuegen(plan.id, uk)
    dritte.beiname = "langsam"  # sie hat Eigenes
    state.plaene.item_speichern(dritte)
    state.plaene.ablauf_setzen(
        plan.id,
        ab.Ablauf(True, iw, (Kante(iw, ik), Kante(iw, zweite.id), Kante(iw, dritte.id))),
    )
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)

    def im_plan() -> list[str]:
        return [it.id for it in state.plaene.laden(plan.id).items]

    assert _texte(_kacheln(ansicht)[uk]) == ["3×", "Kniebeuge"]
    # Ohne Eigenes: keine Rückfrage — aus Ablauf und Plan, die Kachel zählt eine weniger
    vorher = len(seite.dialoge)
    _menue(ansicht, zweite.id, "Aus dem Ablauf nehmen")
    assert not [d for d in seite.dialoge[vorher:] if isinstance(d, ft.AlertDialog)]
    assert im_plan() == [iw, ik, ip, id_, dritte.id]
    assert any("aus Ablauf und Plan genommen" in t for t in _meldungen(seite))
    assert _texte(_kacheln(ansicht)[uk]) == ["2×", "Kniebeuge"]
    # Mit Eigenem (Beiname): eine Rückfrage — die Vorgabe lässt sie frei im Plan
    _menue(ansicht, dritte.id, "Aus dem Ablauf nehmen")
    dialog = seite.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert any("Diese hat Eigenes: Beiname." in t for t in _texte(dialog))
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    assert list(zeilen) == ["Nur aus dem Ablauf", "Auch aus dem Plan löschen"]
    _klick(zeilen["Nur aus dem Ablauf"].on_click, None)
    _klick(dialog.on_dismiss, None)
    assert im_plan() == [iw, ik, ip, id_, dritte.id]
    assert [k.nach for k in state.plaene.laden(plan.id).ablauf.von(iw)] == [ik]
    assert _texte(_kacheln(ansicht)[uk]) == ["2×", "Kniebeuge", "1 frei"]
    # Die Kachel setzt die freie wieder ein — mit ihrem Beinamen, keine neue Planübung
    state.ablauf_wahl[plan.id] = iw
    _klick(_kacheln(ansicht)[uk].content.on_click, None)
    assert im_plan() == [iw, ik, ip, id_, dritte.id]
    assert [k.nach for k in state.plaene.laden(plan.id).ablauf.von(iw)] == [ik, dritte.id]
    # Noch einmal heraus, diesmal mit aus dem Plan: ihre Einstellungen gehen mit
    _menue(ansicht, dritte.id, "Aus dem Ablauf nehmen")
    dialog = seite.dialoge[-1]
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    _klick(zeilen["Auch aus dem Plan löschen"].on_click, None)
    _klick(dialog.on_dismiss, None)
    assert im_plan() == [iw, ik, ip, id_]
    assert _texte(_kacheln(ansicht)[uk]) == ["Kniebeuge"]
    # Die letzte Kniebeuge bleibt im Plan, „frei“ — wie jede Übung, die nur einmal dasteht
    # (Ben, 9.11.2026: Sie soll nicht aus der Auswahl verschwinden)
    _menue(ansicht, ik, "Aus dem Ablauf nehmen")
    assert im_plan() == [iw, ik, ip, id_]
    assert _texte(_kacheln(ansicht)[uk]) == ["Kniebeuge", "frei"]


def test_reihe_herausnehmen_mit_mehrfach_verwendeter_uebung(umgebung) -> None:
    """P224 in der Rückfrage zur Reihe: Was mehrfach im Plan steht und nichts Eigenes hat,
    geht mit aus dem Plan; für Eigenes steht ein Schalter im Dialog (Vorgabe: behalten). Von
    zwei gleichen in der Reihe bleibt die letzte im Plan."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    uk = plan.items[1].exercise_id
    zweite = state.plaene.uebung_hinzufuegen(plan.id, uk)
    zweite.beiname = "2. Durchgang"
    state.plaene.item_speichern(zweite)
    kette = (Kante(iw, ip), Kante(ip, ik), Kante(ik, zweite.id))
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, kette))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)

    def im_plan() -> list[str]:
        return [it.id for it in state.plaene.laden(plan.id).items]

    # Die Planke mit ihrer Reihe (beide Kniebeugen): der Schalter nennt die mit Eigenem
    _menue(ansicht, ip, "Aus dem Ablauf nehmen")
    dialog = seite.dialoge[-1]
    schalter = next(x for x in _alle(dialog) if getattr(x, "data", None) == "eigenes_behalten")
    assert schalter.value is True and "Kniebeuge" in schalter.label
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    _klick(zeilen["Mit der Nachfolgereihe herausnehmen"].on_click, None)
    _klick(dialog.on_dismiss, None)
    # Planke: nur einmal im Plan → bleibt. Erste Kniebeuge: mehrfach, nichts Eigenes → aus dem
    # Plan. Zweite: Eigenes, behalten → bleibt frei
    assert im_plan() == [iw, ip, id_, zweite.id]
    assert state.plaene.laden(plan.id).ablauf.kanten == ()
    # Noch einmal mit ausgeschaltetem Schalter: Von zwei gleichen bleibt die letzte im Plan
    dritte = state.plaene.uebung_hinzufuegen(plan.id, uk)
    kette = (Kante(iw, ip), Kante(ip, zweite.id), Kante(zweite.id, dritte.id))
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, kette))
    ansicht = ablauf_view(seite, state, state.plaene.laden(plan.id), basis)
    _menue(ansicht, ip, "Aus dem Ablauf nehmen")
    dialog = seite.dialoge[-1]
    schalter = next(x for x in _alle(dialog) if getattr(x, "data", None) == "eigenes_behalten")
    schalter.value = False
    _klick(schalter.on_change, SimpleNamespace(control=schalter))
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    _klick(zeilen["Mit der Nachfolgereihe herausnehmen"].on_click, None)
    _klick(dialog.on_dismiss, None)
    assert im_plan() == [iw, ip, id_, dritte.id]


def test_punkt_je_verbindung_und_blatt_auf_dem_weg(umgebung) -> None:
    """Ben, 9.11.2026: Verbindungen bekommen einen Punkt zwischen den Ebenen. Seit 10.11.2026
    verlassen alle Wege die Übung an einem Abzweig: Tipp auf den Griff eines Wegs = nur dieser
    Weg (seit 16.11.2026 in der Leiste unter dem Bild, „Mehr …“ öffnet sein Blatt), Tipp auf
    den Abzweig = das Blatt mit allen."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, _id = (it.id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(iw, ip))))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    punkte = {
        x.data: x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and isinstance(x.data, tuple) and x.data[:1] == ("kante",)
    }
    assert set(punkte) == {("kante", iw, ik), ("kante", iw, ip)}
    # Der Griff ist groß genug für einen Finger und liegt zwischen den Ebenen
    griff = punkte[("kante", iw, ip)]
    assert griff.height >= 36 and griff.on_click is not None
    knoten_w = _mit_daten(ansicht, "knoten", iw)
    knoten_p = _mit_daten(ansicht, "knoten", ip)
    mitte = griff.top + griff.height / 2
    assert knoten_w.top + KNOTEN <= mitte <= knoten_p.top
    # Der Griff eines Wegs zeigt nur diesen Weg (Ben, 10.11.2026) — in der Leiste unter dem
    # Bild; „Mehr …“ öffnet das Blatt mit ihm allein …
    _klick(griff.on_click, None)
    assert not seite.dialoge and _texte(_leiste(ansicht))[:3] == [
        "Weg 2",
        "1 · Wandsitz",
        "3 · Planke",
    ]
    _klick(_in_leiste(ansicht, "weg_mehr").on_click, None)
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)

    def ziele(b) -> list[str]:
        return [x.value for x in _alle(b) if isinstance(x, ft.Dropdown) and x.label == "Weiter zu"]

    assert ziele(blatt) == [ip] and "KOMMT VON" not in _texte(blatt)
    # … „Alle Wege“ holt die anderen dazu
    alle = next(x for x in _alle(blatt) if isinstance(x, ft.TextButton) and x.data == "alle_wege")
    _klick(alle.on_click, None)
    assert ziele(blatt) == [ik, ip] and "KOMMT VON" in _texte(blatt)
    # Der Abzweig unter der Übung — ein Austrittspunkt für alle Wege — öffnet alle auf einmal
    abzweig = _mit_daten(ansicht, "abzweig", iw)
    assert knoten_w.top + KNOTEN < abzweig.top + abzweig.height / 2 < mitte
    _klick(abzweig.on_click, None)
    blatt = seite.dialoge[-1]
    assert ziele(blatt) == [ik, ip] and "KOMMT VON" in _texte(blatt)
    assert _leiste(ansicht) is None and state.ablauf_wahl[plan.id] == iw
    # … ebenso die Fläche zum Ziehen, die über ihm liegt
    vorher = len(seite.dialoge)
    _klick(_punkt(ansicht, iw).content.on_click, None)
    assert len(seite.dialoge) == vorher + 1 and ziele(seite.dialoge[-1]) == [ik, ip]
    # Eine Übung ohne Weg: ihr Punkt (ein Ring) öffnet dasselbe Blatt — dort „+ Weg“
    _klick(_punkt(ansicht, ip).content.on_click, None)
    blatt = seite.dialoge[-1]
    assert ziele(blatt) == [] and "KOMMT VON" in _texte(blatt)
    _knopf(blatt, "Weg")
    # Beschriftete Geschwisterwege: die Beschriftung steht nach außen — nichts überdeckt sich
    state.plaene.ablauf_setzen(
        plan.id,
        ab.Ablauf(
            True, iw, (Kante(iw, ik, text="Rücken tut weh"), Kante(iw, ip, text="Arme tun weh"))
        ),
    )
    plan = state.plaene.laden(plan.id)
    ansicht = ablauf_view(_Seite(), state, plan, basis)
    griffe = sorted(
        (
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.Container)
            and isinstance(x.data, tuple)
            and x.data[:1] == ("kante",)
        ),
        key=lambda g: g.left,
    )
    assert len(griffe) == 2 and griffe[0].left + griffe[0].width <= griffe[1].left


def test_warnung_wenn_der_plan_haengen_bleiben_kann(umgebung) -> None:
    """Ben, 9.11.2026: „dafür braucht es in der Planerstellung eine Warnung, falls es passieren
    könnte, dass der Plan hängen bleibt“ — im Ablauf über dem Bild und im Reiter „Plan“."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, _ip, _id = (it.id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ik, iw))))
    plan = state.plaene.laden(plan.id)
    ansicht = ablauf_view(_Seite(), state, plan, basis)
    warnung = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.data == "ablauf_warnung"
    )
    assert any(
        t.startswith("Kein Weg hinaus ab: 1 · Wandsitz, 2 · Kniebeuge") for t in _texte(warnung)
    )
    editor = plan_view(_Seite(), state, plan, bearbeiten=True, basis=basis)
    assert any(isinstance(x, ft.Container) and x.data == "ablauf_warnung" for x in _alle(editor))
    # Ein Weg hinaus: keine Warnung mehr
    state.plaene.ablauf_setzen(plan.id, plan.ablauf.mit_kante(Kante(ik, ab.ENDE)))
    plan = state.plaene.laden(plan.id)
    ansicht = ablauf_view(_Seite(), state, plan, basis)
    assert not any(
        isinstance(x, ft.Container) and x.data == "ablauf_warnung" and x.visible is not False
        for x in _alle(ansicht)
    )


def test_wege_einer_verborgenen_planuebung_bleiben_beim_speichern(umgebung) -> None:
    """N47: Liegt eine Übung im Papierkorb, blendet der Plan ihre Planübung aus — eine Änderung
    im Ablauf darf ihre Wege nicht löschen; holt man die Übung zurück, sind sie wieder da."""
    state, plan = umgebung
    iw, ik, ip, id_ = (it.id for it in plan.items)
    eigen = ab.Ablauf(an=True, start=iw, kanten=(Kante(iw, ik), Kante(ik, ip), Kante(ip, id_)))
    ablauf_speichern(state, plan.id, eigen.mit_kante(Kante(iw, ip, text="Abkürzung")))
    planke = next(it.exercise_id for it in plan.items if it.id == ip)
    state.uebungen.in_papierkorb(planke)
    sichtbar = state.plaene.laden(plan.id)
    assert ip not in [it.id for it in sichtbar.items]
    ablauf_speichern(state, plan.id, sichtbar.ablauf.mit_kante(Kante(ik, id_, text="kurz")))
    state.uebungen.aus_papierkorb(planke)
    wieder = state.plaene.laden(plan.id)
    wege = {(k.von, k.nach) for k in wieder.ablauf.kanten}
    assert {(ik, ip), (ip, id_), (iw, ip), (ik, id_)} <= wege


def _kacheln(ansicht) -> dict[str, ft.Draggable]:
    """Die Kacheln der Leiste — je Übung eine (Schlüssel: ID der Übung); ohne die Kachel
    „Frage“ und ohne die Punkte im Bild, die sich auch ziehen lassen."""
    return {
        x.data: x
        for x in _alle(ansicht)
        if isinstance(x, ft.Draggable) and x.group == GRUPPE_KACHEL and x.data != FRAGE_KACHEL
    }


def _im_plan(ansicht) -> dict[str, ft.Draggable]:
    """Die Kacheln der Übungen, die im Plan stehen — nur sie lassen sich gedrückt halten („aus
    dem Plan“); dahinter steht der übrige Katalog."""
    return {i: k for i, k in _kacheln(ansicht).items() if k.content.on_long_press is not None}


def _suchen(ansicht, text: str) -> None:
    feld = next(
        x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.hint_text == "Übung suchen"
    )
    feld.value = text
    feld.on_change(SimpleNamespace(control=feld))


def _daten(ansicht, art: str) -> list[tuple]:
    return [
        x.data
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and isinstance(x.data, tuple) and x.data[:1] == (art,)
    ]


def test_leiste_ist_ein_vorrat_an_uebungen(umgebung) -> None:
    """Ben, 16.11.2026: „Wenn man eine Übung mehrfach haben möchte, muss man die Übung 2,3-mal
    reinladen. Kannst du das so machen, dass Übungen aus der Liste oben mehrfach verwendet
    werden können, dann steht da ein 2x, 3x bei Mehrfachverwendung. Unten die Übungen sind aber
    nummeriert.“ — eine Kachel je Übung; tippen setzt eine freie Planübung ein, sonst entsteht
    eine neue derselben Übung; im Bild ist jede ein eigener Knoten mit ihrer Nummer."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    uw, uk, up, ud = (it.exercise_id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik),)))
    zweite = state.plaene.uebung_hinzufuegen(plan.id, uk)  # die Kniebeuge steht zweimal im Plan
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    # Fünf Planübungen, vier Kacheln — in der Reihenfolge des ersten Vorkommens, vor dem
    # übrigen Katalog
    kacheln = _kacheln(ansicht)
    assert list(kacheln)[:4] == [uw, uk, up, ud]
    # „2×“ nur an der Kniebeuge, keine Listennummer mehr; „frei“, solange keine im Bild ist —
    # „1 frei“, wenn eine von mehreren nicht im Bild steht (P224)
    assert _texte(kacheln[uk]) == ["2×", "Kniebeuge", "1 frei"]
    assert _texte(kacheln[uw]) == ["Wandsitz"]
    assert _texte(kacheln[up]) == ["Planke", "frei"] and _texte(kacheln[ud]) == ["Dehnung", "frei"]
    assert _daten(ansicht, "mehrfach") == [("mehrfach", uk)]
    # Tippen mit gewähltem Knoten: zuerst die freie Kniebeuge (Nummer 5) — keine neue Planübung
    state.ablauf_wahl[plan.id] = iw
    _klick(kacheln[uk].content.on_click, None)
    plan = state.plaene.laden(plan.id)
    assert len(plan.items) == 5
    assert [k.nach for k in plan.ablauf.von(iw)] == [ik, zweite.id]
    # Die Wahl geht auf den neuen Knoten: Kachel für Kachel angetippt entsteht eine Kette
    assert state.ablauf_wahl[plan.id] == zweite.id
    # Noch einmal: keine ist mehr frei — eine dritte Kniebeuge entsteht am Ende der Liste,
    # hinter der zweiten. Nie ein Weg zu einer, die schon im Bild steht (Ben, 16.11.2026:
    # „Ich brauche das einheitlich, neue Übung erstellen“)
    _klick(_kacheln(ansicht)[uk].content.on_click, None)
    plan = state.plaene.laden(plan.id)
    dritte = plan.items[-1]
    assert len(plan.items) == 6 and dritte.exercise_id == uk
    assert dritte.target is None and dritte.felder is None  # sie folgt der Übung (P79)
    assert [k.nach for k in plan.ablauf.von(iw)] == [ik, zweite.id]
    assert [k.nach for k in plan.ablauf.von(zweite.id)] == [dritte.id]
    assert state.ablauf_wahl[plan.id] == dritte.id
    assert _texte(_kacheln(ansicht)[uk]) == ["3×", "Kniebeuge"]
    assert any("neu im Plan" in t for d in seite.dialoge for t in _texte(d))
    # Im Bild: drei Knoten derselben Übung, jeder mit seiner Nummer (Stelle in der Liste)
    for item_id, nummer in ((ik, "2"), (zweite.id, "5"), (dritte.id, "6")):
        texte = _texte(_mit_daten(ansicht, "knoten", item_id))
        assert nummer in texte and "Kniebeuge" in texte
    # Jede hat ihre eigenen Wege: einer von der zweiten zur Dehnung
    ablauf_speichern(state, plan.id, plan.ablauf.mit_kante(Kante(zweite.id, id_, text="locker")))
    # Gedrückt halten: eine Planübung aus dem Plan — die zuletzt hinzugekommene, mit Nummer
    _klick(_kacheln(ansicht)[uk].content.on_long_press, None)
    dialog = seite.dialoge[-1]
    assert dialog.title.value == "„6 · Kniebeuge“ aus dem Plan entfernen?"
    assert any("noch 2× im Plan" in t for t in _texte(dialog))
    _klick(_knopf(dialog, "Entfernen").on_click, None)
    _klick(dialog.on_dismiss, None)
    plan = state.plaene.laden(plan.id)
    assert [it.id for it in plan.items] == [iw, ik, ip, id_, zweite.id]
    assert _texte(_kacheln(ansicht)[uk]) == ["2×", "Kniebeuge"]
    # Fällt die erste Kniebeuge weg, zählt die zweite neu (5 → 4) und behält ihre Wege
    state.plaene.uebung_entfernen(ik)
    plan = state.plaene.laden(plan.id)
    assert ab.nummern([it.id for it in plan.items])[zweite.id] == 4
    assert [(k.nach, k.text) for k in plan.ablauf.von(zweite.id)] == [(id_, "locker")]
    assert [k.nach for k in plan.ablauf.von(iw)] == [zweite.id]
    # Eine freie zuerst: Gedrückthalten nimmt die Planke, die nicht im Bild steht — ohne dass
    # das Bild einen Knoten verliert
    ansicht = ablauf_view(seite, state, plan, basis)
    assert _texte(_kacheln(ansicht)[uk]) == ["Kniebeuge"]  # nur noch einmal: kein „1×“
    _klick(_kacheln(ansicht)[up].content.on_long_press, None)
    assert seite.dialoge[-1].title.value == "„2 · Planke“ aus dem Plan entfernen?"


def test_leiste_zeigt_den_ganzen_katalog_mit_suche_und_filter(umgebung) -> None:
    """Ben, 17.11.2026: „Ersetze das Suchfeld und das Plus rechts daneben lieber durch die
    Übungen aller Kataloge und den Filter (dort, wo das Plus steht), so dass dieser Bereich so
    wirkt wie die View, wenn man jetzt das Plus drückt.“ — zuerst die Übungen des Plans, hinter
    einem Strich der übrige Katalog; Suche und Filter wie in „Übung hinzufügen“; eine Kachel
    von außerhalb des Plans legt ihre Planübung an."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, _ip, _id = (it.id for it in plan.items)
    uw, uk, up, ud = (it.exercise_id for it in plan.items)
    zebra = Exercise(name="Zebrastand")
    state.uebungen.speichern(zebra)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik),)))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    alle = state.uebungen.alle()
    assert len(alle) > KACHELN_HOECHSTENS  # das Paket „Standard“ und die fünf eigenen
    # Ohne Suche: die vier des Plans, der Strich, der Katalog bis zum Deckel, „+ n weitere“ —
    # und fest daneben die Kachel „Frage“ (nicht in der scrollenden Reihe)
    kacheln = _kacheln(ansicht)
    assert list(kacheln)[:4] == [uw, uk, up, ud] and list(_im_plan(ansicht)) == [uw, uk, up, ud]
    assert len(kacheln) == KACHELN_HOECHSTENS
    assert _daten(ansicht, "palette_strich") == [("palette_strich",)]
    assert _daten(ansicht, "palette_weitere") == [
        ("palette_weitere", len(alle) - KACHELN_HOECHSTENS)
    ]
    reihe = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Row) and x.scroll == ft.ScrollMode.AUTO
    )
    frage = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Draggable) and x.data == FRAGE_KACHEL
    )
    assert frage not in list(_alle(reihe))
    # Suchfeld, Filter (wo das Plus stand) und „i“ in einer Zeile
    feld = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField))
    filterknopf = next(
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.icon == ft.Icons.FILTER_LIST
    )
    assert feld.hint_text == "Übung suchen" and feld.expand
    assert "Übungen des Plans suchen" not in [
        x.hint_text for x in _alle(ansicht) if isinstance(x, ft.TextField)
    ]
    # Suche über den Katalog: „Zebra“ findet die Übung, die nicht im Plan steht — keine
    # Kachel des Plans, kein Strich, kein Gedrückthalten
    _suchen(ansicht, "Zebra")
    kacheln = _kacheln(ansicht)
    assert list(kacheln) == [zebra.id] and _im_plan(ansicht) == {}
    assert _daten(ansicht, "palette_strich") == [] and _daten(ansicht, "palette_weitere") == []
    assert "kommt in den Plan" in kacheln[zebra.id].content.tooltip
    # Angetippt ohne gewählte Übung (der Ablauf hat einen Start): nur der Hinweis, nichts
    # kommt in den Plan
    _klick(kacheln[zebra.id].content.on_click, None)
    assert len(state.plaene.laden(plan.id).items) == 4
    assert any(t.startswith("Erst eine Übung im Bild antippen") for t in _meldungen(seite))
    # Mit gewählter Kniebeuge: Die Planübung entsteht, der Weg führt zu ihr, sie ist gewählt
    _gesten(ansicht, ik).on_tap(None)
    _klick(_kacheln(ansicht)[zebra.id].content.on_click, None)
    plan = state.plaene.laden(plan.id)
    neu = plan.items[-1]
    assert len(plan.items) == 5 and neu.exercise_id == zebra.id
    assert neu.target is None and neu.felder is None  # sie folgt der Übung (P79)
    assert [k.nach for k in plan.ablauf.von(ik)] == [neu.id]
    assert state.ablauf_wahl[plan.id] == neu.id
    assert any("neu im Plan" in t for t in _meldungen(seite))
    assert _mit_daten(ansicht, "knoten", neu.id) is not None
    # Jetzt gehört sie zum Plan: Gedrückthalten nimmt sie wieder heraus
    assert list(_im_plan(ansicht)) == [zebra.id]
    # Die Suche trifft Plan und Katalog: die Kniebeuge des Plans zuerst
    _suchen(ansicht, "Kniebeuge")
    assert next(iter(_kacheln(ansicht))) == uk and list(_im_plan(ansicht)) == [uk]
    _suchen(ansicht, "gibtesnicht")
    assert _kacheln(ansicht) == {} and "Keine Übung passt zu Suche und Filter." in _texte(ansicht)
    _suchen(ansicht, "")
    # Der Filter: „Eigene Übungen“ — nur die fünf ohne Paket, alle im Plan
    _klick(filterknopf.on_click, None)
    blatt = seite.dialoge[-1]
    chip = next(x for x in _alle(blatt) if isinstance(x, ft.Chip) and x.data == ("Paket", None))
    _klick(chip.on_select, None)
    assert state.hinzufuegen_filter.pakete == {None}
    assert list(_kacheln(ansicht)) == [uw, uk, up, ud, zebra.id]
    assert _daten(ansicht, "palette_strich") == [] and _daten(ansicht, "palette_weitere") == []
    # … und wirkt in „Übung hinzufügen“ genauso (derselbe Stand); geleert steht alles wieder da
    state.hinzufuegen_filter.leeren()
    ansicht = ablauf_view(_Seite(), state, state.plaene.laden(plan.id), basis)
    assert len(_kacheln(ansicht)) == KACHELN_HOECHSTENS
    # Eine Kachel aus dem Katalog auf eine Übung im Bild gezogen: neu im Plan, dahinter
    fremd = next(i for i in _kacheln(ansicht) if i not in _im_plan(ansicht))
    _ablage(ansicht, iw, GRUPPE_KACHEL).on_accept(SimpleNamespace(src=_kacheln(ansicht)[fremd]))
    plan = state.plaene.laden(plan.id)
    assert plan.items[-1].exercise_id == fremd and len(plan.items) == 6
    assert plan.ablauf.von(iw)[-1].nach == plan.items[-1].id
    assert fremd in _im_plan(ansicht)
    # Eine Übung, die es nicht gibt, ändert nichts
    _ablage(ansicht, iw, GRUPPE_KACHEL).on_accept(SimpleNamespace(src=SimpleNamespace(data="x")))
    assert len(state.plaene.laden(plan.id).items) == 6


def test_archivierte_uebung_des_plans_bleibt_in_der_leiste(umgebung) -> None:
    """Die Katalogsuche kennt keine archivierten Übungen — steht eine im Plan, bleibt ihre
    Kachel in der Leiste (sie ist ja im Bild), und die Suche nach ihrem Namen findet sie."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    uw, uk, up, ud = (it.exercise_id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, plan.items[0].id))
    state.uebungen.archivieren(up)
    ansicht = ablauf_view(_Seite(), state, state.plaene.laden(plan.id), basis)
    assert list(_im_plan(ansicht)) == [uw, uk, up, ud]
    _suchen(ansicht, "plank")
    assert list(_im_plan(ansicht)) == [up]
    _suchen(ansicht, "Wand")
    assert list(_im_plan(ansicht)) == [uw]


def test_kachel_auf_uebung_und_auf_start(umgebung) -> None:
    """Ziehen wie Tippen: Auf eine Übung im Bild gezogen kommt eine freie Planübung dahinter,
    sonst eine neue — das löst den Slot ab (Ben, 16.11.2026: „Slot weglassen“) —, und auf
    „Start“ genauso („Ich brauche das einheitlich, neue Übung erstellen“). Eine Kachel
    verbindet nie mit einem Knoten, der schon im Bild steht."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, _id = (it.id for it in plan.items)
    uw, uk, _up, _ud = (it.exercise_id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ik, ip))))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    assert _daten(ansicht, "slot") == []
    # Der Wandsitz auf die Planke: er steht schon im Bild → ein zweiter Wandsitz dahinter
    _ablage(ansicht, ip, GRUPPE_KACHEL).on_accept(SimpleNamespace(src=_kacheln(ansicht)[uw]))
    plan = state.plaene.laden(plan.id)
    neu = plan.items[-1]
    assert len(plan.items) == 5 and neu.exercise_id == uw
    assert [k.nach for k in plan.ablauf.von(ip)] == [neu.id]
    assert state.ablauf_wahl[plan.id] == neu.id
    assert any("neu im Plan" in t for t in _meldungen(seite))
    # Der Start aus dem Ablauf: jetzt nimmt „Start“ eine Kachel an. Die Kniebeuge steht schon
    # im Bild — auf „Start“ gezogen entsteht eine **neue** Kniebeuge und wird der Start; die
    # im Bild bleibt, wo sie ist
    _menue(ansicht, iw, "Aus dem Ablauf nehmen")
    dialog = seite.dialoge[-1]
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    _klick(zeilen["Nur diese herausnehmen"].on_click, None)
    _klick(dialog.on_dismiss, None)
    # Der Wandsitz steht noch einmal im Plan: Der herausgenommene geht mit aus dem Plan (P224)
    assert [it.id for it in state.plaene.laden(plan.id).items] == [ik, ip, _id, neu.id]
    start = next(
        x.content for x in _alle(ansicht) if isinstance(x, ft.Container) and x.data == ("start",)
    )
    assert isinstance(start, ft.DragTarget) and start.group == GRUPPE_KACHEL
    start.on_accept(SimpleNamespace(src=SimpleNamespace(data=uk)))
    plan = state.plaene.laden(plan.id)
    neuer_start = plan.items[-1]
    assert len(plan.items) == 5 and neuer_start.exercise_id == uk
    assert plan.ablauf.start == neuer_start.id != ik
    assert not plan.ablauf.von(neuer_start.id) and not plan.ablauf.zu(neuer_start.id)
    assert [k.nach for k in plan.ablauf.von(ik)] == [ip]  # die alte Kette steht noch


def test_eindeutiger_weg_hat_einen_punkt(umgebung) -> None:
    """Ben, 16.11.2026: „wenn ein Weg eindeutig ist, keine zwei Knoten zwischen den Übungen,
    sondern nur 1. Wenn mehr Wege gemeinsamer Knoten und Abzweigungsknoten so wie jetzt.“ Der
    eine Punkt kostet keine Funktion: Er zeigt die Leiste seines Wegs (von dort „Mehr …“ →
    Herkunft und neue Wege), und an ihm zieht man einen zweiten Weg."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    # Wandsitz: zwei Wege (Abzweig und Griffe) · Kniebeuge: einer · Planke: nur „Ende“
    eigen = ab.Ablauf(
        True, iw, (Kante(iw, ik), Kante(iw, ip), Kante(ik, id_, ab.WDH, 12), Kante(ip, ab.ENDE))
    )
    state.plaene.ablauf_setzen(plan.id, eigen)
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    assert _daten(ansicht, "abzweig") == [("abzweig", iw)]
    assert set(_daten(ansicht, "kante")) == {
        ("kante", iw, ik),
        ("kante", iw, ip),
        ("kante", ik, id_),
        ("kante", ip, ab.ENDE),
    }
    # Der eine Punkt liegt zwischen den zwei Übungen und trägt das Etikett des Wegs
    punkt = _mit_daten(ansicht, "kante", ik, id_)
    oben, unten = _mit_daten(ansicht, "knoten", ik), _mit_daten(ansicht, "knoten", id_)
    assert oben.top + KNOTEN < punkt.top + punkt.height / 2 < unten.top
    assert "12 Wdh." in _texte(punkt) and punkt.height >= 36
    # Er zeigt die Leiste seines Wegs — kein Blatt; das Etikett daneben ebenso
    _klick(_punkt(ansicht, ik).content.on_click, None)
    assert not seite.dialoge and state.ablauf_weg[plan.id] == (ik, id_)
    assert _texte(_leiste(ansicht))[:3] == ["Hauptweg", "2 · Kniebeuge", "4 · Dehnung"]
    _klick(punkt.on_click, None)  # noch einmal, am Etikett: die Wahl geht zurück
    assert _leiste(ansicht) is None
    _klick(_mit_daten(ansicht, "kante", ik, id_).on_click, None)
    # Den vorhandenen Weg ändern — in der Leiste, gespeichert ohne Blatt
    _klick(_in_leiste(ansicht, ("ausloeser", ab.SKALA)).on_select, None)
    assert [k.ausloeser for k in state.plaene.laden(plan.id).ablauf.von(ik)] == [ab.SKALA]

    def ziele(b) -> list[str]:
        return [x.value for x in _alle(b) if isinstance(x, ft.Dropdown) and x.label == "Weiter zu"]

    # „Mehr …“: das Blatt mit diesem Weg; „Herkunft und neue Wege“ holt Herkunft und „+ Weg“
    _klick(_in_leiste(ansicht, "weg_mehr").on_click, None)
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    assert ziele(blatt) == [id_] and "KOMMT VON" not in _texte(blatt)
    alle = next(x for x in _alle(blatt) if isinstance(x, ft.TextButton) and x.data == "alle_wege")
    _klick(alle.on_click, None)
    texte = _texte(blatt)
    assert "KOMMT VON" in texte and "WEITER ZU" in texte and "Hauptweg" in texte
    _klick(blatt.on_dismiss, None)
    # Einen zweiten Weg anlegen — von demselben Punkt aus gezogen, auf die Planke
    _ziehen(ansicht, ik, ip)
    plan = state.plaene.laden(plan.id)
    assert [(k.nach, k.ausloeser) for k in plan.ablauf.von(ik)] == [
        (id_, ab.SKALA),
        (ip, ab.FREI),
    ]
    # Jetzt teilen sich die Wege: die Kniebeuge hat ihren Abzweig, jeder Weg seinen Griff —
    # gezogen wird am Abzweig, der Griff des ersten Wegs zeigt wieder nur dessen Leiste
    assert set(_daten(ansicht, "abzweig")) == {("abzweig", iw), ("abzweig", ik)}
    abzweig = _mit_daten(ansicht, "abzweig", ik)
    ziehpunkt = _mit_daten(ansicht, "punkt", ik)
    assert (ziehpunkt.left, ziehpunkt.top) == (abzweig.left, abzweig.top)
    assert _texte(_leiste(ansicht))[:3] == ["Weg 2", "2 · Kniebeuge", "3 · Planke"]
    _klick(_mit_daten(ansicht, "kante", ik, id_).on_click, None)
    assert _texte(_leiste(ansicht))[:3] == ["Hauptweg", "2 · Kniebeuge", "4 · Dehnung"]
    # Wer nur ``on_kante`` kennt (Workout, Kursplan), bekommt vom einen Punkt seine Kante
    # gemeldet; wer nur ``on_abzweig`` kennt, den Knoten
    katalog = {u.id: u for u in state.uebungen.alle()}
    gemeldet: list = []
    z = abbild.zeichnung(state, eigen, plan.items, katalog, on_kante=gemeldet.append)
    assert not [c for c in z.controls if getattr(c, "data", None) == ("abzweig", ik)]
    punkt = next(c for c in z.controls if getattr(c, "data", None) == ("kante", ik, id_))
    punkt.on_click(None)
    assert gemeldet == [Kante(ik, id_, ab.WDH, 12)]
    z = abbild.zeichnung(state, eigen, plan.items, katalog, on_abzweig=gemeldet.append)
    next(c for c in z.controls if c.data == ("kante", ik, id_)).on_click(None)
    assert gemeldet[-1] == ik
    # Ohne Rückruf ist er nur Anzeige
    z = abbild.zeichnung(state, eigen, plan.items, katalog)
    assert next(c for c in z.controls if c.data == ("kante", ik, id_)).on_click is None


def test_geleertes_bild_bleibt_leer(umgebung, tmp_path) -> None:
    """Ben, 16.11.2026: „Das automatische Übungssetzen, wenn alles gelöscht wird, muss raus.“
    Wer alle Übungen aus dem Bild nimmt, sieht „Start“ und einen leeren Platz — auch nach dem
    Schließen und Wiederöffnen von Plan und App; neue Planübungen stehen nur in der Leiste."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    uw, uk, up, _ud = (it.exercise_id for it in plan.items)
    editor = plan_view(_Seite(), state, plan, bearbeiten=True, basis=basis)
    schalter = next(x for x in _alle(editor) if isinstance(x, ft.SegmentedButton))
    schalter.selected = ["verzweigt"]
    schalter.on_change(SimpleNamespace(control=schalter))
    plan = state.plaene.laden(plan.id)
    assert ab.im_bild(plan.ablauf, [iw, ik, ip, id_]) == [iw, ik, ip, id_]  # folgt der Liste
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    assert _daten(ansicht, "startplatz") == []
    # Der Start mit seiner ganzen Reihe aus dem Ablauf
    _menue(ansicht, iw, "Aus dem Ablauf nehmen")
    dialog = seite.dialoge[-1]
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    _klick(zeilen["Mit der Nachfolgereihe herausnehmen"].on_click, None)
    _klick(dialog.on_dismiss, None)
    leer = ab.Ablauf(an=True, ohne_start=True)
    assert state.plaene.ablauf_laden(plan.id) == leer

    def pruefen(a, p) -> None:
        """Das leere Bild: kein Knoten, „Start“ über dem leeren Platz, alle Kacheln „frei“."""
        assert p.ablauf == leer and [it.id for it in p.items][:4] == [iw, ik, ip, id_]
        assert _daten(a, "knoten") == [] and _daten(a, "kante") == []
        assert _daten(a, "punkt") == []  # auch „Start“ hat keinen Punkt: nichts, wohin er zöge
        assert _daten(a, "start") == [("start",)] and _daten(a, "startplatz") == [("startplatz",)]
        assert all(_texte(k)[-1] == "frei" for k in _im_plan(a).values())
        assert any(t.startswith("Der Ablauf ist leer") for t in _texte(a))

    pruefen(ansicht, state.plaene.laden(plan.id))
    # Plan schließen und wieder öffnen
    plan = state.plaene.laden(plan.id)
    pruefen(ablauf_view(_Seite(), state, plan, basis), plan)
    # Die App neu gestartet: ein zweiter Start liest dieselbe Datenbank von der Platte
    neustart = AppState.starten(tmp_path / "app.db")
    try:
        wieder = neustart.plaene.laden(plan.id)
        pruefen(ablauf_view(_Seite(), neustart, wieder, basis), wieder)
    finally:
        neustart.schliessen()
    # Eine neue Übung im Plan steht nur in der Leiste
    state.plaene.uebung_hinzufuegen(plan.id, uw)
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    pruefen(ansicht, plan)
    assert _texte(_kacheln(ansicht)[uw]) == ["2×", "Wandsitz", "frei"]
    # Reiter „Plan“: die Warnung unter dem Schalter, das Workout beginnt so nicht
    editor = plan_view(_Seite(), state, plan, bearbeiten=True, basis=basis)
    warnung = next(
        x for x in _alle(editor) if isinstance(x, ft.Container) and x.data == "ablauf_warnung"
    )
    assert any(t.startswith("Der Ablauf ist leer") for t in _texte(warnung))
    assert ablauf_zusammenfassung(plan) == "Workout mit eigenem Ablauf — noch ohne Start."
    # „Trainieren“: kein Absturz — das Start-Bild sagt, dass der Ablauf leer ist, ohne Startknopf
    start_bild = workout_view(_Seite(), state, plan, route=f"/plan/{plan.id}")
    assert any(t.startswith("Der Ablauf ist leer") for t in _texte(start_bild))
    with pytest.raises(AssertionError, match="kein Knopf"):
        _knopf(start_bild, "Workout starten")
    # Eine Kachel antippen: sie wird der Start — die freie Planübung, keine neue
    _klick(_kacheln(ansicht)[uk].content.on_click, None)
    plan = state.plaene.laden(plan.id)
    assert plan.ablauf == ab.Ablauf(True, ik) and len(plan.items) == 5
    assert _daten(ansicht, "knoten") == [("knoten", ik)] and _daten(ansicht, "startplatz") == []
    _knopf(workout_view(_Seite(), state, plan, route=f"/plan/{plan.id}"), "Workout starten")
    # … und wieder heraus (der neue Start ist gewählt): leer; in den leeren Platz gezogen ist
    # sie wieder der Start
    assert state.ablauf_wahl[plan.id] == ik
    _menue(ansicht, ik, "Aus dem Ablauf nehmen")
    assert state.plaene.ablauf_laden(plan.id) == leer
    platz = _mit_daten(ansicht, "startplatz").content
    assert isinstance(platz, ft.DragTarget)
    platz.on_accept(SimpleNamespace(src=SimpleNamespace(data=up)))
    assert state.plaene.laden(plan.id).ablauf == ab.Ablauf(True, ip)
    assert state.ablauf_wahl[plan.id] == ip  # der neue Start ist gewählt
    _menue(ansicht, ip, "Aus dem Ablauf nehmen")
    # „Wie die Liste“ unter dem leeren Bild holt die Kette der Liste zurück
    _klick(_knopf(ansicht, "Wie die Liste").on_click, None)
    plan = state.plaene.laden(plan.id)
    assert state.plaene.ablauf_laden(plan.id) == ab.Ablauf(an=True)
    assert len(plan.ablauf.kanten) == 4 and plan.ablauf.start == iw
    assert len(_daten(ansicht, "knoten")) == 5 and _daten(ansicht, "startplatz") == []


def test_liste_und_zurueck_holt_die_liste_in_den_geleerten_ablauf(umgebung) -> None:
    """Ein geleerter Ablauf hat keine Zeichnung, die „Liste“ aufheben müsste: Wer auf „Liste“
    und wieder auf „Workout“ stellt, hat wieder das Workout, das der Liste folgt."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(an=True, ohne_start=True))
    state.plaene.workout_setzen(plan.id, True, False)
    plan = state.plaene.laden(plan.id)
    assert plan.ablauf == ab.Ablauf(an=True, ohne_start=True)
    editor = plan_view(_Seite(), state, plan, bearbeiten=True, basis=basis)
    schalter = next(x for x in _alle(editor) if isinstance(x, ft.SegmentedButton))
    for wert in ("linear", "verzweigt"):
        schalter.selected = [wert]
        schalter.on_change(SimpleNamespace(control=schalter))
    plan = state.plaene.laden(plan.id)
    assert state.plaene.ablauf_laden(plan.id) == ab.Ablauf(an=True)
    assert len(plan.ablauf.kanten) == 3 and plan.ablauf.start == plan.items[0].id


def test_start_herausgenommen_der_platz_liegt_wo_der_start_war(umgebung) -> None:
    """Web-Foto 16.11.2026: Der leere Platz unter „Start“ lag links von allem und schob den
    Rest aus dem Blick. Ist die oberste Ebene frei, liegt er dort, wo der Start war — und eine
    Kachel, die hineinfällt, landet als neuer Knoten genau dort, ohne Weg zum Rest."""
    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    _uw, _uk, _up, ud = (it.exercise_id for it in plan.items)
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ik, ip))))
    plan = state.plaene.laden(plan.id)
    seite = _Seite()
    ansicht = ablauf_view(seite, state, plan, basis)
    vorher = dict(state.ablauf_lagen[plan.id])
    _menue(ansicht, iw, "Aus dem Ablauf nehmen")
    dialog = seite.dialoge[-1]
    zeilen = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    _klick(zeilen["Nur diese herausnehmen"].on_click, None)
    _klick(dialog.on_dismiss, None)
    # die übrigen Knoten bleiben, wo sie waren; der Platz steht über ihnen
    lagen = state.ablauf_lagen[plan.id]
    assert lagen == {ik: vorher[ik], ip: vorher[ip]}
    platz = _mit_daten(ansicht, "startplatz")
    oben = _mit_daten(ansicht, "knoten", ik)
    assert platz.top < oben.top and abs(platz.left - oben.left) < KNOTEN
    # die Dehnung in den Platz: ein neuer Knoten an der Stelle des alten Starts
    platz.content.on_accept(SimpleNamespace(src=SimpleNamespace(data=ud)))
    plan = state.plaene.laden(plan.id)
    assert plan.ablauf.start == id_ and not plan.ablauf.von(id_)
    assert state.ablauf_lagen[plan.id][id_] == vorher[iw]
    # Mit dem, was schon im Bild steht: der Punkt von „Start“, auf die Kniebeuge gezogen
    _ziehen(ansicht, START, ik)
    assert state.plaene.laden(plan.id).ablauf.start == ik


def test_unvollstaendiger_ablauf_startet_nicht_bis_er_repariert_ist(umgebung) -> None:
    """Ben, 16.11.2026: „Fehlermeldung soll kommen. Wenn Plan unvollständig kann er nicht
    durchgeführt werden, bis das repariert ist. Sonst ist es möglich, dass ein Plan
    durcheinander gerät.“ — liegt eine Übung des Ablaufs im Papierkorb, geht das Workout nicht
    mehr still durch sie hindurch: kein „Starten“, kein „Fortsetzen“, die rote Karte nennt
    sie und bietet an, sie aus dem Plan zu nehmen. Zurückholen repariert ebenso."""
    from trainingsapp.ui import plan_ablauf

    state, plan = umgebung
    basis = f"/plan/{plan.id}/bearbeiten"
    iw, ik, ip, id_ = (it.id for it in plan.items)
    eigen = ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ik, ip), Kante(ik, id_), Kante(ip, id_)))
    ablauf_speichern(state, plan.id, eigen)
    state.plaene.workout_setzen(plan.id, True, False)
    kniebeuge = next(it.exercise_id for it in plan.items if it.id == ik)

    state.uebungen.in_papierkorb(kniebeuge)  # eine Übung mitten im Ablauf
    plan = state.plaene.laden(plan.id)
    ids = [it.id for it in plan.items]
    assert ik not in ids and ab.fehlende(plan.ablauf, ids) == [ik]
    satz = (
        "Im Ablauf fehlt eine Übung (Kniebeuge) — der Plan muss korrigiert werden: die Übung "
        "zurückholen oder aus dem Plan nehmen."
    )
    # Reiter „Plan“: Zusammenfassung, rote Karte mit dem Namen und dem Knopf zur Reparatur
    assert ablauf_zusammenfassung(plan) == "Workout mit eigenem Ablauf — unvollständig."
    seite = _Seite()
    editor = plan_view(seite, state, plan, bearbeiten=True, basis=basis)
    warnung = next(
        x for x in _alle(editor) if isinstance(x, ft.Container) and x.data == "ablauf_warnung"
    )
    assert satz in _texte(warnung)
    # „Trainieren“: weder Starten noch Bereitstellen, und der Weg am Bildschirm vorbei lehnt ab
    start_bild = workout_view(_Seite(), state, plan, route=f"/plan/{plan.id}")
    assert any(t.startswith("Im Ablauf fehlt eine Übung") for t in _texte(start_bild))
    for knopf in ("Workout starten", "Bereitstellen"):
        with pytest.raises(AssertionError, match="kein Knopf"):
            _knopf(start_bild, knopf)
    with pytest.raises(ValueError, match="Im Ablauf fehlt eine Übung"):
        plan_ablauf.bereitstellen(_Seite(), state, plan)
    # Auch die Liste der Pläne sagt es — dort tippt man „Trainieren“
    from trainingsapp.ui.views.uebungen import plaene_liste

    assert any("muss korrigiert werden" in t for t in _texte(plaene_liste(_Seite(), state)))

    # Zurückholen repariert
    state.uebungen.aus_papierkorb(kniebeuge)
    plan = state.plaene.laden(plan.id)
    assert not ab.startet_nicht(plan.ablauf, [it.id for it in plan.items])
    assert not any("muss korrigiert" in t for t in _texte(plaene_liste(_Seite(), state)))
    _knopf(workout_view(_Seite(), state, plan, route=f"/plan/{plan.id}"), "Workout starten")

    # Oder: aus dem Plan nehmen — über dem Bild im Reiter „Ablauf“, mit Rückfrage
    state.uebungen.in_papierkorb(kniebeuge)
    plan = state.plaene.laden(plan.id)
    ansicht = ablauf_view(seite, state, plan, basis)
    warnung = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.data == "ablauf_warnung"
    )
    assert satz in _texte(warnung)
    _klick(_knopf(warnung, "„Kniebeuge“ aus dem Plan nehmen").on_click, None)
    dialog = seite.dialoge[-1]
    assert dialog.title.value == "„Kniebeuge“ aus dem Plan nehmen?"
    assert ik in [it.id for it in state.plaene.laden(plan.id, mit_verborgenen=True).items]
    _klick(_knopf(dialog, "Aus dem Plan nehmen").on_click, None)
    _klick(dialog.on_dismiss, None)
    plan = state.plaene.laden(plan.id, mit_verborgenen=True)
    assert [it.id for it in plan.items] == [iw, ip, id_]
    assert [(k.von, k.nach) for k in plan.ablauf.kanten] == [(ip, id_)]  # ihre Wege sind weg
    assert not ab.fehlende(plan.ablauf, [iw, ip, id_])
    assert not [
        x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.data == "ablauf_warnung"
    ]


def test_verborgene_startuebung_ist_kein_start(umgebung) -> None:
    """Liegt die **Startübung** im Papierkorb, wird nicht still die erste sichtbare Planübung
    der Start (P216): Das Bild zeigt „Start“ über dem leeren Platz, das Workout beginnt nicht —
    auch kein „Fortsetzen“ an einer Stelle von heute."""
    state, plan = umgebung
    iw, ik, ip, _id = (it.id for it in plan.items)
    ablauf_speichern(state, plan.id, ab.Ablauf(True, iw, (Kante(iw, ik), Kante(ik, ip))))
    state.plaene.workout_setzen(plan.id, True, False)
    wandsitz = next(it.exercise_id for it in plan.items if it.id == iw)
    state.uebungen.in_papierkorb(wandsitz)
    plan = state.plaene.laden(plan.id)
    ids = [it.id for it in plan.items]
    assert plan.ablauf.start == iw and plan.ablauf.startknoten(ids) is None
    assert ab.fehlende(plan.ablauf, ids) == [iw]
    ansicht = ablauf_view(_Seite(), state, plan, f"/plan/{plan.id}/bearbeiten")
    assert _daten(ansicht, "startplatz") == [("startplatz",)]
    start_bild = workout_view(_Seite(), state, plan, route=f"/plan/{plan.id}")
    for knopf in ("Workout starten", "Bereitstellen"):
        with pytest.raises(AssertionError, match="kein Knopf"):
            _knopf(start_bild, knopf)
    assert not [x for x in _alle(start_bild) if getattr(x, "data", None) == "fortsetzen"]
    # Ein Workout, das der Liste folgt, ist nie unvollständig: Die Liste ist der Ablauf
    state.plaene.ablauf_setzen(plan.id, ab.Ablauf(an=True))
    plan = state.plaene.laden(plan.id)
    assert not ab.startet_nicht(plan.ablauf, [it.id for it in plan.items])
    _knopf(workout_view(_Seite(), state, plan, route=f"/plan/{plan.id}"), "Workout starten")
