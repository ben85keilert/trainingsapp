"""Der Kurs-Editor für den Kursplan (Ben, 16.11.2026, `docs/plan_kurs_ablauf.md` §11.6, Skizzen
K5/K6): die Karte „Der Kurs baut einen Plan“, die Bausteine „Am Plan“ mit ihren Formularen und
der Vorschau „So steht es in der Karte“, Löschen mit Verweisen, die Kopie eines Kurses.

Die Vorschau muss dieselben Texte zeigen wie die Karte der Teilnehmenden
(`KursRepo.plan_aenderungen`) — das prüft `test_vorschau_zeigt_die_texte_der_karte`. Läuft nur
mit `flet`.
"""

from __future__ import annotations

import asyncio
import doctest
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core import ablauf as ab  # noqa: E402
from trainingsapp.core.kursbau import Kurssicht  # noqa: E402
from trainingsapp.core.kursbloecke import (  # noqa: E402
    AUSWAHL,
    HART,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    TEXT,
    Block,
)
from trainingsapp.core.kurse import (  # noqa: E402
    TAGE,
    Bedingung,
    Kapitel,
    Kurs,
    Kursplan,
    PlanVorlage,
    VorlageItem,
)
from trainingsapp.core.models import Exercise, Plan, Session  # noqa: E402
from trainingsapp.core.pakete import PaketPlan, kurs_stand, paket_lesen  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.paket_werkzeug import kursplan_pruefen  # noqa: E402
from trainingsapp.ui.components import baustein_form  # noqa: E402
from trainingsapp.ui.components.baustein_form import KEIN  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views import kurs_bearbeiten as editor  # noqa: E402
from trainingsapp.ui.views.kurs_bearbeiten import (  # noqa: E402
    KEIN_KURSPLAN,
    kapitel_bearbeiten,
    kurs_bearbeiten,
    kurs_kopieren,
)


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/", views=[], update=lambda: None, dialoge=[])

    async def push_route(route: str) -> None:
        p.route = route

    p.push_route = push_route
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: p.dialoge.pop() if p.dialoge else None
    return p


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
        "actions",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text | ft.Markdown) and x.value]


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _hat(c, wert) -> bool:
    return any(getattr(x, "data", None) == wert for x in _alle(c))


def _waehlen(blatt, daten: str, wert: str) -> None:
    """Ein Auswahlfeld des Blatts stellen — wie ein Tipp auf die Option."""
    feld = _daten(blatt, daten)
    assert wert in [o.key for o in feld.options], (daten, wert, [o.key for o in feld.options])
    feld.value = wert
    feld.on_select()


