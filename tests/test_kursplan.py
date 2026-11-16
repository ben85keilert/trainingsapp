"""Der Kursplan: ein Plan, den ein Kurs über die Kapitel baut — die Rechnung
(`core/kursplan.py`) und die Bausteine (`core/kursbloecke.py`).

Bens Beispiel (16.11.2026, `docs/plan_kurs_ablauf.md` §1, §11): Kapitel 1 bringt die Planke
mit 60 Sekunden; Kapitel 2 lässt eine von drei Übungen wählen, hängt sie hinter die Planke,
setzt ihr Ziel aus einem Test und verbindet beide mit einem Weg. Nichts ändert sich ohne Tipp,
jede Zeile lässt sich einzeln abwählen, und was die Person selbst geändert hat, bleibt.
"""

from __future__ import annotations

import copy
import json

from trainingsapp.core import ablauf as ab
from trainingsapp.core.bedingung import ZEIT as B_ZEIT
from trainingsapp.core.kursbloecke import (
    ARTEN,
    AUSWAHL,
    BAUSTEINE,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    Block,
    bloecke_lesen,
    braucht_eingabe,
)
from trainingsapp.core.kurse import Kurs, Kursplan, PlanVorlage, VorlageItem
from trainingsapp.core.kursplan import (
    ANKER_FEHLT,
    DER_PLAN,
    ENTFAELLT,
    NEU,
    OFFEN,
    UEBERNOMMEN,
    WEICHT_AB,
    Aenderung,
    aenderungen,
    anwenden,
    grundplan,
    grundstand,
    wahl_im_plan,
)
from trainingsapp.core.models import Plan, PlanItem
from trainingsapp.core.pakete import PaketPlan
from trainingsapp.core.result_spec import FieldSpec, FieldType
from trainingsapp.core.takt import AUS, Phase, Takt
from trainingsapp.core.timer import Abschnitt, TimerProfil

NAMEN = {
    "planke": "Planke",
    "seit": "Seitstütz",
    "kaefer": "Käfer",
    "bruecke": "Brücke",
    "dehnen": "Dehnen",
}

#: Kapitel 1: die Planke mit 60 Sekunden
KAPITEL_1 = [Block(PLAN_UEBUNG, id="a", uebung="planke", ziel={"hold": 60})]
#: Kapitel 2: eine von drei wählen, hinter die Planke, Ziel aus dem Test, ein Weg dorthin
KAPITEL_2 = [
    Block(AUSWAHL, id="wahl", uebungen=["seit", "kaefer", "bruecke"], anzahl=1),
    Block(TEST, id="test", uebung="kaefer", feld="reps"),
    Block(PLAN_UEBUNG, id="dazu", aus="wahl", hinter="a", ziel_aus="test"),
    Block(PLAN_WEG, id="weg", von="a", zu="dazu", kante={"ausloeser": "zeit", "pflicht": True}),
]
WAHL = {"wahl": ["kaefer"]}
WERTE = {"test": 30.0}


def alle_ids(zeilen: list[Aenderung]) -> set[str]:
    return {z.id for z in zeilen}


def nach_kapitel_1() -> tuple[Plan, dict]:
    zeilen = aenderungen(Plan(name="Rumpf"), KAPITEL_1, {}, {}, {}, NAMEN)
    return anwenden(Plan(name="Rumpf"), KAPITEL_1, {}, {}, alle_ids(zeilen), (), {}, NAMEN)


def nach_kapitel_2() -> tuple[Plan, dict]:
    plan, stand = nach_kapitel_1()
    zeilen = aenderungen(plan, KAPITEL_2, WERTE, WAHL, stand, NAMEN)
    return anwenden(plan, KAPITEL_2, WERTE, WAHL, alle_ids(zeilen), (), stand, NAMEN)


def kurz(zeilen: list[Aenderung]) -> list[tuple[str, str, str, str]]:
    return [(z.id, z.titel, z.unter, z.stand) for z in zeilen]


# ---------------------------------------------------------------------------
# Bens Beispiel
# ---------------------------------------------------------------------------


def test_kapitel_1_bringt_die_planke_mit_ziel_in_den_leeren_plan() -> None:
    leer = Plan(name="Rumpf")
    zeilen = aenderungen(leer, KAPITEL_1, {}, {}, {}, NAMEN)
    assert kurz(zeilen) == [
        ("a", "Planke kommt dazu", "ans Ende", NEU),
        ("a#ziel", "Ziel für Planke: 60 s", "aus dem Kurs", NEU),
    ]
    assert zeilen[1].braucht == "a" and zeilen[0].braucht == ""
    assert all(z.anwendbar and z.block_id == "a" for z in zeilen)

    plan, stand = anwenden(leer, KAPITEL_1, {}, {}, {"a", "a#ziel"}, (), {}, NAMEN)
    assert leer.items == []  # die Eingabe bleibt, wie sie war
    (planke,) = plan.items
    assert (planke.exercise_id, planke.kurs_marke, planke.target, planke.order) == (
        "planke",
        "a",
        {"hold": 60},
        0,
    )
    assert planke.plan_id == plan.id and not plan.ablauf.an  # eine Liste, kein Workout
    assert stand["a"]["uebung"] == "planke" and stand["a"]["ziel"] == {"hold": 60}
    assert json.loads(json.dumps(stand)) == stand  # der Kurs-Stand ist JSON-einfach


def test_kapitel_2_waehlen_testen_anhaengen_verbinden() -> None:
    plan, stand = nach_kapitel_1()
    zeilen = aenderungen(plan, KAPITEL_2, WERTE, WAHL, stand, NAMEN)
    assert kurz(zeilen) == [
        ("dazu:kaefer", "Käfer kommt dazu", "hinter Planke", NEU),
        ("dazu:kaefer#ziel", "Ziel für Käfer: 30 Wiederholungen", "aus deinem Test", NEU),
        (
            "weg#weg",
            "Von Planke weiter zu Käfer, wenn die Zeit ab ist",
            "Pflicht — Überspringen bleibt möglich",
            NEU,
        ),
    ]
    neu, neuer_stand = anwenden(plan, KAPITEL_2, WERTE, WAHL, alle_ids(zeilen), (), stand, NAMEN)
    planke, kaefer = neu.items
    assert [(i.exercise_id, i.kurs_marke) for i in neu.items] == [
        ("planke", "a"),
        ("kaefer", "dazu:kaefer"),
    ]
    assert kaefer.target == {"reps": [30]}  # Wiederholungen stehen je Satz
    # Der Weg: Zeit ab und Pflicht — und der Plan ist damit ein Workout
    assert neu.ablauf.an and neu.workout
    (kante,) = neu.ablauf.kanten
    assert (kante.von, kante.nach, kante.ausloeser, kante.pflicht) == (
        planke.id,
        kaefer.id,
        ab.ZEIT,
        True,
    )
    # Hauptweg und Bedingung der Planübung sind dasselbe: Der Ablauf folgt weiter der Liste
    assert planke.bedingung.art == B_ZEIT and planke.bedingung.hart
    assert ab.folgt_der_liste(neu.ablauf, [(i.id, i.bedingung) for i in neu.items])
    assert neuer_stand["a"]["wege"] == {"dazu:kaefer": {"ausloeser": "zeit", "pflicht": True}}
    assert neuer_stand["dazu:kaefer"]["uebung"] == "kaefer"
    # Die Wahl steht jetzt im Plan
    assert wahl_im_plan(neu, KAPITEL_2) == {"wahl": ["kaefer"]}
    assert wahl_im_plan(plan, KAPITEL_2) == {}


