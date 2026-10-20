"""Frontbilder von Anhängen als Kacheln (Ben, 19.10.2026; `docs/plan_anhaenge.md`, Teil C).

Eine waagrechte Reihe quadratischer Kacheln (64 px) unter einer Eintragskarte, im
Tagebuch und im Tag; ein Raster im Verlauf der Übung. Jede Kachel zeigt das Foto bzw.
das Frontbild des Videos, dekodiert klein (``cache_width``) — das Original bleibt
liegen. **Kein Video läuft hier**; ein Tipp öffnet die Ansicht (`views/anhang.py`).
Mehr als `REIHE_MAX` Kacheln: „+n“ als letzte.

Fehlt die Datei (gelöscht, anderes Gerät), steht „fehlt“ in der Kachel statt eines
Ladefehlers. Flet zeigt lokale Dateien über den absoluten Pfad; haken Android oder iOS
dabei (Gerätetest T63), liefert `bildquelle` stattdessen die Bytes des Frontbilds —
diese eine Stelle ist dafür da.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import REIHE_MAX, Anhang, dauer_text

#: Kantenlänge der Kacheln in Reihe und Raster, Dekodierbreite (3× für scharfe Bildschirme)
KACHEL, KACHEL_GROSS = 64, 104
DEKODIEREN = 3


def bildquelle(pfad: Path) -> str | bytes | None:
    """Was `ft.Image` bekommt: den Pfad — oder ``None``, wenn die Datei fehlt."""
    if not pfad.is_file():
        return None
    return str(pfad)


def kachel(
    a: Anhang,
    pfad: Path,
    on_click: Callable[[], Any] | None,
    *,
    groesse: int = KACHEL,
    unterschrift: str | None = None,
) -> ft.Control:
    """Eine Kachel: Bild, beim Video Dreieck und Dauer; darunter optional ein Text."""
    quelle = bildquelle(pfad)
    inhalt: ft.Control
    if quelle is None:
        inhalt = ft.Container(
            width=groesse,
            height=groesse,
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Column(
                spacing=2,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.BROKEN_IMAGE_OUTLINED, size=20, opacity=0.5),
                    ft.Text("fehlt", size=10, opacity=0.6),
                ],
            ),
        )
    else:
        inhalt = ft.Image(
            src=quelle,
            width=groesse,
            height=groesse,
            fit=ft.BoxFit.COVER,
            cache_width=groesse * DEKODIEREN,
            gapless_playback=True,
            error_content=ft.Container(
                width=groesse,
                height=groesse,
                alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                content=ft.Icon(ft.Icons.BROKEN_IMAGE_OUTLINED, size=20, opacity=0.5),
            ),
        )
    ebenen: list[ft.Control] = [inhalt]
    if a.ist_video:
        ebenen.append(
            ft.Container(
                width=groesse,
                height=groesse,
                alignment=ft.Alignment.CENTER,
                content=ft.Icon(
                    ft.Icons.PLAY_CIRCLE_FILL, size=groesse // 2, color=ft.Colors.WHITE, opacity=0.9
                ),
            )
        )
        if dauer := dauer_text(a.dauer_s):
            ebenen.append(
                ft.Container(
                    right=3,
                    bottom=3,
                    padding=ft.Padding.symmetric(horizontal=4, vertical=1),
                    border_radius=6,
                    bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
                    content=ft.Text(dauer, size=10, color=ft.Colors.WHITE),
                )
            )
    bild = ft.Container(
        width=groesse,
        height=groesse,
        border_radius=10,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        ink=on_click is not None,
        on_click=on_click,
        tooltip=a.note or None,
        content=ft.Stack(controls=ebenen, width=groesse, height=groesse),
    )
    if unterschrift is None:
        return bild
    return ft.Column(
        spacing=2,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[bild, ft.Text(unterschrift, size=10, opacity=0.65, width=groesse, max_lines=1)],
    )


def anhang_reihe(
    anhaenge: list[Anhang],
    pfad_von: Callable[[Anhang], Path],
    oeffner: Callable[[Anhang], Callable[[], Any]],
    *,
    mehr: Callable[[], Any] | None = None,
    max_kacheln: int = REIHE_MAX,
) -> ft.Control | None:
    """Die Reihe — ``None`` ohne Anhänge, damit die Karte nichts Leeres zeigt.

    ``pfad_von``: absoluter Pfad des Frontbilds (`AnhangRepo.bild`). ``mehr``: was „+n“
    tut (ohne: öffnet den ersten verborgenen Anhang).
    """
    if not anhaenge:
        return None
    gezeigt = anhaenge if len(anhaenge) <= max_kacheln else anhaenge[: max_kacheln - 1]
    kacheln: list[ft.Control] = [kachel(a, pfad_von(a), oeffner(a)) for a in gezeigt]
    rest = len(anhaenge) - len(gezeigt)
    if rest > 0:
        kacheln.append(
            ft.Container(
                width=KACHEL,
                height=KACHEL,
                border_radius=10,
                alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ink=True,
                on_click=mehr or oeffner(anhaenge[len(gezeigt)]),
                content=ft.Text(f"+{rest}", size=14, weight=ft.FontWeight.W_600, opacity=0.8),
            )
        )
    return ft.Row(spacing=6, wrap=True, run_spacing=6, controls=kacheln)


def bild_laden(pfad: Path) -> bytes | None:
    """Die Bytes eines Frontbilds — Fallback für Plattformen, die Dateipfade nicht zeigen."""
    with contextlib.suppress(OSError):
        return pfad.read_bytes()
    return None


__all__ = ["KACHEL", "KACHEL_GROSS", "anhang_reihe", "bild_laden", "bildquelle", "kachel"]
