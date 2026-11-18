"""`trainingsapp-paket`: prüfen, bauen, Index — das Werkzeug fürs Inhalte-Repo."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import tomllib
import zlib

from trainingsapp.core.pakete import GRUNDAUSSTATTUNG, paket_lesen
from trainingsapp.data.seed import SEED_DATEI
from trainingsapp.paket_werkzeug import (
    INDEX_FORMAT,
    bauen,
    index,
    main,
    pruefen,
    quelle_pruefen,
    uebernehmen,
    wortliste_lesen,
    wortliste_pruefen,
)

QIGONG = """[paket]
name = "Qigong"
version = 2
neuigkeiten = "Neu: Lotus"

[[exercises]]
key = "baum"
name = "Baum"
description = "Knie weich."
typen = ["Qigong"]
regionen = ["Bein"]
spec = "halten"
icon_key = "fitness_center"

[[exercises]]
key = "lotus"
name = "Lotus"
description = "Sitzen."
typen = ["Entspannung"]
spec = "halten"
icon_key = "self_improvement"
"""


def test_standardpaket_besteht_die_pruefung() -> None:
    fehler, hinweise = pruefen(SEED_DATEI, symbole=None)
    assert fehler == [] and hinweise == []


def test_pruefen_findet_tippfehler(tmp_path) -> None:
    datei = tmp_path / "x.toml"
    datei.write_text(
        QIGONG.replace('key = "lotus"', 'key = "Lötus"').replace("Sitzen.", ""), encoding="utf-8"
    )
    fehler, hinweise = pruefen(datei, symbole=["fitness_center"])
    assert any("Lötus" in f for f in fehler)
    assert any("Beschreibung fehlt" in f for f in fehler)
    assert any("self_improvement" in f for f in fehler)  # nicht in der Auswahl
    assert any("Typ „Qigong“" in h for h in hinweise)
    kaputt = tmp_path / "kaputt.toml"
    kaputt.write_text('[paket]\nname = "A\n', encoding="utf-8")
    assert pruefen(kaputt)[0] and "kaputt.toml" in pruefen(kaputt)[0][0]


def test_bauen_und_index(tmp_path) -> None:
    datei = tmp_path / "qigong.toml"
    datei.write_text(QIGONG, encoding="utf-8")
    pfad = bauen(datei, tmp_path / "dist")
    assert pfad.name == "uebungspaket_Qigong.json"
    inhalt = paket_lesen(pfad.read_bytes())
    assert inhalt.paket.version == 2 and inhalt.paket.neuigkeiten == "Neu: Lotus"
    assert [u.name for u in inhalt.uebungen] == ["Baum", "Lotus"]

    daten = index([pfad, SEED_DATEI], "https://example.org/pakete/", quelle="Praxis")
    assert daten["format"] == INDEX_FORMAT and daten["quelle"] == {"name": "Praxis"}
    q, std = daten["pakete"]
    assert q["url"] == "https://example.org/pakete/uebungspaket_Qigong.json"
    assert q["sha256"] == hashlib.sha256(pfad.read_bytes()).hexdigest()
    assert (q["bytes"], q["uebungen"], q["kurse"], q["neuigkeiten"]) == (
        pfad.stat().st_size,
        2,
        0,
        "Neu: Lotus",
    )
    assert std["id"] == GRUNDAUSSTATTUNG and std["kurse"] == 1 and std["signatur"] is None


def test_index_behaelt_das_datum_unveraenderter_pakete(tmp_path) -> None:
    """K30: `veroeffentlicht` = letzter Inhaltswechsel, nicht Build-Datum — bei gleicher
    Prüfsumme kommt das Datum aus dem vorigen Index, ein geändertes Paket bekommt heute."""
    datei = tmp_path / "qigong.toml"
    datei.write_text(QIGONG, encoding="utf-8")
    pfad = bauen(datei, tmp_path / "dist")
    vorher = index([pfad, SEED_DATEI], "https://x/p")
    vorher["pakete"][0]["veroeffentlicht"] = "2026-01-02"
    vorher["pakete"][1]["veroeffentlicht"] = "2026-03-04"
    datei.write_text(QIGONG.replace("Neu: Lotus", "Neu: Lotus, Baum"), encoding="utf-8")
    pfad = bauen(datei, tmp_path / "dist")

    daten = index([pfad, SEED_DATEI], "https://x/p", vorher=vorher)
    q, std = daten["pakete"]
    assert q["veroeffentlicht"] != "2026-01-02"  # Inhalt geändert → heute
    assert std["veroeffentlicht"] == "2026-03-04"  # unverändert → Datum bleibt

    ziel = tmp_path / "dist" / "index.json"
    ziel.write_text(json.dumps(daten), encoding="utf-8")
    assert main(["index", str(pfad), str(SEED_DATEI), "--ziel", str(ziel), "--basis-url", "x"]) == 0
    neu = json.loads(ziel.read_text(encoding="utf-8"))
    assert neu["pakete"][1]["veroeffentlicht"] == "2026-03-04"


def test_befehlszeile(tmp_path, capsys) -> None:
    datei = tmp_path / "qigong.toml"
    datei.write_text(QIGONG, encoding="utf-8")
    assert main(["pruefen", str(datei)]) == 0
    assert "in Ordnung" in capsys.readouterr().out
    assert main(["bauen", str(datei), "--ziel", str(tmp_path / "dist")]) == 0
    gebaut = tmp_path / "dist" / "uebungspaket_Qigong.json"
    assert gebaut.exists()
    ziel = tmp_path / "dist" / "index.json"
    assert main(["index", str(gebaut), "--ziel", str(ziel), "--basis-url", "https://x/p"]) == 0
    assert json.loads(ziel.read_text("utf-8"))["pakete"][0]["url"].startswith("https://x/p/")
    datei.write_text(QIGONG.replace("Sitzen.", ""), encoding="utf-8")
    assert main(["bauen", str(datei), "--ziel", str(tmp_path / "dist")]) == 1


def test_wortliste(tmp_path, monkeypatch) -> None:
    liste = tmp_path / "wortliste.txt"
    liste.write_text("# Sprachregelung\nAnalyse\nerkennt Stressbelastung  # Beispiel\n", "utf-8")
    assert wortliste_lesen(liste) == ["Analyse", "erkennt Stressbelastung"]
    roh = {
        "paket": {"name": "Q", "neuigkeiten": "Neue HRV-Analyse"},
        "exercises": [
            {"key": "a", "name": "A", "description": "Die Übung erkennt Stressbelastung."}
        ],
        "kurse": [
            {"key": "k", "name": "K", "kapitel": [{"key": "1", "titel": "T", "text": "nichts"}]}
        ],
    }
    treffer = wortliste_pruefen(roh, wortliste_lesen(liste))
    assert treffer == [
        "Paket, neuigkeiten: „Analyse“",
        "Übung „A“, Beschreibung: „erkennt Stressbelastung“",
    ]
    datei = tmp_path / "q.toml"
    datei.write_text(QIGONG.replace("Knie weich.", "Die Analyse zeigt es."), "utf-8")
    fehler, hinweise = pruefen(datei, None, ["Analyse"])
    assert fehler == [] and any("Wortliste" in h for h in hinweise)
    fehler, _ = pruefen(datei, None, ["Analyse"], streng=True)
    assert any("Wortliste" in f for f in fehler)
    assert main(["pruefen", str(datei), "--wortliste", str(liste)]) == 0
    assert main(["pruefen", str(datei), "--wortliste", str(liste), "--streng"]) == 1


def test_wortliste_gepruefte_stellen(tmp_path, capsys) -> None:
    """Eine geprüfte Stelle (Ben, 14.11.2026: „Auswertung“ als Bildschirmname) meldet sich
    nicht mehr einzeln und ist auch mit ``--streng`` kein Fehler — bis sich ihr Text ändert."""
    from trainingsapp.paket_werkzeug import geprueft_lesen, textkennung

    liste = tmp_path / "wortliste.txt"
    liste.write_text("Analyse\n", "utf-8")
    satz = "Die Analyse zeigt es."
    datei = tmp_path / "q.toml"
    datei.write_text(QIGONG.replace("Knie weich.", satz), "utf-8")
    roh = tomllib.loads(datei.read_text("utf-8"))
    uebung = next(e for e in roh["exercises"] if satz in e["description"])
    stelle = f"Übung „{uebung['name']}“, Beschreibung"
    kennung = textkennung(uebung["description"])
    geprueft = tmp_path / "geprueft.txt"
    geprueft.write_text(
        f"# Kommentar\n\nq.toml | {stelle} | Analyse | {kennung} | Name eines Bildschirms\n",
        "utf-8",
    )
    assert geprueft_lesen(geprueft) == {("q.toml", stelle, "analyse", kennung)}

    # Ohne die Datei: der Treffer wie bisher; mit leerer Menge nennt er seine Kennung
    _, hinweise = pruefen(datei, None, ["Analyse"])
    assert hinweise[-1] == f"Wortliste: {stelle}: „Analyse“"
    _, hinweise = pruefen(datei, None, ["Analyse"], geprueft=set())
    assert hinweise[-1] == f"Wortliste: {stelle}: „Analyse“ (Kennung {kennung})"

    aufruf = ["pruefen", str(datei), "--wortliste", str(liste), "--geprueft", str(geprueft)]
    assert main([*aufruf, "--streng"]) == 0
    ausgabe = capsys.readouterr().out
    assert "Wortliste: 1 geprüfte Stelle" in ausgabe and stelle not in ausgabe

    # Der Text ändert sich: Die Prüfung gilt nicht mehr, die Stelle sagt warum
    datei.write_text(QIGONG.replace("Knie weich.", "Die Analyse ist auffällig."), "utf-8")
    assert main([*aufruf, "--streng"]) == 1
    assert "geprüft war ein anderer Text" in capsys.readouterr().out

    # Eine Zeile ohne Begründung gilt nicht — das Werkzeug bricht ab, statt sie zu überlesen
    geprueft.write_text(f"q.toml | {stelle} | Analyse | {kennung}\n", "utf-8")
    assert main(aufruf) == 2
    assert "geprueft.txt, Zeile 1" in capsys.readouterr().out


def test_eigener_typ_ein_hinweis_je_typ(tmp_path, capsys) -> None:
    """Typen außerhalb des Standardpakets: ein Hinweis je Typ mit der Zahl der Übungen, bei
    einer einzelnen mit ihrem Namen (so fällt ein Tippfehler auf); Urteil je Datei zuerst."""
    datei = tmp_path / "q.toml"
    datei.write_text(QIGONG, "utf-8")
    roh = tomllib.loads(QIGONG)
    anzahl = sum("Qigong" in e.get("typen", []) for e in roh["exercises"])
    _, hinweise = pruefen(datei)
    zu_typ = [h for h in hinweise if "Typ „Qigong“" in h]
    wo = f"{anzahl} Übungen" if anzahl > 1 else f"Übung „{roh['exercises'][0]['name']}“"
    assert zu_typ == [f"Typ „Qigong“ ist nicht im Standardpaket ({wo} — gewollt?)"]
    assert main(["pruefen", str(datei)]) == 0
    zeilen = capsys.readouterr().out.splitlines()
    assert zeilen[0] == f"{datei}: in Ordnung"
    assert all(z.startswith("    Hinweis: ") for z in zeilen[1:] if not z.startswith("("))


def test_quelle_pruefen_wie_die_app(tmp_path, monkeypatch) -> None:
    import trainingsapp.core.paketquelle as pq

    datei = tmp_path / "qigong.toml"
    datei.write_text(QIGONG, "utf-8")
    pfad = bauen(datei, tmp_path / "dist")
    daten = index([pfad], "https://x/pakete", quelle="Praxis")
    antworten = {
        "https://x/pakete/index.json": json.dumps(daten).encode(),
        "https://x/pakete/" + pfad.name: pfad.read_bytes(),
    }
    laden = lambda url: antworten[url]  # noqa: E731
    zeilen, fehler = quelle_pruefen("https://x/pakete/index.json", laden)
    assert (
        fehler == []
        and zeilen[0] == "Quelle „Praxis“: 1 Paket(e)"
        and "Prüfsumme in Ordnung" in zeilen[1]
    )
    antworten["https://x/pakete/" + pfad.name] = b"{}"
    _, fehler = quelle_pruefen("https://x/pakete/index.json", laden)
    assert fehler and "Prüfsumme" in fehler[0]
    monkeypatch.setattr(pq, "_laden", laden)
    import trainingsapp.paket_werkzeug as werkzeug

    monkeypatch.setattr(werkzeug, "netz_laden", laden)
    assert main(["quelle", "https://x/pakete/index.json"]) == 1


# ---------------------------------------------------------------------------
# uebernehmen: Export der App zurück ins TOML
# ---------------------------------------------------------------------------


def _git(ordner, *args, datum: str | None = None) -> None:
    umgebung = {**os.environ, "GIT_AUTHOR_DATE": datum, "GIT_COMMITTER_DATE": datum}
    subprocess.run(
        [
            *(
                "git",
                "-C",
                str(ordner),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=t@example.invalid",
            ),
            *("-c", "commit.gpgsign=false", *args),
        ],
        check=True,
        capture_output=True,
        env=umgebung if datum else None,
    )


def _committen(datei, datum: str | None = None) -> None:
    """Die TOML committen — wie im Inhalte-Repo: Die Fassung einer Version steht in der
    Geschichte, `uebernehmen` findet dort die Basis."""
    if not (datei.parent / ".git").exists():
        _git(datei.parent, "init", "-q")
    _git(datei.parent, "add", datei.name)
    _git(datei.parent, "commit", "-q", "--allow-empty", "-m", "Stand", datum=datum)


def _ohne_basiszeile(zeilen: list[str]) -> list[str]:
    """Ohne die Zeilen zu Basis und Versionsvorschlag — sie hängen am Stand von git."""
    return [z for z in zeilen if not z.startswith(("Basis: ", "Version: "))]


def _png(farbe: bytes = b"\x00\x00") -> bytes:
    def block(typ: bytes, daten: bytes) -> bytes:
        laenge, pruef = struct.pack(">I", len(daten)), struct.pack(">I", zlib.crc32(typ + daten))
        return laenge + typ + daten + pruef

    return (
        b"\x89PNG\r\n\x1a\n"
        + block(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
        + block(b"IDAT", zlib.compress(farbe))
        + block(b"IEND", b"")
    )


def _export(tmp_path, toml_text: str, aendern) -> tuple:
    """Die TOML-Datei schreiben und committen, bauen, am JSON ``aendern`` (wie die App),
    beides zurückgeben."""
    datei = tmp_path / "qigong.toml"
    datei.write_text(toml_text, encoding="utf-8")
    _committen(datei)
    export = bauen(datei, tmp_path / "dist")
    roh = json.loads(export.read_text("utf-8"))
    aendern(roh)
    export.write_text(json.dumps(roh, ensure_ascii=False), encoding="utf-8")
    return export, datei


QIGONG_MIT_KOMMENTAR = QIGONG.replace(
    '[[exercises]]\nkey = "lotus"', '# ── Sitzen ──\n[[exercises]]\nkey = "lotus"'
)


def test_uebernehmen_schreibt_geaenderte_felder_und_laesst_den_rest(tmp_path) -> None:
    def aendern(roh):
        baum, lotus = roh["exercises"]
        baum["name"] = "Baum, tief"
        baum["typen"] = ["Qigong", "Kräftigung"]
        baum["result_spec"]["fields"][0]["quick"] = [20, 40]  # weicht von der Vorlage ab
        baum["uhr"] = False
        baum["limit_spec"] = {"rules": [{"type": "timer", "seconds": 300}]}
        baum["media"] = [{"kind": "video", "source": "url", "uri": "https://x/v", "title": "Video"}]
        lotus["regionen"] = ["Bein"]

    export, datei = _export(tmp_path, QIGONG_MIT_KOMMENTAR, aendern)
    zeilen, fehler = uebernehmen(export, datei)
    assert fehler == []
    assert zeilen[0] == "Baum: Name, Typen, Parameter, Limits, Uhr, Videos"
    assert zeilen[1] == "Lotus: Regionen"
    text = datei.read_text("utf-8")
    assert "# ── Sitzen ──" in text and 'key = "baum"' in text, "Kommentare und keys bleiben"
    assert 'name = "Baum, tief"' in text and 'spec = "halten"\n' in text.split("lotus")[1]
    assert "[exercises.result_spec]" in text and "[[exercises.result_spec.fields]]" in text
    assert (
        "uhr = false" in text and 'limit_spec = {rules = [{type = "timer", seconds = 300}]}' in text
    )
    # Dasselbe gebaut ist wieder der Export: Rundlauf ohne Verlust
    wieder = json.loads(bauen(datei, tmp_path / "dist2").read_text("utf-8"))
    erwartet = json.loads(export.read_text("utf-8"))
    for a, b in zip(wieder["exercises"], erwartet["exercises"], strict=True):
        a["typen"], b["typen"] = sorted(a["typen"]), sorted(b["typen"])
    assert wieder["exercises"] == erwartet["exercises"]
    # Ein zweites Mal: nichts mehr zu tun
    assert uebernehmen(export, datei) == (["Keine Änderung"], [])


def test_uebernehmen_findet_zur_vorlage_zurueck_und_ergaenzt_skalar_neben_tabelle(tmp_path) -> None:
    from trainingsapp.core.result_spec import VORLAGEN

    def aendern(roh):
        roh["exercises"][0]["result_spec"] = VORLAGEN["saetze_wdh"][1].to_dict()
        roh["exercises"][1]["result_spec"]["fields"][0]["quick"] = [5]
        roh["exercises"][1]["zaehlt_als"] = "duration"

    export, datei = _export(tmp_path, QIGONG, aendern)
    uebernehmen(export, datei)
    text = datei.read_text("utf-8")
    assert 'spec = "saetze_wdh"' in text and text.count("[exercises.result_spec]") == 1

    # ein Skalar, nachdem der Block eine Untertabelle hat: landet bei der Übung, nicht darin
    def nochmal(roh):
        roh["exercises"][1]["uhr"] = False

    roh = json.loads(export.read_text("utf-8"))
    nochmal(roh)
    export.write_text(json.dumps(roh), encoding="utf-8")
    zeilen, fehler = uebernehmen(export, datei)
    assert _ohne_basiszeile(zeilen) == ["Lotus: Uhr"] and fehler == []
    gelesen = paket_lesen(tomllib.loads(datei.read_text("utf-8")))
    assert [u.uhr for u in gelesen.uebungen] == [True, False]
    assert gelesen.uebungen[1].zaehlt_als == "duration"


def test_uebernehmen_schreibt_beschleunigung_als_inline_tabelle(tmp_path) -> None:
    """Die Karte „Beschleunigungssensor“ (Paketfeld ``beschleunigung``) kommt als eine Zeile
    ins TOML und geht zurück zur Vorgabe, indem die Zeile wegfällt."""
    from trainingsapp.core.zaehlen import SensorWahl

    def aendern(roh):
        roh["exercises"][0]["beschleunigung"] = {"wiederholungen": False, "atmung": True}

    export, datei = _export(tmp_path, QIGONG, aendern)
    zeilen, fehler = uebernehmen(export, datei)
    assert (_ohne_basiszeile(zeilen), fehler) == (["Baum: Beschleunigungssensor"], [])
    text = datei.read_text("utf-8")
    assert "beschleunigung = {wiederholungen = false, atmung = true}" in text
    gelesen = paket_lesen(tomllib.loads(text))
    assert [u.beschleunigung for u in gelesen.uebungen] == [
        SensorWahl(wiederholungen=False, atmung=True),
        SensorWahl(),
    ]
    assert pruefen(datei, symbole=None)[0] == []
    # Dasselbe gebaut ist wieder der Export
    wieder = json.loads(bauen(datei, tmp_path / "dist2").read_text("utf-8"))
    assert wieder["exercises"][0]["beschleunigung"] == {"wiederholungen": False, "atmung": True}
    assert "beschleunigung" not in wieder["exercises"][1]

    # Übernommen und committet — dann ist das die Basis der nächsten Runde
    _committen(datei)
    roh = json.loads(export.read_text("utf-8"))
    del roh["exercises"][0]["beschleunigung"]
    export.write_text(json.dumps(roh, ensure_ascii=False), encoding="utf-8")
    zeilen, fehler = uebernehmen(export, datei)
    assert (_ohne_basiszeile(zeilen), fehler) == (["Baum: Beschleunigungssensor"], [])
    assert "beschleunigung" not in datei.read_text("utf-8")


def test_gps_im_werkzeug_pruefen_und_uebernehmen(tmp_path) -> None:
    """Die Karte „GPS“ (Paketfeld ``gps``, Ben 13.11.2026): Die App liest tolerant (Unsinn =
    GPS aus bzw. Vorgabe), das Werkzeug sagt es vorher — fehlende Rechenart und unbrauchbare
    Grenzen als Fehler, eine unbekannte Rechenart als Hinweis. `uebernehmen` schreibt die Wahl
    aus der App als eine Zeile zurück ins TOML."""
    from trainingsapp.core.gps_wahl import GpsWahl

    datei = tmp_path / "x.toml"
    datei.write_text(
        QIGONG.replace(
            'spec = "halten"\nicon_key = "fitness_center"',
            'spec = "halten"\nicon_key = "fitness_center"\ngps = {tempo = [6, 5, 4, 3]}',
        ).replace(
            'icon_key = "self_improvement"',
            'icon_key = "self_improvement"\ngps = {art = "schwimmen"}',
        ),
        encoding="utf-8",
    )
    fehler, hinweise = pruefen(datei, symbole=None)
    assert fehler == [
        "Übung „Baum“: gps: „art“ fehlt (gehen, laufen, rad) — GPS bleibt aus",
        "Übung „Baum“: gps: „tempo“ braucht vier aufsteigende Zahlen in km/h (bis 120), "
        "nicht [6, 5, 4, 3]",
    ]
    assert [h for h in hinweise if "gps" in h] == [
        "Übung „Lotus“: gps: unbekannte Rechenart „schwimmen“ — GPS bleibt aus "
        "(bekannt: gehen, laufen, rad)"
    ]
    gelesen = paket_lesen(tomllib.loads(datei.read_text("utf-8")))
    assert [u.gps for u in gelesen.uebungen] == [GpsWahl(), GpsWahl()]

    def aendern(roh):
        roh["exercises"][0]["gps"] = {"art": "gehen", "tempo": [4.0, 5.0, 6.0, 7.0]}

    export, datei = _export(tmp_path, QIGONG, aendern)
    zeilen, fehler = uebernehmen(export, datei)
    assert (_ohne_basiszeile(zeilen), fehler) == (["Baum: GPS"], [])
    text = datei.read_text("utf-8")
    assert 'gps = {art = "gehen", tempo = [4.0, 5.0, 6.0, 7.0]}' in text
    assert pruefen(datei, symbole=None)[0] == []
    gelesen = paket_lesen(tomllib.loads(text))
    assert [u.gps for u in gelesen.uebungen] == [
        GpsWahl("gehen", (4.0, 5.0, 6.0, 7.0)),
        GpsWahl(),
    ]


def test_pruefen_meldet_unsinn_in_beschleunigung(tmp_path) -> None:
    """Die App liest ``beschleunigung`` tolerant (Unsinn = Vorgabe) — das Werkzeug sagt es
    vorher: ein falscher Typ ist ein Fehler (die Wahl ginge verloren), ein unbekannter
    Schlüssel ein Hinweis (Tippfehler oder neuere App), wie Typen außerhalb des Standards."""
    from trainingsapp.core.zaehlen import SensorWahl

    datei = tmp_path / "x.toml"
    datei.write_text(
        QIGONG.replace(
            'spec = "halten"\nicon_key = "fitness_center"',
            'spec = "halten"\nicon_key = "fitness_center"\n'
            'beschleunigung = {wiederholungen = "nein", atmung = 1, wiederholung = false}',
        ).replace(
            'icon_key = "self_improvement"',
            'icon_key = "self_improvement"\n'
            'beschleunigung = {atmung = true, feld = "reps", vorlage = "rudern"}',
        ),
        encoding="utf-8",
    )
    fehler, hinweise = pruefen(datei, symbole=None)
    assert fehler == [
        'Übung „Baum“: beschleunigung: „wiederholungen“ muss true oder false sein, nicht "nein"',
        "Übung „Baum“: beschleunigung: „atmung“ muss true oder false sein, nicht 1",
    ]
    assert [h for h in hinweise if "beschleunigung" in h] == [
        "Übung „Baum“: beschleunigung: unbekannter Schlüssel „wiederholung“ — wird überlesen "
        "(bekannt: wiederholungen, atmung, vorlage, feld, signal, atmung_bewegung)",
        "Übung „Lotus“: beschleunigung: unbekannte Vorlage „rudern“ — zählt wie "
        "„Automatisch“ (bekannt: auto, kniebeuge, liegestuetz)",
    ]
    # Die App liest dasselbe Paket weiter — mit der Vorgabe, wo Unsinn stand
    gelesen = paket_lesen(tomllib.loads(datei.read_text("utf-8")))
    assert [u.beschleunigung for u in gelesen.uebungen] == [
        SensorWahl(),
        SensorWahl(atmung=True, feld="reps", vorlage="rudern"),
    ]
    # Keine Tabelle: ein Fehler, nichts sonst
    datei.write_text(
        QIGONG.replace('typen = ["Entspannung"]', 'typen = ["Entspannung"]\nbeschleunigung = true'),
        encoding="utf-8",
    )
    fehler, _ = pruefen(datei, symbole=None)
    assert fehler == [
        "Übung „Lotus“: beschleunigung: keine Tabelle (etwa { wiederholungen = true }), sondern "
        "true — alles gilt als Vorgabe"
    ]


def test_uebernehmen_probe_version_und_neue(tmp_path, capsys) -> None:
    def aendern(roh):
        roh["exercises"][0]["name"] = "Anders"
        roh["exercises"].append(
            {
                "id": "eigene-1",
                "name": "Eigene Übung",
                "description": "Am Handy angelegt.",
                "typen": [],
                "regionen": [],
            }
        )

    export, datei = _export(tmp_path, QIGONG, aendern)
    vorher = datei.read_text("utf-8")
    assert main(["uebernehmen", str(export), str(datei), "--probe"]) == 0
    out = capsys.readouterr().out
    assert "Baum: Name" in out and "Neu angelegt: Eigene Übung (key „eigene_uebung“)" in out
    assert datei.read_text("utf-8") == vorher, "--probe schreibt nicht"
    # Die Datei ist schon weiter (Version 3) — die Basis ist trotzdem Version 2 aus der
    # Geschichte: Die Nummer vom Handy blockiert nichts (Ben, 17.11.2026)
    datei.write_text(vorher.replace("version = 2", "version = 3"), encoding="utf-8")
    assert main(["uebernehmen", str(export), str(datei)]) == 0
    text = datei.read_text("utf-8")
    assert 'name = "Anders"' in text and 'key = "eigene_uebung"' in text
    assert "version = 3" in text
    gelesen = paket_lesen(tomllib.loads(text))
    neu = gelesen.uebungen[-1]
    assert neu.name == "Eigene Übung" and neu.id != "eigene-1", "die ID folgt aus dem key"
    # Ein Export unter anderem Paket: keine Basis — nichts übernehmen, nur nennen …
    datei.write_text(vorher, encoding="utf-8")
    roh = json.loads(export.read_text("utf-8"))
    roh["paket"] = {"id": "anderes", "name": "Meins"}
    export.write_text(json.dumps(roh), encoding="utf-8")
    assert main(["uebernehmen", str(export), str(datei)]) == 0
    out = capsys.readouterr().out
    assert "Keine Basis" in out and "Baum: Name" in out
    assert datei.read_text("utf-8") == vorher
    # … außer ausdrücklich ohne Basis (wie bis 17.11.2026)
    assert main(["uebernehmen", str(export), str(datei), "--ohne-basis"]) == 0
    assert 'name = "Anders"' in datei.read_text("utf-8")


def test_uebernehmen_aelterer_export_holt_nichts_zurueck(tmp_path) -> None:
    """Der Versuch vom 17.11.2026: Am Laptop ist die Beschreibung seit dem Export geändert —
    ein älterer Export derselben Version darf sie nicht zurückholen. Haben beide dieselbe
    Stelle geändert, bleibt die Datei, und die Zeile nennt den Wert der App."""
    export, datei = _export(tmp_path, QIGONG, lambda roh: None)
    text = datei.read_text("utf-8").replace('"Knie weich."', '"Knie weich, Blick weit."')
    datei.write_text(text, encoding="utf-8")
    assert uebernehmen(export, datei) == (["Keine Änderung"], [])
    assert "Blick weit" in datei.read_text("utf-8")
    # Auch, wenn die Änderung am Laptop schon committet ist: Der Export ist älter
    _git(tmp_path, "commit", "-q", "-am", "Laptop", datum="2030-01-02T12:00:00")
    roh = json.loads(export.read_text("utf-8"))
    roh["exportiert"] = "2030-01-01T12:00:00+00:00"
    export.write_text(json.dumps(roh, ensure_ascii=False), encoding="utf-8")
    assert uebernehmen(export, datei) == (["Keine Änderung"], [])
    # Beide geändert: die Datei bleibt, die App wird genannt
    roh["exercises"][0]["description"] = "Knie weich, Fersen schwer."
    roh["exercises"][1]["description"] = "Sitzen, Rücken lang."
    export.write_text(json.dumps(roh, ensure_ascii=False), encoding="utf-8")
    zeilen, fehler = uebernehmen(export, datei)
    assert fehler == []
    assert zeilen[0] == "Lotus: Beschreibung"
    assert any(
        z.startswith("Baum: Beschreibung") and "die Datei bleibt" in z and "Fersen schwer" in z
        for z in zeilen
    )
    text = datei.read_text("utf-8")
    assert "Blick weit" in text and "Rücken lang" in text


def test_uebernehmen_zip_mit_neuer_uebung_und_datei(tmp_path) -> None:
    """Eine ZIP der App (eigenes Paket mit Foto): Die neue Übung bekommt einen Block, ihre
    Datei liegt danach unter ``medien/<paket>/`` neben der TOML und wird als ``datei``
    genannt; gebaut ist sie wieder dieselbe Paketdatei."""
    from trainingsapp.core.paketdatei import paket_oeffnen, paket_zip
    from trainingsapp.core.paketmedien import name_fuer

    export, datei = _export(tmp_path, QIGONG, lambda roh: None)
    bild = _png()
    name = name_fuer(hashlib.sha256(bild).hexdigest(), "png")
    roh = json.loads(export.read_text("utf-8"))
    roh["version"] = 4
    roh["exercises"].append(
        {
            "id": "handy-1",
            "name": "Kranich",
            "description": "Auf einem Bein.",
            "media": [{"kind": "image", "source": "paket", "uri": name, "title": "Foto"}],
        }
    )
    (tmp_path / "bild.png").write_bytes(bild)
    zip_pfad = tmp_path / "export.zip"
    paket_zip(zip_pfad, json.dumps(roh, ensure_ascii=False).encode(), {name: tmp_path / "bild.png"})
    zeilen, fehler = uebernehmen(zip_pfad, datei)
    assert fehler == []
    assert "Neu angelegt: Kranich (key „kranich“)" in zeilen
    abgelegt = tmp_path / "medien" / "qigong" / name.removeprefix("medien/")
    assert abgelegt.read_bytes() == bild
    text = datei.read_text("utf-8")
    assert f'datei = "medien/qigong/{abgelegt.name}"' in text
    gebaut = paket_oeffnen(bauen(datei, tmp_path / "dist2"))
    (kranich,) = [u for u in gebaut.uebungen if u.name == "Kranich"]
    assert [m.uri for m in kranich.media] == [name]


QIGONG_MIT_KURS = (
    QIGONG
    + """
