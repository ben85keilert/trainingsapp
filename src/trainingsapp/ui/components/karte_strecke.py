"""Karte mit Strecke — OpenStreetMap-Kacheln nach deren Nutzungsregeln.

- eigener User-Agent (Paketname der App); mit dem Vorgabewert ``unknown``
  sperrt der OSM-Server
- Namensnennung sichtbar und antippbar („© OpenStreetMap-Mitwirkende" →
  Lizenzseite)
- **Zwischenspeicher** macht flutter_map selbst (seit 8.2, nach den
  Cache-Angaben des Servers, im Cache-Ordner der App): Ohne Netz zeigt die
  Karte, was schon einmal geladen war. Der Speicher kann vom System geleert
  werden, wenn das Handy Platz braucht.
- **kein** Gebiets-Download — verbietet OSM ausdrücklich
  (`docs/plan_gps.md`, Abschnitt 5)
"""

from __future__ import annotations

from collections.abc import Sequence

import flet as ft
import flet_map as fm

from trainingsapp.core.strecke import Punkt

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_LIZENZ = "https://www.openstreetmap.org/copyright"
#: Kennung gegenüber dem Kachelserver (OSM verlangt eine eindeutige)
USER_AGENT_PAKET = "de.praxisebert.trainingsassistent"

LINIE = ft.Colors.BLUE_700
POSITION = ft.Colors.BLUE_600


def osm_ebenen() -> list[fm.MapLayer]:
    """Kachelschicht und Namensnennung — die Grundlage jeder Karte der App."""

    async def lizenz() -> None:
        await ft.UrlLauncher().launch_url(OSM_LIZENZ)

    return [
        fm.TileLayer(
            url_template=OSM_URL,
            user_agent_package_name=USER_AGENT_PAKET,
            max_native_zoom=19,
        ),
        fm.SimpleAttribution(
            text="OpenStreetMap-Mitwirkende",  # „flutter_map | ©" setzt flutter_map davor
            alignment=ft.Alignment.BOTTOM_RIGHT,
            text_style=ft.TextStyle(size=11, color=ft.Colors.with_opacity(0.87, ft.Colors.BLACK)),
            bgcolor=ft.Colors.with_opacity(0.75, ft.Colors.WHITE),
            on_click=lizenz,
        ),
    ]


def _ort(p: Punkt) -> fm.MapLatitudeLongitude:
    return fm.MapLatitudeLongitude(p.lat, p.lon)


class StreckenKarte:
    """Karte mit Linie, Position und Genauigkeitskreis.

    `nachziehen` hängt neue Punkte an die vorhandene Linie an, statt sie neu
    zu bauen — bei einer Stunde mit einer Ortung je Sekunde sind das 3600.
    """

    def __init__(self, mitte: Punkt, *, zoom: float = 16, hoehe: float = 280) -> None:
        self.linie = fm.PolylineMarker(coordinates=[], color=LINIE, stroke_width=4)
        self.position = fm.CircleMarker(
            coordinates=_ort(mitte),
            radius=7,
            color=POSITION,
            border_color=ft.Colors.WHITE,
            border_stroke_width=2,
        )
        self.genauigkeit = fm.CircleMarker(
            coordinates=_ort(mitte),
            radius=mitte.genauigkeit_m or 0,
            use_radius_in_meter=True,
            color=ft.Colors.with_opacity(0.15, POSITION),
            border_color=ft.Colors.with_opacity(0.4, POSITION),
            border_stroke_width=1,
        )
        self.karte = fm.Map(
            height=hoehe,
            initial_center=_ort(mitte),
            initial_zoom=zoom,
            layers=[
                osm_ebenen()[0],
                fm.PolylineLayer(polylines=[self.linie]),
                fm.CircleLayer(circles=[self.genauigkeit, self.position]),
                osm_ebenen()[1],
            ],
        )
        self._gezeigt = 0

    def nachziehen(self, punkte: Sequence[Punkt]) -> bool:
        """Neue Punkte anhängen; ``True``, wenn sich etwas geändert hat."""
        neu = punkte[self._gezeigt :]
        if not neu:
            return False
        self.linie.coordinates.extend(_ort(p) for p in neu)
        self._gezeigt = len(punkte)
        letzte = punkte[-1]
        self.position.coordinates = _ort(letzte)
        self.genauigkeit.coordinates = _ort(letzte)
        self.genauigkeit.radius = letzte.genauigkeit_m or 0
        return True

    async def folgen(self, punkt: Punkt) -> None:
        """Karte auf die Position schieben; Zoom bleibt, wie die Person ihn gewählt hat."""
        await self.karte.center_on(_ort(punkt), zoom=None)


__all__ = ["OSM_LIZENZ", "OSM_URL", "USER_AGENT_PAKET", "StreckenKarte", "osm_ebenen"]
