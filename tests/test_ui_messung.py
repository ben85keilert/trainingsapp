"""Rauchtests der Messansichten — mit Simulator und gespeicherten Dateien, ohne Fenster."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from hrv_core.korrektur import analyse_laden  # noqa: E402
from hrv_core.recording import Beat, Recording, speichern  # noqa: E402
from hrv_core.regeln import Korrekturregeln  # noqa: E402

from attrappen import aufgabe_starten  # noqa: E402
from trainingsapp.core.models import HrvRecording  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource  # noqa: E402
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
    aufgaben: list = []
    return SimpleNamespace(
        route="/",
        views=[],
        update=lambda: None,
        show_dialog=aufrufe.append,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: aufgabe_starten(aufgaben, f, *a),
        aufgaben=aufgaben,
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
        for name in (
            "controls",
            "content",
            "title",
            "subtitle",
            "leading",
            "trailing",
            "tabs",
            "label",
        ):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                lauf(k)

    lauf(c)
    return texte


async def test_aufnahme_gehoert_dem_profil_beim_start(daten) -> None:
    """Profilwechsel während der Aufnahme: der Eintrag bleibt beim Startprofil (15.10.2026)."""
    from trainingsapp.ui.views.messung import aufnahme_eintragen

    state, tmp_path = daten
    start = state.profil.id
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path, subject_id=start)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 5:
        await asyncio.sleep(0.01)
    zweites = state.profil_anlegen("Zweites")
    state.profil_wechseln(zweites.id)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None
    eintrag = aufnahme_eintragen(state, ergebnis, lauf.subject_id)
    assert eintrag.subject_id == start != state.profil.id


def test_messung_ohne_geraet(daten) -> None:
    state, _ = daten
    texte = _baum_texte(messung(_seite(), state))
    assert "Gerät verbinden" in texte
    assert "OHNE GERÄT AUSPROBIEREN" in texte
    state.messung_tab = 2  # Reiter „Aufzeichnungen" — ohne alles: Unterreiter „Strecken"
    texte = _baum_texte(messung(_seite(), state))
    assert state.aufzeichnungen_tab == 0 and "Strecken" in texte and "HRV" in texte
    assert any(t.startswith("Noch kein Training.") for t in texte)
    state.aufzeichnungen_tab = 1
    assert any(
        t.startswith("Noch keine Aufzeichnung.") for t in _baum_texte(messung(_seite(), state))
    )
    state.messung_tab = 1  # Reiter „GPS": das Training direkt, ohne Zwischenschritt (26.10.)
    gps = messung(_seite(), state)
    assert "TRAINING" in _baum_texte(gps)
    assert _knopf(gps, "Training starten") is not None
    wahl = next(c for c in _alle_controls(gps) if isinstance(c, ft.SegmentedButton))
    assert [s.value for s in wahl.segments] == ["gehen", "laufen", "rad"]
    assert any(  # der Timer-Knopf steht in der Karte — der Reiter hat keine Titelleiste
        isinstance(c, ft.IconButton) and c.icon == ft.Icons.TIMER_OUTLINED
        for c in _alle_controls(gps)
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
    state.messung_tab = 2
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

    # Liste im Reiter zeigt die Aufzeichnung — und bietet den Export an; ohne Trainings
    # öffnet sich gleich der Unterreiter „HRV"
    state.messung_tab = 2
    liste = messung(seite, state)
    assert state.aufzeichnungen_tab == 1 and "HRV (1)" in _baum_texte(liste)
    assert "Noch keine Aufzeichnung." not in _baum_texte(liste)
    export = [
        c
        for c in _alle_controls(liste)
        if isinstance(c, ft.TextButton) and c.content == "Alle exportieren"
    ]
    assert len(export) == 1 and export[0].visible
    assert any(
        isinstance(c, ft.IconButton) and (c.tooltip or "").startswith("Exportieren (ZIP")
        for c in ansicht.appbar.actions
    )


def test_detailansicht_zurueck_speichert_geaenderte_korrektur(daten) -> None:
    """Autosave (Ben, 16.10.2026): Zurück speichert eine geänderte Korrektur — aber nicht
    die bloße Vorauswahl einer Messung ohne Sidecar."""
    from hrv_core.korrektur import analyse_regeln

    state, tmp_path = daten
    rr = [800 + (15 if i % 2 else -15) for i in range(160)]
    rr[60] = rr[120] = 1650  # zwei ausgelassene Schläge, zwei Vorschläge
    beats, t = [], 0.0
    for x in rr:
        t += x / 1000
        beats.append(Beat(t_s=round(t, 3), rr_ms=x, hf_bpm=75, t_wall_s=round(t, 3)))
    rec = Recording(beats=beats, geraet="Polar H10 TEST", geraet_profil="polar_h10")
    pfad = speichern(rec, tmp_path / "Messungen" / "PolarH10")
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="Polar H10 TEST",
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)
    routen: list[str] = []
    antworten: list[bool] = []

    async def push_route(route: str) -> None:
        routen.append(route)

    async def confirm_pop(soll: bool) -> None:
        antworten.append(soll)

    seite = _seite()
    seite.push_route = push_route
    ansicht = messung_detail_view(seite, state, eintrag)
    ansicht.confirm_pop = confirm_pop
    seite.views = [ft.View(route="/"), ansicht]
    assert ansicht.can_pop  # nur angesehen: Zurück ist ein gewöhnliches Zurück

    ketten = [c for c in _alle_controls(ansicht) if isinstance(c, ft.ListTile) and c.on_click]
    assert len(ketten) == 2 and analyse_regeln(pfad) is None  # Vorauswahl: beide, kein Sidecar
    ketten[1].on_click()  # den zweiten Vorschlag abwählen — eine Änderung
    assert not ansicht.can_pop
    asyncio.run(ansicht.on_confirm_pop(None))
    assert antworten == [False] and routen == ["/"]
    assert [k.beat_index for k in analyse_laden(pfad)] == [60]
    assert ansicht.can_pop  # gespeichert: nichts mehr offen


def test_detailansicht_ohne_datei(daten) -> None:
    state, _ = daten
    eintrag = HrvRecording(subject_id=state.profil.id, file_path="PolarH10/fehlt.json")
    state.hrv.anlegen(eintrag)
    assert "Die Messdatei fehlt." in _baum_texte(messung_detail_view(_seite(), state, eintrag))


def _menue_eintrag(wurzel, text: str):
    """Ein Eintrag im Menü ⋮ der Kurven — Info und Korrektur stehen seit dem 21.10.2026 dort."""
    menue = next(
        c
        for c in _alle_controls(wurzel)
        if isinstance(c, ft.PopupMenuButton) and c.icon == ft.Icons.MORE_VERT
    )
    return next(i for i in menue.items if i.content == text)


def _loeschen_bestaetigen(seite) -> ft.AlertDialog:
    """Die Rückfrage „… löschen?“ mit „Löschen“ beantworten (Ben, 21.10.2026). Gelöscht wird
    erst, wenn Flutter den Dialog zu meldet — das ``on_dismiss`` ruft der Test selbst."""
    frage = seite.aufrufe[-1]
    assert isinstance(frage, ft.AlertDialog) and frage.title.value.endswith("löschen?")
    next(b for b in frage.actions if isinstance(b, ft.FilledButton)).on_click()
    assert not frage.open
    return frage


def _alle_controls(wurzel) -> list:
    gesehen: set[int] = set()
    alle: list = []

    def lauf(x) -> None:
        if not isinstance(x, ft.Control) or id(x) in gesehen:
            return
        gesehen.add(id(x))
        alle.append(x)
        for name in (
            "controls",
            "content",
            "title",
            "subtitle",
            "leading",
            "trailing",
            "tabs",
            "label",
        ):
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
    from hrv_core.ppi import ppi_folge
    from hrv_core.recording import laden

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
    seite = _seite()
    ansicht = messung_detail_view(seite, state, eintrag)
    folge = ppi_folge(laden(pfad))
    assert folge is not None
    dauer = folge[-1].t_s

    # Die Aufzeichnung öffnet mit den ersten 2 Minuten …
    rr_kurve = next(c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart))
    assert (rr_kurve.min_x, rr_kurve.max_x) == (0.0, 120.0)
    # … der Chip „Ganze Messung“ zeigt die ganze Messung (seit 19.10.2026 statt „Alles“)
    _ganze_messung(ansicht).on_click()

    # Tachogramm, darunter die Vorgabe-Ansicht: Ø HF aus RR, RMSSD
    rr_kurve, hf_kurve, rmssd_kurve = [
        c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart)
    ]
    grau = rr_kurve.data_series[0]
    assert len(grau.points) == 300  # alle Intervalle, eine durchgehende Linie
    assert rr_kurve.max_x == hf_kurve.max_x == rmssd_kurve.max_x == pytest.approx(dauer)
    texte = _baum_texte(ansicht)
    assert any(f"{int(dauer) // 60}:{int(dauer) % 60:02d}" in x for x in texte)
    # Was Grau heißt, steht hinter „Info“ im Menü ⋮ der Kurve (Ben, 17. und 21.10.2026)
    _menue_eintrag(ansicht, "So liest du die Kurven").on_click()
    blatt = seite.aufrufe[-1]
    assert any(
        "auch verworfene" in c.value for c in _alle_controls(blatt) if isinstance(c, ft.Markdown)
    )
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


def _breiten_wahl(wurzel) -> ft.SegmentedButton:
    """Die Breitenwahl der Aufzeichnung (1 Min … 10 Min)."""
    return next(
        c
        for c in _alle_controls(wurzel)
        if isinstance(c, ft.SegmentedButton) and any(s.value == "600" for s in c.segments)
    )


def _ganze_messung(wurzel) -> ft.Container:
    """Der Abschnitt-Chip „Ganze Messung“ unter den Breitenknöpfen (Plan F)."""
    return next(
        c
        for c in _alle_controls(wurzel)
        if isinstance(c, ft.Container)
        and c.on_click is not None
        and any(isinstance(t, ft.Text) and t.value == "Ganze Messung" for t in _alle_controls(c))
    )


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

    # Automatische Korrektur im Menü ⋮ (Ben, 21.10.2026): Blatt öffnet sich, Umschalten
    # wirkt auf den Messlauf
    _menue_eintrag(ansicht, "Automatische Korrektur …").on_click()
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
    from hrv_core.korrektur import analyse_regeln

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

    # Regeln je Messung: dem Sensor folgen, speichern — die Vorgabe bleibt. Der Regler der
    # Karte „Korrektur“ und der Eintrag im Menü ⋮ öffnen dasselbe Blatt.
    _symbol(ansicht, ft.Icons.TUNE, "Was automatische Korrektur heißt").on_click()
    assert isinstance(seite.aufrufe[-1], ft.BottomSheet)
    _menue_eintrag(ansicht, "Automatische Korrektur …").on_click()
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
    from hrv_core.ereignisse import herz_position
    from hrv_core.recording import laden

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
    # Löschen fragt erst (Ben, 21.10.2026) — gelöscht wird, wenn die Rückfrage zu ist
    _symbol(ansicht2, ft.Icons.DELETE_OUTLINE, "Löschen").on_click()
    frage = _loeschen_bestaetigen(seite)
    assert frage.content.value.startswith("„Atemübung 6/min“ bei ")
    assert len(laden(pfad).ereignisse) == 1
    asyncio.run(frage.on_dismiss(None))
    assert laden(pfad).ereignisse == []
    meldung = seite.aufrufe[-1]  # „Notiz gelöscht“ geht von selbst wieder weg
    assert isinstance(meldung, ft.SnackBar) and meldung.persist is False
    meldung.action.on_click()  # Rückgängig
    assert [e["text"] for e in laden(pfad).ereignisse] == ["Atemübung 6/min"]


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
    feld = next(
        c
        for c in _alle_controls(ansicht)
        if isinstance(c, ft.TextField) and c.multiline and c.shift_enter
    )
    # Schon vor der Aufnahme (Ben, 16.10.2026) — getippt, aber nicht gespeichert:
    # „Aufnahme starten" nimmt sie mit, an den Anfang der Aufnahme
    assert not _knopf(ansicht, "Notiz").disabled
    _knopf(ansicht, "Notiz").on_click()
    feld.value = "Vorher"
    await _knopf(ansicht, "Aufnahme starten").on_click()
    assert [x["text"] for x in lauf.aufnahme.ereignisse] == ["Vorher"]
    assert lauf.aufnahme.ereignisse[0]["t_wall_s"] == 0.0
    while lauf.aufnahme_dauer_s() < 30:
        await asyncio.sleep(0.01)

    _knopf(ansicht, "Notiz").on_click()
    assert "eingefroren" in _baum_texte(ansicht)
    eingefroren_bei = lauf.aufnahme_dauer_s()
    while lauf.aufnahme_dauer_s() < eingefroren_bei + 20:
        await asyncio.sleep(0.01)
    feld.value = "Liegestütz"
    feld.on_submit(None)
    _, e = lauf.aufnahme.ereignisse
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
    assert [x["text"] for x in lauf.aufnahme.ereignisse] == ["Vorher", "Liegestütz", "Ende"]

    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None
    assert [x["text"] for x in ergebnis.recording.ereignisse] == ["Vorher", "Liegestütz", "Ende"]
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


def test_notiz_uebungen_aus_plan_einsetzen(daten) -> None:
    """„Übungen" blendet die Übungen eines Plans ein; ein Tipp setzt den Namen in die Notiz."""
    import shutil
    from pathlib import Path

    from hrv_core.recording import laden

    from trainingsapp.core.models import Plan, PlanItem
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

    from hrv_core.ausschnitte import zusatz_speichern
    from hrv_core.ereignisse import anker_aus_herz, metadaten_schreiben, notiz
    from hrv_core.korrektur import analyse_pfad
    from hrv_core.recording import laden

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
    # Löschen fragt erst (Ben, 21.10.2026); die Meldung danach geht von selbst wieder weg
    _symbol(view, ft.Icons.CLOSE, "Abschnitt löschen").on_click()
    frage = _loeschen_bestaetigen(seite)
    assert "„Belastung“" in frage.content.value and segmente() == ["Belastung", "Pause"]
    asyncio.run(frage.on_dismiss(None))
    assert segmente() == ["Pause"]
    meldung = seite.aufrufe[-1]
    assert meldung.persist is False and meldung.content.value == "„Belastung“ gelöscht"
    meldung.action.on_click()  # Rückgängig
    assert sorted(segmente()) == ["Belastung", "Pause"]

    # „Alle löschen“ fragt ebenso — Abbrechen lässt alles stehen
    next(i for i in menue.items if i.content == "Alle löschen").on_click()
    frage = seite.aufrufe[-1]
    assert frage.title.value == "Alle Abschnitte löschen?"
    next(b for b in frage.actions if b.content == "Abbrechen").on_click()
    asyncio.run(frage.on_dismiss(None))
    assert sorted(segmente()) == ["Belastung", "Pause"]
    next(i for i in menue.items if i.content == "Alle löschen").on_click()
    asyncio.run(_loeschen_bestaetigen(seite).on_dismiss(None))
    assert segmente() == []
    assert seite.aufrufe[-1].content.value == "2 Abschnitte gelöscht"


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
    from hrv_core.recording import laden

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

    from hrv_core.korrektur import analyse_pfad

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

    from hrv_core.korrektur import analyse_pfad

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

    from hrv_core.korrektur import analyse_pfad

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


