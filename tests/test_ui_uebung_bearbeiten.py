"""„Übung bearbeiten“ aufgeräumt (Ben, 2.11.2026, `docs/plan_uebung_bearbeiten.md`): Symbol oder
Bild oben mit Blatt und Ablage, Beschreibung als Editor an Ort und Stelle, Parameter als
Knöpfe mit Karten (Name, Chips mit ✕, Ziel), Erklärtexte im (i)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.anhaenge import BILD, Ziel  # noqa: E402
from trainingsapp.core.result_spec import vorrat_feld  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.components.notizeditor import Textnotiz  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten  # noqa: E402

#: Ein kleines, gültiges JPEG — die Ablage lehnt ab, was sich nicht ablaufen lässt
JPEG = b"\xff\xd8\xff\xe0\x00\x06JFIF\xff\xda\x00\x02" + b"0" * 200 + b"\xff\xd9"


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    routen: list[str] = []
    dialoge: list = []

    async def push_route(route: str) -> None:
        routen.append(route)

    p = SimpleNamespace(
        route="/",
        views=[],
        routen=routen,
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: dialoge.pop() if dialoge else None,
        push_route=push_route,
        run_task=lambda f, *a: None,
    )
    return p


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "actions", "appbar", "label", "leading"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _chip(wurzel, text: str) -> ft.Chip:
    return next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.Chip) and isinstance(x.label, ft.Text) and x.label.value == text
    )


def _knopf(wurzel, text: str):
    for x in _alle(wurzel):
        if isinstance(x, ft.TextButton | ft.FilledButton | ft.OutlinedButton | ft.IconButton):
            inhalt = getattr(x, "content", None)
            if inhalt == text or (isinstance(inhalt, ft.Control) and text in _texte(inhalt)):
                return x
    raise AssertionError(f"kein Knopf {text!r}")


def _speichern(ansicht) -> None:
    asyncio.run(_knopf(ansicht, "Speichern").on_click())


def _symbol_kachel(ansicht) -> ft.Container:
    return next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.tooltip == "Symbol oder Bild wählen"
    )


def test_symbol_oben_blatt_bild_und_ablage(page, state) -> None:
    """Punkt 1: Das Symbol steht oben, ein Tipp öffnet das Blatt; dort die Symbole, die
    eigenen Bilder der Ablage (wählen, löschen) und die Wege zu Fotoauswahl und Kamera."""
    u = state.uebungen.laden(seed_id("kniebeuge"))
    ansicht = uebung_bearbeiten(page, state, u)
    kachel = _symbol_kachel(ansicht)
    assert isinstance(kachel.content, ft.Icon)
    # ganz oben, links — im Reiter „Übung“, der zuerst offen ist
    seite = next(x for x in _alle(ansicht) if getattr(x, "data", None) == "reiter_uebung")
    assert seite.visible and seite.controls[0].controls[0] is kachel
    kachel.on_click()
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    texte = _texte(blatt)
    assert "EIGENE BILDER" in texte and "SYMBOLE" in texte
    assert "Noch keine eigenen Bilder — hochladen oder aufnehmen." in texte
    assert _knopf(blatt, "Foto hochladen") and _knopf(blatt, "Foto aufnehmen")
    # Ein Symbol wählen: das Blatt schließt, die Kachel zeigt es, Speichern schreibt es
    hiking = next(
        x
        for x in _alle(blatt)
        if isinstance(x, ft.Container) and x.tooltip == "hiking" and x.on_click
    )
    hiking.on_click()
    _speichern(ansicht)
    assert state.uebungen.laden(u.id).icon_key == "hiking"
    # Ein eigenes Bild in der Ablage: wählen → Bild statt Symbol, überall rund
    rel = state.uebungsbilder.schreiben(JPEG)
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(u.id))
    _symbol_kachel(ansicht).on_click()
    blatt = page.dialoge[-1]
    bild = next(
        x
        for x in _alle(blatt)
        if isinstance(x, ft.Container) and isinstance(x.content, ft.Image) and x.on_click
    )
    assert x_tooltip(bild) == "ungenutzt"
    bild.on_click()
    kachel = _symbol_kachel(ansicht)
    assert any(isinstance(x, ft.Image) for x in _alle(kachel))
    _speichern(ansicht)
    gespeichert = state.uebungen.laden(u.id)
    assert gespeichert.image_path == rel and gespeichert.icon_key == "hiking"
    (eintrag,) = state.uebungsbilder.alle()
    assert eintrag.uebungen == ((u.id, u.name),)
    # Im Katalog und auf der Übungsseite: das Bild, quadratisch mit runden Ecken (P109)
    from trainingsapp.ui.components.uebungsbild import ECKE, uebungsbild

    eckig = uebungsbild(state, "hiking", rel, groesse=32)
    assert isinstance(eckig, ft.Container) and eckig.border_radius == 32 * ECKE
    assert isinstance(uebungsbild(state, "hiking", "Symbole/fehlt.jpg"), ft.Icon)
    # Aus der Ablage löschen: Datei weg, die Übung zeigt wieder ihr Symbol
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(u.id))
    _symbol_kachel(ansicht).on_click()
    blatt = page.dialoge[-1]
    kreuz = next(
        x
        for x in _alle(blatt)
        if isinstance(x, ft.Container) and x.tooltip == "Aus der Ablage löschen"
    )
    kreuz.on_click()  # trägt nur diese Übung — ohne Rückfrage
    assert state.uebungsbilder.alle() == [] and not state.uebungsbilder.datei(rel).exists()
    assert state.uebungen.laden(u.id).image_path is None
    assert isinstance(_symbol_kachel(ansicht).content, ft.Icon)


def x_tooltip(c) -> str | None:
    return c.tooltip


def test_kamera_und_fotoauswahl_fuer_das_symbol(page, state) -> None:
    """„auch Upload ermöglichen“: Die Wege führen über die Kamera- und Hochladen-Seite mit
    dem Ziel ``uebung/<id>`` — das Formular speichert vorher; „Behalten“ legt das Bild in
    die Ablage und an die Übung."""
    from trainingsapp.ui.views.anhang_aufnahme import _Aufnahme, ziel_name

    u = state.uebungen.laden(seed_id("kniebeuge"))
    ansicht = uebung_bearbeiten(page, state, u)
    _symbol_kachel(ansicht).on_click()
    blatt = page.dialoge[-1]
    asyncio.run(_knopf(blatt, "Foto aufnehmen").on_click())
    assert page.routen == [f"/uebung/{u.id}/bearbeiten/anhang/aufnehmen/uebung/{u.id}/foto"]
    ziel = Ziel.fuer_uebung(u.id)
    assert ziel_name(state, ziel) == "Symbol: Kniebeuge"
    a = _Aufnahme(page, state, ziel, BILD)
    a.daten = JPEG
    asyncio.run(a.behalten())
    neu = state.uebungen.laden(u.id)
    assert neu.image_path and state.uebungsbilder.vorhanden(neu.image_path)
    assert a.daten is None and page.dialoge[-1].content.value == "Bild gespeichert"


def test_beschreibung_in_abschnitten_mit_editor_an_ort_und_stelle(page, state) -> None:
    """Punkt 2 und P108: Die Beschreibung besteht aus Abschnitten (Name + Inhalt) in eigener
    Reihenfolge; ein Tipp öffnet den Editor der Notizen (↶ ↷ Abbrechen Fertig), gespeichert
    wird mit dem Formular — als ein Text mit ``## Name``-Zeilen."""
    from trainingsapp.core.beschreibung import abschnitte

    u = state.uebungen.laden(seed_id("kniebeuge"))
    ansicht = uebung_bearbeiten(page, state, u)
    assert "BESCHREIBUNG" in _texte(ansicht) and u.description in _texte(ansicht)
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.multiline]
    karte = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.ink and x.on_click and u.description in _texte(x)
    )
    karte.on_click()
    (feld,) = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.multiline]
    editor = feld.on_change.__self__
    assert isinstance(editor, Textnotiz) and feld.value == u.description and feld.autofocus
    feld.value = "Tief in die Hocke, Fersen am Boden."
    feld.on_change(SimpleNamespace(control=feld))
    asyncio.run(editor.fertig())
    assert "Tief in die Hocke, Fersen am Boden." in _texte(ansicht)  # wieder die Karte
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.multiline]
    assert state.uebungen.laden(u.id).description == u.description  # erst das Formular
    # Ein zweiter Abschnitt mit Namen, dann nach oben
    _knopf(ansicht, "Abschnitt hinzufügen").on_click()
    (feld,) = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.multiline]
    name = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.TextField) and x.label == "Name des Abschnitts"
    )
    name.value = "Für mich"
    feld.value = "langsam, Knie hinter den Zehen"
    feld.on_change(SimpleNamespace(control=feld))
    hoch = next(
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.tooltip == "Nach oben"
    )
    hoch.on_click()
    asyncio.run(feld.on_change.__self__.fertig())
    texte = _texte(ansicht)
    assert texte.index("Für mich") < texte.index("Tief in die Hocke, Fersen am Boden.")
    _speichern(ansicht)
    gespeichert = state.uebungen.laden(u.id).description
    assert (
        gespeichert
        == "## Für mich\nlangsam, Knie hinter den Zehen\nTief in die Hocke, Fersen am Boden."
    )
    assert [(a.name, a.text) for a in abschnitte(gespeichert)] == [
        ("Für mich", "langsam, Knie hinter den Zehen\nTief in die Hocke, Fersen am Boden.")
    ] or len(abschnitte(gespeichert)) == 2
    assert page.dialoge[-1].content.value == "Gespeichert"


