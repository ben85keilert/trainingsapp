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
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from trainingsapp.core.uhr_seiten import Uhrpaket, paket
from trainingsapp.devices.profiles import QUELLE_EKG_RR

#: So oft schaut der Kanal nach neuen Werten (s)
TAKT_S = 1.0
#: So oft rechnet er DFA α1 neu (s) — 200 Schläge, das lohnt keinen Sekundentakt
DFA_TAKT_S = 5.0

Zeilen = tuple[str, str, str]


class MedienKanal:
    """Hält die Session aktuell und nimmt die Tasten des Bands entgegen."""

    def __init__(self, state: Any, medien: Any) -> None:
        self.state = state
        #: Der Flet-Service (`flet_medien.FletMedien`) oder eine Attrappe mit
        #: ``starten``, ``zeigen``, ``beenden``
        self.medien = medien
        self.seite = 0
        self._gezeigt: Zeilen | None = None
        self._aktiv = False
        self._dfa: float | None = None
        self._dfa_zeit: float | None = None

    # -- Tasten ---------------------------------------------------------------

    def taste(self, name: str) -> None:
        """Eine Taste vom Band: ``weiter``/``zurueck`` blättern, ``play``/``pause`` markieren."""
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
            return False
        for beobachter in list(getattr(self.state, "notiz_beobachter", {}).values()):
            with contextlib.suppress(Exception):
                beobachter()
        return True

    # -- Werte ----------------------------------------------------------------

    def paket(self) -> Uhrpaket | None:
        """Das aktuelle Paket — ``None``, wenn nichts zu zeigen ist (aus, kein Gurt)."""
        lauf = self.state.messlauf
        if lauf is None or not lauf.verbunden:
            return None
        if not self.state.hrv_einstellungen().uhr_medien:
            return None
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

    async def schritt(self) -> None:
        """Ein Takt: Seite bauen, senden, wenn sie sich geändert hat; sonst beenden."""
        p = self.paket()
        if p is None:
            if self._aktiv:
                self._aktiv = False
                self._gezeigt = None
                await self.medien.beenden()
            return
        s = p.seiten[self.seite % len(p.seiten)]
        zeilen: Zeilen = (s.titel, s.zeile2, s.zeile3)
        if not self._aktiv:
            await self.medien.starten(*zeilen, laeuft=True)
            self._aktiv = True
        elif zeilen != self._gezeigt:
            await self.medien.zeigen(*zeilen)
        self._gezeigt = zeilen

    async def takt(self) -> None:
        """Jede Sekunde ein Schritt, solange die App lebt; Fehler stoppen die Messung nie."""
        while True:
            with contextlib.suppress(Exception):
                await self.schritt()
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


__all__ = ["TAKT_S", "MedienKanal", "anlegen"]
