"""Fotos und Videos an Einträgen in der Oberfläche (Ben, 19.10.2026) — Leistungen-Blatt,
Tagebuch, Übung, Einstellungen, Ansicht und Aufnahmeseite (am Rechner: „Datei wählen“)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from trainingsapp.core.anhaenge import (  # noqa: E402
    AUDIO,
    BILD,
    VIDEO,
    Qualitaet,
    Ziel,
    neuer_anhang,
)
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
M4A = b"\x00\x00\x00\x1cftypM4A " + b"0" * 800


def _ziel(welt) -> Ziel:
    return Ziel.fuer_eintrag(welt.eintrag.id)


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


@pytest.mark.parametrize("darstellung", ["uebersicht", "zeitleiste"])
async def test_heute_zeigt_frontbilder_unter_der_uebung(welt, page, darstellung) -> None:
    """Ben, 22.10.2026: „Photos erzeugen in Verlauf eine Miniaturansicht. In Heute aber
    nicht“ — jetzt in beiden Darstellungen, ein Tipp öffnet die Ansicht."""
    from trainingsapp.ui.views.tag import tagesansicht

    welt.state.tag_darstellung = darstellung
    ansicht = tagesansicht(page, welt.state, welt.state.heute())
    bilder = [c for c in _alle(ansicht) if isinstance(c, ft.Image)]
    assert len(bilder) == 2  # Foto und Frontbild des Videos
    assert not any("Aufnahme" in t for t in _texte(ansicht))  # keine Büroklammer mit Zahl
    kacheln = [
        c
        for c in _alle(ansicht)
        if isinstance(c, ft.Container) and c.width == 64 and c.on_click is not None
    ]
    await kacheln[0].on_click()
    assert page.routen == [f"/anhang/{welt.foto.id}"]


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
    a = _Aufnahme(page, welt.state, _ziel(welt), BILD)
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
    a = _Aufnahme(page, welt.state, _ziel(welt), art)
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
        page, welt.state, f"/anhang/aufnehmen/{welt.eintrag.id}/foto", _ziel(welt), BILD
    )
    assert "Datei wählen" in _knoepfe(ansicht)
    assert any("Nackendehnung" in t or "Foto:" in t for t in _texte(ansicht))


async def test_behalten_schreibt_zeile_im_loop(welt, page) -> None:
    """Die Bytes gehen in einen Thread, die Zeile nicht: Die SQLite-Verbindung gehört dem
    Event-Loop — ein INSERT aus dem Thread warf am Handy „SQLite objects created in a thread
    can only be used in that same thread“ (21.10.2026)."""
    a = _Aufnahme(page, welt.state, _ziel(welt), BILD)
    a.daten = JPEG
    a.notiz.value = "rechts"
    await a.behalten()
    neu = [x for x in welt.state.anhaenge.je_eintrag(welt.eintrag.id) if x.note == "rechts"]
    assert len(neu) == 1 and neu[0].bytes == len(JPEG)
    assert welt.state.anhaenge.vorhanden(neu[0])
    assert a.daten is None and page.routen == ["/"]


# -- Hochladen aus der Fotoauswahl (P74, Skizzen I1/I2) -----------------------------------

#: Ein JPEG mit Ortsangabe im Exif — so käme es aus der Galerie
JPEG_MIT_ORT = b"\xff\xd8\xff\xe1\x00\x0eExif\x00\x00GPS!!!\xff\xda\x00\x02DATEN\xff\xd9"


def _box(typ: bytes, inhalt: bytes = b"") -> bytes:
    return (8 + len(inhalt)).to_bytes(4, "big") + typ + inhalt


#: Ein MP4 mit ``©xyz`` (Ort) im ``moov``
MP4_MIT_ORT = (
    _box(b"ftyp", b"mp42")
    + _box(b"moov", _box(b"udta", _box(b"\xa9xyz", b"+48.13+011.57/")))
    + _box(b"mdat", b"BILDER")
)


class _Dienst:
    """Was die Seite von flet_hochladen braucht. Die Auswahl ist eine Datei im „Cache“; das
    Verkleinern kopiert sie nur — samt Ort, damit das Netz der App geprüft wird."""

    def __init__(self, cache, name: str, daten: bytes, dauer_ms: int | None = None) -> None:
        cache.mkdir(parents=True, exist_ok=True)
        self.quelle = cache / name
        self.quelle.write_bytes(daten)
        self.name, self.dauer = name, dauer_ms
        self.aufrufe: list[dict] = []

    async def waehlen(self):
        return {"pfad": str(self.quelle), "name": self.name, "mime": None, "bytes": 312_000_000}

    async def dauer_ms(self, _pfad):
        return self.dauer

    async def verkleinern(self, quelle, art, ziel, **kw):
        from pathlib import Path

        self.aufrufe.append({"art": art, **kw})
        Path(ziel).write_bytes(Path(quelle).read_bytes())
        if kw["frontbild"]:
            Path(kw["frontbild"]).write_bytes(JPEG_MIT_ORT)
        return {"bytes": 1, "breite": 1280, "hoehe": 720, "dauer_ms": self.dauer}

    async def abbrechen(self):
        return None


async def test_hochladen_foto_ohne_ort(welt, page, tmp_path) -> None:
    """P74: Die Seite öffnet die Fotoauswahl, verkleinert auf die Vorgabe, nimmt den Ort
    heraus (auch wenn die Erweiterung ihn durchließe) und löscht die Kopie der Auswahl."""
    from trainingsapp.ui.views.anhang_hochladen import _Hochladen

    dienst = _Dienst(tmp_path / "cache", "IMG_1.jpg", JPEG_MIT_ORT)
    welt.state.hochladen = dienst
    h = _Hochladen(page, welt.state, _ziel(welt))
    await h.starten()
    assert h.fertig and not dienst.quelle.exists()  # die Kopie mit Ort ist weg
    assert dienst.aufrufe == [
        {
            "art": "bild",
            "frontbild": None,
            "kurze_seite": 720,
            "jpeg_qualitaet": 85,
            "video_bitrate": 800_000,
            "audio_bitrate": 64_000,
        }
    ]
    assert h.ziel is not None and b"GPS" not in h.ziel.read_bytes()
    assert h.ort.visible and h.status.value.startswith("312,0 MB → ")
    assert _knoepfe(h.knoepfe) == ["Verwerfen", "Behalten"]

    h.notiz.value = "von links"
    await h.behalten()
    (neu,) = [a for a in welt.state.anhaenge.je_eintrag(welt.eintrag.id) if a.note == "von links"]
    assert neu.art == BILD and welt.state.anhaenge.vorhanden(neu)
    assert b"GPS" not in welt.state.anhaenge.datei(neu).read_bytes()
    assert not list(welt.state.anhaenge.hochladen_ordner().iterdir())
    assert page.routen == ["/"]


async def test_hochladen_video_ohne_ort_und_hoechstens_zehn_minuten(welt, page, tmp_path) -> None:
    from trainingsapp.ui.views.anhang_hochladen import _Hochladen

    lang = _Dienst(tmp_path / "cache", "lang.mp4", MP4_MIT_ORT, dauer_ms=11 * 60_000)
    welt.state.hochladen = lang
    h = _Hochladen(page, welt.state, _ziel(welt))
    await h.starten()
    assert not h.fertig and "höchstens 10:00" in h.status.value
    assert not lang.aufrufe and not lang.quelle.exists()
    assert _knoepfe(h.knoepfe) == ["Zurück"]

    kurz = _Dienst(tmp_path / "cache", "kurz.mp4", MP4_MIT_ORT, dauer_ms=9_000)
    welt.state.hochladen = kurz
    h = _Hochladen(page, welt.state, _ziel(welt))
    await h.starten()
    assert h.fertig and kurz.aufrufe[0]["art"] == "video" and kurz.aufrufe[0]["frontbild"]
    assert h.ziel is not None and b"\xa9xyz" not in h.ziel.read_bytes()
    assert h.frontbild is not None and b"GPS" not in h.frontbild.read_bytes()
    assert h.titel.value == "Video · 0:09 · aus der Fotoauswahl"
    await h.behalten()
    (video,) = [a for a in welt.state.anhaenge.je_eintrag(welt.eintrag.id) if a.breite == 1280]
    assert video.art == VIDEO and video.hoehe == 720 and video.dauer_s == 9.0
    assert welt.state.anhaenge.bild(video).is_file()


async def test_hochladen_verwerfen_und_ohne_erweiterung(welt, page, tmp_path) -> None:
    from trainingsapp.ui.views.anhang_hochladen import _Hochladen

    welt.state.hochladen = _Dienst(tmp_path / "cache", "IMG_2.jpg", JPEG_MIT_ORT)
    h = _Hochladen(page, welt.state, _ziel(welt))
    await h.starten()
    ziel = h.ziel
    await h.verwerfen()
    assert ziel is not None and not ziel.exists() and page.routen == ["/"]
    vorher = len(welt.state.anhaenge.je_eintrag(welt.eintrag.id))

    welt.state.hochladen = None  # am Rechner: keine Erweiterung
    h = _Hochladen(page, welt.state, _ziel(welt))
    await h.starten()
    assert "nur in der App am Handy" in h.status.value
    assert len(welt.state.anhaenge.je_eintrag(welt.eintrag.id)) == vorher


def test_leistungen_zeigen_hochladen_nur_mit_erweiterung(welt, page, tmp_path) -> None:
    """Skizze I1: ein dritter Knopf neben Foto und Video — nur, wo die Erweiterung da ist."""
    route = f"/tag/{welt.state.heute()}/leistungen/{welt.uebung.id}"
    assert "Hochladen" not in _knoepfe(leistungen_view(page, welt.state, route, welt.uebung))
    welt.state.hochladen = _Dienst(tmp_path / "cache", "x.jpg", JPEG)
    ansicht = leistungen_view(page, welt.state, route, welt.uebung)
    assert {"Foto", "Video", "Hochladen"} <= set(_knoepfe(ansicht))
    klammer = next(c for c in _alle(ansicht) if isinstance(c, ft.PopupMenuButton))
    assert [i.content.value for i in klammer.items][-1] == "Aus der Fotoauswahl"
    assert not _umbrechend_mit_ausdehnung(ansicht)


# -- Audioaufnahmen und Anhänge am Tag (Ben, 22.10.2026) ----------------------------------


class _Rekorder:
    """Was die Aufnahmeseite von flet-audio-recorder braucht — schreibt beim Stopp ein „M4A“
    in die Datei, die die Seite vorgelegt hat."""

    def __init__(self, erlaubt: bool = True, aac: bool = True) -> None:
        self.erlaubt, self.aac = erlaubt, aac
        self.pfad: str | None = None
        self.konfiguration = None
        self.abgebrochen = False
        self.aufrufe: list[str] = []

    async def has_permission(self) -> bool:
        return self.erlaubt

    async def is_supported_encoder(self, _encoder) -> bool:
        return self.aac

    async def start_recording(self, output_path=None, configuration=None) -> bool:
        from pathlib import Path

        assert Path(output_path).is_file()  # vorgelegt — sonst nähme Flet den Assets-Ordner
        self.pfad, self.konfiguration = output_path, configuration
        return True

    async def pause_recording(self) -> None:
        self.aufrufe.append("pause")

    async def resume_recording(self) -> None:
        self.aufrufe.append("weiter")

    async def stop_recording(self) -> str | None:
        from pathlib import Path

        Path(self.pfad).write_bytes(M4A)
        return self.pfad

    async def cancel_recording(self) -> None:
        from pathlib import Path

        self.abgebrochen = True
        Path(self.pfad).unlink(missing_ok=True)


async def test_audio_aufnehmen_anhalten_und_am_tag_behalten(welt, page) -> None:
    """● nimmt einkanalig mit der Tonrate der Stufe in ``.aufnahme/`` auf, ⏸/▶ hält an und
    macht weiter, ⏹ legt die Aufnahme zum Anhören bereit, „Behalten“ hängt sie an den Tag."""
    from trainingsapp.ui.views.anhang_ton import _Ton

    heute = welt.state.heute()
    t = _Ton(page, welt.state, Ziel.fuer_tag(welt.state.profil.id, heute))
    t.rekorder = _Rekorder()
    await t.starten()
    assert t.laeuft and t.datei is not None and t.datei.parent.name == ".aufnahme"
    assert t.rekorder.konfiguration.channels == 1
    assert t.rekorder.konfiguration.bit_rate == Qualitaet.MITTEL.audio_bitrate
    await t.pause_umschalten()
    assert t.pausiert and "Angehalten" in t.status.value
    await t.pause_umschalten()
    assert t.rekorder.aufrufe == ["pause", "weiter"] and not t.pausiert
    await t.stoppen()
    assert t.fertig and t.spieler is not None and _knoepfe(t.knoepfe) == ["Verwerfen", "Behalten"]
    assert any(isinstance(c, ft.Slider) for c in _alle(t.flaeche))  # Anhören vor dem Behalten
    t.notiz.value = "nach dem Laufen"
    await t.behalten()
    am_tag = welt.state.anhaenge.zum_tag(welt.state.profil.id, heute)
    assert [(a.art, a.note, a.eintrag_id) for a in am_tag] == [(AUDIO, "nach dem Laufen", None)]
    assert am_tag[0].pfad.endswith(".m4a") and welt.state.anhaenge.vorhanden(am_tag[0])
    assert not list(welt.state.anhaenge.aufnahme_ordner().iterdir())
    assert page.routen == ["/"]


async def test_audio_verwerfen_verlassen_und_ohne_berechtigung(welt, page) -> None:
    """Verwerfen löscht und ist gleich wieder bereit; wer die Seite verlässt, bricht eine
    laufende Aufnahme ab und lässt keine Datei liegen; ohne Mikrofon kein Start."""
    from trainingsapp.ui.views.anhang_ton import _Ton

    vorher = len(welt.state.anhaenge.je_eintrag(welt.eintrag.id))
    t = _Ton(page, welt.state, _ziel(welt))
    t.rekorder = _Rekorder()
    await t.starten()
    await t.stoppen()
    datei = t.datei
    await t.verwerfen()
    assert not t.fertig and datei is not None and not datei.exists()
    assert _knoepfe(t.knoepfe) == [] and t.zeit.value == "0:00"  # nur das große ●
    await t.starten()
    laufend = t.datei
    await t.zurueck()
    assert t.rekorder.abgebrochen and laufend is not None and not laufend.exists()
    assert len(welt.state.anhaenge.je_eintrag(welt.eintrag.id)) == vorher

    ohne = _Ton(page, welt.state, _ziel(welt))
    ohne.rekorder = _Rekorder(erlaubt=False)
    await ohne.starten()
    assert "Mikrofon-Berechtigung" in ohne.status.value and not ohne.laeuft
    assert ohne.datei is None
    page.web = True
    im_browser = _Ton(page, welt.state, _ziel(welt))
    await im_browser.starten()
    assert "Browser" in im_browser.status.value


async def test_audio_ohne_aac_wird_wav(welt, page) -> None:
    """Am Rechner kennt der Rekorder manchmal kein AAC — dann WAV, und Aufräumen kennt es."""
    from trainingsapp.core.anhaenge import verwaiste
    from trainingsapp.ui.views.anhang_ton import _Ton

    t = _Ton(page, welt.state, _ziel(welt))
    t.rekorder = _Rekorder(aac=False)
    await t.starten()
    assert t.datei is not None and t.datei.suffix == ".wav"
    await t.stoppen()
    await t.behalten()
    neu = [a for a in welt.state.anhaenge.je_eintrag(welt.eintrag.id) if a.ist_audio]
    assert len(neu) == 1 and neu[0].pfad.endswith(".wav") and neu[0].mime == "audio/wav"
    repo = welt.state.anhaenge
    assert verwaiste(repo.dateien(), repo.alle_zeilen()) == []


def test_audioseite_und_ansicht(welt, page) -> None:
    """Die Seite zeigt das große ● und den Tag im Titel; die Ansicht einer Audioaufnahme
    spielt mit Knopf und Regler und blättert durch die Anhänge desselben Tags."""
    from trainingsapp.ui.views.anhang_ton import anhang_ton_view

    heute = welt.state.heute()
    ziel = Ziel.fuer_tag(welt.state.profil.id, heute)
    seite = anhang_ton_view(page, welt.state, f"/anhang/aufnehmen/tag/{heute}/audio", ziel)
    assert seite.can_pop is False and seite.on_confirm_pop is not None
    texte = _texte(seite)
    assert f"Audio: Zum Tag · {heute:%d.%m.}" in texte
    assert any(
        isinstance(c, ft.IconButton) and c.icon == ft.Icons.FIBER_MANUAL_RECORD
        for c in _alle(seite)
    )

    ton = neuer_anhang(ziel, AUDIO, Qualitaet.MITTEL, dauer_s=65.0)
    welt.state.anhaenge.anlegen(ton, M4A)
    foto = neuer_anhang(ziel, BILD, Qualitaet.MITTEL)
    welt.state.anhaenge.anlegen(foto, JPEG)
    ansicht = anhang_view(page, welt.state, "/", ton)
    texte = _texte(ansicht)
    assert f"Zum Tag · {heute:%d.%m.}" in texte and any("1:05" in t for t in texte)
    assert any(isinstance(c, ft.Slider) for c in _alle(ansicht))
    assert not any(isinstance(c, ft.InteractiveViewer) for c in _alle(ansicht))
    assert [a.id for a in reihe_fuer(welt.state, "/", ton)] == [ton.id, foto.id]


def test_audio_in_leistungen_tagebuch_und_einstellungen(welt, page) -> None:
    """Der Knopf „Audio“ und „Audio aufnehmen“ an der Büroklammer; im Tagebuch eine Karte
    „Aufnahmen · Zum Tag“; die Kachel einer Audioaufnahme zeigt Klangsymbol und Dauer."""
    route = f"/tag/{welt.state.heute()}/leistungen/{welt.uebung.id}"
    ansicht = leistungen_view(page, welt.state, route, welt.uebung)
    assert {"Foto", "Video", "Audio"} <= set(_knoepfe(ansicht))
    klammer = next(c for c in _alle(ansicht) if isinstance(c, ft.PopupMenuButton))
    assert "Audio aufnehmen" in [i.content.value for i in klammer.items]

    heute = welt.state.heute()
    ton = neuer_anhang(Ziel.fuer_tag(welt.state.profil.id, heute), AUDIO, Qualitaet.MITTEL)
    ton.dauer_s = 12.0
    welt.state.anhaenge.anlegen(ton, M4A)
    kontrolle = tagebuch(page, welt.state)
    texte = _texte(kontrolle)
    assert "Aufnahmen · Zum Tag" in texte and "1 Audioaufnahme" in " ".join(texte)
    assert any(isinstance(c, ft.Icon) and c.icon == ft.Icons.GRAPHIC_EQ for c in _alle(kontrolle))
    assert any("0:12" in t for t in texte)
    einstellungen = _texte(einstellungen_anhaenge(page, welt.state))
    assert any("1 Foto, 1 Video, 1 Audioaufnahme" in t for t in einstellungen)
