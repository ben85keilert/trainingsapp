"""Lesen und Schreiben des Austauschformats `raw-v1`.

Das ist der Kompatibilitätsvertrag mit `praxis_gui` in Code gegossen.
Die maßgebliche Beschreibung steht in `docs/kompatibilitaet.md` — bei
Abweichungen gilt das Dokument, und der Code ist zu korrigieren.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .constants import (
    QUALITAET_BPM_ONLY,
    QUALITAET_PPI_OPTISCH,
    QUALITAET_RR_EKG,
    QUELLE_EKG_RR,
    QUELLE_PPG_PPI,
)

SCHEMA_RAW: str = "raw-v1"

# Dateiname: sensor_<YYYY-MM-DD>_<HHMMSS>.json
DATEINAME_MUSTER = re.compile(r"^sensor_\d{4}-\d{2}-\d{2}_\d{6}\.json$")
_ZEITFORMAT_UTC = "%Y-%m-%dT%H:%M:%SZ"

# Endungen, die zwar mit `sensor_` beginnen, aber keine Messdateien sind.
_KEINE_MESSDATEI = ("_analyzed.json", "_ecg.json", "_ppg.json", "_truth.json")
_KORRIGIERT_MUSTER = re.compile(r"__c\d+$")

#: Unterordner unter ``Messungen/`` für synthetische Daten (Vertrag, Abschnitt 6).
GENERATOR_ORDNER: str = "Generator"


@dataclass(slots=True)
class Beat:
    """Ein Herzschlag, wie ihn `raw-v1` in `messungen[]` ablegt.

    Zwei Zeitachsen, das ist kein Versehen:

    - ``t_s``      Herzuhr — kumulierte gültige RR-Intervalle. Kennt keine Lücken.
    - ``t_wall_s`` Wanduhr — reale Zeit seit Aufnahmestart. Kann negativ sein.

    Die Differenz beider zeigt Verbindungslücken. Ohne ``t_wall_s`` verschwindet
    eine Lücke spurlos und ihre Ränder werden stillschweigend überbrückt.

    ``tw_src`` sagt, woher der Wanduhrwert stammt: ``"m"`` = gemessene
    Paketankunft, ``"r"`` = rückwärts rekonstruiert. Eine BLE-Notification kann
    mehrere RR-Werte enthalten; nur der letzte hat eine echte Ankunftszeit.
    Rekonstruierte Stempel dürfen **nie** als Stützstellen der Spektralanalyse
    dienen.
    """

    t_s: float
    rr_ms: int
    hf_bpm: int = 0
    t_wall_s: float | None = None
    tw_src: str = "m"

    @property
    def hat_rr(self) -> bool:
        """``rr_ms == 0`` heißt: das Paket enthielt keine RR-Intervalle."""
        return self.rr_ms > 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"t_s": round(self.t_s, 3)}
        if self.t_wall_s is not None:
            d["t_wall_s"] = round(self.t_wall_s, 3)
            d["tw_src"] = self.tw_src
        d["hf_bpm"] = int(self.hf_bpm)
        d["rr_ms"] = int(self.rr_ms)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Beat:
        # `corrected-v1` enthält kein t_wall_s — dann bleibt es None statt zu raten.
        tw = d.get("t_wall_s")
        return cls(
            t_s=float(d["t_s"]),
            rr_ms=int(d.get("rr_ms") or 0),
            hf_bpm=int(d.get("hf_bpm") or 0),
            t_wall_s=None if tw is None else float(tw),
            tw_src=str(d.get("tw_src") or "m"),
        )


@dataclass(slots=True, weakref_slot=True)
class Recording:
    """Eine Messung im Format `raw-v1`. ``weakref_slot``: `ppi._gemerkt` merkt sich
    abgeleitete Reihen je Messung, ohne sie am Leben zu halten."""

    beats: list[Beat] = field(default_factory=list)
    geraet: str = "Unbekannt"
    geraet_profil: str = "ble_generic"
    intervall_quelle: str = QUELLE_EKG_RR
    # None heißt: aus Quelle und tatsächlichem Inhalt ableiten. Eine feste
    # Vorgabe wäre gefährlich — eine Uhr ohne RR-Intervalle würde sonst als
    # `rr_ekg` in die Datei geschrieben und die Messung als hochwertig gelten.
    datenqualitaet: str | None = None
    start_utc: datetime | None = None
    patient_id: int | None = None
    behandlung_id: int | None = None
    batterie_prozent: int | None = None
    ecg_aufzeichnung: bool = False
    simulation: bool = False
    generator_config: dict[str, Any] | None = None
    titel: str = ""
    notiz: str = ""
    ereignisse: list[dict[str, Any]] = field(default_factory=list)
    # Beim Lesen: alles, was wir nicht kennen. Bleibt beim Schreiben erhalten,
    # damit ein Round-Trip keine fremden Felder verliert.
    extra: dict[str, Any] = field(default_factory=dict)
    # Lokales Datum der Messung. None heißt: aus `start_utc` ableiten. Beim Lesen
    # wird es übernommen — kurz nach Mitternacht Ortszeit weicht es vom
    # UTC-Datum ab, und ein Round-Trip darf die Messung nicht umdatieren.
    datum: str | None = None
    ppg_aufzeichnung: bool = False
    # Rohe PPI-Pakete optischer Sensoren (Vertrag, Abschnitt 3b). None heißt:
    # Gerät ohne PPI — dann fehlt der Schlüssel in der Datei, wie bei praxis_gui.
    ppi_pakete: list[dict[str, Any]] | None = None

    # -- abgeleitet ---------------------------------------------------------

    @property
    def rr_ms(self) -> list[int]:
        """Alle RR-Werte, auch implausible. Filtern macht `hrv_core.segments`."""
        return [b.rr_ms for b in self.beats]

    @property
    def dauer_s(self) -> float:
        return self.beats[-1].t_s if self.beats else 0.0

    @property
    def hat_rr(self) -> bool:
        """Ob überhaupt RR-Intervalle vorliegen — sonst ist keine HRV möglich."""
        return any(b.hat_rr for b in self.beats)

    def effektive_qualitaet(self) -> str:
        """Die Datenqualitätsstufe dieser Aufzeichnung.

        Wurde sie nicht ausdrücklich gesetzt, wird sie aus Intervallquelle und
        tatsächlichem Inhalt abgeleitet. Enthält die Messung keinen einzigen
        RR-Wert, ist sie ``bpm_only`` — unabhängig davon, was das Geräteprofil
        versprochen hat.
        """
        if self.datenqualitaet is not None:
            return self.datenqualitaet
        return _qualitaet_raten(self.intervall_quelle, self.beats)

    def dateiname(self) -> str:
        ts = (self.start_utc or datetime.now(UTC)).strftime("%Y-%m-%d_%H%M%S")
        return f"sensor_{ts}.json"

    # -- Serialisierung -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Erzeugt das `raw-v1`-Dokument.

        Feldreihenfolge wie im Schreiber von praxis_gui (`_save_recording`);
        unsere Erweiterung `datenqualitaet` steht hinter `intervall_quelle`,
        `ppi_pakete` nur bei Geräten mit PPI vor `titel`. Bewusst **ohne**
        `hrv`- und `quality`-Block: Rohdatei bleibt Rohdatei, die Nachberechnung
        setzt `analyzed` und legt das Sidecar an.

        >>> doc = Recording(geraet="Polar H10").to_dict()
        >>> list(doc)[4:7]
        ['geraet_profil', 'intervall_quelle', 'datenqualitaet']
        >>> list(doc)[-6:]
        ['ecg_aufzeichnung', 'ppg_aufzeichnung', 'titel', 'notiz', 'ereignisse', 'messungen']
        >>> "ppi_pakete" in doc
        False
        """
        start = self.start_utc or datetime.now(UTC)
        doc: dict[str, Any] = {
            "behandlung_id": self.behandlung_id,
            "patient_id": self.patient_id,
            "datum": self.datum or start.strftime("%Y-%m-%d"),
            "geraet": self.geraet,
            "geraet_profil": self.geraet_profil,
            "intervall_quelle": self.intervall_quelle,
            "datenqualitaet": self.effektive_qualitaet(),
            "simulation": bool(self.simulation),
            "generator_config": self.generator_config,
            "schema": SCHEMA_RAW,
            "analyzed": False,
            "start_utc": start.strftime(_ZEITFORMAT_UTC),
            "batterie_prozent": self.batterie_prozent,
            "ecg_aufzeichnung": bool(self.ecg_aufzeichnung),
            "ppg_aufzeichnung": bool(self.ppg_aufzeichnung),
        }
        if self.ppi_pakete is not None:
            doc["ppi_pakete"] = self.ppi_pakete
        doc["titel"] = self.titel
        doc["notiz"] = self.notiz
        doc["ereignisse"] = self.ereignisse
        doc["messungen"] = [b.to_dict() for b in self.beats]
        # Unbekannte Felder aus einer gelesenen Datei erhalten, aber nie
        # bekannte überschreiben.
        for k, v in self.extra.items():
            doc.setdefault(k, v)
        return doc

    @classmethod
    def from_dict(cls, doc: dict[str, Any]) -> Recording:
        """Liest `raw-v1` — und ältere Dateien, die vieles davon nicht haben.

        Defensiv, weil Altdateien weder `schema` noch `intervall_quelle` noch
        `geraet_profil` enthalten (siehe docs/kompatibilitaet.md, Abschnitt 7).
        """
        bekannt = {
            "behandlung_id",
            "patient_id",
            "datum",
            "geraet",
            "geraet_profil",
            "intervall_quelle",
            "datenqualitaet",
            "simulation",
            "generator_config",
            "schema",
            "analyzed",
            "start_utc",
            "batterie_prozent",
            "ecg_aufzeichnung",
            "ppg_aufzeichnung",
            "ppi_pakete",
            "titel",
            "notiz",
            "ereignisse",
            "messungen",
        }
        quelle = str(doc.get("intervall_quelle") or QUELLE_EKG_RR)
        beats = [Beat.from_dict(m) for m in (doc.get("messungen") or [])]

        start_raw = doc.get("start_utc")
        start: datetime | None = None
        if start_raw:
            try:
                start = datetime.strptime(str(start_raw), _ZEITFORMAT_UTC).replace(tzinfo=UTC)
            except ValueError:
                start = None

        return cls(
            beats=beats,
            geraet=str(doc.get("geraet") or "Unbekannt"),
            geraet_profil=str(doc.get("geraet_profil") or "ble_generic"),
            intervall_quelle=quelle,
            datenqualitaet=(str(d) if (d := doc.get("datenqualitaet")) else None),
            start_utc=start,
            patient_id=doc.get("patient_id"),
            behandlung_id=doc.get("behandlung_id"),
            batterie_prozent=doc.get("batterie_prozent"),
            ecg_aufzeichnung=bool(doc.get("ecg_aufzeichnung")),
            simulation=bool(doc.get("simulation")),
            generator_config=doc.get("generator_config"),
            titel=str(doc.get("titel") or ""),
            notiz=str(doc.get("notiz") or ""),
            ereignisse=list(doc.get("ereignisse") or []),
            extra={k: v for k, v in doc.items() if k not in bekannt},
            datum=(str(d) if (d := doc.get("datum")) else None),
            ppg_aufzeichnung=bool(doc.get("ppg_aufzeichnung")),
            ppi_pakete=(list(pp) if isinstance(pp := doc.get("ppi_pakete"), list) else None),
        )