def test_parameter_als_knoepfe_mit_karten_namen_chips_und_ziel(page, state) -> None:
    """Punkt 3, 4, 6, 7: Oben ein Knopf je Vorratsfeld, darunter je eingeschaltetem eine
    Karte mit eigenem Namen, Chips (✕ nimmt einen ungenutzten aus der Wahl) und dem Ziel."""
    u = state.uebungen.laden(seed_id("kniebeuge"))
    ansicht = uebung_bearbeiten(page, state, u)
    texte = _texte(ansicht)
    assert "PARAMETER" in texte and "VORGABE FÜR PLÄNE" not in texte
    # Keine Schalter mehr, keine Erklärtexte — das (i) je Abschnitt
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.Switch) and "Wdh" in (x.label or "")]
    assert not any(t.startswith("Eingeschaltete Parameter") for t in texte)
    hilfen = [
        x.tooltip
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.HELP_OUTLINE
    ]
    assert (
        "Parameter, Chips und Ziel" in hilfen
        and "Uhr: Stoppuhr, Timer, zählt, Zeit stellen" in hilfen
    )
    knoepfe = {
        x.label.value: x
        for x in _alle(ansicht)
        if isinstance(x, ft.Chip)
        and isinstance(x.label, ft.Text)
        and x.label.value
        in {"Wiederholungen", "Haltezeit", "Gewicht", "Skala", "Seite", "Freitext"}
    }
    assert knoepfe["Wiederholungen"].selected and not knoepfe["Gewicht"].selected
    # Die Karte: Name und Ziel
    namen = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name"]
    assert [n.value for n in namen[1:]] == ["Wiederholungen"]  # [0] ist der Name der Übung
    # Ohne Wert ist das Ziel zu — „Ziel setzen …“ öffnet es (8.11.2026)
    ziel_knoepfe = [
        x for x in _alle(ansicht) if isinstance(x, ft.TextButton) and x.content == "Ziel setzen …"
    ]
    assert len(ziel_knoepfe) == 1
    ziel_knoepfe[0].on_click()
    ziel = next(
        x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Ziel je Satz"
    )
    ziel.value = "3x12"
    # Gewicht einschalten: eine zweite Karte mit Chips 5 10 20 — das Ziel dort zu, ein Knopf
    knoepfe["Gewicht"].on_select()
    texte = _texte(ansicht)
    assert "kg" in texte
    assert [
        x.label for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Ziel"
    ] == []
    assert [
        x for x in _alle(ansicht) if isinstance(x, ft.TextButton) and x.content == "Ziel setzen …"
    ]
    # Ein ungenutzter Chip trägt ✕ — gewählte nicht
    assert _chip(ansicht, "5kg").on_delete is None  # gewählt (aus dem Vorrat)
    _chip(ansicht, "5kg").on_select()  # abwählen
    chip = _chip(ansicht, "5kg")
    assert not chip.selected and chip.on_delete is not None
    chip.on_delete()
    assert not [c for c in _alle(ansicht) if isinstance(c, ft.Chip) and c.label.value == "5kg"]
    # Umbenennen: „Wiederholungen“ → „Wdh. tief“
    namen = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name"]
    namen[1].value = "Wdh. tief"
    _speichern(ansicht)
    neu = state.uebungen.laden(u.id)
    reps, weight = neu.result_spec.field_by_key("reps"), neu.result_spec.field_by_key("weight")
    assert reps.label == "Wdh. tief" and reps.quick == [10, 15, 20]
    assert weight.quick == [10, 20] and vorrat_feld("weight").quick == [5, 10, 20]
    assert neu.default_target == {"reps": [12, 12, 12]}


