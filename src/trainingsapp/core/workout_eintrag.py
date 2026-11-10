"""Der Workout-Eintrag: ein Durchlauf eines Workouts, gelesen aus der Zeitleiste seiner Einheit
(Ben, 10.11.2026, `docs/plan_workout_eintrag.md`).

Grundregel: **Werte gehören der Übung, der Verlauf gehört dem Workout.** Was in einem Schritt
geleistet wurde, steht im Tagebucheintrag der Übung (`session_entry`) — der Durchlauf kennt nur
dessen ID. Er selbst sagt, was eine Übung nicht wissen kann: die gegangene Reihenfolge, die Zeit
je Schritt, Übersprungenes, Fragen mit Antwort und ob er vorzeitig endete. Dazu trägt die Person
Werte zum Workout als Ganzem ein (`WorkoutWerte`, Tabelle `workout_entry`, Migration 053) — zuerst
die Anstrengung (sRPE). Keine Deutung, keine Last: nur, was eingetragen wurde.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from .result_spec import FieldSpec, FieldType, Layout, ResultSpec

#: Gründe, mit denen ein Schritt ins Tagebuch kam (`devices.plan_ablauf`)
EINGETRAGEN: Final[tuple[str, ...]] = ("fertig", "gemacht")

#: Schlüssel der Anstrengung im Ergebnis eines Workout-Eintrags
SRPE: Final[str] = "srpe"

UEBUNG, FRAGE = "uebung", "frage"


def spec() -> ResultSpec:
    """Die Felder eines Workout-Eintrags — zuerst nur die Anstrengung (CR10, 0–10).

    >>> [f.key for f in spec().fields], spec().fields[0].max
    (['srpe'], 10)
    """
    return ResultSpec(
        layout=Layout.SINGLE,
        fields=[FieldSpec(SRPE, FieldType.SCALE, "Anstrengung (sRPE)", min=0, max=10, step=1)],
    )


@dataclass(frozen=True, slots=True)
class WorkoutWerte:
    """Was zum Workout als Ganzem eingetragen ist — die jüngste Zeile zählt."""

    einheit_id: str
    result: dict[str, Any] = field(default_factory=dict)
    note: str = ""
    spec: ResultSpec = field(default_factory=spec)
    id: str = ""
    created_at: datetime | None = None

    @property
    def srpe(self) -> int | None:
        """Die Anstrengung, falls eingetragen.

        >>> WorkoutWerte("e", {"srpe": 6}).srpe, WorkoutWerte("e").srpe
        (6, None)
        >>> WorkoutWerte("e", {"srpe": "x"}).srpe is None
        True
        """
        wert = self.result.get(SRPE)
        try:
            return None if wert is None else int(wert)
        except (TypeError, ValueError):
            return None

    @property
    def leer(self) -> bool:
        return self.srpe is None and not self.note.strip()


@dataclass(frozen=True, slots=True)
class Zeile:
    """Ein Schritt des Durchlaufs, in gegangener Reihenfolge."""

    art: str
    item_id: str
    name: str
    #: Stelle in der Liste des Plans (1 …), 0 = unbekannt oder eine Frage
    stelle: int = 0
    #: das wievielte Mal in diesem Durchlauf (Schleifen)
    mal: int = 1
    #: wie der Schritt endete (`ui.plan_ablauf.GRUENDE`) — leer: lief noch, als die App endete
    grund: str = ""
    von_s: float = 0.0
    bis_s: float | None = None
    uebung_id: str = ""
    #: die Tagebucheinträge dieses Schritts — dort stehen die Werte
    eintrag_ids: tuple[str, ...] = ()
    #: Antwort auf eine Frage (Skala), ``None`` ohne
    antwort: float | None = None

    @property
    def dauer_s(self) -> float | None:
        return None if self.bis_s is None else max(0.0, self.bis_s - self.von_s)

    @property
    def eingetragen(self) -> bool:
        return self.art == UEBUNG and self.grund in EINGETRAGEN


@dataclass(frozen=True, slots=True)
class Durchlauf:
    """Ein Workout, wie es gelaufen ist."""

    einheit_id: str
    plan_id: str
    name: str
    beginn: datetime
    ende: datetime | None
    zeilen: tuple[Zeile, ...]
    #: endete vorzeitig — die Planübung, bei der es weiterginge (`core.ablauf.fortsetzung`)
    bei: str = ""
    #: setzt ein vorzeitig beendetes Workout desselben Tags fort (`fortsetzungen_markieren`)
    fortgesetzt: bool = False

    @property
    def vorzeitig(self) -> bool:
        return bool(self.bei)

    @property
    def dauer_s(self) -> float:
        """Vom Start bis zum Ende — ohne Ende bis zum letzten Schritt."""
        if self.ende is not None:
            return max(0.0, (self.ende - self.beginn).total_seconds())
        return max((z.bis_s or z.von_s for z in self.zeilen), default=0.0)

    @property
    def uebungen(self) -> int:
        """Wie viele Übungen eingetragen wurden — eine wiederholte zählt einmal."""
        return len({z.item_id for z in self.zeilen if z.eingetragen})

    @property
    def eintrag_ids(self) -> frozenset[str]:
        return frozenset(i for z in self.zeilen for i in z.eintrag_ids)

    def schritt_von(self, eintrag_id: str) -> Zeile | None:
        """Der Schritt, in dem dieser Tagebucheintrag entstand."""
        return next((z for z in self.zeilen if eintrag_id in z.eintrag_ids), None)


def durchlauf(
    einheit_id: str, beginn: datetime, ende: datetime | None, ereignisse: Iterable[Any]
) -> Durchlauf | None:
    """Der Durchlauf aus der Zeitleiste einer Einheit (`core.einheit.Ereignis`: ``t_s``,
    ``quelle``, ``art``, ``text``, ``daten``) — ``None``, wenn sie kein Workout war oder nichts
    daraus ins Tagebuch kam (gleich wieder abgebrochen: kein Eintrag).

    >>> from types import SimpleNamespace as E
    >>> from datetime import UTC, timedelta
    >>> p = {"plan": "p", "workout": True}
    >>> def u(t, art, k, **d): return E(t_s=t, quelle="plan", art=art, text="",
    ...     daten={**p, "planuebung": k, "name": k.upper(), "stelle": 1, **d})
    >>> roh = [E(t_s=0.0, quelle="plan", art="start", text="Beine", daten=p),
    ...        u(0.0, "uebung_start", "a"), u(60.0, "uebung_ende", "a", grund="fertig"),
    ...        E(t_s=60.0, quelle="person", art="eintrag", text="", daten={"eintrag": "e1",
    ...                                                                  "planuebung": "a"}),
    ...        u(60.0, "frage", "f", frage="Noch eine?"),
    ...        u(65.0, "antwort", "f", grund="beantwortet", wert=7),
    ...        u(65.0, "uebung_start", "a"), u(90.0, "uebung_ende", "a", grund="uebersprungen"),
    ...        E(t_s=90.0, quelle="plan", art="ende", text="Beine", daten={**p, "bei": "b"})]
    >>> t0 = datetime(2026, 11, 10, 10, 5, tzinfo=UTC)
    >>> d = durchlauf("x", t0, t0 + timedelta(seconds=90), roh)
    >>> d.name, d.uebungen, d.vorzeitig, d.dauer_s
    ('Beine', 1, True, 90.0)
    >>> [(z.art, z.name, z.mal, z.grund, z.dauer_s) for z in d.zeilen]
    ... # doctest: +NORMALIZE_WHITESPACE
    [('uebung', 'A', 1, 'fertig', 60.0), ('frage', 'Noch eine?', 1, 'beantwortet', 5.0),
     ('uebung', 'A', 2, 'uebersprungen', 25.0)]
    >>> [z.eintrag_ids for z in d.zeilen]
    [('e1',), (), ()]
    >>> d.zeilen[1].antwort, d.schritt_von("e1").stelle
    (7.0, 1)
    >>> durchlauf("x", t0, None, roh[:2]) is None, durchlauf("x", t0, None, []) is None
    (True, True)
    """
    plan_id, name, bei = "", "", ""
    zeilen: list[dict[str, Any]] = []
    for e in ereignisse:
        daten = getattr(e, "daten", None) or {}
        quelle, art = getattr(e, "quelle", ""), getattr(e, "art", "")
        t = float(getattr(e, "t_s", 0.0) or 0.0)
        if quelle == "plan" and art == "start" and daten.get("workout") and not plan_id:
            plan_id, name = str(daten.get("plan") or ""), str(getattr(e, "text", "") or "")
            continue
        if not plan_id:
            continue
        item = str(daten.get("planuebung") or "")
        if quelle == "plan" and art in ("uebung_start", "frage") and item:
            frage = art == "frage"
            zeilen.append(
                {
                    "art": FRAGE if frage else UEBUNG,
                    "item_id": item,
                    "name": str(daten.get("frage") if frage else daten.get("name") or "") or "?",
                    "stelle": 0 if frage else int(daten.get("stelle") or 0),
                    "mal": 1 + sum(1 for z in zeilen if z["item_id"] == item),
                    "von_s": t,
                    "uebung_id": str(daten.get("uebung") or ""),
                    "eintrag_ids": (),
                }
            )
        elif quelle == "plan" and art in ("uebung_ende", "antwort") and item:
            offen = _letzte(zeilen, item, offen=True)
            if offen is not None:
                offen["bis_s"] = t
                offen["grund"] = str(daten.get("grund") or "")
                if art == "antwort" and daten.get("wert") is not None:
                    try:
                        offen["antwort"] = float(daten["wert"])
                    except (TypeError, ValueError):
                        offen["antwort"] = None
        elif quelle == "person" and art == "eintrag" and item and daten.get("eintrag"):
            ziel = _letzte(zeilen, item)
            if ziel is not None:
                ziel["eintrag_ids"] = (*ziel["eintrag_ids"], str(daten["eintrag"]))
        elif quelle == "plan" and art == "ende":
            bei = str(daten.get("bei") or "")
    fertig = tuple(Zeile(**z) for z in zeilen)
    if not plan_id or not any(z.eingetragen for z in fertig):
        return None
    return Durchlauf(einheit_id, plan_id, name, beginn, ende, fertig, bei)


def _letzte(
    zeilen: list[dict[str, Any]], item: str, *, offen: bool = False
) -> dict[str, Any] | None:
    return next(
        (
            z
            for z in reversed(zeilen)
            if z["item_id"] == item and not (offen and z.get("bis_s") is not None)
        ),
        None,
    )


def fortsetzungen_markieren(laeufe: Sequence[Durchlauf]) -> list[Durchlauf]:
    """Die Durchläufe eines Tags in der Reihenfolge ihres Beginns — ``fortgesetzt`` trägt, wer
    auf ein vorzeitig beendetes Workout desselben Plans folgt.

    >>> from datetime import UTC, timedelta
    >>> t = datetime(2026, 11, 10, 10, tzinfo=UTC)
    >>> z = (Zeile(UEBUNG, "a", "A", grund="fertig"),)
    >>> a = Durchlauf("1", "p", "P", t, None, z, bei="b")
    >>> b = Durchlauf("2", "p", "P", t + timedelta(hours=1), None, z)
    >>> c = Durchlauf("3", "p", "P", t + timedelta(hours=2), None, z)
    >>> [(d.einheit_id, d.fortgesetzt) for d in fortsetzungen_markieren([c, b, a])]
    [('1', False), ('2', True), ('3', False)]
    """
    out: list[Durchlauf] = []
    offen: dict[str, bool] = {}
    for d in sorted(laeufe, key=lambda d: d.beginn):
        fort = offen.get(d.plan_id, False)
        out.append(
            Durchlauf(d.einheit_id, d.plan_id, d.name, d.beginn, d.ende, d.zeilen, d.bei, fort)
        )
        offen[d.plan_id] = d.vorzeitig
    return out


def minuten_text(sekunden: float) -> str:
    """``27 min``, unter einer Minute ``40 s``.

    >>> minuten_text(27 * 60 + 20), minuten_text(40), minuten_text(3700)
    ('27 min', '40 s', '1 h 01 min')
    """
    s = max(0, round(sekunden))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{round(s / 60)} min"
    return f"{s // 3600} h {s % 3600 // 60:02d} min"


def kurz(d: Durchlauf) -> str:
    """Die zweite Zeile des Eintrags: ``27 min · 3 Übungen · vorzeitig beendet``.

    >>> from datetime import UTC, timedelta
    >>> t = datetime(2026, 11, 10, 10, tzinfo=UTC)
    >>> z = (Zeile(UEBUNG, "a", "A", grund="fertig"),)
    >>> kurz(Durchlauf("1", "p", "P", t, t + timedelta(minutes=5), z, bei="b", fortgesetzt=True))
    '5 min · 1 Übung · fortgesetzt · vorzeitig beendet'
    """
    n = d.uebungen
    teile = [minuten_text(d.dauer_s), f"{n} Übung" if n == 1 else f"{n} Übungen"]
    if d.fortgesetzt:
        teile.append("fortgesetzt")
    if d.vorzeitig:
        teile.append("vorzeitig beendet")
    return " · ".join(teile)


__all__ = [
    "EINGETRAGEN",
    "FRAGE",
    "SRPE",
    "UEBUNG",
    "Durchlauf",
    "WorkoutWerte",
    "Zeile",
    "durchlauf",
    "fortsetzungen_markieren",
    "kurz",
    "minuten_text",
    "spec",
]
