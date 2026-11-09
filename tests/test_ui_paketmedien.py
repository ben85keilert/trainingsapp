"""Medien im Paket in der Oberfläche (U3, Ben 9.11.2026, `docs/plan_paketinhalte.md` §7):
Zeile auf der Übungsseite, Ansicht, Editoren behalten Paketdateien, Export als ZIP, Import einer
ZIP über den Pfad. Läuft nur mit `flet`."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import struct
import zipfile
import zlib
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.models import Media, MediaKind, MediaSource  # noqa: E402
from trainingsapp.core.paketdatei import paket_oeffnen, paket_zip  # noqa: E402
from trainingsapp.core.pakete import paket_json, paket_lesen  # noqa: E402
from trainingsapp.core.paketmedien import name_fuer  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402


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


def _klick(knopf, *args):
    ergebnis = knopf.on_click(*args)
    if inspect.isawaitable(ergebnis):
        return asyncio.run(ergebnis)
    return ergebnis


def _png() -> bytes:
    def block(typ: bytes, daten: bytes) -> bytes:
        return (
            struct.pack(">I", len(daten)) + typ + daten + struct.pack(">I", zlib.crc32(typ + daten))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + block(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
        + block(b"IDAT", zlib.compress(b"\x00\x00"))
        + block(b"IEND", b"")
    )


PDF = b"%PDF-1.7 Anleitung"
BILD = name_fuer(hashlib.sha256(_png()).hexdigest(), "png")
BLATT = name_fuer(hashlib.sha256(PDF).hexdigest(), "pdf")


def _paket_zip(tmp_path):
    roh = {
        "paket": {"name": "Knie-Reha", "version": 1},
        "exercises": [
            {
                "key": "beuge",
                "name": "Kniebeuge",
                "media": [
                    {"source": "paket", "uri": BILD, "title": "So sieht es aus"},
                    {"source": "paket", "uri": BLATT, "title": "Übungsblatt"},
                    {"uri": "https://x.org/beuge", "title": "Video"},
                ],
            }
        ],
    }
    (tmp_path / "b.png").write_bytes(_png())
    (tmp_path / "a.pdf").write_bytes(PDF)
    inhalt = paket_lesen(roh)
    ziel = tmp_path / "knie.zip"
    paket_zip(
        ziel,
        paket_json(inhalt.paket, inhalt.uebungen),
        {BILD: tmp_path / "b.png", BLATT: tmp_path / "a.pdf"},
    )
    return ziel


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
        route="/uebung/x",
        views=[],
        routen=[],
        dialoge=[],
        width=390,
        web=False,
        platform=None,
        update=lambda: None,
        pop_dialog=lambda: None,
        push_route=push_route,
    )
    seite.show_dialog = seite.dialoge.append
    return seite


def _uebung(state):
    from trainingsapp.core.pakete import paket_id

    (u,) = [x for x in state.uebungen.alle() if x.package_id == paket_id("Knie-Reha")]
    return u


def test_uebungsseite_zeigt_paketdateien_und_oeffnet_sie(tmp_path, page, state) -> None:
    from trainingsapp.ui.views.paketmedium import paketmedium_view
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    state.pakete.importieren(paket_oeffnen(_paket_zip(tmp_path)), subject_id=state.profil.id)
    assert (tmp_path / "Medien" / "Pakete" / BILD.removeprefix("medien/")).is_file()
    seite = uebung_detail(page, state, _uebung(state), None)
    texte = _texte(seite)
    assert "So sieht es aus" in texte and "Übungsblatt" in texte and "Video" in texte
    assert any(t.startswith("aus dem Paket · ") for t in texte)
    bild = next(x for x in _alle(seite) if getattr(x, "data", None) == ("paketmedium", BILD))
    _klick(bild)
    name = BILD.removeprefix("medien/")
    assert page.routen[-1] == f"/uebung/x/paketmedium/{name}"
    ansicht = paketmedium_view(page, state, "/uebung/x", name)
    assert ansicht.appbar.title.value == "So sieht es aus"
    assert [x for x in _alle(ansicht) if isinstance(x, ft.Image)]
    pdf = paketmedium_view(page, state, "/uebung/x", BLATT.removeprefix("medien/"))
    assert "Öffnen mit …" in [x.content for x in _alle(pdf) if isinstance(x, ft.FilledButton)]
    # Fehlt die Datei, steht das da
    (tmp_path / "Medien" / "Pakete" / name).unlink()
    seite = uebung_detail(page, state, _uebung(state), None)
    assert "Datei fehlt — das Paket neu importieren" in _texte(seite)
    assert "Die Datei fehlt — das Paket neu importieren." in _texte(
        paketmedium_view(page, state, "/uebung/x", name)
    )


def test_editoren_behalten_paketdateien(tmp_path, page, state) -> None:
    from trainingsapp.core.bewegungsbild import mit_bewegungsbild
    from trainingsapp.ui.views.plan_einstellen import plan_einstellen
    from trainingsapp.ui.views.uebung_bearbeiten import uebung_bearbeiten

    state.pakete.importieren(paket_oeffnen(_paket_zip(tmp_path)), subject_id=state.profil.id)
    u = _uebung(state)
    # Das Bild der Bewegung (lokal) dazu — es darf keine Linkzeile werden (Altlast T6)
    u.media = mit_bewegungsbild(u.media, "Bewegung/bewegung_1.gif")
    state.uebungen.speichern(u)
    u = _uebung(state)
    ansicht = uebung_bearbeiten(page, state, u)
    adressen = [
        x.value
        for x in _alle(ansicht)
        if isinstance(x, ft.TextField) and x.label == "Adresse (https://…)"
    ]
    assert adressen == ["https://x.org/beuge"]
    assert _texte(ansicht).count("aus dem Paket") == 2
    speichern = next(
        x
        for x in _alle(ansicht.appbar)
        if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    _klick(speichern)
    neu = _uebung(state)
    assert [(m.source, m.uri) for m in neu.media] == [
        (MediaSource.PAKET, BILD),
        (MediaSource.PAKET, BLATT),
        (MediaSource.URL, "https://x.org/beuge"),
        (MediaSource.LOCAL, "Bewegung/bewegung_1.gif"),
    ]
    # Im Plan: eine Paketdatei an der Planübung bleibt, ohne https-Fehler
    from trainingsapp.core.models import Plan

    plan = Plan(name="Reha", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, neu.id)
    item.media = [Media(kind=MediaKind.PDF, source=MediaSource.PAKET, uri=BLATT, title="Blatt")]
    state.plaene.item_speichern(item)
    item = state.plaene.item_laden(item.id)
    einstellen = plan_einstellen(page, state, state.plaene.laden(plan.id), item, neu)
    assert "Blatt" in _texte(einstellen)
    item.target = {"reps": [10]}
    speichern = next(
        x
        for x in _alle(einstellen.appbar)
        if isinstance(x, ft.TextButton) and x.content == "Speichern"
    )
    _klick(speichern)
    assert not [t for t in _texte(einstellen) if t.startswith("Nur https-Adressen")]
    assert [m.uri for m in state.plaene.item_laden(item.id).media] == [BLATT]


def test_export_mit_paketdateien_wird_zip(tmp_path, page, state, monkeypatch) -> None:
    import trainingsapp.ui.views.pakete as modul
    from trainingsapp.ui.views.pakete import paket_export_view

    inhalt = paket_oeffnen(_paket_zip(tmp_path))
    state.pakete.importieren(inhalt, subject_id=state.profil.id)
    geteilt: list = []

    async def datei_weitergeben(_page, pfad, name, mime):
        geteilt.append((pfad, name, mime))

    monkeypatch.setattr(modul, "datei_weitergeben", datei_weitergeben)
    ansicht = paket_export_view(page, state, "/pakete", inhalt.paket.id)
    knopf = next(x for x in _alle(ansicht) if isinstance(x, ft.FilledButton))
    _klick(knopf)
    ((pfad, name, mime),) = geteilt
    assert name == "uebungspaket_Knie-Reha.zip" and mime == "application/zip"
    assert pfad.parent == tmp_path / "Export"
    with zipfile.ZipFile(pfad) as zf:
        assert sorted(zf.namelist()) == sorted(["paket.json", BILD, BLATT])
    wieder = paket_oeffnen(pfad)
    assert {m.uri for m in wieder.uebungen[0].media} >= {BILD, BLATT}


def test_import_einer_zip_ueber_den_pfad(tmp_path, page, state, monkeypatch) -> None:
    from trainingsapp.ui.views.pakete import pakete_view

    datei = _paket_zip(tmp_path)

    class Waehler:
        async def pick_files(self, **kw):
            assert kw.get("with_data") is False  # nicht die ganze ZIP über die Leitung
            return [SimpleNamespace(bytes=None, path=str(datei), name="knie.zip")]

    monkeypatch.setattr(ft, "FilePicker", Waehler)
    page.aufgaben = []
    page.run_task = lambda f, *a: page.aufgaben.append(asyncio.ensure_future(f(*a)))
    ansicht = pakete_view(page, state)
    knopf = next(x for x in _alle(ansicht) if isinstance(x, ft.FilledButton))
    _klick(knopf)
    blatt = page.dialoge[-1]
    datei_knopf = next(c for c in _alle(blatt) if isinstance(c, ft.FilledTonalButton))
    datei_knopf.on_click(None)

    async def lauf() -> None:
        await blatt.on_dismiss(None)
        offen = [t for t in page.aufgaben if isinstance(t, asyncio.Future)]
        if offen:
            await asyncio.gather(*offen)

    asyncio.run(lauf())
    frage = page.dialoge[-1]
    texte = [c.value for c in frage.content.controls if isinstance(c, ft.Text)]
    assert "• 2 Dateien (Videos, Bilder, PDFs) — 0 kB" in texte
    frage.actions[1].on_click()
    assert (tmp_path / "Medien" / "Pakete" / BLATT.removeprefix("medien/")).is_file()
