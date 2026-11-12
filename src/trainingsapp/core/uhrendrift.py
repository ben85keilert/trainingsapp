"""Tiefschlaf des Handys zwischen Ortungszeit und App-Uhr (Ben, 12.11.2026).

Herzschläge und Ortungen stehen auf zwei Uhren: Die Schläge zählen auf der monotonen Uhr
der App (``t_wall_s`` = ``time.monotonic`` seit dem Start der Aufnahme), die Ortungen
tragen die Zeit des Empfängers (``Punkt.t``, UTC). Die monotone Uhr **steht im Tiefschlaf**
der CPU (``CLOCK_MONOTONIC``; `devices.einheit._schlafversatz`), die Empfängerzeit nicht —
jede Schlafphase schiebt die Herzfrequenz gegenüber dem Tempo. In der Kurve „Herzfrequenz
und Tempo“ sah das wie eine Drift aus.

Jede Ortung trägt beide Uhren (``t`` und ``t_empfang``): ``t_empfang − t`` fällt mit jeder
Schlafphase um ihre Dauer. Der Versatz der Einheit (`devices.gatt.UhrAbgleich`: laufendes
Minimum) gilt darum für das **Ende** des Trainings; `schlaf_rest` sagt je Ortungszeit, wie
viel Schlaf bis dahin noch kommt — so viel später steht ein Schlag auf der App-Uhr, als der
Versatz allein ergibt.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Sequence
from typing import Final

from .strecke import Punkt

#: Erst ab so viel (s) gilt ein Sprung als Schlaf — darunter schwankt die Laufzeit der Ortung
SCHWELLE_S: Final[float] = 0.5
#: Über so viele Ortungen zurück das Minimum (die schnellste kam ohne Stau durch)
FENSTER: Final[int] = 5

#: ``(Ortungszeit, Schlaf danach bis zum Ende in s)`` — gilt ab dieser Ortungszeit
Stufen = tuple[tuple[float, float], ...]


def schlaf_rest(punkte: Iterable[Punkt]) -> Stufen:
    """Je Ortungszeit: so viel Tiefschlaf folgt noch bis zur letzten Ortung — als Stufen.

    Ohne Empfangszeit (alte Dateien, Wiedergabe) oder ohne Schlaf leer.

    >>> wach = [Punkt(1000.0 + i, 52.0, 13.0, t_empfang=5.0 + i) for i in range(20)]
    >>> schlaf_rest(wach)
    ()
    >>> spaeter = [Punkt(1050.0 + i, 52.0, 13.0, t_empfang=25.0 + i) for i in range(20)]
    >>> schlaf_rest(wach + spaeter)       # 30 s geschlafen: Empfängeruhr +50, App-Uhr +20
    ((1000.0, 30.0), (1050.0, 0.0))
    >>> stau = [Punkt(1000.0 + i, 52.0, 13.0, t_empfang=5.0 + i + 0.3 * (i % 3)) for i in range(20)]
    >>> schlaf_rest(stau)                 # schwankende Laufzeit ist kein Schlaf
    ()
    """
    roh = sorted((p.t, p.t_empfang - p.t) for p in punkte if p.t_empfang is not None)
    if len(roh) < 2:
        return ()
    # Rückwärts geglättet: Ein Stau hebt den Wert nur kurz, der Schlaf senkt ihn sofort
    glatt = [min(d for _, d in roh[max(0, i - FENSTER + 1) : i + 1]) for i in range(len(roh))]
    ende = min(glatt)
    stufen: list[tuple[float, float]] = []
    for (t, _), g in zip(roh, glatt, strict=True):
        rest = g - ende
        if not stufen:
            stufen.append((t, rest))
        elif stufen[-1][1] - rest > SCHWELLE_S:  # die App-Uhr hat Zeit verloren: Schlaf
            stufen.append((t, max(rest, 0.0)))
    if len(stufen) == 1:
        return ()
    letzte = stufen[-1][1]  # Rest unter der Schwelle: auf null ziehen
    return tuple((t, round(rest - letzte, 3)) for t, rest in stufen)


def rest_bei(stufen: Sequence[tuple[float, float]], t: float) -> float:
    """Der Schlaf, der nach der Ortungszeit ``t`` noch kommt (0 ohne Stufen).

    >>> s = ((1000.0, 30.0), (1050.0, 0.0))
    >>> rest_bei(s, 990.0), rest_bei(s, 1049.0), rest_bei(s, 1050.0), rest_bei((), 5.0)
    (30.0, 30.0, 0.0, 0.0)
    """
    if not stufen:
        return 0.0
    i = bisect_right([s[0] for s in stufen], t) - 1
    return stufen[max(i, 0)][1]


def rest_auf_app_uhr(stufen: Sequence[tuple[float, float]], u: float) -> float:
    """Dasselbe von der anderen Seite: ``u`` ist eine Zeit der App-Uhr, mit dem Versatz
    des Endes in Ortungszeit umgerechnet (``u = t + Rest``).

    >>> s = ((1000.0, 30.0), (1050.0, 0.0))
    >>> rest_auf_app_uhr(s, 1045.0), rest_auf_app_uhr(s, 1055.0)   # t = 1015 und t = 1055
    (30.0, 0.0)
    """
    if not stufen:
        return 0.0
    i = bisect_right([t + rest for t, rest in stufen], u) - 1
    return stufen[max(i, 0)][1]


__all__ = ["FENSTER", "SCHWELLE_S", "Stufen", "rest_auf_app_uhr", "rest_bei", "schlaf_rest"]
