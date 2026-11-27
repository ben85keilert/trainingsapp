"""Der nächste offene Schritt eines Kapitels (Ben, 27.11.2026,
`docs/plan_kurs_medien_ansicht.md` §5 D2: „weniger Rumgeklicke, direkteres Starten“).

Ein Kapitel ist eine Folge von Dingen, die man tut: etwas ausprobieren, eine Frage
beantworten, die Änderungen am Plan ansehen, weitergehen. Der Fußknopf der Kapitelansicht
nennt immer den **nächsten** davon. Hier steht nur, welcher das ist — gerechnet aus dem, was
die Ansicht ohnehin kennt: Blöcke, Werte der Läufe, gespeicherte Antworten, offene Zeilen der
Sammelkarte. **Nie aus Messwerten**, und nichts geschieht von selbst: Der Knopf führt hin, er
übernimmt nichts.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from trainingsapp.core.kursbloecke import FRAGE, TEST, Block, Gegeben, wenn_stand

#: `Schritt.art`
LAUF: Final = "lauf"
ANTWORT: Final = "antwort"
PLAN: Final = "plan"
WEITER: Final = "weiter"


@dataclass(frozen=True, slots=True)
class Schritt:
    """Was als Nächstes dran ist: ``art``, der Block (bei `LAUF` und `ANTWORT`), der Text des
    Knopfs und ob es **sein muss** (ein Lauf, dessen Wert kein Baustein braucht, ist
    freiwillig — der Knopf nennt ihn, daneben bleibt „Weiter“)."""

    art: str
    text: str
    block_id: str = ""
    pflicht: bool = True


def naechster(
    bloecke: Sequence[Block],
    *,
    gemacht: Collection[str] = (),
    antworten: Mapping[str, Gegeben] | None = None,
    pflicht_laeufe: Collection[str] | None = None,
    plan_offen: int = 0,
    weiter: str = "",
    namen: Mapping[str, str] | None = None,
) -> Schritt | None:
    """Der nächste Schritt — ``None``, wenn nichts offen ist und es kein „Weiter“ gibt.

    ``bloecke``: die Blöcke des Kapitels in ihrer Reihenfolge; ``gemacht``: die Schlüssel der
    Läufe mit einem Wert (`KursRepo.testwerte`: die ID, bei „der gewählten“ ``<id>:<übung>``);
    ``antworten``: was gespeichert ist; ``pflicht_laeufe``: die Läufe, deren Wert gebraucht
    wird (``None``: alle); ``plan_offen``: wie viele Zeilen der Sammelkarte sich übernehmen
    lassen; ``weiter``: der Text des Knopfs zum nächsten Kapitel, leer = geht noch nicht;
    ``namen``: Übung-ID → Name, für den Text an einem Lauf ohne eigenen Titel.

    >>> lauf = Block(TEST, id="t", titel="Seitstütz ausprobieren", uebung="u")
    >>> frage = Block(FRAGE, id="q", titel="Wie war das?")
    >>> from trainingsapp.core import ablauf as ab
    >>> frage.frage = ab.Frage("q", "Wie war das?", art=ab.F_JA_NEIN)
    >>> s = naechster([lauf, frage], pflicht_laeufe=[], weiter="Weiter")
    >>> s.art, s.text, s.pflicht
    ('lauf', 'Seitstütz ausprobieren', False)
    >>> naechster([lauf, frage], gemacht=["t"]).text
    'Antworten: Wie war das?'
    >>> beantwortet = {"q": Gegeben(text="ja")}
    >>> naechster([lauf, frage], gemacht=["t"], antworten=beantwortet, plan_offen=2).text
    'Plan ansehen — 2 Änderungen'
    >>> naechster([lauf, frage], gemacht=["t"], antworten=beantwortet, weiter="Weiter").art
    'weiter'
    >>> naechster([lauf], gemacht=["t"]) is None
    True

    Was an einer Antwort hängt, zählt erst, wenn die Antwort es zeigt:

    >>> from trainingsapp.core.kursbloecke import Wenn
    >>> nur = Block(TEST, id="t2", uebung="u", wenn=[Wenn("q", ("ja",))])
    >>> naechster([nur], antworten={}) is None, naechster([nur], antworten=beantwortet).block_id
    (True, 't2')
    """
    gegeben = antworten or {}
    for b in bloecke:
        if b.baustein or (b.wenn and wenn_stand(b.wenn, gegeben) is not True):
            continue
        if b.art == TEST and not any(g == b.id or g.startswith(b.id + ":") for g in gemacht):
            name = (namen or {}).get(b.uebung, "")
            text = b.titel or (f"{name} machen" if name else "Übung machen")
            return Schritt(LAUF, text, b.id, pflicht_laeufe is None or b.id in pflicht_laeufe)
        if b.art == FRAGE and b.frage is not None and b.id not in gegeben:
            return Schritt(ANTWORT, f"Antworten: {b.titel or 'eine Frage'}", b.id)
    if plan_offen > 0:
        wort = "Änderung" if plan_offen == 1 else "Änderungen"
        return Schritt(PLAN, f"Plan ansehen — {plan_offen} {wort}")
    if weiter:
        return Schritt(WEITER, weiter)
    return None


__all__ = ["ANTWORT", "LAUF", "PLAN", "WEITER", "Schritt", "naechster"]
