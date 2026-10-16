"""Ausdauertraining mit GPS — Route `/ausdauer` (live) und `/ausdauer/<id>` (Auswertung).

Gehen, Laufen, Rad (Ben, 14.10.2026: in dieser Reihenfolge) — mit oder ohne
GPS (Laufband, Halle), mit oder ohne Gurt. Gerechnet wird in
`core.strecke.StreckenRechner` (10-m-Schritt, Auto-Pause, Splits), die HRV je
Kilometer in `core.hrv_training`. Diese Ansicht verbindet nur:

- **GPS jede Sekunde** (`GPS_TAKT_S`) — der Vorabtest zeigte keinen
  messbaren Stromvorteil für seltener, aber eine schlechtere Genauigkeit.
- Ist ein Gurt verbunden, läuft die **HRV-Aufnahme** mit; an jedem Kilometer
  ein Ton, eine Vibration und die Notiz „km 3", die beim Speichern eine
  Abschnittsgrenze wird. Die Notiz trägt **nie einen Ort**.
- Beim Beenden: Strecke (Datei unter ``Strecken/``, Zeile `strecke`),
  HRV-Aufnahme (wie sonst unter ``Messungen/``) und ein **Tagebucheintrag**
  der Übung „Gehen"/„Laufen"/„Radfahren" mit Strecke und Zeit.

**GPS-Daten werden nie geteilt** (`docs/plan_gps.md`, Abschnitt 0): Die
Ortungen bleiben in ``Strecken/``; hinaus gehen sie nur über „GPX
exportieren", das die Person selbst antippt. HRV-Datei, Notizen,
Tagebucheintrag und Benachrichtigung bleiben ortsfrei.

**DFA α1 ohne Empfehlung** (Abschnitt 6): Verlauf, Zeit je Wertebereich und
Werte je Kilometer, neutral beschriftet — nur mit EKG-Gurt; keine Zonen.

Der Lauf (`AusdauerLauf`) lebt im `AppState` und übersteht Ansichtswechsel;
bei ausgeschaltetem Display hält ihn der Vordergrunddienst (Typ ``location``).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import flet as ft
from hrv_core.korrektur import (
    Korrigiert,
    analyse_laden,
    analyse_regeln,
    analysebasis,
    anwenden,
    korr_zeiten,
    vorauswahl,
    vorschlaege,
)
from hrv_core.ppi import schlagzeiten
from hrv_core.recording import Recording, laden
from hrv_core.trends import aktuell, reihe

from trainingsapp.config import datenverzeichnis, messungenverzeichnis, streckenverzeichnis
from trainingsapp.core.hrv_training import (
    dfa_verlauf,
    hf_je_zeit,
    werte_zwischen,
    zeit_je_bereich,
)
from trainingsapp.core.models import Exercise, Strecke, lokaler_tag
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld
from trainingsapp.core.strecke import (
    GEHEN,
    LAUFEN,
    RAD,
    SPORT_NAMEN,
    SPORTARTEN,
    Punkt,
    Split,
    StreckenRechner,
    rechnen,
    split_laenge_m,
)
from trainingsapp.data.repositories import SettingRepo
from trainingsapp.data.seed import seed_id
from trainingsapp.data.strecken import StreckenSchreiber, dateiname, gpx, jsonl_lesen, kopf_lesen
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.gps import GpsQuelle
from trainingsapp.ui.ausrichtung import querformat
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.karte_strecke import StreckenKarte, ganze_strecke
from trainingsapp.ui.components.kurve import Reihe, kurve
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.state import AppState

#: Ben, 14.10.2026: GPS im Sekundentakt — seltener sparte im Test keinen messbaren Strom
GPS_TAKT_S = 1.0
#: Benachrichtigung und Live-DFA so oft auffrischen (s)
TEXT_ALLE_S = 5.0
#: Zweck im gemeinsamen Vordergrunddienst — Typ ``location``
ZWECK = "gps"

SPORT_SYMBOLE = {
    GEHEN: ft.Icons.DIRECTIONS_WALK,
    LAUFEN: ft.Icons.DIRECTIONS_RUN,
    RAD: ft.Icons.DIRECTIONS_BIKE,
}


# ---------------------------------------------------------------------------
# Schreibweisen (ortsfrei)
# ---------------------------------------------------------------------------


def km_text(meter: float) -> str:
    """>>> km_text(5212.4), km_text(820)
    ('5,21 km', '0,82 km')
    """
    return f"{meter / 1000:.2f} km".replace(".", ",")


def zeit_text(sekunden: float) -> str:
    """>>> zeit_text(1930), zeit_text(3725)
    ('32:10', '1:02:05')
    """
    s = max(0, round(sekunden))
    h, rest = divmod(s, 3600)
    return f"{h}:{rest // 60:02d}:{rest % 60:02d}" if h else f"{rest // 60}:{rest % 60:02d}"


def tempo_text(sportart: str, s_pro_km: float | None) -> str:
    """Gehen und Laufen als min/km, Rad als km/h.

    >>> tempo_text(LAUFEN, 312), tempo_text(RAD, 150), tempo_text(GEHEN, None)
    ('5:12 /km', '24,0 km/h', '–')
    """
    if s_pro_km is None or s_pro_km <= 0:
        return "–"
    if sportart == RAD:
        return f"{3600 / s_pro_km:.1f} km/h".replace(".", ",")
    return f"{zeit_text(s_pro_km)} /km"


def _zahl(x: float | None, stellen: int = 0) -> str:
    if x is None:
        return "–"
    return f"{x:.{stellen}f}".replace(".", ",")


# ---------------------------------------------------------------------------
# Übung im Tagebuch
# ---------------------------------------------------------------------------


def uebung_fuer(state: AppState, sportart: str) -> Exercise:
    """Die Übung „Gehen"/„Laufen"/„Radfahren" — beim ersten Training angelegt.

    Feste ID je Sportart (wie mitgelieferte Übungen), damit alle Trainings
    einer Sportart im Verlauf zusammenstehen. Felder: Strecke und Zeit.
    """
    uid = seed_id(f"ausdauer_{sportart}")
    vorhanden = state.uebungen.laden(uid, mit_geloeschten=True)
    if vorhanden is not None:
        return vorhanden
    felder = [f for f in (vorrat_feld("distance"), vorrat_feld("duration")) if f is not None]
    uebung = Exercise(
        id=uid,
        name=SPORT_NAMEN[sportart],
        description="Ausdauer — mit GPS oder ohne aufgezeichnet (Reiter „Messung“, „Ausdauer“).",
        result_spec=ResultSpec(layout=Layout.SINGLE, fields=felder),
        typen=["Ausdauer"],
        default_felder=["distance", "duration"],
    )
    state.uebungen.speichern(uebung)
    return uebung


# ---------------------------------------------------------------------------
# Der Lauf
# ---------------------------------------------------------------------------


class AusdauerLauf:
    """Ein laufendes Training: GPS, Rechner, Datei, HRV-Aufnahme und Benachrichtigung."""

    def __init__(self, state: AppState, sportart: str, quelle: GpsQuelle | None) -> None:
        self.state = state
        #: Profil beim Start — ein Wechsel während des Trainings hängt nichts um
        self.subject_id = state.profil.id
        self.sportart = sportart
        self.quelle = quelle
        self.rechner = StreckenRechner(split_m=split_laenge_m(sportart))
        self.start_utc = datetime.now(UTC)
        self._start_mono = time.monotonic()
        self.datei: StreckenSchreiber | None = None
        #: Pfad der Streckendatei — bleibt, auch wenn das Schreiben scheitert
        self.datei_pfad: Path | None = None
        #: Was die Person wissen muss, während es läuft (GPS weg, Dienst fehlt, Datei voll)
        self.warnung: str | None = None
        self.messlauf = state.messlauf if _verbunden(state) else None
        #: Die HRV-Aufnahme hat dieses Training gestartet (und beendet sie)
        self.hrv_eigen = False
        self.dfa: float | None = None
        self.fertig = False
        self._empfang: asyncio.Task[None] | None = None
        self._takt: asyncio.Task[None] | None = None
        self._laeuft = False

    # -- Zahlen ------------------------------------------------------------------

    @property
    def dauer_s(self) -> float:
        return time.monotonic() - self._start_mono

    @property
    def hf(self) -> int | None:
        lauf = self.messlauf
        if lauf is None:
            return None
        with contextlib.suppress(Exception):
            return lauf.live.kennzahlen().hf_bpm
        return None

    @property
    def ekg(self) -> bool:
        profil = self.messlauf.profil if self.messlauf is not None else None
        return bool(profil and profil.intervall_quelle == "ekg_rr")

    def text(self) -> str:
        """Für die Benachrichtigung — ortsfrei."""
        teile = [zeit_text(self.dauer_s)]
        if self.quelle is not None:
            teile.insert(0, km_text(self.rechner.distanz_m))
        if self.hf:
            teile.append(f"HF {self.hf}")
        return " · ".join(teile)

    # -- Ablauf ------------------------------------------------------------------

    async def starten(self) -> None:
        self._laeuft = True
        transport = self.state.ble_transport
        if transport is not None and hasattr(transport, "hintergrund"):
            fehler = await transport.hintergrund(
                True, f"{SPORT_NAMEN[self.sportart]} läuft", self.text(), zweck=ZWECK
            )
            if fehler:
                self.warnung = f"Hintergrunddienst nicht gestartet ({fehler}) — Display anlassen."
        if self.messlauf is not None and self.messlauf.aufnahme is None:
            self.messlauf.subject_id = self.subject_id
            self.messlauf.aufnahme_starten()
            self.hrv_eigen = True
        if self.quelle is not None:
            self.datei_pfad = streckenverzeichnis() / dateiname(self.start_utc)
            # Kopf ohne Koordinaten: damit ein abgebrochenes Training nachgetragen werden kann
            self.datei = StreckenSchreiber(
                self.datei_pfad,
                kopf={
                    "schema": "strecke-v1",
                    "sportart": self.sportart,
                    "subject_id": self.subject_id,
                    "started_at": self.start_utc.isoformat(),
                },
            )
            await self.quelle.starten(GPS_TAKT_S)
            self._empfang = asyncio.create_task(self._empfangen())
        self._takt = asyncio.create_task(self._takten())

    async def _empfangen(self) -> None:
        """Ortungen entgegennehmen — ein Fehler stoppt nicht still, er steht in `warnung`."""
        assert self.quelle is not None
        try:
            async for punkt in self.quelle.punkte():
                if self.datei is not None:
                    try:
                        self.datei.schreiben(punkt)
                    except OSError as fehler:  # Speicher voll, Datei weg
                        self.datei.schliessen()
                        self.datei = None
                        self.warnung = f"Strecke wird nicht mehr gespeichert: {fehler}"
                for split in self.rechner.hinzufuegen(punkt):
                    await self._kilometer(split)
        except Exception as fehler:
            self.warnung = f"GPS-Empfang abgebrochen: {fehler}"

    async def _kilometer(self, split: Split) -> None:
        """Ton, Vibration und die Notiz „km N" — die beim Speichern ein Abschnitt wird."""
        lauf = self.messlauf
        km = round(split.nummer * split_laenge_m(self.sportart) / 1000)
        if lauf is not None and lauf.aufnahme is not None:
            lauf.abschnitt_markieren(f"km {km}", name=f"km {km}")
        if self.state.ton is not None and self.state.toene_geladen:
            with contextlib.suppress(Exception):
                await self.state.ton.spielen("wechsel")
        if self.state.haptik is not None:
            with contextlib.suppress(Exception):
                await self.state.haptik.vibrate()

    async def _takten(self) -> None:
        """Benachrichtigung und Live-DFA α1 alle `TEXT_ALLE_S`."""
        transport = self.state.ble_transport
        while self._laeuft:
            await asyncio.sleep(TEXT_ALLE_S)
            if self.quelle is not None and self.quelle.meldung:
                self.warnung = f"GPS: {self.quelle.meldung}"
            if self.ekg and self.messlauf is not None:
                with contextlib.suppress(Exception):
                    t, rr, naht = self.messlauf.live.verlaufsreihe()
                    self.dfa = (
                        aktuell(t, rr, naht, "dfa_alpha1", 120.0, ende=float(t[-1]))
                        if len(t)
                        else None
                    )
            if transport is not None and hasattr(transport, "hintergrund_text"):
                await transport.hintergrund_text(self.text(), zweck=ZWECK)

    async def _anhalten(self) -> None:
        """GPS, Takt, Datei und Vordergrunddienst beenden — ohne zu speichern."""
        self._laeuft = False
        if self._takt is not None:
            self._takt.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._takt
        if self.quelle is not None:
            with contextlib.suppress(Exception):
                await self.quelle.beenden()
            if self._empfang is not None:
                with contextlib.suppress(Exception):
                    await self._empfang
        if self.datei is not None:
            self.datei.schliessen()
        transport = self.state.ble_transport
        if transport is not None and hasattr(transport, "hintergrund"):
            with contextlib.suppress(Exception):
                await transport.hintergrund(False, zweck=ZWECK)

    async def abbrechen(self) -> None:
        """Start gescheitert: nichts speichern, die angefangene Datei entfernen."""
        await self._anhalten()
        if self.hrv_eigen and self.messlauf is not None:
            with contextlib.suppress(Exception):
                self.messlauf.aufnahme_stoppen(datenverzeichnis())
        if self.datei_pfad is not None:
            with contextlib.suppress(OSError):
                self.datei_pfad.unlink()
        self.fertig = True

    async def stoppen(self) -> Strecke:
        """Alles beenden und speichern: Strecke, HRV-Aufnahme, Tagebucheintrag."""
        await self._anhalten()
        hrv_id = None
        if self.hrv_eigen and self.messlauf is not None:
            from trainingsapp.ui.views.messung import aufnahme_eintragen

            ergebnis = self.messlauf.aufnahme_stoppen(datenverzeichnis())
            if ergebnis is not None:
                hrv_id = aufnahme_eintragen(self.state, ergebnis, self.subject_id).id
        r = self.rechner
        mit_gps = self.quelle is not None and bool(r.teilstuecke)
        if not mit_gps and self.datei_pfad is not None:  # kein Fix: keine leere Datei lassen
            with contextlib.suppress(OSError):
                self.datei_pfad.unlink()
        # Wanduhr — mit GPS nie kürzer als die Zeit zwischen erster und letzter Ortung
        dauer = max(self.dauer_s, r.dauer_s) if mit_gps else self.dauer_s
        strecke = training_eintragen(
            self.state,
            subject_id=self.subject_id,
            sportart=self.sportart,
            started_at=self.start_utc,
            ended_at=datetime.now(UTC),
            file_path=(
                self.datei_pfad.relative_to(streckenverzeichnis()).as_posix()
                if mit_gps and self.datei_pfad is not None
                else ""
            ),
            rechner=r if mit_gps else None,
            dauer_s=dauer,
            hrv_recording_id=hrv_id,
        )
        self.fertig = True
        return strecke


