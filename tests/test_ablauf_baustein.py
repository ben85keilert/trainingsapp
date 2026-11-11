"""Gezeichneter Ablauf (Ben, 8.11.2026 spät, `docs/plan_verzweigungen.md` §8, G1/G2): der
Baustein folgt Kanten — Start, reguläre Kante, Einschub mit „◀ zurück“, Schleife, Pflicht,
Skala-Kante mit „ausführen“, Frage als Entscheidungsknoten, Ende über eine Kante."""

from __future__ import annotations

import pytest

from trainingsapp.core import ablauf as ab
from trainingsapp.core.ablauf import Ablauf, Frage, Kante
from trainingsapp.core.plan_durchlauf import Schritt
from trainingsapp.core.timer import Abschnitt, TimerProfil
from trainingsapp.devices.plan_ablauf import (
    FERTIG,
    HART,
    UEBERZEIT,
    UEBUNG,
    WEICH,
    PlanAblaufBaustein,
)


def _profil(sekunden: float) -> TimerProfil:
    return TimerProfil(id="p", name="Halten", abschnitte=[Abschnitt("Halten", sekunden)])


def _schritte(frage: Frage | None = None) -> list[Schritt]:
    s = [
        Schritt("w", "u1", "Wandsitz", _profil(10), "hold"),
        Schritt("k", "u2", "Kniebeuge", None, None),
        Schritt("p", "u3", "Planke", _profil(10), "hold"),
        Schritt("d", "u4", "Dehnung Beine", None, None),
    ]
    if frage is not None:
        s.append(Schritt(frage.id, "", frage.text, frage=frage))
    return s


def _baustein(ablauf: Ablauf, uebergang: str = HART, frage: Frage | None = None):
    uhr = [0.0]
    teil = PlanAblaufBaustein(
        "p1", "Rumpf", _schritte(frage), uebergang=uebergang, workout=True, ablauf=ablauf
    )
    teil.uhr_uebernehmen(lambda: uhr[0])
    teil.starten(0.0)
    return teil, uhr


def _lauf(teil, uhr, sekunden: float) -> list:
    out = []
    for _ in range(int(sekunden)):
        uhr[0] += 1
        out += teil.takt(uhr[0])
    return out


def _paare(ereignisse) -> list[tuple[str, str]]:
    return [(e.quelle, e.art) for e in ereignisse]


def test_kette_folgt_den_kanten_und_endet_ohne_kante() -> None:
    a = ab.kette(["w", "k", "p"])
    teil, uhr = _baustein(a)
    assert teil.schritt.item_id == "w" and teil.durchlauf == 1
    _lauf(teil, uhr, 10)
    assert teil.schritt.item_id == "k" and teil.phase == UEBUNG  # hart: sofort weiter
    # Ohne Timer läuft im Workout eine Stoppuhr (Fokus mit Kurven) — „Fertig“ beendet sie
    assert teil.timer is not None and teil.timer.lauf.profil.ist_stoppuhr
    teil.gemacht()
    teil.takt(uhr[0])
    assert teil.schritt.item_id == "p" and teil.ergebnisse["k"] == "gemacht"
    _lauf(teil, uhr, 10)
    assert teil.phase == FERTIG  # Planke hat keine Kante → Ende
    assert ab.bedarf(a, ["w", "k", "p", "d"]) == ["d"]


def test_einschub_mit_zurueck_geht_zur_naechsten_des_ursprungs() -> None:
    a = Ablauf(
        True,
        "w",
        (
            Kante("w", "k"),
            Kante("w", "d", ab.SKALA, 7, text="Beine krampfen"),
            Kante("d", ab.ZURUECK),
            Kante("k", "p"),
        ),
    )
    teil, uhr = _baustein(a, WEICH)
    _lauf(teil, uhr, 10)
    assert teil.phase == UEBERZEIT
    staende = teil.kanten_stand()
    assert [s.kante.nach for s in staende] == ["k", "d"]
    assert staende[0].gangbar and not staende[1].erfuellt and staende[1].unpruefbar
    teil.antworten(7)
    staende = teil.kanten_stand()
    assert staende[1].angeboten and teil.naechster == 3  # die Dehnung ist jetzt die reguläre
    ereignisse = []
    teil.kante_gehen(staende[1].kante)
    ereignisse += teil.takt(uhr[0])
    assert teil.schritt.item_id == "d"
    kante = next(e for e in ereignisse if (e.quelle, e.art) == ("plan", "kante"))
    assert kante.daten["von"] == "w" and kante.daten["nach"] == "d"
    assert kante.daten["kante"] == "Beine krampfen"
    # ◀ zurück: nicht zum Wandsitz, sondern zu dessen nächster Kante — der Kniebeuge
    zurueck = teil.kanten_stand()[0]
    assert zurueck.kante.zurueck and teil.kante_ziel(zurueck.kante) == 1
    teil.kante_gehen(zurueck.kante)
    assert teil.schritt.item_id == "k" and teil.verlauf == [0, 3, 1]


