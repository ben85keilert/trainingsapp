"""Die neuen Seiten der Einstellungen (Ben, 11.11.2026: „Verpacke die Inhalte in die Menüs“).

Was bis dahin lose auf der Hauptseite lag, steht hier — dieselben Schalter mit denselben
Schlüsseln, nur an ihrem Ort:

- **Übungen** (`/einstellungen/uebungen`): „Eintrag bleibt offen“, „▶ öffnet den Fokus“,
  Typen und Regionen.
- **Timer und Takt** (`/einstellungen/uhr`): Timer, Alle Timer, Signale (als
  ``/einstellungen/uhr/timer…`` — der Timer legt sich über die Seite, Zurück führt hierher),
  Schnellzeiten, Vibration am Phasenwechsel.
- **Daten und Sicherung** (`/einstellungen/daten`): Geräte-Backup (nur mit
  `geraete_sicherung`), Papierkorb samt Frist, Archiv.
- **Hilfe und Über** (`/einstellungen/hilfe`): die Hilfethemen, Edition und Version.

Erklärtexte stehen im „i“ des Kartentitels (`components.karte.info_knopf`), nicht als graue
Absätze. Kein Teil einer Route hier darf ``timer``, ``anhang`` oder ``paketmedium`` heißen —
`app.ebenen` legt diese Ansichten über jede Seite (darum ``/einstellungen/uhr``).
"""

from __future__ import annotations

import contextlib

import flet as ft

from trainingsapp.config import app_version, edition, ist_aktiv
from trainingsapp.core.eintraege import OFFEN_MIN_VORGABE, OFFEN_WAHL
from trainingsapp.core.sicherung import Sicherung
from trainingsapp.core.timer import schnellzeiten_lesen, schnellzeiten_text
from trainingsapp.data.repositories import PAPIERKORB_TAGE, SettingRepo
from trainingsapp.ui.components.hilfe import THEMEN, hilfe_oeffner
from trainingsapp.ui.components.karte import info_knopf, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.einstellungen import menuezeile

UEBUNGEN = "/einstellungen/uebungen"
UHR = "/einstellungen/uhr"
DATEN = "/einstellungen/daten"
HILFE = "/einstellungen/hilfe"

OFFEN_MD = """\
Sätze, Skala und Notiz gehen in den **offenen Eintrag** der Übung. Nach dieser Zeit ohne
neuen Satz gilt er als abgeschlossen — der nächste Wert beginnt einen neuen Eintrag.

Die Uhr steht beim Üben oben bei der Übung — im Plan als erste Zeile der Karte „Eintragen“.
Ob und wie ihre Zeit zählt, steht an der Übung (Übung bearbeiten → Uhr: „Uhr beim Üben“,
„zählt“, „Zählt als“).
"""

FOKUS_MD = """\
Der **Fokus** ist die Trainingsansicht zur laufenden Uhr: große Zeit, Takt, Bild der
Bewegung, Herzfrequenz, Eintragen.

Aus heißt: Die Uhr bleibt in der Übung, „Fokus“ daneben öffnet ihn bei Bedarf. Derselbe
Schalter steht beim Üben: im Plan rechts neben „Gemacht“, bei einer einzelnen Übung oben
über dem ▶.
"""

SCHNELLZEITEN_MD = """\
Die Chips, wenn du eine Zeit stellst — Sekunden oder Minuten, durch Komma getrennt
(z. B. `30 s, 1 min, 2, 5, 10`). Ein leeres Feld stellt die Vorgabe wieder her.
"""

TAKT_MD = """\
Läuft ein Takt (Atmung, Bewegung), vibriert das Handy kurz zu jeder neuen Phase —
zusätzlich zum Klang.

Die Vibration des Timers selbst steht unter **Signale**.
"""

