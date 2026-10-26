"""Uhr am Handgelenk über die Mediensteuerung — hrv-watch `flet_medien` (Ben, 26.10.2026).

Solange ein Gurt verbunden ist und die Einstellung „Uhr: Mediensteuerung“ an ist,
stehen die Seiten aus `core.uhr_seiten` (HF, RMSSD, Intervall-Kennzahlen) als
Titel, Interpret und Album in einer `MediaSession`; Galaxy Wearable reicht sie an
die Galaxy Fit3 weiter. Jede Sekunde ein Blick (`takt`), gesendet wird nur, was
sich geändert hat — jede Änderung setzt am Band die Laufschrift zurück.

Tasten vom Band: ▶ ◀ blättern die Seiten, ⏯ setzt eine Marke (Notiz ohne Text) in
die laufende Aufnahme — **nie** startet oder stoppt es die Aufnahme (Ben, 26.10.2026).
Die Session meldet immer PLAYING; so schickt das Band bei ⏯ zuverlässig „pause“,
und jeder Druck ist eine Marke.

Kein Rechnen hier: Kennzahlen kommen aus `hrv_core.live`, die Seiten aus
`core.uhr_seiten`. DFA α1 (`LiveFenster.dfa_a1`, 200 Schläge) alle 5 s, nur bei
EKG-Gurten — bei optischen Pulsintervallen ist α1 unter Belastung nicht validiert
(wie `core.hrv_training`). Nur in der gebauten Android-App (`anlegen`); die Logik
(`MedienKanal`) ist mit einer Attrappe des Dienstes ohne Bildschirm testbar.

**Diagnose** (26.10.2026, erster Test ohne Werte am Band): `zustand` sagt in einem
Satz, was der Kanal gerade tut oder warum nicht; `protokoll` hält die letzten
Schritte und Fehler; `test` schickt eine feste Seite auch ohne Gurt, damit sich der
Kanal unabhängig von der Messung prüfen lässt. Beides zeigt die Einstellungsseite.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from datetime import datetime
from typing import Any

from trainingsapp.core.uhr_seiten import Uhrpaket, paket
from trainingsapp.devices.profiles import QUELLE_EKG_RR

log = logging.getLogger(__name__)

#: So oft schaut der Kanal nach neuen Werten (s)
TAKT_S = 1.0
#: So oft rechnet er DFA α1 neu (s) — 200 Schläge, das lohnt keinen Sekundentakt
DFA_TAKT_S = 5.0
#: So lange bleibt die Testseite stehen (s)
TEST_S = 60.0
#: Die Testseite — drei Zeilen, die am Band sofort als solche erkennbar sind
TESTSEITE = ("Test 123", "hrv-watch", "Uhr")

Zeilen = tuple[str, str, str]


class MedienKanal:
    """Hält die Session aktuell und nimmt die Tasten des Bands entgegen."""

    def __init__(self, state: Any, medien: Any, uhr: Any = time.monotonic) -> None:
        self.state = state
        #: Der Flet-Service (`flet_medien.FletMedien`) oder eine Attrappe mit
        #: ``starten``, ``zeigen``, ``beenden``
        self.medien = medien
        self._uhr = uhr
        self.seite = 0
        self._gezeigt: Zeilen | None = None
        self._aktiv = False
        self._dfa: float | None = None
        self._dfa_zeit: float | None = None
        self._test_bis: float | None = None
        #: Was der Kanal gerade tut — für die Einstellungsseite
        self.zustand = "noch kein Takt"
        #: Die letzten Schritte und Fehler, neueste zuletzt
        self.protokoll: deque[str] = deque(maxlen=30)

    def _log(self, text: str) -> None:
        self.protokoll.append(f"{datetime.now():%H:%M:%S} {text}")

    # -- Tasten ---------------------------------------------------------------

    def taste(self, name: str) -> None:
        """Eine Taste vom Band: ``weiter``/``zurueck`` blättern, ``play``/``pause`` markieren."""
        self._log(f"Taste {name}")
        if name == "weiter":
            self.seite += 1
        elif name == "zurueck":
            self.seite -= 1
        elif name in ("play", "pause"):
            self.marke()
        # "stop": nichts — die Aufnahme bleibt, wie sie ist

    def marke(self) -> bool:
        """Eine Notiz ohne Text an „jetzt“ — ``False`` ohne laufende Aufnahme."""
        lauf = self.state.messlauf
        if lauf is None or lauf.notiz_hinzufuegen("") is None:
            self._log("Marke: keine laufende Aufnahme")
            return False
        self._log("Marke gesetzt")
        for beobachter in list(getattr(self.state, "notiz_beobachter", {}).values()):
            with contextlib.suppress(Exception):
                beobachter()
        return True

    # -- Werte ----------------------------------------------------------------

    def _grund(self) -> str | None:
        """Warum gerade nichts zu zeigen ist — ``None``: es gibt etwas zu zeigen."""
        if not self.state.hrv_einstellungen().uhr_medien:
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
        aufnahme_s = lauf.aufnahme_dauer_s() if lauf.aufnahme is not None else None
        if self._dfa_zeit is None or lauf.jetzt_s - self._dfa_zeit >= DFA_TAKT_S:
            self._dfa = self._dfa_live(lauf)
            self._dfa_zeit = lauf.jetzt_s
        return paket(
            lauf.live.kennzahlen(),
            lauf.live.hf_reihe(),
            lauf.jetzt_s,
            aufnahme_s=aufnahme_s,
            dfa_a1=self._dfa,
        )

    @staticmethod
    def _dfa_live(lauf: Any) -> float | None:
        """DFA α1 der letzten 200 guten Schläge — ``None`` bei optischen Sensoren."""
        profil = getattr(lauf, "profil", None)
        if profil is not None and profil.intervall_quelle != QUELLE_EKG_RR:
            return None
        rechnen = getattr(lauf.live, "dfa_a1", None)  # hrv-core ab 26.10.2026
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

    async def schritt(self) -> None:
        """Ein Takt: Seite bauen, senden, wenn sie sich geändert hat; sonst beenden."""
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


__all__ = ["TAKT_S", "TESTSEITE", "TEST_S", "MedienKanal", "anlegen"]
