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
Seit 22.10.2026 auch Audioaufnahmen, und Anhänge am Tag selbst (Notiz zum Tag): je Tag eine
`AUFNAHME` ohne Übung, nach Übungen geordnet bei den Notizen zum Tag.

**Tagesfelder** (Ben, 21.10.2026, `core/tagesfelder.py`, Skizze C4): An der Notiz zum Tag
steht die Zeile mit den Werten des Tags (`Notiz.werte` — „Schmerz Knie 3 · Ibu 400 × 2“);
ein Tag nur mit Werten erscheint dann auch ohne Text. Texte der Felder („Ernährung“) und
Werte mit Notiz sind Notizen der Art `TAGESFELD` nach der Uhr; nach Übungen geordnet hat
jedes Tagesfeld seine Gruppe.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from .anhaenge import AnhangMitBezug, zusammenfassung
from .models import Session, SessionEntry, lokaler_tag
from .tagesfelder import TEXT as NUR_TEXT
from .tagesfelder import Tagesfeld, Tageswert, eintrag_text, tageszeile
from .varianten import von as variante_von

#: Woran eine Notiz hängt — `AUFNAHME`: Fotos und Videos an einem Eintrag, `TAGESFELD`: Text
#: oder Notiz eines Tagesfelds
TAG, PLAN, UEBUNG, AUFNAHME, TAGESFELD = "tag", "plan", "uebung", "aufnahme", "tagesfeld"


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
    #: die Variante ihres Eintrags — leer ohne (Ben, 21.10.2026: „vor allem im Tagebuch“)
    variante: str = ""
    #: Notiz zum Tag: die Werte der Tagesfelder an diesem Tag
    werte: str = ""
    #: Tagesfeld: welches, und wie die Notiz heißt („Ibu 400“, „Ernährung“)
    feld_id: str | None = None
    titel: str = ""
    #: `AUFNAHME`: die Anhänge, die älteste zuerst — an einem Eintrag oder am Tag (dann ohne
    #: Übung, Ben 22.10.2026)
    anhang_ids: tuple[str, ...] = ()

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
    tageswerte: Iterable[Tageswert] = (),
    tagesfelder: Mapping[str, Tagesfeld] | None = None,
) -> list[Notiz]:
    """Die Ebenen als Notizen — ``tage`` (Tag, Text, angelegt), ``sessions`` (mit ihrem
    ersten Eintrag), ``eintraege`` (mit ihrer Session), ``aufnahmen`` (Anhänge mit ihrem
    Eintrag — je Eintrag eine Notiz `AUFNAHME`), ``tageswerte`` mit ihren ``tagesfelder``
    (Wertezeile an der Notiz zum Tag, Texte als `TAGESFELD`). Leere Notizen fallen weg.

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
    >>> lang = SessionEntry(id="e2", session_id="s1", exercise_id="lgs", note="zäh",
    ...                     result={"variant": "lang"}, started_at=e.started_at)
    >>> [x.variante for x in sammeln([], [], [(lang, s)])]
    ['lang']
    >>> a = AnhangMitBezug(Anhang("e1", aufgenommen=e.started_at), "kb", e.started_at)
    >>> b = AnhangMitBezug(Anhang("e1", "video", aufgenommen=e.started_at), "kb", e.started_at)
    >>> [(x.art, x.text, x.bezug_id, x.exercise_id) for x in sammeln([], [], [], [a, b])]
    [('aufnahme', '1 Foto, 1 Video', 'e1', 'kb')]

    Anhänge am Tag (Notiz zum Tag) sind je Tag eine Aufnahme ohne Übung:

    >>> c = AnhangMitBezug(Anhang(None, "audio", id="c", aufgenommen=e.started_at,
    ...                           profil_id="p1", zum_tag=date(2026, 10, 17)), None, None)
    >>> [(x.art, x.text, x.exercise_id, x.anhang_ids) for x in sammeln([], [], [], [c])]
    [('aufnahme', '1 Audioaufnahme', None, ('c',))]
    >>> from . import tagesfelder as tf
    >>> ibu = tf.Tagesfeld(id="ibu", name="Ibu", spec=tf.spec_bauen(tf.ANZAHL, varianten=["400"]))
    >>> ess = tf.Tagesfeld(id="ess", name="Ernährung", spec=tf.spec_bauen(tf.TEXT))
    >>> t = date(2026, 10, 21)
    >>> w = [tf.Tageswert(feld_id="ibu", tag=t, result=tf.ergebnis(1, "400"), spec=ibu.spec,
    ...                   note="nach dem Laufen"),
    ...      tf.Tageswert(feld_id="ess", tag=t, note="Gemüse", spec=ess.spec)]
    >>> n = sammeln([(t, "müde", None)], [], [], [], w, {"ibu": ibu, "ess": ess})
    >>> for x in n:
    ...     print(x.art, "|", x.text, "|", x.werte or x.titel)
    tag | müde | Ibu 400 × 1
    tagesfeld | nach dem Laufen | Ibu 400
    tagesfeld | Gemüse | Ernährung
    """
    ergebnis = [Notiz(t, TAG, text.strip(), zeit) for t, text, zeit in tage if text.strip()]
    ergebnis = _mit_tageswerten(ergebnis, list(tageswerte), tagesfelder or {})
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
                    variante_von(e.result),
                )
            )
    # Je Eintrag eine Notiz `AUFNAHME` — die Anhänge am Tag (Notiz zum Tag) je Tag eine
    je_eintrag: dict[str, list[AnhangMitBezug]] = {}
    je_tag: dict[date, list[AnhangMitBezug]] = {}
    for x in aufnahmen:
        if x.anhang.zum_tag is not None:
            je_tag.setdefault(x.anhang.zum_tag, []).append(x)
        elif x.anhang.eintrag_id is not None:
            je_eintrag.setdefault(x.anhang.eintrag_id, []).append(x)
    for eintrag_id, liste in je_eintrag.items():
        erste = min(liste, key=lambda x: x.anhang.aufgenommen)
        zeit = erste.eintrag_zeit or erste.anhang.aufgenommen
        ergebnis.append(
            Notiz(
                lokaler_tag(zeit),
                AUFNAHME,
                zusammenfassung(x.anhang for x in liste).text,
                zeit,
                erste.exercise_id,
                None,
                eintrag_id,
                anhang_ids=_reihenfolge(liste),
            )
        )
    for tag, liste in je_tag.items():
        erste = min(liste, key=lambda x: x.anhang.aufgenommen)
        ergebnis.append(
            Notiz(
                tag,
                AUFNAHME,
                zusammenfassung(x.anhang for x in liste).text,
                erste.anhang.aufgenommen,
                anhang_ids=_reihenfolge(liste),
            )
        )
    return ergebnis


