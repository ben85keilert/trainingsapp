"""Zeit eintragen, wenn der Timer einer Übung fertig ist (Ben, 17.10.2026).

Ist der Timer einer Übung durch, gilt die Übung als **gemacht**, und ihre Zeit kommt
ins Tagebuch — als **Haltezeit je Satz** (`hold`) oder als **Zeit**
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

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .einheit import AUSFUEHRUNG_SCHLUESSEL, MIN_MARKE_S, Ereignis, ganzzahl_lesen

#: Die Zeitfelder, die der Timer füllen kann — in dieser Reihenfolge der Vorgabe
from .result_spec import basis_key

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
    #: der Abschnitt, in dem der Timer gerade steht (``jetzt_s``) — noch nicht zu Ende
    laeuft: bool = False
    #: die Ausführung dieser Runde (`core.timer.Abschnitt.ausfuehrung`) als Paare — leer = wie
    #: im Block gewählt (`docs/plan_uhr_fokus.md` §3)
    ausfuehrung: tuple[tuple[str, Any], ...] = ()


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
    ereignisse: Iterable[Ereignis], *, min_s: float = MIN_MARKE_S, jetzt_s: float | None = None
) -> list[Gelaufen]:
    """Je Abschnitt des Timers die gelaufene Zeit — aus der Zeitleiste, in ihrer Folge.

    ``jetzt_s``: Der Timer läuft noch — sein Abschnitt kommt bis dahin dazu (``laeuft``),
    auch unter ``min_s`` (Tabelle „Intervalle“ im Ausdauertraining).

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
    >>> [(z.name, z.sekunden, z.laeuft) for z in gelaufene_zeiten([ab(0.0, "Halten"),
    ...     ab(60.0, "Pause", zaehlt=False)], jetzt_s=63.0)]
    [('Halten', 60.0, False), ('Pause', 3.0, True)]
    """
    fertig: list[Gelaufen] = []
    offen: dict[str, Any] | None = None  # name, runde, zaehlt, von_s, summe, lauf_seit

    def schliessen(t: float, *, laeuft: bool = False) -> None:
        nonlocal offen
        if offen is None:
            return
        summe = offen["summe"] + (t - offen["lauf_seit"] if offen["lauf_seit"] is not None else 0)
        if summe >= min_s or laeuft:
            fertig.append(
                Gelaufen(
                    offen["name"],
                    offen["runde"],
                    round(summe, 3),
                    offen["zaehlt"],
                    offen["von_s"],
                    t,
                    laeuft,
                    offen["ausfuehrung"],
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
                "runde": max(1, ganzzahl_lesen(d.get("runde"), 1)),
                "zaehlt": d.get("zaehlt") is not False,
                "von_s": e.t_s,
                "summe": 0.0,
                "lauf_seit": e.t_s,
                # flach wie an der Beteiligung (`devices.einheit.kontext_daten`)
                "ausfuehrung": tuple(
                    (k, d[k]) for k in AUSFUEHRUNG_SCHLUESSEL if d.get(k) not in (None, "")
                ),
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
    else:
        if jetzt_s is not None and offen is not None:
            schliessen(max(jetzt_s, offen["von_s"]), laeuft=True)
    return fertig


def zeitfeld(felder: Iterable[str], gemerkt: str | None = None) -> str | None:
    """Welches Feld der Timer füllt: das, das die Planübung anbietet; bietet sie beide,
    das gemerkte (Knopf im Timer), sonst die Haltezeit. Keins → nur „gemacht“.

    >>> zeitfeld(["reps", "hold"]), zeitfeld(["duration", "hold"], "duration"), zeitfeld(["reps"])
    ('hold', 'duration', None)
    >>> zeitfeld(["reps", "hold_2"]), zeitfeld(["hold", "hold_2"], "hold_2")
    ('hold_2', 'hold_2')
    """
    angeboten = [f for f in felder if basis_key(f) in ZEITFELDER]
    angeboten.sort(key=lambda f: ZEITFELDER.index(basis_key(f)))
    if not angeboten:
        return None
    return gemerkt if gemerkt in angeboten else angeboten[0]


def ergebnis(zeiten: Sequence[Gelaufen], feld: str | None) -> dict[str, Any]:
    """Was ins Tagebuch kommt — leer heißt „gemacht“ (ohne Zeitfeld oder ohne Zeit).

    Haltezeit: ein Wert je zählendem Abschnitt (Sätze). Zeit: die Summe der
    zählenden Abschnitte — mit der Vorgabe „alles zählt“ also die Laufzeit.

    >>> zeiten = [Gelaufen("Halten", 1, 58.4, True, 0, 58.4),
    ...           Gelaufen("Pause", 1, 30.0, False, 58.4, 88.4),
    ...           Gelaufen("Halten", 2, 60.0, True, 88.4, 148.4)]
    >>> ergebnis(zeiten, "hold"), ergebnis(zeiten, "duration"), ergebnis(zeiten, None)
    ({'hold': [58, 60]}, {'duration': 118}, {})
    """
    zaehlend = [z for z in zeiten if z.zaehlt]
    art = basis_key(feld) if feld else None
    if art == "hold" and zaehlend and feld:
        return {feld: [round(z.sekunden) for z in zaehlend]}
    if art == "duration" and feld and (summe := round(sum(z.sekunden for z in zaehlend))) > 0:
        return {feld: summe}
    return {}


def nach_ausfuehrung(zeiten: Sequence[Gelaufen]) -> list[tuple[dict[str, Any], list[Gelaufen]]]:
    """Die zählenden Abschnitte je Ausführung, in der Folge ihres ersten Auftretens (Ben,
    8.11.2026: „1 min links, 2 min rechts, 30 s beide“ — je Ausführung ein Eintrag). Ohne
    Ausführung an den Abschnitten eine Gruppe ``{}`` mit allen Zeiten (wie bisher).

    >>> L, R = (("variant", "links"),), (("variant", "rechts"),)
    >>> zeiten = [Gelaufen("Links", 1, 60.0, True, 0, 60, ausfuehrung=L),
    ...           Gelaufen("Pause", 1, 15.0, False, 60, 75),
    ...           Gelaufen("Rechts", 1, 120.0, True, 75, 195, ausfuehrung=R),
    ...           Gelaufen("Links", 2, 58.0, True, 195, 253, ausfuehrung=L)]
    >>> [(a, [z.sekunden for z in g]) for a, g in nach_ausfuehrung(zeiten)]
    [({'variant': 'links'}, [60.0, 58.0]), ({'variant': 'rechts'}, [120.0])]
    >>> [(a, len(g)) for a, g in nach_ausfuehrung(zeiten[1:2])]
    [({}, 1)]
    """
    if not any(z.ausfuehrung for z in zeiten):
        return [({}, list(zeiten))]
    gruppen: dict[tuple[tuple[str, Any], ...], list[Gelaufen]] = {}
    for z in zeiten:
        if z.zaehlt:
            gruppen.setdefault(z.ausfuehrung, []).append(z)
    return [(dict(a), g) for a, g in gruppen.items()] or [({}, list(zeiten))]


def ausfuehrung_bei(zeiten: Sequence[Gelaufen], t_s: float) -> dict[str, Any]:
    """Die Ausführung des Abschnitts, in dem ``t_s`` lag — für Wiederholungen und Eingaben,
    die zu einer Runde gehören. Ein Satz endet mit seinem Abschnitt: das Ende zählt dazu.

    >>> zeiten = [Gelaufen("L", 1, 60.0, True, 0, 60, ausfuehrung=(("variant", "links"),)),
    ...           Gelaufen("R", 1, 60.0, True, 60, 120, ausfuehrung=(("variant", "rechts"),))]
    >>> ausfuehrung_bei(zeiten, 30), ausfuehrung_bei(zeiten, 60), ausfuehrung_bei(zeiten, 200)
    ({'variant': 'links'}, {'variant': 'links'}, {'variant': 'rechts'})
    """
    for z in zeiten:
        if z.von_s < t_s <= z.bis_s + 0.5:
            return dict(z.ausfuehrung)
    vorher = [z for z in zeiten if z.von_s <= t_s]
    return dict(vorher[-1].ausfuehrung) if vorher else {}


def stelle(zeiten: Sequence[Gelaufen], t_s: float) -> int:
    """Der Abschnitt (Index in ``zeiten``), zu dem eine Eingabe um ``t_s`` gehört — der, in dem
    sie lag (das Ende zählt dazu), sonst der letzte davor. In einer Pause (zählt nicht) gehört
    sie zum Satz davor — man trägt dort ein, was man eben gemacht hat —, vor dem ersten Satz zum
    ersten. Ohne zählenden Abschnitt der, in dem sie lag (Stoppuhr ohne Zeit).

    >>> z = [Gelaufen("Vor", 1, 5.0, False, 0, 5), Gelaufen("H", 1, 30.0, True, 5, 35),
    ...      Gelaufen("P", 1, 10.0, False, 35, 45), Gelaufen("H", 2, 30.0, True, 45, 75)]
    >>> [stelle(z, t) for t in (2, 20, 40, 60, 99)]
    [1, 1, 1, 3, 3]
    """
    hier = next((i for i, z in enumerate(zeiten) if z.von_s < t_s <= z.bis_s + 0.5), None)
    if hier is None:
        vorher = [i for i, z in enumerate(zeiten) if z.von_s <= t_s]
        hier = vorher[-1] if vorher else 0
    if not zeiten or zeiten[hier].zaehlt:
        return hier
    davor = [i for i in range(hier) if zeiten[i].zaehlt]
    danach = [i for i in range(hier, len(zeiten)) if zeiten[i].zaehlt]
    return davor[-1] if davor else (danach[0] if danach else hier)


def satz_nummer(zeiten: Sequence[Gelaufen], i: int) -> int:
    """Der wievielte Satz der Abschnitt ``i`` ist (zählende Abschnitte bis zu ihm) — 1 ohne
    zählenden.

    >>> z = [Gelaufen("H", 1, 30.0, True, 0, 30), Gelaufen("P", 1, 9.0, False, 30, 39),
    ...      Gelaufen("H", 2, 30.0, True, 39, 69)]
    >>> satz_nummer(z, 0), satz_nummer(z, 2), satz_nummer([], 0)
    (1, 2, 1)
    """
    return max(1, sum(1 for z in zeiten[: i + 1] if z.zaehlt))


@dataclass
class Eingaben:
    """Was die Person im Fokus eintrug (Karte „Eintragen“, `docs/plan_uhr_fokus.md` §1) — aus
    der Zeitleiste: ``person/wdh`` (Wiederholungen, je Abschnitt der letzte Wert),
    ``person/skala`` (der letzte Wert je Abschnitt) und ``person/auspraegung`` (die letzte Wahl
    der Ausprägungen). Gespeichert wird erst mit dem Ende des Laufs (P150)."""

    #: Feld → {Abschnitt (Index in den Zeiten): Wiederholungen}
    wdh: dict[str, dict[int, int]] = field(default_factory=dict)
    #: Feld → {Abschnitt: Wert}
    skala: dict[str, dict[int, Any]] = field(default_factory=dict)
    #: die zuletzt im Fokus gewählten Ausprägungen — ``None``: keine Wahl im Fokus
    auspraegung: dict[str, Any] | None = None

    def werte(
        self, zeiten: Sequence[Gelaufen], ausfuehrung: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Die Werte für einen Eintrag: Wiederholungen je Satz (Abschnitt) und die letzte
        Skala — mit ``ausfuehrung`` nur aus deren zählenden Abschnitten (je Ausführung ein
        Eintrag), sonst aus allen.

        >>> L, R = (("variant", "links"),), (("variant", "rechts"),)
        >>> zeiten = [Gelaufen("L", 1, 60.0, True, 0, 60, ausfuehrung=L),
        ...           Gelaufen("R", 1, 60.0, True, 60, 120, ausfuehrung=R)]
        >>> e = Eingaben(wdh={"reps": {0: 10, 1: 12}}, skala={"scale": {1: 7}})
        >>> e.werte(zeiten), e.werte(zeiten, {"variant": "links"})
        ({'reps': [10, 12], 'scale': 7}, {'reps': [10]})
        """
        if ausfuehrung is None:
            stellen = set(range(len(zeiten))) or {0}
        else:
            stellen = {
                i
                for i, z in enumerate(zeiten)
                if z.zaehlt and dict(z.ausfuehrung) == dict(ausfuehrung)
            }
        out: dict[str, Any] = {}
        for feld, je in self.wdh.items():
            liste = [je[i] for i in sorted(je) if i in stellen]
            if liste:
                out[feld] = liste
        for feld, je in self.skala.items():
            drin = [i for i in sorted(je) if i in stellen]
            if drin:
                out[feld] = je[drin[-1]]
        return out


