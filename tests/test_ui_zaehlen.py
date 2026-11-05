"""Wiederholungen zählen in der Oberfläche (Ben, 4.11.2026, ``docs/plan_beschleunigung.md``
§3.4, §4): die Karte „Beschleunigungssensor“ in „Übung bearbeiten“, die Zeile an der
Übungsseite, die Zählzeile in der Karte „Eintragen“ (Knopf nur mit einem Gerät mit
Beschleunigungssensor, Zahl mit −1/+1, „Fertig“, „Zählen abbrechen“ → „Läufe heute“), Uhr und
Zählen zusammen, Abhaken im Plan und auf „Heute“, die Meldung, wenn eine andere Übung startet,
Info- und Laufleiste, die Marken-Leiste im Diagnosemodus.

Der Brustgurt der Attrappen ist ein H10 mit Beschleunigung — eine Wiederholung je 2,5 s
(`attrappen.Gurt`)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from attrappen import Gurt, Seite, Uhr, ruhe, vorbei  # noqa: E402
from trainingsapp.core import zaehlen_eintrag as ze  # noqa: E402
from trainingsapp.core.models import Exercise, Plan, PlanItem  # noqa: E402
from trainingsapp.core.result_spec import Layout, ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.core.zaehlen import ENDE_ABBRUCH, ENDE_FERTIG, SensorWahl  # noqa: E402
from trainingsapp.devices.messlauf import Messlauf  # noqa: E402
from trainingsapp.devices.profiles import UHR_BROADCAST  # noqa: E402
from trainingsapp.devices.zaehlen import ZaehlBaustein  # noqa: E402
from trainingsapp.ui import einheit as einheit_ui  # noqa: E402
from trainingsapp.ui import uebung_lauf  # noqa: E402
from trainingsapp.ui.components import zaehl_stand  # noqa: E402
from trainingsapp.ui.components.zaehlen import zaehl_zeile  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.plan import einzel_plan, plan_view  # noqa: E402

MEHR, WENIGER = "Eine Wiederholung mehr", "Eine Wiederholung weniger"
ATEM_MEHR, ATEM_WENIGER = "Ein Atemzug mehr", "Ein Atemzug weniger"


@pytest.fixture
async def umgebung(tmp_path, monkeypatch):
    """App-Zustand mit verbundenem H10 (Beschleunigung) und laufender HRV-Aufnahme — wie in
    ``test_ui_uhr``; die Uhr der Attrappe wird die der Einheit."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    uhr = Uhr()
    gurt = Gurt(uhr)
    lauf = Messlauf(gurt, jetzt_utc=uhr.utc, backup_basis=tmp_path, subject_id=state.profil.id)
    await lauf.verbinden("gurt", "Polar H10 TEST")
    lesen = asyncio.create_task(lauf.laufen())
    state.messlauf = lauf
    lauf.aufnahme_starten()
    yield state, uhr, gurt
    await lauf.trennen()
    await asyncio.wait_for(lesen, 5)
    state.schliessen()


@pytest.fixture
def formular(tmp_path, monkeypatch):
    """Für „Übung bearbeiten“: App-Zustand ohne Gerät und eine Seite, die Routen merkt."""
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    state.neu_zeichnen = lambda: None
    routen: list[str] = []
    dialoge: list = []

    async def push_route(route: str) -> None:
        routen.append(route)

    page = SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: dialoge.pop() if dialoge else None,
        push_route=push_route,
        run_task=lambda f, *a: None,
    )
    yield page, state
    state.schliessen()


# -- Helfer ------------------------------------------------------------------------------


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "label",
        "leading",
        "items",
        "title",
        "subtitle",
        "trailing",
        "actions",
        "appbar",
        "segments",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


KNOEPFE = ft.FilledButton | ft.OutlinedButton | ft.FilledTonalButton | ft.TextButton


def _knoepfe(c, text: str) -> list:
    return [
        x
        for x in _alle(c)
        if isinstance(x, KNOEPFE)
        and (text == x.content or (isinstance(x.content, ft.Control) and text in _texte(x.content)))
    ]


def _knopf(c, text: str):
    gefunden = _knoepfe(c, text)
    if not gefunden:
        raise AssertionError(f"kein Knopf {text!r}")
    return gefunden[0]


def _nachtragen(c) -> list:
    """„Nachtragen“ eines Laufs in der Karte „Eintragen“ (`components.laeufe_heute`)."""
    return _knoepfe(c, "Nachtragen")


def _flaechen(c, tipp: str) -> list[ft.Container]:
    return [x for x in _alle(c) if isinstance(x, ft.Container) and x.tooltip == tipp]


def _symbol(c, icon, tipp: str = ""):
    return next(
        x
        for x in _alle(c)
        if isinstance(x, ft.IconButton) and x.icon == icon and tipp in (x.tooltip or "")
    )


def _kniebeuge(state, name: str = "Kniebeuge", *felder: str, **mehr) -> Exercise:
    keys = felder or ("reps",)
    spec = ResultSpec(layout=Layout.SINGLE, fields=[f for k in keys if (f := vorrat_feld(k))])
    u = Exercise(name=name, result_spec=spec, **mehr)
    state.uebungen.speichern(u)
    return u


def _ansicht(seite, state, uebung):
    return plan_view(seite, state, einzel_plan(uebung), einzel=True)


async def _sekunden(state, uhr, gurt, n: int) -> None:
    """``n`` Sekunden: Schlag, Beschleunigung bis zur Uhr, ein Takt der Einheit, die
    Oberfläche frischt nach (wie ``_anzeigen`` jede Sekunde)."""
    for _ in range(n):
        uhr.t += 1
        gurt.schlag(1000)
        gurt.beschleunigung()
        await ruhe()
        e = state.einheit
        if e is not None and e.laeuft:
            e.takt()
            einheit_ui.melden(state)


async def _bis_vorbei(state, uhr, gurt) -> None:
    for _ in range(300):
        if vorbei(state):
            return
        await _sekunden(state, uhr, gurt, 1)
        await asyncio.sleep(0.01)
    raise AssertionError("Die Einheit endete nicht")


def _eintraege(state):
    return [e for e, _ in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())]


def _zaehl_teil(state) -> ZaehlBaustein:
    z = state.einheit.teil("zaehlen")
    assert isinstance(z, ZaehlBaustein)
    return z


# -- Übung bearbeiten und Übungsseite ------------------------------------------------------


def test_karte_beschleunigungssensor_speichert_nur_was_man_umlegt(formular) -> None:
    """Die Karte nach „Uhr und Timer“: kleine Schalter „Wiederholungen“ (nie „Wdh.“) und
    „Atmung“, „Bewegung: Automatisch“, „Zählt in“ erst bei zwei Wiederholungsfeldern,
    „Prototyp“ und das (i). Unberührt bleibt die Wahl leer — eine Paketübung gilt sonst als
    geändert; umgelegt wird sie gespeichert."""
    from trainingsapp.ui.components.hilfe import THEMEN
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    page, state = formular
    u = _kniebeuge(state, "Kniebeuge", "reps", "weight")
    ansicht = uebung_bearbeiten(page, state, u)
    texte = _texte(ansicht)
    assert texte.index("UHR UND TIMER") < texte.index("BESCHLEUNIGUNGSSENSOR")
    assert texte.index("BESCHLEUNIGUNGSSENSOR") < texte.index("VIDEOS UND LINKS")
    assert "Prototyp" in texte
    (bewegung,) = [x for x in _alle(ansicht) if isinstance(x, ft.Dropdown)]
    assert bewegung.value == "auto" and [o.text for o in bewegung.options] == [
        "Automatisch",
        "Kniebeuge",
        "Liegestütz",
    ]
    assert any(t.startswith("Umkehrpunkt oben — die Hauptachse") for t in texte)
    hilfen = [
        x.tooltip
        for x in _alle(ansicht)
        if isinstance(x, ft.IconButton) and x.icon == ft.Icons.HELP_OUTLINE
    ]
    assert THEMEN["beschleunigung"][2] in hilfen
    schalter = {x.label: x for x in _alle(ansicht) if isinstance(x, ft.Switch)}
    wdh, atmung = schalter["Wiederholungen"], schalter["Atmung"]
    assert not [x for x in schalter if "Wdh" in (x or "")]
    assert wdh.value and not wdh.disabled and not atmung.value  # Vorgabe: Feld da, Typ fehlt
    assert any("„Wdh. zählen“" in t for t in _texte(ansicht))
    # „Zählt in“ nur bei zwei Wiederholungsfeldern
    (zaehlt_in,) = [
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Row)
        and x.controls
        and isinstance(x.controls[0], ft.Text)
        and x.controls[0].value == "Zählt in"
    ]
    assert not zaehlt_in.visible
    # Unberührt: nichts geändert, nichts gespeichert
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(u.id).beschleunigung == SensorWahl()
    # Atmung an, Wiederholungen aus → gespeichert; der Knopf heißt dann „Atmung erfassen“
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(u.id))
    schalter = {x.label: x for x in _alle(ansicht) if isinstance(x, ft.Switch)}
    schalter["Atmung"].value = True
    schalter["Atmung"].on_change()
    schalter["Wiederholungen"].value = False
    schalter["Wiederholungen"].on_change()
    assert any("„Atmung erfassen“" in t for t in _texte(ansicht))
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(u.id).beschleunigung == SensorWahl(
        wiederholungen=False, atmung=True
    )
    # Zurück auf die Vorgabe: wieder „wie die Übung“ (die explizite Wahl bleibt, wo sie war)
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(u.id))
    schalter = {x.label: x for x in _alle(ansicht) if isinstance(x, ft.Switch)}
    assert not schalter["Wiederholungen"].value and schalter["Atmung"].value
    schalter["Wiederholungen"].value = True
    schalter["Wiederholungen"].on_change()
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(u.id).beschleunigung.wiederholungen is True