SICHERUNG_MD = """\
**Aus (Vorgabe):** Nichts aus der App geht ins Backup des Geräts — nach Gerätewechsel oder
Neuinstallation ist alles weg, was du nicht exportiert hast.

**An:** Datenbank und Messungen gehen in das Backup deines Google-Kontos (mit der
Gerätesperre verschlüsselt, höchstens 25 MB) und kommen auf dem nächsten Gerät zurück.

**GPS-Strecken** nur, wenn du sie ausdrücklich einschließt.

Anhänge (Fotos, Videos, Audio) und Dateien aus Paketen gehen nie mit — sie sind zu groß;
Pakete lassen sich neu laden.
"""

PAPIERKORB_MD = f"""\
Gelöschte Übungen und Pläne liegen im **Papierkorb** und lassen sich dort zurückholen.
Mit dem Schalter löscht die App sie nach {PAPIERKORB_TAGE} Tagen endgültig — Übungen mit
Einträgen im Verlauf nie von selbst, dort fragt sie.

Im **Archiv** liegen Übungen, die du nicht mehr in der Auswahl sehen willst; nichts wird
dort gelöscht.
"""

#: Die Hilfethemen der Seite „Hilfe und Über“: Thema in `components.hilfe.THEMEN` → Untertitel
HILFETHEMEN: dict[str, str] = {
    "notation": "3x15, 30, 15/15/20, +20, 1:30",
    "uebungen": "Eine Kachel für Wandsitz 45° und 90° · woher Übungen kommen",
    "parameter": "Was eine Übung abfragt und was als Ziel gilt",
    "uhr": "Stoppuhr, Timer, „zählt“, Zeit stellen",
    "takt": "Takt, Tempo und „Takt zählt“",
    "workout": "Übergang, Bedingungen, Wege",
    "atmung": "Was „langsame Schwingung unter 8/min“ heißt",
    "herzfrequenz": "Was die Herzfrequenz-Sicht zeigt",
}


def _seite(route: str, name: str, *karten: ft.Control) -> ft.View:
    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(name)),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(ft.Column(spacing=12, controls=list(karten)), expand=False)],
    )


def einstellungen_uebungen(page: ft.Page, state: AppState) -> ft.View:
    """Übungen: offener Eintrag, Fokus, eigene Einteilung."""

    def offen_setzen(e: ft.Event[ft.Dropdown]) -> None:
        state.eintrag_offen_min_setzen(int(e.control.value or OFFEN_MIN_VORGABE))

    def fokus_auto_setzen(e: ft.Event[ft.Switch]) -> None:
        state.fokus_auto_setzen(bool(e.control.value))

    typen, regionen = len(state.tags.namen("typ")), len(state.tags.namen("region"))
    return _seite(
        UEBUNGEN,
        "Übungen",
        karte(
            titel("Eintragen", info_knopf(page, "Eintrag bleibt offen", OFFEN_MD)),
            ft.Dropdown(
                label="Eintrag bleibt offen",
                value=str(state.eintrag_offen_min()),
                options=[
                    ft.DropdownOption(key=str(minuten), text=text)
                    for minuten, text in OFFEN_WAHL.items()
                ],
                on_select=offen_setzen,
                expand=True,
            ),
        ),
        karte(
            titel("Beim Üben", info_knopf(page, "Fokus", FOKUS_MD)),
            ft.Switch(
                label="▶ öffnet den Fokus",
                value=state.fokus_auto(),
                on_change=fokus_auto_setzen,
            ),
        ),
        karte(
            titel("Einteilung"),
            menuezeile(
                page,
                "Typen und Regionen",
                f"Anlegen, umbenennen, löschen · {typen} Typen · {regionen} Regionen",
                ft.Icons.CATEGORY_OUTLINED,
                "/einstellungen/tags",
            ),
            abstand=0,
        ),
    )


def _ist_zeit(teil: str) -> bool:
    """Ist ``teil`` eine Zeit, wie `schnellzeiten_lesen` sie liest („30 s“, „2 min“, „2:30“)?
    Die Funktion selbst liefert für Unlesbares die Vorgabe — daran ist es nicht zu erkennen."""
    from trainingsapp.core.timer import dauer_lesen

    t = teil.strip().lower()
    for endung in ("min", "s"):
        if t.endswith(endung):
            t = t[: -len(endung)].strip()
            break
    return dauer_lesen(t) is not None


