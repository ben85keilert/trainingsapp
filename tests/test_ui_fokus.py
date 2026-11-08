"""Der Fokus — die Trainingsansicht zur laufenden Uhr (Ben, 7.11.2026, `docs/plan_planblock.md`
§B): Chips Takt · Bewegung · HF, die HF-Kachel, die Bildfolge im Takt, der Knopf an der Uhr und
die Einstellung „Fokus beim Start der Uhr öffnen“."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe  # noqa: E402
from trainingsapp.core.bewegungsbild import mit_bewegungsbild  # noqa: E402
from trainingsapp.core.models import Exercise  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.takt import VORLAGEN  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.core.zaehlen import SensorWahl  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.ui.components.bewegungsbild import Bildfolge, bewegung_im_fokus  # noqa: E402
from trainingsapp.ui.state import FOKUS_HF, AppState  # noqa: E402
from trainingsapp.ui.views.uebung_timer import uebung_timer_view  # noqa: E402

#: Ein „PNG“ mit Kopf für 4 quadratische Bilder (1024 × 256) — mehr braucht die App nicht
STREIFEN = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00\x00\x00\rIHDR"
    + (1024).to_bytes(4, "big")
    + (256).to_bytes(4, "big")
    + b"\x08\x06\x00\x00\x00"
)


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    yield state, uhr, gurt
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


def _alle(c):
    yield c
    for name in ("content", "controls", "label", "leading", "appbar", "actions", "title"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    knoepfe = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton
    for x in _alle(c):
        if isinstance(x, knoepfe):
            beschriftung = x.content.value if isinstance(x.content, ft.Text) else x.content
            if beschriftung == text:
                return x
    raise AssertionError(f"kein Knopf {text!r}")


def _kniebeuge(state, *, bild: bool) -> Exercise:
    """Eine Kniebeuge mit Takt (ab · halten · auf) und Timer — mit eigener Bildfolge oder nur
    der Sensor-Vorlage (dann gilt die mitgelieferte)."""
    profil = TimerProfil(id="satz", name="Satz 30 s", abschnitte=[Abschnitt("Satz", 30)], runden=1)
    u = Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(layout=Layout.SINGLE, fields=[vorrat_feld("reps")]),
        timer=[profil.als_dict()],
        takt=VORLAGEN["kniebeuge_2_1_2"],
        beschleunigung=SensorWahl(wiederholungen=True, vorlage="kniebeuge"),
    )
    if bild:
        rel = state.bewegungsbilder.schreiben(STREIFEN)
        u.media = mit_bewegungsbild(u.media, rel)
    state.uebungen.speichern(u)
    return u


async def _sekunden(state, uhr, gurt, n: int) -> None:
    for _ in range(n):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if state.einheit is not None and state.einheit.laeuft:
            state.einheit.takt()


async def test_fokus_chips_hf_und_bildfolge_im_takt(umgebung) -> None:
    state, uhr, gurt = umgebung
    u = _kniebeuge(state, bild=True)
    seite = Seite()
    basis = f"/uebung/{u.id}"
    vorher = uebung_timer_view(seite, state, basis, u)
    assert vorher.appbar.title.value == "Timer · Kniebeuge"
    _knopf(vorher, "Starten").on_click()
    await _sekunden(state, uhr, gurt, 3)
    fokus = uebung_timer_view(seite, state, basis, u)
    assert fokus.appbar.title.value == "Fokus · Kniebeuge"
    # Die Ebenen als ein Knopf neben der Zeit (Ben, 8.11.2026 spät) — ein Menü mit Haken
    ebenen = next(
        x
        for x in _alle(fokus)
        if isinstance(x, ft.PopupMenuButton) and x.icon == ft.Icons.LAYERS_OUTLINED
    )
    assert [i.content.value for i in ebenen.items] == ["Takt", "Bewegung", "HF", "Kurve"]
    assert all(i.checked for i in ebenen.items)
    # Ohne den Chip „zählt“ im Kopf (P148) — der ist Anzeige, keine Kurve
    chips = [
        c
        for c in _alle(fokus)
        if isinstance(c, ft.Chip) and c.label.value not in ("zählt", "zählt nicht")
    ]
    # Die Kurven-Einblendung (Ben: „HF, RR, RMSSD, SDNN, Atemfrequenz, RSA“): Reihen als
    # Chips, Vorgabe HF und RMSSD, je gewählter Reihe ein Streifen mit dem letzten Wert
    assert [c.label.value for c in chips] == [
        "HF",
        "RR",
        "RMSSD",
        "SDNN",
        "Atemfrequenz",
        "RSA",
    ]
    assert [c.selected for c in chips] == [True, False, True, False, False, False]
    assert "RMSSD" in _texte(fokus) and any(t.endswith(" bpm") for t in _texte(fokus))
    rr_chip = chips[1]
    rr_chip.on_select(SimpleNamespace(control=rr_chip))
    assert state.fokus_kurven() == ["hf", "rr", "rmssd"]
    assert "HF" in _texte(fokus) and "60" in _texte(fokus)  # der Gurt schlägt im Sekundentakt
    # Die eigene Bildfolge: ein Streifen aus 4 Bildern, im Takt vor und zurück
    streifen = [
        x
        for x in _alle(fokus)
        if isinstance(x, ft.Stack) and x.controls and isinstance(x.controls[0], ft.Image)
    ]
    assert streifen and streifen[0].controls[0].width == 4 * streifen[0].controls[0].height
    # „HF“ im Ebenen-Menü nimmt die Kachel weg — gemerkt, der Haken geht mit
    hf = next(i for i in ebenen.items if i.content.value == "HF")
    hf.on_click(None)
    assert FOKUS_HF not in state.fokus_ebenen() and hf.checked is False
    karte = next(x for x in _alle(fokus) if isinstance(x, ft.Container) and "HF" in _texte(x)[:1])
    assert karte.visible is False
    state.einheit.timer.lauf.abbrechen()
    await _sekunden(state, uhr, gurt, 2)


def test_bildfolge_waehlt_das_bild_nach_takt_und_zeit() -> None:
    folge = Bildfolge("x.png", 12, hoehe=100)
    assert folge.control.width == 100 and folge.bild.width == 1200
    t = VORLAGEN["kniebeuge_2_1_2"]
    from trainingsapp.core.takt import lage

    folge.nachziehen(t, lage(t, t.dauer_s(0) / 2), 0.0)  # mitten im „ab“
    assert 0 < folge.index < 11 and folge.bild.left == -folge.index * 100
    folge.nachziehen(None, None, 0.0)  # ohne Takt: Pendel über die Zeit
    assert folge.index == 0
    folge.nachziehen(None, None, 1.5)
    assert folge.index == 11


def test_mitgelieferte_kniebeuge_ohne_eigenes_bild(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        u = _kniebeuge(state, bild=False)
        paar = bewegung_im_fokus(state, u)
        assert paar is not None
        _control, folge = paar
        assert isinstance(folge, Bildfolge) and folge.anzahl == 12
        assert folge.bild.src.endswith("kniebeuge.png")
        ohne = Exercise(name="Planke")
        assert bewegung_im_fokus(state, ohne) is None
    finally:
        state.schliessen()


def test_fokus_knopf_an_der_laufenden_uhr_und_einstellung(tmp_path, monkeypatch) -> None:
    from trainingsapp.core.timer import TimerLauf
    from trainingsapp.devices.einheit import (
        Einheitslauf,
        TimerBaustein,
        UebungBaustein,
        UebungKontext,
    )
    from trainingsapp.ui.components.uhr import _laufend
    from trainingsapp.ui.views.einstellungen import einstellungen

    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    try:
        page = Seite()
        u = Exercise(name="Planke")
        state.uebungen.speichern(u)
        e = Einheitslauf(uhr=lambda: 0.0, titel="Planke")
        e.hinzufuegen(UebungBaustein(UebungKontext(u.id, u.name)))
        e.hinzufuegen(TimerBaustein(TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 60)]))))
        e.starten()
        geoeffnet: list[int] = []
        anzeige = _laufend(page, state, e, fokus=lambda: geoeffnet.append(1))
        knopf = next(
            x
            for x in _alle(anzeige)
            if isinstance(x, ft.IconButton) and x.icon == ft.Icons.OPEN_IN_FULL
        )
        assert knopf.tooltip.startswith("Fokus")
        knopf.on_click()
        assert geoeffnet == [1]
        assert not any(
            isinstance(x, ft.IconButton) and x.icon == ft.Icons.OPEN_IN_FULL
            for x in _alle(_laufend(page, state, e))
        )
        # Die Einstellung: Vorgabe an (P145, 8.11.2026), der Schalter stellt sie
        assert state.fokus_auto() is True
        ansicht = einstellungen(page, state, SimpleNamespace())
        schalter = next(
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.Switch) and x.label == "▶ öffnet den Fokus"
        )
        assert schalter.value is True
        schalter.value = False
        schalter.on_change(SimpleNamespace(control=schalter))
        assert state.fokus_auto() is False
    finally:
        state.schliessen()
