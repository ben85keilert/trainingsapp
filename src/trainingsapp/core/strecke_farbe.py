"""Die Strecke in Stücke teilen und nach Tempo oder Herzfrequenz einfärben — die Rechnung.

Ben, 26.10.2026 (P81, ``docs/plan_strecken_ansicht.md`` §3): Die Linie auf der Karte zeigt,
wie schnell man wo war. Statt eines Farbverlaufs über Tausende Stützstellen gibt es **ein
Stück je `SCHRITT_S`** (10 s), jedes mit einem Wert — dem Mittel des Doppler-Tempos seiner
Ortungen (oder der Herzfrequenz) — und daraus einer **Stufe** auf der Farbskala.

Die Skala ist **relativ je Training**: zwischen dem 10. und 90. Perzentil der Werte
(`spanne`). Ein Spaziergang und ein Tempolauf färben sich so beide voll aus, ohne Grenzwerte
je Sportart. Stillstand (unter `STAND_TEMPO_MS`) ist ein eigenes Stück ohne Stufe — die
Karte zeichnet es grau und gepunktet. Keine Farben hier (die stehen in `ui.farben`), nur
Stufen 0 … n−1.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from .strecke import STAND_TEMPO_MS, Punkt

#: Länge eines Stücks (s)
SCHRITT_S: Final[float] = 10.0
#: Perzentile der Spanne — Ausreißer (Tunnel, Ampelsprint) dehnen die Skala nicht
PERZENTIL_UNTEN: Final[float] = 10.0
PERZENTIL_OBEN: Final[float] = 90.0


@dataclass(frozen=True, slots=True)
class Stueck:
    """Ein Abschnitt der Linie: seine Ortungen (die erste des nächsten Stücks noch dazu,
    damit die Linie nicht reißt) und sein Wert — ``None`` ohne Wert, ``pause`` im Stand."""

    punkte: Sequence[Punkt]
    wert: float | None
    pause: bool = False


def stuecke(
    teilstuecke: Sequence[Sequence[Punkt]],
    wert: Callable[[Punkt], float | None],
    *,
    schritt_s: float = SCHRITT_S,
    stand: float | None = STAND_TEMPO_MS,
) -> list[Stueck]:
    """Die Linie in Stücke von ``schritt_s`` — je Teilstück (ein Sprung oder eine Lücke
    beginnt ein neues), der Wert ist das Mittel von ``wert(p)`` über die Ortungen darin.

    ``stand``: liegt der Wert darunter, ist das Stück eine Pause (für die Herzfrequenz
    ``None``).

    >>> pkt = [Punkt(float(i), 52.0, 13.0 + i * 1e-5, tempo_ms=2.0 + (i >= 10) * 1.0)
    ...        for i in range(25)]
    >>> st = stuecke([pkt], lambda p: p.tempo_ms)
    >>> [(len(s.punkte), s.wert) for s in st]
    [(11, 2.0), (11, 3.0), (5, 3.0)]
    >>> stuecke([pkt[:3]], lambda p: 0.1)[0].pause
    True
    """
    aus: list[Stueck] = []
    for teil in teilstuecke:
        if not teil:
            continue
        t0 = teil[0].t
        gruppen: list[list[Punkt]] = []
        for p in teil:
            k = int((p.t - t0) // schritt_s)
            while len(gruppen) <= k:
                gruppen.append([])
            gruppen[k].append(p)
        gruppen = [g for g in gruppen if g]
        for i, g in enumerate(gruppen):
            werte = [w for p in g if (w := wert(p)) is not None]
            mittel = sum(werte) / len(werte) if werte else None
            punkte = list(g) + ([gruppen[i + 1][0]] if i + 1 < len(gruppen) else [])
            pause = stand is not None and mittel is not None and mittel < stand
            aus.append(Stueck(punkte, mittel, pause))
    return aus


def perzentil(werte: Sequence[float], p: float) -> float:
    """Das ``p``-te Perzentil (linear zwischen den Nachbarn).

    >>> perzentil([1, 2, 3, 4, 5], 50), perzentil([1, 2, 3, 4, 5], 90), perzentil([7], 10)
    (3.0, 4.6, 7.0)
    """
    s = sorted(werte)
    if len(s) == 1:
        return float(s[0])
    lage = (len(s) - 1) * p / 100.0
    i = int(lage)
    rest = lage - i
    return float(s[i] + (s[min(i + 1, len(s) - 1)] - s[i]) * rest)


def spanne(stuecke_: Sequence[Stueck]) -> tuple[float, float] | None:
    """Untere und obere Grenze der Farbskala — Perzentile der Werte aller Stücke, die
    nicht Pause sind; ``None`` ohne Wert.

    >>> st = [Stueck([], w) for w in [1.0, 2.0, 2.5, 3.0, 10.0]]
    >>> tuple(round(x, 3) for x in spanne(st))
    (1.4, 7.2)
    >>> spanne([Stueck([], None), Stueck([], 0.1, pause=True)]) is None
    True
    """
    werte = [s.wert for s in stuecke_ if s.wert is not None and not s.pause]
    if not werte:
        return None
    return perzentil(werte, PERZENTIL_UNTEN), perzentil(werte, PERZENTIL_OBEN)


def stufe(wert: float, grenzen: tuple[float, float], n: int) -> int:
    """Die Stufe 0 … n−1 eines Werts auf der Skala — darunter 0, darüber n−1; ohne Spanne
    (alle gleich) die Mitte.

    >>> [stufe(w, (2.0, 4.0), 5) for w in (1.0, 2.0, 2.9, 3.5, 4.0, 9.0)]
    [0, 0, 2, 3, 4, 4]
    >>> stufe(3.0, (3.0, 3.0), 5)
    2
    """
    unten, oben = grenzen
    if oben <= unten:
        return n // 2
    anteil = (wert - unten) / (oben - unten)
    return min(n - 1, max(0, int(anteil * n)))


def gestuft(
    stuecke_: Sequence[Stueck], n: int, grenzen: tuple[float, float] | None = None
) -> list[tuple[Stueck, int | None]]:
    """Jedes Stück mit seiner Stufe — ``None`` für Pausen und Stücke ohne Wert.

    >>> st = stuecke([[Punkt(float(i), 52.0, 13.0, tempo_ms=2.0) for i in range(40)]],
    ...              lambda p: p.tempo_ms)
    >>> [s for _, s in gestuft(st, 3)]  # alle gleich schnell: die Mitte
    [1, 1, 1, 1]
    >>> [s for _, s in gestuft(st, 3, grenzen=(2.0, 4.0))]
    [0, 0, 0, 0]
    """
    grenzen = grenzen if grenzen is not None else spanne(stuecke_)
    aus: list[tuple[Stueck, int | None]] = []
    for s in stuecke_:
        if s.pause or s.wert is None or grenzen is None:
            aus.append((s, None))
        else:
            aus.append((s, stufe(s.wert, grenzen, n)))
    return aus


def tempo_s_pro_km(ms: float) -> float | None:
    """m/s → s/km (``None`` im Stand).

    >>> tempo_s_pro_km(2.5), tempo_s_pro_km(0.0)
    (400.0, None)
    """
    return 1000.0 / ms if ms > 0 else None


__all__ = [
    "PERZENTIL_OBEN",
    "PERZENTIL_UNTEN",
    "SCHRITT_S",
    "Stueck",
    "gestuft",
    "perzentil",
    "spanne",
    "stuecke",
    "stufe",
    "tempo_s_pro_km",
]
