"""Zurück speichert (Ben, 16.10.2026: „Am besten wäre ein Autosave“) — `ui/components/zurueck.py`.

Flutter fragt vor jedem Zurück (``can_pop=False``, ``on_confirm_pop``); hier
steht `View.confirm_pop` durch eine Liste ersetzt, die die Antworten sammelt.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Exercise  # noqa: E402
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.components.zurueck import zurueck_speichert  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


@pytest.fixture
def page():
    routen: list[str] = []
    dialoge: list = []

    async def push_route(route: str) -> None:
        routen.append(route)

    return SimpleNamespace(
        route="/",
        views=[],
        routen=routen,
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        push_route=push_route,
    )


def _zurueck(page, ansicht) -> list[bool]:
    """Wie die Systemtaste: Flutter fragt, die Ansicht antwortet — die Antworten zurück."""
    antworten: list[bool] = []

    async def confirm_pop(soll: bool) -> None:
        antworten.append(soll)

    ansicht.confirm_pop = confirm_pop
    page.views = [ft.View(route="/unten"), ansicht]
    assert ansicht.can_pop is False
    asyncio.run(ansicht.on_confirm_pop(None))
    return antworten


def _alle(wurzel):
    yield wurzel
    for name in ("content", "controls"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _felder(ansicht) -> list:
    return [c for v in ansicht.controls for c in _alle(v) if isinstance(c, ft.TextField)]


# ---------------------------------------------------------------------------
# Die Hilfe selbst
# ---------------------------------------------------------------------------


def test_unveraendert_ist_ein_gewoehnliches_zurueck(page) -> None:
    ansicht = zurueck_speichert(
        page, ft.View(route="/oben"), geaendert=lambda: False, speichern=lambda: "nie"
    )
    assert _zurueck(page, ansicht) == [True]
    assert page.routen == [] and page.dialoge == []


def test_geaendert_speichert_und_geht_selbst_zurueck(page) -> None:
    gespeichert: list[bool] = []
    ansicht = zurueck_speichert(
        page,
        ft.View(route="/oben"),
        geaendert=lambda: True,
        speichern=lambda: gespeichert.append(True),  # None = gespeichert
    )
    assert _zurueck(page, ansicht) == [False]  # Flutter geht nicht selbst
    assert gespeichert == [True]
    assert page.routen == ["/unten"]
    (snack,) = page.dialoge
    assert isinstance(snack, ft.SnackBar) and snack.content.value == "Gespeichert"


def test_unvollstaendig_fragt_weiter_oder_verwerfen(page) -> None:
    ansicht = zurueck_speichert(
        page,
        ft.View(route="/oben"),
        geaendert=lambda: True,
        speichern=lambda: "Ein Name muss sein.",
    )
    assert _zurueck(page, ansicht) == [False]
    (frage,) = page.dialoge
    assert "Ein Name muss sein." in frage.content.value
    weiter, verwerfen = frage.actions[1], frage.actions[0]
    assert weiter.content == "Weiter bearbeiten" and verwerfen.content == "Verwerfen"

    frage.open = True  # wie nach page.show_dialog
    weiter.on_click()
    assert not frage.open and page.routen == []  # bleibt auf der Seite

    frage.open = True
    verwerfen.on_click()
    assert page.routen == []  # erst, wenn Flutter den Dialog geschlossen hat
    asyncio.run(frage.on_dismiss(None))
    assert page.routen == ["/unten"]


# ---------------------------------------------------------------------------
# Die Formulare
# ---------------------------------------------------------------------------


def test_uebung_bearbeiten_speichert_beim_zurueck(page, state) -> None:
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    wade = state.uebungen.laden(seed_id("wadenheben"))
    ansicht = uebung_bearbeiten(page, state, wade)
    name = _felder(ansicht)[0]
    assert name.label == "Name"
    assert _zurueck(page, ansicht) == [True]  # nichts geändert

    name.value = "Wadenheben einbeinig"
    assert _zurueck(page, ansicht) == [False]
    assert state.uebungen.laden(wade.id).name == "Wadenheben einbeinig"
    assert page.routen == ["/unten"]


def test_neue_uebung_ohne_namen_fragt(page, state) -> None:
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    vorher = len(state.uebungen.alle())
    ansicht = uebung_bearbeiten(page, state, None)
    assert _zurueck(page, ansicht) == [True]  # leer geöffnet, leer verlassen

    beschreibung = _felder(ansicht)[1]
    beschreibung.value = "Nur eine Beschreibung"
    assert _zurueck(page, ansicht) == [False]
    (frage,) = page.dialoge
    assert "Ein Name muss sein." in frage.content.value
    assert len(state.uebungen.alle()) == vorher


def test_planuebung_einstellen_speichert_beim_zurueck(page, state) -> None:
    from trainingsapp.core.models import Plan
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen

    plan = Plan(subject_id=state.profil.id, name="Test")
    state.plaene.speichern(plan)
    u = Exercise(name="Kniebeuge", result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    state.uebungen.speichern(u)
    item = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    ansicht = plan_einstellen(page, state, state.plaene.laden(plan.id), item, u)
    chip_15 = next(
        c
        for v in ansicht.controls
        for c in _alle(v)
        if isinstance(c, ft.Chip) and getattr(c.label, "value", "") == "+15"
    )
    chip_15.on_select()  # 15 abwählen
    assert _zurueck(page, ansicht) == [False]
    assert state.plaene.item_laden(item.id).quick == {"reps": [10, 20]}
    assert page.routen == ["/unten"]


def test_timer_profil_speichert_beim_zurueck(page, state) -> None:
    from trainingsapp.ui.views.timer import timer_bearbeiten_view

    ansicht = timer_bearbeiten_view(page, state, None, "/")
    name, *_ = _felder(ansicht)
    name.value = "Planke"
    assert _zurueck(page, ansicht) == [False]
    assert "Planke" in [p.name for p in state.timer_profile()]
    assert page.routen == ["/unten"]


def test_profilname_gilt_beim_zurueck(page, state) -> None:
    from trainingsapp.ui.views.profile import profile_view

    ansicht = profile_view(page, state)
    feld = next(f for f in _felder(ansicht) if f.value == state.profil.name)
    feld.value = "Ben"
    assert _zurueck(page, ansicht) == [False]
    assert state.profile.laden(state.profil.id).name == "Ben"

    leer = profile_view(page, state)
    feld = next(f for f in _felder(leer) if f.value == "Ben")
    feld.value = "  "
    page.dialoge.clear()
    assert _zurueck(page, leer) == [False]
    (frage,) = page.dialoge
    assert "Namen" in frage.content.value
    assert state.profile.laden(state.profil.id).name == "Ben"


def test_korrektur_eines_eintrags_beim_zurueck(page, state) -> None:
    from trainingsapp.ui.app import formular_korrektur

    plan_id = None
    uebung = state.uebungen.laden(seed_id("wadenheben"))
    session = state.sitzungen.session_fuer(state.profil.id, plan_id, state.heute())
    eintrag = state.sitzungen.eintrag_anlegen(session, uebung, {"reps": 10}, "alt")
    ansicht = formular_korrektur(page, state, eintrag)
    notiz = next(f for f in _felder(ansicht) if f.label == "Notiz")
    notiz.value = "neu"
    assert _zurueck(page, ansicht) == [False]
    (neu,) = state.sitzungen.eintraege(session.id)  # die Korrektur ersetzt den alten
    assert neu.note == "neu" and neu.id != eintrag.id
    assert page.routen == [f"/tag/{state.heute().isoformat()}"]  # wie „Speichern"


def test_titelblatt_speichert_beim_wegwischen() -> None:
    from trainingsapp.ui.components.titel import titel_blatt

    gespeichert: list[tuple[str, str]] = []
    blatt = titel_blatt("Alt", "", [], lambda t, b: gespeichert.append((t, b)))
    blatt.on_dismiss(None)  # unverändert weggewischt: nichts
    assert gespeichert == []

    blatt = titel_blatt("Alt", "", [], lambda t, b: gespeichert.append((t, b)))
    titel, beschreibung = (c for c in _alle(blatt.content) if isinstance(c, ft.TextField))
    beschreibung.value = "ruhig"
    blatt.on_dismiss(None)
    assert gespeichert == [("Alt", "ruhig")]

    blatt = titel_blatt("Alt", "", [], lambda t, b: gespeichert.append((t, b)))
    titel, _ = (c for c in _alle(blatt.content) if isinstance(c, ft.TextField))
    titel.value = "Verworfen"
    abbrechen = next(
        c for c in _alle(blatt.content) if isinstance(c, ft.TextButton) and c.content == "Abbrechen"
    )
    abbrechen.on_click()
    blatt.on_dismiss(None)
    assert gespeichert == [("Alt", "ruhig")]  # „Abbrechen" verwirft


def test_titelblatt_liste_filtert_merkt_und_entfernt() -> None:
    """Ben, 26.10.2026: Überschriften aus der gespeicherten Liste — Tippen filtert, ✕
    nimmt eine heraus, Neues lässt sich merken; Antippen übernimmt und zeigt wieder alles."""
    from trainingsapp.core.models import HrvTitel
    from trainingsapp.ui.components.titel import titel_blatt

    vorrat = [HrvTitel(name="Intervalle Beine"), HrvTitel(name="Ruhe morgens", angeheftet=True)]
    entfernt: list[str] = []
    gemerkt: list[str] = []

    def merken(name: str) -> HrvTitel:
        gemerkt.append(name)
        return HrvTitel(name=name)

    blatt = titel_blatt(
        "",
        "",
        ["Plan A"],
        lambda t, b: None,
        gespeicherte=vorrat,
        merken=merken,
        entfernen=lambda t: entfernt.append(t.name),
    )
    titel, _ = (c for c in _alle(blatt.content) if isinstance(c, ft.TextField))

    def zeilen() -> list[str]:
        return [z.title.value for z in _alle(blatt.content) if isinstance(z, ft.ListTile)]

    assert zeilen() == ["Plan A", "Intervalle Beine", "Ruhe morgens"]
    titel.value = "ruh"
    titel.on_change(None)
    assert zeilen() == ["Ruhe morgens", "„ruh“ merken"]
    merk = next(
        z for z in _alle(blatt.content) if isinstance(z, ft.ListTile) and "merken" in z.title.value
    )
    merk.on_click()
    assert gemerkt == ["ruh"]
    assert zeilen() == ["Plan A", "Intervalle Beine", "Ruhe morgens", "ruh"]  # gewählt: alles
    kreuz = next(
        z.trailing
        for z in _alle(blatt.content)
        if isinstance(z, ft.ListTile) and z.title.value == "Intervalle Beine"
    )
    kreuz.on_click()
    assert entfernt == ["Intervalle Beine"]
    assert zeilen() == ["Plan A", "Ruhe morgens", "ruh"]
    next(
        z for z in _alle(blatt.content) if isinstance(z, ft.ListTile) and z.title.value == "ruh"
    ).on_click()
    assert titel.value == "ruh" and zeilen() == ["Plan A", "Ruhe morgens", "ruh"]


def test_titelblatt_hoechstens_sieben_zeilen_feste_hoehe() -> None:
    """Ben, 26.10.2026: höchstens sieben Zeilen („+n weitere“), und die Liste behält beim
    Filtern ihre Höhe — das Feld darüber wandert nicht."""
    from trainingsapp.core.models import HrvTitel
    from trainingsapp.ui.components.titel import MAX_ZEILEN, ZEILE, titel_blatt

    vorrat = [HrvTitel(name=f"Titel {i:02d}") for i in range(10)]
    blatt = titel_blatt("", "", [], lambda t, b: None, gespeicherte=vorrat)
    liste = next(
        c for c in _alle(blatt.content) if isinstance(c, ft.Column) and c.height == 8 * ZEILE
    )
    assert len([z for z in liste.controls if isinstance(z, ft.ListTile)]) == MAX_ZEILEN
    hinweis = [c.value for c in _alle(liste) if isinstance(c, ft.Text) and "weitere" in c.value]
    assert hinweis == ["+3 weitere — zum Filtern tippen"]
    titel, _ = (c for c in _alle(blatt.content) if isinstance(c, ft.TextField))
    titel.value = "Titel 0"
    titel.on_change(None)
    assert len([z for z in liste.controls if isinstance(z, ft.ListTile)]) == MAX_ZEILEN
    assert liste.height == 8 * ZEILE  # unverändert
    titel.value = "Titel 09"
    titel.on_change(None)
    assert [z.title.value for z in liste.controls if isinstance(z, ft.ListTile)] == ["Titel 09"]
    assert liste.height == 8 * ZEILE

    kurz = titel_blatt("", "", [], lambda t, b: None, gespeicherte=vorrat[:2])
    assert any(c.height == 2 * ZEILE for c in _alle(kurz.content) if isinstance(c, ft.Column))
