"""Das Tagebuch — alle Notizen, nach Tagen oder nach Übungen (Ben, 18.10.2026).

Ben: „Der für mich wichtigste Teil fehlt, das Tagebuch. Hier wird geschrieben, diktiert,
reflektiert …“ — als dritter Reiter im Verlauf. Das Tagebuch ist keine eigene Tabelle
(Migration 003): Es fragt die drei Ebenen der Notizen ab — zum Tag (`day_note`), zum Plan
an einem Tag (`session.note`) und zur Übung (`session_entry.note`) — und ordnet sie:

- **nach Tagen** (`nach_tagen`): der neueste Tag oben; im Tag zuerst die Notiz zum Tag,
  dann die übrigen nach der Uhr (ein Zeitstrahl wie die Zeitleiste auf „Heute“);
- **nach Übungen** (`nach_uebungen`): je Übung und je Plan eine Gruppe, die zuletzt
  beschriebene oben, darin die neueste Notiz zuerst; die Notizen zum Tag für sich.

Hier steht nur Ordnen; Lesen macht `data` (`SessionRepo.notizen`, `DayNoteRepo.alle`),
Zeigen `ui/views/tagebuch.py`. **Aufnahmen** (Fotos und Videos an Einträgen, Ben
19.10.2026, `core/anhaenge.py`) sind eine vierte Art: je Eintrag mit Anhängen eine
Notiz der Art `AUFNAHME`, deren Text die Anzahl nennt — die Ansicht zeigt dafür die
Frontbilder, nie ein laufendes Video. Nach Übungen geordnet stehen sie unter der Übung.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .anhaenge import AnhangMitBezug, anzahl_text, zusammenfassung
from .models import Session, SessionEntry, lokaler_tag

#: Woran eine Notiz hängt — `AUFNAHME`: Fotos und Videos an einem Eintrag
TAG, PLAN, UEBUNG, AUFNAHME = "tag", "plan", "uebung", "aufnahme"


@dataclass(frozen=True, slots=True)
class Notiz:
    """Ein Eintrag im Tagebuch."""

    tag: date
    art: str
    text: str
    #: wann — die Übung: ihr Eintrag; der Plan: sein erster Eintrag; der Tag: angelegt
    zeit: datetime | None = None
    exercise_id: str | None = None
    plan_id: str | None = None
    #: woran sie gespeichert ist (Eintrag bzw. Session) — zum Bearbeiten
    bezug_id: str | None = None

    def sortierzeit(self) -> float:
        return self.zeit.timestamp() if self.zeit is not None else 0.0


@dataclass(frozen=True, slots=True)
class Tagesgruppe:
    """Ein Tag im Tagebuch: zuerst die Notiz zum Tag, dann nach der Uhr."""

    tag: date
    notizen: tuple[Notiz, ...]


@dataclass(frozen=True, slots=True)
class Gruppe:
    """Eine Übung (oder ein Plan, oder „zum Tag“) mit ihren Notizen, die neueste zuerst."""

    art: str
    #: Übungs- bzw. Plan-ID; ``None`` für die Notizen zum Tag
    schluessel: str | None
    notizen: tuple[Notiz, ...]


def sammeln(
    tage: Iterable[tuple[date, str, datetime | None]],
    sessions: Iterable[tuple[Session, datetime | None]],
    eintraege: Iterable[tuple[SessionEntry, Session]],
    aufnahmen: Iterable[AnhangMitBezug] = (),
) -> list[Notiz]:
    """Die Ebenen als Notizen — ``tage`` (Tag, Text, angelegt), ``sessions`` (mit ihrem
    ersten Eintrag), ``eintraege`` (mit ihrer Session), ``aufnahmen`` (Anhänge mit ihrem
    Eintrag — je Eintrag eine Notiz `AUFNAHME`). Leere Notizen fallen weg.

    >>> from datetime import UTC
    >>> from .anhaenge import Anhang
    >>> s = Session(id="s1", plan_id="p", note="zäh",
    ...             started_at=datetime(2026, 10, 17, 7, tzinfo=UTC))
    >>> e = SessionEntry(id="e1", session_id="s1", exercise_id="kb", note="eng",
    ...                  started_at=datetime(2026, 10, 17, 7, 5, tzinfo=UTC))
    >>> n = sammeln([(date(2026, 10, 17), "müde", None)], [(s, None)], [(e, s)])
    >>> [(x.art, x.text, x.bezug_id) for x in n]
    [('tag', 'müde', None), ('plan', 'zäh', 's1'), ('uebung', 'eng', 'e1')]
    >>> [(x.plan_id, x.exercise_id) for x in n]
    [(None, None), ('p', None), ('p', 'kb')]
    >>> a = AnhangMitBezug(Anhang("e1", aufgenommen=e.started_at), "kb", e.started_at)
    >>> b = AnhangMitBezug(Anhang("e1", "video", aufgenommen=e.started_at), "kb", e.started_at)
    >>> [(x.art, x.text, x.bezug_id, x.exercise_id) for x in sammeln([], [], [], [a, b])]
    [('aufnahme', '1 Foto, 1 Video', 'e1', 'kb')]
    """
    ergebnis = [Notiz(t, TAG, text.strip(), zeit) for t, text, zeit in tage if text.strip()]
    for s, erst in sessions:
        if s.note.strip():
            zeit = erst or s.started_at
            ergebnis.append(
                Notiz(lokaler_tag(zeit), PLAN, s.note.strip(), zeit, None, s.plan_id, s.id)
            )
    for e, s in eintraege:
        if e.note.strip() and e.started_at is not None:
            ergebnis.append(
                Notiz(
                    lokaler_tag(e.started_at),
                    UEBUNG,
                    e.note.strip(),
                    e.started_at,
                    e.exercise_id,
                    s.plan_id,
                    e.id,
                )
            )
    je_eintrag: dict[str, list[AnhangMitBezug]] = {}
    for x in aufnahmen:
        je_eintrag.setdefault(x.anhang.eintrag_id, []).append(x)
    for eintrag_id, liste in je_eintrag.items():
        erste = min(liste, key=lambda x: x.anhang.aufgenommen)
        zeit = erste.eintrag_zeit or erste.anhang.aufgenommen
        bilder, videos, _ = zusammenfassung(x.anhang for x in liste)
        ergebnis.append(
            Notiz(
                lokaler_tag(zeit),
                AUFNAHME,
                anzahl_text(bilder, videos),
                zeit,
                erste.exercise_id,
                None,
                eintrag_id,
            )
        )
    return ergebnis


def nach_tagen(notizen: Iterable[Notiz]) -> list[Tagesgruppe]:
    """Je Tag eine Gruppe, der neueste Tag oben.

    >>> from datetime import UTC
    >>> a = Notiz(date(2026, 10, 17), UEBUNG, "links enger",
    ...           datetime(2026, 10, 17, 18, tzinfo=UTC), "kb")
    >>> b = Notiz(date(2026, 10, 17), TAG, "Schulter fest")
    >>> c = Notiz(date(2026, 10, 18), PLAN, "gut", datetime(2026, 10, 18, 7, tzinfo=UTC))
    >>> [(g.tag.day, [n.text for n in g.notizen]) for g in nach_tagen([a, b, c])]
    [(18, ['gut']), (17, ['Schulter fest', 'links enger'])]
    """
    je_tag: dict[date, list[Notiz]] = {}
    for n in notizen:
        je_tag.setdefault(n.tag, []).append(n)
    return [
        Tagesgruppe(
            tag,
            tuple(sorted(je_tag[tag], key=lambda n: (n.art != TAG, n.sortierzeit()))),
        )
        for tag in sorted(je_tag, reverse=True)
    ]


def nach_uebungen(notizen: Iterable[Notiz]) -> list[Gruppe]:
    """Je Übung und je Plan eine Gruppe, die zuletzt beschriebene oben; die Notizen zum Tag
    zusammen am Ende.

    >>> from datetime import UTC
    >>> def n(tag, art, text, x=None):
    ...     return Notiz(date(2026, 10, tag), art, text, datetime(2026, 10, tag, 8, tzinfo=UTC),
    ...                  x if art == UEBUNG else None, x if art == PLAN else None)
    >>> gruppen = nach_uebungen([n(15, UEBUNG, "eng", "kb"), n(17, UEBUNG, "besser", "kb"),
    ...                          n(16, PLAN, "zäh", "p"), n(17, TAG, "müde")])
    >>> [(g.art, g.schluessel, [x.text for x in g.notizen]) for g in gruppen]
    [('uebung', 'kb', ['besser', 'eng']), ('plan', 'p', ['zäh']), ('tag', None, ['müde'])]
    """
    gruppen: dict[tuple[str, str | None], list[Notiz]] = {}
    for x in notizen:
        # Aufnahmen stehen unter ihrer Übung, zwischen deren Notizen
        art = UEBUNG if x.art == AUFNAHME else x.art
        schluessel = x.exercise_id if art == UEBUNG else x.plan_id if art == PLAN else None
        gruppen.setdefault((art, schluessel), []).append(x)

    def neueste(liste: list[Notiz]) -> tuple[date, float]:
        return max((x.tag, x.sortierzeit()) for x in liste)

    ergebnis = [
        Gruppe(art, schluessel, tuple(sorted(liste, key=lambda x: (x.tag, x.sortierzeit()))[::-1]))
        for (art, schluessel), liste in gruppen.items()
        if art != TAG
    ]
    ergebnis.sort(key=lambda g: neueste(list(g.notizen)), reverse=True)
    tag = gruppen.get((TAG, None))
    if tag:
        ergebnis.append(
            Gruppe(TAG, None, tuple(sorted(tag, key=lambda x: (x.tag, x.sortierzeit()))[::-1]))
        )
    return ergebnis


def zahl_je_tag(notizen: Iterable[Notiz]) -> dict[date, int]:
    """Wie viele Notizen je Tag — die Punkte in der Wochenleiste.

    >>> zahl_je_tag([Notiz(date(2026, 10, 17), TAG, "a"), Notiz(date(2026, 10, 17), PLAN, "b")])
    {datetime.date(2026, 10, 17): 2}
    """
    zahl: dict[date, int] = {}
    for n in notizen:
        zahl[n.tag] = zahl.get(n.tag, 0) + 1
    return zahl


def oben(hoehen: Sequence[float], abstand: float, versatz: float) -> int:
    """Welche Gruppe oben im Bild steht, wenn die Liste um ``versatz`` gescrollt ist —
    für die Wochenleiste, die beim Scrollen mitgeht. ``hoehen`` der Gruppen in ihrer
    Reihenfolge, ``abstand`` zwischen ihnen.

    >>> oben([100, 200, 50], 10, 0), oben([100, 200, 50], 10, 115), oben([100, 200, 50], 10, 999)
    (0, 1, 2)
    >>> oben([], 10, 50)
    0
    """
    unten = 0.0
    for i, h in enumerate(hoehen):
        unten += h + abstand
        if versatz < unten - abstand / 2:
            return i
    return max(len(hoehen) - 1, 0)


def naechster_tag_mit(tage: Iterable[date], ziel: date) -> date | None:
    """Der Tag mit Notiz, der ``ziel`` am nächsten liegt — erst ``ziel`` selbst, dann der
    nächstältere, sonst der nächstjüngere. Für die Wochenleiste: ein Tipp auf einen Tag
    ohne Notiz springt dorthin, wo es weitergeht.

    >>> t = [date(2026, 10, 12), date(2026, 10, 16)]
    >>> naechster_tag_mit(t, date(2026, 10, 16)), naechster_tag_mit(t, date(2026, 10, 14))
    (datetime.date(2026, 10, 16), datetime.date(2026, 10, 12))
    >>> naechster_tag_mit(t, date(2026, 10, 1)), naechster_tag_mit([], date(2026, 10, 1))
    (datetime.date(2026, 10, 12), None)
    """
    alle = sorted(set(tage))
    if not alle:
        return None
    aelter = [t for t in alle if t <= ziel]
    return aelter[-1] if aelter else alle[0]


def woche(tag: date) -> list[date]:
    """Die Woche (Mo–So) um ``tag``.

    >>> [t.day for t in woche(date(2026, 10, 17))]
    [12, 13, 14, 15, 16, 17, 18]
    """
    montag = tag - timedelta(days=tag.weekday())
    return [montag + timedelta(days=i) for i in range(7)]


__all__ = [
    "PLAN",
    "TAG",
    "UEBUNG",
    "Gruppe",
    "Notiz",
    "Tagesgruppe",
    "nach_tagen",
    "nach_uebungen",
    "naechster_tag_mit",
    "oben",
    "sammeln",
    "woche",
    "zahl_je_tag",
]
