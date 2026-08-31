"""L02, Beispiel 2 — wann update() nötig ist (und wann nicht).

Start:  uv run flet run -d docs/tutorial/L02_flet_modell/beispiel_02.py

DAS IST DIE WICHTIGSTE LEKTION DIESES KAPITELS.

Oben ein Zähler, dessen Handler KEIN update() aufruft — er funktioniert
trotzdem, weil Flet nach jedem Ereignis-Handler automatisch aktualisiert
(Auto-Update).

Unten ein simulierter Live-Puls aus einem Hintergrund-Task: zwei Anzeigen,
derselbe Schleifendurchlauf — nur eine ruft update() auf. Die andere friert
ein, denn im Hintergrund-Task gibt es kein Auto-Update. Klick während der
Messung auf irgendeinen Knopf: Das Auto-Update dieses Klicks spült die
liegengebliebenen Änderungen mit durch — die eingefrorene Anzeige springt.
Genau so entstehen die „mal geht's, mal nicht"-Fehler.
"""

import asyncio
import random

import flet as ft


def main(page: ft.Page) -> None:
    page.title = "Wann braucht es update()?"
    page.padding = 30
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)

    # --- Teil 1: Ereignis-Handler — Auto-Update übernimmt --------------------

    zaehler = ft.Text("0", size=48, weight=ft.FontWeight.BOLD)

    def zaehlen(e: ft.ControlEvent) -> None:
        zaehler.value = str(int(zaehler.value) + 1)
        # Kein update() — nach dem Handler aktualisiert Flet von selbst.

    # --- Teil 2: Hintergrund-Task — hier gibt es KEIN Auto-Update ------------

    laeuft = False
    anzeige_mit = ft.Text("—", size=48, weight=ft.FontWeight.BOLD)
    anzeige_ohne = ft.Text("—", size=48, weight=ft.FontWeight.BOLD)

    async def puls_simulieren() -> None:
        while laeuft:
            wert = str(random.randint(58, 72))

            anzeige_mit.value = wert
            anzeige_mit.update()  # ← nur mit dieser Zeile tickt die Anzeige

            anzeige_ohne.value = wert
            # Hier fehlt update() — mit voller Absicht. Der Wert ändert sich
            # in Python, aber der Bildschirm erfährt nichts davon.

            await asyncio.sleep(1)

    def start_stop(e: ft.ControlEvent) -> None:
        nonlocal laeuft
        laeuft = not laeuft
        e.control.content = "Messung stoppen" if laeuft else "Messung starten"
        if laeuft:
            page.run_task(puls_simulieren)

    def saeule(titel: str, anzeige: ft.Text, farbe: str) -> ft.Container:
        return ft.Container(
            expand=True,
            padding=20,
            border_radius=12,
            bgcolor=farbe,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
                controls=[ft.Text(titel, weight=ft.FontWeight.BOLD), anzeige],
            ),
        )

    page.add(
        ft.Column(
            spacing=20,
            controls=[
                ft.Text("Teil 1 — im Ereignis-Handler", size=18, weight=ft.FontWeight.BOLD),
                ft.Row(
                    spacing=20,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        zaehler,
                        ft.Button("Zählen (Handler ohne update)", on_click=zaehlen),
                    ],
                ),
                ft.Divider(),
                ft.Text("Teil 2 — im Hintergrund-Task", size=18, weight=ft.FontWeight.BOLD),
                ft.Row(
                    spacing=20,
                    controls=[
                        saeule("MIT update()", anzeige_mit, ft.Colors.SECONDARY_CONTAINER),
                        saeule("OHNE update()", anzeige_ohne, ft.Colors.ERROR_CONTAINER),
                    ],
                ),
                ft.Button("Messung starten", on_click=start_stop),
                ft.Text(
                    "Rechts friert ein. Klick trotzdem mal einen Knopf: Das "
                    "Auto-Update des Klicks nimmt die liegengebliebene Änderung "
                    "mit — die Anzeige springt. Deshalb wirken solche Fehler "
                    "launisch.",
                    italic=True,
                ),
            ],
        )
    )


ft.run(main)
