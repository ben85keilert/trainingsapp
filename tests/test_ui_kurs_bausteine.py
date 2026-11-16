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
from dataclasses import replace
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core import ablauf as ab  # noqa: E402
from trainingsapp.core.eigenes_paket import noetige_uebungen  # noqa: E402
from trainingsapp.core.kursbau import (  # noqa: E402
    AB,
    HOECHSTENS,
    OHNE,
    VON_BIS,
    Kurssicht,
    timer_kern,
)
from trainingsapp.core.kursbloecke import (  # noqa: E402
    AUSWAHL,
    HART,
    MENGE,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    SKALA,
    TEST,
    TEXT,
    ZEIT,
    Block,
    Vorgabe,
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
from trainingsapp.core.kursplan import ZIEL  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, Session  # noqa: E402
from trainingsapp.core.pakete import (  # noqa: E402
    Paket,
    Paketinhalt,
    PaketPlan,
    kurs_stand,
    paket_bauen,
    paket_id,
    paket_lesen,
)
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.takt import AUS, VORLAGEN  # noqa: E402
from trainingsapp.core.timer import TimerProfil  # noqa: E402
from trainingsapp.paket_werkzeug import kursplan_pruefen  # noqa: E402
from trainingsapp.ui.components import baustein_form  # noqa: E402
from trainingsapp.ui.components.baustein_form import (  # noqa: E402
    ABHAKEN,
    EIGEN,
    KEIN,
    KEIN_TAKT,
    TAKT,
    WAEHLEN,
)
from trainingsapp.ui.components.kursplan_bild import KEIN_BAUSTEIN  # noqa: E402
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


def _daten_ids(c, art: str) -> list[str]:
    """Die IDs der Zeilen einer Art (``("block", <id>)``) in ihrer Reihenfolge."""
    return [
        x.data[1]
        for x in _alle(c)
        if isinstance(getattr(x, "data", None), tuple) and x.data[0] == art and len(x.data) == 2
    ]


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


def _rundreise(state: AppState, kurs: Kurs) -> tuple[dict, Paketinhalt, Paketinhalt]:
    """Der Kurs als eigenes Paket hinaus und wieder herein — wie beim Weitergeben: die Datei
    (`core.pakete.paket_bauen` mit den Übungen, die der Kurs braucht), gelesen, und noch einmal
    geschrieben und gelesen."""
    noetig = noetige_uebungen([], [kurs])
    uebungen = [u for u in state.uebungen.alle(mit_archivierten=True) if u.id in noetig]
    paket = Paket(id=paket_id("Prüfpaket"), name="Prüfpaket")
    roh = paket_bauen(paket, uebungen, kurse=[kurs], mit_zeitstempel=False)
    gebaut = paket_lesen(roh)
    wieder = paket_lesen(
        paket_bauen(gebaut.paket, gebaut.uebungen, kurse=gebaut.kurse, mit_zeitstempel=False)
    )
    return roh, gebaut, wieder


def _felder(dialog) -> dict[str, object]:
    """Textfelder und Auswahlfelder eines Dialogs nach ihrer Beschriftung."""
    return {
        str(x.label): x
        for x in _alle(dialog)
        if isinstance(x, ft.TextField | ft.Dropdown) and isinstance(x.label, str)
    }


def _parameter_knoepfe(blatt) -> list[str]:
    """Die Parameter-Knöpfe des Blatts in ihrer Reihenfolge (ohne die Chips der Zielmaske)."""
    return [
        x.data[1]
        for x in _alle(blatt)
        if isinstance(x, ft.Chip) and isinstance(x.data, tuple) and x.data[0] == "baustein_feld"
    ]


def _takt_uebernehmen(page) -> None:
    """Im Takt-Blatt, das über dem Baustein-Blatt aufgegangen ist, „Übernehmen“ — das Ziel
    läuft, sobald das Blatt zu ist."""
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    assert any(t.startswith("Takt · ") for t in _texte(blatt)), _texte(blatt)[:3]
    knopf = next(
        x for x in _alle(blatt) if isinstance(x, ft.FilledTonalButton) and x.content == "Übernehmen"
    )
    knopf.on_click()
    asyncio.run(blatt.on_dismiss(None))


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


def test_parameter_takt_und_eigener_timer(page, state) -> None:
    """Ben, 16.11.2026 („muss ebenfalls behoben werden“): Parameter, Takt und ein eigener Timer
    lassen sich am Baustein einstellen — mit den Knöpfen von „Im Plan einstellen“, dem
    Takt-Blatt und dem Timer-Editor. Anlegen, speichern, wieder öffnen: Die Werte stehen, und
    die Vorschau nennt die Zeilen der Karte."""
    kurs, _ = _kurs(state)
    profil = state.profil.id
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _daten(ansicht, ("baustein", "b1")).on_click()
    blatt = page.dialoge[-1]
    # Vorgabe: nichts davon gesetzt — die Planübung folgt der Übung
    assert [_daten(blatt, d).value for d in ("baustein_parameter", "baustein_timer")] == [KEIN] * 2
    assert _daten(blatt, "baustein_takt").value == KEIN
    assert not [t for t in _texte(blatt) if t.startswith("Bleibt, wie es im Kurs steht")]

    # Parameter: die der Übung als Knöpfe, darunter der übrige Feldvorrat
    _waehlen(blatt, "baustein_parameter", WAEHLEN)
    knoepfe = _parameter_knoepfe(blatt)
    assert knoepfe[0] == "hold" and knoepfe[1:4] == ["duration", "reps", "scale"]
    assert "Weitere Parameter holen" in _texte(blatt)
    assert "Kein Parameter gewählt — das heißt „nur abhaken“." in _texte(blatt)
    assert "Seitstütz: nur abhaken" in _texte(blatt)
    _daten(blatt, ("baustein_feld", "weight")).on_select()
    _daten(blatt, ("baustein_feld", "hold")).on_select()
    assert _daten(blatt, ("baustein_feld", "hold")).selected is True
    # … in der Ordnung des Angebots, nicht des Antippens
    assert "Parameter für Seitstütz: Haltezeit, Gewicht" in _texte(blatt)

    # Timer: ein eigener — der Timer-Editor steht im Blatt, jede Änderung gilt sofort
    _waehlen(blatt, "baustein_timer", EIGEN)
    assert _hat(blatt, "baustein_timer_editor")
    assert "Timer für Seitstütz: 0:30 Belastung · 0:15 Pause" in _texte(blatt)
    _daten(blatt, ("zaehlt", 0, 1)).on_click()  # die Pause zählt nicht

    # Takt: das Takt-Blatt geht über dem Blatt auf; bis „Übernehmen“ bleibt der Entwurf
    _waehlen(blatt, "baustein_takt", TAKT)
    assert _daten(blatt, "baustein_takt").value == KEIN
    _takt_uebernehmen(page)
    assert _daten(blatt, "baustein_takt").value == TAKT
    assert "Takt für Seitstütz: 4-6 · 6,0/min" in _texte(blatt)
    assert _hat(blatt, "baustein_timer_editor")  # der Editor steht noch — mit seinem Stand
    vorschau = _texte(_daten(blatt, "baustein_vorschau"))
    _daten(blatt, "baustein_uebernehmen").on_click()
    _speichern(ansicht)

    kurs = state.kurse.laden(kurs.id)
    b1 = kurs.kapitel[0].bloecke[1]
    assert b1.felder == ["hold", "weight"] and b1.takt == VORLAGEN["atmung_4_6"]
    eigen = TimerProfil.aus_dict(b1.timer)
    assert eigen is not None and eigen.id == "kurs-b1" and "bibliothek" not in b1.timer
    assert [(a.name, a.dauer_s, a.zaehlt) for a in eigen.abschnitte] == [
        ("Belastung", 30, True),
        ("Pause", 15, False),
    ]
    # Die Karte der Teilnehmenden nennt dieselben Zeilen wie die Vorschau
    karte = state.kurse.plan_aenderungen(kurs, kurs.kapitel[0], profil)
    assert [z.titel for z in karte] == [
        "Seitstütz kommt dazu",
        "Ziel für Seitstütz: 40 s",
        "Parameter für Seitstütz: Haltezeit, Gewicht",
        "Timer für Seitstütz: 0:30 Belastung · 0:15 Pause",
        "Takt für Seitstütz: 4-6 · 6,0/min",
    ]
    for z in karte:
        assert z.titel in vorschau and z.unter in vorschau

    # Wieder öffnen: Die Werte stehen; der eigene Timer ist zugeklappt, ✎ klappt ihn auf
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _daten(ansicht, ("baustein", "b1")).on_click()
    blatt = page.dialoge[-1]
    assert _daten(blatt, "baustein_parameter").value == WAEHLEN
    assert [
        k for k in ("reps", "hold", "weight") if _daten(blatt, ("baustein_feld", k)).selected
    ] == ["hold", "weight"]
    assert _daten(blatt, "baustein_timer").value == EIGEN
    assert _daten(blatt, "baustein_timer_kurz").value == "0:30 Belastung · 0:15 Pause · gesamt 0:45"
    assert not _hat(blatt, "baustein_timer_editor")
    _daten(blatt, "baustein_timer_editor_auf").on_click()
    assert _hat(blatt, "baustein_timer_editor")
    # der Editor zeigt den gespeicherten Stand: die Pause zählt nicht
    assert _daten(blatt, ("zaehlt", 0, 0)).tooltip.startswith("zählt als Übungszeit")
    assert _daten(blatt, ("zaehlt", 0, 1)).tooltip.startswith("zählt nicht als Übungszeit")
    assert _daten(blatt, "baustein_takt").value == TAKT

    # Die andere Richtung: ausdrücklich kein Takt, nur abhaken, ein Timer aus der Bibliothek
    _waehlen(blatt, "baustein_takt", KEIN_TAKT)
    assert "Takt für Seitstütz: kein Takt" in _texte(blatt)
    _waehlen(blatt, "baustein_parameter", ABHAKEN)
    assert "Seitstütz: nur abhaken" in _texte(blatt)
    timer = state.timer_profile()[0]
    _waehlen(blatt, "baustein_timer", f"t:{timer.id}")
    assert not _hat(blatt, "baustein_timer_kurz")
    _daten(blatt, "baustein_uebernehmen").on_click()
    _speichern(ansicht)
    kurs = state.kurse.laden(kurs.id)
    b1 = kurs.kapitel[0].bloecke[1]
    assert (b1.felder, b1.takt, b1.timer["id"]) == ([], AUS, timer.id)

    # … und zurück auf „wie die Übung“: keine Angabe, keine Zeile
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _daten(ansicht, ("baustein", "b1")).on_click()
    blatt = page.dialoge[-1]
    assert _daten(blatt, "baustein_takt").value == KEIN_TAKT
    assert _daten(blatt, "baustein_parameter").value == ABHAKEN
    _waehlen(blatt, "baustein_takt", KEIN)
    _waehlen(blatt, "baustein_parameter", KEIN)
    _waehlen(blatt, "baustein_timer", KEIN)
    _daten(blatt, "baustein_uebernehmen").on_click()
    _speichern(ansicht)
    b1 = state.kurse.laden(kurs.id).kapitel[0].bloecke[1]
    assert (b1.felder, b1.takt, b1.timer) == (None, None, {})


def test_einstellungen_an_der_gewaehlten_und_am_plan_gehen_durch_das_paket(page, state) -> None:
    """„Die gewählte“ kann mehrere Übungen sein: Zur Wahl stehen die Parameter aller. Am Plan
    gibt es Timer und Takt „für alle Übungen“. Was der Editor so baut, nimmt die Paketprüfung
    an und übersteht die Rundreise als eigenes Paket."""
    kurs, _ = _kurs(state)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])
    _daten(ansicht, ("baustein", "b2")).on_click()
    blatt = page.dialoge[-1]
    _waehlen(blatt, "baustein_parameter", WAEHLEN)
    knoepfe = _parameter_knoepfe(blatt)
    # Käfer und Brücke zählen Wiederholungen — das ist ihr Parameter; der Rest ist Vorrat
    assert knoepfe[:3] == ["reps", "duration", "hold"]
    _daten(blatt, ("baustein_feld", "scale")).on_select()
    _daten(blatt, ("baustein_feld", "reps")).on_select()
    _waehlen(blatt, "baustein_timer", EIGEN)
    _waehlen(blatt, "baustein_takt", TAKT)
    _takt_uebernehmen(page)
    for erwartet in (
        "Parameter für Käfer: Wiederholungen, Skala 0–10",
        "Timer für Käfer: 0:30 Belastung · 0:15 Pause",
        "Takt für Käfer: 4-6 · 6,0/min",
    ):
        assert erwartet in _texte(blatt), erwartet
    _daten(blatt, "baustein_uebernehmen").on_click()

    # Am Plan: Timer und Takt für alle Übungen — Parameter gehören zu einer Übung
    _daten(ansicht, ("baustein_neu", PLAN_EINSTELLEN)).on_click()
    blatt = page.dialoge[-1]
    assert not _hat(blatt, "baustein_parameter")
    _waehlen(blatt, "baustein_timer", EIGEN)
    _waehlen(blatt, "baustein_takt", TAKT)
    _takt_uebernehmen(page)
    assert "Timer für alle Übungen: 0:30 Belastung · 0:15 Pause" in _texte(blatt)
    assert "Takt für alle Übungen: 4-6 · 6,0/min" in _texte(blatt)
    _daten(blatt, "baustein_uebernehmen").on_click()
    _speichern(ansicht)

    kurs = state.kurse.laden(kurs.id)
    b2, am_plan = kurs.kapitel[1].bloecke[2], kurs.kapitel[1].bloecke[-1]
    assert (b2.id, b2.felder, b2.timer["id"]) == ("b2", ["reps", "scale"], "kurs-b2")
    assert b2.takt == VORLAGEN["atmung_4_6"]
    assert (am_plan.id, am_plan.an, am_plan.timer["id"]) == (
        "einstellen-1",
        "",
        "kurs-einstellen-1",
    )
    assert am_plan.takt == VORLAGEN["atmung_4_6"] and am_plan.felder is None

    # Paketprüfung und Rundreise: hinaus, herein, noch einmal — derselbe Kurs
    assert _paketpruefung(state, kurs) == ([], [])
    roh, gebaut, wieder = _rundreise(state, kurs)
    assert kursplan_pruefen(roh, gebaut) == ([], [])
    (gelesen,) = gebaut.kurse
    assert [kurs_stand(k) for k in wieder.kurse] == [kurs_stand(gelesen)]

    def angaben(k: Kurs) -> list[tuple]:
        return [
            (b.id, b.felder, b.takt, timer_kern(b.timer))
            for kapitel in k.kapitel
            for b in kapitel.bloecke
            if b.baustein
        ]

    assert angaben(gelesen) == angaben(kurs)
    assert [b for b in angaben(gelesen) if b[0] in ("b2", "einstellen-1")] == [
        ("b2", ["reps", "scale"], VORLAGEN["atmung_4_6"], timer_kern(b2.timer)),
        ("einstellen-1", None, VORLAGEN["atmung_4_6"], timer_kern(am_plan.timer)),
    ]
    assert gelesen.kapitel[1].bloecke[2].timer["id"] == "kurs-b2"  # die ID des eigenen bleibt