def training_eintragen(
    state: AppState,
    *,
    subject_id: str,
    sportart: str,
    started_at: datetime,
    ended_at: datetime,
    file_path: str,
    rechner: StreckenRechner | None,
    dauer_s: float,
    hrv_recording_id: str | None = None,
    title: str = "",
) -> Strecke:
    """Strecke und Tagebucheintrag anlegen — beim Stoppen und beim Nachtragen.

    ``rechner`` ``None`` heißt ohne GPS (Laufband): Strecke 0, Bewegungszeit = Dauer.
    """
    r = rechner
    strecke = Strecke(
        subject_id=subject_id,
        sportart=sportart,
        started_at=started_at,
        ended_at=ended_at,
        file_path=file_path if r is not None else "",
        distanz_m=r.distanz_m if r is not None else 0.0,
        dauer_s=dauer_s,
        bewegt_s=r.bewegt_s if r is not None else dauer_s,
        hoehe_auf_m=r.hoehe_auf_m if r is not None else 0.0,
        hoehe_ab_m=r.hoehe_ab_m if r is not None else 0.0,
        hrv_recording_id=hrv_recording_id,
        title=title,
    )
    ergebnis_feld: dict[str, Any] = {"duration": round(dauer_s)}
    if strecke.distanz_m >= 10:
        ergebnis_feld["distance"] = round(strecke.distanz_m)
    uebung = uebung_fuer(state, sportart)
    sitzung = state.sitzungen.session_fuer(subject_id, None, lokaler_tag(started_at))
    eintrag = state.sitzungen.eintrag_anlegen(sitzung, uebung, ergebnis_feld)
    strecke.session_entry_id = eintrag.id
    state.strecken.anlegen(strecke)
    return strecke


