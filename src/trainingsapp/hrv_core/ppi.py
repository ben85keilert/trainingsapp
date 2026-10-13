"""PPI-Rohpakete einer Messung den Zeilen von ``messungen`` zuordnen.

Die Verity Sense markiert unbrauchbare Intervalle selbst (Blocker-Bit). In
``messungen`` stehen nur die brauchbaren — wie bei praxis_gui. Was dort fehlt,
ist die Spur, **wo** Intervalle verworfen wurden: Zwei aufeinanderfolgende
Zeilen sind dann keine Nachbarn, und eine Differenz zwischen ihnen ist keine
Schlag-zu-Schlag-Differenz. Bei einer Messung in Bewegung (13.10.2026, 80 %
blockiert) stieg RMSSD dadurch von 100 auf 158 ms.

Die vollständige Folge steht in ``ppi_pakete`` (Vertrag, Abschnitt 3b): alle
Intervalle samt Blocker-Bit und Fehlerschätzung. Daraus entsteht je Zeile
`PpiZeile` — ob davor verworfen wurde und wie sicher das Gerät sich war.
"""

from __future__ import annotations

from dataclasses import dataclass

from .recording import Recording


@dataclass(frozen=True, slots=True)
class PpiZeile:
    """Was ``ppi_pakete`` über eine Zeile von ``messungen`` verrät."""

    #: Vom Gerät verworfene Intervalle zwischen der vorigen Zeile und dieser
    verworfen_davor: int
    #: Fehlerschätzung des Geräts für dieses Intervall (ms)
    fehler_ms: int


def ppi_zeilen(rec: Recording) -> list[PpiZeile] | None:
    """Je Zeile von ``messungen`` eine `PpiZeile` — oder ``None``.

    ``None`` heißt: kein ``ppi_pakete``-Block, oder seine brauchbaren
    Intervalle ergeben nicht genau die ``rr_ms``-Folge der Zeilen (beschnittene
    oder fremde Datei). Dann ist keine Zuordnung möglich, und es wird nicht
    geraten. Brauchbar heißt wie beim Schreiben: kein Blocker und ``ppi_ms > 0``.

    >>> from trainingsapp.hrv_core.recording import Beat
    >>> pakete = [{"t_wall_s": 3.0, "ppi_ms": [800, 810, 820], "fehler_ms": [5, 9, 7],
    ...            "blocker": [0, 1, 0], "kontakt": [1, 1, 1]}]
    >>> rec = Recording(beats=[Beat(0.8, 800), Beat(1.62, 820)], ppi_pakete=pakete)
    >>> ppi_zeilen(rec)
    [PpiZeile(verworfen_davor=0, fehler_ms=5), PpiZeile(verworfen_davor=1, fehler_ms=7)]
    >>> ppi_zeilen(Recording(beats=[Beat(0.8, 800)], ppi_pakete=pakete)) is None
    True
    """
    paare = _intervalle(rec)
    if paare is None:
        return None
    zeilen: list[PpiZeile] = []
    brauchbar: list[int] = []
    verworfen = 0
    for wert, fehler, blocker in paare:
        if blocker or wert <= 0:
            verworfen += 1
            continue
        zeilen.append(PpiZeile(verworfen_davor=verworfen, fehler_ms=fehler))
        brauchbar.append(wert)
        verworfen = 0
    if brauchbar != [b.rr_ms for b in rec.beats]:
        return None
    return zeilen


def _intervalle(rec: Recording) -> list[tuple[int, int, int]] | None:
    """Alle Intervalle aus ``ppi_pakete`` als ``(ppi_ms, fehler_ms, blocker)``, in Folge.

    Defensiv: Fehlt eine Spalte, gilt 0; ist der Block kaputt, ``None``.
    """
    if not rec.ppi_pakete:
        return None
    out: list[tuple[int, int, int]] = []
    try:
        for paket in rec.ppi_pakete:
            ppi = [int(x or 0) for x in paket.get("ppi_ms") or []]
            fehler = [int(x or 0) for x in paket.get("fehler_ms") or []]
            blocker = [int(x or 0) for x in paket.get("blocker") or []]
            fehler += [0] * (len(ppi) - len(fehler))
            blocker += [0] * (len(ppi) - len(blocker))
            out += zip(ppi, fehler[: len(ppi)], blocker[: len(ppi)], strict=True)
    except (TypeError, ValueError, AttributeError):
        return None
    return out


def ppi_naehte(rec: Recording) -> list[int]:
    """Zeilenindizes, vor denen das Gerät Intervalle verworfen hat — dort ist eine Naht.

    >>> from trainingsapp.hrv_core.recording import Beat
    >>> pakete = [{"t_wall_s": 4.0, "ppi_ms": [800, 810, 820, 830], "fehler_ms": [5] * 4,
    ...            "blocker": [1, 0, 1, 0], "kontakt": [1] * 4}]
    >>> ppi_naehte(Recording(beats=[Beat(0.81, 810), Beat(1.64, 830)], ppi_pakete=pakete))
    [1]

    Verworfenes vor der ersten Zeile ist keine Naht — davor gibt es nichts.
    """
    zeilen = ppi_zeilen(rec)
    if zeilen is None:
        return []
    return [i for i, z in enumerate(zeilen) if i > 0 and z.verworfen_davor > 0]


def ppi_verworfen(rec: Recording) -> tuple[int, int] | None:
    """``(verworfen, gesamt)`` über alle Intervalle in ``ppi_pakete`` — ``None`` ohne Block.

    >>> ppi_verworfen(Recording(ppi_pakete=[{"ppi_ms": [800, 0, 810], "blocker": [1, 0, 0]}]))
    (2, 3)
    """
    paare = _intervalle(rec)
    if paare is None:
        return None
    return sum(1 for wert, _, blocker in paare if blocker or wert <= 0), len(paare)


__all__ = ["PpiZeile", "ppi_naehte", "ppi_verworfen", "ppi_zeilen"]
