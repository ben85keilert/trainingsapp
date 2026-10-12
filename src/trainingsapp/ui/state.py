"""Zustand, der so lange lebt wie die App.

Nicht so lange wie eine Ansicht: Ansichten werden bei jedem Wechsel neu
gebaut (L03). Was den Wechsel überleben muss, liegt hier — die
Datenbankverbindung, das aktive Profil, später die laufende HRV-Messung.

Dieses Modul importiert **kein** ``flet``. Der Zustand soll in Tests ohne
Oberfläche funktionieren, und genau das prüft ``tests/test_state.py``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from trainingsapp.config import datenbankpfad
from trainingsapp.core.models import Subject, jetzt, lokaler_tag
from trainingsapp.core.verlauf import MODUS_NUMMER
from trainingsapp.data.db import oeffnen
from trainingsapp.data.repositories import (
    DayNoteRepo,
    ExerciseRepo,
    PlanRepo,
    SessionRepo,
    SettingRepo,
    SubjectRepo,
)
from trainingsapp.data.seed import seed_einspielen

STANDARD_PROFILNAME = "Ich"


@dataclass
class AppState:
    """Alles, was die Ansichten gemeinsam brauchen."""

    con: sqlite3.Connection
    uebungen: ExerciseRepo
    profile: SubjectRepo
    einstellungen: SettingRepo
    plaene: PlanRepo
    sitzungen: SessionRepo
    tagesnotizen: DayNoteRepo
    profil: Subject
    #: Welcher Reiter der Navigationsleiste aktiv ist
    nav_index: int = 0
    #: Suchtext und Kategoriefilter des Katalogs — überleben den Ansichtswechsel
    suchtext: str = ""
    kategorie: str | None = None
    #: Wie viele Übungen der letzte Start neu angelegt hat (für den Startbildschirm)
    neu_eingespielt: int = field(default=0)
    #: Ordnung der Tagesansicht: "plan", "zeit" oder "uebung"
    tag_ordnung: str = "plan"
    #: Pläne, die gerade im Bearbeiten-Modus stehen (überlebt den Routenwechsel)
    plan_bearbeiten: set[str] = field(default_factory=set)
    #: Verlauf: angezeigter Monat (erster Tag), gewählte Kennzahl, X-Achse
    verlauf_monat: date = field(default_factory=lambda: lokaler_tag(jetzt()).replace(day=1))
    verlauf_metrik: str | None = None
    verlauf_modus: str = MODUS_NUMMER
    verlauf_uebung: str | None = None
    #: Baut den Ansichtsstapel zur aktuellen Route neu — setzt `app.main()`.
    #: Views rufen es nach Änderungen, die die Route nicht wechseln (ein Tipp
    #: auf „gemacht" bleibt auf derselben Planansicht).
    neu_zeichnen: Callable[[], None] = field(default=lambda: None)

    # -- Lebenszyklus --------------------------------------------------------

    @classmethod
    def starten(cls, db_pfad: Path | str | None = None) -> AppState:
        """Öffnet die Datenbank, spielt den Seed ein und lädt das aktive Profil.

        Alles, was beim Start passieren muss, an einer Stelle — und ohne
        Oberfläche aufrufbar.
        """
        con = oeffnen(db_pfad if db_pfad is not None else datenbankpfad())
        neu = seed_einspielen(con)
        profile = SubjectRepo(con)
        einstellungen = SettingRepo(con)
        profil = cls._aktives_profil(profile, einstellungen)
        return cls(
            con=con,
            uebungen=ExerciseRepo(con),
            profile=profile,
            einstellungen=einstellungen,
            plaene=PlanRepo(con),
            sitzungen=SessionRepo(con),
            tagesnotizen=DayNoteRepo(con),
            profil=profil,
            neu_eingespielt=neu,
        )

    @staticmethod
    def heute() -> date:
        """Der lokale Kalendertag — die Bezugsgröße der App."""
        return lokaler_tag(jetzt())

    @staticmethod
    def _aktives_profil(profile: SubjectRepo, einstellungen: SettingRepo) -> Subject:
        """Das zuletzt aktive Profil; fehlt eines, das erste; fehlt alles, ein neues."""
        gemerkt = einstellungen.lesen(SettingRepo.AKTIVES_PROFIL)
        if gemerkt and (profil := profile.laden(gemerkt)) is not None:
            return profil
        vorhandene = profile.alle()
        if vorhandene:
            profil = vorhandene[0]
        else:
            profil = Subject(name=STANDARD_PROFILNAME)
            profile.speichern(profil)
        einstellungen.setzen(SettingRepo.AKTIVES_PROFIL, profil.id)
        return profil

    def schliessen(self) -> None:
        self.con.close()

    # -- Profile -------------------------------------------------------------

    def profil_wechseln(self, profil_id: str) -> Subject:
        profil = self.profile.laden(profil_id)
        if profil is None:
            raise KeyError(profil_id)
        self.profil = profil
        self.einstellungen.setzen(SettingRepo.AKTIVES_PROFIL, profil.id)
        return profil

    def profil_anlegen(self, name: str, birth_year: int | None = None) -> Subject:
        """Legt ein Profil an und macht es zum aktiven."""
        profil = Subject(name=name.strip(), birth_year=birth_year)
        self.profile.speichern(profil)
        return self.profil_wechseln(profil.id)

    def profil_umbenennen(self, name: str) -> None:
        self.profil.name = name.strip()
        self.profile.speichern(self.profil)


__all__ = ["STANDARD_PROFILNAME", "AppState"]
