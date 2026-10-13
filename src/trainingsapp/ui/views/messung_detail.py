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
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

import flet as ft

from trainingsapp.config import datenverzeichnis, messungenverzeichnis
from trainingsapp.core.models import HrvRecording
from trainingsapp.hrv_core.export import export_zip, zugehoerige_dateien
from trainingsapp.hrv_core.korrektur import (
    Kette,
    Korrektur,
    Korrigiert,
    analyse_laden,
    analyse_regeln,
    analyse_speichern,
    analysebasis,
    anwenden,
    kennzahlen,
    korr_zeiten,
    rohfolge,
    vorauswahl,
    vorschlaege,
)
from trainingsapp.hrv_core.ppi import ppi_verworfen, schlagzeiten
from trainingsapp.hrv_core.recording import Recording, laden
from trainingsapp.hrv_core.regeln import Korrekturregeln
from trainingsapp.hrv_core.trends import KENNZAHLEN, reihe, verlauf
from trainingsapp.ui.components.korrektur_blatt import korrektur_blatt, regler_knopf
from trainingsapp.ui.components.kurve import RR_SPANNE_MIN_MS, Reihe, kurve
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.verlauf import ansicht_menue, chips, diagramme
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.components.zeitfenster import Fenster, wischbar
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
    verworfen = ppi_verworfen(rec)
    verity = rec.ppi_pakete is not None

    # -- Zustand: Regeln → Basis → Vorschläge → Auswahl -------------------------
    # Regeln der gespeicherten Korrektur, sonst die gerätelokale Vorgabe.
    # Optische Intervalle streuen mehr: Malik „nach Sensor" = 0.30 (Vertrag, Abschnitt 5).
    gespeicherte_regeln = analyse_regeln(pfad)
    z = _Zustand(rec, gespeicherte_regeln or state.korrekturregeln())
    z.gespeichert = analyse_laden(pfad, z.basis)
    z.auswahl_aus(z.gespeichert, ohne_sidecar=gespeicherte_regeln is None)

    dauer = max((t for t, _ in z.roh_punkte), default=0.0)
    fenster = Fenster(dauer or 1.0, None)

    kopf_text = ft.Text(size=13, opacity=0.8)
    hinweis_text = ft.Text(size=12, color=ROT)
    kennzahlen_box = ft.Container()
    rr_box = ft.Container()
    verlauf_box = ft.Column(spacing=4)
    chips_box = ft.Container()
    ketten_box = ft.Column(spacing=0)
    breite_wahl = ft.SegmentedButton(
        selected=["0"],
        segments=[ft.Segment(value=str(s), label=ft.Text(t)) for s, t in BREITEN],
    )
    speichern_knopf = ft.FilledButton("Korrektur speichern", icon=ft.Icons.SAVE, disabled=True)

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
                            ft.Text(f"{_wert(z.roh, key, n)} {einheit}", expand=1),
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
            ],
            einheit="PPI ms" if verity else "RR ms",
            hoehe=220,
            x_von=x_von,
            x_bis=x_bis,
            y_spanne_min=RR_SPANNE_MIN_MS,
        )
        t, werte, naht = reihe(zeiten, korr.rr_ms, korr.breaks)
        hf_punkte = [(x, float(b.hf_bpm)) for x, b in zip(z.achse, beats, strict=True) if b.hf_bpm]

        def daten(kennzahl: str, fenster_s: int) -> list[tuple[float, float]]:
            if kennzahl == "hf_geraet":
                return [(x, h) for x, h in hf_punkte if x_von <= x <= x_bis]
            return verlauf(t, werte, naht, kennzahl, fenster_s, von=x_von, bis=x_bis)

        ohne = [] if rec.hat_rr else [k for k in KENNZAHLEN if k != "hf_geraet"]
        verlauf_box.controls = diagramme(
            state.ansicht(), daten, x_von=x_von, x_bis=x_bis, hoehe=130, ohne=ohne
        )

    def zeichnen(aktualisieren: bool = True) -> None:
        kopf()
        kennzahlen_box.content = tabelle(kennzahlen(z.korrigiert()))
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

    def breite_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            breite_setzen(float(e.control.selected[0]))

    breite_wahl.on_change = breite_gewaehlt

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
        )

    # -- Verlaufskurven ------------------------------------------------------------

    def kurve_umschalten(kennzahl: str) -> None:
        a = state.ansicht()
        a.umschalten(kennzahl)
        state.ansicht_setzen(a)
        ansicht_neu()

    def ansicht_neu() -> None:
        chips_box.content = verlauf_kopf()
        nur_kurven()

    def verlauf_kopf() -> ft.Control:
        return ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(expand=True, content=chips(state.ansicht(), kurve_umschalten)),
                ansicht_menue(page, state, ansicht_neu),
            ],
        )

    async def notiz_speichern(e: ft.Event[ft.TextField]) -> None:
        state.hrv.notiz_setzen(eintrag.id, e.control.value or "")

    chips_box.content = verlauf_kopf()
    zeichnen(aktualisieren=False)
    return ansicht(
        [
            kopf_text,
            hinweis_text,
            kennzahlen_box,
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(
                        "PPI-TACHOGRAMM" if verity else "RR-TACHOGRAMM",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        opacity=0.6,
                    ),
                ],
            ),
            breite_wahl,
            wischbar(
                ft.Column(spacing=8, controls=[rr_box, verlauf_box]),
                fenster,
                lambda: dauer,
                nur_kurven,
            ),
            chips_box,
            ft.Text(
                (
                    "Grau: alle Intervalle des Sensors, auch verworfene · Farbig: gewertet "
                    "(korrigiert) · Rot: auffällige Schläge"
                )
                if verworfen
                else "Grau: Rohwerte · Farbig: korrigiert · Rot: auffällige Schläge",
                size=11,
                opacity=0.55,
            ),
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row(
                        spacing=0,
                        controls=[
                            ft.Text("KORREKTUR", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                            regler_knopf(regeln_oeffnen, "Was automatische Korrektur heißt"),
                        ],
                    ),
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
                "ausgeschlossen. Antippen übernimmt oder verwirft, die Lupe zeigt die "
                "Stelle in der Kurve.",
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
        self.regeln = regeln
        self.basis = analysebasis(self.rec, regeln)
        self.ketten: list[Kette] = vorschlaege(self.basis.rec, regeln)
        self.roh = kennzahlen(anwenden(self.basis.rec, []))
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

    def geaendert(self, gespeicherte_regeln: Korrekturregeln | None) -> bool:
        """Weicht die Auswahl oder die Regel vom Gespeicherten ab?"""

        def schluessel(ks: list[Korrektur]) -> list[tuple[str, int, int]]:
            return sorted((k.op, k.beat_index, k.span()[1]) for k in ks)

        if gespeicherte_regeln is not None and gespeicherte_regeln != self.regeln:
            return True
        return schluessel(self.korrekturen()) != schluessel(self.gespeichert)


__all__ = ["messung_detail_view"]
