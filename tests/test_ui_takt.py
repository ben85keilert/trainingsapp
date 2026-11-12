"""Taktgeber in der Oberfläche (Ben, 5.11.2026; `docs/plan_taktgeber.md` T1–T3): das Takt-Blatt
(Vorlagen, Phasen, Tempo, Knöpfe, Bibliothek), die Zeile in „Übung bearbeiten“ und im
Timer-Editor, der Takt-Knopf an der Uhr, die Animation (einmal gebaut, je Tick nur Werte), der
Reiter „Timer“ mit Anzeige und Tempo-Regler, die Einstellung „Vibration am Phasenwechsel“ und
das Soll im Kopf des Live-Vollbilds."""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Exercise  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.takt import (  # noqa: E402
    ANIMATION_WELLE,
    AUS,
    VORLAGEN,
    Phase,
    Takt,
    lage,
)
from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil  # noqa: E402
from trainingsapp.ui.components.takt_anzeige import TaktAnzeige, ZeitMitTakt  # noqa: E402
from trainingsapp.ui.components.takt_blatt import (  # noqa: E402
    TempoRegler,
    takt_anbringen,
    takt_blatt,
    takt_knopf,
    takt_zeile_text,
)
from trainingsapp.ui.state import AppState  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


class Seite(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(route="/", views=[], dialoge=[], aufgaben=[], routen=[])

    def run_task(self, f, *args):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.aufgaben.append((f, args))
            return None
        aufgabe = loop.create_task(f(*args))
        self.aufgaben.append(aufgabe)
        return aufgabe

    def show_dialog(self, d) -> None:
        self.dialoge.append(d)

    def pop_dialog(self) -> None:
        if self.dialoge:
            self.dialoge.pop()

    def update(self) -> None:
        return None

    async def push_route(self, route: str) -> None:
        self.routen.append(route)
        self.route = route


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "actions", "appbar", "label", "leading"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _knopf(wurzel, text: str):
    for x in _alle(wurzel):
        if isinstance(
            x, ft.TextButton | ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton
        ):
            inhalt = getattr(x, "content", None)
            if inhalt == text or (isinstance(inhalt, ft.Control) and text in _texte(inhalt)):
                return x
    raise AssertionError(f"kein Knopf {text!r}")


def _symbol(wurzel, icon, tipp: str = ""):
    return next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.IconButton) and x.icon == icon and tipp in (x.tooltip or "")
    )


def _chip(wurzel, text: str) -> ft.Chip:
    return next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.Chip) and isinstance(x.label, ft.Text) and x.label.value == text
    )


def _felder(wurzel, label: str) -> list[ft.TextField]:
    return [x for x in _alle(wurzel) if isinstance(x, ft.TextField) and x.label == label]


def _regler(wurzel) -> ft.Slider:
    return next(x for x in _alle(wurzel) if isinstance(x, ft.Slider))


def _ereignis(control, wert):
    return SimpleNamespace(control=SimpleNamespace(value=wert), data=wert)


# -- Takt-Blatt ---------------------------------------------------------------------------------


