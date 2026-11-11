"""Paketversionen „X.Y.Z“ und wann ein Update von selbst kommt (Ben, 9.11.2026).

Ben: „Im Paketmanager/Update fehlt ein Button für ein automatisches Update der Pakete, wenn die
Version nur im 0.0.X-Bereich angehoben wurde.“ Dafür braucht eine Paketversion Stellen.

Gespeichert, verschickt und verglichen wird weiter **eine ganze Zahl** — X·10000 + Y·100 + Z
(Y und Z unter 100). So bleiben Datenbank (`package.version`), Paketdatei und Index, wie sie
sind, und ältere Apps vergleichen weiter richtig. Eine bisherige Version 4 ist 0.0.4. In einer
Quelle (TOML, JSON) darf „X.Y.Z“ stehen — gelesen wird es zur Zahl (`version_zahl`), angezeigt
wird „X.Y.Z“ (`version_text`). Vertrag: `docs/uebungspakete.md`.

Der Update-Modus je Paket (`Paket.update_modus`) — seit U6 (Ben 9.11.2026, F8 c) nach der
**Stufe aus dem Unterschied**, nicht nach der Nummer (`core.paketstufe.automatisch`): **auto**
(„Alle“) — kleine und mittlere Updates kommen beim Start von selbst, große fragen nach;
**klein** („Kleine“) — nur kleine; **manuell** — nur vormerken.
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


#: Größte Version als Zahl — „999999.99.99“; darüber ist sie unlesbar (K38: eine Zahl jenseits
#: von 64 Bit ließ sqlite beim Import werfen)
MAX_ZAHL = 999_999 * 100 * 100 + 99 * 100 + 99


def version_zahl(wert: Any) -> int | None:
    """Die Version als Zahl — aus einer ganzen Zahl (wie bisher) oder „X.Y.Z“; ``None``, wenn
    sie unlesbar ist.

    >>> version_zahl(4), version_zahl("0.0.4"), version_zahl("1.2.3"), version_zahl(" 0.1.0 ")
    (4, 4, 10203, 100)
    >>> [version_zahl(w) for w in ("3", "2.1", "1.100.0", "1.2.3.4", "a", "", True, -1, 2.5)]
    [None, None, None, None, None, None, None, None, None]
    >>> version_zahl(2**63), version_zahl("999999.99.99") == MAX_ZAHL
    (None, True)

    Text nur in der vollen Form „X.Y.Z“ — „3“ wäre sonst 3.0.0, die Zahl 3 aber 0.0.3.
    """
    if isinstance(wert, bool):
        return None
    if isinstance(wert, int):
        return wert if 0 <= wert <= MAX_ZAHL else None
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


__all__ = [
    "AUTO",
    "KLEIN",
    "MANUELL",
    "MODUS_TEXT",
    "STELLE",
    "UPDATE_MODI",
    "version_teile",
    "version_text",
    "version_zahl",
]
