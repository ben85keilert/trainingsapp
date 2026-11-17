"""Die Geometrie des Ablaufbilds (Ben, 10.11.2026): ein Austrittspunkt je Übung, Wege ohne
fremde Knoten zu kreuzen, Rückwege in Gassen, Stummel für „◀ zurück“ und „Ende“. Seit
16.11.2026: ein Abzweig nur, wo mehrere Wege abgehen — ein eindeutiger Weg hat einen Punkt;
und jeder Knoten hat **seinen** Punkt, an dem man im Reiter „Ablauf“ einen Weg zieht."""

from __future__ import annotations

from trainingsapp.core import ablauf as ab
from trainingsapp.core import ablauf_geometrie as geo
from trainingsapp.core.ablauf import Ablauf, Frage, Kante


def _kasten(g: geo.Geometrie, k: str, fragen: set[str]) -> tuple[float, float, float, float]:
    x, y = g.mitten[k]
    if k in fragen:
        return (x - geo.FRAGE_B / 2, y - geo.FRAGE_H / 2, x + geo.FRAGE_B / 2, y + geo.FRAGE_H / 2)
    return (x - geo.NAME_B / 2, y - 32, x + geo.NAME_B / 2, y + 32 + geo.NAME_H)


def _kreuzt(g: geo.Geometrie, w: geo.Weg, fragen: set[str]) -> list[str]:
    """Fremde Knoten, durch die der Weg läuft."""
    out = []
    for k in g.mitten:
        if k in (w.kante.von, w.kante.nach):
            continue
        li, o, r, u = _kasten(g, k, fragen)
        for kurve in w.kurven:
            if any(li <= x <= r and o <= y <= u for x, y in (kurve.bei(i / 40) for i in range(41))):
                out.append(k)
                break
    return out


def test_ein_austrittspunkt_fuer_alle_wege() -> None:
    a = Ablauf(
        True,
        "a",
        (
            Kante("a", "b"),
            Kante("a", "c", ab.SKALA, 7),
            Kante("a", "a"),
            Kante("a", ab.ZURUECK),
            Kante("a", ab.ENDE),
            Kante("b", "a"),
        ),
    )
    ids = ["a", "b", "c"]
    g = geo.geometrie(a, ab.layout(a, ids))
    von_a = [w for w in g.wege if w.kante.von == "a"]
    assert [w.art for w in von_a] == [geo.AB, geo.AB, geo.SCHLEIFE, geo.ZURUECK, geo.ENDE]
    # Alle beginnen am Abzweig; der liegt unter Bild und Namen, der Stamm führt dorthin
    assert {w.kurven[0].p0 for w in von_a} == {g.abzweige["a"]}
    x, y = g.mitten["a"]
    assert g.abzweige["a"] == (x, y + 32 + geo.NAME_H + geo.AUSTRITT)
    assert g.abzweige["a"] == g.austritte["a"]
    oben, unten = g.staemme["a"]
    assert unten == g.abzweige["a"] and y + 32 < oben[1] < unten[1]
    # Jeder Weg hat seinen eigenen Griff — keine zwei liegen aufeinander
    griffe = [w.griff for w in g.wege]
    for i, p in enumerate(griffe):
        for q in griffe[i + 1 :]:
            assert abs(p[0] - q[0]) + abs(p[1] - q[1]) > 20
    # Stummel haben keine Spitze und enden im Griff; „zurück“ links, „Ende“ rechts
    zurueck, ende = von_a[3], von_a[4]
    assert zurueck.spitze is None and zurueck.kurven[-1].p3 == zurueck.griff
    assert zurueck.griff[0] < x < ende.griff[0]
    # Die Schleife kommt links im eigenen Knoten an
    assert von_a[2].spitze is not None and von_a[2].spitze[0] < x


def test_wege_weichen_knoten_aus() -> None:
    """Ein Weg über mehrere Ebenen läuft nicht durch den Knoten dazwischen, ein Rückweg nicht
    durch die Spalte, aus der er kommt."""
    a = Ablauf(
        True,
        "a",
        (
            Kante("a", "b"),
            Kante("b", "c"),
            Kante("c", "d"),
            Kante("a", "c"),  # überspringt b
            Kante("a", "d"),  # überspringt b und c
            Kante("d", "a"),  # ganz hinauf
            Kante("c", "b"),  # eine Ebene hinauf
            Kante("d", "f"),
            Kante("f", "b"),
        ),
        (Frage("f", "Wie geht es?"),),
    )
    ids = ["a", "b", "c", "d"]
    g = geo.geometrie(a, ab.layout(a, ids))
    for w in g.wege:
        assert _kreuzt(g, w, {"f"}) == [], (w.kante.von, w.kante.nach, w.art)
    # Rückwege kommen von der Seite ins Ziel
    for w in g.wege:
        if w.art == geo.RUECK:
            assert w.spitze is not None and w.spitze[1] == g.mitten[w.kante.nach][1]
    assert g.breite > max(x for x, _ in g.mitten.values())
    assert g.hoehe > max(y for _, y in g.austritte.values())


def test_zwei_wege_in_denselben_knoten_haben_getrennte_griffe() -> None:
    a = Ablauf(True, "a", (Kante("a", "b"), Kante("a", "c"), Kante("b", "d"), Kante("c", "d")))
    g = geo.geometrie(a, ab.layout(a, ["a", "b", "c", "d"]))
    nach_d = [w for w in g.wege if w.kante.nach == "d"]
    assert len(nach_d) == 2 and nach_d[0].seite != nach_d[1].seite
    (x0, y0), (x1, y1) = nach_d[0].griff, nach_d[1].griff
    assert abs(x0 - x1) + abs(y0 - y1) > 20