def test_zurueck_mit_wiederholen_laesst_die_unterbrochene_noch_einmal_laufen() -> None:
    a = Ablauf(
        True, "w", (Kante("w", "k"), Kante("w", "d"), Kante("d", ab.ZURUECK, wiederholen=True))
    )
    teil, _uhr = _baustein(a)
    teil.kante_gehen(teil.kanten_stand()[1].kante)
    assert teil.schritt.item_id == "d"
    teil.kante_gehen(teil.kanten_stand()[0].kante)
    assert teil.schritt.item_id == "w" and teil.durchlauf == 2


def test_schleife_bis_skala_und_pflicht_sperrt_die_anderen() -> None:
    a = Ablauf(
        True,
        "p",
        (
            Kante("p", "k", ab.SKALA, 6, pflicht=True),
            Kante("p", "p", text="noch einmal"),
        ),
    )
    teil, uhr = _baustein(a, WEICH)
    _lauf(teil, uhr, 10)
    # Weich, Zeit ab: Überzeit — die Pflicht sperrt den anderen Weg, bis die Skala reicht
    assert teil.phase == UEBERZEIT
    staende = teil.kanten_stand()
    assert not staende[0].gangbar and staende[1].gesperrt
    assert not staende[1].waehlbar(weich=True)  # auch weich nie gegen eine Pflicht
    teil.antworten(4)
    staende = teil.kanten_stand()
    assert not staende[0].erfuellt and staende[1].gesperrt
    teil.antworten(6)
    staende = teil.kanten_stand()
    assert staende[0].gangbar and staende[1].gangbar
    teil.kante_gehen(staende[1].kante)
    assert teil.schritt.item_id == "p" and teil.durchlauf == 2 and teil.skala_wert is None


def test_hart_bleibt_bei_der_uebung_bis_ein_weg_frei_ist() -> None:
    """Ben, 8.11.2026: keine Pause mehr — ist die Zeit ab und kein Weg frei, bleibt die Person bei
    der Übung (der Timer zählt über); hart geht es von selbst weiter, sobald es reicht."""
    a = Ablauf(True, "p", (Kante("p", "k", ab.SKALA, 6, pflicht=True), Kante("p", "p")))
    teil, uhr = _baustein(a, HART)
    _lauf(teil, uhr, 10)
    assert teil.phase == UEBERZEIT and teil.wartet and teil.schritt.item_id == "p"
    assert "p" not in teil.ergebnisse  # noch nichts eingetragen — man kann noch eintragen
    teil.antworten(4)
    assert teil.wartet and teil.schritt.item_id == "p"
    teil.antworten(7)
    assert teil.schritt.item_id == "k" and not teil.wartet and teil.ergebnisse["p"] == "fertig"


def test_ausfuehren_geht_von_selbst_sobald_der_timer_ab_ist() -> None:
    a = Ablauf(True, "w", (Kante("w", "k"), Kante("w", "d", ab.SKALA, 7, ausfuehren=True)))
    teil, uhr = _baustein(a, WEICH)
    _lauf(teil, uhr, 3)
    teil.antworten(8)  # der Timer läuft noch: nichts passiert (weich schubst nicht)
    assert teil.schritt.item_id == "w"
    _lauf(teil, uhr, 8)
    assert teil.schritt.item_id == "d"  # Zeit ab → die erfüllte Kante geht von selbst


