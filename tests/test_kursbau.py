"""Was der Kurs-Editor rechnet (`core/kursbau.py`; Ben, 16.11.2026, `docs/plan_kurs_ablauf.md`
§11.6): die Sicht auf einen Kurs im Bau — Marken, Verweise ins Leere, Löschfolgen, die
Vorschau der Karte — und die Kopie eines Kurses mit umgeschriebenen Verweisen.

Ohne flet und ohne Datenbank: läuft in der ersten CI-Stufe. Dass die Vorschau dieselben Zeilen
nennt wie `KursRepo.plan_aenderungen` und wie der Editor damit umgeht, prüft
`tests/test_ui_kurs_bausteine.py`.
"""

from __future__ import annotations

from trainingsapp.core.kursbau import Kurssicht, folgen_anwenden, kurs_kopie
from trainingsapp.core.kursbloecke import (
    AUSWAHL,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    TEXT,
    Block,
)
from trainingsapp.core.kurse import Kapitel, Kurs, Kursplan, PlanVorlage, VorlageItem
from trainingsapp.core.kursplan import NEU
from trainingsapp.core.models import Exercise
from trainingsapp.core.pakete import PaketPlan
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld


def _katalog() -> dict[str, Exercise]:
    """Vier Übungen unter ihrem Namen als ID — Planke und Seitstütz halten, Käfer und Brücke
    zählen Wiederholungen."""
    return {
        name: Exercise(id=name, name=name, result_spec=ResultSpec(fields=[vorrat_feld(feld)]))
        for name, feld in (
            ("Planke", "hold"),
            ("Seitstütz", "hold"),
            ("Käfer", "reps"),
            ("Brücke", "reps"),
        )
    }


def _kurs() -> Kurs:
    """Ein Kurs mit Kursplan (Grundlage: Planke) und zwei Kapiteln wie in den Skizzen: Kapitel
    2 hängt die gewählte Übung hinter den Seitstütz des ersten, mit Ziel aus dem Test und einem
    Weg dorthin, und stellt an der Planke der Grundlage ein Ziel ein."""
    eins = Kapitel(
        id="k1",
        titel="Grundlage",
        bloecke=[
            Block(TEXT, id="t1", titel="Die Planke", text="Sie hält den Rumpf still."),
            Block(PLAN_UEBUNG, id="b1", uebung="Seitstütz", ziel={"hold": [40]}),
        ],
    )
    zwei = Kapitel(
        id="k2",
        titel="Erweiterung",
        bloecke=[
            Block(AUSWAHL, id="w", uebungen=["Käfer", "Brücke"], anzahl=1),
            Block(TEST, id="t", uebung="Käfer", feld="reps"),
            Block(PLAN_UEBUNG, id="b2", aus="w", hinter="b1", ziel_aus="t", faktor=0.5),
            Block(PLAN_WEG, id="b3", von="b1", zu="b2", kante={"ausloeser": "zeit"}),
            Block(PLAN_EINSTELLEN, id="b4", an="g:1", ziel={"hold": [75]}),
        ],
    )
    return Kurs(
        id="kurs",
        name="Rumpf-Kurs",
        kapitel=[eins, zwei],
        kursplan=Kursplan(
            "Rumpf", [0, 2, 4], vorlage=PlanVorlage("Basis", items=[VorlageItem("Planke")])
        ),
    )


def _sicht(kurs: Kurs, kapitel: Kapitel) -> Kurssicht:
    return Kurssicht(kurs, kapitel.id, kapitel.bloecke, _katalog())


