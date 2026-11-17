"""Der Testlauf eines Kurses (Ben, 16.11.2026, `docs/plan_kurs_ablauf.md` §3.3, Skizzen T1–T4):
Ein Test mit Vorgabe läuft mit der Uhr — Testkarte im Kapitel, Lauf, Ergebnis, ein eigener
abgeschlossener Eintrag, zurück im Kapitel. Läuft nur mit `flet`.

**Alles auf der Uhr der Attrappen:** Die HRV-Aufnahme läuft auf ihr (so wird sie die Uhr der
Einheit), und die Einheit bekommt auch ihre Wanduhr (heute 10:00) statt der echten. Das Kapitel
gilt als eine Stunde davor erreicht — so hängt kein Test an der Tageszeit des Laufs (Katalog
N170).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from functools import partial
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import UTC0, Gurt, Seite, Uhr, ruhe, vorbei  # noqa: E402
from trainingsapp.core.kursbloecke import (  # noqa: E402
    ANTEIL,
    AUSWAHL,
    GANZ,
    HAND,
    MENGE,
    PLAN_UEBUNG,
    SKALA,
    TEST,
    ZEIT,
    Block,
    Vorgabe,
)
from trainingsapp.core.kurse import (  # noqa: E402
    Kapitel,
    Kurs,
    Kursplan,
    PlanVorlage,
    VorlageItem,
)
from trainingsapp.core.models import Exercise, lokaler_tag  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.takt import VORLAGEN  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerProfil, stoppuhr  # noqa: E402
from trainingsapp.devices.einheit import Einheitslauf  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.ui import einheit as einheit_ui  # noqa: E402
from trainingsapp.ui import uebung_lauf  # noqa: E402
from trainingsapp.ui.components.fokus import FOKUS_ANSICHT  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views import kurs_testlauf as kurs_test  # noqa: E402
from trainingsapp.ui.views.kurs_testlauf import ERGEBNIS, LAEUFT, kurs_test_view  # noqa: E402
from trainingsapp.ui.views.kurse import kapitel_view  # noqa: E402

#: Das Kapitel gilt als eine Stunde vor der Uhr der Attrappen erreicht
SEIT = UTC0 - timedelta(hours=1)


class Ton:
    """Der Tondienst: merkt, was gespielt wurde."""

    def __init__(self) -> None:
        self.gespielt: list[str] = []

    async def spielen(self, klang: str, *_a) -> None:
        self.gespielt.append(klang)


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    """App-Zustand, eine laufende HRV-Aufnahme auf der Uhr der Attrappen und eine Seite, die
    Routen und Meldungen merkt. Die Einheit läuft ganz auf dieser Uhr (Modul-Docstring)."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    # „Heute“ der App ist der Tag der Attrappen-Uhr: Sie wird beim Laden der Tests gestellt
    # (`attrappen.UTC0`, heute 10:00) — läuft die Sitzung über Mitternacht, läge sie sonst am
    # Vortag, und kein Eintrag wäre „von heute“ (Katalog N177: 15 rote Tests, 17.11.2026)
    monkeypatch.setattr(AppState, "heute", staticmethod(lambda: lokaler_tag(UTC0)))
    uhr = Uhr()
    monkeypatch.setattr(einheit_ui, "Einheitslauf", partial(Einheitslauf, jetzt_utc=uhr.utc))
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    seite = Seite()
    yield SimpleNamespace(state=state, uhr=uhr, gurt=gurt, seite=seite)
    state.kurs_test = None  # der Wächter eines Laufs, der noch wartet, hört damit auf
    for aufgabe in seite.aufgaben:
        if not aufgabe.done():
            aufgabe.cancel()
    await asyncio.gather(*seite.aufgaben, return_exceptions=True)
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


# -- Helfer ------------------------------------------------------------------------------


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "title",
        "subtitle",
        "leading",
        "trailing",
        "label",
        "actions",
        "appbar",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [str(x.value) for x in _alle(c) if isinstance(x, ft.Text | ft.Markdown) and x.value]


def _daten(c, wert):
    gefunden = [x for x in _alle(c) if getattr(x, "data", None) == wert]
    if not gefunden:
        raise AssertionError(f"kein Control mit data={wert!r}")
    return gefunden[0]


def _hat(c, wert) -> bool:
    return any(getattr(x, "data", None) == wert for x in _alle(c))


async def klick(control) -> None:
    """Tippen wie Flet: Der Handler bekommt das Ereignis (Katalog N168)."""
    ergebnis = control.on_click(SimpleNamespace(control=control))
    if asyncio.iscoroutine(ergebnis):
        await ergebnis


def _kurs(state, vorgabe: Vorgabe | None, *, uebung: str = "Käfer", feld: str = "reps"):
    """Ein Kurs mit einem Kapitel und einem Test bei ``uebung`` — erreicht eine Stunde vor
    der Uhr der Attrappen."""
    uebungen = {
        name: Exercise(name=name, result_spec=ResultSpec(fields=[vorrat_feld(f)]))
        for name, f in (("Käfer", "reps"), ("Planke", "hold"), ("Brücke", "reps"))
    }
    for u in uebungen.values():
        state.uebungen.speichern(u)
    test = Block(TEST, id="test", uebung=uebungen[uebung].id, feld=feld, vorgabe=vorgabe)
    kurs = Kurs(name="Rumpf-Kurs", kapitel=[Kapitel(titel="Erweiterung", bloecke=[test])])
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    kapitel = kurs.kapitel[0]
    _erreichen(state, kurs, kapitel)
    return kurs, kapitel, kapitel.bloecke[0], state.uebungen.laden(uebungen[uebung].id)


def _erreichen(state, kurs, kapitel) -> None:
    state.kurse.kapitel_erreichen(kurs, kapitel, state.profil.id)
    state.kurse.con.execute(
        "UPDATE course_progress SET reached_at = ? WHERE chapter_id = ?",
        (SEIT.isoformat(), kapitel.id),
    )


async def _sekunden(u, n: int, *, beschleunigung: bool = False) -> None:
    """``n`` Sekunden auf der Uhr der Attrappen: Schlag, ein Takt der Einheit."""
    for _ in range(n):
        u.uhr.t += 1
        u.gurt.schlag(1000)
        if beschleunigung:
            u.gurt.beschleunigung()
        await ruhe()
        e = u.state.einheit
        if e is not None and e.laeuft:
            e.takt()


async def _bis_vorbei(u) -> None:
    for _ in range(400):
        if vorbei(u.state):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Die Einheit endete nicht")


def _kapitel(u, kurs, kapitel) -> ft.View:
    browser = SimpleNamespace()
    return kapitel_view(u.seite, u.state, u.state.kurse.laden(kurs.id), kapitel, browser)


def _ansicht(u, kurs, kapitel, block, uebung) -> ft.View:
    return kurs_test_view(u.seite, u.state, kurs, kapitel, block, uebung)


def _laeufe(state, uebung):
    """„Läufe heute“ am Tag der Attrappen-Uhr — nicht am echten Heute (Katalog N177)."""
    return uebung_lauf.laeufe_heute(state, uebung.id, lokaler_tag(UTC0))


def _eintraege(state, uebung):
    return [
        e
        for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
        if e.exercise_id == uebung.id
    ]


async def _starten(u, kurs, kapitel) -> None:
    """„Test starten“ auf der Testkarte im Kapitel."""
    await klick(_daten(_kapitel(u, kurs, kapitel), ("test_starten", "test")))


# -- Testkarte im Kapitel ----------------------------------------------------------------


async def test_karte_mit_vorgabe_startet_den_testlauf(umgebung) -> None:
    """Mit Vorgabe nennt die Karte Übung und Vorgabe, der Knopf heißt „Test starten“ und
    öffnet den Testlauf. Der Aufbau der Ansichten startet nichts — erst der Tipp."""
    u = umgebung
    kurs, kapitel, block, kaefer = _kurs(u.state, Vorgabe(MENGE, 30))
    ansicht = _kapitel(u, kurs, kapitel)
    texte = _texte(ansicht)
    assert "Käfer: 30 Wiederholungen" in texte
    assert (
        "Mach 30 am Stück. Die App misst die Zeit, du sagst danach, wie anstrengend es war."
        in texte
    )
    assert "Noch kein Test, seit du dieses Kapitel öffnest." in texte
    knopf = _daten(ansicht, ("test_starten", "test"))
    assert knopf.content == "Test starten" and not _hat(ansicht, ("test_oeffnen", "test"))
    # Auch die Ansicht des Testlaufs startet nichts: Sie ist bereit
    bereit = _ansicht(u, kurs, kapitel, block, kaefer)
    assert u.state.einheit is None and u.state.kurs_test is None
    assert bereit.data is None and _daten(bereit, "test_start").content == "Start"
    assert bereit.appbar.title.value == "Test · Käfer" and bereit.appbar.leading is None
    await klick(knopf)
    assert u.state.einheit is not None and u.state.einheit.laeuft
    assert u.seite.route == f"/kurse/{kurs.id}/{kapitel.id}/test/test/{kaefer.id}"
    assert u.state.kurs_test.phase == LAEUFT
    # Solange er läuft, führt die Karte zum Test — ein zweiter Tipp startet keinen zweiten
    einheit = u.state.einheit
    laufend = _daten(_kapitel(u, kurs, kapitel), ("test_starten", "test"))
    assert laufend.content == "Zum Test"
    await klick(laufend)
    assert u.state.einheit is einheit
    assert not _eintraege(u.state, kaefer)


async def test_ohne_vorgabe_bleibt_die_karte(umgebung) -> None:
    """Ein Test ohne Vorgabe ist wie bisher: „… was schaffst du?“ und „Zur Übung“."""
    u = umgebung
    kurs, kapitel, _, _ = _kurs(u.state, None, uebung="Planke", feld="hold")
    ansicht = _kapitel(u, kurs, kapitel)
    assert "Planke: was schaffst du?" in _texte(ansicht)
    assert _daten(ansicht, ("test_oeffnen", "test")).content == "Zur Übung"
    assert not _hat(ansicht, ("test_starten", "test"))


