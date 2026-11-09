"""Private Pakete — verschlüsselt, mit Code (U7, Ben 9.11.2026, F9; `docs/plan_paketinhalte.md`
§11).

„Ich möchte für User Pakete bereithalten, die nur diese Person betreffen … vor allem gegen Bots
und andere absichern.“ Zwei Schlösser: Der **Link** liegt in einem Ordner mit langem
Zufallsnamen (nicht zu erraten, nicht im öffentlichen Index), die **Datei** ist mit einem
**Code** verschlüsselt — 8 Zeichen ohne Verwechsler (`K7QM-9XA2`), getrennt vom Link
weitergegeben. Der Server prüft nichts; wer die Datei ohne Code hat, sieht Zeichensalat.

Mit Bordmitteln von Python, ohne neues Paket in der App:

- **Schlüssel:** scrypt(Code, Salz; N = 2¹⁵, r = 8, p = 1) → 64 Bytes: 32 zum Verschlüsseln, 32
  für die Prüfsumme. scrypt braucht Speicher — Durchprobieren mit Grafikkarten lohnt nicht.
- **Verschlüsseln:** je MiB ein Schlüsselstrom aus SHAKE-256(Schlüssel ‖ Salz ‖ Blocknummer),
  mit der Datei XOR-verknüpft (wie ein Zähler-Modus).
- **Echtheit:** HMAC-SHA256 über Kopf und Geheimtext — falscher Code oder verfälschte Datei
  fallen auf, bevor etwas gelesen wird (`CodeFalsch`).

Aufbau: ``TAPRIV`` · Version (1) · Verfahren (1 = scrypt) · log₂N · r · p · Salz (16) ·
Geheimtext · HMAC (32). Gilt für JSON- und ZIP-Pakete gleichermaßen.

Grenze: Wer die Datei hat und gezielt Rechenzeit einsetzt, braucht für 8 Zeichen (32⁸ ≈ 10¹²
Möglichkeiten, je Versuch ein scrypt) Jahre — ein Bot tut das nicht.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, Final

#: So beginnt jede private Paketdatei
MAGIC: Final = b"TAPRIV"
VERSION: Final = 1
SCRYPT: Final = 1
#: scrypt: N = 2^15, r = 8, p = 1 — gut 30 MiB Speicher, rund 0,1–0,5 s je Versuch
_LOG2N, _R, _P = 15, 8, 1
_SALZ: Final = 16
_KOPF: Final = len(MAGIC) + 5 + _SALZ
_TAG: Final = 32
_BLOCK: Final = 1 << 20
#: Die Zeichen eines Codes — ohne 0/O und 1/I, nur Großbuchstaben
ALPHABET: Final = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LAENGE: Final = 8


class CodeFalsch(Exception):
    """Der Code passt nicht — oder die Datei ist verfälscht (beides sieht gleich aus)."""


class PrivatNichtMoeglich(Exception):
    """Diesem Python fehlt scrypt — private Pakete gehen hier nicht."""


def moeglich() -> bool:
    """Kann diese Python-Umgebung private Pakete öffnen (scrypt aus OpenSSL)?"""
    return hasattr(hashlib, "scrypt")


def ist_privat(kopf: bytes) -> bool:
    """Beginnt die Datei wie ein privates Paket?

    >>> ist_privat(b"TAPRIV\\x01\\x01..."), ist_privat(b'{"paket": 1}')
    (True, False)
    """
    return kopf.startswith(MAGIC)


def code_neu() -> str:
    """Ein neuer Code — 8 Zeichen aus `ALPHABET` (32⁸ ≈ 10¹² Möglichkeiten).

    >>> c = code_neu(); len(c), set(c) <= set(ALPHABET)
    (8, True)
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LAENGE))


def code_normieren(text: str) -> str | None:
    """Wie getippt — groß, ohne Leer- und Bindestriche; ``None``, wenn es kein Code sein kann.

    >>> code_normieren("k7qm-9xa2"), code_normieren(" K7QM 9XA2 "), code_normieren("K7QM-9XA0")
    ('K7QM9XA2', 'K7QM9XA2', None)
    """
    roh = "".join(z for z in text.upper() if z not in " -\t")
    if not 6 <= len(roh) <= 16 or any(z not in ALPHABET for z in roh):
        return None
    return roh


def code_text(code: str) -> str:
    """Zum Lesen in Vierergruppen: „K7QM-9XA2“.

    >>> code_text("K7QM9XA2")
    'K7QM-9XA2'
    """
    return "-".join(code[i : i + 4] for i in range(0, len(code), 4))


def ordner_neu() -> str:
    """Ein Ordnername für den Link — 22 Zeichen, rund 130 Bit: nicht zu erraten.

    >>> len(ordner_neu())
    22
    """
    return secrets.token_urlsafe(16)


def _schluessel(code: str, salz: bytes, log2n: int, r: int, p: int) -> tuple[bytes, bytes]:
    if not moeglich():
        raise PrivatNichtMoeglich("Dieses Gerät kann private Pakete nicht öffnen (scrypt fehlt).")
    if not (10 <= log2n <= 20 and 1 <= r <= 16 and 1 <= p <= 4):
        raise CodeFalsch("unbekannte Schlüsselparameter")
    roh = hashlib.scrypt(
        code.encode("utf-8"),
        salt=salz,
        n=2**log2n,
        r=r,
        p=p,
        maxmem=256 * 1024 * 1024,
        dklen=64,
    )
    return roh[:32], roh[32:]


def _strom(schluessel: bytes, salz: bytes, nummer: int, laenge: int) -> bytes:
    return hashlib.shake_256(schluessel + salz + nummer.to_bytes(8, "big")).digest(laenge)


