"""Der Inhalt eines Blatts von unten, der nie unter der Android-Leiste verschwindet.

Ben, 22.10.2026: „wenn das Eingabefenster zu groß ist, verschwindet der untere Teil der
Ansicht hinter die Androidleiste … die transparente Leiste macht den Zugang zum
‚Abbrechen‘ und ‚Speichern‘-Button unmöglich.“

Warum es dazu kam: In Flet 1.0.3 ist eine scrollende Spalte immer so hoch, wie ihr
Elternteil höchstens erlaubt (``ScrollableControl`` erzwingt die Höhe des Elternteils als
Mindesthöhe) — im Blatt also bildschirmhoch. Die Blätter scrollten darum nur, wenn eine
**Schätzung** ihrer Höhe sagte, dass es nicht passt. Lag sie zu niedrig (Sätze, Skalen,
Notiz, Fotos), lief die Spalte über: der untere Teil samt Knöpfen unter die Leiste.

So geht es jetzt (`blatt_spalte`):

- Der Inhalt liegt **immer** in einer scrollenden Spalte — was nicht passt, erreicht man
  durch Scrollen, auch mit offener Tastatur.
- Ihre Höhe ist die **gemessene** Höhe des Inhalts (``on_size_change``), anfangs die
  Schätzung. Flutter kürzt sie auf den Platz, der da ist (``expand_loose``): Ein kurzes
  Blatt bleibt kurz — die Ansicht darunter sichtbar —, ein langes scrollt.
- Die Knöpfe (``fuss``) stehen **fest darunter**, über der Navigationsleiste
  (``SafeArea`` unten).
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Sequence

import flet as ft

#: Anfangshöhe des Inhalts, solange nichts gemessen ist (px)
GESCHAETZT = 360.0


def blatt_spalte(
    inhalt: Sequence[ft.Control] | ft.Column,
    fuss: Sequence[ft.Control] = (),
    *,
    geschaetzt: float = GESCHAETZT,
    abstand: float = 14,
    rand: ft.Padding | None = None,
) -> ft.Control:
    """``content`` für `ft.BottomSheet` (mit ``scrollable=True``): ``inhalt`` scrollt und
    ist so hoch wie gemessen, ``fuss`` steht fest darunter.

    ``inhalt`` darf eine fertige Spalte sein, die der Aufrufer später selbst neu füllt
    (``tight`` und ``STRETCH`` setzt er dann selbst) — gemessen wird sie trotzdem.
    ``geschaetzt``: die Höhe bis zur ersten Messung.
    """
    if isinstance(inhalt, ft.Column):
        innen = inhalt
    else:
        innen = ft.Column(
            tight=True,
            spacing=abstand,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=list(inhalt),
        )
    bereich = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        expand_loose=True,
        height=max(geschaetzt, 1.0),
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[innen],
    )

    def gemessen(e: ft.LayoutSizeChangeEvent) -> None:
        hoehe = float(math.ceil(e.height))
        if hoehe <= 0 or hoehe == bereich.height:
            return
        bereich.height = hoehe
        with contextlib.suppress(Exception):  # schon zu
            bereich.update()

    innen.on_size_change = gemessen
    spalte = ft.Column(
        tight=True,
        spacing=10,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[bereich, *fuss],
    )
    return ft.SafeArea(
        avoid_intrusions_top=False,
        content=ft.Container(
            padding=rand or ft.Padding.only(left=16, right=16, bottom=12),
            content=spalte,
        ),
    )


__all__ = ["GESCHAETZT", "blatt_spalte"]
