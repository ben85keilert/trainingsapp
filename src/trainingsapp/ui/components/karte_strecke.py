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

import contextlib
import math
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
#: Der Marker, der dem Strich der Kurve folgt
ZEIGER = ft.Colors.DEEP_PURPLE_600
#: Rand um die eingepasste Strecke (px) und die größte Zoomstufe dabei
RAND_PX = 28
ZOOM_MAX = 17.0

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


def zoom_fuer(
    sued: float, nord: float, west: float, ost: float, breite_px: float, hoehe_px: float
) -> float:
    """Die Zoomstufe, bei der der Kasten in die Fläche passt (Web-Mercator, Kacheln 256 px).

    >>> round(zoom_fuer(52.50, 52.51, 13.40, 13.42, 320, 244), 1)   # rund 1,4 km breit
    14.4
    >>> zoom_fuer(52.5, 52.5, 13.4, 13.4, 320, 244)                 # ein Punkt: nah heran
    17.0
    """

    def merkator(breite_grad: float) -> float:
        sinus = math.sin(math.radians(max(min(breite_grad, 85.0), -85.0)))
        return math.log((1 + sinus) / (1 - sinus)) / 2

    anteil_x = max(ost - west, 0.0) / 360.0
    anteil_y = max(merkator(nord) - merkator(sued), 0.0) / (2 * math.pi)
    stufen = [
        math.log2(px / (256.0 * anteil))
        for px, anteil in ((breite_px, anteil_x), (hoehe_px, anteil_y))
        if anteil > 0 and px > 0
    ]
    return max(min(min(stufen, default=ZOOM_MAX), ZOOM_MAX), 1.0)


class GanzeStrecke:
    """Die ganze Strecke, eingepasst — für die Auswertung; Start grün, Ziel rot.

    Für die Linie reicht ein Punkt je 5 m; eine Stunde Laufen hat sonst 3600. Mit
    ``faerbung`` stattdessen die Stücke in Farbe.

    Ben, 12.11.2026: ein Knopf **„Ganze Strecke zeigen“** (oben rechts) passt die Karte
    wieder ein, nachdem man sie verschoben oder gezoomt hat; `zeiger` setzt einen Marker
    auf eine Ortung — er folgt dem Strich der Kurve „Weg über die Zeit“.
    """

    def __init__(
        self,
        teilstuecke: Sequence[Sequence[Punkt]],
        *,
        hoehe: float = 300,
        faerbung: Faerbung | None = None,
    ) -> None:
        teile = [ausgeduennt(teil, 5.0) for teil in teilstuecke if teil]
        alle = [p for teil in teile for p in teil]
        self.karte: fm.Map | None = None
        self._hoehe = hoehe
        self._breite_px = 320.0
        self._zeiger: fm.CircleMarker | None = None
        if not alle:
            self.control: ft.Control = ft.Container(
                height=80,
                alignment=ft.Alignment.CENTER,
                content=ft.Text("Ohne GPS aufgezeichnet — keine Strecke.", opacity=0.6),
            )
            return
        self._sued, self._nord = min(p.lat for p in alle), max(p.lat for p in alle)
        self._west, self._ost = min(p.lon for p in alle), max(p.lon for p in alle)
        kacheln, namensnennung = osm_ebenen()  # einmal — zwei Aufrufe verwarfen je eine Schicht
        self._zeiger = fm.CircleMarker(
            coordinates=_ort(alle[0]),
            radius=0,
            color=ZEIGER,
            border_color=ft.Colors.WHITE,
            border_stroke_width=3,
        )
        self.karte = fm.Map(
            height=hoehe,
            initial_center=self._mitte(),
            initial_zoom=15,
            initial_camera_fit=fm.CameraFit(
                bounds=fm.MapLatitudeLongitudeBounds(
                    fm.MapLatitudeLongitude(self._sued, self._west),
                    fm.MapLatitudeLongitude(self._nord, self._ost),
                ),
                padding=ft.Padding.all(RAND_PX),
                max_zoom=ZOOM_MAX,
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
                        self._zeiger,
                    ]
                ),
                namensnennung,
            ],
        )

        def groesse(e: ft.LayoutSizeChangeEvent) -> None:
            self._breite_px = max(float(e.width), 100.0)

        self.control = ft.Container(
            on_size_change=groesse,
            content=ft.Stack(
                controls=[
                    self.karte,
                    ft.Container(
                        right=8,
                        top=8,
                        border_radius=20,
                        bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.WHITE),
                        content=ft.IconButton(
                            ft.Icons.FIT_SCREEN,
                            icon_color=ft.Colors.BLACK_87,
                            tooltip="Ganze Strecke zeigen",
                            data="karte_einpassen",
                            on_click=self.einpassen,
                        ),
                    ),
                ]
            ),
        )

    def _mitte(self) -> fm.MapLatitudeLongitude:
        return fm.MapLatitudeLongitude((self._sued + self._nord) / 2, (self._west + self._ost) / 2)

    def zoom(self) -> float:
        """Die Zoomstufe, bei der die Strecke mit Rand in die Karte passt."""
        return zoom_fuer(
            self._sued,
            self._nord,
            self._west,
            self._ost,
            self._breite_px - 2 * RAND_PX,
            self._hoehe - 2 * RAND_PX,
        )

    async def einpassen(self, _e: object = None) -> None:
        """Die Karte zurück auf die ganze Strecke: Mitte des Kastens, Zoom mit Rand."""
        if self.karte is None:
            return
        with contextlib.suppress(Exception):  # Karte nicht (mehr) auf der Seite
            await self.karte.move_to(destination=self._mitte(), zoom=self.zoom(), rotation=0)

    def zeiger(self, p: Punkt | None) -> None:
        """Den Marker auf eine Ortung setzen — ``None`` nimmt ihn weg."""
        if self._zeiger is None:
            return
        if p is None:
            self._zeiger.radius = 0
        else:
            self._zeiger.coordinates = _ort(p)
            self._zeiger.radius = 8
        with contextlib.suppress(Exception):
            self._zeiger.update()


def ganze_strecke(
    teilstuecke: Sequence[Sequence[Punkt]], *, hoehe: float = 300, faerbung: Faerbung | None = None
) -> ft.Control:
    """Die Karte der `GanzeStrecke` — für Aufrufer, die weder Marker noch Einpassen brauchen."""
    return GanzeStrecke(teilstuecke, hoehe=hoehe, faerbung=faerbung).control


__all__ = [
    "OSM_LIZENZ",
    "OSM_URL",
    "USER_AGENT_PAKET",
    "Faerbung",
    "GanzeStrecke",
    "StreckenKarte",
    "faerbung_aus",
    "ganze_strecke",
    "legende",
    "osm_ebenen",
    "zoom_fuer",
]
