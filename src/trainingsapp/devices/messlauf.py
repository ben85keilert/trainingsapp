"""Eine laufende Messung: Quelle → Live-Fenster, während der Aufnahme auch → Aufnahme.

Der `Messlauf` lebt im `AppState`, nicht in einer Ansicht (L03): Er liest den
Datenstrom der Quelle (`HeartRateSource.stream()`) und ihren Status parallel,
füttert immer das `LiveFenster` und während einer Aufnahme zusätzlich die
`Aufnahme`, sichert alle 15 s ein Backup und meldet der Oberfläche über einen
Beobachter, dass es Neues gibt. Er rechnet nichts selbst — das tun `hrv_core`
(Aufnahme, Live-Kennzahlen) und die Quelle (Protokoll).

Kein flet-Import: Der Messlauf ist ohne Bildschirm testbar (Simulator).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from .. import __version__
from ..hrv_core.aufnahme import Aufnahme
from ..hrv_core.ausschnitte import grenzen_speichern
from ..hrv_core.constants import malik_threshold
from ..hrv_core.ereignisse import Zeitbezug, notiz
from ..hrv_core.export import diagnose_pfad, diagnose_text
from ..hrv_core.live import LiveFenster
from ..hrv_core.ppi import messluecken
from ..hrv_core.recording import Recording, messordner
from ..hrv_core.regeln import Korrekturregeln
from ..hrv_core.segments import abdeckung
from ..hrv_core.zeitachse import Kontinuitaetsuhr
from .base import DeviceStatus, HeartRateSource, Messwert, PpiPaket, Verbindung
from .profiles import GeraeteProfil, profil_fuer_namen

#: Alle so viele Sekunden schreibt die Aufnahme ein Backup (praxis_gui: 15 s).
BACKUP_S = 15.0


@dataclass(frozen=True, slots=True)
class Gespeichert:
    """Was nach „Stopp & speichern" für den Datenbankeintrag gebraucht wird."""

    pfad: Path
    recording: Recording
    sha1: str
    started_at: datetime
    dauer_s: float
    abdeckung_pct: float
    n_luecken: int


def _sha1(pfad: Path) -> str:
    return hashlib.sha1(pfad.read_bytes()).hexdigest()  # Prüfsumme, keine Sicherheitsfunktion