async def test_route_nur_fuer_tests_mit_vorgabe(umgebung) -> None:
    u = umgebung
    kurs, kapitel, block, kaefer = _kurs(u.state, Vorgabe(MENGE, 30))
    route = kurs_test.route_zum_test(kurs.id, kapitel.id, block.id, kaefer.id).split("/")[4:]
    assert route == ["test", "test", kaefer.id]
    gefunden = kurs_test.aus_route(u.state, kurs, kapitel, route)
    assert gefunden is not None and gefunden[0].id == "test" and gefunden[1].id == kaefer.id
    planke = next(x for x in u.state.uebungen.alle() if x.name == "Planke")
    assert kurs_test.aus_route(u.state, kurs, kapitel, ["test", "test", planke.id]) is None
    assert kurs_test.aus_route(u.state, kurs, kapitel, ["test", "fehlt", kaefer.id]) is None
    assert kurs_test.aus_route(u.state, kurs, kapitel, []) is None
    block.vorgabe = None  # ohne Vorgabe gibt es keinen Testlauf
    assert kurs_test.aus_route(u.state, kurs, kapitel, route) is None


class AppSeite:
    """Gerade so viel `ft.Page`, wie `app.main` braucht (wie in ``test_ui_navigation``)."""

    def __init__(self) -> None:
        self.route = "/"
        self.views: list[ft.View] = []
        self.services: list = []
        self.dialoge: list = []
        self.platform = ft.PagePlatform.LINUX
        self.platform_brightness = ft.Brightness.LIGHT
        self.title = ""
        self.padding = 0
        self.theme = self.dark_theme = self.theme_mode = None
        self.bgcolor = None
        self.on_route_change = self.on_view_pop = None
        self.on_platform_brightness_change = self.on_resize = None
        self.on_app_lifecycle_state_change = None

    def update(self) -> None:
        pass

    def run_task(self, *_a, **_k) -> None:
        pass

    def show_dialog(self, dialog) -> None:
        self.dialoge.append(dialog)

    def pop_dialog(self) -> None:
        pass

    async def push_route(self, route: str) -> None:
        self.route = route
        self.on_route_change()

    def routen(self) -> list[str]:
        return [str(v.route) for v in self.views]


def test_route_legt_den_testlauf_ueber_kurs_und_kapitel(tmp_path, monkeypatch) -> None:
    """`app.main`: Aus der Route allein (Start auf der tiefen Route) liegt der Testlauf über
    Kurs und Kapitel — Zurück führt ins Kapitel; sonst folgt der Stapel dem Weg (aus dem
    Kapitel in den Test). Der Aufbau der Route startet keinen Lauf."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    from trainingsapp.ui import app

    vorher = AppState.starten()  # dieselbe Datenbank, die `app.main` gleich öffnet
    kurs, kapitel, block, kaefer = _kurs(vorher, Vorgabe(SKALA, 7))
    vorher.schliessen()
    zum_kapitel = f"/kurse/{kurs.id}/{kapitel.id}"
    route = kurs_test.route_zum_test(kurs.id, kapitel.id, block.id, kaefer.id)

    gestartet: list[AppState] = []
    original = AppState.starten

    def starten(*a, **k):
        s = original(*a, **k)
        gestartet.append(s)
        return s

    monkeypatch.setattr(AppState, "starten", staticmethod(starten))
    seite = AppSeite()
    seite.route = route
    app.main(seite)
    state = gestartet[-1]
    try:
        assert seite.routen() == ["/", f"/kurse/{kurs.id}", zum_kapitel, route]
        assert seite.views[-1].appbar.title.value == "Test · Käfer"
        assert state.einheit is None and state.kurs_test is None  # nur „bereit“
        asyncio.run(seite.on_view_pop())
        assert seite.routen()[-1] == zum_kapitel
        asyncio.run(seite.push_route(route))  # der Weg: aus dem Kapitel in den Test
        assert seite.routen()[-2:] == [zum_kapitel, route]
        assert state.einheit is None
    finally:
        state.schliessen()


def test_block_namens_timer_oeffnet_den_test_nicht_den_timer(tmp_path, monkeypatch) -> None:
    """Befund 16.11.2026: Die IDs in der Adresse eines Kurs-Tests sind frei wählbar (Pakete).
    Hieß ein Test-Block „timer“, las `app.main` das Wort als die Timer-Ansicht — der Tipp auf
    „Test starten“ tat nichts. Die Wörter „timer“, „anhang“, „paketmedium“ zählen in dieser
    Adresse erst hinter den IDs; der Timer **über** dem Test geht weiter auf."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    from trainingsapp.ui import app

    vorher = AppState.starten()
    kurs, kapitel, block, kaefer = _kurs(vorher, Vorgabe(SKALA, 7))
    block.id = "timer"
    vorher.kurse.speichern(kurs)
    vorher.schliessen()
    route = kurs_test.route_zum_test(kurs.id, kapitel.id, "timer", kaefer.id)

    gestartet: list[AppState] = []
    original = AppState.starten

    def starten(*a, **k):
        s = original(*a, **k)
        gestartet.append(s)
        return s

    monkeypatch.setattr(AppState, "starten", staticmethod(starten))
    seite = AppSeite()
    seite.route = route
    app.main(seite)
    state = gestartet[-1]
    try:
        assert seite.routen()[-1] == route
        assert seite.views[-1].appbar.title.value == "Test · Käfer"
        asyncio.run(seite.push_route(f"{route}/timer"))  # der Timer legt sich darüber
        assert seite.routen()[-2:] == [route, f"{route}/timer"]
    finally:
        state.schliessen()


# -- Vorgabe Menge -----------------------------------------------------------------------


async def test_menge_von_hand_ein_eintrag_mit_zeit_und_skala(umgebung) -> None:
    """T1 → T3 → T4: 30 Wiederholungen von Hand gezählt. Der Eintrag hält Wiederholungen, Zeit
    und Skala; es ist **genau einer**, „Läufe heute“ zeigt den Lauf als eingetragen, und
    `testwerte` liefert den Wert."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs(state, Vorgabe(MENGE, 30))
    await _starten(u, kurs, kapitel)
    await _sekunden(u, 65)
    ansicht = _ansicht(u, kurs, kapitel, block, kaefer)
    texte = _texte(ansicht)
    assert ansicht.data == FOKUS_ANSICHT and ansicht.appbar.title.value == "Test · Käfer"
    assert ansicht.appbar.leading.tooltip == "Test abbrechen"
    assert "VORGABE" in texte and _daten(ansicht, "test_vorgabe").value == "30 Wiederholungen"
    assert _daten(ansicht, "test_zeit").value == "1:05" and "Zeit läuft · wird gemessen" in texte
    assert "Du zählst selbst" in texte
    assert "Bei 30 tippst du „Fertig“ — die Uhr hält an." in texte
    assert "„Vorher aufgehört“ fragt, wie viele es waren." in texte
    assert not _hat(ansicht, "test_balken")
    fertig = _daten(ansicht, "test_fertig")
    assert fertig.content == "Fertig — 30 gemacht"
    await klick(fertig)
    assert state.kurs_test.phase == ERGEBNIS and state.einheit.laeuft
    await _sekunden(u, 20)  # das Ergebnis bleibt stehen — die Zeit steht fest
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    texte = _texte(ergebnis)
    assert ergebnis.data == FOKUS_ANSICHT and ergebnis.appbar.leading.tooltip == "Test verwerfen"
    assert "Dein Test" in texte
    assert _daten(ergebnis, "wdh").value == "30" and "die Vorgabe" in texte
    assert _daten(ergebnis, "zeit").value == "1:05" and "von der Uhr" in texte
    assert "Wie anstrengend war es?" in texte and "0 = gar nicht · 10 = mehr geht nicht" in texte
    assert not _hat(ergebnis, "test_wdh")  # die Wiederholungen sind die Vorgabe
    zellen = [x.data[1] for x in _alle(ergebnis) if isinstance(getattr(x, "data", None), tuple)]
    assert zellen == list(range(11))
    assert all(_daten(ergebnis, ("test_skala", w)).bgcolor is None for w in range(11))
    assert not _daten(ergebnis, "test_eintragen").disabled
    await klick(_daten(ergebnis, ("test_skala", 6)))
    assert _daten(ergebnis, ("test_skala", 6)).bgcolor == ft.Colors.PRIMARY
    assert not _eintraege(state, kaefer)  # bis hier ist nichts eingetragen
    await klick(_daten(ergebnis, "test_eintragen"))
    assert u.seite.route == f"/kurse/{kurs.id}/{kapitel.id}" and state.kurs_test is None
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, kaefer)  # genau einer — das Ende der Einheit trug nichts ein
    assert eintrag.result == {"reps": [30], "duration": 65, "scale": 6}
    assert eintrag.started_at == UTC0 and eintrag.ended_at == UTC0 + timedelta(seconds=65)
    assert [f.key for f in eintrag.spec_snapshot.fields] == ["reps", "duration", "scale"]
    assert state.kurse.testwerte(kapitel, state.profil.id, SEIT) == {"test": 30.0}
    (lauf,) = _laeufe(state, kaefer)
    assert lauf.eintrag_id == eintrag.id and lauf.eingetragen == {"uhr"}
    assert not lauf.abgebrochen and not lauf.nachtragbar and not lauf.offen
    assert lauf.werte == [65] and [z.sekunden for z in lauf.zeiten] == [65.0]
    # Die laufende Aufnahme: die Übung als Abschnitt, „Pause“ dort, wo die Uhr hielt — das
    # Ende der Übung steht beim Eintragen (20 s später), nicht beim Tipp auf „Fertig“
    notizen = [(n["t_s"], n["text"]) for n in state.messlauf.aufnahme.ereignisse]
    assert notizen == [(0.0, "Käfer: Start"), (65.0, "Käfer: Pause"), (85.0, "Käfer: Ende")]
    # T4: zurück im Kapitel — der Wert groß, daneben klein, was der Lauf sonst gemessen hat
    danach = _kapitel(u, kurs, kapitel)
    assert _daten(danach, "testwert").value == "30 Wdh."
    assert _daten(danach, "testneben").value == "in 1:05 · Anstrengung 6"
    assert any(t.startswith("Dein Test von heute.") for t in _texte(danach))
    assert _daten(danach, ("test_starten", "test")).content == "Nochmal"


async def test_vorher_aufgehoert_fragt_wie_viele(umgebung) -> None:
    """„Vorher aufgehört …“: Die Vorgabe ist nicht erreicht — die App fragt die Wiederholungen,
    und „Eintragen“ geht erst mit ihnen."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs(state, Vorgabe(MENGE, 30))
    await _starten(u, kurs, kapitel)
    await _sekunden(u, 40)
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_vorher"))
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    feld = _daten(ergebnis, "test_wdh")
    assert isinstance(feld, ft.TextField) and not feld.value and "sagst du" in _texte(ergebnis)
    assert _daten(ergebnis, "zeit").value == "0:40"
    assert _daten(ergebnis, "test_eintragen").disabled
    assert _daten(ergebnis, "test_fehlt").value == "Es fehlt noch: Wiederholungen."
    assert kurs_test.eintragen(u.seite, state) is None and not _eintraege(state, kaefer)
    feld.value = "18"
    feld.on_change(SimpleNamespace(control=feld))
    assert not _daten(ergebnis, "test_eintragen").disabled
    assert not _daten(ergebnis, "test_fehlt").visible
    # die Eingabe überlebt den Neuaufbau der Ansicht
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    assert _daten(ergebnis, "test_wdh").value == "18"
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, kaefer)
    assert eintrag.result == {"reps": [18], "duration": 40}  # keine Skala gewählt: keine drin
    assert state.kurse.testwerte(kapitel, state.profil.id, SEIT) == {"test": 18.0}


