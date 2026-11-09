"""Das App-Update in der App laden und installieren (`ui/app_update.py`, A8 Stufe 2;
Ben, 9.11.2026). Nur mit flet — die Erweiterung ist eine Attrappe."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.laufend import Laufend  # noqa: E402
from trainingsapp.core.update import Release, UpdateFehler  # noqa: E402
from trainingsapp.ui import app_update  # noqa: E402
from trainingsapp.ui.app_update import (  # noqa: E402
    BEREIT,
    ERLAUBEN,
    FEHLER,
    GELADEN,
    INSTALLIEREN,
    LADEN,
    UpdateLauf,
)

RELEASE = Release("0.3.71", 386, "v0.3.71", "https://github.com/x", "s", "", "")


class Dienst:
    """Attrappe von `flet_installieren.FletInstallieren`."""

    def __init__(self, *, darf: bool = True, pruefung: dict | None = None) -> None:
        self.darf = darf
        self.pruefung = pruefung or {
            "eigenes_paket": True,
            "gleiche_signatur": True,
            "version_code": 386,
            "eigener_code": 385,
        }
        self.installiert: list[str] = []
        self.erlaubt = 0

    async def pruefen(self, pfad: str) -> dict[str, Any]:
        return self.pruefung

    async def stand(self) -> dict[str, Any]:
        return {"darf": self.darf, "still": True}

    async def erlauben(self) -> bool:
        self.erlaubt += 1
        return True

    async def installieren(self, pfad: str) -> int:
        self.installiert.append(pfad)
        return 7


@pytest.fixture
def state():
    return SimpleNamespace(
        installieren=Dienst(),
        app_update=None,
        app_update_beobachter=None,
        vor_dem_verlassen={},
        messlauf=None,
        einheit=None,
        gps_test=None,
        timer=None,
    )


@pytest.fixture
def geladen(monkeypatch, tmp_path: Path) -> list[Path]:
    """`apk_laden` schreibt eine Datei statt zu laden; die Liste sammelt die Ziele."""
    ziele: list[Path] = []

    def laden(release, ordner, fortschritt=None, *, abbrechen=None, oeffnen=None):
        ordner.mkdir(parents=True, exist_ok=True)
        pfad = ordner / "trainingsapp-0.3.71-386.apk"
        pfad.write_bytes(b"apk")
        if fortschritt is not None:
            fortschritt(3, 3)
        ziele.append(pfad)
        return pfad

    monkeypatch.setattr(app_update, "apk_laden", laden)
    monkeypatch.setattr(app_update, "updateverzeichnis", lambda: tmp_path / "Updates")
    return ziele


def test_laden_pruefen_installieren(state, geladen) -> None:
    gesichert: list[str] = []
    state.vor_dem_verlassen["notiz"] = lambda: gesichert.append("notiz")
    lauf = app_update.lauf_fuer(state, RELEASE)
    asyncio.run(app_update.laden_und_installieren(state, lauf))
    assert lauf.phase == INSTALLIEREN
    assert state.installieren.installiert == [str(geladen[0])]
    assert gesichert == ["notiz"]  # vor dem Installieren gesichert
    assert "schließt sich" in lauf.meldung


def test_ohne_erlaubnis_erst_einstellung_dann_von_selbst_weiter(state, geladen) -> None:
    state.installieren.darf = False
    lauf = app_update.lauf_fuer(state, RELEASE)
    asyncio.run(app_update.laden_und_installieren(state, lauf))
    assert lauf.phase == ERLAUBEN
    assert state.installieren.installiert == []
    asyncio.run(app_update.erlauben(state))
    assert state.installieren.erlaubt == 1
    # Zurück in der App, erlaubt: geht von selbst weiter — ohne neu zu laden
    state.installieren.darf = True
    asyncio.run(app_update.weiter_nach_erlauben(state))
    assert lauf.phase == INSTALLIEREN
    assert len(geladen) == 1


def test_waehrend_einer_messung_nur_laden(state, geladen, monkeypatch) -> None:
    monkeypatch.setattr(
        app_update, "laufendes", lambda s: [Laufend("HRV-Messung", "Aufnahme 1:00", "HRV")]
    )
    lauf = app_update.lauf_fuer(state, RELEASE)
    asyncio.run(app_update.laden_und_installieren(state, lauf))
    assert lauf.phase == GELADEN
    assert "HRV-Messung" in lauf.meldung
    assert state.installieren.installiert == []
    # Nach der Messung: „Installieren“ nimmt die geladene Datei
    monkeypatch.setattr(app_update, "laufendes", lambda s: [])
    asyncio.run(app_update.installieren(state, lauf))
    assert lauf.phase == INSTALLIEREN
    assert len(geladen) == 1


def test_fremde_apk_wird_verworfen(state, geladen) -> None:
    state.installieren.pruefung = {"eigenes_paket": True, "gleiche_signatur": False}
    lauf = app_update.lauf_fuer(state, RELEASE)
    asyncio.run(app_update.laden_und_installieren(state, lauf))
    assert lauf.phase == FEHLER
    assert "Schlüssel" in lauf.meldung
    assert not geladen[0].exists()
    assert state.installieren.installiert == []


def test_ladefehler(state, monkeypatch, tmp_path) -> None:
    def kaputt(*a, **k):
        raise UpdateFehler("HTTP 404")

    monkeypatch.setattr(app_update, "apk_laden", kaputt)
    monkeypatch.setattr(app_update, "updateverzeichnis", lambda: tmp_path)
    lauf = app_update.lauf_fuer(state, RELEASE)
    asyncio.run(app_update.laden_und_installieren(state, lauf))
    assert (lauf.phase, lauf.meldung) == (FEHLER, "Nicht geladen: HTTP 404")


def test_ergebnis_von_android(state) -> None:
    lauf = app_update.lauf_fuer(state, RELEASE)
    lauf.phase = INSTALLIEREN
    app_update.ergebnis(state, -1, None)
    assert lauf.phase == INSTALLIEREN and "Dialog" in lauf.meldung
    app_update.ergebnis(state, 3, "INSTALL_FAILED_ABORTED")
    assert lauf.phase == GELADEN  # abgelehnt: „Installieren“ steht wieder da
    app_update.ergebnis(state, 5, "INSTALL_FAILED_UPDATE_INCOMPATIBLE")
    assert lauf.phase == FEHLER and "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in lauf.meldung


def test_lauf_bleibt_fuer_dasselbe_release(state) -> None:
    lauf = app_update.lauf_fuer(state, RELEASE)
    lauf.phase = GELADEN
    assert app_update.lauf_fuer(state, RELEASE) is lauf
    neuer = Release("0.3.72", 390, "v0.3.72", "u", "s", "", "")
    assert app_update.lauf_fuer(state, neuer).phase == BEREIT


def _texte(wurzel: Any) -> list[str]:
    gefunden: list[str] = []

    def gehen(c: Any) -> None:
        if isinstance(c, ft.Text) and isinstance(c.value, str):
            gefunden.append(c.value)
        knopf = ft.FilledButton | ft.FilledTonalButton | ft.TextButton
        if isinstance(c, knopf) and isinstance(c.content, str):
            gefunden.append(c.content)
        for name in ("content", "controls"):
            kind = getattr(c, name, None)
            for k in kind if isinstance(kind, list) else [kind]:
                if isinstance(k, ft.BaseControl):
                    gehen(k)

    gehen(wurzel)
    return gefunden


@pytest.mark.parametrize(
    ("phase", "erwartet"),
    [
        (BEREIT, "Laden und installieren"),
        (LADEN, "Abbrechen"),
        (GELADEN, "Installieren"),
        (ERLAUBEN, "Erlauben"),
        (INSTALLIEREN, "gleich"),
        (FEHLER, "Noch einmal"),
    ],
)
def test_bereich_zeigt_je_phase_das_passende(state, phase, erwartet) -> None:
    lauf = app_update.lauf_fuer(state, RELEASE)
    lauf.phase, lauf.meldung, lauf.geladen, lauf.gesamt = phase, "Geht gleich", 30e6, 90e6

    async def browser() -> None:
        return None

    spalte = app_update.app_bereich(state, RELEASE, browser)
    assert any(erwartet in t for t in _texte(spalte)), _texte(spalte)
    assert state.app_update_beobachter is not None
    # Der Beobachter zeichnet neu, auch ohne Seite
    lauf.phase = FEHLER
    state.app_update_beobachter()
    assert "Noch einmal" in _texte(spalte)


def test_updates_seite_bietet_installieren_auf_android(tmp_path) -> None:
    from trainingsapp.ui.state import AppState, UpdateStand
    from trainingsapp.ui.views import updates

    s = AppState.starten(tmp_path / "app.db")
    try:
        s.installieren = Dienst()
        s.paketquellen_setzen([])
        stand = UpdateStand(updates.Pruefung())
        stand.app = RELEASE
        s.updates = stand
        page = SimpleNamespace(
            route="/", views=[], platform=ft.PagePlatform.ANDROID, web=False, update=lambda: None
        )
        ansicht = updates.updates_view(page, s, ft.UrlLauncher())
        texte = [t for c in ansicht.controls for t in _texte(c)]
        assert "Laden und installieren" in texte
        assert "Im Browser laden" in texte
        # Ohne Erweiterung (flet run, Web): wie bisher über den Browser
        s.installieren = None
        ansicht = updates.updates_view(page, s, ft.UrlLauncher())
        texte = [t for c in ansicht.controls for t in _texte(c)]
        assert "Herunterladen" in texte and "Laden und installieren" not in texte
    finally:
        s.schliessen()


def test_lauf_ist_ein_datensatz() -> None:
    lauf = UpdateLauf(RELEASE)
    assert (lauf.phase, lauf.pfad, lauf.abbrechen) == (BEREIT, None, False)
