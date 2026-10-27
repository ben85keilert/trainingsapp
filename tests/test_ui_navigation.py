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


def _alle(c):
    yield c
    for name in ("content", "controls", "appbar", "title", "leading"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


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


def test_aufnahmen_zum_tag_und_audio_liegen_ueber_der_ansicht(umgebung) -> None:
    """Ben, 22.10.2026: Foto, Video und Audio auch zur Notiz zum Tag — der Weg trägt
    ``tag/<datum>`` statt einer Eintrags-ID; ein Tag in der Zukunft fällt aus dem Weg."""
    from datetime import timedelta

    from trainingsapp.ui.views.anhang_ton import anhang_ton_view

    seite, state = umgebung()
    heute = state.heute()
    audio = f"/anhang/aufnehmen/tag/{heute.isoformat()}/audio"
    seite.gehe(audio)
    assert seite.routen() == ["/", audio]
    assert seite.views[-1].can_pop is False  # die Systemtaste räumt den Rekorder auf
    assert any(
        isinstance(c, ft.IconButton) and c.icon == ft.Icons.FIBER_MANUAL_RECORD
        for c in _alle(seite.views[-1])
    )
    # Über einem anderen Tag (Kaltstart baut den Weg hierarchisch)
    gestern = (heute - timedelta(days=1)).isoformat()
    foto = f"/tag/{gestern}/anhang/aufnehmen/tag/{gestern}/foto"
    neu, _ = umgebung(foto)
    assert neu.routen() == ["/", f"/tag/{gestern}", foto]
    morgen = f"/anhang/aufnehmen/tag/{(heute + timedelta(days=1)).isoformat()}/audio"
    zukunft, _ = umgebung(morgen)
    assert zukunft.routen() == ["/"]
    assert anhang_ton_view.__name__  # die Seite gibt es (Import im Router)


def test_zurueck_auf_heute_beendet_das_schreiben(umgebung) -> None:
    """Zurück macht Autosave: Wer auf „Heute“ die Notiz zum Tag schreibt, beendet mit der
    Systemtaste das Schreiben — gespeichert ist schon; ein neuer Aufbau speichert ebenso."""
    seite, state = umgebung()
    haupt = seite.views[0]
    antworten: list[bool] = []

    async def confirm_pop(soll: bool) -> None:
        antworten.append(soll)

    haupt.confirm_pop = confirm_pop
    beendet: list[bool] = []

    async def schreiben_beenden() -> None:
        beendet.append(True)
        state.schreiben_beenden = None

    state.schreiben_beenden = schreiben_beenden
    asyncio.run(haupt.on_confirm_pop(None))
    assert antworten == [False] and beendet == [True] and state.reiter == "heute"
    gespeichert: list[str] = []
    state.vor_dem_verlassen["test"] = lambda: gespeichert.append("ja")
    seite.gehe("/tag/2026-10-17")
    assert gespeichert == ["ja"] and state.vor_dem_verlassen == {}


def test_uebungsseite_behaelt_die_leiste_unten(umgebung) -> None:
    """Ben, 27.10.2026: zwischen Übung und Messung hin und her — die Leiste unten bleibt
    auf Plan, Einzelübung, Timer und Ablauf; ein Tipp führt in diesen Reiter der
    Hauptansicht, die Scrollposition der Übungsseite bleibt für die Rückkehr."""
    from types import SimpleNamespace

    seite, state = umgebung()
    plan = _plan(state)
    seite.gehe(f"/plan/{plan.id}")
    leiste = seite.views[-1].navigation_bar
    assert leiste is not None
    assert leiste.destinations[0].label == "Heute"
    assert leiste.selected_index == 0  # darunter liegt „Heute“
    state.scroll_offsets[f"/plan/{plan.id}"] = 640.0
    messung = [d.label for d in leiste.destinations].index("Messung")
    leiste.selected_index = messung  # der Client setzt den Index, dann kommt das Ereignis
    asyncio.run(leiste.on_change(SimpleNamespace(control=leiste)))
    assert seite.routen() == ["/"]
    assert state.reiter == "messung"
    assert seite.views[0].navigation_bar.selected_index == messung
    assert state.scroll_offsets[f"/plan/{plan.id}"] == 640.0  # kein Zurück — bleibt
    # Zurück zur Übung: die Seite steht wieder an ihrer Stelle, mit Leiste
    seite.gehe(f"/plan/{plan.id}")
    assert seite.views[-1].navigation_bar is not None
    for route in (f"/plan/{plan.id}/timer", f"/plan/{plan.id}/timer/ablauf"):
        seite.gehe(route)
        assert seite.views[-1].navigation_bar is not None, route
    # Formulare darunter nicht — dort gilt „Zurück speichert“
    seite.gehe(f"/plan/{plan.id}/bearbeiten")
    assert seite.views[-1].navigation_bar is None
    seite.gehe("/")
    seite.gehe(f"/uebung/{seed_id('kniebeuge')}")
    assert seite.views[-1].navigation_bar is None


def test_reiter_merken_ihre_scrollposition(umgebung) -> None:
    """Ben, 27.10.2026: „Schaue ich mir die Kurve an, gehe weg, komme wieder, möchte ich
    nicht immer wieder runter scrollen müssen“ — jeder Reiter unten (und die Unterreiter
    von Messung und Übungen) hängt an `scroll_merken`."""
    from types import SimpleNamespace

    seite, state = umgebung()
    erwartet = {
        ("messung", 0): "messung_live",
        ("messung", 1): "messung_gps",
        ("uebungen", 0): "uebungen_katalog",
        ("verlauf", 0): "verlauf_tage",
        ("heute", 0): "heute",
    }
    for (reiter, unterreiter), schluessel in erwartet.items():
        state.reiter = reiter
        state.messung_tab = unterreiter
        state.aufzeichnungen_tab = 0
        seite.gehe("/")
        flaechen = [x for x in _alle(seite.views[0]) if getattr(x, "on_scroll", None)]
        assert flaechen, (reiter, unterreiter)
        flaechen[0].on_scroll(SimpleNamespace(pixels=333.0))
        assert state.scroll_offsets[schluessel] == 333.0, (reiter, unterreiter)


def test_heute_haelt_die_uebungsseite_bis_zurueck(umgebung) -> None:
    """Ben, 27.10.2026: „Man startet eine Übung, die zieht dann einfach zu Heute um als
    oberste View … bis man zurück geht.“ Über die Leiste verlassen → „Heute“ (Leiste oder
    Zurück auf einem anderen Reiter) öffnet die Seite wieder; Zurück auf ihr gibt sie frei."""
    from types import SimpleNamespace

    seite, state = umgebung()
    plan = _plan(state)
    route = f"/plan/{plan.id}"
    seite.gehe(route)
    leiste = seite.views[-1].navigation_bar
    labels = [d.label for d in leiste.destinations]
    leiste.selected_index = labels.index("Messung")
    asyncio.run(leiste.on_change(SimpleNamespace(control=leiste)))
    assert seite.routen() == ["/"] and state.heute_haelt == route
    # „Heute“ in der Hauptansicht: die gehaltene Seite, mit „Heute“ markiert
    haupt = seite.views[0].navigation_bar
    haupt.selected_index = labels.index("Heute")
    asyncio.run(haupt.on_change(SimpleNamespace(control=haupt)))
    assert seite.routen() == ["/", route]
    assert seite.views[-1].navigation_bar.selected_index == labels.index("Heute")
    # „Heute“ auf der gehaltenen Seite: bleiben
    leiste = seite.views[-1].navigation_bar
    asyncio.run(leiste.on_change(SimpleNamespace(control=leiste)))
    assert seite.routen() == ["/", route]
    # Zurück auf einem anderen Reiter (Startseite) führt auch zur gehaltenen Seite
    seite.gehe("/")
    state.reiter = "verlauf"
    haupt = seite.views[0]

    async def confirm_pop(_soll: bool) -> None:
        pass

    haupt.confirm_pop = confirm_pop
    asyncio.run(haupt.on_confirm_pop(None))
    assert seite.routen() == ["/", route] and state.reiter == "heute"
    # Zurück auf der Seite gibt sie frei — „Heute“ ist wieder der Tag
    seite.zurueck()
    assert seite.routen() == ["/"] and state.heute_haelt is None
    haupt = seite.views[0].navigation_bar
    haupt.selected_index = labels.index("Heute")
    asyncio.run(haupt.on_change(SimpleNamespace(control=haupt)))
    assert seite.routen() == ["/"]
    # Gehaltene Seite verschwindet (Plan gelöscht): „Heute“ ist der Tag, nichts hängt
    seite.gehe(route)
    leiste = seite.views[-1].navigation_bar
    leiste.selected_index = labels.index("Messung")
    asyncio.run(leiste.on_change(SimpleNamespace(control=leiste)))
    state.plaene.loeschen(plan.id)
    haupt = seite.views[0].navigation_bar
    haupt.selected_index = labels.index("Heute")
    asyncio.run(haupt.on_change(SimpleNamespace(control=haupt)))
    assert seite.routen() == ["/"] and state.heute_haelt is None