def _qualitaet_raten(intervall_quelle: str, beats: list[Beat]) -> str:
    """Datenqualitätsstufe für Dateien, die das Feld nicht mitbringen."""
    if not any(b.hat_rr for b in beats):
        return QUALITAET_BPM_ONLY
    return QUALITAET_PPI_OPTISCH if intervall_quelle == QUELLE_PPG_PPI else QUALITAET_RR_EKG


# ---------------------------------------------------------------------------
# Dateizugriff
# ---------------------------------------------------------------------------


def ist_messdatei(pfad: Path | str) -> bool:
    """Ob diese Datei eine Rohmessung ist.

    Der Name entscheidet: `sensor_*.json`, aber keine Analyse-, EKG-, PPG-,
    Wahrheits- oder Korrekturdatei. Crash-Backups (`.backup_*`) und
    Zwischenstände (`*.tmp`) fallen schon durch Präfix bzw. Endung heraus.
    Vertrag: docs/kompatibilitaet.md, Abschnitt 2.

    >>> ist_messdatei("sensor_2026-05-23_125422.json")
    True
    >>> ist_messdatei("sensor_2026-05-23_125422_ppg.json")
    False
    >>> ist_messdatei(".backup_2026-05-23_125422.json")
    False
    """
    name = Path(pfad).name
    if not name.startswith("sensor_") or not name.endswith(".json"):
        return False
    if any(name.endswith(s) for s in _KEINE_MESSDATEI):
        return False
    return not _KORRIGIERT_MUSTER.search(Path(name).stem)


