"""Uhr und Fokus beim Üben (Ben, 8.11.2026, `docs/plan_uhr_fokus.md`, Skizzen F1–F7): die
Uhr-Zeile mit „Ohne Uhr“ und „Uhr einstellen …“, der Fokus-Schalter rechts neben „Gemacht“,
das Uhr-Blatt mit Geltung, die Karte „Eintragen“ im Fokus, die Pfeile im Fokus, die Ausführung
je Runde im Editor und „Alle Timer“."""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe, vorbei  # noqa: E402
from trainingsapp.core import varianten as var  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.timer import OHNE_UHR, Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.core.uebung_timer import TimerWahl, profile_der_uebung  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    yield state, uhr, gurt
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


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


def _geltung(blatt, wert: str) -> None:
    """Die Geltung des Uhr-Blatts umschalten: „jetzt“, „plan“ oder „uebung“."""
    segment = next(x for x in _alle(blatt) if isinstance(x, ft.SegmentedButton))
    segment.selected = [wert]
    segment.on_change(SimpleNamespace(control=segment))


def _uhr_zeile(blatt, profil_id: str):
    """Die Zeile einer Uhr im Uhr-Blatt (``data = ("uhr", <ID>)``)."""
    return next(
        x for x in _alle(blatt) if isinstance(x, ft.Container) and x.data == ("uhr", profil_id)
    )


def _uhr_ids(blatt) -> list[str]:
    """Was das Uhr-Blatt gerade zur Wahl stellt, in seiner Reihenfolge."""
    return [
        x.data[1]
        for x in _alle(blatt)
        if isinstance(x, ft.Container) and isinstance(x.data, tuple) and x.data[:1] == ("uhr",)
    ]


async def _aklick(handler, *args) -> None:
    ergebnis = handler(*args)
    if inspect.isawaitable(ergebnis):
        await ergebnis


async def _ticken(state, uhr, gurt, sekunden: int) -> None:
    for _ in range(sekunden):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if state.einheit is not None and not vorbei(state):
            state.einheit.takt()


async def _bis_zum_ende(state, uhr, gurt, sekunden: int = 120) -> None:
    for _ in range(sekunden):
        await _ticken(state, uhr, gurt, 1)
        if vorbei(state):
            return
    for _ in range(200):
        if vorbei(state):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Die Einheit endete nicht")


def _seitstuetz(state, *, uhr: bool = True) -> Exercise:
    """Haltezeit und Wiederholungen, Varianten links/rechts/beide, zwei Timer."""
    spec = ResultSpec(
        layout=Layout.SINGLE, fields=[f for k in ("hold", "reps") if (f := vorrat_feld(k))]
    )
    seiten = TimerProfil(
        id="seiten",
        name="Seiten L·R",
        abschnitte=[
            Abschnitt("Links", 10, ausfuehrung={"variant": "links"}),
            Abschnitt("Rechts", 10, ausfuehrung={"variant": "rechts"}),
        ],
    )
    halten = TimerProfil(id="halten", name="Halten 10 s", abschnitte=[Abschnitt("Halten", 10)])
    uebung = Exercise(
        name="Seitstütz",
        result_spec=var.mit_varianten(
            spec, [var.Variante("links"), var.Variante("rechts"), var.Variante("beide")]
        ),
        timer=[halten.als_dict(), seiten.als_dict()],
        uhr=uhr,
    )
    state.uebungen.speichern(uebung)
    return uebung


def _plan(state, *uebungen: Exercise) -> Plan:
    plan = Plan(
        name="Rumpf",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=u.id) for u in uebungen],
    )
    state.plaene.speichern(plan)
    geladen = state.plaene.laden(plan.id)
    assert geladen is not None
    return geladen


