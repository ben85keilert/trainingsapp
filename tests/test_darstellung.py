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


#: Die Material-Töne der dunklen Kurvenfarben (`ui.farben.DUNKEL` nennt sie beim Namen)
MATERIAL = {
    "bluegrey300": "#90A4AE", "bluegrey400": "#78909C", "cyan400": "#26C6DA",
    "amber400": "#FFCA28", "purple300": "#BA68C8", "lightgreen400": "#9CCC65",
    "blue400": "#42A5F5", "lightblue300": "#4FC3F7", "orange400": "#FFA726",
    "orange600": "#FB8C00", "teal400": "#26A69A", "pink300": "#F06292",
    "indigo300": "#7986CB", "deeporange300": "#FF8A65", "brown300": "#A1887F",
    "lime600": "#C0CA33", "red400": "#EF5350",
}  # fmt: skip

#: Was Material ohne eigene Akzente aus der Grundfarbe ableitet (Petrol, Nachtblau, Violett,
#: OLED = Petrol): Töne 40/100 und 90/10 im Hellen, 80/20 und 30/90 im Dunkeln, Chroma 36 —
#: am 11.11.2026 mit material-color-utilities nachgerechnet. Näherung: Flutter rechnet selbst.
ABGELEITET = {
    "#2E7D6E": {
        HELL: {"primary": ("#FFFFFF", "#046B5C"), "primary_container": ("#00201B", "#A0F2DF")},
        DUNKEL: {"primary": ("#00382F", "#84D6C3"), "primary_container": ("#A0F2DF", "#005045")},
    },
    "#3F6DB5": {
        HELL: {"primary": ("#FFFFFF", "#415F91"), "primary_container": ("#001B3E", "#D7E3FF")},
        DUNKEL: {"primary": ("#0B305F", "#AAC7FF"), "primary_container": ("#D7E3FF", "#284777")},
    },
    "#7A5EA8": {
        HELL: {"primary": ("#FFFFFF", "#69548D"), "primary_container": ("#240E45", "#ECDCFF")},
        DUNKEL: {"primary": ("#3A255B", "#D5BBFC"), "primary_container": ("#ECDCFF", "#513C73")},
    },
}


#: Bestand vom 14.10.2026, bewusst nicht angefasst: Ganz oben im Petrol-Verlauf kommen SDNN
#: (Lila), der Gipfel (Indigo) und Rot auf 2,90 bis 2,99 statt 3:1 — auf den Karten, wo die
#: Kurven stehen, reicht es. Für die Paletten mit eigenen Akzenten gilt überall 3:1.
VERLAUF_BESTAND = 2.9


def _flaechen_von(p, modus: str) -> list[str]:
    f = p.dunkel if modus == DUNKEL else p.hell
    if f is None:
        return list(ABGELEITET_HELL)
    return [*f.stufen(), *(f.verlauf or ())]


@pytest.mark.parametrize("key", list(PALETTEN))
@pytest.mark.parametrize("modus", [DUNKEL, HELL])
def test_akzente_jeder_palette_sind_lesbar(key: str, modus: str) -> None:
    """WCAG AA (4,5:1) für jedes Paar aus Schrift und Fläche — Primär, Container, Text auf
    jeder Flächenstufe. Paletten mit eigenen Akzenten mit ihren Werten, die übrigen mit dem,
    was Material ableitet."""
    p = PALETTEN[key]
    a = p.akzente(modus == DUNKEL)
    paare = a.paare() if a is not None else ABGELEITET[p.saat][modus]
    for name, (schrift, flaeche) in paare.items():
        assert kontrast(schrift, flaeche) >= 4.5, (key, modus, name, schrift, flaeche)
    for grund in _flaechen_von(p, modus):
        text = a.on_surface if a is not None else TEXT[modus]
        assert kontrast(text, grund) >= 4.5, (key, modus, "on_surface", grund)
        if a is None:
            continue
        # leiser Text (Untertitel) und die Akzente als Schrift, Symbol oder Kurve
        assert kontrast(a.on_surface_variant, grund) >= 4.5, (key, modus, "variant", grund)
        assert kontrast(a.primary, grund) >= 4.5, (key, modus, "primary als Schrift", grund)
        assert kontrast(a.tertiary, grund) >= 4.5, (key, modus, "tertiary als Kurve", grund)


