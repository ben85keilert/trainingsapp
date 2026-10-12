"""L05, Beispiel 3 — Handler in Schleifen: die Lambda-Falle und zwei Auswege.

Start:  uv run flet run docs/tutorial/L05_uebungskatalog/beispiel_03.py

Drei Reihen Knöpfe, dreimal dieselbe Absicht: Jeder Knopf soll seinen eigenen
Namen melden. Nur zwei Reihen tun das.
"""

from collections.abc import Callable

import flet as ft

NAMEN = ["Wadenheben", "Einbeinstand", "Unterarmstütz"]


def main(page: ft.Page) -> None:
    page.title = "Handler in Schleifen"
    page.padding = 24

    ausgabe = ft.Text("Tippe auf einen Knopf.", size=20, weight=ft.FontWeight.BOLD)

    def melden(text: str) -> None:
        ausgabe.value = text
        page.update()

    # --- A: Lambda in der Schleife — die Falle ------------------------------
    # `name` wird nicht beim Erzeugen gelesen, sondern beim Klick. Dann steht
    # darin der letzte Wert der Schleife. Alle drei melden "Unterarmstütz".
    reihe_a = []
    for name in NAMEN:
        reihe_a.append(ft.Button(name, on_click=lambda e: melden(f"A: {name}")))  # noqa: B023

    # --- B: Lambda mit Default-Argument -----------------------------------
    # `n=n` wertet n sofort aus und speichert es als Vorgabewert des Lambdas.
    # Funktioniert, ist aber ein Trick, den man kennen muss.
    reihe_b = [ft.Button(n, on_click=lambda e, n=n: melden(f"B: {n}")) for n in NAMEN]

    # --- C: Fabrikfunktion --------------------------------------------------
    # melder(n) wird SOFORT aufgerufen und gibt eine Funktion zurück, die sich
    # genau dieses n gemerkt hat. So steht es in ui/views/katalog.py.
    def melder(n: str) -> Callable[[], None]:
        def handler() -> None:
            melden(f"C: {n}")

        return handler

    reihe_c = [ft.Button(n, on_click=melder(n)) for n in NAMEN]

    def block(titel: str, knoepfe: list[ft.Control], hinweis: str) -> ft.Control:
        return ft.Column(
            spacing=6,
            controls=[
                ft.Text(titel, weight=ft.FontWeight.BOLD),
                ft.Row(spacing=8, controls=knoepfe),
                ft.Text(hinweis, size=12, opacity=0.7),
            ],
        )

    page.add(
        ft.Column(
            spacing=24,
            controls=[
                ausgabe,
                block("A — Lambda in der Schleife", reihe_a, "Alle melden den letzten Namen."),
                block(
                    "B — Lambda mit Default-Argument", reihe_b, "Geht. Aber warum, sieht man nicht."
                ),
                block("C — Fabrikfunktion", reihe_c, "Geht, und man sieht, was festgehalten wird."),
            ],
        )
    )


ft.run(main)