def test_bewegung_waehlt_die_vorlage_und_laesst_unbekannte_in_ruhe(formular) -> None:
    """A5: „Bewegung“ bietet Automatisch, Kniebeuge, Liegestütz (`VORLAGEN_ANGEBOT`) mit dem
    Hinweis je Vorlage; gewählt wird gespeichert, unberührt bleibt, was war — auch ein
    Schlüssel, den diese App nicht anbietet (ein Paket, ein neueres hrv-core): er zeigt
    „Automatisch“ und wird beim Speichern nicht überschrieben."""
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    page, state = formular
    u = _kniebeuge(state, "Kniebeuge", "reps")
    ansicht = uebung_bearbeiten(page, state, u)
    (bewegung,) = [x for x in _alle(ansicht) if isinstance(x, ft.Dropdown)]
    bewegung.value = "kniebeuge"
    bewegung.on_select()
    assert any(t == "Umkehrpunkt oben — nur für den Brustgurt geprüft" for t in _texte(ansicht))
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(u.id).beschleunigung == SensorWahl(vorlage="kniebeuge")
    # Wieder geöffnet: die Wahl steht da; zurück auf Automatisch wird gespeichert
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(u.id))
    (bewegung,) = [x for x in _alle(ansicht) if isinstance(x, ft.Dropdown)]
    assert bewegung.value == "kniebeuge"
    bewegung.value = "auto"
    bewegung.on_select()
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(u.id).beschleunigung == SensorWahl()
    # Ein unbekannter Schlüssel bleibt, solange man nichts wählt
    fremd = _kniebeuge(state, "Rudern", "reps", beschleunigung=SensorWahl(vorlage="rudern"))
    ansicht = uebung_bearbeiten(page, state, fremd)
    (bewegung,) = [x for x in _alle(ansicht) if isinstance(x, ft.Dropdown)]
    assert bewegung.value == "auto"
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(fremd.id).beschleunigung == SensorWahl(vorlage="rudern")
    bewegung.value = "liegestuetz"
    bewegung.on_select()
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(fremd.id).beschleunigung == SensorWahl(vorlage="liegestuetz")


def test_zaehlt_in_bei_zwei_feldern_und_ausgegraut_ohne_feld(formular) -> None:
    """Zwei Wiederholungsfelder (P106): „Zählt in“ unter den Namen der Karten — die Wahl des
    ersten bleibt leer. Ohne Wiederholungsfeld ist der Schalter ausgegraut; Atmung beim Typ
    „Atmung“ von selbst an."""
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    page, state = formular
    u = _kniebeuge(state, "Ausfallschritt", "reps", "reps_2")
    ansicht = uebung_bearbeiten(page, state, u)
    wahl = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.SegmentedButton) and {s.value for s in x.segments} == {"reps", "reps_2"}
    )
    zeile = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Row) and wahl in x.controls and isinstance(x.controls[0], ft.Text)
    )
    assert zeile.visible and wahl.selected == ["reps"]
    wahl.selected = ["reps_2"]
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(u.id).beschleunigung == SensorWahl(feld="reps_2")

    atem = _kniebeuge(state, "Box Breathing", "duration", typen=["Atmung"])
    ansicht = uebung_bearbeiten(page, state, atem)
    schalter = {x.label: x for x in _alle(ansicht) if isinstance(x, ft.Switch)}
    assert schalter["Wiederholungen"].disabled and not schalter["Wiederholungen"].value
    assert schalter["Atmung"].value
    asyncio.run(_knopf(ansicht, "Speichern").on_click())
    assert state.uebungen.laden(atem.id).beschleunigung == SensorWahl()


def test_uebungsseite_zeigt_den_sensor_nur_wenn_er_an_ist(formular) -> None:
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    page, state = formular
    browser = SimpleNamespace(launch_url=None)
    u = _kniebeuge(state, "Kniebeuge", typen=["Atmung"])
    texte = _texte(uebung_detail(page, state, u, browser))
    assert "BESCHLEUNIGUNGSSENSOR" in texte
    assert "Wiederholungen · Atmung" in texte and "Prototyp" in texte
    kb = _kniebeuge(state, "Kniebeuge", beschleunigung=SensorWahl(vorlage="kniebeuge"))
    assert "Prototyp · Kniebeuge" in _texte(uebung_detail(page, state, kb, browser))
    planke = _kniebeuge(state, "Planke", "hold")
    texte = _texte(uebung_detail(page, state, planke, browser))
    assert "Wiederholungen · Atmung" not in texte and "Atmung" not in texte


# -- Die Zählzeile -----------------------------------------------------------------------


async def test_knopf_nur_mit_beschleunigungssensor(umgebung) -> None:
    """Der Knopf ist die Messung mit dem Sensor (P118): nur mit verbundenem Gerät, das einen
    hat, nur mit einem Schalter an, nie beim Nachtragen. Er heißt nach der Übung."""
    state, _, _ = umgebung
    seite = Seite()
    u = _kniebeuge(state)
    ansicht = _ansicht(seite, state, u)
    assert _knopf(ansicht, "Wdh. zählen").tooltip
    # Die Zählzeile steht unter der Zeile der Uhr
    texte = _texte(ansicht)
    assert texte.index("Stoppuhr") < texte.index("Wdh. zählen")
    # Nur Haltezeit: kein Knopf — mit „Atmung“ an: „Atmung erfassen“
    planke = _kniebeuge(state, "Planke", "hold")
    assert not _knoepfe(_ansicht(seite, state, planke), "Wdh. zählen")
    planke.beschleunigung = SensorWahl(atmung=True)
    state.uebungen.speichern(planke)
    assert _knoepfe(_ansicht(seite, state, planke), "Atmung erfassen")
    # Beides aus: kein Knopf
    u.beschleunigung = SensorWahl(wiederholungen=False)
    state.uebungen.speichern(u)
    assert not _knoepfe(_ansicht(seite, state, u), "Wdh. zählen")
    u.beschleunigung = SensorWahl()
    state.uebungen.speichern(u)
    # Ein Gerät ohne Beschleunigungssensor: weder Knopf noch ±1
    lauf = state.messlauf
    lauf.profil = UHR_BROADCAST
    assert not _knoepfe(_ansicht(seite, state, u), "Wdh. zählen")
    state.messlauf = None
    assert not _knoepfe(_ansicht(seite, state, u), "Wdh. zählen")
    state.messlauf = lauf
    lauf.profil = lauf.quelle.profil
    # Beim Nachtragen nie
    nachher = zaehl_zeile(seite, state, uebung=u, plan=None, item=None, nachtrag=object())
    assert nachher is None
    assert zaehl_zeile(seite, state, uebung=u, plan=None, item=None) is not None


