"""Rückgängig und Wiederholen für ein Textfeld — die Notiz zum Tag (Ben, 22.10.2026).

Ben: „Ermögliche direktes Eintragen mit Autosave und zurück und vor Button, falls man aus
Versehen was löscht.“ Flet reicht das Rückgängig von Flutter nicht heraus, darum führt die
App den Verlauf selbst: Jede Änderung des Felds kommt hier an (`Textverlauf.aendern`), ↶ und
↷ holen einen früheren bzw. späteren Stand.

**Schritte, nicht Tastendrücke:** Was man in einem Zug schreibt, ist ein Schritt — ein neuer
beginnt nach einer Pause (`PAUSE_S`) und beim Wechsel zwischen Schreiben und Löschen. Ein
Stück, das auf einmal verschwindet (markiert und gelöscht, ausgeschnitten), ist immer ein
Schritt für sich — genau das holt ↶ zurück. Ein Diktat, das einen halben Satz durch einen
anderen ersetzt, ist kein solches Stück: Dort kommt zugleich etwas dazu.

Hier steht nur die Rechnung (flet-frei); das Feld, das Speichern und die Knöpfe macht
`ui/components/tagesnotiz.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Nach so vielen Sekunden ohne Änderung beginnt ein neuer Schritt
PAUSE_S = 1.5
#: So viele Schritte merkt sich der Verlauf
TIEFE = 100


def entfernt(alt: str, neu: str) -> int:
    """Wie viele Zeichen am Stück aus ``alt`` verschwanden, damit ``neu`` entstand — 0, wenn
    ``neu`` nicht so entstand (etwas kam dazu, oder es fehlt an zwei Stellen).

    >>> entfernt("Knie links fest", "Knie fest"), entfernt("abc", "ab")
    (6, 1)
    >>> entfernt("Knie links", "Knie rechts"), entfernt("ab", "abc"), entfernt("abcd", "bc")
    (0, 0, 0)
    """
    if len(neu) >= len(alt):
        return 0
    vorn = 0
    while vorn < len(neu) and alt[vorn] == neu[vorn]:
        vorn += 1
    rest = len(neu) - vorn
    return len(alt) - len(neu) if alt[len(alt) - rest :] == neu[vorn:] else 0


def stelle(alt: str, neu: str) -> int:
    """Wohin die Schreibmarke gehört, nachdem ``alt`` zu ``neu`` wurde: ans Ende dessen, was
    sich in ``neu`` unterscheidet — nach ↶ steht sie da, wo das Zurückgeholte endet.

    >>> stelle("Knie fest", "Knie links fest"), stelle("Knie links fest", "Knie fest")
    (11, 5)
    >>> stelle("", "alles"), stelle("gleich", "gleich")
    (5, 6)
    """
    vorn = 0
    kuerzer = min(len(alt), len(neu))
    while vorn < kuerzer and alt[vorn] == neu[vorn]:
        vorn += 1
    hinten = 0
    while hinten < kuerzer - vorn and alt[-1 - hinten] == neu[-1 - hinten]:
        hinten += 1
    return len(neu) - hinten


@dataclass
class Textverlauf:
    """Die Stände eines Textfelds — der jetzige (`text`), frühere und spätere.

    >>> v = Textverlauf("Knie")
    >>> for i, t in enumerate(["Knie ", "Knie l", "Knie li", "Knie links"]):
    ...     _ = v.aendern(t, zeit=i * 0.3)  # in einem Zug geschrieben
    >>> v.rueckgaengig(), v.kann_rueckgaengig
    ('Knie', False)
    >>> v.wiederholen(), v.kann_wiederholen
    ('Knie links', False)

    Ein markiertes und gelöschtes Stück ist ein Schritt für sich, auch mitten im Schreiben:

    >>> v = Textverlauf("")
    >>> _ = v.aendern("Schulter fest, Knie gut", zeit=0)
    >>> _ = v.aendern("Schulter fest", zeit=0.5)
    >>> _ = v.aendern("Schulter fest.", zeit=0.8)
    >>> v.rueckgaengig(), v.rueckgaengig(), v.rueckgaengig()
    ('Schulter fest', 'Schulter fest, Knie gut', '')

    Nach einer Pause oder beim Wechsel von Schreiben zu Löschen beginnt ein neuer Schritt;
    wer nach ↶ weiterschreibt, verliert das ↷:

    >>> v = Textverlauf("")
    >>> [v.aendern(t, zeit) for t, zeit in [("a", 0), ("ab", 1), ("abc", 5), ("ab", 5.2)]]
    [True, False, True, True]
    >>> v.rueckgaengig(), v.kann_wiederholen
    ('abc', True)
    >>> _ = v.aendern("abcd", zeit=6)
    >>> v.kann_wiederholen, v.aendern("abcd", zeit=7)  # nichts geändert
    (False, False)
    """

    text: str = ""
    _zurueck: list[str] = field(default_factory=list)
    _vor: list[str] = field(default_factory=list)
    #: Art des offenen Schritts — ``+`` schreiben, ``-`` löschen, ``~`` ersetzen; ``None``:
    #: keiner offen, die nächste Änderung beginnt einen
    _art: str | None = None
    _zeit: float = 0.0

    @property
    def kann_rueckgaengig(self) -> bool:
        return bool(self._zurueck)

    @property
    def kann_wiederholen(self) -> bool:
        return bool(self._vor)

    def aendern(self, neu: str, zeit: float) -> bool:
        """Eine Änderung aus dem Feld (``zeit`` in Sekunden, etwa `time.monotonic`) —
        ``True``, wenn sie einen neuen Schritt begann."""
        if neu == self.text:
            return False
        if len(neu) > len(self.text):
            art = "+"
        elif len(neu) < len(self.text):
            art = "-"
        else:
            art = "~"
        stueck = entfernt(self.text, neu) > 1
        beginnt = self._art is None or art != self._art or zeit - self._zeit > PAUSE_S or stueck
        if beginnt:
            self._zurueck.append(self.text)
            del self._zurueck[:-TIEFE]
        self._vor.clear()
        self.text = neu
        # Nach einem gelöschten Stück beginnt das Weiterschreiben einen eigenen Schritt
        self._art = None if stueck else art
        self._zeit = zeit
        return beginnt

    def schritt_beenden(self) -> None:
        """Den offenen Schritt schließen — was danach kommt, ist ein neuer (etwa nach ↶)."""
        self._art = None

    def rueckgaengig(self) -> str | None:
        """Der Stand vor dem letzten Schritt — ``None``, wenn es keinen gibt."""
        if not self._zurueck:
            return None
        self._vor.append(self.text)
        self.text = self._zurueck.pop()
        self._art = None
        return self.text

    def wiederholen(self) -> str | None:
        """Den zuletzt zurückgenommenen Schritt wieder — ``None``, wenn es keinen gibt."""
        if not self._vor:
            return None
        self._zurueck.append(self.text)
        self.text = self._vor.pop()
        self._art = None
        return self.text

    def neu_beginnen(self, text: str) -> None:
        """Ohne Verlauf von vorn — mit ``text`` als jetzigem Stand."""
        self.text = text
        self._zurueck.clear()
        self._vor.clear()
        self._art = None


__all__ = ["PAUSE_S", "TIEFE", "Textverlauf", "entfernt", "stelle"]
