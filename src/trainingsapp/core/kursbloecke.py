"""Blöcke eines Kurskapitels (Ben, 12.11.2026, P200; Vertrag `docs/plan_kurse.md` §7).

„Die Kurse werden evtl. recht interaktiv“ — ein Kapitel ist darum eine Folge von **Blöcken**,
die von oben nach unten auf einer Seite stehen:

- ``text`` — Markdown, mit Überschrift;
- ``medium`` — ein Bild, Video, Ton oder PDF (`core.models.Media`, mit Rolle wie an der Übung);
- ``frage`` — eine Frage mit Antworten. Sie **erklärt, sie prüft nicht**: Nichts wird
  gespeichert, nichts gezählt, keine Bedingung hängt daran;
- ``test`` — „Wie lange hältst du die Planke?“: ein **gewöhnlicher Eintrag** der Übung, seit
  das Kapitel erreicht ist. Der Wert wird das Ziel dieser Übung im Kapitelplan;
- ``auswahl`` — „Wähle 2 von 4“: Die gewählten Übungen kommen in den Kapitelplan, ab zwei als
  gleichwertige **Wege** im Ablauf (im Workout wählt man jedes Mal einen).

Ein Kapitel mit ``test`` oder ``auswahl`` legt seine Pläne nicht beim Erreichen an, sondern
erst mit „Plan anlegen“ (`braucht_eingabe`, `vorlage_anwenden`). Gerechnet wird nur aus
**Einträgen und der eigenen Wahl**, nie aus Messwerten (`docs/recht/00_zweckbestimmung.md`).
Ein Kapitel ohne Blöcke zeigt Text und Medien wie bisher (`bloecke_von`).

Dieses Modul kennt kein flet und keine Datenbank.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final

from . import ablauf as ab
from .models import Media, medium_aus_dict, new_id

TEXT: Final = "text"
MEDIUM: Final = "medium"
FRAGE: Final = "frage"
TEST: Final = "test"
AUSWAHL: Final = "auswahl"
ARTEN: Final[dict[str, str]] = {
    TEXT: "Text",
    MEDIUM: "Medium",
    FRAGE: "Frage",
    TEST: "Test",
    AUSWAHL: "Auswahl",
}


@dataclass(frozen=True, slots=True)
class Antwort:
    """Eine Antwort auf eine Frage — ``hinweis`` steht da, sobald man sie antippt."""

    text: str
    richtig: bool = False
    hinweis: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"text": self.text}
        if self.richtig:
            d["richtig"] = True
        if self.hinweis:
            d["hinweis"] = self.hinweis
        return d


@dataclass(slots=True)
class Block:
    """Ein Block eines Kapitels. Welche Felder zählen, sagt ``art``."""

    art: str = TEXT
    id: str = field(default_factory=new_id)
    #: Überschrift (``text``), die Frage (``frage``), die Aufforderung (``test``, ``auswahl``)
    titel: str = ""
    #: Markdown (``text``) bzw. der Satz unter der Aufforderung
    text: str = ""
    medium: Media | None = None
    antworten: list[Antwort] = field(default_factory=list)
    #: ``test``: die Übung und ihr Feld (Schlüssel aus dem Feldvorrat)
    uebung: str = ""
    feld: str = "hold"
    #: ``test``: Ziel = Testwert × Faktor (0,8 = „80 % deiner Zeit“)
    faktor: float = 1.0
    #: ``auswahl``: die Übungen zur Wahl und wie viele man nimmt
    uebungen: list[str] = field(default_factory=list)
    anzahl: int = 1
    #: ``auswahl``: hinter welcher Planübung die Gewählten stehen (1-basiert; 0 = am Ende)
    nach: int = 0
    #: ``test``, ``auswahl``: der Name des Kapitelplans — leer = der erste
    plan: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Wie im Paket (`kapitel[].bloecke[]`) — nur, was zur Art gehört.

        >>> Block(TEXT, id="b1", titel="Warum?", text="Darum.").to_dict()
        {'art': 'text', 'id': 'b1', 'titel': 'Warum?', 'text': 'Darum.'}
        >>> Block(TEST, id="b2", uebung="u1", faktor=0.8).to_dict()
        {'art': 'test', 'id': 'b2', 'uebung': 'u1', 'feld': 'hold', 'faktor': 0.8}
        """
        d: dict[str, Any] = {"art": self.art, "id": self.id}
        if self.titel:
            d["titel"] = self.titel
        if self.text:
            d["text"] = self.text
        if self.art == MEDIUM and self.medium is not None:
            d["medium"] = self.medium.als_dict()
        if self.art == FRAGE:
            d["antworten"] = [a.to_dict() for a in self.antworten]
        if self.art == TEST:
            d["uebung"] = self.uebung
            d["feld"] = self.feld
            if self.faktor != 1.0:
                d["faktor"] = self.faktor
        if self.art == AUSWAHL:
            d["uebungen"] = list(self.uebungen)
            d["anzahl"] = self.anzahl
            if self.nach:
                d["nach"] = self.nach
        if self.art in (TEST, AUSWAHL) and self.plan:
            d["plan"] = self.plan
        return d

    @classmethod
    def from_dict(
        cls, roh: Mapping[str, Any], schluessel: Mapping[str, str] | None = None
    ) -> Block | None:
        """Liest, was `to_dict` schreibt — ``None`` bei unbekannter Art oder einem Block, dem
        das Nötige fehlt. ``schluessel``: Paketschlüssel → ID der Übung (Import).

        >>> Block.from_dict({"art": "hologramm"}) is None
        True
        >>> b = Block.from_dict({"art": "auswahl", "uebungen": ["a", "b", "a"], "anzahl": 9})
        >>> b.uebungen, b.anzahl
        (['a', 'b'], 2)
        >>> Block.from_dict({"art": "test", "uebung": "planke"}, {"planke": "u1"}).uebung
        'u1'
        >>> Block.from_dict({"art": "test"}) is None
        True
        """
        art = str(roh.get("art") or "")
        if art not in ARTEN:
            return None
        zu_id = schluessel or {}
        block = cls(
            art=art,
            id=str(roh.get("id") or "") or new_id(),
            titel=" ".join(str(roh.get("titel") or "").split()),
            text=str(roh.get("text") or "").strip(),
            plan=str(roh.get("plan") or "").strip(),
        )
        if art == MEDIUM:
            block.medium = medium_aus_dict(roh.get("medium"))
            if block.medium is None:
                return None
        if art == FRAGE:
            for a in roh.get("antworten") or []:
                if isinstance(a, Mapping) and str(a.get("text") or "").strip():
                    block.antworten.append(
                        Antwort(
                            str(a["text"]).strip(),
                            bool(a.get("richtig")),
                            str(a.get("hinweis") or "").strip(),
                        )
                    )
            if not block.titel or not block.antworten:
                return None
        if art == TEST:
            uebung = str(roh.get("uebung") or "").strip()
            block.uebung = zu_id.get(uebung, uebung)
            block.feld = str(roh.get("feld") or "hold").strip() or "hold"
            block.faktor = _zahl(roh.get("faktor"), 1.0, 0.1, 3.0)
            if not block.uebung:
                return None
        if art == AUSWAHL:
            for u in roh.get("uebungen") or []:
                uid = zu_id.get(str(u), str(u)).strip()
                if uid and uid not in block.uebungen:
                    block.uebungen.append(uid)
            if not block.uebungen:
                return None
            block.anzahl = int(_zahl(roh.get("anzahl"), 1, 1, len(block.uebungen)))
            block.nach = int(_zahl(roh.get("nach"), 0, 0, 999))
        return block


