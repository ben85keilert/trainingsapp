"""Die **Stellen**, an denen ein Medium liegen kann (Ben, 19.11.2026,
`docs/plan_medien_einheitlich.md` §2.3: „ermittle, wann wo Videos bereitgestellt werden können …
Am besten ist im Ablauf angezeigt, wo Medien liegen“).

Eine Übung im Plan hat vier Stellen — **vorher** (vor dem ▶), **dabei** (Begleitung), **bei …**
(zu einem Ereignis in der Übung), **nachher** (nach „Fertig“) —, der Plan selbst drei: vor dem
Start, bei einer Antwort, am Ende; dazu jeder **Weg** im Ablauf. Hier steht nur, *was wo liegt*
(aus `core.material`, also ohne Ersetztes, Bewegung und Symbol); das Ablaufbild setzt daraus
seine Marken (`ui/components/ablaufbild.py`), das Blatt „Medien an dieser Stelle“ seine Zeilen.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

from .ablauf import Ablauf
from .material import Material, material_von, plan_material
from .models import BEGLEITUNG, BEI, NACHHER, Exercise, Media, Plan, PlanItem

VORHER: Final = "vorher"
DABEI: Final = "dabei"
BEI_EREIGNIS: Final = "bei"
DANACH: Final = "nachher"
#: In der Ordnung, in der man ihnen beim Üben begegnet
STELLEN: Final[tuple[str, ...]] = (VORHER, DABEI, BEI_EREIGNIS, DANACH)
#: Wie die Stellen an einer Übung heißen — und am Plan
NAMEN: Final[dict[str, str]] = {
    VORHER: "Vorher",
    DABEI: "Dabei",
    BEI_EREIGNIS: "Bei …",
    DANACH: "Nachher",
}
NAMEN_PLAN: Final[dict[str, str]] = {
    VORHER: "Vor dem Start",
    BEI_EREIGNIS: "Bei einer Antwort",
    DANACH: "Am Ende",
}
ERKLAERT: Final[dict[str, str]] = {
    VORHER: "bevor die Übung beginnt",
    DABEI: "läuft beim Üben mit",
    BEI_EREIGNIS: "zu einem Ereignis in der Übung",
    DANACH: "nach „Fertig“",
}
ERKLAERT_PLAN: Final[dict[str, str]] = {
    VORHER: "bevor der Plan beginnt",
    BEI_EREIGNIS: "zu einer Antwort auf eine Frage des Ablaufs",
    DANACH: "nach der letzten Übung",
}


def stelle_von(m: Media) -> str:
    """An welcher Stelle ein Stück liegt.

    >>> stelle_von(Media(uri="https://x/a")), stelle_von(Media(uri="https://x/b", rolle=BEGLEITUNG))
    ('vorher', 'dabei')
    >>> stelle_von(Media(uri="https://x/c", wann=NACHHER)), stelle_von(Media(uri="x", wann=BEI))
    ('nachher', 'bei')
    """
    if m.rolle == BEGLEITUNG:
        return DABEI
    if m.wann == NACHHER:
        return DANACH
    if m.wann == BEI:
        return BEI_EREIGNIS
    return VORHER


@dataclass(frozen=True, slots=True)
class Stellen:
    """Was an den Stellen einer Übung im Plan (bzw. des Plans) liegt."""

    vorher: tuple[Media, ...] = ()
    dabei: tuple[Media, ...] = ()
    bei: tuple[Media, ...] = ()
    nachher: tuple[Media, ...] = ()

    def an(self, stelle: str) -> tuple[Media, ...]:
        return {
            VORHER: self.vorher,
            DABEI: self.dabei,
            BEI_EREIGNIS: self.bei,
            DANACH: self.nachher,
        }.get(stelle, ())

    @property
    def belegt(self) -> tuple[str, ...]:
        """Die Stellen, an denen etwas liegt — in der Ordnung von `STELLEN`."""
        return tuple(s for s in STELLEN if self.an(s))

    @property
    def leer(self) -> bool:
        return not self.belegt


def _aus(m: Material) -> Stellen:
    je: dict[str, list[Media]] = {s: [] for s in STELLEN}
    for x in m.medien:
        je[stelle_von(x)].append(x)
    return Stellen(*(tuple(je[s]) for s in STELLEN))


def stellen_von(uebung: Exercise | None, item: PlanItem | None) -> Stellen:
    """Die Stellen einer Übung im Plan: was die Planübung trägt und was aus der Übung gilt.

    >>> u = Exercise(name="Planke", media=[Media(uri="https://x/u", rolle=BEGLEITUNG)])
    >>> i = PlanItem(media=[Media(uri="https://x/v"), Media(uri="https://x/n", wann=NACHHER)])
    >>> s = stellen_von(u, i)
    >>> s.belegt, [x.uri for x in s.dabei], stellen_von(Exercise(name="leer"), PlanItem()).leer
    (('vorher', 'dabei', 'nachher'), ['https://x/u'], True)
    """
    return _aus(material_von(uebung, item))


def plan_stellen(plan: Plan) -> Stellen:
    """Die Stellen des Plans selbst — vor dem Start, bei einer Antwort, am Ende (nie „dabei“).

    >>> p = Plan(media=[Media(uri="https://x/a"), Media(uri="https://x/e", wann=NACHHER)])
    >>> plan_stellen(p).belegt
    ('vorher', 'nachher')
    """
    return _aus(plan_material(plan))


def fuer_stelle(m: Media, stelle: str) -> Media:
    """Ein neues Stück **für diese Stelle**: Rolle und Zeitpunkt nach der Stelle, und es kommt
    dort von selbst (bis es abgehakt ist) — sonst läge „nachher“ nur still hinter „Medien“. Für
    „bei …“ fehlt das Ereignis: das wählt man im Editor, hier bleibt es „vorher“.

    >>> n = fuer_stelle(Media(uri="https://x/a", rolle=BEGLEITUNG), DANACH)
    >>> n.rolle, n.wann, n.zeigen
    ('', 'nachher', True)
    >>> d = fuer_stelle(Media(uri="https://x/a", zeigen=True, wann=NACHHER), DABEI)
    >>> d.rolle, d.wann, d.zeigen
    ('begleitung', '', False)
    """
    if stelle == DABEI:
        return replace(m, rolle=BEGLEITUNG, wann="", zeigen=False, oft="", bei=None)
    return replace(
        m, rolle="", wann=NACHHER if stelle == DANACH else "", zeigen=True, oft="", bei=None
    )


def wege_mit_inhalt(ablauf: Ablauf) -> set[tuple[str, str]]:
    """Die Wege (von, nach), an denen etwas liegt — Text, Link oder Datei.

    >>> from .ablauf import Kante
    >>> from .bedingung import Inhalt
    >>> a = Ablauf(an=True, kanten=(Kante("a", "b", inhalt=Inhalt("Dehnen")), Kante("b", "c")))
    >>> wege_mit_inhalt(a)
    {('a', 'b')}
    """
    return {(k.von, k.nach) for k in ablauf.kanten if not k.inhalt.leer}


__all__ = [
    "BEI_EREIGNIS",
    "DABEI",
    "DANACH",
    "ERKLAERT",
    "ERKLAERT_PLAN",
    "NAMEN",
    "NAMEN_PLAN",
    "STELLEN",
    "VORHER",
    "Stellen",
    "fuer_stelle",
    "plan_stellen",
    "stelle_von",
    "stellen_von",
    "wege_mit_inhalt",
]
