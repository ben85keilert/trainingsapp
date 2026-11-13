"""Einstellungen des Ausdauertrainings — Karte einfärben, Tempo mit oder ohne Pausen,
Spalten der Kilometer-Tabelle, Achse der Kurve, Auto-Pause (Ben, 26.10.2026, P81).

Gerätelokal wie `core.hrv_einstellungen` (``app_setting``, Schlüssel
``training_einstellungen``, JSON). Was hier steht, ist Darstellung und Lesart — keine
Bewertung (``docs/recht/00_zweckbestimmung.md``). Plan: ``docs/plan_strecken_ansicht.md``.

**Feste Tempo-Stufen** (Ben, 13.11.2026): Die Verteilung „Zeit je Tempo“ teilt sonst nach
dem Training selbst (`core.strecke_farbe.spanne`) — gut für das eine Training, aber zwei
Trainings lassen sich so nicht vergleichen. Darum gibt es je Sportart vier feste Grenzen in
km/h (fünf Stufen): drei Vorgaben (langsam · mittel · schnell) oder eigene Werte. Die
Stufen heißen nach ihren Zahlen, sie werten nichts. Die Herzfrequenz teilt die Verteilung
nach den Bereichen des Profils (`core.hf_profil.bereiche_fuer`); `hf_bereiche` wählt nur,
welches Modell die Auswertung des Trainings zeigt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any, Final

from hrv_core import herzfrequenz as hz

from .strecke import GEHEN, LAUFEN, RAD, SPORTARTEN

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

#: Stufen der Verteilung „Zeit je Tempo“: nach diesem Training oder nach festen Grenzen
TEMPO_RELATIV: Final[str] = "relativ"
TEMPO_FEST: Final[str] = "fest"
TEMPO_STUFEN: Final[tuple[str, ...]] = (TEMPO_RELATIV, TEMPO_FEST)
#: Vorgaben der festen Grenzen und „eigen“ (die Werte der Person)
NIVEAU_LANGSAM: Final[str] = "langsam"
NIVEAU_MITTEL: Final[str] = "mittel"
NIVEAU_SCHNELL: Final[str] = "schnell"
NIVEAU_EIGEN: Final[str] = "eigen"
NIVEAUS: Final[tuple[str, ...]] = (NIVEAU_LANGSAM, NIVEAU_MITTEL, NIVEAU_SCHNELL, NIVEAU_EIGEN)
NIVEAU_NAMEN: Final[dict[str, str]] = {
    NIVEAU_LANGSAM: "langsam",
    NIVEAU_MITTEL: "mittel",
    NIVEAU_SCHNELL: "schnell",
    NIVEAU_EIGEN: "eigene Werte",
}
#: Vier Grenzen in km/h je Sportart und Vorgabe — darunter, dazwischen und darüber liegen
#: die fünf Stufen. Setzungen zum Einteilen, keine Normwerte (Ben, 13.11.2026: mittel
#: endet beim Rad bei 25 km/h, beim Laufen bei 12–15 km/h; schnell = Rennrad, trainiert).
TEMPO_GRENZEN_KMH: Final[dict[str, dict[str, tuple[float, float, float, float]]]] = {
    GEHEN: {
        NIVEAU_LANGSAM: (2.0, 3.0, 4.0, 5.0),
        NIVEAU_MITTEL: (3.0, 4.0, 5.0, 6.0),
        NIVEAU_SCHNELL: (4.0, 5.0, 6.0, 7.0),
    },
    LAUFEN: {
        NIVEAU_LANGSAM: (6.0, 7.0, 8.5, 10.0),
        NIVEAU_MITTEL: (7.0, 9.0, 11.0, 13.0),
        NIVEAU_SCHNELL: (10.0, 12.0, 14.0, 16.0),
    },
    RAD: {
        NIVEAU_LANGSAM: (10.0, 14.0, 18.0, 22.0),
        NIVEAU_MITTEL: (13.0, 17.0, 21.0, 25.0),
        NIVEAU_SCHNELL: (20.0, 25.0, 30.0, 35.0),
    },
}
TEMPO_GRENZEN_ZAHL: Final[int] = 4
TEMPO_KMH_MAX: Final[float] = 120.0
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


def grenzen_gueltig(werte: Any) -> list[float] | None:
    """Vier aufsteigende Grenzen in km/h — sonst None.

    >>> grenzen_gueltig([8, 10.5, 12, 14]), grenzen_gueltig([8, 8, 12, 14])
    ([8.0, 10.5, 12.0, 14.0], None)
    >>> grenzen_gueltig([8, 10, 12]), grenzen_gueltig("kaputt"), grenzen_gueltig([0, 1, 2, 3])
    (None, None, None)
    """
    if not isinstance(werte, (list, tuple)) or len(werte) != TEMPO_GRENZEN_ZAHL:
        return None
    if any(isinstance(w, bool) or not isinstance(w, (int, float)) for w in werte):
        return None
    zahlen = [float(w) for w in werte]
    if zahlen[0] <= 0 or zahlen[-1] > TEMPO_KMH_MAX:
        return None
    if any(b <= a for a, b in pairwise(zahlen)):
        return None
    return zahlen


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
    >>> TrainingEinstellungen().tempo_grenzen_kmh("rad")
    (13.0, 17.0, 21.0, 25.0)
    >>> f = TrainingEinstellungen(tempo_stufen="fest", tempo_niveau={"laufen": "eigen"},
    ...                           tempo_eigen={"laufen": [8.0, 10.0, 12.0, 14.0]},
    ...                           hf_bereiche="acsm")
    >>> TrainingEinstellungen.aus_dict(f.als_dict()) == f, f.tempo_grenzen_kmh("laufen")
    (True, (8.0, 10.0, 12.0, 14.0))
    >>> g = TrainingEinstellungen.aus_dict({"tempo_niveau": {"laufen": "eigen", "rad": "rasend"},
    ...                                     "tempo_eigen": {"laufen": [3, 2]}, "hf_bereiche": 7})
    >>> g.niveau("laufen"), g.niveau("rad"), g.tempo_grenzen_kmh("laufen"), g.hf_bereiche
    ('eigen', 'mittel', (7.0, 9.0, 11.0, 13.0), '')
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
    #: Sportart → Vorgabe der festen Grenzen (`NIVEAUS`); fehlt eine, gilt „mittel“
    tempo_niveau: dict[str, str] = field(default_factory=dict)
    #: Sportart → die vier eigenen Grenzen in km/h (gelten bei `NIVEAU_EIGEN`)
    tempo_eigen: dict[str, list[float]] = field(default_factory=dict)
    #: eine aus `HF_BEREICHE` — wonach „Zeit je Herzfrequenz“ teilt
    hf_bereiche: str = HF_WIE_PROFIL

    def niveau(self, sportart: str) -> str:
        return self.tempo_niveau.get(sportart, NIVEAU_MITTEL)

    def tempo_grenzen_kmh(self, sportart: str) -> tuple[float, ...]:
        """Die vier festen Grenzen der Sportart: die eigenen, wenn gewählt und gültig, sonst
        die Vorgabe; eine unbekannte Sportart nimmt die des Laufens."""
        vorgaben = TEMPO_GRENZEN_KMH.get(sportart, TEMPO_GRENZEN_KMH[LAUFEN])
        niveau = self.niveau(sportart)
        if niveau == NIVEAU_EIGEN:
            eigen = grenzen_gueltig(self.tempo_eigen.get(sportart))
            return tuple(eigen) if eigen is not None else vorgaben[NIVEAU_MITTEL]
        return vorgaben.get(niveau, vorgaben[NIVEAU_MITTEL])

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
            "tempo_niveau": dict(self.tempo_niveau),
            "tempo_eigen": {k: list(v) for k, v in self.tempo_eigen.items()},
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
        niveau = d.get("tempo_niveau")
        eigen = d.get("tempo_eigen")
        hf = d.get("hf_bereiche")
        niveaus = {
            s: n
            for s, n in (niveau.items() if isinstance(niveau, dict) else ())
            if s in SPORTARTEN and n in NIVEAUS
        }
        eigene = {
            s: g
            for s, w in (eigen.items() if isinstance(eigen, dict) else ())
            if s in SPORTARTEN and (g := grenzen_gueltig(w)) is not None
        }
        return cls(
            faerbung=faerbung if faerbung in FAERBUNGEN else vorgabe.faerbung,
            skala=skala if skala in SKALEN else vorgabe.skala,
            tempo_mit_pausen=bool(d.get("tempo_mit_pausen", vorgabe.tempo_mit_pausen)),
            spalten=gewaehlt,
            kurve_x=kurve_x if kurve_x in KURVE_X else vorgabe.kurve_x,
            auto_pause=bool(d.get("auto_pause", vorgabe.auto_pause)),
            tempo_stufen=stufen if stufen in TEMPO_STUFEN else vorgabe.tempo_stufen,
            tempo_niveau=niveaus,
            tempo_eigen=eigene,
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
    "NIVEAUS",
    "NIVEAU_EIGEN",
    "NIVEAU_LANGSAM",
    "NIVEAU_MITTEL",
    "NIVEAU_NAMEN",
    "NIVEAU_SCHNELL",
    "SKALEN",
    "SPALTEN",
    "SPALTEN_TEXT",
    "STANDARD_SPALTEN",
    "TEMPO_FEST",
    "TEMPO_GRENZEN_KMH",
    "TEMPO_GRENZEN_ZAHL",
    "TEMPO_KMH_MAX",
    "TEMPO_RELATIV",
    "TEMPO_STUFEN",
    "TrainingEinstellungen",
    "einstellungen_lesen",
    "einstellungen_schreiben",
    "grenzen_gueltig",
]