def _zahl(roh: Any, vorgabe: float, unten: float, oben: float) -> float:
    try:
        wert = float(roh)
    except (TypeError, ValueError):
        return vorgabe
    if not math.isfinite(wert):
        return vorgabe
    return min(max(wert, unten), oben)


def bloecke_lesen(roh: Any, schluessel: Mapping[str, str] | None = None) -> list[Block]:
    """Eine Liste von Blöcken — Unlesbares fällt weg, doppelte IDs auch."""
    ergebnis: list[Block] = []
    ids: set[str] = set()
    for e in roh if isinstance(roh, list) else []:
        if not isinstance(e, Mapping):
            continue
        block = Block.from_dict(e, schluessel)
        if block is not None and block.id not in ids:
            ids.add(block.id)
            ergebnis.append(block)
    return ergebnis


def bloecke_von(bloecke: Sequence[Block], text: str, medien: Iterable[Media]) -> list[Block]:
    """Was das Kapitel zeigt: seine Blöcke — ohne Blöcke der Text und die Medien wie bisher.

    >>> [b.art for b in bloecke_von([], "Hallo", [Media(uri="https://x/v")])]
    ['text', 'medium']
    >>> bloecke_von([Block(TEXT, text="neu")], "alt", [])[0].text
    'neu'
    """
    if bloecke:
        return list(bloecke)
    alt = [Block(TEXT, id="text", text=text)] if text.strip() else []
    alt += [Block(MEDIUM, id=f"medium-{n}", medium=m) for n, m in enumerate(medien)]
    return alt


