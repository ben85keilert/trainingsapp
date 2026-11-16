"""Die Karte „So wächst der Plan“ im Kurs-Editor (Ben, 16.11.2026,
`ui/components/kursplan_bild.py`): der Zielplan als Ablaufbild, Späteres blass, Tipp auf eine
Übung bzw. einen Weg. Die Rechnung prüft `tests/test_kursbild.py`. Läuft nur mit `flet`.
"""

from __future__ import annotations

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core import ablauf as ab  # noqa: E402
from trainingsapp.core.kursbau import Kurssicht  # noqa: E402
from trainingsapp.core.kursbild import planbild  # noqa: E402
from trainingsapp.core.kursbloecke import AUSWAHL, PLAN_UEBUNG, PLAN_WEG, Block  # noqa: E402
from trainingsapp.core.kurse import Kapitel, Kurs, Kursplan  # noqa: E402
from trainingsapp.core.models import Exercise  # noqa: E402
from trainingsapp.ui.components.ablaufbild import NEBEL  # noqa: E402
from trainingsapp.ui.components.kursplan_bild import (  # noqa: E402
    KEIN_BAUSTEIN,
    LEER,
    LISTE,
    MAX_HOEHE,
    OHNE_WEG,
    kursplan_bild_karte,
)
from trainingsapp.ui.state import AppState  # noqa: E402

KATALOG = {k: Exercise(id=k, name=k.title()) for k in ("planke", "kaefer", "bruecke", "seit")}


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "actions"):
        kind = getattr(c, name, None)
        if isinstance(kind, list):
            for k in kind:
                yield from _alle(k)
        elif kind is not None and hasattr(kind, "__dict__"):
            yield from _alle(kind)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _mit(c, data):
    (treffer,) = [x for x in _alle(c) if getattr(x, "data", None) == data]
    return treffer


def _kurs(wege: bool = True) -> Kurs:
    zwei = [
        Block(AUSWAHL, id="w", uebungen=["kaefer", "bruecke"]),
        Block(PLAN_UEBUNG, id="dazu", aus="w", hinter="a"),
    ]
    if wege:
        zwei.append(Block(PLAN_WEG, id="weg", von="a", zu="dazu", kante={"ausloeser": "zeit"}))
    return Kurs(
        name="Rumpf-Kurs",
        kursplan=Kursplan("Rumpf"),
        kapitel=[
            Kapitel(id="k1", titel="Anfang", bloecke=[Block(PLAN_UEBUNG, id="a", uebung="planke")]),
            Kapitel(id="k2", titel="Erweiterung", bloecke=zwei),
            Kapitel(id="k3", titel="Seitlich", bloecke=[Block(PLAN_UEBUNG, id="s", uebung="seit")]),
        ],
    )


def _bild(kurs: Kurs):
    erstes = kurs.kapitel[0]
    bild = planbild(Kurssicht(kurs, erstes.id, erstes.bloecke, KATALOG))
    assert bild is not None
    return bild


def test_karte_zeigt_den_zielplan_und_wie_viel_freigegeben_ist(state) -> None:
    kurs = _kurs()
    bild = _bild(kurs)
    karte = kursplan_bild_karte(None, state, bild, KATALOG, kurs.kapitel)
    texte = _texte(karte.control)
    assert "SO WÄCHST DER PLAN" in texte  # `karte.titel` setzt in Großbuchstaben
    # ohne Angabe das letzte Kapitel: alles da, nichts blass
    assert karte.bis() == 3 and "Bis Kapitel 3 „Seitlich“: alle 3 Übungen im Plan." in texte
    assert {"Planke", "Kaefer", "Seit"} <= set(texte)
    assert LISTE not in texte  # der Weg macht den Plan zum Workout
    # Chips: je Kapitel einer — kein „Anfang“, die Grundlage ist leer
    chips = [c for c in _alle(karte.control) if isinstance(c, ft.Chip)]
    assert [c.label.value for c in chips] == ["Kapitel 1", "Kapitel 2", "Kapitel 3"]
    assert [c.selected for c in chips] == [False, False, True]

    # Kapitel 1 wählen: Käfer und Seitstütz kommen später — blass
    karte.waehlen(1)
    assert _mit(karte.control, "kursbild_stand").value == (
        "Bis Kapitel 1 „Anfang“: 1 von 3 Übungen im Plan."
    )
    assert [c.selected for c in chips] == [True, False, False]
    _planke, kaefer, seit = (i.id for i in bild.plan.items)
    assert set(bild.spaeter(1)) == {kaefer, seit}
    # der Chip tut dasselbe wie der Aufruf
    chips[1].on_select(None)
    assert karte.bis() == 2 and _mit(karte.control, "kursbild_stand").value.startswith(
        "Bis Kapitel 2 „Erweiterung“: 2 von 3"
    )


