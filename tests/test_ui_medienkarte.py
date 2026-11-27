"""Die Medienkarte im Kurs (`ui/components/medienkarte.py`, `docs/plan_kurs_medien_ansicht.md`
§2 und §3): Fläche mit Art, Dauer und Aufschrift; Video spielt in der Karte, es spielt immer
nur eines; Ton als schmale Karte; Link und PDF tun, was die Zeile tat."""

from __future__ import annotations

from types import SimpleNamespace

import flet as ft
import pytest

pytest.importorskip("flet_video")

from trainingsapp.core.models import Media, MediaKind, MediaSource
from trainingsapp.ui.components import medienkarte as mk
from trainingsapp.ui.state import AppState


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


@pytest.fixture
def page():
    p = SimpleNamespace(route="/kurse/k/c", views=[], update=lambda: None, dialoge=[], width=412)

    async def push_route(route: str) -> None:
        p.route = route

    p.push_route = push_route
    p.show_dialog = p.dialoge.append
    p.run_task = lambda f, *a: None
    return p


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def texte(c) -> list[str]:
    return [str(x.value) for x in alle(c) if isinstance(x, ft.Text)]


def teil(c, kennung: str):
    return next(
        x for x in alle(c) if isinstance(getattr(x, "data", None), tuple) and x.data[0] == kennung
    )


def datei(state: AppState, zeichen: str, endung: str, art: MediaKind, **mehr) -> Media:
    """Ein Medium mit einer (leeren) Datei in der Ablage."""
    name = zeichen * 64 + "." + endung
    state.pakete.ablage.ordner.mkdir(parents=True, exist_ok=True)
    (state.pakete.ablage.ordner / name).write_bytes(b"x" * 2_000_000)
    return Media(kind=art, source=MediaSource.PAKET, uri="medien/" + name, **mehr)


def test_video_ohne_bild_zeigt_die_titelkarte_und_spielt_in_der_karte(page, state) -> None:
    film = datei(state, "a", "mp4", MediaKind.VIDEO, title="So geht der Seitstütz", text="Hüfte!")
    karte = mk.medienkarte(page, state, film)
    halter = teil(karte, "medienkarte_halter")
    # Titelkarte: die Aufschrift ist der Titel; oben links die Art
    assert teil(halter, "medienkarte_aufschrift").value == "So geht der Seitstütz"
    assert "VIDEO" in texte(halter)
    # der Titel steht auf der Fläche — darunter nur noch die Beschriftung
    assert texte(karte)[-1] == "Hüfte!" and texte(karte).count("So geht der Seitstütz") == 1
    assert halter.aspect_ratio == 16 / 9  # die Fläche hält ihr Format selbst

    gesehen: list[int] = []
    karte = mk.medienkarte(page, state, film, beim_oeffnen=lambda: gesehen.append(1))
    halter = teil(karte, "medienkarte_halter")
    halter.on_click()
    # der Spieler steht in der Karte; „gesehen“ ist gemeldet
    assert getattr(halter.content, "data", None) == "videospieler" and gesehen == [1]
    assert state.medienkarte_aktiv is not None

    # Es spielt immer nur eines: Ein zweites Video macht das erste wieder zum Bild
    zweiter = datei(state, "b", "mp4", MediaKind.VIDEO, title="Zweites")
    halter2 = teil(mk.medienkarte(page, state, zweiter), "medienkarte_halter")
    halter2.on_click()
    assert getattr(halter.content, "data", None) == ("medienkarte_flaeche",)
    assert getattr(halter2.content, "data", None) == "videospieler"
    # ✕ am Spieler: wieder das Bild
    next(x for x in alle(halter2) if getattr(x, "data", None) == "video_schliessen").on_click()
    assert getattr(halter2.content, "data", None) == ("medienkarte_flaeche",)
    assert state.medienkarte_aktiv is None


def test_titelbild_gewaehlt_automatisch_und_nur_text(page, state) -> None:
    film = datei(state, "a", "mp4", MediaKind.VIDEO, title="Seitstütz")
    # automatisch: das Bild, das beim Hinzufügen entstand
    assert mk.titelbild_pfad(state, film) is None
    auto = state.titelbilder.schreiben(film.uri, b"jpeg")
    assert mk.titelbild_pfad(state, film) == auto
    halter = teil(mk.medienkarte(page, state, film), "medienkarte_halter")
    assert teil(halter, "medienkarte_bild") is not None
    # mit Bild steht keine Aufschrift da — außer der eigenen
    assert not [
        x for x in alle(halter) if getattr(x, "data", None) == ("medienkarte_aufschrift", film.uri)
    ]
    film.titelbild_text = "Hüfte hoch"
    halter = teil(mk.medienkarte(page, state, film), "medienkarte_halter")
    assert teil(halter, "medienkarte_aufschrift").value == "Hüfte hoch"

    # gewählt: ein Bild aus der Ablage geht vor
    eigenes = datei(state, "c", "jpg", MediaKind.IMAGE)
    film.titelbild = eigenes.uri
    assert mk.titelbild_pfad(state, film) == state.pakete.ablage.pfad(eigenes.uri)
    # nur Text: kein Bild, auch wenn eines da wäre
    film.titelbild = "text"
    assert mk.titelbild_pfad(state, film) is None
    # die Wahl reist mit
    assert film.als_dict()["titelbild"] == "text"
    assert film.als_dict()["titelbild_text"] == "Hüfte hoch"


def test_ton_ist_eine_schmale_karte(page, state) -> None:
    ton = datei(state, "d", "m4a", MediaKind.AUDIO, title="Atmung dabei")
    karte = mk.medienkarte(page, state, ton)
    assert any(t.startswith("Atmung dabei · Ton") for t in texte(karte))
    assert not [x for x in alle(karte) if getattr(x, "data", None) == ("medienkarte_flaeche",)]
    assert teil(karte, "medienkarte_ton") is not None


