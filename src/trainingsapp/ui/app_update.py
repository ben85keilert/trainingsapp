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

**Automatik** (Ben, 9.11.2026: „Bau die Automatik mit Benachrichtigung und Schalter“;
Schalter `AppState.app_update_auto`, Vorgabe an): Nach der Prüfung beim Start lädt
`automatisch` ein neueres Release von selbst — nur mit Android 12+, erteilter Erlaubnis und
im WLAN, beim ersten Mal nach einem Hinweis. `vorbereiten` prüft die APK und schreibt sie in
eine Sitzung, ohne sie abzuschicken (Phase „vorbereitet“). Geht die App in den Hintergrund
(`lebenszyklus`), stellt `beim_verlassen` einen Wecker in der Erweiterung: nach
`WARTEN_S` schickt sie die Sitzung ab, wenn die App dann nicht zu sehen ist und kein
Vordergrunddienst läuft. Kommt man vorher zurück, nimmt `lebenszyklus` ihn zurück. Nie mit
offenem Formular (`formular_offen`) oder während etwas läuft. Nach dem Update meldet die
Erweiterung „aktualisiert, antippen zum Öffnen“. Scheitert ein Release von selbst, lässt die
Automatik es aus (`AppState.app_update_auslassen`); von Hand geht es weiter.

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
from trainingsapp.ui.components.dialoge import schliessen
from trainingsapp.ui.components.karte import hinweis
from trainingsapp.ui.laufend import laufendes

#: Phasen des Laufs
BEREIT = "bereit"
LADEN = "laden"
GELADEN = "geladen"
ERLAUBEN = "erlauben"
#: Automatik: geprüft und in einer Sitzung, abgeschickt wird beim Verlassen der App
VORBEREITET = "vorbereitet"
INSTALLIEREN = "installieren"
FEHLER = "fehler"
FERTIG = "fertig"

#: So lange muss die App unbenutzt sein, bevor sie sich von selbst aktualisiert (s) — die
#: Texte sagen „eine Minute“. Android schickt den Wecker etwas später, nie früher.
WARTEN_S = 60

#: So oft zeigt die Seite den Fortschritt beim Laden (s)
_TAKT_S = 0.3
#: Android-Code „abgebrochen“ (die Person hat im Dialog von Android abgelehnt)
_ABGEBROCHEN = 3

_GELADEN_TEXT = "Geladen. „Installieren“ spielt das Update ein — Android beendet die App dabei."


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
    #: Von der Automatik begonnen — scheitert es, lässt sie das Release künftig aus
    automatisch: bool = False


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
    if phase == FEHLER and lauf.automatisch:
        state.app_update_auslassen_setzen(lauf.release.tag)
    _zeigen(state)


async def _laden(state: Any, lauf: UpdateLauf) -> bool:
    """Die APK laden (oder die schon geladene nehmen) — ``True``, wenn sie da ist."""
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
        return False
    except UpdateFehler as e:
        # Das Netz zählt nicht als Scheitern des Releases — beim nächsten Start noch einmal
        lauf.automatisch = False
        _setzen(state, lauf, FEHLER, f"Nicht geladen: {e}")
        return False
    return True


async def laden_und_installieren(state: Any, lauf: UpdateLauf) -> None:
    """Laden (oder die schon geladene APK nehmen), prüfen, installieren."""
    if lauf.phase in (LADEN, INSTALLIEREN):
        return
    lauf.automatisch = False  # von Hand
    if await _laden(state, lauf):
        await installieren(state, lauf)


async def _apk_pruefen(state: Any, lauf: UpdateLauf) -> dict[str, Any] | None:
    """Die geladene APK prüfen und Androids Stand holen — ``None``: es geht nicht weiter
    (Phase und Meldung sind gesetzt)."""
    dienst = state.installieren
    assert lauf.pfad is not None
    try:
        pruefung = await dienst.pruefen(str(lauf.pfad))
    except Exception as e:
        _setzen(state, lauf, FEHLER, f"Android kann die APK nicht lesen: {e}")
        return None
    if (befund := apk_befund(pruefung)) is not None:
        with contextlib.suppress(OSError):
            lauf.pfad.unlink()
        lauf.pfad = None
        _setzen(state, lauf, FEHLER, befund)
        return None
    try:
        return dict(await dienst.stand())
    except Exception as e:
        _setzen(state, lauf, FEHLER, f"Android antwortet nicht: {e}")
        return None