async def test_zaehlen_plus_minus_fertig_traegt_ein(umgebung) -> None:
    """Der Tipp startet das Zählen: „Sensor startet …“, dann die Zahl. ±1 ändert nur die Zahl
    (die Flächen bleiben dieselben, ein Tipp geht nie verloren); „Fertig“ trägt Sensor plus
    Korrektur in den offenen Eintrag, danach steht wieder der Knopf da."""
    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state)
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    e = state.einheit
    assert e is not None and e.laeuft and [t.art for t in e.teile] == ["plan", "zaehlen", "hrv"]
    # Während gezählt wird, baut nichts die Ansicht neu — weder der Takt noch ±1 (ein Tipp
    # ginge sonst verloren); die Fixture zeichnet nie neu, darum hier zählen
    neu_gebaut: list[int] = []
    state.neu_zeichnen = lambda: neu_gebaut.append(1)
    ansicht = _ansicht(seite, state, u)
    assert "Sensor startet …" in _texte(ansicht) and "Prototyp" in _texte(ansicht)
    (plus,), (minus,) = _flaechen(ansicht, MEHR), _flaechen(ansicht, WENIGER)
    assert _knoepfe(ansicht, "Fertig") and _knoepfe(ansicht, "Zählen abbrechen")
    assert not _knoepfe(ansicht, "Wdh. zählen")
    # Tooltips der Zählzeile kollidieren nicht mit den Helfern der Uhr („starten“,
    # „Abbrechen“ — `test_ui_uhr._symbol`)
    zeile = [  # die innerste Karte mit den Flächen: die Zählzeile
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and isinstance(x.content, ft.Column) and plus in _alle(x)
    ][-1]
    assert _knoepfe(zeile, "Fertig") and _knoepfe(zeile, "Zählen abbrechen")
    tipps = [str(x.tooltip) for x in _alle(zeile) if getattr(x, "tooltip", None)]
    assert tipps and not [t for t in tipps if "starten" in t or "Abbrechen" in t]

    await _sekunden(state, uhr, gurt, 30)
    z = _zaehl_teil(state)
    assert z.sensor is not None and abs(z.sensor - 12) <= 1
    zahl = next(t for t in _alle(ansicht) if isinstance(t, ft.Text) and t.size == 56)
    assert zahl.value == str(z.wert)
    assert f"Sensor {z.sensor} · Prototyp" in _texte(ansicht)
    plus.on_click()
    plus.on_click()
    minus.on_click()
    assert z.korrektur == 1 and zahl.value == str(z.sensor + 1)
    assert f"Sensor {z.sensor} · +1 · Prototyp" in _texte(ansicht)
    # Der Takt zieht nur Texte nach: dieselben Flächen, kein Neubau
    await _sekunden(state, uhr, gurt, 2)
    assert _flaechen(ansicht, MEHR) == [plus]
    assert neu_gebaut == []
    sensor = z.sensor

    _knopf(ansicht, "Fertig").on_click()
    await _bis_vorbei(state, uhr, gurt)
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] == [sensor + 1]
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.eingetragen == {ze.TEIL_ZAEHLEN}
    assert ze.zaehl_ende(state.einheiten.ereignisse(lauf.einheit_id)) == ENDE_FERTIG
    danach = _ansicht(seite, state, u)
    assert _knoepfe(danach, "Wdh. zählen") and not _flaechen(danach, MEHR)
    assert state.messlauf.acc_anforderungen == {}


async def test_zaehlen_abbrechen_bleibt_unter_laeufe_heute(umgebung) -> None:
    """„Zählen abbrechen“ trägt nichts ein; der Lauf steht mit seinen Sätzen unter dem Knopf
    (auch ohne Uhr an der Übung) und im Timer unter „Läufe heute“ — „Eintragen“ holt es nach."""
    from trainingsapp.ui.views.uebung_timer import uebung_timer_view

    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state, uhr=False)  # ohne Uhr: die Zählzeile zeigt die Läufe selbst
    ansicht = _ansicht(seite, state, u)
    assert "Stoppuhr" not in _texte(ansicht)
    _knopf(ansicht, "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 20)
    ansicht = _ansicht(seite, state, u)
    gezaehlt = _zaehl_teil(state).wert
    assert gezaehlt > 0
    _knopf(ansicht, "Zählen abbrechen").on_click()
    await _bis_vorbei(state, uhr, gurt)
    assert _eintraege(state) == []
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.zaehl_abgebrochen and lauf.nachtragbar
    assert ze.zaehl_ende(state.einheiten.ereignisse(lauf.einheit_id)) == ENDE_ABBRUCH

    danach = _ansicht(seite, state, u)
    texte = _texte(danach)
    assert any(t.startswith(f"Satz 1 · {gezaehlt} Wdh.") for t in texte)
    assert "abgebrochen · nicht eingetragen" in texte
    assert _knoepfe(danach, "Wdh. zählen")  # neu zählen geht
    timer = uebung_timer_view(seite, state, f"/training/{u.id}", u)
    texte = _texte(timer)
    assert "LÄUFE HEUTE" in texte and any(t.startswith("Satz 1 · ") for t in texte)

    (nachtragen,) = _nachtragen(danach)
    # Kein zweites „Eintragen“ mit anderer Bedeutung in derselben Karte (Runde 3, Befund 11)
    assert not [x for x in _knoepfe(danach, "Eintragen") if isinstance(x, ft.FilledTonalButton)]
    assert nachtragen.tooltip
    nachtragen.on_click()
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] == [gezaehlt]
    assert isinstance(seite.dialoge[-1], ft.SnackBar)
    # Danach ist nichts mehr nachzutragen — die Zeile verschwindet aus der Karte
    assert not _nachtragen(_ansicht(seite, state, u))
    assert uebung_lauf.lauf_eintragen(state, lauf.einheit_id) is None


async def test_abhaken_traegt_die_wiederholungen_ein_und_schliesst(umgebung) -> None:
    """„Gemacht“ während des Zählens (Leitentscheidung 7): Das Zählen endet als „abgehakt“,
    die Wiederholungen kommen in den offenen Eintrag, und der wird geschlossen — kein zweiter
    Stempel „gemacht“, nichts doppelt am Ende der Einheit."""
    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state)
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 20)
    gezaehlt = _zaehl_teil(state).wert
    assert gezaehlt > 0
    _knopf(_ansicht(seite, state, u), "Gemacht").on_click()
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] == [gezaehlt] and eintrag.ended_at is not None
    await _bis_vorbei(state, uhr, gurt)
    (eintrag,) = _eintraege(state)  # am Ende nichts doppelt
    assert eintrag.result["reps"] == [gezaehlt]
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert ze.zaehl_ende(state.einheiten.ereignisse(lauf.einheit_id)) == "abgehakt"
    assert not lauf.nachtragbar


async def test_abhaken_auf_heute_waehrend_des_zaehlens(umgebung) -> None:
    """Der Chip auf „Heute“ hakt ab wie „Gemacht“ im Plan — mit den gezählten Wiederholungen."""
    from trainingsapp.ui.views.tag import tagesansicht

    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state)
    andere = _kniebeuge(state, "Ausfallschritt")
    plan = Plan(
        name="Beine",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=u.id), PlanItem(exercise_id=andere.id)],
    )
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    # Der Plan ist angefangen — erst dann stehen die offenen Übungen als Chips da
    sitzung = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    state.sitzungen.eintrag_anlegen(sitzung, andere, {"reps": [10]})
    _knopf(plan_view(seite, state, plan), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 15)
    gezaehlt = _zaehl_teil(state).wert
    ansicht = tagesansicht(seite, state, state.heute())
    chip = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container)
        and x.on_long_press
        and x.border is not None
        and "Kniebeuge" in _texte(x)
    )
    chip.on_click()
    (eintrag,) = [x for x in _eintraege(state) if x.exercise_id == u.id]
    assert eintrag.result["reps"] == [gezaehlt] and eintrag.ended_at is not None
    meldung = seite.dialoge[-1]
    assert isinstance(meldung, ft.SnackBar) and meldung.action is None  # ohne Rückgängig
    assert meldung.content.value == f"Kniebeuge: {eintrag.shorthand()}"
    await _bis_vorbei(state, uhr, gurt)
    assert len([x for x in _eintraege(state) if x.exercise_id == u.id]) == 1


