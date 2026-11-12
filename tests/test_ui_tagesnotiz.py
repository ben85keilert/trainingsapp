"""Die Notizen zum Tag direkt schreiben (Ben, 22.10.2026; mehrere je Tag mit Tags seit
2.11.2026) — `components/tagesnotiz.py` und `components/notizeditor.py` in der Tagesansicht:
Karten und ein Editor statt Dialog, „+ Notiz“, Tag-Chips, Autosave, ↶ ↷, Abbrechen, Fertig,
Zurück speichert, und Foto · Video · Audio an der Notiz."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.anhaenge import AUDIO, Qualitaet, Ziel, neuer_anhang  # noqa: E402
from trainingsapp.ui.components import notizeditor as ne  # noqa: E402
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
        x for x in _alle(wurzel) if isinstance(x, ft.TextField) and x.hint_text == ne.HINWEIS
    ]
    return feld


def _felder(wurzel) -> list[ft.TextField]:
    return [x for x in _alle(wurzel) if isinstance(x, ft.TextField) and x.hint_text == ne.HINWEIS]


def _notiz(feld: ft.TextField) -> tn.Tagesnotiz:
    """Das Objekt hinter dem Feld (die Handler sind seine Methoden)."""
    notiz = feld.on_change.__self__
    assert isinstance(notiz, tn.Tagesnotiz)
    return notiz


def _karte(wurzel, text: str) -> ft.Container:
    """Die Karte einer fertigen Notiz mit diesem Text — Antippen öffnet sie."""
    return next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.Container) and x.ink and x.on_click and text in _texte(x)
    )


def _oeffnen(wurzel, text: str) -> tn.Tagesnotiz:
    """Die Karte antippen: Die Ansicht baut sich neu, der Editor steht da."""
    _karte(wurzel, text).on_click()
    return _notiz(_feld(wurzel))


def _tippen(notiz: tn.Tagesnotiz, text: str) -> None:
    notiz.feld.value = text
    notiz.feld.on_change(SimpleNamespace(control=notiz.feld))


def _symbole(c) -> list:
    return [x.icon for x in _alle(c) if isinstance(x, ft.IconButton)]


def _knopf(c, text: str) -> ft.TextButton:
    return next(x for x in _alle(c) if isinstance(x, ft.TextButton) and x.content == text)


def _gespeichert(state: AppState) -> list[str]:
    return [n.text for n in state.tagesnotizen.zum_tag(state.profil.id, state.heute())]


async def test_karte_und_editor_statt_dialog_mit_autosave(page, state, monkeypatch) -> None:
    """Kein Dialog: Eine gespeicherte Notiz steht als Karte im Block, Antippen öffnet den
    Editor; gespeichert wird nach einer Pause."""
    monkeypatch.setattr(ne, "SPEICHERN_NACH_S", 0.0)
    state.tagesnotizen.anlegen(state.profil.id, state.heute(), "Schulter fest")
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    assert "Schulter fest" in _texte(ansicht) and _felder(ansicht) == []
    assert _knopf(ansicht, "Notiz").icon == ft.Icons.ADD  # „+ Notiz“
    notiz = _oeffnen(ansicht, "Schulter fest")
    feld = notiz.feld
    assert feld.value == "Schulter fest" and feld.multiline and feld.autofocus
    # Ohne Schreiben: Foto · Video · Audio zur Notiz statt ↶ ↷
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
    assert _gespeichert(state) == ["Schulter fest, Knie gut"]
    assert notiz.stand.value == "gespeichert"
    assert page.dialoge == []  # kein Popup
    # Fertig: wieder die Karte, kein Feld mehr
    await notiz.fertig()
    assert "Schulter fest, Knie gut" in _texte(ansicht) and _felder(ansicht) == []


async def test_mehrere_notizen_mit_plus_und_tags(page, state, monkeypatch) -> None:
    """Ben, 2.11.2026: „mehrere erstellbar mit einem ‚+‘“, mit Tags (Merkmalen): „Tagebuch“
    ist fest, eigene legt man in der Chip-Zeile an; eine neue Notiz hat keinen Tag vorgewählt
    (P98); ein Tipp auf einen Chip speichert sofort; leer bleibt keine Notiz (P99)."""
    monkeypatch.setattr(ne, "SPEICHERN_NACH_S", 0.0)
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    erste = _notiz(_feld(ansicht))  # ohne Notiz: gleich zum Schreiben
    assert not erste.vorhanden and erste.notiz.tag_ids == ()
    (tagebuch_chip,) = [c for c in _alle(erste.tag_zeile) if isinstance(c, ft.Chip) and c.on_select]
    assert tagebuch_chip.label.value == "Tagebuch" and not tagebuch_chip.selected
    plus_tag = next(c for c in _alle(erste.tag_zeile) if isinstance(c, ft.Chip) and c.on_click)
    assert plus_tag.label.value == "+ Tag" and not erste.tag_feld.visible
    # Ein Chip ohne Text legt noch nichts an — erst der Text
    tagebuch = state.notiz_tags.sicherstellen(state.profil.id)
    tagebuch_chip.on_select(None)
    assert erste.notiz.tag_ids == (tagebuch.id,) and tagebuch_chip.selected
    assert _gespeichert(state) == []
    erste.feld.on_focus(None)
    _tippen(erste, "Morgens müde")
    await erste._spaeter_speichern()
    assert _gespeichert(state) == ["Morgens müde"]
    (gespeichert,) = state.tagesnotizen.zum_tag(state.profil.id, state.heute())
    assert gespeichert.tag_ids == (tagebuch.id,)
    # Neuen Tag anlegen — in der Zeile, kein Dialog
    plus_tag.on_click(None)
    assert erste.tag_feld.visible
    erste.tag_feld.value = "Kraft"
    erste.tag_feld.on_submit(None)
    kraft = next(t for t in state.notiz_tags.alle(state.profil.id) if t.name == "Kraft")
    assert state.tagesnotizen.laden(gespeichert.id).tag_ids == (tagebuch.id, kraft.id)
    assert [c.label.value for c in erste.chips.values()] == ["Tagebuch", "Kraft"]
    assert page.dialoge == []
    erste.tag_feld.value = "kraft"
    erste.tag_feld.on_submit(None)
    assert erste.tag_feld.error  # gibt es schon
    await erste.fertig()
    assert _felder(ansicht) == []  # Karte
    assert "Kraft" in _texte(ansicht) and "Tagebuch" in _texte(ansicht)  # die Etiketten
    # „+“: eine zweite Notiz, leer, ohne Tag
    _knopf(ansicht, "Notiz").on_click()
    zweite = _notiz(_feld(ansicht))
    assert zweite is not erste and not zweite.vorhanden and zweite.feld.autofocus
    assert zweite.notiz.tag_ids == ()
    zweite.feld.on_focus(None)
    _tippen(zweite, "Kniebeuge schwer")
    await zweite._spaeter_speichern()
    assert _gespeichert(state) == ["Morgens müde", "Kniebeuge schwer"]
    # Leer gemacht: weg
    _tippen(zweite, "")
    await zweite._spaeter_speichern()
    assert _gespeichert(state) == ["Morgens müde"] and not zweite.vorhanden
    await zweite.fertig()
    assert "Kniebeuge schwer" not in _texte(ansicht)
    # „+“ und gleich Fertig: nichts bleibt
    _knopf(ansicht, "Notiz").on_click()
    dritte = _notiz(_feld(ansicht))
    await dritte.fertig()
    assert _gespeichert(state) == ["Morgens müde"] and _felder(ansicht) == []


async def test_rueckgaengig_holt_ein_geloeschtes_stueck_zurueck(page, state) -> None:
    """„… falls man aus Versehen was löscht“: ↶ holt das Stück in einem Schritt zurück und
    speichert; ↷ nimmt es wieder weg."""
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    notiz = _notiz(_feld(ansicht))
    notiz.feld.on_focus(None)
    _tippen(notiz, "Schulter fest, Knie gut")
    _tippen(notiz, "Schulter fest")  # markiert und gelöscht
    notiz.feld.on_blur(None)
    assert _gespeichert(state) == ["Schulter fest"]
    assert not notiz.zurueck_knopf.disabled and notiz.vor_knopf.disabled
    await notiz.rueckgaengig()
    assert notiz.feld.value == "Schulter fest, Knie gut" and _gespeichert(state) == [
        "Schulter fest, Knie gut"
    ]
    await notiz.wiederholen()
    assert notiz.feld.value == "Schulter fest" and _gespeichert(state) == ["Schulter fest"]


async def test_abbrechen_stellt_den_anfang_her_mit_rueckgaengig(page, state) -> None:
    state.tagesnotizen.anlegen(state.profil.id, state.heute(), "alt")
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    notiz = _oeffnen(ansicht, "alt")
    notiz.feld.on_focus(None)
    _tippen(notiz, "ganz neu")
    notiz.feld.on_blur(None)
    assert _gespeichert(state) == ["ganz neu"]
    await notiz.abbrechen()
    assert notiz.feld.value == "alt" and _gespeichert(state) == ["alt"]
    assert not notiz.schreibt and "alt" in _texte(ansicht) and _felder(ansicht) == []
    (meldung,) = page.dialoge
    assert isinstance(meldung, ft.SnackBar) and meldung.action == "Rückgängig"
    meldung.on_action()  # war ein Versehen
    assert _gespeichert(state) == ["ganz neu"] and "ganz neu" in _texte(ansicht)


async def test_fertig_und_zurueck_auf_heute_beenden_das_schreiben(page, state) -> None:
    """Zurück macht Autosave: Beim Schreiben meldet sich die Notiz zum Speichern vor dem
    Verlassen an; Zurück auf „Heute“ beendet das Schreiben wie „Fertig“."""
    notiz = _notiz(_feld(tagesansicht(page, state, state.heute(), mit_datum=False)))
    notiz.feld.on_focus(None)
    assert state.schreiben_beenden == notiz.fertig
    _tippen(notiz, "vor dem Wegwischen")
    state.vor_dem_verlassen[notiz.sichern_schluessel]()  # App geht in den Hintergrund
    assert _gespeichert(state) == ["vor dem Wegwischen"]
    assert state.schreiben_beenden is not None
    await state.schreiben_beenden()
    assert not notiz.schreibt and state.schreiben_beenden is None
    assert notiz.sichern_schluessel not in state.vor_dem_verlassen
    # Der Verlauf bleibt: wieder hineintippen, ↶ geht noch
    notiz.feld.on_focus(None)
    assert notiz.verlauf.kann_rueckgaengig


def test_feld_ueber_die_ganze_breite(page, state) -> None:
    """„Setze das Feld auf die ganze Breite“: Ohne ``expand`` oder ``width`` gäbe Flet dem
    Textfeld feste 300 px — die Spalte streckt es."""
    notiz = _notiz(_feld(tagesansicht(page, state, state.heute(), mit_datum=False)))
    spalte = notiz.control()
    assert notiz.feld in spalte.controls and spalte.controls[0] is notiz.tag_zeile
    assert spalte.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
    assert notiz.feld.width is None and not notiz.feld.expand


async def test_fertig_und_abbrechen_nehmen_dem_feld_den_fokus(page, state) -> None:
    """„Der Fertig-Button macht nicht fertig“ (v0.3.15): Der Fokus ging an den Knopf, der mit
    seiner Leiste verschwand — Flutter gab ihn dem Feld zurück, die Tastatur ging wieder auf.
    Jetzt nimmt ``blur`` dem Feld den Fokus, jedes Mal mit einem neuen Wert."""
    notiz = _notiz(_feld(tagesansicht(page, state, state.heute(), mit_datum=False)))
    assert isinstance(notiz.feld, ne.Notizfeld) and notiz.feld.blur is None
    assert notiz.feld._c == "TextField"  # Flet zeichnet ein gewöhnliches Textfeld
    notiz.feld.on_focus(None)
    _tippen(notiz, "fertig geschrieben")
    await notiz.fertig()
    erster = notiz.feld.blur
    assert erster and not notiz.schreibt and notiz.anhang_leiste.visible
    assert _gespeichert(state) == ["fertig geschrieben"]
    notiz.feld.on_focus(None)
    _tippen(notiz, "doch nicht")
    await notiz.abbrechen()
    assert notiz.feld.blur not in (None, erster)
    assert notiz.feld.value == "fertig geschrieben" and _gespeichert(state) == [
        "fertig geschrieben"
    ]


async def test_daneben_tippen_beendet_das_schreiben(page, state, monkeypatch) -> None:
    """„Der Klick aus dem Fenster raus soll … speichern“: Ein Tipp neben das Feld beendet das
    Schreiben wie „Fertig“ — nach der Nachfrist, denn auch ↶, ↷ und die Chips liegen daneben,
    und Flutter meldet den Tipp schon beim Aufsetzen, ihren Klick erst beim Loslassen."""
    monkeypatch.setattr(ne, "NACHFRIST_S", 0.0)
    notiz = _notiz(_feld(tagesansicht(page, state, state.heute(), mit_datum=False)))
    notiz.feld.on_focus(None)
    _tippen(notiz, "Knie gut, Schulter fest")
    _tippen(notiz, "Knie gut")  # ein Stück gelöscht
    notiz.feld.on_tap_outside(None)  # der Finger setzt auf ↶ auf …
    zeit = notiz._daneben_um
    await notiz.rueckgaengig()  # … und hebt ab
    await notiz._nach_daneben(zeit)
    assert notiz.schreibt and notiz.feld.value == "Knie gut, Schulter fest"
    notiz.feld.on_tap_outside(None)  # auf einen Chip
    zeit = notiz._daneben_um
    (chip,) = [c for c in _alle(notiz.tag_zeile) if isinstance(c, ft.Chip) and c.on_select]
    chip.on_select(None)
    await notiz._nach_daneben(zeit)
    assert notiz.schreibt
    notiz.feld.on_tap_outside(None)  # irgendwo sonst
    await notiz._nach_daneben(notiz._daneben_um)
    assert not notiz.schreibt and notiz.anhang_leiste.visible and notiz.feld.blur
    assert _gespeichert(state) == ["Knie gut, Schulter fest"]
    assert notiz.sichern_schluessel not in state.vor_dem_verlassen
    assert state.schreiben_beenden is None
    page.aufgaben.clear()
    notiz.feld.on_tap_outside(None)  # ohne Schreiben: nichts
    assert page.aufgaben == []


async def test_scrollen_daneben_laesst_die_tastatur_offen(page, state) -> None:
    """Ben, 2.11.2026: „Wenn man außerhalb davon klickt und scrollt, verliert sich der Fokus.
    Bei Kurzklick ist der Fokusverlust erwünscht. Bei gedrückt halten nicht.“ — Zieht der
    Finger nach dem Aufsetzen (die Fläche scrollt), bleibt das Schreiben; hebt er ab, ohne zu
    ziehen (Gestenfänger der Tagesansicht), ist sofort fertig — ohne Nachfrist."""
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    assert isinstance(ansicht, ft.GestureDetector) and ansicht.on_tap_up
    notiz = _notiz(_feld(ansicht))
    assert state.schreib_gesten is None
    notiz.feld.on_focus(None)
    assert state.schreib_gesten == notiz.geste
    _tippen(notiz, "Knie gut")
    notiz.feld.on_tap_outside(None)  # der Finger setzt daneben auf …
    zeit = notiz._daneben_um
    state.schreib_gesten("scroll")  # … und zieht: die Ansicht scrollt
    await notiz._nach_daneben(zeit)  # die Nachfrist läuft ins Leere
    assert notiz.schreibt and notiz._daneben_um is None and not notiz.feld.blur
    page.aufgaben.clear()
    ansicht.on_tap_up(None)  # abheben ohne vorheriges Aufsetzen daneben: nichts
    assert page.aufgaben == [] and notiz.schreibt
    notiz.feld.on_tap_outside(None)  # aufsetzen (die Nachfrist beginnt) …
    ansicht.on_tap_up(None)  # … und gleich abheben: der kurze Tipp ins Leere
    assert page.aufgaben == [notiz._nach_daneben, notiz.fertig]
    await notiz.fertig()
    assert not notiz.schreibt and notiz.feld.blur and state.schreib_gesten is None
    ansicht.on_tap_up(None)  # ohne Schreiben: nichts
    assert state.schreib_gesten is None


def test_scroll_helfer_meldet_das_ziehen(page, state) -> None:
    """`components/scroll.py` sagt dem Schreibenden, dass gescrollt wird — bei Start und
    Fortgang, nicht beim Ende; ohne Schreibenden nichts (auch ohne Ereignisart, wie die
    Navigationstests scrollen)."""
    from trainingsapp.ui.components.scroll import scroll_merken

    gesten: list[str] = []
    spalte = scroll_merken(page, state, "heute", ft.Column(scroll=ft.ScrollMode.AUTO))
    spalte.on_scroll(SimpleNamespace(pixels=5.0))
    state.schreib_gesten = gesten.append
    spalte.on_scroll(SimpleNamespace(pixels=5.0))
    spalte.on_scroll(SimpleNamespace(pixels=20.0, event_type=ft.ScrollType.START))
    spalte.on_scroll(SimpleNamespace(pixels=40.0, event_type=ft.ScrollType.UPDATE))
    spalte.on_scroll(SimpleNamespace(pixels=40.0, event_type=ft.ScrollType.END))
    assert gesten == ["scroll", "scroll"] and state.scroll_offsets["heute"] == 40.0


async def test_platz_beim_schreiben(page, state) -> None:
    """Ben, 2.11.2026: „Klickt man wieder in das Feld, wird das Texteingabefeld überdeckt“ —
    unter der Schreibmarke bleibt Platz für die Leiste, und der runde Knopf der Ansicht
    verschwindet, solange man schreibt."""
    knopf = ft.FloatingActionButton(icon=ft.Icons.ADD)
    page.views.append(SimpleNamespace(floating_action_button=knopf))
    notiz = _notiz(_feld(tagesansicht(page, state, state.heute(), mit_datum=False)))
    assert notiz.feld.scroll_padding.bottom == ne.SICHT_UNTER_FELD_PX >= 48
    notiz.feld.on_focus(None)
    assert knopf.visible is False
    await notiz.fertig()
    assert knopf.visible is True


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


def test_zeitleiste_feld_am_ende_oder_karten_an_der_uhrzeit(page, state) -> None:
    state.tag_darstellung = ZEITLEISTE
    ohne = tagesansicht(page, state, state.heute(), mit_datum=False)
    assert _feld(ohne).value == ""  # gleich zum Schreiben, kein „+ Notiz“
    assert "Notiz zum Tag" in _texte(ohne)
    state.tagesnotizen.anlegen(state.profil.id, state.heute(), "Schulter fest")
    state.tagesnotizen.anlegen(state.profil.id, state.heute(), "abends locker")
    mit = tagesansicht(page, state, state.heute(), mit_datum=False)
    texte = _texte(mit)
    # Je eine Karte an ihrer Uhrzeit, dazu „+ Notiz“ am Ende unter derselben Überschrift
    assert _felder(mit) == [] and texte.count("Notiz zum Tag") == 3
    assert texte.index("Schulter fest") < texte.index("abends locker")
    assert _knopf(mit, "Notiz").icon == ft.Icons.ADD  # „+ Notiz“ am Ende
    _oeffnen(mit, "abends locker")  # Karte → Editor an ihrer Stelle, kein „+“
    assert len(_felder(mit)) == 1 and not [
        x for x in _alle(mit) if isinstance(x, ft.TextButton) and x.content == "Notiz"
    ]
    state.tag_darstellung = UEBERSICHT


async def test_foto_video_audio_zur_notiz(page, state) -> None:
    """Die Knöpfe führen zur Aufnahme für die Notiz; ihre Anhänge stehen als Kacheln unter
    der Karte — eine Audioaufnahme mit Klangsymbol. Eine Notiz nur mit Anhang bleibt."""
    heute = state.heute()
    notiz = state.tagesnotizen.anlegen(state.profil.id, heute, "")
    ton = neuer_anhang(Ziel.fuer_notiz(state.profil.id, heute, notiz.id), AUDIO, Qualitaet.MITTEL)
    state.anhaenge.anlegen(ton, M4A)
    ansicht = tagesansicht(page, state, heute, mit_datum=False)
    assert [n.id for n in state.tagesnotizen.zum_tag(state.profil.id, heute)] == [notiz.id]
    assert any(isinstance(x, ft.Icon) and x.icon == ft.Icons.GRAPHIC_EQ for x in _alle(ansicht))
    kachel = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.width == 64 and x.on_click
    )
    await kachel.on_click()
    assert page.routen[-1] == f"/anhang/{ton.id}"
    karte = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.ink and x.on_click and x.width is None
    )
    karte.on_click()
    editor = _notiz(_feld(ansicht))
    assert editor.id == notiz.id and editor.anhaenge == [ton]
    kamera, video, mikro = [x for x in _alle(editor.anhang_leiste) if isinstance(x, ft.IconButton)][
        :3
    ]
    await mikro.on_click()
    await kamera.on_click()
    assert page.routen[-2:] == [
        f"/anhang/aufnehmen/notiz/{notiz.id}/audio",
        f"/anhang/aufnehmen/notiz/{notiz.id}/foto",
    ]
    assert video.tooltip == "Video zur Notiz"


async def test_der_weg_zur_kamera_legt_die_notiz_an(page, state) -> None:
    """Der Anhang braucht die ID der Notiz: Vor dem Weg zur Kamera steht sie in der
    Datenbank — leer; kommt nichts, räumt der nächste Aufbau sie weg."""
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    notiz = _notiz(_feld(ansicht))
    kamera = next(x for x in _alle(notiz.anhang_leiste) if isinstance(x, ft.IconButton))
    await kamera.on_click()
    assert page.routen == [f"/anhang/aufnehmen/notiz/{notiz.id}/foto"]
    (zeile,) = state.tagesnotizen.zum_tag(state.profil.id, state.heute())
    assert zeile.id == notiz.id and zeile.text == ""
    # Heute baut sich unter der Kamera neu — die leere Notiz bleibt (versteckt), sonst fände
    # die Aufnahme sie nicht; weg kommt sie beim Verlassen der Kamera ohne Foto
    neu = tagesansicht(page, state, state.heute(), mit_datum=False)
    assert _notiz(_feld(neu)).id != notiz.id  # ein frischer Editor, keine Karte der leeren
    assert [n.id for n in state.tagesnotizen.zum_tag(state.profil.id, state.heute())] == [notiz.id]
    assert state.tagesnotizen.aufraeumen(notiz.id)
    assert state.tagesnotizen.zum_tag(state.profil.id, state.heute()) == []


def test_tagesansicht_eines_anderen_tags(page, state) -> None:
    """In `/tag/<datum>` gehört die Notiz zu diesem Tag, die Wege liegen über ihm."""
    from datetime import timedelta

    gestern = state.heute() - timedelta(days=1)
    n = state.tagesnotizen.anlegen(state.profil.id, gestern, "gestern")
    basis = f"/tag/{gestern.isoformat()}"
    ansicht = tagesansicht(page, state, gestern, basis=basis, mit_datum=False)
    notiz = _oeffnen(ansicht, "gestern")
    assert notiz.feld.value == "gestern" and notiz.tag == gestern and notiz.id == n.id
    assert notiz._anhang_wege()[0][2] == f"{basis}/anhang/aufnehmen/notiz/{n.id}/foto"


async def test_andere_karte_antippen_beendet_den_offenen_editor(page, state, monkeypatch) -> None:
    """N98: Während Notiz A geschrieben wird, Karte B antippen — A hört auf (gespeichert),
    und weder A's Nachfrist noch ein spätes „Fertig“ von A klappt B wieder zu."""
    monkeypatch.setattr(ne, "NACHFRIST_S", 0.0)
    state.tagesnotizen.anlegen(state.profil.id, state.heute(), "erste")
    state.tagesnotizen.anlegen(state.profil.id, state.heute(), "zweite")
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    a = _oeffnen(ansicht, "erste")
    a.feld.on_focus(None)
    _tippen(a, "erste, länger")
    a.feld.on_tap_outside(None)  # der Finger setzt auf Karte B auf: A's Nachfrist beginnt
    zeit = a._daneben_um
    b = _oeffnen(ansicht, "zweite")
    assert b is not a and not a.schreibt and a._daneben_um is None
    assert a.sichern_schluessel not in state.vor_dem_verlassen
    assert sorted(_gespeichert(state)) == ["erste, länger", "zweite"]
    b.feld.on_focus(None)
    await a._nach_daneben(zeit)  # die Nachfrist läuft ins Leere
    assert _notiz(_feld(ansicht)) is b and b.schreibt
    await a.fertig()  # der kurze Tipp hatte „Fertig“ schon losgeschickt: B bleibt offen
    assert _notiz(_feld(ansicht)) is b and b.schreibt
    assert state.schreiben_beenden == b.fertig
    await b.fertig()
    assert _felder(ansicht) == []


def test_speichern_vor_dem_verlassen_protokolliert_fehler(state, caplog) -> None:
    """N101: Scheitert das Speichern vor dem Neubau, steht es im Protokoll — und die übrigen
    Schreibenden werden trotzdem gespeichert."""
    from trainingsapp.ui.app import schreibende_sichern

    gesichert: list[str] = []

    def kaputt() -> None:
        raise OSError("Platte voll")

    state.vor_dem_verlassen["notiz:a"] = kaputt
    state.vor_dem_verlassen["notiz:b"] = lambda: gesichert.append("b")
    with caplog.at_level("ERROR"):
        schreibende_sichern(state)
    assert gesichert == ["b"]
    assert "notiz:a" in caplog.text and "Platte voll" in caplog.text