# -- Vorgabe Anstrengung -----------------------------------------------------------------


async def test_anstrengung_bis_7_belegt_die_skala_vor_und_fragt_die_wiederholungen(
    umgebung,
) -> None:
    """T2: „Bei 7 angekommen“ ist ein Tipp — die Skala steht danach auf 7 (änderbar), die
    Wiederholungen fragt die App, weil niemand zählt."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs(state, Vorgabe(SKALA, 7))
    assert "Käfer: bis Anstrengung 7" in _texte(_kapitel(u, kurs, kapitel))
    await _starten(u, kurs, kapitel)
    await _sekunden(u, 72)
    ansicht = _ansicht(u, kurs, kapitel, block, kaefer)
    texte = _texte(ansicht)
    assert _daten(ansicht, "test_vorgabe").value == "Bis Anstrengung 7"
    assert _daten(ansicht, "test_zeit").value == "1:12"
    assert "ANSTRENGUNG" in texte and "7 · hier ist Schluss" in texte
    assert "Die Marke ist die Regel des Kurses. Wie es sich anfühlt, weißt nur du." in texte
    assert "Ein Tipp hält die Uhr an." in texte and "Du zählst selbst" not in texte
    balken = _daten(ansicht, "test_balken")
    hoehen = [c.height for c in balken.controls]
    assert len(hoehen) == 10 and hoehen[6] == 18 and hoehen.count(10) == 9  # die Marke bei 7
    knopf = _daten(ansicht, "test_fertig")
    assert knopf.content == "Bei 7 angekommen"
    await klick(knopf)
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    assert _daten(ergebnis, ("test_skala", 7)).bgcolor == ft.Colors.PRIMARY  # vorbelegt
    assert _daten(ergebnis, "zeit").value == "1:12"
    assert _daten(ergebnis, "test_eintragen").disabled  # das Feld des Tests fehlt noch
    feld = _daten(ergebnis, "test_wdh")
    feld.value = "22"
    feld.on_change(SimpleNamespace(control=feld))
    assert not _daten(ergebnis, "test_eintragen").disabled
    await klick(_daten(ergebnis, ("test_skala", 8)))  # änderbar
    assert _daten(ergebnis, ("test_skala", 7)).bgcolor is None
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, kaefer)
    assert eintrag.result == {"reps": [22], "duration": 72, "scale": 8}
    danach = _kapitel(u, kurs, kapitel)
    assert _daten(danach, "testwert").value == "22 Wdh."
    assert _daten(danach, "testneben").value == "in 1:12 · Anstrengung 8"


# -- Verwerfen ---------------------------------------------------------------------------


async def test_verwerfen_traegt_nichts_ein(umgebung) -> None:
    """„Verwerfen“ nach dem Lauf: kein Eintrag — auch nicht mit dem Ende der Einheit. Der
    Lauf steht abgebrochen unter „Läufe heute“ und lässt sich dort wie jeder abgebrochene
    doch eintragen."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs(state, Vorgabe(MENGE, 30))
    await _starten(u, kurs, kapitel)
    await _sekunden(u, 50)
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_fertig"))
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_verwerfen"))
    assert u.seite.route == f"/kurse/{kurs.id}/{kapitel.id}" and state.kurs_test is None
    await _bis_vorbei(u)
    assert not _eintraege(state, kaefer)
    assert state.kurse.testwerte(kapitel, state.profil.id, SEIT) == {}
    (lauf,) = _laeufe(state, kaefer)
    assert lauf.abgebrochen and lauf.eintrag_id is None and not lauf.offen
    assert lauf.nachtragbar and [z.sekunden for z in lauf.zeiten] == [50.0]
    assert "Noch kein Test, seit du dieses Kapitel öffnest." in _texte(_kapitel(u, kurs, kapitel))


async def test_kreuz_im_lauf_bricht_ab_und_nochmal_ist_bereit(umgebung) -> None:
    """✕ im Lauf bricht ab und führt ins Kapitel. „Nochmal“ im Ergebnis verwirft und zeigt
    wieder „Start“ — gestartet wird erst mit dem Tipp."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs(state, Vorgabe(MENGE, 30))
    await _starten(u, kurs, kapitel)
    await _sekunden(u, 12)
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_abbrechen"))
    assert u.seite.route == f"/kurse/{kurs.id}/{kapitel.id}"
    await _bis_vorbei(u)
    assert not _eintraege(state, kaefer)
    # noch einmal, bis ins Ergebnis — dann „Nochmal“
    await _starten(u, kurs, kapitel)
    await _sekunden(u, 30)
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_fertig"))
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_nochmal"))
    await _bis_vorbei(u)
    bereit = _ansicht(u, kurs, kapitel, block, kaefer)
    assert bereit.data is None and state.kurs_test is None
    await klick(_daten(bereit, "test_start"))  # „Start“ startet den nächsten Lauf
    assert state.kurs_test.phase == LAEUFT and state.einheit.laeuft
    assert _hat(_ansicht(u, kurs, kapitel, block, kaefer), "test_fertig")
    assert not _eintraege(state, kaefer)
    assert [x.abgebrochen for x in _laeufe(state, kaefer)][1:] == [True, True]


async def test_laeuft_schon_etwas_anderes_startet_der_test_nicht(umgebung) -> None:
    """Läuft schon eine Einheit, sagt es eine Meldung — wie im Timer der Übung."""
    u = umgebung
    state = u.state
    kurs, kapitel, _, kaefer = _kurs(state, Vorgabe(MENGE, 30))
    planke = next(x for x in state.uebungen.alle() if x.name == "Planke")
    andere = uebung_lauf.starten(u.seite, state, uebung_lauf.kontext_fuer(planke), stoppuhr())
    await _starten(u, kurs, kapitel)
    assert state.kurs_test is None and state.einheit is andere
    assert u.seite.route == "/"  # nicht in den Testlauf
    assert "Es läuft schon eine Einheit" in u.seite.dialoge[-1].content.value
    andere.timer.lauf.abbrechen()
    andere.takt()
    await _bis_vorbei(u)
    assert not _eintraege(state, kaefer)


# -- Vorgabe Zeit ------------------------------------------------------------------------


async def test_zeit_laeuft_rueckwaerts_und_endet_von_selbst(umgebung, monkeypatch) -> None:
    """Vorgabe Zeit: Die Uhr zeigt den Rest, es gibt keinen Knopf zum Beenden; bei 0 hält der
    Wächter sie an — mit Countdown und Endsignal des Timers. Die Planke hat keine
    Wiederholungen: gefragt wird nur die Skala."""
    u = umgebung
    state = u.state
    state.ton, state.toene_geladen = Ton(), True
    # Der Wächter sieht alle 0,2 s (echte Zeit) nach. Der Test wartet nicht auf die Uhr an der
    # Wand, sondern darauf, dass er einmal nachgesehen hat — so hängt er nicht an der Last
    blicke = 0
    echt = kurs_test.pruefen

    def zaehlend(page, zustand) -> bool:
        nonlocal blicke
        blicke += 1
        return echt(page, zustand)

    monkeypatch.setattr(kurs_test, "pruefen", zaehlend)

    async def blick() -> None:
        vorher = blicke
        for _ in range(1000):
            if blicke > vorher:
                return
            await asyncio.sleep(0.01)
        raise AssertionError("Der Wächter sah nicht nach")

    kurs, kapitel, block, planke = _kurs(state, Vorgabe(ZEIT, 60), uebung="Planke", feld="hold")
    karte = _texte(_kapitel(u, kurs, kapitel))
    assert "Planke: 1 Minute" in karte
    assert "Die Uhr läuft 1 Minute. Danach sagst du, wie anstrengend es war." in karte
    await _starten(u, kurs, kapitel)
    stand = state.kurs_test
    await _sekunden(u, 20)
    ansicht = _ansicht(u, kurs, kapitel, block, planke)
    texte = _texte(ansicht)
    assert _daten(ansicht, "test_zeit").value == "0:40" and "Zeit läuft · endet von selbst" in texte
    assert not _hat(ansicht, "test_fertig") and _hat(ansicht, "test_vorher")
    assert "Bei 0 hält die Uhr von selbst an." in texte and "Du zählst selbst" not in texte
    # der Ticker frischt nur die Zeit auf
    u.uhr.t += 5
    state.timer_beobachter[kurs_test.BEOBACHTER]()
    assert _daten(ansicht, "test_zeit").value == "0:35"
    assert kurs_test.pruefen(u.seite, state) is False  # noch nicht ab
    # Der Wächter läuft mit: Countdown bei 3, 2, 1 und das Ende bei 0 — nach jeder Sekunde
    # der Attrappen-Uhr sieht er einmal nach
    await _sekunden(u, 31)  # 56 s
    await blick()
    assert stand.phase == LAEUFT and state.ton.gespielt == []
    for _ in range(4):  # 57, 58, 59, 60 s
        await _sekunden(u, 1)
        await blick()
    assert stand.phase == ERGEBNIS and stand.sekunden == 60.0 and not stand.vorher
    assert state.ton.gespielt == ["countdown", "countdown", "countdown", "ende"]
    assert state.einheit.timer.lauf.laeuft is False  # die Uhr hält
    ergebnis = _ansicht(u, kurs, kapitel, block, planke)
    texte = _texte(ergebnis)
    assert _daten(ergebnis, "zeit").value == "1:00" and "die Vorgabe" in texte
    assert "Wiederholungen" not in texte and not _hat(ergebnis, "test_wdh")
    assert not _daten(ergebnis, "test_eintragen").disabled
    await klick(_daten(ergebnis, ("test_skala", 5)))
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, planke)
    assert eintrag.result == {"hold": [60], "scale": 5}
    assert state.kurse.testwerte(kapitel, state.profil.id, SEIT) == {"test": 60.0}
    danach = _kapitel(u, kurs, kapitel)
    assert _daten(danach, "testwert").value == "1:00 Haltezeit"
    assert _daten(danach, "testneben").value == "Anstrengung 5"


async def test_zeit_auf_uebung_mit_wiederholungen_fragt_sie(umgebung) -> None:
    """Vorgabe Zeit bei einer Übung mit Wiederholungen: Die Zeit ist die Vorgabe, die
    Wiederholungen sagt die Person danach — ohne sie hat der Test keinen Wert."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs(state, Vorgabe(ZEIT, 30))
    await _starten(u, kurs, kapitel)
    await _sekunden(u, 20)
    assert "Wie viele es waren, sagst du danach." in _texte(
        _ansicht(u, kurs, kapitel, block, kaefer)
    )
    await _sekunden(u, 11)
    kurs_test.pruefen(u.seite, state)  # der Wächter tut dasselbe
    assert state.kurs_test.phase == ERGEBNIS and state.kurs_test.sekunden == 30.0
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    assert _daten(ergebnis, "test_eintragen").disabled
    feld = _daten(ergebnis, "test_wdh")
    feld.value = "14"
    feld.on_change(SimpleNamespace(control=feld))
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, kaefer)
    assert eintrag.result == {"reps": [14], "duration": 30}
    assert _daten(_kapitel(u, kurs, kapitel), "testneben").value == "in 0:30"


