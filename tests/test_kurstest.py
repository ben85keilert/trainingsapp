"""Der **gestaltete Test** eines Kurses (Ben, 16.11.2026: „Der Test muss flexibel gestaltet
werden können“) — die Regeln in `core/kurstest.py`: womit er läuft, welcher Takt mitläuft,
welche Vorgabe gilt, was zur Ausführung gehört und was im Eintrag steht. Ohne flet (erste
CI-Stufe); der Lauf selbst steht in ``test_ui_kurs_test.py``.
"""

from __future__ import annotations

from dataclasses import replace

from trainingsapp.core import kurstest
from trainingsapp.core.kursbloecke import (
    MENGE,
    SKALA,
    TEST,
    WIE_PARAMETER,
    WIE_TAKT,
    WIE_UHR,
    ZEIT,
    Block,
    Vorgabe,
)
from trainingsapp.core.models import Exercise
from trainingsapp.core.result_spec import FieldSpec, FieldType, ResultSpec, vorrat_feld
from trainingsapp.core.takt import VORLAGEN
from trainingsapp.core.timer import Abschnitt, TimerProfil
from trainingsapp.core.varianten import Variante, mit_varianten

KNIEBEUGE = VORLAGEN["kniebeuge_2_1_2"]  # eine Runde dauert 5 s, zählt beim Üben
INTERVALL = TimerProfil(
    id="intervall",
    name="Intervall",
    abschnitte=[Abschnitt("Los", 20), Abschnitt("Pause", 10, zaehlt=False)],
    runden=2,
)
HALTEN = TimerProfil(id="halten", name="Halten", abschnitte=[Abschnitt("Halten", 45)])


def _kaefer(**mehr) -> Exercise:
    spec = ResultSpec(fields=[vorrat_feld(k) for k in ("reps", "weight", "side")])
    spec = mit_varianten(spec, [Variante("auf Knien"), Variante("gestreckt")])
    return Exercise(name="Käfer", result_spec=spec, **mehr)


# -- Vorgaben ohne Angabe ----------------------------------------------------------------


def test_ohne_gestaltung_bleibt_der_test_wie_er_war() -> None:
    """Stoppuhr, kein Takt, keine Ausführung — auch wenn die Übung Timer, Takt und Parameter
    hat: Ohne „wie die Übung“ nimmt der Test nichts davon."""
    kaefer = _kaefer(timer=[HALTEN.als_dict()], takt=KNIEBEUGE, default_target={"weight": 10})
    test = Block(TEST, uebung="k", feld="reps", vorgabe=Vorgabe(SKALA, 7))
    assert not test.gestaltet and test.laeuft
    profil = kurstest.uhr_fuer(test, kaefer)
    assert profil.ist_stoppuhr
    assert kurstest.vorgabe_fuer(test, profil) == Vorgabe(SKALA, 7)
    assert kurstest.takt_fuer(test, kaefer) is None
    assert kurstest.ausfuehrung_fuer(test, kaefer).leer
    assert kurstest.lauf_satz(test, kaefer) == ""
    # die Texte ohne Timer sind die alten
    assert kurstest.anleitung(Vorgabe(SKALA, 7), timer=profil) == kurstest.anleitung(
        Vorgabe(SKALA, 7)
    )
    assert kurstest.knopf_text(Vorgabe(SKALA, 7), timer=profil) == "Bei 7 angekommen"
    assert kurstest.unten_text(Vorgabe(SKALA, 7), timer=profil) == "Ein Tipp hält die Uhr an."


def test_ein_test_ohne_vorgabe_laeuft_sobald_er_gestaltet_ist() -> None:
    assert not Block(TEST, uebung="k").laeuft
    for gestaltet in (
        Block(TEST, uebung="k", timer=INTERVALL.als_dict()),
        Block(TEST, uebung="k", takt=KNIEBEUGE),
        Block(TEST, uebung="k", ziel={"side": "links"}),
        Block(TEST, uebung="k", felder=["weight"]),
        Block(TEST, uebung="k", wie_uebung=[WIE_UHR]),
    ):
        assert gestaltet.laeuft and gestaltet.vorgabe is None


# -- Regel 2 und 3: womit er läuft, welche Vorgabe gilt ----------------------------------


