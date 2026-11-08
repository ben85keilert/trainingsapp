"""„Im Plan einstellen“ mit Karte „Beschleunigungssensor“ und Takt-Zeile (Ben, 5.11.2026, A6;
`docs/plan_beschleunigung.md` §13, `docs/plan_taktgeber.md` §5): dieselbe Ordnung wie „Übung
bearbeiten“ (P107), je Einstellung „wie die Übung“ oder „nur hier“ mit ↺, Zurück speichert; der
Knopf „Wdh. zählen“ in einer Planübung nur, wenn sie ein Wiederholungsfeld anbietet; beim Üben
gilt die Wahl der Planübung (Zähl-Teil, Uhr mit Takt), „für jetzt“ bleibt obenauf.

Der Brustgurt der Attrappen ist ein H10 mit Beschleunigung (`attrappen.Gurt`)."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe, vorbei  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.takt import AUS, VORLAGEN  # noqa: E402
from trainingsapp.core.zaehlen import SensorWahl  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.zaehlen import ZaehlBaustein  # noqa: E402
from trainingsapp.ui import einheit as einheit_ui  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.plan import plan_view  # noqa: E402
from trainingsapp.ui.views.plan_einstellen import KARTE, plan_einstellen  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    """App-Zustand mit verbundenem H10 (Beschleunigung) — wie in ``test_ui_zaehlen``."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    yield state, uhr, gurt
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


@pytest.fixture
def page():
    async def push_route(route: str) -> None:
        seite.routen.append(route)

    seite = SimpleNamespace(
        route="/",
        views=[],
        routen=[],
        dialoge=[],
        width=390,
        update=lambda: None,
        pop_dialog=lambda: seite.dialoge.pop() if seite.dialoge else None,
        push_route=push_route,
        run_task=lambda f, *a: None,
    )
    seite.show_dialog = seite.dialoge.append
    return seite


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "actions", "appbar", "label", "leading"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _klick(knopf, *args) -> None:
    ergebnis = (knopf.on_click or knopf.on_select)(*args)
    if inspect.isawaitable(ergebnis):
        asyncio.run(ergebnis)


KNOEPFE = ft.TextButton | ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton


def _knoepfe(wurzel, text: str) -> list:
    return [
        x
        for x in _alle(wurzel)
        if isinstance(x, KNOEPFE)
        and (x.content == text or (isinstance(x.content, ft.Control) and text in _texte(x.content)))
    ]


def _knopf(wurzel, text: str):
    gefunden = _knoepfe(wurzel, text)
    if not gefunden:
        raise AssertionError(f"kein Knopf {text!r}")
    return gefunden[0]


def _symbol(wurzel, icon, tipp: str = ""):
    return next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.IconButton) and x.icon == icon and tipp in (x.tooltip or "")
    )


def _chip(wurzel, text: str) -> ft.Chip:
    return next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.Chip) and isinstance(x.label, ft.Text) and x.label.value == text
    )


def _schalter(wurzel, label: str) -> ft.Switch:
    return next(x for x in _alle(wurzel) if isinstance(x, ft.Switch) and x.label == label)


def _umlegen(schalter: ft.Switch, wert: bool) -> None:
    schalter.value = wert
    schalter.on_change(SimpleNamespace(control=schalter))


def _sensor_karte(ansicht) -> ft.Container:
    """Die Karte „Beschleunigungssensor“: die Karte, die den Schalter „Atmung“ trägt."""
    return next(
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.Container)
        and c.bgcolor == KARTE
        and any(isinstance(x, ft.Switch) and x.label == "Atmung" for x in _alle(c))
    )


def _takt_zeile(ansicht) -> ft.Row:
    return next(
        r
        for r in _alle(ansicht)
        if isinstance(r, ft.Row)
        and any(isinstance(x, ft.Icon) and x.icon == ft.Icons.GRAPHIC_EQ for x in r.controls)
    )


def _schild_zurueck(wurzel) -> ft.Container | None:
    """Das Schild „nur hier“ mit ↺ — ``None``, wenn „wie die Übung“."""
    return next(
        (
            x
            for x in _alle(wurzel)
            if isinstance(x, ft.Container) and x.tooltip == "Zurück: wie die Übung"
        ),
        None,
    )


