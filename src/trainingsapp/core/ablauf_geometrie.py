"""Die **Geometrie** des Ablaufbilds — wo Knoten, Austrittspunkte und Wege liegen (Ben,
10.11.2026, `docs/plan_verzweigungen.md` §8.11).

Wie bei einem Nerv: Alle Wege einer Übung verlassen sie an **einem** Punkt — ein kurzer Stamm
nach unten (unter Bild und Namen) zum **Austritt**. Gehen dort **mehrere** Wege ab, steht an
ihm der **Abzweig** (ein Knoten zum Antippen: alle Wege dieser Übung), und jeder Weg hat
seinen eigenen **Griff** (Punkt mit Beschriftung: nur dieser Weg). Ist der Weg **eindeutig** —
genau einer —, gibt es keinen Abzweig: Zwischen den zwei Übungen steht nur der Griff (Ben,
16.11.2026: „wenn ein Weg eindeutig ist, keine zwei Knoten zwischen den Übungen, sondern nur
1“). So hat jeder Knoten **seinen Punkt** (`Geometrie.punkte`): den Abzweig, den einen Griff
oder — ohne Weg — die Stelle unter der Beschriftung, an der der Austritt läge; im Reiter
„Ablauf“ zieht man ihn auf eine andere Übung (Ben, 16.11.2026). „Start“ hat denselben Punkt
(`start_punkt`). Die Wege:

- **ab**: zu einem Knoten weiter unten — eine weiche Kurve zur Oberkante; liegt ein anderer
  Knoten im Weg (der Weg überspringt Ebenen), weicht sie seitlich aus;
- **rueck**: zu einem Knoten auf gleicher Höhe oder weiter oben — in einer Gasse neben den
  Knoten hinauf und von der Seite hinein;
- **schleife**: dieselbe Übung noch einmal — links herum zurück in den Knoten;
- **zurueck** und **ende**: kurze Stummel links bzw. rechts am Austritt, sie enden im Griff.

Hier steht nur Rechnung (Punkte, Kurven, Kollisionen) — gezeichnet wird in
`ui/components/ablaufbild.py`. Maße in Pixeln vor dem Zoom.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .ablauf import Ablauf, Kante, Lage

#: Kantenlänge des Übungsbilds
KNOTEN = 64
#: Abstand zweier Spalten
SPALTE = 140
#: Abstand zweier Ebenen — Platz für Beschriftung, Abzweig, Wege und ihre Griffe, aber nicht
#: mehr (Ben, 10.11.2026: 264 war zu lang)
EBENE = 190
RAND = 24
#: links mehr Platz: Schleifen und „◀ zurück“ liegen links am Knoten
RAND_X = 108
START_H = 36
FRAGE_B = 120
FRAGE_H = 66
#: Breite der Beschriftung unter einem Übungsbild
NAME_B = SPALTE - 24
#: so weit unter der **Beschriftung** (Name, Beiname, „bei Bedarf“) liegt der Austritt — knapp
#: darunter, nicht in festem Abstand zum Bild (Ben, 10.11.2026)
AUSTRITT = 12
#: so weit unter einer Frage liegt ihr Austritt (sie hat keine Beschriftung darunter)
AUSTRITT_FRAGE = 20
#: wo der Griff eines Wegs nach unten auf seiner Kurve liegt — gut zwei Drittel der Höhe, der
#: Abstand zum Ziel bleibt dabei wie zuvor
GRIFF_T = 0.72
#: Höhe der Beschriftung, wenn niemand sie angibt (ein bis zwei Zeilen Name)
NAME_H = 34.0
#: Luft um einen Knoten, die ein fremder Weg nicht berührt
LUFT = 6.0
#: Rückwege laufen in Gassen: halbe Spaltenbreiten neben dem Ziel — bei ganzen Spalten genau
#: zwischen zwei Knoten
GASSE = SPALTE / 2

AB, RUECK, SCHLEIFE, ZURUECK, ENDE = "ab", "rueck", "schleife", "zurueck", "ende"

Punkt = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Kurve:
    """Eine kubische Bézier-Kurve — auch eine Gerade (Stützpunkte auf der Strecke)."""

    p0: Punkt
    p1: Punkt
    p2: Punkt
    p3: Punkt

    def bei(self, t: float) -> Punkt:
        """Der Punkt bei ``t`` (0 = Anfang, 1 = Ende).

        >>> Kurve((0, 0), (0, 10), (10, 20), (10, 30)).bei(0.5)
        (5.0, 15.0)
        """
        u = 1 - t
        a, b, c, d = u**3, 3 * u**2 * t, 3 * u * t**2, t**3
        return (
            a * self.p0[0] + b * self.p1[0] + c * self.p2[0] + d * self.p3[0],
            a * self.p0[1] + b * self.p1[1] + c * self.p2[1] + d * self.p3[1],
        )

    def winkel_am_ende(self) -> float:
        """Richtung, in der die Kurve ankommt (rad, 0 = nach rechts, π/2 = nach unten)."""
        vx, vy = self.p3[0] - self.p2[0], self.p3[1] - self.p2[1]
        if abs(vx) < 1e-9 and abs(vy) < 1e-9:
            vx, vy = self.p3[0] - self.p0[0], self.p3[1] - self.p0[1]
        return math.atan2(vy, vx)


def gerade(a: Punkt, b: Punkt) -> Kurve:
    """Die Strecke von ``a`` nach ``b`` als Kurve."""
    return Kurve(
        a,
        (a[0] + (b[0] - a[0]) / 3, a[1] + (b[1] - a[1]) / 3),
        (a[0] + 2 * (b[0] - a[0]) / 3, a[1] + 2 * (b[1] - a[1]) / 3),
        b,
    )


@dataclass(frozen=True, slots=True)
class Weg:
    """Eine Kante im Bild: ihre Kurven ab dem Austritt, die Pfeilspitze (x, y, Winkel) am Ziel
    — ``None`` bei einem Stummel — und der Griff mit der Seite der Beschriftung (−1 links,
    1 rechts, 0 darunter)."""

    kante: Kante
    art: str
    kurven: tuple[Kurve, ...]
    griff: Punkt
    seite: int
    spitze: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True)
class Geometrie:
    """Alles, was die Zeichnung braucht."""

    #: Pixelmitte je Knoten (Mitte des Übungsbilds bzw. der Fragekarte)
    mitten: dict[str, Punkt]
    #: der Austritt je Knoten mit Wegen: dort endet der Stamm, dort beginnen alle seine Wege
    austritte: dict[str, Punkt]
    #: der Abzweig — ein Punkt zum Antippen am Austritt —, nur wo **mehrere** Wege abgehen;
    #: bei genau einem Weg steht allein dessen Griff zwischen den Übungen
    abzweige: dict[str, Punkt]
    #: der Stamm vom Knoten zum Austritt
    staemme: dict[str, tuple[Punkt, Punkt]]
    wege: tuple[Weg, ...]
    breite: float
    hoehe: float
    #: die kleinste Spalte — für `ort`
    x_min: float
    #: **der Punkt** je gezeichnetem Knoten — an ihm beginnen seine Wege, an ihm zieht man
    #: einen neuen (Ben, 16.11.2026): bei mehreren Wegen der Abzweig, bei genau einem dessen
    #: Griff, wenn er **abwärts** führt — bei einem Rückweg (sein Griff läge weit weg), einem
    #: Stummel („Ende“, „◀ zurück“) oder „noch einmal“ der Austritt unter dem Knoten —, ohne
    #: gezeichneten Weg die Stelle knapp unter der Beschriftung
    punkte: dict[str, Punkt]


def ort(lage: Lage, x_min: float = 0.0) -> Punkt:
    """Die Pixelmitte zu einer Lage.

    >>> ort(Lage(1.0, 1)) == (RAND_X + SPALTE + KNOTEN / 2, RAND + START_H + 22 + EBENE + 32)
    True
    """
    return (
        RAND_X + (lage.x - x_min) * SPALTE + KNOTEN / 2,
        RAND + START_H + 22 + lage.ebene * EBENE + KNOTEN / 2,
    )


def start_punkt(x: float) -> Punkt:
    """Der Punkt von „Start“ — an der Unterkante der Pille bei ``x``, von dort führt der Pfeil
    zur Startübung. Im Reiter „Ablauf“ zieht man ihn auf eine Übung: Sie wird der Start.

    >>> start_punkt(140.0) == (140.0, RAND + START_H)
    True
    """
    return (x, float(RAND + START_H))


def geometrie(
    ablauf: Ablauf,
    lage: Mapping[str, Lage],
    *,
    beschriftung: Mapping[str, float] | None = None,
    weitere: Sequence[Lage] = (),
) -> Geometrie:
    """Die Geometrie zu den Lagen der gezeichneten Knoten. ``beschriftung``: Höhe des Texts
    unter dem Bild je Planübung (sonst `NAME_H`); ``weitere``: Lagen ohne Knoten (der leere
    Platz unter „Start“) — sie zählen für die Größe.

    >>> a = Ablauf(True, "p", (Kante("p", "k"), Kante("p", "r"), Kante("k", "p")))
    >>> g = geometrie(a, {"p": Lage(0.5, 0), "k": Lage(0.0, 1), "r": Lage(1.0, 1)})
    >>> [w.art for w in g.wege], sorted(g.austritte)
    (['ab', 'ab', 'rueck'], ['k', 'p'])
    >>> g.austritte["p"][1] - g.mitten["p"][1] == KNOTEN / 2 + NAME_H + AUSTRITT
    True
    >>> all(w.kurven[0].p0 == g.austritte[w.kante.von] for w in g.wege)  # ein Austrittspunkt
    True
    >>> sorted(g.abzweige)  # „p“ hat zwei Wege: Abzweig und Griffe; „k“ einen: nur den Griff
    ['p']
    >>> g.punkte["p"] == g.abzweige["p"]  # je Knoten ein Punkt: hier der Abzweig
    True
    >>> g.punkte["r"][1] - g.mitten["r"][1] == KNOTEN / 2 + NAME_H + AUSTRITT  # ohne Weg
    True

    Der eine Weg von „k“ ist ein **Rückweg** — sein Griff liegt in der Gasse, weit weg. Der
    Punkt von „k“ bleibt darum unter „k“ (sein Austritt), der Griff gehört nur dem Weg:

    >>> weg_k = next(w for w in g.wege if w.kante.von == "k")
    >>> g.punkte["k"] == g.austritte["k"], g.punkte["k"] == weg_k.griff
    (True, False)

    Ein einzelner Weg **abwärts** dagegen: Punkt und Griff sind dasselbe.

    >>> g = geometrie(Ablauf(True, "p", (Kante("p", "k"),)), {"p": Lage(0, 0), "k": Lage(0, 1)})
    >>> g.punkte["p"] == g.wege[0].griff
    True

    Führt der eine Weg zum **Ende** (oder „◀ zurück“, „noch einmal“), bleibt der Punkt unter dem
    Knoten — am Stummel steht nur „Ende“:

    >>> from trainingsapp.core.bedingung import ENDE as zum_ende
    >>> g = geometrie(Ablauf(True, "p", (Kante("p", zum_ende),)), {"p": Lage(0, 0)})
    >>> g.punkte["p"] == g.austritte["p"], g.punkte["p"] == g.wege[0].griff
    (True, False)
    """
    text_h = dict(beschriftung or {})
    fragen = {f.id for f in ablauf.fragen}
    alle = [*lage.values(), *weitere]
    x_min = min((v.x for v in alle), default=0.0)
    x_max = max((v.x for v in alle), default=0.0)
    ebene_max = max((v.ebene for v in alle), default=0)
    mitten = {k: ort(v, x_min) for k, v in lage.items()}

    def halb(k: str) -> tuple[float, float]:
        """Halbe Breite und halbe Höhe der Form eines Knotens."""
        return (FRAGE_B / 2, FRAGE_H / 2) if k in fragen else (KNOTEN / 2, KNOTEN / 2)

    def kasten(k: str) -> tuple[float, float, float, float]:
        """Was ein Knoten belegt — Form und Beschriftung, mit Luft."""
        x, y = mitten[k]
        if k in fragen:
            return (
                x - FRAGE_B / 2 - LUFT,
                y - FRAGE_H / 2 - LUFT,
                x + FRAGE_B / 2 + LUFT,
                y + FRAGE_H / 2 + LUFT,
            )
        return (
            x - NAME_B / 2 - LUFT,
            y - KNOTEN / 2 - LUFT,
            x + NAME_B / 2 + LUFT,
            y + KNOTEN / 2 + text_h.get(k, NAME_H) + LUFT,
        )

    kaesten = {k: kasten(k) for k in mitten}

    def treffer(kurven: Sequence[Kurve], ohne: set[str]) -> int:
        """Wie viele Stützpunkte der Kurven in fremden Knoten liegen."""
        n = 0
        for kurve in kurven:
            for i in range(1, 24):
                x, y = kurve.bei(i / 24)
                for name, (li, o, r, u) in kaesten.items():
                    if name not in ohne and li <= x <= r and o <= y <= u:
                        n += 1
        return n

    def unter(kn: str) -> tuple[float, float]:
        """Wo der Stamm eines Knotens beginnt und wo er endet (Höhe des Austritts)."""
        y = mitten[kn][1]
        if kn in fragen:
            beginn = y + FRAGE_H / 2
            return beginn, beginn + AUSTRITT_FRAGE
        text = y + KNOTEN / 2 + text_h.get(kn, NAME_H)
        return text + 2, text + AUSTRITT

    austritte: dict[str, Punkt] = {}
    staemme: dict[str, tuple[Punkt, Punkt]] = {}
    for kn in dict.fromkeys(x.von for x in ablauf.kanten):
        if kn not in mitten:
            continue
        x = mitten[kn][0]
        beginn, unten = unter(kn)
        austritte[kn] = (x, unten)
        staemme[kn] = ((x, min(beginn, unten - 8)), (x, unten))

    wege: list[Weg] = []
    ankommend: dict[str, int] = {}
    gassen: dict[float, int] = {}
    for k in ablauf.kanten:
        j = austritte.get(k.von)
        if j is None:
            continue
        x0, y0 = mitten[k.von]
        hb, _ = halb(k.von)
        if k.schleife:
            ziel = (x0 - hb - 6, y0)
            kurve = Kurve(j, (x0 - 46, j[1] + 26), (x0 - hb - 62, y0 + 34), ziel)
            wege.append(
                Weg(k, SCHLEIFE, (kurve,), kurve.bei(0.45), -1, (*ziel, kurve.winkel_am_ende()))
            )
            continue
        if k.zurueck or k.zum_ende:
            # Stummel: links „◀ zurück“, rechts „Ende“ — sie enden im Griff
            s = -1 if k.zurueck else 1
            ende = (j[0] + s * 46, j[1] + 24)
            kurve = Kurve(j, (j[0] + s * 22, j[1]), (j[0] + s * 40, j[1] + 6), ende)
            wege.append(Weg(k, ZURUECK if k.zurueck else ENDE, (kurve,), ende, 0, None))
            continue
        if k.nach not in mitten:
            continue
        x1, y1 = mitten[k.nach]
        hb1, hh1 = halb(k.nach)
        if y1 > y0:
            b = (x1, y1 - hh1 - 6)
            d = max((b[1] - j[1]) * 0.55, 30.0)
            beste: Kurve | None = None
            beste_n = -1
            # gerade hinunter, sonst seitlich ausweichen — die erste Kurve ohne Treffer
            for versatz in (0.0, 0.75, -0.75, 1.5, -1.5, 2.25, -2.25):
                v = versatz * SPALTE
                kurve = Kurve(j, (j[0] + v, j[1] + d), (b[0] + v, b[1] - d), b)
                n = treffer((kurve,), {k.von, k.nach})
                if beste is None or n < beste_n:
                    beste, beste_n = kurve, n
                if n == 0:
                    break
            assert beste is not None
            # Der Griff nahe am Ziel, wo die Wege auseinander liegen; kommen mehrere Wege im
            # selben Knoten an, liegen ihre Griffe gestaffelt und abwechselnd rechts und links
            i = ankommend.get(k.nach, 0)
            ankommend[k.nach] = i + 1
            griff = beste.bei(max(GRIFF_T - 0.2 * i, 0.36))
            wege.append(
                Weg(k, AB, (beste,), griff, 1 if i % 2 == 0 else -1, (*b, beste.winkel_am_ende()))
            )
            continue
        # hinauf oder auf gleicher Höhe: im freien Band unter dem Austritt zur Seite, in einer
        # Gasse zwischen den Spalten hinauf und von der Seite ins Ziel. Die Gasse liegt neben
        # dem **Ziel** (zuerst auf der Seite, von der der Weg kommt); steht dort ein Knoten,
        # die nächste — die erste ohne Treffer, sonst die mit den wenigsten
        oben, unten = y1 + 30, j[1] - 10
        zuerst = 1 if x0 >= x1 else -1
        wahl: tuple[int, float, tuple[Kurve, ...]] | None = None
        wahl_n = -1
        for stufe in range(1, 9):
            for s in (zuerst, -zuerst):
                gasse = x1 + s * GASSE * stufe
                if gasse < 8 and wahl is not None:  # links aus dem Bild — nicht dorthin
                    continue
                haken = Kurve(j, (j[0], j[1] + 34), (gasse, j[1] + 34), (gasse, unten))
                hinauf = gerade((gasse, unten), (gasse, oben))
                ziel = (x1 + s * (hb1 + 6), y1)
                hinein = Kurve((gasse, oben), (gasse, y1), (gasse, y1), ziel)
                # der Haken darf am eigenen Knoten vorbei, die Gasse nicht durch ihn hindurch
                n = treffer((haken,), {k.von, k.nach}) + treffer((hinauf, hinein), {k.nach})
                if wahl is None or n < wahl_n:
                    wahl, wahl_n = (s, gasse, (haken, hinauf, hinein)), n
                if n == 0:
                    break
            if wahl_n == 0:
                break
        assert wahl is not None
        s, gasse, kurven = wahl
        # mehrere Rückwege in derselben Gasse laufen zusammen — ihre Griffe liegen gestaffelt
        i = gassen.get(gasse, 0)
        gassen[gasse] = i + 1
        wege.append(
            Weg(
                k,
                RUECK,
                kurven,
                (
                    gasse,
                    min(unten - 16 - 40 * i, (oben + unten) / 2 + 20) if i else (oben + unten) / 2,
                ),
                s,
                (*kurven[-1].p3, math.pi if s > 0 else 0.0),
            )
        )

    rechts = max(
        [RAND_X + (x_max - x_min) * SPALTE + max(KNOTEN, FRAGE_B)]
        + [p[0] for w in wege for kurve in w.kurven for p in (kurve.p0, kurve.p3)]
    )
    breite = rechts + RAND + 120
    tiefster = max((p[1] for p in austritte.values()), default=0.0)
    hoehe = max(RAND + START_H + 22 + ebene_max * EBENE + KNOTEN + NAME_H + AUSTRITT, tiefster) + 80
    # Ein Abzweig steht nur, wo sich die Wege teilen: bei genau einem gezeichneten Weg bleibt
    # zwischen den zwei Übungen ein Punkt — sein Griff (Ben, 16.11.2026)
    anzahl = Counter(w.kante.von for w in wege)
    abzweige = {kn: p for kn, p in austritte.items() if anzahl[kn] >= 2}
    # Der Punkt je Knoten: der Abzweig, der Griff des einen Wegs — oder, ohne gezeichneten Weg,
    # die Stelle, an der der Austritt läge. Ist der eine Weg ein **Rückweg**, liegt sein Griff
    # weit weg in der Gasse: Dann ist der Punkt des Knotens sein Austritt, direkt unter ihm
    # (Ben, 17.11.2026, am Foto: „Nach der Frage ist es nicht möglich ein Ende zu setzen“ —
    # unter der Frage stand nichts zum Ziehen)
    # — und ebenso bei einem **Stummel** („Ende“, „◀ zurück“) oder „noch einmal“: Sein Griff ist
    # das Ende, nicht der Knoten — wer von dort einen zweiten Weg ziehen wollte, fand unter der
    # Frage nichts (Ben, 17.11.2026: „Daneben kann man aber nicht, wenn das Ende gesetzt ist,
    # noch einen weiteren Weg aufrufen“). Am Griff liegt der Punkt nur bei einem Weg **abwärts**
    griffe = {w.kante.von: w.griff for w in wege if anzahl[w.kante.von] == 1 and w.art == AB}
    punkte = {
        kn: abzweige.get(kn) or griffe.get(kn) or austritte.get(kn) or (mitten[kn][0], unter(kn)[1])
        for kn in mitten
    }
    return Geometrie(
        mitten, austritte, abzweige, staemme, tuple(wege), breite, hoehe, x_min, punkte
    )


__all__ = [
    "AB",
    "AUSTRITT",
    "EBENE",
    "ENDE",
    "FRAGE_B",
    "FRAGE_H",
    "KNOTEN",
    "NAME_B",
    "RAND",
    "RAND_X",
    "RUECK",
    "SCHLEIFE",
    "SPALTE",
    "START_H",
    "ZURUECK",
    "Geometrie",
    "Kurve",
    "Weg",
    "geometrie",
    "gerade",
    "ort",
    "start_punkt",
]
