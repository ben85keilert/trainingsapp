"""Oberfläche der Kurse (Ben, 15.10.2026): Liste, Kurs, Kapitel, Weiter und Freischalten.

Wie `test_ui_pakete.py`: Ansichten bauen, Handler direkt aufrufen. Läuft nur
mit `flet` (nicht in der CI-Gruppe `ci`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.kurse import GELESEN, MESSUNG, TAGE  # noqa: E402
from trainingsapp.ui.state import AppState  # noqa: E402
from trainingsapp.ui.views.kurse import kapitel_view, kurs_view, kurse_liste  # noqa: E402
from trainingsapp.ui.views.uebungen import uebungen  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/", views=[], update=lambda: None, dialoge=[])

    async def push_route(route: str) -> None:
        p.route = route

    p.push_route = push_route
    p.show_dialog = p.dialoge.append
    p.pop_dialog = lambda: p.dialoge.pop() if p.dialoge else None
    return p


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls", "spans", "trailing", "leading", "title", "subtitle"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def texte(ansicht) -> list[str]:
    wurzeln = ansicht.controls if isinstance(ansicht, ft.View) else [ansicht]
    gefunden: list[str] = []
    for c in (c for v in wurzeln for c in alle(v)):
        if isinstance(c, ft.Text | ft.TextSpan):
            gefunden.append(getattr(c, "value", None) or getattr(c, "text", None) or "")
        elif isinstance(c, ft.Markdown):
            gefunden.append(c.value)
    return gefunden


def knopf(ansicht, beschriftung: str):
    for c in (c for v in ansicht.controls for c in alle(v)):
        if isinstance(c, ft.FilledButton | ft.FilledTonalButton) and c.content == beschriftung:
            return c
    raise AssertionError(f"Knopf „{beschriftung}“ fehlt: {texte(ansicht)}")


async def klick(control) -> None:
    ergebnis = control.on_click()
    if ergebnis is not None:
        await ergebnis


def test_kursliste_und_dritter_reiter(page, state) -> None:
    liste = kurse_liste(page, state)
    inhalt = texte(liste)
    assert "HRV-Messung verstehen" in inhalt
    assert any("noch nicht begonnen" in t for t in inhalt)
    reiter = uebungen(page, state)
    assert reiter.length == 3
    labels = [t.label for c in alle(reiter) if isinstance(c, ft.TabBar) for t in c.tabs]
    assert labels == ["Übungen", "Pläne", "Kurse"]


def test_kurs_zeigt_kapitel_mit_status(page, state) -> None:
    (kurs,) = state.kurse.alle()
    ansicht = kurs_view(page, state, kurs)
    assert ansicht.route == f"/kurse/{kurs.id}"
    inhalt = texte(ansicht)
    assert f"1. {kurs.kapitel[0].titel}" in inhalt
    assert any("jetzt dran" in t for t in inhalt) and any("gesperrt" in t for t in inhalt)
    knopf(ansicht, "Kurs beginnen")


@pytest.mark.asyncio
async def test_weiter_schliesst_ab_und_oeffnet_das_naechste(page, state) -> None:
    (kurs,) = state.kurse.alle()
    erstes, zweites = kurs.kapitel[0], kurs.kapitel[1]
    browser = ft.UrlLauncher()
    ansicht = kapitel_view(page, state, kurs, erstes, browser)
    assert ansicht.route == f"/kurse/{kurs.id}/{erstes.id}"
    # Öffnen = erreichen
    assert erstes.id in state.kurse.staende(state.profil.id, kurs.id)
    assert any("Herzratenvariabilität" in t for t in texte(ansicht))  # der Markdown-Text
    assert erstes.bedingung.art == GELESEN

    await klick(knopf(ansicht, "Weiter"))
    staende = state.kurse.staende(state.profil.id, kurs.id)
    assert staende[erstes.id].abgeschlossen is not None and not staende[erstes.id].uebersprungen
    assert zweites.id in staende  # das nächste ist erreicht
    assert page.route == f"/kurse/{kurs.id}/{zweites.id}"


@pytest.mark.asyncio
async def test_link_im_kapiteltext_oeffnet_nur_https(page, state) -> None:
    """S1: Markdown-Links und Medien aus Paketen gehen nur als https:// oder mailto: an den
    Browser; alles andere bleibt zu, mit Hinweis — auch was die Datenbank liefert."""
    from trainingsapp.core.models import Media, MediaKind
    from trainingsapp.ui.components.links import NICHT_GEOEFFNET

    (kurs,) = state.kurse.alle()
    erstes = kurs.kapitel[0]
    erstes.media.append(Media(kind=MediaKind.VIDEO, uri="intent://scan/#Intent;end", title="x"))
    erstes.media.append(Media(kind=MediaKind.VIDEO, uri="https://example.org/v", title="y"))
    geoeffnet: list[str] = []

    async def launch_url(url: str) -> None:
        geoeffnet.append(url)

    browser = SimpleNamespace(launch_url=launch_url)
    ansicht = kapitel_view(page, state, kurs, erstes, browser)
    (markdown,) = [c for v in ansicht.controls for c in alle(v) if isinstance(c, ft.Markdown)]

    await markdown.on_tap_link(SimpleNamespace(data="intent://scan/#Intent;end"))
    await markdown.on_tap_link(SimpleNamespace(data="tel:+49123"))
    assert geoeffnet == []
    assert [d.content.value for d in page.dialoge] == [NICHT_GEOEFFNET, NICHT_GEOEFFNET]
    await markdown.on_tap_link(SimpleNamespace(data="https://example.org/hrv"))
    assert geoeffnet == ["https://example.org/hrv"]

    kacheln = [
        c
        for v in ansicht.controls
        for c in alle(v)
        if isinstance(c, ft.ListTile) and c.title.value in ("x", "y")
    ]
    assert len(kacheln) == 2
    for kachel in kacheln:
        await kachel.on_click()
    assert geoeffnet == ["https://example.org/hrv", "https://example.org/v"]
    assert len(page.dialoge) == 3


@pytest.mark.asyncio
async def test_freischalten_fragt_einmal_und_markiert_uebersprungen(page, state) -> None:
    (kurs,) = state.kurse.alle()
    messen = next(k for k in kurs.kapitel if k.bedingung.art == MESSUNG)
    # Bis dahin durchklicken
    for k in kurs.kapitel[: kurs.kapitel.index(messen)]:
        state.kurse.kapitel_erreichen(kurs, k, state.profil.id)
        state.kurse.kapitel_abschliessen(kurs, k, state.profil.id)
    browser = ft.UrlLauncher()
    ansicht = kapitel_view(page, state, kurs, messen, browser)
    inhalt = texte(ansicht)
    assert any("noch keine Messung von 5 min" in t for t in inhalt)
    with pytest.raises(AssertionError):
        knopf(ansicht, "Weiter")  # Bedingung nicht erfüllt: kein „Weiter“

    await klick(knopf(ansicht, "Trotzdem freischalten"))
    (dialog,) = page.dialoge
    assert any("Noch keine Messung von 5 min" in t for t in texte(dialog.content))
    bestaetigen = next(a for a in dialog.actions if isinstance(a, ft.FilledButton))
    bestaetigen.on_click()
    await dialog.on_dismiss()
    staende = state.kurse.staende(state.profil.id, kurs.id)
    assert staende[messen.id].uebersprungen and staende[messen.id].abgeschlossen is not None
    naechstes = kurs.kapitel[kurs.kapitel.index(messen) + 1]
    assert page.route == f"/kurse/{kurs.id}/{naechstes.id}"

    # Im Kurs steht es als übersprungen
    assert any("übersprungen" in t for t in texte(kurs_view(page, state, kurs)))


def test_kapitel_mit_plan_legt_den_plan_an(page, state) -> None:
    (kurs,) = state.kurse.alle()
    atmen = next(k for k in kurs.kapitel if k.bedingung.art == TAGE)
    for k in kurs.kapitel[: kurs.kapitel.index(atmen)]:
        state.kurse.kapitel_erreichen(kurs, k, state.profil.id)
        state.kurse.kapitel_abschliessen(kurs, k, state.profil.id)
    ansicht = kapitel_view(page, state, kurs, atmen, ft.UrlLauncher())
    inhalt = texte(ansicht)
    assert "Kurs: Ruhig atmen" in inhalt and any("0 von 3 Tagen" in t for t in inhalt)
    (plan,) = state.kurse.kapitel_plaene(atmen.id, state.profil.id)
    assert plan.aktiv and plan.steht_an(state.heute())
    assert plan in state.plaene.alle(state.profil.id)
    # Gesperrtes Kapitel: nur Hinweis, kein Knopf
    letztes = kurs.kapitel[-1]
    gesperrt = kapitel_view(page, state, kurs, letztes, ft.UrlLauncher())
    assert any("gesperrt" in t for t in texte(gesperrt))
    with pytest.raises(AssertionError):
        knopf(gesperrt, "Weiter")


def test_bilder_im_kapiteltext_sind_links_bis_man_sie_einschaltet(page, state) -> None:
    """S2 (Ben, 20.10.2026): Ein Bild im Kapiteltext lüde beim Öffnen vom Server des
    Paketautors — darum Vorgabe aus: Es steht als Link, der erst auf Tipp öffnet."""
    (kurs,) = state.kurse.alle()
    erstes = kurs.kapitel[0]
    erstes.text = "Haltung: ![Rücken gerade](https://example.org/r.png)\n\nText"

    def markdown() -> ft.Markdown:
        ansicht = kapitel_view(page, state, kurs, erstes, ft.UrlLauncher())
        (m,) = [c for v in ansicht.controls for c in alle(v) if isinstance(c, ft.Markdown)]
        return m

    assert markdown().value == "Haltung: [Bild: Rücken gerade](https://example.org/r.png)\n\nText"
    state.kapitel_bilder_setzen(True)
    assert markdown().value == erstes.text
