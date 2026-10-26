"""Strecken speichern — eigener Ordner, nie bei den Messungen.

- **Während der Aufzeichnung** eine Zeile JSON je Ortung (``.jsonl``): Jede
  Zeile ist sofort geschrieben, ein Absturz kostet höchstens die letzte. Die
  erste Zeile ist seit 15.10.2026 ein **Kopf** (``{"kopf": {…}}``: Schema,
  Sportart, Profil-ID, Startzeit — keine Koordinate), damit ein Training, das
  Android mitten im Lauf beendet hat, beim nächsten Start nachgetragen werden
  kann (`verwaiste`). Dateien ohne Kopf bleiben lesbar.
- **Export auf ausdrücklichen Wunsch** als GPX 1.1 — das Austauschformat, das
  Strava, Komoot, Garmin Connect, OsmAnd und Google Earth lesen. Die
  Herzfrequenz steht, wenn vorhanden, in Garmins ``TrackPointExtension`` —
  so lesen sie Strava und Co.

**GPS-Daten werden nie geteilt** (`docs/plan_gps.md`, Abschnitt 0): Strecken
liegen in `config.streckenverzeichnis()`, nicht in ``Messungen/`` (das liest
und synchronisiert praxis_gui, und der Messungs-Export packt alles mit dem
Präfix der Messung ein). Einzige Ausnahme ist der GPX-Export, den die Person
selbst auslöst (Ben, 14.10.2026).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, fields
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import IO, Final
from xml.sax.saxutils import escape, quoteattr

from trainingsapp.core.bewegung import ENTFERNT
from trainingsapp.core.strecke import Punkt, abstand_m

#: Namen in der GPX-Datei (``<type>``) — frei wählbar, das lesen die meisten Dienste
GPX_SPORTART: Final[dict[str, str]] = {
    "gehen": "walking",
    "laufen": "running",
    "rad": "cycling",
}

_FELDER: Final[frozenset[str]] = frozenset(f.name for f in fields(Punkt))


class StreckenSchreiber:
    """Hängt Ortungen zeilenweise an eine ``.jsonl``-Datei an.

    >>> import tempfile
    >>> ordner = tempfile.TemporaryDirectory()
    >>> pfad = Path(ordner.name) / "s.jsonl"
    >>> with StreckenSchreiber(pfad) as s:
    ...     s.schreiben(Punkt(1.5, 52.1, 13.2, genauigkeit_m=4.0))
    >>> jsonl_lesen(pfad) == [Punkt(1.5, 52.1, 13.2, genauigkeit_m=4.0)]
    True
    >>> ordner.cleanup()
    """

    def __init__(self, pfad: Path, kopf: Mapping[str, object] | None = None) -> None:
        self.pfad = pfad
        pfad.parent.mkdir(parents=True, exist_ok=True)
        neu = not pfad.exists() or pfad.stat().st_size == 0
        self._datei: IO[str] | None = pfad.open("a", encoding="utf-8")
        if kopf is not None and neu:
            self._datei.write(json.dumps({"kopf": dict(kopf)}, separators=(",", ":")) + "\n")
            self._datei.flush()

    def schreiben(self, punkt: Punkt) -> None:
        if self._datei is None:
            return
        werte = {k: v for k, v in asdict(punkt).items() if v is not None and v is not False}
        self._datei.write(json.dumps(werte, separators=(",", ":")) + "\n")
        self._datei.flush()

    def schliessen(self) -> None:
        if self._datei is not None:
            self._datei.close()
            self._datei = None

    def __enter__(self) -> StreckenSchreiber:
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None,
        fehler: BaseException | None,
        spur: TracebackType | None,
    ) -> None:
        self.schliessen()


def dateiname(start: datetime) -> str:
    """Name der Datei eines Trainings — wie die Messdateien nach der Startzeit (lokal).

    >>> dateiname(datetime(2026, 10, 18, 9, 5, 7, tzinfo=UTC)).startswith("strecke_2026-10-18_")
    True
    """
    return f"strecke_{start.astimezone():%Y-%m-%d_%H%M%S}.jsonl"


def jsonl_lesen(pfad: Path) -> list[Punkt]:
    """Alle Ortungen einer ``.jsonl``-Datei; Kopfzeile, eine abgebrochene letzte Zeile
    und Zeilen ohne ``lat``/``lon`` fallen weg."""
    punkte: list[Punkt] = []
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        try:
            werte = json.loads(zeile)
        except json.JSONDecodeError:
            continue  # Absturz mitten im Schreiben
        if not isinstance(werte, Mapping) or "kopf" in werte:
            continue
        try:
            punkte.append(Punkt(**{k: v for k, v in werte.items() if k in _FELDER}))
        except TypeError:
            continue  # von Hand bearbeitet, Pflichtfeld fehlt
    return punkte


def kopf_lesen(pfad: Path) -> dict[str, object] | None:
    """Der Kopf einer Streckendatei (erste Zeile) — ``None`` bei Dateien von vor dem Kopf.

    >>> import tempfile
    >>> ordner = tempfile.TemporaryDirectory()
    >>> pfad = Path(ordner.name) / "s.jsonl"
    >>> with StreckenSchreiber(pfad, kopf={"sportart": "gehen"}) as s:
    ...     s.schreiben(Punkt(1.5, 52.1, 13.2))
    >>> kopf_lesen(pfad), len(jsonl_lesen(pfad))
    ({'sportart': 'gehen'}, 1)
    >>> ordner.cleanup()
    """
    try:
        with pfad.open(encoding="utf-8") as f:
            erste = f.readline()
        werte = json.loads(erste)
    except (OSError, json.JSONDecodeError):
        return None
    kopf = werte.get("kopf") if isinstance(werte, Mapping) else None
    return dict(kopf) if isinstance(kopf, Mapping) else None


def verwaiste(verzeichnis: Path, bekannte: set[str]) -> list[Path]:
    """Streckendateien ohne Eintrag in der Tabelle ``strecke`` — ein Training, das Android
    mitten im Lauf beendet hat (die Zeile entsteht erst beim Stoppen). ``bekannte``:
    die ``file_path``-Werte aller Zeilen, auch gelöschter. Vorabtest-Dateien zählen nicht."""
    if not verzeichnis.is_dir():
        return []
    return sorted(
        p
        for p in verzeichnis.glob("strecke_*.jsonl")
        if p.relative_to(verzeichnis).as_posix() not in bekannte
    )


def gpx(
    punkte: Iterable[Punkt],
    *,
    name: str,
    sportart: str | None = None,
    herzfrequenz: Mapping[float, int] | None = None,
) -> bytes:
    """GPX 1.1 mit einer Spur. ``herzfrequenz``: GPS-Zeit ``t`` → Schläge/min.

    >>> text = gpx([Punkt(0.0, 52.5, 13.4, hoehe_m=40.0)], name="Gehen & mehr",
    ...            sportart="gehen", herzfrequenz={0.0: 92}).decode()
    >>> "<type>walking</type>" in text, "<gpxtpx:hr>92</gpxtpx:hr>" in text
    (True, True)
    >>> '<trkpt lat="52.5000000" lon="13.4000000"><ele>40.0</ele>' in text
    True
    >>> "Gehen &amp; mehr" in text
    True
    """
    jetzt = _zeit(datetime.now(UTC).timestamp())
    kopf = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="Trainingsassistent"'
        ' xmlns="http://www.topografix.com/GPX/1/1"'
        ' xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xsi:schemaLocation="http://www.topografix.com/GPX/1/1'
        ' http://www.topografix.com/GPX/1/1/gpx.xsd">',
        f"<metadata><name>{escape(name)}</name><time>{jetzt}</time></metadata>",
        f"<trk><name>{escape(name)}</name>",
    ]
    if sportart:
        kopf.append(f"<type>{escape(GPX_SPORTART.get(sportart, sportart))}</type>")
    kopf.append("<trkseg>")
    zeilen = list(kopf)
    hf = herzfrequenz or {}
    for p in punkte:
        teile = [f"<trkpt lat={quoteattr(f'{p.lat:.7f}')} lon={quoteattr(f'{p.lon:.7f}')}>"]
        if p.hoehe_m is not None:
            teile.append(f"<ele>{p.hoehe_m:.1f}</ele>")
        teile.append(f"<time>{_zeit(p.t)}</time>")
        if p.t in hf:
            teile.append(
                "<extensions><gpxtpx:TrackPointExtension>"
                f"<gpxtpx:hr>{int(hf[p.t])}</gpxtpx:hr>"
                "</gpxtpx:TrackPointExtension></extensions>"
            )
        teile.append("</trkpt>")
        zeilen.append("".join(teile))
    zeilen += ["</trkseg></trk>", "</gpx>", ""]
    return "\n".join(zeilen).encode("utf-8")


def spur_ohne_ort(pfad: Path, kopf: Mapping[str, object]) -> bytes:
    """Die Streckendatei als **Rohspur ohne Ort** (``spur-ohne-ort-v1``, `core.bewegung`).

    Dieselben Zeilen wie die Datei — ohne Breite, Länge und Richtung (`ENTFERNT`), dafür
    mit ``ds_m``, dem Abstand zum vorigen Fix (`abstand_m`, ungefiltert, jede Ortung).
    Die erste Zeile ist der neue Kopf, Kopf und kaputte Zeilen der Quelle fallen weg wie
    beim Lesen. Eine Dateikopie, keine Rechnung — der Leser filtert und glättet selbst.

    >>> import tempfile
    >>> ordner = tempfile.TemporaryDirectory()
    >>> pfad = Path(ordner.name) / "s.jsonl"
    >>> with StreckenSchreiber(pfad, kopf={"schema": "strecke-v1"}) as s:
    ...     s.schreiben(Punkt(1.0, 52.0, 13.0, genauigkeit_m=4.0, hoehe_m=40.0,
    ...                       tempo_ms=2.5, richtung_grad=90.0))
    ...     s.schreiben(Punkt(2.0, 52.0, 13.00004, genauigkeit_m=4.0, hoehe_m=40.5))
    >>> zeilen = spur_ohne_ort(pfad, {"schema": "spur-ohne-ort-v1"}).decode().splitlines()
    >>> zeilen[0]
    '{"kopf":{"schema":"spur-ohne-ort-v1"}}'
    >>> zeilen[1]
    '{"t":1.0,"genauigkeit_m":4.0,"hoehe_m":40.0,"tempo_ms":2.5}'
    >>> zeilen[2]
    '{"t":2.0,"ds_m":2.738,"genauigkeit_m":4.0,"hoehe_m":40.5}'
    >>> ordner.cleanup()
    """
    aus = [json.dumps({"kopf": dict(kopf)}, ensure_ascii=False, separators=(",", ":"))]
    vorher: Punkt | None = None
    for p in jsonl_lesen(pfad):
        werte: dict[str, object] = {"t": p.t}
        if vorher is not None:
            werte["ds_m"] = round(abstand_m(vorher, p), 3)
        for k, v in asdict(p).items():
            if k != "t" and k not in ENTFERNT and v is not None and v is not False:
                werte[k] = v
        aus.append(json.dumps(werte, separators=(",", ":")))
        vorher = p
    return ("\n".join(aus) + "\n").encode("utf-8")


def _zeit(t: float) -> str:
    """UTC mit Millisekunden: ``2026-10-14T13:02:01.250Z``.

    >>> _zeit(0.25)
    '1970-01-01T00:00:00.250Z'
    """
    d = datetime.fromtimestamp(t, UTC)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


__all__ = [
    "GPX_SPORTART",
    "StreckenSchreiber",
    "dateiname",
    "gpx",
    "jsonl_lesen",
    "kopf_lesen",
    "spur_ohne_ort",
    "verwaiste",
]
