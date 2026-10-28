"""GPS-Vorabtest — Route `/einstellungen/gps-test` (Phase 0 in `docs/plan_gps.md`).

Zwei Tests, beide mit einem Bericht ohne Orte (`core.gps_vorabtest`):

- **Strecke:** gehen oder laufen, GPS alle 1, 3 oder 10 s, Karte und
  Kennzahlen live. Die Strecke bleibt auf dem Gerät (``Strecken/``); hinaus
  geht sie nur per ausdrücklichem GPX-Export.
- **Dauertest:** 30 min, nebenher beim Laufen (Ben, 14.10.2026) — 15 min GPS
  jede Sekunde, dann 15 min seltener (3, 5 oder 10 s). Lässt die Genauigkeit
  bei längerem GPS nach (Median je 5 min)? Was kostet der Akku (Strom je Phase
  aus dem Ladestandsmesser)? Am Ende ein Ton. Der erste, einstündige Akkutest
  (vier Phasen) war nicht auswertbar: Das Handy wurde nebenher benutzt.

Bei ausgeschaltetem Display hält der Vordergrunddienst (Typ ``location``) die
App am Leben; die Benachrichtigung zeigt den Stand. Läuft gleichzeitig eine
HRV-Messung, teilen sich beide den Dienst. Der Lauf (`GpsTestLauf`) lebt im
`AppState`, damit er Ansichtswechsel übersteht.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import flet as ft

from trainingsapp.config import app_version, streckenverzeichnis
from trainingsapp.core.gps_vorabtest import (
    DAUERTEST_ZWEITE,
    AkkuProbe,
    Phase,
    akku_auswerten,
    bericht,
    dauertest,
    phasenname,
)
from trainingsapp.core.laufend import minuten
from trainingsapp.core.strecke import Punkt, ausgeduennt, distanz_m, genaue
from trainingsapp.data.strecken import StreckenSchreiber, gpx
from trainingsapp.devices.gps import GpsQuelle, GpsSimulator
from trainingsapp.ui.components.kacheln import KachelWert, raster, zahl
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.weitergeben import weitergeben, zeitstempel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.timer import ton_spielen
from trainingsapp.ui.wach import GPS_TEST, wach_setzen

#: Wählbare GPS-Intervalle der Strecke (s)
INTERVALLE = (1.0, 3.0, 10.0)
#: Akku messen und Benachrichtigung auffrischen — alle so viele Sekunden
PROBE_S = 10.0
#: Zweck im Vordergrunddienst (`FletBleTransport.hintergrund`)
ZWECK = "gps"


class GpsTestLauf:
    """Ein laufender Test. Die Oberfläche liest nur mit; gerechnet wird in `core`."""

    def __init__(
        self,
        state: AppState,
        quelle: GpsQuelle,
        art: str,
        plan: Sequence[tuple[float | None, float | None]],
        *,
        bildschirm_an: bool = False,
    ) -> None:
        self.state = state
        self.quelle = quelle
        #: "strecke" oder "akku"
        self.art = art
        #: (GPS-Intervall oder None, Dauer in s oder None = bis Stopp) je Phase
        self.plan = list(plan)
        self.bildschirm_an = bildschirm_an
        self.phasen: list[Phase] = []
        #: Lebenszyklus: (Zeit, im Vordergrund)
        self.wechsel: list[tuple[float, bool]] = []
        self.gestartet = datetime.now()
        #: Stand des Vordergrunddienstes für den Bericht
        self.dienst = ""
        self.datei: StreckenSchreiber | None = None
        self.bericht = ""
        self.fertig = False
        self.von_selbst_fertig = False
        #: Was die Benachrichtigung zeigt (`ui.laufend`) — Phase, Zeit, Strecke
        self.meldung = ""
        self._stopp = asyncio.Event()
        self._aufgabe: asyncio.Task[None] | None = None

    @property
    def phase(self) -> Phase | None:
        return self.phasen[-1] if self.phasen else None

    def punkte(self) -> list[Punkt]:
        return [p for ph in self.phasen for p in ph.punkte]

    def lebenszeichen(self, vorn: bool) -> None:
        """App in den Vorder- oder Hintergrund gewechselt (Display an/aus)."""
        self.wechsel.append((self.quelle.jetzt(), vorn))

    def starten(self) -> None:
        self._aufgabe = asyncio.create_task(self._ablauf())

    async def stoppen(self) -> None:
        self._stopp.set()
        if self._aufgabe is not None:
            with contextlib.suppress(Exception):
                await self._aufgabe

    # -- Ablauf -------------------------------------------------------------------

    async def _ablauf(self) -> None:
        try:
            for nummer, (intervall, dauer) in enumerate(self.plan, 1):
                if self._stopp.is_set():
                    break
                await self._phase(nummer, intervall, dauer)
            self.von_selbst_fertig = not self._stopp.is_set()
        except Exception as fehler:  # nie still verschlucken — der Bericht nennt ihn
            self.dienst += f" · Abbruch: {fehler or type(fehler).__name__}"
        finally:
            await self._abschluss()

    async def _phase(self, nummer: int, intervall: float | None, dauer: float | None) -> None:
        ph = Phase(intervall, start=self.quelle.jetzt())
        self.phasen.append(ph)
        await self._akku(ph)
        empfang: asyncio.Task[None] | None = None
        if intervall is not None:
            await self.quelle.starten(intervall)
            empfang = asyncio.create_task(self._empfangen(ph))
        try:
            while not self._stopp.is_set():
                rest = None if dauer is None else dauer - (self.quelle.jetzt() - ph.start)
                if rest is not None and rest <= 0:
                    break
                warten = PROBE_S if rest is None else min(PROBE_S, rest / _zeitfaktor(self.quelle))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stopp.wait(), timeout=max(0.01, warten))
                await self._akku(ph)
                await self._benachrichtigen(nummer, ph, dauer)
        finally:
            if intervall is not None:
                await self.quelle.beenden()
                if empfang is not None:
                    await empfang
            ph.ende = self.quelle.jetzt()
            await self._akku(ph)

    async def _empfangen(self, ph: Phase) -> None:
        async for punkt in self.quelle.punkte():
            ph.punkte.append(punkt)
            if self.datei is not None:
                self.datei.schreiben(punkt)

    async def _akku(self, ph: Phase) -> None:
        transport = self.state.ble_transport
        if transport is None or not hasattr(transport, "akku"):
            return
        werte = await transport.akku()
        if werte:
            ph.akku.append(AkkuProbe.aus_werten(self.quelle.jetzt(), werte))

    async def _benachrichtigen(self, nummer: int, ph: Phase, dauer: float | None) -> None:
        transport = self.state.ble_transport
        jetzt = self.quelle.jetzt()
        if self.art == "akku" and dauer is not None:
            rest = max(0.0, dauer - (jetzt - ph.start))
            text = f"Phase {nummer}/{len(self.plan)} · {ph.name} · noch {_uhr(rest)} min"
        else:
            text = (
                f"{_uhr(jetzt - self.phasen[0].start)} · {zahl(_km(self.punkte()), 2)} km"
                f" · {len(ph.punkte)} Ortungen"
            )
        self.meldung = text
        if transport is not None and hasattr(transport, "hintergrund_text"):
            await transport.hintergrund_text(text, zweck=ZWECK)

    async def _abschluss(self) -> None:
        if self.datei is not None:
            self.datei.schliessen()
        transport = self.state.ble_transport
        if transport is not None and hasattr(transport, "hintergrund"):
            await transport.hintergrund(False, zweck=ZWECK)
        if self.bildschirm_an:
            await _wach(self.state, False)
        kopf = [
            f"GPS-Vorabtest · {'Dauertest' if self.art == 'akku' else 'Strecke'}"
            f" · Trainingsassistent {app_version()[0]}",
            f"Gestartet {self.gestartet:%d.%m.%Y %H:%M} · Quelle {self.quelle.name}"
            + (" · Bildschirm an" if self.bildschirm_an else ""),
            f"Hintergrunddienst: {self.dienst or '–'}",
        ]
        if self.quelle.meldung:
            kopf.append(f"GPS meldet: {self.quelle.meldung}")
        self.bericht = bericht(
            self.phasen, kopf=kopf, wechsel=self.wechsel, jetzt=self.quelle.jetzt()
        )
        self.fertig = True
        if self.von_selbst_fertig and self.art == "akku":
            await _signal(self.state)


# -- Helfer ---------------------------------------------------------------------------


def _zeitfaktor(quelle: GpsQuelle) -> float:
    """Wie viel schneller die Uhr der Quelle läuft (Simulator in Tests)."""
    return float(getattr(quelle, "beschleunigung", 1.0)) or 1.0


def _km(punkte: Sequence[Punkt]) -> float:
    """Die Strecke wie in der späteren Aufzeichnung: genaue Ortungen, 5-m-Schritt."""
    return distanz_m(ausgeduennt(genaue(punkte, 30.0), 5.0)) / 1000


#: Eine Schreibweise für alle Zeiten (N26)
_uhr = minuten


async def _wach(state: AppState, an: bool) -> None:
    await wach_setzen(state, an, GPS_TEST)


async def _signal(state: AppState) -> None:
    """Ton und Vibration: Der Akkutest ist fertig — Regler und Lautstärke wie beim Timer."""
    await ton_spielen(state, "ende")
    if state.haptik is not None:
        with contextlib.suppress(Exception):
            await state.haptik.vibrate()


def quelle_holen(page: ft.Page, state: AppState) -> GpsQuelle:
    """Die GPS-Quelle: auf Android das Handy-GPS (in `app.py` angelegt), sonst ein Simulator."""
    if state.gps_quelle is None:
        state.gps_quelle = GpsSimulator()
    quelle: GpsQuelle = state.gps_quelle
    return quelle


def kennzahlen(lauf: GpsTestLauf) -> list[KachelWert]:
    """Die Live-Werte des laufenden Tests."""
    ph = lauf.phase
    if ph is None:
        return []
    jetzt = lauf.quelle.jetzt()
    letzte = ph.punkte[-1] if ph.punkte else None
    abstand = (
        ph.punkte[-1].t_empfang - ph.punkte[-2].t_empfang
        if len(ph.punkte) >= 2
        and ph.punkte[-1].t_empfang is not None
        and ph.punkte[-2].t_empfang is not None
        else None
    )
    akku = akku_auswerten(ph.akku)
    strom = KachelWert(
        "Strom",
        zahl(akku.strom_ma if akku else None, 1),
        "mA",
        zusatz=f"Akku {akku.prozent_ende} %" if akku and akku.prozent_ende is not None else "",
    )
    werte = []
    if lauf.art == "akku":
        nummer = len(lauf.phasen)
        dauer = lauf.plan[nummer - 1][1] or 0
        werte += [
            KachelWert("Phase", f"{nummer}/{len(lauf.plan)}", zusatz=ph.name, gross=True),
            KachelWert("Noch", _uhr(dauer - (jetzt - ph.start)), "min", gross=True),
        ]
    else:
        werte += [
            KachelWert("Zeit", _uhr(jetzt - lauf.phasen[0].start), "min", gross=True),
            KachelWert("Strecke", zahl(_km(lauf.punkte()), 2), "km", gross=True),
        ]
    werte += [
        KachelWert("Ortungen", str(len(ph.punkte)), zusatz=ph.name),
        KachelWert("Genauigkeit", zahl(letzte.genauigkeit_m if letzte else None, 0), "m"),
        KachelWert("Abstand", zahl(abstand, 1), "s"),
        KachelWert(
            "Tempo",
            zahl(letzte.tempo_ms * 3.6 if letzte and letzte.tempo_ms is not None else None, 1),
            "km/h",
        ),
        strom,
    ]
    return werte


# -- Ansicht --------------------------------------------------------------------------


def gps_test_view(page: ft.Page, state: AppState) -> ft.View:
    from trainingsapp.ui.components.karte_strecke import StreckenKarte

    state.gps_test_ansicht += 1
    nummer = state.gps_test_ansicht
    inhalt = ft.Column(spacing=14)
    werte_platz = ft.Container()
    karte_platz = ft.Container()
    warnung = ft.Text(size=13, color=ft.Colors.ERROR, visible=False)
    strecken_karte: StreckenKarte | None = None

    def lauf_jetzt() -> GpsTestLauf | None:
        lauf: GpsTestLauf | None = state.gps_test
        return lauf

    # -- Starten und Beenden ------------------------------------------------------

    async def starten(art: str, plan: Sequence[tuple[float | None, float | None]]) -> None:
        # Eine Ortungsquelle, eine Sitzung: Der Test begänne eine neue, und das
        # laufende Ausdauertraining bekäme still keine Punkte mehr.
        if state.ausdauer is not None and not state.ausdauer.fertig:
            page.show_dialog(
                ft.SnackBar(ft.Text("Erst das Ausdauertraining beenden — beide brauchen das GPS."))
            )
            return
        quelle = quelle_holen(page, state)
        berechtigung = getattr(quelle, "berechtigung", None)
        if berechtigung is not None:
            status = await berechtigung()
            if status != "erteilt":
                berechtigung_zeigen(quelle, status)
                return
        lauf = GpsTestLauf(
            state, quelle, art, plan, bildschirm_an=art == "strecke" and state.gps_test_wach
        )
        transport = state.ble_transport
        if transport is not None and hasattr(transport, "hintergrund"):
            fehler = await transport.hintergrund(True, "GPS-Test läuft", "Start …", zweck=ZWECK)
            lauf.dienst = f"FEHLER: {fehler}" if fehler else "gestartet (Typ location)"
        else:
            lauf.dienst = "keiner (nur in der Android-App)"
        if lauf.bildschirm_an:
            await _wach(state, True)
        lauf.datei = StreckenSchreiber(streckenverzeichnis() / f"vorabtest_{zeitstempel()}.jsonl")
        state.gps_test = lauf
        lauf.starten()
        zeichnen()
        page.update()
        page.run_task(ticker)

    async def strecke_starten() -> None:
        await starten("strecke", [(state.gps_test_intervall, None)])

    async def akku_starten() -> None:
        await starten("akku", dauertest(state.gps_test_zweite_s))

    async def beenden() -> None:
        lauf = lauf_jetzt()
        if lauf is not None:
            await lauf.stoppen()
        zeichnen()
        page.update()

    def berechtigung_zeigen(quelle: Any, status: str) -> None:
        texte = {
            "Standort aus": ("Der Standort ist am Handy ausgeschaltet.", True),
            "dauerhaft verweigert": (
                "Der Standort ist für die App gesperrt — in den App-Einstellungen erlauben"
                " (genauer Standort).",
                False,
            ),
        }
        text, standort = texte.get(status, ("Ohne Standort gibt es keinen GPS-Test.", False))

        async def oeffnen() -> None:
            page.pop_dialog()
            await quelle.einstellungen_oeffnen(standort=standort)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Standort"),
                content=ft.Text(text),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.TextButton("Einstellungen öffnen", on_click=oeffnen),
                ],
            )
        )

    # -- Bericht weitergeben -----------------------------------------------------

    async def kopieren() -> None:
        lauf = lauf_jetzt()
        if lauf is None:
            return
        await ft.Clipboard().set(lauf.bericht)
        page.show_dialog(ft.SnackBar(ft.Text("Bericht kopiert")))

    async def teilen() -> None:
        lauf = lauf_jetzt()
        if lauf is not None:
            name = f"gps_test_{zeitstempel()}.txt"
            await weitergeben(page, name, lauf.bericht.encode("utf-8"), "text/plain")

    async def gpx_export() -> None:
        lauf = lauf_jetzt()
        if lauf is None or not lauf.punkte():
            return
        daten = gpx(lauf.punkte(), name=f"GPS-Test {lauf.gestartet:%d.%m.%Y %H:%M}")
        await weitergeben(page, f"strecke_{zeitstempel()}.gpx", daten, "application/gpx+xml")

    # -- Live ---------------------------------------------------------------------

    def aktualisieren(lauf: GpsTestLauf) -> bool:
        """Werte und Karte nachziehen; ``True``, wenn die Karte zu folgen hat."""
        nonlocal strecken_karte
        werte_platz.content = raster(kennzahlen(lauf))
        punkte = lauf.punkte()
        genauigkeiten = [p.genauigkeit_m for p in punkte[-10:] if p.genauigkeit_m is not None]
        warnung.visible = len(genauigkeiten) >= 5 and min(genauigkeiten) > 100
        warnung.value = (
            "Nur ungefährer Standort? In den App-Einstellungen „Genauen Standort“ erlauben."
        )
        if not state.gps_test_karte or not punkte:
            karte_platz.content = None
            strecken_karte = None
            return False
        if strecken_karte is None:
            strecken_karte = StreckenKarte(punkte[-1])
            karte_platz.content = strecken_karte.karte
        return strecken_karte.nachziehen(punkte)

    async def ticker() -> None:
        route = state.route_nummer  # die Ansicht verlassen → Schluss (H35)
        while state.gps_test_ansicht == nummer and state.route_nummer == route:
            lauf = lauf_jetzt()
            if lauf is None:
                return
            if state.im_vordergrund:
                if lauf.fertig:
                    zeichnen()
                    with contextlib.suppress(Exception):
                        page.update()
                    return
                folgen = aktualisieren(lauf)
                with contextlib.suppress(Exception):  # ein Fehler beendete die Aufgabe still
                    page.update()
                if folgen and strecken_karte is not None:
                    with contextlib.suppress(Exception):
                        await strecken_karte.folgen(lauf.punkte()[-1])
            await asyncio.sleep(1.0)

    # -- Aufbau -------------------------------------------------------------------

    def zweite_wahl() -> ft.Control:
        def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
            if e.control.selected:
                state.gps_test_zweite_s = float(next(iter(e.control.selected)))

        return ft.SegmentedButton(
            selected=[str(state.gps_test_zweite_s)],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=str(x), label=ft.Text(f"{x:g} s")) for x in DAUERTEST_ZWEITE
            ],
            on_change=gewaehlt,
        )

    def intervall_wahl() -> ft.Control:
        def gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
            state.gps_test_intervall = float(next(iter(e.control.selected)))

        return ft.SegmentedButton(
            segments=[ft.Segment(value=str(i), label=ft.Text(f"{zahl(i)} s")) for i in INTERVALLE],
            selected=[str(state.gps_test_intervall)],
            on_change=gewaehlt,
        )

    def schalter(text: str, attribut: str) -> ft.Control:
        def umgelegt(e: ft.Event[ft.Switch]) -> None:
            setattr(state, attribut, bool(e.control.value))

        return ft.Switch(label=text, value=bool(getattr(state, attribut)), on_change=umgelegt)

    def bericht_karte(lauf: GpsTestLauf) -> ft.Control:
        knoepfe: list[ft.Control] = [
            ft.OutlinedButton("Kopieren", icon=ft.Icons.COPY, on_click=kopieren),
            ft.OutlinedButton("Teilen", icon=ft.Icons.SHARE, on_click=teilen),
        ]
        if lauf.art == "strecke" and lauf.punkte():
            knoepfe.append(
                ft.OutlinedButton("GPX exportieren", icon=ft.Icons.ROUTE, on_click=gpx_export)
            )
        return karte(
            titel("Bericht"),
            hinweis(
                "Ohne Orte — darf weitergegeben werden. Die Strecke selbst bleibt auf dem"
                " Handy; „GPX exportieren“ gibt sie ausdrücklich heraus."
            ),
            ft.Text(lauf.bericht, size=12, font_family="monospace", selectable=True),
            ft.Row(knoepfe, wrap=True, spacing=8, run_spacing=8),
        )

    def zeichnen() -> None:
        nonlocal strecken_karte
        lauf = lauf_jetzt()
        if lauf is not None and not lauf.fertig:
            titel_text = (
                f"Dauertest · {lauf.phase.name if lauf.phase else phasenname(None)}"
                if lauf.art == "akku"
                else "Strecke läuft"
            )
            erklaerung = (
                "Display aus, nicht laden — laufen oder gehen, wie du magst. Nach 30 min "
                "kommt ein Ton."
                if lauf.art == "akku"
                else "Display darf aus sein — GPS läuft im Hintergrund weiter."
                " Am Ende 1 min stehen bleiben."
            )
            strecken_karte = None
            aktualisieren(lauf)
            inhalt.controls = [
                karte(
                    titel(titel_text),
                    hinweis(erklaerung),
                    werte_platz,
                    warnung,
                    ft.FilledButton("Beenden", icon=ft.Icons.STOP, on_click=beenden),
                ),
                karte_platz,
            ]
            return
        inhalt.controls = [
            karte(
                titel("Strecke"),
                hinweis(
                    "Draußen starten, 1 min stehen bleiben, dann gehen. Am Ende wieder 1 min"
                    " stehen. Ist die Strecke bekannt (400-m-Bahn, ausgemessener Weg),"
                    " notiere sie — der Bericht zeigt, welche Rechnung am nächsten liegt."
                ),
                ft.Text("GPS alle", size=13),
                intervall_wahl(),
                schalter("Karte zeigen", "gps_test_karte"),
                schalter("Bildschirm anlassen", "gps_test_wach"),
                ft.FilledButton(
                    "Strecke starten", icon=ft.Icons.DIRECTIONS_WALK, on_click=strecke_starten
                ),
            ),
            karte(
                titel("Dauertest (30 min)"),
                hinweis(
                    "15 min GPS jede Sekunde, dann 15 min seltener — nebenher beim Laufen "
                    "oder Gehen. Der Bericht zeigt die Genauigkeit je 5 min (lässt sie nach?) "
                    "und den Strom je Phase. Display aus, nicht laden; der Strom ist nur "
                    "vergleichbar, wenn du das Handy in beiden Phasen gleich benutzt. Am "
                    "Ende kommt ein Ton."
                ),
                ft.Text("Zweite Phase: GPS alle", size=13),
                zweite_wahl(),
                ft.OutlinedButton(
                    "Dauertest starten", icon=ft.Icons.BATTERY_STD, on_click=akku_starten
                ),
            ),
            *([bericht_karte(lauf)] if lauf is not None and lauf.fertig else []),
            hinweis(
                f"Ortungsquelle: {quelle_holen(page, state).name}. Karte: OpenStreetMap;"
                " schon gesehene Gegenden zeigt sie auch ohne Netz."
            ),
        ]

    zeichnen()
    lauf = lauf_jetzt()
    if lauf is not None and not lauf.fertig:
        page.run_task(ticker)

    return ft.View(
        route="/einstellungen/gps-test",
        appbar=ft.AppBar(title=ft.Text("GPS-Test")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


__all__ = ["GpsTestLauf", "gps_test_view", "kennzahlen", "quelle_holen"]
