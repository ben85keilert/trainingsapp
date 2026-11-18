"""Die Ansicht „Verkleinern“ (`views/verkleinern.py`, Ben 17.11.2026, `docs/plan_medien_reiter.md`
§5): grobes Schema mit Größe vorher, das Original bleibt, die Kopie ansehen, übernehmen oder
verwerfen — und der Einstieg aus dem Reiter „Medien“. Der echte Lauf braucht ffmpeg (die CI hat
keins und überspringt ihn)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from mp4_bau import mp4, spur  # noqa: E402
from trainingsapp.core.models import Exercise, Media, MediaKind, MediaSource, Plan  # noqa: E402
from trainingsapp.core.paketmedien import dateiname, name_fuer  # noqa: E402
from trainingsapp.ui import verkleinern as weg  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views import verkleinern as vk  # noqa: E402
from trainingsapp.ui.views.plan_medien import plan_medien_view  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    vk._ENTWUERFE.clear()
    s.schliessen()


@pytest.fixture
def page():
    wege: list[str] = []

    async def push_route(route: str) -> None:
        wege.append(route)

    dialoge: list = []
    return SimpleNamespace(
        route="/",
        views=[],
        dialoge=dialoge,
        wege=wege,
        width=390,
        update=lambda: None,
        show_dialog=dialoge.append,
        pop_dialog=lambda: dialoge.pop() if dialoge else None,
        push_route=push_route,
        run_task=lambda f, *a: asyncio.run(f(*a)),
    )


def _alle(c):
    yield c
    for name in ("content", "controls", "leading", "title", "subtitle", "trailing", "appbar"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _texte(c) -> list[str]:
    return [x.value for x in _alle(c) if isinstance(x, ft.Text) and isinstance(x.value, str)]


def _daten(c, wert):
    return next(x for x in _alle(c) if getattr(x, "data", None) == wert)


def _ablegen(state: AppState, daten: bytes) -> str:
    import hashlib

    name = name_fuer(hashlib.sha256(daten).hexdigest(), "mp4")
    pfad = state.pakete.ablage.pfad(name)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)
    return name


def _plan_mit_video(state: AppState, name: str) -> tuple[Exercise, Plan]:
    u = Exercise(
        name="Kniebeuge",
        media=[Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=name, title="Film")],
    )
    state.uebungen.speichern(u)
    plan = Plan(name="Beine", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    state.plaene.uebung_hinzufuegen(plan.id, u.id)
    return u, state.plaene.laden(plan.id)


def test_schema_schaetzung_und_ohne_umwandler(page, state, monkeypatch) -> None:
    # Ein künstlicher Kopf: 1080p, 30 fps, 2:10 — 84 MB
    kopf = mp4(
        spur(b"vide", breite=1920, hoehe=1080, dauer_s=130, bilder=3900),
        spur(b"soun", dauer_s=130),
        dauer_s=130,
    )
    name = _ablegen(state, kopf + bytes(84_000_000 - len(kopf)))
    _plan_mit_video(state, name)
    monkeypatch.setattr(weg, "ffmpeg", lambda: None)  # kein Umwandler auf diesem „Gerät“
    ansicht = vk.verkleinern_view(page, state, "/plaene/p/medien", dateiname(name))
    assert ansicht.route == f"/plaene/p/medien/verkleinern/{dateiname(name)}"
    assert _daten(ansicht, "verkleinern_original").value == (
        "Jetzt · 1080p · 30 fps · 2:10 · 84 MB"
    )
    texte = _texte(ansicht)
    assert {"Klein", "Mittel", "Groß"} <= set(texte)
    assert _daten(ansicht, "verkleinern_schaetzung").value == "Neu etwa 14 MB · jetzt 84 MB"
    # Genauer: 360p, sparsam, ohne Ton — die Schätzung läuft mit, keine Vorlage mehr gewählt
    _daten(ansicht, "verkleinern_genauer").on_click(None)
    aufloesung = _daten(ansicht, "verkleinern_aufloesung")
    assert [s.value for s in aufloesung.segments] == ["360", "480", "720", "1080"]
    aufloesung.on_change(SimpleNamespace(control=SimpleNamespace(selected=["360"])))
    _daten(ansicht, "verkleinern_ton").on_change(
        SimpleNamespace(control=SimpleNamespace(selected=["ohne"]))
    )
    assert _daten(ansicht, "verkleinern_schaetzung").value == "Neu etwa 4 MB · jetzt 84 MB"
    # Ohne Umwandler: „Erstellen“ geht nicht, ein Satz sagt warum
    assert _daten(ansicht, "verkleinern_erstellen").disabled
    assert _daten(ansicht, "verkleinern_weg").value == weg.KEIN_WEG


def test_einstieg_aus_der_uebersicht(page, state) -> None:
    kopf = mp4(spur(b"vide", breite=1920, hoehe=1080, dauer_s=130, bilder=3900), dauer_s=130)
    name = _ablegen(state, kopf + bytes(84_000_000 - len(kopf)))
    _u, plan = _plan_mit_video(state, name)
    basis = f"/plaene/{plan.id}"
    ansicht = plan_medien_view(page, state, plan, basis)
    chip = _daten(ansicht, ("medien_groesse", True))
    assert chip.tooltip == "Verkleinern …"
    chip.on_click(None)
    assert page.wege[-1] == f"{basis}/medien/verkleinern/{dateiname(name)}"
    assert state.paketmedium_titel[dateiname(name)] == "Film"


ffmpeg_da = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ohne ffmpeg")


def _echtes_video(tmp_path) -> bytes:
    quelle = tmp_path / "quelle.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-b:v",
            "6M",
            "-c:a",
            "aac",
            str(quelle),
        ],
        check=True,
    )
    return quelle.read_bytes()


@ffmpeg_da
async def test_erstellen_vergleichen_uebernehmen_und_original(page, state, tmp_path) -> None:
    name = _ablegen(state, _echtes_video(tmp_path))
    u, plan = _plan_mit_video(state, name)
    item = plan.items[0]
    state.plaene.item_speichern(
        replace(item, media=[Media(uri="https://x.org/stufe", ersetzt=name)])
    )
    ablage = state.pakete.ablage
    seite = SimpleNamespace(**{**vars(page), "run_task": lambda f, *a: None})
    vorher = ft.View(route="/plaene/p/medien")
    ansicht = vk.verkleinern_view(seite, state, "/plaene/p/medien", dateiname(name))
    seite.views = [vorher, ansicht]
    _daten(ansicht, ("verkleinern_vorlage", "klein")).on_click(None)
    await _daten(ansicht, "verkleinern_erstellen").on_click(None)
    entwurf = vk._ENTWUERFE[name]
    assert ablage.vorhanden(entwurf.neu) and ablage.vorhanden(name)  # das Original bleibt
    assert entwurf.info is not None and entwurf.info.kurze_seite == 480
    zeigen = _daten(ansicht, "verkleinern_zeigen")
    assert [s.value for s in zeigen.segments] == ["original", "neu"]
    # Verwerfen: die Kopie weg, das Schema wieder da
    erste = entwurf.neu
    _daten(ansicht, "verkleinern_verwerfen").on_click(None)
    assert not ablage.vorhanden(erste) and name not in vk._ENTWUERFE
    # Noch einmal, dann übernehmen
    await _daten(ansicht, "verkleinern_erstellen").on_click(None)
    neu = vk._ENTWUERFE[name].neu
    await _daten(ansicht, "verkleinern_uebernehmen").on_click(None)
    assert [m.uri for m in state.uebungen.laden(u.id).media] == [neu]
    assert state.plaene.item_laden(item.id).media[0].ersetzt == neu
    assert ablage.original(neu) == name and seite.wege[-1] == "/plaene/p/medien"
    # In der Ansicht der neuen Datei: „Original wieder nehmen“
    wieder = vk.verkleinern_view(seite, state, "/plaene/p/medien", dateiname(neu))
    seite.views = [vorher, wieder]
    await _daten(wieder, "verkleinern_original_nehmen").on_click(None)
    assert [m.uri for m in state.uebungen.laden(u.id).media] == [name]
    assert not ablage.vorhanden(neu)


def test_einstieg_auf_der_uebungsseite_auch_ohne_plan(page, state) -> None:
    """Ein Video einer Übung, die in keinem Plan steht, erreicht man über ihre Seite."""
    from trainingsapp.ui.views.uebung_detail import uebung_detail

    kopf = mp4(spur(b"vide", breite=1920, hoehe=1080, dauer_s=130, bilder=3900), dauer_s=130)
    name = _ablegen(state, kopf + bytes(84_000_000 - len(kopf)))
    u = Exercise(
        name="Planke",
        media=[
            Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=name, title="Seitlich"),
            Media(uri="https://x.org/link", title="Ein Link"),
        ],
    )
    state.uebungen.speichern(u)
    ansicht = uebung_detail(page, state, state.uebungen.laden(u.id), None)
    knoepfe = [x for x in _alle(ansicht) if getattr(x, "data", None) == ("verkleinern", name)]
    assert len(knoepfe) == 1  # nur am Video aus dem Paket, nicht am Link
    asyncio.run(knoepfe[0].on_click(None))
    assert page.wege[-1] == f"/uebung/{u.id}/verkleinern/{dateiname(name)}"
    assert state.paketmedium_titel[dateiname(name)] == "Seitlich"