# ---------------------------------------------------------------------------
# Verwaiste Streckendateien — Training, das Android mitten im Lauf beendet hat
# ---------------------------------------------------------------------------


def verwaiste_uebernehmen(state: AppState, pfad: Path) -> Strecke | None:
    """Eine Streckendatei ohne Zeile als Training nachtragen (Ben, 15.10.2026: beim
    Start erkennen und anbieten). Sportart, Profil und Start kommen aus dem Kopf der
    Datei; ohne Kopf gilt „Gehen", das aktive Profil und die erste Ortung. Eine Datei
    ohne Ortung wird gelöscht, nicht eingetragen (``None``)."""
    punkte = jsonl_lesen(pfad)
    if not punkte:
        with contextlib.suppress(OSError):
            pfad.unlink()
        state.verwaiste_strecken = [p for p in state.verwaiste_strecken if p != pfad]
        return None
    kopf = kopf_lesen(pfad) or {}
    sportart = str(kopf.get("sportart") or "")
    if sportart not in SPORTARTEN:
        sportart = GEHEN
    subject_id = str(kopf.get("subject_id") or "")
    if not subject_id or state.profile.laden(subject_id) is None:
        subject_id = state.profil.id
    try:
        started_at = datetime.fromisoformat(str(kopf["started_at"]))
    except (KeyError, ValueError):
        started_at = datetime.fromtimestamp(punkte[0].t, UTC)
    ended_at = datetime.fromtimestamp(punkte[-1].t, UTC)
    r = rechnen(punkte, sportart)
    strecke = training_eintragen(
        state,
        subject_id=subject_id,
        sportart=sportart,
        started_at=started_at,
        ended_at=ended_at,
        file_path=pfad.relative_to(streckenverzeichnis()).as_posix(),
        rechner=r,
        dauer_s=max(r.dauer_s, (ended_at - started_at).total_seconds()),
        title="Nachgetragen — die App wurde während des Trainings beendet",
    )
    state.verwaiste_strecken = [p for p in state.verwaiste_strecken if p != pfad]
    return strecke


