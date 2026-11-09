"""Eigene Pakete in der Oberfläche (U4, Ben 9.11.2026): Karte im Paketmanager, Paket anlegen,
Inhalt wählen, exportieren mit Version (erst 1.0.0, unverändert dieselbe, dann klein 1.0.1) und
„Datei fürs Paket“ in „Übung bearbeiten“. Läuft nur mit `flet`."""

from __future__ import annotations

import asyncio
import inspect
import struct
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Exercise, MediaSource  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402

GPS = b"GPS 52.5200 N 13.4050 E"


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
        "appbar",
        "actions",
        "items",
        "header",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    async def push_route(route: str) -> None:
        seite.routen.append(route)

    seite = SimpleNamespace(
        route="/pakete",
        views=[],
        routen=[],
        dialoge=[],
        aufgaben=[],
        width=390,
        web=False,
        platform=None,
        update=lambda: None,
        pop_dialog=lambda: None,
        push_route=push_route,
    )
    seite.show_dialog = seite.dialoge.append
    seite.run_task = lambda f, *a: seite.aufgaben.append(asyncio.ensure_future(f(*a)))
    return seite


def _klick(page, knopf, *args) -> None:
    async def lauf() -> None:
        ergebnis = knopf.on_click(*args)
        if inspect.isawaitable(ergebnis):
            await ergebnis
        offen = [t for t in page.aufgaben if isinstance(t, asyncio.Future) and not t.done()]
        if offen:
            await asyncio.gather(*offen)

    asyncio.run(lauf())


def _dialog_zu(page, dialog) -> None:
    async def lauf() -> None:
        await dialog.on_dismiss(None)
        offen = [t for t in page.aufgaben if isinstance(t, asyncio.Future) and not t.done()]
        if offen:
            await asyncio.gather(*offen)

    asyncio.run(lauf())


def test_eigenes_paket_anlegen_exportieren_und_version(page, state, monkeypatch) -> None:
    import trainingsapp.ui.views.eigene_pakete as modul
    from trainingsapp.ui.views.eigene_pakete import NEU, eigenes_paket_view
    from trainingsapp.ui.views.pakete import pakete_view

    u = Exercise(name="Meine Beuge")
    state.uebungen.speichern(u)
    geteilt: list = []

    async def datei_weitergeben(_page, pfad, name, mime):
        geteilt.append((pfad.name, mime))

    monkeypatch.setattr(modul, "datei_weitergeben", datei_weitergeben)
    manager = pakete_view(page, state, "/pakete")
    assert "EIGENE PAKETE" in _texte(manager)
    _klick(page, _daten(manager, "eigenes_paket_neu"))
    assert page.routen[-1] == "/pakete/eigen/neu"

    ansicht = eigenes_paket_view(page, state, "/pakete", NEU)
    name = next(x for x in _alle(ansicht) if isinstance(x, ft.TextField))
    name.value = "Knie für Anna"
    haken = _daten(ansicht, ("uebungen", u.id))
    haken.value = True
    haken.on_change(SimpleNamespace(control=haken))
    _klick(page, _daten(ansicht, "exportieren"))
    dialog = page.dialoge[-1]
    assert "Version 1.0.0" in _texte(dialog) and "Die erste Fassung." in _texte(dialog)
    dialog.open = True
    _daten(dialog, "los").on_click()
    _dialog_zu(page, dialog)
    assert geteilt == [("uebungspaket_Knie_fuer_Anna.json", "application/json")]
    (ep,) = state.eigene_pakete.alle()
    assert ep.version == 10000 and ep.uebungen == [u.id]

    # Unverändert: dieselbe Version
    ansicht = eigenes_paket_view(page, state, "/pakete", ep.id)
    assert "Zuletzt geteilt: Version 1.0.0" in " ".join(_texte(ansicht))
    _klick(page, _daten(ansicht, "exportieren"))
    assert "Unverändert seit Version 1.0.0 — noch einmal teilen." in _texte(page.dialoge[-1])
    # Geändert (die Übung heißt anders): klein → 1.0.1
    u = state.uebungen.laden(u.id)
    u.name = "Meine tiefe Beuge"
    state.uebungen.speichern(u)
    ansicht = eigenes_paket_view(page, state, "/pakete", ep.id)
    _klick(page, _daten(ansicht, "exportieren"))
    dialog = page.dialoge[-1]
    assert "Version 1.0.1" in _texte(dialog)
    stufe = _daten(dialog, "stufe")
    stufe.selected = ["mittel"]
    stufe.on_change(SimpleNamespace(control=stufe))
    assert "Version 1.1.0" in _texte(dialog)