async def installieren(state: Any, lauf: UpdateLauf) -> None:
    """Die geladene APK prüfen und installieren — wenn Android es erlaubt und nichts läuft.
    Ist sie schon vorbereitet (Automatik), wird nur noch abgeschickt."""
    dienst = state.installieren
    if dienst is None or lauf.phase == INSTALLIEREN:
        return
    vorbereitet = lauf.phase == VORBEREITET
    stand: dict[str, Any] | None = None
    if vorbereitet:
        try:
            stand = dict(await dienst.stand())
        except Exception as e:
            _setzen(state, lauf, FEHLER, f"Android antwortet nicht: {e}")
            return
        vorbereitet = int(stand.get("vorbereitet", -1)) >= 0  # sonst neu aus der Datei
    if not vorbereitet:
        if lauf.pfad is None or not lauf.pfad.is_file():
            lauf.phase = BEREIT
            await laden_und_installieren(state, lauf)
            return
        if (stand := await _apk_pruefen(state, lauf)) is None:
            return
    assert stand is not None
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
            VORBEREITET if vorbereitet else GELADEN,
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
        if vorbereitet:
            await dienst.abschicken()
        else:
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
        return
    if status == INSTALLER_ERFOLG:
        _setzen(state, lauf, FERTIG, installer_text(status))
        return
    if lauf.automatisch:  # auch abgelehnt: die Automatik fragt für dieses Release nicht wieder
        state.app_update_auslassen_setzen(lauf.release.tag)
    if status == _ABGEBROCHEN:
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


# -- Automatik ---------------------------------------------------------------------------


async def automatisch(page: Any, state: Any) -> None:
    """Nach der Prüfung (`views.updates`): ein neueres Release von selbst laden und
    vorbereiten — mit Schalter, Android 12+, Erlaubnis, im WLAN; beim ersten Mal erst der
    Hinweis. Fehlt etwas davon, bleibt es bei der Karte „App“."""
    dienst = state.installieren
    stand = state.updates
    if dienst is None or stand is None or stand.app is None or not state.app_update_auto():
        return
    if state.app_update_auslassen() == stand.app.tag:
        return
    if stand.app.apk_sha256 is None:
        # Ohne Prüfsumme von GitHub installiert sich nichts von selbst (S29) — von Hand über
        # die Karte „App“ bleibt es möglich, dort sieht die Person, was sie tut
        return
    lauf = lauf_fuer(state, stand.app)
    if lauf.phase not in (BEREIT, FEHLER):  # unterwegs, oder es wartet auf eine Hand
        return
    try:
        geraet = dict(await dienst.stand())
    except Exception:
        return
    if not (geraet.get("still") and geraet.get("darf")) or geraet.get("getaktet"):
        return
    if not state.app_update_hinweis_gesehen():
        page.show_dialog(hinweis_dialog(page, state, lauf))
        return
    await _von_selbst(page, state, lauf)


async def _von_selbst(page: Any, state: Any, lauf: UpdateLauf) -> None:
    lauf.automatisch = True
    if await _laden(state, lauf):
        await vorbereiten(page, state, lauf)


async def vorbereiten(page: Any, state: Any, lauf: UpdateLauf) -> None:
    """Prüfen und die Sitzung schreiben, ohne sie abzuschicken — das geschieht, wenn die App
    eine Minute nicht benutzt wurde (`beim_verlassen`)."""
    dienst = state.installieren
    if dienst is None or lauf.pfad is None:
        return
    if (stand := await _apk_pruefen(state, lauf)) is None:
        return
    if not (stand.get("darf") and stand.get("still")):
        _setzen(state, lauf, GELADEN, _GELADEN_TEXT)
        return
    try:
        await dienst.vorbereiten(str(lauf.pfad))
    except Exception as e:
        _setzen(state, lauf, FEHLER, f"Nicht vorbereitet: {e}")
        return
    _setzen(
        state,
        lauf,
        VORBEREITET,
        f"Version {lauf.release.version} ist geladen und geprüft. Sie installiert sich, wenn "
        "die App eine Minute nicht benutzt wurde und nichts läuft — danach meldet sich eine "
        "Benachrichtigung.",
    )
    if not state.im_vordergrund:  # beim Laden schon gegangen
        await beim_verlassen(page, state)


def formular_offen(page: Any) -> bool:
    """Steht ein Formular offen (`components.zurueck`: ``can_pop = False``; die Startseite
    hält Zurück immer an)? Dann nicht von selbst installieren — der Neustart verlöre es."""
    return any(
        getattr(v, "can_pop", True) is False and getattr(v, "route", "/") != "/"
        for v in list(getattr(page, "views", []))
    )


async def beim_verlassen(page: Any, state: Any) -> None:
    """Die App geht in den Hintergrund: Ist ein Update vorbereitet, den Wecker stellen —
    nicht, solange etwas läuft oder ein Formular offen ist."""
    dienst = state.installieren
    lauf = state.app_update
    if dienst is None or not isinstance(lauf, UpdateLauf) or lauf.phase != VORBEREITET:
        return
    if not state.app_update_auto() or laufendes(state) or formular_offen(page):
        return
    with contextlib.suppress(Exception):
        await dienst.spaeter(WARTEN_S)


