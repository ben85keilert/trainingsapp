"""Varianten in der Oberfläche (Ben, 21.10.2026; Skizzen A, B, C1, D; P57, P58).

Die Variantenzeile oben in der Ausführung, je Ausführung ein offener Eintrag, das Etikett
neben „Notiz“ mit seinem Blatt, der Abschnitt „Varianten in diesem Plan“, die Varianten in
den Übungseinstellungen und die Kurve mit einer Linie je Variante.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
fc = pytest.importorskip("flet_charts")

from trainingsapp.core import varianten as var  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.standards import varianten_an  # noqa: E402
from trainingsapp.ui.state import UNTEREINANDER, AppState  # noqa: E402
from trainingsapp.ui.views.plan import plan_view  # noqa: E402

KURZ_LANG = [var.Variante("kurz", kuerzel="K"), var.Variante("lang", text="Brust bis zum Boden")]


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
        "segments",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control | ft.Segment):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _klick(knopf, *args) -> None:
    ergebnis = knopf.on_click(*args)
    if inspect.isawaitable(ergebnis):
        asyncio.run(ergebnis)


def _liegestuetz(state: AppState) -> Exercise:
    spec = var.mit_varianten(ResultSpec(fields=[vorrat_feld("reps")]), KURZ_LANG)
    u = Exercise(name="Liegestütz", result_spec=spec)
    state.uebungen.speichern(u)
    return state.uebungen.laden(u.id)


def _plan(state: AppState, uebung: Exercise) -> tuple[Plan, PlanItem]:
    plan = Plan(name="Kraft", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, uebung.id)
    state.plan_darstellung_setzen(UNTEREINANDER)
    return state.plaene.laden(plan.id), item


def _variantenzeile(ansicht) -> ft.SegmentedButton | None:
    return next(
        (
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.SegmentedButton)
            and [s.value for s in x.segments] == ["kurz", "lang"]
        ),
        None,
    )


def _waehlen(ansicht, name: str) -> None:
    zeile = _variantenzeile(ansicht)
    assert zeile is not None
    zeile.on_change(SimpleNamespace(control=SimpleNamespace(selected=[name] if name else [])))


def _plus(ansicht, text: str = "10"):
    return next(
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.FilledButton)
        and isinstance(c.content, ft.Control)
        and [t.lstrip("+") for t in _texte(c.content)] == [text]
    )


def _eintraege(state: AppState) -> list:
    return [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]


def test_je_ausfuehrung_ein_offener_eintrag(page, state) -> None:
    """Ben: „kurz+30, lang+15, kurz+30 → kein zweiter Kurzeintrag“ — die Zeile wählt, die
    „+“-Knöpfe sammeln je Variante in ihrem eigenen offenen Eintrag (P57)."""
    plan, item = _plan(state, _liegestuetz(state))
    ansicht = plan_view(page, state, plan)
    assert _variantenzeile(ansicht) is not None
    _waehlen(ansicht, "kurz")
    assert state.auspraegung_wahl[item.id] == {"variant": "kurz"}
    _klick(_plus(ansicht))
    _klick(_plus(ansicht))
    _waehlen(ansicht, "lang")
    _klick(_plus(ansicht))
    _waehlen(ansicht, "kurz")
    _klick(_plus(ansicht))
    ergebnisse = sorted((e.result["variant"], e.result["reps"]) for e in _eintraege(state))
    assert ergebnisse == [("kurz", [10.0, 10.0, 10.0]), ("lang", [10.0])]
    assert all(e.ended_at is None for e in _eintraege(state))  # beide noch offen
    # „Heute geleistet“ nennt die Summen je Variante, der andere offene Eintrag ist wählbar
    texte = _texte(ansicht)
    assert any("offen · Tippen wählt" in t for t in texte)


def test_etikett_setzt_die_variante_des_offenen_eintrags(page, state) -> None:
    """Das Etikett neben „Notiz“ (nur das Symbol, A1): das Blatt setzt die Variante des
    offenen Eintrags nachträglich — eine Korrektur — und legt neue Varianten an."""
    uebung = _liegestuetz(state)
    plan, item = _plan(state, uebung)
    ansicht = plan_view(page, state, plan)
    _klick(_plus(ansicht))  # ohne Variante
    (offen,) = _eintraege(state)
    assert "variant" not in offen.result
    (etikett,) = [
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.tooltip == "Variante"
    ]
    etikett.on_click()
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    texte = _texte(blatt.content)
    assert "ohne Variante" in texte and "Brust bis zum Boden" in texte
    lang = next(
        x
        for x in _alle(blatt.content)
        if isinstance(x, ft.Container) and x.on_click is not None and "lang" in _texte(x)
    )
    blatt.open = True
    lang.on_click()
    asyncio.run(blatt.on_dismiss(None))
    (korrigiert,) = _eintraege(state)
    assert korrigiert.result["variant"] == "lang" and korrigiert.id != offen.id  # Korrektur
    assert state.auspraegung_wahl[item.id]["variant"] == "lang"
    # Eine neue Variante aus dem Blatt landet in der Übung
    (etikett,) = [
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.tooltip == "Variante: lang"
    ]
    etikett.on_click()
    blatt = page.dialoge[-1]
    (feld,) = [x for x in _alle(blatt.content) if isinstance(x, ft.TextField)]
    feld.value = "eng"
    blatt.open = True
    feld.on_submit(None)
    asyncio.run(blatt.on_dismiss(None))
    assert var.namen(state.uebungen.laden(uebung.id).result_spec) == ["kurz", "lang", "eng"]


def test_varianten_bereich_unter_den_parametern(page, state) -> None:
    """P58/P79: „Im Plan einstellen“ hat unter den Parametern den Abschnitt „Varianten“; aus
    heißt: keine Variantenzeile in dieser Planübung — „nur hier“, ↺ holt sie zurück. Die
    Übungsseite aus dem Plan zeigt es in der Karte „In diesem Plan“."""
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    uebung = _liegestuetz(state)
    plan, item = _plan(state, uebung)
    ansicht = plan_einstellen(page, state, plan, item, uebung)
    assert "VARIANTEN" in _texte(ansicht)
    schalter = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Switch) and "Varianten" in (x.tooltip or "")
    )
    assert schalter.value is True
    schalter.value = False
    schalter.on_change()
    speichern = next(
        x for x in _alle(ansicht) if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    _klick(speichern)
    gespeichert = state.plaene.item_laden(item.id)
    assert not varianten_an(gespeichert)
    assert _variantenzeile(plan_view(page, state, state.plaene.laden(plan.id))) is None
    assert var.namen(state.uebungen.laden(uebung.id).result_spec) == ["kurz", "lang"]
    seite = uebung_detail(page, state, uebung, None, gespeichert, plan=plan, einstellen="/x")
    assert "nicht gezeigt" in _texte(seite) and "nur hier" in _texte(seite)

    # Wieder öffnen: der Schalter steht aus, „nur hier“ — wieder an, gespeichert mit „Speichern“
    ansicht = plan_einstellen(page, state, state.plaene.laden(plan.id), gespeichert, uebung)
    schalter = next(
        x for x in _alle(ansicht) if isinstance(x, ft.Switch) and "Varianten" in (x.tooltip or "")
    )
    assert schalter.value is False and "nur hier" in _texte(ansicht)
    schalter.value = True
    schalter.on_change()
    speichern = next(
        x for x in _alle(ansicht) if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    _klick(speichern)
    assert varianten_an(state.plaene.item_laden(item.id))
    assert _variantenzeile(plan_view(page, state, state.plaene.laden(plan.id))) is not None


def test_ohne_varianten_keine_zeile_aber_das_etikett(page, state) -> None:
    """Ohne Varianten bleibt der Block wie bisher — nur das Etikett steht neben „Notiz“, damit
    die erste Variante unterwegs entstehen kann (A1); einen Plan-Abschnitt gibt es nicht."""
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen

    u = Exercise(name="Kniebeuge", result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    state.uebungen.speichern(u)
    plan, item = _plan(state, state.uebungen.laden(u.id))
    ansicht = plan_view(page, state, plan)
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.SegmentedButton)]
    etiketten = [
        x for x in _alle(ansicht) if isinstance(x, ft.IconButton) and x.tooltip == "Variante"
    ]
    assert len(etiketten) == 1
    einstellen = plan_einstellen(page, state, plan, item, state.uebungen.laden(u.id))
    assert "VARIANTEN" not in _texte(einstellen)
    assert not [
        x
        for x in _alle(einstellen)
        if isinstance(x, ft.Switch) and "Varianten" in (x.tooltip or "")
    ]


def test_viele_varianten_brechen_auf_zeilen_um(page, state) -> None:
    """Passen die Namen nicht in eine Zeile, stehen sie als Knöpfe mit Zeichen und Namen in
    einer umbrechenden Reihe (Ben, 26.10.2026: „lesbar auf mehrere Zeilen“) — bis dahin nur
    Zeichen ohne Namen (D1). Die Beschreibung der gewählten steht darunter."""
    planke = [
        var.Variante("Unterarm", symbol="crop_square", text="Ellbogen unter den Schultern"),
        var.Variante("Arme gestreckt", symbol="height"),
        var.Variante("Seitlich", symbol="swap_horiz"),
        var.Variante("Diagonal", kuerzel="D"),
    ]
    spec = var.mit_varianten(ResultSpec(fields=[vorrat_feld("hold")]), planke)
    u = Exercise(name="Planke", result_spec=spec)
    state.uebungen.speichern(u)
    plan, item = _plan(state, state.uebungen.laden(u.id))
    state.auspraegung_wahl[item.id] = {"variant": "Unterarm"}
    ansicht = plan_view(page, state, plan)
    assert not [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.SegmentedButton) and [s.value for s in x.segments][:1] == ["Unterarm"]
    ]
    (reihe,) = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Row)
        and x.wrap
        and len(x.controls) == 4
        and all(isinstance(k, ft.OutlinedButton | ft.FilledTonalButton) for k in x.controls)
    ]
    assert isinstance(reihe.controls[0], ft.FilledTonalButton)  # die gewählte, getönt
    texte = _texte(ansicht)
    assert all(n in texte for n in ("Unterarm", "Arme gestreckt", "Seitlich", "Diagonal"))
    assert "Unterarm – Ellbogen unter den Schultern" in texte


def test_varianten_in_den_uebungseinstellungen(page, state) -> None:
    """D3/D4: Abschnitt VARIANTEN mit Plakette, Name und Beschreibung; „Variante hinzufügen“
    öffnet den Dialog, „Übernehmen“ und „Speichern“ legen sie in die Übung."""
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    uebung = _liegestuetz(state)
    ansicht = uebung_bearbeiten(page, state, uebung)
    texte = _texte(ansicht)
    assert "VARIANTEN" in texte and "Brust bis zum Boden" in texte
    hinzu = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.TextButton) and x.content == "Variante hinzufügen"
    )
    _klick(hinzu)
    dialog = page.dialoge[-1]
    felder = {x.label: x for x in _alle(dialog.content) if isinstance(x, ft.TextField)}
    felder["Name"].value = "eng"
    felder["oder Kürzel"].value = "E"
    uebernehmen = next(
        x
        for x in _alle(dialog)
        if isinstance(x, ft.FilledButton | ft.TextButton) and x.content == "Übernehmen"
    )
    dialog.open = True
    _klick(uebernehmen)
    if dialog.on_dismiss is not None:
        asyncio.run(dialog.on_dismiss(None))
    speichern = next(
        x for x in _alle(ansicht) if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    _klick(speichern)
    liste = var.varianten(state.uebungen.laden(uebung.id).result_spec)
    assert [(v.name, v.kuerzel) for v in liste] == [("kurz", "K"), ("lang", ""), ("eng", "E")]


def _eintragen(state: AppState, uebung: Exercise, tag: date, **result) -> None:
    session = state.sitzungen.session_fuer(state.profil.id, None, tag)
    start = datetime.combine(tag, time(18)).astimezone()
    state.sitzungen.eintrag_anlegen(session, uebung, result, started_at=start)


def test_kurve_eine_linie_je_variante(state) -> None:
    """B2: eine Kurve, kurz und lang als eigene Linien in fester Farbe; die Farbpunkte
    blenden aus, „Zusammen“ (gestrichelt) ist zuschaltbar; die Ergebnisse zählen je
    Variante."""
    from trainingsapp.ui.views.verlauf_kachel import verlauf_kachel_view

    uebung = _liegestuetz(state)
    heute = state.heute()
    _eintragen(state, uebung, heute - timedelta(days=2), variant="kurz", reps=[30, 30])
    _eintragen(state, uebung, heute - timedelta(days=2), variant="lang", reps=[15])
    _eintragen(state, uebung, heute, variant="kurz", reps=[40])
    seite = SimpleNamespace(route="/", update=lambda: None)
    ansicht = verlauf_kachel_view(seite, state, uebung.id)
    (kurve,) = [x for x in _alle(ansicht) if isinstance(x, fc.LineChart)]
    assert [[p.y for p in d.points] for d in kurve.data_series] == [[60, 40], [15]]
    assert kurve.data_series[0].color != kurve.data_series[1].color
    legende = {x.label.value: x for x in _alle(ansicht) if isinstance(x, ft.Chip)}
    assert set(legende) >= {"kurz", "lang", "Zusammen"} and not legende["Zusammen"].selected
    texte = _texte(ansicht)
    assert "Höchster · kurz" in texte and "Höchster · lang" in texte
    assert any(t.startswith("kurz · 30 · 30") for t in texte) and "lang · 15" in texte
    # „Zusammen“ an: eine dritte, gestrichelte Linie mit der Summe des Tages
    legende["Zusammen"].on_select(None)
    ansicht = verlauf_kachel_view(seite, state, uebung.id)
    (kurve,) = [x for x in _alle(ansicht) if isinstance(x, fc.LineChart)]
    assert [p.y for p in kurve.data_series[-1].points] == [75, 40]
    assert kurve.data_series[-1].dash_pattern
    # „lang“ ausblenden: bleibt kurz und Zusammen
    legende = {x.label.value: x for x in _alle(ansicht) if isinstance(x, ft.Chip)}
    legende["lang"].on_select(None)
    ansicht = verlauf_kachel_view(seite, state, uebung.id)
    (kurve,) = [x for x in _alle(ansicht) if isinstance(x, fc.LineChart)]
    assert len(kurve.data_series) == 2


def test_tag_und_tagebuch_je_variante(page, state) -> None:
    """B1: im Tag je Variante eine Zeile mit eigener Zahl, im Tagebuch „Liegestütz · lang“."""
    from trainingsapp.ui.views.tag import tag_view
    from trainingsapp.ui.views.verlauf import verlauf

    uebung = _liegestuetz(state)
    heute = state.heute()
    _eintragen(state, uebung, heute, variant="kurz", reps=[30, 30])
    _eintragen(state, uebung, heute, variant="lang", reps=[15])
    texte = _texte(tag_view(page, state, heute))
    assert texte.count("Liegestütz") >= 2 and "kurz" in texte and "lang" in texte
    assert "60" in texte and "15" in texte
    state.verlauf_tab = 1  # Reiter „Übungen“: je Variante eine Zeile
    texte = _texte(verlauf(page, state))
    assert texte.count("Liegestütz") == 2


def test_chip_gibt_markiertem_eintrag_ohne_variante_die_variante(page, state) -> None:
    """Ben, 28.10.2026: Luft anhalten mit Stoppuhr-Zeiten, dann die Variante setzen — ein
    Tipp auf den Chip gibt sie dem markierten Eintrag, der noch keine hat (wie das Etikett).
    Hat er schon eine, beginnt der nächste Wert wie bisher einen neuen Eintrag (P57)."""
    uebung = _liegestuetz(state)
    plan, _item = _plan(state, uebung)
    ansicht = plan_view(page, state, plan)
    _klick(_plus(ansicht))  # ein offener Eintrag ohne Variante
    (offen,) = _eintraege(state)
    assert "variant" not in offen.result and offen.ended_at is None
    _waehlen(ansicht, "lang")
    (korrigiert,) = _eintraege(state)
    assert korrigiert.result["variant"] == "lang" and korrigiert.ended_at is None
    assert korrigiert.result["reps"] == [10] and korrigiert.id != offen.id  # eine Korrektur
    ansicht = plan_view(page, state, plan)
    _klick(_plus(ansicht))  # sammelt weiter in ihm
    (weiter,) = _eintraege(state)
    assert weiter.result["reps"] == [10, 10] and weiter.result["variant"] == "lang"
    # Er hat jetzt eine Variante: „kurz“ wählen ändert ihn nicht, der nächste Wert ist neu
    _waehlen(ansicht, "kurz")
    assert [e.result["variant"] for e in _eintraege(state)] == ["lang"]
    ansicht = plan_view(page, state, plan)
    _klick(_plus(ansicht))
    assert sorted(e.result["variant"] for e in _eintraege(state)) == ["kurz", "lang"]


def test_keine_variante_automatisch(page, state) -> None:
    """Ben, 28.10.2026: „keine Variante automatisch“ — der letzte Eintrag gibt Gewicht und
    Winkel vor, die Variante nicht; sie beginnt mit „ohne“."""
    uebung = _liegestuetz(state)
    plan, item = _plan(state, uebung)
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    state.sitzungen.eintrag_fertig(session, uebung, {"variant": "lang", "reps": [5]})
    ansicht = plan_view(page, state, plan)
    assert "variant" not in state.auspraegung_wahl.get(item.id, {})
    zeile = _variantenzeile(ansicht)
    assert zeile is not None and zeile.selected in ([], None)


def test_gemacht_schliesst_markierten_eintrag_ohne_leistung(page, state) -> None:
    """Ben, 28.10.2026: Ein markierter Eintrag, der nichts hat außer dem Stempel, zeigt
    „Gemacht“ statt „Abschließen“ — der Knopf schließt ihn, ein zweiter Stempel entsteht
    nicht. Mit Werten heißt er „Abschließen“."""
    uebung = _liegestuetz(state)
    plan, _item = _plan(state, uebung)
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    state.sitzungen.eintrag_anlegen(session, uebung, {})  # offen, ohne alles
    ansicht = plan_view(page, state, plan)

    def knopf(text: str):
        return next(
            x
            for x in _alle(ansicht)
            if isinstance(x, ft.OutlinedButton) and _texte(x.content) == [text]
        )

    _klick(knopf("Gemacht"))
    (eintrag,) = _eintraege(state)
    assert eintrag.ended_at is not None and eintrag.result == {}
    assert page.dialoge[-1].content.value == "Liegestütz: gemacht"
    # Mit einem Wert heißt der Knopf „Abschließen“
    ansicht = plan_view(page, state, plan)
    _klick(_plus(ansicht))
    ansicht = plan_view(page, state, plan)
    _klick(knopf("Abschließen"))
    assert all(e.ended_at is not None for e in _eintraege(state)) and len(_eintraege(state)) == 2
    assert page.dialoge[-1].content.value == "Liegestütz: abgeschlossen"