# ---------------------------------------------------------------------------
# Wie live: Knöpfe, ganzer Abschnitt, Zeitachse und feste Werteachsen (Ben, 21.10.2026)
# ---------------------------------------------------------------------------


def _titelzeile(wurzel, titel: str) -> ft.Row:
    """Die Titelzeile der Karte mit der Hauptkurve."""
    return next(
        r
        for r in _alle_controls(wurzel)
        if isinstance(r, ft.Row)
        and any(isinstance(c, ft.Text) and c.value == titel for c in r.controls)
    )


def _knoepfe_rechts(zeile: ft.Row) -> list[str]:
    """Was rechts vom Titel steht: Text der Knöpfe, sonst Tooltip, beim Menü „⋮“."""
    out = []
    for c in zeile.controls[1:]:
        menue = getattr(c, "content", None)
        if isinstance(menue, ft.PopupMenuButton):
            out.append("⋮" if menue.icon == ft.Icons.MORE_VERT else "?")
        elif isinstance(c, ft.TextButton):
            out.append(str(c.content))
        else:
            out.append(str(c.tooltip).split(":")[0].split(" (")[0])
    return out


def test_aufzeichnung_wie_live_ganzer_abschnitt_und_feste_achsen(daten) -> None:
    import flet_charts as fc
    from hrv_core.ausschnitte import Abschnitt, zusatz_speichern

    state, tmp_path = daten
    eintrag, pfad = _golden_eintrag(state, tmp_path)
    zusatz_speichern(pfad, None, [Abschnitt("Ruhe", 60.0, 240.0)], float)
    seite = _seite()
    view = messung_detail_view(seite, state, eintrag)

    def rr() -> fc.LineChart:
        return next(c for c in _alle_controls(view) if isinstance(c, fc.LineChart))

    # Titelzeile wie live: Fenster & Darstellung zweiter von rechts, Info und Korrektur im Menü
    zeile = _titelzeile(view, "RR-TACHOGRAMM")
    assert _knoepfe_rechts(zeile) == ["Ablesen", "Vollbild", "Fenster & Darstellung", "⋮"]
    eintraege = [i.content for i in zeile.controls[-1].content.items if i.content]
    assert eintraege[:3] == [
        "So liest du die Kurven",
        "Automatische Korrektur …",
        "Als Ansicht speichern …",
    ]
    assert "Fenster & Darstellung …" not in eintraege
    knoepfe = _breiten_wahl(view)
    assert [s.label.value for s in knoepfe.segments] == ["1 Min", "2 Min", "5 Min", "10 Min"]

    # Ein Tipp auf den Abschnitt-Chip zeigt ihn ganz, mit 30 s Rand …
    chip = next(
        c
        for c in _alle_controls(view)
        if isinstance(c, ft.Container) and c.on_click is not None and "Ruhe 1:00" in _baum_texte(c)
    )
    chip.on_click()
    assert (rr().min_x, rr().max_x) == (30.0, 270.0) and knoepfe.selected == []
    # … die Breitenknöpfe zoomen hinein, ein zweiter Tipp zeigt wieder den ganzen
    knoepfe.on_change(_ereignis("60"))
    assert rr().max_x - rr().min_x == pytest.approx(60) and knoepfe.selected == ["60"]
    chip.on_click()
    assert (rr().min_x, rr().max_x) == (30.0, 270.0)
    _ganze_messung(view).on_click()

    # Fenster & Darstellung: Breite eintippen …
    zeile.controls[-2].on_click()
    blatt = seite.aufrufe[-1]
    felder = [c for c in _alle_controls(blatt) if isinstance(c, ft.TextField)]
    assert [f.label for f in felder][:3] == ["Breite der Zeitachse", "von", "bis"]
    breite, von, bis = felder[:3]
    breite.value = "1:30"
    breite.on_submit(None)
    assert rr().max_x - rr().min_x == pytest.approx(90)
    # … und die Werteachse der Hauptkurve fest: 500–1500 ms
    assert "RR-Tachogramm" in _baum_texte(blatt)
    von.value, bis.value = "500", "1500"
    bis.on_blur(None)
    assert state.ansicht().y_achsen == {"rr": (500.0, 1500.0)}
    assert (rr().min_y, rr().max_y) == (470.0, 1530.0)
    assert [label.value for label in rr().left_axis.labels] == [500, 750, 1000, 1250, 1500]
    # Halb ausgefüllt: „Fertig“ sagt, was fehlt, und die Achse bleibt fest
    fertig = _knopf(blatt, "Fertig")
    von.value = ""
    fertig.on_click()
    assert von.error and state.ansicht().y_achsen == {"rr": (500.0, 1500.0)}
    bis.value = ""  # beide leer: wieder automatisch
    fertig.on_click()
    assert von.error is None and state.ansicht().y_achsen == {}
    assert rr().min_y > 470.0


