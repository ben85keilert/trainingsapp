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
from trainingsapp.ui.views.anhang_aufnahme import _Aufnahme, anhang_aufnahme_view  # noqa: E402
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


def _umbrechend_mit_ausdehnung(wurzel) -> list:
    """Zeilen mit ``wrap=True``, in denen ein Kind ``expand`` hat — Flutter legt sie als Wrap
    an, ein Expanded darin ist ein Layoutfehler: Die Release-App zeigt statt des Abschnitts
    eine leere graue/weiße Fläche (Ben, 21.10.2026: „großes weißes Fenster bei Fotos und
    Videos“)."""
    return [
        c
        for c in _alle(wurzel)
        if isinstance(c, ft.Row) and c.wrap and any(k.expand for k in c.controls)
    ]


def test_uebung_zeigt_raster(welt, page) -> None:
    browser = SimpleNamespace()
    ansicht = uebung_detail(page, welt.state, welt.uebung, browser)
    assert "FOTOS UND VIDEOS" in _texte(ansicht)
    assert any(isinstance(c, ft.SegmentedButton) for c in _alle(ansicht))
    assert not _umbrechend_mit_ausdehnung(ansicht)
    # Eine Übung ohne Aufnahmen hat den Abschnitt nicht
    andere = welt.state.uebungen.laden(seed_id("wandsitz"))
    assert "FOTOS UND VIDEOS" not in _texte(uebung_detail(page, welt.state, andere, browser))


def test_keine_ausdehnung_in_umbrechenden_zeilen(welt, page) -> None:
    """Dieselbe Regel für alle Ansichten mit Anhängen: Blatt, Seite, Tagebuch, Tag,
    Einstellungen, Einzelansicht."""
    from trainingsapp.ui.views.tag import tagesansicht

    heute = welt.state.heute()
    ansichten = [
        leistungen_blatt(page, welt.state, welt.uebung, heute),
        leistungen_view(page, welt.state, f"/leistungen/{welt.uebung.id}", welt.uebung),
        tagebuch(page, welt.state),
        tagesansicht(page, welt.state, heute),
        einstellungen_anhaenge(page, welt.state),
        anhang_view(page, welt.state, "/", welt.foto),
        anhang_view(page, welt.state, "/", welt.video),
    ]
    for ansicht in ansichten:
        assert not _umbrechend_mit_ausdehnung(ansicht), ansicht


async def test_verwerfen_laesst_die_kamera_an(welt, page) -> None:
    """Ben, 21.10.2026: „wenn ein Bild verworfen wird, ist die Kamera danach deaktiviert“ —
    das Ergebnis ersetzte die Kamera im Baum, flet-camera gab dabei den Controller frei.
    Jetzt liegt es über ihr (`Camera.content`), „Verwerfen“ nimmt es nur weg."""
    flet_camera = pytest.importorskip("flet_camera")
    a = _Aufnahme(page, welt.state, welt.eintrag, BILD)
    a.kamera = flet_camera.Camera()
    a.flaeche.content = a.kamera
    a.bereit = True
    a.daten = JPEG
    a.ergebnis_zeigen()
    assert a.flaeche.content is a.kamera and isinstance(a.kamera.content, ft.Container)
    await a.verwerfen()
    assert a.flaeche.content is a.kamera and a.kamera.content is None
    assert a.bereit and a.daten is None


class _Kamera:
    """Was die Seite von flet-camera braucht — schreibt die Aufrufe mit."""

    def __init__(self, blitz: bool = True) -> None:
        self.aufrufe: list[tuple[str, ...]] = []
        self.content = None
        self.blitz = blitz

    async def set_flash_mode(self, modus) -> None:
        if not self.blitz:
            raise RuntimeError("Diese Kamera hat keinen Blitz")
        self.aufrufe.append(("blitz", modus.value))

    async def initialize(self, _beschreibung, preset, **_kw) -> None:
        self.aufrufe.append(("öffnen", preset.value))

    async def take_picture(self) -> bytes:
        self.aufrufe.append(("foto",))
        return JPEG


def _mit_kamera(page, welt, art: str, **kw) -> _Aufnahme:
    page.platform = ft.PagePlatform.ANDROID
    a = _Aufnahme(page, welt.state, welt.eintrag, art)
    a.kamera = _Kamera(**kw)
    a.kameras = [SimpleNamespace(lens_direction=SimpleNamespace(value="back"))]
    a.bereit = True
    a.zeichnen()
    return a