def test_einzelne_zeile_abwaehlen() -> None:
    """Der Käfer kommt dazu, sein Ziel aus dem Test nicht — er folgt dann der Übung."""
    plan, stand = nach_kapitel_1()
    gewaehlt = {"dazu:kaefer", "weg#weg"}
    neu, neuer_stand = anwenden(plan, KAPITEL_2, WERTE, WAHL, gewaehlt, (), stand, NAMEN)
    assert neu.items[1].target is None
    danach = aenderungen(neu, KAPITEL_2, WERTE, WAHL, neuer_stand, NAMEN)
    assert [(z.id, z.stand) for z in danach] == [
        ("dazu:kaefer", UEBERNOMMEN),
        ("dazu:kaefer#ziel", NEU),  # bleibt angeboten
        ("weg#weg", UEBERNOMMEN),
    ]
    # Ohne die Übung bewirkt ihr Ziel nichts — und der Weg dorthin auch nicht
    nur_ziel, _ = anwenden(plan, KAPITEL_2, WERTE, WAHL, {"dazu:kaefer#ziel", "weg#weg"}, (), stand)
    assert [i.exercise_id for i in nur_ziel.items] == ["planke"]
    assert not nur_ziel.ablauf.an
    # Nichts gewählt: nichts geändert
    assert anwenden(plan, KAPITEL_2, WERTE, WAHL, set(), (), stand, NAMEN) == (plan, stand)


def test_was_an_einer_neuen_uebung_haengt_braucht_ihre_zeile() -> None:
    """Die Karte wählt mit ab, was ohne die Grundzeile nichts bewirkte (`Aenderung.braucht`):
    nicht nur das Ziel der Übung, die erst dazukommt, auch der Weg zu ihr und was ein
    ``plan_einstellen`` desselben Kapitels an ihr setzt."""
    plan, stand = nach_kapitel_1()
    kapitel = [*KAPITEL_2, Block(PLAN_EINSTELLEN, id="st", an="dazu", felder=["reps"])]
    zeilen = aenderungen(plan, kapitel, WERTE, WAHL, stand, NAMEN)
    assert [(z.id, z.braucht) for z in zeilen] == [
        ("dazu:kaefer", ""),
        ("dazu:kaefer#ziel", "dazu:kaefer"),
        ("weg#weg", "dazu:kaefer"),
        ("st#felder", "dazu:kaefer"),
    ]
    # Steht die Übung im Plan, hängt nichts mehr an ihrer Zeile
    neu, neuer_stand = anwenden(plan, kapitel, WERTE, WAHL, {"dazu:kaefer"}, (), stand, NAMEN)
    danach = aenderungen(neu, kapitel, WERTE, WAHL, neuer_stand, NAMEN)
    assert [(z.id, z.stand, z.braucht) for z in danach] == [
        ("dazu:kaefer", UEBERNOMMEN, ""),
        ("dazu:kaefer#ziel", NEU, ""),
        ("weg#weg", NEU, ""),
        ("st#felder", NEU, ""),
    ]
    # Ein Weg von einer neuen Übung zu einer, die schon da ist, braucht die neue
    rueck = [
        Block(PLAN_UEBUNG, id="de", uebung="dehnen"),
        Block(PLAN_WEG, id="zurueck", von="de", zu="a", kante={}),
    ]
    assert [(z.id, z.braucht) for z in aenderungen(plan, rueck, {}, {}, stand, NAMEN)] == [
        ("de", ""),
        ("zurueck#weg", "de"),
    ]


def test_zweimal_anwenden_aendert_nichts() -> None:
    plan, stand = nach_kapitel_2()
    zeilen = aenderungen(plan, KAPITEL_2, WERTE, WAHL, stand, NAMEN)
    assert {z.stand for z in zeilen} == {UEBERNOMMEN}
    assert not any(z.anwendbar for z in zeilen)
    ids = {"dazu:kaefer", "dazu:kaefer#ziel", "weg#weg"}
    assert anwenden(plan, KAPITEL_2, WERTE, WAHL, ids, ids, stand, NAMEN) == (plan, stand)
    # Auch Kapitel 1 noch einmal: Die Planke steht schon da
    assert anwenden(plan, KAPITEL_1, {}, {}, {"a", "a#ziel"}, (), stand, NAMEN) == (plan, stand)
    assert len(plan.items) == 2


def test_person_aendert_ihr_ziel_kapitel_3_weicht_ab() -> None:
    """„Planke: Du hast 45 s eingestellt. Der Kurs schlägt 75 s vor.“ — ohne ``trotz``
    bleibt ihr Wert, mit ``trotz`` gilt der des Kurses."""
    plan, stand = nach_kapitel_2()
    plan.items[0].target = {"hold": 45}  # im Plan-Editor geändert
    kapitel_3 = [Block(PLAN_EINSTELLEN, id="mehr", an="a", ziel={"hold": 75})]
    (zeile,) = aenderungen(plan, kapitel_3, {}, {}, stand, NAMEN)
    assert (zeile.id, zeile.stand, zeile.eigen, zeile.kurs) == (
        "mehr#ziel",
        WEICHT_AB,
        "45 s",
        "75 s",
    )
    assert zeile.titel == "Planke: Du hast 45 s eingestellt. Der Kurs schlägt 75 s vor."
    assert zeile.anwendbar

    gelassen, stand_gelassen = anwenden(plan, kapitel_3, {}, {}, {"mehr#ziel"}, (), stand, NAMEN)
    assert gelassen.items[0].target == {"hold": 45} and stand_gelassen == stand
    uebernommen, stand_neu = anwenden(
        plan, kapitel_3, {}, {}, {"mehr#ziel"}, {"mehr#ziel"}, stand, NAMEN
    )
    assert uebernommen.items[0].target == {"hold": 75}
    assert stand_neu["a"]["ziel"] == {"hold": 75}
    (danach,) = aenderungen(uebernommen, kapitel_3, {}, {}, stand_neu, NAMEN)
    assert danach.stand == UEBERNOMMEN
    # ``trotz`` allein wählt nichts
    assert anwenden(plan, kapitel_3, {}, {}, set(), {"mehr#ziel"}, stand, NAMEN)[0] == plan

    # Hat die Person nichts geändert, ist es eine gewöhnliche neue Zeile
    unberuehrt, stand_u = nach_kapitel_2()
    (neu,) = aenderungen(unberuehrt, kapitel_3, {}, {}, stand_u, NAMEN)
    assert (neu.stand, neu.titel) == (NEU, "Ziel für Planke: 75 s")
    # … und hat sie von sich aus schon 75 s eingestellt, steht es schon so im Plan
    unberuehrt.items[0].target = {"hold": 75}
    (gleich,) = aenderungen(unberuehrt, kapitel_3, {}, {}, stand_u, NAMEN)
    assert gleich.stand == UEBERNOMMEN


