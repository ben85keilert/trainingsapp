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
- **Der Takt geht vor** (Taktgeber Teil 2 T4, `docs/plan_taktgeber.md` §3): Lief ein Atemtakt —
  die Messdatei trägt dann ein Paar Notizen ``timer/takt`` … ``timer/ende`` auf der Spur
  ``atemtakt`` (Vertrag §4, `takt_laeufe`) —, ist es ``getaktet`` mit ``takt_pro_min`` = der
  Rate des **längsten** Takt-Laufs (nach einer Tempoänderung gibt es mehrere; ein am Ende
  offener Lauf reicht bis zum Ende der Aufnahme, `takt_rate`). Ein Bewegungstakt setzt keine
  Marke und also kein ``getaktet``.

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

#: Die Marke des Atemtakts in den Ereignissen (Vertrag §4): Beginn ``timer/takt``, Ende
#: ``timer/ende``, beide auf der Spur ``atemtakt``
MARKE_QUELLE: Final[str] = "timer"
MARKE_ART_TAKT: Final[str] = "takt"
MARKE_ART_ENDE: Final[str] = "ende"
SPUR_ATEMTAKT: Final[str] = "atemtakt"
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


def _zeit(e: Mapping[str, Any]) -> float | None:
    """Die Wanduhr einer Notiz (``t_wall_s``, sonst ``t_s``) — ``None`` ohne Zahl."""
    for k in ("t_wall_s", "t_s"):
        wert = e.get(k)
        if isinstance(wert, int | float) and not isinstance(wert, bool):
            return float(wert)
    return None


def takt_laeufe(
    ereignisse: Iterable[Mapping[str, Any]], ende_s: float | None = None
) -> list[tuple[float, float, float]]:
    """Die Takt-Läufe aus den Marken der Messdatei (Vertrag §4, Spur ``atemtakt``):
    ``(von_s, bis_s, rate_pro_min)`` je Paar Beginn (``timer/takt`` mit ``wert``) und Ende
    (``timer/ende`` auf der Spur); ein offener Lauf reicht bis ``ende_s`` (sonst bis zu seinem
    Beginn — Dauer 0). Notizen ohne Zeit oder ohne Rate fallen weg.

    >>> m = lambda art, **f: {"quelle": "timer", "art": art, "spur": "atemtakt", **f}
    >>> takt_laeufe([{"t_wall_s": 10.0, "marke": m("takt", wert=6.0, name="A")},
    ...              {"t_wall_s": 70.0, "marke": m("ende", name="A")},
    ...              {"t_wall_s": 80.0, "marke": m("takt", wert=5.0)}], ende_s=100.0)
    [(10.0, 70.0, 6.0), (80.0, 100.0, 5.0)]
    >>> takt_laeufe([{"t_wall_s": 1.0, "marke": {"quelle": "timer", "art": "abschnitt"}}])
    []
    """
    out: list[tuple[float, float, float]] = []
    offen: tuple[float, float] | None = None
    for e in ereignisse:
        if not isinstance(e, Mapping):
            continue
        m = e.get("marke")
        if not isinstance(m, Mapping) or m.get("spur") != SPUR_ATEMTAKT:
            continue
        if m.get("quelle") != MARKE_QUELLE:
            continue
        t = _zeit(e)
        if t is None:
            continue
        if m.get("art") == MARKE_ART_TAKT:
            rate = m.get("wert")
            if offen is not None:
                out.append((offen[0], max(offen[0], t), offen[1]))
                offen = None
            if isinstance(rate, int | float) and not isinstance(rate, bool) and rate > 0:
                offen = (t, float(rate))
        elif m.get("art") == MARKE_ART_ENDE and offen is not None:
            out.append((offen[0], max(offen[0], t), offen[1]))
            offen = None
    if offen is not None:
        bis = offen[0] if ende_s is None else max(offen[0], ende_s)
        out.append((offen[0], bis, offen[1]))
    return out


def takt_rate(ereignisse: Iterable[Mapping[str, Any]], ende_s: float | None = None) -> float | None:
    """Die Rate des längsten Takt-Laufs (je Minute, zwei Nachkommastellen) — ``None``, wenn
    keiner lief.

    >>> m = lambda art, **f: {"quelle": "timer", "art": art, "spur": "atemtakt", **f}
    >>> takt_rate([{"t_wall_s": 0.0, "marke": m("takt", wert=6.0)},
    ...            {"t_wall_s": 20.0, "marke": m("ende")},
    ...            {"t_wall_s": 20.0, "marke": m("takt", wert=4.5)}], ende_s=100.0)
    4.5
    >>> takt_rate([]) is None
    True
    """
    laeufe = takt_laeufe(ereignisse, ende_s)
    if not laeufe:
        return None
    _von, _bis, rate = max(laeufe, key=lambda lauf: (lauf[1] - lauf[0], lauf[0]))
    return round(rate, 2)


def protokoll(
    ereignisse: Iterable[Mapping[str, Any]],
    ist_atemuebung: Callable[[str], bool | None],
    *,
    ende_s: float | None = None,
) -> dict[str, Any] | None:
    """Das Protokollfeld aus den Ereignissen der Aufnahme — ``None`` = unbekannt (kein Feld).

    ``ist_atemuebung(kurzcode)``: ``True`` für eine Übung vom Typ „Atmung“, ``False`` für eine
    andere, ``None`` für einen Code, den der Katalog nicht kennt (zählt wie eine andere Übung:
    es lief etwas, nur was, ist unklar). ``ende_s``: das Ende der Aufnahme auf der Wanduhr —
    so weit reicht ein offener Takt-Lauf (`takt_rate`).

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

    Der Takt geht vor (T4): ein Atemtakt macht die Messung ``getaktet``, auch in einer
    Atemübung —

    >>> takt = {"t_wall_s": 5.0, "uebungen": ["ATEMATEM"],
    ...         "marke": {"quelle": "timer", "art": "takt", "spur": "atemtakt", "wert": 6.0}}
    >>> protokoll([takt], atem, ende_s=65.0)
    {'art': 'getaktet', 'takt_pro_min': 6.0}
    """
    rate = takt_rate(ereignisse := list(ereignisse), ende_s)
    if rate is not None:
        return {"art": ART_GETAKTET, "takt_pro_min": rate}
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
    "takt_laeufe",
    "takt_rate",
    "text",
]
