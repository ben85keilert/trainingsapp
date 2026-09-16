"""Handler in Flet — die wichtigsten on_…-Ereignisse auf einer Seite.

Start:  uv run flet run -d docs/tutorial/Z_grundlagen/beispiel_handler.py

Jeder Block unten gehört zu einem Abschnitt in handler.md. Das Protokoll
rechts zeigt, welcher Handler wann gefeuert hat — Ereignisname, Control und
Nutzdaten. Ausprobieren, dann den Text daneben lesen.
"""

import asyncio
import time

import flet as ft

UEBUNGEN = {"kniebeuge": "Kniebeuge", "plank": "Plank", "rudern": "Rudern"}


def main(page: ft.Page) -> None:
    page.title = "Handler"
    page.padding = 20
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)

    # --- Protokoll: jeder Handler schreibt eine Zeile hinein ----------------

    protokoll = ft.ListView(expand=True, spacing=2, auto_scroll=True)

    def log(e: ft.ControlEvent | None, text: str) -> None:
        """Ereignisname und Control-Typ voranstellen, wenn ein Event da ist."""
        kopf = f"[{e.name} @ {type(e.control).__name__}] " if e is not None else "[von Hand] "
        protokoll.controls.append(ft.Text(kopf + text, size=12, font_family="monospace"))

    # --- 1. on_click: die Grundform, ein Handler für viele Knöpfe -----------

    def geklickt(e: ft.ControlEvent) -> None:
        # e.control.data trägt die id — derselbe Handler für alle drei Knöpfe.
        log(e, f"data={e.control.data!r}")

    knoepfe_data = ft.Row(
        [ft.Button(name, data=key, on_click=geklickt) for key, name in UEBUNGEN.items()]
    )

    # --- 2. Lambda mit Default-Argument (k=key friert den Wert ein) ---------

    knoepfe_lambda = ft.Row(
        [
            ft.OutlinedButton(name, on_click=lambda e, k=key: log(e, f"lambda k={k!r}"))
            for key, name in UEBUNGEN.items()
        ]
    )

    # --- 3. on_change feuert bei jedem Zeichen, on_submit bei Enter ---------

    treffer = ft.Text("3 Treffer")

    def gefiltert(e: ft.ControlEvent) -> None:
        suchtext = e.control.value.lower()
        anzahl = sum(1 for name in UEBUNGEN.values() if suchtext in name.lower())
        treffer.value = f"{anzahl} Treffer"
        log(e, f"value={e.control.value!r}")

    async def eingegeben(e: ft.ControlEvent) -> None:
        log(e, f"Enter mit value={e.control.value!r}")
        e.control.value = ""
        treffer.value = "3 Treffer"
        await e.control.focus()  # Coroutine → der Handler muss async sein

    suchfeld = ft.TextField(label="Suchen (Enter leert)", on_change=gefiltert, on_submit=eingegeben)

    # --- 4. Slider: on_change viele Male, on_change_end einmal --------------

    zieh_zaehler = 0
    slider_anzeige = ft.Text("30 s")

    def gezogen(e: ft.ControlEvent) -> None:
        nonlocal zieh_zaehler
        zieh_zaehler += 1
        slider_anzeige.value = f"{e.control.value:.0f} s  (on_change #{zieh_zaehler})"

    def losgelassen(e: ft.ControlEvent) -> None:
        nonlocal zieh_zaehler
        log(e, f"Endwert {e.control.value:.0f} nach {zieh_zaehler} on_change-Aufrufen")
        zieh_zaehler = 0

    slider = ft.Slider(min=10, max=120, value=30, on_change=gezogen, on_change_end=losgelassen)

    # --- 5. Switch und Checkbox: e.control.value ist bool ------------------

    def bool_wert(e: ft.ControlEvent) -> None:
        log(e, f"value={e.control.value}")

    schalter = ft.Switch(label="Dunkelmodus", on_change=bool_wert)
    haken = ft.Checkbox(label="Erledigt", on_change=bool_wert)

    # --- 6. async-Handler: Rechnung im Thread, Oberfläche bleibt bedienbar --

    def schwere_rechnung() -> int:
        time.sleep(2)  # steht für hrv_core.kennzahlen(...) — reines Rechnen
        return 42

    async def auswerten(e: ft.ControlEvent) -> None:
        e.control.disabled = True
        e.control.update()  # sofort grau — das Auto-Update käme erst nach dem await
        log(e, "Rechnung gestartet, Slider bleibt beweglich")
        ergebnis = await asyncio.to_thread(schwere_rechnung)
        log(e, f"Ergebnis {ergebnis}")
        e.control.disabled = False  # Auto-Update erledigt den Rest

    def blockieren(e: ft.ControlEvent) -> None:
        log(e, "2 s time.sleep — nichts geht mehr")
        time.sleep(2)  # ABSICHTLICH FALSCH: friert die ganze Oberfläche ein
        log(e, "wieder da")

    # --- 7. Exception im Handler: Terminal lesen, kein Auto-Update ----------

    def absturz(e: ft.ControlEvent) -> None:
        log(e, "diese Zeile erscheint erst beim NÄCHSTEN Ereignis")
        raise ValueError("absichtlicher Fehler — Traceback steht im Terminal")

    # --- 8. Seiten-Handler: Tastatur und Fenstergröße -----------------------

    def taste(e: ft.KeyboardEvent) -> None:
        mods = "+".join(m for m, an in (("ctrl", e.ctrl), ("shift", e.shift), ("alt", e.alt)) if an)
        log(e, f"key={e.key!r} {mods}")

    def groesse(e: ft.PageResizeEvent) -> None:
        log(e, f"{e.width:.0f} x {e.height:.0f}")

    page.on_keyboard_event = taste
    page.on_resize = groesse

    # --- 9. Außerhalb eines Handlers: kein Ereignis, kein Auto-Update -------

    async def aus_einem_task() -> None:
        await asyncio.sleep(1.5)
        log(None, "aus einem Task, OHNE update() — sichtbar erst beim nächsten Ereignis")
        await asyncio.sleep(3)
        log(None, "aus einem Task, MIT page.update() — sofort sichtbar")
        page.update()

    # --- Aufbau ----------------------------------------------------------------

    def abschnitt(titel: str, *controls: ft.Control) -> ft.Column:
        return ft.Column([ft.Text(titel, weight=ft.FontWeight.BOLD), *controls], spacing=6)

    links = ft.Column(
        [
            abschnitt("1. on_click mit data", knoepfe_data),
            abschnitt("2. Lambda mit k=key", knoepfe_lambda),
            abschnitt("3. on_change / on_submit", suchfeld, treffer),
            abschnitt("4. Slider", slider, slider_anzeige),
            abschnitt("5. bool-Werte", ft.Row([schalter, haken])),
            abschnitt(
                "6. lange Arbeit",
                ft.Row(
                    [
                        ft.Button("async + to_thread", on_click=auswerten),
                        ft.Button("time.sleep (falsch)", on_click=blockieren),
                    ]
                ),
            ),
            abschnitt("7. Exception", ft.Button("Exception werfen", on_click=absturz)),
            ft.Text("8. Taste drücken oder Fenster ziehen → Protokoll", italic=True, size=12),
            ft.Text("9. Beim Start läuft ein Task — Protokoll beobachten", italic=True, size=12),
        ],
        expand=1,
        scroll=ft.ScrollMode.AUTO,
        spacing=16,
    )

    page.add(
        ft.Row(
            [links, ft.VerticalDivider(), ft.Column([ft.Text("Protokoll"), protokoll], expand=1)],
            expand=True,
        )
    )

    page.run_task(aus_einem_task)


ft.run(main)