def test_lassen_merkt_sich_der_kurs_und_fragt_nicht_wieder() -> None:
    """„45 s lassen“ (K3): Der Plan bleibt, wie er ist; die Zeile ist im Kurs-Stand erledigt
    und gilt danach als übernommen — sonst stünde „Dein Plan weicht ab“ bei jedem Öffnen da."""
    plan, stand = nach_kapitel_2()
    plan.items[0].target = {"hold": 45}
    kapitel_3 = [Block(PLAN_EINSTELLEN, id="mehr", an="a", ziel={"hold": 75})]
    gelassen, danach = anwenden(plan, kapitel_3, {}, {}, (), (), stand, NAMEN, lassen={"mehr#ziel"})
    assert gelassen == plan and gelassen.items[0].target == {"hold": 45}
    assert danach["a"]["erledigt"] == [*stand["a"]["erledigt"], "mehr#ziel"]
    assert danach["a"]["ziel"] == {"hold": 60}  # was der Kurs zuletzt gesetzt hat, bleibt stehen
    (zeile,) = aenderungen(gelassen, kapitel_3, {}, {}, danach, NAMEN)
    assert zeile.stand == UEBERNOMMEN and not zeile.anwendbar
    # zweimal dasselbe ändert nichts; ein spätes „übernehmen“ auch nicht mehr
    assert anwenden(gelassen, kapitel_3, {}, {}, (), (), danach, NAMEN, lassen={"mehr#ziel"}) == (
        gelassen,
        danach,
    )
    ids = {"mehr#ziel"}
    assert anwenden(gelassen, kapitel_3, {}, {}, ids, ids, danach, NAMEN) == (gelassen, danach)

    # Steht die Zeile in ``trotz`` und in ``lassen``, gilt „lassen“ — ihr Wert bleibt
    beides, stand_b = anwenden(plan, kapitel_3, {}, {}, ids, ids, stand, NAMEN, lassen=ids)
    assert beides == plan and stand_b == danach

    # Ein späteres Kapitel mit einem anderen Vorschlag fragt wieder: Ihr Wert ist ihrer
    kapitel_4 = [Block(PLAN_EINSTELLEN, id="noch", an="a", ziel={"hold": 90})]
    (wieder,) = aenderungen(gelassen, kapitel_4, {}, {}, danach, NAMEN)
    assert (wieder.stand, wieder.eigen, wieder.kurs) == (WEICHT_AB, "45 s", "90 s")

    # ``lassen`` gilt nur, wo der Plan abweicht: Eine neue Zeile bleibt neu
    unberuehrt, stand_u = nach_kapitel_2()
    ohne, stand_o = anwenden(unberuehrt, kapitel_3, {}, {}, (), (), stand_u, NAMEN, lassen=ids)
    assert (ohne, stand_o) == (unberuehrt, stand_u)
    assert [z.stand for z in aenderungen(ohne, kapitel_3, {}, {}, stand_o, NAMEN)] == [NEU]


def test_was_uebernommen_ist_wird_nicht_wieder_angeboten() -> None:
    """Kapitel 3 hat das Ziel der Planke auf 75 s gesetzt. Öffnet man danach Kapitel 1 noch
    einmal, bietet es seine 60 s nicht wieder an — sonst drehte ein altes Kapitel ein
    späteres zurück. Dasselbe gilt, wenn die Person den Wert danach selbst ändert."""
    plan, stand = nach_kapitel_2()
    kapitel_3 = [Block(PLAN_EINSTELLEN, id="mehr", an="a", ziel={"hold": 75})]
    plan, stand = anwenden(plan, kapitel_3, {}, {}, {"mehr#ziel"}, (), stand, NAMEN)
    assert plan.items[0].target == {"hold": 75}
    assert [z.stand for z in aenderungen(plan, KAPITEL_1, {}, {}, stand, NAMEN)] == [
        UEBERNOMMEN,
        UEBERNOMMEN,
    ]
    assert anwenden(plan, KAPITEL_1, {}, {}, {"a", "a#ziel"}, {"a#ziel"}, stand, NAMEN)[0] == plan
    plan.items[0].target = {"hold": 50}
    assert {z.stand for z in aenderungen(plan, KAPITEL_1, {}, {}, stand, NAMEN)} == {UEBERNOMMEN}
    assert {z.stand for z in aenderungen(plan, kapitel_3, {}, {}, stand, NAMEN)} == {UEBERNOMMEN}


def test_ziel_aus_dem_test_bleibt_wenn_der_juengste_eintrag_sich_aendert() -> None:
    """Der Testwert ist der jüngste Eintrag der Übung — er ändert sich mit jedem Training.
    Ein übernommenes Ziel wird davon nicht wieder „neu“."""
    plan, stand = nach_kapitel_2()
    zeilen = aenderungen(plan, KAPITEL_2, {"test": 42.0}, WAHL, stand, NAMEN)
    ziel = next(z for z in zeilen if z.id == "dazu:kaefer#ziel")
    assert (ziel.stand, ziel.titel) == (UEBERNOMMEN, "Ziel für Käfer: 30 Wiederholungen")
    neu, _ = anwenden(
        plan, KAPITEL_2, {"test": 42.0}, WAHL, {"dazu:kaefer#ziel"}, {"dazu:kaefer#ziel"}, stand
    )
    assert neu.items[1].target == {"reps": [30]}


# ---------------------------------------------------------------------------
# Anker, Marken, Offenes
# ---------------------------------------------------------------------------


def test_anker_geloescht_die_uebung_kommt_ans_ende() -> None:
    """„Dehnen kommt ans Ende — Brücke, hinter die es gehört, ist nicht mehr in deinem Plan.“"""
    plan, stand = nach_kapitel_1()
    bruecke = [Block(PLAN_UEBUNG, id="br", uebung="bruecke", hinter="a")]
    plan, stand = anwenden(plan, bruecke, {}, {}, {"br"}, (), stand, NAMEN)
    assert [i.exercise_id for i in plan.items] == ["planke", "bruecke"]
    dehnen = [Block(PLAN_UEBUNG, id="de", uebung="dehnen", hinter="br")]
    (zeile,) = aenderungen(plan, dehnen, {}, {}, stand, NAMEN)
    assert (zeile.stand, zeile.unter) == (NEU, "hinter Brücke")

    plan.items = [i for i in plan.items if i.kurs_marke != "br"]  # die Person löscht die Brücke
    (zeile,) = aenderungen(plan, dehnen, {}, {}, stand, NAMEN)
    assert kurz([zeile]) == [
        (
            "de",
            "Dehnen kommt ans Ende",
            "Brücke, hinter die es gehört, ist nicht mehr in deinem Plan.",
            ANKER_FEHLT,
        )
    ]
    assert zeile.anwendbar
    neu, _ = anwenden(plan, dehnen, {}, {}, {"de"}, (), stand, NAMEN)
    assert [i.exercise_id for i in neu.items] == ["planke", "dehnen"]


