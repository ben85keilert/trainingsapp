"""Die Rechnung hinter dem Bedienen im Bild (Ben, 16.11.2026: „Ziehen von einem Knoten auf
eine Übung zum Verbinden“, die Leiste eines Wegs unter dem Bild) — flet-frei, in
`core/ablauf.py`: was ein gezogener Punkt verbindet (`verbinden`), welche Zahl nach einem
Wechsel des Auslösers gilt (`ausloeser_wechsel`, vorher eine Lambda im Wege-Formular) und wie
weit „−“ und „+“ gehen (`kante_schritt`)."""

from __future__ import annotations

import itertools
from dataclasses import replace

from trainingsapp.core import ablauf as ab
from trainingsapp.core.ablauf import Ablauf, Frage, Kante


def test_punkt_auf_knoten_ist_ein_weg_auf_sich_selbst_noch_einmal() -> None:
    a = Ablauf(True, "a", (Kante("a", "b", ab.WDH, 12),), (Frage("f"),))
    # auf eine andere Übung oder eine Frage: ein neuer, freier Weg — hinten angehängt, der
    # Hauptweg (der erste) bleibt der Hauptweg
    neu = ab.verbinden(a, "a", "f")
    assert neu is not None and neu.kanten == (Kante("a", "b", ab.WDH, 12), Kante("a", "f"))
    assert neu.start == "a" and neu.fragen == a.fragen
    # auf sich selbst: die Schleife mit ihrer Beschriftung — wie vorher „Routing → Noch einmal“
    schleife = ab.verbinden(a, "b", "b")
    assert schleife is not None
    assert schleife.kanten[-1] == Kante("b", "b", text="noch einmal")
    assert ab.verbinden(schleife, "b", "b") is None  # die Schleife gibt es schon
    # „Ende“ und „◀ zurück“ sind Ziele wie Knoten
    for ziel in (ab.ENDE, ab.ZURUECK):
        weg = ab.verbinden(a, "b", ziel)
        assert weg is not None and weg.kanten[-1] == Kante("b", ziel)
        assert ab.verbinden(weg, "b", ziel) is None
    # Den Weg gibt es schon — auch wenn er einen anderen Auslöser trägt: nichts
    assert ab.verbinden(a, "a", "b") is None
    # Eine Frage hat keinen Weg zu sich selbst, aber zu jeder Übung
    assert ab.verbinden(a, "f", "f") is None
    von_frage = ab.verbinden(a, "f", "b")
    assert von_frage is not None and von_frage.kanten[-1] == Kante("f", "b")
    # Leere Angaben ändern nichts
    assert ab.verbinden(a, "", "b") is None and ab.verbinden(a, "a", "") is None


def test_start_auf_knoten_setzt_den_start() -> None:
    a = Ablauf(True, "a", (Kante("a", "b"), Kante("b", "c")), (Frage("f"),))
    neu = ab.verbinden(a, ab.VOM_START, "b")
    assert neu is not None and neu.start == "b" and neu.kanten == a.kanten  # kein Weg dazu
    assert ab.verbinden(a, ab.VOM_START, "a") is None  # ist es schon
    # eine Frage darf der Start sein (`Ablauf.startknoten`), ein Ende nicht
    frage = ab.verbinden(a, ab.VOM_START, "f")
    assert frage is not None and frage.startknoten(["a", "b", "c"]) == "f"
    assert ab.verbinden(a, ab.VOM_START, ab.ENDE) is None
    assert ab.verbinden(a, ab.VOM_START, ab.ZURUECK) is None
    # „Start“ ist kein Ziel
    assert ab.verbinden(a, "b", ab.VOM_START) is None
    assert ab.verbinden(a, ab.VOM_START, ab.VOM_START) is None
    # Ohne Start (geleert, Ben 16.11.2026): Der gezogene Start hebt den Vermerk auf — nichts
    # sonst ändert sich, und das Workout beginnt wieder
    ohne = Ablauf(True, kanten=(Kante("b", "c"),), ohne_start=True)
    assert ab.ohne_start_text(ohne, ["a", "b", "c"])
    gesetzt = ab.verbinden(ohne, ab.VOM_START, "b")
    assert gesetzt is not None and (gesetzt.start, gesetzt.ohne_start) == ("b", False)
    assert gesetzt.kanten == ohne.kanten and not ab.ohne_start_text(gesetzt, ["a", "b", "c"])