async def test_andere_uebung_beendet_das_zaehlen_mit_meldung(umgebung) -> None:
    """Zählen von Y, dann Zählen (oder die Uhr) von X: Ys Zählen endet mit „andere_uebung“,
    5 s die Meldung „Kniebeuge · n Wdh. nicht eingetragen“ mit „Eintragen“."""
    from trainingsapp.ui.components.dialoge import MELDUNG_MS

    state, uhr, gurt = umgebung
    seite = Seite()
    kniebeuge = _kniebeuge(state)
    liegestuetz = _kniebeuge(state, "Liegestütz")
    _knopf(_ansicht(seite, state, kniebeuge), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 15)
    gezaehlt = _zaehl_teil(state).wert
    erste = state.einheit
    _knopf(_ansicht(seite, state, liegestuetz), "Wdh. zählen").on_click()
    meldung = seite.dialoge[-1]
    assert isinstance(meldung, ft.SnackBar)
    assert meldung.content.value == f"Kniebeuge · {gezaehlt} Wdh. nicht eingetragen"
    assert meldung.action.label == "Eintragen" and meldung.duration == MELDUNG_MS
    assert not meldung.persist
    assert ze.zaehl_ende(erste.ereignisse) == "andere_uebung"
    assert _zaehl_teil(state).kontext.uebung_id == liegestuetz.id
    meldung.action.on_click()
    await ruhe()
    (eintrag,) = _eintraege(state)
    assert eintrag.exercise_id == kniebeuge.id and eintrag.result["reps"] == [gezaehlt]

    # Die Uhr der Kniebeuge beendet das Zählen des Liegestützes ebenso
    await _sekunden(state, uhr, gurt, 15)
    gezaehlt = _zaehl_teil(state).wert
    _symbol(_ansicht(seite, state, kniebeuge), ft.Icons.PLAY_ARROW, "starten").on_click()
    meldung = seite.dialoge[-1]
    assert isinstance(meldung, ft.SnackBar)
    assert meldung.content.value == f"Liegestütz · {gezaehlt} Wdh. nicht eingetragen"
    assert state.einheit.timer is not None and state.einheit.teil("zaehlen") is None

    # Nie über einem offenen Dialog: dann bleibt sie liegen
    from trainingsapp.ui.components import zaehlen

    offen = SimpleNamespace(_dialogs=SimpleNamespace(controls=[SimpleNamespace(open=True)]))
    offen.show_dialog = seite.dialoge.append
    vorher = len(seite.dialoge)
    gemerkt = uebung_lauf.ZaehlMeldung("x", kniebeuge.id, "Kniebeuge", 3)
    assert not zaehlen.meldung_zeigen(offen, state, gemerkt)
    assert len(seite.dialoge) == vorher and state.zaehl_meldung is gemerkt
    assert zaehlen.meldung_zeigen(seite, state) and state.zaehl_meldung is None


async def test_uhr_und_zaehlen_zusammen(umgebung) -> None:
    """Läuft die Uhr und zählt der Sensor dieselbe Übung, steht die Zahl mit ±1 in der
    laufenden Uhr — einmal, nicht noch in der Zählzeile; der Timer („Während“) zeigt sie
    auch, die Karte „Sätze“ je Satz die Wiederholungen. „Fertig“ der Uhr trägt beides ein."""
    from trainingsapp.core.timer import Abschnitt, TimerProfil
    from trainingsapp.ui.views.uebung_timer import uebung_timer_view

    state, uhr, gurt = umgebung
    seite = Seite()
    profil = TimerProfil(
        name="2 × 20 s",
        abschnitte=[Abschnitt("Satz", 20), Abschnitt("Pause", 10, zaehlt=False)],
        runden=2,
    )
    u = _kniebeuge(state, "Kniebeuge", "reps", "hold", timer=[profil.als_dict()])
    _symbol(_ansicht(seite, state, u), ft.Icons.PLAY_ARROW, "starten").on_click()
    e = state.einheit
    assert e is not None and e.timer is not None
    await _sekunden(state, uhr, gurt, 1)
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    assert state.einheit is e and isinstance(e.teil("zaehlen"), ZaehlBaustein)
    ansicht = _ansicht(seite, state, u)
    assert len(_flaechen(ansicht, MEHR)) == 1 and len(_knoepfe(ansicht, "Fertig")) == 1
    assert _knoepfe(ansicht, "Zählen abbrechen") and not _knoepfe(ansicht, "Wdh. zählen")
    await _sekunden(state, uhr, gurt, 15)
    _flaechen(ansicht, MEHR)[0].on_click()
    z = _zaehl_teil(state)
    assert z.korrektur == 1
    assert f"Sensor {z.sensor} · +1 · Prototyp" in _texte(ansicht)

    timer = uebung_timer_view(seite, state, f"/training/{u.id}", u)
    assert len(_flaechen(timer, MEHR)) == 1
    assert any(t.endswith(f" · {z.wert} Wdh.") for t in _texte(timer))  # Satz 1 · läuft
    await _sekunden(state, uhr, gurt, 10)  # Satz 1 vorbei, Pause
    timer = uebung_timer_view(seite, state, f"/training/{u.id}", u)
    satz1 = z.saetze[0].wert
    assert any(t.endswith(f" · {satz1} Wdh.") for t in _texte(timer))

    _knopf(ansicht, "Fertig").on_click()  # „Fertig“ der Uhr: beides
    await _bis_vorbei(state, uhr, gurt)
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] and eintrag.result["reps"][0] == satz1
    assert eintrag.result.get("hold")
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.eingetragen == {ze.TEIL_UHR, ze.TEIL_ZAEHLEN}


async def test_info_und_laufleiste_zeigen_das_zaehlen(umgebung) -> None:
    from trainingsapp.ui.components import startleiste as sl

    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state)
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 15)
    z = _zaehl_teil(state)
    assert sl.SYMBOLE["zaehlen"] == ft.Icons.SENSORS and sl.KURZ["zaehlen"] == "Zählen"
    assert sl._teil_titel(z) == "Zählen · Kniebeuge"
    assert z.status() == f"Kniebeuge · {z.wert}"
    assert einheit_ui.teil_route(z) == f"/training/{u.id}"
    leiste = sl.startleiste(seite, state)
    assert leiste is not None
    assert any("Zählen · Kniebeuge" in t for t in _texte(leiste))
    uebung_lauf.zaehlen_beenden(state, u.id)
    await _bis_vorbei(state, uhr, gurt)


async def test_marken_leiste_zeigt_den_sensor(umgebung, monkeypatch) -> None:
    """Diagnosemodus (A2): neben der Zahl der Tipps live „Sensor 11“ — nur der Text wird
    nachgezogen; ohne Zählen steht dort nichts."""
    from trainingsapp.ui.components import marken_leiste as ml
    from trainingsapp.ui.components import marken_stand

    state, uhr, gurt = umgebung
    seite = Seite()
    seite.overlay = []
    # Der Diagnosemodus „läuft“ — die Leiste nimmt den Messlauf
    monkeypatch.setattr(marken_stand, "diagnose_lauf", lambda s: s.messlauf)
    monkeypatch.setattr(ml, "diagnose_lauf", lambda s: s.messlauf)
    ml.aktualisieren(seite, state)
    stand = state.diagnose_leiste
    assert stand.sensor is not None and not stand.sensor.visible
    u = _kniebeuge(state)
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    ml.aktualisieren(seite, state)  # wie nach jedem Neuaufbau
    stand = state.diagnose_leiste
    sensor = stand.sensor
    await _sekunden(state, uhr, gurt, 15)
    z = _zaehl_teil(state)
    assert sensor.visible and sensor.value == f"Sensor {z.sensor}"
    uebung_lauf.zaehlen_beenden(state, u.id)
    einheit_ui.melden(state)
    assert not sensor.visible and sensor.value == ""
    await _bis_vorbei(state, uhr, gurt)
    zaehl_stand.anzeigen(state).clear()