def _speichern(ansicht) -> None:
    _klick(next(x for x in _alle(ansicht.appbar) if isinstance(x, ft.TextButton)))


async def _sekunden(state, uhr, gurt, n: int) -> None:
    """``n`` Sekunden: Schlag, Beschleunigung, ein Takt der Einheit (wie ``test_ui_zaehlen``)."""
    for _ in range(n):
        uhr.t += 1
        gurt.schlag(1000)
        gurt.beschleunigung()
        await ruhe()
        e = state.einheit
        if e is not None and e.laeuft:
            e.takt()
            einheit_ui.melden(state)


async def _bis_vorbei(state, uhr, gurt) -> None:
    for _ in range(300):
        if vorbei(state):
            return
        await _sekunden(state, uhr, gurt, 1)
        await asyncio.sleep(0.01)
    raise AssertionError("Die Einheit endete nicht")


def _kniebeuge(state, *keys: str, **mehr) -> Exercise:
    spec = ResultSpec(
        layout=Layout.SINGLE, fields=[f for k in (keys or ("reps",)) if (f := vorrat_feld(k))]
    )
    u = Exercise(name="Kniebeuge", result_spec=spec, **mehr)
    state.uebungen.speichern(u)
    return state.uebungen.laden(u.id)


def _plan(state, uebung: Exercise, **item_felder) -> tuple[Plan, PlanItem]:
    plan = Plan(name="Beine", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, uebung.id)
    if item_felder:
        state.plaene.item_speichern(replace(item, **item_felder))
    plan = state.plaene.laden(plan.id)
    return plan, plan.items[0]


# -- Im Plan einstellen ---------------------------------------------------------------------------


def test_karte_wie_die_uebung_nur_hier_und_zurueck(page, state) -> None:
    """Die Karte nach „Uhr und Timer“ zeigt, was gilt (wie die Übung); ein umgelegter Schalter
    macht sie „nur hier“ mit Rahmen und ↺; ↺ holt die Übung zurück; was ihr gleicht, folgt ihr
    beim Speichern wieder (`bereinigt`). Zurück speichert."""
    u = _kniebeuge(state, "reps", beschleunigung=SensorWahl(vorlage="kniebeuge"))
    plan, item = _plan(state, u)
    ansicht = plan_einstellen(page, state, plan, item, u)
    texte = _texte(ansicht)
    assert "BESCHLEUNIGUNGSSENSOR" in texte and texte.index("UHR") < texte.index(
        "BESCHLEUNIGUNGSSENSOR"
    )
    karte = _sensor_karte(ansicht)
    assert _schalter(karte, "Wiederholungen").value and not _schalter(karte, "Atmung").value
    assert "wie die Übung" in _texte(karte) and _schild_zurueck(karte) is None
    assert karte.border is None
    bewegung = next(x for x in _alle(karte) if isinstance(x, ft.Dropdown))
    assert bewegung.value == "kniebeuge" and any("Umkehrpunkt oben" in t for t in _texte(karte))
    # Atmung an → nur hier, die Vorlage der Übung bleibt in der eigenen Karte
    _umlegen(_schalter(karte, "Atmung"), True)
    karte = _sensor_karte(ansicht)
    assert karte.border is not None and _schild_zurueck(karte) is not None
    assert _schalter(karte, "Atmung").value and "Wdh. zählen · Atmung" in " ".join(_texte(karte))
    _speichern(ansicht)
    gespeichert = state.plaene.item_laden(item.id)
    assert gespeichert.acc == SensorWahl(atmung=True, vorlage="kniebeuge")
    # Wieder aus → gleicht der Übung → folgt ihr wieder (nicht „nur hier“)
    ansicht = plan_einstellen(page, state, plan, gespeichert, u)
    _umlegen(_schalter(_sensor_karte(ansicht), "Atmung"), False)
    assert _schild_zurueck(_sensor_karte(ansicht)) is None
    _speichern(ansicht)
    assert state.plaene.item_laden(item.id).acc is None
    # Wiederholungen aus (nur hier), ↺ holt die Übung zurück
    ansicht = plan_einstellen(page, state, plan, state.plaene.item_laden(item.id), u)
    _umlegen(_schalter(_sensor_karte(ansicht), "Wiederholungen"), False)
    karte = _sensor_karte(ansicht)
    assert "Aus — in diesem Plan zählt der Sensor nicht." in _texte(karte)
    assert not any(isinstance(x, ft.Dropdown) for x in _alle(karte))  # keine Bewegung ohne Wdh.
    _schild_zurueck(karte).on_click()
    karte = _sensor_karte(ansicht)
    assert _schalter(karte, "Wiederholungen").value and _schild_zurueck(karte) is None
    # „Alles wie die Übung“ räumt auch die Karte auf
    _umlegen(_schalter(karte, "Atmung"), True)
    _klick(_knopf(ansicht, "Alles wie die Übung"))
    assert _schild_zurueck(_sensor_karte(ansicht)) is None
    _speichern(ansicht)
    assert state.plaene.item_laden(item.id).acc is None


