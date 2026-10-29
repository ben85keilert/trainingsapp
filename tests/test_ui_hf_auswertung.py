"""Herzfrequenz-Sicht der Auswertung `/messung/<id>` (Stufe 2, Ben 29.10.2026): Umschalter,
Kacheln, Abschnittstabelle, Kandidaten übernehmen, Vorschlag als Abschnitt, Cache und
Nachrechnen mit heutigem Profil, sRPE und „nicht mitrechnen“. Ohne Fenster."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from hrv_core.recording import Beat, Recording, speichern  # noqa: E402

from attrappen import aufgabe_starten  # noqa: E402
from trainingsapp.core.hf_profil import Profilwert  # noqa: E402
from trainingsapp.core.models import HrvRecording  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.messung_detail import messung_detail_view  # noqa: E402


@pytest.fixture
def daten(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    yield state, tmp_path
    state.schliessen()


def _seite() -> SimpleNamespace:
    aufrufe: list = []
    aufgaben: list = []
    s = SimpleNamespace(
        route="/",
        views=[],
        update=lambda: None,
        show_dialog=aufrufe.append,
        pop_dialog=lambda: None,
        run_task=lambda f, *a, **kw: aufgabe_starten(aufgaben, f, *a, **kw),
        aufgaben=aufgaben,
        aufrufe=aufrufe,
        height=900,
        width=412,
    )
    return s


def _alle(wurzel):
    gesehen: set[int] = set()

    def lauf(x):
        if not isinstance(x, ft.BaseControl) or id(x) in gesehen:
            return
        gesehen.add(id(x))
        yield x
        for name in ("controls", "content", "title", "subtitle", "actions", "label", "leading"):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                yield from lauf(k)

    yield from lauf(wurzel)


def _texte(wurzel) -> list[str]:
    return [c.value for c in _alle(wurzel) if isinstance(c, ft.Text) and c.value]


def _knopf(wurzel, text: str):
    return next(
        c
        for c in _alle(wurzel)
        if isinstance(c, ft.TextButton | ft.FilledButton | ft.FilledTonalButton)
        and c.content == text
    )


def _segment(wurzel, werte: list[str]) -> ft.SegmentedButton:
    return next(
        c
        for c in _alle(wurzel)
        if isinstance(c, ft.SegmentedButton) and [s.value for s in c.segments] == werte
    )


def _aufzeichnung(state: AppState, tmp_path, hf: list[float]) -> tuple[HrvRecording, object]:
    """Eine Messdatei mit einem Schlag je Sekunde (RR aus der HF) und Marke Erholung."""
    beats, t = [], 0.0
    for h in hf:
        rr = round(60000 / h)
        t += rr / 1000
        beats.append(Beat(t_s=round(t, 3), rr_ms=rr, hf_bpm=int(h), t_wall_s=round(t, 3)))
    rec = Recording(
        beats=beats,
        geraet="Polar H10 TEST",
        geraet_profil="polar_h10",
        start_utc=datetime(2026, 10, 28, 6, 0, tzinfo=UTC),
    )
    rec.ereignisse.append(
        {
            "beat_index": 899,
            "dt_s": 0.0,
            "t_wall_s": 900.0,
            "t_s": 900.0,
            "wall_time": "08:15:00",
            "text": "Belastung beendet",
            "marke": {
                "quelle": "person",
                "art": "erholung",
                "kontext": "dauer",
                "haltung": "steht",
            },
        }
    )
    ordner = tmp_path / "Messungen" / "PolarH10"
    pfad = speichern(rec, ordner)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="Polar H10 TEST",
        geraet_profil="polar_h10",
        started_at=rec.start_utc,
        duration_s=len(hf),
    )
    state.hrv.anlegen(eintrag)
    return eintrag, pfad


def _profil(state: AppState) -> None:
    p = state.profil
    p.birth_year, p.geschlecht = 1986, "m"
    state.profil_speichern(p)
    state.profilwerte.hinzufuegen(Profilwert(p.id, "ruhe_hf", 55, "eintrag", date(2026, 10, 1)))


async def _hf_sicht(seite, state, eintrag):
    ansicht = messung_detail_view(seite, state, eintrag)
    await _abwarten(seite)
    return ansicht


async def _abwarten(seite) -> None:
    while seite.aufgaben:
        aufgaben = list(seite.aufgaben)
        seite.aufgaben.clear()
        await asyncio.gather(*aufgaben, return_exceptions=True)


async def test_hf_sicht_der_auswertung_mit_kandidaten_und_vorschlag(daten) -> None:
    state, tmp_path = daten
    _profil(state)
    # 5 min Ruhe (60), 10 min Belastung (165), 3 min Erholung
    hf = [60.0] * 300 + [165.0] * 600 + [165 - i * 0.5 for i in range(180)]
    eintrag, pfad = _aufzeichnung(state, tmp_path, hf)
    seite = _seite()
    ansicht = await _hf_sicht(seite, state, eintrag)
    texte = _texte(ansicht)
    # Vorgabe Herzfrequenz: HF-Kacheln, Kurve, Kandidaten; HRV-Teil unsichtbar
    assert "Ø Herzfrequenz" in texte and "HERZFREQUENZ · GANZE AUFNAHME" in texte
    assert any(t.startswith("Höchstes 30-s-Mittel: 165") for t in texte)
    assert any(t.startswith("Ruhe-HF dieser Messung: 60") for t in texte)
    assert "ERHOLUNGEN · 1" in texte and "VORGESCHLAGENE ABSCHNITTE" in texte
    assert any(t.startswith("Gerechnet mit Ruhe 55") for t in texte)
    hrv_spalte = next(
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.Column)
        and any(isinstance(x, ft.Container) for x in c.controls)
        and c.visible is False
    )
    assert hrv_spalte is not None
    # Cache geschrieben
    stand = state.hf_cache.lesen(eintrag.id)
    assert stand is not None and stand.auswertung.hfmax_kandidat["wert"] == pytest.approx(
        165, abs=1
    )
    # HFmax übernehmen → Profilwert mit Herkunft; danach „Profil ist seither anders“
    _knopf(ansicht, "Als HFmax übernehmen").on_click()
    werte = state.profilwerte.alle(state.profil.id, "hf_max")
    assert len(werte) == 1 and werte[0].quelle == "feldmaximum"
    assert werte[0].hrv_recording_id == eintrag.id and werte[0].herkunft["messung"] == eintrag.id
    assert state.hf_profil().hfmax_bpm == pytest.approx(165, abs=1)
    texte = _texte(ansicht)
    assert "Dein Profil ist seither anders." in texte
    # Nachrechnen mit heutigem Profil → ungespeichert, Speichern fragt
    _knopf(ansicht, "Mit heutigem Profil nachrechnen").on_click()
    await _abwarten(seite)
    texte = _texte(ansicht)
    assert "Nachgerechnet, nicht gespeichert." in texte
    assert state.hf_cache.lesen(eintrag.id).profil_stand["hfmax"] == pytest.approx(
        185.4
    )  # noch alt
    _knopf(ansicht, "Speichern").on_click()
    dialog = seite.aufrufe[-1]
    assert isinstance(dialog, ft.AlertDialog)
    next(a for a in dialog.actions if isinstance(a, ft.FilledButton)).on_click()
    assert state.hf_cache.lesen(eintrag.id).profil_stand["hfmax"] == pytest.approx(165, abs=1)
    # Ruhe-HF ins Tagesfeld und als Profilwert
    _knopf(ansicht, "Ins Tagesfeld Ruhepuls").on_click()
    tag = eintrag.started_at.astimezone().date()
    assert any(w.wert == 60 for w in state.tageswerte.am_tag(state.profil.id, tag))
    _knopf(ansicht, "Als Ruhe-HF übernehmen").on_click()
    ruhe = state.profilwerte.alle(state.profil.id, "ruhe_hf")
    assert ruhe[-1].quelle == "messung_morgen_10" and ruhe[-1].wert == pytest.approx(60, abs=0.5)
    # Vorschlag übernehmen → eigener Abschnitt (Notizpaar in der Datei) und neue Tabelle
    _knopf(ansicht, "Übernehmen").on_click()
    await _abwarten(seite)
    from hrv_core.recording import laden

    rec = laden(pfad)
    marken = [e["marke"]["art"] for e in rec.ereignisse if isinstance(e.get("marke"), dict)]
    assert "abschnitt" in marken and "ende" in marken
    texte = _texte(ansicht)
    assert any(t.startswith("ABSCHNITTE · 1") for t in texte)
    # „nicht mitrechnen“ und sRPE
    schalter = next(
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.Switch) and c.label == "Diese Messung nicht mitrechnen"
    )
    schalter.on_change(SimpleNamespace(control=SimpleNamespace(value=True)))
    assert state.ausnahmen.ist(state.profil.id, "hrv_recording", eintrag.id)
    assert "Anstrengung (sRPE)" in texte
    # Umschalten auf HRV
    _segment(ansicht, ["hf", "hrv"]).on_change(
        SimpleNamespace(control=SimpleNamespace(selected=["hrv"]))
    )
    assert state.hrv_sicht() == "hrv"
    assert any(t.startswith("Datei: ") for t in _texte(ansicht))


async def test_hf_sicht_ohne_profil_und_hrv_vorgabe(daten) -> None:
    state, tmp_path = daten
    hf = [70.0] * 200
    eintrag, _ = _aufzeichnung(state, tmp_path, hf)
    state.hrv_sicht_setzen("hrv")
    seite = _seite()
    ansicht = await _hf_sicht(seite, state, eintrag)
    assert _segment(ansicht, ["hf", "hrv"]).selected == ["hrv"]
    # HF-Sicht wird erst gerechnet, wenn sie gezeigt wird
    assert state.hf_cache.lesen(eintrag.id) is None
    _segment(ansicht, ["hf", "hrv"]).on_change(
        SimpleNamespace(control=SimpleNamespace(selected=["hf"]))
    )
    await _abwarten(seite)
    texte = _texte(ansicht)
    assert "Gerechnet ohne Ruhe-HF/HFmax — keine Reserve, keine Bereiche." in texte
    assert state.hf_cache.lesen(eintrag.id) is not None
