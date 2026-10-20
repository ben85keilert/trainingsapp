"""Fotos und Videos an Einträgen in der Oberfläche (Ben, 19.10.2026) — Leistungen-Blatt,
Tagebuch, Übung, Einstellungen, Ansicht und Aufnahmeseite (am Rechner: „Datei wählen“)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.anhaenge import BILD, VIDEO, Qualitaet, neuer_anhang  # noqa: E402
from trainingsapp.core.models import Plan  # noqa: E402
from trainingsapp.data.seed import seed_id  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.anhang import anhang_view, reihe_fuer  # noqa: E402
from trainingsapp.ui.views.anhang_aufnahme import anhang_aufnahme_view  # noqa: E402
from trainingsapp.ui.views.einstellungen_anhaenge import einstellungen_anhaenge  # noqa: E402
from trainingsapp.ui.views.leistungen import leistungen_blatt, leistungen_view  # noqa: E402
from trainingsapp.ui.views.tagebuch import tagebuch  # noqa: E402
from trainingsapp.ui.views.uebung_detail import uebung_detail  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200


@pytest.fixture
def welt(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    state = AppState.starten(tmp_path / "app.db")
    plan = Plan(name="Dehnung", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    uebung = state.uebungen.laden(seed_id("nacken_dehnung"))
    session = state.sitzungen.session_fuer(state.profil.id, plan.id, state.heute())
    eintrag = state.sitzungen.eintrag_anlegen(session, uebung, {"hold": [45]}, "gut")
    foto = neuer_anhang(eintrag.id, BILD, Qualitaet.MITTEL, note="links")
    state.anhaenge.anlegen(foto, JPEG)
    video = neuer_anhang(eintrag.id, VIDEO, Qualitaet.KLEIN, dauer_s=9.0)
    state.anhaenge.anlegen(video, b"0" * 900, JPEG)
    yield SimpleNamespace(state=state, uebung=uebung, eintrag=eintrag, foto=foto, video=video)
    state.schliessen()


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
        services=[],
        platform=ft.PagePlatform.LINUX,
        web=False,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: None,
        push_route=push_route,
        run_task=lambda *_a: None,
    )


def _alle(c):
    yield c
    for name in (
        "content",
        "controls",
        "appbar",
        "title",
        "subtitle",
        "leading",
        "trailing",
        "items",
    ):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _alle(k)


def _texte(wurzel) -> list[str]:
    return [str(c.value) for c in _alle(wurzel) if isinstance(c, ft.Text) and c.value]


def _knoepfe(wurzel) -> list[str]:
    return [
        str(c.content)
        for c in _alle(wurzel)
        if isinstance(c, ft.OutlinedButton | ft.FilledButton | ft.TextButton)
        and isinstance(c.content, str)
    ]


def test_leistungen_zeigen_knoepfe_und_kacheln(welt, page) -> None:
    ansicht = leistungen_view(
        page, welt.state, f"/tag/{welt.state.heute()}/leistungen/{welt.uebung.id}", welt.uebung
    )
    knoepfe = _knoepfe(ansicht)
    assert "Foto" in knoepfe and "Video" in knoepfe
    bilder = [c for c in _alle(ansicht) if isinstance(c, ft.Image)]
    assert len(bilder) == 2  # Foto und Frontbild des Videos
    assert any(isinstance(c, ft.PopupMenuButton) for c in _alle(ansicht))  # Büroklammer
    assert any("0:09" in t for t in _texte(ansicht))  # Dauer im Overlay


def test_blatt_ohne_eintrag_bittet_erst_einzutragen(welt, page) -> None:
    andere = welt.state.uebungen.laden(seed_id("wandsitz"))
    blatt = leistungen_blatt(page, welt.state, andere, welt.state.heute())
    assert any("erst eintragen" in t for t in _texte(blatt))
    assert "Foto" not in _knoepfe(blatt)


def test_tagebuch_zeigt_aufnahmen_block(welt, page) -> None:
    kontrolle = tagebuch(page, welt.state)
    texte = _texte(kontrolle)
    assert any(t.startswith("Aufnahmen · ") for t in texte)
    assert any("1 Foto, 1 Video" in t for t in texte)
    assert len([c for c in _alle(kontrolle) if isinstance(c, ft.Image)]) == 2


def test_uebung_zeigt_raster(welt, page) -> None:
    browser = SimpleNamespace()
    ansicht = uebung_detail(page, welt.state, welt.uebung, browser)
    assert "FOTOS UND VIDEOS" in _texte(ansicht)
    assert any(isinstance(c, ft.SegmentedButton) for c in _alle(ansicht))
    # Eine Übung ohne Aufnahmen hat den Abschnitt nicht
    andere = welt.state.uebungen.laden(seed_id("wandsitz"))
    assert "FOTOS UND VIDEOS" not in _texte(uebung_detail(page, welt.state, andere, browser))


def test_einstellungen_zeigen_ueberblick(welt, page) -> None:
    ansicht = einstellungen_anhaenge(page, welt.state)
    texte = _texte(ansicht)
    assert any("1 Foto, 1 Video" in t for t in texte)
    assert any("Nichts aufzuräumen" in t for t in texte)
    # Eine verwaiste Datei taucht auf
    fremd = welt.state.anhaenge.wurzel / "2026" / "01" / "x.jpg"
    fremd.parent.mkdir(parents=True, exist_ok=True)
    fremd.write_bytes(JPEG)
    assert any("1 verwaiste Datei" in t for t in _texte(einstellungen_anhaenge(page, welt.state)))


def test_ansicht_foto_und_video(welt, page) -> None:
    foto = anhang_view(page, welt.state, "/", welt.foto)
    assert any(isinstance(c, ft.InteractiveViewer) for c in _alle(foto))
    assert any("Mittel · 1080p" in t for t in _texte(foto))
    video = anhang_view(page, welt.state, "/", welt.video)
    assert not any(isinstance(c, ft.InteractiveViewer) for c in _alle(video))
    assert any("0:09" in t for t in _texte(video))
    # Unter der Übung blättern die Pfeile durch alle Aufnahmen der Übung
    reihe = reihe_fuer(welt.state, f"/uebung/{welt.uebung.id}", welt.foto)
    assert [a.id for a in reihe] == [welt.foto.id, welt.video.id]


def test_aufnahmeseite_am_rechner(welt, page) -> None:
    ansicht = anhang_aufnahme_view(
        page, welt.state, f"/anhang/aufnehmen/{welt.eintrag.id}/foto", welt.eintrag, BILD
    )
    assert "Datei wählen" in _knoepfe(ansicht)
    assert any("Nackendehnung" in t or "Foto:" in t for t in _texte(ansicht))
