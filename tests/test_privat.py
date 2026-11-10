"""Private Pakete (U7, Ben 9.11.2026, F9, `docs/plan_paketinhalte.md` §11): verschlüsselt mit
einem Code, ohne ihn nicht zu lesen; die App merkt sich den Code, Updates aus dem Link öffnet
sie von selbst; das Werkzeug legt Ordner und Code einmal an und lässt private Pakete aus dem
Index."""

from __future__ import annotations

import hashlib
import json
import urllib.error

import pytest

from trainingsapp.core.paketdatei import CodeNoetig, paket_oeffnen
from trainingsapp.core.pakete import Paket, PaketFehler, paket_lesen
from trainingsapp.core.paketquelle import (
    QuellenFehler,
    ZugangNoetig,
    link_lesen,
    paket_laden,
    pruefen,
    stand_json,
    stand_lesen,
    stand_url,
)
from trainingsapp.core.privat import (
    CodeFalsch,
    code_neu,
    code_text,
    datei_entschluesseln,
    datei_verschluesseln,
    entschluesseln,
    ist_privat,
    verschluesseln,
)
from trainingsapp.data.db import oeffnen
from trainingsapp.data.pakete import PaketRepo

CODE = "K7QM9XA2"


def _paket(version: int = 1, text: str = "Langsam.") -> bytes:
    roh = {
        "paket": {"name": "Für Max", "version": version, "fuer": "Max"},
        "exercises": [{"key": "a", "name": "Übung für Max", "description": text}],
    }
    return json.dumps(roh, ensure_ascii=False).encode("utf-8")


def test_verschluesseln_falscher_code_und_verfaelscht(tmp_path) -> None:
    daten = _paket() * 3000  # einige hundert kB; mehrere Blöcke prüft die Datei unten
    geheim = verschluesseln(daten, CODE)
    assert ist_privat(geheim) and b"Max" not in geheim
    assert entschluesseln(geheim, CODE) == daten
    assert verschluesseln(daten, CODE) != geheim  # frisches Salz
    with pytest.raises(CodeFalsch):
        entschluesseln(geheim, "K7QM9XA3")
    kaputt = bytearray(geheim)
    kaputt[40] ^= 1
    with pytest.raises(CodeFalsch):
        entschluesseln(bytes(kaputt), CODE)
    # Datei für Datei, über mehrere Blöcke
    gross = tmp_path / "gross.bin"
    gross.write_bytes(bytes(range(256)) * 9000)  # gut 2 MiB
    zu, auf = tmp_path / "zu.bin", tmp_path / "auf.bin"
    datei_verschluesseln(gross, zu, CODE)
    assert entschluesseln(zu.read_bytes(), CODE) == gross.read_bytes()
    datei_entschluesseln(zu, auf, CODE)
    assert auf.read_bytes() == gross.read_bytes()
    with pytest.raises(CodeFalsch):
        datei_entschluesseln(zu, tmp_path / "nicht.bin", "AAAAAAAA")
    assert not (tmp_path / "nicht.bin").exists()
    assert len(code_neu()) == 8


def test_paket_oeffnen_braucht_den_code(tmp_path) -> None:
    geheim = verschluesseln(_paket(), CODE)
    with pytest.raises(CodeNoetig):
        paket_oeffnen(geheim)
    with pytest.raises(PaketFehler, match="Der Code passt nicht"):
        paket_oeffnen(geheim, code="AAAAAAAA")
    inhalt = paket_oeffnen(geheim, code=CODE)
    assert inhalt.code == CODE and inhalt.paket.fuer == "Max"
    datei = tmp_path / "paket.json"
    datei.write_bytes(geheim)
    inhalt = paket_oeffnen(datei, code=CODE, arbeit=tmp_path / "Import")
    assert inhalt.uebungen[0].name == "Übung für Max"


