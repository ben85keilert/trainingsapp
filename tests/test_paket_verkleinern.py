"""``trainingsapp-paket verkleinern`` (`paket_verkleinern.py`, Ben 17.11.2026,
`docs/plan_medien_reiter.md` §5): große Videos einer Paketdatei am Rechner mit ffmpeg kleiner —
eine neue Datei daneben, das Original bleibt, alle Verweise ziehen mit. Der echte Lauf braucht
ffmpeg (die CI hat keins und überspringt ihn)."""

from __future__ import annotations

import hashlib
import shutil
import subprocess

import pytest

from trainingsapp.core.paketdatei import paket_oeffnen, paket_zip
from trainingsapp.core.pakete import paket_json, paket_lesen
from trainingsapp.core.paketmedien import name_fuer
from trainingsapp.paket_verkleinern import verkleinern
from trainingsapp.paket_werkzeug import main


def _paket(tmp_path, video: bytes, pdf: bytes = b"%PDF-1.7 Blatt"):
    """Eine ZIP wie aus dem Export der App: eine Übung mit Video, ein Plan mit PDF am Plan."""
    v = name_fuer(hashlib.sha256(video).hexdigest(), "mp4")
    p = name_fuer(hashlib.sha256(pdf).hexdigest(), "pdf")
    roh = {
        "paket": {"name": "Knie-Reha", "version": 3},
        "exercises": [
            {
                "key": "beuge",
                "name": "Kniebeuge",
                "media": [{"kind": "video", "source": "paket", "uri": v, "title": "Film"}],
            }
        ],
        "plaene": [
            {
                "key": "woche1",
                "name": "Woche 1",
                "medien": [{"source": "paket", "uri": p, "title": "Blatt"}],
                "uebungen": [{"uebung": "beuge"}],
            }
        ],
    }
    inhalt = paket_lesen(roh)
    (tmp_path / "v.mp4").write_bytes(video)
    (tmp_path / "p.pdf").write_bytes(pdf)
    ziel = tmp_path / "knie.zip"
    paket_zip(
        ziel,
        paket_json(inhalt.paket, inhalt.uebungen, plaene=inhalt.plaene),
        {v: tmp_path / "v.mp4", p: tmp_path / "p.pdf"},
    )
    return ziel, v, p


def test_ohne_ffmpeg_und_falscher_ordner(tmp_path, monkeypatch) -> None:
    quelle, _v, _p = _paket(tmp_path, b"\x00\x00\x00\x08ftyp")
    monkeypatch.setattr("trainingsapp.paket_verkleinern.ffmpeg", lambda: None)
    assert verkleinern(quelle, tmp_path / "neu")[1] == [
        "ffmpeg ist nicht installiert — es wird nur aufgerufen, nie mitgeliefert"
    ]
    monkeypatch.setattr("trainingsapp.paket_verkleinern.ffmpeg", lambda: "/usr/bin/ffmpeg")
    assert "Original bleibt" in verkleinern(quelle, tmp_path)[1][0]
    assert verkleinern(quelle, tmp_path / "neu", vorlage="riesig")[1][0].startswith(
        "Unbekannte Vorlage"
    )


def _video(tmp_path) -> bytes:
    datei = tmp_path / "quelle.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-b:v",
            "6M",
            "-c:a",
            "aac",
            str(datei),
        ],
        check=True,
    )
    return datei.read_bytes()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ohne ffmpeg")
def test_verkleinert_in_eine_neue_datei_und_verweise_ziehen_mit(tmp_path) -> None:
    quelle, v, p = _paket(tmp_path, _video(tmp_path))
    vorher = quelle.read_bytes()
    # Probe: nur zeigen
    zeilen, fehler = verkleinern(quelle, tmp_path / "neu", schreiben=False)
    assert not fehler and any(z.startswith("würde verkleinern:") for z in zeilen)
    assert not (tmp_path / "neu").exists()
    # Über das Werkzeug
    assert main(["verkleinern", str(quelle), "--vorlage", "klein"]) == 0
    (neu,) = (tmp_path / "verkleinert").iterdir()
    assert quelle.read_bytes() == vorher  # das Original bleibt
    inhalt = paket_oeffnen(neu)
    try:
        (u,) = inhalt.uebungen
        (m,) = u.media
        assert m.uri != v and m.uri in inhalt.medien  # neue Prüfsumme, Verweis zieht mit
        (plan,) = inhalt.plaene
        assert [x.uri for x in plan.medien] == [p]  # das PDF bleibt, wie es ist
        neu_video = tmp_path / "neu_video.mp4"
        inhalt.medien[m.uri].kopieren(neu_video)
    finally:
        inhalt.raeumen()
    from trainingsapp.core.videoinfo import lesen

    info = lesen(neu_video)
    assert info is not None and info.kurze_seite == 480
    assert neu_video.stat().st_size < len(_video(tmp_path))
