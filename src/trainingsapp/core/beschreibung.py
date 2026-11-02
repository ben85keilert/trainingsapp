"""Die Beschreibung einer Übung in Abschnitten (Ben, 2.11.2026, P108: „den Text als ‚Name‘ +
‚Inhalt‘ setzen. Dann steht direkt drunter z. B. die Beschreibung vom Paket, individueller Text
für einen Patienten, eigener Text vom Patienten usw. Nur die Reihenfolge ist wichtig“).

Gespeichert bleibt **ein Text** (`exercise.description`, Paketfeld ``description``): Ein
Abschnitt beginnt mit einer Zeile ``## Name``, darunter sein Inhalt; Text vor der ersten
Überschrift ist ein Abschnitt ohne Namen. So lesen Pakete, praxis_gui und ältere Stände den
Text weiter als Text, und der Drei-Wege-Abgleich der Pakete (`core/pakete.py`) sieht ein
Feld. Die Reihenfolge ist die Reihenfolge im Text.

>>> text = "Füße hüftbreit.\\n\\n## Worauf achten\\nFersen am Boden.\\n## Für Ben\\nlangsam"
>>> [(a.name, a.text) for a in abschnitte(text)]
[('', 'Füße hüftbreit.'), ('Worauf achten', 'Fersen am Boden.'), ('Für Ben', 'langsam')]
>>> zusammen(abschnitte(text)) == text.replace("\\n\\n## ", "\\n## ")
True
>>> abschnitte(""), zusammen([])
([], '')
>>> kurz(text)
'Füße hüftbreit.'
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

#: Eine Überschrift im Text: ``## Name``
_UEBERSCHRIFT = re.compile(r"^##\s+(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class Abschnitt:
    """Name (leer = ohne Überschrift) und Inhalt."""

    name: str = ""
    text: str = ""

    @property
    def leer(self) -> bool:
        return not self.name.strip() and not self.text.strip()


def abschnitte(text: str) -> list[Abschnitt]:
    """Den Text in Abschnitte lesen — ohne Überschrift ein einziger ohne Namen; leer → keine.

    >>> abschnitte("nur Text")
    [Abschnitt(name='', text='nur Text')]
    >>> abschnitte("## A\\n\\n## B\\nb")
    [Abschnitt(name='A', text=''), Abschnitt(name='B', text='b')]
    """
    ergebnis: list[Abschnitt] = []
    name = ""
    zeilen: list[str] = []

    def abschliessen() -> None:
        inhalt = "\n".join(zeilen).strip()
        if name or inhalt:
            ergebnis.append(Abschnitt(name, inhalt))

    for zeile in text.splitlines():
        m = _UEBERSCHRIFT.match(zeile)
        if m is not None:
            abschliessen()
            name, zeilen = m.group(1), []
        else:
            zeilen.append(zeile)
    abschliessen()
    return ergebnis


def zusammen(teile: Iterable[Abschnitt]) -> str:
    """Die Abschnitte als ein Text — leere fallen weg; ein Abschnitt ohne Namen steht nur
    ganz vorn ohne Überschrift, sonst bekommt er ``## `` ohne Namen nicht, sondern bleibt
    namenlos angehängt (er gehört dann zum vorigen).

    >>> zusammen([Abschnitt("", "a"), Abschnitt("B", "b")])
    'a\\n## B\\nb'
    >>> zusammen([Abschnitt("B", "b"), Abschnitt("", "c")])
    '## B\\nb\\nc'
    """
    zeilen: list[str] = []
    for a in teile:
        if a.leer:
            continue
        name, inhalt = a.name.strip(), a.text.strip()
        if name:
            zeilen.append(f"## {name}")
        if inhalt:
            zeilen.append(inhalt)
    return "\n".join(zeilen)


def kurz(text: str) -> str:
    """Der Inhalt des ersten Abschnitts — für eine Zeile ohne Überschriften."""
    teile = abschnitte(text)
    return teile[0].text if teile else ""


__all__ = ["Abschnitt", "abschnitte", "kurz", "zusammen"]
