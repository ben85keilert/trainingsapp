"""Das Protokollfeld „Atmung“ der Messdatei (``raw-v1``, Vertrag `docs/kompatibilitaet.md` §5).

Plan `docs/plan_beschleunigung.md` §7.4, P125: Die Messdatei sagt im Kopf, **wie** während der
Messung geatmet wurde — ``{"art": "spontan"}``, ``{"art": "uebung", "uebung": "<Kurzcode>"}``
oder ``{"art": "getaktet", "takt_pro_min": 6.0}``. Ohne die Angabe sind HF-Power, LF/HF und
DFA α1 zwischen Messungen nicht vergleichbar (§7.1). **Automatisch, nie von Hand**, aus den
Übungen der Aufnahme:

- Lief eine Übung vom Typ „Atmung“ (`core.zaehlen.atmung_an`, über die Kurzcodes in den
  Ereignissen — `uebungen`, Vertrag §4), ist die Art ``uebung`` mit dem Kurzcode der ersten.
- Lief gar keine Übung, ist die Messung ``spontan`` (frei geatmet).
- Liefen nur andere Übungen (Kniebeugen, Laufen), bleibt das Feld weg: unbekannt — wer bei
  Kniebeugen wie atmet, weiß niemand, und der Leser rät nicht (Vertrag §5).
- ``getaktet`` kommt erst mit dem Taktgeber im Timer (A18, Plan §7.6).

Der `Messlauf` bekommt dafür den Haken ``atmung_protokoll`` (Ereignisse → Feld), den die
Oberfläche mit dem Übungskatalog belegt (`protokoll` mit `ist_atemuebung`); geschrieben wird
das Feld beim Speichern direkt hinter ``datenqualitaet`` (`kopffeld_schreiben`), fürs
Crash-Backup trägt es der Block ``_wiederherstellung``. Altdateien ohne Feld bleiben lesbar;
`hrv_core.recording.Recording` hält es in ``extra``, `hrv_core.deid` behält es.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Final

from hrv_core.recording import json_atomar_schreiben

#: Der Schlüssel im Kopf der Messdatei
FELD: Final[str] = "atmung"
#: Die Arten (Vertrag §5)
ART_SPONTAN: Final[str] = "spontan"
ART_GETAKTET: Final[str] = "getaktet"
ART_UEBUNG: Final[str] = "uebung"
ARTEN: Final[tuple[str, ...]] = (ART_SPONTAN, ART_GETAKTET, ART_UEBUNG)
#: Hinter diesem Kopffeld steht ``atmung`` (Vertrag §3) — sonst hinter `intervall_quelle`
_VORGAENGER: Final[tuple[str, ...]] = ("datenqualitaet", "intervall_quelle")


def kurzcodes(ereignisse: Iterable[Mapping[str, Any]]) -> list[str]:
    """Die Kurzcodes aller Übungen, die die Ereignisse nennen — in Reihenfolge, ohne Doppelte.

    >>> kurzcodes([{"text": "Start", "uebungen": ["AAAAAAAA", "BBBBBBBB"]},
    ...            {"text": "ohne"}, {"uebungen": ["AAAAAAAA", "CCCCCCCC"]}])
    ['AAAAAAAA', 'BBBBBBBB', 'CCCCCCCC']
    >>> kurzcodes([{"uebungen": "kein Feld"}])
    []
    """
    out: dict[str, None] = {}
    for e in ereignisse:
        codes = e.get("uebungen") if isinstance(e, Mapping) else None
        if not isinstance(codes, list):
            continue
        for c in codes:
            if isinstance(c, str) and c:
                out.setdefault(c, None)
    return list(out)


def protokoll(
    ereignisse: Iterable[Mapping[str, Any]], ist_atemuebung: Callable[[str], bool | None]
) -> dict[str, Any] | None:
    """Das Protokollfeld aus den Ereignissen der Aufnahme — ``None`` = unbekannt (kein Feld).

    ``ist_atemuebung(kurzcode)``: ``True`` für eine Übung vom Typ „Atmung“, ``False`` für eine
    andere, ``None`` für einen Code, den der Katalog nicht kennt (zählt wie eine andere Übung:
    es lief etwas, nur was, ist unklar).

    >>> atem = {"ATEMATEM": True, "KNIEBEUG": False}.get
    >>> protokoll([], atem)
    {'art': 'spontan'}
    >>> protokoll([{"text": "Box Breathing", "uebungen": ["ATEMATEM"]}], atem)
    {'art': 'uebung', 'uebung': 'ATEMATEM'}
    >>> protokoll([{"uebungen": ["KNIEBEUG"]}, {"uebungen": ["ATEMATEM"]}], atem)
    {'art': 'uebung', 'uebung': 'ATEMATEM'}
    >>> protokoll([{"uebungen": ["KNIEBEUG"]}], atem) is None
    True
    >>> protokoll([{"uebungen": ["UNBEKANN"]}], atem) is None
    True
    """
    codes = kurzcodes(ereignisse)
    if not codes:
        return {"art": ART_SPONTAN}
    for code in codes:
        if ist_atemuebung(code) is True:
            return {"art": ART_UEBUNG, "uebung": code}
    return None


def feld_lesen(doc: Mapping[str, Any]) -> dict[str, Any] | None:
    """Das Feld aus dem Kopf (oder aus ``Recording.extra``) — ``None``, wenn es fehlt oder
    keine bekannte Art trägt (unbekannt, kein Standardwert).

    >>> feld_lesen({"atmung": {"art": "getaktet", "takt_pro_min": 6}})
    {'art': 'getaktet', 'takt_pro_min': 6}
    >>> feld_lesen({}) is None, feld_lesen({"atmung": {"art": "x"}}) is None
    (True, True)
    """
    feld = doc.get(FELD)
    if not isinstance(feld, Mapping) or feld.get("art") not in ARTEN:
        return None
    return dict(feld)


def text(feld: Mapping[str, Any] | None, uebung_name: str = "") -> str:
    """Das Feld in Worten für die Auswertung — leer, wenn unbekannt.

    >>> text({"art": "spontan"}), text({"art": "getaktet", "takt_pro_min": 6.0})
    ('spontan geatmet', 'getaktet 6/min')
    >>> text({"art": "uebung", "uebung": "ATEMATEM"}, "Box Breathing"), text(None)
    ('Atemübung Box Breathing', '')
    """
    if feld is None:
        return ""
    art = feld.get("art")
    if art == ART_SPONTAN:
        return "spontan geatmet"
    if art == ART_GETAKTET:
        takt = feld.get("takt_pro_min")
        return f"getaktet {takt:g}/min" if isinstance(takt, int | float) else "getaktet"
    if art == ART_UEBUNG:
        return f"Atemübung {uebung_name or feld.get('uebung', '')}".rstrip()
    return ""


def einordnen(doc: Mapping[str, Any], feld: Mapping[str, Any]) -> dict[str, Any]:
    """Das Feld in den Kopf setzen, direkt hinter ``datenqualitaet`` (Vertrag §3) — ein
    vorhandenes wird ersetzt; alles andere bleibt in seiner Reihenfolge.

    >>> list(einordnen({"geraet": "H10", "intervall_quelle": "ekg_rr", "datenqualitaet": "rr_ekg",
    ...                 "simulation": False, "messungen": []}, {"art": "spontan"}))
    ['geraet', 'intervall_quelle', 'datenqualitaet', 'atmung', 'simulation', 'messungen']
    >>> list(einordnen({"atmung": {"art": "x"}, "intervall_quelle": "ekg_rr"}, {"art": "spontan"}))
    ['intervall_quelle', 'atmung']
    """
    out: dict[str, Any] = {}
    gesetzt = False
    for k, v in doc.items():
        if k == FELD:
            continue
        out[k] = v
        if (
            not gesetzt
            and k in _VORGAENGER
            and not any(g in doc for g in _VORGAENGER[: _VORGAENGER.index(k)])
        ):
            out[FELD] = dict(feld)
            gesetzt = True
    if not gesetzt:
        out[FELD] = dict(feld)
    return out


def kopffeld_schreiben(pfad: Path | str, feld: Mapping[str, Any]) -> None:
    """Das Feld in eine geschriebene Messdatei setzen (atomar, `json_atomar_schreiben`).

    Raises:
        OSError, ValueError: Datei nicht lesbar oder kein JSON-Objekt.
    """
    p = Path(pfad)
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict):
        raise ValueError(f"keine Messdatei: {p}")
    json_atomar_schreiben(p, einordnen(doc, feld))


__all__ = [
    "ARTEN",
    "ART_GETAKTET",
    "ART_SPONTAN",
    "ART_UEBUNG",
    "FELD",
    "einordnen",
    "feld_lesen",
    "kopffeld_schreiben",
    "kurzcodes",
    "protokoll",
    "text",
]
