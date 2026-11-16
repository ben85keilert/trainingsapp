"""Die Karte „Das kommt noch“ auf der Kursseite (Ben, 16.11.2026, Schritt A1,
`docs/plan_kurs_ablauf.md` §12, Skizze V1; `ui/components/kommt_noch.py`).

Unter „Dein Kursplan“ steht, was die späteren Kapitel am Plan vorschlagen. Die Karte ändert
nichts, klappt zu und auf (gemerkt für die Sitzung) und fehlt, wenn nichts mehr kommt. Die
Rechnung prüft `tests/test_kursvorschau.py`. Läuft nur mit `flet`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.kursbloecke import (  # noqa: E402
    AUSWAHL,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    Block,
)
from trainingsapp.core.kurse import FREI, Kapitel, Kurs, Kursplan  # noqa: E402
from trainingsapp.core.models import Exercise  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil  # noqa: E402
from trainingsapp.ui.components.kommt_noch import FUSS, UNTERTITEL, ZEICHEN  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.kurse import kapitel_view, kurs_view  # noqa: E402

KARTE, KOPF, INHALT = "kommt_noch", "kommt_noch_kopf", "kommt_noch_inhalt"


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/", views=[], update=lambda: None, dialoge=[])

    async def push_route(route: str) -> None:
        p.route = route

    p.push_route = push_route
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: p.dialoge.pop() if p.dialoge else None
    return p


def _alle(c):
    yield c
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "actions"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _hat(c, wert) -> bool:
    return any(getattr(x, "data", None) == wert for x in _alle(c))


def _timer(sekunden: int, runden: int = 1) -> dict:
    return TimerProfil(abschnitte=[Abschnitt("Halten", sekunden)], runden=runden).als_dict()


def _kurs(state: AppState, **mehr) -> tuple[Kurs, dict[str, Exercise]]:
    """Der Kurs der Skizze V1 — gespeichert und wieder geladen: Kapitel 1 Planke, 2 Käfer,
    3 Seitstütz und ein Timer für die Planke, 4 eine von drei mit Ziel aus dem Test, 5 ein
    Weg von Käfer zu Seitstütz."""
    ue = {
        name: Exercise(name=name, result_spec=ResultSpec(fields=[vorrat_feld(feld)]))
        for name, feld in (
            ("Planke", "hold"),
            ("Käfer", "reps"),
            ("Seitstütz", "hold"),
            ("Brücke", "reps"),
            ("Vogel", "reps"),
            ("Rolle", "reps"),
        )
    }
    for u in ue.values():
        state.uebungen.speichern(u)
    kurs = Kurs(
        name="Rumpf-Kurs",
        kursplan=Kursplan("Rumpf"),
        kapitel=[
            Kapitel(
                titel="Grundlage",
                bloecke=[Block(PLAN_UEBUNG, id="planke", uebung=ue["Planke"].id)],
            ),
            Kapitel(
                titel="Erweiterung",
                bloecke=[
                    Block(
                        PLAN_UEBUNG,
                        id="kaefer",
                        uebung=ue["Käfer"].id,
                        hinter="planke",
                        timer=_timer(60),
                    )
                ],
            ),
            Kapitel(
                titel="Seitlich",
                bloecke=[
                    Block(PLAN_UEBUNG, id="seit", uebung=ue["Seitstütz"].id, hinter="kaefer"),
                    Block(PLAN_EINSTELLEN, id="runden", an="planke", timer=_timer(60, 3)),
                ],
            ),
            Kapitel(
                titel="Deine Wahl",
                bloecke=[
                    Block(
                        AUSWAHL,
                        id="wahl",
                        uebungen=[ue[n].id for n in ("Brücke", "Vogel", "Rolle")],
                        anzahl=1,
                    ),
                    Block(TEST, id="test", aus="wahl", feld="reps"),
                    Block(PLAN_UEBUNG, id="dazu", aus="wahl", ziel_aus="test"),
                ],
            ),
            Kapitel(
                titel="Abschluss",
                bloecke=[
                    Block(PLAN_WEG, id="weg", von="kaefer", zu="seit", kante={"ausloeser": "zeit"})
                ],
            ),
        ],
        **mehr,
    )
    state.kurse.speichern(kurs)
    geladen = state.kurse.laden(kurs.id)
    assert geladen is not None
    return geladen, ue


def _kapitel_1_fertig(state: AppState, kurs: Kurs) -> None:
    """Kapitel 1 übernommen und abgeschlossen — Kapitel 2 läuft."""
    profil, eins = state.profil.id, kurs.kapitel[0]
    state.kurse.starten(kurs, profil)
    zeilen = state.kurse.plan_aenderungen(kurs, eins, profil)
    state.kurse.plan_uebernehmen(kurs, eins, profil, {z.id for z in zeilen})
    state.kurse.kapitel_abschliessen(kurs, eins, profil)


def _zeilen(ansicht) -> list[str]:
    """Die Zeilen der Karte, wie sie zu lesen sind: Zeichen und Satz. „+“ und „~“ stehen als
    Text da, der Pfeil eines Weges als Symbol (als Text fehlte er der Schrift im Browser)."""
    ergebnis = []
    for x in _alle(_daten(ansicht, KARTE)):
        if isinstance(getattr(x, "data", None), tuple) and x.data[0] == "kommt_noch_zeile":
            zeichen = ZEICHEN[x.data[1]][0]
            symbole = [s.icon for s in _alle(x) if isinstance(s, ft.Icon)]
            if zeichen == "→":
                assert symbole == [ft.Icons.ARROW_FORWARD] and len(_texte(x)) == 1
            else:
                assert not symbole and _texte(x)[0] == zeichen
            ergebnis.append(f"{zeichen} {_texte(x)[-1]}")
    return ergebnis


def test_karte_unter_dein_kursplan_mit_den_zeilen_der_skizze(page, state) -> None:
    kurs, _ue = _kurs(state)
    _kapitel_1_fertig(state, kurs)
    plan = state.kurse.kursplan(kurs, state.profil.id)
    vorher = state.con.total_changes

    ansicht = kurs_view(page, state, kurs)
    texte = _texte(_daten(ansicht, KARTE))
    assert texte[:2] == ["Das kommt noch", UNTERTITEL]
    assert [t for t in texte if t.startswith("KAPITEL")] == [
        "KAPITEL 3 · SEITLICH",
        "KAPITEL 4 · DEINE WAHL",
        "KAPITEL 5 · ABSCHLUSS",
    ]
    assert _zeilen(ansicht) == [
        "+ Seitstütz kommt dazu, hinter Käfer",
        "~ Timer für Planke: 1:00 Halten · 3 Runden",
        "+ eine Übung, die du dort wählst (1 von 3)",
        "~ ihr Ziel aus deinem Test",
        "→ von Käfer weiter zu Seitstütz nach 60 s",
    ]
    assert texte[-1] == FUSS
    # aufgeklappt, mit dem Pfeil nach oben; die Karte steht unter „Dein Kursplan“
    assert _daten(ansicht, INHALT).visible
    assert [x.icon for x in _alle(_daten(ansicht, KOPF)) if isinstance(x, ft.Icon)] == [
        ft.Icons.EXPAND_LESS
    ]
    marken = [getattr(x, "data", None) for x in _alle(ansicht)]
    assert marken.index(("kursplan", plan.id)) < marken.index(KARTE)
    # Die Vorschau ändert nichts: kein Schreiben, der Plan bleibt — und kein Knopf außer dem Kopf
    assert state.con.total_changes == vorher
    assert state.kurse.kursplan(kurs, state.profil.id) == plan
    assert not [x for x in _alle(_daten(ansicht, KARTE)) if isinstance(x, ft.Button | ft.Checkbox)]


def test_kopf_klappt_zu_und_die_sitzung_merkt_es(page, state) -> None:
    kurs, _ue = _kurs(state)
    _kapitel_1_fertig(state, kurs)
    ansicht = kurs_view(page, state, kurs)
    assert state.kommt_noch_zu == set()

    _daten(ansicht, KOPF).on_click()
    assert not _daten(ansicht, INHALT).visible
    assert state.kommt_noch_zu == {kurs.id}
    kopf = _daten(ansicht, KOPF)
    assert [x.icon for x in _alle(kopf) if isinstance(x, ft.Icon)] == [ft.Icons.EXPAND_MORE]
    assert _texte(kopf) == ["Das kommt noch", UNTERTITEL]  # der Kopf bleibt stehen

    # die Ansicht wird neu gebaut (zurück vom Kapitel): Die Karte ist noch zu
    ansicht = kurs_view(page, state, kurs)
    assert not _daten(ansicht, INHALT).visible
    _daten(ansicht, KOPF).on_click()
    assert _daten(ansicht, INHALT).visible and state.kommt_noch_zu == set()

    # ein anderer Kurs ist davon unberührt — und in der Datenbank steht davon nichts
    state.kommt_noch_zu.add("anderer-kurs")
    assert _daten(kurs_view(page, state, kurs), INHALT).visible


def test_keine_karte_ohne_kursplan_vor_dem_start_und_wenn_nichts_mehr_kommt(page, state) -> None:
    kurs, _ue = _kurs(state)
    profil = state.profil.id
    assert not _hat(kurs_view(page, state, kurs), KARTE)  # noch kein Kapitel erreicht

    # begonnen, noch kein Plan (leere Grundlage): Die Vorschau rechnet gegen die Grundlage —
    # „Dein Kursplan“ gibt es noch nicht, und es entsteht auch keiner
    state.kurse.starten(kurs, profil)
    ansicht = kurs_view(page, state, kurs)
    assert _zeilen(ansicht)[0] == "+ Käfer kommt dazu, hinter Planke"
    assert "DEIN KURSPLAN" not in _texte(ansicht)
    assert state.kurse.kursplan(kurs, profil) is None

    # im letzten Kapitel kommt nichts mehr
    for kapitel in kurs.kapitel[:-1]:
        state.kurse.kapitel_abschliessen(kurs, kapitel, profil)
    assert not _hat(kurs_view(page, state, kurs), KARTE)

    ohne = Kurs(name="Ohne Kursplan", kapitel=[Kapitel(titel="A"), Kapitel(titel="B")])
    state.kurse.speichern(ohne)
    state.kurse.starten(ohne, profil)
    assert not _hat(kurs_view(page, state, ohne), KARTE)


def test_offene_wahl_aus_dem_kapitel_steht_in_der_vorschau(page, state) -> None:
    """Die Wahl, die das Kapitel für die Sitzung hält (P212), gilt auch auf der Kursseite —
    mit demselben Stempel gelesen wie im Kapitel, und sie bleibt dabei erhalten."""
    kurs, ue = _kurs(state, freischaltung=FREI)  # „frei“: Kapitel 4 lässt sich schon öffnen
    _kapitel_1_fertig(state, kurs)
    vier = kurs.kapitel[3]
    bruecke = ue["Brücke"]

    kapitel = kapitel_view(page, state, kurs, vier, ft.UrlLauncher())
    _daten(kapitel, ("wahl", "wahl", bruecke.id)).on_select()
    gehalten = dict(state.kurs_wahl)
    assert [wahl for _stempel, wahl in gehalten.values()] == [{"wahl": [bruecke.id]}]

    ansicht = kurs_view(page, state, kurs)
    assert _zeilen(ansicht)[2:4] == [
        "+ Brücke kommt dazu, ans Ende",
        "~ Ziel für Brücke aus deinem Test",
    ]
    assert state.kurs_wahl == gehalten  # gelesen, nicht verworfen
    assert state.kurse.kursplan(kurs, state.profil.id).items[-1].exercise_id == ue["Planke"].id

    # „Von vorn“: kein Kapitel erreicht — keine Karte, und die alte Wahl gilt nicht mehr
    state.kurse.zuruecksetzen(kurs, state.profil.id)
    assert not _hat(kurs_view(page, state, kurs), KARTE)
    state.kurse.starten(kurs, state.profil.id)
    assert "+ eine Übung, die du dort wählst (1 von 3)" in _zeilen(kurs_view(page, state, kurs))