# -- Zählt schon jemand ------------------------------------------------------------------


async def test_zaehlt_der_sensor_endet_die_menge_von_selbst(umgebung) -> None:
    """Zählt bei der Übung schon der Sensor, tritt die Uhr des Tests seinem Zähllauf bei: Die
    Karte zeigt die Zahl statt „Du zählst selbst“, und bei der Menge hält die Uhr von selbst
    an. Eingetragen wird einmal — das Ende der Einheit trägt die Wiederholungen nicht noch
    in einen zweiten Eintrag."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs(state, Vorgabe(MENGE, 4))
    uebung_lauf.zaehlen_starten(u.seite, state, uebung_lauf.kontext_fuer(kaefer), uebung=kaefer)
    await _sekunden(u, 2, beschleunigung=True)
    zaehllauf = state.einheit
    await _starten(u, kurs, kapitel)
    assert state.einheit is zaehllauf and zaehllauf.timer is not None  # die Uhr trat bei
    await _sekunden(u, 6, beschleunigung=True)
    ansicht = _ansicht(u, kurs, kapitel, block, kaefer)
    texte = _texte(ansicht)
    assert "Sensor zählt" in texte and "Du zählst selbst" not in texte
    assert "Bei 4 hält die Uhr von selbst an." in texte
    assert int(_daten(ansicht, "test_zahl").value) >= 1
    for _ in range(40):
        await _sekunden(u, 1, beschleunigung=True)
        kurs_test.pruefen(u.seite, state)  # der Wächter tut dasselbe
        if state.kurs_test.phase == ERGEBNIS:
            break
    stand = state.kurs_test
    assert stand.phase == ERGEBNIS and stand.gezaehlt and stand.wdh >= 4
    gezaehlt = stand.wdh
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    assert _daten(ergebnis, "wdh").value == str(gezaehlt) and "gezählt" in _texte(ergebnis)
    assert not _hat(ergebnis, "test_wdh")
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, kaefer)
    assert eintrag.result["reps"] == [gezaehlt] and eintrag.result["duration"] > 0
    (lauf,) = _laeufe(state, kaefer)
    assert lauf.eingetragen == {"uhr", "zaehlen"} and not lauf.nachtragbar


# -- Test „der gewählten“ ----------------------------------------------------------------


async def test_der_gewaehlten_je_uebung_ein_knopf(umgebung) -> None:
    """Ein Test mit ``aus`` misst die Gewählten: je Übung eine Zeile mit „Test starten“, der
    Lauf gehört zu dieser Übung, und danach steht in ihrer Zeile, was er gemessen hat."""
    u = umgebung
    state = u.state
    uebungen = {
        name: Exercise(name=name, result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
        for name in ("Käfer", "Brücke", "Kniebeuge")
    }
    for x in uebungen.values():
        state.uebungen.speichern(x)
    kaefer, bruecke = uebungen["Käfer"], uebungen["Brücke"]
    wahl = Block(AUSWAHL, id="wahl", uebungen=[x.id for x in uebungen.values()], anzahl=2)
    test = Block(TEST, id="test", aus="wahl", feld="reps", vorgabe=Vorgabe(SKALA, 7))
    kurs = Kurs(name="Rumpf-Kurs", kapitel=[Kapitel(titel="Wahl", bloecke=[wahl, test])])
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    kapitel = kurs.kapitel[0]
    _erreichen(state, kurs, kapitel)
    ansicht = _kapitel(u, kurs, kapitel)
    assert "Deine Auswahl: bis Anstrengung 7" in _texte(ansicht)
    assert not [
        x for x in _alle(ansicht) if (getattr(x, "data", None) or ("",))[0] == "test_starten"
    ]
    for x in (kaefer, bruecke):
        _daten(ansicht, ("wahl", "wahl", x.id)).on_select()
    assert _daten(ansicht, ("test_starten", "test", kaefer.id)).content == "Test starten"
    await klick(_daten(ansicht, ("test_starten", "test", bruecke.id)))
    assert u.seite.route == f"/kurse/{kurs.id}/{kapitel.id}/test/test/{bruecke.id}"
    assert state.kurs_test.uebung_id == bruecke.id
    gefunden = kurs_test.aus_route(state, kurs, kapitel, ["test", "test", bruecke.id])
    assert gefunden is not None
    block, uebung = gefunden
    await _sekunden(u, 48)
    await klick(_daten(_ansicht(u, kurs, kapitel, block, uebung), "test_fertig"))
    ergebnis = _ansicht(u, kurs, kapitel, block, uebung)
    feld = _daten(ergebnis, "test_wdh")
    feld.value = "15"
    feld.on_change(SimpleNamespace(control=feld))
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    danach = _kapitel(u, kurs, kapitel)  # die offene Wahl hält die Sitzung (P212)
    assert _daten(danach, ("testwert", "test", bruecke.id)).value == (
        "15 Wdh. · in 0:48 · Anstrengung 7"
    )
    assert _daten(danach, ("testwert", "test", kaefer.id)).value == "noch kein Test"
    assert _daten(danach, ("test_starten", "test", bruecke.id)).content == "Nochmal"
    assert _daten(danach, ("test_starten", "test", kaefer.id)).content == "Test starten"


# -- Der gestaltete Test (Ben, 16.11.2026: „Der Test muss flexibel gestaltet werden können“) --

INTERVALL = TimerProfil(
    id="intervall",
    name="Intervall",
    abschnitte=[Abschnitt("Los", 20), Abschnitt("Pause", 10, zaehlt=False)],
    runden=2,
)
HALTEN = TimerProfil(id="halten", name="Halten", abschnitte=[Abschnitt("Halten", 45)])
KNIEBEUGE = VORLAGEN["kniebeuge_2_1_2"]  # eine Runde dauert 5 s; beim Üben zählt er


def _uebung(name: str, *felder: str, **mehr) -> Exercise:
    return Exercise(
        name=name, result_spec=ResultSpec(fields=[vorrat_feld(k) for k in felder]), **mehr
    )


def _gestaltet(state, uebung: Exercise, **block):
    """Ein Kurs mit einem Kapitel und einem Test bei ``uebung`` mit den Angaben ``block`` —
    erreicht eine Stunde vor der Uhr der Attrappen (wie `_kurs`)."""
    state.uebungen.speichern(uebung)
    test = Block(TEST, id="test", uebung=uebung.id, **block)
    kurs = Kurs(name="Rumpf-Kurs", kapitel=[Kapitel(titel="Erweiterung", bloecke=[test])])
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    kapitel = kurs.kapitel[0]
    _erreichen(state, kurs, kapitel)
    return kurs, kapitel, kapitel.bloecke[0], state.uebungen.laden(uebung.id)


def _chip(c, text: str) -> ft.Chip:
    return next(x for x in _alle(c) if isinstance(x, ft.Chip) and x.label.value == text)


def _symbolknopf(c, tooltip: str) -> ft.IconButton:
    return next(x for x in _alle(c) if isinstance(x, ft.IconButton) and x.tooltip == tooltip)


async def _oeffnen_und_starten(u, kurs, kapitel, block, uebung) -> None:
    """Ein gestalteter Test: „Test starten“ im Kapitel öffnet ihn bereit, „Start“ startet."""
    await _starten(u, kurs, kapitel)
    assert vorbei(u.state) and u.state.kurs_test is None  # nur geöffnet, nichts läuft
    await klick(_daten(_ansicht(u, kurs, kapitel, block, uebung), "test_start"))


async def test_gestalteter_test_oeffnet_sich_bereit_und_zeigt_wie_er_laeuft(umgebung) -> None:
    """F2: Die Karte sagt in einem Satz, wie der Test läuft; „Test starten“ öffnet ihn
    **bereit** — Hinweis, Ausführung (vorgegeben zum Lesen, frei zum Wählen), Timer, Takt —
    und startet nichts. Erst „Start“ startet die Uhr, mit dem Timer des Tests."""
    u = umgebung
    state = u.state
    kaefer = _uebung("Käfer", "reps", "weight", "side")
    kurs, kapitel, block, kaefer = _gestaltet(
        state,
        kaefer,
        feld="reps",
        text="Mach dich vorher 5 Minuten warm.",
        timer=INTERVALL.als_dict(),
        takt=KNIEBEUGE,
        ziel={"side": "links"},
        felder=["weight"],
    )
    assert block.vorgabe is None and block.laeuft
    karte = _kapitel(u, kurs, kapitel)
    texte = _texte(karte)
    assert "Käfer: was schaffst du?" in texte and "Mach dich vorher 5 Minuten warm." in texte
    assert _daten(karte, ("test_wie", "test")).value == (
        "Läuft mit dem Timer „Intervall“ (1:00) und im Takt Kniebeuge 2-1-2. "
        "Ausführung: links. Gewicht wählst du vor dem Start."
    )
    assert "Noch kein Test, seit du dieses Kapitel öffnest." in texte
    knopf = _daten(karte, ("test_starten", "test"))
    assert knopf.content == "Test starten" and not _hat(karte, ("test_oeffnen", "test"))
    await klick(knopf)
    assert u.seite.route == f"/kurse/{kurs.id}/{kapitel.id}/test/test/{kaefer.id}"
    assert state.einheit is None and state.kurs_test is None  # nur geöffnet
    bereit = _ansicht(u, kurs, kapitel, block, kaefer)
    texte = _texte(bereit)
    assert bereit.data is None and bereit.appbar.leading is None
    assert "TIMER" in texte and _daten(bereit, "test_vorgabe").value == "Intervall · 1:00"
    assert (
        "Der Timer läuft 1 Minute. Danach sagst du, wie viele es waren und wie anstrengend "
        "es war." in texte
    )
    assert _daten(bereit, "test_hinweis").value == "Mach dich vorher 5 Minuten warm."
    assert "SO MACHST DU DEN TEST" in texte
    assert _daten(bereit, ("test_fest", "side")).value == "links" and "vorgegeben" in texte
    assert not [x for x in _alle(bereit) if isinstance(x, ft.Chip)]  # die Seite steht fest
    # der Timer steht schon groß im Kopf — die Karte nennt seine Abschnitte
    assert _daten(bereit, "test_timer").value == "Abschnitte"
    assert _daten(bereit, "test_abschnitte").value == "0:20 Los · 0:10 Pause · 2 Runden"
    assert "Takt läuft mit" in texte
    assert _daten(bereit, "test_takt").value == "12,0/min · 2 s ab, 1 s halten, 2 s auf"
    # das Gewicht ist frei: mit „+“ gewählt — die Wahl überlebt den Neuaufbau der Ansicht
    await klick(_symbolknopf(bereit, "Gewicht mehr"))
    bereit = _ansicht(u, kurs, kapitel, block, kaefer)
    assert "5 kg" in _texte(bereit)
    await klick(_symbolknopf(bereit, "Gewicht mehr"))
    assert state.einheit is None
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_start"))
    e = state.einheit
    stand = state.kurs_test
    assert e is not None and e.laeuft and stand.phase == LAEUFT
    assert e.timer.lauf.profil.name == "Intervall" and stand.timer is not None
    assert not e.ende_mit_timer  # ist der Timer durch, wartet das Ergebnis
    assert e.timer.lauf.takt_uebung == KNIEBEUGE and e.teil("zaehlen") is None
    assert stand.vorgabe is None and stand.ausfuehrung == {"side": "links", "weight": 6}
    assert stand.ausfuehrung_text == "links · 6 kg"
    # Solange er läuft, führt die Karte zum Test
    laufend = _daten(_kapitel(u, kurs, kapitel), ("test_starten", "test"))
    assert laufend.content == "Zum Test"
    await klick(laufend)
    assert state.einheit is e and state.kurs_test is stand


async def test_timer_mit_abschnitten_endet_von_selbst_und_traegt_einmal_ein(umgebung) -> None:
    """Der Test läuft mit seinem Timer aus zwei Abschnitten: Die Ansicht zeigt den Abschnitt
    und seinen Rest, ein Knopf zum Beenden fehlt; ist der Timer durch, wartet das Ergebnis
    (die Einheit läuft weiter). Die Zeit des Tests ist, was in den zählenden Abschnitten lief;
    eingetragen wird genau einmal."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _gestaltet(
        state, _uebung("Käfer", "reps"), feld="reps", timer=INTERVALL.als_dict()
    )
    await _oeffnen_und_starten(u, kurs, kapitel, block, kaefer)
    await _sekunden(u, 12)
    ansicht = _ansicht(u, kurs, kapitel, block, kaefer)
    texte = _texte(ansicht)
    assert ansicht.data == FOKUS_ANSICHT and "TIMER" in texte
    assert _daten(ansicht, "test_zeit").value == "0:08"  # der Rest des Abschnitts
    assert _daten(ansicht, "test_abschnitt").value == "Los · Runde 1 von 2"
    assert _daten(ansicht, "test_gesamt").value == "0:12 von 1:00"
    assert "danach Pause 0:10" in texte and "Timer läuft · endet von selbst" in texte
    assert len(_daten(ansicht, "test_leiste").content.controls) == 4  # vier Abschnitte
    assert not _hat(ansicht, "test_fertig") and _hat(ansicht, "test_vorher")
    assert "Du zählst selbst" in texte and "Wie viele es waren, sagst du danach." in texte
    assert "Ist der Timer durch, hält die Uhr von selbst an." in texte
    # der Ticker frischt Zeit und Abschnitt auf
    u.uhr.t += 10
    state.timer_beobachter[kurs_test.BEOBACHTER]()
    assert _daten(ansicht, "test_zeit").value == "0:08"  # 22 s: die Pause, noch 8 s
    assert _daten(ansicht, "test_abschnitt").value == "Pause · Runde 1 von 2 · zählt nicht"
    assert kurs_test.pruefen(u.seite, state) is False
    await _sekunden(u, 39)  # 61 s — der Timer ist seit einer Sekunde durch
    # Die Einheit endet nicht mit dem Timer: Sie wartet auf das Ergebnis. Der Wächter sieht
    # alle 0,2 s (echte Zeit) nach — war er noch nicht da, tut der Test dasselbe
    assert state.einheit.laeuft
    kurs_test.pruefen(u.seite, state)
    stand = state.kurs_test
    assert stand.phase == ERGEBNIS and stand.durch and not stand.vorher
    assert stand.sekunden == 40.0 and stand.ende_t_s == 60.0  # zweimal „Los“; Ende bei 1:00
    await _sekunden(u, 20)  # die Einheit wartet auf „Eintragen“ — nichts ist eingetragen
    assert state.einheit.laeuft and not _eintraege(state, kaefer)
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    texte = _texte(ergebnis)
    assert _daten(ergebnis, "test_ende").value == "Der Timer ist durch"
    assert _daten(ergebnis, "zeit").value == "0:40" and "vom Timer" in texte
    assert _daten(ergebnis, "test_eintragen").disabled
    feld = _daten(ergebnis, "test_wdh")
    feld.value = "14"
    feld.on_change(SimpleNamespace(control=feld))
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, kaefer)  # genau einer — das Ende der Einheit trug nichts ein
    assert eintrag.result == {"reps": [14], "duration": 40}
    assert eintrag.started_at == UTC0 and eintrag.ended_at == UTC0 + timedelta(seconds=60)
    assert state.kurse.testwerte(kapitel, state.profil.id, SEIT) == {"test": 14.0}
    (lauf,) = _laeufe(state, kaefer)
    assert lauf.eintrag_id == eintrag.id and lauf.eingetragen == {"uhr"}
    assert not lauf.abgebrochen and not lauf.nachtragbar and not lauf.offen
    assert [(z.name, z.sekunden) for z in lauf.zeiten] == [
        ("Los", 20.0),
        ("Pause", 10.0),
        ("Los", 20.0),
        ("Pause", 10.0),
    ]
    # In der laufenden Aufnahme stehen die Abschnitte des Timers — wie beim Üben
    notizen = [n["text"] for n in state.messlauf.aufnahme.ereignisse]
    assert notizen[0] == "Käfer: Start" and notizen[-1] == "Käfer: Ende"
    assert "Pause (Runde 1/2)" in notizen and "Los (Runde 2/2)" in notizen
    assert _daten(_kapitel(u, kurs, kapitel), "testwert").value == "14 Wdh."


