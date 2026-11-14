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
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from trainingsapp.core.experimentell import DFA_LANG
from trainingsapp.core.uhr_seiten import SEITEN as UHR_SEITEN
from trainingsapp.core.uhr_seiten import SEITEN_VORGABE as UHR_SEITEN_VORGABE

#: Diagnosemodus (`docs/plan_diagnosemodus.md`): Form der Marken-Leiste — unten ein Drittel
#: (Vorgabe, P111) oder ein schwebender Knopf
DIAGNOSE_LEISTEN: Final[tuple[str, ...]] = ("unten", "knopf")
#: Beschleunigung des Polar H10: Raten (Hz) und Bereiche (g), die das Gerät kennt
ACC_RATEN: Final[tuple[int, ...]] = (25, 50, 100, 200)
ACC_BEREICHE: Final[tuple[int, ...]] = (2, 4, 8)

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
#: 26.10.2026: einstellbar, mindestens 30 min; 30.10.2026: bis 12 h, damit der lange
#: Knopfsatz 1·3·6 h auch live greift). Gilt ab der nächsten Verbindung.
PUFFER_S: Final[tuple[int, ...]] = (1800, 3600, 7200, 14400, 21600, 43200)
#: Notizen zur Messung: so viele Zeilen zeigt die Liste, mehr rollt sie (Ben, 27.10.2026:
#: „bei vielen Notizen ist es schwierig, die Notizen durchzuklicken und an der Kurve zu
#: beobachten“); 0 = alle, wie bisher
NOTIZEN_ZEILEN: Final[tuple[int, ...]] = (5, 7, 10, 15, 0)
#: Grenzen der von Hand gezogenen Höhe der Notizliste (px)
NOTIZEN_HOEHE_MIN_PX: Final[int] = 60
NOTIZEN_HOEHE_MAX_PX: Final[int] = 720
#: Eingetippte Breite der Zeitachse (Ben, 21.10.2026): mindestens 10 s, live höchstens
#: so viel, wie der Puffer hält (`HrvEinstellungen.puffer_s`)
FENSTER_MIN_S: Final[int] = 10
FENSTER_MAX_S: Final[int] = max(PUFFER_S)
#: Knöpfe der Zeitachse (s) — drei Sätze zur Wahl und ein eigener (Ben, 30.10.2026:
#: „kurz 1-2-10, mittel 2-5-15, lang 1-3-6 Std, eigene“)
BREITEN_KURZ: Final[str] = "kurz"
BREITEN_MITTEL: Final[str] = "mittel"
BREITEN_LANG: Final[str] = "lang"
BREITEN_EIGEN: Final[str] = "eigen"
BREITEN_SAETZE: Final[dict[str, tuple[int, ...]]] = {
    BREITEN_KURZ: (60, 120, 600),
    BREITEN_MITTEL: (120, 300, 900),
    BREITEN_LANG: (3600, 10800, 21600),
}
BREITEN_NAMEN: Final[dict[str, str]] = {
    BREITEN_KURZ: "Kurz",
    BREITEN_MITTEL: "Mittel",
    BREITEN_LANG: "Lang",
    BREITEN_EIGEN: "Eigene",
}
#: Die Herzfrequenz-Kurve: Mittel über so viele Sekunden (Ben, 30.10.2026: „In HF braucht
#: es Fenstereinstellungen für HF“)
HF_MITTEL_S: Final[tuple[int, ...]] = (1, 5, 10, 30, 60)
#: Standardwerte der festen Werteachsen (Ben, 30.10.2026: „vorgegebene Standardwerte, die den
#: ganzen Bereich abdecken von HF, RR usw., nachstellbar, aktivierbar und auf Standard wieder
#: herstellbar“). Schlüssel sind die Werteachsen der Kennzahlen (`hrv_core.trends`,
#: ``achse_schluessel``); die Bedeutung kennt die Oberfläche (`ACHSEN_NAMEN`).
ACHSEN_VORGABE: Final[dict[str, tuple[float, float]]] = {
    "bpm": (40.0, 200.0),
    "rr": (300.0, 1500.0),
    "var": (0.0, 200.0),
    "%": (0.0, 100.0),
    "permin": (0.0, 40.0),
    "rsa": (0.0, 40.0),
    "ms2": (0.0, 5000.0),
    "ratio": (0.0, 10.0),
    "alpha": (0.0, 2.0),
}
ACHSEN_NAMEN: Final[dict[str, tuple[str, str]]] = {
    "bpm": ("Herzfrequenz", "bpm"),
    "rr": ("RR bzw. PPI", "ms"),
    "var": ("Variabilität (RMSSD, SDNN, SD1, SD2)", "ms"),
    "%": ("pNNx", "%"),
    "permin": ("Atemfrequenz, Gipfel", "/min"),
    "rsa": ("Atemschwankung", "bpm"),
    "ms2": ("Spektrale Leistung (VLF, LF, HF)", "ms²"),
    "ratio": ("LF/HF", ""),
    "alpha": (DFA_LANG, ""),
}
#: Eigene Breiten: so viele höchstens, zwischen `FENSTER_MIN_S` und einem Tag (eine Nacht
#: braucht 6-h-Fenster; live begrenzt der Puffer ohnehin)
BREITEN_EIGEN_MAX: Final[int] = 5
BREITE_EIGEN_MAX_S: Final[int] = 86400

