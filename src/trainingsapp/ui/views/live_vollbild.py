"""Live-Vollbild: eine Kurve der laufenden Messung allein, quer, ohne Leisten.

Route ``/live`` (Ben, 15.10.2026). Der Knopf an der Tachogramm-Karte öffnet es,
`ui.ausrichtung` dreht den Bildschirm dabei ins Querformat; Zurück stellt
hochkant wieder her. Gedacht zum genauen Hinsehen und Setzen: eine Kurve füllt
den Bildschirm, oben eine dünne Zeile mit Schließen, ‹ Kurvenname ▾ ›, den
Zoomstufen und — zurückgeblättert — dem Weg zurück zur Gegenwart.

**Seiten.** Das Tachogramm und je Gruppe der in der Analyse gewählten
Verlaufskurven (gleiche Achse = ein Diagramm, wie dort). Blättern über die
Pfeile, die Liste hinter dem Namen oder **hoch/runter wischen**; waagrecht
wischen bleibt das Blättern in der Zeit (`zeitfenster.wischbar`), darum nicht
links/rechts. `AppState.vollbild_kurve` merkt die Seite.

**Notizen ohne Tastatur.** Das runde Symbol unten rechts setzt eine Notiz ohne
Text (live: jetzt; zurückgeblättert: Fenstermitte); jede Marke lässt sich mit
dem Finger an ihre Stelle ziehen (`Notizfeld.greifen`). Text kommt hochkant
dazu — die Tastatur fräße quer den halben Bildschirm.

Die Höhe der Kurve wird gemessen (``on_size_change``), weil die Ansicht noch
hochkant gebaut wird und erst danach gedreht erscheint; bis dahin gilt eine
Schätzung aus ``page.height``.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.hrv_einstellungen import LIVE_FENSTER
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.hrv_core.atmung import ATEMUEBUNG, RUHE
from trainingsapp.hrv_core.trends import titel
from trainingsapp.ui.components.analyse import verlaufsdaten
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.notizen import Notizfeld
from trainingsapp.ui.components.verlauf import diagramme, fenster_text, kurvengruppen
from trainingsapp.ui.components.zeitfenster import Fenster, wischbar
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.messung import ohne_rr, tachogramm

#: Platz über der Kurve (Kopfzeile) und Ränder — für die Schätzung vor der Messung (px)
_KOPF_PX = 76
#: So schnell (px/s) muss ein senkrechtes Wischen sein, damit es blättert
_WISCH_PX_S = 250


def _uhr(sekunden: float) -> str:
    s = max(0, round(sekunden))
    return f"{s // 60}:{s % 60:02d}"


def live_vollbild_view(page: ft.Page, state: AppState) -> ft.View:
    """Die Ansicht hinter ``/live`` — ohne Gerät nur ein Hinweis mit Zurück."""
    lauf: Messlauf | None = state.messlauf

    async def schliessen() -> None:
        await page.push_route("/")

    if lauf is None or lauf.status.verbindung == Verbindung.GETRENNT:
        return ft.View(
            route="/live",
            padding=16,
            controls=[
                sicher(
                    ft.Column(
                        controls=[
                            ft.Text("Kein Gerät verbunden.", size=16),
                            ft.TextButton("Zurück", icon=ft.Icons.CLOSE, on_click=schliessen),
                        ]
                    )
                )
            ],
        )
    return _vollbild(page, state, lauf, schliessen)


def _vollbild(
    page: ft.Page, state: AppState, lauf: Messlauf, schliessen: Callable[[], Any]
) -> ft.View:
    state.live_ansicht += 1  # die Live-Ansicht darunter rechnet nicht mehr
    meine_nummer = state.live_ansicht
    einst = state.hrv_einstellungen()
    verity = bool(lauf.profil and lauf.profil.kann("pmd_ppi"))
    fenster = Fenster(einst.fenster_s, state.messung_ende_s)
    speicher: dict[Any, Any] = {}
    kurven_box = ft.Container()
    lage_box = ft.Container()
    name_box = ft.Container()
    stand: dict[str, Any] = {
        "hoehe": max(160.0, float(page.height or 480) - _KOPF_PX),
        "zuletzt": 0.0,
    }

    def anfang() -> float:
        return max(0.0, lauf.jetzt_s() - lauf.live.max_s)

    def mitte() -> float:
        return sum(fenster.bereich(lauf.jetzt_s(), anfang())) / 2

    # -- Seiten -----------------------------------------------------------------------

    ansicht = state.ansicht()
    ohne = [] if lauf.live.kennzahlen().rr_ms else ohne_rr()
    gruppen = kurvengruppen(ansicht, ansicht.bereich if ansicht.bereich != "zeit" else "zeit", ohne)
    seiten: list[tuple[str, list[str] | None]] = [
        ("PPI-Tachogramm" if verity else "RR-Tachogramm", None)
    ] + [(" · ".join(titel(k, ansicht.pnn_ms) for k in g), list(g)) for g in gruppen]

    def seite() -> int:
        return min(max(state.vollbild_kurve, 0), len(seiten) - 1)

    def blaettern(schritt: int) -> None:
        state.vollbild_kurve = (seite() + schritt) % len(seiten)
        aktualisieren(erzwingen=True)

    def waehlen(i: int) -> Callable[[], None]:
        def handler() -> None:
            state.vollbild_kurve = i
            aktualisieren(erzwingen=True)

        return handler

    def senkrecht(e: ft.DragEndEvent) -> None:
        """Hoch/runter wischen: nächste bzw. vorige Kurve (waagrecht gehört der Zeit)."""
        v = e.primary_velocity
        if v is None or abs(v) < _WISCH_PX_S:
            return
        blaettern(1 if v < 0 else -1)

    # -- Notizen ------------------------------------------------------------------------

    def notizen_speichern(liste: list[dict]) -> None:
        if lauf.aufnahme is not None:
            lauf.aufnahme.ereignisse = liste

    notizfeld = Notizfeld(
        zeitbezug=lauf.notiz_zeitbezug,
        ereignisse=lambda: list(lauf.aufnahme.ereignisse) if lauf.aufnahme is not None else [],
        speichern=notizen_speichern,
        neu_zeichnen=lambda: aktualisieren(erzwingen=True),
        zeigen=lambda _x: None,
        mitte=mitte,
        jetzt=lauf.jetzt_s,
        breite=lambda: fenster.breite_s,
    )

    def marke() -> None:
        x = None if fenster.ende_s is None else mitte()
        if not notizfeld.marke_setzen(x):
            page.show_dialog(
                ft.SnackBar(ft.Text("Notizen gehören zu einer Aufnahme — erst „Aufnahme starten“."))
            )

    # -- Zeichnen -----------------------------------------------------------------------

    def kurve_bauen(x_von: float, x_bis: float) -> ft.Control:
        hoehe = int(stand["hoehe"])
        marken = notizfeld.marken(x_von, x_bis)
        _, gruppe = seiten[seite()]
        if gruppe is None:
            return tachogramm(
                lauf,
                x_von,
                x_bis,
                korrigiert=einst.korrigiert,
                verity=verity,
                marken=marken,
                hoehe=hoehe,
            )
        atem_modus = ATEMUEBUNG if state.hrv_einstellungen().atemuebung else RUHE
        daten = verlaufsdaten(
            lauf.live.verlaufsreihe(),
            lauf.live.hf_reihe(),
            ansicht,
            atem_modus,
            speicher,
            x_von,
            x_bis,
        )
        teile = diagramme(
            ansicht,
            daten,
            x_von=x_von,
            x_bis=x_bis,
            hoehe=max(100, hoehe - 24),
            ohne=ohne,
            marken=marken,
            gruppen=[gruppe],
        )
        return ft.Column(spacing=2, tight=True, controls=teile)

    def lage() -> ft.Control:
        if fenster.ende_s is None:
            return ft.Container()
        zurueck = lauf.jetzt_s() - fenster.bereich(lauf.jetzt_s(), anfang())[1]
        return ft.Row(
            spacing=4,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(f"−{_uhr(zurueck)}", size=12, opacity=0.7),
                ft.TextButton("Live", icon=ft.Icons.SKIP_NEXT, on_click=zur_gegenwart),
            ],
        )

    def name() -> ft.Control:
        aktuell = seite()
        return ft.PopupMenuButton(
            tooltip="Kurve wählen",
            content=ft.Row(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(seiten[aktuell][0], size=13, weight=ft.FontWeight.W_600),
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18),
                ],
            ),
            items=[
                ft.PopupMenuItem(
                    content=n,
                    checked=i == aktuell,
                    on_click=waehlen(i),
                )
                for i, (n, _) in enumerate(seiten)
            ],
        )

    def fuellen() -> None:
        state.messung_ende_s = fenster.ende_s
        x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
        kurven_box.content = kurve_bauen(x_von, x_bis)
        lage_box.content = lage()
        name_box.content = name()

    def aktualisieren(erzwingen: bool = False) -> None:
        if state.live_ansicht != meine_nummer:
            return
        jetzt = time.monotonic()
        if not erzwingen and jetzt - stand["zuletzt"] < 0.5:
            return
        stand["zuletzt"] = jetzt
        fuellen()
        with contextlib.suppress(Exception):
            spalte.update()

    def gewischt() -> None:
        state.messung_ende_s = fenster.ende_s
        x_von, x_bis = fenster.bereich(lauf.jetzt_s(), anfang())
        kurven_box.content = kurve_bauen(x_von, x_bis)
        lage_box.content = lage()
        for c in (kurven_box, lage_box):
            with contextlib.suppress(Exception):
                c.update()

    def losgelassen() -> None:
        notizfeld.loslassen()  # speichert eine gezogene Marke (zeichnet selbst neu)

    def beobachten(layout: bool) -> None:
        if layout and lauf.status.verbindung == Verbindung.GETRENNT:
            state.neu_zeichnen()
        else:
            aktualisieren(erzwingen=layout)

    def zur_gegenwart() -> None:
        fenster.ende_s = None
        aktualisieren(erzwingen=True)

    def fenster_wechseln(e: ft.Event[ft.SegmentedButton]) -> None:
        if not e.control.selected:
            return
        fenster.breite_s = int(e.control.selected[0])
        aktuell = state.hrv_einstellungen()
        aktuell.fenster_s = int(fenster.breite_s)
        state.hrv_einstellungen_setzen(aktuell)
        aktualisieren(erzwingen=True)

    def groesse(e: ft.LayoutSizeChangeEvent) -> None:
        """Die wirkliche Höhe der Kurvenfläche — nach dem Drehen anders als geschätzt."""
        neu = max(120.0, float(e.height))
        if abs(neu - stand["hoehe"]) < 4:
            return
        stand["hoehe"] = neu
        aktualisieren(erzwingen=True)

    kopf = ft.Row(
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.IconButton(ft.Icons.CLOSE, tooltip="Vollbild verlassen", on_click=schliessen),
            ft.IconButton(
                ft.Icons.CHEVRON_LEFT, tooltip="Vorige Kurve", on_click=lambda: blaettern(-1)
            ),
            name_box,
            ft.IconButton(
                ft.Icons.CHEVRON_RIGHT, tooltip="Nächste Kurve", on_click=lambda: blaettern(1)
            ),
            ft.Container(expand=True),
            lage_box,
            ft.SegmentedButton(
                selected=[str(fenster.breite_s if fenster.breite_s in LIVE_FENSTER else 120)],
                show_selected_icon=False,
                style=ft.ButtonStyle(
                    visual_density=ft.VisualDensity.COMPACT,
                    padding=ft.Padding.symmetric(horizontal=6),
                ),
                segments=[
                    ft.Segment(value=str(s), label=ft.Text(fenster_text(s), size=12))
                    for s in LIVE_FENSTER
                ],
                on_change=fenster_wechseln,
            ),
        ],
    )
    flaeche = ft.GestureDetector(
        expand=True,
        on_vertical_drag_end=senkrecht,
        content=ft.Container(
            expand=True,
            on_size_change=groesse,
            content=wischbar(
                kurven_box,
                fenster,
                lauf.jetzt_s,
                gewischt,
                anfang=anfang,
                greifen=notizfeld.greifen,
                losgelassen=losgelassen,
            ),
        ),
    )
    spalte = ft.Column(spacing=0, expand=True, controls=[kopf, flaeche])
    inhalt = ft.Stack(
        expand=True,
        controls=[
            spalte,
            ft.FloatingActionButton(
                icon=ft.Icons.ADD_COMMENT_OUTLINED,
                mini=True,
                tooltip="Notiz an dieser Stelle (Text später hochkant)",
                on_click=lambda: marke(),
                right=12,
                bottom=12,
            ),
        ],
    )
    fuellen()
    lauf.beobachter = beobachten
    return ft.View(
        route="/live",
        padding=ft.Padding.only(left=4, right=4, top=0, bottom=0),
        controls=[sicher(inhalt)],
    )


__all__ = ["live_vollbild_view"]