def braucht_eingabe(bloecke: Iterable[Block]) -> bool:
    """Das Kapitel legt seine Pläne erst mit „Plan anlegen“ an (Test oder Auswahl).

    >>> braucht_eingabe([Block(TEXT)]), braucht_eingabe([Block(TEST, uebung="u")])
    (False, True)
    """
    return any(b.art in (TEST, AUSWAHL) for b in bloecke)


def wert_im_test(werte: Mapping[str, Any], feld: str) -> float | None:
    """Der Wert eines Eintrags für einen Test — bei Sätzen der **beste** Satz („wie lange
    kannst du“), nie die Summe.

    >>> wert_im_test({"hold": [40, 48, 35]}, "hold"), wert_im_test({"hold": 48}, "hold")
    (48.0, 48.0)
    >>> wert_im_test({"reps": 10}, "hold") is None
    True
    """
    wert = werte.get(feld)
    try:
        if isinstance(wert, list):
            zahlen = [float(w) for w in wert if w is not None]
            return max(zahlen) if zahlen else None
        return float(wert) if wert is not None and wert != "" else None
    except (TypeError, ValueError):
        return None


def ziel_aus_test(block: Block, wert: float) -> int:
    """Das Ziel im Plan: Testwert × Faktor, auf ganze Einheiten — mindestens 1.

    >>> ziel_aus_test(Block(TEST, uebung="u", faktor=0.8), 48)
    38
    """
    return max(1, round(wert * block.faktor))


def fertig(
    bloecke: Iterable[Block], werte: Mapping[str, float], wahl: Mapping[str, Sequence[str]]
) -> bool:
    """Alles da für „Plan anlegen“: jeder Test hat einen Wert, jede Auswahl ihre Anzahl.

    >>> b = [Block(TEST, id="t", uebung="u"), Block(AUSWAHL, id="a", uebungen=["x", "y"])]
    >>> fertig(b, {"t": 48}, {}), fertig(b, {"t": 48}, {"a": ["x"]})
    (False, True)
    """
    for b in bloecke:
        if b.art == TEST and b.id not in werte:
            return False
        if b.art == AUSWAHL and len(wahl.get(b.id, ())) != b.anzahl:
            return False
    return True


