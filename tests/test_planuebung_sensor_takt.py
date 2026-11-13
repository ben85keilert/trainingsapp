"""Die Planübung folgt der Übung auch beim Beschleunigungssensor und beim Takt (Ben, 5.11.2026,
A6; `docs/plan_beschleunigung.md` §13, `docs/plan_taktgeber.md` §5,
`docs/plan_uebungen_einstellen.md`): `PlanItem.acc`/`PlanItem.takt` (``None`` = wie die Übung,
Migration 039), die Auflösung in `core.zaehlen.wirksame_wahl` und
`core.uebung_timer.takt_der_uebung`/`takt_fuer` (Uhr für jetzt > Abschnitt > Planübung >
Übung), `core.standards` (Abweichungen, Bereinigen, Übernehmen, Alles wie die Übung), die
Rundreise durchs Repository, die Migration und das Paketfeld je Planübung. Ohne flet."""

from __future__ import annotations

from dataclasses import replace

from trainingsapp.core import standards
from trainingsapp.core import zaehlen as zl
from trainingsapp.core.kurse import Kapitel, PlanVorlage, VorlageItem, plan_aus_vorlage
from trainingsapp.core.models import Exercise, Plan, PlanItem
from trainingsapp.core.pakete import PaketPlan, paketplan_aus, plan_stand
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
from trainingsapp.core.takt import AUS, VORLAGEN
from trainingsapp.core.timer import Abschnitt
from trainingsapp.core.uebung_timer import takt_der_uebung, takt_fuer
from trainingsapp.core.zaehlen import SensorWahl
from trainingsapp.data.db import MIGRATIONS_DIR, migrieren, verbinden
from trainingsapp.data.repositories import ExerciseRepo, PlanRepo


def _kniebeuge(*keys: str, **mehr) -> Exercise:
    spec = ResultSpec(fields=[f for k in (keys or ("reps",)) if (f := vorrat_feld(k))])
    return Exercise(name="Kniebeuge", result_spec=spec, **mehr)


# -- Auflösung --------------------------------------------------------------------------------


def test_sensor_karte_plan_vor_uebung_und_knopf_nur_mit_wiederholungsfeld() -> None:
    """`wirksame_wahl`: die der Planübung, sonst die der Übung. Wiederholungen zählt eine
    Planübung nur, wenn sie ein Wiederholungsfeld anbietet — auch mit eigener Karte."""
    u = _kniebeuge("reps", "reps_2", beschleunigung=SensorWahl(vorlage="kniebeuge", feld="reps_2"))
    folgt = PlanItem()
    assert zl.wirksame_wahl(u, folgt) is u.beschleunigung
    assert zl.wiederholungen_an(u, folgt) and not zl.atmung_an(u, folgt)
    assert zl.zaehlt_in(u, folgt) == "reps_2"
    eigen = PlanItem(acc=SensorWahl(wiederholungen=False, atmung=True))
    assert not zl.wiederholungen_an(u, eigen) and zl.atmung_an(u, eigen)
    assert zl.wirksame_wahl(u, eigen).vorlage == zl.VORLAGE_AUTO
    # „Zählt in“ nur, wenn die Planübung das Feld anbietet
    nur_erstes = PlanItem(felder=["reps"], acc=SensorWahl(feld="reps_2"))
    assert zl.zaehlt_in(u, nur_erstes) == "reps"
    # Kein Wiederholungsfeld im Plan: kein Zählen, auch wenn die Karte es will
    nur_abhaken = PlanItem(felder=[], acc=SensorWahl(wiederholungen=True))
    assert not zl.wiederholungen_an(u, nur_abhaken) and zl.zaehlt_in(u, nur_abhaken) is None
    assert zl.knopf_text(zl.wiederholungen_an(u, nur_abhaken), zl.atmung_an(u, nur_abhaken)) == ""
    # Atmung: die Vorgabe (Typ) bleibt die der Übung, die Planübung kann sie abschalten
    atmen = Exercise(name="Atmen", typen=["Atmung"])
    assert zl.atmung_an(atmen, PlanItem()) and not zl.atmung_an(
        atmen, PlanItem(acc=SensorWahl(atmung=False))
    )