def test_wiederholungen_nur_mit_wiederholungsfeld_im_plan_und_zaehlt_in(page, state) -> None:
    """Bietet die Planübung kein Wiederholungsfeld an, ist der Schalter ausgegraut und aus —
    ein Feld, das nur der Plan holt, schaltet ihn frei; „Zählt in“ nennt die Felder des Plans."""
    planke = _kniebeuge(state, "hold")
    plan, item = _plan(state, planke)
    ansicht = plan_einstellen(page, state, plan, item, planke)
    karte = _sensor_karte(ansicht)
    wdh = _schalter(karte, "Wiederholungen")
    assert wdh.disabled and not wdh.value
    assert any("Kein Wiederholungsfeld in diesem Plan" in t for t in _texte(karte))
    # „Wiederholungen“ aus dem Vorrat holen → der Schalter geht an
    _klick(_chip(ansicht, "Wiederholungen"))
    karte = _sensor_karte(ansicht)
    assert not _schalter(karte, "Wiederholungen").disabled
    assert _schalter(karte, "Wiederholungen").value
    assert "Wdh. zählen" in " ".join(_texte(karte))
    # Zwei Wiederholungsfelder: „Zählt in“ unter den Namen des Plans
    u = _kniebeuge(state, "reps", "reps_2")
    plan, item = _plan(state, u)
    ansicht = plan_einstellen(page, state, plan, item, u)
    karte = _sensor_karte(ansicht)
    assert "Zählt in" in _texte(karte)
    wahl = next(x for x in _alle(karte) if isinstance(x, ft.SegmentedButton))
    assert [s.value for s in wahl.segments] == ["reps", "reps_2"] and wahl.selected == ["reps"]
    wahl.selected = ["reps_2"]
    wahl.on_change(SimpleNamespace(control=wahl))
    assert _schild_zurueck(_sensor_karte(ansicht)) is not None
    _speichern(ansicht)
    assert state.plaene.item_laden(item.id).acc == SensorWahl(feld="reps_2")
    # Bietet der Plan nur das erste an, fällt „Zählt in“ weg
    nur_erstes = replace(state.plaene.item_laden(item.id), felder=["reps"])
    ansicht = plan_einstellen(page, state, plan, nur_erstes, u)
    assert "Zählt in" not in _texte(_sensor_karte(ansicht))


