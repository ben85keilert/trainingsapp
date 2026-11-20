"""Lässt sich die Bedingung eines Wegs **eintragen**? (Ben, 20.11.2026: „wenn Wiederholungen als
Ziel formuliert sind, müssen diese verfügbar sein in Parameter zum Eintragen. Haltezeit als
Ziel/Bedingung bräuchte die Uhr auch dort … gegenchecken, ob Bedingung durch Eingabe erfüllt
werden kann“).

Im Workout lässt sich jede Bedingung erfüllen — Wiederholungen von Hand, die Skala zum Antippen,
die Zeit von der Uhr des Schritts (`views/workout.py`). Aber **eingetragen** wird nur, wofür die
Planübung einen Parameter anbietet: Zählt ein Weg Wiederholungen und die Planübung hat kein
Wiederholungsfeld, gehen sie fürs Weitergehen mit und landen in keinem Eintrag. Hier steht, was
ein Weg braucht und ob die Planübung es hat; „Im Plan einstellen“ zeigt den Hinweis am Weg und
schaltet den Parameter auf Tipp ein.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from . import ablauf as ab
from .ablauf import Kante
from .result_spec import FieldSpec, FieldType, basis_key
from .timer_eintrag import ZEITFELDER

WDH: Final = "wdh"
ZEIT: Final = "zeit"
SKALA: Final = "skala"
#: Wie der Parameter heißt, der fehlt
NAMEN: Final[dict[str, str]] = {WDH: "Wiederholungen", ZEIT: "eine Zeit", SKALA: "eine Skala"}


def braucht(k: Kante) -> str | None:
    """Welche Eingabe der Auslöser eines Wegs zählt — ``None`` bei „frei“ und bei Antworten.

    >>> braucht(Kante("a", "b", ausloeser=ab.WDH)), braucht(Kante("a", "b", ausloeser=ab.ZEIT))
    ('wdh', 'zeit')
    >>> braucht(Kante("a", "b", ausloeser=ab.WDH_IN_ZEIT)), braucht(Kante("a", "b"))
    ('wdh', None)
    >>> braucht(Kante("a", "b", ausloeser=ab.SKALA))
    'skala'
    """
    return {ab.WDH: WDH, ab.WDH_IN_ZEIT: WDH, ab.ZEIT: ZEIT, ab.SKALA: SKALA}.get(k.ausloeser)


def passt(art: str, feld: FieldSpec) -> bool:
    """Nimmt dieses Feld die Eingabe der Art auf? Gefragt wird nach der *Art* des Felds
    (`basis_key`), nie nach dem Schlüssel — ``reps_2`` zählt wie ``reps``."""
    if art == WDH:
        return basis_key(feld.key) == "reps"
    if art == ZEIT:
        return basis_key(feld.key) in ZEITFELDER
    if art == SKALA:
        return feld.type == FieldType.SCALE
    return False


def fehlt(k: Kante, felder: Iterable[FieldSpec]) -> str | None:
    """Die Art der Eingabe, die der Weg zählt und für die die Planübung **keinen** Parameter
    anbietet — ``None``, wenn alles da ist oder der Weg nichts zählt.

    >>> from .result_spec import vorrat_feld
    >>> wdh = Kante("a", "b", ausloeser=ab.WDH)
    >>> fehlt(wdh, []), fehlt(wdh, [vorrat_feld("reps_2")]), fehlt(Kante("a", "b"), [])
    ('wdh', None, None)
    >>> zeit = Kante("a", "b", ausloeser=ab.ZEIT)
    >>> fehlt(zeit, [vorrat_feld("reps")]), fehlt(zeit, [vorrat_feld("hold")])
    ('zeit', None)
    """
    art = braucht(k)
    if art is None:
        return None
    return None if any(passt(art, f) for f in felder) else art


def kandidat(art: str, felder: Iterable[FieldSpec]) -> FieldSpec | None:
    """Das erste Feld der Reihe, das die Eingabe aufnähme — zum Einschalten auf Tipp.

    >>> from .result_spec import vorrat_feld
    >>> kandidat(ZEIT, [vorrat_feld("reps"), vorrat_feld("hold"), vorrat_feld("duration")]).key
    'hold'
    >>> kandidat(SKALA, [vorrat_feld("reps")]) is None
    True
    """
    return next((f for f in felder if passt(art, f)), None)


__all__ = ["NAMEN", "SKALA", "WDH", "ZEIT", "braucht", "fehlt", "kandidat", "passt"]