async def test_uhr_zeile_menue_und_fokus_schalter(umgebung) -> None:
    """F1: Uhr ▾ · Zeit · Takt · ▶ — kein „zählt“, kein ⧗ mehr in der Zeile; im Menü „Ohne Uhr“,
    „Uhr einstellen …“ und „Bereitstellen“. Rechts neben „Gemacht“ der Fokus-Schalter (P145)."""
    from trainingsapp.ui.views.plan import plan_view

    state, _, _ = umgebung
    u = _seitstuetz(state)
    plan = _plan(state, u)
    ansicht = plan_view(Seite(), state, plan)
    texte = _texte(ansicht)
    for t in ("Ohne Uhr — nur Fokus", "Uhr einstellen …", "Bereitstellen für „Alle starten“"):
        assert t in texte
    assert not any(
        isinstance(x, ft.Chip) and isinstance(x.label, ft.Text) and x.label.value == "zählt"
        for x in _alle(ansicht)
    )
    assert not any(
        isinstance(x, ft.IconButton) and x.icon == ft.Icons.HOURGLASS_TOP for x in _alle(ansicht)
    )
    assert state.fokus_auto()  # Vorgabe an (P145)
    schalter = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.CENTER_FOCUS_STRONG
    )
    schalter.on_click()
    assert not state.fokus_auto()
    ansicht = plan_view(Seite(), state, plan)
    assert any(
        isinstance(x, ft.IconButton) and x.icon == ft.Icons.CENTER_FOCUS_WEAK
        for x in _alle(ansicht)
    )


async def test_uhr_blatt_geltung_plan_uebung_und_neuer_timer(umgebung) -> None:
    """F3: Geltung In „Rumpf“ schreibt die Planübung, Übung die Übung (der gewählte Timer wird
    ihre Vorgabe); „Neuer Timer — nur in …“ öffnet gleich den Editor der Planübung. Beim Üben
    ist „Für jetzt“ die Vorgabe (Ben, 17.11.2026)."""
    from trainingsapp.ui.components.uhr_blatt import JETZT, PLAN, UEBUNG, uhr_blatt

    state, _, _ = umgebung
    u = _seitstuetz(state)
    plan = _plan(state, u)
    item = plan.items[0]
    seite = Seite()
    blatt = uhr_blatt(seite, state, uebung=u, plan=plan, item=item, basis=f"/plan/{plan.id}")
    segment = next(x for x in _alle(blatt) if isinstance(x, ft.SegmentedButton))
    assert segment.selected == [JETZT]
    assert [s.value for s in segment.segments] == ["jetzt", PLAN, UEBUNG]
    # Ohne Uhr — nur in diesem Plan
    _geltung(blatt, PLAN)
    zeile = next(
        x for x in _alle(blatt) if isinstance(x, ft.Container) and x.data == ("uhr", OHNE_UHR)
    )
    next(x for x in _alle(zeile) if isinstance(x, ft.IconButton)).on_click()
    _knopf(blatt, "Übernehmen").on_click()
    wahl = TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer)
    assert wahl.uhr is False
    assert state.uebungen.laden(u.id).uhr is True  # die Übung bleibt
    # Übung: „Seiten L·R“ wird ihre Vorgabe
    blatt = uhr_blatt(seite, state, uebung=u, plan=plan, item=item, basis=f"/plan/{plan.id}")
    segment = next(x for x in _alle(blatt) if isinstance(x, ft.SegmentedButton))
    segment.selected = [UEBUNG]
    segment.on_change(SimpleNamespace(control=segment))
    zeile = next(
        x for x in _alle(blatt) if isinstance(x, ft.Container) and x.data == ("uhr", "seiten")
    )
    next(x for x in _alle(zeile) if isinstance(x, ft.IconButton)).on_click()
    _knopf(blatt, "Übernehmen").on_click()
    assert [p.id for p in profile_der_uebung(state.uebungen.laden(u.id))] == ["seiten", "halten"]
    # Neuer Timer — nur in „Rumpf“: in den Editor der Planübung
    blatt = uhr_blatt(seite, state, uebung=u, plan=plan, item=item, basis=f"/plan/{plan.id}")
    _geltung(blatt, PLAN)
    await _aklick(_knopf(blatt, "Neuer Timer — nur in „Rumpf“").on_click)
    await blatt.on_dismiss(None)
    assert seite.route == f"/plan/{plan.id}/timer/uebung/{u.id}/{item.id}/bearbeiten"


