"""Einstellungen der Herzfrequenz-Bereiche — **je Profil** (Ben, 29.10.2026).

Welches Bereichsmodell gilt (drei Bereiche, fünf ACSM-Stufen, zehn Cluster, eigene), und
bei „eigen“ die Grenzen und Namen der Person. Gespeichert in ``app_setting`` unter
``hf_einstellungen:<profil-id>`` (wie `darstellung:<profil-id>`), weil Bereiche zur Person
gehören, nicht zum Gerät. Was die Sicht zeigt (Vorgabe Herzfrequenz oder HRV), steht
gerätelokal in `core.hrv_einstellungen`.

Kein Wissen über die Physiologie: die Grenzen rechnet `hrv_core.herzfrequenz`, zusammen
mit dem Profil in `core.hf_profil.bereiche_fuer`.

>>> e = HfEinstellungen(modell="eigen", eigene=[EigeneGrenze(bpm=120), EigeneGrenze(prozent=80)])
>>> HfEinstellungen.aus_dict(e.als_dict()) == e
True
>>> HfEinstellungen.aus_dict({"modell": "fuenf"}).modell
'auto'
>>> a = HfEinstellungen.aus_dict({"alarm_an": True, "alarm_bpm": 150, "alarm_takt_s": 9})
>>> a.alarm_grenze(), a.alarm_takt_s, HfEinstellungen.aus_dict({"alarm_bpm": 500}).alarm_bpm
(150.0, 4, None)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Final

from hrv_core import herzfrequenz as hz

#: „auto“: drei Bereiche, sobald eine individuelle Schwelle vorliegt, sonst zehn Cluster
MODELL_AUTO: Final[str] = "auto"
MODELLE: Final[tuple[str, ...]] = (
    MODELL_AUTO,
    hz.MODELL_DREI,
    hz.MODELL_ACSM,
    hz.MODELL_CLUSTER,
    hz.MODELL_EIGEN,
)
MODELL_NAMEN: Final[dict[str, str]] = {
    MODELL_AUTO: "Automatisch",
    hz.MODELL_DREI: "Drei Bereiche (Schwellen)",
    hz.MODELL_ACSM: "Fünf Stufen (ACSM)",
    hz.MODELL_CLUSTER: "Zehn Cluster (je 10 %)",
    hz.MODELL_EIGEN: "Eigene Bereiche",
}
MODELL_ERKLAERUNG: Final[dict[str, str]] = {
    MODELL_AUTO: "Drei Bereiche, sobald eine eigene Schwelle (Talk-Test, Labor) vorliegt; "
    "bis dahin zehn Cluster.",
    hz.MODELL_DREI: "Unter Schwelle 1, zwischen den Schwellen, über Schwelle 2. Die Schwellen "
    "kommen aus Labor, Talk-Test oder der Schätzung aus Ruhe- und Spitzen-HF (sonst 42 / 77 % "
    "der Reserve) — mit sichtbarer Unsicherheit.",
    hz.MODELL_ACSM: "Stufen der Leitlinien: 30 / 40 / 60 / 90 % der Herzfrequenzreserve.",
    hz.MODELL_CLUSTER: "Zehn gleich breite Stufen der Reserve — ohne Deutung.",
    hz.MODELL_EIGEN: "Deine Grenzen in bpm oder % der Reserve, mit eigenen Namen.",
}
#: Vorgabe-Formel: „auto“ wählt nach Geschlecht (Gulati für Frauen, sonst Nes/HUNT)
#: Reihenfolge im Menü (Ben, 30.10.2026): automatisch – Frauen – Nes – Tanaka (älter)
FORMELN: Final[tuple[str, ...]] = ("auto", "gulati", "nes", "tanaka")
FORMEL_NAMEN: Final[dict[str, str]] = {
    "auto": "Automatisch (Frauen Gulati, sonst Nes/HUNT)",
    "gulati": "Gulati 2010 (Frauen): 206 − 0,88 · Alter",
    "nes": "Nes 2013 (HUNT, Männer und Frauen): 211 − 0,64 · Alter",
    "tanaka": "Tanaka 2001 (älter, kleinere Stichprobe): 208 − 0,7 · Alter",
}
EIGENE_MAX: Final[int] = 8
#: Signal über einer selbst gesetzten Grenze (Ben, 30.10.2026: „Ein Alarm, piepen alle 3–5
#: Sekunden, wenn man über einer bestimmten HF ist … nicht aufdringlich“): so oft höchstens (s)
ALARM_TAKT_S: Final[tuple[int, ...]] = (3, 4, 5, 10)
ALARM_KLANG: Final[str] = "schale"
ALARM_MIN_BPM: Final[float] = 40.0
ALARM_MAX_BPM: Final[float] = 230.0


@dataclass(frozen=True, slots=True)
class EigeneGrenze:
    """Eine Grenze der eigenen Bereiche — in bpm **oder** in % der Reserve."""

    bpm: float | None = None
    prozent: float | None = None

    def als_dict(self) -> dict[str, float]:
        d: dict[str, float] = {}
        if self.bpm is not None:
            d["bpm"] = float(self.bpm)
        if self.prozent is not None:
            d["prozent"] = float(self.prozent)
        return d

    @classmethod
    def aus_dict(cls, d: Any) -> EigeneGrenze | None:
        if not isinstance(d, dict):
            return None
        bpm = _zahl(d.get("bpm"))
        prozent = _zahl(d.get("prozent"))
        if bpm is None and prozent is None:
            return None
        return cls(bpm=bpm, prozent=None if bpm is not None else prozent)


def _zahl(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


@dataclass
class HfEinstellungen:
    """Bereichsmodell und eigene Grenzen eines Profils."""

    modell: str = MODELL_AUTO
    eigene: list[EigeneGrenze] = field(default_factory=list)
    #: Namen der eigenen Bereiche (eine mehr als Grenzen); leer = „Bereich 1…n“
    namen: list[str] = field(default_factory=list)
    formel: str = "auto"
    #: Signal über einer Grenze: an, Grenze (bpm), Klang (`core.klang.KLAENGE`), Takt (s)
    alarm_an: bool = False
    alarm_bpm: float | None = None
    alarm_klang: str = ALARM_KLANG
    alarm_takt_s: int = 4

    def alarm_grenze(self) -> float | None:
        """Die wirksame Grenze — nur mit Schalter und Wert.

        >>> HfEinstellungen(alarm_an=True, alarm_bpm=150).alarm_grenze()
        150.0
        >>> HfEinstellungen(alarm_bpm=150).alarm_grenze() is None
        True
        """
        return float(self.alarm_bpm) if self.alarm_an and self.alarm_bpm else None

    def als_dict(self) -> dict[str, Any]:
        return {
            "modell": self.modell,
            "eigene": [g.als_dict() for g in self.eigene],
            "namen": list(self.namen),
            "formel": self.formel,
            "alarm_an": self.alarm_an,
            "alarm_bpm": self.alarm_bpm,
            "alarm_klang": self.alarm_klang,
            "alarm_takt_s": self.alarm_takt_s,
        }

    @classmethod
    def aus_dict(cls, d: Any) -> HfEinstellungen:
        vorgabe = cls()
        if not isinstance(d, dict):
            return vorgabe
        modell = d.get("modell")
        eigene_roh = d.get("eigene")
        eigene = (
            [g for g in (EigeneGrenze.aus_dict(x) for x in eigene_roh) if g is not None]
            if isinstance(eigene_roh, list)
            else []
        )
        namen_roh = d.get("namen")
        namen = (
            [str(n)[:40] for n in namen_roh if isinstance(n, str)]
            if isinstance(namen_roh, list)
            else []
        )
        formel = d.get("formel")
        bpm = _zahl(d.get("alarm_bpm"))
        takt = d.get("alarm_takt_s")
        klang = d.get("alarm_klang")
        return cls(
            modell=modell if modell in MODELLE else vorgabe.modell,
            eigene=eigene[:EIGENE_MAX],
            namen=namen,
            formel=formel if formel in FORMELN else vorgabe.formel,
            alarm_an=d.get("alarm_an") is True,
            alarm_bpm=bpm if bpm is not None and ALARM_MIN_BPM <= bpm <= ALARM_MAX_BPM else None,
            alarm_klang=klang if isinstance(klang, str) and klang else vorgabe.alarm_klang,
            alarm_takt_s=takt
            if isinstance(takt, int) and not isinstance(takt, bool) and takt in ALARM_TAKT_S
            else vorgabe.alarm_takt_s,
        )


def einstellungen_lesen(text: str | None) -> HfEinstellungen:
    try:
        return HfEinstellungen.aus_dict(json.loads(text or ""))
    except (TypeError, ValueError):
        return HfEinstellungen()


def einstellungen_schreiben(e: HfEinstellungen) -> str:
    return json.dumps(e.als_dict(), ensure_ascii=False)


__all__ = [
    "ALARM_KLANG",
    "ALARM_MAX_BPM",
    "ALARM_MIN_BPM",
    "ALARM_TAKT_S",
    "EIGENE_MAX",
    "FORMELN",
    "FORMEL_NAMEN",
    "MODELLE",
    "MODELL_AUTO",
    "MODELL_ERKLAERUNG",
    "MODELL_NAMEN",
    "EigeneGrenze",
    "HfEinstellungen",
    "einstellungen_lesen",
    "einstellungen_schreiben",
]
