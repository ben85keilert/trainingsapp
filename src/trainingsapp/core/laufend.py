"""Was gerade läuft — der Inhalt der Benachrichtigung (Ben, 16.10.2026).

Läuft eine HRV-Messung, ein Training mit Karte, ein GPS-Test oder der Timer,
steht das in einer Benachrichtigung mit dem Symbol der App in der Statusleiste:
im Titel, was läuft, darunter je Tätigkeit eine Zeile mit ihrer Zeit —
„HRV-Messung: Aufnahme 12:34 · Polar H10“, „Gehen: 1,23 km · 10:05“, „Timer:
Belastung noch 0:12 · Runde 2/5“. Eingeklappt passt eine kurze Zeile („HRV 12:34
· Gehen 10:05 · Timer 0:12“). Die Stoppuhr im Kopf der Benachrichtigung zählt
Android selbst weiter (``seit_ms``), auch wenn die App gerade nichts rechnet.

Ortsfrei: Koordinaten stehen nie darin (`docs/plan_gps.md`, Abschnitt 0).
Kein flet-Import — die Zeilen baut `ui.laufend`, zeigen lässt sie
`ui.geraete.flet_ble_transport`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Laufend:
    """Eine Tätigkeit, die gerade läuft."""

    #: „HRV-Messung“, „Gehen“, „Timer“
    titel: str
    #: Die Zeile in der ausgeklappten Benachrichtigung, mit Zeit
    zeile: str
    #: Kurzform für die eingeklappte Zeile („HRV 12:34“)
    kurz: str
    #: Beginn — für die Stoppuhr im Kopf; ``None`` = keine (z. B. nur verbunden)
    seit: datetime | None = None


@dataclass(frozen=True, slots=True)
class Benachrichtigung:
    """Was die Benachrichtigung zeigt — eingeklappt ``text``, ausgeklappt ``lang``."""

    titel: str
    text: str
    lang: str
    #: Stoppuhr ab diesem Zeitpunkt (ms seit 1970); 0 = keine
    seit_ms: int = 0


def uhr(sekunden: float) -> str:
    """Laufzeit als ``m:ss`` bzw. ``h:mm:ss``.

    >>> uhr(5), uhr(754.9), uhr(3725)
    ('0:05', '12:34', '1:02:05')
    """
    s = max(0, int(sekunden))
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


def benachrichtigung(laufend: Sequence[Laufend]) -> Benachrichtigung | None:
    """Der Inhalt für alles, was läuft — ``None``, wenn nichts läuft.

    Eine Tätigkeit: ihr Titel mit „läuft“, darunter ihre Zeile. Mehrere: die Titel
    nebeneinander, eingeklappt die Kurzformen, ausgeklappt je eine Zeile. Die
    Stoppuhr beginnt mit der frühesten Tätigkeit, die einen Beginn hat.

    >>> from datetime import UTC
    >>> hrv = Laufend("HRV-Messung", "Aufnahme 12:34 · Polar H10", "HRV 12:34",
    ...               datetime(2026, 10, 16, 8, 0, tzinfo=UTC))
    >>> timer = Laufend("Timer", "Belastung noch 0:12 · Runde 2/5", "Timer 0:12")
    >>> b = benachrichtigung([hrv])
    >>> b.titel, b.text, b.seit_ms
    ('HRV-Messung läuft', 'Aufnahme 12:34 · Polar H10', 1792137600000)
    >>> b = benachrichtigung([hrv, timer])
    >>> b.titel, b.text
    ('HRV-Messung · Timer', 'HRV 12:34 · Timer 0:12')
    >>> print(b.lang)
    HRV-Messung: Aufnahme 12:34 · Polar H10
    Timer: Belastung noch 0:12 · Runde 2/5
    >>> benachrichtigung([]) is None
    True
    """
    if not laufend:
        return None
    anfaenge = [x.seit for x in laufend if x.seit is not None]
    seit_ms = int(min(anfaenge).timestamp() * 1000) if anfaenge else 0
    if len(laufend) == 1:
        (x,) = laufend
        return Benachrichtigung(f"{x.titel} läuft", x.zeile, x.zeile, seit_ms)
    return Benachrichtigung(
        " · ".join(x.titel for x in laufend),
        " · ".join(x.kurz for x in laufend),
        "\n".join(f"{x.titel}: {x.zeile}" for x in laufend),
        seit_ms,
    )


__all__ = ["Benachrichtigung", "Laufend", "benachrichtigung", "uhr"]
