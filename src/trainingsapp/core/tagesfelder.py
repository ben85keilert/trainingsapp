"""Tagesfelder — Parameter und Tags an der Tagesnotiz (Ben, 21.10.2026).

Ben (Notiz „Tagesnotiz“): „Auch hier Parameter und Tags ermöglichen … Tracking von
Beschwerden mit Skalen 0-10 … frei wählbares Tag-Label, das solange aktiv getrackt werden
kann, z.B. Trinkmenge … Ibu 400 1,2,3 … mit Variante … wieviele Ibu 400 oder 800 … Das
ganze darf aber auch nicht zu kompliziert werden.“ Plan und Skizzen:
`docs/plan_tagesfelder.md`.

Ein **Tagesfeld** ist ein frei benanntes Label je Profil mit **genau einer Art** (`ARTEN`):
Skala, Anzahl, Menge, Dauer, Ja/Nein oder nur Text. Dazu wahlweise **Varianten** (dasselbe
Feld `variant` wie bei den Übungen, `core.varianten`) und eine Notiz je Wert. Je Feld
**wie oft**: einmal am Tag (ein Wert je Tag und Variante, ein neuer Tipp korrigiert ihn)
oder mehrmals mit Uhrzeit (jeder Tipp ein eigener Wert).

Die Definition ist eine `ResultSpec` — Wertfeld `value` (`WERT`), wahlweise `variant`
davor. Jeder Wert speichert eine Kopie davon; angezeigt wird immer mit der Kopie. Für die
Kurven im Verlauf werden Werte zu `SessionEntry` im Speicher (`als_eintraege`), damit
`core.verlauf` nicht ein zweites Mal rechnet.

**Messwert** (Ben, 28.10.2026, `docs/plan_tagesfelder_messwert.md`): ein abgelesener Wert,
der sich nicht addiert — mit einem bis drei **Teilen** (`TEIL_KEYS`: Blutdruck systolisch ·
diastolisch · Puls), je Teil Name, Einheit und Plausibilitätsgrenze (nur gegen Tippfehler).
**Tageswert** je Feld (`Tagesfeld.tageswert`): wie aus mehreren Einträgen eines Tages der
eine Wert wird — Summe, Mittel, Höchster, Niedrigster, Letzter; die Vorgabe hängt an der Art.
**Standardfelder** (`STANDARDFELDER`): angelegt in jedem Profil, löschbar, wiederherstellbar.
**Null ist ein Wert** (Ben: „Die App ist ein Tagebuch“): „0 Kaffee“ lässt sich eintragen.

Hier steht nur Rechnen und Prüfen; Lesen und Schreiben macht `data/tagesfelder.py`.
Rechtlich (`docs/recht/00_zweckbestimmung.md`): nur Zahlen, nie eine Bewertung, kein
Trendpfeil, keine Grenze, keine Erinnerung an Einnahmen.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from typing import Any, Final

from . import varianten as var
from .models import SessionEntry, jetzt, lokaler_tag, new_id
from .result_spec import FieldSpec, FieldType, Layout, ResultSpec

#: Der Schlüssel des Wertfelds in `result` und in der Spezifikation
WERT: Final[str] = "value"

SKALA, ANZAHL, MENGE, DAUER, JA_NEIN, TEXT = "skala", "anzahl", "menge", "dauer", "ja_nein", "text"
MESSWERT = "messwert"
#: Die Arten in der Reihenfolge der Auswahl (Skizze B2) mit ihrem Namen
ARTEN: Final[dict[str, str]] = {
    SKALA: "Skala",
    ANZAHL: "Anzahl",
    MENGE: "Menge",
    DAUER: "Dauer",
    MESSWERT: "Messwert",
    JA_NEIN: "Ja/Nein",
    TEXT: "nur Text",
}
#: Arten, deren Werte sich über den Tag addieren — Schnellknöpfe zählen dazu
SUMMIERT: Final[frozenset[str]] = frozenset({ANZAHL, MENGE, DAUER})
#: Arten mit Zahlen, die ein Tageswert verdichtet (Summe, Mittel …)
ZAHLEN: Final[frozenset[str]] = frozenset({SKALA, ANZAHL, MENGE, DAUER, MESSWERT})
_TYP: Final[dict[str, FieldType]] = {
    SKALA: FieldType.SCALE,
    ANZAHL: FieldType.INT,
    MENGE: FieldType.FLOAT,
    DAUER: FieldType.DURATION,
    MESSWERT: FieldType.READING,
    JA_NEIN: FieldType.BOOL,
}
_ART_VON_TYP: Final[dict[FieldType, str]] = {t: a for a, t in _TYP.items()}
_LABEL: Final[dict[str, str]] = {
    SKALA: "Wert",
    ANZAHL: "Anzahl",
    MENGE: "Menge",
    DAUER: "Dauer",
    MESSWERT: "Wert",
    JA_NEIN: "Ja/Nein",
}
#: Die Teile eines Messworts, in dieser Reihenfolge — der erste ist `WERT`
TEIL_KEYS: Final[tuple[str, ...]] = ("value", "value_2", "value_3")
TEILE_MAX: Final[int] = len(TEIL_KEYS)

#: Tageswert (Ben, 28.10.2026): wie aus mehreren Einträgen eines Tages einer wird
TW_SUMME, TW_MITTEL, TW_MAX, TW_MIN, TW_LETZTER = "summe", "mittel", "max", "min", "letzter"
TAGESWERT_NAMEN: Final[dict[str, str]] = {
    TW_SUMME: "Summe",
    TW_MITTEL: "Mittel",
    TW_MAX: "Höchster",
    TW_MIN: "Niedrigster",
    TW_LETZTER: "Letzter des Tages",
}


def tageswert_vorgabe(art: str) -> str:
    """Die Vorgabe je Art: Anzahl, Menge, Dauer summieren; Skala und Messwert mitteln.

    >>> tageswert_vorgabe(ANZAHL), tageswert_vorgabe(SKALA), tageswert_vorgabe(TEXT)
    ('summe', 'mittel', '')
    """
    if art in SUMMIERT:
        return TW_SUMME
    if art in (SKALA, MESSWERT):
        return TW_MITTEL
    return ""


def tageswert_optionen(art: str) -> list[str]:
    """Was sich je Art einstellen lässt (Plan §1) — leer bei Ja/Nein und Text.

    >>> tageswert_optionen(MENGE), tageswert_optionen(MESSWERT), tageswert_optionen(JA_NEIN)
    (['summe', 'mittel', 'max', 'letzter'], ['mittel', 'max', 'min', 'letzter'], [])
    """
    if art in SUMMIERT:
        return [TW_SUMME, TW_MITTEL, TW_MAX, TW_LETZTER]
    if art in (SKALA, MESSWERT):
        return [TW_MITTEL, TW_MAX, TW_MIN, TW_LETZTER]
    return []


@dataclass(frozen=True, slots=True)
class Teil:
    """Ein Teil eines Messworts — „systolisch“ in mmHg, 30–300, Pflicht oder optional."""

    name: str
    einheit: str = ""
    von: float | None = None
    bis: float | None = None
    #: darf beim Eintragen leer bleiben (Puls am Blutdruckgerät)
    optional: bool = False


NAME_MAX: Final[int] = 40
#: So viele Schnellknöpfe passen in das Blatt
SCHNELL_MAX: Final[int] = 4
#: Höchstwert für Anzahl und Menge — ein Tippfehler wie „250000“ ist kein Wert
WERT_MAX: Final[float] = 100_000
#: Eine Dauer am Tag höchstens 24 Stunden
DAUER_MAX_S: Final[float] = 24 * 3600


# ---------------------------------------------------------------------------
# Definition
# ---------------------------------------------------------------------------


def spec_bauen(
    art: str,
    *,
    von: float = 0,
    bis: float = 10,
    schritt: float = 1,
    einheit: str = "",
    schnell: Sequence[float] = (),
    varianten: Sequence[str | var.Variante] = (),
    teile: Sequence[Teil] = (),
) -> ResultSpec:
    """Die Spezifikation eines Tagesfelds aus seinen Angaben. ``teile``: die Teile eines
    Messworts (ohne Angabe ein Teil „Wert“ mit ``einheit``).

    >>> s = spec_bauen(ANZAHL, schnell=[1], varianten=["400", "800"])
    >>> [f.key for f in s.fields], s.fields[1].type, s.fields[1].quick, s.chart_metrics
    (['variant', 'value'], <FieldType.INT: 'int'>, [1], ['value'])
    >>> spec_bauen(TEXT).fields, spec_bauen(TEXT).layout
    ([], <Layout.FREEFORM: 'freeform'>)
    >>> f = spec_bauen(SKALA, von=1, bis=5).fields[0]
    >>> (f.min, f.max, f.step, f.quick)
    (1, 5, 1, [])
    >>> bd = spec_bauen(MESSWERT, teile=[Teil("systolisch", "mmHg", 30, 300),
    ...                                  Teil("diastolisch", "mmHg", 30, 300),
    ...                                  Teil("Puls", "bpm", 20, 250, optional=True)])
    >>> [(f.key, f.label, f.unit, f.required) for f in bd.fields]  # doctest: +NORMALIZE_WHITESPACE
    [('value', 'systolisch', 'mmHg', True), ('value_2', 'diastolisch', 'mmHg', True),
     ('value_3', 'Puls', 'bpm', False)]
    """
    if art not in ARTEN:
        raise ValueError(f"unbekannte Art: {art}")
    felder: list[FieldSpec] = []
    if art == MESSWERT:
        teil_liste = list(teile)[:TEILE_MAX] or [Teil("Wert", einheit.strip())]
        for i, t in enumerate(teil_liste):
            f = FieldSpec(TEIL_KEYS[i], FieldType.READING, t.name.strip() or f"Teil {i + 1}")
            f.unit = t.einheit.strip() or None
            f.min, f.max = t.von, t.bis
            f.required = i == 0 or not t.optional
            felder.append(f)
    elif art != TEXT:
        f = FieldSpec(WERT, _TYP[art], _LABEL[art])
        if art == SKALA:
            f.min, f.max, f.step = von, bis, schritt
        elif art == DAUER:
            f.unit = "s"
        elif einheit.strip():
            f.unit = einheit.strip()
        if art in SUMMIERT:
            f.quick = [_als_zahl(q) for q in schnell if q and q > 0][:SCHNELL_MAX]
        felder.append(f)
    spec = ResultSpec(
        layout=Layout.FREEFORM if art == TEXT else Layout.SINGLE,
        fields=felder,
        chart_metrics=[f.key for f in felder] if art not in (TEXT, JA_NEIN) else [],
    )
    liste = [v if isinstance(v, var.Variante) else var.Variante(v) for v in varianten]
    return var.mit_varianten(spec, liste)


def wertfeld(spec: ResultSpec | None) -> FieldSpec | None:
    """Das Wertfeld (beim Messwert der erste Teil) — ``None`` bei „nur Text“."""
    return spec.field_by_key(WERT) if spec is not None else None


def teile_von(spec: ResultSpec | None) -> list[FieldSpec]:
    """Die Teile eines Messworts in ihrer Reihenfolge — bei anderen Arten das Wertfeld.

    >>> [f.key for f in teile_von(spec_bauen(MESSWERT, teile=[Teil("a"), Teil("b")]))]
    ['value', 'value_2']
    >>> [f.key for f in teile_von(spec_bauen(MENGE))], teile_von(spec_bauen(TEXT))
    (['value'], [])
    """
    if spec is None:
        return []
    return [f for k in TEIL_KEYS if (f := spec.field_by_key(k)) is not None]


def teile_lesen(spec: ResultSpec | None) -> list[Teil]:
    """Die Teile als `Teil` — fürs Formular.

    >>> bd = spec_bauen(MESSWERT, teile=[Teil("sys", "mmHg", 30, 300), Teil("Puls", optional=True)])
    >>> teile_lesen(bd)  # doctest: +NORMALIZE_WHITESPACE
    [Teil(name='sys', einheit='mmHg', von=30, bis=300, optional=False),
     Teil(name='Puls', einheit='', von=None, bis=None, optional=True)]
    """
    return [
        Teil(f.label, f.unit or "", f.min, f.max, optional=not f.required and i > 0)
        for i, f in enumerate(teile_von(spec))
    ]


def art_von(spec: ResultSpec | None) -> str:
    """Die Art aus der Spezifikation (auch aus einer Spec-Kopie).

    >>> art_von(spec_bauen(MENGE, einheit="ml")), art_von(spec_bauen(TEXT)), art_von(None)
    ('menge', 'text', 'text')
    """
    f = wertfeld(spec)
    return _ART_VON_TYP.get(f.type, TEXT) if f is not None else TEXT


def teile_pruefen(teile: Sequence[Teil]) -> list[Teil]:
    """Die Teile eines Messworts aus dem Formular — ``ValueError`` mit Grund.

    >>> teile_pruefen([Teil(" sys ", "mmHg"), Teil("dia", "mmHg")])[0].name
    'sys'
    >>> teile_pruefen([])
    Traceback (most recent call last):
    ValueError: Ein Messwert braucht mindestens einen Teil.
    >>> teile_pruefen([Teil("a"), Teil("a")])
    Traceback (most recent call last):
    ValueError: Zwei Teile heißen „a“.
    """
    liste = [replace(t, name=" ".join(t.name.split()), einheit=t.einheit.strip()) for t in teile]
    liste = [t for t in liste if t.name]
    if not liste:
        raise ValueError("Ein Messwert braucht mindestens einen Teil.")
    if len(liste) > TEILE_MAX:
        raise ValueError(f"Höchstens {TEILE_MAX} Teile.")
    namen = [t.name.casefold() for t in liste]
    for n in namen:
        if namen.count(n) > 1:
            raise ValueError(f"Zwei Teile heißen „{liste[namen.index(n)].name}“.")
    for t in liste:
        if t.von is not None and t.bis is not None and t.bis <= t.von:
            raise ValueError(f"„{t.name}“: „bis“ muss größer sein als „von“.")
    return liste


def schnellwerte(spec: ResultSpec | None) -> list[float]:
    """Die Schnellknöpfe eines Felds (nur Anzahl, Menge, Dauer)."""
    f = wertfeld(spec)
    if f is None or art_von(spec) not in SUMMIERT:
        return []
    return [q for q in f.quick if isinstance(q, int | float) and not isinstance(q, bool) and q > 0]


def mit_varianten(spec: ResultSpec, namen: Sequence[str]) -> ResultSpec:
    """Dieselbe Spezifikation mit diesen Varianten — die Angaben bisheriger bleiben."""
    alt = {v.name: v for v in var.varianten(spec)}
    return var.mit_varianten(spec, [alt.get(n, var.Variante(n)) for n in namen])


def name_pruefen(name: str, vorhandene: Iterable[str], bisher: str | None = None) -> str:
    """Der Name eines Tagesfelds, bereinigt — ``ValueError`` mit Grund.

    >>> name_pruefen("  Ibu  ", ["Trinken"])
    'Ibu'
    >>> name_pruefen("trinken", ["Trinken"])
    Traceback (most recent call last):
    ValueError: „Trinken“ gibt es schon.
    >>> name_pruefen("Trinken", ["Trinken"], bisher="Trinken")
    'Trinken'
    """
    text = " ".join(name.split())
    if not text:
        raise ValueError("Name?")
    if len(text) > NAME_MAX:
        raise ValueError(f"Höchstens {NAME_MAX} Zeichen.")
    gleich = [
        n
        for n in vorhandene
        if n.casefold() == text.casefold() and n.casefold() != (bisher or "").casefold()
    ]
    if gleich:
        raise ValueError(f"„{gleich[0]}“ gibt es schon.")
    return text


@dataclass(slots=True)
class Tagesfeld:
    """Ein Tagesfeld — was jemand an jedem Tag festhalten will."""

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    name: str = ""
    spec: ResultSpec = field(default_factory=lambda: spec_bauen(TEXT))
    #: mehrmals mit Uhrzeit (sonst einmal am Tag)
    mehrmals: bool = False
    #: steht unter Heute; aus = ausgeschaltet, alles bleibt
    aktiv: bool = True
    reihenfolge: int = 0
    created_at: datetime = field(default_factory=jetzt)
    #: gelöscht seit — die Werte bleiben, außer sie wurden mitgelöscht
    deleted_at: datetime | None = None
    #: Tageswert (`TAGESWERT_NAMEN`) — leer: die Vorgabe der Art (`tageswert_vorgabe`)
    tageswert: str = ""
    #: aus den Standardfeldern der App (`STANDARDFELDER`), etwa ``"blutdruck"``
    standard_key: str | None = None
    #: festes Feld der App (Ben, 29.10.2026): nicht löschbar, nur ausschaltbar — gekoppelt
    #: mit der HF-Messung (Ruhepuls, Anstrengung), Migration 034
    fest: bool = False

    @property
    def art(self) -> str:
        return art_von(self.spec)

    @property
    def wirksamer_tageswert(self) -> str:
        """Was gilt — eingestellt oder die Vorgabe der Art.

        >>> Tagesfeld(spec=spec_bauen(MENGE)).wirksamer_tageswert
        'summe'
        >>> Tagesfeld(spec=spec_bauen(MENGE), tageswert="max").wirksamer_tageswert
        'max'
        """
        art = self.art
        if self.tageswert in tageswert_optionen(art):
            return self.tageswert
        return tageswert_vorgabe(art)

    @property
    def teile(self) -> list[FieldSpec]:
        return teile_von(self.spec)

    @property
    def varianten(self) -> list[str]:
        return var.namen(self.spec)

    @property
    def schnell(self) -> list[float]:
        return schnellwerte(self.spec)

    def zusammenfassung(self) -> str:
        """Die zweite Zeile in der Liste (Skizze B1).

        >>> Tagesfeld(name="Ibu", spec=spec_bauen(ANZAHL, schnell=[1], varianten=["400", "800"]),
        ...           mehrmals=True).zusammenfassung()
        'Anzahl · 400, 800 · mehrmals mit Uhrzeit'
        >>> Tagesfeld(spec=spec_bauen(SKALA)).zusammenfassung()
        'Skala 0–10 · einmal am Tag'
        >>> Tagesfeld(spec=spec_bauen(MENGE, einheit="ml", schnell=[250, 500]),
        ...           mehrmals=True).zusammenfassung()
        'Menge in ml · +250 ml, +500 ml · mehrmals mit Uhrzeit'
        """
        f = wertfeld(self.spec)
        teile = [art_text(self.spec)]
        if self.varianten:
            teile.append(", ".join(self.varianten))
        elif f is not None and self.schnell:
            teile.append(", ".join(schnell_text(f, q) for q in self.schnell))
        teile.append("mehrmals mit Uhrzeit" if self.mehrmals else "einmal am Tag")
        if self.mehrmals and self.art in ZAHLEN and self.tageswert:
            teile.append(f"Tageswert: {TAGESWERT_NAMEN.get(self.tageswert, self.tageswert)}")
        return " · ".join(teile)


def art_text(spec: ResultSpec | None) -> str:
    """„Skala 0–10“, „Menge in ml“, „Anzahl“, „nur Text“."""
    art = art_von(spec)
    f = wertfeld(spec)
    if art == SKALA and f is not None:
        return f"Skala {zahl(f.min or 0)}–{zahl(f.max if f.max is not None else 10)}"
    if art in (ANZAHL, MENGE) and f is not None and f.unit:
        return f"{ARTEN[art]} in {f.unit}"
    if art == MESSWERT:
        teile = teile_von(spec)
        if len(teile) > 1:
            return "Messwert " + " / ".join(f.label for f in teile)
        if teile and teile[0].unit:
            return f"Messwert in {teile[0].unit}"
    return ARTEN[art]


# ---------------------------------------------------------------------------
# Werte
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Tageswert:
    """Ein Wert eines Tagesfelds — unveränderlich, eine Korrektur ist ein neuer Wert."""

    id: str = field(default_factory=new_id)
    subject_id: str = ""
    feld_id: str = ""
    tag: date = field(default_factory=lambda: lokaler_tag(jetzt()))
    zeit: datetime = field(default_factory=jetzt)
    result: dict[str, Any] = field(default_factory=dict)
    spec: ResultSpec = field(default_factory=ResultSpec)
    note: str = ""
    ersetzt: str | None = None
    created_at: datetime | None = None

    @property
    def variante(self) -> str:
        return var.von(self.result)

    @property
    def wert(self) -> Any:
        return self.result.get(WERT)

    @property
    def werte(self) -> tuple[Any, ...]:
        """Die Teile eines Messworts (``None``, wo einer fehlt) — bei anderen Arten ein Tupel
        mit dem Wert.

        >>> Tageswert(result={"value": 128, "value_2": 82}).werte
        (128, 82, None)
        >>> Tageswert(result={"value": 3}).werte
        (3, None, None)
        """
        return tuple(self.result.get(k) for k in TEIL_KEYS)


def ergebnis(wert: Any = None, variante: str = "") -> dict[str, Any]:
    """Was in `result` steht: Variante und Wert, leeres weggelassen. Ein Tupel oder eine
    Liste sind die Teile eines Messworts (``None`` = Teil leer).

    >>> ergebnis(2, "400"), ergebnis(None), ergebnis(0)
    ({'variant': '400', 'value': 2}, {}, {'value': 0})
    >>> ergebnis((128, 82, None))
    {'value': 128, 'value_2': 82}
    """
    d: dict[str, Any] = {}
    if variante:
        d[var.VARIANTE] = variante
    if isinstance(wert, list | tuple):
        for k, w in zip(TEIL_KEYS, wert, strict=False):
            if w is not None:
                d[k] = w
    elif wert is not None:
        d[WERT] = wert
    return d


def _als_zahl(x: float) -> float | int:
    return int(x) if float(x).is_integer() else x


def zahl(wert: float) -> str:
    """„3“, „2,5“, „1,25“ — deutsch, ohne überflüssige Stellen."""
    if float(wert).is_integer():
        return str(int(wert))
    return f"{wert:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def dauer_text(sekunden: float) -> str:
    """Eine Dauer am Tag: „45 s“, „10 min“, „1 h 30 min“, „7 h“.

    >>> [dauer_text(s) for s in (45, 600, 5400, 25200, 630)]
    ['45 s', '10 min', '1 h 30 min', '7 h', '10:30 min']
    """
    s = round(sekunden)
    if s < 60:
        return f"{s} s"
    if s % 60:
        return f"{s // 60}:{s % 60:02d} min"
    minuten = s // 60
    h, m = divmod(minuten, 60)
    if not h:
        return f"{m} min"
    return f"{h} h {m} min" if m else f"{h} h"


def menge_text(wert: float, einheit: str | None) -> str:
    """„750 ml“, „1,25 l“ (ab 1000 ml), „3 Gläser“.

    >>> menge_text(750, "ml"), menge_text(1250, "ml"), menge_text(3, "Gläser"), menge_text(2, "")
    ('750 ml', '1,25 l', '3 Gläser', '2')
    """
    if einheit == "ml" and abs(wert) >= 1000:
        return f"{zahl(round(wert / 1000, 2))} l"
    return f"{zahl(wert)} {einheit}".strip() if einheit else zahl(wert)


def messwert_text(spec: ResultSpec | None, werte: Sequence[Any]) -> str:
    """Ein Messwert mit allen Teilen: „128/82 mmHg“, „128/82 mmHg · 72 bpm“, „72,4 kg“.
    Teile mit derselben Einheit stehen mit „/“ zusammen, die Einheit einmal dahinter;
    ein leerer optionaler Teil fehlt. Leer, wenn der erste Teil fehlt.

    >>> bd = spec_bauen(MESSWERT, teile=[Teil("sys", "mmHg"), Teil("dia", "mmHg"),
    ...                                  Teil("Puls", "bpm", optional=True)])
    >>> messwert_text(bd, (128, 82, 72)), messwert_text(bd, (128, 82, None))
    ('128/82 mmHg · 72 bpm', '128/82 mmHg')
    >>> messwert_text(spec_bauen(MESSWERT, einheit="kg"), (72.4,)), messwert_text(bd, (None, 82))
    ('72,4 kg', '')
    """
    teile = teile_von(spec)
    if not teile:
        return ""
    liste = list(werte)[: len(teile)]
    if not liste or liste[0] is None:
        return ""
    gruppen: list[tuple[str, list[str]]] = []  # (Einheit, Zahlen) in Reihenfolge
    for f, w in zip(teile, liste, strict=False):
        if w is None:
            continue
        try:
            x = float(w)
        except (TypeError, ValueError):
            continue
        text = "–" if not math.isfinite(x) else zahl(x)
        einheit = f.unit or ""
        if gruppen and gruppen[-1][0] == einheit:
            gruppen[-1][1].append(text)
        else:
            gruppen.append((einheit, [text]))
    return " · ".join(f"{'/'.join(z)} {e}".strip() for e, z in gruppen)


def wert_text(spec: ResultSpec | None, wert: Any) -> str:
    """Ein Wert in der Schreibweise seiner Art — „3“, „1,25 l“, „10 min“, „ja“, beim Messwert
    alle Teile („128/82 mmHg“, ``wert`` als Tupel oder nur der erste Teil); leer ohne.

    >>> wert_text(spec_bauen(SKALA), 3), wert_text(spec_bauen(DAUER), 600)
    ('3', '10 min')
    >>> wert_text(spec_bauen(JA_NEIN), False), wert_text(spec_bauen(ANZAHL), None)
    ('nein', '')
    >>> wert_text(spec_bauen(MESSWERT, einheit="kg"), 72.4)
    '72,4 kg'
    """
    f = wertfeld(spec)
    if f is None or wert is None or wert == "":
        return ""
    art = art_von(spec)
    if art == MESSWERT:
        return messwert_text(spec, wert if isinstance(wert, list | tuple) else (wert,))
    if art == JA_NEIN:
        return "ja" if wert else "nein"
    try:
        x = float(wert)
    except (TypeError, ValueError):
        return str(wert)
    if not math.isfinite(x):
        return "–"
    if art == DAUER:
        return dauer_text(x)
    if art in (ANZAHL, MENGE):
        return menge_text(x, f.unit)
    return zahl(x)


def schnell_text(f: FieldSpec, wert: float) -> str:
    """Die Beschriftung eines Schnellknopfs — mit Einheit (Ben, 28.10.2026: „Immer Einheiten
    mit angeben“): „+250 ml“, „+1 l“, „+1“, „+10 min“.

    >>> dauer, anzahl = spec_bauen(DAUER).fields[0], spec_bauen(ANZAHL).fields[0]
    >>> schnell_text(dauer, 600), schnell_text(anzahl, 1)
    ('+10 min', '+1')
    >>> ml = spec_bauen(MENGE, einheit="ml").fields[0]
    >>> schnell_text(ml, 250), schnell_text(ml, 1000)
    ('+250 ml', '+1 l')
    """
    if f.type == FieldType.DURATION:
        return "+" + dauer_text(wert)
    return "+" + menge_text(wert, f.unit)


_STUNDEN_MINUTEN = re.compile(r"^\s*(\d{1,2}):([0-5]\d)\s*(?:h|std)?\s*$", re.IGNORECASE)
_MIT_EINHEIT = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(h|std|stunden?|min|minuten?|m|s|sek|sekunden?)?\s*$",
    re.IGNORECASE,
)
_ZUSAMMEN = re.compile(r"^\s*(\d+)\s*(?:h|std)\s*(\d+)\s*(?:min|m)?\s*$", re.IGNORECASE)


def dauer_lesen(text: str) -> float | None:
    """Sekunden aus einer Dauer am Tag. Eine Zahl allein sind **Minuten** (am Tag denkt man
    in Minuten und Stunden, nicht in Sekunden wie beim Halten); „7:30“ sind Stunden und
    Minuten.

    >>> [dauer_lesen(t) for t in ("10", "1:30", "7 h", "1,5 h", "90 s", "1 h 20", "20 min")]
    [600.0, 5400.0, 25200.0, 5400.0, 90.0, 4800.0, 1200.0]
    >>> dauer_lesen("25 h"), dauer_lesen("x"), dauer_lesen("")
    (None, None, None)
    """
    sekunden: float | None = None
    if (m := _STUNDEN_MINUTEN.match(text)) or (m := _ZUSAMMEN.match(text)):
        sekunden = int(m.group(1)) * 3600.0 + int(m.group(2)) * 60.0
    elif m := _MIT_EINHEIT.match(text):
        zahl_ = float(m.group(1).replace(",", "."))
        einheit = (m.group(2) or "min").lower()
        if einheit.startswith(("h", "std", "stunde")):
            sekunden = zahl_ * 3600
        elif einheit.startswith("s"):
            sekunden = zahl_
        else:
            sekunden = zahl_ * 60
    if sekunden is None or not math.isfinite(sekunden) or not 0 <= sekunden <= DAUER_MAX_S:
        return None
    return float(round(sekunden))


def wert_lesen(spec: ResultSpec | None, text: str) -> float | int | None:
    """Ein eingetippter Wert für Anzahl, Menge, Dauer oder Skala — ``None`` bei Unsinn.

    >>> wert_lesen(spec_bauen(ANZAHL), "3"), wert_lesen(spec_bauen(MENGE), "0,5")
    (3, 0.5)
    >>> wert_lesen(spec_bauen(ANZAHL), "1,5"), wert_lesen(spec_bauen(SKALA), "11")
    (None, None)
    >>> wert_lesen(spec_bauen(DAUER), "45"), wert_lesen(spec_bauen(ANZAHL), "0")
    (2700.0, 0)
    >>> wert_lesen(spec_bauen(MESSWERT, teile=[Teil("kg", "kg", 20, 300)]), "19")
    """
    f = wertfeld(spec)
    if f is None:
        return None
    art = art_von(spec)
    if art == DAUER:
        return dauer_lesen(text)
    try:
        x = float(text.strip().replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(x):
        return None
    if art == SKALA:
        return skala_runden(f, x)
    if art == MESSWERT:
        return teil_lesen(f, text)
    if art == ANZAHL:
        return int(x) if x.is_integer() and 0 <= x <= WERT_MAX else None
    return _als_zahl(x) if 0 <= x <= WERT_MAX else None


def teil_lesen(f: FieldSpec, text: str) -> float | int | None:
    """Ein Teil eines Messworts — innerhalb seiner Plausibilitätsgrenze; ``None`` sonst.

    >>> f = spec_bauen(MESSWERT, teile=[Teil("sys", "mmHg", 30, 300)]).fields[0]
    >>> teil_lesen(f, "128"), teil_lesen(f, "72,5"), teil_lesen(f, "20"), teil_lesen(f, "x")
    (128, 72.5, None, None)
    """
    try:
        x = float(text.strip().replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(x):
        return None
    lo = f.min if f.min is not None else -WERT_MAX
    hi = f.max if f.max is not None else WERT_MAX
    return _als_zahl(round(x, 3)) if lo <= x <= hi else None


_TRENNER = re.compile(r"\s*[/|;]\s*|\s{2,}")


def messwert_aufteilen(text: str) -> list[str]:
    """„128/82“ oder „128/82/72“ in die Teile — ein Feld, in das man alles tippt.

    >>> messwert_aufteilen("128/82"), messwert_aufteilen(" 128 / 82 / 72 ")
    (['128', '82'], ['128', '82', '72'])
    >>> messwert_aufteilen("72,4")
    ['72,4']
    """
    return [t for t in _TRENNER.split(text.strip()) if t]


def messwert_lesen(spec: ResultSpec | None, texte: Sequence[str]) -> tuple[Any, ...] | None:
    """Die Teile eines Messworts aus den Feldern des Blatts: Pflichtteile müssen lesbar
    sein, ein leerer optionaler Teil wird ``None``; sonst ``None`` (mit Fehler im Blatt).

    >>> bd = spec_bauen(MESSWERT, teile=[Teil("sys", "mmHg", 30, 300), Teil("dia", "mmHg", 30, 300),
    ...                                  Teil("Puls", "bpm", 20, 250, optional=True)])
    >>> messwert_lesen(bd, ["128", "82", ""]), messwert_lesen(bd, ["128/82"])
    ((128, 82, None), (128, 82, None))
    >>> messwert_lesen(bd, ["128", ""]) is None
    True
    """
    teile = teile_von(spec)
    if not teile:
        return None
    eingaben = list(texte)
    if len(eingaben) >= 1 and len([t for t in eingaben[1:] if t.strip()]) == 0:
        geteilt = messwert_aufteilen(eingaben[0] or "")
        if len(geteilt) > 1:
            eingaben = geteilt
    eingaben += [""] * (len(teile) - len(eingaben))
    werte: list[Any] = []
    for f, text in zip(teile, eingaben, strict=False):
        if not (text or "").strip():
            if f.required:
                return None
            werte.append(None)
            continue
        w = teil_lesen(f, text)
        if w is None:
            return None
        werte.append(w)
    return tuple(werte)


def eingabe_text(spec: ResultSpec | None, wert: Any) -> str:
    """Ein Wert so, wie man ihn eintippt — `wert_lesen` liest ihn zurück.

    >>> d = spec_bauen(DAUER)
    >>> [eingabe_text(d, s) for s in (600, 5400, 90)], eingabe_text(spec_bauen(MENGE), 0.5)
    (['10', '1:30', '90 s'], '0,5')
    >>> all(wert_lesen(d, eingabe_text(d, s)) == s for s in (600, 5400, 90, 25200))
    True
    """
    if wert is None or isinstance(wert, bool):
        return ""
    if isinstance(wert, list | tuple):
        wert = wert[0] if wert else None
    try:
        x = float(wert)
    except (TypeError, ValueError):
        return ""
    if art_von(spec) != DAUER:
        return zahl(x)
    s = round(x)
    if s % 60:
        return f"{s} s"
    if s < 3600:
        return str(s // 60)
    return f"{s // 3600}:{(s % 3600) // 60:02d}"


def skala_runden(f: FieldSpec, x: float) -> float | int | None:
    """Ein Skalenwert im Bereich, auf den Schritt gerastet — für den Schiebebalken.

    >>> f = spec_bauen(SKALA).fields[0]
    >>> skala_runden(f, 3.4), skala_runden(f, 3.6), skala_runden(f, -1)
    (3, 4, None)
    """
    lo = f.min if f.min is not None else 0
    hi = f.max if f.max is not None else 10
    schritt = f.step or 1
    if not lo - 1e-9 <= x <= hi + 1e-9:
        return None
    gerastet = lo + round((x - lo) / schritt) * schritt
    gerastet = round(min(max(gerastet, lo), hi), 6)
    return _als_zahl(gerastet)


# ---------------------------------------------------------------------------
# Der Stand eines Tages
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Stand:
    """Was ein Tagesfeld an einem Tag zeigt — je Variante einer."""

    variante: str
    #: der Tageswert nach `Tagesfeld.wirksamer_tageswert` (Summe, Mittel, Höchster …), ja
    #: (Ja/Nein), beim Messwert ein Tupel je Teil; ``None`` bei „nur Text“
    wert: float | bool | tuple[float | None, ...] | None
    #: so viele Einträge an diesem Tag
    anzahl: int
    #: der Text (nur Text) oder die letzte Notiz
    text: str = ""


def varianten_reihenfolge(spec: ResultSpec | None, werte: Iterable[Tageswert]) -> list[str]:
    """Die Varianten in der Reihenfolge des Felds, dann entfernte, zuletzt „ohne“ (leer)."""
    vorne = var.namen(spec)
    gesehen = {w.variante for w in werte}
    andere = sorted(v for v in gesehen if v and v not in vorne)
    ergebnis = [v for v in vorne if v in gesehen] + andere
    if "" in gesehen:
        ergebnis.append("")
    return ergebnis


def tagesstand(feld: Tagesfeld, werte: Iterable[Tageswert]) -> list[Stand]:
    """Je Variante der Stand eines Tages, in der Reihenfolge der Varianten.

    >>> ibu = Tagesfeld(id="ibu", spec=spec_bauen(ANZAHL, varianten=["400", "800"]), mehrmals=True)
    >>> w = [Tageswert(feld_id="ibu", result=ergebnis(1, "400")),
    ...      Tageswert(feld_id="ibu", result=ergebnis(1, "400"), note="nach dem Laufen")]
    >>> tagesstand(ibu, w)
    [Stand(variante='400', wert=2.0, anzahl=2, text='nach dem Laufen')]
    >>> schmerz = Tagesfeld(spec=spec_bauen(SKALA), mehrmals=True)
    >>> tagesstand(schmerz, [Tageswert(result={"value": 3}), Tageswert(result={"value": 6})])
    [Stand(variante='', wert=4.5, anzahl=2, text='')]
    >>> tagesstand(Tagesfeld(spec=spec_bauen(TEXT)), [Tageswert(note="Gemüse")])
    [Stand(variante='', wert=None, anzahl=1, text='Gemüse')]
    """
    liste = list(werte)
    ergebnis_: list[Stand] = []
    for v in varianten_reihenfolge(feld.spec, liste):
        teil = [w for w in liste if w.variante == v]
        ergebnis_.append(Stand(v, _verdichtet(feld, teil), len(teil), _letzte_notiz(teil)))
    return ergebnis_


def _letzte_notiz(werte: Sequence[Tageswert]) -> str:
    notizen = [w.note.strip() for w in sorted(werte, key=lambda w: w.zeit) if w.note.strip()]
    return notizen[-1] if notizen else ""


def verdichten(zahlen: Sequence[float], tageswert: str) -> float | None:
    """Mehrere Zahlen eines Tages zu einer — nach dem Tageswert.

    >>> verdichten([3, 6], "mittel"), verdichten([3, 6], "summe"), verdichten([3, 6], "max")
    (4.5, 9.0, 6.0)
    >>> verdichten([3, 6], "min"), verdichten([3, 6], "letzter"), verdichten([], "summe")
    (3.0, 6.0, None)
    """
    if not zahlen:
        return None
    if tageswert == TW_MITTEL:
        return round(sum(zahlen) / len(zahlen), 2)
    if tageswert == TW_MAX:
        return float(max(zahlen))
    if tageswert == TW_MIN:
        return float(min(zahlen))
    if tageswert == TW_LETZTER:
        return float(zahlen[-1])
    return float(sum(zahlen))


def _zahlen(werte: Sequence[Tageswert], teil: int = 0) -> list[float]:
    """Die Zahlen eines Teils, in der Reihenfolge der Uhr."""
    out: list[float] = []
    for w in sorted(werte, key=lambda w: w.zeit):
        try:
            x = w.werte[teil] if teil else w.wert
            if x is None:
                continue
            out.append(float(x))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _verdichtet(
    feld: Tagesfeld, werte: Sequence[Tageswert]
) -> float | bool | tuple[float | None, ...] | None:
    art = feld.art
    if art == TEXT:
        return None
    if art == JA_NEIN:
        ja_nein = [bool(w.wert) for w in werte if w.wert is not None]
        return any(ja_nein) if ja_nein else None
    tw = feld.wirksamer_tageswert
    if art == MESSWERT:
        teile = tuple(verdichten(_zahlen(werte, i), tw) for i in range(len(feld.teile)))
        return None if not teile or teile[0] is None else teile
    return verdichten(_zahlen(werte), tw)


def stand_text(feld: Tagesfeld, staende: Sequence[Stand]) -> str:
    """Was auf dem Knopf unter Heute steht (Skizze A1) — „–“ ohne Wert.

    >>> ibu = Tagesfeld(spec=spec_bauen(ANZAHL, varianten=["400", "800"]))
    >>> stand_text(ibu, [Stand("400", 2.0, 2), Stand("800", 1.0, 1)])
    '400 × 2 · 800 × 1'
    >>> trinken = Tagesfeld(spec=spec_bauen(MENGE, einheit="ml"))
    >>> stand_text(trinken, [Stand("", 1250.0, 5)]), stand_text(trinken, [])
    ('1,25 l', '–')
    >>> schmerz = Tagesfeld(spec=spec_bauen(SKALA, varianten=["Knie", "Rücken"]))
    >>> stand_text(schmerz, [Stand("Knie", 3.0, 1)])
    'Knie 3'
    >>> bd = Tagesfeld(spec=spec_bauen(MESSWERT, teile=[Teil("sys", "mmHg"), Teil("dia", "mmHg")]))
    >>> stand_text(bd, [Stand("", (126.0, 81.0), 2)])
    'Ø 126/81 mmHg · 2×'
    >>> stand_text(Tagesfeld(spec=spec_bauen(TEXT)), [Stand("", None, 1, "Mittags Gemüse")])
    'Mittags Gemüse'
    """
    teile = [t for s in staende if (t := _stand_teil(feld, s))]
    return " · ".join(teile) if teile else "–"


def _stand_teil(feld: Tagesfeld, s: Stand) -> str:
    if feld.art == TEXT:
        return s.text
    if s.wert is None:
        return ""
    f = wertfeld(feld.spec)
    if (
        feld.art == ANZAHL
        and s.variante
        and (f is None or not f.unit)
        and not isinstance(s.wert, tuple)
    ):
        return f"{s.variante} × {zahl(float(s.wert))}"
    text = wert_text(feld.spec, s.wert)
    if feld.art == MESSWERT and s.anzahl > 1:
        # Mehrere Messungen: sagen, was die Zahl ist (Mittel „Ø“, sonst der Name) und wie viele
        tw = feld.wirksamer_tageswert
        vorne = "Ø " if tw == TW_MITTEL else ""
        text = f"{vorne}{text} · {s.anzahl}×"
    return f"{s.variante} {text}" if s.variante else text


def tageszeile(feld: Tagesfeld, werte: Iterable[Tageswert]) -> str:
    """„Schmerz Knie 3“, „Ibu 400 × 2“, „Trinken 1,25 l“ — ein Feld in der Wertezeile eines
    Tages (Tagebuch, Verlauf); leer ohne Wert. Text-Felder stehen nicht in der Zeile.

    >>> ibu = Tagesfeld(name="Ibu", spec=spec_bauen(ANZAHL, varianten=["400"]))
    >>> tageszeile(ibu, [Tageswert(result=ergebnis(1, "400"))] * 2)
    'Ibu 400 × 2'
    >>> tageszeile(Tagesfeld(name="Ernährung", spec=spec_bauen(TEXT)), [Tageswert(note="x")])
    ''
    """
    if feld.art == TEXT:
        return ""
    staende = [s for s in tagesstand(feld, werte) if s.wert is not None]
    return f"{feld.name} {stand_text(feld, staende)}" if staende else ""


def eintrag_text(name: str, w: Tageswert) -> str:
    """Ein einzelner Wert mit Feldname — die Punkte der Zeitleiste, die Titel im Tagebuch:
    „Ibu 400“, „Ibu 400 × 2“, „Trinken 250 ml“, „Schmerz Knie 3“, „Ernährung“.

    >>> s = spec_bauen(ANZAHL, varianten=["400"])
    >>> eintrag_text("Ibu", Tageswert(result=ergebnis(1, "400"), spec=s))
    'Ibu 400'
    >>> eintrag_text("Ibu", Tageswert(result=ergebnis(2, "400"), spec=s))
    'Ibu 400 × 2'
    >>> m = spec_bauen(MENGE, einheit="ml")
    >>> eintrag_text("Trinken", Tageswert(result=ergebnis(250), spec=m))
    'Trinken 250 ml'
    >>> eintrag_text("Ernährung", Tageswert(note="Gemüse", spec=spec_bauen(TEXT)))
    'Ernährung'
    """
    teile = [name]
    if w.variante:
        teile.append(w.variante)
    art = art_von(w.spec)
    f = wertfeld(w.spec)
    if art == MESSWERT:
        if text := messwert_text(w.spec, w.werte):
            teile.append(text)
    elif art == ANZAHL and (f is None or not f.unit) and w.variante:
        if w.wert not in (None, 1):
            teile.append(f"× {wert_text(w.spec, w.wert)}")
    elif art != TEXT and (text := wert_text(w.spec, w.wert)):
        teile.append(text)
    return " ".join(teile)


def einmal_ziel(werte: Iterable[Tageswert], variante: str) -> Tageswert | None:
    """Der Wert, den „einmal am Tag“ korrigiert — der jüngste dieser Variante."""
    passend = [w for w in werte if w.variante == variante]
    return max(passend, key=lambda w: w.zeit) if passend else None


def plus(spec: ResultSpec | None, alt: Any, menge: float) -> float | int:
    """Ein Schnellknopf bei „einmal am Tag“: zum bisherigen Wert dazu.

    >>> plus(spec_bauen(ANZAHL), 2, 1), plus(spec_bauen(MENGE), None, 250)
    (3, 250)
    """
    try:
        basis = float(alt) if alt is not None else 0.0
    except (TypeError, ValueError):
        basis = 0.0
    return _als_zahl(round(basis + menge, 6))


#: Ohne frühere Werte: Nachtragen an einem vergangenen Tag um 12:00 (wie bei den Übungen)
UHRZEIT_NACHTRAGEN: Final[time] = time(12, 0)


def uhrzeit_vorlage(am_tag: Sequence[Tageswert], frueher: Sequence[Tageswert]) -> time:
    """Die vorbelegte Uhrzeit beim Nachtragen an einem vergangenen Tag (Ben, 21.10.2026:
    „Zeit festlegen, dabei soll die alte Zeit genommen werden als Vorlage“): die des
    jüngsten Werts dieses Felds an dem Tag, sonst die seines jüngsten Werts überhaupt
    (Ibu nimmt man oft zur selben Zeit), sonst 12:00.

    >>> from datetime import UTC
    >>> w = Tageswert(zeit=datetime(2026, 10, 19, 6, 10, tzinfo=UTC))
    >>> uhrzeit_vorlage([], []), uhrzeit_vorlage([], [w]) == w.zeit.astimezone().time()
    (datetime.time(12, 0), True)
    """
    for liste in (am_tag, frueher):
        if liste:
            letzte = max(liste, key=lambda w: w.zeit).zeit.astimezone()
            return time(letzte.hour, letzte.minute)
    return UHRZEIT_NACHTRAGEN


def zeitpunkt(tag: date, uhrzeit: time) -> datetime:
    """Tag und Uhrzeit (Ortszeit) als Zeitpunkt mit Zeitzone."""
    return datetime.combine(tag, uhrzeit).astimezone()


# ---------------------------------------------------------------------------
# Rückblick
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Kurve:
    """Eine Linie bzw. ein Stapelteil im Verlauf: je Variante und Teil die Tageswerte."""

    variante: str
    #: Index des Teils (Messwert), sonst 0
    teil: int
    #: Name des Teils („systolisch“), sonst leer
    name: str
    einheit: str
    punkte: list[tuple[date, float]]


def tageskurve(feld: Tagesfeld, werte: Iterable[Tageswert]) -> list[Kurve]:
    """**Eine** Rechnung für Säulen, Linien und Kacheln (Plan §4): je Variante (in ihrer
    Reihenfolge) und je Teil die Tageswerte nach `Tagesfeld.wirksamer_tageswert`, nach
    Tagen sortiert — Tage ohne Wert fehlen.

    >>> trinken = Tagesfeld(spec=spec_bauen(MENGE, einheit="ml"), mehrmals=True)
    >>> mo, di = date(2026, 10, 19), date(2026, 10, 20)
    >>> w = [Tageswert(tag=mo, result=ergebnis(250)), Tageswert(tag=mo, result=ergebnis(500)),
    ...      Tageswert(tag=di, result=ergebnis(300))]
    >>> [(k.variante, k.einheit, k.punkte) for k in tageskurve(trinken, w)]
    [('', 'ml', [(datetime.date(2026, 10, 19), 750.0), (datetime.date(2026, 10, 20), 300.0)])]
    >>> bd = Tagesfeld(spec=spec_bauen(MESSWERT, teile=[Teil("sys", "mmHg"), Teil("dia", "mmHg")]))
    >>> k = tageskurve(bd, [Tageswert(tag=mo, result=ergebnis((128, 82)))])
    >>> [(x.name, x.punkte[0][1]) for x in k]
    [('sys', 128.0), ('dia', 82.0)]
    """
    liste = list(werte)
    if feld.art in (TEXT, JA_NEIN):
        return []
    teile = feld.teile if feld.art == MESSWERT else [wertfeld(feld.spec)]
    out: list[Kurve] = []
    for v in varianten_reihenfolge(feld.spec, liste):
        je_tag: dict[date, list[Tageswert]] = {}
        for w in liste:
            if w.variante == v:
                je_tag.setdefault(w.tag, []).append(w)
        staende = {t: tagesstand(feld, je_tag[t])[0].wert for t in sorted(je_tag)}
        for i, f in enumerate(teile):
            punkte: list[tuple[date, float]] = []
            for t, wert in staende.items():
                x = wert[i] if isinstance(wert, tuple) and i < len(wert) else wert
                if isinstance(x, int | float) and not isinstance(x, bool):
                    punkte.append((t, float(x)))
            if punkte:
                out.append(
                    Kurve(
                        v,
                        i,
                        f.label if feld.art == MESSWERT and f is not None else "",
                        (f.unit or "") if f is not None else "",
                        punkte,
                    )
                )
    return out


def kurven_titel(feld: Tagesfeld) -> str:
    """Die Überschrift der Kurve: „Menge je Tag · Summe“, „Skala · Mittel des Tages“.

    >>> kurven_titel(Tagesfeld(spec=spec_bauen(MENGE), mehrmals=True))
    'Menge je Tag · Summe'
    >>> kurven_titel(Tagesfeld(spec=spec_bauen(SKALA)))
    'Skala 0–10'
    """
    tw = feld.wirksamer_tageswert
    if not tw:
        return art_text(feld.spec)
    if not feld.mehrmals and feld.art not in SUMMIERT:
        return art_text(feld.spec)
    was = {TW_SUMME: "Summe", TW_MITTEL: "Mittel des Tages"}.get(tw, TAGESWERT_NAMEN[tw])
    if feld.art in SUMMIERT:
        return f"{ARTEN[feld.art]} je Tag · {was}"
    return f"{art_text(feld.spec)} · {was}"


def als_eintraege(werte: Iterable[Tageswert]) -> list[tuple[date, SessionEntry]]:
    """Werte als Einträge im Speicher — damit rechnet `core.verlauf` Kurven und Linien je
    Variante. Die Feld-ID steht als ``exercise_id``.

    >>> from trainingsapp.core.verlauf import kennzahlen, linien
    >>> s = spec_bauen(ANZAHL, varianten=["400", "800"])
    >>> mo, di = date(2026, 10, 19), date(2026, 10, 20)
    >>> w = [Tageswert(feld_id="ibu", tag=mo, result=ergebnis(1, "400"), spec=s),
    ...      Tageswert(feld_id="ibu", tag=mo, result=ergebnis(1, "400"), spec=s),
    ...      Tageswert(feld_id="ibu", tag=di, result=ergebnis(1, "800"), spec=s)]
    >>> e = als_eintraege(w)
    >>> (k,) = kennzahlen([x for _, x in e])
    >>> k.label, [(x.variante, [v for _, v in x.werte]) for x in linien(e, k)]
    ('Anzahl je Tag', [('400', [2.0]), ('800', [1.0])])
    """
    return [
        (
            w.tag,
            SessionEntry(
                id=w.id,
                exercise_id=w.feld_id,
                result=dict(w.result),
                spec_snapshot=w.spec,
                note=w.note,
                started_at=w.zeit,
                ended_at=w.zeit,
                created_at=w.created_at,
            ),
        )
        for w in werte
    ]


@dataclass(frozen=True, slots=True)
class Summe:
    """Eine Kachel unter der Kurve (Skizze C3): je Variante im Zeitraum."""

    variante: str
    #: Summe (Anzahl, Menge, Dauer), Mittel (Skala), Tage mit „ja“ (Ja/Nein)
    wert: float
    eintraege: int
    tage: int
    #: Messwert: Mittel der Tageswerte je Teil
    teile: tuple[float | None, ...] = ()


def summen(feld: Tagesfeld, werte: Iterable[Tageswert]) -> list[Summe]:
    """Je Variante, was im Zeitraum zusammenkam — „400 · 9 Stück an 7 Tagen“.

    >>> s = spec_bauen(ANZAHL, varianten=["400", "800"])
    >>> ibu = Tagesfeld(spec=s, mehrmals=True)
    >>> mo, di = date(2026, 10, 19), date(2026, 10, 20)
    >>> w = [Tageswert(tag=mo, result=ergebnis(2, "400")),
    ...      Tageswert(tag=di, result=ergebnis(1, "400")),
    ...      Tageswert(tag=di, result=ergebnis(1, "800"))]
    >>> [(x.variante, x.wert, x.eintraege, x.tage) for x in summen(ibu, w)]
    [('400', 3.0, 2, 2), ('800', 1.0, 1, 1)]
    """
    liste = list(werte)
    ergebnis_: list[Summe] = []
    for v in varianten_reihenfolge(feld.spec, liste):
        teil = [w for w in liste if w.variante == v]
        tage = {w.tag for w in teil}
        if feld.art == JA_NEIN:
            ja = {w.tag for w in teil if w.wert}
            ergebnis_.append(Summe(v, float(len(ja)), len(teil), len(tage)))
            continue
        if feld.art in (SKALA, MESSWERT):
            # Mittel der Tageswerte (jeder Tag zählt gleich, egal wie oft gemessen)
            je_tag = [
                s.wert
                for t in sorted(tage)
                for s in tagesstand(feld, [w for w in teil if w.tag == t])
            ]
            if feld.art == MESSWERT:
                n = len(feld.teile)
                mittel_teile = tuple(
                    verdichten(
                        [
                            float(y)
                            for x in je_tag
                            if isinstance(x, tuple)
                            for y in (x[i],)
                            if y is not None
                        ],
                        TW_MITTEL,
                    )
                    for i in range(n)
                )
                ergebnis_.append(Summe(v, 0.0, len(teil), len(tage), mittel_teile))
                continue
            zahlen = [float(x) for x in je_tag if isinstance(x, int | float)]
            mittel = round(sum(zahlen) / len(zahlen), 2) if zahlen else 0.0
            ergebnis_.append(Summe(v, mittel, len(teil), len(tage)))
            continue
        gesamt = verdichten(_zahlen(teil), TW_SUMME)
        ergebnis_.append(Summe(v, float(gesamt or 0), len(teil), len(tage)))
    return ergebnis_


def summe_text(feld: Tagesfeld, s: Summe) -> str:
    """Der große Wert einer Kachel: „9 Stück“, „12,5 l“, „3 h 20 min“, „Ø 3,4“, „an 5 Tagen“."""
    if feld.art == JA_NEIN:
        return f"{zahl(s.wert)}× ja"
    if feld.art == SKALA:
        return f"Ø {zahl(s.wert)}"
    if feld.art == MESSWERT:
        text = messwert_text(feld.spec, s.teile)
        return f"Ø {text}" if text else "–"
    f = wertfeld(feld.spec)
    if feld.art == ANZAHL and (f is None or not f.unit):
        return f"{zahl(s.wert)} Stück"
    return wert_text(feld.spec, s.wert)


# ---------------------------------------------------------------------------
# Vorschläge (Skizze B2) — füllen das Formular, mehr nicht
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Vorschlag:
    """Eine Vorlage zum Anlegen — und die Definition eines Standardfelds."""

    name: str
    art: str
    mehrmals: bool = False
    von: float = 0
    bis: float = 10
    einheit: str = ""
    schnell: tuple[float, ...] = ()
    varianten: tuple[str, ...] = ()
    #: Gruppe im Blatt „Vorlage wählen“ (`GRUPPEN`)
    gruppe: str = ""
    #: Messwert: die Teile
    teile: tuple[Teil, ...] = ()
    tageswert: str = ""
    #: Standardfeld: sein Schlüssel (`STANDARDFELDER`)
    standard_key: str | None = None
    #: festes Feld: nicht löschbar (alle Standardfelder seit 29.10.2026)
    fest: bool = False

    def feld(self, subject_id: str = "") -> Tagesfeld:
        return Tagesfeld(
            subject_id=subject_id,
            name=self.name,
            spec=spec_bauen(
                self.art,
                von=self.von,
                bis=self.bis,
                einheit=self.einheit,
                schnell=self.schnell,
                varianten=self.varianten,
                teile=self.teile,
            ),
            mehrmals=self.mehrmals,
            tageswert=self.tageswert,
            standard_key=self.standard_key,
            fest=self.fest,
        )


#: Gruppen der Vorlagen, in dieser Reihenfolge
BESCHWERDEN, MESSWERTE, EINNAHMEN, ALLTAG = "Beschwerden", "Messwerte", "Einnahmen", "Alltag"
GRUPPEN: Final[tuple[str, ...]] = (BESCHWERDEN, MESSWERTE, EINNAHMEN, ALLTAG)

#: Blutdruck wie Heimgeräte ihn zeigen: systolisch / diastolisch, der Puls darf leer bleiben.
#: Die Grenzen sind Tippfehler-Schutz, keine Bewertung (`docs/recht/00_zweckbestimmung.md`).
BLUTDRUCK_TEILE: Final[tuple[Teil, ...]] = (
    Teil("systolisch", "mmHg", 30, 300),
    Teil("diastolisch", "mmHg", 30, 300),
    Teil("Puls", "bpm", 20, 250, optional=True),
)

#: Störungen eines Tages (Ben, 29.10.2026, Frage 5): nur ein Feld zum Festhalten — die App
#: fragt nicht nach und bewertet nichts; ein markierter Tag kann aus der Rechenautomatik
#: fallen („nicht mitrechnen“, `data.hf_profil.RechenAusnahmeRepo`).
STOERUNG_VARIANTEN: Final[tuple[str, ...]] = ("Infekt", "Alkohol", "Hitze", "Reise", "wenig Schlaf")

#: Die Vorlagen beim Anlegen (Blatt „Vorlage wählen“, in Gruppen). Neutral benannt
#: (`docs/recht/00_zweckbestimmung.md`): Die App hält fest, was die Person einträgt — sie
#: bewertet nichts und erinnert an nichts. Die **festen** Felder (Ben, 29.10.2026: nicht
#: löschbar, nur ausschaltbar) sind mit der Herzfrequenz-Messung gekoppelt: Ruhepuls
#: (Morgenmessung → Vorschlag, Eintrag → Profil), Anstrengung (sRPE nach der Einheit),
#: Störung (Tag aus der Rechenautomatik).
VORLAGEN: Final[tuple[Vorschlag, ...]] = (
    Vorschlag("Schmerz", SKALA, gruppe=BESCHWERDEN),
    Vorschlag("Stimmung", SKALA, gruppe=BESCHWERDEN),
    Vorschlag("Belastung", SKALA, gruppe=BESCHWERDEN),
    Vorschlag(
        "Anstrengung (sRPE)",
        SKALA,
        gruppe=BESCHWERDEN,
        tageswert=TW_MAX,
        standard_key="srpe",
        fest=True,
    ),
    Vorschlag(
        "Blutdruck",
        MESSWERT,
        mehrmals=True,
        gruppe=MESSWERTE,
        teile=BLUTDRUCK_TEILE,
        tageswert=TW_MITTEL,
        standard_key="blutdruck",
        fest=True,
    ),
    Vorschlag(
        "Gewicht",
        MESSWERT,
        gruppe=MESSWERTE,
        teile=(Teil("Gewicht", "kg", 1, 500),),
        standard_key="gewicht",
        fest=True,
    ),
    Vorschlag(
        "Blutzucker",
        MESSWERT,
        mehrmals=True,
        gruppe=MESSWERTE,
        teile=(Teil("Blutzucker", "mg/dl", 10, 1000),),
    ),
    Vorschlag(
        "SpO₂", MESSWERT, mehrmals=True, gruppe=MESSWERTE, teile=(Teil("SpO₂", "%", 50, 100),)
    ),
    Vorschlag(
        "Temperatur",
        MESSWERT,
        mehrmals=True,
        gruppe=MESSWERTE,
        teile=(Teil("Temperatur", "°C", 30, 45),),
        tageswert=TW_MAX,
    ),
    Vorschlag(
        "Ruhepuls",
        MESSWERT,
        gruppe=MESSWERTE,
        teile=(Teil("Ruhepuls", "bpm", 20, 250),),
        tageswert=TW_MIN,
        standard_key="ruhepuls",
        fest=True,
    ),
    Vorschlag("Trinken", MENGE, mehrmals=True, einheit="ml", schnell=(250, 500), gruppe=EINNAHMEN),
    Vorschlag("Medikament", ANZAHL, mehrmals=True, schnell=(1,), gruppe=EINNAHMEN),
    Vorschlag("Kaffee", ANZAHL, mehrmals=True, schnell=(1,), gruppe=EINNAHMEN),
    Vorschlag("Schlaf", DAUER, gruppe=ALLTAG),
    Vorschlag("Spazieren", DAUER, mehrmals=True, schnell=(900, 1800), gruppe=ALLTAG),
    Vorschlag("Meditation", DAUER, mehrmals=True, schnell=(600,), gruppe=ALLTAG),
    Vorschlag("Ernährung", TEXT, gruppe=ALLTAG),
    Vorschlag(
        "Störung",
        JA_NEIN,
        mehrmals=True,
        varianten=STOERUNG_VARIANTEN,
        gruppe=ALLTAG,
        standard_key="stoerung",
        fest=True,
    ),
)
#: Bisheriger Name — die Tests und das Formular kennen ihn
VORSCHLAEGE: Final[tuple[Vorschlag, ...]] = VORLAGEN
#: Standardfelder: in jedem Profil angelegt (ausgeschaltet, Ben 28.10.2026); seit 29.10.2026
#: **fest** — nicht löschbar, nur ausschaltbar (`Vorschlag.fest`)
STANDARDFELDER: Final[tuple[Vorschlag, ...]] = tuple(v for v in VORLAGEN if v.standard_key)
#: Schlüssel der festen Felder, mit denen die Herzfrequenz-Messung spricht
STANDARD_RUHEPULS: Final[str] = "ruhepuls"
STANDARD_SRPE: Final[str] = "srpe"
STANDARD_STOERUNG: Final[str] = "stoerung"


def standardfeld(felder: Iterable[Tagesfeld], key: str) -> Tagesfeld | None:
    """Das (nicht gelöschte) Standardfeld eines Profils mit diesem Schlüssel."""
    return next((f for f in felder if f.standard_key == key and f.deleted_at is None), None)


def vorlagen_in_gruppen(suche: str = "") -> list[tuple[str, list[Vorschlag]]]:
    """Die Vorlagen je Gruppe, gefiltert nach ``suche`` (ohne Suche alle); leere Gruppen fehlen.

    >>> [(g, [v.name for v in liste]) for g, liste in vorlagen_in_gruppen("blut")]
    [('Messwerte', ['Blutdruck', 'Blutzucker'])]
    """
    s = suche.strip().casefold()
    out: list[tuple[str, list[Vorschlag]]] = []
    for g in GRUPPEN:
        liste = [v for v in VORLAGEN if v.gruppe == g and (not s or s in v.name.casefold())]
        if liste:
            out.append((g, liste))
    return out


def standardfelder_fehlend(vorhandene: Iterable[Tagesfeld]) -> list[Vorschlag]:
    """Welche Standardfelder ein Profil noch nicht hat — gelöschte zählen als vorhanden
    (der Start legt sie nicht wieder an; „Wiederherstellen“ ist Sache der Einstellungen).

    >>> [v.name for v in standardfelder_fehlend([])]
    ['Anstrengung (sRPE)', 'Blutdruck', 'Gewicht', 'Ruhepuls', 'Störung']
    >>> [v.name for v in standardfelder_fehlend([Tagesfeld(standard_key="ruhepuls")])]
    ['Anstrengung (sRPE)', 'Blutdruck', 'Gewicht', 'Störung']
    """
    da = {f.standard_key for f in vorhandene if f.standard_key}
    return [v for v in STANDARDFELDER if v.standard_key not in da]


def vorgabe_mehrmals(art: str) -> bool:
    """Wie oft als Vorgabe einer Art: Anzahl, Menge, Dauer mehrmals, sonst einmal."""
    return art in SUMMIERT


def mit_art(spec: ResultSpec, art: str) -> ResultSpec:
    """Dieselben Varianten, eine andere Art (im Formular, solange es keine Werte gibt)."""
    return spec_bauen(art, varianten=var.varianten(spec), schnell=_vorgabe_schnell(art))


def mit_teilen(spec: ResultSpec, teile: Sequence[Teil]) -> ResultSpec:
    """Dieselben Varianten, andere Teile (Messwert im Formular).

    >>> s = spec_bauen(MESSWERT, teile=[Teil("a")], varianten=["links"])
    >>> [f.key for f in mit_teilen(s, [Teil("a"), Teil("b")]).fields]
    ['variant', 'value', 'value_2']
    """
    return var.mit_varianten(spec_bauen(MESSWERT, teile=teile), var.varianten(spec))


def _vorgabe_schnell(art: str) -> tuple[float, ...]:
    return {ANZAHL: (1,), MENGE: (250,), DAUER: (600,)}.get(art, ())


def mit_angaben(
    spec: ResultSpec,
    *,
    von: float | None = None,
    bis: float | None = None,
    einheit: str | None = None,
    schnell: Sequence[float] | None = None,
) -> ResultSpec:
    """Die Spezifikation mit geänderten Angaben der Art (Bereich, Einheit, Schnellknöpfe)."""
    f = wertfeld(spec)
    if f is None:
        return spec
    neu = replace(f, quick=list(f.quick), optionen=dict(f.optionen))
    if von is not None:
        neu.min = _als_zahl(von)
    if bis is not None:
        neu.max = _als_zahl(bis)
    if einheit is not None and f.type != FieldType.DURATION:
        neu.unit = einheit.strip() or None
    if schnell is not None:
        neu.quick = [_als_zahl(q) for q in schnell if q > 0][:SCHNELL_MAX]
    return replace(spec, fields=[neu if x.key == WERT else x for x in spec.fields])


def bereich_pruefen(von_text: str, bis_text: str) -> tuple[float, float]:
    """Der Bereich einer Skala aus zwei Feldern — ``ValueError`` mit Grund.

    >>> bereich_pruefen("0", "10"), bereich_pruefen("1", "5")
    ((0.0, 10.0), (1.0, 5.0))
    >>> bereich_pruefen("5", "5")
    Traceback (most recent call last):
    ValueError: „bis“ muss größer sein als „von“.
    """
    try:
        lo = float(von_text.strip().replace(",", "."))
        hi = float(bis_text.strip().replace(",", "."))
    except ValueError:
        raise ValueError("Zahlen für „von“ und „bis“?") from None
    if not (math.isfinite(lo) and math.isfinite(hi)):
        raise ValueError("Zahlen für „von“ und „bis“?")
    if hi <= lo:
        raise ValueError("„bis“ muss größer sein als „von“.")
    if hi - lo > 1000:
        raise ValueError("Höchstens 1000 Stufen.")
    return lo, hi


def ohne_geloeschte(felder: Iterable[Tagesfeld]) -> list[Tagesfeld]:
    return [f for f in felder if f.deleted_at is None]


def namen(felder: Iterable[Tagesfeld]) -> Mapping[str, str]:
    return {f.id: f.name for f in felder}


__all__ = [
    "ANZAHL",
    "ARTEN",
    "BLUTDRUCK_TEILE",
    "DAUER",
    "GRUPPEN",
    "JA_NEIN",
    "MENGE",
    "MESSWERT",
    "SKALA",
    "STANDARDFELDER",
    "SUMMIERT",
    "TAGESWERT_NAMEN",
    "TEILE_MAX",
    "TEIL_KEYS",
    "TEXT",
    "VORLAGEN",
    "VORSCHLAEGE",
    "WERT",
    "ZAHLEN",
    "Kurve",
    "Stand",
    "Summe",
    "Tagesfeld",
    "Tageswert",
    "Teil",
    "Vorschlag",
    "als_eintraege",
    "art_text",
    "art_von",
    "bereich_pruefen",
    "dauer_lesen",
    "dauer_text",
    "eingabe_text",
    "einmal_ziel",
    "eintrag_text",
    "ergebnis",
    "menge_text",
    "mit_angaben",
    "mit_art",
    "mit_varianten",
    "name_pruefen",
    "plus",
    "schnell_text",
    "schnellwerte",
    "skala_runden",
    "spec_bauen",
    "stand_text",
    "summe_text",
    "summen",
    "tageskurve",
    "tagesstand",
    "tageszeile",
    "uhrzeit_vorlage",
    "vorgabe_mehrmals",
    "wert_lesen",
    "wert_text",
    "wertfeld",
    "zeitpunkt",
]
