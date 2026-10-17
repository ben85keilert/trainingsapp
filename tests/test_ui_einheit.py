"""Einheit in der Oberfläche: Bereitstellen, Startleiste, Alle starten, Laufleiste (17.10.2026)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.einheit import Rolle, Zustand  # noqa: E402
from trainingsapp.core.timer import Abschnitt, TimerLauf, TimerProfil  # noqa: E402
from trainingsapp.ui import einheit as einheit_ui  # noqa: E402
from trainingsapp.ui.components.startleiste import (  # noqa: E402
    einheit_reiter,
    leiste_auffrischen,
    leiste_einsetzen,
    startleiste,
)
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.timer import lauf_fuer, timer_view  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path / "daten"))
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


class Seite(SimpleNamespace):
    """Stellvertreter für `ft.Page`: Aufgaben laufen im Loop des Tests (wenn es einen gibt)."""

    def __init__(self) -> None:
        super().__init__(route="/", views=[], dialoge=[], aufgaben=[])

    def run_task(self, f, *args):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.aufgaben.append((f, args))
            return None
        aufgabe = loop.create_task(f(*args))
        self.aufgaben.append(aufgabe)
        return aufgabe

    def show_dialog(self, d) -> None:
        self.dialoge.append(d)

    def update(self) -> None:
        return None

    async def push_route(self, route: str) -> None:
        self.route = route


def _alle(c):
    yield c
    for name in ("content", "controls"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _knopf(c, text: str):
    for x in _alle(c):
        if isinstance(x, ft.Button | ft.FilledButton | ft.OutlinedButton | ft.TextButton):
            inhalt = x.content
            if inhalt == text or (isinstance(inhalt, ft.Text) and inhalt.value == text):
                return x
    raise AssertionError(f"kein Knopf {text!r}")


def _profil(sekunden: int = 2) -> TimerProfil:
    return TimerProfil(name="Kurz", abschnitte=[Abschnitt("A", sekunden)])


def test_ohne_einheit_keine_leiste(state) -> None:
    assert startleiste(Seite(), state) is None


def _start(c):
    """▶ der Infoleiste."""
    (knopf,) = [x for x in _alle(c) if isinstance(x, ft.FilledIconButton)]
    return knopf


def test_timer_bereitstellen_zeigt_infoleiste_und_startkarte(state) -> None:
    page = Seite()
    gezeichnet: list[int] = []
    state.neu_zeichnen = lambda: gezeichnet.append(1)
    ansicht = timer_view(page, state, "/")
    _knopf(ansicht, "Bereitstellen").on_click()
    assert einheit_ui.bereitgestellt(state, "timer") and gezeichnet
    # Auf jeder anderen Seite nur eine Zeile (Ben, 17.10.2026: „der halbe Screen“)
    leiste = startleiste(page, state)
    assert leiste is not None and leiste.visible is not False
    assert "Bereit" in _texte(leiste)
    assert not _start(leiste).disabled  # ein Timer ist sofort bereit
    # Ausführlich im Reiter „Einheit“ auf „Heute“
    karte = einheit_reiter(page, state)
    texte = _texte(karte)
    assert "Bereitgestellt" in texte and any(t.startswith("Timer · ") for t in texte)
    assert not _knopf(karte, "Alle starten").disabled
    # In der Timer-Ansicht heißt der Knopf jetzt „Bereitgestellt“ — ein Tipp nimmt ihn heraus
    _knopf(timer_view(page, state, "/"), "Bereitgestellt").on_click()
    assert state.einheit is None and startleiste(page, state) is None


def test_leiste_steht_fest_ueber_einer_scrollenden_ansicht() -> None:
    ansicht = ft.View(route="/x", scroll=ft.ScrollMode.AUTO, padding=16, controls=[ft.Text("a")])
    leiste = ft.Container()
    leiste_einsetzen(ansicht, leiste)
    assert ansicht.scroll is None and ansicht.controls[0] is leiste
    inhalt = ansicht.controls[1]
    assert isinstance(inhalt, ft.Column) and inhalt.scroll == ft.ScrollMode.AUTO
    assert [c.value for c in inhalt.controls] == ["a"]
    haupt = ft.View(route="/", padding=0, controls=[ft.Text("b")])
    leiste_einsetzen(haupt, zweite := ft.Container())
    assert haupt.controls[0] is zweite and zweite.margin is not None  # eigener Rand


async def test_alle_starten_laufleiste_und_ende_mit_dem_timer(state) -> None:
    page = Seite()
    state.neu_zeichnen = lambda: None
    lauf = lauf_fuer(state, _profil(2))
    einheit_ui.timer_bereitstellen(page, state, lauf)
    await asyncio.sleep(0)  # vorbereiten
    e = state.einheit
    e.ende_mit_timer = True
    assert einheit_ui.alle_starten(page, state, 0.0) is e
    assert e.zustand is Zustand.LAEUFT and lauf.laeuft and state.timer is lauf
    assert einheit_ui.besitzt_timer(state, lauf)
    # Gehört der Timer einer Einheit, tauscht ihn auch ein anderes Profil nicht aus
    assert lauf_fuer(state, _profil(9)) is lauf
    leiste = startleiste(page, state)
    assert leiste is not None and any(
        t.startswith("0:00 · A (") or t.startswith("0:0") for t in _texte(leiste)
    )
    symbole = [x.icon for x in _alle(leiste) if isinstance(x, ft.IconButton)]
    assert ft.Icons.PAUSE in symbole and ft.Icons.STOP in symbole
    # Der Takt läuft, der Timer endet nach 2 s — und mit ihm die Einheit
    await asyncio.wait_for(
        asyncio.gather(*[a for a in page.aufgaben if isinstance(a, asyncio.Task)]), 6
    )
    assert e.zustand is Zustand.BEENDET and state.einheit is None
    zeitleiste = state.einheiten.ereignisse(e.id)
    assert [(x.quelle, x.art) for x in zeitleiste] == [
        ("einheit", "start"),
        ("timer", "abschnitt"),
        ("timer", "ende"),
        ("einheit", "ende"),
    ]


async def test_alles_beenden_mitten_im_timer(state) -> None:
    page = Seite()
    state.neu_zeichnen = lambda: None
    lauf = lauf_fuer(state, _profil(60))
    einheit_ui.timer_bereitstellen(page, state, lauf)
    e = state.einheit
    einheit_ui.alle_starten(page, state, 0.0)
    await asyncio.sleep(0.05)
    einheit_ui.anhalten_oder_weiter(page, state)
    assert not lauf.laeuft  # ⏸ hält den Timer an
    einheit_ui.alle_beenden(state)
    await asyncio.wait_for(
        asyncio.gather(*[a for a in page.aufgaben if isinstance(a, asyncio.Task)]), 6
    )
    arten = [(x.quelle, x.art) for x in state.einheiten.ereignisse(e.id)]
    assert arten[-2:] == [("timer", "ende"), ("einheit", "ende")]
    assert ("timer", "pause") in arten
    assert state.einheit is None


def test_rolle_der_hrv_ohne_aufnahme_ist_mitstarten(state) -> None:
    """Ohne Gurt gibt es nichts bereitzustellen."""
    assert einheit_ui.hrv_bereitstellen(Seite(), state) is None
    assert Rolle.MITSTARTEN.value == "mitstarten"


def test_laufende_einheit_steht_in_der_benachrichtigung(state) -> None:
    from trainingsapp.ui.laufend import laufendes

    page = Seite()
    state.neu_zeichnen = lambda: None
    einheit_ui.timer_bereitstellen(page, state, TimerLauf(_profil(30)))
    assert not [x for x in laufendes(state) if x.titel == "Einheit"]  # erst nach dem Start
    state.einheit.titel = "Kurz"
    state.einheit.starten()
    (zeile,) = [x for x in laufendes(state) if x.titel == "Einheit"]
    assert zeile.zeile.startswith("Kurz: 0:00 · A") and zeile.kurz == "Einheit 0:00"
    state.einheit.beenden()


async def test_startkarte_zeigt_den_stand_der_vorbereitung(state) -> None:
    """Während das GPS Empfang sucht, frischt die Startkarte jede Sekunde auf — die
    Genauigkeit an Ort und Stelle (Knöpfe bleiben, kein Tipp geht verloren), bei
    „bereit“ baut sie neu und gibt „Alle starten“ frei."""
    from attrappen import Empfaenger, Uhr, ruhe

    seite = Seite()
    uhr = Uhr()
    gps = Empfaenger(uhr)
    einheit_ui.ausdauer_bereitstellen(seite, state, "laufen", gps)
    await ruhe()
    leiste = einheit_reiter(seite, state)
    knopf = _knopf(leiste, "Alle starten")
    assert knopf.disabled and "sucht Empfang …" in _texte(leiste)
    gps.ortung(0, genauigkeit_m=50)
    await ruhe()
    einheit_ui.melden(state)  # das tut der Sekundentakt der Vorbereitung
    assert "sucht Empfang … 50 m" in _texte(leiste)
    assert _knopf(leiste, "Alle starten") is knopf  # nur der Text, kein Neubau
    gps.ortung(0, genauigkeit_m=6)
    await ruhe()
    einheit_ui.melden(state)
    assert "Empfang gut · 6 m" in _texte(leiste)
    assert not _knopf(leiste, "Alle starten").disabled
    einheit_ui.leeren(seite, state)
    await asyncio.sleep(0)


async def test_infoleiste_zeigt_den_stand_und_oeffnet_den_reiter(state) -> None:
    """Skizze 16: die Teile als Symbole (der nicht bereite mit Rand), „1 von 2 bereit“,
    der Stand des langsamsten Teils, ▶ erst, wenn alles bereit ist; Antippen öffnet „Heute“
    im Reiter „Einheit“."""
    from attrappen import Empfaenger, Uhr, ruhe

    seite = Seite()
    gezeichnet: list[int] = []
    state.neu_zeichnen = lambda: gezeichnet.append(1)
    gps = Empfaenger(Uhr())
    einheit_ui.ausdauer_bereitstellen(seite, state, "laufen", gps)
    einheit_ui.timer_bereitstellen(seite, state, TimerLauf(_profil(60)))
    await ruhe()
    leiste = startleiste(seite, state)
    assert leiste is not None
    texte = _texte(leiste)
    assert "1 von 2 bereit" in texte and "GPS sucht Empfang …" in texte
    symbole = [x for x in _alle(leiste) if isinstance(x, ft.Container) and x.width == 26]
    assert [s.border is not None for s in symbole] == [True, False]  # GPS sucht noch
    assert _start(leiste).disabled
    gps.ortung(0, genauigkeit_m=50)
    await ruhe()
    einheit_ui.melden(state)
    assert "GPS sucht Empfang … 50 m" in _texte(leiste)
    gps.ortung(0, genauigkeit_m=6)
    await ruhe()
    einheit_ui.melden(state)
    assert "Alles bereit" in _texte(leiste) and not _start(leiste).disabled
    state.reiter = "messung"
    await leiste.on_click()
    assert state.reiter == "heute" and gezeichnet
    assert einheit_ui.heute_reiter(state) == einheit_ui.REITER_EINHEIT
    einheit_ui.leeren(seite, state)
    await asyncio.sleep(0)


def test_heute_hat_den_reiter_einheit_nur_mit_einheit(state) -> None:
    """Reiterregel (Ben, 17.10.2026): Erscheint eine Einheit oder beginnt sie, öffnet
    „Heute“ auf „Einheit“; wer auf den Tag wechselt, bleibt dort bis zur nächsten Änderung."""
    from trainingsapp.ui.views.heute import heute

    page = Seite()
    state.neu_zeichnen = lambda: None
    assert not isinstance(heute(page, state), ft.Tabs)
    einheit_ui.timer_bereitstellen(page, state, TimerLauf(_profil(60)))
    reiter = heute(page, state)
    assert isinstance(reiter, ft.Tabs) and reiter.selected_index == einheit_ui.REITER_EINHEIT
    assert "Bereitgestellt" in _texte(reiter)
    reiter.on_change(SimpleNamespace(control=SimpleNamespace(selected_index=1)))
    tag = heute(page, state)
    assert tag.selected_index == einheit_ui.REITER_TAG and "STEHT AN" in _texte(tag)
    assert heute(page, state).selected_index == einheit_ui.REITER_TAG  # bleibt
    einheit_ui.alle_starten(page, state, 0.0)
    lauf = heute(page, state)
    assert lauf.selected_index == einheit_ui.REITER_EINHEIT  # sie beginnt: wieder „Einheit“
    assert "Timer · Kurz" in _texte(lauf) and "0:00 von 1:00" in _texte(lauf)
    state.einheit.beenden()
    assert not isinstance(heute(page, state), ft.Tabs)


def test_feste_leiste_auf_heute_nur_im_reiter_des_tages_und_im_lauf(state) -> None:
    page = Seite()
    state.neu_zeichnen = lambda: None
    einheit_ui.timer_bereitstellen(page, state, TimerLauf(_profil(60)))
    state.reiter = "heute"
    leiste = startleiste(page, state, haupt=True)
    assert leiste is not None and leiste.visible is False  # im Reiter „Einheit“ steht alles
    einheit_ui.heute_reiter_waehlen(state, einheit_ui.REITER_TAG)
    leiste_auffrischen(state)
    assert leiste.visible is False  # bereitgestellt: der Tag wie sonst
    state.reiter = "messung"  # die Navigationsleiste wechselt, ohne neu zu bauen
    leiste_auffrischen(state)
    assert leiste.visible and "Bereit" in _texte(leiste)
    einheit_ui.alle_starten(page, state, 0.0)
    state.reiter = "heute"
    einheit_ui.heute_reiter_waehlen(state, einheit_ui.REITER_TAG)
    leiste = startleiste(page, state, haupt=True)
    assert leiste is not None and leiste.visible
    assert ft.Icons.STOP in [x.icon for x in _alle(leiste) if isinstance(x, ft.IconButton)]
    state.einheit.beenden()


async def test_einheit_beenden_laesst_sich_im_lauf_abwaehlen(state) -> None:
    """„Man kann einstellen, dass die Einheit mit dem Timer endet. Das soll nachträglich
    auch deaktiviert werden können“ (Ben, 17.10.2026) — in der Übersicht."""
    page = Seite()
    state.neu_zeichnen = lambda: None
    einheit_ui.ausdauer_bereitstellen(page, state, "laufen", None)  # drinnen: gleich bereit
    einheit_ui.timer_bereitstellen(page, state, TimerLauf(_profil(1)))
    await asyncio.sleep(0)
    e = state.einheit
    e.ende_mit_timer = True  # in der Startkarte angehakt
    einheit_ui.alle_starten(page, state, 0.0)
    uebersicht = einheit_reiter(page, state)
    assert "Wenn der Timer fertig ist – auch jetzt noch änderbar" in _texte(uebersicht)
    (haken,) = [
        x for x in _alle(uebersicht) if isinstance(x, ft.Checkbox) and x.label == "Einheit beenden"
    ]
    haken.on_change(SimpleNamespace(control=SimpleNamespace(value=False)))
    assert e.ende_mit_timer is False
    assert "Sie läuft nach dem Timer weiter, bis du sie beendest." in _texte(uebersicht)
    await asyncio.sleep(1.6)
    assert e.timer is not None and e.timer.lauf.fertig
    assert e.zustand is Zustand.LAEUFT  # der Timer ist durch, die Einheit läuft weiter
    einheit_ui.melden(state)
    assert "Timer fertig" in _texte(uebersicht)
    einheit_ui.alle_beenden(state)
    await asyncio.wait_for(
        asyncio.gather(*[a for a in page.aufgaben if isinstance(a, asyncio.Task)]), 6
    )
    assert state.einheit is None