async def test_timer_durch_und_verworfen_traegt_nichts_ein(umgebung) -> None:
    """Ein Timer, der durchlief, lässt sich an der Uhr nicht mehr abbrechen — „Verwerfen“
    trägt trotzdem nichts ein, auch nicht mit dem Ende der Einheit: Der Lauf steht
    abgebrochen unter „Läufe heute“."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _gestaltet(
        state, _uebung("Käfer", "reps"), feld="reps", timer=INTERVALL.als_dict()
    )
    await _oeffnen_und_starten(u, kurs, kapitel, block, kaefer)
    await _sekunden(u, 62)
    kurs_test.pruefen(u.seite, state)  # der Wächter tut dasselbe
    assert state.kurs_test.phase == ERGEBNIS and state.kurs_test.durch
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_verwerfen"))
    assert u.seite.route == f"/kurse/{kurs.id}/{kapitel.id}" and state.kurs_test is None
    await _bis_vorbei(u)
    assert not _eintraege(state, kaefer)
    assert state.kurse.testwerte(kapitel, state.profil.id, SEIT) == {}
    (lauf,) = _laeufe(state, kaefer)
    assert lauf.abgebrochen and lauf.eintrag_id is None and not lauf.offen and lauf.nachtragbar
    # … und vor dem Ende des Timers: „Vorher aufgehört …“ nimmt die Zeit bis dahin, ✕ bricht ab
    await _oeffnen_und_starten(u, kurs, kapitel, block, kaefer)
    await _sekunden(u, 25)  # 20 s „Los“, 5 s Pause
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_vorher"))
    stand = state.kurs_test
    assert stand.phase == ERGEBNIS and stand.vorher and not stand.durch
    assert stand.sekunden == 20.0
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    assert _daten(ergebnis, "test_ende").value == "Vorher aufgehört"
    await klick(_daten(ergebnis, "test_abbrechen"))
    await _bis_vorbei(u)
    assert not _eintraege(state, kaefer)
    assert [x.abgebrochen for x in _laeufe(state, kaefer)] == [True, True]


async def test_takt_fuehrt_zaehlt_nicht_und_schlaegt_seine_runden_vor(umgebung) -> None:
    """F3, F4: Der Takt läuft mit, aber er zählt nicht — kein Zähl-Teil, „Du zählst selbst“
    weicht seiner Karte. Im Ergebnis stehen seine Runden als Vorschlag in den Wiederholungen;
    „Eintragen“ bestätigt, −/+ ändern. Die vor dem Start gewählte Ausführung steht im
    Eintrag."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _gestaltet(
        state,
        _uebung("Käfer", "reps", "side"),
        feld="reps",
        vorgabe=Vorgabe(SKALA, 7),
        takt=KNIEBEUGE,
        felder=["side"],
    )
    await _starten(u, kurs, kapitel)
    assert state.einheit is None  # gestaltet: erst bereit
    bereit = _ansicht(u, kurs, kapitel, block, kaefer)
    assert _daten(bereit, "test_vorgabe").value == "Bis Anstrengung 7"
    assert [x.label.value for x in _alle(bereit) if isinstance(x, ft.Chip)] == [
        "links",
        "rechts",
        "beide",
    ]
    assert not any(x.selected for x in _alle(bereit) if isinstance(x, ft.Chip))
    _chip(bereit, "rechts").on_select()
    bereit = _ansicht(u, kurs, kapitel, block, kaefer)
    assert _chip(bereit, "rechts").selected and not _chip(bereit, "links").selected
    await klick(_daten(bereit, "test_start"))
    e = state.einheit
    assert e.timer.lauf.profil.ist_stoppuhr and e.timer.lauf.takt_uebung == KNIEBEUGE
    assert e.teil("zaehlen") is None  # der Takt zählt nicht — auch wenn er es beim Üben täte
    await _sekunden(u, 92)
    assert e.teil("zaehlen") is None and kurs_test.pruefen(u.seite, state) is False
    ansicht = _ansicht(u, kurs, kapitel, block, kaefer)
    texte = _texte(ansicht)
    assert _daten(ansicht, "test_zeit").value == "1:32" and "TAKT" in texte
    assert _daten(ansicht, "test_ausfuehrung").value == "rechts"
    assert _daten(ansicht, "test_takt").value == "12,0/min · 2 s ab, 1 s halten, 2 s auf"
    assert "Der Takt führt — gezählt hat damit noch niemand." in texte
    assert "Runde 19 · 12,0/min" in texte  # die Anzeige des Takts wie im Fokus
    assert "Du zählst selbst" not in texte and not _hat(ansicht, "test_zahl")
    assert "Ein Tipp hält Uhr und Takt an. Danach sagst du, wie viele es waren." in texte
    await klick(_daten(ansicht, "test_fertig"))
    stand = state.kurs_test
    assert stand.phase == ERGEBNIS and not stand.gezaehlt
    assert stand.wdh == 18 and stand.takt_runden == 18 and stand.skala == 7
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    texte = _texte(ergebnis)
    assert _daten(ergebnis, "test_ende").value == "Bei 7 angekommen"
    assert "Der Takt lief 18 Runden. Stimmt die Zahl?" in texte and "sagst du" not in texte
    assert _daten(ergebnis, "test_wdh").value == "18"
    assert not _daten(ergebnis, "test_eintragen").disabled  # „Eintragen“ bestätigt
    assert _daten(ergebnis, "ausfuehrung").value == "rechts"
    assert "wie vor dem Start gewählt" in texte
    await klick(_daten(ergebnis, "test_wdh_plus"))
    await klick(_daten(ergebnis, "test_wdh_plus"))
    await klick(_daten(ergebnis, "test_wdh_minus"))
    assert stand.wdh == 19 and _daten(ergebnis, "test_wdh").value == "19"
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, kaefer)
    assert eintrag.result == {"reps": [19], "duration": 92, "scale": 7, "side": "rechts"}
    assert [f.key for f in eintrag.spec_snapshot.fields] == ["reps", "side", "duration", "scale"]
    ereignisse = state.einheiten.ereignisse(e.id)
    assert [x.daten["name"] for x in ereignisse if (x.quelle, x.art) == ("timer", "takt")] == [
        "Kniebeuge 2-1-2"
    ]
    assert not [x for x in ereignisse if x.quelle == "zaehlen"]
    danach = _kapitel(u, kurs, kapitel)
    assert _daten(danach, "testwert").value == "19 Wdh."
    assert _daten(danach, "testneben").value == "in 1:32 · Anstrengung 7 · rechts"