def verwaiste_dialog(page: ft.Page, state: AppState) -> ft.AlertDialog:
    """Beim Start: je verwaister Datei „Übernehmen" oder „Löschen" (keine Koordinaten)."""
    zeilen = ft.Column(tight=True, spacing=4)

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def beschriftung(pfad: Path) -> str:
        kopf = kopf_lesen(pfad) or {}
        sport = SPORT_NAMEN.get(str(kopf.get("sportart") or ""), "Training")
        try:
            wann = datetime.fromisoformat(str(kopf["started_at"])).astimezone()
            return f"{sport} vom {wann:%d.%m.%Y %H:%M}"
        except (KeyError, ValueError):
            return f"{sport} ({pfad.name})"

    def uebernehmer(pfad: Path) -> Callable[[], None]:
        def handler() -> None:
            strecke = verwaiste_uebernehmen(state, pfad)
            melden("Training nachgetragen — auch im Tagebuch." if strecke else "Datei war leer.")
            zeichnen()

        return handler

    def loescher(pfad: Path) -> Callable[[], None]:
        def handler() -> None:
            with contextlib.suppress(OSError):
                pfad.unlink()
            state.verwaiste_strecken = [p for p in state.verwaiste_strecken if p != pfad]
            melden("Strecke gelöscht.")
            zeichnen()

        return handler

    def zeichnen() -> None:
        if not state.verwaiste_strecken:
            page.pop_dialog()
            return
        zeilen.controls = [
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(beschriftung(pfad), expand=True),
                    ft.TextButton("Löschen", on_click=loescher(pfad)),
                    ft.FilledTonalButton("Übernehmen", on_click=uebernehmer(pfad)),
                ],
            )
            for pfad in state.verwaiste_strecken
        ]
        with contextlib.suppress(Exception):
            zeilen.update()

    zeichnen()
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Unvollständiges Training gefunden"),
        content=ft.Column(
            tight=True,
            spacing=10,
            controls=[
                ft.Text(
                    "Die App wurde während eines Trainings beendet. Die Strecke liegt noch "
                    "auf dem Handy — nachtragen (Strecke, Zeit, Tagebuch) oder löschen?",
                    size=13,
                ),
                zeilen,
            ],
        ),
        actions=[ft.TextButton("Später", on_click=lambda: page.pop_dialog())],
    )


def _verbunden(state: AppState) -> bool:
    lauf = state.messlauf
    return lauf is not None and lauf.status.verbindung == Verbindung.VERBUNDEN


# ---------------------------------------------------------------------------
# Live
# ---------------------------------------------------------------------------


def _gross(name: str, wert: str, *, einheit: str = "", farbe: str | None = None) -> ft.Control:
    return ft.Container(
        expand=True,
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                ft.Text(name, size=12, opacity=0.7),
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(wert, size=28, weight=ft.FontWeight.W_600, color=farbe),
                        ft.Text(einheit, size=12, opacity=0.7),
                    ],
                ),
            ],
        ),
    )


