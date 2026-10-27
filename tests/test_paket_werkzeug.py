"""`trainingsapp-paket`: prüfen, bauen, Index — das Werkzeug fürs Inhalte-Repo."""

from __future__ import annotations

import hashlib
import json
import tomllib

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


def _export(tmp_path, toml_text: str, aendern) -> tuple:
    """Die TOML-Datei bauen, am JSON ``aendern`` (wie die App), beides zurückgeben."""
    datei = tmp_path / "qigong.toml"
    datei.write_text(toml_text, encoding="utf-8")
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
    assert zeilen == ["Lotus: Uhr"] and fehler == []
    gelesen = paket_lesen(tomllib.loads(datei.read_text("utf-8")))
    assert [u.uhr for u in gelesen.uebungen] == [True, False]
    assert gelesen.uebungen[1].zaehlt_als == "duration"


def test_uebernehmen_probe_version_und_fremde(tmp_path, capsys) -> None:
    def aendern(roh):
        roh["exercises"][0]["name"] = "Anders"
        roh["exercises"].append(
            {"id": "eigene-1", "name": "Eigene Übung", "typen": [], "regionen": []}
        )

    export, datei = _export(tmp_path, QIGONG, aendern)
    vorher = datei.read_text("utf-8")
    assert main(["uebernehmen", str(export), str(datei), "--probe"]) == 0
    out = capsys.readouterr().out
    assert "Baum: Name" in out and "Nicht übernommen" in out and "Eigene Übung" in out
    assert datei.read_text("utf-8") == vorher, "--probe schreibt nicht"
    # andere Version desselben Pakets: nichts übernehmen
    datei.write_text(vorher.replace("version = 2", "version = 3"), encoding="utf-8")
    assert main(["uebernehmen", str(export), str(datei)]) == 1
    assert "Version 2" in capsys.readouterr().out
    # anderer Paketname (eigener Export unter neuem Namen): Zuordnung über die IDs trotzdem
    roh = json.loads(export.read_text("utf-8"))
    roh["paket"] = {"id": "anderes", "name": "Meins"}
    export.write_text(json.dumps(roh), encoding="utf-8")
    assert main(["uebernehmen", str(export), str(datei)]) == 0
    assert 'name = "Anders"' in datei.read_text("utf-8")


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
    # Datei inzwischen weiter: andere Version als in der Datenbank → nichts
    datei.write_text(text.replace("version = 2", "version = 3"), encoding="utf-8")
    zeilen, fehler = uebernehmen(db, datei)
    assert zeilen == [] and "Version 2" in fehler[0]
