"""Was es an Medien schon gibt — zum Wiederverwenden (Ben, 19.11.2026,
`docs/plan_medien_einheitlich.md` §2.1: „hinterlegte Videos aus dem Reiter ‚Medien‘ können nicht
eingebunden werden“).

„Aus vorhandenen Medien …“ bietet die Stücke an, die Übungen, Planübungen und Pläne schon tragen.
Gewählt wird ein **Verweis auf dieselbe Datei bzw. Adresse**, keine Kopie: ein neues Stück mit
derselben ``uri`` — Titel und Beschriftung kommen mit, Rolle und Zeitpunkt gehören der neuen
Stelle (`uebernommen`).

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from .models import NICHT_MATERIAL, Exercise, Media, MediaSource, Plan


@dataclass(frozen=True, slots=True)
class Vorhanden:
    """Ein Stück, das es schon gibt, und wo (das erste Vorkommen, „+ n“ bei weiteren)."""

    medium: Media
    wo: str
    weitere: int = 0

    @property
    def wo_text(self) -> str:
        return self.wo if not self.weitere else f"{self.wo} + {self.weitere}"


def vorrat(
    uebungen: Iterable[Exercise],
    plaene: Iterable[Plan] = (),
    *,
    zuerst: Iterable[tuple[Media, str]] = (),
    ohne: Collection[str] = (),
) -> list[Vorhanden]:
    """Die Stücke zum Wiederverwenden — jede Adresse einmal. ``zuerst``: Stücke, die vorn stehen
    sollen (die des Plans, an dem man gerade arbeitet), mit ihrem Ort; ``ohne``: Adressen, die an
    der Stelle schon stehen. Nie lokale Medien (das Bild der Bewegung), nie Bewegung oder Symbol.

    >>> u = Exercise(name="Kniebeuge", media=[Media(uri="https://x.org/a", title="Technik"),
    ...     Media(uri="https://x.org/s", rolle="symbol")])
    >>> from .models import PlanItem
    >>> p = Plan(name="Beine", media=[Media(uri="https://x.org/p", title="Einstimmung")],
    ...     items=[PlanItem(exercise_id=u.id, media=[Media(uri="https://x.org/a")])])
    >>> [(v.medium.uri, v.wo_text) for v in vorrat([u], [p])]
    [('https://x.org/a', 'Übung Kniebeuge + 1'), ('https://x.org/p', 'Plan Beine')]
    >>> [v.medium.uri for v in vorrat([u], [p], ohne={"https://x.org/a"})]
    ['https://x.org/p']
    """
    je: dict[str, Vorhanden] = {}

    def dazu(m: Media, wo: str) -> None:
        if not m.uri or m.source == MediaSource.LOCAL or m.rolle in NICHT_MATERIAL:
            return
        if m.uri in ohne:
            return
        alt = je.get(m.uri)
        je[m.uri] = (
            Vorhanden(m, wo) if alt is None else Vorhanden(alt.medium, alt.wo, alt.weitere + 1)
        )

    for m, wo in zuerst:
        dazu(m, wo)
    namen: dict[str, str] = {}
    for u in uebungen:
        namen[u.id] = u.name
        for m in u.media:
            dazu(m, f"Übung {u.name}")
    for p in plaene:
        for m in p.media:
            dazu(m, f"Plan {p.name}")
        for item in p.items:
            for m in item.media:
                dazu(m, f"{p.name} · {namen.get(item.exercise_id, 'Übung')}")
    return list(je.values())


def uebernommen(m: Media) -> Media:
    """Das Stück für die neue Stelle: dieselbe Datei bzw. Adresse (kein Kopieren), Art, Titel,
    Lizenz und Beschriftung — Rolle, Zeitpunkt, „ersetzt“ und Abschnitte bleiben der alten Stelle.

    >>> alt = Media(uri="https://x.org/a", title="Technik", text="von der Seite", wann="nachher",
    ...     rolle="", zeigen=True, abschnitte=("Ausführung",))
    >>> neu = uebernommen(alt)
    >>> neu.uri, neu.title, neu.text, neu.wann, neu.zeigen, neu.abschnitte, neu.id != alt.id
    ('https://x.org/a', 'Technik', 'von der Seite', '', False, (), True)
    """
    return Media(
        kind=m.kind, source=m.source, uri=m.uri, title=m.title, license=m.license, text=m.text
    )


def passt(v: Vorhanden, suche: str) -> bool:
    """Trifft die Suche Titel, Beschriftung oder Ort?

    >>> v = Vorhanden(Media(uri="https://x.org/a", title="Technik"), "Übung Kniebeuge")
    >>> passt(v, "knie"), passt(v, " TECH "), passt(v, "plan")
    (True, True, False)
    """
    wort = suche.strip().casefold()
    return not wort or any(
        wort in t.casefold() for t in (v.medium.title, v.medium.text, v.wo, v.medium.uri)
    )


__all__ = ["Vorhanden", "passt", "uebernommen", "vorrat"]