def test_test_misst_die_gewaehlte(page, state) -> None:
    """Ben, 16.11.2026 („muss behoben werden“): Der Test-Dialog bietet neben den Übungen des
    Katalogs „die gewählte aus ‹Auswahl›“ an — aus diesem Kapitel (auch ungespeichert) und
    früheren. Gespeichert wird ``aus``, die feste Übung ist dann leer. Anlegen, speichern,
    wieder öffnen; die Vorschau eines Bausteins mit Ziel aus diesem Test nimmt die
    Beispielübung; Löschen der Auswahl nennt den Test; Paketprüfung und Rundreise."""
    kurs, u = _kurs(state)
    profil = state.profil.id
    eins, zwei = kurs.kapitel
    ansicht = kapitel_bearbeiten(page, state, kurs, zwei)
    assert "Käfer · Wiederholungen" in _texte(ansicht)

    # Eine weitere Auswahl, noch ungespeichert: Planke oder Käfer — ohne gemeinsames Feld
    _daten(ansicht, ("block_neu", AUSWAHL)).on_click()
    dialog = page.dialoge[-1]
    dazu = _felder(dialog)["Übung zur Auswahl hinzufügen"]
    for name in ("Planke", "Käfer"):
        dazu.value = u[name].id
        dazu.on_select()
    _felder(dialog)["Aufforderung (leer = Vorgabe)"].value = "Halten oder zählen"
    _daten(dialog, "block_uebernehmen").on_click()
    neue_wahl = next(b for b in _daten_ids(ansicht, "block") if b not in ("w", "t"))

    # Der Test-Dialog: die Übungen des Katalogs — davor „die gewählte aus …“, beide Auswahlen
    _daten(ansicht, ("block", "t")).on_click()
    dialog = page.dialoge[-1]
    uebung = _felder(dialog)["Übung"]
    assert uebung.value == u["Käfer"].id
    angebot = {o.key: o.text for o in uebung.options}
    assert [k for k in angebot if k.startswith("aus:")] == ["aus:w", f"aus:{neue_wahl}"]
    assert angebot["aus:w"] == "die gewählte aus „1 von 2: Käfer, Brücke“"
    assert angebot[f"aus:{neue_wahl}"] == "die gewählte aus „Halten oder zählen“"
    assert "Ziel in % des Tests" not in _felder(dialog)  # Kursplan: Der Baustein sagt es
    hinweis = next(
        x for x in _alle(dialog) if isinstance(x, ft.Text) and "kein gemeinsames Feld" in x.value
    )
    assert hinweis.visible is False
    # ohne gemeinsames Feld: was wenigstens eine der Übungen hat — und der Hinweis dazu
    uebung.value = f"aus:{neue_wahl}"
    uebung.on_select()
    feld = _felder(dialog)["Was wird gemessen"]
    assert [o.key for o in feld.options] == ["reps", "hold"] and hinweis.visible is True
    # Käfer und Brücke zählen beide Wiederholungen
    uebung.value = "aus:w"
    uebung.on_select()
    assert [o.key for o in feld.options] == ["reps"] and feld.value == "reps"
    assert hinweis.visible is False
    _daten(dialog, "block_uebernehmen").on_click()
    assert "die gewählte · Wiederholungen" in _texte(ansicht)

    # Der Baustein mit dem Ziel aus diesem Test: die Vorschau nimmt die Beispielübung
    _daten(ansicht, ("baustein", "b2")).on_click()
    blatt = page.dialoge[-1]
    assert _daten(blatt, "baustein_ziel").value == "test:t"
    assert dict((o.key, o.text) for o in _daten(blatt, "baustein_ziel").options)["test:t"] == (
        "aus dem Test „die gewählte“"
    )
    vorschau = _texte(_daten(blatt, "baustein_vorschau"))
    assert "Ziel für Käfer: 15 Wiederholungen" in vorschau  # 30 Wiederholungen × 0,5
    assert any(
        t.startswith("Beispiel mit der Wahl „Käfer“ und dem Testwert 30 Wiederholungen.")
        for t in vorschau
    )
    _daten(blatt, "baustein_abbrechen").on_click()
    _speichern(ansicht)

    kurs = state.kurse.laden(kurs.id)
    eins, zwei = kurs.kapitel
    test = next(b for b in zwei.bloecke if b.id == "t")
    assert (test.aus, test.uebung, test.feld) == ("w", "", "reps")
    # Wieder öffnen: „die gewählte“ steht
    ansicht = kapitel_bearbeiten(page, state, kurs, zwei)
    _daten(ansicht, ("block", "t")).on_click()
    assert _felder(page.dialoge[-1])["Übung"].value == "aus:w"
    assert _felder(page.dialoge[-1])["Was wird gemessen"].value == "reps"

    # Paketprüfung und Rundreise (ein Test mit „aus“ braucht Formatversion 6)
    assert _paketpruefung(state, kurs) == ([], [])
    roh, gebaut, wieder = _rundreise(state, kurs)
    assert roh["version"] == 6 and kursplan_pruefen(roh, gebaut) == ([], [])
    (gelesen,) = gebaut.kurse
    assert [kurs_stand(k) for k in wieder.kurse] == [kurs_stand(gelesen)]
    assert [(b.aus, b.uebung) for b in gelesen.kapitel[1].bloecke if b.art == TEST] == [("w", "")]

    # Die Kopie schreibt „aus“ um
    kopie = kurs_kopieren(state, kurs)
    ids = {
        a.id: n.id
        for ka, kn in zip(kurs.kapitel, kopie.kapitel, strict=True)
        for a, n in zip(ka.bloecke, kn.bloecke, strict=True)
    }
    kopierter = next(b for b in kopie.kapitel[1].bloecke if b.id == ids["t"])
    assert (kopierter.aus, kopierter.uebung) == (ids["w"], "") and ids["w"] != "w"
    assert _paketpruefung(state, kopie) == ([], [])

    # Die Karte: Wer Käfer wählt und 30 Wiederholungen testet, sieht die Zeile der Vorschau
    state.kurse.starten(kurs, profil)
    karte = state.kurse.plan_aenderungen(kurs, eins, profil)
    state.kurse.plan_uebernehmen(kurs, eins, profil, {z.id for z in karte})
    state.kurse.kapitel_abschliessen(kurs, eins, profil)
    session = Session(subject_id=profil)
    state.sitzungen.anlegen(session)
    state.sitzungen.eintrag_anlegen(session, u["Käfer"], {"reps": [30]})
    karte = state.kurse.plan_aenderungen(kurs, zwei, profil, {"w": [u["Käfer"].id]})
    assert [(z.titel, z.unter) for z in karte][:2] == [
        ("Käfer kommt dazu", "hinter Seitstütz"),
        ("Ziel für Käfer: 15 Wiederholungen", "50 % von deinem Test (30 Wdh.)"),
    ]
    for z in karte[:2]:
        assert z.titel in vorschau and z.unter in vorschau

    # Die Auswahl löschen: Die Rückfrage nennt den Test — ohne sie hätte er keine Übung
    zeile = _daten(ansicht, ("block", "w"))
    next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Entfernen").on_click()
    frage = page.dialoge[-1]
    texte = _texte(frage)
    assert "Darauf beziehen sich andere Blöcke:" in texte
    assert "• Test — die gewählte · Wiederholungen: wird mit gelöscht" in texte
    assert any(t.startswith("• Übung dazu — die gewählte, hinter Seitstütz") for t in texte)
    _daten(frage, "block_loeschen_ja").on_click()
    assert not _hat(ansicht, ("block", "t")) and not _hat(ansicht, ("baustein", "b2"))
    _speichern(ansicht)
    geblieben = [b.id for b in state.kurse.laden(kurs.id).kapitel[1].bloecke]
    assert "t" not in geblieben and "w" not in geblieben and "b4" in geblieben


