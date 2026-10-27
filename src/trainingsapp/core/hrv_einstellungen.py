"""Einstellungen der HRV-Messung — was man sieht, mit sinnvollen Vorgaben.

Die App richtet sich an Patienten und Kunden, die sich selbst überprüfen. Sie
soll ohne jede Einstellung brauchbar sein; wer mehr will, stellt es unter
Einstellungen → HRV-Messung ein und kann jederzeit auf die Vorgaben
zurücksetzen (`HrvEinstellungen()`).

Was hier steht, gilt gerätelokal (``app_setting``, Schlüssel
``hrv_einstellungen``). Welche Verlaufskurven mit welchen Fenstern zu sehen
sind, ist die `Ansicht` (`core.hrv_ansicht`) — sie lässt sich zusätzlich unter
Namen speichern. Was „automatische Korrektur" heißt, sind die
`Korrekturregeln` (`hrv_core.regeln`).

Kein Wissen über die Kennzahlen selbst: Kachel-Schlüssel sind Text, die
Bedeutung kennt die Oberfläche. Dieses Modul importiert nichts aus anderen
Schichten.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Final

from trainingsapp.core.uhr_seiten import SEITEN as UHR_SEITEN

#: Werte der Übersicht über der Kurve, wenn nichts eingestellt ist (Reihenfolge zählt)
STANDARD_KACHELN: Final[tuple[str, ...]] = (
    "hf",
    "rr",
    "atemfrequenz",
    "rmssd",
    "sdnn",
    "schwankung",
    "artefakte",
)
#: Davon groß hervorgehoben
STANDARD_GROSS: Final[tuple[str, ...]] = ("hf", "rr")
#: Darstellung der Werte: eine ruhige Übersicht (Liste) oder Kacheln
UEBERSICHT: Final[str] = "uebersicht"
KACHELN: Final[str] = "kacheln"

#: Breiten der Knöpfe über der Live-Kurve (s)
LIVE_FENSTER: Final[tuple[int, ...]] = (60, 120, 300, 600)
#: Wie lange der Live-Verlauf zurückreicht (s) — der Puffer der Live-Kurven (Ben,
#: 26.10.2026: einstellbar, mindestens 30 min). Gilt ab der nächsten Verbindung.
PUFFER_S: Final[tuple[int, ...]] = (1800, 3600, 7200, 14400)
#: Notizen zur Messung: so viele Zeilen zeigt die Liste, mehr rollt sie (Ben, 27.10.2026:
#: „bei vielen Notizen ist es schwierig, die Notizen durchzuklicken und an der Kurve zu
#: beobachten“); 0 = alle, wie bisher
NOTIZEN_ZEILEN: Final[tuple[int, ...]] = (5, 7, 10, 15, 0)
#: Eingetippte Breite der Zeitachse (Ben, 21.10.2026): mindestens 10 s, live höchstens
#: so viel, wie der Puffer hält (`HrvEinstellungen.puffer_s`)
FENSTER_MIN_S: Final[int] = 10
FENSTER_MAX_S: Final[int] = max(PUFFER_S)

#: Ebenen über der Hauptkurve einer Aufzeichnung (Ben, 19.10.2026, Plan D): Notizen (gelb),
#: Leistungen der Person (blau, `person/leistung`), Abschnittsbalken — einzeln einblendbar
EBENE_NOTIZEN: Final[str] = "notizen"
EBENE_LEISTUNGEN: Final[str] = "leistungen"
EBENE_ABSCHNITTE: Final[str] = "abschnitte"
EBENEN: Final[tuple[str, ...]] = (EBENE_NOTIZEN, EBENE_LEISTUNGEN, EBENE_ABSCHNITTE)

#: Erweitert — Latenz, nach der ein losgelassenes Analysefenster neu rechnet (ms).
#: Kommt in dieser Zeit noch eine Bewegung nach, wird erst danach gerechnet.
NACHRECHNEN_MS: Final[tuple[int, ...]] = (0, 250, 500, 800, 1200)
#: Erweitert — so oft rechnet das Live-Spektrum neu (s). Ben, 14.10.2026: alle
#: 15 s genügen; wer es genauer braucht, stellt es nach.
LIVE_SPEKTRUM_S: Final[tuple[int, ...]] = (5, 10, 15, 30, 60)
#: Längen des verschiebbaren Analysefensters in der Aufzeichnung (s); 5 min ist
#: die übliche Dauer einer Kurzzeit-HRV
ANALYSE_LAENGEN: Final[tuple[int, ...]] = (60, 120, 300, 600)
#: Schrittweite der Pfeile ‹ › am Analysefenster (Ben, 26.10.2026): ein halbes oder ein
#: ganzes Fenster, sonst Sekunden
ANALYSE_SCHRITTE: Final[tuple[str, ...]] = ("halb", "ganz", "60", "30", "10")

#: Analysebereiche unter der Hauptkurve
BEREICH_ZEIT: Final[str] = "zeit"
BEREICH_FREQUENZ: Final[str] = "frequenz"
BEREICH_NICHTLINEAR: Final[str] = "nichtlinear"


@dataclass
class HrvEinstellungen:
    """Gerätelokale Einstellungen der HRV-Messung.

    >>> e = HrvEinstellungen(kacheln=["hf", "rr"], fenster_s=300)
    >>> HrvEinstellungen.aus_dict(e.als_dict()) == e
    True
    >>> HrvEinstellungen.aus_dict({"fenster_s": 7, "kacheln": "kaputt"}) == HrvEinstellungen()
    True
    >>> HrvEinstellungen.aus_dict({"fenster_s": 210}).fenster_s  # eingetippt: 3:30 min
    210
    >>> HrvEinstellungen.aus_dict({"notizen_zeilen": 10}).notizen_zeilen
    10
    >>> HrvEinstellungen.aus_dict({"notizen_zeilen": 8}).notizen_zeilen  # nicht zur Wahl
    7
    >>> HrvEinstellungen.aus_dict({"puffer_s": 7200}).puffer_s, HrvEinstellungen().puffer_s
    (7200, 1800)
    >>> HrvEinstellungen.aus_dict({"analyse_schritt": "30"}).analyse_schritt
    '30'
    >>> HrvEinstellungen.aus_dict({"analyse_schritt": 30}).analyse_schritt  # kein Text: Vorgabe
    'halb'
    >>> HrvEinstellungen.aus_dict({"puffer_s": 1800, "fenster_s": 7200}).fenster_s  # passt nicht
    120
    >>> e = HrvEinstellungen.aus_dict({"live_spektrum_s": 30, "nachrechnen_ms": 7})
    >>> e.live_spektrum_s, e.nachrechnen_ms
    (30, 500)
    >>> HrvEinstellungen(frequenz=True, nichtlinear=True).bereiche(optisch=True)
    ['zeit', 'frequenz']
    >>> HrvEinstellungen().bereiche(optisch=False)
    ['zeit']
    """

    #: Reiter „Messung" in der Navigationsleiste — ohne Gerät spart Ausblenden Platz
    messung_anzeigen: bool = True
    #: Werte über der Hauptkurve, in dieser Reihenfolge (Übersicht oder Kacheln)
    kacheln: list[str] = field(default_factory=lambda: list(STANDARD_KACHELN))
    #: Davon groß hervorgehoben (Übersicht: oben in einer Reihe; Kacheln: halbe Breite)
    gross: list[str] = field(default_factory=lambda: list(STANDARD_GROSS))
    #: `UEBERSICHT` oder `KACHELN`
    darstellung: str = UEBERSICHT
    #: Breite des Live-Zeitfensters (s) — ein Knopf (`LIVE_FENSTER`) oder eingetippt
    fenster_s: int = 120
    #: Live-Verlauf: so weit reicht der Puffer zurück (s, `PUFFER_S`) — gilt ab der
    #: nächsten Verbindung (`devices.messlauf.Messlauf`)
    puffer_s: int = 1800
    #: Live die korrigierte Kurve (Artefakte überbrückt) statt der rohen
    korrigiert: bool = True
    #: Analysebereiche unter der Hauptkurve: Frequenz und Nichtlinear anbieten. Für
    #: Laien uninteressant — deshalb aus; wer es braucht, schaltet es ein.
    frequenz: bool = False
    nichtlinear: bool = False
    #: Nichtlineares auch bei optischen Pulsintervallen (Verity Sense) — nicht
    #: empfohlen: DFA und SampEn brauchen präzise Schlagzeiten
    nichtlinear_optisch: bool = False
    #: In Notizen zur Messung die Übungen aus Plänen zum Antippen anbieten
    notiz_uebungen: bool = True
    #: Notizliste: so viele Zeilen, dann rollt sie (`NOTIZEN_ZEILEN`; 0 = alle)
    notizen_zeilen: int = 7
    #: Zeitachse der Kurven mit der Uhrzeit beschriften statt mit der Dauer seit Beginn
    #: (Ben, 20.10.2026) — gilt live und in der Aufzeichnung, Knopf an der Breitenwahl
    achse_uhrzeit: bool = False
    #: Atemübung: auch langsames Atmen (unter 8/min) auswerten (`hrv_core.atmung`)
    atemuebung: bool = False
    #: Erweitert: Latenz vor dem Nachrechnen eines losgelassenen Analysefensters (ms)
    nachrechnen_ms: int = 500
    #: Erweitert: Live-Spektrum (und Poincaré) nur so oft neu rechnen (s)
    live_spektrum_s: int = 15
    #: Zuletzt gewählte Länge des verschiebbaren Analysefensters (s)
    analyse_laenge_s: int = 300
    #: Schrittweite der Pfeile am Analysefenster (`ANALYSE_SCHRITTE`)
    analyse_schritt: str = "halb"
    #: Eingeblendete Ebenen über der Kurve (`EBENEN`; Vorgabe alle)
    ebenen: list[str] = field(default_factory=lambda: list(EBENEN))
    #: Uhr am Handgelenk: Werte als Mediensteuerung senden (hrv-watch `flet_medien`,
    #: Ben, 26.10.2026) — für Bänder ohne eigene App wie die Galaxy Fit3
    uhr_medien: bool = False
    #: Welche Seiten die Uhr bekommt (`core.uhr_seiten.SEITEN`; „hf“ immer)
    uhr_seiten: list[str] = field(default_factory=lambda: list(UHR_SEITEN))

    def bereiche(self, *, optisch: bool) -> list[str]:
        """Welche Analysebereiche die Ansicht anbietet (Zeit immer)."""
        out = [BEREICH_ZEIT]
        if self.frequenz:
            out.append(BEREICH_FREQUENZ)
        if self.nichtlinear and (self.nichtlinear_optisch or not optisch):
            out.append(BEREICH_NICHTLINEAR)
        return out

    # -- Serialisierung --------------------------------------------------------

    def als_dict(self) -> dict[str, Any]:
        return {
            "messung_anzeigen": self.messung_anzeigen,
            "kacheln": list(self.kacheln),
            "gross": list(self.gross),
            "darstellung": self.darstellung,
            "fenster_s": self.fenster_s,
            "puffer_s": self.puffer_s,
            "korrigiert": self.korrigiert,
            "frequenz": self.frequenz,
            "nichtlinear": self.nichtlinear,
            "nichtlinear_optisch": self.nichtlinear_optisch,
            "notiz_uebungen": self.notiz_uebungen,
            "notizen_zeilen": self.notizen_zeilen,
            "achse_uhrzeit": self.achse_uhrzeit,
            "atemuebung": self.atemuebung,
            "nachrechnen_ms": self.nachrechnen_ms,
            "live_spektrum_s": self.live_spektrum_s,
            "analyse_laenge_s": self.analyse_laenge_s,
            "analyse_schritt": self.analyse_schritt,
            "ebenen": list(self.ebenen),
            "uhr_medien": self.uhr_medien,
            "uhr_seiten": list(self.uhr_seiten),
        }

    @classmethod
    def aus_dict(cls, d: Any) -> HrvEinstellungen:
        """Defensiv: Unbrauchbares fällt auf die Vorgabe zurück, nie eine Ausnahme."""
        vorgabe = cls()
        if not isinstance(d, dict):
            return vorgabe

        def schalter(name: str) -> bool:
            wert = d.get(name)
            return wert if isinstance(wert, bool) else getattr(vorgabe, name)

        def liste(name: str) -> list[str]:
            wert = d.get(name)
            if isinstance(wert, list) and all(isinstance(k, str) for k in wert):
                return list(dict.fromkeys(wert))
            return list(getattr(vorgabe, name))

        def auswahl(name: str, erlaubt: tuple[int, ...]) -> int:
            wert = d.get(name)
            if isinstance(wert, int) and not isinstance(wert, bool) and wert in erlaubt:
                return wert
            return int(getattr(vorgabe, name))

        kacheln = liste("kacheln")
        gross = liste("gross")
        darstellung = d.get("darstellung")
        fenster = d.get("fenster_s")
        puffer = auswahl("puffer_s", PUFFER_S)
        return cls(
            messung_anzeigen=schalter("messung_anzeigen"),
            kacheln=kacheln,
            gross=gross,
            darstellung=darstellung if darstellung in (UEBERSICHT, KACHELN) else UEBERSICHT,
            fenster_s=fenster
            if isinstance(fenster, int)
            and not isinstance(fenster, bool)
            and FENSTER_MIN_S <= fenster <= puffer
            else vorgabe.fenster_s,
            puffer_s=puffer,
            korrigiert=schalter("korrigiert"),
            frequenz=schalter("frequenz"),
            nichtlinear=schalter("nichtlinear"),
            nichtlinear_optisch=schalter("nichtlinear_optisch"),
            notiz_uebungen=schalter("notiz_uebungen"),
            notizen_zeilen=auswahl("notizen_zeilen", NOTIZEN_ZEILEN),
            achse_uhrzeit=schalter("achse_uhrzeit"),
            atemuebung=schalter("atemuebung"),
            nachrechnen_ms=auswahl("nachrechnen_ms", NACHRECHNEN_MS),
            live_spektrum_s=auswahl("live_spektrum_s", LIVE_SPEKTRUM_S),
            analyse_laenge_s=auswahl("analyse_laenge_s", ANALYSE_LAENGEN),
            analyse_schritt=schritt
            if (schritt := d.get("analyse_schritt")) in ANALYSE_SCHRITTE
            else vorgabe.analyse_schritt,
            ebenen=[k for k in liste("ebenen") if k in EBENEN],
            uhr_medien=schalter("uhr_medien"),
            uhr_seiten=[k for k in liste("uhr_seiten") if k in UHR_SEITEN],
        )


def einstellungen_lesen(text: str | None) -> HrvEinstellungen:
    try:
        return HrvEinstellungen.aus_dict(json.loads(text or ""))
    except (TypeError, ValueError):
        return HrvEinstellungen()


def einstellungen_schreiben(e: HrvEinstellungen) -> str:
    return json.dumps(e.als_dict(), ensure_ascii=False)


__all__ = [
    "ANALYSE_LAENGEN",
    "ANALYSE_SCHRITTE",
    "BEREICH_FREQUENZ",
    "BEREICH_NICHTLINEAR",
    "BEREICH_ZEIT",
    "FENSTER_MAX_S",
    "FENSTER_MIN_S",
    "KACHELN",
    "LIVE_FENSTER",
    "LIVE_SPEKTRUM_S",
    "NACHRECHNEN_MS",
    "PUFFER_S",
    "STANDARD_GROSS",
    "STANDARD_KACHELN",
    "UEBERSICHT",
    "HrvEinstellungen",
    "einstellungen_lesen",
    "einstellungen_schreiben",
]
