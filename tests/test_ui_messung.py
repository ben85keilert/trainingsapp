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
from trainingsapp.ui.components.kacheln import KACHELN  # noqa: E402
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
    assert "OHNE GERÄT AUSPROBIEREN" in texte
    state.messung_tab = 1  # Reiter „Aufzeichnungen"
    assert any(
        t.startswith("Noch keine Aufzeichnung.") for t in _baum_texte(messung(_seite(), state))
    )


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
        e = state.hrv_einstellungen()
        e.fenster_s, e.korrigiert = fenster, fenster != 120
        state.hrv_einstellungen_setzen(e)
        assert messung(seite, state) is not None
    # Alle Analysebereiche und alle Kacheln einmal durchrechnen
    e = state.hrv_einstellungen()
    e.kacheln = list(KACHELN)
    state.hrv_einstellungen_setzen(e)
    for bereich in ("zeit", "frequenz", "nichtlinear"):
        a = state.ansicht()
        a.bereich = bereich
        a.modus = {"rmssd": "block", "lf_power": "block"}
        state.ansicht_setzen(a)
        texte = _baum_texte(messung(seite, state))
        assert "DFA α1 2 min" in texte and "LF-Band 2 min" in texte  # Kacheln
    # Ein anderer Reiter: die alte Live-Ansicht rechnet nicht weiter
    nummer = state.live_ansicht
    state.messung_tab = 1
    messung(seite, state)
    assert state.live_ansicht == nummer + 1
    state.messung_tab = 0

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
    state.messung_tab = 1
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
    # Vorgabe: dem Sensor folgen — Bruchstücke, Rat zum Brustgurt
    assert "Bruchstücken" in (hinweis2[0].value or "")
    assert "H10" in (hinweis2[0].value or "")
    assert not any("selbst geprüft" in x for x in _baum_texte(ansicht2))

    # Wer selbst prüfen lässt, bekommt die Warnung
    state.korrekturregeln_setzen(Korrekturregeln(sensor_verwerfung="selbst"))
    ansicht3 = messung_detail_view(_seite(), state, eintrag2)
    hinweis3 = [
        c
        for c in _alle_controls(ansicht3)
        if isinstance(c, ft.Text) and "die meisten Intervalle" in (c.value or "")
    ]
    assert "wieder aufgenommen" in (hinweis3[0].value or "")
    assert "Vorsicht" in (hinweis3[0].value or "")
    assert any("90 davon selbst geprüft" in x for x in _baum_texte(ansicht3))


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
    assert not schalter["Verworfene Intervalle selbst prüfen"].value  # Vorgabe: aus
    schalter["Verworfene Intervalle selbst prüfen"].on_change(_ereignis(True))
    assert stand[-1].sensor_verwerfung == "selbst"

    auswahl = {c.label: c for c in _alle_controls(blatt) if isinstance(c, ft.Dropdown)}
    auswahl["Schwelle"].on_select(_ereignis("0.25"))
    assert stand[-1].malik == 0.25 and stand[-1].sensor_verwerfung == "selbst"
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
    assert state.ansicht().kurven[-1] == "sdnn"
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
    assert not lauf.regeln.selbst_pruefen  # Vorgabe: dem Sensor folgen
    sensor.on_change(_ereignis(True))
    assert lauf.regeln.selbst_pruefen and state.korrekturregeln().selbst_pruefen

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
    # Gemerkte Vorgabe „selbst prüfen" (nicht die Werksvorgabe)
    state.korrekturregeln_setzen(Korrekturregeln(sensor_verwerfung="selbst"))
    seite = _seite()
    ansicht = messung_detail_view(seite, state, eintrag)
    texte = _baum_texte(ansicht)
    assert any("26 davon selbst geprüft" in x for x in texte)
    i = texte.index("Schläge")
    assert texte[i + 1 : i + 3] == ["300", "300"]  # Vorauswahl: interpoliert, nichts entfernt

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