async def test_live_ablesen_und_knoepfe_wie_in_der_aufzeichnung(daten) -> None:
    import flet_charts as fc

    state, tmp_path = daten
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    while lauf.jetzt_s() < 90:
        await asyncio.sleep(0.01)
    seite = _seite()
    ansicht = messung(seite, state)
    zeile = _titelzeile(ansicht, "RR-TACHOGRAMM")
    assert _knoepfe_rechts(zeile) == ["Ablesen", "Kurven im Vollbild", "Fenster & Darstellung", "⋮"]
    knoepfe = _breiten_wahl(ansicht)
    assert [s.label.value for s in knoepfe.segments] == ["1 Min", "2 Min", "5 Min", "10 Min"]

    # Ablesen hält die Kurve an und zeigt die Werte am Strich — wie in der Aufzeichnung
    knopf = _knopf(ansicht, "Ablesen")
    knopf.on_click()
    assert state.messung_ende_s is not None and knopf.style is not None
    texte = _baum_texte(ansicht)
    assert "RR" in texte and "HF" in texte and any(t.startswith("RMSSD") for t in texte)
    assert any(t.endswith(" Uhr") for t in texte)

    def strich_x() -> list[float]:
        kurven = [c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart)]
        return [
            s.points[0].x
            for k in kurven
            for s in k.data_series
            if len(s.points) == 2
            and s.points[0].x == s.points[1].x
            and s.color == ft.Colors.ON_SURFACE
        ]

    assert len(strich_x()) >= 2  # in der Hauptkurve und in den Verlaufskurven
    vorher = strich_x()[0]
    _symbol(ansicht, ft.Icons.CHEVRON_RIGHT, "Ein Schlag weiter").on_click()
    assert strich_x()[0] > vorher
    # Ein Tipp in die Kurve setzt den Strich dorthin (Mitte der Zeichenfläche ≈ Fenstermitte)
    wisch = next(c for c in _alle_controls(ansicht) if isinstance(c, ft.GestureDetector))
    wisch.on_tap_down(SimpleNamespace(local_position=SimpleNamespace(x=52 + 10, y=10)))
    assert strich_x()[0] < vorher
    _knopf(ansicht, "Live").on_click()  # wieder mitlaufen — Ablesen endet
    assert state.messung_ende_s is None and knopf.style is None and strich_x() == []

    # Die Breite eintippen — gilt auch beim nächsten Mal
    zeile.controls[-2].on_click()
    feld = next(
        c
        for c in _alle_controls(seite.aufrufe[-1])
        if isinstance(c, ft.TextField) and c.label == "Breite der Zeitachse"
    )
    feld.value = "3"
    feld.on_submit(None)
    assert state.hrv_einstellungen().fenster_s == 180 and knoepfe.selected == []
    kurve = next(c for c in _alle_controls(ansicht) if isinstance(c, fc.LineChart))
    assert kurve.max_x - kurve.min_x == pytest.approx(180)
    # Automatische Korrektur steht jetzt im Menü ⋮
    _menue_eintrag(ansicht, "Automatische Korrektur …").on_click()
    assert isinstance(seite.aufrufe[-1], ft.BottomSheet)

    await lauf.trennen()
    await asyncio.wait_for(task, 5)


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


