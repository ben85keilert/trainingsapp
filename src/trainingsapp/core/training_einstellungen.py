"""Einstellungen des Ausdauertrainings — Karte einfärben, Tempo mit oder ohne Pausen,
Spalten der Kilometer-Tabelle, Achse der Kurve, Auto-Pause (Ben, 26.10.2026, P81).

Gerätelokal wie `core.hrv_einstellungen` (``app_setting``, Schlüssel
``training_einstellungen``, JSON). Was hier steht, ist Darstellung und Lesart — keine
Bewertung: Zonen oder Grenzwerte für Puls und Tempo gibt es nicht
(``docs/recht/00_zweckbestimmung.md``). Plan: ``docs/plan_strecken_ansicht.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Final

#: Wonach die Strecke auf der Karte eingefärbt wird
FAERBUNG_TEMPO: Final[str] = "tempo"
FAERBUNG_HF: Final[str] = "hf"
FAERBUNG_AUS: Final[str] = "aus"
FAERBUNGEN: Final[tuple[str, ...]] = (FAERBUNG_TEMPO, FAERBUNG_HF, FAERBUNG_AUS)
#: Farbskalen (die Farben selbst: `ui.farben.TEMPO_SKALEN`)
SKALEN: Final[tuple[str, ...]] = ("tempo", "viridis", "glut")
#: Wählbare Spalten der Tabelle „Je Kilometer“ — „km“ steht immer
SPALTEN: Final[tuple[str, ...]] = ("zeit", "tempo", "hf", "dfa", "hoehe_auf", "hoehe_ab", "pause")
SPALTEN_TEXT: Final[dict[str, str]] = {
    "zeit": "Zeit (gesamt)",
    "tempo": "Tempo",
    "hf": "Ø HF",
    "dfa": "DFA α1",
    "hoehe_auf": "Höhe hinauf",
    "hoehe_ab": "Höhe hinab",
    "pause": "Pause",
}
STANDARD_SPALTEN: Final[tuple[str, ...]] = ("zeit", "tempo", "hf", "dfa", "hoehe_auf")
#: x-Achse der Kurve „Herzfrequenz und Tempo“
KURVE_ZEIT: Final[str] = "zeit"
KURVE_STRECKE: Final[str] = "strecke"
KURVE_X: Final[tuple[str, ...]] = (KURVE_ZEIT, KURVE_STRECKE)


@dataclass(frozen=True, slots=True)
class TrainingEinstellungen:
    """Gerätelokale Einstellungen des Ausdauertrainings.

    >>> e = TrainingEinstellungen(skala="viridis", tempo_mit_pausen=True, spalten=["zeit", "pause"])
    >>> TrainingEinstellungen.aus_dict(e.als_dict()) == e
    True
    >>> kaputt = {"faerbung": "lila", "spalten": "kaputt", "kurve_x": 3}
    >>> TrainingEinstellungen.aus_dict(kaputt) == TrainingEinstellungen()
    True
    >>> TrainingEinstellungen.aus_dict({"spalten": ["pause", "unsinn", "zeit"]}).spalten
    ['zeit', 'pause']
    >>> TrainingEinstellungen().zeigt("hoehe_ab"), TrainingEinstellungen().zeigt("tempo")
    (False, True)
    """

    #: `FAERBUNG_TEMPO`, `FAERBUNG_HF` oder `FAERBUNG_AUS`
    faerbung: str = FAERBUNG_TEMPO
    #: eine aus `SKALEN`
    skala: str = "tempo"
    #: Tempo je Kilometer mit den Pausen (Echtzeit) statt der Bewegungszeit — gilt in der
    #: Tabelle „Je Kilometer“, live, bei den Intervallen und beim Ø Tempo
    tempo_mit_pausen: bool = False
    #: sichtbare Spalten der Tabelle „Je Kilometer“, in der Reihenfolge von `SPALTEN`
    spalten: list[str] = field(default_factory=lambda: list(STANDARD_SPALTEN))
    #: `KURVE_ZEIT` oder `KURVE_STRECKE`
    kurve_x: str = KURVE_ZEIT
    #: Auto-Pause: Stillstand zählt nicht zur Bewegungszeit (`core.strecke.STILLSTAND_S`)
    auto_pause: bool = True

    def zeigt(self, spalte: str) -> bool:
        return spalte in self.spalten

    def als_dict(self) -> dict[str, Any]:
        return {
            "faerbung": self.faerbung,
            "skala": self.skala,
            "tempo_mit_pausen": self.tempo_mit_pausen,
            "spalten": list(self.spalten),
            "kurve_x": self.kurve_x,
            "auto_pause": self.auto_pause,
        }

    @classmethod
    def aus_dict(cls, d: dict[str, Any]) -> TrainingEinstellungen:
        """Tolerant: Unbekanntes oder Falsches fällt auf die Vorgabe zurück."""
        vorgabe = cls()
        faerbung = d.get("faerbung")
        skala = d.get("skala")
        kurve_x = d.get("kurve_x")
        spalten = d.get("spalten")
        if isinstance(spalten, list):
            gewaehlt = [s for s in SPALTEN if s in spalten]
        else:
            gewaehlt = list(vorgabe.spalten)
        return cls(
            faerbung=faerbung if faerbung in FAERBUNGEN else vorgabe.faerbung,
            skala=skala if skala in SKALEN else vorgabe.skala,
            tempo_mit_pausen=bool(d.get("tempo_mit_pausen", vorgabe.tempo_mit_pausen)),
            spalten=gewaehlt,
            kurve_x=kurve_x if kurve_x in KURVE_X else vorgabe.kurve_x,
            auto_pause=bool(d.get("auto_pause", vorgabe.auto_pause)),
        )


def einstellungen_lesen(text: str | None) -> TrainingEinstellungen:
    try:
        return TrainingEinstellungen.aus_dict(json.loads(text or ""))
    except (TypeError, ValueError, AttributeError):
        return TrainingEinstellungen()


def einstellungen_schreiben(e: TrainingEinstellungen) -> str:
    return json.dumps(e.als_dict(), ensure_ascii=False)


__all__ = [
    "FAERBUNGEN",
    "FAERBUNG_AUS",
    "FAERBUNG_HF",
    "FAERBUNG_TEMPO",
    "KURVE_STRECKE",
    "KURVE_X",
    "KURVE_ZEIT",
    "SKALEN",
    "SPALTEN",
    "SPALTEN_TEXT",
    "STANDARD_SPALTEN",
    "TrainingEinstellungen",
    "einstellungen_lesen",
    "einstellungen_schreiben",
]