def vorlage_anwenden(
    vorlagen: Sequence[Any],
    bloecke: Iterable[Block],
    werte: Mapping[str, float],
    wahl: Mapping[str, Sequence[str]],
    je_satz: Callable[[str, str], bool] | None = None,
) -> list[Any]:
    """Die Plan-Vorlagen des Kapitels (`core.kurse.PlanVorlage`) mit Testwerten und Auswahl.

    - ``test``: Jede Planübung dieser Übung im gemeinten Plan bekommt das Ziel im Feld des
      Tests (das übrige Ziel bleibt). ``je_satz(uebung, feld)``: das Feld hält je Satz einen
      Wert (Satzliste) — dann steht das Ziel als ein Satz ``[48]``.
    - ``auswahl``: Die Gewählten kommen hinter die Stelle ``nach`` (0 = ans Ende). Ab zwei
      Gewählten und ohne gezeichneten Ablauf der Vorlage werden sie gleichwertige **Wege**:
      Die Planübung davor führt zu jeder von ihnen, jede führt zur nächsten danach. Hat die
      Vorlage schon einen Ablauf, kommen die Gewählten ans Ende und der Ablauf bleibt.

    >>> from trainingsapp.core.kurse import PlanVorlage, VorlageItem
    >>> v = PlanVorlage("Rumpf", items=[VorlageItem("planke"), VorlageItem("dehnen")])
    >>> b = [Block(TEST, id="t", uebung="planke"),
    ...      Block(AUSWAHL, id="a", uebungen=["s", "k", "b"], anzahl=2, nach=1)]
    >>> (neu,) = vorlage_anwenden([v], b, {"t": 48}, {"a": ["s", "b"]})
    >>> [(i.exercise_id, i.target) for i in neu.items]
    [('planke', {'hold': 48}), ('s', {}), ('b', {}), ('dehnen', {})]
    >>> sorted((k["von"], k["nach"]) for k in neu.ablauf["kanten"])
    [('#1', '#2'), ('#1', '#3'), ('#2', '#4'), ('#3', '#4')]
    >>> [i.exercise_id for i in v.items]
    ['planke', 'dehnen']
    """
    from .kurse import VorlageItem  # hier, weil `core.kurse` dieses Modul lädt

    ergebnis = [replace(v, items=[replace(i) for i in v.items]) for v in vorlagen]
    if not ergebnis:
        return ergebnis

    def gemeint(block: Block) -> Any:
        return next((v for v in ergebnis if v.name == block.plan), ergebnis[0])

    for block in bloecke:
        if block.art == TEST and block.id in werte:
            for item in gemeint(block).items:
                if item.exercise_id == block.uebung:
                    ziel = ziel_aus_test(block, werte[block.id])
                    liste = je_satz is not None and je_satz(block.uebung, block.feld)
                    item.target = {**item.target, block.feld: [ziel] if liste else ziel}
        if block.art == AUSWAHL:
            gewaehlt = [u for u in wahl.get(block.id, ()) if u in block.uebungen]
            if not gewaehlt:
                continue
            vorlage = gemeint(block)
            verzweigen = len(gewaehlt) >= 2 and not vorlage.ablauf and block.nach >= 1
            stelle = min(block.nach, len(vorlage.items)) if block.nach and not vorlage.ablauf else 0
            neu = [VorlageItem(u) for u in gewaehlt]
            if stelle:
                vorlage.items[stelle:stelle] = neu
            else:
                vorlage.items.extend(neu)
            if verzweigen and stelle:
                vorlage.ablauf = _wege(len(vorlage.items), stelle, len(gewaehlt))
    return ergebnis


def _wege(anzahl: int, stelle: int, wege: int) -> dict[str, Any]:
    """Der Ablauf einer Kette aus ``anzahl`` Planübungen, in der hinter ``stelle`` (1-basiert)
    ``wege`` Planübungen gleichwertig nebeneinander stehen."""
    ids = [f"i{n}" for n in range(1, anzahl + 1)]
    zweige = ids[stelle : stelle + wege]
    danach = ids[stelle + wege] if stelle + wege < anzahl else ab.ENDE
    kanten: list[ab.Kante] = []
    for n in range(anzahl - 1):
        von, nach = ids[n], ids[n + 1]
        if von in zweige or nach in zweige:
            continue
        kanten.append(ab.Kante(von, nach))
    for z in zweige:
        kanten.append(ab.Kante(ids[stelle - 1], z))
        kanten.append(ab.Kante(z, danach))
    return ab.als_position(ab.Ablauf(an=True, start=ids[0], kanten=tuple(kanten)), ids)


__all__ = [
    "ARTEN",
    "AUSWAHL",
    "FRAGE",
    "MEDIUM",
    "TEST",
    "TEXT",
    "Antwort",
    "Block",
    "bloecke_lesen",
    "bloecke_von",
    "braucht_eingabe",
    "fertig",
    "vorlage_anwenden",
    "wert_im_test",
    "ziel_aus_test",
]