[[kurse]]
key = "einstieg"
name = "Einstieg"

[[kurse.kapitel]]
key = "a"
titel = "Warum stehen?"
text = "Text"

[[kurse.kapitel]]
key = "b"
titel = "Stehen üben"
bedingung = { art = "tage", soll = 3 }

[[kurse.kapitel.plaene]]
name = "Stehen"
wochentage = [0, 1, 2, 3, 4, 5, 6]
uebungen = [{ uebung = "baum" }]
"""
)


def test_uebernehmen_aus_der_datenbank_mit_kapitelplan(tmp_path) -> None:
    from trainingsapp.core.models import Plan, PlanItem, Subject
    from trainingsapp.data.db import oeffnen
    from trainingsapp.data.kurse import KursRepo
    from trainingsapp.data.pakete import PaketRepo
    from trainingsapp.data.repositories import ExerciseRepo, PlanRepo, SubjectRepo
    from trainingsapp.data.seed import seed_inhalt

    datei = tmp_path / "qigong.toml"
    datei.write_text(QIGONG_MIT_KURS, encoding="utf-8")
    inhalt = seed_inhalt(datei)
    db = tmp_path / "app.db"
    con = oeffnen(db)
    PaketRepo(con).importieren(inhalt)
    profil = Subject(name="Test")
    SubjectRepo(con).speichern(profil)
    (kurs,) = PaketRepo(con).kurse(inhalt.paket.id)
    KursRepo(con).kapitel_erreichen(kurs, kurs.kapitel[1], profil.id)
    # In der App: Plan auf drei Tage, Lotus mit Ziel dazu; Übung Baum umbenannt
    plaene = PlanRepo(con)
    (plan,) = [p for p in plaene.alle(profil.id) if p.kurs_kapitel_id]
    lotus = next(u for u in inhalt.uebungen if u.name == "Lotus")
    plan.items.append(PlanItem(plan_id=plan.id, exercise_id=lotus.id, order=1, target={"hold": 60}))
    plaene.speichern(plan)
    plaene.wochentage_setzen(plan.id, [0, 2, 4])
    uebungen = ExerciseRepo(con)
    baum = next(u for u in uebungen.alle() if u.name == "Baum")
    baum.name = "Baum, tief"
    uebungen.speichern(baum)
    eigener = Plan(name="Eigener", subject_id=profil.id)
    plaene.speichern(eigener)
    con.close()

    zeilen, fehler = uebernehmen(db, datei)
    assert fehler == []
    assert zeilen[:2] == [
        "Baum: Name",
        "Einstieg, Kapitel „Stehen üben“, Plan „Stehen“: Wochentage, Übungen",
    ]
    text = datei.read_text("utf-8")
    assert "wochentage = [0, 2, 4]" in text
    assert 'uebungen = [{uebung = "baum"}, {uebung = "lotus", ziel = {hold = 60}}]' in text
    assert 'bedingung = { art = "tage", soll = 3 }' in text, "Unberührtes bleibt, wie es war"
    gelesen = paket_lesen(tomllib.loads(text))
    vorlage = gelesen.kurse[0].kapitel[1].plaene[0]
    assert [i.exercise_id for i in vorlage.items] == [baum.id, lotus.id]
    assert uebernehmen(db, datei) == (["Keine Änderung"], [])
    # Datei inzwischen weiter (Version 3, Baum am Laptop umbenannt): Die Basis ist der
    # Paketstand der Datenbank — die Nummer blockiert nichts, und was beide geändert haben,
    # bleibt, wie es in der Datei steht
    datei.write_text(
        text.replace("version = 2", "version = 3").replace("Baum, tief", "Baum am Laptop"),
        encoding="utf-8",
    )
    zeilen, fehler = uebernehmen(db, datei)
    assert fehler == [] and zeilen[0] == "Keine Änderung"
    assert any("Baum am Laptop: Name" in z and "App: Baum, tief" in z for z in zeilen)
    assert "Baum am Laptop" in datei.read_text("utf-8")


def test_pruefen_sieht_takt_und_beschleunigung_je_planuebung(tmp_path) -> None:
    """Prüfrunde A6, Befund 2: `pruefen` meldet Unsinn in `takt`/`beschleunigung` auch an
    `plaene[].uebungen[]` und in den Plänen der Kurskapitel — mit dem Weg dorthin; ein
    unlesbarer Takt heißt dort „die Planübung folgt der Übung“ (so liest ihn die App), nie
    „kein Takt“. `takt = {}` (ausdrücklich keiner) ist in Ordnung."""
    from trainingsapp.core.takt import AUS

    text = (
        QIGONG_MIT_KURS.replace(
            'uebungen = [{ uebung = "baum" }]',
            'uebungen = [{ uebung = "baum", takt = { phasen = "x" }, '
            'beschleunigung = { atmung = "ja", wdh = true } }]',
        )
        + """