def test_uhr_eigener_timer_dann_der_der_uebung_dann_die_stoppuhr() -> None:
    kaefer = _kaefer(timer=[HALTEN.als_dict()])
    eigen = Block(TEST, uebung="k", timer=INTERVALL.als_dict(), wie_uebung=[WIE_UHR])
    assert kurstest.uhr_fuer(eigen, kaefer).name == "Intervall"  # der eigene geht vor
    wie_uebung = Block(TEST, uebung="k", wie_uebung=[WIE_UHR])
    profil = kurstest.uhr_fuer(wie_uebung, kaefer)
    assert profil.name == "Halten" and profil.gesamt_s() == 45
    # eine eigene Kopie — der Lauf darf das Profil der Übung nicht anfassen
    profil.abschnitte[0].dauer_s = 1
    assert kurstest.uhr_fuer(wie_uebung, kaefer).gesamt_s() == 45
    # die Übung hat keinen Timer: die Stoppuhr
    assert kurstest.uhr_fuer(wie_uebung, _kaefer()).ist_stoppuhr
    assert kurstest.uhr_fuer(Block(TEST, uebung="k"), kaefer).ist_stoppuhr


def test_timer_und_vorgabe_zeit_zusammen_gibt_es_nicht() -> None:
    """Aus einem Paket kann die Kombination kommen: Dann ist der Timer die Zeit. Menge und
    Anstrengung gelten mit Timer weiter."""
    zeit = Block(TEST, uebung="k", vorgabe=Vorgabe(ZEIT, 60), timer=INTERVALL.als_dict())
    profil = kurstest.uhr_fuer(zeit)
    assert kurstest.vorgabe_fuer(zeit, profil) is None
    assert kurstest.kopf(zeit.vorgabe, profil) == ("Timer", "Intervall · 1:00")
    assert kurstest.knopf_text(zeit.vorgabe, timer=profil) == ""
    assert kurstest.gemessen(zeit.vorgabe, timer=profil) == ("wdh", "skala")
    menge = Block(TEST, uebung="k", vorgabe=Vorgabe(MENGE, 30), timer=INTERVALL.als_dict())
    assert kurstest.vorgabe_fuer(menge, profil) == Vorgabe(MENGE, 30)
    assert kurstest.knopf_text(menge.vorgabe, timer=profil) == "Fertig — 30 gemacht"
    # ohne Timer bleibt die Zeit die Vorgabe
    assert kurstest.vorgabe_fuer(
        Block(TEST, uebung="k", vorgabe=Vorgabe(ZEIT, 60)), kurstest.uhr_fuer(Block(TEST))
    ) == Vorgabe(ZEIT, 60)


def test_mit_timer_endet_der_test_wenn_der_timer_durch_ist() -> None:
    assert not kurstest.erreicht(None, wdh=None, gelaufen_s=59.0)
    assert kurstest.erreicht(None, wdh=None, gelaufen_s=60.0, durch=True)
    # die Vorgabe kann vorher beenden — und ist verfehlt, wenn der Timer eher durch war
    assert kurstest.erreicht(Vorgabe(MENGE, 30), wdh=30, gelaufen_s=12.0)
    assert kurstest.verfehlt(Vorgabe(MENGE, 30), vorher=False, durch=True, wdh=12, gelaufen_s=60)
    assert not kurstest.verfehlt(None, vorher=False, durch=True, wdh=None, gelaufen_s=60)
    assert kurstest.ende_text(Vorgabe(MENGE, 30), vorher=True, durch=True) == "Der Timer ist durch"


def test_zeit_des_tests_ist_was_in_zaehlenden_abschnitten_lief() -> None:
    assert kurstest.gezaehlte_zeit(INTERVALL, 60.0) == 40.0  # zweimal „Los“, die Pausen nicht
    assert kurstest.gezaehlte_zeit(INTERVALL, 25.0) == 20.0  # in der ersten Pause aufgehört
    assert kurstest.gezaehlte_zeit(INTERVALL, 42.5) == 32.5
    assert kurstest.woher_zeit(None, timer=INTERVALL) == kurstest.VOM_TIMER


# -- Regel 4: der Takt führt, er zählt nicht ---------------------------------------------


