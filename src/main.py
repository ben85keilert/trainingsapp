"""Einstiegspunkt für `flet build` — die Oberfläche selbst liegt in `trainingsapp.ui.app`."""

import flet as ft

from trainingsapp.ui.app import main

if __name__ == "__main__":
    ft.run(main)