async def test_ohne_uhr_oeffnet_den_fokus_ohne_zeit(umgebung) -> None:
    """F7, P146: „Uhr aus“ heißt „Ohne Uhr“ — ▶ öffnet den Fokus ohne Zeit; ins Tagebuch kommt
    keine Zeit, aber was im Fokus eingetragen wurde."""
    from trainingsapp.ui.components.uhr import uhr_teile
    from trainingsapp.ui.views.uebung_timer import uebung_timer_view

    state, uhr, gurt = umgebung
    u = _seitstuetz(state, uhr=False)
    seite = Seite()
    teile = uhr_teile(seite, state, uebung=u, plan=None, item=None, timer_oeffnen=lambda: None)
    assert "Ohne Uhr" in _texte(teile.zeile) and "—" in _texte(teile.zeile)
    play = next(
        x
        for x in _alle(teile.zeile)
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.PLAY_ARROW
    )
    play.on_click()
    assert state.einheit is not None and state.einheit.timer.lauf.profil.id == OHNE_UHR
    await _ticken(state, uhr, gurt, 8)
    fokus = uebung_timer_view(seite, state, f"/uebung/{u.id}", u)
    assert "Ohne Uhr — keine Zeit im Tagebuch" in _texte(fokus)
    # Erweitern statt ersetzen (8.11.2026 spät): die Knöpfe wie im Block (+10, +15, +20);
    # +15, +10, dann nimmt „−“ den letzten zurück
    _knopf(fokus, "+15").on_click()
    _knopf(fokus, "+10").on_click()
    assert "15 · 10  = 25" in _texte(fokus)
    next(
        x
        for x in _alle(fokus)
        if isinstance(x, ft.IconButton) and x.tooltip == "Letzten Satz zurücknehmen"
    ).on_click()
    assert "15" in _texte(fokus)
    _knopf(fokus, "Fertig").on_click()
    await _bis_zum_ende(state, uhr, gurt)
    (eintrag,) = [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]
    assert eintrag.result == {"reps": [15]}  # keine Haltezeit


