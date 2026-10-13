"""Rauchtests der Messansichten — mit Simulator und gespeicherten Dateien, ohne Fenster."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import HrvRecording  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource  # noqa: E402
from trainingsapp.hrv_core.korrektur import analyse_laden  # noqa: E402
from trainingsapp.hrv_core.recording import Beat, Recording, speichern  # noqa: E402
from trainingsapp.hrv_core.regeln import Korrekturregeln  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.messung import messung  # noqa: E402
from trainingsapp.ui.views.messung_detail import messung_detail_view  # noqa: E402


@pytest.fixture
def daten(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    yield state, tmp_path
    state.schliessen()


def _seite() -> SimpleNamespace:
    aufrufe: list[object] = []
    return SimpleNamespace(
        route="/",
        views=[],
        update=lambda: None,
        show_dialog=aufrufe.append,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: None,
        aufrufe=aufrufe,
    )


def _baum_texte(c) -> list[str]:
    """Alle Texte im Control-Baum — um zu prüfen, was angezeigt wird."""
    gesehen: set[int] = set()
    texte: list[str] = []

    def lauf(x) -> None:
        if not isinstance(x, ft.Control) or id(x) in gesehen:
            return
        gesehen.add(id(x))
        if isinstance(x, ft.Text) and x.value:
            texte.append(x.value)
        for name in ("controls", "content", "title", "subtitle", "leading", "trailing"):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                lauf(k)

    lauf(c)
    return texte


def test_messung_ohne_geraet(daten) -> None:
    state, _ = daten
    texte = _baum_texte(messung(_seite(), state))
    assert "Gerät verbinden" in texte
    assert "Ohne Gerät ausprobieren:" in texte
    assert "Noch keine Aufzeichnung." in texte


async def test_messung_live_mit_simulator(daten) -> None:
    state, tmp_path = daten
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 40:
        await asyncio.sleep(0.01)

    seite = _seite()
    ansicht = messung(seite, state)
    texte = _baum_texte(ansicht)
    assert "Herzfrequenz" in texte and "RMSSD 30 s" in texte
    assert any(t.startswith("Aufnahme ") for t in texte)
    assert lauf.beobachter is not None
    lauf.beobachter(False)  # Auffrischen ohne Seite darf nichts werfen
    for fenster in (60, 120, 300):
        state.messung_fenster_s = fenster
        state.messung_korrigiert = fenster != 120
        assert messung(seite, state) is not None

    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None and ergebnis.pfad.exists()


def test_detailansicht_mit_artefakt_korrigieren_und_speichern(daten) -> None:
    state, tmp_path = daten
    rr = [800 + (15 if i % 2 else -15) for i in range(120)]
    rr[60] = 1650  # ausgelassener Schlag
    beats, t = [], 0.0
    for x in rr:
        t += x / 1000
        beats.append(Beat(t_s=round(t, 3), rr_ms=x, hf_bpm=75, t_wall_s=round(t, 3)))
    rec = Recording(beats=beats, geraet="Polar H10 TEST", geraet_profil="polar_h10")
    ordner = tmp_path / "Messungen" / "PolarH10"
    pfad = speichern(rec, ordner)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="Polar H10 TEST",
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)

    seite = _seite()
    ansicht = messung_detail_view(seite, state, eintrag)
    assert ansicht.route == f"/messung/{eintrag.id}"
    texte = _baum_texte(ansicht)
    assert any("interpolieren" in x for x in texte)

    # „Alle" übernehmen und speichern — über die Knöpfe der Ansicht
    knoepfe = {
        getattr(c, "content", None) if isinstance(getattr(c, "content", None), str) else None: c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.TextButton | ft.FilledButton)
    }
    knoepfe["Alle"].on_click()
    asyncio.run(knoepfe["Korrektur speichern"].on_click())
    assert [k.beat_index for k in analyse_laden(pfad)] == [60]
    assert pfad.read_text(encoding="utf-8").count('"rr_ms": 1650') == 1  # Rohdatei unverändert

    # Liste im Reiter zeigt die Aufzeichnung — und bietet den Export an
    liste = messung(seite, state)
    assert "Noch keine Aufzeichnung." not in _baum_texte(liste)
    export = [
        c
        for c in _alle_controls(liste)
        if isinstance(c, ft.TextButton) and c.content == "Alle exportieren"
    ]
    assert len(export) == 1 and export[0].visible
    assert any(
        isinstance(c, ft.IconButton) and c.tooltip == "Exportieren (ZIP)"
        for c in ansicht.appbar.actions
    )


def test_detailansicht_ohne_datei(daten) -> None:
    state, _ = daten
    eintrag = HrvRecording(subject_id=state.profil.id, file_path="PolarH10/fehlt.json")
    state.hrv.anlegen(eintrag)
    assert "Die Messdatei fehlt." in _baum_texte(messung_detail_view(_seite(), state, eintrag))


def _alle_controls(wurzel) -> list:
    gesehen: set[int] = set()
    alle: list = []

    def lauf(x) -> None:
        if not isinstance(x, ft.Control) or id(x) in gesehen:
            return
        gesehen.add(id(x))
        alle.append(x)
        for name in ("controls", "content", "title", "subtitle", "leading", "trailing"):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                lauf(k)

    lauf(wurzel)
    return alle


@pytest.mark.parametrize(
    ("profil", "quelle", "markiert"),
    [
        ("polar_h10", "ekg_rr", True),
        ("verity_sense", "ppg_ppi", False),
    ],
)
def test_detailansicht_schwelle_nach_intervallquelle(daten, profil, quelle, markiert) -> None:
    """Sprung um ein gutes Viertel: bei EKG ein Artefakt (0.20), optisch nicht (0.30)."""
    state, tmp_path = daten
    rr = [800 + (10 if i % 2 else -10) for i in range(120)]
    rr[60] = 1100
    beats, t = [], 0.0
    for x in rr:
        t += x / 1000
        beats.append(Beat(t_s=round(t, 3), rr_ms=x, hf_bpm=75, t_wall_s=round(t, 3)))
    rec = Recording(beats=beats, geraet="TEST", geraet_profil=profil, intervall_quelle=quelle)
    pfad = speichern(rec, tmp_path / "Messungen" / "Test")
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="TEST",
        geraet_profil=profil,
        intervall_quelle=quelle,
    )
    state.hrv.anlegen(eintrag)
    texte = _baum_texte(messung_detail_view(_seite(), state, eintrag))
    assert any("Malik" in x for x in texte) is markiert


def test_detailansicht_meldet_verworfene_intervalle(daten) -> None:
    """Golden-PPI-Datei (9 % verworfen) und eine in Bewegung (75 %): Kopfzeile, Hinweis."""
    import shutil
    from pathlib import Path

    state, tmp_path = daten
    golden = Path(__file__).parent / "golden" / "rr" / "sensor_2026-10-13_000000.json"
    ordner = tmp_path / "Messungen" / "VeritySense"
    ordner.mkdir(parents=True)
    pfad = ordner / golden.name
    shutil.copy(golden, pfad)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="Polar Sense SYNTH",
        geraet_profil="verity_sense",
        intervall_quelle="ppg_ppi",
    )
    state.hrv.anlegen(eintrag)
    ansicht = messung_detail_view(_seite(), state, eintrag)
    texte = _baum_texte(ansicht)
    assert any("9 % vom Sensor verworfen" in x for x in texte)
    hinweis = [
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.Text) and "die meisten Intervalle" in (c.value or "")
    ]
    assert len(hinweis) == 1 and not hinweis[0].visible

    # Dieselbe Folge, aber drei von vier Intervallen verworfen
    rec = Recording(
        beats=[
            Beat(t_s=0.8 * (i + 1), rr_ms=800, hf_bpm=75, t_wall_s=3.2 * (i + 1)) for i in range(30)
        ],
        geraet_profil="verity_sense",
        intervall_quelle="ppg_ppi",
        ppi_pakete=[
            {
                "t_wall_s": 3.2 * (i + 1),
                "ppi_ms": [800] * 4,
                "fehler_ms": [10] * 4,
                "blocker": [1, 1, 1, 0],
                "kontakt": [1] * 4,
            }
            for i in range(30)
        ],
    )
    pfad2 = speichern(rec, ordner)
    eintrag2 = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad2.relative_to(tmp_path / "Messungen").as_posix(),
        geraet_profil="verity_sense",
        intervall_quelle="ppg_ppi",
    )
    state.hrv.anlegen(eintrag2)
    ansicht2 = messung_detail_view(_seite(), state, eintrag2)
    assert any("75 % vom Sensor verworfen" in x for x in _baum_texte(ansicht2))
    hinweis2 = [
        c
        for c in _alle_controls(ansicht2)
        if isinstance(c, ft.Text) and "die meisten Intervalle" in (c.value or "")
    ]
    assert hinweis2[0].visible
    # Vorgabe „selbst": wieder aufgenommen, kein Bruchstück-Hinweis
    assert "wieder aufgenommen" in (hinweis2[0].value or "")
    assert any("90 davon selbst geprüft" in x for x in _baum_texte(ansicht2))

    # Wer dem Sensor folgt, bekommt den alten Hinweis
    state.korrekturregeln_setzen(Korrekturregeln(sensor_verwerfung="sensor"))
    ansicht3 = messung_detail_view(_seite(), state, eintrag2)
    hinweis3 = [
        c
        for c in _alle_controls(ansicht3)
        if isinstance(c, ft.Text) and "die meisten Intervalle" in (c.value or "")
    ]
    assert "Bruchstücken" in (hinweis3[0].value or "")


def test_detailansicht_zeigt_verworfene_grau_auf_voller_zeitachse(daten) -> None:
    """Graue Linie über alle Intervalle, auch verworfene; Dauer und Achse inklusive."""
    import shutil
    from pathlib import Path

    import flet_charts as fc

    from trainingsapp.hrv_core.ppi import ppi_folge
    from trainingsapp.hrv_core.recording import laden

    state, tmp_path = daten
    golden = Path(__file__).parent / "golden" / "rr" / "sensor_2026-10-13_000000.json"
    ordner = tmp_path / "Messungen" / "VeritySense"
    ordner.mkdir(parents=True)
    pfad = ordner / golden.name
    shutil.copy(golden, pfad)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="Polar Sense SYNTH",
        geraet_profil="verity_sense",
        intervall_quelle="ppg_ppi",
    )
    state.hrv.anlegen(eintrag)
    ansicht = messung_detail_view(_seite(), state, eintrag)
    folge = ppi_folge(laden(pfad))
    assert folge is not None
    dauer = folge[-1].t_s

    # Tachogramm, darunter die Vorgabe-Ansicht: Ø HF aus RR, RMSSD
    rr_kurve, hf_kurve, rmssd_kurve = [
        c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart)
    ]
    grau = rr_kurve.data_series[0]
    assert len(grau.points) == 300  # alle Intervalle, eine durchgehende Linie
    assert rr_kurve.max_x == hf_kurve.max_x == rmssd_kurve.max_x == pytest.approx(dauer)
    texte = _baum_texte(ansicht)
    assert any(f"{int(dauer) // 60}:{int(dauer) % 60:02d}" in x for x in texte)
    assert any("auch verworfene" in x for x in texte)
    for kurve in (rr_kurve, hf_kurve):
        achse = kurve.left_axis
        assert not achse.show_min and not achse.show_max
        assert all(label.value % achse.label_spacing == 0 for label in achse.labels)


# ---------------------------------------------------------------------------
# Einstellblatt, Verlaufskurven, Zeitfenster
# ---------------------------------------------------------------------------


def test_korrektur_blatt_aendert_regeln() -> None:
    from trainingsapp.ui.components.korrektur_blatt import korrektur_blatt

    stand: list[Korrekturregeln] = []
    blatt = korrektur_blatt(Korrekturregeln(), stand.append, erweitert=True, verity=True)
    alle = _alle_controls(blatt)
    texte = _baum_texte(blatt)
    assert "Automatische Korrektur" in texte and "KETTEN" in texte

    schalter = {c.label: c for c in alle if isinstance(c, ft.Switch)}
    schalter["Verworfene Intervalle selbst prüfen"].on_change(_ereignis(False))
    assert stand[-1].sensor_verwerfung == "sensor"

    auswahl = {c.label: c for c in _alle_controls(blatt) if isinstance(c, ft.Dropdown)}
    auswahl["Schwelle"].on_select(_ereignis("0.25"))
    assert stand[-1].malik == 0.25 and stand[-1].sensor_verwerfung == "sensor"
    auswahl = {c.label: c for c in _alle_controls(blatt) if isinstance(c, ft.Dropdown)}
    auswahl["Schwelle"].on_select(_ereignis("auto"))
    assert stand[-1].malik is None
    auswahl["Sicher bis"].on_select(_ereignis("3"))
    assert stand[-1].auto_max == 3

    # Live: nur die Erkennung, ohne Verity auch ohne Sensor-Teil
    live = _baum_texte(korrektur_blatt(Korrekturregeln(), stand.append))
    assert "KETTEN" not in live and "SENSOR" not in live and "AUSREISSER" in live


def _ereignis(wert) -> SimpleNamespace:
    return SimpleNamespace(control=SimpleNamespace(value=wert, selected=[wert]))


async def test_messung_live_verity_mit_verlauf_und_wischen(daten) -> None:
    import flet_charts as fc

    from trainingsapp.devices.simulated import SIM_PPI

    state, tmp_path = daten
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_PPI, "Simulator Verity")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    while lauf.jetzt_s() < 150:
        await asyncio.sleep(0.01)

    seite = _seite()
    ansicht = messung(seite, state)
    charts = [c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart)]
    assert len(charts) == 3  # PPI, Ø HF aus RR, RMSSD
    assert charts[0].left_axis.title.value == "PPI ms"
    assert len({c.max_x for c in charts}) == 1

    # Chip SDNN dazu: teilt sich mit RMSSD das ms-Diagramm
    chip = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.Chip) and getattr(c.label, "value", "") == "SDNN"
    )
    chip.on_select()
    assert state.ansicht().kurven == ["hf_rr", "rmssd", "sdnn"]
    charts = [c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart)]
    assert len(charts) == 3 and len(charts[2].data_series) >= 2

    # Waagrecht wischen blättert zurück, „Live" kehrt zurück
    wisch = next(c for c in _alle_controls(ansicht) if isinstance(c, ft.GestureDetector))
    ende_vorher = charts[0].max_x
    wisch.on_horizontal_drag_update(SimpleNamespace(primary_delta=160.0, local_delta=None))
    wisch.on_horizontal_drag_end(None)
    assert state.messung_ende_s is not None
    charts = [c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart)]
    assert charts[0].max_x < ende_vorher
    live = next(
        c for c in _alle_controls(ansicht) if isinstance(c, ft.TextButton) and c.content == "Live"
    )
    live.on_click()
    assert state.messung_ende_s is None

    # Regler: Blatt öffnet sich, Umschalten wirkt auf den Messlauf
    regler = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.TUNE
    )
    regler.on_click()
    blatt = seite.aufrufe[-1]
    assert isinstance(blatt, ft.BottomSheet)
    sensor = next(
        c
        for c in _alle_controls(blatt)
        if isinstance(c, ft.Switch) and c.label == "Verworfene Intervalle selbst prüfen"
    )
    sensor.on_change(_ereignis(False))
    assert not lauf.regeln.selbst_pruefen and not state.korrekturregeln().selbst_pruefen

    await lauf.trennen()
    await asyncio.wait_for(task, 5)


def test_detailansicht_regeln_je_messung_und_lupe(daten) -> None:
    import shutil
    from pathlib import Path

    import flet_charts as fc

    from trainingsapp.hrv_core.korrektur import analyse_regeln

    state, tmp_path = daten
    golden = Path(__file__).parent / "golden" / "rr" / "sensor_2026-10-13_000000.json"
    ordner = tmp_path / "Messungen" / "VeritySense"
    ordner.mkdir(parents=True)
    pfad = ordner / golden.name
    shutil.copy(golden, pfad)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet_profil="verity_sense",
        intervall_quelle="ppg_ppi",
    )
    state.hrv.anlegen(eintrag)
    seite = _seite()
    ansicht = messung_detail_view(seite, state, eintrag)
    texte = _baum_texte(ansicht)
    assert any("26 davon selbst geprüft" in x for x in texte)
    i = texte.index("Schläge")
    assert texte[i + 1 : i + 3] == ["300 ", "300 "]  # Vorauswahl: interpoliert, nichts entfernt

    # Lupe zoomt auf die Kette (Intervall 150, Sensor unsicher)
    lupe = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.IconButton) and c.tooltip == "In der Kurve zeigen"
    )
    lupe.on_click()
    rr = next(c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart))
    assert rr.max_x - rr.min_x == pytest.approx(60)

    # Regeln je Messung: dem Sensor folgen, speichern — die Vorgabe bleibt
    next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.TUNE
    ).on_click()
    sensor = next(
        c
        for c in _alle_controls(seite.aufrufe[-1])
        if isinstance(c, ft.Switch) and c.label == "Verworfene Intervalle selbst prüfen"
    )
    sensor.on_change(_ereignis(False))
    texte = _baum_texte(ansicht)
    assert not any("selbst geprüft" in x for x in texte)
    knopf = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.FilledButton) and c.content == "Korrektur speichern"
    )
    assert not knopf.disabled
    asyncio.run(knopf.on_click())
    assert analyse_regeln(pfad) is not None and not analyse_regeln(pfad).selbst_pruefen
    assert state.korrekturregeln().selbst_pruefen
    # Wieder geöffnet: mit den Regeln der Messung
    assert not any(
        "selbst geprüft" in x for x in _baum_texte(messung_detail_view(seite, state, eintrag))
    )


# ---------------------------------------------------------------------------
# Notizen
# ---------------------------------------------------------------------------


def _knopf(wurzel, text: str):
    return next(
        c
        for c in _alle_controls(wurzel)
        if isinstance(c, ft.TextButton | ft.FilledButton) and c.content == text
    )


def _symbol(wurzel, icon, tooltip: str | None = None):
    return next(
        c
        for c in _alle_controls(wurzel)
        if isinstance(c, ft.IconButton)
        and c.icon == icon
        and (tooltip is None or c.tooltip == tooltip)
    )


def test_detailansicht_notiz_setzen_verschieben_loeschen(daten) -> None:
    """Notiz in die Kurve tippen, ±5 s, speichern — landet als ``ereignisse`` in der Datei."""
    import json
    import shutil
    from pathlib import Path

    import flet_charts as fc

    from trainingsapp.hrv_core.ereignisse import herz_position
    from trainingsapp.hrv_core.recording import laden

    state, tmp_path = daten
    ordner = tmp_path / "Messungen" / "PolarH10"
    ordner.mkdir(parents=True)
    golden = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"
    pfad = ordner / golden.name
    shutil.copy(golden, pfad)
    messwerte = json.loads(pfad.read_text(encoding="utf-8"))["messungen"]
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)
    seite = _seite()
    ansicht = messung_detail_view(seite, state, eintrag)
    assert "NOTIZEN" in _baum_texte(ansicht)

    _knopf(ansicht, "Notiz").on_click()
    assert "eingefroren" not in _baum_texte(ansicht)  # nachträglich: kein Live-Zustand
    _knopf(ansicht, "In Kurve").on_click()
    assert "Tippe in die Kurve" in _baum_texte(ansicht)
    wisch = next(c for c in _alle_controls(ansicht) if isinstance(c, ft.GestureDetector))
    breite = 320.0
    wisch.on_tap_down(SimpleNamespace(local_position=SimpleNamespace(x=52 + breite / 4, y=10)))
    rr = next(c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart))
    dauer = rr.max_x
    soll = round(dauer / 4, 3)
    # Marke der offenen Eingabe steht in der Hauptkurve (gestrichelt)
    assert any(s.dash_pattern and s.points[0].x == pytest.approx(soll) for s in rr.data_series)
    _knopf(ansicht, "+5 s").on_click()
    feld = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.TextField) and c.multiline and c.shift_enter
    )
    feld.value = "Atemübung 6/min"
    _symbol(ansicht, ft.Icons.CHECK, "Speichern").on_click()

    rec = laden(pfad)
    (e,) = rec.ereignisse
    assert e["text"] == "Atemübung 6/min"
    assert herz_position(rec.beats, e) == pytest.approx(soll + 5, abs=1.0)
    assert json.loads(pfad.read_text(encoding="utf-8"))["messungen"] == messwerte
    assert state.hrv.laden(eintrag.id).sha1 != ""
    assert any("Atemübung 6/min" in x for x in _baum_texte(ansicht))

    # Wieder geöffnet: Notiz in Liste und Kurve; antippen, verschieben, löschen
    ansicht2 = messung_detail_view(seite, state, eintrag)
    zeile = next(
        c
        for c in _alle_controls(ansicht2)
        if isinstance(c, ft.Container)
        and c.on_click is not None
        and "Atemübung 6/min" in _baum_texte(c)
    )
    zeile.on_click()
    _knopf(ansicht2, "−1 s").on_click()
    _symbol(ansicht2, ft.Icons.CHECK, "Speichern").on_click()
    (e2,) = laden(pfad).ereignisse
    assert herz_position(rec.beats, e2) == pytest.approx(herz_position(rec.beats, e) - 1, abs=0.5)
    zeile = next(
        c
        for c in _alle_controls(ansicht2)
        if isinstance(c, ft.Container)
        and c.on_click is not None
        and "Atemübung 6/min" in _baum_texte(c)
    )
    zeile.on_click()
    _symbol(ansicht2, ft.Icons.DELETE_OUTLINE, "Löschen").on_click()
    assert laden(pfad).ereignisse == []


async def test_live_notiz_eingefroren_und_jetzt(daten) -> None:
    state, tmp_path = daten
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    while lauf.jetzt_s() < 20:
        await asyncio.sleep(0.01)

    seite = _seite()
    ansicht = messung(seite, state)
    assert _knopf(ansicht, "Notiz").disabled  # ohne Aufnahme keine Notiz
    await _knopf(ansicht, "Aufnahme starten").on_click()
    while lauf.aufnahme_dauer_s() < 30:
        await asyncio.sleep(0.01)

    _knopf(ansicht, "Notiz").on_click()
    assert "eingefroren" in _baum_texte(ansicht)
    eingefroren_bei = lauf.aufnahme_dauer_s()
    while lauf.aufnahme_dauer_s() < eingefroren_bei + 20:
        await asyncio.sleep(0.01)
    feld = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.TextField) and c.multiline and c.shift_enter
    )
    feld.value = "Liegestütz"
    feld.on_submit(None)
    (e,) = lauf.aufnahme.ereignisse
    # Der Zeitpunkt ist der von „+ Notiz", nicht der des Speicherns
    assert e["t_wall_s"] == pytest.approx(eingefroren_bei, abs=2.0)

    # Zweite Notiz: mitlaufen lassen, dann „Jetzt"
    _knopf(ansicht, "Notiz").on_click()
    _symbol(ansicht, ft.Icons.PLAY_CIRCLE_OUTLINE).on_click()
    assert "läuft mit" in _baum_texte(ansicht)
    _knopf(ansicht, "Jetzt").on_click()
    assert "eingefroren" in _baum_texte(ansicht)
    feld.value = "Ende"
    _symbol(ansicht, ft.Icons.CHECK, "Speichern").on_click()
    assert [x["text"] for x in lauf.aufnahme.ereignisse] == ["Liegestütz", "Ende"]

    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None
    assert [x["text"] for x in ergebnis.recording.ereignisse] == ["Liegestütz", "Ende"]
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