async def test_der_takt_beendet_eine_menge_nicht(umgebung) -> None:
    """Vorgabe Menge mit Takt: Auch wenn der Takt die Menge längst durchlaufen hat, endet der
    Test nicht von selbst — erst der Knopf. Die Menge ist dann die Vorgabe, kein Vorschlag."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _gestaltet(
        state,
        _uebung("Käfer", "reps"),
        feld="duration",
        vorgabe=Vorgabe(MENGE, 4),
        takt=VORLAGEN["metronom_1"],
    )
    await _oeffnen_und_starten(u, kurs, kapitel, block, kaefer)
    await _sekunden(u, 12)  # zwölf Schläge — dreimal die Menge
    assert kurs_test.pruefen(u.seite, state) is False and state.kurs_test.phase == LAEUFT
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_fertig"))
    stand = state.kurs_test
    assert stand.wdh == 4 and stand.takt_runden is None
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    assert _daten(ergebnis, "wdh").value == "4" and "die Vorgabe" in _texte(ergebnis)
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, kaefer)
    assert eintrag.result == {"reps": [4], "duration": 12}


async def test_wie_die_uebung_nimmt_ihren_timer_takt_und_ihre_parameter(umgebung) -> None:
    """„Wie die Übung“: ihr Timer, ihr Takt, ihre Parameter (frei, vorbelegt mit ihrem
    Standard). Neben dem Timer gilt eine Vorgabe „Zeit“ nicht — der Timer ist die Zeit."""
    u = umgebung
    state = u.state
    planke = _uebung(
        "Planke",
        "hold",
        "weight",
        timer=[HALTEN.als_dict()],
        takt=VORLAGEN["atmung_4_6"],
        default_target={"weight": 10},
    )
    kurs, kapitel, block, planke = _gestaltet(
        state,
        planke,
        feld="hold",
        vorgabe=Vorgabe(ZEIT, 60),
        wie_uebung=["uhr", "takt", "parameter"],
    )
    karte = _kapitel(u, kurs, kapitel)
    assert "Planke: was schaffst du?" in _texte(karte)  # nicht „Planke: 1 Minute“
    assert _daten(karte, ("test_wie", "test")).value == (
        "Läuft mit dem Timer „Halten“ (0:45) und im Takt Atmung 4-6. "
        "Gewicht wählst du vor dem Start."
    )
    await _starten(u, kurs, kapitel)
    bereit = _ansicht(u, kurs, kapitel, block, planke)
    assert _daten(bereit, "test_vorgabe").value == "Halten · 0:45"
    assert "10 kg" in _texte(bereit)  # vorbelegt mit dem Standard der Übung
    await klick(_daten(bereit, "test_start"))
    stand = state.kurs_test
    lauf = state.einheit.timer.lauf
    assert stand.vorgabe is None and lauf.profil.name == "Halten"
    assert lauf.takt_uebung == VORLAGEN["atmung_4_6"] and stand.ausfuehrung == {"weight": 10}
    await _sekunden(u, 30)
    ansicht = _ansicht(u, kurs, kapitel, block, planke)
    assert _daten(ansicht, "test_zeit").value == "0:15"
    assert _daten(ansicht, "test_ausfuehrung").value == "10 kg"
    assert not _hat(ansicht, "test_fertig") and _hat(ansicht, "test_vorher")
    await _sekunden(u, 16)
    kurs_test.pruefen(u.seite, state)  # der Wächter tut dasselbe
    assert stand.phase == ERGEBNIS and stand.durch and stand.sekunden == 45.0
    assert stand.wdh is None and stand.takt_runden is None  # eine Haltezeit hat keine
    ergebnis = _ansicht(u, kurs, kapitel, block, planke)
    assert "Wiederholungen" not in _texte(ergebnis)
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, planke)
    assert eintrag.result == {"hold": [45], "weight": 10}
    assert state.kurse.testwerte(kapitel, state.profil.id, SEIT) == {"test": 45.0}


async def test_vorgegebene_ausfuehrung_ohne_vorgabe_endet_mit_fertig(umgebung) -> None:
    """Ein Test, der nur die Ausführung vorgibt: Er läuft mit der Stoppuhr und endet mit
    „Fertig“ („Vorher aufgehört“ gibt es ohne Vorgabe nicht). Die Ausführung steht im Eintrag
    — in seiner Kopie der Felder, auch wenn die Übung das Feld nicht anbietet."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, planke = _gestaltet(
        state, _uebung("Planke", "hold"), feld="hold", ziel={"angle": 90}
    )
    route = kurs_test.route_zum_test(kurs.id, kapitel.id, block.id, planke.id).split("/")[4:]
    assert kurs_test.aus_route(state, kurs, kapitel, route) is not None  # auch ohne Vorgabe
    await _starten(u, kurs, kapitel)
    bereit = _ansicht(u, kurs, kapitel, block, planke)
    texte = _texte(bereit)
    assert "TEST" in texte and _daten(bereit, "test_vorgabe").value == "Was schaffst du?"
    assert (
        "Die App misst die Zeit, bis du „Fertig“ tippst. Danach sagst du, wie anstrengend es "
        "war." in texte
    )
    assert _daten(bereit, ("test_fest", "angle")).value == "90°"
    assert not _hat(bereit, "test_timer") and not _hat(bereit, "test_takt")
    await klick(_daten(bereit, "test_start"))
    assert state.einheit.timer.lauf.profil.ist_stoppuhr and state.einheit.ende_mit_timer
    await _sekunden(u, 48)
    ansicht = _ansicht(u, kurs, kapitel, block, planke)
    assert _daten(ansicht, "test_zeit").value == "0:48"
    assert _daten(ansicht, "test_fertig").content == "Fertig" and not _hat(ansicht, "test_vorher")
    assert _daten(ansicht, "test_ausfuehrung").value == "90°"
    await klick(_daten(ansicht, "test_fertig"))
    ergebnis = _ansicht(u, kurs, kapitel, block, planke)
    texte = _texte(ergebnis)
    assert _daten(ergebnis, "test_ende").value == "Fertig"
    assert _daten(ergebnis, "zeit").value == "0:48" and "von der Uhr" in texte
    assert _daten(ergebnis, "ausfuehrung").value == "90°" and "vorgegeben" in texte
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, planke)
    assert eintrag.result == {"hold": [48], "angle": 90}
    assert [f.key for f in eintrag.spec_snapshot.fields] == ["hold", "angle"]
    assert [f.key for f in state.uebungen.laden(planke.id).result_spec.fields] == ["hold"]
    danach = _kapitel(u, kurs, kapitel)
    assert _daten(danach, "testwert").value == "48s Haltezeit"
    assert _daten(danach, "testneben").value == "90°"


