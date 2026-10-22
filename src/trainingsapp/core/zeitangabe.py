"""Zeitangaben einer Messung — als Dauer („2:15“) oder als Uhrzeit („14:03:05“).

Eine Notiz trägt man live nach der Dauer seit Aufnahmestart ein, nachträglich oft
nur nach der Uhr („um 14:03 hat es gezogen“) — beides muss sich lesen und
schreiben lassen (Ben, 20.10.2026). Dasselbe gilt für die Zeitachse der Kurven:
Dauer seit Beginn oder echte Uhrzeit.

Die Uhrzeit ist immer die **lokale** des Geräts, gerechnet aus ``start_utc`` der
Aufnahme plus Sekunden — so wie `hrv_core.ereignisse.uhrzeit` die ``wall_time``
einer Notiz bildet. Über Mitternacht hinweg gilt die nächstliegende Deutung
(`uhr_lesen`).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from hrv_core.ereignisse import Zeitbezug, anker_aus_wand

from trainingsapp.core.laufend import minuten

#: Die beiden Schreibweisen (Notizeingabe, Achse)
DAUER = "dauer"
UHR = "uhr"

#: Sekunden eines Tages — für die Deutung einer Uhrzeit ohne Datum
_TAG_S = 86400.0

_DAUER = re.compile(r"^\s*([-−+]?)\s*(?:(\d+):)?(?:(\d+):)?(\d+(?:[.,]\d*)?)\s*(?:s|sek)?\s*$")
_UHR = re.compile(r"^\s*(\d{1,2})[:.](\d{2})(?::(\d{2}))?\s*(?:Uhr)?\s*$", re.IGNORECASE)
_BREITE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(s|sek|sec|m|min|h|std)?\.?\s*$", re.IGNORECASE)
#: Einheit einer eingetippten Breite → Sekunden; ohne Einheit sind es Minuten
_BREITE_EINHEIT = {"s": 1, "sek": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "std": 3600}


def dauer_text(sekunden: float) -> str:
    """Dauer als ``m:ss`` (`core.laufend.minuten`); vor dem Nullpunkt mit Minus.

    >>> dauer_text(135), dauer_text(-12.4), dauer_text(4200)
    ('2:15', '−0:12', '70:00')
    """
    return ("−" if sekunden < 0 else "") + minuten(abs(sekunden))


def dauer_lesen(text: str) -> float | None:
    """``m:ss``, ``h:mm:ss`` oder Sekunden → Sekunden; ``None``, wenn nicht lesbar.

    >>> dauer_lesen("2:15"), dauer_lesen("1:02:03"), dauer_lesen("90"), dauer_lesen("−0:12")
    (135.0, 3723.0, 90.0, -12.0)
    >>> dauer_lesen("2,5 s"), dauer_lesen("14:03 Uhr"), dauer_lesen("abc"), dauer_lesen("")
    (2.5, None, None, None)
    """
    m = _DAUER.match(text or "")
    if m is None:
        return None
    vorzeichen, a, b, rest = m.groups()
    sekunden = float(rest.replace(",", "."))
    teile = [int(t) for t in (a, b) if t is not None]
    for faktor, wert in zip((60, 3600), reversed(teile), strict=False):
        sekunden += faktor * wert
    return -sekunden if vorzeichen in ("-", "−") else sekunden


def breite_lesen(text: str) -> float | None:
    """Eine eingetippte Breite der Zeitachse in Sekunden (Ben, 21.10.2026).

    Eine Zahl allein heißt **Minuten** — so sind auch die Knöpfe beschriftet;
    ``m:ss`` und ``h:mm:ss`` wie bei `dauer_lesen`, dazu „90 s“, „1,5 h“. ``None``,
    wenn nichts Lesbares oder nichts Positives dasteht.

    >>> breite_lesen("3"), breite_lesen("2,5"), breite_lesen("1:30"), breite_lesen("90 s")
    (180.0, 150.0, 90.0, 90.0)
    >>> breite_lesen("15 Min"), breite_lesen("1 h"), breite_lesen("1:00:00")
    (900.0, 3600.0, 3600.0)
    >>> breite_lesen(""), breite_lesen("abc"), breite_lesen("0"), breite_lesen("-2")
    (None, None, None, None)
    """
    text = (text or "").strip()
    if ":" in text:
        sekunden = dauer_lesen(text)
    else:
        m = _BREITE.match(text)
        if m is None:
            return None
        zahl, einheit = m.groups()
        sekunden = float(zahl.replace(",", ".")) * _BREITE_EINHEIT[(einheit or "min").lower()]
    return sekunden if sekunden is not None and sekunden > 0 else None


def _lokal(start_utc: datetime) -> datetime:
    return start_utc.astimezone()


def uhr_text(start_utc: datetime | None, sekunden: float, *, mit_sekunden: bool = True) -> str:
    """Lokale Uhrzeit ``sekunden`` nach ``start_utc`` — ``HH:MM:SS`` oder ``HH:MM``.

    >>> from datetime import UTC
    >>> s = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    >>> t = uhr_text(s, 135); len(t), t.endswith(":15")
    (8, True)
    >>> len(uhr_text(s, 135, mit_sekunden=False)), uhr_text(None, 1)
    (5, '')
    """
    if start_utc is None:
        return ""
    try:
        t = _lokal(start_utc + timedelta(seconds=float(sekunden)))
    except (TypeError, ValueError, OverflowError):
        return ""
    return t.strftime("%H:%M:%S" if mit_sekunden else "%H:%M")


def uhr_lesen(text: str, start_utc: datetime | None) -> float | None:
    """``HH:MM[:SS]`` (lokal) → Sekunden nach ``start_utc``; ``None``, wenn nicht lesbar.

    Ohne Datum: höchstens eine Stunde vor dem Aufnahmestart, sonst ist der folgende
    Tag gemeint — eine Messung über Mitternacht bleibt eine Messung.

    >>> from datetime import UTC
    >>> s = datetime(2026, 10, 20, 12, 0, 30, tzinfo=UTC)
    >>> lokal = s.astimezone()
    >>> uhr_lesen(lokal.strftime("%H:%M:%S"), s), uhr_lesen(lokal.strftime("%H:%M"), s)
    (0.0, -30.0)
    >>> spaet = s + timedelta(hours=20)  # „morgen früh“ gehört noch zur Nacht
    >>> uhr_lesen(spaet.astimezone().strftime("%H:%M:%S"), s)
    72000.0
    >>> uhr_lesen("2:15", s), uhr_lesen("25:00", s), uhr_lesen("14:03", None)
    (None, None, None)
    """
    m = _UHR.match(text or "")
    if m is None or start_utc is None:
        return None
    h, mi, se = (int(g) if g is not None else 0 for g in m.groups())
    if h > 23 or mi > 59 or se > 59:
        return None
    # Eine zweistellige Angabe mit Punkt oder Doppelpunkt könnte auch „2:15“ (Dauer) sein —
    # eine Uhrzeit verlangt zwei Ziffern vor dem Trenner
    if len(m.group(1)) < 2:
        return None
    start = _lokal(start_utc)
    punkt = start.replace(hour=h, minute=mi, second=se, microsecond=0)
    sekunden = (punkt - start).total_seconds()
    if sekunden < -3600:
        sekunden += _TAG_S
    return float(sekunden)


def tagessekunden(start_utc: datetime | None) -> float:
    """Lokale Uhrzeit von ``start_utc`` in Sekunden seit Mitternacht — der Versatz, mit dem
    Achsenmarken auf runde Uhrzeiten fallen (``x + tagessekunden`` ist ein Vielfaches
    des Schritts). ``0`` ohne Startzeit.

    >>> from datetime import UTC
    >>> s = datetime(2026, 10, 20, 12, 0, 30, tzinfo=UTC)
    >>> l = s.astimezone(); tagessekunden(s) == l.hour * 3600 + l.minute * 60 + l.second
    True
    """
    if start_utc is None:
        return 0.0
    t = _lokal(start_utc)
    return float(t.hour * 3600 + t.minute * 60 + t.second)


# ---------------------------------------------------------------------------
# Wanduhr der Aufnahme ↔ x-Achse der Kurve
# ---------------------------------------------------------------------------


def wand_aus_x(zb: Zeitbezug, x: float) -> float:
    """Sekunden seit Aufnahmestart (``t_wall_s``) an der Stelle ``x`` der Kurve."""
    return float(zb.anker(x).get("t_wall_s") or 0.0)


def x_aus_wand(zb: Zeitbezug, t_wall_s: float) -> float | None:
    """Die Stelle auf der Kurve zu ``t_wall_s`` Sekunden nach Aufnahmestart.

    Live liegt die Wanduhr um ``wand_versatz`` neben der Achse; nachträglich geht es
    über den Anker (`hrv_core.ereignisse.anker_aus_wand`), weil Herzuhr und Wanduhr
    auseinanderlaufen, sobald Schläge fehlen.

    >>> from hrv_core.recording import Beat
    >>> beats = [Beat(0.8, 800, 70, 1.0), Beat(1.6, 800, 70, 1.8), Beat(2.4, 800, 70, 2.6)]
    >>> x_aus_wand(Zeitbezug(lambda: beats, None, wand_versatz=5.0), 2.0)
    7.0
    >>> nach = Zeitbezug(lambda: beats, None, achse=lambda: [0.8, 1.6, 2.4])
    >>> x_aus_wand(nach, 2.0), wand_aus_x(nach, 2.0)  # Wanduhr 0,2 s hinter der Herzuhr
    (1.8, 2.2)
    """
    if zb.wand_versatz is not None:
        return float(t_wall_s) + zb.wand_versatz
    return zb.x(anker_aus_wand(zb.beats(), float(t_wall_s)))


__all__ = [
    "DAUER",
    "UHR",
    "breite_lesen",
    "dauer_lesen",
    "dauer_text",
    "tagessekunden",
    "uhr_lesen",
    "uhr_text",
    "wand_aus_x",
    "x_aus_wand",
]
