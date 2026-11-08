"""Das **Ablaufbild** — der gezeichnete Ablauf eines Plans (Ben, 8.11.2026 spät,
`docs/plan_verzweigungen.md` §4.5 und §8, Skizzen E1/E4/E5).

Eine schieb- und zoombare Fläche (`ft.InteractiveViewer`) über einem `ft.Stack`: unten eine
`ft.Canvas` mit den Kanten, darüber je Knoten ein Bild der Übung (`uebungsbild`) mit Beschriftung,
der Start als dunkle Pille, Fragen als blaue Karte, leere Slots gestrichelt. Die Knoten ordnen
sich selbst (`core.ablauf.layout`): der Start oben, jede Kante eine Ebene tiefer, Abzweige
rechts, Bedarfsübungen ganz rechts. Niemand zieht einen Knoten — gezogen wird nur *in* einen
Slot (`ft.DragTarget`, Reiter „Ablauf“).

Kanten sind Linien mit Pfeil: der Ablauf kräftig, Wege zu Bedarfsübungen gestrichelt, ``◀
zurück`` gepunktet als Bogen nach links, Schleifen als Bogen am Knoten. Am Mittelpunkt sitzt das
**Etikett** (Auslöser, Beschriftung) — es ist der Tipp-Punkt der Kante (Linien treffen am
Handy niemanden). **Vernebeln**: Knoten in ``vernebelt`` und ihre Kanten stehen auf 25 %.

Nur Zeichnen; was ein Tipp bedeutet, sagt der Aufrufer über die Rückrufe.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft
import flet.canvas as cv

from trainingsapp.core import ablauf as ab
from trainingsapp.core.ablauf import Ablauf, Kante
from trainingsapp.core.models import Exercise, PlanItem
from trainingsapp.ui.components.uebungsbild import uebungsbild

#: Maße der Zeichnung (px, vor dem Zoom)
KNOTEN = 64
SPALTE = 132
EBENE = 128
RAND = 24
#: links mehr Platz: Schleifen und „◀ zurück“ zeichnen ihren Bogen links am Knoten
RAND_X = 70
START_H = 36
FRAGE_B = 120
FRAGE_H = 66
#: so durchsichtig wird Vernebeltes
NEBEL = 0.25


@dataclass(frozen=True, slots=True)
class Slot:
    """Ein leerer Platz unter einem Knoten — wartet auf eine Übung aus der Palette."""

    von: str


@dataclass(slots=True)
class Bild:
    """Die gezeichnete Fläche samt dem, was der Aufrufer nachträglich braucht."""

    control: ft.Control
    #: Pixelmitte je Knoten (für Tests und „Pfad abspielen“)
    mitten: dict[str, tuple[float, float]]
    #: die Knoten-Controls je ID (Deckkraft fürs Abspielen)
    knoten: dict[str, ft.Control]


def ablaufbild(
    state: Any,
    ablauf: Ablauf,
    items: Sequence[PlanItem],
    katalog: Mapping[str, Exercise],
    *,
    laufend: str | None = None,
    erledigt: Sequence[str] = (),
    vernebelt: Sequence[str] = (),
    gewaehlt: str | None = None,
    zaehlung: Counter[tuple[str, str]] | None = None,
    slots: Sequence[Slot] = (),
    on_knoten: Callable[[str], Any] | None = None,
    on_knoten_lang: Callable[[str], Any] | None = None,
    on_kante: Callable[[Kante], Any] | None = None,
    on_plus: Callable[[str], Any] | None = None,
    on_slot: Callable[[Slot, str], Any] | None = None,
    on_start: Callable[[], Any] | None = None,
    hoehe: float | None = 420,
) -> Bild:
    """Die Zeichnung. ``laufend`` pulsiert, ``erledigt`` sind grau, ``vernebelt`` auf 25 %;
    ``gewaehlt`` bekommt Rahmen und „+“ (``on_plus``); ``zaehlung`` macht oft gegangene Kanten
    dicker (Auswertung); ``slots`` sind leere Plätze — ``on_slot(slot, exercise_id)`` läuft,
    wenn eine Übung aus der Palette (Draggable mit ``data`` = Übungs-ID) hineinfällt."""
    ids = [it.id for it in items]
    namen = {it.id: katalog[it.exercise_id].name for it in items if it.exercise_id in katalog}
    namen.update({f.id: f.text for f in ablauf.fragen})
    lage = ab.layout(ablauf, ids)
    # Slots hängen unter ihrem Knoten, rechts neben dem, was dort schon liegt
    slot_lage: dict[int, ab.Lage] = {}
    belegt = {(v.spalte, v.ebene) for v in lage.values()}
    for n, slot in enumerate(slots):
        oben = lage.get(slot.von)
        if oben is None:
            continue
        spalte, ebene = oben.spalte, oben.ebene + 1
        while (spalte, ebene) in belegt:
            spalte += 1
        belegt.add((spalte, ebene))
        slot_lage[n] = ab.Lage(spalte, ebene)
    nebel = set(vernebelt)
    fertig = set(erledigt)

    def mitte(lg: ab.Lage) -> tuple[float, float]:
        return (
            RAND_X + lg.spalte * SPALTE + KNOTEN / 2,
            RAND + START_H + 18 + lg.ebene * EBENE + KNOTEN / 2,
        )

    mitten = {k: mitte(v) for k, v in lage.items()}
    spalten = max([v.spalte for v in lage.values()] + [v.spalte for v in slot_lage.values()] + [0])
    ebenen = max([v.ebene for v in lage.values()] + [v.ebene for v in slot_lage.values()] + [0])
    breite = RAND_X + RAND + spalten * SPALTE + max(KNOTEN, FRAGE_B) + 40
    hoch = RAND * 2 + START_H + 18 + (ebenen + 1) * EBENE + 40
    bedarf = set(ab.bedarf(ablauf, ids))

    # -- Kanten --------------------------------------------------------------------------
    formen: list[cv.Shape] = []
    etiketten: list[ft.Control] = []

    def farbe_fuer(k: Kante) -> str:
        if ablauf.frage(k.von) is not None:
            return ft.Colors.SECONDARY
        if k.nach in bedarf or k.zurueck:
            return ft.Colors.TERTIARY
        return ft.Colors.PRIMARY

    def paint(k: Kante, dimm: bool) -> ft.Paint:
        staerke = 2.5
        if zaehlung is not None and (z := zaehlung.get((k.von, k.nach), 0)) > 0:
            staerke = min(2.5 + z * 0.9, 8.0)
        dash: list[int | float] | None = None
        if k.zurueck:
            dash = [2, 6]
        elif k.nach in bedarf:
            dash = [7, 5]
        return ft.Paint(
            color=ft.Colors.with_opacity(NEBEL if dimm else 1.0, farbe_fuer(k)),
            stroke_width=staerke,
            style=ft.PaintingStyle.STROKE,
            stroke_cap=ft.StrokeCap.ROUND,
            stroke_dash_pattern=dash,
        )

    def pfeil(x: float, y: float, winkel: float, farbe: str, dimm: bool) -> cv.Shape:
        """Eine kleine Spitze bei (x, y), die in Richtung ``winkel`` (rad) zeigt."""
        l_ = 9.0
        a1, a2 = winkel + math.radians(150), winkel - math.radians(150)
        return cv.Path(
            [
                cv.Path.MoveTo(x, y),
                cv.Path.LineTo(x + l_ * math.cos(a1), y + l_ * math.sin(a1)),
                cv.Path.LineTo(x + l_ * math.cos(a2), y + l_ * math.sin(a2)),
                cv.Path.Close(),
            ],
            paint=ft.Paint(color=ft.Colors.with_opacity(NEBEL if dimm else 1.0, farbe)),
        )

    def etikett(k: Kante, x: float, y: float, dimm: bool) -> None:
        text = "weiter" if k.ausloeser == ab.FREI and not k.text and not k.pflicht else k.kurztext()
        if k.zurueck:
            text = (
                "◀ zurück"
                + (" · noch einmal" if k.wiederholen else "")
                + (f" · {k.text}" if k.text else "")
            )
        if k.zum_ende:
            text = "Ende" + (f" · {k.text}" if k.text else "")
        if zaehlung is not None and (z := zaehlung.get((k.von, k.nach), 0)) > 0:
            text = f"{text} · {z}×" if text else f"{z}×"
        if not text:
            text = "weiter"
        warm = k.nach in bedarf or k.zurueck
        etiketten.append(
            ft.Container(
                left=x - 6,
                top=y - 11,
                padding=ft.Padding.symmetric(horizontal=7, vertical=3),
                border_radius=9,
                bgcolor=ft.Colors.TERTIARY_CONTAINER if warm else ft.Colors.SURFACE_CONTAINER_HIGH,
                opacity=NEBEL if dimm else 1.0,
                on_click=(lambda _e, kk=k: on_kante(kk)) if on_kante is not None else None,
                tooltip="Kante einstellen" if on_kante is not None else None,
                content=ft.Text(
                    text,
                    size=10,
                    color=ft.Colors.ON_TERTIARY_CONTAINER if warm else None,
                    no_wrap=True,
                ),
                data=("kante", k.von, k.nach),
            )
        )

    for k in ablauf.kanten:
        if k.von not in mitten:
            continue
        dimm = k.von in nebel or k.nach in nebel
        x0, y0 = mitten[k.von]
        farbe = farbe_fuer(k)
        if k.schleife:
            # Bogen links am Knoten
            r = KNOTEN / 2 + 14
            formen.append(
                cv.Path(
                    [
                        cv.Path.MoveTo(x0 - KNOTEN / 2, y0 + 14),
                        cv.Path.CubicTo(
                            x0 - r - 22, y0 + 14, x0 - r - 22, y0 - 14, x0 - KNOTEN / 2, y0 - 14
                        ),
                    ],
                    paint=paint(k, dimm),
                )
            )
            formen.append(pfeil(x0 - KNOTEN / 2, y0 - 14, 0.0, farbe, dimm))
            etikett(k, x0 - r - 40, y0 - 24, dimm)
            continue
        if k.zurueck:
            # gepunkteter Bogen nach links oben — „dorthin, wo ich herkam“
            formen.append(
                cv.Path(
                    [
                        cv.Path.MoveTo(x0 - KNOTEN / 2, y0),
                        cv.Path.CubicTo(x0 - 40, y0, x0 - 40, y0 - 60, x0 - 24, y0 - 70),
                    ],
                    paint=paint(k, dimm),
                )
            )
            formen.append(pfeil(x0 - 24, y0 - 70, -math.radians(60), farbe, dimm))
            etikett(k, x0 - 60, y0 - 50, dimm)
            continue
        if k.zum_ende:
            formen.append(
                cv.Path(
                    [cv.Path.MoveTo(x0, y0 + KNOTEN / 2), cv.Path.LineTo(x0, y0 + KNOTEN / 2 + 36)],
                    paint=paint(k, dimm),
                )
            )
            formen.append(pfeil(x0, y0 + KNOTEN / 2 + 36, math.radians(90), farbe, dimm))
            etikett(k, x0 + 10, y0 + KNOTEN / 2 + 14, dimm)
            continue
        if k.nach not in mitten:
            continue
        x1, y1 = mitten[k.nach]
        if y1 > y0:
            # abwärts: von der Unterkante zur Oberkante, als weiche Kurve
            a = (x0, y0 + KNOTEN / 2)
            b = (x1, y1 - KNOTEN / 2 - 4)
            formen.append(
                cv.Path(
                    [
                        cv.Path.MoveTo(*a),
                        cv.Path.CubicTo(a[0], a[1] + 40, b[0], b[1] - 40, b[0], b[1]),
                    ],
                    paint=paint(k, dimm),
                )
            )
            formen.append(pfeil(b[0], b[1], math.radians(90), farbe, dimm))
            etikett(k, (a[0] + b[0]) / 2 + (14 if x1 >= x0 else -60), (a[1] + b[1]) / 2 - 10, dimm)
        else:
            # aufwärts oder gleiche Ebene: rechts herum zurück
            a = (x0 + KNOTEN / 2, y0)
            b = (x1 + KNOTEN / 2 + 4, y1)
            aus = max(x0, x1) + KNOTEN / 2 + 44
            formen.append(
                cv.Path(
                    [cv.Path.MoveTo(*a), cv.Path.CubicTo(aus, a[1], aus, b[1], b[0], b[1])],
                    paint=paint(k, dimm),
                )
            )
            formen.append(pfeil(b[0], b[1], math.radians(180), farbe, dimm))
            etikett(k, aus - 20, (a[1] + b[1]) / 2 - 10, dimm)

    # Start → Startknoten
    start = ablauf.startknoten(ids)
    if start is not None and start in mitten:
        sx, sy = mitten[start]
        formen.append(
            cv.Path(
                [cv.Path.MoveTo(sx, RAND + START_H), cv.Path.LineTo(sx, sy - KNOTEN / 2 - 4)],
                paint=ft.Paint(
                    color=ft.Colors.PRIMARY, stroke_width=2.5, style=ft.PaintingStyle.STROKE
                ),
            )
        )
        formen.append(pfeil(sx, sy - KNOTEN / 2 - 4, math.radians(90), ft.Colors.PRIMARY, False))

    # -- Knoten -------------------------------------------------------------------------
    knoten_controls: dict[str, ft.Control] = {}
    schichten: list[ft.Control] = [cv.Canvas(shapes=formen, width=breite, height=hoch)]
    nummer = {k: n for n, k in enumerate(ab.hauptpfad(ablauf, ids), start=1)}

    def gesten(knoten: str, inhalt: ft.Control) -> ft.Control:
        if on_knoten is None and on_knoten_lang is None:
            return inhalt
        return ft.GestureDetector(
            content=inhalt,
            on_tap=(lambda _e, kk=knoten: on_knoten(kk)) if on_knoten is not None else None,
            on_long_press=(
                (lambda _e, kk=knoten: on_knoten_lang(kk)) if on_knoten_lang is not None else None
            ),
        )

    if start is not None and start in mitten:
        sx, _sy = mitten[start]
        schichten.append(
            ft.Container(
                left=sx - 36,
                top=RAND,
                width=72,
                height=START_H,
                border_radius=18,
                bgcolor=ft.Colors.ON_SURFACE,
                alignment=ft.Alignment.CENTER,
                on_click=(lambda _e: on_start()) if on_start is not None else None,
                tooltip="Pfad abspielen" if on_start is not None else None,
                content=ft.Text(
                    "Start", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.SURFACE
                ),
                data=("start",),
            )
        )

    for it in items:
        if it.id not in mitten:
            continue
        u = katalog.get(it.exercise_id)
        x, y = mitten[it.id]
        dimm = it.id in nebel
        ist_bedarf = it.id in bedarf
        rahmen = None
        if it.id == gewaehlt:
            rahmen = ft.Border.all(2.5, ft.Colors.PRIMARY)
        elif it.id == laufend:
            rahmen = ft.Border.all(3, ft.Colors.PRIMARY)
        elif ist_bedarf:
            rahmen = ft.Border.all(2, ft.Colors.TERTIARY)
        bild = ft.Container(
            width=KNOTEN,
            height=KNOTEN,
            border_radius=14,
            border=rahmen,
            bgcolor=ft.Colors.TERTIARY_CONTAINER if ist_bedarf else ft.Colors.PRIMARY_CONTAINER,
            alignment=ft.Alignment.CENTER,
            shadow=(
                ft.BoxShadow(
                    blur_radius=14,
                    spread_radius=4,
                    color=ft.Colors.with_opacity(0.25, ft.Colors.PRIMARY),
                )
                if it.id == laufend
                else None
            ),
            content=uebungsbild(
                state,
                u.icon_key if u else None,
                u.image_path if u else None,
                groesse=34,
                color=ft.Colors.TERTIARY if ist_bedarf else ft.Colors.PRIMARY,
            ),
        )
        zeichen: list[ft.Control] = [bild]
        if (nr := nummer.get(it.id)) is not None:
            zeichen.append(
                ft.Container(
                    left=-6,
                    top=-6,
                    width=18,
                    height=18,
                    border_radius=9,
                    bgcolor=ft.Colors.ON_SURFACE,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        str(nr), size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.SURFACE
                    ),
                )
            )
        if it.id in fertig:
            zeichen.append(
                ft.Container(
                    right=-6,
                    top=-6,
                    content=ft.Icon(ft.Icons.CHECK_CIRCLE, size=18, color=ft.Colors.PRIMARY),
                )
            )
        if it.id == gewaehlt and on_plus is not None:
            zeichen.append(
                ft.Container(
                    right=-14,
                    bottom=-14,
                    width=30,
                    height=30,
                    border_radius=15,
                    bgcolor=ft.Colors.PRIMARY,
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda _e, kk=it.id: on_plus(kk),
                    tooltip="Pfad hinzufügen",
                    content=ft.Icon(ft.Icons.ADD, size=20, color=ft.Colors.ON_PRIMARY),
                    data=("plus", it.id),
                )
            )
        unterzeile = []
        if it.beiname:
            unterzeile.append(ft.Text(it.beiname, size=10, opacity=0.65, no_wrap=True))
        if ist_bedarf:
            unterzeile.append(ft.Text("bei Bedarf", size=10, opacity=0.6))
        inhalt = ft.Column(
            spacing=2,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Stack(
                    width=KNOTEN,
                    height=KNOTEN,
                    controls=zeichen,
                    clip_behavior=ft.ClipBehavior.NONE,
                ),
                ft.Text(
                    namen.get(it.id, "?"),
                    size=11,
                    weight=ft.FontWeight.W_600,
                    text_align=ft.TextAlign.CENTER,
                    max_lines=2,
                    width=SPALTE - 16,
                ),
                *unterzeile,
            ],
        )
        knoten = ft.Container(
            left=x - (SPALTE - 16) / 2,
            top=y - KNOTEN / 2,
            width=SPALTE - 16,
            opacity=NEBEL if dimm else (0.55 if it.id in fertig and it.id != laufend else 1.0),
            animate_opacity=ft.Animation(400, ft.AnimationCurve.EASE_IN_OUT),
            content=gesten(it.id, inhalt),
            data=("knoten", it.id),
        )
        knoten_controls[it.id] = knoten
        schichten.append(knoten)

    for f in ablauf.fragen:
        if f.id not in mitten:
            continue
        x, y = mitten[f.id]
        dimm = f.id in nebel
        rahmen = ft.Border.all(2.5 if f.id in (gewaehlt, laufend) else 1.5, ft.Colors.SECONDARY)
        zeichen = [
            ft.Container(
                width=FRAGE_B,
                height=FRAGE_H,
                border_radius=14,
                border=rahmen,
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
                padding=8,
                content=ft.Column(
                    spacing=2,
                    tight=True,
                    controls=[
                        ft.Row(
                            spacing=6,
                            controls=[
                                ft.Icon(ft.Icons.HELP_OUTLINE, size=16, color=ft.Colors.SECONDARY),
                                ft.Text(
                                    f.text,
                                    size=11,
                                    weight=ft.FontWeight.W_600,
                                    color=ft.Colors.ON_SECONDARY_CONTAINER,
                                    expand=True,
                                    max_lines=2,
                                ),
                            ],
                        ),
                        ft.Text(f"Skala {f.min}–{f.max}", size=10, opacity=0.65),
                    ],
                ),
            )
        ]
        if f.id == gewaehlt and on_plus is not None:
            zeichen.append(
                ft.Container(
                    right=-14,
                    bottom=-14,
                    width=30,
                    height=30,
                    border_radius=15,
                    bgcolor=ft.Colors.SECONDARY,
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda _e, kk=f.id: on_plus(kk),
                    tooltip="Pfad hinzufügen",
                    content=ft.Icon(ft.Icons.ADD, size=20, color=ft.Colors.ON_SECONDARY),
                    data=("plus", f.id),
                )
            )
        knoten = ft.Container(
            left=x - FRAGE_B / 2,
            top=y - FRAGE_H / 2,
            width=FRAGE_B,
            opacity=NEBEL if dimm else 1.0,
            animate_opacity=ft.Animation(400, ft.AnimationCurve.EASE_IN_OUT),
            content=gesten(
                f.id,
                ft.Stack(
                    width=FRAGE_B,
                    height=FRAGE_H,
                    controls=zeichen,
                    clip_behavior=ft.ClipBehavior.NONE,
                ),
            ),
            data=("frage", f.id),
        )
        knoten_controls[f.id] = knoten
        schichten.append(knoten)

    # leere Slots: Linie vom Knoten, gestricheltes Feld, Ziel fürs Ziehen
    for n, slot in enumerate(slots):
        lg = slot_lage.get(n)
        if lg is None or slot.von not in mitten:
            continue
        x, y = mitte(lg)
        x0, y0 = mitten[slot.von]
        formen.append(
            cv.Path(
                [
                    cv.Path.MoveTo(x0, y0 + KNOTEN / 2),
                    cv.Path.CubicTo(x0, y0 + 40, x, y - 44, x, y - 24),
                ],
                paint=ft.Paint(
                    color=ft.Colors.OUTLINE,
                    stroke_width=2,
                    style=ft.PaintingStyle.STROKE,
                    stroke_dash_pattern=[4, 4],
                ),
            )
        )

        def fallen(e: ft.DragTargetEvent, s: Slot = slot) -> None:
            if on_slot is None:
                return
            quelle = getattr(e, "src", None)
            exercise_id = getattr(quelle, "data", None)
            if isinstance(exercise_id, str) and exercise_id:
                on_slot(s, exercise_id)

        feld = ft.Container(
            width=KNOTEN,
            height=44,
            border_radius=14,
            border=ft.Border.all(2, ft.Colors.OUTLINE),
            alignment=ft.Alignment.CENTER,
            content=ft.Text("hierher", size=11, opacity=0.6),
        )

        def drueber(_e: object, f: ft.Container = feld, an: bool = True) -> None:
            """Schwebt eine Übung über dem Slot, leuchtet er."""
            f.border = ft.Border.all(
                2.5 if an else 2, ft.Colors.PRIMARY if an else ft.Colors.OUTLINE
            )
            f.bgcolor = ft.Colors.PRIMARY_CONTAINER if an else None
            with contextlib.suppress(Exception):  # noch nicht auf der Seite
                f.update()

        schichten.append(
            ft.Container(
                left=x - KNOTEN / 2,
                top=y - 22,
                content=ft.DragTarget(
                    group="uebung",
                    content=feld,
                    on_accept=fallen,
                    on_will_accept=drueber,
                    on_leave=lambda e, f=feld: drueber(e, f, False),
                ),
                data=("slot", slot.von),
            )
        )
    # Etiketten über allem, damit sie antippbar bleiben
    schichten.extend(etiketten)

    flaeche = ft.Stack(
        width=breite, height=hoch, controls=schichten, clip_behavior=ft.ClipBehavior.NONE
    )
    # Ohne ``hoehe`` füllt die Fläche, was ihr Elternteil ihr gibt (ein Container mit
    # ``expand`` in einer Spalte) — kein ``expand`` hier, das gälte nur in Row/Column
    viewer = ft.InteractiveViewer(
        content=ft.Container(content=flaeche, padding=0),
        min_scale=0.5,
        max_scale=3,
        boundary_margin=ft.Margin.all(200),
        constrained=False,
        height=hoehe,
    )
    return Bild(viewer, mitten, knoten_controls)


async def abspielen(page: Any, bild: Bild, pfad: Sequence[str], schritt_s: float = 0.5) -> None:
    """„Pfad abspielen“ (§8.3): alles wird blass, dann leuchtet der Pfad Knoten für Knoten
    auf; am Ende kehrt jede Deckkraft zurück."""
    alt = {k: c.opacity for k, c in bild.knoten.items()}
    for c in bild.knoten.values():
        c.opacity = 0.3
    with contextlib.suppress(Exception):
        page.update()
    for k in pfad:
        knoten = bild.knoten.get(k)
        if knoten is None:
            continue
        knoten.opacity = 1.0
        with contextlib.suppress(Exception):
            knoten.update()
        await asyncio.sleep(schritt_s)
    await asyncio.sleep(schritt_s)
    for k, c in bild.knoten.items():
        c.opacity = alt.get(k, 1.0)
    with contextlib.suppress(Exception):
        page.update()


__all__ = ["EBENE", "KNOTEN", "NEBEL", "SPALTE", "Bild", "Slot", "ablaufbild", "abspielen"]
