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

Für die Kurve liefert `ppi_folge` dieselbe Folge mit Zeit: Die Summe **aller**
Intervalle ist die Herzuhr des Geräts. ``t_s`` in ``messungen`` summiert nur
die brauchbaren — bei 44 % verworfenen Intervallen (13.10.2026, in Ruhe) zeigte
die Kurve 2:00 statt der gemessenen 3:34, und jede Lücke war zugeschoben.
"""

from __future__ import annotations

import functools
import weakref
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .recording import Beat, Recording
from .segments import luecken_finden

#: Abgeleitete Reihen je Messung (`_gemerkt`) — so viele Messungen merkt sich das Modul
_MERK_MAX = 4
_merk: OrderedDict[int, tuple[weakref.ref[Recording], tuple[int, ...], dict[str, Any]]] = (
    OrderedDict()
)


def _vergessen(schluessel: int) -> None:
    """Die Messung ist weg (Weakref-Rückruf): ihre Reihen auch — sofern unter dem
    Schlüssel nicht schon eine neue Messung mit derselben ``id`` liegt."""
    eintrag = _merk.get(schluessel)
    if eintrag is not None and eintrag[0]() is None:
        del _merk[schluessel]


def _gemerkt[T](rec: Recording, name: str, rechnen: Callable[[], T]) -> T:
    """``rechnen()`` einmal je Messung — beim Öffnen einer Verity-Aufzeichnung entstanden
    dieselben Reihen 6- bis 18-mal (14.10.2026: zusammen ~0,27 s bei 73 min).

    Gemerkt wird je Objekt (Identität, kein Vergleich der Inhalte); ändern sich
    ``ppi_pakete`` oder ``beats`` (anderes Objekt, andere Länge), gilt es als neu.
    Die Messung selbst hält der Speicher nur schwach (`weakref`): Mit der Ansicht
    verschwinden auch ihre Reihen — bei Stundenmessungen am Handy zweistellige MB.
    """
    stempel = (
        id(rec.ppi_pakete),
        len(rec.ppi_pakete) if rec.ppi_pakete is not None else -1,
        id(rec.beats),
        len(rec.beats),
    )
    schluessel = id(rec)
    eintrag = _merk.get(schluessel)
    if eintrag is None or eintrag[0]() is not rec or eintrag[1] != stempel:
        rueckruf = functools.partial(_vergessen, schluessel)
        eintrag = (weakref.ref(rec, lambda _r: rueckruf()), stempel, {})
        _merk[schluessel] = eintrag
        while len(_merk) > _MERK_MAX:
            _merk.popitem(last=False)
    else:
        _merk.move_to_end(schluessel)
    werte = eintrag[2]
    if name not in werte:
        werte[name] = rechnen()
    return werte[name]


@dataclass(frozen=True, slots=True)
class PpiZeile:
    """Was ``ppi_pakete`` über eine Zeile von ``messungen`` verrät."""

    #: Vom Gerät verworfene Intervalle zwischen der vorigen Zeile und dieser
    verworfen_davor: int
    #: Fehlerschätzung des Geräts für dieses Intervall (ms)
    fehler_ms: int


@dataclass(frozen=True, slots=True)
class PpiIntervall:
    """Ein Intervall aus ``ppi_pakete`` auf der Herzuhr des Geräts."""

    #: Ende des Intervalls: Beginn der Messung + Summe aller Intervalle bis hier (s)
    t_s: float
    ppi_ms: int
    fehler_ms: int
    #: Wie beim Schreiben: kein Blocker und ``ppi_ms > 0`` — steht in ``messungen``
    brauchbar: bool


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
    zeilen = _gemerkt(rec, "zeilen", lambda: _ppi_zeilen(rec))
    return None if zeilen is None else list(zeilen)


def _ppi_zeilen(rec: Recording) -> list[PpiZeile] | None:
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
    Gemerkt je Messung (`_gemerkt`); niemand verändert die Liste.
    """
    return _gemerkt(rec, "intervalle", lambda: _intervalle_lesen(rec))


def _intervalle_lesen(rec: Recording) -> list[tuple[int, int, int]] | None:
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


