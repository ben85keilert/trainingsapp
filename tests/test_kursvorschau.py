"""Die Vorschau „Das kommt noch“ der Kursseite (Ben, 16.11.2026, Schritt A1,
`docs/plan_kurs_ablauf.md` §12, Skizze V1): die Rechnung (`core/kursvorschau.py`) und die
Methode, die ihr die echten Daten gibt (`KursRepo.kommt_noch`). Ohne flet.

Der Kurs der Skizze: Kapitel 1 bringt die Planke, Kapitel 2 den Käfer; Kapitel 3 den Seitstütz
und einen Timer für die Planke; Kapitel 4 lässt eine von drei Übungen wählen und setzt ihr Ziel
aus einem Test; Kapitel 5 verbindet Käfer und Seitstütz. Die Vorschau **ändert nichts**, und
wo Wahl oder Test fehlen, sagt sie nur, dass etwas kommt.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

import pytest

from trainingsapp.core import kursplan as kp
from trainingsapp.core.kursbloecke import (
    AUSWAHL,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    Block,
)
from trainingsapp.core.kurse import FREI, Kapitel, Kurs, Kursplan
from trainingsapp.core.kursvorschau import DAZU, EINSTELLEN, WEG, KapitelVorschau, kommt_noch
from trainingsapp.core.models import Exercise, Plan, Session, Subject
from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
from trainingsapp.core.timer import Abschnitt, TimerProfil
from trainingsapp.data.db import oeffnen
from trainingsapp.data.kurse import KursRepo
from trainingsapp.data.repositories import ExerciseRepo, PlanRepo, SessionRepo, SubjectRepo

NAMEN = {"p": "Planke", "k": "Käfer", "s": "Seitstütz", "b": "Brücke", "v": "Vogel", "r": "Rolle"}
ZEICHEN = {DAZU: "+", EINSTELLEN: "~", WEG: "→"}


def _timer(sekunden: int, runden: int = 1) -> dict:
    return TimerProfil(abschnitte=[Abschnitt("Halten", sekunden)], runden=runden).als_dict()


def skizzen_kurs(ids: Mapping[str, str] | None = None) -> Kurs:
    """Der Kurs der Skizze V1 — ``ids``: Kürzel → Übungs-ID (ohne: das Kürzel selbst)."""
    u = dict(ids) if ids is not None else {k: k for k in NAMEN}
    return Kurs(
        name="Rumpf-Kurs",
        kursplan=Kursplan("Rumpf"),
        kapitel=[
            Kapitel(
                titel="Grundlage",
                bloecke=[Block(PLAN_UEBUNG, id="planke", uebung=u["p"], ziel={"reps": [20]})],
            ),
            Kapitel(
                titel="Erweiterung",
                bloecke=[
                    Block(
                        PLAN_UEBUNG, id="kaefer", uebung=u["k"], hinter="planke", timer=_timer(60)
                    )
                ],
            ),
            Kapitel(
                titel="Seitlich",
                bloecke=[
                    Block(PLAN_UEBUNG, id="seit", uebung=u["s"], hinter="kaefer"),
                    Block(PLAN_EINSTELLEN, id="runden", an="planke", timer=_timer(60, 3)),
                ],
            ),
            Kapitel(
                titel="Deine Wahl",
                bloecke=[
                    Block(AUSWAHL, id="wahl", uebungen=[u["b"], u["v"], u["r"]], anzahl=1),
                    Block(TEST, id="test", aus="wahl", feld="reps"),
                    Block(PLAN_UEBUNG, id="dazu", aus="wahl", ziel_aus="test"),
                ],
            ),
            Kapitel(
                titel="Abschluss",
                bloecke=[
                    Block(PLAN_WEG, id="weg", von="kaefer", zu="seit", kante={"ausloeser": "zeit"})
                ],
            ),
        ],
    )


def uebernommen(kurs: Kurs, bis: int, namen: Mapping[str, str] = NAMEN) -> tuple[Plan, dict]:
    """Plan und Kurs-Stand, nachdem die ersten ``bis`` Kapitel ganz übernommen sind."""
    alle = [b for k in kurs.kapitel for b in k.bloecke]
    plan = kp.grundplan(kurs, "s1", set(namen))
    stand: dict = kp.grundstand(plan)
    for kapitel in kurs.kapitel[:bis]:
        zeilen = kp.aenderungen(plan, kapitel.bloecke, {}, {}, stand, namen, bezug=alle)
        plan, stand = kp.anwenden(
            plan, kapitel.bloecke, {}, {}, {z.id for z in zeilen}, (), stand, namen, bezug=alle
        )
    return plan, stand


def als_text(vorschau: list[KapitelVorschau]) -> list[str]:
    """Die Karte, wie sie zu lesen ist: Überschrift, darunter Zeichen und Satz."""
    zeilen: list[str] = []
    for kapitel in vorschau:
        zeilen.append(kapitel.kopf)
        zeilen.extend(f"{ZEICHEN[z.art]} {z.text}" for z in kapitel.zeilen)
    return zeilen


# ---------------------------------------------------------------------------
# Die Rechnung
# ---------------------------------------------------------------------------


def test_die_skizze_kapitel_2_laeuft() -> None:
    """Kapitel 1 ist übernommen, Kapitel 2 läuft und ist es noch nicht: Es gilt als
    übernommen (der Käfer ist Anker in Kapitel 3 und trägt die 60 s für den Weg in Kapitel 5),
    gezeigt wird es nicht."""
    kurs = skizzen_kurs()
    plan, stand = uebernommen(kurs, 1)
    vorschau = kommt_noch(kurs, plan, stand, {}, {}, 1, NAMEN)
    assert als_text(vorschau) == [
        "Kapitel 3 · Seitlich",
        "+ Seitstütz kommt dazu, hinter Käfer",
        "~ Timer für Planke: 1:00 Halten · 3 Runden",
        "Kapitel 4 · Deine Wahl",
        "+ eine Übung, die du dort wählst (1 von 3)",
        "~ ihr Ziel aus deinem Test",
        "Kapitel 5 · Abschluss",
        "→ von Käfer weiter zu Seitstütz nach 60 s",
    ]
    assert [k.nummer for k in vorschau] == [3, 4, 5]
    # offen ist nur, was an Wahl und Test hängt
    assert [[z.offen for z in k.zeilen] for k in vorschau] == [
        [False, False],
        [True, True],
        [False],
    ]


def test_die_vorschau_aendert_nichts() -> None:
    kurs = skizzen_kurs()
    plan, stand = uebernommen(kurs, 1)
    vorher = (copy.deepcopy(plan), copy.deepcopy(stand), copy.deepcopy(kurs))
    wahl, werte = {"wahl": ["b"]}, {"test:b": 24.0}
    kommt_noch(kurs, plan, stand, wahl, werte, 1, NAMEN)
    assert (plan, stand, kurs) == vorher
    assert [i.exercise_id for i in plan.items] == ["p"]  # der Käfer steht nur in der Kopie
    assert wahl == {"wahl": ["b"]} and werte == {"test:b": 24.0}


def test_offene_zeilen_wahl_und_test() -> None:
    """Ohne Wahl nur, **dass** etwas kommt; mit Wahl die Übung, ihr Ziel wartet auf den
    Test; mit Test steht der Wert da."""
    kurs = skizzen_kurs()
    plan, stand = uebernommen(kurs, 1)

    def vier(wahl: dict, werte: dict) -> list[str]:
        vorschau = kommt_noch(kurs, plan, stand, wahl, werte, 1, NAMEN)
        return als_text([k for k in vorschau if k.nummer == 4])[1:]

    assert vier({}, {}) == [
        "+ eine Übung, die du dort wählst (1 von 3)",
        "~ ihr Ziel aus deinem Test",
    ]
    assert vier({"wahl": ["b"]}, {}) == [
        "+ Brücke kommt dazu, ans Ende",
        "~ Ziel für Brücke aus deinem Test",
    ]
    assert vier({"wahl": ["b"]}, {"test:b": 24.0}) == [
        "+ Brücke kommt dazu, ans Ende",
        "~ Ziel für Brücke: 24 Wiederholungen",
    ]
    # der Wert einer anderen Übung zählt nicht für die gewählte
    assert vier({"wahl": ["b"]}, {"test:v": 24.0})[1] == "~ Ziel für Brücke aus deinem Test"


def test_auswahl_zaehlt_nur_was_es_hier_gibt_und_nennt_ihr_kapitel() -> None:
    """„(2 von 2)“: gezählt wird wie in der Auswahl des Kapitels — nur Übungen, die es hier
    gibt. Steht die Auswahl in einem anderen Kapitel als ihr Baustein, heißt es nicht „dort“."""
    kurs = skizzen_kurs()
    wahl, _test, dazu = kurs.kapitel[3].bloecke
    wahl.anzahl = 2
    dazu.timer, dazu.felder = _timer(30), ["reps"]
    plan, stand = uebernommen(kurs, 1)
    ohne_rolle = {k: v for k, v in NAMEN.items() if k != "r"}
    vier = kommt_noch(kurs, plan, stand, {}, {}, 1, ohne_rolle)[1]
    assert als_text([vier])[1:] == [
        "+ 2 Übungen, die du dort wählst (2 von 2)",
        "~ ihr Ziel aus deinem Test",
        "~ ihre Parameter",
        "~ ihr Timer",
    ]

    # die Auswahl steht in Kapitel 2 (es läuft), der Baustein in Kapitel 4
    kurs = skizzen_kurs()
    auswahl = kurs.kapitel[3].bloecke.pop(0)
    kurs.kapitel[1].bloecke.insert(0, auswahl)
    plan, stand = uebernommen(kurs, 1)
    vier = kommt_noch(kurs, plan, stand, {}, {}, 1, NAMEN)[1]
    assert vier.zeilen[0].text == "eine Übung, die du in Kapitel 2 wählst (1 von 3)"


def _mit_bezug_auf_die_gewaehlte() -> Kurs:
    """Kapitel 5 bezieht sich dreimal auf die Gewählte aus Kapitel 4: ein Weg zu ihr, eine
    Einstellung an ihr, eine Übung hinter ihr."""
    kurs = skizzen_kurs()
    kurs.kapitel[4].bloecke = [
        Block(PLAN_WEG, id="hin", von="seit", zu="dazu", kante={"ausloeser": "wdh", "n": 12}),
        Block(PLAN_EINSTELLEN, id="mehr", an="dazu", ziel={"reps": [15]}, timer=_timer(45)),
        Block(PLAN_UEBUNG, id="rolle", uebung="r", hinter="dazu", ziel={"reps": [8]}),
        Block(PLAN_WEG, id="raus", von="dazu", zu="ende"),
        Block(PLAN_EINSTELLEN, id="hart", uebergang="hart"),
    ]
    return kurs


def test_bezug_auf_eine_wahl_aus_einem_frueheren_kapitel_ist_offen() -> None:
    """`core.kursplan` rechnet je Kapitel: Fehlt die Wahl aus Kapitel 4, hält es in Kapitel 5
    die Gewählte für „nicht mehr in deinem Plan“ (entfällt, Anker fehlt). In der Vorschau ist
    das offen — die Übung gibt es nur noch nicht."""
    kurs = _mit_bezug_auf_die_gewaehlte()
    plan, stand = uebernommen(kurs, 3)  # bis Kapitel 3 übernommen, Kapitel 4 läuft ohne Wahl
    alle = [b for k in kurs.kapitel for b in k.bloecke]
    fuenf = kurs.kapitel[4].bloecke

    # nachgestellt: so sagt es die Rechnung des Kapitels selbst
    roh = kp.aenderungen(plan, fuenf, {}, {}, stand, NAMEN, bezug=alle)
    assert [(z.id, z.stand) for z in roh] == [
        ("hin#weg", kp.ENTFAELLT),
        ("mehr", kp.ENTFAELLT),
        ("rolle", kp.ANKER_FEHLT),
        ("rolle#ziel", kp.NEU),
        ("raus#weg", kp.ENTFAELLT),
        ("hart#uebergang", kp.NEU),
    ]
    # N172 (16.11.2026): der Satz nennt den Grund — die Wahl fehlt, nichts wurde weggenommen
    assert roh[1].unter == "Deine Auswahl fehlt noch."
    assert roh[2].unter == "Deine Auswahl, hinter die es gehört, fehlt noch."

    (vorschau,) = kommt_noch(kurs, plan, stand, {}, {}, 3, NAMEN)
    assert als_text([vorschau]) == [
        "Kapitel 5 · Abschluss",
        "→ von Seitstütz weiter zu deiner Auswahl",
        "~ Ziel für deine Auswahl aus dem Kurs",
        "~ Timer für deine Auswahl",
        "+ Rolle kommt dazu, hinter deine Auswahl",
        "~ Ziel für Rolle: 8 Wiederholungen",
        "→ von deiner Auswahl weiter zum Ende",
        "~ Übergang im Workout: hart",
    ]
    assert [z.offen for z in vorschau.zeilen] == [True, True, True, True, False, True, False]
    assert not any("nicht mehr in deinem Plan" in z.text for z in vorschau.zeilen)

    # mit der Wahl stehen die Namen da
    (mit,) = kommt_noch(kurs, plan, stand, {"wahl": ["b"]}, {"test:b": 20.0}, 3, NAMEN)
    assert als_text([mit])[1:] == [
        "→ von Seitstütz weiter zu Brücke nach 12 Wdh.",
        "~ Ziel für Brücke: 15 Wiederholungen",
        "~ Timer für Brücke: 0:45 Halten",
        "+ Rolle kommt dazu, hinter Brücke",
        "~ Ziel für Rolle: 8 Wiederholungen",
        "→ von Brücke weiter zum Ende",
        "~ Übergang im Workout: hart",
    ]


def test_was_hinter_der_gewaehlten_wartet_heisst_beim_namen() -> None:
    """Eine feste Übung hinter der Gewählten wartet mit auf die Wahl. Ein Baustein, der sich
    auf **sie** bezieht, meint nicht „deine Auswahl“ — und `core.kursplan` hielte sie für
    „nicht mehr in deinem Plan“."""
    kurs = skizzen_kurs()
    kurs.kapitel[3].bloecke += [
        Block(PLAN_UEBUNG, id="rolle", uebung="r", hinter="dazu", ziel={"reps": [8]}),
        Block(PLAN_EINSTELLEN, id="lang", an="rolle", timer=_timer(30)),
        Block(PLAN_WEG, id="hin", von="dazu", zu="rolle"),
    ]
    kurs.kapitel[4].bloecke = [Block(PLAN_UEBUNG, id="vogel", uebung="v", hinter="rolle")]
    plan, stand = uebernommen(kurs, 3)
    alle = [b for k in kurs.kapitel for b in k.bloecke]

    roh = kp.aenderungen(plan, kurs.kapitel[3].bloecke, {}, {}, stand, NAMEN, bezug=alle)
    assert [(z.id, z.stand) for z in roh] == [
        ("dazu", kp.OFFEN),
        ("rolle", kp.OFFEN),
        ("lang", kp.ENTFAELLT),
        ("hin#weg", kp.OFFEN),
    ]
    assert roh[2].unter == "Rolle ist noch nicht in deinem Plan."  # sie wartet (N172)

    vorschau = kommt_noch(kurs, plan, stand, {}, {}, 2, NAMEN)  # Kapitel 3 läuft
    assert als_text(vorschau) == [
        "Kapitel 4 · Deine Wahl",
        "+ eine Übung, die du dort wählst (1 von 3)",
        "~ ihr Ziel aus deinem Test",
        "+ Rolle kommt dazu, hinter deine Auswahl",
        "~ Ziel für Rolle aus dem Kurs",
        "~ Timer für Rolle",
        "→ von deiner Auswahl weiter zu Rolle",
        "Kapitel 5 · Abschluss",
        "+ Vogel kommt dazu, hinter Rolle",
    ]
    assert all(z.offen for k in vorschau for z in k.zeilen)


def test_wo_der_plan_abweicht_steht_der_satz_und_der_eigene_wert_bleibt() -> None:
    """Die Person hat der Planke einen eigenen Timer gegeben: Kapitel 3 wird fragen — die
    Vorschau sagt es, ohne Wertung, und rechnet mit ihrem Wert weiter."""
    kurs = skizzen_kurs()
    plan, stand = uebernommen(kurs, 2)
    planke = plan.items[0]
    planke.timer = {"eigen": _timer(90)}
    drei = kommt_noch(kurs, plan, stand, {}, {}, 1, NAMEN)[0]
    assert als_text([drei]) == [
        "Kapitel 3 · Seitlich",
        "+ Seitstütz kommt dazu, hinter Käfer",
        "~ Planke: Du hast 1:30 Halten eingestellt. Der Kurs schlägt 1:00 Halten · 3 Runden vor.",
    ]
    assert not drei.zeilen[1].offen


def test_aus_dem_plan_genommen_ans_ende_und_entfaellt_mit_grund() -> None:
    """Die Person hat den Käfer aus dem Plan genommen: Der Seitstütz (hinter Käfer) kommt ans
    Ende, der Weg von Käfer zu Seitstütz entfällt — mit dem Grund, ohne Wertung."""
    kurs = skizzen_kurs()
    plan, stand = uebernommen(kurs, 2)
    plan.items = [i for i in plan.items if i.exercise_id != "k"]
    vorschau = kommt_noch(kurs, plan, stand, {}, {}, 2, NAMEN)  # Kapitel 3 läuft
    assert als_text(vorschau) == [
        "Kapitel 4 · Deine Wahl",
        "+ eine Übung, die du dort wählst (1 von 3)",
        "~ ihr Ziel aus deinem Test",
        "Kapitel 5 · Abschluss",
        "→ Ein Weg entfällt — Käfer ist nicht mehr in deinem Plan.",
    ]
    # und in Kapitel 3 selbst, solange Kapitel 2 läuft
    drei = kommt_noch(kurs, plan, stand, {}, {}, 1, NAMEN)[0]
    assert als_text([drei])[1] == "+ Seitstütz kommt ans Ende"


def test_spaeter_in_einem_frueheren_kapitel_gilt_als_uebernommen() -> None:
    """Kapitel 1 ist fertig, aber nichts daraus übernommen („Später“): „So wüchse der Plan,
    wenn du alles übernimmst“ — die Planke gilt nicht als „nicht mehr in deinem Plan“."""
    kurs = skizzen_kurs()
    plan, stand = uebernommen(kurs, 0)
    assert not plan.items
    vorschau = kommt_noch(kurs, plan, stand, {}, {}, 1, NAMEN)
    assert als_text(vorschau)[:3] == [
        "Kapitel 3 · Seitlich",
        "+ Seitstütz kommt dazu, hinter Käfer",
        "~ Timer für Planke: 1:00 Halten · 3 Runden",
    ]
    assert not any("entfällt" in z or "ans Ende" in z for z in als_text(vorschau))


def test_uebernommenes_kommt_nicht_vor_und_am_ende_kommt_nichts() -> None:
    kurs = skizzen_kurs()
    # Kapitel 3 ist schon übernommen (Freischaltung „frei“), Kapitel 2 läuft noch
    plan, stand = uebernommen(kurs, 3)
    assert [k.nummer for k in kommt_noch(kurs, plan, stand, {}, {}, 1, NAMEN)] == [4, 5]
    # alles übernommen, was ohne Wahl geht: nur Kapitel 4 hat noch etwas
    plan, stand = uebernommen(kurs, 5)
    assert [k.nummer for k in kommt_noch(kurs, plan, stand, {}, {}, 1, NAMEN)] == [4]
    # im letzten Kapitel kommt nichts mehr; ohne Kursplan gibt es keine Vorschau
    assert kommt_noch(kurs, plan, stand, {}, {}, 4, NAMEN) == []
    kurs.kursplan = None
    assert kommt_noch(kurs, plan, stand, {}, {}, 1, NAMEN) == []


# ---------------------------------------------------------------------------
# Die Datenbank: `KursRepo.kommt_noch`
# ---------------------------------------------------------------------------


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    yield verbindung
    verbindung.close()


@pytest.fixture
def profil(con) -> Subject:
    s = Subject(name="Test")
    SubjectRepo(con).speichern(s)
    return s


def kurs_in_der_datenbank(con, freischaltung: str = "") -> tuple[Kurs, dict[str, str]]:
    """Der Kurs der Skizze mit eigenen Übungen — gespeichert und wieder geladen."""
    ids: dict[str, str] = {}
    for kuerzel, name in NAMEN.items():
        uebung = Exercise(name=name, result_spec=SPEC_SAETZE_WDH)
        ExerciseRepo(con).speichern(uebung)
        ids[kuerzel] = uebung.id
    kurs = skizzen_kurs(ids)
    if freischaltung:
        kurs.freischaltung = freischaltung
    repo = KursRepo(con)
    repo.speichern(kurs)
    geladen = repo.laden(kurs.id)
    assert geladen is not None
    return geladen, ids


def alles_uebernehmen(repo: KursRepo, kurs: Kurs, kapitel: Kapitel, profil_id: str) -> None:
    zeilen = repo.plan_aenderungen(kurs, kapitel, profil_id)
    repo.plan_uebernehmen(kurs, kapitel, profil_id, {z.id for z in zeilen})


def test_repo_keine_vorschau_vor_dem_start_ohne_kursplan_und_am_ende(con, profil) -> None:
    repo = KursRepo(con)
    kurs, _ids = kurs_in_der_datenbank(con)
    assert repo.kommt_noch(kurs, profil.id) == []  # noch kein Kapitel erreicht

    repo.starten(kurs, profil.id)
    assert [k.nummer for k in repo.kommt_noch(kurs, profil.id)] == [2, 3, 4, 5]

    ohne = Kurs(name="Ohne Kursplan", kapitel=[Kapitel(titel="A"), Kapitel(titel="B")])
    repo.speichern(ohne)
    repo.starten(ohne, profil.id)
    assert repo.kommt_noch(ohne, profil.id) == []

    for kapitel in kurs.kapitel:
        repo.kapitel_abschliessen(kurs, kapitel, profil.id)
    assert repo.kommt_noch(kurs, profil.id) == []  # der Kurs ist abgeschlossen


def test_repo_liest_nur_auch_wenn_es_den_plan_noch_nicht_gibt(con, profil) -> None:
    """Begonnen, nichts übernommen: gerechnet wird gegen die Grundlage — kein Plan entsteht,
    nichts wird geschrieben."""
    repo = KursRepo(con)
    kurs, _ids = kurs_in_der_datenbank(con)
    repo.starten(kurs, profil.id)
    assert repo.kursplan(kurs, profil.id) is None  # leere Grundlage

    vorher = con.total_changes
    vorschau = repo.kommt_noch(kurs, profil.id)
    assert con.total_changes == vorher and not con.in_transaction
    assert repo.kursplan(kurs, profil.id) is None
    assert PlanRepo(con).alle(profil.id) == []
    assert als_text(vorschau)[:2] == [
        "Kapitel 2 · Erweiterung",
        "+ Käfer kommt dazu, hinter Planke",
    ]

    # mit Plan ebenso: Plan und Kurs-Stand bleiben, wie sie sind
    alles_uebernehmen(repo, kurs, kurs.kapitel[0], profil.id)
    plan = repo.kursplan(kurs, profil.id)
    stand = PlanRepo(con).kurs_stand(plan.id)
    vorher = con.total_changes
    repo.kommt_noch(kurs, profil.id, {"wahl": [kurs.kapitel[3].bloecke[0].uebungen[0]]})
    assert con.total_changes == vorher
    assert repo.kursplan(kurs, profil.id) == plan
    assert PlanRepo(con).kurs_stand(plan.id) == stand


def test_repo_die_skizze_mit_echtem_plan_wahl_und_test(con, profil) -> None:
    """Kapitel 1 übernommen und abgeschlossen, Kapitel 2 läuft. Die Wahl kommt erst als
    offene Wahl der Sitzung (Argument), dann steht sie im Plan; der Testwert kommt aus einem
    gewöhnlichen Eintrag, sobald das Kapitel mit dem Test erreicht ist."""
    repo = KursRepo(con)
    kurs, ids = kurs_in_der_datenbank(con, FREI)
    eins, zwei, drei, vier, _fuenf = kurs.kapitel
    repo.starten(kurs, profil.id)
    alles_uebernehmen(repo, kurs, eins, profil.id)
    repo.kapitel_abschliessen(kurs, eins, profil.id)

    assert als_text(repo.kommt_noch(kurs, profil.id)) == [
        "Kapitel 3 · Seitlich",
        "+ Seitstütz kommt dazu, hinter Käfer",
        "~ Timer für Planke: 1:00 Halten · 3 Runden",
        "Kapitel 4 · Deine Wahl",
        "+ eine Übung, die du dort wählst (1 von 3)",
        "~ ihr Ziel aus deinem Test",
        "Kapitel 5 · Abschluss",
        "→ von Käfer weiter zu Seitstütz nach 60 s",
    ]

    # die offene Wahl der Sitzung: die Übung steht da, ihr Ziel wartet auf den Test
    offen = {"wahl": [ids["b"]]}
    vier_zeilen = als_text(repo.kommt_noch(kurs, profil.id, offen))[4:6]
    assert vier_zeilen == ["+ Brücke kommt dazu, ans Ende", "~ Ziel für Brücke aus deinem Test"]

    # der Test: ein gewöhnlicher Eintrag der Brücke, nachdem Kapitel 4 erreicht ist („frei“)
    repo.kapitel_erreichen(kurs, vier, profil.id)
    sitzungen = SessionRepo(con)
    session = Session(subject_id=profil.id)
    sitzungen.anlegen(session)
    sitzungen.eintrag_anlegen(session, ExerciseRepo(con).laden(ids["b"]), {"reps": [22]})
    vier_zeilen = als_text(repo.kommt_noch(kurs, profil.id, offen))[4:6]
    assert vier_zeilen == ["+ Brücke kommt dazu, ans Ende", "~ Ziel für Brücke: 22 Wiederholungen"]

    # Kapitel 4 übernommen: Die Wahl steht im Plan und gilt ohne Argument — Kapitel 4 hat
    # nichts mehr, und Übernommenes aus Kapitel 3 fehlt ebenso
    zeilen = repo.plan_aenderungen(kurs, vier, profil.id, offen)
    repo.plan_uebernehmen(kurs, vier, profil.id, {z.id for z in zeilen}, wahl=offen)
    repo.plan_uebernehmen(kurs, drei, profil.id, {"runden#timer"})
    assert als_text(repo.kommt_noch(kurs, profil.id)) == [
        "Kapitel 3 · Seitlich",
        "+ Seitstütz kommt dazu, hinter Käfer",
        "Kapitel 5 · Abschluss",
        "→ von Käfer weiter zu Seitstütz nach 60 s",
    ]
    # Kapitel 2 abgeschlossen (nichts übernommen): Kapitel 3 läuft und fällt aus der Vorschau
    repo.kapitel_abschliessen(kurs, zwei, profil.id)
    assert [k.nummer for k in repo.kommt_noch(kurs, profil.id)] == [5]