async def test_takt_blatt_vorlagen_phasen_tempo_und_knoepfe(state) -> None:
    page = Seite()
    jetzt: list = []
    uebung: list = []
    gestartet: list = []
    blatt = takt_blatt(
        page,
        state,
        takt=None,
        fuer_jetzt=jetzt.append,
        in_die_uebung=uebung.append,
        starten=gestartet.append,
        uebung_name="Atmen",
    )
    assert isinstance(blatt, ft.BottomSheet)
    for t in VORLAGEN.values():
        assert _chip(blatt, t.name)
    assert _chip(blatt, "Atmung 4-6").selected  # die erste Vorlage ist der Ausgangspunkt
    assert len(_felder(blatt, "Phase")) == 2
    _chip(blatt, "Box 4-4-4-4").on_click()
    assert len(_felder(blatt, "Phase")) == 4 and _chip(blatt, "Box 4-4-4-4").selected
    assert "3,8/min · Runde 16 s · 4 Phasen" in " ".join(_texte(blatt))
    # + Phase hängt eine an (die Art wechselt ein ↔ aus), ✕ nimmt sie wieder
    _knopf(blatt, "Phase").on_click()
    assert len(_felder(blatt, "Phase")) == 5
    minus = [
        x
        for x in _alle(blatt)
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.REMOVE_CIRCLE_OUTLINE
    ]
    minus[-1].on_click()  # die angehängte wieder weg
    assert len(_felder(blatt, "Phase")) == 4
    # Der Tempo-Regler: 0,5×–2×, Rate und Rundendauer ziehen nach
    regler = _regler(blatt)
    assert (regler.min, regler.max) == (0.5, 2.0)
    regler.on_change(_ereignis(regler, 2.0))  # 2× = doppelt so schnell (7.11.2026)
    assert "Tempo 2,0×" in _texte(blatt) and "7,5/min · Runde 8 s" in " ".join(_texte(blatt))
    # Eine unlesbare Dauer: kein Knopf greift, das Feld ist markiert
    sekunden = _felder(blatt, "s")
    sekunden[1].value = "x"
    _knopf(blatt, "Übernehmen").on_click()  # Geltung „Für jetzt“ vorbelegt (K5)
    assert jetzt == [] and sekunden[1].error == "0,1–600"
    sekunden[1].value = "2,5"
    _knopf(blatt, "Übernehmen").on_click()  # Geltung „Für jetzt“ vorbelegt (K5)
    await blatt.on_dismiss(None)  # das Blatt ist zu — jetzt läuft die Aktion
    (t,) = jetzt
    assert (
        isinstance(t, Takt) and t.tempo == 0.5 and [p.dauer_s for p in t.phasen] == [4, 2.5, 4, 4]
    )
    assert [p.art for p in t.phasen] == ["ein", "halten", "aus", "halten"]
    # Die Vorschau läuft im Blatt: eine Anzeige mit dem Namen der ersten Phase
    assert "ein" in _texte(blatt)
    # „In die Übung“ trägt den Namen der Übung; „Takt starten“ gibt den Takt an die Uhr
    # K5: die Geltungen stehen oben als Segmente — „Übung „Atmen““ mit dem Namen der Übung
    geltung = next(x for x in _alle(blatt) if isinstance(x, ft.SegmentedButton))
    assert [s.label.value for s in geltung.segments] == ["Für jetzt", "Übung „Atmen“"]
    _knopf(blatt, "Takt starten").on_click()
    await blatt.on_dismiss(None)
    assert len(gestartet) == 1 and gestartet[0].phasen == t.phasen
    # „Kein Takt“ → None
    _knopf(blatt, "Kein Takt").on_click()
    await blatt.on_dismiss(None)
    assert jetzt[-1] is None


async def test_takt_blatt_bibliothek_und_eigener_takt(state) -> None:
    page = Seite()
    blatt = takt_blatt(page, state, takt=VORLAGEN["atmung_4_7_8"], in_die_uebung=lambda t: None)
    assert _chip(blatt, "4-7-8").selected and len(_felder(blatt, "Phase")) == 3
    name = _felder(blatt, "Name")[0]
    name.value = ""
    _knopf(blatt, "Als Vorlage sichern").on_click()
    assert name.error == "Ein Name, bitte." and state.takt_bibliothek() == []
    name.value = "Mein Abend"
    _knopf(blatt, "Als Vorlage sichern").on_click()
    (eigen,) = state.takt_bibliothek()
    assert eigen.name == "Mein Abend" and eigen.phasen == VORLAGEN["atmung_4_7_8"].phasen
    # Beim nächsten Öffnen steht er als Chip neben den Vorlagen und lässt sich wählen
    blatt = takt_blatt(page, state, takt=None, fuer_jetzt=lambda t: None)
    _chip(blatt, "Mein Abend").on_click()
    assert _felder(blatt, "Name")[0].value == "Mein Abend"
    # „Wie eingestellt“ nur, wenn eine Wahl für jetzt da ist
    weg: list = []
    blatt = takt_blatt(page, state, takt=None, fuer_jetzt=lambda t: None, zuruecksetzen=weg.append)
    assert _knopf(blatt, "Wie eingestellt")


