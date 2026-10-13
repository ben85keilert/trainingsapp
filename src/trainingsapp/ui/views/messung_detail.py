"""Eine Aufzeichnung — Route `/messung/<id>`: ansehen und korrigieren.

Die Rohdatei bleibt unangetastet. Korrekturen sind Vorschläge der Automatik
(`hrv_core.korrektur.vorschlaege`) als Ketten; was übernommen wird, landet in
`sensor_<ts>_analyzed.json` neben der Rohdatei — dieselbe Teilmenge von
`analysis-v1`, die praxis_gui liest, samt den Regeln, mit denen sie entstand.

Was „automatisch" heißt, stellt das Regler-Symbol neben „Korrektur" ein
(`Korrekturregeln`) — je Messung, auf Wunsch als Vorgabe gemerkt. Bei der
Verity Sense prüft das Programm die vom Sensor verworfenen Intervalle
standardmäßig selbst (`korrektur.analysebasis`).

Alle Kurven teilen ein Zeitfenster (Breite wählen, waagrecht wischen); die
Lupe an einer Kette zoomt auf ihre Stelle.

Aufbau wie live: Kacheln (Werte der ganzen Messung, korrigiert), Hauptkurve,
darunter die Analyse (Zeit ↔ Frequenz ↔ Nichtlinear) mit einer Zusammenfassung
der ganzen Messung je Bereich — Zeitbereich roh und korrigiert, Frequenzbänder
mit Sperrgrund (Task-Force-Mindestdauer), Poincaré, DFA α1 und SampEn.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from typing import Any

import flet as ft
import numpy as np

from trainingsapp.config import datenverzeichnis, messungenverzeichnis
from trainingsapp.core.models import HrvRecording
from trainingsapp.hrv_core.atmung import ATEMUEBUNG, RUHE, atemfrequenz, kurzgrund
from trainingsapp.hrv_core.constants import BAND_OK
from trainingsapp.hrv_core.ereignisse import Zeitbezug, metadaten_schreiben
from trainingsapp.hrv_core.export import export_zip, zugehoerige_dateien
from trainingsapp.hrv_core.frequency import frequenzbereich
from trainingsapp.hrv_core.korrektur import (
    Kette,
    Korrektur,
    Korrigiert,
    analyse_laden,
    analyse_regeln,
    analyse_speichern,
    analysebasis,
    anwenden,
    korr_zeiten,
    rohfolge,
    vorauswahl,
    vorschlaege,
)
from trainingsapp.hrv_core.nonlinear import compute_dfa_alpha1, compute_poincare, compute_sampen
from trainingsapp.hrv_core.ppi import ppi_verworfen, schlagzeiten
from trainingsapp.hrv_core.recording import Recording, laden
from trainingsapp.hrv_core.regeln import Korrekturregeln
from trainingsapp.hrv_core.segments import filter_rr
from trainingsapp.hrv_core.time_domain import compute_time_domain
from trainingsapp.hrv_core.trends import DFA_MIN_SCHLAEGE, KENNZAHLEN, reihe, titel
from trainingsapp.ui.components.analyse import Analyse
from trainingsapp.ui.components.kacheln import KACHELN, KachelWert, anzeige, zahl
from trainingsapp.ui.components.karte import hinweis, karte
from trainingsapp.ui.components.karte import titel as kartentitel
from trainingsapp.ui.components.korrektur_blatt import korrektur_blatt, regler_knopf
from trainingsapp.ui.components.kurve import RR_SPANNE_MIN_MS, Reihe, kurve
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.notizen import Notizfeld, uebungs_katalog, uebungsquellen
from trainingsapp.ui.components.verlauf import FARBEN
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.components.zeitfenster import Fenster, wischbar
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.messung import ohne_rr

ROT = ft.Colors.RED_400
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
    fenster = Fenster(dauer or 1.0, None)
    # Notizen hängen an den Zeilen der Rohdatei; die Kurve hat ihre eigene Zeitachse
    zeilen_achse = schlagzeiten(rec)

    kopf_text = ft.Text(size=13, opacity=0.8)
    hinweis_text = ft.Text(size=12, color=ROT)
    kacheln_box = ft.Container()
    rr_box = ft.Container()
    ketten_box = ft.Column(spacing=0)
    breite_wahl = ft.SegmentedButton(
        selected=["0"],
        show_selected_icon=False,
        segments=[ft.Segment(value=str(s), label=ft.Text(t)) for s, t in BREITEN],
    )
    speichern_knopf = ft.FilledButton("Korrektur speichern", icon=ft.Icons.SAVE, disabled=True)

    # -- Kennzahlen der ganzen Messung (korrigiert) --------------------------------

    def zeitbereich(korrigiert: bool) -> dict[str, Any] | None:
        """Ø HF, Ø RR, RMSSD, SDNN, pNNx — roh oder korrigiert, Nähte übersprungen."""
        korr = z.korrigiert() if korrigiert else z.roh_korr()
        return compute_time_domain(
            korr.rr_ms, pnn_threshold_ms=state.ansicht().pnn_ms, breaks=korr.breaks
        )

    def frequenz() -> dict[str, Any] | None:
        korr = z.korrigiert()
        return z.merken("frequenz", lambda: frequenzbereich(korr.rr_ms, korr.t_s, korr.breaks))

    def nichtlinear() -> dict[str, Any]:
        def rechnen() -> dict[str, Any]:
            korr = z.korrigiert()
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
        kopf_text.value = "  ·  ".join(t for t in teile if t)
        # Mehr als die Hälfte verworfen: Folgt man dem Sensor, bleiben Bruchstücke.
        viel = bool(verworfen and verworfen[1] and verworfen[0] * 2 > verworfen[1])
        hinweis_text.visible = viel
        hinweis_text.value = (
            "Der Sensor hat die meisten Intervalle verworfen — meist Bewegung oder ein "
            "lockerer Sitz. Sie sind wieder aufgenommen und nach den eigenen Regeln "
            "geprüft; was nicht passt, steht unten in der Korrektur."
            if z.basis.aufgenommen
            else "Der Sensor hat die meisten Intervalle verworfen — meist Bewegung "
            "oder ein lockerer Sitz. Die Kennzahlen beruhen auf Bruchstücken; für "
            "HRV ruhig sitzen bzw. liegen und den Sensor fest anlegen."
        )

    def analyse_reihe() -> tuple[Any, Any, Any]:
        korr = z.korrigiert()
        return z.merken("reihe", lambda: reihe(korr_zeiten(korr, z.achse), korr.rr_ms, korr.breaks))

    def hf_geraet() -> list[tuple[float, float]]:
        beats = z.basis.rec.beats
        return [(x, float(b.hf_bpm)) for x, b in zip(z.achse, beats, strict=True) if b.hf_bpm]

    def kurven() -> None:
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
        zeiten = korr_zeiten(korr, z.achse)
        korr_linie, korr_naehte = _linie(
            zip(zeiten, korr.rr_ms, strict=True), korr.breaks, x_von=x_von, x_bis=x_bis
        )
        rr_box.content = kurve(
            [
                Reihe(
                    sichtbar,
                    farbe=ft.Colors.OUTLINE,
                    breite=1,
                    naehte=sichtbar_naehte,
                    skala=False,
                ),
                Reihe(korr_linie, farbe=ft.Colors.PRIMARY, naehte=korr_naehte),
                Reihe(art, farbe=ROT, nur_punkte=True, skala=False),
                *notizfeld.marken(x_von, x_bis),
            ],
            einheit="PPI ms" if verity else "RR ms",
            hoehe=220,
            x_von=x_von,
            x_bis=x_bis,
            y_spanne_min=RR_SPANNE_MIN_MS,
        )
        analyse.zeichnen(x_von, x_bis)

    def zeichnen(aktualisieren: bool = True) -> None:
        kopf()
        kacheln_box.content = anzeige(kachel_werte(), einst.darstellung)
        analyse.aufbauen()
        kurven()
        ketten_box.controls = [ketten_zeile(i, k) for i, k in enumerate(z.ketten)] or [
            ft.Text("Keine Auffälligkeiten gefunden.", opacity=0.7)
        ]
        speichern_knopf.disabled = not z.geaendert(gespeicherte_regeln)
        if aktualisieren:
            page.update()

    def nur_kurven() -> None:
        kurven()
        page.update()

    # -- Zeitfenster -------------------------------------------------------------

    def breite_setzen(breite_s: float, mitte: float | None = None) -> None:
        fenster.breite_s = breite_s if breite_s > 0 else (dauer or 1.0)
        if mitte is None:
            fenster.ende_s = None if breite_s <= 0 else fenster.ende_s
        else:
            fenster.ende_s = None
            fenster.verschieben(mitte + fenster.breite_s / 2 - dauer, dauer)
        breite_wahl.selected = [str(int(breite_s))] if breite_s in dict(BREITEN) else []
        nur_kurven()

    def zentrieren(x: float) -> None:
        """Die Kurve auf eine Zeit rücken (Notiz antippen); bei „Alles" bleibt sie."""
        fenster.ende_s = None
        fenster.verschieben(x + fenster.breite_s / 2 - dauer, dauer)

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
        zeitbezug=lambda: Zeitbezug(lambda: rec.beats, rec.start_utc, achse=lambda: zeilen_achse),
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

    analyse = Analyse(
        page,
        state,
        bereiche=einst.bereiche(optisch=verity),
        reihe=analyse_reihe,
        hf_geraet=hf_geraet,
        ohne=lambda: [] if rec.hat_rr else ohne_rr(),
        neu_zeichnen=lambda: zeichnen(),
        wischen=lambda c: wischbar(c, fenster, lambda: dauer, nur_kurven),
        tabelle=tabelle,
        optisch=verity,
        hoehe=130,
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
        analyse_speichern(pfad, rec, z.korrekturen(), regeln=z.regeln, basis=z.basis)
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

    async def notiz_speichern(e: ft.Event[ft.TextField]) -> None:
        """Allgemeine Notiz: Datenbank (Liste) und ``notiz`` der Messdatei (praxis_gui)."""
        text = (e.control.value or "").strip()
        state.hrv.notiz_setzen(eintrag.id, text)
        if text != (rec.notiz or "").strip():
            try:
                state.hrv.sha1_setzen(eintrag.id, metadaten_schreiben(pfad, notiz=text))
                rec.notiz = text
            except (OSError, ValueError):
                pass

    zeichnen(aktualisieren=False)
    return ansicht(
        [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=4),
                content=ft.Column(spacing=4, controls=[kopf_text, hinweis_text]),
            ),
            kacheln_box,
            karte(
                kartentitel("PPI-Tachogramm" if verity else "RR-Tachogramm"),
                breite_wahl,
                wischbar(rr_box, fenster, lambda: dauer, nur_kurven, tippen=notizfeld.tippen),
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
            karte(
                kartentitel("Notiz zur Messung"),
                ft.TextField(
                    value=eintrag.note or rec.notiz,
                    multiline=True,
                    min_lines=1,
                    max_lines=5,
                    hint_text="z. B. Atemübung 6/min, Liegestütz",
                    on_blur=notiz_speichern,
                ),
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
        self._basis_bauen(regeln)

    def _basis_bauen(self, regeln: Korrekturregeln) -> None:
        self._korr: tuple[frozenset[int], Korrigiert] | None = None
        self._gemerkt: dict[str, tuple[frozenset[int], Any]] = {}
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

    def merken(self, name: str, rechnen: Callable[[], Any]) -> Any:
        """Ergebnis zur aktuellen Auswahl — Spektrum und DFA nur bei Änderungen neu."""
        schluessel = frozenset(self.uebernommen)
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