def test_test_misst_die_gewaehlte_auch_mit_kapitelplan(page, state) -> None:
    """Ohne Kursplan gilt dasselbe: Der Test darf „die gewählte“ messen; ihr Wert wird ihr Ziel
    im Kapitelplan (`core.kursbloecke.vorlage_anwenden`) — „Ziel in %“ bleibt dort stehen."""
    u = _uebungen(state)
    plan = Plan(name="Rumpf", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    state.plaene.uebung_hinzufuegen(plan.id, u["Planke"].id)
    kurs = editor.kurs_anlegen(state)
    kapitel = kurs.kapitel[0]
    kapitel.plaene = [PlanVorlage("Rumpf", items=[VorlageItem(u["Planke"].id)])]
    kapitel.bloecke = [Block(AUSWAHL, id="w", uebungen=[u["Käfer"].id, u["Brücke"].id])]
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    _daten(ansicht, ("block_neu", TEST)).on_click()
    dialog = page.dialoge[-1]
    _daten(dialog, "block_uebernehmen").on_click()
    assert "Ein Test braucht eine Übung." in _texte(dialog)
    felder = _felder(dialog)
    felder["Übung"].value = "aus:w"
    felder["Übung"].on_select()
    assert felder["Was wird gemessen"].value == "reps"
    felder["Ziel in % des Tests"].value = "80"
    _daten(dialog, "block_uebernehmen").on_click()
    assert "die gewählte — wird Ziel im Plan (80 %)" in _texte(ansicht)
    _felder(ansicht)["Titel"].value = "Rumpf"
    _speichern(ansicht)
    test = state.kurse.laden(kurs.id).kapitel[0].bloecke[1]
    assert (test.art, test.aus, test.uebung, test.feld, test.faktor) == (
        TEST,
        "w",
        "",
        "reps",
        0.8,
    )


# -- Der Test mit Vorgabe (Skizze T5) ----------------------------------------------------------


def _test_oeffnen(page, ansicht, block_id: str = "t"):
    """Der Dialog des Tests ``block_id`` im Kapitel-Formular."""
    _daten(ansicht, ("block", block_id)).on_click()
    dialog = page.dialoge[-1]
    assert isinstance(dialog, ft.AlertDialog) and dialog.title.value == "Test"
    return dialog


def _vorgabe(dialog, art: str) -> None:
    """Ein Tipp auf einen der vier Knöpfe unter „Vorgabe — wann der Test endet“."""
    _daten(dialog, ("test_vorgabe", art)).on_select()


def _zu_sehen(wurzel, ziel) -> bool:
    """Ist ``ziel`` unter ``wurzel`` zu sehen — es selbst und alles, worin es steckt?"""

    def suche(c, sichtbar: bool) -> bool | None:
        sichtbar = sichtbar and c.visible is not False
        if c is ziel:
            return sichtbar
        for name in ("content", "controls"):
            kind = getattr(c, name, None)
            for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
                if isinstance(k, ft.BaseControl) and (gefunden := suche(k, sichtbar)) is not None:
                    return gefunden
        return None

    return bool(suche(wurzel, True))


def _gewaehlt(dialog, kennung: str) -> list[str]:
    """Welche Knöpfe einer Reihe gewählt sind (``(kennung, <wert>)``)."""
    return [
        x.data[1]
        for x in _alle(dialog)
        if isinstance(x, ft.Chip)
        and isinstance(x.data, tuple)
        and x.data[0] == kennung
        and x.selected
    ]


def _zeit_stellen(page, dialog, text: str) -> None:
    """Die Zeit der Vorgabe im Blatt für jede Zeit, das über dem Dialog aufgeht: eintippen,
    „Übernehmen“ — gestellt ist, sobald das Blatt zu ist."""
    _daten(dialog, "test_zeit").on_click()
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet) and "Zeit stellen" in _texte(blatt)
    feld = next(x for x in _alle(blatt) if isinstance(x, ft.TextField))
    feld.value = text
    knopf = next(
        x for x in _alle(blatt) if isinstance(x, ft.FilledButton) and x.content == "Übernehmen"
    )
    knopf.on_click()
    asyncio.run(blatt.on_dismiss(None))


