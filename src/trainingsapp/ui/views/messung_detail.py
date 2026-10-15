"""Eine Aufzeichnung — Route `/messung/<id>`: ansehen und korrigieren.

Die Rohdatei bleibt unangetastet. Korrekturen sind Vorschläge der Automatik
(`hrv_core.korrektur.vorschlaege`) als Ketten; was übernommen wird, landet in
`sensor_<ts>_analyzed.json` neben der Rohdatei — dieselbe Teilmenge von
`analysis-v1`, die praxis_gui liest, samt den Regeln, mit denen sie entstand.

Was „automatisch" heißt, stellt das Regler-Symbol neben „Korrektur" ein
(`Korrekturregeln`) — je Messung, auf Wunsch als Vorgabe gemerkt. Bei der
Verity Sense zählt standardmäßig nur, was der Sensor nicht verworfen hat; auf
Wunsch prüft das Programm das Verworfene selbst (`korrektur.analysebasis`).
Die Regeln und ihre Gründe: docs/korrektur.md.

Alle Kurven teilen ein Zeitfenster (Breite wählen, waagrecht wischen); die
Lupe an einer Kette zoomt auf ihre Stelle. Die Ansicht öffnet mit den ersten
2 Minuten (`START_BREITE_S`) — „Alles" rechnete beim Öffnen sofort über die
ganze Messung.

Spektrum, Poincaré und DFA gelten für das **Analysefenster**: die ganze
Messung (Vorgabe), einen Abschnitt oder ein Band fester Länge, das man in der
Rohkurve greift und schiebt. Gerechnet wird beim Loslassen, nach einer kurzen
Latenz (Einstellungen → Erweitert), falls noch eine Bewegung nachkommt
(`docs/plan_analyse_leistung.md`).

Aufbau wie live: Kacheln (Werte der ganzen Messung, korrigiert), Hauptkurve,
darunter die Analyse (Zeit ↔ Frequenz ↔ Nichtlinear) mit einer Zusammenfassung
der ganzen Messung je Bereich — Zeitbereich roh und korrigiert, Frequenzbänder
mit Sperrgrund (Task-Force-Mindestdauer), Poincaré, DFA α1 und SampEn.
"""

from __future__ import annotations

import asyncio
import contextlib
from bisect import bisect_left
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import flet as ft
import numpy as np

from trainingsapp.config import datenverzeichnis, messungenverzeichnis
from trainingsapp.core.hrv_einstellungen import ANALYSE_LAENGEN
from trainingsapp.core.models import HrvRecording
from trainingsapp.core.timer import ENDE_MARKE
from trainingsapp.core.timer import name_aus_notiz as abschnittsname
from trainingsapp.hrv_core.atmung import ATEMUEBUNG, RUHE, atemfrequenz, kurzgrund
from trainingsapp.hrv_core.ausschnitte import FARBEN as ABSCHNITT_FARBEN
from trainingsapp.hrv_core.ausschnitte import (
    Abschnitt,
    Grenze,
    abschnitt_spektrum,
    abschnitt_werte,
    achsen_umrechnung,
    aus_grenzen,
    einrasten,
    farben_nach_namen,
    zusatz_lesen,
    zusatz_speichern,
)
from trainingsapp.hrv_core.constants import BAND_OK
from trainingsapp.hrv_core.ereignisse import Zeitbezug, metadaten_schreiben
from trainingsapp.hrv_core.export import export_zip, zugehoerige_dateien
from trainingsapp.hrv_core.frequency import Fensterspektrum, frequenzbereich
from trainingsapp.hrv_core.korrektur import (
    Kette,
    Korrektur,
    Korrigiert,
    SidecarFehler,
    analyse_laden,
    analyse_regeln,
    analyse_speichern,
    analysebasis,
    anwenden,
    korr_zeiten,
    rohfolge,
    vorauswahl,
    vorschlaege,
    zuschneiden,
)
from trainingsapp.hrv_core.nonlinear import compute_dfa_alpha1, compute_poincare, compute_sampen
from trainingsapp.hrv_core.ppi import ppi_verworfen, schlagzeiten
from trainingsapp.hrv_core.recording import Recording, laden
from trainingsapp.hrv_core.regeln import Korrekturregeln
from trainingsapp.hrv_core.segments import filter_rr
from trainingsapp.hrv_core.time_domain import compute_time_domain
from trainingsapp.hrv_core.trends import DFA_MIN_SCHLAEGE, KENNZAHLEN, reihe, titel
from trainingsapp.ui.components.analyse import Analyse, Analysefenster
from trainingsapp.ui.components.bereich import BereichEditor, band, schatten
from trainingsapp.ui.components.kacheln import KACHELN, KachelWert, anzeige, zahl
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.korrektur_blatt import korrektur_blatt, regler_knopf
from trainingsapp.ui.components.kurve import RR_SPANNE_MIN_MS, Reihe, kurve
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.notizen import (
    Notizfeld,
    senkrechte,
    uebungs_katalog,
    uebungsquellen,
)
from trainingsapp.ui.components.titel import (
    geuebte_plaene,
    titel_blatt,
    titel_kopf,
    titel_vorschlaege,
)
from trainingsapp.ui.components.verlauf import FARBEN, fenster_text
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.components.zeitfenster import Fenster, wischbar
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.messung import ohne_rr

QUALITAET = {
    "rr_ekg": "RR aus EKG (volle HRV)",
    "ppi_optisch": "Pulsintervalle optisch (Frequenzwerte mit Vorbehalt)",
    "bpm_only": "nur Herzfrequenz (keine HRV)",
}


def _uhr(sekunden: float) -> str:
    s = int(sekunden)
    return f"{s // 60}:{s % 60:02d}"


def _wert(d: dict | None, key: str, nachkomma: int = 1) -> str:
    if not d or d.get(key) is None:
        return "–"
    return zahl(d[key], nachkomma)


def _linie(
    paare: Iterable[tuple[float, float]],
    naht_vor: Iterable[int],
    unten: float = 0.0,
    oben: float = float("inf"),
    x_von: float = float("-inf"),
    x_bis: float = float("inf"),
) -> tuple[list[tuple[float, float]], list[int]]:
    """Punkte im Bereich ``(unten, oben)`` und die Nähte als Indizes in diese Liste.

    ``naht_vor`` zählt in ``paare``; fällt ein Punkt heraus, rutscht seine Naht
    auf den nächsten sichtbaren. ``x_von``/``x_bis``: sichtbares Zeitfenster —
    Flet schneidet nicht ab, Punkte daneben lägen über den Achsen.
    """
    vor = set(naht_vor)
    punkte: list[tuple[float, float]] = []
    idx: list[int] = []
    offen = False
    for i, (t, r) in enumerate(paare):
        offen = offen or i in vor
        if not (x_von <= t <= x_bis and unten < r < oben):
            continue
        if offen and punkte:
            idx.append(len(punkte))
        offen = False
        punkte.append((t, r))
    return punkte, idx


def _verworfen_text(rec_verworfen: tuple[int, int] | None) -> Sequence[str]:
    """Anteil der vom Sensor verworfenen Intervalle — leer ohne PPI-Rohdaten."""
    if not rec_verworfen or not rec_verworfen[1] or not rec_verworfen[0]:
        return []
    return [f"{round(100 * rec_verworfen[0] / rec_verworfen[1])} % vom Sensor verworfen"]


#: Breiten des Zeitfensters (s); 0 = die ganze Messung
BREITEN = [(60, "1 min"), (120, "2 min"), (300, "5 min"), (0, "Alles")]
#: So breit öffnet die Aufzeichnung — am Anfang der Messung (Ben, 14.10.2026)
START_BREITE_S = 120

#: Analysefenster: wofür Spektrum, Poincaré und DFA gerechnet werden
AW_ALLES = "alles"
AW_ABSCHNITT = "abschnitt"
AW_BAND = "band"


CROP = "crop"
ABSCHNITT = "abschnitt"
#: Farbe des verschiebbaren Analysefensters in der Rohkurve
BAND_FARBE = ft.Colors.TERTIARY


@dataclass
class _Analysewahl:
    """Das gewählte Analysefenster und, beim Band, ob es gerade gezogen wird."""

    art: str = AW_ALLES
    abschnitt_id: str | None = None
    laenge_s: int = 300
    #: Beginn des Bands auf der Kurvenachse — ``None`` = mitten im sichtbaren Ausschnitt
    von: float | None = None
    #: Band gegriffen: Abstand Finger − Beginn (s)
    griff: float | None = None
    #: Losgelassen, das Nachrechnen ist geplant
    wartet: bool = False
    #: Laufende Nummer des Nachrechnen-Auftrags — nur der letzte rechnet
    auftrag: int = 0


@dataclass
class _Kurvenmodus:
    """Was Tippen und Ziehen in der Rohkurve gerade tun."""

    #: Bereich wählen — fürs Zuschneiden (``art`` = `CROP`) oder einen Abschnitt
    editor: BereichEditor | None = None
    art: str = ""
    #: Der bearbeitete Abschnitt (``None`` = ein neuer)
    abschnitt: Abschnitt | None = None
    name_feld: ft.TextField | None = None
    #: Ablesen: der Strich steht an ``strich`` (s), darunter alle Werte
    ablesen: bool = False
    strich: float | None = None


def _wertchip(farbe: str | None, name: str, wert: str, einheit: str) -> ft.Control:
    return ft.Row(
        spacing=4,
        tight=True,
        controls=[
            ft.Container(width=8, height=8, border_radius=4, bgcolor=farbe or ft.Colors.OUTLINE),
            ft.Text(name, size=11, opacity=0.7),
            ft.Text(wert, size=13, weight=ft.FontWeight.W_600),
            ft.Text(einheit, size=11, opacity=0.7),
        ],
    )