[[plaene]]
key = "morgen"
name = "Morgen"
uebungen = [
  { uebung = "baum", takt = { phasen = [{ dauer_s = "x", art = "tanz" }] } },
  { uebung = "lotus", takt = {}, beschleunigung = { atmung = true } },
]
"""
    )
    datei = tmp_path / "x.toml"
    datei.write_text(text, encoding="utf-8")
    fehler, hinweise = pruefen(datei, symbole=None)
    assert fehler == [
        "Plan „Morgen“, Übung „baum“: takt: Phase 1: „dauer_s“ muss eine Zahl zwischen 0.1 und "
        '600 sein, nicht "x" — die Phase fällt weg',
        "Kurs „Einstieg“, Kapitel „Stehen üben“, Plan „Stehen“, Übung „baum“: beschleunigung: "
        '„atmung“ muss true oder false sein, nicht "ja"',
        "Kurs „Einstieg“, Kapitel „Stehen üben“, Plan „Stehen“, Übung „baum“: takt: „phasen“ "
        'muss eine Liste von Tabellen sein, nicht "x" — die Planübung folgt der Übung',
    ]
    assert [h for h in hinweise if "Plan" in h] == [
        "Plan „Morgen“, Übung „baum“: takt: Phase 1: unbekannte Art „tanz“ — gilt als „frei“ "
        "(bekannt: ein, aus, halten, ab, auf, frei)",
        "Kurs „Einstieg“, Kapitel „Stehen üben“, Plan „Stehen“, Übung „baum“: beschleunigung: "
        "unbekannter Schlüssel „wdh“ — wird überlesen (bekannt: wiederholungen, atmung, "
        "vorlage, feld, signal, atmung_bewegung)",
    ]
    # Die App liest dasselbe Paket: der kaputte Takt heißt „wie die Übung“, `{}` keiner
    gelesen = paket_lesen(tomllib.loads(text))
    (kapitelplan,) = gelesen.kurse[0].kapitel[1].plaene
    assert kapitelplan.items[0].takt is None
    morgen_baum, morgen_lotus = gelesen.plaene[0].vorlage.items
    assert morgen_baum.takt is None and morgen_lotus.takt is AUS


def test_pruefen_warnt_vor_kapiteln_ohne_key(tmp_path) -> None:
    """K41 (Ben, 11.11.2026): Ohne ``key`` hängt die Kapitel-ID an der Nummer — ein Einschub
    verschöbe Fortschritt und Kapitelpläne. Das Werkzeug sagt es vorher."""
    kurs = (
        '\n[[kurse]]\nkey = "ruhe"\nname = "Ruhe"\n'
        '\n[[kurse.kapitel]]\nkey = "eins"\ntitel = "Eins"\ntext = "a"\n'
        '\n[[kurse.kapitel]]\ntitel = "Zwei"\ntext = "b"\n'
    )
    datei = tmp_path / "x.toml"
    datei.write_text(QIGONG + kurs, encoding="utf-8")
    fehler, hinweise = pruefen(datei, symbole=None)
    assert fehler == []
    assert any("Kurs „Ruhe“: Kapitel 2 ohne `key`" in h for h in hinweise)
    datei.write_text(QIGONG + kurs.replace('titel = "Zwei"', 'key = "zwei"\ntitel = "Zwei"'))
    assert not any("ohne `key`" in h for h in pruefen(datei, symbole=None)[1])


INDIVIDUELL = """[paket]
name = "Für A."
version = "0.1.0"