async def test_fokus_karte_eintragen_und_pfeile_danach(umgebung) -> None:
    """F2, F6: Im Fokus die Karte „Eintragen“ mit der Ausführung der Runde (fest) und den
    Wiederholungen je Satz; nach dem Lauf fest oben die Pfeile — › bleibt im Fokus (P147)."""
    from trainingsapp.ui.views.uebung_timer import uebung_timer_view

    state, uhr, gurt = umgebung
    u = _seitstuetz(state)
    andere = Exercise(name="Luft anhalten")
    state.uebungen.speichern(andere)
    plan = _plan(state, u, andere)
    item = plan.items[0]
    basis = f"/plan/{plan.id}"
    seite = Seite()
    state.uhr_wahl[item.id] = "seiten"
    vorher = uebung_timer_view(seite, state, basis, u, plan, item)
    pfeile = next(x for x in _alle(vorher) if isinstance(x, ft.Container) and x.data == "pfeile")
    assert pfeile.visible and "1/2" in _texte(pfeile)
    _knopf(vorher, "Starten").on_click()
    await _ticken(state, uhr, gurt, 4)
    fokus = uebung_timer_view(seite, state, basis, u, plan, item)
    texte = _texte(fokus)
    assert "aus der Runde" in texte and "links" in texte
    # Im Lauf ein Fokus: keine Laufleiste; die Uhr fest oben, nicht in der scrollenden Spalte
    from trainingsapp.ui.components.fokus import FOKUS_ANSICHT

    assert fokus.data == FOKUS_ANSICHT
    scroll = next(
        x for x in _alle(fokus) if isinstance(x, ft.Column) and x.scroll == ft.ScrollMode.AUTO
    )
    uhren = [x for x in _alle(fokus) if isinstance(x, ft.Text) and x.size == 64]
    assert uhren and not any(u in list(_alle(scroll)) for u in uhren)
    # „Messung läuft weiter“ ist überall die Vorgabe (Ben, 8.11.2026 spät)
    assert state.messung_ende_beenden is False
    assert "Wiederholungen — niemand zählt" in texte
    # Der Überblick über die Sätze steht unter der Karte „Eintragen“ (Ben, 15.11.2026: Er schob
    # sie bei vielen Sätzen aus dem Blick)
    unten = _texte(scroll)
    eintragen = next(n for n, t in enumerate(unten) if t.startswith("Wiederholungen — niemand"))
    saetze = next(n for n, t in enumerate(unten) if t.startswith("Satz 1"))
    assert eintragen < saetze
    pfeile = next(x for x in _alle(fokus) if isinstance(x, ft.Container) and x.data == "pfeile")
    assert not pfeile.visible  # während die Uhr läuft, keine Pfeile
    _knopf(fokus, "+10").on_click()
    await _bis_zum_ende(state, uhr, gurt)
    eintraege = {
        e.result.get("variant"): e.result
        for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    }
    assert eintraege == {
        "links": {"variant": "links", "hold": [10], "reps": [10]},
        "rechts": {"variant": "rechts", "hold": [10]},
    }
    danach = uebung_timer_view(seite, state, basis, u, plan, item)
    texte = _texte(danach)
    assert "Eingetragen · links · Haltezeit je Satz" in texte
    with pytest.raises(AssertionError):
        _knopf(danach, "Nächste Übung")  # die Pfeile oben führen weiter
    pfeile = next(x for x in _alle(danach) if isinstance(x, ft.Container) and x.data == "pfeile")
    rechts = next(
        x
        for x in _alle(pfeile)
        if isinstance(x, ft.TextButton | ft.FilledTonalButton) and x.tooltip == "Nächste Übung"
    )
    assert isinstance(rechts, ft.FilledTonalButton)  # erledigt: betont
    await _aklick(rechts.on_click)
    zweite = plan.items[1]
    assert seite.route == f"{basis}/timer/uebung/{andere.id}/{zweite.id}"
    assert state.plan_gezeigt[plan.id] == zweite.id and state.ersetzen_bei == seite.route


async def test_editor_ausfuehrung_je_runde(umgebung) -> None:
    """F4: Im Editor des Übungs-Timers je Abschnitt die Zeile „Ausführung“ — der Name folgt der
    Wahl, die Vorschau nennt die Einträge je Ausführung."""
    from trainingsapp.ui.views.timer import timer_bearbeiten_view
    from trainingsapp.ui.views.uebung_timer import uebung_profilziel

    state, _, _ = umgebung
    u = _seitstuetz(state)
    basis = f"/uebung/{u.id}"
    ansicht = timer_bearbeiten_view(
        Seite(), state, "halten", basis, uebung_profilziel(state, basis, u)
    )
    assert "wie gewählt" in _texte(ansicht)
    _knopf(ansicht, "Abschnitt hinzufügen").on_click()
    chips = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Chip) and isinstance(x.label, ft.Text) and x.label.value == "rechts"
    ]
    assert len(chips) == 2
    chips[1].on_select()  # der neue Abschnitt: rechts
    namen = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.TextField) and isinstance(x.data, tuple) and x.data[:1] == ("name",)
    ]
    assert namen[1].value == "Rechts"
    assert any(t.startswith("Eingetragen wird je Ausführung ein Eintrag") for t in _texte(ansicht))
    await _knopf(ansicht, "Speichern").on_click()
    halten = next(p for p in profile_der_uebung(state.uebungen.laden(u.id)) if p.id == "halten")
    assert [a.ausfuehrung for a in halten.abschnitte] == [{}, {"variant": "rechts"}]


