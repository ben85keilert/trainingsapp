"""Eine Aufzeichnung — Route `/messung/<id>`: ansehen und korrigieren.

Die Rohdatei bleibt unangetastet. Korrekturen sind Vorschläge der Automatik
(`hrv_core.korrektur.automatisch`) als Ketten; was übernommen wird, landet in
`sensor_<ts>_analyzed.json` neben der Rohdatei — dieselbe Teilmenge von
`analysis-v1`, die praxis_gui liest.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from trainingsapp.config import datenverzeichnis, messungenverzeichnis
from trainingsapp.core.models import HrvRecording
from trainingsapp.hrv_core.constants import malik_threshold
from trainingsapp.hrv_core.export import export_zip, zugehoerige_dateien
from trainingsapp.hrv_core.korrektur import (
    Kette,
    Korrektur,
    analyse_laden,
    analyse_speichern,
    anwenden,
    automatisch,
    kennzahlen,
)
from trainingsapp.hrv_core.recording import laden
from trainingsapp.ui.components.kurve import Reihe, kurve
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.state import AppState

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
    return f"{d[key]:.{nachkomma}f}"


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
            padding=16,
            controls=[sicher(ft.Column(spacing=14, controls=inhalt), expand=False)],
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
    # Optische Intervalle (Verity Sense) streuen mehr: 0.30 statt 0.20 (Vertrag, Abschnitt 5).
    malik = malik_threshold(rec.intervall_quelle)
    ketten: list[Kette] = automatisch(rec, malik=malik)
    gespeichert = analyse_laden(pfad)
    gespeicherte_indizes = {k.beat_index for k in gespeichert}
    uebernommen: set[int] = {
        i
        for i, k in enumerate(ketten)
        if any(v.beat_index in gespeicherte_indizes for v in k.vorschlag)
    }
    roh = kennzahlen(anwenden(rec, []))

    kennzahlen_box = ft.Container()
    rr_box = ft.Container()
    ketten_box = ft.Column(spacing=0)
    speichern_knopf = ft.FilledButton("Korrektur speichern", icon=ft.Icons.SAVE, disabled=True)

    def korrekturen() -> list[Korrektur]:
        return [v for i in sorted(uebernommen) for v in ketten[i].vorschlag]

    def tabelle(korr_werte: dict | None) -> ft.Control:
        zeilen = [
            ("Ø Herzfrequenz", "mean_bpm", "bpm", 0),
            ("RMSSD", "rmssd", "ms", 1),
            ("SDNN", "sdnn", "ms", 1),
            ("pNN50", "pnn50", "%", 1),
            ("Schläge", "n", "", 0),
        ]
        return ft.Column(
            spacing=2,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("", expand=2),
                        ft.Text("roh", size=12, opacity=0.6, expand=1),
                        ft.Text("korrigiert", size=12, opacity=0.6, expand=1),
                    ]
                ),
                *[
                    ft.Row(
                        controls=[
                            ft.Text(titel, expand=2),
                            ft.Text(f"{_wert(roh, key, n)} {einheit}", expand=1),
                            ft.Text(
                                f"{_wert(korr_werte, key, n)} {einheit}",
                                expand=1,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ]
                    )
                    for titel, key, einheit, n in zeilen
                ],
            ],
        )

    def zeichnen(aktualisieren: bool = True) -> None:
        korr = anwenden(rec, korrekturen())
        kennzahlen_box.content = tabelle(kennzahlen(korr))
        roh_punkte = [(b.t_s, float(b.rr_ms)) for b in rec.beats if b.rr_ms]
        markiert = {v.beat_index for k in ketten for v in k.vorschlag}
        art = [
            (rec.beats[i].t_s, float(rec.beats[i].rr_ms))
            for i in sorted(markiert)
            if i < len(rec.beats) and 0 < rec.beats[i].rr_ms < 2600
        ]
        sichtbar = [p for p in roh_punkte if 200 < p[1] < 2600]
        rr_box.content = kurve(
            [
                Reihe(sichtbar, farbe=ft.Colors.OUTLINE, breite=1),
                Reihe(
                    [(t, r) for t, r in zip(korr.t_s, korr.rr_ms, strict=True) if r > 0],
                    farbe=ft.Colors.PRIMARY,
                ),
                Reihe(art, farbe=ROT, nur_punkte=True),
            ],
            einheit="RR ms",
            hoehe=220,
        )
        ketten_box.controls = [ketten_zeile(i, k) for i, k in enumerate(ketten)] or [
            ft.Text("Keine Auffälligkeiten gefunden.", opacity=0.7)
        ]
        speichern_knopf.disabled = sorted(korrekturen(), key=lambda k: k.beat_index) == sorted(
            gespeichert, key=lambda k: k.beat_index
        )
        if aktualisieren:
            page.update()

    def schalter(i: int) -> Callable[[], None]:
        def handler() -> None:
            uebernommen.symmetric_difference_update({i})
            zeichnen()

        return handler

    def alle_uebernehmen() -> None:
        uebernommen.update(range(len(ketten)))
        zeichnen()

    def keine() -> None:
        uebernommen.clear()
        zeichnen()

    async def speichern() -> None:
        analyse_speichern(pfad, rec, korrekturen(), malik=malik)
        gespeichert[:] = korrekturen()
        page.show_dialog(
            ft.SnackBar(ft.Text("Korrektur gespeichert — die Rohdatei bleibt unverändert."))
        )
        zeichnen()

    speichern_knopf.on_click = speichern

    def ketten_zeile(i: int, k: Kette) -> ft.Control:
        an = i in uebernommen
        t = rec.beats[k.start].t_s if k.start < len(rec.beats) else 0.0
        anzahl = k.ende - k.start + 1
        was = "interpolieren" if k.art == "interpolieren" else "ausschließen"
        return ft.ListTile(
            dense=True,
            leading=ft.Icon(
                ft.Icons.CHECK_BOX if an else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                color=ft.Colors.PRIMARY if an else None,
            ),
            title=ft.Text(f"{_uhr(t)} · {anzahl} {'Schlag' if anzahl == 1 else 'Schläge'} {was}"),
            subtitle=ft.Text(k.grund + (" · unsicher" if k.unsicher else ""), size=12),
            on_click=schalter(i),
        )

    async def notiz_speichern(e: ft.Event[ft.TextField]) -> None:
        state.hrv.notiz_setzen(eintrag.id, e.control.value or "")

    hf_punkte = [(b.t_s, float(b.hf_bpm)) for b in rec.beats if b.hf_bpm]
    kopf = [
        rec.geraet or eintrag.geraet,
        _uhr(rec.dauer_s),
        QUALITAET.get(rec.effektive_qualitaet(), rec.effektive_qualitaet()),
    ]
    zeichnen(aktualisieren=False)
    return ansicht(
        [
            ft.Text("  ·  ".join(t for t in kopf if t), size=13, opacity=0.8),
            kennzahlen_box,
            ft.Text("RR-TACHOGRAMM", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            rr_box,
            ft.Text(
                "Grau: Rohwerte · Farbig: korrigiert · Rot: auffällige Schläge",
                size=11,
                opacity=0.55,
            ),
            ft.Text("HERZFREQUENZ", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            kurve([Reihe(hf_punkte, farbe=ft.Colors.TERTIARY)], einheit="HF bpm", hoehe=140),
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text("KORREKTUR", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                    ft.Row(
                        spacing=0,
                        controls=[
                            ft.TextButton("Alle", on_click=alle_uebernehmen),
                            ft.TextButton("Keine", on_click=keine),
                        ],
                    ),
                ],
            ),
            ft.Text(
                "Vorschläge der Automatik: kurze Ketten werden interpoliert, lange "
                "ausgeschlossen. Antippen übernimmt oder verwirft.",
                size=12,
                opacity=0.7,
            ),
            ketten_box,
            speichern_knopf,
            ft.TextField(
                label="Notiz",
                value=eintrag.note,
                multiline=True,
                min_lines=1,
                max_lines=5,
                hint_text="z. B. Atemübung 6/min, Liegestütz",
                on_blur=notiz_speichern,
            ),
            ft.Text(f"Datei: {eintrag.file_path}", size=11, opacity=0.5, selectable=True),
        ]
    )


__all__ = ["messung_detail_view"]