def test_notiz_uebungen_aus_plan_einsetzen(daten) -> None:
    """„Übungen" blendet die Übungen eines Plans ein; ein Tipp setzt den Namen in die Notiz."""
    import shutil
    from pathlib import Path

    from trainingsapp.core.models import Plan, PlanItem
    from trainingsapp.hrv_core.recording import laden
    from trainingsapp.ui.components.notizen import ALLE, uebungsquellen

    state, tmp_path = daten
    katalog = state.uebungen.alle()
    plan = Plan(
        name="Dehnung",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=u.id) for u in katalog[:3]],
    )
    state.plaene.speichern(plan)
    quellen = uebungsquellen(state)
    assert quellen[0].name == "Dehnung" and quellen[0].uebungen == [u.name for u in katalog[:3]]
    assert quellen[-1].id == ALLE and len(quellen[-1].uebungen) == len(katalog)

    ordner = tmp_path / "Messungen" / "PolarH10"
    ordner.mkdir(parents=True)
    golden = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"
    pfad = ordner / golden.name
    shutil.copy(golden, pfad)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)
    ansicht = messung_detail_view(_seite(), state, eintrag)
    _knopf(ansicht, "Notiz").on_click()
    _knopf(ansicht, "Übungen").on_click()
    assert state.notiz_uebungen_offen  # überlebt den Neuaufbau
    namen = [
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.Container)
        and c.on_click is not None
        and _baum_texte(c) in ([katalog[0].name], [katalog[1].name])
    ]
    assert len(namen) == 2
    namen[0].on_click()
    namen[1].on_click()
    feld = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.TextField) and c.multiline and c.shift_enter
    )
    assert feld.value == f"{katalog[0].name}, {katalog[1].name}"
    _symbol(ansicht, ft.Icons.CHECK, "Speichern").on_click()
    (e,) = laden(pfad).ereignisse
    assert e["text"] == f"{katalog[0].name}, {katalog[1].name}"
    # Die Notiz kennt die Übungen über ihre Kurzcodes (6 Zeichen statt UUID)
    from trainingsapp.core.kurzcode import katalog_aufloesen, kurzcode

    assert e["uebungen"] == [kurzcode(katalog[0].id), kurzcode(katalog[1].id)]
    assert katalog_aufloesen(e["uebungen"], [u.id for u in katalog]) == [
        katalog[0].id,
        katalog[1].id,
    ]

    # Ausgeschaltet in den Einstellungen: kein Knopf „Übungen"
    einst = state.hrv_einstellungen()
    einst.notiz_uebungen = False
    state.hrv_einstellungen_setzen(einst)
    ansicht = messung_detail_view(_seite(), state, eintrag)
    knopf = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.TextButton) and c.content == "Übungen"
    )
    assert not knopf.visible


def test_detailansicht_alle_bereiche_und_kacheln(daten) -> None:
    """Frequenz und Nichtlinear: Tabellen der ganzen Messung, gesperrte Bänder mit Grund."""
    import shutil
    from pathlib import Path

    state, tmp_path = daten
    ordner = tmp_path / "Messungen" / "PolarH10"
    ordner.mkdir(parents=True)
    golden = Path(__file__).parent / "golden" / "rr" / "sensor_synth_ruhe_sitzend_11.json"
    pfad = ordner / golden.name
    shutil.copy(golden, pfad)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)
    e = state.hrv_einstellungen()
    e.kacheln = list(KACHELN)
    e.frequenz = e.nichtlinear = True  # für Laien standardmäßig aus
    state.hrv_einstellungen_setzen(e)
    for bereich, erwartet in (
        ("zeit", "pNN50"),
        ("frequenz", "LF 0,04–0,15 Hz"),
        ("nichtlinear", "DFA α1"),
    ):
        a = state.ansicht()
        a.bereich = bereich
        state.ansicht_setzen(a)
        texte = _baum_texte(messung_detail_view(_seite(), state, eintrag))
        assert erwartet in texte, bereich
        assert "Ø Herzfrequenz" in texte and "LF-Band" in texte  # Kacheln der ganzen Messung
    # Atemfrequenz der ganzen Messung: Median der Minutenfenster (Wahrheit 14,55/min)
    texte = _baum_texte(messung_detail_view(_seite(), state, eintrag))
    i = texte.index("Atemfrequenz")
    assert texte[i + 1] == "20 von 20 Minutenfenstern deutlich" and texte[i + 2] in ("14,5", "14,6")
    # 6 min: LF und HF rechenbar, VLF gesperrt (braucht 20 min)
    texte = _baum_texte(messung_detail_view(_seite(), state, eintrag))
    assert any(t.startswith("Ganze Messung") for t in texte)
    a = state.ansicht()
    a.bereich = "frequenz"
    state.ansicht_setzen(a)
    texte = _baum_texte(messung_detail_view(_seite(), state, eintrag))
    assert "gesperrt" in texte and any("VLF: kein Teilstück ≥ 20 min" in t for t in texte)


