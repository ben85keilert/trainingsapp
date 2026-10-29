"""Live-Akkumulatoren der Herzfrequenz (`core/hf_training.py`, Ben 29.10.2026): dieselben
Zahlen wie `hrv_core.herzfrequenz.zusammenfassung` auf denselben Schlägen; Bezüge Aufnahme,
Abschnitt, 5 min."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from hrv_core import herzfrequenz as hz
from hrv_core.recording import Beat

from trainingsapp.core.hf_einstellungen import HfEinstellungen
from trainingsapp.core.hf_profil import Profilwert, bereiche_fuer, grenzen_bpm, hf_profil
from trainingsapp.core.hf_training import (
    BEZUG_ABSCHNITT,
    BEZUG_AUFNAHME,
    HfAkkumulator,
    LiveHf,
    akkumulator_fuer,
    fenster_zusammenfassung,
    hf_je_schlag,
)
from trainingsapp.core.models import Subject

HEUTE = date(2026, 10, 29)


def _profil():
    s = Subject(name="Ich", birth_year=1986, geschlecht="w")
    e = [
        Profilwert(s.id, "ruhe_hf", 60, "eintrag", date(2026, 10, 1)),
        Profilwert(s.id, "hf_max", 180, "ergometrie", date(2026, 10, 1)),
    ]
    return hf_profil(e, s, HEUTE)


def _beats(n: int = 600, seed: int = 2) -> list[Beat]:
    """Schläge mit wechselnder HF (80 → 160 → 100), Zeiten aus den RR, ab und zu ohne RR."""
    zufall = np.random.default_rng(seed)
    beats: list[Beat] = []
    t = 0.3
    for i in range(n):
        hf = 80.0 if i < 200 else 160.0 if i < 400 else 100.0
        rr = round(60000 / (hf + zufall.normal(0, 2)))
        if i % 50 == 7:  # Paket ohne RR: nur Geräte-HF
            beats.append(Beat(0.0, 0, int(hf), round(t, 3)))
        else:
            beats.append(Beat(0.0, rr, int(hf), round(t, 3)))
        t += rr / 1000
    return beats


def test_hf_je_schlag_und_leerer_akkumulator() -> None:
    assert hf_je_schlag(800, 75) == 75.0
    a = HfAkkumulator()
    assert a.zusammenfassung()["mittel_bpm"] is None and a.sekunden == [0.0]
    a.schlag(0.5, 0, 0)  # nichts Brauchbares
    assert a.n == 0 and a.letzte_hf is None


def test_akkumulator_wie_hrv_core_auf_denselben_schlaegen() -> None:
    profil = _profil()
    grenzen = grenzen_bpm(bereiche_fuer(profil, HfEinstellungen(modell="drei")))
    beats = _beats()
    akk = akkumulator_fuer(profil, grenzen)
    akk.beats(beats)
    akk._abschliessen()  # die letzte angefangene Sekunde zählt im Test mit
    t = np.asarray([b.t_wall_s for b in beats])
    reihe = hz.hf_reihe(t, [b.rr_ms for b in beats], [b.hf_bpm for b in beats], luecke_s=0.0)
    soll = hz.zusammenfassung(reihe, ruhe=60, hfmax=180, grenzen_bpm=grenzen, geschlecht="w")
    ist = akk.zusammenfassung()
    assert ist["gueltig_s"] == soll["gueltig_s"]
    assert ist["sekunden_je_bereich"] == soll["sekunden_je_bereich"]
    assert ist["mittel_bpm"] == pytest.approx(soll["mittel_bpm"])
    assert ist["mittel_prozent"] == pytest.approx(soll["mittel_prozent"])
    assert ist["trimp"] == pytest.approx(soll["trimp"])
    assert ist["minimum_bpm"] == pytest.approx(soll["minimum_bpm"])
    assert ist["gipfel_bpm"] == pytest.approx(soll["gipfel_bpm"])
    assert sum(ist["sekunden_je_bereich"]) == ist["gueltig_s"]


def test_akkumulator_ohne_profil_zaehlt_nur_bereiche() -> None:
    a = HfAkkumulator(grenzen_bpm=[110.0])
    for i in range(10):
        a.schlag(i + 0.5, 500, 0)  # 120 bpm
    a._abschliessen()
    assert a.sekunden == [0.0, 10.0] and a.trimp is None and a.mittel_prozent is None
    assert a.mittel_bpm == 120.0


def test_live_hf_bezuege_aufnahme_und_abschnitt() -> None:
    profil = _profil()
    grenzen = grenzen_bpm(bereiche_fuer(profil, HfEinstellungen(modell="drei")))
    beats = _beats()
    live = LiveHf(profil, grenzen)
    live.nachfuehren(beats[:300])
    assert live.fuer(BEZUG_ABSCHNITT) is None
    n_aufnahme = live.aufnahme.n
    # Abschnitt beginnt bei der 200. Sekunde — rückwirkend aus den Schlägen gebaut
    von = float(beats[200].t_wall_s)
    live.abschnitt_setzen("seg-1", von, beats[:300])
    ab = live.fuer(BEZUG_ABSCHNITT)
    assert ab is not None and 0 < ab.n < n_aufnahme and ab.mittel_bpm > 150
    live.nachfuehren(beats)  # Rest kommt dazu — beide wachsen
    assert live.aufnahme.n > n_aufnahme and ab.n > 0
    assert live.fuer(BEZUG_AUFNAHME) is live.aufnahme
    live.abschnitt_setzen("seg-1", von, beats)  # derselbe: nichts passiert
    assert live.fuer(BEZUG_ABSCHNITT) is ab
    live.abschnitt_setzen(None, 0.0, beats)
    assert live.fuer(BEZUG_ABSCHNITT) is None
    # neue Aufnahme (weniger Zeilen als verarbeitet): von vorn
    live.nachfuehren(beats[:10])
    assert live.aufnahme.n <= 10


def test_fenster_zusammenfassung_aus_dem_puffer() -> None:
    profil = _profil()
    grenzen = grenzen_bpm(bereiche_fuer(profil, HfEinstellungen(modell="drei")))
    punkte = [(float(i) + 0.5, 500, 0) for i in range(400)]  # 120 bpm, 400 s
    z = fenster_zusammenfassung(punkte, profil, grenzen, jetzt_s=400.0)
    assert z["gueltig_s"] == 300.0 and z["mittel_bpm"] == 120.0
    assert z["mittel_prozent"] == pytest.approx(50.0)
    leer = fenster_zusammenfassung([], profil, grenzen, jetzt_s=400.0)
    assert leer["mittel_bpm"] is None
