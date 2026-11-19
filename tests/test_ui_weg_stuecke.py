"""Mehrere Stücke an einem Weg (Ben, 18.11.2026: „Bisher geht das vor allem für bestimmte Wege“
— und nur mit einem Link; `docs/plan_medien_zeitpunkte.md` §2, Frage d): der Editor des Wegs
nimmt weitere Links mit Titel."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.ablauf import Ablauf, Kante  # noqa: E402
from trainingsapp.core.bedingung import Inhalt, Stueck  # noqa: E402
from trainingsapp.ui.components.wege_form import wege_karte  # noqa: E402


def _alle(c):
    yield c
    for name in ("content", "controls"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _verlassen(feld, wert: str) -> None:
    feld.on_blur(SimpleNamespace(control=SimpleNamespace(value=wert)))


def test_weiteres_medium_am_weg() -> None:
    kante = Kante("i1", "i2", inhalt=Inhalt("Erst lockern", "https://x.org/a"))
    stand = {"a": Ablauf(an=True, start="i1", kanten=(kante,))}
    merken: dict = {}

    def karte():
        return wege_karte(
            "i1",
            lambda: stand["a"],
            lambda neu: stand.update(a=neu),
            lambda: None,
            namen={"i1": "1 · Kniebeuge", "i2": "2 · Planke"},
            merken=merken,
        )

    _daten(karte(), "weg_stueck_dazu").on_click(None)
    # Der Titel allein wartet, bis die Adresse dasteht
    _verlassen(_daten(karte(), ("weg_stueck_titel", 0)), "Wade dehnen")
    assert stand["a"].kanten[0].inhalt.medien == ()
    assert _daten(karte(), ("weg_stueck_titel", 0)).value == "Wade dehnen"
    _verlassen(_daten(karte(), ("weg_stueck_uri", 0)), "https://x.org/wade")
    inhalt = stand["a"].kanten[0].inhalt
    assert inhalt.medien == (Stueck("https://x.org/wade", "Wade dehnen"),)
    assert (inhalt.text, inhalt.url) == ("Erst lockern", "https://x.org/a")  # bleibt
    # Eine geleerte Adresse nimmt das Stück heraus
    _verlassen(_daten(karte(), ("weg_stueck_uri", 0)), "")
    assert stand["a"].kanten[0].inhalt.medien == ()
