"""Einstellungen als Menü (Ben, 11.11.2026): Die Hauptseite zeigt nur Menüzeilen, jede führt
auf eine Seite, und jede frühere Einstellung ist über die neue Ordnung erreichbar — mit
demselben Schlüssel. Dazu das Geräte-Backup (Sicherheitsdurchsicht S4; Ben, 20.10.2026):
Vorgabe aus, der Schalter schreibt die Marke, die der BackupAgent liest; GPS-Strecken
gesondert; in der Praxis-Edition gibt es die Karte nicht. Nur mit flet."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.sicherung import MARKE  # noqa: E402
from trainingsapp.data.repositories import SettingRepo  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.einstellungen import MENUE, einstellungen  # noqa: E402
from trainingsapp.ui.views.einstellungen_darstellung import (  # noqa: E402
    einstellungen_darstellung,
)
from trainingsapp.ui.views.einstellungen_seiten import (  # noqa: E402
    einstellungen_daten,
    einstellungen_hilfe,
    einstellungen_uebungen,
    einstellungen_uhr,
)


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/einstellungen", views=[], platform=None, dialoge=[], aufgaben=[])
    p.update = lambda: None
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: None
    p.run_task = lambda f, *a: p.aufgaben.append((f, a))
    return p


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls", "trailing", "leading", "appbar", "title", "subtitle"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def _von(ansicht, art) -> list:
    return [c for v in ansicht.controls for c in alle(v) if isinstance(c, art)]


def _schalter(ansicht) -> dict[str, ft.Switch]:
    return {s.label: s for s in _von(ansicht, ft.Switch)}


def _ziele(ansicht) -> list[str]:
    """Wohin die Menüzeilen einer Seite führen (`menuezeile` legt die Route in ``data``)."""
    return [z.data for z in _von(ansicht, ft.ListTile) if str(z.data or "").startswith("/")]


def _umlegen(schalter: ft.Switch, wert: bool) -> None:
    schalter.on_change(SimpleNamespace(control=SimpleNamespace(value=wert)))


# -- Die Hauptseite ist nur noch das Menü ----------------------------------------------------


def test_hauptseite_zeigt_nur_menuezeilen(page, state, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_EDITION", "solo")
    ansicht = einstellungen(page, state, SimpleNamespace())
    assert ansicht.route == "/einstellungen"
    # nichts Einstellbares mehr direkt auf der Seite
    for art in (ft.Switch, ft.Dropdown, ft.TextField, ft.SegmentedButton, ft.Checkbox):
        assert _von(ansicht, art) == [], art
    zeilen = _von(ansicht, ft.ListTile)
    assert [z.data for z in zeilen] == [z.route for z in MENUE]
    assert len({z.route for z in MENUE}) == len(MENUE)
    for zeile in zeilen:
        # Symbol, Titel, eine Zeile mit dem Wichtigsten, Pfeil
        assert isinstance(zeile.leading, ft.Icon) and zeile.title.value
        assert zeile.subtitle.value and zeile.subtitle.max_lines == 1
        assert zeile.trailing.icon == ft.Icons.CHEVRON_RIGHT


def test_untertitel_nennen_den_stand(page, state, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_EDITION", "solo")
    state.fokus_auto_setzen(False)

    def text() -> dict[str, str]:
        zeilen = _von(einstellungen(page, state, SimpleNamespace()), ft.ListTile)
        return {z.title.value: z.subtitle.value for z in zeilen}

    stand = text()
    assert stand["Profil"].startswith(state.profil.name) and "1 Profil" in stand["Profil"]
    assert stand["Darstellung"].startswith("Petrol · System")
    assert "Fokus aus" in stand["Übungen"]
    assert "Geräte-Backup aus" in stand["Daten und Sicherung"]
    state.fokus_auto_setzen(True)
    assert "Fokus an" in text()["Übungen"]


def test_praxis_edition_ohne_updates_und_backup(page, state, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_EDITION", "praxis")
    ansicht = einstellungen(page, state, SimpleNamespace())
    titel = [z.title.value for z in _von(ansicht, ft.ListTile)]
    assert "Updates" not in titel and "Profil" in titel
    assert "Mit dem Gerät sichern" not in _schalter(einstellungen_daten(page, state))


# -- Jede frühere Einstellung ist erreichbar -------------------------------------------------


def test_uebungen_offener_eintrag_fokus_einteilung(page, state) -> None:
    ansicht = einstellungen_uebungen(page, state)
    assert ansicht.route == "/einstellungen/uebungen"
    (offen,) = _von(ansicht, ft.Dropdown)
    assert offen.label == "Eintrag bleibt offen"
    offen.on_select(SimpleNamespace(control=SimpleNamespace(value="60")))
    assert state.eintrag_offen_min() == 60

    fokus = _schalter(ansicht)["▶ öffnet den Fokus"]
    assert fokus.value is state.fokus_auto()
    _umlegen(fokus, not fokus.value)
    assert state.fokus_auto() is (not fokus.value)
    assert _ziele(ansicht) == ["/einstellungen/tags"]
    # Erklärungen stehen im „i“, nicht als graue Absätze
    assert len(_von(ansicht, ft.IconButton)) == 2


def test_timer_und_takt_schnellzeiten_vibration_verweise(page, state) -> None:
    ansicht = einstellungen_uhr(page, state)
    assert ansicht.route == "/einstellungen/uhr"
    assert _ziele(ansicht) == [
        "/einstellungen/uhr/timer",
        "/einstellungen/uhr/timer/alle",
        "/einstellungen/uhr/timer/signale",
    ]
    (feld,) = _von(ansicht, ft.TextField)
    assert feld.label == "Schnellzeiten"
    feld.value = "45 s, 2 min"
    ereignis = SimpleNamespace(control=feld)
    feld.on_blur(ereignis)
    assert state.schnellzeiten() == (45, 120)

    vibration = _schalter(ansicht)["Vibration am Phasenwechsel"]
    _umlegen(vibration, False)
    assert state.takt_vibration() is False


def test_schnellzeiten_tippfehler_behaelt_die_eigene_liste(page, state) -> None:
    """Review 11.11.2026: Unlesbares ersetzte die eigene Liste still durch die Vorgabe."""
    state.schnellzeiten_setzen("45 s, 2 min")
    (feld,) = _von(einstellungen_uhr(page, state), ft.TextField)
    feld.value = "45 s, abc"
    feld.on_blur(SimpleNamespace(control=feld))
    assert feld.error and state.schnellzeiten() == (45, 120)
    feld.value = "20 s, 3 min"
    feld.on_blur(SimpleNamespace(control=feld))
    assert not feld.error and state.schnellzeiten() == (20, 180)


def test_schnellzeiten_zurueck_speichert(page, state) -> None:
    """Zurück, ohne das Feld zu verlassen: das Getippte gilt (Ben, 16.10.2026)."""
    ansicht = einstellungen_uhr(page, state)
    page.views = [ft.View(route="/einstellungen"), ansicht]
    wege: list[str] = []

    async def push_route(route: str) -> None:
        wege.append(route)

    async def confirm_pop(_ok: bool) -> None:
        pass

    page.push_route = push_route
    ansicht.confirm_pop = confirm_pop
    assert ansicht.can_pop is False
    (feld,) = _von(ansicht, ft.TextField)
    feld.value = "20 s, 3 min"
    asyncio.run(ansicht.on_confirm_pop(None))
    assert state.schnellzeiten() == (20, 180)
    assert wege == ["/einstellungen"]


def test_darstellung_hat_alle_paletten_und_schalter(page, state) -> None:
    from trainingsapp.core.darstellung import BERNSTEIN, PALETTEN

    ansicht = einstellungen_darstellung(page, state)
    assert ansicht.route == "/einstellungen/darstellung"
    assert len(_von(ansicht, ft.SegmentedButton)) == 1
    assert "Farbverlauf im Hintergrund" in _schalter(ansicht)
    namen = [t.value for t in _von(ansicht, ft.Text)]
    for palette in PALETTEN.values():
        assert palette.name in namen
    kachel = next(
        c
        for c in _von(ansicht, ft.Container)
        if c.on_click is not None and any(getattr(t, "value", None) == "Bernstein" for t in alle(c))
    )
    kachel.on_click()
    assert state.darstellung().palette == BERNSTEIN


def test_daten_papierkorb_und_archiv(page, state, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_EDITION", "solo")
    ansicht = einstellungen_daten(page, state)
    assert ansicht.route == "/einstellungen/daten"
    assert _ziele(ansicht) == ["/papierkorb", "/archiv"]
    schalter = next(s for name, s in _schalter(ansicht).items() if name.startswith("Papierkorb"))
    assert schalter.value is True  # Vorgabe wie auf der Papierkorb-Seite
    _umlegen(schalter, False)
    assert state.einstellungen.lesen(SettingRepo.PAPIERKORB_AUTO, "1") == "0"


def test_hilfe_zeigt_themen_und_version(page, state) -> None:
    from trainingsapp.ui.components.hilfe import THEMEN

    ansicht = einstellungen_hilfe(page, state)
    assert ansicht.route == "/einstellungen/hilfe"
    themen = [z.data for z in _von(ansicht, ft.ListTile) if z.data]
    # die drei Zeilen der alten Hauptseite sind dabei
    assert {"notation", "uebungen", "atmung"} <= set(themen)
    assert all(t in THEMEN for t in themen)
    next(z for z in _von(ansicht, ft.ListTile) if z.data == "atmung").on_click()
    assert isinstance(page.dialoge[-1], ft.AlertDialog)
    texte = [t.value for t in _von(ansicht, ft.Text)]
    assert any(str(t).startswith("Version ") for t in texte)
    assert any(str(t).startswith("Edition ") for t in texte)


def test_profil_waehlen_auf_der_profilseite(page, state) -> None:
    """Die Wahl des aktiven Profils lag auf der Hauptseite — jetzt der Kreis vor dem Namen."""
    from trainingsapp.ui.views.profile import profile_view

    erstes = state.profil.id
    state.profil_anlegen("Gast")
    assert state.profil.id != erstes
    ansicht = profile_view(page, state)
    kreise = {
        k.data: k
        for k in _von(ansicht, ft.IconButton)
        if k.icon in (ft.Icons.RADIO_BUTTON_CHECKED, ft.Icons.RADIO_BUTTON_UNCHECKED)
    }
    assert len(kreise) == 2
    assert kreise[state.profil.id].icon == ft.Icons.RADIO_BUTTON_CHECKED
    kreise[erstes].on_click()
    assert state.profil.id == erstes


def test_training_fuehrt_zum_gps_test(page, state) -> None:
    from trainingsapp.ui.views.einstellungen_training import einstellungen_training

    assert _ziele(einstellungen_training(page, state)) == ["/einstellungen/gps-test"]


# -- Routen: jede Zeile öffnet ihre Seite, Zurück führt dorthin, woher man kam ---------------


@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    from test_ui_navigation import Seite

    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRAININGSAPP_EDITION", "solo")
    from trainingsapp.ui import app

    gestartet: list[AppState] = []
    original = AppState.starten

    def starten(*a, **k):
        s = original(*a, **k)
        gestartet.append(s)
        return s

    monkeypatch.setattr(AppState, "starten", staticmethod(starten))
    seite = Seite("/")
    app.main(seite)
    yield seite
    for s in gestartet:
        s.schliessen()


def test_jede_menuezeile_oeffnet_ihre_seite(umgebung) -> None:
    seite = umgebung
    seite.gehe("/einstellungen")
    for zeile in MENUE:
        seite.gehe(zeile.route)
        assert seite.routen() == ["/", "/einstellungen", zeile.route], zeile.titel
        seite.zurueck()
        assert seite.routen() == ["/", "/einstellungen"], zeile.titel


def test_verweise_der_unterseiten_und_zurueck(umgebung) -> None:
    """Von einer Seite der Einstellungen in die nächste — Zurück führt zur Seite, nicht zum
    Menü (die Seiten sind keine Geschwister, `navigation.geschwister`)."""
    seite = umgebung
    seite.gehe("/einstellungen")
    for von, nach in (
        ("/einstellungen/uebungen", "/einstellungen/tags"),
        ("/einstellungen/uhr", "/einstellungen/uhr/timer"),
        ("/einstellungen/uhr", "/einstellungen/uhr/timer/alle"),
        ("/einstellungen/uhr", "/einstellungen/uhr/timer/signale"),
        ("/einstellungen/training", "/einstellungen/gps-test"),
        ("/einstellungen/daten", "/papierkorb"),
        ("/einstellungen/daten", "/archiv"),
        ("/einstellungen/hrv", "/einstellungen/hrv/ueberschriften"),
    ):
        seite.gehe(von)
        seite.gehe(nach)
        assert seite.routen() == ["/", "/einstellungen", von, nach], nach
        seite.zurueck()
        assert seite.routen() == ["/", "/einstellungen", von], nach
        seite.zurueck()
        assert seite.routen() == ["/", "/einstellungen"]


def test_alte_routen_gelten_weiter(umgebung) -> None:
    """Verweise aus anderen Ansichten und gemerkte Routen bleiben gültig."""
    seite = umgebung
    for route in (
        "/einstellungen/timer",
        "/einstellungen/timer/alle",
        "/einstellungen/tags",
        "/einstellungen/gps-test",
        "/einstellungen/profile",
        "/einstellungen/tagesfelder/neu",
    ):
        seite.gehe("/")
        seite.gehe(route)
        assert seite.routen() == ["/", route], route


# -- Geräte-Backup (S4) ----------------------------------------------------------------------


def test_geraete_backup_vorgabe_aus_schalter_schreibt_die_marke(page, state, tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_EDITION", "solo")
    schalter = _schalter(einstellungen_daten(page, state))
    assert schalter["Mit dem Gerät sichern"].value is False
    assert "GPS-Strecken einschließen" not in schalter  # erst sichtbar, wenn an
    assert not (tmp_path / MARKE).exists()

    _umlegen(schalter["Mit dem Gerät sichern"], True)
    assert (tmp_path / MARKE).read_text(encoding="utf-8") == "an\n"
    schalter = _schalter(einstellungen_daten(page, state))
    assert schalter["Mit dem Gerät sichern"].value is True
    assert schalter["GPS-Strecken einschließen"].value is False

    _umlegen(schalter["GPS-Strecken einschließen"], True)
    assert (tmp_path / MARKE).read_text(encoding="utf-8") == "an\nstrecken\n"
    assert state.sicherung().strecken

    _umlegen(schalter["Mit dem Gerät sichern"], False)
    assert not (tmp_path / MARKE).exists()  # aus = keine Marke, der Agent sichert nichts


def test_praxis_edition_ohne_geraete_backup(page, state, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_EDITION", "praxis")
    assert "Mit dem Gerät sichern" not in _schalter(einstellungen_daten(page, state))
