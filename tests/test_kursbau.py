"""Was der Kurs-Editor rechnet (`core/kursbau.py`; Ben, 16.11.2026, `docs/plan_kurs_ablauf.md`
§11.6): die Sicht auf einen Kurs im Bau — Marken, Verweise ins Leere, Löschfolgen, die
Vorschau der Karte — und die Kopie eines Kurses mit umgeschriebenen Verweisen.

Ohne flet und ohne Datenbank: läuft in der ersten CI-Stufe. Dass die Vorschau dieselben Zeilen
nennt wie `KursRepo.plan_aenderungen` und wie der Editor damit umgeht, prüft
`tests/test_ui_kurs_bausteine.py`.
"""

from __future__ import annotations

from trainingsapp.core.kursbau import (
    AB,
    HOECHSTENS,
    OHNE,
    VON_BIS,
    VORGABE_WAHL,
    Kurssicht,
    Vorgabenwahl,
    faktor_lesen,
    faktor_text,
    folgen_anwenden,
    kurs_kopie,
    name_des_tests,
    timer_einbetten,
    timer_kern,
    zielfeld,
)
from trainingsapp.core.kursbloecke import (
    AUSWAHL,
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
from trainingsapp.core.kurse import Kapitel, Kurs, Kursplan, PlanVorlage, VorlageItem
from trainingsapp.core.kursplan import NEU
from trainingsapp.core.models import Exercise
from trainingsapp.core.pakete import PaketPlan
from trainingsapp.core.result_spec import FELDVORRAT, ResultSpec, vorrat_feld
from trainingsapp.core.takt import AUS, VORLAGEN
from trainingsapp.core.timer import Abschnitt, TimerProfil


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
        ("b2", "Ziel für Käfer: 15 Wiederholungen", "50 % von deinem Test (30 Wdh.)", NEU),
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


def test_parameter_zur_wahl_wie_im_plan() -> None:
    """Die Parameter, die ein Baustein anbieten kann: die der Übung und der übrige Feldvorrat,
    in der Ordnung des Vorrats — bei „der gewählten“ die Parameter aller Übungen der Auswahl."""
    kurs = _kurs()
    sicht = _sicht(kurs, kurs.kapitel[1])
    eigene, vorrat = sicht.parameter(["Seitstütz"])
    assert [f.key for f in eigene] == ["hold"]
    assert [f.key for f in vorrat] == [f.key for f in FELDVORRAT if f.key != "hold"]
    # die Auswahl: Käfer und Brücke zählen Wiederholungen; mit dem Seitstütz käme Halten dazu
    assert [f.key for f in sicht.parameter(sicht.uebungen_von(kurs.kapitel[1].bloecke[2]))[0]] == [
        "reps"
    ]
    eigene, vorrat = sicht.parameter(["Seitstütz", "Käfer", "Brücke", "fehlt"])
    assert [f.key for f in eigene] == ["reps", "hold"]  # Ordnung des Vorrats, nicht der Übungen
    assert not {"reps", "hold"} & {f.key for f in vorrat}
    assert sicht.parameter([]) == ([], [*FELDVORRAT])
    # Die Wahl steht in der Ordnung des Angebots; Unbekanntes bleibt am Ende
    assert sicht.felder_wahl(["Käfer"], ["weight", "alt", "reps", "duration", "weight"]) == [
        "reps",
        "duration",
        "weight",
        "alt",
    ]


def test_takt_vorgabe_und_eingebetteter_timer() -> None:
    kurs = _kurs()
    katalog = _katalog()
    katalog["Käfer"].takt = VORLAGEN["atmung_4_7_8"]
    katalog["Brücke"].takt = AUS
    sicht = Kurssicht(kurs, "k2", kurs.kapitel[1].bloecke, katalog)
    assert sicht.takt_vorgabe(["Käfer"]) == VORLAGEN["atmung_4_7_8"]
    assert sicht.takt_vorgabe(["Brücke"]) is None  # ausdrücklich keiner ist kein Ausgangspunkt
    assert sicht.takt_vorgabe(["Käfer", "Brücke"]) is None  # „die gewählte“: nicht eindeutig
    assert sicht.takt_vorgabe([]) is None

    runden = TimerProfil(
        id="runden",
        name="3 Runden",
        abschnitte=[Abschnitt("Üben", 40), Abschnitt("Pause", 20, zaehlt=False)],
        runden=3,
        bibliothek="runden",
    )
    kopie = timer_einbetten(runden)
    assert kopie["id"] == "runden" and "bibliothek" not in kopie
    eigen = timer_einbetten(runden, "uebung-1")
    assert eigen["id"] == "kurs-uebung-1" and "bibliothek" not in eigen
    assert timer_kern(eigen) == timer_kern(kopie) == timer_kern(runden.als_dict())
    assert runden.id == "runden" and runden.bibliothek == "runden"  # das Profil bleibt
    gelesen = TimerProfil.aus_dict(eigen)
    assert gelesen is not None and gelesen.runden == 3 and gelesen.abschnitte[1].zaehlt is False


def test_vorschau_nennt_parameter_takt_und_timer() -> None:
    """Je Angabe eine Zeile — an der Planübung und am Plan (`core.kursplan.aenderungen`); die
    Zeile des Bausteins in der Liste nennt sie auch."""
    kurs = _kurs()
    eins, zwei = kurs.kapitel
    timer = timer_einbetten(
        TimerProfil(id="x", name="Runden", abschnitte=[Abschnitt("Üben", 40)], runden=3), "b1"
    )
    b1 = eins.bloecke[1]
    b1.felder, b1.takt, b1.timer = ["hold", "weight"], VORLAGEN["atmung_4_6"], timer
    zwei.bloecke[2].felder = []
    zwei.bloecke[2].takt = AUS
    zwei.bloecke.append(
        Block(PLAN_EINSTELLEN, id="b5", takt=VORLAGEN["atmung_4_6"], timer=dict(timer))
    )
    sicht = _sicht(kurs, eins)
    assert [(z.titel, z.unter) for z in sicht.vorschau().zeilen] == [
        ("Seitstütz kommt dazu", "ans Ende"),
        ("Ziel für Seitstütz: 40 s", "aus dem Kurs"),
        ("Parameter für Seitstütz: Haltezeit, Gewicht", "aus dem Kurs"),
        ("Timer für Seitstütz: 0:40 Üben · 3 Runden", "aus dem Kurs"),
        ("Takt für Seitstütz: 4-6 · 6,0/min", "aus dem Kurs"),
    ]
    assert sicht.kurz(b1) == (
        "Seitstütz, ans Ende · Ziel 40 s · Parameter: Haltezeit, Gewicht · "
        "Timer 0:40 Üben · 3 Runden · Takt 4-6 · 6,0/min"
    )
    sicht = _sicht(kurs, zwei)
    titel = [z.titel for z in sicht.vorschau().zeilen]
    assert titel[:4] == [
        "Käfer kommt dazu",
        "Ziel für Käfer: 15 Wiederholungen",
        "Käfer: nur abhaken",
        "Takt für Käfer: kein Takt",
    ]
    assert titel[-2:] == [
        "Timer für alle Übungen: 0:40 Üben · 3 Runden",
        "Takt für alle Übungen: 4-6 · 6,0/min",
    ]
    assert sicht.kurz(zwei.bloecke[2]) == (
        "die gewählte, hinter Seitstütz · Ziel aus dem Test × 0,5 · nur abhaken · kein Takt"
    )
    assert sicht.kurz(zwei.bloecke[-1]) == "Plan: Timer 0:40 Üben · 3 Runden · Takt 4-6 · 6,0/min"


def test_test_misst_die_gewaehlte() -> None:
    """Ben, 16.11.2026: Ein Test darf „die gewählte“ einer Auswahl messen (``aus``). Der Editor
    kennt ihn als Verweis: Name, Zeile, Verweis ins Leere, Löschfolgen, Kopie — und die Vorschau
    nimmt den Beispielwert der Beispielübung."""
    kurs = _kurs()
    zwei = kurs.kapitel[1]
    test = zwei.bloecke[1]
    test.uebung, test.aus = "", "w"
    sicht = _sicht(kurs, zwei)
    assert sicht.tests() == [("t", "die gewählte")]
    assert sicht.kurz(test) == "die gewählte · Wiederholungen"
    assert sicht.uebungen_von(test) == ["Käfer", "Brücke"]
    assert sicht.haengt(test) == []
    # Käfer und Brücke zählen Wiederholungen — das ist das gemeinsame Feld
    assert [f.key for f in sicht.testfelder(sicht.uebungen_von(test))[0]] == ["reps"]

    # Die Vorschau: der Beispielwert steht unter der Beispielübung (die erste der Auswahl)
    vorschau = sicht.vorschau()
    assert (vorschau.wahl, vorschau.werte) == ({"w": ["Käfer"]}, {"t:Käfer": 30})
    assert [(z.block_id, z.titel, z.unter) for z in vorschau.zeilen][:2] == [
        ("b2", "Käfer kommt dazu", "hinter Seitstütz"),
        ("b2", "Ziel für Käfer: 15 Wiederholungen", "50 % von deinem Test (30 Wdh.)"),
    ]
    assert sicht.beispiel_text(zwei.bloecke[2], vorschau) == (
        "Beispiel mit der Wahl „Käfer“ und dem Testwert 30 Wiederholungen."
    )

    # Die Auswahl fällt weg: Der Test hätte keine Übung mehr — er wird mit gelöscht, und mit ihm
    # „die gewählte“ samt Weg
    folgen = sicht.folgen("w")
    assert [(f.block.id, f.was) for f in folgen] == [
        ("t", "wird mit gelöscht"),
        ("b2", "wird mit gelöscht"),
        ("b3", "wird mit gelöscht"),
    ]
    assert sicht.folge_text(folgen[0]) == "Test — die gewählte · Wiederholungen: wird mit gelöscht"
    assert [b.id for b in folgen_anwenden(zwei.bloecke, folgen) if b.id != "w"] == ["b4"]
    # Nur der Test fällt weg: Der Baustein verliert sein Ziel
    assert [(f.block.id, f.was) for f in sicht.folgen("t")] == [
        ("b2", "verliert das Ziel aus dem Test")
    ]

    # Die Auswahl steht erst in einem späteren Kapitel: Der Test hängt
    spaeter = Kapitel(id="k0", titel="Vorab", bloecke=[Block(TEST, id="t0", aus="w", feld="reps")])
    kurs.kapitel.insert(0, spaeter)
    assert _sicht(kurs, spaeter).haengt(spaeter.bloecke[0]) == ["Auswahl"]
    kurs.kapitel.remove(spaeter)

    # Die Kopie schreibt ``aus`` des Tests um wie das der Bausteine
    kopie = kurs_kopie(kurs)
    auswahl, kopierter, uebung = kopie.kapitel[1].bloecke[:3]
    assert auswahl.id != "w" and (kopierter.aus, kopierter.uebung) == (auswahl.id, "")
    assert uebung.ziel_aus == kopierter.id
    assert [z.titel for z in _sicht(kopie, kopie.kapitel[1]).vorschau().zeilen][:2] == [
        "Käfer kommt dazu",
        "Ziel für Käfer: 15 Wiederholungen",
    ]


def test_testfelder_bei_mehreren_uebungen() -> None:
    """Was ein Test messen kann: bei „der gewählten“ das, was alle Übungen der Auswahl haben —
    haben sie nichts gemeinsam, was wenigstens eine hat (und der Editor sagt es)."""
    kurs = _kurs()
    sicht = _sicht(kurs, kurs.kapitel[1])
    assert [f.key for f in sicht.testfelder(["Käfer"])[0]] == ["reps"]
    felder, gemeinsam = sicht.testfelder(["Käfer", "Brücke"])
    assert ([f.key for f in felder], gemeinsam) == (["reps"], True)
    felder, gemeinsam = sicht.testfelder(["Seitstütz", "Käfer"])
    assert ([f.key for f in felder], gemeinsam) == (["reps", "hold"], False)
    assert sicht.testfelder(["fehlt"]) == ([], True)


def test_test_der_gewaehlten_im_kurs_mit_kapitelplaenen_nur_aus_dem_eigenen_kapitel() -> None:
    """Im Kursplan-Kurs steht die Wahl eines früheren Kapitels im Kursplan; mit Kapitelplänen
    kennt ein Kapitel nur seine eigene — so bietet der Test-Dialog die Auswahlen an."""
    eins = Kapitel(id="k1", bloecke=[Block(AUSWAHL, id="w1", uebungen=["Käfer", "Brücke"])])
    zwei = Kapitel(id="k2", bloecke=[Block(AUSWAHL, id="w2", uebungen=["Planke", "Seitstütz"])])
    mit = Kurs(id="a", name="Mit Kursplan", kursplan=Kursplan("Plan"), kapitel=[eins, zwei])
    ohne = Kurs(id="b", name="Kapitelpläne", kapitel=[eins, zwei])
    katalog = _katalog()
    assert [i for i, _ in Kurssicht(mit, "k2", zwei.bloecke, katalog).auswahlen_fuer_test()] == [
        "w1",
        "w2",
    ]
    assert [i for i, _ in Kurssicht(ohne, "k2", zwei.bloecke, katalog).auswahlen_fuer_test()] == [
        "w2"
    ]


# -- Der Test mit Vorgabe (Skizze T5) ----------------------------------------------------------


def test_vorgabenwahl_baut_jede_vorgabe() -> None:
    """Was im Test-Dialog unter „Vorgabe — wann der Test endet“ eingestellt ist: Ohne · Menge ·
    Zeit · Anstrengung (ab · höchstens · von–bis). Jede Wahl ergibt die Vorgabe, die ein Paket
    auch läse, und eine gespeicherte Vorgabe steht wieder so im Dialog."""
    assert list(VORGABE_WAHL.values()) == ["Ohne", "Menge", "Zeit", "Anstrengung"]
    wahl = Vorgabenwahl()
    assert (wahl.art, wahl.vorgabe(), wahl.fehler(), wahl.vorlaeufig()) == (OHNE, None, None, None)
    assert wahl.mit_art(MENGE).mit_menge("12").vorgabe() == Vorgabe(MENGE, 12)
    assert wahl.mit_art(ZEIT).mit_sekunden(90).vorgabe() == Vorgabe(ZEIT, 90)
    skala = wahl.mit_art(SKALA)
    assert skala.vorgabe() == Vorgabe(SKALA, 7)  # „ab 7“ ist die Vorbelegung der Skizze
    assert skala.mit_form(HOECHSTENS).vorgabe() == Vorgabe(SKALA, 0, 4)
    assert skala.mit_form(VON_BIS).vorgabe() == Vorgabe(SKALA, 5, 7)
    # Die Zahlen der anderen Arten bleiben: zurückgeschaltet steht die Menge wieder da
    hin_und_her = wahl.mit_art(MENGE).mit_menge("12").mit_art(SKALA).mit_art(OHNE).mit_art(MENGE)
    assert hin_und_her.vorgabe() == Vorgabe(MENGE, 12)
    # Eine Menge ohne Zahl ist keine Vorgabe — „Übernehmen“ sagt, was fehlt; das Angebot der
    # Felder richtet sich trotzdem schon nach der Art
    leer = wahl.mit_art(MENGE).mit_menge("")
    assert leer.vorgabe() is None and "braucht eine Zahl" in (leer.fehler() or "")
    assert leer.vorlaeufig() == Vorgabe(MENGE)
    # −/+ bleiben in den Grenzen, in denen die Form etwas Eigenes sagt
    assert skala.schritt(AB, 5).vorgabe() == Vorgabe(SKALA, 10)
    assert skala.schritt(AB, -99).vorgabe() == Vorgabe(SKALA, 1)
    hoechstens = skala.mit_form(HOECHSTENS)
    assert hoechstens.schritt(HOECHSTENS, 99).vorgabe() == Vorgabe(SKALA, 0, 9)  # nie „bis 10“
    assert hoechstens.schritt(HOECHSTENS, -99).vorgabe() == Vorgabe(SKALA, 0, 1)
    von_bis = skala.mit_form(VON_BIS)
    assert von_bis.schritt("von", 99).vorgabe() == Vorgabe(SKALA, 6, 7)  # „von“ bleibt darunter
    assert von_bis.schritt("bis", 99).vorgabe() == Vorgabe(SKALA, 5, 9)
    assert von_bis.schritt("bis", -99).vorgabe() == Vorgabe(SKALA, 5, 6)
    assert von_bis.stellen() == (("von", 5), ("bis", 7))
    # Rundreise: was gespeichert ist, steht wieder so da — und ergibt wieder dasselbe
    for vorgabe in (
        Vorgabe(MENGE, 30),
        Vorgabe(ZEIT, 45),
        Vorgabe(SKALA, 7),
        Vorgabe(SKALA, bis=4),
        Vorgabe(SKALA, 5, 7),
    ):
        gelesen = Vorgabenwahl.aus(vorgabe)
        assert gelesen.vorgabe() == vorgabe
        assert Vorgabe.from_dict(vorgabe.to_dict()) == vorgabe  # wie das Paket sie liest
    assert Vorgabenwahl.aus(Vorgabe(SKALA, bis=4)).form == HOECHSTENS
    assert Vorgabenwahl.aus(Vorgabe(SKALA, 5, 7)).form == VON_BIS
    assert Vorgabenwahl.aus(Vorgabe(ZEIT, 90)).zeit_text == "1:30"


def test_faktor_im_feld() -> None:
    """Der Faktor des Tests steht als „mal“ (0,8) oder — ohne Vorgabe, wie bisher — in Prozent
    da; gelesen wird in den Grenzen des Pakets."""
    assert (faktor_text(0.8), faktor_text(0.8, prozent=True)) == ("0,8", "80")
    assert faktor_lesen(faktor_text(0.85)) == 0.85
    assert faktor_lesen(faktor_text(0.85, prozent=True), prozent=True) == 0.85
    assert (faktor_lesen("0"), faktor_lesen("12"), faktor_lesen("x")) == (0.1, 3.0, 1.0)


def test_ins_ziel_kommt_angebot_und_vorbelegung() -> None:
    """Mit Vorgabe steht zur Wahl, was der Lauf vorgibt oder misst — die Wiederholungen (wenn
    die Übung welche hat oder die Vorgabe eine Menge ist) und die Zeitfelder der Übung bzw.
    „Zeit“, nie die Skala. Vorbelegt ist bei einer Menge die Vorgabe selbst (Wiederholungen),
    sonst das Gemessene; eine getroffene Wahl, die weiter gilt, bleibt."""
    kurs = _kurs()
    sicht = _sicht(kurs, kurs.kapitel[1])

    def angebot(uebungen: list[str], vorgabe: Vorgabe | None) -> list[str]:
        return [f.key for f in sicht.zielfelder(uebungen, vorgabe)[0]]

    menge, zeit, skala = Vorgabe(MENGE, 30), Vorgabe(ZEIT, 60), Vorgabe(SKALA, 7)
    # Käfer zählt Wiederholungen; die Uhr zählt bei ihm als „Zeit“
    for vorgabe in (menge, zeit, skala):
        assert angebot(["Käfer"], vorgabe) == ["reps", "duration"]
        assert zielfeld(sicht.zielfelder(["Käfer"], vorgabe)[0]) == "reps"
    assert angebot(["Käfer"], None) == ["reps"]  # ohne Vorgabe wie bisher
    # Die Planke hält: Wiederholungen gibt es nur, wenn die Vorgabe sie verlangt
    assert angebot(["Planke"], menge) == ["reps", "hold"]
    assert angebot(["Planke"], zeit) == angebot(["Planke"], skala) == ["hold"]
    assert zielfeld(sicht.zielfelder(["Planke"], menge)[0]) == "reps"  # die Vorgabe selbst
    assert zielfeld(sicht.zielfelder(["Planke"], zeit)[0]) == "hold"
    assert zielfeld(sicht.zielfelder(["Planke"], skala)[0]) == "hold"  # das Gemessene
    # Eine getroffene Wahl bleibt, solange sie zur Wahl steht — sonst gilt die Vorbelegung
    assert zielfeld(sicht.zielfelder(["Planke"], menge)[0], "hold") == "hold"
    assert zielfeld(sicht.zielfelder(["Käfer"], skala)[0], "duration") == "duration"
    assert zielfeld(sicht.zielfelder(["Planke"], zeit)[0], "reps") == "hold"
    # „die gewählte“: was bei allen zur Wahl steht — die Skala steht nie dabei
    katalog = _katalog()
    katalog["Käfer"].result_spec = ResultSpec(
        fields=[vorrat_feld("reps"), vorrat_feld("scale"), vorrat_feld("weight")]
    )
    mit_skala = Kurssicht(kurs, "k2", kurs.kapitel[1].bloecke, katalog)
    assert [f.key for f in mit_skala.zielfelder(["Käfer", "Brücke"], skala)[0]] == [
        "reps",
        "duration",
    ]
    assert [f.key for f in mit_skala.zielfelder(["Käfer"], None)[0]] == ["reps", "weight"]
    felder, gemeinsam = sicht.zielfelder(["Planke", "Käfer"], skala)
    assert ([f.key for f in felder], gemeinsam) == (["reps", "duration", "hold"], False)
    # „Gemessen wird“: alles außer der Vorgabe — ohne Wiederholungen bei einer Übung ohne sie
    kaefer = Block(TEST, uebung="Käfer", feld="reps")
    planke = Block(TEST, uebung="Planke", feld="hold")
    kaefer.vorgabe, planke.vorgabe = skala, skala
    assert (sicht.misst(kaefer), sicht.misst(planke)) == (["Wiederholungen", "Zeit"], ["Zeit"])
    kaefer.vorgabe, planke.vorgabe = menge, zeit
    assert (sicht.misst(kaefer), sicht.misst(planke)) == (["Zeit", "Anstrengung"], ["Anstrengung"])
    kaefer.vorgabe = None
    assert sicht.misst(kaefer) == []


def test_test_mit_vorgabe_name_zeile_und_vorschau() -> None:
    """Der Test mit Vorgabe heißt nach Übung und Vorgabe („Käfer: bis Anstrengung 7“) — in
    der Liste, in der Wahl „aus dem Test …“ und über der Karte. Die Vorschau rechnet mit einem
    Beispielwert: Steht im Feld die Vorgabe selbst, ist sie es."""
    kurs = _kurs()
    zwei = kurs.kapitel[1]
    test, baustein = zwei.bloecke[1], zwei.bloecke[2]
    sicht = _sicht(kurs, zwei)
    test.vorgabe = Vorgabe(SKALA, 7)
    assert sicht.kurz(test) == "Käfer: bis Anstrengung 7 · Wiederholungen"
    assert sicht.tests() == [("t", "Käfer: bis Anstrengung 7")]
    assert name_des_tests(test, sicht.katalog) == "Käfer: bis Anstrengung 7"
    assert sicht.test_kurz(test, kapitelplan=True) == "Käfer: bis Anstrengung 7 — wird Ziel im Plan"
    # gemessen werden die Wiederholungen: der Beispielwert bleibt 30, die Karte nennt die Regel
    vorschau = sicht.vorschau()
    assert vorschau.werte == {"t": 30}
    ziel = next(z for z in vorschau.zeilen if z.block_id == "b2" and "Ziel" in z.titel)
    assert ziel.titel == "Ziel für Käfer: 15 Wiederholungen"
    assert ziel.unter == "50 % von deinem Test (30 Wdh. bis Anstrengung 7)"
    # „So steht es im Kapitel“: die Überschrift der Testkarte und die Zeile der Sammelkarte —
    # dieselbe, die `vorschau` liefert
    kapitel = sicht.test_vorschau(test)
    assert kapitel.kopf == ("Käfer: bis Anstrengung 7",)
    assert [(wo, z) for wo, z in kapitel.zeilen] == [("", ziel)]
    assert kapitel.beispiel == "Beispiel mit der Wahl „Käfer“ und dem Testwert 30 Wiederholungen."

    # Vorgabe Menge, ins Ziel kommen die Wiederholungen: Der Beispielwert ist die Vorgabe
    test.vorgabe = Vorgabe(MENGE, 12)
    assert sicht.kurz(test) == "Käfer: 12 Wiederholungen"  # das Feld stünde doppelt da
    vorschau = sicht.vorschau()
    assert vorschau.werte == {"t": 12}
    assert "Ziel für Käfer: 6 Wiederholungen" in [z.titel for z in vorschau.zeilen]
    # … ins Ziel kommt die Zeit: gemessen, also ein Beispielwert
    test.feld = "duration"
    assert sicht.kurz(test) == "Käfer: 12 Wiederholungen · Zeit"
    assert sicht.vorschau().werte == {"t": 60}
    test.vorgabe, test.feld = Vorgabe(ZEIT, 45), "reps"
    assert sicht.kurz(test) == "Käfer: 45 Sekunden · Wiederholungen"
    assert sicht.vorschau().werte == {"t": 30}

    # Der Test misst „die gewählte“: je Übung der Beispielwahl eine Überschrift; die
    # Aufforderung ersetzt sie
    test.uebung, test.aus, test.vorgabe = "", "w", Vorgabe(SKALA, 5, 7)
    assert sicht.kurz(test) == "die gewählte: zwischen Anstrengung 5 und 7 · Wiederholungen"
    assert sicht.test_vorschau(test).kopf == ("Käfer: zwischen Anstrengung 5 und 7",)
    test.titel = "Wie viele schaffst du?"
    assert sicht.test_vorschau(test).kopf == ("Wie viele schaffst du?",)
    test.titel = ""

    # Ein Baustein eines späteren Kapitels nimmt sein Ziel aus diesem Test: Die Zeile steht mit
    # dem Titel ihres Kapitels dabei; ohne Kursplan gibt es keine Sammelkarte
    drei = Kapitel(
        id="k3",
        titel="Mehr",
        bloecke=[Block(PLAN_EINSTELLEN, id="b9", an="b2", ziel_aus="t", faktor=1.0)],
    )
    kurs.kapitel.append(drei)
    zeilen = _sicht(kurs, zwei).test_vorschau(test).zeilen
    assert [(wo, z.block_id) for wo, z in zeilen] == [("", "b2"), ("Mehr", "b9")]
    assert zeilen[1][1].titel == "Ziel für Käfer: 30 Wiederholungen"
    assert baustein.ziel_aus == "t"
    kurs.kursplan = None
    ohne = _sicht(kurs, zwei).test_vorschau(test)
    assert (ohne.kopf, ohne.zeilen, ohne.beispiel) == (
        ("Käfer: zwischen Anstrengung 5 und 7",),
        (),
        "",
    )


def test_marke_fuer_einen_weg_aus_dem_bild() -> None:
    """Ein Tipp auf eine Übung im Bild des Kursplans (`core/kursbild.py`) wird ein Weg dieses
    Kapitels: Die Marke geht so ins Blatt, wie es sie anbietet — die Grundlage, ein Baustein
    „Übung dazu“, bei einer der Gewählten ihr Baustein. Was erst ein späteres Kapitel bringt,
    kann ein Weg dieses Kapitels nicht nennen; `bringt` sagt, welches."""
    kurs = _kurs()
    eins, zwei = kurs.kapitel
    drei = Kapitel(
        id="k3", titel="Seitlich", bloecke=[Block(PLAN_UEBUNG, id="b5", uebung="Brücke")]
    )
    kurs.kapitel.append(drei)
    sicht = _sicht(kurs, zwei)
    assert sicht.marke_fuer_weg("g:1") == "g:1"
    assert sicht.marke_fuer_weg("b1") == "b1"  # ein früheres Kapitel
    assert sicht.marke_fuer_weg("b2") == "b2"  # dieses Kapitel: ein neuer Weg steht am Ende
    assert sicht.marke_fuer_weg("b2:Käfer") == "b2"  # eine der Gewählten: „die gewählte“
    assert sicht.marke_fuer_weg("b5") == sicht.marke_fuer_weg("b5:Brücke") == ""
    assert sicht.marke_fuer_weg("gibt-es-nicht") == ""
    # was das Blatt in „Von“ anbietet, ist genau das (`marken_davor`)
    assert sicht.marke_fuer_weg("b2:Käfer") in [m for m, _ in sicht.marken_davor("")]
    # ein vorhandener Baustein darf nur nennen, was vor ihm steht
    assert sicht.marke_fuer_weg("b2", "b2") == "" and sicht.marke_fuer_weg("b1", "b2") == "b1"
    # aus Sicht des ersten Kapitels kommt die gewählte erst später
    assert _sicht(kurs, eins).marke_fuer_weg("b2:Käfer") == ""
    assert _sicht(kurs, drei).marke_fuer_weg("b5") == "b5"

    nr, kapitel = sicht.bringt("b5")
    assert (nr, kapitel.id, kapitel.titel) == (3, "k3", "Seitlich")
    assert sicht.bringt("b2:Käfer")[0] == 2 and sicht.bringt("b1")[0] == 1
    assert sicht.bringt("g:1") is None and sicht.bringt("gibt-es-nicht") is None
    assert sicht.bringt("t") is None  # ein Test bringt keine Planübung
    assert sicht.marke_name("b5") == "Brücke" and sicht.marke_name("b2:Käfer") == "Käfer"