async def test_ohne_mengen_und_zugeklappt(umgebung) -> None:
    """Eine Übung nur mit „Atmung“ und ohne Mengen bekommt die Zeile allein unter der
    Ausführung; in der Darstellung „Aufklappen“ steht das laufende Zählen auch im
    zugeklappten Block — der Knopf dort nicht."""
    from trainingsapp.ui.state import AUFKLAPPEN

    state, uhr, gurt = umgebung
    seite = Seite()
    atem = Exercise(name="Box Breathing", typen=["Atmung"], uhr=False)
    state.uebungen.speichern(atem)
    ansicht = _ansicht(seite, state, atem)
    _knopf(ansicht, "Atmung erfassen").on_click()
    z = _zaehl_teil(state)
    assert not z.wdh and z.atem
    ansicht = _ansicht(seite, state, atem)
    assert "Sensor startet …" in _texte(ansicht) and not _flaechen(ansicht, MEHR)
    assert len(_flaechen(ansicht, ATEM_MEHR)) == 1  # ±1 gilt den Atemzügen (A3)
    _knopf(ansicht, "Zählen abbrechen").on_click()
    await _bis_vorbei(state, uhr, gurt)
    assert _eintraege(state) == []  # nur Atmung: nichts einzutragen

    state.plan_darstellung_setzen(AUFKLAPPEN)
    kniebeuge = _kniebeuge(state)
    ausfall = _kniebeuge(state, "Ausfallschritt")
    plan = Plan(
        name="Beine",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=kniebeuge.id), PlanItem(exercise_id=ausfall.id)],
    )
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    state.plan_offen = plan.items[0].id
    ansicht = plan_view(seite, state, plan)
    (knopf,) = _knoepfe(ansicht, "Wdh. zählen")  # nur im offenen Block
    knopf.on_click()
    state.plan_offen = plan.items[1].id  # die andere aufklappen
    ansicht = plan_view(seite, state, plan)
    assert len(_flaechen(ansicht, MEHR)) == 1  # das Zählen steht zugeklappt weiter da
    assert len(_knoepfe(ansicht, "Wdh. zählen")) == 1  # der Knopf nur im offenen Block
    uebung_lauf.zaehlen_beenden(state, kniebeuge.id, plan.items[0].id)
    await _bis_vorbei(state, uhr, gurt)


async def test_atmung_erfassen_zeigt_atemzuege_rate_und_phase(umgebung) -> None:
    """A3: „Atmung erfassen“ zeigt groß die Atemzüge, darunter „Atmung 4 · 6/min ▲ ·
    Prototyp“; ±1 korrigiert die Atemzüge, nur die Texte ziehen nach. Hört die Atmung auf,
    endet der Lauf nach 2 min als ``kein_atem`` mit der Meldung „— 2 min kein Atemzug erkannt“
    (ohne „Eintragen“: ins Tagebuch kommt nichts, P120). Mit Wiederholungen dazu bleibt die
    Zahl die der Wiederholungen, die Atem-Spur steht als dritte Zeile."""
    state, uhr, gurt = umgebung
    gurt.bewegung = False
    seite = Seite()
    atem = Exercise(name="Box Breathing", typen=["Atmung"], uhr=False)
    state.uebungen.speichern(atem)
    _knopf(_ansicht(seite, state, atem), "Atmung erfassen").on_click()
    await _sekunden(state, uhr, gurt, 45)
    z = _zaehl_teil(state)
    assert not z.wdh and z.atem and z.atemzuege >= 3 and z.atem_rate is not None
    ansicht = _ansicht(seite, state, atem)
    texte = _texte(ansicht)
    assert str(z.atemzuege) in texte and zaehl_stand.klein_text(z) in texte
    assert "6/min" in zaehl_stand.klein_text(z) and zaehl_stand.atem_phase(z) in ("▲", "▼")
    assert _knopf(ansicht, "Fertig").tooltip == "Atmung beenden — ins Tagebuch kommt nichts"
    (mehr,) = _flaechen(ansicht, ATEM_MEHR)
    vorher = z.atemzuege
    mehr.on_click()
    assert z.atem_korrektur == 1 and z.atemzuege == vorher + 1
    assert str(vorher + 1) in _texte(ansicht)  # nachgezogen, nicht neu gebaut
    assert "· +1 ·" in zaehl_stand.klein_text(z)
    gurt.atem_mg = 0.0  # der Gurt liegt still
    await _sekunden(state, uhr, gurt, 135)
    assert z.grund == "kein_atem"
    await _bis_vorbei(state, uhr, gurt)  # ein Zähllauf endet mit dem Zählen
    meldung = uebung_lauf.meldung_abholen(state)
    assert meldung is not None and meldung.atmung
    assert meldung.text == "Box Breathing · Atmung beendet — 2 min kein Atemzug erkannt"
    (lauf,) = uebung_lauf.laeufe_heute(state, atem.id)  # steht da, aber nichts nachzutragen
    assert _eintraege(state) == [] and lauf.zaehlart == "atem" and not lauf.nachzutragen
    gurt.atem_mg, gurt.bewegung = 25.0, True

    # Wdh + Atmung: die Zahl sind die Wiederholungen, die Atem-Spur eine Zeile darunter
    u = _kniebeuge(state, "Kniebeuge", "reps", beschleunigung=SensorWahl(atmung=True))
    _knopf(_ansicht(seite, state, u), "Wdh. zählen · Atmung").on_click()
    await _sekunden(state, uhr, gurt, 12)
    gurt.bewegung = False
    await _sekunden(state, uhr, gurt, 25)
    z = _zaehl_teil(state)
    assert z.wdh and z.atem and z.wert >= 3 and z.atem_sensor is not None
    ansicht = _ansicht(seite, state, u)
    texte = _texte(ansicht)
    assert str(z.wert) in texte and zaehl_stand.atem_text(z) in texte
    assert zaehl_stand.atem_text(z).startswith("Atmung ")
    assert len(_flaechen(ansicht, MEHR)) == 1 and not _flaechen(ansicht, ATEM_MEHR)
    uebung_lauf.zaehlen_beenden(state, u.id)
    await _bis_vorbei(state, uhr, gurt)
    for _ in range(100):  # das Eintragen kommt mit dem Abschluss der Einheit (`_laufen`)
        if _eintraege(state):
            break
        await asyncio.sleep(0.01)
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] == [z.wert]  # die Atmung nicht


async def test_keine_bewegung_neben_der_uhr_zeichnet_neu(umgebung) -> None:
    """Endet das Zählen von selbst (60 s ohne neue Wiederholung), während die Uhr weiterläuft,
    zeichnet die Oberfläche einmal neu: die Uhr zeigt dann die letzte Zahl ohne „Zählen
    abbrechen“, und ein zweites Zählen gibt es in diesem Lauf nicht."""
    state, uhr, gurt = umgebung
    gezeichnet: list[int] = []
    state.neu_zeichnen = lambda: gezeichnet.append(1)
    seite = Seite()
    u = _kniebeuge(state)
    _symbol(_ansicht(seite, state, u), ft.Icons.PLAY_ARROW, "starten").on_click()
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 12)
    gurt.bewegung = False
    vorher = len(gezeichnet)
    await _sekunden(state, uhr, gurt, 65)
    z = _zaehl_teil(state)
    assert z.grund == "keine_bewegung" and state.einheit.laeuft  # die Uhr läuft weiter
    assert len(gezeichnet) > vorher
    ansicht = _ansicht(seite, state, u)
    assert "Zählen abgebrochen (keine Bewegung)" in _texte(ansicht)
    assert not _knoepfe(ansicht, "Zählen abbrechen") and not _knoepfe(ansicht, "Wdh. zählen")
    assert not _flaechen(ansicht, MEHR) and not _flaechen(ansicht, WENIGER)  # ±1 ginge ins Leere
    _knopf(ansicht, "Fertig").on_click()  # die Uhr
    await _bis_vorbei(state, uhr, gurt)
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.eingetragen == {ze.TEIL_UHR} and ze.TEIL_ZAEHLEN in lauf.nachzutragen


# -- Befunde der Prüfung (4.11.2026) -----------------------------------------------------------


async def test_zaehlen_abbrechen_neben_der_uhr_nimmt_die_flaechen_weg(umgebung) -> None:
    """Endet das Zählen, während die Uhr weiterläuft („Zählen abbrechen“), bleiben in Uhr und
    Timer die Zahl und warum — ohne −1/+1: ein Tipp darauf ginge ins Leere
    (`zaehl_stand.korrigieren` korrigiert nur, solange gezählt wird)."""
    from trainingsapp.core.timer import Abschnitt, TimerProfil
    from trainingsapp.ui.views.uebung_timer import uebung_timer_view

    state, uhr, gurt = umgebung
    seite = Seite()
    profil = TimerProfil(name="Satz 60 s", abschnitte=[Abschnitt("Satz", 60)], runden=1)
    u = _kniebeuge(state, "Kniebeuge", "reps", "hold", timer=[profil.als_dict()])
    _symbol(_ansicht(seite, state, u), ft.Icons.PLAY_ARROW, "starten").on_click()
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 12)
    ansicht = _ansicht(seite, state, u)
    assert len(_flaechen(ansicht, MEHR)) == 1
    _knopf(ansicht, "Zählen abbrechen").on_click()
    z = _zaehl_teil(state)
    assert z.grund == ENDE_ABBRUCH and state.einheit.laeuft  # die Uhr läuft weiter
    ansicht = _ansicht(seite, state, u)
    timer = uebung_timer_view(seite, state, f"/training/{u.id}", u)
    for sicht in (ansicht, timer):
        assert not _flaechen(sicht, MEHR) and not _flaechen(sicht, WENIGER)  # vorher: 1
        assert "Zählen abgebrochen" in _texte(sicht) and str(z.wert) in _texte(sicht)
    _knopf(ansicht, "Fertig").on_click()  # die Uhr
    await _bis_vorbei(state, uhr, gurt)


