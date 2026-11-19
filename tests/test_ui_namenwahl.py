"""Der Name eines Abschnitts (`ui/components/namenwahl.py`), ohne Fenster.

Ben, 19.11.2026: eine eigene Liste gemerkter Abschnittsnamen — „Nimm das alte Muster für
beide“: dasselbe Verhalten wie die Überschrift im Titel-Blatt (die Tests dazu stehen in
`test_ui_zurueck.py`, `test_titelblatt_*`).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import AbschnittName  # noqa: E402
from trainingsapp.ui.components.abschnitte import name_dialog  # noqa: E402
from trainingsapp.ui.components.namenwahl import Namenwahl, name_merken, namenwahl  # noqa: E402


def _zeilen(w: Namenwahl) -> list[str]:
    return [z.title.value for z in w.liste.controls if isinstance(z, ft.ListTile)]


def _tippen(w: Namenwahl, text: str) -> None:
    w.feld.value = text
    w.feld.on_change(None)


def _hrv(namen: list[AbschnittName]) -> SimpleNamespace:
    gemerkt: list[str] = []

    def merken(_p: str, name: str, *, verwendet: bool = True) -> AbschnittName:
        gemerkt.append(name)
        return AbschnittName(name=name)

    return SimpleNamespace(
        abschnittnamen=lambda _p: list(namen),
        abschnittname_merken=merken,
        abschnittname_entfernen=lambda i: namen.remove(next(n for n in namen if n.id == i)),
        gemerkt=gemerkt,
    )


def test_wie_das_titelblatt_liste_filtert_merkt_und_entfernt() -> None:
    """Vorgabe im Feld, die gemerkten Namen als Liste (angeheftete zuerst, wie das Repo sie
    liefert), Tippen filtert („enthält“), „merken“ nimmt Neues auf, ✕ nimmt heraus — keine
    Knöpfe."""
    namen = [AbschnittName(name="Behandlung", angeheftet=True), AbschnittName(name="Radfahren")]
    hrv = _hrv(namen)
    state = SimpleNamespace(hrv=hrv, profil=SimpleNamespace(id="p"))
    w = namenwahl(state, wert="Abschnitt 3")
    assert w.feld.value == "Abschnitt 3" and w.feld.label == "Name"
    assert _zeilen(w) == ["Behandlung", "Radfahren"]  # gewählt: alles
    assert not [c for c in w.control.controls if isinstance(c, ft.Row)]  # keine Knopfreihe
    symbole = [z.leading.icon for z in w.liste.controls if isinstance(z, ft.ListTile)]
    assert symbole == [ft.Icons.PUSH_PIN, ft.Icons.BOOKMARK_BORDER]
    _tippen(w, "rad")
    assert _zeilen(w) == ["Radfahren", "„rad“ merken"]
    _tippen(w, "Treppe")
    next(z for z in w.liste.controls if "merken" in z.title.value).on_click()
    assert hrv.gemerkt == ["Treppe"] and "Treppe" in _zeilen(w)
    kreuz = next(z.trailing for z in w.liste.controls if z.title.value == "Radfahren")
    kreuz.on_click()
    assert [n.name for n in namen] == ["Behandlung"] and "Radfahren" not in _zeilen(w)
    next(z for z in w.liste.controls if z.title.value == "Behandlung").on_click()
    assert w.text == "Behandlung"


def test_start_dialog_nimmt_den_namen_aus_der_liste_leer_gilt_die_vorgabe() -> None:
    namen = [AbschnittName(name="Behandlung Rücken")]
    state = SimpleNamespace(hrv=_hrv(namen), profil=SimpleNamespace(id="p"))
    gestartet: list[str] = []
    w = namenwahl(state, wert="Abschnitt 2")
    dialog = name_dialog(None, wahl=w, vorgabe="Abschnitt 2", starten=gestartet.append)
    next(z for z in w.liste.controls if z.title.value == "Behandlung Rücken").on_click()
    next(b for b in dialog.actions if b.content == "Start").on_click()
    asyncio.run(dialog.on_dismiss(None))
    w.feld.value = ""
    next(b for b in dialog.actions if b.content == "Start").on_click()
    asyncio.run(dialog.on_dismiss(None))
    assert gestartet == ["Behandlung Rücken", "Abschnitt 2"]


def test_vergebene_namen_werden_gemerkt_nie_die_vorgabe() -> None:
    gemerkt: list[str] = []
    state = SimpleNamespace(
        profil=SimpleNamespace(id="p"),
        hrv=SimpleNamespace(abschnittname_merken=lambda _p, n: gemerkt.append(n)),
    )
    for name in ("Radfahren (5 km)", "Abschnitt 3", "  ", "Behandlung"):
        name_merken(state, name)
    assert gemerkt == ["Radfahren", "Behandlung"]


def test_schlichtes_feld_ohne_leere_liste() -> None:
    w = Namenwahl(wert="Rad (1)")
    assert w.text == "Rad (1)" and not w.liste.visible
