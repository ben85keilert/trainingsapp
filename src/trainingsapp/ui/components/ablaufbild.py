"""Das **Ablaufbild** — der gezeichnete Ablauf eines Plans (Ben, 8.11.2026,
`docs/plan_verzweigungen.md` §4.5 und §8, Skizzen E1/E4/E5; Rückmeldung vom Abend).

Eine schieb- und zoombare Fläche (`ft.InteractiveViewer`) über einem `ft.Stack`: unten eine
`ft.Canvas` mit den Kanten, darüber je Knoten das Bild der Übung (`uebungsbild`) mit Nummer und
Namen, der Start als dunkle Pille (auch Ablagefläche: eine Übung darauf = neuer Start), Fragen als
blaue Karte.

**Lagen** (`core.ablauf.Lage`) bekommt das Bild von außen: Der Reiter hält sie fest, bis jemand
„Neu anordnen“ tippt (`core.ablauf.lagen_ergaenzen`) — die Zeichnung springt beim Bearbeiten
nicht. Ein Knoten steht mittig über seinen Kindern (`core.ablauf.layout`). Die **Nummer** am
Knoten ist seine Stelle in der Planliste (Frage 5: nur ein Alias der festen ID).

Die Wege verlassen eine Übung **wie bei einem Nerv** (Ben, 10.11.2026): ein kurzer Stamm nach
unten, dann der **Abzweig** — ein Knoten zum Antippen (``on_abzweig``: alle Wege dieser Übung) —,
von dort die einzelnen Wege, jeder mit seinem **Griff** (Punkt und Etikett mit Auslöser,
Beschriftung, Pflicht; ``on_kante``: nur dieser Weg). **Ist der Weg eindeutig** — die Übung hat
genau einen —, steht zwischen den zwei Übungen **nur ein Punkt**, sein Griff (Ben, 16.11.2026):
Er meldet ``on_kante`` mit seiner Kante (wer nur ``on_abzweig`` gibt, bekommt den Knoten). Der
Ablauf kräftig, Wege zu Bedarfsübungen gestrichelt, ``◀ zurück`` gepunktet; Rückwege laufen in
Gassen zwischen den Spalten. Wo was liegt, rechnet `core.ablauf_geometrie` — hier wird nur
gezeichnet. **Vernebeln**: Knoten in ``vernebelt`` und ihre Kanten stehen auf 25 %.

**Im Bild bedienen** (Ben, 16.11.2026: „Alles, was sich auslagern lässt vom Routingmenü in die
Grafik, wird ausgelagert“) — alles nur, wenn der Aufrufer den Rückruf gibt; ohne Rückrufe sieht
das Bild aus wie zuvor und nichts lässt sich ziehen (Workout, Workout-Eintrag):

- ``on_verbinden(von, nach)``: Jeder Knoten hat **seinen Punkt** (`Geometrie.punkte` — der
  Abzweig, der eine Griff oder, ohne Weg, ein kleiner Ring unter der Übung), „Start“ ebenso.
  Der Punkt lässt sich **ziehen** (`ft.Draggable`, Gruppe `GRUPPE_WEG`) und auf einen Knoten
  fallen lassen — auch auf den eigenen; ``von`` ist die ID des Knotens oder `START`, ``nach``
  die ID des Knotens, auf den er fiel. Für `core.ablauf.ENDE` und `ZURUECK` gibt es die
  Ziele am Rand des Bildes (`ziele`, `mit_zielen`), sichtbar nur, während gezogen wird
  (``on_ziehen``); was ins Leere fällt, fängt `fangnetz` — Flet meldet keinen Abbruch.
- ``on_kachel_auf(knoten, wert)``: Eine Kachel der Leiste (Gruppe `GRUPPE_KACHEL`) fällt auf
  einen Knoten; ``wert`` ist das ``data`` ihres Draggable.
- ``menue``: ein **Menü an einem Knoten** (`Menue`) als Karte in der Fläche, dahinter ein
  Schirm, der den schließenden Tipp fängt — kein Flutter-Menü: Die reichen den Tipp, der sie
  schließt, an das Darunter weiter. Geöffnet wird es vom Aufrufer, z. B. auf
  ``on_knoten_lang``.

**Ohne Start** (der Ablauf ist geleert, `core.ablauf.Ablauf.ohne_start`) steht „Start“ über
einem **leeren Platz** (`core.ablauf.startplatz`) — im Reiter eine Ablage: Was dort
hineinfällt, wird der Start (``on_start_ablegen``).

Für den Reiter, der die Fläche einmal baut und dann nur ihren Inhalt tauscht (die Ansicht behält
Zoom und Lage): `zeichnung` + `aktualisieren`; für ein Blatt (Workout): `ablaufbild`.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft
import flet.canvas as cv

from trainingsapp.core import ablauf as ab
from trainingsapp.core import ablauf_geometrie as geo
from trainingsapp.core.ablauf import Ablauf, Kante, Lage
from trainingsapp.core.ablauf_geometrie import (
    EBENE,
    FRAGE_B,
    FRAGE_H,
    KNOTEN,
    NAME_B,
    RAND,
    RAND_X,
    SPALTE,
    START_H,
)
from trainingsapp.core.models import Exercise, PlanItem
from trainingsapp.ui.components.layout import ohne_auto_update
from trainingsapp.ui.components.uebungsbild import uebungsbild

#: größte Breite eines Etiketts neben seinem Griff
ETIKETT_B = 108
#: der Punkt einer Verbindung, der Abzweig einer Übung und ihre Fläche zum Antippen
PUNKT = 14
ABZWEIG = 20
GRIFF = 44
#: der Hof um den Punkt eines gewählten Wegs — und unter dem Finger beim Ziehen
HOF = 30
#: Höhe der Fläche am Punkt von „Start“ — flacher als `GRIFF`: darunter beginnt die Startübung
START_GRIFF = 36
#: so durchsichtig wird Vernebeltes
NEBEL = 0.25
#: Gruppen beim Ziehen: die Kacheln der Leiste (Übungen, „Frage“) und die Punkte der Knoten —
#: eine Ablage kennt nur eine Gruppe, darum nimmt ein Knoten beide verschachtelt an
GRUPPE_KACHEL = "uebung"
GRUPPE_WEG = "weg"
#: „Start“ als Herkunft in ``on_verbinden`` (kein Knoten)
START = ab.VOM_START
#: Breite der Menükarte an einem Knoten und Höhe einer Zeile darin
MENUE_B = 216
MENUE_ZEILE = 42


@dataclass(frozen=True, slots=True)
class Eintrag:
    """Eine Zeile im Menü an einem Knoten — ``aktion`` darf auch eine Koroutine liefern."""

    text: str
    aktion: Callable[[], Any]
    symbol: ft.IconData | None = None
    #: rot (herausnehmen, löschen)
    gefahr: bool = False


@dataclass(frozen=True, slots=True)
class Menue:
    """Das Menü an einem Knoten (Ben, 16.11.2026: „gedrückt halten von Kachel um ein Menü zu
    öffnen“): ``knoten`` trägt es, ``schliessen`` läuft beim Tipp daneben. Die Aktionen
    schließen es selbst — die Zeichnung hält nichts. ``nach_oben``: Die Karte steht über dem
    Knoten statt darunter — für eine Übung unten im sichtbaren Ausschnitt, deren Menü sonst
    unter dem Rand verschwände (``on_lang_ort`` der Zeichnung sagt, wo der Finger lag)."""

    knoten: str
    eintraege: Sequence[Eintrag]
    schliessen: Callable[[], Any]
    nach_oben: bool = False


@dataclass(slots=True)
class Ziele:
    """„Ende“ und „◀ zurück“ als Ablagen am unteren Rand des Bildes (`ziele`) — sichtbar nur,
    während ein Punkt gezogen wird."""

    control: ft.Container

    def zeigen(self, an: bool) -> None:
        """Ein- oder ausblenden — als ``on_ziehen`` der Zeichnung."""
        if bool(self.control.visible) == an:
            return
        self.control.visible = an
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            self.control.update()


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

    Auch am Stummel steht, wann der Weg gilt — an einer Frage sieht man sonst nicht, welche
    Antwort zum Ende führt (Ben, 17.11.2026):

    >>> etikett_text(Kante("f", ab.ENDE, ab.ANTWORT, antworten=("Nein",)))
    'Ende · „Nein“'
    """
    wann = [k.ausloeser_text()] if k.ausloeser != ab.FREI else []
    if k.zurueck:
        teile = ["◀ zurück"] + (["noch einmal"] if k.wiederholen else []) + wann
    elif k.zum_ende:
        teile = ["Ende", *wann]
    else:
        teile = wann
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
    weg_gewaehlt: tuple[str, str] | None = None,
    zaehlung: Counter[tuple[str, str]] | None = None,
    menue: Menue | None = None,
    on_knoten: Callable[[str], Any] | None = None,
    on_knoten_lang: Callable[[str], Any] | None = None,
    on_lang_ort: Callable[[float], Any] | None = None,
    on_kante: Callable[[Kante], Any] | None = None,
    on_abzweig: Callable[[str], Any] | None = None,
    on_start: Callable[[], Any] | None = None,
    on_start_ablegen: Callable[[str], Any] | None = None,
    on_verbinden: Callable[[str, str], Any] | None = None,
    on_kachel_auf: Callable[[str, str], Any] | None = None,
    on_ziehen: Callable[[bool], Any] | None = None,
) -> Zeichnung:
    """Die Schichten der Fläche. ``lagen``: wo jeder Knoten liegt (sonst `core.ablauf.layout`);
    ``laufend`` leuchtet, ``erledigt`` ist blass, ``vernebelt`` auf 25 %, ``gewaehlt`` hat einen
    Rahmen, ``weg_gewaehlt`` (von, nach) einen Hof um seinen Griff; ``zaehlung`` macht oft
    gegangene Kanten dicker.

    Antippen: ``on_knoten(knoten)``, ``on_knoten_lang(knoten)`` (gedrückt halten; kurz davor
    meldet ``on_lang_ort(anteil)``, wo der Finger auf der Seite liegt — 0 oben, 1 unten),
    ``on_kante(kante)`` — der Griff eines Wegs, auch der eine Punkt eines eindeutigen Wegs —,
    ``on_abzweig(knoten)`` — der Abzweig einer Übung (alle ihre Wege) und der Punkt einer Übung
    **ohne** Weg; wer nur ``on_abzweig`` gibt, bekommt auch den einen Punkt so gemeldet.
    ``on_start()``: die Pille „Start“.

    Ziehen (jedes nur mit seinem Rückruf, sonst lässt sich nichts ziehen und nichts ablegen):

    - ``on_start_ablegen(wert)``: eine Kachel der Leiste fällt auf „Start“ oder den leeren
      Platz darunter (``wert`` = ``data`` ihres Draggable; im Reiter „Ablauf“ die ID der
      **Übung** — welche Planübung daraus wird, entscheidet der Reiter);
    - ``on_kachel_auf(knoten, wert)``: eine Kachel fällt auf einen Knoten im Bild;
    - ``on_verbinden(von, nach)``: der Punkt von ``von`` (ID eines Knotens oder `START`) fällt
      auf den Knoten ``nach`` — ``von == nach`` heißt: auf sich selbst. „Ende“ und „◀ zurück“
      melden die Ziele am Rand (`ziele`) mit `core.ablauf.ENDE` bzw. `ZURUECK` als ``nach``;
    - ``on_ziehen(an)``: ein Punkt wird gezogen (``True``) bzw. ist abgelegt (``False``) —
      dafür gedacht, die Ziele ein- und auszublenden (`Ziele.zeigen`). Fällt der Punkt ins
      Leere, kommt **kein** ``False`` (`fangnetz`).

    ``menue``: das Menü an einem Knoten (`Menue`) — Schirm über allem, der Knoten und die Karte
    darüber."""
    ids = [it.id for it in items]
    nummer = ab.nummern(ids)
    namen = {it.id: katalog[it.exercise_id].name for it in items if it.exercise_id in katalog}
    namen.update({f.id: f.text for f in ablauf.fragen})
    lage = dict(lagen) if lagen is not None else ab.layout(ablauf, ids)
    lage = {k: v for k, v in lage.items() if k in namen}
    nebel = set(vernebelt)
    fertig = set(erledigt)
    bedarf = set(ab.bedarf(ablauf, ids))
    start = ablauf.startknoten(ids)
    kein_start = start is None
    if start is not None and start not in lage:
        start = None  # es gibt ihn, aber er lässt sich nicht zeichnen
    # Ohne Start: „Start“ und der leere Platz darunter stehen links von allem (Ben, 16.11.2026)
    platz = ab.startplatz(lage.values()) if start is None else None

    def text_hoehe(it: PlanItem) -> float:
        """So hoch ist die Beschriftung unter dem Bild etwa — der Stamm beginnt darunter."""
        zeilen = 2 if len(namen.get(it.id, "")) > 17 else 1
        return 4 + zeilen * 15 + (14 if it.beiname else 0) + (14 if it.id in bedarf else 0)

    g = geo.geometrie(
        ablauf,
        lage,
        beschriftung={it.id: text_hoehe(it) for it in items},
        weitere=[platz] if platz is not None else [],
    )
    mitten = g.mitten
    breite, hoehe = g.breite, g.hoehe

    def mitte(lg: Lage) -> tuple[float, float]:
        return geo.ort(lg, g.x_min)

    formen: list[cv.Shape] = []
    etiketten: list[ft.Control] = []
    hoefe: list[ft.Control] = []

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

    def kante_tippen(k: Kante) -> tuple[Callable[[Any], Any] | None, str]:
        """Was der Griff eines Wegs beim Antippen tut, und der Zusatz für den Hinweis: seine
        Kante melden — der eine Punkt eines eindeutigen Wegs meldet den Knoten, wenn der
        Aufrufer nur ``on_abzweig`` kennt."""
        if on_kante is not None:
            return (lambda _e, kk=k: on_kante(kk)), " — diesen Weg einstellen"
        if k.von not in g.abzweige and on_abzweig is not None:
            return (lambda _e, kk=k.von: on_abzweig(kk)), " — Wege einstellen"
        return None, ""

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
        hoch: float = GRIFF
        if not text:
            left, breite, ausrichtung = x - GRIFF / 2, GRIFF, ft.Alignment.CENTER
            inhalt: ft.Control = punkt
        elif seite == 0:
            # Stummel („◀ zurück“, „Ende“): der Punkt, die Beschriftung mittig darunter
            breite, hoch = 88, GRIFF + 26
            left, ausrichtung = x - breite / 2, ft.Alignment.TOP_CENTER
            inhalt = ft.Column(
                spacing=2,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(height=(GRIFF - PUNKT) / 2 - 2),
                    punkt,
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                        border_radius=10,
                        bgcolor=ft.Colors.TERTIARY_CONTAINER
                        if warm
                        else ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        content=aufschrift,
                    ),
                ],
            )
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
        tippen, hinweis = kante_tippen(k)
        if weg_gewaehlt == (k.von, k.nach):
            # der gewählte Weg: ein Hof um seinen Punkt (unter dem Griff, verschiebt nichts)
            hoefe.append(
                ft.Container(
                    left=x - HOF / 2,
                    top=y - HOF / 2,
                    width=HOF,
                    height=HOF,
                    border_radius=HOF / 2,
                    bgcolor=ft.Colors.with_opacity(0.22, farbe_fuer(k)),
                    border=ft.Border.all(2, farbe_fuer(k)),
                    data=("weg_gewaehlt", k.von, k.nach),
                )
            )
        etiketten.append(
            ft.Container(
                left=left,
                top=y - GRIFF / 2,
                width=breite,
                height=hoch,
                alignment=ausrichtung,
                opacity=NEBEL if dimm else 1.0,
                on_click=tippen,
                content=inhalt,
                tooltip=(text or "Weg") + hinweis,
                data=("kante", k.von, k.nach),
            )
        )

    def linie(kurven: Sequence[geo.Kurve], farbe_: ft.Paint) -> cv.Shape:
        teile: list[Any] = [cv.Path.MoveTo(*kurven[0].p0)]
        teile.extend(cv.Path.CubicTo(*c.p1, *c.p2, *c.p3) for c in kurven)
        return cv.Path(teile, paint=farbe_)

    # Stamm und Abzweig: alle Wege einer Übung verlassen sie an einem Punkt — der Abzweig
    # steht nur, wo mehrere Wege abgehen (sonst ist der Griff des einen Wegs der einzige Punkt)
    abzweig_punkte: list[ft.Control] = []
    for knoten_id, (oben_p, unten_p) in g.staemme.items():
        dimm = knoten_id in nebel
        farbe = ft.Colors.SECONDARY if ablauf.frage(knoten_id) is not None else ft.Colors.PRIMARY
        formen.append(
            cv.Path(
                [cv.Path.MoveTo(*oben_p), cv.Path.LineTo(*unten_p)],
                paint=ft.Paint(
                    color=ft.Colors.with_opacity(NEBEL if dimm else 1.0, farbe),
                    stroke_width=3,
                    style=ft.PaintingStyle.STROKE,
                    stroke_cap=ft.StrokeCap.ROUND,
                ),
            )
        )
        if knoten_id not in g.abzweige:
            continue
        anzahl = len(ablauf.von(knoten_id))
        abzweig_punkte.append(
            ft.Container(
                left=unten_p[0] - GRIFF / 2,
                top=unten_p[1] - GRIFF / 2,
                width=GRIFF,
                height=GRIFF,
                alignment=ft.Alignment.CENTER,
                opacity=NEBEL if dimm else 1.0,
                on_click=(
                    (lambda _e, kk=knoten_id: on_abzweig(kk)) if on_abzweig is not None else None
                ),
                tooltip=f"{anzahl} Wege" + (" — alle einstellen" if on_abzweig is not None else ""),
                data=("abzweig", knoten_id),
                content=ft.Container(
                    width=ABZWEIG,
                    height=ABZWEIG,
                    border_radius=ABZWEIG / 2,
                    bgcolor=farbe,
                    border=ft.Border.all(3, ft.Colors.SURFACE),
                ),
            )
        )

    for w in g.wege:
        k = w.kante
        dimm = k.von in nebel or k.nach in nebel
        formen.append(linie(w.kurven, paint(k, dimm)))
        if w.spitze is not None:
            formen.append(pfeil(*w.spitze, farbe_fuer(k), dimm))
        etikett(k, *w.griff, dimm, w.seite)

    # Start → Startknoten
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
    elif platz is not None:
        # kein Start: „Start“ über dem leeren Platz, gestrichelt verbunden
        sx, sy = mitte(platz)
        if kein_start and on_start_ablegen is not None:
            formen.append(
                cv.Path(
                    [cv.Path.MoveTo(sx, RAND + START_H), cv.Path.LineTo(sx, sy - 24)],
                    paint=ft.Paint(
                        color=ft.Colors.OUTLINE,
                        stroke_width=2,
                        style=ft.PaintingStyle.STROKE,
                        stroke_dash_pattern=[4, 4],
                    ),
                )
            )
    else:
        sx = RAND_X + KNOTEN / 2

    knoten_controls: dict[str, ft.Control] = {}
    leinwand = cv.Canvas(shapes=formen, width=breite, height=hoehe)
    schichten: list[ft.Control] = [leinwand]

    def wert_von(e: Any) -> str:
        """Was das abgelegte Draggable trägt (sein ``data``) — leer, wenn es nichts ist."""
        wert = getattr(getattr(e, "src", None), "data", None)
        return wert if isinstance(wert, str) else ""

    def leuchten(form: ft.Container) -> tuple[Callable[[Any], None], Callable[[Any], None]]:
        """Schwebt etwas Passendes über einer Ablage, bekommt ihre Form einen kräftigen Rand —
        der Finger verdeckt sonst, ob man getroffen hat. Zurück: was beim Hineinkommen und
        beim Verlassen läuft."""
        vorher = form.border

        def setzen(rand: ft.Border | None) -> None:
            ohne_auto_update()  # kommt beim Ziehen dauernd: nur diese Form neu zeichnen
            form.border = rand
            with contextlib.suppress(Exception):  # noch nicht auf der Seite
                form.update()

        def hinein(e: Any) -> None:
            if getattr(e, "accept", True):  # die andere Gruppe meldet sich auch — abgelehnt
                setzen(ft.Border.all(3, ft.Colors.TERTIARY))

        return hinein, lambda _e: setzen(vorher)

    def lang_ort(e: Any) -> None:
        """Wo der Finger beim Gedrückthalten liegt, als Anteil der Seitenhöhe — der Aufrufer
        entscheidet damit, ob das Menü nach oben aufgeht (`Menue.nach_oben`)."""
        y = getattr(getattr(e, "global_position", None), "y", None)
        hoch = getattr(getattr(e, "page", None), "height", None)
        if on_lang_ort is not None and isinstance(y, int | float) and hoch:
            ohne_auto_update()  # gezeichnet wird gleich danach, mit dem Menü
            on_lang_ort(float(y) / float(hoch))

    def gesten(knoten: str, inhalt: ft.Control, form: ft.Container) -> ft.Control:
        """Tippen und Gedrückthalten auf einem Knoten — und, mit den Rückrufen dazu, der Knoten
        als Ablage: für einen Punkt (ein Weg hierher) und für eine Kachel der Leiste (eine neue
        Übung dahinter). Zwei Ablagen ineinander, weil jede nur eine Gruppe annimmt."""
        if on_knoten is not None or on_knoten_lang is not None:
            inhalt = ft.GestureDetector(
                content=inhalt,
                on_tap=(lambda _e, kk=knoten: on_knoten(kk)) if on_knoten is not None else None,
                on_long_press=(
                    (lambda _e, kk=knoten: on_knoten_lang(kk))
                    if on_knoten_lang is not None
                    else None
                ),
                # dasselbe Gedrückthalten, mit Ort — Flutter meldet es vor ``on_long_press``
                on_long_press_start=(
                    lang_ort if on_knoten_lang is not None and on_lang_ort is not None else None
                ),
            )
        if on_verbinden is None and on_kachel_auf is None:
            return inhalt
        hinein, hinaus = leuchten(form)
        if on_verbinden is not None:

            def punkt_faellt(e: Any, kk: str = knoten) -> None:
                if (von := wert_von(e)) and on_verbinden is not None:
                    on_verbinden(von, kk)

            inhalt = ft.DragTarget(
                group=GRUPPE_WEG,
                content=inhalt,
                on_accept=punkt_faellt,
                on_will_accept=hinein,
                on_leave=hinaus,
            )
        if on_kachel_auf is not None:

            def kachel_faellt(e: Any, kk: str = knoten) -> None:
                if (wert := wert_von(e)) and on_kachel_auf is not None:
                    on_kachel_auf(kk, wert)

            inhalt = ft.DragTarget(
                group=GRUPPE_KACHEL,
                content=inhalt,
                on_accept=kachel_faellt,
                on_will_accept=hinein,
                on_leave=hinaus,
            )
        return inhalt

    def ablage(inhalt: ft.Control, wenn: Callable[[str], Any] | None) -> ft.Control:
        """Eine Fläche, auf die man eine Kachel aus der Palette ziehen kann."""
        if wenn is None:
            return inhalt

        def fallen(e: ft.DragTargetEvent) -> None:
            if wert := wert_von(e):
                wenn(wert)

        return ft.DragTarget(group=GRUPPE_KACHEL, content=inhalt, on_accept=fallen)

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
        form = ft.Container(
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
        )
        zeichen: list[ft.Control] = [form, badge(str(nummer.get(it.id, "?")))]
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
                    width=NAME_B,
                ),
                *unterzeile,
            ],
        )
        knoten = ft.Container(
            left=x - NAME_B / 2,
            top=y - KNOTEN / 2,
            width=NAME_B,
            opacity=NEBEL if dimm else (0.55 if it.id in fertig and it.id != laufend else 1.0),
            animate_opacity=ft.Animation(400, ft.AnimationCurve.EASE_IN_OUT),
            content=gesten(it.id, inhalt, form),
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
        form = ft.Container(
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
                    ft.Text(
                        f.kurz(),
                        size=10,
                        opacity=0.65,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
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
                    controls=[form],
                    clip_behavior=ft.ClipBehavior.NONE,
                ),
                form,
            ),
            data=("frage", f.id),
        )
        knoten_controls[f.id] = knoten
        schichten.append(knoten)

    def ablagefeld(x: float, y: float, wenn: Callable[[str], Any], daten: tuple[str, ...]) -> None:
        """Ein leerer Platz bei (x, y): gestrichelt, „hierher“ — fällt eine Kachel aus der
        Palette hinein, läuft ``wenn`` mit ihrem Wert."""
        feld = ft.Container(
            width=KNOTEN,
            height=44,
            border_radius=14,
            border=ft.Border.all(2, ft.Colors.OUTLINE),
            alignment=ft.Alignment.CENTER,
            content=ft.Text("hierher", size=11, opacity=0.6),
        )

        def drueber(_e: object, an: bool = True) -> None:
            """Schwebt eine Übung über dem Platz, leuchtet er."""
            feld.border = ft.Border.all(
                2.5 if an else 2, ft.Colors.PRIMARY if an else ft.Colors.OUTLINE
            )
            feld.bgcolor = ft.Colors.PRIMARY_CONTAINER if an else None
            with contextlib.suppress(Exception):  # noch nicht auf der Seite
                feld.update()

        def fallen(e: ft.DragTargetEvent) -> None:
            if wert := wert_von(e):
                wenn(wert)

        schichten.append(
            ft.Container(
                left=x - KNOTEN / 2,
                top=y - 22,
                content=ft.DragTarget(
                    group=GRUPPE_KACHEL,
                    content=feld,
                    on_accept=fallen,
                    on_will_accept=drueber,
                    on_leave=lambda e: drueber(e, False),
                ),
                data=daten,
            )
        )

    # Der leere Platz unter „Start“ — nur, wo man etwas hineinlegen kann (Reiter „Ablauf“)
    if kein_start and platz is not None and on_start_ablegen is not None:
        ablagefeld(*mitte(platz), on_start_ablegen, ("startplatz",))
    # über allem, damit sie antippbar bleiben: erst die Abzweige, darüber die Griffe der Wege
    schichten.extend(abzweig_punkte)
    schichten.extend(hoefe)
    schichten.extend(etiketten)

    # -- Im Bild bedienen: der Punkt jedes Knotens zum Ziehen ---------------------------------
    def zieht(an: bool) -> Callable[[Any], None] | None:
        melden = on_ziehen
        if melden is None:
            return None
        return lambda _e: melden(an)

    def ziehpunkt(
        von: str,
        x: float,
        y: float,
        *,
        tippen: Callable[[Any], Any] | None,
        zeichen: ft.Control | None = None,
        hoch: float = GRIFF,
        dimm: bool = False,
    ) -> ft.Control:
        """Die Fläche über dem Punkt eines Knotens: ziehen = verbinden, tippen wie der Punkt
        darunter. ``zeichen``: was dort zu sehen ist, wenn sonst nichts dort steht (der Ring
        einer Übung ohne Weg, der Punkt von „Start“). Die Fläche ist durchsichtig, aber
        gefüllt — sonst träfe der Finger nur das Zeichen. Kein Tooltip: Sein Gedrückthalten
        gewönne gegen das Ziehen, wer den Finger erst ruhen lässt, zöge dann nichts."""
        return ft.Container(
            left=x - GRIFF / 2,
            top=y - hoch / 2,
            opacity=NEBEL if dimm else 1.0,
            data=("punkt", von),
            content=ft.Draggable(
                group=GRUPPE_WEG,
                data=von,
                on_drag_start=zieht(True),
                on_drag_complete=zieht(False),
                content=ft.Container(
                    width=GRIFF,
                    height=hoch,
                    bgcolor=ft.Colors.TRANSPARENT,
                    alignment=ft.Alignment.CENTER,
                    on_click=tippen,
                    content=zeichen,
                ),
                # unter dem Finger: ein Hof, der um die Fingerkuppe herum sichtbar bleibt
                content_feedback=ft.Container(
                    width=GRIFF,
                    height=hoch,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Container(
                        width=HOF,
                        height=HOF,
                        border_radius=HOF / 2,
                        bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.TERTIARY),
                        border=ft.Border.all(2, ft.Colors.TERTIARY),
                        alignment=ft.Alignment.CENTER,
                        content=ft.Container(
                            width=PUNKT,
                            height=PUNKT,
                            border_radius=PUNKT / 2,
                            bgcolor=ft.Colors.TERTIARY,
                        ),
                    ),
                ),
            ),
        )

    if on_verbinden is not None:
        einzige = {w.kante.von: w for w in g.wege if w.kante.von not in g.abzweige}
        for knoten_id, (x, y) in g.punkte.items():
            ist_frage = ablauf.frage(knoten_id) is not None
            # antippen wie das, was dort schon steht: der Abzweig (alle Wege) oder der eine
            # Griff (dieser Weg) — ohne Weg die Wege der Übung („+ Weg“)
            tippen: Callable[[Any], Any] | None = None
            ring: ft.Control | None = None
            # Der Punkt liegt auf dem Griff des einen Wegs — oder, bei einem Rückweg, für
            # sich unter dem Knoten (`Geometrie.punkte`): dort ist er ein Ring wie ohne Weg
            einziger = einzige.get(knoten_id)
            am_griff = einziger is not None and einziger.griff == (x, y)
            if einziger is not None and am_griff:
                tippen, _ = kante_tippen(einziger.kante)
            elif on_abzweig is not None:
                tippen = lambda _e, kk=knoten_id: on_abzweig(kk)  # noqa: E731
            if knoten_id not in g.abzweige and not am_griff:
                # ohne Weg — oder mit einem Rückweg, dessen Griff woanders liegt: ein kleiner,
                # hohler Punkt unter der Übung (Ben, 16.11.2026; 17.11.2026)
                ring = ft.Container(
                    width=PUNKT,
                    height=PUNKT,
                    border_radius=PUNKT / 2,
                    bgcolor=ft.Colors.SURFACE,
                    border=ft.Border.all(
                        2.5, ft.Colors.SECONDARY if ist_frage else ft.Colors.PRIMARY
                    ),
                )
            schichten.append(
                ziehpunkt(knoten_id, x, y, tippen=tippen, zeichen=ring, dimm=knoten_id in nebel)
            )
        if mitten:
            # „Start“ hat denselben Punkt: auf eine Übung gezogen ist sie der Start. Seine
            # Fläche ist flacher — darunter beginnt gleich die Startübung
            schichten.append(
                ziehpunkt(
                    START,
                    *geo.start_punkt(sx),
                    tippen=(lambda _e: on_start()) if on_start is not None else None,
                    zeichen=ft.Container(
                        width=PUNKT,
                        height=PUNKT,
                        border_radius=PUNKT / 2,
                        bgcolor=ft.Colors.PRIMARY,
                        border=ft.Border.all(2, ft.Colors.SURFACE),
                    ),
                    hoch=START_GRIFF,
                )
            )

    # -- Das Menü an einem Knoten: Schirm über allem, der Knoten und die Karte darüber --------
    if menue is not None and menue.knoten in mitten and menue.eintraege:
        x, y = mitten[menue.knoten]
        links = max(x - MENUE_B / 2, 4.0)
        # so hoch ist die Karte: ihre Zeilen und die Linien dazwischen
        karte_h = len(menue.eintraege) * (MENUE_ZEILE + 1) - 1
        oben = max(y - 10 - karte_h, 4.0) if menue.nach_oben else y + 10
        # die Karte muss in der Fläche liegen — außerhalb nähme sie keinen Tipp an
        breite = max(breite, links + MENUE_B + 12)
        hoehe = max(hoehe, oben + karte_h + 24)
        leinwand.width, leinwand.height = breite, hoehe

        def waehlen(eintrag: Eintrag) -> Callable[[Any], Any]:
            async def handler(_e: Any = None) -> None:
                ergebnis = eintrag.aktion()
                if inspect.isawaitable(ergebnis):
                    await ergebnis

            return handler

        zeilen: list[ft.Control] = []
        for n, eintrag in enumerate(menue.eintraege):
            ton = ft.Colors.ERROR if eintrag.gefahr else None
            if n:
                zeilen.append(ft.Container(height=1, bgcolor=ft.Colors.OUTLINE_VARIANT))
            zeilen.append(
                ft.Container(
                    height=MENUE_ZEILE,
                    padding=ft.Padding.symmetric(horizontal=14),
                    alignment=ft.Alignment.CENTER_LEFT,
                    ink=True,
                    on_click=waehlen(eintrag),
                    data=("menue_eintrag", eintrag.text),
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            *(
                                [ft.Icon(eintrag.symbol, size=18, color=ton)]
                                if eintrag.symbol is not None
                                else []
                            ),
                            ft.Text(eintrag.text, size=14, color=ton, expand=True, max_lines=1),
                        ],
                    ),
                )
            )
        schirm = ft.GestureDetector(
            left=0,
            top=0,
            on_tap=lambda _e: menue.schliessen(),
            data=("schirm",),
            content=ft.Container(
                width=breite,
                height=hoehe,
                bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.SURFACE),
            ),
        )
        # der Knoten, an dem das Menü hängt, steht über dem Schirm — er bleibt klar
        traeger = knoten_controls[menue.knoten]
        schichten.remove(traeger)
        schichten += [
            schirm,
            traeger,
            ft.Container(
                left=links,
                top=oben,
                width=MENUE_B,
                height=karte_h,
                border_radius=14,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                shadow=ft.BoxShadow(
                    blur_radius=18,
                    spread_radius=1,
                    color=ft.Colors.with_opacity(0.3, ft.Colors.SHADOW),
                    offset=ft.Offset(0, 4),
                ),
                data=("menue", menue.knoten),
                content=ft.Column(spacing=0, tight=True, controls=zeilen),
            ),
        ]
    return Zeichnung(schichten, breite, hoehe, mitten, knoten_controls)


