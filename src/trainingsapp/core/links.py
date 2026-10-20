"""Welche Links die App öffnen darf (Sicherheitsdurchsicht S1, Ben, 20.10.2026).

Links kommen aus Paketen, aus Kapiteltexten (Markdown) und aus der Datenbank —
also von Fremden. `launch_url` reichte bisher jedes Schema an das System weiter:
``intent://`` startet auf Android fremde Apps mit Parametern, ``tel:``/``sms:``
wählen, ``file://`` und am Rechner alles, was der Desktop verknüpft. Darum gilt
zweifach — beim Paketimport **und** vor jedem Öffnen — dieselbe Regel: nur
``https://`` mit Host und ``mailto:``. Kein ``http://``, weil die App sonst
unverschlüsselt hinausgeht, obwohl sie es nirgends sonst tut.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

from typing import Final

#: Länger ist keine Adresse, die jemand gemeint hat (wie `paketquelle.url_pruefen`)
MAX_LAENGE: Final[int] = 2000


def erlaubt(url: str) -> bool:
    """Darf die App ``url`` öffnen? Nur ``https://<host>…`` und ``mailto:…``.

    Das Schema darf groß oder klein stehen; Leerzeichen und Steuerzeichen
    irgendwo in der Adresse machen sie ungültig, ``https`` braucht einen Host.

    >>> erlaubt("https://example.org/video?x=1#t")
    True
    >>> erlaubt("HTTPS://Example.org"), erlaubt("mailto:praxis@example.org")
    (True, True)
    >>> erlaubt("http://example.org"), erlaubt("intent://scan/#Intent;end")
    (False, False)
    >>> erlaubt("https://"), erlaubt("https:///pfad"), erlaubt("mailto:")
    (False, False, False)
    >>> erlaubt("https://example.org/a b"), erlaubt("https://example.org/\\x00")
    (False, False)
    >>> erlaubt(""), erlaubt("tel:+49"), erlaubt("file:///etc/passwd")
    (False, False, False)
    """
    if not url or len(url) > MAX_LAENGE:
        return False
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
        return False
    schema, doppelpunkt, rest = url.partition(":")
    if not doppelpunkt:
        return False
    schema = schema.lower()
    if schema == "mailto":
        return bool(rest)
    if schema != "https" or not rest.startswith("//"):
        return False
    host = rest[2:]
    for trenner in "/?#":
        host = host.split(trenner, 1)[0]
    return bool(host)


__all__ = ["MAX_LAENGE", "erlaubt"]
