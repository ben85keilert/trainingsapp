"""Zustand, der so lange lebt wie die App.

Nicht so lange wie eine Ansicht: Ansichten werden bei jedem Wechsel neu
gebaut (L03). Was den Wechsel überleben muss, liegt hier — die
Datenbankverbindung, das aktive Profil, später die laufende HRV-Messung.

Dieses Modul importiert **kein** ``flet``. Der Zustand soll in Tests ohne
Oberfläche funktionieren, und genau das prüft ``tests/test_state.py``.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from trainingsapp.config import datenbankpfad
from trainingsapp.core.hrv_ansicht import (
    Ansicht,
    ansicht_lesen,
    ansichten_lesen,
    ansichten_schreiben,
)
from trainingsapp.core.hrv_einstellungen import (
    HrvEinstellungen,
    einstellungen_lesen,
    einstellungen_schreiben,
)
from trainingsapp.core.models import Subject, jetzt, lokaler_tag
from trainingsapp.core.timer import (
    TimerProfil,
    TimerSignale,
    timer_profile_lesen,
    timer_profile_schreiben,
    timer_signale_lesen,
    timer_signale_schreiben,
)
from trainingsapp.core.verlauf import MODUS_NUMMER
from trainingsapp.data.db import oeffnen
from trainingsapp.data.repositories import (
    DayNoteRepo,
    ExerciseRepo,
    HrvRepo,
    PlanRepo,
    SessionRepo,
    SettingRepo,
    SubjectRepo,
)
from trainingsapp.data.seed import seed_einspielen
from trainingsapp.data.upgrade import datenformat_aktualisieren
from trainingsapp.hrv_core.regeln import Korrekturregeln

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
    hrv: HrvRepo
    profil: Subject
    #: Welcher Reiter der Navigationsleiste aktiv ist — als Schlüssel, nicht als
    #: Index: der Reiter „Messung" lässt sich ausblenden (`app.REITER`)
    reiter: str = "heute"
    #: Suchtext und Tag-Filter des Katalogs — überleben den Ansichtswechsel.
    #: Innerhalb einer Art genügt ein Treffer (oder), zwischen den Arten müssen
    #: beide passen (und). Leer = kein Filter.
    suchtext: str = ""
    typ_filter: set[str] = field(default_factory=set)  # Kräftigung, Dehnung, …
    region_filter: set[str] = field(default_factory=set)  # Nacken, Bein, …
    #: Wie viele Übungen der letzte Start neu angelegt hat (für den Startbildschirm)
    neu_eingespielt: int = field(default=0)
    #: Übungen, deren Papierkorbfrist abgelaufen ist, die aber einen Verlauf
    #: haben — die Automatik löscht sie nicht, der Papierkorb fragt nach
    papierkorb_offen: int = 0
    #: Reiter „Übungen": 0 = Katalog, 1 = Pläne
    uebungen_tab: int = 0
    #: Ordnung der Tagesansicht: "plan", "zeit" oder "uebung"
    tag_ordnung: str = "plan"
    #: Verlauf: angezeigter Monat (erster Tag), gewählte Kennzahl, X-Achse
    verlauf_monat: date = field(default_factory=lambda: lokaler_tag(jetzt()).replace(day=1))
    verlauf_metrik: str | None = None
    verlauf_modus: str = MODUS_NUMMER
    verlauf_uebung: str | None = None
    #: Kachel-Kurve: welches Mengenfeld, welche Variante (None = alle zusammen)
    verlauf_feld: str | None = None
    verlauf_variante: str | None = None
    #: Scrollposition je scrollbarer Fläche (Schlüssel meist die Route) — damit
    #: der Neubau nach einem Tipp nicht wieder oben beginnt
    scroll_offsets: dict[str, float] = field(default_factory=dict)
    #: Planansicht: je Planübung der gewählte Parameter („reps", „hold" …) und
    #: die gewählten Ausprägungen ({"angle": 45}) — nur für diese Sitzung
    parameter_wahl: dict[str, str] = field(default_factory=dict)
    auspraegung_wahl: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Laufende HRV-Messung — lebt hier, nicht in der Ansicht, damit sie den
    #: Reiterwechsel überlebt (L03). Typ: `devices.messlauf.Messlauf`.
    messlauf: Any = None
    #: Bluetooth-Zugang (nur Android, `ui.geraete.FletBleTransport`); hält den
    #: Flet-Service stark referenziert, sonst räumt Flet ihn ab.
    ble_transport: Any = None
    #: Reiter „Messung": 0 = Live, 1 = Aufzeichnungen
    messung_tab: int = 0
    #: Zählt jeden Aufbau der Hauptansicht hoch; eine Live-Ansicht, deren Nummer
    #: nicht mehr stimmt, ist nicht zu sehen und rechnet nichts mehr
    live_ansicht: int = 0
    #: Live-Ansicht zurückgeblättert: rechter Rand in s; None = folgt der Messung
    messung_ende_s: float | None = None
    #: Klappfeld „Notizen" unter der Hauptkurve aufgeklappt
    notizen_offen: bool = False
    #: Notizen: Übungen zum Antippen eingeblendet, und aus welchem Plan
    #: (Plan-ID; ``None`` = der erste anstehende, „alle" = der ganze Katalog)
    notiz_uebungen_offen: bool = False
    notiz_uebungen_quelle: str | None = None
    #: Laufender Timer (`core.timer.TimerLauf`) — lebt hier, damit er den
    #: Ansichtswechsel überlebt; die Aufgabe, die ihn ticken lässt
    timer: Any = None
    timer_aufgabe: Any = None
    #: Vibration (Flet-Dienst `HapticFeedback`), setzt `app.main()`
    haptik: Any = None
    #: Signaltöne (`flet_ton.FletTon`, nur in der gebauten App) und ob sie geladen sind
    ton: Any = None
    toene_geladen: bool = False
    #: Bildschirm anlassen, solange der Timer läuft (Flet-Dienst `Wakelock`)
    wach: Any = None
    #: Wer erfährt, dass der Timer Notizen in die laufende Messung geschrieben hat
    notiz_beobachter: dict[str, Callable[[], None]] = field(default_factory=dict)
    #: Wer bei jedem Tick des Timers aufgefrischt wird (Name → Funktion);
    #: Ansichten tragen sich beim Bauen ein und ersetzen ihren alten Eintrag
    timer_beobachter: dict[str, Callable[[], None]] = field(default_factory=dict)
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
        datenformat_aktualisieren(con)
        profile = SubjectRepo(con)
        einstellungen = SettingRepo(con)
        profil = cls._aktives_profil(profile, einstellungen)
        offen = cls._papierkorb_aufraeumen(con, einstellungen)
        return cls(
            con=con,
            uebungen=ExerciseRepo(con),
            profile=profile,
            einstellungen=einstellungen,
            plaene=PlanRepo(con),
            sitzungen=SessionRepo(con),
            tagesnotizen=DayNoteRepo(con),
            hrv=HrvRepo(con),
            profil=profil,
            neu_eingespielt=neu,
            papierkorb_offen=offen,
        )

    @staticmethod
    def _papierkorb_aufraeumen(con: sqlite3.Connection, einstellungen: SettingRepo) -> int:
        """Beim Start: Fälliges endgültig löschen, sofern eingeschaltet (Vorgabe: an)."""
        if einstellungen.lesen(SettingRepo.PAPIERKORB_AUTO, "1") != "1":
            return 0
        PlanRepo(con).papierkorb_aufraeumen()  # alle Profile, nicht nur das aktive
        _, offen = ExerciseRepo(con).papierkorb_aufraeumen()
        return len(offen)

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

    # -- HRV: Korrekturregeln und Ansichten -----------------------------------

    def korrekturregeln(self) -> Korrekturregeln:
        """Gerätelokale Vorgabe der automatischen Korrektur."""
        return Korrekturregeln.aus_json(self.einstellungen.lesen(SettingRepo.HRV_KORREKTUR))

    def korrekturregeln_setzen(self, regeln: Korrekturregeln) -> None:
        self.einstellungen.setzen(SettingRepo.HRV_KORREKTUR, regeln.als_json())
        if self.messlauf is not None:
            self.messlauf.regeln_setzen(regeln)

    def ansicht(self) -> Ansicht:
        """Die aktuelle Ansicht der Verlaufskurven (live und in der Aufzeichnung)."""
        return ansicht_lesen(self.einstellungen.lesen(SettingRepo.HRV_ANSICHT))

    def ansicht_setzen(self, ansicht: Ansicht) -> None:
        self.einstellungen.setzen(SettingRepo.HRV_ANSICHT, json.dumps(ansicht.als_dict()))

    def ansichten(self) -> list[Ansicht]:
        """Gespeicherte Ansichten, nach Namen."""
        gespeichert = ansichten_lesen(self.einstellungen.lesen(SettingRepo.HRV_ANSICHTEN))
        return sorted(gespeichert, key=lambda a: a.name.casefold())

    def ansicht_speichern(self, ansicht: Ansicht) -> None:
        """Unter ihrem Namen speichern — eine gleichnamige wird ersetzt."""
        andere = [a for a in self.ansichten() if a.name != ansicht.name]
        self.einstellungen.setzen(
            SettingRepo.HRV_ANSICHTEN, ansichten_schreiben([*andere, ansicht])
        )

    def ansicht_loeschen(self, name: str) -> None:
        rest = [a for a in self.ansichten() if a.name != name]
        self.einstellungen.setzen(SettingRepo.HRV_ANSICHTEN, ansichten_schreiben(rest))

    def hrv_einstellungen(self) -> HrvEinstellungen:
        """Was die Messung zeigt — Kacheln, Fenster, Analysebereiche."""
        return einstellungen_lesen(self.einstellungen.lesen(SettingRepo.HRV_EINSTELLUNGEN))

    def hrv_einstellungen_setzen(self, e: HrvEinstellungen) -> None:
        self.einstellungen.setzen(SettingRepo.HRV_EINSTELLUNGEN, einstellungen_schreiben(e))

    def hrv_zuruecksetzen(self) -> None:
        """Einstellungen, aktuelle Ansicht und Korrekturregeln auf die Vorgaben.

        Unter Namen gespeicherte Ansichten bleiben — sie sind Arbeit des Nutzers.
        """
        for schluessel in (
            SettingRepo.HRV_EINSTELLUNGEN,
            SettingRepo.HRV_ANSICHT,
            SettingRepo.HRV_KORREKTUR,
        ):
            self.einstellungen.loeschen(schluessel)
        if self.messlauf is not None:
            self.messlauf.regeln_setzen(Korrekturregeln())

    # -- Timer -------------------------------------------------------------------

    def timer_profile(self) -> list[TimerProfil]:
        """Gespeicherte Profile; ohne eigene die zwei Vorlagen."""
        return timer_profile_lesen(self.einstellungen.lesen(SettingRepo.TIMER_PROFILE))

    def timer_profile_setzen(self, profile: list[TimerProfil]) -> None:
        self.einstellungen.setzen(SettingRepo.TIMER_PROFILE, timer_profile_schreiben(profile))

    def timer_profil(self) -> TimerProfil:
        """Das zuletzt benutzte Profil — fehlt es, das erste."""
        profile = self.timer_profile()
        gemerkt = self.einstellungen.lesen(SettingRepo.TIMER_AKTIV)
        return next((p for p in profile if p.id == gemerkt), profile[0])

    def timer_profil_waehlen(self, profil_id: str) -> None:
        self.einstellungen.setzen(SettingRepo.TIMER_AKTIV, profil_id)

    def timer_signale(self) -> TimerSignale:
        """Ton, Countdown, Vibration, Bildschirm an, Notizen — alles an, wenn nichts gespeichert."""
        return timer_signale_lesen(self.einstellungen.lesen(SettingRepo.TIMER_SIGNALE))

    def timer_signale_setzen(self, signale: TimerSignale) -> None:
        self.einstellungen.setzen(SettingRepo.TIMER_SIGNALE, timer_signale_schreiben(signale))

    def profil_umbenennen(self, name: str) -> None:
        self.profil.name = name.strip()
        self.profile.speichern(self.profil)


__all__ = ["STANDARD_PROFILNAME", "AppState"]
