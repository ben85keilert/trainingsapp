"""Der Ansichtsstapel folgt dem Weg (Ben, 18.10.2026) — `app.main` mit einer nachgebauten Seite.

Die Seite hier tut, was der Flet-Client tut: ``push_route`` setzt die Route und meldet den
Wechsel, die Systemtaste ruft ``on_view_pop`` (über der Hauptansicht) bzw. fragt die
Hauptansicht (``on_confirm_pop``). Geprüft wird, welche Ansichten danach im Stapel liegen.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Plan  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402


class Seite:
    """Gerade so viel `ft.Page`, wie `app.main` braucht — ohne Client."""

    def __init__(self, route: str = "/") -> None:
        self.route = route
        self.views: list[ft.View] = []
        self.services: list = []
        self.dialoge: list = []
        self.platform = ft.PagePlatform.LINUX
        self.platform_brightness = ft.Brightness.LIGHT
        self.title = ""
        self.padding = 0
        self.theme = self.dark_theme = self.theme_mode = None
        self.bgcolor = None
        self.on_route_change = self.on_view_pop = None
        self.on_platform_brightness_change = self.on_resize = None
        self.on_app_lifecycle_state_change = None

    def update(self) -> None:
        pass

    def run_task(self, *_a, **_k) -> None:
        pass

    def show_dialog(self, dialog) -> None:
        self.dialoge.append(dialog)

    def pop_dialog(self) -> None:
        pass

    async def push_route(self, route: str) -> None:
        self.route = route
        self.on_route_change()

    def zurueck(self) -> None:
        """Die Systemtaste über der Hauptansicht (Flet: ``view_pop``)."""
        asyncio.run(self.on_view_pop())

    def gehe(self, route: str) -> None:
        asyncio.run(self.push_route(route))

    def routen(self) -> list[str]:
        return [str(v.route) for v in self.views]


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    from trainingsapp.ui import app
    from trainingsapp.ui.state import AppState

    gestartet: list[AppState] = []
    original = AppState.starten

    def starten(*a, **k):
        s = original(*a, **k)
        gestartet.append(s)
        return s

    monkeypatch.setattr(AppState, "starten", staticmethod(starten))

    def oeffnen(route: str = "/") -> tuple[Seite, AppState]:
        seite = Seite(route)
        app.main(seite)
        return seite, gestartet[-1]

    yield oeffnen
    for s in gestartet:
        s.schliessen()


def _plan(state) -> Plan:
    plan = Plan(name="Kräftigung kurz", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    for key in ("liegestuetzen", "kniebeuge"):
        state.plaene.uebung_hinzufuegen(plan.id, seed_id(key))
    geladen = state.plaene.laden(plan.id)
    assert geladen is not None
    return geladen


def test_verlauf_uebung_tag_zurueck_fuehrt_zur_uebung(umgebung) -> None:
    """Bens Beispiel: Verlauf → Übung → Tag → zurück → die Übung (bisher: „Heute“)."""
    seite, _ = umgebung()
    kachel = f"/verlauf/{seed_id('kniebeuge')}"
    seite.gehe(kachel)
    seite.gehe("/tag/2026-10-17")
    assert seite.routen() == ["/", kachel, "/tag/2026-10-17"]
    seite.zurueck()
    assert seite.routen() == ["/", kachel] and seite.route == kachel
    seite.zurueck()
    assert seite.routen() == ["/"]


def test_start_auf_heute_oeffnet_den_ablauf_mit_einem_zurueck(umgebung) -> None:
    seite, state = umgebung()
    plan = _plan(state)
    ablauf = f"/plan/{plan.id}/timer/ablauf"
    seite.gehe(ablauf)
    assert seite.routen() == ["/", ablauf]  # kein Plan, kein Timer dazwischen
    seite.zurueck()
    assert seite.routen() == ["/"]
    # Über Plan und Timer geht es denselben Weg zurück
    seite.gehe(f"/plan/{plan.id}")
    seite.gehe(f"/plan/{plan.id}/timer")
    seite.gehe(ablauf)
    assert seite.routen() == ["/", f"/plan/{plan.id}", f"/plan/{plan.id}/timer", ablauf]


def test_kaltstart_auf_tiefer_route_baut_hierarchisch(umgebung) -> None:
    """Start (oder Neuladen im Browser) mitten im Plan: Zurück geht trotzdem."""
    _, state = umgebung()
    plan = _plan(state)
    neu, _ = umgebung(f"/plan/{plan.id}/timer")
    assert neu.routen() == ["/", f"/plan/{plan.id}", f"/plan/{plan.id}/timer"]
    neu.zurueck()
    assert neu.routen() == ["/", f"/plan/{plan.id}"]


def test_tage_blaettern_ersetzt_und_ersetzen_bei(umgebung) -> None:
    seite, state = umgebung()
    seite.gehe("/tag/2026-10-17")
    seite.gehe("/tag/2026-10-16")
    assert seite.routen() == ["/", "/tag/2026-10-16"]
    # „ersetzen“ gilt nur für genau die angekündigte Route
    state.ersetzen_bei = "/archiv"
    seite.gehe("/papierkorb")
    assert seite.routen() == ["/", "/tag/2026-10-16", "/papierkorb"]
    assert state.ersetzen_bei is None
    state.ersetzen_bei = "/archiv"
    seite.gehe("/archiv")
    assert seite.routen() == ["/", "/tag/2026-10-16", "/archiv"]


def test_unbekannte_route_faellt_aus_dem_weg(umgebung) -> None:
    seite, state = umgebung()
    plan = _plan(state)
    seite.gehe(f"/plan/{plan.id}")
    state.plaene.loeschen(plan.id)
    seite.gehe("/tag/2026-10-17")  # der Plan darunter ist weg
    assert seite.routen() == ["/", "/tag/2026-10-17"]
    assert state.navigation == ["/tag/2026-10-17"]


def test_zurueck_auf_der_startseite_minimiert_nicht(umgebung) -> None:
    """Ben, 18.10.2026: Die App bleibt offen — ein anderer Reiter geht zu „Heute“."""
    seite, state = umgebung()
    haupt = seite.views[0]
    assert haupt.can_pop is False
    antworten: list[bool] = []

    async def confirm_pop(soll: bool) -> None:
        antworten.append(soll)

    haupt.confirm_pop = confirm_pop
    state.reiter = "verlauf"
    asyncio.run(haupt.on_confirm_pop(None))
    assert antworten == [False] and state.reiter == "heute"
    asyncio.run(haupt.on_confirm_pop(None))  # auf „Heute“: nichts
    assert antworten == [False, False] and state.reiter == "heute"


def test_tag_ansicht_bleibt_an_ihrem_datum(umgebung) -> None:
    """Jede Ansicht trägt die Route, über die man sie erreichte — Zurück liest sie."""
    seite, _ = umgebung()
    seite.gehe(f"/tag/{date(2026, 10, 17).isoformat()}")
    seite.gehe(f"/tag/{date(2026, 10, 17).isoformat()}/leistungen/{seed_id('kniebeuge')}")
    assert seite.routen()[-2] == "/tag/2026-10-17"
    seite.zurueck()
    assert seite.routen() == ["/", "/tag/2026-10-17"]


def test_neue_uebung_timer_editor_zurueck_ins_formular(umgebung) -> None:
    """Durchsicht 18.10.: Aus dem Timer-Editor einer neuen Übung führt Zurück ins Formular
    der jetzt gespeicherten Übung — nicht an ihm vorbei auf die Startseite."""
    from trainingsapp.core.models import Exercise

    seite, state = umgebung()
    seite.gehe("/uebung/neu")
    neu = Exercise(name="Neu")
    state.uebungen.speichern(neu)
    formular = f"/uebung/{neu.id}/bearbeiten"
    # wie `uebung_bearbeiten.timer_editor` nach dem Speichern
    assert state.navigation[-1:] == ["/uebung/neu"]
    state.navigation[-1] = formular
    seite.gehe(f"{formular}/timer/profil")
    assert seite.routen() == ["/", formular, f"{formular}/timer/profil"]
    seite.zurueck()
    assert seite.routen() == ["/", formular]


def test_nur_der_vorfahr_baubar_faellt_aus_dem_weg(umgebung) -> None:
    """Eine Route, deren Blatt fehlt (Planübung gelöscht), stellt nicht den Plan ein
    zweites Mal auf den Stapel."""
    seite, state = umgebung()
    plan = _plan(state)
    seite.gehe(f"/plan/{plan.id}")
    seite.gehe(f"/plan/{plan.id}/info/gibt-es-nicht")
    assert seite.routen() == ["/", f"/plan/{plan.id}"]
    assert state.navigation == [f"/plan/{plan.id}"]
