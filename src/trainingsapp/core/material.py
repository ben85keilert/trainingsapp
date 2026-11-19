"""Material zu einer Übung beim Üben (U2, Ben 9.11.2026, `docs/plan_paketinhalte.md` §9, F6).

„Übungserklärungen beim „i“. Wenn es Anweisungen gibt, dann in Fokus/Übung anzeigen, dass
Material existiert (Video, Text, PDF, …). Solange das Material angesehen wird, pausiert die Uhr,
kann aber manuell wieder gestartet werden.“

Material sind die **Anweisungen der Planübung** — ihre Abschnitte und Medien, aus dem Paketplan
oder selbst geschrieben (`PlanItem.description`, `PlanItem.media`) — und die **Videos und Links
der Übung**. Die Beschreibung der Übung bleibt im „i“; das Bild der Bewegung (lokal, T6) ist kein
Material, ebenso Stücke mit der Rolle Bewegung oder Symbol (M1/M2, 18.11.2026) — sie haben ihren
eigenen Platz. Was die Oberfläche daraus macht (Knopf, Blatt, Uhr anhalten), steht in
`ui/components/material.py`.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace
from typing import Final

from .beschreibung import Abschnitt, abschnitte
from .linkvideos import direkt
from .models import (
    BEGLEITUNG,
    BEI,
    E_ABSCHNITT,
    E_ANTWORT,
    E_SATZ,
    E_WDH,
    E_ZEIT,
    IMMER,
    NACHHER,
    NICHT_MATERIAL,
    Ereignis,
    Exercise,
    Media,
    MediaKind,
    MediaSource,
    Plan,
    PlanItem,
)
from .paketmedien import ist_paketmedium

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
class Lage:
    """Wo die Übung gerade steht — woran `Material.faellig` die Ereignisse misst. Alles aus Uhr,
    Zählung und Wahl, nie aus Messwerten."""

    #: Name des laufenden Timer-Abschnitts
    abschnitt: str = ""
    #: der wievielte zählende Abschnitt läuft (1 = Satz 1; 0 = keiner)
    satz: int = 0
    #: Sekunden seit dem Start der Uhr
    gelaufen_s: float = 0.0
    #: gezählte Wiederholungen — ``None``: es zählt niemand
    wdh: int | None = None
    #: die gewählten Antworten einer Frage des Ablaufs
    antworten: tuple[str, ...] = ()

    def trifft(self, e: Ereignis) -> bool:
        """Ist das Ereignis eingetreten?

        >>> Lage(abschnitt="Pause").trifft(Ereignis("abschnitt", name="pause"))
        True
        >>> Lage(satz=2).trifft(Ereignis("satz", n=2)), Lage(satz=3).trifft(Ereignis("satz", n=2))
        (True, False)
        >>> Lage(wdh=None).trifft(Ereignis("wdh", n=5)), Lage(wdh=7).trifft(Ereignis("wdh", n=5))
        (False, True)
        >>> Lage(antworten=("Knie zwickt",)).trifft(Ereignis("antwort", antworten=("knie zwickt",)))
        True
        """
        if e.art == E_ABSCHNITT:
            return bool(self.abschnitt) and self.abschnitt.casefold() == e.name.casefold()
        if e.art == E_SATZ:
            return self.satz == e.n
        if e.art == E_ZEIT:
            return self.gelaufen_s >= e.sekunden
        if e.art == E_WDH:
            return self.wdh is not None and self.wdh >= e.n
        if e.art == E_ANTWORT:
            gewaehlt = {a.casefold() for a in self.antworten}
            return any(a.casefold() in gewaehlt for a in e.antworten)
        return False


def _von_selbst(stuecke: tuple[Media, ...], gesehen: Collection[str]) -> tuple[Media, ...]:
    return tuple(m for m in stuecke if m.oft == IMMER or (m.zeigen and m.uri not in gesehen))


@dataclass(frozen=True, slots=True)
class Material:
    """Was es beim Üben zu sehen gibt: Abschnitte der Planübung, dann Medien (Planübung zuerst,
    dann die Übung)."""

    abschnitte: tuple[Abschnitt, ...] = ()
    #: Was gilt — ohne das Ersetzte
    medien: tuple[Media, ...] = ()
    #: Stücke der Übung, die ein Stück der Planübung oder einer Ergänzung hier ersetzt
    #: (`Media.ersetzt`): nicht angeboten, im Blatt erreichbar
    ersetzt: tuple[Media, ...] = ()

    @property
    def leer(self) -> bool:
        return not self.abschnitte and not self.medien

    @property
    def begleitungen(self) -> tuple[Media, ...]:
        """Was beim Üben mitläuft — die Uhr läuft weiter."""
        return tuple(m for m in self.medien if m.rolle == BEGLEITUNG)

    @property
    def begleitvideos(self) -> tuple[Media, ...]:
        """Begleitungen, die die App selbst abspielt — eine Videodatei aus dem Paket oder ein
        Link auf eine Videodatei (`core.linkvideos.direkt`). Sie laufen im Fokus mit (Ben,
        18.11.2026); ein anderer Link (eine Videoseite) bleibt im Blatt.

        >>> m = Material(medien=(
        ...     Media(uri="https://x.org/mit.mp4", rolle=BEGLEITUNG),
        ...     Media(uri="https://youtu.be/abc", rolle=BEGLEITUNG),
        ...     Media(uri="https://x.org/erklaert.mp4"),
        ...     Media(kind=MediaKind.AUDIO, source=MediaSource.PAKET, uri="medien/"
        ...           + "a" * 64 + ".m4a", rolle=BEGLEITUNG),
        ... ))
        >>> [x.uri for x in m.begleitvideos]
        ['https://x.org/mit.mp4']
        """
        return tuple(
            m
            for m in self.begleitungen
            if (ist_paketmedium(m) and m.kind == MediaKind.VIDEO)
            or (m.source != MediaSource.PAKET and direkt(m.uri))
        )

    @property
    def erklaerungen(self) -> tuple[Media, ...]:
        """Was man ansieht und abhakt — die Uhr steht."""
        return tuple(m for m in self.medien if m.rolle != BEGLEITUNG)

    @property
    def vorher(self) -> tuple[Media, ...]:
        """Erklärungen für **vor** der Übung (bzw. vor dem Start des Plans) — die Vorgabe."""
        return tuple(m for m in self.erklaerungen if not m.wann)

    @property
    def nachher(self) -> tuple[Media, ...]:
        """Erklärungen für **nach** der Übung bzw. am Ende des Plans (Ben, 18.11.2026)."""
        return tuple(m for m in self.erklaerungen if m.wann == NACHHER)

    @property
    def bei(self) -> tuple[Media, ...]:
        """Erklärungen, die zu einem **Ereignis** aufgehen (`Media.bei`)."""
        return tuple(m for m in self.erklaerungen if m.wann == BEI and m.bei is not None)

    def neu(self, gesehen: Collection[str]) -> tuple[Media, ...]:
        """Erklärungen für vorher, die von selbst kommen: jedes Mal (``oft = "immer"``) oder
        beim ersten Mal, bis sie abgehakt sind.

        >>> a = Media(uri="https://x/a", zeigen=True)
        >>> b = Media(uri="https://x/b")
        >>> c = Media(uri="https://x/c", oft="immer")
        >>> d = Media(uri="https://x/d", zeigen=True, wann="nachher")
        >>> m = Material(medien=(a, b, c, d))
        >>> [x.uri for x in m.neu(set())], [x.uri for x in m.neu({"https://x/a", "https://x/c"})]
        (['https://x/a', 'https://x/c'], ['https://x/c'])
        """
        return _von_selbst(self.vorher, gesehen)

    def nachher_neu(self, gesehen: Collection[str]) -> tuple[Media, ...]:
        """Was nach der Übung von selbst kommt — wie `neu`, für „nachher“.

        >>> d = Media(uri="https://x/d", zeigen=True, wann="nachher")
        >>> e = Media(uri="https://x/e", wann="nachher")
        >>> m = Material(medien=(d, e))
        >>> [x.uri for x in m.nachher_neu(set())], m.nachher_neu({"https://x/d"})
        (['https://x/d'], ())
        """
        return _von_selbst(self.nachher, gesehen)

    def faellig(self, lage: Lage, schon: Collection[str] = ()) -> tuple[Media, ...]:
        """Die Stücke „bei …“, deren Ereignis **jetzt** eingetreten ist — ohne die, die in
        diesem Lauf schon kamen (``schon``: ihre Adressen).

        >>> pause = Media(uri="https://x/p", wann="bei", bei=Ereignis("abschnitt", name="Pause"))
        >>> spaet = Media(uri="https://x/s", wann="bei", bei=Ereignis("zeit", sekunden=60))
        >>> m = Material(medien=(pause, spaet))
        >>> [x.uri for x in m.faellig(Lage(abschnitt="pause", gelaufen_s=10))]
        ['https://x/p']
        >>> [x.uri for x in m.faellig(Lage(abschnitt="Satz", gelaufen_s=61), {"https://x/p"})]
        ['https://x/s']
        """
        return tuple(
            m for m in self.bei if m.uri not in schon and m.bei is not None and lage.trifft(m.bei)
        )

    def nach_abschnitten(
        self, ohne: Collection[Media] = ()
    ) -> tuple[list[tuple[Abschnitt, tuple[Media, ...]]], tuple[Media, ...]]:
        """Das Blatt in seiner Ordnung (Ben, 18.11.2026: „zugewiesen … und danach geordnet.
        Gerne auch Mehrfachzuweisung“): je Abschnitt seine Stücke — ein Stück mit zwei
        Abschnitten steht unter beiden —, dazu die Stücke ohne (bekannten) Abschnitt. ``ohne``:
        Stücke, die schon woanders stehen (oben als „neu“).

        >>> v = Media(uri="https://x/v", abschnitte=("Ausführung", "Hinweise"))
        >>> w = Media(uri="https://x/w", abschnitte=("Gibt es nicht",))
        >>> m = Material(
        ...     (Abschnitt("Ausführung", "stehen"), Abschnitt("Hinweise", "ruhig atmen")), (v, w)
        ... )
        >>> je, rest = m.nach_abschnitten()
        >>> [(a.name, [x.uri for x in ms]) for a, ms in je]
        [('Ausführung', ['https://x/v']), ('Hinweise', ['https://x/v'])]
        >>> [x.uri for x in rest]
        ['https://x/w']
        """
        da = {a.name.casefold() for a in self.abschnitte if a.name}
        medien = [m for m in self.medien if m not in ohne]
        je = [
            (
                a,
                tuple(
                    m
                    for m in medien
                    if a.name and a.name.casefold() in {n.casefold() for n in m.abschnitte}
                ),
            )
            for a in self.abschnitte
        ]
        rest = tuple(m for m in medien if not ({n.casefold() for n in m.abschnitte} & da))
        return je, rest

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
    einmal, lokale Medien (das Bild der Bewegung) nie, ebenso keine Bewegung und kein Symbol.

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
    >>> folge = Media(kind=MediaKind.IMAGE, source=MediaSource.PAKET, uri="medien/a.png",
    ...               rolle="bewegung")
    >>> material_von(Exercise(name="Kniebeuge", media=[folge]), None).leer
    True

    Ein Stück der Planübung (oder einer Ergänzung) kann eines der Übung **ersetzen**:

    >>> p = PlanItem(media=[Media(uri="https://x.org/stufe", ersetzt="https://x.org/v")])
    >>> m = material_von(u, p)
    >>> [x.uri for x in m.medien], [x.uri for x in m.ersetzt]
    (['https://x.org/stufe'], ['https://x.org/v'])
    """
    teile = tuple(a for a in abschnitte(item.description) if not a.leer) if item else ()
    alle = [*(item.media if item is not None else []), *(uebung.media if uebung else [])]
    weg = {m.ersetzt for m in alle if m.ersetzt and m.ersetzt != m.uri}
    medien: list[Media] = []
    ersetzt: list[Media] = []
    schon: set[str] = set()
    for m in alle:
        if not m.uri or m.source == MediaSource.LOCAL or m.uri in schon:
            continue
        if m.rolle in NICHT_MATERIAL:
            continue
        schon.add(m.uri)
        (ersetzt if m.uri in weg else medien).append(m)
    # Abschnitte der Übungsbeschreibung kommen nur dazu, wenn ein Stück zu ihnen gehört (Ben,
    # 18.11.2026, Frage e) — sonst bleibt die Beschreibung der Übung im „i“
    gemeint = {n.casefold() for m in medien for n in m.abschnitte}
    da = {a.name.casefold() for a in teile}
    if uebung is not None and gemeint - da:
        teile += tuple(
            a
            for a in abschnitte(uebung.description)
            if not a.leer and a.name.casefold() in gemeint - da
        )
    return Material(teile, tuple(medien), tuple(ersetzt))