#: Ebenen über der Hauptkurve einer Aufzeichnung (Ben, 19.10.2026, Plan D): Notizen (gelb),
#: Leistungen der Person (blau, `person/leistung`), Abschnittsbalken — einzeln einblendbar
EBENE_NOTIZEN: Final[str] = "notizen"
EBENE_LEISTUNGEN: Final[str] = "leistungen"
EBENE_ABSCHNITTE: Final[str] = "abschnitte"
#: Einatmen schattiert und die Läufe „Atmung erfassen“ als Band — nur angeboten, wenn die
#: Messung ein Atem-Beiwerk hat (`docs/plan_beschleunigung.md` §7.3, B1)
EBENE_ATMUNG: Final[str] = "atmung"
EBENEN: Final[tuple[str, ...]] = (EBENE_NOTIZEN, EBENE_LEISTUNGEN, EBENE_ABSCHNITTE, EBENE_ATMUNG)
#: Die Ebenen, die es vor der Merkliste ``ebenen_bekannt`` gab (bis 0.3.46): Eine gespeicherte
#: Liste ohne Merkliste kannte nur diese — jede spätere Ebene ist dann an, wie bei einer
#: frischen Installation (fünfte Prüfrunde, C4)
EBENEN_ALT: Final[frozenset[str]] = frozenset({EBENE_NOTIZEN, EBENE_LEISTUNGEN, EBENE_ABSCHNITTE})

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

#: Die zwei Sichten der Hauptkarte (Ben, 29.10.2026, Entscheidung 10): Herzfrequenz oder HRV
SICHT_HF: Final[str] = "hf"
SICHT_HRV: Final[str] = "hrv"
SICHTEN: Final[tuple[str, ...]] = (SICHT_HF, SICHT_HRV)

#: Analysebereiche unter der Hauptkurve
BEREICH_ZEIT: Final[str] = "zeit"
BEREICH_FREQUENZ: Final[str] = "frequenz"
BEREICH_NICHTLINEAR: Final[str] = "nichtlinear"


