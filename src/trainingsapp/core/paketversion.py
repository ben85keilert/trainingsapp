"""Paketversionen „X.Y.Z“ und wann ein Update von selbst kommt (Ben, 9.11.2026).

Ben: „Im Paketmanager/Update fehlt ein Button für ein automatisches Update der Pakete, wenn die
Version nur im 0.0.X-Bereich angehoben wurde.“ Dafür braucht eine Paketversion Stellen.

Gespeichert, verschickt und verglichen wird weiter **eine ganze Zahl** — X·10000 + Y·100 + Z
(Y und Z unter 100). So bleiben Datenbank (`package.version`), Paketdatei und Index, wie sie
sind, und ältere Apps vergleichen weiter richtig. Eine bisherige Version 4 ist 0.0.4. In einer
Quelle (TOML, JSON) darf „X.Y.Z“ stehen — gelesen wird es zur Zahl (`version_zahl`), angezeigt
wird „X.Y.Z“ (`version_text`). Vertrag: `docs/uebungspakete.md`.

Der Update-Modus je Paket (`Paket.update_modus`): **auto** — jedes Update beim Start
einspielen; **klein** — nur, wenn bloß die letzte Stelle steigt, größere merkt die App vor;
**manuell** — nur vormerken.
"""

from __future__ import annotations

import re
from typing import Any, Final

#: Y und Z bleiben darunter — sonst wäre die Zahl nicht mehr eindeutig
STELLE: Final = 100
#: Die Update-Modi in der Reihenfolge der Auswahl
AUTO, KLEIN, MANUELL = "auto", "klein", "manuell"
UPDATE_MODI: Final = (AUTO, KLEIN, MANUELL)
#: So heißen sie in der App
MODUS_TEXT: Final = {
    AUTO: "Alle automatisch",
    KLEIN: "Kleine automatisch",
    MANUELL: "Manuell",
}

_PUNKTE = re.compile(r"(\d{1,6})\.(\d{1,2})\.(\d{1,2})")


def version_zahl(wert: Any) -> int | None:
    """Die Version als Zahl — aus einer ganzen Zahl (wie bisher) oder „X.Y.Z“; ``None``, wenn
    sie unlesbar ist.

    >>> version_zahl(4), version_zahl("0.0.4"), version_zahl("1.2.3"), version_zahl(" 0.1.0 ")
    (4, 4, 10203, 100)
    >>> [version_zahl(w) for w in ("3", "2.1", "1.100.0", "1.2.3.4", "a", "", True, -1, 2.5)]
    [None, None, None, None, None, None, None, None, None]

    Text nur in der vollen Form „X.Y.Z“ — „3“ wäre sonst 3.0.0, die Zahl 3 aber 0.0.3.
    """
    if isinstance(wert, bool):
        return None
    if isinstance(wert, int):
        return wert if wert >= 0 else None
    if not isinstance(wert, str):
        return None
    treffer = _PUNKTE.fullmatch(wert.strip())
    if treffer is None:
        return None
    x, y, z = (int(t) for t in treffer.groups())
    return (x * STELLE + y) * STELLE + z


def version_teile(zahl: int) -> tuple[int, int, int]:
    """``(X, Y, Z)`` aus der Zahl.

    >>> version_teile(10203), version_teile(4)
    ((1, 2, 3), (0, 0, 4))
    """
    return zahl // (STELLE * STELLE), zahl // STELLE % STELLE, zahl % STELLE


def version_text(zahl: int | None) -> str:
    """„X.Y.Z“ zum Anzeigen — leer ohne Version.

    >>> version_text(4), version_text(10203), version_text(None)
    ('0.0.4', '1.2.3', '')
    """
    if zahl is None:
        return ""
    return ".".join(str(t) for t in version_teile(zahl))


def nur_klein(alt: int | None, neu: int | None) -> bool:
    """Steigt nur die letzte Stelle — 0.0.4 → 0.0.5, 1.2.3 → 1.2.9?

    >>> nur_klein(4, 5), nur_klein(10203, 10209)
    (True, True)
    >>> nur_klein(4, 100), nur_klein(10203, 10300), nur_klein(10203, 20000)
    (False, False, False)
    >>> nur_klein(None, 5), nur_klein(5, 5), nur_klein(5, 4)
    (False, False, False)
    """
    if alt is None or neu is None or neu <= alt:
        return False
    return version_teile(alt)[:2] == version_teile(neu)[:2]


def von_selbst(modus: str, alt: int | None, neu: int | None) -> bool:
    """Spielt die App dieses Update beim Prüfen von selbst ein? Sonst merkt sie es vor.

    >>> von_selbst(AUTO, 4, 100), von_selbst(KLEIN, 4, 5), von_selbst(KLEIN, 4, 100)
    (True, True, False)
    >>> von_selbst(MANUELL, 4, 5), von_selbst("unbekannt", 4, 5)
    (False, False)
    """
    if modus == AUTO:
        return True
    if modus == KLEIN:
        return nur_klein(alt, neu)
    return False


__all__ = [
    "AUTO",
    "KLEIN",
    "MANUELL",
    "MODUS_TEXT",
    "STELLE",
    "UPDATE_MODI",
    "nur_klein",
    "version_teile",
    "version_text",
    "version_zahl",
    "von_selbst",
]
