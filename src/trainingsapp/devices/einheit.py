"""Der Ablauf einer Einheit: Teile bereitstellen, gemeinsam starten, im Takt sammeln.

Datenmodell und Regeln stehen in `trainingsapp.core.einheit` (Vertrag
``docs/plan_einheit.md``); hier läuft es ab:

1. `Einheitslauf.hinzufuegen` — HRV (`HrvBaustein`), Timer (`TimerBaustein`),
   GPS (``devices.strecke_baustein``) …
2. `Einheitslauf.vorbereiten` (async, alle zugleich) — bis jeder Teil ``bereit``
   ist. Ein Fehler gehört dem Teil, nicht der Einheit (`fehler`).
3. `Einheitslauf.starten` (synchron) — eine Uhrzeit für alle. Mit Countdown nimmt
   eine mitstartende HRV-Aufnahme schon ab jetzt auf (Vorlauf); die übrigen Teile
   starten, sobald der Takt das Ende des Countdowns erreicht — mit genau diesem t0.
4. `Einheitslauf.takt` (`laufen` ruft ihn alle `TICK_S`) — sammelt die Ereignisse der
   Teile, schreibt sie in die Zeitleiste (`Senke`), projiziert sie in die laufende
   HRV-Aufnahme (Marke + Spur, 5-s-Regel) und meldet sie dem `beobachter`.
5. `Einheitslauf.beenden` und `abschliessen` — Ende je Teil nach `am_ende_stoppen`
   (Vorgabe: was ich nicht gestartet habe, stoppe ich nicht).

**Einzeln gestartet** (Ben, 18.10.2026: „Wenn aber Dienste einzeln gestartet werden, sollten
diese auch in die Leiste und zu Heute-Einheit … Ohne die manuelle Verbindung kann man die
ja trotzdem noch verketten“): Ein Teil kann einer laufenden Einheit beitreten
(`Einheitslauf.beitreten`) — er beginnt dann auf ihrer Achse. Eine Einheit, die nur aus
solchen Einzelstarts entstand, endet von selbst, wenn nichts in ihr mehr läuft
(`ende_wenn_alles_fertig`, `aktiv` je Teil).

Die Teile kennen einander nicht. Kein flet: Speichern in die Datenbank und das
Eintragen einer Aufnahme bleiben beim Aufrufer (UI), wie bei `Messlauf`.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..core.einheit import (
    MIN_MARKE_S,
    Baustein,
    Beteiligung,
    Ereignis,
    Projektion,
    Rolle,
    Senke,
    Zeitbasis,
    Zustand,
    in_uebung,
    projektion,
)
from ..core.laufend import uhr as uhr_text
from ..core.limits import TICK_S
from ..core.models import new_id
from ..core.timer import TimerLauf
from .base import Verbindung
from .messlauf import Gespeichert, Messlauf

#: So viel Tiefschlaf (s) zwischen zwei Takten wird ein Ereignis ``einheit/schlaf``
SCHLAF_AB_S = 2.0


def _schlafversatz() -> float | None:
    """Wie weit die Bootuhr der monotonen voraus ist — wächst er, lag die CPU im Tiefschlaf.

    ``time.monotonic`` steht im Tiefschlaf (CLOCK_MONOTONIC), ``CLOCK_BOOTTIME`` nicht
    (Linux, Android). Anderswo ``None``.
    """
    boot = getattr(time, "CLOCK_BOOTTIME", None)
    if boot is None:
        return None
    try:
        return time.clock_gettime(boot) - time.monotonic()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Teile
# ---------------------------------------------------------------------------


class TimerBaustein:
    """Der Timer als Teil einer Einheit — er meldet Abschnitte, Pause, Weiter und Ende.

    Die Einheit ist dann der **einzige** Abnehmer von `TimerLauf.neue_marken` (die
    Oberfläche spielt nur noch die Töne). Gestartet wird immer von vorn, auf t0.
    """

    art = "timer"

    def __init__(self, lauf: TimerLauf, *, uhr: Callable[[], float] | None = None) -> None:
        self.lauf = lauf
        if uhr is not None:
            lauf.uhr_setzen(uhr)
        self._t0: float | None = None
        self._lief = False
        self._abgebrochen_gemeldet = False

    def uhr_uebernehmen(self, uhr: Callable[[], float]) -> None:
        """Die Uhr der Einheit — beim HRV-Simulator läuft sie schneller (`Einheitslauf`)."""
        self.lauf.uhr_setzen(uhr)

    @property
    def bereit(self) -> bool:
        return bool(self.lauf.profil.abschnitte)

    @property
    def aktiv(self) -> bool:
        """Läuft noch etwas? Angehalten ja — fertig oder abgebrochen nicht."""
        return self._t0 is not None and not (self.lauf.fertig or self.lauf.abgebrochen)

    def status(self) -> str:
        p = self.lauf.profil
        return p.kurztext() if p.abschnitte else "ohne Abschnitte"

    async def vorbereiten(self) -> None:
        return None

    def starten(self, t0: float, bei: float | None = None) -> Beteiligung:
        """Von vorn, auf t0 — oder ``bei`` (Uhr der Einheit) mit t0 als Bezug: so startet
        ein Plan-Ablauf den Timer jeder Übung später, auf derselben Achse."""
        self._t0 = t0
        self.lauf.zuruecksetzen()
        self.lauf.start(bei=t0 if bei is None else bei)
        self._lief = True
        return Beteiligung("timer", Rolle.MITSTARTEN, daten={"profil": self.lauf.profil.name})

    def takt(self, jetzt: float) -> list[Ereignis]:
        if self._t0 is None:
            return []
        t0 = self._t0
        out: list[Ereignis] = []
        marken = self.lauf.neue_marken()
        laeuft = self.lauf.laeuft
        start = self.lauf.start_uhr
        if self.lauf.abgebrochen:
            # Abgebrochen (Ben, 17.10.2026): das Ende des Timers, nicht eine Pause —
            # eingetragen wird daraus nichts (`core.timer_eintrag`)
            if not self._abgebrochen_gemeldet:
                self._abgebrochen_gemeldet = True
                halt = self.lauf.angehalten_bei if self.lauf.angehalten_bei is not None else jetzt
                out.append(
                    Ereignis(
                        halt - t0, "timer", "ende", "Timer abgebrochen", {"grund": "abgebrochen"}
                    )
                )
            self._lief = False
            return out
        if self._lief and not laeuft and not self.lauf.fertig:
            halt = self.lauf.angehalten_bei if self.lauf.angehalten_bei is not None else jetzt
            out.append(Ereignis(halt - t0, "timer", "pause", "Timer angehalten"))
        elif not self._lief and laeuft and start is not None:
            # Geht es im selben Abschnitt weiter, meldet `neue_marken` nichts — dann ist es
            # ein „weiter“; ein übersprungener Abschnitt beginnt mit seiner eigenen Marke.
            if not any(m.bei is not None and m.bei >= start - 1e-6 for m in marken):
                nummer = self.lauf.stand().nummer
                name, runde, von = self.lauf.angaben(nummer)
                abschnitt = self.lauf.abschnittsname(nummer)
                weiter = {"abschnitt": abschnitt, "name": name, "runde": runde, "von": von}
                weiter.update(self._ablauf(self.lauf.abschnitt(nummer)))
                out.append(Ereignis(start - t0, "timer", "weiter", f"weiter: {abschnitt}", weiter))
        self._lief = laeuft
        for m in marken:
            t = (m.bei if m.bei is not None else jetzt - m.vor_s) - t0
            if m.ende:
                out.append(Ereignis(t, "timer", "ende", m.text))
                continue
            daten: dict[str, Any] = {
                "abschnitt": m.abschnitt,
                "name": m.name,
                "runde": m.runde,
                "von": m.von,
                "profil": self.lauf.profil.name,
                "profil_id": self.lauf.profil.id,
            }
            if m.soll_s:
                daten["soll_s"] = m.soll_s
            if not m.zaehlt:
                daten["zaehlt"] = False
            out.append(Ereignis(t, "timer", "abschnitt", m.text, daten))
        return out

    def _ablauf(self, abschnitt: Any) -> dict[str, Any]:
        """Welcher Ablauf und wie lang geplant (P54): ``profil_id``, ``soll_s`` (nicht bei
        der Stoppuhr)."""
        d: dict[str, Any] = {"profil_id": self.lauf.profil.id}
        if abschnitt is not None and not self.lauf.vorwaerts:
            d["soll_s"] = float(abschnitt.dauer_s)
        return d

    def beenden(self, jetzt: float) -> list[Ereignis]:
        out = self.takt(jetzt)
        if self._t0 is not None and not self.lauf.fertig and not self._abgebrochen_gemeldet:
            self.lauf.pause()
            out.append(
                Ereignis(jetzt - self._t0, "timer", "ende", "Timer beendet", {"grund": "beendet"})
            )
        return out


class HrvBaustein:
    """Die HRV-Messung als Teil einer Einheit.

    Läuft schon eine Aufnahme, tritt sie bei (`Rolle.LAEUFT_SCHON`) und läuft danach
    weiter; sonst beginnt die Einheit eine (`aufnahme_beginnen`, beim Countdown schon
    vorher). Verbinden bleibt Sache der Messansicht — bereit ist der Teil, wenn der
    Gurt verbunden ist. Endet die Aufnahme mitten in der Einheit oder beginnt eine
    neue, meldet der Takt das (``hrv/verlassen``, ``hrv/beigetreten``).
    """

    art = "hrv"

    def __init__(self, messlauf: Messlauf, *, basis: Path | None = None) -> None:
        self.messlauf = messlauf
        #: Datenverzeichnis zum Speichern, wenn die Aufnahme mit der Einheit endet
        self.basis = basis
        self.rolle = Rolle.LAEUFT_SCHON if messlauf.aufnahme is not None else Rolle.MITSTARTEN
        self._aufnahme: Any = None
        self._t0: float | None = None
        self.beteiligung: Beteiligung | None = None

    @property
    def bereit(self) -> bool:
        lauf = self.messlauf
        return lauf.aufnahme is not None or lauf.status.verbindung == Verbindung.VERBUNDEN

    @property
    def aktiv(self) -> bool:
        """Läuft eine Aufnahme?"""
        return self.messlauf.aufnahme is not None

    def status(self) -> str:
        lauf = self.messlauf
        if lauf.aufnahme is not None:
            return f"läuft seit {uhr_text(lauf.aufnahme_dauer_s())} · bekommt eine Marke"
        if lauf.status.verbindung == Verbindung.VERBUNDEN:
            return f"{lauf.geraet_name or 'Gurt'} verbunden · startet mit"
        return "nicht verbunden"

    async def vorbereiten(self) -> None:
        return None

    def aufnahme_beginnen(self, start_mono: float, start_utc: datetime) -> None:
        """Die Aufnahme mit der Einheit beginnen — auf den vorgegebenen Nullpunkt."""
        if self.messlauf.aufnahme is None:
            self.messlauf.aufnahme_starten(start_mono=start_mono, start_utc=start_utc)
            self.rolle = Rolle.MITSTARTEN

    def starten(self, t0: float) -> Beteiligung:
        self._t0 = t0
        self._aufnahme = self.messlauf.aufnahme
        self.beteiligung = self._beteiligung(self.rolle, von_s=0.0)
        return self.beteiligung

    def _beteiligung(self, rolle: Rolle, *, von_s: float) -> Beteiligung:
        lauf = self.messlauf
        aufnahme = lauf.aufnahme
        versatz = None
        if aufnahme is not None and self._t0 is not None:
            versatz = round(aufnahme.start_mono - self._t0, 6)
        return Beteiligung(
            "hrv",
            rolle,
            datei=lauf.datei_relativ() or "",
            versatz_s=versatz,
            von_s=von_s,
            daten={"teil": lauf.geraet_name},
        )

    def takt(self, jetzt: float) -> list[Ereignis]:
        lauf = self.messlauf
        if self._t0 is None or lauf.aufnahme is self._aufnahme:
            return []
        t0 = self._t0
        out: list[Ereignis] = []
        if self._aufnahme is not None and self.beteiligung is not None:
            out.append(
                Ereignis(jetzt - t0, "hrv", "verlassen", daten={"datei": self.beteiligung.datei})
            )
        self._aufnahme = lauf.aufnahme
        if lauf.aufnahme is not None:
            von = lauf.aufnahme.start_mono - t0
            self.beteiligung = self._beteiligung(Rolle.MITSTARTEN, von_s=max(von, 0.0))
            out.append(
                Ereignis(
                    max(von, 0.0),
                    "hrv",
                    "beigetreten",
                    daten={
                        "datei": self.beteiligung.datei,
                        "versatz_s": self.beteiligung.versatz_s,
                        "teil": lauf.geraet_name,
                    },
                )
            )
        return out

    def beenden(self, jetzt: float) -> list[Ereignis]:
        return self.takt(jetzt)

    def projizieren(self, p: Projektion, bei: float) -> bool:
        """Eine Projektion als Notiz und Grenze in die laufende Aufnahme — wenn es sie gibt."""
        lauf = self.messlauf
        if lauf.aufnahme is None or lauf.aufnahme is not self._aufnahme:
            return False
        eintrag = lauf.abschnitt_markieren(
            p.text,
            name=p.name,
            ende=p.ende,
            spur=p.spur,
            bei=bei,
            marke=p.marke,
            als_notiz=p.als_notiz,
            uebungen=p.uebungen,
        )
        return eintrag is not None

    def abschliessen(self) -> Gespeichert | None:
        """Die Aufnahme beenden und speichern — nur mit Datenverzeichnis."""
        if self.basis is None or self.messlauf.aufnahme is None:
            return None
        return self.messlauf.aufnahme_stoppen(self.basis)


@dataclass
class UebungKontext:
    """Wozu eine Übung lief — der Aufrufer trägt damit ins Tagebuch ein (``ui``)."""

    uebung_id: str
    name: str
    plan_id: str | None = None
    item_id: str | None = None
    #: Welches Feld die Zeit bekommt (``hold``/``duration``) — ``None``: nur „gemacht“
    zeitfeld: str | None = None


class UebungBaustein:
    """Eine Übung als Teil einer Einheit (Ben, 17.10.2026): Anfang und Ende in der
    Zeitleiste (``plan/uebung_start``, ``plan/uebung_ende``) — in einer laufenden
    HRV-Aufnahme ein Abschnitt auf der Spur „uebung“ mit den Marken „Planke beginnt“
    und „Planke fertig“. Ins Tagebuch trägt der Aufrufer aus der Zeitleiste ein
    (`core.timer_eintrag`); dafür gibt `abschliessen_async` den `UebungKontext`.
    """

    art = "plan"

    def __init__(self, kontext: UebungKontext) -> None:
        self.kontext = kontext
        self._t0: float | None = None
        self._gemeldet = False
        self._ende_gemeldet = False

    @property
    def name(self) -> str:
        return self.kontext.name

    @property
    def bereit(self) -> bool:
        return True

    def status(self) -> str:
        return "trägt die Zeit ein" if self.kontext.zeitfeld else "trägt „gemacht“ ein"

    async def vorbereiten(self) -> None:
        return None

    def _daten(self) -> dict[str, Any]:
        """Was die Zeitleiste über die Übung festhält — genug, um einen abgebrochenen
        Lauf später doch einzutragen („Läufe heute“)."""
        k = self.kontext
        daten: dict[str, Any] = {"uebung": k.uebung_id, "name": k.name}
        if k.plan_id:
            daten["plan"] = k.plan_id
        if k.item_id:
            daten["planuebung"] = k.item_id
        if k.zeitfeld:
            daten["zeitfeld"] = k.zeitfeld
        return daten

    def starten(self, t0: float) -> Beteiligung:
        self._t0 = t0
        return Beteiligung("plan", Rolle.MITSTARTEN, daten=self._daten())

    def takt(self, jetzt: float) -> list[Ereignis]:
        if self._t0 is None or self._gemeldet:
            return []
        self._gemeldet = True
        return [Ereignis(0.0, "plan", "uebung_start", f"{self.name} beginnt", self._daten())]

    def beenden(self, jetzt: float) -> list[Ereignis]:
        out = self.takt(jetzt)
        if self._t0 is not None and not self._ende_gemeldet:
            self._ende_gemeldet = True
            out.append(
                Ereignis(
                    jetzt - self._t0, "plan", "uebung_ende", f"{self.name} fertig", self._daten()
                )
            )
        return out

    async def abschliessen_async(self, stoppen: bool = True) -> UebungKontext:
        return self.kontext


# ---------------------------------------------------------------------------
# Die Einheit
# ---------------------------------------------------------------------------


@dataclass
class Abschluss:
    """Was nach dem Ende übrig ist und der Aufrufer eintragen muss."""

    #: die gespeicherte HRV-Aufnahme, wenn sie mit der Einheit endete
    hrv: Gespeichert | None = None
    #: je weiterem Teil, was er hinterlässt (``devices.strecke_baustein``: die Strecke)
    teile: dict[str, Any] = field(default_factory=dict)


class Einheitslauf:
    """Klammer um HRV, Timer, GPS … — gemeinsam vorbereitet, gemeinsam gestartet."""

    def __init__(
        self,
        *,
        uhr: Callable[[], float] = time.monotonic,
        jetzt_utc: Callable[[], datetime] = lambda: datetime.now(UTC),
        senke: Senke | None = None,
        subject_id: str | None = None,
        titel: str = "",
    ) -> None:
        self.id = new_id()
        #: Uhr der Einheit — mit HRV die des `Messlauf` (`Messlauf.uhr`)
        self.uhr = uhr
        #: Läuft die Uhr in echter Zeit? Nur dann ist ein Sprung der Boot-Uhr Tiefschlaf
        #: (Simulator und Attrappen laufen schneller oder stehen — H26)
        self.echtzeit = uhr is time.monotonic
        self._jetzt_utc = jetzt_utc
        self.senke = senke
        self.subject_id = subject_id
        self.titel = titel
        self.teile: list[Baustein] = []
        self.zustand = Zustand.VORBEREITUNG
        self.zeitbasis: Zeitbasis | None = None
        #: Uhr der Einheit bei t_s = 0
        self.t0: float | None = None
        self.countdown_s = 0.0
        #: Ende der Einheit, wenn der Timer fertig ist („Dauer 15 min“, Ablauf)
        self.ende_mit_timer = False
        #: Ende der Einheit, wenn ein Plan-Ablauf durch ist (``plan/ende``)
        self.ende_mit_plan = False
        #: Ende, sobald kein Teil mehr läuft (`aktiv`) — für Einheiten aus Einzelstarts
        #: (Ben, 18.10.2026): der Timer allein endet mit ihm, eine Messung mit ihrem Stopp
        self.ende_wenn_alles_fertig = False
        #: je Teil (``"hrv"``, ``"gps"``): beim Ende stoppen? Fehlt er, gilt die Vorgabe —
        #: stoppen, was mit der Einheit begann, weiterlaufen lassen, was schon lief
        self.am_ende_stoppen: dict[str, bool] = {}
        #: alle Ereignisse in der Reihenfolge der Zeitleiste
        self.ereignisse: list[Ereignis] = []
        #: Fehler beim Vorbereiten je Teil
        self.fehler: dict[str, str] = {}
        #: Was nicht klappte, aber nichts anhält (Zeitleiste nicht geschrieben …)
        self.warnung: str | None = None
        #: Wird nach jedem Takt mit den neuen Ereignissen gerufen; Fehler stoppen nichts
        self.beobachter: Callable[[list[Ereignis]], None] | None = None
        self._beteiligungen: dict[int, Beteiligung] = {}
        self._gestartet: set[int] = set()
        self._nr = 0
        self._zurueck: dict[str, tuple[Ereignis, Projektion]] = {}
        self._schlaf: float | None = None
        self._kopf_geschrieben = False

    # -- Aufbau -------------------------------------------------------------------

    def hinzufuegen(self, teil: Baustein) -> None:
        """Einen Teil dazunehmen — nur vor dem Start, jede Art einmal."""
        if self.zustand not in (Zustand.VORBEREITUNG, Zustand.BEREIT):
            raise RuntimeError("Teile kommen vor dem Start dazu")
        if any(t.art == teil.art for t in self.teile):
            raise ValueError(f"{teil.art} ist schon dabei")
        self.teile.append(teil)
        if isinstance(teil, HrvBaustein):  # mit HRV gilt die Uhr der Quelle (Simulator!)
            self.uhr = teil.messlauf.uhr
            self.echtzeit = bool(getattr(teil.messlauf.quelle, "echtzeit", True))
        self._uhr_weitergeben()
        self.zustand = Zustand.VORBEREITUNG

    def _uhr_weitergeben(self) -> None:
        """Alle Teile auf die Uhr der Einheit — vor dem Start, solange es geht."""
        for t in self.teile:
            uebernehmen = getattr(t, "uhr_uebernehmen", None)
            if callable(uebernehmen):
                uebernehmen(self.uhr)

    def entfernen(self, art: str) -> None:
        if self.zustand not in (Zustand.VORBEREITUNG, Zustand.BEREIT):
            raise RuntimeError("Teile gehen nur vor dem Start")
        self.teile = [t for t in self.teile if t.art != art]

    def beitreten(self, teil: Baustein) -> None:
        """Ein einzeln gestarteter Teil kommt in die laufende Einheit — er beginnt jetzt, auf
        ihrer Achse: der Timer von vorn, die HRV mit einer neuen Aufnahme (läuft schon eine,
        tritt sie nur bei). Was so dazukam, hat die Einheit nicht gestartet: Eine
        HRV-Aufnahme läuft nach ihrem Ende weiter (`am_ende_stoppen`), ein Timer endet mit.

        Raises:
            RuntimeError: Die Einheit läuft nicht (vorbereitet, im Countdown, beendet).
            ValueError: Ein Teil dieser Art ist schon dabei.
        """
        if self.zustand is not Zustand.LAEUFT or self.t0 is None or self.zeitbasis is None:
            raise RuntimeError("Beitreten geht nur, solange die Einheit läuft")
        if any(t.art == teil.art for t in self.teile):
            raise ValueError(f"{teil.art} ist schon dabei")
        jetzt = self.uhr()
        t = max(jetzt - self.t0, 0.0)
        uebernehmen = getattr(teil, "uhr_uebernehmen", None)
        if callable(uebernehmen):
            uebernehmen(self.uhr)
        if isinstance(teil, HrvBaustein):
            neu = teil.messlauf.aufnahme is None
            teil.aufnahme_beginnen(jetzt, self.zeitbasis.utc(t))
            b = teil.starten(self.t0)
            if neu:
                self.am_ende_stoppen.setdefault("hrv", False)
        elif isinstance(teil, TimerBaustein):
            b = teil.starten(self.t0, bei=jetzt)
        else:
            b = teil.starten(self.t0)
        b.von_s = round(t, 3)
        self.teile.append(teil)
        self._beteiligungen[id(teil)] = b
        self._gestartet.add(id(teil))
        if self.senke is not None and self._kopf_geschrieben:
            try:
                self.senke.beteiligung(self.id, b)
            except Exception as fehler:
                self.warnung = f"Zeitleiste nicht gespeichert: {fehler}"
        daten: dict[str, Any] = {"teil": teil.art}
        if isinstance(teil, HrvBaustein):
            daten.update({"datei": b.datei, "versatz_s": b.versatz_s})
        elif isinstance(teil, TimerBaustein):
            daten["profil"] = teil.lauf.profil.name
        self._aufnehmen([Ereignis(t, teil.art, "beigetreten", "", daten)], jetzt)

    def teil(self, art: str) -> Baustein | None:
        return next((t for t in self.teile if t.art == art), None)

    @property
    def hrv(self) -> HrvBaustein | None:
        teil = self.teil("hrv")
        return teil if isinstance(teil, HrvBaustein) else None

    @property
    def timer(self) -> TimerBaustein | None:
        """Der laufende Timer — der Teil ``timer`` oder der der Übung, die ein Plan-Ablauf
        gerade führt (`devices.plan_ablauf`). Laufleiste, ⏸ und Töne folgen ihm."""
        teil = self.teil("timer")
        if isinstance(teil, TimerBaustein):
            return teil
        innen = getattr(self.teil("plan"), "timer", None)
        return innen if isinstance(innen, TimerBaustein) else None

    @property
    def bereit(self) -> bool:
        return bool(self.teile) and all(t.bereit for t in self.teile)

    @property
    def laeuft(self) -> bool:
        return self.zustand in (Zustand.COUNTDOWN, Zustand.LAEUFT)

    def dauer_s(self) -> float:
        """Sekunden seit dem Start (im Countdown negativ) — 0 vor dem Start."""
        if self.t0 is None:
            return 0.0
        return self.uhr() - self.t0

    # -- Vorbereiten und Starten -----------------------------------------------------

    async def vorbereiten(self) -> dict[str, str]:
        """Alle Teile zugleich vorbereiten — ein Fehler bleibt bei seinem Teil.

        Wer schon startete, während noch vorbereitet wurde („Trotzdem starten“),
        behält seinen Zustand — erst ein Ergebnis in der Vorbereitung macht ``BEREIT``.
        """
        teile = list(self.teile)
        ergebnisse = await asyncio.gather(*(t.vorbereiten() for t in teile), return_exceptions=True)
        self.fehler = {
            t.art: str(e) or type(e).__name__
            for t, e in zip(teile, ergebnisse, strict=True)
            if isinstance(e, BaseException)
        }
        if self.zustand is Zustand.VORBEREITUNG and self.bereit and not self.fehler:
            self.zustand = Zustand.BEREIT
        return self.fehler

    def starten(self, countdown_s: float = 0.0) -> float:
        """Alle Teile auf einen Zeitpunkt — synchron, ohne ``await`` (Vertrag §2).

        Gibt t0 zurück (Uhr der Einheit). Mit Countdown liegt t0 in der Zukunft; eine
        mitstartende HRV-Aufnahme beginnt schon jetzt (Vorlauf), die übrigen Teile
        startet der erste Takt nach t0 — mit genau diesem t0.
        """
        if self.zustand not in (Zustand.VORBEREITUNG, Zustand.BEREIT):
            raise RuntimeError("Die Einheit läuft schon")
        if not self.teile:
            raise RuntimeError("Eine Einheit ohne Teile")
        jetzt = self.uhr()
        self.countdown_s = max(countdown_s, 0.0)
        t0 = jetzt + self.countdown_s
        self.t0 = t0
        self.zeitbasis = Zeitbasis(t0, self._jetzt_utc() + timedelta(seconds=self.countdown_s))
        hrv = self.hrv
        if hrv is not None and hrv.messlauf.aufnahme is None:
            hrv.aufnahme_beginnen(jetzt, self.zeitbasis.utc(jetzt - t0))
        if self.countdown_s > 0:
            # Nur die HRV nimmt schon auf (Vorlauf); der Rest startet nach dem Countdown
            self.zustand = Zustand.COUNTDOWN
            if hrv is not None:
                self._teil_starten(hrv, t0)
            self._kopf_schreiben()
        else:
            # Erst alle Teile in einer Schleife ohne ``await``, geschrieben wird danach
            self._rest_starten(t0)
            self._kopf_schreiben()
            self._start_melden(t0)
        return t0

    def _teil_starten(self, teil: Baustein, t0: float) -> None:
        b = teil.starten(t0)
        self._beteiligungen[id(teil)] = b
        self._gestartet.add(id(teil))

    def _rest_starten(self, t0: float) -> list[Baustein]:
        """Die Teile, die noch nicht laufen — synchron, ohne zu schreiben."""
        neu = [t for t in self.teile if id(t) not in self._gestartet]
        for teil in neu:
            self._teil_starten(teil, t0)
        self.zustand = Zustand.LAEUFT
        return neu

    def _start_melden(self, t0: float) -> list[Ereignis]:
        daten: dict[str, Any] = {"countdown_s": self.countdown_s} if self.countdown_s else {}
        start = Ereignis(0.0, "einheit", "start", self.titel, daten)
        self._aufnehmen([start], t0)
        return [start]

    def _kopf_schreiben(self) -> None:
        """Kopf der Einheit und die Beteiligungen der gestarteten Teile."""
        if self.senke is None or self.zeitbasis is None:
            return
        try:
            self.senke.einheit_beginnen(
                self.id, self.subject_id, self.zeitbasis.utc(0.0), self.titel
            )
            self._kopf_geschrieben = True
            for b in self._beteiligungen.values():
                self.senke.beteiligung(self.id, b)
        except Exception as fehler:  # die Einheit läuft trotzdem
            self.warnung = f"Zeitleiste nicht gespeichert: {fehler}"

    def _beteiligungen_schreiben(self, teile: Sequence[Baustein]) -> None:
        if self.senke is None or not self._kopf_geschrieben:
            return
        try:
            for teil in teile:
                self.senke.beteiligung(self.id, self._beteiligungen[id(teil)])
        except Exception as fehler:
            self.warnung = f"Zeitleiste nicht gespeichert: {fehler}"

    # -- Takt -----------------------------------------------------------------------

    @property
    def _einheit_spur(self) -> bool:
        """Eine eigene Spur für die Einheit lohnt nur, wenn die HRV-Aufnahme schon lief."""
        hrv = self.hrv
        return hrv is not None and hrv.rolle is Rolle.LAEUFT_SCHON

    def takt(self) -> list[Ereignis]:
        """Ereignisse aller Teile seit dem letzten Takt sammeln, schreiben, projizieren."""
        if not self.laeuft or self.t0 is None:
            return []
        jetzt = self.uhr()
        neu: list[Ereignis] = []
        if self.zustand is Zustand.COUNTDOWN:
            if jetzt < self.t0:
                return []
            self._beteiligungen_schreiben(self._rest_starten(self.t0))
            neu.extend(self._start_melden(self.t0))
        gesammelt: list[Ereignis] = []
        for teil in self.teile:
            if id(teil) in self._gestartet:
                gesammelt.extend(self._sicher(teil, teil.takt, jetzt))
        gesammelt.extend(self._schlaf_pruefen(jetzt))
        gesammelt.sort(key=lambda e: e.t_s)
        gesammelt = self._mit_uebung(gesammelt)
        self._aufnehmen(gesammelt, jetzt)
        neu.extend(gesammelt)
        if neu and self.beobachter is not None:
            with contextlib.suppress(Exception):
                self.beobachter(neu)
        if self._zu_ende(neu):
            self.beenden()
        return neu

    def _zu_ende(self, neu: Sequence[Ereignis]) -> bool:
        """Endet die Einheit jetzt? Mit dem Timer bzw. dem Plan-Ablauf, wenn so eingestellt —
        aus Einzelstarts, sobald nichts mehr läuft."""
        if self.ende_mit_timer and any(e.quelle == "timer" and e.art == "ende" for e in neu):
            return True
        if self.ende_mit_plan and any(e.quelle == "plan" and e.art == "ende" for e in neu):
            return True
        return self.ende_wenn_alles_fertig and not any(self._aktiv(t) for t in self.teile)

    def _mit_uebung(self, liste: list[Ereignis]) -> list[Ereignis]:
        """Läuft eine Übung mit ihrem Timer (Uhr der Übung), nennen die Timer-Ereignisse sie
        (`core.einheit.in_uebung`, P54). Der Plan-Ablauf macht das selbst je Übung."""
        teil = self.teil("plan")
        if not isinstance(teil, UebungBaustein):
            return liste
        return [in_uebung(e, teil.kontext.uebung_id) for e in liste]

    def _aktiv(self, teil: Baustein) -> bool:
        """Läuft der Teil noch? Ohne Angabe (`aktiv`) gilt er als laufend."""
        return id(teil) in self._gestartet and bool(getattr(teil, "aktiv", True))

    def nachtragen(self, ereignis: Ereignis) -> None:
        """Ein Ereignis von außen in die Zeitleiste — etwa ``person/eintrag``, wenn eine
        Übung eines Plan-Ablaufs eingetragen wurde (fortlaufende Nummer wie alle)."""
        if self.t0 is not None:
            self._aufnehmen([ereignis], self.uhr())

    def _sicher(
        self, teil: Baustein, aufruf: Callable[[float], list[Ereignis]], jetzt: float
    ) -> list[Ereignis]:
        """Ein Fehler gehört dem Teil, nicht der Einheit: Er steht in `warnung`, der Takt
        läuft für die anderen weiter (ein kaputter Rechner hielte sonst auch die HRV an)."""
        try:
            return aufruf(jetzt)
        except Exception as fehler:
            self.warnung = f"{teil.art}: {fehler or type(fehler).__name__}"
            return []

    def _schlaf_pruefen(self, jetzt: float) -> list[Ereignis]:
        """Tiefschlaf zwischen zwei Takten wird ein Ereignis (Datenqualität)."""
        if not self.echtzeit or self.t0 is None:
            return []
        versatz = _schlafversatz()
        if versatz is None:
            return []
        alt, self._schlaf = self._schlaf, versatz
        if alt is None or versatz - alt < SCHLAF_AB_S:
            return []
        return [
            Ereignis(
                jetzt - self.t0, "einheit", "schlaf", daten={"schlaf_s": round(versatz - alt, 1)}
            )
        ]

    def _aufnehmen(self, neu: Sequence[Ereignis], jetzt: float) -> None:
        """Nummerieren, in die Zeitleiste schreiben, projizieren — auch ohne Neues prüft
        das wartende Anfangsmarken (5-s-Regel)."""
        if not neu:
            self._projizieren(neu, jetzt)
            return
        liste: list[tuple[int, Ereignis]] = []
        for e in neu:
            liste.append((self._nr, e))
            self._nr += 1
            self.ereignisse.append(e)
            if e.quelle == "hrv" and e.art == "beigetreten":
                self._beigetreten()
        if self.senke is not None and self._kopf_geschrieben:
            try:
                self.senke.ereignisse_schreiben(self.id, liste)
            except Exception as fehler:  # die Einheit läuft trotzdem
                self.warnung = f"Zeitleiste nicht gespeichert: {fehler}"
        self._projizieren(neu, jetzt)

    def _beigetreten(self) -> None:
        """Eine neue HRV-Aufnahme mitten in der Einheit: eine weitere Beteiligung."""
        hrv = self.hrv
        if hrv is None or hrv.beteiligung is None:
            return
        self._beteiligungen[id(hrv)] = hrv.beteiligung
        if self.senke is not None and self._kopf_geschrieben:
            with contextlib.suppress(Exception):
                self.senke.beteiligung(self.id, hrv.beteiligung)

    def _projizieren(self, neu: Sequence[Ereignis], jetzt: float) -> None:
        """In die HRV-Aufnahme — Anfänge warten `MIN_MARKE_S` (5-s-Regel), Enden nicht."""
        hrv = self.hrv
        if hrv is None or self.t0 is None:
            return
        t0 = self.t0
        for e in neu:
            p = projektion(e, self.id, einheit_spur=self._einheit_spur)
            if p is None:
                continue
            offen = self._zurueck.pop(p.spur, None)
            if offen is not None and e.t_s - offen[0].t_s >= MIN_MARKE_S:
                hrv.projizieren(offen[1], t0 + offen[0].t_s)
            if p.ende:
                hrv.projizieren(p, t0 + e.t_s)
            else:
                self._zurueck[p.spur] = (e, p)
        t = jetzt - t0
        for spur, (e, p) in list(self._zurueck.items()):
            if t - e.t_s >= MIN_MARKE_S:
                hrv.projizieren(p, t0 + e.t_s)
                del self._zurueck[spur]

    async def laufen(self, takt_s: float = TICK_S) -> None:
        """Takt für Takt, bis die Einheit endet — über `page.run_task` starten."""
        while self.zustand is not Zustand.BEENDET:
            self.takt()
            await asyncio.sleep(takt_s)

    # -- Ende -----------------------------------------------------------------------

    def stoppt_am_ende(self, art: str) -> bool:
        """Endet der Teil mit der Einheit? Vorgabe: was mit ihr begann."""
        if art in self.am_ende_stoppen:
            return self.am_ende_stoppen[art]
        if art == "hrv":
            hrv = self.hrv
            return hrv is not None and hrv.rolle is Rolle.MITSTARTEN
        return True

    def beenden(self) -> list[Ereignis]:
        """Alle Teile beenden — die letzten Ereignisse schreiben und projizieren (synchron)."""
        if self.zustand is Zustand.BEENDET:
            return []
        jetzt = self.uhr()
        if self.t0 is None:  # nie gestartet
            self.zustand = Zustand.BEENDET
            return []
        t = jetzt - self.t0
        gesammelt: list[Ereignis] = []
        for teil in self.teile:
            if id(teil) in self._gestartet:
                gesammelt.extend(self._sicher(teil, teil.beenden, jetzt))
        grund = "abgebrochen" if self.zustand is Zustand.COUNTDOWN else ""
        gesammelt.sort(key=lambda e: e.t_s)
        gesammelt = self._mit_uebung(gesammelt)
        ende = Ereignis(
            max(t, 0.0), "einheit", "ende", self.titel, {"grund": grund} if grund else {}
        )
        self._aufnehmen([*gesammelt, ende], jetzt)
        # Was jetzt noch wartet, lief kürzer als 5 s — keine Marke (5-s-Regel)
        self._zurueck.clear()
        self.zustand = Zustand.BEENDET
        if self.senke is not None and self._kopf_geschrieben and self.zeitbasis is not None:
            try:
                for b in self._beteiligungen.values():
                    if b.bis_s is None:
                        b.bis_s = round(max(t, 0.0), 3)
                    self.senke.beteiligung(self.id, b)
                self.senke.einheit_beenden(self.id, self.zeitbasis.utc(max(t, 0.0)))
            except Exception as fehler:
                self.warnung = f"Zeitleiste nicht abgeschlossen: {fehler}"
        if self.beobachter is not None:
            with contextlib.suppress(Exception):
                self.beobachter([*gesammelt, ende])
        return [*gesammelt, ende]

    async def abschliessen(self) -> Abschluss:
        """Nach `beenden`: Teile aufräumen, die HRV-Aufnahme speichern, wenn sie mit endet."""
        if self.zustand is not Zustand.BEENDET:
            self.beenden()
        abschluss = Abschluss()
        for teil in self.teile:
            fertig = getattr(teil, "abschliessen_async", None)
            if fertig is None:
                continue
            # Auch ein Teil, der im Countdown nie startete, gibt frei, was er hält (GPS)
            ergebnis = await fertig(self.stoppt_am_ende(teil.art))
            if id(teil) in self._gestartet:
                abschluss.teile[teil.art] = ergebnis
        hrv = self.hrv
        if hrv is not None and self.stoppt_am_ende("hrv"):
            abschluss.hrv = hrv.abschliessen()
        return abschluss


__all__ = [
    "SCHLAF_AB_S",
    "Abschluss",
    "Einheitslauf",
    "HrvBaustein",
    "TimerBaustein",
    "UebungBaustein",
    "UebungKontext",
]