def ausdauer_view(page: ft.Page, state: AppState) -> ft.View:
    """Training vorbereiten und starten — läuft eines, die großen Zahlen und die Karte."""
    nummer = state.ausdauer_ansicht = state.ausdauer_ansicht + 1
    inhalt = ft.Column(spacing=14)
    zahlen = ft.Column(spacing=8)
    karte_platz = ft.Container()
    pause_text = ft.Text("Auto-Pause", size=13, color=ft.Colors.AMBER_800, visible=False)
    warnung = ft.Text(size=13, color=ft.Colors.ERROR, visible=False)
    strecken_karte: StreckenKarte | None = None
    gross = {"an": False}

    def lauf_jetzt() -> AusdauerLauf | None:
        lauf: AusdauerLauf | None = state.ausdauer
        return lauf if lauf is not None and not lauf.fertig else None

    # -- Start ---------------------------------------------------------------------

    async def starten() -> None:
        from trainingsapp.ui.views.gps_test import quelle_holen

        if state.gps_test is not None and not state.gps_test.fertig:
            page.show_dialog(ft.SnackBar(ft.Text("Erst den GPS-Test beenden.")))
            return
        quelle: GpsQuelle | None = None
        if state.ausdauer_gps:
            quelle = quelle_holen(page, state)
            berechtigung = getattr(quelle, "berechtigung", None)
            if berechtigung is not None and (status := await berechtigung()) != "erteilt":
                page.show_dialog(
                    ft.SnackBar(
                        ft.Text(
                            f"Standort {status} — in den Einstellungen des Handys erlauben, "
                            "oder ohne GPS trainieren."
                        )
                    )
                )
                return
        lauf = AusdauerLauf(state, state.ausdauer_sportart, quelle)
        try:
            await lauf.starten()
        except Exception as fehler:  # GPS startet nicht, Datei nicht anlegbar …
            await lauf.abbrechen()
            page.show_dialog(ft.SnackBar(ft.Text(f"Training nicht gestartet: {fehler}")))
            return
        state.ausdauer = lauf  # erst jetzt — ein halb gestarteter Lauf bliebe sonst hängen
        zeichnen()
        page.update()
        page.run_task(ticker)
        if quelle is not None and state.ausdauer_karte:
            karten_hinweis_einmal()

    def karten_hinweis_einmal() -> None:
        """Einmal (nicht je Aufzeichnung, Ben 15.10.2026): Die Karte holt Kacheln online."""
        if state.einstellungen.lesen(SettingRepo.HINWEIS_KARTE, "0") == "1":
            return

        def verstanden() -> None:
            state.einstellungen.setzen(SettingRepo.HINWEIS_KARTE, "1")
            page.pop_dialog()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Karte während des Trainings"),
                content=ft.Text(
                    "Die Karte lädt ihre Kacheln von OpenStreetMap. Dabei gehen grobe "
                    "Kachelkoordinaten (einige hundert Meter) an deren Server — die Strecke "
                    "selbst bleibt auf dem Handy. Wer das nicht will, schaltet „Karte zeigen“ "
                    "aus; dann wird nichts geladen."
                ),
                actions=[ft.FilledButton("Verstanden", on_click=verstanden)],
            )
        )

    def karte_gewaehlt(e: ft.Event[ft.Switch]) -> None:
        state.ausdauer_karte = bool(e.control.value)

    def beenden_fragen() -> None:
        async def beenden() -> None:
            page.pop_dialog()
            lauf = lauf_jetzt()
            if lauf is None:
                return
            strecke = await lauf.stoppen()
            state.ausdauer = None
            page.show_dialog(ft.SnackBar(ft.Text("Training gespeichert — auch im Tagebuch.")))
            await page.push_route(f"/ausdauer/{strecke.id}")

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Training beenden?"),
                content=ft.Text("Strecke, Zeit und HRV werden gespeichert."),
                actions=[
                    ft.TextButton("Weiter trainieren", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Beenden", icon=ft.Icons.STOP, on_click=beenden),
                ],
            )
        )

    def kartenhoehe() -> float:
        """Quer: die Karte füllt die Höhe neben den Zahlen; hochkant klein oder groß."""
        if querformat(page):
            return max(220.0, float(page.height or 480) - 120)
        return 460.0 if gross["an"] else 220.0

    def karte_umschalten() -> None:
        gross["an"] = not gross["an"]
        if strecken_karte is not None:
            strecken_karte.karte.height = kartenhoehe()
            with contextlib.suppress(Exception):
                strecken_karte.karte.update()

    def umbauen() -> None:
        """Gedreht (``page.on_resize``): Zahlen und Karte neu anordnen, Karte in neuer Höhe."""
        if state.ausdauer_ansicht != nummer or lauf_jetzt() is None:
            return
        zeichnen()
        with contextlib.suppress(Exception):
            page.update()

    # -- Live-Werte ----------------------------------------------------------------

    def werte(lauf: AusdauerLauf) -> None:
        r = lauf.rechner
        aktuell_ms = r.aktuelles_tempo_ms()
        aktuell_s = 1000.0 / aktuell_ms if aktuell_ms else None
        reihen: list[ft.Control] = [
            ft.Row(
                spacing=8,
                controls=[
                    _gross("Zeit", zeit_text(lauf.dauer_s)),
                    _gross("Strecke", km_text(r.distanz_m).removesuffix(" km"), einheit="km")
                    if lauf.quelle is not None
                    else _gross("Strecke", "–"),
                ],
            )
        ]
        if lauf.quelle is not None:
            reihen.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        _gross("Tempo", tempo_text(lauf.sportart, aktuell_s)),
                        _gross("Ø Tempo", tempo_text(lauf.sportart, r.tempo_s_pro_km)),
                    ],
                )
            )
        if lauf.messlauf is not None:
            hf_zeile: list[ft.Control] = [
                _gross("Herzfrequenz", _zahl(lauf.hf), einheit="bpm", farbe=ft.Colors.RED_400)
            ]
            if lauf.ekg:
                hf_zeile.append(_gross("DFA α1 (Schätzwert)", _zahl(lauf.dfa, 2)))
            reihen.append(ft.Row(spacing=8, controls=hf_zeile))
        zahlen.controls = reihen
        pause_text.visible = lauf.quelle is not None and r.pausiert and r.distanz_m > 0
        warnung.value = lauf.warnung or ""
        warnung.visible = bool(lauf.warnung)

    def zeichnen() -> None:
        nonlocal strecken_karte
        lauf = lauf_jetzt()
        if lauf is not None:
            werte(lauf)
            strecken_karte = None
            karte_platz.content = None
            zahlen_karte = karte(
                ft.Row(
                    controls=[
                        ft.Icon(SPORT_SYMBOLE[lauf.sportart]),
                        titel(f"{SPORT_NAMEN[lauf.sportart]} läuft"),
                        pause_text,
                    ],
                ),
                zahlen,
                warnung,
                ft.FilledButton("Beenden", icon=ft.Icons.STOP, on_click=beenden_fragen),
                ft.Switch(
                    label="Karte zeigen (Kacheln von OpenStreetMap)",
                    value=state.ausdauer_karte,
                    on_change=karte_gewaehlt,
                )
                if lauf.quelle is not None
                else ft.Container(),
                hinweis(
                    "Display darf aus sein — die Benachrichtigung zeigt Strecke, Zeit und "
                    "Herzfrequenz. An jedem Kilometer ein Ton."
                ),
            )
            if querformat(page) and lauf.quelle is not None and state.ausdauer_karte:
                # Quer (Ben, 15.10.2026): Zahlen links, die Karte rechts in voller Höhe
                inhalt.controls = [
                    ft.Row(
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                width=min(360.0, float(page.width or 900) * 0.42),
                                content=zahlen_karte,
                            ),
                            ft.Container(expand=True, content=karte_platz),
                        ],
                    )
                ]
            else:
                inhalt.controls = [zahlen_karte, karte_platz]
            return
        sportwahl = ft.SegmentedButton(
            selected=[state.ausdauer_sportart],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=s, label=ft.Text(SPORT_NAMEN[s]), icon=ft.Icon(SPORT_SYMBOLE[s]))
                for s in SPORTARTEN
            ],
            on_change=sport_gewaehlt,
        )
        gps_schalter = ft.Switch(
            label="Mit GPS (aus: Laufband, Halle)",
            value=state.ausdauer_gps,
            on_change=gps_gewaehlt,
        )
        inhalt.controls = [
            karte(
                titel("Training"),
                sportwahl,
                gps_schalter,
                geraet_zeile(),
                ft.FilledButton("Start", icon=ft.Icons.PLAY_ARROW, on_click=starten),
            ),
            hinweis(
                "Die Strecke bleibt auf dem Handy (Ordner „Strecken“) — nicht im "
                "Messungs-Export, nie in einer Synchronisation. Hinaus geht sie nur, "
                "wenn du in der Auswertung „GPX exportieren“ tippst. Nur die Karte holt "
                "ihre Kacheln online (abschaltbar)."
            ),
        ]

    def geraet_zeile() -> ft.Control:
        lauf = state.messlauf
        if not _verbunden(state):
            return hinweis(
                "Ohne Gurt: Strecke und Zeit. Im Reiter „Messung“ unter „Live“ einen Gurt "
                "verbinden, dann laufen Herzfrequenz und HRV mit."
            )
        name = lauf.geraet_name if lauf is not None else ""
        optisch = bool(lauf and lauf.profil and lauf.profil.intervall_quelle != "ekg_rr")
        if optisch:
            return hinweis(
                f"{name}: Herzfrequenz und HRV laufen mit. Achtung — optisch steht die "
                "Herzfrequenz bei Bewegung oft still (Polar), und HRV gibt es nur in Ruhe. "
                "Für das Training besser den Brustgurt (H10)."
            )
        return hinweis(f"{name}: Herzfrequenz, HRV und DFA α1 laufen mit.")

    def sport_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.ausdauer_sportart = str(e.control.selected[0])

    def gps_gewaehlt(e: ft.Event[ft.Switch]) -> None:
        state.ausdauer_gps = bool(e.control.value)

    # -- Takt der Anzeige ------------------------------------------------------------

    async def ticker() -> None:
        nonlocal strecken_karte
        while state.ausdauer_ansicht == nummer:
            lauf = lauf_jetzt()
            if lauf is None:
                return
            if state.im_vordergrund:
                werte(lauf)
                punkte = lauf.rechner.punkte
                if not state.ausdauer_karte and strecken_karte is not None:
                    strecken_karte = None
                    karte_platz.content = None
                if punkte and strecken_karte is None and state.ausdauer_karte:
                    strecken_karte = StreckenKarte(punkte[-1], hoehe=kartenhoehe())
                    karte_platz.content = karte(
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                titel("Karte"),
                                ft.IconButton(
                                    ft.Icons.OPEN_IN_FULL,
                                    tooltip="Karte groß oder klein",
                                    on_click=lambda: karte_umschalten(),
                                    visible=not querformat(page),  # quer ist sie schon groß
                                ),
                            ],
                        ),
                        strecken_karte.karte,
                    )
                folgen = strecken_karte.nachziehen(punkte) if strecken_karte else False
                with contextlib.suppress(Exception):
                    page.update()
                if folgen and strecken_karte is not None:
                    with contextlib.suppress(Exception):
                        await strecken_karte.folgen(punkte[-1])
            await asyncio.sleep(1.0)

    zeichnen()
    state.groesse_beobachter["ausdauer"] = umbauen
    if lauf_jetzt() is not None:
        page.run_task(ticker)
    return ft.View(
        route="/ausdauer",
        appbar=ft.AppBar(title=ft.Text("Ausdauer")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------


def _hrv_laden(state: AppState, strecke: Strecke) -> tuple[Recording, Korrigiert] | None:
    """Die HRV-Aufnahme des Trainings, korrigiert wie in ihrer Auswertung (Sidecar, Regeln)."""
    if not strecke.hrv_recording_id:
        return None
    eintrag = state.hrv.laden(strecke.hrv_recording_id)
    if eintrag is None:
        return None
    pfad = messungenverzeichnis() / eintrag.file_path
    if not pfad.exists():
        return None
    rec = laden(pfad)
    regeln = analyse_regeln(pfad) or state.korrekturregeln()
    basis = analysebasis(rec, regeln)
    gespeichert = analyse_laden(pfad, basis)
    if gespeichert:
        korrekturen = gespeichert
    else:
        ketten = vorschlaege(basis.rec, regeln)
        korrekturen = [
            v for i in sorted(vorauswahl(ketten, regeln.vorauswahl)) for v in ketten[i].vorschlag
        ]
    return basis.rec, anwenden(basis.rec, korrekturen)


def _km_tabelle(
    strecke: Strecke,
    splits: Sequence[Split],
    hrv: tuple[Recording, Korrigiert] | None,
    ekg: bool,
) -> ft.Control:
    kopf = ["km", "Zeit", "Tempo", "Ø HF", "DFA α1", "Höhe"]
    zeilen = [kopf]
    bisher = 0.0
    for sp in splits:
        bisher += sp.distanz_m
        voll = abs(sp.distanz_m - split_laenge_m(strecke.sportart)) < 1
        hf = alpha = None
        if hrv is not None:
            rec, korr = hrv
            start = rec.start_utc.timestamp() if rec.start_utc else None
            if start is not None:
                w = werte_zwischen(rec, korr, sp.t_start - start, sp.t_ende - start, dfa=ekg)
                hf, alpha = w["mean_bpm"], w["dfa_alpha1"]
        zeilen.append(
            [
                _zahl(bisher / 1000, 0 if voll else 2),
                zeit_text(sp.t_ende - sp.t_start),
                tempo_text(strecke.sportart, sp.tempo_s_pro_km),
                _zahl(hf),
                _zahl(alpha, 2),
                _zahl(sp.hoehe_auf_m),
            ]
        )
    return ft.Column(
        spacing=2,
        controls=[
            ft.Row(
                spacing=4,
                controls=[
                    ft.Text(
                        zelle,
                        expand=1,
                        size=12 if i == 0 else 13,
                        weight=ft.FontWeight.W_600 if i == 0 else None,
                        opacity=0.7 if i == 0 else 1.0,
                        text_align=ft.TextAlign.RIGHT if j else ft.TextAlign.LEFT,
                    )
                    for j, zelle in enumerate(zeile)
                ],
            )
            for i, zeile in enumerate(zeilen)
        ],
    )


def _dfa_teil(hrv: tuple[Recording, Korrigiert], start_utc: datetime) -> ft.Control | None:
    """DFA-α1-Überblick: Verlauf, Zeit je Wertebereich — beschreibend, ohne Empfehlung."""
    rec, korr = hrv
    achse = schlagzeiten(rec)
    zeiten = korr_zeiten(korr, achse)
    t, rr, naht = reihe(zeiten, korr.rr_ms, korr.breaks)
    korrigiert = [z for z, f in zip(zeiten, korr.flag, strict=True) if f != "orig"]
    punkte = dfa_verlauf(t, rr, naht, korrigiert)
    if not punkte or all(w is None for _, w, _ in punkte):
        return None
    versatz = (start_utc - rec.start_utc).total_seconds() if rec.start_utc else 0.0
    linien: list[list[tuple[float, float]]] = [[]]
    for te, wert, _ in punkte:
        if wert is None:
            if linien[-1]:
                linien.append([])
            continue
        linien[-1].append(((te - versatz) / 60.0, wert))
    reihen = [Reihe(teil, farbe=ft.Colors.PURPLE_400) for teil in linien if teil]
    bereiche = zeit_je_bereich(punkte)
    return ft.Column(
        spacing=8,
        controls=[
            kurve(
                reihen,
                einheit="DFA α1",
                hoehe=180,
                y_spanne_min=0.5,
                y_schritt_min=0.1,
                x_text=lambda x: f"{x:g}".replace(".", ","),
                x_schritte=(1, 2, 5, 10, 15, 30, 60),
            ),
            ft.Text("Minuten je Wertebereich", size=12, opacity=0.7),
            ft.Row(
                wrap=True,
                spacing=14,
                controls=[
                    ft.Text(f"{name}: {_zahl(minuten, 1)} min", size=13)
                    for name, minuten in bereiche
                ],
            ),
            hinweis(
                "DFA α1 beschreibt, wie gleichmäßig sich die Herzschlag-Abstände verändern — "
                "ein Schätzwert, nur mit EKG-Gurt. Fenster mit 3 % oder mehr korrigierten "
                "Schlägen bleiben leer. Die App gibt keine Zonen oder Empfehlungen; x-Achse: "
                "Minuten seit dem Start."
            ),
        ],
    )


def ausdauer_detail_view(page: ft.Page, state: AppState, strecke: Strecke) -> ft.View:
    route = f"/ausdauer/{strecke.id}"
    punkte: list[Punkt] = []
    if strecke.file_path:
        pfad = streckenverzeichnis() / strecke.file_path
        if pfad.exists():
            punkte = jsonl_lesen(pfad)
    r = rechnen(punkte, strecke.sportart) if punkte else None
    hrv = _hrv_laden(state, strecke)
    eintrag = state.hrv.laden(strecke.hrv_recording_id) if strecke.hrv_recording_id else None
    ekg = bool(eintrag and eintrag.intervall_quelle == "ekg_rr")
    lokal = strecke.started_at.astimezone()

    async def gpx_export() -> None:
        if not punkte:
            return
        herz: dict[float, int] = {}
        if hrv is not None and hrv[0].start_utc is not None:
            start = hrv[0].start_utc.timestamp()
            je_wand = hf_je_zeit(hrv[0], [p.t - start for p in punkte])
            herz = {p.t: bpm for p in punkte if (bpm := je_wand.get(p.t - start)) is not None}
        daten = gpx(
            punkte,
            name=f"{SPORT_NAMEN[strecke.sportart]} {lokal:%d.%m.%Y %H:%M}",
            sportart=strecke.sportart,
            herzfrequenz=herz or None,
        )
        await weitergeben(
            page, f"{lokal:%Y-%m-%d_%H%M}_{strecke.sportart}.gpx", daten, "application/gpx+xml"
        )

    def loeschen_fragen() -> None:
        async def loeschen() -> None:
            state.strecken.loeschen(strecke.id)
            page.pop_dialog()
            page.show_dialog(ft.SnackBar(ft.Text("Aus der Liste entfernt — die Datei bleibt.")))
            await page.push_route("/")

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Training entfernen?"),
                content=ft.Text(
                    "Es verschwindet aus der Liste. Die Strecke bleibt im Ordner „Strecken“, "
                    "HRV-Aufnahme und Tagebucheintrag bleiben."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Entfernen", on_click=loeschen),
                ],
            )
        )

    async def hrv_oeffnen() -> None:
        await page.push_route(f"/messung/{strecke.hrv_recording_id}")

    # Zwei feste Zeilen — Kacheln mit expand in einer umbrechenden Zeile zeigt Flet
    # nur als grauen Fehlerkasten
    ueberblick = ft.Column(
        spacing=8,
        controls=[
            ft.Row(
                spacing=8,
                controls=[
                    _gross("Strecke", km_text(strecke.distanz_m).removesuffix(" km"), einheit="km")
                    if strecke.file_path
                    else _gross("Strecke", "–"),
                    _gross("Zeit", zeit_text(strecke.dauer_s)),
                ],
            ),
            ft.Row(
                spacing=8,
                controls=[
                    _gross("in Bewegung", zeit_text(strecke.bewegt_s)),
                    _gross(
                        "Ø Tempo",
                        tempo_text(strecke.sportart, r.tempo_s_pro_km if r is not None else None),
                    ),
                ],
            ),
        ],
    )
    teile: list[ft.Control] = [
        karte(
            ft.Row(
                controls=[
                    ft.Icon(SPORT_SYMBOLE.get(strecke.sportart, ft.Icons.DIRECTIONS_RUN)),
                    titel(SPORT_NAMEN.get(strecke.sportart, strecke.sportart)),
                ]
            ),
            ueberblick,
            ft.Text(
                f"Höhe: {_zahl(strecke.hoehe_auf_m)} m hinauf, {_zahl(strecke.hoehe_ab_m)} m "
                "hinab (nur in Bewegung, ab 5 m)",
                size=12,
                opacity=0.7,
            ),
        ),
        karte(titel("Strecke"), ganze_strecke(r.teilstuecke if r is not None else [])),
    ]
    if r is not None and r.splits_mit_rest():
        teile.append(
            karte(
                titel("Je Kilometer" if strecke.sportart != RAD else "Je 5 Kilometer"),
                _km_tabelle(strecke, r.splits_mit_rest(), hrv, ekg),
            )
        )
    if hrv is not None and ekg:
        dfa = _dfa_teil(hrv, strecke.started_at)
        if dfa is not None:
            teile.append(karte(titel("DFA α1 — Überblick"), dfa))
    if eintrag is not None:  # nicht nur die ID — die Aufnahme kann gelöscht sein
        teile.append(
            karte(
                titel("HRV"),
                hinweis("Die Herzfrequenz-Aufnahme dieses Trainings, mit Abschnitten je km."),
                ft.FilledTonalButton(
                    "HRV-Auswertung öffnen", icon=ft.Icons.MONITOR_HEART, on_click=hrv_oeffnen
                ),
            )
        )
    teile.append(
        hinweis(
            "Die Strecke bleibt auf dem Handy. „GPX exportieren“ (oben) gibt sie ausdrücklich "
            "heraus — Strava, Komoot, Garmin Connect und OsmAnd lesen GPX."
        )
    )
    return ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(f"{SPORT_NAMEN.get(strecke.sportart, '')} {lokal:%d.%m. %H:%M}"),
            actions=[
                ft.IconButton(
                    ft.Icons.IOS_SHARE,
                    tooltip="GPX exportieren",
                    on_click=gpx_export,
                    disabled=not punkte,
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="Aus der Liste entfernen",
                    on_click=loeschen_fragen,
                ),
            ],
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=12,
        controls=[sicher(ft.Column(spacing=12, controls=teile), expand=False)],
    )


