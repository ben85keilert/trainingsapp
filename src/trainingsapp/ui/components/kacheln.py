"""Werte über der Hauptkurve — als ruhige Übersicht (Vorgabe) oder als Kacheln.

Welche Werte, in welcher Reihenfolge und welche groß hervorgehoben sind, stellt
man unter Einstellungen → HRV-Messung ein — vollständig. Werte einer
Verlaufskurve tragen deren Farbe (Punkt bzw. Streifen) und rechnen mit
demselben Fenster wie die Kurve (`core.hrv_ansicht.Ansicht`). Gerechnet wird
nicht hier: Die Werte kommen fertig herein (`KachelWert`).

**Übersicht:** Die großen Werte stehen oben in einer Reihe, die übrigen
darunter als Liste — Name links, Wert rechts, feine Linien dazwischen. Gibt es
keinen Wert (Atemfrequenz bei undeutlicher Atmung), steht der Grund klein unter
dem Namen; manchmal mit einem Knopf, der weiterhilft („Atemübung").
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft
from hrv_core.trends import KENNZAHLEN

#: Feste Höhen — ein gleichmäßiges Raster statt Kacheln, die je nach Inhalt springen
HOEHE = 74
HOEHE_GROSS = 90


@dataclass(frozen=True, slots=True)
class KachelArt:
    """Ein wählbarer Wert."""

    titel: str
    #: Schlüssel der Verlaufskurve, deren aktuellen Wert er zeigt
    kennzahl: str | None = None
    erklaerung: str = ""


def _aus_kurve(kennzahl: str) -> KachelArt:
    k = KENNZAHLEN[kennzahl]
    return KachelArt(k.titel, kennzahl=kennzahl, erklaerung=k.erklaerung)


#: Alle Werte. Schlüssel bleiben stabil — sie stehen in den Einstellungen.
KACHELN: dict[str, KachelArt] = {
    "hf": KachelArt("Herzfrequenz", erklaerung="Zuletzt vom Gerät gemeldet."),
    "rr": KachelArt("RR", erklaerung="Letzter Abstand zweier Herzschläge."),
    "artefakte": KachelArt(
        "Artefakte", erklaerung="Markierte Schläge im Puffer bzw. korrigierte in der Messung."
    ),
    "schwankung": KachelArt(
        "Schwankung 60 s",
        erklaerung="Mittlere Spannweite der Herzfrequenz je 10 s — beschreibend, keine Bewertung.",
    ),
    **{k: _aus_kurve(k) for k in ("atemfrequenz", "rsa")},
    **{k: _aus_kurve(k) for k in ("hf_rr", "mean_rr", "rmssd", "sdnn", "pnnx")},
    **{k: _aus_kurve(k) for k in ("lf_power", "hf_power", "lf_hf", "gipfel", "vlf_power")},
    # ULF braucht Stunden (mindestens 4 h) — nur als Wert der ganzen Aufzeichnung
    "ulf": KachelArt(
        "ULF-Band",
        erklaerung="Leistung unter 0,003 Hz — Tagesrhythmus. Erst ab 4 h Messung, "
        "nur in der Aufzeichnung.",
    ),
    **{k: _aus_kurve(k) for k in ("sd1", "sd2", "dfa_alpha1")},
}

#: Gruppen für die Auswahl in den Einstellungen
GRUPPEN: list[tuple[str, list[str]]] = [
    ("Grundwerte", ["hf", "rr", "artefakte"]),
    ("Atmung", ["atemfrequenz", "rsa", "schwankung"]),
    ("Zeit", ["hf_rr", "mean_rr", "rmssd", "sdnn", "pnnx"]),
    ("Frequenz", ["lf_power", "hf_power", "lf_hf", "gipfel", "vlf_power", "ulf"]),
    ("Nichtlinear", ["sd1", "sd2", "dfa_alpha1"]),
]


@dataclass(frozen=True, slots=True)
class KachelWert:
    """Was ein Wert der Übersicht (oder eine Kachel) zeigt."""

    titel: str
    wert: str
    einheit: str = ""
    zusatz: str = ""
    farbe: str | None = None
    gross: bool = False
    #: Warum es keinen Wert gibt („Atemschwankung zu schwach")
    grund: str = ""
    #: Ein Knopf, der weiterhilft: (Beschriftung, Handler)
    aktion: tuple[str, Callable[[], object]] | None = None


def zahl(wert: float | int | None, nachkomma: int = 0) -> str:
    """„–" für fehlende Werte, sonst mit deutschem Komma.

    >>> zahl(None), zahl(12.345, 1), zahl(60)
    ('–', '12,3', '60')
    """
    if wert is None:
        return "–"
    return f"{wert:.{nachkomma}f}".replace(".", ",")


def kachel(w: KachelWert) -> ft.Control:
    # Der Farbstreifen ist ein eigenes Kästchen: Ein Rahmen nur links verträgt
    # sich in Flutter nicht mit runden Ecken.
    inhalt = ft.Container(
        expand=True,
        padding=ft.Padding.only(left=10, right=8, top=8, bottom=8),
        content=ft.Column(
            spacing=2,
            tight=True,
            controls=[
                ft.Text(w.titel, size=11, opacity=0.7, max_lines=1, no_wrap=True),
                ft.Row(
                    spacing=3,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(w.wert, size=28 if w.gross else 19, weight=ft.FontWeight.BOLD),
                        ft.Text(w.einheit, size=11, opacity=0.65),
                    ],
                ),
                ft.Text(
                    w.zusatz or w.grund,
                    size=10,
                    opacity=0.6,
                    max_lines=1,
                    visible=bool(w.zusatz or w.grund),
                ),
            ],
        ),
    )
    return ft.Container(
        col={"xs": 6} if w.gross else {"xs": 4},
        height=HOEHE_GROSS if w.gross else HOEHE,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Container(width=4, bgcolor=w.farbe or ft.Colors.TRANSPARENT),
                inhalt,
            ],
        ),
    )


def raster(werte: list[KachelWert]) -> ft.Control:
    """Große Kacheln zu zweit, die übrigen zu dritt — mit gleichmäßigem Abstand."""
    if not werte:
        return ft.Container()
    return ft.ResponsiveRow(spacing=10, run_spacing=10, controls=[kachel(w) for w in werte])


def uebersicht(werte: list[KachelWert]) -> ft.Control:
    """Große Werte oben in einer Reihe, die übrigen als ruhige Liste darunter."""
    if not werte:
        return ft.Container()
    gross = [w for w in werte if w.gross]
    liste = [w for w in werte if not w.gross]
    teile: list[ft.Control] = []
    if gross:
        teile.append(
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[_hauptwert(w) for w in gross],
            )
        )
    for i, w in enumerate(liste):
        if teile or i:
            teile.append(
                ft.Divider(
                    height=1,
                    thickness=0.5,
                    color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
                )
            )
        teile.append(_zeile(w))
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        border_radius=16,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
        content=ft.Column(spacing=6, tight=True, controls=teile),
    )


def _hauptwert(w: KachelWert) -> ft.Control:
    return ft.Container(
        expand=True,
        padding=ft.Padding.only(bottom=4),
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                ft.Row(
                    spacing=4,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(w.wert, size=34, weight=ft.FontWeight.BOLD, color=w.farbe),
                        ft.Text(w.einheit, size=13, opacity=0.65),
                    ],
                ),
                ft.Text(w.titel, size=12, opacity=0.7, max_lines=1),
                ft.Text(
                    w.grund or w.zusatz,
                    size=11,
                    opacity=0.55,
                    max_lines=2,
                    visible=bool(w.grund or w.zusatz),
                ),
            ],
        ),
    )


def _zeile(w: KachelWert) -> ft.Control:
    links: list[ft.Control] = [
        ft.Text(w.titel, size=14, max_lines=1),
    ]
    if w.grund:
        links.append(ft.Text(w.grund, size=11, opacity=0.6, max_lines=2))
    rechts: list[ft.Control] = []
    if w.aktion is not None:
        text, handler = w.aktion
        rechts.append(
            ft.TextButton(
                text,
                on_click=handler,
                style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8)),
            )
        )
    rechts.append(
        ft.Row(
            spacing=3,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.END,
            controls=[
                ft.Text(w.wert, size=17, weight=ft.FontWeight.W_600),
                ft.Text(f"{w.einheit} {w.zusatz}".strip(), size=12, opacity=0.65),
            ],
        )
    )
    return ft.Row(
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(
                width=8,
                height=8,
                border_radius=4,
                bgcolor=w.farbe or ft.Colors.TRANSPARENT,
            ),
            ft.Column(spacing=0, tight=True, expand=True, controls=links),
            *rechts,
        ],
    )


def anzeige(werte: list[KachelWert], darstellung: str) -> ft.Control:
    """Übersicht oder Kacheln — wie eingestellt."""
    return raster(werte) if darstellung == "kacheln" else uebersicht(werte)


__all__ = [
    "GRUPPEN",
    "KACHELN",
    "KachelArt",
    "KachelWert",
    "anzeige",
    "kachel",
    "raster",
    "uebersicht",
    "zahl",
]
