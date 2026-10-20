"""Vollbild der Kurven (quer) — Bausteine für Live und Aufzeichnung (Ben, 16.10.2026).

Beide Vollbilder — `views.live_vollbild` und der Vollbild-Modus von
`views.messung_detail` — sind gleich aufgebaut:

- **Kopfzeile:** Schließen, links ‹ Kurve der linken Achse ▾ ›, in der Mitte das
  Zeitfenster, rechts ‹ Kurve der rechten Achse ▾ ›. Gewechselt wird über die
  Pfeile oder die Liste dahinter (`seiten_wahl`) — nicht mehr durch Wischen
  hoch/runter, das beim Zeitwischen dazwischenfuhr. Waagrecht wischen blättert
  weiter in der Zeit.
- **Zwei y-Achsen** wie in praxis_gui (`Ansicht.links`/`Ansicht.rechts`,
  `doppelkurve`): links standardmäßig die Rohkurve (RR- bzw. PPI-Tachogramm),
  rechts RMSSD. Je Seite eine Skala; Kurven gleicher Achse teilen sie (HF Gerät
  und Ø HF). Wählbar ist jede Verlaufskurve der angebotenen Analysebereiche —
  auch über Bereiche hinweg, z. B. RMSSD links und DFA α1 rechts. Fenster und
  Darstellung je Kurve sind dieselben wie unter der Hauptkurve.
- **Werkzeugleiste** rechts, senkrecht (`werkzeug`): Ablesen, Notiz ohne Text,
  Notizen, in der Aufzeichnung auch Abschnitte und Zuschneiden, dazu Fenster &
  Darstellung. Was bearbeitet wird, steht in einer Seitenleiste daneben — mit
  denselben Feldern wie hochkant.
- **Etikett** (`etikett`): Ein Tipp auf eine Notizmarke zeigt Zeit und Text in
  der Kurve, ein Tipp auf einen Abschnittsbalken dessen Werte; daneben
  Bearbeiten und Löschen. Ablesen zeigt seine Werte ebenso über der Kurve
  (`ablese_karte`), statt der Kurve unten Höhe zu nehmen.

Gerechnet wird hier nichts: Die Punkte kommen über ``daten`` (`verlauf`) und
``roh`` von der Ansicht.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft
from hrv_core.trends import KENNZAHLEN, titel, treppe

from trainingsapp.core.hrv_ansicht import BLOCK, LINKS, RECHTS, ROH, Ansicht
from trainingsapp.ui.components.kacheln import zahl
from trainingsapp.ui.components.kurve import ACHSE_PX, RR_SPANNE_MIN_MS, Reihe, Skala, kurve
from trainingsapp.ui.components.verlauf import (
    BEREICH_TITEL,
    Daten,
    bezeichnung,
    schritt_min,
    werte_bei,
)
from trainingsapp.ui.farben import FARBEN

#: Breite der Werkzeugleiste rechts und der Seitenleiste daneben (px)
LEISTE_PX = 48
SEITE_PX = 330
#: Breite eines Etiketts und der Ablesewerte über der Kurve (px)
ETIKETT_PX = 250
ABLESEN_PX = 330
#: Höhe der Zeitachse unter der Zeichenfläche (``label_size`` der x-Achse, px)
ZEITACHSE_PX = 22


# ---------------------------------------------------------------------------
# Welche Kurven es gibt
# ---------------------------------------------------------------------------


def angebot(bereiche: Sequence[str], ohne: Sequence[str], *, roh: bool) -> list[str]:
    """Die wählbaren Kurven: das Tachogramm (falls es RR gibt), dann je Bereich seine.

    >>> angebot(["zeit"], ["hf_rr"], roh=True)[:4]
    ['roh', 'hf_geraet', 'mean_rr', 'rmssd']
    >>> angebot(["zeit"], [k for k in KENNZAHLEN if k != "hf_geraet"], roh=False)
    ['hf_geraet']
    """
    out = [ROH] if roh else []
    out += [k for k, kz in KENNZAHLEN.items() if kz.bereich in bereiche and k not in ohne]
    return out


def achse(kennzahl: str) -> str | None:
    """Schlüssel der Werteachse — das Tachogramm teilt seine mit Ø RR.

    >>> achse("roh") == achse("mean_rr"), achse("rmssd") == achse("sdnn"), achse("x")
    (True, True, None)
    """
    if kennzahl == ROH:
        return KENNZAHLEN["mean_rr"].achse_schluessel
    kz = KENNZAHLEN.get(kennzahl)
    return kz.achse_schluessel if kz else None


def farbe(kennzahl: str) -> str:
    return ft.Colors.PRIMARY if kennzahl == ROH else FARBEN[kennzahl]


def name(kennzahl: str, pnn_ms: float, roh_titel: str) -> str:
    return roh_titel if kennzahl == ROH else titel(kennzahl, pnn_ms)


def rechts_px(ansicht: Ansicht, angebot_: Sequence[str]) -> float:
    """So breit ist die rechte Achse (px) — 0, wenn rechts nichts steht."""
    return ACHSE_PX if ansicht.achsen(angebot_)[1] else 0.0


# ---------------------------------------------------------------------------
# Die Kurve mit zwei Achsen
# ---------------------------------------------------------------------------


def doppelkurve(
    ansicht: Ansicht,
    daten: Daten,
    roh: Callable[[], list[Reihe]],
    *,
    angebot: Sequence[str],
    x_von: float,
    x_bis: float,
    hoehe: int,
    roh_einheit: str,
    marken: Sequence[Reihe] = (),
    hinten: Sequence[Reihe] = (),
    gesehen: dict[str, tuple[str, list[tuple[float, float]]]] | None = None,
    x_text: Callable[[float], str] | None = None,
    x_null: float = 0.0,
) -> ft.Control:
    """Die Kurven der linken und der rechten Achse in einem Diagramm.

    ``roh`` liefert die Reihen des Tachogramms (grau, gewertet, auffällig) für
    den Ausschnitt; ``daten`` die Punkte jeder Verlaufskurve (Fenster und
    Blöcke wie in `Ansicht`). ``marken`` (Notizen, Ablesestrich) liegen über
    den Kurven, ``hinten`` (Zuschnitt, Abschnittsbalken) darunter — beide
    gehören zur linken Achse. ``gesehen`` bekommt je Verlaufskurve Bezeichnung
    und Punkte — zum Ablesen. ``x_text``/``x_null``: Beschriftung der Zeitachse
    (`kurve`), etwa Uhrzeiten statt Dauern.
    """
    links, rechts = ansicht.achsen(angebot)

    def seite(kurven: list[str]) -> tuple[list[Reihe], str, float, float, str | None]:
        reihen: list[Reihe] = []
        spanne, kennzahlen = 0.0, []
        for k in kurven:
            if k == ROH:
                reihen += roh()
                spanne = max(spanne, RR_SPANNE_MIN_MS)
                continue
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
            spanne = max(spanne, kz.spanne_min)
            kennzahlen.append(k)
        erste = kurven[0] if kurven else ROH
        einheit = (
            roh_einheit if erste == ROH else KENNZAHLEN[erste].einheit or KENNZAHLEN[erste].titel
        )
        schritt = schritt_min(kennzahlen) if kennzahlen and ROH not in kurven else 1.0
        return reihen, einheit, spanne, schritt, farbe(erste) if len(kurven) == 1 else None

    l_reihen, l_einheit, l_spanne, l_schritt, l_farbe = seite(links)
    zweite = None
    if rechts:
        r_reihen, r_einheit, r_spanne, r_schritt, r_farbe = seite(rechts)
        zweite = Skala(r_reihen, r_einheit, r_spanne, r_schritt, r_farbe)
    return kurve(
        [*hinten, *l_reihen, *marken],
        einheit=l_einheit,
        hoehe=hoehe,
        x_von=x_von,
        x_bis=x_bis,
        y_spanne_min=l_spanne,
        y_schritt_min=l_schritt,
        x_text=x_text,
        x_null=x_null,
        rechts=zweite,
        farbe=l_farbe,
    )


# ---------------------------------------------------------------------------
# Kopfzeile: Kurve je Achse wählen
# ---------------------------------------------------------------------------


def seiten_wahl(
    state: Any,
    seite: str,
    angebot_: Sequence[str],
    roh_titel: str,
    geaendert: Callable[[], None],
) -> ft.Control:
    """‹ Name ▾ › einer Achse: Pfeile blättern, die Liste wählt.

    In der Liste stehen die Kurven je Analysebereich mit ihrer Einheit; ein Tipp
    nimmt eine Kurve dazu (gleiche Skala), ersetzt die Seite (andere Skala),
    nimmt sie weg (schon gewählt) oder tauscht die Seiten (steht drüben).
    ``state`` ist der `AppState` — die Wahl gehört zur Ansicht und bleibt.
    """
    ansicht = state.ansicht()
    links, rechts = ansicht.achsen(angebot_)
    hier = links if seite == LINKS else rechts
    drueben = rechts if seite == LINKS else links
    wort = "Linke" if seite == LINKS else "Rechte"

    def aendern(was: Callable[[Ansicht], None]) -> Callable[[], None]:
        def handler() -> None:
            a = state.ansicht()
            was(a)
            state.ansicht_setzen(a)
            geaendert()

        return handler

    def waehlen(k: str) -> Callable[[], None]:
        return aendern(lambda a: a.achse_waehlen(seite, k, achse))

    def blaettern(schritt: int) -> Callable[[], None]:
        return aendern(lambda a: a.achse_blaettern(seite, schritt, angebot_))

    eintraege: list[ft.PopupMenuItem] = []
    if seite == RECHTS:
        eintraege.append(
            ft.PopupMenuItem(
                content="Keine Kurve rechts",
                checked=not rechts,
                on_click=aendern(lambda a: a.rechts_leeren()),
            )
        )
    bereich = None
    for k in angebot_:
        neu = "roh" if k == ROH else KENNZAHLEN[k].bereich
        if neu != bereich:
            bereich = neu
            eintraege.append(_ueberschrift("ROHDATEN" if k == ROH else BEREICH_TITEL[neu].upper()))
        eintraege.append(
            ft.PopupMenuItem(
                content=_eintrag(
                    k,
                    ansicht,
                    roh_titel,
                    drueben=("rechts" if seite == LINKS else "links") if k in drueben else "",
                ),
                checked=k in hier,
                on_click=waehlen(k),
            )
        )
    eintraege += [
        ft.PopupMenuItem(),
        ft.PopupMenuItem(
            content="Seiten tauschen",
            icon=ft.Icons.SWAP_HORIZ,
            on_click=aendern(lambda a: a.seiten_tauschen()),
        ),
    ]
    beschriftung = (
        [*(_punkt(farbe(k)) for k in hier[:3]), ft.Text(_namen(hier, ansicht, roh_titel), size=13)]
        if hier
        else [ft.Text("keine", size=13, opacity=0.6)]
    )
    return ft.Row(
        spacing=0,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.IconButton(
                ft.Icons.CHEVRON_LEFT,
                tooltip=f"{wort} Achse: vorige Kurve",
                visual_density=ft.VisualDensity.COMPACT,
                on_click=blaettern(-1),
            ),
            ft.PopupMenuButton(
                tooltip=f"{wort} Achse: Kurven wählen",
                menu_position=ft.PopupMenuPosition.UNDER,
                content=ft.Row(
                    spacing=4,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[*beschriftung, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18)],
                ),
                items=eintraege,
            ),
            ft.IconButton(
                ft.Icons.CHEVRON_RIGHT,
                tooltip=f"{wort} Achse: nächste Kurve",
                visual_density=ft.VisualDensity.COMPACT,
                on_click=blaettern(1),
            ),
        ],
    )


def _namen(kurven: Sequence[str], ansicht: Ansicht, roh_titel: str) -> str:
    """„RMSSD · SDNN", ab drei Kurven „LF-Band +2" — passt in die Kopfzeile.

    >>> _namen(["rmssd", "sdnn"], Ansicht(), "RR"), _namen(["lf_power", "hf_power", "vlf_power"],
    ...     Ansicht(), "RR")
    ('RMSSD · SDNN', 'LF-Band +2')
    """
    namen = [name(k, ansicht.pnn_ms, roh_titel) for k in kurven]
    return " · ".join(namen) if len(namen) <= 2 else f"{namen[0]} +{len(namen) - 1}"


def _eintrag(k: str, ansicht: Ansicht, roh_titel: str, *, drueben: str) -> ft.Control:
    """Eine Kurve in der Liste: Farbe, Name mit Fenster, Einheit — und ob sie drüben steht."""
    einheit = "ms" if k == ROH else KENNZAHLEN[k].einheit
    return ft.Row(
        spacing=6,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            _punkt(farbe(k)),
            ft.Text(roh_titel if k == ROH else bezeichnung(k, ansicht), size=13),
            ft.Text(einheit, size=11, opacity=0.6),
            *([ft.Text(f"· {drueben}", size=11, opacity=0.6)] if drueben else []),
        ],
    )


def _ueberschrift(text: str) -> ft.PopupMenuItem:
    return ft.PopupMenuItem(
        content=ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.6), height=28
    )


def _punkt(farbe_: str) -> ft.Control:
    return ft.Container(width=10, height=10, border_radius=5, bgcolor=farbe_)


# ---------------------------------------------------------------------------
# Werkzeugleiste, Seitenleiste, Etikett
# ---------------------------------------------------------------------------


def werkzeug(
    icon: ft.IconData, tooltip: str, on_click: Callable[[], Any], *, aktiv: bool = False
) -> ft.IconButton:
    """Ein Knopf der Werkzeugleiste — getönt, solange sein Werkzeug an ist."""
    knopf = ft.IconButton(icon, tooltip=tooltip, on_click=on_click)
    markieren(knopf, aktiv)
    return knopf


def markieren(knopf: ft.IconButton, aktiv: bool) -> None:
    knopf.style = (
        ft.ButtonStyle(bgcolor=ft.Colors.with_opacity(0.16, ft.Colors.PRIMARY)) if aktiv else None
    )


def leiste(*knoepfe: ft.Control) -> ft.Control:
    """Die Werkzeugleiste rechts — senkrecht, quer ist Breite übrig, Höhe nicht."""
    return ft.Container(
        width=LEISTE_PX,
        content=ft.Column(
            spacing=2,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=list(knoepfe),
        ),
    )


def seitenkopf(text: str, schliessen: Callable[[], None]) -> ft.Control:
    """Überschrift der Seitenleiste mit ✕."""
    return ft.Row(
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(text.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.7, expand=True),
            ft.IconButton(ft.Icons.CLOSE, icon_size=18, tooltip="Schließen", on_click=schliessen),
        ],
    )


def lage_px(
    x: float, x_von: float, x_bis: float, breite_px: float, rechts: float, kasten: float
) -> float:
    """Linker Rand (px) eines Kastens, der über der Stelle ``x`` der Kurve steht.

    ``breite_px``: die ganze Breite der Kurve samt Achsen; ``rechts``: Breite
    der rechten Achse. Der Kasten bleibt im Bild.

    >>> lage_px(50.0, 0.0, 100.0, 452.0, 0.0, 250.0)  # Mitte der Zeichenfläche
    127.0
    >>> lage_px(0.0, 0.0, 100.0, 452.0, 0.0, 250.0), lage_px(100.0, 0.0, 100.0, 452.0, 0.0, 250.0)
    (0.0, 202.0)
    """
    flaeche = max(breite_px - ACHSE_PX - rechts, 1.0)
    anteil = min(max((x - x_von) / max(x_bis - x_von, 1e-9), 0.0), 1.0)
    mitte = ACHSE_PX + anteil * flaeche
    return round(min(max(mitte - kasten / 2, 0.0), max(breite_px - kasten, 0.0)), 1)


def etikett(
    kopf: str,
    text: str,
    farbe_: str,
    knoepfe: Sequence[ft.Control],
    *,
    zeilen: Sequence[str] = (),
) -> ft.Control:
    """Ein kleiner Kasten in der Kurve: Zeit bzw. Name, Text, darunter die Knöpfe."""
    return ft.Container(
        width=ETIKETT_PX,
        padding=ft.Padding.only(left=10, right=4, top=6, bottom=2),
        border_radius=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(1.5, farbe_),
        shadow=ft.BoxShadow(blur_radius=8, color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK)),
        content=ft.Column(
            spacing=2,
            tight=True,
            controls=[
                ft.Text(kopf, size=11, opacity=0.75, max_lines=1),
                ft.Text(text, size=14, weight=ft.FontWeight.W_600, max_lines=3)
                if text
                else ft.Text("(ohne Text)", size=13, italic=True, opacity=0.6),
                *(ft.Text(z, size=11, opacity=0.75) for z in zeilen),
                ft.Row(spacing=0, alignment=ft.MainAxisAlignment.END, controls=list(knoepfe)),
            ],
        ),
    )


def etikett_knopf(icon: ft.IconData, tooltip: str, aktion: Callable[[], None]) -> ft.Control:
    """Ein Knopf im Etikett (Bearbeiten, Löschen, Schließen)."""
    return ft.IconButton(icon, icon_size=20, tooltip=tooltip, on_click=lambda: aktion())


def notiz_etikett(
    zeit: str,
    text: str,
    farbe_: str,
    *,
    bearbeiten: Callable[[], None],
    loeschen: Callable[[], None],
    schliessen: Callable[[], None],
) -> ft.Control:
    """Das Etikett einer Notizmarke mit Bearbeiten, Löschen, Schließen — Live und
    Auswertung zeigen dasselbe (N28)."""
    return etikett(
        zeit,
        text,
        farbe_,
        [
            etikett_knopf(ft.Icons.EDIT_OUTLINED, "Notiz bearbeiten", bearbeiten),
            etikett_knopf(ft.Icons.DELETE_OUTLINE, "Notiz löschen", loeschen),
            etikett_knopf(ft.Icons.CLOSE, "Etikett schließen", schliessen),
        ],
    )


#: Eine abgelesene Zeile: Farbe, Name, Zahl, Einheit (`wertchip`).
Ablesewert = tuple[str | None, str, str, str]


def intervall_werte(rr_ms: float | None, zusatz: str, *, verity: bool) -> list[Ablesewert]:
    """RR bzw. PPI und die Herzfrequenz daraus — leer ohne Intervall."""
    if rr_ms is None:
        return []
    return [
        (ft.Colors.PRIMARY, "PPI" if verity else "RR", zahl(rr_ms), "ms" + zusatz),
        (FARBEN["hf_rr"], "HF", zahl(60000 / rr_ms if rr_ms else None), "bpm"),
    ]


def geraet_wert(hf_reihe: Sequence[tuple[float, float]], x: float) -> list[Ablesewert]:
    """„HF Gerät“ am nächsten Gerätewert, wenn er höchstens 3 s entfernt liegt."""
    geraet = min(hf_reihe, key=lambda p: abs(p[0] - x), default=None)
    if geraet is None or abs(geraet[0] - x) >= 3:
        return []
    return [(FARBEN["hf_geraet"], "HF Gerät", zahl(geraet[1]), "bpm")]


def kennzahl_werte(
    gesehen: dict[str, tuple[str, list[tuple[float, float]]]], x: float, *, ohne: Sequence[str] = ()
) -> list[Ablesewert]:
    """Die gezeichneten Verlaufskurven an der Stelle ``x``, Stellenzahl nach Größe."""
    werte: list[Ablesewert] = []
    for k, name_, wert in werte_bei(gesehen, x):
        if k in ohne:
            continue
        stellen = 0 if abs(wert) >= 100 else 1 if abs(wert) >= 10 else 2
        werte.append((FARBEN.get(k), name_, zahl(wert, stellen), KENNZAHLEN[k].einheit))
    return werte


def wertchip(farbe_: str | None, name_: str, wert: str, einheit: str) -> ft.Control:
    """Ein abgelesener Wert: Farbpunkt, Name, Zahl, Einheit."""
    return ft.Row(
        spacing=4,
        tight=True,
        controls=[
            ft.Container(width=8, height=8, border_radius=4, bgcolor=farbe_ or ft.Colors.OUTLINE),
            ft.Text(name_, size=11, opacity=0.7),
            ft.Text(wert, size=13, weight=ft.FontWeight.W_600),
            ft.Text(einheit, size=11, opacity=0.7),
        ],
    )


def ablese_karte(
    kopfzeile: str,
    nebenbei: str,
    werte: Sequence[tuple[str | None, str, str, str]],
    *,
    schritt: Callable[[int], None],
    schliessen: Callable[[], None],
    schwebend: bool = False,
) -> ft.Control:
    """Die Werte an der Ablesestelle: ‹ Zeit ›, was dort liegt, ✕ — darunter je Wert ein Chip.

    ``schwebend``: als Kasten über der Kurve (Vollbild) statt als Fläche darunter.
    """
    return ft.Container(
        width=ABLESEN_PX if schwebend else None,
        border_radius=10,
        padding=ft.Padding.only(left=4, right=4, top=2, bottom=8),
        bgcolor=(
            ft.Colors.SURFACE_CONTAINER_HIGHEST
            if schwebend
            else ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE)
        ),
        shadow=(
            ft.BoxShadow(blur_radius=8, color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK))
            if schwebend
            else None
        ),
        content=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Row(
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.IconButton(
                            ft.Icons.CHEVRON_LEFT,
                            tooltip="Ein Schlag zurück",
                            on_click=lambda: schritt(-1),
                        ),
                        ft.Text(kopfzeile, size=14, weight=ft.FontWeight.W_600),
                        ft.IconButton(
                            ft.Icons.CHEVRON_RIGHT,
                            tooltip="Ein Schlag weiter",
                            on_click=lambda: schritt(1),
                        ),
                        ft.Text(
                            nebenbei,
                            size=12,
                            opacity=0.7,
                            expand=True,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.IconButton(
                            ft.Icons.CLOSE,
                            icon_size=18,
                            tooltip="Ablesen beenden",
                            on_click=lambda: schliessen(),
                        ),
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10),
                    content=ft.Row(
                        wrap=True,
                        spacing=14,
                        run_spacing=4,
                        controls=[wertchip(*w) for w in werte],
                    ),
                ),
            ],
        ),
    )


def ablese_seite(
    box: ft.Container, x: float, x_von: float, x_bis: float, rechts: float = 0.0
) -> None:
    """Die schwebenden Ablesewerte stehen auf der Seite, auf der der Strich nicht ist.

    ``rechts``: Breite der rechten Achse — ihre Zahlen bleiben frei.
    """
    links_vom_strich = (x - x_von) > (x_bis - x_von) / 2
    box.left, box.right = (ACHSE_PX + 4, None) if links_vom_strich else (None, rechts + 4)
    box.top = 4


__all__ = [
    "ABLESEN_PX",
    "ETIKETT_PX",
    "LEISTE_PX",
    "SEITE_PX",
    "ZEITACHSE_PX",
    "ablese_karte",
    "ablese_seite",
    "achse",
    "angebot",
    "doppelkurve",
    "etikett",
    "farbe",
    "lage_px",
    "leiste",
    "markieren",
    "name",
    "rechts_px",
    "seiten_wahl",
    "seitenkopf",
    "werkzeug",
    "wertchip",
]