def test_aufzeichnung_zuschneiden_und_abschnitte(daten) -> None:
    """Crop aus dem Sidecar steht im Kopf. Abschnitte entstehen nicht mehr von selbst aus
    Notizen: „Aus Notizen …" macht gewählte Notizen zu Grenzen; Löschen mit Rückgängig."""
    import json
    import shutil
    from pathlib import Path

    from trainingsapp.hrv_core.ausschnitte import zusatz_speichern
    from trainingsapp.hrv_core.ereignisse import anker_aus_herz, metadaten_schreiben, notiz
    from trainingsapp.hrv_core.korrektur import analyse_pfad
    from trainingsapp.hrv_core.recording import laden

    state, tmp_path = daten
    ordner = tmp_path / "Messungen" / "PolarH10"
    ordner.mkdir(parents=True)
    golden = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"
    pfad = ordner / golden.name
    shutil.copy(golden, pfad)
    rec = laden(pfad)
    notizen = [
        notiz(text, anker_aus_herz(rec.beats, t), rec.start_utc)
        for t, text in ((60, "Belastung"), (150, "Pause"))
    ]
    metadaten_schreiben(pfad, ereignisse=notizen)
    zusatz_speichern(pfad, (30.0, 300.0), [], float)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)
    seite = _seite()
    view = messung_detail_view(seite, state, eintrag)
    texte = _baum_texte(view)
    assert any("zugeschnitten 0:30–5:00" in t for t in texte)
    loeschknoepfe = [
        c
        for c in _alle_controls(view)
        if isinstance(c, ft.IconButton) and c.tooltip == "Abschnitt löschen"
    ]
    assert loeschknoepfe == []  # Notizen teilen nicht von selbst
    assert any(t.startswith("Noch keine Abschnitte") for t in texte)

    menue = next(
        c for c in _alle_controls(view) if isinstance(c, ft.PopupMenuButton) and c.tooltip == "Mehr"
    )
    next(i for i in menue.items if i.content == "Aus Notizen …").on_click()
    _knopf(seite.aufrufe[-1], "Anlegen").on_click()
    texte = _baum_texte(view)
    assert "Belastung" in texte and "Pause" in texte

    def segmente() -> list[str]:
        return [s["name"] for s in json.loads(analyse_pfad(pfad).read_text())["segments"]]

    assert segmente() == ["Belastung", "Pause"]
    _symbol(view, ft.Icons.CLOSE, "Abschnitt löschen").on_click()
    assert segmente() == ["Pause"]
    seite.aufrufe[-1].action.on_click()  # Rückgängig
    assert sorted(segmente()) == ["Belastung", "Pause"]


def _golden_eintrag(state, tmp_path) -> tuple[HrvRecording, object]:
    import shutil
    from pathlib import Path

    ordner = tmp_path / "Messungen" / "PolarH10"
    ordner.mkdir(parents=True, exist_ok=True)
    golden = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"
    pfad = ordner / golden.name
    shutil.copy(golden, pfad)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet_profil="polar_h10",
        duration_s=301.0,
    )
    state.hrv.anlegen(eintrag)
    return eintrag, pfad


def test_titel_und_beschreibung_in_die_messdatei(daten) -> None:
    """Kopfzeile antippen → Blatt; Speichern schreibt titel/notiz in die Datei und die Liste."""
    from trainingsapp.hrv_core.recording import laden

    state, tmp_path = daten
    eintrag, pfad = _golden_eintrag(state, tmp_path)
    seite = _seite()
    view = messung_detail_view(seite, state, eintrag)
    assert "Referenzmessung (anonymisiert)" in _baum_texte(view)  # Titel aus der Datei
    assert state.hrv.laden(eintrag.id).title == "Referenzmessung (anonymisiert)"
    kopf = next(
        c
        for c in _alle_controls(view)
        if isinstance(c, ft.Container)
        and c.on_click is not None
        and "Referenzmessung (anonymisiert)" in _baum_texte(c)
    )
    kopf.on_click()
    blatt = seite.aufrufe[-1]
    felder = [c for c in _alle_controls(blatt) if isinstance(c, ft.TextField)]
    felder[0].value, felder[1].value = "Intervalle Beine", "Nach dem Lauf"
    _knopf(blatt, "Speichern").on_click()
    rec = laden(pfad)
    assert (rec.titel, rec.notiz) == ("Intervalle Beine", "Nach dem Lauf")
    gespeichert = state.hrv.laden(eintrag.id)
    assert (gespeichert.title, gespeichert.note) == ("Intervalle Beine", "Nach dem Lauf")
    assert "Intervalle Beine" in _baum_texte(view) and "Nach dem Lauf" in _baum_texte(view)


