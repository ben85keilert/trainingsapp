"""GPS-Vorabtest in der Oberfläche: Ansicht, Ablauf, Vordergrunddienst.

Der Ablauf (`GpsTestLauf`) läuft hier mit einem beschleunigten Simulator und
einem Stellvertreter für den Transport, der Akkuwerte liefert und mitschreibt,
was am Vordergrunddienst passiert. Läuft nur, wenn `flet` installiert ist.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.devices.gps import GpsSimulator  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.gps_test import GpsTestLauf, gps_test_view, kennzahlen  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


class Transport:
    """Stellvertreter für `FletBleTransport`: Akku sinkt um 10 µAh je simulierter Sekunde."""

    def __init__(self, quelle: GpsSimulator) -> None:
        self.quelle = quelle
        self.dienst: list[tuple[bool, str]] = []
        self.texte: list[str] = []

    async def hintergrund(self, an: bool, titel: str = "", text: str = "", *, zweck: str) -> None:
        self.dienst.append((an, zweck))

    async def hintergrund_text(self, text: str, *, zweck: str) -> None:
        self.texte.append(text)

    async def akku(self) -> dict[str, Any]:
        return {"prozent": 80, "ladung_uah": 4_000_000 - int(self.quelle.jetzt() * 10)}


def test_ansicht_laesst_sich_bauen(state) -> None:
    page = SimpleNamespace(route="/einstellungen/gps-test", views=[])
    view = gps_test_view(page, state)
    assert view.route == "/einstellungen/gps-test"
    assert state.gps_quelle is not None and state.gps_quelle.name == "Simulator"


async def test_kein_test_waehrend_eines_trainings(state) -> None:
    """Training und Test teilen die eine Ortungsquelle — der Test wartet, bis das Training endet."""
    meldungen: list = []
    page = SimpleNamespace(route="/einstellungen/gps-test", views=[], show_dialog=meldungen.append)
    state.ausdauer = SimpleNamespace(fertig=False)
    view = gps_test_view(page, state)

    def alle(c):
        yield c
        for name in ("content", "controls"):
            kind = getattr(c, name, None)
            for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
                if isinstance(k, ft.Control):
                    yield from alle(k)

    knopf = next(
        c
        for v in view.controls
        for c in alle(v)
        if isinstance(c, ft.OutlinedButton) and c.content == "Dauertest starten"
    )
    await knopf.on_click()
    assert state.gps_test is None
    assert "Ausdauertraining" in meldungen[-1].content.value


async def test_akkutest_laeuft_durch_und_berichtet(state) -> None:
    quelle = GpsSimulator(beschleunigung=2000, rauschen_m=2.0)
    state.ble_transport = Transport(quelle)
    lauf = GpsTestLauf(state, quelle, "akku", [(1.0, 120.0), (10.0, 120.0), (None, 120.0)])
    lauf.starten()
    await lauf._aufgabe  # ≈ 0,2 s echte Zeit
    assert lauf.fertig and lauf.von_selbst_fertig
    assert [ph.name for ph in lauf.phasen] == ["GPS 1 s", "GPS 10 s", "ohne GPS"]
    assert len(lauf.phasen[0].punkte) > 3 * len(lauf.phasen[1].punkte) > 0
    assert lauf.phasen[2].punkte == []
    assert all(len(ph.akku) >= 2 for ph in lauf.phasen)
    # Der Dienst wird für den Zweck „gps" beendet — eine Messung liefe weiter
    assert lauf.state.ble_transport.dienst == [(False, "gps")]
    assert "Mehrverbrauch gegenüber „ohne GPS“ (36,0 mA)" in lauf.bericht
    assert "GPS 1 s ±0,0 mA" in lauf.bericht


async def test_strecke_bis_stopp_mit_kennzahlen(state) -> None:
    quelle = GpsSimulator(beschleunigung=500)
    lauf = GpsTestLauf(state, quelle, "strecke", [(1.0, None)])
    lauf.starten()
    import asyncio

    await asyncio.sleep(0.1)  # ≈ 50 simulierte Sekunden
    werte = {w.titel: w for w in kennzahlen(lauf)}
    assert int(werte["Ortungen"].wert) > 10
    assert werte["Strecke"].einheit == "km"
    await lauf.stoppen()
    assert lauf.fertig and not lauf.von_selbst_fertig
    assert "Strecke" in lauf.bericht and "Ortungen" in lauf.bericht


async def test_vordergrunddienst_teilen_sich_messung_und_gps() -> None:
    """Endet ein Zweck, läuft der Dienst für den anderen weiter — mit passendem Typ."""
    from trainingsapp.ui.geraete.flet_ble_transport import FletBleTransport

    aufrufe: list[tuple[str, Any]] = []

    class Ble:
        async def hintergrund_starten(self, titel, text="", *, geraet=True, standort=False):
            aufrufe.append(("start", (titel, geraet, standort)))

        async def hintergrund_beenden(self):
            aufrufe.append(("ende", None))

        async def hintergrund_text(self, titel, text=""):
            aufrufe.append(("text", (titel, text)))

    transport = object.__new__(FletBleTransport)
    transport._zwecke = {}
    transport.ble = Ble()

    await transport.hintergrund(True, "HRV-Messung läuft", "H10")
    await transport.hintergrund(True, "GPS-Test läuft", "Start", zweck="gps")
    await transport.hintergrund_text("1,2 km", zweck="gps")
    await transport.hintergrund(False)
    await transport.hintergrund(False, zweck="gps")
    assert aufrufe == [
        ("start", ("HRV-Messung läuft", True, False)),
        ("start", ("Training mit Messung läuft", True, True)),
        ("text", ("Training mit Messung läuft", "H10 · 1,2 km")),
        ("start", ("GPS-Test läuft", False, True)),
        ("ende", None),
    ]