def messung_detail_view(page: ft.Page, state: AppState, eintrag: HrvRecording) -> ft.View:
    route = f"/messung/{eintrag.id}"
    pfad = messungenverzeichnis() / eintrag.file_path

    def ansicht(inhalt: list[ft.Control]) -> ft.View:
        return ft.View(
            route=route,
            appbar=ft.AppBar(
                title=ft.Text(f"Messung {eintrag.started_at.astimezone():%d.%m. %H:%M}"),
                actions=[
                    ft.IconButton(
                        ft.Icons.CONTENT_CUT,
                        tooltip="Zuschneiden",
                        on_click=lambda: crop_oeffnen(),
                    ),
                    ft.IconButton(
                        ft.Icons.SHARE, tooltip="Exportieren (ZIP)", on_click=exportieren
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE, tooltip="Aus der Liste entfernen", on_click=fragen
                    ),
                ],
            ),
            scroll=ft.ScrollMode.AUTO,
            padding=12,
            controls=[sicher(ft.Column(spacing=12, controls=inhalt), expand=False)],
        )

    # -- Exportieren -----------------------------------------------------------

    async def exportieren() -> None:
        """Rohdatei samt Korrektur und Diagnoseprotokoll als ZIP herausgeben."""
        dateien = zugehoerige_dateien(pfad)
        if not dateien:
            page.show_dialog(ft.SnackBar(ft.Text("Keine Dateien zu dieser Messung gefunden.")))
            return
        daten = export_zip(dateien, datenverzeichnis())
        await weitergeben(page, f"{pfad.stem}.zip", daten, "application/zip")

    # -- Entfernen -------------------------------------------------------------

    def fragen() -> None:
        page.show_dialog(dialog)

    def abbrechen() -> None:
        page.pop_dialog()

    async def entfernen() -> None:
        state.hrv.loeschen(eintrag.id)
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text("Aus der Liste entfernt — die Datei bleibt.")))
        await page.push_route("/")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Aufzeichnung entfernen?"),
        content=ft.Text(
            "Sie verschwindet aus der Liste. Die Messdatei bleibt im Ordner "
            f"„{pfad.parent.name}“ liegen und lässt sich in praxis_gui weiter öffnen."
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.FilledButton("Entfernen", on_click=entfernen),
        ],
    )

    if not pfad.exists():
        return ansicht(
            [
                ft.Text("Die Messdatei fehlt.", size=16, weight=ft.FontWeight.W_600),
                ft.Text(str(pfad), size=12, selectable=True, opacity=0.7),
            ]
        )

    rec = laden(pfad)
    verworfen = ppi_verworfen(rec)
    verity = rec.ppi_pakete is not None
    einst = state.hrv_einstellungen()

    # -- Zustand: Regeln → Basis → Vorschläge → Auswahl -------------------------
    # Regeln der gespeicherten Korrektur, sonst die gerätelokale Vorgabe.
    # Optische Intervalle streuen mehr: Malik „nach Sensor" = 0.30 (Vertrag, Abschnitt 5).
    gespeicherte_regeln = analyse_regeln(pfad)
    z = _Zustand(rec, gespeicherte_regeln or state.korrekturregeln())
    z.gespeichert = analyse_laden(pfad, z.basis)
    z.auswahl_aus(z.gespeichert, ohne_sidecar=gespeicherte_regeln is None)

    dauer = max((t for t, _ in z.roh_punkte), default=0.0)
    start_breite = START_BREITE_S if dauer > START_BREITE_S else 0
    fenster = (
        Fenster(float(start_breite), float(start_breite))
        if start_breite
        else Fenster(dauer or 1.0, None)
    )
    # Notizen hängen an den Zeilen der Rohdatei; die Kurve hat ihre eigene Zeitachse
    zeilen_achse = schlagzeiten(rec)
    # Crop und eigene Abschnitte stehen im Sidecar auf der Herzuhr der Rohdatei
    nach_datei, nach_achse = achsen_umrechnung(zeilen_achse, [b.t_s for b in rec.beats])
    z.ausschnitt, eigene = zusatz_lesen(pfad, nach_achse)
    zeitbezug = Zeitbezug(lambda: rec.beats, rec.start_utc, achse=lambda: zeilen_achse)

    kopf_text = ft.Text(size=13, opacity=0.8)
    hinweis_text = ft.Text(size=12, color=FARBEN["rot"])
    titel_box = ft.Container()
    # Die Datei ist die Wahrheit — die Zeile hält nur Kopien für die Liste
    if rec.titel != eintrag.title:
        state.hrv.titel_setzen(eintrag.id, rec.titel)
    beschreibung = rec.notiz or eintrag.note
    kacheln_box = ft.Container()
    rr_box = ft.Container()
    ketten_box = ft.Column(spacing=0)
    breite_wahl = ft.SegmentedButton(
        selected=[str(start_breite)],
        # Ein Abschnitt kann jede Breite haben — dann ist keine Taste gewählt
        allow_empty_selection=True,
        show_selected_icon=False,
        segments=[ft.Segment(value=str(s), label=ft.Text(t)) for s, t in BREITEN],
    )
    speichern_knopf = ft.FilledButton("Korrektur speichern", icon=ft.Icons.SAVE, disabled=True)

    # -- Kennzahlen der ganzen Messung (korrigiert) --------------------------------

    def zeitbereich(korrigiert: bool) -> dict[str, Any] | None:
        """Ø HF, Ø RR, RMSSD, SDNN, pNNx — roh oder korrigiert, Nähte übersprungen."""
        korr = z.analyse_korr(roh=not korrigiert)
        return compute_time_domain(
            korr.rr_ms, pnn_threshold_ms=state.ansicht().pnn_ms, breaks=korr.breaks
        )

    def frequenz() -> dict[str, Any] | None:
        korr = z.analyse_korr()
        return z.merken("frequenz", lambda: frequenzbereich(korr.rr_ms, korr.t_s, korr.breaks))

    def nichtlinear() -> dict[str, Any]:
        def rechnen() -> dict[str, Any]:
            korr = z.analyse_korr()
            valide = filter_rr(korr.rr_ms)
            poincare = compute_poincare(korr.rr_ms, korr.breaks) or {}
            dfa = (
                compute_dfa_alpha1(valide, window_n=int(valide.size))
                if valide.size >= DFA_MIN_SCHLAEGE
                else None
            )
            # SampEn ist quadratisch — über sehr lange Messungen zu teuer
            sampen = compute_sampen(valide) if valide.size <= 3000 else None
            return {
                **poincare,
                "dfa_alpha1": dfa["dfa_alpha1"] if dfa else None,
                "sampen": sampen,
                "n": int(valide.size),
            }

        return z.merken("nichtlinear", rechnen)

    def atmung() -> dict[str, Any]:
        """Atemfrequenz der ganzen Messung: Median der gültigen 60-s-Fenster."""

        def rechnen() -> dict[str, Any]:
            t, rr, _ = analyse_reihe()
            modus = ATEMUEBUNG if state.hrv_einstellungen().atemuebung else RUHE
            # Alle 15 s ein Minutenfenster — über Stunden höchstens 2000 Fenster
            schritt = max(15.0, float(t[-1] - t[0]) / 2000.0) if t.size else 15.0
            fenster = [
                atemfrequenz(t, rr, ende - 60.0, ende, modus=modus)
                for ende in (np.arange(t[0] + 60.0, t[-1] + 1e-9, schritt) if t.size else [])
            ]
            gueltig = [a for a in fenster if a.gueltig]
            gruende = Counter(g for a in fenster if not a.gueltig for g in a.gruende[:1])
            return {
                "rate": float(np.median([a.rate_pro_min for a in gueltig])) if gueltig else None,
                "rsa": float(np.median([a.rsa_bpm for a in gueltig])) if gueltig else None,
                "gueltig": len(gueltig),
                "fenster": len(fenster),
                "grund": kurzgrund([gruende.most_common(1)[0][0]]) if gruende else "",
            }

        return z.merken(
            "atmung" + ("_uebung" if state.hrv_einstellungen().atemuebung else ""), rechnen
        )

    def kachel_werte() -> list[KachelWert]:
        """Dieselben Werte wie live, für die ganze Messung."""
        a = state.ansicht()
        td = zeitbereich(True) or {}
        korr = z.korrigiert()
        gross = set(einst.gross)
        out: list[KachelWert] = []
        for key in einst.kacheln:
            art = KACHELN.get(key)
            if art is None or key == "schwankung":
                continue
            g = key in gross
            if key == "hf":
                out.append(KachelWert("Ø Herzfrequenz", zahl(td.get("mean_bpm")), "bpm", gross=g))
            elif key == "rr":
                titel_rr = "Ø PPI" if verity else "Ø RR"
                out.append(KachelWert(titel_rr, zahl(td.get("mean_rr")), "ms", gross=g))
            elif key == "ulf":
                f = frequenz() or {}
                gesperrt = f.get("band_status", {}).get("ulf") not in (None, BAND_OK)
                out.append(
                    KachelWert(
                        art.titel,
                        zahl(f.get("ulf"), 0),
                        "ms²",
                        gross=g,
                        grund="braucht 4 h Messung" if gesperrt else "",
                    )
                )
            elif key == "artefakte":
                out.append(
                    KachelWert(
                        "Korrigiert",
                        str(korr.interpoliert + korr.entfernt),
                        zusatz=f"von {len(rec.beats)}",
                        gross=g,
                    )
                )
            elif key in ("atemfrequenz", "rsa"):
                at = atmung()
                kz = KENNZAHLEN[key]
                wert = at["rate"] if key == "atemfrequenz" else at["rsa"]
                hinweis_atmung = (
                    f"{at['gueltig']} von {at['fenster']} Minutenfenstern deutlich"
                    if at["gueltig"]
                    else at["grund"]
                )
                out.append(
                    KachelWert(
                        kz.titel,
                        zahl(wert, kz.nachkomma),
                        kz.einheit,
                        farbe=FARBEN[key],
                        gross=g,
                        grund=hinweis_atmung if key == "atemfrequenz" else "",
                    )
                )
            elif art.kennzahl is not None:
                k = art.kennzahl
                kz = KENNZAHLEN[k]
                out.append(
                    KachelWert(
                        titel(k, a.pnn_ms),
                        *_gesamtwert(k, td, frequenz, nichtlinear, kz.nachkomma),
                        farbe=FARBEN[k],
                        gross=g,
                    )
                )
        return out

    def tabelle(bereich: str) -> ft.Control | None:
        if bereich == "frequenz":
            return _frequenz_tabelle(frequenz())
        if bereich == "nichtlinear":
            return _nichtlinear_tabelle(nichtlinear(), verity)
        return _zeit_tabelle(zeitbereich(False), zeitbereich(True), state.ansicht().pnn_ms)

    def kopf() -> None:
        teile = [
            rec.geraet or eintrag.geraet,
            _uhr(dauer),
            QUALITAET.get(rec.effektive_qualitaet(), rec.effektive_qualitaet()),
            *_verworfen_text(verworfen),
        ]
        if z.basis.aufgenommen:
            teile.append(f"{z.basis.aufgenommen} davon selbst geprüft")
        if z.ausschnitt is not None:
            lo, hi = z.ausschnitt
            teile.append(f"zugeschnitten {_uhr(lo)}–{_uhr(hi)}")
        kopf_text.value = "  ·  ".join(t for t in teile if t)
        # Mehr als die Hälfte verworfen: Folgt man dem Sensor, bleiben Bruchstücke.
        viel = bool(verworfen and verworfen[1] and verworfen[0] * 2 > verworfen[1])
        hinweis_text.visible = viel
        hinweis_text.value = (
            "Der Sensor hat die meisten Intervalle verworfen — meist Bewegung, auch "
            "bei festem Sitz. Sie sind wieder aufgenommen und nach den eigenen Regeln "
            "geprüft. Vorsicht: In Bewegung sind sie meist falsch, RMSSD liegt dann "
            "leicht um ein Mehrfaches zu hoch."
            if z.basis.aufgenommen
            else "Der Sensor hat die meisten Intervalle verworfen — meist Bewegung, "
            "auch bei festem Sitz. Gewertet wird nur, was er sicher gemessen hat; "
            "die Kennzahlen beruhen auf Bruchstücken. Für HRV ruhig sitzen oder "
            "liegen — in Bewegung misst ein Brustgurt (H10) zuverlässig."
        )

    def analyse_reihe() -> tuple[Any, Any, Any]:
        korr = z.korrigiert()

        def rechnen() -> tuple[Any, Any, Any]:
            t, rr, naht = reihe(korr_zeiten(korr, z.achse), korr.rr_ms, korr.breaks)
            if z.ausschnitt is not None:  # Crop: Kurven nur im Ausschnitt
                im = (t >= z.ausschnitt[0]) & (t <= z.ausschnitt[1])
                t, rr, naht = t[im], rr[im], naht[im]
            return t, rr, naht

        return z.merken("reihe", rechnen)

    def hf_geraet() -> list[tuple[float, float]]:
        beats = z.basis.rec.beats
        return [(x, float(b.hf_bpm)) for x, b in zip(z.achse, beats, strict=True) if b.hf_bpm]

    def zeiten_korr() -> list[float]:
        """Zeit je korrigiertem Wert — einmal je Auswahl, nicht bei jedem Neuzeichnen."""
        return z.merken("korr_zeiten", lambda: korr_zeiten(z.korrigiert(), z.achse))

    # -- Modus der Rohkurve: normal · Bereich wählen · Ablesen --------------------
    # Normal blättert Ziehen die Kurve, ein Tipp gehört den Notizen („In Kurve").
    # Mit offenem Bereichseditor (Zuschneiden, Abschnitt) zieht der Finger die
    # Grenze; beim Ablesen den Strich, unter dem alle Werte stehen.

    m = _Kurvenmodus()
    editor_box = ft.Container(visible=False)
    ablese_box = ft.Container(visible=False)
    ablesen_knopf = ft.TextButton(
        "Ablesen",
        icon=ft.Icons.ADS_CLICK,
        tooltip="Werte an einer Stelle der Kurven ablesen",
        on_click=lambda: ablesen_umschalten(),
    )

    def kurven(mit_analyse: bool = True) -> None:
        x_von, x_bis = fenster.bereich(dauer)
        korr = z.korrigiert()
        markiert = {v.beat_index for k in z.ketten for v in k.vorschlag}
        beats = z.basis.rec.beats
        art = [
            (z.achse[i], float(beats[i].rr_ms))
            for i in sorted(markiert)
            if i < len(beats) and 0 < beats[i].rr_ms < 2600 and x_von <= z.achse[i] <= x_bis
        ]
        # Grau reißt nur an Messlücken ab; farbig auch an Nähten und Ausschlüssen —
        # dort gibt es keine Schlag-zu-Schlag-Differenz.
        sichtbar, sichtbar_naehte = _linie(z.roh_punkte, z.roh_naehte, 200, 2600, x_von, x_bis)
        zeiten = zeiten_korr()
        korr_linie, korr_naehte = _linie(
            zip(zeiten, korr.rr_ms, strict=True), korr.breaks, x_von=x_von, x_bis=x_bis
        )
        strich = m.strich if m.ablesen else None
        rr_box.content = kurve(
            [
                *bereich_reihen(x_von, x_bis),
                *band_reihen(x_von, x_bis),
                Reihe(
                    sichtbar,
                    farbe=ft.Colors.OUTLINE,
                    breite=1,
                    naehte=sichtbar_naehte,
                    skala=False,
                ),
                Reihe(korr_linie, farbe=ft.Colors.PRIMARY, naehte=korr_naehte),
                Reihe(art, farbe=FARBEN["rot"], nur_punkte=True, skala=False),
                *notizfeld.marken(x_von, x_bis),
                *(m.editor.reihen(x_von, x_bis) if m.editor is not None else []),
                *(
                    [senkrechte([strich], ft.Colors.ON_SURFACE, 1.2, gestrichelt=False)]
                    if strich is not None and x_von <= strich <= x_bis
                    else []
                ),
            ],
            einheit="PPI ms" if verity else "RR ms",
            hoehe=220,
            x_von=x_von,
            x_bis=x_bis,
            y_spanne_min=RR_SPANNE_MIN_MS,
        )
        if mit_analyse:
            analyse.zeichnen(x_von, x_bis, strich=strich)
            if strich is not None:
                ablesen_zeichnen()

    def bereich_reihen(x_von: float, x_bis: float) -> list[Reihe]:
        """Zuschnitt grau schattiert, Abschnitte als Balken oben — gestapelt, wo sie sich decken."""
        out: list[Reihe] = []
        if z.ausschnitt is not None and m.art != CROP:
            lo, hi = z.ausschnitt
            grau = ft.Colors.with_opacity(0.14, ft.Colors.ON_SURFACE)
            if lo > x_von:
                out.append(schatten(x_von, min(lo, x_bis), grau))
            if hi < x_bis:
                out.append(schatten(max(hi, x_von), x_bis, grau))
        bearbeitet = m.abschnitt.id if m.abschnitt is not None else None
        # Der Balken im Editor liegt oben — die übrigen rücken eine Ebene tiefer
        versatz = 1 if m.art == ABSCHNITT else 0
        ebenen: list[float] = []  # Ende des letzten Balkens je Ebene
        for a in sorted(eigene, key=lambda a: a.von_s):
            ebene = next((i for i, ende in enumerate(ebenen) if a.von_s >= ende), len(ebenen))
            if ebene == len(ebenen):
                ebenen.append(a.bis_s)
            ebenen[ebene] = a.bis_s
            if a.id == bearbeitet or a.bis_s < x_von or a.von_s > x_bis:
                continue
            balken = band(max(a.von_s, x_von), min(a.bis_s, x_bis), a.farbe)
            balken.ebene = min(ebene + versatz, 3)
            out.append(balken)
        return out

    def kurve_tippen(x: float) -> None:
        if m.editor is not None:
            m.editor.tippen(x)
        elif m.ablesen:
            strich_setzen(x)
        else:
            notizfeld.tippen(x)

    def kurve_greifen(x: float) -> bool:
        if m.editor is not None:
            return m.editor.ziehen(x)
        if m.ablesen:
            strich_setzen(x, zeichnen=False)
            return True
        return band_greifen(x)

    def analyse_tippen(x: float) -> None:
        if m.ablesen:
            strich_setzen(x)

    def analyse_greifen(x: float) -> bool:
        if not m.ablesen:
            return False
        strich_setzen(x, zeichnen=False)
        return True

    # -- Ablesen ---------------------------------------------------------------------

    def ablesen_umschalten() -> None:
        m.ablesen = not m.ablesen
        if m.ablesen and m.strich is None:
            m.strich = sum(fenster.bereich(dauer)) / 2
        if m.ablesen:
            m.strich = schlag_bei(m.strich or 0.0)
        ablesen_knopf.style = (
            ft.ButtonStyle(bgcolor=ft.Colors.with_opacity(0.16, ft.Colors.PRIMARY))
            if m.ablesen
            else None
        )
        ablese_box.visible = m.ablesen
        nur_kurven()

    def naechster(zeiten: Sequence[float], x: float) -> int:
        """Index der Zeit, die ``x`` am nächsten liegt (``zeiten`` aufsteigend)."""
        i = bisect_left(zeiten, x)
        if i <= 0:
            return 0
        if i >= len(zeiten):
            return len(zeiten) - 1
        return i if zeiten[i] - x < x - zeiten[i - 1] else i - 1

    def schlag_bei(x: float) -> float:
        """Der korrigierte Schlag, der ``x`` am nächsten liegt — dort steht der Strich."""
        zeiten = zeiten_korr()
        if not zeiten:
            return x
        return float(zeiten[naechster(zeiten, x)])

    def strich_setzen(x: float, *, zeichnen: bool = True) -> None:
        m.strich = schlag_bei(min(max(x, 0.0), dauer))
        if zeichnen:
            nur_kurven()

    def strich_schritt(richtung: int) -> None:
        """Ein Schlag vor oder zurück; die Kurve rückt mit, wenn der Strich hinausläuft."""
        zeiten = zeiten_korr()
        jetzt = m.strich
        if not zeiten or jetzt is None:
            return
        i = naechster(zeiten, jetzt)
        m.strich = float(zeiten[min(max(i + richtung, 0), len(zeiten) - 1)])
        x_von, x_bis = fenster.bereich(dauer)
        if not x_von <= m.strich <= x_bis:
            zentrieren(m.strich)
        nur_kurven()

    def ablesen_zeichnen() -> None:
        x = m.strich
        if x is None:
            return
        korr = z.korrigiert()
        zeiten = zeiten_korr()
        werte: list[tuple[str | None, str, str, str]] = []
        if zeiten:
            i = naechster(zeiten, x)
            rr = korr.rr_ms[i]
            zusatz = " (interpoliert)" if korr.flag[i] != "orig" else ""
            werte.append(
                (ft.Colors.PRIMARY, "RR" if not verity else "PPI", zahl(rr), "ms" + zusatz)
            )
            werte.append((FARBEN["hf_rr"], "HF", zahl(60000 / rr if rr else None), "bpm"))
        roh = min(z.roh_punkte, key=lambda p: abs(p[0] - x), default=None)
        if roh is not None and abs(roh[0] - x) < 3:
            werte.append((ft.Colors.OUTLINE, "roh", zahl(roh[1]), "ms"))
        geraet = min(hf_geraet(), key=lambda p: abs(p[0] - x), default=None)
        if geraet is not None and abs(geraet[0] - x) < 3:
            werte.append((FARBEN["hf_geraet"], "HF Gerät", zahl(geraet[1]), "bpm"))
        for k, name, wert in analyse.werte_bei(x):
            kz = KENNZAHLEN[k]
            stellen = 0 if abs(wert) >= 100 else 1 if abs(wert) >= 10 else 2
            werte.append((FARBEN.get(k), name, zahl(wert, stellen), kz.einheit))
        in_abschnitten = [a.name for a in eigene if a.von_s <= x <= a.bis_s]
        uhr = zeitbezug.uhr(zeitbezug.anker(x))
        kopfzeile = f"{_uhr(x)}" + (f" · {uhr} Uhr" if uhr else "")
        ablese_box.content = ft.Container(
            border_radius=10,
            padding=ft.Padding.only(left=4, right=4, top=2, bottom=8),
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
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
                                on_click=lambda: strich_schritt(-1),
                            ),
                            ft.Text(kopfzeile, size=14, weight=ft.FontWeight.W_600),
                            ft.IconButton(
                                ft.Icons.CHEVRON_RIGHT,
                                tooltip="Ein Schlag weiter",
                                on_click=lambda: strich_schritt(1),
                            ),
                            ft.Text(
                                " · ".join(in_abschnitten),
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
                                on_click=lambda: ablesen_umschalten(),
                            ),
                        ],
                    ),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=10),
                        content=ft.Row(
                            wrap=True,
                            spacing=14,
                            run_spacing=4,
                            controls=[_wertchip(*w) for w in werte],
                        ),
                    ),
                ],
            ),
        )

    # -- Abschnitte (Werte je Teil der Messung) ---------------------------------

    abschnitte_box = ft.Column(spacing=2)

    def notiz_punkte() -> list[tuple[float, str]]:
        punkte = []
        for e in rec.ereignisse:
            x = zeitbezug.x(e)
            if x is not None:
                punkte.append((x, str(e.get("text") or "Notiz")))
        return sorted(punkte)

    def grenzen() -> tuple[float, float]:
        return z.ausschnitt if z.ausschnitt is not None else (0.0, dauer)

    def werte_von(a: Abschnitt) -> dict[str, Any]:
        lo, hi = grenzen()
        von, bis = max(a.von_s, lo), min(a.bis_s, hi)
        korr = z.korrigiert()
        pnn_ms = state.ansicht().pnn_ms
        atem_modus = ATEMUEBUNG if state.hrv_einstellungen().atemuebung else RUHE
        return z.merken(
            f"abschnitt:{a.id}:{von:.3f}:{bis:.3f}:{pnn_ms:g}:{atem_modus}:{int(einst.frequenz)}",
            lambda: abschnitt_werte(
                korr,
                korr_zeiten(korr, z.achse),
                von,
                bis,
                pnn_ms=pnn_ms,
                frequenz=einst.frequenz,
                atem_modus=atem_modus,
            ),
        )

    def abschnitt_zeile(a: Abschnitt) -> ft.Control:
        w = werte_von(a)
        teile = [f"Ø HF {zahl(w['mean_bpm'])}", f"RMSSD {zahl(w['rmssd'])}"]
        teile.append(f"SDNN {zahl(w['sdnn'])}")
        if w["atem"] is not None:
            teile.append(f"Atem {zahl(w['atem'], 1)}/min")
        if w["lf_hf"] is not None:
            teile.append(f"LF/HF {zahl(w['lf_hf'], 2)}")
        return ft.Container(
            on_click=lambda: abschnitt_bearbeiten(a),
            border_radius=8,
            padding=ft.Padding.only(left=0, right=0, top=2, bottom=2),
            bgcolor=(
                ft.Colors.with_opacity(0.08, a.farbe)
                if m.abschnitt is not None and m.abschnitt.id == a.id
                else None
            ),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(width=4, height=36, border_radius=2, bgcolor=a.farbe),
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(a.name, size=13, weight=ft.FontWeight.W_600, max_lines=1),
                            ft.Text(
                                f"{_uhr(a.von_s)}–{_uhr(a.bis_s)} ({_uhr(a.dauer_s)})  ·  "
                                + "  ·  ".join(teile),
                                size=12,
                                opacity=0.75,
                            ),
                        ],
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        icon_size=18,
                        tooltip="Abschnitt löschen",
                        on_click=lambda: abschnitt_loeschen(a),
                    ),
                ],
            ),
        )

    def abschnitte_zeichnen() -> None:
        if eigene:
            abschnitte_box.controls = [
                abschnitt_zeile(a) for a in sorted(eigene, key=lambda a: a.von_s)
            ]
        else:
            abschnitte_box.controls = [
                hinweis(
                    "Noch keine Abschnitte. „+ Abschnitt“ wählt einen Bereich in der Kurve; "
                    "im Menü daneben werden Notizen zu Grenzen. Mit dem Timer entstehen sie "
                    "beim Speichern der Aufnahme von selbst."
                )
            ]

    def zusatz_sichern() -> None:
        try:
            zusatz_speichern(pfad, z.ausschnitt, eigene, nach_datei)
        except (OSError, SidecarFehler) as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Nicht gespeichert: {fehler}")))

    def abschnitt_loeschen(a: Abschnitt) -> None:
        vorher = list(eigene)
        eigene[:] = [b for b in eigene if b.id != a.id]
        if m.abschnitt is not None and m.abschnitt.id == a.id:
            editor_schliessen(zeichnen_=False)
        zusatz_sichern()
        zeichnen()

        def zurueck() -> None:
            eigene[:] = vorher
            zusatz_sichern()
            zeichnen()

        page.show_dialog(
            ft.SnackBar(
                ft.Text(f"„{a.name}“ gelöscht"),
                action=ft.SnackBarAction("Rückgängig", on_click=zurueck),
            )
        )

    def alle_loeschen() -> None:
        if not eigene:
            return
        vorher = list(eigene)
        eigene.clear()
        editor_schliessen(zeichnen_=False)
        zusatz_sichern()
        zeichnen()

        def zurueck() -> None:
            eigene[:] = vorher
            zusatz_sichern()
            zeichnen()

        page.show_dialog(
            ft.SnackBar(
                ft.Text(
                    "1 Abschnitt gelöscht"
                    if len(vorher) == 1
                    else f"{len(vorher)} Abschnitte gelöscht"
                ),
                action=ft.SnackBarAction("Rückgängig", on_click=zurueck),
            )
        )

    def aus_notizen_oeffnen() -> None:
        """Notizen zu Abschnittsgrenzen machen — welche, entscheidet man selbst."""
        lo, hi = grenzen()
        notizen = [(x, t) for x, t in notiz_punkte() if lo <= x <= hi]
        if not notizen:
            page.show_dialog(ft.SnackBar(ft.Text("Keine Notizen in der Messung.")))
            return
        haken = [ft.Checkbox(value=True) for _ in notizen]
        vorschau = ft.Text(size=13, weight=ft.FontWeight.W_600)

        def grenzen_aus_haken() -> list[Grenze]:
            return [
                Grenze(x, abschnittsname(t), schluss=t.strip() == ENDE_MARKE)
                for (x, t), h in zip(notizen, haken, strict=True)
                if h.value
            ]

        def vorschau_zeichnen() -> None:
            n = len(aus_grenzen(grenzen_aus_haken(), lo, hi))
            vorschau.value = f"Ergibt {n} {'Abschnitt' if n == 1 else 'Abschnitte'}"

        def umgeschaltet() -> None:
            vorschau_zeichnen()
            vorschau.update()

        def alle(an: bool) -> None:
            for h in haken:
                h.value = an
            vorschau_zeichnen()
            page.update()

        def anlegen() -> None:
            neu = aus_grenzen(grenzen_aus_haken(), lo, hi)
            farben_nach_namen(neu, vergeben=len(eigene))
            eigene.extend(neu)
            zusatz_sichern()
            page.pop_dialog()
            zeichnen()

        for h in haken:
            h.on_change = lambda _: umgeschaltet()
        vorschau_zeichnen()
        zeilen = [
            ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    h,
                    ft.Text(_uhr(x), size=12, opacity=0.7, width=44),
                    ft.Text(t, size=13, expand=True, max_lines=2),
                ],
            )
            for (x, t), h in zip(notizen, haken, strict=True)
        ]
        page.show_dialog(
            ft.BottomSheet(
                show_drag_handle=True,
                scrollable=True,
                content=ft.Container(
                    padding=ft.Padding.only(left=16, right=16, bottom=16),
                    content=ft.Column(
                        tight=True,
                        spacing=8,
                        controls=[
                            ft.Text("Abschnitte aus Notizen", size=18, weight=ft.FontWeight.W_600),
                            ft.Text(
                                "Jede gewählte Notiz beginnt einen Abschnitt, benannt nach "
                                "ihr; er reicht bis zur nächsten gewählten. „Timer fertig“ "
                                "beendet nur. Notizen, die mitten in einer Übung stehen, "
                                "einfach abwählen.",
                                size=12,
                                opacity=0.7,
                            ),
                            ft.Row(
                                controls=[
                                    ft.TextButton("Alle", on_click=lambda: alle(True)),
                                    ft.TextButton("Keine", on_click=lambda: alle(False)),
                                ]
                            ),
                            *zeilen,
                            vorschau,
                            ft.Row(
                                alignment=ft.MainAxisAlignment.END,
                                controls=[
                                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                                    ft.FilledButton("Anlegen", icon=ft.Icons.ADD, on_click=anlegen),
                                ],
                            ),
                        ],
                    ),
                ),
            )
        )

    # -- Bereich wählen: Zuschneiden und Abschnitte ----------------------------------

    def editor_oeffnen(art: str, von: float, bis: float, abschnitt: Abschnitt | None) -> None:
        lo, hi = (0.0, dauer) if art == CROP else grenzen()
        farbe = (
            abschnitt.farbe
            if abschnitt is not None
            else (
                ft.Colors.PRIMARY
                if art == CROP
                else ABSCHNITT_FARBEN[len(eigene) % len(ABSCHNITT_FARBEN)]
            )
        )
        if m.ablesen:
            ablesen_umschalten()
        m.art, m.abschnitt = art, abschnitt
        m.editor = BereichEditor(
            von=von,
            bis=bis,
            anfang=lo,
            ende=hi,
            notizen=notiz_punkte,
            geaendert=lambda: nur_kurven(mit_analyse=False),
            zeigen=zentrieren_und_zeichnen,
            breite=lambda: fenster.breite_s,
            farbe=farbe,
            schattieren=art == CROP,
        )
        name = ft.TextField(
            label="Name",
            value=abschnitt.name if abschnitt is not None else name_vorschlag(von),
            dense=True,
            capitalization=ft.TextCapitalization.SENTENCES,
        )
        m.name_feld = name if art == ABSCHNITT else None
        if art == CROP:
            ueberschrift = "Zuschneiden"
            erklaerung = (
                "Anfang oder Ende wählen, dann in die Kurve tippen oder ziehen. Grau zählt "
                "nicht — für keine Kennzahl. Die Rohdatei bleibt unverändert; praxis_gui "
                "zeigt den Zuschnitt ebenso."
            )
            knoepfe: list[ft.Control] = [
                ft.TextButton("Ganze Messung", on_click=lambda: crop_setzen(None)),
                ft.TextButton("Abbrechen", on_click=lambda: editor_schliessen()),
                ft.FilledButton("Übernehmen", icon=ft.Icons.CHECK, on_click=crop_uebernehmen),
            ]
        else:
            ueberschrift = "Abschnitt" if abschnitt is not None else "Neuer Abschnitt"
            erklaerung = (
                "Anfang oder Ende wählen, dann in die Kurve tippen oder ziehen — Notizen "
                "ziehen die Grenze an, die Stecknadel setzt sie genau auf eine."
            )
            knoepfe = [
                *(
                    [
                        ft.TextButton(
                            "Löschen",
                            icon=ft.Icons.DELETE_OUTLINE,
                            on_click=lambda: abschnitt_loeschen(abschnitt),
                        )
                    ]
                    if abschnitt is not None
                    else []
                ),
                ft.TextButton("Abbrechen", on_click=lambda: editor_schliessen()),
                ft.FilledButton("Speichern", icon=ft.Icons.CHECK, on_click=abschnitt_sichern),
            ]
        editor_box.content = ft.Container(
            border_radius=10,
            padding=ft.Padding.only(left=10, right=4, top=4, bottom=8),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.4, farbe)),
            content=ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                ueberschrift.upper(),
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                opacity=0.7,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                icon_size=18,
                                tooltip="Schließen",
                                on_click=lambda: editor_schliessen(),
                            ),
                        ],
                    ),
                    *([name] if art == ABSCHNITT else []),
                    m.editor.control,
                    ft.Text(erklaerung, size=12, opacity=0.65),
                    ft.Row(
                        spacing=4,
                        wrap=True,
                        alignment=ft.MainAxisAlignment.END,
                        controls=knoepfe,
                    ),
                ],
            ),
        )
        editor_box.visible = True
        zeichnen()

    def name_vorschlag(von: float) -> str:
        """Die Notiz an der Anfangsgrenze, sonst „Abschnitt n"."""
        notiz = next((t for x, t in notiz_punkte() if abs(x - von) < 0.5), "")
        return abschnittsname(notiz) if notiz else f"Abschnitt {len(eigene) + 1}"

    def editor_schliessen(*, zeichnen_: bool = True) -> None:
        m.editor, m.art, m.abschnitt, m.name_feld = None, "", None, None
        editor_box.visible = False
        editor_box.content = None
        if zeichnen_:
            zeichnen()

    def crop_oeffnen() -> None:
        """Zuschneiden in der Rohkurve — zeigt dafür die ganze Messung."""
        lo, hi = z.ausschnitt or (0.0, dauer)
        breite_setzen(0, zeichnen_=False)  # „Alles": beide Grenzen im Blick; der Editor zeichnet
        editor_oeffnen(CROP, lo, hi, None)

    def crop_setzen(neu: tuple[float, float] | None) -> None:
        z.ausschnitt = neu
        zusatz_sichern()
        editor_schliessen(zeichnen_=False)
        page.show_dialog(
            ft.SnackBar(
                ft.Text(
                    "Zugeschnitten — Kennzahlen nur aus diesem Bereich, die Rohdatei bleibt."
                    if neu
                    else "Wieder die ganze Messung."
                )
            )
        )
        zeichnen()

    def crop_uebernehmen() -> None:
        e = m.editor
        if e is None:
            return
        ganz = e.von <= 0.5 and e.bis >= dauer - 0.5
        crop_setzen(None if ganz or e.bis - e.von < 10 else (e.von, e.bis))

    def abschnitt_neu() -> None:
        """Neuer Abschnitt: der sichtbare Bereich, Grenzen rasten an nahen Notizen ein."""
        x_von, x_bis = fenster.bereich(dauer)
        lo, hi = grenzen()
        punkte = [x for x, _ in notiz_punkte()]
        rand = 0.1 * (x_bis - x_von)
        toleranz = max(2.0, 0.05 * (x_bis - x_von))
        von = max(einrasten(x_von + rand, punkte, toleranz), lo)
        bis = min(einrasten(x_bis - rand, punkte, toleranz), hi)
        if bis - von < 5:
            page.show_dialog(ft.SnackBar(ft.Text("Der sichtbare Bereich ist zu kurz.")))
            return
        editor_oeffnen(ABSCHNITT, von, bis, None)

    def abschnitt_bearbeiten(a: Abschnitt) -> None:
        breite_setzen(max(a.dauer_s * 1.4, 30.0), (a.von_s + a.bis_s) / 2)
        editor_oeffnen(ABSCHNITT, a.von_s, a.bis_s, a)

    def abschnitt_sichern() -> None:
        e = m.editor
        if e is None:
            return
        name = ((m.name_feld.value if m.name_feld else "") or "").strip()
        if m.abschnitt is not None:
            m.abschnitt.name = name or m.abschnitt.name
            m.abschnitt.von_s, m.abschnitt.bis_s = e.von, e.bis
        else:
            eigene.append(
                Abschnitt(name or f"Abschnitt {len(eigene) + 1}", e.von, e.bis, farbe=e.farbe)
            )
        zusatz_sichern()
        editor_schliessen()

    def zeichnen(aktualisieren: bool = True) -> None:
        kopf()
        abschnitte_zeichnen()
        kacheln_box.content = anzeige(kachel_werte(), einst.darstellung)
        analyse.aufbauen()
        kurven()
        ketten_box.controls = [ketten_zeile(i, k) for i, k in enumerate(z.ketten)] or [
            ft.Text("Keine Auffälligkeiten gefunden.", opacity=0.7)
        ]
        speichern_knopf.disabled = not z.geaendert(gespeicherte_regeln)
        if aktualisieren:
            page.update()

    def nur_kurven(mit_analyse: bool = True) -> None:
        kurven(mit_analyse)
        page.update()

    def wisch_zeichnen(mit_analyse: bool = True) -> None:
        """Beim Wischen und Ziehen: nur Rohkurve und Analyse aktualisieren, nicht die Seite.

        Wird das Band gezogen, ändert sich an der Analyse nichts — sie rechnet
        erst nach dem Loslassen.
        """
        mit_analyse = mit_analyse and aw.griff is None
        kurven(mit_analyse)
        geaendert: list[ft.Control] = [rr_box]
        if mit_analyse:
            geaendert.append(analyse.control)
            if ablese_box.visible:
                geaendert.append(ablese_box)
        for c in geaendert:
            with contextlib.suppress(Exception):
                c.update()

    # -- Zeitfenster -------------------------------------------------------------

    def breite_setzen(
        breite_s: float, mitte: float | None = None, *, zeichnen_: bool = True
    ) -> None:
        fenster.breite_s = breite_s if breite_s > 0 else (dauer or 1.0)
        if mitte is None and m.editor is not None:
            mitte = m.editor.grenze  # im Editor zoomt man auf die gewählte Grenze
        if mitte is None:
            fenster.ende_s = None if breite_s <= 0 else fenster.ende_s
        else:
            fenster.ende_s = None
            fenster.verschieben(mitte + fenster.breite_s / 2 - dauer, dauer)
        breite_wahl.selected = [str(int(breite_s))] if breite_s in dict(BREITEN) else []
        if zeichnen_:
            nur_kurven()

    def zentrieren(x: float) -> None:
        """Die Kurve auf eine Zeit rücken (Notiz antippen); bei „Alles" bleibt sie."""
        fenster.ende_s = None
        fenster.verschieben(x + fenster.breite_s / 2 - dauer, dauer)

    def zentrieren_und_zeichnen(x: float) -> None:
        """Im Editor: die Kurve zur gewählten Grenze rücken, wenn sie am Rand oder draußen liegt.

        Die Rohkurve zeichnet danach der Editor; die Verlaufskurven ziehen hier mit.
        """
        x_von, x_bis = fenster.bereich(dauer)
        if not x_von + 0.1 * (x_bis - x_von) <= x <= x_bis - 0.1 * (x_bis - x_von):
            zentrieren(x)
            analyse.zeichnen(*fenster.bereich(dauer))

    # -- Notizen ---------------------------------------------------------------

    def notizen_speichern(liste: list[dict]) -> None:
        """Als Metadaten in die Messdatei — wie praxis_gui; die Messwerte bleiben."""
        try:
            sha1 = metadaten_schreiben(pfad, ereignisse=liste)
        except (OSError, ValueError) as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Notiz nicht gespeichert: {fehler}")))
            return
        rec.ereignisse = list(liste)
        state.hrv.sha1_setzen(eintrag.id, sha1)

    def notizen_offen(offen: bool) -> None:
        state.notizen_offen = offen

    def uebungen_merken(offen: bool, quelle: str | None) -> None:
        state.notiz_uebungen_offen, state.notiz_uebungen_quelle = offen, quelle

    notizfeld = Notizfeld(
        zeitbezug=lambda: zeitbezug,
        ereignisse=lambda: list(rec.ereignisse),
        speichern=notizen_speichern,
        neu_zeichnen=nur_kurven,
        zeigen=zentrieren,
        mitte=lambda: sum(fenster.bereich(dauer)) / 2,
        offen=state.notizen_offen,
        offen_merken=notizen_offen,
        uebungen=(lambda: uebungsquellen(state)) if einst.notiz_uebungen else None,
        uebungen_offen=state.notiz_uebungen_offen,
        quelle=state.notiz_uebungen_quelle,
        uebungen_merken=uebungen_merken,
        katalog=(lambda: uebungs_katalog(state)) if einst.notiz_uebungen else None,
    )

    def breite_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            breite_setzen(float(e.control.selected[0]))

    breite_wahl.on_change = breite_gewaehlt

    # -- Analysefenster: wofür Spektrum, Poincaré und DFA gelten --------------------
    # Die ganze Messung (Vorgabe), ein Abschnitt oder ein Band fester Länge. Das Band
    # greift man in der Rohkurve und schiebt es; gerechnet wird nach dem Loslassen,
    # wenn innerhalb der Latenz (Einstellungen → Erweitert) nichts nachkommt.

    aw = _Analysewahl(
        laenge_s=einst.analyse_laenge_s if einst.analyse_laenge_s in ANALYSE_LAENGEN else 300
    )

    def band_sichtbar() -> bool:
        return aw.art == AW_BAND and analyse.bereich in ("frequenz", "nichtlinear")

    def band_bereich() -> tuple[float, float]:
        lo, hi = grenzen()
        laenge = min(float(aw.laenge_s), hi - lo)
        if aw.von is None:
            aw.von = sum(fenster.bereich(dauer)) / 2 - laenge / 2
        aw.von = min(max(aw.von, lo), hi - laenge)
        return aw.von, aw.von + laenge

    def band_reihen(x_von: float, x_bis: float) -> list[Reihe]:
        """Das Band in der Rohkurve: getönt, mit Kanten."""
        if not band_sichtbar():
            return []
        von, bis = band_bereich()
        if bis < x_von or von > x_bis:
            return []
        kanten = [x for x in (von, bis) if x_von <= x <= x_bis]
        return [
            schatten(max(von, x_von), min(bis, x_bis), ft.Colors.with_opacity(0.14, BAND_FARBE)),
            *([senkrechte(kanten, BAND_FARBE, 2.0, gestrichelt=False)] if kanten else []),
        ]

    def band_greifen(x: float) -> bool:
        """Ein Finger auf dem Band nimmt es mit; daneben blättert er die Kurve."""
        if not band_sichtbar():
            return False
        von, bis = band_bereich()
        if aw.griff is None:
            if not von <= x <= bis:
                return False
            aw.griff = x - von
            return True
        aw.von = x - aw.griff
        band_bereich()  # an die Grenzen der Messung
        return True

    def rr_losgelassen() -> None:
        if aw.griff is not None:
            aw.griff = None
            nachrechnen_planen()
            # Bis gerechnet ist: das letzte Ergebnis, blass, mit Hinweis
            analyse.zeichnen(*fenster.bereich(dauer), strich=m.strich if m.ablesen else None)
            with contextlib.suppress(Exception):
                analyse.control.update()

    def nachrechnen_planen() -> None:
        """Nach der Latenz rechnen — kommt vorher noch eine Bewegung, gilt nur die letzte."""
        aw.wartet = True
        aw.auftrag += 1
        nummer = aw.auftrag
        route = state.route_nummer  # die Ansicht verlassen → nicht mehr für sie rechnen

        async def spaeter() -> None:
            await asyncio.sleep(state.hrv_einstellungen().nachrechnen_ms / 1000)
            if nummer != aw.auftrag or route != state.route_nummer:
                return
            aw.wartet = False
            analyse.zeichnen(*fenster.bereich(dauer), strich=m.strich if m.ablesen else None)
            with contextlib.suppress(Exception):
                analyse.control.update()

        page.run_task(spaeter)

    def band_schieben(richtung: int) -> Callable[[], None]:
        def handler() -> None:
            von, bis = band_bereich()
            aw.von = von + richtung * (bis - von) / 2
            band_bereich()
            nachrechnen_planen()
            mitte = sum(band_bereich()) / 2
            x_von, x_bis = fenster.bereich(dauer)
            if not x_von <= mitte <= x_bis:
                zentrieren(mitte)
            nur_kurven()

        return handler

    def laenge_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        neu = int(e.control.value or aw.laenge_s)
        mitte = sum(band_bereich()) / 2
        aw.laenge_s = neu
        aw.von = mitte - neu / 2
        einst.analyse_laenge_s = neu
        gespeichert_ = state.hrv_einstellungen()
        gespeichert_.analyse_laenge_s = neu
        state.hrv_einstellungen_setzen(gespeichert_)
        nachrechnen_planen()
        nur_kurven()

    def art_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if not e.control.selected:
            return
        aw.art = str(e.control.selected[0])
        if aw.art == AW_ABSCHNITT and not any(a.id == aw.abschnitt_id for a in eigene):
            aw.abschnitt_id = eigene[0].id if eigene else None
        if aw.art == AW_BAND:
            aw.von = None  # mitten in den sichtbaren Ausschnitt
        nur_kurven()

    def abschnitt_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        aw.abschnitt_id = e.control.value
        nur_kurven()

    def analysefenster() -> Analysefenster:
        if aw.art == AW_ABSCHNITT:
            a = next((a for a in eigene if a.id == aw.abschnitt_id), None)
            if a is not None:
                lo, hi = grenzen()
                von, bis = max(a.von_s, lo), min(a.bis_s, hi)
                korr = z.korrigiert()
                return Analysefenster(
                    f"abschnitt:{a.id}:{von:.3f}:{bis:.3f}",
                    von,
                    bis,
                    f"Abschnitt „{a.name}“ · {_uhr(von)}–{_uhr(bis)}",
                    # wie die Abschnittswerte in der Tabelle: Nähte und langer Weg
                    ganzes=lambda: abschnitt_spektrum(korr, korr_zeiten(korr, z.achse), von, bis),
                )
        if aw.art == AW_BAND:
            von, bis = band_bereich()
            return Analysefenster(
                f"band:{von:.2f}:{bis:.2f}",
                von,
                bis,
                f"{fenster_text(round(bis - von))} · {_uhr(von)}–{_uhr(bis)}",
            )
        lo, hi = grenzen()
        return Analysefenster(
            AW_ALLES,
            lo,
            hi,
            "Ganze Messung" if z.ausschnitt is None else f"Zuschnitt {_uhr(lo)}–{_uhr(hi)}",
            ganzes=lambda: Fensterspektrum.aus_frequenzbereich(frequenz()),
        )

    def fenster_kopf() -> ft.Control:
        """Wahl des Analysefensters über Spektrum bzw. Poincaré."""
        zeilen: list[ft.Control] = [
            ft.SegmentedButton(
                selected=[aw.art],
                show_selected_icon=False,
                segments=[
                    ft.Segment(value=AW_ALLES, label=ft.Text("Alles")),
                    ft.Segment(value=AW_ABSCHNITT, label=ft.Text("Abschnitt")),
                    ft.Segment(value=AW_BAND, label=ft.Text("Fenster")),
                ],
                on_change=art_gewaehlt,
            )
        ]
        if aw.art == AW_ABSCHNITT:
            if eigene:
                zeilen.append(
                    ft.Dropdown(
                        label="Abschnitt",
                        value=aw.abschnitt_id,
                        dense=True,
                        options=[
                            ft.DropdownOption(
                                key=a.id, text=f"{a.name} · {_uhr(a.von_s)}–{_uhr(a.bis_s)}"
                            )
                            for a in eigene
                        ],
                        on_select=abschnitt_gewaehlt,
                    )
                )
            else:
                zeilen.append(hinweis("Noch keine Abschnitte — oben unter „Abschnitte“ anlegen."))
        elif aw.art == AW_BAND:
            zeilen.append(
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Dropdown(
                            label="Länge",
                            value=str(aw.laenge_s),
                            dense=True,
                            width=120,
                            options=[
                                ft.DropdownOption(key=str(x), text=fenster_text(x))
                                for x in ANALYSE_LAENGEN
                            ],
                            on_select=laenge_gewaehlt,
                        ),
                        ft.IconButton(
                            ft.Icons.CHEVRON_LEFT,
                            tooltip="Fenster ein halbes zurück",
                            on_click=band_schieben(-1),
                        ),
                        ft.IconButton(
                            ft.Icons.CHEVRON_RIGHT,
                            tooltip="Fenster ein halbes weiter",
                            on_click=band_schieben(1),
                        ),
                    ],
                )
            )
            zeilen.append(hinweis("Das Band in der Rohkurve greifen und schieben."))
        zeilen.append(ft.Text(analysefenster().titel, size=12, weight=ft.FontWeight.W_600))
        return ft.Column(spacing=6, tight=True, controls=zeilen)

    analyse = Analyse(
        page,
        state,
        bereiche=einst.bereiche(optisch=verity),
        reihe=analyse_reihe,
        hf_geraet=hf_geraet,
        ohne=lambda: [] if rec.hat_rr else ohne_rr(),
        neu_zeichnen=lambda: zeichnen(),
        wischen=lambda c: wischbar(
            c,
            fenster,
            lambda: dauer,
            wisch_zeichnen,
            tippen=analyse_tippen,
            greifen=analyse_greifen,
        ),
        tabelle=tabelle,
        optisch=verity,
        hoehe=130,
        analysefenster=analysefenster,
        fenster_kopf=fenster_kopf,
        warten=lambda: aw.griff is not None or aw.wartet,
    )

    # -- Korrektur ---------------------------------------------------------------

    def schalter(i: int) -> Callable[[], None]:
        def handler() -> None:
            z.uebernommen.symmetric_difference_update({i})
            zeichnen()

        return handler

    def hinsehen(i: int) -> Callable[[], None]:
        """Auf die Kette zoomen: eine Minute um ihre Mitte."""

        def handler() -> None:
            k = z.ketten[i]
            mitte = (z.achse[k.start] + z.achse[min(k.ende, len(z.achse) - 1)]) / 2
            breite_setzen(60, mitte)

        return handler

    def alle_uebernehmen() -> None:
        z.uebernommen.update(range(len(z.ketten)))
        zeichnen()

    def keine() -> None:
        z.uebernommen.clear()
        zeichnen()

    async def speichern() -> None:
        nonlocal gespeicherte_regeln
        try:
            analyse_speichern(pfad, rec, z.korrekturen(), regeln=z.regeln, basis=z.basis)
        except (OSError, SidecarFehler) as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Nicht gespeichert: {fehler}")))
            return
        z.gespeichert = z.korrekturen()
        gespeicherte_regeln = z.regeln
        page.show_dialog(
            ft.SnackBar(ft.Text("Korrektur gespeichert — die Rohdatei bleibt unverändert."))
        )
        zeichnen()

    speichern_knopf.on_click = speichern

    def regeln_oeffnen() -> None:
        def aendern(regeln: Korrekturregeln) -> None:
            z.regeln_setzen(regeln, analyse_laden(pfad, analysebasis(rec, regeln)))
            zeichnen()

        def merken(regeln: Korrekturregeln) -> None:
            state.korrekturregeln_setzen(regeln)
            page.show_dialog(
                ft.SnackBar(ft.Text("Als Vorgabe gemerkt — gilt für neue Aufzeichnungen und live."))
            )

        page.show_dialog(
            korrektur_blatt(
                z.regeln,
                aendern,
                erweitert=True,
                verity=verity,
                standard_merken=merken,
                schliessen=page.pop_dialog,
            )
        )

    def ketten_zeile(i: int, k: Kette) -> ft.Control:
        an = i in z.uebernommen
        t = z.achse[k.start] if k.start < len(z.achse) else 0.0
        anzahl = k.ende - k.start + 1
        was = "interpolieren" if k.art == "interpolieren" else "ausschließen"
        zusatz = []
        if k.unsicher:
            zusatz.append("unsicher")
        vom_sensor = sum(1 for j in range(k.start, k.ende + 1) if z.basis.zeile[j] is None)
        if vom_sensor:
            zusatz.append(f"Sensor verwarf {vom_sensor}")
        return ft.ListTile(
            dense=True,
            leading=ft.Icon(
                ft.Icons.CHECK_BOX if an else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                color=ft.Colors.PRIMARY if an else None,
            ),
            title=ft.Text(f"{_uhr(t)} · {anzahl} {'Schlag' if anzahl == 1 else 'Schläge'} {was}"),
            subtitle=ft.Text(" · ".join([k.grund, *zusatz]), size=12),
            trailing=ft.IconButton(
                ft.Icons.ZOOM_IN, tooltip="In der Kurve zeigen", on_click=hinsehen(i)
            ),
            on_click=schalter(i),
            content_padding=ft.Padding.only(left=0, right=0),
        )

    # -- Titel und Beschreibung (``titel``/``notiz`` der Messdatei, wie praxis_gui) --

    def titel_zeichnen() -> None:
        titel_box.content = titel_kopf(rec.titel, beschreibung, titel_bearbeiten)

    def titel_speichern(titel: str, text: str) -> None:
        nonlocal beschreibung
        if titel == rec.titel and text == (rec.notiz or ""):
            return
        try:
            sha1 = metadaten_schreiben(pfad, titel=titel, notiz=text)
        except (OSError, ValueError) as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Nicht gespeichert: {fehler}")))
            return
        rec.titel, rec.notiz, beschreibung = titel, text, text
        state.hrv.titel_setzen(eintrag.id, titel)
        state.hrv.notiz_setzen(eintrag.id, text)
        state.hrv.sha1_setzen(eintrag.id, sha1)
        titel_zeichnen()
        page.update()

    def titel_bearbeiten() -> None:
        von = eintrag.started_at
        bis = von + timedelta(seconds=eintrag.duration_s or dauer)
        plaene = geuebte_plaene(state, von, bis)
        page.show_dialog(
            titel_blatt(
                rec.titel,
                beschreibung,
                titel_vorschlaege(state, von, bis, rec.ereignisse),
                titel_speichern,
                page.pop_dialog,
                vorgabe=plaene[0] if plaene else "",
            )
        )

    titel_zeichnen()
    zeichnen(aktualisieren=False)
    return ansicht(
        [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=4),
                content=ft.Column(spacing=4, controls=[titel_box, kopf_text, hinweis_text]),
            ),
            kacheln_box,
            karte(
                kartentitel("PPI-Tachogramm" if verity else "RR-Tachogramm", ablesen_knopf),
                breite_wahl,
                wischbar(
                    rr_box,
                    fenster,
                    lambda: dauer,
                    lambda: wisch_zeichnen(mit_analyse=m.editor is None),
                    tippen=kurve_tippen,
                    greifen=kurve_greifen,
                    losgelassen=rr_losgelassen,
                ),
                ablese_box,
                editor_box,
                notizfeld.control,
                hinweis(
                    (
                        "Grau: alle Intervalle des Sensors, auch verworfene · Farbig: gewertet "
                        "(korrigiert) · Rot: auffällige Schläge"
                    )
                    if verworfen
                    else "Grau: Rohwerte · Farbig: korrigiert · Rot: auffällige Schläge"
                ),
            ),
            karte(
                kartentitel(
                    "Abschnitte",
                    ft.TextButton("Abschnitt", icon=ft.Icons.ADD, on_click=abschnitt_neu),
                    ft.PopupMenuButton(
                        icon=ft.Icons.MORE_VERT,
                        tooltip="Mehr",
                        items=[
                            ft.PopupMenuItem(
                                content="Aus Notizen …",
                                icon=ft.Icons.NOTES,
                                on_click=lambda: aus_notizen_oeffnen(),
                            ),
                            ft.PopupMenuItem(
                                content="Alle löschen",
                                icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                                on_click=lambda: alle_loeschen(),
                            ),
                        ],
                    ),
                ),
                abschnitte_box,
                hinweis(
                    "Werte je Abschnitt — so lassen sich Belastung und Pause oder Übungen "
                    "vergleichen. Antippen: Grenzen in der Kurve verschieben, umbenennen, "
                    "löschen. Notizen sind dafür nicht nötig; nahe Notizen ziehen die "
                    "Grenzen an."
                ),
            ),
            analyse.control,
            karte(
                kartentitel(
                    "Korrektur",
                    regler_knopf(regeln_oeffnen, "Was automatische Korrektur heißt"),
                    ft.TextButton("Alle", on_click=alle_uebernehmen),
                    ft.TextButton("Keine", on_click=keine),
                ),
                hinweis(
                    "Vorschläge der Automatik: kurze Ketten werden interpoliert, lange "
                    "ausgeschlossen. Antippen übernimmt oder verwirft, die Lupe zeigt die "
                    "Stelle in der Kurve."
                ),
                ketten_box,
                speichern_knopf,
            ),
            ft.Text(f"Datei: {eintrag.file_path}", size=11, opacity=0.5, selectable=True),
        ]
    )