def test_app_merkt_sich_den_code_und_holt_updates(tmp_path) -> None:
    con = oeffnen(tmp_path / "app.db")
    pakete = PaketRepo(con)
    url = "https://x.org/pakete/p/7Hq3vX9aBcDeFgHiJkLmNo/paket.json"
    dateien = {url: verschluesseln(_paket(1), CODE)}

    geladen: list[str] = []

    def laden(adresse: str) -> bytes:
        geladen.append(adresse)
        if adresse not in dateien:
            raise urllib.error.URLError("HTTP 404")
        return dateien[adresse]

    with pytest.raises(ZugangNoetig):
        link_lesen(url, laden)
    art, (eintrag, inhalt) = link_lesen(url, laden, CODE)
    assert art == "paket" and eintrag.sha256 == hashlib.sha256(dateien[url]).hexdigest()
    pakete.importieren(inhalt)
    pakete.quelle_setzen(inhalt.paket.id, url, "datei")
    p = pakete.laden(inhalt.paket.id)
    assert p.privat and p.zugangscode == CODE and p.fuer == "Max"
    # Eine neue Fassung unter demselben Link: die Prüfung entschlüsselt mit dem gemerkten Code
    dateien[url] = verschluesseln(_paket(2, "Noch langsamer."), CODE)
    ergebnis = pruefen([], [pakete.laden(inhalt.paket.id)], laden)
    assert ergebnis.fehler == [] and [u.eintrag.version for u in ergebnis.updates] == [2]
    # Mit der Standdatei daneben (`trainingsapp-paket bauen` schreibt sie) fragt die Prüfung
    # nur sie — das Paket selbst wird erst für das Update geladen und gegen sie geprüft
    stand = stand_url(url)
    assert stand == "https://x.org/pakete/p/7Hq3vX9aBcDeFgHiJkLmNo/paket.stand.json"
    dateien[stand] = stand_json(2, hashlib.sha256(dateien[url]).hexdigest(), len(dateien[url]))
    geladen.clear()
    ergebnis = pruefen([], [pakete.laden(inhalt.paket.id)], laden)
    assert geladen == [stand] and [u.eintrag.version for u in ergebnis.updates] == [2]
    assert paket_laden(ergebnis.updates[0].eintrag, laden, CODE).paket.version == 2
    dateien[url] = verschluesseln(_paket(2, "Vertauscht."), CODE)  # passt nicht zur Standdatei
    with pytest.raises(QuellenFehler, match="Prüfsumme"):
        paket_laden(ergebnis.updates[0].eintrag, laden, CODE)
    con.close()


def test_werkzeug_baut_privat_und_laesst_es_aus_dem_index(tmp_path, capsys) -> None:
    from trainingsapp.paket_werkzeug import index, main

    toml = tmp_path / "max.toml"
    toml.write_text(
        '[paket]\nname = "Für Max"\nversion = "1.0.0"\n\n[privat]\nfuer = "Max"\n\n'
        '[[exercises]]\nkey = "a"\nname = "Übung für Max"\ndescription = "Langsam."\n',
        encoding="utf-8",
    )
    ziel = tmp_path / "dist"
    assert (
        main(["bauen", str(toml), "--ziel", str(ziel), "--basis-url", "https://x.org/pakete"]) == 0
    )
    ausgabe = capsys.readouterr().out
    zugang = json.loads((tmp_path / "max.zugang.json").read_text("utf-8"))
    pfad = ziel / "p" / zugang["ordner"] / "paket.json"
    assert pfad.is_file() and ist_privat(pfad.read_bytes())
    # Umgeleitet (CI, Protokoll) stehen weder Link noch Code in der Ausgabe — nur die Datei
    karte = tmp_path / "max.zugangskarte.txt"
    assert zugang["ordner"] not in ausgabe and code_text(zugang["code"]) not in ausgabe
    assert str(karte) in ausgabe
    assert f"Link: https://x.org/pakete/p/{zugang['ordner']}/paket.json" in karte.read_text("utf-8")
    assert code_text(zugang["code"]) in karte.read_text("utf-8")
    with pytest.raises(CodeNoetig):
        paket_oeffnen(pfad)
    assert paket_oeffnen(pfad, code=zugang["code"]).paket.fuer == "Max"
    # Die Standdatei daneben: Version, Prüfsumme und Größe der verschlüsselten Datei — sonst nichts
    stand = pfad.with_name("paket.stand.json")
    eintrag = stand_lesen(stand.read_bytes(), Paket(id="p", name="x", quelle="https://x/p.json"))
    assert eintrag is not None and eintrag.version == 10000
    assert eintrag.sha256 == hashlib.sha256(pfad.read_bytes()).hexdigest()
    assert eintrag.bytes == pfad.stat().st_size
    assert "Max" not in stand.read_text("utf-8")
    # Neue Fassung: derselbe Ordner, derselbe Code
    assert main(["bauen", str(toml), "--ziel", str(ziel)]) == 0
    assert json.loads((tmp_path / "max.zugang.json").read_text("utf-8")) == zugang
    # Nie im öffentlichen Index
    offen = tmp_path / "offen.json"
    offen.write_text(
        json.dumps({"paket": {"name": "Offen"}, "exercises": [{"name": "A"}]}), "utf-8"
    )
    assert [e["name"] for e in index([pfad, offen])["pakete"]] == ["Offen"]
    assert paket_lesen(json.loads(offen.read_text("utf-8"))).paket.name == "Offen"


