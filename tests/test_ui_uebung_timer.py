"""Timer einer Übung in der Oberfläche (Ben, 17.10.2026; Skizzen 12–15): Uhr neben dem i,
Profile und „zählt“, Starten, laufende Anzeige, „gemacht“ mit dem Eingetragenen."""

from __future__ import annotations

import asyncio

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.core.uebung_timer import TimerWahl, profile_der_uebung  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.uebung_timer import uebung_timer_view  # noqa: E402


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    """App-Zustand, dazu eine laufende HRV-Aufnahme auf der Uhr-Attrappe (ihre Uhr wird
    die der Einheit — so laufen Timer und Zeitleiste ohne zu warten)."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
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
    for name in ("content", "controls", "label", "leading"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if not isinstance(x, knoepfe):
            continue
        beschriftung = x.content.value if isinstance(x.content, ft.Text) else x.content
        if beschriftung == text:
            return x
    raise AssertionError(f"kein Knopf {text!r}")


def _planke(state, *, pause_zaehlt: bool = True) -> Exercise:
    hold = vorrat_feld("hold")
    profil = TimerProfil(
        id="halten",
        name="Halten 3 × 10 s",
        abschnitte=[Abschnitt("Halten", 10), Abschnitt("Pause", 5, zaehlt=pause_zaehlt)],
        runden=3,
    )
    uebung = Exercise(
        name="Planke",
        result_spec=ResultSpec(layout=Layout.SINGLE, fields=[hold] if hold else []),
        timer=[profil.als_dict()],
    )
    state.uebungen.speichern(uebung)
    return uebung


async def _bis_zum_ende(state, uhr, gurt, sekunden: int = 120) -> None:
    for _ in range(sekunden):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if state.einheit is not None:
            state.einheit.takt()
        if state.einheit is None:
            return
    for _ in range(200):
        if state.einheit is None:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Die Einheit endete nicht")


async def test_vorher_zaehlt_umschalten_speichert_in_der_uebung(umgebung) -> None:
    state, _, _ = umgebung
    uebung = _planke(state)
    seite = Seite()
    ansicht = uebung_timer_view(seite, state, f"/uebung/{uebung.id}", uebung)
    texte = _texte(ansicht)
    assert ansicht.appbar.title.value == "Timer · Planke" and "Halten 3 × 10 s" in texte
    assert "zählt: 0:45" in texte and "Laufzeit 0:45" in texte  # erst einmal zählt alles
    # Die Pause zählt erst einmal mit — Tipp: zählt nicht; gespeichert in der Übung
    zwei = [x for x in _alle(ansicht) if isinstance(x, ft.FilledButton) and x.content == "zählt"]
    assert len(zwei) == 2
    zwei[1].on_click()
    gespeichert = state.uebungen.laden(uebung.id)
    assert gespeichert is not None
    (profil,) = profile_der_uebung(gespeichert)
    assert [a.zaehlt for a in profil.abschnitte] == [True, False]


async def test_im_plan_haelt_die_planuebung_die_wahl(umgebung) -> None:
    state, _, _ = umgebung
    uebung = _planke(state)
    plan = Plan(name="Rumpf", subject_id=state.profil.id, items=[PlanItem(exercise_id=uebung.id)])
    state.plaene.speichern(plan)
    gespeichert = state.plaene.laden(plan.id)
    assert gespeichert is not None
    item = gespeichert.items[0]
    ansicht = uebung_timer_view(Seite(), state, f"/plan/{plan.id}", uebung, gespeichert, item)
    [x for x in _alle(ansicht) if isinstance(x, ft.FilledButton) and x.content == "zählt"][
        1
    ].on_click()
    wieder = state.plaene.item_laden(item.id)
    assert wieder is not None
    wahl = TimerWahl.aus_dict(wieder.timer)
    assert wahl.eigen is not None and [a.zaehlt for a in wahl.eigen.abschnitte] == [True, False]
    # Die Übung selbst bleibt, wie sie ist
    katalog = state.uebungen.laden(uebung.id)
    assert katalog is not None
    assert [a.zaehlt for a in profile_der_uebung(katalog)[0].abschnitte] == [True, True]


async def test_starten_laufen_fertig_gemacht(umgebung) -> None:
    state, uhr, gurt = umgebung
    uebung = _planke(state, pause_zaehlt=False)
    seite = Seite()
    basis = f"/uebung/{uebung.id}"
    _knopf(uebung_timer_view(seite, state, basis, uebung), "Starten").on_click()
    assert state.einheit is not None and state.einheit.laeuft
    for _ in range(12):  # Halten 1 vorbei, Pause läuft
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        state.einheit.takt()
    laufend = uebung_timer_view(seite, state, basis, uebung)
    texte = _texte(laufend)
    assert "Pause · zählt nicht" in texte
    assert texte.count("Satz 1") == 1 and "Satz 2" in texte and "Satz 3" in texte
    for text in ("Weiter", "Fertig", "Abbrechen"):
        _knopf(laufend, text)
    _knopf(laufend, "Fertig").on_click()
    await _bis_zum_ende(state, uhr, gurt)
    danach = uebung_timer_view(seite, state, basis, uebung)
    texte = _texte(danach)
    assert "Planke gemacht" in texte
    assert "Eingetragen · Haltezeit je Satz" in texte and "0:10" in texte
    assert "LÄUFE HEUTE" in texte and "eingetragen" in texte


async def test_uhr_neben_dem_i_im_plan(umgebung) -> None:
    from trainingsapp.ui.views.plan import plan_view

    state, _, _ = umgebung
    uebung = _planke(state)
    ohne = Exercise(name="Kniebeuge")
    state.uebungen.speichern(ohne)
    plan = Plan(
        name="Rumpf",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=uebung.id), PlanItem(exercise_id=ohne.id)],
    )
    state.plaene.speichern(plan)
    gespeichert = state.plaene.laden(plan.id)
    assert gespeichert is not None
    ansicht = plan_view(Seite(), state, gespeichert)
    uhren = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.icon in (ft.Icons.TIMER, ft.Icons.TIMER_OUTLINED)
    ]
    assert [u.tooltip for u in uhren] == ["Timer dieser Übung", "Timer festlegen"]
    assert any("Timer: Halten 3 × 10 s" in t for t in _texte(ansicht))


async def test_editor_baut_eine_folge_mit_zaehlt(umgebung) -> None:
    """Der Editor kann Teile (Folge) und „zählt“ je Abschnitt — gespeichert in der Übung."""
    from trainingsapp.ui.views.timer import timer_bearbeiten_view
    from trainingsapp.ui.views.uebung_timer import uebung_profilziel

    state, _, _ = umgebung
    uebung = _planke(state)
    seite = Seite()
    basis = f"/uebung/{uebung.id}"
    ziel = uebung_profilziel(state, basis, uebung)
    ansicht = timer_bearbeiten_view(seite, state, "halten", basis, ziel)
    assert ansicht.appbar.title.value == "Timer der Übung"
    _knopf(ansicht, "Teil anhängen").on_click()
    felder = [x for x in _alle(ansicht) if isinstance(x, ft.TextField)]
    teile = [f for f in felder if f.label == "Teil"]
    assert len(teile) == 2
    teile[0].value = "Training"
    # Der Cooldown zählt von sich aus nicht; die Pause des Trainings schalten wir aus
    zaehlt = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.TextButton) and x.content in ("zählt", "zählt nicht")
    ]
    assert [x.content for x in zaehlt] == ["zählt", "zählt", "zählt nicht"]
    zaehlt[1].on_click()
    await _knopf(ansicht, "Speichern").on_click()
    gespeichert = state.uebungen.laden(uebung.id)
    assert gespeichert is not None
    (profil,) = profile_der_uebung(gespeichert)
    assert profil.id == "halten" and profil.teil_name == "Training"
    assert [a.zaehlt for a in profil.abschnitte] == [True, False]
    assert [(t.name, [a.name for a in t.abschnitte]) for t in profil.teile] == [
        ("Cooldown", ["Cooldown"])
    ]
    assert seite.route == f"{basis}/timer/uebung/{uebung.id}"


async def test_editor_im_plan_speichert_eine_kopie_der_planuebung(umgebung) -> None:
    from trainingsapp.ui.views.timer import timer_bearbeiten_view
    from trainingsapp.ui.views.uebung_timer import uebung_profilziel

    state, _, _ = umgebung
    uebung = _planke(state)
    plan = Plan(name="Rumpf", subject_id=state.profil.id, items=[PlanItem(exercise_id=uebung.id)])
    state.plaene.speichern(plan)
    gespeichert = state.plaene.laden(plan.id)
    assert gespeichert is not None
    item = gespeichert.items[0]
    basis = f"/plan/{plan.id}"
    ziel = uebung_profilziel(state, basis, uebung, gespeichert, item)
    ansicht = timer_bearbeiten_view(Seite(), state, "halten", basis, ziel)
    name = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name")
    name.value = "Halten im Plan"
    await _knopf(ansicht, "Speichern").on_click()
    wahl = TimerWahl.aus_dict(state.plaene.item_laden(item.id).timer)
    assert wahl.eigen is not None and wahl.eigen.name == "Halten im Plan"
    katalog = state.uebungen.laden(uebung.id)
    assert katalog is not None and profile_der_uebung(katalog)[0].name == "Halten 3 × 10 s"


async def test_timer_aus_der_regel_laesst_sich_bearbeiten(umgebung) -> None:
    """Der Einzeltimer aus der Timer-Regel (Paket „Standard“) hat eine ID ohne Schrägstrich
    — sonst zerbräche die Route des Editors, und er legte ein neues Profil an."""
    from trainingsapp.ui.views.timer import timer_bearbeiten_view
    from trainingsapp.ui.views.uebung_timer import uebung_profilziel

    state, _, _ = umgebung
    uebung = Exercise(
        name="Kohärenzatmung", limit_spec={"rules": [{"type": "timer", "seconds": 300}]}
    )
    state.uebungen.speichern(uebung)
    (regel,) = profile_der_uebung(uebung)
    assert "/" not in regel.id
    basis = f"/uebung/{uebung.id}"
    ansicht = timer_bearbeiten_view(
        Seite(), state, regel.id, basis, uebung_profilziel(state, basis, uebung)
    )
    assert ansicht.appbar.title.value == "Timer der Übung"
    assert ansicht.route.endswith(f"/bearbeiten/{regel.id}")
    await _knopf(ansicht, "Speichern").on_click()
    gespeichert = state.uebungen.laden(uebung.id)
    assert gespeichert is not None
    assert [p.id for p in profile_der_uebung(gespeichert)] == [regel.id]


# ---------------------------------------------------------------------------
# Abschnitt „Timer“ im Übungsformular (Ben, 17.10.2026)
# ---------------------------------------------------------------------------


@pytest.fixture
def formular(tmp_path):
    state = AppState.starten(tmp_path / "app.db")
    a = TimerProfil(id="pa", name="Halten", abschnitte=[Abschnitt("Halten", 60)], runden=3)
    b = TimerProfil(id="pb", name="Kurz", abschnitte=[Abschnitt("Halten", 20)])
    u = Exercise(
        name="Planke",
        result_spec=ResultSpec(fields=[vorrat_feld("hold")]),
        timer=[a.als_dict(), b.als_dict()],
    )
    state.uebungen.speichern(u)
    yield state, state.uebungen.laden(u.id)
    state.schliessen()


def _symbolknopf(c, symbol, nummer: int = 0):
    knoepfe = [
        x for x in _alle(c) if isinstance(x, ft.IconButton) and x.icon == symbol and x.visible
    ]
    return knoepfe[nummer]


async def test_formular_timer_reihenfolge_bibliothek_entfernen(formular) -> None:
    """Die Profile der Übung im Formular: nach oben (das erste ist die Vorgabe), eine Kopie
    aus der Bibliothek, entfernen — gespeichert wird mit dem Formular."""
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    state, uebung = formular
    seite = Seite()
    ansicht = uebung_bearbeiten(seite, state, uebung)
    texte = _texte(ansicht)
    assert "TIMER" in texte and "Halten · Vorgabe" in texte and "Kurz" in texte
    _symbolknopf(ansicht, ft.Icons.ARROW_UPWARD).on_click()  # „Kurz“ nach oben
    assert "Kurz · Vorgabe" in _texte(ansicht)
    _knopf(ansicht, "Timer hinzufügen").on_click()
    dialog = seite.dialoge[-1]
    vorlage = state.timer_profile()[0]
    (zeile,) = [
        z
        for z in dialog.content.controls
        if isinstance(z, ft.ListTile) and z.title.value == vorlage.name
    ]
    zeile.on_click()
    await dialog.on_dismiss(None)  # neu gezeichnet erst, wenn der Dialog zu ist
    assert vorlage.name in _texte(ansicht)
    _symbolknopf(ansicht, ft.Icons.DELETE_OUTLINE, 1).on_click()  # „Halten“ entfernen
    await _knopf(ansicht, "Speichern").on_click()
    gespeichert = profile_der_uebung(state.uebungen.laden(uebung.id))
    assert [p.name for p in gespeichert] == ["Kurz", vorlage.name]
    assert gespeichert[1].id != vorlage.id  # eine eigene Kopie


async def test_formular_timer_editor_speichert_vorher(formular) -> None:
    """Der Stift öffnet den Editor über dem Formular — das Formular speichert vorher,
    denn beim Zurückkommen entsteht es neu. Eine neue Übung braucht zuerst einen Namen."""
    from trainingsapp.ui.views.timer import timer_bearbeiten_view
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten
    from trainingsapp.ui.views.uebung_timer import formular_profilziel

    state, uebung = formular
    seite = Seite()
    ansicht = uebung_bearbeiten(seite, state, uebung)
    name = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name")
    name.value = "Unterarmstütz"
    await _symbolknopf(ansicht, ft.Icons.EDIT_OUTLINED).on_click()
    formular_route = f"/uebung/{uebung.id}/bearbeiten"
    assert seite.route == f"{formular_route}/timer/profil/pa"
    assert state.uebungen.laden(uebung.id).name == "Unterarmstütz"
    # Der Editor speichert in die Übung und führt zurück ins Formular
    ziel = formular_profilziel(state, formular_route, state.uebungen.laden(uebung.id))
    editor = timer_bearbeiten_view(seite, state, "pa", formular_route, ziel)
    assert editor.route == f"{formular_route}/timer/profil/pa"
    assert ziel.zurueck == formular_route
    neu = TimerProfil(id="pa", name="Halten lang", abschnitte=[Abschnitt("Halten", 90)])
    ziel.speichern(neu)
    assert [p.name for p in profile_der_uebung(state.uebungen.laden(uebung.id))] == [
        "Halten lang",
        "Kurz",
    ]
    # Neue Übung: ohne Namen bleibt das Formular stehen, mit Namen geht es in den Editor
    leer = Seite()
    neue = uebung_bearbeiten(leer, state, None)
    _knopf(neue, "Timer hinzufügen").on_click()
    dialog = leer.dialoge[-1]
    neues_profil = next(
        z
        for z in dialog.content.controls
        if isinstance(z, ft.ListTile) and z.title.value == "Neues Profil"
    )
    neues_profil.on_click()
    await dialog.on_dismiss(None)
    assert leer.route == "/"
    feld = next(x for x in _alle(neue) if isinstance(x, ft.TextField) and x.label == "Name")
    assert feld.error == "Ein Name muss sein."
    feld.value = "Seitstütz mit Timer"  # „Seitstütz“ steht schon im Katalog
    _knopf(neue, "Timer hinzufügen").on_click()
    dialog = leer.dialoge[-1]
    next(
        z
        for z in dialog.content.controls
        if isinstance(z, ft.ListTile) and z.title.value == "Neues Profil"
    ).on_click()
    await dialog.on_dismiss(None)
    (seitstuetz,) = [u for u in state.uebungen.alle() if u.name == "Seitstütz mit Timer"]
    assert leer.route == f"/uebung/{seitstuetz.id}/bearbeiten/timer/profil"


def test_formular_ohne_eigenes_profil_nennt_die_timer_regel(tmp_path) -> None:
    """Ohne eigenes Profil gilt die Timer-Regel der Übung (Paket „Standard“) — als Hinweis."""
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    state = AppState.starten(tmp_path / "app.db")
    try:
        u = Exercise(name="Atmung", limit_spec={"rules": [{"type": "timer", "seconds": 300}]})
        state.uebungen.speichern(u)
        texte = _texte(uebung_bearbeiten(Seite(), state, state.uebungen.laden(u.id)))
        assert "Ohne eigenes Profil gilt die Timer-Regel der Übung: 5:00 Atmung." in texte
    finally:
        state.schliessen()
