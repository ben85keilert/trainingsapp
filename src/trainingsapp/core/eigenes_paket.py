"""Ein eigenes Paket, in der App gebaut (U4, Ben 9.11.2026, `docs/plan_paketinhalte.md` §7).

„Es ist leichter für mich, wenn ich ein Paket erstelle, darin Videos reinlade, dieses Paket
exportiere und dann jemandem mitgebe“ — und F5: Übungen, Pläne und Kurse. Ein eigenes Paket hat
eine **feste ID** (jede neue Fassung ist ein Update desselben Pakets bei allen, die es haben),
Kopf (Name, Beschreibung, Neuigkeiten) und die gewählten Übungen, Pläne und Kurse. Übungen,
die ein gewählter Plan oder Kurs braucht, kommen von selbst mit (`noetige_uebungen`).

**Version vorschlagen:** Beim Export schlägt die App die nächste Version vor — ist der Inhalt
seit der letzten Fassung gleich (`inhalt_sha`), bleibt sie; sonst steigt sie um eine Stufe:
*klein* (letzte Stelle, Empfänger mit „Kleine automatisch“ bekommen sie von selbst), *mittel*
oder *groß*. Die erste Fassung ist 1.0.0.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from .kurse import Kurs
from .models import Plan, new_id
from .paketversion import STELLE

KLEIN: Final = "klein"
MITTEL: Final = "mittel"
GROSS: Final = "gross"
STUFEN: Final[dict[str, str]] = {
    KLEIN: "Klein (z. B. Text, ein Video dazu)",
    MITTEL: "Mittel (neue Übungen, neuer Plan)",
    GROSS: "Groß (vieles anders)",
}
#: Die erste Fassung eines eigenen Pakets: 1.0.0
ERSTE_VERSION: Final = STELLE * STELLE


@dataclass(slots=True)
class EigenesPaket:
    """Ein eigenes Paket: Kopf, Auswahl und was beim letzten Export galt."""

    id: str = field(default_factory=new_id)
    name: str = ""
    beschreibung: str = ""
    neuigkeiten: str = ""
    #: Version der letzten exportierten Fassung (``None`` = noch keine)
    version: int | None = None
    uebungen: list[str] = field(default_factory=list)
    plaene: list[str] = field(default_factory=list)
    kurse: list[str] = field(default_factory=list)
    exportiert_sha: str | None = None
    exportiert_am: datetime | None = None

    @property
    def leer(self) -> bool:
        return not self.uebungen and not self.plaene and not self.kurse


def naechste_version(alt: int | None, stufe: str = KLEIN) -> int:
    """Die nächste Version nach ``alt`` — die erste ist 1.0.0.

    >>> from trainingsapp.core.paketversion import version_text
    >>> [version_text(naechste_version(10203, s)) for s in (KLEIN, MITTEL, GROSS)]
    ['1.2.4', '1.3.0', '2.0.0']
    >>> version_text(naechste_version(None))
    '1.0.0'
    """
    if alt is None:
        return ERSTE_VERSION
    x, rest = divmod(alt, STELLE * STELLE)
    y, z = divmod(rest, STELLE)
    if stufe == GROSS:
        return (x + 1) * STELLE * STELLE
    if stufe == MITTEL:
        return x * STELLE * STELLE + (y + 1) * STELLE
    return x * STELLE * STELLE + y * STELLE + z + 1


def inhalt_sha(roh: dict[str, Any]) -> str:
    """Die Prüfsumme des Inhalts einer Paketdatei — ohne Version, Neuigkeiten und
    Zeitstempel: Gleicher Inhalt, gleiche Summe, auch über Fassungen hinweg.

    >>> a = {"paket": {"name": "P", "version": 1}, "exercises": [], "exportiert": "x"}
    >>> b = {"paket": {"name": "P", "version": 2, "neuigkeiten": "n"}, "exercises": []}
    >>> inhalt_sha(a) == inhalt_sha(b)
    True
    """
    kopie = json.loads(json.dumps(roh, ensure_ascii=False))
    kopie.pop("exportiert", None)
    kopie.pop("version", None)  # Formatversion folgt dem Inhalt
    kopf = kopie.get("paket")
    if isinstance(kopf, dict):
        kopf.pop("version", None)
        kopf.pop("neuigkeiten", None)
    text = json.dumps(kopie, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def noetige_uebungen(plaene: Iterable[Plan], kurse: Iterable[Kurs]) -> list[str]:
    """Die Übungen, die gewählte Pläne und Kurse brauchen — Planübungen, Kapitelpläne und
    die Übung einer Kapitelbedingung („Summe“), in der Reihenfolge des ersten Auftretens.

    >>> from trainingsapp.core.models import PlanItem
    >>> noetige_uebungen([Plan(items=[PlanItem(exercise_id="a"), PlanItem(exercise_id="a")])], [])
    ['a']
    """
    ids: list[str] = []

    def dazu(uebung_id: str | None) -> None:
        if uebung_id and uebung_id not in ids:
            ids.append(uebung_id)

    for p in plaene:
        for i in sorted(p.items, key=lambda x: x.order):
            dazu(i.exercise_id)
    for k in kurse:
        for kap in k.kapitel:
            for v in kap.plaene:
                for vi in v.items:
                    dazu(vi.exercise_id)
            dazu(getattr(kap.bedingung, "exercise_id", None))
    return ids


__all__ = [
    "ERSTE_VERSION",
    "GROSS",
    "KLEIN",
    "MITTEL",
    "STUFEN",
    "EigenesPaket",
    "inhalt_sha",
    "naechste_version",
    "noetige_uebungen",
]