def test_frage_verzweigt_nach_dem_wert_und_ende_ueber_kante() -> None:
    frage = Frage("f", "Wie fühlt es sich an?")
    a = Ablauf(
        True,
        "w",
        (
            Kante("w", "f", ab.ZEIT),
            Kante("f", "k", ab.SKALA, 0, 6),
            Kante("f", "d", ab.SKALA, 7),
            Kante("d", ab.ENDE),
        ),
        (frage,),
    )
    teil, uhr = _baustein(a, frage=frage)
    ereignisse = _lauf(teil, uhr, 10)
    assert teil.schritt.frage is frage and ("plan", "frage") in _paare(ereignisse)
    assert teil.status() == "4 Übungen · 2 mit Timer"
    teil.antworten(8)
    ereignisse = teil.takt(uhr[0])
    antwort = next(e for e in ereignisse if (e.quelle, e.art) == ("plan", "antwort"))
    assert antwort.daten["wert"] == 8 and ("plan", "uebung_ende") not in _paare(ereignisse)
    assert teil.schritt.item_id == "d"
    ende = teil.kanten_stand()[0]
    assert ende.kante.zum_ende
    teil.kante_gehen(ende.kante)
    ereignisse = teil.takt(uhr[0])
    assert teil.phase == FERTIG and ("plan", "ende") in _paare(ereignisse)


def test_ohne_an_bleibt_die_planfolge() -> None:
    a = Ablauf(False, "p", (Kante("p", "w"),))
    teil, _uhr = _baustein(a)
    assert teil.ablauf is None and teil.schritt.item_id == "w"


def test_hart_fuehrt_eine_erfuellte_kante_sofort_aus_auch_mitten_im_timer() -> None:
    a = Ablauf(True, "w", (Kante("w", "k"), Kante("w", "d", ab.SKALA, 7, ausfuehren=True)))
    teil, uhr = _baustein(a, HART)
    _lauf(teil, uhr, 3)
    teil.antworten(8)
    assert teil.schritt.item_id == "d" and teil.ergebnisse["w"] == "fertig"


def test_ausgelassene_knoten_werden_durchlaufen() -> None:
    """Heute schon gemacht (abgewählt) oder im Papierkorb: der Knoten fehlt unter den
    Schritten — Start und Kanten gehen durch ihn hindurch, statt das Workout zu beenden."""
    a = Ablauf(True, "x", (Kante("x", "w"), Kante("w", "y"), Kante("y", "p")))
    teil, uhr = _baustein(a)  # „x“ und „y“ gibt es nicht unter den Schritten
    assert teil.schritt.item_id == "w" and not teil.hat("x") and teil.hat("w")
    assert teil.kante_ziel(teil.kanten_stand()[0].kante) == 2  # durch „y“ zur Planke
    _lauf(teil, uhr, 10)
    assert teil.schritt.item_id == "p" and teil.phase == UEBUNG


def test_schleife_zaehlt_die_durchlaeufe_im_verlauf() -> None:
    a = Ablauf(True, "w", (Kante("w", "w", text="noch einmal"), Kante("w", "k")))
    teil, uhr = _baustein(a)
    _lauf(teil, uhr, 10)  # zwei freie Wege: auch hart wird erst gefragt (Ben, 9.11.2026)
    assert teil.wartet and teil.wahl_noetig and teil.schritt.item_id == "w"
    teil.kante_gehen(teil.kanten_stand()[0].kante)  # „noch einmal“
    _lauf(teil, uhr, 10)
    teil.kante_gehen(teil.kanten_stand()[0].kante)
    assert teil.schritt.item_id == "w" and teil.durchlauf == 3 and teil.verlauf == [0, 0, 0]
    teil.kante_gehen(teil.kanten_stand()[1].kante)
    assert teil.schritt.item_id == "k"


def test_mehrere_freie_wege_hart_wartet_auf_die_wahl() -> None:
    """Ben, 9.11.2026: „Egal ob hart oder weich, wenn es mehrere Pfade gibt, wird erst
    abgefragt, bevor es weiter geht“ — die Zeit ist ab, nichts geht von selbst."""
    a = Ablauf(True, "w", (Kante("w", "k"), Kante("w", "p")))
    teil, uhr = _baustein(a, HART)
    assert teil.wahl_noetig
    _lauf(teil, uhr, 15)
    assert teil.schritt.item_id == "w" and teil.wartet and "w" not in teil.ergebnisse
    teil.kante_gehen(teil.kanten_stand()[1].kante)
    assert teil.schritt.item_id == "p" and teil.ergebnisse["w"] == "fertig"
    assert not teil.wahl_noetig  # die Planke hat keinen Weg mehr — sie endet das Workout


