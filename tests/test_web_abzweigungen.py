"""Abzweigungen für die Web-Fassung: dokumentiert, gezählt, getestet (Ben, 14.11.2026).

„Abzweigungen streng dokumentiert und getrackt, damit sie wirklich getestet werden“: Jede
Stelle, an der der Quelltext für den Browser etwas anderes tut als in der App, steht in
`docs/web_abzweigungen.toml` — mit einem Test oder einem Gerätetest. Dieser Test zählt die
Stellen im Quelltext nach; eine neue Abzweigung ohne Eintrag lässt ihn scheitern. Darunter die
Tests der Web-Zweige selbst (Web-Profil, Karte „Rechtliches“, Bluetooth-Transport).
Regel und Begründung: `docs/plan_web.md` §2.
"""

from __future__ import annotations

import asyncio
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from trainingsapp import config
from trainingsapp.core.laufend import Benachrichtigung
from trainingsapp.core.links import erlaubt

PROJEKT = Path(__file__).resolve().parents[1]
REGISTER = PROJEKT / "docs" / "web_abzweigungen.toml"

#: Woran eine Abzweigung im Quelltext zu erkennen ist (dieselbe Liste steht im Register)
MARKE_PY = re.compile(r'\bim_browser\(|"emscripten"|\b_web\b|\bweb_verweise\(|TRAININGSAPP_WEB')
MARKE_DART = re.compile(r"\bkIsWeb\b")


def _stellen(datei: Path, marke: re.Pattern[str], kommentar: str) -> int:
    return sum(
        1
        for zeile in datei.read_text(encoding="utf-8").splitlines()
        if marke.search(zeile) and not zeile.lstrip().startswith(kommentar)
    )


def gezaehlt() -> dict[str, int]:
    """Datei → Zahl der Stellen, an denen sie für den Browser abzweigt."""
    funde: dict[str, int] = {}
    for datei in sorted((PROJEKT / "src" / "trainingsapp").rglob("*.py")):
        if n := _stellen(datei, MARKE_PY, "#"):
            funde[datei.relative_to(PROJEKT).as_posix()] = n
    for datei in sorted((PROJEKT / "erweiterungen").rglob("*.dart")):
        teile = datei.relative_to(PROJEKT).parts
        if "build" in teile or ".dart_tool" in teile:
            continue
        if n := _stellen(datei, MARKE_DART, "//"):
            funde[datei.relative_to(PROJEKT).as_posix()] = n
    return funde


def register() -> list[dict]:
    with REGISTER.open("rb") as f:
        return tomllib.load(f)["abzweigung"]


# -- Das Register stimmt mit dem Quelltext überein ---------------------------------------------


def test_jede_abzweigung_steht_im_register() -> None:
    eingetragen = {e["datei"]: e["stellen"] for e in register()}
    assert gezaehlt() == eingetragen, (
        "Der Quelltext zweigt für den Browser anders ab, als docs/web_abzweigungen.toml sagt. "
        "Neue Abzweigung? Erst prüfen, ob sie ins Web-Profil gehört (config.WEB); sonst dort "
        "eintragen — mit einem Test, der die Stelle im Web-Zweig durchläuft."
    )


def test_jede_abzweigung_nennt_was_sie_prueft() -> None:
    offene = (PROJEKT / "docs" / "offene_fragen.md").read_text(encoding="utf-8")
    for eintrag in register():
        datei = eintrag["datei"]
        assert eintrag.get("was", "").strip(), f"{datei}: „was“ fehlt"
        tests, geraet = eintrag.get("test", []), eintrag.get("geraetetest", "")
        assert tests or geraet, f"{datei}: weder Test noch Gerätetest genannt"
        for name in tests:
            pfad, _, funktion = name.partition("::")
            text = (PROJEKT / pfad).read_text(encoding="utf-8")
            assert re.search(rf"^(async )?def {re.escape(funktion)}\(", text, re.M), (
                f"{datei}: den Test {name} gibt es nicht"
            )
        if geraet:
            assert f"| {geraet} |" in offene, (
                f"{datei}: Gerätetest {geraet} steht nicht in docs/offene_fragen.md"
            )


def test_abgeschaltete_funktionen_stehen_im_vertrag() -> None:
    vertrag = (PROJEKT / "docs" / "plan_web.md").read_text(encoding="utf-8")
    for funktion in config.WEB.ohne:
        assert f"| `{funktion}` |" in vertrag, (
            f"docs/plan_web.md §2 nennt {funktion} nicht — warum fehlt sie im Browser?"
        )
    assert config.NICHT_IM_BROWSER is config.WEB.ohne