async def test_alle_timer_gruppen_und_loeschen(umgebung) -> None:
    """F5/Z3: Bibliothek, Nur an einer Übung (mit „gilt in …“) und Nur in Plänen; Löschen fragt
    und nennt die Pläne — danach gilt dort der nächste Timer."""
    from trainingsapp.ui.views.alle_timer import alle_timer_view

    state, _, _ = umgebung
    u = _seitstuetz(state)
    plan = _plan(state, u)
    item = plan.items[0]
    eigen = TimerProfil(id="eigen", name="Nur hier", abschnitte=[Abschnitt("H", 20)])
    state.plaene.timer_setzen(item.id, TimerWahl("", eigen).als_dict())
    seite = Seite()
    ansicht = alle_timer_view(seite, state, "/einstellungen")
    texte = _texte(ansicht)
    for kopf in ("BIBLIOTHEK · ZUM ZUORDNEN", "NUR AN EINER ÜBUNG", "NUR IN PLÄNEN"):
        assert kopf in texte
    assert any(t.startswith("Nur hier  ·  Rumpf › Seitstütz") for t in texte)
    zeile = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and isinstance(x.data, tuple) and x.data[2] == "halten"
    )
    menue = next(x for x in _alle(zeile) if isinstance(x, ft.PopupMenuButton))
    loeschen = next(x for x in menue.items if x.content is not None and _texte(x) == ["Löschen …"])
    loeschen.on_click()
    dialog = seite.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert "Er gilt in keinem Plan." in _texte(dialog)  # im Plan gilt die eigene Kopie
    _knopf(dialog, "Löschen").on_click()
    assert [p.id for p in profile_der_uebung(state.uebungen.laden(u.id))] == ["seiten"]
    # Die eigene Kopie: gilt in „Rumpf“
    ansicht = alle_timer_view(seite, state, "/einstellungen")
    zeile = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and isinstance(x.data, tuple) and x.data[2] == "eigen"
    )
    menue = next(x for x in _alle(zeile) if isinstance(x, ft.PopupMenuButton))
    next(x for x in menue.items if _texte(x) == ["Löschen …"]).on_click()
    assert "Er gilt in: Rumpf" in _texte(seite.dialoge[-1])[0]
    _knopf(seite.dialoge[-1], "Löschen").on_click()
    assert TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer).eigen is None


