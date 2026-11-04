"""Sensorblatt des Diagnosemodus: was das Gerät kann, was sich einschalten lässt, Vorabtest.

Plan `docs/plan_diagnosemodus.md` §2.3. Geöffnet vom Knopf „Diagnosemodus“ an der
Gerätezeile der Messung (nur wenn in den Einstellungen angeboten). Beim Öffnen:

1. Merkmalsliste des PMD-Dienstes lesen und die Einstellungen abfragen (`PolarQuelle`) —
   daraus „✓ geprüft“ statt „laut Profil“;
2. die gewählten Ströme einschalten und höchstens 20 s prüfen, ob sie mit ihrer Rate kommen
   (`Messlauf.vorabtest_beginnen`/`vorabtest_stand`); fehlt etwas, steht es da — starten
   lässt sich trotzdem.

„Mit Diagnose aufnehmen“ merkt den Diagnosemodus für diese Messung vor
(`Messlauf.diagnose_vormerken`) und startet die Aufnahme wie „Aufnahme starten“; läuft
schon eine, beginnt der Mitschnitt sofort. Zu ohne Start: Ströme wie vorher.

Gezeichnet wird nur, was sich ändert (die Zeilen nach dem Lesen, die Zeile des
Vorabtests im Takt) — nie das ganze Blatt.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.core import diagnose as dg
from trainingsapp.core.hrv_einstellungen import ACC_BEREICHE, ACC_RATEN
from trainingsapp.ui.components import diagnose_punkt, marken_leiste
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import schliessen
from trainingsapp.ui.state import AppState

#: Takt, in dem das Blatt den Vorabtest nachzieht (s)
TAKT_S = 0.5

_NAMEN = {"hr": "Herzfrequenz", "ecg": "EKG", "acc": "Beschleunigung"}


def _acc_wahl(state: AppState) -> tuple[int, int] | None:
    e = state.hrv_einstellungen()
    return (e.diagnose_acc_hz, e.diagnose_acc_g) if e.diagnose_acc else None


def sensorblatt(
    page: ft.Page,
    state: AppState,
    lauf: Any,
    *,
    aufnahme_starten: Callable[[], Awaitable[None]],
) -> ft.BottomSheet:
    """Das Blatt (siehe Modultext). ``aufnahme_starten``: der Start der Messansicht."""
    zustand: dict[str, Any] = {"gestartet": False, "offen": True, "test": 0}
    blatt: ft.BottomSheet
    quelle = lauf.quelle
    zeilen_box = ft.Column(spacing=4, tight=True)
    acc_box = ft.Row(spacing=8, wrap=True, visible=False)
    fehlt_text = ft.Text("", size=12, opacity=0.7)
    summe_text = ft.Text("", size=12)
    test_text = ft.Text("Vorabtest beginnt …", size=12)
    kopf_text = ft.Text("", size=13)

    def einst() -> Any:
        return state.hrv_einstellungen()

    def setzen(**werte: Any) -> None:
        e = einst()
        for k, v in werte.items():
            setattr(e, k, v)
        state.hrv_einstellungen_setzen(e)

    def kopf_neu() -> None:
        s = lauf.status
        teile = [lauf.geraet_name or "Gerät", "verbunden" if lauf.verbunden else "getrennt"]
        if s.batterie_prozent is not None:
            teile.append(f"Akku {s.batterie_prozent} %")
        kopf_text.value = " · ".join(teile)

    def zeilen_neu() -> None:
        e = einst()
        profil = lauf.profil
        zeilen = dg.sensoren(
            profil.faehigkeiten if profil is not None else (),
            dienste=getattr(quelle, "dienste", ()),
            merkmale=getattr(quelle, "pmd_merkmale", None),
            acc_hz=e.diagnose_acc_hz,
        )
        controls: list[ft.Control] = []
        for z in zeilen:
            if z.schaltbar:
                an = e.diagnose_ekg if z.schluessel == "ecg" else e.diagnose_acc
                rechts: ft.Control = ft.Switch(
                    value=an,
                    on_change=lambda ev, k=z.schluessel: umgeschaltet(k, bool(ev.control.value)),
                )
            else:
                rechts = ft.Text("immer" if z.immer else z.hinweis or "–", size=12, opacity=0.7)
            controls.append(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=0,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(z.name, size=14),
                                ft.Text(
                                    z.zustand_text
                                    + (f" · ~{z.mb_h:g} MB/h" if z.mb_h else "")
                                    + (f" · {z.hinweis}" if z.hinweis and z.schaltbar else ""),
                                    size=11,
                                    opacity=0.7,
                                ),
                            ],
                        ),
                        rechts,
                    ],
                )
            )
        zeilen_box.controls = controls
        fehlt = dg.fehlende(zeilen)
        fehlt_text.value = f"Hat dieses Gerät nicht: {fehlt}" if fehlt else ""
        fehlt_text.visible = bool(fehlt)
        hat_acc = any(z.schluessel == "acc" for z in zeilen)
        hat_ekg = any(z.schluessel == "ecg" for z in zeilen)
        acc_box.visible = hat_acc and e.diagnose_acc
        menge = dg.menge_mb_h(
            ekg=hat_ekg and e.diagnose_ekg,
            acc_hz=e.diagnose_acc_hz if hat_acc and e.diagnose_acc else None,
        )
        summe_text.value = (
            f"Rohmitschnitt aller Pakete, zusammen etwa {menge:g} MB je Stunde. "
            f"Marken: Leiste {'unten' if e.diagnose_leiste == 'unten' else 'als Knopf'}"
            + (" · Uhr ⏯" if e.uhr_medien and e.diagnose_uhr else "")
            + "."
        )

    def zeichnen() -> None:
        with contextlib.suppress(Exception):
            for c in (kopf_text, zeilen_box, acc_box, fehlt_text, summe_text, test_text):
                c.update()

    def gewuenscht() -> tuple[bool, tuple[int, int] | None]:
        e = einst()
        profil = lauf.profil
        caps = set(profil.faehigkeiten) if profil is not None else set()
        ekg = e.diagnose_ekg and "pmd_ecg" in caps
        acc = _acc_wahl(state) if "pmd_acc" in caps else None
        return ekg, acc

    def umgeschaltet(schluessel: str, an: bool) -> None:
        setzen(**{"diagnose_ekg" if schluessel == "ecg" else "diagnose_acc": an})
        zeilen_neu()
        zeichnen()
        page.run_task(vorabtest)

    def rate_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        with contextlib.suppress(TypeError, ValueError):
            setzen(diagnose_acc_hz=int(ev.control.value or 200))
        zeilen_neu()
        zeichnen()
        page.run_task(vorabtest)

    def bereich_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
        with contextlib.suppress(TypeError, ValueError):
            setzen(diagnose_acc_g=int(ev.control.value or 8))
        page.run_task(vorabtest)

    acc_box.controls = [
        ft.Dropdown(
            label="Rate",
            width=130,
            dense=True,
            value=str(einst().diagnose_acc_hz),
            options=[ft.DropdownOption(key=str(r), text=f"{r} Hz") for r in ACC_RATEN],
            on_select=rate_gewaehlt,
        ),
        ft.Dropdown(
            label="Bereich",
            width=130,
            dense=True,
            value=str(einst().diagnose_acc_g),
            options=[ft.DropdownOption(key=str(g), text=f"{g} g") for g in ACC_BEREICHE],
            on_select=bereich_gewaehlt,
        ),
    ]

    async def vorabtest() -> None:
        zustand["test"] += 1
        nummer = zustand["test"]
        ekg, acc = gewuenscht()
        test_text.value = "Vorabtest: Ströme starten …"
        zeichnen()
        await lauf.vorabtest_beginnen(ekg=ekg, acc=acc)
        while zustand["offen"] and nummer == zustand["test"] and not zustand["gestartet"]:
            stand = lauf.vorabtest_stand(ekg=ekg, acc=acc)
            teile = []
            for name, v in stand["stroeme"].items():
                einheit = "/s" if name == "hr" else " Hz"
                zeichen = "✓" if v["ok"] else "…" if not stand["fertig"] else "✗"
                teile.append(f"{_NAMEN.get(name, name)} {v['rate']:g}{einheit} {zeichen}")
            if stand["fertig"]:
                fehlt = [_NAMEN.get(n, n) for n, v in stand["stroeme"].items() if not v["ok"]]
                schluss = (
                    "alles kommt an."
                    if not fehlt
                    else f"es fehlt {', '.join(fehlt)} — starten geht trotzdem."
                )
                test_text.value = "Vorabtest: " + " · ".join(teile) + " — " + schluss
                kopf_neu()
                zeichnen()
                return
            test_text.value = f"Vorabtest ({stand['seit_s']:.0f} s): " + " · ".join(teile)
            with contextlib.suppress(Exception):
                test_text.update()
            await asyncio.sleep(TAKT_S)

    async def vorbereiten() -> None:
        """Merkmale lesen, Einstellungen fragen, dann der Vorabtest."""
        with contextlib.suppress(Exception):
            if hasattr(quelle, "merkmale_lesen"):
                await quelle.merkmale_lesen()
            if hasattr(quelle, "einstellungen_abfragen"):
                await quelle.einstellungen_abfragen()
        if not zustand["offen"]:
            return
        kopf_neu()
        zeilen_neu()
        zeichnen()
        await vorabtest()

    async def starten() -> None:
        ekg, acc = gewuenscht()
        e = einst()
        zustand["gestartet"] = True
        lauf.diagnose_vormerken(
            ekg=ekg,
            acc=acc,
            kopf={
                "marken": {
                    "leiste": e.diagnose_leiste,
                    "uhr": bool(e.uhr_medien and e.diagnose_uhr),
                }
            },
        )
        schliessen(blatt)
        if lauf.aufnahme is None:
            await aufnahme_starten()
        state.diagnose_leiste_offen = e.diagnose_leiste == "unten"
        diagnose_punkt.aktualisieren(page, state)
        marken_leiste.aktualisieren(page, state)
        state.neu_zeichnen()

    def zu(_e: Any = None) -> None:
        zustand["offen"] = False
        if not zustand["gestartet"]:
            page.run_task(lauf.vorabtest_abbrechen)

    kopf_neu()
    zeilen_neu()
    laeuft = lauf.aufnahme is not None
    blatt = ft.BottomSheet(
        scrollable=True,
        show_drag_handle=True,
        on_dismiss=zu,
        content=blatt_spalte(
            [
                ft.Text("Diagnosemodus", size=17, weight=ft.FontWeight.W_600),
                kopf_text,
                zeilen_box,
                acc_box,
                fehlt_text,
                summe_text,
                test_text,
                ft.Text(
                    "Alles bleibt auf dem Handy. Solange aufgezeichnet wird, blinkt oben "
                    "rechts ein roter Punkt; ein Tipp darauf zeigt den Stand.",
                    size=11,
                    opacity=0.6,
                ),
            ],
            [
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton("Abbrechen", on_click=lambda: schliessen(blatt)),
                        ft.FilledButton(
                            "Diagnose starten" if laeuft else "Mit Diagnose aufnehmen",
                            icon=ft.Icons.FIBER_MANUAL_RECORD,
                            on_click=starten,
                        ),
                    ],
                )
            ],
            rand=ft.Padding.only(left=16, right=16, bottom=12),
        ),
    )
    page.run_task(vorbereiten)
    return blatt


def diagnosemodus_knopf(
    page: ft.Page,
    state: AppState,
    lauf: Any,
    *,
    aufnahme_starten: Callable[[], Awaitable[None]],
) -> ft.Control:
    """Der Knopf an der Gerätezeile — nur, wenn angeboten, möglich und noch nicht aktiv."""
    from trainingsapp import config

    sichtbar = (
        config.ist_aktiv("diagnosemodus")
        and state.hrv_einstellungen().diagnose_anbieten
        and bool(getattr(lauf, "diagnose_moeglich", False))
        and not getattr(lauf, "diagnose_aktiv", False)
        and lauf.verbunden
    )
    return ft.TextButton(
        "Diagnosemodus",
        icon=ft.Icons.BUG_REPORT_OUTLINED,
        visible=sichtbar,
        on_click=lambda: page.show_dialog(
            sensorblatt(page, state, lauf, aufnahme_starten=aufnahme_starten)
        ),
    )


__all__ = ["TAKT_S", "diagnosemodus_knopf", "sensorblatt"]
