"""Die Herzfrequenz-Sicht der Live-Karte (Ben, 29.10.2026; hrv-research `KONZEPT_HF_APP.md`
§4.2, Entscheidung 10): große Zahl mit %HRR und Bereich, die Skala Ruhe-HF … HFmax mit den
Bereichen und ihrem Unsicherheitsband, die Zeit je Bereich für den gewählten Bezug
(Aufnahme · Abschnitt · 5 min), die HF-Erholung ab einem Belastungsende.

**Die HF ist der Träger, nicht das Urteil** (`docs/recht/00_zweckbestimmung.md`): Bereiche
heißen „Bereich 1…n“ oder wie die Person sie nennt, die Farben sind Stufen **einer** Farbe
(keine Ampel), das Unsicherheitsband ist eine Breite, kein Hinweis, und eine geschätzte HFmax
trägt „geschätzt ±…“. Die Rechnung steht in `hrv_core.herzfrequenz` und `core.hf_training`;
hier wird nur gebaut.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft
from hrv_core import herzfrequenz as hz

from trainingsapp.core.hf_einstellungen import (
    ACHSE_AUTO,
    ACHSE_FEST,
    ACHSE_PROFIL,
    ALARM_MAX_BPM,
    ALARM_MIN_BPM,
    ALARM_TAKT_S,
    ERHOLUNG_FENSTER_S,
    ERHOLUNG_X_MAX_S,
    ERHOLUNG_X_MIN_S,
    MESSEN_BIS_S,
    TAKT_NACH_ABSTAND,
    HfEinstellungen,
)
from trainingsapp.core.hf_profil import HfProfil, bereich_von
from trainingsapp.core.hf_training import BEZUEGE, BEZUG_ABSCHNITT, BEZUG_NAMEN
from trainingsapp.core.hf_ziel import (
    BEZUG_NAMEN as INTERVALL_BEZUG_NAMEN,
)
from trainingsapp.core.hf_ziel import (
    TONFOLGE,
    dauer_kurz,
    delta_text,
    hrr_text,
    tal_hinweis,
    ziel_grenzen,
    ziel_text,
)
from trainingsapp.core.klang import KLAENGE
from trainingsapp.core.laufend import minuten
from trainingsapp.ui.components.kacheln import KachelWert, zahl
from trainingsapp.ui.components.kurve import Band

#: Route des Einstellungsbereichs „Herzfrequenz“ (Shortlink aus der Messung)
EINSTELLUNGEN = "/einstellungen/herzfrequenz"
#: Höhe der Skala (px)
SKALA_PX = 22
#: Deckkraft der Bereichsstufen: eine Farbe, heller nach dunkler — keine Ampel
_DECKKRAFT = (0.18, 0.30, 0.42, 0.54, 0.66, 0.74, 0.80, 0.86, 0.92, 0.98)

KONTEXT_NAMEN: dict[str, str] = {
    "dauer": "Dauerbelastung",
    "intervall": "Intervall",
    "sprint": "Sprint",
    "satz": "Satz",
    "test_submaximal": "Test (submaximal)",
    "test_maximal": "Test (maximal)",
}
HALTUNG_NAMEN: dict[str, str] = {
    "steht": "steht",
    "sitzt": "sitzt",
    "liegt": "liegt",
    "geht": "geht / läuft aus",
}


def bandfarbe(i: int, n: int) -> str:
    """Die blasse Füllung des ``i``-ten von ``n`` Bereichen hinter einer Kurve — heller als
    `stufenfarbe`, damit die Linie lesbar bleibt; nach oben hin kräftiger."""
    if n <= 1:
        return ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY)
    return ft.Colors.with_opacity(0.06 + 0.16 * i / (n - 1), ft.Colors.PRIMARY)


def hf_baender(bereiche: Sequence[hz.Bereich]) -> list[Band]:
    """Die Bereiche als Bänder für `kurve` (Ben, 30.10.2026: Belastungszonen im
    Koordinatensystem, rechts die Namen)."""
    n = len(bereiche)
    return [Band(b.von_bpm, b.bis_bpm, bandfarbe(i, n), b.name) for i, b in enumerate(bereiche)]


def stufenfarbe(i: int, n: int) -> str:
    """Die Farbe des ``i``-ten von ``n`` Bereichen: eine Farbe in Stufen.

    >>> stufenfarbe(0, 3) != stufenfarbe(2, 3), stufenfarbe(9, 10) == stufenfarbe(9, 10)
    (True, True)
    """
    if n <= 1:
        return ft.Colors.with_opacity(0.5, ft.Colors.PRIMARY)
    schritt = (len(_DECKKRAFT) - 1) / (n - 1)
    return ft.Colors.with_opacity(_DECKKRAFT[round(i * schritt)], ft.Colors.PRIMARY)


def prozent_text(p: float | None) -> str:
    return "–" if p is None else f"{p:.0f} %"


def hf_kopf(
    hf: float | None,
    profil: HfProfil,
    bereiche: Sequence[hz.Bereich],
    *,
    einstellungen: Callable[[], Any],
) -> ft.Control:
    """Große Zahl, rechts %HRR und der Name des Bereichs — oder der Weg zum Profil."""
    b = bereich_von(hf, list(bereiche))
    rechts: list[ft.Control]
    if profil.vollstaendig:
        rechts = [
            ft.Text(prozent_text(profil.prozent(hf)), size=22, weight=ft.FontWeight.W_600),
            ft.Text(
                "der Reserve" + (" · HFmax geschätzt" if profil.hfmax_geschaetzt else ""),
                size=11,
                opacity=0.6,
            ),
            ft.Text(b.name if b is not None else "", size=13, opacity=0.8),
        ]
    else:
        rechts = [
            ft.TextButton(
                "Ruhe-HF und HFmax eintragen",
                icon=ft.Icons.PERSON_OUTLINE,
                on_click=lambda _=None: einstellungen(),
            ),
            ft.Text("Erst dann gibt es % der Reserve und Bereiche.", size=11, opacity=0.6),
        ]
    return ft.Row(
        spacing=14,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Row(
                spacing=4,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.END,
                controls=[
                    ft.Text(zahl(hf), size=44, weight=ft.FontWeight.BOLD),
                    ft.Text("bpm", size=13, opacity=0.65),
                ],
            ),
            ft.Column(spacing=0, tight=True, expand=True, controls=rechts),
        ],
    )


def skala(bereiche: Sequence[hz.Bereich], profil: HfProfil, hf: float | None) -> ft.Control:
    """Balken von Ruhe-HF bis HFmax: Bereiche als Stufen, Grenzen mit Band, Zeiger bei ``hf``."""
    if not bereiche or not profil.vollstaendig:
        return ft.Container()
    ruhe, hfmax = float(profil.ruhe_bpm), float(profil.hfmax_bpm)  # type: ignore[arg-type]
    spanne = hfmax - ruhe
    n = len(bereiche)
    stufen = ft.Row(
        spacing=0,
        controls=[
            ft.Container(
                expand=max(1, round((b.bis_bpm - b.von_bpm) / spanne * 1000)),
                height=SKALA_PX,
                bgcolor=stufenfarbe(i, n),
                tooltip=f"{b.name}: {b.von_bpm:.0f}–{b.bis_bpm:.0f} bpm",
            )
            for i, b in enumerate(bereiche)
        ],
    )
    ebenen: list[ft.Control] = [
        ft.Container(content=stufen, border_radius=6, clip_behavior=ft.ClipBehavior.ANTI_ALIAS)
    ]
    # Unsicherheitsband je innerer Grenze: eine helle Breite, kein Hinweis
    for b in bereiche[:-1]:
        if b.unsicherheit_bpm <= 0:
            continue
        mitte = (b.bis_bpm - ruhe) / spanne
        breite = min(1.0, 2 * b.unsicherheit_bpm / spanne)
        ebenen.append(
            ft.Container(
                alignment=ft.Alignment(max(-1.0, min(1.0, mitte * 2 - 1)), 0),
                content=ft.Container(
                    width=max(4.0, breite * 300),
                    height=SKALA_PX,
                    bgcolor=ft.Colors.with_opacity(0.35, ft.Colors.ON_PRIMARY),
                    tooltip=f"±{b.unsicherheit_bpm:.0f} bpm",
                ),
            )
        )
    if hf is not None:
        x = (float(hf) - ruhe) / spanne
        ebenen.append(
            ft.Container(
                alignment=ft.Alignment(max(-1.0, min(1.0, x * 2 - 1)), 0),
                content=ft.Container(
                    width=3,
                    height=SKALA_PX + 8,
                    bgcolor=ft.Colors.ON_SURFACE,
                    border_radius=2,
                ),
            )
        )
    beschriftung = ft.Row(
        controls=[
            ft.Text(f"Ruhe {ruhe:.0f}", size=11, opacity=0.65),
            ft.Text(
                f"HFmax {hfmax:.0f}"
                + (
                    f" (geschätzt ±{profil.hfmax_unsicherheit:.0f})"
                    if profil.hfmax_geschaetzt
                    else ""
                ),
                size=11,
                opacity=0.65,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )
    return ft.Column(
        spacing=4,
        tight=True,
        controls=[ft.Stack(controls=ebenen, height=SKALA_PX + 8), beschriftung],
    )


def zeit_je_bereich(sekunden: Sequence[float] | None, bereiche: Sequence[hz.Bereich]) -> ft.Control:
    """Gestapelter Balken plus Zeile je Bereich (Name · Minuten · Anteil)."""
    if not bereiche or sekunden is None or len(sekunden) != len(bereiche):
        return ft.Text("Noch keine Zeit im Bezug.", size=12, opacity=0.6)
    gesamt = float(sum(sekunden))
    if gesamt <= 0:
        return ft.Text("Noch keine Zeit im Bezug.", size=12, opacity=0.6)
    n = len(bereiche)
    balken = ft.Row(
        spacing=0,
        controls=[
            ft.Container(
                expand=max(1, round(s / gesamt * 1000)),
                height=10,
                bgcolor=stufenfarbe(i, n),
            )
            for i, s in enumerate(sekunden)
            if s > 0
        ],
    )
    zeilen = [
        ft.Row(
            spacing=8,
            controls=[
                ft.Container(width=10, height=10, bgcolor=stufenfarbe(i, n), border_radius=2),
                ft.Text(b.name, size=12, expand=True),
                ft.Text(minuten(s), size=12),
                ft.Text(f"{s / gesamt * 100:.0f} %", size=12, opacity=0.65, width=40),
            ],
        )
        for i, (b, s) in enumerate(zip(bereiche, sekunden, strict=True))
    ]
    return ft.Column(
        spacing=4,
        tight=True,
        controls=[
            ft.Container(content=balken, border_radius=4, clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
            *zeilen,
        ],
    )


def bezug_wahl(
    bezug: str, waehlen: Callable[[str], None], *, abschnitt_laeuft: bool
) -> ft.SegmentedButton:
    """Aufnahme · Abschnitt · 5 min — der Bezug der Zeit je Bereich und der Kacheln."""

    def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            waehlen(str(e.control.selected[0]))

    return ft.SegmentedButton(
        selected=[bezug],
        show_selected_icon=False,
        on_change=gewaehlt,
        segments=[
            ft.Segment(
                value=b,
                label=ft.Text(BEZUG_NAMEN[b], size=12),
                disabled=(b == BEZUG_ABSCHNITT and not abschnitt_laeuft),
            )
            for b in BEZUEGE
        ],
    )


def sicht_wahl(
    sicht: str, waehlen: Callable[[str], None], *, hrv_moeglich: bool
) -> ft.SegmentedButton:
    """Der Umschalter ``[ Herzfrequenz | HRV ]`` über der Hauptkarte."""

    def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            waehlen(str(e.control.selected[0]))

    return ft.SegmentedButton(
        selected=[sicht],
        show_selected_icon=False,
        on_change=gewaehlt,
        segments=[
            ft.Segment(
                value="hf", label=ft.Text("Herzfrequenz"), icon=ft.Icon(ft.Icons.FAVORITE_BORDER)
            ),
            ft.Segment(
                value="hrv",
                label=ft.Text("HRV"),
                icon=ft.Icon(ft.Icons.SHOW_CHART),
                disabled=not hrv_moeglich,
                tooltip=None if hrv_moeglich else "Gerät sendet nur den Puls",
            ),
        ],
    )


def takt_name(takt_s: int) -> str:
    """Beschriftung einer Tonfolge: „nach Abstand“ oder „alle 4 s“."""
    return "nach Abstand" if takt_s == TAKT_NACH_ABSTAND else f"alle {takt_s} s"


def alarm_text(e: HfEinstellungen) -> str:
    """„Zielbereich 130–150 · Ton an“ — leer, wenn kein Ton gilt."""
    if not e.alarm_an or (e.alarm_grenze() is None and e.ziel_unten() is None):
        return ""
    return f"Zielbereich {ziel_text(e)} · Ton an"


def alarm_zeilen(
    state: Any,
    *,
    vorspielen: Callable[[str], None] | None = None,
    geaendert: Callable[[], None] | None = None,
) -> list[ft.Control]:
    """Ton außerhalb eines selbst gesetzten Zielbereichs (Ben, 30.10.2026: „piepen alle 3–5
    Sekunden, wenn man über einer bestimmten HF ist … nicht aufdringlich“; 7.11.2026,
    Entscheidung C: auch darunter, mit tieferem Klang): Schalter, Grenzen in bpm, Takt und
    Klänge — je Profil (`HfEinstellungen`). Steht im Blatt der Live-Sicht und unter
    Einstellungen → Herzfrequenz; ``vorspielen`` spielt den gewählten Klang zur Probe. Nur
    Information, keine Steuerung (`docs/recht/00_zweckbestimmung.md`).
    """
    e = state.hf_einstellungen()
    feld = ft.TextField(
        label="darüber",
        suffix=ft.Text("bpm"),
        value=f"{e.alarm_bpm:g}" if e.alarm_bpm else "",
        dense=True,
        width=130,
        border=ft.OutlineInputBorder(border_radius=8),
        keyboard_type=ft.KeyboardType.NUMBER,
        text_align=ft.TextAlign.RIGHT,
    )

    def speichern() -> None:
        state.hf_einstellungen_setzen(e)
        if geaendert is not None:
            geaendert()

    def grenze_uebernehmen(_ev: object = None) -> None:
        roh = (feld.value or "").strip().replace(",", ".")
        if not roh:
            e.alarm_bpm = None
            feld.error = None
        else:
            try:
                wert = float(roh)
            except ValueError:
                wert = -1.0
            if ALARM_MIN_BPM <= wert <= ALARM_MAX_BPM:
                e.alarm_bpm, feld.error = wert, None
            else:
                feld.error = f"{ALARM_MIN_BPM:.0f} bis {ALARM_MAX_BPM:.0f} bpm"
        speichern()
        with contextlib.suppress(Exception):
            feld.update()

    def umgeschaltet(ev: ft.Event[ft.Switch]) -> None:
        e.alarm_an = bool(ev.control.value)
        grenze_uebernehmen()

    def takt_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        if ev.control.value is not None:
            e.alarm_takt_s = int(ev.control.value)
            speichern()

    def klang_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        if ev.control.value:
            e.alarm_klang = str(ev.control.value)
            speichern()
            if vorspielen is not None:
                vorspielen(e.alarm_klang)

    feld.on_submit = grenze_uebernehmen
    feld.on_blur = grenze_uebernehmen

    # Zielbereich nach unten (Entscheidung C, 7.11.2026): ein tieferer Ton darunter
    unten = ft.TextField(
        label="darunter",
        suffix=ft.Text("bpm"),
        value=f"{e.ziel_unten_bpm:g}" if e.ziel_unten_bpm else "",
        dense=True,
        width=130,
        border=ft.OutlineInputBorder(border_radius=8),
        keyboard_type=ft.KeyboardType.NUMBER,
        text_align=ft.TextAlign.RIGHT,
        tooltip="Untere Linie des Zielbereichs — leer: nur die obere",
    )

    def unten_uebernehmen(_ev: object = None) -> None:
        roh = (unten.value or "").strip().replace(",", ".")
        if not roh:
            e.ziel_unten_bpm, unten.error = None, None
        else:
            try:
                wert = float(roh)
            except ValueError:
                wert = -1.0
            if ALARM_MIN_BPM <= wert <= ALARM_MAX_BPM:
                e.ziel_unten_bpm, unten.error = wert, None
            else:
                unten.error = f"{ALARM_MIN_BPM:.0f} bis {ALARM_MAX_BPM:.0f} bpm"
        speichern()
        with contextlib.suppress(Exception):
            unten.update()

    def klang_tief_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        if ev.control.value:
            e.alarm_klang_tief = str(ev.control.value)
            speichern()
            if vorspielen is not None:
                vorspielen(e.alarm_klang_tief)

    unten.on_submit = unten_uebernehmen
    unten.on_blur = unten_uebernehmen
    return [
        ft.Switch(label="Ton außerhalb des Zielbereichs", value=e.alarm_an, on_change=umgeschaltet),
        ft.Row(
            spacing=8,
            wrap=True,
            run_spacing=6,
            controls=[
                feld,
                ft.Dropdown(
                    label="Tonfolge",
                    value=str(e.alarm_takt_s),
                    options=[
                        ft.DropdownOption(key=str(x), text=takt_name(x)) for x in ALARM_TAKT_S
                    ],
                    on_select=takt_gewaehlt,
                    dense=True,
                    width=160,
                    border=ft.OutlineInputBorder(border_radius=8),
                ),
                ft.Dropdown(
                    label="Klang darüber",
                    value=e.alarm_klang,
                    options=[
                        ft.DropdownOption(key=k, text=t) for k, t in KLAENGE.items() if k != "ende"
                    ],
                    on_select=klang_gewaehlt,
                    dense=True,
                    width=190,
                    border=ft.OutlineInputBorder(border_radius=8),
                ),
            ],
        ),
        ft.Row(
            spacing=8,
            wrap=True,
            run_spacing=6,
            controls=[
                unten,
                ft.Dropdown(
                    label="Klang darunter",
                    value=e.alarm_klang_tief,
                    options=[
                        ft.DropdownOption(key=k, text=t) for k, t in KLAENGE.items() if k != "ende"
                    ],
                    on_select=klang_tief_gewaehlt,
                    dense=True,
                    width=190,
                    border=ft.OutlineInputBorder(border_radius=8),
                ),
            ],
        ),
        ft.Text(
            "Ein leiser Klang, solange die Herzfrequenz über oder unter deinem Zielbereich "
            "liegt — wie ein Timer, keine Bewertung; die Linien setzt du selbst. „Nach "
            "Abstand“: je weiter weg, desto dichter die Töne (1 bpm alle 6 s … ab 15 bpm jede "
            "Sekunde). Töne gibt es nur in der installierten App.",
            size=11,
            opacity=0.65,
        ),
    ]


def hf_kacheln(
    hf: float | None,
    profil: HfProfil,
    bereiche: Sequence[hz.Bereich],
    zusammenfassung: dict[str, Any] | None,
    bezug_name: str,
) -> list[KachelWert]:
    """Die Werte der Herzfrequenz-Sicht über der Kurve — Bezug in der Beschriftung."""
    b = bereich_von(hf, list(bereiche))
    out = [
        KachelWert("Herzfrequenz", zahl(hf), "bpm", gross=True),
        KachelWert(
            "Reserve",
            prozent_text(profil.prozent(hf)) if profil.vollstaendig else "–",
            zusatz=(b.name if b is not None else ""),
            gross=True,
            grund="" if profil.vollstaendig else "Ruhe-HF und HFmax fehlen",
        ),
    ]
    z = zusammenfassung or {}
    zeit = None
    if (
        b is not None
        and z.get("sekunden_je_bereich")
        and len(z["sekunden_je_bereich"]) == len(bereiche)
    ):
        zeit = z["sekunden_je_bereich"][list(bereiche).index(b)]
    out.append(
        KachelWert(
            f"Zeit im Bereich · {bezug_name}",
            minuten(zeit) if zeit is not None else "–",
            zusatz=b.name if b is not None else "",
        )
    )
    out.append(KachelWert(f"Ø HF · {bezug_name}", zahl(z.get("mittel_bpm")), "bpm"))
    out.append(
        KachelWert(f"Gipfel · {bezug_name}", zahl(z.get("gipfel_bpm")), "bpm", zusatz="5-s-Mittel")
    )
    if profil.vollstaendig:
        out.append(
            KachelWert(
                f"Ø Reserve · {bezug_name}",
                prozent_text(z.get("mittel_prozent")),
            )
        )
        out.append(
            KachelWert(
                f"TRIMP · {bezug_name}",
                zahl(z.get("trimp"), 1),
                zusatz="Banister, Konvention",
            )
        )
    return out


def erholung_block(
    erholung: hz.Erholung | None,
    rest_s: dict[int, float],
    *,
    laeuft: bool,
    kontext: str,
    haltung: str,
    starten: Callable[[], None],
    beenden: Callable[[], None],
    kontext_setzen: Callable[[str], None],
    haltung_setzen: Callable[[str], None],
    fruehere: Sequence[hz.Erholung] = (),
    knopf: bool = True,
) -> ft.Control:
    """Erholung: Knopf, HF am Ende, HRR je Fenster (30 / 60 / 120 s und X), Kontext und
    Haltung (Pflichtfelder, Entscheidung 14), darunter die früheren Erholungen dieser
    Aufnahme. ``knopf=False``: ohne den Knopf im Kopf — die Messansicht hat ihn als großen
    Knopf neben „Sprechen wird schwer“ (Skizze H4)."""

    def auswahl(
        label: str, wert: str, namen: dict[str, str], setzen: Callable[[str], None]
    ) -> ft.Control:
        def gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
            w = str(e.control.value or "")
            if w in namen:
                setzen(w)

        return ft.Dropdown(
            label=label,
            value=wert,
            options=[ft.DropdownOption(key=k, text=v) for k, v in namen.items()],
            on_select=gewaehlt,
            dense=True,
            expand=True,
        )

    kopf = ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text("ERHOLUNG", size=11, weight=ft.FontWeight.BOLD, opacity=0.6, expand=True),
            *(
                [
                    ft.TextButton("Beenden", icon=ft.Icons.STOP, on_click=lambda _=None: beenden())
                    if laeuft
                    else ft.TextButton(
                        "Belastung endet jetzt",
                        icon=ft.Icons.FLAG,
                        on_click=lambda _=None: starten(),
                    )
                ]
                if knopf
                else []
            ),
        ],
    )
    teile: list[ft.Control] = [kopf]
    if laeuft and erholung is not None:
        werte: list[ft.Control] = [
            ft.Column(
                spacing=0,
                tight=True,
                controls=[
                    ft.Text(zahl(erholung.hf_ende), size=22, weight=ft.FontWeight.W_600),
                    ft.Text("HF am Ende", size=11, opacity=0.6),
                ],
            )
        ]
        for f, w in erholung.hrr.items():
            rest = rest_s.get(f, 0)
            werte.append(
                ft.Column(
                    spacing=0,
                    tight=True,
                    controls=[
                        ft.Text(
                            f"−{w:.0f}"
                            if w is not None
                            else (f"in {rest:.0f} s" if rest > 0 else "–"),
                            size=22,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(f"HRR{f}", size=11, opacity=0.6),
                    ],
                )
            )
        teile.append(ft.Row(spacing=18, controls=werte))
        teile.append(
            ft.Row(
                spacing=8,
                controls=[
                    auswahl("Woran", kontext, KONTEXT_NAMEN, kontext_setzen),
                    auswahl("Haltung", haltung, HALTUNG_NAMEN, haltung_setzen),
                ],
            )
        )
    for e in list(fruehere)[-5:]:
        hrr60 = e.hrr.get(60)
        teile.append(
            ft.Text(
                f"{minuten(e.t0)} · {KONTEXT_NAMEN.get(e.kontext, e.kontext or '–')} · "
                f"{HALTUNG_NAMEN.get(e.haltung, e.haltung or '–')} · HF {zahl(e.hf_ende)} · "
                f"HRR60 {'−' + f'{hrr60:.0f}' if hrr60 is not None else '–'}",
                size=12,
                opacity=0.75,
            )
        )
    if not laeuft and not fruehere:
        teile.append(
            ft.Text(
                "„Belastung endet jetzt“ antippen: HF jetzt und in den Fenstern danach. "
                "Vergleichbar sind nur Erholungen mit gleichem „Woran“ und gleicher Haltung.",
                size=11,
                opacity=0.6,
            )
        )
    return ft.Column(spacing=8, tight=True, controls=teile)


# ---------------------------------------------------------------------------
# Zielbereich, Wertebereich, Erholung, Ablese-Intervall (Ben, 10.11.2026, A22) — für die
# Messansicht und das HF-Vollbild; `hl` ist ein `ui.hf_live.HfLive`
# ---------------------------------------------------------------------------

#: Farbe der Zielbereich-Linien — die der Notizmarken wäre es fast; bewusst kein Rot
ZIEL_FARBE = ft.Colors.AMBER_300


def _knopf(text: str, tipp: Callable[[], None], *, tooltip: str | None = None) -> ft.Control:
    return ft.OutlinedButton(
        content=ft.Text(text, size=12),
        tooltip=tooltip,
        on_click=lambda _=None: tipp(),
        style=ft.ButtonStyle(
            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
            visual_density=ft.VisualDensity.COMPACT,
        ),
    )


def tonfolge_bild() -> ft.Control:
    """Die Tonfolge nach Abstand als fünf Stufen: „1 bpm alle 6 s“ … „ab 15 jede Sekunde“."""
    n = len(TONFOLGE)
    balken = ft.Row(
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.END,
        controls=[
            ft.Container(
                expand=True,
                height=8 + i * 6,
                border_radius=2,
                bgcolor=ft.Colors.with_opacity(0.35 + 0.6 * i / (n - 1), ft.Colors.PRIMARY),
            )
            for i in range(n)
        ],
    )
    texte = ft.Row(
        spacing=4,
        controls=[
            ft.Text(
                f"{'ab ' if i == n - 1 else ''}{ab:.0f}{' bpm' if i == 0 else ''}\n"
                f"{'alle ' if i == 0 else ''}{s:.0f} s",
                size=10,
                opacity=0.7,
                expand=True,
            )
            for i, (ab, s) in enumerate(TONFOLGE)
        ],
    )
    return ft.Column(spacing=2, tight=True, controls=[balken, texte])


def ziel_seite(
    hl: Any, geaendert: Callable[[], None], *, stumm_knoepfe: Sequence[tuple[str, float]] = ()
) -> ft.Control:
    """„Zielbereich und Ton“ (Skizze H3): beide Linien mit − und +, aus den eigenen Bereichen
    übernehmen, Ton an/aus, Klang darüber und darunter, die Tonfolge, stumm für eine Zeit.

    Ein Ton als Information wie bei einem Timer — keine Bewertung, keine Steuerung
    (`docs/recht/00_zweckbestimmung.md`); die Linien setzt die Person selbst.
    """
    oben_t = ft.Text(width=40, text_align=ft.TextAlign.CENTER, weight=ft.FontWeight.W_600)
    unten_t = ft.Text(width=40, text_align=ft.TextAlign.CENTER, weight=ft.FontWeight.W_600)
    stumm_t = ft.Text(size=11, opacity=0.75)
    stumm_auf = ft.TextButton(
        "Ton wieder an",
        on_click=lambda _=None: stumm_setzen(None),
        style=ft.ButtonStyle(visual_density=ft.VisualDensity.COMPACT),
    )
    bild = tonfolge_bild()
    schalter = ft.Switch(label="Ton außerhalb", value=False)

    def nachziehen(zeichnen: bool = True) -> None:
        e = hl.einst()
        oben, unten = ziel_grenzen(e)
        oben_t.value = "–" if oben is None else f"{oben:.0f}"
        unten_t.value = "–" if unten is None else f"{unten:.0f}"
        schalter.value = e.alarm_an
        s = hl.stumm()
        stumm_t.value = s.text(time.monotonic()) if s is not None else ""
        stumm_t.visible = stumm_auf.visible = s is not None
        bild.visible = e.alarm_takt_s == TAKT_NACH_ABSTAND
        if zeichnen:
            for c in (oben_t, unten_t, schalter, stumm_t, stumm_auf, bild):
                with contextlib.suppress(Exception):
                    c.update()

    def schritt(seite: str, d: float) -> None:
        hl.ziel_schritt(seite, d)
        nachziehen()
        geaendert()

    def aus_bereich(b: hz.Bereich) -> None:
        hl.ziel_aus_bereich(b)
        nachziehen()
        geaendert()

    def umgeschaltet(ev: ft.Event[ft.Switch]) -> None:
        hl.ziel_aendern(an=bool(ev.control.value))
        nachziehen()
        geaendert()

    def klang_gewaehlt(feld: str) -> Callable[[ft.Event[ft.Dropdown]], None]:
        def gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
            if ev.control.value:
                e = hl.einst(frisch=True)
                setattr(e, feld, str(ev.control.value))
                hl.einst_speichern(e)
                hl.klang_spielen(str(ev.control.value))

        return gewaehlt

    def takt_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        if ev.control.value is not None:
            e = hl.einst(frisch=True)
            e.alarm_takt_s = int(ev.control.value)
            hl.einst_speichern(e)
            nachziehen()

    def stumm_setzen(dauer: float | None) -> None:
        hl.stumm_setzen(dauer)
        nachziehen()
        geaendert()

    schalter.on_change = umgeschaltet

    def zeile(name: str, seite: str, text: ft.Text) -> ft.Control:
        return ft.Row(
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(name, size=13, expand=True),
                ft.IconButton(
                    ft.Icons.REMOVE,
                    icon_size=18,
                    tooltip=f"{name} senken",
                    on_click=lambda _=None: schritt(seite, -1),
                    on_long_press=lambda _=None: schritt(seite, -5),
                ),
                text,
                ft.IconButton(
                    ft.Icons.ADD,
                    icon_size=18,
                    tooltip=f"{name} erhöhen",
                    on_click=lambda _=None: schritt(seite, 1),
                    on_long_press=lambda _=None: schritt(seite, 5),
                ),
            ],
        )

    def klang(label: str, feld: str) -> ft.Control:
        return ft.Dropdown(
            label=label,
            value=getattr(hl.einst(), feld),
            options=[ft.DropdownOption(key=k, text=t) for k, t in KLAENGE.items() if k != "ende"],
            on_select=klang_gewaehlt(feld),
            dense=True,
            expand=True,
            text_size=12,
            border=ft.OutlineInputBorder(border_radius=8),
        )

    teile: list[ft.Control] = [
        zeile("Oben", "oben", oben_t),
        zeile("Unten", "unten", unten_t),
    ]
    if hl.bereiche:
        teile.append(
            ft.Row(
                spacing=6,
                run_spacing=4,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Aus meinen Bereichen:", size=11, opacity=0.7),
                    *(
                        _knopf(
                            b.name,
                            lambda b=b: aus_bereich(b),  # type: ignore[misc]
                            tooltip=f"{b.von_bpm:.0f}–{b.bis_bpm:.0f} bpm",
                        )
                        for b in hl.bereiche
                    ),
                ],
            )
        )
    teile += [
        ft.Divider(height=8),
        schalter,
        ft.Row(
            spacing=6,
            controls=[klang("darüber", "alarm_klang"), klang("darunter", "alarm_klang_tief")],
        ),
        ft.Dropdown(
            label="Tonfolge",
            value=str(hl.einst().alarm_takt_s),
            options=[ft.DropdownOption(key=str(x), text=takt_name(x)) for x in ALARM_TAKT_S],
            on_select=takt_gewaehlt,
            dense=True,
            text_size=12,
            border=ft.OutlineInputBorder(border_radius=8),
        ),
        bild,
    ]
    if stumm_knoepfe:
        teile.append(
            ft.Row(
                spacing=6,
                run_spacing=4,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Stumm:", size=11, opacity=0.7),
                    *(
                        _knopf(name, lambda d=d: stumm_setzen(d))  # type: ignore[misc]
                        for name, d in stumm_knoepfe
                    ),
                ],
            )
        )
        teile.append(
            ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[stumm_t, stumm_auf],
            )
        )
    teile.append(
        ft.Text(
            "Ein leiser Klang, solange die Herzfrequenz außerhalb deiner beiden Linien liegt — "
            "wie ein Timer, keine Bewertung. − und + rücken um 1 bpm, lang gedrückt um 5.",
            size=10,
            opacity=0.6,
        )
    )
    nachziehen(zeichnen=False)
    return ft.Column(spacing=6, tight=True, controls=teile)


def ziel_zeile(hl: Any, geaendert: Callable[[], None], oeffnen: Callable[[], None]) -> ft.Control:
    """Die Zeile „Zielbereich 130–150 − + Ton an“ der Messansicht hochkant (Skizze H4): − und +
    rücken den ganzen Bereich um 5 bpm, der Tipp auf den Text öffnet „Zielbereich und Ton“."""
    e = hl.einst()
    text = ziel_text(e)
    stumm = hl.stumm()

    def ruecken(d: float) -> None:
        hl.ziel_beide(d)
        geaendert()

    def ton(_e: object = None) -> None:
        if hl.stumm() is not None:
            hl.stumm_setzen(None)
        else:
            hl.ziel_aendern(an=not hl.einst(frisch=True).alarm_an)
        geaendert()

    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=2),
        border_radius=10,
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        content=ft.Row(
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    expand=True,
                    ink=True,
                    on_click=lambda _=None: oeffnen(),
                    tooltip="Zielbereich und Ton einstellen",
                    padding=ft.Padding.symmetric(vertical=8),
                    content=ft.Text(
                        spans=[
                            ft.TextSpan("Zielbereich ", ft.TextStyle(weight=ft.FontWeight.W_600)),
                            ft.TextSpan(text or "setzen …"),
                        ],
                        size=13,
                    ),
                ),
                ft.IconButton(
                    ft.Icons.REMOVE,
                    icon_size=18,
                    tooltip="Zielbereich senken (5 bpm)",
                    on_click=lambda _=None: ruecken(-5),
                ),
                ft.IconButton(
                    ft.Icons.ADD,
                    icon_size=18,
                    tooltip="Zielbereich anheben (5 bpm)",
                    on_click=lambda _=None: ruecken(5),
                ),
                ft.TextButton(
                    "Ton stumm" if stumm is not None else ("Ton an" if e.alarm_an else "Ton aus"),
                    icon=ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED
                    if e.alarm_an and stumm is None
                    else ft.Icons.NOTIFICATIONS_OFF_OUTLINED,
                    tooltip="Ton außerhalb des Zielbereichs an- oder ausschalten",
                    on_click=ton,
                ),
            ],
        ),
    )


def ziel_blatt(
    hl: Any, geaendert: Callable[[], None], stumm_knoepfe: Sequence[tuple[str, float]]
) -> ft.BottomSheet:
    """„Zielbereich und Ton“ als Blatt von unten — hochkant, wo keine Seitenleiste ist."""
    from trainingsapp.ui.components.blatt import blatt_spalte
    from trainingsapp.ui.components.dialoge import schliessen

    blatt = ft.BottomSheet(content=ft.Container(), scrollable=True)

    def zu(_e: object = None) -> None:
        schliessen(blatt)
        geaendert()

    blatt.content = blatt_spalte(
        [
            ft.Text("Zielbereich und Ton", size=16, weight=ft.FontWeight.W_600),
            ziel_seite(hl, geaendert, stumm_knoepfe=stumm_knoepfe),
        ],
        [ft.TextButton("Fertig", on_click=zu)],
    )
    return blatt


def _seg(
    wert: str, namen: Sequence[tuple[str, str]], gewaehlt: Callable[[str], None]
) -> ft.SegmentedButton:
    def change(ev: ft.Event[ft.SegmentedButton]) -> None:
        if ev.control.selected:
            gewaehlt(str(ev.control.selected[0]))

    return ft.SegmentedButton(
        selected=[wert],
        show_selected_icon=False,
        on_change=change,
        segments=[ft.Segment(value=k, label=ft.Text(t, size=12)) for k, t in namen],
    )


def _bpm_feld(
    wert: float, setzen: Callable[[float], None], *, von: float, bis: float, label: str
) -> ft.TextField:
    feld = ft.TextField(
        label=label,
        suffix=ft.Text("bpm"),
        value=f"{wert:g}",
        dense=True,
        width=120,
        border=ft.OutlineInputBorder(border_radius=8),
        keyboard_type=ft.KeyboardType.NUMBER,
        text_align=ft.TextAlign.RIGHT,
    )

    def uebernehmen(_e: object = None) -> None:
        try:
            w = float((feld.value or "").strip().replace(",", "."))
        except ValueError:
            w = -1.0
        if von <= w <= bis:
            feld.error = None
            setzen(w)
        else:
            feld.error = f"{von:.0f} bis {bis:.0f}"
        with contextlib.suppress(Exception):
            feld.update()

    feld.on_submit = uebernehmen
    feld.on_blur = uebernehmen
    return feld


def wertebereich_gruppe(hl: Any, geaendert: Callable[[], None]) -> tuple[str, list[ft.Control]]:
    """Gruppe „Wertebereich“ des Blatts „Fenster und Darstellung“ (Skizze H4): oben und unten
    **je für sich** Automatik · Profilwert (HFmax bzw. Ruhe-HF) · fester Wert. Gilt hochkant
    und im Vollbild; eine gesetzte Seite weicht der Kurve (`core.hf_ziel.wertebereich`)."""
    e = hl.einst(frisch=True)
    p = hl.profil

    def setzen(feld: str, wert: Any) -> None:
        aktuell = hl.einst(frisch=True)
        setattr(aktuell, feld, wert)
        hl.einst_speichern(aktuell)
        geaendert()

    def fest_setzen(seite: str, wert: float) -> None:
        """Ein getippter fester Wert gilt sofort — die Seite steht dann auf „Fest“."""
        aktuell = hl.einst(frisch=True)
        setattr(aktuell, seite + "_bpm", wert)
        setattr(aktuell, seite, ACHSE_FEST)
        hl.einst_speichern(aktuell)
        geaendert()

    def profilname(name: str, wert: float | None) -> str:
        return f"{name} {wert:.0f}" if wert else f"{name} –"

    oben_feld = _bpm_feld(
        e.achse_oben_bpm,
        lambda w: fest_setzen("achse_oben", w),
        von=ALARM_MIN_BPM,
        bis=ALARM_MAX_BPM,
        label="Fest oben",
    )
    unten_feld = _bpm_feld(
        e.achse_unten_bpm,
        lambda w: fest_setzen("achse_unten", w),
        von=20.0,
        bis=ALARM_MAX_BPM,
        label="Fest unten",
    )
    return (
        "Wertebereich",
        [
            ft.Text("oben", size=12, weight=ft.FontWeight.W_600),
            ft.Row(
                spacing=8,
                wrap=True,
                run_spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    _seg(
                        e.achse_oben,
                        [
                            (ACHSE_AUTO, "Automatik"),
                            (ACHSE_PROFIL, profilname("HFmax", p.hfmax_bpm)),
                            (ACHSE_FEST, "Fest"),
                        ],
                        lambda w: setzen("achse_oben", w),
                    ),
                    oben_feld,
                ],
            ),
            ft.Text("unten", size=12, weight=ft.FontWeight.W_600),
            ft.Row(
                spacing=8,
                wrap=True,
                run_spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    _seg(
                        e.achse_unten,
                        [
                            (ACHSE_AUTO, "Automatik"),
                            (ACHSE_PROFIL, profilname("Ruhe-HF", p.ruhe_bpm)),
                            (ACHSE_FEST, "Fest"),
                        ],
                        lambda w: setzen("achse_unten", w),
                    ),
                    unten_feld,
                ],
            ),
            ft.Text(
                "Jede Seite für sich. Vorgabe: Ruhe-HF bis HFmax, wenn beide im Profil stehen — "
                "sonst Automatik. Liegt die Kurve außerhalb, reicht die Achse bis dorthin. Gilt "
                "hochkant und im Vollbild.",
                size=11,
                opacity=0.65,
            ),
        ],
    )


def erholung_gruppe(hl: Any, geaendert: Callable[[], None]) -> tuple[str, list[ft.Control]]:
    """Gruppe „Erholung messen“: welche Fenster nach dem Belastungsende gelten (30 · 60 · 120
    und das freie X) und bis wann gemessen wird."""
    e = hl.einst(frisch=True)

    def speichern(aendern: Callable[[HfEinstellungen], None]) -> None:
        aktuell = hl.einst(frisch=True)
        aendern(aktuell)
        hl.einst_speichern(aktuell)
        geaendert()

    def fest_umschalten(f: int) -> Callable[[ft.Event[ft.Chip]], None]:
        def change(ev: ft.Event[ft.Chip]) -> None:
            an = bool(ev.control.selected)

            def aendern(a: HfEinstellungen) -> None:
                a.erholung_fest = [
                    x
                    for x in ERHOLUNG_FENSTER_S
                    if (x in a.erholung_fest and x != f) or (x == f and an)
                ]

            speichern(aendern)

        return change

    def x_setzen(w: float) -> None:
        speichern(lambda a: setattr(a, "erholung_x_s", round(w)))

    def x_umschalten(ev: ft.Event[ft.Chip]) -> None:
        an = bool(ev.control.selected)
        speichern(lambda a: setattr(a, "erholung_x_s", (a.erholung_x_s or 180) if an else 0))

    def bis_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        if ev.control.value is not None:
            speichern(lambda a: setattr(a, "messen_bis_s", int(ev.control.value)))  # type: ignore[arg-type]

    x_feld = ft.TextField(
        label="X",
        suffix=ft.Text("s"),
        value=str(e.erholung_x_s or 180),
        dense=True,
        width=100,
        border=ft.OutlineInputBorder(border_radius=8),
        keyboard_type=ft.KeyboardType.NUMBER,
        text_align=ft.TextAlign.RIGHT,
    )

    def x_uebernehmen(_e: object = None) -> None:
        try:
            w = int((x_feld.value or "").strip())
        except ValueError:
            w = -1
        if ERHOLUNG_X_MIN_S <= w <= ERHOLUNG_X_MAX_S:
            x_feld.error = None
            x_setzen(w)
        else:
            x_feld.error = f"{ERHOLUNG_X_MIN_S} bis {ERHOLUNG_X_MAX_S}"
        with contextlib.suppress(Exception):
            x_feld.update()

    x_feld.on_submit = x_uebernehmen
    x_feld.on_blur = x_uebernehmen
    return (
        "Erholung messen",
        [
            ft.Row(
                spacing=6,
                wrap=True,
                run_spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    *(
                        ft.Chip(
                            label=ft.Text(f"{f}"),
                            selected=f in e.erholung_fest,
                            on_select=fest_umschalten(f),
                        )
                        for f in ERHOLUNG_FENSTER_S
                    ),
                    ft.Chip(
                        label=ft.Text("X"), selected=bool(e.erholung_x_s), on_select=x_umschalten
                    ),
                    x_feld,
                ],
            ),
            ft.Dropdown(
                label="Messen bis",
                value=str(e.messen_bis_s),
                options=[
                    ft.DropdownOption(key=str(s), text=f"{s // 60}:00 nach dem Belastungsende")
                    for s in MESSEN_BIS_S
                ],
                on_select=bis_gewaehlt,
                dense=True,
                border=ft.OutlineInputBorder(border_radius=8),
            ),
            ft.Text(
                "Sekunden nach „Belastung endet jetzt“: je Fenster die Abnahme gegen die HF am "
                "Ende (HRR, 5-s-Mittel). Nach „Messen bis“ endet die Erholung von selbst — nie "
                "vor dem längsten Fenster. Einen eigenen Bereich liest im Vollbild „Intervall“ ab.",
                size=11,
                opacity=0.65,
            ),
        ],
    )


def erholung_karte(
    erholung: hz.Erholung,
    rest_s: dict[int, float],
    vorige: hz.Erholung | None,
    *,
    x_s: int,
    x_bearbeiten: Callable[[], None],
) -> ft.Control:
    """Die Karte über der Kurve, solange eine Erholung läuft (Skizze H2): je Fenster die
    Abnahme oder „in 0:18“, das freie Fenster X mit Stift, darunter die vorige Erholung."""
    zeilen: list[ft.Control] = []
    for f, w in erholung.hrr.items():
        rest = rest_s.get(f, 0.0)
        ist_x = f == x_s and f not in ERHOLUNG_FENSTER_S
        name: ft.Control = ft.Text(f"HRR{f}", size=13, weight=ft.FontWeight.W_600, expand=True)
        if ist_x:
            name = ft.Container(
                expand=True,
                ink=True,
                on_click=lambda _=None: x_bearbeiten(),
                tooltip="Fenster X ändern",
                content=ft.Text(f"HRR {f} ✎", size=13, weight=ft.FontWeight.W_600),
            )
        if w is not None:
            wert = ft.Text(
                f"{'−' if w >= 0 else '+'}{abs(w):.0f} bpm",
                size=14,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.PRIMARY,
            )
        else:
            wert = ft.Text(
                f"in {int(rest) // 60}:{int(rest) % 60:02d}" if rest > 0 else "–",
                size=13,
                opacity=0.65,
            )
        zeilen.append(ft.Row(spacing=8, controls=[name, wert]))
    if vorige is not None:
        v60 = next(
            (vorige.hrr[f] for f in (60, *vorige.hrr) if vorige.hrr.get(f) is not None), None
        )
        zeilen.append(ft.Divider(height=6))
        zeilen.append(
            ft.Text(
                f"Blass: vorige Erholung ({minuten(vorige.t0)}"
                + (f", HRR −{v60:.0f}" if v60 is not None else "")
                + ")",
                size=10,
                opacity=0.65,
            )
        )
    return ft.Container(
        width=214,
        padding=10,
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.94, ft.Colors.SURFACE_CONTAINER_HIGH),
        content=ft.Column(spacing=6, tight=True, controls=zeilen),
    )


def intervall_karte(
    e: hz.IntervallErholung,
    zeit: Callable[[float], str],
    *,
    bezug_setzen: Callable[[str], None],
    ende_aufs_tal: Callable[[], None],
    als_notiz: Callable[[], None] | None,
    schliessen: Callable[[], None],
) -> ft.Control:
    """Die Ablesewerte des Intervalls (Ben, 10.11.2026): HF an Anfang und Ende mit Δ, Spitze
    und Tal, die Erholung ab dem gewählten Bezug („HRR 95 s: −31 bpm“). Liegt das Ende über
    dem tiefsten Wert, steht es da — mit dem Knopf, das Ende dorthin zu setzen. Nur Zahlen."""

    def bpm(w: float | None) -> str:
        return "–" if w is None else f"{w:.0f}"

    def paar(name: str, wert: str, zusatz: str = "") -> ft.Control:
        return ft.Row(
            spacing=6,
            controls=[
                ft.Text(name, size=11, opacity=0.7, width=54),
                ft.Text(wert, size=13, weight=ft.FontWeight.W_600),
                ft.Text(zusatz, size=11, opacity=0.7),
            ],
        )

    hinweis = tal_hinweis(e.ueber_tal, zeit(e.tal_t) if e.tal_t is not None else "")
    teile: list[ft.Control] = [
        ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    f"Intervall {dauer_kurz(e.bis - e.von)}",
                    size=12,
                    weight=ft.FontWeight.BOLD,
                    expand=True,
                ),
                ft.IconButton(
                    ft.Icons.CLOSE,
                    icon_size=16,
                    tooltip="Intervall schließen",
                    on_click=lambda _=None: schliessen(),
                ),
            ],
        ),
        paar("Anfang", f"{bpm(e.hf_von)} bpm", zeit(e.von)),
        paar("Ende", f"{bpm(e.hf_bis)} bpm", f"{zeit(e.bis)} · {delta_text(e.delta)}"),
        paar("HF-Max", bpm(e.spitze_hf), zeit(e.spitze_t) if e.spitze_t is not None else ""),
        paar("HF-Min", bpm(e.tal_hf), zeit(e.tal_t) if e.tal_t is not None else ""),
        ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("ab", size=11, opacity=0.7),
                _seg(e.bezug, list(INTERVALL_BEZUG_NAMEN.items()), bezug_setzen),
            ],
        ),
        ft.Text(
            hrr_text(e.hrr, e.x_s), size=15, weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY
        ),
    ]
    if hinweis:
        teile.append(ft.Text(hinweis, size=11))
        teile.append(
            ft.TextButton(
                "Ende auf den tiefsten Wert",
                on_click=lambda _=None: ende_aufs_tal(),
                style=ft.ButtonStyle(visual_density=ft.VisualDensity.COMPACT),
            )
        )
    if als_notiz is not None and e.hrr is not None:
        teile.append(
            ft.TextButton(
                "Als Notiz festhalten",
                icon=ft.Icons.ADD_COMMENT_OUTLINED,
                on_click=lambda _=None: als_notiz(),
                style=ft.ButtonStyle(visual_density=ft.VisualDensity.COMPACT),
            )
        )
    teile.append(
        ft.Text("Alle Werte sind 5-s-Mittel. Linien ziehen oder antippen.", size=10, opacity=0.6)
    )
    return ft.Container(
        width=INTERVALL_PX,
        padding=ft.Padding.only(left=10, right=4, top=2, bottom=8),
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.94, ft.Colors.SURFACE_CONTAINER_HIGH),
        content=ft.Column(spacing=3, tight=True, scroll=ft.ScrollMode.AUTO, controls=teile),
    )


#: Breite der Karte des Ablese-Intervalls (px)
INTERVALL_PX = 236


HF_INFO = """\
**Herzfrequenz-Sicht.** Die große Zahl ist die Herzfrequenz aus den Schlagabständen
(bei reinen Pulsgebern die des Geräts). Daneben steht der Anteil an deiner
**Herzfrequenzreserve** (Ruhe-HF = 0 %, HFmax = 100 %) und der Bereich, in dem du bist.

