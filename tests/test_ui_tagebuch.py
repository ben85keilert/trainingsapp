"""Der Reiter „Tagebuch“ im Verlauf (Ben, 18.10.2026) — `ui/views/tagebuch.py`.

Alle Notizen (zum Tag, zum Plan, zur Übung) nach Tagen mit mitlaufender Wochenleiste oder
nach Übungen; antippen bearbeitet.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Plan  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.components.notizeditor import Textnotiz  # noqa: E402
from trainingsapp.ui.components.tagesnotiz import Tagesnotiz  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.tagebuch import NEU, NOTIZEN, TAGE, UEBUNGEN, tagebuch  # noqa: E402


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
    return SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        aufgaben=aufgaben,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        run_task=lambda f, *a: aufgaben.append(f),
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "actions"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _welt(state: AppState):
    """Gestern ein Plan mit Notiz und eine Übung mit Notiz, heute die Notiz zum Tag."""
    plan = Plan(name="Kräftigung kurz", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    gestern = state.heute() - timedelta(days=1)
    um = datetime.combine(gestern, time(18)).astimezone()
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, gestern)
    kniebeuge = state.uebungen.laden(seed_id("kniebeuge"))
    state.sitzungen.eintrag_anlegen(
        session, kniebeuge, {"reps": [15]}, "links enger", started_at=um
    )
    state.sitzungen.notiz_setzen(session.id, "zäh heute")
    tagebuch_tag = state.notiz_tags.sicherstellen(state.profil.id)
    state.tagesnotizen.anlegen(state.profil.id, state.heute(), "Schulter fest", [tagebuch_tag.id])
    return plan, gestern, kniebeuge


def test_nach_tagen_neueste_oben_mit_wochenleiste(page, state) -> None:
    _plan, gestern, _ = _welt(state)
    ansicht = tagebuch(page, state)
    texte = _texte(ansicht)
    heute_kopf = next(t for t in texte if t.startswith("Heute · "))
    gestern_kopf = next(t for t in texte if t.startswith("Gestern · "))
    assert texte.index(heute_kopf) < texte.index(gestern_kopf)  # neuester Tag oben
    assert "Schulter fest" in texte and "Zum Tag" in texte
    # Gestern: Plan und Übung nach der Uhr (beide 18:00 — der Plan zuerst)
    assert texte.index("zäh heute") < texte.index("links enger") and "18:00" in texte
    assert "Plan „Kräftigung kurz“" in texte and "Kniebeuge" in texte
    # Die Wochenleiste zeigt Punkte für Tage mit Notizen (gestern zwei)
    zellen = [x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.tooltip]
    if gestern.isocalendar()[:2] == state.heute().isocalendar()[:2]:
        assert "2 Notizen" in [z.tooltip for z in zellen]
    assert "1 Notiz" in [z.tooltip for z in zellen]


def test_scrollen_nimmt_die_woche_mit(page, state) -> None:
    """Steht ein älterer Tag oben, zeigt die Leiste seine Woche (Höhen gemeldet)."""
    _welt(state)
    vor_zwei_wochen = state.heute() - timedelta(days=15)
    state.tagesnotizen.anlegen(state.profil.id, vor_zwei_wochen, "lange her")
    ansicht = tagebuch(page, state)
    liste = next(x for x in _alle(ansicht) if isinstance(x, ft.Column) and x.on_scroll)
    bloecke = [x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.on_size_change]
    assert len(bloecke) == 3
    for b in bloecke:
        b.on_size_change(SimpleNamespace(height=120, width=400))
    liste.on_scroll(SimpleNamespace(pixels=2 * (120 + 14) + 10))  # der dritte Tag oben
    assert state.scroll_offsets["tagebuch-tage"] == 2 * (120 + 14) + 10
    from trainingsapp.core.verlauf import wochen_titel

    beginn = vor_zwei_wochen - timedelta(days=vor_zwei_wochen.weekday())
    assert wochen_titel(beginn) in _texte(ansicht)


def test_nach_uebungen_und_antippen_bearbeitet_in_der_liste(page, state) -> None:
    """Ben, 2.11.2026 (P101, P103): kein Popup — die Notiz zum Tag und die zum Plan öffnen
    sich als Editor an Ort und Stelle; die einer Übung in ihren Leistungen des Tages."""
    _plan, _gestern, _ = _welt(state)
    state.tagebuch_ordnung = UEBUNGEN
    ansicht = tagebuch(page, state)
    texte = _texte(ansicht)
    assert "Kniebeuge" in texte and "Zum Tag" in texte
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.on_size_change]
    karte = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and "links enger" in _texte(x)
    )
    karte.on_click()  # die Leistungen des Tages als Blatt
    assert isinstance(page.dialoge[-1], ft.BottomSheet)
    tag_karte = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and "Schulter fest" in _texte(x)
    )
    assert "Tagebuch" in _texte(tag_karte)  # das Etikett des festen Tags
    tag_karte.on_click()
    assert len(page.dialoge) == 1  # kein Dialog dazu
    (notiz,) = state.tagesnotizen.zum_tag(state.profil.id, state.heute())
    assert state.tagebuch_bearbeitet == f"tag:{notiz.id}"
    ansicht = tagebuch(page, state)  # die Ansicht neu — mit dem Editor statt der Karte
    (feld,) = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.multiline]
    assert feld.value == "Schulter fest" and feld.autofocus
    editor = feld.on_change.__self__
    assert isinstance(editor, Tagesnotiz)
    assert [c.label.value for c in editor.chips.values()] == ["Tagebuch"]
    feld.value = "Schulter frei"
    feld.on_change(SimpleNamespace(control=feld))
    asyncio.run(editor.fertig())
    assert state.tagesnotizen.laden(notiz.id).text == "Schulter frei"
    assert state.tagebuch_bearbeitet is None and state.tagebuch_editor is None
    # Die Notiz zum Plan ebenso — ein Texteditor ohne Tags
    ansicht = tagebuch(page, state)
    plan_karte = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and "zäh heute" in _texte(x)
    )
    plan_karte.on_click()
    assert state.tagebuch_bearbeitet.startswith("plan:")
    ansicht = tagebuch(page, state)
    (feld,) = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.multiline]
    assert feld.value == "zäh heute"
    editor = feld.on_change.__self__
    assert isinstance(editor, Textnotiz)
    feld.value = "zäh, aber gut"
    feld.on_change(SimpleNamespace(control=feld))
    asyncio.run(editor.fertig())
    session_notizen = {s.note for s, _ in state.sitzungen.session_notizen(state.profil.id)}
    assert "zäh, aber gut" in session_notizen and len(page.dialoge) == 1


def test_leer_und_neue_notiz_zum_tag(page, state) -> None:
    """„+“ im Kopf (und im leeren Tagebuch): eine neue Notiz zu heute oben in der Liste —
    als Editor, kein Dialog."""
    ansicht = tagebuch(page, state)
    assert any(t.startswith("Keine Notizen") for t in _texte(ansicht))
    knopf = next(
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.icon == ft.Icons.ADD
    )
    knopf.on_click()
    assert state.tagebuch_bearbeitet == NEU
    ansicht = tagebuch(page, state)
    assert any(t.startswith("Neue Notiz · Heute") for t in _texte(ansicht))
    (feld,) = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.multiline]
    editor = feld.on_change.__self__
    feld.value = "erster Eintrag"
    feld.on_change(SimpleNamespace(control=feld))
    asyncio.run(editor.fertig())
    assert [n.text for n in state.tagesnotizen.zum_tag(state.profil.id, state.heute())] == [
        "erster Eintrag"
    ]
    assert page.dialoge == [] and state.tagebuch_bearbeitet is None
    assert "erster Eintrag" in _texte(tagebuch(page, state))


def test_notizen_abschnitt_mit_filter_suche_und_wochenleiste(page, state) -> None:
    """Ben, 2.11.2026 (Punkt 4): ein dritter Abschnitt nur für die Notizen zum Tag, filterbar
    nach Tags (ODER, „ohne Tag“), durchsuchbar, fortlaufend wie „Tage“ und mit derselben
    ein-/ausblendbaren Wochenleiste; gekürzt auf die Zeilen von Heute (Punkt 3)."""
    _plan, gestern, _ = _welt(state)
    kraft = state.notiz_tags.anlegen(state.profil.id, "Kraft")
    state.tagesnotizen.anlegen(state.profil.id, gestern, "Kniebeuge schwer", [kraft.id])
    state.tagesnotizen.anlegen(state.profil.id, gestern, "ohne Etikett")
    state.tagebuch_ordnung = NOTIZEN
    ansicht = tagebuch(page, state)
    texte = _texte(ansicht)
    assert {"Schulter fest", "Kniebeuge schwer", "ohne Etikett"} <= set(texte)
    assert "zäh heute" not in texte and "links enger" not in texte  # nur Notizen zum Tag
    kalender = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.CALENDAR_VIEW_WEEK
    )
    assert kalender.visible
    zellen = [x for x in _alle(ansicht) if isinstance(x, ft.Container) and x.tooltip]
    assert "1 Notiz" in [z.tooltip for z in zellen]  # die Wochenleiste
    # Gekürzt wie das Feld unter Heute
    from trainingsapp.core.tagebuch import NOTIZ_ZEILEN

    karte = next(x for x in _alle(ansicht) if isinstance(x, ft.Text) and x.value == "Schulter fest")
    assert karte.max_lines == NOTIZ_ZEILEN
    # Filter: Chip „Kraft“ (ODER mit „ohne Tag“)
    chips = {c.label.value: c for c in _alle(ansicht) if isinstance(c, ft.Chip)}
    assert set(chips) == {"Tagebuch", "Kraft", "ohne Tag"}
    chips["Kraft"].on_select(None)
    assert state.tagebuch_tags == {kraft.id}
    texte = _texte(tagebuch(page, state))
    assert "Kniebeuge schwer" in texte and "Schulter fest" not in texte
    chips = {c.label.value: c for c in _alle(tagebuch(page, state)) if isinstance(c, ft.Chip)}
    chips["ohne Tag"].on_select(None)
    texte = _texte(tagebuch(page, state))
    assert "Kniebeuge schwer" in texte and "ohne Etikett" in texte and "Schulter fest" not in texte
    state.tagebuch_tags.clear()
    # Suche: jedes Wort muss vorkommen — im Text oder im Tag
    suche = next(x for x in _alle(tagebuch(page, state)) if isinstance(x, ft.TextField))
    suche.value = "kraft SCHWER"
    suche.on_submit(SimpleNamespace(control=suche))
    assert state.tagebuch_suche == "kraft SCHWER"
    texte = _texte(tagebuch(page, state))
    assert "Kniebeuge schwer" in texte and "Schulter fest" not in texte
    suche = next(x for x in _alle(tagebuch(page, state)) if isinstance(x, ft.TextField))
    suche.value = "Gemüse"
    suche.on_submit(SimpleNamespace(control=suche))
    assert any(
        t.startswith("Keine Notizen zu diesem Filter") for t in _texte(tagebuch(page, state))
    )
    state.tagebuch_suche = ""
    state.tagebuch_ordnung = TAGE


def test_der_verlauf_hat_vier_reiter(page, state) -> None:
    """Seit den Tagesfeldern (21.10.2026) steht „Zum Tag“ vor dem Tagebuch."""
    from trainingsapp.ui.views.verlauf import TAGEBUCH, verlauf

    state.verlauf_tab = TAGEBUCH
    reiter = verlauf(page, state)
    leiste = next(x for x in _alle(reiter) if isinstance(x, ft.TabBar))
    assert [t.label for t in leiste.tabs] == ["Tage", "Übungen", "Zum Tag", "Tagebuch"]


def test_andere_notiz_antippen_scrollen_und_neubau_beim_schreiben(page, state) -> None:
    """N98: Eine andere Notiz antippen beendet den offenen Editor, sein spätes „Fertig“
    schließt die neue nicht. N99: Scrollen der Liste meldet sich dem Schreibenden. N100: Der
    Editor überlebt den Neubau — und trägt seine Haken wieder ein, die der Routenaufbau leert."""
    _welt(state)
    state.tagesnotizen.anlegen(state.profil.id, state.heute(), "Knie gut")
    state.tagebuch_ordnung = NOTIZEN

    def karte(ansicht, text):
        return next(
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.Container) and x.on_click and text in _texte(x)
        )

    def editor_in(ansicht):
        (feld,) = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.multiline]
        return feld.on_change.__self__

    karte(tagebuch(page, state), "Schulter fest").on_click()
    ansicht = tagebuch(page, state)
    a = editor_in(ansicht)
    a.feld.on_focus(None)
    a.feld.value = "Schulter frei"
    a.feld.on_change(SimpleNamespace(control=a.feld))
    # N100: der Routenaufbau leert die Haken, der Neubau der Ansicht trägt sie wieder ein
    state.vor_dem_verlassen.clear()
    state.schreiben_beenden = None
    ansicht = tagebuch(page, state)
    assert editor_in(ansicht) is a
    assert state.vor_dem_verlassen[a.sichern_schluessel] == a.speichern
    assert state.schreiben_beenden == a.fertig
    # N99: Scrollen daneben — die Nachfrist läuft ins Leere
    liste = next(x for x in _alle(ansicht) if isinstance(x, ft.Column) and x.on_scroll)
    a.feld.on_tap_outside(None)
    liste.on_scroll(SimpleNamespace(pixels=40.0, event_type=ft.ScrollType.UPDATE))
    assert a._daneben_um is None and a.schreibt
    liste.on_scroll(SimpleNamespace(pixels=40.0))  # ohne Ereignisart (andere Tests): nichts
    # N98: die andere Notiz antippen
    karte(ansicht, "Knie gut").on_click()
    assert not a.schreibt
    assert "Schulter frei" in [
        n.text for n in state.tagesnotizen.zum_tag(state.profil.id, state.heute())
    ]
    offen = state.tagebuch_bearbeitet
    b = editor_in(tagebuch(page, state))
    assert b is not a and b.feld.value == "Knie gut"
    asyncio.run(a.fertig())  # A's Nachfrist bzw. spätes „Fertig“
    assert state.tagebuch_bearbeitet == offen and state.tagebuch_editor[1] is b
    asyncio.run(b.fertig())
    assert state.tagebuch_bearbeitet is None


def test_notiz_nur_mit_aufnahme_bleibt_beim_filtern(page, state) -> None:
    """N90: Eine Notiz zum Tag ohne Text, nur mit Audio, steht im Abschnitt „Notizen“ auch
    beim Filter auf ihren Tag und bei „ohne Tag“ (dort eine ohne Tag)."""
    from trainingsapp.core.anhaenge import AUDIO, Qualitaet, Ziel, neuer_anhang
    from trainingsapp.core.tagebuch import OHNE_TAG

    heute = state.heute()
    etikett = state.notiz_tags.sicherstellen(state.profil.id)

    def mit_audio(tag_ids):
        notiz = state.tagesnotizen.anlegen(state.profil.id, heute, "", tag_ids)
        ziel = Ziel.fuer_notiz(state.profil.id, heute, notiz.id)
        anhang = neuer_anhang(ziel, AUDIO, Qualitaet.MITTEL)
        state.anhaenge.anlegen(anhang, b"\x00\x00\x00\x1cftypM4A " + b"0" * 400)

    mit_audio([etikett.id])
    state.tagebuch_ordnung = NOTIZEN
    assert "1 Audioaufnahme" in _texte(tagebuch(page, state))
    state.tagebuch_tags = {etikett.id}
    assert "1 Audioaufnahme" in _texte(tagebuch(page, state))
    state.tagebuch_tags = {OHNE_TAG}
    assert "1 Audioaufnahme" not in _texte(tagebuch(page, state))
    mit_audio([])
    assert "1 Audioaufnahme" in _texte(tagebuch(page, state))