# ---------------------------------------------------------------------------
# Zusammenfassungen der ganzen Messung
# ---------------------------------------------------------------------------


def _gesamtwert(
    kennzahl: str,
    td: dict[str, Any],
    frequenz: Callable[[], dict[str, Any] | None],
    nichtlinear: Callable[[], dict[str, Any]],
    nachkomma: int,
) -> tuple[str, str, str]:
    """``(Wert, Einheit, Zusatz)`` einer Kachel über die ganze Messung."""
    einheit = KENNZAHLEN[kennzahl].einheit
    zeit = {
        "hf_rr": "mean_bpm",
        "mean_rr": "mean_rr",
        "rmssd": "rmssd",
        "sdnn": "sdnn",
        "pnnx": "pnn50",
    }
    if kennzahl in zeit:
        return zahl(td.get(zeit[kennzahl]), nachkomma), einheit, ""
    if kennzahl in ("lf_power", "hf_power", "lf_hf", "gipfel", "vlf_power"):
        f = frequenz() or {}
        if kennzahl == "gipfel":
            g = f.get("gipfel_hz")
            return zahl(g * 60 if g else None, 1), einheit, ""
        band = {"lf_power": "lf", "hf_power": "hf", "lf_hf": "lf", "vlf_power": "vlf"}[kennzahl]
        wert = f.get(
            {"lf_power": "lf", "hf_power": "hf", "lf_hf": "lf_hf", "vlf_power": "vlf"}[kennzahl]
        )
        if wert is None and f.get("band_status", {}).get(band) not in (None, BAND_OK):
            return "gesperrt", "", _kurzgrund(f["band_reason"].get(band, ""))
        return zahl(wert, nachkomma), einheit, ""
    n = nichtlinear()
    return zahl(n.get(kennzahl), nachkomma), einheit, ""