async def test_titel_und_beschreibung_schon_vor_der_aufnahme(daten) -> None:
    """Ben, 17.10.2026: Titel und Beschreibung vor dem Start eintragen — der Start übernimmt
    sie, die Messdatei hat sie; die nächste Aufnahme beginnt wieder ohne."""
    state, tmp_path = daten
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    while lauf.jetzt_s() < 10:
        await asyncio.sleep(0.01)
    seite = _seite()
    ansicht = messung(seite, state)
    assert lauf.aufnahme is None
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
    titel_feld.value, beschreibung_feld.value = "Abendmessung", "Nach dem Training"
    _knopf(blatt, "Speichern").on_click()
    assert lauf.titel_notiz() == ("Abendmessung", "Nach dem Training")
    ansicht = messung(seite, state)
    assert "Abendmessung" in _baum_texte(ansicht)  # steht schon vor dem Start da

    await _knopf(ansicht, "Aufnahme starten").on_click()
    assert (lauf.aufnahme.titel, lauf.aufnahme.notiz) == ("Abendmessung", "Nach dem Training")
    while lauf.aufnahme_dauer_s() < 10:
        await asyncio.sleep(0.01)
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    assert ergebnis is not None
    assert (ergebnis.recording.titel, ergebnis.recording.notiz) == (
        "Abendmessung",
        "Nach dem Training",
    )
    assert lauf.titel_notiz() == ("", "")  # die nächste Aufnahme beginnt ohne
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