async def test_offene_zaehllaeufe_auch_ohne_geraet(umgebung) -> None:
    """Ohne verbundenes Gerät gibt es keinen Knopf — die abgebrochenen Zählläufe von heute
    lassen sich aber weiter eintragen: an einer Übung ohne Uhr gibt es keinen anderen Ort."""
    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state, uhr=False)
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 20)
    gezaehlt = _zaehl_teil(state).wert
    assert gezaehlt > 0
    _knopf(_ansicht(seite, state, u), "Zählen abbrechen").on_click()
    await _bis_vorbei(state, uhr, gurt)
    await state.messlauf.trennen()  # der Gurt ist ab
    ansicht = _ansicht(seite, state, u)
    assert not _knoepfe(ansicht, "Wdh. zählen")  # kein Knopf ohne Sensor (P118)
    (nachtragen,) = _nachtragen(ansicht)  # vorher: keiner
    assert any(t.startswith(f"Satz 1 · {gezaehlt} Wdh.") for t in _texte(ansicht))
    nachtragen.on_click()
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] == [gezaehlt]
    assert not _nachtragen(_ansicht(seite, state, u))
    state.messlauf = None  # ganz ohne Messlauf ebenso: nichts mehr offen, nichts zu sehen
    assert not _nachtragen(_ansicht(seite, state, u))


async def test_knopf_folgt_der_planuebung(umgebung) -> None:
    """Ob es „Wdh. zählen“ gibt, entscheidet die Planübung (P79): Liegestütz nur mit
    Haltezeit im Plan bekommt keinen Knopf, die Planke mit Wiederholungen nur im Plan einen."""
    state, uhr, gurt = umgebung
    seite = Seite()
    liegestuetz = _kniebeuge(state, "Liegestütz", "reps", "hold", uhr=False)
    planke = _kniebeuge(state, "Planke", "hold", uhr=False)
    plan = Plan(
        name="P",
        subject_id=state.profil.id,
        items=[
            PlanItem(exercise_id=liegestuetz.id, felder=["hold"]),
            PlanItem(exercise_id=planke.id, felder=["hold", "reps"]),
        ],
    )
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    (knopf,) = _knoepfe(plan_view(seite, state, plan), "Wdh. zählen")  # vorher: Liegestütz
    knopf.on_click()
    z = _zaehl_teil(state)
    assert z.kontext.uebung_id == planke.id and z.feld == "reps"
    await _sekunden(state, uhr, gurt, 20)
    gezaehlt = z.wert
    _knopf(plan_view(seite, state, plan), "Fertig").on_click()
    await _bis_vorbei(state, uhr, gurt)
    (eintrag,) = _eintraege(state)
    assert eintrag.exercise_id == planke.id and eintrag.result["reps"] == [gezaehlt]


# -- Lücken der ersten Runde (4.11.2026) -------------------------------------------------------


async def test_chip_mit_wert_beendet_das_zaehlen_und_schliesst_einen_eintrag(umgebung) -> None:
    """Ein Chip, der mit einem Wert abhakt (Zeit „5:00“), während der Sensor zählt: Das Zählen
    endet als „abgehakt“ wie bei „Gemacht“; Wiederholungen und Wert stehen in **einem**
    Eintrag, der geschlossen ist — kein zweiter Stempel, nichts doppelt am Ende der Einheit."""
    from trainingsapp.ui.views.plan import chip_text

    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state, "Kniebeuge", "reps", "duration")
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 20)
    z = _zaehl_teil(state)
    gezaehlt = z.wert
    assert gezaehlt > 0
    _knopf(_ansicht(seite, state, u), chip_text(vorrat_feld("duration"), 300)).on_click()
    assert z.grund == "abgehakt" and not z.aktiv  # vorher: es zählte weiter
    (eintrag,) = _eintraege(state)
    assert eintrag.result == {"reps": [gezaehlt], "duration": 300}
    assert eintrag.ended_at is not None
    await _bis_vorbei(state, uhr, gurt)
    (eintrag,) = _eintraege(state)  # am Ende nichts doppelt
    assert eintrag.result == {"reps": [gezaehlt], "duration": 300}
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.eingetragen == {ze.TEIL_ZAEHLEN} and not lauf.nachtragbar
    assert state.messlauf.acc_anforderungen == {}


async def test_laufleiste_fuehrt_im_plan_zur_uebung(umgebung) -> None:
    """Ein Tipp auf das Zählen im Reiter „Einheit“ führt in den Plan — und die Liste beginnt
    bei der Übung, aufgeklappt (`AppState.plan_ziel`, wie „Weiter mit …“ auf „Heute“)."""
    from trainingsapp.ui.components import startleiste as sl

    state, uhr, gurt = umgebung
    seite = Seite()
    andere = _kniebeuge(state, "Ausfallschritt")
    u = _kniebeuge(state)
    plan = Plan(
        name="Beine",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=andere.id), PlanItem(exercise_id=u.id)],
    )
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    item = plan.items[1]
    kontext = uebung_lauf.kontext_fuer(u, plan, item)
    uebung_lauf.zaehlen_starten(seite, state, kontext, uebung=u, item=item)
    z = _zaehl_teil(state)
    oeffnen = sl._oeffner(seite, state, z)
    assert oeffnen is not None
    state.plan_ziel = state.plan_offen = None
    await oeffnen()
    assert seite.route == f"/plan/{plan.id}"
    assert state.plan_ziel == item.id and state.plan_offen == item.id  # vorher: None
    plan_view(seite, state, plan)  # beginnt bei der Übung — einmal
    assert state.plan_ziel is None
    uebung_lauf.zaehlen_beenden(state, u.id, item.id, ENDE_ABBRUCH)
    await _bis_vorbei(state, uhr, gurt)


async def test_reiter_einheit_zeigt_den_zaehllauf_ohne_zeile_der_uhr(umgebung) -> None:
    """Ein Zähllauf ohne Uhr steht im Reiter „Einheit“ als „Zählen · Kniebeuge“ — nicht mehr
    daneben „Übung · Kniebeuge — trägt die Zeit ein“, die in den Timer der Übung führte, wo
    weder Zahl noch ±1 stehen (Runde 3, Befund 7). Läuft die Uhr mit, bleibt ihre Zeile."""
    from trainingsapp.ui.components import startleiste as sl

    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state)
    uebung_lauf.zaehlen_starten(seite, state, uebung_lauf.kontext_fuer(u))
    await _sekunden(state, uhr, gurt, 20)
    texte = _texte(sl.einheit_reiter(seite, state))
    assert "Zählen · Kniebeuge" in texte
    assert "Übung · Kniebeuge" not in texte and "trägt die Zeit ein" not in texte  # vorher: da
    uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABBRUCH)
    await _bis_vorbei(state, uhr, gurt)