def test_werkzeug_laesst_die_zugangsdatei_aus(tmp_path, capsys) -> None:
    """``pakete/*.json`` sammelt neben der TOML auch ``<name>.zugang.json`` ein
    (``veroeffentlichen.sh``, CI des Inhalte-Repos) — pruefen, bauen und index lassen sie aus,
    sonst bräche jede Veröffentlichung nach dem ersten privaten Paket ab."""
    from trainingsapp.paket_werkzeug import main

    toml = tmp_path / "max.toml"
    toml.write_text(
        '[paket]\nname = "Für Max"\nversion = "1.0.0"\n\n[privat]\nfuer = "Max"\n\n'
        '[[exercises]]\nkey = "a"\nname = "Übung für Max"\ndescription = "Langsam."\n',
        encoding="utf-8",
    )
    ziel = tmp_path / "dist"
    assert main(["bauen", str(toml), "--ziel", str(ziel)]) == 0
    zugang = tmp_path / "max.zugang.json"
    assert zugang.is_file()
    capsys.readouterr()
    assert main(["pruefen", str(zugang)]) == 0
    assert f"{zugang}: übersprungen" in capsys.readouterr().out
    assert main(["bauen", str(toml), str(zugang), "--ziel", str(ziel)]) == 0
    assert sorted(p.name for p in ziel.iterdir()) == ["p"]
    # Nur Privates: der Index ist leer, aber da (sonst fehlte er nach rsync --delete)
    assert main(["index", "--ziel", str(ziel / "index.json")]) == 0
    assert json.loads((ziel / "index.json").read_text("utf-8"))["pakete"] == []


def test_verfaelschter_kopf_ist_code_falsch() -> None:
    """Schlüsselparameter im Kopf, die mehr Speicher verlangen als erlaubt, sind eine
    verfälschte Datei — kein `ValueError`, der die Update-Prüfung abbricht."""
    geheim = bytearray(verschluesseln(b'{"paket": {"name": "T"}}', "K7QM9XA2"))
    geheim[8:11] = bytes([20, 16, 4])  # log₂N, r, p
    with pytest.raises(CodeFalsch):
        entschluesseln(bytes(geheim), "K7QM9XA2")
    with pytest.raises(PaketFehler, match="Code passt nicht"):
        paket_oeffnen(bytes(geheim), code="K7QM9XA2")


def test_klartext_bleibt_nicht_liegen(tmp_path) -> None:
    """Der Klartext eines privaten Pakets aus einer Datei liegt nur für den Import im
    Arbeitsordner: `klartext_aufraeumen` nimmt ihn weg, und ohne Paket darin bleibt er gar
    nicht erst."""
    from trainingsapp.core.paketdatei import klartext_aufraeumen
    from trainingsapp.core.privat import datei_verschluesseln

    arbeit = tmp_path / "Import"
    klar = tmp_path / "klar.json"
    klar.write_bytes(b'{"paket": {"name": "T"}, "exercises": [{"name": "A"}]}')
    datei = tmp_path / "paket.json"
    datei_verschluesseln(klar, datei, "K7QM9XA2")
    assert paket_oeffnen(datei, code="K7QM9XA2", arbeit=arbeit).paket.name == "T"
    assert [p.name[:9] for p in arbeit.iterdir()] == ["klartext_"]
    assert klartext_aufraeumen(arbeit) == 1 and not list(arbeit.iterdir())
    assert klartext_aufraeumen(tmp_path / "fehlt") == 0
    # Entschlüsselt, aber kein Paket darin: nichts bleibt
    klar.write_bytes(b"kein Paket")
    datei_verschluesseln(klar, datei, "K7QM9XA2")
    with pytest.raises(PaketFehler):
        paket_oeffnen(datei, code="K7QM9XA2", arbeit=arbeit)
    assert not list(arbeit.iterdir())
