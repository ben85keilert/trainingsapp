"""Der Videospieler mit Knöpfen unter dem Bild (Ben, 18.11.2026: „Behalte die
Videosteuerelemente an, solange kein Play ist“; 20.11.2026: Zeitleiste, Lautstärke, Schleife,
✕, Ausrichtung im Vollbild) — `ui/components/videospieler.py`."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
fv = pytest.importorskip("flet_video")

from mp4_bau import mp4, spur  # noqa: E402
from trainingsapp.ui import ausrichtung  # noqa: E402
from trainingsapp.ui.components import videospieler  # noqa: E402
from trainingsapp.ui.components.videospieler import Videospieler  # noqa: E402


def _alle(c):
    if c is None:
        return
    yield c
    for name in ("controls", "content"):
        kind = getattr(c, name, None)
        for k in kind if isinstance(kind, list) else [kind]:
            if isinstance(k, ft.Control):
                yield from _alle(k)


def _knoepfe(spieler: Videospieler) -> dict[str, ft.IconButton]:
    return {k.data: k for k in _alle(spieler.control) if isinstance(k, ft.IconButton)}


@pytest.fixture(autouse=True)
def _laut_zurueck():
    yield
    videospieler._lautstaerke[0] = 100.0


def _seite(platform=ft.PagePlatform.ANDROID, route="/plan/p1"):
    gesetzt: list[list[ft.DeviceOrientation]] = []
    aufgaben: list = []

    async def set_allowed_device_orientations(liste):
        gesetzt.append(list(liste))

    return SimpleNamespace(
        platform=platform,
        route=route,
        gesetzt=gesetzt,
        aufgaben=aufgaben,
        set_allowed_device_orientations=set_allowed_device_orientations,
        run_task=lambda f, *a: aufgaben.append(f(*a)),
    )


async def _laufen(seite) -> None:
    for aufgabe in seite.aufgaben:
        await aufgabe
    seite.aufgaben.clear()


def test_knoepfe_stehen_unter_dem_bild_und_das_bild_spielt_auf_tipp() -> None:
    s = Videospieler(["/a.mp4"])
    video = s.video
    assert video.autoplay is False and s.spielt is False
    # Unter dem Bild, nicht darüber: Zeitleiste, Knöpfe, (zugeklappt) Lautstärke
    _bild, zeile = s.control.content.controls
    assert [z.data for z in zeile.content.controls] == ["video_zeit", "video_knoepfe", "video_laut"]
    assert [k.data for k in s.knopf_zeile.controls if isinstance(k, ft.IconButton)] == [
        "video_zurueck",
        "video_spielen",
        "video_vor",
        "video_schleife",
        "video_lautstaerke",
        "video_vollbild",
    ]
    # Sechs Knöpfe passen in die 320 px des Fokus
    assert sum(k.width for k in s.knopf_zeile.controls if isinstance(k, ft.IconButton)) <= 320 - 16
    assert "video_schliessen" not in _knoepfe(s)  # ein ✕ nur, wo es jemand haben will
    # Über dem Bild nur eine durchsichtige Fläche für den Tipp; im Vollbild die von media_kit,
    # sichtbar beim Öffnen, Lautstärke durch Wischen
    auf_dem_bild = video.controls[fv.VideoControlsMode.NORMAL]
    assert isinstance(auf_dem_bild, ft.Container) and auf_dem_bild.on_click is not None
    assert auf_dem_bild.bgcolor == ft.Colors.TRANSPARENT  # sonst ginge der Tipp durch
    voll = video.controls[fv.VideoControlsMode.FULLSCREEN]
    assert isinstance(voll, fv.MaterialVideoControls) and voll.visible_on_mount is True
    assert voll.volume_gesture is True
    # Nie ein Ereignis je Bild nach Python (`.claude/rules/uhr_timer.md`)
    assert video.on_position_change is None


async def test_spielen_anhalten_und_ende() -> None:
    gemeldet: list[bool] = []
    s = Videospieler(["/a.mp4"], autoplay=True, hoehe=180, breite=320, beim_spielen=gemeldet.append)
    knopf = _knoepfe(s)["video_spielen"]
    assert s.spielt and knopf.icon == ft.Icons.PAUSE
    assert s.control.width == 320 and s.control.content.controls[0].height == 180
    await knopf.on_click(None)  # ohne Seite wirft pause() — die Anzeige stimmt trotzdem
    assert not s.spielt and knopf.icon == ft.Icons.PLAY_ARROW and gemeldet == [False]
    await s.video.controls[fv.VideoControlsMode.NORMAL].on_click(None)  # Tipp aufs Bild
    assert s.spielt and gemeldet == [False, True]
    # „completed = False“ meldet der Spieler beim Neubeginn — das ist kein Ende
    await s._zu_ende(SimpleNamespace(data=False))
    assert s.spielt
    await s._zu_ende(SimpleNamespace(data=True))
    assert not s.spielt and knopf.icon == ft.Icons.PLAY_ARROW and s._am_ende
    # ▶ nach dem Ende beginnt von vorn
    gesprungen: list = []

    async def seek(position):
        gesprungen.append(position.in_milliseconds)

    async def play():
        gesprungen.append("play")

    s.video.seek, s.video.play = seek, play
    await s.spielen()
    assert gesprungen == [0, "play"] and not s._am_ende
    # In der Schleife ist kein Ende
    schleife = Videospieler(["/a.mp4"], autoplay=True, schleife=True)
    await schleife._zu_ende(SimpleNamespace(data=True))
    assert schleife.spielt and schleife.video.playlist_mode == fv.PlaylistMode.LOOP


async def test_mehrere_dateien_das_ende_der_ersten_ist_kein_ende() -> None:
    s = Videospieler(["/a.mp4", "/b.mp4"], autoplay=True)

    async def laeuft() -> bool:
        return True

    s.video.is_playing = laeuft
    await s._zu_ende(SimpleNamespace(data=True))
    assert s.spielt  # das zweite läuft schon — ▶ stünde sonst falsch da

    async def steht() -> bool:
        return False

    s.video.is_playing = steht
    await s._zu_ende(SimpleNamespace(data=True))
    assert not s.spielt


def test_schleife_knopf_stellt_um_und_meldet() -> None:
    gestellt: list[bool] = []
    s = Videospieler(["/a.mp4"], bei_schleife=gestellt.append)
    knopf = _knoepfe(s)["video_schleife"]
    assert s.video.playlist_mode is None and knopf.icon == ft.Icons.REPEAT
    knopf.on_click(None)
    assert s.schleife and s.video.playlist_mode == fv.PlaylistMode.LOOP
    assert knopf.icon == ft.Icons.REPEAT_ON and "an" in knopf.tooltip
    knopf.on_click(None)
    # ausdrücklich „none“ — ``None`` ließe den Spieler in der Schleife (`video.dart` übergeht es)
    assert not s.schleife and s.video.playlist_mode == fv.PlaylistMode.NONE
    assert gestellt == [True, False]


def test_lautstaerke_zeile_stumm_und_gilt_fuer_den_naechsten() -> None:
    s = Videospieler(["/a.mp4"])
    knoepfe = _knoepfe(s)
    assert s.laut_zeile.visible is False and s.video.volume == 100
    knoepfe["video_lautstaerke"].on_click(None)
    assert s.laut_zeile.visible is True
    s.laut_leiste.value = 30
    s.laut_leiste.on_change(None)
    assert s.video.volume == 30 and knoepfe["video_lautstaerke"].icon == ft.Icons.VOLUME_DOWN
    knoepfe["video_stumm"].on_click(None)
    assert s.video.volume == 0 and knoepfe["video_lautstaerke"].icon == ft.Icons.VOLUME_OFF
    knoepfe["video_stumm"].on_click(None)
    assert s.video.volume == 30
    # Das nächste Video beginnt nicht wieder laut
    assert Videospieler(["/b.mp4"]).video.volume == 30


async def test_zeitleiste_dauer_aus_dem_kopf_ziehen_springt_beim_loslassen(tmp_path) -> None:
    datei = tmp_path / "a.mp4"
    datei.write_bytes(
        mp4(spur(b"vide", breite=1920, hoehe=1080, dauer_s=90.0, bilder=90), dauer_s=90.0)
    )
    s = Videospieler([str(datei)])
    assert s.dauer_text.value == "1:30" and s.leiste.max == 90 and s.stand_text.value == "0:00"
    gesprungen: list[int] = []

    async def seek(position):
        gesprungen.append(position.in_milliseconds)

    s.video.seek = seek
    s.leiste.on_change_start(None)
    s.leiste.value = 42.0
    s.leiste.on_change(None)
    assert s.stand_text.value == "0:42" and gesprungen == []  # beim Ziehen nur die Zahl
    await s.leiste.on_change_end(None)
    assert gesprungen == [42_000] and not s._zieht

    # ⟳ 10 s vom Stand des Spielers, nie über das Ende hinaus
    async def stand():
        return ft.Duration(seconds=85)

    s.video.get_current_position = stand
    await _knoepfe(s)["video_vor"].on_click(None)
    assert gesprungen[-1] == 90_000 and s.stand_text.value == "1:30"
    # Der Takt fragt nach: Stand vom Spieler in die Leiste
    await s._stand_holen()
    assert s.leiste.value == 85 and s.stand_text.value == "1:25"
    # Ohne lesbaren Kopf: Dauer erst vom Spieler
    ohne = Videospieler(["/gibt-es-nicht.mp4"])
    assert ohne.dauer_text.value == "–:––" and ohne.hochkant is None

    async def dauer():
        return ft.Duration(seconds=75)

    ohne.video.get_current_position, ohne.video.get_duration = stand, dauer
    await ohne._stand_holen()
    assert ohne.dauer_text.value == "1:15" and ohne.leiste.max == 75


async def test_vollbild_richtet_sich_nach_dem_video(tmp_path, monkeypatch) -> None:
    """Ben, 20.11.2026: „Ein hochkant aufgenommenes Handy-Video wird im Vollbild gedreht“ —
    media_kit stellt immer quer und gibt danach alles frei."""
    hoch = tmp_path / "hoch.mp4"  # quer gespeichert, im Kopf gedreht: so filmt ein Telefon
    hoch.write_bytes(mp4(spur(b"vide", breite=1920, hoehe=1080, bilder=90, gedreht=True)))
    quer = tmp_path / "quer.mp4"
    quer.write_bytes(mp4(spur(b"vide", breite=1920, hoehe=1080, bilder=90)))
    seite = _seite()
    monkeypatch.setattr(Videospieler, "_seite", lambda self: seite)
    D = ft.DeviceOrientation

    s = Videospieler([str(hoch)])
    assert s.hochkant is True
    _knoepfe(s)["video_vollbild"].on_click(None)
    assert s.video.fullscreen is True
    s.video.on_enter_fullscreen(None)
    await _laufen(seite)
    assert seite.gesetzt == [[D.PORTRAIT_UP]]
    # Danach wieder die Ausrichtung der Ansicht (ein Plan: hochkant), nicht „alles frei“
    await s.video.on_exit_fullscreen(None)
    await _laufen(seite)
    assert seite.gesetzt[-1] == [D.PORTRAIT_UP]

    s = Videospieler([str(quer)])
    s.video.on_enter_fullscreen(None)
    await _laufen(seite)
    assert seite.gesetzt[-1] == [D.LANDSCAPE_LEFT, D.LANDSCAPE_RIGHT]
    # Format unbekannt: frei drehbar
    s = Videospieler(["/gibt-es-nicht.mp4"])
    s.video.on_enter_fullscreen(None)
    await _laufen(seite)
    assert len(seite.gesetzt[-1]) == 3
    # In einer Ansicht, die drehen darf (Anhang), danach wieder frei
    seite.route = "/tag/2026-11-20/anhang/a1"
    await s.video.on_exit_fullscreen(None)
    await _laufen(seite)
    assert len(seite.gesetzt[-1]) == 3
    # Am Rechner gibt es nichts zu stellen
    rechner = _seite(platform=ft.PagePlatform.LINUX)
    ausrichtung.fuer_video(rechner, True)
    ausrichtung.nach_video(rechner)
    assert rechner.aufgaben == []


async def test_nach_dem_vollbild_gilt_der_stand_des_spielers(monkeypatch) -> None:
    gemeldet: list[bool] = []
    s = Videospieler(["/a.mp4"], autoplay=True, beim_spielen=gemeldet.append)
    monkeypatch.setattr(Videospieler, "_seite", lambda self: None)

    async def steht() -> bool:
        return False

    s.video.is_playing = steht
    await s.video.on_exit_fullscreen(None)
    # Im Vollbild angehalten = von Hand angehalten (der Fokus startet es dann nicht wieder)
    assert not s.spielt and gemeldet == [False]


async def test_bildschirm_bleibt_ueber_wach_an_nicht_ueber_media_kit(monkeypatch) -> None:
    """media_kit nähme dem Timer den wachen Bildschirm weg, sobald ein Video anhält."""
    assert Videospieler(["/a.mp4"]).video.wakelock is True  # ohne state: wie bisher

    class Dienst:
        an = False

        async def enable(self):
            self.an = True

        async def disable(self):
            self.an = False

    state = SimpleNamespace(wach=Dienst(), wach_gruende={"timer"})
    seite = _seite()
    monkeypatch.setattr(Videospieler, "_seite", lambda self: seite)
    monkeypatch.setattr(Videospieler, "_takt_starten", lambda self: None)
    s = Videospieler(["/a.mp4"], autoplay=True, state=state)
    assert s.video.wakelock is False
    s.control.did_mount()
    await _laufen(seite)
    assert state.wach_gruende == {"timer", "video"} and state.wach.an
    await s.anhalten()
    await _laufen(seite)
    assert state.wach_gruende == {"timer"} and state.wach.an  # der Timer hält weiter
    await s.spielen()
    s.control.will_unmount()
    await _laufen(seite)
    assert state.wach_gruende == {"timer"}


def test_schliessen_knopf_im_bild() -> None:
    weg: list[int] = []
    s = Videospieler(["/a.mp4"], hoehe=180, breite=320, beim_schliessen=lambda: weg.append(1))
    _knoepfe(s)["video_schliessen"].on_click(None)
    assert weg == [1]


def test_vollbild_und_neu_beginnen() -> None:
    s = Videospieler(["/a.mp4", "/b.mp4"])
    assert [m.resource for m in s.video.playlist] == ["/a.mp4", "/b.mp4"]
    _knoepfe(s)["video_vollbild"].on_click(None)
    assert s.video.fullscreen is True
    s.neu_beginnen(True)
    assert s.video.autoplay is True and s.spielt
    s.neu_beginnen(False)
    assert s.video.autoplay is False and not s.spielt