def test_takt_eigener_dann_der_der_uebung_dann_keiner() -> None:
    kniebeuge = _kaefer(takt=KNIEBEUGE)
    assert kurstest.takt_fuer(Block(TEST, uebung="k"), kniebeuge) is None
    assert kurstest.takt_fuer(Block(TEST, uebung="k", wie_uebung=[WIE_TAKT]), kniebeuge) == (
        KNIEBEUGE
    )
    eigen = Block(TEST, uebung="k", takt=VORLAGEN["metronom_1"], wie_uebung=[WIE_TAKT])
    assert kurstest.takt_fuer(eigen, kniebeuge) == VORLAGEN["metronom_1"]
    assert kurstest.takt_fuer(Block(TEST, uebung="k", wie_uebung=[WIE_TAKT]), _kaefer()) is None


def test_der_takt_beendet_nie_etwas_und_seine_runden_sind_ein_vorschlag() -> None:
    """„Ein Soll ist keine Messung“: Auch 30 Runden des Takts beenden eine Vorgabe Menge
    nicht — gezählt hat nur der Sensor. Im Ergebnis stehen die Runden als Vorschlag."""
    kaefer = kurstest.Felder("reps", "duration", "scale")
    runden = kurstest.takt_runden(kurstest.uhr_fuer(Block(TEST)), KNIEBEUGE, 152.0)
    assert runden == 30
    assert not kurstest.erreicht(Vorgabe(MENGE, 30), wdh=None, gelaufen_s=152.0)
    # Vorgabe Anstrengung, niemand zählte: die Runden vorbelegt, aber als Frage
    assert kurstest.am_ende(Vorgabe(SKALA, 7), kaefer, gelaufen_s=152.0, takt_runden=runden) == (
        30,
        152.0,
        7,
    )
    assert kurstest.woher_wdh(Vorgabe(SKALA, 7), kaefer, takt=True) == kurstest.VOM_TAKT
    assert kurstest.takt_frage(30) == "Der Takt lief 30 Runden. Stimmt die Zahl?"
    # zählt der Sensor, gilt er wie bisher
    assert kurstest.am_ende(
        Vorgabe(SKALA, 7), kaefer, gelaufen_s=152.0, gezaehlt=27, takt_runden=runden
    ) == (27, 152.0, 7)
    assert kurstest.woher_wdh(Vorgabe(SKALA, 7), kaefer, gezaehlt=True, takt=True) == (
        kurstest.GEZAEHLT
    )
    # eine erreichte Menge ist die Vorgabe, kein Vorschlag
    assert kurstest.woher_wdh(Vorgabe(MENGE, 30), kaefer, takt=True) == kurstest.VORGEGEBEN
    # keine volle Runde: kein Vorschlag, es wird gefragt wie ohne Takt
    assert kurstest.am_ende(None, kaefer, gelaufen_s=3.0, takt_runden=0)[0] is None
    # eine Übung ohne Wiederholungen bekommt keine
    assert kurstest.am_ende(
        None, kurstest.Felder(None, "hold", "scale"), gelaufen_s=60.0, takt_runden=12
    ) == (None, 60.0, None)


def test_takt_runden_aus_der_uhr_je_zaehlendem_abschnitt() -> None:
    # zweimal 20 s „Los“ = je 4 Runden; in den Pausen läuft er, zählt aber nicht mit
    assert kurstest.takt_runden(INTERVALL, KNIEBEUGE, 60.0) == 8
    assert kurstest.takt_runden(INTERVALL, KNIEBEUGE, 34.9) == 4  # die angefangene zählt nicht
    assert kurstest.takt_runden(INTERVALL, KNIEBEUGE, 35.0) == 5
    assert kurstest.takt_runden(INTERVALL, None, 60.0) == 0
    # ein Abschnitt mit eigenem Takt behält ihn (Abschnitt > Test)
    eigen = replace(
        INTERVALL, abschnitte=[Abschnitt("Los", 20, takt=VORLAGEN["metronom_1"])], runden=1
    )
    assert kurstest.takt_runden(eigen, KNIEBEUGE, 20.0) == 20
    # ein Takt mit Rundenzahl hört auf
    assert kurstest.takt_runden(HALTEN, replace(KNIEBEUGE, runden=3), 45.0) == 3


# -- Regel 5: die Ausführung --------------------------------------------------------------