async def test_fuer_jetzt_mit_abschnitten(umgebung) -> None:
    """Ben, 9.11.2026 (Skizzen G1/G2): Für jetzt → Zeit stellen → „Mit Abschnitten …“ — der
    Editor stellt die Uhr für jetzt, nichts kommt in die Übung; nur „Als Timer der Übung
    speichern …“ hängt sie mit Namen an."""
    from trainingsapp.core.timer import EINMAL
    from trainingsapp.ui.components.uhr_blatt import JETZT, STELLEN, uhr_blatt
    from trainingsapp.ui.views.timer import timer_bearbeiten_view
    from trainingsapp.ui.views.uebung_timer import jetzt_profilziel

    state, _, _ = umgebung
    u = _seitstuetz(state)
    plan = _plan(state, u)
    item = plan.items[0]
    basis = f"/plan/{plan.id}"
    seite = Seite()
    blatt = uhr_blatt(seite, state, uebung=u, plan=plan, item=item, basis=basis)
    segment = next(x for x in _alle(blatt) if isinstance(x, ft.SegmentedButton))
    assert segment.selected == [JETZT]  # beim Üben die Vorgabe
    # kein Knopf mehr unter der Liste — „Timer stellen …“ steht in ihr, hinter der Stoppuhr
    assert "Zeit stellen …" not in _texte(blatt)
    await _aklick(_uhr_zeile(blatt, STELLEN).on_click)
    await _aklick(blatt.on_dismiss, None)
    zeit = seite.dialoge[-1]
    weiter = next(
        x for x in _alle(zeit) if isinstance(x, ft.Container) and x.data == "mit_abschnitten"
    )
    weiter.on_click(None)
    await _aklick(zeit.on_dismiss, None)
    await ruhe()
    route = f"{basis}/timer/uebung/{u.id}/{item.id}/bearbeiten/{EINMAL}"
    assert seite.route == route and state.uhr_einmal_start[item.id] == 60
    vorher = [p.id for p in profile_der_uebung(state.uebungen.laden(u.id))]

    # Das erweiterte Fenster: der erste Abschnitt hat die gestellte Zeit, einer kommt dazu
    editor = timer_bearbeiten_view(
        seite, state, EINMAL, basis, jetzt_profilziel(state, basis, u, plan, item)
    )
    assert editor.route == route and editor.appbar.title.value == "Für jetzt"
    assert "Gilt nur jetzt — bis die App neu startet" in _texte(editor)
    _knopf(editor, "Abschnitt hinzufügen").on_click()
    await _aklick(_knopf(editor, "Übernehmen").on_click)
    jetzt = state.uhr_einmal[item.id]
    assert jetzt.id == EINMAL and [a.dauer_s for a in jetzt.abschnitte] == [60, 60]
    assert state.uhr_wahl[item.id] == EINMAL
    assert [p.id for p in profile_der_uebung(state.uebungen.laden(u.id))] == vorher

    # Im Uhr-Blatt steht sie mit ✎ — gilt nur für jetzt
    blatt = uhr_blatt(seite, state, uebung=u, plan=plan, item=item, basis=basis)
    assert any(isinstance(x, ft.Container) and x.data == ("uhr", EINMAL) for x in _alle(blatt))
    assert "Für jetzt" in _texte(blatt)

    # Wieder geöffnet: die Abschnitte sind da; nur der Knopf speichert in die Übung
    editor = timer_bearbeiten_view(
        seite, state, EINMAL, basis, jetzt_profilziel(state, basis, u, plan, item)
    )
    assert len([x for x in _alle(editor) if isinstance(x, ft.Stack)]) == 2
    speichern = next(
        x for x in _alle(editor) if isinstance(x, ft.FilledTonalButton) and x.data == "als_profil"
    )
    assert speichern.content == "Als Timer der Übung speichern …"
    await _aklick(speichern.on_click)
    dialog = seite.dialoge[-1]
    feld = next(x for x in _alle(dialog) if isinstance(x, ft.TextField))
    feld.value = "L-R für jetzt"
    _knopf(dialog, "Speichern").on_click()
    profile = profile_der_uebung(state.uebungen.laden(u.id))
    neu = next(p for p in profile if p.name == "L-R für jetzt")
    assert len(neu.abschnitte) == 2 and state.uhr_wahl[item.id] == neu.id


async def test_eigener_timer_der_planuebung_bleibt_in_der_bibliothek(umgebung) -> None:
    """N71 (Ben, 11.11.2026): Wählt man unter „In Plan“ eine andere Zeile, verschwände der
    eigene Timer der Planübung — er bleibt als Eintrag der Bibliothek."""
    from trainingsapp.ui.components.uhr_blatt import uhr_blatt

    state, _, _ = umgebung
    u = _seitstuetz(state)
    plan = _plan(state, u)
    item = plan.items[0]
    eigen = TimerProfil(id="nur-hier", name="Nur hier", abschnitte=[Abschnitt("H", 20)])
    state.plaene.timer_setzen(item.id, TimerWahl("", eigen).als_dict())
    plan = state.plaene.laden(plan.id)
    item = plan.items[0]
    assert "nur-hier" not in [p.id for p in state.timer_profile()]
    blatt = uhr_blatt(Seite(), state, uebung=u, plan=plan, item=item, basis=f"/plan/{plan.id}")
    _geltung(blatt, "plan")
    zeile = next(
        x for x in _alle(blatt) if isinstance(x, ft.Container) and x.data == ("uhr", "seiten")
    )
    next(x for x in _alle(zeile) if isinstance(x, ft.IconButton)).on_click()
    _knopf(blatt, "Übernehmen").on_click()
    assert TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer).eigen is None
    assert "nur-hier" in [p.id for p in state.timer_profile()]


