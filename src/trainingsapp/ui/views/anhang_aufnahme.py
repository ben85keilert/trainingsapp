"""Foto oder Video an einen Eintrag hängen — Route
``<basis>/anhang/aufnehmen/<ziel>/<foto|video>`` (Ben, 19.10.2026; `docs/plan_anhaenge.md`,
Teil B). ``<ziel>`` ist die ID des Eintrags oder, seit 22.10.2026, ``tag/<datum>`` für die
Notiz zum Tag (`core.anhaenge.Ziel`); ``…/audio`` führt zum Rekorder (`views/anhang_ton.py`).

Die Kamera läuft **in der App** (`flet-camera`): So sind die drei Qualitätsstufen
(`core.anhaenge.Qualitaet`) beim Aufnehmen steuerbar, nichts landet in der Galerie des
Telefons, und die Bytes tragen keinen Ortsstempel. Vor dem Start eines Videos wird ein
Foto geschossen — das ist das Frontbild (`vorschau`), ohne Thumbnail-Bibliothek.

Ablauf: Vorschau vollflächig, unten Auslöser bzw. Aufnahme/Stopp mit laufender Zeit und
Restzeit bis zur Höchstdauer, Kamera wechseln (Front ist für Übungen vor dem Handy die
Regel). Oben im Bild (Ben, 21.10.2026, P73, Skizzen H1/H2: „Timer, Qualität direkt an der
Kamera, Blitz … nicht zu viel“): Blitz (Foto aus · automatisch · an, Video Licht), Timer
(ein Tipp: aus → 1 → 3 → 5 → 10 s; dann zählt die Mitte groß herunter, je Sekunde ein Ton,
„Abbrechen“ hält an) und die Qualität dieser Aufnahme (die Vorgabe bleibt in den
Einstellungen). Mehr nicht — für Profiaufnahmen und lange Videos ist die Kamera des
Telefons da. Nach der Aufnahme: Vorschau, Notizzeile, „Behalten“ / „Verwerfen“. Die
Vorschau liegt **über** der Kamera (`Camera.content`), nie an ihrer Stelle — ein aus dem
Baum genommenes Kamera-Control verliert seinen Controller.
„Behalten“ schreibt die Dateien in einem Thread (die Bytes sind groß,
`AnhangRepo.dateien_schreiben`), die Zeile danach im Event-Loop (`AnhangRepo.eintragen` —
die SQLite-Verbindung darf den Thread nicht wechseln) und geht zurück zur Ansicht darunter.

Am Rechner gibt es keine Kamera-Erweiterung (`Camera` wirft dort beim Anzeigen) — dort
steht „Datei wählen“: Ein Bild oder Video vom Rechner, **unverkleinert**, nur zum Prüfen
des Ablaufs in der Entwicklung. Am Handy kommt ein vorhandenes Foto oder Video über
„Hochladen“ (`views/anhang_hochladen.py`, Erweiterung `flet_hochladen`: verkleinert, ohne
Ortsangabe; Plan, Abschnitt F).
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import time
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import (
    AUDIO,
    BILD,
    VIDEO,
    Anhang,
    Qualitaet,
    Ziel,
    blitz_text,
    blitz_weiter,
    countdown_text,
    dauer_text,
    groesse_text,
    neuer_anhang,
    timer_text,
    timer_weiter,
)
from trainingsapp.core.models import jetzt
from trainingsapp.core.timer import COUNTDOWN
from trainingsapp.data.anhaenge import qualitaet_lesen, video_max_s
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_ziel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.timer_takt import ton_spielen

#: Routenteile
ANHANG, AUFNEHMEN = "anhang", "aufnehmen"
ARTEN = {"foto": BILD, "video": VIDEO, "audio": AUDIO}
WORT = {art: wort for wort, art in ARTEN.items()}
#: Takt des Selbstauslösers (s) — eine Zahl, ein Ton
COUNTDOWN_TAKT_S = 1.0


def aufnahme_route(basis: str, ziel: Ziel | str, art: str) -> str:
    """``<basis>/anhang/aufnehmen/<ziel>/<foto|video|audio>`` — ``basis`` ``""`` oder ``/`` =
    Heute; ``ziel`` eine Eintrags-ID oder ein `Ziel` (auch der Tag).

    >>> aufnahme_route("/", "e1", BILD), aufnahme_route("/tag/2026-10-20", "e1", VIDEO)
    ('/anhang/aufnehmen/e1/foto', '/tag/2026-10-20/anhang/aufnehmen/e1/video')
    >>> from datetime import date
    >>> aufnahme_route("/", Ziel.fuer_tag("p", date(2026, 10, 22)), AUDIO)
    '/anhang/aufnehmen/tag/2026-10-22/audio'
    """
    teil = ziel.teil if isinstance(ziel, Ziel) else ziel
    return f"{basis.rstrip('/')}/{ANHANG}/{AUFNEHMEN}/{teil}/{WORT.get(art, 'foto')}"


def ziel_name(state: AppState, ziel: Ziel) -> str:
    """Wofür aufgenommen wird — der Name der Übung des Eintrags, beim Tag „Zum Tag · 22.10.“."""
    if ziel.zum_tag is not None:
        return f"Zum Tag · {ziel.zum_tag:%d.%m.}"
    eintrag = state.sitzungen.eintrag_laden(ziel.eintrag_id) if ziel.eintrag_id else None
    uebung = (
        state.uebungen.laden(eintrag.exercise_id, mit_geloeschten=True)
        if eintrag is not None
        else None
    )
    return uebung.name if uebung is not None else "Übung"


def _kamera_moeglich(page: Any) -> bool:
    """Nur Android, iOS und Web haben die Kamera-Erweiterung (flet-camera `before_update`)."""
    plattform = getattr(page, "platform", None)
    return bool(getattr(page, "web", False)) or plattform in (
        ft.PagePlatform.ANDROID,
        ft.PagePlatform.IOS,
    )


class _Aufnahme:
    """Zustand der Seite: Kamera, laufende Aufnahme, Ergebnis."""

    def __init__(self, page: Any, state: AppState, ziel: Ziel, art: str) -> None:
        self.page, self.state, self.ziel, self.art = page, state, ziel, art
        self.qualitaet: Qualitaet = qualitaet_lesen(state.einstellungen)
        self.max_s: int = video_max_s(state.einstellungen)
        self.kamera: Any = None  # flet_camera.Camera
        self.kameras: list[Any] = []
        self.kamera_index = 0
        self.bereit = False
        #: Der zuletzt gemeldete Fehler der Kamera — er steht in jedem weiteren Zustand
        self.letzter_fehler: str | None = None
        self.laeuft_seit: float | None = None
        #: Ergebnis: Daten, Frontbild (Video), Dauer
        self.daten: bytes | None = None
        self.frontbild: bytes | None = None
        self.dauer_s: float | None = None
        self.notiz = ft.TextField(
            label="Notiz (optional)", hint_text="z. B. links, Seitenansicht", dense=True
        )
        self.status = ft.Text("", size=13, opacity=0.75)
        self.zeit = ft.Text("", size=28, weight=ft.FontWeight.W_600)
        self.flaeche = ft.Container(expand=True, alignment=ft.Alignment.CENTER)
        self.knoepfe = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=16)
        self.ticker: asyncio.Task[None] | None = None
        #: Oben im Bild (P73): Blitz (flet-camera ``FlashMode`` als Text) und Selbstauslöser
        #: (s) — nur für diese Seite; die Qualität oben gilt nur für diese Aufnahme
        self.blitz = "off"
        self.timer_s = 0
        self.leiste = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=8)
        #: Countdown des Selbstauslösers: Sekunden bis zum Auslösen, groß in der Mitte
        self.countdown_rest: int | None = None
        self.countdown_aufgabe: Any = None
        self.gross = ft.Text("", size=120, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE)
        #: die Seite, sobald sie gebaut ist (für Zurück)
        self.ansicht: Any = None

    # -- Kamera --------------------------------------------------------------------------

    async def kamera_starten(self) -> None:
        """Kamera anlegen, Berechtigung holen, mit der eingestellten Qualität öffnen."""
        try:
            from flet_camera import Camera, ResolutionPreset
        except ImportError:
            self.melden("Kamera-Erweiterung fehlt in diesem Build.")
            return
        try:
            from flet_permission_handler import Permission, PermissionHandler, PermissionStatus

            ph = PermissionHandler()
            self.page.services.append(ph)
            noetig = [Permission.CAMERA] + ([Permission.MICROPHONE] if self.art == VIDEO else [])
            for p in noetig:
                status = await ph.request(p)
                if status not in (PermissionStatus.GRANTED, PermissionStatus.LIMITED, None):
                    self.melden(
                        "Ohne Kamera-Berechtigung geht es nicht — in den Systemeinstellungen "
                        "der App erlauben."
                    )
                    return
        except ImportError:
            pass  # ohne Handler fragt das Kamera-Plugin selbst
        self.kamera = Camera(expand=True, on_state_change=self._zustand)
        self.flaeche.content = self.kamera
        self.flaeche.update()
        try:
            self.kameras = await self.kamera.get_available_cameras()
        except Exception as fehler:
            self.melden(f"Keine Kamera gefunden: {fehler}")
            return
        if not self.kameras:
            self.melden("Keine Kamera gefunden.")
            return
        # Front zuerst — Übungen vor dem aufgestellten Handy sind die Regel
        self.kamera_index = next(
            (i for i, k in enumerate(self.kameras) if str(k.lens_direction.value) == "front"),
            0,
        )
        await self._oeffnen(ResolutionPreset(self.qualitaet.preset))

    async def _oeffnen(self, preset: Any) -> None:
        assert self.kamera is not None
        try:
            await self.kamera.initialize(
                self.kameras[self.kamera_index],
                preset,
                enable_audio=self.art == VIDEO,
                video_bitrate=self.qualitaet.video_bitrate,
                audio_bitrate=self.qualitaet.audio_bitrate,
            )
        except Exception as fehler:
            self.melden(f"Kamera lässt sich nicht öffnen: {fehler}")
            return
        await self._blitz_setzen()  # ein neuer Controller beginnt mit seinem eigenen Blitz
        self.bereit = True
        self.status.value = self.kamera_text()
        self.zeichnen()

    async def _blitz_setzen(self) -> bool:
        """Den gewählten Blitz an die Kamera geben — ``False``, wenn sie keinen hat."""
        if self.kamera is None:
            return False
        try:
            from flet_camera import FlashMode

            await self.kamera.set_flash_mode(FlashMode(self.blitz))
        except Exception:
            return False
        return True

    def kamera_text(self) -> str:
        """„Mittel · 720p · Frontkamera · Timer 3 s“ — was gerade eingestellt ist."""
        teile = [self.qualitaet.label, self._richtung()]
        if self.timer_s:
            teile.append(f"Timer {self.timer_s} s")
        return " · ".join(t for t in teile if t)

    def _zustand(self, e: Any) -> None:
        """Ein Fehler im Zustand der Kamera. flet-camera trägt ihn in **jedem** weiteren
        Zustand mit (``errorDescription`` bleibt stehen) — darum zählt nur ein neuer, und
        die Kamera bleibt bereit, solange sie geöffnet ist. Blitzfehler (keine Lampe an
        dieser Kamera) meldet `blitz_tippen` selbst. Bis 21.10.2026 machte schon das
        „Blitz aus“ beim Öffnen einer Kamera ohne Lampe („torchModeNotSupported“) jeden
        späteren Zustand zum Fehler: Auslöser gesperrt, „Verwerfen“ verließ die Seite."""
        if not getattr(e, "has_error", False):
            return
        text = str(getattr(e, "error_description", "") or "Fehler")
        if text == self.letzter_fehler:
            return
        self.letzter_fehler = text
        if "torch" in text.lower() or "flash" in text.lower():
            return
        if getattr(e, "is_initialized", True):
            self.status.value = f"Kamera: {text}"
            self.zeichnen()
        else:
            self.melden(f"Kamera: {text}")

    def _richtung(self) -> str:
        if not self.kameras:
            return ""
        wert = str(self.kameras[self.kamera_index].lens_direction.value)
        return {"front": "Frontkamera", "back": "Rückkamera"}.get(wert, "Kamera")

    async def wechseln(self) -> None:
        if self.kamera is None or len(self.kameras) < 2 or self.laeuft_seit is not None:
            return
        self.kamera_index = (self.kamera_index + 1) % len(self.kameras)
        try:
            await self.kamera.set_description(self.kameras[self.kamera_index])
        except Exception as fehler:
            self.melden(f"Kamera wechseln: {fehler}")
            return
        await self._blitz_setzen()
        self.status.value = self.kamera_text()
        self.zeichnen()

    # -- Oben im Bild: Blitz, Timer, Qualität (P73, Skizze H1) ---------------------------

    async def blitz_tippen(self) -> None:
        """Blitz weiterschalten: Foto aus → automatisch → an, Video Licht aus ↔ an."""
        if self.kamera is None or not self.bereit:
            return
        self.blitz = blitz_weiter(self.art, self.blitz)
        if await self._blitz_setzen():
            self.status.value = self.kamera_text()
        else:  # die Frontkamera hat meist keinen
            self.blitz = "off"
            self.status.value = f"{self.kamera_text()} · ohne Blitz"
        self.zeichnen()

    def timer_tippen(self) -> None:
        """Selbstauslöser weiterschalten: aus → 1 → 3 → 5 → 10 s → aus."""
        self.timer_s = timer_weiter(self.timer_s)
        self.status.value = self.kamera_text()
        self.zeichnen()

    def qualitaet_waehler(self, q: Qualitaet) -> Callable[[], Awaitable[None]]:
        async def handler() -> None:
            await self.qualitaet_setzen(q)

        return handler

    async def qualitaet_setzen(self, q: Qualitaet) -> None:
        """Die Qualität dieser Aufnahme: Die Kamera öffnet mit dem anderen Preset neu
        (flet-camera tauscht den Controller); die Vorgabe in den Einstellungen bleibt."""
        if (
            q == self.qualitaet
            or self.kamera is None
            or not self.kameras
            or self.laeuft_seit is not None
            or self.countdown_rest is not None
        ):
            return
        from flet_camera import ResolutionPreset

        self.qualitaet = q
        self.bereit = False
        self.status.value = "Kamera wird neu geöffnet …"
        self.zeichnen()
        await self._oeffnen(ResolutionPreset(q.preset))

    # -- Auslösen, mit Selbstauslöser (Skizze H2) ----------------------------------------

    async def ausloesen(self) -> None:
        """Der Auslöser: gleich — oder nach dem Countdown des Selbstauslösers."""
        if (
            self.kamera is None
            or not self.bereit
            or self.countdown_rest is not None
            or self.laeuft_seit is not None
        ):
            return
        if self.timer_s <= 0:
            await self._jetzt_ausloesen()
            return
        self.countdown_rest = self.timer_s
        self.zeichnen()  # gleich „Abbrechen“ statt des Auslösers
        self.countdown_aufgabe = self.page.run_task(self._countdown)

    async def _jetzt_ausloesen(self) -> None:
        await (self.foto() if self.art == BILD else self.video_start())

    async def _countdown(self) -> None:
        """Je Sekunde die Zahl groß in der Mitte und ein kurzer Ton (der Countdown-Ton des
        Timers, mit dessen Lautstärke) — danach Foto bzw. Videostart."""
        for rest in range(self.timer_s, 0, -1):
            if self.countdown_rest is None:  # abgebrochen
                return
            self.countdown_rest = rest
            self.gross.value = str(rest)
            self.status.value = countdown_text(self.art, rest, self.max_s)
            self.zeichnen()
            await ton_spielen(self.state, COUNTDOWN)
            await asyncio.sleep(COUNTDOWN_TAKT_S)
        if self.countdown_rest is None:
            return
        self.countdown_ende()
        await self._jetzt_ausloesen()

    def countdown_ende(self) -> None:
        self.countdown_rest = None
        self.countdown_aufgabe = None
        self.gross.value = ""
        self.status.value = self.kamera_text()
        self.zeichnen()

    def abbrechen(self) -> None:
        """„Abbrechen“ hält den Countdown an — aufgenommen wird nichts."""
        aufgabe = self.countdown_aufgabe
        self.countdown_ende()
        if aufgabe is not None:
            with contextlib.suppress(Exception):
                aufgabe.cancel()

    # -- Aufnehmen -----------------------------------------------------------------------

    async def foto(self) -> None:
        if self.kamera is None or not self.bereit:
            return
        try:
            self.daten = await self.kamera.take_picture()
        except Exception as fehler:
            self.melden(f"Foto fehlgeschlagen: {fehler}")
            return
        self.ergebnis_zeigen()

    async def video_start(self) -> None:
        if self.kamera is None or not self.bereit or self.laeuft_seit is not None:
            return
        try:
            # Das Frontbild: ein Foto direkt vor dem Start
            self.frontbild = await self.kamera.take_picture()
            with contextlib.suppress(Exception):
                await self.kamera.prepare_for_video_recording()
            await self.kamera.start_video_recording()
        except Exception as fehler:
            self.melden(f"Video fehlgeschlagen: {fehler}")
            return
        self.laeuft_seit = time.monotonic()
        self.zeichnen()
        self.ticker = self.page.run_task(self._ticken)

    async def _ticken(self) -> None:
        while self.laeuft_seit is not None:
            vergangen = time.monotonic() - self.laeuft_seit
            self.zeit.value = f"{dauer_text(vergangen)} · noch {dauer_text(self.max_s - vergangen)}"
            with contextlib.suppress(Exception):
                self.zeit.update()
            if vergangen >= self.max_s:
                await self.video_stopp()
                return
            await asyncio.sleep(0.5)

    async def video_stopp(self) -> None:
        if self.kamera is None or self.laeuft_seit is None:
            return
        self.dauer_s = time.monotonic() - self.laeuft_seit
        self.laeuft_seit = None
        try:
            self.daten = await self.kamera.stop_video_recording()
        except Exception as fehler:
            self.melden(f"Video fehlgeschlagen: {fehler}")
            return
        self.ergebnis_zeigen()

    async def datei_waehlen(self) -> None:
        """Nur am Rechner: ein Bild oder Video von der Platte — unverkleinert, zum Prüfen."""
        endungen = ["jpg", "jpeg"] if self.art == BILD else ["mp4"]
        try:
            dateien = await ft.FilePicker().pick_files(
                dialog_title="Foto wählen" if self.art == BILD else "Video wählen",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=endungen,
                with_data=False,
            )
        except Exception as fehler:
            self.melden(f"Dateiauswahl: {fehler}")
            return
        if not dateien or not dateien[0].path:
            return
        from pathlib import Path

        pfad = Path(dateien[0].path)
        self.daten = await asyncio.to_thread(pfad.read_bytes)
        if self.art == VIDEO:
            self.frontbild = None  # kein Frontbild ohne Kamera — die Kachel zeigt „fehlt“
            self.dauer_s = None
        self.ergebnis_zeigen()

    # -- Ergebnis ------------------------------------------------------------------------

    def ergebnis_zeigen(self) -> None:
        assert self.daten is not None
        bild = self.daten if self.art == BILD else self.frontbild
        vorschau: ft.Control = (
            ft.Image(src=bild, fit=ft.BoxFit.CONTAIN, expand=True)
            if bild
            else ft.Icon(ft.Icons.VIDEOCAM, size=64, opacity=0.5)
        )
        if self.kamera is not None:
            # Über die Kamera legen, nicht an ihre Stelle: Aus dem Baum genommen gibt das
            # Plugin den Controller frei, und nach „Verwerfen“ war die Kamera tot (Ben,
            # 21.10.2026 — flet-camera `dispose` → „Camera is not initialized“)
            self.kamera.content = ft.Container(
                expand=True,
                bgcolor=ft.Colors.BLACK,
                alignment=ft.Alignment.CENTER,
                content=vorschau,
            )
        else:
            self.flaeche.content = vorschau
        teile = [groesse_text(len(self.daten)), self.qualitaet.label]
        if self.art == VIDEO and self.dauer_s is not None:
            teile.insert(0, dauer_text(self.dauer_s))
        self.status.value = " · ".join(teile)
        self.zeit.value = ""
        self.zeichnen()

    async def behalten(self) -> None:
        if self.daten is None:
            return
        a: Anhang = neuer_anhang(
            self.ziel,
            self.art,
            self.qualitaet,
            jetzt(),
            dauer_s=self.dauer_s,
            note=self.notiz.value or "",
        )
        daten, frontbild = self.daten, self.frontbild
        try:
            # Nur die Bytes im Thread — die SQLite-Verbindung gehört dem Event-Loop
            await asyncio.to_thread(self.state.anhaenge.dateien_schreiben, a, daten, frontbild)
            self.state.anhaenge.eintragen(a)
        except (OSError, sqlite3.Error) as fehler:
            self.melden(f"Nicht gespeichert: {fehler}")
            return
        self.daten = None
        self.page.show_dialog(
            ft.SnackBar(ft.Text("Foto gespeichert" if self.art == BILD else "Video gespeichert"))
        )
        await self.zurueck()

    async def verwerfen(self) -> None:
        """Zurück zur Kamera — sie lief unter dem Ergebnis weiter, ein neuer Versuch geht
        sofort."""
        self.daten, self.frontbild, self.dauer_s = None, None, None
        if self.kamera is not None and self.bereit:
            self.kamera.content = None
            self.status.value = self.kamera_text()
            self.zeichnen()
        else:
            await self.zurueck()

    async def zurueck(self) -> None:
        await self.aufraeumen()
        await self.page.push_route(zurueck_ziel(self.page, self.ansicht))

    async def aufraeumen(self) -> None:
        """Eine laufende Aufnahme beim Verlassen verwerfen (Zurück, Wegwischen)."""
        if self.countdown_rest is not None:
            self.abbrechen()
        if self.ticker is not None:
            self.ticker.cancel()
            self.ticker = None
        if self.kamera is not None and self.laeuft_seit is not None:
            self.laeuft_seit = None
            with contextlib.suppress(Exception):
                await self.kamera.stop_video_recording()

    # -- Darstellung ---------------------------------------------------------------------

    def melden(self, text: str) -> None:
        self.status.value = text
        self.bereit = False
        self.zeichnen()

    def zeichnen(self) -> None:
        self.knoepfe.controls = self._knoepfe()
        self.leiste.controls = self._leiste()
        self.notiz.visible = self.daten is not None
        for c in (
            self.knoepfe,
            self.leiste,
            self.gross,
            self.status,
            self.zeit,
            self.notiz,
            self.flaeche,
        ):
            with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
                c.update()

    def _knoepfe(self) -> list[ft.Control]:
        if self.daten is not None:
            return [
                ft.OutlinedButton(
                    "Verwerfen", icon=ft.Icons.DELETE_OUTLINE, on_click=self.verwerfen
                ),
                ft.FilledButton("Behalten", icon=ft.Icons.CHECK, on_click=self.behalten),
            ]
        if not _kamera_moeglich(self.page):
            return [
                ft.FilledButton(
                    "Datei wählen", icon=ft.Icons.FOLDER_OPEN, on_click=self.datei_waehlen
                )
            ]
        if self.countdown_rest is not None:
            return [ft.OutlinedButton("Abbrechen", icon=ft.Icons.CLOSE, on_click=self.abbrechen)]
        wechsel = ft.IconButton(
            ft.Icons.FLIP_CAMERA_ANDROID,
            tooltip="Kamera wechseln",
            on_click=self.wechseln,
            disabled=len(self.kameras) < 2 or self.laeuft_seit is not None,
        )
        if self.art == BILD:
            return [
                wechsel,
                ft.IconButton(
                    ft.Icons.CAMERA,
                    icon_size=56,
                    tooltip="Foto aufnehmen",
                    on_click=self.ausloesen,
                    disabled=not self.bereit,
                ),
                ft.Container(width=48),
            ]
        if self.laeuft_seit is not None:
            return [
                ft.IconButton(
                    ft.Icons.STOP_CIRCLE,
                    icon_size=56,
                    icon_color=ft.Colors.ERROR,
                    tooltip="Aufnahme beenden",
                    on_click=self.video_stopp,
                )
            ]
        return [
            wechsel,
            ft.IconButton(
                ft.Icons.FIBER_MANUAL_RECORD,
                icon_size=56,
                icon_color=ft.Colors.ERROR,
                tooltip="Video aufnehmen",
                on_click=self.ausloesen,
                disabled=not self.bereit,
            ),
            ft.Container(width=48),
        ]

    def _leiste(self) -> list[ft.Control]:
        """Oben im Bild (Skizze H1): Blitz, Timer, Qualität — nur mit Kamera und solange
        kein Ergebnis dasteht. Während der Aufnahme bleibt nur das Licht schaltbar."""
        if self.kamera is None or not self.kameras or self.daten is not None:
            return []
        frei = self.bereit and self.laeuft_seit is None and self.countdown_rest is None
        symbol = {
            "auto": ft.Icons.FLASH_AUTO,
            "always": ft.Icons.FLASH_ON,
            "torch": ft.Icons.FLASHLIGHT_ON,
        }.get(self.blitz, ft.Icons.FLASHLIGHT_OFF if self.art == VIDEO else ft.Icons.FLASH_OFF)
        return [
            _schalter(
                symbol,
                blitz_text(self.art, self.blitz),
                "Licht" if self.art == VIDEO else "Blitz",
                self.blitz_tippen,
                aus=not self.bereit or self.countdown_rest is not None,
            ),
            _schalter(
                ft.Icons.TIMER if self.timer_s else ft.Icons.TIMER_OFF,
                timer_text(self.timer_s),
                "Selbstauslöser",
                self.timer_tippen,
                aus=not frei,
            ),
            ft.PopupMenuButton(
                tooltip="Qualität dieser Aufnahme",
                disabled=not frei,
                content=_schalter(ft.Icons.HD, self.qualitaet.label, None, None, aus=not frei),
                items=[
                    ft.PopupMenuItem(
                        content=q.label,
                        checked=q == self.qualitaet,
                        on_click=self.qualitaet_waehler(q),
                    )
                    for q in Qualitaet
                ],
            ),
        ]


def _schalter(
    symbol: Any, text: str, tooltip: str | None, on_click: Any, *, aus: bool = False
) -> ft.Control:
    """Ein Knopf oben im Bild: hell auf dunklem, halbdurchsichtigem Grund."""
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=18,
        bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
        opacity=0.5 if aus else 1.0,
        tooltip=tooltip,
        ink=on_click is not None,
        on_click=None if aus else on_click,
        content=ft.Row(
            tight=True,
            spacing=6,
            controls=[
                ft.Icon(symbol, size=18, color=ft.Colors.WHITE),
                ft.Text(text, size=13, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
            ],
        ),
    )


def anhang_aufnahme_view(page: Any, state: AppState, route: str, ziel: Ziel, art: str) -> ft.View:
    """Die Seite. ``art``: `BILD` oder `VIDEO`; ``ziel``: woran die Aufnahme hängt."""
    a = _Aufnahme(page, state, ziel, art)
    titel = ("Foto: " if art == BILD else "Video: ") + ziel_name(state, ziel)
    hinweis = (
        f"Höchstens {dauer_text(a.max_s)} min · Vorgabe der Qualität: Einstellungen → Anhänge"
        if art == VIDEO
        else "Vorgabe der Qualität: Einstellungen → Anhänge"
    )
    if _kamera_moeglich(page):
        a.status.value = "Kamera wird geöffnet …"
        a.flaeche.content = ft.ProgressRing()
        page.run_task(a.kamera_starten)
    else:
        a.status.value = (
            "Am Rechner gibt es keine Kamera in der App — zum Prüfen eine Datei wählen "
            "(unverkleinert)."
        )
    a.zeichnen()

    async def schliessen() -> None:
        await a.zurueck()

    ansicht = ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(titel),
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
                            bgcolor=ft.Colors.BLACK,
                            # Über dem Bild: der Countdown groß in der Mitte, oben die Leiste
                            content=ft.Stack(
                                expand=True,
                                fit=ft.StackFit.EXPAND,
                                controls=[
                                    a.flaeche,
                                    ft.Container(alignment=ft.Alignment.CENTER, content=a.gross),
                                    ft.Container(top=10, left=8, right=8, content=a.leiste),
                                ],
                            ),
                        ),
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=16),
                            content=ft.Column(
                                spacing=6,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    a.zeit,
                                    a.status,
                                    a.notiz,
                                    a.knoepfe,
                                    ft.Text(hinweis, size=11, opacity=0.55),
                                    ft.Container(height=8),
                                ],
                            ),
                        ),
                    ],
                )
            )
        ],
    )

    # Zurück über die Systemtaste: Flutter nimmt die Seite samt Kamera weg, eine laufende
    # Aufnahme ist damit verworfen (H19: die Engine lebt weiter)
    a.ansicht = ansicht
    return ansicht


__all__ = [
    "ANHANG",
    "ARTEN",
    "AUFNEHMEN",
    "WORT",
    "anhang_aufnahme_view",
    "aufnahme_route",
    "ziel_name",
]