[[exercises]]
key = "kranich"
name = "Kranich"
description = "Auf einem Bein."

[[plaene]]
key = "morgens"
name = "Morgens"
uebungen = [
  { uebung = "kranich" },
  { uebung = "kniebeuge", paket = "Standard" },
  { uebung = "baum", paket = "Qigong Basis" },
]
"""

QIGONG_MIT_ID = QIGONG.replace(
    '[paket]\nname = "Qigong"',
    '[paket]\nid = "d9f9b050-7d51-409d-8df7-efffb04543ef"\nname = "Qigong Basis"',
)


def test_verweise_auf_andere_pakete(tmp_path) -> None:
    """V1 und V2 (`docs/plan_paketverweise.md`, Ben 17.11.2026): ``paket = "…"`` an einer
    Planübung wird zur ID der Übung dort — bei einem Paket mit eigener ID im Kopf die aus
    jener Datei, nicht die aus dem Namen; `pruefen` folgt jedem Verweis in die Datei daneben."""
    from trainingsapp.core.pakete import paket_id, uebung_id

    (tmp_path / "standard.toml").write_text(SEED_DATEI.read_text("utf-8"), encoding="utf-8")
    (tmp_path / "qigong.toml").write_text(QIGONG_MIT_ID, encoding="utf-8")
    datei = tmp_path / "fuer_a.toml"
    datei.write_text(INDIVIDUELL, encoding="utf-8")
    fehler, hinweise = pruefen(datei, symbole=None)
    assert fehler == [] and not any("Verweis" in h or "prüfbar" in h for h in hinweise)
    gebaut = json.loads(bauen(datei, tmp_path / "dist").read_text("utf-8"))
    ids = [e["uebung"] for e in gebaut["plaene"][0]["uebungen"]]
    assert ids[1] == uebung_id(GRUNDAUSSTATTUNG, "kniebeuge")
    assert ids[2] == uebung_id("d9f9b050-7d51-409d-8df7-efffb04543ef", "baum")
    assert ids[2] != uebung_id(paket_id("Qigong Basis"), "baum"), "nicht die ID aus dem Namen"

    kaputt = INDIVIDUELL.replace(
        '{ uebung = "kniebeuge", paket = "Standard" }', '{ uebung = "kniebeuge" }'
    ).replace(
        '{ uebung = "baum", paket = "Qigong Basis" }',
        '{ uebung = "gibtsnicht", paket = "Standard" }',
    )
    datei.write_text(kaputt, encoding="utf-8")
    fehler, _ = pruefen(datei, symbole=None)
    assert any("„kniebeuge“ ist kein Schlüssel dieses Pakets" in f for f in fehler)
    assert any("„gibtsnicht“ gibt es in „Standard“ nicht" in f for f in fehler)
    datei.write_text(
        INDIVIDUELL.replace('paket = "Qigong Basis"', 'paket = "Unbekannt"'), encoding="utf-8"
    )
    fehler, hinweise = pruefen(datei, symbole=None)
    assert fehler == []
    assert any("„Unbekannt“ liegt nicht neben fuer_a.toml" in h for h in hinweise)


def test_version_gegen_die_veroeffentlichte_fassung(tmp_path) -> None:
    """Stufe 4 (`docs/plan_rueckweg_handy.md`, Ben 17.11.2026): Mit ``--stufe-als-hinweis``
    sperrt nur eine Nummer, die nicht gestiegen ist; eine zu kleine Stufe ist ein Hinweis —
    die Geräte rechnen sie selbst aus dem Unterschied. Nach `uebernehmen` schlägt das Werkzeug
    die Nummer vor."""
    from trainingsapp.paket_werkzeug import gegen_pruefen

    alt = tmp_path / "alt"
    alt.mkdir()
    (alt / "qigong.toml").write_text(QIGONG, encoding="utf-8")
    veroeffentlicht = bauen(alt / "qigong.toml", tmp_path / "dist")
    neu_text = QIGONG + (
        '\n[[exercises]]\nkey = "kranich"\nname = "Kranich"\ndescription = "Auf einem Bein."\n'
    )
    datei = tmp_path / "qigong.toml"
    datei.write_text(neu_text, encoding="utf-8")  # neue Übung, Nummer gleich (2 = 0.0.2)
    for locker in (False, True):
        fehler, _ = gegen_pruefen(datei, str(veroeffentlicht), stufe_als_hinweis=locker)
        assert fehler and "mindestens 0.1.0, steht 0.0.2" in fehler[0]
    datei.write_text(neu_text.replace("version = 2", 'version = "0.0.3"'), encoding="utf-8")
    assert gegen_pruefen(datei, str(veroeffentlicht))[0], "streng: die Stufe reicht nicht"
    fehler, hinweise = gegen_pruefen(datei, str(veroeffentlicht), stufe_als_hinweis=True)
    assert fehler == [] and "mindestens 0.1.0, steht 0.0.3" in hinweise[0]

    # Vorschlag nach dem Übernehmen: gegen den letzten Commit
    def aendern(roh):
        roh["exercises"].append({"id": "x", "name": "Kranich", "description": "Bein."})

    repo = tmp_path / "repo"
    repo.mkdir()
    export, datei = _export(repo, QIGONG, aendern)
    zeilen, fehler = uebernehmen(export, datei)
    assert fehler == []
    assert any(
        z.startswith("Version: steht 0.0.2, für diese Änderungen mindestens 0.1.0") for z in zeilen
    )


def test_verlinken_ersetzt_die_datei_durch_einen_link(tmp_path) -> None:
    """Stufe 5: ``datei = …`` wird ``uri = …`` — mit ``pruefen_mit`` nur, wenn der Link genau
    diese Datei liefert (keine Webseite, keine andere Datei)."""
    from trainingsapp.paket_werkzeug import verlinken

    bild = _png()
    (tmp_path / "medien").mkdir()
    (tmp_path / "medien" / "foto.png").write_bytes(bild)
    datei = tmp_path / "qigong.toml"
    datei.write_text(
        QIGONG.replace(
            'icon_key = "fitness_center"',
            'icon_key = "fitness_center"\nmedia = [{ datei = "medien/foto.png", title = "Foto" }]',
        ),
        encoding="utf-8",
    )
    url = "https://example.invalid/foto.png"
    sha = hashlib.sha256(bild).hexdigest()
    fehler = verlinken(datei, "medien/foto.png", url, pruefen_mit=lambda u: (sha, "text/html", 9))[
        1
    ]
    assert fehler and "Webseite" in fehler[0]
    fehler = verlinken(
        datei, "medien/foto.png", url, pruefen_mit=lambda u: ("0" * 64, "image/png", 9)
    )[1]
    assert fehler and "andere Datei" in fehler[0]
    assert 'datei = "medien/foto.png"' in datei.read_text("utf-8"), "bei Fehlern bleibt die Datei"
    zeilen, fehler = verlinken(
        datei, "medien/foto.png", url, pruefen_mit=lambda u: (sha, "image/png", len(bild))
    )
    assert fehler == [] and zeilen[0].startswith("Link geprüft: dieselbe Datei")
    text = datei.read_text("utf-8")
    assert f'uri = "{url}"' in text and "datei =" not in text and 'title = "Foto"' in text
    assert pruefen(datei)[0] == []
    assert verlinken(datei, "medien/foto.png", url)[1], "nennt die Datei nicht mehr"
    assert verlinken(datei, "medien/foto.png", "http://x")[1], "nur https"


def test_verlinken_schreibt_die_pruefsumme_an_einen_videolink(tmp_path) -> None:
    """Ein Video, das die App selbst lädt (`core.linkvideos.direkt`), bekommt ``#sha256=…`` —
    die App spielt nur diese Datei; ``pruefen`` meldet eine unlesbare Prüfsumme."""
    from trainingsapp.core.linkvideos import pruefsumme
    from trainingsapp.paket_werkzeug import verlinken

    video = b"\x00\x00\x00\x18ftypmp42" + b"v" * 100
    (tmp_path / "medien").mkdir()
    (tmp_path / "medien" / "baum.mp4").write_bytes(video)
    datei = tmp_path / "qigong.toml"
    datei.write_text(
        QIGONG.replace(
            'icon_key = "fitness_center"',
            'icon_key = "fitness_center"\nmedia = [{ datei = "medien/baum.mp4", title = "Baum" }]',
        ),
        encoding="utf-8",
    )
    zeilen, fehler = verlinken(datei, "medien/baum.mp4", "https://example.invalid/baum.mp4")
    assert fehler == [] and any("Prüfsumme am Link" in z for z in zeilen)
    (eintrag,) = [e for e in tomllib.loads(datei.read_text("utf-8"))["exercises"] if "media" in e]
    uri = eintrag["media"][0]["uri"]
    assert uri.startswith("https://example.invalid/baum.mp4#sha256=")
    assert pruefsumme(uri) == hashlib.sha256(video).hexdigest()
    assert pruefen(datei)[0] == []
    datei.write_text(datei.read_text("utf-8").replace(uri, uri[:-3]), encoding="utf-8")
    assert any("Prüfsumme am Link unlesbar" in f for f in pruefen(datei)[0])


QIGONG_MIT_PLAN = (
    QIGONG
    + """
