"""Diagnosemodus, Oberfläche (Stufe 1): Karte in den Einstellungen, Sensorblatt mit Vorabtest,
roter Punkt im Overlay. Ohne Fenster — Attrappen für Seite, Messlauf und Quelle. Nur mit flet.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.hrv_einstellungen import HrvEinstellungen  # noqa: E402
from trainingsapp.devices.base import DeviceStatus, Verbindung  # noqa: E402
from trainingsapp.devices.profiles import POLAR_H10  # noqa: E402
from trainingsapp.ui.components import diagnose_punkt  # noqa: E402
from trainingsapp.ui.components.sensorblatt import (  # noqa: E402
    diagnosemodus_knopf,
    sensorblatt,
)
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.einstellungen_hrv import einstellungen_hrv  # noqa: E402

PMD = "fb005c80-02e7-f387-1cad-8acd2d8df0c8"
HR = "0000180d-0000-1000-8000-00805f9b34fb"


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/", views=[], overlay=[], platform=None, dialoge=[], aufgaben=[])
    p.update = lambda: None
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: None

    def run_task(f, *a):
        aufgabe = asyncio.get_running_loop().create_task(f(*a))
        p.aufgaben.append(aufgabe)
        return aufgabe

    p.run_task = run_task
    return p


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls", "trailing", "leading"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def texte(wurzel) -> list[str]:
    return [str(c.value) for c in alle(wurzel) if isinstance(c, ft.Text) and c.value]


class Quelle:
    """So viel `PolarQuelle`, wie das Sensorblatt liest."""

    def __init__(self) -> None:
        self.dienste = frozenset({PMD, HR})
        self.pmd_merkmale: frozenset[str] | None = None
        self.gelesen = 0

    async def merkmale_lesen(self) -> frozenset[str]:
        self.gelesen += 1
        self.pmd_merkmale = frozenset({"ecg", "acc"})
        return self.pmd_merkmale

    async def einstellungen_abfragen(self) -> None:
        return None


class Lauf:
    """So viel `Messlauf`, wie Sensorblatt, Knopf und Punkt brauchen."""

    def __init__(self) -> None:
        self.quelle = Quelle()
        self.profil = POLAR_H10
        self.geraet_name = "Polar H10 TEST"
        self.status = DeviceStatus(verbindung=Verbindung.VERBUNDEN, batterie_prozent=88)
        self.verbunden = True
        self.aufnahme: Any = None
        self.diagnose_moeglich = True
        self.diagnose_aktiv = False
        self.vorgemerkt: dict[str, Any] | None = None
        self.test: list[tuple[bool, Any]] = []
        self.abgebrochen = 0

    async def vorabtest_beginnen(self, *, ekg, acc) -> None:
        self.test.append((ekg, acc))

    def vorabtest_stand(self, *, ekg, acc) -> dict[str, Any]:
        stroeme = {"hr": {"rate": 1.0, "soll": 1.0, "ok": True}}
        if ekg:
            stroeme["ecg"] = {"rate": 130.0, "soll": 130.0, "ok": True}
        if acc:
            stroeme["acc"] = {"rate": 0.0, "soll": float(acc[0]), "ok": False}
        return {"seit_s": 20.0, "fertig": True, "stroeme": stroeme}

    async def vorabtest_abbrechen(self) -> None:
        self.abgebrochen += 1

    def diagnose_vormerken(self, *, ekg, acc, kopf=None) -> None:
        self.vorgemerkt = {"ekg": ekg, "acc": acc, "kopf": kopf}
        self.diagnose_aktiv = True

    def diagnose_stand(self) -> dict[str, Any]:
        return {"seit_s": 3, "bytes": 1000, "zeilen": 10, "stroeme": {}, "akku": 88}

    async def diagnose_beenden(self) -> None:
        self.diagnose_aktiv = False


def test_karte_in_den_einstellungen_und_schalter(page, state) -> None:
    ansicht = einstellungen_hrv(page, state)
    alles = " ".join(texte(ansicht))
    assert "Diagnosemodus" in alles and "keine Mitschnitte" in alles
    schalter = {s.label: s for s in alle(ansicht) if isinstance(s, ft.Switch)}
    knopf = schalter["Diagnosemodus anbieten"]
    assert knopf.value is False
    knopf.on_change(SimpleNamespace(control=SimpleNamespace(value=True)))
    assert state.hrv_einstellungen().diagnose_anbieten is True


def test_praxis_edition_hat_die_karte_auch(page, state, monkeypatch) -> None:
    monkeypatch.setenv("TRAININGSAPP_EDITION", "praxis")
    assert "Diagnosemodus anbieten" in {
        s.label for s in alle(einstellungen_hrv(page, state)) if isinstance(s, ft.Switch)
    }


def test_knopf_nur_wenn_angeboten_und_moeglich(page, state) -> None:
    lauf = Lauf()

    async def starten() -> None:
        return None

    assert diagnosemodus_knopf(page, state, lauf, aufnahme_starten=starten).visible is False
    e = state.hrv_einstellungen()
    e.diagnose_anbieten = True
    state.hrv_einstellungen_setzen(e)
    assert diagnosemodus_knopf(page, state, lauf, aufnahme_starten=starten).visible is True
    lauf.diagnose_moeglich = False  # Simulator ohne mithörenden Transport
    assert diagnosemodus_knopf(page, state, lauf, aufnahme_starten=starten).visible is False


async def test_sensorblatt_liest_merkmale_testet_und_startet(page, state) -> None:
    lauf = Lauf()
    gestartet: list[bool] = []

    async def aufnahme_starten() -> None:
        gestartet.append(True)
        lauf.aufnahme = object()

    blatt = sensorblatt(page, state, lauf, aufnahme_starten=aufnahme_starten)
    vorher = " ".join(texte(blatt))
    assert "laut Profil" in vorher  # vor dem Lesen gilt das Profil
    await asyncio.gather(*page.aufgaben)
    nachher = " ".join(texte(blatt))
    assert lauf.quelle.gelesen == 1 and "✓ geprüft" in nachher
    assert lauf.test == [(True, (200, 8))]
    assert "es fehlt Beschleunigung" in nachher  # der Vorabtest nennt, was nicht kam
    assert "Hat dieses Gerät nicht: PPI, PPG" in nachher
    # EKG ausschalten: Einstellung gemerkt, Vorabtest neu
    ekg = next(s for s in alle(blatt) if isinstance(s, ft.Switch) and s.value and s.on_change)
    ekg.on_change(SimpleNamespace(control=SimpleNamespace(value=False)))
    await asyncio.gather(*page.aufgaben)
    assert state.hrv_einstellungen().diagnose_ekg is False and lauf.test[-1] == (False, (200, 8))
    # Starten: vorgemerkt, Aufnahme gestartet, Punkt im Overlay
    start = next(c for c in alle(blatt) if isinstance(c, ft.FilledButton))
    await start.on_click()
    assert gestartet == [True] and lauf.vorgemerkt is not None
    assert lauf.vorgemerkt["acc"] == (200, 8) and lauf.vorgemerkt["ekg"] is False
    assert lauf.vorgemerkt["kopf"]["marken"]["leiste"] == "unten"
    state.messlauf = lauf
    diagnose_punkt.aktualisieren(page, state)
    assert len(page.overlay) == 1 and state.diagnose_punkt is page.overlay[0]
    diagnose_punkt.aktualisieren(page, state)  # idempotent
    assert len(page.overlay) == 1


async def test_blatt_zu_ohne_start_stellt_die_stroeme_zurueck(page, state) -> None:
    lauf = Lauf()

    async def aufnahme_starten() -> None:
        raise AssertionError("darf nicht starten")

    blatt = sensorblatt(page, state, lauf, aufnahme_starten=aufnahme_starten)
    await asyncio.gather(*page.aufgaben)
    blatt.on_dismiss(None)
    await asyncio.gather(*page.aufgaben)
    assert lauf.abgebrochen == 1 and lauf.vorgemerkt is None


async def test_punkt_geht_mit_dem_ende_der_diagnose(page, state) -> None:
    lauf = Lauf()
    lauf.diagnose_aktiv = True
    state.messlauf = lauf
    diagnose_punkt.aktualisieren(page, state)
    assert len(page.overlay) == 1
    blatt = diagnose_punkt.stand_blatt(page, state)
    assert any("seit 3 s" in t for t in texte(blatt))
    beenden = next(c for c in alle(blatt) if isinstance(c, ft.FilledTonalButton))
    await beenden.on_click()
    assert not lauf.diagnose_aktiv and page.overlay == [] and state.diagnose_punkt is None


def test_einstellungen_runden_reise() -> None:
    e = HrvEinstellungen(diagnose_anbieten=True, diagnose_leiste="knopf", diagnose_acc_hz=50)
    zurueck = HrvEinstellungen.aus_dict(e.als_dict())
    assert zurueck == e
    kaputt = HrvEinstellungen.aus_dict({"diagnose_leiste": "seitlich", "diagnose_acc_hz": 33})
    assert kaputt.diagnose_leiste == "unten" and kaputt.diagnose_acc_hz == 200


async def test_auswertung_zeigt_diagnose_und_marken_als_ebene(page, state, tmp_path) -> None:
    from hrv_core import mitschnitt as mt
    from hrv_core.recording import Beat, Recording, speichern

    from trainingsapp.core.models import HrvRecording
    from trainingsapp.ui.views.messung_detail import messung_detail_view

    beats, t = [], 0.0
    for i in range(120):
        t += 0.8
        beats.append(Beat(t_s=round(t, 3), rr_ms=800 + (i % 3), hf_bpm=75, t_wall_s=round(t, 3)))
    rec = Recording(beats=beats, geraet="Polar H10 TEST", geraet_profil="polar_h10")
    pfad = speichern(rec, tmp_path / "Messungen" / "PolarH10")
    s = mt.Schreiber(mt.mitschnitt_pfad(pfad), {"aufnahme": {"start_mono_ns": 0}}, uhr_ns=lambda: 0)
    for k in range(3):
        s.marke(mt.MARKE_WDH, nr=k + 1, t=(10 + 2 * k) * 10**9)
    s.marke(mt.MARKE_STOERUNG, t=30 * 10**9)
    s.schliessen()
    eintrag = HrvRecording(
        subject_id=state.profil.id,
        file_path=pfad.relative_to(tmp_path / "Messungen").as_posix(),
        geraet="Polar H10 TEST",
        geraet_profil="polar_h10",
    )
    state.hrv.anlegen(eintrag)
    page.web = False
    ansicht = messung_detail_view(page, state, eintrag)
    # Die Ansicht füllt sich in Aufgaben, die weitere starten (EKG, Diagnose) — abwarten
    erledigt = 0
    while erledigt < len(page.aufgaben):
        erledigt = len(page.aufgaben)
        await asyncio.gather(*page.aufgaben)
    alles = " ".join(texte(ansicht))
    assert "4 Marken (Wdh 3, Störung 1)" in alles
    knoepfe = [
        c
        for c in alle(ansicht)
        if isinstance(c, ft.OutlinedButton) and c.content == "Diagnosepaket teilen"
    ]
    assert len(knoepfe) == 1


class LeistenLauf(Lauf):
    """Mit Notizen und einem Mitschnitt, der die Marken sammelt."""

    def __init__(self) -> None:
        super().__init__()
        self.diagnose_aktiv = True
        self.notizen: list[dict] = []
        self.marken: list[dict] = []
        self.weg: list[int] = []

    def ereignisse(self) -> list[dict]:
        return self.notizen

    def marke(self, typ, **felder):
        zeile = {"art": "marke", "id": len(self.marken) + 1, "typ": typ, **felder}
        self.marken.append(zeile)
        return zeile

    def marke_weg(self, marke_id, **felder):
        self.weg.append(marke_id)
        return {"art": "marke_weg", "id": marke_id}


async def test_marken_leiste_art_aus_dem_kontext_chip_rueckgaengig_stoerung(page, state) -> None:
    from trainingsapp.core.kurzcode import kurzcode
    from trainingsapp.core.models import Exercise
    from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    from trainingsapp.ui.components import marken_leiste as ml

    uebung = Exercise(name="Kniebeuge", result_spec=SPEC_SAETZE_WDH)
    state.uebungen.speichern(uebung)
    lauf = LeistenLauf()
    state.messlauf = lauf
    ml.aktualisieren(page, state)
    assert len(page.overlay) == 1
    # Ohne Übung: Atemzug
    ml.tippen(page, state)
    assert lauf.marken[-1]["typ"] == "atem" and lauf.marken[-1]["nr"] == 1
    # Übung mit Wiederholungen beginnt: Wiederholung, Zählung je Satz ab 1
    lauf.notizen.append(
        {
            "text": "Kniebeuge: Start",
            "uebungen": [kurzcode(uebung.id)],
            "marke": {"quelle": "plan", "art": "uebung_start", "name": "Kniebeuge"},
        }
    )
    ml.tippen(page, state)
    ml.tippen(page, state)
    assert [(m["typ"], m["nr"]) for m in lauf.marken[1:]] == [("wdh", 1), ("wdh", 2)]
    assert lauf.marken[-1]["kontext"] == {
        "phase": "uebung",
        "uebung": "Kniebeuge",
        "uebung_id": kurzcode(uebung.id),
        "satz": 1,
    }
    stand = state.diagnose_leiste
    assert stand.zahl.value == "2" and stand.kopf.value == "Wiederholung · Kniebeuge S1"
    # ↶: die letzte zurück, die Zahl folgt
    ml.zuruecknehmen(page, state)
    assert lauf.weg == [3] and stand.zahl.value == "1"
    # Chip „Atem“ gilt, bis sich der Kontext ändert (neuer Satz)
    ml.art_waehlen(state, "atem")
    ml.tippen(page, state)
    assert lauf.marken[-1]["typ"] == "atem"
    lauf.notizen.append({"marke": {"quelle": "person", "art": "leistung", "feld": "reps"}})
    ml.tippen(page, state)
    assert (lauf.marken[-1]["typ"], lauf.marken[-1]["nr"]) == ("wdh", 1)
    assert lauf.marken[-1]["kontext"]["satz"] == 2
    # Störung: eine eigene Marke ohne Nummer, die Zählung bleibt
    ml.tippen(page, state, "stoerung")
    assert lauf.marken[-1]["typ"] == "stoerung" and lauf.marken[-1]["nr"] is None
    # Einklappen: der schwebende Knopf ersetzt die Leiste; die Ansicht bekommt weniger Platz
    hoch = ml.platz(page, state)
    state.diagnose_leiste_offen = False
    ml.aktualisieren(page, state)
    assert len(page.overlay) == 1 and ml.platz(page, state) < hoch
    # Ende der Diagnose: weg, und die nächste Diagnose zählt neu
    lauf.diagnose_aktiv = False
    ml.aktualisieren(page, state)
    assert page.overlay == [] and state.diagnose_leiste is None
