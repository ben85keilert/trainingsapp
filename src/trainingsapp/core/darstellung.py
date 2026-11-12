"""Darstellung: Farbprofil, Hell/Dunkel und Hintergrundverlauf — je Profil.

Ben, 14.10.2026: „Das Systemschwarz ist einfach, aber auch sehr langweilig.“
Gewählt wurden vier Paletten (Petrol als Vorgabe, Nachtblau, Violett,
OLED-Schwarz), ein Schalter für den Verlauf und Hell/Dunkel/System. Die Wahl
gilt **je Profil** — teilen sich mehrere Personen ein Gerät, sieht man am
Hintergrund, wer gerade dran ist. Am 11.11.2026 kamen drei warme dazu: Sand,
Bernstein und Koralle.

Eine Palette ist reine Farbdaten: eine Grundfarbe, aus der Material die
Akzente ableitet, und sechs eigene Flächenstufen je Modus, die das abgeleitete
Fast-Schwarz ersetzen. Weil die App ihre Flächen über Material-Rollen färbt
(``SURFACE_CONTAINER_LOW`` …), färbt das die ganze App, ohne dass eine Ansicht
etwas davon weiß. ``ui/theme.py`` baut daraus das Flet-Thema.

Die warmen Paletten bringen zusätzlich ihre **Akzente** mit (`Akzente`): Aus
Gelb oder Koralle leitet Material gedämpfte Töne ab, und was es ableitet, lässt
sich hier nicht nachrechnen. Feste Paare (Primär und der Text darauf, Container
und der Text darauf) sind prüfbar — Gelb als Fläche trägt dunklen Text, als
Schrift auf hellem Grund wird es zu dunklem Bernstein.

Dieses Modul importiert kein ``flet``; die Kontrastrechnung hier prüft
``tests/test_darstellung.py`` für jede Palette.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

#: Helligkeit: dem System folgen oder fest
SYSTEM = "system"
HELL = "hell"
DUNKEL = "dunkel"
HELLIGKEITEN: dict[str, str] = {HELL: "Hell", DUNKEL: "Dunkel", SYSTEM: "System"}


@dataclass(frozen=True)
class Flaechen:
    """Die Flächenstufen eines Modus, von der untersten zur höchsten.

    Die Namen folgen den Material-Rollen (``surface_container_low`` …). ``verlauf``
    läuft von oben nach unten; ``None`` = einfarbig.
    """

    lowest: str
    surface: str
    low: str
    container: str
    high: str
    highest: str
    bright: str
    verlauf: tuple[str, str] | None = None

    def stufen(self) -> tuple[str, ...]:
        """Alle Flächen, auf denen Text oder Kurven stehen können."""
        return (self.lowest, self.surface, self.low, self.container, self.high, self.highest)


@dataclass(frozen=True)
class Akzente:
    """Die Akzentfarben eines Modus als feste Paare — ``on_…`` ist die Schrift auf der Fläche.

    Die Namen sind die Material-Rollen (``ft.ColorScheme``). ``primary`` und ``tertiary``
    stehen auch als Schrift, Symbol und Kurve auf den Flächen — darum sind sie im Hellen
    dunkel und im Dunkeln hell.
    """

    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str
    secondary_container: str
    on_secondary_container: str
    tertiary: str
    on_tertiary: str
    on_surface: str
    on_surface_variant: str

    def paare(self) -> dict[str, tuple[str, str]]:
        """Schrift und Fläche, die zusammen lesbar sein müssen (Name → (Schrift, Fläche))."""
        return {
            "primary": (self.on_primary, self.primary),
            "primary_container": (self.on_primary_container, self.primary_container),
            "secondary_container": (self.on_secondary_container, self.secondary_container),
            "tertiary": (self.on_tertiary, self.tertiary),
        }


@dataclass(frozen=True)
class Palette:
    """Ein Farbprofil. ``hell=None``: im hellen Modus leitet Material alles ab;
    ohne Akzente leitet Material sie aus ``saat`` ab."""

    key: str
    name: str
    saat: str
    dunkel: Flaechen
    hell: Flaechen | None
    akzente_dunkel: Akzente | None = None
    akzente_hell: Akzente | None = None

    def akzente(self, dunkel: bool) -> Akzente | None:
        return self.akzente_dunkel if dunkel else self.akzente_hell


PETROL = "petrol"
NACHTBLAU = "nachtblau"
VIOLETT = "violett"
OLED = "oled"
SAND = "sand"
BERNSTEIN = "bernstein"
KORALLE = "koralle"

PALETTEN: dict[str, Palette] = {
    PETROL: Palette(
        PETROL,
        "Petrol",
        "#2E7D6E",
        Flaechen("#08110F", "#0D1A17", "#12221F", "#162825", "#1D322E", "#263E39", "#2E4842",
                 ("#1F4740", "#0D1A17")),
        Flaechen("#FFFFFF", "#F2F8F6", "#EAF3F0", "#E3EEEA", "#DCE9E5", "#D3E3DE", "#F7FBFA",
                 ("#CFE8E0", "#F2F8F6")),
    ),
    NACHTBLAU: Palette(
        NACHTBLAU,
        "Nachtblau",
        "#3F6DB5",
        Flaechen("#070C16", "#0C1424", "#111B2E", "#152034", "#1C293F", "#25344C", "#2D3D57",
                 ("#20386A", "#0C1424")),
        Flaechen("#FFFFFF", "#F4F7FC", "#EBF0F8", "#E4EAF5", "#DCE4F1", "#D3DCEC", "#F9FBFE",
                 ("#D3E1F7", "#F4F7FC")),
    ),
    VIOLETT: Palette(
        VIOLETT,
        "Violett",
        "#7A5EA8",
        Flaechen("#0C0A12", "#14111C", "#1B1726", "#201B2C", "#282236", "#322B42", "#3A324B",
                 ("#36275E", "#14111C")),
        Flaechen("#FFFFFF", "#F8F5FC", "#F0EBF7", "#EBE5F4", "#E5DEF0", "#DDD5EA", "#FCFAFE",
                 ("#E4D6F7", "#F8F5FC")),
    ),
    # Echtes Schwarz spart auf OLED-Displays Strom (lange Messungen); die
    # Kacheln sind leicht getönt, damit sie sich vom Grund abheben.
    OLED: Palette(
        OLED,
        "OLED-Schwarz",
        "#2E7D6E",
        Flaechen("#000000", "#000000", "#0B0F0E", "#101513", "#171D1B", "#202826", "#2A3330"),
        None,
    ),
    # Warme Paletten (Ben, 11.11.2026). Jede Fläche bleibt im Dunkeln so dunkel und im
    # Hellen so hell wie bei den kühlen — die Kurvenfarben (`ui/farben.py`) sind darauf
    # abgestimmt.
    SAND: Palette(
        SAND,
        "Sand",
        "#A6814C",
        Flaechen("#100D09", "#17130D", "#1E1911", "#231E15", "#2C261B", "#373023", "#40382A",
                 ("#44351D", "#17130D")),
        Flaechen("#FFFFFF", "#FAF6EF", "#F4EEE3", "#F0E9DC", "#EBE3D4", "#E6DDCC", "#FDFBF7",
                 ("#EEDFC4", "#FAF6EF")),
        Akzente("#E3C28F", "#3F2D0B", "#5A431C", "#FFDEA9", "#51442F", "#F1E0C5",
                "#9FD1C0", "#04372B", "#ECE1D2", "#D2C5B1"),
        Akzente("#765626", "#FFFFFF", "#F6DFB8", "#2A1C05", "#EDDFC8", "#241A0A",
                "#2B6656", "#FFFFFF", "#1F1B14", "#4E4537"),
    ),
    BERNSTEIN: Palette(
        BERNSTEIN,
        "Bernstein",
        "#E0A100",
        Flaechen("#110D04", "#191407", "#201A0B", "#261F0E", "#2F2713", "#3B3119", "#453A1F",
                 ("#493705", "#191407")),
        Flaechen("#FFFFFF", "#FFF9EA", "#FBF2DC", "#F8EDD2", "#F4E7C7", "#F0E1BB", "#FFFCF4",
                 ("#FFE7A3", "#FFF9EA")),
        Akzente("#F6C344", "#3F2E00", "#5C4300", "#FFDF9C", "#54451C", "#F7E2AE",
                "#A9C7F5", "#0B305F", "#EDE2CC", "#D1C5A8"),
        Akzente("#775600", "#FFFFFF", "#FFDD82", "#261A00", "#F7E2A9", "#241A04",
                "#3B5F94", "#FFFFFF", "#1F1B10", "#4D4632"),
    ),
    KORALLE: Palette(
        KORALLE,
        "Koralle",
        "#D9705F",
        Flaechen("#120B0A", "#1B1110", "#231715", "#291B19", "#332321", "#402D2A", "#4A3532",
                 ("#51251F", "#1B1110")),
        Flaechen("#FFFFFF", "#FDF6F4", "#FAEEEB", "#F7E8E4", "#F3E1DC", "#EFDAD4", "#FFFBFA",
                 ("#FBD9D1", "#FDF6F4")),
        Akzente("#FFB4A6", "#5C150C", "#7E2B20", "#FFDAD3", "#5A3F3A", "#FCDCD5",
                "#8FD8B4", "#00382A", "#F1DFDB", "#D8C2BD"),
        Akzente("#9C3D2F", "#FFFFFF", "#FFDAD3", "#3B0906", "#F8DED8", "#2C1512",
                "#256B4B", "#FFFFFF", "#221918", "#534340"),
    ),
}  # fmt: skip


@dataclass(frozen=True)
class Darstellung:
    """Was ein Profil gewählt hat."""

    palette: str = PETROL
    helligkeit: str = SYSTEM
    verlauf: bool = True

    def farben(self) -> Palette:
        return PALETTEN[self.palette]


def darstellung_lesen(text: str | None) -> Darstellung:
    """Aus der gespeicherten Einstellung; Unbekanntes fällt auf die Vorgabe zurück.

    >>> darstellung_lesen(None)
    Darstellung(palette='petrol', helligkeit='system', verlauf=True)
    >>> darstellung_lesen('{"palette": "violett", "helligkeit": "dunkel", "verlauf": false}')
    Darstellung(palette='violett', helligkeit='dunkel', verlauf=False)
    >>> darstellung_lesen('{"palette": "gibt_es_nicht", "helligkeit": 3}').palette
    'petrol'
    """
    vorgabe = Darstellung()
    try:
        roh = json.loads(text) if text else {}
    except ValueError:
        roh = {}
    if not isinstance(roh, dict):
        roh = {}
    palette = roh.get("palette")
    helligkeit = roh.get("helligkeit")
    verlauf = roh.get("verlauf")
    return Darstellung(
        # nur Text kann ein Schlüssel sein — eine Liste dort würfe ``unhashable`` (H98)
        palette=palette if isinstance(palette, str) and palette in PALETTEN else vorgabe.palette,
        helligkeit=helligkeit
        if isinstance(helligkeit, str) and helligkeit in HELLIGKEITEN
        else vorgabe.helligkeit,
        verlauf=verlauf if isinstance(verlauf, bool) else vorgabe.verlauf,
    )


def darstellung_schreiben(d: Darstellung) -> str:
    return json.dumps(asdict(d), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Kontrast nach WCAG 2.x
# ---------------------------------------------------------------------------


def leuchtdichte(farbe: str) -> float:
    """Relative Leuchtdichte einer ``#RRGGBB``-Farbe (0 = schwarz, 1 = weiß).

    >>> leuchtdichte("#000000"), leuchtdichte("#FFFFFF")
    (0.0, 1.0)
    """
    h = farbe.lstrip("#")
    kanaele = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in kanaele)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontrast(a: str, b: str) -> float:
    """Kontrastverhältnis zweier Farben, 1 bis 21. Text braucht ≥ 4,5, Grafik ≥ 3.

    >>> round(kontrast("#000000", "#FFFFFF"), 1)
    21.0
    >>> round(kontrast("#FFCA28", "#EAF3F0"), 2)   # Amber auf heller Karte — zu blass
    1.35
    """
    hell, dunkel = sorted((leuchtdichte(a), leuchtdichte(b)), reverse=True)
    return (hell + 0.05) / (dunkel + 0.05)


__all__ = [
    "BERNSTEIN",
    "DUNKEL",
    "HELL",
    "HELLIGKEITEN",
    "KORALLE",
    "NACHTBLAU",
    "OLED",
    "PALETTEN",
    "PETROL",
    "SAND",
    "SYSTEM",
    "VIOLETT",
    "Akzente",
    "Darstellung",
    "Flaechen",
    "Palette",
    "darstellung_lesen",
    "darstellung_schreiben",
    "kontrast",
    "leuchtdichte",
]