def test_spaeteres_steht_blass(state) -> None:
    """Was ein späteres Kapitel bringt, zeichnet das Ablaufbild auf `NEBEL` — geprüft an der
    Zeichnung, die die Karte bestellt."""
    from trainingsapp.ui.components import ablaufbild as abbild

    kurs = _kurs()
    bild = _bild(kurs)
    planke, kaefer, seit = (i.id for i in bild.plan.items)
    z = abbild.zeichnung(state, bild.ablauf, bild.plan.items, KATALOG, vernebelt=bild.spaeter(1))
    assert z.knoten[kaefer].opacity == NEBEL and z.knoten[seit].opacity == NEBEL
    assert z.knoten[planke].opacity != NEBEL


def test_tipp_auf_uebung_und_weg_ruft_die_rueckrufe(state) -> None:
    kurs = _kurs()
    bild = _bild(kurs)
    von: list[str] = []
    wege: list[tuple[int, str, str]] = []
    karte = kursplan_bild_karte(
        None,
        state,
        bild,
        KATALOG,
        kurs.kapitel,
        bis=2,
        weg_von=von.append,
        weg_oeffnen=lambda w: wege.append((w.nr, w.kapitel_id, w.block_id)),
    )
    planke, kaefer, seit = (i.id for i in bild.plan.items)
    karte.knoten(kaefer)
    assert von == ["dazu:kaefer"]  # die Marke, mit der ein Baustein „Weg“ die Übung nennt
    karte.kante(ab.Kante(planke, kaefer))
    assert wege == [(2, "k2", "weg")]
    # ein Schritt der Liste gehört zu keinem Baustein — die Karte sagt es
    karte.kante(ab.Kante(kaefer, seit))
    assert wege == [(2, "k2", "weg")]
    meldung = _mit(karte.control, "kursbild_meldung")
    assert meldung.visible and meldung.value == KEIN_BAUSTEIN
    karte.knoten(planke)
    assert not meldung.visible and von == ["dazu:kaefer", "a"]


def test_uebung_ohne_weg_steht_unter_dem_bild_und_laesst_sich_antippen(state) -> None:
    """Zu einer Übung, die ein späteres Kapitel ohne Weg bringt, führt im eigenen Ablauf nichts
    — das Ablaufbild zeichnet sie nicht. Die Karte nennt sie darunter; ein Tipp ist „Weg von
    hier“ wie am Knoten."""
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
                    Block(PLAN_WEG, id="vorbei", von="p", zu="k"),
                ],
            ),
            Kapitel(id="k2", titel="B", bloecke=[Block(PLAN_UEBUNG, id="d", uebung="bruecke")]),
        ],
    )
    von: list[str] = []
    karte = kursplan_bild_karte(None, state, _bild(kurs), KATALOG, kurs.kapitel, weg_von=von.append)
    assert OHNE_WEG in _texte(karte.control)
    (knopf,) = _mit(karte.control, "kursbild_lose").controls
    assert knopf.content == "Bruecke · Kapitel 2" and knopf.opacity == 1.0
    knopf.on_click(None)
    assert von == ["d"]
    # bis Kapitel 1 gibt es sie noch nicht: blass wie im Bild
    karte.waehlen(1)
    (knopf,) = _mit(karte.control, "kursbild_lose").controls
    assert knopf.opacity == NEBEL
    # die Karte reicht Meldungen des Aufrufers durch und gibt den gerechneten Plan heraus
    karte.melden("Hinweis")
    assert _mit(karte.control, "kursbild_meldung").value == "Hinweis"
    assert karte.bild.lose() == [karte.bild.plan.items[-1].id]


def test_bild_ist_so_hoch_wie_die_zeichnung(state) -> None:
    """Das Formular rollt — das Bild zeigt darum alle Übungen, statt ein Fenster von 340 px."""
    from trainingsapp.ui.components import ablaufbild as abbild

    kurs = _kurs()
    bild = _bild(kurs)
    karte = kursplan_bild_karte(None, state, bild, KATALOG, kurs.kapitel)
    (ansicht,) = [c for c in _alle(karte.control) if isinstance(c, ft.InteractiveViewer)]
    z = abbild.zeichnung(state, bild.ablauf, bild.plan.items, KATALOG)
    assert ansicht.height == int(min(z.hoehe + 16, MAX_HOEHE)) and ansicht.height > 340
    fest = kursplan_bild_karte(None, state, bild, KATALOG, kurs.kapitel, hoehe=300)
    (ansicht,) = [c for c in _alle(fest.control) if isinstance(c, ft.InteractiveViewer)]
    assert ansicht.height == 300


def test_liste_und_leerer_plan(state) -> None:
    kurs = _kurs(wege=False)
    karte = kursplan_bild_karte(None, state, _bild(kurs), KATALOG, kurs.kapitel)
    assert LISTE in _texte(karte.control)
    leer = Kurs(name="Leer", kursplan=Kursplan("P"), kapitel=[Kapitel(id="k1", titel="A")])
    karte = kursplan_bild_karte(None, state, _bild(leer), KATALOG, leer.kapitel)
    assert LEER in _texte(karte.control)
    karte.waehlen(1)  # tut nichts, wirft nicht
