"""Videos hinter Links (Stufe 7, `docs/plan_rueckweg_handy.md`, Ben 17.11.2026): laden nur über
https und nur Videodateien, je Server erlaubt, nur im WLAN (umstellbar), gespeichert in der
Paketablage, angezeigt unter Anhänge, weggeräumt, wenn das Medium wegfällt."""

from __future__ import annotations

import asyncio
import hashlib
import io
from types import SimpleNamespace

import pytest

pytest.importorskip("flet")

import flet as ft

from trainingsapp.core.linkvideos import LinkFehler, laden
from trainingsapp.core.models import Exercise, Media, MediaKind, MediaSource
from trainingsapp.ui.state import AppState

VIDEO = b"\x00\x00\x00\x18ftypmp42" + b"x" * 5000


class _Antwort(io.BytesIO):
    def __init__(self, daten: bytes, url: str, typ: str) -> None:
        super().__init__(daten)
        self._url = url
        self.headers = {"Content-Type": typ, "Content-Length": str(len(daten))}

    def geturl(self) -> str:
        return self._url


def _oeffner(daten: bytes = VIDEO, typ: str = "video/mp4", ziel: str | None = None):
    def oeffnen(anfrage):
        return _Antwort(daten, ziel or anfrage.full_url, typ)

    return oeffnen


def test_laden_nur_videodateien_ueber_https(tmp_path) -> None:
    name, n = laden("https://x.invalid/a/v.mp4", tmp_path, oeffnen=_oeffner())
    assert name == f"medien/{hashlib.sha256(VIDEO).hexdigest()}.mp4" and n == len(VIDEO)
    assert (tmp_path / name.removeprefix("medien/")).read_bytes() == VIDEO
    with pytest.raises(LinkFehler, match="Webseite"):
        laden("https://x.invalid/v.mp4", tmp_path, oeffnen=_oeffner(b"<html>", "text/html"))
    with pytest.raises(LinkFehler, match="nicht https"):
        laden("https://x.invalid/v.mp4", tmp_path, oeffnen=_oeffner(ziel="http://y.invalid/v"))
    with pytest.raises(LinkFehler, match="zu groß"):
        laden("https://x.invalid/v.mp4", tmp_path, grenze=10, oeffnen=_oeffner())
    with pytest.raises(LinkFehler, match="nur https"):
        laden("http://x.invalid/v.mp4", tmp_path)
    # Ohne Endung in der Adresse: der Content-Type sagt es
    name, _ = laden("https://x.invalid/datei?id=1", tmp_path, oeffnen=_oeffner())
    assert name.endswith(".mp4")
    assert not list(tmp_path.glob("*.teil")), "keine halben Dateien"


@pytest.fixture
def state(tmp_path):
    s = AppState.starten(tmp_path / "app.db")
    yield s
    s.schliessen()


def test_server_mobil_und_ablage_ohne_leichen(state, tmp_path) -> None:
    assert state.link_server() == [] and not state.link_mobil()
    state.link_server_erlauben("dl.dropbox.com")
    state.link_server_erlauben("x.invalid")
    assert state.link_server_erlaubt("x.invalid") and not state.link_server_erlaubt("y.invalid")
    state.link_server_entziehen("x.invalid")
    assert state.link_server() == ["dl.dropbox.com"]
    state.link_mobil_setzen(True)
    assert state.link_mobil()

    ablage = state.pakete.ablage
    url = "https://x.invalid/v.mp4"
    name, n = laden(url, ablage.ordner, oeffnen=_oeffner())
    ablage.link_merken(url, name, "Erklärvideo", n)
    # Die Adresse steht an einer Übung — die Kopie bleibt beim Aufräumen
    u = Exercise(name="Kniebeuge", media=[Media(kind=MediaKind.VIDEO, uri=url, title="Video")])
    state.uebungen.speichern(u)
    ablage.aufraeumen()
    assert ablage.link_datei(url) == name and [v.title for v in ablage.links()] == ["Erklärvideo"]
    # Das Medium fällt weg — beim nächsten Aufräumen gehen Zeile und Datei
    u.media = []
    state.uebungen.speichern(u)
    ablage.aufraeumen()
    assert ablage.link_datei(url) is None and ablage.links() == []
    assert not ablage.vorhanden(name)


