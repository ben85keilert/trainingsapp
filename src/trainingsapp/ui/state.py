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

from hrv_core.aufnahme import backups_finden
from hrv_core.regeln import Korrekturregeln

from trainingsapp.config import (
    datenbankpfad,
    messungenverzeichnis,
    paketordner,
    streckenverzeichnis,
)
from trainingsapp.core.darstellung import Darstellung, darstellung_lesen, darstellung_schreiben
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
from trainingsapp.core.kurse import Kurs
from trainingsapp.core.models import Exercise, Subject, jetzt, lokaler_tag
from trainingsapp.core.pakete import Paket
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
from trainingsapp.data.kurse import KursRepo
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.repositories import (
    DayNoteRepo,
    ExerciseRepo,
    HrvRepo,
    PlanRepo,
    SessionRepo,
    SettingRepo,
    StreckeRepo,
    SubjectRepo,
    TagRepo,
)
from trainingsapp.data.seed import pakete_aus_ordner, seed_einspielen
from trainingsapp.data.strecken import verwaiste as strecken_verwaiste
from trainingsapp.data.upgrade import datenformat_aktualisieren
from trainingsapp.devices.bekannte import (
    BekanntesGeraet,
    bekannte_lesen,
    bekannte_schreiben,
    merken,
    vergessen,
)

STANDARD_PROFILNAME = "Ich"

