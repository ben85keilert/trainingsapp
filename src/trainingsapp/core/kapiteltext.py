"""Kapiteltexte (Markdown) vor der Anzeige: Bilder aus dem Netz nur mit Einwilligung.

Flet rendert ``![…](https://…)`` sofort beim Öffnen des Kapitels — ohne Tipp und ohne
Hinweis erfährt der Server des Paketautors so IP-Adresse und Lesezeitpunkt, wie ein
Zählpixel in einer Mail (Sicherheitsdurchsicht 19.10.2026, S2). Ben, 20.10.2026:
ein Schalter wie in Mail-Programmen, Vorgabe aus. Solange er aus ist, macht
`bilder_zu_links` jedes Bild zu einem Link „[Bild: …](…)“, der erst auf Tipp öffnet —
und dann wie jeder Link nur mit ``https`` (`core.links`). Ist er an, bleibt der Text,
wie das Paket ihn liefert.

Später (Katalog): Bilder, die das Paket selbst mitbringt, brauchen keinen Schalter —
sie laden nichts aus dem Netz.
"""

from __future__ import annotations

import re

#: ``![alt](ziel)`` und ``![alt](ziel "Titel")`` — Inline-Bilder
_BILD = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<ziel>[^)]*)\)")
#: ``![alt][ref]`` — Bilder mit Referenz, die weiter unten im Text aufgelöst wird
_BILD_REF = re.compile(r"!\[(?P<alt>[^\]]*)\]\[(?P<ref>[^\]]*)\]")


def _etikett(alt: str) -> str:
    alt = alt.strip()
    return f"[Bild: {alt}]" if alt else "[Bild]"


def bilder_zu_links(text: str) -> str:
    """Jedes Markdown-Bild wird ein Link, der erst auf Tipp öffnet.

    >>> bilder_zu_links("Siehe ![Haltung](https://x/h.png) und Text")
    'Siehe [Bild: Haltung](https://x/h.png) und Text'
    >>> bilder_zu_links("![](https://x/p.png \\"Titel\\")")
    '[Bild](https://x/p.png "Titel")'
    >>> bilder_zu_links("![a][ref]\\n\\n[ref]: https://x/a.png")
    '[Bild: a][ref]\\n\\n[ref]: https://x/a.png'
    >>> bilder_zu_links("[Link](https://x) bleibt, Text mit ! bleibt")
    '[Link](https://x) bleibt, Text mit ! bleibt'

    Auch in Codeblöcken — ein ``![…](…)`` dort ist dann als Linktext zu lesen; das ist
    der Preis dafür, dass nichts von selbst lädt.
    """
    text = _BILD.sub(lambda m: f"{_etikett(m['alt'])}({m['ziel']})", text)
    return _BILD_REF.sub(lambda m: f"{_etikett(m['alt'])}[{m['ref']}]", text)
