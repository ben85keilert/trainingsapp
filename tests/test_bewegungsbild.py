"""Das Bild der Bewegung an einer Übung (Taktgeber Teil 2 T6, `docs/plan_taktgeber.md` §5):
Kern (`core/bewegungsbild.py`), Ablage ``Medien/Bewegung/`` (`data.uebungsbilder.
BewegungsbildRepo`, auch GIF), das Ziel ``bewegung/<id>`` für Kamera und Fotoauswahl — und
dass es nie ins Paket kommt. Ohne flet."""

from __future__ import annotations

from pathlib import Path

from trainingsapp.core.anhaenge import Ziel, ziel_lesen
from trainingsapp.core.bewegungsbild import (
    ORDNER,
    TITEL,
    bewegungsbild,
    ist_bewegungsbild,
    mit_bewegungsbild,
)
from trainingsapp.core.models import Exercise, Media, MediaKind, MediaSource
from trainingsapp.core.pakete import stand
from trainingsapp.data.db import migrieren, verbinden
from trainingsapp.data.repositories import ExerciseRepo
from trainingsapp.data.seed import seed_einspielen
from trainingsapp.data.uebungsbilder import BewegungsbildRepo, UebungsbildRepo

#: Kleine, gültige Dateien ohne Metadaten — die Ablage lehnt ab, was sich nicht ablaufen lässt
JPEG = b"\xff\xd8\xff\xe0\x00\x06JFIF\xff\xda\x00\x02" + b"0" * 100 + b"\xff\xd9"
GIF = b"GIF89a" + bytes([1, 0, 1, 0, 0, 0, 0]) + b"," + bytes(9) + b"\x02\x02\x44\x01\x00;"
PNG = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00\x00\x00\x0dIHDR"
    + bytes(13)
    + bytes(4)
    + b"\x00\x00\x00\x02IDAT\x78\x9c"
    + bytes(4)
    + b"\x00\x00\x00\x00IEND"
    + bytes(4)
)


def test_ablage_der_bewegung_mit_gif_und_medium_an_der_uebung(tmp_path: Path) -> None:
    con = verbinden(tmp_path / "a.db")
    migrieren(con)
    seed_einspielen(con)
    uebungen = ExerciseRepo(con)
    a = Exercise(name="Kniebeuge", media=[Media(uri="https://x", title="Video")])
    b = Exercise(name="Liegestütz")
    uebungen.speichern(a)
    uebungen.speichern(b)
    repo = BewegungsbildRepo(con, tmp_path / "Medien")
    assert repo.alle() == [] and repo.pfad_von(a.id) is None
    gif = repo.schreiben(GIF, a.id)
    assert gif.startswith(f"{ORDNER}/bewegung_") and gif.endswith(".gif")
    assert repo.datei(gif).read_bytes() == GIF  # ein GIF bleibt, wie es ist (es läuft)
    assert repo.pfad_von(a.id) == gif
    geladen = uebungen.laden(a.id)
    assert bewegungsbild(geladen.media) == gif
    assert [(m.uri, m.title) for m in geladen.media] == [("https://x", "Video"), (gif, TITEL)]
    # Ein zweites Bild ersetzt das erste als Medium; das Video bleibt; B trägt es auch
    png = repo.schreiben(PNG)
    repo.setzen(a.id, png)
    repo.setzen(b.id, png)
    assert bewegungsbild(uebungen.laden(a.id).media) == png
    assert [m.uri for m in uebungen.laden(a.id).media if m.kind == MediaKind.VIDEO] == ["https://x"]
    neu, alt = repo.alle()
    assert neu.pfad == png and {n for _, n in neu.uebungen} == {"Kniebeuge", "Liegestütz"}
    assert alt.pfad == gif and not alt.benutzt
    # Hochladen: eine fertige Datei wird verschoben
    quelle = tmp_path / "fertig.jpg"
    quelle.write_bytes(JPEG)
    jpg = repo.uebernehmen(quelle, b.id)
    assert not quelle.exists() and jpg.endswith(".jpg") and repo.pfad_von(b.id) == jpg
    # Löschen nimmt die Datei und das Medium
    assert repo.loeschen(png) == 1 and not repo.vorhanden(png)
    assert bewegungsbild(uebungen.laden(a.id).media) is None
    assert bewegungsbild(uebungen.laden(b.id).media) == jpg
    repo.setzen(b.id, None)
    assert uebungen.laden(b.id).media == []
    # Die Ablage der Symbole bleibt getrennt — ein GIF wird dort JPEG, nie ein Medium
    symbole = UebungsbildRepo(con, tmp_path / "Medien")
    assert symbole.alle() == [] and symbole.schreiben(JPEG).endswith(".jpg")
    assert symbole.schreiben(GIF).endswith(".jpg")
    con.close()


def test_nie_ins_paket_und_ziel_route() -> None:
    u = Exercise(
        name="Kniebeuge",
        media=mit_bewegungsbild([Media(uri="https://x")], "Bewegung/bewegung_1.gif"),
    )
    assert ist_bewegungsbild(u.media[-1]) and u.media[-1].source == MediaSource.LOCAL
    assert [m["uri"] for m in stand(u).get("media", [])] == ["https://x"]
    assert Ziel.fuer_bewegung(u.id).teil == f"bewegung/{u.id}"
    gelesen = ziel_lesen(["bewegung", u.id, "foto"], "p1")
    assert gelesen is not None and gelesen[0].bewegung_id == u.id and gelesen[1] == ["foto"]
    assert not gelesen[0].ist_uebung and gelesen[0].ist_bewegung