def test_zuschneiden_in_der_kurve(daten) -> None:
    """✂ öffnet den Bereichseditor in der Rohkurve; ±5 s rückt den Anfang, Übernehmen speichert."""
    import json

    from trainingsapp.hrv_core.korrektur import analyse_pfad

    state, tmp_path = daten
    eintrag, pfad = _golden_eintrag(state, tmp_path)
    seite = _seite()
    view = messung_detail_view(seite, state, eintrag)
    schere = next(a for a in view.appbar.actions if a.icon == ft.Icons.CONTENT_CUT)
    schere.on_click()
    assert "ZUSCHNEIDEN" in _baum_texte(view)
    for _ in range(6):
        _knopf(view, "+5 s").on_click()
    _knopf(view, "Übernehmen").on_click()
    crop = json.loads(analyse_pfad(pfad).read_text())["active_crop"]
    assert crop["t_start_s"] == pytest.approx(30.0, abs=1.0)
    assert any("zugeschnitten 0:30–" in t for t in _baum_texte(view))
    assert "ZUSCHNEIDEN" not in _baum_texte(view)


def test_abschnitt_anlegen_umbenennen_verschieben(daten) -> None:
    """„+ Abschnitt" nimmt den sichtbaren Bereich; antippen öffnet ihn wieder zum Ändern."""
    import json

    from trainingsapp.hrv_core.korrektur import analyse_pfad

    state, tmp_path = daten
    eintrag, pfad = _golden_eintrag(state, tmp_path)
    seite = _seite()
    view = messung_detail_view(seite, state, eintrag)
    _knopf(view, "Abschnitt").on_click()
    assert "NEUER ABSCHNITT" in _baum_texte(view)
    name = next(
        c for c in _alle_controls(view) if isinstance(c, ft.TextField) and c.label == "Name"
    )
    name.value = "Ruhe"
    _knopf(view, "Speichern").on_click()

    def segmente() -> list[dict]:
        return json.loads(analyse_pfad(pfad).read_text())["segments"]

    (ruhe,) = segmente()
    assert ruhe["name"] == "Ruhe"
    zeile = next(
        c
        for c in _alle_controls(view)
        if isinstance(c, ft.Container) and c.on_click is not None and "Ruhe" in _baum_texte(c)
    )
    zeile.on_click()  # bearbeiten: Ende 5 s weiter
    ende = next(
        c
        for c in _alle_controls(view)
        if isinstance(c, ft.Container) and c.on_click is not None and "Ende" in _baum_texte(c)
    )
    ende.on_click()
    _knopf(view, "+5 s").on_click()
    _knopf(view, "Speichern").on_click()
    (neu,) = segmente()
    assert neu["t_end_s"] == pytest.approx(ruhe["t_end_s"] + 5, abs=0.01)
    assert neu["id"] == ruhe["id"]


def test_bereich_pfeile_setzen_grenzen_an_den_rand() -> None:
    """|◀ setzt den Anfang an den Beginn, ▶| das Ende an den Schluss; die Kurve rückt mit."""
    from trainingsapp.ui.components.bereich import ANFANG, ENDE, BereichEditor

    gezeigt: list[float] = []
    geaendert: list[int] = []
    editor = BereichEditor(
        von=600.0,
        bis=900.0,
        anfang=0.0,
        ende=4200.0,
        notizen=lambda: [(3.0, "Start")],
        geaendert=lambda: geaendert.append(1),
        zeigen=gezeigt.append,
        breite=lambda: 60.0,
    )
    editor.waehlen(ENDE)
    _symbol(editor.control, ft.Icons.FIRST_PAGE, "Anfang an den Beginn der Messung").on_click()
    assert (editor.aktiv, editor.von, editor.bis) == (ANFANG, 0.0, 900.0)
    assert editor.rast == ""  # kein Einrasten an der Notiz bei 3 s
    _symbol(editor.control, ft.Icons.LAST_PAGE, "Ende an den Schluss der Messung").on_click()
    assert (editor.aktiv, editor.von, editor.bis) == (ENDE, 0.0, 4200.0)
    assert gezeigt[-2:] == [0.0, 4200.0] and len(geaendert) == 3
    assert "70:00" in _baum_texte(editor.control)


def test_abschnitt_ueber_die_ganze_messung_per_pfeil(daten) -> None:
    """Im Abschnitts-Editor der Aufzeichnung: beide Pfeile → Abschnitt über die ganze Messung."""
    import json

    from trainingsapp.hrv_core.korrektur import analyse_pfad

    state, tmp_path = daten
    eintrag, pfad = _golden_eintrag(state, tmp_path)
    view = messung_detail_view(_seite(), state, eintrag)
    _knopf(view, "Abschnitt").on_click()
    _symbol(view, ft.Icons.FIRST_PAGE).on_click()
    _symbol(view, ft.Icons.LAST_PAGE).on_click()
    _knopf(view, "Speichern").on_click()
    (seg,) = json.loads(analyse_pfad(pfad).read_text())["segments"]
    schlaege = json.loads(pfad.read_text())["messungen"]
    # vom ersten bis zum letzten Schlag der Datei (Herzuhr)
    assert seg["t_start_s"] == pytest.approx(schlaege[0]["t_s"], abs=0.01)
    assert seg["t_end_s"] == pytest.approx(schlaege[-1]["t_s"], abs=0.01)


