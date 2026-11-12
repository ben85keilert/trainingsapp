"""Einstellungen — Route `/einstellungen`: nur noch das Menü (Ben, 11.11.2026).

Bis 11.11.2026 lagen Profilwahl, Farbprofil, Geräte-Backup, lose Schalter und ein Dutzend
Verweise untereinander auf dieser einen Seite — „sehr unübersichtlich“. Jetzt zeigt sie
Menüzeilen (Symbol, Titel, **eine** Zeile mit dem Wichtigsten, Pfeil) in fünf Gruppen; alles
Einstellbare liegt eine Ebene tiefer:

====================  ==============================  ===================================
Gruppe                Zeile                           Seite
====================  ==============================  ===================================
Person                Profil                          `/einstellungen/profile`
..                    Darstellung                     `/einstellungen/darstellung`
Üben                  Übungen                         `/einstellungen/uebungen`
..                    Timer und Takt                  `/einstellungen/uhr`
..                    Tagesfelder                     `/einstellungen/tagesfelder`
..                    Notiz-Tags                      `/einstellungen/notiz-tags`
Messen                Herzfrequenz                    `/einstellungen/herzfrequenz`
..                    HRV-Messung                     `/einstellungen/hrv`
..                    Training und GPS                `/einstellungen/training`
Inhalte und Daten     Pakete                          `/einstellungen/pakete`
..                    Updates (nur Solo)              `/einstellungen/updates`
..                    Anhänge                         `/einstellungen/anhaenge`
..                    Daten und Sicherung             `/einstellungen/daten`
App                   Hilfe und Über                  `/einstellungen/hilfe`
====================  ==============================  ===================================

Die neuen Seiten (Übungen, Timer und Takt, Daten und Sicherung, Hilfe und Über) stehen in
`einstellungen_seiten.py`, die Darstellung in `einstellungen_darstellung.py`. `MENUE` ist
die Liste der Zeilen — `tests/test_ui_einstellungen.py` prüft, dass jede Seite gebaut wird
und jede frühere Einstellung über sie erreichbar ist.

Die Seiten der Einstellungen ersetzen einander im Stapel nicht (`navigation.geschwister`):
Zurück führt dorthin, woher man kam.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from trainingsapp.config import app_version, ist_aktiv
from trainingsapp.core.anhaenge import groesse_text
from trainingsapp.core.darstellung import HELLIGKEITEN
from trainingsapp.core.eintraege import OFFEN_WAHL
from trainingsapp.ui.components.karte import karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.scroll import scroll_merken
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.timer import timer_knopf


@dataclass(frozen=True)
class Zeile:
    """Eine Menüzeile: wohin sie führt und was in ihrer einen Zeile Untertitel steht."""

    gruppe: str
    titel: str
    symbol: ft.IconData
    route: str
    untertitel: Callable[[AppState], str]
    #: Funktionsschalter (`config.ist_aktiv`) — einer genügt; leer = immer
    schalter: tuple[str, ...] = ()

    def sichtbar(self) -> bool:
        return not self.schalter or any(ist_aktiv(s) for s in self.schalter)


def _profil(state: AppState) -> str:
    anzahl = len(state.profile.alle())
    return f"{state.profil.name} · " + ("1 Profil" if anzahl == 1 else f"{anzahl} Profile")


def _darstellung(state: AppState) -> str:
    d = state.darstellung()
    verlauf = " · Verlauf" if d.verlauf and d.farben().dunkel.verlauf is not None else ""
    return f"{d.farben().name} · {HELLIGKEITEN[d.helligkeit]}{verlauf}"


def _uebungen(state: AppState) -> str:
    offen = OFFEN_WAHL.get(state.eintrag_offen_min(), "")
    offen = offen.replace(" ohne Satz", "") if "ohne Satz" in offen else "bis „Abschließen“"
    return (
        f"Eintrag offen: {offen} · Fokus {'an' if state.fokus_auto() else 'aus'} · "
        f"{len(state.tags.namen('typ'))} Typen, {len(state.tags.namen('region'))} Regionen"
    )


def _uhr(state: AppState) -> str:
    return f"Zuletzt „{state.timer_profil().anzeigename}“ · Signale · Schnellzeiten"


def _tagesfelder(state: AppState) -> str:
    felder = state.tagesfelder.alle(state.profil.id)
    aktiv = sum(1 for f in felder if f.aktiv)
    aus = f" · {len(felder) - aktiv} aus" if len(felder) > aktiv else ""
    return f"Unter Heute → „Zum Tag“ · {aktiv} aktiv{aus}"


def _notiz_tags(state: AppState) -> str:
    tags = state.notiz_tags.alle(state.profil.id)
    mehr = f" · +{len(tags) - 4}" if len(tags) > 4 else ""
    return " · ".join(t.name for t in tags[:4]) + mehr


def _herzfrequenz(state: AppState) -> str:
    hf = state.hf_profil()
    if not hf.vollstaendig:
        return "Ruhe-HF und HFmax fehlen · Bereiche · Zielbereich"
    geschaetzt = " (geschätzt)" if hf.hfmax_geschaetzt else ""
    return f"Ruhe {hf.ruhe_bpm:.0f} · HFmax {hf.hfmax_bpm:.0f}{geschaetzt} · Bereiche"


def _hrv(state: AppState) -> str:
    e = state.hrv_einstellungen()
    reiter = "" if e.messung_anzeigen else " · Reiter „Messung“ aus"
    return f"{len(e.kacheln)} Kacheln · Kurven · Korrektur · Diagnose{reiter}"


def _training(state: AppState) -> str:
    return "Strecke einfärben · Tempo und Pausen · Spalten · GPS-Test"


def _pakete(state: AppState) -> str:
    anzahl = len(state.pakete.alle())
    return ("1 Paket" if anzahl == 1 else f"{anzahl} Pakete") + " · importieren, exportieren"


def _updates(state: AppState) -> str:
    return state.updates_label() or (
        "App und Pakete · beim Start geprüft"
        if state.update_pruefung()
        else "App und Pakete · Prüfung beim Start aus"
    )


def _anhaenge(state: AppState) -> str:
    umfang = state.anhaenge.gesamt(state.profil.id)
    return f"{umfang.text} · {groesse_text(umfang.bytes)} · Qualität, Aufräumen"


def _daten(state: AppState) -> str:
    backup = (
        f"Geräte-Backup {'an' if state.sicherung().an else 'aus'} · "
        if ist_aktiv("geraete_sicherung")
        else ""
    )
    return f"{backup}Papierkorb · Archiv"


def _hilfe(state: AppState) -> str:
    version, build = app_version()
    return f"So wird eingegeben · Version {version}" + (
        f" (Build {build})" if build is not None else ""
    )


PERSON = "Person"
UEBEN = "Üben"
MESSEN = "Messen"
INHALTE = "Inhalte und Daten"
APP = "App"

#: Das Menü in seiner Reihenfolge: erst wer, dann was man täglich tut, dann die Messung,
#: dann Inhalte und Daten, zuletzt die App selbst
MENUE: tuple[Zeile, ...] = (
    Zeile(PERSON, "Profil", ft.Icons.PERSON_OUTLINE, "/einstellungen/profile", _profil),
    Zeile(
        PERSON,
        "Darstellung",
        ft.Icons.PALETTE_OUTLINED,
        "/einstellungen/darstellung",
        _darstellung,
    ),
    Zeile(UEBEN, "Übungen", ft.Icons.FITNESS_CENTER, "/einstellungen/uebungen", _uebungen),
    Zeile(UEBEN, "Timer und Takt", ft.Icons.TIMER_OUTLINED, "/einstellungen/uhr", _uhr),
    Zeile(UEBEN, "Tagesfelder", ft.Icons.LABEL_OUTLINE, "/einstellungen/tagesfelder", _tagesfelder),
    Zeile(UEBEN, "Notiz-Tags", ft.Icons.SELL_OUTLINED, "/einstellungen/notiz-tags", _notiz_tags),
    Zeile(
        MESSEN,
        "Herzfrequenz",
        ft.Icons.FAVORITE_BORDER,
        "/einstellungen/herzfrequenz",
        _herzfrequenz,
    ),
    Zeile(MESSEN, "HRV-Messung", ft.Icons.MONITOR_HEART_OUTLINED, "/einstellungen/hrv", _hrv),
    Zeile(
        MESSEN, "Training und GPS", ft.Icons.DIRECTIONS_RUN, "/einstellungen/training", _training
    ),
    Zeile(INHALTE, "Pakete", ft.Icons.INVENTORY_2_OUTLINED, "/einstellungen/pakete", _pakete),
    Zeile(
        INHALTE,
        "Updates",
        ft.Icons.SYSTEM_UPDATE,
        "/einstellungen/updates",
        _updates,
        schalter=("update_pruefung", "paket_quellen"),
    ),
    Zeile(INHALTE, "Anhänge", ft.Icons.ATTACH_FILE, "/einstellungen/anhaenge", _anhaenge),
    Zeile(INHALTE, "Daten und Sicherung", ft.Icons.BACKUP_OUTLINED, "/einstellungen/daten", _daten),
    Zeile(APP, "Hilfe und Über", ft.Icons.HELP_OUTLINE, "/einstellungen/hilfe", _hilfe),
)


def menuezeile(
    page: ft.Page,
    titel_text: str,
    untertitel: str,
    symbol: ft.IconData,
    route: str,
) -> ft.ListTile:
    """Eine Zeile, die auf eine Seite führt — auch für die Verweise in den Unterseiten."""

    async def oeffnen() -> None:
        await page.push_route(route)

    return ft.ListTile(
        leading=ft.Icon(symbol),
        title=ft.Text(titel_text),
        subtitle=ft.Text(untertitel, size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        if untertitel
        else None,
        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
        on_click=oeffnen,
        content_padding=ft.Padding.only(left=0, right=0),
        dense=True,
        data=route,  # wohin die Zeile führt — für Tests und zum Wiederfinden
    )


def einstellungen(page: ft.Page, state: AppState, browser: ft.UrlLauncher) -> ft.View:
    gruppen: dict[str, list[ft.Control]] = {}
    for zeile in MENUE:
        if zeile.sichtbar():
            gruppen.setdefault(zeile.gruppe, []).append(
                menuezeile(page, zeile.titel, zeile.untertitel(state), zeile.symbol, zeile.route)
            )

    ansicht = ft.View(
        route="/einstellungen",
        appbar=ft.AppBar(
            title=ft.Text("Einstellungen"), actions=[timer_knopf(page, state, "einstellungen")]
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=12,
                    controls=[
                        karte(titel(name), *zeilen, abstand=0) for name, zeilen in gruppen.items()
                    ],
                ),
                expand=False,
            )
        ],
    )
    return scroll_merken(page, state, "/einstellungen", ansicht)


__all__ = ["MENUE", "Zeile", "einstellungen", "menuezeile"]