def _test_im_kurs(state: AppState, kurs: Kurs, block_id: str = "t") -> Block:
    return next(
        b for k in state.kurse.laden(kurs.id).kapitel for b in k.bloecke if b.id == block_id
    )


def test_test_dialog_ohne_vorgabe_wie_bisher(page, state) -> None:
    """Ohne Vorgabe steht der Dialog da wie bisher — dazu die Wahl, auf „Ohne“: kein „Gemessen
    wird“, keine Vorschau, das Feld heißt „Was wird gemessen“, und der Block bleibt ohne."""
    kurs, _ = _kurs(state)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])
    dialog = _test_oeffnen(page, ansicht)
    assert "VORGABE — WANN DER TEST ENDET" in _texte(dialog)
    assert _daten_ids(dialog, "test_vorgabe") == [OHNE, MENGE, ZEIT, SKALA]
    assert _gewaehlt(dialog, "test_vorgabe") == [OHNE]
    feld = _daten(dialog, "test_feld")
    assert (feld.label, feld.value) == ("Was wird gemessen", "reps")
    for teil in (
        "test_gemessen",
        "test_vorschau",
        "test_menge",
        "test_zeit",
        ("test_skala_form", AB),
        ("test_skala_wert", AB),
    ):
        assert not _zu_sehen(dialog, _daten(dialog, teil)), teil
    assert _zu_sehen(dialog, feld)
    _daten(dialog, "block_uebernehmen").on_click()
    assert "Käfer · Wiederholungen" in _texte(ansicht)
    _speichern(ansicht)
    assert _test_im_kurs(state, kurs).vorgabe is None