def _seite():
    gezeigt: list = []
    seite = SimpleNamespace(
        route="/uebung/u1",
        views=[],
        update=lambda: None,
        show_dialog=gezeigt.append,
        pop_dialog=lambda: None,
    )
    seite.run_task = lambda f, *a, **kw: gezeigt.append(("aufgabe", f))
    return seite, gezeigt


def alle(wurzel):
    yield wurzel
    for name in ("content", "controls", "actions", "title", "trailing", "subtitle"):
        kind = getattr(wurzel, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from alle(k)


def test_zeile_fragt_beim_ersten_server_und_merkt_ihn(state) -> None:
    from trainingsapp.ui.components.medienliste import medium_zeile

    seite, gezeigt = _seite()
    medium = Media(kind=MediaKind.VIDEO, uri="https://x.invalid/v.mp4", title="Video")
    zeile = medium_zeile(seite, state, medium)
    assert zeile.data == ("linkvideo", medium.uri)
    assert "in der App laden" in zeile.subtitle.value
    asyncio.run(zeile.on_click())
    dialog = gezeigt[-1]
    hinweis = next(c for c in alle(dialog) if getattr(c, "data", None) == "server_hinweis")
    assert "x.invalid" in hinweis.value and "IP-Adresse" in hinweis.value
    laden_knopf = dialog.actions[-1]
    laden_knopf.on_click()
    assert state.link_server_erlaubt("x.invalid")
    assert gezeigt[-1][0] == "aufgabe", "danach lädt es"
    # Ein Link, der keine Videodatei ist, bleibt ein Link in den Browser
    seite_zeile = medium_zeile(seite, state, Media(kind=MediaKind.VIDEO, uri="https://youtu.be/x"))
    assert seite_zeile.data == ("medium", "https://youtu.be/x")
    # Liegt das Video schon da, heißt die Zeile so
    ablage = state.pakete.ablage
    name, n = laden(medium.uri, ablage.ordner, oeffnen=_oeffner())
    ablage.link_merken(medium.uri, name, "Video", n)
    assert "auf dem Gerät" in medium_zeile(seite, state, medium).subtitle.value


def test_nur_im_wlan(state) -> None:
    from trainingsapp.ui.components.linkvideo import netz_frei

    class Dienst:
        def __init__(self, getaktet: bool) -> None:
            self.getaktet = getaktet

        async def stand(self):
            return {"getaktet": self.getaktet}

    assert asyncio.run(netz_frei(state)), "ohne Gerätedienst (Rechner): frei"
    state.installieren = Dienst(getaktet=True)
    assert not asyncio.run(netz_frei(state))
    state.link_mobil_setzen(True)
    assert asyncio.run(netz_frei(state))
    state.link_mobil_setzen(False)
    state.installieren = Dienst(getaktet=False)
    assert asyncio.run(netz_frei(state))


def test_einstellungen_zeigen_server_und_geladene_videos(state) -> None:
    from trainingsapp.ui.views.einstellungen_anhaenge import geladene_videos_karte
    from trainingsapp.ui.views.updates import _link_server_zeilen

    seite, _ = _seite()
    state.link_server_erlauben("x.invalid")
    zeilen = [c for z in _link_server_zeilen(seite, state) for c in alle(z)]
    eintrag = next(c for c in zeilen if getattr(c, "data", None) == ("link_server", "x.invalid"))
    eintrag.trailing.on_click()
    assert state.link_server() == []

    ablage = state.pakete.ablage
    url = "https://x.invalid/v.mp4"
    u = Exercise(name="K", media=[Media(kind=MediaKind.VIDEO, uri=url, source=MediaSource.URL)])
    state.uebungen.speichern(u)
    name, n = laden(url, ablage.ordner, oeffnen=_oeffner())
    ablage.link_merken(url, name, "Erklärvideo", n)
    karte = geladene_videos_karte(seite, state)
    zeile = next(c for c in alle(karte) if getattr(c, "data", None) == ("link_download", url))
    zeile.trailing.on_click()
    assert ablage.links() == [] and not ablage.vorhanden(name), "nur die Kopie geht"
    assert state.uebungen.laden(u.id).media[0].uri == url, "der Link bleibt"
