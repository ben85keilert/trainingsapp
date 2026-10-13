"""Kacheln über der Hauptkurve — welche, einstellbar unter Einstellungen → HRV-Messung.

Zwei große Kacheln (Herzfrequenz, RR) stehen nebeneinander, alle übrigen zu
dritt in einem Raster mit gleichem Abstand. Kacheln einer Verlaufskurve tragen
deren Farbe als Streifen — so findet man den Wert in der Kurve wieder — und
rechnen mit demselben Fenster wie die Kurve (`core.hrv_ansicht.Ansicht`).
Gerechnet wird nicht hier: Die Werte kommen fertig herein (`KachelWert`).
"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from trainingsapp.hrv_core.trends import KENNZAHLEN

#: Feste Höhen — ein gleichmäßiges Raster statt Kacheln, die je nach Inhalt springen
HOEHE = 74
HOEHE_GROSS = 90


@dataclass(frozen=True, slots=True)
class KachelArt:
    """Eine wählbare Kachel."""

    titel: str
    #: Große Kachel (halbe Breite) statt eines Drittels
    gross: bool = False
    #: Schlüssel der Verlaufskurve, deren aktuellen Wert sie zeigt
    kennzahl: str | None = None
    erklaerung: str = ""


def _aus_kurve(kennzahl: str) -> KachelArt:
    k = KENNZAHLEN[kennzahl]
    return KachelArt(k.titel, kennzahl=kennzahl, erklaerung=k.erklaerung)


#: Alle Kacheln. Schlüssel bleiben stabil — sie stehen in den Einstellungen.
KACHELN: dict[str, KachelArt] = {
    "hf": KachelArt("Herzfrequenz", gross=True, erklaerung="Zuletzt vom Gerät gemeldet."),
    "rr": KachelArt("RR", gross=True, erklaerung="Letzter Abstand zweier Herzschläge."),
    "artefakte": KachelArt(
        "Artefakte", erklaerung="Markierte Schläge im Puffer bzw. korrigierte in der Messung."
    ),
    "schwankung": KachelArt(
        "Schwankung 60 s",
        erklaerung="Mittlere Spannweite der Herzfrequenz je 10 s — beschreibend, keine Bewertung.",
    ),
    **{k: _aus_kurve(k) for k in ("hf_rr", "mean_rr", "rmssd", "sdnn", "pnnx")},
    **{k: _aus_kurve(k) for k in ("lf_power", "hf_power", "lf_hf", "gipfel")},
    **{k: _aus_kurve(k) for k in ("sd1", "sd2", "dfa_alpha1")},
}

#: Gruppen für die Auswahl in den Einstellungen
GRUPPEN: list[tuple[str, list[str]]] = [
    ("Grundwerte", ["hf", "rr", "artefakte", "schwankung"]),
    ("Zeit", ["hf_rr", "mean_rr", "rmssd", "sdnn", "pnnx"]),
    ("Frequenz", ["lf_power", "hf_power", "lf_hf", "gipfel"]),
    ("Nichtlinear", ["sd1", "sd2", "dfa_alpha1"]),
]


@dataclass(frozen=True, slots=True)
class KachelWert:
    """Was eine Kachel zeigt."""

    titel: str
    wert: str
    einheit: str = ""
    zusatz: str = ""
    farbe: str | None = None
    gross: bool = False


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
                ft.Text(w.zusatz, size=10, opacity=0.6, max_lines=1, visible=bool(w.zusatz)),
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


__all__ = ["GRUPPEN", "KACHELN", "KachelArt", "KachelWert", "kachel", "raster", "zahl"]