def _speichern(ansicht) -> None:
    knopf = next(
        x
        for x in _alle(ansicht.appbar)
        if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    asyncio.run(knopf.on_click())


def _an(wert: bool) -> SimpleNamespace:
    return SimpleNamespace(control=SimpleNamespace(value=wert))


def _uebungen(state: AppState) -> dict[str, Exercise]:
    uebungen = {
        name: Exercise(name=name, result_spec=ResultSpec(fields=[vorrat_feld(feld)]))
        for name, feld in (
            ("Planke", "hold"),
            ("Seitstütz", "hold"),
            ("Käfer", "reps"),
            ("Brücke", "reps"),
        )
    }
    for u in uebungen.values():
        state.uebungen.speichern(u)
    return uebungen


def _kurs(state: AppState) -> tuple[Kurs, dict[str, Exercise]]:
    """Ein eigener Kurs mit Kursplan (Grundlage: Planke) und zwei Kapiteln wie in den Skizzen:
    Kapitel 2 hängt die gewählte Übung hinter die Planke des ersten, mit Ziel aus dem Test und
    einem Weg dorthin."""
    u = _uebungen(state)
    eins = Kapitel(
        titel="Grundlage",
        bloecke=[
            Block(TEXT, id="t1", titel="Die Planke", text="Sie hält den Rumpf still."),
            Block(PLAN_UEBUNG, id="b1", uebung=u["Seitstütz"].id, ziel={"hold": [40]}),
        ],
    )
    zwei = Kapitel(
        titel="Erweiterung",
        bloecke=[
            Block(AUSWAHL, id="w", uebungen=[u["Käfer"].id, u["Brücke"].id], anzahl=1),
            Block(TEST, id="t", uebung=u["Käfer"].id, feld="reps"),
            Block(PLAN_UEBUNG, id="b2", aus="w", hinter="b1", ziel_aus="t", faktor=0.5),
            Block(PLAN_WEG, id="b3", von="b1", zu="b2", kante={"ausloeser": "zeit"}),
            Block(PLAN_EINSTELLEN, id="b4", an="g:1", ziel={"hold": [75]}),
        ],
    )
    kurs = Kurs(
        name="Rumpf-Kurs",
        kapitel=[eins, zwei],
        kursplan=Kursplan(
            "Rumpf", [0, 2, 4], vorlage=PlanVorlage("Basis", items=[VorlageItem(u["Planke"].id)])
        ),
    )
    state.kurse.speichern(kurs)
    return state.kurse.laden(kurs.id), u


def _paketpruefung(state: AppState, kurs: Kurs) -> tuple[list[str], list[str]]:
    """Der Kurs als Paketdatei (`core.pakete.kurs_stand`) durch die Prüfung des Paketwerkzeugs
    — ``(Fehler, Hinweise)`` zu Kursplan und Bausteinen (`paket_werkzeug.kursplan_pruefen`). Was
    der Editor baut, muss sie ohne Fehler annehmen: Sonst ließe sich ein eigener Kurs nicht als
    Paket weitergeben."""
    roh = {
        "paket": {"name": "Prüfpaket"},
        "exercises": [
            {"key": u.id, "name": u.name} for u in state.uebungen.alle(mit_archivierten=True)
        ],
        "kurse": [kurs_stand(kurs)],
    }
    return kursplan_pruefen(roh, paket_lesen(roh))


def test_doctests_des_editors() -> None:
    """Die Doctests der Ansicht (`antworten_text`, `block_kurz` …) — die CI fährt Doctests nur
    für `core/` und `devices/`; die der Rechenlogik laufen dort mit (`core/kursbau.py`)."""
    ergebnis = doctest.testmod(editor)
    assert ergebnis.attempted > 0 and ergebnis.failed == 0


# -- Kurs bearbeiten: „Der Kurs baut einen Plan“ ---------------------------------------------


def test_kursplan_einschalten_name_tage_und_vorlage(page, state) -> None:
    u = _uebungen(state)
    plan = Plan(name="Rumpf Basis", subject_id=state.profil.id, wochentage=[0, 2, 4])
    state.plaene.speichern(plan)
    state.plaene.uebung_hinzufuegen(plan.id, u["Planke"].id)
    state.plaene.uebung_hinzufuegen(plan.id, u["Käfer"].id)
    kurs = editor.kurs_anlegen(state)
    ansicht = kurs_bearbeiten(page, state, kurs)
    # Aus ist die Vorgabe — ein Kurs ohne Kursplan zeigt nur den Schalter und die Erklärung
    assert _daten(ansicht, "kursplan_an").value is False
    assert not _hat(ansicht, "kursplan_name")

    _daten(ansicht, "kursplan_an").on_change(_an(True))
    gespeichert = state.kurse.laden(kurs.id).kursplan
    assert gespeichert is not None and gespeichert.vorlage is None
    assert gespeichert.wochentage == list(range(7))
    assert "leer — der Plan beginnt ohne Übungen" in _texte(ansicht)

    name = _daten(ansicht, "kursplan_name")
    name.value = "  Mein  Rumpf "
    name.on_blur(SimpleNamespace(control=name))
    assert state.kurse.laden(kurs.id).kursplan.name == "Mein Rumpf"

    # Die Grundlage: einer der eigenen Pläne — als Vorlage im Kurs, mit seinen Tagen
    _daten(ansicht, "kursplan_vorlage").on_click()
    _daten(page.dialoge[-1], ("kursplan_plan", plan.id)).on_click()
    gespeichert = state.kurse.laden(kurs.id).kursplan
    assert [i.exercise_id for i in gespeichert.vorlage.items] == [u["Planke"].id, u["Käfer"].id]
    assert gespeichert.wochentage == [0, 2, 4]
    assert "Planke  ·  Käfer" in _texte(ansicht)
    _daten(ansicht, ("kursplan_tag", 5)).on_click()
    assert state.kurse.laden(kurs.id).kursplan.wochentage == [0, 2, 4, 5]

    # Ohne Bausteine geht die Grundlage ohne Rückfrage wieder weg
    dialoge = len(page.dialoge)
    _daten(ansicht, "kursplan_vorlage_weg").on_click()
    assert len(page.dialoge) == dialoge
    assert state.kurse.laden(kurs.id).kursplan.vorlage is None


def test_kursplan_ausschalten_fragt_bei_bausteinen(page, state) -> None:
    kurs, _ = _kurs(state)
    profil = state.profil.id
    state.kurse.starten(kurs, profil)  # die Grundlage hat Übungen: Der Kursplan entsteht
    plan = state.kurse.kursplan(kurs, profil)
    assert plan is not None and plan.aktiv
    ansicht = kurs_bearbeiten(page, state, kurs)
    assert _daten(ansicht, "kursplan_an").value is True
    assert "1 Block  ·  1 am Plan  ·  gelesen" in _texte(ansicht)

    _daten(ansicht, "kursplan_an").on_change(_an(False))
    frage = page.dialoge[-1]
    assert frage.title.value == "Keinen Plan mehr bauen?"
    assert "stehen 4 Bausteine" in frage.content.value
    assert state.kurse.laden(kurs.id).kursplan is not None  # erst die Rückfrage
    _daten(frage, "kursplan_aus_nein").on_click()
    assert _daten(ansicht, "kursplan_an").value is True  # der Schalter steht wieder auf „an“

    _daten(ansicht, "kursplan_an").on_change(_an(False))
    _daten(page.dialoge[-1], "kursplan_aus_ja").on_click()
    danach = state.kurse.laden(kurs.id)
    assert danach.kursplan is None
    # Die Bausteine bleiben in den Kapiteln — sie bewirken nur nichts mehr
    assert [b.id for b in danach.kapitel[1].bloecke] == ["w", "t", "b2", "b3", "b4"]
    assert state.kurse.plan_aenderungen(danach, danach.kapitel[1], profil) == []
    # Der Kursplan, den es schon gibt, bleibt bestehen und aktiv — er wächst nur nicht weiter
    geblieben = state.plaene.laden(plan.id)
    assert geblieben is not None and geblieben.aktiv
    assert [i.exercise_id for i in geblieben.items] == [i.exercise_id for i in plan.items]


def test_grundlage_entfernen_fragt_und_nimmt_verweise_mit(page, state) -> None:
    """Ohne Grundlage gibt es `g:1` nicht mehr — der Baustein, der dort einstellt, bliebe sonst
    still hängen."""
    kurs, _ = _kurs(state)
    ansicht = kurs_bearbeiten(page, state, kurs)
    _daten(ansicht, "kursplan_vorlage_weg").on_click()
    frage = page.dialoge[-1]
    assert "• Erweiterung · Einstellen — Planke: Ziel 75 s: wird mit gelöscht" in _texte(frage)
    assert state.kurse.laden(kurs.id).kursplan.vorlage is not None
    _daten(frage, "kursplan_vorlage_ja").on_click()
    danach = state.kurse.laden(kurs.id)
    assert danach.kursplan.vorlage is None
    assert [b.id for b in danach.kapitel[1].bloecke] == ["w", "t", "b2", "b3"]


def test_kapitel_loeschen_nimmt_verweise_anderer_kapitel_mit(page, state) -> None:
    kurs, _ = _kurs(state)
    ansicht = kurs_bearbeiten(page, state, kurs)
    zeile = _daten(ansicht, ("kapitel", kurs.kapitel[0].id))
    next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Kapitel löschen").on_click()
    frage = page.dialoge[-1]
    texte = _texte(frage)
    assert (
        "• Erweiterung · Übung dazu — die gewählte, hinter Seitstütz · Ziel aus dem Test × 0,5: "
        "kommt ans Ende"
    ) in texte
    assert any(t.endswith("Zeit ab: wird mit gelöscht") for t in texte)
    _daten(frage, "kapitel_loeschen").on_click()
    (rest,) = state.kurse.laden(kurs.id).kapitel
    assert [(b.id, b.hinter) for b in rest.bloecke if b.art == PLAN_UEBUNG] == [("b2", "")]
    assert [b.id for b in rest.bloecke] == ["w", "t", "b2", "b4"]


# -- Kapitel bearbeiten: zwei Abschnitte, Bausteine -------------------------------------------


def test_kurs_mit_bausteinen_oeffnet_ohne_fehler(page, state) -> None:
    """Der Editor stürzte bei Bausteinen ab (`ARTEN[b.art]`). Jetzt stehen sie im Abschnitt „Am
    Plan“ mit Kurztext; ein Verweis ins Leere steht dabei."""
    kurs, _ = _kurs(state)
    kurs_bearbeiten(page, state, kurs)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])
    texte = _texte(ansicht)
    assert "IM KAPITEL — WAS MAN LIEST UND TUT" in texte and "AM PLAN — WAS SICH ÄNDERT" in texte
    for erwartet in (
        "Auswahl",
        "1 von 2 · Käfer, Brücke",
        "Übung dazu",
        "die gewählte, hinter Seitstütz · Ziel aus dem Test × 0,5",
        "Weg",
        "Seitstütz → die gewählte · Zeit ab",
        "Einstellen",
        "Planke: Ziel 75 s",
    ):
        assert erwartet in texte, erwartet
    assert not [t for t in texte if t.startswith("Verweis fehlt")]
    # Jede Zeile öffnet ihr Formular: Blöcke den Dialog, Bausteine das Blatt
    _daten(ansicht, ("block", "w")).on_click()
    assert isinstance(page.dialoge[-1], ft.AlertDialog)
    for block_id, titel in (
        ("b2", "Übung in den Plan"),
        ("b3", "Weg im Plan"),
        ("b4", "Am Plan einstellen"),
    ):
        _daten(ansicht, ("baustein", block_id)).on_click()
        blatt = page.dialoge[-1]
        assert isinstance(blatt, ft.BottomSheet) and titel in _texte(blatt)

    # Kapitel vertauscht: Kapitel 2 steht jetzt vorn und nennt eine Übung, die erst später kommt
    kurs.kapitel.reverse()
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    uebersicht = kurs_bearbeiten(page, state, kurs)
    assert any(t.endswith("Verweis fehlt") for t in _texte(uebersicht))
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    assert "Verweis fehlt: Wohin" in _texte(ansicht) and "Verweis fehlt: Von" in _texte(ansicht)
    # Dieselben Stellen meldet die Paketprüfung — der Editor zeigt, was sie nicht annähme
    fehler, _ = _paketpruefung(state, kurs)
    assert len(fehler) == 2 and all("steht erst in Kapitel 2" in f for f in fehler)
    # Das Blatt bestätigt so einen Verweis nicht noch einmal: Es zeigt ihn und verlangt eine
    # neue Wahl — zur Wahl steht nur, was die Prüfung annimmt
    _daten(ansicht, ("baustein", "b2")).on_click()
    blatt = page.dialoge[-1]
    wohin = _daten(blatt, "baustein_hinter")
    assert [o.key for o in wohin.options] == [KEIN, "g:1", "b1"]
    assert wohin.options[-1].text == "hinter Seitstütz — fehlt hier"
    _daten(blatt, "baustein_uebernehmen").on_click()
    assert "Verweis fehlt: Wohin — bitte neu wählen." in _texte(blatt)
    _waehlen(blatt, "baustein_hinter", "g:1")
    assert [o.key for o in _daten(blatt, "baustein_hinter").options] == [KEIN, "g:1"]
    _daten(blatt, "baustein_uebernehmen").on_click()
    assert "die gewählte, hinter Planke · Ziel aus dem Test × 0,5" in _texte(ansicht)
    zeile = _daten(ansicht, ("baustein", "b3"))  # der Weg von b1 geht hier nicht: weg damit
    next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Entfernen").on_click()
    _speichern(ansicht)
    assert _paketpruefung(state, state.kurse.laden(kurs.id)) == ([], [])


