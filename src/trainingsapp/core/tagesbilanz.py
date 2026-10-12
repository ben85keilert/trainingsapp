"""Was habe ich gemacht? — Einträge bündeln, Mengen addieren, Offenes zeigen.

Am Ende des Tages zählt nicht jeder einzelne Tipp, sondern die Bilanz:
dreimal 50 Liegestütze sind **150 Liegestütze**. Dafür werden Einträge zu
`Buendel`n zusammengefasst:

- **Schlüssel** ist die Übung plus ihre *Ausprägung* (`core/parameter.py`):
  Wandsitz bei 45° und Wandsitz bei 90° sind zwei Bündel, auch wenn es
  dieselbe Übung ist.
- **Mengen** (Wiederholungen, Haltezeit, Strecke …) werden addiert.
- **Abgehakt** ohne Werte und **Leistung** mit Werten bleiben getrennt
  sichtbar: „150 Wdh. · zusätzlich 1× abgehakt“.

Für den Verlauf fasst `kachel` zusätzlich Varianten zusammen: Eine Kopie
einer Übung gehört zur selben Kachel (`Exercise.family_id`), solange man sie
nicht ausdrücklich eigenständig macht.

Alles hier ist reine Rechnung ohne Datenbank und ohne Oberfläche.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .models import Exercise, SessionEntry
from .parameter import MENGE, auspraegung, rolle
from .result_spec import FieldSpec, FieldType, ResultSpec, format_wert, ist_leer
from .units import format_dauer, satz_summe


def mengen(spec: ResultSpec | None, werte: dict[str, Any]) -> dict[str, float]:
    """Die addierbaren Werte eines Eintrags: Satzlisten als Summe.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> mengen(SPEC_SAETZE_WDH, {"reps": [15, 15, 20]})
    {'reps': 50.0}
    >>> mengen(SPEC_SAETZE_WDH, {})
    {}
    """
    if spec is None:
        return {}
    ergebnis: dict[str, float] = {}
    for f in spec.fields:
        wert: Any = werte.get(f.key)
        if rolle(f) != MENGE or ist_leer(wert):
            continue
        try:
            if isinstance(wert, list):
                ergebnis[f.key] = satz_summe([float(w) for w in wert])
            else:
                ergebnis[f.key] = float(wert)
        except (TypeError, ValueError):
            continue
    return ergebnis


def menge_text(f: FieldSpec, summe: float) -> str:
    """„150 Wdh.“, „2:30 Haltezeit“, „1500 m“.

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> menge_text(vorrat_feld("reps"), 150)
    '150 Wdh.'
    >>> menge_text(vorrat_feld("hold"), 150)
    '2:30 Haltezeit'
    """
    if f.unit == "s" or f.type == FieldType.DURATION:
        return f"{format_dauer(summe)} {f.label}"
    zahl = f"{summe:g}"
    return f"{zahl} {f.unit}" if f.unit else f"{zahl} {f.label}"


@dataclass(slots=True)
class Buendel:
    """Gleiche Übung, gleiche Ausprägung, ein Tag (oder eine Session)."""

    exercise_id: str
    auspraegung: tuple[tuple[str, Any], ...] = ()
    #: Einträge mit Werten — die Leistungen
    leistungen: list[SessionEntry] = field(default_factory=list)
    #: Einträge ohne Menge — nur abgehakt
    abgehakt: list[SessionEntry] = field(default_factory=list)
    #: Summe je Mengenfeld über alle Leistungen
    summen: dict[str, float] = field(default_factory=dict)
    #: Spezifikation zum Beschriften (die des jüngsten Eintrags)
    spec: ResultSpec | None = None

    @property
    def eintraege(self) -> list[SessionEntry]:
        """Alle Einträge, zeitlich sortiert."""
        return sorted(
            [*self.leistungen, *self.abgehakt],
            key=lambda e: (e.started_at is None, e.started_at),
        )

    def auspraegung_text(self) -> str:
        """„45°“, „20kg · links“ — leer, wenn es keine gibt."""
        if self.spec is None:
            return ""
        teile = []
        for key, wert in self.auspraegung:
            f = self.spec.field_by_key(key)
            teile.append(format_wert(f, wert) if f is not None else str(wert))
        return " · ".join(teile)

    def leistung_text(self) -> str:
        """„150 Wdh.“ — die Summen der Mengenfelder."""
        if self.spec is None:
            return ""
        teile = [
            menge_text(f, self.summen[f.key]) for f in self.spec.fields if f.key in self.summen
        ]
        return " · ".join(teile)

    def einzelwerte_text(self) -> str:
        """Woraus sich die Summe zusammensetzt: „50 · 50 · 50“ oder „3x15 · 20“."""
        return " · ".join(e.shorthand() for e in self.leistungen if e.result)

    def zusammenfassung(self) -> str:
        """Die eine Zeile für die Tagesansicht.

        Leistung zuerst, Abgehaktes getrennt dahinter — man soll auf einen Blick
        sehen, was gezählt und was nur angetippt wurde.
        """
        teile = []
        leistung = self.leistung_text()
        if leistung:
            n = len(self.leistungen)
            teile.append(leistung if n == 1 else f"{leistung} aus {n} Einträgen")
        elif self.leistungen:  # Werte ohne Menge, etwa nur ein gemessener Winkel
            teile.append(self.einzelwerte_text())
        if self.abgehakt:
            n = len(self.abgehakt)
            wort = "abgehakt" if n == 1 else f"{n}× abgehakt"
            teile.append(f"zusätzlich {wort}" if teile else wort)
        return " · ".join(teile)


def buendeln(
    eintraege: Iterable[SessionEntry],
    gruppe: Callable[[SessionEntry], Hashable] = lambda e: e.exercise_id,
) -> list[Buendel]:
    """Fasst Einträge zusammen — in der Reihenfolge des jeweils ersten Eintrags.

    ``gruppe`` bestimmt, was zusammengehört (Vorgabe: die Übung). Die
    Ausprägung kommt immer dazu, sie trennt in jedem Fall.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> e = [SessionEntry(exercise_id="lgs", result={"reps": [50]}, spec_snapshot=SPEC_SAETZE_WDH)
    ...      for _ in range(3)]
    >>> b = buendeln([*e, SessionEntry(exercise_id="lgs", spec_snapshot=SPEC_SAETZE_WDH)])
    >>> len(b), b[0].summen, b[0].zusammenfassung()
    (1, {'reps': 150.0}, '150 Wdh. aus 3 Einträgen · zusätzlich abgehakt')
    """
    nach_schluessel: dict[Hashable, Buendel] = {}
    for e in eintraege:
        auspr = auspraegung(e.spec_snapshot, e.result)
        schluessel = (gruppe(e), auspr)
        b = nach_schluessel.get(schluessel)
        if b is None:
            b = nach_schluessel[schluessel] = Buendel(exercise_id=e.exercise_id, auspraegung=auspr)
        b.spec = e.spec_snapshot or b.spec
        summen = mengen(e.spec_snapshot, e.result)
        if ist_leistung(e):
            b.leistungen.append(e)
        else:
            b.abgehakt.append(e)  # „Gemacht“ — ggf. mit gewählter Ausprägung
        for key, wert in summen.items():
            b.summen[key] = b.summen.get(key, 0.0) + wert
    return list(nach_schluessel.values())


def ist_leistung(e: SessionEntry) -> bool:
    """Hat der Eintrag Werte, die zählen — oder wurde er nur abgehakt?

    Eine Menge zählt immer. Eine Ausprägung allein (Gemacht bei 45°) ist nur
    abgehakt — außer die Übung hat gar keine Mengen, dann ist die Ausprägung
    die Leistung (eine Winkelmessung).

    >>> from trainingsapp.core.result_spec import vorrat_feld
    >>> wandsitz = ResultSpec(fields=[vorrat_feld("hold"), vorrat_feld("angle")])
    >>> ist_leistung(SessionEntry(result={"angle": 45}, spec_snapshot=wandsitz))
    False
    >>> ist_leistung(SessionEntry(result={"angle": 45, "hold": [30]}, spec_snapshot=wandsitz))
    True
    >>> messung = ResultSpec(fields=[vorrat_feld("angle")])
    >>> ist_leistung(SessionEntry(result={"angle": 45}, spec_snapshot=messung))
    True
    """
    if mengen(e.spec_snapshot, e.result):
        return True
    return bool(auspraegung(e.spec_snapshot, e.result)) and _nur_auspraegung(e)


def _nur_auspraegung(e: SessionEntry) -> bool:
    """Hat die Übung gar keine Mengen? Dann ist die Ausprägung selbst die Leistung."""
    spec = e.spec_snapshot
    return spec is not None and not any(rolle(f) == MENGE for f in spec.fields)


def kachel(uebung: Exercise | None, exercise_id: str) -> str:
    """Die Kachel im Verlauf: das Original einer Variantenfamilie, sonst die Übung selbst."""
    if uebung is None:
        return exercise_id
    return uebung.family_id or uebung.id


@dataclass(slots=True)
class Kachel:
    """Eine Kachel im Verlauf: alle Varianten einer Übung, alle Ausprägungen.

    Die Teile sind die Bündel je Übung + Ausprägung. Die Kachel addiert ihre
    Mengen (je Feld, Varianten teilen sich die Feldschlüssel aus dem
    Feldvorrat) und weist die Teile einzeln aus, wenn es mehrere gibt —
    „marginale Abweichungen werden notiert“.
    """

    kachel_id: str
    teile: list[Buendel] = field(default_factory=list)

    @property
    def summen(self) -> dict[str, float]:
        ergebnis: dict[str, float] = {}
        for b in self.teile:
            for key, wert in b.summen.items():
                ergebnis[key] = ergebnis.get(key, 0.0) + wert
        return ergebnis

    @property
    def leistungen(self) -> int:
        return sum(len(b.leistungen) for b in self.teile)

    @property
    def abgehakt(self) -> int:
        return sum(len(b.abgehakt) for b in self.teile)

    def feld(self, key: str) -> FieldSpec | None:
        """Beschriftung eines Mengenfelds — aus irgendeinem Teil, der es kennt."""
        for b in self.teile:
            if b.spec is not None and (f := b.spec.field_by_key(key)) is not None:
                return f
        return None

    def zusammenfassung(self) -> str:
        """„150 Wdh. · zusätzlich 2× abgehakt“ — über alle Varianten."""
        teile = [
            menge_text(f, summe)
            for key, summe in self.summen.items()
            if (f := self.feld(key)) is not None
        ]
        if not teile and self.leistungen:
            teile = [b.einzelwerte_text() for b in self.teile if b.leistungen]
        if self.abgehakt:
            wort = "abgehakt" if self.abgehakt == 1 else f"{self.abgehakt}× abgehakt"
            teile.append(f"zusätzlich {wort}" if teile else wort)
        return " · ".join(t for t in teile if t)

    def aufschluesselung(self, namen: dict[str, str]) -> str:
        """Woraus die Kachel besteht, wenn mehr als eine Variante/Ausprägung dabei ist.

        ``namen`` bildet Übungs-IDs auf Namen ab.
        """
        if len(self.teile) < 2:
            return ""
        zeilen = []
        for b in self.teile:
            name = namen.get(b.exercise_id, "?")
            if zusatz := b.auspraegung_text():
                name += f" {zusatz}"
            zeilen.append(f"{name}: {b.zusammenfassung()}")
        return "davon " + " · ".join(zeilen)


def kacheln(eintraege: Iterable[SessionEntry], kachel_von: Callable[[str], str]) -> list[Kachel]:
    """Einträge zu Kacheln — Varianten zusammen, Teile je Übung + Ausprägung.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> e = [SessionEntry(exercise_id=x, result={"reps": [n]}, spec_snapshot=SPEC_SAETZE_WDH)
    ...      for x, n in (("eng", 20), ("weit", 30), ("eng", 10))]
    >>> (k,) = kacheln(e, lambda _: "liegestuetz")
    >>> k.summen, k.aufschluesselung({"eng": "eng", "weit": "weit"})
    ({'reps': 60.0}, 'davon eng: 30 Wdh. aus 2 Einträgen · weit: 30 Wdh.')
    """
    nach_kachel: dict[str, list[SessionEntry]] = {}
    for e in eintraege:
        nach_kachel.setdefault(kachel_von(e.exercise_id), []).append(e)
    return [Kachel(kachel_id=k, teile=buendeln(liste)) for k, liste in nach_kachel.items()]


@dataclass(slots=True)
class Planstand:
    """Wie weit ein Plan an einem Tag gekommen ist."""

    plan_id: str
    name: str
    erledigt: list[str] = field(default_factory=list)  # exercise_ids
    offen: list[str] = field(default_factory=list)

    @property
    def gesamt(self) -> int:
        return len(self.erledigt) + len(self.offen)


def planstand(plan_id: str, name: str, exercise_ids: Iterable[str], gemacht: set[str]) -> Planstand:
    """Erledigt ist eine Planübung, wenn die Übung an diesem Tag dran war — egal wo.

    >>> s = planstand("p", "Dehnung", ["a", "b", "c"], {"b"})
    >>> s.erledigt, s.offen, s.gesamt
    (['b'], ['a', 'c'], 3)
    """
    stand = Planstand(plan_id=plan_id, name=name)
    for exercise_id in dict.fromkeys(exercise_ids):
        (stand.erledigt if exercise_id in gemacht else stand.offen).append(exercise_id)
    return stand


__all__ = [
    "Buendel",
    "Kachel",
    "Planstand",
    "buendeln",
    "ist_leistung",
    "kachel",
    "kacheln",
    "menge_text",
    "mengen",
    "planstand",
]
