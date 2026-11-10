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
(150.0, 0, None)
>>> w = HfEinstellungen.aus_dict({"achse_oben": "fest", "achse_oben_bpm": 180, "erholung_x_s": 95})
>>> w.achse_oben, w.achse_oben_bpm, w.achse_unten, w.erholung_fenster()
('fest', 180.0, 'profil', (30, 60, 95, 120))
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
#: 0 = **nach Abstand** (Ben, 10.11.2026: „Tonfolge schneller mit der Abweichung“,
#: `core.hf_ziel.tonfolge_s`) — die Vorgabe; die festen Takte bleiben wählbar
TAKT_NACH_ABSTAND: Final[int] = 0
ALARM_TAKT_S: Final[tuple[int, ...]] = (TAKT_NACH_ABSTAND, 3, 4, 5, 10)
ALARM_KLANG: Final[str] = "schale"
#: Klang unter dem Zielbereich — tiefer als der obere (`core.klang.KLAENGE`)
ALARM_KLANG_TIEF: Final[str] = "glocke3"
ALARM_MIN_BPM: Final[float] = 40.0
ALARM_MAX_BPM: Final[float] = 230.0
#: Wertebereich der HF-Achse, **je Seite für sich** (Ben, 10.11.2026, A22): Automatik aus der
#: Kurve · der Profilwert (oben HFmax, unten Ruhe-HF) · ein fester Wert
ACHSE_AUTO: Final[str] = "auto"
ACHSE_PROFIL: Final[str] = "profil"
ACHSE_FEST: Final[str] = "fest"
ACHSEN: Final[tuple[str, ...]] = (ACHSE_AUTO, ACHSE_PROFIL, ACHSE_FEST)
ACHSE_OBEN_FEST: Final[float] = 180.0
ACHSE_UNTEN_FEST: Final[float] = 60.0
#: Erholung: die festen Fenster nach dem Belastungsende (s), das frei wählbare „X“ und bis
#: wann gemessen wird — danach endet die Erholung von selbst
ERHOLUNG_FENSTER_S: Final[tuple[int, ...]] = (30, 60, 120)
ERHOLUNG_X_S: Final[int] = 180
ERHOLUNG_X_MIN_S: Final[int] = 10
ERHOLUNG_X_MAX_S: Final[int] = 900
MESSEN_BIS_S: Final[tuple[int, ...]] = (60, 120, 180, 300, 600)


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