def test_bausteine_ohne_kursplan_nur_mit_hinweis(page, state) -> None:
    kurs, _ = _kurs(state)
    kurs.kursplan = None
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])
    assert KEIN_KURSPLAN in _texte(ansicht)
    assert _hat(ansicht, "block_dazu") and not _hat(ansicht, "baustein_dazu")
    assert _hat(ansicht, ("baustein", "b2"))  # die vorhandenen stehen da und lassen sich öffnen
    _daten(ansicht, ("baustein", "b2")).on_click()
    assert any(t.startswith("Der Kurs baut keinen Plan") for t in _texte(page.dialoge[-1]))


def test_kurs_ohne_kursplan_wie_vorher(page, state) -> None:
    """Ohne Kursplan bleibt das Kapitel, wie es war: die fünf Blockarten, die Pläne des
    Kapitels, die Bedingung — und Test oder Auswahl brauchen weiter einen Kapitelplan."""
    u = _uebungen(state)
    kurs = editor.kurs_anlegen(state)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    for art in (TEXT, "medium", "frage", TEST, AUSWAHL):
        assert _hat(ansicht, ("block_neu", art))
    assert not _hat(ansicht, "baustein_dazu")
    assert not _hat(ansicht, ("baustein_neu", PLAN_UEBUNG))
    assert "Noch kein Block — das Kapitel zeigt nur seinen Titel." in _texte(ansicht)
    assert _hat(ansicht, "plan_uebernehmen") and _hat(ansicht, "bedingung_art")
    # Die Arten klappen unter „+ Im Kapitel“ auf und nach der Wahl wieder zu
    reihe = _daten(ansicht, ("block_neu", TEXT))
    arten = next(x for x in _alle(ansicht) if reihe in (getattr(x, "controls", None) or []))
    assert arten.visible is False
    _daten(ansicht, "block_dazu").on_click()
    assert arten.visible is True
    _daten(ansicht, ("block_neu", TEST)).on_click()
    assert arten.visible is False
    dialog = page.dialoge[-1]
    felder = {str(x.label): x for x in _alle(dialog) if isinstance(x, ft.TextField | ft.Dropdown)}
    assert "Ziel in % des Tests" in felder  # der Test wird Ziel im Kapitelplan
    felder["Übung"].value = u["Planke"].id
    felder["Übung"].on_select()
    _daten(dialog, "block_uebernehmen").on_click()
    _speichern(ansicht)
    assert "Test und Auswahl brauchen einen Plan im Kapitel." in _texte(ansicht)


