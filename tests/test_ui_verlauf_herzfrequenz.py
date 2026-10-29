"""Verlauf → Herzfrequenz (Stufe 3, Ben 29.10.2026): Ruhe-HF mit Baseline, Wochenlast aus dem
HF-Cache und dem Tagesfeld „Anstrengung“, Tests, „Alle nachrechnen“. Ohne Fenster."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from hrv_core.recording import Beat, Recording, speichern  # noqa: E402

from attrappen import aufgabe_starten  # noqa: E402
from trainingsapp.core import tagesfelder as tf  # noqa: E402
from trainingsapp.core.hf_auswertung import HfAuswertung  # noqa: E402
from trainingsapp.core.hf_profil import Profilwert  # noqa: E402
from trainingsapp.core.models import HrvRecording  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.verlauf_herzfrequenz import (  # noqa: E402
    testpunkte_aus_cache as hf_testpunkte,
)
from trainingsapp.ui.views.verlauf_herzfrequenz import (  # noqa: E402
    verlauf_herzfrequenz_view,
)


@pytest.fixture
def daten(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    yield state, tmp_path
    state.schliessen()


def _seite() -> SimpleNamespace:
    aufgaben: list = []
    aufrufe: list = []
    return SimpleNamespace(
        route="/verlauf/herzfrequenz",
        views=[],
        update=lambda: None,
        show_dialog=aufrufe.append,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: aufgabe_starten(aufgaben, f, *a),
        aufgaben=aufgaben,
        aufrufe=aufrufe,
    )


def _texte(wurzel) -> list[str]:
    gesehen: set[int] = set()
    out: list[str] = []

    def lauf(x) -> None:
        if not isinstance(x, ft.BaseControl) or id(x) in gesehen:
            return
        gesehen.add(id(x))
        if isinstance(x, ft.Text) and x.value:
            out.append(x.value)
        for name in ("controls", "content", "title", "subtitle", "label"):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                lauf(k)

    lauf(wurzel)
    return out


def _cache(gesamt: dict, abschnitte: list | None = None, talk: dict | None = None) -> HfAuswertung:
    return HfAuswertung(gesamt, abschnitte or [], [], None, None, None, talk, [], None, {})


def test_testpunkte_erkennen_die_standardtests() -> None:
    a = _cache(
        {},
        [
            {"name": "Einlaufen", "werte": {}, "erholung": None},
            {"name": "Stufe 3", "werte": {}, "erholung": None},
            {"name": "Alles", "werte": {}, "erholung": None},
            {"name": "Stehen", "werte": {}, "erholung": None},
        ],
        talk={"wert": 131.0},
    )
    a.hfmax_kandidat = {"wert": 188.0}
    namen = [p.name for p in hf_testpunkte("r", date(2026, 10, 1), a)]
    assert namen == ["Feld-Maximaltest", "Talk-Test"]  # mit „Alles“ kein Submaximaltest


def test_verlauf_herzfrequenz_zeigt_baseline_wochenlast_und_tests(daten) -> None:
    state, _tmp_path = daten
    heute = state.heute()
    p = state.profil
    for i in range(8):
        state.profilwerte.hinzufuegen(
            Profilwert(p.id, "ruhe_hf", 54 + i % 3, "messung_morgen_5", heute - timedelta(days=i))
        )
    # zwei Aufnahmen mit Cache in dieser und der vorigen Woche
    for i, trimp in ((1, 40.0), (9, 25.0)):
        start = datetime.combine(heute - timedelta(days=i), datetime.min.time()).replace(
            hour=7, tzinfo=UTC
        )
        rec = HrvRecording(subject_id=p.id, file_path=f"P/{i}.json", started_at=start)
        state.hrv.anlegen(rec)
        state.hf_cache.schreiben(
            rec.id,
            _cache(
                {"trimp": trimp, "gueltig_s": 1800.0},
                [
                    {"name": "Stufe 2", "werte": {"mittel_bpm": 140}, "erholung": None},
                    {
                        "name": "Stufe 3",
                        "werte": {"mittel_bpm": 160},
                        "erholung": {"hf_ende": 162, "hrr": {"60": 30 + i}},
                    },
                    {"name": "Stehen", "werte": {}, "erholung": None},
                ],
            ),
        )
    srpe = tf.standardfeld(state.tagesfelder.alle(p.id), tf.STANDARD_SRPE)
    state.tageswerte.einmal_setzen(srpe, heute - timedelta(days=1), wert=6)
    seite = _seite()
    ansicht = verlauf_herzfrequenz_view(seite, state)
    texte = _texte(ansicht)
    assert "RUHE-HF UND NACHT-HF" in texte and "Morgenmessung 5 min" in texte
    assert "WOCHENLAST" in texte and "TESTS" in texte and "Submaximaltest" in texte
    assert any("HRR60 −31" in t for t in texte) and any("HRR60 −39" in t for t in texte)
    assert "180" in texte  # sRPE-Last 6 × 30 min
    assert any(t.startswith("0 Aufnahmen ohne") for t in texte)
    # Ausnahme: die Messung von gestern zählt nicht mehr
    rid = next(r for r in state.hrv.alle(p.id) if r.file_path == "P/1.json").id
    state.ausnahmen.setzen(p.id, "hrv_recording", rid)
    texte = _texte(verlauf_herzfrequenz_view(seite, state))
    assert not any("HRR60 −31" in t for t in texte)
    # Zeitraum umschalten
    wahl = next(c for c in _alle(ansicht) if isinstance(c, ft.SegmentedButton))
    wahl.on_change(SimpleNamespace(control=SimpleNamespace(selected=["4w"])))
    assert state.verlauf_zeitraum == "4w"


def _alle(wurzel):
    gesehen: set[int] = set()

    def lauf(x):
        if not isinstance(x, ft.BaseControl) or id(x) in gesehen:
            return
        gesehen.add(id(x))
        yield x
        for name in ("controls", "content", "title", "subtitle", "label"):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                yield from lauf(k)

    yield from lauf(wurzel)


def test_alle_nachrechnen_fuellt_den_cache(daten) -> None:
    state, tmp_path = daten
    beats, t = [], 0.0
    for _ in range(300):
        t += 0.8
        beats.append(Beat(t_s=round(t, 3), rr_ms=800, hf_bpm=75, t_wall_s=round(t, 3)))
    rec = Recording(beats=beats, geraet="Polar H10", geraet_profil="polar_h10")
    pfad = speichern(rec, tmp_path / "Messungen" / "PolarH10")
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        started_at=datetime.now(UTC),
    )
    state.hrv.anlegen(eintrag)
    seite = _seite()
    ansicht = verlauf_herzfrequenz_view(seite, state)
    assert any(t.startswith("1 Aufnahmen ohne") for t in _texte(ansicht))
    knopf = next(
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.TextButton) and c.content == "Alle nachrechnen"
    )
    knopf.on_click()
    assert state.hf_cache.lesen(eintrag.id) is not None
    assert state.hf_cache.lesen(eintrag.id).auswertung.gesamt["mittel_bpm"] == pytest.approx(75)
