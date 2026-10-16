"""Einstellungen der HRV-Messung: Vorgaben, Speichern, Zurücksetzen, Ansicht."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from hrv_core.regeln import Korrekturregeln

from trainingsapp.core.hrv_ansicht import Ansicht
from trainingsapp.core.hrv_einstellungen import (
    STANDARD_KACHELN,
    HrvEinstellungen,
    einstellungen_lesen,
)


def test_vorgaben_und_bereiche() -> None:
    e = HrvEinstellungen()
    assert e.kacheln == list(STANDARD_KACHELN) and e.messung_anzeigen
    assert e.gross == ["hf", "rr"] and e.darstellung == "uebersicht" and not e.atemuebung
    # Für Laien: nur der Zeitbereich — Frequenz und Nichtlinear schaltet man ein
    assert e.bereiche(optisch=False) == ["zeit"]
    e.frequenz = e.nichtlinear = True
    assert e.bereiche(optisch=False) == ["zeit", "frequenz", "nichtlinear"]
    assert e.bereiche(optisch=True) == ["zeit", "frequenz"]  # Verity: nicht empfohlen
    e.nichtlinear_optisch = True
    assert e.bereiche(optisch=True) == ["zeit", "frequenz", "nichtlinear"]
    e.frequenz = e.nichtlinear = False
    assert e.bereiche(optisch=False) == ["zeit"]
    assert einstellungen_lesen("{kaputt") == HrvEinstellungen()
    assert einstellungen_lesen('{"kacheln": ["hf", "hf", "rr"]}').kacheln == ["hf", "rr"]


def test_zustand_speichert_und_setzt_zurueck(tmp_path) -> None:
    from trainingsapp.ui.state import AppState

    state = AppState.starten(tmp_path / "app.db")
    try:
        e = state.hrv_einstellungen()
        e.messung_anzeigen, e.kacheln, e.fenster_s = False, ["hf"], 300
        state.hrv_einstellungen_setzen(e)
        state.ansicht_setzen(Ansicht("Eigen", ["rmssd"]))
        state.ansicht_speichern(Ansicht("Eigen", ["rmssd"]))
        state.korrekturregeln_setzen(Korrekturregeln(malik=0.4))
    finally:
        state.schliessen()
    state = AppState.starten(tmp_path / "app.db")
    try:
        assert state.hrv_einstellungen() == e
        state.hrv_zuruecksetzen()
        assert state.hrv_einstellungen() == HrvEinstellungen()
        assert state.ansicht() == Ansicht()
        assert state.korrekturregeln() == Korrekturregeln()
        assert [a.name for a in state.ansichten()] == ["Eigen"]  # Arbeit des Nutzers bleibt
    finally:
        state.schliessen()


def test_einstellungsseiten_bauen_und_schalten(tmp_path) -> None:
    ft = pytest.importorskip("flet")
    from trainingsapp.ui.state import AppState
    from trainingsapp.ui.views.einstellungen import einstellungen
    from trainingsapp.ui.views.einstellungen_hrv import einstellungen_hrv

    state = AppState.starten(tmp_path / "app.db")
    dialoge: list = []
    seite = SimpleNamespace(
        route="/einstellungen/hrv",
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
    )
    try:
        assert einstellungen(seite, state).route == "/einstellungen"
        ansicht = einstellungen_hrv(seite, state)
        assert ansicht.route == "/einstellungen/hrv"

        def alle(x, gesehen=None):
            gesehen = gesehen if gesehen is not None else set()
            if not isinstance(x, ft.Control) or id(x) in gesehen:
                return []
            gesehen.add(id(x))
            out = [x]
            for name in ("controls", "content", "title", "subtitle", "leading", "trailing"):
                wert = getattr(x, name, None)
                for k in wert if isinstance(wert, list) else [wert]:
                    out += alle(k, gesehen)
            return out

        controls = alle(ansicht)
        schalter = next(
            c for c in controls if isinstance(c, ft.Switch) and "Reiter" in str(c.label)
        )
        schalter.on_change(SimpleNamespace(control=SimpleNamespace(value=False)))
        assert not state.hrv_einstellungen().messung_anzeigen
        # Hinzufügen per Chip, groß per Stern, umordnen, entfernen
        chip = next(
            c
            for c in controls
            if isinstance(c, ft.Chip) and getattr(c.label, "value", "") == "DFA α1"
        )
        chip.on_click()
        assert state.hrv_einstellungen().kacheln[-1] == "dfa_alpha1"
        liste = next(c for c in alle(ansicht) if isinstance(c, ft.ReorderableListView))
        sterne = [
            c
            for c in alle(liste)
            if isinstance(c, ft.IconButton) and c.icon in (ft.Icons.STAR, ft.Icons.STAR_BORDER)
        ]
        sterne[-1].on_click()  # DFA α1 groß
        assert "dfa_alpha1" in state.hrv_einstellungen().gross
        letzte = len(state.hrv_einstellungen().kacheln) - 1
        liste.on_reorder(SimpleNamespace(old_index=letzte, new_index=0))
        assert state.hrv_einstellungen().kacheln[0] == "dfa_alpha1"
        weg = next(
            c
            for c in alle(liste.controls[0])
            if isinstance(c, ft.IconButton) and c.icon == ft.Icons.CLOSE
        )
        weg.on_click()
        assert "dfa_alpha1" not in state.hrv_einstellungen().kacheln
        zurueck = next(
            c
            for c in controls
            if isinstance(c, ft.OutlinedButton) and "zurücksetzen" in str(c.content)
        )
        zurueck.on_click()
        dialoge[-1].actions[-1].on_click()  # „Zurücksetzen" bestätigen
        assert state.hrv_einstellungen() == HrvEinstellungen()
    finally:
        state.schliessen()