def _reihenfolge(liste: list[AnhangMitBezug]) -> tuple[str, ...]:
    """Die IDs der Anhänge, die älteste zuerst."""
    return tuple(x.anhang.id for x in sorted(liste, key=lambda x: x.anhang.aufgenommen))


def _mit_tageswerten(
    notizen: list[Notiz], werte: list[Tageswert], felder: Mapping[str, Tagesfeld]
) -> list[Notiz]:
    """Die Notizen zum Tag mit ihrer Wertezeile — dazu die Texte der Tagesfelder."""
    if not werte:
        return notizen
    je_tag: dict[date, list[Tageswert]] = {}
    for w in werte:
        je_tag.setdefault(w.tag, []).append(w)
    zum_tag = {n.tag: n for n in notizen if n.art == TAG}
    ergebnis = [n for n in notizen if n.art != TAG]
    for tag in sorted(set(zum_tag) | set(je_tag)):
        teile = [
            text
            for feld in felder.values()
            if (text := tageszeile(feld, [w for w in je_tag.get(tag, []) if w.feld_id == feld.id]))
        ]
        notiz = zum_tag.get(tag)
        if notiz is not None:
            ergebnis.append(replace(notiz, werte=" · ".join(teile)))
        elif teile:
            ergebnis.append(Notiz(tag, TAG, "", None, werte=" · ".join(teile)))
    for w in werte:
        if not w.note.strip():
            continue
        feld = felder.get(w.feld_id)
        name = feld.name if feld is not None else "Tagesfeld"
        titel = (
            " · ".join(x for x in (name, w.variante) if x)
            if feld is None or feld.art == NUR_TEXT
            else eintrag_text(name, w)
        )
        ergebnis.append(
            Notiz(
                w.tag,
                TAGESFELD,
                w.note.strip(),
                w.zeit,
                bezug_id=w.id,
                variante=w.variante,
                feld_id=w.feld_id,
                titel=titel,
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
        if x.art == TAG and not x.text:
            continue  # nur Werte — die stehen nach Tagen, nicht als Notiz zum Tag
        # Aufnahmen stehen unter ihrer Übung, zwischen deren Notizen — die am Tag bei den
        # Notizen zum Tag
        art = (UEBUNG if x.exercise_id else TAG) if x.art == AUFNAHME else x.art
        schluessel = {UEBUNG: x.exercise_id, PLAN: x.plan_id, TAGESFELD: x.feld_id}.get(art)
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
    "AUFNAHME",
    "PLAN",
    "TAG",
    "TAGESFELD",
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