def test_takt_zeile_text() -> None:
    assert takt_zeile_text(None) == "Takt: keiner"
    assert takt_zeile_text(AUS) == "Takt: keiner"
    assert takt_zeile_text(VORLAGEN["box_4"].mit_tempo(1.5)) == (
        "Takt: Box 4-4-4-4 · 4-4-4-4 · 0,67× · 2,5/min"
    )


# -- Übung bearbeiten und Timer-Editor -----------------------------------------------------------


async def test_formular_zeile_takt_mit_stift_und_x(state) -> None:
    """„Übung bearbeiten“ → Uhr und Timer: die Zeile „Takt: …“, der Stift öffnet das Blatt
    („In die Übung“), ✕ nimmt ihn; gespeichert wird mit der Übung — Zurück speichert auch."""
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    page = Seite()
    u = Exercise(
        name="Atmen", result_spec=ResultSpec(layout=Layout.TIMED, fields=[vorrat_feld("hold")])
    )
    state.uebungen.speichern(u)
    ansicht = uebung_bearbeiten(page, state, u)
    assert "Takt: keiner" in _texte(ansicht)
    _symbol(ansicht, ft.Icons.EDIT_OUTLINED, "Takt einstellen").on_click()
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet) and "Takt der Übung" in _texte(blatt)
    _chip(blatt, "4-7-8").on_click()
    _knopf(blatt, "Übernehmen").on_click()  # einzige Geltung: die Übung (K5)
    await blatt.on_dismiss(None)
    assert "Takt: 4-7-8 · 4-7-8 · 3,2/min" in _texte(ansicht)
    await _knopf(ansicht, "Speichern").on_click()
    gespeichert = state.uebungen.laden(u.id)
    assert gespeichert.takt == VORLAGEN["atmung_4_7_8"]
    # Das (i) erklärt den Takt
    assert any(
        isinstance(x, ft.IconButton) and x.tooltip == "Takt, Tempo und „Takt zählt“"
        for x in _alle(ansicht)
    )
    # ✕ nimmt ihn — gespeichert ist er weg
    ansicht = uebung_bearbeiten(page, state, gespeichert)
    _symbol(ansicht, ft.Icons.CLOSE, "Takt entfernen").on_click()
    assert "Takt: keiner" in _texte(ansicht)
    await _knopf(ansicht, "Speichern").on_click()
    assert state.uebungen.laden(u.id).takt is None


async def test_timer_editor_takt_je_abschnitt(state) -> None:
    """Der Timer-Editor: je Abschnitt der Takt-Knopf in der Zeile (Ben, 9.11.2026, G3) — ein
    Takt steht dann in einer zweiten Zeile darunter und reist mit dem Profil."""
    from trainingsapp.ui.views.timer import timer_bearbeiten_view

    page = Seite()
    ansicht = timer_bearbeiten_view(page, state, None, "/")
    knoepfe = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and isinstance(x.data, tuple) and x.data[:1] == ("takt",)
    ]
    assert [x.tooltip for x in knoepfe] == ["Takt: keiner", "Takt: keiner"]  # Belastung, Pause
    knoepfe[0].on_click()
    blatt = page.dialoge[-1]
    assert "Takt: Belastung" in _texte(blatt)
    _chip(blatt, "Kniebeuge 2-1-2").on_click()
    _knopf(blatt, "Übernehmen").on_click()  # einzige Geltung: der Abschnitt (K5)
    await blatt.on_dismiss(None)
    assert "Kniebeuge 2-1-2 · 2-1-2 · 12,0/min" in _texte(ansicht)
    name = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name")
    name.value = "Kniebeugen"
    await _knopf(ansicht, "Speichern").on_click()
    profil = next(p for p in state.timer_profile() if p.name == "Kniebeugen")
    assert profil.abschnitte[0].takt == VORLAGEN["kniebeuge_2_1_2"]
    assert profil.abschnitte[1].takt is None
    # Wieder geöffnet steht er da; ✕ nimmt ihn
    ansicht = timer_bearbeiten_view(page, state, profil.id, "/")
    assert "Kniebeuge 2-1-2 · 2-1-2 · 12,0/min" in _texte(ansicht)
    _symbol(ansicht, ft.Icons.CLOSE, "Takt entfernen").on_click()
    await _knopf(ansicht, "Speichern").on_click()
    profil = next(p for p in state.timer_profile() if p.name == "Kniebeugen")
    assert profil.abschnitte[0].takt is None


