"""Foto oder Video an einen Eintrag hängen — Route
``<basis>/anhang/aufnehmen/<eintrag>/<foto|video>`` (Ben, 19.10.2026; `docs/plan_anhaenge.md`,
Teil B).

Die Kamera läuft **in der App** (`flet-camera`): So sind die drei Qualitätsstufen
(`core.anhaenge.Qualitaet`) beim Aufnehmen steuerbar, nichts landet in der Galerie des
Telefons, und die Bytes tragen keinen Ortsstempel. Vor dem Start eines Videos wird ein
Foto geschossen — das ist das Frontbild (`vorschau`), ohne Thumbnail-Bibliothek.

Ablauf: Vorschau vollflächig, unten Auslöser bzw. Aufnahme/Stopp mit laufender Zeit und
Restzeit bis zur Höchstdauer, Kamera wechseln (Front ist für Übungen vor dem Handy die
Regel), Qualitätsstufe als Text. Nach der Aufnahme: Vorschau, Notizzeile, „Behalten“ /
„Verwerfen“. „Behalten“ schreibt über `AnhangRepo.anlegen` in einem Thread (die Bytes
sind groß) und geht zurück zur Ansicht darunter.

Am Rechner gibt es keine Kamera-Erweiterung (`Camera` wirft dort beim Anzeigen) — dort
steht „Datei wählen“: Ein Bild oder Video vom Rechner, **unverkleinert**, nur zum Prüfen
des Ablaufs in der Entwicklung. Der Galerie-Import am Handy braucht eine eigene
Erweiterung mit Verkleinern (Plan, Abschnitt F) und ist bewusst nicht gebaut.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import (
    BILD,
    VIDEO,
    Anhang,
    Qualitaet,
    dauer_text,
    groesse_text,
    neuer_anhang,
)
from trainingsapp.core.models import SessionEntry, jetzt
from trainingsapp.data.anhaenge import qualitaet_lesen, video_max_s
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_ziel
from trainingsapp.ui.state import AppState

#: Routenteile
ANHANG, AUFNEHMEN = "anhang", "aufnehmen"
ARTEN = {"foto": BILD, "video": VIDEO}


def aufnahme_route(basis: str, eintrag_id: str, art: str) -> str:
    """``<basis>/anhang/aufnehmen/<eintrag>/<foto|video>`` — ``basis`` ``""`` oder ``/`` = Heute.

    >>> aufnahme_route("/", "e1", BILD), aufnahme_route("/tag/2026-10-20", "e1", VIDEO)
    ('/anhang/aufnehmen/e1/foto', '/tag/2026-10-20/anhang/aufnehmen/e1/video')
    """
    wort = "video" if art == VIDEO else "foto"
    return f"{basis.rstrip('/')}/{ANHANG}/{AUFNEHMEN}/{eintrag_id}/{wort}"


def _kamera_moeglich(page: Any) -> bool:
    """Nur Android, iOS und Web haben die Kamera-Erweiterung (flet-camera `before_update`)."""
    plattform = getattr(page, "platform", None)
    return bool(getattr(page, "web", False)) or plattform in (
        ft.PagePlatform.ANDROID,
        ft.PagePlatform.IOS,
    )


class _Aufnahme:
    """Zustand der Seite: Kamera, laufende Aufnahme, Ergebnis."""

    def __init__(self, page: Any, state: AppState, eintrag: SessionEntry, art: str) -> None:
        self.page, self.state, self.eintrag, self.art = page, state, eintrag, art
        self.qualitaet: Qualitaet = qualitaet_lesen(state.einstellungen)
        self.max_s: int = video_max_s(state.einstellungen)
        self.kamera: Any = None  # flet_camera.Camera
        self.kameras: list[Any] = []
        self.kamera_index = 0
        self.bereit = False
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
            )
        except Exception as fehler:
            self.melden(f"Kamera lässt sich nicht öffnen: {fehler}")
            return
        with contextlib.suppress(Exception):
            from flet_camera import FlashMode

            await self.kamera.set_flash_mode(FlashMode.OFF)
        self.bereit = True
        self.status.value = f"{self.qualitaet.label} · {self._richtung()}"
        self.zeichnen()

    def _zustand(self, e: Any) -> None:
        if getattr(e, "has_error", False):
            self.melden(f"Kamera: {getattr(e, 'error_description', '') or 'Fehler'}")

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
        self.status.value = f"{self.qualitaet.label} · {self._richtung()}"
        self.zeichnen()

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
            self.eintrag.id,
            self.art,
            self.qualitaet,
            jetzt(),
            dauer_s=self.dauer_s,
            note=self.notiz.value or "",
        )
        daten, frontbild = self.daten, self.frontbild
        try:
            await asyncio.to_thread(self.state.anhaenge.anlegen, a, daten, frontbild)
        except OSError as fehler:
            self.melden(f"Nicht gespeichert: {fehler}")
            return
        self.daten = None
        self.page.show_dialog(
            ft.SnackBar(ft.Text("Foto gespeichert" if self.art == BILD else "Video gespeichert"))
        )
        await self.zurueck()

    async def verwerfen(self) -> None:
        self.daten, self.frontbild, self.dauer_s = None, None, None
        if self.kamera is not None and self.bereit:
            self.flaeche.content = self.kamera
            self.status.value = f"{self.qualitaet.label} · {self._richtung()}"
            self.zeichnen()
        else:
            await self.zurueck()

    async def zurueck(self) -> None:
        await self.aufraeumen()
        await self.page.push_route(zurueck_ziel(self.page, self.ansicht))

    async def aufraeumen(self) -> None:
        """Eine laufende Aufnahme beim Verlassen verwerfen (Zurück, Wegwischen)."""
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
        self.notiz.visible = self.daten is not None
        for c in (self.knoepfe, self.status, self.zeit, self.notiz, self.flaeche):
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
                    on_click=self.foto,
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
                on_click=self.video_start,
                disabled=not self.bereit,
            ),
            ft.Container(width=48),
        ]


def anhang_aufnahme_view(
    page: Any, state: AppState, route: str, eintrag: SessionEntry, art: str
) -> ft.View:
    """Die Seite. ``art``: `BILD` oder `VIDEO`."""
    uebung = state.uebungen.laden(eintrag.exercise_id, mit_geloeschten=True)
    a = _Aufnahme(page, state, eintrag, art)
    titel = ("Foto: " if art == BILD else "Video: ") + (uebung.name if uebung else "Übung")
    hinweis = (
        f"Höchstens {dauer_text(a.max_s)} min · Qualität in Einstellungen → Anhänge"
        if art == VIDEO
        else "Qualität in Einstellungen → Anhänge"
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
                            alignment=ft.Alignment.CENTER,
                            content=a.flaeche,
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


__all__ = ["ANHANG", "ARTEN", "AUFNEHMEN", "anhang_aufnahme_view", "aufnahme_route"]
