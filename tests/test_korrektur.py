"""Nachträgliche RR-Korrektur und Live-Fenster.

Golden-Test (CLAUDE.md: HRV-Änderungen brauchen einen): automatische Ketten und
Kennzahlen der echten Messung aus praxis_gui sind festgehalten. Die Werte sind
am 2026-10-12 gegen praxis_gui gegengeprüft (`AnalysisSession.plan_outlier_runs`
und `auto_correct_runs` auf derselben Datei: dieselben neun Ketten, RMSSD
44,816 ms, SDNN 90,123 ms).
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trainingsapp.hrv_core.aufnahme import Aufnahme
from trainingsapp.hrv_core.korrektur import (
    Korrektur,
    analyse_laden,
    analyse_pfad,
    analyse_speichern,
    anwenden,
    automatisch,
    kennzahlen,
)
from trainingsapp.hrv_core.live import LiveFenster
from trainingsapp.hrv_core.recording import Recording, ist_messdatei, laden
from trainingsapp.hrv_core.time_domain import compute_time_domain

GOLDEN = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"


def basis(n: int = 120) -> list[int]:
    """Ruhige Reihe mit Atemwelle (Periode 5 Schläge) und langsamer Drift."""
    return [
        round(850 + 40 * math.sin(2 * math.pi * i / 5) + 10 * math.sin(2 * math.pi * i / 17))
        for i in range(n)
    ]


def messung(rr: list[int], extra_wand_s: dict[int, float] | None = None) -> Recording:
    """Eine Messung, wie die Aufnahme sie schreibt. Pakete ohne RR kommen im
    Sekundentakt; ``extra_wand_s`` schiebt vor einem Schlag Wanduhrzeit ein."""
    a = Aufnahme(
        geraet="Polar H10",
        geraet_profil="polar_h10",
        intervall_quelle="ekg_rr",
        start_mono=0.0,
        start_utc=datetime(2026, 10, 12, 8, 0, tzinfo=UTC),
    )
    t = 0.0
    for i, x in enumerate(rr):
        t += (x / 1000.0 if x else 1.0) + (extra_wand_s or {}).get(i, 0.0)
        a.schlag(x, 70, t, "m")
    return a.recording()


def alle_vorschlaege(rec: Recording, nullen: bool = True) -> list[Korrektur]:
    """Standard hier wie praxis_gui (Nullen interpolieren) — für den Abgleich."""
    return [k for kette in automatisch(rec, nullen=nullen) for k in kette.vorschlag]


# ---------------------------------------------------------------------------
# Golden-Datei
# ---------------------------------------------------------------------------


def test_golden_automatische_ketten() -> None:
    rec = laden(GOLDEN)
    ketten = automatisch(rec, nullen=True)

    assert [(k.start, k.ende) for k in ketten] == [
        (i, i) for i in (13, 30, 46, 50, 100, 179, 200, 293, 312)
    ]
    # Alle neun sind H10-Pakete ohne RR — kurze Ketten, interpolieren.
    assert {k.art for k in ketten} == {"interpolieren"}
    assert not any(k.unsicher for k in ketten)
    assert {k.grund for k in ketten} == {"kein RR"}
    assert all(k.vorschlag[0].original_value_ms == 0.0 for k in ketten)


def test_golden_kennzahlen_vor_und_nach_der_korrektur() -> None:
    rec = laden(GOLDEN)

    roh = compute_time_domain(rec.rr_ms)
    assert roh is not None
    assert roh["n"] == 305
    assert roh["n_diffs"] == 295
    assert roh["rmssd"] == pytest.approx(45.8182, abs=1e-3)
    assert roh["sdnn"] == pytest.approx(90.6341, abs=1e-3)

    korr = anwenden(rec, alle_vorschlaege(rec))
    kz = kennzahlen(korr)
    assert kz is not None
    assert korr.interpoliert == 9
    assert korr.entfernt == 0
    assert korr.breaks == []
    assert kz["n"] == 314
    assert kz["n_diffs"] == 313
    # Gegengeprüft mit praxis_gui (siehe Moduldocstring).
    assert kz["rmssd"] == pytest.approx(44.8162, abs=1e-3)
    assert kz["sdnn"] == pytest.approx(90.1228, abs=1e-3)
    assert kz["mean_rr"] == pytest.approx(990.3933, abs=1e-3)


def test_golden_interpolation_zwischen_den_nachbarn() -> None:
    rec = laden(GOLDEN)
    korr = anwenden(rec, alle_vorschlaege(rec))
    # Index 13 liegt zwischen 1123 und 1104 ms.
    assert korr.rr_ms[13] == pytest.approx((1123 + 1104) / 2)
    assert korr.flag[13] == "interp"
    assert korr.flag.count("interp") == 9


# ---------------------------------------------------------------------------
# Synthetische Fälle
# ---------------------------------------------------------------------------


def test_doppelschlag() -> None:
    """Ein Schlag zu viel erkannt: 850 ms zerfällt in zwei halbe Intervalle."""
    rr = basis()
    sauber = compute_time_domain(rr)
    mit = [*rr[:50], rr[50] // 2, rr[50] - rr[50] // 2, *rr[51:]]
    rec = messung(mit)

    (kette,) = automatisch(rec)
    assert (kette.start, kette.ende, kette.art, kette.unsicher) == (50, 51, "interpolieren", False)
    assert "Malik" in kette.grund

    vorher = compute_time_domain(mit)
    nachher = kennzahlen(anwenden(rec, kette.vorschlag))
    assert sauber and vorher and nachher
    assert vorher["rmssd"] > 1.8 * sauber["rmssd"]
    assert nachher["rmssd"] == pytest.approx(sauber["rmssd"], rel=0.03)


def test_ausgelassener_schlag() -> None:
    """Ein Schlag nicht erkannt: zwei Intervalle verschmelzen zu einem langen."""
    rr = basis()
    sauber = compute_time_domain(rr)
    mit = [*rr[:50], rr[50] + rr[51], *rr[52:]]
    rec = messung(mit)

    (kette,) = automatisch(rec)
    assert (kette.start, kette.ende, kette.art) == (50, 50, "interpolieren")

    vorher = compute_time_domain(mit)
    nachher = kennzahlen(anwenden(rec, kette.vorschlag))
    assert sauber and vorher and nachher
    assert vorher["rmssd"] > 3 * sauber["rmssd"]
    assert nachher["rmssd"] == pytest.approx(sauber["rmssd"], rel=0.03)


def test_einzelne_null_wird_interpoliert_wie_in_praxis_gui() -> None:
    rr = basis()
    rec = messung([*rr[:50], 0, *rr[50:]])
    (kette,) = automatisch(rec, nullen=True)
    assert (kette.start, kette.art, kette.grund) == (50, "interpolieren", "kein RR")


def test_lange_nullfolge_wird_ausgeschlossen() -> None:
    """Acht Pakete ohne RR = acht Sekunden ohne Schlag — ein Ausfall, kein Ausreißer."""
    rr = basis()
    rec = messung([*rr[:50], *([0] * 8), *rr[50:]])

    (kette,) = automatisch(rec, nullen=True)
    assert (kette.start, kette.ende, kette.art) == (50, 57, "ausschliessen")
    assert kette.luecke_s > 3.0
    (vorschlag,) = kette.vorschlag
    assert (vorschlag.op, vorschlag.beat_index, vorschlag.beat_index_end) == (
        "exclude_range",
        50,
        57,
    )

    korr = anwenden(rec, kette.vorschlag)
    assert korr.entfernt == 8
    assert korr.breaks == [50]  # Naht: keine Differenz über die Lücke
    assert len(korr.rr_ms) == len(rec.beats) - 8


def test_kurze_kette_mit_langer_luecke_wird_ausgeschlossen() -> None:
    """Zwei Nullen, aber gut fünf Sekunden ungedeckt — nie interpolieren."""
    rr = basis()
    rec = messung([*rr[:50], 0, 0, *rr[50:]], extra_wand_s={51: 4.0})
    (kette,) = automatisch(rec, nullen=True)
    assert kette.art == "ausschliessen"
    assert "Lücke" in kette.grund


def test_nahe_ausreisser_werden_zur_unsicheren_kette() -> None:
    """Zwei Ausreißer, zwei gute Schläge dazwischen: eine Kette über vier Schläge."""
    rr = basis()
    mit = [*rr[:50], 1700, *rr[51:53], 1700, *rr[54:]]
    (kette,) = automatisch(messung(mit))
    assert (kette.start, kette.ende, kette.unsicher) == (50, 53, True)
    assert [k.beat_index for k in kette.vorschlag] == [50, 53]
    assert all(k.unsicher for k in kette.vorschlag)


def test_reiner_pulsgeber_bekommt_keine_vorschlaege() -> None:
    rec = messung([0] * 30)
    assert rec.effektive_qualitaet() == "bpm_only"
    assert automatisch(rec) == []


def test_saubere_reihe_bleibt_unangetastet() -> None:
    assert automatisch(messung(basis())) == []


# ---------------------------------------------------------------------------
# anwenden: Operationen
# ---------------------------------------------------------------------------


def test_delete_hinterlaesst_eine_naht() -> None:
    rec = messung([800, 810, 820, 830, 840])
    korr = anwenden(rec, [Korrektur("delete", 2, 2.43, 820.0)])
    assert korr.rr_ms == [800.0, 810.0, 830.0, 840.0]
    assert korr.breaks == [2]
    assert korr.entfernt == 1
    assert korr.roh_index == [0, 1, 3, 4]


def test_interpolation_einer_kette_ist_eine_rampe() -> None:
    rec = messung([800, 2500, 2500, 2500, 900])
    korr = anwenden(rec, [Korrektur("interpolate", i, 0.0, 2500.0) for i in (1, 2, 3)])
    assert korr.rr_ms == [800.0, 825.0, 850.0, 875.0, 900.0]


def test_praxis_operationen_werden_angewendet() -> None:
    """set_value, split, merge stammen aus praxis_gui — lesen und anwenden."""
    rec = messung([800, 1600, 400, 400, 900])
    korr = anwenden(
        rec,
        [
            Korrektur.from_dict({"op": "split", "beat_index": 1, "t_s": 2.4, "n_parts": 2}),
            Korrektur.from_dict({"op": "merge", "beat_index": 2, "t_s": 2.8, "with_next": True}),
            Korrektur.from_dict({"op": "set_value", "beat_index": 4, "t_s": 4.1, "value_ms": 880}),
        ],
    )
    assert korr.rr_ms == [800.0, 800.0, 800.0, 800.0, 880.0]
    assert korr.flag == ["orig", "split", "split", "merge", "set"]


def test_zeitachse_der_korrigierten_reihe_beginnt_am_onset() -> None:
    rec = laden(GOLDEN)
    korr = anwenden(rec, [])
    assert korr.t_s[0] == pytest.approx(rec.beats[0].t_s)
    assert len(korr.t_s) == len(korr.rr_ms) == len(rec.beats)


def test_korrektur_dict_wie_praxis_gui() -> None:
    k = Korrektur("exclude_range", 200, 170.2049, 0.0, beat_index_end=212)
    assert k.to_dict() == {
        "op": "exclude_range",
        "beat_index": 200,
        "t_s": 170.205,
        "original_value_ms": 0.0,
        "beat_index_end": 212,
    }
    # praxis_gui schreibt bei exclude_range keinen Originalwert.
    aus_praxis = Korrektur.from_dict({"op": "exclude_range", "beat_index": 5, "t_s": 3.0})
    assert aus_praxis.original_value_ms is None
    assert "original_value_ms" not in aus_praxis.to_dict()


# ---------------------------------------------------------------------------
# Sidecar analysis-v1
# ---------------------------------------------------------------------------


def _sha1(pfad: Path) -> str:
    return hashlib.sha1(pfad.read_bytes()).hexdigest()


def test_analyse_round_trip(tmp_path: Path) -> None:
    roh = tmp_path / GOLDEN.name
    shutil.copy(GOLDEN, roh)
    vorher = _sha1(roh)
    rec = laden(roh)
    vorschlaege = alle_vorschlaege(rec)

    pfad = analyse_speichern(roh, rec, vorschlaege)

    assert pfad == analyse_pfad(roh) == tmp_path / "sensor_2026-05-23_125422_analyzed.json"
    assert not ist_messdatei(pfad)
    assert _sha1(roh) == vorher  # Rohdatei unangetastet
    assert not list(tmp_path.glob("*.tmp"))

    doc = json.loads(pfad.read_text(encoding="utf-8"))
    assert doc["schema"] == "analysis-v1"
    assert doc["source_file"] == roh.name
    assert doc["source_file_sha1"] == vorher
    assert doc["corrections_meta"]["corrections_total"] == 9
    assert doc["corrections_meta"]["corrections_by_op"] == {"interpolate": 9}
    assert len(doc["rr_corrected"]) == len(rec.beats)
    zeile = doc["rr_corrected"][13]
    assert zeile == {"t_s": pytest.approx(14.7275), "rr_ms": 1114, "flag": "interp"}
    assert doc["updated_utc"].endswith("Z")

    zurueck = analyse_laden(roh)
    assert zurueck == sorted(vorschlaege, key=lambda k: k.beat_index)
    assert kennzahlen(anwenden(rec, zurueck)) == kennzahlen(anwenden(rec, vorschlaege))


def test_vorhandenes_sidecar_wird_fortgeschrieben(tmp_path: Path) -> None:
    """Felder aus praxis_gui (Segmente, Ergebnisse, Operationen, die wir nicht
    erzeugen) dürfen beim Speichern nicht verschwinden."""
    roh = tmp_path / GOLDEN.name
    shutil.copy(GOLDEN, roh)
    analyse_pfad(roh).write_text(
        json.dumps(
            {
                "schema": "analysis-v1",
                "segments": [{"id": "r001", "name": "Ruhe", "t_start_s": 0, "t_end_s": 60}],
                "derived_metrics": {"rmssd": 44.0},
                "corrections": [
                    {"op": "set_value", "beat_index": 3, "t_s": 4.2, "value_ms": 1090.0},
                    {"op": "zukunft", "beat_index": 4, "t_s": 5.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    rec = laden(roh)
    geladen = analyse_laden(roh)
    assert [k.op for k in geladen] == ["set_value"]  # Unbekanntes übergangen

    analyse_speichern(roh, rec, [*geladen, Korrektur("interpolate", 13, 13.614, 0.0)])
    doc = json.loads(analyse_pfad(roh).read_text(encoding="utf-8"))
    assert doc["segments"][0]["name"] == "Ruhe"
    assert doc["derived_metrics"] == {"rmssd": 44.0}
    assert [c["op"] for c in doc["corrections"]] == ["set_value", "interpolate"]
    assert doc["corrections"][0]["value_ms"] == 1090.0


def test_ohne_sidecar_keine_korrekturen(tmp_path: Path) -> None:
    assert analyse_laden(tmp_path / "sensor_2026-10-12_080000.json") == []


# ---------------------------------------------------------------------------
# Live-Fenster
# ---------------------------------------------------------------------------


def test_live_artefakt_markiert_rohwert_bleibt() -> None:
    f = LiveFenster()
    rr = [*basis(30), 1700, *basis(30)[:10], 2600, 900]
    for i, x in enumerate(rr):
        f.hinzufuegen(float(i), x, 70)
    punkte = f.punkte()

    malik = punkte[30]
    assert malik.artefakt
    assert malik.rr_ms == 1700  # Rohwert unverändert
    assert malik.rr_korr is not None and 780 < malik.rr_korr < 920

    implausibel = punkte[41]
    assert implausibel.artefakt and implausibel.rr_ms == 2600
    assert implausibel.rr_korr is not None and implausibel.rr_korr < 1000

    assert sum(p.artefakt for p in punkte) == 2
    assert f.kennzahlen().artefakte == 2


def test_live_null_ist_kein_artefakt_sondern_kein_wert() -> None:
    f = LiveFenster()
    for i, x in enumerate([800, 810, 0, 805, 795, 800]):
        f.hinzufuegen(float(i), x, 72)
    null = f.punkte()[2]
    assert (null.artefakt, null.rr_korr, null.hf_bpm) == (False, None, 72)
    kz = f.kennzahlen()
    assert kz.schlaege == 5
    assert kz.rr_ms == 800


def test_live_rmssd_30s_mit_naht_am_artefakt() -> None:
    f = LiveFenster()
    rr = basis(80)
    rr[70] = 1700
    t = 0.0
    zeiten = []
    for x in rr:
        t += x / 1000.0
        zeiten.append(t)
        f.hinzufuegen(t, x, 70)
    kz = f.kennzahlen()

    im_fenster = [x for x, tt in zip(rr, zeiten, strict=True) if tt >= zeiten[-1] - 30.0]
    erwartet = compute_time_domain([None if x == 1700 else x for x in im_fenster])
    assert erwartet is not None
    assert kz.rmssd_30s == pytest.approx(erwartet["rmssd"])
    # Mit dem Artefakt als Differenz wäre RMSSD weit höher.
    roh = compute_time_domain(im_fenster, skip_seams=False)
    assert roh is not None and roh["rmssd"] > 2 * kz.rmssd_30s


@pytest.mark.parametrize("amplitude", [5.0, 8.0])
def test_live_schwankung_auf_sinus(amplitude: float) -> None:
    """HF = 70 ± A bei 6 Atemzügen/min: je 10-s-Fenster ein Atemzug, Spannweite 2·A."""
    f = LiveFenster()
    t = 0.0
    while t < 120.0:
        hf = 70.0 + amplitude * math.sin(2 * math.pi * 0.1 * t)
        rr = 60000.0 / hf
        t += rr / 1000.0
        f.hinzufuegen(t, round(rr), round(hf))
    kz = f.kennzahlen()

    assert kz.schwankung_60s == pytest.approx(2 * amplitude, rel=0.05)
    assert kz.hf_mittel_60s == pytest.approx(70.0, abs=1.0)
    assert kz.sdnn_60s is not None and kz.rmssd_30s is not None
    assert kz.artefakte == 0


def test_live_fenster_haelt_nur_max_s_und_laeuft_nie_zurueck() -> None:
    f = LiveFenster(max_s=10.0)
    for i in range(30):
        f.hinzufuegen(float(i), 800, 75)
    assert f.punkte()[0].t_s == 19.0
    assert len(f.punkte(seit_s=25.0)) == 5

    f.hinzufuegen(29.0, 800, 75)  # gleiche Paketankunft
    assert f.punkte()[-1].t_s == pytest.approx(29.001)

    f.leeren()
    assert f.punkte() == []
    leer = f.kennzahlen()
    assert leer.hf_bpm is None and leer.rmssd_30s is None and leer.schwankung_60s is None
    assert leer.schlaege == 0


def test_live_zu_wenig_daten_gibt_none() -> None:
    f = LiveFenster()
    for i, x in enumerate([800, 810, 790]):
        f.hinzufuegen(float(i), x, 75)
    kz = f.kennzahlen()
    assert kz.rmssd_30s is None and kz.sdnn_60s is None and kz.schwankung_60s is None
    assert kz.hf_bpm == 75


def test_live_reiner_pulsgeber_nutzt_gemeldete_herzfrequenz() -> None:
    f = LiveFenster()
    for i in range(60):
        f.hinzufuegen(float(i), 0, 70 + (i % 10))
    kz = f.kennzahlen()
    assert kz.schlaege == 0 and kz.rmssd_30s is None
    assert kz.schwankung_60s == pytest.approx(9.0)


# ---------------------------------------------------------------------------
# Standard: Nullen sind „kein Schlag", kein Artefakt
# ---------------------------------------------------------------------------


def test_golden_standard_erfindet_keine_schlaege() -> None:
    """Puls um 60: Pakete ohne RR sind keine Aussetzer — keine Vorschläge, 305 Schläge."""
    rec = laden(GOLDEN)
    assert automatisch(rec) == []
    kz = kennzahlen(anwenden(rec, []))
    roh = compute_time_domain(rec.rr_ms)
    assert kz is not None and roh is not None
    assert kz["n"] == roh["n"] == 305
    assert kz["rmssd"] == pytest.approx(roh["rmssd"], abs=1e-9)


def test_einzelne_null_bleibt_ohne_vorschlag() -> None:
    rr = basis()
    rec = messung([*rr[:50], 0, *rr[50:]])
    assert automatisch(rec) == []


def test_aussetzer_wird_am_langen_intervall_erkannt() -> None:
    """Fehlt wirklich ein Schlag, ist das Folgeintervall doppelt so lang — Malik findet es."""
    rr = basis()
    mit = [*rr[:50], 0, rr[50] + rr[51], *rr[52:]]
    ketten = automatisch(messung(mit))
    (kette,) = [k for k in ketten if k.start <= 51 <= k.ende]
    assert "Malik" in kette.grund
    assert 50 not in {v.beat_index for v in kette.vorschlag}  # die Null selbst bleibt
