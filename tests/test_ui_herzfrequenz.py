"""Herzfrequenz-Sicht und Einstellungen → Herzfrequenz (Ben, 29.10.2026; hrv-research
Entscheidungen 10–14): Umschalter, Kacheln, Skala, Zeit je Bereich, Erholung mit Marke,
Profilwerte eintragen, Bereichsmodell, Sicht merken. Ohne Fenster."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
fc = pytest.importorskip("flet_charts")

from attrappen import aufgabe_starten  # noqa: E402
from trainingsapp.core.hf_profil import Profilwert  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.simulated import SIM_SYNTH, SimulatedSource  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.einstellungen_herzfrequenz import (  # noqa: E402
    einstellungen_herzfrequenz,
)
from trainingsapp.ui.views.messung import messung  # noqa: E402


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
    routen: list[str] = []

    async def push_route(r: str) -> None:
        routen.append(r)

    return SimpleNamespace(
        route="/",
        views=[],
        update=lambda: None,
        show_dialog=aufrufe.append,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: aufgabe_starten(aufgaben, f, *a),
        push_route=push_route,
        aufgaben=aufgaben,
        aufrufe=aufrufe,
        routen=routen,
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
        for name in ("controls", "content", "title", "subtitle", "actions", "label", "leading"):
            wert = getattr(x, name, None)
            for k in wert if isinstance(wert, list) else [wert]:
                yield from lauf(k)

    yield from lauf(wurzel)


def _texte(wurzel) -> list[str]:
    return [c.value for c in _alle(wurzel) if isinstance(c, ft.Text) and c.value]


def _segment(wurzel, werte: list[str]) -> ft.SegmentedButton:
    return next(
        c
        for c in _alle(wurzel)
        if isinstance(c, ft.SegmentedButton) and [s.value for s in c.segments] == werte
    )


def _knopf(wurzel, text: str):
    return next(
        c
        for c in _alle(wurzel)
        if isinstance(c, ft.TextButton | ft.FilledButton | ft.FilledTonalButton)
        and c.content == text
    )


def _profil_fuellen(state: AppState) -> None:
    p = state.profil
    p.birth_year, p.geschlecht = 1986, "m"
    state.profil_speichern(p)
    state.profilwerte.hinzufuegen(
        Profilwert(p.id, "ruhe_hf", 55, "messung_morgen_5", date(2026, 10, 28))
    )


async def _lauf(state: AppState, tmp_path, *, sekunden: float = 20) -> tuple[Messlauf, object]:
    lauf = Messlauf(SimulatedSource(tempo=30.0), backup_basis=tmp_path)
    await lauf.verbinden(SIM_SYNTH, "Simulator H10")
    task = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    while lauf.aufnahme_dauer_s() < sekunden:
        await asyncio.sleep(0.01)
    return lauf, task


async def _ende(lauf: Messlauf, task) -> None:
    await lauf.trennen()
    await asyncio.wait_for(task, 5)


# -- Live ------------------------------------------------------------------------------


async def test_hf_sicht_ist_vorgabe_und_umschaltbar(daten) -> None:
    state, tmp_path = daten
    _profil_fuellen(state)
    lauf, task = await _lauf(state, tmp_path)
    try:
        seite = _seite()
        ansicht = messung(seite, state)
        texte = _texte(ansicht)
        assert "HERZFREQUENZ" in texte and "RR-TACHOGRAMM" not in texte
        assert "Reserve" in texte  # HF-Kacheln: Herzfrequenz, Reserve, Zeit im Bereich …
        assert any(t.startswith("ZEIT JE BEREICH") for t in texte)
        assert "ERHOLUNG" in texte  # HRV-Analyse bleibt im Baum, nur unsichtbar
        assert any(t.startswith("Ruhe 55") for t in texte)  # Skala beschriftet
        assert any("HFmax 185" in t and "geschätzt" in t for t in texte)  # Formel-Startwert
        chart = next(c for c in _alle(ansicht) if isinstance(c, fc.LineChart))
        assert chart.left_axis.title.value == "HF bpm"
        # Bereiche als Bänder hinter der Kurve, rechts beschriftet (zehn Cluster, Ben 30.10.)
        assert sum(1 for s in chart.data_series if s.below_line_bgcolor) >= 1
        assert chart.right_axis is not None and any(
            lbl.label.value.startswith("Bereich") for lbl in chart.right_axis.labels
        )
        # Umschalten auf HRV: Tachogramm, HRV-Kacheln — und gemerkt
        umschalter = _segment(ansicht, ["hf", "hrv"])
        assert umschalter.selected == ["hf"] and not umschalter.segments[1].disabled
        umschalter.on_change(SimpleNamespace(control=SimpleNamespace(selected=["hrv"])))
        assert state.hrv_sicht() == "hrv"
        texte = _texte(messung(seite, state))
        assert "RR-TACHOGRAMM" in texte and "RMSSD 30 s" in texte
        assert not any(t.startswith("ZEIT JE BEREICH") for t in texte)
    finally:
        await _ende(lauf, task)


async def test_hf_sicht_ohne_profil_fuehrt_zu_den_einstellungen(daten) -> None:
    state, tmp_path = daten
    lauf, task = await _lauf(state, tmp_path, sekunden=5)
    try:
        seite = _seite()
        ansicht = messung(seite, state)
        texte = _texte(ansicht)
        assert "Erst dann gibt es % der Reserve und Bereiche." in texte
        assert "Noch keine Zeit im Bezug." in texte
        _knopf(ansicht, "Ruhe-HF und HFmax eintragen").on_click()
        await asyncio.gather(*seite.aufgaben)
        assert seite.routen == ["/einstellungen/herzfrequenz"]
    finally:
        await _ende(lauf, task)


async def test_erholung_setzt_marke_und_bezug_wechselt(daten) -> None:
    state, tmp_path = daten
    _profil_fuellen(state)
    lauf, task = await _lauf(state, tmp_path, sekunden=12)
    try:
        seite = _seite()
        ansicht = messung(seite, state)
        _knopf(ansicht, "Belastung endet jetzt").on_click()
        assert state.hf_erholung is not None and state.hf_erholung["kontext"] == "dauer"
        marken = [
            e["marke"]
            for e in lauf.aufnahme.ereignisse
            if isinstance(e.get("marke"), dict) and e["marke"].get("art") == "erholung"
        ]
        assert len(marken) == 1 and marken[0]["haltung"] == "steht"
        ansicht = messung(seite, state)
        texte = _texte(ansicht)
        assert "HF am Ende" in texte and "HRR30" in texte and "HRR120" in texte
        assert "HRR180" in texte  # das freie Fenster X, Vorgabe 180 s (A22)
        # Haltung ändern schreibt in die Marke der Datei
        haltung = next(
            c for c in _alle(ansicht) if isinstance(c, ft.Dropdown) and c.label == "Haltung"
        )
        haltung.on_select(SimpleNamespace(control=SimpleNamespace(value="liegt")))
        assert marken[0]["haltung"] == "liegt"
        _knopf(messung(seite, state), "Erholung beenden").on_click()
        assert state.hf_erholung is None
        # Bezug 5 min / Aufnahme; Abschnitt nur, wenn einer läuft
        bezug = _segment(messung(seite, state), ["aufnahme", "abschnitt", "fenster"])
        assert bezug.segments[1].disabled
        bezug.on_change(SimpleNamespace(control=SimpleNamespace(selected=["fenster"])))
        assert state.hf_bezug == "fenster"
        assert any(t.startswith("ZEIT JE BEREICH · 5 MIN") for t in _texte(messung(seite, state)))
        lauf.abschnitt_starten("Belastung")
        bezug = _segment(messung(seite, state), ["aufnahme", "abschnitt", "fenster"])
        assert not bezug.segments[1].disabled
        bezug.on_change(SimpleNamespace(control=SimpleNamespace(selected=["abschnitt"])))
        assert any(
            t.startswith("ZEIT JE BEREICH · ABSCHNITT") for t in _texte(messung(seite, state))
        )
        assert state.live_hf.abschnitt is not None
    finally:
        await _ende(lauf, task)


# -- Einstellungen ------------------------------------------------------------------


def test_einstellungen_herzfrequenz_eintragen_und_modell(daten) -> None:
    state, _ = daten
    seite = _seite()
    ansicht = einstellungen_herzfrequenz(seite, state)
    texte = _texte(ansicht)
    assert "RUHE-HF" in texte and "HFMAX" in texte and "BEREICHE" in texte
    assert texte.count("kein Wert") >= 3  # Ruhe, VT1, VT2 — HFmax ohne Jahrgang auch
    # Jahrgang eintragen → Formel-Startwert
    jahrgang = next(
        c for c in _alle(ansicht) if isinstance(c, ft.TextField) and c.label == "Jahrgang"
    )
    jahrgang.value = "1986"
    jahrgang.on_submit(None)
    assert state.profil.birth_year == 1986
    ansicht = einstellungen_herzfrequenz(seite, state)
    assert any("geschätzt (Nes 2013 (HUNT))" in t for t in _texte(ansicht))
    # Geschlecht w → Gulati
    _segment(ansicht, ["w", "m", "d", "-"]).on_change(
        SimpleNamespace(control=SimpleNamespace(selected=["w"]))
    )
    assert state.profile.laden(state.profil.id).geschlecht == "w"
    assert state.hf_profil().formel.formel == "gulati"
    # Ruhe-HF eintragen: erstes Formular (Karte Ruhe-HF)
    ansicht = einstellungen_herzfrequenz(seite, state)
    felder = [c for c in _alle(ansicht) if isinstance(c, ft.TextField) and c.label == "Wert (bpm)"]
    felder[0].value = "58"
    _knopf(ansicht, "Eintragen").on_click()
    werte = state.profilwerte.alle(state.profil.id, "ruhe_hf")
    assert len(werte) == 1 and werte[0].wert == 58 and werte[0].quelle == "eintrag"
    assert state.hf_profil().vollstaendig
    # ungültiger Wert bleibt draußen
    ansicht = einstellungen_herzfrequenz(seite, state)
    felder = [c for c in _alle(ansicht) if isinstance(c, ft.TextField) and c.label == "Wert (bpm)"]
    felder[0].value = "500"
    _knopf(ansicht, "Eintragen").on_click()
    assert len(state.profilwerte.alle(state.profil.id, "ruhe_hf")) == 1
    # Vorschau der Bereiche (auto → zehn Cluster) und Modellwechsel
    texte = _texte(ansicht)
    assert "Bereich 10" in texte
    modell = next(
        c for c in _alle(ansicht) if isinstance(c, ft.Dropdown) and c.label == "Bereichsmodell"
    )
    modell.on_select(SimpleNamespace(control=SimpleNamespace(value="acsm")))
    assert state.hf_einstellungen().modell == "acsm"
    assert "moderat" in _texte(einstellungen_herzfrequenz(seite, state))
    # Eigene Grenzen
    modell.on_select(SimpleNamespace(control=SimpleNamespace(value="eigen")))
    ansicht = einstellungen_herzfrequenz(seite, state)
    grenze = next(c for c in _alle(ansicht) if isinstance(c, ft.TextField) and c.label == "Grenze")
    grenze.value = "120"
    _knopf(ansicht, "Hinzufügen").on_click()
    e = state.hf_einstellungen()
    assert len(e.eigene) == 1 and e.eigene[0].bpm == 120
    texte = _texte(einstellungen_herzfrequenz(seite, state))
    assert "Grenze 1: 120 bpm" in texte and "Bereich 2" in texte
    # Festsetzen und entfernen über die Verlaufszeile
    ansicht = einstellungen_herzfrequenz(seite, state)
    pin = next(
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.PUSH_PIN_OUTLINED
    )
    pin.on_click()
    assert state.hf_profil().ruhe.fest
    ansicht = einstellungen_herzfrequenz(seite, state)
    assert any("festgesetzt" in t for t in _texte(ansicht))
    # Sicht-Vorgabe
    _segment(ansicht, ["hf", "hrv"]).on_change(
        SimpleNamespace(control=SimpleNamespace(selected=["hrv"]))
    )
    assert state.hrv_einstellungen().standard_sicht == "hrv"
    # Ausnahmen
    state.ausnahmen.setzen(state.profil.id, "tag", "2026-10-28")
    ansicht = einstellungen_herzfrequenz(seite, state)
    assert "Tag 2026-10-28" in _texte(ansicht)
    _knopf(ansicht, "Wieder mitrechnen").on_click()
    assert state.ausnahmen.alle(state.profil.id) == {}


def test_herkunft_eines_werts_steht_leserlich_darunter(daten) -> None:
    """Ben, 30.10.2026: Tag, Uhrzeit, Fenster und Abschnitt statt einer Kennung."""
    from datetime import UTC, datetime, timedelta

    from trainingsapp.core.models import HrvRecording
    from trainingsapp.ui.views.einstellungen_herzfrequenz import herkunft_text

    state, _ = daten
    start = datetime(2026, 10, 28, 20, 3, tzinfo=UTC)
    rec = HrvRecording(subject_id=state.profil.id, file_path="P/n.json", started_at=start)
    state.hrv.anlegen(rec)
    p = Profilwert(
        state.profil.id,
        "ruhe_hf",
        51,
        "nacht",
        state.heute(),
        geraet="Polar H10",
        hrv_recording_id=rec.id,
        herkunft={
            "messung": rec.id,
            "fenster": [3 * 3600, 5 * 3600],
            "abschnitt": "seg-1",
            "abschnitt_name": "Schlafen",
            "grundlage": "abschnitt",
        },
    )
    state.profilwerte.hinzufuegen(p)
    ortszeit = start.astimezone()
    text = herkunft_text(p, state)
    assert text.startswith(f"Messung {ortszeit:%d.%m.%Y %H:%M} · Polar H10 · Fenster ")
    von = (ortszeit + timedelta(hours=3)).strftime("%H:%M")
    assert f"Fenster {von}–" in text and "Abschnitt „Schlafen“" in text and "seg-1" not in text
    ansicht = einstellungen_herzfrequenz(_seite(), state)
    assert text in _texte(ansicht)
    assert any(
        isinstance(c, ft.IconButton) and c.icon == ft.Icons.OPEN_IN_NEW for c in _alle(ansicht)
    )
    # ein Eintrag von Hand ohne Notiz: keine Herkunftszeile
    leer = Profilwert(state.profil.id, "ruhe_hf", 55, "eintrag", state.heute())
    assert herkunft_text(leer, state) == ""


def test_ruhepuls_aus_dem_tagesfeld_steht_in_der_liste_und_ist_entfernbar(daten) -> None:
    """Ben, 30.10.2026: „Einträge Ruhe-HF lassen sich nicht löschen“ — der geltende Wert kam
    aus dem Tagesfeld und stand in keiner Liste."""
    from trainingsapp.core import tagesfelder as tf

    state, _ = daten
    feld = tf.standardfeld(state.tagesfelder.alle(state.profil.id), tf.STANDARD_RUHEPULS)
    state.tageswerte.einmal_setzen(feld, state.heute(), wert=(57,))
    assert state.hf_profil().ruhe is not None and state.hf_profil().ruhe.quelle == "tagesfeld"
    ansicht = einstellungen_herzfrequenz(_seite(), state)
    texte = _texte(ansicht)
    assert any("Tagesfeld „Ruhepuls“" in t and "57" in t for t in texte)
    assert any(t.startswith("aus dem Tagesfeld „Ruhepuls“ vom") for t in texte)
    muell = [
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.IconButton) and c.tooltip == "Tageswert entfernen"
    ]
    assert len(muell) == 1
    muell[0].on_click()
    assert state.tageswerte.am_tag(state.profil.id, state.heute()) == []
    assert state.hf_profil().ruhe is None


def test_einstellungen_zeigen_herzfrequenz_kachel(daten) -> None:
    from trainingsapp.ui.views.einstellungen import einstellungen

    state, _ = daten
    seite = _seite()
    seite.platform = None
    texte = _texte(einstellungen(seite, state, SimpleNamespace()))
    assert "Herzfrequenz" in texte and any("Ruhe-HF und HFmax fehlen" in t for t in texte)


class _Ton:
    """Attrappe des Tondienstes: merkt, was gespielt wurde."""

    def __init__(self) -> None:
        self.gespielt: list[tuple[str, float, str]] = []

    async def laden(self, name: str, wav: bytes) -> None:
        pass

    async def spielen(self, name: str, lautstaerke: float = 1.0, quelle: str = "medien") -> None:
        self.gespielt.append((name, lautstaerke, quelle))


async def _aufgaben(seite) -> None:
    while seite.aufgaben:
        aufgaben = list(seite.aufgaben)
        seite.aufgaben.clear()
        await asyncio.gather(*aufgaben, return_exceptions=True)


async def test_hf_blatt_mittel_bereiche_und_signal(daten) -> None:
    """Ben, 30.10.2026: In der HF-Sicht hat „Fenster & Darstellung“ HF-Einstellungen — keine
    Verlaufskurven. Seit dem 10.11.2026 (A22): Wertebereich je Seite statt „Bereiche im Bild |
    alle“, „Zielbereich und Ton“ mit − und + statt des Felds, „Erholung messen“. Der Ton
    spielt, solange die HF außerhalb liegt — die Tonfolge nach Abstand."""
    state, tmp_path = daten
    _profil_fuellen(state)
    ton = _Ton()
    state.ton, state.toene_geladen = ton, True
    e = state.hf_einstellungen()
    e.alarm_an, e.alarm_bpm = True, 40  # der Simulator liegt sicher darüber
    state.hf_einstellungen_setzen(e)
    lauf, task = await _lauf(state, tmp_path)
    try:
        seite = _seite()
        ansicht = messung(seite, state)
        # Die Zeile „Zielbereich bis 40 − + Ton an“ (Skizze H4)
        assert _knopf(ansicht, "Ton an") is not None
        await _aufgaben(seite)
        assert [g[0] for g in ton.gespielt] == ["schale"]
        # Innerhalb der Tonfolge kein zweiter Klang
        lauf.beobachter(False)
        await _aufgaben(seite)
        assert len(ton.gespielt) == 1
        # Vorgabe des Wertebereichs: Ruhe-HF bis HFmax im Bild
        chart = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, fc.LineChart) and c.left_axis.title.value == "HF bpm"
        )
        assert chart.min_y <= 55 and chart.max_y >= 185
        # Das Blatt der HF-Sicht
        knopf = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.IconButton) and str(c.tooltip).startswith("Fenster & Darstellung")
        )
        knopf.on_click()
        blatt = seite.aufrufe[-1]
        assert isinstance(blatt, ft.BottomSheet)
        btexte = _texte(blatt)
        assert "ZEITACHSE" in btexte and "HERZFREQUENZ" in btexte
        assert "WERTEBEREICH" in btexte and "ZIELBEREICH UND TON" in btexte
        assert "ERHOLUNG MESSEN" in btexte and "KURVEN" not in btexte
        assert not any(t.startswith("RMSSD") for t in btexte)
        mittel = next(
            c
            for c in _alle(blatt)
            if isinstance(c, ft.Dropdown) and c.label == "Kurve als Mittel über"
        )
        mittel.on_select(SimpleNamespace(control=SimpleNamespace(value="10")))
        assert state.hrv_einstellungen().hf_mittel_s == 10
        # Wertebereich: oben Automatik, unten fest 60 — jede Seite für sich
        oben, unten = (
            c
            for c in _alle(blatt)
            if isinstance(c, ft.SegmentedButton)
            and [s.value for s in c.segments] == ["auto", "profil", "fest"]
        )
        assert oben.selected == ["profil"] and unten.selected == ["profil"]
        oben.on_change(SimpleNamespace(control=SimpleNamespace(selected=["auto"])))
        feld = next(
            c for c in _alle(blatt) if isinstance(c, ft.TextField) and c.label == "Fest unten"
        )
        feld.value = "60"
        feld.on_submit(None)
        e = state.hf_einstellungen()
        assert (e.achse_oben, e.achse_unten, e.achse_unten_bpm) == ("auto", "fest", 60.0)
        chart = next(
            c
            for c in _alle(messung(seite, state))
            if isinstance(c, fc.LineChart) and c.left_axis.title.value == "HF bpm"
        )
        assert chart.max_y < 185  # oben folgt der Kurve, nicht mehr der HFmax
        feld.value = "500"  # außerhalb: Hinweis, der alte Wert bleibt
        feld.on_submit(None)
        assert feld.error and state.hf_einstellungen().achse_unten_bpm == 60.0
        # Zielbereich: + rückt die obere Linie, der Schalter stellt den Ton ab
        plus = next(
            c for c in _alle(blatt) if isinstance(c, ft.IconButton) and c.tooltip == "Oben erhöhen"
        )
        plus.on_click()
        assert state.hf_einstellungen().alarm_bpm == 41
        plus.on_long_press()
        assert state.hf_einstellungen().alarm_bpm == 46
        schalter = next(
            c for c in _alle(blatt) if isinstance(c, ft.Switch) and c.label == "Ton außerhalb"
        )
        schalter.on_change(SimpleNamespace(control=SimpleNamespace(value=False)))
        assert state.hf_einstellungen().alarm_grenze() is None
        # Erholung messen: X ändern, ein festes Fenster abwählen
        x = next(c for c in _alle(blatt) if isinstance(c, ft.TextField) and c.label == "X")
        x.value = "95"
        x.on_submit(None)
        chip60 = next(
            c
            for c in _alle(blatt)
            if isinstance(c, ft.Chip) and isinstance(c.label, ft.Text) and c.label.value == "60"
        )
        chip60.on_select(SimpleNamespace(control=SimpleNamespace(selected=False)))
        assert state.hf_einstellungen().erholung_fenster() == (30, 95, 120)
    finally:
        await _ende(lauf, task)


async def test_zielbereich_zeile_stumm_und_ton_darunter(daten) -> None:
    """A22: − und + rücken den ganzen Zielbereich um 5 bpm; unter der unteren Linie klingt der
    tiefere Klang; „stumm“ schweigt, bis man es aufhebt."""
    state, tmp_path = daten
    _profil_fuellen(state)
    ton = _Ton()
    state.ton, state.toene_geladen = ton, True
    e = state.hf_einstellungen()
    e.alarm_an, e.alarm_bpm, e.ziel_unten_bpm = True, 228, 220  # der Simulator liegt darunter
    state.hf_einstellungen_setzen(e)
    lauf, task = await _lauf(state, tmp_path)
    try:
        seite = _seite()
        ansicht = messung(seite, state)
        await _aufgaben(seite)
        assert [g[0] for g in ton.gespielt] == ["glocke3"]
        plus = next(
            c
            for c in _alle(ansicht)
            if isinstance(c, ft.IconButton) and str(c.tooltip).startswith("Zielbereich senken")
        )
        plus.on_click()
        e = state.hf_einstellungen()
        assert (e.alarm_bpm, e.ziel_unten_bpm) == (223, 215)
        # Stumm bis Messende: kein Ton mehr, der Knopf hebt es auf
        from trainingsapp.core.hf_ziel import BIS_MESSENDE
        from trainingsapp.ui.hf_live import HfLive

        hl = HfLive(seite, state, lauf)
        hl.stumm_setzen(BIS_MESSENDE)
        state.hf_zielton.zuletzt = -1e9
        ansicht = messung(seite, state)
        await _aufgaben(seite)
        assert len(ton.gespielt) == 1
        state.hf_zielton.zuletzt = -1e9
        _knopf(ansicht, "Ton stumm").on_click()  # hebt es auf — der Ton ist gleich wieder da
        assert state.hf_stumm is None
        await _aufgaben(seite)
        assert len(ton.gespielt) == 2
    finally:
        await _ende(lauf, task)


def test_einstellungen_herzfrequenz_signal_karte(daten) -> None:
    state, _ = daten
    ton = _Ton()
    state.ton, state.toene_geladen = ton, True
    seite = _seite()
    view = einstellungen_herzfrequenz(seite, state)
    assert "ZIELBEREICH UND TON" in _texte(view)
    klang = next(
        c for c in _alle(view) if isinstance(c, ft.Dropdown) and c.label == "Klang darüber"
    )
    assert [o.key for o in klang.options][:2] == ["wechsel", "glocke1"]
    assert "schale" in [o.key for o in klang.options]
    klang.on_select(SimpleNamespace(control=SimpleNamespace(value="holz")))
    assert state.hf_einstellungen().alarm_klang == "holz"
    asyncio.run(_aufgaben(seite))
    assert [g[0] for g in ton.gespielt] == ["holz"]  # vorgespielt
    takt = next(c for c in _alle(view) if isinstance(c, ft.Dropdown) and c.label == "Tonfolge")
    assert [o.text for o in takt.options][:2] == ["nach Abstand", "alle 3 s"]  # A22
    assert takt.value == "0"
    takt.on_select(SimpleNamespace(control=SimpleNamespace(value="10")))
    assert state.hf_einstellungen().alarm_takt_s == 10


async def test_knoepfe_der_hf_sicht_bleiben_ueber_die_takte_dieselben(daten) -> None:
    """H69: Die Sicht frischt zweimal je Sekunde auf — Knöpfe und Bezugswahl entstehen dabei
    nicht neu (ein Tipp, der gerade läuft, ginge verloren), nur was sich ändert."""
    state, tmp_path = daten
    _profil_fuellen(state)
    lauf, task = await _lauf(state, tmp_path, sekunden=12)
    try:
        seite = _seite()
        ansicht = messung(seite, state)
        talk = _knopf(ansicht, "Sprechen wird schwer")
        ende = _knopf(ansicht, "Belastung endet jetzt")
        wahl = next(c for c in _alle(ansicht) if isinstance(c, ft.SegmentedButton))
        for _ in range(3):
            lauf.beobachter(False)
        assert _knopf(ansicht, "Sprechen wird schwer") is talk
        assert _knopf(ansicht, "Belastung endet jetzt") is ende
        assert wahl in list(_alle(ansicht))
        ende.on_click()  # der Zustand wechselt: jetzt entsteht die Knopfzeile neu
        lauf.beobachter(False)
        assert _knopf(ansicht, "Erholung beenden") is not ende
        assert _knopf(ansicht, "Sprechen wird schwer") is not None
    finally:
        await _ende(lauf, task)