def ppi_folge(rec: Recording) -> list[PpiIntervall] | None:
    """Alle Intervalle in Folge, mit Zeit auf der Herzuhr des Geräts — oder ``None``.

    ``None`` unter denselben Bedingungen wie `ppi_zeilen`: Nur wenn die
    brauchbaren Intervalle genau die Zeilen von ``messungen`` sind, gehören die
    Zeiten zu ihnen. Die Uhr beginnt beim Beginn des ersten Zeilenintervalls
    (wie ``t_s``); davor Verworfenes verschiebt die Zeilen nach hinten.

    >>> from trainingsapp.hrv_core.recording import Beat
    >>> pakete = [{"t_wall_s": 3.0, "ppi_ms": [800, 810, 820], "fehler_ms": [5, 9, 7],
    ...            "blocker": [0, 1, 0], "kontakt": [1, 1, 1]}]
    >>> rec = Recording(beats=[Beat(0.8, 800), Beat(1.62, 820)], ppi_pakete=pakete)
    >>> [(p.t_s, p.ppi_ms, p.brauchbar) for p in ppi_folge(rec)]
    [(0.8, 800, True), (1.61, 810, False), (2.43, 820, True)]
    """
    folge = _gemerkt(rec, "folge", lambda: _ppi_folge(rec))
    return None if folge is None else list(folge)


def _ppi_folge(rec: Recording) -> list[PpiIntervall] | None:
    paare = _intervalle(rec)
    if paare is None or ppi_zeilen(rec) is None or not rec.beats:
        return None
    t = float(rec.beats[0].t_s) - float(rec.beats[0].rr_ms) / 1000.0
    folge: list[PpiIntervall] = []
    for wert, fehler, blocker in paare:
        t += max(wert, 0) / 1000.0
        folge.append(PpiIntervall(round(t, 4), wert, fehler, not blocker and wert > 0))
    return folge


def schlagzeiten(rec: Recording) -> list[float]:
    """Zeit je Zeile von ``messungen`` — auf der Herzuhr aller Intervalle, sonst ``t_s``.

    >>> from trainingsapp.hrv_core.recording import Beat
    >>> pakete = [{"ppi_ms": [800, 810, 820], "blocker": [0, 1, 0]}]
    >>> schlagzeiten(Recording(beats=[Beat(0.8, 800), Beat(1.62, 820)], ppi_pakete=pakete))
    [0.8, 2.43]
    >>> schlagzeiten(Recording(beats=[Beat(0.8, 800), Beat(1.62, 820)]))
    [0.8, 1.62]
    """
    return list(_gemerkt(rec, "schlagzeiten", lambda: _schlagzeiten(rec)))


def _schlagzeiten(rec: Recording) -> list[float]:
    folge = ppi_folge(rec)
    if folge is None:
        return [float(b.t_s) for b in rec.beats]
    return [p.t_s for p in folge if p.brauchbar]


def messluecken(rec: Recording) -> list[int]:
    """Messlücken (`segments.luecken_finden`) — bei PPI auf der Herzuhr aller Intervalle.

    Die Lückenerkennung vergleicht Wanduhr und Herzuhr. ``t_s`` zählt die vom
    Gerät verworfenen Intervalle nicht mit, die Divergenz wüchse mit jedem
    davon, und ein Blocker-Lauf von 4 s sähe aus wie ein Verbindungsabriss —
    13.10.2026: 11 Scheinlücken in 3½ Minuten Ruhemessung. Ohne ``ppi_pakete``
    ist es `luecken_finden` auf den Zeilen.
    """
    achse = schlagzeiten(rec)
    return luecken_finden([replace(b, t_s=t) for b, t in zip(rec.beats, achse, strict=True)])


@dataclass(frozen=True, slots=True)
class Wiederaufnahme:
    """Eine Messung, in der die Verwerfungen des Sensors aufgehoben sind."""

    #: Alle Intervalle aus ``ppi_pakete`` mit ``ppi_ms > 0`` als Zeilen
    rec: Recording
    #: Je Zeile von ``rec``: Zeile der Rohdatei — ``None`` = vom Sensor verworfen
    zeile: list[int | None]

    @property
    def aufgenommen(self) -> int:
        """Wie viele vom Sensor verworfene Intervalle wieder aufgenommen sind."""
        return sum(z is None for z in self.zeile)


