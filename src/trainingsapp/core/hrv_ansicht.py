"""Ansicht der HRV-Messung: welche Verlaufskurven unter der Hauptkurve stehen.

Die Hauptkurve (RR- bzw. PPI-Tachogramm) steht immer oben. Darunter wählt man
einen Analysebereich — Zeit, Frequenz, Nichtlinear — und darin die
Verlaufskurven (`hrv_core.trends.KENNZAHLEN`), je mit eigenem Fenster und als
gleitender Wert oder in Blöcken. Eine Ansicht lässt sich unter einem Namen
speichern und wieder laden (praxis_gui: „Vorlagen").

**Mehrere Kurven in einem Diagramm?** Nur auf gleicher Achse (``gemeinsam``):
RMSSD und SDNN teilen sich die ms-Achse der Variabilität, LF und HF die
ms²-Achse. Ø RR hat zwar auch ms, liegt aber bei 800 statt 40 ms und bekommt
eine eigene Achse — sonst wäre RMSSD eine flache Linie am Boden. Hochkant
sind zwei y-Achsen nebeneinander zu schmal; dort stehen die Diagramme
untereinander.

**Vollbild (quer, Ben 16.10.2026): zwei y-Achsen wie in praxis_gui.** ``links``
und ``rechts`` nennen die Kurven an der linken und der rechten Achse, `ROH` ist
das Tachogramm (Vorgabe links). Je Seite **eine** Skala: Kurven gleicher Achse
teilen sie (HF Gerät und Ø HF), eine Kurve anderer Skala ersetzt die Seite
(`achse_waehlen`). Kombinieren darf man über die Analysebereiche hinweg —
RMSSD links, DFA α1 rechts.

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
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

#: Rohpunkte der Tachogramm-Kurven (grau, Artefakte) zeigen RR-Werte in diesem Bereich (ms) —
#: live und in der Aufzeichnung dieselben Grenzen; vorher 250–2200 und 200–2600 (H38)
ROH_MIN_MS: Final = 200
ROH_MAX_MS: Final = 2600
#: Kleinste Spanne der Pulskurve (bpm) — sonst füllte jedes Zucken die Höhe
HF_SPANNE_MIN_BPM: Final = 10.0

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
#: (4: Kurven des Vollbilds je Achse)
VERSION: Final[int] = 4
#: Vollbild: das Tachogramm (RR bzw. PPI) — keine Kennzahl, aber wählbar wie eine
ROH: Final[str] = "roh"
#: Seiten der Werteachsen im Vollbild
LINKS: Final[str] = "links"
RECHTS: Final[str] = "rechts"
#: Vorgabe des Vollbilds: Rohdaten links, Kurzzeitvariabilität rechts
VOLL_LINKS: Final[tuple[str, ...]] = (ROH,)
VOLL_RECHTS: Final[tuple[str, ...]] = ("rmssd",)


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
    #: Vollbild: Kurven an der linken und der rechten Achse (`ROH` = Tachogramm)
    links: list[str] = field(default_factory=lambda: list(VOLL_LINKS))
    rechts: list[str] = field(default_factory=lambda: list(VOLL_RECHTS))

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

    # -- Vollbild: zwei Achsen ---------------------------------------------------

    def achse_waehlen(self, seite: str, kennzahl: str, achse: Callable[[str], str | None]) -> None:
        """Eine Kurve aus der Liste an die Achse ``seite`` — dazu, weg, ersetzen, tauschen.

        - Steht sie dort schon, geht sie weg. Die linke Achse bleibt nie leer:
          Dann rückt die rechte nach links (ohne rechte bleibt die Kurve).
        - Steht sie auf der anderen Seite, tauschen die Seiten.
        - Hat sie dieselbe Skala wie die Kurven dort, kommt sie dazu.
        - Sonst ersetzt sie die Kurven dieser Seite.

        ``achse`` liefert den Schlüssel der Werteachse (wie bei `gruppen`).

        >>> ach = {"roh": "rr", "rmssd": "var", "sdnn": "var", "dfa_alpha1": "alpha"}.get
        >>> a = Ansicht()
        >>> a.links, a.rechts
        (['roh'], ['rmssd'])
        >>> a.achse_waehlen(RECHTS, "sdnn", ach); a.rechts
        ['rmssd', 'sdnn']
        >>> a.achse_waehlen(RECHTS, "dfa_alpha1", ach); a.rechts
        ['dfa_alpha1']
        >>> a.achse_waehlen(LINKS, "rmssd", ach); a.links, a.rechts
        (['rmssd'], ['dfa_alpha1'])
        >>> a.achse_waehlen(LINKS, "dfa_alpha1", ach); a.links, a.rechts
        (['dfa_alpha1'], ['rmssd'])
        >>> a.achse_waehlen(LINKS, "dfa_alpha1", ach); a.links, a.rechts
        (['rmssd'], [])
        >>> a.achse_waehlen(LINKS, "rmssd", ach); a.links
        ['rmssd']
        """
        hier, dort = (self.links, self.rechts) if seite == LINKS else (self.rechts, self.links)
        if kennzahl in hier:
            hier.remove(kennzahl)
            if not self.links:
                self.links, self.rechts = (self.rechts, []) if self.rechts else ([kennzahl], [])
            return
        if kennzahl in dort:
            self.links, self.rechts = self.rechts, self.links
            return
        skala = achse(kennzahl)
        if hier and skala is not None and achse(hier[0]) == skala:
            hier.append(kennzahl)
        else:
            hier[:] = [kennzahl]

    def rechts_leeren(self) -> None:
        """Rechts keine Kurve — nur die linke Achse."""
        self.rechts = []

    def seiten_tauschen(self) -> None:
        """Links und rechts tauschen; ohne rechte Kurve ändert sich nichts.

        >>> a = Ansicht(links=["roh"], rechts=["rmssd"]); a.seiten_tauschen(); a.links, a.rechts
        (['rmssd'], ['roh'])
        """
        if self.rechts:
            self.links, self.rechts = self.rechts, self.links

    def achse_blaettern(self, seite: str, schritt: int, angebot: Sequence[str]) -> None:
        """Pfeile ‹ ›: die nächste bzw. vorige Kurve des Angebots an diese Achse.

        Was auf der anderen Seite steht, wird übersprungen; rechts gehört „keine
        Kurve" zur Runde, links nicht. Mehrere Kurven einer Seite weichen der
        einen nächsten.

        >>> a = Ansicht(links=["roh"], rechts=["rmssd"])
        >>> angebot = ["roh", "hf_rr", "rmssd", "sdnn"]
        >>> a.achse_blaettern(RECHTS, 1, angebot); a.rechts
        ['sdnn']
        >>> a.achse_blaettern(RECHTS, 1, angebot); a.rechts
        []
        >>> a.achse_blaettern(RECHTS, 1, angebot); a.rechts
        ['hf_rr']
        >>> a.achse_blaettern(LINKS, -1, angebot); a.links
        ['sdnn']
        """
        hier = self.links if seite == LINKS else self.rechts
        dort = self.rechts if seite == LINKS else self.links
        runde: list[str | None] = [k for k in angebot if k not in dort]
        if seite == RECHTS:
            runde.insert(0, None)
        if not runde:
            return
        jetzt = hier[0] if hier else None
        i = runde.index(jetzt) if jetzt in runde else (-1 if schritt > 0 else 0)
        neu = runde[(i + schritt) % len(runde)]
        hier[:] = [neu] if neu is not None else []

    def achsen(self, angebot: Iterable[str]) -> tuple[list[str], list[str]]:
        """Was das Vollbild zeichnet: je Seite die Kurven, die es gerade gibt.

        Fällt links alles weg (ein reiner Pulsgeber hat kein Tachogramm), rückt
        die rechte Seite nach links; bleibt nichts, die erste angebotene Kurve.

        >>> Ansicht(links=["roh"], rechts=["hf_geraet"]).achsen(["hf_geraet", "hf_rr"])
        (['hf_geraet'], [])
        >>> Ansicht(links=["roh"], rechts=["rmssd"]).achsen(["hf_geraet"])
        (['hf_geraet'], [])
        """
        da = list(angebot)
        links = [k for k in self.links if k in da]
        rechts = [k for k in self.rechts if k in da]
        if not links:
            links, rechts = rechts or da[:1], []
        return links, rechts

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
            "links": list(self.links),
            "rechts": list(self.rechts),
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
        links = _seite(d.get("links"), VOLL_LINKS) or list(VOLL_LINKS)
        return cls(
            name=str(d.get("name") or "Standard"),
            kurven=list(dict.fromkeys(kurven)),
            fenster=fenster,
            gemeinsam=d.get("gemeinsam", True) is not False,
            modus=modus,
            pnn_ms=pnn if isinstance(pnn, int) and 1 <= pnn <= 500 else PNN_STANDARD,
            bereich=str(d.get("bereich") or "zeit"),
            links=links,
            rechts=[k for k in _seite(d.get("rechts"), VOLL_RECHTS) if k not in links],
        )


def _seite(roh: Any, vorgabe: Iterable[str]) -> list[str]:
    """Kurven einer Vollbild-Achse aus dem Gespeicherten — fehlt sie, die Vorgabe.

    >>> _seite(None, ("roh",)), _seite([], ("rmssd",)), _seite(["pnn50", 3, "pnn50"], ())
    (['roh'], [], ['pnnx'])
    """
    if not isinstance(roh, list):
        return list(vorgabe)
    return list(dict.fromkeys(_neu(k) for k in roh if isinstance(k, str)))


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
    "LINKS",
    "PNN_STANDARD",
    "PNN_WAHL",
    "RECHTS",
    "ROH",
    "STANDARD_KURVEN",
    "VOLL_LINKS",
    "VOLL_RECHTS",
    "Ansicht",
    "ansicht_lesen",
    "ansichten_lesen",
    "ansichten_schreiben",
]
