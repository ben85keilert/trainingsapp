"""Verlaufskurven unter der Hauptkurve — live und in der Aufzeichnung.

Die Ansicht (`core.hrv_ansicht.Ansicht`) sagt, welche Kurven zu sehen sind,
mit welchem Fenster und ob gleitend oder in Blöcken. Je Analysebereich (Zeit,
Frequenz, Nichtlinear) stehen nur dessen Chips und Kurven da. Antippen eines
Chips zeigt oder verbirgt eine Kurve; gleiche Achsen teilen sich ein Diagramm,
verschiedene stehen untereinander — alle mit derselben Zeitachse wie die
Hauptkurve, sodass ein Wischen alle zugleich verschiebt. Gerechnet wird nichts
hier: die Werte liefert der Aufrufer (`daten`), aus `hrv_core.trends`.

**Fenster & Darstellung** (`darstellung_blatt`) ist seit dem 21.10.2026 ein eigener
Knopf neben dem Menü (Ben: „weil man diese Einstellungen vielleicht öfter braucht“)
und stellt außer Fenster und gleitend/Blöcke auch die **Breite der Zeitachse**
(eintippen) und **feste Werteachsen** ein (``Ansicht.y_achsen``, z. B. RR 500–1500).
Das Menü (`ansicht_menue`) nimmt dafür Info und automatische Korrektur auf.
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

import flet as ft
from hrv_core.trends import KENNZAHLEN, im_bereich, titel, treppe

from trainingsapp.core.hrv_ansicht import BLOCK, GLEITEND, PNN_WAHL, Ansicht
from trainingsapp.core.zeitangabe import breite_lesen
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.karte import titel as abschnitt_titel
from trainingsapp.ui.components.kurve import Reihe, kurve
from trainingsapp.ui.components.zeitfenster import BreiteFeld
from trainingsapp.ui.farben import FARBEN  # feste Farbe je Kurve, hell/dunkel

BEREICH_TITEL = {"zeit": "Zeit", "frequenz": "Frequenz", "nichtlinear": "Nichtlinear"}

#: (Kennzahl, Fenster, Block?) → Punkte
Daten = Callable[[str, int, bool], Sequence[tuple[float, float]]]


@dataclass(frozen=True, slots=True)
class Werteachse:
    """Eine y-Achse im Blatt „Fenster & Darstellung“: Schlüssel in ``Ansicht.y_achsen``,
    die Kurven, die sie teilen, ihre Einheit und Farbe (die der ersten Kurve)."""

    schluessel: str
    name: str
    einheit: str
    farbe: str | None = None


@dataclass(frozen=True, slots=True)
class Zeitachse:
    """Die Breite der Zeitachse für das Blatt: jetzt, wie sie gesetzt wird, höchstens."""

    breite_s: float
    setzen: Callable[[float], None]
    max_s: float | None = None
    #: Die Wahl des Knopfsatzes (`zeitfenster.BreitenSatz.control`) — erster Eintrag der
    #: Zeitachse, über der Breite (Ben, 30.10.2026)
    satz: ft.Control | None = None


def _achse(kennzahl: str) -> str | None:
    k = KENNZAHLEN.get(kennzahl)
    return k.achse_schluessel if k else None


def fenster_text(sekunden: float) -> str:
    """„30 s", „2 min".

    >>> fenster_text(30), fenster_text(120), fenster_text(90)
    ('30 s', '2 min', '90 s')
    """
    s = int(sekunden)
    if s >= 3600 and s % 1800 == 0:
        return f"{s / 3600:g} h".replace(".", ",")
    return f"{s // 60} min" if s >= 120 and s % 60 == 0 else f"{s} s"


#: Eigene Fenster der Verlaufskurven (Ben, 30.10.2026: „einen manuellen Wert eingeben“):
#: von 3 s bis zu einem Tag — ein 30-min-Mittel der RR über eine Nacht ist aufschlussreich
FENSTER_EIGEN_MIN_S: Final[int] = 3
FENSTER_EIGEN_MAX_S: Final[int] = 86400


def fenster_lesen(text: str) -> int | None:
    """Ein eingetipptes Fenster in Sekunden: eine Zahl allein sind **Sekunden** (wie die
    Auswahl daneben), sonst „2 min“, „1:30“, „1 h“ (`zeitangabe.breite_lesen`).

    >>> fenster_lesen("45"), fenster_lesen("2 min"), fenster_lesen("1 h"), fenster_lesen("1:30")
    (45, 120, 3600, 90)
    >>> fenster_lesen("2"), fenster_lesen("abc"), fenster_lesen("30 h")
    (None, None, None)
    """
    t = (text or "").strip().replace(",", ".")
    try:
        sek = float(t)
    except ValueError:
        wert = breite_lesen(t)
        if wert is None:
            return None
        sek = wert
    s = round(sek)
    return s if FENSTER_EIGEN_MIN_S <= s <= FENSTER_EIGEN_MAX_S else None


def bezeichnung(kennzahl: str, ansicht: Ansicht) -> str:
    """„RMSSD 30 s" — mit Fenster, wo gerechnet wird; Blöcke „je 30 s".

    >>> bezeichnung("rmssd", Ansicht()), bezeichnung("hf_geraet", Ansicht())
    ('RMSSD 30 s', 'HF Gerät')
    >>> bezeichnung("pnnx", Ansicht(pnn_ms=20, modus={"pnnx": "block"}))
    'pNN20 je 30 s'
    """
    k = KENNZAHLEN[kennzahl]
    name = titel(kennzahl, ansicht.pnn_ms)
    if not k.rechnet:
        return name
    fenster = fenster_text(ansicht.fenster_fuer(kennzahl, k.fenster_s))
    return f"{name} je {fenster}" if ansicht.modus_fuer(kennzahl) == BLOCK else f"{name} {fenster}"


def schritt_min(kennzahlen: Sequence[str]) -> float:
    """Feinster Achsenschritt: Kennzahlen um 1 (DFA α1, LF/HF) brauchen Zehntel."""
    return 0.01 if min(KENNZAHLEN[k].spanne_min for k in kennzahlen) < 4 else 1.0


def diagramme(
    ansicht: Ansicht,
    daten: Daten,
    *,
    x_von: float,
    x_bis: float,
    hoehe: int = 120,
    ohne: Sequence[str] = (),
    bereich: str | None = None,
    marken: Sequence[Reihe] = (),
    gesehen: dict[str, tuple[str, list[tuple[float, float]]]] | None = None,
) -> list[ft.Control]:
    """Je Gruppe gleicher Achse ein Diagramm, darüber die Legende.

    ``ohne``: Kurven, die es für diese Messung nicht gibt (z. B. ``hf_rr`` bei
    einem reinen Pulsgeber) — sie bleiben gewählt, werden aber nicht gezeichnet.
    ``bereich``: nur die Kurven dieses Analysebereichs. ``marken``: in jedes
    Diagramm (der Ablesestrich). ``gesehen`` bekommt je Kurve Bezeichnung und
    Punkte — zum Ablesen an einer Stelle. Das Vollbild zeichnet anders: zwei
    Achsen in einem Diagramm (`components.vollbild.doppelkurve`).
    """
    out: list[ft.Control] = []
    for gruppe in kurvengruppen(ansicht, bereich, ohne):
        reihen = []
        legende: list[ft.Control] = []
        for k in gruppe:
            kz = KENNZAHLEN[k]
            fenster = ansicht.fenster_fuer(k, kz.fenster_s)
            block = kz.rechnet and ansicht.modus_fuer(k) == BLOCK
            punkte = list(daten(k, fenster, block))
            if gesehen is not None:
                gesehen[k] = (bezeichnung(k, ansicht), punkte)
            naehte: list[int] = []
            if block:
                punkte, naehte = treppe(punkte, fenster, x_von, x_bis)
            reihen.append(Reihe(punkte, farbe=FARBEN[k], naehte=naehte))
            legende.append(_legende(bezeichnung(k, ansicht), FARBEN[k]))
        out.append(ft.Row(spacing=14, run_spacing=4, wrap=True, controls=legende))
        out.append(
            kurve(
                [*reihen, *marken],
                einheit=KENNZAHLEN[gruppe[0]].einheit or KENNZAHLEN[gruppe[0]].titel,
                hoehe=hoehe,
                x_von=x_von,
                x_bis=x_bis,
                y_spanne_min=max(KENNZAHLEN[k].spanne_min for k in gruppe),
                y_schritt_min=schritt_min(gruppe),
                y_fest=ansicht.y_bereich(_achse(gruppe[0])),
            )
        )
    return out


def werte_bei(
    gesehen: dict[str, tuple[str, list[tuple[float, float]]]], x: float
) -> list[tuple[str, str, float]]:
    """(Kennzahl, Bezeichnung, Wert) gezeichneter Verlaufskurven an der Stelle ``x``.

    Je Kurve der nächste Punkt, sofern er nicht weiter als ein Fünfzigstel der
    Spanne entfernt liegt (sonst ist dort eine Lücke).

    >>> werte_bei({"rmssd": ("RMSSD 30 s", [(10.0, 40.0), (20.0, 42.0)])}, 19.0)
    [('rmssd', 'RMSSD 30 s', 42.0)]
    >>> werte_bei({"rmssd": ("RMSSD 30 s", [(10.0, 40.0), (20.0, 42.0)])}, 90.0)
    []
    """
    out = []
    for k, (name, punkte) in gesehen.items():
        if not punkte:
            continue
        spanne = max(punkte[-1][0] - punkte[0][0], 1.0)
        px, py = min(punkte, key=lambda p: abs(p[0] - x))
        if abs(px - x) <= max(spanne / 50, 5.0) and math.isfinite(py):
            out.append((k, name, float(py)))
    return out


def kurvengruppen(
    ansicht: Ansicht, bereich: str | None = None, ohne: Sequence[str] = ()
) -> list[list[str]]:
    """Die Diagramme der Ansicht: je Gruppe gleicher Achse die Kennzahlen.

    >>> kurvengruppen(Ansicht(kurven=["hf_rr", "rmssd", "sdnn", "lf_hf"]), "zeit")
    [['hf_rr'], ['rmssd', 'sdnn']]
    """
    nur = [k for k in (im_bereich(bereich) if bereich else KENNZAHLEN) if k not in ohne]
    return ansicht.gruppen(_achse, nur=nur)


def _legende(text: str, farbe: str) -> ft.Control:
    return ft.Row(
        spacing=5,
        tight=True,
        controls=[
            ft.Container(width=10, height=10, border_radius=5, bgcolor=farbe),
            ft.Text(text, size=11, opacity=0.85),
        ],
    )


def chips(
    ansicht: Ansicht,
    umschalten: Callable[[str], None],
    bereich: str = "zeit",
    ohne: Sequence[str] = (),
) -> ft.Control:
    """Ein Chip je Kurve des Bereichs, mit Farbpunkt; gewählte sind getönt."""

    def handler(k: str) -> Callable[[], None]:
        return lambda: umschalten(k)

    return ft.Row(
        wrap=True,
        spacing=8,
        run_spacing=8,
        controls=[
            ft.Chip(
                label=ft.Text(titel(k, ansicht.pnn_ms), size=12),
                leading=ft.Container(width=10, height=10, border_radius=5, bgcolor=FARBEN[k]),
                selected=k in ansicht.kurven,
                on_select=handler(k),
                show_checkmark=False,
                selected_color=ft.Colors.with_opacity(0.22, FARBEN[k]),
                visual_density=ft.VisualDensity.COMPACT,
            )
            for k in im_bereich(bereich)
            if k not in ohne
        ],
    )


def bereich_wahl(
    bereiche: Sequence[str], aktiv: str, wechseln: Callable[[str], None]
) -> ft.Control:
    """Zeit | Frequenz | Nichtlinear — nur die angebotenen."""

    def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            wechseln(str(e.control.selected[0]))

    return ft.SegmentedButton(
        selected=[aktiv if aktiv in bereiche else bereiche[0]],
        show_selected_icon=False,
        segments=[ft.Segment(value=b, label=ft.Text(BEREICH_TITEL[b])) for b in bereiche],
        on_change=gewaehlt,
    )


def ansicht_menue(
    page: Any,
    state: Any,
    geaendert: Callable[[], None],
    *,
    oben: Sequence[ft.PopupMenuItem] = (),
) -> ft.Control:
    """Das Menü ⋮ der Kurven: ``oben`` (Info, automatische Korrektur), dann die Ansichten —
    speichern, laden, löschen, zurücksetzen.

    „Fenster & Darstellung“ steht seit dem 21.10.2026 als eigener Knopf daneben
    (`darstellung_knopf`), Info und Korrektur dafür hier (Ben). ``state`` ist der
    `AppState` (Speicherort: ``app_setting``); ``geaendert`` baut die Kurven neu.
    """
    aktuell = state.ansicht()
    gespeichert = state.ansichten()

    def laden(a: Ansicht) -> Callable[[], None]:
        def handler() -> None:
            a.bereich = state.ansicht().bereich  # der Bereich bleibt, wo man ist
            state.ansicht_setzen(a)
            geaendert()

        return handler

    def zuruecksetzen() -> None:
        state.ansicht_setzen(Ansicht(bereich=state.ansicht().bereich))
        geaendert()

    def loeschen() -> None:
        state.ansicht_loeschen(aktuell.name)
        page.show_dialog(ft.SnackBar(ft.Text(f"Ansicht „{aktuell.name}“ gelöscht.")))
        geaendert()

    eintraege: list[ft.PopupMenuItem] = [
        *oben,
        *([ft.PopupMenuItem()] if oben else []),  # Trennlinie
        ft.PopupMenuItem(
            content="Als Ansicht speichern …",
            icon=ft.Icons.SAVE_OUTLINED,
            on_click=lambda: page.show_dialog(speichern_dialog(page, state, geaendert)),
        ),
    ]
    if gespeichert:
        eintraege.append(ft.PopupMenuItem())  # Trennlinie
        eintraege += [
            ft.PopupMenuItem(
                content=a.name,
                checked=a.name == aktuell.name,
                on_click=laden(a),
            )
            for a in gespeichert
        ]
    eintraege.append(ft.PopupMenuItem())
    if any(a.name == aktuell.name for a in gespeichert):
        eintraege.append(
            ft.PopupMenuItem(
                content=f"„{aktuell.name}“ löschen", icon=ft.Icons.DELETE_OUTLINE, on_click=loeschen
            )
        )
    eintraege.append(
        ft.PopupMenuItem(
            content="Kurven auf Standard zurücksetzen",
            icon=ft.Icons.RESTART_ALT,
            on_click=zuruecksetzen,
        )
    )
    return ft.PopupMenuButton(
        icon=ft.Icons.MORE_VERT,
        tooltip=f"Mehr · Ansicht: {aktuell.name}",
        items=eintraege,
    )


def darstellung_knopf(oeffnen: Callable[[], None]) -> ft.IconButton:
    """Der Knopf „Fenster & Darstellung“ neben dem Menü — zweiter von rechts (Ben, 21.10.2026)."""
    return ft.IconButton(
        ft.Icons.TUNE,
        tooltip="Fenster & Darstellung: Zeitachse, Werteachsen, Fenster",
        on_click=oeffnen,
    )


#: Was eine Zeile „Werteachse“ sagt, wenn die Zahlen nicht passen
Y_UNVOLLSTAENDIG = "von und bis eintragen — von kleiner als bis"


def _feldzahl(wert: float) -> str:
    """Zahl für ein Eingabefeld — ohne „k“, mit Komma.

    >>> _feldzahl(1500.0), _feldzahl(0.5), _feldzahl(25000.0)
    ('1500', '0,5', '25000')
    """
    return f"{wert:g}".replace(".", ",") if abs(wert) < 1e15 else str(wert)


def _zahl_lesen(text: str | None) -> float | None:
    """Eine eingetippte Zahl — Komma oder Punkt; ``None``, wenn keine.

    >>> _zahl_lesen("1500"), _zahl_lesen(" 0,5 "), _zahl_lesen(""), _zahl_lesen("abc")
    (1500.0, 0.5, None, None)
    """
    try:
        wert = float((text or "").strip().replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    return wert if math.isfinite(wert) else None


class _YZeile:
    """Eine Werteachse im Blatt: von, bis, zurück auf automatisch. Leer = automatisch."""

    def __init__(self, achse: Werteachse, ansicht: Ansicht, speichern: Callable[[], None]):
        self._achse = achse
        self._ansicht = ansicht
        self._speichern = speichern
        bereich = ansicht.y_bereich(achse.schluessel)
        self._von = self._feld("von", bereich[0] if bereich else None)
        self._bis = self._feld("bis", bereich[1] if bereich else None)
        self._auto = ft.IconButton(
            ft.Icons.RESTART_ALT,
            icon_size=20,
            tooltip="Wieder automatisch",
            visible=bereich is not None,
            on_click=lambda: self.automatisch(),
        )
        self.control = ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=10,
                            height=10,
                            border_radius=5,
                            bgcolor=achse.farbe or ft.Colors.PRIMARY,
                        ),
                        ft.Text(achse.name, weight=ft.FontWeight.W_600, expand=True),
                        ft.Text(achse.einheit, size=12, opacity=0.7),
                    ],
                ),
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[self._von, ft.Text("–", size=16), self._bis, self._auto],
                ),
            ],
        )

    def _feld(self, label: str, wert: float | None) -> ft.TextField:
        return ft.TextField(
            label=label,
            value=_feldzahl(wert) if wert is not None else "",
            hint_text="auto",
            dense=True,
            width=110,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_align=ft.TextAlign.RIGHT,
            on_submit=lambda _: self.uebernehmen(melden=True),
            on_blur=lambda _: self.uebernehmen(),
        )

    def uebernehmen(self, *, melden: bool = False) -> bool:
        """Beide leer → automatisch; beide Zahlen, von < bis → fest. Sonst bleibt die Achse,
        wie sie war (``False``) — der Hinweis steht nur, wenn ``melden``."""
        roh = (self._von.value or "").strip(), (self._bis.value or "").strip()
        lo, hi = _zahl_lesen(roh[0]), _zahl_lesen(roh[1])
        if not any(roh):
            neu: tuple[float, float] | None = None
        elif lo is not None and hi is not None and lo < hi:
            neu = (lo, hi)
        else:
            self._von.error = Y_UNVOLLSTAENDIG if melden else None
            self._aktualisieren()
            return False
        self._von.error = None
        if neu != self._ansicht.y_bereich(self._achse.schluessel):
            self._ansicht.y_setzen(self._achse.schluessel, neu)
            self._speichern()
        self._auto.visible = neu is not None
        self._aktualisieren()
        return True

    def automatisch(self) -> None:
        self._von.value = self._bis.value = ""
        self.uebernehmen()

    def _aktualisieren(self) -> None:
        with contextlib.suppress(Exception):  # Blatt schon zu
            self.control.update()


def darstellung_blatt(
    page: Any,
    state: Any,
    geaendert: Callable[[], None],
    kurven: Sequence[str] | None = None,
    *,
    achsen: Sequence[Werteachse] = (),
    zeitachse: Zeitachse | None = None,
) -> ft.BottomSheet:
    """Zeitachse, Werteachsen und je gewählter Kurve: Fenster, gleitend oder Blöcke; pNNx.

    Ein Blatt von unten, kein Dialog: Ein ``AlertDialog`` misst seinen Inhalt
    vorab (intrinsische Größe), und das können Auswahllisten (``Dropdown``) nicht
    — der Dialog blieb unsichtbar, nur der Bildschirm wurde dunkel (14.10.).
    ``kurven``: statt der Kurven des Bereichs diese (das Vollbild: beide Achsen).

    ``zeitachse``: die Breite eintippen (`BreiteFeld`); ``achsen``: die y-Achsen der
    gezeigten Kurven (`vollbild.werteachsen`) — leer heißt automatisch, zwei Zahlen
    legen sie fest (Ben, 21.10.2026). Getipptes gilt beim Bestätigen, beim Verlassen
    des Felds und beim Schließen des Blatts; ein halb ausgefülltes Paar hält „Fertig“
    mit einem Hinweis auf.
    """
    ansicht = state.ansicht()
    gewaehlt = [
        k
        for k in (kurven if kurven is not None else im_bereich(ansicht.bereich))
        if k in KENNZAHLEN and KENNZAHLEN[k].rechnet and (kurven is not None or k in ansicht.kurven)
    ]

    def speichern() -> None:
        state.ansicht_setzen(ansicht)
        geaendert()

    breite = (
        BreiteFeld(zeitachse.breite_s, zeitachse.setzen, max_s=zeitachse.max_s)
        if zeitachse is not None
        else None
    )
    y_zeilen = [_YZeile(a, ansicht, speichern) for a in achsen]

    def alles_uebernehmen(*, melden: bool) -> bool:
        if breite is not None:
            breite.uebernehmen()
        return all([z.uebernehmen(melden=melden) for z in y_zeilen])

    def fenster_setzen(k: str) -> Callable[[ft.Event[ft.Dropdown]], None]:
        def handler(e: ft.Event[ft.Dropdown]) -> None:
            with contextlib.suppress(TypeError, ValueError):
                ansicht.fenster[k] = int(e.control.value or 0)
                speichern()

        return handler

    def fenster_wahl(k: str, kz: Any) -> ft.Dropdown:
        """Die Auswahl der Kennzahl — ein eigenes Fenster steht als zusätzlicher Eintrag."""
        jetzt = ansicht.fenster_fuer(k, kz.fenster_s)
        werte = sorted({*kz.fenster_wahl, jetzt})
        return ft.Dropdown(
            value=str(jetzt),
            options=[ft.DropdownOption(key=str(s), text=fenster_text(s)) for s in werte],
            on_select=fenster_setzen(k),
            dense=True,
            width=110,
        )

    def eigenes_fenster(k: str, kz: Any, wahl: ft.Dropdown) -> ft.TextField:
        """Ein Fenster eintippen (Ben, 30.10.2026): Sekunden, „2 min“, „1 h“ — damit sich
        auch langsame Wellen abbilden lassen (30-min-Mittel über eine Nacht)."""
        feld = ft.TextField(
            label="eigenes",
            dense=True,
            width=96,
            hint_text="s · min · h",
            keyboard_type=ft.KeyboardType.DATETIME,
        )

        def uebernehmen(_e: object = None) -> None:
            if not (feld.value or "").strip():
                return
            sek = fenster_lesen(feld.value or "")
            if sek is None:
                feld.error = "3 s bis 24 h"
                with contextlib.suppress(Exception):
                    feld.update()
                return
            feld.error = None
            ansicht.fenster[k] = sek
            speichern()
            werte = sorted({*kz.fenster_wahl, sek})
            wahl.options = [ft.DropdownOption(key=str(s), text=fenster_text(s)) for s in werte]
            wahl.value = str(sek)
            feld.value = ""
            for c in (wahl, feld):
                with contextlib.suppress(Exception):
                    c.update()

        feld.on_submit = uebernehmen
        feld.on_blur = uebernehmen
        return feld

    def modus_setzen(k: str) -> Callable[[ft.Event[ft.SegmentedButton]], None]:
        def handler(e: ft.Event[ft.SegmentedButton]) -> None:
            if e.control.selected:
                if e.control.selected[0] == BLOCK:
                    ansicht.modus[k] = BLOCK
                else:
                    ansicht.modus.pop(k, None)
                speichern()

        return handler

    def pnn_setzen(e: ft.Event[ft.Dropdown]) -> None:
        with contextlib.suppress(TypeError, ValueError):
            ansicht.pnn_ms = int(e.control.value or 50)
            speichern()

    def gemeinsam(e: ft.Event[ft.Switch]) -> None:
        ansicht.gemeinsam = bool(e.control.value)
        speichern()

    zeilen: list[ft.Control] = []
    for k in gewaehlt:
        kz = KENNZAHLEN[k]
        zeilen.append(
            ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Row(
                        spacing=6,
                        controls=[
                            ft.Container(width=10, height=10, border_radius=5, bgcolor=FARBEN[k]),
                            ft.Text(titel(k, ansicht.pnn_ms), weight=ft.FontWeight.W_600),
                        ],
                    ),
                    ft.Row(
                        spacing=8,
                        wrap=True,
                        run_spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            (wahl := fenster_wahl(k, kz)),
                            eigenes_fenster(k, kz, wahl),
                            ft.SegmentedButton(
                                selected=[ansicht.modus_fuer(k)],
                                show_selected_icon=False,
                                segments=[
                                    ft.Segment(value=GLEITEND, label=ft.Text("gleitend")),
                                    ft.Segment(value=BLOCK, label=ft.Text("Blöcke")),
                                ],
                                on_change=modus_setzen(k),
                            ),
                        ],
                    ),
                ],
            )
        )
    if "pnnx" in gewaehlt:
        zeilen.append(
            ft.Dropdown(
                label="Schwelle für pNNx",
                value=str(ansicht.pnn_ms),
                options=[ft.DropdownOption(key=str(x), text=f"{x} ms") for x in PNN_WAHL],
                on_select=pnn_setzen,
                dense=True,
            )
        )
    if not zeilen:
        zeilen.append(ft.Text("Keine gewählte Kurve hat ein Fenster.", size=12, opacity=0.7))
    zeilen += [
        ft.Switch(
            label="Gleiche Achse in einem Diagramm", value=ansicht.gemeinsam, on_change=gemeinsam
        ),
        ft.Text(
            "Gleitend: Je länger das Fenster, desto ruhiger die Kurve und desto "
            "später zeigt sie eine Änderung. Blöcke: ein Wert je Fenster, ohne "
            "Überlappung — gut zum Vergleichen von Abschnitten.",
            size=11,
            opacity=0.65,
        ),
    ]
    teile: list[ft.Control] = []
    if breite is not None:
        teile += [abschnitt_titel("Zeitachse")]
        if zeitachse is not None and zeitachse.satz is not None:
            teile.append(zeitachse.satz)
        teile.append(breite.control)
    if y_zeilen:
        teile += [
            abschnitt_titel("Werteachsen"),
            ft.Text(
                "Leer heißt automatisch: Die Achse folgt den Werten im Ausschnitt. Zwei "
                "Zahlen legen sie fest, z. B. RR 500 bis 1500 ms — was darüber oder "
                "darunter liegt, schneidet die Kurve am Rand ab.",
                size=11,
                opacity=0.65,
            ),
            *(z.control for z in y_zeilen),
        ]
    if teile:
        teile.append(abschnitt_titel("Kurven"))

    def fertig() -> None:
        if alles_uebernehmen(melden=True):
            # genau das Blatt — eine SnackBar der Live-Ansicht (Gurt getrennt) läge sonst
            # oben und `pop_dialog` träfe sie (N18)
            schliessen(blatt)

    def beim_schliessen(_e: object = None) -> None:
        """Weggewischt: was vollständig getippt ist, gilt (Blätter speichern beim Schließen)."""
        alles_uebernehmen(melden=False)

    blatt: ft.BottomSheet
    kopf = ft.Row(
        controls=[
            ft.Text("Fenster & Darstellung", size=18, weight=ft.FontWeight.W_600, expand=True),
            ft.TextButton("Fertig", on_click=fertig),
        ]
    )
    blatt = ft.BottomSheet(
        content=ft.Container(
            padding=ft.Padding.only(left=16, top=4, right=16, bottom=16),
            content=ft.Column(
                spacing=16,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[kopf, *teile, *zeilen],
            ),
        ),
        scrollable=True,
        show_drag_handle=True,
        on_dismiss=beim_schliessen,
    )
    return blatt


def speichern_dialog(page: Any, state: Any, geaendert: Callable[[], None]) -> ft.AlertDialog:
    """Die aktuelle Ansicht unter einem Namen ablegen — gleicher Name ersetzt."""
    ansicht = state.ansicht()
    name = ft.TextField(
        label="Name",
        value="" if ansicht.name == "Standard" else ansicht.name,
        hint_text="z. B. Atemübung, Ruhe morgens",
        autofocus=True,
    )

    nachher = Nachher()
    dialog: ft.AlertDialog

    def speichern() -> None:
        text = (name.value or "").strip()
        if not text:
            return
        ansicht.name = text
        state.ansicht_speichern(ansicht)
        state.ansicht_setzen(ansicht)
        nachher.danach(
            lambda: page.show_dialog(ft.SnackBar(ft.Text(f"Ansicht „{text}“ gespeichert.")))
        )
        nachher.danach(geaendert)
        schliessen(dialog)

    dialog = ft.AlertDialog(
        title=ft.Text("Ansicht speichern"),
        content=name,
        on_dismiss=nachher.bei_schliessen,
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
            ft.FilledButton("Speichern", on_click=speichern),
        ],
    )
    return dialog


__all__ = [
    "BEREICH_TITEL",
    "FARBEN",
    "Werteachse",
    "Zeitachse",
    "ansicht_menue",
    "bereich_wahl",
    "bezeichnung",
    "chips",
    "darstellung_blatt",
    "darstellung_knopf",
    "diagramme",
    "fenster_lesen",
    "fenster_text",
    "kurvengruppen",
    "speichern_dialog",
    "werte_bei",
]
