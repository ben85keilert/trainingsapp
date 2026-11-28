"""Die Skala als Linie mit Wertefenster (Ben, 28.11.2026, `ui/components/skala_linie.py`):
Linie und Fenster koppeln in beide Richtungen, gemeldet wird je Eingabe einmal."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.result_spec import FieldSpec, FieldType  # noqa: E402
from trainingsapp.ui.components.skala_linie import (  # noqa: E402
    STRICHE_MAX,
    SkalaLinie,
    skala_feld,
)


def _alle(control):
    yield control
    for name in ("controls", "content"):
        kind = getattr(control, name, None)
        if isinstance(kind, list):
            for k in kind:
                yield from _alle(k)
        elif isinstance(kind, ft.Control):
            yield from _alle(kind)


def _striche(linie: SkalaLinie) -> int:
    return sum(1 for c in _alle(linie.control) if isinstance(c, ft.Container) and c.width == 2)


def test_leer_dann_linie_setzt_das_fenster() -> None:
    gemeldet: list = []
    linie = SkalaLinie(skala_feld(0, 10), None, gemeldet.append, data="x")
    assert linie.wert is None and linie.fenster.value == "" and linie.regler.opacity == 0.45
    assert (linie.regler.data, linie.fenster.data) == ("x", ("fenster", "x"))
    # Ziehen: das Fenster folgt, gemeldet wird noch nichts
    linie.regler.on_change(SimpleNamespace(control=SimpleNamespace(value=6.4)))
    assert linie.fenster.value == "6" and linie.regler.opacity == 1 and gemeldet == []
    linie.regler.value = 6.4
    linie.regler.on_change_end(None)
    assert gemeldet == [6]
    linie.regler.on_change_end(None)  # derselbe Wert noch einmal: keine zweite Meldung
    assert gemeldet == [6]


def test_tipp_auf_den_anfang_setzt_den_kleinsten_wert() -> None:
    """Ohne Wert steht der Punkt blass am Anfang — ein Tipp dorthin ändert die Linie nicht,
    das Loslassen trägt trotzdem den kleinsten Wert ein."""
    gemeldet: list = []
    linie = SkalaLinie(skala_feld(1, 10), None, gemeldet.append)
    linie.regler.on_change_end(None)
    assert gemeldet == [1] and linie.fenster.value == "1"


def test_fenster_stellt_die_linie_und_meldet_beim_verlassen() -> None:
    gemeldet: list = []
    linie = SkalaLinie(skala_feld(0, 10), 2, gemeldet.append)
    linie.fenster.value = "7"
    linie.fenster.on_change(None)
    assert linie.regler.value == 7 and gemeldet == []  # der Punkt folgt, gemeldet wird später
    linie.fenster.on_blur(None)
    assert gemeldet == [7]
    # außerhalb: beim Tippen bleibt der Punkt, beim Verlassen gilt der Rand
    linie.fenster.value = "42"
    linie.fenster.on_change(None)
    assert linie.regler.value == 7
    linie.fenster.on_submit(None)
    assert (linie.fenster.value, linie.regler.value, gemeldet) == ("10", 10, [7, 10])
    # Unlesbares fällt auf den Stand zurück
    linie.fenster.value = "abc"
    linie.fenster.on_blur(None)
    assert linie.fenster.value == "10" and gemeldet == [7, 10]
    # leer: kein Wert, der Punkt wird blass
    linie.fenster.value = " "
    linie.fenster.on_blur(None)
    assert linie.wert is None and linie.regler.opacity == 0.45 and gemeldet == [7, 10, None]


def test_schritt_komma_und_striche() -> None:
    f = FieldSpec("s", FieldType.SCALE, "Skala", min=0, max=5, step=0.5)
    gemeldet: list = []
    linie = SkalaLinie(f, None, gemeldet.append)
    linie.fenster.value = "2,7"
    linie.fenster.on_blur(None)
    assert gemeldet == [2.5] and linie.fenster.value == "2,5" and linie.regler.value == 2.5
    assert _striche(linie) == 11
    assert _striche(SkalaLinie(skala_feld(6, 20), 13)) == 15  # Borg: je Stufe ein Strich
    fein = SkalaLinie(skala_feld(0, 100), 40)
    assert _striche(fein) == 0 and STRICHE_MAX < 100 and fein.regler.divisions == 100


def test_wort_der_stufe_wandert_mit() -> None:
    linie = SkalaLinie(skala_feld(0, 10), 5, worte={5: "anstrengend", 10: "maximal"})
    texte = lambda: [c.value for c in _alle(linie.control) if isinstance(c, ft.Text)]  # noqa: E731
    assert "5 · anstrengend" in texte()
    linie.regler.value = 10
    linie.regler.on_change(None)
    assert "10 · maximal" in texte()
    linie.regler.value = 6
    linie.regler.on_change(None)
    assert "" in texte() and "10 · maximal" not in texte()


def test_setzen_meldet_nichts_und_gesperrt() -> None:
    gemeldet: list = []
    linie = SkalaLinie(skala_feld(0, 10), None, gemeldet.append, gesperrt=True)
    assert linie.regler.disabled and linie.fenster.disabled
    linie.setzen(4, aktualisieren=False)
    assert (linie.wert, linie.fenster.value, linie.regler.value, gemeldet) == (4, "4", 4, [])
