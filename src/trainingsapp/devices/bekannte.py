"""Bekannte Geräte — einmal verbunden, beim nächsten Mal ein Tipp.

Nach jeder erfolgreichen Verbindung merkt sich die App das Gerät (ID, Name,
Profil, wann). Die Liste steht über „Geräte suchen"; ein Tipp verbindet direkt
über die gespeicherte ID — ohne Suche. Android erreicht ein bekanntes Gerät über
seine Adresse, solange es eingeschaltet ist; findet die App es nicht, hilft die
Suche wie bisher.

Gespeichert wird gerätelokal als JSON (`SettingRepo.BEKANNTE_GERAETE`), die
zuletzt benutzten zuerst, höchstens `MAX_BEKANNT`. Keine Oberfläche hier.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Final

#: So viele Geräte merkt sich die App
MAX_BEKANNT: Final[int] = 6


@dataclass(frozen=True, slots=True)
class BekanntesGeraet:
    """Ein Gerät, mit dem die App schon verbunden war."""

    id: str
    name: str
    profil_id: str = ""
    #: Zuletzt verbunden (ISO 8601, UTC)
    zuletzt: str = ""

    def zuletzt_text(self) -> str:
        """„14.10." — für die Liste; leer, wenn unbekannt.

        >>> BekanntesGeraet("a", "H10", zuletzt="2026-10-14T08:00:00+00:00").zuletzt_text()
        '14.10.'
        """
        try:
            return datetime.fromisoformat(self.zuletzt).astimezone().strftime("%d.%m.")
        except (TypeError, ValueError):
            return ""


def bekannte_lesen(text: str | None) -> list[BekanntesGeraet]:
    """Gespeicherte Liste — Kaputtes fällt weg, nie eine Ausnahme.

    >>> bekannte_lesen('[{"id": "A", "name": "Polar H10"}, {"name": "ohne ID"}, 3]')
    [BekanntesGeraet(id='A', name='Polar H10', profil_id='', zuletzt='')]
    >>> bekannte_lesen("kaputt")
    []
    """
    try:
        roh = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    out: list[BekanntesGeraet] = []
    for d in roh if isinstance(roh, list) else []:
        if isinstance(d, dict) and isinstance(d.get("id"), str) and d["id"]:
            out.append(
                BekanntesGeraet(
                    id=d["id"],
                    name=str(d.get("name") or d["id"]),
                    profil_id=str(d.get("profil_id") or ""),
                    zuletzt=str(d.get("zuletzt") or ""),
                )
            )
    return out


def bekannte_schreiben(geraete: list[BekanntesGeraet]) -> str:
    return json.dumps([asdict(g) for g in geraete], ensure_ascii=False)


def merken(geraete: list[BekanntesGeraet], neu: BekanntesGeraet) -> list[BekanntesGeraet]:
    """Nach vorn (oder neu dazu), höchstens `MAX_BEKANNT`.

    >>> a, b = BekanntesGeraet("A", "H10"), BekanntesGeraet("B", "Verity")
    >>> [g.id for g in merken(merken([a], b), BekanntesGeraet("A", "H10 neu"))]
    ['A', 'B']
    """
    return [neu, *(g for g in geraete if g.id != neu.id)][:MAX_BEKANNT]


def vergessen(geraete: list[BekanntesGeraet], geraet_id: str) -> list[BekanntesGeraet]:
    return [g for g in geraete if g.id != geraet_id]


__all__ = [
    "MAX_BEKANNT",
    "BekanntesGeraet",
    "bekannte_lesen",
    "bekannte_schreiben",
    "merken",
    "vergessen",
]
