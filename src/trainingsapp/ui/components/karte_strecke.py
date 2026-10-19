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

from trainingsapp.core.strecke import Punkt, ausgeduennt

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
        kacheln, namensnennung = osm_ebenen()
        self.karte = fm.Map(
            height=hoehe,
            initial_center=_ort(mitte),
            initial_zoom=zoom,
            layers=[
                kacheln,
                fm.PolylineLayer(polylines=[self.linie]),
                fm.CircleLayer(circles=[self.genauigkeit, self.position]),
                namensnennung,
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


def ganze_strecke(teilstuecke: Sequence[Sequence[Punkt]], *, hoehe: float = 300) -> ft.Control:
    """Die ganze Strecke, eingepasst — für die Auswertung; Start grün, Ziel rot.

    Für die Linie reicht ein Punkt je 5 m; eine Stunde Laufen hat sonst 3600.
    """
    teile = [ausgeduennt(teil, 5.0) for teil in teilstuecke if teil]
    alle = [p for teil in teile for p in teil]
    if not alle:
        return ft.Container(
            height=80,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("Ohne GPS aufgezeichnet — keine Strecke.", opacity=0.6),
        )
    sued, nord = min(p.lat for p in alle), max(p.lat for p in alle)
    west, ost = min(p.lon for p in alle), max(p.lon for p in alle)
    kacheln, namensnennung = osm_ebenen()  # einmal — zwei Aufrufe verwarfen je eine Schicht
    return fm.Map(
        height=hoehe,
        initial_center=fm.MapLatitudeLongitude((sued + nord) / 2, (west + ost) / 2),
        initial_zoom=15,
        initial_camera_fit=fm.CameraFit(
            bounds=fm.MapLatitudeLongitudeBounds(
                fm.MapLatitudeLongitude(sued, west), fm.MapLatitudeLongitude(nord, ost)
            ),
            padding=ft.Padding.all(28),
            max_zoom=17,
        ),
        layers=[
            kacheln,
            fm.PolylineLayer(
                polylines=[
                    fm.PolylineMarker(
                        coordinates=[_ort(p) for p in teil], color=LINIE, stroke_width=4
                    )
                    for teil in teile
                    if len(teil) > 1
                ]
            ),
            fm.CircleLayer(
                circles=[
                    fm.CircleMarker(
                        coordinates=_ort(alle[0]),
                        radius=7,
                        color=ft.Colors.GREEN_600,
                        border_color=ft.Colors.WHITE,
                        border_stroke_width=2,
                    ),
                    fm.CircleMarker(
                        coordinates=_ort(alle[-1]),
                        radius=7,
                        color=ft.Colors.RED_600,
                        border_color=ft.Colors.WHITE,
                        border_stroke_width=2,
                    ),
                ]
            ),
            namensnennung,
        ],
    )


__all__ = [
    "OSM_LIZENZ",
    "OSM_URL",
    "USER_AGENT_PAKET",
    "StreckenKarte",
    "ganze_strecke",
    "osm_ebenen",
]
