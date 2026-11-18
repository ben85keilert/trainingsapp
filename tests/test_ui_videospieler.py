"""Der Videospieler mit Knöpfen unter dem Bild (Ben, 18.11.2026: „Behalte die
Videosteuerelemente an, solange kein Play ist“) — `ui/components/videospieler.py`."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
fv = pytest.importorskip("flet_video")

from trainingsapp.ui.components.videospieler import Videospieler  # noqa: E402


def _knoepfe(spieler: Videospieler) -> dict[str, ft.IconButton]:
    zeile = spieler.control.content.controls[1].content
    return {k.data: k for k in zeile.controls if isinstance(k, ft.IconButton)}


def test_knoepfe_stehen_unter_dem_bild_und_das_bild_spielt_auf_tipp() -> None:
    s = Videospieler(["/a.mp4"])
    video = s.video
    assert video.autoplay is False and s.spielt is False
    # Unter dem Bild, nicht darüber: die Zeile ist das zweite Kind der Spalte
    assert list(_knoepfe(s)) == ["video_zurueck", "video_spielen", "video_vor", "video_vollbild"]
    # Über dem Bild nur eine durchsichtige Fläche für den Tipp; im Vollbild die von media_kit,
    # sichtbar beim Öffnen
    auf_dem_bild = video.controls[fv.VideoControlsMode.NORMAL]
    assert isinstance(auf_dem_bild, ft.Container) and auf_dem_bild.on_click is not None
    assert auf_dem_bild.bgcolor == ft.Colors.TRANSPARENT  # sonst ginge der Tipp durch
    voll = video.controls[fv.VideoControlsMode.FULLSCREEN]
    assert isinstance(voll, fv.MaterialVideoControls) and voll.visible_on_mount is True


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
    s._zu_ende(SimpleNamespace(data=False))
    assert s.spielt
    s._zu_ende(SimpleNamespace(data=True))
    assert not s.spielt and knopf.icon == ft.Icons.PLAY_ARROW
    # In der Schleife ist kein Ende
    schleife = Videospieler(["/a.mp4"], autoplay=True, schleife=True)
    schleife._zu_ende(SimpleNamespace(data=True))
    assert schleife.spielt and schleife.video.playlist_mode == fv.PlaylistMode.LOOP


def test_vollbild_und_neu_beginnen() -> None:
    s = Videospieler(["/a.mp4", "/b.mp4"])
    assert [m.resource for m in s.video.playlist] == ["/a.mp4", "/b.mp4"]
    _knoepfe(s)["video_vollbild"].on_click(None)
    assert s.video.fullscreen is True
    s.neu_beginnen(True)
    assert s.video.autoplay is True and s.spielt
    s.neu_beginnen(False)
    assert s.video.autoplay is False and not s.spielt