def test_titel_vorschlag_ist_der_geuebte_plan(daten) -> None:
    """Wurde während der Messung aus einem Plan eingetragen, steht er im leeren Titelfeld."""
    from hrv_core.ereignisse import metadaten_schreiben

    from trainingsapp.core.models import Plan, PlanItem, jetzt, lokaler_tag

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


async def test_crash_backup_wird_beim_start_erkannt_und_wiederhergestellt(daten) -> None:
    """Akku leer während der Aufnahme (Ben, 15.10.2026): das 15-s-Backup wird beim nächsten
    Start gefunden, „Wiederherstellen" macht daraus die Messung des Startprofils."""
    from trainingsapp.config import messungenverzeichnis
    from trainingsapp.ui.views.messung import backup_dialog, backup_uebernehmen

    state, tmp_path = daten
    start = state.profil.id
    lauf = Messlauf(SimulatedSource(tempo=60.0), backup_basis=tmp_path, subject_id=start)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 20:
        await asyncio.sleep(0.01)
    await lauf.trennen()  # kein aufnahme_stoppen: so sieht ein Prozess-Tod aus
    await asyncio.wait_for(task, 5)
    backups = list(messungenverzeichnis().rglob(".backup_*.json"))
    assert len(backups) == 1

    zweiter = AppState.starten(tmp_path / "app.db")  # der nächste Start
    assert zweiter.hrv_backups == backups
    zweiter.schliessen()

    state.hrv_backups = list(backups)
    zweites = state.profil_anlegen("Zweites")
    state.profil_wechseln(zweites.id)  # ein anderes Profil ist aktiv — egal
    seite = _seite()
    dialog = backup_dialog(seite, state)
    assert "Unvollständige Messung gefunden" in _baum_texte(dialog)
    assert any("Simulator H10 vom" in t for t in _baum_texte(dialog))

    # Über den Dialog (Ben, 16.10.2026: fror ein, „Später" schloss nicht): Das
    # Schreiben läuft in einem Thread, danach ist genau dieser Dialog zu.
    dialog.open = True
    knopf = next(c for c in _alle_controls(dialog) if isinstance(c, ft.FilledTonalButton))
    await knopf.on_click()
    assert not dialog.open and seite.aufrufe == []  # die Meldung kommt erst nach dem Schließen
    (eintrag,) = state.hrv.alle(start)
    assert eintrag.subject_id == start
    assert eintrag.file_path.startswith("Generator/sensor_")
    assert (messungenverzeichnis() / eintrag.file_path).exists()
    assert not backups[0].exists()
    assert state.hrv_backups == []
    assert state.hrv.laden(eintrag.id) is not None
    assert eintrag.duration_s >= 15

    # Noch einmal dasselbe Backup (Kopie): die Messung steht schon in der Liste
    backups[0].write_text(
        (messungenverzeichnis() / eintrag.file_path).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    state.hrv_backups = list(backups)
    assert backup_uebernehmen(state, backups[0]) is None
    assert not backups[0].exists()
    assert len(state.hrv.alle(start)) == 1


def test_uebersicht_zeilen_gleich_hoch_mit_und_ohne_grund() -> None:
    """Die Atemfrequenz hat mal einen Wert, mal einen Grund mit Knopf — die Zeile bleibt
    gleich hoch, sonst flackert die Ansicht darunter (Ben, 26.10.2026)."""
    from trainingsapp.ui.components.kacheln import (
        HAUPTWERT_HOEHE,
        ZEILE_HOEHE,
        KachelWert,
        uebersicht,
    )

    mit_grund = KachelWert(
        "Atemfrequenz 60 s",
        "–",
        "/min",
        grund="langsame Schwingung",
        aktion=("Atemübung", lambda: None),
    )
    mit_wert = KachelWert("Atemfrequenz 60 s", "12,0", "/min")

    def zeilen(w: KachelWert) -> list[ft.Container]:
        karte = uebersicht([KachelWert("Herzfrequenz", "70", "bpm", gross=True), w])
        # Container mit Höhe — ohne den Farbpunkt (8 px) vor jeder Zeile
        return [
            c
            for c in _alle_controls(karte)
            if isinstance(c, ft.Container) and c.height and c.height >= 20
        ]

    for w in (mit_grund, mit_wert):
        hoehen = sorted({c.height for c in zeilen(w)})
        assert hoehen == [ZEILE_HOEHE, HAUPTWERT_HOEHE]
    # Der Grund bleibt einzeilig — eine zweite Zeile würde die Höhe sprengen
    grund = next(
        c
        for c in _alle_controls(uebersicht([mit_grund]))
        if isinstance(c, ft.Text) and c.value == "langsame Schwingung"
    )
    assert grund.max_lines == 1