def test_link_und_fehlende_datei(page, state) -> None:
    link = Media(uri="https://example.org/seite", title="Übersicht")
    karte = mk.medienkarte(page, state, link)
    halter = teil(karte, "medienkarte_halter")
    assert {"LINK", "example.org", "Übersicht"} <= set(texte(halter))
    assert halter.on_click is not None
    # nichts aus dem Netz: Ein Link hat nie ein Bild, außer ein gewähltes
    assert mk.titelbild_pfad(state, link) is None

    fehlt = Media(kind=MediaKind.VIDEO, source=MediaSource.PAKET, uri="medien/" + "e" * 64 + ".mp4")
    karte = mk.medienkarte(page, state, fehlt)
    assert "Datei fehlt — das Paket neu importieren." in texte(karte)
    assert teil(karte, "medienkarte_halter").on_click is None


def test_miniatur_und_eckdaten(page, state) -> None:
    film = datei(state, "a", "mp4", MediaKind.VIDEO, title="Seitstütz")
    assert mk.eckdaten_von(state, film)[0] == "Video · 2 MB"
    klein = mk.miniatur(state, film)
    assert (klein.width, klein.height) == (64, 36)


# -- Das Blatt „Titelbild“ (`components/titelbild_blatt.py`) -----------------------------------


def _blatt(page):
    return page.dialoge[-1]


def _d(c, wert):
    return next(x for x in alle_blatt(c) if getattr(x, "data", None) == wert)


def alle_blatt(wurzel):
    yield wurzel
    for name in ("content", "controls"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle_blatt(k)


def test_titelbild_blatt_bild_aus_dem_video_text_und_nur_text(page, state, monkeypatch) -> None:
    """Ben, 27.11.2026: „Man fährt durch und klickt ein Bild, kann einen Text dazusetzen.“"""
    import asyncio

    from trainingsapp.ui import standbild
    from trainingsapp.ui.components import titelbild_blatt

    film = datei(state, "a", "mp4", MediaKind.VIDEO, title="Seitstütz")
    gefragt: list[float] = []

    async def aus_video(_state, _pfad, sekunden):
        gefragt.append(sekunden)
        return b"\xff\xd8bild-an-der-stelle\xff\xd9"

    async def ablegen(_state, daten, endung):
        assert endung == "jpg" and daten.startswith(b"\xff\xd8")
        return "medien/" + "9" * 64 + ".jpg"

    monkeypatch.setattr(standbild, "aus_video", aus_video)
    monkeypatch.setattr(standbild, "moeglich", lambda _s: True)
    monkeypatch.setattr(titelbild_blatt.paketdatei, "ablegen", ablegen)

    ergebnis: list[tuple[str, str]] = []
    titelbild_blatt.oeffnen(page, state, film, lambda b, t: ergebnis.append((b, t)))
    blatt = _blatt(page)
    assert _d(blatt, "titelbild_nehmen") is not None  # der Spieler mit dem Knopf steht da
    asyncio.run(_d(blatt, "titelbild_nehmen").on_click())
    assert gefragt == [0.0]  # der Spieler antwortet im Test nicht — dann der Anfang
    _d(blatt, "titelbild_text").value = "Hüfte hoch"
    asyncio.run(_d(blatt, "titelbild_fertig").on_click())
    assert ergebnis == [("medien/" + "9" * 64 + ".jpg", "Hüfte hoch")]
    # das neue Bild ist bis zum Speichern vorgemerkt — das Aufräumen lässt es liegen
    assert "medien/" + "9" * 64 + ".jpg" in state.pakete.ablage._entwuerfe

    # „Nur Text“ nimmt das Bild weg, „Automatisch“ stellt zurück
    film.titelbild = ergebnis[0][0]
    titelbild_blatt.oeffnen(page, state, film, lambda b, t: ergebnis.append((b, t)))
    blatt = _blatt(page)
    schalter = _d(blatt, "titelbild_nur_text")
    schalter.value = True
    schalter.on_change()
    asyncio.run(_d(blatt, "titelbild_fertig").on_click())
    assert ergebnis[-1] == ("text", "")
    titelbild_blatt.oeffnen(page, state, film, lambda b, t: ergebnis.append((b, t)))
    _d(_blatt(page), "titelbild_auto").on_click()
    asyncio.run(_d(_blatt(page), "titelbild_fertig").on_click())
    assert ergebnis[-1] == ("", "")
    assert titelbild_blatt.stand_text("text") == "nur Text"


def test_titelbild_reist_im_paket_mit_und_bleibt_beim_aufraeumen(state) -> None:
    from trainingsapp.core.models import Exercise
    from trainingsapp.core.pakete import paketmedien_in

    bild = datei(state, "c", "jpg", MediaKind.IMAGE)
    film = datei(state, "a", "mp4", MediaKind.VIDEO, title="Seitstütz", titelbild=bild.uri)
    film.titelbild_text = "Hüfte hoch"
    uebung = Exercise(name="Seitstütz", media=[film])
    assert paketmedien_in([uebung], [], []) == {film.uri, bild.uri}
    state.uebungen.speichern(uebung)
    geladen = state.uebungen.laden(uebung.id).media[0]
    assert (geladen.titelbild, geladen.titelbild_text) == (bild.uri, "Hüfte hoch")
    # das Titelbild nennt nur der Zusatz des Stücks — das Aufräumen findet es dort
    state.pakete.ablage.aufraeumen()
    assert state.pakete.ablage.pfad(bild.uri).is_file()