def test_aus_dem_plan_genommen_kommt_nicht_als_neu_wieder() -> None:
    """Was die Person geändert hat, bleibt: Eine Übung, die der Kurs gebracht und die Person
    aus dem Plan genommen hat, steht nicht wieder mit Haken da — der Kurs fragt (Vorgabe
    „lassen“), und nach „lassen“ fragt er nicht noch einmal."""
    plan, stand = nach_kapitel_1()
    bruecke = [Block(PLAN_UEBUNG, id="br", uebung="bruecke", hinter="a", ziel={"hold": [30]})]
    ids = {z.id for z in aenderungen(plan, bruecke, {}, {}, stand, NAMEN)}
    plan, stand = anwenden(plan, bruecke, {}, {}, ids, (), stand, NAMEN)
    assert [i.exercise_id for i in plan.items] == ["planke", "bruecke"]

    plan.items = [i for i in plan.items if i.kurs_marke != "br"]  # die Person nimmt sie heraus
    wieder, ziel = aenderungen(plan, bruecke, {}, {}, stand, NAMEN)
    assert (wieder.id, wieder.stand, wieder.kurs, wieder.eigen) == (
        "br",
        WEICHT_AB,
        "Brücke",
        "Plan so",
    )
    assert wieder.titel == (
        "Brücke: Du hast die Übung aus deinem Plan genommen. Der Kurs bringt sie wieder mit."
    )
    assert (ziel.stand, ziel.braucht) == (NEU, "br")  # hängt an der Zeile der Übung

    # „Übernehmen“ ohne die Abweichung ändert nichts — auch das Ziel allein bewirkt nichts
    gleich, _ = anwenden(plan, bruecke, {}, {}, {"br", "br#ziel"}, (), stand, NAMEN)
    assert [i.exercise_id for i in gleich.items] == ["planke"]
    # „lassen“: der Plan bleibt, und der Kurs fragt nicht wieder
    gelassen, stand_l = anwenden(plan, bruecke, {}, {}, set(), (), stand, NAMEN, lassen={"br"})
    assert [i.exercise_id for i in gelassen.items] == ["planke"]
    assert [z.stand for z in aenderungen(gelassen, bruecke, {}, {}, stand_l, NAMEN)] == [
        UEBERNOMMEN
    ]
    # „übernehmen“: Sie steht wieder hinter der Planke, mit ihrem Ziel
    zurueck, stand_z = anwenden(plan, bruecke, {}, {}, {"br", "br#ziel"}, {"br"}, stand, NAMEN)
    assert [(i.exercise_id, i.target) for i in zurueck.items] == [
        ("planke", {"hold": 60}),
        ("bruecke", {"hold": [30]}),
    ]
    assert {z.stand for z in aenderungen(zurueck, bruecke, {}, {}, stand_z, NAMEN)} == {UEBERNOMMEN}


def test_gewaehlte_uebung_ist_wieder_neu_wenn_man_sie_wieder_waehlt() -> None:
    """Eine Gewählte, die die Person aus dem Plan genommen hat, gibt die Auswahl wieder frei —
    wählt man sie noch einmal, ist das eine neue Entscheidung, keine Abweichung."""
    plan, stand = nach_kapitel_1()
    plan, stand = anwenden(plan, KAPITEL_2, WERTE, WAHL, {"dazu:kaefer"}, (), stand, NAMEN)
    plan.items = [i for i in plan.items if i.kurs_marke != "dazu:kaefer"]
    dazu = next(
        z for z in aenderungen(plan, KAPITEL_2, WERTE, WAHL, stand, NAMEN) if z.id == "dazu:kaefer"
    )
    assert (dazu.id, dazu.stand) == ("dazu:kaefer", NEU)


def test_neue_uebung_steht_hinter_ihrem_anker_nicht_am_ende() -> None:
    plan, stand = nach_kapitel_1()
    plan.items.append(PlanItem(plan_id=plan.id, exercise_id="dehnen", order=1))  # selbst dazu
    neu, _ = anwenden(plan, KAPITEL_2, WERTE, WAHL, {"dazu:kaefer"}, (), stand, NAMEN)
    assert [(i.exercise_id, i.order) for i in neu.items] == [
        ("planke", 0),
        ("kaefer", 1),
        ("dehnen", 2),
    ]


def test_einstellen_und_weg_an_fehlender_marke_entfallen() -> None:
    plan, stand = nach_kapitel_2()
    bloecke = [
        Block(PLAN_EINSTELLEN, id="e", an="dazu", ziel={"reps": [40]}, uebergang="hart"),
        Block(PLAN_WEG, id="w", von="dazu", zu="ende"),
    ]
    vorher = aenderungen(plan, bloecke, {}, {}, stand, NAMEN)
    assert [(z.id, z.stand) for z in vorher] == [
        ("e#ziel", NEU),
        ("e#uebergang", NEU),
        ("w#weg", NEU),
    ]
    assert vorher[0].titel == "Ziel für Käfer: 40 Wiederholungen"
    assert vorher[2].titel == "Von Käfer weiter zum Ende"

    kaefer = plan.items[1]
    plan.items = plan.items[:1]  # die Person nimmt den Käfer aus dem Plan
    plan.ablauf = plan.ablauf.ohne_knoten(kaefer.id)
    zeilen = aenderungen(plan, bloecke, {}, {}, stand, NAMEN)
    assert kurz(zeilen) == [
        ("e", "Eine Einstellung entfällt", "Käfer ist nicht mehr in deinem Plan.", ENTFAELLT),
        (
            "e#uebergang",
            "Übergang im Workout: hart",
            "Vorgabe aus dem Kurs — umschalten kannst du jederzeit",
            NEU,
        ),
        ("w#weg", "Ein Weg entfällt", "Käfer ist nicht mehr in deinem Plan.", ENTFAELLT),
    ]
    assert not zeilen[0].anwendbar and not zeilen[2].anwendbar
    # Entfallenes lässt sich nicht erzwingen, der Rest gilt
    neu, _ = anwenden(plan, bloecke, {}, {}, {"e", "e#ziel", "e#uebergang", "w#weg"}, (), stand)
    assert neu.uebergang_hart and len(neu.items) == 1
    # Eine Marke, die es nie gab: „Die Übung“
    (nie,) = aenderungen(
        plan, [Block(PLAN_WEG, id="w2", von="a", zu="gibtsnicht")], {}, {}, stand, NAMEN
    )
    assert (nie.stand, nie.unter) == (ENTFAELLT, "Die Übung ist nicht mehr in deinem Plan.")


def test_fehlende_wahl_und_fehlender_test_sind_offen() -> None:
    plan, stand = nach_kapitel_1()
    ohne = aenderungen(plan, KAPITEL_2, {}, {}, stand, NAMEN)
    assert kurz(ohne) == [
        ("dazu", "Deine Auswahl kommt dazu", "Triff zuerst deine Auswahl.", OFFEN),
        ("weg#weg", "Ein Weg für deine Auswahl", "Triff zuerst deine Auswahl.", OFFEN),
    ]
    assert not any(z.anwendbar for z in ohne)
    assert anwenden(plan, KAPITEL_2, {}, {}, {"dazu", "weg#weg"}, (), stand, NAMEN) == (plan, stand)

    # Gewählt, aber noch nicht getestet: Die Übung kann kommen, ihr Ziel wartet
    ohne_test = aenderungen(plan, KAPITEL_2, {}, WAHL, stand, NAMEN)
    assert [(z.id, z.stand) for z in ohne_test] == [
        ("dazu:kaefer", NEU),
        ("dazu:kaefer#ziel", OFFEN),
        ("weg#weg", NEU),
    ]
    assert ohne_test[1].unter == "aus deinem Test — mach ihn zuerst"
    neu, _ = anwenden(plan, KAPITEL_2, {}, WAHL, alle_ids(ohne_test), (), stand, NAMEN)
    assert neu.items[1].target is None
    # Was sich auf die offene Wahl bezieht, wartet mit
    spaeter = [
        *KAPITEL_2,
        Block(PLAN_UEBUNG, id="de", uebung="dehnen", hinter="dazu"),
        Block(PLAN_EINSTELLEN, id="e", an="dazu", felder=["reps"]),
    ]
    staende = {z.id: z.stand for z in aenderungen(plan, spaeter, {}, {}, stand, NAMEN)}
    assert staende == {"dazu": OFFEN, "weg#weg": OFFEN, "de": OFFEN, "e": OFFEN}


