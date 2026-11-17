"""Der Kopf von Video- und Tondateien (`core/videoinfo.py`, Ben 17.11.2026,
`docs/plan_medien_reiter.md` §3): Dauer, Bildgröße, Bildrate, Tonspur — aus künstlichen
Köpfen (`mp4_bau`), weil die CI kein ffmpeg hat."""

from __future__ import annotations

from mp4_bau import mp4, spur
from trainingsapp.core import videoinfo
from trainingsapp.core.videoinfo import Videoinfo, aus_bytes, lesen


def test_video_mit_ton_kopf_am_ende(tmp_path) -> None:
    daten = mp4(
        spur(b"vide", breite=1920, hoehe=1080, dauer_s=3.0, bilder=90),
        spur(b"soun", dauer_s=3.0),
        dauer_s=3.0,
    )
    datei = tmp_path / "a.mp4"
    datei.write_bytes(daten)
    info = lesen(datei)
    assert info == Videoinfo(dauer_s=3.0, breite=1920, hoehe=1080, bildrate=30.0, ton=True)
    assert info.text() == "1080p · 30 fps · 0:03"
    assert aus_bytes(daten) == info


def test_hochkant_ohne_ton_kopf_vorn_und_ntsc_bildrate(tmp_path) -> None:
    hoch = mp4(
        spur(b"vide", breite=720, hoehe=1280, dauer_s=2.52, bilder=63),
        dauer_s=2.52,
        moov_vorn=True,
    )
    (tmp_path / "b.mp4").write_bytes(hoch)
    info = lesen(tmp_path / "b.mp4")
    assert info is not None
    assert (info.breite, info.hoehe, info.kurze_seite, info.bildrate, info.ton) == (
        720,
        1280,
        720,
        25.0,
        False,
    )
    # 24000/1001 Bilder je Sekunde: 96 Bilder in 4,004 s
    ntsc = mp4(spur(b"vide", breite=640, hoehe=480, massstab=24000, dauer_s=4.004, bilder=96))
    assert aus_bytes(ntsc).bildrate == 23.976  # type: ignore[union-attr]


def test_version_1_und_64_bit_laenge(tmp_path) -> None:
    daten = mp4(
        spur(b"vide", breite=1280, hoehe=720, dauer_s=130.5, bilder=3915, version=1),
        dauer_s=130.5,
        version=1,
        mdat64=True,
    )
    (tmp_path / "c.mov").write_bytes(daten)
    info = lesen(tmp_path / "c.mov")
    assert info is not None and info.dauer_s == 130.5 and info.aufloesung == "720p"
    assert info.text() == "720p · 30 fps · 2:10"


def test_nur_ton() -> None:
    info = aus_bytes(mp4(spur(b"soun", dauer_s=5.0), dauer_s=5.0))
    assert info == Videoinfo(dauer_s=5.0, ton=True)
    assert info.text() == "0:05" and info.kurze_seite is None


def test_unlesbares_gibt_none(tmp_path, monkeypatch) -> None:
    assert lesen(tmp_path / "fehlt.mp4") is None
    (tmp_path / "leer.mp4").write_bytes(b"")
    assert lesen(tmp_path / "leer.mp4") is None
    # eine Länge über das Dateiende hinaus
    (tmp_path / "kaputt.mp4").write_bytes((400).to_bytes(4, "big") + b"ftyp" + bytes(20))
    assert lesen(tmp_path / "kaputt.mp4") is None
    # ohne moov
    (tmp_path / "ohne.mp4").write_bytes(b"\x00\x00\x00\x10ftypisom\x00\x00\x02\x00")
    assert lesen(tmp_path / "ohne.mp4") is None
    # ein Kopf über der Grenze wird nicht gelesen
    daten = mp4(spur(b"vide", breite=640, hoehe=360, bilder=30))
    (tmp_path / "gross.mp4").write_bytes(daten)
    monkeypatch.setattr(videoinfo, "MOOV_HOECHSTENS", 50)
    assert lesen(tmp_path / "gross.mp4") is None


def test_unbekannte_dauer_und_keine_bilder() -> None:
    # Dauer 0 (ein zerstückeltes MP4 trägt sie woanders): keine Dauer, keine Bildrate
    info = aus_bytes(mp4(spur(b"vide", breite=640, hoehe=360, dauer_s=0.0), dauer_s=0.0))
    assert info == Videoinfo(breite=640, hoehe=360)
    assert info.text() == "360p"