def eingaben(ereignisse: Iterable[Ereignis], zeiten: Sequence[Gelaufen]) -> Eingaben:
    """Die Eingaben der Person aus der Zeitleiste, den Abschnitten zugeordnet (`Eingaben`).

    >>> ev = [Ereignis(10.0, "person", "wdh", "", {"feld": "reps", "wert": 8}),
    ...       Ereignis(50.0, "person", "wdh", "", {"feld": "reps", "wert": 10}),
    ...       Ereignis(70.0, "person", "skala", "", {"feld": "scale", "wert": 6}),
    ...       Ereignis(80.0, "person", "auspraegung", "", {"weight": 12, "side": None})]
    >>> zeiten = [Gelaufen("H", 1, 60.0, True, 0, 60), Gelaufen("H", 2, 60.0, True, 60, 120)]
    >>> e = eingaben(ev, zeiten)
    >>> e.wdh, e.skala, e.auspraegung
    ({'reps': {0: 10}}, {'scale': {1: 6}}, {'weight': 12})
    """
    e = Eingaben()
    for x in ereignisse:
        if x.quelle != "person":
            continue
        d = x.daten
        if x.art == "auspraegung":  # flach; ``None`` = im Fokus abgewählt
            e.auspraegung = {k: d[k] for k in AUSFUEHRUNG_SCHLUESSEL if d.get(k) not in (None, "")}
            continue
        feld = str(d.get("feld") or "")
        if not feld or d.get("wert") is None:
            continue
        if x.art == "wdh":
            e.wdh.setdefault(feld, {})[stelle(zeiten, x.t_s)] = max(0, ganzzahl_lesen(d["wert"]))
        elif x.art == "skala":
            e.skala.setdefault(feld, {})[stelle(zeiten, x.t_s)] = d["wert"]
    return e


