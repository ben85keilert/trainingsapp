"""Stoppuhr und Timer in der Übung (Ben, 18.10.2026; docs/plan_stoppuhr.md): die Zeile
(Vorgabe) und die Knöpfe, Anhalten und Weiter, Fertig trägt ein, Abbrechen ohne Rückfrage;
Uhr an/aus und „Zählt als“ an Übung und Planübung; die Stoppuhr im Timer-Menü; „Uhr und
Timer“ in der Info-Ansicht."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe, vorbei  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.uebung_timer import TimerWahl  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.ui.state import UHR_KNOEPFE, AppState  # noqa: E402
from trainingsapp.ui.views.plan import einzel_plan, plan_view  # noqa: E402


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    """App-Zustand mit einer laufenden HRV-Aufnahme auf der Uhr-Attrappe — ihre Uhr wird die
    der Einheit, so laufen Stoppuhr und Zeitleiste ohne zu warten."""
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
    for name in ("content", "controls", "label", "leading", "items", "title", "actions", "appbar"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if isinstance(x, knoepfe) and text in [*_texte(x.content), x.content]:
            return x
    raise AssertionError(f"kein Knopf {text!r}")


def _symbol(c, icon, tipp: str = ""):
    return next(
        x
        for x in _alle(c)
        if isinstance(x, ft.IconButton) and x.icon == icon and tipp in (x.tooltip or "")
    )


def _wahl(c, werte: set[str]):
    """Die Segmentwahl mit genau diesen Werten."""
    return next(
        x
        for x in _alle(c)
        if isinstance(x, ft.SegmentedButton) and {s.value for s in x.segments} == werte
    )


def _uhr_menue(c):
    return next(
        x
        for x in _alle(c)
        if isinstance(x, ft.PopupMenuButton) and x.tooltip == "Stoppuhr oder Timer wählen"
    )


def _wandsitz(state, **mehr) -> Exercise:
    u = Exercise(
        name="Wandsitz",
        result_spec=ResultSpec(layout=Layout.TIMED, fields=[vorrat_feld("hold")]),
        **mehr,
    )
    state.uebungen.speichern(u)
    return u


def _ansicht(state, uebung):
    return plan_view(Seite(), state, einzel_plan(uebung), einzel=True)


async def _sekunden(state, uhr, gurt, n: int) -> None:
    for _ in range(n):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if state.einheit is not None and state.einheit.laeuft:
            state.einheit.takt()


async def _bis_vorbei(state) -> None:
    for _ in range(300):
        if vorbei(state):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Die Einheit endete nicht")


def _eintraege(state):
    return [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]


async def test_stoppuhr_in_der_zeile_pause_haelt_nur_an(umgebung) -> None:
    """Die Zeile (Vorgabe): links „Stoppuhr“, rechts ▶. Läuft sie, zeigt die Übung Zeit,
    Anhalten und Fertig; „Anhalten“ hält nur an — „Fertig“ trägt einen Satz Haltezeit ein,
    die Pause zählt nicht (Ben: „Pause pausiert und beendet nicht“)."""
    state, uhr, gurt = umgebung
    uebung = _wandsitz(state)
    ansicht = _ansicht(state, uebung)
    assert "Stoppuhr" in _texte(ansicht) and "0:00" in _texte(ansicht)
    _symbol(ansicht, ft.Icons.PLAY_ARROW, "starten").on_click()
    e = state.einheit
    assert e is not None and e.laeuft and e.timer.lauf.vorwaerts
    await _sekunden(state, uhr, gurt, 30)
    ansicht = _ansicht(state, uebung)
    assert "Stoppuhr läuft" in _texte(ansicht) and "0:30" in _texte(ansicht)
    _knopf(ansicht, "Anhalten").on_click()
    await _sekunden(state, uhr, gurt, 20)
    ansicht = _ansicht(state, uebung)
    assert "Stoppuhr · angehalten" in _texte(ansicht) and "0:30" in _texte(ansicht)
    _knopf(ansicht, "Weiter").on_click()
    await _sekunden(state, uhr, gurt, 12)
    _knopf(_ansicht(state, uebung), "Fertig").on_click()
    await _sekunden(state, uhr, gurt, 1)
    await _bis_vorbei(state)
    (eintrag,) = _eintraege(state)
    assert eintrag.result == {"hold": [42]}
    assert "Stoppuhr" in _texte(_ansicht(state, uebung))  # die Zeile steht wieder bereit


async def test_abbrechen_ohne_rueckfrage_traegt_nichts_ein(umgebung) -> None:
    state, uhr, gurt = umgebung
    uebung = _wandsitz(state)
    seite = Seite()
    ansicht = plan_view(seite, state, einzel_plan(uebung), einzel=True)
    _symbol(ansicht, ft.Icons.PLAY_ARROW, "starten").on_click()
    await _sekunden(state, uhr, gurt, 15)
    _symbol(_ansicht(state, uebung), ft.Icons.CLOSE, "Abbrechen").on_click()
    assert seite.dialoge == []  # keine Rückfrage
    await _sekunden(state, uhr, gurt, 1)
    await _bis_vorbei(state)
    assert _eintraege(state) == []


async def test_ohne_haltezeit_zaehlt_die_uhr_als_zeit(umgebung) -> None:
    """Ohne Haltezeit immer Zeit — auch ohne den Parameter Zeit („auch ohne Chips/Kachel“)."""
    state, uhr, gurt = umgebung
    dehnen = Exercise(name="Dehnen")
    state.uebungen.speichern(dehnen)
    _symbol(_ansicht(state, dehnen), ft.Icons.PLAY_ARROW, "starten").on_click()
    await _sekunden(state, uhr, gurt, 75)
    _knopf(_ansicht(state, dehnen), "Fertig").on_click()
    await _sekunden(state, uhr, gurt, 1)
    await _bis_vorbei(state)
    (eintrag,) = _eintraege(state)
    assert eintrag.result == {"duration": 75}
    assert [f.label for f in eintrag.spec_snapshot.fields] == ["Zeit"]


async def test_knoepfe_uhr_und_timer_neben_gemacht(umgebung) -> None:
    """Darstellung „Knöpfe“ (B2): „Uhr“ startet die Stoppuhr; „Timer“ ohne Timer der Übung
    führt zu ihm, mit einem startet er ihn."""
    state, uhr, gurt = umgebung
    state.uhr_darstellung_setzen(UHR_KNOEPFE)
    uebung = _wandsitz(state)
    ansicht = _ansicht(state, uebung)
    assert "Stoppuhr" not in _texte(ansicht)  # keine Zeile
    _knopf(ansicht, "Timer")
    _knopf(ansicht, "Uhr").on_click()
    e = state.einheit
    assert e is not None and e.timer.lauf.vorwaerts
    assert "Stoppuhr läuft" in _texte(_ansicht(state, uebung))  # dieselbe Anzeige
    e.timer.lauf.abbrechen()
    await _sekunden(state, uhr, gurt, 1)
    await _bis_vorbei(state)


def test_uhr_aus_keine_uhr_in_der_uebung(umgebung) -> None:
    state, _, _ = umgebung
    uebung = _wandsitz(state, uhr=False)
    texte = _texte(_ansicht(state, uebung))
    assert "Stoppuhr" not in texte
    assert not [
        x
        for x in _alle(_ansicht(state, uebung))
        if isinstance(x, ft.IconButton) and "starten" in (x.tooltip or "")
    ]


def test_die_wahl_im_menue_aendert_keine_einstellung(umgebung) -> None:
    """Ben: „wenn im Übungsfeld ein anderer Timer ausgewählt wurde, ändert sich keine
    Einstellung“ — die Wahl gilt für die Sitzung, Übung und Planübung bleiben."""
    from trainingsapp.core.timer import Abschnitt, TimerProfil

    state, _, _ = umgebung
    halten = TimerProfil(id="h", name="Halten", abschnitte=[Abschnitt("Halten", 60)])
    uebung = _wandsitz(state, timer=[halten.als_dict()])
    ansicht = _ansicht(state, uebung)
    assert "Halten" in _texte(ansicht)  # ohne Wahl: der Timer der Übung
    stoppuhr = next(i for i in _uhr_menue(ansicht).items if "Stoppuhr" in _texte(i))
    stoppuhr.on_click()
    assert "Stoppuhr" in _texte(_uhr_menue(_ansicht(state, uebung)).content)
    assert state.uebungen.laden(uebung.id).timer == [halten.als_dict()]


async def test_stoppuhr_im_timer_menue(umgebung) -> None:
    """Im Timer (Leiste) ist die Stoppuhr der erste Reiter und die Vorgabe; sie zählt
    vorwärts, ohne Abschnitte, und „Fertig“ beendet sie."""
    from trainingsapp.ui.views.timer import timer_view

    state, _, _ = umgebung
    ansicht = timer_view(Seite(), state, "/")
    reiter = next(x for x in _alle(ansicht) if isinstance(x, ft.SegmentedButton))
    assert [s.value for s in reiter.segments] == ["stoppuhr", "einmal", "profile"]
    assert reiter.selected == ["stoppuhr"] and state.timer_profil().ist_stoppuhr
    texte = _texte(ansicht)
    assert "zählt vorwärts, bis du „Fertig“ tippst" in texte and "SO ZÄHLT SIE" in [
        t.upper() for t in texte
    ]


def _feld(ansicht, label: str) -> ft.TextField:
    return next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == label)


async def test_einmaluhren_name_marken_dauer_und_profile(umgebung) -> None:
    """Ben, 19.10.2026: Stoppuhr und Timer sind Einmaluhren mit Namen und dem Schalter,
    ob er in die Marken kommt; der Timer hat eine Dauer; Abschnitte baut der Editor ohne
    Namen; der Reiter „Profile“ führt zur Bibliothek."""
    from trainingsapp.core.timer import EINMAL, STOPPUHR, TimerLauf
    from trainingsapp.ui.views.timer import PROFILE, timer_bearbeiten_view, timer_view

    state, _, _ = umgebung
    ansicht = timer_view(Seite(), state, "/")
    reiter = next(x for x in _alle(ansicht) if isinstance(x, ft.SegmentedButton))

    # Stoppuhr: Name und Schalter wirken auf die Marken
    name = _feld(ansicht, "Name (optional)")
    name.value = "Dehnen"
    name.on_change()
    assert state.timer_einmal(STOPPUHR).name == "Dehnen"
    assert state.timer_profil().markenname == "Dehnen"
    assert TimerLauf(state.timer_profil()).markentext(0) == "Dehnen"
    schalter = next(x for x in _alle(ansicht) if isinstance(x, ft.Switch))
    schalter.value = False
    schalter.on_change()
    assert state.timer_profil().anzeigename == "Dehnen"
    assert state.timer_profil().markenname == "Stoppuhr"
    assert TimerLauf(state.timer_profil()).markentext(0) == "Stoppuhr"

    # Timer: zählt eine Dauer rückwärts, Vorgabe 5:00; Feld und Chips stellen sie
    reiter.on_change(SimpleNamespace(control=SimpleNamespace(selected=[EINMAL])))
    assert state.timer_profil().id == EINMAL and state.timer_profil().gesamt_s() == 300
    ansicht = timer_view(Seite(), state, "/")
    dauer = _feld(ansicht, "Dauer")
    dauer.value = "2:30"
    dauer.on_blur()
    assert state.timer_profil().gesamt_s() == 150 and state.timer_profil().einfach
    ansicht = timer_view(Seite(), state, "/")
    assert "Abschnitte und Runden …" in _texte(ansicht) or any(
        isinstance(x, ft.TextButton) and x.content == "Abschnitte und Runden …"
        for x in _alle(ansicht)
    )
    _feld(ansicht, "Name (optional)").value = "Atmen"
    _feld(ansicht, "Name (optional)").on_change()
    lauf = TimerLauf(state.timer_profil())
    assert lauf.markentext(0) == "Atmen" and lauf.markentext(1) == "Timer fertig"

    # Der Editor für den Einmal-Timer: ohne Namensfeld, „Übernehmen“ statt „Speichern“
    editor = timer_bearbeiten_view(Seite(), state, EINMAL, "/")
    assert editor.route == "/timer/bearbeiten/einmal"
    assert _feld(editor, "Name").visible is False
    assert any(isinstance(x, ft.TextButton) and x.content == "Übernehmen" for x in _alle(editor))
    seite = Seite()
    editor = timer_bearbeiten_view(seite, state, EINMAL, "/")
    next(
        x
        for x in _alle(editor)
        if isinstance(x, ft.TextButton) and x.content == "Abschnitt hinzufügen"
    ).on_click()
    await next(
        x for x in _alle(editor) if isinstance(x, ft.TextButton) and x.content == "Übernehmen"
    ).on_click()
    assert seite.route == "/timer"
    uhr = state.timer_profil()
    assert uhr.id == EINMAL and len(uhr.abschnitte) == 2 and uhr.name == "Atmen"
    assert (
        not uhr.einfach and state.timer_profile() == state.timer_profile()
    )  # nichts in der Bibliothek
    assert all(p.id != EINMAL for p in state.timer_profile())
    ansicht = timer_view(Seite(), state, "/")
    assert any(
        isinstance(x, ft.TextButton) and x.content == "Nur eine Dauer" for x in _alle(ansicht)
    )

    # Profile: die Bibliothek, zuletzt die Vorlage
    reiter = next(x for x in _alle(ansicht) if isinstance(x, ft.SegmentedButton))
    reiter.on_change(SimpleNamespace(control=SimpleNamespace(selected=[PROFILE])))
    assert state.timer_profil().id == "vorlage-intervall"
    ansicht = timer_view(Seite(), state, "/")
    chips = [x for x in _alle(ansicht) if isinstance(x, ft.Chip)]
    assert [_texte(c.label)[0] for c in chips] == ["Intervall 30/15", "Halten 3 × 1 min"]


async def test_formular_uhr_und_zaehlt_als(umgebung) -> None:
    """Übung bearbeiten: „Zählt als“ nur mit Haltezeit; gespeichert werden Uhr und Wahl —
    die Vorgabe (Haltezeit) bleibt leer."""
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    state, _, _ = umgebung
    uebung = _wandsitz(state)
    ansicht = uebung_bearbeiten(Seite(), state, uebung)
    wahl = _wahl(ansicht, {"hold", "duration"})
    assert wahl.selected == ["hold"]
    await _knopf(ansicht, "Speichern").on_click()
    assert state.uebungen.laden(uebung.id).zaehlt_als == ""  # unverändert: leer
    ansicht = uebung_bearbeiten(Seite(), state, state.uebungen.laden(uebung.id))
    wahl = _wahl(ansicht, {"hold", "duration"})
    wahl.selected = ["duration"]
    schalter = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Switch) and "Stoppuhr und Timer beim Üben" in str(x.label)
    )
    schalter.value = False
    zaehlt = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Switch) and x.label == "Timerzeit zählt"
    )
    assert zaehlt.value is True  # Vorgabe an (P79, D2)
    zaehlt.value = False
    await _knopf(ansicht, "Speichern").on_click()
    gespeichert = state.uebungen.laden(uebung.id)
    assert (gespeichert.uhr, gespeichert.zaehlt_als, gespeichert.zeit_zaehlt) == (
        False,
        "duration",
        False,
    )


async def test_planuebung_stellt_die_uhr_fuer_den_plan_ein(umgebung) -> None:
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen

    state, _, _ = umgebung
    uebung = _wandsitz(state)
    plan = Plan(name="Rumpf", subject_id=state.profil.id, items=[PlanItem(exercise_id=uebung.id)])
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    item = plan.items[0]
    seite = Seite()
    seite.views = []
    ansicht = plan_einstellen(seite, state, plan, item, uebung, f"/plaene/{plan.id}")
    uhr_wahl = _wahl(ansicht, {"uebung", "an", "aus"})
    uhr_wahl.selected = ["aus"]
    await _knopf(ansicht, "Speichern").on_click()
    wahl = TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer)
    assert wahl.uhr is False and state.uebungen.laden(uebung.id).uhr is True


def test_info_ansicht_zeigt_uhr_und_timer(umgebung) -> None:
    """Ben: „wenn eine Übung einen Timer hat, wird der in der Übungseinstellung gezeigt, aber
    nicht in der Informationsview“ — jetzt mit „Zählt als“."""
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    state, _, _ = umgebung
    uebung = _wandsitz(state)
    browser = SimpleNamespace(launch_url=None)
    texte = _texte(uebung_detail(Seite(), state, uebung, browser))
    assert "UHR UND TIMER" in texte and "Zählt als" in texte and "Haltezeit je Satz" in texte
