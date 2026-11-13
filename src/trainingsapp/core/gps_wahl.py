"""GPS je Übung — die Karte „GPS“ im Reiter „Sensor“ (Ben, 13.11.2026, ``docs/plan_gps.md`` §12).

Bis dahin hing GPS an der festen Liste `core.strecke.SPORTARTEN`, und die App legte je
Sportart selbst eine Übung an. Jetzt ist es eine Eigenschaft der Übung (`Exercise.gps`,
Spalte ``exercise.gps_json``, Paketfeld ``gps``): Jede Übung mit eingeschaltetem GPS steht
im Reiter „Messung → GPS“ zur Wahl, und das Training wird bei ihr eingetragen. „Gehen“,
„Laufen“ und „Radfahren“ sind gewöhnliche Übungen des Pakets „Standard“.

**Rechenart.** Eine GPS-Übung rechnet wie Gehen, Laufen oder Rad — daran hängen die
Splitlänge (`core.strecke.split_laenge_m`), km/h oder min/km in der Anzeige und der Typ im
GPX. Mehr als diese drei gibt es nicht; `strecke.sportart` trägt die Rechenart weiter.

**Tempo-Grenzen.** Vier Grenzen in km/h (fünf Stufen) für „Zeit je Tempo“ mit festen Stufen
(Ben, 13.11.2026: „Mit festen Grenzen lassen sich Trainings vergleichen“). Sie standen einen
Tag lang geräteweit in den Einstellungen und gehören seither zur Übung; leer heißt: die
Vorgabe „mittel“ der Rechenart. Die Stufen heißen nach ihren Zahlen, sie teilen ein und
werten nichts (``docs/recht/00_zweckbestimmung.md``).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Final

from .strecke import GEHEN, LAUFEN, RAD, SPORTARTEN

#: Vorgaben der festen Grenzen und „eigen“ (die Werte der Person)
NIVEAU_LANGSAM: Final[str] = "langsam"
NIVEAU_MITTEL: Final[str] = "mittel"
NIVEAU_SCHNELL: Final[str] = "schnell"
NIVEAU_EIGEN: Final[str] = "eigen"
NIVEAUS: Final[tuple[str, ...]] = (NIVEAU_LANGSAM, NIVEAU_MITTEL, NIVEAU_SCHNELL, NIVEAU_EIGEN)
NIVEAU_NAMEN: Final[dict[str, str]] = {
    NIVEAU_LANGSAM: "langsam",
    NIVEAU_MITTEL: "mittel",
    NIVEAU_SCHNELL: "schnell",
    NIVEAU_EIGEN: "eigene Werte",
}
#: Vier Grenzen in km/h je Rechenart und Vorgabe — darunter, dazwischen und darüber liegen
#: die fünf Stufen. Setzungen zum Einteilen, keine Normwerte (Ben, 13.11.2026: mittel
#: endet beim Rad bei 25 km/h, beim Laufen bei 12–15 km/h; schnell = Rennrad, trainiert).
TEMPO_GRENZEN_KMH: Final[dict[str, dict[str, tuple[float, float, float, float]]]] = {
    GEHEN: {
        NIVEAU_LANGSAM: (2.0, 3.0, 4.0, 5.0),
        NIVEAU_MITTEL: (3.0, 4.0, 5.0, 6.0),
        NIVEAU_SCHNELL: (4.0, 5.0, 6.0, 7.0),
    },
    LAUFEN: {
        NIVEAU_LANGSAM: (6.0, 7.0, 8.5, 10.0),
        NIVEAU_MITTEL: (7.0, 9.0, 11.0, 13.0),
        NIVEAU_SCHNELL: (10.0, 12.0, 14.0, 16.0),
    },
    RAD: {
        NIVEAU_LANGSAM: (10.0, 14.0, 18.0, 22.0),
        NIVEAU_MITTEL: (13.0, 17.0, 21.0, 25.0),
        NIVEAU_SCHNELL: (20.0, 25.0, 30.0, 35.0),
    },
}
TEMPO_GRENZEN_ZAHL: Final[int] = 4
TEMPO_KMH_MAX: Final[float] = 120.0


def grenzen_gueltig(werte: Any) -> list[float] | None:
    """Vier aufsteigende Grenzen in km/h — sonst None.

    >>> grenzen_gueltig([8, 10.5, 12, 14]), grenzen_gueltig([8, 8, 12, 14])
    ([8.0, 10.5, 12.0, 14.0], None)
    >>> grenzen_gueltig([8, 10, 12]), grenzen_gueltig("kaputt"), grenzen_gueltig([0, 1, 2, 3])
    (None, None, None)
    """
    if not isinstance(werte, (list, tuple)) or len(werte) != TEMPO_GRENZEN_ZAHL:
        return None
    if any(isinstance(w, bool) or not isinstance(w, (int, float)) for w in werte):
        return None
    zahlen = [float(w) for w in werte]
    if zahlen[0] <= 0 or zahlen[-1] > TEMPO_KMH_MAX:
        return None
    if any(b <= a for a, b in pairwise(zahlen)):
        return None
    return zahlen


def vorgabe_kmh(art: str, niveau: str = NIVEAU_MITTEL) -> tuple[float, ...]:
    """Die Grenzen einer Vorgabe; eine unbekannte Rechenart nimmt die des Laufens, ein
    unbekanntes Niveau (auch „eigen“) „mittel“.

    >>> vorgabe_kmh("rad"), vorgabe_kmh("gehen", "schnell")
    ((13.0, 17.0, 21.0, 25.0), (4.0, 5.0, 6.0, 7.0))
    >>> vorgabe_kmh("schwimmen") == vorgabe_kmh("laufen", "eigen") == (7.0, 9.0, 11.0, 13.0)
    True
    """
    vorgaben = TEMPO_GRENZEN_KMH.get(art, TEMPO_GRENZEN_KMH[LAUFEN])
    return vorgaben.get(niveau, vorgaben[NIVEAU_MITTEL])


@dataclass(frozen=True, slots=True)
class GpsWahl:
    """Die Karte „GPS“ einer Übung.

    Unveränderlich wie `core.zaehlen.SensorWahl` — `dataclasses.replace` kopiert beim
    Kopieren einer Übung nur flach.

    >>> GpsWahl().an, GpsWahl().als_dict(), GpsWahl(art="rad").grenzen_kmh()
    (False, {}, (13.0, 17.0, 21.0, 25.0))
    >>> w = GpsWahl(art="laufen", tempo=(8.0, 10.0, 12.0, 14.0))
    >>> w.an, w.als_dict(), GpsWahl.aus_dict(w.als_dict()) == w
    (True, {'art': 'laufen', 'tempo': [8.0, 10.0, 12.0, 14.0]}, True)
    >>> w.niveau(), GpsWahl(art="laufen").niveau(), GpsWahl("gehen", (4.0, 5.0, 6.0, 7.0)).niveau()
    ('eigen', 'mittel', 'schnell')
    """

    #: Rechenart: eine aus `core.strecke.SPORTARTEN` — leer: GPS ist aus
    art: str = ""
    #: Vier Grenzen in km/h — leer: die Vorgabe „mittel“ der Rechenart
    tempo: tuple[float, ...] = ()

    @property
    def an(self) -> bool:
        return self.art in SPORTARTEN

    def grenzen_kmh(self) -> tuple[float, ...]:
        """Die vier geltenden Grenzen: die eigenen, sonst die Vorgabe „mittel“."""
        return self.tempo or vorgabe_kmh(self.art)

    def niveau(self) -> str:
        """Welcher Vorgabe die Grenzen entsprechen — sonst „eigen“."""
        grenzen = self.grenzen_kmh()
        for name in (NIVEAU_MITTEL, NIVEAU_LANGSAM, NIVEAU_SCHNELL):
            if grenzen == vorgabe_kmh(self.art, name):
                return name
        return NIVEAU_EIGEN

    def als_dict(self) -> dict[str, Any]:
        """Nur, was gesetzt ist — aus ist leer (im Paket fehlt das Feld dann).

        >>> GpsWahl(art="gehen").als_dict(), GpsWahl(tempo=(1.0, 2.0, 3.0, 4.0)).als_dict()
        ({'art': 'gehen'}, {})
        """
        if not self.an:
            return {}
        d: dict[str, Any] = {"art": self.art}
        if self.tempo:
            d["tempo"] = list(self.tempo)
        return d

    @classmethod
    def aus_dict(cls, d: Any) -> GpsWahl:
        """Defensiv: Unbrauchbares gilt als Vorgabe. Eine unbekannte Rechenart (eine neuere
        App) heißt hier: GPS aus; ungültige Grenzen: die Vorgabe.

        >>> GpsWahl.aus_dict("kaputt") == GpsWahl.aus_dict({"art": "schwimmen"}) == GpsWahl()
        True
        >>> GpsWahl.aus_dict({"art": " Rad ", "tempo": [3, 2, 1]})
        GpsWahl(art='rad', tempo=())
        >>> GpsWahl.aus_dict({"art": "gehen", "tempo": [3, 4, 5, 6], "x": 1}).tempo
        (3.0, 4.0, 5.0, 6.0)
        """
        if not isinstance(d, dict):
            return cls()
        art = d.get("art")
        art = art.strip().lower() if isinstance(art, str) else ""
        if art not in SPORTARTEN:
            return cls()
        grenzen = grenzen_gueltig(d.get("tempo"))
        return cls(art=art, tempo=tuple(grenzen) if grenzen is not None else ())


#: Die Schlüssel der Karte im Paket (``gps``)
SCHLUESSEL: Final[tuple[str, ...]] = ("art", "tempo")


def gps_pruefen(roh: Any) -> tuple[list[str], list[str]]:
    """Was `GpsWahl.aus_dict` still als Vorgabe läse, in Worten — ``(Fehler, Hinweise)`` für
    ``trainingsapp-paket pruefen`` (wie `core.zaehlen.wahl_pruefen`): Ein falscher Typ, eine
    fehlende Rechenart und unbrauchbare Grenzen sind Fehler — die Wahl ginge beim Einlesen
    verloren. Eine unbekannte Rechenart oder ein unbekannter Schlüssel ist ein Hinweis: ein
    Tippfehler, oder ein Feld einer neueren App.

    >>> gps_pruefen({"art": "gehen", "tempo": [3, 4, 5, 6]}), gps_pruefen({"art": "rad"})
    (([], []), ([], []))
    >>> gps_pruefen(True)[0]
    ['keine Tabelle (etwa { art = "gehen" }), sondern true — GPS bleibt aus']
    >>> gps_pruefen({"tempo": [3, 4, 5, 6]})[0]
    ['„art“ fehlt (gehen, laufen, rad) — GPS bleibt aus']
    >>> gps_pruefen({"art": 3})[0]
    ['„art“ muss ein Text in Anführungszeichen sein, nicht 3']
    >>> for h in gps_pruefen({"art": "schwimmen", "tempi": 1})[1]: print(h)
    unbekannte Rechenart „schwimmen“ — GPS bleibt aus (bekannt: gehen, laufen, rad)
    unbekannter Schlüssel „tempi“ — wird überlesen (bekannt: art, tempo)
    >>> gps_pruefen({"art": "rad", "tempo": [25, 20, 30, 35]})[0]
    ['„tempo“ braucht vier aufsteigende Zahlen in km/h (bis 120), nicht [25, 20, 30, 35]']
    """
    if not isinstance(roh, dict):
        return [
            f'keine Tabelle (etwa {{ art = "gehen" }}), sondern {_wert_text(roh)} — GPS bleibt aus'
        ], []
    fehler: list[str] = []
    hinweise: list[str] = []
    bekannt = ", ".join(SPORTARTEN)
    art = roh.get("art")
    if "art" not in roh:
        fehler.append(f"„art“ fehlt ({bekannt}) — GPS bleibt aus")
    elif not isinstance(art, str):
        fehler.append(f"„art“ muss ein Text in Anführungszeichen sein, nicht {_wert_text(art)}")
    elif art.strip().lower() not in SPORTARTEN:
        hinweise.append(f"unbekannte Rechenart „{art}“ — GPS bleibt aus (bekannt: {bekannt})")
    if "tempo" in roh and grenzen_gueltig(roh["tempo"]) is None:
        fehler.append(
            f"„tempo“ braucht vier aufsteigende Zahlen in km/h (bis {TEMPO_KMH_MAX:.0f}), "
            f"nicht {_wert_text(roh['tempo'])}"
        )
    hinweise.extend(
        f"unbekannter Schlüssel „{schluessel}“ — wird überlesen (bekannt: {', '.join(SCHLUESSEL)})"
        for schluessel in roh
        if str(schluessel) not in SCHLUESSEL
    )
    return fehler, hinweise


def _wert_text(wert: Any) -> str:
    """Ein Wert, wie er in der TOML-Datei steht."""
    if isinstance(wert, bool):
        return "true" if wert else "false"
    if isinstance(wert, str):
        return f'"{wert}"'
    return str(wert)


__all__ = [
    "NIVEAUS",
    "NIVEAU_EIGEN",
    "NIVEAU_LANGSAM",
    "NIVEAU_MITTEL",
    "NIVEAU_NAMEN",
    "NIVEAU_SCHNELL",
    "SCHLUESSEL",
    "TEMPO_GRENZEN_KMH",
    "TEMPO_GRENZEN_ZAHL",
    "TEMPO_KMH_MAX",
    "GpsWahl",
    "gps_pruefen",
    "grenzen_gueltig",
    "vorgabe_kmh",
]
