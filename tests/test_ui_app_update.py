"""Das App-Update in der App laden und installieren (`ui/app_update.py`, A8 Stufe 2 und
Automatik; Ben, 9.11.2026). Nur mit flet — die Erweiterung ist eine Attrappe."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
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
    VORBEREITET,
    WARTEN_S,
    UpdateLauf,
)

RELEASE = Release("0.3.71", 386, "v0.3.71", "https://github.com/x", "s", "", "")


class Dienst:
    """Attrappe von `flet_installieren.FletInstallieren`."""

    def __init__(self, *, darf: bool = True, pruefung: dict | None = None) -> None:
        self.darf = darf
        self.still = True
        self.getaktet = False
        self.pruefung = pruefung or {
            "eigenes_paket": True,
            "gleiche_signatur": True,
            "version_code": 386,
            "eigener_code": 385,
        }
        self.installiert: list[str] = []
        self.erlaubt = 0
        self.vorbereitet = -1  # Nummer der vorbereiteten Sitzung (Automatik)
        self.abgeschickt = 0
        self.wecker: list[int | None] = []  # spaeter(s) → s, nicht_spaeter → None
        self.verworfen = 0
        self.benachrichtigung = 0

    async def pruefen(self, pfad: str) -> dict[str, Any]:
        return self.pruefung

    async def stand(self) -> dict[str, Any]:
        return {
            "darf": self.darf,
            "still": self.still,
            "getaktet": self.getaktet,
            "vorbereitet": self.vorbereitet,
        }

    async def erlauben(self) -> bool:
        self.erlaubt += 1
        return True

    async def installieren(self, pfad: str) -> int:
        self.installiert.append(pfad)
        return 7

    async def vorbereiten(self, pfad: str) -> dict[str, Any]:
        self.vorbereitet = 11
        return {"sitzung": 11, "version_code": 386, "version_name": "0.3.71"}

    async def abschicken(self) -> int:
        if self.vorbereitet < 0:
            raise RuntimeError("Keine vorbereitete Sitzung")
        self.abgeschickt += 1
        self.vorbereitet = -1
        return 11

    async def spaeter(self, sekunden: int) -> bool:
        self.wecker.append(sekunden)
        return self.vorbereitet >= 0

    async def nicht_spaeter(self) -> None:
        self.wecker.append(None)

    async def verwerfen(self) -> None:
        self.verworfen += 1
        self.vorbereitet = -1

    async def benachrichtigung_erlauben(self) -> bool:
        self.benachrichtigung += 1
        return True


class Zustand(SimpleNamespace):
    """Was `ui/app_update.py` vom `AppState` braucht — Einstellungen im Speicher."""

    def __init__(self) -> None:
        super().__init__(
            installieren=Dienst(),
            app_update=None,
            app_update_beobachter=None,
            vor_dem_verlassen={},
            messlauf=None,
            einheit=None,
            gps_test=None,
            timer=None,
            im_vordergrund=True,
            updates=None,
            auto=True,
            hinweis_gesehen=True,
            auslassen="",
        )

    def app_update_auto(self) -> bool:
        return self.auto

    def app_update_auto_setzen(self, an: bool) -> None:
        self.auto = an

    def app_update_hinweis_gesehen(self) -> bool:
        return self.hinweis_gesehen

    def app_update_hinweis_merken(self) -> None:
        self.hinweis_gesehen = True

    def app_update_auslassen(self) -> str:
        return self.auslassen

    def app_update_auslassen_setzen(self, tag: str) -> None:
        self.auslassen = tag


@pytest.fixture
def state() -> Zustand:
    return Zustand()


class Seite(SimpleNamespace):
    """Seite mit Ansichten und gezeigten Dialogen."""

    def __init__(self, *views: Any) -> None:
        super().__init__(views=list(views), dialoge=[])

    def show_dialog(self, d: Any) -> None:
        self.dialoge.append(d)


@pytest.fixture
def seite() -> Seite:
    return Seite(SimpleNamespace(route="/", can_pop=False))  # die Startseite hält Zurück an


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
        if isinstance(c, ft.Switch) and isinstance(c.label, str):
            gefunden.append(c.label)
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
        (VORBEREITET, "Jetzt installieren"),
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
        assert "Updates der App von selbst installieren" in texte  # der Schalter
        # Ohne Erweiterung (flet run, Web): wie bisher über den Browser, ohne Automatik
        s.installieren = None
        ansicht = updates.updates_view(page, s, ft.UrlLauncher())
        texte = [t for c in ansicht.controls for t in _texte(c)]
        assert "Herunterladen" in texte and "Laden und installieren" not in texte
        assert "Updates der App von selbst installieren" not in texte
    finally:
        s.schliessen()


def test_lauf_ist_ein_datensatz() -> None:
    lauf = UpdateLauf(RELEASE)
    assert (lauf.phase, lauf.pfad, lauf.abbrechen) == (BEREIT, None, False)


# -- Automatik ---------------------------------------------------------------------------


def _mit_release(state: Zustand, sha256: str | None = "ab" * 32) -> Zustand:
    """Die Automatik nimmt nur ein Release mit Prüfsumme von GitHub (S29)."""
    state.updates = SimpleNamespace(app=replace(RELEASE, apk_sha256=sha256))
    return state


def test_automatik_nie_ohne_pruefsumme(state, seite, geladen) -> None:
    """S29: Nennt GitHub keinen ``digest``, installiert sich nichts von selbst."""
    asyncio.run(app_update.automatisch(seite, _mit_release(state, sha256=None)))
    assert state.app_update is None and geladen == []


def test_automatik_laedt_und_bereitet_vor(state, seite, geladen) -> None:
    asyncio.run(app_update.automatisch(seite, _mit_release(state)))
    lauf = state.app_update
    assert lauf.phase == VORBEREITET and lauf.automatisch
    assert "eine Minute" in lauf.meldung
    dienst = state.installieren
    assert dienst.vorbereitet == 11
    assert (dienst.installiert, dienst.abgeschickt, dienst.wecker) == ([], 0, [])  # App vorn


def test_automatik_beim_laden_schon_im_hintergrund(state, seite, geladen) -> None:
    state.im_vordergrund = False
    asyncio.run(app_update.automatisch(seite, _mit_release(state)))
    assert state.installieren.wecker == [WARTEN_S]


@pytest.mark.parametrize(
    "bedingung",
    [
        "schalter aus",
        "mobile daten",
        "vor android 12",
        "nicht erlaubt",
        "ausgelassen",
        "kein release",
    ],
)
def test_automatik_nur_wenn_alles_passt(state, seite, geladen, bedingung) -> None:
    _mit_release(state)
    dienst = state.installieren
    if bedingung == "schalter aus":
        state.auto = False
    elif bedingung == "mobile daten":
        dienst.getaktet = True
    elif bedingung == "vor android 12":
        dienst.still = False
    elif bedingung == "nicht erlaubt":
        dienst.darf = False
    elif bedingung == "ausgelassen":
        state.auslassen = RELEASE.tag
    else:
        state.updates = SimpleNamespace(app=None)
    asyncio.run(app_update.automatisch(seite, state))
    assert geladen == []
    assert state.app_update is None or state.app_update.phase == BEREIT


def test_automatik_erst_nach_dem_hinweis(state, seite, geladen) -> None:
    state.hinweis_gesehen = False
    asyncio.run(app_update.automatisch(seite, _mit_release(state)))
    assert geladen == [] and len(seite.dialoge) == 1
    dialog = seite.dialoge[0]
    texte = [a.content for a in dialog.actions]
    assert texte == ["Ausschalten", "Verstanden"]
    assert "WLAN" in dialog.content.value
    asyncio.run(dialog.actions[1].on_click())  # Verstanden
    assert state.hinweis_gesehen and state.installieren.benachrichtigung == 1
    assert state.app_update.phase == VORBEREITET


def test_hinweis_ausschalten(state, seite, geladen) -> None:
    state.hinweis_gesehen = False
    asyncio.run(app_update.automatisch(seite, _mit_release(state)))
    seite.dialoge[0].actions[0].on_click()  # Ausschalten
    assert state.hinweis_gesehen and not state.auto
    assert geladen == []


@pytest.fixture(autouse=True)
def _kein_systemdialog(monkeypatch) -> None:
    """Der Zähler der Systemdialoge lebt im Prozess (N131): Ein Test davor, der Teilen oder
    die Dateiauswahl benutzt hat, darf hier keine Nachfrist hinterlassen."""
    from trainingsapp.ui import systemdialog

    monkeypatch.setattr(systemdialog, "_zuletzt", float("-inf"))
    monkeypatch.setattr(systemdialog, "_offen", 0)


def _vorbereitet(state: Zustand, seite: Seite) -> UpdateLauf:
    asyncio.run(app_update.automatisch(seite, _mit_release(state)))
    assert state.app_update.phase == VORBEREITET
    return state.app_update


def test_wecker_beim_verlassen_und_zurueck(state, seite, geladen) -> None:
    _vorbereitet(state, seite)
    asyncio.run(app_update.lebenszyklus(seite, state, False))
    asyncio.run(app_update.lebenszyklus(seite, state, True))
    assert state.installieren.wecker == [WARTEN_S, None]


def test_kein_wecker_waehrend_etwas_laeuft(state, seite, geladen, monkeypatch) -> None:
    _vorbereitet(state, seite)
    monkeypatch.setattr(
        app_update, "laufendes", lambda s: [Laufend("Timer", "Planke 0:30", "Timer")]
    )
    asyncio.run(app_update.lebenszyklus(seite, state, False))
    assert state.installieren.wecker == []


def test_kein_wecker_solange_ein_systemdialog_offen_ist(state, seite, geladen, monkeypatch) -> None:
    """N131: Dateiauswahl, Fotoauswahl und Teilen-Blatt zählen für Android als „verlassen“ —
    die Automatik stellt dann keinen Wecker, auch nicht kurz nach der Rückkehr."""
    from trainingsapp.ui import systemdialog

    _vorbereitet(state, seite)

    async def in_der_auswahl() -> None:
        await app_update.lebenszyklus(seite, state, False)

    asyncio.run(systemdialog.mit(in_der_auswahl()))
    assert state.installieren.wecker == []
    asyncio.run(app_update.lebenszyklus(seite, state, False))  # Nachfrist
    assert state.installieren.wecker == []
    assert not systemdialog.ist_offen(jetzt=time.monotonic() + systemdialog.NACHFRIST_S + 1)


def test_kein_wecker_mit_offenem_formular(state, geladen) -> None:
    formular = Seite(
        SimpleNamespace(route="/", can_pop=False),
        SimpleNamespace(route="/uebung/1/bearbeiten", can_pop=False),
    )
    _vorbereitet(state, formular)
    assert app_update.formular_offen(formular)
    asyncio.run(app_update.lebenszyklus(formular, state, False))
    assert state.installieren.wecker == []
    # Nur Seiten, die Zurück nicht anhalten: kein Formular
    assert not app_update.formular_offen(Seite(SimpleNamespace(route="/", can_pop=False)))
    assert not app_update.formular_offen(Seite(SimpleNamespace(route="/x", can_pop=True)))


def test_jetzt_installieren_schickt_die_sitzung_ab(state, seite, geladen) -> None:
    lauf = _vorbereitet(state, seite)
    gesichert: list[int] = []
    state.vor_dem_verlassen["notiz"] = lambda: gesichert.append(1)
    asyncio.run(app_update.installieren(state, lauf))
    dienst = state.installieren
    assert (dienst.abgeschickt, dienst.installiert, gesichert) == (1, [], [1])
    assert lauf.phase == INSTALLIEREN


def test_jetzt_installieren_ohne_sitzung_schreibt_neu(state, seite, geladen) -> None:
    lauf = _vorbereitet(state, seite)
    state.installieren.vorbereitet = -1  # Android hat die Sitzung verworfen (Neustart)
    asyncio.run(app_update.installieren(state, lauf))
    assert state.installieren.installiert == [str(geladen[0])]
    assert lauf.phase == INSTALLIEREN


def test_schalter_aus_verwirft_die_sitzung(state, seite, geladen) -> None:
    lauf = _vorbereitet(state, seite)
    asyncio.run(app_update.automatik_umschalten(seite, state, False))
    assert not state.auto and state.installieren.verworfen == 1
    assert lauf.phase == GELADEN  # die Datei bleibt für „Installieren“
    asyncio.run(app_update.lebenszyklus(seite, state, False))
    assert state.installieren.wecker == []


def test_schalter_an_legt_gleich_los(state, seite, geladen) -> None:
    state.auto, state.hinweis_gesehen = False, False
    asyncio.run(app_update.automatik_umschalten(seite, _mit_release(state), True))
    assert state.auto and state.hinweis_gesehen  # eingeschaltet = gelesen, kein Dialog
    assert seite.dialoge == [] and state.installieren.benachrichtigung == 1
    assert state.app_update.phase == VORBEREITET


def test_fremde_apk_von_selbst_wird_ausgelassen(state, seite, geladen) -> None:
    state.installieren.pruefung = {"eigenes_paket": True, "gleiche_signatur": False}
    asyncio.run(app_update.automatisch(seite, _mit_release(state)))
    assert state.app_update.phase == FEHLER and state.auslassen == RELEASE.tag
    asyncio.run(app_update.automatisch(seite, state))  # beim nächsten Start: nicht noch einmal
    assert len(geladen) == 1


def test_netzfehler_von_selbst_wird_nicht_ausgelassen(state, seite, monkeypatch, tmp_path) -> None:
    def kaputt(*a, **k):
        raise UpdateFehler("HTTP 500")

    monkeypatch.setattr(app_update, "apk_laden", kaputt)
    monkeypatch.setattr(app_update, "updateverzeichnis", lambda: tmp_path)
    asyncio.run(app_update.automatisch(seite, _mit_release(state)))
    assert state.app_update.phase == FEHLER and state.auslassen == ""


def test_android_lehnt_ab_von_selbst_wird_ausgelassen(state, seite, geladen) -> None:
    lauf = _vorbereitet(state, seite)
    app_update.ergebnis(state, 3, "INSTALL_FAILED_ABORTED")
    assert lauf.phase == GELADEN and state.auslassen == RELEASE.tag


class _Einstellungen:
    def __init__(self) -> None:
        self.werte: dict[str, str] = {}

    def lesen(self, key: str, vorgabe: str | None = None) -> str | None:
        return self.werte.get(key, vorgabe)

    def setzen(self, key: str, value: str) -> None:
        self.werte[key] = value


def test_wecker_ohne_ergebnis_gibt_die_automatik_auf(state, seite, geladen) -> None:
    """N125: Scheitert das Update im Hintergrund, während die App nicht lebt, kommt kein
    Ergebnis an. Nach `VERSUCHE_MAX` gestellten Weckern, nach denen beim nächsten Start noch
    die alte Version läuft, lädt die Automatik nicht wieder — und die Karte sagt es."""
    state.einstellungen = _Einstellungen()
    for start in range(app_update.VERSUCHE_MAX):
        state.app_update = None  # neuer Start der App
        _vorbereitet(state, seite)
        asyncio.run(app_update.lebenszyklus(seite, state, False))  # Wecker, dann Prozess-Tod
        assert len(geladen) == start + 1 and state.auslassen == ""
    state.app_update = None
    asyncio.run(app_update.automatisch(seite, state))
    assert len(geladen) == app_update.VERSUCHE_MAX and state.auslassen == RELEASE.tag
    lauf = state.app_update
    assert lauf.phase == BEREIT and "nicht von selbst installiert" in lauf.meldung
    asyncio.run(app_update.automatisch(seite, state))  # und danach gar nicht mehr
    assert len(geladen) == app_update.VERSUCHE_MAX


def test_zurueck_vor_dem_wecker_zaehlt_nicht(state, seite, geladen) -> None:
    state.einstellungen = _Einstellungen()
    lauf = _vorbereitet(state, seite)
    for _ in range(5):
        asyncio.run(app_update.lebenszyklus(seite, state, False))
        assert app_update._versuche(state, RELEASE.tag) == 1
        asyncio.run(app_update.lebenszyklus(seite, state, True))
        assert app_update._versuche(state, RELEASE.tag) == 0
    assert lauf.phase == VORBEREITET and state.auslassen == ""


def test_sitzung_weg_beim_zurueckkommen_heisst_gescheitert(state, seite, geladen) -> None:
    """N125: Der Wecker hat die Sitzung abgeschickt, die alte Version läuft noch und kein
    Ergebnis kam — beim Zurückkommen steht es in der Karte, das Release wird ausgelassen."""
    state.einstellungen = _Einstellungen()
    lauf = _vorbereitet(state, seite)
    asyncio.run(app_update.lebenszyklus(seite, state, False))
    state.installieren.vorbereitet = -1  # abgeschickt, ohne dass `ergebnis` lief
    asyncio.run(app_update.lebenszyklus(seite, state, True))
    assert lauf.phase == GELADEN and "nicht von selbst installiert" in lauf.meldung
    assert state.auslassen == RELEASE.tag and not lauf.automatisch


def test_einstellungen_im_app_state(tmp_path) -> None:
    from trainingsapp.ui.state import AppState

    s = AppState.starten(tmp_path / "app.db")
    try:
        assert s.app_update_auto() and not s.app_update_hinweis_gesehen()
        assert s.app_update_auslassen() == ""
        s.app_update_auto_setzen(False)
        s.app_update_hinweis_merken()
        s.app_update_auslassen_setzen("v0.3.81")
        assert not s.app_update_auto() and s.app_update_hinweis_gesehen()
        assert s.app_update_auslassen() == "v0.3.81"
    finally:
        s.schliessen()