[[plaene]]
key = "morgens"
name = "Morgens"
wochentage = [0, 2, 4]
uebungen = [{ uebung = "baum" }]
"""
)


def test_uebernehmen_paketplaene_aus_einem_export(tmp_path) -> None:
    """Stufe 6 (Ben, 17.11.2026: „beides“ — auch Pläne des Pakets ändern sich am Handy): Ein
    Export trägt die Pläne mit ihrem Paketschlüssel; je Feld und je Planübung in drei Wegen,
    die Datei gewinnt; ein neuer Plan wird angehängt, Übungen darin als ``key``."""

    def aendern(roh):
        (plan,) = roh["plaene"]
        plan["wochentage"] = [0, 1, 2, 3, 4]
        plan["uebungen"].append({"uebung": roh["exercises"][1]["id"], "ziel": {"hold": 60}})
        roh["plaene"].append(
            {"key": "abends", "name": "Abends", "uebungen": [{"uebung": roh["exercises"][1]["id"]}]}
        )

    export, datei = _export(tmp_path, QIGONG_MIT_PLAN, aendern)
    zeilen, fehler = uebernehmen(export, datei)
    assert fehler == []
    assert "Plan „Morgens“: uebungen, wochentage" in zeilen
    assert "Neuer Plan „Abends“ (key „abends“)" in zeilen
    text = datei.read_text("utf-8")
    assert "wochentage = [0, 1, 2, 3, 4]" in text
    assert '{uebung = "lotus", ziel = {hold = 60}}' in text and 'key = "abends"' in text
    gelesen = paket_lesen(tomllib.loads(text))
    assert [p.key for p in gelesen.plaene] == ["morgens", "abends"]
    # Beide ändern den Namen: die Datei bleibt, die Zeile sagt es
    _committen(datei)
    datei.write_text(text.replace('name = "Morgens"', 'name = "Früh"'), encoding="utf-8")
    roh = json.loads(export.read_text("utf-8"))
    roh["plaene"][0]["name"] = "Morgenrunde"
    export.write_text(json.dumps(roh, ensure_ascii=False), encoding="utf-8")
    zeilen, fehler = uebernehmen(export, datei)
    assert any(
        "Plan „Morgenrunde“: name — in der Datei und in der App geändert" in z for z in zeilen
    )
    assert 'name = "Früh"' in datei.read_text("utf-8")


def test_uebernehmen_paketplan_aus_der_datenbank(tmp_path) -> None:
    from trainingsapp.core.models import Subject
    from trainingsapp.data.db import oeffnen
    from trainingsapp.data.pakete import PaketRepo
    from trainingsapp.data.repositories import PlanRepo, SubjectRepo
    from trainingsapp.data.seed import seed_inhalt

    datei = tmp_path / "qigong.toml"
    datei.write_text(QIGONG_MIT_PLAN, encoding="utf-8")
    inhalt = seed_inhalt(datei)
    db = tmp_path / "app.db"
    con = oeffnen(db)
    profil = Subject(name="Test")
    SubjectRepo(con).speichern(profil)
    PaketRepo(con).importieren(inhalt, subject_id=profil.id)
    (plan,) = PlanRepo(con).des_pakets(inhalt.paket.id, profil.id)
    PlanRepo(con).wochentage_setzen(plan.id, [5, 6])
    con.close()
    zeilen, fehler = uebernehmen(db, datei)
    assert fehler == [] and "Plan „Morgens“: wochentage" in zeilen
    assert "wochentage = [5, 6]" in datei.read_text("utf-8")
    assert uebernehmen(db, datei)[0] == ["Keine Änderung"]


def test_kurs_kopie_kehrt_in_ihren_kurs_zurueck(tmp_path) -> None:
    """Stufe 6 (Ben, 17.11.2026): Einen Paketkurs bearbeitet man in der App als Kopie; die
    Kopie merkt sich ihr Original (Migration 067), `uebernehmen` führt sie zurück — Kapitel
    behalten ihren ``key`` (daran hängt der Fortschritt), neue bekommen einen. Aus der
    Datenbank wie aus einem Export (eigenes Paket mit der Kopie)."""
    from trainingsapp.core.kursbau import kurs_kopie
    from trainingsapp.core.kurse import Kapitel
    from trainingsapp.core.pakete import Paket, paket_json
    from trainingsapp.data.db import oeffnen
    from trainingsapp.data.kurse import KursRepo
    from trainingsapp.data.pakete import PaketRepo
    from trainingsapp.data.seed import seed_inhalt

    datei = tmp_path / "qigong.toml"
    datei.write_text(QIGONG_MIT_KURS, encoding="utf-8")
    _committen(datei)
    inhalt = seed_inhalt(datei)
    db = tmp_path / "app.db"
    con = oeffnen(db)
    PaketRepo(con).importieren(inhalt)
    kurse = KursRepo(con)
    (original,) = kurse.des_pakets(inhalt.paket.id)
    kopie = kurs_kopie(original, version=inhalt.paket.version)
    kopie.kapitel[0].text = "Weil Stehen trägt."
    kopie.kapitel.append(Kapitel(titel="Dritte Woche", text="Weiter."))
    kurse.speichern(kopie)
    assert kurse.laden(kopie.id).kopie_von["kurs"] == original.id, "gespeichert (Migration 067)"
    con.close()

    zeilen, fehler = uebernehmen(db, datei)
    assert fehler == []
    assert any(
        z.startswith("Kurs „Einstieg“: aus der Kopie übernommen (3 Kapitel)") for z in zeilen
    )
    text = datei.read_text("utf-8")
    assert "Weil Stehen trägt." in text and "(Kopie)" not in text
    gelesen = paket_lesen(tomllib.loads(text))
    (kurs,) = gelesen.kurse
    assert kurs.id == original.id and kurs.name == "Einstieg"
    assert [k.id for k in kurs.kapitel[:2]] == [k.id for k in original.kapitel], "Fortschritt"
    assert kurs.kapitel[2].titel == "Dritte Woche"
    assert [i.exercise_id for i in kurs.kapitel[1].plaene[0].items] == [
        u.id for u in gelesen.uebungen if u.name == "Baum"
    ]
    assert 'uebung = "baum"' in text
    # Am Laptop dasselbe Kapitel anders: die Datei bleibt
    datei.write_text(text.replace("Weil Stehen trägt.", "Am Laptop."), encoding="utf-8")
    kopie.kapitel[0].text = "Am Handy noch einmal."
    export = tmp_path / "eigen.json"
    export.write_bytes(paket_json(Paket(id="eigen", name="Meins", version=10000), [], [kopie]))
    assert json.loads(export.read_bytes())["kurse"][0]["kopie_von"]["kurs"] == original.id
    zeilen, fehler = uebernehmen(export, datei)
    assert any("Kurs „Einstieg“: in der Datei und in der Kopie geändert" in z for z in zeilen)
    assert "Am Laptop." in datei.read_text("utf-8")


def test_bauen_schreibt_was_das_paket_braucht(tmp_path) -> None:
    """V3 (Ben, 17.11.2026): Verweist ein Paket auf Übungen anderer Pakete daneben, steht im
    Kopf, welche es braucht — ab welcher Version und wo die App sie findet; die Adresse eines
    privaten Pakets nur in einem privaten (der Code nie)."""
    from trainingsapp.paket_werkzeug import privat_bauen

    (tmp_path / "standard.toml").write_text(SEED_DATEI.read_text("utf-8"), encoding="utf-8")
    (tmp_path / "qigong.toml").write_text(
        QIGONG_MIT_ID + '\n[privat]\nfuer = ""\n', encoding="utf-8"
    )
    (tmp_path / "qigong.zugang.json").write_text(
        json.dumps({"ordner": "geheim123", "code": "ABCDEFGH"}), encoding="utf-8"
    )
    datei = tmp_path / "fuer_a.toml"
    datei.write_text(INDIVIDUELL, encoding="utf-8")
    basis = "https://example.invalid/pakete"
    gebaut = json.loads(bauen(datei, tmp_path / "dist", basis_url=basis).read_text("utf-8"))
    braucht = {v["name"]: v for v in gebaut["paket"]["braucht"]}
    assert braucht["Standard"]["id"] == GRUNDAUSSTATTUNG
    assert braucht["Standard"]["quelle"] == f"{basis}/uebungspaket_Standard.json"
    from trainingsapp.data.seed import seed_inhalt

    assert braucht["Standard"]["version"] == seed_inhalt(SEED_DATEI).paket.version
    assert "quelle" not in braucht["Qigong Basis"], "ein öffentliches Paket verrät keinen Ordner"
    assert "ABCDEFGH" not in json.dumps(gebaut)
    # Privat verweist auf privat: die Adresse ja, der Code nie
    datei.write_text(INDIVIDUELL.replace("[paket]", '[privat]\nfuer = "A."\n\n[paket]'), "utf-8")
    pfad, _ = privat_bauen(datei, tmp_path / "dist2", basis)
    from trainingsapp.core.paketdatei import paket_oeffnen

    zugang = json.loads((tmp_path / "fuer_a.zugang.json").read_text("utf-8"))
    kopf = paket_oeffnen(pfad, code=zugang["code"]).paket
    qigong = next(v for v in kopf.braucht if v.name == "Qigong Basis")
    assert qigong.quelle == f"{basis}/p/geheim123/paket.json"
    assert "ABCDEFGH" not in pfad.read_bytes().decode("latin-1")


def test_link_laden_geht_ueber_den_https_oeffner(monkeypatch) -> None:
    """S35 (Release-Durchsicht 18.11.2026): Auch das Werkzeug (`verlinken --pruefen`) folgt
    Umleitungen nur auf https:// — `netz.OEFFNER`, nie `urlopen`."""
    import io
    import urllib.request

    import pytest

    from trainingsapp.core import netz
    from trainingsapp.paket_werkzeug import link_laden

    class Antwort(io.BytesIO):
        def __init__(self, daten: bytes) -> None:
            super().__init__(daten)
            self.headers = {"Content-Type": "video/mp4"}

        def geturl(self) -> str:
            return "https://x.invalid/v.mp4"

    gesehen: list[str] = []

    class Oeffner:
        def open(self, anfrage, timeout=None):
            gesehen.append(anfrage.full_url)
            return Antwort(b"abc")

    monkeypatch.setattr(netz, "OEFFNER", Oeffner())
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("urlopen umgangen"))
    _sha, art, n = link_laden("https://x.invalid/v.mp4")
    assert (art, n, gesehen) == ("video/mp4", 3, ["https://x.invalid/v.mp4"])
