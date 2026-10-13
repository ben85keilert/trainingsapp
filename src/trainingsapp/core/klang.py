"""Signaltöne des Timers als WAV-Bytes — erzeugt, nicht als Dateien mitgeliefert.

Drei kurze Klänge mit weichem Ein- und Ausklingen (sonst knackt es) und einem
Hauch Oberton, damit sie auch aus kleinen Handylautsprechern hörbar sind:

- ``countdown``: ein kurzer Ton — 3, 2 und 1 s vor jedem Abschnittsende
- ``wechsel``: zwei Töne aufwärts — ein neuer Abschnitt beginnt
- ``ende``: vier Töne aufwärts, der letzte lang — geschafft

Erzeugt statt mitgeliefert: keine Asset-Dateien, die `flet run` und
`flet build` an verschiedenen Orten suchen, und die Klänge stehen als Zahlen
hier im Quelltext. Nur Standardbibliothek, kein Wissen über die Oberfläche.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from collections.abc import Sequence
from typing import Final

#: Abtastrate (Hz) — für Pieptöne genügt die halbe CD-Rate
RATE: Final[int] = 22050

#: Die Klänge: je Ton (Frequenz in Hz, Dauer in s)
TOENE: Final[dict[str, tuple[tuple[float, float], ...]]] = {
    "countdown": ((880.0, 0.12),),
    "wechsel": ((988.0, 0.13), (1319.0, 0.32)),
    "ende": ((784.0, 0.14), (988.0, 0.14), (1175.0, 0.14), (1568.0, 0.6)),
}

_EINBLENDEN_S = 0.005
_AUSBLENDEN_S = 0.012


def wav(folge: Sequence[tuple[float, float]], lautstaerke: float = 0.7) -> bytes:
    """Töne ``(Frequenz Hz, Dauer s)`` nacheinander als 16-bit-Mono-WAV.

    Jeder Ton klingt nach kurzem Einblenden ab und wird am Ende ausgeblendet —
    die Kurve endet bei null, der nächste Ton setzt ohne Knacken an.

    >>> daten = wav(((440.0, 0.1),))
    >>> daten[:4], daten[8:12], len(daten) - 44 == 2 * round(0.1 * RATE)
    (b'RIFF', b'WAVE', True)
    >>> proben = struct.unpack(f"<{(len(daten) - 44) // 2}h", daten[44:])
    >>> proben[0], proben[-1], max(abs(p) for p in proben) <= 0.7 * 32767
    (0, 0, True)
    """
    proben: list[int] = []
    voll = 32767 * min(max(lautstaerke, 0.0), 1.0)
    for frequenz, dauer in folge:
        n = max(round(dauer * RATE), 1)
        ein = max(round(_EINBLENDEN_S * RATE), 1)
        aus = max(round(_AUSBLENDEN_S * RATE), 1)
        for i in range(n):
            t = i / RATE
            huelle = min(i / ein, 1.0, (n - 1 - i) / aus) * math.exp(-2.5 * i / n)
            welle = math.sin(2 * math.pi * frequenz * t) + 0.25 * math.sin(
                4 * math.pi * frequenz * t
            )
            proben.append(round(voll * huelle * welle / 1.25))
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as datei:
        datei.setnchannels(1)
        datei.setsampwidth(2)
        datei.setframerate(RATE)
        datei.writeframes(struct.pack(f"<{len(proben)}h", *proben))
    return puffer.getvalue()


def toene() -> dict[str, bytes]:
    """Alle Klänge des Timers als WAV-Bytes.

    >>> sorted(toene())
    ['countdown', 'ende', 'wechsel']
    """
    return {name: wav(folge) for name, folge in TOENE.items()}


__all__ = ["RATE", "TOENE", "toene", "wav"]