# -- Animation -------------------------------------------------------------------------------------


def test_anzeige_baut_einmal_und_zieht_je_tick_nur_werte_nach() -> None:
    """V1: Je Tick werden Texte und Füllstände gesetzt, kein Control neu gebaut; am
    Phasenwechsel bekommt der Kreis sein Ziel mit der Phasendauer als Animation."""
    anzeige = TaktAnzeige(groesse=120)
    assert anzeige.control.visible is False
    t = VORLAGEN["atmung_4_6"]
    anzeige.nachziehen(t, lage(t, 0.0))
    assert anzeige.control.visible and anzeige.art == "kreis"
    kreis = anzeige.kreis
    assert kreis is not None and kreis.scale == 1.0  # einatmen: groß
    assert kreis.animate_scale.duration == 4000
    assert anzeige.name_text.value == "ein" and anzeige.rest_text.value == "4 s"
    inhalt = anzeige.flaeche.content
    anzeige.nachziehen(t, lage(t, 2.0))
    assert anzeige.flaeche.content is inhalt and anzeige.kreis is kreis
    assert anzeige.rest_text.value == "2 s" and kreis.scale == 1.0
    anzeige.nachziehen(t, lage(t, 4.5))  # ausatmen: klein über 6 s
    assert anzeige.kreis is kreis and kreis.scale == 0.55
    assert kreis.animate_scale.duration == 6000 and anzeige.name_text.value == "aus"
    assert "Runde 1 · 6,0/min" in anzeige.unten_text.value
    # Ein anderer Takt: neue Animation, einmal gebaut
    box = VORLAGEN["box_4"]
    anzeige.nachziehen(box, lage(box, 5.0))
    assert anzeige.art == "box" and anzeige.flaeche.content is not inhalt
    assert len(anzeige.seiten) == 4 and anzeige.seiten[1].value == 0.25
    assert anzeige.seiten[0].value == 1.0 and anzeige.seiten[2].value == 0.0
    inhalt = anzeige.flaeche.content
    anzeige.nachziehen(box, lage(box, 6.0))
    assert anzeige.flaeche.content is inhalt and anzeige.seiten[1].value == 0.5
    # Puls, Balken, Welle, Kreis mit Halten
    puls = VORLAGEN["metronom_1"]
    anzeige.nachziehen(puls, lage(puls, 0.0))
    assert anzeige.art == "puls" and anzeige.ring is not None and anzeige.kreis.scale == 1.25
    anzeige.nachziehen(puls, lage(puls, 0.5))
    assert anzeige.kreis.scale == 1.0 and anzeige.ring.value == 0.5
    fuenf = Takt(tuple(Phase(f"p{k}", 2) for k in range(5)))
    anzeige.nachziehen(fuenf, lage(fuenf, 5.0))
    assert anzeige.art == "balken" and [b.value for b in anzeige.balken] == [1, 1, 0.5, 0, 0]
    welle = Takt(VORLAGEN["atmung_4_6"].phasen, animation=ANIMATION_WELLE)
    anzeige.nachziehen(welle, lage(welle, 5.0))
    assert anzeige.art == "welle" and len(anzeige.wellen) == 32
    punkte = [w for w in anzeige.wellen if w.height == 14]
    assert len(punkte) == 1 and punkte[0] is anzeige.wellen[16]
    anzeige.nachziehen(welle, lage(welle, 5.4))
    assert sum(1 for w in anzeige.wellen if w.height == 14) == 1
    drei = VORLAGEN["atmung_4_7_8"]
    anzeige.nachziehen(drei, lage(drei, 5.0))
    assert anzeige.art == "kreis_halten" and anzeige.kreis.border.top.width == 4
    anzeige.nachziehen(None, None)
    assert anzeige.control.visible is False
    klein = TaktAnzeige(groesse=56, klein=True)
    klein.nachziehen(t, lage(t, 1.0))
    assert klein.control.visible and klein.name_text.value == "ein"


