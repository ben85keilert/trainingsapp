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
        assert einstellungen(seite, state, ft.UrlLauncher()).route == "/einstellungen"
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
        # EKG-Rohsignal (Ben, 30.10.2026): standardmäßig aus, Schalter stellt es an
        ekg = next(
            c for c in controls if isinstance(c, ft.Switch) and c.label == "EKG mitschreiben"
        )
        assert ekg.value is False and not state.hrv_einstellungen().ekg_mitschreiben
        ekg.on_change(SimpleNamespace(control=SimpleNamespace(value=True)))
        assert state.hrv_einstellungen().ekg_mitschreiben is True
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
        # Zeitfenster live: dieselben Knöpfe wie an der Kurve, jede andere Breite
        # eingetippt (Ben, 21.10.2026) — auch über den Knöpfen hinaus, bis 30 min
        knoepfe = next(
            c
            for c in controls
            if isinstance(c, ft.SegmentedButton) and any(s.value == "600" for s in c.segments)
        )
        assert [s.label.value for s in knoepfe.segments] == ["1 Min", "2 Min", "10 Min"]
        # Knopfsätze (Ben, 30.10.2026): Kurz 1·2·10, Mittel 2·5·15, Lang 1·3·6 h, Eigene
        satz = next(
            c
            for c in controls
            if isinstance(c, ft.SegmentedButton) and any(s.value == "lang" for s in c.segments)
        )
        assert [s.label.value for s in satz.segments] == ["Kurz", "Mittel", "Lang", "Eigene"]
        satz.on_change(SimpleNamespace(control=SimpleNamespace(selected=["mittel"])))
        assert state.hrv_einstellungen().breiten() == (120, 300, 900)
        assert [s.label.value for s in knoepfe.segments] == ["2 Min", "5 Min", "15 Min"]
        satz.on_change(SimpleNamespace(control=SimpleNamespace(selected=["lang"])))
        assert state.hrv_einstellungen().breiten() == (3600, 10800, 21600)
        assert [s.label.value for s in knoepfe.segments] == ["1 h", "3 h", "6 h"]
        eigene = next(
            c for c in controls if isinstance(c, ft.TextField) and c.label == "Eigene Breiten"
        )
        satz.on_change(SimpleNamespace(control=SimpleNamespace(selected=["eigen"])))
        assert state.hrv_einstellungen().breiten_satz == "lang"  # noch keine eigenen
        eigene.value = "2, 30, 6 h"
        eigene.on_submit(None)
        assert state.hrv_einstellungen().breiten() == (120, 1800, 21600)
        assert [s.label.value for s in knoepfe.segments] == ["2 Min", "30 Min", "6 h"]
        eigene.value = "abc"
        eigene.on_submit(None)
        assert eigene.error and state.hrv_einstellungen().breiten() == (120, 1800, 21600)
        satz.on_change(SimpleNamespace(control=SimpleNamespace(selected=["kurz"])))
        feld = next(
            c for c in controls if isinstance(c, ft.TextField) and c.label == "Breite der Zeitachse"
        )
        feld.value = "3:30"
        feld.on_submit(None)
        assert state.hrv_einstellungen().fenster_s == 210 and knoepfe.selected == []
        feld.value = "90 min"  # mehr hält der Live-Puffer nicht
        feld.on_blur(None)
        assert state.hrv_einstellungen().fenster_s == 1800 and feld.value == "30:00"
        feld.value = "viel"
        feld.on_submit(None)
        assert feld.error and state.hrv_einstellungen().fenster_s == 1800
        knoepfe.on_change(SimpleNamespace(control=SimpleNamespace(selected=["300"])))
        assert state.hrv_einstellungen().fenster_s == 300 and feld.value == "5:00"
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


