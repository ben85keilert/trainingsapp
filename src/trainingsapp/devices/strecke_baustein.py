"""Das Ausdauertraining als Teil einer Einheit — die Strecke ohne Oberfläche (Ben, 17.10.2026).

Der flet-freie Kern des Ausdauertrainings (G15): Ortungen annehmen, mit
`core.strecke.StreckenRechner` rechnen, die Strecke in die `Streckenablage` schreiben
und die Kilometer melden. Ohne Empfänger (``quelle=None``: Laufband, Halle) läuft nur
die Zeit mit — Teil ``gps`` heißt dann „Training ohne GPS“, wie eine `Strecke` ohne
Datei. Als `core.einheit.Baustein`:

- **Bereitstellen** (`vorbereiten`) schaltet GPS ein und nimmt Ortungen entgegen,
  ohne sie zu zählen — „bereit“ ist der Teil, sobald eine frische Ortung genauer
  als `MAX_GENAUIGKEIT_M` ist (ein kalter Empfänger braucht dafür Zeit).
- **Starten** (synchron): Ab t0 zählt jede Ortung; davor eingetroffene fallen weg.
  Die Datei entsteht jetzt (Kopf ohne Ort), ihr Pfad steht in der Beteiligung — so
  findet ein Nachtragen nach einem Absturz seine Einheit (H16).
- **Versatz** (`Beteiligung.versatz_s`): Zeit einer Ortung (``Punkt.t``, Uhr des
  Empfängers) + Versatz = ``t_s`` der Einheit. Damit legt die Auswertung Ortungen und
  Herzschläge aufeinander, ohne über Startzeiten in ganzen Sekunden zu gehen.
- **Kilometer** kommen zur **Split-Zeit** (Ende des Kilometers auf der Uhr des
  Empfängers, über `UhrAbgleich` auf die Uhr der Einheit gebracht), nicht zur
  Verarbeitungszeit. Die erste gezählte Ortung beginnt „km 1“ (``gps/start``),
  jeder Split den nächsten Abschnitt (``gps/km``), das Ende schließt ihn (``gps/ende``).

**Ortsfrei:** Ereignisse tragen Kilometer, Zeiten, Split-Länge, nie eine
Koordinate (`core.einheit.daten_pruefen`). Die Ortungen gehen nur an die
`Streckenablage` — die Datei unter ``Strecken/``, die nie geteilt wird.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ..core.einheit import Beteiligung, Ereignis, Rolle
from ..core.strecke import MAX_GENAUIGKEIT_M, Punkt, Split, StreckenRechner, split_laenge_m
from .gatt import UhrAbgleich
from .gps import GpsQuelle

#: Ortungstakt (s) — wie das Ausdauertraining (Ben: Sekundentakt, keine Sparstufe)
GPS_TAKT_S = 1.0
#: So alt (s) darf die letzte Ortung sein, damit der Teil als bereit gilt
FRISCH_S = 10.0


class Streckenablage(Protocol):
    """Wohin die gezählten Ortungen gehen — die Datei unter ``Strecken/``.

    ``devices`` kennt ``data`` nicht (Architekturregel); die Oberfläche reicht die
    Ablage hinein (``ui.training.Streckendatei``).
    """

    def anlegen(self, start_utc: datetime) -> str:
        """Die Datei mit Kopf (ohne Ort) anlegen — ihr Pfad relativ zu ``Strecken/``."""
        ...

    def schreiben(self, punkt: Punkt) -> None: ...

    def schliessen(self, behalten: bool) -> None:
        """Schließen; ``behalten=False`` entfernt sie (keine Ortung gezählt)."""
        ...


@dataclass
class StreckeErgebnis:
    """Was nach dem Ende bleibt — für Datenbankzeile und Tagebuch (UI)."""

    rechner: StreckenRechner
    sportart: str
    #: UTC der ersten und letzten gezählten Ortung (Uhr des Empfängers)
    start_utc: datetime | None
    ende_utc: datetime | None
    #: so viele Ortungen gingen in die Ablage
    geschrieben: int
    #: die Datei relativ zu ``Strecken/`` — leer ohne GPS oder ohne gezählte Ortung
    datei: str = ""
    #: Zeit einer Ortung (``Punkt.t``) + Versatz = ``t_s`` der Einheit
    versatz_s: float | None = None


class StreckeBaustein:
    """Ausdauertraining als Teil einer Einheit — mit GPS oder ohne (Laufband)."""

    art = "gps"

    def __init__(
        self,
        quelle: GpsQuelle | None,
        sportart: str,
        *,
        ablage: Streckenablage | None = None,
        jetzt_utc: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_genauigkeit_m: float = MAX_GENAUIGKEIT_M,
        takt_s: float = GPS_TAKT_S,
    ) -> None:
        self.quelle = quelle
        self.sportart = sportart
        self.ablage = ablage
        self._jetzt_utc = jetzt_utc
        self.max_genauigkeit_m = max_genauigkeit_m
        self.takt_s = takt_s
        self.split_m = split_laenge_m(sportart)
        self.rechner = StreckenRechner(split_m=self.split_m)
        #: Uhr der Einheit (`uhr_uebernehmen`) — allein die der Quelle
        self._uhr: Callable[[], float] = quelle.jetzt if quelle is not None else time.monotonic
        self._abgleich = UhrAbgleich(uhr=self._uhr)
        #: Ortungen mit ihrer Empfangszeit auf der Uhr der Einheit
        self._puffer: deque[tuple[Punkt, float]] = deque()
        self._empfang: asyncio.Task[None] | None = None
        self._t0: float | None = None
        #: letzte Ortung (auch vor dem Start) — für „bereit“ und die Startleiste
        self.letzte: Punkt | None = None
        self._gestartet_gemeldet = False
        self._letzte_gezaehlt: tuple[float, Punkt] | None = None
        self.geschrieben = 0
        #: Was nicht klappt, aber nichts anhält (Datei voll, GPS weg)
        self.warnung: str | None = None
        #: die Beteiligung ab dem Start — der Versatz wird am Ende nachgetragen
        self.beteiligung: Beteiligung | None = None
        #: aufgeräumt (GPS aus, Datei zu) — auch, wenn der Teil nie startete
        self.fertig = False

    # -- Zustand -----------------------------------------------------------------

    @property
    def mit_gps(self) -> bool:
        return self.quelle is not None

    @property
    def bereit(self) -> bool:
        if self.quelle is None:  # Laufband: nichts abzuwarten
            return True
        p = self.letzte
        if p is None or (p.genauigkeit_m is not None and p.genauigkeit_m > self.max_genauigkeit_m):
            return False
        if p.t_empfang is None:  # Wiedergabe ohne Empfangszeit
            return True
        return self.quelle.jetzt() - p.t_empfang <= FRISCH_S

    def status(self) -> str:
        if self.quelle is None:
            return "ohne GPS — Zeit, Herzfrequenz und HRV"
        if self.quelle.meldung:
            return f"GPS: {self.quelle.meldung}"
        p = self.letzte
        if p is None:
            return "sucht Empfang …"
        genau = f"{p.genauigkeit_m:.0f} m" if p.genauigkeit_m is not None else "Genauigkeit ?"
        return f"Empfang gut · {genau}" if self.bereit else f"sucht Empfang … {genau}"

    # -- Ablauf ------------------------------------------------------------------

    def uhr_uebernehmen(self, uhr: Callable[[], float]) -> None:
        """Die Uhr der Einheit — vor dem Start (`Einheitslauf.hinzufuegen`). Was schon
        ankam, stand auf der alten Uhr und zählt ohnehin erst ab dem Start: weg damit."""
        if uhr is self._uhr:
            return
        self._uhr = uhr
        self._abgleich = UhrAbgleich(uhr=uhr)
        self._puffer.clear()

    async def vorbereiten(self) -> None:
        """GPS einschalten — Ortungen kommen, gezählt wird erst ab dem Start."""
        if self.quelle is not None and self._empfang is None:
            await self.quelle.starten(self.takt_s)
            self._empfang = asyncio.create_task(self._empfangen())

    async def _empfangen(self) -> None:
        assert self.quelle is not None
        try:
            async for punkt in self.quelle.punkte():
                self.letzte = punkt
                self._puffer.append((punkt, self._empfangszeit(punkt)))
        except Exception as fehler:  # steht in `warnung`, stoppt nicht still
            self.warnung = f"GPS-Empfang abgebrochen: {fehler}"

    def _empfangszeit(self, p: Punkt) -> float:
        """Wann die Ortung ankam — auf der Uhr der Einheit.

        ``t_empfang`` steht auf der Uhr der Quelle (in der App ``time.monotonic``, wie
        Gurt und Einheit). Führt die Einheit eine andere — der Simulator, eine
        Wiedergabe —, rechnet der Abstand beider Uhren in diesem Augenblick um; sie
        laufen gleich schnell.
        """
        assert self.quelle is not None
        quelle_jetzt = self.quelle.jetzt()
        t = p.t_empfang if p.t_empfang is not None else quelle_jetzt
        return t + (self._uhr() - quelle_jetzt)

    def _uhrzeit(self, p: Punkt, empfang: float) -> float:
        """Zeit der Ortung auf der Uhr der Einheit (Empfängerzeit, über den Abgleich)."""
        return self._abgleich.umrechnen(p.t, jetzt=empfang)

    def _split_zeit(self, s: Split) -> float:
        offset = self._abgleich.offset or 0.0
        return s.t_ende + offset

    def _versatz(self) -> float | None:
        """Zeit einer Ortung (Empfängeruhr) + Versatz = ``t_s`` der Einheit."""
        offset = self._abgleich.offset
        if self._t0 is None or offset is None:
            return None
        return round(offset - self._t0, 6)

    @property
    def versatz_s(self) -> float | None:
        """Ortungszeit (``Punkt.t``) + Versatz = ``t_s`` der Einheit — ``None`` vor dem
        Start und vor der ersten Ortung (der Abgleich der Uhren fehlt noch). Live für die
        Tabellen „Intervalle“ und „Kilometer“ (`core.intervalle`)."""
        return self._versatz()

    def starten(self, t0: float) -> Beteiligung:
        self._t0 = t0
        # Vor dem Start Eingetroffenes zählt nicht — nur für den Abgleich der Uhren
        while self._puffer and self._uhrzeit(*self._puffer[0]) < t0:
            self._puffer.popleft()
        datei = ""
        if self.quelle is not None and self.ablage is not None:
            try:
                datei = self.ablage.anlegen(self._jetzt_utc())
            except OSError as fehler:  # die Einheit läuft trotzdem, nur ohne Datei
                self.ablage = None
                self.warnung = f"Strecke wird nicht gespeichert: {fehler}"
        daten: dict[str, object] = {"sportart": self.sportart}
        if self.quelle is not None:
            daten["split_m"] = self.split_m
        self.beteiligung = Beteiligung(
            "gps", Rolle.MITSTARTEN, datei=datei, versatz_s=self._versatz(), daten=daten
        )
        return self.beteiligung

    def takt(self, jetzt: float) -> list[Ereignis]:
        if self._t0 is None:
            return []
        t0 = self._t0
        out: list[Ereignis] = []
        while self._puffer:
            p, empfang = self._puffer.popleft()
            t = self._uhrzeit(p, empfang)
            if t < t0:
                continue
            self._schreiben(p)
            splits = self.rechner.hinzufuegen(p)
            if not self._gestartet_gemeldet and self.rechner.erste is p:
                self._gestartet_gemeldet = True
                daten = {"sportart": self.sportart, "split_m": self.split_m}
                out.append(Ereignis(t - t0, "gps", "start", "", daten))
            if self.rechner.letzter is p:
                self._letzte_gezaehlt = (t, p)
            for s in splits:
                km = round(s.nummer * self.split_m / 1000)
                daten = {
                    "km": km,
                    "split_m": self.split_m,
                    "dauer_s": round(s.t_ende - s.t_start, 1),
                    "bewegt_s": round(s.bewegt_s, 1),
                }
                out.append(Ereignis(self._split_zeit(s) - t0, "gps", "km", f"km {km}", daten))
        return out

    def _schreiben(self, p: Punkt) -> None:
        if self.ablage is None:
            return
        try:
            self.ablage.schreiben(p)
            self.geschrieben += 1
        except OSError as fehler:  # Speicher voll, Datei weg — die Einheit läuft weiter
            with contextlib.suppress(OSError):
                self.ablage.schliessen(True)  # was schon drinsteht, bleibt
            self.ablage = None
            self.warnung = f"Strecke wird nicht mehr gespeichert: {fehler}"

    def beenden(self, jetzt: float) -> list[Ereignis]:
        out = self.takt(jetzt)
        if self.beteiligung is not None:  # der Abgleich ist jetzt am genauesten
            self.beteiligung.versatz_s = self._versatz()
        if self._t0 is None or not self._gestartet_gemeldet:
            return out
        t = self._letzte_gezaehlt[0] if self._letzte_gezaehlt else jetzt
        r = self.rechner
        daten = {
            "distanz_m": round(r.distanz_m, 1),
            "dauer_s": round(r.dauer_s, 1),
            "bewegt_s": round(r.bewegt_s, 1),
        }
        out.append(Ereignis(max(t, self._t0) - self._t0, "gps", "ende", "", daten))
        return out

    async def abschliessen_async(self, stoppen: bool = True) -> StreckeErgebnis:
        """GPS aus, Empfang beenden, Datei schließen — ohne gezählte Ortung kommt sie weg.

        Auch für einen Teil, der nie startete (Startleiste geleert, Countdown
        abgebrochen): Dann gibt er nur das GPS frei. Strecke und Tagebuch trägt der
        Aufrufer ein (``ui.training``).
        """
        if self.quelle is not None:
            with contextlib.suppress(Exception):
                await self.quelle.beenden()
        if self._empfang is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._empfang, 5)
        r = self.rechner
        datei = self.beteiligung.datei if self.beteiligung is not None else ""
        if self.ablage is not None:
            behalten = bool(r.teilstuecke)  # kein Fix: keine leere Datei lassen
            with contextlib.suppress(OSError):
                self.ablage.schliessen(behalten)
            self.ablage = None
            if not behalten:
                datei = ""
        elif not r.teilstuecke:
            datei = ""
        self.fertig = True
        erste, letzte = r.erste, r.letzter
        return StreckeErgebnis(
            rechner=r,
            sportart=self.sportart,
            start_utc=datetime.fromtimestamp(erste.t, UTC) if erste else None,
            ende_utc=datetime.fromtimestamp(letzte.t, UTC) if letzte else None,
            geschrieben=self.geschrieben,
            datei=datei,
            versatz_s=self._versatz(),
        )


__all__ = ["FRISCH_S", "GPS_TAKT_S", "StreckeBaustein", "StreckeErgebnis", "Streckenablage"]