def test_vorschau_rechnet_auf_dem_beispielplan() -> None:
    """Die Zeilen eines Kapitels, wie die Karte sie nennt: Kapitel davor übernommen, die erste
    Übung jeder Auswahl gewählt, der Beispielwert je Test (30 Wiederholungen × 0,5)."""
    kurs = _kurs()
    eins, zwei = kurs.kapitel
    assert [
        (z.block_id, z.titel, z.unter, z.stand) for z in _sicht(kurs, eins).vorschau().zeilen
    ] == [
        ("b1", "Seitstütz kommt dazu", "ans Ende", NEU),
        ("b1", "Ziel für Seitstütz: 40 s", "aus dem Kurs", NEU),
    ]
    sicht = _sicht(kurs, zwei)
    vorschau = sicht.vorschau()
    assert (vorschau.wahl, vorschau.werte) == ({"w": ["Käfer"]}, {"t": 30})
    assert [(z.block_id, z.titel, z.unter, z.stand) for z in vorschau.zeilen] == [
        ("b2", "Käfer kommt dazu", "hinter Seitstütz", NEU),
        ("b2", "Ziel für Käfer: 15 Wiederholungen", "aus deinem Test", NEU),
        ("b3", "Von Seitstütz weiter zu Käfer, wenn die Zeit ab ist", "aus dem Kurs", NEU),
        ("b4", "Ziel für Planke: 75 s", "aus dem Kurs", NEU),
    ]
    assert sicht.beispiel_text(zwei.bloecke[2], vorschau) == (
        "Beispiel mit der Wahl „Käfer“ und dem Testwert 30 Wiederholungen."
    )
    assert sicht.beispiel_text(zwei.bloecke[4], vorschau) == ""
    # Ein Kurs ohne Kursplan hat keine Zeilen — die Bausteine bewirken dort nichts
    kurs.kursplan = None
    assert _sicht(kurs, zwei).vorschau().zeilen == ()


def test_marken_zur_wahl_und_verweise_ins_leere() -> None:
    kurs = _kurs()
    eins, zwei = kurs.kapitel
    sicht = _sicht(kurs, zwei)
    # Zur Wahl steht, was die Paketprüfung annimmt: die Grundlage und „Übung dazu“ davor
    assert sicht.marken_davor("b2") == [("g:1", "Planke"), ("b1", "Seitstütz")]
    assert [m for m, _ in sicht.marken_davor("b3")] == ["g:1", "b1", "b2"]
    assert [m for m, _ in sicht.marken_davor("neu")] == ["g:1", "b1", "b2"]  # ein neuer: am Ende
    assert sicht.auswahlen() == [("w", "1 von 2: Käfer, Brücke")]
    assert sicht.tests() == [("t", "Käfer")]
    assert [sicht.kurz(b) for b in zwei.bloecke[2:]] == [
        "die gewählte, hinter Seitstütz · Ziel aus dem Test × 0,5",
        "Seitstütz → die gewählte · Zeit ab",
        "Planke: Ziel 75 s",
    ]
    assert not any(sicht.haengt(b) for b in zwei.bloecke)
    # Kapitel vertauscht: Kapitel 2 steht vorn und nennt eine Übung, die erst später kommt
    kurs.kapitel.reverse()
    sicht = _sicht(kurs, zwei)
    assert [sicht.haengt(b) for b in zwei.bloecke[2:]] == [["Wohin"], ["Von"], []]
    assert _sicht(kurs, eins).haengt(eins.bloecke[1]) == []


def test_loeschfolgen_ueber_kapitel() -> None:
    kurs = _kurs()
    eins, zwei = kurs.kapitel
    sicht = _sicht(kurs, eins)
    folgen = sicht.folgen("b1")
    assert [(f.kapitel_id, f.block.id, f.was) for f in folgen] == [
        ("k2", "b2", "kommt ans Ende"),
        ("k2", "b3", "wird mit gelöscht"),
    ]
    assert sicht.folge_text(folgen[0]) == (
        "Erweiterung · Übung dazu — die gewählte, hinter Seitstütz · Ziel aus dem Test × 0,5: "
        "kommt ans Ende"
    )
    danach = folgen_anwenden(zwei.bloecke, folgen)
    assert [(b.id, b.hinter) for b in danach] == [
        ("w", ""),
        ("t", ""),
        ("b2", ""),
        ("b4", ""),
    ]
    assert zwei.bloecke[2].hinter == "b1"  # die Blöcke des Kurses bleiben, bis gespeichert wird
    # Die Auswahl fällt weg: „die gewählte“ gibt es nicht mehr — und mit ihr der Weg dorthin
    assert [(f.block.id, f.neu) for f in _sicht(kurs, zwei).folgen("w")] == [
        ("b2", None),
        ("b3", None),
    ]
    # Ohne Grundlage gibt es g:1 nicht mehr
    assert [(f.block.id, f.was) for f in sicht.folgen("g:1")] == [("b4", "wird mit gelöscht")]