def test_ausfuehrung_ist_was_der_lauf_nicht_misst_nach_der_art() -> None:
    """Nach `basis_key`, nie nach dem Schlüssel: ``hold_2`` und ``scale_3`` sind gemessen,
    ``weight_2`` ist Ausführung."""
    ja = ["side", "angle", "weight", "weight_2", "distance"]
    nein = ["reps", "reps_2", "hold", "hold_2", "duration", "scale", "scale_3", "note", "done"]
    assert all(kurstest.ist_ausfuehrung(vorrat_feld(k)) for k in ja)
    assert not any(kurstest.ist_ausfuehrung(vorrat_feld(k)) for k in nein)
    # ein Zeitfeld unter fremdem Schlüssel (Vorlage „Zeit als Benchmark“) ist keine
    assert not kurstest.ist_ausfuehrung(FieldSpec("seconds", FieldType.DURATION, "Zeit"))
    spec = ResultSpec(fields=[vorrat_feld(k) for k in (*nein, *ja)])
    uebung = Exercise(result_spec=mit_varianten(spec, [Variante("kurz")]))
    assert [f.key for f in kurstest.ausfuehrungsfelder(uebung)] == [
        "variant",
        "side",
        "angle",
        "weight",
        "weight_2",
        "distance",
    ]


def test_ausfuehrung_vorgegeben_frei_und_vorbelegt() -> None:
    kaefer = _kaefer(default_target={"weight": 10, "variant": "gestreckt", "reps": [12]})
    test = Block(
        TEST,
        uebung="k",
        ziel={"side": "links", "reps": [15]},  # Wiederholungen sind keine Ausführung
        felder=["weight", "variant"],
    )
    aus = kurstest.ausfuehrung_fuer(test, kaefer)
    assert [(f.key, w) for f, w in aus.fest] == [("side", "links")]
    assert [f.key for f in aus.frei] == ["variant", "weight"]  # die Variante zuerst
    assert dict(aus.vorbelegt) == {"variant": "gestreckt", "weight": 10}
    assert aus.werte() == {"side": "links", "variant": "gestreckt", "weight": 10}
    assert aus.text() == "gestreckt · links · 10 kg"
    # die Wahl der Person gilt — auch „nichts“
    assert aus.werte({"variant": "auf Knien"}) == {"side": "links", "variant": "auf Knien"}
    assert aus.text({"weight": 12.5}) == "links · 12.5 kg"


def test_wie_die_uebung_macht_alles_frei_was_nicht_vorgegeben_ist() -> None:
    kaefer = _kaefer()
    alle = kurstest.ausfuehrung_fuer(Block(TEST, uebung="k", wie_uebung=[WIE_PARAMETER]), kaefer)
    assert not alle.fest and [f.key for f in alle.frei] == ["variant", "side", "weight"]
    assert dict(alle.vorbelegt) == {}  # die Übung hat keinen Standard: nichts gewählt
    teils = kurstest.ausfuehrung_fuer(
        Block(TEST, uebung="k", ziel={"weight": 5}, felder=["weight"], wie_uebung=[WIE_PARAMETER]),
        kaefer,
    )
    assert [(f.key, w) for f, w in teils.fest] == [("weight", 5)]  # vorgegeben geht vor
    assert [f.key for f in teils.frei] == ["variant", "side"]


def test_ein_feld_das_die_uebung_nicht_anbietet_kommt_aus_dem_vorrat() -> None:
    planke = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    test = Block(
        TEST,
        uebung="p",
        ziel={"angle": 90, "variant": "auf Knien", "tanz": 3, "hold": [60]},
        felder=["side", "variant", "note"],
    )
    aus = kurstest.ausfuehrung_fuer(test, planke)
    assert [(f.label, w) for f, w in aus.fest] == [("Winkel", 90), ("Variante", "auf Knien")]
    # frei: die Seite aus dem Vorrat; ohne Varianten der Übung gibt es keine zu wählen,
    # Freitext ist keine Ausführung
    assert [(f.key, f.quick) for f in aus.frei] == [("side", ["links", "rechts", "beide"])]
    assert aus.text({"side": "beide"}) == "auf Knien · 90° · beide"
    assert [f.key for f in planke.result_spec.fields] == ["hold"]  # die Übung bleibt