def einstellungen_uhr(page: ft.Page, state: AppState) -> ft.View:
    """Timer und Takt: die Timer-Seiten, Schnellzeiten, Vibration des Takts."""

    def gespeichert() -> str:
        return schnellzeiten_text(state.schnellzeiten())

    def lesbar(text: str) -> bool:
        """Leer meint die Vorgabe; sonst muss jeder Teil eine Zeit sein — ein Tippfehler
        ersetzte die eigene Liste sonst still durch die Vorgabe (Review 11.11.2026)."""
        teile = [t for t in text.replace(";", ",").split(",") if t.strip()]
        return all(_ist_zeit(t) for t in teile)

    def schnellzeiten_setzen(e: ft.Event[ft.TextField]) -> None:
        text = e.control.value or ""
        if not lesbar(text):
            e.control.error = "Zeiten wie 30 s, 1 min, 2:30 — durch Komma getrennt."
        else:
            e.control.error = None
            e.control.value = schnellzeiten_text(state.schnellzeiten_setzen(text))
        with contextlib.suppress(Exception):
            e.control.update()

    schnellzeiten_feld = ft.TextField(
        label="Schnellzeiten",
        value=gespeichert(),
        hint_text="30 s, 1 min, 2 min, 5 min, 10 min, 15 min",
        dense=True,
        on_blur=schnellzeiten_setzen,
        on_submit=schnellzeiten_setzen,
    )

    def takt_vibration_setzen(e: ft.Event[ft.Switch]) -> None:
        state.takt_vibration_setzen(bool(e.control.value))

    def geaendert() -> bool:
        """Steht im Feld etwas anderes als gespeichert? (Zurück, ohne das Feld zu verlassen)"""
        text = schnellzeiten_feld.value or ""
        return schnellzeiten_text(schnellzeiten_lesen(text)) != gespeichert()

    def sichern() -> None:
        if lesbar(schnellzeiten_feld.value or ""):  # Unlesbares verwirft Zurück, statt es
            state.schnellzeiten_setzen(schnellzeiten_feld.value or "")  # zur Vorgabe zu machen

    ansicht = _seite(
        UHR,
        "Timer und Takt",
        karte(
            titel("Timer"),
            menuezeile(
                page,
                "Timer",
                f"Stoppuhr, Zeit, Vorlagen · zuletzt „{state.timer_profil().anzeigename}“",
                ft.Icons.TIMER_OUTLINED,
                f"{UHR}/timer",
            ),
            # Alle Timer an einem Ort (Ben, 8.11.2026, `docs/plan_uhr_fokus.md` §5)
            menuezeile(
                page,
                "Alle Timer",
                "Vorlagen, Timer der Übungen und der Pläne — bearbeiten, zuordnen",
                ft.Icons.APPS,
                f"{UHR}/timer/alle",
            ),
            menuezeile(
                page,
                "Signale",
                "Ton, Lautstärke, Countdown, Vibration, Bildschirm an",
                ft.Icons.NOTIFICATIONS_OUTLINED,
                f"{UHR}/timer/signale",
            ),
            abstand=0,
        ),
        karte(
            titel("Zeit stellen", info_knopf(page, "Schnellzeiten", SCHNELLZEITEN_MD)),
            schnellzeiten_feld,
        ),
        karte(
            titel("Takt", info_knopf(page, "Vibration am Phasenwechsel", TAKT_MD)),
            ft.Switch(
                label="Vibration am Phasenwechsel",
                value=state.takt_vibration(),
                on_change=takt_vibration_setzen,
            ),
        ),
    )
    return zurueck_speichert(page, ansicht, geaendert=geaendert, speichern=sichern, meldung="")


