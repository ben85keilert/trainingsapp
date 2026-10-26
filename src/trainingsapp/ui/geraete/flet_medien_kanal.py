"""Uhr am Handgelenk über die Mediensteuerung — hrv-watch `flet_medien` (Ben, 26.10.2026).

Solange ein Gurt verbunden ist und die Einstellung „Uhr am Handgelenk“ an ist,
stehen die Seiten aus `core.uhr_seiten` als Titel, Interpret und Album in einer
`MediaSession`; Galaxy Wearable reicht sie an die Galaxy Fit3 weiter. Jede Sekunde
ein Blick (`takt`), gesendet wird nur, was sich geändert hat — jede Änderung setzt
am Band die Laufschrift zurück. Welche Seiten, sagt `HrvEinstellungen.uhr_seiten`.

Tasten vom Band: ▶ ◀ blättern. ⏯ tut, was die Seite sagt (`TASTE_JE_SEITE`,
hrv-watch ENTSCHEIDUNGEN #7): auf HF, Atmung und Training eine Marke (Notiz ohne
Text) in die laufende Aufnahme; auf der Intervallseite beginnen Gipfel und Tal neu;
auf der HRR-Seite ist jetzt das Ende der Belastung (Notiz „HRR“, dann HRR30/60).
**Nie** startet oder stoppt ⏯ die Aufnahme (Ben, 26.10.2026). Die Session meldet
immer PLAYING; so schickt das Band bei ⏯ zuverlässig „pause“.

Kein Rechnen hier: Kennzahlen kommen aus `hrv_core.live`, die Seiten aus
`core.uhr_seiten`. DFA α1 (`LiveFenster.dfa_a1`, 200 Schläge) und Atemfrequenz
(`LiveFenster.atemfrequenz`, 60 s, Modus Atemübung) alle 5 s; α1 nur bei EKG-Gurten
— bei optischen Pulsintervallen ist es unter Belastung nicht validiert. Timer und
Tempo kommen aus `state.timer` bzw. der laufenden Einheit und `state.ausdauer`.

**Gurt-Warnung:** der Messlauf führt eine `Artefaktwache`; jeden neuen Alarm schickt
der Kanal als Benachrichtigung (`warnen`, das Band vibriert), und Zeile 3 zeigt die
Warnung, solange sie gilt.

Nur in der gebauten Android-App (`anlegen`); die Logik (`MedienKanal`) ist mit einer
Attrappe des Dienstes ohne Bildschirm testbar. **Diagnose:** `zustand` sagt in einem
Satz, was der Kanal tut oder warum nicht; `protokoll` hält die letzten Schritte und
Fehler; `test` schickt eine feste Seite auch ohne Gurt. Beides zeigt die
Einstellungsseite.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from datetime import datetime
from typing import Any

from trainingsapp.core.uhr_seiten import (
    SEITE_HF,
    SEITEN,
    TASTE_HRR,
    TASTE_JE_SEITE,
    TASTE_MARKE,
    TASTE_NEU,
    Seite,
    Training,
    Uhrpaket,
    paket,
)
from trainingsapp.devices.profiles import QUELLE_EKG_RR

log = logging.getLogger(__name__)

#: So oft schaut der Kanal nach neuen Werten (s)
TAKT_S = 1.0
#: So oft rechnet er DFA α1 und Atemfrequenz neu (s) — das lohnt keinen Sekundentakt
RECHEN_TAKT_S = 5.0
#: So lange bleibt die Testseite stehen (s)
TEST_S = 60.0
#: Die Testseite — drei Zeilen, die am Band sofort als solche erkennbar sind
TESTSEITE = ("Test 123", "hrv-watch", "Uhr")
#: Darunter gilt das GPS-Tempo als Stand (m/s)
STAND_MS = 0.3

Zeilen = tuple[str, str, str]


class MedienKanal:
    """Hält die Session aktuell und nimmt die Tasten des Bands entgegen."""

    def __init__(self, state: Any, medien: Any, uhr: Any = time.monotonic) -> None:
        self.state = state
        #: Der Flet-Service (`flet_medien.FletMedien`) oder eine Attrappe mit
        #: ``starten``, ``zeigen``, ``beenden``, ``warnen``
        self.medien = medien
        self._uhr = uhr
        self.seite = 0
        self._seiten: list[Seite] = []
        self._gezeigt: Zeilen | None = None
        self._aktiv = False
        self._lauf: Any = None
        self._dfa: float | None = None
        self._atmung: float | None = None
        self._rechen_zeit: float | None = None
        #: Gipfel und Tal ab hier (⏯ auf der Intervallseite)
        self.seit_s: float | None = None
        #: Ende der Belastung (⏯ auf der HRR-Seite)
        self.hrr_t0_s: float | None = None
        self._alarme_gesehen = 0
        self._test_bis: float | None = None
        #: Was der Kanal gerade tut — für die Einstellungsseite
        self.zustand = "noch kein Takt"
        #: Die letzten Schritte und Fehler, neueste zuletzt
        self.protokoll: deque[str] = deque(maxlen=30)

    def _log(self, text: str) -> None:
        self.protokoll.append(f"{datetime.now():%H:%M:%S} {text}")

    # -- Tasten ---------------------------------------------------------------

    def aktuelle_art(self) -> str:
        """Welche Seite gerade steht (`core.uhr_seiten.SEITEN`)."""
        if not self._seiten:
            return SEITE_HF
        return self._seiten[self.seite % len(self._seiten)].art

    def taste(self, name: str) -> None:
        """Eine Taste vom Band: ``weiter``/``zurueck`` blättern, ``play``/``pause`` tun,
        was die Seite sagt."""
        self._log(f"Taste {name} auf {self.aktuelle_art()}")
        if name == "weiter":
            self.seite += 1
        elif name == "zurueck":
            self.seite -= 1
        elif name in ("play", "pause"):
            self._taste_der_seite()
        # "stop": nichts — die Aufnahme bleibt, wie sie ist

    def _taste_der_seite(self) -> None:
        was = TASTE_JE_SEITE.get(self.aktuelle_art(), TASTE_MARKE)
        lauf = self.state.messlauf
        if was == TASTE_NEU:
            self.seit_s = None if lauf is None else lauf.jetzt_s()
            self._log("Gipfel und Tal neu ab jetzt")
        elif was == TASTE_HRR:
            self.hrr_t0_s = None if lauf is None else lauf.jetzt_s()
            self._log("Ende der Belastung — HRR läuft")
            self.marke("HRR")
        else:
            self.marke()

    def marke(self, text: str = "") -> bool:
        """Eine Notiz an „jetzt“ (ohne Text: eine Marke) — ``False`` ohne laufende Aufnahme."""
        lauf = self.state.messlauf
        if lauf is None or lauf.notiz_hinzufuegen(text) is None:
            self._log("Marke: keine laufende Aufnahme")
            return False
        self._log("Marke gesetzt" if not text else f"Notiz „{text}“ gesetzt")
        for beobachter in list(getattr(self.state, "notiz_beobachter", {}).values()):
            with contextlib.suppress(Exception):
                beobachter()
        return True

    # -- Werte ----------------------------------------------------------------

    def _einstellung(self) -> Any:
        return self.state.hrv_einstellungen()

    def _grund(self) -> str | None:
        """Warum gerade nichts zu zeigen ist — ``None``: es gibt etwas zu zeigen."""
        if not self._einstellung().uhr_medien:
            return "aus (Einstellung)"
        lauf = self.state.messlauf
        if lauf is None:
            return "kein Gurt gewählt (Messung → Verbinden)"
        if not lauf.verbunden:
            return "Gurt nicht verbunden"
        return None

    def paket(self) -> Uhrpaket | None:
        """Das aktuelle Paket — ``None``, wenn nichts zu zeigen ist (aus, kein Gurt)."""
        if self._grund() is not None:
            return None
        lauf = self.state.messlauf
        if lauf is not self._lauf:  # neue Messung: ihre Uhr beginnt bei null
            self._lauf = lauf
            self.seit_s = self.hrr_t0_s = self._rechen_zeit = None
        jetzt_s = lauf.jetzt_s()  # Methode am Messlauf — nicht Attribut (Fehler in 0.3.18)
        aufnahme_s = lauf.aufnahme_dauer_s() if lauf.aufnahme is not None else None
        dfa_moeglich = self._dfa_moeglich(lauf)
        if self._rechen_zeit is None or jetzt_s - self._rechen_zeit >= RECHEN_TAKT_S:
            self._dfa = self._rechnen(lauf, "dfa_a1") if dfa_moeglich else None
            self._atmung = self._rechnen(lauf, "atemfrequenz")
            self._rechen_zeit = jetzt_s
        auswahl = getattr(self._einstellung(), "uhr_seiten", None)
        return paket(
            lauf.live.kennzahlen(),
            lauf.live.hf_reihe(),
            jetzt_s,
            auswahl=SEITEN if auswahl is None else auswahl,
            seit_s=self.seit_s,
            hrr_t0_s=self.hrr_t0_s,
            aufnahme_s=aufnahme_s,
            dfa_a1=self._dfa,
            dfa_moeglich=dfa_moeglich,
            atmung=self._atmung,
            training=training_aus(self.state),
            warnung=getattr(lauf, "warnung", None),
        )

    @staticmethod
    def _dfa_moeglich(lauf: Any) -> bool:
        """DFA α1 nur bei EKG-Gurten — bei optischen Sensoren fehlt der Platz dafür."""
        profil = getattr(lauf, "profil", None)
        return profil is None or profil.intervall_quelle == QUELLE_EKG_RR

    @staticmethod
    def _rechnen(lauf: Any, name: str) -> float | None:
        """``lauf.live.<name>()`` — ``None``, wenn hrv-core es nicht kennt oder es scheitert."""
        rechnen = getattr(lauf.live, name, None)  # hrv-core ab 26.10.2026
        if rechnen is None:
            return None
        with contextlib.suppress(Exception):
            return rechnen()
        return None

    async def test(self) -> None:
        """Die Testseite für `TEST_S` Sekunden zeigen — auch ohne Gurt und ohne Einstellung."""
        self._test_bis = self._uhr() + TEST_S
        try:
            await self.medien.starten(*TESTSEITE, laeuft=True)
        except Exception as e:
            self._aktiv = False
            self._test_bis = None
            self.zustand = f"Test fehlgeschlagen: {type(e).__name__}: {e}"
            self._log(self.zustand)
            log.warning("Uhr: %s", self.zustand)
            return
        self._aktiv = True
        self._gezeigt = TESTSEITE
        self.zustand = "Testseite gesendet"
        self._log(self.zustand)

    async def _warnung_weiterreichen(self) -> None:
        """Jeden neuen Alarm der Artefaktwache als Benachrichtigung ans Band."""
        lauf = self.state.messlauf
        wache = getattr(lauf, "artefaktwache", None)
        if wache is None or wache.alarme == self._alarme_gesehen:
            return
        self._alarme_gesehen = wache.alarme
        if not self._einstellung().uhr_medien:
            return
        text = wache.text or "zu viele Artefakte"
        await self.medien.warnen("Gurt prüfen", text.removeprefix("Gurt prüfen: "))
        self._log(f"Warnung gesendet: {text}")

    async def schritt(self) -> None:
        """Ein Takt: Seite bauen, senden, wenn sie sich geändert hat; sonst beenden."""
        await self._warnung_weiterreichen()
        if self._test_bis is not None:
            if self._uhr() < self._test_bis:
                return  # die Testseite steht
            self._test_bis = None
        p = self.paket()
        if p is None:
            grund = self._grund() or "nichts zu zeigen"
            if self._aktiv:
                self._aktiv = False
                self._gezeigt = None
                await self.medien.beenden()
                self._log(f"beendet: {grund}")
            self.zustand = grund
            return
        self._seiten = p.seiten
        s = p.seiten[self.seite % len(p.seiten)]
        zeilen: Zeilen = (s.titel, s.zeile2, s.zeile3)
        if not self._aktiv:
            await self.medien.starten(*zeilen, laeuft=True)
            self._aktiv = True
            self._log(f"gestartet: {' | '.join(zeilen)}")
        elif zeilen != self._gezeigt:
            await self.medien.zeigen(*zeilen)
        self._gezeigt = zeilen
        self.zustand = f"sendet Seite {self.seite % len(p.seiten) + 1}: {' | '.join(zeilen)}"

    async def takt(self) -> None:
        """Jede Sekunde ein Schritt, solange die App lebt; Fehler stoppen die Messung nie."""
        while True:
            try:
                await self.schritt()
            except Exception as e:
                self.zustand = f"Fehler: {type(e).__name__}: {e}"
                self._log(self.zustand)
                log.warning("Uhr: %s", self.zustand)
                self._aktiv = False
                self._gezeigt = None
            await asyncio.sleep(TAKT_S - (time.monotonic() % TAKT_S))


def _timer_lauf(state: Any) -> Any:
    """Der Timer, der gerade läuft: der der Einheit, sonst der für sich gestartete."""
    e = getattr(state, "einheit", None)
    if e is not None and getattr(e, "laeuft", False) and getattr(e, "timer", None) is not None:
        return e.timer.lauf
    t = getattr(state, "timer", None)
    return t if t is not None and t.begonnen else None


def training_aus(state: Any) -> Training:
    """Timer-Abschnitt mit Rest und GPS-Tempo mit Strecke aus dem App-Zustand."""
    abschnitt = rest = None
    t = _timer_lauf(state)
    if t is not None and not t.fertig and not getattr(t, "abgebrochen", False):
        s = t.stand()
        if t.vorwaerts:
            abschnitt = t.profil.anzeigename
        else:
            abschnitt = s.name or f"Abschnitt {s.index + 1}"
            if getattr(s, "runden", 1) > 1:
                abschnitt += f" {s.runde}/{s.runden}"
            rest = s.rest_s
    tempo = distanz = None
    a = getattr(state, "ausdauer", None)
    rechner = getattr(a, "rechner", None)
    if rechner is not None and not getattr(a, "fertig", False):
        v = rechner.aktuelles_tempo_ms()
        tempo = 1000.0 / v if v is not None and v >= STAND_MS else None
        distanz = rechner.distanz_m
    return Training(abschnitt, rest, tempo, distanz)


def anlegen(page: Any, state: Any) -> MedienKanal | None:
    """Der Kanal in der gebauten Android-App — sonst ``None``.

    Legt den Flet-Service an und hängt ihn an die Seite; der Kanal hält die starke
    Referenz (sonst räumt Flet den Dienst ab).
    """
    import flet_medien  # nur hier — die Erweiterung gibt es nur im App-Build

    if not flet_medien.verfuegbar(page):
        return None
    kanal: MedienKanal | None = None

    def taste(e: Any) -> None:
        if kanal is not None:
            kanal.taste(str(getattr(e, "taste", "")))

    medien = flet_medien.FletMedien(on_taste=taste)
    page.services.append(medien)
    kanal = MedienKanal(state, medien)
    return kanal


__all__ = [
    "RECHEN_TAKT_S",
    "TAKT_S",
    "TESTSEITE",
    "TEST_S",
    "MedienKanal",
    "anlegen",
    "training_aus",
]