def _achse(x: Any) -> str:
    return x if isinstance(x, str) and x in ACHSEN else ACHSE_PROFIL


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
    alarm_takt_s: int = TAKT_NACH_ABSTAND
    #: Zielbereich (Entscheidung C, 7.11.2026): auch eine **untere** Grenze mit eigenem,
    #: tieferem Klang — ein Ton als Information, keine Steuerung
    ziel_unten_bpm: float | None = None
    alarm_klang_tief: str = ALARM_KLANG_TIEF
    #: Wertebereich der HF-Achse je Seite (`ACHSEN`) und der feste Wert dazu
    achse_oben: str = ACHSE_PROFIL
    achse_oben_bpm: float = ACHSE_OBEN_FEST
    achse_unten: str = ACHSE_PROFIL
    achse_unten_bpm: float = ACHSE_UNTEN_FEST
    #: Erholung: welche der festen Fenster gelten, das Fenster X (0 = keins), Messen bis (s)
    erholung_fest: list[int] = field(default_factory=lambda: list(ERHOLUNG_FENSTER_S))
    erholung_x_s: int = ERHOLUNG_X_S
    messen_bis_s: int = 180

    def erholung_fenster(self) -> tuple[int, ...]:
        """Die Fenster der Erholung, aufsteigend — die gewählten festen und X.

        >>> HfEinstellungen().erholung_fenster()
        (30, 60, 120, 180)
        >>> HfEinstellungen(erholung_fest=[60], erholung_x_s=0).erholung_fenster()
        (60,)
        """
        fenster = {f for f in self.erholung_fest if f in ERHOLUNG_FENSTER_S}
        if self.erholung_x_s:
            fenster.add(int(self.erholung_x_s))
        return tuple(sorted(fenster)) or (ERHOLUNG_FENSTER_S[1],)

    def messen_bis(self) -> int:
        """So lange läuft eine Erholung höchstens — nie kürzer als das längste Fenster
        samt seinem Mittel.

        >>> HfEinstellungen(messen_bis_s=60).messen_bis()
        183
        """
        return max(int(self.messen_bis_s), max(self.erholung_fenster()) + 3)

    def messen_bis_anzeige(self) -> int:
        """„Messen bis“ für die Beschriftung — ohne die Sekunden fürs letzte Mittel.

        >>> HfEinstellungen().messen_bis_anzeige(), HfEinstellungen().messen_bis()
        (180, 183)
        """
        return max(int(self.messen_bis_s), max(self.erholung_fenster()))

    def alarm_grenze(self) -> float | None:
        """Die wirksame Grenze — nur mit Schalter und Wert.

        >>> HfEinstellungen(alarm_an=True, alarm_bpm=150).alarm_grenze()
        150.0
        >>> HfEinstellungen(alarm_bpm=150).alarm_grenze() is None
        True
        """
        return float(self.alarm_bpm) if self.alarm_an and self.alarm_bpm else None

    def ziel_unten(self) -> float | None:
        """Die wirksame untere Grenze des Zielbereichs — nur mit Schalter und Wert.

        >>> HfEinstellungen(alarm_an=True, ziel_unten_bpm=110).ziel_unten()
        110.0
        """
        return float(self.ziel_unten_bpm) if self.alarm_an and self.ziel_unten_bpm else None

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
            "ziel_unten_bpm": self.ziel_unten_bpm,
            "alarm_klang_tief": self.alarm_klang_tief,
            "achse_oben": self.achse_oben,
            "achse_oben_bpm": self.achse_oben_bpm,
            "achse_unten": self.achse_unten,
            "achse_unten_bpm": self.achse_unten_bpm,
            "erholung_fest": list(self.erholung_fest),
            "erholung_x_s": self.erholung_x_s,
            "messen_bis_s": self.messen_bis_s,
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
        unten = _zahl(d.get("ziel_unten_bpm"))
        klang_tief = d.get("alarm_klang_tief")
        oben_bpm = _zahl(d.get("achse_oben_bpm"))
        unten_bpm = _zahl(d.get("achse_unten_bpm"))
        fest_roh = d.get("erholung_fest")
        x_s = d.get("erholung_x_s")
        bis_s = d.get("messen_bis_s")
        return cls(
            modell=modell if modell in MODELLE else vorgabe.modell,
            eigene=eigene[:EIGENE_MAX],
            namen=namen,
            formel=formel if formel in FORMELN else vorgabe.formel,
            alarm_an=d.get("alarm_an") is True,
            alarm_bpm=bpm if bpm is not None and ALARM_MIN_BPM <= bpm <= ALARM_MAX_BPM else None,
            ziel_unten_bpm=(
                unten if unten is not None and ALARM_MIN_BPM <= unten <= ALARM_MAX_BPM else None
            ),
            alarm_klang_tief=(
                str(klang_tief) if isinstance(klang_tief, str) and klang_tief else ALARM_KLANG_TIEF
            ),
            alarm_klang=klang if isinstance(klang, str) and klang else vorgabe.alarm_klang,
            alarm_takt_s=takt
            if isinstance(takt, int) and not isinstance(takt, bool) and takt in ALARM_TAKT_S
            else vorgabe.alarm_takt_s,
            achse_oben=_achse(d.get("achse_oben")),
            achse_oben_bpm=(
                oben_bpm
                if oben_bpm is not None and ALARM_MIN_BPM <= oben_bpm <= ALARM_MAX_BPM
                else ACHSE_OBEN_FEST
            ),
            achse_unten=_achse(d.get("achse_unten")),
            achse_unten_bpm=(
                unten_bpm
                if unten_bpm is not None and 20.0 <= unten_bpm <= ALARM_MAX_BPM
                else ACHSE_UNTEN_FEST
            ),
            erholung_fest=(
                [f for f in ERHOLUNG_FENSTER_S if f in fest_roh]
                if isinstance(fest_roh, list)
                else list(ERHOLUNG_FENSTER_S)
            ),
            erholung_x_s=(
                x_s
                if isinstance(x_s, int)
                and not isinstance(x_s, bool)
                and (x_s == 0 or ERHOLUNG_X_MIN_S <= x_s <= ERHOLUNG_X_MAX_S)
                else ERHOLUNG_X_S
            ),
            messen_bis_s=bis_s if bis_s in MESSEN_BIS_S and not isinstance(bis_s, bool) else 180,
        )


def einstellungen_lesen(text: str | None) -> HfEinstellungen:
    try:
        return HfEinstellungen.aus_dict(json.loads(text or ""))
    except (TypeError, ValueError):
        return HfEinstellungen()


def einstellungen_schreiben(e: HfEinstellungen) -> str:
    return json.dumps(e.als_dict(), ensure_ascii=False)


__all__ = [
    "ACHSEN",
    "ACHSE_AUTO",
    "ACHSE_FEST",
    "ACHSE_OBEN_FEST",
    "ACHSE_PROFIL",
    "ACHSE_UNTEN_FEST",
    "ALARM_KLANG",
    "ALARM_MAX_BPM",
    "ALARM_MIN_BPM",
    "ALARM_TAKT_S",
    "EIGENE_MAX",
    "ERHOLUNG_FENSTER_S",
    "ERHOLUNG_X_MAX_S",
    "ERHOLUNG_X_MIN_S",
    "ERHOLUNG_X_S",
    "FORMELN",
    "FORMEL_NAMEN",
    "MESSEN_BIS_S",
    "MODELLE",
    "MODELL_AUTO",
    "MODELL_ERKLAERUNG",
    "MODELL_NAMEN",
    "TAKT_NACH_ABSTAND",
    "EigeneGrenze",
    "HfEinstellungen",
    "einstellungen_lesen",
    "einstellungen_schreiben",
]