def test_im_kursplan_kurs_brauchen_test_und_tage_keinen_kapitelplan(page, state) -> None:
    """Baut der Kurs einen Plan, liefern Test und Auswahl nur Wert und Wahl, und „Tage“ zählt
    die Übungen des Kursplans (`KursRepo.stand`) — ein Kapitelplan ist nicht nötig."""
    kurs, _ = _kurs(state)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])
    _daten(ansicht, ("block", "t")).on_click()
    felder = {
        str(x.label): x
        for x in _alle(page.dialoge[-1])
        if isinstance(x, ft.TextField | ft.Dropdown)
    }
    assert "Ziel in % des Tests" not in felder
    _daten(ansicht, "bedingung_art").on_select(_an(TAGE))
    soll = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Tage")
    soll.value = "3"
    _speichern(ansicht)
    gespeichert = state.kurse.laden(kurs.id).kapitel[1]
    assert gespeichert.bedingung == Bedingung(art=TAGE, soll=3.0) and not gespeichert.plaene


def test_baustein_jeder_art_anlegen_speichern_wieder_oeffnen(page, state) -> None:
    kurs, _ = _kurs(state)
    kapitel = kurs.kapitel[1]
    kapitel.bloecke = kapitel.bloecke[:2]  # nur Auswahl und Test — die Bausteine entstehen hier
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])
    assert "Noch kein Baustein — dieses Kapitel ändert den Plan nicht." in _texte(ansicht)
    timer = state.timer_profile()[0]

    # 1. Übung in den Plan: die gewählte, hinter die Planke der Grundlage, Ziel aus dem Test
    _daten(ansicht, "baustein_dazu").on_click()
    _daten(ansicht, ("baustein_neu", PLAN_UEBUNG)).on_click()
    blatt = page.dialoge[-1]
    _daten(blatt, "baustein_uebernehmen").on_click()
    assert "Wähle eine Übung." in _texte(blatt)  # unvollständig bleibt im Blatt
    assert "Noch keine Zeile — dem Baustein fehlt etwas." in _texte(blatt)
    _waehlen(blatt, "baustein_uebung", "aus:w")
    _waehlen(blatt, "baustein_hinter", "g:1")
    assert "Käfer kommt dazu" in _texte(blatt) and "hinter Planke" in _texte(blatt)
    _waehlen(blatt, "baustein_ziel", "test:t")
    faktor = _daten(blatt, "baustein_faktor")
    faktor.value = "0,8"
    faktor.on_blur()
    assert "Ziel für Käfer: 24 Wiederholungen" in _texte(blatt)  # Beispielwert 30 × 0,8
    assert any(
        t.startswith("Beispiel mit der Wahl „Käfer“ und dem Testwert") for t in _texte(blatt)
    )
    _waehlen(blatt, "baustein_timer", f"t:{timer.id}")
    _daten(blatt, "baustein_uebernehmen").on_click()

    # 2. Am Plan einstellen: Übergang und Pause für den ganzen Plan
    _daten(ansicht, ("baustein_neu", PLAN_EINSTELLEN)).on_click()
    blatt = page.dialoge[-1]
    _daten(blatt, "baustein_uebernehmen").on_click()
    assert any(t.startswith("Stell mindestens eines ein") for t in _texte(blatt))
    _waehlen(blatt, "baustein_uebergang", HART)
    _waehlen(blatt, "baustein_pause", "aus")
    assert "Übergang im Workout: hart" in _texte(blatt)
    _daten(blatt, "baustein_uebernehmen").on_click()

    # 3. Noch eine Einstellung: ein festes Ziel und „nur abhaken“ an der gewählten Übung
    _daten(ansicht, ("baustein_neu", PLAN_EINSTELLEN)).on_click()
    blatt = page.dialoge[-1]
    _waehlen(blatt, "baustein_an", "uebung-1")
    _waehlen(blatt, "baustein_ziel", baustein_form.FEST)
    (zielfeld,) = [
        x for x in _alle(_daten(blatt, "baustein_zielwerte")) if isinstance(x, ft.TextField)
    ]
    zielfeld.value = "3x12"
    zielfeld.on_blur()
    assert "Ziel für Käfer: 3x12 Wiederholungen" in _texte(blatt)
    _waehlen(blatt, "baustein_parameter", baustein_form.ABHAKEN)
    _daten(blatt, "baustein_uebernehmen").on_click()

    # 4. Weg: von der Planke zur gewählten, nach 12 Wiederholungen, Pflicht, von selbst
    _daten(ansicht, ("baustein_neu", PLAN_WEG)).on_click()
    blatt = page.dialoge[-1]
    _daten(blatt, "baustein_uebernehmen").on_click()
    assert "Ein Weg braucht „Von“ und „Zu“." in _texte(blatt)
    _waehlen(blatt, "baustein_von", "g:1")
    _waehlen(blatt, "baustein_zu", "uebung-1")
    _daten(blatt, ("baustein_ausloeser", ab.WDH)).on_select()
    menge = _daten(blatt, "baustein_n")
    assert menge.value == "12"
    menge.value = "15"
    menge.on_change()
    _daten(blatt, "baustein_pflicht").on_change(_an(True))
    _daten(blatt, "baustein_selbst").on_change(
        SimpleNamespace(control=SimpleNamespace(selected=["ausfuehren"]))
    )
    assert "Von Planke weiter zu Käfer nach 15 Wdh." in _texte(blatt)
    _daten(blatt, "baustein_uebernehmen").on_click()

    # Vor dem Speichern steht nichts in der Datenbank
    assert len(state.kurse.laden(kurs.id).kapitel[1].bloecke) == 2
    _speichern(ansicht)
    kurs = state.kurse.laden(kurs.id)
    uebung, plan, einzeln, weg = kurs.kapitel[1].bloecke[2:]
    # Lesbare, feste IDs aus Art und laufender Nummer
    assert [b.id for b in (uebung, plan, einzeln, weg)] == [
        "uebung-1",
        "einstellen-1",
        "einstellen-2",
        "weg-1",
    ]
    assert (uebung.aus, uebung.uebung, uebung.hinter) == ("w", "", "g:1")
    assert (uebung.ziel_aus, uebung.faktor, uebung.ziel) == ("t", 0.8, {})
    assert uebung.timer["abschnitte"] == timer.als_dict()["abschnitte"]
    assert "bibliothek" not in uebung.timer  # eingebettet, ohne Verweis in die Bibliothek
    assert (plan.an, plan.uebergang, plan.pause_ohne_timer) == ("", HART, False)
    assert (einzeln.an, einzeln.ziel, einzeln.felder) == ("uebung-1", {"reps": [12, 12, 12]}, [])
    assert (weg.von, weg.zu) == ("g:1", "uebung-1")
    assert weg.kante == {"ausloeser": "wdh", "n": 15, "pflicht": True, "ausfuehren": True}
    # Was der Editor gebaut hat, nimmt die Paketprüfung an: IDs, Marken, Verweise
    assert _paketpruefung(state, kurs) == ([], [])

    # Wieder öffnen: Die Felder stehen, wie sie gespeichert wurden
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])
    _daten(ansicht, ("baustein", "uebung-1")).on_click()
    blatt = page.dialoge[-1]
    assert _daten(blatt, "baustein_uebung").value == "aus:w"
    assert _daten(blatt, "baustein_hinter").value == "g:1"
    assert _daten(blatt, "baustein_ziel").value == "test:t"
    assert _daten(blatt, "baustein_faktor").value == "0,8"
    assert _daten(blatt, "baustein_timer").value == f"t:{timer.id}"
    _daten(ansicht, ("baustein", "einstellen-1")).on_click()
    blatt = page.dialoge[-1]
    assert _daten(blatt, "baustein_an").value == KEIN
    assert _daten(blatt, "baustein_uebergang").value == HART
    assert _daten(blatt, "baustein_pause").value == "aus"
    _daten(ansicht, ("baustein", "einstellen-2")).on_click()
    blatt = page.dialoge[-1]
    assert _daten(blatt, "baustein_an").value == "uebung-1"
    assert _daten(blatt, "baustein_ziel").value == baustein_form.FEST
    assert _daten(blatt, "baustein_parameter").value == baustein_form.ABHAKEN
    (zielfeld,) = [
        x for x in _alle(_daten(blatt, "baustein_zielwerte")) if isinstance(x, ft.TextField)
    ]
    assert zielfeld.value == "3x12"
    _daten(ansicht, ("baustein", "weg-1")).on_click()
    blatt = page.dialoge[-1]
    assert _daten(blatt, "baustein_von").value == "g:1"
    assert _daten(blatt, "baustein_zu").value == "uebung-1"
    assert _daten(blatt, ("baustein_ausloeser", ab.WDH)).selected is True
    assert _daten(blatt, "baustein_n").value == "15"
    assert _daten(blatt, "baustein_pflicht").value is True
    assert _daten(blatt, "baustein_selbst").selected == ["ausfuehren"]


