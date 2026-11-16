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
from trainingsapp.ui.views.kurse import kapitel_view, kurs_view  # noqa: E402

UEBERNEHMEN = "kursplan_uebernehmen"
STAND = "Dein Plan ist auf dem Stand dieses Kapitels."


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


def _kurs(state: AppState, kursplan: Kursplan | None = None) -> tuple[Kurs, dict[str, Exercise]]:
    """Bens Beispiel als Kurs mit Kursplan — gespeichert und wieder geladen."""
    ue = _uebungen(state)
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
                    Block(TEST, id="test", uebung=ue["Käfer"].id, feld="reps"),
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
                bloecke=[Block(PLAN_EINSTELLEN, id="mehr", an="a", ziel={"hold": [75]})],
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

    # Der Test: ein gewöhnlicher Eintrag. Die neue Ansicht hat die Wahl nicht mehr — sie
    # hält nur, bis übernommen ist
    _test_eintragen(state, kaefer, {"reps": [24, 30]})
    ansicht = _kapitel(page, state, kurs, zwei)
    assert _daten(ansicht, ("wahl", "wahl", bruecke.id)).selected is False
    _daten(ansicht, ("wahl", "wahl", kaefer.id)).on_select()
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
