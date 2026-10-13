"""Spektrum und Poincaré-Wolke des sichtbaren Ausschnitts.

Beide zeigen, was gerade im Zeitfenster der Hauptkurve liegt: Wer zoomt oder
wischt, sieht das Spektrum bzw. die Wolke genau dieses Ausschnitts. Die Linie
des Spektrums ist neutral; nur die Bänder sind getönt — eine Bewertung („gut",
„kohärent") gibt es nicht (wie praxis_gui seit „Live-PSD ohne Urteil").

Die Höhe richtet sich nach LF und HF; VLF wird am oberen Rand abgeschnitten.
praxis_gui zeigt dafür eine logarithmische Achse — am Handy ist eine lineare
für Laien lesbarer.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

import flet as ft
import numpy as np

from trainingsapp.hrv_core.constants import FREQ_BANDS
from trainingsapp.hrv_core.frequency import Fensterspektrum
from trainingsapp.ui.components.kacheln import zahl
from trainingsapp.ui.components.kurve import Reihe, kurve
from trainingsapp.ui.components.verlauf import FARBEN

#: Bänder im Bild: (von, bis, Farbe der Fläche) — VLF grau, LF und HF wie ihre Kurven
BAND_FARBEN = (
    (FREQ_BANDS["vlf"][0], FREQ_BANDS["vlf"][1], ft.Colors.OUTLINE),
    (FREQ_BANDS["lf"][0], FREQ_BANDS["lf"][1], FARBEN["lf_power"]),
    (FREQ_BANDS["hf"][0], FREQ_BANDS["hf"][1], FARBEN["hf_power"]),
    (FREQ_BANDS["hf"][1], 0.5, None),
)


def hz_text(f: float) -> str:
    """Frequenz mit deutschem Komma.

    >>> hz_text(0.1), hz_text(0.25)
    ('0,1', '0,25')
    """
    return f"{f:g}".replace(".", ",")


def spektrum_kurve(fs: Fensterspektrum | None, *, hoehe: int = 150) -> ft.Control:
    """Leistungsdichte über der Frequenz, Bänder getönt, der Gipfel markiert."""
    if fs is None:
        return ft.Container(
            height=60,
            alignment=ft.Alignment.CENTER,
            content=ft.Text(
                "Für ein Spektrum fehlen gute Schläge im Ausschnitt "
                "(mindestens 30, und 70 % der Zeit belegt).",
                size=12,
                opacity=0.6,
                text_align=ft.TextAlign.CENTER,
            ),
        )
    freqs, psd = np.asarray(fs.freqs), np.asarray(fs.psd)
    reihen: list[Reihe] = []
    for lo, hi, farbe in BAND_FARBEN:
        maske = (freqs >= lo) & (freqs <= hi)
        # Den nächsten Punkt mitnehmen, damit die Bänder lückenlos aneinanderstoßen
        idx = np.flatnonzero(maske)
        if idx.size == 0:
            continue
        if idx[-1] + 1 < freqs.size:
            idx = np.append(idx, idx[-1] + 1)
        reihen.append(
            Reihe(
                [(float(freqs[i]), float(psd[i])) for i in idx],
                farbe=ft.Colors.ON_SURFACE_VARIANT,
                breite=1.5,
                flaeche=ft.Colors.with_opacity(0.35, farbe) if farbe else None,
                # VLF (langsame Drift) bestimmt die Höhe nicht — sonst wären LF und
                # HF über einer langen Messung nur ein Strich am Boden.
                skala=lo >= FREQ_BANDS["lf"][0],
            )
        )
    gipfel = fs.werte.get("gipfel_hz")
    if gipfel:
        i = int(np.argmin(np.abs(freqs - gipfel)))
        reihen.append(
            Reihe([(float(freqs[i]), float(psd[i]))], farbe=ft.Colors.PRIMARY, nur_punkte=True)
        )
    return kurve(
        reihen,
        einheit="ms²/Hz",
        hoehe=hoehe,
        x_von=0.0,
        x_bis=0.5,
        y_von=0.0,
        x_text=hz_text,
        x_schritte=(0.05, 0.1, 0.2),
    )


def band_leiste(fs: Fensterspektrum | None, optisch: bool = False) -> ft.Control:
    """LF, HF, LF/HF und Gipfel des Ausschnitts in einer Zeile — mit Vorbehalt bei kurzer Dauer."""
    if fs is None:
        return ft.Container()
    w = fs.werte
    teile = [
        ("LF", zahl(w.get("lf")), "ms²", FARBEN["lf_power"]),
        ("HF", zahl(w.get("hf")), "ms²", FARBEN["hf_power"]),
        ("LF/HF", zahl(w.get("lf_hf"), 2), "", FARBEN["lf_hf"]),
    ]
    gipfel = w.get("gipfel_hz")
    if gipfel:
        teile.append(
            (
                "Gipfel",
                f"{hz_text(round(gipfel, 3))} Hz",
                f"{zahl(gipfel * 60, 1)}/min",
                FARBEN["gipfel"],
            )
        )
    zeilen: list[ft.Control] = [
        ft.Row(
            wrap=True,
            spacing=14,
            run_spacing=4,
            controls=[
                ft.Row(
                    spacing=4,
                    tight=True,
                    controls=[
                        ft.Container(width=8, height=8, border_radius=4, bgcolor=farbe),
                        ft.Text(name, size=11, opacity=0.7),
                        ft.Text(wert, size=13, weight=ft.FontWeight.W_600),
                        ft.Text(einheit, size=11, opacity=0.7),
                    ],
                )
                for name, wert, einheit, farbe in teile
            ],
        )
    ]
    vorbehalt = []
    if not fs.reif["lf"]:
        minuten = f"{round(fs.dauer_s / 60, 1):g}".replace(".", ",")
        vorbehalt.append(
            f"Ausschnitt {minuten} min: LF erst ab 5 min, HF ab 3 min belastbar — "
            "vorher Orientierung."
            if not fs.reif["hf"]
            else "LF erst ab 5 min belastbar — vorher Orientierung."
        )
    if optisch:
        vorbehalt.append("Optische Pulsintervalle: Frequenzwerte mit Vorbehalt.")
    if vorbehalt:
        zeilen.append(ft.Text(" ".join(vorbehalt), size=11, opacity=0.6))
    return ft.Column(spacing=4, tight=True, controls=zeilen)


def poincare_kurve(paare: Sequence[tuple[float, float]], *, hoehe: int = 240) -> ft.Control:
    """Jeder Punkt: ein Intervall (x) gegen das nächste (y); gestrichelt die Diagonale."""
    if len(paare) < 3:
        return ft.Container(
            height=60,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("Zu wenige Schläge im Ausschnitt.", size=12, opacity=0.6),
        )
    werte = [v for p in paare for v in p]
    lo, hi = min(werte), max(werte)
    rand = max((hi - lo) * 0.08, 20.0)
    lo, hi = lo - rand, hi + rand
    return kurve(
        [
            Reihe(
                [(lo, lo), (hi, hi)],
                farbe=ft.Colors.OUTLINE,
                breite=1,
                gestrichelt=True,
                skala=False,
            ),
            Reihe(
                list(paare),
                farbe=ft.Colors.with_opacity(0.75, FARBEN["sd1"]),
                nur_punkte=True,
                radius=2.5 if len(paare) > 200 else 3.0,
            ),
        ],
        einheit="RR n+1 (ms)",
        hoehe=hoehe,
        x_von=lo,
        x_bis=hi,
        y_von=lo,
        y_bis=hi,
        x_text=lambda x: f"{x:g}",
        x_schritte=(10, 20, 25, 50, 100, 200, 250, 500),
    )


def poincare_paare(
    t: np.ndarray, rr: np.ndarray, naht: np.ndarray, von: float, bis: float
) -> list[tuple[float, float]]:
    """Paare aufeinanderfolgender guter Schläge im Ausschnitt — nie über eine Naht."""
    im = (t > von) & (t <= bis)
    idx = np.flatnonzero(im)
    paare: list[tuple[float, float]] = []
    for a, b in pairwise(idx):
        if b == a + 1 and not naht[b] and np.isfinite(rr[a]) and np.isfinite(rr[b]):
            paare.append((float(rr[a]), float(rr[b])))
    return paare


__all__ = ["band_leiste", "hz_text", "poincare_kurve", "poincare_paare", "spektrum_kurve"]