def test_test_mit_vorgabe_einstellen_speichern_wieder_oeffnen(page, state) -> None:
    """Ben, 16.11.2026 (Skizze T5): Die Autorin gibt dem Test eine Vorgabe — Menge, Zeit oder
    Anstrengung (ab · höchstens · von–bis). Jede lässt sich einstellen und speichern (der Block
    trägt die `Vorgabe`), steht nach dem Öffnen wieder so da, und „Ohne“ nimmt sie wieder weg.
    Dazu: was gemessen wird, die Zeile der Liste, die Vorschau „So steht es im Kapitel“ mit der
    Zeile der Sammelkarte, wie `Kurssicht.vorschau` sie liefert."""
    kurs, u = _kurs(state)
    zwei = kurs.kapitel[1]

    def oeffnen() -> tuple[ft.View, ft.AlertDialog]:
        frisch = state.kurse.laden(kurs.id)
        ansicht = kapitel_bearbeiten(page, state, frisch, frisch.kapitel[1])
        return ansicht, _test_oeffnen(page, ansicht)

    def sichern(ansicht, dialog) -> Block:
        _daten(dialog, "block_uebernehmen").on_click()
        _speichern(ansicht)
        return _test_im_kurs(state, kurs)

    def wert(dialog, marke: str) -> str:
        return str(_daten(dialog, ("test_skala_wert", marke)).value)

    # -- Anstrengung „ab“: −/+ stellen die Marke ------------------------------------------
    ansicht, dialog = oeffnen()
    _vorgabe(dialog, SKALA)
    assert _gewaehlt(dialog, "test_vorgabe") == [SKALA]
    assert _gewaehlt(dialog, "test_skala_form") == [AB] and wert(dialog, AB) == "7"
    feld = _daten(dialog, "test_feld")
    assert (feld.label, feld.value) == ("Ins Ziel kommt", "reps")
    assert [(o.key, o.text) for o in feld.options] == [
        ("reps", "Wiederholungen"),
        ("duration", "Zeit"),
    ]
    assert _texte(_daten(dialog, "test_gemessen")) == ["GEMESSEN WIRD", "Wiederholungen", "Zeit"]
    assert "mal" not in _felder(dialog)  # Kursplan: Den Faktor trägt der Baustein
    vorschau = _daten(dialog, "test_vorschau")
    assert vorschau.visible is True
    assert _texte(vorschau)[:2] == ["SO STEHT ES IM KAPITEL", "Käfer: bis Anstrengung 7"]
    _daten(dialog, ("test_skala_minus", AB)).on_click()
    assert wert(dialog, AB) == "6"
    assert _texte(_daten(dialog, "test_vorschau"))[1] == "Käfer: bis Anstrengung 6"
    # Die Zeile der Sammelkarte kommt aus der Vorschau des Kapitels — Wort für Wort
    entwurf = replace(next(b for b in zwei.bloecke if b.id == "t"), vorgabe=Vorgabe(SKALA, 6))
    sicht = Kurssicht(kurs, zwei.id, zwei.bloecke, {x.id: x for x in u.values()}).mit(entwurf)
    (ziel,) = [z for z in sicht.vorschau().zeilen if z.block_id == "b2" and z.art == ZIEL]
    assert ziel.titel == "Ziel für Käfer: 15 Wiederholungen" and "Anstrengung 6" in ziel.unter
    assert f"Sammelkarte: „{ziel.titel} — {ziel.unter}“" in _texte(_daten(dialog, "test_vorschau"))
    assert any(
        t.startswith("Beispiel mit der Wahl „Käfer“ und dem Testwert 30 Wiederholungen.")
        for t in _texte(_daten(dialog, "test_vorschau"))
    )
    _daten(dialog, "block_uebernehmen").on_click()
    assert "Käfer: bis Anstrengung 6 · Wiederholungen" in _texte(ansicht)  # die Zeile der Liste
    # … und der Baustein nennt den Test so in seiner Wahl „Ziel“
    _daten(ansicht, ("baustein", "b2")).on_click()
    ziel_wahl = _daten(page.dialoge[-1], "baustein_ziel")
    assert {o.key: o.text for o in ziel_wahl.options}["test:t"] == (
        "aus dem Test „Käfer: bis Anstrengung 6“"
    )
    _daten(page.dialoge[-1], "baustein_abbrechen").on_click()
    _speichern(ansicht)
    assert _test_im_kurs(state, kurs).vorgabe == Vorgabe(SKALA, 6)

    # -- wieder öffnen zeigt dieselben Werte; „höchstens“ und „von–bis“ --------------------
    ansicht, dialog = oeffnen()
    assert _gewaehlt(dialog, "test_vorgabe") == [SKALA]
    assert _gewaehlt(dialog, "test_skala_form") == [AB] and wert(dialog, AB) == "6"
    assert _daten(dialog, "test_feld").value == "reps"
    _daten(dialog, ("test_skala_form", HOECHSTENS)).on_select()
    assert wert(dialog, HOECHSTENS) == "4"
    _daten(dialog, ("test_skala_plus", HOECHSTENS)).on_click()
    assert _texte(_daten(dialog, "test_vorschau"))[1] == "Käfer: solange höchstens Anstrengung 5"
    assert sichern(ansicht, dialog).vorgabe == Vorgabe(SKALA, 0, 5)
    ansicht, dialog = oeffnen()
    assert _gewaehlt(dialog, "test_skala_form") == [HOECHSTENS] and wert(dialog, HOECHSTENS) == "5"
    _daten(dialog, ("test_skala_form", VON_BIS)).on_select()
    assert (wert(dialog, "von"), wert(dialog, "bis")) == ("5", "7")
    for _ in range(9):  # „von“ bleibt unter „bis“, „bis“ unter 10
        _daten(dialog, ("test_skala_plus", "bis")).on_click()
    for _ in range(2):
        _daten(dialog, ("test_skala_minus", "von")).on_click()
    assert (wert(dialog, "von"), wert(dialog, "bis")) == ("3", "9")
    assert _daten(dialog, ("test_skala_plus", "bis")).disabled is True
    assert sichern(ansicht, dialog).vorgabe == Vorgabe(SKALA, 3, 9)
    ansicht, dialog = oeffnen()
    assert _gewaehlt(dialog, "test_skala_form") == [VON_BIS]
    assert (wert(dialog, "von"), wert(dialog, "bis")) == ("3", "9")

    # -- Menge: Zahl der Wiederholungen; die Vorgabe ist der Beispielwert -----------------
    _vorgabe(dialog, MENGE)
    menge = _daten(dialog, "test_menge")
    assert menge.value == "30" and _daten(dialog, "test_feld").value == "reps"
    assert _texte(_daten(dialog, "test_gemessen")) == ["GEMESSEN WIRD", "Zeit", "Anstrengung"]
    menge.value = ""
    menge.on_blur()
    assert any("braucht eine Zahl" in t for t in _texte(_daten(dialog, "test_vorschau")))
    _daten(dialog, "block_uebernehmen").on_click()  # ohne Zahl wird nichts übernommen
    assert "Die Vorgabe „Menge“ braucht eine Zahl von Wiederholungen." in _texte(dialog)
    assert "Käfer: zwischen Anstrengung 3 und 9 · Wiederholungen" in _texte(ansicht)
    menge.value = "12"
    menge.on_blur()
    texte = _texte(_daten(dialog, "test_vorschau"))
    assert texte[1] == "Käfer: 12 Wiederholungen"
    assert any(t.startswith("Sammelkarte: „Ziel für Käfer: 6 Wiederholungen — ") for t in texte)
    _daten(dialog, "block_uebernehmen").on_click()
    assert "Käfer: 12 Wiederholungen" in _texte(ansicht)  # ohne „· Wiederholungen“ dahinter
    _speichern(ansicht)
    assert _test_im_kurs(state, kurs).vorgabe == Vorgabe(MENGE, 12)
    ansicht, dialog = oeffnen()
    assert _gewaehlt(dialog, "test_vorgabe") == [MENGE]
    assert _daten(dialog, "test_menge").value == "12"

    # -- Zeit: das Blatt für jede Zeit ---------------------------------------------------
    _vorgabe(dialog, ZEIT)
    assert _daten(dialog, "test_zeit").content == "1:00"
    _zeit_stellen(page, dialog, "1:30")
    assert _daten(dialog, "test_zeit").content == "1:30"
    assert _texte(_daten(dialog, "test_vorschau"))[1] == "Käfer: 1:30 Minuten"
    assert _texte(_daten(dialog, "test_gemessen")) == [
        "GEMESSEN WIRD",
        "Wiederholungen",
        "Anstrengung",
    ]
    assert sichern(ansicht, dialog).vorgabe == Vorgabe(ZEIT, 90)
    ansicht, dialog = oeffnen()
    assert _gewaehlt(dialog, "test_vorgabe") == [ZEIT]
    assert _daten(dialog, "test_zeit").content == "1:30"
    assert "Käfer: 1:30 Minuten · Wiederholungen" in _texte(ansicht)

    # -- als Paket hinaus und wieder herein: Die Vorgabe reist mit ------------------------
    frisch = state.kurse.laden(kurs.id)
    assert _paketpruefung(state, frisch)[0] == []
    _, gebaut, wieder = _rundreise(state, frisch)
    for inhalt in (gebaut, wieder):
        (gelesen,) = inhalt.kurse
        assert [b.vorgabe for b in gelesen.kapitel[1].bloecke if b.art == TEST] == [
            Vorgabe(ZEIT, 90)
        ]

    # -- „Ohne“ nimmt die Vorgabe weg ------------------------------------------------------
    _vorgabe(dialog, OHNE)
    assert _daten(dialog, "test_vorschau").visible is False
    assert _daten(dialog, "test_gemessen").visible is False
    assert _daten(dialog, "test_feld").label == "Was wird gemessen"
    assert sichern(ansicht, dialog).vorgabe is None
    ansicht, dialog = oeffnen()
    assert _gewaehlt(dialog, "test_vorgabe") == [OHNE]
    assert "Käfer · Wiederholungen" in _texte(ansicht)


