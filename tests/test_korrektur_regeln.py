"""Einstellbare Korrektur und vom Sensor verworfene Intervalle selbst prüfen.

Golden-Datensatz ``sensor_2026-10-13_000000.json`` (synthetisch, siehe
``tests/golden/rr/README.md``): 300 Intervalle, 26 vom Sensor verworfen,
Intervall 150/151 mit 120 ms Fehlerschätzung. Die Sollwerte rechnet der Test
aus ``ppi_pakete`` selbst nach, ohne den Produktivcode.

Vorgaben (ALGO_VERSION 6, docs/korrektur.md): dem Sensor folgen, alle
Vorschläge übernehmen. „Selbst prüfen" (ALGO_VERSION 4) bleibt wählbar.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from hrv_core.korrektur import (
    Korrektur,
    analyse_laden,
    analyse_pfad,
    analyse_regeln,
    analyse_speichern,
    analysebasis,
    anwenden,
    auf_zeilen,
    kennzahlen,
    von_zeilen,
    vorauswahl,
    vorschlaege,
)
from hrv_core.ppi import ohne_verwerfung, ppi_naehte
from hrv_core.recording import Beat, Recording, laden, speichern
from hrv_core.regeln import Korrekturregeln
from hrv_core.time_domain import compute_time_domain
from hrv_core.trends import reihe, verlauf

from trainingsapp.core.hrv_ansicht import BLOCK, Ansicht, ansichten_lesen

GOLDEN_PPI = Path(__file__).parent / "golden" / "rr" / "sensor_2026-10-13_000000.json"
SENSOR = Korrekturregeln(sensor_verwerfung="sensor")
SELBST = Korrekturregeln(sensor_verwerfung="selbst")


def _alle_intervalle() -> tuple[list[int], list[int]]:
    doc = json.loads(GOLDEN_PPI.read_text(encoding="utf-8"))
    ppi = [x for p in doc["ppi_pakete"] for x in p["ppi_ms"]]
    fehler = [x for p in doc["ppi_pakete"] for x in p["fehler_ms"]]
    return ppi, fehler


# ---------------------------------------------------------------------------
# Analysebasis: alle Intervalle des Sensors
# ---------------------------------------------------------------------------


def test_golden_selbst_pruefen_nimmt_alle_intervalle_auf() -> None:
    rec = laden(GOLDEN_PPI)
    basis = analysebasis(rec, SELBST)
    ppi, _ = _alle_intervalle()
    assert [b.rr_ms for b in basis.rec.beats] == ppi
    assert basis.aufgenommen == 26
    assert sum(z is not None for z in basis.zeile) == len(rec.beats) == 274
    # Zeilen der Rohdatei bleiben, wie sie sind (bis auf die Herzuhr)
    for b, z in zip(basis.rec.beats, basis.zeile, strict=True):
        if z is not None:
            roh = rec.beats[z]
            assert (b.rr_ms, b.hf_bpm, b.t_wall_s, b.tw_src) == (
                roh.rr_ms,
                roh.hf_bpm,
                roh.t_wall_s,
                roh.tw_src,
            )
    assert ppi_naehte(basis.rec) == []


def test_golden_selbst_pruefen_kennzahlen_unabhaengig_nachgerechnet() -> None:
    """Alle 300 Intervalle, 150/151 (Sensor unsicher) als Rampe interpoliert."""
    ppi, fehler = _alle_intervalle()
    assert [i for i, f in enumerate(fehler) if f > 50] == [150, 151]
    x = [float(v) for v in ppi]
    x[150] = x[149] + (x[152] - x[149]) / 3
    x[151] = x[149] + (x[152] - x[149]) * 2 / 3
    diffs = [x[i] - x[i - 1] for i in range(1, len(x))]
    soll = math.sqrt(sum(d * d for d in diffs) / len(diffs))

    regeln = SELBST
    basis = analysebasis(laden(GOLDEN_PPI), regeln)
    ketten = vorschlaege(basis.rec, regeln)
    assert [(k.start, k.ende, k.art) for k in ketten] == [(150, 151, "interpolieren")]
    kz = kennzahlen(anwenden(basis.rec, [v for k in ketten for v in k.vorschlag]))
    assert kz is not None
    assert kz["n_diffs"] == 299
    assert kz["rmssd"] == pytest.approx(soll, abs=1e-9)
    assert kz["rmssd"] == pytest.approx(21.8946, abs=1e-4)


def test_dem_sensor_folgen_wie_bis_algo_version_3() -> None:
    rec = laden(GOLDEN_PPI)
    basis = analysebasis(rec, SENSOR)
    assert basis.rec is rec and basis.zeile == list(range(274)) and basis.aufgenommen == 0
    kz = kennzahlen(anwenden(rec, []))
    assert kz is not None and kz["rmssd"] == pytest.approx(21.7432, abs=1e-4)


def test_golden_vorgabe_kennzahlen_unabhaengig_nachgerechnet() -> None:
    """Vorgabe: nur die nicht verworfenen Intervalle, Naht hinter jedem verworfenen,
    die beiden mit 120 ms Fehlerschätzung als Rampe interpoliert (ALGO_VERSION 6)."""
    doc = json.loads(GOLDEN_PPI.read_text(encoding="utf-8"))
    zeilen: list[float] = []
    fehler: list[int] = []
    naehte: set[int] = set()
    verworfen_davor = False
    for paket in doc["ppi_pakete"]:
        for wert, f, blocker in zip(
            paket["ppi_ms"], paket["fehler_ms"], paket["blocker"], strict=True
        ):
            if blocker:
                verworfen_davor = True
                continue
            if verworfen_davor and zeilen:
                naehte.add(len(zeilen))
            zeilen.append(float(wert))
            fehler.append(f)
            verworfen_davor = False
    unsicher = [i for i, f in enumerate(fehler) if f > 50]
    assert unsicher == [126, 127] and not naehte & {126, 127, 128}
    x = zeilen
    x[126] = x[125] + (x[128] - x[125]) / 3
    x[127] = x[125] + (x[128] - x[125]) * 2 / 3
    diffs = [x[i] - x[i - 1] for i in range(1, len(x)) if i not in naehte]
    soll = math.sqrt(sum(d * d for d in diffs) / len(diffs))

    regeln = Korrekturregeln()
    assert (regeln.sensor_verwerfung, regeln.vorauswahl) == ("sensor", "alle")
    rec = laden(GOLDEN_PPI)
    basis = analysebasis(rec, regeln)
    ketten = vorschlaege(basis.rec, regeln)
    assert [(k.start, k.ende, k.art) for k in ketten] == [(126, 127, "interpolieren")]
    gewaehlt = vorauswahl(ketten, regeln.vorauswahl)
    kz = kennzahlen(anwenden(basis.rec, [v for i in gewaehlt for v in ketten[i].vorschlag]))
    assert kz is not None
    assert kz["n_diffs"] == len(diffs) == 269
    assert kz["rmssd"] == pytest.approx(soll, abs=1e-9)
    assert kz["rmssd"] == pytest.approx(21.7375, abs=1e-4)


def test_vorgabe_verworfenes_in_bewegung_zaehlt_nicht() -> None:
    """Was der Sensor in Bewegung verwirft, ist oft falsch — auch bei kleiner
    Fehlerschätzung (14.10.2026). Nach Vorgabe zählt es nicht; „selbst" nähme
    das Gezappel auf und RMSSD stiege um ein Vielfaches."""
    ruhig = [800 + (8 if i % 2 else -8) for i in range(60)]
    zappel = [800 + (150 if i % 2 else -150) for i in range(30)]
    werte = ruhig[:30] + zappel + ruhig[30:]
    blocker = [0] * 30 + [1] * 30 + [0] * 30
    pakete = [
        {"t_wall_s": 1.0 + i, "ppi_ms": [w], "fehler_ms": [12], "blocker": [b]}
        for i, (w, b) in enumerate(zip(werte, blocker, strict=True))
    ]
    beats, t = [], 0.0
    for w, b in zip(werte, blocker, strict=True):
        t += w / 1000
        if not b:
            beats.append(Beat(round(t, 3), w, 75, None))
    rec = Recording(beats=beats, intervall_quelle="ppg_ppi", ppi_pakete=pakete)

    def rmssd(regeln: Korrekturregeln) -> float:
        basis = analysebasis(rec, regeln)
        ketten = vorschlaege(basis.rec, regeln)
        gewaehlt = vorauswahl(ketten, regeln.vorauswahl)
        kz = kennzahlen(anwenden(basis.rec, [v for i in gewaehlt for v in ketten[i].vorschlag]))
        assert kz is not None
        return float(kz["rmssd"])

    assert rmssd(Korrekturregeln()) == pytest.approx(16.0)
    assert rmssd(SELBST) > 5 * rmssd(Korrekturregeln())


def test_ohne_ppi_pakete_ist_die_basis_die_rohdatei() -> None:
    rec = Recording(beats=[Beat(0.8 * (i + 1), 800) for i in range(10)])
    assert ohne_verwerfung(rec) is None
    assert analysebasis(rec, Korrekturregeln()).rec is rec


def test_verworfene_ausreisser_werden_selbst_erkannt() -> None:
    """Was der Sensor zu Recht verwarf, findet die Automatik selbst."""
    werte = [800, 810, 805, 1650, 800, 795, 810, 805, 800, 790, 805, 800]
    blocker = [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    pakete = [{"t_wall_s": 10.0, "ppi_ms": werte, "fehler_ms": [10] * 12, "blocker": blocker}]
    gute = [w for w, b in zip(werte, blocker, strict=True) if not b]
    beats, t = [], 0.0
    for w in gute:
        t += w / 1000
        beats.append(Beat(round(t, 3), w, 70, None))
    rec = Recording(beats=beats, intervall_quelle="ppg_ppi", ppi_pakete=pakete)
    regeln = SELBST
    basis = analysebasis(rec, regeln)
    ketten = vorschlaege(basis.rec, regeln)
    assert [(k.start, k.ende, k.art) for k in ketten] == [(3, 3, "interpolieren")]
    assert basis.zeile[3] is None


# ---------------------------------------------------------------------------
# Regeln wirken
# ---------------------------------------------------------------------------


def _reihe(rr: list[int], quelle: str = "ekg_rr") -> Recording:
    beats, t = [], 0.0
    for x in rr:
        t += x / 1000
        beats.append(Beat(round(t, 3), x, 75, round(t, 3)))
    return Recording(beats=beats, intervall_quelle=quelle)


def test_malik_abschaltbar_und_schwelle_einstellbar() -> None:
    rr = [800 + (10 if i % 2 else -10) for i in range(60)]
    rr[30] = 1100  # 28 % über dem gleitenden Mittel
    rec = _reihe(rr)
    assert [k.start for k in vorschlaege(rec, Korrekturregeln())] == [30]  # EKG: 20 %
    assert [k.start for k in vorschlaege(rec, Korrekturregeln(malik=0.25))] == [30]
    assert vorschlaege(rec, Korrekturregeln(malik=0.3)) == []
    assert vorschlaege(rec, Korrekturregeln(malik_an=False)) == []
    assert vorschlaege(_reihe(rr, "ppg_ppi"), Korrekturregeln()) == []  # optisch: 30 %


def test_grenzen_und_kettenplanung_einstellbar() -> None:
    rr = [800 + (10 if i % 2 else -10) for i in range(60)]
    rr[20:23] = [2100, 2100, 2100]
    rec = _reihe(rr)
    k = vorschlaege(rec, Korrekturregeln(malik_an=False))
    assert [(x.start, x.ende, x.art, x.unsicher) for x in k] == [(20, 22, "interpolieren", True)]
    k = vorschlaege(rec, Korrekturregeln(malik_an=False, auto_max=3))
    assert k[0].unsicher is False
    k = vorschlaege(rec, Korrekturregeln(malik_an=False, unsicher_max=2))
    assert k[0].art == "ausschliessen"
    assert vorschlaege(rec, Korrekturregeln(malik_an=False, rr_max=2500)) == []


def test_vorauswahl() -> None:
    rr = [800 + (10 if i % 2 else -10) for i in range(80)]
    rr[10] = 1650
    rr[30:33] = [2100] * 3
    rr[50:60] = [2100] * 10
    ketten = vorschlaege(_reihe(rr), Korrekturregeln())
    arten = [(k.art, k.unsicher) for k in ketten]
    assert arten == [
        ("interpolieren", False),
        ("interpolieren", True),
        ("ausschliessen", False),
    ]
    assert vorauswahl(ketten, "keine") == set()
    assert vorauswahl(ketten, "sicher") == {0, 2}  # unsichere Kette bliebe roh
    assert vorauswahl(ketten, "alle") == {0, 1, 2}  # Vorgabe: kein Artefakt bleibt roh
    assert Korrekturregeln().vorauswahl == "alle"


def test_regeln_lesen_defensiv() -> None:
    r = Korrekturregeln.aus_dict(
        {"sensor_verwerfung": "quatsch", "vorauswahl": 3, "rr_min": 900, "rr_max": 100}
    )
    assert r.sensor_verwerfung == "sensor" and r.vorauswahl == "alle"
    assert (r.rr_min, r.rr_max) == (500, 800)  # auf die Grenzen beschnitten
    assert Korrekturregeln.aus_json("kaputt") == Korrekturregeln()
    assert Korrekturregeln.aus_dict({"malik_an": "ja"}).malik_an is True  # kein bool: Vorgabe


# ---------------------------------------------------------------------------
# Sidecar
# ---------------------------------------------------------------------------


def _golden_kopie(tmp_path: Path) -> Path:
    ziel = tmp_path / GOLDEN_PPI.name
    ziel.write_bytes(GOLDEN_PPI.read_bytes())
    return ziel


def test_sidecar_mit_wiederaufnahme(tmp_path: Path) -> None:
    pfad = _golden_kopie(tmp_path)
    rec = laden(pfad)
    regeln = SELBST
    basis = analysebasis(rec, regeln)
    # Eine Korrektur an einer Zeile, eine an einem wieder aufgenommenen Intervall,
    # ein Ausschluss über einen Blocker-Lauf (Intervalle 3–5 verworfen)
    korrekturen = [
        Korrektur("interpolate", 150, 0.0, 850.0),
        Korrektur("interpolate", 40, 0.0, 850.0),
        Korrektur("exclude_range", 2, 0.0, 850.0, beat_index_end=7),
    ]
    assert basis.zeile[40] is None
    analyse_speichern(pfad, rec, korrekturen, regeln=regeln, basis=basis)
    doc = json.loads(analyse_pfad(pfad).read_text(encoding="utf-8"))

    # Für praxis_gui: Zeilen der Rohdatei — das Intervall 40 hat keine
    zeilen = [(d["op"], d["beat_index"], d.get("beat_index_end")) for d in doc["corrections"]]
    # (vor Intervall 150 verwarf der Sensor 24 — Zeile 126)
    assert zeilen == [("exclude_range", 2, 4), ("interpolate", 126, None)]
    assert len(doc["rr_corrected"]) == len(rec.beats) - 3
    assert [d["beat_index"] for d in doc["corrections_ppi"]] == [2, 40, 150]
    assert doc["corrections_meta"]["regeln"]["sensor_verwerfung"] == "selbst"
    assert doc["corrections_meta"]["malik_threshold"] == 0.3

    # Zurück: in der Basis vollständig, ohne Basis die Zeilen
    assert [k.beat_index for k in analyse_laden(pfad, basis)] == [2, 40, 150]
    assert [k.beat_index for k in analyse_laden(pfad)] == [2, 126]
    assert analyse_regeln(pfad) == regeln

    # Wer dem Sensor folgt, speichert ohne Erweiterung — sie verschwindet
    analyse_speichern(
        pfad, rec, analyse_laden(pfad), regeln=SENSOR, basis=analysebasis(rec, SENSOR)
    )
    doc = json.loads(analyse_pfad(pfad).read_text(encoding="utf-8"))
    assert "corrections_ppi" not in doc


def test_sidecar_von_praxis_geaendert_gilt_praxis(tmp_path: Path) -> None:
    """Passt ``corrections_ppi`` nicht mehr zu ``corrections``, zählt praxis_gui."""
    pfad = _golden_kopie(tmp_path)
    rec = laden(pfad)
    basis = analysebasis(rec, SELBST)
    analyse_speichern(
        pfad,
        rec,
        [Korrektur("interpolate", 150, 0.0, 850.0)],
        regeln=SELBST,
        basis=basis,
    )
    doc = json.loads(analyse_pfad(pfad).read_text(encoding="utf-8"))
    doc["corrections"] = [{"op": "delete", "beat_index": 10, "t_s": 8.5}]
    analyse_pfad(pfad).write_text(json.dumps(doc), encoding="utf-8")
    geladen = analyse_laden(pfad, basis)
    assert [(k.op, k.beat_index) for k in geladen] == [("delete", basis.zeile.index(10))]


def test_altes_sidecar_auf_die_basis_uebertragen(tmp_path: Path) -> None:
    pfad = _golden_kopie(tmp_path)
    rec = laden(pfad)
    analyse_speichern(pfad, rec, [Korrektur("exclude_range", 90, 0.0, 850.0, beat_index_end=100)])
    assert analyse_regeln(pfad) == Korrekturregeln(malik=0.2)  # aus corrections_meta
    basis = analysebasis(rec, SELBST)
    (k,) = analyse_laden(pfad, basis)
    assert (basis.zeile[k.beat_index], basis.zeile[k.span()[1]]) == (90, 100)
    # Hin und zurück ergibt dieselben Zeilen
    assert [(x.beat_index, x.span()[1]) for x in auf_zeilen([k], basis, rec)] == [(90, 100)]
    assert von_zeilen(auf_zeilen([k], basis, rec), basis)[0].span() == k.span()


def test_round_trip_ueber_speichern(tmp_path: Path) -> None:
    rec = laden(GOLDEN_PPI)
    pfad = speichern(rec, tmp_path)
    assert analyse_regeln(pfad) is None
    assert analyse_laden(pfad, analysebasis(rec, Korrekturregeln())) == []


# ---------------------------------------------------------------------------
# Verlaufskurven
# ---------------------------------------------------------------------------


def test_verlauf_gleich_compute_time_domain_je_fenster() -> None:
    zufall = np.random.default_rng(3)
    rr = (850 + 50 * np.sin(np.arange(400) / 4) + zufall.normal(0, 15, 400)).round()
    t = np.cumsum(rr) / 1000
    naht = np.zeros(400, dtype=bool)
    naht[200] = True
    rr[100] = np.nan
    for kennzahl, schluessel in (("rmssd", "rmssd"), ("sdnn", "sdnn"), ("pnnx", "pnn50")):
        for te, wert in verlauf(t, rr, naht, kennzahl, 30, schritt_s=20):
            maske = (t > te - 30) & (t <= te)
            idx = np.flatnonzero(maske)
            werte: list[float | None] = []
            for i in idx:
                if naht[i] and werte:
                    werte.append(None)
                werte.append(None if np.isnan(rr[i]) else float(rr[i]))
            erwartet = compute_time_domain(werte)
            assert erwartet is not None
            assert wert == pytest.approx(erwartet[schluessel]), (kennzahl, te)
    hf = verlauf(t, rr, naht, "hf_rr", 10, schritt_s=50)
    assert all(65 < w < 75 for _, w in hf)


def test_verlauf_luecke_statt_erfundener_zahl() -> None:
    t = [float(i) for i in range(1, 21)] + [float(i) for i in range(60, 80)]
    rr = [1000.0] * 40
    punkte = verlauf(t, rr, [False] * 40, "sdnn", 10, schritt_s=5)
    assert not [x for x, _ in punkte if 30 <= x <= 55]
    _, rr2, naht2 = reihe([1, 2, 3], [800, 2500, 810], [])
    assert np.isnan(rr2[1]) and not naht2.any()


# ---------------------------------------------------------------------------
# Ansichten
# ---------------------------------------------------------------------------


def test_ansicht_umschalten_und_gruppen() -> None:
    a = Ansicht(kurven=[])
    for k in ("rmssd", "hf_rr", "sdnn", "pnnx", "hf_geraet"):
        a.umschalten(k)
    assert a.kurven == ["rmssd", "hf_rr", "sdnn", "pnnx", "hf_geraet"]  # keine Höchstzahl mehr
    achse = {"rmssd": "var", "sdnn": "var", "hf_rr": "bpm", "pnnx": "%", "hf_geraet": "bpm"}.get
    assert a.gruppen(achse) == [["rmssd", "sdnn"], ["hf_rr", "hf_geraet"], ["pnnx"]]
    a.umschalten("rmssd")
    assert a.gruppen(achse) == [["hf_rr", "hf_geraet"], ["sdnn"], ["pnnx"]]
    assert a.gruppen(achse, nur=["sdnn", "pnnx"]) == [["sdnn"], ["pnnx"]]
    assert ansichten_lesen("kaputt") == [] and ansichten_lesen('[{"name": 1}, 3]')[0].name == "1"


def test_ansicht_alt_wird_ergaenzt_und_neu_bleibt() -> None:
    """Ansichten von vor Version 2: pNN50 heißt pnnx, neue Bereiche kommen dazu."""
    alt = Ansicht.aus_dict({"name": "Alt", "kurven": ["pnn50"], "fenster": {"pnn50": 60}})
    assert alt.kurven[0] == "pnnx" and alt.fenster == {"pnnx": 60}
    assert "lf_power" in alt.kurven and "dfa_alpha1" in alt.kurven
    neu = Ansicht("Neu", ["rmssd"], modus={"rmssd": BLOCK, "sdnn": "quatsch"}, pnn_ms=20)
    zurueck = Ansicht.aus_dict(neu.als_dict())
    assert zurueck.kurven == ["rmssd"] and zurueck.pnn_ms == 20
    assert zurueck.modus == {"rmssd": BLOCK}
    assert Ansicht.aus_dict({"pnn_ms": 9999}).pnn_ms == 50


def test_ansicht_vollbild_achsen_bleiben_und_alte_bekommen_die_vorgabe() -> None:
    """Vollbild (16.10.2026): Kurven je Achse reisen mit der Ansicht; ältere: Roh | RMSSD."""
    from trainingsapp.core.hrv_ansicht import LINKS, RECHTS, ROH

    alt = Ansicht.aus_dict({"v": 3, "name": "Alt", "kurven": ["rmssd"]})
    assert (alt.links, alt.rechts) == ([ROH], ["rmssd"])
    a = Ansicht(links=["rmssd", "sdnn"], rechts=[])
    zurueck = Ansicht.aus_dict(json.loads(json.dumps(a.als_dict())))
    assert (zurueck.links, zurueck.rechts) == (["rmssd", "sdnn"], [])  # „keine rechts" bleibt
    kaputt = Ansicht.aus_dict({"links": [], "rechts": ["roh", 3, "pnn50"]})
    assert (kaputt.links, kaputt.rechts) == ([ROH], ["pnnx"])  # nie leer, nie doppelt
    # Wählen über die Bereiche hinweg: RMSSD links, DFA α1 rechts
    achse = {"roh": "rr", "rmssd": "var", "dfa_alpha1": "alpha"}.get
    v = Ansicht()
    v.achse_waehlen(LINKS, "rmssd", achse)
    v.achse_waehlen(RECHTS, "dfa_alpha1", achse)
    assert (v.links, v.rechts) == (["rmssd"], ["dfa_alpha1"])


def test_state_speichert_regeln_und_ansichten(tmp_path: Path) -> None:
    from trainingsapp.ui.state import AppState

    state = AppState.starten(tmp_path / "app.db")
    try:
        assert state.korrekturregeln() == Korrekturregeln()
        state.korrekturregeln_setzen(Korrekturregeln(malik=0.25, sensor_verwerfung="selbst"))
        a = Ansicht("Atemübung", ["rmssd", "sdnn"], {"rmssd": 60}, gemeinsam=False)
        state.ansicht_setzen(a)
        state.ansicht_speichern(a)
        state.ansicht_speichern(Ansicht("Belastung", ["hf_rr"]))
    finally:
        state.schliessen()

    state = AppState.starten(tmp_path / "app.db")
    try:
        assert state.korrekturregeln().malik == 0.25
        assert state.korrekturregeln().selbst_pruefen
        assert state.ansicht() == a
        assert [x.name for x in state.ansichten()] == ["Atemübung", "Belastung"]
        state.ansicht_loeschen("Atemübung")
        assert [x.name for x in state.ansichten()] == ["Belastung"]
    finally:
        state.schliessen()
