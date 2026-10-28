"""Der Tag neu (Ben, 18.10.2026; P40, Skizzen A und B) — `ui/views/tag.py`, `nachtragen.py`.

Übersicht mit Plan-Karten (Chip = gemacht, mit Rückgängig; lang drücken = Werte), Zeitleiste
statt „Chronologisch“, Nachtragen mit Uhrzeit und Plan (seit 21.10.2026 der Trainingsblock,
P72), alle Einträge einer Übung an einem beliebigen Tag.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Plan, Strecke, lokaler_tag  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui import einheit as einheit_ui  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.leistungen import leistungen_view  # noqa: E402
from trainingsapp.ui.views.nachtragen import (  # noqa: E402
    FRUEHER,
    OHNE_PLAN,
    nachtragen_blatt,
    nachtragen_view,
)
from trainingsapp.ui.views.tag import ZEITLEISTE, tagesansicht  # noqa: E402


@pytest.fixture
def state(tmp_path):
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

    return SimpleNamespace(
        route="/",
        views=[],
        routen=routen,
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        push_route=push_route,
        run_task=lambda *_a: None,
    )


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "title",
        "subtitle",
        "leading",
        "label",
        "actions",
        "appbar",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(wurzel, text: str):
    for x in _alle(wurzel):
        if isinstance(x, ft.Button | ft.FilledButton | ft.OutlinedButton | ft.TextButton) and (
            x.content == text
        ):
            return x
    raise AssertionError(f"kein Knopf {text!r}")


def _feld(wurzel, label: str) -> ft.TextField:
    return next(x for x in _alle(wurzel) if isinstance(x, ft.TextField) and x.label == label)


def _plan(state: AppState, *keys: str, name: str = "Kräftigung kurz") -> Plan:
    plan = Plan(name=name, subject_id=state.profil.id)
    state.plaene.speichern(plan)
    for key in keys:
        state.plaene.uebung_hinzufuegen(plan.id, seed_id(key))
    geladen = state.plaene.laden(plan.id)
    assert geladen is not None
    return geladen


def _eintragen(state: AppState, plan_id: str | None, key: str, result: dict, **zeit):
    uebung = state.uebungen.laden(seed_id(key))
    tag = lokaler_tag(zeit["started_at"]) if "started_at" in zeit else state.heute()
    session = state.sitzungen.session_fuer(state.profil.id, plan_id, tag)
    return state.sitzungen.eintrag_anlegen(session, uebung, result, **zeit)


def _heute_um(state: AppState, minuten_zurueck: int) -> datetime:
    """Ein Zeitpunkt heute, höchstens ``minuten_zurueck`` vor jetzt — nie gestern."""
    jetzt = datetime.now().astimezone()
    anfang = datetime.combine(state.heute(), time()).astimezone()
    return max(jetzt - timedelta(minutes=minuten_zurueck), anfang)


def test_plan_karte_chip_hakt_ab_rueckgaengig_und_lang_druecken(page, state) -> None:
    plan = _plan(state, "liegestuetzen", "kniebeuge", "wandsitz")
    _eintragen(state, plan.id, "liegestuetzen", {"reps": [15, 15, 13]})
    ansicht = tagesansicht(page, state, state.heute())
    texte = _texte(ansicht)
    assert "STEHT AN" in texte and any(t.startswith("1 von 3") for t in texte)
    # Chips haben eine Umrandung; die gemachte Zeile hat seit 28.10.2026 auch Langdruck
    chips = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_long_press and x.border is not None
    ]
    assert [_texte(c)[-1] for c in chips] == ["Kniebeuge", "Wandsitz"]

    chips[0].on_click()  # Tipp = gemacht, in der Session des Plans
    eintraege = state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    assert [(e.exercise_id, s.plan_id) for e, s in eintraege][-1] == (seed_id("kniebeuge"), plan.id)
    meldung = page.dialoge[-1]
    assert isinstance(meldung, ft.SnackBar) and meldung.action == "Rückgängig"
    meldung.on_action()
    assert len(state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())) == 1

    # Gedrückt halten öffnet seit 28.10.2026 das Zielblatt — Nachtragen steht zuerst, mit Plan
    chips[1].on_long_press()
    blatt = page.dialoge[-1]
    nachtragen = next(
        t
        for t in _alle(blatt.content)
        if isinstance(t, ft.ListTile) and t.title.value == "Nachtragen"
    )
    blatt.open = True
    nachtragen.on_click()
    asyncio.run(blatt.on_dismiss(None))
    assert page.routen[-1] == f"/nachtragen/{seed_id('wandsitz')}/{plan.id}"


def test_start_oeffnet_plan_oder_ablauf_und_fertig_ist_eine_zeile(page, state) -> None:
    ohne = _plan(state, "kniebeuge", name="Ohne Timer")
    mit = _plan(state, "wandsitz", name="Mit Timer")
    state.plaene.plan_timer_setzen(
        mit.id, TimerProfil(name="Kurz", abschnitte=[Abschnitt("A", 60)]).als_dict(), False
    )
    fertig = _plan(state, "liegestuetzen", name="Schon fertig")
    _eintragen(state, fertig.id, "liegestuetzen", {"reps": [10]})
    ansicht = tagesansicht(page, state, state.heute())
    starts = [x for x in _alle(ansicht) if isinstance(x, ft.FilledButton) and x.content == "Start"]
    assert len(starts) == 2
    for knopf in starts:
        asyncio.run(knopf.on_click())
    assert page.routen == [f"/plan/{ohne.id}", f"/plan/{mit.id}/timer/ablauf"]
    texte = _texte(ansicht)
    assert any("mit Ablauf" in t for t in texte)
    assert any(t.startswith("1 von 1 erledigt") for t in texte)


def test_zeitleiste_mit_plan_training_und_notiz(page, state) -> None:
    plan = _plan(state, "liegestuetzen", "kniebeuge")
    frueh = _heute_um(state, 30)
    _eintragen(state, plan.id, "liegestuetzen", {"reps": [15, 13]}, started_at=frueh)
    gehen = _eintragen(state, None, "wadenheben", {"duration": 305}, started_at=_heute_um(state, 5))
    training = Strecke(subject_id=state.profil.id, sportart="gehen", distanz_m=408, dauer_s=305)
    training.session_entry_id = gehen.id
    state.strecken.anlegen(training)
    state.sitzungen.notiz_setzen(
        state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute()).id, "gut gegangen"
    )
    state.tagesnotizen.setzen(state.profil.id, state.heute(), "Schulter fest")

    uebersicht = tagesansicht(page, state, state.heute())
    texte = _texte(uebersicht)
    assert "1 Übung · 1 Training · 2 Notizen" in texte
    assert "Training" in texte and "Kräftigung kurz" in texte  # Etiketten

    state.tag_darstellung = ZEITLEISTE
    texte = _texte(tagesansicht(page, state, state.heute()))
    assert "DER TAG" in texte and "jetzt" in texte
    assert "gut gegangen" in texte and "Notiz zum Tag" in texte
    assert texte.index("Kräftigung kurz") < texte.index("Training")  # nach der Uhr
    assert "noch offen: Kniebeuge" in texte
    assert "STEHT AN" in texte  # oben eine Zeile je Plan, der ansteht


def test_vergangener_tag_ohne_spaeteren_plan_und_mit_eigener_route(page, state) -> None:
    _plan(state, "kniebeuge")  # heute angelegt — vorgestern gab es ihn nicht
    vorgestern = state.heute() - timedelta(days=2)
    um = datetime.combine(vorgestern, time(18)).astimezone()
    _eintragen(state, None, "kniebeuge", {"reps": [19, 18]}, started_at=um)
    basis = f"/tag/{vorgestern.isoformat()}"
    ansicht = tagesansicht(page, state, vorgestern, basis=basis, mit_datum=False)
    texte = _texte(ansicht)
    assert "PLÄNE" not in texte and "STEHT AN" not in texte
    # Langdruck gibt es jetzt an jeder gemachten Zeile (Zielblatt, 28.10.2026) — nur keine Chips
    zeile = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and "Kniebeuge" in _texte(x)
    )
    zeile.on_click()  # ein Blatt über dem Tag, kein Seitenwechsel (Ben, 18.10.2026)
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet) and not page.routen
    assert any(t.startswith("1 Eintrag vom") for t in _texte(blatt))
    blatt.open = True  # wie nach page.show_dialog
    _knopf(blatt, "Nachtragen").on_click()
    asyncio.run(blatt.on_dismiss(None))  # erst wenn das Blatt zu ist, geht es weiter
    assert page.routen == [f"{basis}/nachtragen/{seed_id('kniebeuge')}"]


def _plus(wurzel, text: str | None = None):
    """Ein „+“-Knopf der Karte „Eintragen“ — der erste oder der mit ``text``."""
    return next(
        x
        for x in _alle(wurzel)
        if isinstance(x, ft.FilledButton)
        and isinstance(x.content, ft.Text)
        and str(x.content.value).startswith("+")
        and (text is None or x.content.value == text)
    )


def _klick(knopf) -> None:
    ergebnis = knopf.on_click()
    if asyncio.iscoroutine(ergebnis):
        asyncio.run(ergebnis)


def _zurueck(page, ansicht, basis: str) -> list[bool]:
    """Zurück (Pfeil oder Systemtaste) über ``basis`` — gibt die Antworten an Flutter."""
    antworten: list[bool] = []

    async def confirm_pop(soll: bool) -> None:
        antworten.append(soll)

    ansicht.confirm_pop = confirm_pop
    page.views = [ft.View(route=basis), ansicht]
    asyncio.run(ansicht.on_confirm_pop(None))
    return antworten


def test_nachtragen_frueher_heute_in_den_plan(page, state) -> None:
    """P72 (Ben, 21.10.2026, Skizze G1): Nachtragen ist der Trainingsblock — oben Wann und
    Plan; alles bekommt die gewählte Zeit und sammelt sich in einem Eintrag, „Fertig“
    schließt ihn ab."""
    plan = _plan(state, "kniebeuge")
    uebung = state.uebungen.laden(seed_id("kniebeuge"))
    route = f"/nachtragen/{uebung.id}/{plan.id}"
    ansicht = nachtragen_view(page, state, route, state.heute(), uebung, plan.id)
    texte = _texte(ansicht)
    assert "Wann" in texte and "Plan" in texte and "EINTRAGEN" in texte
    assert not [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.icon in (ft.Icons.TIMER, ft.Icons.TIMER_OUTLINED)
    ]  # ohne Uhr — die Übung ist vorbei
    wann = next(x for x in _alle(ansicht) if isinstance(x, ft.SegmentedButton))
    assert wann.selected == ["jetzt"]
    wann.selected = [FRUEHER]
    wann.on_change(SimpleNamespace(control=wann))
    uhrzeit = _feld(ansicht, "Uhrzeit")
    assert uhrzeit.visible and uhrzeit.value  # vorbelegt
    uhrzeit.value = "25:00"
    uhrzeit.on_submit()
    assert uhrzeit.error == "Uhrzeit?"

    zeit = _heute_um(state, 20).replace(second=0, microsecond=0)
    uhrzeit.value = f"{zeit:%H:%M}"
    uhrzeit.on_change()
    assert uhrzeit.error is None
    ansicht = nachtragen_view(page, state, route, state.heute(), uebung, plan.id)  # neu gebaut
    assert f"EINTRAGEN · mit {zeit:%H:%M}" in _texte(ansicht)  # die Zeit bleibt
    _klick(_plus(ansicht))
    _klick(_plus(ansicht))
    ((eintrag, session),) = state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    assert session.plan_id == plan.id and len(eintrag.result["reps"]) == 2  # ein Eintrag
    assert eintrag.started_at is not None and eintrag.started_at.astimezone() == zeit
    assert eintrag.ended_at is None
    assert "NACHTRAG" in _texte(nachtragen_view(page, state, route, state.heute(), uebung))

    page.views = [ft.View(route="/"), ansicht]
    _klick(_knopf(ansicht, "Fertig"))
    ((eintrag, _),) = state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    assert eintrag.ended_at is not None and eintrag.ended_at.astimezone() == zeit
    assert page.routen == ["/"] and not state.nachtrag_zeit  # beim nächsten Mal wieder „Jetzt“


def test_nachtragen_ohne_plan_und_zurueck_schliesst(page, state) -> None:
    plan = _plan(state, "kniebeuge")
    uebung = state.uebungen.laden(seed_id("kniebeuge"))
    vorgestern = state.heute() - timedelta(days=2)
    basis = f"/tag/{vorgestern.isoformat()}"
    ansicht = nachtragen_view(page, state, f"{basis}/nachtragen/{uebung.id}", vorgestern, uebung)
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.SegmentedButton)]  # nur Uhrzeit
    assert "Plan" not in _texte(ansicht)  # den Plan gab es vorgestern nicht
    assert f"AM {vorgestern:%d.%m.} GELEISTET" not in _texte(ansicht)
    uhrzeit = _feld(ansicht, "Uhrzeit")
    assert uhrzeit.value == "12:00"  # ohne frühere Einträge
    uhrzeit.value = "7:30"
    uhrzeit.on_change()
    # „…“: Sätze × Wert
    mehr = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.OutlinedButton)
        and isinstance(x.content, ft.Text)
        and x.content.value == "…"
    )
    mehr.on_click()
    kasten = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container)
        and isinstance(x.padding, ft.Padding)
        and x.padding.left == 70
        and x.visible
    )
    saetze, wert = [f for f in _alle(kasten) if isinstance(f, ft.TextField)][:2]
    saetze.value, wert.value = "3", "12"
    _klick(next(x for x in _alle(kasten) if isinstance(x, ft.OutlinedButton)))

    assert _zurueck(page, ansicht, basis) == [False]  # Zurück schließt und geht selbst
    assert page.routen == [basis]
    ((eintrag, session),) = state.sitzungen.eintraege_am_tag(state.profil.id, vorgestern)
    assert session.plan_id is None and eintrag.result["reps"] == [12.0, 12.0, 12.0]
    assert eintrag.started_at is not None and f"{eintrag.started_at.astimezone():%H:%M}" == "07:30"
    assert eintrag.ended_at == eintrag.started_at
    assert plan.id not in state.sitzungen.plaene_am_tag(state.profil.id, vorgestern)


def test_nachtragen_nimmt_die_alte_zeit_und_haengt_nicht_an(page, state) -> None:
    """„Die alte Zeit als Vorlage“: Gab es die Übung an dem Tag, steht ihre Uhrzeit da. Ein
    Nachtrag hängt sich nie an einen Eintrag von jetzt — und nicht an einen geschlossenen."""
    gestern = state.heute() - timedelta(days=1)
    um = datetime.combine(gestern, time(18, 15)).astimezone()
    _eintragen(state, None, "kniebeuge", {"reps": [19]}, started_at=um, ended_at=um)
    _eintragen(state, None, "kniebeuge", {"reps": [5]})  # heute, offen
    uebung = state.uebungen.laden(seed_id("kniebeuge"))
    basis = f"/tag/{gestern.isoformat()}"
    route = f"{basis}/nachtragen/{uebung.id}"
    ansicht = nachtragen_view(page, state, route, gestern, uebung)
    assert _feld(ansicht, "Uhrzeit").value == "18:15"
    texte = _texte(ansicht)
    assert f"AM {gestern:%d.%m.} GELEISTET" in texte and "EINTRAGEN · mit 18:15" in texte
    _klick(_plus(ansicht))
    am_tag = state.sitzungen.eintraege_am_tag(state.profil.id, gestern)
    assert [len(e.result["reps"]) for e, _ in am_tag] == [1, 1]  # ein neuer, nicht angehängt
    heute = state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    assert [e.result["reps"] for e, _ in heute] == [[5.0]]


def test_nachtragen_nach_dem_plan_waehlt_den_plan(page, state) -> None:
    """Ben, 21.10.2026: Nach einem Eintrag im Plan stand beim Nachtragen „ohne Plan“ — der
    Nachtrag landete neben dem Plan, die Zeile zeigte aber nur dessen Schild. Jetzt ist der
    Plan vorgewählt, über die Zeile in „Gemacht“ wie über den runden Knopf; Einträge ohne
    Plan in derselben Zeile sagt ein eigenes Schild."""
    plan = _plan(state, "liegestuetzen", "kniebeuge")
    lgs = seed_id("liegestuetzen")
    frueh = _heute_um(state, 30)
    _eintragen(state, plan.id, "liegestuetzen", {"reps": [15]}, started_at=frueh, ended_at=frueh)
    ansicht = tagesansicht(page, state, state.heute())
    zeile = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and x.on_click and "Liegestützen" in _texte(x)
    )
    zeile.on_click()
    blatt = page.dialoge[-1]
    blatt.open = True
    _knopf(blatt, "Nachtragen").on_click()
    asyncio.run(blatt.on_dismiss(None))
    assert page.routen == [f"/nachtragen/{lgs}/{plan.id}"]

    # Der runde Knopf übergibt keinen Plan — die Seite wählt den, in dem sie heute dran war
    uebung = state.uebungen.laden(lgs)
    seite = nachtragen_view(page, state, f"/nachtragen/{lgs}", state.heute(), uebung)
    chips = {x.label.value: x for x in _alle(seite) if isinstance(x, ft.Chip)}
    assert chips["Kräftigung kurz"].selected and not chips["ohne Plan"].selected
    _klick(_plus(seite))
    plaene = [
        s.plan_id for _, s in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
    ]
    assert plaene == [plan.id, plan.id]

    # „ohne Plan“ ersetzt die Seite (Zurück führt weiter zum Tag)
    asyncio.run(chips["ohne Plan"].on_select())
    assert page.routen[-1] == state.ersetzen_bei == f"/nachtragen/{lgs}/{OHNE_PLAN}"
    seite = nachtragen_view(page, state, page.routen[-1], state.heute(), uebung, OHNE_PLAN)
    chips = {x.label.value: x for x in _alle(seite) if isinstance(x, ft.Chip)}
    assert chips["ohne Plan"].selected and not chips["Kräftigung kurz"].selected

    # Wer bewusst „ohne Plan“ nachträgt, sieht das in der Zeile
    _eintragen(state, None, "liegestuetzen", {"reps": [5]})
    texte = _texte(tagesansicht(page, state, state.heute()))
    assert "Kräftigung kurz" in texte and "ohne Plan" in texte


def test_nachtragen_blatt_suche_und_auswahl(page, state) -> None:
    _eintragen(state, None, "wandsitz", {"hold": [60]})
    blatt = nachtragen_blatt(page, state, state.heute(), "")
    assert "ZULETZT GEMACHT" in _texte(blatt) and "Wandsitz" in _texte(blatt)
    suche = next(x for x in _alle(blatt) if isinstance(x, ft.TextField))
    suche.value = "kniebeu"
    suche.on_change(None)
    treffer = next(x for x in _alle(blatt) if isinstance(x, ft.ListView))
    assert treffer.visible and [_texte(z)[0] for z in treffer.controls] == ["Kniebeuge"]
    treffer.controls[0].on_click()
    asyncio.run(blatt.on_dismiss(None))  # erst wenn das Blatt zu ist, geht es weiter
    assert page.routen == [f"/nachtragen/{seed_id('kniebeuge')}"]


def test_leistungen_eines_anderen_tags_mit_nachtragen_und_verlauf(page, state) -> None:
    gestern = state.heute() - timedelta(days=1)
    um = datetime.combine(gestern, time(18)).astimezone()
    _eintragen(state, None, "kniebeuge", {"reps": [19, 18]}, started_at=um)
    _eintragen(state, None, "kniebeuge", {"reps": [5]})  # heute — gehört nicht dazu
    uebung = state.uebungen.laden(seed_id("kniebeuge"))
    basis = f"/tag/{gestern.isoformat()}"
    nachtragen = f"{basis}/nachtragen/{uebung.id}"
    ansicht = leistungen_view(
        page, state, f"{basis}/leistungen/{uebung.id}", uebung, gestern, nachtragen
    )
    assert any(t.startswith("1 Eintrag vom") for t in _texte(ansicht))
    asyncio.run(_knopf(ansicht, "Nachtragen").on_click())
    asyncio.run(_knopf(ansicht, "Im Verlauf ansehen").on_click())
    assert page.routen == [nachtragen, f"/verlauf/{uebung.id}"]


def test_runder_knopf_nur_im_tag_nicht_ueber_der_einheit(page, state) -> None:
    from trainingsapp.core.timer import TimerLauf
    from trainingsapp.ui.app import hauptansicht

    state.reiter = "heute"
    assert hauptansicht(page, state).floating_action_button is not None
    einheit_ui.timer_bereitstellen(
        page, state, TimerLauf(TimerProfil(name="Kurz", abschnitte=[Abschnitt("A", 60)]))
    )
    assert einheit_ui.heute_reiter(state) == einheit_ui.REITER_EINHEIT
    assert hauptansicht(page, state).floating_action_button is None
    einheit_ui.heute_reiter_waehlen(state, einheit_ui.REITER_TAG)
    assert hauptansicht(page, state).floating_action_button is not None


# ---------------------------------------------------------------------------
# Routing der Plan-Karten (Ben, 18.10.2026: temp.md „Routing von den Übungen“)
# ---------------------------------------------------------------------------


def _symbole(wurzel, symbol) -> list:
    return [x for x in _alle(wurzel) if isinstance(x, ft.IconButton) and x.icon == symbol]


def test_karte_ohne_pfeil_weiter_springt_zur_offenen_uebung(page, state) -> None:
    """Der Pfeil war ein dritter Weg in den Plan — weg. „Weiter“ öffnet den Plan bei der
    nächsten offenen Übung (`AppState.plan_ziel`), der Plan rollt einmal dorthin."""
    from trainingsapp.ui.views.plan import plan_view

    plan = _plan(state, "liegestuetzen", "kniebeuge", "wandsitz")
    neu = tagesansicht(page, state, state.heute())
    assert not _symbole(neu, ft.Icons.CHEVRON_RIGHT)
    assert _knopf(neu, "Übungen ansehen")
    _eintragen(state, plan.id, "liegestuetzen", {"reps": [15]})
    unterwegs = tagesansicht(page, state, state.heute())
    assert not _symbole(unterwegs, ft.Icons.CHEVRON_RIGHT)
    weiter = next(
        x for x in _alle(unterwegs) if isinstance(x, ft.FilledButton) and x.content == "Weiter"
    )
    asyncio.run(weiter.on_click())
    assert page.routen == [f"/plan/{plan.id}"]
    assert state.plan_ziel == plan.items[1].id
    aufgaben: list = []
    page.run_task = lambda f, *a: aufgaben.append(f)
    ansicht = plan_view(page, state, state.plaene.laden(plan.id))
    liste = next(x for x in _alle(ansicht) if isinstance(x, ft.ListView))
    assert liste.build_controls_on_demand is False and len(aufgaben) == 1
    assert isinstance(liste.controls[2].key, ft.ScrollKey)  # Kopf, 1. Übung, 2. Übung
    assert state.plan_ziel is None  # nur einmal
    wieder = plan_view(page, state, state.plaene.laden(plan.id))
    assert next(x for x in _alle(wieder) if isinstance(x, ft.ListView)).build_controls_on_demand


def test_anderer_plan_kommt_nur_auf_heute_und_x_mit_rueckgaengig(page, state) -> None:
    """„Anderen Plan“ springt nicht mehr in den Plan — auf der Karte wählt man dann Start
    oder die Übungen. Das X nimmt ihn für heute weg, mit Rückgängig."""
    plan = _plan(state, "kniebeuge", name="Sonntagsplan")
    state.plaene.wochentage_setzen(plan.id, [(state.heute().weekday() + 1) % 7])
    ansicht = tagesansicht(page, state, state.heute())
    _knopf(ansicht, "Anderen Plan").on_click()
    dialog = page.dialoge[-1]
    zeile = next(x for x in _alle(dialog) if isinstance(x, ft.ListTile))
    zeile.on_click()
    asyncio.run(dialog.on_dismiss(None))
    assert page.routen == []  # kein Sprung in den Plan
    assert plan.id in state.sitzungen.plaene_am_tag(state.profil.id, state.heute())
    assert "„Sonntagsplan“ steht jetzt an." in _texte(page.dialoge[-1])

    ansicht = tagesansicht(page, state, state.heute())
    (x,) = _symbole(ansicht, ft.Icons.CLOSE)
    x.on_click()
    assert plan.id not in state.sitzungen.plaene_am_tag(state.profil.id, state.heute())
    meldung = page.dialoge[-1]
    assert isinstance(meldung, ft.SnackBar) and meldung.action == "Rückgängig"
    assert "holt ihn zurück" in _texte(meldung)[0]
    meldung.on_action()
    assert plan.id in state.sitzungen.plaene_am_tag(state.profil.id, state.heute())


def test_einheit_zeilen_fuehren_zu_ihrem_teil(page, state) -> None:
    """Im Reiter „Einheit“ öffnet ein Tipp auf den Plan-Ablauf dessen Ablaufansicht (Ben:
    „Klick auf den Plan öffnet aber nicht das entsprechende Menü“)."""
    from trainingsapp.ui import plan_ablauf
    from trainingsapp.ui.components.startleiste import einheit_reiter

    plan = _plan(state, "kniebeuge", "wandsitz")
    plan_ablauf.bereitstellen(page, state, plan)
    karte = einheit_reiter(page, state)
    titel = "Plan-Ablauf · Kräftigung kurz"
    zeile = next(
        x for x in _alle(karte) if isinstance(x, ft.Container) and x.on_click and titel in _texte(x)
    )
    asyncio.run(zeile.on_click())
    assert page.routen == [f"/plan/{plan.id}/timer/ablauf"]


def test_rueckgaengig_holt_dieselbe_session_und_eintraege_halten_den_plan(page, state) -> None:
    """Durchsicht 18.10.: „Rückgängig“ nach dem X holt die Session mit ihrer Notiz zurück;
    hat der Plan inzwischen Einträge, nimmt das X ihn nicht weg."""
    plan = _plan(state, "kniebeuge", name="Sonntagsplan")
    state.plaene.wochentage_setzen(plan.id, [(state.heute().weekday() + 1) % 7])
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    state.sitzungen.notiz_setzen(session.id, "erst später")
    ansicht = tagesansicht(page, state, state.heute())
    (x,) = _symbole(ansicht, ft.Icons.CLOSE)
    x.on_click()
    assert plan.id not in state.sitzungen.plaene_am_tag(state.profil.id, state.heute())
    page.dialoge[-1].on_action()  # Rückgängig
    zurueck = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    assert zurueck.id == session.id and zurueck.note == "erst später"

    ansicht = tagesansicht(page, state, state.heute())
    (x,) = _symbole(ansicht, ft.Icons.CLOSE)
    _eintragen(state, plan.id, "kniebeuge", {"reps": [10]})  # kam inzwischen dazu
    x.on_click()
    assert plan.id in state.sitzungen.plaene_am_tag(state.profil.id, state.heute())
    assert "er bleibt" in _texte(page.dialoge[-1])[0]


def test_weiter_zur_ersten_uebung_beginnt_oben(page, state) -> None:
    from trainingsapp.ui.views.plan import plan_view

    plan = _plan(state, "liegestuetzen", "kniebeuge")
    route = f"/plan/{plan.id}"
    state.scroll_offsets[route] = 800.0  # von früher
    state.plan_ziel = plan.items[0].id
    plan_view(page, state, state.plaene.laden(plan.id))
    assert route not in state.scroll_offsets