async def test_vorgabe_mit_timer_und_takt_der_timer_kann_eher_durch_sein(umgebung) -> None:
    """Vorgabe Anstrengung, eigener Timer und Takt zusammen: Der Knopf der Vorgabe beendet
    vorher; ist der Timer eher durch, gilt die Vorgabe als nicht erreicht (die Skala wird
    gefragt, nicht vorbelegt). Die Runden des Takts zählen nur in den zählenden Abschnitten
    in den Vorschlag."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _gestaltet(
        state,
        _uebung("Käfer", "reps"),
        feld="reps",
        vorgabe=Vorgabe(SKALA, 7),
        timer=INTERVALL.als_dict(),
        takt=KNIEBEUGE,
    )
    await _starten(u, kurs, kapitel)
    bereit = _ansicht(u, kurs, kapitel, block, kaefer)
    assert _daten(bereit, "test_vorgabe").value == "Bis Anstrengung 7"
    assert _daten(bereit, "test_timer").value == "Timer: Intervall · 1:00"
    assert any(
        t.endswith("Ist der Timer vorher durch (1 Minute), endet der Test.") for t in _texte(bereit)
    )
    await klick(_daten(bereit, "test_start"))
    await _sekunden(u, 35)  # 20 s „Los“, 10 s Pause, 5 s „Los“
    ansicht = _ansicht(u, kurs, kapitel, block, kaefer)
    assert _daten(ansicht, "test_fertig").content == "Bei 7 angekommen"
    assert _hat(ansicht, "test_vorher") and "TAKT" in _texte(ansicht)
    assert _daten(ansicht, "test_abschnitt").value == "Los · Runde 2 von 2"
    assert _hat(ansicht, "test_balken")  # die Marke der Anstrengung
    await klick(_daten(ansicht, "test_fertig"))
    stand = state.kurs_test
    assert stand.phase == ERGEBNIS and not stand.vorher and not stand.durch
    assert stand.sekunden == 25.0 and stand.skala == 7
    assert stand.wdh == 5 and stand.takt_runden == 5  # vier Runden, Pause, eine Runde
    assert _daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_ende").value == (
        "Bei 7 angekommen"
    )
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_nochmal"))
    await _bis_vorbei(u)
    # noch einmal — diesmal ist der Timer eher durch
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_start"))
    await _sekunden(u, 62)
    kurs_test.pruefen(u.seite, state)  # der Wächter tut dasselbe
    stand = state.kurs_test
    assert stand.phase == ERGEBNIS and stand.durch and stand.vorher
    assert stand.sekunden == 40.0 and stand.skala is None
    assert stand.wdh == 8 and stand.takt_runden == 8
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    texte = _texte(ergebnis)
    assert _daten(ergebnis, "test_ende").value == "Der Timer ist durch"
    assert "Der Takt lief 8 Runden. Stimmt die Zahl?" in texte and "vom Timer" in texte
    assert all(_daten(ergebnis, ("test_skala", w)).bgcolor is None for w in range(11))
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, kaefer)
    assert eintrag.result == {"reps": [8], "duration": 40}


# -- Wert für den Plan (W3, Ben 17.11.2026; `docs/plan_kurs_ablauf.md` §17) ---------------


def _kurs_mit_ziel(state, vorgabe: Vorgabe | None, faktor: float = 0.8):
    """Wie `_kurs`, aber der Kurs baut einen Plan, und ein Baustein nimmt sein Ziel aus dem
    Test (``faktor`` vom Wert) — aus dem Testwert wird ein Ziel, also gibt es die Karte „Wert
    für den Plan“."""
    kaefer = Exercise(name="Käfer", result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    state.uebungen.speichern(kaefer)
    kurs = Kurs(
        name="Rumpf-Kurs",
        kursplan=Kursplan("Rumpf", [0, 2, 4]),
        kapitel=[
            Kapitel(
                titel="Erweiterung",
                bloecke=[
                    Block(TEST, id="test", uebung=kaefer.id, feld="reps", vorgabe=vorgabe),
                    Block(PLAN_UEBUNG, id="dazu", uebung=kaefer.id, ziel_aus="test", faktor=faktor),
                ],
            )
        ],
    )
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    kapitel = kurs.kapitel[0]
    _erreichen(state, kurs, kapitel)
    return kurs, kapitel, kapitel.bloecke[0], state.uebungen.laden(kaefer.id)


def _weg(karte, wie: str, schluessel=None) -> None:
    """Den Weg der Karte „Wert für den Plan“ wählen — wie der Tipp auf den Umschalter."""
    marke = ("planwert_weg", schluessel) if schluessel is not None else "planwert_weg"
    umschalter = _daten(karte, marke)
    umschalter.selected = [wie]
    umschalter.on_change(SimpleNamespace(control=umschalter))


def _tippen(feld, text: str) -> None:
    feld.value = text
    feld.on_change(SimpleNamespace(control=feld))


async def _bis_zum_ergebnis(u, kurs, kapitel, block, kaefer, wdh: str = "22"):
    """Der Lauf „bis Anstrengung 7“ bis zur Ergebnis-Seite, die Wiederholungen getippt."""
    await _starten(u, kurs, kapitel)
    await _sekunden(u, 72)
    await klick(_daten(_ansicht(u, kurs, kapitel, block, kaefer), "test_fertig"))
    ergebnis = _ansicht(u, kurs, kapitel, block, kaefer)
    if wdh:
        _tippen(_daten(ergebnis, "test_wdh"), wdh)
    return ergebnis


async def test_wert_fuer_den_plan_steht_direkt_nach_dem_test(umgebung) -> None:
    """Ben, 17.11.2026: „Die Werteintragung kommt normal direkt nach einem Test“ — „ganz
    genommen – prozentual abgeändert – manuell eingegeben (mit Klick und per Tastatur)“. Die
    Karte steht auf der Ergebnis-Seite, vorgewählt, was der Kurs sagt (80 %); „Eintragen“
    merkt die Wahl, und die Sammelkarte bietet sie als Ziel an."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs_mit_ziel(state, Vorgabe(SKALA, 7))
    ergebnis = await _bis_zum_ergebnis(u, kurs, kapitel, block, kaefer, wdh="")
    karte = _daten(ergebnis, "planwert_karte")
    assert not karte.visible  # noch kein Wert: Die Wiederholungen fehlen
    _tippen(_daten(ergebnis, "test_wdh"), "22")
    assert karte.visible and _daten(karte, "planwert_test").value == "Dein Test: 22 Wdh."
    # vorgewählt: was der Kurs sagt — 80 %, daneben die Zahl
    assert _daten(karte, "planwert_weg").selected == [ANTEIL]
    assert _daten(karte, "planwert_anteil").visible and not _daten(karte, "planwert_hand").visible
    assert _daten(karte, "planwert_prozent").value == "80"
    assert _daten(karte, "planwert_ergibt").value == "= 18 Wdh."
    satz = _daten(karte, "planwert_satz")
    assert satz.value == "Der Plan nimmt 18 Wdh."
    assert "Dein Eintrag vom Test bleibt, wie er ist." in _texte(karte)
    assert state.kurs_test.planwahl is None  # die Vorgabe: nichts zu merken

    # Anteil mit Klick und per Tastatur
    await klick(_daten(karte, "planwert_prozent_plus"))
    assert _daten(karte, "planwert_prozent").value == "85" and "19 Wdh." in satz.value
    _tippen(_daten(karte, "planwert_prozent"), "50")
    assert "Der Plan nimmt 11 Wdh." in satz.value
    assert (state.kurs_test.planwahl.wie, state.kurs_test.planwahl.anteil) == (ANTEIL, 0.5)

    # ganz
    _weg(karte, GANZ)
    assert "Der Plan nimmt 22 Wdh." in satz.value and not _daten(karte, "planwert_anteil").visible

    # von Hand: beginnt bei der Zahl, die dastand; − / + und Tastatur
    _weg(karte, HAND)
    zahl = _daten(karte, "planwert_zahl")
    assert _daten(karte, "planwert_hand").visible and zahl.value == "22"
    await klick(_daten(karte, "planwert_zahl_minus"))
    assert zahl.value == "21" and "21 Wdh." in satz.value
    _tippen(zahl, "20")
    assert "Der Plan nimmt 20 Wdh." in satz.value
    _tippen(zahl, "")  # eine leere Eingabe ändert nichts — beim Verlassen steht die Zahl wieder da
    assert "Der Plan nimmt 20 Wdh." in satz.value
    zahl.on_blur(SimpleNamespace(control=zahl))
    assert zahl.value == "20"

    # ändern sich die Wiederholungen, bleibt die Zahl von Hand — der Test darüber folgt
    _tippen(_daten(ergebnis, "test_wdh"), "24")
    assert _daten(karte, "planwert_test").value == "Dein Test: 24 Wdh."
    assert "Der Plan nimmt 20 Wdh." in satz.value

    # die Wahl überlebt den Neuaufbau der Ansicht
    wieder = _daten(_ansicht(u, kurs, kapitel, block, kaefer), "planwert_karte")
    assert _daten(wieder, "planwert_weg").selected == [HAND]
    assert _daten(wieder, "planwert_zahl").value == "20"

    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    (eintrag,) = _eintraege(state, kaefer)
    assert eintrag.result["reps"] == [24]  # der Eintrag bleibt, wie er gemacht wurde
    variable = state.kurse.variablen(kurs.id, state.profil.id)["test"]
    assert (variable.wert, variable.wie, variable.hand, variable.schwebt) == (
        24.0,
        HAND,
        20.0,
        False,
    )

    # im Kapitel: die Wahl unter dem Wert, und die Sammelkarte bietet sie als Ziel an
    danach = _kapitel(u, kurs, kapitel)
    assert _daten(danach, "testwert").value == "24 Wdh."
    assert _daten(danach, ("planwert", "test")).value == "Für den Plan: 20 Wdh. — von Hand"
    texte = _texte(danach)
    assert "Ziel für Käfer: 20 Wiederholungen" in texte
    assert "dein Wert von Hand (20 Wdh.) — Test: 24 Wdh. bis Anstrengung 7" in texte


