"""Welche Pläne an einem Tag erscheinen.

Ein Plan steht an, wenn er aktiv ist und der Wochentag passt
(`Plan.steht_an`). Dazu kommen Pläne, die für diesen Tag eigens aufgenommen
wurden — erkennbar daran, dass es eine Session dieses Plans an dem Tag gibt.
Ein Plan, an dem heute schon trainiert wurde, bleibt deshalb immer sichtbar,
auch wenn er inzwischen deaktiviert ist.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime, time
from typing import Any

from . import eintraege as offene
from .models import Exercise, Plan, PlanItem, Session, SessionEntry
from .parameter import kontextfelder
from .result_spec import ist_leer
from .standards import aktive_felder, ziel_von
from .tagesfelder import UHRZEIT_NACHTRAGEN

WOCHENTAGE_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def tage_text(wochentage: Iterable[int]) -> str:
    """„täglich", „Mo–Fr", „Mo Mi Fr" oder „an keinem Tag".

    >>> tage_text(range(7)), tage_text([0, 1, 2, 3, 4]), tage_text([5, 6])
    ('täglich', 'Mo–Fr', 'Sa So')
    >>> tage_text([0, 2, 4]), tage_text([])
    ('Mo Mi Fr', 'an keinem Tag')
    """
    tage = sorted(set(wochentage))
    if not tage:
        return "an keinem Tag"
    if tage == list(range(7)):
        return "täglich"
    if len(tage) >= 3 and tage == list(range(tage[0], tage[-1] + 1)):
        return f"{WOCHENTAGE_KURZ[tage[0]]}–{WOCHENTAGE_KURZ[tage[-1]]}"
    return " ".join(WOCHENTAGE_KURZ[t] for t in tage)


def heutige_plaene(
    plaene: Iterable[Plan], tag: date, aufgenommen: Iterable[str]
) -> list[tuple[Plan, bool]]:
    """Die Pläne für diesen Tag, in ihrer Reihenfolge — mit Markierung „zusätzlich".

    ``aufgenommen`` sind die IDs der Pläne mit einer Session an diesem Tag.
    Zusätzlich ist ein Plan, der nur deshalb erscheint.

    >>> mo = date(2026, 10, 12)
    >>> a, b, c = Plan(name="A"), Plan(name="B", wochentage=[1]), Plan(name="C", aktiv=False)
    >>> [(p.name, extra) for p, extra in heutige_plaene([a, b, c], mo, {c.id})]
    [('A', False), ('C', True)]
    """
    extra = set(aufgenommen)
    ergebnis: list[tuple[Plan, bool]] = []
    for plan in plaene:
        if plan.steht_an(tag):
            ergebnis.append((plan, False))
        elif plan.id in extra:
            ergebnis.append((plan, True))
    return ergebnis


def warum_nicht(plan: Plan, tag: date) -> str:
    """Kurzer Grund, warum ein Plan heute nicht von sich aus ansteht.

    >>> warum_nicht(Plan(aktiv=False), date(2026, 10, 12))
    'deaktiviert'
    >>> warum_nicht(Plan(wochentage=[1, 3]), date(2026, 10, 12))
    'nur Di Do'
    """
    if not plan.aktiv:
        return "deaktiviert"
    if tag.weekday() not in plan.wochentage:
        return f"nur {tage_text(plan.wochentage)}" if plan.wochentage else "an keinem Tag"
    return ""


# ---------------------------------------------------------------------------
# Reihenfolge und Mehrfachaufnahme (Ben, 14.10.2026: „am Anfang Rumpfbeuge
# und später wieder")
# ---------------------------------------------------------------------------
#
# Eine Übung darf mehrmals im Plan stehen. Einträge verweisen nur auf die
# Übung, nicht auf die Stelle im Plan — der Tag ist die Bezugsgröße. Darum
# gilt die k-te Stelle einer Übung als erledigt, sobald es heute k Einträge
# dieser Übung gibt: Wer die Rumpfbeuge zu Beginn macht, hakt die erste
# Stelle ab; die zweite wartet, bis sie ein zweites Mal dran war.


def vorkommen(items: Iterable[PlanItem]) -> dict[str, int]:
    """Die wievielte Stelle ihrer Übung jede Planübung ist (ab 1).

    >>> a, b, c = (PlanItem(exercise_id=x) for x in "ABA")
    >>> [vorkommen([a, b, c])[i.id] for i in (a, b, c)]
    [1, 1, 2]
    """
    gezaehlt: dict[str, int] = {}
    ergebnis: dict[str, int] = {}
    for item in items:
        gezaehlt[item.exercise_id] = gezaehlt.get(item.exercise_id, 0) + 1
        ergebnis[item.id] = gezaehlt[item.exercise_id]
    return ergebnis


def erledigte(items: Sequence[PlanItem], anzahl: Mapping[str, int]) -> set[str]:
    """IDs der Planübungen, die heute erledigt sind — ``anzahl`` = Einträge je Übung.

    >>> a, b, c = (PlanItem(exercise_id=x) for x in "ABA")
    >>> sorted(i.exercise_id for i in (a, b, c) if i.id in erledigte([a, b, c], {"A": 1}))
    ['A']
    >>> erledigte([a, b, c], {"A": 1}) == {a.id}
    True
    >>> len(erledigte([a, b, c], {"A": 3, "B": 1}))
    3
    """
    stelle = vorkommen(items)
    return {i.id for i in items if stelle[i.id] <= anzahl.get(i.exercise_id, 0)}


def verschoben(ids: Sequence[str], alt: int, neu: int) -> list[str]:
    """Die Reihenfolge, nachdem das Element an ``alt`` nach ``neu`` gewandert ist.

    ``neu`` ist die Endposition (so meldet sie `ReorderableListView`);
    außerhalb der Liste wird sie an den Rand gesetzt.

    >>> verschoben(["a", "b", "c", "d"], 0, 2)
    ['b', 'c', 'a', 'd']
    >>> verschoben(["a", "b", "c"], 2, 0), verschoben(["a", "b", "c"], 1, 9)
    (['c', 'a', 'b'], ['a', 'c', 'b'])
    """
    liste = list(ids)
    if not 0 <= alt < len(liste):
        return liste
    element = liste.pop(alt)
    liste.insert(min(max(neu, 0), len(liste)), element)
    return liste


def erste_offene(items: Sequence[PlanItem], anzahl: Mapping[str, int]) -> PlanItem | None:
    """Die erste Planübung, die heute noch offen ist — wohin ein Nachtrag gehört
    (`ui/views/nachtragen.py`, N25). ``None``: alles erledigt oder kein Plan.

    >>> a, b = (PlanItem(exercise_id=x) for x in "AB")
    >>> erste_offene([a, b], {"A": 1}) is b, erste_offene([a, b], {"A": 1, "B": 1}) is None
    (True, True)
    """
    fertig = erledigte(items, anzahl)
    return next((i for i in items if i.id not in fertig), None)


def nachtrag_vorwahl(
    gewuenscht: str | None,
    plaene: Sequence[str],
    offen: Iterable[str],
    gemacht_in: Sequence[str | None],
) -> str | None:
    """Welcher Plan beim Nachtragen vorgewählt ist: der übergebene, sonst einer, in dem die
    Übung an diesem Tag noch offen ist, sonst der, in dem sie zuletzt eingetragen wurde —
    erst dann „ohne Plan“ (Ben, 21.10.2026: Nach einem Training im Plan stand „ohne Plan“
    da, und der Nachtrag landete neben dem Plan).

    ``plaene``: die Pläne des Tags mit dieser Übung (wie die Chips sie zeigen); ``offen``:
    die davon, in denen sie noch offen ist; ``gemacht_in``: der Plan je Eintrag der Übung
    an diesem Tag, der älteste zuerst (``None``: ohne Plan).

    >>> nachtrag_vorwahl("p", ["p", "q"], [], [])
    'p'
    >>> nachtrag_vorwahl(None, ["p", "q"], ["q"], ["p"])
    'q'
    >>> nachtrag_vorwahl(None, ["p", "q"], [], ["q", None, "p", None])
    'p'
    >>> nachtrag_vorwahl(None, ["p"], [], [None]) is None
    True
    """
    if gewuenscht is not None and gewuenscht in plaene:
        return gewuenscht
    noch_offen = set(offen)
    if (plan := next((p for p in plaene if p in noch_offen), None)) is not None:
        return plan
    return next((p for p in reversed(gemacht_in) if p is not None and p in plaene), None)


def nachtrag_uhrzeit(
    am_tag: Sequence[datetime], frueher: Sequence[datetime], jetzt_: datetime | None = None
) -> time:
    """Die vorbelegte Uhrzeit beim Nachtragen einer Übung (Ben, 21.10.2026, P72: wie bei den
    Tagesfeldern „die alte Zeit als Vorlage“, `core.tagesfelder.uhrzeit_vorlage`): der Anfang
    ihres jüngsten Eintrags an dem Tag, sonst die Uhrzeit ihres jüngsten Eintrags überhaupt,
    sonst 12:00. Mit ``jetzt_`` (Nachtragen heute) nie später als jetzt.

    >>> from datetime import UTC
    >>> t = datetime(2026, 10, 19, 5, 30, tzinfo=UTC).astimezone()
    >>> nachtrag_uhrzeit([], [])
    datetime.time(12, 0)
    >>> nachtrag_uhrzeit([t], []) == nachtrag_uhrzeit([], [t]) == time(t.hour, t.minute)
    True
    >>> nachtrag_uhrzeit([], [], datetime(2026, 10, 21, 7, 5).astimezone())
    datetime.time(7, 5)
    """
    vorlage = UHRZEIT_NACHTRAGEN
    for liste in (am_tag, frueher):
        if liste:
            t = max(liste).astimezone()
            vorlage = time(t.hour, t.minute)
            break
    if jetzt_ is not None:
        lokal = jetzt_.astimezone()
        vorlage = min(vorlage, time(lokal.hour, lokal.minute))
    return vorlage


# ---------------------------------------------------------------------------
# Regeln der Übungsausführung (bis 19.10.2026 in `ui/views/plan.py`, N25)
# ---------------------------------------------------------------------------


def einzel_plan(uebung: Exercise) -> Plan:
    """Ein Plan, der nur in der Ansicht existiert: genau diese Übung, mit ihrem Standard.

    Für „Trainieren“ aus dem Katalog. Er wird nie gespeichert; die Einträge
    landen in der planlosen Session des Tages („Ohne Plan“). Die feste
    Planübungs-ID hält die gewählte Ausprägung über den Neubau der Ansicht.

    >>> u = Exercise(id="u1", name="Kniebeuge")
    >>> p = einzel_plan(u)
    >>> p.id, p.items[0].id, p.items[0].exercise_id
    ('einzel-u1', 'einzel-u1', 'u1')
    """
    return Plan(
        id=f"einzel-{uebung.id}",
        name=uebung.name,
        items=[
            PlanItem(id=f"einzel-{uebung.id}", exercise_id=uebung.id)  # folgt der Übung
        ],
    )


def auspraegung_vorgabe(
    wahl: dict[str, dict[str, Any]],
    item: PlanItem,
    uebung: Exercise,
    letzter: Callable[[], SessionEntry | None],
) -> dict[str, Any]:
    """Gewählte Ausprägungen — sonst aus dem Ziel, sonst wie beim letzten Mal.

    ``wahl`` ist die Auswahl je Planübung (`AppState.auspraegung_wahl`); fehlt die
    Planübung dort, wird sie hier eingetragen. ``letzter`` liefert den letzten Eintrag
    der Übung — erst gefragt, wenn das Ziel keine Ausprägung vorgibt. ``uebung`` so,
    wie die Planübung sie sieht (`core.standards.mit_plan_spec`). Gilt im Plan, beim
    Abhaken auf „Heute“ und beim Nachtragen gleich.

    >>> from trainingsapp.core.result_spec import FieldSpec, FieldType, ResultSpec
    >>> spec = ResultSpec(fields=[FieldSpec("w", FieldType.WEIGHT, "Gewicht"),
    ...                           FieldSpec("reps", FieldType.SET_LIST, "Wdh.")])
    >>> u = Exercise(id="u", result_spec=spec)
    >>> wahl: dict = {}
    >>> item = PlanItem(id="i", exercise_id="u", target={"w": 10, "reps": [12]})
    >>> auspraegung_vorgabe(wahl, item, u, lambda: None)
    {'w': 10}
    >>> ohne = PlanItem(id="j", exercise_id="u", target={"reps": [12]})
    >>> auspraegung_vorgabe(wahl, ohne, u, lambda: SessionEntry(result={"w": 15, "reps": [8]}))
    {'w': 15}
    >>> wahl["j"]["w"] = 20   # die Auswahl der Person gilt danach
    >>> auspraegung_vorgabe(wahl, ohne, u, lambda: None)
    {'w': 20}
    """
    felder = kontextfelder(replace(uebung.result_spec, fields=aktive_felder(item, uebung)))
    if not felder:
        return {}
    if item.id not in wahl:
        quelle: Mapping[str, Any] = ziel_von(item, uebung)
        if not any(not ist_leer(quelle.get(f.key)) for f in felder):
            eintrag = letzter()
            quelle = eintrag.result if eintrag is not None else {}
        wahl[item.id] = {f.key: quelle[f.key] for f in felder if not ist_leer(quelle.get(f.key))}
    keys = {f.key for f in felder}
    return {k: v for k, v in wahl[item.id].items() if k in keys}


def ziel_ohne_kontext(item: PlanItem, uebung: Exercise) -> dict[str, Any]:
    """Das Ziel ohne Ausprägungen — die bestimmt allein die Auswahl im Block.

    Sonst gewänne beim Eintragen der Winkel aus dem Ziel (90°) gegen den gerade
    gewählten (45°), und eine aufgehobene Auswahl käme über das Ziel zurück.

    >>> from trainingsapp.core.result_spec import FieldSpec, FieldType, ResultSpec
    >>> spec = ResultSpec(fields=[FieldSpec("angle", FieldType.DEGREES, "Winkel"),
    ...                           FieldSpec("hold", FieldType.SET_LIST, "Halten")])
    >>> ziel_ohne_kontext(PlanItem(target={"angle": 90, "hold": [30]}), Exercise(result_spec=spec))
    {'hold': [30]}
    """
    keys = {f.key for f in kontextfelder(uebung.result_spec)}
    return {k: v for k, v in ziel_von(item, uebung).items() if k not in keys}


def spaetere_stelle_offen(
    item: PlanItem, stelle: Mapping[str, int], fertig: Iterable[str], eigene: Iterable[str]
) -> bool:
    """Braucht diese Planübung einen **eigenen** Eintrag statt an den heutigen anzuhängen?

    Ja für die spätere Stelle einer Übung, die heute noch offen ist (D7) — aber nur
    einmal je Block: ``eigene`` sind die Blöcke, die heute schon einen eigenen Eintrag
    angelegt haben. ``stelle`` aus `vorkommen`, ``fertig`` aus `erledigte`.

    >>> a, b = PlanItem(id="a", exercise_id="x"), PlanItem(id="b", exercise_id="x")
    >>> stelle = vorkommen([a, b])
    >>> leer: set[str] = set()
    >>> spaetere_stelle_offen(a, stelle, leer, leer), spaetere_stelle_offen(b, stelle, leer, leer)
    (False, True)
    >>> spaetere_stelle_offen(b, stelle, {"b"}, leer), spaetere_stelle_offen(b, stelle, leer, {"b"})
    (False, False)
    """
    return stelle[item.id] > 1 and item.id not in set(fertig) and item.id not in set(eigene)


# ---------------------------------------------------------------------------
# Aus den Einträgen des Tages ableiten statt je Block neu abfragen (N24)
# ---------------------------------------------------------------------------
#
# Die Planansicht liest die Einträge des Tages einmal (`SessionRepo.eintraege_am_tag`)
# und leitet daraus ab, was sie vorher je Block einzeln abfragte. Die Regeln sind
# dieselben wie in `SessionRepo` (`anzahl_am_tag`, `_heute_im_plan`, `stand`,
# `ziel_eintrag`) — `tests/test_plan_regeln.py` vergleicht beide.


def anzahl_je_uebung(eintraege: Iterable[SessionEntry]) -> dict[str, int]:
    """Wie oft jede Übung dran war — wie `SessionRepo.anzahl_am_tag` aus den Einträgen.

    >>> anzahl_je_uebung([SessionEntry(exercise_id="a"), SessionEntry(exercise_id="a"),
    ...                   SessionEntry(exercise_id="b")])
    {'a': 2, 'b': 1}
    """
    return dict(Counter(e.exercise_id for e in eintraege))


def im_plan(
    eintraege: Iterable[tuple[SessionEntry, Session]], exercise_id: str, plan_id: str | None
) -> list[SessionEntry]:
    """Die Einträge dieser Übung in Sessions dieses Plans (``None`` = ohne Plan), der
    Reihe nach — wie `SessionRepo._heute_im_plan`.

    >>> p, frei = Session(id="s1", plan_id="p"), Session(id="s2")
    >>> def e(i, x): return SessionEntry(id=i, exercise_id=x)
    >>> liste = [(e("1", "a"), p), (e("2", "a"), frei), (e("3", "b"), p)]
    >>> [e.id for e in im_plan(liste, "a", "p")], [e.id for e in im_plan(liste, "a", None)]
    (['1'], ['2'])
    """
    return [e for e, s in eintraege if e.exercise_id == exercise_id and s.plan_id == plan_id]


def stand_im_plan(
    eintraege: Iterable[tuple[SessionEntry, Session]],
    uebung: Exercise,
    plan_id: str | None,
    kontext: Mapping[str, Any] | None,
    jetzt: datetime,
    offen_min: int = offene.OFFEN_MIN_VORGABE,
) -> offene.Stand:
    """Offener Eintrag und ob er zur gewählten Ausprägung passt — wie `SessionRepo.stand`,
    nur aus den schon gelesenen Einträgen des Tages. ``.offen`` ist, was
    `SessionRepo.offener_eintrag` liefert, ``.ziel``, was `ziel_eintrag`/`text_eintrag`
    liefern.

    >>> from datetime import UTC
    >>> from trainingsapp.core.result_spec import FieldSpec, FieldType, ResultSpec
    >>> spec = ResultSpec(fields=[FieldSpec("w", FieldType.WEIGHT, "Gewicht"),
    ...                           FieldSpec("reps", FieldType.SET_LIST, "Wdh.")])
    >>> u = Exercise(id="u", result_spec=spec)
    >>> t = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)
    >>> e = SessionEntry(exercise_id="u", result={"w": 10, "reps": [12]}, started_at=t,
    ...                  created_at=t)
    >>> liste = [(e, Session(id="s", plan_id="p"))]
    >>> stand_im_plan(liste, u, "p", {"w": 10}, t).zustand
    'markiert'
    >>> stand_im_plan(liste, u, "p", {"w": 15}, t).zustand
    'offen_anders'
    >>> stand_im_plan(liste, u, None, {}, t).zustand
    'keiner'
    """
    kontext = kontext or {}
    felder = {f.key for f in kontextfelder(uebung.result_spec)} | set(kontext)
    return offene.stand(im_plan(eintraege, uebung.id, plan_id), kontext, felder, jetzt, offen_min)


def letzter_heute(eintraege: Sequence[SessionEntry], exercise_id: str) -> SessionEntry | None:
    """Der jüngste Eintrag dieser Übung aus den (zeitlich sortierten) Einträgen des Tages —
    gibt es einen, ist er auch der letzte überhaupt (`SessionRepo.letzter_eintrag`);
    sonst ``None``, und die Datenbank muss gefragt werden.

    >>> liste = [SessionEntry(id="1", exercise_id="a"), SessionEntry(id="2", exercise_id="a")]
    >>> letzter_heute(liste, "a").id, letzter_heute(liste, "b")
    ('2', None)
    """
    return next((e for e in reversed(eintraege) if e.exercise_id == exercise_id), None)


__all__ = [
    "WOCHENTAGE_KURZ",
    "anzahl_je_uebung",
    "auspraegung_vorgabe",
    "einzel_plan",
    "erledigte",
    "erste_offene",
    "heutige_plaene",
    "im_plan",
    "letzter_heute",
    "nachtrag_uhrzeit",
    "nachtrag_vorwahl",
    "spaetere_stelle_offen",
    "stand_im_plan",
    "tage_text",
    "verschoben",
    "vorkommen",
    "warum_nicht",
    "ziel_ohne_kontext",
]
