"""Zeit eintragen, wenn der Timer einer Übung fertig ist (Ben, 17.10.2026).

Ist der Timer einer Übung durch, gilt die Übung als **gemacht**, und ihre Zeit kommt
ins Tagebuch — als **Haltezeit je Satz** (`hold`) oder als **Zeit gesamt**
(`duration`), je nachdem, was die Planübung anbietet. Gerechnet wird aus der
Zeitleiste der Einheit (`core.einheit.Ereignis`), nicht aus dem Profil:

- „Weiter“ und „Fertig“ kürzen einen Abschnitt — eingetragen wird die gelaufene Zeit.
- Eine Pause zählt nicht; geht es im selben Abschnitt weiter, zählt er weiter.
- Was kürzer als `core.einheit.MIN_MARKE_S` lief, fällt weg (versehentliches
  „Weiter“) — wie bei den Marken in der Messung.
- Nur Abschnitte, die **zählen** (`core.timer.Abschnitt.zaehlt`); erst einmal zählt
  alles, die App rät nicht aus dem Namen.
- **Abgebrochen** (`core.timer.TimerLauf.abbrechen`) → kein Eintrag.

Rein, ohne Datenbank: Speichern bleibt beim Aufrufer (``data``, ``ui``).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .einheit import MIN_MARKE_S, Ereignis

#: Die Zeitfelder, die der Timer füllen kann — in dieser Reihenfolge der Vorgabe
ZEITFELDER: tuple[str, ...] = ("hold", "duration")


@dataclass(frozen=True, slots=True)
class Gelaufen:
    """Ein Abschnitt, wie er wirklich lief."""

    #: „Halten“ — ohne Runde
    name: str
    runde: int
    #: Laufzeit ohne Pausen (s)
    sekunden: float
    zaehlt: bool
    #: Anfang und Ende auf der Achse der Einheit (``t_s``)
    von_s: float
    bis_s: float


def abgebrochen(ereignisse: Iterable[Ereignis]) -> bool:
    """Endete der Timer mit „Abbrechen“?

    >>> abgebrochen([Ereignis(9.0, "timer", "ende", "", {"grund": "abgebrochen"})])
    True
    >>> abgebrochen([Ereignis(9.0, "timer", "ende", "Timer fertig")])
    False
    """
    return any(
        e.quelle == "timer" and e.art == "ende" and e.daten.get("grund") == "abgebrochen"
        for e in ereignisse
    )


def gelaufene_zeiten(
    ereignisse: Iterable[Ereignis], *, min_s: float = MIN_MARKE_S
) -> list[Gelaufen]:
    """Je Abschnitt des Timers die gelaufene Zeit — aus der Zeitleiste, in ihrer Folge.

    >>> def ab(t, name, runde=1, zaehlt=True):
    ...     d = {"name": name, "runde": runde, "von": 3}
    ...     return Ereignis(t, "timer", "abschnitt", name, d if zaehlt else {**d, "zaehlt": False})
    >>> zeiten = gelaufene_zeiten([
    ...     ab(0.0, "Halten"), Ereignis(40.0, "timer", "pause"),
    ...     Ereignis(70.0, "timer", "weiter", "", {"name": "Halten"}),
    ...     ab(90.0, "Pause", zaehlt=False),   # Halten: 40 s + 20 s
    ...     ab(120.0, "Halten", 2), ab(122.0, "Pause", 2, zaehlt=False),  # 2 s: fällt weg
    ...     Ereignis(150.0, "timer", "ende", "Timer fertig")])
    >>> [(z.name, z.runde, z.sekunden, z.zaehlt) for z in zeiten]
    [('Halten', 1, 60.0, True), ('Pause', 1, 30.0, False), ('Pause', 2, 28.0, False)]
    """
    fertig: list[Gelaufen] = []
    offen: dict[str, Any] | None = None  # name, runde, zaehlt, von_s, summe, lauf_seit

    def schliessen(t: float) -> None:
        nonlocal offen
        if offen is None:
            return
        summe = offen["summe"] + (t - offen["lauf_seit"] if offen["lauf_seit"] is not None else 0)
        if summe >= min_s:
            fertig.append(
                Gelaufen(
                    offen["name"],
                    offen["runde"],
                    round(summe, 3),
                    offen["zaehlt"],
                    offen["von_s"],
                    t,
                )
            )
        offen = None

    for e in ereignisse:
        if e.quelle != "timer":
            continue
        d = e.daten
        if e.art == "abschnitt":
            schliessen(e.t_s)
            offen = {
                "name": str(d.get("name") or e.text),
                "runde": int(d.get("runde") or 1),
                "zaehlt": d.get("zaehlt") is not False,
                "von_s": e.t_s,
                "summe": 0.0,
                "lauf_seit": e.t_s,
            }
        elif e.art == "pause" and offen is not None and offen["lauf_seit"] is not None:
            offen["summe"] += e.t_s - offen["lauf_seit"]
            offen["lauf_seit"] = None
        elif e.art == "weiter" and offen is not None and offen["lauf_seit"] is None:
            offen["lauf_seit"] = e.t_s
        elif e.art == "ende":
            if offen is not None and offen["lauf_seit"] is None:
                offen["lauf_seit"] = e.t_s  # angehalten beendet: die Pause zählt nicht
            schliessen(e.t_s)
            break
    return fertig


def zeitfeld(felder: Iterable[str], gemerkt: str | None = None) -> str | None:
    """Welches Feld der Timer füllt: das, das die Planübung anbietet; bietet sie beide,
    das gemerkte (Knopf im Timer), sonst die Haltezeit. Keins → nur „gemacht“.

    >>> zeitfeld(["reps", "hold"]), zeitfeld(["duration", "hold"], "duration"), zeitfeld(["reps"])
    ('hold', 'duration', None)
    """
    angeboten = [f for f in ZEITFELDER if f in set(felder)]
    if not angeboten:
        return None
    return gemerkt if gemerkt in angeboten else angeboten[0]


def ergebnis(zeiten: Sequence[Gelaufen], feld: str | None) -> dict[str, Any]:
    """Was ins Tagebuch kommt — leer heißt „gemacht“ (ohne Zeitfeld oder ohne Zeit).

    Haltezeit: ein Wert je zählendem Abschnitt (Sätze). Zeit gesamt: die Summe der
    zählenden Abschnitte — mit der Vorgabe „alles zählt“ also die Laufzeit.

    >>> zeiten = [Gelaufen("Halten", 1, 58.4, True, 0, 58.4),
    ...           Gelaufen("Pause", 1, 30.0, False, 58.4, 88.4),
    ...           Gelaufen("Halten", 2, 60.0, True, 88.4, 148.4)]
    >>> ergebnis(zeiten, "hold"), ergebnis(zeiten, "duration"), ergebnis(zeiten, None)
    ({'hold': [58, 60]}, {'duration': 118}, {})
    """
    zaehlend = [z for z in zeiten if z.zaehlt]
    if feld == "hold" and zaehlend:
        return {"hold": [round(z.sekunden) for z in zaehlend]}
    if feld == "duration" and (summe := round(sum(z.sekunden for z in zaehlend))) > 0:
        return {"duration": summe}
    return {}


__all__ = ["ZEITFELDER", "Gelaufen", "abgebrochen", "ergebnis", "gelaufene_zeiten", "zeitfeld"]