class Messlauf:
    """Verbindet eine Quelle mit Live-Anzeige und Aufnahme."""

    def __init__(
        self,
        quelle: HeartRateSource,
        *,
        jetzt_utc: Callable[[], datetime] = lambda: datetime.now(UTC),
        backup_basis: Path | None = None,
        regeln: Korrekturregeln | None = None,
    ) -> None:
        self.quelle = quelle
        #: Erkennungsregeln der Live-Anzeige (`regeln_setzen`)
        self.regeln = regeln or Korrekturregeln()
        # Die Uhr der Quelle — beim Simulator läuft sie ``tempo``-fach, bei echten
        # Geräten ist sie time.monotonic(). t_capture der Messwerte passt dazu.
        self._uhr: Callable[[], float] = getattr(quelle, "jetzt", time.monotonic)
        self._jetzt_utc = jetzt_utc
        self._backup_basis = backup_basis
        self.live = LiveFenster()
        # Live-x-Achse gebündelter PPI-Pakete (Verity Sense): Schlagzeiten aus der
        # Intervallsumme statt aus der streuenden Ankunft (`hrv_core.zeitachse`).
        self._ppi_uhr = Kontinuitaetsuhr()
        #: Anzeigezeiten des letzten PPI-Pakets: (rr_ms, t, verworfen, fehler_ms) in Folge
        self._schlagzeiten: deque[tuple[int, float, bool, int]] = deque()
        self.aufnahme: Aufnahme | None = None
        #: Abschnittsgrenzen des Timers in der laufenden Aufnahme: (Notiz, Name, Ende?)
        self._grenzen: list[tuple[dict, str, bool]] = []
        self.status = DeviceStatus(verbindung=Verbindung.GETRENNT)
        self.device_id = ""
        self.geraet_name = ""
        self.profil: GeraeteProfil | None = None
        self.simulation = False
        #: Nullpunkt der Live-Achse (Verbindungsbeginn), monotonic
        self.start_mono = self._uhr()
        self._letztes_backup = 0.0
        #: Wird mit ``layout=True`` gerufen, wenn sich die Verbindung ändert,
        #: sonst nach neuen Messwerten. Fehler im Beobachter stoppen nichts.
        self.beobachter: Callable[[bool], None] | None = None

    # -- Zeit ------------------------------------------------------------------

    def jetzt_s(self) -> float:
        """Sekunden seit Verbindungsbeginn — die x-Achse der Live-Kurven."""
        return self._uhr() - self.start_mono

    @property
    def verbunden(self) -> bool:
        return self.status.verbindung in (Verbindung.VERBUNDEN, Verbindung.VERBINDE)

    # -- Verbinden und Lesen ---------------------------------------------------------

    async def verbinden(self, device_id: str, name: str | None = None) -> None:
        self.device_id = device_id
        self.geraet_name = name or device_id
        self.simulation = device_id.startswith("sim:")
        self.profil = profil_fuer_namen(name or "")
        self.live.leeren()
        self.status = DeviceStatus(verbindung=Verbindung.VERBINDE, meldung="Verbinde …")
        await self.quelle.connect(device_id, name)
        # Das Profil steht erst nach dem Verbinden fest (ohne Namen: aus den
        # PMD-Features). Optische Intervalle streuen mehr — die EKG-Schwelle
        # markierte bei der Verity Sense gesunde Schläge als Artefakt.
        self.profil = self.quelle.profil or self.profil
        quelle = self.profil.intervall_quelle if self.profil else ""
        self.live = LiveFenster(malik=malik_threshold(quelle))
        self.live.regeln_setzen(self.regeln, quelle)
        self._ppi_uhr = Kontinuitaetsuhr()
        self._schlagzeiten.clear()
        self.start_mono = self._uhr()
        self.status = self.quelle.aktueller_status

    def regeln_setzen(self, regeln: Korrekturregeln) -> None:
        """Neue Erkennungsregeln — wirken sofort auf den ganzen Live-Puffer."""
        self.regeln = regeln
        self.live.regeln_setzen(regeln, self.profil.intervall_quelle if self.profil else "")

    async def laufen(self) -> None:
        """Liest, bis die Quelle endet — über `page.run_task` starten."""
        status_task = asyncio.create_task(self._status_lesen())
        try:
            async for wert in self.quelle.stream():
                if isinstance(wert, PpiPaket):
                    if self.aufnahme is not None:
                        self.aufnahme.ppi_paket(
                            wert.t_capture, wert.ppi_ms, wert.fehler_ms, wert.blocker, wert.kontakt
                        )
                    self._ppi_paket_erwarten(wert)
                    continue
                if not isinstance(wert, Messwert):
                    continue
                t_live, fehler = self._live_zeit(wert)
                self.live.hinzufuegen(
                    t_live - self.start_mono, wert.rr_ms, wert.hf_bpm, fehler_ms=fehler
                )
                self._verworfene_zeigen()
                if self.aufnahme is not None:
                    self.aufnahme.schlag(wert.rr_ms, wert.hf_bpm, wert.t_capture, wert.tw_src)
                    self._backup_wenn_faellig()
                self._melden(False)
        finally:
            status_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await status_task
            self.status = replace(self.status, verbindung=Verbindung.GETRENNT)
            self._melden(True)

    def _ppi_paket_erwarten(self, paket: PpiPaket) -> None:
        """Anzeigezeiten aller Intervalle eines PPI-Pakets vormerken.

        Die brauchbaren kommen gleich als `Messwert` hinterher und holen sich
        ihre Zeit in `_live_zeit`. Die vom Gerät verworfenen gehen direkt ins
        Live-Fenster (`_verworfene_zeigen`), jeweils an ihrer Stelle in der
        Folge — dort trennen sie die Kennzahlen und füllen die Kurve.
        """
        self._verworfene_zeigen()
        gueltig = [p > 0 for p in paket.ppi_ms]
        zeiten = iter(self._ppi_uhr.paket(paket.t_capture, paket.ppi_ms, gueltig))
        erwartet: deque[tuple[int, float, bool, int]] = deque()
        fehler_je = list(paket.fehler_ms) + [0] * (len(paket.ppi_ms) - len(paket.fehler_ms))
        for rr, blocker, fehler in zip(paket.ppi_ms, paket.blocker, fehler_je, strict=False):
            if rr <= 0:
                continue
            _, t = next(zeiten)
            erwartet.append((rr, t, bool(blocker), int(fehler)))
        self._schlagzeiten = erwartet
        self._verworfene_zeigen()

    def _verworfene_zeigen(self) -> None:
        """Verworfene Intervalle vorn in der Warteschlange ins Live-Fenster schreiben."""
        while self._schlagzeiten and self._schlagzeiten[0][2]:
            rr, t, _, fehler = self._schlagzeiten.popleft()
            self.live.hinzufuegen(t - self.start_mono, rr, 0, verworfen=True, fehler_ms=fehler)

    def _live_zeit(self, wert: Messwert) -> tuple[float, int]:
        """Anzeigezeit eines Schlags: Kontinuitätsuhr, falls er zum letzten PPI-Paket gehört.

        Die Quelle schickt das Paket vor seinen Schlägen. Passt das Intervall
        nicht zum nächsten erwarteten (fremder Schlag), gilt die Ankunft. Die
        Datei bekommt immer die Ankunftszeit (``aufnahme.schlag``). Dazu die
        Fehlerschätzung des Geräts für dieses Intervall (0 = keine).
        """
        if self._schlagzeiten:
            if self._schlagzeiten[0][0] == wert.rr_ms:
                _, t, _, fehler = self._schlagzeiten.popleft()
                return t, fehler
            self._schlagzeiten.clear()
        return wert.t_capture, 0

    async def _status_lesen(self) -> None:
        async for s in self.quelle.status():
            vorher = self.status.verbindung
            self.status = s
            if self.aufnahme is not None and s.batterie_prozent is not None:
                self.aufnahme.batterie_prozent = s.batterie_prozent
            self._melden(s.verbindung != vorher)

    def diagnose(self, **zusatz: str) -> str:
        """Kopf und Verbindungsprotokoll der Quelle als Text — zum Teilen und Ablegen.

        Leer, wenn die Quelle kein Protokoll führt (Simulator). ``zusatz`` hängt
        weitere Kopfzeilen an (z. B. die Eckdaten einer Aufnahme).
        """
        zeilen = list(getattr(self.quelle, "protokoll", []))
        if not zeilen:
            return ""
        s = self.status
        status = [s.verbindung.value]
        if s.batterie_prozent is not None:
            status.append(f"Akku {s.batterie_prozent} %")
        if s.meldung:
            status.append(s.meldung)
        kopf = {
            "App": f"Trainingsassistent {__version__}",
            "Gerät": f"{self.geraet_name} [{self.device_id}]",
            "Profil": self.profil.id if self.profil else "–",
            "Status": " · ".join(status),
            "Stand": self._jetzt_utc().astimezone().isoformat(timespec="seconds"),
            **zusatz,
        }
        return diagnose_text(kopf, zeilen)

    def _melden(self, layout: bool) -> None:
        if self.beobachter is None:
            return
        # Die Anzeige darf die Messung nie stoppen.
        with contextlib.suppress(Exception):
            self.beobachter(layout)

    # -- Aufnahme -----------------------------------------------------------------

    def aufnahme_starten(self) -> None:
        if self.aufnahme is not None:
            return
        profil = self.profil
        self.aufnahme = Aufnahme(
            geraet=self.geraet_name,
            geraet_profil=profil.id if profil else "ble_generic",
            intervall_quelle=profil.intervall_quelle if profil else "ekg_rr",
            start_mono=self._uhr(),
            start_utc=self._jetzt_utc(),
            ppi=bool(profil and profil.kann("pmd_ppi")),
            simulation=self.simulation,
        )
        self.aufnahme.batterie_prozent = self.status.batterie_prozent
        self._grenzen = []
        self._letztes_backup = self._uhr()

    def notiz_zeitbezug(self) -> Zeitbezug | None:
        """Zeitbezug der Live-Achse für Notizen — nur während einer Aufnahme.

        Die Live-Achse zählt ab Verbindungsbeginn, die Wanduhr der Aufnahme ab
        deren Start; der Unterschied ist ``wand_versatz``.
        """
        aufnahme = self.aufnahme
        if aufnahme is None:
            return None
        return Zeitbezug(
            lambda: aufnahme.beats,
            aufnahme.start_utc,
            wand_versatz=aufnahme.start_mono - self.start_mono,
        )

    def notiz_hinzufuegen(self, text: str, vor_s: float = 0.0) -> dict | None:
        """Notiz in die laufende Aufnahme, ``vor_s`` Sekunden vor jetzt — ohne Aufnahme ``None``.

        Für den Timer: Jeder Abschnittsanfang wird eine Notiz an der Stelle, an der
        er war (`core.timer.TimerLauf.neue_marken`). Verankert wie „+ Notiz" →
        „Jetzt" über die Wanduhr. Angehängt, nicht einsortiert: So verrutscht keine
        Notiz, die gerade jemand bearbeitet (das Notizfeld merkt sich den Index).
        """
        zb = self.notiz_zeitbezug()
        if zb is None or self.aufnahme is None:
            return None
        eintrag = notiz(text, zb.anker(self.jetzt_s() - max(vor_s, 0.0)), zb.start_utc)
        self.aufnahme.ereignisse.append(eintrag)
        return eintrag

    def abschnitt_markieren(
        self, text: str, vor_s: float = 0.0, *, name: str, ende: bool = False
    ) -> dict | None:
        """Wie `notiz_hinzufuegen` — und die Notiz wird beim Speichern eine Abschnittsgrenze.

        Für den Timer: Seine Abschnitte werden Abschnitte der Messung (Sidecar wie
        praxis_gui, `ausschnitte.grenzen_speichern`) — danach unabhängig von den
        Notizen verschieb- und löschbar. ``ende``: beendet nur den letzten.
        """
        eintrag = self.notiz_hinzufuegen(text, vor_s)
        if eintrag is not None:
            self._grenzen.append((eintrag, name, ende))
        return eintrag

    def aufnahme_dauer_s(self) -> float:
        return self.aufnahme.dauer_s() if self.aufnahme is not None else 0.0

    def _ordner(self, basis: Path) -> Path:
        geraeteordner = self.profil.ordner if self.profil else "Unbekannt"
        return messordner(basis, geraeteordner, simulation=self.simulation)

    def _backup_wenn_faellig(self) -> None:
        if self.aufnahme is None or self._backup_basis is None:
            return
        if self._uhr() - self._letztes_backup < BACKUP_S:
            return
        self._letztes_backup = self._uhr()
        with contextlib.suppress(OSError):
            self.aufnahme.backup(self._ordner(self._backup_basis))

    def aufnahme_stoppen(self, basis: Path) -> Gespeichert | None:
        """Speichert atomar und beendet die Aufnahme. ``None``, wenn nichts aufgezeichnet wurde."""
        aufnahme, self.aufnahme = self.aufnahme, None
        if aufnahme is None or not aufnahme.beats:
            return None
        pfad = aufnahme.speichern(self._ordner(basis))
        rec = aufnahme.recording()
        grenzen, self._grenzen = self._grenzen, []
        if grenzen:  # Abschnitte des Timers — scheitert das, bleibt die Messung
            with contextlib.suppress(OSError, ValueError):
                grenzen_speichern(pfad, rec, grenzen)
        # Das Verbindungsprotokoll gehört zur Messung: Ohne adb ist es die einzige
        # Spur, warum ein Sensor (Verity Sense) Lücken oder keine Intervalle hatte.
        text = self.diagnose(
            Aufnahme=f"{pfad.name}, {len(rec.beats)} Zeilen, {len(rec.ppi_pakete or [])} PPI-Pakete"
        )
        if text:
            with contextlib.suppress(OSError):
                diagnose_pfad(pfad).write_text(text, encoding="utf-8")
        deckung = abdeckung(rec.beats, messluecken(rec))
        return Gespeichert(
            pfad=pfad,
            recording=rec,
            sha1=_sha1(pfad),
            started_at=aufnahme.start_utc,
            dauer_s=aufnahme.dauer_s(),
            abdeckung_pct=float(deckung.get("coverage_pct", 100.0)),
            n_luecken=int(deckung.get("n_gaps", 0)),
        )

    async def trennen(self) -> None:
        await self.quelle.disconnect()
        self.status = replace(self.status, verbindung=Verbindung.GETRENNT)