def test_mehrfachfelder_einer_art_und_zaehlt_als(page, state) -> None:
    """P106 (Ben, 2.11.2026: „Mehrfachfelder sollen direkt möglich sein. Zeitfelder können der
    Stoppuhr zugeordnet werden. Mehrere Skalen machen eh Sinn“): „+“ auf der Karte legt ein
    zweites Feld derselben Art an (``hold_2``, eigener Name, eigene Chips), ✕ nimmt es weg;
    „Zählt als“ bietet jedes Zeitfeld an; der Timer trägt in das gewählte ein."""
    from trainingsapp.core.timer_eintrag import Gelaufen, ergebnis
    from trainingsapp.core.uebung_timer import zaehlt_als

    u = state.uebungen.laden(seed_id("kniebeuge"))
    ansicht = uebung_bearbeiten(page, state, u)
    _chip(ansicht, "Haltezeit").on_select()  # Haltezeit an
    plus = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton)
        and (x.tooltip or "").startswith("Noch ein Feld „Haltezeit“")
    )
    plus.on_click()
    namen = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name"]
    assert [n.value for n in namen[1:]] == ["Wiederholungen", "Haltezeit", "Haltezeit 2"]
    namen[3].value = "Pause"
    # Zählt als: Haltezeit, Pause, Zeit — gewählt wird die Pause
    wahl = next(x for x in _alle(ansicht) if isinstance(x, ft.SegmentedButton))
    uhr_an = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Switch) and x.label == "Uhr beim Üben"
    )
    uhr_an.on_change()  # zeichnet die Wahl mit den Namen neu
    assert [s.value for s in wahl.segments] == ["hold", "hold_2", "duration"]
    assert [s.label.value for s in wahl.segments] == ["Haltezeit", "Pause", "Zeit"]
    wahl.selected = ["hold_2"]
    _speichern(ansicht)
    neu = state.uebungen.laden(u.id)
    assert [f.key for f in neu.result_spec.fields] == ["reps", "hold", "hold_2"]
    assert neu.result_spec.field_by_key("hold_2").label == "Pause" and neu.zaehlt_als == "hold_2"
    felder = [f.key for f in neu.result_spec.fields]
    assert zaehlt_als(felder, neu) == "hold_2"
    assert ergebnis([Gelaufen("Halten", 1, 30.0, True, 0, 30.0)], "hold_2") == {"hold_2": [30]}
    # ✕ nimmt das zweite Feld weg (beide Karten tragen eins), der Knopf „Haltezeit“ bleibt an;
    # „zählt als“ fällt auf die Haltezeit zurück
    ansicht = uebung_bearbeiten(page, state, neu)
    weg = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.tooltip == "Dieses Feld entfernen"
    ]
    assert len(weg) == 2
    weg[-1].on_click()
    assert _chip(ansicht, "Haltezeit").selected
    _speichern(ansicht)
    neu = state.uebungen.laden(u.id)
    assert [f.key for f in neu.result_spec.fields] == ["reps", "hold"]
    assert zaehlt_als([f.key for f in neu.result_spec.fields], neu) == "hold"


def test_neue_uebung_zweimal_speichern_legt_eine_an(page, state) -> None:
    """N82: Doppeltipp auf „Speichern“ oder Speichern und gleich Zurück — eine Übung, und
    nach dem Speichern gilt das Formular nicht mehr als geändert."""
    ansicht = uebung_bearbeiten(page, state, None)
    name = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name")
    name.value = "Seitstütz neu"
    _speichern(ansicht)
    _speichern(ansicht)
    assert [u.name for u in state.uebungen.alle()].count("Seitstütz neu") == 1