def test_mehrere_freie_wege_weich_fertig_fragt() -> None:
    """„Wenn man auf Fertig klickt, geht der Hauptpfad weiter“ — nicht mehr: Fertig wartet auf
    die Wahl, auch ohne Timer (Stoppuhr)."""
    a = Ablauf(True, "k", (Kante("k", "w"), Kante("k", "p")))
    teil, uhr = _baustein(a, WEICH)
    assert teil.schritt.item_id == "k"
    teil.gemacht()
    _lauf(teil, uhr, 1)
    assert teil.schritt.item_id == "k" and teil.wartet
    teil.weiter()  # „Weiter“ ohne Ziel nimmt nicht still den Hauptweg
    assert teil.schritt.item_id == "k" and teil.wartet
    teil.kante_gehen(teil.kanten_stand()[1].kante)
    assert teil.schritt.item_id == "p"


def test_ein_angebotener_weg_entscheidet_von_selbst() -> None:
    """Ist genau ein Weg angeboten (sein Auslöser ist erfüllt), braucht es keine Wahl."""
    a = Ablauf(True, "w", (Kante("w", "k"), Kante("w", "p", ab.ZEIT)))
    teil, uhr = _baustein(a, HART)
    _lauf(teil, uhr, 10)
    assert teil.schritt.item_id == "p" and not teil.wartet


def test_zwei_angebotene_wege_von_selbst_gehen_nicht_von_selbst() -> None:
    """Zwei Wege „von selbst“, beide erfüllt: keiner geht — die Person wählt."""
    a = Ablauf(
        True,
        "w",
        (Kante("w", "k", ab.ZEIT, ausfuehren=True), Kante("w", "p", ab.ZEIT, ausfuehren=True)),
    )
    teil, uhr = _baustein(a, HART)
    _lauf(teil, uhr, 12)
    assert teil.schritt.item_id == "w" and teil.wartet and teil.wahl_noetig


def test_ueberspringen_ueber_den_gewaehlten_weg() -> None:
    a = Ablauf(True, "w", (Kante("w", "k"), Kante("w", "p")))
    teil, uhr = _baustein(a, HART)
    _lauf(teil, uhr, 3)
    teil.ueberspringen(teil.kanten_stand()[1].kante)
    assert teil.schritt.item_id == "p" and teil.ergebnisse["w"] == "uebersprungen"


# -- Durcharbeiten (Ben, 9.11.2026, P166/P167) -------------------------------------------------


def test_regulaere_kante_steht_in_der_zeitleiste() -> None:
    """Auch die Kante, die von selbst geht, steht als ``plan/kante`` da — daraus liest die Liste,
    welche Tore offen sind."""
    a = ab.kette(["w", "k"])
    teil, uhr = _baustein(a)
    out = _lauf(teil, uhr, 10)
    kanten = [e for e in out if (e.quelle, e.art) == ("plan", "kante")]
    assert [(e.daten["von"], e.daten["nach"]) for e in kanten] == [("w", "k")]
    assert "pflicht_offen" not in kanten[0].daten


def test_ueberspringen_einer_pflicht_oeffnet_kein_tor() -> None:
    a = Ablauf(True, "w", (Kante("w", "k", ab.WDH, 12, pflicht=True),))
    teil, uhr = _baustein(a)
    out = _lauf(teil, uhr, 3)
    teil.ueberspringen()
    out += teil.takt(uhr[0])
    (kante,) = [e for e in out if (e.quelle, e.art) == ("plan", "kante")]
    assert kante.daten["pflicht_offen"] is True and teil.schritt.item_id == "k"
    # Erfüllt die Pflicht (12 Wdh.), steht kein „pflicht_offen“ an der Kante
    teil2, uhr2 = _baustein(a)
    teil2.wdh_setzen(12)
    out2 = _lauf(teil2, uhr2, 10)
    (kante2,) = [e for e in out2 if (e.quelle, e.art) == ("plan", "kante")]
    assert "pflicht_offen" not in kante2.daten


