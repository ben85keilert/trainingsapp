"""HF-Auswertung einer Aufzeichnung, Cache und Verlauf (Stufe 2/3, Ben 29.10.2026)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest
from hrv_core.constants import ALGO_VERSION
from hrv_core.recording import Beat, Recording

from trainingsapp.core.hf_auswertung import (
    AbschnittWand,
    HfAuswertung,
    achse_zu_wand,
    auswerten,
    erholungs_marken,
    phase_name,
    profil_stand,
    wand_zu_achse,
)
from trainingsapp.core.hf_einstellungen import HfEinstellungen
from trainingsapp.core.hf_profil import Profilwert, bereiche_fuer, hf_profil
from trainingsapp.core.hf_verlauf import (
    Tageslast,
    Testpunkt,
    baseline_reihe,
    tageslasten,
    wochenlasten,
)
from trainingsapp.core.hf_verlauf import testreihe as hf_testreihe
from trainingsapp.core.models import HrvRecording, Subject
from trainingsapp.data.db import oeffnen, schema_version
from trainingsapp.data.hf_cache import HfCacheRepo
from trainingsapp.data.repositories import HrvRepo, SubjectRepo

HEUTE = date(2026, 10, 29)


def _profil(voll: bool = True):
    s = Subject(name="Ich", birth_year=1986, geschlecht="m")
    e = []
    if voll:
        e = [
            Profilwert(s.id, "ruhe_hf", 60, "eintrag", date(2026, 10, 1)),
            Profilwert(s.id, "hf_max", 180, "ergometrie", date(2026, 10, 1), unsicherheit=3),
        ]
    return hf_profil(e, s, HEUTE)


def _rec(hf_verlauf: list[float], *, start: datetime | None = None, marken=()) -> Recording:
    """Eine Aufzeichnung mit einem Schlag je Sekunde und gegebener HF je Sekunde."""
    beats = [
        Beat(float(i), round(60000 / h), int(h), float(i) + 0.4) for i, h in enumerate(hf_verlauf)
    ]
    ereignisse = [
        {
            "beat_index": int(t),
            "dt_s": 0.0,
            "t_wall_s": float(t),
            "t_s": float(t),
            "text": "x",
            "marke": {"quelle": "person", "art": "erholung", "kontext": k, "haltung": h},
        }
        for t, k, h in marken
    ]
    return Recording(
        beats=beats,
        start_utc=start or datetime(2026, 10, 29, 6, 0, tzinfo=UTC),
        ereignisse=ereignisse,
    )


def test_achsen_umrechnung() -> None:
    a, w = [1.0, 2.0, 4.0], [1.0, 2.5, 6.0]
    assert achse_zu_wand(a, w, 3.0) == 4.25 and wand_zu_achse(a, w, 4.25) == 3.0
    assert wand_zu_achse(a, w, 7.0) == 5.0 and wand_zu_achse([], [], 3.0) == 3.0


def test_auswertung_gesamt_abschnitte_erholung_und_kandidaten() -> None:
    profil = _profil()
    bereiche = bereiche_fuer(profil, HfEinstellungen(modell="drei"))
    # 5 min Ruhe (62), 10 min Belastung (150), 3 min Erholung (fallend)
    hf = [62.0] * 300 + [150.0] * 600 + [150 - i * 0.4 for i in range(180)]
    rec = _rec(hf, marken=[(900.0, "intervall", "geht")])
    rec.ereignisse.append(
        {
            "beat_index": 600,
            "dt_s": 0.0,
            "t_wall_s": 600.0,
            "t_s": 600.0,
            "text": "Sprechen",
            "marke": {"quelle": "person", "art": "talk"},
        }
    )
    abschnitte = [
        AbschnittWand("seg-1", "Belastung", 300.0, 900.0, endteil_s=120.0),
        AbschnittWand("seg-2", "Ruhe vorher", 0.0, 300.0),
    ]
    a = auswerten(rec, profil=profil, bereiche=bereiche, abschnitte=abschnitte)
    assert a.algo_version == ALGO_VERSION and a.reihe is not None
    assert a.gesamt["gueltig_s"] == pytest.approx(1080.0, abs=2)
    assert a.gesamt["gipfel_bpm"] == pytest.approx(150.0)
    assert len(a.gesamt["sekunden_je_bereich"]) == 3
    # Abschnitt Belastung: Rechenbereich mit Endteil, Erholung am getippten Ende
    b = next(x for x in a.abschnitte if x["id"] == "seg-1")
    assert b["rechen_bis_s"] == 1020.0 and b["werte"]["mittel_bpm"] < 150
    assert b["erholung"] is not None and b["erholung"]["hrr"]["60"] == pytest.approx(24.0, abs=1)
    assert b["drift"] is None  # unter 20 min
    r = next(x for x in a.abschnitte if x["id"] == "seg-2")
    assert r["werte"]["mittel_bpm"] == pytest.approx(62.0, abs=0.1) and r["erholung"] is None
    # Erholung aus der Marke, mit Kontext und Haltung
    assert len(a.erholungen) == 1 and a.erholungen[0]["kontext"] == "intervall"
    assert a.erholungen[0]["hrr"]["30"] == pytest.approx(12.0, abs=1)
    # HFmax-Kandidat: Plateau bei 150, gültig; Ruhe-Kandidat: Aufnahme ist 18 min → Kandidat
    assert a.hfmax_kandidat is not None and a.hfmax_kandidat["gueltig"]
    assert a.hfmax_kandidat["wert"] == pytest.approx(150.0)
    assert a.ruhe_kandidat is not None and a.ruhe_kandidat["quelle"] == "messung_morgen_10"
    assert a.ruhe_kandidat["wert"] == pytest.approx(62.0, abs=0.1)
    # Vorschlag: eine Belastungsphase — deckt sich mit „Belastung“, fällt also weg
    assert all(v["art"] != "belastung" for v in a.vorschlaege)
    ohne = auswerten(rec, profil=profil, bereiche=bereiche)
    assert any(v["art"] == "belastung" and v["von_s"] == 300.0 for v in ohne.vorschlaege)
    assert a.aktivitaet is not None and not a.aktivitaet["gueltig"]
    assert a.talk is not None and a.talk["wert"] == pytest.approx(150.0) and a.talk["n_marken"] == 1
    assert a.talk["prozent"] == pytest.approx(75.0)
    assert a.profil_stand["hfmax"] == 180 and len(a.profil_stand["grenzen"]) == 2
    # Rundlauf über das Dict (Cache)
    d = a.als_dict()
    z = HfAuswertung.aus_dict(d)
    assert z.gesamt == a.gesamt and z.abschnitte == a.abschnitte and z.reihe is None
    assert phase_name("belastung", rec, 300.0, 900.0).startswith("Belastung ")


def test_auswertung_ohne_profil_und_nacht() -> None:
    profil = _profil(voll=False)
    assert bereiche_fuer(profil, HfEinstellungen()) == []
    # 7 h: 1 h wach (70), 5 h Schlaf (50), 1 h wach (72); Start 22 Uhr Ortszeit
    hf = [70.0] * 3600 + [50.0] * 18000 + [72.0] * 3600
    start = datetime(2026, 10, 28, 20, 0, tzinfo=UTC)  # 22:00 MESZ
    rec = _rec(hf, start=start)
    a = auswerten(rec, profil=profil, bereiche=[])
    assert a.gesamt["mittel_prozent"] is None and a.aktivitaet is None
    assert a.ruhe_kandidat is None  # zu lang für eine Morgenmessung
    schlaf = [v for v in a.vorschlaege if v["art"] == "schlaf"]
    assert len(schlaf) == 1 and schlaf[0]["von_s"] == pytest.approx(3600.0, abs=120)
    # ohne Schlafabschnitt zählt das Nachtfenster 20–10 Uhr der Aufnahme (≥ 4 h Daten)
    assert a.nacht is not None and a.nacht["gueltig"] and a.nacht["wert"] == pytest.approx(50.0)
    assert a.nacht["grundlage"] == "nachtfenster" and a.nacht["abschnitt_id"] is None
    assert a.nacht["von_s"] <= 0 and a.nacht["bis_s"] - a.nacht["von_s"] == pytest.approx(14 * 3600)
    # bestätigter Schlafabschnitt → Nacht-HF daraus, kein Schlafvorschlag mehr
    b = auswerten(
        rec,
        profil=profil,
        bereiche=[],
        abschnitte=[AbschnittWand("seg-s", "Schlafen bis 6", 3600.0, 21600.0)],
    )
    assert b.nacht is not None and b.nacht["gueltig"] and b.nacht["wert"] == pytest.approx(50.0)
    assert b.nacht["abschnitt_id"] == "seg-s" and b.nacht["grundlage"] == "abschnitt"
    assert not any(v["art"] == "schlaf" for v in b.vorschlaege)
    assert erholungs_marken(rec) == []
    # eine echte Nacht schwankt: 21–6 Uhr, Wachphasen und REM-Anstiege, trotzdem Nacht-HF
    rng = np.random.default_rng(1)
    hf = [68.0] * 1800  # 8 Stunden Schlaf mit 90-min-Zyklen 44–56 bpm, dann wach
    hf += [50.0 + 6 * np.sin(i / 5400 * 2 * np.pi) + rng.normal(0, 2) for i in range(8 * 3600)]
    hf += [66.0] * 1800
    nacht = _rec(hf, start=datetime(2026, 10, 28, 19, 0, tzinfo=UTC))  # 21:00 MESZ
    c = auswerten(nacht, profil=profil, bereiche=[])
    assert c.nacht is not None and c.nacht["gueltig"] and 44 < c.nacht["wert"] < 52
    assert c.nacht["grundlage"] == "nachtfenster"
    # kurze Aufnahme am Abend: kein Nachtwert
    kurz = auswerten(
        _rec([60.0] * 3600, start=datetime(2026, 10, 28, 20, 0, tzinfo=UTC)),
        profil=profil,
        bereiche=[],
    )
    assert kurz.nacht is None


def test_alpha1_schwellen_nur_bei_ekg_und_mit_gruenden() -> None:
    """Entscheidung 20: α1-Fenster gegen HF; weißes Rauschen hat α1 ≈ 0,5 und keinen
    Durchgang durch 0,75 — Struktur da, Schwelle ungültig mit Grund. Optisch: nichts."""
    rng = np.random.default_rng(5)
    beats, t = [], 0.0
    for i in range(1200):
        rr = 750 - i * 0.15 + rng.normal(0, 25)  # leichte Rampe 80 → 100 bpm, Rauschen
        t += rr / 1000
        beats.append(Beat(round(t, 3), int(rr), int(60000 / rr), round(t, 3)))
    rec = Recording(beats=beats, geraet="Polar H10", geraet_profil="polar_h10")
    a = auswerten(rec, profil=_profil(), bereiche=[])
    assert a.alpha1 is not None and a.alpha1["n_fenster"] > 20
    assert a.alpha1["vt1"]["gueltig"] is False and a.alpha1["vt1"]["gruende"]
    assert len(a.alpha1["reihe"]["alpha1"]) == a.alpha1["n_fenster"]
    assert 0.3 < np.median(a.alpha1["reihe"]["alpha1"]) < 0.75
    assert HfAuswertung.aus_dict(a.als_dict()).alpha1 == a.alpha1
    # Artefakte über 5 % → ungültig, auch wenn die Regression etwas hergäbe
    b = auswerten(rec, profil=_profil(), bereiche=[], artefakt=[i % 10 == 0 for i in range(1200)])
    assert any("Artefaktanteil" in g for g in b.alpha1["vt1"]["gruende"])
    # optischer Sensor: keine α1-Schwellen
    optisch = Recording(
        beats=beats, geraet="Verity", geraet_profil="verity_sense", intervall_quelle="ppg_ppi"
    )
    assert auswerten(optisch, profil=_profil(), bereiche=[]).alpha1 is None


def test_leere_aufzeichnung() -> None:
    a = auswerten(Recording(), profil=_profil(), bereiche=[])
    assert a.gesamt["mittel_bpm"] is None and a.hfmax_kandidat is None and a.vorschlaege == []


# -- Cache ---------------------------------------------------------------------------


@pytest.fixture
def con(tmp_path):
    c = oeffnen(tmp_path / "t.db")
    yield c
    c.close()


def test_hf_cache_schreiben_lesen_veraltet(con) -> None:
    assert schema_version(con) >= 35
    s = Subject(name="Ich")
    SubjectRepo(con).speichern(s)
    hrv = HrvRepo(con)
    r = HrvRecording(
        subject_id=s.id, file_path="P/a.json", started_at=datetime(2026, 10, 20, tzinfo=UTC)
    )
    hrv.anlegen(r)

    repo = HfCacheRepo(con)
    assert repo.lesen(r.id) is None and repo.fehlende(s.id) == [r.id]
    profil = _profil()
    bereiche = bereiche_fuer(profil, HfEinstellungen(modell="drei"))
    a = auswerten(_rec([100.0] * 120), profil=profil, bereiche=bereiche)
    repo.schreiben(r.id, a)
    stand = repo.lesen(r.id)
    assert stand is not None and stand.auswertung.gesamt == a.gesamt
    assert not stand.veraltet(profil_stand(profil, bereiche))
    anderes = profil_stand(_profil(), bereiche_fuer(_profil(), HfEinstellungen(modell="acsm")))
    assert stand.veraltet(anderes) and not stand.veraltet()
    assert repo.fehlende(s.id) == [] and len(repo.alle(s.id)) == 1
    # eine ältere Rechenvorschrift der App: veraltet, und „Alle nachrechnen“ holt sie nach
    alt_stand = HfAuswertung.aus_dict({**a.als_dict(), "version": 1})
    repo.schreiben(r.id, alt_stand)
    assert repo.lesen(r.id).veraltet() and repo.fehlende(s.id) == [r.id]
    repo.schreiben(r.id, a)  # Upsert
    assert len(repo.alle(s.id)) == 1
    repo.loeschen(r.id)
    assert repo.lesen(r.id) is None


# -- Verlauf ------------------------------------------------------------------------------


def test_wochenlast_monotonie_strain_und_srpe() -> None:
    mo = date(2026, 10, 5)
    t = tageslasten(
        [(mo, 40.0, 30), (mo + timedelta(days=2), 80.0, 60), (mo + timedelta(days=4), None, 20)],
        {mo: 5, mo + timedelta(days=4): 3},
    )
    assert [x.trimp for x in t] == [40.0, 80.0, None]
    assert [x.srpe_last for x in t] == [150.0, None, 60.0]
    w = wochenlasten(t)
    assert len(w) == 1 and w[0].trimp == 120.0 and w[0].srpe_last == 210.0 and w[0].minuten == 110
    taeglich = np.array([40, 0, 80, 0, 0, 0, 0], dtype=float)
    assert w[0].monotonie == pytest.approx(taeglich.mean() / taeglich.std())
    assert w[0].strain == pytest.approx(120 * w[0].monotonie)
    einzel = wochenlasten([Tageslast(mo, 40.0, None, 30)])
    assert einzel[0].monotonie is None  # ein Lasttag: keine Monotonie


def test_baseline_reihe_mit_ausnahme() -> None:
    werte = [(date(2026, 10, i), 50.0) for i in range(1, 8)] + [
        (date(2026, 10, 8), 80.0),
        (date(2026, 10, 9), 50.0),
    ]
    ohne = baseline_reihe(werte)
    mit = baseline_reihe(werte, ausgenommen={date(2026, 10, 8)})
    assert ohne[-1].oben > mit[-1].oben  # der Ausreißer weitet das Band nur ohne Ausnahme
    assert mit[-2].wert == 80.0 and mit[-2].median == 50.0  # Punkt bleibt, zählt nicht


def test_testreihe_gruppiert() -> None:
    p = [
        Testpunkt(date(2026, 10, 1), "a", "Submaximaltest", 30, 160, 140),
        Testpunkt(date(2026, 10, 8), "b", "Submaximaltest", 34, 158, 139),
        Testpunkt(date(2026, 10, 3), "c", "Talk-Test", None, None, 120),
    ]
    r = hf_testreihe(p, ausgenommen={date(2026, 10, 3)})
    assert list(r) == ["Submaximaltest"] and [x.hrr60 for x in r["Submaximaltest"]] == [30, 34]