def test_neue_paletten_haben_beide_modi_und_akzente() -> None:
    from trainingsapp.core.darstellung import BERNSTEIN, KORALLE, SAND

    for key in (SAND, BERNSTEIN, KORALLE):
        p = PALETTEN[key]
        assert p.hell is not None and p.akzente_hell is not None and p.akzente_dunkel is not None
        assert p.hell.verlauf is not None and p.dunkel.verlauf is not None
        # Gelb als Fläche trägt dunkle Schrift, als Schrift auf Hellem ist es dunkel
        assert leuchtdichte_von(p.akzente_dunkel.on_primary) < 0.1
        assert leuchtdichte_von(p.akzente_hell.primary) < 0.2


def leuchtdichte_von(farbe: str) -> float:
    from trainingsapp.core.darstellung import leuchtdichte

    return leuchtdichte(farbe)


def _lab(farbe: str) -> tuple[float, float, float]:
    """CIE-Lab (D65) einer ``#RRGGBB``-Farbe — für den Farbabstand ΔE."""
    h = farbe.lstrip("#")
    r, g, b = (
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        for c in (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    )
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    fx, fy, fz = (t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (x, y, z))
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _abstand(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(_lab(a), _lab(b), strict=True)) ** 0.5


@pytest.mark.parametrize("key", list(PALETTEN))
@pytest.mark.parametrize("modus", [DUNKEL, HELL])
def test_kurven_auf_jeder_palette_sichtbar_und_unterscheidbar(key: str, modus: str) -> None:
    """Grafik nach WCAG (≥ 3:1) für jede Kurvenfarbe auf jeder Fläche der Palette — hell wie
    dunkel, mit den Abweichungen der Palette; und die Linien einer Übung (Primärfarbe zuerst)
    fallen auseinander."""
    pytest.importorskip("flet")
    from trainingsapp.ui import farben

    p = PALETTEN[key]
    a = p.akzente(modus == DUNKEL)
    f = p.dunkel if modus == DUNKEL else p.hell
    verlauf = f.verlauf if f is not None else None
    try:
        farben.helligkeit_setzen(modus == HELL, key)
        kurven = {
            n: MATERIAL.get(str(getattr(c, "value", c)), str(c)) for n, c in farben.FARBEN.items()
        }
    finally:
        farben.helligkeit_setzen(False)
    for name, farbe in kurven.items():
        if not farbe.startswith("#"):
            continue  # Material-Rolle (PRIMARY, TERTIARY): mit den Akzenten oben geprüft
        for grund in _flaechen_von(p, modus):
            oben = a is None and grund in (verlauf or ())
            mindestens = VERLAUF_BESTAND if oben else 3.0
            assert kontrast(farbe, grund) >= mindestens, (key, modus, name, farbe, grund)
    if a is None:
        return
    reihen = [a.primary, *(kurven[r] for r in farben.REIHEN[1:])]
    for i, eine in enumerate(reihen):
        for andere in reihen[i + 1 :]:
            assert _abstand(eine, andere) >= 20, (key, modus, eine, andere)
    # die Herzfrequenz (TERTIARY) neben den Kurven, mit denen sie zusammen steht
    for name in ("rmssd", "hf_geraet", "mean_rr", "sdnn", "pnnx", "atemfrequenz"):
        assert _abstand(a.tertiary, kurven[name]) >= 20, (key, modus, name)


def test_thema_bringt_die_akzente_der_palette() -> None:
    pytest.importorskip("flet")
    from trainingsapp.core.darstellung import BERNSTEIN
    from trainingsapp.ui import farben
    from trainingsapp.ui.theme import anwenden, thema

    p = PALETTEN[BERNSTEIN]
    for dunkel in (True, False):
        schema = thema(p, dunkel, True).color_scheme
        a = p.akzente(dunkel)
        assert schema is not None and a is not None
        assert (schema.primary, schema.on_primary) == (a.primary, a.on_primary)
        assert schema.on_surface == a.on_surface
    # ohne eigene Akzente bleibt die Ableitung aus der Grundfarbe
    assert thema(PALETTEN[PETROL], True, True).color_scheme.primary is None

    page = SimpleNamespace(platform_brightness=None, views=[])
    try:
        anwenden(page, Darstellung(palette=BERNSTEIN, helligkeit=DUNKEL))
        assert farben.FARBEN["reihe_2"] == farben.JE_PALETTE[BERNSTEIN][0]["reihe_2"]
        anwenden(page, Darstellung(palette=PETROL, helligkeit=DUNKEL))
        assert farben.FARBEN["reihe_2"] == farben.DUNKEL["reihe_2"]
    finally:
        farben.helligkeit_setzen(False)


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
