"""Verity Sense live: Zeitachse gebündelter PPI-Pakete und Ausreißerschwelle.

Die Verity Sense schickt alle ~5 s rund fünf Intervalle, mit 0–1 s Streuung in
der Zustellung. Aus der Ankunft zurückgerechnet lag der erste Schlag eines
Pakets oft vor dem letzten des vorigen; das Live-Fenster schob ihn dann auf
1 ms dahinter — senkrechte Zacken in der Kurve. Dazu rechnete es mit der
EKG-Schwelle (0.20) statt der für optische Intervalle (0.30).
"""

from __future__ import annotations

import asyncio
import random

import numpy as np
import pytest

from trainingsapp.devices.base import DeviceInfo, HeartRateSource, Verbindung
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.devices.pmd import PpiProbe, ppi_messwerte
from trainingsapp.devices.profiles import POLAR_H10, VERITY_SENSE, GeraeteProfil
from trainingsapp.hrv_core.constants import MALIK_THRESHOLD_EKG, MALIK_THRESHOLD_PPI
from trainingsapp.hrv_core.zeitachse import NEU_ANKERN_S, Kontinuitaetsuhr


def _rr_reihe(n: int, seed: int = 1) -> list[int]:
    """Ruhepuls ~70 mit Atemmodulation (6/min) und etwas Rauschen."""
    zufall = random.Random(seed)
    t, rr = 0.0, []
    for _ in range(n):
        wert = 860 + 60 * np.sin(2 * np.pi * 0.1 * t) + zufall.gauss(0, 8)
        rr.append(round(float(wert)))
        t += wert / 1000
    return rr


class _VerityAttrappe(HeartRateSource):
    """Liefert PPI-Bündel wie die Verity Sense: ~5 Intervalle, Zustellung 0–1 s verspätet."""

    def __init__(self, rr: list[int], profil: GeraeteProfil = VERITY_SENSE, seed: int = 4) -> None:
        super().__init__()
        self._rr = rr
        self._profil = profil
        self._zufall = random.Random(seed)
        self._t = 0.0

    @property
    def profil(self) -> GeraeteProfil | None:
        return self._profil

    def jetzt(self) -> float:
        return self._t

    async def scan(self, timeout: float = 8.0) -> list[DeviceInfo]:
        return []

    async def connect(self, device_id: str, name: str | None = None) -> None:
        self._sitzung_beginnen()
        self._status_aendern(verbindung=Verbindung.VERBUNDEN)

    async def disconnect(self) -> None:
        self._status_aendern(verbindung=Verbindung.GETRENNT)
        self._ende_signalisieren()

    def alles_senden(self) -> None:
        herz = 3.0  # Algorithmus-Latenz des Geräts
        for i in range(0, len(self._rr), 5):
            buendel = self._rr[i : i + 5]
            herz += sum(buendel) / 1000
            self._t = herz + self._zufall.uniform(0.0, 1.0)
            proben = [PpiProbe(70, x, 5, False, True, True) for x in buendel]
            paket, werte = ppi_messwerte("verity", proben, self._t)
            self._push_messwert(paket)
            for w in werte:
                self._push_messwert(w)


async def _live(rr: list[int], profil: GeraeteProfil = VERITY_SENSE) -> Messlauf:
    quelle = _VerityAttrappe(rr, profil)
    lauf = Messlauf(quelle)
    await lauf.verbinden("verity", "Polar Sense TEST")
    quelle.alles_senden()
    await quelle.disconnect()
    await asyncio.wait_for(lauf.laufen(), 5)
    return lauf


@pytest.mark.asyncio
async def test_ppi_live_zeitachse_folgt_den_intervallen() -> None:
    rr = _rr_reihe(150)
    lauf = await _live(rr)
    punkte = lauf.live.punkte()
    assert [p.rr_ms for p in punkte] == rr
    abweichung = np.diff([p.t_s for p in punkte]) * 1000 - np.array(rr[1:])
    # Abstand zweier Punkte = Intervall des späteren Schlags. Nur solange sich
    # das Minimum der Zustellverzögerung noch einpendelt, darf eine Paketgrenze
    # danebenliegen — nie wird etwas zusammengeschoben.
    assert (np.abs(abweichung) > 100).sum() <= 2
    assert np.diff([p.t_s for p in punkte]).min() > 0.3


def test_ohne_uhr_verzerrt_die_ankunft_die_paketgrenzen() -> None:
    """Gegenprobe: Aus der Ankunft zurückgerechnet liegt fast jede Paketgrenze daneben."""
    from trainingsapp.devices.base import rr_auf_zeitachse

    zufall = random.Random(4)
    rr, herz, zeiten = _rr_reihe(150), 3.0, []
    for i in range(0, len(rr), 5):
        buendel = rr[i : i + 5]
        herz += sum(buendel) / 1000
        zeiten += [t for _, t, _ in rr_auf_zeitachse(buendel, herz + zufall.uniform(0.0, 1.0))]
    abweichung = np.diff(zeiten) * 1000 - np.array(rr[1:])
    assert (np.abs(abweichung) > 100).sum() > 10  # von 29 Paketgrenzen


@pytest.mark.asyncio
async def test_live_schwelle_nach_intervallquelle() -> None:
    assert (await _live(_rr_reihe(20))).live._malik == MALIK_THRESHOLD_PPI
    assert (await _live(_rr_reihe(20), POLAR_H10)).live._malik == MALIK_THRESHOLD_EKG


def test_uhr_verankert_nach_verlust_neu() -> None:
    uhr = Kontinuitaetsuhr()
    assert uhr.paket(5.0, [1000] * 5, [True] * 5)[-1] == (1000, 5.0)
    # 30 s Funkstille: Die Intervalle dazwischen fehlen in der Summe.
    zeiten = [t for _, t in uhr.paket(40.0, [1000] * 5, [True] * 5)]
    assert zeiten[-1] == pytest.approx(40.0)
    assert zeiten[0] - 5.0 > NEU_ANKERN_S  # die Lücke bleibt sichtbar
