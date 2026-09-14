"""L03, Beispiel 2 — Routen und der Ansichtsstapel.

Start:  uv run flet run -d docs/tutorial/L03_navigation/beispiel_02.py

Tippe eine Übung an: eine Detailansicht legt sich obenauf. Der Zurück-Knopf
nimmt sie wieder herunter — auf Android tut das auch die Zurück-Taste.
"""

import json
from pathlib import Path

import flet as ft

SEED = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "trainingsapp"
    / "data"
    / "seed"
    / "exercises.json"
)
UEBUNGEN = {u["key"]: u for u in json.loads(SEED.read_text(encoding="utf-8"))["exercises"]}


async def main(page: ft.Page) -> None:
    page.title = "Routen"
    page.theme = ft.Theme(color_scheme_seed="#2E7D6E", use_material3=True)

    def liste() -> ft.View:
        # Seit Flet 0.80 ist `controls` das erste Positionsargument, nicht mehr
        # `route` — darum beide als Schlüsselwort, sonst landet "/" in `controls`.
        return ft.View(
            route="/",
            controls=[
                ft.AppBar(title=ft.Text("Übungen")),
                ft.ListView(
                    expand=True,
                    controls=[
                        ft.ListTile(
                            title=ft.Text(u["name"]),
                            subtitle=ft.Text(u["category"], size=12),
                            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                            # push_route setzt die Route — der Rest passiert im Handler.
                            # Es ist eine Coroutine; aus einem Lambda heraus startet
                            # run_task sie als Task auf der Ereignisschleife der Seite.
                            on_click=lambda e, k=key: page.run_task(
                                page.push_route, f"/uebung/{k}"
                            ),
                        )
                        for key, u in UEBUNGEN.items()
                    ],
                ),
            ],
        )

    def detail(key: str) -> ft.View:
        u = UEBUNGEN[key]
        return ft.View(
            route=f"/uebung/{key}",
            controls=[
                # Weil diese Ansicht ÜBER der Liste liegt, zeigt Flet
                # automatisch einen Zurück-Pfeil.
                ft.AppBar(title=ft.Text(u["name"])),
                ft.Container(
                    padding=20,
                    content=ft.Column(
                        spacing=14,
                        controls=[
                            ft.Row(
                                spacing=10,
                                controls=[
                                    ft.Icon(u.get("icon_key") or "fitness_center", size=32),
                                    ft.Text(u["category"], size=16, opacity=0.7),
                                ],
                            ),
                            ft.Divider(),
                            ft.Text(u["description"]),
                        ],
                    ),
                ),
            ],
        )

    def route_gewechselt(e: ft.RouteChangeEvent) -> None:
        page.views.clear()
        page.views.append(liste())  # Wurzel bleibt immer unten
        if page.route.startswith("/uebung/"):
            key = page.route.rsplit("/", 1)[-1]
            if key in UEBUNGEN:
                page.views.append(detail(key))
        page.update()

    # Ereignisbehandler dürfen Coroutinen sein — dann kann man push_route awaiten.
    async def zurueck(e: ft.ViewPopEvent) -> None:
        page.views.pop()
        await page.push_route(page.views[-1].route)

    page.on_route_change = route_gewechselt
    page.on_view_pop = zurueck
    await page.push_route("/")


ft.run(main)
