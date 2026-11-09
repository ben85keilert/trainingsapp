"""Paketinhalte U2 in der Oberfläche (Ben, 9.11.2026, `docs/plan_paketinhalte.md` §9, F6/F7).

Anweisungen je Planübung (Abschnitte und Links) in „Im Plan einstellen“ und im „i“; der Knopf
„Material“ in der Übung und im Fokus — solange das Blatt offen ist, steht die Uhr; „Plan neu
laden“ im Plan-Editor und „Wieder anlegen“ im Paketmanager. Läuft nur mit `flet`.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe  # noqa: E402
from trainingsapp.core.models import Exercise, Media, Plan  # noqa: E402
from trainingsapp.core.pakete import paket_lesen  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "title",
        "subtitle",
        "leading",
        "trailing",
        "label",
        "appbar",
        "actions",
        "items",
        "header",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _klick(knopf, *args):
    ergebnis = knopf.on_click(*args)
    if inspect.isawaitable(ergebnis):
        return asyncio.run(ergebnis)
    return ergebnis


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    async def push_route(route: str) -> None:
        seite.routen.append(route)

    seite = SimpleNamespace(
        route="/",
        views=[],
        routen=[],
        dialoge=[],
        width=390,
        update=lambda: None,
        pop_dialog=lambda: None,
        push_route=push_route,
    )
    seite.show_dialog = seite.dialoge.append
    return seite


def _planuebung(state: AppState, **mehr):
    u = Exercise(name="Unterarmstütz", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    state.uebungen.speichern(u)
    plan = Plan(name="Rücken", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    if mehr:
        state.plaene.item_speichern(replace(item, **mehr))
    return state.uebungen.laden(u.id), state.plaene.laden(plan.id), state.plaene.item_laden(item.id)


# -- Anweisungen: „Im Plan einstellen“ und das „i“ ----------------------------------------


def test_anweisungen_im_plan_einstellen_bleiben_wortgleich_und_links_kommen_dazu(
    page, state
) -> None:
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen

    text = "## Im Plan\n\n\nam Fenster, langsam"  # mit Leerzeilen — so, wie er im Paket stand
    uebung, plan, item = _planuebung(
        state, description=text, media=[Media(uri="https://x.org/a.pdf", title="Blatt")]
    )
    assert item.description == text
    ansicht = plan_einstellen(page, state, plan, item, uebung)
    texte = _texte(ansicht)
    assert "ANWEISUNGEN" in texte and "Im Plan" in texte and "am Fenster, langsam" in texte
    titel = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Titel"]
    assert [t.value for t in titel] == ["Blatt"]
    # Ein Link dazu — die Felder entstehen neu, die Werte stehen im Formular
    _klick(_daten(ansicht, "link_hinzufuegen"))
    felder = [x for x in _alle(ansicht) if isinstance(x, ft.TextField)]
    neu_titel = [f for f in felder if f.label == "Titel"][-1]
    neu_adresse = [f for f in felder if f.label == "Adresse (https://…)"][-1]
    neu_titel.on_change(SimpleNamespace(control=SimpleNamespace(value="Video")))
    neu_adresse.on_change(SimpleNamespace(control=SimpleNamespace(value="http://x.org/v")))
    speichern = next(
        x
        for x in _alle(ansicht.appbar)
        if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    _klick(speichern)
    # Nur https: nichts gespeichert, der Hinweis steht da
    assert "Nur https-Adressen: http://x.org/v" in _texte(ansicht)
    assert [m.uri for m in state.plaene.item_laden(item.id).media] == ["https://x.org/a.pdf"]
    neu_adresse.on_change(SimpleNamespace(control=SimpleNamespace(value="https://x.org/v")))
    _klick(speichern)
    gespeichert = state.plaene.item_laden(item.id)
    assert [(m.title, m.uri) for m in gespeichert.media] == [
        ("Blatt", "https://x.org/a.pdf"),
        ("Video", "https://x.org/v"),
    ]
    assert gespeichert.description == text  # unberührt — wortgleich


def test_das_i_zeigt_die_anweisungen_der_planuebung(page, state) -> None:
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    uebung, plan, item = _planuebung(
        state,
        description="## Im Plan\nam Fenster",
        media=[Media(uri="https://x.org/v", title="So geht es hier")],
    )
    seite = uebung_detail(
        page, state, uebung, None, item, plan=plan, route="/r", einstellen="/einstellen"
    )
    texte = _texte(seite)
    assert "ANWEISUNGEN IN DIESEM PLAN" in texte
    assert "Im Plan" in texte and "am Fenster" in texte and "So geht es hier" in texte
    # Ohne Anweisungen keine Überschrift
    ohne = uebung_detail(
        page,
        state,
        uebung,
        None,
        replace(item, description="", media=[]),
        plan=plan,
        route="/r",
        einstellen="/einstellen",
    )
    assert "ANWEISUNGEN IN DIESEM PLAN" not in _texte(ohne)


# -- Material hält die Uhr an ---------------------------------------------------------------


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
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


async def _sekunden(state, uhr, gurt, n: int) -> None:
    for _ in range(n):
        uhr.t += 1
        gurt.schlag(1000)
        await ruhe()
        if state.einheit is not None and state.einheit.laeuft:
            state.einheit.takt()


async def test_material_haelt_die_uhr_an_und_laesst_sie_weiterlaufen(umgebung) -> None:
    """F6: „solange das Material angesehen wird, pausiert die Uhr, kann aber manuell wieder
    gestartet werden“ — Schließen lässt sie weiterlaufen, „Uhr weiter“ sofort."""
    from trainingsapp.ui.views.plan import einzel_plan, plan_view

    state, uhr, gurt = umgebung
    uebung = Exercise(
        name="Wandsitz",
        result_spec=ResultSpec(layout=Layout.TIMED, fields=[vorrat_feld("hold")]),
        media=[Media(uri="https://x.org/wandsitz", title="So geht’s")],
    )
    state.uebungen.speichern(uebung)
    seite = Seite()

    def ansicht():
        return plan_view(seite, state, einzel_plan(uebung), einzel=True)

    ohne = Exercise(name="Ohne Material")
    state.uebungen.speichern(ohne)
    leer = plan_view(seite, state, einzel_plan(ohne), einzel=True)
    assert not [x for x in _alle(leer) if getattr(x, "data", None) == "material"]

    next(
        x
        for x in _alle(ansicht())
        if isinstance(x, ft.IconButton)
        and x.icon == ft.Icons.PLAY_ARROW
        and "starten" in (x.tooltip or "")
    ).on_click()
    await _sekunden(state, uhr, gurt, 10)
    lauf = state.einheit.timer.lauf
    assert lauf.laeuft
    material = _daten(ansicht(), "material")
    assert "Video" in material.tooltip
    material.on_click()
    blatt = seite.dialoge[-1]
    assert "So geht’s" in _texte(blatt) and "Die Uhr steht, solange du hier bist." in _texte(blatt)
    assert not lauf.laeuft
    await _sekunden(state, uhr, gurt, 20)
    assert round(lauf.vergangen_s()) == 10
    await blatt.on_dismiss(None)  # zu — die Uhr läuft weiter
    assert lauf.laeuft
    await _sekunden(state, uhr, gurt, 5)
    # Noch einmal: „Uhr weiter“ von Hand, danach ändert Schließen nichts
    _daten(ansicht(), "material").on_click()
    blatt = seite.dialoge[-1]
    assert not lauf.laeuft
    _daten(blatt, "uhr_weiter").on_click()
    assert lauf.laeuft and "Die Uhr läuft weiter." in _texte(blatt)
    lauf.pause()  # die Person hält sie selbst an — Schließen startet sie nicht wieder
    await blatt.on_dismiss(None)
    assert not lauf.laeuft
    lauf.abbrechen()
    await _sekunden(state, uhr, gurt, 2)


async def test_material_im_fokus(umgebung) -> None:
    from trainingsapp.ui.views.uebung_timer import uebung_timer_view

    state, uhr, gurt = umgebung
    profil = TimerProfil(id="satz", name="Satz 30 s", abschnitte=[Abschnitt("Satz", 30)])
    u = Exercise(
        name="Kniebeuge",
        timer=[profil.als_dict()],
        media=[Media(uri="https://x.org/k.pdf", title="Blatt")],
    )
    state.uebungen.speichern(u)
    seite = Seite()
    basis = f"/uebung/{u.id}"
    vorher = uebung_timer_view(seite, state, basis, u)
    next(
        x
        for x in _alle(vorher)
        if isinstance(x, ft.FilledButton | ft.FilledTonalButton | ft.OutlinedButton)
        and (x.content == "Starten" or "Starten" in _texte(x))
    ).on_click()
    await _sekunden(state, uhr, gurt, 3)
    fokus = uebung_timer_view(seite, state, basis, u)
    assert fokus.appbar.title.value == "Fokus · Kniebeuge"
    knopf = _daten(fokus, "material")
    assert isinstance(knopf, ft.IconButton) and "PDF" in knopf.tooltip
    knopf.on_click()
    assert not state.einheit.timer.lauf.laeuft
    await seite.dialoge[-1].on_dismiss(None)
    assert state.einheit.timer.lauf.laeuft
    state.einheit.timer.lauf.abbrechen()
    await _sekunden(state, uhr, gurt, 2)


# -- Plan neu laden, wieder anlegen ---------------------------------------------------------


def _paket(state: AppState) -> tuple[str, Plan]:
    roh = {
        "paket": {"name": "Qigong", "version": 1},
        "exercises": [
            {"key": "baum", "name": "Baum", "description": "Stehen."},
            {"key": "tief", "name": "Baum tief", "description": "Tiefer stehen."},
        ],
        "plaene": [
            {
                "key": "morgen",
                "name": "Morgen",
                "uebungen": [{"uebung": "baum", "ziel": {"duration": 300}}, {"uebung": "tief"}],
            }
        ],
    }
    inhalt = paket_lesen(roh)
    state.pakete.importieren(inhalt, subject_id=state.profil.id)
    (plan,) = state.plaene.des_pakets(inhalt.paket.id, state.profil.id)
    return inhalt.paket.id, plan


def test_plan_neu_laden_im_plan_editor(page, state) -> None:
    from trainingsapp.ui.views.plan import plan_view

    _paket_id, plan = _paket(state)
    baum, tief = plan.items
    state.plaene.uebung_entfernen(tief.id)  # herausgenommen
    plan = state.plaene.laden(plan.id)
    editor = plan_view(page, state, plan, bearbeiten=True)
    assert "Aus Paket „Qigong“" in _texte(editor)
    _klick(_daten(editor, "neu_laden"))
    blatt = page.dialoge[-1]
    assert "Kommt zurück: Baum tief. Deine Änderungen an den Übungen dieses Plans bleiben." in (
        _texte(blatt)
    )
    blatt.open = True
    _klick(_daten(blatt, "weich"))
    assert [i.exercise_id for i in state.plaene.laden(plan.id).items] == [
        baum.exercise_id,
        tief.exercise_id,
    ]
    # Ein eigener Plan hat keine Quelle — keine Zeile
    eigen = Plan(name="Eigen", subject_id=state.profil.id)
    state.plaene.speichern(eigen)
    assert not [
        x
        for x in _alle(plan_view(page, state, eigen, bearbeiten=True))
        if getattr(x, "data", None) == "neu_laden"
    ]


def test_paketmanager_legt_geloeschten_plan_wieder_an(page, state) -> None:
    from trainingsapp.ui.views.pakete import paket_view

    paket_id, plan = _paket(state)
    state.plaene.loeschen(plan.id)
    state.plaene.endgueltig_loeschen(plan.id)
    paket = state.pakete.laden(paket_id)
    ansicht = paket_view(page, state, "/pakete", paket)
    assert "gelöscht" in _texte(ansicht)
    _klick(_daten(ansicht, ("plan_wieder", "morgen")))
    (wieder,) = state.plaene.des_pakets(paket_id, state.profil.id)
    assert wieder.id == plan.id and len(wieder.items) == 2
    ansicht = paket_view(page, state, "/pakete", paket)
    assert "wie im Paket" in _texte(ansicht)


def test_kurs_neu_laden_im_menue(page, state) -> None:
    from trainingsapp.core.kurse import Kapitel, Kurs, PlanVorlage, VorlageItem
    from trainingsapp.data.seed import seed_id
    from trainingsapp.ui.views.kurse import kurs_view

    kapitel = Kapitel(
        titel="Üben", plaene=[PlanVorlage("Kurs: Üben", [0], [VorlageItem(seed_id("kniebeuge"))])]
    )
    k = Kurs(name="Testkurs", kapitel=[kapitel])
    state.kurse.speichern(k)
    state.kurse.starten(k, state.profil.id)
    (plan,) = state.kurse.kapitel_plaene(kapitel.id, state.profil.id)
    state.plaene.loeschen(plan.id)
    assert state.kurse.kapitel_plaene(kapitel.id, state.profil.id) == []
    ansicht = kurs_view(page, state, k)
    menue = next(x for x in _alle(ansicht) if isinstance(x, ft.PopupMenuButton))
    next(i for i in menue.items if i.content == "Kurs neu laden …").on_click()
    dialog = page.dialoge[-1]
    dialog.open = True
    _klick(_daten(dialog, "weich"))
    asyncio.run(dialog.on_dismiss(None))
    assert [p.id for p in state.kurse.kapitel_plaene(kapitel.id, state.profil.id)] == [plan.id]
    assert "1 Plan neu geladen" in _texte(page.dialoge[-1])