def ziele(on_verbinden: Callable[[str, str], Any]) -> Ziele:
    """Die zwei Ziele, die kein Knoten sind — **„Ende“** und **„zurück“** (dorthin, wo man
    herkam) — als Ablagen für den Punkt eines Knotens: ``on_verbinden(von, core.ablauf.ENDE)``
    bzw. ``…ZURUECK``. Sie stehen am unteren Rand des Bildes (`mit_zielen`) und sind nur zu
    sehen, während gezogen wird: ``on_ziehen=ziele.zeigen`` an der Zeichnung. **In den Ecken**,
    kurz beschriftet: Was sie verdecken, lässt sich nicht treffen — mittig lag eine Übung
    genau unter „zurück, wo ich herkam“ (Web-Foto 16.11.2026)."""
    leiste = ft.Container(left=8, right=8, bottom=8, visible=False, data=("ziele",))
    z = Ziele(leiste)

    def ziel(text: str, symbol: ft.IconData, nach: str) -> ft.Control:
        pille = ft.Container(
            padding=ft.Padding.symmetric(horizontal=14, vertical=9),
            border_radius=20,
            border=ft.Border.all(2, ft.Colors.OUTLINE),
            bgcolor=ft.Colors.SURFACE,
            shadow=ft.BoxShadow(blur_radius=8, color=ft.Colors.with_opacity(0.2, ft.Colors.SHADOW)),
            content=ft.Row(
                tight=True,
                spacing=6,
                controls=[ft.Icon(symbol, size=16), ft.Text(text, size=13)],
            ),
        )

        def faerben(an: bool) -> None:
            pille.border = ft.Border.all(
                2.5 if an else 2, ft.Colors.TERTIARY if an else ft.Colors.OUTLINE
            )
            pille.bgcolor = ft.Colors.TERTIARY_CONTAINER if an else ft.Colors.SURFACE
            with contextlib.suppress(Exception):  # noch nicht auf der Seite
                pille.update()

        def drueber(e: Any, an: bool = True) -> None:
            """Schwebt ein Punkt über dem Ziel, leuchtet es."""
            if an and not getattr(e, "accept", True):
                return
            ohne_auto_update()  # kommt beim Ziehen dauernd: nur die Pille neu zeichnen
            faerben(an)

        def fallen(e: Any) -> None:
            von = getattr(getattr(e, "src", None), "data", None)
            faerben(False)
            z.zeigen(False)
            if isinstance(von, str) and von:
                on_verbinden(von, nach)

        return ft.DragTarget(
            group=GRUPPE_WEG,
            content=pille,
            on_accept=fallen,
            on_will_accept=drueber,
            on_leave=lambda e: drueber(e, False),
            data=("ziel", nach),
        )

    leiste.content = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        controls=[
            ziel("Ende", ft.Icons.STOP, ab.ENDE),
            ziel("zurück", ft.Icons.UNDO, ab.ZURUECK),
        ],
    )
    return z