def _kurzgrund(grund: str) -> str:
    """„kein Teilstück ≥ 5 min (…)" → „< 5 min" — passt in eine Kachel."""
    if "≥" in grund:
        return "< " + grund.split("≥", 1)[1].split("(")[0].strip()
    return grund[:24]


def _zeilen_tabelle(
    kopf: list[str], zeilen: list[tuple[str, list[str]]], hinweis_text: str = ""
) -> ft.Control:
    """Eine kleine Tabelle: erste Spalte Name, dann Werte (rechts fett)."""
    breit = len(kopf) > 1
    inhalt: list[ft.Control] = []
    if breit:
        inhalt.append(
            ft.Row(
                controls=[
                    ft.Text("", expand=2),
                    *[ft.Text(k, size=12, opacity=0.6, expand=1) for k in kopf],
                ]
            )
        )
    for name, werte in zeilen:
        inhalt.append(
            ft.Row(
                controls=[
                    ft.Text(name, expand=2),
                    *[
                        ft.Text(
                            w,
                            expand=1,
                            weight=ft.FontWeight.BOLD if i == len(werte) - 1 else None,
                        )
                        for i, w in enumerate(werte)
                    ],
                ]
            )
        )
    if hinweis_text:
        inhalt.append(hinweis(hinweis_text))
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        border_radius=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        content=ft.Column(spacing=4, tight=True, controls=inhalt),
    )