def test_takt_vorrang_uhr_abschnitt_planuebung_uebung() -> None:
    """`takt_fuer`: Uhr für jetzt > Timer-Abschnitt > Planübung > Übung > keiner; ein leerer
    Takt in der Planübung heißt ausdrücklich keiner, `AUS` als Wahl schaltet alles ab."""
    u = Exercise(name="Atmen", takt=VORLAGEN["atmung_4_6"])
    im_plan = PlanItem(takt=VORLAGEN["metronom_1"])
    assert takt_der_uebung(u, PlanItem()) is VORLAGEN["atmung_4_6"]
    assert takt_der_uebung(u, im_plan) is VORLAGEN["metronom_1"]
    assert takt_der_uebung(u, PlanItem(takt=AUS)) is None
    assert takt_der_uebung(None, im_plan) is None
    abschnitt = Abschnitt("Box", 60, takt=VORLAGEN["box_4"])
    assert takt_fuer(u, item=im_plan) is VORLAGEN["metronom_1"]
    assert takt_fuer(u, abschnitt, item=im_plan) is VORLAGEN["box_4"]
    assert takt_fuer(u, abschnitt, VORLAGEN["atmung_4_7_8"], im_plan) is VORLAGEN["atmung_4_7_8"]
    assert takt_fuer(u, abschnitt, AUS, im_plan) is None
    assert takt_fuer(u, None, None, PlanItem(takt=AUS)) is None
    assert takt_fuer(Exercise(), item=PlanItem()) is None


# -- standards: Abweichungen, Bereinigen, Übernehmen --------------------------------------------


def test_abweichungen_bereinigt_und_alles_wie_die_uebung() -> None:
    u = _kniebeuge("reps", takt=VORLAGEN["kniebeuge_2_1_2"])
    assert standards.abweichungen(PlanItem(), u) == []
    gleich = PlanItem(acc=SensorWahl(), takt=VORLAGEN["kniebeuge_2_1_2"])
    assert standards.abweichungen(gleich, u) == []
    b = standards.bereinigt(gleich, u)
    assert b.acc is None and b.takt is None
    anders = PlanItem(acc=SensorWahl(atmung=True), takt=AUS)
    assert standards.abweichungen(anders, u) == ["Beschleunigungssensor", "Takt"]
    b = standards.bereinigt(anders, u)
    assert b.acc == SensorWahl(atmung=True) and b.takt is AUS
    assert standards.sensor_von(anders, u).atmung is True
    assert standards.takt_von(anders, u) is None and standards.takt_von(PlanItem(), u) is u.takt
    # „keiner“ gleicht „keiner“
    ohne = Exercise(name="Planke")
    assert standards.abweichungen(PlanItem(takt=AUS), ohne) == []
    assert standards.bereinigt(PlanItem(takt=AUS), ohne).takt is None
    # Alles wie die Übung
    zurueck = standards.vom_standard(u, anders)
    assert zurueck.acc is None and zurueck.takt is None


def test_in_die_uebung_uebernehmen_nimmt_sensor_und_takt_mit() -> None:
    u = _kniebeuge("reps", takt=VORLAGEN["kniebeuge_2_1_2"])
    hier = PlanItem(acc=SensorWahl(atmung=True, vorlage="liegestuetz"), takt=AUS)
    aenderungen, folgen, eigene = standards.uebernehmen_vorschau(
        hier, u, [("Morgens", PlanItem()), ("Reha", PlanItem(takt=VORLAGEN["box_4"]))]
    )
    assert aenderungen == ["Beschleunigungssensor wie im Plan", "kein Takt mehr"]
    assert folgen == ["Morgens"] and eigene == ["Reha – Takt"]
    neu = standards.als_standard(hier, u)
    assert neu.beschleunigung == hier.acc and neu.takt is None
    mit_takt = standards.als_standard(PlanItem(takt=VORLAGEN["box_4"]), u)
    assert mit_takt.takt is VORLAGEN["box_4"]
    assert standards.uebernehmen_vorschau(PlanItem(takt=VORLAGEN["box_4"]), u)[0] == [
        "Takt „Box 4-4-4-4“"
    ]


