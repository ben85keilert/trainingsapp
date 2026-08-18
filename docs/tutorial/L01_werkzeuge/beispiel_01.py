"""L01, Beispiel 1 — das kleinstmögliche Flet-Programm.

Start:  python docs/tutorial/L01_werkzeuge/beispiel_01.py

Drei Zeilen Substanz. Mehr braucht ein Fenster nicht.
"""

import flet as ft


def main(page: ft.Page) -> None:
    # `page` ist das Fenster. Alles, was sichtbar sein soll, muss hier hinein.
    page.title = "Erstes Fenster"
    page.add(ft.Text("Hallo Trainingsassistent"))


# ft.app startet die Flutter-Seite und ruft `main` auf, sobald sie bereit ist.
# Der Aufruf blockiert, bis das Fenster geschlossen wird.
ft.app(target=main)