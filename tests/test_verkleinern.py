"""Verkleinern nach grobem Schema (`core/verkleinern.py`, Ben 17.11.2026,
`docs/plan_medien_reiter.md` §5): Ziel nie über dem Original, Schätzung, ffmpeg-Aufruf — und ein
echter Lauf mit ffmpeg, wo es installiert ist (die CI hat keins)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time

import pytest

from trainingsapp.core import videoinfo
from trainingsapp.core.verkleinern import (
    BILDRATEN,
    KURZE_SEITEN,
    SCHARF,
    SPARSAM,
    SPRACHE,
    VORLAGEN,
    Abgebrochen,
    Schema,
    ffmpeg_befehl,
    mit_ffmpeg,
    wahl,
    ziel,
)
from trainingsapp.core.videoinfo import Videoinfo

FULLHD = Videoinfo(dauer_s=130, breite=1920, hoehe=1080, bildrate=59.94, ton=True)


def test_vorlagen_und_schaetzung() -> None:
    werte = {k: ziel(s, FULLHD, 84_000_000) for k, s in VORLAGEN.items()}
    assert [(z.kurze_seite, z.bildrate, z.kanaele) for z in werte.values()] == [
        (480, 24, 1),
        (720, 30, 2),
        (1080, 30, 2),
    ]
    # Mittel ist die Stufe der Kamera: 0,8 Mbit/s Bild + 64 kbit/s Ton
    assert (werte["mittel"].video_bitrate, werte["mittel"].audio_bitrate) == (800_000, 64_000)
    mb = {k: round(z.bytes(130) / 1e6, 1) for k, z in werte.items()}
    assert mb == {"klein": 6.4, "mittel": 14.3, "gross": 34.7}
    assert not any(z.nicht_kleiner for z in werte.values())


def test_genauer_bildqualitaet_ton_und_nie_ueber_dem_original() -> None:
    sparsam = ziel(Schema(720, 30, SPARSAM, SPRACHE), FULLHD)
    scharf = ziel(Schema(720, 30, SCHARF, SPRACHE), FULLHD)
    assert (sparsam.video_bitrate, scharf.video_bitrate) == (560_000, 1_200_000)
    assert (sparsam.audio_bitrate, sparsam.kanaele) == (48_000, 1)
    klein = Videoinfo(dauer_s=60, breite=640, hoehe=360, bildrate=25, ton=False)
    z = ziel(VORLAGEN["gross"], klein, 1_000_000)
    assert (z.kurze_seite, z.bildrate, z.kanaele, z.nicht_kleiner) == (360, 25, 0, True)
    assert wahl(klein) == ((360,), (15, 24), False)
    assert wahl(None) == (KURZE_SEITEN, BILDRATEN, True)


def test_ffmpeg_befehl_ohne_metadaten_und_mit_fortschritt(tmp_path) -> None:
    z = ziel(VORLAGEN["mittel"], FULLHD)
    befehl = ffmpeg_befehl(tmp_path / "a.mov", tmp_path / "b.mp4", z, "/usr/bin/ffmpeg")
    assert befehl[0] == "/usr/bin/ffmpeg"
    for paar in (
        ("-map_metadata", "-1"),
        ("-map_chapters", "-1"),
        ("-movflags", "+faststart"),
        ("-c:v", "libx264"),
        ("-b:a", "64000"),
        ("-ac", "2"),
        ("-progress", "pipe:1"),
    ):
        i = befehl.index(paar[0])
        assert befehl[i + 1] == paar[1]


def test_ohne_ffmpeg_ein_klarer_fehler(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("trainingsapp.core.verkleinern.ffmpeg", lambda: None)
    with pytest.raises(RuntimeError, match="nicht installiert"):
        mit_ffmpeg(tmp_path / "a.mp4", tmp_path / "b.mp4", ziel(VORLAGEN["mittel"]))


def _video(pfad, *, breite=1280, hoehe=720, fps=30, sekunden=3, ton=True) -> None:
    """Ein kurzes Testvideo mit ffmpeg — mit Ortsangabe in den Metadaten."""
    befehl = [
        "ffmpeg",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={breite}x{hoehe}:rate={fps}",
    ]
    if ton:
        befehl += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
    befehl += [
        "-t",
        str(sekunden),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-b:v",
        "6M",
        *(["-c:a", "aac"] if ton else []),
        "-metadata",
        "location=+52.5200+013.4050/",
        str(pfad),
    ]
    subprocess.run(befehl, check=True)


ffmpeg_da = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ohne ffmpeg")


@ffmpeg_da
def test_echter_lauf_mit_ffmpeg(tmp_path) -> None:
    quelle = tmp_path / "quelle.mp4"
    _video(quelle)
    info = videoinfo.lesen(quelle)
    assert info is not None and info.kurze_seite == 720
    z = ziel(VORLAGEN["klein"], info, quelle.stat().st_size)
    anteile: list[float] = []
    ausgabe = tmp_path / "klein.mp4"
    mit_ffmpeg(quelle, ausgabe, z, dauer_s=info.dauer_s, fortschritt=anteile.append)
    neu = videoinfo.lesen(ausgabe)
    assert neu is not None and (neu.kurze_seite, round(neu.bildrate or 0)) == (480, 24)
    assert anteile and anteile[-1] == 1.0
    assert ausgabe.stat().st_size < quelle.stat().st_size
    assert b"52.5200" not in ausgabe.read_bytes()  # der Ort ist weg
    # Ohne Ton
    stumm = tmp_path / "stumm.mp4"
    mit_ffmpeg(quelle, stumm, ziel(Schema(360, 15, SPARSAM, "ohne"), info), dauer_s=info.dauer_s)
    assert videoinfo.lesen(stumm).ton is False  # type: ignore[union-attr]


@ffmpeg_da
def test_abbruch_laesst_keine_halbe_datei(tmp_path) -> None:
    quelle = tmp_path / "quelle.mp4"
    _video(quelle, sekunden=8)
    abbruch = threading.Event()
    abbruch.set()
    ausgabe = tmp_path / "halb.mp4"
    with pytest.raises(Abgebrochen):
        mit_ffmpeg(quelle, ausgabe, ziel(VORLAGEN["mittel"]), dauer_s=8, abbruch=abbruch)
    assert not ausgabe.exists()


def _ersatz(tmp_path, rumpf: str):
    """Ein Programm an Stelle von ffmpeg (Python mit Shebang) — es nimmt dieselben Argumente,
    das letzte ist die Zieldatei."""
    datei = tmp_path / "ersatz_ffmpeg"
    datei.write_text(f"#!{sys.executable}\nimport sys, time, pathlib\n{rumpf}\n", "utf-8")
    datei.chmod(0o755)
    return str(datei)


def _im_faden(ziel_fn):
    """``ziel_fn`` in einem Faden — ``(fertig?, Ergebnis oder Ausnahme)`` nach höchstens 20 s:
    hinge `mit_ffmpeg`, hinge sonst der ganze Testlauf."""
    ergebnis: list[object] = []

    def lauf() -> None:
        try:
            ergebnis.append(ziel_fn())
        except BaseException as fehler:  # der Test sieht sie an
            ergebnis.append(fehler)

    faden = threading.Thread(target=lauf, daemon=True)
    faden.start()
    faden.join(timeout=20)
    return not faden.is_alive(), ergebnis[0] if ergebnis else None


@pytest.mark.skipif(sys.platform == "win32", reason="Shebang")
def test_viele_meldungen_haengen_nicht(tmp_path) -> None:
    """Ein kaputtes Video: ffmpeg schreibt mehr Meldungen, als eine Leitung fasst, und bricht
    ab — der Fehler kommt mit der letzten Zeile, nichts hängt (Prüfrunde 18.11.2026)."""
    programm = _ersatz(
        tmp_path,
        'sys.stderr.write("Fehler im Block 7\\n" * 20000)\n'
        'print("out_time_us=1000000", flush=True)\n'
        'sys.stderr.write("Ungültige Daten\\n")\n'
        "sys.exit(1)",
    )
    ausgabe = tmp_path / "neu.mp4"
    fertig, ergebnis = _im_faden(
        lambda: mit_ffmpeg(
            tmp_path / "a.mp4", ausgabe, ziel(VORLAGEN["mittel"]), dauer_s=2, programm=programm
        )
    )
    assert fertig, "mit_ffmpeg hängt"
    assert isinstance(ergebnis, RuntimeError) and str(ergebnis) == "Ungültige Daten"
    assert not ausgabe.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="Shebang")
def test_abbruch_auch_nach_der_letzten_fortschrittszeile(tmp_path) -> None:
    """Im zweiten Durchgang (``+faststart``) schreibt ffmpeg keinen Fortschritt mehr — ein
    Abbruch dort gilt trotzdem: keine Datei, kein Entwurf (Prüfrunde 18.11.2026)."""
    programm = _ersatz(
        tmp_path,
        'print("out_time_us=2000000", flush=True)\n'
        'print("progress=end", flush=True)\n'
        "time.sleep(4)\n"
        'pathlib.Path(sys.argv[-1]).write_bytes(b"fertig")',
    )
    ausgabe = tmp_path / "neu.mp4"
    abbruch = threading.Event()
    threading.Timer(0.6, abbruch.set).start()
    beginn = time.monotonic()
    fertig, ergebnis = _im_faden(
        lambda: mit_ffmpeg(
            tmp_path / "a.mp4",
            ausgabe,
            ziel(VORLAGEN["mittel"]),
            dauer_s=2,
            abbruch=abbruch,
            programm=programm,
        )
    )
    assert fertig and isinstance(ergebnis, Abgebrochen)
    assert time.monotonic() - beginn < 3.5  # nicht erst nach dem Ende des Programms
    assert not ausgabe.exists()
