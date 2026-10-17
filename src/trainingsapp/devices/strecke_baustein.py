"""GPS als Teil einer Einheit — die Strecke ohne Oberfläche (Ben, 17.10.2026).

Der flet-freie Kern dessen, was ``ui/views/ausdauer.py`` live tut: Ortungen
annehmen, mit `core.strecke.StreckenRechner` rechnen, die Strecke schreiben lassen
und die Kilometer melden. Als `core.einheit.Baustein`:

- **Bereitstellen** (`vorbereiten`) schaltet GPS ein und nimmt Ortungen entgegen,
  ohne sie zu zählen — „bereit“ ist der Teil, sobald eine frische Ortung genauer
  als `MAX_GENAUIGKEIT_M` ist (ein kalter Empfänger braucht dafür Zeit).
- **Starten** (synchron): Ab t0 zählt jede Ortung; davor eingetroffene fallen weg.
- **Kilometer** kommen zur **Split-Zeit** (Ende des Kilometers auf der Uhr des
  Empfängers, über `UhrAbgleich` auf die Uhr der Einheit gebracht), nicht zur
  Verarbeitungszeit. Die erste gezählte Ortung beginnt „km 1“ (``gps/start``),
  jeder Split den nächsten Abschnitt (``gps/km``), das Ende schließt ihn (``gps/ende``).

**Ortsfrei:** Ereignisse tragen Kilometer, Zeiten, Split-Länge, nie eine
Koordinate (`core.einheit.daten_pruefen`). Die Ortungen gehen nur an den
``schreiber`` — die Datei unter ``Strecken/``, die nie geteilt wird.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ..core.einheit import Beteiligung, Ereignis, Rolle
from ..core.strecke import MAX_GENAUIGKEIT_M, Punkt, Split, StreckenRechner, split_laenge_m
from .gatt import UhrAbgleich
from .gps import GpsQuelle

#: Ortungstakt (s) — wie das Ausdauertraining (Ben: Sekundentakt, keine Sparstufe)
GPS_TAKT_S = 1.0
#: So alt (s) darf die letzte Ortung sein, damit der Teil als bereit gilt
FRISCH_S = 10.0


@dataclass
class StreckeErgebnis:
    """Was nach dem Ende bleibt — für Datenbankzeile und Tagebuch (UI)."""

    rechner: StreckenRechner
    sportart: str
    #: UTC der ersten und letzten gezählten Ortung (Uhr des Empfängers)
    start_utc: datetime | None
    ende_utc: datetime | None
    #: so viele Ortungen gingen an den Schreiber
    geschrieben: int


class StreckeBaustein:
    """GPS-Training als Teil einer Einheit."""

    art = "gps"

    def __init__(
        self,
        quelle: GpsQuelle,
        sportart: str,
        *,
        schreiber: Callable[[Punkt], None] | None = None,
        max_genauigkeit_m: float = MAX_GENAUIGKEIT_M,
        takt_s: float = GPS_TAKT_S,
    ) -> None:
        self.quelle = quelle
        self.sportart = sportart
        self.schreiber = schreiber
        self.max_genauigkeit_m = max_genauigkeit_m
        self.takt_s = takt_s
        self.split_m = split_laenge_m(sportart)
        self.rechner = StreckenRechner(split_m=self.split_m)
        self._abgleich = UhrAbgleich(uhr=quelle.jetzt)
        self._puffer: deque[Punkt] = deque()
        self._empfang: asyncio.Task[None] | None = None
        self._t0: float | None = None
        #: letzte Ortung (auch vor dem Start) — für „bereit“ und die Startleiste
        self.letzte: Punkt | None = None
        self._gestartet_gemeldet = False
        self._letzte_gezaehlt: tuple[float, Punkt] | None = None
        self.geschrieben = 0
        #: Was nicht klappt, aber nichts anhält (Datei voll, GPS weg)
        self.warnung: str | None = None

    # -- Zustand -----------------------------------------------------------------

    @property
    def bereit(self) -> bool:
        p = self.letzte
        if p is None or (p.genauigkeit_m is not None and p.genauigkeit_m > self.max_genauigkeit_m):
            return False
        if p.t_empfang is None:  # Wiedergabe ohne Empfangszeit
            return True
        return self.quelle.jetzt() - p.t_empfang <= FRISCH_S

    def status(self) -> str:
        if self.quelle.meldung:
            return f"GPS: {self.quelle.meldung}"
        p = self.letzte
        if p is None:
            return "sucht Empfang …"
        genau = f"{p.genauigkeit_m:.0f} m" if p.genauigkeit_m is not None else "Genauigkeit ?"
        return f"Empfang gut · {genau}" if self.bereit else f"sucht Empfang … {genau}"

    # -- Ablauf ------------------------------------------------------------------

    async def vorbereiten(self) -> None:
        """GPS einschalten — Ortungen kommen, gezählt wird erst ab dem Start."""
        if self._empfang is None:
            await self.quelle.starten(self.takt_s)
            self._empfang = asyncio.create_task(self._empfangen())

    async def _empfangen(self) -> None:
        try:
            async for punkt in self.quelle.punkte():
                self.letzte = punkt
                self._puffer.append(punkt)
        except Exception as fehler:  # steht in `warnung`, stoppt nicht still
            self.warnung = f"GPS-Empfang abgebrochen: {fehler}"

    def _uhrzeit(self, p: Punkt) -> float:
        """Zeit der Ortung auf der Uhr der Einheit (Empfängerzeit, über den Abgleich)."""
        return self._abgleich.umrechnen(p.t, jetzt=p.t_empfang)

    def _split_zeit(self, s: Split) -> float:
        offset = self._abgleich.offset or 0.0
        return s.t_ende + offset

    def starten(self, t0: float) -> Beteiligung:
        self._t0 = t0
        # Vor dem Start Eingetroffenes zählt nicht — nur für den Abgleich der Uhren
        while self._puffer and self._uhrzeit(self._puffer[0]) < t0:
            self._puffer.popleft()
        return Beteiligung("gps", Rolle.MITSTARTEN, daten={"sportart": self.sportart})

    def takt(self, jetzt: float) -> list[Ereignis]:
        if self._t0 is None:
            return []
        t0 = self._t0
        out: list[Ereignis] = []
        while self._puffer:
            p = self._puffer.popleft()
            t = self._uhrzeit(p)
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
        if self.schreiber is None:
            return
        try:
            self.schreiber(p)
            self.geschrieben += 1
        except OSError as fehler:  # Speicher voll, Datei weg — die Einheit läuft weiter
            self.schreiber = None
            self.warnung = f"Strecke wird nicht mehr gespeichert: {fehler}"

    def beenden(self, jetzt: float) -> list[Ereignis]:
        out = self.takt(jetzt)
        if self._t0 is None or not self._gestartet_gemeldet:
            return out
        t = self._letzte_gezaehlt[0] if self._letzte_gezaehlt else jetzt
        r = self.rechner
        daten = {
            "distanz_m": round(r.distanz_m, 1),
            "dauer_s": round(r.dauer_s, 1),
            "bewegt_s": round(r.bewegt_s, 1),
        }
        out.append(Ereignis(max(t, jetzt) - self._t0, "gps", "ende", "", daten))
        return out

    async def abschliessen_async(self, stoppen: bool = True) -> StreckeErgebnis:
        """GPS aus, Empfang beenden — die Strecke bleibt beim Aufrufer (Datenbank, Tagebuch)."""
        with contextlib.suppress(Exception):
            await self.quelle.beenden()
        if self._empfang is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._empfang, 5)
        r = self.rechner
        erste, letzte = r.erste, r.letzter
        return StreckeErgebnis(
            rechner=r,
            sportart=self.sportart,
            start_utc=datetime.fromtimestamp(erste.t, UTC) if erste else None,
            ende_utc=datetime.fromtimestamp(letzte.t, UTC) if letzte else None,
            geschrieben=self.geschrieben,
        )


__all__ = ["FRISCH_S", "GPS_TAKT_S", "StreckeBaustein", "StreckeErgebnis"]
