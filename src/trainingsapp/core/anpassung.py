"""Vorschlag nach der Belastung (Ben, 12.11.2026, P200; `docs/plan_kurse.md` §8).

„Ein gemachter Plan fragt die Belastung nach. Bei 7+ wird die Zeit runtergesetzt, bei 3− wird
die Zeit erhöht.“ — als **Vorschlag**: Ein Plan kann eine **Regel** tragen (aus dem Kurs oder
Paket, geschrieben von der Person, die ihn gebaut hat). Nach dem Workout rechnet die App aus
der eingetragenen Anstrengung, welche Zeitziele die Regel ändern würde, und zeigt sie. Geändert
wird nur auf Tipp („Übernehmen“), nie von selbst; die Vorschläge lassen sich abschalten.

Grundlage ist allein die **Selbstauskunft** (Skala 0–10) und das Ziel im Plan — nie ein
Messwert (Herzfrequenz, HRV): Eine Empfehlung aus Messwerten wäre ``physiologische_steuerung``
(`docs/recht/00_zweckbestimmung.md`). Die App deutet die Zahl nicht; sie wendet die Regel der
Autorin an und nennt sie beim Vorschlag.

Dieses Modul kennt kein flet und keine Datenbank.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from .models import Exercise, PlanItem
from .result_spec import basis_key
from .standards import ziel_wirksam

#: Die Felder, die eine Regel ändert: Zeiten („wird die Zeit runtergesetzt“)
ZEITEN: Final = ("hold", "duration")


@dataclass(frozen=True, slots=True)
class Regel:
    """Ab welcher Anstrengung das Ziel sinkt, bis zu welcher es steigt, und um wie viel."""

    #: Anstrengung ≥ ``ab`` → kürzer
    ab: int = 7
    #: Anstrengung ≤ ``bis`` → länger
    bis: int = 3
    #: Schritt in Prozent des Ziels
    prozent: int = 10

    def als_dict(self) -> dict[str, int]:
        return {"ab": self.ab, "bis": self.bis, "prozent": self.prozent}

    @classmethod
    def aus_dict(cls, roh: Any) -> Regel | None:
        """Liest, was `als_dict` schreibt — ``None`` ohne brauchbare Regel.

        >>> Regel.aus_dict({"ab": 8, "bis": 2, "prozent": 5})
        Regel(ab=8, bis=2, prozent=5)
        >>> Regel.aus_dict({}) is None, Regel.aus_dict({"ab": 3, "bis": 7}) is None
        (True, True)
        >>> Regel.aus_dict({"prozent": 400}).prozent
        50
        """
        if not isinstance(roh, Mapping) or not roh:
            return None

        def zahl(key: str, vorgabe: int, unten: int, oben: int) -> int:
            try:
                wert = float(roh.get(key, vorgabe))
            except (TypeError, ValueError):
                return vorgabe
            return int(min(max(wert, unten), oben)) if math.isfinite(wert) else vorgabe

        regel = cls(zahl("ab", 7, 1, 10), zahl("bis", 3, 0, 9), zahl("prozent", 10, 1, 50))
        return regel if regel.bis < regel.ab else None

    def richtung(self, anstrengung: int) -> int:
        """−1 = kürzer, +1 = länger, 0 = bleibt.

        >>> r = Regel()
        >>> r.richtung(8), r.richtung(5), r.richtung(3)
        (-1, 0, 1)
        """
        if anstrengung >= self.ab:
            return -1
        if anstrengung <= self.bis:
            return 1
        return 0

    def text(self) -> str:
        """„ab 7 → −10 %, bis 3 → +10 %“ — steht beim Vorschlag."""
        return f"ab {self.ab} → −{self.prozent} %, bis {self.bis} → +{self.prozent} %"


@dataclass(frozen=True, slots=True)
class Vorschlag:
    """Ein Ziel, das die Regel ändern würde."""

    item_id: str
    uebung_id: str
    name: str
    feld: str
    #: Das Ziel jetzt und das vorgeschlagene — eine Zahl oder je Satz eine
    alt: Any
    neu: Any


def _geaendert(wert: Any, faktor: float) -> Any:
    """Der Zielwert mit ``faktor`` — auf ganze Sekunden, mindestens 1; ``None``, wenn er sich
    nicht ändern lässt (Text, leer) oder gleich bliebe.

    >>> _geaendert(48, 0.9), _geaendert([45, 45], 1.1), _geaendert("3x15", 0.9)
    (43, [50, 50], None)
    >>> _geaendert(3, 0.9) is None
    True
    """

    def eins(x: Any) -> int | None:
        try:
            zahl = float(x)
        except (TypeError, ValueError):
            return None
        return max(1, round(zahl * faktor)) if math.isfinite(zahl) and zahl > 0 else None

    if isinstance(wert, list):
        neu = [eins(x) for x in wert]
        if not neu or any(n is None for n in neu):
            return None
        return None if [float(a) for a in wert] == [float(b) for b in neu if b is not None] else neu
    einzel = eins(wert)
    if einzel is None or isinstance(wert, str):
        return None
    return None if float(wert) == float(einzel) else einzel


def vorschlaege(
    regel: Regel | None,
    items: Iterable[PlanItem],
    uebungen: Mapping[str, Exercise],
    anstrengung: int | None,
) -> list[Vorschlag]:
    """Was die Regel nach dieser Anstrengung ändern würde — je Planübung ihre Zeitziele
    (Haltezeit, Zeit), soweit sie ein Ziel hat. Ohne Regel, ohne Anstrengung oder im
    mittleren Bereich: nichts.

    >>> from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    >>> u = Exercise(id="u", name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    >>> item = PlanItem(id="i", exercise_id="u", target={"hold": [48]})
    >>> [(v.name, v.alt, v.neu) for v in vorschlaege(Regel(), [item], {"u": u}, 8)]
    [('Planke', [48], [43])]
    >>> vorschlaege(Regel(), [item], {"u": u}, 5), vorschlaege(None, [item], {"u": u}, 9)
    ([], [])
    """
    if regel is None or anstrengung is None:
        return []
    richtung = regel.richtung(anstrengung)
    if richtung == 0:
        return []
    faktor = 1 + richtung * regel.prozent / 100
    ergebnis: list[Vorschlag] = []
    for item in items:
        uebung = uebungen.get(item.exercise_id)
        if uebung is None:
            continue
        for feld, wert in ziel_wirksam(item, uebung).items():
            if basis_key(feld) not in ZEITEN:
                continue
            neu = _geaendert(wert, faktor)
            if neu is not None:
                ergebnis.append(Vorschlag(item.id, uebung.id, uebung.name, feld, wert, neu))
    return ergebnis


def ziel_mit(item: PlanItem, uebung: Exercise, vorschlag: Vorschlag) -> dict[str, Any]:
    """Das Ziel der Planübung nach „Übernehmen“: das wirksame Ziel mit dem neuen Wert — die
    Planübung bekommt damit ein eigenes Ziel („nur hier“, P79)."""
    from .standards import ziel_von

    return {**ziel_von(item, uebung), vorschlag.feld: vorschlag.neu}


__all__ = ["ZEITEN", "Regel", "Vorschlag", "vorschlaege", "ziel_mit"]
