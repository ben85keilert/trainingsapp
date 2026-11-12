"""Geräteprobe — Route ``/geraeteprobe``: Rohmitschnitt eines Geräts ohne Messung (Stufe 6).

Plan `docs/plan_diagnosemodus.md` §2.8. Erreichbar im Diagnosemodus aus der Gerätesuche der
Messung („Rohmitschnitt“ an jedem Treffer, auch an Geräten ohne Herzfrequenz-Dienst). Die
Ansicht verbindet, zeigt Dienste und Merkmale mit Namen (`hrv_core.geraete.gatt`), startet den
Mitschnitt (`devices.erkundung.Geraeteprobe`), nimmt Marken („jetzt bewegt“, „jetzt still“)
und am Ende ein kurzes Formular. Darunter die Proben auf dem Handy zum Teilen und Löschen.

Der Lauf lebt im `AppState` (``geraeteprobe``) — ein Neuaufbau der Ansicht unterbricht ihn
nicht; der rote Punkt zeigt ihn wie den Diagnosemodus einer Messung.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import flet as ft

from trainingsapp.config import datenverzeichnis
from trainingsapp.core import diagnose as dg
from trainingsapp.devices.erkundung import Geraeteprobe, probe_loeschen, probe_zip, proben
from trainingsapp.ui.components import diagnose_punkt
from trainingsapp.ui.components.dialoge import schliessen
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.weitergeben import weitergeben
from trainingsapp.ui.state import AppState

ROUTE = "/geraeteprobe"


def geraeteprobe_view(page: ft.Page, state: AppState) -> ft.View:
    ziel = getattr(state, "probe_ziel", None)
    probe: Geraeteprobe | None = getattr(state, "geraeteprobe", None)
    if probe is None and ziel is not None and state.ble_transport is not None:
        probe = Geraeteprobe(state.ble_transport, datenverzeichnis())
        state.geraeteprobe = probe
    kopf = ft.Text("", size=13)
    dienste_box = ft.Column(spacing=2, tight=True)
    stand_text = ft.Text("", size=12, font_family="monospace")
    knoepfe = ft.Row(spacing=8, wrap=True)
    proben_box = ft.Column(spacing=4, tight=True)

    def zeichnen() -> None:
        with contextlib.suppress(Exception):
            for c in (kopf, dienste_box, stand_text, knoepfe, proben_box):
                c.update()

    def kopf_neu() -> None:
        if probe is None:
            kopf.value = (
                "Kein Gerät gewählt — in der Messung „Geräte suchen“, dann „Rohmitschnitt“."
                if state.ble_transport is not None
                else "Bluetooth gibt es nur in der App auf dem Handy."
            )
            return
        teile = [probe.name or "Gerät", "verbunden" if probe.verbunden else "nicht verbunden"]
        if probe.getrennt_grund and not probe.verbunden:
            teile.append(f"getrennt: {probe.getrennt_grund}")
        if probe.laeuft:
            teile.append("● Rohmitschnitt läuft")
        kopf.value = " · ".join(teile)

    def dienste_neu() -> None:
        zeilen: list[ft.Control] = []
        for d in probe.dienste if probe is not None else []:
            zeilen.append(ft.Text(d["name"], size=13, weight=ft.FontWeight.W_600))
            for m in d["merkmale"]:
                was = ", ".join(m["eigenschaften"]) or "–"
                zeilen.append(ft.Text(f"   {m['name']} · {was}", size=12, opacity=0.8))
        dienste_box.controls = zeilen

    def knoepfe_neu() -> None:
        if probe is None:
            knoepfe.controls = []
        elif probe.laeuft:
            knoepfe.controls = [
                ft.FilledTonalButton("jetzt bewegt", on_click=lambda: marke("bewegt")),
                ft.FilledTonalButton("jetzt still", on_click=lambda: marke("still")),
                ft.OutlinedButton("Marke", on_click=lambda: marke(None)),
                ft.FilledButton("Stopp", icon=ft.Icons.STOP, on_click=stopp_fragen),
            ]
        elif probe.verbunden:
            knoepfe.controls = [
                ft.FilledButton(
                    "Rohmitschnitt starten", icon=ft.Icons.FIBER_MANUAL_RECORD, on_click=starten
                )
            ]
        else:
            knoepfe.controls = [ft.OutlinedButton("Verbinden", on_click=verbinden)]

    def proben_neu() -> None:
        zeilen: list[ft.Control] = []
        for p in proben(datenverzeichnis()):
            ordner = p["ordner"]
            text = f"{p['name']} · {dg.groesse_text(p['bytes'])}"
            if p["formular"].get("was"):
                text += f" · {p['formular']['was']}"
            zeilen.append(
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(text, size=12, expand=True),
                        ft.IconButton(
                            ft.Icons.SHARE,
                            tooltip="Teilen (ohne Bluetooth-Adresse)",
                            on_click=lambda _e, o=ordner: page.run_task(teilen, o),
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            tooltip="Löschen",
                            on_click=lambda _e, o=ordner: loeschen(o),
                        ),
                    ],
                )
            )
        proben_box.controls = zeilen or [hinweis("Noch keine Geräteprobe auf dem Handy.")]

    def alles_neu() -> None:
        kopf_neu()
        dienste_neu()
        knoepfe_neu()
        proben_neu()
        zeichnen()

    async def verbinden() -> None:
        # Jeder Neuaufbau der Ansicht käme sonst mit einem weiteren Aufbau dazu (H108)
        if probe is None or ziel is None or probe.verbindet:
            return
        kopf.value = f"Verbinde mit {ziel[1] or ziel[0]} …"
        zeichnen()
        try:
            await probe.verbinden(ziel[0], ziel[1])
        except Exception as e:
            kopf.value = f"Verbinden fehlgeschlagen: {e}"
            zeichnen()
            return
        alles_neu()

    async def starten() -> None:
        if probe is None:
            return
        try:
            await probe.starten()
        except Exception as e:  # Speicher voll, Ordner nicht anzulegen (H108)
            kopf.value = f"Rohmitschnitt nicht gestartet: {e}"
            diagnose_punkt.aktualisieren(page, state)
            zeichnen()
            return
        diagnose_punkt.aktualisieren(page, state)
        alles_neu()
        page.run_task(takt)

    async def takt() -> None:
        while probe is not None and probe.laeuft and gebaut["route"] == state.route_nummer:
            s = probe.stand()
            pakete = ", ".join(f"{k} {v}" for k, v in s["pakete"].items()) or "noch keine"
            stand_text.value = (
                f"{dg.dauer_text(s['seit_s'])} · {dg.groesse_text(s['bytes'])} · "
                f"gelesen {s['gelesen']} · abonniert {s['abonniert']} · Fehler {s['fehler']}\n"
                f"Pakete: {pakete}"
            )
            with contextlib.suppress(Exception):
                stand_text.update()
            await asyncio.sleep(1.0)

    def marke(phase: str | None) -> None:
        if probe is not None:
            probe.marke(phase)
            page.show_dialog(ft.SnackBar(ft.Text(f"Marke: {phase or 'frei'}")))

    def stopp_fragen() -> None:
        hersteller = ft.TextField(label="Hersteller und Modell", dense=True)
        was = ft.TextField(label="Was getan (still, bewegt, Treppe …)", dense=True)
        vergleich = ft.TextField(label="Vergleichswert (z. B. Puls laut Uhr 64)", dense=True)
        dialog: ft.AlertDialog

        async def beenden() -> None:
            schliessen(dialog)
            if probe is None:
                return
            meldung = "Geräteprobe gespeichert."
            try:
                await probe.beenden(
                    {
                        "hersteller": hersteller.value or "",
                        "was": was.value or "",
                        "vergleich": vergleich.value or "",
                    }
                )
            except Exception as e:
                # Formular nicht zu schreiben (Speicher voll, H108): Die Probe ist trotzdem
                # zu Ende — sonst blieben sie und der rote Punkt stehen
                meldung = f"Geräteprobe beendet, aber nicht vollständig gespeichert: {e}"
            state.geraeteprobe = None
            diagnose_punkt.aktualisieren(page, state)
            page.show_dialog(ft.SnackBar(ft.Text(meldung)))
            state.neu_zeichnen()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Rohmitschnitt beenden"),
            content=ft.Column(tight=True, spacing=8, controls=[hersteller, was, vergleich]),
            actions=[
                ft.TextButton("Weiter mitschneiden", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Beenden und speichern", on_click=beenden),
            ],
        )
        page.show_dialog(dialog)

    async def teilen(ordner: Any) -> None:
        daten = await asyncio.to_thread(probe_zip, ordner)
        await weitergeben(page, f"geraeteprobe_{ordner.name}.zip", daten, "application/zip")

    def loeschen(ordner: Any) -> None:
        dialog: ft.AlertDialog

        def ja() -> None:
            schliessen(dialog)
            with contextlib.suppress(OSError, ValueError):
                probe_loeschen(ordner)
            proben_neu()
            zeichnen()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Geräteprobe löschen?"),
            content=ft.Text("Mitschnitt und Formular gehen weg."),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Löschen", on_click=ja),
            ],
        )
        page.show_dialog(dialog)

    gebaut = {"route": state.route_nummer}
    kopf_neu()
    dienste_neu()
    knoepfe_neu()
    proben_neu()
    if probe is not None and not probe.verbunden and not probe.laeuft and ziel is not None:
        page.run_task(verbinden)
    if probe is not None and probe.laeuft:
        page.run_task(takt)
    inhalt = ft.Column(
        spacing=14,
        controls=[
            karte(titel("Gerät"), kopf, knoepfe, stand_text),
            karte(
                titel("Dienste und Merkmale"),
                dienste_box,
                hinweis(
                    "Mitgeschrieben wird nur dieses Gerät — jedes Merkmal mit Benachrichtigung, "
                    "Lesbares einmal. Die App schreibt nie auf das Gerät und liest weder "
                    "Seriennummer noch Systemkennung."
                ),
            ),
            karte(
                titel("Geräteproben auf dem Handy"),
                proben_box,
                hinweis(
                    "Teilen gibt den Mitschnitt ohne Bluetooth-Adresse weiter. Proben mit dem "
                    "Puls einer anderen Person nur mit ihrer Einwilligung weitergeben."
                ),
            ),
        ],
    )
    return ft.View(
        route=ROUTE,
        appbar=ft.AppBar(title=ft.Text("Geräteprobe")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


__all__ = ["ROUTE", "geraeteprobe_view"]
