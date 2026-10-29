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

from collections.abc import Callable, Sequence
from typing import Any

import flet as ft
from hrv_core import herzfrequenz as hz

from trainingsapp.core.hf_profil import HfProfil, bereich_von
from trainingsapp.core.hf_training import BEZUEGE, BEZUG_ABSCHNITT, BEZUG_NAMEN
from trainingsapp.core.laufend import minuten
from trainingsapp.ui.components.kacheln import KachelWert, zahl

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
) -> ft.Control:
    """Erholung: Knopf, HF am Ende, HRR nach 30 / 60 / 120 s, Kontext und Haltung
    (Pflichtfelder, Entscheidung 14), darunter die früheren Erholungen dieser Aufnahme."""

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
            ft.TextButton("Beenden", icon=ft.Icons.STOP, on_click=lambda _=None: beenden())
            if laeuft
            else ft.TextButton(
                "Belastung endet jetzt", icon=ft.Icons.FLAG, on_click=lambda _=None: starten()
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
                "Am Ende einer Belastung antippen: HF jetzt und nach 30 / 60 / 120 s. "
                "Vergleichbar sind nur Erholungen mit gleichem „Woran“ und gleicher Haltung.",
                size=11,
                opacity=0.6,
            )
        )
    return ft.Column(spacing=8, tight=True, controls=teile)


HF_INFO = """\
**Herzfrequenz-Sicht.** Die große Zahl ist die Herzfrequenz aus den Schlagabständen
(bei reinen Pulsgebern die des Geräts). Daneben steht der Anteil an deiner
**Herzfrequenzreserve** (Ruhe-HF = 0 %, HFmax = 100 %) und der Bereich, in dem du bist.

- **Skala:** Ruhe-HF bis HFmax, die Bereiche als Stufen einer Farbe. Helle Streifen an den
  Grenzen zeigen, wie unsicher eine Grenze ist (Formel ± 11, Schätzung ± 6, Labor ± 3 bpm).
- **Zeit je Bereich** zählt für den gewählten Bezug: die ganze Aufnahme, den laufenden
  Abschnitt oder die letzten 5 Minuten.
- **Erholung:** „Belastung endet jetzt“ merkt sich den Zeitpunkt; danach stehen HF am Ende
  und die Abnahme nach 30, 60 und 120 s (HRR). Woran und in welcher Haltung — nur gleiche
  Paare sind vergleichbar.

Die Bereiche sind deine Werte wie ein Timer: Woher Ruhe-HF, HFmax und Grenzen kommen, steht
unter Einstellungen → Herzfrequenz, mit Quelle, Datum und Unsicherheit. Die App bewertet
nichts und gibt keinen Rat.
"""


__all__ = [
    "EINSTELLUNGEN",
    "HALTUNG_NAMEN",
    "HF_INFO",
    "KONTEXT_NAMEN",
    "bezug_wahl",
    "erholung_block",
    "hf_kacheln",
    "hf_kopf",
    "prozent_text",
    "sicht_wahl",
    "skala",
    "stufenfarbe",
    "zeit_je_bereich",
]