def test_eindeutiger_weg_hat_nur_einen_punkt() -> None:
    """Ben, 16.11.2026: „wenn ein Weg eindeutig ist, keine zwei Knoten zwischen den Übungen,
    sondern nur 1. Wenn mehr Wege gemeinsamer Knoten und Abzweigungsknoten so wie jetzt.“ —
    der Abzweig steht nur, wo mehrere Wege abgehen; bei genau einem bleibt sein Griff."""
    a = Ablauf(
        True,
        "a",
        (
            Kante("a", "b"),  # a: zwei Wege → Abzweig und je Weg ein Griff
            Kante("a", "c", ab.SKALA, 7),
            Kante("b", "d"),  # b: ein Weg hinunter
            Kante("c", ab.ENDE),  # c: nur der Stummel „Ende“
            Kante("d", "d"),  # d: nur die Schleife
        ),
    )
    ids = ["a", "b", "c", "d"]
    g = geo.geometrie(a, ab.layout(a, ids))
    assert sorted(g.abzweige) == ["a"]
    # Der Austritt bleibt für alle: dort endet der Stamm, dort beginnt der Weg
    assert sorted(g.austritte) == ids == sorted(g.staemme)
    assert all(w.kurven[0].p0 == g.austritte[w.kante.von] for w in g.wege)
    # Je Weg genau ein Griff — bei „b“ also ein einziger Punkt zwischen b und d, unter dem
    # Austritt und über dem Ziel
    (weg,) = [w for w in g.wege if w.kante.von == "b"]
    assert g.austritte["b"][1] < weg.griff[1] < g.mitten["d"][1] - 32
    assert len(g.wege) == len(a.kanten)
    # Eine Übung ohne Weg hat weder Austritt noch Stamm noch Abzweig
    leer = Ablauf(True, "a")
    g = geo.geometrie(leer, ab.layout(leer, ["a"]))
    assert g.austritte == {} and g.staemme == {} and g.abzweige == {}
    # Zeigt einer von zwei Wegen auf einen Knoten, der nicht gezeichnet wird, bleibt ein Punkt
    halb = Ablauf(True, "a", (Kante("a", "b"), Kante("a", "x")))
    g = geo.geometrie(halb, ab.layout(halb, ["a", "b"]))
    assert g.abzweige == {} and [w.kante.nach for w in g.wege] == ["b"]


def test_jeder_knoten_hat_seinen_punkt() -> None:
    """Ben, 16.11.2026: „Ziehen von einem Knoten auf eine Übung zum Verbinden“ — der Punkt, an
    dem gezogen wird, ist bei mehreren Wegen der Abzweig, bei genau einem dessen Griff (es
    bleibt bei einem Punkt zwischen zwei Übungen) und ohne Weg eine Stelle knapp unter der
    Beschriftung. Wo er liegt, sagt die Geometrie, nicht die Oberfläche."""
    a = Ablauf(
        True,
        "a",
        (
            Kante("a", "b"),  # a: zwei Wege → der Abzweig
            Kante("a", "c"),
            Kante("b", "d"),  # b: ein Weg → sein Griff
            Kante("c", "f"),  # c: ein Weg zu einer Frage
            Kante("f", ab.ENDE),  # die Frage: nur der Stummel „Ende“
        ),
        (Frage("f", "Wie geht es?"),),
    )
    ids = ["a", "b", "c", "d"]
    lage = ab.layout(a, ids)
    g = geo.geometrie(a, lage, beschriftung={"d": 48.0})
    assert sorted(g.punkte) == sorted(g.mitten) == ["a", "b", "c", "d", "f"]
    assert g.punkte["a"] == g.abzweige["a"]
    griff = {w.kante.von: w.griff for w in g.wege}
    assert g.punkte["b"] == griff["b"] and g.punkte["c"] == griff["c"]
    # Der eine Weg der Frage ist der Stummel „Ende“: Ihr Punkt bleibt unter ihr — am Stummel
    # steht nur „Ende“ (Ben, 17.11.2026: Von dort zog niemand einen zweiten Weg)
    assert g.punkte["f"] == g.austritte["f"] != griff["f"]
    # „d“ hat keinen Weg: der Punkt liegt mittig unter Bild und Beschriftung — so tief, wie
    # der Austritt läge; einen Stamm dorthin gibt es nicht
    x, y = g.mitten["d"]
    assert g.punkte["d"] == (x, y + geo.KNOTEN / 2 + 48.0 + geo.AUSTRITT)
    assert "d" not in g.austritte and "d" not in g.staemme
    # Keine zwei Punkte liegen aufeinander, jeder liegt in der Fläche
    punkte = list(g.punkte.values())
    for i, p in enumerate(punkte):
        assert 0 < p[0] < g.breite and 0 < p[1] < g.hoehe
        for q in punkte[i + 1 :]:
            assert abs(p[0] - q[0]) + abs(p[1] - q[1]) > 30
    # Eine Frage ohne Weg: unter der Karte
    nur = Ablauf(True, "a", (Kante("a", "f"),), (Frage("f"),))
    g = geo.geometrie(nur, ab.layout(nur, ["a"]))
    x, y = g.mitten["f"]
    assert g.punkte["f"] == (x, y + geo.FRAGE_H / 2 + geo.AUSTRITT_FRAGE)
    # „Start“ hat denselben Punkt: an der Unterkante der Pille, über der Startübung
    sx, sy = geo.start_punkt(g.mitten["a"][0])
    assert sx == g.mitten["a"][0] and sy == geo.RAND + geo.START_H
    assert sy < g.mitten["a"][1] - geo.KNOTEN / 2
