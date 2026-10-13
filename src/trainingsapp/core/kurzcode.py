"""Kurzcodes für Übungen — 6 Zeichen statt einer 36-stelligen UUID.

Eine Notiz zur HRV-Messung, die Übungen nennt, trägt deren Kurzcodes im Feld
``uebungen`` (Vertrag: `docs/kompatibilitaet.md`, Abschnitt 4). Der Code ist
kein Schlüssel für sich: Die App löst ihn gegen den eigenen Katalog auf
(`katalog_aufloesen`). 30 Bit reichen dafür — bei 1 000 Übungen liegt die
Chance einer Doppelung unter 0,05 %.

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
#: Zeichen je Code (5 Bit je Zeichen → 30 Bit)
LAENGE: Final[int] = 6


def kurzcode(uebung_id: str) -> str:
    """Kurzcode einer Übungs-ID: SHA-1 der UUID (Kleinschrift), erste 30 Bit, Base32.

    >>> kurzcode("2B0C6F0E-0000-4000-8000-000000000001")
    '2ATPZC'
    >>> kurzcode("2b0c6f0e-0000-4000-8000-000000000001")  # Schreibweise egal
    '2ATPZC'
    >>> len(kurzcode("x")), set(kurzcode("y")) <= set(ALPHABET)
    (6, True)
    """
    digest = hashlib.sha1(uebung_id.strip().lower().encode("utf-8"), usedforsecurity=False)
    zahl = int.from_bytes(digest.digest()[:4], "big") >> 2  # die oberen 30 Bit
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

    >>> katalog_aufloesen(["2ATPZC", "XXXXXX"], ["2b0c6f0e-0000-4000-8000-000000000001"])
    ['2b0c6f0e-0000-4000-8000-000000000001']
    """
    nach_code: dict[str, str] = {}
    for uebung_id in ids:
        nach_code.setdefault(kurzcode(uebung_id), uebung_id)
    return [nach_code[c] for c in codes if c in nach_code]


__all__ = ["ALPHABET", "LAENGE", "genannte", "katalog_aufloesen", "kurzcode"]
