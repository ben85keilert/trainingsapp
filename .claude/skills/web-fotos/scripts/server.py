"""Die App als Flet-Web-Server für Bildschirmfotos — mit eigener Test-Datenbank.

Aufruf (über `starten.sh`): ``TRAININGSAPP_DATA_DIR=<ordner> python server.py <port>``.
Ohne ``TRAININGSAPP_DATA_DIR`` bricht das Skript ab: nie Bens echte Daten.

- Der Browser des Rechners geht nicht auf (``webbrowser.open`` ersetzt).
- Die Hinweise des ersten Starts (Updates) sind abgeschaltet — sie lägen über jedem Foto.
- Ein Wach-Thread hält ``im_vordergrund`` wahr: Kopfloses Chromium meldet der App manchmal
  „verborgen“, dann zeichnen Live-Ansichten nicht.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

if not os.environ.get("TRAININGSAPP_DATA_DIR"):
    sys.exit("TRAININGSAPP_DATA_DIR fehlt — der Server läuft nur mit eigener Test-Datenbank.")

import flet as ft

from trainingsapp.data.repositories import SettingRepo
from trainingsapp.ui.app import main
from trainingsapp.ui.state import AppState

webbrowser.open = lambda *a, **k: True  # type: ignore[assignment]
_starten = AppState.starten.__func__  # type: ignore[attr-defined]


def starten(cls, *a, **k):
    state = _starten(cls, *a, **k)
    state.einstellungen.setzen(SettingRepo.HINWEIS_UPDATES, "1")
    state.einstellungen.setzen(SettingRepo.HINWEIS_APP_UPDATE, "1")
    state.update_pruefung_setzen(False)
    state.app_update_auto_setzen(False)

    def wach() -> None:
        while True:
            state.im_vordergrund = True
            time.sleep(2)

    threading.Thread(target=wach, daemon=True).start()
    return state


AppState.starten = classmethod(starten)  # type: ignore[method-assign,assignment]
ft.run(main, view=ft.AppView.WEB_BROWSER, port=int(sys.argv[1]), no_cdn=True)
