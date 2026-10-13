"""Export: Messdateien samt Beiwerk als ZIP — byte-genau, nicht neu geschrieben.

„Export = Dateikopie" (docs/kompatibilitaet.md, Abschnitt 2, „Export"): Die
Dateien wandern unverändert ins Archiv, mit Pfaden relativ zum
Datenverzeichnis (``Messungen/VeritySense/sensor_….json``). Ausgepackt in einen
Patientenordner liegt dann alles dort, wo praxis_gui es sucht.

Zum Beiwerk gehört das Verbindungsprotokoll (``sensor_<ts>_diagnose.txt``) —
auf dem Handy ohne adb die einzige Sicht in den Verbindungsablauf.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path

#: Endung des Verbindungsprotokolls neben der Rohdatei
DIAGNOSE_ENDUNG = "_diagnose.txt"


def diagnose_pfad(rec_pfad: Path) -> Path:
    """``sensor_<ts>.json`` → ``sensor_<ts>_diagnose.txt`` (gleicher Ordner).

    >>> diagnose_pfad(Path("/m/sensor_2026-10-13_081500.json")).name
    'sensor_2026-10-13_081500_diagnose.txt'
    """
    rec_pfad = Path(rec_pfad)
    return rec_pfad.with_name(rec_pfad.stem + DIAGNOSE_ENDUNG)


def diagnose_text(kopf: Mapping[str, object], zeilen: Iterable[str]) -> str:
    """Kopf („Schlüssel: Wert") und Protokollzeilen, durch eine Leerzeile getrennt.

    >>> diagnose_text({"Gerät": "Polar Sense 1A", "Profil": "verity_sense"},
    ...               ["08:15:00 Verbunden (MTU 232)"]).splitlines()
    ['Gerät: Polar Sense 1A', 'Profil: verity_sense', '', '08:15:00 Verbunden (MTU 232)']
    """
    kopfzeilen = [f"{k}: {v}" for k, v in kopf.items()]
    return "\n".join([*kopfzeilen, "", *zeilen]) + "\n"


def zugehoerige_dateien(rec_pfad: Path) -> list[Path]:
    """Die Rohdatei und alles, was an ihrem Stamm hängt — nur vorhandene Dateien.

    Beiwerk sind ``sensor_<ts>_*`` (``_analyzed.json``, ``_ecg.json``,
    ``_ppg.json``, ``_truth.json``, ``_diagnose.txt``) und ``sensor_<ts>__c*``.
    Halbfertige ``*.tmp`` und Ordner (``analysis-v3`` von praxis_gui) bleiben
    außen vor. Die Rohdatei steht vorn, der Rest nach Namen.
    """
    rec_pfad = Path(rec_pfad)
    ordner = rec_pfad.parent
    if not ordner.is_dir():
        return []
    praefix = rec_pfad.stem + "_"
    treffer = [
        p
        for p in ordner.iterdir()
        if p.is_file()
        and not p.name.endswith(".tmp")
        and (p.name == rec_pfad.name or p.name.startswith(praefix))
    ]
    return sorted(treffer, key=lambda p: (p.name != rec_pfad.name, p.name))


def export_zip(dateien: Iterable[Path], basis: Path) -> bytes:
    """Dateien als ZIP im Speicher, Pfade relativ zu ``basis``.

    Jede Datei kommt einmal hinein, auch wenn sie mehrfach übergeben wird. Eine
    Datei außerhalb von ``basis`` landet unter ihrem Namen auf oberster Ebene.

    Raises:
        ValueError: keine einzige Datei.
    """
    wurzel = Path(basis).resolve()
    puffer = io.BytesIO()
    gepackt: set[str] = set()
    with zipfile.ZipFile(puffer, "w", compression=zipfile.ZIP_DEFLATED) as archiv:
        for pfad in dateien:
            pfad = Path(pfad).resolve()
            try:
                name = pfad.relative_to(wurzel).as_posix()
            except ValueError:
                name = pfad.name
            if name in gepackt:
                continue
            archiv.write(pfad, name)
            gepackt.add(name)
    if not gepackt:
        raise ValueError("Keine Dateien zum Exportieren")
    return puffer.getvalue()


__all__ = [
    "DIAGNOSE_ENDUNG",
    "diagnose_pfad",
    "diagnose_text",
    "export_zip",
    "zugehoerige_dateien",
]
