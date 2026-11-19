"""Das Blatt „Abschnitt“ (`ui/components/abschnitt_blatt.py`): Zeiten je Feld, ohne Fenster.

Ben, 19.11.2026: „‚Von‘: Button/Schalter für Uhrzeit/Dauer direkt neben der Zeit. ‚Bis‘: hier
braucht es 3 Möglichkeiten: Uhrzeit, Dauer der Messung, Länge des Abschnittes.“
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from hrv_core.ereignisse import Zeitbezug  # noqa: E402
from hrv_core.recording import Beat  # noqa: E402

from trainingsapp.core.zeitangabe import DAUER, LAENGE, UHR, uhr_text  # noqa: E402
from trainingsapp.ui.components.abschnitt_blatt import abschnitt_blatt  # noqa: E402

START = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)
BEATS = [Beat(float(i), 1000, 60, float(i)) for i in range(0, 601)]


def _alle(c):
    yield c
    for name in ("content", "controls"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _blatt(*, uhr_da: bool = True, uhr: bool = False):
    zb = Zeitbezug(lambda: BEATS, START if uhr_da else None, achse=lambda: [b.t_s for b in BEATS])
    gesichert: list[tuple] = []
    blatt = abschnitt_blatt(
        None,
        zeitbezug=zb,
        live=False,
        grenzen=lambda: (0.0, 600.0),
        name="Treppe",
        von=60.0,
        bis=120.0,
        neu=True,
        uhr=uhr,
        sichern=lambda *w: gesichert.append(w),
    )
    alle = list(_alle(blatt))
    felder = {c.label: c for c in alle if isinstance(c, ft.TextField)}
    wahl = next(c for c in alle if isinstance(c, ft.SegmentedButton))
    knopf = next(c for c in alle if isinstance(c, ft.TextButton) and c.data == "von_schreibweise")
    return blatt, felder, wahl, knopf, gesichert


def _waehlen(wahl: ft.SegmentedButton, modus: str) -> None:
    wahl.selected = [modus]
    wahl.on_change(SimpleNamespace(control=wahl))


def _speichern(blatt) -> None:
    next(c for c in _alle(blatt) if isinstance(c, ft.FilledButton)).on_click()
    asyncio.run(blatt.on_dismiss(None))


def test_bis_als_laenge_des_abschnitts() -> None:
    blatt, felder, wahl, _, gesichert = _blatt()
    assert [s.value for s in wahl.segments] == [UHR, DAUER, LAENGE]
    assert [s.label.value for s in wahl.segments] == ["Uhrzeit", "Messdauer", "Länge"]
    assert felder["Von"].value == "1:00" and felder["Bis"].value == "2:00"  # Messdauer
    _waehlen(wahl, LAENGE)
    assert felder["Bis"].value == "1:00"  # 60 s lang
    felder["Bis"].value = "3:00"
    _speichern(blatt)
    assert gesichert == [("Treppe", 60.0, 240.0, 0.0, 0.0)]


def test_mit_laenge_rueckt_das_ende_mit_dem_anfang() -> None:
    blatt, felder, wahl, _, gesichert = _blatt()
    _waehlen(wahl, LAENGE)
    felder["Von"].value = "2:00"
    felder["Von"].on_blur(None)
    assert felder["Bis"].value == "1:00"  # die Länge bleibt
    _speichern(blatt)
    assert gesichert[0][1:3] == (120.0, 180.0)
    # In „Messdauer“ bleibt das Ende stehen
    blatt, felder, wahl, _, gesichert = _blatt()
    felder["Von"].value = "1:30"
    felder["Von"].on_blur(None)
    _speichern(blatt)
    assert gesichert[0][1:3] == (90.0, 120.0)


def test_von_schaltet_neben_dem_feld_zwischen_uhrzeit_und_messdauer() -> None:
    blatt, felder, _, knopf, gesichert = _blatt()
    assert knopf.visible and knopf.content == "Uhrzeit"
    knopf.on_click()
    assert felder["Von"].value == uhr_text(START, 60.0) and knopf.content == "Messdauer"
    assert felder["Bis"].value == "2:00"  # „Bis“ hat seine eigene Schreibweise
    felder["Von"].value = uhr_text(START, 90.0)
    _speichern(blatt)
    assert gesichert[0][1:3] == (90.0, 120.0)


def test_ohne_startzeit_keine_uhrzeit() -> None:
    _, felder, wahl, knopf, _ = _blatt(uhr_da=False, uhr=True)
    assert [s.value for s in wahl.segments] == [DAUER, LAENGE]
    assert not knopf.visible and felder["Von"].value == "1:00"


def test_unlesbare_laenge_sagt_was_sie_erwartet() -> None:
    blatt, felder, wahl, _, gesichert = _blatt()
    _waehlen(wahl, LAENGE)
    felder["Bis"].value = "bald"
    _speichern(blatt)
    assert felder["Bis"].error == "Länge, z. B. 30:00" and gesichert == []