def test_umschalten_der_vorgabe_belegt_ins_ziel_kommt_vor(page, state) -> None:
    """Vorbelegt ist bei Vorgabe Menge die Vorgabe selbst (Wiederholungen), sonst das Gemessene
    — die Wiederholungen, bei einer Übung ohne sie das Zeitfeld. Was von Hand gewählt oder
    schon gespeichert ist, bleibt, solange es zur Wahl steht."""
    kurs, u = _kurs(state)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])

    def neuer_test(uebung: str) -> ft.AlertDialog:
        _daten(ansicht, ("block_neu", TEST)).on_click()
        dialog = page.dialoge[-1]
        wahl = _felder(dialog)["Übung"]
        wahl.value = u[uebung].id
        wahl.on_select()
        return dialog

    def stand(dialog) -> tuple[list[str], str]:
        feld = _daten(dialog, "test_feld")
        return [o.key for o in feld.options], feld.value

    # Die Planke hält: Wiederholungen gibt es nur, wenn die Vorgabe sie verlangt
    dialog = neuer_test("Planke")
    assert stand(dialog) == (["hold"], "hold")
    _vorgabe(dialog, MENGE)
    assert stand(dialog) == (["reps", "hold"], "reps")  # die Vorgabe selbst
    assert _texte(_daten(dialog, "test_gemessen")) == ["GEMESSEN WIRD", "Zeit", "Anstrengung"]
    _vorgabe(dialog, ZEIT)
    assert stand(dialog) == (["hold"], "hold")
    assert _texte(_daten(dialog, "test_gemessen")) == ["GEMESSEN WIRD", "Anstrengung"]
    _vorgabe(dialog, SKALA)
    assert stand(dialog) == (["hold"], "hold")  # das Gemessene: die Zeit
    assert _texte(_daten(dialog, "test_gemessen")) == ["GEMESSEN WIRD", "Zeit"]
    # von Hand gewählt: bleibt, solange es zur Wahl steht
    _vorgabe(dialog, MENGE)
    feld = _daten(dialog, "test_feld")
    assert feld.value == "reps"
    feld.value = "hold"
    feld.on_select()
    _vorgabe(dialog, ZEIT)
    _vorgabe(dialog, MENGE)
    assert stand(dialog) == (["reps", "hold"], "hold")
    _vorgabe(dialog, OHNE)
    assert stand(dialog) == (["hold"], "hold")
    _vorgabe(dialog, MENGE)
    _daten(dialog, "block_uebernehmen").on_click()
    assert "Planke: 30 Wiederholungen · Haltezeit" in _texte(ansicht)

    # Käfer zählt: Wiederholungen bei jeder Vorgabe, daneben die Zeit der Uhr
    dialog = neuer_test("Käfer")
    assert stand(dialog) == (["reps"], "reps")
    for art in (MENGE, ZEIT, SKALA):
        _vorgabe(dialog, art)
        assert stand(dialog) == (["reps", "duration"], "reps"), art
    feld = _daten(dialog, "test_feld")
    feld.value = "duration"
    feld.on_select()
    _vorgabe(dialog, MENGE)
    assert stand(dialog)[1] == "duration"
    _daten(dialog, "block_uebernehmen").on_click()
    assert "Käfer: 30 Wiederholungen · Zeit" in _texte(ansicht)

    # Gespeichert gilt als gewählt: Der Test „t“ misst Wiederholungen — das bleibt
    dialog = _test_oeffnen(page, ansicht)
    for art in (SKALA, ZEIT, MENGE, OHNE):
        _vorgabe(dialog, art)
        assert _daten(dialog, "test_feld").value == "reps"
    # Die Übung wechselt: Was nicht mehr zur Wahl steht, weicht der Vorbelegung
    _vorgabe(dialog, SKALA)
    wahl = _felder(dialog)["Übung"]
    wahl.value = u["Planke"].id
    wahl.on_select()
    assert stand(dialog) == (["hold"], "hold")
    assert _texte(_daten(dialog, "test_vorschau"))[1] == "Planke: bis Anstrengung 7"


def test_faktor_des_tests_gilt_im_kapitelplan(page, state) -> None:
    """Wo der Faktor gilt: Im Kapitelplan nimmt `vorlage_anwenden` den des Tests — dort steht
    er im Dialog, ohne Vorgabe als „Ziel in % des Tests“, mit Vorgabe als „mal“ neben dem
    Feld (dieselbe Zahl). Im Kursplan nimmt die Sammelkarte den des Bausteins — der Test-Dialog
    zeigt dort keinen."""
    u = _uebungen(state)
    kurs = editor.kurs_anlegen(state)
    kapitel = kurs.kapitel[0]
    kapitel.plaene = [PlanVorlage("Rumpf", items=[VorlageItem(u["Planke"].id)])]
    kapitel.bloecke = [Block(TEST, id="t", uebung=u["Planke"].id, feld="hold", faktor=0.8)]
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[0])
    assert "Planke — wird Ziel im Plan (80 %)" in _texte(ansicht)
    dialog = _test_oeffnen(page, ansicht)
    prozent, mal = _felder(dialog)["Ziel in % des Tests"], _daten(dialog, "test_mal")
    assert (prozent.value, prozent.visible, mal.visible) == ("80", True, False)
    _vorgabe(dialog, ZEIT)
    assert (mal.label, mal.value, mal.visible, prozent.visible) == ("mal", "0,8", True, False)
    assert _daten(dialog, "test_feld").value == "hold"  # gespeichert: bleibt
    # nur die Überschrift — eine Sammelkarte gibt es ohne Kursplan nicht
    assert _texte(_daten(dialog, "test_vorschau")) == ["SO STEHT ES IM KAPITEL", "Planke: 1 Minute"]
    mal.value = "0,5"
    _vorgabe(dialog, OHNE)  # der Faktor wandert mit
    assert (prozent.value, prozent.visible, mal.visible) == ("50", True, False)
    prozent.value = "60"
    _vorgabe(dialog, ZEIT)
    assert mal.value == "0,6"
    _daten(dialog, "block_uebernehmen").on_click()
    assert "Planke: 1 Minute — wird Ziel im Plan (60 %)" in _texte(ansicht)
    _speichern(ansicht)
    test = _test_im_kurs(state, kurs)
    assert (test.vorgabe, test.faktor, test.feld) == (Vorgabe(ZEIT, 60), 0.6, "hold")

    # Kurs mit Kursplan: kein Faktor am Test — und er bleibt, wie er war
    kurs, _ = _kurs(state)
    eigener = next(b for b in kurs.kapitel[1].bloecke if b.id == "t")
    eigener.faktor = 0.7
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    ansicht = kapitel_bearbeiten(page, state, kurs, kurs.kapitel[1])
    dialog = _test_oeffnen(page, ansicht)
    assert not _hat(dialog, "test_mal") and "Ziel in % des Tests" not in _felder(dialog)
    _vorgabe(dialog, SKALA)
    assert not _hat(dialog, "test_mal")
    assert any("sagt der Baustein unter „Am Plan“" in t for t in _texte(dialog))
    _daten(dialog, "block_uebernehmen").on_click()
    _speichern(ansicht)
    test = _test_im_kurs(state, kurs)
    assert (test.vorgabe, test.faktor) == (Vorgabe(SKALA, 7), 0.7)


