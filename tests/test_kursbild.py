"""Das Bild des Kursplans im Kurs-Editor (`core/kursbild.py`, Ben 16.11.2026) — flet-frei.

Der Zielplan nach allen Kapiteln, und welches Kapitel was bringt: Planübungen und Wege.
"""

from __future__ import annotations

from itertools import pairwise

from trainingsapp.core import ablauf as ab
from trainingsapp.core.kursbau import Kurssicht
from trainingsapp.core.kursbild import GRUNDLAGE_NR, planbild
from trainingsapp.core.kursbloecke import (
    AUSWAHL,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    Block,
)
from trainingsapp.core.kurse import Kapitel, Kurs, Kursplan, PlanVorlage, VorlageItem
from trainingsapp.core.models import Exercise

KATALOG = {
    k: Exercise(id=k, name=k.title()) for k in ("planke", "kaefer", "bruecke", "seit", "dehnen")
}


def _sicht(kurs: Kurs) -> Kurssicht:
    erstes = kurs.kapitel[0] if kurs.kapitel else Kapitel()
    return Kurssicht(kurs, erstes.id, erstes.bloecke, KATALOG)


def _namen(bild, ids) -> list[str]:
    je_id = {i.id: KATALOG[i.exercise_id].name for i in bild.plan.items}
    return [je_id.get(i, i) for i in ids]


def _rumpf() -> Kurs:
    return Kurs(
        name="Rumpf-Kurs",
        kursplan=Kursplan("Rumpf"),
        kapitel=[
            Kapitel(
                id="k1",
                titel="Anfang",
                bloecke=[Block(PLAN_UEBUNG, id="a", uebung="planke", ziel={"hold": [60]})],
            ),
            Kapitel(
                id="k2",
                titel="Erweiterung",
                bloecke=[
                    Block(AUSWAHL, id="w", uebungen=["kaefer", "bruecke"], anzahl=1),
                    Block(TEST, id="t", aus="w", feld="reps"),
                    Block(PLAN_UEBUNG, id="dazu", aus="w", hinter="a", ziel_aus="t"),
                    Block(PLAN_WEG, id="weg", von="a", zu="dazu", kante={"ausloeser": "zeit"}),
                ],
            ),
            Kapitel(
                id="k3",
                titel="Seitlich",
                bloecke=[
                    Block(PLAN_UEBUNG, id="s", uebung="seit", hinter="dazu"),
                    Block(PLAN_EINSTELLEN, id="mehr", an="a", ziel={"hold": [90]}),
                    Block(PLAN_WEG, id="raus", von="s", zu="ende"),
                ],
            ),
        ],
    )


def test_zielplan_nach_allen_kapiteln_und_was_jedes_bringt() -> None:
    bild = planbild(_sicht(_rumpf()))
    assert bild is not None
    assert [(KATALOG[i.exercise_id].name, bild.kapitel[i.id]) for i in bild.plan.items] == [
        ("Planke", 1),
        ("Kaefer", 2),  # die Beispielwahl: die erste der Auswahl
        ("Seit", 3),
    ]
    planke, kaefer, seit = (i.id for i in bild.plan.items)
    assert bild.plan.items[0].target == {"hold": [90]}  # Kapitel 3 hat gesteigert
    # was erst später freigegeben wird, ist im Bild blass
    assert _namen(bild, bild.spaeter(0)) == ["Planke", "Kaefer", "Seit"]
    assert _namen(bild, bild.spaeter(1)) == ["Kaefer", "Seit"]
    assert _namen(bild, bild.spaeter(2)) == ["Seit"] and bild.spaeter(3) == []
    assert [bild.stand(n) for n in range(4)] == [(0, 3), (1, 3), (2, 3), (3, 3)]
    assert _namen(bild, bild.bringt(2)) == ["Kaefer"]
    # die Wege kommen aus Bausteinen — das Bild kennt Kapitel und Block
    assert bild.workout
    assert {k: (w.nr, w.kapitel_id, w.block_id) for k, w in bild.wege.items()} == {
        (planke, kaefer): (2, "k2", "weg"),
        (seit, ab.ENDE): (3, "k3", "raus"),
    }
    # die Marke, mit der ein neuer Weg die Planübung nennt
    assert [bild.marke(i) for i in (planke, kaefer, seit)] == ["a", "dazu:kaefer", "s"]
    # gezeichnet wird der Ablauf des Plans
    assert {(k.von, k.nach) for k in bild.ablauf.kanten} >= set(bild.wege)


