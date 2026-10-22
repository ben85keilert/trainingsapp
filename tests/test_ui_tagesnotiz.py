"""Die Notiz zum Tag direkt schreiben (Ben, 22.10.2026) — `components/tagesnotiz.py` in der
Tagesansicht: Feld statt Dialog, Autosave, ↶ ↷, Abbrechen, Fertig, Zurück speichert, und
Foto · Video · Audio zum Tag."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.anhaenge import AUDIO, Qualitaet, Ziel, neuer_anhang  # noqa: E402
from trainingsapp.ui.components import tagesnotiz as tn  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.tag import UEBERSICHT, ZEITLEISTE, tagesansicht  # noqa: E402

M4A = b"\x00\x00\x00\x1cftypM4A " + b"0" * 400


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
    aufgaben: list = []

    async def push_route(route: str) -> None:
        routen.append(route)

    def run_task(funktion, *_a):
        aufgaben.append(funktion)
        return object()  # wie eine laufende Aufgabe — das Speichern ruft der Test selbst

    return SimpleNamespace(
        route="/",
        views=[],
        routen=routen,
        dialoge=dialoge,
        aufgaben=aufgaben,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        push_route=push_route,
        run_task=run_task,
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "actions", "appbar", "label"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _feld(wurzel) -> ft.TextField:
    (feld,) = [
        x for x in _alle(wurzel) if isinstance(x, ft.TextField) and x.hint_text == tn.HINWEIS
    ]
    return feld


def _notiz(feld: ft.TextField) -> tn.Tagesnotiz:
    """Das Objekt hinter dem Feld (die Handler sind seine Methoden)."""
    notiz = feld.on_change.__self__
    assert isinstance(notiz, tn.Tagesnotiz)
    return notiz


def _tippen(notiz: tn.Tagesnotiz, text: str) -> None:
    notiz.feld.value = text
    notiz.feld.on_change(SimpleNamespace(control=notiz.feld))


def _symbole(c) -> list:
    return [x.icon for x in _alle(c) if isinstance(x, ft.IconButton)]


def _gespeichert(state: AppState) -> str:
    return state.tagesnotizen.lesen(state.profil.id, state.heute())


async def test_feld_statt_dialog_mit_autosave(page, state, monkeypatch) -> None:
    """Kein Dialog mehr: Das Feld steht im Block, gespeichert wird nach einer Pause."""
    monkeypatch.setattr(tn, "SPEICHERN_NACH_S", 0.0)
    state.tagesnotizen.setzen(state.profil.id, state.heute(), "Schulter fest")
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    feld = _feld(ansicht)
    assert feld.value == "Schulter fest" and feld.multiline
    notiz = _notiz(feld)
    # Ohne Schreiben: Foto · Video · Audio zum Tag statt ↶ ↷
    assert notiz.anhang_leiste.visible and not notiz.schreib_leiste.visible
    assert _symbole(notiz.anhang_leiste)[:3] == [
        ft.Icons.CAMERA_ALT_OUTLINED,
        ft.Icons.VIDEOCAM_OUTLINED,
        ft.Icons.MIC_NONE,
    ]
    knoepfe = list(_alle(notiz.schreib_leiste))
    notiz.feld.on_focus(None)
    assert notiz.schreib_leiste.visible and not notiz.anhang_leiste.visible
    assert _symbole(notiz.schreib_leiste) == [ft.Icons.UNDO, ft.Icons.REDO]
    assert "Abbrechen" in [
        x.content for x in _alle(notiz.schreib_leiste) if isinstance(x, ft.TextButton)
    ]
    # Dieselben Knöpfe wie vorher — ein ersetzter Knopf bekäme den Klick nicht mehr
    assert list(_alle(notiz.schreib_leiste)) == knoepfe
    _tippen(notiz, "Schulter fest, Knie gut")
    assert page.aufgaben  # das Speichern wartet auf die Pause
    await notiz._spaeter_speichern()
    assert _gespeichert(state) == "Schulter fest, Knie gut"
    assert notiz.stand.value == "gespeichert"
    assert page.dialoge == []  # kein Popup


async def test_rueckgaengig_holt_ein_geloeschtes_stueck_zurueck(page, state) -> None:
    """„… falls man aus Versehen was löscht“: ↶ holt das Stück in einem Schritt zurück und
    speichert; ↷ nimmt es wieder weg."""
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    notiz = _notiz(_feld(ansicht))
    notiz.feld.on_focus(None)
    _tippen(notiz, "Schulter fest, Knie gut")
    _tippen(notiz, "Schulter fest")  # markiert und gelöscht
    notiz.feld.on_blur(None)
    assert _gespeichert(state) == "Schulter fest"
    assert not notiz.zurueck_knopf.disabled and notiz.vor_knopf.disabled
    await notiz.rueckgaengig()
    assert notiz.feld.value == "Schulter fest, Knie gut" == _gespeichert(state)
    await notiz.wiederholen()
    assert notiz.feld.value == "Schulter fest" == _gespeichert(state)


async def test_abbrechen_stellt_den_anfang_her_mit_rueckgaengig(page, state) -> None:
    state.tagesnotizen.setzen(state.profil.id, state.heute(), "alt")
    notiz = _notiz(_feld(tagesansicht(page, state, state.heute(), mit_datum=False)))
    notiz.feld.on_focus(None)
    _tippen(notiz, "ganz neu")
    notiz.feld.on_blur(None)
    assert _gespeichert(state) == "ganz neu"
    await notiz.abbrechen()
    assert notiz.feld.value == "alt" == _gespeichert(state)
    assert not notiz.schreibt and notiz.anhang_leiste.visible
    (meldung,) = page.dialoge
    assert isinstance(meldung, ft.SnackBar) and meldung.action == "Rückgängig"
    meldung.on_action()  # war ein Versehen
    assert notiz.feld.value == "ganz neu" == _gespeichert(state)


async def test_fertig_und_zurueck_auf_heute_beenden_das_schreiben(page, state) -> None:
    """Zurück macht Autosave: Beim Schreiben meldet sich die Notiz zum Speichern vor dem
    Verlassen an; Zurück auf „Heute“ beendet das Schreiben wie „Fertig“."""
    notiz = _notiz(_feld(tagesansicht(page, state, state.heute(), mit_datum=False)))
    notiz.feld.on_focus(None)
    assert state.schreiben_beenden == notiz.fertig
    _tippen(notiz, "vor dem Wegwischen")
    state.vor_dem_verlassen[tn.SICHERN]()  # App geht in den Hintergrund
    assert _gespeichert(state) == "vor dem Wegwischen"
    assert state.schreiben_beenden is not None
    await state.schreiben_beenden()
    assert not notiz.schreibt and state.schreiben_beenden is None
    assert tn.SICHERN not in state.vor_dem_verlassen
    # Der Verlauf bleibt: wieder hineintippen, ↶ geht noch
    notiz.feld.on_focus(None)
    assert notiz.verlauf.kann_rueckgaengig


def test_feld_ueber_die_ganze_breite(page, state) -> None:
    """„Setze das Feld auf die ganze Breite“: Ohne ``expand`` oder ``width`` gäbe Flet dem
    Textfeld feste 300 px — die Spalte streckt es."""
    notiz = _notiz(_feld(tagesansicht(page, state, state.heute(), mit_datum=False)))
    spalte = notiz.control()
    assert notiz.feld in spalte.controls
    assert spalte.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
    assert notiz.feld.width is None and not notiz.feld.expand


async def test_fertig_und_abbrechen_nehmen_dem_feld_den_fokus(page, state) -> None:
    """„Der Fertig-Button macht nicht fertig“ (v0.3.15): Der Fokus ging an den Knopf, der mit
    seiner Leiste verschwand — Flutter gab ihn dem Feld zurück, die Tastatur ging wieder auf.
    Jetzt nimmt ``blur`` dem Feld den Fokus, jedes Mal mit einem neuen Wert."""
    notiz = _notiz(_feld(tagesansicht(page, state, state.heute(), mit_datum=False)))
    assert isinstance(notiz.feld, tn.Notizfeld) and notiz.feld.blur is None
    assert notiz.feld._c == "TextField"  # Flet zeichnet ein gewöhnliches Textfeld
    notiz.feld.on_focus(None)
    _tippen(notiz, "fertig geschrieben")
    await notiz.fertig()
    erster = notiz.feld.blur
    assert erster and not notiz.schreibt and notiz.anhang_leiste.visible
    assert _gespeichert(state) == "fertig geschrieben"
    notiz.feld.on_focus(None)
    _tippen(notiz, "doch nicht")
    await notiz.abbrechen()
    assert notiz.feld.blur not in (None, erster)
    assert notiz.feld.value == "fertig geschrieben" == _gespeichert(state)


async def test_daneben_tippen_beendet_das_schreiben(page, state, monkeypatch) -> None:
    """„Der Klick aus dem Fenster raus soll … speichern“: Ein Tipp neben das Feld beendet das
    Schreiben wie „Fertig“ — nach der Nachfrist, denn auch ↶ und ↷ liegen daneben, und Flutter
    meldet den Tipp schon beim Aufsetzen, ihren Klick erst beim Loslassen."""
    monkeypatch.setattr(tn, "NACHFRIST_S", 0.0)
    notiz = _notiz(_feld(tagesansicht(page, state, state.heute(), mit_datum=False)))
    notiz.feld.on_focus(None)
    _tippen(notiz, "Knie gut, Schulter fest")
    _tippen(notiz, "Knie gut")  # ein Stück gelöscht
    notiz.feld.on_tap_outside(None)  # der Finger setzt auf ↶ auf …
    zeit = notiz._daneben_um
    await notiz.rueckgaengig()  # … und hebt ab
    await notiz._nach_daneben(zeit)
    assert notiz.schreibt and notiz.feld.value == "Knie gut, Schulter fest"
    notiz.feld.on_tap_outside(None)  # irgendwo sonst
    await notiz._nach_daneben(notiz._daneben_um)
    assert not notiz.schreibt and notiz.anhang_leiste.visible and notiz.feld.blur
    assert _gespeichert(state) == "Knie gut, Schulter fest"
    assert tn.SICHERN not in state.vor_dem_verlassen and state.schreiben_beenden is None
    page.aufgaben.clear()
    notiz.feld.on_tap_outside(None)  # ohne Schreiben: nichts
    assert page.aufgaben == []


def test_auffrischen_behaelt_den_stand(page, state) -> None:
    """Baut die Ansicht die Spalte neu (hier: Darstellung umschalten), entsteht ein neues Feld
    mit demselben Text — und demselben Verlauf."""
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    altes = _feld(ansicht)
    notiz = _notiz(altes)
    notiz.feld.on_focus(None)
    _tippen(notiz, "halb geschrieben")
    umschalter = next(x for x in _alle(ansicht) if isinstance(x, ft.SegmentedButton))
    umschalter.selected = [ZEITLEISTE]
    umschalter.on_change(SimpleNamespace(control=umschalter))
    neues = _feld(ansicht)
    assert neues is not altes
    assert _notiz(neues) is notiz and neues.value == "halb geschrieben"
    assert notiz.verlauf.kann_rueckgaengig
    state.tag_darstellung = UEBERSICHT


def test_zeitleiste_feld_am_ende_oder_an_der_uhrzeit(page, state) -> None:
    state.tag_darstellung = ZEITLEISTE
    ohne = tagesansicht(page, state, state.heute(), mit_datum=False)
    assert _feld(ohne).value == ""  # gleich zum Schreiben, kein „+ Notiz zum Tag“
    assert "Notiz zum Tag" in _texte(ohne)
    state.tagesnotizen.setzen(state.profil.id, state.heute(), "Schulter fest")
    mit = tagesansicht(page, state, state.heute(), mit_datum=False)
    assert _feld(mit).value == "Schulter fest"
    knoepfe = [x.content for x in _alle(mit) if isinstance(x, ft.TextButton)]
    assert "Notiz zum Tag" not in knoepfe
    state.tag_darstellung = UEBERSICHT


async def test_foto_video_audio_zum_tag(page, state) -> None:
    """Die Knöpfe führen zur Aufnahme für den Tag; Anhänge am Tag stehen als Kacheln unter
    der Notiz — eine Audioaufnahme mit Klangsymbol."""
    heute = state.heute()
    ton = neuer_anhang(Ziel.fuer_tag(state.profil.id, heute), AUDIO, Qualitaet.MITTEL)
    state.anhaenge.anlegen(ton, M4A)
    ansicht = tagesansicht(page, state, heute, mit_datum=False)
    notiz = _notiz(_feld(ansicht))
    kamera, video, mikro = [x for x in _alle(notiz.anhang_leiste) if isinstance(x, ft.IconButton)][
        :3
    ]
    await mikro.on_click()
    await kamera.on_click()
    assert page.routen == [
        f"/anhang/aufnehmen/tag/{heute.isoformat()}/audio",
        f"/anhang/aufnehmen/tag/{heute.isoformat()}/foto",
    ]
    assert video.tooltip == "Video zum Tag"
    assert any(isinstance(x, ft.Icon) and x.icon == ft.Icons.GRAPHIC_EQ for x in _alle(ansicht))
    kachel = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.width == 64 and x.on_click
    )
    await kachel.on_click()
    assert page.routen[-1] == f"/anhang/{ton.id}"


def test_tagesansicht_eines_anderen_tags(page, state) -> None:
    """In `/tag/<datum>` gehört die Notiz zu diesem Tag, die Wege liegen über ihm."""
    from datetime import timedelta

    gestern = state.heute() - timedelta(days=1)
    state.tagesnotizen.setzen(state.profil.id, gestern, "gestern")
    basis = f"/tag/{gestern.isoformat()}"
    notiz = _notiz(_feld(tagesansicht(page, state, gestern, basis=basis, mit_datum=False)))
    assert notiz.feld.value == "gestern" and notiz.tag == gestern
    assert notiz._anhang_wege()[0][2] == f"{basis}/anhang/aufnehmen/tag/{gestern}/foto"