def _zeit_tabelle(
    roh: dict[str, Any] | None, korr: dict[str, Any] | None, pnn_ms: int
) -> ft.Control:
    zeilen = [
        ("Ø Herzfrequenz", "mean_bpm", "bpm", 0),
        ("Ø RR", "mean_rr", "ms", 0),
        ("RMSSD", "rmssd", "ms", 1),
        ("SDNN", "sdnn", "ms", 1),
        (f"pNN{pnn_ms}", "pnn50", "%", 1),
        ("Schläge", "n", "", 0),
    ]
    return _zeilen_tabelle(
        ["roh", "korrigiert"],
        [
            (titel_, [f"{_wert(roh, k, n)} {e}".strip(), f"{_wert(korr, k, n)} {e}".strip()])
            for titel_, k, e, n in zeilen
        ],
        "Ganze Messung. Über Nähte (Lücken, Ausschlüsse) wird keine Differenz gebildet.",
    )


def _frequenz_tabelle(f: dict[str, Any] | None) -> ft.Control:
    if f is None:
        return _zeilen_tabelle(
            [], [], "Für die Frequenzanalyse fehlen gute Schläge (mindestens 60)."
        )

    def band(key: str) -> str:
        if f.get(key) is not None:
            return f"{zahl(f[key])} ms²"
        return "gesperrt" if f["band_status"].get(key) != BAND_OK else "–"

    gipfel = f.get("gipfel_hz")
    zeilen = [
        ("ULF unter 0,003 Hz", [band("ulf")]),
        ("VLF 0,003–0,04 Hz", [band("vlf")]),
        ("LF 0,04–0,15 Hz", [band("lf")]),
        ("HF 0,15–0,40 Hz", [band("hf")]),
        ("LF/HF", [zahl(f.get("lf_hf"), 2)]),
        ("LF n.u. / HF n.u.", [f"{zahl(f.get('lf_n'))} / {zahl(f.get('hf_n'))} %"]),
        ("Gipfel", [f"{zahl(gipfel, 2)} Hz · {zahl(gipfel * 60)}/min" if gipfel else "–"]),
    ]
    gruende = [
        f"{b.upper()}: {f['band_reason'][b]}"
        for b in ("ulf", "vlf", "lf", "hf")
        if b in f["band_reason"]
    ]
    text = "Ganze Messung (korrigiert), Lomb-Scargle je lückenfreiem Teilstück."
    if f.get("strategy") == "lang":
        text += (
            " Lange Messung: LF/HF als Mittel von 5-min-Spektren, VLF von 30-min-Spektren, "
            "ULF über die ganze Länge."
        )
    if gruende:
        text += " Gesperrt — " + "; ".join(gruende) + "."
    return _zeilen_tabelle(["ganze Messung"], zeilen, text)