async def test_abhaken_auf_heute_nach_dem_start_auf_der_uebungsseite(umgebung) -> None:
    """Zählen auf der Übungsseite gestartet (ohne Plan), auf „Heute“ am Chip eines Plans
    abgehakt: Der Kontext des Abhakens gewinnt — der Eintrag steht im Plan, nicht unter „Ohne
    Plan“, und nur einmal."""
    from trainingsapp.ui.views.tag import tagesansicht

    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state)
    andere = _kniebeuge(state, "Ausfallschritt")
    plan = Plan(
        name="Beine",
        subject_id=state.profil.id,
        items=[PlanItem(exercise_id=u.id), PlanItem(exercise_id=andere.id)],
    )
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    sitzung = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    state.sitzungen.eintrag_anlegen(sitzung, andere, {"reps": [10]})
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()  # die Übungsseite, ohne Plan
    assert _zaehl_teil(state).kontext.plan_id is None
    await _sekunden(state, uhr, gurt, 15)
    gezaehlt = _zaehl_teil(state).wert
    ansicht = tagesansicht(seite, state, state.heute())
    chip = next(
        x
        for x in _alle(ansicht)
        if isinstance(x, ft.Container)
        and x.on_long_press
        and x.border is not None
        and "Kniebeuge" in _texte(x)
    )
    chip.on_click()
    await _bis_vorbei(state, uhr, gurt)
    eintraege = [
        (x, s.plan_id)
        for x, s in state.sitzungen.eintraege_am_tag(state.profil.id, state.heute())
        if x.exercise_id == u.id
    ]
    ((eintrag, plan_id),) = eintraege  # einmal
    assert plan_id == plan.id  # vorher: None — die Sitzung ohne Plan
    assert eintrag.result["reps"] == [gezaehlt] and eintrag.ended_at is not None


async def test_von_selbst_beendet_zeigt_die_meldung_einmal(umgebung) -> None:
    """60 s ohne Bewegung: Das Zählen endet abgebrochen, und nach dem Neuaufbau kommt 5 s die
    Meldung „Kniebeuge · n Wdh. nicht eingetragen — 60 s ohne Bewegung“ mit „Eintragen“ — wie
    bei einer anderen Übung, einmal, nie über einem offenen Dialog."""
    from trainingsapp.ui.components import zaehlen
    from trainingsapp.ui.components.dialoge import MELDUNG_MS

    state, uhr, gurt = umgebung
    seite = Seite()
    # Wie `ui.app.zeige_route`: nach jedem Aufbau eine liegengebliebene Meldung zeigen
    state.neu_zeichnen = lambda: zaehlen.meldung_zeigen(seite, state)
    u = _kniebeuge(state, uhr=False)
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 15)
    assert _zaehl_teil(state).wert > 0
    gurt.bewegung = False
    await _bis_vorbei(state, uhr, gurt)
    (lauf,) = uebung_lauf.laeufe_heute(state, u.id)
    assert lauf.zaehl_abgebrochen and lauf.nachtragbar
    text = f"Kniebeuge · {sum(lauf.wdh)} Wdh. nicht eingetragen — 60 s ohne Bewegung"

    def gezeigt() -> list:
        return [d for d in seite.dialoge if isinstance(d, ft.SnackBar) and d.content.value == text]

    (meldung,) = gezeigt()  # vorher: keine
    assert meldung.action.label == "Eintragen" and meldung.duration == MELDUNG_MS
    assert not meldung.persist
    state.neu_zeichnen()  # noch ein Aufbau: nicht doppelt
    assert len(gezeigt()) == 1
    meldung.action.on_click()
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] == lauf.wdh

    # Bei offenem Dialog bleibt sie liegen, bis die Ansicht das nächste Mal aufgebaut wird
    offen = SimpleNamespace(_dialogs=SimpleNamespace(controls=[SimpleNamespace(open=True)]))
    offen.show_dialog = seite.dialoge.append
    state.neu_zeichnen = lambda: zaehlen.meldung_zeigen(offen, state)
    gurt.bewegung = True
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 15)
    gurt.bewegung = False
    vorher = len(seite.dialoge)
    await _bis_vorbei(state, uhr, gurt)
    assert len(seite.dialoge) == vorher and state.zaehl_meldung is not None
    assert zaehlen.meldung_zeigen(seite, state) and state.zaehl_meldung is None
    assert seite.dialoge[-1].content.value.endswith("— 60 s ohne Bewegung")


# -- Befunde der dritten Runde (5.11.2026) -----------------------------------------------------


async def test_waehrend_der_sensor_zaehlt_keine_menge_von_hand(umgebung, monkeypatch) -> None:
    """P122 (Plan §4.4): Mit dem Knopf zählt der Sensor, die Person korrigiert höchstens mit
    ±1. Solange er in „Wdh.“ zählt, hat die Zeile weder „+10“ noch den eigenen Wert, und ein
    Knopf aus der Ansicht von vorher hängt keinen zweiten Satz an — vorher stand nach „+10“
    und „Fertig“ ``[10.0, 9]`` für einen Satz im Eintrag. Nach dem Zählen ist alles wieder
    da, und im Diagnosemodus zählen beide (Prüfung, Abschnitt 6)."""
    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state)
    vorher = _ansicht(seite, state, u)
    plus_zehn = _knopf(vorher, "+10")
    _knopf(vorher, "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 20)
    ansicht = _ansicht(seite, state, u)
    assert not _knoepfe(ansicht, "+10")  # vorher: ein Knopf „+10“ neben der Zahl
    assert "Der Sensor zählt — korrigieren mit −1/+1" in _texte(ansicht)
    assert _flaechen(ansicht, MEHR)  # ±1 bleibt
    plus_zehn.on_click()  # ein Knopf von vor dem Tipp
    assert _eintraege(state) == []
    z = _zaehl_teil(state)
    assert z.aktiv
    _knopf(ansicht, "Fertig").on_click()
    await _bis_vorbei(state, uhr, gurt)
    (eintrag,) = _eintraege(state)
    assert eintrag.result == {"reps": [z.wert]}  # vorher: [10.0, z.wert]
    assert _knoepfe(_ansicht(seite, state, u), "+10")  # nach dem Zählen wieder da

    # Im Diagnosemodus zählen Person und Sensor zugleich (Prüfung)
    monkeypatch.setattr(Messlauf, "diagnose_aktiv", property(lambda self: True))
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 5)
    assert _knoepfe(_ansicht(seite, state, u), "+10")
    uebung_lauf.zaehlen_beenden(state, u.id, None, ENDE_ABBRUCH)
    await _bis_vorbei(state, uhr, gurt)


async def test_im_diagnosemodus_steht_ein_satz_von_hand_nicht_doppelt_da(
    umgebung, monkeypatch
) -> None:
    """Im Diagnosemodus zählen Person und Sensor zugleich (P122, §6): Ein Chip „+10“ ist der
    Satz, den der Sensor gerade zählt — er endet dort, und „Fertig“ trägt ihn nicht noch einmal
    ein. Vorher stand ``[10.0, 10.0, 18]`` für zwei Sätze im Tagebuch (Runde 3, Befund 5)."""
    state, uhr, gurt = umgebung
    monkeypatch.setattr(Messlauf, "diagnose_aktiv", property(lambda self: True))
    seite = Seite()
    u = _kniebeuge(state)
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 25)
    z = _zaehl_teil(state)
    _knopf(_ansicht(seite, state, u), "+10").on_click()
    assert z.aktiv and len(z.saetze) == 2 and z.saetze[0].von_hand  # der Sensor zählt weiter
    assert z.wert == 0  # der nächste Satz beginnt
    await _sekunden(state, uhr, gurt, 20)
    _knopf(_ansicht(seite, state, u), "+10").on_click()
    assert [s.von_hand for s in z.saetze] == [True, True, False]
    _knopf(_ansicht(seite, state, u), "Fertig").on_click()
    await _bis_vorbei(state, uhr, gurt)
    (eintrag,) = _eintraege(state)
    assert eintrag.result == {"reps": [10.0, 10.0]}  # vorher: [10.0, 10.0, 18]


async def test_im_diagnosemodus_folgt_ein_chip_neben_der_uhr_ihren_saetzen(
    umgebung, monkeypatch
) -> None:
    """Diagnosemodus, Wandsitz mit Uhr 3 × (20 s / 10 s) und „Wdh. zählen“: Satz 1 zählt nur
    der Sensor, mitten in Halten 2 tippt die Person „+10“, Satz 3 wieder nur der Sensor. Vorher
    stand der Chip vor Satz 1 im Tagebuch, und der Rest von Halten 2 kam als eigener Satz hinein
    (vier Wiederholungswerte für drei Haltezeiten). Jetzt kommt Satz 1 vor dem Chip, der Chip
    beendet Halten 2, und Halten 3 ist Satz 3 (Runde 5)."""
    from trainingsapp.core.timer import Abschnitt, TimerProfil

    state, uhr, gurt = umgebung
    monkeypatch.setattr(Messlauf, "diagnose_aktiv", property(lambda self: True))
    seite = Seite()
    profil = TimerProfil(
        name="3 × 20 s",
        abschnitte=[Abschnitt("Halten", 20), Abschnitt("Pause", 10, zaehlt=False)],
        runden=3,
    )
    u = _kniebeuge(state, "Wandsitz", "reps", "hold", timer=[profil.als_dict()])
    _symbol(_ansicht(seite, state, u), ft.Icons.PLAY_ARROW, "starten").on_click()
    await _sekunden(state, uhr, gurt, 1)
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 41)  # Satz 1, die Pause, 12 s von Halten 2
    z = _zaehl_teil(state)
    assert len(z.saetze) == 2 and z.saetze[0].wert > 0
    _knopf(_ansicht(seite, state, u), "+10").on_click()
    assert z.aktiv and [s.von_hand for s in z.saetze] == [True, True]  # kein Satz mitten darin
    await _bis_vorbei(state, uhr, gurt)
    assert [s.von_hand for s in z.saetze] == [True, True, False]
    s1, _s2, s3 = z.saetze
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] == [s1.wert, 10.0, s3.wert]  # vorher: [10.0, s1, Rest, s3]
    assert len(eintrag.result["hold"]) == 3


