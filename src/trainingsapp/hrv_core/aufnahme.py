"""Eine laufende Aufnahme: aus Einzelschlägen wird eine `raw-v1`-Datei.

Hier stehen die Schreibregeln, die praxis_gui beim Aufzeichnen anwendet
(`widget.py`, `_on_hr_received`) — als eigene Klasse, damit sie ohne Gerät und
ohne Oberfläche prüfbar sind. Vertrag: docs/kompatibilitaet.md, Abschnitt 3a/3b
und 6a.

Was die Klasse **nicht** tut: Bluetooth-Pakete zerlegen. Die Geräteschicht
liefert schon Einzelschläge mit Empfangszeit (``t_capture``) und Herkunft
(``tw_src``). Sie arbeitet nur mit Primitiven, damit `hrv_core` nichts aus
`devices` importieren muss.

Ablauf::

    aufnahme = Aufnahme(geraet="Polar H10 A1B2", geraet_profil="polar_h10",
                        intervall_quelle="ekg_rr", start_mono=time.monotonic(),
                        start_utc=datetime.now(UTC))
    aufnahme.schlag(rr_ms=812, hf_bpm=74, t_capture=..., tw_src="m")
    aufnahme.backup(ordner)          # alle 15 s
    aufnahme.speichern(ordner)       # beim Stopp — löscht das Backup
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .constants import AUFNAHME_RR_MAX_MS, AUFNAHME_RR_MIN_MS
from .recording import Beat, Recording, json_atomar_schreiben

_TW_SRC = ("m", "r", "g")


class Aufnahme:
    """Sammelt die Schläge einer Aufnahme und schreibt sie als `raw-v1`.

    Args:
        geraet: Anzeigename, i. d. R. der BLE-Gerätename.
        geraet_profil: Profil-ID (``polar_h10``, ``verity_sense`` …).
        intervall_quelle: ``ekg_rr`` oder ``ppg_ppi``.
        start_mono: Nullpunkt der Wanduhr — derselbe Uhrtyp wie ``t_capture``
            (``time.monotonic()``), nie ``datetime.now()``.
        start_utc: Aufnahmestart als Datum/Uhrzeit (Kopf und Dateiname).
        ppi: Gerät liefert PPI-Pakete (Verity Sense) — dann trägt die Datei
            ``ppi_pakete``, auch wenn keines ankam.
        simulation: synthetische Daten. Die Datei bekommt ``simulation: true``;
            den Ordner ``Messungen/Generator`` wählt der Aufrufer
            (`recording.messordner`).

    Öffentliche Attribute, die der Aufrufer während der Aufnahme setzen darf:
    ``titel``, ``notiz``, ``batterie_prozent``, ``patient_id``,
    ``behandlung_id``.

    >>> from datetime import UTC, datetime
    >>> a = Aufnahme(geraet="H10", geraet_profil="polar_h10", intervall_quelle="ekg_rr",
    ...              start_mono=100.0, start_utc=datetime(2026, 10, 12, 8, 0, tzinfo=UTC))
    >>> a.schlag(800, 75, 100.8, "m").t_s
    0.8
    >>> a.schlag(0, 75, 101.8, "m").t_s          # Paket ohne RR: Herzuhr steht
    0.8
    >>> a.schlag(2400, 75, 104.2, "m").t_s       # implausibel: Zeile ja, Herzuhr nein
    0.8
    >>> [b.rr_ms for b in a.beats]
    [800, 0, 2400]
    """

    def __init__(
        self,
        *,
        geraet: str,
        geraet_profil: str,
        intervall_quelle: str,
        start_mono: float,
        start_utc: datetime,
        ppi: bool = False,
        simulation: bool = False,
    ) -> None:
        if start_utc.tzinfo is None:
            raise ValueError("start_utc braucht eine Zeitzone (UTC)")
        self.geraet = geraet
        self.geraet_profil = geraet_profil
        self.intervall_quelle = intervall_quelle
        self.start_mono = float(start_mono)
        self.start_utc = start_utc.astimezone(UTC)
        self.simulation = bool(simulation)
        self.titel = ""
        self.notiz = ""
        self.batterie_prozent: int | None = None
        self.patient_id: int | None = None
        self.behandlung_id: int | None = None
        # Lokales Datum wie bei praxis_gui (`datetime.now()`), nicht das UTC-Datum.
        self.datum = self.start_utc.astimezone().strftime("%Y-%m-%d")

        self._ppi = bool(ppi)
        self._beats: list[Beat] = []
        self._ppi_pakete: list[dict[str, Any]] = []
        self._herz_ms = 0  # ganze Millisekunden, wie praxis_gui
        self._backup_pfade: set[Path] = set()

    # -- Erfassen -----------------------------------------------------------

    def schlag(self, rr_ms: int, hf_bpm: int, t_capture: float, tw_src: str) -> Beat:
        """Hängt einen Schlag an und liefert die geschriebene Zeile.

        Die Zeile wird **immer** angehängt, mit dem Rohwert — auch ``rr_ms = 0``
        (Paket ohne RR) und implausible Werte. Die Herzuhr ``t_s`` wächst nur
        bei ``300 ≤ rr_ms ≤ 2000``; ``t_wall_s = round(t_capture − start_mono, 3)``.
        """
        if tw_src not in _TW_SRC:
            raise ValueError(f"tw_src muss eines von {_TW_SRC} sein, nicht {tw_src!r}")
        rr = int(rr_ms)
        if AUFNAHME_RR_MIN_MS <= rr <= AUFNAHME_RR_MAX_MS:
            self._herz_ms += rr
        beat = Beat(
            t_s=round(self._herz_ms / 1000.0, 3),
            rr_ms=rr,
            hf_bpm=int(hf_bpm),
            t_wall_s=round(float(t_capture) - self.start_mono, 3),
            tw_src=tw_src,
        )
        self._beats.append(beat)
        return beat

    def ppi_paket(
        self,
        t_capture: float,
        ppi_ms: Iterable[int],
        fehler_ms: Iterable[int],
        blocker: Iterable[int | bool],
        kontakt: Iterable[int | bool],
    ) -> None:
        """Ein PPI-Paket roh mitschreiben (Vertrag, Abschnitt 3b).

        Kommt ein Paket an, obwohl die Aufnahme ohne ``ppi=True`` angelegt
        wurde, schaltet sie auf PPI um — Rohdaten zu verwerfen wäre schlimmer
        als ein unerwarteter Schlüssel.
        """
        spalten = {
            "ppi_ms": [int(x) for x in ppi_ms],
            "fehler_ms": [int(x) for x in fehler_ms],
            "blocker": [1 if x else 0 for x in blocker],
            "kontakt": [1 if x else 0 for x in kontakt],
        }
        laengen = {len(v) for v in spalten.values()}
        if len(laengen) != 1:
            raise ValueError(f"PPI-Spalten unterschiedlich lang: {laengen}")
        self._ppi = True
        self._ppi_pakete.append(
            {"t_wall_s": round(float(t_capture) - self.start_mono, 3), **spalten}
        )

    # -- Abfragen -----------------------------------------------------------

    @property
    def beats(self) -> list[Beat]:
        """Die bisher geschriebenen Zeilen (Kopie)."""
        return list(self._beats)

    @property
    def ppi(self) -> bool:
        return self._ppi

    def dauer_s(self) -> float:
        """Wanduhrzeit vom Start bis zum letzten Schlag."""
        if not self._beats or self._beats[-1].t_wall_s is None:
            return 0.0
        return max(0.0, float(self._beats[-1].t_wall_s))

    def recording(self, *, titel: str = "", notiz: str = "") -> Recording:
        """Der aktuelle Stand als `Recording` (für Backup, Speichern, Anzeige).

        Ohne Argument gelten die Attribute ``titel``/``notiz``.
        """
        return Recording(
            beats=list(self._beats),
            geraet=self.geraet,
            geraet_profil=self.geraet_profil,
            intervall_quelle=self.intervall_quelle,
            start_utc=self.start_utc,
            patient_id=self.patient_id,
            behandlung_id=self.behandlung_id,
            batterie_prozent=self.batterie_prozent,
            simulation=self.simulation,
            titel=titel or self.titel,
            notiz=notiz or self.notiz,
            datum=self.datum,
            ppg_aufzeichnung=False,
            ppi_pakete=[dict(p) for p in self._ppi_pakete] if self._ppi else None,
        )

    # -- Schreiben ----------------------------------------------------------

    def backup_name(self) -> str:
        """``.backup_<UTC-Start>.json`` — wie praxis_gui (`_start_backup`)."""
        return f".backup_{self.start_utc.strftime('%Y-%m-%d_%H%M%S')}.json"

    def backup(self, ordner: Path) -> Path:
        """Crash-Sicherung, atomar und kompakt (Vertrag, Abschnitt 6a).

        Gedacht für einen 15-s-Takt. Der Punkt am Anfang hält die Datei aus
        jeder Messungsliste heraus.
        """
        ordner = Path(ordner)
        ordner.mkdir(parents=True, exist_ok=True)
        pfad = json_atomar_schreiben(
            ordner / self.backup_name(), self.recording().to_dict(), kompakt=True
        )
        self._backup_pfade.add(pfad)
        return pfad

    def speichern(self, ordner: Path) -> Path:
        """Schreibt die Messdatei atomar und löscht danach das Backup.

        Raises:
            ValueError: Es wurde kein einziger Schlag aufgezeichnet — wie
                praxis_gui („Keine Daten zum Speichern") entsteht dann keine Datei.
        """
        if not self._beats:
            raise ValueError("Keine Daten zum Speichern")
        ordner = Path(ordner)
        ordner.mkdir(parents=True, exist_ok=True)
        rec = self.recording()
        pfad = json_atomar_schreiben(ordner / rec.dateiname(), rec.to_dict())
        # Erst nach erfolgreichem Schreiben aufräumen — sonst ginge bei einem
        # Fehler die einzige Kopie verloren.
        for alt in {*self._backup_pfade, ordner / self.backup_name()}:
            alt.unlink(missing_ok=True)
        self._backup_pfade.clear()
        return pfad


__all__ = ["Aufnahme"]