async def test_blitz_timer_und_qualitaet_oben_im_bild(welt, page) -> None:
    """P73 (Ben, 21.10.2026, Skizze H1): oben im Bild Blitz, Timer und die Qualität dieser
    Aufnahme — die Vorgabe in den Einstellungen bleibt."""
    pytest.importorskip("flet_camera")
    from trainingsapp.data.anhaenge import qualitaet_lesen

    a = _mit_kamera(page, welt, BILD)
    assert _texte(a.leiste) == ["Aus", "Aus", "Mittel · 720p"]
    await a.blitz_tippen()
    assert a.blitz == "auto" and a.kamera.aufrufe[-1] == ("blitz", "auto")
    a.timer_tippen()
    a.timer_tippen()
    assert a.timer_s == 3 and a.status.value == "Mittel · 720p · Rückkamera · Timer 3 s"

    menue = next(c for c in a.leiste.controls if isinstance(c, ft.PopupMenuButton))
    await next(i for i in menue.items if i.content == "Groß · 1080p").on_click()
    assert a.qualitaet is Qualitaet.GROSS and ("öffnen", "veryHigh") in a.kamera.aufrufe
    assert a.kamera.aufrufe[-1] == ("blitz", "auto")  # der neue Controller bekommt den Blitz
    assert a.bereit and "Groß · 1080p" in _texte(a.leiste)
    assert qualitaet_lesen(welt.state.einstellungen) is Qualitaet.MITTEL

    video = _mit_kamera(page, welt, VIDEO, blitz=False)  # Frontkamera: meist ohne Blitz
    assert _texte(video.leiste)[0] == "Licht aus"
    await video.blitz_tippen()
    assert video.blitz == "off" and video.status.value.endswith("ohne Blitz")


async def test_selbstausloeser_zaehlt_mit_ton_und_bricht_ab(welt, page, monkeypatch) -> None:
    """Skizze H2: Mit Timer zählt die Mitte groß herunter, je Sekunde ein Ton; „Abbrechen“
    hält an, ohne aufzunehmen."""
    pytest.importorskip("flet_camera")
    import asyncio

    from trainingsapp.ui.views import anhang_aufnahme as modul

    toene: list[str] = []

    async def ton(_state, klang, _signale=None) -> bool:
        toene.append(klang)
        return True

    monkeypatch.setattr(modul, "ton_spielen", ton)
    monkeypatch.setattr(modul, "COUNTDOWN_TAKT_S", 0)
    aufgaben: list[asyncio.Task] = []

    def run_task(f, *args):
        aufgaben.append(asyncio.ensure_future(f(*args)))
        return aufgaben[-1]

    page.run_task = run_task
    a = _mit_kamera(page, welt, BILD)
    a.timer_s = 3
    await a.ausloesen()
    assert a.countdown_rest == 3 and _knoepfe(a.knoepfe) == ["Abbrechen"]
    a.abbrechen()
    await asyncio.gather(*aufgaben, return_exceptions=True)
    assert a.countdown_rest is None and a.gross.value == "" and a.daten is None
    assert ("foto",) not in a.kamera.aufrufe

    await a.ausloesen()
    await asyncio.gather(*aufgaben[1:])
    assert toene == ["countdown"] * 3
    assert a.kamera.aufrufe[-1] == ("foto",) and a.daten == JPEG and a.gross.value == ""


async def test_ein_blitzfehler_sperrt_die_kamera_nicht(welt, page) -> None:
    """flet-camera trägt einen Fehler in jedem weiteren Zustand mit. „Blitz aus“ an einer
    Kamera ohne Lampe („torchModeNotSupported“, im Browser schon beim Öffnen) sperrte so den
    Auslöser, und „Verwerfen“ verließ die Seite (21.10.2026)."""
    pytest.importorskip("flet_camera")
    a = _mit_kamera(page, welt, BILD)
    fehler = SimpleNamespace(
        has_error=True,
        error_description="Error code: torchModeNotSupported",
        is_initialized=True,
    )
    for _ in range(3):  # jeder weitere Zustand trägt ihn mit
        a._zustand(fehler)
    assert a.bereit and "torch" not in a.status.value
    a.daten = JPEG
    a.ergebnis_zeigen()
    await a.verwerfen()
    assert a.bereit and a.daten is None and not page.routen  # zurück zur Kamera
    # Ein anderer Fehler steht im Text — einmal; die geöffnete Kamera bleibt bereit
    a._zustand(SimpleNamespace(has_error=True, error_description="Kaputt", is_initialized=True))
    assert a.bereit and a.status.value == "Kamera: Kaputt"
    a.status.value = ""
    a._zustand(SimpleNamespace(has_error=True, error_description="Kaputt", is_initialized=True))
    assert a.status.value == ""
    # Ist sie nicht (mehr) geöffnet, ist sie es nicht
    a._zustand(SimpleNamespace(has_error=True, error_description="weg", is_initialized=False))
    assert not a.bereit


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
    # Nur der Name der Stufe — die Auflösung kann eine frühere gewesen sein
    assert any("Mittel" in t for t in _texte(foto))
    assert not any("1080p" in t or "720p" in t for t in _texte(foto))
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


async def test_behalten_schreibt_zeile_im_loop(welt, page) -> None:
    """Die Bytes gehen in einen Thread, die Zeile nicht: Die SQLite-Verbindung gehört dem
    Event-Loop — ein INSERT aus dem Thread warf am Handy „SQLite objects created in a thread
    can only be used in that same thread“ (21.10.2026)."""
    a = _Aufnahme(page, welt.state, welt.eintrag, BILD)
    a.daten = JPEG
    a.notiz.value = "rechts"
    await a.behalten()
    neu = [x for x in welt.state.anhaenge.je_eintrag(welt.eintrag.id) if x.note == "rechts"]
    assert len(neu) == 1 and neu[0].bytes == len(JPEG)
    assert welt.state.anhaenge.vorhanden(neu[0])
    assert a.daten is None and page.routen == ["/"]
