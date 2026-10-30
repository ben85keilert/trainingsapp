"""Signaltöne des Timers als WAV-Bytes — erzeugt, nicht als Dateien mitgeliefert.

Drei kurze Klänge mit weichem Ein- und Ausklingen (sonst knackt es) und einem
Hauch Oberton, damit sie auch aus kleinen Handylautsprechern hörbar sind:

- ``countdown``: ein kurzer Ton — 3, 2 und 1 s vor jedem Abschnittsende
- ``wechsel``: zwei Töne aufwärts — ein neuer Abschnitt beginnt
- ``ende``: vier Töne aufwärts, der letzte lang — geschafft („Fanfare")

Dazu Klänge zur Wahl (Ben, 14.10.2026: „Glocke 1, 2, 3 für unterschiedliche
Bereiche"): drei Glocken (hell, mittel, tief), ein Gong und ein Klangholz.
Glocken sind keine reinen Töne — sie bestehen aus unharmonischen Teiltönen,
die verschieden schnell verklingen (`glocke`). Welcher Klang wann spielt,
entscheidet `core.timer.klang_fuer`.

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


#: Teiltöne einer Handglocke: (Verhältnis zum Grundton, Stärke, Abklingfaktor).
#: Unterton, Prim, kleine Terz, Quinte, Oktave und zwei höhere — die oberen
#: verklingen schneller, darum wird der Klang mit der Zeit dunkler.
GLOCKE: Final[tuple[tuple[float, float, float], ...]] = (
    (0.5, 0.35, 0.6),
    (1.0, 1.0, 1.0),
    (1.183, 0.55, 1.4),
    (1.506, 0.35, 1.8),
    (2.0, 0.6, 2.2),
    (2.514, 0.25, 3.0),
    (3.011, 0.18, 3.6),
)
#: Gong: eng beieinander liegende Teiltöne (Schwebung), langsam verklingend
GONG: Final[tuple[tuple[float, float, float], ...]] = (
    (1.0, 1.0, 1.0),
    (1.012, 0.7, 1.0),
    (1.48, 0.5, 1.5),
    (2.05, 0.45, 2.0),
    (2.69, 0.3, 2.6),
    (3.42, 0.2, 3.2),
)
#: Klangholz: zwei kurze, harte Teiltöne
HOLZ: Final[tuple[tuple[float, float, float], ...]] = ((1.0, 1.0, 1.0), (2.76, 0.5, 1.6))
#: Klangschale (Ben, 30.10.2026: „ein Klicken vielleicht Holzschale/Tempelklang, irgendwas
#: Nettes, was fast nicht auffällt“): weich angeschlagen, wenige Teiltöne, kurzer Nachklang
SCHALE: Final[tuple[tuple[float, float, float], ...]] = (
    (1.0, 1.0, 1.0),
    (2.71, 0.3, 1.9),
    (4.9, 0.08, 2.8),
)

#: Angeschlagene Klänge: Teiltöne, Grundton (Hz), Nachklang (s). Tiefer als
#: etwa 500 Hz geben Handylautsprecher wenig her — darum liegt Glocke 3 dort.
GLOCKEN: Final[dict[str, tuple[tuple[tuple[float, float, float], ...], float, float]]] = {
    "glocke1": (GLOCKE, 1046.5, 1.4),  # C6, hell
    "glocke2": (GLOCKE, 784.0, 1.7),  # G5
    "glocke3": (GLOCKE, 523.3, 2.0),  # C5, tief
    "gong": (GONG, 330.0, 2.4),
    "holz": (HOLZ, 1150.0, 0.18),
    "schale": (SCHALE, 660.0, 0.7),
}
#: Leiser als die übrigen (Spitze statt 0,7): der Hinweis an der HF-Grenze soll nebenbei
#: hörbar sein, nicht aufschrecken
LAUTSTAERKE: Final[dict[str, float]] = {"schale": 0.4}

#: Klänge zur Wahl, in der Reihenfolge der Auswahl — Schlüssel → Anzeigename.
#: ``wechsel`` (Piep) ist die Vorgabe; ``countdown`` steht nicht zur Wahl.
KLAENGE: Final[dict[str, str]] = {
    "wechsel": "Piep",
    "glocke1": "Glocke 1 · hell",
    "glocke2": "Glocke 2 · mittel",
    "glocke3": "Glocke 3 · tief",
    "gong": "Gong",
    "holz": "Klangholz",
    "schale": "Klangschale · leise",
    "ende": "Fanfare",
}


def glocke(
    teiltoene: Sequence[tuple[float, float, float]],
    grund_hz: float,
    dauer_s: float,
    lautstaerke: float = 0.7,
) -> bytes:
    """Ein angeschlagener Klang aus Teiltönen ``(Verhältnis, Stärke, Abklingfaktor)``.

    Jeder Teilton klingt exponentiell ab, ``Abklingfaktor``-mal so schnell wie
    der Grundton (der nach ``dauer_s`` auf etwa 1 % ist). Sinus und Hüllkurve
    entstehen per Drehung bzw. Multiplikation statt ``sin``/``exp`` je Probe —
    so bleibt die Erzeugung auch auf dem Handy schnell. Kurz eingeblendet, am
    Ende auf null ausgeblendet, die Spitze auf ``lautstaerke`` normiert.

    >>> daten = glocke(GLOCKE, 784.0, 0.5)
    >>> daten[:4], len(daten) - 44 == 2 * round(0.5 * RATE)
    (b'RIFF', True)
    >>> proben = struct.unpack(f"<{(len(daten) - 44) // 2}h", daten[44:])
    >>> proben[0], proben[-1], round(max(abs(p) for p in proben) / 32767, 2)
    (0, 0, 0.7)
    """
    n = max(round(dauer_s * RATE), 2)
    ein = max(round(0.002 * RATE), 1)
    aus = max(round(0.03 * RATE), 1)
    tau_proben = dauer_s / 4.6 * RATE  # e^-4.6 ≈ 1 %
    summe = [0.0] * n
    for verhaeltnis, staerke, faktor in teiltoene:
        f = grund_hz * verhaeltnis
        if f >= RATE / 2:
            continue
        schritt = complex(math.cos(2 * math.pi * f / RATE), math.sin(2 * math.pi * f / RATE))
        schritt *= math.exp(-faktor / tau_proben)
        z = complex(staerke, 0.0)  # Imaginärteil = Sinus, beginnt bei null
        for i in range(n):
            summe[i] += z.imag
            z *= schritt
    geformt = [x * min(i / ein, 1.0, (n - 1 - i) / aus) for i, x in enumerate(summe)]
    voll = 32767 * min(max(lautstaerke, 0.0), 1.0) / (max(abs(x) for x in geformt) or 1.0)
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as datei:
        datei.setnchannels(1)
        datei.setsampwidth(2)
        datei.setframerate(RATE)
        datei.writeframes(struct.pack(f"<{n}h", *(round(voll * x) for x in geformt)))
    return puffer.getvalue()


def toene() -> dict[str, bytes]:
    """Alle Klänge des Timers als WAV-Bytes — Signale und Klänge zur Wahl.

    >>> sorted(toene())
    ['countdown', 'ende', 'glocke1', 'glocke2', 'glocke3', 'gong', 'holz', 'schale', 'wechsel']
    >>> set(KLAENGE) <= set(toene())
    True
    """
    daten = {name: wav(folge) for name, folge in TOENE.items()}
    for name, (teiltoene, grund, dauer) in GLOCKEN.items():
        daten[name] = glocke(teiltoene, grund, dauer, LAUTSTAERKE.get(name, 0.7))
    return daten


__all__ = ["GLOCKEN", "KLAENGE", "LAUTSTAERKE", "RATE", "TOENE", "glocke", "toene", "wav"]
