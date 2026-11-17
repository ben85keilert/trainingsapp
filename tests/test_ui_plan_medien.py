"""Der Reiter „Medien“ im Plan-Editor (`views/plan_medien.py`, Ben 17.11.2026,
`docs/plan_medien_reiter.md` §3): Übersicht nach Herkunft, je Stück „wo“, Größe und „groß“;
Tippen öffnet, der Stift führt zum Ort, an dem man ändert — hier ändert sich nichts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from mp4_bau import mp4, spur  # noqa: E402
from trainingsapp.core.models import (  # noqa: E402
    Exercise,
    Media,
    MediaKind,
    MediaSource,
    Plan,
)
from trainingsapp.data.material import MaterialRepo  # noqa: E402
from trainingsapp.ui.components import editor_reiter as er  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.plan_medien import dateiinfo, plan_medien_view  # noqa: E402

TECHNIK = "https://x.org/technik"
FILM = "medien/" + "c" * 64 + ".mp4"


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    s.neu_zeichnen = lambda: None
    yield s
    s.schliessen()


@pytest.fixture
def page():
    wege: list[str] = []

    async def push_route(route: str) -> None:
        wege.append(route)

    dialoge: list = []

    def run_task(f, *args):
        asyncio.run(f(*args))

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
        run_task=run_task,
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


def _plan(state: AppState) -> tuple[Exercise, Plan]:
    """Kniebeuge mit Beschreibung, einem Link und einem Video als Paketdatei (2:10, 84 MB —
    deutlich über „Mittel“); im Plan eine Anweisung an der Planübung."""
    ablage = state.pakete.ablage
    pfad = ablage.pfad(FILM)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    kopf = mp4(spur(b"vide", breite=1920, hoehe=1080, dauer_s=130, bilder=3900), dauer_s=130)
    pfad.write_bytes(kopf + bytes(84_000_000 - len(kopf)))
    u = Exercise(
        name="Kniebeuge",
        description="## Ausführung\nTief",
        media=[
            Media(uri=TECHNIK, title="Technik", zeigen=True),
            Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri=FILM, title="Film"),
        ],
    )
    state.uebungen.speichern(u)
    plan = Plan(name="Beine", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    item = state.plaene.uebung_hinzufuegen(plan.id, u.id)
    state.plaene.item_speichern(replace(item, description="## Im Plan\nlangsam"))
    return state.uebungen.laden(u.id), state.plaene.laden(plan.id)


def test_reiter_gruppen_groesse_und_gross(page, state) -> None:
    _u, plan = _plan(state)
    basis = f"/plaene/{plan.id}"
    ansicht = plan_medien_view(page, state, plan, basis)
    assert ansicht.route == f"{basis}/medien" and ansicht.appbar.title.value == "Medien · Beine"
    reiter = [
        x.data
        for x in _alle(ansicht)
        if isinstance(x, ft.Container) and isinstance(x.data, tuple) and x.data[:1] == ("reiter",)
    ]
    # Plan · Uhren · Medien — „Ablauf“ erst mit „Workout“, sein Platz bleibt frei
    assert reiter == [("reiter", ""), ("reiter", "uhren"), ("reiter", "medien")]
    medien_reiter = _daten(ansicht, ("reiter", "medien"))
    assert medien_reiter.on_click is None  # der gewählte
    texte = _texte(ansicht)
    assert "AUS DEN ÜBUNGEN" in texte and "AUS DIESEM PLAN" in texte
    assert _daten(ansicht, "medien_kopf").value == "4 Stücke · 1 Datei · 84 MB"
    assert "Dateien reisen mit, wenn du den Plan als Paket weitergibst; Links nicht." in texte
    assert "Video-Datei · Erklärung · 1080p · 30 fps · 2:10" in texte
    assert "bei 1 · Kniebeuge" in texte and "im „i“ bei 1 · Kniebeuge" in texte
    assert _daten(ansicht, ("medien_groesse", True)).content.value == "84 MB · groß"


def test_tippen_oeffnet_und_aendert_nichts(page, state) -> None:
    _u, plan = _plan(state)
    basis = f"/plaene/{plan.id}"
    page.route = f"{basis}/medien"
    ansicht = plan_medien_view(page, state, plan, basis)
    # Text: ein Blatt zum Lesen
    _daten(ansicht, ("medien_zeile", "Im Plan")).on_click(None)
    blatt = page.dialoge[-1]
    assert isinstance(blatt, ft.BottomSheet)
    assert {"Im Plan", "langsam", "bei 1 · Kniebeuge"} <= set(_texte(blatt))
    # Paketdatei: die Ansicht der Datei über dem Reiter
    asyncio.run(_daten(ansicht, ("medien_zeile", "Film")).on_click(None))
    assert page.wege[-1] == f"{basis}/medien/paketmedium/{'c' * 64}.mp4"
    # Der Link öffnet im Browser — „gesehen“ setzt die Übersicht nicht
    assert MaterialRepo(state.con).gesehen(state.profil.id) == set()


def test_stift_fuehrt_zum_ort_mit_dem_passenden_reiter(page, state) -> None:
    u, plan = _plan(state)
    basis = f"/plaene/{plan.id}"
    ansicht = plan_medien_view(page, state, plan, basis)
    _daten(ansicht, ("medien_aendern", "Technik")).on_click(None)
    ziel = f"/uebung/{u.id}/bearbeiten"
    assert page.wege[-1] == ziel and er.gemerkt(state, ziel) == er.MATERIAL
    _daten(ansicht, ("medien_aendern", "Beschreibung · Kniebeuge")).on_click(None)
    assert er.gemerkt(state, ziel) == er.UEBUNG
    _daten(ansicht, ("medien_aendern", "Im Plan")).on_click(None)
    einstellen = f"{basis}/ziel/{plan.items[0].id}"
    assert page.wege[-1] == einstellen and er.gemerkt(state, einstellen) == er.MATERIAL


def test_ohne_medien_ein_hinweis_und_dateiinfo_ohne_datei(page, state) -> None:
    u = Exercise(name="Planke")
    state.uebungen.speichern(u)
    plan = Plan(name="Leer", subject_id=state.profil.id)
    state.plaene.speichern(plan)
    state.plaene.uebung_hinzufuegen(plan.id, u.id)
    ansicht = plan_medien_view(page, state, state.plaene.laden(plan.id), f"/plaene/{plan.id}")
    assert _daten(ansicht, "medien_kopf").value == "Noch keine Medien"
    assert any(t.startswith("Keine Übung dieses Plans bringt Medien mit") for t in _texte(ansicht))
    fehlt = Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri="medien/" + "d" * 64 + ".mp4")
    assert dateiinfo(state, fehlt) is None and dateiinfo(state, Media(uri=TECHNIK)) is None


def test_weg_mit_text_und_link_zeigt_den_text_und_einen_knopf(page, state) -> None:
    from trainingsapp.core.ablauf import Ablauf, Kante
    from trainingsapp.core.bedingung import Inhalt

    _u, plan = _plan(state)
    item = plan.items[0]
    weg = Kante(item.id, item.id, text="Noch einmal", inhalt=Inhalt("Lockerer", TECHNIK))
    state.plaene.ablauf_setzen(plan.id, Ablauf(an=True, start=item.id, kanten=(weg,)))
    plan = state.plaene.laden(plan.id)
    ansicht = plan_medien_view(page, state, plan, f"/plaene/{plan.id}")
    assert "IM WORKOUT" in _texte(ansicht)
    assert "am Weg von 1 · Kniebeuge zu 1 · Kniebeuge" in _texte(ansicht)
    _daten(ansicht, ("medien_zeile", "Noch einmal")).on_click(None)
    blatt = page.dialoge[-1]
    assert "Lockerer" in _texte(blatt)
    knopf = _daten(blatt, ("medien_link", TECHNIK))
    assert isinstance(knopf, ft.TextButton) and knopf.on_click is not None


def test_plan_selbst_link_dazu_aendern_herausnehmen(page, state) -> None:
    """Stufe 2: Beschreibung und Stücke des Plans selbst — im Blatt, gespeichert beim Schließen."""
    _u, plan = _plan(state)
    basis = f"/plaene/{plan.id}"
    ansicht = plan_medien_view(page, state, plan, basis)
    menue = _daten(ansicht, "plan_medium_dazu")
    menue.items[0].on_click(None)  # „Link …“
    blatt = page.dialoge[-1]
    _daten(blatt, "plan_titel").value = "Einstimmung"
    _daten(blatt, "plan_adresse").value = "https://x.org/einstimmung"
    _daten(blatt, "plan_zeigen").value = True
    asyncio.run(blatt.on_dismiss(None))
    (m,) = state.plaene.laden(plan.id).media
    assert (m.uri, m.title, m.zeigen) == ("https://x.org/einstimmung", "Einstimmung", True)
    # Eine Adresse, die die App nicht öffnen darf, kommt nicht dazu — die Meldung erst danach
    _daten(plan_medien_view(page, state, plan, basis), "plan_medium_dazu").items[0].on_click(None)
    blatt = page.dialoge[-1]
    _daten(blatt, "plan_adresse").value = "http://x.org/unsicher"
    asyncio.run(blatt.on_dismiss(None))
    assert isinstance(page.dialoge[-1], ft.SnackBar) and len(state.plaene.laden(plan.id).media) == 1
    # Ändern und herausnehmen über den Stift der Zeile
    ansicht = plan_medien_view(page, state, plan, basis)
    assert "am Plan · vor dem Start" in _texte(ansicht)
    _daten(ansicht, ("medien_aendern", "Einstimmung")).on_click(None)
    blatt = page.dialoge[-1]
    _daten(blatt, "plan_herausnehmen").on_click(None)
    asyncio.run(blatt.on_dismiss(None))
    assert state.plaene.laden(plan.id).media == []
    # Die Beschreibung
    ansicht = plan_medien_view(page, state, plan, basis)
    _daten(ansicht, "plan_beschreibung_dazu").on_click(None)
    blatt = page.dialoge[-1]
    _daten(blatt, "plan_beschreibung").value = "## So läuft es\nDreimal die Woche"
    asyncio.run(blatt.on_dismiss(None))
    assert state.plaene.laden(plan.id).description == "## So läuft es\nDreimal die Woche"


def test_medien_des_plans_vor_dem_ersten_start(page, state) -> None:
    """Das Blatt geht vor dem ersten Start auf (einmal je Sitzung, bis abgehakt); der Knopf am
    Kopf ist da, solange der Plan etwas hat."""
    from trainingsapp.ui.components import material

    _u, plan = _plan(state)
    assert material.plan_knopf(page, state, plan) is None
    assert material.plan_neu_zeigen(page, state, plan) is False
    state.plaene.medien_setzen(
        plan.id, [Media(uri="https://x.org/einstimmung", title="Einstimmung", zeigen=True)]
    )
    plan = state.plaene.laden(plan.id)
    knopf = material.plan_knopf(page, state, plan)
    assert knopf is not None and knopf.tooltip.startswith("Neu — Medien zum Plan")
    assert material.plan_neu_zeigen(page, state, plan) is True
    blatt = page.dialoge[-1]
    assert "Neu zum Plan" in _texte(blatt) and "Beine" in _texte(blatt)
    # einmal je Sitzung — der nächste Tipp startet
    assert material.plan_neu_zeigen(page, state, plan) is False
    haken = _daten(blatt, ("gesehen", "https://x.org/einstimmung"))
    haken.on_change(SimpleNamespace(control=SimpleNamespace(value=True)))
    state.material_angeboten = set()  # neue Sitzung: abgehakt kommt nicht wieder
    assert material.plan_neu_zeigen(page, state, plan) is False
    assert material.plan_knopf(page, state, plan).icon == ft.Icons.MENU_BOOK_OUTLINED
