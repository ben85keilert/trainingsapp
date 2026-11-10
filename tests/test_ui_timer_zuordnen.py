"""Timer zuordnen (Skizzen Z3/Z4, `docs/plan_timer_zuordnen.md`): die Seite „Zuordnen“ mit dem
Filter der Übungsauswahl, „Alle Timer“ mit Bibliothek und „Gleiche zusammenlegen …“."""

from __future__ import annotations

import inspect

import pytest

ft = pytest.importorskip("flet")

from attrappen import Seite  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.core.uebung_timer import TimerWahl, profile_der_uebung, timer_fuer  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.timer_bibliothek import stellen_von  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


def _alle(c):
    yield c
    for name in ("content", "controls", "label", "appbar", "actions", "title", "items"):
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
            if isinstance(beschriftung, str) and beschriftung.startswith(text):
                return x
    raise AssertionError(f"kein Knopf {text!r}")


async def _klick(handler, *args) -> None:
    ergebnis = handler(*args)
    if inspect.isawaitable(ergebnis):
        await ergebnis


def _timer(state: AppState) -> TimerProfil:
    p = TimerProfil(id="t1", name="Planke 30/15", abschnitte=[Abschnitt("Halten", 30)])
    state.timer_profile_setzen([p])
    return p


def _uebungen(state: AppState) -> tuple[Exercise, Exercise, Exercise]:
    a = Exercise(name="ZZ Planke", typen=["Isometrie-Test"])
    b = Exercise(name="ZZ Seitstütz", typen=["Isometrie-Test"])
    c = Exercise(name="ZZ Kniebeuge", typen=["Kraft-Test"])
    for u in (a, b, c):
        state.uebungen.speichern(u)
    return a, b, c


def _haken(ansicht, art: str, schluessel: str):
    return next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Checkbox) and x.data == ("haken", art, schluessel)
    )


async def test_filter_dann_alle_ankreuzen_ordnet_zu(state) -> None:
    """Ben, 10.11.2026: mit dem Filter „jeder Isometrieübung einen Timer direkt zuweisen“."""
    from trainingsapp.ui.views.timer_zuordnen import timer_zuordnen_view

    profil = _timer(state)
    a, b, c = _uebungen(state)
    state.zuordnen_filter.typen.add("Isometrie-Test")
    seite = Seite()
    ansicht = timer_zuordnen_view(seite, state, "/einstellungen", profil)
    assert "ÜBUNGEN · 2" in _texte(ansicht)
    await _klick(_knopf(ansicht, "Alle 2 ankreuzen").on_click)
    assert _haken(ansicht, "uebung", a.id).value and _haken(ansicht, "uebung", b.id).value
    await _klick(_knopf(ansicht, "Zuordnen").on_click)
    assert seite.route == "/einstellungen/timer/alle"
    assert {s.uebung_id for s in stellen_von(state, "t1")} == {a.id, b.id}
    # verwiesen, nicht kopiert: in der Bibliothek geändert, gilt es an beiden
    state.timer_profile_setzen(
        [TimerProfil(id="t1", name="Planke 30/15", abschnitte=[Abschnitt("Halten", 45)])]
    )
    for u in (a, b):
        assert timer_fuer(state.uebungen.laden(u.id)).gesamt_s() == 45
    assert timer_fuer(state.uebungen.laden(c.id)) is None
    # Abwählen löst die Zuordnung wieder
    state.zuordnen_filter.leeren()
    ansicht = timer_zuordnen_view(seite, state, "/einstellungen", profil)
    assert "Vorgabe der Übung" in _texte(ansicht)
    _haken(ansicht, "uebung", a.id).on_change()
    await _klick(_knopf(ansicht, "Zuordnen").on_click)
    assert {s.uebung_id for s in stellen_von(state, "t1")} == {b.id}
    assert state.uebungen.laden(a.id).timer == []


async def test_plan_fuer_alle_uebungen_zuordnen(state) -> None:
    from trainingsapp.ui.views.timer_zuordnen import timer_zuordnen_view

    profil = _timer(state)
    a, _, _ = _uebungen(state)
    plan = Plan(name="Testplan", subject_id=state.profil.id)
    plan.items = [PlanItem(plan_id=plan.id, exercise_id=a.id)]
    state.plaene.speichern(plan)
    seite = Seite()
    ansicht = timer_zuordnen_view(seite, state, "/einstellungen", profil)
    _haken(ansicht, "plan", plan.id).on_change()
    await _klick(_knopf(ansicht, "Zuordnen").on_click)
    geladen = state.plaene.laden(plan.id)
    assert geladen.timer["bibliothek"] == "t1"
    assert timer_fuer(a, geladen, geladen.items[0]).name == "Planke 30/15"