def test_eintrag_haelt_die_ausfuehrung_in_seiner_kopie_der_felder() -> None:
    planke = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    test = Block(TEST, uebung="p", feld="hold", ziel={"angle": 90}, felder=["side"])
    wie = kurstest.ausfuehrung_fuer(test, planke).werte({"side": "links"})
    mit, werte = kurstest.eintrag(test, planke, wdh=None, sekunden=48.2, skala=6, ausfuehrung=wie)
    assert werte == {"hold": [48], "scale": 6, "angle": 90, "side": "links"}
    assert [f.key for f in mit.result_spec.fields] == ["hold", "scale", "angle", "side"]
    assert [f.key for f in planke.result_spec.fields] == ["hold"]
    assert kurstest.ausfuehrung_aus(werte, mit.result_spec) == "links · 90°"
    assert not kurstest.fehlt(test, planke, wdh=None, sekunden=48.2, skala=6)
    # ohne Ausführung der Eintrag wie bisher
    assert kurstest.eintrag(test, planke, wdh=None, sekunden=48.2, skala=6)[1] == {
        "hold": [48],
        "scale": 6,
    }


# -- Texte ---------------------------------------------------------------------------------


def test_satz_der_testkarte_sagt_wie_der_test_laeuft() -> None:
    kaefer = _kaefer(takt=KNIEBEUGE, timer=[HALTEN.als_dict()])
    test = Block(
        TEST,
        uebung="k",
        timer=INTERVALL.als_dict(),
        wie_uebung=[WIE_TAKT],
        ziel={"side": "links"},
        felder=["weight", "variant"],
    )
    assert kurstest.lauf_satz(test, kaefer) == (
        "Läuft mit dem Timer „Intervall“ (1:00) und im Takt Kniebeuge 2-1-2. "
        "Ausführung: links. Variante und Gewicht wählst du vor dem Start."
    )
    nur_takt = Block(TEST, uebung="k", takt=VORLAGEN["metronom_1"])
    assert kurstest.lauf_satz(nur_takt, kaefer) == "Läuft im Takt Metronom 1 s."
    # ohne Übung (Test „der gewählten“ vor der Wahl): was erst die Übung sagt, allgemein
    offen = Block(TEST, aus="wahl", wie_uebung=[WIE_UHR, WIE_TAKT, WIE_PARAMETER])
    assert kurstest.lauf_satz(offen) == (
        "Läuft mit dem Timer der Übung und in ihrem Takt. Die Ausführung wählst du vor dem Start."
    )
    assert kurstest.lauf_satz(offen, kaefer).startswith(
        "Läuft mit dem Timer „Halten“ (0:45) und im Takt Kniebeuge 2-1-2."
    )


def test_texte_ohne_vorgabe() -> None:
    stoppuhr = kurstest.uhr_fuer(Block(TEST))
    assert kurstest.kopf(None, stoppuhr) == ("Test", "Was schaffst du?")
    assert kurstest.knopf_text(None, timer=stoppuhr) == "Fertig"
    assert not kurstest.vorher_knopf(None, timer=stoppuhr)
    assert kurstest.vorher_knopf(None, timer=INTERVALL)
    assert kurstest.zeit_zeile(None, timer=INTERVALL) == "Timer läuft · endet von selbst"
    assert kurstest.anleitung(None, timer=INTERVALL) == (
        "Der Timer läuft 1 Minute. Danach sagst du, wie viele es waren und wie anstrengend es war."
    )
    assert kurstest.unten_text(None, takt=True) == (
        "Ein Tipp hält Uhr und Takt an. Danach sagst du, wie viele es waren."
    )
    assert kurstest.ende_text(None) == "Fertig"
    assert kurstest.timer_text(INTERVALL) == "Intervall · 1:00"
    assert kurstest.takt_text(KNIEBEUGE) == "12,0/min · 2 s ab, 1 s halten, 2 s auf"


