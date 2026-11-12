"""Die Kurve „Weg über die Zeit“ und die Ablesezeile der Trainings-Auswertung (Ben, 12.11.2026).

x = Minuten seit der ersten Ortung, y = zurückgelegte Kilometer. Eine Pause ist ein
waagrechtes Stück, das Tempo die Steigung — und weil die Zeit nie zurückläuft, liegt auch
bei mehreren Runden nichts übereinander. Die Linie trägt **dieselben Farben wie die Karte**
(Tempo oder Herzfrequenz, `core.strecke_farbe.laeufe`).

`Ablesung` schlägt zu einer Stelle des Trainings (`components.abfahren.Strich`) nach, was
dort war: Zeit, Strecke, Tempo, Herzfrequenz, Höhe — und die Ortung für den Marker der
Karte. Gerechnet wird hier nichts; Strecke je Zeit kommt aus dem `StreckenRechner`.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence

from trainingsapp.core.strecke import RAD, Punkt, StreckenRechner
from trainingsapp.core.strecke_farbe import laeufe
from trainingsapp.core.zeitangabe import dauer_text
from trainingsapp.ui.components.karte_strecke import LINIE, Faerbung
from trainingsapp.ui.components.kurve import Reihe

HINWEIS = "Tippen oder ziehen: Stelle ablesen — die Karte zeigt sie."


def _zahl(wert: float, stellen: int) -> str:
    return f"{wert:.{stellen}f}".replace(".", ",")


def weg_zeit_reihen(r: StreckenRechner, faerbung: Faerbung | None) -> list[Reihe]:
    """Die Linien der Kurve: je Farblauf eine — ohne Färbung eine je Teilstück."""
    t0 = r.erste.t if r.erste is not None else 0.0

    def xy(p: Punkt) -> tuple[float, float]:
        stand = r.stand_bei(p.t)
        return ((p.t - t0) / 60.0, (stand[0] if stand is not None else 0.0) / 1000.0)

    teile: list[tuple[Sequence[Punkt], str]]
    if faerbung is None:
        teile = [(teil, str(LINIE)) for teil in r.teilstuecke]
    else:
        teile = [(stueck, farbe) for stueck, farbe, _ in faerbung]
    return [Reihe([xy(p) for p in lauf], farbe=farbe, breite=3.0) for lauf, farbe in laeufe(teile)]


class Ablesung:
    """Was an einer Stelle des Trainings war.

    Args:
        r: der Rechner der Strecke (Strecke je Zeit, erste und letzte Ortung).
        punkte: alle Ortungen — für Tempo, Höhe und den Marker der Karte.
        herz: Ortungszeit → Schläge/min (nur mit HRV-Aufnahme).
    """

    def __init__(
        self,
        r: StreckenRechner,
        punkte: Sequence[Punkt],
        *,
        sportart: str,
        herz: Mapping[float, int] | None = None,
    ) -> None:
        self.r, self.sportart = r, sportart
        self.herz = herz or {}
        self._punkte = sorted(punkte, key=lambda p: p.t)
        self._zeiten = [p.t for p in self._punkte]
        self.t0 = r.erste.t if r.erste is not None else 0.0
        self.t1 = r.letzter.t if r.letzter is not None else self.t0

    @property
    def dauer_s(self) -> float:
        return self.t1 - self.t0

    def ortung(self, s: float) -> Punkt | None:
        """Die Ortung, die der Zeit ``s`` (seit der ersten) am nächsten liegt."""
        if not self._punkte:
            return None
        t = self.t0 + s
        i = bisect_left(self._zeiten, t)
        if i <= 0:
            return self._punkte[0]
        if i >= len(self._punkte):
            return self._punkte[-1]
        vor, nach = self._punkte[i - 1], self._punkte[i]
        return vor if t - vor.t <= nach.t - t else nach

    def km(self, s: float) -> float | None:
        stand = self.r.stand_bei(self.t0 + s)
        return stand[0] / 1000.0 if stand is not None else None

    def text(self, s: float | None) -> str:
        """„12:30 · 2,31 km · 5:40 /km · 142 bpm · 48 m“ — ohne Strich der Hinweis."""
        if s is None:
            return HINWEIS
        teile = [dauer_text(s)]
        km = self.km(s)
        if km is not None:
            teile.append(f"{_zahl(km, 2)} km")
        p = self.ortung(s)
        if p is not None and p.tempo_ms is not None and p.tempo_ms >= 0.3:
            if self.sportart == RAD:
                teile.append(f"{_zahl(p.tempo_ms * 3.6, 1)} km/h")
            else:
                teile.append(f"{dauer_text(1000.0 / p.tempo_ms)} /km")
        elif p is not None and p.tempo_ms is not None:
            teile.append("Pause")
        if p is not None and (bpm := self.herz.get(p.t)) is not None:
            teile.append(f"{bpm} bpm")
        if p is not None and p.hoehe_m is not None:
            teile.append(f"{round(p.hoehe_m)} m")
        return " · ".join(teile)


__all__ = ["HINWEIS", "Ablesung", "weg_zeit_reihen"]
