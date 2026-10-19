"""`trainingsapp-paket`: prüfen, bauen, Index — das Werkzeug fürs Inhalte-Repo."""

from __future__ import annotations

import hashlib
import json

from trainingsapp.core.pakete import GRUNDAUSSTATTUNG, paket_lesen
from trainingsapp.data.seed import SEED_DATEI
from trainingsapp.paket_werkzeug import (
    INDEX_FORMAT,
    bauen,
    index,
    main,
    pruefen,
    quelle_pruefen,
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
variante_von = "baum"
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
    assert any("Original 'baum'" in f for f in fehler) is False  # baum gibt es
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
    assert inhalt.uebungen[1].family_id == inhalt.uebungen[0].id

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
