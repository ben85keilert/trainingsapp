"""Die Geometrie des Ablaufbilds (Ben, 10.11.2026): ein Austrittspunkt je Übung, Wege ohne
fremde Knoten zu kreuzen, Rückwege in Gassen, Stummel für „◀ zurück“ und „Ende“."""

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
    assert g.abzweige["a"] == (x, y + 32 + geo.AUSTRITT)
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
    assert g.hoehe > max(y for _, y in g.abzweige.values())


def test_zwei_wege_in_denselben_knoten_haben_getrennte_griffe() -> None:
    a = Ablauf(True, "a", (Kante("a", "b"), Kante("a", "c"), Kante("b", "d"), Kante("c", "d")))
    g = geo.geometrie(a, ab.layout(a, ["a", "b", "c", "d"]))
    nach_d = [w for w in g.wege if w.kante.nach == "d"]
    assert len(nach_d) == 2 and nach_d[0].seite != nach_d[1].seite
    (x0, y0), (x1, y1) = nach_d[0].griff, nach_d[1].griff
    assert abs(x0 - x1) + abs(y0 - y1) > 20