# -- Repository und Migration -------------------------------------------------------------------


def test_rundreise_null_heisst_wie_die_uebung_leer_heisst_keiner(tmp_path) -> None:
    con = verbinden(tmp_path / "app.db")
    migrieren(con)
    uebungen, plaene = ExerciseRepo(con), PlanRepo(con)
    u = _kniebeuge("reps")
    uebungen.speichern(u)
    plan = Plan(name="P")
    plaene.speichern(plan)
    item = plaene.uebung_hinzufuegen(plan.id, u.id)
    geladen = plaene.item_laden(item.id)
    assert geladen is not None and geladen.acc is None and geladen.takt is None
    zeile = con.execute("SELECT acc_json, takt_json FROM plan_item WHERE id = ?", (item.id,))
    assert tuple(zeile.fetchone()) == (None, None)
    # Eigene Karte und ausdrücklich kein Takt
    plaene.item_speichern(replace(geladen, acc=SensorWahl(atmung=True), takt=AUS))
    zeile = con.execute("SELECT acc_json, takt_json FROM plan_item WHERE id = ?", (item.id,))
    assert tuple(zeile.fetchone()) == ('{"atmung": true}', "{}")
    wieder = plaene.item_laden(item.id)
    assert wieder is not None and wieder.acc == SensorWahl(atmung=True)
    assert wieder.takt is not None and wieder.takt.leer
    assert takt_der_uebung(replace(u, takt=VORLAGEN["box_4"]), wieder) is None
    # Eine eigene Wahl mit den Vorgaben bleibt eine eigene („{}“ ist nicht NULL)
    plaene.item_speichern(replace(wieder, acc=SensorWahl(), takt=VORLAGEN["box_4"]))
    zeile = con.execute("SELECT acc_json FROM plan_item WHERE id = ?", (item.id,)).fetchone()
    assert zeile["acc_json"] == "{}"
    wieder = plaene.item_laden(item.id)
    assert wieder is not None and wieder.acc == SensorWahl()
    assert wieder.takt is not None and wieder.takt.name == "Box 4-4-4-4"
    # Der Plan mit seinen Übungen liest dieselben Spalten; Kaputtes heißt „wie die Übung“ —
    # nicht eine eigene Karte oder „kein Takt“, die die Übung überstimmten (Prüfrunde A6,
    # Befund 3); ein Takt ohne brauchbare Phase ebenso
    con.execute("UPDATE plan_item SET acc_json = '[1', takt_json = 'x' WHERE id = ?", (item.id,))
    con.commit()
    (im_plan,) = plaene.laden(plan.id).items
    assert im_plan.acc is None and im_plan.takt is None
    geladen = plaene.item_laden(item.id)
    assert geladen is not None and geladen.acc is None and geladen.takt is None
    con.execute(
        "UPDATE plan_item SET acc_json = '[]', takt_json = '{\"phasen\": \"x\"}' WHERE id = ?",
        (item.id,),
    )
    con.commit()
    (im_plan,) = plaene.laden(plan.id).items
    assert im_plan.acc is None and im_plan.takt is None
    # Zurück auf „wie die Übung“
    plaene.sensor_takt_setzen(item.id, None, None)
    wieder = plaene.item_laden(item.id)
    assert wieder is not None and wieder.acc is None and wieder.takt is None
    con.close()


def test_migration_039_alte_planuebungen_folgen_der_uebung(tmp_path) -> None:
    ordner = tmp_path / "bis038"
    ordner.mkdir()
    for datei in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if int(datei.name[:3]) <= 38:
            (ordner / datei.name).write_text(datei.read_text(encoding="utf-8"), encoding="utf-8")
    con = verbinden(tmp_path / "alt.db")
    assert migrieren(con, ordner) == 38
    jetzt = "2026-11-05T12:00:00+00:00"
    con.execute(
        "INSERT INTO exercise (id, name, category, result_spec_json, created_at, updated_at) "
        "VALUES ('u', 'Atmen', '', '{\"fields\": []}', ?, ?)",
        (jetzt, jetzt),
    )
    con.execute(
        "INSERT INTO plan (id, name, created_at, updated_at) VALUES ('p', 'P', ?, ?)",
        (jetzt, jetzt),
    )
    con.execute(
        "INSERT INTO plan_item (id, plan_id, exercise_id, sort_order, target_json) "
        "VALUES ('i', 'p', 'u', 0, 'null')"
    )
    con.commit()
    assert migrieren(con) == 59
    zeile = con.execute("SELECT acc_json, takt_json FROM plan_item WHERE id = 'i'").fetchone()
    assert tuple(zeile) == (None, None)
    item = PlanRepo(con).item_laden("i")
    assert item is not None and item.acc is None and item.takt is None
    con.close()