# -- Die Web-Zweige selbst ---------------------------------------------------------------------


def test_web_profil_schaltet_funktionen_ab_und_zeigt_verweise(monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_EDITION", "solo")
    monkeypatch.delenv("TRAININGSAPP_WEB", raising=False)
    assert not config.im_browser() and config.web_verweise() == ()
    assert all(config.ist_aktiv(f) for f in config.WEB.ohne)  # in der App alle da (solo)

    monkeypatch.setenv("TRAININGSAPP_WEB", "1")
    assert config.im_browser()
    assert not any(config.ist_aktiv(f) for f in config.WEB.ohne)
    assert config.ist_aktiv("plaene") and config.ist_aktiv("hrv_rohdaten")  # der Rest bleibt
    titel = [t for t, _ in config.web_verweise()]
    assert titel == ["Impressum", "Datenschutzerklärung", "Quelltext bei GitHub"]
    assert all(erlaubt(url) for _, url in config.web_verweise())  # nur https, sonst öffnet nichts


def _zeilen(ansicht, ft) -> list:
    def alle(wurzel):
        yield wurzel
        for name in ("content", "controls"):
            kind = getattr(wurzel, name, None)
            for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
                if isinstance(k, ft.BaseControl):
                    yield from alle(k)

    return [c for v in ansicht.controls for c in alle(v) if isinstance(c, ft.ListTile)]


def test_einstellungen_zeigen_rechtliches_nur_im_browser(tmp_path, monkeypatch) -> None:
    ft = pytest.importorskip("flet")
    from trainingsapp.ui.state import AppState
    from trainingsapp.ui.views.einstellungen import MENUE, einstellungen

    monkeypatch.setenv("TRAININGSAPP_EDITION", "solo")
    geoeffnet: list[str] = []

    async def launch_url(url: str) -> None:
        geoeffnet.append(url)

    browser = SimpleNamespace(launch_url=launch_url)
    page = SimpleNamespace(route="/einstellungen", views=[], platform=None, dialoge=[])
    page.update = lambda: None
    page.show_dialog = page.dialoge.append
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    try:
        monkeypatch.delenv("TRAININGSAPP_WEB", raising=False)
        in_der_app = [z.data for z in _zeilen(einstellungen(page, state, browser), ft)]
        assert in_der_app == [z.route for z in MENUE]  # keine Zeile mehr als das Menü

        monkeypatch.setenv("TRAININGSAPP_WEB", "1")
        zeilen = _zeilen(einstellungen(page, state, browser), ft)
        verweise = [z for z in zeilen if str(z.data).startswith("https://")]
        assert [z.data for z in verweise] == [url for _, url in config.WEB.verweise]
        assert [z.title.value for z in verweise] == [t for t, _ in config.WEB.verweise]
        # das Menü darüber: dieselben Zeilen ohne das, was es im Browser nicht gibt
        routen = [z.data for z in zeilen if str(z.data).startswith("/")]
        assert routen == [z.route for z in MENUE if z.sichtbar()]
        assert "/einstellungen/updates" not in routen

        for zeile in verweise:
            asyncio.run(zeile.on_click())
        assert geoeffnet == [url for _, url in config.WEB.verweise]
        assert page.dialoge == []  # nichts wurde als „nicht erlaubt“ abgewiesen
    finally:
        state.schliessen()


def test_transport_im_browser_lange_frist_und_keine_grosse_zahl() -> None:
    pytest.importorskip("flet")
    from trainingsapp.ui.geraete.flet_ble_transport import (
        FRIST_AUSWAHL_WEB_S,
        FletBleTransport,
    )

    fristen: list[float] = []

    async def scan(timeout_s: float) -> list:
        fristen.append(timeout_s)
        return []

    t = FletBleTransport.__new__(FletBleTransport)  # ohne Seite und ohne Erweiterung
    t.ble = SimpleNamespace(scan=scan)
    jetzt = Benachrichtigung("Timer läuft", "noch 0:30", "noch 0:30", 1_794_609_744_000)

    assert t._web is False  # Vorgabe: die App
    asyncio.run(t.scan(8.0))
    assert fristen == [8.0] and t._seit_ms(jetzt) == jetzt.seit_ms

    t._web = True
    asyncio.run(t.scan(8.0))
    assert fristen[-1] == FRIST_AUSWAHL_WEB_S > 8.0  # das Auswahlfenster des Browsers wartet
    assert t._seit_ms(jetzt) == 0  # Epochen-Millisekunden (> 0xFFFFFFFF) kämen bei Dart nicht an
    assert jetzt.seit_ms > 0xFFFFFFFF
