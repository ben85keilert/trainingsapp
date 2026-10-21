"""Tagesfelder in der Oberfläche (Ben, 21.10.2026, `docs/plan_tagesfelder.md`): Block „Zum
Tag“ unter Heute (unter „Gemacht“ am Ende), das Blatt mit Schiebebalken und Uhrzeit-Vorlage,
Einstellungen → Tagesfelder, Verlauf (Tage, Reiter „Zum Tag“, Feldansicht), Tagebuch und
Zeitleiste."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core import tagesfelder as tf  # noqa: E402
from trainingsapp.ui.components.skala_regler import skala_regler  # noqa: E402
from trainingsapp.ui.components.tagesfeld_blatt import tagesfeld_blatt  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    dialoge: list = []
    aufgaben: list = []
    routen: list = []

    async def push_route(r: str) -> None:
        routen.append(r)

    return SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        aufgaben=aufgaben,
        routen=routen,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: aufgaben.append(f),
        push_route=push_route,
        height=800,
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "actions", "appbar", "segments", "label"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    """Ein Knopf mit diesem Text (Text als ``content`` oder direkt) — auch ein antippbarer
    Container (der Schnellknopf unter Heute)."""
    for x in _alle(c):
        inhalt = getattr(x, "content", None)
        if isinstance(x, ft.Container) and x.ink and getattr(inhalt, "value", None) == text:
            return x
        if isinstance(
            x, ft.FilledButton | ft.TextButton | ft.FilledTonalButton | ft.OutlinedButton
        ):
            inhalt = x.content
            wert = inhalt if isinstance(inhalt, str) else getattr(inhalt, "value", None)
            if wert == text:
                return x
    raise AssertionError(f"kein Knopf „{text}“ in {_texte(c)}")


def _ausfuehren(ergebnis) -> None:
    if asyncio.iscoroutine(ergebnis):
        asyncio.run(ergebnis)


def _felder(state: AppState) -> dict[str, tf.Tagesfeld]:
    p = state.profil.id
    ibu = tf.Tagesfeld(
        subject_id=p,
        name="Ibu",
        spec=tf.spec_bauen(tf.ANZAHL, schnell=[1], varianten=["400", "800"]),
        mehrmals=True,
    )
    schmerz = tf.Tagesfeld(
        subject_id=p, name="Schmerz", spec=tf.spec_bauen(tf.SKALA, varianten=["Knie", "Rücken"])
    )
    trinken = tf.Vorschlag(
        "Trinken", tf.MENGE, mehrmals=True, einheit="ml", schnell=(250, 500)
    ).feld(p)
    essen = tf.Vorschlag("Ernährung", tf.TEXT).feld(p)
    for f in (ibu, schmerz, trinken, essen):
        state.tagesfelder.speichern(f)
    return {"ibu": ibu, "schmerz": schmerz, "trinken": trinken, "essen": essen}


def _um(state: AppState, stunde: int, minute: int = 0, tag=None) -> datetime:
    return datetime.combine(tag or state.heute(), time(stunde, minute)).astimezone()


# ---------------------------------------------------------------------------
# Heute
# ---------------------------------------------------------------------------


def test_zum_tag_steht_unter_gemacht_am_ende(page, state) -> None:
    from trainingsapp.ui.views.tag import tagesansicht

    f = _felder(state)
    state.tagesnotizen.setzen(state.profil.id, state.heute(), "Schulter fest")
    state.tageswerte.hinzufuegen(f["ibu"], state.heute(), _um(state, 0, 1), wert=1, variante="400")
    texte = _texte(tagesansicht(page, state, state.heute(), mit_datum=False))
    gemacht = next(i for i, t in enumerate(texte) if t.startswith("GEMACHT"))
    zum_tag = texte.index("Zum Tag")
    assert zum_tag > gemacht
    assert "Schulter fest" in texte[zum_tag:]
    assert texte.index("Ibu") > zum_tag and "400 × 1" in texte
    assert texte.index("Ernährung") > zum_tag
    assert any(t.endswith("1 Tageswert") for t in texte)  # Kopfzeile


def test_ohne_tagesfelder_ein_hinweis(page, state) -> None:
    from trainingsapp.ui.views.tag import tagesansicht

    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    knopf = _knopf(ansicht, "Tagesfelder …")
    _ausfuehren(knopf.on_click())
    assert page.routen == ["/einstellungen/tagesfelder"]


def test_schnellknopf_traegt_ein_mit_rueckgaengig(page, state) -> None:
    from trainingsapp.ui.views.tag import tagesansicht

    f = _felder(state)
    ansicht = tagesansicht(page, state, state.heute(), mit_datum=False)
    _knopf(ansicht, "+250").on_click()
    (w,) = state.tageswerte.am_tag(state.profil.id, state.heute())
    assert (w.feld_id, w.wert) == (f["trinken"].id, 250)
    meldung = page.dialoge[-1]
    assert isinstance(meldung, ft.SnackBar) and meldung.action == "Rückgängig"
    assert meldung.persist is False
    meldung.on_action()
    assert state.tageswerte.am_tag(state.profil.id, state.heute()) == []


def test_schnellknopf_traegt_die_gewaehlte_variante_ein(page, state) -> None:
    from trainingsapp.ui.views.tag import tagesansicht

    f = _felder(state)
    state.tagesfeld_varianten[f["ibu"].id] = "800"
    _knopf(tagesansicht(page, state, state.heute(), mit_datum=False), "+1").on_click()
    (w,) = state.tageswerte.am_tag(state.profil.id, state.heute())
    assert (w.variante, w.wert) == ("800", 1)


def test_zeitleiste_zeigt_werte_nach_der_uhr(page, state) -> None:
    from trainingsapp.ui.views.tag import ZEITLEISTE, tagesansicht

    f = _felder(state)
    state.tag_darstellung = ZEITLEISTE
    state.tageswerte.hinzufuegen(f["ibu"], state.heute(), _um(state, 0, 2), wert=1, variante="400")
    state.tageswerte.einmal_setzen(f["schmerz"], state.heute(), wert=3, variante="Knie")
    for minute in (3, 4, 5):
        state.tageswerte.hinzufuegen(f["trinken"], state.heute(), _um(state, 0, minute), wert=250)
    texte = _texte(tagesansicht(page, state, state.heute(), mit_datum=False))
    assert "Ibu 400" in texte  # ein Punkt an seiner Uhrzeit
    assert "Schmerz Knie 3" in texte  # einmal am Tag: an der Notiz zum Tag
    # drei Mal Trinken hintereinander: eine Zeile
    assert "Trinken 750 ml" in texte and "3× · 00:03–00:05" in texte


# ---------------------------------------------------------------------------
# Blatt
# ---------------------------------------------------------------------------


def test_skala_als_schiebebalken(page, state) -> None:
    f = _felder(state)["schmerz"]
    blatt = tagesfeld_blatt(page, state, f, state.heute())
    (regler,) = [x for x in _alle(blatt) if isinstance(x, ft.Slider)]
    assert (regler.min, regler.max, regler.divisions) == (0, 10, 10)
    regler.value = 3.4
    regler.on_change_end(None)
    (w,) = state.tageswerte.am_tag(state.profil.id, state.heute())
    assert (w.variante, w.wert) == ("Knie", 3)
    # noch einmal: Korrektur statt zweitem Wert
    (regler,) = [x for x in _alle(blatt) if isinstance(x, ft.Slider)]
    regler.value = 5
    regler.on_change_end(None)
    (w2,) = state.tageswerte.am_tag(state.profil.id, state.heute())
    assert w2.wert == 5 and w2.ersetzt == w.id


def test_skala_regler_loescht_mit_x() -> None:
    gemeldet: list = []
    f = tf.spec_bauen(tf.SKALA).fields[0]
    regler = skala_regler(f, 4, gemeldet.append)
    (loeschen,) = [x for x in _alle(regler) if isinstance(x, ft.IconButton)]
    loeschen.on_click(None)
    assert gemeldet == [None]


def test_notiz_speichert_beim_schliessen(page, state) -> None:
    f = _felder(state)["schmerz"]
    danach: list = []
    blatt = tagesfeld_blatt(page, state, f, state.heute(), danach=lambda: danach.append(1))
    (regler,) = [x for x in _alle(blatt) if isinstance(x, ft.Slider)]
    regler.value = 2
    regler.on_change_end(None)
    notiz = next(
        x for x in _alle(blatt) if isinstance(x, ft.TextField) and x.label == "Notiz (optional)"
    )
    notiz.value = "nach dem Laufen"
    asyncio.run(blatt.on_dismiss(None))
    (w,) = state.tageswerte.am_tag(state.profil.id, state.heute())
    assert (w.wert, w.note) == (2, "nach dem Laufen")
    assert danach == [1]


def test_mehrmals_schnellknopf_und_liste(page, state) -> None:
    f = _felder(state)["ibu"]
    blatt = tagesfeld_blatt(page, state, f, state.heute())
    _knopf(blatt, "+1 · 400").on_click(None)
    _knopf(blatt, "+1 · 400").on_click(None)
    werte = state.tageswerte.am_tag(state.profil.id, state.heute())
    assert [w.wert for w in werte] == [1, 1]
    texte = _texte(blatt)
    assert "HEUTE EINGETRAGEN" in texte
    assert "Ibu · heute" in texte


def test_nachtragen_nimmt_die_alte_zeit_als_vorlage(page, state) -> None:
    """Ben: „Zeit festlegen, dabei soll die alte Zeit genommen werden als Vorlage“."""
    f = _felder(state)["ibu"]
    vorgestern = state.heute() - timedelta(days=2)
    gestern = state.heute() - timedelta(days=1)
    state.tageswerte.hinzufuegen(
        f, vorgestern, _um(state, 8, 10, vorgestern), wert=1, variante="400"
    )
    blatt = tagesfeld_blatt(page, state, f, gestern)
    uhr = next(x for x in _alle(blatt) if isinstance(x, ft.TextField) and x.label == "Uhrzeit")
    assert uhr.value == "08:10"  # die Zeit des letzten Werts davor
    _knopf(blatt, "+1 · 400").on_click(None)
    (w,) = state.tageswerte.am_tag(state.profil.id, gestern)
    assert w.zeit.astimezone().strftime("%H:%M") == "08:10"
    # ohne frühere Werte: 12:00 wie beim Nachtragen von Übungen
    leer = tagesfeld_blatt(page, state, _felder_neu(state), gestern)
    uhr = next(x for x in _alle(leer) if isinstance(x, ft.TextField) and x.label == "Uhrzeit")
    assert uhr.value == "12:00"


def _felder_neu(state: AppState) -> tf.Tagesfeld:
    neu = tf.Vorschlag("Meditation", tf.DAUER, mehrmals=True, schnell=(600,)).feld(state.profil.id)
    state.tagesfelder.speichern(neu)
    return neu


def test_eintrag_aendern_mit_alter_uhrzeit(page, state) -> None:
    f = _felder(state)["ibu"]
    gestern = state.heute() - timedelta(days=1)
    w = state.tageswerte.hinzufuegen(
        f, gestern, _um(state, 14, 30, gestern), wert=1, variante="400"
    )
    blatt = tagesfeld_blatt(page, state, f, gestern)
    zeile = next(
        x
        for x in _alle(blatt)
        if isinstance(x, ft.Container) and callable(x.on_click) and x.ink and "14:30" in _texte(x)
    )
    zeile.on_click(None)
    uhr = [x for x in _alle(blatt) if isinstance(x, ft.TextField) and x.label == "Uhrzeit"]
    assert any(u.value == "14:30" for u in uhr)  # die alte Zeit steht vor
    notiz = next(x for x in _alle(blatt) if isinstance(x, ft.TextField) and x.label == "Notiz")
    notiz.value = "nach dem Laufen"
    _knopf(blatt, "Übernehmen").on_click(None)
    (neu,) = state.tageswerte.am_tag(state.profil.id, gestern)
    assert neu.ersetzt == w.id and neu.note == "nach dem Laufen"
    assert neu.zeit.astimezone().strftime("%H:%M") == "14:30"


def test_nur_text_speichert_beim_schliessen(page, state) -> None:
    f = _felder(state)["essen"]
    blatt = tagesfeld_blatt(page, state, f, state.heute())
    feld = next(x for x in _alle(blatt) if isinstance(x, ft.TextField) and x.multiline)
    feld.value = "Mittags Gemüse"
    asyncio.run(blatt.on_dismiss(None))
    (w,) = state.tageswerte.am_tag(state.profil.id, state.heute())
    assert w.note == "Mittags Gemüse"


# ---------------------------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------------------------


def test_liste_aktiv_und_ausgeschaltet(page, state) -> None:
    from trainingsapp.ui.views.tagesfelder import tagesfelder_view

    f = _felder(state)
    state.tagesfelder.schalten(f["essen"].id, False)
    texte = _texte(tagesfelder_view(page, state))
    assert "AKTIV · 3" in texte and "AUSGESCHALTET · 1" in texte
    assert "Anzahl · 400, 800 · mehrmals mit Uhrzeit" in texte


def test_formular_mit_vorschlag_speichert(page, state) -> None:
    from trainingsapp.ui.views.tagesfelder import tagesfeld_formular_view

    ansicht = tagesfeld_formular_view(page, state, None)
    chip = next(x for x in _alle(ansicht) if isinstance(x, ft.Chip) and _texte(x) == ["Medikament"])
    chip.on_click()
    name = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Name")
    name.value = "Ibu"
    name.on_change(SimpleNamespace(control=name))
    variante = next(
        x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Neue Variante"
    )
    variante.value = "400"
    variante.on_submit(None)
    speichern = ansicht.appbar.actions[-2]
    _ausfuehren(speichern.on_click(None))
    (feld,) = state.tagesfelder.alle(state.profil.id)
    assert (feld.name, feld.art, feld.varianten, feld.mehrmals) == ("Ibu", tf.ANZAHL, ["400"], True)


def test_formular_sperrt_die_art_mit_werten(page, state) -> None:
    from trainingsapp.ui.views.tagesfelder import tagesfeld_formular_view

    f = _felder(state)["ibu"]
    state.tageswerte.hinzufuegen(f, state.heute(), wert=1, variante="400")
    texte = _texte(tagesfeld_formular_view(page, state, f.id))
    assert any(t.startswith("Die Art bleibt") for t in texte)


@pytest.mark.parametrize(
    ("weg", "liste", "werte"), [("aus", 1, 1), ("behalten", 0, 1), ("alles", 0, 0)]
)
def test_loeschen_drei_wege(page, state, weg, liste, werte) -> None:
    from trainingsapp.ui.views.tagesfelder import loeschen_dialog

    f = _felder(state)["ibu"]
    state.tageswerte.hinzufuegen(f, state.heute(), wert=1, variante="400")
    dialog = loeschen_dialog(page, state, f, lambda: None)
    (gruppe,) = [x for x in _alle(dialog) if isinstance(x, ft.RadioGroup)]
    gruppe.value = weg
    _knopf(dialog, "Ausführen").on_click(None)
    asyncio.run(dialog.on_dismiss(None))
    aktiv = [x for x in state.tagesfelder.alle(state.profil.id) if x.name == "Ibu"]
    assert len(aktiv) == liste
    if weg == "aus":
        assert not aktiv[0].aktiv
    assert len(state.tageswerte.zwischen(state.profil.id, None, None, [f.id])) == werte
    if weg != "aus":
        meldung = page.dialoge[-1]
        assert meldung.action == "Rückgängig"
        meldung.on_action()
        assert len(state.tageswerte.zwischen(state.profil.id, None, None, [f.id])) == 1


# ---------------------------------------------------------------------------
# Verlauf und Tagebuch
# ---------------------------------------------------------------------------


def test_verlauf_tage_zeigt_zum_tag(page, state) -> None:
    from trainingsapp.ui.views.verlauf import verlauf

    f = _felder(state)
    state.tageswerte.hinzufuegen(f["ibu"], state.heute(), _um(state, 0, 1), wert=1, variante="400")
    state.verlauf_tab = 0
    texte = _texte(verlauf(page, state))
    assert "ZUM TAG" in texte and "Ibu" in texte and "400 × 1" in texte


def test_reiter_zum_tag(page, state) -> None:
    from trainingsapp.ui.views.verlauf import ZUM_TAG, verlauf

    f = _felder(state)
    state.tageswerte.hinzufuegen(f["ibu"], state.heute(), _um(state, 0, 1), wert=1, variante="400")
    state.tagesfelder.loeschen(f["essen"].id, mit_werten=False)
    state.verlauf_tab = ZUM_TAG
    texte = _texte(verlauf(page, state))
    assert "Ibu" in texte and "Schmerz" in texte and "Ernährung" not in texte


@pytest.mark.parametrize("schluessel", ["ibu", "schmerz", "trinken", "essen"])
def test_feldansicht_je_art(page, state, schluessel) -> None:
    from trainingsapp.ui.views.verlauf_tagesfeld import verlauf_tagesfeld_view

    f = _felder(state)
    feld = f[schluessel]
    gestern = state.heute() - timedelta(days=1)
    for tag in (gestern, state.heute()):
        if feld.art == tf.TEXT:
            state.tageswerte.hinzufuegen(feld, tag, _um(state, 0, 1, tag), note="Gemüse")
        elif feld.art == tf.SKALA:
            state.tageswerte.einmal_setzen(
                feld, tag, wert=3, variante="Knie", zeit=_um(state, 0, 1, tag)
            )
            state.tageswerte.einmal_setzen(
                feld, tag, wert=2, variante="Rücken", zeit=_um(state, 0, 1, tag)
            )
        else:
            v = feld.varianten[0] if feld.varianten else ""
            state.tageswerte.hinzufuegen(
                feld, tag, _um(state, 0, 1, tag), wert=feld.schnell[0], variante=v
            )
    ansicht = verlauf_tagesfeld_view(page, state, feld.id)
    texte = _texte(ansicht)
    assert "EINTRÄGE · NEUESTE ZUERST" in texte and "Tage mit Eintrag" in texte
    if schluessel == "ibu":
        assert "2 Stück" in texte


def test_tagebuch_mit_werten_und_texten(page, state) -> None:
    from trainingsapp.ui.views.tagebuch import UEBUNGEN, tagebuch

    f = _felder(state)
    state.tageswerte.hinzufuegen(
        f["ibu"], state.heute(), _um(state, 0, 1), wert=1, variante="400", note="nach dem Laufen"
    )
    state.tageswerte.einmal_setzen(f["essen"], state.heute(), note="Mittags Gemüse")
    texte = _texte(tagebuch(page, state))
    assert "Ibu 400 × 1" in texte  # die Wertezeile an der Notiz zum Tag
    assert "nach dem Laufen" in texte and "Mittags Gemüse" in texte
    state.tagebuch_ordnung = UEBUNGEN
    texte = _texte(tagebuch(page, state))
    assert "Ernährung" in texte and "Ibu" in texte
    assert "Übungen und Felder" in texte