def ebenen_lesen(d: Mapping[str, Any]) -> list[str]:
    """Die eingeblendeten Ebenen aus einer gespeicherten Einstellung: die gespeicherte Wahl
    (Unbekanntes fällt weg), dazu **an** jede Ebene, die es beim Speichern noch nicht gab —
    nach der Merkliste ``ebenen_bekannt``; fehlt sie, galten nur `EBENEN_ALT` als bekannt.
    Ohne gespeicherte Liste alle.

    >>> ebenen_lesen({})
    ['notizen', 'leistungen', 'abschnitte', 'atmung']
    >>> ebenen_lesen({"ebenen": ["notizen", "abschnitte"]})  # vor der Ebene „Atmung“ gespeichert
    ['notizen', 'abschnitte', 'atmung']
    >>> ebenen_lesen({"ebenen": ["notizen"], "ebenen_bekannt": list(EBENEN)})  # abgewählt
    ['notizen']
    >>> ebenen_lesen({"ebenen": ["notizen", "fremd"], "ebenen_bekannt": ["notizen", "fremd"]})
    ['notizen', 'leistungen', 'abschnitte', 'atmung']
    """
    gespeichert = d.get("ebenen")
    if not isinstance(gespeichert, list) or not all(isinstance(k, str) for k in gespeichert):
        return list(EBENEN)
    bekannt_roh = d.get("ebenen_bekannt")
    bekannt = (
        set(bekannt_roh)
        if isinstance(bekannt_roh, list) and all(isinstance(k, str) for k in bekannt_roh)
        else set(EBENEN_ALT)
    )
    ebenen = [k for k in dict.fromkeys(gespeichert) if k in EBENEN]
    return ebenen + [k for k in EBENEN if k not in bekannt and k not in ebenen]


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
    >>> HrvEinstellungen.aus_dict({"notizen_hoehe_px": 240, "poincare": False}).notizen_hoehe_px
    240
    >>> HrvEinstellungen.aus_dict({"notizen_hoehe_px": 5}).notizen_hoehe_px  # zu klein: Zeilen
    0
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
    #: Welcher Satz Breitenknöpfe an den Kurven steht (`BREITEN_SAETZE` oder `BREITEN_EIGEN`)
    breiten_satz: str = BREITEN_KURZ
    #: Die eigenen Breiten (s), aufsteigend — gelten bei `breiten_satz == BREITEN_EIGEN`
    breiten_eigen: list[int] = field(default_factory=list)
    #: Live die korrigierte Kurve (Artefakte überbrückt) statt der rohen
    korrigiert: bool = True
    #: Herzfrequenz-Sicht: alle Bereiche in der Kurve zeigen (die Werteachse reicht dann von
    #: der untersten bis zur obersten Grenze) statt nur die, die der Ausschnitt trifft
    hf_bereiche_alle: bool = False
    #: Herzfrequenz-Sicht: die Kurve ist ein Mittel über so viele Sekunden (`HF_MITTEL_S`)
    hf_mittel_s: int = 5
    #: Standardwerte der festen Werteachsen je Achsenschlüssel — die Vorgabe `ACHSEN_VORGABE`,
    #: unter Einstellungen → HRV-Messung → Kurven nachstellbar; im Blatt „Fenster &
    #: Darstellung“ schaltet man sie je Achse ein und stellt sie wieder her
    achsen_standard: dict[str, tuple[float, float]] = field(
        default_factory=lambda: dict(ACHSEN_VORGABE)
    )
    #: EKG-Rohsignal des Polar H10 mitschreiben (PMD, 130 Hz) — aus, bis die Person es
    #: einschaltet; nur gespeichert (Beiwerk ``_ecg.json``), nicht gerechnet (Ben, 30.10.2026)
    ekg_mitschreiben: bool = False
    #: Analysebereiche unter der Hauptkurve: Frequenz und Nichtlinear anbieten. Für
    #: Laien uninteressant — deshalb aus; wer es braucht, schaltet es ein.
    frequenz: bool = False
    nichtlinear: bool = False
    #: Nichtlineares auch bei optischen Pulsintervallen (Verity Sense) — nicht
    #: empfohlen: DFA und SampEn brauchen präzise Schlagzeiten
    nichtlinear_optisch: bool = False
    #: Bereich „Nichtlinear“: die Poincaré-Wolke über den Verlaufskurven zeigen — aus rückt
    #: sie näher an die Hauptkurve, SD1, SD2 und DFA α1 bleiben als Zeile (Ben, 10.11.2026, A21)
    poincare: bool = True
    #: In Notizen zur Messung die Übungen aus Plänen zum Antippen anbieten
    notiz_uebungen: bool = True
    #: Notizliste: so viele Zeilen, dann rollt sie (`NOTIZEN_ZEILEN`; 0 = alle)
    notizen_zeilen: int = 7
    #: Notizliste: von Hand gezogene Höhe in Pixeln (Griff unter der Liste, Ben 10.11.2026,
    #: A21) — 0 = nach `notizen_zeilen`; gilt live und in der Aufzeichnung
    notizen_hoehe_px: int = 0
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
    uhr_seiten: list[str] = field(default_factory=lambda: list(UHR_SEITEN_VORGABE))
    #: Welche Sicht die Hauptkarte öffnet (`SICHTEN`); Vorgabe Herzfrequenz
    standard_sicht: str = SICHT_HF
    #: Die zuletzt gewählte Sicht beim nächsten Öffnen wiederherstellen
    sicht_merken: bool = True
    #: Diagnosemodus anbieten (Ben, 4.11.2026): ein Knopf an der Gerätezeile, gestartet
    #: wird je Messung — Rohmitschnitt, Zusatzströme, Marken (`docs/plan_diagnosemodus.md`)
    diagnose_anbieten: bool = False
    #: Form der Marken-Leiste (`DIAGNOSE_LEISTEN`)
    diagnose_leiste: str = "unten"
    #: ⏯ an der Uhr setzt im Diagnosemodus Diagnosemarken
    diagnose_uhr: bool = True
    #: Zuletzt gewählte Ströme im Sensorblatt
    diagnose_ekg: bool = True
    diagnose_acc: bool = True
    diagnose_acc_hz: int = 200
    diagnose_acc_g: int = 8

    def breiten(self) -> tuple[int, ...]:
        """Die Breitenknöpfe (s) — eigene ohne Einträge fallen auf „kurz“ zurück.

        >>> HrvEinstellungen().breiten(), HrvEinstellungen(breiten_satz="mittel").breiten()
        ((60, 120, 600), (120, 300, 900))
        >>> HrvEinstellungen(breiten_satz="lang").breiten()
        (3600, 10800, 21600)
        >>> HrvEinstellungen(breiten_satz="eigen", breiten_eigen=[1800, 7200]).breiten()
        (1800, 7200)
        >>> HrvEinstellungen(breiten_satz="eigen").breiten()
        (60, 120, 600)
        """
        if self.breiten_satz == BREITEN_EIGEN and self.breiten_eigen:
            return tuple(self.breiten_eigen)
        return BREITEN_SAETZE.get(self.breiten_satz, BREITEN_SAETZE[BREITEN_KURZ])

    def achse_standard(self, achse: str) -> tuple[float, float] | None:
        """Der Standardbereich einer Werteachse — die eigene Einstellung, sonst die Vorgabe.

        >>> HrvEinstellungen().achse_standard("rr"), HrvEinstellungen().achse_standard("x")
        ((300.0, 1500.0), None)
        >>> HrvEinstellungen(achsen_standard={"rr": (500.0, 1200.0)}).achse_standard("rr")
        (500.0, 1200.0)
        """
        return self.achsen_standard.get(achse) or ACHSEN_VORGABE.get(achse)

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
            "breiten_satz": self.breiten_satz,
            "breiten_eigen": list(self.breiten_eigen),
            "korrigiert": self.korrigiert,
            "hf_bereiche_alle": self.hf_bereiche_alle,
            "hf_mittel_s": self.hf_mittel_s,
            "achsen_standard": {k: list(v) for k, v in self.achsen_standard.items()},
            "ekg_mitschreiben": self.ekg_mitschreiben,
            "frequenz": self.frequenz,
            "nichtlinear": self.nichtlinear,
            "nichtlinear_optisch": self.nichtlinear_optisch,
            "poincare": self.poincare,
            "notiz_uebungen": self.notiz_uebungen,
            "notizen_zeilen": self.notizen_zeilen,
            "notizen_hoehe_px": self.notizen_hoehe_px,
            "achse_uhrzeit": self.achse_uhrzeit,
            "atemuebung": self.atemuebung,
            "nachrechnen_ms": self.nachrechnen_ms,
            "live_spektrum_s": self.live_spektrum_s,
            "analyse_laenge_s": self.analyse_laenge_s,
            "analyse_schritt": self.analyse_schritt,
            "ebenen": list(self.ebenen),
            # Welche Ebenen diese Liste kannte — eine neue Ebene einer späteren Version
            # ist beim Lesen an, eine hier abgewählte bleibt aus (`ebenen_lesen`)
            "ebenen_bekannt": list(EBENEN),
            "uhr_medien": self.uhr_medien,
            "uhr_seiten": list(self.uhr_seiten),
            "standard_sicht": self.standard_sicht,
            "sicht_merken": self.sicht_merken,
            "diagnose_anbieten": self.diagnose_anbieten,
            "diagnose_leiste": self.diagnose_leiste,
            "diagnose_uhr": self.diagnose_uhr,
            "diagnose_ekg": self.diagnose_ekg,
            "diagnose_acc": self.diagnose_acc,
            "diagnose_acc_hz": self.diagnose_acc_hz,
            "diagnose_acc_g": self.diagnose_acc_g,
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
        satz = d.get("breiten_satz")
        eigen = breiten_pruefen(d.get("breiten_eigen"))
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
            breiten_satz=satz
            if satz in BREITEN_SAETZE or (satz == BREITEN_EIGEN and eigen)
            else vorgabe.breiten_satz,
            breiten_eigen=eigen,
            korrigiert=schalter("korrigiert"),
            hf_bereiche_alle=schalter("hf_bereiche_alle"),
            hf_mittel_s=auswahl("hf_mittel_s", HF_MITTEL_S),
            achsen_standard=achsen_pruefen(d.get("achsen_standard")),
            ekg_mitschreiben=schalter("ekg_mitschreiben"),
            frequenz=schalter("frequenz"),
            nichtlinear=schalter("nichtlinear"),
            nichtlinear_optisch=schalter("nichtlinear_optisch"),
            poincare=schalter("poincare"),
            notiz_uebungen=schalter("notiz_uebungen"),
            notizen_zeilen=auswahl("notizen_zeilen", NOTIZEN_ZEILEN),
            notizen_hoehe_px=hoehe
            if isinstance(hoehe := d.get("notizen_hoehe_px"), int)
            and not isinstance(hoehe, bool)
            and (hoehe == 0 or NOTIZEN_HOEHE_MIN_PX <= hoehe <= NOTIZEN_HOEHE_MAX_PX)
            else 0,
            achse_uhrzeit=schalter("achse_uhrzeit"),
            atemuebung=schalter("atemuebung"),
            nachrechnen_ms=auswahl("nachrechnen_ms", NACHRECHNEN_MS),
            live_spektrum_s=auswahl("live_spektrum_s", LIVE_SPEKTRUM_S),
            analyse_laenge_s=auswahl("analyse_laenge_s", ANALYSE_LAENGEN),
            analyse_schritt=schritt
            if (schritt := d.get("analyse_schritt")) in ANALYSE_SCHRITTE
            else vorgabe.analyse_schritt,
            ebenen=ebenen_lesen(d),
            uhr_medien=schalter("uhr_medien"),
            uhr_seiten=[k for k in liste("uhr_seiten") if k in UHR_SEITEN],
            standard_sicht=sicht
            if (sicht := d.get("standard_sicht")) in SICHTEN
            else vorgabe.standard_sicht,
            sicht_merken=schalter("sicht_merken"),
            diagnose_anbieten=schalter("diagnose_anbieten"),
            diagnose_leiste=leiste
            if (leiste := d.get("diagnose_leiste")) in DIAGNOSE_LEISTEN
            else vorgabe.diagnose_leiste,
            diagnose_uhr=schalter("diagnose_uhr"),
            diagnose_ekg=schalter("diagnose_ekg"),
            diagnose_acc=schalter("diagnose_acc"),
            diagnose_acc_hz=auswahl("diagnose_acc_hz", ACC_RATEN),
            diagnose_acc_g=auswahl("diagnose_acc_g", ACC_BEREICHE),
        )