def test_vorzeitiges_ende_merkt_die_stelle_und_fortsetzen_kennt_zurueck() -> None:
    """⏹ mitten in der Dehnung (Einschub): ``plan/ende`` sagt ``bei`` = Dehnung, ``vorher`` =
    Wandsitz; fortgesetzt führt „◀ zurück“ zur Kniebeuge, der nächsten des Wandsitzes."""
    a = Ablauf(
        True,
        "w",
        (Kante("w", "k"), Kante("w", "d", text="krampft"), Kante("d", ab.ZURUECK), Kante("k", "p")),
    )
    teil, uhr = _baustein(a)
    out = _lauf(teil, uhr, 10)  # zwei freie Wege: es wird gefragt
    teil.kante_gehen(teil.kanten_stand()[1].kante)  # „krampft“
    out += _lauf(teil, uhr, 2)
    assert teil.schritt.item_id == "d"
    out += teil.beenden(uhr[0])
    (ende,) = [e for e in out if (e.quelle, e.art) == ("plan", "ende")]
    assert (ende.daten["bei"], ende.daten["vorher"]) == ("d", "w")
    assert ab.fortsetzung(out, "p1") == ab.Fortsetzung("d", "w")

    uhr2 = [0.0]
    weiter = PlanAblaufBaustein(
        "p1", "Rumpf", _schritte(), uebergang=HART, workout=True, ablauf=a, erste="d", vorher="w"
    )
    weiter.uhr_uebernehmen(lambda: uhr2[0])
    weiter.starten(0.0)
    assert weiter.schritt.item_id == "d" and weiter.durchlauf == 1
    weiter.gemacht()  # Dehnung ohne Timer: „Fertig“ → ◀ zurück → die nächste des Wandsitzes
    weiter.takt(uhr2[0])
    assert weiter.schritt.item_id == "k"


def test_ende_nach_fertiger_uebung_setzt_mit_der_naechsten_fort() -> None:
    """Weich in der Überzeit: die Übung war fertig (sie wird eingetragen) — fortgesetzt wird mit
    der nächsten; bis zum Ende durchgelaufen gibt es keine Stelle."""
    a = ab.kette(["w", "k"])
    teil, uhr = _baustein(a, WEICH)
    out = _lauf(teil, uhr, 11)
    assert teil.phase == UEBERZEIT
    out += teil.beenden(uhr[0])
    assert ab.fortsetzung(out, "p1") == ab.Fortsetzung("k", "w")
    durch, uhr3 = _baustein(ab.kette(["w"]))
    alles = _lauf(durch, uhr3, 10)
    assert durch.phase == FERTIG and ab.fortsetzung(alles, "p1") is None


@pytest.mark.parametrize("hart", [True, False])
@pytest.mark.parametrize("tipps", [1, 2])
def test_zweimal_fertig_verliert_den_letzten_satz_nicht(hart, tipps) -> None:
    """N59: Zwei Tipps auf „Fertig“ innerhalb eines Takts — das Timer-Ende wird trotzdem
    abgeholt, der angefangene dritte Satz (12 s) steht im Eintrag."""
    from trainingsapp.core.plan_durchlauf import Schritt
    from trainingsapp.core.timer import Abschnitt, TimerProfil
    from trainingsapp.core.timer_eintrag import ergebnis, gelaufene_zeiten
    from trainingsapp.devices.einheit import Einheitslauf
    from trainingsapp.devices.plan_ablauf import HART, WEICH, PlanAblaufBaustein

    t = [0.0]
    profil = TimerProfil(
        id="t",
        name="H",
        runden=3,
        abschnitte=[Abschnitt("Halten", 30), Abschnitt("Pause", 10, zaehlt=False)],
    )
    schritte = [
        Schritt("i1", "u1", "Planke", profil, "hold"),
        Schritt("i2", "u2", "Brücke", profil, "hold"),
    ]
    teil = PlanAblaufBaustein(
        "p", "Test", schritte, uebergang=HART if hart else WEICH, workout=True
    )
    e = Einheitslauf(uhr=lambda: t[0])
    e.hinzufuegen(teil)
    e.starten(0.0)
    for _ in range(4 * 92):  # zwei Sätze mit Pausen, 12 s im dritten
        t[0] += 0.25
        e.takt()
    for _ in range(tipps):
        teil.gemacht()
        t[0] += 0.05
    for _ in range(8):
        t[0] += 0.25
        e.takt()
    ev = e.ereignisse
    a = next(n for n, x in enumerate(ev) if x.art == "uebung_start")
    b = next(n for n, x in enumerate(ev) if x.art == "uebung_ende")
    assert ergebnis(gelaufene_zeiten(ev[a : b + 1]), "hold") == {"hold": [30, 30, 12]}
    assert teil.k == 1  # der zweite Tipp hat den nächsten Schritt nicht auch beendet
