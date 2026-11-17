"""V4 an der Oberfläche (`docs/plan_paketverweise.md`, Ben 17.11.2026): Kapitel und Plan sagen,
welche Übungen auf ihr Paket warten und woher sie kämen, mit „… laden“ (der Plan beim Bearbeiten,
unter „Aus Paket …“); kommt das Paket, sind sie da und der Hinweis ist weg."""

from __future__ import annotations

import asyncio

import pytest

ft = pytest.importorskip("flet")

from attrappen import Seite  # noqa: E402
from trainingsapp.core.pakete import paket_id, paket_lesen, uebung_id  # noqa: E402
from trainingsapp.ui.components import paket_link  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.kurse import kapitel_view  # noqa: E402
from trainingsapp.ui.views.plan import plan_view  # noqa: E402

A_ID = paket_id("Grundlagen")
A1 = uebung_id(A_ID, "a1")
PAKET_A = {
    "paket": {"id": A_ID, "name": "Grundlagen", "version": 1},
    "exercises": [{"key": "a1", "name": "A eins", "description": "x"}],
}
PAKET_B = {
    "paket": {
        "name": "Für Anna",
        "version": 1,
        "braucht": [{"id": A_ID, "name": "Grundlagen", "quelle": "https://x.invalid/a.json"}],
    },
    "exercises": [{"key": "b1", "name": "B eins", "description": "x"}],
    "plaene": [{"key": "p", "name": "Morgens", "uebungen": [{"uebung": A1}, {"uebung": "b1"}]}],
    "kurse": [
        {
            "key": "kurs",
            "name": "Kurs für Anna",
            "kapitel": [
                {
                    "key": "eins",
                    "titel": "Eins",
                    "plaene": [{"name": "Kapitel", "uebungen": [{"uebung": A1}]}],
                    "bedingung": {"art": "summe", "uebung": A1, "soll": 10},
                }
            ],
        }
    ],
}


class _Seite(Seite):
    def __init__(self) -> None:
        super().__init__()
        self.dialoge: list = []
        self.aufgaben: list = []

    def show_dialog(self, d) -> None:
        self.dialoge.append(d)

    def run_task(self, f, *a, **kw) -> None:
        self.aufgaben.append(asyncio.run(f(*a, **kw)))


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls", "header", "trailing", "leading", "title", "subtitle"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def _mit_data(ansicht, data: str) -> list:
    wurzeln = ansicht.controls if isinstance(ansicht, ft.View) else [ansicht]
    return [c for w in wurzeln for c in alle(w) if getattr(c, "data", None) == data]


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAININGSAPP_DATA_DIR", str(tmp_path))
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


def test_kapitel_und_plan_nennen_was_wartet_und_laden_es(state, monkeypatch) -> None:
    b = paket_lesen(PAKET_B)
    state.pakete.importieren(b, subject_id=state.profil.id)
    (kurs,) = [k for k in state.kurse.alle() if k.package_id == b.paket.id]
    seite = _Seite()

    ansicht = kapitel_view(seite, state, kurs, kurs.kapitel[0], ft.UrlLauncher())
    (satz,) = _mit_data(ansicht, "wartet")
    assert satz.value.startswith("1 Übung dieses Kapitels fehlt hier — sie kommt aus „Grundlagen“")
    (plan,) = state.pakete.des_pakets_plaene(b.paket.id, state.profil.id)
    (satz,) = _mit_data(plan_view(seite, state, plan, bearbeiten=True), "wartet")
    assert satz.value.startswith("1 Übung des Plans fehlt hier")

    geladen: list[tuple[str, bool]] = []

    async def link_importieren(_page, st, url, **kw):  # wie der echte: lädt, importiert, danach
        geladen.append((url, kw["herkunft"]))
        st.pakete.importieren(paket_lesen(PAKET_A), subject_id=st.profil.id)
        await kw["danach"]()

    monkeypatch.setattr(paket_link, "link_importieren", link_importieren)
    (knopf,) = _mit_data(ansicht, "wartet_laden")
    assert knopf.content == "„Grundlagen“ laden"
    knopf.on_click()
    assert geladen == [("https://x.invalid/a.json", True)]

    plan = state.plaene.laden(plan.id)
    assert plan.items[0].exercise_id == A1
    assert _mit_data(plan_view(seite, state, plan, bearbeiten=True), "wartet") == []
    nachher = kapitel_view(seite, state, kurs, kurs.kapitel[0], ft.UrlLauncher())
    assert _mit_data(nachher, "wartet") == []