async def test_uhr_blatt_fuer_jetzt_ist_vorgabe_und_timer_stellen_steht_in_der_liste(
    umgebung,
) -> None:
    """Ben, 17.11.2026: „Setze standardmäßig den Button ‚Für jetzt‘ aktiv und dort zwischen
    Stoppuhr und ‚Ohne Uhr‘ bei Für jetzt den Button, um den Timer einzustellen.“ — die Zeile
    „Timer stellen …“ steht hinter der Stoppuhr, öffnet die Räder, und die gestellte Zeit ist
    danach gewählt. „Übernehmen“ ohne Änderung schreibt nichts fest."""
    from trainingsapp.core.timer import EINMAL, STOPPUHR
    from trainingsapp.ui.components.uhr_blatt import JETZT, PLAN, STELLEN, UEBUNG, uhr_blatt

    state, _, _ = umgebung
    u = _seitstuetz(state)
    plan = _plan(state, u)
    item = plan.items[0]
    basis = f"/plan/{plan.id}"
    seite = Seite()
    blatt = uhr_blatt(seite, state, uebung=u, plan=plan, item=item, basis=basis)
    segment = next(x for x in _alle(blatt) if isinstance(x, ft.SegmentedButton))
    assert segment.selected == [JETZT]
    ids = _uhr_ids(blatt)
    assert ids[:2] == [STOPPUHR, STELLEN] and ids[-1] == OHNE_UHR
    assert "Timer stellen …" in _texte(blatt)
    # Nur bei „Für jetzt“: In „Plan“ und Übung steht dafür „Neuer Timer …“ unter der Liste
    for g in (PLAN, UEBUNG):
        _geltung(blatt, g)
        assert STELLEN not in _uhr_ids(blatt)
    _geltung(blatt, JETZT)

    # Ohne Änderung übernommen: nichts gilt „für jetzt“, die Planübung bleibt ohne Wahl
    _knopf(blatt, "Übernehmen").on_click()
    assert item.id not in state.uhr_wahl and item.id not in state.uhr_zaehlt
    assert state.plaene.item_laden(item.id).timer == {}

    # Timer stellen: die Räder, 90 s — gilt für jetzt und ist gewählt
    blatt = uhr_blatt(seite, state, uebung=u, plan=plan, item=item, basis=basis)
    await _aklick(_uhr_zeile(blatt, STELLEN).on_click)
    await _aklick(blatt.on_dismiss, None)
    zeit = seite.dialoge[-1]
    feld = next(x for x in _alle(zeit) if isinstance(x, ft.TextField))
    feld.value = "1:30"
    await _aklick(_knopf(zeit, "Übernehmen").on_click)
    await _aklick(zeit.on_dismiss, None)
    assert state.uhr_einmal[item.id].gesamt_s() == 90 and state.uhr_wahl[item.id] == EINMAL
    assert state.plaene.item_laden(item.id).timer == {}  # gespeichert wird nichts

    # Wieder geöffnet: an derselben Stelle die gestellte Zeit, gewählt — mit dem Weg zum Ändern
    blatt = uhr_blatt(seite, state, uebung=u, plan=plan, item=item, basis=basis)
    ids = _uhr_ids(blatt)
    assert ids[:2] == [STOPPUHR, EINMAL] and STELLEN not in ids
    zeile = _uhr_zeile(blatt, EINMAL)
    assert zeile.bgcolor == ft.Colors.SECONDARY_CONTAINER
    neu = next(
        x for x in _alle(zeile) if isinstance(x, ft.IconButton) and x.data == "zeit_neu_stellen"
    )
    await _aklick(neu.on_click)
    await _aklick(blatt.on_dismiss, None)
    zeit = seite.dialoge[-1]
    # die Räder beginnen bei der gestellten Zeit
    assert next(x for x in _alle(zeit) if isinstance(x, ft.TextField)).value == "1:30"


