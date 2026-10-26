"""`GpsQuelle` über ``flet-geolocator`` — GPS auf dem Handy.

Übersetzt nur: Positionsereignisse → `core.strecke.Punkt` mit der Empfangszeit
auf der monotonen Uhr. Das Intervall gilt auf Android (``interval_duration``);
Genauigkeit „best" heißt dort Fused Location mit hoher Priorität, also GNSS.

**Bei ausgeschaltetem Display** liefert Android weiter Ortungen, solange der
Vordergrunddienst der App mit Typ ``location`` läuft (`flet_ble`,
``hintergrund(..., zweck="gps")``) — er muss starten, während die App sichtbar
ist. Eine eigene Benachrichtigung des Geolocators gibt es deshalb nicht.

**Lebensdauer:** Der Service hängt an ``page.services`` und muss stark
referenziert bleiben (im `AppState`), sonst räumt Flet ihn ab.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import flet as ft
import flet_geolocator as fgl

from trainingsapp.core.strecke import Punkt
from trainingsapp.devices.gps import GpsQuelle

#: Berechtigung im Klartext für die Oberfläche
ERTEILT = "erteilt"
VERWEIGERT = "verweigert"
DAUERHAFT_VERWEIGERT = "dauerhaft verweigert"
STANDORT_AUS = "Standort aus"


class FletGpsQuelle(GpsQuelle):
    name = "Handy-GPS"

    def __init__(self, page: ft.Page) -> None:
        super().__init__()
        self.geo = fgl.Geolocator()
        page.services.append(self.geo)

    async def berechtigung(self, *, anfragen: bool = True) -> str:
        """Standort erlaubt? Fragt bei Bedarf nach (Android-Dialog). Wirft nie."""
        try:
            if not await self.geo.is_location_service_enabled():
                return STANDORT_AUS
            status = await self.geo.get_permission_status()
            if status == fgl.GeolocatorPermissionStatus.DENIED and anfragen:
                status = await self.geo.request_permission()
        except Exception as fehler:
            self.meldung = str(fehler) or type(fehler).__name__
            return VERWEIGERT
        if status in (
            fgl.GeolocatorPermissionStatus.WHILE_IN_USE,
            fgl.GeolocatorPermissionStatus.ALWAYS,
        ):
            return ERTEILT
        if status == fgl.GeolocatorPermissionStatus.DENIED_FOREVER:
            return DAUERHAFT_VERWEIGERT
        return VERWEIGERT

    async def einstellungen_oeffnen(self, *, standort: bool = False) -> None:
        """App-Einstellungen (Berechtigung) bzw. Standort-Einstellungen des Geräts."""
        try:
            if standort:
                await self.geo.open_location_settings()
            else:
                await self.geo.open_app_settings()
        except Exception as fehler:
            self.meldung = str(fehler) or type(fehler).__name__

    async def starten(self, intervall_s: float) -> None:
        if self.laeuft:
            await self.beenden()
        self._sitzung_beginnen()
        self.geo.configuration = fgl.GeolocatorAndroidConfiguration(
            accuracy=fgl.GeolocatorPositionAccuracy.BEST,
            distance_filter=0,
            interval_duration=ft.Duration(milliseconds=round(intervall_s * 1000)),
            # Höhe über dem Meeresspiegel (EGM2008) statt über dem Ellipsoid — wie iOS,
            # wie Strava und Komoot es erwarten (Ben, 26.10.2026, G-F7); in Deutschland
            # rund 45 m Unterschied. Liefert das Gerät keine NMEA-Sätze, bleibt es beim
            # Ellipsoid — der Kopf der Streckendatei nennt den Bezug (`core.bewegung`).
            use_msl_altitude=True,
        )
        # Die Dart-Seite abonniert den Positionsstrom, sobald ein Handler da ist,
        # und abonniert neu, wenn sich die Einstellung ändert.
        self.geo.on_position_change = self._position
        self.geo.on_error = self._fehler
        self.geo.update()

    async def beenden(self) -> None:
        if self.geo.on_position_change is not None:
            self.geo.on_position_change = None
            self.geo.on_error = None
            try:
                self.geo.update()
            except Exception as fehler:  # Seite schon weg
                self.meldung = str(fehler) or type(fehler).__name__
        self._sitzung_beenden()

    # -- Ereignisse aus Dart ------------------------------------------------------

    def _position(self, e: Any) -> None:
        p = e.position
        if p is None or p.latitude is None or p.longitude is None:
            return
        # Android meldet „nicht verfügbar" als 0, iOS als negativ: Ein Tempo zählt nur
        # mit positiver Tempogenauigkeit — sonst stünde der Rechner für immer („steht")
        # und die Strecke bliebe 0 (15.10.2026). Ohne Tempo rechnet er Weg je Zeit.
        tempo = _zahl(p.speed)
        tempo_genau = _zahl(getattr(p, "speed_accuracy", None))
        tempo_gueltig = tempo is not None and tempo >= 0 and bool(tempo_genau and tempo_genau > 0)
        genauigkeit = _zahl(p.accuracy)
        self._einreihen(
            Punkt(
                t=_utc_sekunden(p.timestamp),
                lat=float(p.latitude),
                lon=float(p.longitude),
                genauigkeit_m=genauigkeit if genauigkeit is not None and genauigkeit > 0 else None,
                hoehe_m=_zahl(p.altitude),
                hoehe_genauigkeit_m=_zahl(p.altitude_accuracy),
                tempo_ms=tempo if tempo_gueltig else None,
                richtung_grad=_zahl(p.heading),
                t_empfang=time.monotonic(),
                simuliert=bool(p.mocked),
            )
        )

    def _fehler(self, e: Any) -> None:
        self.meldung = str(getattr(e, "data", "") or "GPS-Fehler")


def _zahl(wert: Any) -> float | None:
    """Zahl oder ``None`` — ob 0 „fehlt" heißt, entscheidet der Aufrufer je Feld."""
    return float(wert) if isinstance(wert, int | float) else None


def _utc_sekunden(zeit: Any) -> float:
    """Zeitstempel der Ortung → s seit 1970; ohne Zeitzone gilt UTC (so liefert es Dart)."""
    if isinstance(zeit, datetime):
        if zeit.tzinfo is None:
            zeit = zeit.replace(tzinfo=UTC)
        return zeit.timestamp()
    if isinstance(zeit, int | float):  # Millisekunden
        return float(zeit) / 1000
    return time.time()


__all__ = [
    "DAUERHAFT_VERWEIGERT",
    "ERTEILT",
    "STANDORT_AUS",
    "VERWEIGERT",
    "FletGpsQuelle",
]