async def test_im_diagnosemodus_sind_saetze_mal_wert_zwei_saetze(umgebung, monkeypatch) -> None:
    """„Sätze × Wert“ 2 × 6 während des Zählens im Diagnosemodus: zwei Sätze von Hand — der
    erste ist der des Sensors, der zweite kein gezählter. Vorher endete nur einer, und die
    Nummern im Mitschnitt liefen den Sätzen davon (Runde 5)."""
    state, uhr, gurt = umgebung
    monkeypatch.setattr(Messlauf, "diagnose_aktiv", property(lambda self: True))
    seite = Seite()
    u = _kniebeuge(state)
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 12)
    z = _zaehl_teil(state)
    ansicht = _ansicht(seite, state, u)
    felder = [f for f in _alle(ansicht) if isinstance(f, ft.TextField)]
    i = next(i for i, f in enumerate(felder) if f.label == "Sätze")
    felder[i].value, felder[i + 1].value = "2", "6"  # Sätze × Wert
    (eintragen,) = [k for k in _knoepfe(ansicht, "Eintragen") if isinstance(k, ft.OutlinedButton)]
    eintragen.on_click()
    assert [s.von_hand for s in z.saetze] == [True, True, False]  # vorher: [True, False]
    await _sekunden(state, uhr, gurt, 10)
    _knopf(_ansicht(seite, state, u), "Fertig").on_click()
    await _bis_vorbei(state, uhr, gurt)
    (eintrag,) = _eintraege(state)
    assert eintrag.result["reps"] == [6.0, 6.0, z.saetze[-1].wert]


async def test_wie_geplant_fehlt_solange_der_sensor_zaehlt(umgebung) -> None:
    """„Wie geplant · 3x15“ hakte während des Zählens mit der Zahl des Sensors ab, nicht mit dem
    Ziel — Text und Wirkung passten nicht (Runde 3, Befund 8). Solange der Sensor zählt, steht
    der Knopf nicht da; danach wieder."""
    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state, default_target={"reps": [15, 15, 15]})
    assert _knoepfe(_ansicht(seite, state, u), "Wie geplant · 3x15")
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 20)
    ansicht = _ansicht(seite, state, u)
    assert not _knoepfe(ansicht, "Wie geplant · 3x15")  # vorher: da, trug [7] ein
    assert _knoepfe(ansicht, "Gemacht")
    _knopf(ansicht, "Fertig").on_click()
    await _bis_vorbei(state, uhr, gurt)
    assert _knoepfe(_ansicht(seite, state, u), "Wie geplant · 3x15")


async def test_bereitgestellt_gibt_es_keinen_knopf_der_nie_zaehlt(umgebung) -> None:
    """Steht eine Einheit bereit (etwa die Uhr der Übung), zählt der Sensor nicht — der Knopf
    „Wdh. zählen“ meldete nur „Es steht eine Einheit bereit“ (Runde 3, Befund 9). Er fehlt,
    bis oben gestartet oder geleert wird."""
    from trainingsapp.core.timer import Abschnitt, TimerProfil

    state, _uhr, _gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state, "Wandsitz", "hold", "reps")
    assert _knoepfe(_ansicht(seite, state, u), "Wdh. zählen")
    profil = TimerProfil(name="Halten 40 s", abschnitte=[Abschnitt("Halten", 40)])
    uebung_lauf.bereitstellen(seite, state, uebung_lauf.kontext_fuer(u), profil)
    assert zaehl_stand.bereitgestellt(state)
    assert not _knoepfe(_ansicht(seite, state, u), "Wdh. zählen")  # vorher: ein Knopf
    einheit_ui.leeren(seite, state)
    assert not zaehl_stand.bereitgestellt(state)
    assert _knoepfe(_ansicht(seite, state, u), "Wdh. zählen")


async def test_laeufe_heute_nennt_einen_leeren_zaehllauf_nicht_gemacht(umgebung) -> None:
    """Ein Zähllauf ohne Zahl hat nichts eingetragen: „Läufe heute“ sagte „gemacht“, dazu
    „Satz 1 · 0 Wdh. (Sensor)“; „Atmung erfassen“ hieß ebenso „gemacht“, und „Fertig“
    versprach „eintragen“ (Runde 3, Befund 10). Jetzt „nichts gezählt“ bzw. „Atmung“."""
    from trainingsapp.ui.components.laeufe_heute import laeufe_karte

    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state)
    gurt.bewegung = False
    _knopf(_ansicht(seite, state, u), "Wdh. zählen").on_click()
    await _sekunden(state, uhr, gurt, 8)
    _knopf(_ansicht(seite, state, u), "Zählen abbrechen").on_click()
    await _bis_vorbei(state, uhr, gurt)
    texte = _texte(laeufe_karte(seite, state, u, lambda: None))
    assert any(t.endswith(" · nichts gezählt") for t in texte)  # vorher: „… · gemacht“
    assert not any("0 Wdh." in t for t in texte) and "nichts einzutragen" in texte

    atem = _kniebeuge(state, "Box Breathing", "duration", typen=["Atmung"])
    _knopf(_ansicht(seite, state, atem), "Atmung erfassen").on_click()
    await _sekunden(state, uhr, gurt, 5)
    (fertig,) = _knoepfe(_ansicht(seite, state, atem), "Fertig")
    assert "eintragen" not in (fertig.tooltip or "")  # P120: nichts ins Tagebuch
    fertig.on_click()
    await _bis_vorbei(state, uhr, gurt)
    texte = _texte(laeufe_karte(seite, state, atem, lambda: None))
    assert any(t.endswith(" · Atmung") for t in texte) and _eintraege(state) == []


async def test_im_plan_ablauf_gibt_es_keinen_knopf_der_nie_zaehlt(umgebung) -> None:
    """Im Plan-Ablauf zählt der Sensor noch nicht (Plan §13) — darum steht dort kein Knopf
    „Wdh. zählen“, der nur „Es läuft schon eine Einheit“ meldete; der Start sagt, warum.
    Nach dem Ablauf ist der Knopf wieder da."""
    from trainingsapp.ui import plan_ablauf

    state, uhr, gurt = umgebung
    seite = Seite()
    u = _kniebeuge(state)
    plan = Plan(name="Beine", subject_id=state.profil.id, items=[PlanItem(exercise_id=u.id)])
    state.plaene.speichern(plan)
    plan = state.plaene.laden(plan.id)
    item = plan.items[0]
    assert _knoepfe(plan_view(seite, state, plan), "Wdh. zählen")
    e = plan_ablauf.starten(seite, state, plan)
    await _sekunden(state, uhr, gurt, 3)
    assert e.laeuft and zaehl_stand.im_plan_ablauf(state)
    assert not zaehl_stand.sichtbar(state, u, item=item)
    assert not _knoepfe(plan_view(seite, state, plan), "Wdh. zählen")  # vorher: ein Knopf
    with pytest.raises(RuntimeError, match="Im Plan-Ablauf zählt der Sensor noch nicht"):
        uebung_lauf.zaehlen_starten(
            seite, state, uebung_lauf.kontext_fuer(u, plan, item), uebung=u, item=item
        )
    assert e.teil("zaehlen") is None and state.messlauf.acc_anforderungen == {}
    einheit_ui.alle_beenden(state)
    await _bis_vorbei(state, uhr, gurt)
    assert _knoepfe(plan_view(seite, state, plan), "Wdh. zählen")