def test_test_in_einem_anderen_kapitel_kommt_ueber_bezug() -> None:
    plan, stand = nach_kapitel_2()
    spaeter = [Block(PLAN_EINSTELLEN, id="e", an="a", ziel_aus="frueh", faktor=0.5)]
    frueh = [Block(TEST, id="frueh", uebung="planke", feld="hold")]
    assert aenderungen(plan, spaeter, {"frueh": 90.0}, {}, stand, NAMEN)[0].stand == OFFEN
    (zeile,) = aenderungen(plan, spaeter, {"frueh": 90.0}, {}, stand, NAMEN, bezug=frueh)
    assert (zeile.stand, zeile.titel, zeile.unter) == (
        NEU,
        "Ziel für Planke: 45 s",
        "aus deinem Test",
    )
    neu, _ = anwenden(plan, spaeter, {"frueh": 90.0}, {}, {"e#ziel"}, (), stand, bezug=frueh)
    assert neu.items[0].target == {"hold": [45]}


def test_mehrere_gewaehlte_stehen_in_der_reihenfolge_der_wahl_und_bekommen_je_einen_weg() -> None:
    plan, stand = nach_kapitel_1()
    bloecke = [
        Block(PLAN_UEBUNG, id="dazu", aus="wahl", hinter="a", ziel={"reps": [10]}),
        Block(PLAN_WEG, id="weg", von="a", zu="dazu"),
        Block(PLAN_EINSTELLEN, id="e", an="dazu", felder=[]),
    ]
    wahl = {"wahl": ["bruecke", "seit"]}
    zeilen = aenderungen(plan, bloecke, {}, wahl, stand, NAMEN)
    assert [z.id for z in zeilen] == [
        "dazu:bruecke",
        "dazu:bruecke#ziel",
        "dazu:seit",
        "dazu:seit#ziel",
        "weg#weg:a>dazu:bruecke",
        "weg#weg:a>dazu:seit",
        "e#felder:dazu:bruecke",
        "e#felder:dazu:seit",
    ]
    assert zeilen[2].unter == "hinter Planke" and zeilen[-1].titel == "Seitstütz: nur abhaken"
    neu, neuer_stand = anwenden(plan, bloecke, {}, wahl, alle_ids(zeilen), (), stand, NAMEN)
    planke, bruecke, seit = neu.items
    assert [i.exercise_id for i in neu.items] == ["planke", "bruecke", "seit"]
    assert bruecke.felder == [] and seit.target == {"reps": [10]}
    assert {(k.von, k.nach) for k in neu.ablauf.von(planke.id)} == {
        (planke.id, bruecke.id),
        (planke.id, seit.id),
    }
    assert wahl_im_plan(neu, bloecke) == {"wahl": ["bruecke", "seit"]}
    assert anwenden(neu, bloecke, {}, wahl, alle_ids(zeilen), (), neuer_stand, NAMEN) == (
        neu,
        neuer_stand,
    )


def test_uebung_die_es_hier_nicht_gibt_ergibt_keine_zeile() -> None:
    bloecke = [Block(PLAN_UEBUNG, id="x", uebung="unbekannt", ziel={"reps": [5]})]
    assert aenderungen(Plan(), bloecke, {}, {}, {}, NAMEN) == []
    assert anwenden(Plan(), bloecke, {}, {}, {"x"}, (), {}, NAMEN)[0].items == []
    # ohne Namen gilt jede Übung als vorhanden
    assert len(anwenden(Plan(), bloecke, {}, {}, {"x"}, (), {})[0].items) == 1


# ---------------------------------------------------------------------------
# Wege im Ablauf
# ---------------------------------------------------------------------------


def test_workout_das_der_liste_folgt_waechst_mit() -> None:
    """Folgt der Ablauf der Liste und sagt kein Weg etwas anderes, bleibt es so: Die neue
    Planübung gehört von selbst dazu."""
    plan, stand = nach_kapitel_2()
    dehnen = [Block(PLAN_UEBUNG, id="de", uebung="dehnen")]
    neu, _ = anwenden(plan, dehnen, {}, {}, {"de"}, (), stand, NAMEN)
    paare = [(i.id, i.bedingung) for i in neu.items]
    assert ab.folgt_der_liste(neu.ablauf, paare)
    assert [(k.von, k.nach) for k in neu.ablauf.kanten] == [
        (neu.items[0].id, neu.items[1].id),
        (neu.items[1].id, neu.items[2].id),
    ]
    assert neu.ablauf.kanten[0].pflicht  # der Weg aus Kapitel 2 bleibt
    # Eine Liste ohne Ablauf bleibt eine Liste
    liste, stand_l = nach_kapitel_1()
    mehr, _ = anwenden(liste, dehnen, {}, {}, {"de"}, (), stand_l, NAMEN)
    assert not mehr.ablauf.an and not mehr.workout and mehr.ablauf.leer


def test_weg_zu_einem_anderen_ziel_kommt_dazu_der_weg_der_kette_bleibt() -> None:
    plan, stand = nach_kapitel_2()
    plan, stand = anwenden(
        plan, [Block(PLAN_UEBUNG, id="de", uebung="dehnen")], {}, {}, {"de"}, (), stand, NAMEN
    )
    planke, kaefer, dehnen = plan.items
    abkuerzung = [Block(PLAN_WEG, id="ab", von="a", zu="de", kante={"text": "heute kurz"})]
    (zeile,) = aenderungen(plan, abkuerzung, {}, {}, stand, NAMEN)
    assert (zeile.titel, zeile.unter, zeile.stand) == (
        "Von Planke weiter zu Dehnen",
        "„heute kurz“",
        NEU,
    )
    neu, _ = anwenden(plan, abkuerzung, {}, {}, {"ab#weg"}, (), stand, NAMEN)
    assert [(k.nach, k.text) for k in neu.ablauf.von(planke.id)] == [
        (kaefer.id, ""),
        (dehnen.id, "heute kurz"),
    ]
    # ein Abzweig: Der Ablauf ist jetzt ein eigener
    assert not ab.folgt_der_liste(neu.ablauf, [(i.id, i.bedingung) for i in neu.items])
    assert [(k.von, k.nach) for k in neu.ablauf.von(kaefer.id)] == [(kaefer.id, dehnen.id)]