#: Wie die Übungen im Plan beim Training aussehen (Ben, 14.10.2026: „Mache
#: Vorschläge für verschiedene Layouts“). Umschalten unter Einstellungen →
#: Übungen oder oben im Plan; gilt für dieses Gerät.
UNTEREINANDER = "untereinander"
UMSCHALTEN = "umschalten"
AUFKLAPPEN = "aufklappen"
PLAN_DARSTELLUNGEN: dict[str, str] = {
    UNTEREINANDER: "Alle Parameter untereinander",
    UMSCHALTEN: "Ein Parameter, umschaltbar",
    AUFKLAPPEN: "Aufklappen: eine Übung offen",
}


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
    #: Ausdauertrainings mit GPS (Migration 012) — nie synchronisiert
    strecken: StreckeRepo
    #: Typen und Regionen (Migration 013) — Einstellungen → Typen und Regionen
    tags: TagRepo
    #: Übungspakete (Migration 014) — importieren, exportieren, Herkunft
    pakete: PaketRepo
    #: Kurse (Migration 016) — Kapitel, Fortschritt je Profil, Pläne aus Kapiteln
    kurse: KursRepo
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
    #: „Übung hinzufügen“ im Plan: Typ- und Region-Filter (`ui/components/tagwahl.py`)
    hinzufuegen_typen: set[str] = field(default_factory=set)
    hinzufuegen_regionen: set[str] = field(default_factory=set)
    #: Wie viele Übungen der letzte Start neu angelegt hat (für den Startbildschirm)
    neu_eingespielt: int = field(default=0)
    #: Je Paket, was beim Update aus dem Paket fiel und auf „übernehmen oder löschen“
    #: wartet (`PaketRepo.entfallene_offen`) — Dialog beim Start
    entfallene: list[tuple[Paket, list[Exercise], list[Kurs]]] = field(default_factory=list)
    #: Meldungen des Entwicklungs-Loaders (`TRAININGSAPP_PAKETE`, nur am Rechner) —
    #: Karte auf „Heute“, damit ein Tippfehler in einer Paketdatei auffällt
    paketfehler: list[str] = field(default_factory=list)
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
    #: Zählt jeden Routenwechsel — verzögerte Rechnungen einer verlassenen Ansicht
    #: erkennen daran, dass sie nicht mehr gebraucht werden
    route_nummer: int = 0
    #: Planansicht: je Planübung der gewählte Parameter („reps", „hold" …) und
    #: die gewählten Ausprägungen ({"angle": 45}) — nur für diese Sitzung
    parameter_wahl: dict[str, str] = field(default_factory=dict)
    auspraegung_wahl: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Darstellung „Aufklappen": die Planübung, deren Eingabe offen ist
    plan_offen: str | None = None
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
    #: Live-Vollbild (`views.live_vollbild`): Index der gezeigten Kurve (0 = Tachogramm)
    vollbild_kurve: int = 0
    #: Zuletzt gesetzte Bildschirmausrichtung (`ui.ausrichtung`), None = noch keine
    ausrichtung: str | None = None
    #: Wer erfährt, dass sich die Bildschirmgröße geändert hat (Drehen, Fenster);
    #: Ansichten tragen sich beim Bauen ein und ersetzen ihren alten Eintrag
    groesse_beobachter: dict[str, Callable[[], None]] = field(default_factory=dict)
    #: Klappfeld „Notizen" unter der Hauptkurve aufgeklappt
    notizen_offen: bool = False
    #: Einstellungen → HRV-Messung: Teil „Erweitert" aufgeklappt
    hrv_erweitert_offen: bool = False
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
    #: GPS: Ortungsquelle (`devices.gps.GpsQuelle` — auf Android `FletGpsQuelle`,
    #: in `app.py` angelegt; sonst beim ersten Bedarf ein Simulator) und der
    #: laufende Vorabtest (`ui.views.gps_test.GpsTestLauf`) mit seinen Vorgaben
    gps_quelle: Any = None
    gps_test: Any = None
    gps_test_ansicht: int = 0
    gps_test_intervall: float = 1.0
    #: Dauertest: Takt der zweiten Phase (s) — die erste läuft immer mit 1 s
    gps_test_zweite_s: float = 10.0
    #: Laufendes Ausdauertraining (`ui.views.ausdauer.AusdauerLauf`) und seine Vorgaben
    ausdauer: Any = None
    ausdauer_ansicht: int = 0
    ausdauer_sportart: str = "gehen"
    ausdauer_gps: bool = True
    #: Karte im Training zeigen — Kacheln kommen online (einmaliger Hinweis, `HINWEIS_KARTE`)
    ausdauer_karte: bool = True
    #: Streckendateien ohne Zeile `strecke` (Prozess-Tod im Training) — beim Start erkannt
    verwaiste_strecken: list[Path] = field(default_factory=list)
    #: Crash-Backups laufender HRV-Aufnahmen (Akku leer, Absturz) — beim Start erkannt,
    #: `ui.views.messung.backup_dialog` bietet Wiederherstellen an
    hrv_backups: list[Path] = field(default_factory=list)
    gps_test_karte: bool = True
    gps_test_wach: bool = False
    #: App sichtbar? Display aus oder andere App → False (Lebenszyklus in `app.py`)
    im_vordergrund: bool = True
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
        paketfehler = pakete_aus_ordner(con, paketordner())  # nur mit TRAININGSAPP_PAKETE
        datenformat_aktualisieren(con)
        profile = SubjectRepo(con)
        einstellungen = SettingRepo(con)
        profil = cls._aktives_profil(profile, einstellungen)
        offen = cls._papierkorb_aufraeumen(con, einstellungen)
        strecken = StreckeRepo(con)
        try:
            verwaist = strecken_verwaiste(streckenverzeichnis(), strecken.dateipfade())
        except OSError:
            verwaist = []
        try:
            backups = backups_finden(messungenverzeichnis())
        except OSError:
            backups = []
        return cls(
            con=con,
            uebungen=ExerciseRepo(con),
            profile=profile,
            einstellungen=einstellungen,
            plaene=PlanRepo(con),
            sitzungen=SessionRepo(con),
            tagesnotizen=DayNoteRepo(con),
            hrv=HrvRepo(con),
            strecken=strecken,
            verwaiste_strecken=verwaist,
            hrv_backups=backups,
            tags=TagRepo(con),
            pakete=PaketRepo(con),
            kurse=KursRepo(con),
            profil=profil,
            neu_eingespielt=neu,
            entfallene=PaketRepo(con).entfallene_offen(),
            paketfehler=paketfehler,
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

    def profil_loeschen(self, profil_id: str) -> None:
        """Ein Profil ausblenden; war es aktiv, wird das erste übrige aktiv.

        Das letzte Profil bleibt — ohne Profil gäbe es nichts, wem Einträge
        gehören (`ValueError`).
        """
        andere = [p for p in self.profile.alle() if p.id != profil_id]
        if not andere:
            raise ValueError("Das letzte Profil lässt sich nicht löschen.")
        self.profile.loeschen(profil_id)
        if self.profil.id == profil_id:
            self.profil_wechseln(andere[0].id)

    def profil_umbenennen_id(self, profil_id: str, name: str) -> None:
        """Ein beliebiges Profil umbenennen (nicht nur das aktive)."""
        profil = self.profile.laden(profil_id)
        if profil is None or not name.strip():
            return
        profil.name = name.strip()
        self.profile.speichern(profil)
        if self.profil.id == profil_id:
            self.profil = profil

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

    def plan_darstellung(self) -> str:
        """Wie die Übungen im Plan aussehen — ein Schlüssel aus `PLAN_DARSTELLUNGEN`."""
        wert = self.einstellungen.lesen(SettingRepo.PLAN_DARSTELLUNG, UNTEREINANDER)
        return wert if wert in PLAN_DARSTELLUNGEN else UNTEREINANDER

    def plan_darstellung_setzen(self, wert: str) -> None:
        if wert in PLAN_DARSTELLUNGEN:
            self.einstellungen.setzen(SettingRepo.PLAN_DARSTELLUNG, wert)

    def darstellung(self, profil_id: str | None = None) -> Darstellung:
        """Farbprofil, Hell/Dunkel und Verlauf eines Profils (Vorgabe: das aktive)."""
        schluessel = f"{SettingRepo.DARSTELLUNG}:{profil_id or self.profil.id}"
        return darstellung_lesen(self.einstellungen.lesen(schluessel))

    def darstellung_setzen(self, d: Darstellung) -> None:
        """Gilt für das aktive Profil."""
        schluessel = f"{SettingRepo.DARSTELLUNG}:{self.profil.id}"
        self.einstellungen.setzen(schluessel, darstellung_schreiben(d))

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

    # -- Bluetooth: bekannte Geräte ------------------------------------------------

    def bekannte_geraete(self) -> list[BekanntesGeraet]:
        """Zuletzt verbundene Geräte, die neuesten zuerst."""
        return bekannte_lesen(self.einstellungen.lesen(SettingRepo.BEKANNTE_GERAETE))

    def geraet_merken(self, geraet_id: str, name: str, profil_id: str) -> None:
        neu = BekanntesGeraet(geraet_id, name or geraet_id, profil_id, jetzt().isoformat())
        liste = merken(self.bekannte_geraete(), neu)
        self.einstellungen.setzen(SettingRepo.BEKANNTE_GERAETE, bekannte_schreiben(liste))

    def geraet_vergessen(self, geraet_id: str) -> None:
        liste = vergessen(self.bekannte_geraete(), geraet_id)
        self.einstellungen.setzen(SettingRepo.BEKANNTE_GERAETE, bekannte_schreiben(liste))

    def profil_umbenennen(self, name: str) -> None:
        self.profil.name = name.strip()
        self.profile.speichern(self.profil)


__all__ = [
    "AUFKLAPPEN",
    "PLAN_DARSTELLUNGEN",
    "STANDARD_PROFILNAME",
    "UMSCHALTEN",
    "UNTEREINANDER",
    "AppState",
]