def _nichtlinear_tabelle(n: dict[str, Any], optisch: bool) -> ft.Control:
    zeilen = [
        ("SD1", [f"{zahl(n.get('sd1'), 1)} ms"]),
        ("SD2", [f"{zahl(n.get('sd2'), 1)} ms"]),
        ("SD1/SD2", [zahl(n.get("sd1_sd2"), 2)]),
        ("DFA α1", [zahl(n.get("dfa_alpha1"), 2)]),
        ("SampEn", [zahl(n.get("sampen"), 2)]),
    ]
    text = (
        "Ganze Messung (korrigiert). Nichtlineare Werte brauchen genaue Schlagzeiten: "
        "beim 130-Hz-EKG des H10 als Trend lesbar"
        + (", bei optischen Pulsintervallen nicht belastbar." if optisch else ".")
    )
    return _zeilen_tabelle(["ganze Messung"], zeilen, text)


class _Zustand:
    """Was die Detailansicht über die Korrektur weiß — ohne Oberfläche.

    Regeln → Analysebasis (`korrektur.analysebasis`) → Vorschläge → Auswahl.
    Ändern sich die Regeln, entsteht alles dahinter neu.
    """

    def __init__(self, rec: Recording, regeln: Korrekturregeln) -> None:
        self.rec = rec
        self.gespeichert: list[Korrektur] = []
        self.uebernommen: set[int] = set()
        #: Crop auf der Kurvenachse — ``None`` = die ganze Messung zählt
        self.ausschnitt: tuple[float, float] | None = None
        self._basis_bauen(regeln)

    def _basis_bauen(self, regeln: Korrekturregeln) -> None:
        self._korr: tuple[frozenset[int], Korrigiert] | None = None
        self._gemerkt: dict[str, tuple[Any, Any]] = {}
        self.regeln = regeln
        self.basis = analysebasis(self.rec, regeln)
        self.ketten: list[Kette] = vorschlaege(self.basis.rec, regeln)
        self._roh = anwenden(self.basis.rec, [])
        # Zeitachse: Herzuhr aller Intervalle — bei der Verity Sense samt der vom
        # Sensor verworfenen, sonst schrumpfte die Messung um deren Dauer.
        self.achse = schlagzeiten(self.basis.rec)
        self.roh_punkte, self.roh_naehte = rohfolge(self.basis.rec)

    def auswahl_aus(self, gespeichert: list[Korrektur], *, ohne_sidecar: bool) -> None:
        """Übernommen sind die gespeicherten Ketten — ohne Sidecar die Vorauswahl."""
        if ohne_sidecar and not gespeichert:
            self.uebernommen = vorauswahl(self.ketten, self.regeln.vorauswahl)
            return
        indizes = {k.beat_index for k in gespeichert}
        self.uebernommen = {
            i
            for i, k in enumerate(self.ketten)
            if any(v.beat_index in indizes for v in k.vorschlag)
        }

    def regeln_setzen(self, regeln: Korrekturregeln, gespeichert: list[Korrektur]) -> None:
        """Neue Regeln: neue Basis und Vorschläge, Auswahl nach Vorauswahl der Regeln."""
        self._basis_bauen(regeln)
        self.gespeichert = gespeichert
        self.uebernommen = vorauswahl(self.ketten, regeln.vorauswahl)

    def korrekturen(self) -> list[Korrektur]:
        return [v for i in sorted(self.uebernommen) for v in self.ketten[i].vorschlag]

    def korrigiert(self) -> Korrigiert:
        """Die korrigierte Reihe — zwischengespeichert, Wischen rechnet sie nicht neu."""
        schluessel = frozenset(self.uebernommen)
        if self._korr is None or self._korr[0] != schluessel:
            self._korr = (schluessel, anwenden(self.basis.rec, self.korrekturen()))
        return self._korr[1]

    def roh_korr(self) -> Korrigiert:
        """Die Reihe ohne jede Korrektur (nur die Nähte der Messung)."""
        return self._roh

    def analyse_korr(self, roh: bool = False) -> Korrigiert:
        """Die Reihe für Kennzahlen — bei Crop nur dessen Ausschnitt (`zuschneiden`)."""
        korr = self.roh_korr() if roh else self.korrigiert()
        if self.ausschnitt is None:
            return korr
        return zuschneiden(korr, korr_zeiten(korr, self.achse), *self.ausschnitt)

    def merken(self, name: str, rechnen: Callable[[], Any]) -> Any:
        """Ergebnis zu Auswahl und Crop — Spektrum und DFA nur bei Änderungen neu."""
        schluessel = (frozenset(self.uebernommen), self.ausschnitt)
        alt = self._gemerkt.get(name)
        if alt is None or alt[0] != schluessel:
            self._gemerkt[name] = (schluessel, rechnen())
        return self._gemerkt[name][1]

    def geaendert(self, gespeicherte_regeln: Korrekturregeln | None) -> bool:
        """Weicht die Auswahl oder die Regel vom Gespeicherten ab?"""

        def schluessel(ks: list[Korrektur]) -> list[tuple[str, int, int]]:
            return sorted((k.op, k.beat_index, k.span()[1]) for k in ks)

        if gespeicherte_regeln is not None and gespeicherte_regeln != self.regeln:
            return True
        return schluessel(self.korrekturen()) != schluessel(self.gespeichert)


__all__ = ["messung_detail_view"]