def test_block_aus_dem_paket_ergibt_denselben_lauf() -> None:
    """Was `Block.to_dict` schreibt, läuft nach dem Lesen genauso."""
    test = Block(
        TEST,
        id="t",
        uebung="k",
        feld="reps",
        vorgabe=Vorgabe(SKALA, 7),
        timer=INTERVALL.als_dict(),
        takt=KNIEBEUGE,
        ziel={"side": "links"},
        felder=["weight"],
        wie_uebung=[WIE_PARAMETER],
        text="Mach dich vorher 5 Minuten warm.",
    )
    gelesen = Block.from_dict(test.to_dict())
    assert gelesen is not None and gelesen.laeuft and gelesen.text == test.text
    kaefer = _kaefer()
    assert kurstest.uhr_fuer(gelesen, kaefer) == kurstest.uhr_fuer(test, kaefer)
    assert kurstest.takt_fuer(gelesen, kaefer) == KNIEBEUGE
    a, b = kurstest.ausfuehrung_fuer(gelesen, kaefer), kurstest.ausfuehrung_fuer(test, kaefer)
    assert a.werte() == b.werte() == {"side": "links"}
    assert [f.key for f in a.frei] == ["variant", "weight"]


def test_ein_timer_ohne_eigenen_namen_wird_nicht_beim_namen_genannt() -> None:
    """Im Kurs-Editor heißt ein Timer ohne eigenen Namen „Timer“ — das nennt kein Text: Dann
    steht nur seine Zeit da (wie im Zusatz des Editors)."""
    ohne = replace(INTERVALL, name="Timer")
    assert kurstest.timer_name(INTERVALL) == "Intervall" and kurstest.timer_name(ohne) == ""
    assert kurstest.timer_text(ohne) == "1:00"
    assert kurstest.kopf(None, ohne) == ("Timer", "1:00")
    test = Block(TEST, uebung="k", timer=ohne.als_dict(), takt=KNIEBEUGE)
    assert kurstest.lauf_satz(test, _kaefer()) == (
        "Läuft mit einem Timer (1:00) und im Takt Kniebeuge 2-1-2."
    )


def test_ueberschrift_der_testkarte_nennt_die_vorgabe_die_im_lauf_gilt() -> None:
    """Eine Stelle für die Karte im Kapitel und die Vorschau im Editor: mit der Vorgabe, die
    gilt — sonst die Frage."""
    mit = Block(TEST, uebung="k", vorgabe=Vorgabe(SKALA, 5, 7))
    assert kurstest.karten_ueberschrift(mit, "Käfer") == "Käfer: zwischen Anstrengung 5 und 7"
    assert kurstest.karten_ueberschrift(mit, "Käfer", skala="Schwere") == (
        "Käfer: zwischen Schwere 5 und 7"
    )
    ohne = Block(TEST, uebung="k", takt=KNIEBEUGE)
    assert kurstest.karten_ueberschrift(ohne, "Deine Auswahl") == (
        f"Deine Auswahl: {kurstest.OHNE_VORGABE}"
    )
    # eine Zeit neben einem Timer gilt nicht — auch wenn der Timer erst von der Übung kommt
    zeit = Block(TEST, uebung="k", vorgabe=Vorgabe(ZEIT, 60), wie_uebung=[WIE_UHR])
    assert kurstest.karten_ueberschrift(zeit, "Käfer", _kaefer()) == "Käfer: 1 Minute"
    assert kurstest.karten_ueberschrift(zeit, "Käfer", _kaefer(timer=[HALTEN.als_dict()])) == (
        "Käfer: was schaffst du?"
    )


def test_nur_tests_die_gebraucht_werden_sind_pflicht() -> None:
    """„Plan anlegen“ wartet nur auf Tests, aus deren Wert ein Ziel wird — ein Lauf zum
    Ausprobieren hält nichts auf (Ben, 23.11.2026, `docs/plan_kurs_uebungen.md` §10.1)."""
    from trainingsapp.core.kursbloecke import PLAN_UEBUNG, TEST, Block, abnehmer, fertig

    test = Block(TEST, id="t", uebung="planke")
    probe = Block(TEST, id="e", uebung="seitstuetz")
    baustein = Block(PLAN_UEBUNG, id="b", uebung="planke", ziel_aus="t")
    alle = [test, probe, baustein]
    assert [b.id for b in abnehmer(test, alle)] == ["b"] and abnehmer(probe, alle) == []
    assert not fertig(alle, {}, {}, ziel_tests={"t"})
    assert fertig(alle, {"t": 60.0}, {}, ziel_tests={"t"})
    assert not fertig(alle, {"t": 60.0}, {})  # ohne Angabe: jeder Test, wie bisher
