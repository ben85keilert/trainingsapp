"""**Deine Werte** — was die Person im Kurs gemacht und geantwortet hat (Ben, 23.11.2026,
`docs/plan_kurs_uebungen.md` §5).

Ein Lauf im Kurs hinterlässt alles, was eingegeben wurde, als Variablen (`course_variable`,
Migration 065/074): den Wert des Tests unter seinem Namen (`core.kursbloecke.wert_schluessel`),
jedes Feld des Eintrags unter ``<test>.<feld>``, jede Antwort unter ``<test>.f:<frage>``
(`core.kursbloecke.antwort_name`) — und
die Antwort auf eine Frage im Kapitel unter der Block-ID der Frage. Hier wird daraus die Karte
der Kursseite: je Kapitel die Läufe und Antworten, **nur Zahlen und eigene Worte, keine
Wertung**. Der Tipp auf einen Lauf führt zu seinem Tag.

Dieses Modul kennt kein flet und keine Datenbank; gerechnet wird nur aus Einträgen und
Selbstauskunft, nie aus Messwerten (`docs/recht/00_zweckbestimmung.md`).
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from . import ablauf as ab
from .kursbloecke import FRAGE, FRAGE_VORSATZ, TEST, Block, antwort_name, feld_schluessel
from .kurse import Kurs, Kursvariable
from .models import Exercise
from .result_spec import FieldSpec, basis_key, vorrat_feld, wert_text
from .tagesbilanz import menge_text


@dataclass(frozen=True, slots=True)
class Wertzeile:
    """Eine Zeile der Karte: ein Lauf mit seinen Werten oder eine Antwort."""

    titel: str
    text: str
    #: der Eintrag des Laufs — ``None`` bei einer Antwort oder wenn es ihn nicht mehr gibt
    eintrag_id: str | None = None
    gesetzt: datetime | None = None
    block_id: str = ""
    antwort: bool = False


@dataclass(slots=True)
class Wertgruppe:
    """Die Zeilen eines Kapitels — ``kapitel``: „1. Die Planke“."""

    kapitel: str
    zeilen: list[Wertzeile] = field(default_factory=list)


def antwort_text(variable: Kursvariable, skala: bool = False) -> str:
    """Eine gespeicherte Antwort, lesbar: der Text, mehrere mit „·“, Ja/Nein, eine Skala als
    Zahl.

    >>> antwort_text(Kursvariable("f", 0.0, text="leicht"))
    'leicht'
    >>> antwort_text(Kursvariable("f", 0.0, text='["Knie", "Schulter"]'))
    'Knie · Schulter'
    >>> antwort_text(Kursvariable("f", 1.0)), antwort_text(Kursvariable("f", 0.0))
    ('Ja', 'Nein')
    >>> antwort_text(Kursvariable("f", 6.0), skala=True)
    '6'
    """
    if variable.text is not None:
        if variable.text.startswith("["):
            try:
                liste = json.loads(variable.text)
            except ValueError:
                liste = None
            if isinstance(liste, list):
                return " · ".join(str(a) for a in liste)
        return variable.text
    if skala:
        return f"{variable.wert:g}"
    return "Ja" if variable.wert else "Nein"


def _feld(uebung: Exercise | None, key: str) -> FieldSpec | None:
    if uebung is not None:
        for f in uebung.result_spec.fields:
            if f.key == key:
                return f
    return vorrat_feld(basis_key(key))


def _felder_text(
    name: str, variablen: Mapping[str, Kursvariable], uebung: Exercise | None
) -> list[str]:
    """Die Felder eines Laufs als „1:00 Haltezeit“, „Seite: links“ — in der Ordnung der
    Übung, Unbekanntes dahinter."""
    vorsatz = feld_schluessel(name, "")
    da = {
        n[len(vorsatz) :]: v
        for n, v in variablen.items()
        if n.startswith(vorsatz) and not n[len(vorsatz) :].startswith(FRAGE_VORSATZ)
    }
    ordnung = [f.key for f in uebung.result_spec.fields] if uebung is not None else []
    teile: list[str] = []
    for key in [k for k in ordnung if k in da] + sorted(k for k in da if k not in ordnung):
        feld, v = _feld(uebung, key), da[key]
        if feld is None:
            continue
        if v.text is not None:
            teile.append(f"{feld.label}: {v.text}")
        elif feld.unit == "s":
            teile.append(menge_text(feld, v.wert))
        else:
            teile.append(f"{feld.label}: {wert_text(feld, v.wert)}")
    return teile


def deine_werte(
    kurs: Kurs,
    variablen: Mapping[str, Kursvariable],
    uebungen: Mapping[str, Exercise],
    ziel_tests: Collection[str] = (),
) -> list[Wertgruppe]:
    """Je Kapitel, was die Person gemacht und geantwortet hat — Kapitel ohne Werte fehlen.
    ``ziel_tests``: die Tests, aus deren Wert ein Ziel wird (`wert_wird_ziel`) — sie heißen
    „Test …“, die anderen „… ausprobiert“. Schwebende Variablen (nur die Wahl des Werts für
    den Plan, Migration 066) zählen nicht: Dort ist noch nichts gemacht.

    >>> from trainingsapp.core.kurse import Kapitel
    >>> from trainingsapp.core.result_spec import ResultSpec
    >>> planke = Exercise(id="p", name="Planke", result_spec=ResultSpec(
    ...     fields=[vorrat_feld("hold"), vorrat_feld("scale")]))
    >>> kurs = Kurs(id="k", name="Rumpf", kapitel=[Kapitel(id="a", titel="Die Planke", bloecke=[
    ...     Block(TEST, id="t", uebung="p"), Block(TEST, id="e", uebung="p")])])
    >>> v = {n: Kursvariable(n, w) for n, w in
    ...      {"t": 60.0, "t.hold": 60.0, "t.scale": 7.0, "e": 31.0, "e.hold": 31.0}.items()}
    >>> v["t"] = Kursvariable("t", 60.0, wie="anteil", anteil=0.8, wahl_stempel="s")
    >>> (gruppe,) = deine_werte(kurs, v, {"p": planke}, ziel_tests={"t"})
    >>> gruppe.kapitel
    '1. Die Planke'
    >>> [(z.titel, z.text) for z in gruppe.zeilen]  # doctest: +NORMALIZE_WHITESPACE
    [('Test Planke', '1:00 Haltezeit · Skala 0–10: 7 · für den Plan: 48s Haltezeit (80 %)'),
     ('Planke ausprobiert', '31s Haltezeit')]
    >>> deine_werte(kurs, {}, {"p": planke})
    []
    """
    from .kurstest import wahl_text  # hier, weil `core.kurstest` schwer ist und selten gebraucht

    ergebnis: list[Wertgruppe] = []
    for nr, kapitel in enumerate(kurs.kapitel, start=1):
        gruppe = Wertgruppe(f"{nr}. {kapitel.titel}")
        for block in kapitel.bloecke:
            if block.art == TEST:
                gruppe.zeilen.extend(
                    _lauf_zeilen(block, variablen, uebungen, ziel_tests, wahl_text)
                )
            elif block.art == FRAGE and (v := variablen.get(block.id)) is not None:
                gruppe.zeilen.append(
                    Wertzeile(
                        block.titel,
                        antwort_text(v, block.frage is not None and block.frage.art == ab.F_SKALA),
                        gesetzt=v.gesetzt,
                        block_id=block.id,
                        antwort=True,
                    )
                )
        if gruppe.zeilen:
            ergebnis.append(gruppe)
    return ergebnis


def _lauf_zeilen(
    block: Block,
    variablen: Mapping[str, Kursvariable],
    uebungen: Mapping[str, Exercise],
    ziel_tests: Collection[str],
    wahl_text: object,
) -> list[Wertzeile]:
    zeilen: list[Wertzeile] = []
    namen = (
        [block.id]
        if not block.aus
        else sorted(
            n for n in variablen if n.startswith(f"{block.id}:") and "." not in n[len(block.id) :]
        )
    )
    for name in namen:
        v = variablen.get(name)
        if v is None or v.schwebt:
            continue
        uid = name.split(":", 1)[1] if block.aus else block.uebung
        uebung = uebungen.get(uid)
        wie = uebung.name if uebung is not None else "Übung"
        teile = _felder_text(name, variablen, uebung)
        feld = _feld(uebung, block.feld)
        if not teile and feld is not None:
            teile = [menge_text(feld, v.wert)]
        gewaehlt = v.planwert()
        if gewaehlt is not None and feld is not None and block.id in ziel_tests:
            teile.append(
                f"für den Plan: {menge_text(feld, gewaehlt.wert)} ({wahl_text(gewaehlt)})"  # type: ignore[operator]
            )
        zeilen.append(
            Wertzeile(
                f"Test {wie}" if block.id in ziel_tests else f"{wie} ausprobiert",
                " · ".join(teile),
                eintrag_id=v.eintrag_id,
                gesetzt=v.gesetzt,
                block_id=block.id,
            )
        )
        # die Antworten auf die Fragen am Lauf, in der Reihenfolge des Blocks
        for frage in block.fragen:
            a = variablen.get(antwort_name(name, frage.id))
            if a is not None:
                zeilen.append(
                    Wertzeile(
                        frage.text,
                        antwort_text(a, frage.art == ab.F_SKALA),
                        gesetzt=a.gesetzt,
                        block_id=block.id,
                        antwort=True,
                    )
                )
    return zeilen


__all__ = [
    "Wertgruppe",
    "Wertzeile",
    "antwort_text",
    "deine_werte",
]
