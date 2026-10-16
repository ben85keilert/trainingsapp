"""Dialoge zeichnen erst nach dem Schließen neu (`ui/components/dialoge.py`).

Flet awaitet einen Handler nur, wenn `inspect.iscoroutinefunction` ihn
erkennt — alles andere ruft es synchron auf. Darum prüfen die Tests genau
diese Bedingung an den echten Dialogen, nicht nur, ob sich ``on_dismiss``
aufrufen lässt.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.pakete import GRUNDAUSSTATTUNG  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.components.dialoge import (  # noqa: E402
    Erledigt,
    Nachher,
    reste_dialog,
    schliessen,
)
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.pakete import (  # noqa: E402
    entfallene_dialog,
    import_rueckfrage,
    paket_view,
)
from trainingsapp.ui.views.uebung_detail import uebung_detail  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


@pytest.fixture
def page():
    dialoge: list = []
    return SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
    )


def test_flet_erkennt_nur_die_methode_als_koroutine() -> None:
    nachher = Nachher()
    assert inspect.iscoroutinefunction(nachher.bei_schliessen)
    assert not inspect.iscoroutinefunction(nachher)  # die Instanz liefe in Flet nie


def test_aktionen_laufen_nach_dem_schliessen_einmal() -> None:
    lauf: list[str] = []

    async def spaeter() -> None:
        lauf.append("async")

    nachher = Nachher()
    nachher.danach(lambda: lauf.append("sync"))
    nachher.danach(spaeter)
    asyncio.run(nachher.bei_schliessen(None))
    asyncio.run(nachher.bei_schliessen(None))
    assert lauf == ["sync", "async"]


def test_paketdialoge_haben_einen_koroutinen_handler(page, state) -> None:
    wade = state.uebungen.laden(seed_id("wadenheben"))
    wade.description = "Meine Fassung"
    state.uebungen.speichern(wade)

    detail = uebung_detail(page, state, wade, ft.UrlLauncher())
    knopf = next(
        c
        for v in detail.controls
        for c in _alle(v)
        if isinstance(c, ft.TextButton) and c.content == "Auf Paketstand zurücksetzen"
    )
    knopf.on_click()
    assert inspect.iscoroutinefunction(page.dialoge[-1].on_dismiss)

    ansicht = paket_view(page, state, "/pakete", state.pakete.laden(GRUNDAUSSTATTUNG))
    entfernen = next(
        c
        for v in ansicht.controls
        for c in _alle(v)
        if isinstance(c, ft.OutlinedButton) and c.content == "Paket entfernen"
    )
    entfernen.on_click()
    assert inspect.iscoroutinefunction(page.dialoge[-1].on_dismiss)
    offen = entfallene_dialog(page, state, state.pakete.laden(GRUNDAUSSTATTUNG), [wade], [])
    assert inspect.iscoroutinefunction(offen.on_dismiss)

    inhalt = state.pakete.inhalt(GRUNDAUSSTATTUNG)
    dialog = import_rueckfrage(page, state, inhalt, state.pakete.vorschau(inhalt))
    assert inspect.iscoroutinefunction(dialog.on_dismiss)


def test_profil_loeschen_zeichnet_erst_nach_dem_schliessen(page, state) -> None:
    """profile.py hatte das 1:1-Muster pop_dialog → neu_zeichnen (Durchsicht 15.10.2026)."""
    from trainingsapp.ui.views.profile import profile_view

    state.profil_anlegen("Zweites")
    gezeichnet: list[str] = []
    state.neu_zeichnen = lambda: gezeichnet.append("neu")  # type: ignore[method-assign]
    ansicht = profile_view(page, state)
    knopf = next(
        c
        for v in ansicht.controls
        for c in _alle(v)
        if isinstance(c, ft.IconButton) and c.icon == ft.Icons.DELETE_OUTLINE and not c.disabled
    )
    knopf.on_click()
    dialog = page.dialoge[-1]
    assert inspect.iscoroutinefunction(dialog.on_dismiss)
    dialog.actions[-1].on_click()  # „Löschen"
    assert gezeichnet == []  # noch nicht — der Dialog ist erst zu, wenn Flutter es sagt
    asyncio.run(dialog.on_dismiss(None))
    assert gezeichnet == ["neu"]


# ---------------------------------------------------------------------------
# Liegengebliebene Dateien beim Start (Ben, 16.10.2026: Backup-Dialog fror ein)
# ---------------------------------------------------------------------------


def _reste(page, tmp_path, fehler: bool = False):
    offen = [tmp_path / "a.json", tmp_path / "b.json"]
    for pfad in offen:
        pfad.write_text("{}", encoding="utf-8")

    async def uebernehmen(pfad):
        if fehler:
            raise ValueError("Backup unlesbar")
        offen.remove(pfad)
        return Erledigt("übernommen", f"/ziel/{pfad.stem}")

    def loeschen(pfad):
        pfad.unlink()
        offen.remove(pfad)
        return Erledigt("gelöscht")

    dialog = reste_dialog(
        page,
        titel="Liegengeblieben",
        text="Übernehmen oder löschen?",
        offen=lambda: list(offen),
        beschriftung=lambda pfad: f"Datei {pfad.stem}",
        knopf="Übernehmen",
        uebernehmen=uebernehmen,
        loeschen=loeschen,
    )
    dialog.open = True  # wie nach page.show_dialog
    return dialog, offen


def _knopf_in_zeile(dialog, zeile: int, art):
    zeilen = dialog.content.controls[1].controls
    return next(c for c in _alle(zeilen[zeile]) if type(c) is art)


def test_reste_dialog_schliesst_genau_sich_und_meldet_erst_danach(page, tmp_path) -> None:
    routen: list[str] = []

    async def push_route(route: str) -> None:
        routen.append(route)

    page.push_route = push_route
    dialog, offen = _reste(page, tmp_path)
    assert inspect.iscoroutinefunction(dialog.on_dismiss)

    uebernehmen = _knopf_in_zeile(dialog, 0, ft.FilledTonalButton)
    asyncio.run(uebernehmen.on_click())
    assert [p.stem for p in offen] == ["b"]
    assert dialog.open  # „b" ist noch offen
    assert page.dialoge == []  # keine SnackBar, solange der Dialog offen ist
    asyncio.run(uebernehmen.on_click())  # der zweite Tipp: nichts mehr zu tun, kein Fehler

    _knopf_in_zeile(dialog, 0, ft.TextButton).on_click()  # „b" löschen
    assert offen == [] and not (tmp_path / "b.json").exists()
    assert not dialog.open  # zu — ohne pop_dialog, das den obersten Dialog träfe
    assert page.dialoge == [] and routen == []

    asyncio.run(dialog.on_dismiss(None))  # Flutter meldet: wirklich zu
    (snack,) = page.dialoge
    assert isinstance(snack, ft.SnackBar) and snack.content.value == "übernommen · gelöscht"
    assert routen == ["/ziel/a"]


def test_reste_dialog_fehler_bleibt_in_der_zeile(page, tmp_path) -> None:
    dialog, offen = _reste(page, tmp_path, fehler=True)
    asyncio.run(_knopf_in_zeile(dialog, 0, ft.FilledTonalButton).on_click())
    assert len(offen) == 2 and dialog.open
    texte = [c.value for c in _alle(dialog.content) if isinstance(c, ft.Text)]
    assert "Nicht übernommen: Backup unlesbar" in texte
    assert page.dialoge == []

    dialog.actions[0].on_click()  # „Später" schließt genau diesen Dialog
    assert not dialog.open
    schliessen(dialog)  # schon zu: nichts passiert


def _alle(wurzel):
    yield wurzel
    for name in ("content", "controls"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)
