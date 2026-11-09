"""Private Pakete (U7, Ben 9.11.2026, F9, `docs/plan_paketinhalte.md` §11): verschlüsselt mit
einem Code, ohne ihn nicht zu lesen; die App merkt sich den Code, Updates aus dem Link öffnet
sie von selbst; das Werkzeug legt Ordner und Code einmal an und lässt private Pakete aus dem
Index."""

from __future__ import annotations

import hashlib
import json

import pytest

from trainingsapp.core.paketdatei import CodeNoetig, paket_oeffnen
from trainingsapp.core.pakete import PaketFehler, paket_lesen
from trainingsapp.core.paketquelle import ZugangNoetig, link_lesen, pruefen
from trainingsapp.core.privat import (
    CodeFalsch,
    code_neu,
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

    def laden(adresse: str) -> bytes:
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
    assert f"Link: https://x.org/pakete/p/{zugang['ordner']}/paket.json" in ausgabe
    assert (tmp_path / "max.zugangskarte.txt").is_file()
    with pytest.raises(CodeNoetig):
        paket_oeffnen(pfad)
    assert paket_oeffnen(pfad, code=zugang["code"]).paket.fuer == "Max"
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