def test_abbrechen_im_blatt_aendert_nichts(page, state) -> None:
    kurs, _ = _kurs(state)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])
    _daten(ansicht, ("baustein", "b2")).on_click()
    blatt = page.dialoge[-1]
    _waehlen(blatt, "baustein_hinter", KEIN)
    assert "ans Ende" in _texte(blatt)  # die Vorschau folgt dem Entwurf
    _daten(blatt, "baustein_abbrechen").on_click()
    assert "die gewählte, hinter Seitstütz · Ziel aus dem Test × 0,5" in _texte(ansicht)
    _speichern(ansicht)
    assert state.kurse.laden(kurs.id).kapitel[1].bloecke[2].hinter == "b1"


def test_vorschau_zeigt_die_texte_der_karte(page, state) -> None:
    """„So steht es in der Karte“ nennt dieselben Zeilen wie `KursRepo.plan_aenderungen` — für
    eine Person, die Kapitel 1 übernommen, wie im Beispiel gewählt und getestet hat."""
    kurs, u = _kurs(state)
    profil = state.profil.id
    eins, zwei = kurs.kapitel
    # Kapitel 1: gegen die Grundlage, ohne Wahl und Test — gleich nach dem Speichern
    ansicht = kapitel_bearbeiten(page, state, kurs, eins)
    _daten(ansicht, ("baustein", "b1")).on_click()
    vorschau = _texte(_daten(page.dialoge[-1], "baustein_vorschau"))
    karte = state.kurse.plan_aenderungen(kurs, eins, profil)
    assert [z.titel for z in karte] == ["Seitstütz kommt dazu", "Ziel für Seitstütz: 40 s"]
    for z in karte:
        assert z.titel in vorschau and z.unter in vorschau

    # Kapitel 2: Die Person hat Kapitel 1 übernommen, Käfer gewählt und 30 Wiederholungen getestet
    state.kurse.starten(kurs, profil)
    state.kurse.plan_uebernehmen(kurs, eins, profil, {z.id for z in karte})
    state.kurse.kapitel_abschliessen(kurs, eins, profil)
    session = Session(subject_id=profil)
    state.sitzungen.anlegen(session)
    state.sitzungen.eintrag_anlegen(session, u["Käfer"], {"reps": [30]})
    wahl = {"w": [u["Käfer"].id]}
    karte = state.kurse.plan_aenderungen(kurs, zwei, profil, wahl)
    assert [(z.block_id, z.titel, z.unter) for z in karte] == [
        ("b2", "Käfer kommt dazu", "hinter Seitstütz"),
        ("b2", "Ziel für Käfer: 15 Wiederholungen", "aus deinem Test"),
        ("b3", "Von Seitstütz weiter zu Käfer, wenn die Zeit ab ist", "aus dem Kurs"),
        ("b4", "Ziel für Planke: 75 s", "aus dem Kurs"),
    ]
    ansicht = kapitel_bearbeiten(page, state, kurs, zwei)
    for block_id in ("b2", "b3", "b4"):
        _daten(ansicht, ("baustein", block_id)).on_click()
        vorschau = _texte(_daten(page.dialoge[-1], "baustein_vorschau"))
        zeilen = [z for z in karte if z.block_id == block_id]
        assert zeilen
        for z in zeilen:
            assert z.titel in vorschau and z.unter in vorschau, (block_id, z.titel, vorschau)
        fremde = [z.titel for z in karte if z.block_id != block_id]
        assert not set(fremde) & set(vorschau)  # nur die Zeilen dieses Bausteins
    # … und als Ganzes: dieselbe Rechnung, dieselben Zeilen
    sicht = Kurssicht(kurs, zwei.id, zwei.bloecke, {x.id: x for x in u.values()})
    assert [(z.id, z.titel, z.unter, z.stand) for z in sicht.vorschau().zeilen] == [
        (z.id, z.titel, z.unter, z.stand) for z in karte
    ]


