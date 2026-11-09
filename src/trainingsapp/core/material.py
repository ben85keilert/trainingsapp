"""Material zu einer Übung beim Üben (U2, Ben 9.11.2026, `docs/plan_paketinhalte.md` §9, F6).

„Übungserklärungen beim „i“. Wenn es Anweisungen gibt, dann in Fokus/Übung anzeigen, dass
Material existiert (Video, Text, PDF, …). Solange das Material angesehen wird, pausiert die Uhr,
kann aber manuell wieder gestartet werden.“

Material sind die **Anweisungen der Planübung** — ihre Abschnitte und Medien, aus dem Paketplan
oder selbst geschrieben (`PlanItem.description`, `PlanItem.media`) — und die **Videos und Links
der Übung**. Die Beschreibung der Übung bleibt im „i“; das Bild der Bewegung (lokal, T6) ist kein
Material. Was die Oberfläche daraus macht (Knopf, Blatt, Uhr anhalten), steht in
`ui/components/material.py`.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .beschreibung import Abschnitt, abschnitte
from .models import Exercise, Media, MediaKind, MediaSource, PlanItem

VIDEO: Final = "video"
PDF: Final = "pdf"
BILD: Final = "bild"
TON: Final = "ton"
LINK: Final = "link"
#: Je Art die Namen für eins und mehrere — in der Reihenfolge der Kurztexte
NAMEN: Final[dict[str, tuple[str, str]]] = {
    VIDEO: ("Video", "Videos"),
    PDF: ("PDF", "PDFs"),
    BILD: ("Bild", "Bilder"),
    TON: ("Ton", "Töne"),
    LINK: ("Link", "Links"),
}


def art(medium: Media) -> str:
    """Wie das Material heißt — aus der Art und der Adresse (eine PDF-Datei erkennt man an
    ihrem Namen, bis das Paketformat eigene Arten kennt, U3).

    >>> art(Media(uri="https://x.org/a.PDF?v=2")), art(Media(uri="https://x.org/film"))
    ('pdf', 'video')
    >>> art(Media(kind=MediaKind.AUDIO, uri="https://x.org/a.mp3"))
    'ton'
    >>> art(Media(kind=MediaKind.IMAGE, uri="https://x.org/b.jpg"))
    'bild'
    >>> art(Media(uri="mailto:praxis@example.org"))
    'link'
    """
    pfad = medium.uri.split("?", 1)[0].split("#", 1)[0].lower()
    if pfad.endswith(".pdf"):
        return PDF
    if pfad.startswith("mailto:"):
        return LINK
    if medium.kind == MediaKind.AUDIO:
        return TON
    if medium.kind == MediaKind.IMAGE:
        return BILD
    return VIDEO


@dataclass(frozen=True, slots=True)
class Material:
    """Was es beim Üben zu sehen gibt: Abschnitte der Planübung, dann Medien (Planübung zuerst,
    dann die Übung)."""

    abschnitte: tuple[Abschnitt, ...] = ()
    medien: tuple[Media, ...] = ()

    @property
    def leer(self) -> bool:
        return not self.abschnitte and not self.medien

    def kurztext(self) -> str:
        """„Text · 2 Videos · PDF“ — was es gibt.

        >>> m = Material(
        ...     (Abschnitt("Im Plan", "am Fenster"),),
        ...     (Media(uri="https://x/a"), Media(uri="https://x/b"), Media(uri="https://x/c.pdf")),
        ... )
        >>> m.kurztext()
        'Text · 2 Videos · PDF'
        >>> Material().kurztext()
        ''
        """
        teile = ["Text"] if self.abschnitte else []
        zaehler: dict[str, int] = {}
        for m in self.medien:
            zaehler[art(m)] = zaehler.get(art(m), 0) + 1
        for a, (eins, mehrere) in NAMEN.items():
            n = zaehler.get(a, 0)
            if n:
                teile.append(eins if n == 1 else f"{n} {mehrere}")
        return " · ".join(teile)


def material_von(uebung: Exercise | None, item: PlanItem | None) -> Material:
    """Das Material zu einer Übung, in einem Plan zu ihrer Planübung — dieselbe Adresse nur
    einmal, lokale Medien (das Bild der Bewegung) nie.

    >>> u = Exercise(name="Baum", description="## Ausführung\\nstehen",
    ...              media=[Media(uri="https://x.org/v")])
    >>> p = PlanItem(description="## Im Plan\\nam Fenster",
    ...              media=[Media(uri="https://x.org/v"), Media(uri="https://x.org/p.pdf")])
    >>> m = material_von(u, p)
    >>> [a.name for a in m.abschnitte], [x.uri for x in m.medien]
    (['Im Plan'], ['https://x.org/v', 'https://x.org/p.pdf'])
    >>> material_von(u, None).kurztext()
    'Video'
    >>> bild = Media(kind=MediaKind.IMAGE, source=MediaSource.LOCAL, uri="Medien/b.webp")
    >>> material_von(Exercise(name="leer", media=[bild]), PlanItem()).leer
    True
    """
    teile = tuple(a for a in abschnitte(item.description) if not a.leer) if item else ()
    medien: list[Media] = []
    gesehen: set[str] = set()
    for m in [*(item.media if item is not None else []), *(uebung.media if uebung else [])]:
        if not m.uri or m.source == MediaSource.LOCAL or m.uri in gesehen:
            continue
        gesehen.add(m.uri)
        medien.append(m)
    return Material(teile, tuple(medien))


__all__ = ["BILD", "LINK", "NAMEN", "PDF", "TON", "VIDEO", "Material", "art", "material_von"]