async def test_ohne_wahl_rechnet_der_kurs_wie_bisher(umgebung) -> None:
    """Wer die Karte nicht anfasst — oder wieder wählt, was der Kurs sagt —, hinterlässt keine
    Wahl: Der Kurs rechnet wie bisher, die Sammelkarte nennt seine Regel."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs_mit_ziel(state, Vorgabe(SKALA, 7))
    ergebnis = await _bis_zum_ergebnis(u, kurs, kapitel, block, kaefer)
    karte = _daten(ergebnis, "planwert_karte")
    _weg(karte, GANZ)
    assert state.kurs_test.planwahl is not None
    _weg(karte, ANTEIL)  # wieder 80 %: die Vorgabe des Kurses
    assert state.kurs_test.planwahl is None
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    assert state.kurse.variablen(kurs.id, state.profil.id)["test"].wie == ""
    danach = _kapitel(u, kurs, kapitel)
    assert not _hat(danach, ("planwert", "test"))
    texte = _texte(danach)
    assert "Ziel für Käfer: 18 Wiederholungen" in texte
    assert "80 % von deinem Test (22 Wdh. bis Anstrengung 7)" in texte


async def test_wert_aendern_im_kapitel(umgebung) -> None:
    """Skizze W3: „Wert ändern“ an der Testkarte klappt die Karte auf; „Übernehmen“ merkt die
    Wahl, „Abbrechen“ nicht. Wer wieder wählt, was der Kurs sagt, ist die Wahl los. Am Plan
    ändert sich dabei nichts — das Ziel steht in der Sammelkarte zum Übernehmen."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs_mit_ziel(state, Vorgabe(SKALA, 7))
    ergebnis = await _bis_zum_ergebnis(u, kurs, kapitel, block, kaefer)
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    profil = state.profil.id

    ansicht = _kapitel(u, kurs, kapitel)
    assert not _hat(ansicht, ("planwert_karte", "test"))  # erst auf Tipp
    await klick(_daten(ansicht, ("wert_aendern", "test")))
    karte = _daten(ansicht, ("planwert_karte", "test"))
    assert _daten(karte, ("planwert_weg", "test")).selected == [ANTEIL]  # die Vorgabe: 80 %
    # Abbrechen: zu, nichts gemerkt
    _weg(karte, GANZ, "test")
    await klick(_daten(karte, ("planwert_abbrechen", "test")))
    assert not _hat(ansicht, ("planwert_karte", "test"))
    assert state.kurse.planwerte(kurs.id, profil, {"test": 22.0}) == {}

    # von Hand, übernehmen
    await klick(_daten(ansicht, ("wert_aendern", "test")))
    karte = _daten(ansicht, ("planwert_karte", "test"))
    _weg(karte, HAND, "test")
    await klick(_daten(karte, ("planwert_zahl_plus", "test")))
    await klick(_daten(karte, ("planwert_zahl_plus", "test")))
    assert _daten(karte, ("planwert_zahl", "test")).value == "20"
    await klick(_daten(karte, ("planwert_uebernehmen", "test")))
    (gewaehlt,) = state.kurse.planwerte(kurs.id, profil, {"test": 22.0}).values()
    assert (gewaehlt.wie, gewaehlt.wert) == (HAND, 20)
    danach = _kapitel(u, kurs, kapitel)
    assert _daten(danach, ("planwert", "test")).value == "Für den Plan: 20 Wdh. — von Hand"
    assert "Ziel für Käfer: 20 Wiederholungen" in _texte(danach)
    assert state.kurse.kursplan(kurs, profil) is None  # am Plan hat sich nichts geändert

    # die Karte öffnet mit der Wahl; zurück zu dem, was der Kurs sagt: Die Wahl ist weg
    await klick(_daten(danach, ("wert_aendern", "test")))
    karte = _daten(danach, ("planwert_karte", "test"))
    assert _daten(karte, ("planwert_weg", "test")).selected == [HAND]
    _weg(karte, ANTEIL, "test")
    assert _daten(karte, ("planwert_prozent", "test")).value == "80"
    await klick(_daten(karte, ("planwert_uebernehmen", "test")))
    assert state.kurse.planwerte(kurs.id, profil, {"test": 22.0}) == {}
    assert "Ziel für Käfer: 18 Wiederholungen" in _texte(_kapitel(u, kurs, kapitel))


async def test_ohne_ziel_im_plan_keine_karte(umgebung) -> None:
    """Hinterlässt ein Test nur seinen Wert (kein Baustein nimmt ihn, das Kapitel hat keine
    Plan-Vorlage), gibt es weder die Karte noch „Wert ändern“."""
    u = umgebung
    state = u.state
    kurs, kapitel, block, kaefer = _kurs(state, Vorgabe(SKALA, 7))
    ergebnis = await _bis_zum_ergebnis(u, kurs, kapitel, block, kaefer)
    assert not _hat(ergebnis, "planwert_karte")
    await klick(_daten(ergebnis, "test_eintragen"))
    await _bis_vorbei(u)
    assert not _hat(_kapitel(u, kurs, kapitel), ("wert_aendern", "test"))


async def test_wert_fuer_den_plan_im_kapitelplan_mit_zeit(umgebung) -> None:
    """Kapitelplan, Test ohne Lauf, Feld mit Zeit: Die Karte wählt vor, was der Test sagt
    (80 %), „von Hand“ geht in 5-Sekunden-Schritten und steht als m:ss im Feld; „Plan anlegen“
    nimmt die Wahl. Danach steht das Ziel im Plan — „Wert ändern“ gibt es nicht mehr."""
    u = umgebung
    state = u.state
    planke = Exercise(name="Planke", result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    state.uebungen.speichern(planke)
    kurs = Kurs(
        name="Halten",
        kapitel=[
            Kapitel(
                titel="Wie lange?",
                plaene=[PlanVorlage("Halten", [0, 2, 4], [VorlageItem(planke.id)])],
                bloecke=[Block(TEST, id="t", uebung=planke.id, feld="hold", faktor=0.8)],
            )
        ],
    )
    state.kurse.speichern(kurs)
    kurs = state.kurse.laden(kurs.id)
    kapitel = kurs.kapitel[0]
    _erreichen(state, kurs, kapitel)
    profil = state.profil.id
    sitzung = state.sitzungen.session_fuer(profil, None, lokaler_tag(UTC0))
    state.sitzungen.eintrag_anlegen(sitzung, planke, {"hold": [50]}, started_at=UTC0)

    ansicht = _kapitel(u, kurs, kapitel)
    assert any("Im Plan wird daraus das Ziel: 40s Haltezeit." in t for t in _texte(ansicht))
    await klick(_daten(ansicht, ("wert_aendern", "t")))
    karte = _daten(ansicht, ("planwert_karte", "t"))
    assert _daten(karte, ("planwert_weg", "t")).selected == [ANTEIL]
    assert _daten(karte, ("planwert_ergibt", "t")).value == "= 40s Haltezeit"
    _weg(karte, HAND, "t")
    zahl = _daten(karte, ("planwert_zahl", "t"))
    assert zahl.value == "0:40" and zahl.keyboard_type == ft.KeyboardType.DATETIME
    await klick(_daten(karte, ("planwert_zahl_plus", "t")))
    assert zahl.value == "0:45"
    _tippen(zahl, "1:05")
    assert _daten(karte, ("planwert_satz", "t")).value == "Der Plan nimmt 1:05 Haltezeit."
    await klick(_daten(karte, ("planwert_zahl_minus", "t")))
    assert zahl.value == "1:00"
    await klick(_daten(karte, ("planwert_uebernehmen", "t")))

    # die Wahl hält den Testwert nicht fest (Test ohne Lauf): Er bleibt der jüngste Eintrag
    variable = state.kurse.variablen(kurs.id, profil)["t"]
    assert variable.schwebt and (variable.wie, variable.hand) == (HAND, 60.0)
    danach = _kapitel(u, kurs, kapitel)
    assert _daten(danach, ("planwert", "t")).value == "Für den Plan: 1:00 Haltezeit — von Hand"
    assert any("Im Plan wird daraus das Ziel: 1:00 Haltezeit." in t for t in _texte(danach))

    await klick(_daten(danach, "plan_anlegen"))
    (plan,) = state.kurse.kapitel_plaene(kapitel.id, profil)
    assert plan.items[0].target == {"hold": [60]}  # nicht 40 (80 % von 50)
    fertig = _kapitel(u, kurs, kapitel)
    assert not _hat(fertig, ("wert_aendern", "t"))  # das Ziel steht im Plan