def test_uebung_ohne_weg_steht_im_plan_aber_nicht_im_ablauf() -> None:
    """Ein Weg, der nicht der Reihe der Liste folgt, macht den Ablauf eigen — eine Übung, die
    ein späteres Kapitel ohne Weg bringt, hängt dann nicht mehr von selbst an der Kette. Das
    Bild zeichnet sie nicht; `lose` nennt sie, damit die Karte es sagen kann."""
    kurs = Kurs(
        name="K",
        kursplan=Kursplan("Plan"),
        kapitel=[
            Kapitel(
                id="k1",
                titel="A",
                bloecke=[
                    Block(PLAN_UEBUNG, id="p", uebung="planke"),
                    Block(PLAN_UEBUNG, id="s", uebung="seit"),
                    Block(PLAN_UEBUNG, id="k", uebung="kaefer"),
                    Block(PLAN_WEG, id="vorbei", von="p", zu="k"),  # an „Seit“ vorbei
                ],
            ),
            Kapitel(id="k2", titel="B", bloecke=[Block(PLAN_UEBUNG, id="d", uebung="dehnen")]),
        ],
    )
    bild = planbild(_sicht(kurs))
    assert bild is not None and bild.workout
    assert _namen(bild, bild.lose()) == ["Dehnen"]
    assert bild.stand(2) == (4, 4) and bild.kapitel[bild.lose()[0]] == 2  # im Plan ist sie
    # solange die Wege der Reihe der Liste folgen, hängt eine neue Übung von selbst an
    assert planbild(_sicht(_rumpf())).lose() == []


def test_eine_liste_wird_der_reihe_nach_gezeichnet() -> None:
    """Ohne Weg ist der Kursplan eine Liste — das Bild zeigt die Übungen untereinander, damit
    man sieht, was da ist und woran sich ein Weg hängen ließe."""
    kurs = _rumpf()
    for kap in kurs.kapitel:
        kap.bloecke = [b for b in kap.bloecke if b.art != PLAN_WEG]
    bild = planbild(_sicht(kurs))
    assert bild is not None and not bild.workout and bild.wege == {} and bild.lose() == []
    ids = [i.id for i in bild.plan.items]
    assert [(k.von, k.nach) for k in bild.ablauf.kanten] == list(pairwise(ids))
    assert not bild.plan.ablauf.an  # der Plan selbst bleibt eine Liste


def test_grundlage_gehoert_keinem_kapitel() -> None:
    vorlage = PlanVorlage("egal", [], [VorlageItem("planke"), VorlageItem("dehnen")])
    kurs = Kurs(
        name="K",
        kursplan=Kursplan("Plan", vorlage=vorlage),
        kapitel=[
            Kapitel(
                id="k1",
                titel="A",
                bloecke=[
                    Block(PLAN_UEBUNG, id="k", uebung="kaefer", hinter="g:1"),
                    Block(PLAN_WEG, id="w", von="g:1", zu="k"),
                ],
            )
        ],
    )
    bild = planbild(_sicht(kurs))
    assert bild is not None
    assert [(KATALOG[i.exercise_id].name, bild.kapitel[i.id]) for i in bild.plan.items] == [
        ("Planke", GRUNDLAGE_NR),
        ("Kaefer", 1),
        ("Dehnen", GRUNDLAGE_NR),
    ]
    assert bild.stand(GRUNDLAGE_NR) == (2, 3)
    assert [bild.marke(i.id) for i in bild.plan.items] == ["g:1", "k", "g:2"]
    planke, kaefer, _ = (i.id for i in bild.plan.items)
    assert set(bild.wege) == {(planke, kaefer)}


def test_zwei_gewaehlte_ergeben_zwei_wege_desselben_bausteins() -> None:
    kurs = _rumpf()
    kurs.kapitel[1].bloecke[0].anzahl = 2
    kurs.kapitel[2].bloecke = []
    bild = planbild(_sicht(kurs))
    assert bild is not None
    planke, kaefer, bruecke = (i.id for i in bild.plan.items)
    assert {k: w.block_id for k, w in bild.wege.items()} == {
        (planke, kaefer): "weg",
        (planke, bruecke): "weg",
    }


def test_ohne_kursplan_kein_bild_und_ohne_kapitel_ein_leerer_plan() -> None:
    assert planbild(_sicht(Kurs(name="Ohne"))) is None
    leer = planbild(_sicht(Kurs(name="Leer", kursplan=Kursplan("P"))))
    assert leer is not None and leer.plan.items == [] and leer.stand(0) == (0, 0)


def test_das_bild_folgt_den_ungespeicherten_bloecken_des_kapitels() -> None:
    """Im Formular eines Kapitels zählt, was gerade dasteht (`Kurssicht.bloecke`)."""
    kurs = _rumpf()
    zwei = kurs.kapitel[1]
    neu = [*zwei.bloecke, Block(PLAN_UEBUNG, id="d", uebung="dehnen")]
    bild = planbild(Kurssicht(kurs, zwei.id, neu, KATALOG))
    assert bild is not None
    # „Seitstütz“ aus Kapitel 3 steht hinter der Gewählten, die neue Übung am Ende
    assert [(KATALOG[i.exercise_id].name, bild.kapitel[i.id]) for i in bild.plan.items][-2:] == [
        ("Seit", 3),
        ("Dehnen", 2),
    ]
