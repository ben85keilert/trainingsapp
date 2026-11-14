"""Einstellungen des Ausdauertrainings — Karte einfärben, Tempo mit oder ohne Pausen,
Spalten der Kilometer-Tabelle, Achse der Kurve, Auto-Pause (Ben, 26.10.2026, P81).

Gerätelokal wie `core.hrv_einstellungen` (``app_setting``, Schlüssel
``training_einstellungen``, JSON). Was hier steht, ist Darstellung und Lesart — keine
Bewertung (``docs/recht/00_zweckbestimmung.md``). Plan: ``docs/plan_strecken_ansicht.md``.

**Feste Tempo-Stufen** (Ben, 13.11.2026): Die Verteilung „Zeit je Tempo“ teilt sonst nach
dem Training selbst (`core.strecke_farbe.spanne`) — gut für das eine Training, aber zwei
Trainings lassen sich so nicht vergleichen. Hier steht nur noch die Wahl „Training“ oder
„Fest“ (`tempo_stufen`); die vier Grenzen selbst gehören seit „GPS je Übung“ zur Übung
(`core.gps_wahl.GpsWahl`) — die Schlüssel ``tempo_niveau`` und ``tempo_eigen`` von einem Tag
davor liest nur noch die Datenumstellung (`data.upgrade`, Schritt 7). Die Herzfrequenz teilt
die Verteilung nach den Bereichen des Profils (`core.hf_profil.bereiche_fuer`); `hf_bereiche`
wählt nur, welches Modell die Auswertung des Trainings zeigt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Final

from hrv_core import herzfrequenz as hz

from trainingsapp.core.experimentell import DFA_LANG

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
    "dfa": DFA_LANG,
    "hoehe_auf": "Höhe hinauf",
    "hoehe_ab": "Höhe hinab",
    "pause": "Pause",
}
STANDARD_SPALTEN: Final[tuple[str, ...]] = ("zeit", "tempo", "hf", "dfa", "hoehe_auf")
#: x-Achse der Kurve „Herzfrequenz und Tempo“
KURVE_ZEIT: Final[str] = "zeit"
KURVE_STRECKE: Final[str] = "strecke"
KURVE_X: Final[tuple[str, ...]] = (KURVE_ZEIT, KURVE_STRECKE)

#: Stufen der Verteilung „Zeit je Tempo“: nach diesem Training oder nach festen Grenzen
TEMPO_RELATIV: Final[str] = "relativ"
TEMPO_FEST: Final[str] = "fest"
TEMPO_STUFEN: Final[tuple[str, ...]] = (TEMPO_RELATIV, TEMPO_FEST)
#: Herzfrequenz-Verteilung der Auswertung: wie im Profil eingestellt, ein Modell von dort
#: (3 · 5 · 10 Bereiche) oder gleich breite Schritte von zehn Schlägen
HF_WIE_PROFIL: Final[str] = ""
HF_BPM: Final[str] = "bpm"
HF_BEREICHE: Final[tuple[str, ...]] = (
    HF_WIE_PROFIL,
    hz.MODELL_DREI,
    hz.MODELL_ACSM,
    hz.MODELL_CLUSTER,
    HF_BPM,
)


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
    >>> f = TrainingEinstellungen(tempo_stufen="fest", hf_bereiche="acsm")
    >>> TrainingEinstellungen.aus_dict(f.als_dict()) == f
    True
    >>> alt = {"tempo_niveau": {"laufen": "eigen"}, "tempo_eigen": {"laufen": [8, 10, 12, 14]}}
    >>> TrainingEinstellungen.aus_dict({**alt, "hf_bereiche": 7}) == TrainingEinstellungen()
    True
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
    #: Stufen von „Zeit je Tempo“: `TEMPO_RELATIV` (dieses Training) oder `TEMPO_FEST`
    tempo_stufen: str = TEMPO_RELATIV
    #: eine aus `HF_BEREICHE` — wonach „Zeit je Herzfrequenz“ teilt
    hf_bereiche: str = HF_WIE_PROFIL

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
            "tempo_stufen": self.tempo_stufen,
            "hf_bereiche": self.hf_bereiche,
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
        stufen = d.get("tempo_stufen")
        hf = d.get("hf_bereiche")
        return cls(
            faerbung=faerbung if faerbung in FAERBUNGEN else vorgabe.faerbung,
            skala=skala if skala in SKALEN else vorgabe.skala,
            tempo_mit_pausen=bool(d.get("tempo_mit_pausen", vorgabe.tempo_mit_pausen)),
            spalten=gewaehlt,
            kurve_x=kurve_x if kurve_x in KURVE_X else vorgabe.kurve_x,
            auto_pause=bool(d.get("auto_pause", vorgabe.auto_pause)),
            tempo_stufen=stufen if stufen in TEMPO_STUFEN else vorgabe.tempo_stufen,
            hf_bereiche=hf if isinstance(hf, str) and hf in HF_BEREICHE else HF_WIE_PROFIL,
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
    "HF_BEREICHE",
    "HF_BPM",
    "HF_WIE_PROFIL",
    "KURVE_STRECKE",
    "KURVE_X",
    "KURVE_ZEIT",
    "SKALEN",
    "SPALTEN",
    "SPALTEN_TEXT",
    "STANDARD_SPALTEN",
    "TEMPO_FEST",
    "TEMPO_RELATIV",
    "TEMPO_STUFEN",
    "TrainingEinstellungen",
    "einstellungen_lesen",
    "einstellungen_schreiben",
]
