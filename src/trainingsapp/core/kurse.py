"""Kurse — Kapitel, die man von oben nach unten durcharbeitet (Ben, 15.10.2026).

Neben Übungen (Vorratskammer) und Plänen (Rahmen für einen Tag) die dritte
Kategorie: Ein **Kurs** ist eine Folge von **Kapiteln**. Jedes Kapitel hat
Erklärtext (Markdown), Medien, optional **Plan-Vorlagen** — beim Erreichen des
Kapitels legt die App sie als echte Pläne an, beim Abschluss deaktiviert sie
sie — und eine **Bedingung**, die erfüllt sein muss, bevor das nächste
Kapitel aufgeht:

- ``gelesen`` — angesehen und mit „Weiter“ bestätigt (Erklärkapitel);
- ``summe`` — eine Menge einer Übung seit Kapitelstart („100 Liegestützen“),
  Varianten zählen mit;
- ``tage`` — an so vielen Tagen seit Kapitelstart geübt;
- ``messung`` — eine HRV-Messung von mindestens so vielen Minuten liegt vor.
  Geprüft wird nur, **dass** gemessen wurde, nie ein Messwert — eine Empfehlung
  aus Messwerten wäre ``physiologische_steuerung`` (`docs/recht`).

Überspringen: je Kurs ``frei`` (alle Kapitel offen), ``rueckfrage`` (ein
Dialog „Noch 60 von 100 — trotzdem freischalten?“) oder ``streng`` (gar nicht,
für zugewiesene Kurse in Edition B). Übersprungenes bleibt sichtbar.

Ein Kurs kann auch nur erklären — etwa, was die HRV-Messung ist und wie man
die App bedient. Dann sind alle Bedingungen ``gelesen``.

Hier steht nur Rechnung: Status der Kapitel, Stand einer Bedingung, Plan aus
Vorlage. Laden, Speichern und Datenbeschaffung macht `data/kurse.py`;
das Paketformat `core/pakete.py`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from . import links
from .models import (
    Exercise,
    HrvRecording,
    Media,
    MediaKind,
    MediaSource,
    Plan,
    PlanItem,
    SessionEntry,
    jetzt,
    new_id,
)
from .result_spec import FieldSpec, FieldType, vorrat_feld
from .tagesbilanz import menge_text, mengen

# -- Freischaltung (Spalte `course.unlock_mode`) --------------------------------
FREI = "frei"
RUECKFRAGE = "rueckfrage"
STRENG = "streng"
FREISCHALTUNGEN: dict[str, str] = {
    FREI: "Alle Kapitel offen",
    RUECKFRAGE: "Der Reihe nach — Überspringen auf Rückfrage",
    STRENG: "Der Reihe nach — kein Überspringen",
}

# -- Arten einer Bedingung -----------------------------------------------------
GELESEN = "gelesen"
SUMME = "summe"
TAGE = "tage"
MESSUNG = "messung"
BEDINGUNGEN = (GELESEN, SUMME, TAGE, MESSUNG)

# -- Status eines Kapitels -----------------------------------------------------
FERTIG = "fertig"
UEBERSPRUNGEN = "uebersprungen"
AKTUELL = "aktuell"
OFFEN = "offen"  # noch nicht dran, aber zugänglich (Freischaltung „frei“)
GESPERRT = "gesperrt"


# ---------------------------------------------------------------------------
# Modelle
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Bedingung:
    """Was erfüllt sein muss, damit ein Kapitel als abgeschlossen gilt.

    ``soll`` ist je Art: Menge (``summe``), Tage (``tage``), Minuten
    (``messung``); bei ``gelesen`` ohne Bedeutung.
    """

    art: str = GELESEN
    #: ``summe``: die Übung (Varianten zählen mit)
    exercise_id: str = ""
    #: ``summe``: welches Mengenfeld (Schlüssel aus dem Feldvorrat, z. B. ``reps``)
    feld: str = "reps"
    soll: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"art": self.art}
        if self.art == SUMME:
            d["uebung"] = self.exercise_id
            d["feld"] = self.feld
        if self.art != GELESEN:
            d["soll"] = self.soll
        return d

    @classmethod
    def from_dict(cls, roh: Mapping[str, Any]) -> Bedingung:
        """Liest, was `to_dict` schreibt; Unbekanntes gilt als ``gelesen``.

        >>> Bedingung.from_dict({"art": "summe", "uebung": "u1", "feld": "reps", "soll": 100})
        Bedingung(art='summe', exercise_id='u1', feld='reps', soll=100.0)
        >>> Bedingung.from_dict({}).art
        'gelesen'
        """
        art = str(roh.get("art") or GELESEN)
        if art not in BEDINGUNGEN:
            art = GELESEN
        try:
            soll = float(roh.get("soll") or 0)
        except (TypeError, ValueError):
            soll = 0.0
        if not math.isfinite(soll):  # 1e400, "inf", NaN — `int(soll)` stürzte später ab (K17)
            soll = 0.0
        return cls(
            art=art,
            exercise_id=str(roh.get("uebung") or roh.get("exercise_id") or ""),
            feld=str(roh.get("feld") or "reps"),
            soll=max(soll, 0.0),
        )


@dataclass(slots=True)
class VorlageItem:
    """Eine Übung in einer Plan-Vorlage — wie `PlanItem`, ohne Plan und ID."""

    exercise_id: str
    target: dict[str, Any] = field(default_factory=dict)
    #: Angebotene Parameter — ``None`` = wie die Übung, ``[]`` = nur abhaken
    felder: list[str] | None = None


@dataclass(slots=True)
class PlanVorlage:
    """Ein Plan, den ein Kapitel beim Erreichen anlegt (`plan_aus_vorlage`)."""

    name: str
    wochentage: list[int] = field(default_factory=lambda: list(range(7)))
    items: list[VorlageItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "wochentage": list(self.wochentage)}
        d["uebungen"] = [
            {
                "uebung": i.exercise_id,
                **({"ziel": i.target} if i.target else {}),
                **({"felder": list(i.felder)} if i.felder is not None else {}),
            }
            for i in self.items
        ]
        return d

    @classmethod
    def from_dict(cls, roh: Mapping[str, Any]) -> PlanVorlage:
        """Liest, was `to_dict` schreibt — Wochentage außerhalb 0–6 fallen weg.

        >>> v = PlanVorlage.from_dict({"name": "Atmung", "wochentage": [0, 2, 9]})
        >>> v.wochentage, v.items
        ([0, 2], [])
        """
        tage = roh.get("wochentage")
        wochentage = (
            sorted({int(t) for t in tage if isinstance(t, int) and 0 <= t <= 6})
            if isinstance(tage, list)
            else list(range(7))
        )
        items: list[VorlageItem] = []
        for e in roh.get("uebungen", []) or []:
            if not isinstance(e, Mapping) or not e.get("uebung"):
                continue
            felder = e.get("felder")
            items.append(
                VorlageItem(
                    exercise_id=str(e["uebung"]),
                    target=dict(e.get("ziel") or {}),
                    felder=None if felder is None else [str(k) for k in felder],
                )
            )
        return cls(name=str(roh.get("name") or "Plan"), wochentage=wochentage, items=items)


@dataclass(slots=True)
class Kapitel:
    id: str = field(default_factory=new_id)
    kurs_id: str = ""
    order: int = 0
    titel: str = ""
    #: Erklärtext als Markdown (`ft.Markdown` zeigt ihn an)
    text: str = ""
    media: list[Media] = field(default_factory=list)
    plaene: list[PlanVorlage] = field(default_factory=list)
    bedingung: Bedingung = field(default_factory=Bedingung)

    @property
    def uebungen(self) -> set[str]:
        """Die Übungen aller Plan-Vorlagen — für die Bedingung ``tage``."""
        return {i.exercise_id for p in self.plaene for i in p.items}


@dataclass(slots=True)
class Kurs:
    id: str = field(default_factory=new_id)
    name: str = ""
    beschreibung: str = ""
    freischaltung: str = RUECKFRAGE
    kapitel: list[Kapitel] = field(default_factory=list)
    #: Aus welchem Paket der Kurs kam (`core/pakete.py`); ``None`` = eigener Kurs
    package_id: str | None = None
    created_at: datetime = field(default_factory=jetzt)
    updated_at: datetime = field(default_factory=jetzt)
    deleted_at: datetime | None = None

    def kapitel_mit(self, kapitel_id: str) -> Kapitel | None:
        return next((k for k in self.kapitel if k.id == kapitel_id), None)


@dataclass(slots=True)
class Kapitelstand:
    """Der Fortschritt eines Profils in einem Kapitel (Tabelle ``course_progress``)."""

    kapitel_id: str
    erreicht: datetime
    abgeschlossen: datetime | None = None
    uebersprungen: bool = False


@dataclass(slots=True)
class Stand:
    """Wie weit eine Bedingung erfüllt ist: ``ist`` von ``soll``."""

    ist: float = 0.0
    soll: float = 0.0

    @property
    def erfuellt(self) -> bool:
        return self.ist >= self.soll

    @property
    def fehlt(self) -> float:
        return max(self.soll - self.ist, 0.0)


# ---------------------------------------------------------------------------
# Status der Kapitel
# ---------------------------------------------------------------------------


def status(kurs: Kurs, staende: Mapping[str, Kapitelstand]) -> dict[str, str]:
    """Status je Kapitel-ID: fertig, übersprungen, aktuell, offen oder gesperrt.

    Abgeschlossene Kapitel sind ``fertig`` (oder ``uebersprungen``); das erste
    nicht abgeschlossene ist ``aktuell``; alles danach ``gesperrt`` — bei
    Freischaltung „frei“ stattdessen ``offen``.

    >>> k = Kurs(kapitel=[Kapitel(titel=t) for t in "ABC"])
    >>> a, b, c = k.kapitel
    >>> fertig = Kapitelstand(a.id, jetzt(), abgeschlossen=jetzt())
    >>> [status(k, {a.id: fertig})[x.id] for x in (a, b, c)]
    ['fertig', 'aktuell', 'gesperrt']
    >>> k.freischaltung = FREI
    >>> status(k, {})[c.id]
    'offen'
    """
    ergebnis: dict[str, str] = {}
    aktuell_vergeben = False
    for kapitel in kurs.kapitel:
        stand = staende.get(kapitel.id)
        if stand is not None and stand.abgeschlossen is not None:
            ergebnis[kapitel.id] = UEBERSPRUNGEN if stand.uebersprungen else FERTIG
        elif not aktuell_vergeben:
            ergebnis[kapitel.id] = AKTUELL
            aktuell_vergeben = True
        else:
            ergebnis[kapitel.id] = OFFEN if kurs.freischaltung == FREI else GESPERRT
    return ergebnis


def aktuelles(kurs: Kurs, staende: Mapping[str, Kapitelstand]) -> Kapitel | None:
    """Das Kapitel, das gerade dran ist — ``None``, wenn der Kurs abgeschlossen ist."""
    stati = status(kurs, staende)
    return next((k for k in kurs.kapitel if stati[k.id] == AKTUELL), None)


def naechstes(kurs: Kurs, kapitel: Kapitel) -> Kapitel | None:
    """Das Kapitel nach diesem — ``None`` am Ende.

    >>> k = Kurs(kapitel=[Kapitel(titel="A"), Kapitel(titel="B")])
    >>> naechstes(k, k.kapitel[0]).titel, naechstes(k, k.kapitel[1])
    ('B', None)
    """
    ids = [k.id for k in kurs.kapitel]
    if kapitel.id not in ids:
        return None
    i = ids.index(kapitel.id) + 1
    return kurs.kapitel[i] if i < len(kurs.kapitel) else None


def begonnen(staende: Mapping[str, Kapitelstand]) -> bool:
    return bool(staende)


def abgeschlossen(kurs: Kurs, staende: Mapping[str, Kapitelstand]) -> bool:
    """Alle Kapitel abgeschlossen (auch übersprungen) — und es gibt welche."""
    return bool(kurs.kapitel) and all(
        (s := staende.get(k.id)) is not None and s.abgeschlossen is not None for k in kurs.kapitel
    )


def fortschritt_text(kurs: Kurs, staende: Mapping[str, Kapitelstand]) -> str:
    """„noch nicht begonnen“, „Kapitel 3 von 7“, „abgeschlossen“.

    >>> k = Kurs(kapitel=[Kapitel(titel=t) for t in "ABC"])
    >>> fortschritt_text(k, {})
    'noch nicht begonnen'
    >>> a = k.kapitel[0]
    >>> fortschritt_text(k, {a.id: Kapitelstand(a.id, jetzt(), abgeschlossen=jetzt())})
    'Kapitel 2 von 3'
    """
    if not kurs.kapitel:
        return "noch ohne Kapitel"
    if not begonnen(staende):
        return "noch nicht begonnen"
    if abgeschlossen(kurs, staende):
        return "abgeschlossen"
    aktuell = aktuelles(kurs, staende)
    nummer = kurs.kapitel.index(aktuell) + 1 if aktuell is not None else len(kurs.kapitel)
    return f"Kapitel {nummer} von {len(kurs.kapitel)}"


# ---------------------------------------------------------------------------
# Bedingung rechnen
# ---------------------------------------------------------------------------


def bedingung_stand(
    bedingung: Bedingung,
    seit: datetime | None,
    eintraege: Iterable[tuple[date, SessionEntry]] = (),
    messungen: Iterable[HrvRecording] = (),
    familie: Iterable[str] = (),
    plan_uebungen: Iterable[str] = (),
) -> Stand:
    """Wie weit die Bedingung erfüllt ist — gerechnet ab ``seit`` (Kapitelstart).

    ``eintraege`` sind gültige Einträge mit ihrem lokalen Tag (wie
    `SessionRepo.eintraege_zwischen`), ``familie`` die Übung der Bedingung samt
    Varianten, ``plan_uebungen`` die Übungen der Kapitelpläne (für ``tage``;
    leer = jeder Eintrag zählt). ``seit=None`` heißt: Kapitel noch nicht
    erreicht — nichts zählt.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> from datetime import UTC, timedelta
    >>> t0 = datetime(2026, 10, 12, 8, tzinfo=UTC)
    >>> e = [(date(2026, 10, 12 + i), SessionEntry(exercise_id="l", result={"reps": [20, 20]},
    ...       spec_snapshot=SPEC_SAETZE_WDH, started_at=t0 + timedelta(days=i))) for i in range(3)]
    >>> b = Bedingung(SUMME, "l", "reps", 100)
    >>> s = bedingung_stand(b, t0, e, familie={"l"})
    >>> (s.ist, s.soll, s.erfuellt)
    (120.0, 100.0, True)
    >>> bedingung_stand(b, t0 + timedelta(days=1), e, familie={"l"}).ist  # ab Tag 2
    80.0
    >>> bedingung_stand(Bedingung(TAGE, soll=3), t0, e).ist
    3.0
    >>> bedingung_stand(Bedingung(GELESEN), None).erfuellt
    True
    """
    if bedingung.art == GELESEN:
        return Stand(0.0, 0.0)
    soll = float(bedingung.soll)
    if seit is None:
        return Stand(0.0, soll)
    ab = [(t, e) for t, e in eintraege if e.started_at is not None and e.started_at >= seit]
    if bedingung.art == SUMME:
        ids = set(familie) or {bedingung.exercise_id}
        summe = sum(
            mengen(e.spec_snapshot, e.result).get(bedingung.feld, 0.0)
            for _, e in ab
            if e.exercise_id in ids
        )
        return Stand(summe, soll)
    if bedingung.art == TAGE:
        ids = set(plan_uebungen)
        tage = {t for t, e in ab if not ids or e.exercise_id in ids}
        return Stand(float(len(tage)), soll)
    if bedingung.art == MESSUNG:
        passt = any(m.started_at >= seit and m.duration_s >= soll * 60 for m in messungen)
        return Stand(soll if passt else 0.0, soll)
    return Stand(0.0, soll)


def bedingung_text(bedingung: Bedingung, uebung: Exercise | None = None) -> str:
    """Die Bedingung in Worten: „100 Wdh. Liegestütz“, „an 3 Tagen üben“, „5 min messen“.

    >>> bedingung_text(Bedingung(TAGE, soll=3))
    'an 3 Tagen üben'
    >>> bedingung_text(Bedingung(MESSUNG, soll=5))
    'eine HRV-Messung von 5 min'
    >>> bedingung_text(Bedingung(SUMME, "l", "reps", 100), Exercise(name="Liegestütz"))
    '100 Wdh. Liegestütz'
    """
    if bedingung.art == SUMME:
        name = uebung.name if uebung is not None else "der Übung"
        return f"{menge_text(_feld(bedingung, uebung), bedingung.soll)} {name}"
    if bedingung.art == TAGE:
        n = int(bedingung.soll)
        return f"an {n} {'Tag' if n == 1 else 'Tagen'} üben"
    if bedingung.art == MESSUNG:
        return f"eine HRV-Messung von {bedingung.soll:g} min"
    return "Kapitel ansehen"


def stand_text(bedingung: Bedingung, stand: Stand, uebung: Exercise | None = None) -> str:
    """„60 von 100 Wdh.“, „2 von 3 Tagen“, „noch keine Messung von 5 min“.

    >>> stand_text(Bedingung(SUMME, "l", "reps", 100), Stand(60, 100))
    '60 von 100 Wdh.'
    >>> stand_text(Bedingung(TAGE, soll=3), Stand(3, 3))
    '3 von 3 Tagen'
    >>> stand_text(Bedingung(MESSUNG, soll=5), Stand(0, 5))
    'noch keine Messung von 5 min'
    """
    if bedingung.art == SUMME:
        f = _feld(bedingung, uebung)
        return f"{menge_text(f, stand.ist).split(' ', 1)[0]} von {menge_text(f, stand.soll)}"
    if bedingung.art == TAGE:
        return f"{stand.ist:g} von {stand.soll:g} Tagen"
    if bedingung.art == MESSUNG:
        if stand.erfuellt:
            return f"Messung von {stand.soll:g} min liegt vor"
        return f"noch keine Messung von {stand.soll:g} min"
    return ""


def fehlt_text(bedingung: Bedingung, stand: Stand, uebung: Exercise | None = None) -> str:
    """Was zum Freischalten noch fehlt — für die Rückfrage beim Überspringen.

    >>> fehlt_text(Bedingung(SUMME, "l", "reps", 100), Stand(40, 100))
    'Noch 60 Wdh.'
    >>> fehlt_text(Bedingung(TAGE, soll=3), Stand(1, 3))
    'Noch 2 Tage'
    """
    if bedingung.art == SUMME:
        return f"Noch {menge_text(_feld(bedingung, uebung), stand.fehlt)}"
    if bedingung.art == TAGE:
        n = int(stand.fehlt)
        return f"Noch {n} {'Tag' if n == 1 else 'Tage'}"
    if bedingung.art == MESSUNG:
        return f"Noch keine Messung von {stand.soll:g} min"
    return ""


def _feld(bedingung: Bedingung, uebung: Exercise | None) -> FieldSpec:
    f = uebung.result_spec.field_by_key(bedingung.feld) if uebung is not None else None
    if f is None:
        f = vorrat_feld(bedingung.feld)
    return f or FieldSpec(key=bedingung.feld, type=FieldType.FLOAT, label=bedingung.feld)


# ---------------------------------------------------------------------------
# Pläne aus Vorlagen
# ---------------------------------------------------------------------------


def plan_aus_vorlage(
    vorlage: PlanVorlage, kapitel: Kapitel, subject_id: str, vorhandene: Iterable[str]
) -> Plan:
    """Der echte Plan zu einer Vorlage — nur mit Übungen, die es hier gibt.

    >>> v = PlanVorlage("Atmung", [0, 2, 4], [VorlageItem("a"), VorlageItem("fehlt")])
    >>> p = plan_aus_vorlage(v, Kapitel(id="k1"), "s1", {"a"})
    >>> (p.name, p.wochentage, [i.exercise_id for i in p.items], p.kurs_kapitel_id)
    ('Atmung', [0, 2, 4], ['a'], 'k1')
    """
    da = set(vorhandene)
    plan = Plan(
        name=vorlage.name,
        subject_id=subject_id,
        wochentage=list(vorlage.wochentage),
        kurs_kapitel_id=kapitel.id,
    )
    for nr, item in enumerate(i for i in vorlage.items if i.exercise_id in da):
        plan.items.append(
            PlanItem(
                plan_id=plan.id,
                exercise_id=item.exercise_id,
                order=nr,
                target=dict(item.target),
                felder=None if item.felder is None else list(item.felder),
            )
        )
    return plan


# ---------------------------------------------------------------------------
# Medien als JSON (Spalte `course_chapter.media_json`)
# ---------------------------------------------------------------------------


def medien_to_list(media: Iterable[Media]) -> list[dict[str, Any]]:
    return [
        {
            "kind": str(m.kind),
            "source": str(m.source),
            "uri": m.uri,
            "title": m.title,
            **({"license": m.license} if m.license else {}),
        }
        for m in media
        if m.uri
    ]


def medien_from_list(roh: Any) -> list[Media]:
    """Liest Medien; Unlesbares fällt weg, Dateien vom Ursprungsgerät (``local``) auch.

    Ebenso ein Link, den die App nicht öffnen darf (`links.erlaubt`: nur ``https://``
    und ``mailto:``) — still, damit ein ``intent://`` im Paket nicht das Kapitel kostet
    (S1). Das gilt beim Import wie beim Lesen aus der Datenbank.

    >>> roh = [{"kind": "audio", "uri": "https://x/a.mp3"}, {"uri": ""}]
    >>> [str(m.kind) for m in medien_from_list(roh)]
    ['audio']
    >>> medien_from_list([{"uri": "intent://scan/#Intent;end"}])
    []
    """
    ergebnis: list[Media] = []
    if not isinstance(roh, list):
        return ergebnis
    for d in roh:
        if not isinstance(d, Mapping):
            continue
        uri = str(d.get("uri") or "").strip()
        try:
            art = MediaKind(d.get("kind", "video"))
            quelle = MediaSource(d.get("source", "url"))
        except ValueError:
            continue
        if not uri or quelle == MediaSource.LOCAL or not links.erlaubt(uri):
            continue
        ergebnis.append(
            Media(
                kind=art,
                source=quelle,
                uri=uri,
                title=str(d.get("title") or ""),
                license=str(d.get("license") or ""),
            )
        )
    return ergebnis


__all__ = [
    "AKTUELL",
    "BEDINGUNGEN",
    "FERTIG",
    "FREI",
    "FREISCHALTUNGEN",
    "GELESEN",
    "GESPERRT",
    "MESSUNG",
    "OFFEN",
    "RUECKFRAGE",
    "STRENG",
    "SUMME",
    "TAGE",
    "UEBERSPRUNGEN",
    "Bedingung",
    "Kapitel",
    "Kapitelstand",
    "Kurs",
    "PlanVorlage",
    "Stand",
    "VorlageItem",
    "abgeschlossen",
    "aktuelles",
    "bedingung_stand",
    "bedingung_text",
    "begonnen",
    "fehlt_text",
    "fortschritt_text",
    "medien_from_list",
    "medien_to_list",
    "naechstes",
    "plan_aus_vorlage",
    "stand_text",
    "status",
]