async def lebenszyklus(page: Any, state: Any, vorn: bool) -> None:
    """Aus `app.py`: zurück in der App den Wecker zurücknehmen und nach „Erlauben“
    weitermachen; in den Hintergrund den Wecker stellen."""
    if not vorn:
        await beim_verlassen(page, state)
        return
    lauf = state.app_update
    if state.installieren is not None and isinstance(lauf, UpdateLauf):
        if lauf.phase == VORBEREITET:
            with contextlib.suppress(Exception):
                await state.installieren.nicht_spaeter()
        await weiter_nach_erlauben(state)


async def automatik_umschalten(page: Any, state: Any, an: bool) -> None:
    """Der Schalter: an = gleich loslegen (ein eingeschalteter Schalter ersetzt den Hinweis),
    aus = eine vorbereitete Sitzung verwerfen — die geladene Datei bleibt für „Installieren“."""
    state.app_update_auto_setzen(an)
    dienst = state.installieren
    lauf = state.app_update
    if an:
        state.app_update_hinweis_merken()
        if dienst is not None:
            with contextlib.suppress(Exception):
                await dienst.benachrichtigung_erlauben()
        await automatisch(page, state)
    elif dienst is not None and isinstance(lauf, UpdateLauf) and lauf.phase == VORBEREITET:
        with contextlib.suppress(Exception):
            await dienst.verwerfen()
        lauf.automatisch = False
        _setzen(state, lauf, GELADEN, _GELADEN_TEXT)


def hinweis_dialog(page: Any, state: Any, lauf: UpdateLauf) -> ft.AlertDialog:
    """Einmal, bevor die App zum ersten Mal selbst lädt — Verstanden oder Ausschalten (Muster
    von `views.updates.hinweis_dialog`; jede neue Netzverbindung in Solo braucht ihn)."""
    groesse = f" (rund {_mb(lauf.release.apk_bytes)} MB)" if lauf.release.apk_bytes else ""

    async def verstanden() -> None:
        state.app_update_hinweis_merken()
        schliessen(dialog)
        if state.installieren is not None:
            with contextlib.suppress(Exception):
                await state.installieren.benachrichtigung_erlauben()
        await _von_selbst(page, state, lauf)

    def ausschalten() -> None:
        state.app_update_hinweis_merken()
        state.app_update_auto_setzen(False)
        schliessen(dialog)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("App-Updates von selbst"),
        content=ft.Text(
            f"Version {lauf.release.version} ist erschienen. Die App lädt neue Versionen im "
            f"WLAN selbst von GitHub{groesse} und installiert sie, wenn sie eine Minute nicht "
            "benutzt wurde und nichts läuft — die Daten bleiben. Danach meldet eine "
            "Benachrichtigung das Update. Unter Einstellungen → Updates lässt sich das "
            "ausschalten."
        ),
        actions=[
            ft.TextButton("Ausschalten", on_click=ausschalten),
            ft.FilledButton("Verstanden", on_click=verstanden),
        ],
    )
    return dialog


def automatik_schalter(page: Any, state: Any) -> list[ft.Control]:
    """Schalter und Erklärung für die Karte „App“ (nur mit der Erweiterung)."""

    def umschalten(ev: ft.Event[ft.Switch]) -> None:
        page.run_task(automatik_umschalten, page, state, bool(ev.control.value))

    return [
        ft.Switch(
            label="Updates der App von selbst installieren",
            value=state.app_update_auto(),
            on_change=umschalten,
        ),
        hinweis(
            "Im WLAN lädt die App eine neue Version selbst und installiert sie, wenn sie eine "
            "Minute nicht benutzt wurde und nichts läuft; danach meldet sich eine "
            "Benachrichtigung. Braucht Android 12 und einmal „Erlauben“."
        ),
    ]


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
        elif lauf.phase == VORBEREITET:
            teile += [
                hinweis(lauf.meldung),
                knoepfe(
                    ft.FilledButton(
                        "Jetzt installieren", icon=ft.Icons.SYSTEM_UPDATE, on_click=weiter
                    ),
                    browser=False,
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
    "VORBEREITET",
    "WARTEN_S",
    "UpdateLauf",
    "app_bereich",
    "aufraeumen",
    "automatik_schalter",
    "automatik_umschalten",
    "automatisch",
    "beim_verlassen",
    "ergebnis",
    "erlauben",
    "formular_offen",
    "hinweis_dialog",
    "installieren",
    "laden_und_installieren",
    "lauf_fuer",
    "lebenszyklus",
    "vorbereiten",
    "weiter_nach_erlauben",
]
