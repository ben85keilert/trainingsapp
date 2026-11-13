"""Der Reiter „Notizen“ im Verlauf (Ben, 18.10.2026 als „Tagebuch“) — `ui/views/tagebuch.py`.

Alles Geschriebene (zum Tag, zum Plan, zur Übung) nach Tagen mit mitlaufender Wochenleiste;
Suche, Filterblatt und die Schnellwahl „Tagebuch“ (Ben, 12.11.2026,
`docs/plan_notizen_reiter.md`); antippen bearbeitet.
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
from trainingsapp.ui.views.tagebuch import (  # noqa: E402
    ART,
    B_PLAN,
    B_UEBUNG,
    NEU,
    TAGS,
    ZEITRAUM,
    tagebuch,
)


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


def _chips(c) -> dict[str, ft.Chip]:
    """Die Chips der Schnellwahl (die Labels der Filter haben ein ✕)."""
    return {x.label.value: x for x in _alle(c) if isinstance(x, ft.Chip) and not x.on_delete}


def _blatt(page, ansicht) -> ft.BottomSheet:
    """Das Filterblatt öffnen."""
    knopf = next(
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.icon == ft.Icons.FILTER_LIST
    )
    knopf.on_click(None)
    assert isinstance(page.dialoge[-1], ft.BottomSheet)
    return page.dialoge[-1]


def _blatt_chip(blatt, bereich: str, wert) -> ft.Chip:
    return next(x for x in _alle(blatt) if isinstance(x, ft.Chip) and x.data == (bereich, wert))


def _suchen(ansicht, text: str) -> None:
    feld = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField))
    feld.value = text
    feld.on_change(SimpleNamespace(control=feld))


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
    assert state.scroll_offsets["tagebuch"] == 2 * (120 + 14) + 10
    from trainingsapp.core.verlauf import wochen_titel

    beginn = vor_zwei_wochen - timedelta(days=vor_zwei_wochen.weekday())
    assert wochen_titel(beginn) in _texte(ansicht)


def test_antippen_bearbeitet_in_der_liste(page, state) -> None:
    """Ben, 2.11.2026 (P101, P103): kein Popup — die Notiz zum Tag und die zum Plan öffnen
    sich als Editor an Ort und Stelle; die einer Übung in ihren Leistungen des Tages."""
    _plan, _gestern, _ = _welt(state)
    ansicht = tagebuch(page, state)
    texte = _texte(ansicht)
    assert "Kniebeuge" in texte and "Zum Tag" in texte
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.SegmentedButton)]  # eine Liste
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


def test_schnellwahl_tagebuch_filter_und_suche(page, state) -> None:
    """Ben, 12.11.2026: eine Liste von allem Geschriebenen; „Tagebuch“ mit einem Tipp; Filter
    nach Art, Notiz-Tags (ODER, „ohne Tag“), Zeitraum, Plan, Übung; die Suche trifft Text,
    Titel und Tags und füllt nur die Liste neu."""
    plan, gestern, kniebeuge = _welt(state)
    kraft = state.notiz_tags.anlegen(state.profil.id, "Kraft")
    fest = state.notiz_tags.sicherstellen(state.profil.id)
    state.tagesnotizen.anlegen(state.profil.id, gestern, "Beine schwer", [kraft.id])
    state.tagesnotizen.anlegen(state.profil.id, gestern, "ohne Etikett")
    ansicht = tagebuch(page, state)
    alles = {"Schulter fest", "Beine schwer", "ohne Etikett", "zäh heute", "links enger"}
    assert alles <= set(_texte(ansicht))
    assert _chips(ansicht)["Alles"].selected and not _chips(ansicht)["Tagebuch"].selected
    kalender = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.CALENDAR_VIEW_WEEK
    )
    assert kalender.on_click is not None
    # Gekürzt wie das Feld unter Heute
    from trainingsapp.core.tagebuch import AUFNAHME, NOTIZ_ZEILEN, OHNE_TAG, PLAN, TAG, UEBUNG

    karte = next(x for x in _alle(ansicht) if isinstance(x, ft.Text) and x.value == "Schulter fest")
    assert karte.max_lines == NOTIZ_ZEILEN

    # Schnellwahl: ein Tipp, dieselbe Ansicht zieht nach — und die Wahl bleibt stehen
    _chips(ansicht)["Tagebuch"].on_select(None)
    assert state.tagebuch_filter.ist_tagebuch(fest.id)
    assert alles & set(_texte(ansicht)) == {"Schulter fest"}
    assert _chips(ansicht)["Tagebuch"].selected and not _chips(ansicht)["Alles"].selected
    assert alles & set(_texte(tagebuch(page, state))) == {"Schulter fest"}  # nach dem Neubau
    labels = [c.label.value for c in _alle(ansicht) if isinstance(c, ft.Chip) and c.on_delete]
    assert labels == ["Tagebuch"]  # der Tag genügt (Ben, 13.11.2026)
    _chips(ansicht)["Alles"].on_select(None)
    assert state.tagebuch_filter.leer and alles <= set(_texte(ansicht))

    # Filterblatt: Bereiche, wirkt sofort, Trefferzahl
    blatt = _blatt(page, ansicht)
    koepfe = set(_texte(blatt))
    assert {"Filter", ART, TAGS, ZEITRAUM, B_PLAN, B_UEBUNG} <= koepfe and "5 Notizen" in koepfe
    _blatt_chip(blatt, TAGS, kraft.id).on_select(None)
    assert alles & set(_texte(ansicht)) == {"Beine schwer"}
    _blatt_chip(blatt, TAGS, OHNE_TAG).on_select(None)  # ODER
    assert alles & set(_texte(ansicht)) == {"Beine schwer", "ohne Etikett"}
    assert "2 Notizen" in _texte(blatt)
    state.tagebuch_filter.leeren()
    for art, erwartet in ((UEBUNG, {"links enger"}), (PLAN, {"zäh heute"})):
        blatt = _blatt(page, ansicht)
        _blatt_chip(blatt, ART, art).on_select(None)
        assert alles & set(_texte(ansicht)) == erwartet
        _blatt_chip(blatt, ART, art).on_select(None)
    assert {w for b, w in (c.data for c in _alle(blatt) if isinstance(c, ft.Chip)) if b == ART} >= {
        TAG,
        AUFNAHME,
    }
    # Plan und Übung: der Bezug; Zeitraum: nur eine Wahl zugleich
    _blatt_chip(blatt, B_PLAN, plan.id).on_select(None)
    assert alles & set(_texte(ansicht)) == {"zäh heute", "links enger"}
    _blatt_chip(blatt, B_UEBUNG, kniebeuge.id).on_select(None)
    assert alles & set(_texte(ansicht)) == {"links enger"}
    state.tagebuch_filter.leeren()
    blatt = _blatt(page, ansicht)
    _blatt_chip(blatt, ZEITRAUM, 7).on_select(None)
    _blatt_chip(blatt, ZEITRAUM, 28).on_select(None)
    assert state.tagebuch_filter.zeitraum == {28}
    state.tagebuch_filter.leeren()

    # Suche: jedes Wort — im Text, im Tag oder im Titel (Name der Übung)
    ansicht = tagebuch(page, state)
    _suchen(ansicht, "kraft SCHWER")
    assert state.tagebuch_suche == "kraft SCHWER"
    assert alles & set(_texte(ansicht)) == {"Beine schwer"}
    _suchen(ansicht, "kniebeu")
    assert alles & set(_texte(ansicht)) == {"links enger"}
    _suchen(ansicht, "Gemüse")
    assert any(t.startswith("Keine Notizen zu Suche und Filter") for t in _texte(ansicht))
    state.tagebuch_suche = ""


def test_notizen_zu_einer_uebung_im_blatt_der_wege(page, state) -> None:
    """P195 (Ben: „ja“): statt der Ordnung „nach Übungen“ der Weg „Notizen zu ‚Kniebeuge‘“ an
    der Karte — er setzt den Filter auf die Übung."""
    _plan, _gestern, kniebeuge = _welt(state)
    ansicht = tagebuch(page, state)
    karte = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_long_press and "links enger" in _texte(x)
    )
    karte.on_long_press()
    blatt = page.dialoge[-1]
    weg = next(
        x
        for x in _alle(blatt)
        if getattr(x, "on_click", None) and "Notizen zu „Kniebeuge“" in _texte(x)
    )
    weg.on_click()
    asyncio.run(blatt.on_dismiss(None))  # die Wahl wirkt, wenn das Blatt zu ist
    assert state.tagebuch_filter.uebungen == {kniebeuge.id}
    texte = _texte(tagebuch(page, state))
    assert "links enger" in texte and "Schulter fest" not in texte and "zäh heute" not in texte


def test_sprung_von_tage_zum_tag(page, state) -> None:
    """„n Notizen zum Tag“ im Reiter „Tage“ setzt `tagebuch_sprung` — die Liste zeigt den Tag
    (auch jenseits der ersten Seite) und springt hin."""
    _welt(state)
    alt = state.heute() - timedelta(days=200)
    state.tagesnotizen.anlegen(state.profil.id, alt, "lange her")
    state.tagebuch_sprung = alt
    ansicht = tagebuch(page, state)
    assert state.tagebuch_sprung is None and "lange her" in _texte(ansicht)
    assert page.aufgaben  # das Hinspringen ist bestellt


def test_der_verlauf_hat_vier_reiter(page, state) -> None:
    """Seit den Tagesfeldern (21.10.2026) steht „Zum Tag“ vor dem Tagebuch."""
    from trainingsapp.ui.views.verlauf import TAGEBUCH, verlauf

    state.verlauf_tab = TAGEBUCH
    reiter = verlauf(page, state)
    leiste = next(x for x in _alle(reiter) if isinstance(x, ft.TabBar))
    assert [t.label for t in leiste.tabs] == ["Tage", "Übungen", "Zum Tag", "Notizen"]


def test_andere_notiz_antippen_scrollen_und_neubau_beim_schreiben(page, state) -> None:
    """N98: Eine andere Notiz antippen beendet den offenen Editor, sein spätes „Fertig“
    schließt die neue nicht. N99: Scrollen der Liste meldet sich dem Schreibenden. N100: Der
    Editor überlebt den Neubau — und trägt seine Haken wieder ein, die der Routenaufbau leert."""
    _welt(state)
    state.tagesnotizen.anlegen(state.profil.id, state.heute(), "Knie gut")

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
    assert "1 Audioaufnahme" in _texte(tagebuch(page, state))
    state.tagebuch_filter.tagebuch_setzen(etikett.id)  # die Schnellwahl „Tagebuch“
    assert "1 Audioaufnahme" in _texte(tagebuch(page, state))
    state.tagebuch_filter.leeren()
    state.tagebuch_filter.tags.add(OHNE_TAG)
    assert "1 Audioaufnahme" not in _texte(tagebuch(page, state))
    mit_audio([])
    assert "1 Audioaufnahme" in _texte(tagebuch(page, state))


def test_filter_speichern_und_loeschen(page, state) -> None:
    """Ben, 13.11.2026: Das Lesezeichen im Filterblatt legt die Auswahl unter einem Namen ab;
    gespeicherte Filter stehen in der Schnellwahl und lassen sich löschen — auch „Tagebuch“,
    das dann nicht wiederkommt. Je Profil in den Einstellungen."""
    from trainingsapp.core.tagebuch import ABLAGE_SCHLUESSEL, PLAN

    _welt(state)
    state.notiz_tags.sicherstellen(state.profil.id)
    schluessel = f"{ABLAGE_SCHLUESSEL}:{state.profil.id}"
    ansicht = tagebuch(page, state)
    assert list(_chips(ansicht)) == ["Tagebuch", "Alles"]
    assert state.einstellungen.lesen(schluessel) is None  # Vorgabe, nichts geschrieben

    blatt = _blatt(page, ansicht)
    merken = next(
        x
        for x in _alle(blatt)
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.BOOKMARK_ADD_OUTLINED
    )
    assert merken.disabled  # nichts gewählt
    _blatt_chip(blatt, ART, PLAN).on_select(None)
    assert not merken.disabled
    merken.on_click(None)
    feld = next(x for x in _alle(blatt) if isinstance(x, ft.TextField))
    speichern = next(
        x for x in _alle(blatt) if isinstance(x, ft.FilledTonalButton) and x.content == "Speichern"
    )
    speichern.on_click(None)
    assert feld.error == "Name fehlt" and list(_chips(ansicht)) == ["Tagebuch", "Alles"]
    feld.value = "Planworte"
    speichern.on_click(None)
    assert list(_chips(ansicht)) == ["Tagebuch", "Planworte", "Alles"]
    assert _chips(ansicht)["Planworte"].selected
    assert merken.disabled and merken.icon == ft.Icons.BOOKMARK  # schon gespeichert

    # im Blatt: setzen und löschen
    _blatt_chip(blatt, "Gespeichert", "Tagebuch").on_select(None)
    assert state.tagebuch_filter.arten == set() and _chips(ansicht)["Tagebuch"].selected
    _blatt_chip(blatt, "Gespeichert", "Tagebuch").on_delete(None)
    assert list(_chips(ansicht)) == ["Planworte", "Alles"]

    # bleibt nach dem Neuaufbau: „Tagebuch“ kommt nicht wieder, Eigenes bleibt
    ansicht = tagebuch(page, state)
    assert list(_chips(ansicht)) == ["Planworte", "Alles"]
    _chips(ansicht)["Planworte"].on_select(None)
    assert state.tagebuch_filter.arten == {PLAN}
    blatt = _blatt(page, ansicht)
    _blatt_chip(blatt, "Gespeichert", "Planworte").on_delete(None)
    assert list(_chips(ansicht)) == ["Alles"]
    assert state.einstellungen.lesen(schluessel) == "[]"
    assert list(_chips(tagebuch(page, state))) == ["Alles"]