def test_weg_den_die_person_geaendert_hat_weicht_ab() -> None:
    plan, stand = nach_kapitel_2()
    plan, stand = anwenden(
        plan,
        [
            Block(PLAN_UEBUNG, id="de", uebung="dehnen"),
            Block(PLAN_WEG, id="ab", von="a", zu="de", kante={"text": "heute kurz"}),
        ],
        {},
        {},
        {"de", "ab#weg"},
        (),
        stand,
        NAMEN,
    )
    planke, _kaefer, dehnen = plan.items
    # Die Person macht aus dem freien Weg einen mit Wiederholungen
    eigener = ab.Kante(planke.id, dehnen.id, ab.WDH, 12)
    alt = next(k for k in plan.ablauf.kanten if k.nach == dehnen.id and k.von == planke.id)
    plan.ablauf = plan.ablauf.kante_ersetzen(alt, eigener)
    spaeter = [Block(PLAN_WEG, id="ab2", von="a", zu="de", kante={"ausloeser": "skala", "n": 7})]
    (zeile,) = aenderungen(plan, spaeter, {}, {}, stand, NAMEN)
    assert (zeile.stand, zeile.eigen, zeile.kurs) == (WEICHT_AB, "12 Wdh.", "Skala ≥ 7")
    assert zeile.titel == (
        "Weg von Planke zu Dehnen: Du hast „12 Wdh.“ eingestellt. Der Kurs schlägt „Skala ≥ 7“ vor."
    )
    assert anwenden(plan, spaeter, {}, {}, {"ab2#weg"}, (), stand, NAMEN)[0] == plan
    neu, _ = anwenden(plan, spaeter, {}, {}, {"ab2#weg"}, {"ab2#weg"}, stand, NAMEN)
    assert [k.ausloeser for k in neu.ablauf.von(planke.id) if k.nach == dehnen.id] == [ab.SKALA]
    # „Lassen“: Der eigene Weg bleibt, und die Zeile kommt nicht wieder
    gelassen, stand_l = anwenden(plan, spaeter, {}, {}, (), (), stand, NAMEN, lassen={"ab2#weg"})
    assert gelassen == plan and "ab2#weg" in stand_l["a"]["erledigt"]
    assert stand_l["a"]["wege"] == stand["a"]["wege"]  # was der Kurs gesetzt hat, bleibt stehen
    assert [z.stand for z in aenderungen(plan, spaeter, {}, {}, stand_l, NAMEN)] == [UEBERNOMMEN]
    # Den Weg, den der Kurs selbst gesetzt hat, ersetzt ein späteres Kapitel ohne Rückfrage
    unberuehrt = copy.deepcopy(plan)
    unberuehrt.ablauf = unberuehrt.ablauf.kante_ersetzen(eigener, alt)
    assert aenderungen(unberuehrt, spaeter, {}, {}, stand, NAMEN)[0].stand == NEU


def test_weg_nennt_die_dauer_des_eigenen_timers() -> None:
    """„Von Planke weiter zu Käfer nach 60 s“ — wenn der Kurs der Planke einen Timer gibt."""
    timer = TimerProfil(id="t", name="Halten", abschnitte=[Abschnitt("Halten", 60)]).als_dict()
    kapitel_1 = [Block(PLAN_UEBUNG, id="a", uebung="planke", timer=timer)]
    zeilen = aenderungen(Plan(), kapitel_1, {}, {}, {}, NAMEN)
    assert kurz(zeilen)[1] == ("a#timer", "Timer für Planke: 1:00 Halten", "aus dem Kurs", NEU)
    plan, stand = anwenden(Plan(), kapitel_1, {}, {}, {"a", "a#timer"}, (), {}, NAMEN)
    assert plan.items[0].timer == {"eigen": timer}
    weg = aenderungen(plan, KAPITEL_2, WERTE, WAHL, stand, NAMEN)[-1]
    assert weg.titel == "Von Planke weiter zu Käfer nach 60 s"


# ---------------------------------------------------------------------------
# Einstellen: Timer, Takt, Parameter, Plan
# ---------------------------------------------------------------------------


def test_einstellen_am_plan_und_an_der_planuebung() -> None:
    plan, stand = nach_kapitel_2()
    timer = TimerProfil(
        id="r", name="Runden", abschnitte=[Abschnitt("Üben", 40), Abschnitt("Pause", 20)], runden=3
    ).als_dict()
    takt = Takt((Phase("ab", 2, "ab"), Phase("auf", 2, "auf")), name="2-2")
    bloecke = [
        Block(
            PLAN_EINSTELLEN, id="k", an="dazu", timer=timer, takt=takt, felder=["reps", "weight"]
        ),
        Block(
            PLAN_EINSTELLEN, id="p", timer=timer, takt=AUS, uebergang="hart", pause_ohne_timer=False
        ),
    ]
    zeilen = aenderungen(plan, bloecke, {}, {}, stand, NAMEN)
    assert [(z.id, z.titel, z.stand) for z in zeilen] == [
        ("k#felder", "Parameter für Käfer: Wiederholungen, Gewicht", NEU),
        ("k#timer", "Timer für Käfer: 0:40 Üben · 0:20 Pause · 3 Runden", NEU),
        ("k#takt", f"Takt für Käfer: {takt.kurztext()}", NEU),
        ("p#timer", "Timer für alle Übungen: 0:40 Üben · 0:20 Pause · 3 Runden", NEU),
        # „kein Takt“ an einem Plan, der keinen hat: steht schon so da
        ("p#takt", "Takt für alle Übungen: kein Takt", UEBERNOMMEN),
        ("p#uebergang", "Übergang im Workout: hart", NEU),
        ("p#pause_ohne_timer", "Pause nach Übungen ohne Timer: aus", NEU),
    ]
    neu, neuer_stand = anwenden(plan, bloecke, {}, {}, alle_ids(zeilen), (), stand, NAMEN)
    kaefer = neu.items[1]
    assert kaefer.felder == ["reps", "weight"] and kaefer.takt == takt
    assert kaefer.timer == {"eigen": timer} and kaefer.target == {"reps": [30]}  # das Ziel bleibt
    assert neu.timer == timer and neu.uebergang_hart and not neu.pause_ohne_timer
    assert neuer_stand[DER_PLAN]["uebergang"] == "hart"
    assert {z.stand for z in aenderungen(neu, bloecke, {}, {}, neuer_stand, NAMEN)} == {UEBERNOMMEN}

    # Die Person stellt am Timer des Käfers eine andere Dauer ein
    eigener = copy.deepcopy(timer)
    eigener["abschnitte"][0]["dauer_s"] = 30
    kaefer.timer = {"eigen": {**eigener, "id": "kopie"}}
    spaeter = [Block(PLAN_EINSTELLEN, id="k2", an="dazu", timer={**timer, "runden": 4})]
    (zeit,) = aenderungen(neu, spaeter, {}, {}, neuer_stand, NAMEN)
    assert zeit.stand == WEICHT_AB
    assert zeit.eigen == "0:30 Üben · 0:20 Pause · 3 Runden"
    assert zeit.kurs == "0:40 Üben · 0:20 Pause · 4 Runden"