def test_ids_bleiben_und_kommen_nicht_wieder(page, state) -> None:
    """Die ID eines Bausteins steht als Marke im Plan — eine neue trifft nie eine, die es gab:
    nicht die eines hier gelöschten Bausteins, nicht eine, die ein Kursplan schon trägt."""
    kurs, u = _kurs(state)
    kurs.kapitel[0].bloecke.append(Block(PLAN_UEBUNG, id="uebung-4", uebung=u["Brücke"].id))
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    profil = state.profil.id
    # Ein Kursplan trägt die Marke eines Bausteins, den es im Kurs nicht mehr gibt
    state.kurse.starten(kurs, profil)
    plan = state.kurse.kursplan(kurs, profil)
    plan.items[0].kurs_marke = "uebung-9"
    state.plaene.speichern(plan)

    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])

    def neu(art: str) -> str:
        _daten(ansicht, ("baustein_neu", art)).on_click()
        blatt = page.dialoge[-1]
        if art == PLAN_UEBUNG:
            _waehlen(blatt, "baustein_uebung", f"u:{u['Käfer'].id}")
        else:
            _waehlen(blatt, "baustein_von", "b1")
            _waehlen(blatt, "baustein_zu", "ende")
        _daten(blatt, "baustein_uebernehmen").on_click()
        return blatt.data[1]

    assert neu(PLAN_UEBUNG) == "uebung-10"
    assert neu(PLAN_WEG) == "weg-1"
    # löschen und neu anlegen: die Nummer ist verbraucht
    zeile = _daten(ansicht, ("baustein", "weg-1"))
    next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Entfernen").on_click()
    assert not _hat(ansicht, ("baustein", "weg-1"))
    assert neu(PLAN_WEG) == "weg-2"
    # ein abgebrochenes Blatt verbraucht seine Nummer auch — sie stand schon im Blatt
    _daten(ansicht, ("baustein_neu", PLAN_WEG)).on_click()
    _daten(page.dialoge[-1], "baustein_abbrechen").on_click()
    assert neu(PLAN_WEG) == "weg-4"
    _speichern(ansicht)
    assert [b.id for b in state.kurse.laden(kurs.id).kapitel[0].bloecke] == [
        "t1",
        "b1",
        "uebung-4",
        "uebung-10",
        "weg-2",
        "weg-4",
    ]