# -- Paket: je Planübung `beschleunigung` und `takt` --------------------------------------------


def test_paketplan_traegt_sensor_und_takt_je_planuebung() -> None:
    u = _kniebeuge("reps")
    plan = Plan(
        name="Beine",
        items=[
            PlanItem(exercise_id=u.id, order=0),
            PlanItem(
                exercise_id=u.id, order=1, acc=SensorWahl(atmung=True), takt=VORLAGEN["box_4"]
            ),
            PlanItem(exercise_id=u.id, order=2, acc=SensorWahl(), takt=AUS),
        ],
    )
    pp = paketplan_aus(plan, "beine")
    uebungen = pp.to_dict()["uebungen"]
    assert uebungen[0] == {"uebung": u.id}
    assert uebungen[1]["beschleunigung"] == {"atmung": True}
    assert uebungen[1]["takt"]["name"] == "Box 4-4-4-4"
    assert uebungen[2] == {"uebung": u.id, "beschleunigung": {}, "takt": {}}
    # Rundreise über den Paketstand (JSON) und zurück in einen Plan
    zurueck = PaketPlan.from_dict(plan_stand(pp))
    items = zurueck.vorlage.items
    assert items[0].beschleunigung is None and items[0].takt is None
    assert items[1].beschleunigung == SensorWahl(atmung=True)
    assert items[1].takt is not None and items[1].takt.name == "Box 4-4-4-4"
    assert items[2].beschleunigung == SensorWahl() and items[2].takt is AUS
    neu = plan_aus_vorlage(zurueck.vorlage, Kapitel(id="k1"), "s1", [u.id])
    assert [i.acc for i in neu.items] == [None, SensorWahl(atmung=True), SensorWahl()]
    assert neu.items[0].takt is None and neu.items[2].takt is AUS
    assert neu.items[1].takt is not None and neu.items[1].takt.name == "Box 4-4-4-4"


def test_paketfeld_je_planuebung_tolerant() -> None:
    """Unbrauchbares gilt als „wie die Übung“ — eine ältere Datei und eine neuere App lesen
    sich gegenseitig; `takt = {}` ist ausdrücklich keiner. Eine Takt-Tabelle ohne brauchbare
    Phase (Tippfehler) ist **nicht** „keiner“ — sie schaltete sonst den Takt der Übung in
    diesem Plan ab (Prüfrunde A6, Befund 2). Eine Tabelle `beschleunigung` ist immer eine
    eigene Karte, Unbrauchbares darin die Vorgabe (wie an der Übung)."""
    v = PlanVorlage.from_dict(
        {
            "name": "P",
            "uebungen": [
                {"uebung": "a", "beschleunigung": "ja", "takt": 3},
                {"uebung": "b", "beschleunigung": {"atmung": 1, "vorlage": "kniebeuge"}},
                {"uebung": "c", "takt": {"phasen": "kaputt"}},
                {"uebung": "d", "takt": {"phasen": [{"dauer_s": "x"}]}},
                {"uebung": "e", "takt": {}, "beschleunigung": {}},
            ],
        }
    )
    a, b, c, d, e = v.items
    assert a.beschleunigung is None and a.takt is None
    assert b.beschleunigung == SensorWahl(vorlage="kniebeuge")
    assert c.takt is None and d.takt is None  # wie die Übung, nie AUS
    assert e.takt is AUS and e.beschleunigung == SensorWahl()
    assert VorlageItem("a").to_dict("k") == {"uebung": "k"}