def test_live_verlauf_einstellbar(tmp_path) -> None:
    """„Live-Verlauf behalten“ (Ben, 26.10.2026): 30 min · 1 h · 2 h · 4 h — die Zeitachse
    darf nie breiter sein als der Puffer."""
    ft = pytest.importorskip("flet")
    from trainingsapp.ui.state import AppState
    from trainingsapp.ui.views.einstellungen_hrv import einstellungen_hrv

    state = AppState.starten(tmp_path / "app.db")
    seite = SimpleNamespace(
        route="/einstellungen/hrv",
        update=lambda: None,
        show_dialog=lambda *_: None,
        pop_dialog=lambda: None,
    )
    try:
        ansicht = einstellungen_hrv(seite, state)

        def alle(x, gesehen=None):
            gesehen = gesehen if gesehen is not None else set()
            if not isinstance(x, ft.Control) or id(x) in gesehen:
                return []
            gesehen.add(id(x))
            out = [x]
            for name in ("controls", "content"):
                wert = getattr(x, name, None)
                for k in wert if isinstance(wert, list) else [wert]:
                    out += alle(k, gesehen)
            return out

        controls = alle(ansicht)
        wahl = next(
            c for c in controls if isinstance(c, ft.Dropdown) and c.label == "Live-Verlauf behalten"
        )
        assert [o.text for o in wahl.options] == ["30 min", "1 h", "2 h", "4 h", "6 h", "12 h"]
        feld = next(
            c for c in controls if isinstance(c, ft.TextField) and c.label == "Breite der Zeitachse"
        )
        wahl.on_select(SimpleNamespace(control=SimpleNamespace(value="7200")))
        assert state.hrv_einstellungen().puffer_s == 7200
        feld.value = "90 min"  # jetzt möglich — der Puffer hält 2 h
        feld.on_submit(None)
        assert state.hrv_einstellungen().fenster_s == 5400 and feld.value == "90:00"
        wahl.on_select(SimpleNamespace(control=SimpleNamespace(value="1800")))
        e = state.hrv_einstellungen()
        assert (e.puffer_s, e.fenster_s) == (1800, 1800)  # die Breite rückt an den Puffer
    finally:
        state.schliessen()


def test_werteachsen_standard_in_den_einstellungen(tmp_path) -> None:
    """Ben, 30.10.2026: Standardwerte der Werteachsen (ganzer Bereich) stehen in den
    Einstellungen, sind nachstellbar und auf die Vorgabe zurücksetzbar."""
    ft = pytest.importorskip("flet")
    from trainingsapp.ui.state import AppState
    from trainingsapp.ui.views.einstellungen_hrv import einstellungen_hrv

    state = AppState.starten(tmp_path / "app.db")
    seite = SimpleNamespace(
        route="/einstellungen/hrv", update=lambda: None, show_dialog=lambda d: None
    )
    try:
        ansicht = einstellungen_hrv(seite, state)

        def alle(x, gesehen=None):
            gesehen = gesehen if gesehen is not None else set()
            if not isinstance(x, ft.Control) or id(x) in gesehen:
                return []
            gesehen.add(id(x))
            out = [x]
            for name in ("controls", "content"):
                wert = getattr(x, name, None)
                for k in wert if isinstance(wert, list) else [wert]:
                    out += alle(k, gesehen)
            return out

        controls = alle(ansicht)
        rr = next(
            c
            for c in controls
            if isinstance(c, ft.Row)
            and any(isinstance(t, ft.Text) and t.value == "RR bzw. PPI" for t in alle(c))
        )
        von, bis = (c for c in alle(rr) if isinstance(c, ft.TextField))
        assert (von.value, bis.value) == ("300", "1500")
        von.value = "500"
        von.on_submit(None)
        assert state.hrv_einstellungen().achse_standard("rr") == (500.0, 1500.0)
        bis.value = "400"  # unter „von“: bleibt, Hinweis am Feld
        bis.on_submit(None)
        assert von.error and state.hrv_einstellungen().achse_standard("rr") == (500.0, 1500.0)
        vorgabe = next(
            c for c in controls if isinstance(c, ft.TextButton) and c.content == "Auf Vorgabe"
        )
        vorgabe.on_click()
        assert state.hrv_einstellungen().achse_standard("rr") == (300.0, 1500.0)
        assert (von.value, bis.value) == ("300", "1500") and not von.error
    finally:
        state.schliessen()