# ---------------------------------------------------------------------------
# Für den Reiter „Messung"
# ---------------------------------------------------------------------------


def ausdauer_karte(page: ft.Page, state: AppState) -> ft.Control:
    """Einstieg im Reiter „Messung → Live": Training starten oder das laufende öffnen."""

    async def oeffnen() -> None:
        await page.push_route("/ausdauer")

    lauf: AusdauerLauf | None = state.ausdauer
    if lauf is not None and not lauf.fertig:
        return karte(
            titel(f"{SPORT_NAMEN[lauf.sportart]} läuft"),
            ft.Text(lauf.text(), size=14),
            ft.FilledButton("Öffnen", icon=ft.Icons.OPEN_IN_NEW, on_click=oeffnen),
        )
    return karte(
        titel("Ausdauer"),
        hinweis("Gehen, Laufen, Rad — mit GPS und, falls verbunden, mit HRV."),
        ft.FilledTonalButton("Training starten", icon=ft.Icons.DIRECTIONS_RUN, on_click=oeffnen),
    )


def strecken_zeilen(page: ft.Page, state: AppState) -> list[ft.Control]:
    """Die Trainings des Profils für die Liste der Aufzeichnungen — neueste zuerst."""

    def oeffner(strecke_id: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(f"/ausdauer/{strecke_id}")

        return handler

    zeilen: list[ft.Control] = []
    for s in state.strecken.alle(state.profil.id):
        lokal = s.started_at.astimezone()
        teile = [SPORT_NAMEN.get(s.sportart, s.sportart)]
        if s.file_path:
            teile.append(km_text(s.distanz_m))
        teile.append(zeit_text(s.dauer_s))
        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(SPORT_SYMBOLE.get(s.sportart, ft.Icons.DIRECTIONS_RUN)),
                title=ft.Text(" · ".join(teile)),
                subtitle=ft.Text(
                    f"{lokal:%d.%m.%Y  %H:%M}" + ("  ·  mit HRV" if s.hrv_recording_id else ""),
                    size=12,
                ),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
                on_click=oeffner(s.id),
            )
        )
    return zeilen


__all__ = [
    "AusdauerLauf",
    "ausdauer_detail_view",
    "ausdauer_karte",
    "ausdauer_view",
    "km_text",
    "strecken_zeilen",
    "tempo_text",
    "training_eintragen",
    "uebung_fuer",
    "verwaiste_dialog",
    "verwaiste_uebernehmen",
    "zeit_text",
]
