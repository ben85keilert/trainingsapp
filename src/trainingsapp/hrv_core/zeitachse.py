"""Schlagzeiten eines gebündelt zustellenden Geräts — für die Live-Anzeige.

Vorlage: praxis_gui, ``sensors/devices/zeitachse.py`` (``LiveKontinuitaetsuhr``).

Das Problem
===========
Der Polar H10 meldet etwa jede Sekunde 1–2 RR-Intervalle; die Paketankunft ist
ein guter Näherungswert für den letzten Schlag. Die Polar Verity Sense sendet
dagegen in einem ~5-s-Takt rund fünf Intervalle auf einmal, mit 0–1 s Streuung
in der Zustellung (in praxis_gui gemessen: Median 0,55 s, p95 1,3 s). Aus der
Ankunft zurückgerechnet, liegt der erste Schlag eines Pakets darum regelmäßig
**vor** dem letzten des vorigen. Auf der x-Achse der Live-Kurve lief die Zeit
zurück; zusammengeschoben auf 1 ms Abstand standen mehrere verschiedene
Intervalle fast übereinander — die Kurve zeigte senkrechte Zacken, die im
Herzschlag nicht vorkommen.

Die Kontinuitätsuhr
===================
Verlässlich ist die **Summe aller gelieferten Intervalle** — auch der vom Gerät
als unbrauchbar markierten: Das ist die Herzuhr des Geräts. Offen bleibt nur
ihr Versatz zur Uhr der App, und dafür gilt: Ein Schlag kann nie *nach* seiner
Zustellung liegen. Der kleinste beobachtete Wert von (Ankunft − Summe) ist die
beste Schätzung; alles darüber war Wartezeit.

Nur für die Anzeige: ``t_wall_s`` in der Messdatei bleibt die Ankunftsachse
(Vertrag, Abschnitt 3a/3b) — die Rohzutaten dafür stehen in ``ppi_pakete``.
"""

from __future__ import annotations

from collections.abc import Sequence

#: Liegt (Ankunft − Summe) um mehr als das über dem Anker, fehlen Intervalle
#: (Verbindungsabriss, verlorene Pakete) — dann wird neu verankert. Zustellung
#: allein streut darunter (p95 1,3 s).
NEU_ANKERN_S = 3.0


class Kontinuitaetsuhr:
    """Schlagzeiten aus der laufenden Intervallsumme, Paket für Paket.

    Der Anker ist das Minimum von (Ankunft − Intervallsumme) über die letzten
    ``fenster`` Pakete. Abweichend von praxis_gui wird nach einem Verlust
    (Anstieg über `NEU_ANKERN_S`) neu verankert: Sonst schöbe das alte Minimum
    die Schläge nach einer Lücke minutenlang um deren Länge nach links, und die
    Lücke verschwände aus der Kurve.

    >>> uhr = Kontinuitaetsuhr()
    >>> uhr.paket(10.0, [1000, 1000], [True, True])          # 9,0 und 10,0
    [(1000, 9.0), (1000, 10.0)]

    Das nächste Paket kommt 0,6 s zu spät — aus der Ankunft zurückgerechnet
    läge sein erster Schlag bei 11,6; die Uhr setzt ihn auf 11,0:

    >>> uhr.paket(12.6, [1000, 1000], [True, True])
    [(1000, 11.0), (1000, 12.0)]

    Ein blockiertes Intervall hat trotzdem gedauert:

    >>> uhr.paket(14.0, [900, 1100], [False, True])
    [(1100, 14.0)]
    """

    def __init__(self, fenster: int = 60) -> None:
        self._fenster = max(1, int(fenster))
        self._summe_s = 0.0
        self._o: list[float] = []  # Ankunft − Summe je Paket (höchstens fenster)
        self._letzte_t: float | None = None

    def paket(
        self, t_ankunft: float, intervalle_ms: Sequence[int], brauchbar: Sequence[bool]
    ) -> list[tuple[int, float]]:
        """``[(rr_ms, t_schlag)]`` für die **brauchbaren** Intervalle, in Reihenfolge.

        Die Zeiten steigen streng — ein Schlag rutscht nie hinter seinen Vorgänger.
        """
        iv = [int(x or 0) for x in intervalle_ms]
        if not iv:
            return []
        ok = list(brauchbar) + [False] * (len(iv) - len(brauchbar))
        start = self._summe_s
        self._summe_s += sum(iv) / 1000.0
        o = float(t_ankunft) - self._summe_s
        if self._o and o - min(self._o) > NEU_ANKERN_S:
            self._o.clear()
        self._o.append(o)
        if len(self._o) > self._fenster:
            del self._o[0]
        anker = min(self._o)

        out: list[tuple[int, float]] = []
        summe = start
        for x, b in zip(iv, ok, strict=True):
            summe += x / 1000.0
            if not b:
                continue
            t = round(summe + anker, 6)
            if self._letzte_t is not None and t <= self._letzte_t:
                t = self._letzte_t + max(x / 1000.0 * 0.01, 1e-3)
            self._letzte_t = t
            out.append((x, t))
        return out


__all__ = ["NEU_ANKERN_S", "Kontinuitaetsuhr"]