# -- Die Karte „So wächst der Plan“ (§14) ------------------------------------------------------


def _kursbild(ansicht):
    """Bild (`core.kursbild.Planbild`) und Handgriffe (`KursplanBild`) der Karte „So wächst der
    Plan“ — ``None``, wenn die Ansicht keine zeigt."""
    for x in _alle(ansicht):
        daten = getattr(x, "data", None)
        if isinstance(daten, tuple) and daten and daten[0] == "kursbild":
            assert x.visible is not False
            return daten[1], daten[2]
    return None


def _planuebung(bild, uebung: Exercise) -> str:
    """Die Planübung des Beispielplans zu einer Übung."""
    (item,) = [i.id for i in bild.plan.items if i.exercise_id == uebung.id]
    return item


def _kurs_mit_drei_kapiteln(state: AppState) -> tuple[Kurs, dict[str, Exercise]]:
    """Der Kurs der Skizzen und ein drittes Kapitel, das die Brücke bringt — aus Sicht von
    Kapitel 2 steht sie im Bild blass."""
    kurs, u = _kurs(state)
    kurs.kapitel.append(
        Kapitel(
            titel="Seitlich",
            kurs_id=kurs.id,
            bloecke=[Block(PLAN_UEBUNG, id="b5", uebung=u["Brücke"].id)],
        )
    )
    state.kurse.speichern(kurs)
    return state.kurse.laden(kurs.id), u


def test_bild_des_plans_im_kurs_formular(page, state) -> None:
    """Ben, 16.11.2026: „die Karte aus dem Ablauf beim Erstellen des Kurses mit einbauen“ — im
    Kurs-Formular steht sie unter dem Kursplan, nur zum Ansehen, bis zum letzten Kapitel. Die
    Grundlage aus einem eigenen Plan (die Vorlage im Kurs) ist im Bild. Ohne Kursplan gibt es
    die Karte nicht."""
    kurs, u = _kurs_mit_drei_kapiteln(state)
    ansicht = kurs_bearbeiten(page, state, kurs)
    bild, karte = _kursbild(ansicht)
    texte = _texte(ansicht)
    assert "SO WÄCHST DER PLAN" in texte
    assert karte.bis() == 3 and "Bis Kapitel 3 „Seitlich“: alle 4 Übungen im Plan." in texte
    assert {"Planke", "Seitstütz", "Käfer", "Brücke"} <= set(texte)
    # die Grundlage (ein eigener Plan als Vorlage im Kurs) steht im Bild — als „Anfang“
    planke = _planuebung(bild, u["Planke"])
    assert bild.kapitel[planke] == 0 and bild.marke(planke) == "g:1"
    assert _daten_ids(ansicht, "kursbild_bis") == [0, 1, 2, 3]
    # nur zum Ansehen: Tipps auf Übung und Weg öffnen nichts
    offen = len(page.dialoge)
    karte.knoten(planke)
    karte.kante(ab.Kante(_planuebung(bild, u["Seitstütz"]), _planuebung(bild, u["Käfer"])))
    assert len(page.dialoge) == offen
    assert not any(t.startswith("Tippe eine Übung an") for t in texte)

    # Wochentage ändern das Bild nicht — die Karte bleibt dieselbe (Zoom, gewähltes Kapitel)
    karte.waehlen(1)
    _daten(ansicht, ("kursplan_tag", 5)).on_click()
    assert _kursbild(ansicht)[1] is karte and karte.bis() == 1
    # Kapitel ändern es: ein neues Kapitel bekommt seinen Chip
    _daten(ansicht, "kapitel_hinzufuegen").on_click()
    assert _daten_ids(ansicht, "kursbild_bis") == [0, 1, 2, 3, 4]
    assert _kursbild(ansicht)[1] is not karte

    # Der Schalter aus: keine Karte; wieder an: Sie ist zurück (ohne Grundlage — kein „Anfang“)
    _daten(ansicht, "kursplan_an").on_change(_an(False))
    _daten(page.dialoge[-1], "kursplan_aus_ja").on_click()
    assert _kursbild(ansicht) is None and "SO WÄCHST DER PLAN" not in _texte(ansicht)
    _daten(ansicht, "kursplan_an").on_change(_an(True))
    bild, _ = _kursbild(ansicht)
    assert [bild.kapitel[i.id] for i in bild.plan.items] == [1, 2, 3]
    assert _daten_ids(ansicht, "kursbild_bis") == [1, 2, 3, 4]

    # Ein Kurs, der keinen Plan baut, hat kein Bild — auch nicht im Kapitel
    ohne = editor.kurs_anlegen(state)
    assert _kursbild(kurs_bearbeiten(page, state, ohne)) is None
    assert _kursbild(kapitel_bearbeiten(page, state, ohne, ohne.kapitel[0])) is None


def test_bild_des_plans_im_kapitel_folgt_den_bausteinen(page, state) -> None:
    """Im Kapitel-Formular steht die Karte unter den Listen, bis zu diesem Kapitel — was ein
    späteres bringt, ist blass. Sie rechnet mit den **ungespeicherten** Blöcken: Ein neuer
    Baustein steht im Bild, bevor gespeichert ist."""
    kurs, u = _kurs_mit_drei_kapiteln(state)
    zwei = kurs.kapitel[1]
    ansicht = kapitel_bearbeiten(page, state, kurs, zwei)
    bild, karte = _kursbild(ansicht)
    texte = _texte(ansicht)
    assert karte.bis() == 2
    assert "Bis Kapitel 2 „Erweiterung“: 3 von 4 Übungen im Plan." in texte
    assert any(t.startswith("Tippe eine Übung an, um von ihr einen Weg zu setzen") for t in texte)
    assert bild.spaeter(2) == [_planuebung(bild, u["Brücke"])]  # Kapitel 3 bringt sie: blass
    # die Karte steht unter den Listen und den Knöpfen „+ Im Kapitel“ / „+ Am Plan“
    reihenfolge = [
        x.data
        for x in _alle(ansicht)
        if getattr(x, "data", None) in (("baustein", "b4"), "baustein_dazu")
        or (isinstance(getattr(x, "data", None), tuple) and x.data[0] == "kursbild")
    ]
    assert [d if isinstance(d, str) else d[0] for d in reihenfolge] == [
        "baustein",
        "baustein_dazu",
        "kursbild",
    ]

    # Ein anderes Kapitel gewählt — das bleibt, wenn das Bild neu entsteht
    karte.waehlen(1)
    # Ein neuer Baustein „Übung dazu“ (der Seitstütz noch einmal, ans Ende): ohne zu speichern
    _daten(ansicht, ("baustein_neu", PLAN_UEBUNG)).on_click()
    blatt = page.dialoge[-1]
    _waehlen(blatt, "baustein_uebung", f"u:{u['Seitstütz'].id}")
    _daten(blatt, "baustein_uebernehmen").on_click()
    neues_bild, neue_karte = _kursbild(ansicht)
    assert neue_karte is not karte and neue_karte.bis() == 1
    assert len(neues_bild.plan.items) == 5
    assert [neues_bild.marke(i.id) for i in neues_bild.plan.items if i.kurs_marke == "uebung-1"]
    assert "Bis Kapitel 1 „Grundlage“: 2 von 5 Übungen im Plan." in _texte(ansicht)
    neue_karte.waehlen(2)
    assert "Bis Kapitel 2 „Erweiterung“: 4 von 5 Übungen im Plan." in _texte(ansicht)
    gespeichert = state.kurse.laden(kurs.id).kapitel[1]
    assert "uebung-1" not in [b.id for b in gespeichert.bloecke]  # noch nichts gespeichert

    # Der Titel im Feld gilt schon für die Karte, sobald sie neu entsteht; Löschen zieht nach
    _felder(ansicht)["Titel"].value = "Mehr Rumpf"
    zeile = _daten(ansicht, ("baustein", "uebung-1"))
    next(x for x in _alle(zeile) if getattr(x, "tooltip", None) == "Entfernen").on_click()
    assert "Bis Kapitel 2 „Mehr Rumpf“: 3 von 4 Übungen im Plan." in _texte(ansicht)