def test_kopie_schreibt_verweise_um() -> None:
    kurs = _kurs()
    kopie = kurs_kopie(kurs)
    assert kopie.id != kurs.id and kopie.package_id is None and kopie.name == "Rumpf-Kurs (Kopie)"
    assert kopie.kursplan is not None and kopie.kursplan is not kurs.kursplan
    assert (kopie.kursplan.name, kopie.kursplan.wochentage) == ("Rumpf", [0, 2, 4])
    assert [i.exercise_id for i in kopie.kursplan.vorlage.items] == ["Planke"]
    assert {k.id for k in kopie.kapitel}.isdisjoint({"k1", "k2"})

    alt = [b for k in kurs.kapitel for b in k.bloecke]
    neu = [b for k in kopie.kapitel for b in k.bloecke]
    assert [b.art for b in neu] == [b.art for b in alt]
    assert {b.id for b in neu}.isdisjoint({b.id for b in alt})
    ids = {a.id: n.id for a, n in zip(alt, neu, strict=True)}
    assert [ids[i] for i in ("b1", "b2", "b3", "b4")] == [
        "uebung-1",
        "uebung-2",
        "weg-1",
        "einstellen-1",
    ]
    uebung, weg, einstellen = neu[4], neu[5], neu[6]
    assert (uebung.aus, uebung.hinter, uebung.ziel_aus) == (ids["w"], "uebung-1", ids["t"])
    assert (weg.von, weg.zu, weg.kante) == ("uebung-1", "uebung-2", {"ausloeser": "zeit"})
    assert einstellen.an == "g:1"  # die Grundlage bleibt
    # Die Karte der Kopie sagt dasselbe wie die des Originals — in beiden Kapiteln
    for kapitel, kopiert in zip(kurs.kapitel, kopie.kapitel, strict=True):
        original = _sicht(kurs, kapitel).vorschau().zeilen
        assert original
        assert [(z.titel, z.unter, z.stand) for z in _sicht(kopie, kopiert).vorschau().zeilen] == [
            (z.titel, z.unter, z.stand) for z in original
        ]
        assert not any(_sicht(kopie, kopiert).haengt(b) for b in kopiert.bloecke)
    assert kurs.kapitel[1].bloecke[2].hinter == "b1"  # das Original bleibt, wie es war


def test_kopie_nimmt_die_grundlage_aus_dem_paket_als_vorlage() -> None:
    """Ein eigener Kurs gehört zu keinem Paket: Der Plan des Pakets, mit dem der Kursplan
    beginnt, kommt darum als Vorlage in die Kopie — sonst begänne er leer."""
    paketplan = PaketPlan("basis", PlanVorlage("Basis", items=[VorlageItem("a"), VorlageItem("b")]))
    gefragt: list[str] = []

    def paketplaene(paket_id: str) -> list[PaketPlan]:
        gefragt.append(paket_id)
        return [paketplan] if paket_id == "p" else []

    kurs = Kurs(
        name="Aus dem Paket",
        package_id="p",
        kursplan=Kursplan("Rumpf", grundlage="basis"),
        kapitel=[Kapitel(bloecke=[Block(PLAN_EINSTELLEN, id="e", an="g:2", ziel={"hold": 30})])],
    )
    kopie = kurs_kopie(kurs, paketplaene)
    assert gefragt == ["p"] and kopie.package_id is None
    assert kopie.kursplan.grundlage == ""  # die Vorlage ersetzt den Verweis ins Paket
    assert [i.exercise_id for i in kopie.kursplan.vorlage.items] == ["a", "b"]
    assert kopie.kapitel[0].bloecke[0].an == "g:2"
    assert kurs.kursplan.vorlage is None and kurs.kursplan.grundlage == "basis"
    # Kennt das Paket den Plan nicht (mehr), bleibt der Schlüssel stehen; ohne Kursplan mit
    # Grundlage wird das Paket gar nicht gefragt
    kurs.kursplan.grundlage = "weg"
    assert kurs_kopie(kurs, paketplaene).kursplan.grundlage == "weg"
    gefragt.clear()
    kurs.kursplan = Kursplan("Rumpf")
    assert kurs_kopie(kurs, paketplaene).kursplan.vorlage is None and gefragt == []
