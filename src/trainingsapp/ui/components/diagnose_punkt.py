"""Der rote Punkt oben rechts, solange der Diagnosemodus aufzeichnet — und sein Stand-Blatt.

Plan `docs/plan_diagnosemodus.md` §2.4 (Ben, 4.11.2026: „wichtig zu wissen + das kostet mehr
Batterie“; P110: oben rechts, oben links liegt der Zurück-Pfeil). Der Punkt liegt in
``page.overlay`` — über jeder Ansicht und unberührt vom Neuaufbau in `app.zeige_route`
(der räumt nur ``page.views``). Er blinkt mit 1 Hz (eine Aufgabe schaltet seine Deckkraft,
nur er wird gezeichnet). Ein Tipp öffnet den **Stand**: seit wann, wie viel, Pakete je Strom
und Sekunde, Lücken, Akku von Gurt und Handy — mit „Diagnose beenden“ (die Zusatzströme
hören auf, die Messung läuft weiter).

`aktualisieren` ist idempotent: `zeige_route` ruft es bei jedem Aufbau, Sensorblatt und
Stand-Blatt nach jedem Wechsel.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import flet as ft

from trainingsapp.core import diagnose as dg
from trainingsapp.ui.components import marken_leiste
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen

#: Halbe Periode des Blinkens (s) — 1 Hz
BLINK_S = 0.5
_NAMEN = {"hr": "Herzfrequenz", "ecg": "EKG", "acc": "Beschleunigung", "ppi": "PPI"}


def _aktiv(state: Any) -> bool:
    """Zeichnet der Diagnosemodus auf — an einer Messung oder als Geräteprobe?"""
    lauf = getattr(state, "messlauf", None)
    probe = getattr(state, "geraeteprobe", None)
    return bool(
        (lauf is not None and getattr(lauf, "diagnose_aktiv", False))
        or (probe is not None and getattr(probe, "laeuft", False))
    )


def aktualisieren(page: ft.Page, state: Any) -> None:
    """Punkt zeigen oder wegnehmen — je nachdem, ob der Diagnosemodus aufzeichnet."""
    punkt = getattr(state, "diagnose_punkt", None)
    # Controls vergleichen ihre Felder (Dataclass) — darum nach Identität suchen
    da = punkt is not None and any(p is punkt for p in page.overlay)
    if _aktiv(state):
        if da:
            return
        punkt = _bauen(page, state)
        page.overlay.append(punkt)
        state.diagnose_punkt = punkt
        page.run_task(_blinken, page, state, punkt)
        with contextlib.suppress(Exception):
            page.update()
    elif punkt is not None:
        state.diagnose_punkt = None
        page.overlay[:] = [p for p in page.overlay if p is not punkt]
        with contextlib.suppress(Exception):
            page.update()


def _bauen(page: ft.Page, state: Any) -> ft.Control:
    licht = ft.Container(
        width=12,
        height=12,
        border_radius=6,
        bgcolor=ft.Colors.RED_600,
        animate_opacity=200,
        border=ft.Border.all(1.5, ft.Colors.WHITE),
    )
    return ft.SafeArea(
        right=0,
        top=0,
        content=ft.Container(
            width=30,
            height=30,
            alignment=ft.Alignment.CENTER,
            content=licht,
            tooltip="Diagnose zeichnet auf — Stand",
            on_click=lambda: page.show_dialog(stand_blatt(page, state)),
        ),
    )


async def _blinken(page: ft.Page, state: Any, punkt: ft.Control) -> None:
    licht = punkt.content.content  # type: ignore[attr-defined]
    an = True
    while getattr(state, "diagnose_punkt", None) is punkt:
        if not _aktiv(state):
            aktualisieren(page, state)
            return
        an = not an
        licht.opacity = 1.0 if an else 0.25
        with contextlib.suppress(Exception):
            licht.update()
        await asyncio.sleep(BLINK_S)


def stand_text(stand: dict[str, Any], akku_handy: int | None = None) -> list[str]:
    """Die Zeilen des Stands (ohne flet testbar).

    >>> stand_text({"seit_s": 125, "bytes": 2_100_000, "zeilen": 900,
    ...     "stroeme": {"hr": {"pakete_s": 1.0, "proben_s": 1.0, "pakete": 120},
    ...                 "acc": {"pakete_s": 5.6, "proben_s": 200.0, "pakete": 670}},
    ...     "seq_luecken": 0, "trennungen": 1, "akku": 80, "verzug_ms": 12,
    ...     "schreibfehler": 0}, 64)  # doctest: +NORMALIZE_WHITESPACE
    ['seit 2 min · 2,1 MB · 900 Zeilen', 'Herzfrequenz: 1 Pakete/s', 'Beschleunigung: 200 Hz',
     'Lücken: 0 · Trennungen: 1', 'Akku Gurt 80 % · Handy 64 % · Verzug 12 ms']
    """
    zeilen = [
        f"seit {dg.dauer_text(stand.get('seit_s', 0))} · {dg.groesse_text(stand.get('bytes', 0))}"
        f" · {stand.get('zeilen', 0)} Zeilen"
    ]
    for name, s in (stand.get("stroeme") or {}).items():
        if name == "hr":
            zeilen.append(f"{_NAMEN.get(name, name)}: {s['pakete_s']:g} Pakete/s")
        elif name in ("ecg", "acc"):
            zeilen.append(f"{_NAMEN.get(name, name)}: {s['proben_s']:g} Hz")
        else:
            zeilen.append(f"{_NAMEN.get(name, name)}: {s['pakete']} Pakete")
    zeilen.append(
        f"Lücken: {stand.get('seq_luecken', 0)} · Trennungen: {stand.get('trennungen', 0)}"
    )
    akku = []
    if stand.get("akku") is not None:
        akku.append(f"Akku Gurt {stand['akku']} %")
    if akku_handy is not None:
        akku.append(f"Handy {akku_handy} %")
    akku.append(f"Verzug {stand.get('verzug_ms', 0)} ms")
    zeilen.append(" · ".join(akku))
    if stand.get("schreibfehler"):
        zeilen.append(f"Schreibfehler: {stand['schreibfehler']} (Speicher voll?)")
    return zeilen


def stand_blatt(page: ft.Page, state: Any) -> ft.BottomSheet:
    """Was gerade aufgezeichnet wird — im Sekundentakt nachgezogen, solange offen."""
    lauf = state.messlauf
    text = ft.Text("", size=13)
    offen: dict[str, Any] = {"ja": True, "akku_handy": None}
    blatt: ft.BottomSheet

    def neu() -> None:
        probe = getattr(state, "geraeteprobe", None)
        if probe is not None and probe.laeuft:
            s = probe.stand()
            text.value = (
                f"Geräteprobe {probe.name}: seit {dg.dauer_text(s['seit_s'])} · "
                f"{dg.groesse_text(s['bytes'])} · Pakete "
                + (", ".join(f"{k} {v}" for k, v in s["pakete"].items()) or "–")
            )
        elif lauf is not None:
            text.value = "\n".join(stand_text(lauf.diagnose_stand(), offen["akku_handy"]))
        else:
            return
        with contextlib.suppress(Exception):
            text.update()

    async def takt() -> None:
        transport = getattr(state, "ble_transport", None)
        akku = getattr(transport, "akku", None)
        if callable(akku):
            with contextlib.suppress(Exception):
                werte = await asyncio.wait_for(akku(), timeout=5.0)
                if isinstance(werte, dict):
                    offen["akku_handy"] = werte.get("prozent")
        while offen["ja"] and _aktiv(state):
            neu()
            await asyncio.sleep(1.0)

    async def beenden() -> None:
        offen["ja"] = False
        schliessen(blatt)
        if lauf is not None:
            await lauf.diagnose_beenden()
        aktualisieren(page, state)
        marken_leiste.aktualisieren(page, state)
        state.neu_zeichnen()
        page.show_dialog(ft.SnackBar(ft.Text("Diagnose beendet — die Messung läuft weiter.")))

    def leiste_zeigen() -> None:
        state.diagnose_leiste_offen = True
        schliessen(blatt)
        marken_leiste.aktualisieren(page, state)
        state.neu_zeichnen()

    def zu(_e: Any = None) -> None:
        offen["ja"] = False

    neu()
    blatt = ft.BottomSheet(
        scrollable=True,
        show_drag_handle=True,
        on_dismiss=zu,
        content=blatt_spalte(
            [
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.FIBER_MANUAL_RECORD, color=ft.Colors.RED_600, size=16),
                        ft.Text("Diagnose zeichnet auf", size=17, weight=ft.FontWeight.W_600),
                    ],
                ),
                text,
                ft.Text(
                    "Mit EKG und Beschleunigung braucht der Gurt deutlich mehr Akku. Die Datei "
                    "liegt neben der Messung; „Teilen“ in der Auswertung gibt sie weiter — "
                    "ohne Bluetooth-Adresse.",
                    size=11,
                    opacity=0.6,
                ),
            ],
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    wrap=True,
                    controls=[
                        ft.TextButton("Marken-Leiste zeigen", on_click=leiste_zeigen),
                        ft.FilledTonalButton(
                            "Diagnose beenden", icon=ft.Icons.STOP, on_click=beenden
                        ),
                    ],
                )
            ],
            rand=ft.Padding.only(left=16, right=16, bottom=12),
        ),
    )
    page.run_task(takt)
    return blatt


__all__ = ["BLINK_S", "aktualisieren", "stand_blatt", "stand_text"]