def test_beziehungen_im_bild_setzen(page, state) -> None:
    """„Beim neu erstellten Kursplan ließen sich dort die Beziehungen setzen“: Ein Tipp auf
    eine Übung öffnet das Blatt für einen neuen Weg dieses Kapitels, „Von“ vorbelegt — mit der
    Marke, wie das Blatt sie anbietet (Grundlage ``g:<n>``, ein Baustein, bei einer der
    Gewählten ihr Baustein). Eine blasse Übung meldet, welches Kapitel sie bringt. Ein Tipp auf
    den Punkt eines Wegs öffnet seinen Baustein — aus einem anderen Kapitel meldet er es."""
    kurs, u = _kurs_mit_drei_kapiteln(state)
    zwei, drei = kurs.kapitel[1], kurs.kapitel[2]
    ansicht = kapitel_bearbeiten(page, state, kurs, zwei)
    bild, karte = _kursbild(ansicht)
    planke, seit, kaefer, bruecke = (
        _planuebung(bild, u[name]) for name in ("Planke", "Seitstütz", "Käfer", "Brücke")
    )
    assert [bild.marke(i) for i in (planke, seit, kaefer, bruecke)] == [
        "g:1",
        "b1",
        f"b2:{u['Käfer'].id}",
        "b5",
    ]

    # Blass: Die Brücke kommt erst mit Kapitel 3 — kein Blatt, eine Zeile sagt es
    assert bruecke in bild.spaeter(karte.bis())
    offen = len(page.dialoge)
    karte.knoten(bruecke)
    meldung = page.dialoge[-1]
    assert len(page.dialoge) == offen + 1 and isinstance(meldung, ft.SnackBar)
    assert meldung.content.value == (
        "Brücke kommt erst mit Kapitel 3 „Seitlich“ in den Plan — ein Weg dieses Kapitels kann "
        "die Übung noch nicht nennen."
    )

    # Eine der Gewählten (`b2:<käfer>`): „Von“ ist ihr Baustein — „die gewählte“, wie das
    # Blatt sie anbietet; nichts „fehlt hier“
    karte.knoten(kaefer)
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet) and "Weg im Plan" in _texte(blatt)
    von = _daten(blatt, "baustein_von")
    assert von.value == "b2" and [o.key for o in von.options] == ["g:1", "b1", "b2"]
    assert not any("fehlt hier" in o.text for o in von.options)
    assert not _hat(blatt, "baustein_loeschen")  # ein neuer Baustein
    _daten(blatt, "baustein_abbrechen").on_click()
    # Ein Baustein eines früheren Kapitels
    karte.knoten(seit)
    assert _daten(page.dialoge[-1], "baustein_von").value == "b1"
    _daten(page.dialoge[-1], "baustein_abbrechen").on_click()

    # Die Grundlage: von der Planke zur gewählten — übernommen steht der Weg im Bild
    karte.knoten(planke)
    blatt = page.dialoge[-1]
    assert _daten(blatt, "baustein_von").value == "g:1"
    _waehlen(blatt, "baustein_zu", "b2")
    _daten(blatt, "baustein_uebernehmen").on_click()
    assert "Planke → die gewählte" in _texte(ansicht)
    bild, karte = _kursbild(ansicht)
    planke, seit, kaefer = (_planuebung(bild, u[n]) for n in ("Planke", "Seitstütz", "Käfer"))
    neuer = bild.wege[(planke, kaefer)]
    assert (neuer.nr, neuer.kapitel_id) == (2, zwei.id)
    (neue_id,) = [b for b in _daten_ids(ansicht, "baustein") if b not in ("b2", "b3", "b4")]
    assert neuer.block_id == neue_id and neue_id.startswith("weg-")
    assert neue_id not in [b.id for b in state.kurse.laden(kurs.id).kapitel[1].bloecke]
    _speichern(ansicht)
    gespeichert = next(b for b in state.kurse.laden(kurs.id).kapitel[1].bloecke if b.id == neue_id)
    assert (gespeichert.art, gespeichert.von, gespeichert.zu) == (PLAN_WEG, "g:1", "b2")
    assert _paketpruefung(state, state.kurse.laden(kurs.id))[0] == []

    # … und nach dem Speichern wieder geöffnet: Der Baustein ist ein Weg im Bild
    kurs = state.kurse.laden(kurs.id)
    zwei, drei = kurs.kapitel[1], kurs.kapitel[2]
    ansicht = kapitel_bearbeiten(page, state, kurs, zwei)
    bild, karte = _kursbild(ansicht)
    planke, seit, kaefer = (_planuebung(bild, u[n]) for n in ("Planke", "Seitstütz", "Käfer"))
    assert {w.block_id for w in bild.wege.values()} == {"b3", neue_id}

    # Tipp auf den Punkt eines Wegs dieses Kapitels: das Blatt seines Bausteins, zum Ändern
    karte.kante(ab.Kante(seit, kaefer))
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet) and blatt.data == ("baustein_blatt", "b3")
    assert _daten(blatt, "baustein_von").value == "b1" and _hat(blatt, "baustein_loeschen")
    _daten(blatt, "baustein_abbrechen").on_click()
    # Ein Schritt, der nur die Reihenfolge der Liste ist: kein Blatt — die Karte sagt es selbst
    offen = len(page.dialoge)
    karte.kante(ab.Kante(planke, seit))
    assert len(page.dialoge) == offen and KEIN_BAUSTEIN in _texte(ansicht)

    # Derselbe Weg aus Sicht von Kapitel 3: Er gehört nicht hierher — eine Zeile sagt, wohin
    ansicht = kapitel_bearbeiten(page, state, kurs, drei)
    bild, karte = _kursbild(ansicht)
    seit, kaefer = (_planuebung(bild, u[n]) for n in ("Seitstütz", "Käfer"))
    assert karte.bis() == 3
    offen = len(page.dialoge)
    karte.kante(ab.Kante(seit, kaefer))
    meldung = page.dialoge[-1]
    assert len(page.dialoge) == offen + 1 and isinstance(meldung, ft.SnackBar)
    assert meldung.content.value == (
        "Dieser Weg kommt aus Kapitel 2 „Erweiterung“ — dort lässt er sich ändern."
    )


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
        ("b2", "Ziel für Käfer: 15 Wiederholungen", "50 % von deinem Test (30 Wdh.)"),
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
    assert "Darauf beziehen sich andere Blöcke:" in texte
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
