"""Einheiten und Kurzschrift-Eingabe.

Der Kurzschrift-Parser ist der **dritte** Beschleuniger, nicht der erste.
Auf einer Handytastatur ist „Wie zuletzt" ein Tipp und zwei Chips sind zwei
Tipper — „3x15@40kg" zu schreiben dauert länger. Der Parser lohnt sich für
Geübte und auf dem Desktop.
"""

from __future__ import annotations

import re
from typing import Any

# 3x15  ·  3 x 15  ·  3×15
_SAETZE = re.compile(r"^\s*(\d+)\s*[x×*]\s*(\d+)\s*", re.IGNORECASE)
# Ein Segment einer Satzliste: "15" oder "3x15"; "1:30" bei Zeiten
_SEGMENT = re.compile(
    r"^(?:(\d+)\s*[x×*]\s*)?([0-9][0-9.,:]*\s*(?:s|sek|sec|min|m)?)$", re.IGNORECASE
)
# @40kg  ·  @ 40 kg  ·  mit 40kg
_GEWICHT = re.compile(r"[@]\s*(\d+(?:[.,]\d+)?)\s*(kg|g|lb)?", re.IGNORECASE)
# 45°  ·  45 grad
_WINKEL = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:°|grad\b)", re.IGNORECASE)
# 1:30  ·  90s  ·  2min
_DAUER_MMSS = re.compile(r"\b(\d+):([0-5]\d)\b")
_DAUER_EINHEIT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(s|sek|sec|min|m)\b", re.IGNORECASE)


def parse_dauer(text: str) -> float | None:
    """Sekunden aus einer Dauerangabe.

    >>> parse_dauer("1:30")
    90.0
    >>> parse_dauer("90s")
    90.0
    >>> parse_dauer("2min")
    120.0
    >>> parse_dauer("45")
    45.0
    >>> parse_dauer("keine Ahnung") is None
    True
    """
    text = text.strip()
    if not text:
        return None

    if (m := _DAUER_MMSS.search(text)) is not None:
        return float(int(m.group(1)) * 60 + int(m.group(2)))

    if (m := _DAUER_EINHEIT.search(text)) is not None:
        wert = float(m.group(1).replace(",", "."))
        einheit = m.group(2).lower()
        return wert * 60.0 if einheit in ("min", "m") else wert

    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def parse_sets(text: str, zeit: bool = False) -> list[float] | None:
    """Eine Satzliste aus Text — die Notation „je Satz".

    Ein Wert je Satz; Sätze trennt ``/`` oder ``,``; ``AxB`` steht für A Sätze
    mit je B. Bei ``zeit=True`` sind die Werte Zeiten (``1:30`` = 90 s).
    Eine 0 oder ein leerer Text heißt „ohne Angabe" → ``None``.

    >>> parse_sets("30")
    [30.0]
    >>> parse_sets("3x15")
    [15.0, 15.0, 15.0]
    >>> parse_sets("15/15/20")
    [15.0, 15.0, 20.0]
    >>> parse_sets("2x15, 20")
    [15.0, 15.0, 20.0]
    >>> parse_sets("3x30", zeit=True)
    [30.0, 30.0, 30.0]
    >>> parse_sets("1:30/45s", zeit=True)
    [90.0, 45.0]
    >>> parse_sets("0") is None and parse_sets("") is None and parse_sets("abc") is None
    True
    """
    text = text.strip().lstrip("+").strip()
    if not text:
        return None
    werte: list[float] = []
    for segment in re.split(r"[/,;]", text):
        segment = segment.strip()
        if not segment:
            continue
        m = _SEGMENT.match(segment)
        if m is None:
            return None
        anzahl = int(m.group(1)) if m.group(1) else 1
        wert = parse_dauer(m.group(2)) if zeit else _zahl(m.group(2))
        if wert is None:
            return None
        werte.extend([wert] * anzahl)
    if not werte or all(w == 0 for w in werte):
        return None
    return werte


