"""Kurzcodes für Übungen — 8 Zeichen statt einer 36-stelligen UUID.

Eine Notiz zur HRV-Messung, die Übungen nennt, trägt deren Kurzcodes im Feld
``uebungen`` (Vertrag: `docs/kompatibilitaet.md`, Abschnitt 4). Der Code ist
kein Schlüssel für sich: Die App löst ihn gegen den eigenen Katalog auf
(`katalog_aufloesen`).

**Warum 8 Zeichen (40 Bit)?** Die Chance, dass zwei Übungen eines Katalogs
denselben Code haben, ist etwa ``n² / 2^(Bits+1)``:

==========  ==============  ================  =================
Übungen     6 Zeichen        **8 Zeichen**     10 Zeichen
==========  ==============  ================  =================
1 000       0,05 %           0,00005 %         ~0
10 000      4,5 %            0,005 %           0,000004 %
100 000     —                0,45 %            0,0004 %
==========  ==============  ================  =================

6 Zeichen (bis 14.10.2026) reichten für einen privaten Katalog, nicht für die
Praxis-Edition mit großen, geteilten Katalogen; 10 wären mehr als nötig.
Ältere 6-Zeichen-Codes sind die ersten 6 Zeichen des neuen Codes und werden
weiter aufgelöst.

Crockford-Base32 lässt I, L, O und U weg: nichts, was man verwechseln oder
falsch vorlesen könnte. Dieses Modul importiert nichts aus anderen Schichten.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from typing import Final

#: Crockford-Base32
ALPHABET: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
#: Zeichen je Code (5 Bit je Zeichen → 40 Bit)
LAENGE: Final[int] = 8
#: Länge der ersten Fassung (14.10.2026) — ein Präfix des heutigen Codes
LAENGE_ALT: Final[int] = 6


def kurzcode(uebung_id: str) -> str:
    """Kurzcode einer Übungs-ID: SHA-1 der UUID (Kleinschrift), erste 40 Bit, Base32.

    >>> kurzcode("2B0C6F0E-0000-4000-8000-000000000001")
    '2ATPZCAY'
    >>> kurzcode("2b0c6f0e-0000-4000-8000-000000000001")  # Schreibweise egal
    '2ATPZCAY'
    >>> len(kurzcode("x")), set(kurzcode("y")) <= set(ALPHABET)
    (8, True)
    """
    digest = hashlib.sha1(uebung_id.strip().lower().encode("utf-8"), usedforsecurity=False)
    zahl = int.from_bytes(digest.digest()[:5], "big")  # die oberen 40 Bit
    zeichen = []
    for _ in range(LAENGE):
        zeichen.append(ALPHABET[zahl & 31])
        zahl >>= 5
    return "".join(reversed(zeichen))


def genannte(text: str, katalog: Mapping[str, str]) -> list[str]:
    """Kurzcodes der Übungen, deren Namen im Text stehen — in der Reihenfolge im Text.

    ``katalog``: Name → Kurzcode. Nur ganze Namen zählen, ohne Rücksicht auf
    Groß- und Kleinschreibung; längere Namen gehen vor (wer „Kniebeuge
    einbeinig" schreibt, meint nicht auch „Kniebeuge").

    >>> k = {"Kniebeuge": "A", "Kniebeuge einbeinig": "B", "Planke": "C", "Rad": "D"}
    >>> genannte("Planke, danach Kniebeuge einbeinig", k)
    ['C', 'B']
    >>> genannte("Radfahren, kniebeuge, Kniebeuge", k)
    ['A']
    >>> genannte("", k)
    []
    """
    rest = text or ""
    treffer: list[tuple[int, str]] = []
    for name in sorted((n for n in katalog if n.strip()), key=len, reverse=True):
        muster = re.compile(rf"(?<!\w){re.escape(name.strip())}(?!\w)", re.IGNORECASE)
        for m in muster.finditer(rest):
            treffer.append((m.start(), katalog[name]))
        # Gefundenes überdecken — kürzere Namen finden darin nichts mehr
        rest = muster.sub(lambda m: "\0" * len(m.group(0)), rest)
    return list(dict.fromkeys(code for _, code in sorted(treffer)))


def katalog_aufloesen(codes: Iterable[str], ids: Iterable[str]) -> list[str]:
    """Übungs-IDs zu Kurzcodes — Unbekanntes fällt weg, bei Doppelung zählt die erste.

    Codes der ersten Fassung (6 Zeichen) sind der Anfang der heutigen und
    werden weiter erkannt.

    >>> ids = ["2b0c6f0e-0000-4000-8000-000000000001"]
    >>> katalog_aufloesen(["2ATPZCAY", "2ATPZC", "XXXXXXXX"], ids) == ids * 2
    True
    """
    nach_code: dict[str, str] = {}
    nach_alt: dict[str, str] = {}
    for uebung_id in ids:
        code = kurzcode(uebung_id)
        nach_code.setdefault(code, uebung_id)
        nach_alt.setdefault(code[:LAENGE_ALT], uebung_id)
    out = []
    for c in codes:
        treffer = nach_code.get(c) or (nach_alt.get(c) if len(c) == LAENGE_ALT else None)
        if treffer is not None:
            out.append(treffer)
    return out


__all__ = ["ALPHABET", "LAENGE", "LAENGE_ALT", "genannte", "katalog_aufloesen", "kurzcode"]