def mit_zielen(bild_ansicht: ft.Control, z: Ziele) -> ft.Stack:
    """Die Fläche mit den Zielen darüber — sie stehen fest am unteren Rand, auch wenn das Bild
    geschoben oder gezoomt ist."""
    return ft.Stack(controls=[bild_ansicht, z.control])


def fangnetz(inhalt: ft.Control, z: Ziele) -> ft.DragTarget:
    """Eine Ablage um die ganze Ansicht: Fällt ein Punkt **ins Leere**, verschwinden die Ziele
    wieder. Flet meldet einem Draggable nur das angenommene Ablegen (``on_drag_complete``),
    einen Abbruch nicht — ohne dieses Netz blieben „Ende“ und „◀ zurück“ stehen. Was außerhalb
    liegt (die Titelleiste), fängt es nicht; dort räumt das nächste Neuzeichnen auf."""
    return ft.DragTarget(group=GRUPPE_WEG, content=inhalt, on_accept=lambda _e: z.zeigen(False))


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
    "ABZWEIG",
    "EBENE",
    "GRUPPE_KACHEL",
    "GRUPPE_WEG",
    "KNOTEN",
    "NEBEL",
    "SPALTE",
    "START",
    "Bild",
    "Eintrag",
    "Menue",
    "Zeichnung",
    "Ziele",
    "ablaufbild",
    "abspielen",
    "aktualisieren",
    "ansicht",
    "etikett_text",
    "fangnetz",
    "flaeche_neu",
    "mit_zielen",
    "zeichnung",
    "ziele",
]