def achsen_pruefen(roh: Any) -> dict[str, tuple[float, float]]:
    """Gespeicherte Standardwerte der Werteachsen — Unbrauchbares fällt auf die Vorgabe zurück.

    >>> achsen_pruefen({"rr": [500, 1200], "var": [9, 3], "x": [0, 1]})["rr"]
    (500.0, 1200.0)
    >>> achsen_pruefen({"var": [9, 3]})["var"], "x" in achsen_pruefen({"x": [0, 1]})
    ((0.0, 200.0), False)
    >>> achsen_pruefen("kaputt") == ACHSEN_VORGABE
    True
    """
    out = dict(ACHSEN_VORGABE)
    if not isinstance(roh, dict):
        return out
    for k, v in roh.items():
        if k not in ACHSEN_VORGABE or not isinstance(v, list | tuple) or len(v) != 2:
            continue
        lo, hi = v
        zahlen = all(isinstance(x, int | float) and not isinstance(x, bool) for x in (lo, hi))
        if zahlen and lo < hi:
            out[k] = (float(lo), float(hi))
    return out


def breiten_pruefen(werte: Any) -> list[int]:
    """Eigene Breiten bereinigen: ganze Sekunden im erlaubten Bereich, aufsteigend, ohne
    Doppelte, höchstens `BREITEN_EIGEN_MAX` — Unbrauchbares fällt weg.

    >>> breiten_pruefen([600, 120.0, "x", 120, 5, 99999, 7200])
    [120, 600, 7200]
    >>> breiten_pruefen("kaputt"), breiten_pruefen(None)
    ([], [])
    """
    if not isinstance(werte, list | tuple):
        return []
    out: set[int] = set()
    for w in werte:
        if isinstance(w, bool) or not isinstance(w, int | float):
            continue
        sek = round(w)
        if FENSTER_MIN_S <= sek <= BREITE_EIGEN_MAX_S:
            out.add(sek)
    return sorted(out)[:BREITEN_EIGEN_MAX]