- **Skala:** Ruhe-HF bis HFmax, die Bereiche als Stufen einer Farbe. Helle Streifen an den
  Grenzen zeigen, wie unsicher eine Grenze ist (Formel ± 11, Schätzung ± 6, Labor ± 3 bpm).
- **Zeit je Bereich** zählt für den gewählten Bezug: die ganze Aufnahme, den laufenden
  Abschnitt oder die letzten 5 Minuten.
- **Erholung:** „Belastung endet jetzt“ merkt sich den Zeitpunkt; danach stehen HF am Ende
  und die Abnahme nach 30, 60 und 120 s und einem eigenen Fenster X (HRR). Woran und in
  welcher Haltung — nur gleiche Paare sind vergleichbar.
- **Zielbereich:** zwei Linien, die du selbst setzt. Außerhalb klingt auf Wunsch ein leiser
  Ton — darüber ein anderer als darunter, dichter, je weiter die Herzfrequenz entfernt ist.
  Er sagt nur, wo die Zahl zu deinen Linien liegt.
- **Vollbild:** dieselbe Sicht quer, mit dem **Intervall** zum Ablesen: Anfang und Ende
  setzen, dazwischen HF-Max, HF-Min und die Erholung in diesem Bereich.

Die Bereiche sind deine Werte wie ein Timer: Woher Ruhe-HF, HFmax und Grenzen kommen, steht
unter Einstellungen → Herzfrequenz, mit Quelle, Datum und Unsicherheit. Die App bewertet
nichts und gibt keinen Rat.
"""


__all__ = [
    "EINSTELLUNGEN",
    "HALTUNG_NAMEN",
    "HF_INFO",
    "INTERVALL_PX",
    "KONTEXT_NAMEN",
    "ZIEL_FARBE",
    "alarm_text",
    "alarm_zeilen",
    "bandfarbe",
    "bezug_wahl",
    "erholung_block",
    "erholung_gruppe",
    "erholung_karte",
    "hf_baender",
    "hf_kacheln",
    "hf_kopf",
    "intervall_karte",
    "prozent_text",
    "sicht_wahl",
    "skala",
    "stufenfarbe",
    "takt_name",
    "tonfolge_bild",
    "wertebereich_gruppe",
    "zeit_je_bereich",
    "ziel_blatt",
    "ziel_seite",
    "ziel_zeile",
]