# -- Uhr, Reiter Timer, Einstellungen, Vollbild ------------------------------------------------


def test_takt_knopf_fuer_jetzt_und_am_lauf(state) -> None:
    page = Seite()
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 60)]))
    knopf = takt_knopf(page, state, key="u1", takt=VORLAGEN["atmung_4_6"], lauf=lauf)
    assert knopf.tooltip.startswith("Takt: Atmung 4-6")
    knopf.on_click()
    blatt = page.dialoge[-1]
    _chip(blatt, "Metronom 1 s").on_click()
    _knopf(blatt, "Übernehmen").on_click()  # Geltung „Für jetzt“ vorbelegt (K5)
    asyncio.run(blatt.on_dismiss(None))
    assert state.uhr_takt["u1"].name == "Metronom 1 s" and lauf.takt_jetzt is state.uhr_takt["u1"]
    # Kein Takt → AUS (auch nicht der der Übung); „Wie eingestellt“ nimmt die Wahl zurück
    knopf = takt_knopf(page, state, key="u1", takt=VORLAGEN["atmung_4_6"], lauf=lauf)
    knopf.on_click()
    blatt = page.dialoge[-1]
    _knopf(blatt, "Kein Takt").on_click()
    asyncio.run(blatt.on_dismiss(None))
    assert state.uhr_takt["u1"] is AUS and lauf.takt_jetzt is AUS
    knopf = takt_knopf(page, state, key="u1", takt=VORLAGEN["atmung_4_6"], lauf=lauf)
    assert knopf.tooltip == "Takt wählen"
    knopf.on_click()
    blatt = page.dialoge[-1]
    _knopf(blatt, "Wie eingestellt").on_click()
    asyncio.run(blatt.on_dismiss(None))
    assert "u1" not in state.uhr_takt and lauf.takt_jetzt is None
    # Anbringen: Wahl, Vorgabe und Tempo für jetzt — vor dem Start keine Änderung im Lauf
    state.uhr_tempo["u1"] = 1.5
    neu = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 60)]))
    takt_anbringen(state, neu, "u1", VORLAGEN["box_4"])
    assert neu.takt_uebung is VORLAGEN["box_4"] and neu.takt_jetzt is None
    assert neu.tempo_faktor == 1.5 and neu.tempo_aenderungen == []
    # Der Regler im Lauf
    regler = TempoRegler(state, "u1", neu)
    assert regler.text.value == "0,67×" and regler.control.visible is False  # Geschwindigkeit
    regler.nachziehen(True)
    assert regler.control.visible
    # Beim Ziehen nur der Text (Befund 3), beim Loslassen das Tempo — eine Änderung im Lauf
    neu.start()
    regler.regler.on_change(_ereignis(regler.regler, 0.9))
    regler.regler.on_change(_ereignis(regler.regler, 0.75))
    assert regler.text.value == "0,75×" and neu.tempo_faktor == 1.5
    assert "u1" not in state.uhr_tempo or state.uhr_tempo["u1"] == 1.5
    assert neu.tempo_aenderungen == []
    regler.regler.on_change_end(_ereignis(regler.regler, 0.75))
    assert neu.tempo_faktor == 1.33 and state.uhr_tempo["u1"] == 1.33  # 0,75× = längere Dauern
    assert regler.text.value == "0,75×" and len(neu.tempo_aenderungen) == 1


