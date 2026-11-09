"""Das App-Update in der App laden und installieren (Katalog A8 Stufe 2; Ben, 9.11.2026).

Nur in der gebauten Android-App (Erweiterung `flet_installieren`, `AppState.installieren`).
Ablauf auf der Seite „Updates“, Karte „App“:

1. **Laden:** `core.update.apk_laden` läuft im Hintergrund (`asyncio.to_thread`). Der
   Fortschritt geht alle 0,3 s an die Seite, das Laden lässt sich abbrechen. Das geht auch,
   während etwas läuft.
2. **Prüfen:** Die Erweiterung liest die APK (Paket, Versionsnummer, Signatur),
   `core.update.apk_befund` sagt, was dagegen spricht.
3. **Erlauben:** Fehlt „Unbekannte Apps installieren“, führt ein Knopf zur Einstellung.
   Zurück in der App geht es von selbst weiter (`weiter_nach_erlauben`, aus dem
   Lebenszyklus in `app.py`).
4. **Installieren:** nie, solange etwas läuft (`ui.laufend.laufendes`: Messung, Einheit,
   Training, Timer). Vorher wird gespeichert, was gerade geschrieben wird
   (`AppState.vor_dem_verlassen`). Android beendet die App dabei — ab Android 12 ohne
   Rückfrage, sonst nach einem Dialog von Android.

Der Stand (`UpdateLauf`) hängt an `AppState.app_update` und überlebt so den Neuaufbau der
Seite. Die Seite meldet sich mit `AppState.app_update_beobachter` an (`app_bereich`).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.config import app_version, updateverzeichnis
from trainingsapp.core.update import (
    INSTALLER_ERFOLG,
    INSTALLER_RUECKFRAGE,
    Release,
    UpdateAbgebrochen,
    UpdateFehler,
    alte_apks_loeschen,
    apk_befund,
    apk_laden,
    installer_text,
)
from trainingsapp.ui.components.karte import hinweis
from trainingsapp.ui.laufend import laufendes

#: Phasen des Laufs
BEREIT = "bereit"
LADEN = "laden"
GELADEN = "geladen"
ERLAUBEN = "erlauben"
INSTALLIEREN = "installieren"
FEHLER = "fehler"
FERTIG = "fertig"

#: So oft zeigt die Seite den Fortschritt beim Laden (s)
_TAKT_S = 0.3
#: Android-Code „abgebrochen“ (die Person hat im Dialog von Android abgelehnt)
_ABGEBROCHEN = 3


@dataclass
class UpdateLauf:
    """Wie weit „Laden und installieren“ für ein Release ist."""

    release: Release
    phase: str = BEREIT
    geladen: int = 0
    gesamt: int = 0
    pfad: Path | None = None
    meldung: str = ""
    abbrechen: bool = False


def lauf_fuer(state: Any, release: Release) -> UpdateLauf:
    """Der Lauf für ``release`` — der bisherige, wenn er demselben Release gilt."""
    alt = state.app_update
    if isinstance(alt, UpdateLauf) and alt.release == release:
        return alt
    state.app_update = UpdateLauf(release)
    return state.app_update


def aufraeumen() -> None:
    """Beim Start: geladene APKs bis zur laufenden Version und halbe Downloads löschen."""
    with contextlib.suppress(OSError):
        alte_apks_loeschen(updateverzeichnis(), *app_version())


def _zeigen(state: Any) -> None:
    if (beobachter := state.app_update_beobachter) is not None:
        with contextlib.suppress(Exception):  # die Seite ist vielleicht schon weg
            beobachter()


def _setzen(state: Any, lauf: UpdateLauf, phase: str, meldung: str = "") -> None:
    lauf.phase = phase
    lauf.meldung = meldung
    _zeigen(state)


async def laden_und_installieren(state: Any, lauf: UpdateLauf) -> None:
    """Laden (oder die schon geladene APK nehmen), prüfen, installieren."""
    if lauf.phase in (LADEN, INSTALLIEREN):
        return
    lauf.abbrechen = False
    lauf.geladen = lauf.gesamt = 0
    _setzen(state, lauf, LADEN)

    def fortschritt(geladen: int, gesamt: int) -> None:  # aus dem Hintergrund-Thread
        lauf.geladen, lauf.gesamt = geladen, gesamt

    aufgabe = asyncio.ensure_future(
        asyncio.to_thread(
            apk_laden,
            lauf.release,
            updateverzeichnis(),
            fortschritt,
            abbrechen=lambda: lauf.abbrechen,
        )
    )
    while not aufgabe.done():
        await asyncio.wait({aufgabe}, timeout=_TAKT_S)
        _zeigen(state)
    try:
        lauf.pfad = aufgabe.result()
    except UpdateAbgebrochen:
        _setzen(state, lauf, BEREIT, "Laden abgebrochen.")
        return
    except UpdateFehler as e:
        _setzen(state, lauf, FEHLER, f"Nicht geladen: {e}")
        return
    await installieren(state, lauf)


async def installieren(state: Any, lauf: UpdateLauf) -> None:
    """Die geladene APK prüfen und installieren — wenn Android es erlaubt und nichts läuft."""
    dienst = state.installieren
    if dienst is None or lauf.phase == INSTALLIEREN:
        return
    if lauf.pfad is None or not lauf.pfad.is_file():
        lauf.phase = BEREIT
        await laden_und_installieren(state, lauf)
        return
    try:
        pruefung = await dienst.pruefen(str(lauf.pfad))
    except Exception as e:
        _setzen(state, lauf, FEHLER, f"Android kann die APK nicht lesen: {e}")
        return
    if (befund := apk_befund(pruefung)) is not None:
        with contextlib.suppress(OSError):
            lauf.pfad.unlink()
        lauf.pfad = None
        _setzen(state, lauf, FEHLER, befund)
        return
    try:
        stand = await dienst.stand()
    except Exception as e:
        _setzen(state, lauf, FEHLER, f"Android antwortet nicht: {e}")
        return
    if not stand.get("darf"):
        _setzen(
            state,
            lauf,
            ERLAUBEN,
            "Geladen. Android muss der App einmal erlauben, Updates zu installieren: "
            "„Erlauben“ öffnet die Einstellung, danach geht es von selbst weiter.",
        )
        return
    if laeuft := laufendes(state):
        was = ", ".join(x.titel for x in laeuft)
        _setzen(
            state,
            lauf,
            GELADEN,
            f"Geladen. Installieren geht, sobald nichts mehr läuft (jetzt: {was}) — "
            "Android beendet die App dabei.",
        )
        return
    # Android beendet die App gleich: sichern, was gerade geschrieben wird
    for sichern in list(state.vor_dem_verlassen.values()):
        with contextlib.suppress(Exception):
            sichern()
    _setzen(
        state,
        lauf,
        INSTALLIEREN,
        "Installiere … Die App schließt sich gleich — danach wieder öffnen."
        if stand.get("still")
        else "Android fragt gleich nach — „Aktualisieren“ tippen. Danach die App wieder öffnen.",
    )
    try:
        await dienst.installieren(str(lauf.pfad))
    except Exception as e:
        _setzen(state, lauf, FEHLER, f"Nicht installiert: {e}")


def ergebnis(state: Any, status: int, meldung: str | None) -> None:
    """Das Ergebnis von Android (`FletInstallieren.on_ergebnis`)."""
    lauf = state.app_update
    if not isinstance(lauf, UpdateLauf):
        return
    if status == INSTALLER_RUECKFRAGE:
        _setzen(state, lauf, INSTALLIEREN, installer_text(status))
    elif status == INSTALLER_ERFOLG:
        _setzen(state, lauf, FERTIG, installer_text(status))
    elif status == _ABGEBROCHEN:
        _setzen(state, lauf, GELADEN, "Nicht installiert — abgebrochen.")
    else:
        _setzen(state, lauf, FEHLER, installer_text(status, meldung))


async def erlauben(state: Any) -> None:
    """Die Einstellung „Unbekannte Apps installieren“ für die App öffnen."""
    if state.installieren is None:
        return
    try:
        await state.installieren.erlauben()
    except Exception as e:
        lauf = state.app_update
        if isinstance(lauf, UpdateLauf):
            _setzen(state, lauf, ERLAUBEN, f"Die Einstellung ließ sich nicht öffnen: {e}")


async def weiter_nach_erlauben(state: Any) -> None:
    """Zurück in der App (Lebenszyklus): kam man von „Erlauben“, geht es weiter."""
    lauf = state.app_update
    if isinstance(lauf, UpdateLauf) and lauf.phase == ERLAUBEN:
        await installieren(state, lauf)


def _mb(n: int) -> str:
    return f"{n / 1_000_000:.0f}"


def app_bereich(
    state: Any,
    release: Release,
    im_browser: Callable[[], Awaitable[None]],
) -> ft.Column:
    """Der Teil der Karte „App“, der lädt und installiert — zeichnet sich bei jedem Schritt
    neu (`AppState.app_update_beobachter`)."""
    lauf = lauf_fuer(state, release)
    spalte = ft.Column(spacing=8)

    async def starten() -> None:
        await laden_und_installieren(state, lauf)

    async def weiter() -> None:
        await installieren(state, lauf)

    async def zur_einstellung() -> None:
        await erlauben(state)

    def abbrechen() -> None:
        lauf.abbrechen = True

    def knoepfe(*rechts: ft.Control, browser: bool = True) -> ft.Row:
        links = [ft.TextButton("Im Browser laden", on_click=im_browser)] if browser else []
        return ft.Row(alignment=ft.MainAxisAlignment.END, wrap=True, controls=[*links, *rechts])

    def zeichnen() -> None:
        teile: list[ft.Control] = []
        if lauf.phase == BEREIT:
            teile.append(
                hinweis(
                    "Lädt die APK in der App und installiert sie als Update, die Daten "
                    "bleiben. Android beendet die App dabei — danach wieder öffnen."
                )
            )
            if lauf.meldung:
                teile.append(hinweis(lauf.meldung))
            teile.append(
                knoepfe(
                    ft.FilledButton(
                        "Laden und installieren", icon=ft.Icons.SYSTEM_UPDATE, on_click=starten
                    )
                )
            )
        elif lauf.phase == LADEN:
            anteil = lauf.geladen / lauf.gesamt if lauf.gesamt else None
            stand = (
                f"{_mb(lauf.geladen)} von {_mb(lauf.gesamt)} MB"
                if lauf.gesamt
                else f"{_mb(lauf.geladen)} MB"
            )
            teile += [
                ft.ProgressBar(value=anteil),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(f"Lade … {stand}", size=13),
                        ft.TextButton("Abbrechen", on_click=abbrechen),
                    ],
                ),
            ]
        elif lauf.phase == INSTALLIEREN:
            teile.append(
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.ProgressRing(width=18, height=18, stroke_width=2),
                        ft.Text(lauf.meldung, size=13, expand=True),
                    ],
                )
            )
        elif lauf.phase == ERLAUBEN:
            teile += [
                hinweis(lauf.meldung),
                knoepfe(
                    ft.TextButton("Installieren", on_click=weiter),
                    ft.FilledButton("Erlauben", icon=ft.Icons.SETTINGS, on_click=zur_einstellung),
                    browser=False,
                ),
            ]
        elif lauf.phase == GELADEN:
            teile += [
                hinweis(lauf.meldung),
                knoepfe(
                    ft.FilledButton("Installieren", icon=ft.Icons.SYSTEM_UPDATE, on_click=weiter)
                ),
            ]
        elif lauf.phase == FEHLER:
            teile += [
                ft.Text(lauf.meldung, size=13, color=ft.Colors.ERROR, selectable=True),
                knoepfe(ft.FilledButton("Noch einmal", icon=ft.Icons.REFRESH, on_click=starten)),
            ]
        else:  # FERTIG — selten zu sehen: Android beendet die App vorher
            teile.append(hinweis(lauf.meldung))
        spalte.controls = teile
        with contextlib.suppress(Exception):  # noch nicht oder nicht mehr auf der Seite
            spalte.update()

    zeichnen()
    state.app_update_beobachter = zeichnen
    return spalte


__all__ = [
    "BEREIT",
    "ERLAUBEN",
    "FEHLER",
    "FERTIG",
    "GELADEN",
    "INSTALLIEREN",
    "LADEN",
    "UpdateLauf",
    "app_bereich",
    "aufraeumen",
    "ergebnis",
    "erlauben",
    "installieren",
    "laden_und_installieren",
    "lauf_fuer",
    "weiter_nach_erlauben",
]