def _xor(a: bytes, b: bytes) -> bytes:
    return (int.from_bytes(a, "little") ^ int.from_bytes(b, "little")).to_bytes(len(a), "little")


def _bloecke(f: BinaryIO, laenge: int) -> Iterator[bytes]:
    rest = laenge
    while rest > 0:
        block = f.read(min(_BLOCK, rest))
        if not block:
            raise CodeFalsch("Datei zu kurz")
        rest -= len(block)
        yield block


def verschluesseln(daten: bytes, code: str) -> bytes:
    """Die Paketdatei verschlüsselt — mit frischem Salz (zweimal verschlüsselt sieht anders aus).

    >>> geheim = verschluesseln(b'{"paket": {"name": "P"}}', "K7QM9XA2")
    >>> ist_privat(geheim), b"paket" in geheim, entschluesseln(geheim, "K7QM9XA2")[:9]
    (True, False, b'{"paket":')
    >>> try:
    ...     entschluesseln(geheim, "K7QM9XA3")
    ... except CodeFalsch:
    ...     print("falsch")
    falsch
    """
    salz = secrets.token_bytes(_SALZ)
    kopf = MAGIC + bytes([VERSION, SCRYPT, _LOG2N, _R, _P]) + salz
    k_enc, k_mac = _schluessel(code, salz, _LOG2N, _R, _P)
    teile = [
        _xor(daten[i : i + _BLOCK], _strom(k_enc, salz, n, len(daten[i : i + _BLOCK])))
        for n, i in enumerate(range(0, len(daten), _BLOCK))
    ]
    geheim = b"".join(teile)
    return kopf + geheim + hmac.new(k_mac, kopf + geheim, hashlib.sha256).digest()


def _kopf_lesen(kopf: bytes) -> tuple[bytes, int, int, int]:
    if len(kopf) < _KOPF or not ist_privat(kopf):
        raise CodeFalsch("kein privates Paket")
    version, verfahren, log2n, r, p = kopf[len(MAGIC) : len(MAGIC) + 5]
    if version != VERSION or verfahren != SCRYPT:
        raise CodeFalsch("das private Paket ist neuer als diese App")
    return kopf[len(MAGIC) + 5 : _KOPF], log2n, r, p


def entschluesseln(daten: bytes, code: str) -> bytes:
    """Die Paketdatei im Klartext — wirft `CodeFalsch`."""
    if len(daten) < _KOPF + _TAG:
        raise CodeFalsch("Datei zu kurz")
    kopf, geheim, tag = daten[:_KOPF], daten[_KOPF:-_TAG], daten[-_TAG:]
    salz, log2n, r, p = _kopf_lesen(kopf)
    k_enc, k_mac = _schluessel(code, salz, log2n, r, p)
    if not hmac.compare_digest(hmac.new(k_mac, kopf + geheim, hashlib.sha256).digest(), tag):
        raise CodeFalsch("Der Code passt nicht.")
    return b"".join(
        _xor(geheim[i : i + _BLOCK], _strom(k_enc, salz, n, len(geheim[i : i + _BLOCK])))
        for n, i in enumerate(range(0, len(geheim), _BLOCK))
    )


def datei_verschluesseln(quelle: Path, ziel: Path, code: str) -> None:
    """Wie `verschluesseln`, für große Dateien (ZIP mit Videos) — Block für Block."""
    salz = secrets.token_bytes(_SALZ)
    kopf = MAGIC + bytes([VERSION, SCRYPT, _LOG2N, _R, _P]) + salz
    k_enc, k_mac = _schluessel(code, salz, _LOG2N, _R, _P)
    mac = hmac.new(k_mac, kopf, hashlib.sha256)
    try:
        with quelle.open("rb") as ein, ziel.open("wb") as aus:
            aus.write(kopf)
            for n, block in enumerate(_bloecke(ein, quelle.stat().st_size)):
                geheim = _xor(block, _strom(k_enc, salz, n, len(block)))
                mac.update(geheim)
                aus.write(geheim)
            aus.write(mac.digest())
    except BaseException:
        ziel.unlink(missing_ok=True)
        raise


def datei_entschluesseln(quelle: Path, ziel: Path, code: str) -> None:
    """Wie `entschluesseln`, Block für Block: erst die Echtheit (ein Durchgang), dann der
    Klartext nach ``ziel`` — bei `CodeFalsch` bleibt kein ``ziel``."""
    groesse = quelle.stat().st_size
    if groesse < _KOPF + _TAG:
        raise CodeFalsch("Datei zu kurz")
    laenge = groesse - _KOPF - _TAG
    with quelle.open("rb") as ein:
        kopf = ein.read(_KOPF)
        salz, log2n, r, p = _kopf_lesen(kopf)
        k_enc, k_mac = _schluessel(code, salz, log2n, r, p)
        mac = hmac.new(k_mac, kopf, hashlib.sha256)
        for block in _bloecke(ein, laenge):
            mac.update(block)
        if not hmac.compare_digest(mac.digest(), ein.read(_TAG)):
            raise CodeFalsch("Der Code passt nicht.")
        ein.seek(_KOPF)
        try:
            with ziel.open("wb") as aus:
                for n, block in enumerate(_bloecke(ein, laenge)):
                    aus.write(_xor(block, _strom(k_enc, salz, n, len(block))))
        except BaseException:
            ziel.unlink(missing_ok=True)
            raise


__all__ = [
    "ALPHABET",
    "CODE_LAENGE",
    "MAGIC",
    "CodeFalsch",
    "PrivatNichtMoeglich",
    "code_neu",
    "code_normieren",
    "code_text",
    "datei_entschluesseln",
    "datei_verschluesseln",
    "entschluesseln",
    "ist_privat",
    "moeglich",
    "ordner_neu",
    "verschluesseln",
]