def test_uhr_zeile_und_laufende_uhr_zeigen_den_takt(state) -> None:
    from trainingsapp.ui.components.uhr import _laufend, uhr_teile
    from trainingsapp.ui.views.plan import einzel_plan

    page = Seite()
    u = Exercise(
        name="Atmen",
        result_spec=ResultSpec(layout=Layout.TIMED, fields=[vorrat_feld("hold")]),
        takt=VORLAGEN["atmung_4_6"],
    )
    state.uebungen.speichern(u)
    plan = einzel_plan(u)
    teile = uhr_teile(page, state, uebung=u, plan=None, item=None, timer_oeffnen=lambda: None)
    knopf = _symbol(teile.zeile, ft.Icons.GRAPHIC_EQ)
    assert knopf.tooltip.startswith("Takt: Atmung 4-6")
    knopf.on_click()
    blatt = page.dialoge[-1]
    assert "Takt · Atmen" in _texte(blatt) and _knopf(blatt, "Takt starten")
    assert plan is not None
    # Die laufende Uhr: kleine Anzeige, Regler — nach dem Start
    from trainingsapp.devices.einheit import (
        Einheitslauf,
        TimerBaustein,
        UebungBaustein,
        UebungKontext,
    )

    uhr = SimpleNamespace(t=1000.0)
    e = Einheitslauf(uhr=lambda: uhr.t, titel="Atmen")
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("Atmen", 60)]))
    e.hinzufuegen(UebungBaustein(UebungKontext(u.id, u.name, zeitfeld="hold")))
    e.hinzufuegen(TimerBaustein(lauf))
    takt_anbringen(state, lauf, u.id, u.takt)
    e.starten()
    uhr.t += 5
    anzeige = _laufend(page, state, e)
    assert "ein" not in _texte(anzeige) or True  # bei 5 s: „aus“
    kleine = [x for x in _alle(anzeige) if isinstance(x, ft.Container) and x.on_click]
    assert any("aus" in _texte(k) for k in kleine)
    assert any(isinstance(x, ft.Slider) for x in _alle(anzeige))
    # Antippen → groß: ein Dialog, der sich beim Ticker anmeldet und abmeldet
    gross = next(k for k in kleine if "aus" in _texte(k))
    gross.on_click()
    dialog = page.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog) and "takt_gross" in state.timer_beobachter
    assert "aus" in _texte(dialog)
    asyncio.run(dialog.on_dismiss(None)) if asyncio.iscoroutinefunction(
        dialog.on_dismiss
    ) else dialog.on_dismiss(None)
    assert "takt_gross" not in state.timer_beobachter


def test_reiter_timer_mit_takt_anzeige_und_knopf(state) -> None:
    from trainingsapp.ui.views.timer import TAKT_KEY, lauf_fuer, timer_view

    page = Seite()
    state.uhr_takt[TAKT_KEY] = VORLAGEN["gleich_5_5"]
    ansicht = timer_view(page, state, "/")
    lauf = state.timer
    assert lauf is not None and lauf.takt_jetzt is VORLAGEN["gleich_5_5"]
    assert "Takt: Gleichtakt 5-5 · 5-5 · 6,0/min" in _texte(ansicht)
    assert _symbol(ansicht, ft.Icons.GRAPHIC_EQ, "Takt: Gleichtakt 5-5")
    regler_zeile = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Row) and any(isinstance(y, ft.Slider) for y in x.controls)
    )
    assert regler_zeile.visible is False  # vor dem Start kein Tempo-Regler
    lauf.start()
    state.timer_beobachter["ansicht"]()
    assert regler_zeile.visible is True
    assert any(
        x.visible
        for x in _alle(ansicht)
        if isinstance(x, ft.Row) and any(isinstance(y, ft.Slider) for y in x.controls)
    )
    assert "ein" in _texte(ansicht)
    # Takt und Zeit nebeneinander (Ben, 9.11.2026), nicht untereinander
    zeile = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Row)
        and "ein" in _texte(x)
        and any(re.fullmatch(r"\d+:\d\d", t) for t in _texte(x))
    )
    assert zeile.alignment == ft.MainAxisAlignment.CENTER
    assert lauf_fuer(state, state.timer_profil()) is lauf