async def test_alle_timer_bibliothek_und_zusammenlegen(state) -> None:
    """„gilt in …“ an der Bibliothek; inhaltsgleiche Kopien werden auf Bestätigung einer — eine
    Planübung, die die alte Kopie gewählt hatte, wählt den gemeinsamen."""
    from trainingsapp.ui.views.alle_timer import alle_timer_view

    state.timer_profile_setzen(
        [TimerProfil(id="lib", name="Anders", abschnitte=[Abschnitt("A", 5)])]
    )
    a, b, _ = _uebungen(state)
    for u, tid in ((a, "ka"), (b, "kb")):
        u.timer = [
            TimerProfil(id="vorn", name="Vorn", abschnitte=[Abschnitt("V", 10)]).als_dict()
            if u is b
            else TimerProfil(id="x", name="X", abschnitte=[Abschnitt("X", 11)]).als_dict(),
            TimerProfil(id=tid, name="Halten", abschnitte=[Abschnitt("H", 30)]).als_dict(),
        ]
        state.uebungen.speichern(u)
    plan = Plan(name="Rumpf", subject_id=state.profil.id)
    plan.items = [PlanItem(plan_id=plan.id, exercise_id=b.id, timer=TimerWahl("kb").als_dict())]
    state.plaene.speichern(plan)
    seite = Seite()
    ansicht = alle_timer_view(seite, state, "/einstellungen")
    assert any(t.endswith("nicht zugeordnet") for t in _texte(ansicht))
    _knopf(ansicht, "Gleiche zusammenlegen").on_click()
    dialog = seite.dialoge[-1]
    assert any("ZZ Planke, ZZ Seitstütz" in t for t in _texte(dialog))
    _knopf(dialog, "Zusammenlegen").on_click()
    pa = profile_der_uebung(state.uebungen.laden(a.id))
    pb = profile_der_uebung(state.uebungen.laden(b.id))
    assert [p.bibliothek for p in pa] == ["", "ka"] and [p.bibliothek for p in pb] == ["", "ka"]
    assert len(stellen_von(state, "ka")) == 2
    geladen = state.plaene.laden(plan.id)
    assert timer_fuer(state.uebungen.laden(b.id), geladen, geladen.items[0]).id == "ka"
    ansicht = alle_timer_view(seite, state, "/einstellungen")
    assert any(t.endswith("gilt in 2 Übungen") for t in _texte(ansicht))


def _zugeordnet(state) -> tuple[Exercise, Exercise]:
    """„Planke 30/15“ aus der Bibliothek an zwei Übungen."""
    from trainingsapp.ui.timer_bibliothek import zuordnung_setzen

    profil = _timer(state)
    a, b, _ = _uebungen(state)
    zuordnung_setzen(state, profil, {a.id, b.id}, set())
    return state.uebungen.laden(a.id), state.uebungen.laden(b.id)


def _zaehlt_umschalten(ansicht) -> None:
    chip = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.data == ("zaehlt", 0, 0)
    )
    chip.on_click()


async def _speichern_und_antworten(seite, ansicht, antwort: str) -> None:
    """„Speichern“ tippen und im Dialog „Überall ändern · Nur hier“ antworten."""
    import asyncio

    lauf = asyncio.ensure_future(_knopf(ansicht, "Speichern").on_click())
    await asyncio.sleep(0)
    dialog = seite.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert "„Planke 30/15“ gilt an 2 Stellen" in _texte(dialog)
    if antwort:
        next(x for x in _alle(dialog) if getattr(x, "data", None) == antwort).on_click()
    else:
        _knopf(dialog, "Abbrechen").on_click()
    await lauf


