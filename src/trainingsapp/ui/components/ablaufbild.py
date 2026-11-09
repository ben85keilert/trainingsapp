"""Das **Ablaufbild** — der gezeichnete Ablauf eines Plans (Ben, 8.11.2026,
`docs/plan_verzweigungen.md` §4.5 und §8, Skizzen E1/E4/E5; Rückmeldung vom Abend).

Eine schieb- und zoombare Fläche (`ft.InteractiveViewer`) über einem `ft.Stack`: unten eine
`ft.Canvas` mit den Kanten, darüber je Knoten das Bild der Übung (`uebungsbild`) mit Nummer und
Namen, der Start als dunkle Pille (auch Ablagefläche: eine Übung darauf = neuer Start), Fragen als
blaue Karte, leere Slots gestrichelt (`ft.DragTarget`).

**Lagen** (`core.ablauf.Lage`) bekommt das Bild von außen: Der Reiter hält sie fest, bis jemand
„Neu anordnen“ tippt (`core.ablauf.lagen_ergaenzen`) — die Zeichnung springt beim Bearbeiten
nicht. Ein Knoten steht mittig über seinen Kindern (`core.ablauf.layout`). Die **Nummer** am
Knoten ist seine Stelle in der Planliste (Frage 5: nur ein Alias der festen ID).

Kanten sind Linien mit Pfeil: der Ablauf kräftig, Wege zu Bedarfsübungen gestrichelt, ``◀ zurück``
gepunktet als Bogen, Schleifen als Bogen am Knoten. Das **Etikett** (Auslöser, Beschriftung,
Pflicht) sitzt nahe am Ziel, wo die Linien auseinanderlaufen; ein freier Weg ohne Beschriftung hat
keins. **Vernebeln**: Knoten in ``vernebelt`` und ihre Kanten stehen auf 25 %.

Für den Reiter, der die Fläche einmal baut und dann nur ihren Inhalt tauscht (die Ansicht behält
Zoom und Lage): `zeichnung` + `aktualisieren`; für ein Blatt (Workout): `ablaufbild`.
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
from trainingsapp.core.ablauf import Ablauf, Kante, Lage
from trainingsapp.core.models import Exercise, PlanItem
from trainingsapp.ui.components.uebungsbild import uebungsbild

#: Maße der Zeichnung (px, vor dem Zoom)
KNOTEN = 64
SPALTE = 140
EBENE = 156
RAND = 24
#: links mehr Platz: Schleifen und „◀ zurück“ zeichnen ihren Bogen links am Knoten
RAND_X = 76
START_H = 36
FRAGE_B = 120
FRAGE_H = 66
ETIKETT_B = 120
#: der Punkt einer Verbindung und seine Fläche zum Antippen (Ben, 9.11.2026)
PUNKT = 14
GRIFF = 44
#: so durchsichtig wird Vernebeltes
NEBEL = 0.25


@dataclass(frozen=True, slots=True)
class Slot:
    """Ein leerer Platz unter einem Knoten — wartet auf eine Übung aus der Palette."""

    von: str


@dataclass(slots=True)
class Zeichnung:
    """Der Inhalt der Fläche — die Schichten und was der Aufrufer nachträglich braucht."""

    controls: list[ft.Control]
    breite: float
    hoehe: float
    #: Pixelmitte je Knoten (Tests, „Pfad abspielen“)
    mitten: dict[str, tuple[float, float]]
    #: die Knoten-Controls je ID (Deckkraft fürs Abspielen)
    knoten: dict[str, ft.Control]


@dataclass(slots=True)
class Bild:
    """Die schiebbare Fläche — ``control`` ist der `ft.InteractiveViewer`."""

    control: ft.InteractiveViewer
    flaeche: ft.Stack
    mitten: dict[str, tuple[float, float]]
    knoten: dict[str, ft.Control]


def etikett_text(k: Kante, zaehlung: Counter[tuple[str, str]] | None = None) -> str:
    """Was an der Kante steht — leer bei einem freien Weg ohne Beschriftung.

    >>> etikett_text(Kante("a", "b")), etikett_text(Kante("a", "b", ab.SKALA, 7, text="Rücken"))
    ('', 'Skala ≥ 7 · Rücken')
    >>> etikett_text(Kante("a", ab.ZURUECK, wiederholen=True))
    '◀ zurück · noch einmal'
    """
    if k.zurueck:
        teile = ["◀ zurück"] + (["noch einmal"] if k.wiederholen else [])
    elif k.zum_ende:
        teile = ["Ende"]
    else:
        teile = [k.ausloeser_text()] if k.ausloeser != ab.FREI else []
    if k.text:
        teile.append(k.text)
    if k.pflicht:
        teile.append("Pflicht")
    if zaehlung is not None and (z := zaehlung.get((k.von, k.nach), 0)) > 0:
        teile.append(f"{z}×")
    return " · ".join(teile)


def zeichnung(
    state: Any,
    ablauf: Ablauf,
    items: Sequence[PlanItem],
    katalog: Mapping[str, Exercise],
    *,
    lagen: Mapping[str, Lage] | None = None,
    laufend: str | None = None,
    erledigt: Sequence[str] = (),
    vernebelt: Sequence[str] = (),
    gewaehlt: str | None = None,
    zaehlung: Counter[tuple[str, str]] | None = None,
    slots: Sequence[Slot] = (),
    on_knoten: Callable[[str], Any] | None = None,
    on_knoten_lang: Callable[[str], Any] | None = None,
    on_kante: Callable[[Kante], Any] | None = None,
    on_slot: Callable[[Slot, str], Any] | None = None,
    on_start: Callable[[], Any] | None = None,
    on_start_ablegen: Callable[[str], Any] | None = None,
) -> Zeichnung:
    """Die Schichten der Fläche. ``lagen``: wo jeder Knoten liegt (sonst `core.ablauf.layout`);
    ``laufend`` leuchtet, ``erledigt`` ist blass, ``vernebelt`` auf 25 %, ``gewaehlt`` hat einen
    Rahmen; ``zaehlung`` macht oft gegangene Kanten dicker; ``slots`` sind leere Plätze —
    ``on_slot(slot, item_id)`` läuft, wenn eine Planübung aus der Palette (Draggable mit ``data``
    = ID) hineinfällt, ``on_start_ablegen(item_id)`` beim Ablegen auf „Start“."""
    ids = [it.id for it in items]
    nummer = ab.nummern(ids)
    namen = {it.id: katalog[it.exercise_id].name for it in items if it.exercise_id in katalog}
    namen.update({f.id: f.text for f in ablauf.fragen})
    lage = dict(lagen) if lagen is not None else ab.layout(ablauf, ids)
    lage = {k: v for k, v in lage.items() if k in namen}
    slot_lage: dict[int, Lage] = {}
    for n, slot in enumerate(slots):
        oben = lage.get(slot.von)
        if oben is not None:
            belegt = [*lage.values(), *slot_lage.values()]
            slot_lage[n] = ab.freie_lage(belegt, oben.x, oben.ebene + 1)
    alle = [*lage.values(), *slot_lage.values()]
    x_min = min((v.x for v in alle), default=0.0)
    x_max = max((v.x for v in alle), default=0.0)
    ebene_max = max((v.ebene for v in alle), default=0)
    nebel = set(vernebelt)
    fertig = set(erledigt)
    bedarf = set(ab.bedarf(ablauf, ids))

    def mitte(lg: Lage) -> tuple[float, float]:
        return (
            RAND_X + (lg.x - x_min) * SPALTE + KNOTEN / 2,
            RAND + START_H + 22 + lg.ebene * EBENE + KNOTEN / 2,
        )

    mitten = {k: mitte(v) for k, v in lage.items()}
    breite = RAND_X + (x_max - x_min) * SPALTE + max(KNOTEN, FRAGE_B) + RAND + 80
    hoehe = RAND + START_H + 22 + (ebene_max + 1) * EBENE + 40

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

    def etikett(k: Kante, x: float, y: float, dimm: bool, seite: int = 1) -> None:
        """Der Griff einer Verbindung bei (x, y) — ein Punkt in der Mitte zwischen den Ebenen
        (Ben, 9.11.2026: „Pfeile/Verbindungen lassen sich bisher nicht anklicken. Erstelle einen
        Punkt …, damit man diesen gut klicken kann“). Die Fläche ist groß genug für einen Finger.
        Eine Beschriftung steht **nach außen** neben dem Punkt (``seite`` −1: links, 1: rechts),
        damit sich Geschwisterwege nicht überdecken."""
        text = etikett_text(k, zaehlung)
        warm = k.nach in bedarf or k.zurueck
        punkt = ft.Container(
            width=PUNKT,
            height=PUNKT,
            border_radius=PUNKT / 2,
            bgcolor=farbe_fuer(k),
            border=ft.Border.all(2, ft.Colors.SURFACE),
        )
        aufschrift = ft.Text(
            text,
            size=10,
            max_lines=2,
            text_align=ft.TextAlign.CENTER,
            color=ft.Colors.ON_TERTIARY_CONTAINER if warm else None,
        )
        rand = 4  # vom Rand der Blase bis zum Punkt
        if not text:
            left, breite, ausrichtung = x - GRIFF / 2, GRIFF, ft.Alignment.CENTER
            inhalt: ft.Control = punkt
        else:
            links = seite < 0
            inhalt = ft.Container(
                padding=ft.Padding.only(
                    left=8 if links else rand, right=rand if links else 8, top=3, bottom=3
                ),
                border_radius=10,
                bgcolor=ft.Colors.TERTIARY_CONTAINER
                if warm
                else ft.Colors.SURFACE_CONTAINER_HIGHEST,
                content=ft.Row(
                    spacing=4,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[aufschrift, punkt] if links else [punkt, aufschrift],
                ),
            )
            breite = ETIKETT_B
            mitte_punkt = rand + PUNKT / 2  # so weit liegt die Punktmitte vom Rand
            left = x + mitte_punkt - breite if links else x - mitte_punkt
            ausrichtung = ft.Alignment.CENTER_RIGHT if links else ft.Alignment.CENTER_LEFT
        etiketten.append(
            ft.Container(
                left=left,
                top=y - GRIFF / 2,
                width=breite,
                height=GRIFF,
                alignment=ausrichtung,
                opacity=NEBEL if dimm else 1.0,
                on_click=(lambda _e, kk=k: on_kante(kk)) if on_kante is not None else None,
                content=inhalt,
                tooltip=text or "Weg einstellen",
                data=("kante", k.von, k.nach),
            )
        )

    def bezier(
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        p3: tuple[float, float],
        t: float,
    ) -> tuple[float, float]:
        u = 1 - t
        return (
            u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
        )

    for k in ablauf.kanten:
        if k.von not in mitten:
            continue
        dimm = k.von in nebel or k.nach in nebel
        x0, y0 = mitten[k.von]
        farbe = farbe_fuer(k)
        breit = FRAGE_B / 2 if ablauf.frage(k.von) is not None else KNOTEN / 2
        if k.schleife:
            r = KNOTEN / 2 + 14
            formen.append(
                cv.Path(
                    [
                        cv.Path.MoveTo(x0 - breit, y0 + 14),
                        cv.Path.CubicTo(
                            x0 - r - 24, y0 + 14, x0 - r - 24, y0 - 14, x0 - breit, y0 - 14
                        ),
                    ],
                    paint=paint(k, dimm),
                )
            )
            formen.append(pfeil(x0 - breit, y0 - 14, 0.0, farbe, dimm))
            etikett(k, x0 - r - 12, y0 + 34, dimm, -1)
            continue
        if k.zurueck:
            formen.append(
                cv.Path(
                    [
                        cv.Path.MoveTo(x0 - breit, y0),
                        cv.Path.CubicTo(x0 - 44, y0, x0 - 44, y0 - 64, x0 - 26, y0 - 74),
                    ],
                    paint=paint(k, dimm),
                )
            )
            formen.append(pfeil(x0 - 26, y0 - 74, -math.radians(60), farbe, dimm))
            etikett(k, x0 - 40, y0 - 40, dimm, -1)
            continue
        if k.zum_ende:
            unten = y0 + KNOTEN / 2 + 40
            formen.append(
                cv.Path(
                    [cv.Path.MoveTo(x0, y0 + KNOTEN / 2), cv.Path.LineTo(x0, unten)],
                    paint=paint(k, dimm),
                )
            )
            formen.append(pfeil(x0, unten, math.radians(90), farbe, dimm))
            etikett(k, x0, unten + 16, dimm)
            continue
        if k.nach not in mitten:
            continue
        x1, y1 = mitten[k.nach]
        if y1 > y0:
            # abwärts: Unterkante zur Oberkante als weiche Kurve; der Punkt in der Mitte
            a = (x0, y0 + KNOTEN / 2)
            b = (x1, y1 - KNOTEN / 2 - 6)
            c1, c2 = (a[0], a[1] + 50), (b[0], b[1] - 50)
            formen.append(
                cv.Path(
                    [cv.Path.MoveTo(*a), cv.Path.CubicTo(*c1, *c2, *b)],
                    paint=paint(k, dimm),
                )
            )
            formen.append(pfeil(b[0], b[1], math.radians(90), farbe, dimm))
            ex, ey = bezier(a, c1, c2, b, 0.5)  # die Mitte zwischen den Ebenen
            etikett(k, ex, ey, dimm, -1 if x1 < x0 else 1)
        else:
            # aufwärts oder gleiche Ebene: rechts herum zurück
            a = (x0 + breit, y0)
            b = (x1 + KNOTEN / 2 + 6, y1)
            aus = max(x0, x1) + KNOTEN / 2 + 48
            formen.append(
                cv.Path(
                    [cv.Path.MoveTo(*a), cv.Path.CubicTo(aus, a[1], aus, b[1], b[0], b[1])],
                    paint=paint(k, dimm),
                )
            )
            formen.append(pfeil(b[0], b[1], math.radians(180), farbe, dimm))
            etikett(k, aus, (a[1] + b[1]) / 2, dimm)

    # Start → Startknoten
    start = ablauf.startknoten(ids)
    if start is not None and start in mitten:
        sx, sy = mitten[start]
        oben_y = sy - (FRAGE_H if ablauf.frage(start) is not None else KNOTEN) / 2 - 6
        formen.append(
            cv.Path(
                [cv.Path.MoveTo(sx, RAND + START_H), cv.Path.LineTo(sx, oben_y)],
                paint=ft.Paint(
                    color=ft.Colors.PRIMARY, stroke_width=2.5, style=ft.PaintingStyle.STROKE
                ),
            )
        )
        formen.append(pfeil(sx, oben_y, math.radians(90), ft.Colors.PRIMARY, False))
    else:
        sx = RAND_X + KNOTEN / 2

    # Slots: Linie vom Knoten, gestricheltes Feld
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
                    cv.Path.CubicTo(x0, y0 + 50, x, y - 54, x, y - 24),
                ],
                paint=ft.Paint(
                    color=ft.Colors.OUTLINE,
                    stroke_width=2,
                    style=ft.PaintingStyle.STROKE,
                    stroke_dash_pattern=[4, 4],
                ),
            )
        )

    knoten_controls: dict[str, ft.Control] = {}
    schichten: list[ft.Control] = [cv.Canvas(shapes=formen, width=breite, height=hoehe)]

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

    def ablage(inhalt: ft.Control, wenn: Callable[[str], Any] | None) -> ft.Control:
        """Eine Fläche, auf die man eine Planübung aus der Palette ziehen kann."""
        if wenn is None:
            return inhalt

        def fallen(e: ft.DragTargetEvent) -> None:
            item_id = getattr(getattr(e, "src", None), "data", None)
            if isinstance(item_id, str) and item_id:
                wenn(item_id)

        return ft.DragTarget(group="uebung", content=inhalt, on_accept=fallen)

    # Start-Pille: tippen = Pfad abspielen, eine Übung darauf = neuer Start
    schichten.append(
        ft.Container(
            left=sx - 40,
            top=RAND,
            content=ablage(
                ft.Container(
                    width=80,
                    height=START_H,
                    border_radius=18,
                    bgcolor=ft.Colors.ON_SURFACE,
                    alignment=ft.Alignment.CENTER,
                    on_click=(lambda _e: on_start()) if on_start is not None else None,
                    tooltip="Pfad abspielen" if on_start is not None else None,
                    content=ft.Text(
                        "Start", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.SURFACE
                    ),
                ),
                on_start_ablegen,
            ),
            data=("start",),
        )
    )

    def badge(text: str, farbe: str = ft.Colors.ON_SURFACE) -> ft.Control:
        return ft.Container(
            left=-7,
            top=-7,
            width=20,
            height=20,
            border_radius=10,
            bgcolor=farbe,
            alignment=ft.Alignment.CENTER,
            content=ft.Text(text, size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.SURFACE),
        )

    for it in items:
        if it.id not in mitten:
            continue
        u = katalog.get(it.exercise_id)
        x, y = mitten[it.id]
        dimm = it.id in nebel
        ist_bedarf = it.id in bedarf
        rahmen = None
        schatten = None
        if it.id == gewaehlt:
            rahmen = ft.Border.all(3, ft.Colors.PRIMARY)
            schatten = ft.BoxShadow(
                blur_radius=12,
                spread_radius=3,
                color=ft.Colors.with_opacity(0.35, ft.Colors.PRIMARY),
            )
        elif it.id == laufend:
            rahmen = ft.Border.all(3, ft.Colors.PRIMARY)
            schatten = ft.BoxShadow(
                blur_radius=14,
                spread_radius=4,
                color=ft.Colors.with_opacity(0.25, ft.Colors.PRIMARY),
            )
        elif ist_bedarf:
            rahmen = ft.Border.all(2, ft.Colors.TERTIARY)
        zeichen: list[ft.Control] = [
            ft.Container(
                width=KNOTEN,
                height=KNOTEN,
                border_radius=14,
                border=rahmen,
                shadow=schatten,
                bgcolor=ft.Colors.TERTIARY_CONTAINER if ist_bedarf else ft.Colors.PRIMARY_CONTAINER,
                alignment=ft.Alignment.CENTER,
                content=uebungsbild(
                    state,
                    u.icon_key if u else None,
                    u.image_path if u else None,
                    groesse=34,
                    color=ft.Colors.TERTIARY if ist_bedarf else ft.Colors.PRIMARY,
                ),
            ),
            badge(str(nummer.get(it.id, "?"))),
        ]
        if it.id in fertig:
            zeichen.append(
                ft.Container(
                    right=-6,
                    top=-6,
                    content=ft.Icon(ft.Icons.CHECK_CIRCLE, size=18, color=ft.Colors.PRIMARY),
                )
            )
        unterzeile: list[ft.Control] = []
        if it.beiname:
            unterzeile.append(ft.Text(it.beiname, size=10, opacity=0.65, max_lines=1))
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
                    width=SPALTE - 24,
                ),
                *unterzeile,
            ],
        )
        knoten = ft.Container(
            left=x - (SPALTE - 24) / 2,
            top=y - KNOTEN / 2,
            width=SPALTE - 24,
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
        dick = 3 if f.id in (gewaehlt, laufend) else 1.5
        zeichen = [
            ft.Container(
                width=FRAGE_B,
                height=FRAGE_H,
                border_radius=14,
                border=ft.Border.all(dick, ft.Colors.SECONDARY),
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
            ),
        ]
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

    for n, slot in enumerate(slots):
        lg = slot_lage.get(n)
        if lg is None or slot.von not in mitten:
            continue
        x, y = mitte(lg)
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

        def fallen(e: ft.DragTargetEvent, s: Slot = slot) -> None:
            item_id = getattr(getattr(e, "src", None), "data", None)
            if on_slot is not None and isinstance(item_id, str) and item_id:
                on_slot(s, item_id)

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
    schichten.extend(etiketten)  # über allem, damit sie antippbar bleiben
    return Zeichnung(schichten, breite, hoehe, mitten, knoten_controls)


def flaeche_neu(z: Zeichnung) -> ft.Stack:
    return ft.Stack(
        width=z.breite, height=z.hoehe, controls=z.controls, clip_behavior=ft.ClipBehavior.NONE
    )


def ansicht(flaeche: ft.Stack, hoehe: float | None = None) -> ft.InteractiveViewer:
    """Die schieb- und zoombare Fläche — ohne ``hoehe`` so hoch, wie das Elternteil sie lässt."""
    return ft.InteractiveViewer(
        content=ft.Container(content=flaeche, padding=0),
        min_scale=0.4,
        max_scale=3,
        boundary_margin=ft.Margin.all(240),
        constrained=False,
        height=hoehe,
    )


def ablaufbild(
    state: Any,
    ablauf: Ablauf,
    items: Sequence[PlanItem],
    katalog: Mapping[str, Exercise],
    *,
    hoehe: float | None = 420,
    **optionen: Any,
) -> Bild:
    """Bild und Fläche auf einmal (Blatt im Workout) — ``optionen`` wie `zeichnung`."""
    z = zeichnung(state, ablauf, items, katalog, **optionen)
    flaeche = flaeche_neu(z)
    return Bild(ansicht(flaeche, hoehe), flaeche, z.mitten, z.knoten)


def aktualisieren(bild: Bild, z: Zeichnung) -> None:
    """Neuer Inhalt in derselben Fläche — die Ansicht behält Zoom und Lage."""
    bild.flaeche.controls = z.controls
    bild.flaeche.width, bild.flaeche.height = z.breite, z.hoehe
    bild.mitten, bild.knoten = z.mitten, z.knoten
    with contextlib.suppress(Exception):  # noch nicht auf der Seite
        bild.flaeche.update()


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


__all__ = [
    "EBENE",
    "KNOTEN",
    "NEBEL",
    "SPALTE",
    "Bild",
    "Slot",
    "Zeichnung",
    "ablaufbild",
    "abspielen",
    "aktualisieren",
    "ansicht",
    "etikett_text",
    "flaeche_neu",
    "zeichnung",
]