def laden(pfad: Path | str) -> Recording:
    """Liest eine Messdatei."""
    with open(pfad, encoding="utf-8") as f:
        return Recording.from_dict(json.load(f))


def json_atomar_schreiben(pfad: Path | str, doc: Any, *, kompakt: bool = False) -> Path:
    """Schreibt JSON so, dass nie eine halbe Datei entsteht.

    Erst ``<pfad>.tmp`` vollständig schreiben und auf den Datenträger zwingen,
    dann mit `os.replace` an die Zielstelle tauschen — das ist auf allen
    Plattformen ein atomarer Schritt. Bricht das Schreiben ab, bleibt die alte
    Datei unverändert und der Zwischenstand wird entfernt.

    Args:
        kompakt: ohne Einrückung (für das 15-s-Backup, das bei langen Messungen
            sonst unnötig groß wird).
    """
    ziel = Path(pfad)
    tmp = ziel.with_name(ziel.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            if kompakt:
                json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
            else:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ziel)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return ziel


def messordner(basis: Path | str, geraeteordner: str, *, simulation: bool = False) -> Path:
    """Zielordner einer Messung: ``<basis>/Messungen/<Geräteordner>``.

    Simulationen landen zwingend unter ``Generator`` — sonst könnte Synthetik
    unbemerkt zwischen echten Messungen auftauchen.

    >>> messordner("/daten", "PolarH10").as_posix()
    '/daten/Messungen/PolarH10'
    >>> messordner("/daten", "PolarH10", simulation=True).as_posix()
    '/daten/Messungen/Generator'
    """
    return Path(basis) / "Messungen" / (GENERATOR_ORDNER if simulation else geraeteordner)


def speichern(rec: Recording, ordner: Path | str, dateiname: str | None = None) -> Path:
    """Schreibt eine Messung atomar als `raw-v1` und liefert den Pfad zurück.

    Den Ordner bestimmt der Aufrufer — für Simulationen `messordner(...,
    simulation=True)`, sonst könnte Synthetik in einer Patientenakte landen.
    """
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    return json_atomar_schreiben(ordner / (dateiname or rec.dateiname()), rec.to_dict())


__all__ = [
    "GENERATOR_ORDNER",
    "SCHEMA_RAW",
    "Beat",
    "Recording",
    "ist_messdatei",
    "json_atomar_schreiben",
    "laden",
    "messordner",
    "speichern",
]
