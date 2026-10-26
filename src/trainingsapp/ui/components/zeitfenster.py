"""Zeitfenster der Messkurven: zoomen (Breite) und seitlich wischen (Lage).

Alle Kurven einer Messung — Tachogramm und Verlaufskurven — teilen sich ein
Zeitfenster. Waagrecht wischen verschiebt es für alle zugleich; darum
wechselt man die Verlaufskurven über Chips, nicht über ein Wischen.
Senkrecht bleibt der Seite: Ein waagrechter Zieh-Erkenner gewinnt nur
waagrechte Bewegungen, die Seite scrollt weiter.

Zoomen geht über die Fensterbreite (Knöpfe) — eine Zwei-Finger-Geste
bräuchte in Flet einen Skalier-Erkenner, und der nähme der Seite auch das
senkrechte Scrollen. Live und in der Aufzeichnung sind es dieselben vier
Knöpfe (`breiten_wahl`, Ben 21.10.2026); jede andere Breite tippt man unter
„Fenster & Darstellung“ ein (`BreiteFeld`).

**Last beim Wischen** (gemessen 14.10.2026, `docs/plan_analyse_leistung.md`):
Ohne `drag_interval` schickt Flet jede Fingerbewegung als Ereignis, und nach
jedem Ereignis ohne eigenes ``update()`` vergleicht es die ganze Seite. Darum
kommen Ziehereignisse höchstens alle `_ZIEH_MS`, das Auto-Update ist in den
Ziehhandlern aus (wer neu zeichnet, aktualisiert selbst), und die Drossel
zählt ab dem **Ende** des letzten Neuzeichnens — sonst zeichnete unter Last
jedes wartende Ereignis wieder neu.

**Fallstrick der Drossel** (Flet 1.0.3, `gesture_detector.dart`): Verworfene
Zwischenereignisse werden nicht aufsummiert. `primary_delta` ist Flutters
``details.primaryDelta`` — nur der Weg des *letzten* Touch-Frames (bei 120 Hz
und 50 ms Drossel ein Sechstel der Bewegung). `local_delta` rechnet Flet
dagegen gegen die Lage beim letzten *gesendeten* Ereignis (am Gestenbeginn
zurückgesetzt) — das ist der ganze Weg. Darum zählt hier `local_delta`.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.core.hrv_einstellungen import FENSTER_MIN_S
from trainingsapp.core.zeitangabe import breite_lesen, dauer_text
from trainingsapp.ui.components.layout import ohne_auto_update

#: Breiten der Zeitachse (s) — „Min“ hinten dran (Ben, 19.10.2026), live und in der
#: Aufzeichnung dieselben (21.10.2026)
BREITEN: tuple[tuple[int, str], ...] = (
    (60, "1 Min"),
    (120, "2 Min"),
    (300, "5 Min"),
    (600, "10 Min"),
)
#: Was das Feld „Breite der Zeitachse“ versteht
BREITE_UNLESBAR = "Nicht lesbar — z. B. 3, 1:30 oder 90 s"

#: Höchstens so oft je Sekunde wird beim Wischen neu gezeichnet
_WISCH_HZ = 8.0
#: Ziehereignisse kommen höchstens so oft (ms) aus Flutter
_ZIEH_MS = 50
#: Ohne gemessene Breite: so breit ist die Zeichenfläche ungefähr (px)
_BREITE_VORGABE = 320.0
#: Platz der y-Beschriftung links (px) — er wischt nicht mit
_ACHSE_PX = 52.0


@dataclass
class Fenster:
    """Sichtbarer Ausschnitt: ``breite_s`` und rechter Rand (``None`` = am Ende/live).

    >>> f = Fenster(60, None)
    >>> f.bereich(200.0)
    (140.0, 200.0)
    >>> f.verschieben(-30, 200.0); f.bereich(200.0)
    (110.0, 170.0)
    >>> f.verschieben(+100, 200.0); f.ende_s is None
    True
    >>> f.verschieben(-500, 200.0, anfang=0.0); f.bereich(200.0)
    (0.0, 60.0)
    """

    breite_s: float
    ende_s: float | None = None

    def bereich(self, jetzt_s: float, anfang: float = 0.0) -> tuple[float, float]:
        """``(von, bis)`` — mindestens ``breite_s`` breit, nie vor ``anfang``."""
        bis = jetzt_s if self.ende_s is None else min(self.ende_s, jetzt_s)
        bis = max(bis, anfang + self.breite_s)
        return bis - self.breite_s, bis

    def verschieben(self, delta_s: float, jetzt_s: float, anfang: float = 0.0) -> None:
        """Um ``delta_s`` verschieben; am rechten Ende rastet es wieder ein (folgt)."""
        _, bis = self.bereich(jetzt_s, anfang)
        neu = max(bis + delta_s, anfang + self.breite_s)
        self.ende_s = None if neu >= jetzt_s - 0.5 else neu

    def breite_links(
        self, breite_s: float, jetzt_s: float, anfang: float = 0.0, *, folgen: bool = True
    ) -> None:
        """Die Breite ändern, der **linke Rand bleibt** (Ben, 26.10.2026: der Fixpunkt beim
        Wechsel 1 · 2 · 5 · 10 Min). Folgt das Fenster live der Gegenwart (``folgen``),
        folgt es weiter — ein stehender linker Rand wäre das Ende des Mitlaufens. In der
        Aufzeichnung (``folgen=False``) heißt ``ende_s = None`` nur „am Ende“, der linke
        Rand bleibt auch dann.

        >>> f = Fenster(60, 100.0)
        >>> f.breite_links(120, 500.0); f.bereich(500.0)
        (40.0, 160.0)
        >>> f.breite_links(600, 500.0); f.ende_s is None  # reicht bis ans Ende: folgt
        True
        >>> f.breite_links(60, 500.0); f.bereich(500.0)  # folgt weiter, rechts bleibt
        (440.0, 500.0)
        >>> g = Fenster(500, None)  # Aufzeichnung, ganze Messung
        >>> g.breite_links(60, 500.0, folgen=False); g.bereich(500.0)
        (0.0, 60.0)
        """
        if self.ende_s is None and folgen:
            self.breite_s = breite_s
            return
        von, _ = self.bereich(jetzt_s, anfang)
        self.breite_s = breite_s
        neu = von + breite_s
        self.ende_s = None if neu >= jetzt_s - 0.5 else neu


def wischbar(
    inhalt: ft.Control,
    fenster: Fenster,
    jetzt_s: Callable[[], float],
    neu_zeichnen: Callable[[], None],
    anfang: Callable[[], float] = lambda: 0.0,
    tippen: Callable[[float], None] | None = None,
    greifen: Callable[[float], bool] | None = None,
    losgelassen: Callable[[], None] | None = None,
    tippen_punkt: Callable[[float, float], None] | None = None,
    rechts_px: Callable[[], float] = lambda: 0.0,
) -> ft.Control:
    """``inhalt`` (die Kurvenspalte) waagrecht wischbar machen.

    Nach rechts wischen blättert zurück (wie in einer Bildergalerie); ``anfang``
    liefert den frühesten Zeitpunkt (Live: Beginn des Puffers). ``tippen``
    bekommt bei einem Tipp die Zeit unter dem Finger (Notiz in die Kurve setzen).

    ``greifen`` bekommt zu Beginn einer Geste die Zeit unter dem Finger; gibt
    es ``True`` zurück, gehört die ganze Geste ihm (eine Grenze, der
    Ablesestrich oder das Analysefenster folgt dem Finger, ``greifen`` bekommt
    jede weitere Lage) und die Kurve bleibt stehen. Sonst blättert die Geste
    bis zum Ende — ein Finger, der unterwegs über ein Fenster streicht, greift
    es nicht. ``losgelassen`` meldet das Ende jeder Geste.

    Gezeichnet wird höchstens `_WISCH_HZ`-mal je Sekunde und am Ende der Geste —
    ``neu_zeichnen`` aktualisiert selbst, was es geändert hat.

    ``tippen_punkt`` bekommt statt ``tippen`` Zeit **und** Höhe des Tipps (px von
    oben) — das Vollbild unterscheidet so Abschnittsbalken oben von der Kurve.
    ``rechts_px``: so breit ist rechts eine zweite Werteachse; sie zählt nicht
    zur Zeichenfläche.
    """
    #: ``greift``: None = noch nicht entschieden, True = Geste gehört ``greifen``, False = blättern
    stand: dict[str, Any] = {"breite_px": _BREITE_VORGABE, "zuletzt": 0.0, "greift": None}

    def groesse(e: ft.LayoutSizeChangeEvent) -> None:
        stand["breite_px"] = max(float(e.width) - _ACHSE_PX, 100.0)

    def zeichnen_gedrosselt() -> None:
        if time.monotonic() - stand["zuletzt"] >= 1.0 / _WISCH_HZ:
            neu_zeichnen()
            # Ab dem Ende gezählt: Ereignisse, die währenddessen auflaufen, fassen sich zusammen
            stand["zuletzt"] = time.monotonic()

    def flaeche_px() -> float:
        """Breite der Zeichenfläche: ohne die Beschriftung links und eine Achse rechts."""
        return max(stand["breite_px"] - rechts_px(), 50.0)

    def zeit(position: ft.Offset) -> float:
        return zeit_unter(position.x, fenster, jetzt_s(), anfang(), flaeche_px())

    def gegriffen(position: ft.Offset | None) -> bool:
        """Gehört diese Lage ``greifen``? Entschieden wird einmal je Geste, am Anfang."""
        if greifen is None or position is None or stand["greift"] is False:
            return False
        if greifen(zeit(position)):
            stand["greift"] = True
            return True
        stand["greift"] = False
        return False

    def beginn(e: ft.DragStartEvent) -> None:
        ohne_auto_update()
        stand["greift"] = None
        if gegriffen(getattr(e, "local_position", None)):
            zeichnen_gedrosselt()

    def ziehen(e: ft.DragUpdateEvent) -> None:
        ohne_auto_update()
        if gegriffen(getattr(e, "local_position", None)):
            zeichnen_gedrosselt()
            return
        # ``local_delta`` = Weg seit dem letzten *gesendeten* Ereignis; ``primary_delta``
        # ist nur der Weg des letzten Touch-Frames — mit `drag_interval` ginge
        # der Rest der Bewegung verloren (Finger 300 px, Kurve 50 px).
        weg = getattr(e, "local_delta", None)
        dx = weg.x if weg is not None else e.primary_delta
        if dx is None:
            dx = 0.0
        vorher = fenster.ende_s
        fenster.verschieben(-dx / flaeche_px() * fenster.breite_s, jetzt_s(), anfang())
        if fenster.ende_s == vorher:
            return  # am Rand oder bei „Alles": nichts bewegt, nichts zu zeichnen
        zeichnen_gedrosselt()

    def ende(_: ft.DragEndEvent) -> None:
        ohne_auto_update()
        neu_zeichnen()
        stand["zuletzt"] = time.monotonic()
        stand["greift"] = None
        if losgelassen is not None:
            losgelassen()

    def tipp(e: ft.TapEvent) -> None:
        if e.local_position is None:
            return
        x = zeit(e.local_position)
        if tippen_punkt is not None:
            tippen_punkt(x, float(e.local_position.y))
        elif tippen is not None:
            tippen(x)

    return ft.GestureDetector(
        content=ft.Container(content=inhalt, on_size_change=groesse),
        drag_interval=_ZIEH_MS,
        on_horizontal_drag_start=beginn if greifen is not None else None,
        on_horizontal_drag_update=ziehen,
        on_horizontal_drag_end=ende,
        on_tap_down=tipp if tippen is not None or tippen_punkt is not None else None,
    )


def zeit_unter(
    x_px: float, fenster: Fenster, jetzt_s: float, anfang: float, breite_px: float
) -> float:
    """Zeit unter einer waagrechten Position (px) — links liegt die y-Beschriftung.

    >>> zeit_unter(52 + 160, Fenster(60, None), 200.0, 0.0, 320.0)
    170.0
    """
    von, bis = fenster.bereich(jetzt_s, anfang)
    anteil = min(max((x_px - _ACHSE_PX) / max(breite_px, 1.0), 0.0), 1.0)
    return round(von + anteil * (bis - von), 3)


# ---------------------------------------------------------------------------
# Breite wählen: vier Knöpfe, jede andere eintippen
# ---------------------------------------------------------------------------


def breiten_auswahl(breite_s: float) -> list[str]:
    """Der gewählte Knopf zu einer Breite — keiner, wenn sie zu keinem passt.

    >>> breiten_auswahl(120.0), breiten_auswahl(210), breiten_auswahl(0)
    (['120'], [], [])
    """
    return [str(s) for s, _ in BREITEN if abs(breite_s - s) < 0.5]


def breiten_wahl(
    breite_s: float, waehlen: Callable[[float], None], *, kompakt: bool = False
) -> ft.SegmentedButton:
    """1 · 2 · 5 · 10 Min — hochkant über die volle Breite, im Vollbild ``kompakt``.

    Jede andere Breite (eingetippt, ein Abschnitt, die ganze Messung) wählt keinen
    Knopf; das Fenster behält sie trotzdem. Nach einer Änderung von außen stellt
    `breiten_auswahl` die Wahl nach.
    """

    def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            waehlen(float(e.control.selected[0]))

    return ft.SegmentedButton(
        selected=breiten_auswahl(breite_s),
        allow_empty_selection=True,
        show_selected_icon=False,
        expand=not kompakt,
        style=ft.ButtonStyle(
            visual_density=ft.VisualDensity.COMPACT, padding=ft.Padding.symmetric(horizontal=6)
        )
        if kompakt
        else None,
        segments=[
            ft.Segment(value=str(s), label=ft.Text(t, size=12 if kompakt else None))
            for s, t in BREITEN
        ],
        on_change=gewaehlt,
    )


class BreiteFeld:
    """Die Breite der Zeitachse eintippen — unter „Fenster & Darstellung“ (Ben, 21.10.2026).

    Eine Zahl sind Minuten, dazu ``m:ss`` oder „90 s“ (`core.zeitangabe.breite_lesen`);
    übernommen wird beim Bestätigen, beim Verlassen des Felds und — über `uebernehmen` —
    beim Schließen des Blatts. Zu klein oder größer als ``max_s`` (live der Puffer, in
    der Aufzeichnung die Messung) wird an die Grenze gesetzt.
    """

    def __init__(
        self, breite_s: float, setzen: Callable[[float], None], *, max_s: float | None = None
    ) -> None:
        self._setzen = setzen
        self._max_s = max_s
        self._breite_s = float(breite_s)
        self.control = ft.TextField(
            label="Breite der Zeitachse",
            value=dauer_text(breite_s),
            suffix="min",
            helper="z. B. 3 · 1:30 · 90 s",
            dense=True,
            width=220,
            keyboard_type=ft.KeyboardType.DATETIME,
            on_submit=lambda _: self.uebernehmen(),
            on_blur=lambda _: self.uebernehmen(),
        )

    def anzeigen(self, breite_s: float) -> None:
        """Eine Breite, die anders gewählt wurde (ein Knopf), ins Feld schreiben."""
        self._breite_s = float(breite_s)
        self.control.value = dauer_text(breite_s)
        self.control.error = None
        with contextlib.suppress(Exception):
            self.control.update()

    def max_setzen(self, max_s: float | None) -> None:
        """Eine neue Obergrenze (live: der Puffer wurde umgestellt)."""
        self._max_s = max_s

    def uebernehmen(self) -> None:
        """Den getippten Wert übernehmen — unverändert passiert nichts."""
        sekunden = breite_lesen(self.control.value or "")
        if sekunden is None:
            self.control.error = BREITE_UNLESBAR
        else:
            obergrenze = self._max_s if self._max_s is not None else sekunden
            sekunden = float(round(min(max(sekunden, FENSTER_MIN_S), max(obergrenze, 1.0))))
            self.control.error = None
            self.control.value = dauer_text(sekunden)
            if abs(sekunden - self._breite_s) >= 0.5:
                self._breite_s = sekunden
                self._setzen(sekunden)
        with contextlib.suppress(Exception):  # Blatt schon zu
            self.control.update()


__all__ = [
    "BREITEN",
    "BreiteFeld",
    "Fenster",
    "breiten_auswahl",
    "breiten_wahl",
    "wischbar",
    "zeit_unter",
]
