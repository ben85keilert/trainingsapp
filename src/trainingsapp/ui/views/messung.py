"""Reiter „Messung": Gerät verbinden, live sehen, aufzeichnen.

Die laufende Messung liegt im `AppState` (`state.messlauf`), nicht in dieser
Ansicht — sonst risse sie bei jedem Reiterwechsel ab (L03). Die Ansicht
schaut nur zu: `Messlauf` meldet neue Werte über einen Beobachter, und die
Ansicht frischt Kennzahlen und Kurven auf.

Live wird nichts an den Rohdaten verändert. Artefakte werden markiert (rote
Punkte), die korrigierte Kurve ist eine Anzeige; gespeichert werden immer
die Rohwerte. Korrigiert wird nachträglich in der Aufzeichnung.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.config import datenverzeichnis, messungenverzeichnis
from trainingsapp.core.models import HrvRecording
from trainingsapp.devices.base import DeviceInfo, Verbindung
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.profiles import profil_fuer_namen
from trainingsapp.devices.simulated import SIM_PPI, SIM_PREFIX, SIM_SYNTH, SimulatedSource
from trainingsapp.ui.components.kurve import Reihe, kurve
from trainingsapp.ui.state import AppState

FENSTER = [(60, "1 min"), (120, "2 min"), (300, "5 min")]
ROT = ft.Colors.RED_400


def _protokoll(lauf_oder_quelle: Any, zeilen: int = 20) -> list[str]:
    """Die letzten Diagnosezeilen der Quelle (PolarQuelle führt sie mit)."""
    quelle = getattr(lauf_oder_quelle, "quelle", lauf_oder_quelle)
    return list(getattr(quelle, "protokoll", []))[-zeilen:]


def _diagnose(zeilen: list[str]) -> ft.Control:
    """Aufklappbar — für Screenshots, wenn am Handy etwas nicht klappt."""
    return ft.ExpansionTile(
        title=ft.Text("Diagnose", size=13),
        subtitle=ft.Text(zeilen[-1] if zeilen else "noch keine Einträge", size=11, opacity=0.6),
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=12, right=12, bottom=8),
                content=ft.Text(
                    "\n".join(zeilen) or "–", size=11, selectable=True, font_family="monospace"
                ),
            )
        ],
    )


async def _hintergrund(state: AppState, lauf: Messlauf, an: bool, text: str = "") -> None:
    """Vordergrunddienst an/aus — nur in der Android-App (über `FletBleTransport`).

    Solange er läuft, misst und zeichnet die App auch bei ausgeschaltetem
    Display oder in einer anderen App weiter. Ein Fehler stoppt die Messung
    nicht; er landet im Diagnoseprotokoll.
    """
    transport = state.ble_transport
    if transport is None or not hasattr(transport, "hintergrund"):
        return
    fehler = await transport.hintergrund(an, "HRV-Messung läuft", text)
    protokoll = getattr(lauf.quelle, "protokoll", None)
    if protokoll is not None:
        zeile = f"Hintergrunddienst {'gestartet' if an else 'beendet'}"
        protokoll.append(
            f"{time.strftime('%H:%M:%S')} " + (f"{zeile} — FEHLER: {fehler}" if fehler else zeile)
        )


def _uhr(sekunden: float) -> str:
    s = int(sekunden)
    return f"{s // 60}:{s % 60:02d}"


def _zahl(wert: float | int | None, nachkomma: int = 0) -> str:
    if wert is None:
        return "–"
    return f"{wert:.{nachkomma}f}"


def _kachel(titel: str, wert: str, einheit: str = "", gross: bool = False) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border_radius=10,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                ft.Text(titel, size=11, opacity=0.65),
                ft.Row(
                    spacing=3,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(wert, size=26 if gross else 18, weight=ft.FontWeight.BOLD),
                        ft.Text(einheit, size=11, opacity=0.65),
                    ],
                ),
            ],
        ),
    )


# ---------------------------------------------------------------------------
# Verbinden
# ---------------------------------------------------------------------------


def _verbinden_teil(page: ft.Page, state: AppState) -> ft.Control:
    ergebnisse = ft.Column(spacing=0)
    hinweis = ft.Text("", size=12, opacity=0.7)
    ring = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)

    def zeile(info: DeviceInfo) -> ft.Control:
        profil = profil_fuer_namen(info.name)
        teile = [profil.name if profil else "unbekanntes Gerät"]
        if info.rssi is not None:
            teile.append(f"{info.rssi} dBm")
        return ft.ListTile(
            leading=ft.Icon(ft.Icons.BLUETOOTH),
            title=ft.Text(info.name or info.id),
            subtitle=ft.Text("  ·  ".join(teile), size=12),
            trailing=ft.FilledTonalButton("Verbinden", on_click=verbinder(info)),
        )

    def verbinder(info: DeviceInfo) -> Callable[[], Any]:
        async def handler() -> None:
            await verbinden(info.id, info.name)

        return handler

    async def verbinden(device_id: str, name: str | None) -> None:
        hinweis.value = f"Verbinde mit {name or device_id} …"
        ring.visible = True
        page.update()
        if device_id.startswith(SIM_PREFIX):
            quelle: Any = SimulatedSource()
        elif state.ble_transport is not None:
            from trainingsapp.devices.polar import PolarQuelle

            quelle = PolarQuelle(state.ble_transport)
        else:
            return
        lauf = Messlauf(quelle, backup_basis=datenverzeichnis())
        state.messlauf = lauf
        try:
            await lauf.verbinden(device_id, name)
        except Exception as fehler:  # Gerät weg, Bluetooth aus, Berechtigung fehlt …
            state.messlauf = None
            ring.visible = False
            hinweis.value = f"Verbinden fehlgeschlagen: {fehler}"
            diagnose.content = _diagnose(_protokoll(quelle))
            page.update()
            return
        await _hintergrund(state, lauf, True, f"Verbunden mit {lauf.geraet_name}")

        async def laufen() -> None:
            try:
                await lauf.laufen()
            finally:
                await _hintergrund(state, lauf, False)

        page.run_task(laufen)
        state.neu_zeichnen()

    async def suchen() -> None:
        if state.ble_transport is None:
            hinweis.value = (
                "Bluetooth gibt es nur in der App auf dem Handy. "
                "Am Rechner zeigt der Simulator, wie es aussieht."
            )
            page.update()
            return
        from trainingsapp.devices.polar import PolarQuelle

        ring.visible = True
        hinweis.value = "Suche Geräte (8 s) — Gurt anfeuchten bzw. Sensor einschalten …"
        ergebnisse.controls = []
        page.update()
        try:
            gefunden = await PolarQuelle(state.ble_transport).scan(8.0)
        except Exception as fehler:
            gefunden = []
            hinweis.value = f"Suche fehlgeschlagen: {fehler}"
        else:
            hinweis.value = (
                f"{len(gefunden)} Gerät(e) gefunden."
                if gefunden
                else "Nichts gefunden. Ist Bluetooth an und der Sensor in der Nähe?"
            )
        ring.visible = False
        ergebnisse.controls = [zeile(i) for i in gefunden]
        page.update()

    def simulator(device_id: str, name: str) -> Callable[[], Any]:
        async def handler() -> None:
            await verbinden(device_id, name)

        return handler

    diagnose = ft.Container()

    return ft.Container(
        padding=16,
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Text("Gerät verbinden", size=18, weight=ft.FontWeight.W_600),
                ft.Text(
                    "Polar H10 (Brustgurt, RR-Intervalle) oder Polar Verity Sense "
                    "(optisch, Pulsintervalle). Den Gurt vorher anfeuchten.",
                    size=12,
                    opacity=0.7,
                ),
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.FilledButton("Geräte suchen", icon=ft.Icons.SEARCH, on_click=suchen),
                        ring,
                    ],
                ),
                hinweis,
                ergebnisse,
                diagnose,
                ft.Text("Ohne Gerät ausprobieren:", size=12, opacity=0.7),
                ft.Row(
                    wrap=True,
                    spacing=4,
                    controls=[
                        ft.TextButton(
                            "Simulator wie H10",
                            icon=ft.Icons.SCIENCE,
                            on_click=simulator(SIM_SYNTH, "Simulator H10"),
                        ),
                        ft.TextButton(
                            "Simulator wie Verity",
                            icon=ft.Icons.SCIENCE_OUTLINED,
                            on_click=simulator(SIM_PPI, "Simulator Verity"),
                        ),
                    ],
                ),
            ],
        ),
    )


# ---------------------------------------------------------------------------
# Live
# ---------------------------------------------------------------------------


def _live_teil(page: ft.Page, state: AppState, lauf: Messlauf) -> ft.Control:
    status_box = ft.Container()
    zahlen_box = ft.Container()
    rr_box = ft.Container()
    hf_box = ft.Container()
    aufnahme_box = ft.Container()
    diagnose_box = ft.Container()
    letzte = 0.0

    def fenster_wechseln(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.messung_fenster_s = int(e.control.selected[0])
            aktualisieren(erzwingen=True)

    def korrigiert_wechseln(e: ft.Event[ft.Switch]) -> None:
        state.messung_korrigiert = bool(e.control.value)
        aktualisieren(erzwingen=True)

    async def aufnahme_starten() -> None:
        lauf.aufnahme_starten()
        aktualisieren(erzwingen=True)
        await _hintergrund(state, lauf, True, f"Aufnahme läuft · {lauf.geraet_name}")

    async def aufnahme_stoppen() -> None:
        ergebnis = lauf.aufnahme_stoppen(datenverzeichnis())
        await _hintergrund(state, lauf, True, f"Verbunden mit {lauf.geraet_name}")
        if ergebnis is None:
            aktualisieren(erzwingen=True)
            return
        eintrag = HrvRecording(
            subject_id=state.profil.id,
            file_path=ergebnis.pfad.relative_to(messungenverzeichnis()).as_posix(),
            sha1=ergebnis.sha1,
            geraet=ergebnis.recording.geraet,
            geraet_profil=ergebnis.recording.geraet_profil or "ble_generic",
            intervall_quelle=ergebnis.recording.intervall_quelle or "ekg_rr",
            datenqualitaet=ergebnis.recording.effektive_qualitaet(),
            started_at=ergebnis.started_at,
            duration_s=ergebnis.dauer_s,
            coverage_pct=ergebnis.abdeckung_pct,
            n_gaps=ergebnis.n_luecken,
        )
        state.hrv.anlegen(eintrag)
        page.show_dialog(ft.SnackBar(ft.Text(f"Gespeichert: {ergebnis.pfad.name}")))
        await page.push_route(f"/messung/{eintrag.id}")

    async def trennen() -> None:
        if lauf.aufnahme is not None:
            page.show_dialog(
                ft.SnackBar(ft.Text("Erst die Aufnahme stoppen — sonst geht sie verloren."))
            )
            return
        await lauf.trennen()
        state.messlauf = None
        state.neu_zeichnen()

    def status_zeile() -> ft.Control:
        s = lauf.status
        farbe = {
            Verbindung.VERBUNDEN: ft.Colors.GREEN_400,
            Verbindung.VERBINDE: ft.Colors.AMBER_400,
            Verbindung.FEHLER: ROT,
        }.get(s.verbindung, ft.Colors.OUTLINE)
        teile = [lauf.geraet_name or "Gerät"]
        if s.batterie_prozent is not None:
            teile.append(f"Akku {s.batterie_prozent} %")
        if s.hautkontakt is False:
            teile.append("kein Hautkontakt")
        return ft.Column(
            spacing=2,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.CIRCLE, size=12, color=farbe),
                        ft.Text("  ·  ".join(teile), size=13, expand=True),
                    ],
                ),
                ft.Text(s.meldung, size=12, opacity=0.7) if s.meldung else ft.Container(),
            ],
        )

    def zahlen() -> ft.Control:
        k = lauf.live.kennzahlen()
        hf = k.hf_bpm if k.hf_bpm is not None else lauf.status.hf_bpm
        return ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=8,
            controls=[
                _kachel("Herzfrequenz", _zahl(hf), "bpm", gross=True),
                _kachel("RR", _zahl(k.rr_ms), "ms", gross=True),
                _kachel("RMSSD 30 s", _zahl(k.rmssd_30s, 1), "ms"),
                _kachel("SDNN 60 s", _zahl(k.sdnn_60s, 1), "ms"),
                _kachel("Schwankung 60 s", _zahl(k.schwankung_60s, 1), "bpm"),
                _kachel("Artefakte", f"{k.artefakte}", f"von {k.schlaege}"),
            ],
        )

    def kurven() -> tuple[ft.Control, ft.Control]:
        fenster = state.messung_fenster_s
        jetzt = lauf.jetzt_s()
        punkte = lauf.live.punkte(seit_s=max(0.0, jetzt - fenster))
        x_von, x_bis = max(0.0, jetzt - fenster), max(jetzt, float(fenster))
        mit_rr = [p for p in punkte if p.rr_ms > 0]
        if state.messung_korrigiert:
            rr_linie = [(p.t_s, p.rr_korr) for p in mit_rr if p.rr_korr is not None]
        else:
            rr_linie = [(p.t_s, float(p.rr_ms)) for p in mit_rr]
        artefakte = [(p.t_s, float(p.rr_ms)) for p in mit_rr if p.artefakt and 250 < p.rr_ms < 2200]
        rr = kurve(
            [
                Reihe(rr_linie, farbe=ft.Colors.PRIMARY),
                Reihe(artefakte, farbe=ROT, nur_punkte=True),
            ],
            einheit="RR ms",
            x_von=x_von,
            x_bis=x_bis,
        )
        hf_punkte = [(p.t_s, float(p.hf_bpm)) for p in punkte if p.hf_bpm > 0]
        hf = kurve(
            [Reihe(hf_punkte, farbe=ft.Colors.TERTIARY)],
            einheit="HF bpm",
            hoehe=130,
            x_von=x_von,
            x_bis=x_bis,
        )
        return rr, hf

    def aufnahme_teil() -> ft.Control:
        if lauf.aufnahme is None:
            return ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    ft.FilledButton(
                        "Aufnahme starten",
                        icon=ft.Icons.FIBER_MANUAL_RECORD,
                        on_click=aufnahme_starten,
                    ),
                    ft.TextButton("Trennen", icon=ft.Icons.BLUETOOTH_DISABLED, on_click=trennen),
                ],
            )
        n = len(lauf.aufnahme.beats)
        return ft.Row(
            wrap=True,
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, color=ROT, size=16),
                ft.Text(f"Aufnahme {_uhr(lauf.aufnahme_dauer_s())} · {n} Zeilen", size=14),
                ft.FilledButton("Stopp & speichern", icon=ft.Icons.STOP, on_click=aufnahme_stoppen),
            ],
        )

    def aktualisieren(erzwingen: bool = False) -> None:
        """Vom Messlauf nach neuen Werten gerufen — höchstens zweimal je Sekunde."""
        nonlocal letzte
        jetzt = time.monotonic()
        if not erzwingen and jetzt - letzte < 0.5:
            return
        letzte = jetzt
        status_box.content = status_zeile()
        zahlen_box.content = zahlen()
        rr_box.content, hf_box.content = kurven()
        aufnahme_box.content = aufnahme_teil()
        if not lauf.simulation:
            diagnose_box.content = _diagnose(_protokoll(lauf))
        # Ansicht nicht (mehr) auf der Seite — beim nächsten Aufbau geht es weiter.
        with contextlib.suppress(Exception):
            spalte.update()

    def beobachten(layout: bool) -> None:
        if layout and lauf.status.verbindung == Verbindung.GETRENNT:
            state.neu_zeichnen()
        else:
            aktualisieren(erzwingen=layout)

    spalte = ft.Column(
        spacing=12,
        controls=[
            status_box,
            zahlen_box,
            ft.Row(
                wrap=True,
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.SegmentedButton(
                        selected=[str(state.messung_fenster_s)],
                        segments=[ft.Segment(value=str(s), label=ft.Text(t)) for s, t in FENSTER],
                        on_change=fenster_wechseln,
                    ),
                    ft.Switch(
                        label="korrigiert",
                        value=state.messung_korrigiert,
                        on_change=korrigiert_wechseln,
                    ),
                ],
            ),
            rr_box,
            hf_box,
            ft.Text(
                "Rote Punkte: Artefakte (markiert, nicht verändert). Gespeichert werden immer "
                "die Rohwerte; korrigiert wird in der Aufzeichnung.",
                size=11,
                opacity=0.55,
            ),
            aufnahme_box,
            diagnose_box,
        ],
    )
    # Erstbefüllung ohne update() — die Spalte hängt noch nicht an der Seite.
    status_box.content = status_zeile()
    zahlen_box.content = zahlen()
    rr_box.content, hf_box.content = kurven()
    aufnahme_box.content = aufnahme_teil()
    lauf.beobachter = beobachten
    return ft.Container(padding=16, content=spalte)


# ---------------------------------------------------------------------------
# Aufzeichnungen
# ---------------------------------------------------------------------------


def _liste(page: ft.Page, state: AppState) -> ft.Control:
    eintraege = state.hrv.alle(state.profil.id)

    def oeffner(recording_id: str) -> Callable[[], Any]:
        async def handler() -> None:
            await page.push_route(f"/messung/{recording_id}")

        return handler

    zeilen: list[ft.Control] = [
        ft.Container(
            padding=ft.Padding.only(left=16, top=8),
            content=ft.Text("AUFZEICHNUNGEN", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
        )
    ]
    if not eintraege:
        zeilen.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=16, vertical=4),
                content=ft.Text("Noch keine Aufzeichnung.", opacity=0.6),
            )
        )
    for a in eintraege:
        lokal = a.started_at.astimezone()
        teile = [f"{lokal:%d.%m. %H:%M}", _uhr(a.duration_s), a.geraet or a.geraet_profil]
        if a.note:
            teile.append(a.note[:40])
        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.MONITOR_HEART_OUTLINED),
                title=ft.Text("  ·  ".join(teile[:2])),
                subtitle=ft.Text("  ·  ".join(teile[2:]), size=12),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
                on_click=oeffner(a.id),
            )
        )
    return ft.Column(spacing=0, controls=zeilen)


def messung(page: ft.Page, state: AppState) -> ft.Control:
    lauf = state.messlauf
    oben = (
        _live_teil(page, state, lauf)
        if lauf is not None and lauf.status.verbindung != Verbindung.GETRENNT
        else _verbinden_teil(page, state)
    )
    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
        controls=[oben, ft.Divider(height=1), _liste(page, state)],
    )


__all__ = ["messung"]