def test_verschieben_bleibt_im_abschnitt(page, state) -> None:
    kurs, _ = _kurs(state)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])

    def schieben(daten, tooltip: str) -> None:
        zeile = _daten(ansicht, daten)
        knopf = next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == tooltip)
        assert not knopf.disabled
        knopf.on_click()

    erste = _daten(ansicht, ("baustein", "b2"))
    assert next(x for x in _alle(erste) if getattr(x, "tooltip", None) == "Nach oben").disabled
    schieben(("baustein", "b2"), "Nach unten")  # b2 hinter b3 — an der Auswahl und dem Test vorbei
    schieben(("block", "t"), "Nach oben")
    _speichern(ansicht)
    assert [b.id for b in state.kurse.laden(kurs.id).kapitel[1].bloecke] == [
        "t",
        "w",
        "b3",
        "b2",
        "b4",
    ]
    # Der Weg steht jetzt vor der Übung, zu der er führt — das sagt die Zeile
    ansicht = kapitel_bearbeiten(page, state, state.kurse.laden(kurs.id), kurs.kapitel[1])
    assert "Verweis fehlt: Zu" in _texte(ansicht)


# -- Löschen mit Verweisen ---------------------------------------------------------------------


def test_loeschen_mit_verweisen_fragt_und_leert(page, state) -> None:
    kurs, _ = _kurs(state)
    eins = kurs.kapitel[0]
    ansicht = kapitel_bearbeiten(page, state, kurs, eins)
    # b1 löschen — über das Blatt; die Rückfrage kommt, wenn das Blatt zu ist
    _daten(ansicht, ("baustein", "b1")).on_click()
    blatt = page.dialoge[-1]
    _daten(blatt, "baustein_loeschen").on_click()
    asyncio.run(blatt.on_dismiss(None))
    frage = page.dialoge[-1]
    assert frage.title.value == "„Übung dazu“ löschen?"
    texte = _texte(frage)
    assert "Darauf beziehen sich andere Bausteine:" in texte
    assert (
        "• Erweiterung · Übung dazu — die gewählte, hinter Seitstütz · Ziel aus dem Test × 0,5: "
        "kommt ans Ende"
    ) in texte
    assert "• Erweiterung · Weg — Seitstütz → die gewählte · Zeit ab: wird mit gelöscht" in texte
    # Abbrechen lässt alles, wie es war
    next(x for x in _alle(frage) if getattr(x, "content", None) == "Abbrechen").on_click()
    assert _hat(ansicht, ("baustein", "b1"))

    zeile = _daten(ansicht, ("baustein", "b1"))
    next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Entfernen").on_click()
    _daten(page.dialoge[-1], "block_loeschen_ja").on_click()
    assert not _hat(ansicht, ("baustein", "b1"))
    # … gilt erst mit „Speichern“: Das andere Kapitel ist noch unberührt
    assert [b.id for b in state.kurse.laden(kurs.id).kapitel[1].bloecke] == [
        "w",
        "t",
        "b2",
        "b3",
        "b4",
    ]
    _speichern(ansicht)
    danach = state.kurse.laden(kurs.id)
    assert [b.id for b in danach.kapitel[0].bloecke] == ["t1"]
    assert [b.id for b in danach.kapitel[1].bloecke] == ["w", "t", "b2", "b4"]
    assert danach.kapitel[1].bloecke[2].hinter == ""  # geleert: Die Übung kommt ans Ende

    # Im zweiten Kapitel: Der Test fällt weg — das Ziel daraus auch; die Auswahl fällt weg —
    # „die gewählte“ gibt es dann nicht mehr
    kurs = danach
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])
    zeile = _daten(ansicht, ("block", "t"))
    next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Entfernen").on_click()
    frage = page.dialoge[-1]
    assert any(t.endswith("verliert das Ziel aus dem Test") for t in _texte(frage))
    _daten(frage, "block_loeschen_ja").on_click()
    assert "die gewählte, ans Ende" in _texte(ansicht)
    zeile = _daten(ansicht, ("block", "w"))
    next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Entfernen").on_click()
    frage = page.dialoge[-1]
    assert "• Übung dazu — die gewählte, ans Ende: wird mit gelöscht" in _texte(frage)
    _daten(frage, "block_loeschen_ja").on_click()
    _speichern(ansicht)
    assert [b.id for b in state.kurse.laden(kurs.id).kapitel[1].bloecke] == ["b4"]