def test_datei_fuers_paket_in_uebung_bearbeiten(tmp_path, page, state, monkeypatch) -> None:
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    def seg(marker: int, nutzlast: bytes) -> bytes:
        return bytes([0xFF, marker]) + struct.pack(">H", len(nutzlast) + 2) + nutzlast

    foto = tmp_path / "Mein Foto.jpg"
    foto.write_bytes(
        b"\xff\xd8"
        + seg(0xE1, b"Exif\x00\x00" + GPS)
        + seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")
        + b"\x12\x34\xff\xd9"
    )

    class Waehler:
        async def pick_files(self, **_):
            return [SimpleNamespace(path=str(foto), name=foto.name, bytes=None)]

    monkeypatch.setattr(ft, "FilePicker", Waehler)
    u = Exercise(name="Meine Beuge")
    state.uebungen.speichern(u)
    ansicht = uebung_bearbeiten(page, state, state.uebungen.laden(u.id))
    menue = _daten(ansicht, "datei_fuers_paket")
    eintrag = next(i for i in menue.items if i.content == "Datei wählen …")
    asyncio.run(eintrag.on_click())
    titel = [x for x in _alle(ansicht) if isinstance(x, ft.TextField) and x.label == "Titel"]
    assert [t.value for t in titel] == ["Mein Foto"]
    titel[0].value = "So geht es"
    speichern = next(
        x
        for x in _alle(ansicht.appbar)
        if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    _klick(page, speichern)
    (m,) = state.uebungen.laden(u.id).media
    assert (m.source, m.title) == (MediaSource.PAKET, "So geht es")
    assert GPS not in state.pakete.ablage.pfad(m.uri).read_bytes()


def test_eigenes_paket_privat_teilen(page, state, monkeypatch) -> None:
    """U7: Ein eigenes Paket privat weitergeben — die Datei ist verschlüsselt, der Code steht
    danach da und bleibt für jede Fassung."""
    import trainingsapp.ui.views.eigene_pakete as modul
    from trainingsapp.core.paketdatei import CodeNoetig, paket_oeffnen
    from trainingsapp.core.privat import code_normieren, ist_privat
    from trainingsapp.ui.views.eigene_pakete import NEU, eigenes_paket_view

    u = Exercise(name="Nur für Anna")
    state.uebungen.speichern(u)
    geteilt: list[bytes] = []

    async def datei_weitergeben(_page, pfad, name, mime):
        geteilt.append(pfad.read_bytes())

    monkeypatch.setattr(modul, "datei_weitergeben", datei_weitergeben)
    ansicht = eigenes_paket_view(page, state, "/pakete", NEU)
    next(x for x in _alle(ansicht) if isinstance(x, ft.TextField)).value = "Für Anna"
    haken = _daten(ansicht, ("uebungen", u.id))
    haken.value = True
    haken.on_change(SimpleNamespace(control=haken))
    schalter = _daten(ansicht, "privat")
    schalter.value = True
    schalter.on_change(SimpleNamespace(control=schalter))
    _klick(page, _daten(ansicht, "exportieren"))
    dialog = page.dialoge[-1]
    dialog.open = True
    _daten(dialog, "los").on_click()
    _dialog_zu(page, dialog)
    (daten,) = geteilt
    assert ist_privat(daten)
    gezeigt = page.dialoge[-1]
    code_anzeige = next(t for t in _texte(gezeigt) if len(t) == 9 and t[4] == "-")
    code = code_normieren(code_anzeige)
    with pytest.raises(CodeNoetig):
        paket_oeffnen(daten)
    assert paket_oeffnen(daten, code=code).uebungen[0].name == "Nur für Anna"
    (ep,) = state.eigene_pakete.alle()
    assert ep.code == code  # bleibt für jede Fassung
