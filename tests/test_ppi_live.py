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
from trainingsapp.hrv_core.regeln import Korrekturregeln
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

    def __init__(
        self,
        rr: list[int],
        profil: GeraeteProfil = VERITY_SENSE,
        seed: int = 4,
        blockiert: frozenset[int] = frozenset(),
    ) -> None:
        super().__init__()
        self._rr = rr
        self._blockiert = blockiert
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
            proben = [
                PpiProbe(70, x, 5, i + k in self._blockiert, True, True)
                for k, x in enumerate(buendel)
            ]
            paket, werte = ppi_messwerte("verity", proben, self._t)
            self._push_messwert(paket)
            for w in werte:
                self._push_messwert(w)


async def _live(
    rr: list[int],
    profil: GeraeteProfil = VERITY_SENSE,
    blockiert: frozenset[int] = frozenset(),
    regeln: Korrekturregeln | None = None,
) -> Messlauf:
    quelle = _VerityAttrappe(rr, profil, blockiert=blockiert)
    lauf = Messlauf(quelle, regeln=regeln)
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


@pytest.mark.asyncio
async def test_verworfene_intervalle_stehen_live_in_der_kurve() -> None:
    """Blocker bei Index 7 (mitten im Paket) und 9–11 (über die Paketgrenze bei 10).

    Vorher fehlten sie im Live-Fenster ganz; bei 44 % verworfenen Intervallen
    blieben von der Kurve nur Bruchstücke mit Zeitlücken dazwischen.
    """
    rr = _rr_reihe(40)
    lauf = await _live(rr, blockiert=frozenset({7, 9, 10, 11}), regeln=_SENSOR)
    punkte = lauf.live.punkte()
    assert [p.rr_ms for p in punkte] == rr
    assert [i for i, p in enumerate(punkte) if p.verworfen] == [7, 9, 10, 11]
    assert all(p.rr_korr is None and not p.artefakt for p in punkte if p.verworfen)
    # Die Zeit läuft mit den Intervallen weiter — auch über die verworfenen.
    abweichung = np.diff([p.t_s for p in punkte]) * 1000 - np.array(rr[1:])
    assert (np.abs(abweichung) > 100).sum() <= 2
    kz = lauf.live.kennzahlen()
    assert (kz.schlaege, kz.verworfen) == (36, 4)


_SENSOR = Korrekturregeln(sensor_verwerfung="sensor")


@pytest.mark.asyncio
async def test_verworfene_intervalle_werden_live_selbst_geprueft() -> None:
    """Vorgabe „selbst": Verworfenes zählt, wenn es die eigenen Prüfungen besteht."""
    rr = _rr_reihe(40)
    lauf = await _live(rr, blockiert=frozenset({7, 9, 10, 11}))
    punkte = lauf.live.punkte()
    assert [i for i, p in enumerate(punkte) if p.sensor_verworfen] == [7, 9, 10, 11]
    assert not any(p.verworfen or p.artefakt for p in punkte)
    assert all(p.rr_korr == p.rr_ms for p in punkte)
    kz = lauf.live.kennzahlen()
    assert (kz.schlaege, kz.verworfen) == (40, 4)
    # Umschalten wirkt sofort auf den ganzen Puffer
    lauf.regeln_setzen(_SENSOR)
    assert [i for i, p in enumerate(lauf.live.punkte()) if p.verworfen] == [7, 9, 10, 11]
    assert lauf.live.kennzahlen().schlaege == 36


def test_live_fehlerschaetzung_markiert_artefakt() -> None:
    from trainingsapp.hrv_core.live import LiveFenster

    f = LiveFenster()
    f.regeln_setzen(Korrekturregeln(), "ppg_ppi")
    for i in range(10):
        f.hinzufuegen(i * 0.8, 800 + (i % 2) * 10, 70, fehler_ms=120 if i == 4 else 10)
    assert [p.artefakt for p in f.punkte()] == [i == 4 for i in range(10)]
    f.regeln_setzen(Korrekturregeln(fehler_an=False), "ppg_ppi")
    assert not any(p.artefakt for p in f.punkte())


def test_live_kennzahlen_differenzieren_nicht_ueber_verworfene() -> None:
    from trainingsapp.hrv_core.live import LiveFenster
    from trainingsapp.hrv_core.time_domain import compute_time_domain

    f = LiveFenster()
    werte = [800, 820, 800, 820, 800, 1000, 1020, 1000, 1020, 1000]
    for i, rr in enumerate(werte):
        f.hinzufuegen(i * 0.9, rr, 70, verworfen=i == 5)
    kz = f.kennzahlen()
    erwartet = compute_time_domain([*werte[:5], None, *werte[6:]])
    assert erwartet is not None and kz.rmssd_30s == pytest.approx(erwartet["rmssd"])
    assert kz.rmssd_30s == pytest.approx(20.0)  # über den Verworfenen hinweg: 220 ms Sprung
    assert kz.rr_ms == 1000 and kz.verworfen == 1


def test_live_kennzahlen_differenzieren_nicht_ueber_die_naht() -> None:
    from trainingsapp.hrv_core.live import LiveFenster
    from trainingsapp.hrv_core.time_domain import compute_time_domain

    f = LiveFenster()
    werte = [800, 820, 800, 820, 800, 1000, 1020, 1000, 1020, 1000]
    for i, rr in enumerate(werte):
        if i == 5:
            f.naht()  # davor verwarf der Sensor Intervalle
        f.hinzufuegen(i * 0.9, rr, 70)
    kz = f.kennzahlen()
    erwartet = compute_time_domain(werte, breaks=[5])
    assert erwartet is not None and kz.rmssd_30s == pytest.approx(erwartet["rmssd"])
    assert kz.rmssd_30s == pytest.approx(20.0)  # ohne Naht: der 200-ms-Sprung zählte mit
    assert [p.naht_davor for p in f.punkte()] == [False] * 5 + [True] + [False] * 4