def test_loeschen_verwerfen_laesst_andere_kapitel(page, state) -> None:
    """„Abbrechen“ des Kapitel-Formulars verwirft auch, was das Löschen in anderen Kapiteln
    nach sich gezogen hätte."""
    kurs, _ = _kurs(state)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    zeile = _daten(ansicht, ("baustein", "b1"))
    next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Entfernen").on_click()
    _daten(page.dialoge[-1], "block_loeschen_ja").on_click()
    abbrechen = next(
        x for x in _alle(ansicht.appbar) if getattr(x, "tooltip", None) == "Abbrechen — verwirft"
    )
    asyncio.run(abbrechen.on_click())
    danach = state.kurse.laden(kurs.id)
    assert [b.id for b in danach.kapitel[0].bloecke] == ["t1", "b1"]
    assert [b.id for b in danach.kapitel[1].bloecke] == ["w", "t", "b2", "b3", "b4"]
    assert [b.id for b in kurs.kapitel[1].bloecke] == ["w", "t", "b2", "b3", "b4"]


# -- Kopie eines Kurses ------------------------------------------------------------------------


def test_kopie_schreibt_verweise_um(page, state) -> None:
    kurs, u = _kurs(state)
    profil = state.profil.id
    kopie = kurs_kopieren(state, kurs)
    assert kopie.id != kurs.id and kopie.package_id is None
    assert kopie.kursplan is not None and kopie.kursplan.name == "Rumpf"
    assert kopie.kursplan.wochentage == [0, 2, 4]
    assert [i.exercise_id for i in kopie.kursplan.vorlage.items] == [u["Planke"].id]

    alt = [b for k in kurs.kapitel for b in k.bloecke]
    neu = [b for k in kopie.kapitel for b in k.bloecke]
    assert [b.art for b in neu] == [b.art for b in alt]
    assert {b.id for b in neu}.isdisjoint({b.id for b in alt})
    ids = {a.id: n.id for a, n in zip(alt, neu, strict=True)}
    # Bausteine tragen lesbare IDs wie im Editor
    assert [ids[i] for i in ("b1", "b2", "b3", "b4")] == [
        "uebung-1",
        "uebung-2",
        "weg-1",
        "einstellen-1",
    ]
    uebung, weg, einstellen = neu[4], neu[5], neu[6]
    assert (uebung.aus, uebung.hinter, uebung.ziel_aus) == (ids["w"], "uebung-1", ids["t"])
    assert uebung.faktor == 0.5
    assert (weg.von, weg.zu, weg.kante) == ("uebung-1", "uebung-2", {"ausloeser": "zeit"})
    assert einstellen.an == "g:1"  # die Grundlage bleibt
    assert _paketpruefung(state, kopie) == ([], [])

    # Die Karte der Kopie sagt dasselbe wie die des Originals — in beiden Kapiteln
    def karte(k: Kurs, wahl_id: str) -> list[list[tuple[str, str, str]]]:
        ergebnis = []
        for kapitel in k.kapitel:
            zeilen = state.kurse.plan_aenderungen(k, kapitel, profil, {wahl_id: [u["Käfer"].id]})
            ergebnis.append([(z.titel, z.unter, z.stand) for z in zeilen])
            state.kurse.plan_uebernehmen(
                k, kapitel, profil, {z.id for z in zeilen}, wahl={wahl_id: [u["Käfer"].id]}
            )
        return ergebnis

    original = karte(kurs, "w")
    assert original[1][0] == ("Käfer kommt dazu", "hinter Seitstütz", "neu")
    assert karte(kopie, ids["w"]) == original
    # … und der Editor öffnet die Kopie
    ansicht = kapitel_bearbeiten(page, state, kopie, kopie.kapitel[1])
    assert "die gewählte, hinter Seitstütz · Ziel aus dem Test × 0,5" in _texte(ansicht)
    assert not [t for t in _texte(ansicht) if t.startswith("Verweis fehlt")]


def test_kopie_nimmt_die_grundlage_aus_dem_paket_als_vorlage() -> None:
    """Ein eigener Kurs gehört zu keinem Paket: Der Plan des Pakets, mit dem der Kursplan
    beginnt, kommt darum als Vorlage in die Kopie — sonst begänne er leer."""
    paketplan = PaketPlan("basis", PlanVorlage("Basis", items=[VorlageItem("a"), VorlageItem("b")]))
    gespeichert: list[Kurs] = []
    state = SimpleNamespace(
        pakete=SimpleNamespace(paketplaene=lambda paket_id: [paketplan] if paket_id == "p" else []),
        kurse=SimpleNamespace(speichern=gespeichert.append, laden=lambda _id: None),
    )
    kurs = Kurs(
        name="Aus dem Paket",
        package_id="p",
        kursplan=Kursplan("Rumpf", grundlage="basis"),
        kapitel=[Kapitel(bloecke=[Block(PLAN_EINSTELLEN, id="e", an="g:2", ziel={"hold": 30})])],
    )
    kopie = kurs_kopieren(state, kurs)
    assert gespeichert == [kopie] and kopie.package_id is None
    assert kopie.kursplan.grundlage == ""  # die Vorlage ersetzt den Verweis ins Paket
    assert [i.exercise_id for i in kopie.kursplan.vorlage.items] == ["a", "b"]
    assert kopie.kapitel[0].bloecke[0].an == "g:2"
    assert kurs.kursplan.vorlage is None  # das Original bleibt, wie es war
