"""Varianten einer Übung — „Liegestütz kurz/lang“ (Ben, 21.10.2026; `docs/plan_varianten.md`).

Eine Variante ist ein Etikett **innerhalb** einer Übung: Man wechselt nicht die Übung, um
kurze und lange Liegestütze zu trennen. Gespeichert wird sie als Ausprägungsfeld
``variant`` (Auswahl) in der `ResultSpec` der Übung:

- die Namen in ``quick`` — ihre Reihenfolge ist die der Knöpfe beim Eintragen,
- Symbol, Kürzel und Beschreibung je Name in ``optionen`` (alles freiwillig).

Damit trennt eine Variante Einträge wie Gewicht und Seite (`core.parameter`): Gezählt wird
je Variante für sich (Ben: „Kurze Liegestützen lassen sich 400 in kurzer Zeit machen. 400
lange sind eine ganz andere Übung“). Jede Spec-Kopie eines Eintrags trägt das Feld mit —
die Anzeige bleibt richtig, auch wenn die Übung sich ändert —, es braucht keine Migration,
und ein Paket kann Varianten über ``result_spec`` mitbringen.

Nicht zu verwechseln mit der Kopie einer Übung — die ist eine eigene Übung mit eigener
Kachel im Verlauf.

Reiner Kern: kein Flet, keine Datenbank. Symbole sind Namen von Material-Symbolen in
Kleinschreibung (`SYMBOLE`); die Oberfläche übersetzt sie (`ui.components.varianten`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final

from .result_spec import FieldSpec, FieldType, ResultSpec, ist_leer

#: Schlüssel des Variantenfelds in Spec und Einträgen
VARIANTE: Final[str] = "variant"
#: Name des Felds, wie Formulare und Ziel ihn zeigen
LABEL: Final[str] = "Variante"
NAME_MAX: Final[int] = 30
KUERZEL_MAX: Final[int] = 3
TEXT_MAX: Final[int] = 200

#: Symbole zur Auswahl (Skizze D4): Pfeile, Formen, Person — in dieser Reihenfolge
SYMBOLE: Final[tuple[str, ...]] = (
    "north_east",
    "swap_horiz",
    "height",
    "rotate_right",
    "open_in_full",
    "close_fullscreen",
    "circle_outlined",
    "crop_square",
    "change_history",
    "star_outline",
    "accessibility_new",
)

#: Wie die Variantenzeile beim Eintragen aussieht (`zeilenform`, Skizze A3; Ben, 26.10.2026)
NAMEN: Final[str] = "namen"
ZEILEN: Final[str] = "zeilen"

#: Geschätzte Breite eines Segments mit Namen: je Zeichen, Innenabstand, Symbol davor
ZEICHEN_PX: Final[float] = 8.0
INNEN_PX: Final[float] = 32.0
SYMBOL_PX: Final[float] = 22.0


@dataclass(frozen=True, slots=True)
class Variante:
    """Eine Variante: der Name, dazu wahlweise ein Symbol oder ein Kürzel und eine
    Beschreibung (Skizzen D3/D4)."""

    name: str
    symbol: str = ""
    kuerzel: str = ""
    text: str = ""

    @property
    def hat_zeichen(self) -> bool:
        """Lässt sie sich ohne Namen zeigen — mit Symbol oder Kürzel?

        >>> Variante("diagonal", symbol="north_east").hat_zeichen, Variante("lang").hat_zeichen
        (True, False)
        """
        return bool(self.symbol or self.kuerzel)

    def angaben(self) -> dict[str, str]:
        """Was zum Namen gespeichert wird (`FieldSpec.optionen`) — nur, was gesetzt ist.

        >>> Variante("Unterarm", kuerzel="UA").angaben()
        {'kuerzel': 'UA'}
        """
        paare = (("symbol", self.symbol), ("kuerzel", self.kuerzel), ("text", self.text))
        return {k: v for k, v in paare if v}


def ist_variante(f: FieldSpec) -> bool:
    """Ist das Feld das Variantenfeld einer Übung?"""
    return f.key == VARIANTE and f.type == FieldType.CHOICE


def feld(spec: ResultSpec | None) -> FieldSpec | None:
    """Das Variantenfeld einer Spezifikation — ``None``, wenn es keines gibt."""
    if spec is None:
        return None
    return next((f for f in spec.fields if ist_variante(f)), None)


def aus_feld(f: FieldSpec, name: str) -> Variante:
    """Die Variante ``name`` mit ihren Angaben aus dem Feld."""
    a = f.optionen.get(name) or {}
    return Variante(
        name,
        symbol=str(a.get("symbol") or ""),
        kuerzel=str(a.get("kuerzel") or ""),
        text=str(a.get("text") or ""),
    )


def varianten(spec: ResultSpec | None) -> list[Variante]:
    """Die Varianten einer Übung (oder einer Spec-Kopie), in ihrer Reihenfolge.

    >>> spec = mit_varianten(ResultSpec(), [Variante("kurz"), Variante("lang", kuerzel="L")])
    >>> [(v.name, v.kuerzel) for v in varianten(spec)], varianten(ResultSpec())
    ([('kurz', ''), ('lang', 'L')], [])
    """
    f = feld(spec)
    if f is None:
        return []
    return [aus_feld(f, n) for n in f.quick if isinstance(n, str) and n.strip()]


def namen(spec: ResultSpec | None) -> list[str]:
    return [v.name for v in varianten(spec)]


def finden(spec: ResultSpec | None, name: str) -> Variante:
    """Die Variante dieses Namens mit ihren Angaben aus ``spec`` — gibt es sie dort nicht
    (mehr), nur der Name: Ein Eintrag behält seine Variante, auch wenn die Übung sie nicht
    mehr kennt."""
    f = feld(spec)
    return aus_feld(f, name) if f is not None else Variante(name)


def von(werte: Mapping[str, Any]) -> str:
    """Die Variante eines Eintrags — leer, wenn er keine hat.

    >>> von({"variant": "lang", "reps": [12]}), von({"reps": [12]})
    ('lang', '')
    """
    wert = werte.get(VARIANTE)
    return "" if ist_leer(wert) else str(wert)


def mit_varianten(spec: ResultSpec, liste: Sequence[Variante]) -> ResultSpec:
    """Die Spezifikation mit genau diesen Varianten. Das Feld steht vorn — „lang · 3x15“ —,
    ohne Varianten fällt es weg.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> spec = mit_varianten(SPEC_SAETZE_WDH, [Variante("kurz"), Variante("lang", text="tief")])
    >>> [f.key for f in spec.fields], spec.fields[0].quick, spec.fields[0].optionen
    (['variant', 'reps'], ['kurz', 'lang'], {'lang': {'text': 'tief'}})
    >>> [f.key for f in mit_varianten(spec, []).fields]
    ['reps']
    """
    andere = [f for f in spec.fields if not ist_variante(f)]
    if not liste:
        return replace(spec, fields=andere)
    alt = feld(spec)
    neu = FieldSpec(
        VARIANTE,
        FieldType.CHOICE,
        alt.label if alt is not None else LABEL,
        quick=[v.name for v in liste],
        optionen={v.name: v.angaben() for v in liste if v.angaben()},
    )
    return replace(spec, fields=[neu, *andere])


def name_pruefen(name: str, vorhandene: Iterable[str], bisher: str | None = None) -> str:
    """Der Name einer neuen oder umbenannten Variante, bereinigt — ``ValueError`` mit Grund.

    Groß/klein zählt nicht („Lang“ ist „lang“), ``bisher`` darf bleiben.

    >>> name_pruefen("  ganz   tief ", ["kurz"])
    'ganz tief'
    >>> name_pruefen("Kurz", ["kurz"])
    Traceback (most recent call last):
    ValueError: „Kurz“ gibt es schon
    >>> name_pruefen("Kurz", ["kurz"], bisher="kurz")
    'Kurz'
    """
    bereinigt = " ".join(name.split())
    if not bereinigt:
        raise ValueError("Name fehlt")
    if len(bereinigt) > NAME_MAX:
        raise ValueError(f"höchstens {NAME_MAX} Zeichen")
    andere = {v.casefold() for v in vorhandene if bisher is None or v != bisher}
    if bereinigt.casefold() in andere:
        raise ValueError(f"„{bereinigt}“ gibt es schon")
    return bereinigt


def kuerzel_pruefen(text: str) -> str:
    """Ein Kürzel: bis 3 Zeichen ohne Leerraum — ``ValueError``, wenn länger.

    >>> kuerzel_pruefen(" ua "), kuerzel_pruefen("")
    ('ua', '')
    """
    kuerzel = "".join(text.split())
    if len(kuerzel) > KUERZEL_MAX:
        raise ValueError(f"höchstens {KUERZEL_MAX} Zeichen")
    return kuerzel


def text_pruefen(text: str) -> str:
    """Eine Beschreibung: eine Zeile, höchstens `TEXT_MAX` Zeichen.

    >>> text_pruefen(" ein Arm\\nund das Gegenbein ")
    'ein Arm und das Gegenbein'
    """
    bereinigt = " ".join(text.split())
    if len(bereinigt) > TEXT_MAX:
        raise ValueError(f"höchstens {TEXT_MAX} Zeichen")
    return bereinigt


def ersetzen(liste: Sequence[Variante], bisher: str | None, neu: Variante) -> list[Variante]:
    """``bisher`` durch ``neu`` ersetzen (an derselben Stelle) — ohne ``bisher`` anhängen.

    >>> [v.name for v in ersetzen([Variante("a"), Variante("b")], "a", Variante("c"))]
    ['c', 'b']
    >>> [v.name for v in ersetzen([Variante("a")], None, Variante("b"))]
    ['a', 'b']
    """
    if bisher is None or all(v.name != bisher for v in liste):
        return [*liste, neu]
    return [neu if v.name == bisher else v for v in liste]


def entfernen(liste: Sequence[Variante], name: str) -> list[Variante]:
    return [v for v in liste if v.name != name]


def verschoben(liste: Sequence[Variante], name: str, richtung: int) -> list[Variante]:
    """Eine Variante um eine Stelle nach oben (-1) oder unten (+1).

    >>> [v.name for v in verschoben([Variante("a"), Variante("b")], "b", -1)]
    ['b', 'a']
    """
    neu = list(liste)
    i = next((k for k, v in enumerate(neu) if v.name == name), None)
    if i is None or not 0 <= i + richtung < len(neu):
        return neu
    neu[i], neu[i + richtung] = neu[i + richtung], neu[i]
    return neu


def segment_breite(v: Variante) -> float:
    """Geschätzte Breite eines Segments mit Namen (und Symbol davor)."""
    return len(v.name) * ZEICHEN_PX + INNEN_PX + (SYMBOL_PX if v.symbol else 0.0)


def zeilenform(liste: Sequence[Variante], breite: float) -> str:
    """Wie die Variantenzeile die Varianten zeigt:

    - `NAMEN` — sie passen in eine Zeile: Segmente mit Namen (Skizze A3);
    - `ZEILEN` — sonst Knöpfe mit Zeichen und Namen, die auf so viele Zeilen umbrechen,
      wie sie brauchen (Ben, 26.10.2026: vier Varianten „lesbar auf mehrere Zeilen“ —
      bis dahin nur Zeichen ohne Namen oder zwei Spalten mit abgeschnittenen Namen).

    >>> zeilenform([Variante("kurz"), Variante("lang")], 300)
    'namen'
    >>> atmen = [Variante("Bauch"), Variante("Brust"), Variante("Schultern"), Variante("Rücken")]
    >>> zeilenform(atmen, 300)
    'zeilen'
    """
    if sum(segment_breite(v) for v in liste) <= breite:
        return NAMEN
    return ZEILEN


def zum_bearbeiten(kopie: ResultSpec | None, aktuell: ResultSpec, wert: str = "") -> ResultSpec:
    """Die Spezifikation, mit der ein Eintrag **nachträglich** bearbeitet wird: seine Kopie,
    dazu die heutigen Varianten der Übung — so lässt sich auch ein Eintrag von vor der ersten
    Variante noch auf „lang“ setzen (Skizze A6). Seine eigene Variante bleibt wählbar, auch
    wenn die Übung sie nicht mehr kennt. Hat die Übung keine Varianten, bleibt die Kopie.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> heute = mit_varianten(SPEC_SAETZE_WDH, [Variante("kurz"), Variante("lang")])
    >>> namen(zum_bearbeiten(SPEC_SAETZE_WDH, heute)), namen(zum_bearbeiten(None, heute, "weit"))
    (['kurz', 'lang'], ['kurz', 'lang', 'weit'])
    >>> zum_bearbeiten(SPEC_SAETZE_WDH, SPEC_SAETZE_WDH) is SPEC_SAETZE_WDH
    True
    """
    basis = kopie or aktuell
    liste = varianten(aktuell)
    if not liste:
        return basis
    if wert and wert not in [v.name for v in liste]:
        liste = [*liste, finden(kopie, wert)]
    return mit_varianten(basis, liste)


__all__ = [
    "KUERZEL_MAX",
    "LABEL",
    "NAMEN",
    "NAME_MAX",
    "SYMBOLE",
    "TEXT_MAX",
    "VARIANTE",
    "Variante",
    "aus_feld",
    "entfernen",
    "ersetzen",
    "feld",
    "finden",
    "ist_variante",
    "kuerzel_pruefen",
    "mit_varianten",
    "name_pruefen",
    "namen",
    "segment_breite",
    "text_pruefen",
    "varianten",
    "verschoben",
    "von",
    "zeilenform",
    "zum_bearbeiten",
]
