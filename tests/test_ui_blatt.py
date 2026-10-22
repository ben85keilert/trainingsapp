"""Blätter von unten, die nie unter der Android-Leiste verschwinden (`components/blatt.py`).

Ben, 22.10.2026: „wenn das Eingabefenster zu groß ist, verschwindet der untere Teil der
Ansicht hinter die Androidleiste … die transparente Leiste macht den Zugang zum ‚Abbrechen‘
und ‚Speichern‘-Button unmöglich.“
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.ui.components.blatt import blatt_spalte  # noqa: E402


def _teile(sicher: ft.SafeArea) -> tuple[ft.Column, list[ft.Control], ft.Column]:
    """Scrollbereich, Fuß und die gemessene Spalte darin."""
    spalte = sicher.content.content
    bereich, *fuss = spalte.controls
    (innen,) = bereich.controls
    return bereich, fuss, innen


def test_inhalt_scrollt_knoepfe_stehen_fest_darunter() -> None:
    knoepfe = ft.Row([ft.TextButton("Abbrechen"), ft.FilledButton("Speichern")])
    sicher = blatt_spalte([ft.Text("Kopf"), ft.Text("viel Inhalt")], [knoepfe], geschaetzt=500)
    assert isinstance(sicher, ft.SafeArea) and sicher.avoid_intrusions_top is False
    bereich, fuss, innen = _teile(sicher)
    # Der Inhalt scrollt immer, nimmt höchstens den Platz, der da ist — die Knöpfe nicht
    assert bereich.scroll == ft.ScrollMode.AUTO and bereich.expand and bereich.expand_loose
    assert bereich.height == 500 and fuss == [knoepfe]
    assert [c.value for c in innen.controls] == ["Kopf", "viel Inhalt"]


def test_hoehe_folgt_der_messung() -> None:
    """Die Schätzung gilt nur bis zur ersten Messung — ein kurzes Blatt bleibt kurz."""
    sicher = blatt_spalte([ft.Text("kurz")], geschaetzt=600)
    bereich, _, innen = _teile(sicher)
    innen.on_size_change(SimpleNamespace(height=211.3, width=380))
    assert bereich.height == 212
    innen.on_size_change(SimpleNamespace(height=0, width=380))  # noch nicht gezeichnet
    assert bereich.height == 212


def test_vorhandene_spalte_wird_gemessen() -> None:
    """Wer seine Spalte selbst neu füllt (Tagesfeld-Blatt), gibt sie direkt."""
    eigene = ft.Column(tight=True, controls=[ft.Text("a")])
    _, fuss, innen = _teile(blatt_spalte(eigene))
    assert innen is eigene and fuss == [] and eigene.on_size_change is not None