def plan_material(plan: Plan) -> Material:
    """Was es zum **Plan selbst** zu sehen gibt (Ben, 17.11.2026, `docs/plan_medien_reiter.md`
    §4): seine Beschreibung in Abschnitten und seine Stücke — dieselbe Adresse nur einmal, nie
    lokale, nie eine Begleitung (es läuft keine Übung daneben).

    >>> p = Plan(description="## So läuft es\\nDreimal die Woche",
    ...          media=[Media(uri="https://x.org/a", zeigen=True), Media(uri="https://x.org/a")])
    >>> m = plan_material(p)
    >>> [a.name for a in m.abschnitte], [x.uri for x in m.medien], m.kurztext()
    (['So läuft es'], ['https://x.org/a'], 'Text · Video')
    >>> plan_material(Plan()).leer
    True
    """
    teile = tuple(a for a in abschnitte(plan.description) if not a.leer)
    medien: list[Media] = []
    schon: set[str] = set()
    for m in plan.media:
        if not m.uri or m.source == MediaSource.LOCAL or m.uri in schon:
            continue
        schon.add(m.uri)
        # am Plan selbst: keine Begleitung (es läuft keine Übung daneben), auch keine Bewegung
        medien.append(replace(m, rolle="") if m.rolle else m)
    return Material(teile, tuple(medien))


__all__ = [
    "BILD",
    "LINK",
    "NAMEN",
    "PDF",
    "TON",
    "VIDEO",
    "Lage",
    "Material",
    "art",
    "material_von",
    "plan_material",
]