async def test_speichern_fragt_ueberall_oder_nur_hier(state) -> None:
    """Z4: Ein Timer an zwei Übungen, an einer geändert — „Nur hier“ legt dort eine Kopie an,
    die andere bleibt; „Überall ändern“ ändert die Bibliothek; Abbrechen speichert nichts."""
    from trainingsapp.ui.views.timer import timer_bearbeiten_view
    from trainingsapp.ui.views.uebung_timer import uebung_profilziel

    a, b = _zugeordnet(state)
    basis = f"/uebung/{a.id}"

    def editor(seite):
        frisch = state.uebungen.laden(a.id)
        ziel = uebung_profilziel(state, basis, frisch)
        ansicht = timer_bearbeiten_view(seite, state, profile_der_uebung(frisch)[0].id, basis, ziel)
        seite.views = [ansicht]
        return ansicht

    # Abbrechen: nichts gespeichert, der Editor bleibt
    seite = Seite()
    ansicht = editor(seite)
    _zaehlt_umschalten(ansicht)
    await _speichern_und_antworten(seite, ansicht, "")
    assert seite.route == "/"
    assert state.timer_profile()[0].abschnitte[0].zaehlt is True
    # Nur hier: Kopie an Übung a, Bibliothek und Übung b unverändert
    await _speichern_und_antworten(seite, ansicht, "hier")
    pa = profile_der_uebung(state.uebungen.laden(a.id))
    assert [(p.name, p.bibliothek, p.abschnitte[0].zaehlt) for p in pa] == [
        ("Planke 30/15 (ZZ Planke)", "", False)
    ]
    pb = profile_der_uebung(state.uebungen.laden(b.id))
    assert [(p.bibliothek, p.abschnitte[0].zaehlt) for p in pb] == [("t1", True)]
    assert len(stellen_von(state, "t1")) == 1
    # Ohne Änderung fragt nichts; an nur einer Stelle auch nicht
    seite = Seite()
    frisch = state.uebungen.laden(b.id)
    ziel = uebung_profilziel(state, f"/uebung/{b.id}", frisch)
    ansicht = timer_bearbeiten_view(seite, state, "t1", f"/uebung/{b.id}", ziel)
    _zaehlt_umschalten(ansicht)
    await _knopf(ansicht, "Speichern").on_click()
    assert not [d for d in seite.dialoge if isinstance(d, ft.AlertDialog)]
    assert state.timer_profile()[0].abschnitte[0].zaehlt is False  # in der Bibliothek geändert


async def test_ueberall_aendern_schreibt_die_bibliothek(state) -> None:
    from trainingsapp.ui.views.timer import timer_bearbeiten_view
    from trainingsapp.ui.views.uebung_timer import uebung_profilziel

    a, b = _zugeordnet(state)
    seite = Seite()
    ziel = uebung_profilziel(state, f"/uebung/{a.id}", a)
    ansicht = timer_bearbeiten_view(seite, state, "t1", f"/uebung/{a.id}", ziel)
    _zaehlt_umschalten(ansicht)
    await _speichern_und_antworten(seite, ansicht, "ueberall")
    assert state.timer_profile()[0].abschnitte[0].zaehlt is False
    for u in (a, b):
        (p,) = profile_der_uebung(state.uebungen.laden(u.id))
        assert (p.bibliothek, p.abschnitte[0].zaehlt) == ("t1", False)


async def test_im_plan_geaendert_wird_eigene_kopie(state) -> None:
    """Im Plan heißt „nur hier“: eigene Kopie der Planübung — die Bibliothek bleibt, ohne Frage."""
    from trainingsapp.ui.views.timer import timer_bearbeiten_view
    from trainingsapp.ui.views.uebung_timer import uebung_profilziel

    a, _ = _zugeordnet(state)
    plan = Plan(name="Testplan", subject_id=state.profil.id)
    plan.items = [PlanItem(plan_id=plan.id, exercise_id=a.id)]
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    item = plan.items[0]
    seite = Seite()
    ziel = uebung_profilziel(state, f"/plan/{plan.id}", a, plan, item)
    ansicht = timer_bearbeiten_view(seite, state, "t1", f"/plan/{plan.id}", ziel)
    _zaehlt_umschalten(ansicht)
    await _knopf(ansicht, "Speichern").on_click()
    assert not [d for d in seite.dialoge if isinstance(d, ft.AlertDialog)]
    eigen = TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer).eigen
    assert eigen is not None and eigen.bibliothek == "" and eigen.id != "t1"
    assert eigen.name == "Planke 30/15 (Testplan)" and eigen.abschnitte[0].zaehlt is False
    assert state.timer_profile()[0].abschnitte[0].zaehlt is True