async def test_timer_einer_planuebung_steht_den_anderen_im_plan_zur_wahl(umgebung) -> None:
    """Ben, 17.11.2026: „Wenn man einen Timer setzt im Bereich ‚In Plan‘, wird dieser Timer den
    anderen Übungen im Timereditor des Plans nicht zur Verfügung gestellt.“ — nachgestellt:
    Der „nur hier“-Timer der ersten Planübung stand an der zweiten nicht zur Wahl. Jetzt steht
    er unter „In Plan“ in der Liste; gewählt wird er **zugeordnet**, nicht kopiert: Er kommt in
    die Bibliothek, beide Planübungen verweisen darauf."""
    from trainingsapp.ui.components.uhr_blatt import PLAN, UEBUNG, uhr_blatt

    state, _, _ = umgebung
    u = _seitstuetz(state)
    v = Exercise(name="Brücke", result_spec=ResultSpec(Layout.SINGLE, [vorrat_feld("hold")]))
    state.uebungen.speichern(v)
    plan = _plan(state, u, v)
    erste, zweite = plan.items
    eigen = TimerProfil(id="nur-hier", name="Im Plan 40/20", abschnitte=[Abschnitt("H", 40)])
    state.plaene.timer_setzen(erste.id, TimerWahl("", eigen).als_dict())
    # die zweite hat schon einen eigenen — er darf mit der neuen Wahl nicht verschwinden (N71)
    alt = TimerProfil(id="alt-hier", name="Alt 30", abschnitte=[Abschnitt("H", 30)])
    state.plaene.timer_setzen(zweite.id, TimerWahl("", alt).als_dict())
    plan = state.plaene.laden(plan.id)
    erste, zweite = plan.items
    basis = f"/plan/{plan.id}"

    def blatt_der_zweiten(**mehr):
        return uhr_blatt(Seite(), state, uebung=v, plan=plan, item=zweite, basis=basis, **mehr)

    # Für jetzt und Übung: nicht dabei; unter „In Plan“ mit der Herkunft
    blatt = blatt_der_zweiten()
    assert "nur-hier" not in _uhr_ids(blatt)
    _geltung(blatt, UEBUNG)
    assert "nur-hier" not in _uhr_ids(blatt)
    _geltung(blatt, PLAN)
    assert "nur-hier" in _uhr_ids(blatt)
    assert "in diesem Plan · bei Seitstütz" in _texte(_uhr_zeile(blatt, "nur-hier"))
    # im Editor des Plans (Uhrenplan, „Im Plan einstellen“) ebenso
    assert "nur-hier" in _uhr_ids(blatt_der_zweiten(im_editor=True, jetzt_grund="nur beim Üben"))
    # an der Planübung selbst steht er einmal — als ihr eigener
    eigenes = uhr_blatt(Seite(), state, uebung=u, plan=plan, item=erste, basis=basis)
    _geltung(eigenes, PLAN)
    assert _uhr_ids(eigenes).count("nur-hier") == 1

    # gewählt und übernommen: ein gemeinsamer Timer, beide verweisen
    assert "nur-hier" not in [p.id for p in state.timer_profile()]
    next(x for x in _alle(_uhr_zeile(blatt, "nur-hier")) if isinstance(x, ft.IconButton)).on_click()
    _knopf(blatt, "Übernehmen").on_click()
    bibliothek = [p.id for p in state.timer_profile()]
    assert "nur-hier" in bibliothek and "alt-hier" in bibliothek
    for it in (erste, zweite):
        wahl = TimerWahl.aus_dict(state.plaene.item_laden(it.id).timer)
        assert wahl.eigen is not None and wahl.eigen.id == "nur-hier"
        assert wahl.eigen.bibliothek == "nur-hier"
    # in der Datenbank steht an beiden ein Verweis, keine Kopie
    roh = [
        r[0]
        for r in state.con.execute("SELECT timer_json FROM plan_item WHERE plan_id = ?", (plan.id,))
    ]
    assert all('"ref"' in (x or "") for x in roh)
