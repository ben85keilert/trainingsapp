"""Der Timer-Editor nach Skizzen G3–G5 (Ben, 9.11.2026, `docs/plan_timer_editor.md` §2).

Fest oben Name und Gesamtzeit, die Reiter Zeiten · Klänge, je Abschnitt eine Zeile, je Teil die
Gesamtzeit mit den Runden; Teile kopiert ⧉, Abschnitte langes Drücken; unter „Klänge“ dieselben
Zeilen, die Namen nur zum Lesen; Wischen wechselt, nur die rechte Spalte gleitet."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Seite  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.timer import timer_bearbeiten_view  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


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


async def _aklick(handler, *args) -> None:
    ergebnis = handler(*args)
    if inspect.isawaitable(ergebnis):
        await ergebnis


def _reiter(ansicht) -> ft.SegmentedButton:
    return next(
        x for x in _alle(ansicht) if isinstance(x, ft.SegmentedButton) and x.data == "reiter"
    )


def _gesamt(ansicht) -> str:
    return next(x for x in _alle(ansicht) if isinstance(x, ft.Text) and x.data == "gesamt").value


async def test_kopf_gesamtzeit_reiter_und_wischen(state) -> None:
    ansicht = timer_bearbeiten_view(Seite(), state, None, "/")
    assert _gesamt(ansicht) == "0:45"  # Belastung 0:30 + Pause 0:15
    # Runden + : die Fußzeile des Teils und die Gesamtzeit oben
    plus = next(
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.icon == ft.Icons.ADD
    )
    plus.on_click()
    assert _gesamt(ansicht) == "1:30"
    fuss = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Text) and x.data == ("teil_gesamt", 0)
    )
    assert fuss.value == "1:30" and "2 × 0:45" in _texte(ansicht)
    # Das „i“ trägt den Erklärtext — er steht nicht mehr als Absatz da
    assert not any(t.startswith("Je Abschnitt ein Name") for t in _texte(ansicht))
    assert any(
        isinstance(x, ft.IconButton) and x.icon == ft.Icons.INFO_OUTLINE for x in _alle(ansicht)
    )
    # Reiter Klänge: Namen nur zum Lesen, rechts die Klänge, unten der ganze Timer
    reiter = _reiter(ansicht)
    reiter.on_change(SimpleNamespace(control=SimpleNamespace(selected=["klaenge"])))
    felder = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.TextField) and isinstance(x.data, tuple) and x.data[:1] == ("name",)
    ]
    assert len(felder) == 2 and not any(f.visible for f in felder)
    sichtbar = [x.value for x in _alle(ansicht) if isinstance(x, ft.Text) and x.visible]
    assert "Belastung" in sichtbar and "Pause" in sichtbar
    ganz = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.data == "klaenge_ganz"
    )
    assert ganz.visible
    stapel = [x for x in _alle(ansicht) if isinstance(x, ft.Stack)]
    assert len(stapel) == 2
    assert all(s.controls[0].offset.x == -1 and s.controls[1].offset.x == 0 for s in stapel)
    assert all(s.controls[0].animate_offset is not None for s in stapel)  # es gleitet
    # Wischen nach rechts: zurück zu den Zeiten — nach links wieder zu den Klängen
    gesten = next(x for x in _alle(ansicht) if isinstance(x, ft.GestureDetector))
    gesten.on_horizontal_drag_end(SimpleNamespace(primary_velocity=900))
    assert reiter.selected == ["zeiten"] and all(f.visible for f in felder) and not ganz.visible
    assert all(s.controls[0].offset.x == 0 and s.controls[1].offset.x == 1 for s in stapel)
    gesten.on_horizontal_drag_end(SimpleNamespace(primary_velocity=-900))
    assert reiter.selected == ["klaenge"]
    gesten.on_horizontal_drag_end(SimpleNamespace(primary_velocity=-60))  # zu langsam
    assert reiter.selected == ["klaenge"]


async def test_teil_und_abschnitt_kopieren(state) -> None:
    seite = Seite()
    ansicht = timer_bearbeiten_view(seite, state, None, "/")
    kopieren = next(
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.data == ("teil_kopieren", 0)
    )
    kopieren.on_click()
    teile = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and isinstance(x.data, tuple) and x.data[:1] == ("teil",)
    ]
    assert len(teile) == 2 and _gesamt(ansicht) == "1:30"
    # Langes Drücken auf die Pause im ersten Teil: kopieren (P151)
    zeile = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.data == ("abschnitt", 0, 1)
    )
    zeile.on_long_press(None)
    dialog = seite.dialoge[-1]
    kacheln = {x.title.value: x for x in _alle(dialog) if isinstance(x, ft.ListTile)}
    assert set(kacheln) == {"Kopieren", "Entfernen"}
    kacheln["Kopieren"].on_click(None)
    await _aklick(dialog.on_dismiss, None)
    assert _gesamt(ansicht) == "1:45"
    name = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name")
    name.value = "Doppelt"
    await _aklick(_knopf(ansicht, "Speichern").on_click)
    profil = next(p for p in state.timer_profile() if p.name == "Doppelt")
    assert [a.name for a in profil.abschnitte] == ["Belastung", "Pause", "Pause"]
    assert [[a.name for a in t.abschnitte] for t in profil.teile] == [["Belastung", "Pause"]]


async def test_klaenge_je_abschnitt_und_signale_als_blatt(state) -> None:
    seite = Seite()
    ansicht = timer_bearbeiten_view(seite, state, None, "/")
    _reiter(ansicht).on_change(SimpleNamespace(control=SimpleNamespace(selected=["klaenge"])))
    wahlen = [x for x in _alle(ansicht) if isinstance(x, ft.Dropdown)]
    assert len(wahlen) == 4  # zwei Abschnitte, neue Runde, Ende
    wahlen[0].value = "glocke1"
    wahlen[0].on_select(SimpleNamespace(control=wahlen[0]))
    wahlen[-1].value = "gong"
    wahlen[-1].on_select(SimpleNamespace(control=wahlen[-1]))
    # „Signale ›“: ein Blatt über dem Editor — nichts Ungespeichertes geht verloren
    _knopf(ansicht, "Signale ›").on_click(None)
    blatt = seite.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet) and "Signale für alle Timer" in _texte(blatt)
    assert seite.route == "/"
    name = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name")
    name.value = "Mit Klang"
    await _aklick(_knopf(ansicht, "Speichern").on_click)
    profil = next(p for p in state.timer_profile() if p.name == "Mit Klang")
    assert [a.klang for a in profil.abschnitte] == ["glocke1", ""] and profil.ende_klang == "gong"
