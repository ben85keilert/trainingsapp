"""Ein Tag: was gemacht ist, als Liste und als Zeitleiste (Ben, 18.10.2026; P40).

Die Tagesansicht hat zwei Darstellungen (`ui/views/tag.py`):

- **Übersicht** (Vorgabe): je Übung eine Zeile in der Reihenfolge ihres ersten Eintrags —
  Wert, Sätze, die Pläne als Etikett (`gemacht`). Hat eine Übung Varianten, bekommt jede
  ihre eigene Zeile mit eigener Zahl (Ben, 21.10.2026: „Varianten werden separat gezählt.
  Das ist vor allem im Tagebuch wichtig“).
- **Zeitleiste**: der Tag in Uhrzeit-Reihenfolge; ein Plan ist ein Block mit seinen
  Übungen, was ohne Plan dazukam, steht einzeln an seiner Stelle (`zeitleiste`).

Darüber steht in beiden, was ansteht: je Plan eine Karte (`plankarten`) — noch nicht
begonnen, unterwegs oder fertig (Skizze C1).

„Nach Plan“, „Nach Übung“ und „Chronologisch“ zeigten dreimal fast dasselbe; die Sicht
je Übung über Tage hinweg hat der Verlauf. Hier wird nur gruppiert — Werte und Sätze
rechnet `core/verlauf.tageszeilen`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time

from .models import Plan, PlanItem, Session, SessionEntry, lokaler_tag
from .plaene import erledigte, heutige_plaene
from .varianten import von as variante_von
from .verlauf import Tageszeile, tageszeilen

#: Zustände der Plan-Karte (Skizze C1)
NEU, UNTERWEGS, FERTIG, LEER = "neu", "unterwegs", "fertig", "leer"


@dataclass(frozen=True, slots=True)
class Gemacht:
    """Eine Übung an diesem Tag — alle ihre Einträge einer Variante, Ausprägungen zusammen."""

    exercise_id: str
    #: der erste Eintrag des Tages
    beginn: datetime | None
    zeile: Tageszeile
    eintraege: tuple[SessionEntry, ...]
    #: die Pläne, in denen sie dran war (in der Reihenfolge des ersten Eintrags)
    plan_ids: tuple[str, ...]
    #: die Variante dieser Zeile — leer ohne (Ben, 21.10.2026)
    variante: str = ""
    #: mindestens ein Eintrag ohne Plan — neben Plan-Einträgen zeigt die Zeile das an
    ohne_plan: bool = False

    @property
    def nur_abgehakt(self) -> bool:
        return self.zeile.kennzahl is None


def gemacht(
    eintraege: Iterable[tuple[SessionEntry, Session]], namen: dict[str, str]
) -> list[Gemacht]:
    """Je Übung und Variante eine Zeile, in der Reihenfolge des ersten Eintrags.

    >>> from datetime import UTC
    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> plan, frei = Session(id="s1", plan_id="p"), Session(id="s2")
    >>> def e(x, minute, *n, v=""): return SessionEntry(exercise_id=x,
    ...     result={"reps": list(n), **({"variant": v} if v else {})},
    ...     spec_snapshot=SPEC_SAETZE_WDH, started_at=datetime(2026, 10, 18, 7, minute, tzinfo=UTC))
    >>> z = gemacht([(e("lgs", 1, 15, 15), plan), (e("kb", 2), frei), (e("lgs", 3, 13), frei)], {})
    >>> [(g.exercise_id, g.zeile.wert, g.plan_ids, g.nur_abgehakt, g.ohne_plan) for g in z]
    [('lgs', 43.0, ('p',), False, True), ('kb', None, (), True, True)]

    Kurz und lang zählen getrennt — 400 kurze sind etwas anderes als 400 lange:

    >>> z = gemacht([(e("lgs", 1, 30, v="kurz"), plan), (e("lgs", 2, 15, v="lang"), plan),
    ...              (e("lgs", 3, 30, v="kurz"), plan)], {})
    >>> [(g.variante, g.zeile.wert) for g in z]
    [('kurz', 60.0), ('lang', 15.0)]
    """
    je_zeile: dict[tuple[str, str], list[tuple[SessionEntry, Session]]] = {}
    for e, s in eintraege:
        je_zeile.setdefault((e.exercise_id, variante_von(e.result)), []).append((e, s))
    ergebnis = []
    for (exercise_id, variante), liste in je_zeile.items():
        nur = [e for e, _ in liste]
        (zeile,) = tageszeilen(nur, lambda x: x, namen) or [
            Tageszeile(exercise_id, None, None, "", variante=variante)
        ]
        plaene = tuple(dict.fromkeys(s.plan_id for _, s in liste if s.plan_id))
        beginn = min((e.started_at for e in nur if e.started_at), default=None)
        ohne = any(not s.plan_id for _, s in liste)
        ergebnis.append(Gemacht(exercise_id, beginn, zeile, tuple(nur), plaene, variante, ohne))
    return ergebnis


def gemacht_reihen(
    eintraege: Iterable[tuple[SessionEntry, Session]],
    namen: dict[str, str],
    ist_training: Callable[[SessionEntry], bool] = lambda _: False,
) -> list[Gemacht]:
    """Je Übung eine Zeile, nach dem ersten Eintrag — ein Training (Gehen, Laufen, Rad)
    immer für sich, auch wenn es dieselbe Übung zweimal am Tag war (bis 19.10.2026
    `_Daten.reihen` in `ui/views/tag.py`, N25).

    >>> from datetime import UTC
    >>> s = Session(id="s")
    >>> def e(i, x, minute): return SessionEntry(id=i, exercise_id=x,
    ...     started_at=datetime(2026, 10, 18, 7, minute, tzinfo=UTC))
    >>> liste = [(e("1", "gehen", 1), s), (e("2", "kb", 2), s), (e("3", "gehen", 3), s)]
    >>> [g.exercise_id for g in gemacht_reihen(liste, {})]
    ['gehen', 'kb']
    >>> training = lambda e: e.exercise_id == "gehen"
    >>> [(g.exercise_id, len(g.eintraege)) for g in gemacht_reihen(liste, {}, training)]
    [('gehen', 1), ('kb', 1), ('gehen', 1)]
    """
    paare = list(eintraege)
    reihen = gemacht([(e, s) for e, s in paare if not ist_training(e)], namen)
    for e, s in paare:
        if ist_training(e):
            reihen.extend(gemacht([(e, s)], namen))
    return sorted(reihen, key=lambda g: (g.beginn is None, g.beginn.timestamp() if g.beginn else 0))


@dataclass(frozen=True, slots=True)
class Abschnitt:
    """Ein Punkt der Zeitleiste: ein Plan mit seinen Übungen oder eine Übung ohne Plan."""

    beginn: datetime | None
    zeilen: tuple[Gemacht, ...]
    #: der Plan dieses Blocks — ``None``: eine Übung ohne Plan
    plan_id: str | None = None
    session: Session | None = None

    @property
    def ende(self) -> datetime | None:
        zeiten = [e.started_at for g in self.zeilen for e in g.eintraege if e.started_at]
        return max(zeiten, default=None)


def zeitleiste(
    eintraege: Sequence[tuple[SessionEntry, Session]],
    namen: dict[str, str],
    ist_training: Callable[[SessionEntry], bool] = lambda _: False,
) -> list[Abschnitt]:
    """Der Tag in Uhrzeit-Reihenfolge: je Plan-Session ein Block, ohne Plan jede Übung
    einzeln — ein Training (``ist_training``) immer für sich.

    >>> from datetime import UTC
    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> plan, frei = Session(id="s1", plan_id="p"), Session(id="s2")
    >>> def e(x, stunde, *n): return SessionEntry(exercise_id=x, result={"reps": list(n)},
    ...     spec_snapshot=SPEC_SAETZE_WDH, started_at=datetime(2026, 10, 18, stunde, tzinfo=UTC))
    >>> a = zeitleiste([(e("lauf", 12, 1), frei), (e("lgs", 7, 15), plan),
    ...                 (e("kb", 8, 10), plan), (e("dehn", 18), frei)], {})
    >>> [(x.plan_id, [g.exercise_id for g in x.zeilen]) for x in a]
    [('p', ['lgs', 'kb']), (None, ['lauf']), (None, ['dehn'])]
    """
    plan_sessions: dict[str, list[tuple[SessionEntry, Session]]] = {}
    frei: list[tuple[SessionEntry, Session]] = []
    for e, s in eintraege:
        if s.plan_id and not ist_training(e):
            plan_sessions.setdefault(s.id, []).append((e, s))
        else:
            frei.append((e, s))
    abschnitte = []
    for liste in plan_sessions.values():
        zeilen = gemacht(liste, namen)
        beginn = min((g.beginn for g in zeilen if g.beginn), default=None)
        session = liste[0][1]
        abschnitte.append(Abschnitt(beginn, tuple(zeilen), session.plan_id, session))
    trainings = [(e, s) for e, s in frei if ist_training(e)]
    uebrige = [(e, s) for e, s in frei if not ist_training(e)]
    for e, s in trainings:
        abschnitte.extend(Abschnitt(g.beginn, (g,), None, s) for g in gemacht([(e, s)], namen))
    abschnitte.extend(Abschnitt(g.beginn, (g,), None, None) for g in gemacht(uebrige, namen))
    return sorted(abschnitte, key=lambda a: (a.beginn is None, a.beginn or datetime.min))


@dataclass(frozen=True, slots=True)
class Plankarte:
    """Ein Plan an einem Tag: was erledigt ist, was offen, wann begonnen (Skizze C1)."""

    plan: Plan
    #: nur da, weil für den Tag aufgenommen — laut Zeitplan stünde er nicht an
    zusaetzlich: bool
    #: die erledigten Planübungen (IDs) — wie im Plan (`core.plaene.erledigte`)
    erledigt: frozenset[str]
    #: die offenen Planübungen, in der Reihenfolge des Plans
    offen: tuple[PlanItem, ...]
    #: erster und letzter Eintrag in der Session dieses Plans
    beginn: datetime | None = None
    ende: datetime | None = None
    #: Einträge in der Session dieses Plans
    eintraege: int = 0
    notiz: str = ""

    @property
    def zustand(self) -> str:
        if not self.plan.items:
            return LEER
        if not self.offen:
            return FERTIG
        return UNTERWEGS if self.erledigt or self.eintraege else NEU

    def stand_text(self) -> str:
        """„2 von 5“ — kein Prozent, kein Drängen: Ein Plan ist ein Rahmen."""
        return f"{len(self.erledigt)} von {len(self.plan.items)}"


def plaene_des_tags(
    plaene: Iterable[Plan], tag: date, aufgenommen: Iterable[str]
) -> list[tuple[Plan, bool]]:
    """Wie `core.plaene.heutige_plaene` — ohne Pläne, die es an dem Tag noch nicht gab.

    Ein vergangener Tag zeigte sonst einen erst später angelegten Plan als „0 von 5“.

    >>> from datetime import UTC
    >>> alt = Plan(name="Alt", created_at=datetime(2026, 10, 1, 8, tzinfo=UTC))
    >>> neu = Plan(name="Neu", created_at=datetime(2026, 10, 18, 8, tzinfo=UTC))
    >>> [p.name for p, _ in plaene_des_tags([alt, neu], date(2026, 10, 16), [])]
    ['Alt']
    >>> [p.name for p, _ in plaene_des_tags([alt, neu], date(2026, 10, 16), [neu.id])]
    ['Alt', 'Neu']
    """
    aufgenommen = set(aufgenommen)
    return [
        (p, extra)
        for p, extra in heutige_plaene(plaene, tag, aufgenommen)
        if p.id in aufgenommen or lokaler_tag(p.created_at) <= tag
    ]


def plankarten(
    plaene: Iterable[tuple[Plan, bool]],
    anzahl: Mapping[str, int],
    eintraege: Iterable[tuple[SessionEntry, Session]],
) -> list[Plankarte]:
    """Die Karten der Pläne eines Tages — ``plaene`` aus `core.plaene.heutige_plaene`,
    ``anzahl`` = Einträge je Übung an diesem Tag (planunabhängig, wie im Plan).

    >>> from datetime import UTC
    >>> a, b = PlanItem(exercise_id="lgs"), PlanItem(exercise_id="kb")
    >>> plan = Plan(id="p", items=[a, b])
    >>> s = Session(id="s", plan_id="p", note="ruhig")
    >>> e = SessionEntry(exercise_id="lgs", started_at=datetime(2026, 10, 18, 18, tzinfo=UTC))
    >>> (k,) = plankarten([(plan, False)], {"lgs": 1}, [(e, s)])
    >>> k.zustand, k.stand_text(), [i.exercise_id for i in k.offen], k.beginn.hour, k.notiz
    ('unterwegs', '1 von 2', ['kb'], 18, 'ruhig')
    >>> [x.zustand for x in plankarten([(plan, False), (Plan(), True)], {}, [])]
    ['neu', 'leer']
    >>> plankarten([(plan, False)], {"lgs": 1, "kb": 2}, [])[0].zustand
    'fertig'
    """
    je_plan: dict[str, list[tuple[SessionEntry, Session]]] = {}
    for e, s in eintraege:
        if s.plan_id:
            je_plan.setdefault(s.plan_id, []).append((e, s))
    karten = []
    for plan, zusaetzlich in plaene:
        fertig = erledigte(plan.items, anzahl)
        liste = je_plan.get(plan.id, [])
        zeiten = [e.started_at for e, _ in liste if e.started_at]
        karten.append(
            Plankarte(
                plan=plan,
                zusaetzlich=zusaetzlich,
                erledigt=frozenset(fertig),
                offen=tuple(i for i in plan.items if i.id not in fertig),
                beginn=min(zeiten, default=None),
                ende=max(zeiten, default=None),
                eintraege=len(liste),
                notiz=next((s.note for _, s in liste if s.note), ""),
            )
        )
    return karten


def uhrzeit_lesen(text: str) -> time | None:
    """„7:30“, „07.05“, „1845“ oder „9“ → Uhrzeit; unlesbar → ``None`` (Nachtragen).

    >>> uhrzeit_lesen("7:30"), uhrzeit_lesen("07.05"), uhrzeit_lesen("1845"), uhrzeit_lesen("9")
    (datetime.time(7, 30), datetime.time(7, 5), datetime.time(18, 45), datetime.time(9, 0))
    >>> uhrzeit_lesen("25:00"), uhrzeit_lesen("7:3x"), uhrzeit_lesen("")
    (None, None, None)
    """
    t = text.strip().replace(".", ":").replace(" ", "")
    if ":" in t:
        stunde, _, minute = t.partition(":")
    elif t.isdigit() and len(t) in (3, 4):
        stunde, minute = t[:-2], t[-2:]
    else:
        stunde, minute = t, "0"
    if not (stunde.isdigit() and minute.isdigit()):
        return None
    h, m = int(stunde), int(minute)
    return time(h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


def zusammenfassung(uebungen: int, trainings: int, notizen: int, tageswerte: int = 0) -> str:
    """„6 Übungen · 1 Training · 2 Notizen · 3 Tageswerte“ — nur, was es gibt. ``tageswerte``:
    wie viele Tagesfelder an dem Tag etwas haben (`core.tagesfelder`).

    >>> zusammenfassung(6, 1, 2), zusammenfassung(1, 0, 0), zusammenfassung(0, 0, 0)
    ('6 Übungen · 1 Training · 2 Notizen', '1 Übung', 'Noch nichts eingetragen')
    >>> zusammenfassung(0, 0, 1, 1)
    '1 Notiz · 1 Tageswert'
    """
    teile = []
    if uebungen:
        teile.append(f"{uebungen} {'Übung' if uebungen == 1 else 'Übungen'}")
    if trainings:
        teile.append(f"{trainings} {'Training' if trainings == 1 else 'Trainings'}")
    if notizen:
        teile.append(f"{notizen} {'Notiz' if notizen == 1 else 'Notizen'}")
    if tageswerte:
        teile.append(f"{tageswerte} {'Tageswert' if tageswerte == 1 else 'Tageswerte'}")
    return " · ".join(teile) or "Noch nichts eingetragen"


__all__ = [
    "FERTIG",
    "LEER",
    "NEU",
    "UNTERWEGS",
    "Abschnitt",
    "Gemacht",
    "Plankarte",
    "gemacht",
    "gemacht_reihen",
    "plaene_des_tags",
    "plankarten",
    "uhrzeit_lesen",
    "zeitleiste",
    "zusammenfassung",
]