def test_uebergang_den_die_person_umgestellt_hat_weicht_ab() -> None:
    """Der Kurs setzt nur die Vorgabe — stellt die Person sie um, bleibt ihre."""
    plan, stand = nach_kapitel_2()
    hart = [Block(PLAN_EINSTELLEN, id="p", uebergang="hart")]
    plan, stand = anwenden(plan, hart, {}, {}, {"p#uebergang"}, (), stand, NAMEN)
    assert plan.uebergang_hart
    plan.uebergang_hart = False  # zurück auf weich
    weich_bleibt = [Block(PLAN_EINSTELLEN, id="p2", uebergang="hart")]
    (zeile,) = aenderungen(plan, weich_bleibt, {}, {}, stand, NAMEN)
    assert (zeile.stand, zeile.eigen, zeile.kurs) == (WEICHT_AB, "weich", "hart")
    assert zeile.titel == (
        "Übergang im Workout: Du hast weich eingestellt. Der Kurs schlägt hart vor."
    )
    assert not anwenden(plan, weich_bleibt, {}, {}, {"p2#uebergang"}, (), stand)[0].uebergang_hart


def test_timer_mit_neuer_id_ist_derselbe_timer() -> None:
    """Eine Kopie mit anderer ID (Plan-Editor: „Nur hier“) ist keine Änderung der Person."""
    timer = TimerProfil(id="t", name="Halten", abschnitte=[Abschnitt("Halten", 60)]).als_dict()
    bloecke = [Block(PLAN_UEBUNG, id="a", uebung="planke", timer=timer)]
    plan, stand = anwenden(Plan(), bloecke, {}, {}, {"a", "a#timer"}, (), {}, NAMEN)
    plan.items[0].timer = {"eigen": {**timer, "id": "anders"}, "uhr": True}
    laenger = [Block(PLAN_EINSTELLEN, id="e", an="a", timer={**timer, "runden": 2})]
    (zeile,) = aenderungen(plan, laenger, {}, {}, stand, NAMEN)
    assert zeile.stand == NEU
    neu, _ = anwenden(plan, laenger, {}, {}, {"e#timer"}, (), stand, NAMEN)
    assert neu.items[0].timer["uhr"] is True and neu.items[0].timer["eigen"]["runden"] == 2


def test_feld_der_uebung_bestimmt_text_und_form_des_ziels() -> None:
    """Hält die Übung ihre Zeit als eine Dauer (kein Wert je Satz), steht das Ziel aus dem
    Test als Zahl — und das Feld heißt, wie die Übung es nennt."""

    def feld_von(uebung: str, key: str) -> FieldSpec | None:
        if (uebung, key) == ("planke", "seconds"):
            return FieldSpec("seconds", FieldType.DURATION, "Zeit", unit="s")
        if (uebung, key) == ("kaefer", "reps"):
            return FieldSpec("reps", FieldType.SET_LIST, "Wdh.", unit="Wdh.")
        return None

    bloecke = [
        Block(TEST, id="t", uebung="planke", feld="seconds"),
        Block(PLAN_UEBUNG, id="a", uebung="planke", ziel_aus="t", faktor=0.8),
        Block(PLAN_UEBUNG, id="k", uebung="kaefer", ziel={"reps": [10, 10]}),
    ]
    zeilen = aenderungen(Plan(), bloecke, {"t": 100.0}, {}, {}, NAMEN, feld_von)
    assert [z.titel for z in zeilen] == [
        "Planke kommt dazu",
        "Ziel für Planke: 80 s",
        "Käfer kommt dazu",
        "Ziel für Käfer: 2x10 Wdh.",
    ]
    plan, _ = anwenden(Plan(), bloecke, {"t": 100.0}, {}, alle_ids(zeilen), (), {}, NAMEN, feld_von)
    assert plan.items[0].target == {"seconds": 80}


# ---------------------------------------------------------------------------
# Grundlage
# ---------------------------------------------------------------------------


def test_grundlage_leer() -> None:
    kurs = Kurs(id="k", name="Rumpf-Kurs", kursplan=Kursplan("Rumpf", [0, 2, 4]))
    plan = grundplan(kurs, "s1", NAMEN)
    assert (plan.name, plan.wochentage, plan.items, plan.kurs_id, plan.subject_id) == (
        "Rumpf",
        [0, 2, 4],
        [],
        "k",
        "s1",
    )
    assert plan.aktiv and plan.kurs_kapitel_id is None and plan.package_id is None
    assert grundstand(plan) == {
        DER_PLAN: {"timer": None, "takt": None, "uebergang": "weich", "pause_ohne_timer": True}
    }
    # ohne Namen heißt der Plan wie der Kurs
    assert grundplan(Kurs(name="Rumpf-Kurs", kursplan=Kursplan()), "s1", NAMEN).name == "Rumpf-Kurs"


def test_grundlage_aus_vorlage_mit_marken_und_ablauf() -> None:
    vorlage = PlanVorlage(
        "egal",
        [1],
        [VorlageItem("planke", {"hold": 60}), VorlageItem("fehlt"), VorlageItem("dehnen")],
        ablauf={"an": True, "start": "#1", "kanten": [{"von": "#1", "nach": "#3", "text": "los"}]},
    )
    kurs = Kurs(id="k", name="Rumpf-Kurs", kursplan=Kursplan("Rumpf", [0, 3], vorlage=vorlage))
    plan = grundplan(kurs, "s1", NAMEN)
    assert (plan.name, plan.wochentage) == ("Rumpf", [0, 3])  # Name und Tage vom Kursplan
    planke, dehnen = plan.items
    # die Marke nennt die Stelle in der Vorlage — auch wenn eine Übung davor hier fehlt
    assert [(i.exercise_id, i.kurs_marke) for i in plan.items] == [
        ("planke", "g:1"),
        ("dehnen", "g:3"),
    ]
    assert [(k.von, k.nach) for k in plan.ablauf.kanten] == [(planke.id, dehnen.id)]
    assert vorlage.name == "egal" and len(vorlage.items) == 3  # die Vorlage bleibt
    stand = grundstand(plan)
    assert stand["g:1"]["ziel"] == {"hold": 60} and stand["g:1"]["wege"] == {"g:3": {"text": "los"}}
    # zwei Profile bekommen je ihren eigenen Plan
    assert grundplan(kurs, "s2", NAMEN).id != plan.id

    # Bausteine beziehen sich auf die Grundlage; was die Person daran ändert, erkennt der Kurs
    bloecke = [
        Block(PLAN_UEBUNG, id="k", uebung="kaefer", hinter="g:1"),
        Block(PLAN_EINSTELLEN, id="e", an="g:1", ziel={"hold": 90}),
    ]
    zeilen = aenderungen(plan, bloecke, {}, {}, stand, NAMEN)
    assert [(z.id, z.unter, z.stand) for z in zeilen] == [
        ("k", "hinter Planke", NEU),
        ("e#ziel", "aus dem Kurs", NEU),
    ]
    plan.items[0].target = {"hold": 30}
    assert aenderungen(plan, bloecke, {}, {}, stand, NAMEN)[1].stand == WEICHT_AB
    neu, _ = anwenden(plan, bloecke, {}, {}, {"k"}, (), stand, NAMEN)
    assert [i.exercise_id for i in neu.items] == ["planke", "kaefer", "dehnen"]
    # die Grundlage hat einen eigenen Ablauf: Die neue Übung ist dort (noch) nicht verbunden
    assert [(k.von, k.nach) for k in neu.ablauf.kanten] == [(planke.id, dehnen.id)]


