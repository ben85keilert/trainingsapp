"""Reiter in „Übung bearbeiten“ und „Im Plan einstellen“ (Ben, 12.11.2026).

Fünf Reiter mit Symbol und Wort — Übung · Parameter · Uhr · Sensor · Material; ein Formular,
die Reiter schalten nur um. Dazu: „Timer hinzufügen“ über dem Takt und ohne Doppelte, der
Sprung auf den Reiter „Uhr“, die Ordnung der Parameter und „In ein Paket verschieben /
kopieren“.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.eigenes_paket import EigenesPaket  # noqa: E402
from trainingsapp.core.models import Exercise, Plan  # noqa: E402
from trainingsapp.core.result_spec import FELDVORRAT, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.ui.components import editor_reiter as er  # noqa: E402
from trainingsapp.ui.components import paketwechsel  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.uebung_bearbeiten import SCHON_DABEI, uebung_bearbeiten  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    async def push_route(route: str) -> None:
        seite.routen.append(route)

    def run_task(f, *args):
        seite.aufgaben.append((f, args))  # der Test lässt sie laufen (`_aufgaben`)

    seite = SimpleNamespace(
        route="/",
        views=[],
        routen=[],
        dialoge=[],
        aufgaben=[],
        width=390,
        update=lambda: None,
        pop_dialog=lambda: None,
        push_route=push_route,
        run_task=run_task,
    )
    seite.show_dialog = seite.dialoge.append
    return seite


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "title",
        "subtitle",
        "actions",
        "appbar",
        "label",
        "leading",
        "trailing",
        "tabs",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _daten(c, data: str):
    return next(x for x in _alle(c) if getattr(x, "data", None) == data)


def _knopf(c, text: str):
    """Ein Knopf an seinem Text — Flet hält ihn als ``content`` (Text oder Zeichenkette)."""
    return next(
        x
        for x in _alle(c)
        if isinstance(x, ft.TextButton | ft.OutlinedButton | ft.FilledButton)
        and (x.content == text or text in _texte(x))
    )


def _zu(page, dialog) -> None:
    """Der Dialog ist zu: was danach laufen soll, läuft — auch die Aufgaben der Seite."""
    asyncio.run(dialog.on_dismiss(None))
    while page.aufgaben:
        f, args = page.aufgaben.pop(0)
        asyncio.run(f(*args))


def _klick(knopf, *args) -> None:
    ergebnis = knopf.on_click(*args)
    if inspect.isawaitable(ergebnis):
        asyncio.run(ergebnis)


def _uebung(state: AppState, *keys: str, **mehr) -> Exercise:
    u = Exercise(
        name="Unterarmstütz",
        result_spec=ResultSpec(fields=[vorrat_feld(k) for k in keys or ("hold",)]),
        **mehr,
    )
    state.uebungen.speichern(u)
    return state.uebungen.laden(u.id)


def _seite(ansicht, key: str):
    return _daten(ansicht, f"reiter_{key}")


def test_fuenf_reiter_mit_wort_und_symbol_einer_ist_offen(page, state) -> None:
    u = _uebung(state)
    ansicht = uebung_bearbeiten(page, state, u)
    assert ansicht.appbar.title.value == "Unterarmstütz"  # der Name, nicht „Übung bearbeiten“
    leiste = _daten(ansicht, "editor_reiter")
    tabs = [t for t in _alle(leiste) if isinstance(t, ft.Tab)]
    assert [t.label for t in tabs] == ["Übung", "Parameter", "Uhr", "Sensor", "Material"]
    assert all(t.icon for t in tabs)
    assert [k for k in er.SCHLUESSEL if _seite(ansicht, k).visible] == [er.UEBUNG]
    # Ein Tipp schaltet um — dasselbe Formular, nichts wird neu gebaut
    feld = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name")
    leiste.selected_index = 2
    leiste.on_change(SimpleNamespace(control=leiste))
    assert [k for k in er.SCHLUESSEL if _seite(ansicht, k).visible] == [er.UHR]
    assert feld in list(_alle(ansicht))
    # Was wo steht
    assert "ORDNEN" in _texte(_seite(ansicht, er.UEBUNG))
    assert {"PARAMETER", "VARIANTEN"} <= set(_texte(_seite(ansicht, er.PARAMETER)))
    assert "BESCHLEUNIGUNGSSENSOR" in _texte(_seite(ansicht, er.SENSOR))
    assert "VIDEOS, LINKS UND DATEIEN" in _texte(_seite(ansicht, er.MATERIAL))
    # Uhr: „Timer hinzufügen“ steht über dem Takt
    uhr = list(_alle(_seite(ansicht, er.UHR)))
    takt = next(i for i, x in enumerate(uhr) if isinstance(x, ft.Text) and "Takt" in str(x.value))
    assert uhr.index(_knopf(ansicht, "Timer hinzufügen")) < takt


def test_gemerkter_reiter_und_fehler_springt_zum_namen(page, state) -> None:
    u = _uebung(state)
    route = f"/uebung/{u.id}/bearbeiten"
    er.merken(state, route, er.UHR)  # „In der Übung festlegen“ auf der Timer-Seite
    ansicht = uebung_bearbeiten(page, state, u)
    assert _seite(ansicht, er.UHR).visible and not _seite(ansicht, er.UEBUNG).visible
    # Speichern ohne Namen: der Reiter mit dem Fehler kommt nach vorn
    feld = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name")
    feld.value = ""
    speichern = _knopf(ansicht, "Speichern")
    _klick(speichern)
    assert _seite(ansicht, er.UEBUNG).visible and feld.error
    # Gespeichert: der nächste Besuch beginnt vorn
    feld.value = "Unterarmstütz"
    _klick(speichern)
    assert er.gemerkt(state, route) == er.UEBUNG


def test_timer_hinzufuegen_graut_vorhandene_aus(page, state) -> None:
    halten = TimerProfil(id="h", name="Halten", abschnitte=[Abschnitt("Halten", 30)])
    state.timer_in_bibliothek(halten)
    u = _uebung(state)
    ansicht = uebung_bearbeiten(page, state, u)
    knopf = _knopf(ansicht, "Timer hinzufügen")
    _klick(knopf)
    zeile = next(
        x for x in _alle(page.dialoge[-1]) if isinstance(x, ft.ListTile) and "Halten" in _texte(x)
    )
    assert not zeile.disabled and zeile.data is None
    _klick(zeile)
    _zu(page, page.dialoge[-1])
    _klick(knopf)
    zeile = next(
        x for x in _alle(page.dialoge[-1]) if isinstance(x, ft.ListTile) and "Halten" in _texte(x)
    )
    assert zeile.disabled and zeile.data == SCHON_DABEI and zeile.on_click is None
    assert "schon dabei" in _texte(zeile)


def test_ordnung_der_parameter_in_der_ganzen_app(page, state) -> None:
    """Zeit, Wiederholungen, Haltezeit, Skala, Text, Seite, Winkel, Gewicht, Strecke, Ja/Nein."""
    from trainingsapp.core.parameter import auspraegungsfelder, mengenfelder

    assert [f.key for f in FELDVORRAT] == [
        "duration",
        "reps",
        "hold",
        "scale",
        "note",
        "side",
        "angle",
        "weight",
        "distance",
        "done",
    ]
    # Gespeichert in alter Folge — gezeigt in der neuen
    u = _uebung(state, "reps", "hold", "weight", "distance", "duration", "angle", "side")
    assert [f.key for f in u.result_spec.fields][:2] == ["reps", "hold"]
    assert [f.key for f in mengenfelder(u.result_spec)] == ["duration", "reps", "hold", "distance"]
    assert [f.key for f in auspraegungsfelder(u.result_spec)] == ["side", "angle", "weight"]


def test_kopie_in_ein_paket_und_verschieben(page, state) -> None:
    paket = EigenesPaket(name="Rücken")
    state.eigene_pakete.speichern(paket)
    eigen = _uebung(state)
    assert paketwechsel.gehoert_zu(state, eigen) == "Eigene"
    # Verschieben: nur die Auswahl der eigenen Pakete ändert sich
    assert paketwechsel.verschieben(state, eigen, paket.id)
    assert state.eigene_pakete.laden(paket.id).uebungen == [eigen.id]
    assert paketwechsel.gehoert_zu(state, eigen) == "Rücken"
    assert paketwechsel.verschieben(state, eigen, paketwechsel.EIGENE)
    assert state.eigene_pakete.laden(paket.id).uebungen == []
    # Kopie: neue ID, eigene Übung, gleich im Paket
    kopie = paketwechsel.kopieren(state, eigen, paket.id)
    assert kopie.id != eigen.id and kopie.package_id is None and kopie.name.endswith("(Kopie)")
    assert state.eigene_pakete.laden(paket.id).uebungen == [kopie.id]
    # Eine Paketübung gehört ihrem Paket: kopieren ja, verschieben nein
    knie = next(u for u in state.uebungen.alle() if u.package_id and u.name == "Kniebeuge")
    assert not paketwechsel.verschieben(state, knie, paket.id)
    ansicht = uebung_bearbeiten(page, state, knie)
    assert _daten(ansicht, "paket_verschieben").disabled
    _klick(_daten(ansicht, "paket_kopieren"))
    dialog = page.dialoge[-1]
    _klick(_daten(dialog, f"paketziel_{paket.id}"))
    _zu(page, dialog)
    neu = [i for i in state.eigene_pakete.laden(paket.id).uebungen if i != kopie.id]
    assert len(neu) == 1 and state.uebungen.laden(neu[0]).package_id is None
    assert page.routen[-1] == f"/uebung/{neu[0]}/bearbeiten"
    assert state.uebungen.laden(knie.id).package_id == knie.package_id  # das Original bleibt


def test_im_plan_einstellen_hat_dieselben_reiter(page, state) -> None:
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen

    u = _uebung(state, "reps")
    plan = Plan(name="Rücken", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    plan = state.plaene.laden(plan.id)
    basis = f"/plan/{plan.id}/bearbeiten"
    ansicht = plan_einstellen(page, state, plan, item, u, basis)
    leiste = _daten(ansicht, "editor_reiter")
    assert [t.label for t in _alle(leiste) if isinstance(t, ft.Tab)] == [
        "Übung",
        "Parameter",
        "Uhr",
        "Sensor",
        "Material",
    ]
    assert "PARAMETER" in _texte(_seite(ansicht, er.PARAMETER))
    assert "UHR" in _texte(_seite(ansicht, er.UHR))
    assert "BESCHLEUNIGUNGSSENSOR" in _texte(_seite(ansicht, er.SENSOR))
    assert "NUR IN DIESEM PLAN" in _texte(_seite(ansicht, er.MATERIAL))
    assert _daten(_seite(ansicht, er.SENSOR), "bewegungstyp").value == ""