def _alte_regel(k: Kante, art: str) -> tuple[int, float]:
    """Die Regel, wie sie bis 16.11.2026 als Lambda in `components/wege_form._weg` stand
    (Kommentar N72) — hier abgeschrieben, damit der Umzug nach `core.ablauf` nichts ändert."""
    n = (
        k.n
        if k.n and {art, k.ausloeser} <= {ab.WDH, ab.WDH_IN_ZEIT}
        else 12
        if art in (ab.WDH, ab.WDH_IN_ZEIT)
        else 7
        if art == ab.SKALA
        else 0
    )
    return n, k.sekunden or (60.0 if art == ab.WDH_IN_ZEIT else 0.0)


def test_ausloeser_wechsel_rechnet_wie_das_formular_bisher() -> None:
    for alt, n, sekunden, neu in itertools.product(
        ab.AUSLOESER, (0, 1, 7, 12, 30), (0.0, 45.0), ab.AUSLOESER
    ):
        k = Kante("a", "b", alt, n, sekunden=sekunden, text="Rücken", pflicht=True, bis=9)
        ergebnis = ab.ausloeser_wechsel(k, neu)
        assert (ergebnis.n, ergebnis.sekunden) == _alte_regel(k, neu), (alt, n, sekunden, neu)
        assert ergebnis.ausloeser == neu
        # alles andere am Weg bleibt, wie es war
        assert replace(ergebnis, ausloeser=alt, n=n, sekunden=sekunden) == k
    # Die Zahl wandert nur zwischen den Wiederholungs-Auslösern mit (N72): Aus „30 Wdh.“ wird
    # nie „Skala ≥ 30“
    k = Kante("a", "b", ab.WDH, 30)
    assert ab.ausloeser_wechsel(k, ab.WDH_IN_ZEIT).n == 30
    assert ab.ausloeser_wechsel(k, ab.SKALA).n == 7
    assert ab.ausloeser_wechsel(ab.ausloeser_wechsel(k, ab.SKALA), ab.WDH).n == 12


def test_schritte_bleiben_gueltig_und_ladbar() -> None:
    """„−“ und „+“ führen nie zu einem Weg, den das Laden anders läse: Wiederholungen und
    Sekunden bleiben über null (sonst fiele der Auslöser auf „frei“ bzw. „Wdh.“ zurück),
    „bis“ liegt nie unter „ab“ (sonst fiele es weg)."""
    wege = [
        Kante("a", "b", ab.WDH, 1),
        Kante("a", "b", ab.WDH_IN_ZEIT, 1, sekunden=5.0),
        Kante("a", "b", ab.SKALA, 7),
        Kante("a", "b", ab.SKALA, 0, bis=0),
    ]
    for k in wege:
        for feld, schritt in itertools.product(("n", "sekunden", "bis"), (-1, 1)):
            neu = k
            for _ in range(4):
                neu = ab.kante_schritt(neu, feld, schritt)
                assert Kante.aus_dict(neu.als_dict()) == neu, (k, feld, schritt, neu)
                assert neu.ausloeser == k.ausloeser
                if neu.bis is not None:
                    assert neu.bis >= neu.n
    # Wiederholungen: nie unter 1; Sekunden: in Fünferschritten, nie unter 5
    assert ab.kante_schritt(wege[0], "n", -1).n == 1 and ab.kante_schritt(wege[0], "n", 1).n == 2
    assert ab.kante_schritt(wege[1], "sekunden", -1).sekunden == ab.SEKUNDEN_SCHRITT
    assert ab.kante_schritt(wege[1], "sekunden", 1).sekunden == 2 * ab.SEKUNDEN_SCHRITT
    # Skala: „ab“ darf unter null (N72); „bis“ offen ↔ „ab“
    assert ab.kante_schritt(Kante("a", "b", ab.SKALA, 0), "n", -1).n == -1
    offen = Kante("a", "b", ab.SKALA, 3)
    zu = ab.kante_schritt(offen, "bis", 1)
    assert zu.bis == 3 and ab.kante_schritt(zu, "bis", -1).bis is None
    assert ab.kante_schritt(ab.kante_schritt(zu, "bis", 1), "n", 1).n == 4  # bis 4: ab bis 4
    assert ab.kante_schritt(replace(zu, bis=4), "n", 5).n == 4
    # Was nicht zum Auslöser gehört, ändert nichts — auch ein unbekanntes Feld nicht
    frei = Kante("a", "b", text="Rücken")
    for feld in ("n", "sekunden", "bis", "sonstwas"):
        assert ab.kante_schritt(frei, feld, 1) == frei
    assert ab.kante_schritt(wege[0], "sekunden", 1) == wege[0]
    assert ab.kante_schritt(wege[0], "bis", 1) == wege[0]
    assert ab.kante_schritt(wege[2], "sekunden", 1) == wege[2]