def test_takt_zeile_mit_stift_kreuz_und_zurueck(page, state) -> None:
    """In „Uhr und Timer“ die Zeile „Takt: …“: wie die Übung, der Stift öffnet das Blatt mit „In
    diesen Plan“, ✕ heißt ausdrücklich keiner (nur hier), ↺ wie die Übung."""
    u = _kniebeuge(state, "reps", takt=VORLAGEN["kniebeuge_2_1_2"])
    plan, item = _plan(state, u)
    ansicht = plan_einstellen(page, state, plan, item, u)
    zeile = _takt_zeile(ansicht)
    assert any(t.startswith("Takt: Kniebeuge 2-1-2") for t in _texte(zeile))
    assert _schild_zurueck(zeile) is None and "wie die Übung" in _texte(zeile)
    # Stift → Blatt → Metronom „In diesen Plan“
    _symbol(zeile, ft.Icons.EDIT_OUTLINED, "Takt nur hier").on_click()
    blatt = page.dialoge[-1]
    assert "In diesen Plan" in [k.content for k in _knoepfe(blatt, "In diesen Plan")]
    assert not _knoepfe(blatt, "In die Übung") and not _knoepfe(blatt, "Für jetzt")
    _chip(blatt, "Metronom 1 s").on_click()
    _knopf(blatt, "In diesen Plan").on_click()
    asyncio.run(blatt.on_dismiss(None))
    zeile = _takt_zeile(ansicht)
    assert any(t.startswith("Takt: Metronom 1 s") for t in _texte(zeile))
    assert _schild_zurueck(zeile) is not None
    _speichern(ansicht)
    gespeichert = state.plaene.item_laden(item.id)
    assert gespeichert.takt is not None and gespeichert.takt.name == "Metronom 1 s"
    # ✕ → ausdrücklich keiner; gespeichert als leerer Takt
    ansicht = plan_einstellen(page, state, plan, gespeichert, u)
    _symbol(_takt_zeile(ansicht), ft.Icons.CLOSE, "kein Takt").on_click()
    zeile = _takt_zeile(ansicht)
    assert "Takt: keiner" in _texte(zeile) and _schild_zurueck(zeile) is not None
    assert not _symbol(zeile, ft.Icons.CLOSE, "kein Takt").visible
    _speichern(ansicht)
    assert state.plaene.item_laden(item.id).takt is AUS
    # ↺ → wie die Übung
    ansicht = plan_einstellen(page, state, plan, state.plaene.item_laden(item.id), u)
    _schild_zurueck(_takt_zeile(ansicht)).on_click()
    zeile = _takt_zeile(ansicht)
    assert any(t.startswith("Takt: Kniebeuge 2-1-2") for t in _texte(zeile))
    _speichern(ansicht)
    assert state.plaene.item_laden(item.id).takt is None
    # Ein Takt wie der der Übung folgt ihr wieder — und „In die Übung übernehmen“ nennt den Takt
    ansicht = plan_einstellen(page, state, plan, state.plaene.item_laden(item.id), u)
    _symbol(_takt_zeile(ansicht), ft.Icons.EDIT_OUTLINED, "Takt nur hier").on_click()
    blatt = page.dialoge[-1]
    _chip(blatt, "Box 4-4-4-4").on_click()
    _knopf(blatt, "In diesen Plan").on_click()
    asyncio.run(blatt.on_dismiss(None))
    _klick(_knopf(ansicht, "In die Übung übernehmen …"))
    dialog = page.dialoge[-1]
    assert "• Takt „Box 4-4-4-4“" in _texte(dialog)
    dialog.open = True
    _klick(next(x for x in _alle(dialog) if isinstance(x, ft.FilledButton)))
    assert state.uebungen.laden(u.id).takt.name == "Box 4-4-4-4"
    assert state.plaene.item_laden(item.id).takt is None


def test_uebungsseite_zeigt_sensor_und_takt_der_planuebung(page, state) -> None:
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    u = _kniebeuge(state, "reps", takt=VORLAGEN["kniebeuge_2_1_2"])
    plan, item = _plan(state, u, acc=SensorWahl(wiederholungen=False, atmung=True), takt=AUS)
    browser = SimpleNamespace(launch_url=None)
    ansicht = uebung_detail(page, state, u, browser, item=item, plan=plan, einstellen="/x")
    texte = _texte(ansicht)
    assert "Sensor" in texte and "Atmung" in texte and "Takt" in texte and "keiner" in texte
    assert texte.count("nur hier") >= 2
    assert not any(t.startswith("Takt: Kniebeuge") for t in texte)