def einstellungen_daten(page: ft.Page, state: AppState) -> ft.View:
    """Daten und Sicherung: Geräte-Backup (`core/sicherung.py`, S4), Papierkorb, Archiv."""

    def sicherung_schalter(ev: ft.Event[ft.Switch]) -> None:
        alt = state.sicherung()
        state.sicherung_setzen(Sicherung(an=bool(ev.control.value), strecken=alt.strecken))
        state.neu_zeichnen()  # der Strecken-Schalter erscheint oder verschwindet

    def strecken_schalter(ev: ft.Event[ft.Switch]) -> None:
        state.sicherung_setzen(Sicherung(an=True, strecken=bool(ev.control.value)))

    def papierkorb_auto(ev: ft.Event[ft.Switch]) -> None:
        state.einstellungen.setzen(SettingRepo.PAPIERKORB_AUTO, "1" if ev.control.value else "0")

    sicherung = state.sicherung()
    sicherung_karte = (
        [
            karte(
                titel("Geräte-Backup", info_knopf(page, "Geräte-Backup", SICHERUNG_MD)),
                ft.Switch(
                    label="Mit dem Gerät sichern",
                    value=sicherung.an,
                    on_change=sicherung_schalter,
                ),
                *(
                    [
                        ft.Switch(
                            label="GPS-Strecken einschließen",
                            value=sicherung.strecken,
                            on_change=strecken_schalter,
                        )
                    ]
                    if sicherung.an
                    else []
                ),
            )
        ]
        if ist_aktiv("geraete_sicherung")
        else []
    )
    uebungen = len(state.uebungen.papierkorb())
    plaene = len(state.plaene.papierkorb(state.profil.id))
    archiv = len(state.uebungen.archivierte())
    return _seite(
        DATEN,
        "Daten und Sicherung",
        *sicherung_karte,
        karte(
            titel(
                "Papierkorb und Archiv", info_knopf(page, "Papierkorb und Archiv", PAPIERKORB_MD)
            ),
            ft.Switch(
                label=f"Papierkorb nach {PAPIERKORB_TAGE} Tagen leeren",
                value=state.einstellungen.lesen(SettingRepo.PAPIERKORB_AUTO, "1") == "1",
                on_change=papierkorb_auto,
            ),
            menuezeile(
                page,
                "Papierkorb",
                f"{uebungen} Übungen · {plaene} Pläne — zurückholen oder endgültig löschen",
                ft.Icons.DELETE_OUTLINE,
                "/papierkorb",
            ),
            menuezeile(
                page,
                "Archiv",
                f"{archiv} Übungen — aus der Auswahl genommen, nichts gelöscht",
                ft.Icons.ARCHIVE_OUTLINED,
                "/archiv",
            ),
            abstand=4,
        ),
    )


def einstellungen_hilfe(page: ft.Page, state: AppState) -> ft.View:
    """Hilfe und Über: die Hilfethemen und welche App das ist."""
    version, build = app_version()
    version_text = f"Version {version}" + (f" (Build {build})" if build is not None else "")
    return _seite(
        HILFE,
        "Hilfe und Über",
        karte(
            titel("Hilfe"),
            *[
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.HELP_OUTLINE),
                    title=ft.Text(THEMEN[thema][0]),
                    subtitle=ft.Text(
                        untertitel, size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS
                    ),
                    on_click=hilfe_oeffner(page, thema),
                    content_padding=ft.Padding.only(left=0, right=0),
                    dense=True,
                    data=thema,
                )
                for thema, untertitel in HILFETHEMEN.items()
            ],
            abstand=0,
        ),
        karte(
            titel("Über diese App"),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.INFO_OUTLINE),
                title=ft.Text(version_text),
                subtitle=ft.Text(f"Edition {edition().value}", size=12),
                content_padding=ft.Padding.only(left=0, right=0),
                dense=True,
            ),
            abstand=0,
        ),
    )


__all__ = [
    "DATEN",
    "HILFE",
    "HILFETHEMEN",
    "UEBUNGEN",
    "UHR",
    "einstellungen_daten",
    "einstellungen_hilfe",
    "einstellungen_uebungen",
    "einstellungen_uhr",
]