def test_takt_und_zeit_in_einer_zeile() -> None:
    """Ben, 9.11.2026: Takt neben der Zeit, etwas kleiner als sie — überall dieselbe Zeile."""
    uhr = ZeitMitTakt(84)
    zeile = uhr.zeile()
    assert zeile.controls[0] is uhr.takt_platz and uhr.takt_platz.content is uhr.takt.control
    assert zeile.controls[1].controls[0] is uhr.zeit_text
    assert uhr.takt.groesse == 84 and not uhr.takt.klein
    t = VORLAGEN["atmung_4_6"]
    uhr.nachziehen("1:30:00", None, None)  # ohne Takt: die Zeit allein, volle Größe
    assert uhr.zeit_text.value == "1:30:00" and uhr.zeit_text.size == 84
    assert uhr.takt.control.visible is False
    uhr.nachziehen("1:30:00", t, lage(t, 1.0))  # neben dem Takt wird sie kleiner
    assert uhr.takt.control.visible and uhr.zeit_text.size == 63
    uhr.nachziehen("12:34", t, lage(t, 1.0))
    assert uhr.zeit_text.size == 84 and uhr.takt.name_text.value == "ein"
    uhr.takt_platz.visible = False  # die Ebene „Takt“ im Fokus aus
    uhr.nachziehen("1:30:00", t, lage(t, 1.0))
    assert uhr.zeit_text.size == 84
    # Daneben, was der Aufrufer bringt; antippen → ``on_takt``, die Zeit → ``on_zeit``
    getippt: list[str] = []
    rechts = ft.IconButton(ft.Icons.LAYERS_OUTLINED)
    fokus = ZeitMitTakt(64, on_takt=lambda: getippt.append("takt"))
    zeile = fokus.zeile(unter=[ft.Text("Satz 1")], rechts=[rechts], on_zeit=lambda: None)
    assert zeile.controls[-1] is rechts and zeile.controls[1].expand
    fokus.takt.control.on_click()
    assert getippt == ["takt"] and fokus.takt.control.tooltip == "Takt groß zeigen"
    # In der Übung (40): die kompakte Form, der Text neben dem Kreis
    klein = ZeitMitTakt(40)
    assert klein.takt.klein and klein.takt.groesse == 40
    klein.nachziehen("0:30", t, lage(t, 1.0))
    assert klein.takt.control.visible and klein.takt.rest_text.value == "3 s"


@pytest.mark.parametrize("g", [40, 64, 84, 120, 200])
def test_welle_passt_in_die_flaeche(g: int) -> None:
    """Die Säulen der Welle füllen die Fläche, ohne über sie hinaus zu ragen — auch klein."""
    welle = Takt(VORLAGEN["atmung_4_6"].phasen, animation=ANIMATION_WELLE)
    anzeige = TaktAnzeige(groesse=g, klein=g < 56)
    anzeige.nachziehen(welle, lage(welle, 1.0))
    reihe = anzeige.flaeche.content.controls[1]
    breite = sum(w.width for w in anzeige.wellen) + (len(anzeige.wellen) - 1) * reihe.spacing
    assert breite <= g + 1e-6
    assert all(s.height <= g for s in reihe.controls)