def ohne_verwerfung(rec: Recording) -> Wiederaufnahme | None:
    """Die Messung mit **allen** Intervallen des Sensors — oder ``None`` ohne `ppi_folge`.

    Die Verity Sense verwirft Intervalle, die sich in Verteilung und
    Fehlerschätzung nicht von den behaltenen unterscheiden (13.10.2026: 37 %
    in Ruhe). Hier kommen sie zurück — als ganz normale Zeilen, über die die
    Automatik (`korrektur.automatisch`) wie über jede andere urteilt.

    - Zeilen der Rohdatei bleiben, wie sie sind; nur ``t_s`` ist die Herzuhr
      aller Intervalle (`schlagzeiten`).
    - Wieder aufgenommene Intervalle bekommen die Wanduhr ihres Pakets nach
      Regel 3a.4 (Ankunft für das letzte, rückwärts gerechnet für frühere)
      und die Herzfrequenz der Zeile davor.
    - ``ppi_pakete`` trägt keine Blocker mehr: Die Zuordnung (`ppi_zeilen`)
      passt auf die neuen Zeilen, Nähte gibt es nur noch an ``ppi_ms = 0``.

    >>> pakete = [{"t_wall_s": 3.0, "ppi_ms": [800, 810, 820], "fehler_ms": [5, 9, 7],
    ...            "blocker": [0, 1, 0], "kontakt": [1, 1, 1]}]
    >>> rec = Recording(beats=[Beat(0.8, 800, 70, 1.37, "r"), Beat(1.62, 820, 71, 3.0)],
    ...                 ppi_pakete=pakete)
    >>> w = ohne_verwerfung(rec)
    >>> [(b.t_s, b.rr_ms, b.hf_bpm, b.t_wall_s, b.tw_src) for b in w.rec.beats]
    [(0.8, 800, 70, 1.37, 'r'), (1.61, 810, 70, 2.18, 'r'), (2.43, 820, 71, 3.0, 'm')]
    >>> w.zeile, w.aufgenommen, ppi_naehte(w.rec)
    ([0, None, 1], 1, [])
    """
    folge = ppi_folge(rec)
    if folge is None or rec.ppi_pakete is None:
        return None
    wand = _wanduhr(rec.ppi_pakete)
    beats: list[Beat] = []
    zeile: list[int | None] = []
    r = 0
    hf = rec.beats[0].hf_bpm
    for j, p in enumerate(folge):
        if p.brauchbar:
            b = rec.beats[r]
            beats.append(replace(b, t_s=p.t_s))
            zeile.append(r)
            hf = b.hf_bpm
            r += 1
        elif p.ppi_ms > 0:
            t_wand, quelle = wand[j] if j < len(wand) else (None, "r")
            beats.append(Beat(p.t_s, p.ppi_ms, hf, t_wand, quelle))
            zeile.append(None)
    pakete = [
        {**paket, "blocker": [0] * len(paket.get("ppi_ms") or [])} for paket in rec.ppi_pakete
    ]
    return Wiederaufnahme(replace(rec, beats=beats, ppi_pakete=pakete), zeile)


def _wanduhr(pakete: list[dict]) -> list[tuple[float | None, str]]:
    """Wanduhr je Intervall aus ``ppi_pakete`` — wie der Schreiber (Vertrag 3a.4).

    Das letzte Intervall eines Pakets bekommt die Ankunft (``"m"``), frühere
    die Ankunft minus die Summe der späteren (``"r"``), verworfene inklusive.
    """
    out: list[tuple[float | None, str]] = []
    for paket in pakete:
        werte = [max(int(x or 0), 0) for x in paket.get("ppi_ms") or []]
        ankunft = paket.get("t_wall_s")
        rest = 0
        teil: list[tuple[float | None, str]] = []
        for k in range(len(werte) - 1, -1, -1):
            if ankunft is None:
                teil.append((None, "r"))
            else:
                teil.append(
                    (round(float(ankunft) - rest / 1000.0, 3), "m" if k == len(werte) - 1 else "r")
                )
            rest += werte[k]
        out += reversed(teil)
    return out


def ppi_verworfen(rec: Recording) -> tuple[int, int] | None:
    """``(verworfen, gesamt)`` über alle Intervalle in ``ppi_pakete`` — ``None`` ohne Block.

    >>> ppi_verworfen(Recording(ppi_pakete=[{"ppi_ms": [800, 0, 810], "blocker": [1, 0, 0]}]))
    (2, 3)
    """
    paare = _intervalle(rec)
    if paare is None:
        return None
    return sum(1 for wert, _, blocker in paare if blocker or wert <= 0), len(paare)


__all__ = [
    "PpiIntervall",
    "PpiZeile",
    "Wiederaufnahme",
    "messluecken",
    "ohne_verwerfung",
    "ppi_folge",
    "ppi_naehte",
    "ppi_verworfen",
    "ppi_zeilen",
    "schlagzeiten",
]
