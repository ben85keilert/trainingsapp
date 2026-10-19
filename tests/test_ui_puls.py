"""Geräte, die nur den Puls senden, und die Aufräumarbeiten der Messansicht (Ben, 17.10.2026).

- Puls (bpm) als Hauptkurve, wenn kein Intervall kommt — live und in der Aufzeichnung.
- Der graue Erklärtext steckt hinter einem „i“, die Diagnose hinter einem Knopf oben.
- Die Beschreibung steht als aufklappbarer Auszug im Status.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
fc = pytest.importorskip("flet_charts")

from hrv_core.recording import Beat, Recording, speichern  # noqa: E402

from attrappen import aufgabe_starten  # noqa: E402
from trainingsapp.core.models import HrvRecording  # noqa: E402
from trainingsapp.devices.base import DeviceStatus, Verbindung  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.profiles import (  # noqa: E402
    BLE_GENERIC,
    UHR_BROADCAST,
    profil_fuer_namen,
)
from trainingsapp.devices.simulated import SIM_PULS, SimulatedSource  # noqa: E402
from trainingsapp.ui.components.titel import titel_kopf  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.messung import (  # noqa: E402
    NUR_PULS_NACH,
    aufnahme_eintragen,
    messung,
    nur_puls,
)
from trainingsapp.ui.views.messung_detail import messung_detail_view  # noqa: E402


@pytest.fixture
def daten(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    yield state, tmp_path
    state.schliessen()


def _seite() -> SimpleNamespace:
    aufrufe: list = []
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
        height=900,
        width=412,
    )


def _alle(wurzel):
    gesehen: set[int] = set()

    def lauf(x):
        if not isinstance(x, ft.BaseControl) or id(x) in gesehen:
            return
        gesehen.add(id(x))
        yield x
        for name in ("controls", "content", "title", "actions"):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                yield from lauf(k)

    yield from lauf(wurzel)


def _lauf(profil, rr_ms: int, anzahl: int) -> Messlauf:
    lauf = Messlauf(SimulatedSource())
    lauf.profil, lauf.geraet_name = profil, "Forerunner 955"
    lauf.status = DeviceStatus(verbindung=Verbindung.VERBUNDEN)
    for i in range(anzahl):
        lauf.live.hinzufuegen(float(i), rr_ms, 70 + i % 5)
    return lauf


def test_nur_puls_aus_profil_oder_erkannt() -> None:
    """Im Geräteprofil hinterlegt (Uhr) — sonst erkannt, wenn kein Intervall kommt."""
    assert profil_fuer_namen("Forerunner 955") is UHR_BROADCAST
    assert profil_fuer_namen("Mi Smart Band 6") is UHR_BROADCAST
    assert not UHR_BROADCAST.hrv_moeglich
    assert nur_puls(_lauf(UHR_BROADCAST, 0, 0))  # schon vor dem ersten Paket
    assert not nur_puls(_lauf(UHR_BROADCAST, 820, 3))  # sendet doch Intervalle
    assert not nur_puls(_lauf(BLE_GENERIC, 0, NUR_PULS_NACH - 1))  # noch zu früh
    assert nur_puls(_lauf(BLE_GENERIC, 0, NUR_PULS_NACH))


def test_live_puls_als_hauptkurve(daten) -> None:
    state, _ = daten
    state.messlauf = _lauf(UHR_BROADCAST, 0, 60)
    seite = _seite()
    ansicht = messung(seite, state)
    alle = list(_alle(ansicht))
    texte = [c.value for c in alle if isinstance(c, ft.Text) and c.value]
    assert "HERZFREQUENZ" in texte and "RR-TACHOGRAMM" not in texte
    # Kacheln ohne Puls sagen, warum — nicht „zu wenige gute Schläge“
    assert "Gerät sendet nur den Puls" in texte
    assert "zu wenige gute Schläge" not in texte  # der Grund in einer Kachel
    schalter = next(c for c in alle if isinstance(c, ft.Switch))
    assert not schalter.visible  # ohne Intervalle nichts zu korrigieren
    kurve = next(c for c in alle if isinstance(c, fc.LineChart))
    assert max(len(s.points) for s in kurve.data_series) == 60
    # Was die Farben heißen: hinter dem „i“, nicht mehr als grauer Text darunter
    assert not any("Grau: alle Rohwerte" in t for t in texte)
    info = next(c for c in alle if isinstance(c, ft.IconButton) and c.icon == ft.Icons.INFO_OUTLINE)
    info.on_click()
    (blatt,) = seite.aufrufe
    assert "nur die **Herzfrequenz**" in next(
        c.value for c in _alle(blatt) if isinstance(c, ft.Markdown)
    )


def test_diagnose_hinter_einem_knopf_oben(daten) -> None:
    state, _ = daten
    lauf = _lauf(BLE_GENERIC, 820, 30)
    lauf.quelle.protokoll = ["12:00:00 Verbunden", "12:00:05 Erste Werte"]
    state.messlauf = lauf
    seite = _seite()
    ansicht = messung(seite, state)
    alle = list(_alle(ansicht))
    assert not any(isinstance(c, ft.ExpansionTile) for c in alle)  # kein Klappfeld unten
    knopf = next(
        c for c in alle if isinstance(c, ft.IconButton) and c.icon == ft.Icons.RECEIPT_LONG_OUTLINED
    )
    knopf.on_click()
    (blatt,) = seite.aufrufe
    assert any("Erste Werte" in (c.value or "") for c in _alle(blatt) if isinstance(c, ft.Text))
    # Der Simulator führt kein Protokoll — dort gibt es den Knopf nicht
    lauf.simulation = True
    state.messlauf = lauf
    alle = list(_alle(messung(_seite(), state)))
    knopf = next(
        c for c in alle if isinstance(c, ft.IconButton) and c.icon == ft.Icons.RECEIPT_LONG_OUTLINED
    )
    assert not knopf.visible


def test_beschreibung_als_aufklappbarer_auszug() -> None:
    umgeklappt: list[bool] = []
    zu = titel_kopf(
        "Abend",
        "Lang\nund breit",
        lambda: None,
        klein=True,
        umklappen=lambda: umgeklappt.append(True),
    )
    auszug = next(c for c in _alle(zu) if isinstance(c, ft.Text) and c.value == "Lang\nund breit")
    assert auszug.max_lines == 1
    knopf = next(c for c in _alle(zu) if isinstance(c, ft.IconButton))
    knopf.on_click()
    assert umgeklappt == [True]
    auf = titel_kopf(
        "Abend", "Lang\nund breit", lambda: None, klein=True, offen=True, umklappen=lambda: None
    )
    assert (
        next(
            c for c in _alle(auf) if isinstance(c, ft.Text) and c.value == "Lang\nund breit"
        ).max_lines
        is None
    )


def test_aufzeichnung_einer_reinen_pulsmessung(daten) -> None:
    """Ohne ein Intervall: Wanduhr als Achse, Puls als Kurve, Ø Herzfrequenz aus dem Puls."""
    state, tmp_path = daten
    beats = [Beat(t_s=0.0, rr_ms=0, hf_bpm=70 + i % 7, t_wall_s=float(i)) for i in range(1, 300)]
    rec = Recording(beats=beats, geraet="Forerunner 955", geraet_profil="watch_broadcast")
    pfad = speichern(rec, tmp_path / "Messungen" / "Uhr")
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="Forerunner 955",
        geraet_profil="watch_broadcast",
    )
    state.hrv.anlegen(eintrag)
    ansicht = messung_detail_view(_seite(), state, eintrag)
    alle = list(_alle(ansicht))
    texte = [c.value for c in alle if isinstance(c, ft.Text) and c.value]
    assert "HERZFREQUENZ" in texte
    assert any(t.startswith("Forerunner 955  ·  4:59") for t in texte)  # Dauer aus der Wanduhr
    assert "73" in texte  # Ø Herzfrequenz aus dem Puls des Geräts
    assert "Gerät sendet nur den Puls" in texte
    assert "zu wenige gute Schläge" not in texte  # der Grund in einer Kachel
    kurve = next(c for c in alle if isinstance(c, fc.LineChart))
    assert max(len(s.points) for s in kurve.data_series) == 120  # die ersten 2 min
    # Korrektur und Abschnitte gibt es ohne Intervalle nicht, Zuschneiden ebenso
    karten = [
        c
        for c in alle
        if isinstance(c, ft.Container)
        and any(t.value in ("KORREKTUR", "ABSCHNITTE") for t in _alle(c) if isinstance(t, ft.Text))
        and c.bgcolor is not None
    ]
    assert karten and not any(k.visible for k in karten)
    schere = next(
        c
        for c in ansicht.appbar.actions
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.CONTENT_CUT
    )
    assert not schere.visible


def test_erklaerungen_der_karten_hinter_dem_i(daten) -> None:
    """Abschnitte, Korrektur und Verlauf: Erklärtexte hinter dem „i“ (Ben, 17.10.2026) —
    unter den Tabellen bleibt nur, was die Zahlen einschränkt."""
    import shutil
    from pathlib import Path

    state, tmp_path = daten
    ordner = tmp_path / "Messungen" / "PolarH10"
    ordner.mkdir(parents=True)
    golden = Path(__file__).parent / "golden" / "rr" / "sensor_2026-05-23_125422.json"
    shutil.copy(golden, ordner / golden.name)
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=f"PolarH10/{golden.name}",
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)
    seite = _seite()
    alle = list(_alle(messung_detail_view(seite, state, eintrag)))
    texte = [c.value for c in alle if isinstance(c, ft.Text) and c.value]
    for grau in ("Werte je Abschnitt", "Vorschläge der Automatik", "Wo die Kurve", "Über Nähte"):
        assert not any(grau in t for t in texte), grau
    assert "Noch keine Abschnitte." in texte and "ganze Messung" in texte
    knoepfe = {
        c.tooltip: c
        for c in alle
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.INFO_OUTLINE
    }
    for tooltip, erklaert in (
        ("So arbeitest du mit Abschnitten", "Werte je Abschnitt"),
        ("So funktioniert die Korrektur", "Vorschläge der Automatik"),
        ("So liest du den Verlauf", "Über Nähte"),  # Bereich „Zeit“: Kurven und Tabelle
    ):
        knoepfe[tooltip].on_click()
        markdown = next(c.value for c in _alle(seite.aufrufe[-1]) if isinstance(c, ft.Markdown))
        assert erklaert in markdown, tooltip
    assert "Wo die Kurve abreißt" in markdown


async def test_uhr_im_simulator_bis_zur_aufzeichnung(daten) -> None:
    """Ende zu Ende mit dem Simulator „wie Uhr“: verbinden, aufnehmen, speichern, ansehen."""
    state, tmp_path = daten
    lauf = Messlauf(SimulatedSource(tempo=60.0), backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden(SIM_PULS, "Simulator Uhr")
    assert lauf.profil is UHR_BROADCAST
    assert nur_puls(lauf)  # schon vor dem ersten Wert: das Profil sagt es
    task = asyncio.create_task(lauf.laufen())
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < 150:
        await asyncio.sleep(0.01)
    state.messlauf = lauf
    live = list(_alle(messung(_seite(), state)))
    assert "HERZFREQUENZ" in [c.value for c in live if isinstance(c, ft.Text)]
    ergebnis = lauf.aufnahme_stoppen(tmp_path)
    await lauf.trennen()
    await asyncio.wait_for(task, 5)
    assert ergebnis is not None
    rec = ergebnis.recording
    assert not rec.hat_rr and rec.effektive_qualitaet() == "bpm_only"
    assert all(b.t_wall_s is not None for b in rec.beats)

    eintrag = aufnahme_eintragen(state, ergebnis, lauf.subject_id)
    seite = _seite()
    ansicht = messung_detail_view(seite, state, eintrag)
    await asyncio.gather(*seite.aufgaben)  # die Messdatei liest ein Thread (H39)
    alle = list(_alle(ansicht))
    texte = [c.value for c in alle if isinstance(c, ft.Text) and c.value]
    assert "HERZFREQUENZ" in texte
    assert any(t.startswith("Simulator Uhr  ·  2:") for t in texte)  # gut 2½ Minuten
    kurve = next(c for c in alle if isinstance(c, fc.LineChart))
    assert 115 <= max(len(s.points) for s in kurve.data_series) <= 121  # 1/s, erste 2 min