def test_timer_knopf_der_uebungsseite_im_plan_oeffnet_den_timer_der_planuebung(page, state) -> None:
    """Prüfrunde A6, Befund 5: Unter `/plan/<id>/info/<item>` führt der Timer-Knopf oben zum
    Timer **der Planübung** (`…/timer/uebung/<Übung>/<Planübung>` über dieser Seite), wie die
    Uhr im Plan — dort gilt der Takt der Planübung. Für sich bleibt es der Timer der Übung."""
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    u = _kniebeuge(state, "reps", takt=VORLAGEN["kniebeuge_2_1_2"])
    plan, item = _plan(state, u, takt=AUS)
    browser = SimpleNamespace(launch_url=None)
    route = f"/plan/{plan.id}/info/{item.id}"
    ansicht = uebung_detail(page, state, u, browser, item=item, plan=plan, route=route)
    _klick(_symbol(ansicht.appbar, ft.Icons.TIMER_OUTLINED, "Uhr dieser Übung"))
    assert page.routen == [f"{route}/timer/uebung/{u.id}/{item.id}"]
    page.routen.clear()
    _klick(_symbol(uebung_detail(page, state, u, browser).appbar, ft.Icons.TIMER_OUTLINED))
    assert page.routen == [f"/uebung/{u.id}/timer/uebung/{u.id}"]


# -- Beim Üben gilt die Planübung ----------------------------------------------------------------


async def test_ueben_nimmt_die_wahl_der_planuebung(umgebung) -> None:
    """Der Knopf und der Zähl-Teil folgen der Planübung: Atmung aus der Planübung, Vorlage
    „Automatisch“ statt der der Übung; ohne Wiederholungsfeld im Plan kein Knopf trotz Karte."""
    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state, "reps", uhr=False, beschleunigung=SensorWahl(vorlage="kniebeuge"))
    plan, _item = _plan(state, u, acc=SensorWahl(atmung=True, vorlage="auto"))
    (knopf,) = _knoepfe(plan_view(seite, state, plan), "Wdh. zählen · Atmung")
    knopf.on_click()
    z = state.einheit.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein)
    assert z.atem and z.wdh and z.vorlage == "auto"
    await _sekunden(state, uhr, gurt, 3)
    _knopf(plan_view(seite, state, plan), "Zählen abbrechen").on_click()
    await _bis_vorbei(state, uhr, gurt)
    # Nur abhaken im Plan: kein Knopf, auch wenn die Planübung Wiederholungen will
    planke = _kniebeuge(state, "hold", uhr=False)
    plan2, _ = _plan(state, planke, felder=[], acc=SensorWahl(wiederholungen=True))
    assert not _knoepfe(plan_view(seite, state, plan2), "Wdh. zählen")


async def test_uhr_nimmt_den_takt_der_planuebung_fuer_jetzt_obenauf(umgebung) -> None:
    """Die Uhr der Planübung bekommt den Takt der Planübung als Vorgabe (Planübung > Übung) —
    die Wahl „für jetzt“ geht vor, und mit `AUS` in der Planübung gibt es keinen."""
    from trainingsapp.ui.components.uhr import schluessel

    state, _uhr, _gurt = umgebung
    seite = Seite()
    u = Exercise(
        name="Atmen",
        result_spec=ResultSpec(layout=Layout.TIMED, fields=[vorrat_feld("hold")]),
        takt=VORLAGEN["atmung_4_6"],
    )
    state.uebungen.speichern(u)
    u = state.uebungen.laden(u.id)
    plan, item = _plan(state, u, takt=VORLAGEN["metronom_1"])
    ansicht = plan_view(seite, state, plan)
    takt_knopf = _symbol(ansicht, ft.Icons.GRAPHIC_EQ)
    assert takt_knopf.tooltip.startswith("Takt: Metronom 1 s")
    _symbol(ansicht, ft.Icons.PLAY_ARROW, "starten").on_click()
    e = state.einheit
    assert e is not None and e.timer is not None
    assert e.timer.lauf.takt_uebung is not None and e.timer.lauf.takt_uebung.name == "Metronom 1 s"
    assert e.timer.lauf.takt_aktuell().name == "Metronom 1 s"
    # Für jetzt obenauf
    state.uhr_takt[schluessel(u, item)] = VORLAGEN["box_4"]
    e.timer.lauf.takt_jetzt = VORLAGEN["box_4"]
    assert e.timer.lauf.takt_aktuell().name == "Box 4-4-4-4"
    state.uhr_takt.clear()
    # Ausdrücklich keiner in der Planübung (ihre Uhr steht noch, die andere läuft)
    plan2, _item2 = _plan(state, u, takt=AUS)
    ansicht = plan_view(seite, state, plan2)
    assert _symbol(ansicht, ft.Icons.GRAPHIC_EQ).tooltip == "Takt wählen"