def einstellungen_lesen(text: str | None) -> HrvEinstellungen:
    try:
        return HrvEinstellungen.aus_dict(json.loads(text or ""))
    except (TypeError, ValueError):
        return HrvEinstellungen()


def einstellungen_schreiben(e: HrvEinstellungen) -> str:
    return json.dumps(e.als_dict(), ensure_ascii=False)


__all__ = [
    "ACC_BEREICHE",
    "ACC_RATEN",
    "ACHSEN_NAMEN",
    "ACHSEN_VORGABE",
    "ANALYSE_LAENGEN",
    "ANALYSE_SCHRITTE",
    "BEREICH_FREQUENZ",
    "BEREICH_NICHTLINEAR",
    "BEREICH_ZEIT",
    "BREITEN_EIGEN",
    "BREITEN_EIGEN_MAX",
    "BREITEN_KURZ",
    "BREITEN_LANG",
    "BREITEN_MITTEL",
    "BREITEN_NAMEN",
    "BREITEN_SAETZE",
    "BREITE_EIGEN_MAX_S",
    "FENSTER_MAX_S",
    "FENSTER_MIN_S",
    "HF_MITTEL_S",
    "KACHELN",
    "LIVE_FENSTER",
    "LIVE_SPEKTRUM_S",
    "NACHRECHNEN_MS",
    "NOTIZEN_HOEHE_MAX_PX",
    "NOTIZEN_HOEHE_MIN_PX",
    "PUFFER_S",
    "SICHTEN",
    "SICHT_HF",
    "SICHT_HRV",
    "STANDARD_GROSS",
    "STANDARD_KACHELN",
    "UEBERSICHT",
    "HrvEinstellungen",
    "achsen_pruefen",
    "breiten_pruefen",
    "einstellungen_lesen",
    "einstellungen_schreiben",
]
