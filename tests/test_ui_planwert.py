"""Die Karte „Wert für den Plan“ (Ben, 17.11.2026, W3; `ui/components/planwert.py`,
`docs/plan_kurs_ablauf.md` §17).

    „Wert wird genommen und kann ganz genommen werden – prozentual abgeändert – manuell
    eingegeben (mit Klick und per Tastatur)“

Hier die Karte für sich und die Zeile je Übung bei einem Test „der gewählten“; die Karte auf
der Ergebnis-Seite des Testlaufs und hinter „Wert ändern“ im Kapitel prüft
`tests/test_ui_kurs_test.py`, die Rechnung `tests/test_kurse.py` und die Doctests in
`core/kursbloecke.py`. Läuft nur mit `flet`.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.kursbloecke import (  # noqa: E402
    ANTEIL,
    AUSWAHL,
    GANZ,
    HAND,
    TEST,
    Block,
    planwert,
)
from trainingsapp.core.kurse import Kapitel, Kurs, PlanVorlage, VorlageItem  # noqa: E402
from trainingsapp.core.models import Exercise, Session  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.ui.components.planwert import KARTE, planwert_karte  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.kurse import kapitel_view  # noqa: E402


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
    for name in ("content", "controls", "title", "subtitle", "leading", "trailing", "label"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text) and x.value]


def _daten(c, wert):
    gefunden = [x for x in _alle(c) if getattr(x, "data", None) == wert]
    if not gefunden:
        raise AssertionError(f"kein Control mit data={wert!r}")
    return gefunden[0]


def _hat(c, wert) -> bool:
    return any(getattr(x, "data", None) == wert for x in _alle(c))


def _klick(control) -> None:
    ergebnis = control.on_click(SimpleNamespace(control=control))
    if asyncio.iscoroutine(ergebnis):
        asyncio.run(ergebnis)


def _weg(karte, wie: str, marke="planwert_weg") -> None:
    umschalter = _daten(karte, marke)
    umschalter.selected = [wie]
    umschalter.on_change(SimpleNamespace(control=umschalter))


def _tippen(feld, text: str) -> None:
    feld.value = text
    feld.on_change(SimpleNamespace(control=feld))


# -- Die Karte für sich --------------------------------------------------------------------


def test_vorgewaehlt_ist_was_der_kurs_sagt(page) -> None:
    """Mindert der Kurs (80 %), steht „Anteil“ mit 80 % da; sonst „Ganz“. Dann beginnt
    „Anteil“ bei 100 % — die App erfindet keinen Abschlag."""
    reps = vorrat_feld("reps")
    mindert = planwert_karte(page, feld=reps, test_wert=22.0, vorgabe=0.8)
    assert _daten(mindert.control, "planwert_weg").selected == [ANTEIL]
    assert mindert.wahl() == planwert(ANTEIL, 22.0, anteil=0.8)
    assert _daten(mindert.control, "planwert_satz").value == "Der Plan nimmt 18 Wdh."

    ganz = planwert_karte(page, feld=reps, test_wert=22.0, vorgabe=1.0)
    assert _daten(ganz.control, "planwert_weg").selected == [GANZ]
    assert not _daten(ganz.control, "planwert_anteil").visible
    assert ganz.wahl() == planwert(GANZ, 22.0)
    _weg(ganz.control, ANTEIL)
    assert _daten(ganz.control, "planwert_prozent").value == "100"
    assert ganz.wahl().wert == 22
    _klick(_daten(ganz.control, "planwert_prozent_minus"))
    assert _daten(ganz.control, "planwert_prozent").value == "95"
    assert _daten(ganz.control, "planwert_ergibt").value == "= 21 Wdh."

    # mit einer getroffenen Wahl öffnet die Karte dort
    hand = planwert_karte(
        page, feld=reps, test_wert=22.0, vorgabe=0.8, gewaehlt=planwert(HAND, 22.0, hand=20)
    )
    assert _daten(hand.control, "planwert_weg").selected == [HAND]
    assert _daten(hand.control, "planwert_zahl").value == "20"
    assert _daten(hand.control, "planwert_hand").visible


def test_ohne_wert_ist_die_karte_verborgen_und_folgt_ihm(page) -> None:
    """Solange der Test keinen Wert hat, gibt es nichts zu wählen. Kommt er, gilt die Vorgabe
    des Kurses; ändert er sich, folgen „ganz“ und „Anteil“ — die Zahl von Hand bleibt."""
    gemeldet: list = []
    karte = planwert_karte(
        page, feld=vorrat_feld("reps"), test_wert=None, vorgabe=0.8, bei_wahl=gemeldet.append
    )
    assert not karte.control.visible and karte.wahl() is None
    karte.wert_setzen(22.0)
    assert karte.control.visible and karte.wahl() == planwert(ANTEIL, 22.0, anteil=0.8)
    karte.wert_setzen(30.0)
    assert karte.wahl().wert == 24  # 80 % von 30
    _weg(karte.control, HAND)
    assert karte.wahl().wert == 24 and gemeldet[-1].wie == HAND
    karte.wert_setzen(40.0)
    assert karte.wahl().wert == 24  # von Hand bleibt
    assert _daten(karte.control, "planwert_test").value == "Dein Test: 40 Wdh."
    karte.wert_setzen(None)
    assert not karte.control.visible


def test_unlesbares_aendert_nichts(page) -> None:
    """Eine Eingabe, die sich nicht lesen lässt (leer, 0), lässt die Wahl, wie sie war — beim
    Verlassen des Felds steht wieder da, was gilt."""
    karte = planwert_karte(page, feld=vorrat_feld("reps"), test_wert=22.0, vorgabe=0.8)
    prozent = _daten(karte.control, "planwert_prozent")
    _tippen(prozent, "")
    _tippen(prozent, "0")
    assert karte.wahl().anteil == 0.8
    prozent.on_blur(SimpleNamespace(control=prozent))
    assert prozent.value == "80"
    _tippen(prozent, "999")  # über der Grenze: 300 %
    assert karte.wahl().anteil == 3.0
    _weg(karte.control, HAND)
    zahl = _daten(karte.control, "planwert_zahl")
    _tippen(zahl, "0")
    assert karte.wahl().wert == 66  # wo „von Hand“ begann: 300 % von 22
    _klick(_daten(karte.control, "planwert_zahl_minus"))
    assert zahl.value == "65"


def test_knoepfe_und_schluessel(page) -> None:
    """Im Kapitel bringt die Karte „Abbrechen“ und „Übernehmen“ mit, und ihre Controls tragen
    den Schlüssel des Tests — mehrere Karten auf einer Seite bleiben unterscheidbar."""
    knopf = ft.FilledButton("Übernehmen", data="ja")
    karte = planwert_karte(
        page,
        feld=vorrat_feld("hold"),
        test_wert=50.0,
        vorgabe=1.0,
        knoepfe=[knopf],
        schluessel="t:x",
    )
    assert karte.control.data == (KARTE, "t:x")
    assert _hat(karte.control, "ja") and _hat(karte.control, ("planwert_weg", "t:x"))
    assert "Dein Eintrag vom Test bleibt, wie er ist." in _texte(karte.control)
    assert _daten(karte.control, ("planwert_satz", "t:x")).value == "Der Plan nimmt 50s Haltezeit."


# -- Test „der gewählten“: je Übung eine Zeile ----------------------------------------------


def test_wert_aendern_je_uebung_bei_mehreren_gewaehlten(page, state) -> None:
    """Misst ein Test mehrere gewählte Übungen, hat jede ihre Zeile — und ihren Knopf „Wert
    ändern“. Die Wahl gilt nur für diese Übung (`wert_schluessel`: ``<test>:<übung>``)."""
    uebungen = {
        name: Exercise(name=name, result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
        for name in ("Kniebeuge", "Käfer", "Brücke")
    }
    for u in uebungen.values():
        state.uebungen.speichern(u)
    kniebeuge, kaefer, bruecke = uebungen.values()
    kurs = Kurs(
        name="Kapitelpläne",
        kapitel=[
            Kapitel(
                titel="Wählen und testen",
                plaene=[PlanVorlage("Beine", items=[VorlageItem(kniebeuge.id)])],
                bloecke=[
                    Block(TEST, id="t", aus="w", feld="reps", faktor=0.5),
                    Block(AUSWAHL, id="w", uebungen=[kaefer.id, bruecke.id], anzahl=2),
                ],
            )
        ],
    )
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    kapitel = kurs.kapitel[0]
    profil = state.profil.id
    state.kurse.starten(kurs, profil)
    for uebung, wdh in ((kaefer, 30), (bruecke, 12)):
        session = Session(subject_id=profil)
        state.sitzungen.anlegen(session)
        state.sitzungen.eintrag_anlegen(session, uebung, {"reps": [wdh]})

    ansicht = kapitel_view(page, state, kurs, kapitel, ft.UrlLauncher())
    for uebung in (kaefer, bruecke):
        _daten(ansicht, ("wahl", "w", uebung.id)).on_select()
    assert "im Plan das Ziel: 15 Wdh." in _texte(ansicht)  # Käfer: 50 % von 30
    assert not _hat(ansicht, (KARTE, f"t:{kaefer.id}"))
    _klick(_daten(ansicht, ("wert_aendern", "t", kaefer.id)))
    schluessel = f"t:{kaefer.id}"
    karte = _daten(ansicht, (KARTE, schluessel))
    assert _daten(karte, ("planwert_prozent", schluessel)).value == "50"
    _weg(karte, GANZ, ("planwert_weg", schluessel))
    _klick(_daten(karte, ("planwert_uebernehmen", schluessel)))

    werte = {schluessel: 30.0, f"t:{bruecke.id}": 12.0}
    (gewaehlt,) = state.kurse.planwerte(kurs.id, profil, werte).items()
    assert gewaehlt[0] == schluessel and (gewaehlt[1].wie, gewaehlt[1].wert) == (GANZ, 30)
    # „Plan anlegen“ nimmt je Übung ihr Ziel: Käfer ganz, Brücke wie der Kurs (50 %)
    wahl = {"w": [kaefer.id, bruecke.id]}
    (plan,) = state.kurse.plaene_anlegen(kapitel, profil, werte, wahl)
    ziele = {i.exercise_id: i.target for i in plan.items}
    assert ziele[kaefer.id] == {"reps": [30]} and ziele[bruecke.id] == {"reps": [6]}