def _zahl(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def format_sets(werte: list[float] | None, zeit: bool = False) -> str:
    """Eine Satzliste kompakt: ``3x15``, ``30``, ``15/15/20``; Zeiten mit Einheit.

    >>> format_sets([15, 15, 15])
    '3x15'
    >>> format_sets([30])
    '30'
    >>> format_sets([15, 15, 20])
    '15/15/20'
    >>> format_sets([30, 30, 30], zeit=True)
    '3x30s'
    >>> format_sets([90, 45], zeit=True)
    '1:30/45s'
    >>> format_sets([])
    ''
    """
    if not werte:
        return ""

    def einzel(w: float) -> str:
        if zeit:
            return format_dauer(w).rstrip("s")
        return str(int(w)) if float(w).is_integer() else f"{w:g}"

    einheit = "s" if zeit else ""
    if len(werte) > 1 and all(w == werte[0] for w in werte):
        return f"{len(werte)}x{einzel(werte[0])}{einheit}"
    return "/".join(einzel(w) for w in werte) + einheit


def satz_summe(werte: list[float] | None) -> float:
    """Summe über alle Sätze — die Standardkennzahl für die Kurve."""
    return float(sum(werte)) if werte else 0.0


def format_dauer(sekunden: float) -> str:
    """Sekunden lesbar darstellen.

    >>> format_dauer(90)
    '1:30'
    >>> format_dauer(45)
    '45s'
    """
    sekunden = round(sekunden)
    if sekunden < 60:
        return f"{sekunden}s"
    return f"{sekunden // 60}:{sekunden % 60:02d}"


def parse_shorthand(text: str) -> dict[str, Any]:
    """Zerlegt eine Kurzschrift-Eingabe in Feldwerte.

    Erkennt Sätze×Wiederholungen, Gewicht, Winkel und Dauer — alles optional
    und in beliebiger Kombination. Was nicht erkannt wird, fehlt einfach im
    Ergebnis; der Aufrufer füllt dann aus Vorbelegung oder letztem Eintrag.

    >>> parse_shorthand("3x15")
    {'reps': [15.0, 15.0, 15.0]}
    >>> parse_shorthand("3x12 @40kg")
    {'reps': [12.0, 12.0, 12.0], 'weight': 40.0}
    >>> parse_shorthand("45°")
    {'angle': 45.0}
    >>> parse_shorthand("1:30")
    {'hold': [90.0]}
    >>> parse_shorthand("völlig frei") == {}
    True
    """
    werte: dict[str, Any] = {}
    rest = text

    if (m := _SAETZE.search(rest)) is not None:
        werte["reps"] = [float(m.group(2))] * int(m.group(1))
        rest = rest[m.end() :]

    if (m := _GEWICHT.search(rest)) is not None:
        gewicht = float(m.group(1).replace(",", "."))
        einheit = (m.group(2) or "kg").lower()
        if einheit == "g":
            gewicht /= 1000.0
        elif einheit == "lb":
            gewicht *= 0.45359237
        werte["weight"] = round(gewicht, 3)
        rest = rest[: m.start()] + rest[m.end() :]

    if (m := _WINKEL.search(rest)) is not None:
        werte["angle"] = float(m.group(1).replace(",", "."))
        rest = rest[: m.start()] + rest[m.end() :]

    # Dauer nur prüfen, wenn nach den anderen Mustern noch etwas übrig ist —
    # sonst würde die "15" aus "3x15" als 15 Sekunden gelesen.
    if (rest_str := rest.strip()) and (dauer := parse_dauer(rest_str)) is not None:
        werte["hold"] = [dauer]

    return werte


def format_bpm(rr_ms: float) -> float:
    """RR-Intervall in Herzfrequenz.

    >>> format_bpm(1000)
    60.0
    """
    return 60000.0 / rr_ms if rr_ms > 0 else 0.0


__all__ = ["format_bpm", "format_dauer", "parse_dauer", "parse_shorthand"]
