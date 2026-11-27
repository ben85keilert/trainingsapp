"""Die Teilnehmer-Seite des Kursplans (Ben, 16.11.2026, `docs/plan_kurs_ablauf.md` §11.5,
Skizzen K2–K4): die Sammelkarte „Das ändert sich an deinem Plan“ im Kapitel und die Karte
„Dein Kursplan“ auf der Kursseite.

Bens Beispiel: Kapitel 1 bringt die Planke mit 60 Sekunden; Kapitel 2 lässt eine von drei
Übungen wählen, hängt sie hinter die Planke, setzt ihr Ziel aus einem Test und verbindet beide
mit einem Weg; Kapitel 3 steigert die Planke. Nichts ändert sich ohne Tipp. Die Rechnung
prüft `tests/test_kursplan.py`, die Datenbank `tests/test_kurse.py`. Läuft nur mit `flet`.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.kursbloecke import (  # noqa: E402
    AUSWAHL,
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
from trainingsapp.core.models import Exercise, Session  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.kurse import kapitel_view, kurs_view, kurse_liste  # noqa: E402

UEBERNEHMEN = "kursplan_uebernehmen"
#: Der eine Satz, wenn nichts mehr anzubieten und nichts offen ist — auch nach „lassen“ wahr
STAND = "Aus diesem Kapitel ist nichts mehr offen."


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


def _kapitel(page, state, kurs: Kurs, kapitel: Kapitel):
    return kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())


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


def _kurs(
    state: AppState, kursplan: Kursplan | None = None, *, test_aus: bool = False
) -> tuple[Kurs, dict[str, Exercise]]:
    """Bens Beispiel als Kurs mit Kursplan — gespeichert und wieder geladen. ``test_aus``: Der
    Test in Kapitel 2 misst nicht den Käfer, sondern **die gewählte** Übung (``aus``), und
    Kapitel 3 testet sie noch einmal (die Auswahl steht dann in einem früheren Kapitel)."""
    ue = _uebungen(state)
    test = (
        Block(TEST, id="test", aus="wahl", feld="reps")
        if test_aus
        else Block(TEST, id="test", uebung=ue["Käfer"].id, feld="reps")
    )
    nochmal = [Block(TEST, id="test3", aus="wahl", feld="reps")] if test_aus else []
    kurs = Kurs(
        name="Rumpf-Kurs",
        kursplan=kursplan or Kursplan("Rumpf", [0, 2, 4]),
        kapitel=[
            Kapitel(
                titel="Ausgangsstand",
                bloecke=[
                    Block(TEXT, id="t", text="Die Planke hält den Rumpf still."),
                    Block(PLAN_UEBUNG, id="a", uebung=ue["Planke"].id, ziel={"hold": [60]}),
                ],
            ),
            Kapitel(
                titel="Erweiterung",
                bloecke=[
                    Block(
                        AUSWAHL,
                        id="wahl",
                        uebungen=[ue[n].id for n in ("Seitstütz", "Käfer", "Brücke")],
                        anzahl=1,
                    ),
                    test,
                    Block(PLAN_UEBUNG, id="dazu", aus="wahl", hinter="a", ziel_aus="test"),
                    Block(
                        PLAN_WEG,
                        id="weg",
                        von="a",
                        zu="dazu",
                        kante={"ausloeser": "zeit", "pflicht": True},
                    ),
                ],
                bedingung=Bedingung(TAGE, soll=3),
            ),
            Kapitel(
                titel="Steigern",
                bloecke=[
                    Block(PLAN_EINSTELLEN, id="mehr", an="a", ziel={"hold": [75]}),
                    *nochmal,
                ],
            ),
        ],
    )
    state.kurse.speichern(kurs)
    geladen = state.kurse.laden(kurs.id)
    assert geladen is not None
    return geladen, ue


def _test_eintragen(state: AppState, uebung: Exercise, werte: dict) -> None:
    """Der Test ist ein gewöhnlicher Eintrag der Übung."""
    session = Session(subject_id=state.profil.id)
    state.sitzungen.anlegen(session)
    state.sitzungen.eintrag_anlegen(session, uebung, werte)


def _meldung(page) -> str:
    assert isinstance(page.dialoge[-1], ft.SnackBar)
    return str(page.dialoge[-1].content.value)


def _offene_wahl(state: AppState) -> dict[tuple[str, str], dict[str, list[str]]]:
    """Was die Sitzung an offener Wahl hält: (Profil, Kapitel) → {Auswahl-Block: Übungen}."""
    return {schluessel: wahl for schluessel, (_stempel, wahl) in state.kurs_wahl.items()}


# ---------------------------------------------------------------------------
# Kapitel: die Sammelkarte
# ---------------------------------------------------------------------------


def test_kapitel_1_zeigt_die_zeilen_und_aendert_erst_mit_uebernehmen(page, state) -> None:
    kurs, ue = _kurs(state)
    eins = kurs.kapitel[0]
    profil = state.profil.id
    ansicht = _kapitel(page, state, kurs, eins)
    texte = _texte(ansicht)
    assert "Das ändert sich an deinem Plan" in texte and "Rumpf · dein Kursplan" in texte
    assert "Planke kommt dazu" in texte and "ans Ende" in texte
    assert "Ziel für Planke: 60 s" in texte and "aus dem Kurs" in texte
    assert "Nichts ändert sich ohne deinen Tipp. Einzelnes kannst du abwählen." in texte
    assert _daten(ansicht, ("kursplan_zeile", "a")).value is True
    # Öffnen ändert nichts: Den Plan gibt es noch nicht — und „Plan anlegen“ gibt es hier nie
    assert state.kurse.kursplan(kurs, profil) is None
    assert not _hat(ansicht, "plan_anlegen")

    _daten(ansicht, UEBERNEHMEN).on_click()
    plan = state.kurse.kursplan(kurs, profil)
    assert plan is not None and plan.name == "Rumpf" and plan.aktiv
    assert [(i.exercise_id, i.target) for i in plan.items] == [(ue["Planke"].id, {"hold": [60]})]
    assert _meldung(page) == "Plan geändert — er steht auf „Heute“"

    # Danach steht nur noch der eine Satz da
    ansicht = _kapitel(page, state, kurs, eins)
    assert STAND in _texte(ansicht) and "Planke kommt dazu" not in _texte(ansicht)
    assert not _hat(ansicht, UEBERNEHMEN) and not _hat(ansicht, ("kursplan_zeile", "a"))


def test_kapitel_2_ohne_wahl_offen_mit_wahl_zeilen_und_nur_gewaehltes_gilt(page, state) -> None:
    kurs, ue = _kurs(state)
    eins, zwei, _drei = kurs.kapitel
    profil = state.profil.id
    kaefer, bruecke = ue["Käfer"], ue["Brücke"]
    state.kurse.starten(kurs, profil)
    state.kurse.plan_uebernehmen(kurs, eins, profil, {"a", "a#ziel"})
    state.kurse.kapitel_abschliessen(kurs, eins, profil)

    # Ohne Wahl: offen, nichts zu übernehmen — und kein „Plan anlegen“
    ansicht = _kapitel(page, state, kurs, zwei)
    texte = _texte(ansicht)
    assert "Deine Auswahl kommt dazu" in texte and "Triff zuerst deine Auswahl." in texte
    assert not _hat(ansicht, UEBERNEHMEN) and not _hat(ansicht, "plan_anlegen")
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.Checkbox)]

    # Wahl treffen: Die Zeilen stehen da; das Ziel wartet noch auf den Test
    _daten(ansicht, ("wahl", "wahl", kaefer.id)).on_select()
    texte = _texte(ansicht)
    assert "Käfer kommt dazu" in texte and "hinter Planke" in texte
    assert "Ziel für Käfer" in texte and "aus deinem Test — mach ihn zuerst" in texte
    assert not _hat(ansicht, ("kursplan_zeile", f"dazu:{kaefer.id}#ziel"))
    # Umentscheiden baut die Karte neu — die Zeilen hängen an der Wahl
    _daten(ansicht, ("wahl", "wahl", bruecke.id)).on_select()
    assert "Brücke kommt dazu" in _texte(ansicht) and "Käfer kommt dazu" not in _texte(ansicht)
    assert state.kurse.kursplan(kurs, profil).items[-1].exercise_id == ue["Planke"].id

    # Der Test: ein gewöhnlicher Eintrag. Wer dafür das Kapitel verlässt und zurückkommt —
    # die Ansicht wird neu gebaut, wie nach jeder Route —, findet Wahl und Zeilen wieder
    # (Ben, 16.11.2026, P212): Die Sitzung hält die offene Wahl, bis sie übernommen ist
    assert _offene_wahl(state) == {(profil, zwei.id): {"wahl": [bruecke.id]}}
    _test_eintragen(state, kaefer, {"reps": [24, 30]})
    ansicht = _kapitel(page, state, kurs, zwei)
    chip = _daten(ansicht, ("wahl", "wahl", bruecke.id))
    assert chip.selected is True and chip.disabled is False  # gewählt und weiter änderbar
    assert _daten(ansicht, ("wahl", "wahl", kaefer.id)).selected is False
    assert "Brücke kommt dazu" in _texte(ansicht)  # die Karte zeigt sofort die Zeilen dazu
    assert "Deine Auswahl kommt dazu" not in _texte(ansicht)
    assert _hat(ansicht, UEBERNEHMEN)
    _daten(ansicht, ("wahl", "wahl", kaefer.id)).on_select()  # umentscheiden geht weiter
    assert _offene_wahl(state) == {(profil, zwei.id): {"wahl": [kaefer.id]}}
    marke = f"dazu:{kaefer.id}"
    texte = _texte(ansicht)
    assert "Ziel für Käfer: 30 Wiederholungen" in texte and "aus deinem Test" in texte
    assert "Von Planke weiter zu Käfer, wenn die Zeit ab ist" in texte
    assert "Pflicht — Überspringen bleibt möglich" in texte

    # Die Grundzeile abwählen: Was an ihr hängt, geht mit aus — und kommt mit ihr zurück
    grund = _daten(ansicht, ("kursplan_zeile", marke))
    ziel = _daten(ansicht, ("kursplan_zeile", f"{marke}#ziel"))
    weg = _daten(ansicht, ("kursplan_zeile", "weg#weg"))
    grund.on_change()
    assert (grund.value, ziel.value, weg.value) == (False, False, False)
    assert ziel.disabled and weg.disabled and not grund.disabled
    assert _daten(ansicht, UEBERNEHMEN).disabled is True
    grund.on_change()
    assert (grund.value, ziel.value, weg.value) == (True, True, True)
    assert not ziel.disabled and _daten(ansicht, UEBERNEHMEN).disabled is False

    # Eine Zeile abwählen: „Übernehmen“ ändert nur das Gewählte
    weg.on_change()
    assert weg.value is False and ziel.value is True
    _daten(ansicht, UEBERNEHMEN).on_click()
    plan = state.kurse.kursplan(kurs, profil)
    assert [(i.exercise_id, i.kurs_marke, i.target) for i in plan.items] == [
        (ue["Planke"].id, "a", {"hold": [60]}),
        (kaefer.id, marke, {"reps": [30]}),
    ]
    assert not plan.ablauf.an  # der Weg blieb weg: weiter eine Liste
    assert _offene_wahl(state) == {}  # im Kursplan fest — keine offene Wahl mehr

    # Danach: die Wahl ist fest, zwei sind übernommen, der Weg bleibt angeboten
    ansicht = _kapitel(page, state, kurs, zwei)
    chip = _daten(ansicht, ("wahl", "wahl", kaefer.id))
    assert chip.selected is True and chip.disabled is True
    assert _daten(ansicht, ("wahl", "wahl", bruecke.id)).disabled is True
    assert "2 schon übernommen" in _texte(ansicht)
    assert "Käfer kommt dazu" not in _texte(ansicht)
    assert _daten(ansicht, ("kursplan_zeile", "weg#weg")).value is True
    assert not _hat(ansicht, "plan_anlegen")
    _daten(ansicht, UEBERNEHMEN).on_click()
    assert state.kurse.kursplan(kurs, profil).ablauf.an  # jetzt ein Workout mit dem Weg
    assert STAND in _texte(_kapitel(page, state, kurs, zwei))


def _bis_kapitel_3(state: AppState) -> tuple[Kurs, Kapitel, str]:
    """Kapitel 1 übernommen, die Person stellt die Planke selbst auf 45 s, Kapitel 3 ist dran.
    Zurück: Kurs, Kapitel 3 und die ID der Planübung."""
    kurs, _ue = _kurs(state)
    eins, zwei, drei = kurs.kapitel
    profil = state.profil.id
    state.kurse.starten(kurs, profil)
    plan = state.kurse.plan_uebernehmen(kurs, eins, profil, {"a", "a#ziel"})
    state.kurse.kapitel_abschliessen(kurs, eins, profil)
    state.kurse.kapitel_abschliessen(kurs, zwei, profil, uebersprungen=True)
    state.plaene.ziel_setzen(plan.items[0].id, {"hold": [45]})  # im Plan-Editor geändert
    return kurs, drei, plan.items[0].id


def test_dein_plan_weicht_ab_lassen_bleibt_und_fragt_nicht_wieder(page, state) -> None:
    kurs, drei, planke = _bis_kapitel_3(state)
    ansicht = _kapitel(page, state, kurs, drei)
    texte = _texte(ansicht)
    assert "Dein Plan weicht ab" in texte
    assert "Planke: Du hast 45 s eingestellt. Der Kurs schlägt 75 s vor." in texte
    assert "Was du selbst geändert hast, bleibt — außer du übernimmst den Vorschlag." in texte
    assert not [x for x in _alle(ansicht) if isinstance(x, ft.Checkbox)]  # Knöpfe statt Haken
    lassen = _daten(ansicht, ("kursplan_lassen", "mehr#ziel"))
    trotz = _daten(ansicht, ("kursplan_trotz", "mehr#ziel"))
    assert (lassen.content, trotz.content) == ("45 s lassen", "75 s übernehmen")
    assert lassen.icon == ft.Icons.CHECK and trotz.icon is None  # Vorgabe: lassen

    _daten(ansicht, UEBERNEHMEN).on_click()
    assert state.plaene.item_laden(planke).target == {"hold": [45]}
    assert _meldung(page) == "Dein Plan bleibt, wie er ist"
    # Beim nächsten Öffnen steht die Abweichung nicht mehr da
    ansicht = _kapitel(page, state, kurs, drei)
    assert "Dein Plan weicht ab" not in _texte(ansicht) and STAND in _texte(ansicht)
    assert not _hat(ansicht, UEBERNEHMEN)


def test_dein_plan_weicht_ab_uebernehmen_setzt_den_kurswert(page, state) -> None:
    kurs, drei, planke = _bis_kapitel_3(state)
    ansicht = _kapitel(page, state, kurs, drei)
    _daten(ansicht, ("kursplan_trotz", "mehr#ziel")).on_click()
    # der gewählte Knopf trägt den Haken
    assert _daten(ansicht, ("kursplan_trotz", "mehr#ziel")).icon == ft.Icons.CHECK
    assert _daten(ansicht, ("kursplan_lassen", "mehr#ziel")).icon is None
    # … und zurück zu „lassen“ geht auch
    _daten(ansicht, ("kursplan_lassen", "mehr#ziel")).on_click()
    assert _daten(ansicht, ("kursplan_lassen", "mehr#ziel")).icon == ft.Icons.CHECK
    _daten(ansicht, ("kursplan_trotz", "mehr#ziel")).on_click()
    assert state.plaene.item_laden(planke).target == {"hold": [45]}  # noch nichts geändert

    _daten(ansicht, UEBERNEHMEN).on_click()
    assert state.plaene.item_laden(planke).target == {"hold": [75]}
    assert _meldung(page) == "Plan geändert — er steht auf „Heute“"
    assert STAND in _texte(_kapitel(page, state, kurs, drei))


def test_aus_dem_plan_genommen_fragt_und_das_ziel_haengt_an_der_antwort(page, state) -> None:
    """Die Person hat eine Übung, die der Kurs brachte, aus dem Plan genommen: Das Kapitel
    fragt („Planke übernehmen“ · „Plan so lassen“, Vorgabe lassen). Das Ziel der Übung gilt
    nur mit ihr — solange „lassen“ gewählt ist, ist seine Zeile aus."""
    kurs, _ue = _kurs(state)
    eins = kurs.kapitel[0]
    profil = state.profil.id
    state.kurse.starten(kurs, profil)
    plan = state.kurse.plan_uebernehmen(kurs, eins, profil, {"a", "a#ziel"})
    state.plaene.uebung_entfernen(plan.items[0].id)  # im Plan-Editor entfernt

    ansicht = _kapitel(page, state, kurs, eins)
    texte = _texte(ansicht)
    assert "Dein Plan weicht ab" in texte
    assert (
        "Planke: Du hast die Übung aus deinem Plan genommen. Der Kurs bringt sie wieder mit."
        in texte
    )
    trotz = _daten(ansicht, ("kursplan_trotz", "a"))
    lassen = _daten(ansicht, ("kursplan_lassen", "a"))
    assert (trotz.content, lassen.content) == ("Planke übernehmen", "Plan so lassen")
    assert lassen.icon == ft.Icons.CHECK and trotz.icon is None
    ziel = _daten(ansicht, ("kursplan_zeile", "a#ziel"))
    assert ziel.value is False and ziel.disabled is True
    trotz.on_click()
    assert ziel.value is True and ziel.disabled is False
    _daten(ansicht, ("kursplan_lassen", "a")).on_click()
    assert ziel.value is False and ziel.disabled is True

    # „Plan so lassen“: nichts kommt zurück, und gefragt wird nicht wieder
    _daten(ansicht, UEBERNEHMEN).on_click()
    assert state.kurse.kursplan(kurs, profil).items == []
    assert _meldung(page) == "Dein Plan bleibt, wie er ist"
    ansicht = _kapitel(page, state, kurs, eins)
    assert "Dein Plan weicht ab" not in _texte(ansicht) and not _hat(ansicht, UEBERNEHMEN)


def test_aus_dem_plan_genommen_uebernehmen_bringt_die_uebung_mit_ziel_zurueck(page, state) -> None:
    kurs, ue = _kurs(state)
    eins = kurs.kapitel[0]
    profil = state.profil.id
    state.kurse.starten(kurs, profil)
    plan = state.kurse.plan_uebernehmen(kurs, eins, profil, {"a", "a#ziel"})
    state.plaene.uebung_entfernen(plan.items[0].id)
    ansicht = _kapitel(page, state, kurs, eins)
    _daten(ansicht, ("kursplan_trotz", "a")).on_click()
    _daten(ansicht, UEBERNEHMEN).on_click()
    wieder = state.kurse.kursplan(kurs, profil)
    assert [(i.exercise_id, i.target) for i in wieder.items] == [(ue["Planke"].id, {"hold": [60]})]
    assert _meldung(page) == "Plan geändert — er steht auf „Heute“"


def test_anker_fehlt_und_entfaellt_sind_hinweiszeilen_ohne_haken(page, state) -> None:
    """Die Person hat die Planke aus dem Plan genommen: Die gewählte Übung kommt ans Ende
    (und sagt es), der Weg von der Planke und die Einstellung an ihr entfallen."""
    kurs, ue = _kurs(state)
    eins, zwei, drei = kurs.kapitel
    profil = state.profil.id
    kaefer = ue["Käfer"]
    state.kurse.starten(kurs, profil)
    plan = state.kurse.plan_uebernehmen(kurs, eins, profil, {"a", "a#ziel"})
    state.kurse.kapitel_abschliessen(kurs, eins, profil)
    state.plaene.uebung_entfernen(plan.items[0].id)
    _test_eintragen(state, kaefer, {"reps": [30]})

    ansicht = _kapitel(page, state, kurs, zwei)
    _daten(ansicht, ("wahl", "wahl", kaefer.id)).on_select()
    marke = f"dazu:{kaefer.id}"
    texte = _texte(ansicht)
    assert "Käfer kommt ans Ende" in texte
    assert "Planke, hinter die es gehört, ist nicht mehr in deinem Plan." in texte
    assert "Ein Weg entfällt" in texte and "Planke ist nicht mehr in deinem Plan." in texte
    assert _hat(ansicht, ("kursplan_hinweis", marke)) and _hat(
        ansicht, ("kursplan_hinweis", "weg#weg")
    )
    # ohne Haken: nur das Ziel lässt sich abwählen
    assert [x.data for x in _alle(ansicht) if isinstance(x, ft.Checkbox)] == [
        ("kursplan_zeile", f"{marke}#ziel")
    ]
    _daten(ansicht, UEBERNEHMEN).on_click()
    nachher = state.kurse.kursplan(kurs, profil)
    assert [(i.exercise_id, i.target) for i in nachher.items] == [(kaefer.id, {"reps": [30]})]

    # Kapitel 3 hat nur noch einen Hinweis — nichts zu übernehmen
    state.kurse.kapitel_abschliessen(kurs, zwei, profil, uebersprungen=True)
    ansicht = _kapitel(page, state, kurs, drei)
    assert "Eine Einstellung entfällt" in _texte(ansicht)
    assert not _hat(ansicht, UEBERNEHMEN) and STAND not in _texte(ansicht)


def test_spaeter_klappt_die_karte_zu_und_speichert_nichts(page, state) -> None:
    kurs, _ue = _kurs(state)
    eins = kurs.kapitel[0]
    ansicht = _kapitel(page, state, kurs, eins)
    _daten(ansicht, "kursplan_spaeter").on_click()
    assert "Planke kommt dazu" not in _texte(ansicht) and not _hat(ansicht, UEBERNEHMEN)
    assert "Das ändert sich an deinem Plan" in _texte(ansicht)
    assert state.kurse.kursplan(kurs, state.profil.id) is None
    _daten(ansicht, "kursplan_zeigen").on_click()
    assert "Planke kommt dazu" in _texte(ansicht) and _hat(ansicht, UEBERNEHMEN)
    # beim nächsten Öffnen steht sie wieder da
    assert "Planke kommt dazu" in _texte(_kapitel(page, state, kurs, eins))


def test_gesperrtes_kapitel_zeigt_keine_karte_und_tage_zaehlen_erst_mit_dem_plan(
    page, state
) -> None:
    kurs, _ue = _kurs(state)
    eins, zwei, _drei = kurs.kapitel
    profil = state.profil.id
    # Kapitel 2 ist noch gesperrt: nur lesen
    ansicht = _kapitel(page, state, kurs, zwei)
    assert not _hat(ansicht, "kursplan_karte")
    # Kapitel 1 ohne „Übernehmen“ abgeschlossen: Der Kursplan hat noch keine Übung
    _kapitel(page, state, kurs, eins)
    state.kurse.kapitel_abschliessen(kurs, eins, profil)
    ansicht = _kapitel(page, state, kurs, zwei)
    assert _hat(ansicht, "kursplan_karte")
    assert "Zählt, sobald dein Kursplan Übungen hat." in _texte(ansicht)
    # Das fertige Kapitel 1 bietet weiter an, was liegen blieb
    ansicht = _kapitel(page, state, kurs, eins)
    _daten(ansicht, UEBERNEHMEN).on_click()
    assert state.kurse.kursplan(kurs, profil) is not None
    assert "Zählt, sobald dein Kursplan Übungen hat." not in _texte(
        _kapitel(page, state, kurs, zwei)
    )


def test_erstes_kapitel_oeffnen_legt_den_kursplan_aus_der_grundlage_an(page, state) -> None:
    """Wer das erste Kapitel gleich in der Liste antippt, statt „Kurs beginnen“ zu wählen,
    bekommt den Kursplan aus der Grundlage genauso."""
    ue = _uebungen(state)
    vorlage = PlanVorlage("Basis", items=[VorlageItem(ue["Seitstütz"].id)])
    kurs = Kurs(
        name="Mit Grundlage",
        kursplan=Kursplan("Rumpf", vorlage=vorlage),
        kapitel=[Kapitel(titel="Lesen", text="Nur Text."), Kapitel(titel="Zwei")],
    )
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    ansicht = _kapitel(page, state, kurs, kurs.kapitel[0])
    plan = state.kurse.kursplan(kurs, state.profil.id)
    assert plan is not None
    assert [(i.exercise_id, i.kurs_marke) for i in plan.items] == [(ue["Seitstütz"].id, "g:1")]
    assert not _hat(ansicht, "kursplan_karte")  # ein Kapitel ohne Bausteine hat keine Karte


# ---------------------------------------------------------------------------
# Kursseite, von vorn, Kurs ohne Kursplan
# ---------------------------------------------------------------------------


def test_kursseite_zeigt_dein_kursplan_mit_trainieren(page, state) -> None:
    kurs, ue = _kurs(state)
    eins, zwei, _drei = kurs.kapitel
    profil = state.profil.id
    assert "DEIN KURSPLAN" not in _texte(kurs_view(page, state, kurs))  # noch keiner

    state.kurse.starten(kurs, profil)
    state.kurse.plan_uebernehmen(kurs, eins, profil, {"a", "a#ziel"})
    state.kurse.kapitel_abschliessen(kurs, eins, profil)
    wahl = {"wahl": [ue["Käfer"].id]}
    plan = state.kurse.plan_uebernehmen(kurs, zwei, profil, {f"dazu:{ue['Käfer'].id}"}, wahl=wahl)
    ansicht = kurs_view(page, state, kurs)
    texte = _texte(ansicht)
    assert "DEIN KURSPLAN" in texte and "Rumpf" in texte
    assert "Planke · Käfer — wächst mit den Kapiteln" in texte
    zeile = _daten(ansicht, ("kursplan", plan.id))
    knopf = next(x for x in _alle(zeile) if getattr(x, "data", None) in ("liste", "workout"))
    assert "Trainieren" in _texte(knopf)
    asyncio.run(knopf.on_click())
    assert page.route == f"/plan/{plan.id}" and state.reiter == "heute"
    asyncio.run(zeile.on_click())  # Tipp auf die Karte öffnet den Plan
    assert page.route == f"/plaene/{plan.id}"


def test_von_vorn_frueherer_durchlauf_und_wie_beim_letzten_mal(page, state) -> None:
    kurs, ue = _kurs(state)
    eins, zwei, _drei = kurs.kapitel
    profil = state.profil.id
    kaefer = ue["Käfer"]
    state.kurse.starten(kurs, profil)
    state.kurse.plan_uebernehmen(kurs, eins, profil, {"a", "a#ziel"})
    state.kurse.kapitel_abschliessen(kurs, eins, profil)
    alt = state.kurse.plan_uebernehmen(
        kurs, zwei, profil, {f"dazu:{kaefer.id}"}, wahl={"wahl": [kaefer.id]}
    )
    # Im laufenden Durchlauf gibt es „Wie beim letzten Mal“ nicht
    assert not _hat(_kapitel(page, state, kurs, zwei), ("wie_letztes_mal", "wahl"))

    state.kurse.zuruecksetzen(kurs, profil)
    ansicht = kurs_view(page, state, kurs)
    texte = _texte(ansicht)
    assert "DEIN KURSPLAN" in texte and "Rumpf · Durchlauf 1" in texte
    assert "früherer Durchlauf · deaktiviert" in texte
    assert "Im neuen Durchlauf baut der Kurs mit dir einen neuen Plan." in texte
    assert _hat(ansicht, ("frueherer_plan", alt.id)) and not _hat(ansicht, ("kursplan", alt.id))

    # Neuer Durchlauf: Kapitel 1 übernehmen, in Kapitel 2 ist nichts vorgewählt
    ansicht = _kapitel(page, state, kurs, eins)
    _daten(ansicht, UEBERNEHMEN).on_click()
    state.kurse.kapitel_abschliessen(kurs, eins, profil)
    ansicht = _kapitel(page, state, kurs, zwei)
    chip = _daten(ansicht, ("wahl", "wahl", kaefer.id))
    assert chip.selected is False and chip.disabled is False
    assert "Deine Auswahl kommt dazu" in _texte(ansicht)
    _daten(ansicht, ("wie_letztes_mal", "wahl")).on_click()  # nur eine Vorbelegung
    assert chip.selected is True
    assert "Käfer kommt dazu" in _texte(ansicht)
    neu = state.kurse.kursplan(kurs, profil)
    assert neu is not None and neu.id != alt.id and len(neu.items) == 1
    # Die Kursseite zeigt den neuen Plan und darunter den früheren
    ansicht = kurs_view(page, state, kurs)
    assert _hat(ansicht, ("kursplan", neu.id)) and _hat(ansicht, ("frueherer_plan", alt.id))


def _bis_kapitel_2(state: AppState, kurs: Kurs) -> None:
    """Für das aktive Profil: Kapitel 1 übernommen und abgeschlossen, Kapitel 2 ist dran."""
    eins = kurs.kapitel[0]
    profil = state.profil.id
    state.kurse.starten(kurs, profil)
    state.kurse.plan_uebernehmen(kurs, eins, profil, {"a", "a#ziel"})
    state.kurse.kapitel_abschliessen(kurs, eins, profil)


def _test_knoepfe(ansicht) -> list[tuple]:
    """Die „Zur Übung“-Knöpfe aller Testkarten — ihre Kennungen."""
    return [
        x.data
        for x in _alle(ansicht)
        if isinstance(getattr(x, "data", None), tuple) and x.data[0] == "test_oeffnen"
    ]


def test_test_misst_die_gewaehlte_und_die_karte_folgt_der_wahl(page, state) -> None:
    """Ben, 16.11.2026: Der Test gilt der Übung, die die Person gewählt hat (``aus``) — nicht
    einer, die der Kurs fest nennt. Ohne Wahl nur die Aufforderung; mit Wahl Name, Wert und
    „Zur Übung“ **der Gewählten**; wechselt die Wahl, folgt die Karte, und das Ziel in der
    Sammelkarte kommt aus ihrem Wert."""
    kurs, ue = _kurs(state, test_aus=True)
    zwei = kurs.kapitel[1]
    profil = state.profil.id
    kaefer, bruecke = ue["Käfer"], ue["Brücke"]
    _bis_kapitel_2(state, kurs)

    # Ohne Wahl: die Aufforderung und der Hinweis — kein Knopf, es gibt noch keine Übung
    ansicht = _kapitel(page, state, kurs, zwei)
    texte = _texte(ansicht)
    assert "Deine Auswahl" in texte
    assert "Triff zuerst deine Auswahl — der Test gilt der Übung, die du wählst." in texte
    assert _hat(ansicht, ("test_wahl_fehlt", "test")) and _test_knoepfe(ansicht) == []

    # Käfer gewählt: Die Karte nennt ihn, „Zur Übung“ führt zu ihm — nicht zu einer anderen
    _daten(ansicht, ("wahl", "wahl", kaefer.id)).on_select()
    texte = _texte(ansicht)
    assert "Käfer" in texte
    assert "Noch kein Eintrag bei „Käfer“, seit du dieses Kapitel öffnest." in texte
    assert not _hat(ansicht, ("test_wahl_fehlt", "test"))
    assert _test_knoepfe(ansicht) == [("test_oeffnen", "test", kaefer.id)]
    knopf = _daten(ansicht, ("test_oeffnen", "test", kaefer.id))
    assert knopf.content == "Zur Übung"
    asyncio.run(knopf.on_click())
    assert page.route == f"/uebung/{kaefer.id}"

    # Eingetragen und zurück: Die Wahl steht noch (P212), der Wert der Gewählten erscheint,
    # und die Sammelkarte setzt ihr Ziel daraus
    _test_eintragen(state, kaefer, {"reps": [24, 30]})
    ansicht = _kapitel(page, state, kurs, zwei)
    assert _daten(ansicht, ("testwert", "test", kaefer.id)).value == "30 Wdh."
    assert _daten(ansicht, ("test_oeffnen", "test", kaefer.id)).content == "Nochmal"
    assert "Ziel für Käfer: 30 Wiederholungen" in _texte(ansicht)

    # Wahl wechseln: Die Karte folgt — die Brücke hat noch keinen Eintrag, der Wert des
    # Käfers zählt für sie nicht
    _daten(ansicht, ("wahl", "wahl", bruecke.id)).on_select()
    texte = _texte(ansicht)
    assert "Noch kein Eintrag bei „Brücke“, seit du dieses Kapitel öffnest." in texte
    assert "Noch kein Eintrag bei „Käfer“, seit du dieses Kapitel öffnest." not in texte
    assert not _hat(ansicht, ("testwert", "test", kaefer.id))
    assert _test_knoepfe(ansicht) == [("test_oeffnen", "test", bruecke.id)]
    assert "Ziel für Brücke" in texte and "aus deinem Test — mach ihn zuerst" in texte
    assert "Ziel für Käfer: 30 Wiederholungen" not in texte

    _test_eintragen(state, bruecke, {"reps": [12]})
    ansicht = _kapitel(page, state, kurs, zwei)
    assert _daten(ansicht, ("testwert", "test", bruecke.id)).value == "12 Wdh."
    assert "Ziel für Brücke: 12 Wiederholungen" in _texte(ansicht)
    _daten(ansicht, UEBERNEHMEN).on_click()
    plan = state.kurse.kursplan(kurs, profil)
    assert [(i.exercise_id, i.target) for i in plan.items][1] == (bruecke.id, {"reps": [12]})
    # Fest im Kursplan: Die Testkarte nennt weiter die Gewählte
    ansicht = _kapitel(page, state, kurs, zwei)
    assert _daten(ansicht, ("testwert", "test", bruecke.id)).value == "12 Wdh."
    assert _test_knoepfe(ansicht) == [("test_oeffnen", "test", bruecke.id)]


def test_test_der_gewaehlten_mit_auswahl_im_frueheren_kapitel(page, state) -> None:
    """Steht die Auswahl in einem früheren Kapitel, gilt für den Test, was dort in den
    Kursplan übernommen ist — bis dahin sagt die Karte, wo zu wählen ist."""
    kurs, ue = _kurs(state, test_aus=True)
    _eins, zwei, drei = kurs.kapitel
    profil = state.profil.id
    bruecke = ue["Brücke"]
    _bis_kapitel_2(state, kurs)
    state.kurse.kapitel_abschliessen(kurs, zwei, profil, uebersprungen=True)

    # Kapitel 2 übersprungen, nichts gewählt: Kapitel 3 kann die Übung nicht nennen
    ansicht = _kapitel(page, state, kurs, drei)
    hinweis = _daten(ansicht, ("test_wahl_fehlt", "test3"))
    assert hinweis.value == (
        "Der Test gilt der Übung, die du in einem früheren Kapitel wählst — "
        "übernimm deine Wahl dort zuerst in deinen Kursplan."
    )
    assert _test_knoepfe(ansicht) == []

    # In Kapitel 2 gewählt und übernommen: Kapitel 3 nennt die Gewählte
    ansicht = _kapitel(page, state, kurs, zwei)
    _daten(ansicht, ("wahl", "wahl", bruecke.id)).on_select()
    _daten(ansicht, UEBERNEHMEN).on_click()
    ansicht = _kapitel(page, state, kurs, drei)
    assert "Brücke" in _texte(ansicht)
    assert not _hat(ansicht, ("test_wahl_fehlt", "test3"))
    knopf = _daten(ansicht, ("test_oeffnen", "test3", bruecke.id))
    asyncio.run(knopf.on_click())
    assert page.route == f"/uebung/{bruecke.id}"
    _test_eintragen(state, bruecke, {"reps": [15]})
    ansicht = _kapitel(page, state, kurs, drei)
    assert _daten(ansicht, ("testwert", "test3", bruecke.id)).value == "15 Wdh."


def test_offene_wahl_gilt_je_profil_und_von_vorn_verwirft_sie(page, state) -> None:
    """P212: Die offene Wahl gehört dem Profil, das sie traf — ein zweites sieht sie nicht,
    und wer zurück wechselt, findet seine wieder. „Von vorn“ verwirft sie: Im neuen Durchlauf
    ist nichts vorgewählt. Gehalten wird nur im Speicher."""
    kurs, ue = _kurs(state)
    zwei = kurs.kapitel[1]
    erstes = state.profil.id
    kaefer, bruecke = ue["Käfer"], ue["Brücke"]
    _bis_kapitel_2(state, kurs)
    ansicht = _kapitel(page, state, kurs, zwei)
    _daten(ansicht, ("wahl", "wahl", kaefer.id)).on_select()
    _daten(ansicht, ("wahl", "wahl", kaefer.id)).on_select()  # wieder abgewählt: kein Eintrag
    assert _offene_wahl(state) == {}
    _daten(ansicht, ("wahl", "wahl", kaefer.id)).on_select()
    # nichts davon steht in der Datenbank: Ohne die Sitzung ist die Wahl nicht getroffen
    assert {z.stand for z in state.kurse.plan_aenderungen(kurs, zwei, erstes)} == {"offen"}

    # Ein zweites Profil sieht sie nicht — und hält seine eigene
    zweites = state.profil_anlegen("Zweite").id
    _bis_kapitel_2(state, kurs)
    ansicht = _kapitel(page, state, kurs, zwei)
    assert _daten(ansicht, ("wahl", "wahl", kaefer.id)).selected is False
    assert "Deine Auswahl kommt dazu" in _texte(ansicht)
    _daten(ansicht, ("wahl", "wahl", bruecke.id)).on_select()
    assert _offene_wahl(state) == {
        (erstes, zwei.id): {"wahl": [kaefer.id]},
        (zweites, zwei.id): {"wahl": [bruecke.id]},
    }
    state.profil_wechseln(erstes)
    ansicht = _kapitel(page, state, kurs, zwei)
    assert _daten(ansicht, ("wahl", "wahl", kaefer.id)).selected is True
    assert _daten(ansicht, ("wahl", "wahl", bruecke.id)).selected is False
    assert "Käfer kommt dazu" in _texte(ansicht)

    # „Von vorn“ im Menü der Kursseite verwirft die Wahl dieses Profils
    seite = kurs_view(page, state, kurs)
    menue = next(a for a in seite.appbar.actions if isinstance(a, ft.PopupMenuButton))
    next(i for i in menue.items if i.content == "Von vorn beginnen").on_click()
    next(x for x in page.dialoge[-1].actions if isinstance(x, ft.FilledButton)).on_click()
    assert _offene_wahl(state) == {(zweites, zwei.id): {"wahl": [bruecke.id]}}
    _bis_kapitel_2(state, kurs)
    ansicht = _kapitel(page, state, kurs, zwei)
    assert _daten(ansicht, ("wahl", "wahl", kaefer.id)).selected is False
    assert "Deine Auswahl kommt dazu" in _texte(ansicht)

    # Beginnt der Kurs nicht über das Menü von vorn, gilt die alte Wahl trotzdem nicht: Das
    # Kapitel wird neu erreicht, der Stempel passt nicht mehr
    state.profil_wechseln(zweites)
    state.kurse.zuruecksetzen(kurs, zweites)
    _bis_kapitel_2(state, kurs)
    ansicht = _kapitel(page, state, kurs, zwei)
    assert _daten(ansicht, ("wahl", "wahl", bruecke.id)).selected is False
    assert _offene_wahl(state) == {}


def test_offene_wahl_ist_weg_wenn_der_kurs_entfernt_wird(page, state) -> None:
    """P212: Mit dem Kurs geht seine offene Wahl — die Kursliste räumt auf; und käme der
    Kurs wieder, bevor sie das tat, gälte die alte Wahl nicht mehr (Stempel)."""
    kurs, ue = _kurs(state)
    zwei = kurs.kapitel[1]
    kaefer = ue["Käfer"]
    _bis_kapitel_2(state, kurs)
    _daten(_kapitel(page, state, kurs, zwei), ("wahl", "wahl", kaefer.id)).on_select()
    assert _offene_wahl(state) == {(state.profil.id, zwei.id): {"wahl": [kaefer.id]}}
    state.kurse.entfernen(kurs)
    state.kurse.wiederherstellen(kurs.id)
    wieder = state.kurse.laden(kurs.id)
    ansicht = _kapitel(page, state, wieder, wieder.kapitel[1])
    assert _daten(ansicht, ("wahl", "wahl", kaefer.id)).selected is False
    assert _offene_wahl(state) == {}

    _daten(ansicht, ("wahl", "wahl", kaefer.id)).on_select()
    assert _offene_wahl(state)
    state.kurse.entfernen(wieder)
    kurse_liste(page, state)
    assert _offene_wahl(state) == {}


def test_kurs_ohne_kursplan_sieht_aus_wie_vorher(page, state) -> None:
    """Kapitelpläne wie bisher: „Plan anlegen“ steht da, keine Sammelkarte, keine Karte „Dein
    Kursplan“ — auch wenn im Kapitel ein Baustein steht (er tut dort nichts)."""
    ue = _uebungen(state)
    planke = ue["Planke"]
    kapitel = Kapitel(
        titel="Rumpf",
        plaene=[PlanVorlage("Rumpf Woche 1", items=[VorlageItem(planke.id)])],
        bloecke=[
            Block(TEST, id="test", uebung=planke.id, feld="hold"),
            Block(PLAN_UEBUNG, id="a", uebung=ue["Käfer"].id),
        ],
    )
    kurs = Kurs(name="Ohne Kursplan", kapitel=[kapitel])
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    ansicht = _kapitel(page, state, kurs, kurs.kapitel[0])
    assert _daten(ansicht, "plan_anlegen").disabled is True
    assert not _hat(ansicht, "kursplan_karte")
    assert "Das ändert sich an deinem Plan" not in _texte(ansicht)
    _test_eintragen(state, planke, {"hold": [48]})
    ansicht = _kapitel(page, state, kurs, kurs.kapitel[0])
    assert "Dein Eintrag bei „Planke“. Im Plan wird daraus das Ziel: 48s Haltezeit." in _texte(
        ansicht
    )
    _daten(ansicht, "plan_anlegen").on_click()
    (plan,) = state.kurse.kapitel_plaene(kurs.kapitel[0].id, state.profil.id)
    assert plan.items[0].target == {"hold": [48]} and plan.kurs_id is None
    assert "DEIN KURSPLAN" not in _texte(kurs_view(page, state, kurs))


def test_kapitel_mit_eigenen_vorlagen_im_kursplan_kurs_behaelt_plan_anlegen(page, state) -> None:
    """Kapitelpläne neben dem Kursplan (`KursRepo.kapitel_erreichen`): Hat ein Kapitel eigene
    Plan-Vorlagen und einen Test, entsteht sein Plan weiter mit „Plan anlegen“ — sonst
    entstünde er nie."""
    ue = _uebungen(state)
    planke = ue["Planke"]
    kapitel = Kapitel(
        titel="Beides",
        plaene=[PlanVorlage("Extra", items=[VorlageItem(planke.id)])],
        bloecke=[
            Block(TEST, id="test", uebung=planke.id, feld="hold"),
            Block(PLAN_UEBUNG, id="a", uebung=ue["Käfer"].id),
        ],
    )
    kurs = Kurs(name="Beides", kursplan=Kursplan("Rumpf"), kapitel=[kapitel])
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    _kapitel(page, state, kurs, kurs.kapitel[0])
    _test_eintragen(state, planke, {"hold": [48]})
    ansicht = _kapitel(page, state, kurs, kurs.kapitel[0])
    assert _hat(ansicht, "kursplan_karte") and "Käfer kommt dazu" in _texte(ansicht)
    _daten(ansicht, "plan_anlegen").on_click()
    (extra,) = state.kurse.kapitel_plaene(kurs.kapitel[0].id, state.profil.id)
    assert extra.items[0].target == {"hold": [48]}
    assert state.kurse.kursplan(kurs, state.profil.id) is None  # der wartet auf „Übernehmen“