def test_grundlage_aus_paketplan() -> None:
    timer = TimerProfil(id="t", name="Alle", abschnitte=[Abschnitt("Üben", 45)]).als_dict()
    paketplan = PaketPlan(
        "rumpf-basis",
        PlanVorlage("Basis aus dem Paket", [5], [VorlageItem("planke"), VorlageItem("bruecke")]),
        beschreibung="Jeden zweiten Tag.",
        timer=timer,
        pause_ohne_timer=False,
    )
    kurs = Kurs(id="k", name="Rumpf-Kurs", kursplan=Kursplan("Rumpf", grundlage="rumpf-basis"))
    plan = grundplan(kurs, "s1", NAMEN, paketplan)
    assert (plan.name, plan.wochentage, plan.description) == (
        "Rumpf",
        list(range(7)),
        "Jeden zweiten Tag.",
    )
    assert plan.timer == timer and plan.timer is not paketplan.timer
    assert not plan.pause_ohne_timer
    assert [(i.exercise_id, i.kurs_marke) for i in plan.items] == [
        ("planke", "g:1"),
        ("bruecke", "g:2"),
    ]
    # eine Kopie: weder Paket noch Kapitel als Herkunft, eigene ID
    assert plan.package_id is None and plan.package_key is None and plan.kurs_kapitel_id is None
    assert grundstand(plan)[DER_PLAN]["pause_ohne_timer"] is False
    # Hat der Kurs auch eine Vorlage, gilt sie — der Paketplan bleibt dann draußen
    kurs.kursplan.vorlage = PlanVorlage("V", items=[VorlageItem("dehnen")])
    eigen = grundplan(kurs, "s1", NAMEN, paketplan)
    assert [i.exercise_id for i in eigen.items] == ["dehnen"] and eigen.description == ""
    # Schlüssel ohne Paketplan (eigener Kurs, Plan nicht im Paket): Der Plan beginnt leer
    kurs.kursplan.vorlage = None
    assert grundplan(kurs, "s1", NAMEN, None).items == []


def test_kursplan_rundreise_und_nachsicht() -> None:
    kursplan = Kursplan(
        "Rumpf", [0, 2], vorlage=PlanVorlage("V", [1], [VorlageItem("planke", {"hold": 60})])
    )
    assert Kursplan.aus_dict(json.loads(json.dumps(kursplan.als_dict()))) == kursplan
    assert Kursplan.aus_dict(Kursplan("R", grundlage="basis").als_dict()).grundlage == "basis"
    assert Kursplan.aus_dict(None) is None and Kursplan.aus_dict([1]) is None
    kaputt = Kursplan.aus_dict({"name": 7, "wochentage": "mo", "grundlage": 3, "vorlage": "x"})
    assert kaputt == Kursplan("7", list(range(7)))


# ---------------------------------------------------------------------------
# Bausteine lesen und schreiben
# ---------------------------------------------------------------------------


def test_bausteine_rundreise() -> None:
    timer = TimerProfil(id="t", name="Halten", abschnitte=[Abschnitt("Halten", 60)]).als_dict()
    takt = Takt((Phase("ein", 4, "ein"), Phase("aus", 6, "aus")), name="4-6")
    bloecke = [
        Block(
            PLAN_UEBUNG, id="a", uebung="planke", ziel={"hold": 60}, felder=["hold"], timer=timer
        ),
        Block(PLAN_UEBUNG, id="b", aus="wahl", hinter="a", ziel_aus="test", faktor=0.8, takt=takt),
        Block(PLAN_EINSTELLEN, id="c", an="a", ziel={"hold": 75}, takt=AUS),
        Block(PLAN_EINSTELLEN, id="d", uebergang="weich", pause_ohne_timer=True, timer=timer),
        Block(PLAN_WEG, id="e", von="a", zu="b", kante={"ausloeser": "zeit", "pflicht": True}),
        Block(PLAN_WEG, id="f", von="b", zu="ende"),
    ]
    roh = json.loads(json.dumps([b.to_dict() for b in bloecke]))
    assert bloecke_lesen(roh) == bloecke
    assert roh[0] == {
        "art": "plan_uebung",
        "id": "a",
        "uebung": "planke",
        "ziel": {"hold": 60},
        "felder": ["hold"],
        "timer": timer,
    }
    assert roh[1] == {
        "art": "plan_uebung",
        "id": "b",
        "aus": "wahl",
        "hinter": "a",
        "ziel_aus": "test",
        "faktor": 0.8,
        "takt": takt.als_dict(),
    }
    assert roh[2] == {
        "art": "plan_einstellen",
        "id": "c",
        "an": "a",
        "ziel": {"hold": 75},
        "takt": {},
    }
    assert roh[5] == {"art": "plan_weg", "id": "f", "von": "b", "zu": "ende"}
    assert all(b.baustein for b in bloecke) and not Block(TEST, uebung="u").baustein


def test_bausteine_lesen_paketschluessel_und_unbrauchbares() -> None:
    schluessel = {"planke": "id-planke"}
    (b,) = bloecke_lesen([{"art": "plan_uebung", "id": "a", "uebung": "planke"}], schluessel)
    assert b.uebung == "id-planke"
    # ``aus`` geht vor ``uebung``; ein Verweis in die Timer-Bibliothek ist im Paket keiner
    (b,) = bloecke_lesen(
        [{"art": "plan_uebung", "id": "a", "uebung": "planke", "aus": "w", "timer": {"ref": "x"}}]
    )
    assert (b.uebung, b.aus, b.timer) == ("", "w", {})
    # ein Timer ohne ID bekommt eine feste aus der Block-ID
    roh = {
        "art": "plan_einstellen",
        "id": "t1",
        "timer": {"abschnitte": [{"name": "A", "dauer_s": 5}]},
    }
    assert bloecke_lesen([roh])[0].timer["id"] == "kurs-t1"
    assert bloecke_lesen([roh]) == bloecke_lesen([roh])
    # was nichts ändern könnte, fällt weg — eine unbekannte Art auch (ältere Apps)
    assert (
        bloecke_lesen(
            [
                {"art": "plan_uebung", "id": "1"},
                {"art": "plan_einstellen", "id": "2", "an": "a"},
                {"art": "plan_einstellen", "id": "3", "uebergang": "schnell"},
                {"art": "plan_weg", "id": "4", "von": "a"},
                {"art": "plan_hologramm", "id": "5", "uebung": "planke"},
            ]
        )
        == []
    )
    # ``ziel`` und ``ziel_aus`` zugleich: der Test gilt
    (b,) = bloecke_lesen([{"art": "plan_einstellen", "an": "a", "ziel": {"x": 1}, "ziel_aus": "t"}])
    assert (b.ziel, b.ziel_aus) == ({}, "t")


def test_bausteine_aendern_kurse_ohne_kursplan_nicht() -> None:
    """Die fünf Arten „im Kapitel“ bleiben, wie sie sind; ein Baustein ist keine Eingabe."""
    assert set(ARTEN) == {"text", "medium", "frage", "test", "auswahl"}
    assert set(BAUSTEINE) == {PLAN_UEBUNG, PLAN_EINSTELLEN, PLAN_WEG}
    assert not braucht_eingabe([Block(PLAN_UEBUNG, id="a", uebung="planke")])
    assert braucht_eingabe(KAPITEL_2)
