"""Ansicht der HRV-Messung: welche Verlaufskurven unter dem RR-Tachogramm stehen.

Das RR-Tachogramm (bzw. PPI) steht immer oben. Darunter zeigt die Ansicht die
gewählten Verlaufskurven (`hrv_core.trends.KENNZAHLEN`: RMSSD, SDNN, pNN50,
mittlere Herzfrequenz aus RR, Herzfrequenz des Geräts) mit je eigenem
Fenster. Eine Ansicht lässt sich unter einem Namen speichern und wieder laden
(praxis_gui: „Vorlagen").

**Mehrere Kurven in einem Diagramm?** Nur bei gleicher Einheit (``gemeinsam``):
RMSSD und SDNN teilen sich die ms-Achse und sind direkt vergleichbar, ebenso
Ø HF aus RR und HF des Geräts. Kurven verschiedener Einheit bekommen
getrennte, übereinander stehende Diagramme mit derselben Zeitachse — zwei
y-Achsen links und rechts (praxis_gui) sind am Handy nicht lesbar, und die
Skalen suggerierten einen Zusammenhang, den es nicht gibt.

Kein Wissen über die Kennzahlen selbst: Die Schlüssel sind Text, die Einheit
reicht die Ansicht herein (`gruppen`). Dieses Modul importiert nichts aus
anderen Schichten.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Final

#: Vorgabe: ruhige Herzfrequenz aus den Intervallen und die Kurzzeitvariabilität
STANDARD_KURVEN: Final[tuple[str, ...]] = ("hf_rr", "rmssd")
#: Höchstens so viele Verlaufskurven — mehr ist am Handy nicht lesbar
MAX_KURVEN: Final[int] = 4


@dataclass
class Ansicht:
    """Gewählte Verlaufskurven, ihre Fenster und ob gleiche Einheiten zusammen stehen.

    >>> a = Ansicht("Ruhe", ["hf_rr", "rmssd", "sdnn"], {"rmssd": 60})
    >>> a.fenster_fuer("rmssd", 30), a.fenster_fuer("sdnn", 60)
    (60, 60)
    >>> Ansicht.aus_dict(a.als_dict()) == a
    True
    >>> a.gruppen({"hf_rr": "bpm", "rmssd": "ms", "sdnn": "ms"}.get)
    [['hf_rr'], ['rmssd', 'sdnn']]
    >>> Ansicht(gemeinsam=False, kurven=["rmssd", "sdnn"]).gruppen(lambda k: "ms")
    [['rmssd'], ['sdnn']]
    """

    name: str = "Standard"
    kurven: list[str] = field(default_factory=lambda: list(STANDARD_KURVEN))
    #: Fenster je Kennzahl (s) — fehlt eine, gilt ihre Vorgabe
    fenster: dict[str, int] = field(default_factory=dict)
    #: Kurven gleicher Einheit in einem Diagramm
    gemeinsam: bool = True

    def fenster_fuer(self, kennzahl: str, vorgabe: float) -> int:
        return int(self.fenster.get(kennzahl, vorgabe))

    def umschalten(self, kennzahl: str) -> None:
        """Kurve zeigen oder ausblenden; die Reihenfolge der übrigen bleibt."""
        if kennzahl in self.kurven:
            self.kurven.remove(kennzahl)
        elif len(self.kurven) < MAX_KURVEN:
            self.kurven.append(kennzahl)

    def gruppen(self, einheit: Callable[[str], str | None]) -> list[list[str]]:
        """Je Diagramm die Kurven — gleiche Einheit zusammen, wenn ``gemeinsam``.

        Die Diagramme stehen in der Reihenfolge, in der ihre erste Kurve gewählt wurde.
        """
        out: list[list[str]] = []
        nach_einheit: dict[str, list[str]] = {}
        for k in self.kurven:
            e = einheit(k)
            if e is None:
                continue
            if self.gemeinsam and e in nach_einheit:
                nach_einheit[e].append(k)
                continue
            gruppe = [k]
            nach_einheit.setdefault(e, gruppe)
            out.append(gruppe)
        return out

    # -- Serialisierung --------------------------------------------------------

    def als_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kurven": list(self.kurven),
            "fenster": dict(self.fenster),
            "gemeinsam": self.gemeinsam,
        }

    @classmethod
    def aus_dict(cls, d: Any) -> Ansicht:
        """Defensiv: Unbrauchbares wird übergangen, nie eine Ausnahme."""
        if not isinstance(d, dict):
            return cls()
        kurven = [str(k) for k in d.get("kurven") or [] if isinstance(k, str)][:MAX_KURVEN]
        fenster: dict[str, int] = {}
        roh = d.get("fenster")
        for k, v in roh.items() if isinstance(roh, dict) else []:
            try:
                if int(v) > 0:
                    fenster[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
        return cls(
            name=str(d.get("name") or "Standard"),
            kurven=kurven if "kurven" in d else list(STANDARD_KURVEN),
            fenster=fenster,
            gemeinsam=d.get("gemeinsam", True) is not False,
        )


def ansicht_lesen(text: str | None) -> Ansicht:
    try:
        return Ansicht.aus_dict(json.loads(text or ""))
    except (TypeError, ValueError):
        return Ansicht()


def ansichten_lesen(text: str | None) -> list[Ansicht]:
    """Gespeicherte Ansichten (JSON-Liste) — kaputte Einträge fallen weg."""
    try:
        roh = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    return (
        [Ansicht.aus_dict(d) for d in roh if isinstance(d, dict)] if isinstance(roh, list) else []
    )


def ansichten_schreiben(ansichten: Iterable[Ansicht]) -> str:
    return json.dumps([a.als_dict() for a in ansichten], ensure_ascii=False)


__all__ = [
    "MAX_KURVEN",
    "STANDARD_KURVEN",
    "Ansicht",
    "ansicht_lesen",
    "ansichten_lesen",
    "ansichten_schreiben",
]