def ohne_timer(dauer_s: float, feld: str | None) -> dict[str, Any]:
    """Eine Übung ohne Timer mit eingeschalteter Uhr (Ben, 18.10.2026): Ihre Zeit von Beginn
    bis „Gemacht“ ist ein Lauf — ein Satz Haltezeit bzw. die Zeit; unter
    `core.einheit.MIN_MARKE_S` nur „gemacht“.

    >>> ohne_timer(42.4, "duration"), ohne_timer(42.4, "hold"), ohne_timer(3.0, "duration")
    ({'duration': 42}, {'hold': [42]}, {})
    """
    if dauer_s < MIN_MARKE_S:
        return {}
    return ergebnis([Gelaufen("", 1, dauer_s, True, 0.0, dauer_s)], feld)


def vom_timer_text(anfaenge: Iterable[datetime]) -> str:
    """„vom Timer, 10:07“ — wann die Läufe begannen, die ein Timer eintrug (Ortszeit);
    leer ohne einen (Ben, 17.10.2026; Skizze 12).

    >>> zehn = datetime(2026, 10, 17, 10, 7).astimezone()
    >>> vom_timer_text([zehn]), vom_timer_text([])
    ('vom Timer, 10:07', '')
    >>> vom_timer_text([zehn.replace(minute=31), zehn, zehn.replace(hour=11, minute=2)])
    'vom Timer, 10:07, 10:31 und 11:02'
    """
    zeiten = [f"{t.astimezone():%H:%M}" for t in sorted(anfaenge)]
    if not zeiten:
        return ""
    if len(zeiten) == 1:
        return f"vom Timer, {zeiten[0]}"
    return f"vom Timer, {', '.join(zeiten[:-1])} und {zeiten[-1]}"


__all__ = [
    "ZEITFELDER",
    "Gelaufen",
    "abgebrochen",
    "ergebnis",
    "gelaufene_zeiten",
    "ohne_timer",
    "vom_timer_text",
    "zeitfeld",
]