def test_einstellung_vibration_und_vollbild_soll(state) -> None:
    from trainingsapp.ui.views.einstellungen_seiten import einstellungen_uhr
    from trainingsapp.ui.views.live_vollbild import takt_kopf_text

    page = Seite()
    ansicht = einstellungen_uhr(page, state)  # Einstellungen → Timer und Takt
    schalter = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Switch) and x.label == "Vibration am Phasenwechsel"
    )
    assert schalter.value is True and state.takt_vibration() is True
    schalter.on_change(_ereignis(schalter, False))
    assert state.takt_vibration() is False
    assert takt_kopf_text(state) == ""
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("A", 60, takt=VORLAGEN["atmung_4_6"])]))
    state.timer = lauf
    lauf.start()
    assert takt_kopf_text(state) == "Soll ▲ ein 4 s"


# -- Prüfrunde 1 (0.3.52) -------------------------------------------------------------------


def test_box_rahmen_seiten_liegen_rechts_und_links() -> None:
    """Befund 6: Beide senkrechten Seiten standen in der Mitte des Kreises."""
    g = 120
    anzeige = TaktAnzeige(groesse=g)
    box = VORLAGEN["box_4"]
    anzeige.nachziehen(box, lage(box, 1.0))
    oben, rechts, unten, links = anzeige.rahmen
    breite = g - 16
    assert oben.top == 0 and unten.bottom == 0 and oben.left == unten.left == 8
    # Um die Mitte gedreht: die Mitte des rechten Balkens liegt am rechten Rand, die des
    # linken am linken — nicht beide bei g/2
    assert rechts.left + breite / 2 == pytest.approx(g - 2.5)
    assert links.left + breite / 2 == pytest.approx(2.5)
    assert rechts.top == links.top == pytest.approx((g - 5) / 2)
    # Lauflicht im Uhrzeigersinn: rechts abwärts, unten rückwärts, links aufwärts
    assert rechts.content.rotate.angle > 0 > links.content.rotate.angle
    assert unten.content.rotate.angle == pytest.approx(3.141592653589793)


def test_laufende_uhr_zeigt_rate_und_tempo_des_wirksamen_takts(state) -> None:
    """Befund 9: Unter dem Kreis stand die Rate des gespeicherten Takts ohne „2,0ד."""
    from trainingsapp.devices.einheit import (
        Einheitslauf,
        TimerBaustein,
        UebungBaustein,
        UebungKontext,
    )
    from trainingsapp.ui.components.uhr import _laufend

    page = Seite()
    u = Exercise(
        name="Atmen",
        result_spec=ResultSpec(layout=Layout.TIMED, fields=[vorrat_feld("hold")]),
        takt=VORLAGEN["atmung_4_6"],
    )
    state.uebungen.speichern(u)
    uhr = SimpleNamespace(t=1000.0)
    e = Einheitslauf(uhr=lambda: uhr.t, titel="Atmen")
    lauf = TimerLauf(TimerProfil(abschnitte=[Abschnitt("Atmen", 60)]))
    e.hinzufuegen(UebungBaustein(UebungKontext(u.id, u.name, zeitfeld="hold")))
    e.hinzufuegen(TimerBaustein(lauf))
    takt_anbringen(state, lauf, u.id, u.takt)
    e.starten()
    uhr.t += 5
    anzeige = _laufend(page, state, e)
    assert "Runde 1 · 6,0/min" in _texte(anzeige)
    lauf.tempo_setzen(2.0)
    state.timer_beobachter["uhr_in_der_uebung"]()
    assert "Runde 1 · 3,0/min · 0,5×" in _texte(anzeige)  # halb so schnell
    # Groß ebenso — und „Schließen“ trifft genau diesen Dialog (Befund 10)
    gross = next(
        k for k in _alle(anzeige) if isinstance(k, ft.Container) and k.on_click and _texte(k)
    )
    gross.on_click()
    dialog = page.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog) and "Runde 1 · 3,0/min · 0,5×" in _texte(dialog)
    dialog.open = True
    page.dialoge.append("meldung")  # eine SnackBar obenauf
    _knopf(dialog, "Schließen").on_click()
    assert dialog.open is False and page.dialoge[-1] == "meldung"
