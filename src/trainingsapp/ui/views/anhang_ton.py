"""Eine Audioaufnahme anhängen — Route ``<basis>/anhang/aufnehmen/<ziel>/audio`` (Ben,
22.10.2026: „Auch eine Audioaufnahme soll möglich sein + Photo + Video. Erweitere die Medien
um Audio.“).

Wie die Kamera (`views/anhang_aufnahme.py`) eine Seite über der Ansicht, von der man kommt —
für einen Eintrag (Leistungen) oder für den Tag (Notiz zum Tag unter Heute,
`core.anhaenge.Ziel`). Ablauf: ● nimmt auf, die Zeit läuft groß mit, ⏸ hält an und macht
weiter, ⏹ beendet; danach Anhören, eine Notizzeile, „Behalten“ / „Verwerfen“ — Verwerfen
führt zurück zum ●. Nach `AUDIO_MAX_S` endet die Aufnahme von selbst.

Aufgenommen wird mit flet-audio-recorder (Flutter-Plugin record) als AAC in ``.m4a``,
einkanalig, mit der Tonrate der Qualitätsstufe (`Qualitaet.audio_bitrate`) — gleich in eine
Datei unter ``Anhaenge/.aufnahme/``, nichts liegt im Speicher. „Behalten“ verschiebt sie an
ihren Platz (`AnhangRepo.dateien_uebernehmen`). Kennt der Rekorder kein AAC (am Rechner),
wird es WAV. Die Datei wird **vor** dem Start leer angelegt: Flet reicht dem Plugin nur
einen vorhandenen Pfad unverändert durch, einen neuen legte es in den Ordner der App-Assets
(``getAssetSrc``).

Der Rekorder ist ein Dienst, kein Teil der Seite — wer sie verlässt (Pfeil, Systemtaste),
verwirft eine laufende Aufnahme samt Datei, sonst nähme er weiter auf.
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import (
    AUDIO,
    AUDIO_MAX_S,
    ENDUNG,
    Qualitaet,
    Ziel,
    dauer_text,
    groesse_text,
    neuer_anhang,
)
from trainingsapp.core.models import jetzt, new_id
from trainingsapp.data.anhaenge import qualitaet_lesen
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.tonspieler import Tonspieler
from trainingsapp.ui.components.zurueck import zurueck_ziel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.anhang_aufnahme import ziel_name

#: Takt der laufenden Zeit (s)
TAKT_S = 0.5


class _Ton:
    """Zustand der Seite: Rekorder, laufende Aufnahme, Ergebnis."""

    def __init__(self, page: Any, state: AppState, ziel: Ziel) -> None:
        self.page, self.state, self.ziel = page, state, ziel
        self.qualitaet: Qualitaet = qualitaet_lesen(state.einstellungen)
        self.rekorder: Any = None  # flet_audio_recorder.AudioRecorder
        #: Die Datei, in die der Rekorder schreibt — bis „Behalten“ in ``.aufnahme/``
        self.datei: Path | None = None
        self.endung = ENDUNG[AUDIO]
        #: Wann die Aufnahme begann (Uhrzeit des Anhangs) und wie lange sie lief
        self.beginn: datetime | None = None
        self.laeuft_seit: float | None = None
        self.angesammelt = 0.0
        self.pausiert = False
        self.dauer_s: float | None = None
        #: Beendet und bereit zum Behalten
        self.fertig = False
        self.spieler: Tonspieler | None = None
        self.ticker: Any = None
        self.notiz = ft.TextField(
            label="Notiz (optional)", hint_text="z. B. Gedanken nach dem Laufen", dense=True
        )
        self.zeit = ft.Text("0:00", size=48, weight=ft.FontWeight.W_600)
        self.rest = ft.Text("", size=12, opacity=0.6)
        self.status = ft.Text("", size=13, opacity=0.75, text_align=ft.TextAlign.CENTER)
        self.flaeche = ft.Container(alignment=ft.Alignment.CENTER)
        self.knoepfe = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=16)
        #: die Seite, sobald sie gebaut ist (für Zurück)
        self.ansicht: Any = None

    @property
    def laeuft(self) -> bool:
        """Es wird aufgenommen — auch angehalten."""
        return self.laeuft_seit is not None or self.pausiert

    def vergangen(self) -> float:
        """Sekunden Aufnahme, ohne die Pausen."""
        lauf = time.monotonic() - self.laeuft_seit if self.laeuft_seit is not None else 0.0
        return self.angesammelt + lauf

    def bereit_text(self) -> str:
        return f"{self.qualitaet.name_kurz} · höchstens {dauer_text(AUDIO_MAX_S)} min"

    # -- Aufnehmen -----------------------------------------------------------------------

    def _rekorder_anlegen(self) -> bool:
        if self.rekorder is not None:
            return True
        try:
            from flet_audio_recorder import AudioRecorder
        except ImportError:
            self.melden("Audioaufnahme fehlt in diesem Build.")
            return False
        self.rekorder = AudioRecorder()
        return True

    async def _konfiguration(self) -> Any:
        """AAC, ein Kanal, die Tonrate der Stufe; Bluetooth-Kopfhörer bleiben außen vor
        (deren Gesprächsmodus klingt dünn) — das Mikrofon des Telefons nimmt auf."""
        from flet_audio_recorder import (
            AndroidRecorderConfiguration,
            AudioEncoder,
            AudioRecorderConfiguration,
        )

        encoder, self.endung = AudioEncoder.AACLC, ENDUNG[AUDIO]
        with contextlib.suppress(Exception):
            if not await self.rekorder.is_supported_encoder(AudioEncoder.AACLC):
                encoder, self.endung = AudioEncoder.WAV, "wav"
        return AudioRecorderConfiguration(
            encoder=encoder,
            channels=1,
            sample_rate=44_100,
            bit_rate=self.qualitaet.audio_bitrate,
            auto_gain=True,
            suppress_noise=True,
            android_configuration=AndroidRecorderConfiguration(manage_bluetooth=False),
        )

    async def starten(self) -> None:
        """● — Berechtigung holen, Datei vorlegen, aufnehmen."""
        if self.laeuft or self.fertig:
            return
        if getattr(self.page, "web", False):
            self.melden("Im Browser geht das nicht — in der App am Handy aufnehmen.")
            return
        if not self._rekorder_anlegen():
            return
        try:
            if not await self.rekorder.has_permission():
                self.melden(
                    "Ohne Mikrofon-Berechtigung geht es nicht — in den Systemeinstellungen "
                    "der App erlauben."
                )
                return
            konfiguration = await self._konfiguration()
            self.datei = self.state.anhaenge.aufnahme_ordner() / f"{new_id()}.{self.endung}"
            self.datei.touch()  # nur einen vorhandenen Pfad reicht Flet unverändert durch
            gestartet = await self.rekorder.start_recording(
                output_path=str(self.datei), configuration=konfiguration
            )
        except Exception as fehler:
            self.datei_loeschen()
            self.melden(f"Aufnahme fehlgeschlagen: {fehler}")
            return
        if not gestartet:
            self.datei_loeschen()
            self.melden("Die Aufnahme ließ sich nicht starten.")
            return
        self.beginn = jetzt()
        self.angesammelt = 0.0
        self.laeuft_seit = time.monotonic()
        self.status.value = f"Aufnahme läuft · {self.qualitaet.name_kurz}"
        self.zeichnen()
        self.ticker = self.page.run_task(self._ticken)

    async def _ticken(self) -> None:
        while self.laeuft:
            vergangen = self.vergangen()
            self.zeit.value = dauer_text(vergangen)
            self.rest.value = f"noch {dauer_text(max(AUDIO_MAX_S - vergangen, 0))} min"
            for c in (self.zeit, self.rest):
                with contextlib.suppress(Exception):
                    c.update()
            if vergangen >= AUDIO_MAX_S:
                await self.stoppen()
                return
            await asyncio.sleep(TAKT_S)

    async def pause_umschalten(self) -> None:
        """⏸ hält an, ▶ nimmt weiter auf — in dieselbe Datei."""
        if self.rekorder is None or not self.laeuft:
            return
        try:
            if self.pausiert:
                await self.rekorder.resume_recording()
                self.pausiert = False
                self.laeuft_seit = time.monotonic()
                self.status.value = f"Aufnahme läuft · {self.qualitaet.name_kurz}"
            else:
                await self.rekorder.pause_recording()
                self.angesammelt = self.vergangen()
                self.laeuft_seit = None
                self.pausiert = True
                self.status.value = "Angehalten — ▶ nimmt weiter auf, ⏹ beendet"
        except Exception as fehler:
            self.status.value = f"Pause: {fehler}"
        self.zeichnen()

    async def stoppen(self) -> None:
        """⏹ — die Aufnahme beenden und zum Anhören bereitlegen."""
        if self.rekorder is None or not self.laeuft:
            return
        self.dauer_s = self.vergangen()
        self.laeuft_seit = None
        self.pausiert = False
        try:
            gemeldet = await self.rekorder.stop_recording()
        except Exception as fehler:
            self.datei_loeschen()
            self.melden(f"Aufnahme fehlgeschlagen: {fehler}")
            return
        datei = self.datei
        if (datei is None or not _hat_inhalt(datei)) and gemeldet and _hat_inhalt(Path(gemeldet)):
            datei = Path(gemeldet)  # der Rekorder schrieb woanders hin
        if datei is None or not _hat_inhalt(datei):
            self.datei_loeschen()
            self.melden("Die Aufnahme ist leer — noch einmal versuchen.")
            return
        self.datei = datei
        self.fertig = True
        self.spieler = Tonspieler(datei, self.dauer_s)
        self.spieler.anlegen()
        self.flaeche.content = self.spieler.control
        self.zeit.value = dauer_text(self.dauer_s)
        self.rest.value = ""
        self.status.value = f"{groesse_text(datei.stat().st_size)} · {self.qualitaet.name_kurz}"
        self.zeichnen()

    # -- Ergebnis ------------------------------------------------------------------------

    async def behalten(self) -> None:
        if not self.fertig or self.datei is None:
            return
        if self.spieler is not None:
            await self.spieler.anhalten()
        a = neuer_anhang(
            self.ziel,
            AUDIO,
            self.qualitaet,
            self.beginn or jetzt(),
            dauer_s=self.dauer_s,
            note=self.notiz.value or "",
            endung=self.endung,
        )
        try:
            # Verschieben im Thread, die Zeile im Event-Loop (die Verbindung gehört ihm)
            await asyncio.to_thread(self.state.anhaenge.dateien_uebernehmen, a, self.datei)
            self.state.anhaenge.eintragen(a)
        except (OSError, sqlite3.Error) as fehler:
            self.melden(f"Nicht gespeichert: {fehler}")
            return
        self.datei = None
        self.fertig = False
        self.page.show_dialog(ft.SnackBar(ft.Text("Audioaufnahme gespeichert")))
        await self.zurueck()

    async def verwerfen(self) -> None:
        """Weg damit — und gleich bereit für einen neuen Versuch."""
        if self.spieler is not None:
            await self.spieler.anhalten()
            self.spieler = None
        self.datei_loeschen()
        self.fertig = False
        self.dauer_s = None
        self.zeit.value = "0:00"
        self.status.value = self.bereit_text()
        self.zeichnen()

    async def zurueck(self) -> None:
        await self.aufraeumen()
        await self.page.push_route(zurueck_ziel(self.page, self.ansicht))

    async def aufraeumen(self) -> None:
        """Beim Verlassen: eine laufende Aufnahme verwerfen, nichts liegen lassen."""
        if self.ticker is not None:
            with contextlib.suppress(Exception):
                self.ticker.cancel()
            self.ticker = None
        if self.rekorder is not None and self.laeuft:
            self.laeuft_seit = None
            self.pausiert = False
            with contextlib.suppress(Exception):
                await self.rekorder.cancel_recording()
        if self.spieler is not None:
            await self.spieler.anhalten()
        self.datei_loeschen()

    def datei_loeschen(self) -> None:
        if self.datei is not None:
            with contextlib.suppress(OSError):
                self.datei.unlink(missing_ok=True)
            self.datei = None

    # -- Darstellung ---------------------------------------------------------------------

    def melden(self, text: str) -> None:
        self.status.value = text
        self.zeichnen()

    def zeichnen(self) -> None:
        self.knoepfe.controls = self._knoepfe()
        self.notiz.visible = self.fertig
        if not self.fertig:
            self.flaeche.content = _mikrofon(self.laeuft_seit is not None)
        for c in (self.knoepfe, self.notiz, self.flaeche, self.zeit, self.rest, self.status):
            with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
                c.update()

    def _knoepfe(self) -> list[ft.Control]:
        if self.fertig:
            return [
                ft.OutlinedButton(
                    "Verwerfen", icon=ft.Icons.DELETE_OUTLINE, on_click=self.verwerfen
                ),
                ft.FilledButton("Behalten", icon=ft.Icons.CHECK, on_click=self.behalten),
            ]
        if self.laeuft:
            return [
                ft.IconButton(
                    ft.Icons.PLAY_CIRCLE if self.pausiert else ft.Icons.PAUSE_CIRCLE,
                    icon_size=56,
                    tooltip="Weiter aufnehmen" if self.pausiert else "Anhalten",
                    on_click=self.pause_umschalten,
                ),
                ft.IconButton(
                    ft.Icons.STOP_CIRCLE,
                    icon_size=56,
                    icon_color=ft.Colors.ERROR,
                    tooltip="Aufnahme beenden",
                    on_click=self.stoppen,
                ),
            ]
        return [
            ft.IconButton(
                ft.Icons.FIBER_MANUAL_RECORD,
                icon_size=72,
                icon_color=ft.Colors.ERROR,
                tooltip="Aufnehmen",
                on_click=self.starten,
            )
        ]


def _hat_inhalt(pfad: Path) -> bool:
    with contextlib.suppress(OSError):
        return pfad.is_file() and pfad.stat().st_size > 0
    return False


def _mikrofon(laeuft: bool) -> ft.Control:
    """Das große Mikrofon in der Mitte — rot, solange aufgenommen wird."""
    return ft.Icon(
        ft.Icons.MIC if laeuft else ft.Icons.MIC_NONE,
        size=96,
        color=ft.Colors.ERROR if laeuft else None,
        opacity=1 if laeuft else 0.45,
    )


def anhang_ton_view(page: Any, state: AppState, route: str, ziel: Ziel) -> ft.View:
    """Die Seite — ``ziel``: woran die Aufnahme hängt."""
    t = _Ton(page, state, ziel)
    t.status.value = t.bereit_text()
    t.zeichnen()

    async def schliessen() -> None:
        await t.zurueck()

    ansicht = ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text("Audio: " + ziel_name(state, ziel)),
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=schliessen),
        ),
        padding=0,
        controls=[
            sicher(
                ft.Column(
                    expand=True,
                    spacing=8,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Container(
                            expand=True,
                            bgcolor=ft.Colors.SURFACE_CONTAINER,
                            padding=16,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Column(
                                tight=True,
                                spacing=8,
                                alignment=ft.MainAxisAlignment.CENTER,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[t.flaeche, t.zeit, t.rest],
                            ),
                        ),
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=16),
                            content=ft.Column(
                                spacing=6,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    t.status,
                                    t.notiz,
                                    t.knoepfe,
                                    ft.Text(
                                        "Bleibt auf diesem Gerät — kein Export, kein Backup. "
                                        "Qualität: Einstellungen → Anhänge.",
                                        size=11,
                                        opacity=0.55,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.Container(height=8),
                                ],
                            ),
                        ),
                    ],
                )
            )
        ],
    )
    t.ansicht = ansicht

    # Auch die Systemtaste räumt auf — der Rekorder liegt außerhalb der Seite und nähme
    # sonst weiter auf (`components/zurueck.py`, gleiche Technik wie beim Hochladen)
    async def zurueck_gedrueckt(_e: object = None) -> None:
        await ansicht.confirm_pop(False)
        await t.zurueck()

    ansicht.can_pop = False
    ansicht.on_confirm_pop = zurueck_gedrueckt
    return ansicht


__all__ = ["anhang_ton_view"]
