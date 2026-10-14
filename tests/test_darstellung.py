"""Farbprofile: je Profil gespeichert, lesbar in jeder Palette und jedem Modus."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from trainingsapp.core.darstellung import (
    DUNKEL,
    HELL,
    OLED,
    PALETTEN,
    PETROL,
    VIOLETT,
    Darstellung,
    darstellung_lesen,
    darstellung_schreiben,
    kontrast,
)
from trainingsapp.ui.state import AppState

#: Näherung der Material-Textfarbe (``on_surface``, Ton 90 bzw. 10) — die
#: Grundfarben liegen nah genug beieinander, dass der Ton kaum abweicht
TEXT = {DUNKEL: "#DEE4E1", HELL: "#171D1B"}

#: Flächen, die Material im hellen Modus selbst ableitet (Paletten ohne
#: eigene helle Stufen, z. B. OLED) — von Bildschirmfotos abgelesen
ABGELEITET_HELL = ("#FFFFFF", "#F5FBF7", "#EFF5F1", "#E9EFEB", "#E3EAE6", "#DEE4E1")


def flaechen(modus: str) -> list[str]:
    """Alle Flächen aller Paletten eines Modus, Verlauf eingeschlossen."""
    farben: list[str] = []
    for p in PALETTEN.values():
        f = p.dunkel if modus == DUNKEL else p.hell
        if f is None:
            farben.extend(ABGELEITET_HELL)
            continue
        farben.extend(f.stufen())
        if f.verlauf:
            farben.extend(f.verlauf)
    return farben


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


def test_lesen_und_schreiben() -> None:
    d = Darstellung(palette=VIOLETT, helligkeit=HELL, verlauf=False)
    assert darstellung_lesen(darstellung_schreiben(d)) == d
    assert darstellung_lesen("kein json") == Darstellung()
    assert darstellung_lesen("[1, 2]") == Darstellung()


def test_jedes_profil_hat_seine_darstellung(state) -> None:
    erstes = state.profil.id
    assert state.darstellung() == Darstellung()  # Vorgabe: Petrol, System, Verlauf
    state.darstellung_setzen(Darstellung(palette=OLED, helligkeit=DUNKEL))

    state.profil_anlegen("Gast")
    assert state.darstellung() == Darstellung()  # das neue Profil beginnt bei der Vorgabe
    state.darstellung_setzen(Darstellung(palette=VIOLETT))

    state.profil_wechseln(erstes)
    assert state.darstellung().palette == OLED
    assert state.darstellung(erstes).helligkeit == DUNKEL


@pytest.mark.parametrize("modus", [DUNKEL, HELL])
def test_text_ist_auf_jeder_flaeche_lesbar(modus: str) -> None:
    """WCAG AA für Fließtext: mindestens 4,5:1 — auch auf dem Verlauf."""
    for farbe in flaechen(modus):
        assert kontrast(TEXT[modus], farbe) >= 4.5, (modus, farbe)


def test_flaechen_steigen_stufenweise() -> None:
    """Dunkel: jede höhere Stufe ist heller — sonst verschwimmen Kacheln."""
    from trainingsapp.core.darstellung import leuchtdichte

    for p in PALETTEN.values():
        stufen = [leuchtdichte(c) for c in p.dunkel.stufen()[1:]]  # ab surface
        assert stufen == sorted(stufen), p.key


def test_kurven_im_hellen_modus_sichtbar() -> None:
    """Grafik nach WCAG: jede helle Kurvenfarbe ≥ 3:1 auf jeder hellen Fläche."""
    pytest.importorskip("flet")
    from trainingsapp.ui.farben import DUNKEL as KURVEN_DUNKEL
    from trainingsapp.ui.farben import HELL as KURVEN_HELL

    assert KURVEN_HELL.keys() == KURVEN_DUNKEL.keys()
    for name, farbe in KURVEN_HELL.items():
        if not farbe.startswith("#"):
            continue  # Material-Rolle (TERTIARY) passt sich selbst an
        for grund in flaechen(HELL):
            assert kontrast(farbe, grund) >= 3.0, (name, farbe, grund)


def test_thema_und_hintergrund() -> None:
    ft = pytest.importorskip("flet")
    from trainingsapp.ui import farben
    from trainingsapp.ui.theme import anwenden, hintergrund, hintergrund_setzen, thema

    petrol, oled = PALETTEN[PETROL], PALETTEN[OLED]
    t = thema(petrol, True, True)
    assert t.color_scheme is not None and t.color_scheme.surface == petrol.dunkel.surface
    assert t.scaffold_bgcolor == ft.Colors.TRANSPARENT  # sonst deckt das Gerüst den Verlauf zu
    assert thema(petrol, True, False).scaffold_bgcolor == petrol.dunkel.surface
    assert hintergrund(oled, True, True) is None  # OLED bleibt schwarz
    assert thema(oled, False, True).color_scheme is None  # hell: Material leitet ab

    page = SimpleNamespace(platform_brightness=None, views=[ft.View(route="/")])
    try:
        anwenden(page, Darstellung(helligkeit=HELL))
        assert page.theme_mode == ft.ThemeMode.LIGHT
        assert farben.FARBEN["rmssd"] == farben.HELL["rmssd"]
        hintergrund_setzen(page, Darstellung(helligkeit=HELL))
        assert page.views[0].decoration is not None

        anwenden(page, Darstellung(helligkeit=DUNKEL, verlauf=False))
        assert farben.FARBEN["rmssd"] == farben.DUNKEL["rmssd"]
        hintergrund_setzen(page, Darstellung(verlauf=False))
        assert page.views[0].decoration is None
    finally:
        farben.helligkeit_setzen(False)
