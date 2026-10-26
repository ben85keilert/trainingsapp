"""Export: Messdateien samt Beiwerk als ZIP — Dateikopie, nicht neu gerechnet.

„Export = Dateikopie" (docs/kompatibilitaet.md, Abschnitt 2, „Export"): Die
Dateien wandern ins Archiv, mit Pfaden relativ zum Datenverzeichnis
(``Messungen/VeritySense/sensor_….json``). Ausgepackt in einen Patientenordner
liegt dann alles dort, wo praxis_gui es sucht.

Zum Beiwerk gehört das Verbindungsprotokoll (``sensor_<ts>_diagnose.txt``) —
auf dem Handy ohne adb die einzige Sicht in den Verbindungsablauf.

**Die Bluetooth-Adresse bleibt auf dem Gerät** (Ben, 20.10.2026, Sicherheitsdurchsicht
S10): Die Originaldatei trägt seit dem 19.10.2026 das Feld ``adresse`` (MAC bzw. UUID
des Sensors) — eine Gerätekennung, über die sich Messungen derselben Person
zusammenführen ließen. Jede Kopie, die das Gerät verlässt, geht durch
`exportkopie`: Die Messdatei ohne den Schlüssel ``adresse`` (sonst byteidentisch,
geschrieben wie von `hrv_core.recording`), das Diagnoseprotokoll mit maskierten
Adressen (`adresse_maskieren`). Dateien ohne Adresse bleiben byteidentisch.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path

#: Endung des Verbindungsprotokolls neben der Rohdatei
DIAGNOSE_ENDUNG = "_diagnose.txt"

#: BLE-Adresse im Fließtext: MAC (``E2:B4:CC:3F:08:44``, Android/Linux, auch mit ``-``)
#: oder Geräte-UUID (macOS/iOS) — dieselben Formen wie ``hrv_core.deid._ADRESSE``, nur
#: nicht an Zeilenanfang und -ende gebunden. Die Ränder verlangen ein Nicht-Hex-Zeichen,
#: damit Uhrzeiten (``08:15:00``) und Zeitstempel (``2026-10-13``) nie anschlagen.
ADRESSE_MUSTER = re.compile(
    r"(?<![0-9A-Fa-f:-])(?:"
    r"(?P<mac>(?:[0-9A-Fa-f]{2}[:-]){3})(?:[0-9A-Fa-f]{2}[:-]){2}[0-9A-Fa-f]{2}"
    r"|(?P<uuid>[0-9A-Fa-f]{8})-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
    r")(?![0-9A-Fa-f:-])"
)


def adresse_maskieren(text: str) -> str:
    """Alle BLE-Adressen im Text unkenntlich machen — für Kopien, die das Gerät verlassen.

    Von einer MAC bleiben die ersten drei Oktette (der Herstellerteil), von einer UUID
    die ersten acht Zeichen — genug, um ein Protokoll noch einem Gerätetyp zuzuordnen,
    zu wenig, um Messungen über eine Kennung zusammenzuführen.

    >>> adresse_maskieren("Gerät: Polar H10 [E2:B4:CC:3F:08:44]")
    'Gerät: Polar H10 [E2:B4:CC:xx:xx:xx]'
    >>> adresse_maskieren("Verbunden mit 0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0 (MTU 232)")
    'Verbunden mit 0F1E2D3C-xxxx-xxxx-xxxx-xxxxxxxxxxxx (MTU 232)'
    >>> adresse_maskieren("08:15:00 Verbunden · Stand 2026-10-13T08:15:00+02:00")
    '08:15:00 Verbunden · Stand 2026-10-13T08:15:00+02:00'
    """

    def ersetzen(treffer: re.Match[str]) -> str:
        mac = treffer.group("mac")
        if mac:
            trenner = mac[2]
            return mac + trenner.join(("xx", "xx", "xx"))
        return treffer.group("uuid") + "-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

    return ADRESSE_MUSTER.sub(ersetzen, text)


def messdatei_ohne_adresse(daten: bytes) -> bytes:
    r"""Eine JSON-Datei ohne den Schlüssel ``adresse`` auf oberster Ebene — sonst unverändert.

    Trägt die Datei keine Adresse (oder ist sie gar kein JSON-Objekt), kommen die Bytes
    unverändert zurück. Sonst wird sie genau so geschrieben wie `hrv_core.recording`
    (``ensure_ascii=False, indent=2``, kein Zeilenumbruch am Ende), sodass die Kopie bis
    auf die eine Zeile byteidentisch zur Originaldatei ist.

    >>> messdatei_ohne_adresse(b'{"geraet": "Polar H10"}')
    b'{"geraet": "Polar H10"}'
    >>> messdatei_ohne_adresse(b'{\n  "geraet": "Polar H10",\n  "adresse": "E2:B4:CC:3F:08:44"\n}')
    b'{\n  "geraet": "Polar H10"\n}'
    """
    try:
        doc = json.loads(daten)
    except ValueError:  # kein JSON (auch UnicodeDecodeError) — nichts zu entfernen
        return daten
    if not isinstance(doc, dict) or "adresse" not in doc:
        return daten
    del doc["adresse"]
    return json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")


def exportkopie(pfad: Path) -> bytes:
    """Der Inhalt einer Datei, wie er das Gerät verlassen darf.

    JSON-Dateien verlieren den Schlüssel ``adresse`` (`messdatei_ohne_adresse`), das
    Diagnoseprotokoll bekommt maskierte Adressen (`adresse_maskieren`), alles andere
    wandert byteidentisch. Die Datei auf dem Gerät bleibt unberührt.
    """
    pfad = Path(pfad)
    daten = pfad.read_bytes()
    if pfad.suffix == ".json":
        return messdatei_ohne_adresse(daten)
    if pfad.name.endswith(DIAGNOSE_ENDUNG):
        # surrogateescape: auch ein kaputtes Byte kommt unverändert wieder heraus
        text = daten.decode("utf-8", "surrogateescape")
        return adresse_maskieren(text).encode("utf-8", "surrogateescape")
    return daten


def in_zip_schreiben(archiv: zipfile.ZipFile, pfad: Path, name: str) -> None:
    """``pfad`` als ``name`` ins Archiv — über `exportkopie`, mit Zeitstempel und Rechten
    der Originaldatei (wie ``ZipFile.write``)."""
    eintrag = zipfile.ZipInfo.from_file(pfad, name)
    archiv.writestr(eintrag, exportkopie(pfad), compress_type=zipfile.ZIP_DEFLATED)


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


def export_zip(
    dateien: Iterable[Path], basis: Path, *, zusatz: Mapping[str, bytes] | None = None
) -> bytes:
    """Dateien als ZIP im Speicher, Pfade relativ zu ``basis``.

    Jede Datei kommt einmal hinein, auch wenn sie mehrfach übergeben wird. Eine
    Datei außerhalb von ``basis`` landet unter ihrem Namen auf oberster Ebene.
    Jede geht durch `exportkopie` — ohne Bluetooth-Adresse.

    ``zusatz``: erzeugte Dateien (ZIP-Pfad → Inhalt), die es auf dem Gerät so nicht gibt —
    die Rohspur eines Trainings ohne Ort (`core.bewegung`), GPX-Dateien; ein Pfad, den schon
    eine Datei belegt, bleibt der Datei.

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
            in_zip_schreiben(archiv, pfad, name)
            gepackt.add(name)
        for name, inhalt in (zusatz or {}).items():
            if name in gepackt:
                continue
            archiv.writestr(name, inhalt, compress_type=zipfile.ZIP_DEFLATED)
            gepackt.add(name)
    if not gepackt:
        raise ValueError("Keine Dateien zum Exportieren")
    return puffer.getvalue()


__all__ = [
    "ADRESSE_MUSTER",
    "DIAGNOSE_ENDUNG",
    "adresse_maskieren",
    "diagnose_pfad",
    "diagnose_text",
    "export_zip",
    "exportkopie",
    "in_zip_schreiben",
    "messdatei_ohne_adresse",
    "zugehoerige_dateien",
]
