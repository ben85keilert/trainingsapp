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

**Einfärben** (Ben, 26.10.2026, P81): Statt einer Linie viele Stücke, jedes in der Farbe
seines Tempos (oder seiner Herzfrequenz) — `Faerbung` = Liste aus (Ortungen, Farbe,
gepunktet). Die Stufen rechnet `core.strecke_farbe`, die Farben stehen in
`ui.farben.TEMPO_SKALEN`; `faerbung_aus` verbindet beides. Weiße Randlinie, damit auch helle
Töne auf der Karte stehen; Stillstand grau und gepunktet.
"""

from __future__ import annotations

from collections.abc import Sequence

import flet as ft
import flet_map as fm

from trainingsapp.core.strecke import Punkt, ausgeduennt
from trainingsapp.core.strecke_farbe import Stueck, gestuft
from trainingsapp.ui.farben import PAUSE_FARBE, TEMPO_SKALEN

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_LIZENZ = "https://www.openstreetmap.org/copyright"
#: Kennung gegenüber dem Kachelserver (OSM verlangt eine eindeutige)
USER_AGENT_PAKET = "de.praxisebert.trainingsassistent"

LINIE = ft.Colors.BLUE_700
POSITION = ft.Colors.BLUE_600

#: Ein Linienstück: Ortungen, Farbe, gepunktet (Stillstand)
Faerbung = Sequence[tuple[Sequence[Punkt], str, bool]]


def faerbung_aus(
    stuecke: Sequence[Stueck], skala: str, grenzen: tuple[float, float] | None = None
) -> Faerbung:
    """Stücke mit Stufe → Stücke mit Farbe der Skala; Pausen und Stücke ohne Wert grau."""
    farben = TEMPO_SKALEN.get(skala) or TEMPO_SKALEN["tempo"]
    aus: list[tuple[Sequence[Punkt], str, bool]] = []
    for s, stufe in gestuft(stuecke, len(farben), grenzen):
        farbe = farben[stufe] if stufe is not None else PAUSE_FARBE
        aus.append((s.punkte, farbe, s.pause))
    return aus


def _linien(faerbung: Faerbung, *, breite: float = 5) -> list[fm.PolylineMarker]:
    return [
        fm.PolylineMarker(
            coordinates=[_ort(p) for p in punkte],
            color=farbe,
            stroke_width=breite,
            border_color=ft.Colors.WHITE,
            border_stroke_width=1,
            stroke_pattern=fm.DottedStrokePattern() if gepunktet else fm.SolidStrokePattern(),
        )
        for punkte, farbe, gepunktet in faerbung
        if len(punkte) > 1
    ]


def legende(skala: str, von: str, bis: str, *, titel: str = "") -> ft.Control:
    """Der Farbbalken unter der Karte: „langsam 7:40 … schnell 4:50“."""
    farben = TEMPO_SKALEN.get(skala) or TEMPO_SKALEN["tempo"]
    return ft.Row(
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(titel, size=12, opacity=0.7, visible=bool(titel)),
            ft.Text(von, size=12, opacity=0.8),
            ft.Row(
                spacing=0,
                controls=[
                    ft.Container(width=22, height=10, bgcolor=f, border_radius=2) for f in farben
                ],
            ),
            ft.Text(bis, size=12, opacity=0.8),
        ],
    )


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
        self.schicht = fm.PolylineLayer(polylines=[self.linie])
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
                self.schicht,
                fm.CircleLayer(circles=[self.genauigkeit, self.position]),
                namensnennung,
            ],
        )
        self._gezeigt = 0
        self._stuecke: list[fm.PolylineMarker] = []
        self._pausen: list[bool] = []

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

    def faerben(self, faerbung: Faerbung | None) -> None:
        """Die Linie in Stücken in Farbe — oder (``None``) wieder einfarbig.

        Die Stücke bleiben dieselben Controls: Nur das letzte wächst, und eine Farbe
        ändert sich, wenn die Spanne wandert — so geht jede Sekunde wenig über die Leitung."""
        if faerbung is None:
            if self._stuecke:
                self._stuecke = []
                self._pausen = []
                self.schicht.polylines = [self.linie]
            return
        neu: list[fm.PolylineMarker] = []
        pausen: list[bool] = []
        for punkte, farbe, gepunktet in faerbung:
            if len(punkte) < 2:
                continue
            i = len(neu)
            if i < len(self._stuecke):
                m = self._stuecke[i]
                if len(m.coordinates) != len(punkte):
                    m.coordinates = [_ort(p) for p in punkte]
                if m.color != farbe:
                    m.color = farbe
                if self._pausen[i] != gepunktet:
                    m.stroke_pattern = (
                        fm.DottedStrokePattern() if gepunktet else fm.SolidStrokePattern()
                    )
            else:
                m = _linien([(punkte, farbe, gepunktet)])[0]
            neu.append(m)
            pausen.append(gepunktet)
        if len(neu) != len(self._stuecke):
            self.schicht.polylines = neu
        self._stuecke, self._pausen = neu, pausen

    async def folgen(self, punkt: Punkt) -> None:
        """Karte auf die Position schieben; Zoom bleibt, wie die Person ihn gewählt hat."""
        await self.karte.center_on(_ort(punkt), zoom=None)


def ganze_strecke(
    teilstuecke: Sequence[Sequence[Punkt]], *, hoehe: float = 300, faerbung: Faerbung | None = None
) -> ft.Control:
    """Die ganze Strecke, eingepasst — für die Auswertung; Start grün, Ziel rot.

    Für die Linie reicht ein Punkt je 5 m; eine Stunde Laufen hat sonst 3600. Mit
    ``faerbung`` stattdessen die Stücke in Farbe.
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
                polylines=_linien(faerbung)
                if faerbung is not None
                else [
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
    "Faerbung",
    "StreckenKarte",
    "faerbung_aus",
    "ganze_strecke",
    "legende",
    "osm_ebenen",
]
