"""Ansicht der HRV-Messung: welche Verlaufskurven unter der Hauptkurve stehen.

Die Hauptkurve (RR- bzw. PPI-Tachogramm) steht immer oben. Darunter wählt man
einen Analysebereich — Zeit, Frequenz, Nichtlinear — und darin die
Verlaufskurven (`hrv_core.trends.KENNZAHLEN`), je mit eigenem Fenster und als
gleitender Wert oder in Blöcken. Eine Ansicht lässt sich unter einem Namen
speichern und wieder laden (praxis_gui: „Vorlagen").

**Mehrere Kurven in einem Diagramm?** Nur auf gleicher Achse (``gemeinsam``):
RMSSD und SDNN teilen sich die ms-Achse der Variabilität, LF und HF die
ms²-Achse. Ø RR hat zwar auch ms, liegt aber bei 800 statt 40 ms und bekommt
eine eigene Achse — sonst wäre RMSSD eine flache Linie am Boden. Zwei
y-Achsen links und rechts (praxis_gui) sind am Handy nicht lesbar.

**Keine Höchstzahl mehr.** Bis Oktober 2026 waren es höchstens vier Kurven —
eine eigene Festlegung für kleine Bildschirme, keine fachliche. Weil gleiche
Achsen sich ein Diagramm teilen und je Bereich nur dessen Kurven stehen, wächst
die Ansicht langsamer als die Zahl der Kurven.

Kein Wissen über die Kennzahlen selbst: Die Schlüssel sind Text, Achse und
Bereich reicht die Oberfläche herein. Dieses Modul importiert nichts aus
anderen Schichten.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Final

#: Vorgabe je Bereich: ruhige Herzfrequenz, Kurzzeitvariabilität und Atmung; LF,
#: HF und LF/HF (wer Frequenz will, will LF/HF); SD1 und DFA α1
STANDARD_KURVEN: Final[tuple[str, ...]] = (
    "hf_rr",
    "rmssd",
    "atemfrequenz",
    "lf_power",
    "hf_power",
    "lf_hf",
    "sd1",
    "dfa_alpha1",
)
#: Mit Formatstand 3 neu hinzugekommene Vorgaben — ältere Ansichten bekommen sie dazu
NEU_IN_3: Final[tuple[str, ...]] = ("atemfrequenz", "lf_hf")
#: Darstellung einer Kurve: gleitendes Fenster oder Blöcke ohne Überlappung
GLEITEND: Final[str] = "gleitend"
BLOCK: Final[str] = "block"
#: pNNx: wählbare Schwellen (ms) und Vorgabe — pNN50 ist das übliche
PNN_WAHL: Final[tuple[int, ...]] = (10, 20, 30, 40, 50, 100)
PNN_STANDARD: Final[int] = 50
#: Formatstand der gespeicherten Ansicht; ältere werden beim Lesen ergänzt
VERSION: Final[int] = 3


@dataclass
class Ansicht:
    """Gewählte Verlaufskurven, ihre Fenster und Darstellung.

    >>> a = Ansicht("Ruhe", ["hf_rr", "rmssd", "sdnn"], {"rmssd": 60}, modus={"hf_rr": "block"})
    >>> a.fenster_fuer("rmssd", 30), a.fenster_fuer("sdnn", 60), a.modus_fuer("hf_rr")
    (60, 60, 'block')
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
    #: Kurven gleicher Achse in einem Diagramm
    gemeinsam: bool = True
    #: Darstellung je Kennzahl (`BLOCK`); fehlt eine, ist sie gleitend
    modus: dict[str, str] = field(default_factory=dict)
    #: Schwelle für pNNx (ms)
    pnn_ms: int = PNN_STANDARD
    #: Gewählter Analysebereich (zeit, frequenz, nichtlinear)
    bereich: str = "zeit"

    def fenster_fuer(self, kennzahl: str, vorgabe: float) -> int:
        return int(self.fenster.get(kennzahl, vorgabe))

    def modus_fuer(self, kennzahl: str) -> str:
        return BLOCK if self.modus.get(kennzahl) == BLOCK else GLEITEND

    def umschalten(self, kennzahl: str) -> None:
        """Kurve zeigen oder ausblenden; die Reihenfolge der übrigen bleibt."""
        if kennzahl in self.kurven:
            self.kurven.remove(kennzahl)
        else:
            self.kurven.append(kennzahl)

    def gruppen(
        self, achse: Callable[[str], str | None], nur: Iterable[str] | None = None
    ) -> list[list[str]]:
        """Je Diagramm die Kurven — gleiche Achse zusammen, wenn ``gemeinsam``.

        ``achse`` liefert je Kennzahl den Schlüssel ihrer Werteachse (``None``:
        unbekannt, fällt weg). ``nur``: auf diese Kennzahlen beschränken (der
        gewählte Bereich). Die Diagramme stehen in der Reihenfolge, in der ihre
        erste Kurve gewählt wurde.
        """
        erlaubt = set(nur) if nur is not None else None
        out: list[list[str]] = []
        nach_achse: dict[str, list[str]] = {}
        for k in self.kurven:
            if erlaubt is not None and k not in erlaubt:
                continue
            a = achse(k)
            if a is None:
                continue
            if self.gemeinsam and a in nach_achse:
                nach_achse[a].append(k)
                continue
            gruppe = [k]
            nach_achse.setdefault(a, gruppe)
            out.append(gruppe)
        return out

    # -- Serialisierung --------------------------------------------------------

    def als_dict(self) -> dict[str, Any]:
        return {
            "v": VERSION,
            "name": self.name,
            "kurven": list(self.kurven),
            "fenster": dict(self.fenster),
            "gemeinsam": self.gemeinsam,
            "modus": dict(self.modus),
            "pnn_ms": self.pnn_ms,
            "bereich": self.bereich,
        }

    @classmethod
    def aus_dict(cls, d: Any) -> Ansicht:
        """Defensiv: Unbrauchbares wird übergangen, nie eine Ausnahme.

        Ansichten von vor Version 2 kannten nur den Zeitbereich und hießen pNN50
        noch ``pnn50``: Sie bekommen die Vorgaben der neuen Bereiche dazu.

        >>> alt = Ansicht.aus_dict({"name": "Alt", "kurven": ["pnn50", "rmssd"]})
        >>> alt.kurven
        ['pnnx', 'rmssd', 'lf_power', 'hf_power', 'sd1', 'dfa_alpha1', 'atemfrequenz', 'lf_hf']
        """
        if not isinstance(d, dict):
            return cls()
        kurven = [_neu(k) for k in d.get("kurven") or [] if isinstance(k, str)]
        v = d.get("v")
        stand = v if isinstance(v, int) else 1
        if "kurven" not in d:
            kurven = list(STANDARD_KURVEN)
        else:
            if stand < 2:
                kurven += [k for k in STANDARD_KURVEN[2:] if k not in kurven and k not in NEU_IN_3]
            if stand < 3:
                kurven += [k for k in NEU_IN_3 if k not in kurven]
        fenster: dict[str, int] = {}
        roh = d.get("fenster")
        for k, v in roh.items() if isinstance(roh, dict) else []:
            try:
                if int(v) > 0:
                    fenster[_neu(str(k))] = int(v)
            except (TypeError, ValueError):
                continue
        modus_roh = d.get("modus")
        modus = {
            str(k): BLOCK
            for k, v in (modus_roh.items() if isinstance(modus_roh, dict) else [])
            if v == BLOCK
        }
        pnn = d.get("pnn_ms")
        return cls(
            name=str(d.get("name") or "Standard"),
            kurven=list(dict.fromkeys(kurven)),
            fenster=fenster,
            gemeinsam=d.get("gemeinsam", True) is not False,
            modus=modus,
            pnn_ms=pnn if isinstance(pnn, int) and 1 <= pnn <= 500 else PNN_STANDARD,
            bereich=str(d.get("bereich") or "zeit"),
        )


def _neu(schluessel: str) -> str:
    """Schlüssel älterer Ansichten auf die heutigen abbilden."""
    return {"pnn50": "pnnx"}.get(schluessel, schluessel)


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
    "BLOCK",
    "GLEITEND",
    "PNN_STANDARD",
    "PNN_WAHL",
    "STANDARD_KURVEN",
    "Ansicht",
    "ansicht_lesen",
    "ansichten_lesen",
    "ansichten_schreiben",
]
