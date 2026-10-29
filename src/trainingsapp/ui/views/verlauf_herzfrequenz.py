"""Verlauf → Herzfrequenz — Route `/verlauf/herzfrequenz` (Stufe 3, Ben 29.10.2026).

Drei Karten über Tage und Wochen (hrv-research `KONZEPT_HF_APP.md` §5.7):

- **Ruhe-HF und Nacht-HF**: alle Einträge des Profils je Quelle als Punkte, dazu die
  **Baseline** (Median der letzten 7 Werte) mit Band ± 1 SD als zwei gestrichelte Linien —
  eine Linie mit Breite, kein Pfeil. Ausgenommene Tage bleiben Punkt, zählen nicht.
- **Wochenlast**: Σ TRIMP und Σ sRPE-Last (sRPE × Minuten) je Woche aus dem HF-Cache und dem
  Tagesfeld „Anstrengung“, dazu Monotonie und Strain (Foster) — Zahlen, so beschriftet.
- **Tests**: Submaximaltest (HRR60 nach Stufe 3, Ø HF Stufe 2), Talk-Test (HF am Marker),
  Feld-Maximaltest (höchstes 30-s-Mittel) als Punkte über die Zeit.

Gerechnet wird aus dem Cache (`data/hf_cache.py`); Aufnahmen ohne Cache rechnet „Alle
nachrechnen“ im Thread nach. Keine Bewertung (`docs/recht/00_zweckbestimmung.md`).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import flet as ft
from hrv_core.korrektur import korrektur_laden

from trainingsapp.config import messungenverzeichnis
from trainingsapp.core import tagesfelder as tf
from trainingsapp.core.hf_auswertung import HfAuswertung, auswerten
from trainingsapp.core.hf_profil import QUELLEN, bereiche_fuer
from trainingsapp.core.hf_verlauf import (
    Baselinepunkt,
    Tageslast,
    Testpunkt,
    Wochenlast,
    baseline_reihe,
    tageslasten,
    wochenlasten,
)
from trainingsapp.core.hf_verlauf import testreihe as hf_testreihe
from trainingsapp.core.verlauf import ZEITRAEUME, datum_marken, zeitraum_beginn
from trainingsapp.data.hf_profil import RechenAusnahmeRepo
from trainingsapp.ui.components.kacheln import zahl
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.kurve import Reihe, kurve
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState

ROUTE = "/verlauf/herzfrequenz"
#: Farben je Quelle der Ruhe-HF (Ordnungsfarben, keine Ampel)
_QUELLFARBEN: dict[str, str] = {
    "nacht": ft.Colors.INDIGO_300,
    "messung_morgen_10": ft.Colors.PRIMARY,
    "messung_morgen_5": ft.Colors.PRIMARY,
    "eintrag": ft.Colors.OUTLINE,
    "tagesminimum": ft.Colors.TEAL_300,
    "tagesfeld": ft.Colors.BROWN_300,
}


def testpunkte_aus_cache(recording_id: str, tag: date, a: HfAuswertung) -> list[Testpunkt]:
    """Welche Tests eine Aufnahme enthält — an den Stufen-Abschnitten des Standardpakets
    erkannt (`hf_submaximaltest`, `hf_feld_maximaltest`) und am Talk-Marker.

    >>> stufen = [
    ...     {"name": "Stufe 2", "werte": {"mittel_bpm": 140}, "erholung": None},
    ...     {"name": "Stufe 3", "werte": {"mittel_bpm": 160},
    ...      "erholung": {"hf_ende": 162, "hrr": {"60": 31}}},
    ...     {"name": "Stehen", "werte": {}, "erholung": None},
    ... ]
    >>> a = HfAuswertung({}, stufen, [], None, None, None, None, [], None, {})
    >>> [(p.name, p.hrr60, p.mittel_bpm) for p in testpunkte_aus_cache("r", date(2026, 10, 1), a)]
    [('Submaximaltest', 31, 140)]
    """
    namen = {x["name"].strip().casefold(): x for x in a.abschnitte}
    out: list[Testpunkt] = []
    if "stufe 3" in namen and "stehen" in namen and "alles" not in namen:
        s3 = namen["stufe 3"]
        e = s3.get("erholung") or {}
        hrr60 = (e.get("hrr") or {}).get("60")
        s2 = namen.get("stufe 2") or {}
        out.append(
            Testpunkt(
                tag,
                recording_id,
                "Submaximaltest",
                hrr60,
                e.get("hf_ende"),
                (s2.get("werte") or {}).get("mittel_bpm"),
            )
        )
    if "alles" in namen and a.hfmax_kandidat and a.hfmax_kandidat.get("wert") is not None:
        out.append(
            Testpunkt(tag, recording_id, "Feld-Maximaltest", None, a.hfmax_kandidat["wert"], None)
        )
    if a.talk and a.talk.get("wert") is not None:
        out.append(Testpunkt(tag, recording_id, "Talk-Test", None, a.talk["wert"], None))
    return out


def _tage_x(tage: Sequence[date], beginn: date) -> list[float]:
    return [float((t - beginn).days) for t in tage]


def verlauf_herzfrequenz_view(page: Any, state: AppState) -> ft.View:
    heute = state.heute()
    inhalt = ft.Column(spacing=14)
    profil_id = state.profil.id

    def zeitraum_waehlen(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.verlauf_zeitraum = str(e.control.selected[0])
            zeichnen()

    def zeichnen() -> None:
        inhalt.controls = teile()
        with contextlib.suppress(Exception):
            inhalt.update()

    def beginn_und_ende() -> tuple[date, date]:
        b = zeitraum_beginn(state.verlauf_zeitraum, heute)
        return (b or heute - timedelta(days=365)), heute

    # -- Ruhe-HF / Nacht-HF -----------------------------------------------------------------

    def ruhe_karte(beginn: date, ende: date) -> ft.Control:
        aus = state.ausnahmen.tage(profil_id)
        eintraege = [
            e for e in state.profilwerte.alle(profil_id, "ruhe_hf") if beginn <= e.datum <= ende
        ]
        if not eintraege:
            return karte(
                titel("Ruhe-HF und Nacht-HF"),
                hinweis("Noch keine Einträge im Zeitraum — Einstellungen → Herzfrequenz."),
            )
        spanne = max(1, (ende - beginn).days)
        reihen: list[Reihe] = []
        legende: list[ft.Control] = []
        je_quelle: dict[str, list[tuple[date, float]]] = {}
        for e in eintraege:
            je_quelle.setdefault(e.quelle, []).append((e.datum, float(e.wert)))
        for quelle, punkte in je_quelle.items():
            farbe = _QUELLFARBEN.get(quelle, ft.Colors.PRIMARY)
            reihen.append(
                Reihe(
                    [(float((d - beginn).days), w) for d, w in punkte],
                    farbe=farbe,
                    nur_punkte=True,
                    radius=4,
                )
            )
            legende.append(
                ft.Row(
                    spacing=4,
                    controls=[
                        ft.Container(width=10, height=10, bgcolor=farbe, border_radius=5),
                        ft.Text(QUELLEN.get(quelle, quelle), size=11),
                    ],
                )
            )
        # Baseline über alle messenden Quellen (Nacht und Morgen getrennt wären zwei Linien —
        # hier eine Linie je Quelle mit mehr als drei Werten)
        for quelle, punkte in je_quelle.items():
            if len(punkte) < 3:
                continue
            bl: list[Baselinepunkt] = baseline_reihe(punkte, ausgenommen=aus)
            farbe = _QUELLFARBEN.get(quelle, ft.Colors.PRIMARY)
            reihen.append(
                Reihe(
                    [(float((p.tag - beginn).days), p.median) for p in bl if p.median is not None],
                    farbe=farbe,
                    breite=1.5,
                )
            )
            for rand in ("unten", "oben"):
                reihen.append(
                    Reihe(
                        [
                            (float((p.tag - beginn).days), getattr(p, rand))
                            for p in bl
                            if getattr(p, rand) is not None
                        ],
                        farbe=ft.Colors.with_opacity(0.5, farbe),
                        breite=1.0,
                        gestrichelt=True,
                    )
                )
        marken = {float((d - beginn).days): t for d, t in datum_marken(beginn, ende)}
        return karte(
            titel("Ruhe-HF und Nacht-HF"),
            kurve(
                reihen,
                einheit="bpm",
                hoehe=200,
                x_von=0.0,
                x_bis=float(spanne),
                y_spanne_min=20.0,
                x_text=lambda x: marken.get(round(x), ""),
                x_schritte=[1.0],
            ),
            ft.Row(spacing=10, wrap=True, controls=legende),
            hinweis(
                "Punkte je Quelle; die Linie ist der Median der letzten 7 Werte, gestrichelt "
                "± 1 SD. Ausgenommene Tage („nicht mitrechnen“) bleiben Punkt, zählen aber nicht."
            ),
        )

    # -- Wochenlast ---------------------------------------------------------------------------

    def lasten(beginn: date, ende: date) -> tuple[list[Tageslast], list[Testpunkt]]:
        aus = state.ausnahmen.alle(profil_id)
        aus_tage = state.ausnahmen.tage(profil_id)
        aus_messungen = aus.get(RechenAusnahmeRepo.MESSUNG, set())
        trimp: list[tuple[date, float | None, float]] = []
        tests: list[Testpunkt] = []
        for rid, start, a in state.hf_cache.alle(profil_id):
            tag = start.astimezone().date()
            if not beginn <= tag <= ende or rid in aus_messungen or tag in aus_tage:
                continue
            g = a.gesamt or {}
            trimp.append((tag, g.get("trimp"), (g.get("gueltig_s") or 0.0) / 60.0))
            tests.extend(testpunkte_aus_cache(rid, tag, a))
        srpe: dict[date, float] = {}
        feld = tf.standardfeld(state.tagesfelder.alle(profil_id), tf.STANDARD_SRPE)
        if feld is not None:
            for w in state.tageswerte.zwischen(profil_id, beginn, ende, feld_ids=[feld.id]):
                try:
                    srpe[w.tag] = max(srpe.get(w.tag, 0.0), float(w.wert))
                except (TypeError, ValueError):
                    continue
        return tageslasten(trimp, srpe), tests

    def last_karte(tage: list[Tageslast]) -> ft.Control:
        wochen: list[Wochenlast] = wochenlasten(tage)
        if not wochen:
            return karte(
                titel("Wochenlast"),
                hinweis(
                    "Noch keine Aufnahme mit Herzfrequenz-Auswertung im Zeitraum. Die Auswertung "
                    "entsteht beim Öffnen einer Messung in der Herzfrequenz-Sicht — oder unten "
                    "mit „Alle nachrechnen“."
                ),
            )
        kopf = ft.Row(
            spacing=6,
            controls=[
                ft.Text("Woche ab", size=11, opacity=0.6, expand=True),
                ft.Text("TRIMP", size=11, opacity=0.6, width=50, text_align=ft.TextAlign.RIGHT),
                ft.Text("sRPE-Last", size=11, opacity=0.6, width=64, text_align=ft.TextAlign.RIGHT),
                ft.Text("Minuten", size=11, opacity=0.6, width=56, text_align=ft.TextAlign.RIGHT),
                ft.Text("Monot.", size=11, opacity=0.6, width=46, text_align=ft.TextAlign.RIGHT),
                ft.Text("Strain", size=11, opacity=0.6, width=50, text_align=ft.TextAlign.RIGHT),
            ],
        )
        zeilen: list[ft.Control] = [kopf]
        for w in reversed(wochen[-16:]):
            zeilen.append(
                ft.Row(
                    spacing=6,
                    controls=[
                        ft.Text(f"{w.montag:%d.%m.}", size=13, expand=True),
                        ft.Text(zahl(w.trimp), size=13, width=50, text_align=ft.TextAlign.RIGHT),
                        ft.Text(
                            zahl(w.srpe_last), size=13, width=64, text_align=ft.TextAlign.RIGHT
                        ),
                        ft.Text(
                            f"{w.minuten:.0f}", size=13, width=56, text_align=ft.TextAlign.RIGHT
                        ),
                        ft.Text(
                            zahl(w.monotonie, 1), size=13, width=46, text_align=ft.TextAlign.RIGHT
                        ),
                        ft.Text(zahl(w.strain), size=13, width=50, text_align=ft.TextAlign.RIGHT),
                    ],
                )
            )
        return karte(
            titel("Wochenlast"),
            *zeilen,
            hinweis(
                "TRIMP nach Banister aus den Aufnahmen, sRPE-Last = Anstrengung (0–10) × Minuten "
                "des Tages. Monotonie = Mittel/SD der Tageslasten, Strain = Wochenlast × Monotonie "
                "(Foster) — Konventionen, keine Grenzwerte."
            ),
        )

    # -- Tests --------------------------------------------------------------------------------

    def test_karte(tests: list[Testpunkt]) -> ft.Control:
        reihen = hf_testreihe(tests)
        if not reihen:
            return karte(
                titel("Tests"),
                hinweis(
                    "Noch kein Submaximaltest, Talk-Test oder Feld-Maximaltest im Zeitraum "
                    "(Übungen im Paket Standard)."
                ),
            )
        zeilen: list[ft.Control] = []
        for name, punkte in reihen.items():
            zeilen.append(ft.Text(name, size=13, weight=ft.FontWeight.W_600))
            for p in punkte[-10:]:
                teile_ = [f"{p.tag:%d.%m.%Y}"]
                if p.hrr60 is not None:
                    teile_.append(f"HRR60 −{p.hrr60:.0f}")
                if p.hf_ende is not None:
                    teile_.append(
                        ("HFmax-Kandidat " if name == "Feld-Maximaltest" else "HF ")
                        + f"{p.hf_ende:.0f}"
                    )
                if p.mittel_bpm is not None:
                    teile_.append(f"Ø Stufe 2 {p.mittel_bpm:.0f}")
                zeilen.append(ft.Text(" · ".join(teile_), size=12))
        return karte(
            titel("Tests"),
            *zeilen,
            hinweis("Vergleichbar bei gleichem Weg, gleichem Gerät und gleicher Haltung danach."),
        )

    # -- Nachrechnen -----------------------------------------------------------------------

    nachrechnen_knopf = ft.TextButton("Alle nachrechnen", icon=ft.Icons.REFRESH)

    async def nachrechnen() -> None:
        fehlende = state.hf_cache.fehlende(profil_id)
        if not fehlende:
            page.show_dialog(ft.SnackBar(ft.Text("Alle Aufnahmen sind ausgewertet.")))
            return
        nachrechnen_knopf.disabled = True
        with contextlib.suppress(Exception):
            nachrechnen_knopf.update()
        profil = state.hf_profil()
        bereiche = bereiche_fuer(profil, state.hf_einstellungen())
        vorgabe = state.korrekturregeln()
        n = 0
        for rid in fehlende:
            eintrag = state.hrv.laden(rid)
            if eintrag is None:
                continue
            pfad = messungenverzeichnis() / eintrag.file_path
            if not pfad.exists():
                continue

            def rechnen(p=pfad):
                stand = korrektur_laden(p, vorgabe)
                return auswerten(stand.rec, profil=profil, bereiche=bereiche)

            try:
                a = await asyncio.to_thread(rechnen)
            except Exception:
                continue
            state.hf_cache.schreiben(rid, a)
            n += 1
        nachrechnen_knopf.disabled = False
        page.show_dialog(ft.SnackBar(ft.Text(f"{n} Aufnahmen ausgewertet.")))
        zeichnen()

    nachrechnen_knopf.on_click = lambda _=None: page.run_task(nachrechnen)

    def teile() -> list[ft.Control]:
        beginn, ende = beginn_und_ende()
        tage, tests = lasten(beginn, ende)
        return [
            ft.SegmentedButton(
                selected=[state.verlauf_zeitraum if state.verlauf_zeitraum in ZEITRAEUME else "3m"],
                show_selected_icon=False,
                segments=[
                    ft.Segment(value=k, label=ft.Text(text)) for k, (text, _) in ZEITRAEUME.items()
                ],
                on_change=zeitraum_waehlen,
            ),
            ruhe_karte(beginn, ende),
            last_karte(tage),
            test_karte(tests),
            ft.Row(
                spacing=8,
                controls=[
                    nachrechnen_knopf,
                    hinweis(
                        f"{len(state.hf_cache.fehlende(profil_id))} Aufnahmen ohne "
                        "Herzfrequenz-Auswertung"
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ]

    inhalt.controls = teile()
    return ft.View(
        route=ROUTE,
        appbar=ft.AppBar(title=ft.Text("Herzfrequenz im Verlauf")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


__all__ = ["ROUTE", "testpunkte_aus_cache", "verlauf_herzfrequenz_view"]