def test_ablesen_zeigt_alle_werte_an_einer_stelle(daten) -> None:
    """„Ablesen" zeigt einen Strich und darunter RR, HF und die Verlaufskurven an dieser Stelle."""
    state, tmp_path = daten
    eintrag, _ = _golden_eintrag(state, tmp_path)
    seite = _seite()
    view = messung_detail_view(seite, state, eintrag)
    knopf = _knopf(view, "Ablesen")
    knopf.on_click()
    texte = _baum_texte(view)
    assert "RR" in texte and "HF" in texte and "bpm" in texte
    assert any(t.startswith("RMSSD") for t in texte)  # Verlaufskurve der Zeitansicht
    assert any(t.endswith(" Uhr") for t in texte)  # Zeit der Stelle samt Uhrzeit
    _symbol(view, ft.Icons.CHEVRON_RIGHT, "Ein Schlag weiter").on_click()
    _symbol(view, ft.Icons.CLOSE, "Ablesen beenden").on_click()
    assert knopf.style is None  # wieder aus: Ziehen blättert die Kurve


async def test_live_titel_landet_in_der_messdatei(daten) -> None:
    """Während der Aufnahme: „Titel hinzufügen" → Blatt; der Titel steht danach in der Datei."""
    state, tmp_path = daten
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    while lauf.jetzt_s() < 10:
        await asyncio.sleep(0.01)
    seite = _seite()
    ansicht = messung(seite, state)
    await _knopf(ansicht, "Aufnahme starten").on_click()
    while lauf.aufnahme_dauer_s() < 20:
        await asyncio.sleep(0.01)
    ansicht = messung(seite, state)  # der Statusbereich zeigt jetzt die Aufnahme
    kopf = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.Container)
        and c.on_click is not None
        and "Titel hinzufügen" in _baum_texte(c)
    )
    kopf.on_click()
    blatt = seite.aufrufe[-1]
    titel_feld, beschreibung_feld = [
        c for c in _alle_controls(blatt) if isinstance(c, ft.TextField)
    ]
    titel_feld.value, beschreibung_feld.value = "Morgenmessung", "Gut geschlafen"
    _knopf(blatt, "Speichern").on_click()
    assert (lauf.aufnahme.titel, lauf.aufnahme.notiz) == ("Morgenmessung", "Gut geschlafen")
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None
    assert (ergebnis.recording.titel, ergebnis.recording.notiz) == (
        "Morgenmessung",
        "Gut geschlafen",
    )
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


def test_titel_vorschlag_ist_der_geuebte_plan(daten) -> None:
    """Wurde während der Messung aus einem Plan eingetragen, steht er im leeren Titelfeld."""
    from trainingsapp.core.models import Plan, PlanItem, jetzt, lokaler_tag
    from trainingsapp.hrv_core.ereignisse import metadaten_schreiben

    state, tmp_path = daten
    eintrag, pfad = _golden_eintrag(state, tmp_path)
    metadaten_schreiben(pfad, titel="")
    uebung = state.uebungen.alle()[0]
    plan = Plan(name="Beine", subject_id=state.profil.id, items=[PlanItem(exercise_id=uebung.id)])
    state.plaene.speichern(plan)
    sitzung = state.sitzungen.session_fuer(state.profil.id, plan.id, lokaler_tag(jetzt()))
    state.sitzungen.erledigt(sitzung, uebung)

    seite = _seite()
    view = messung_detail_view(seite, state, eintrag)
    kopf = next(
        c
        for c in _alle_controls(view)
        if isinstance(c, ft.Container)
        and c.on_click is not None
        and "Titel und Beschreibung hinzufügen" in _baum_texte(c)
    )
    kopf.on_click()
    blatt = seite.aufrufe[-1]
    titel_feld = next(c for c in _alle_controls(blatt) if isinstance(c, ft.TextField))
    assert titel_feld.value == "Beine"
    chips = [c.label.value for c in _alle_controls(blatt) if isinstance(c, ft.Chip)]
    assert "Beine" in chips  # auch als Vorschlag zum Antippen
