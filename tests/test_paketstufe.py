"""Stufe eines Paket-Updates aus dem Unterschied (U6, Ben 9.11.2026, F8 c;
`docs/plan_paketversionen.md` §2): groß, mittel, klein — und das Werkzeug hält die Nummer
ehrlich (`trainingsapp-paket pruefen --gegen`)."""

from __future__ import annotations

import json

from trainingsapp.core.pakete import paket_lesen
from trainingsapp.core.paketstufe import GROSS, KEINE, KLEIN, MITTEL, automatisch, stufe


def _paket(**teile) -> dict:
    roh = {"paket": {"name": "Q", "version": teile.pop("version", 1)}}
    roh.update(teile)
    return roh


def _stufe(alt: dict, neu: dict) -> tuple[str, list[str]]:
    s = stufe(paket_lesen(alt), paket_lesen(neu))
    return s.stufe, s.gruende


def test_eingabe_felder_sind_mittel_chips_klein() -> None:
    def uebung(**f) -> dict:
        return {"key": "a", "name": "A", "description": "x", **f}

    wdh = {"fields": [{"key": "reps", "type": "set_list", "label": "Wdh."}]}
    wdh_chips = {"fields": [{"key": "reps", "type": "set_list", "label": "Wdh.", "quick": [5]}]}
    halten = {"fields": [{"key": "hold", "type": "set_list", "label": "Halten"}]}
    a = _paket(exercises=[uebung(result_spec=wdh)])
    assert _stufe(a, _paket(exercises=[uebung(result_spec=wdh_chips)]))[0] == KLEIN
    assert _stufe(a, _paket(exercises=[uebung(result_spec=halten)])) == (
        MITTEL,
        ["„A“: Felder der Eingabe"],
    )
    assert _stufe(a, _paket(exercises=[uebung(result_spec=wdh, icon_key="spa")]))[0] == KLEIN
    assert _stufe(a, a) == (KEINE, [])


def test_kapitel_am_ende_mittel_dazwischen_und_bedingung_gross() -> None:
    def kurs(*kapitel: dict, freischaltung: str = "rueckfrage") -> dict:
        return {"key": "k", "name": "K", "freischaltung": freischaltung, "kapitel": list(kapitel)}

    a1 = {"key": "a", "titel": "A", "text": "x"}
    b1 = {"key": "b", "titel": "B", "text": "y"}
    c1 = {"key": "c", "titel": "C", "text": "z"}
    alt = _paket(kurse=[kurs(a1, b1)])
    assert _stufe(alt, _paket(kurse=[kurs(a1, b1, c1)]))[0] == MITTEL  # ans Ende
    assert _stufe(alt, _paket(kurse=[kurs(a1, c1, b1)]))[0] == GROSS  # dazwischen
    assert _stufe(alt, _paket(kurse=[kurs(a1)]))[0] == GROSS  # fällt weg
    assert _stufe(alt, _paket(kurse=[kurs(b1, a1)]))[0] == GROSS  # wandert
    tage = {**b1, "bedingung": {"art": "tage", "soll": 3}}
    assert _stufe(alt, _paket(kurse=[kurs(a1, tage)])) == (
        GROSS,
        ["Kurs „K“, Kapitel „B“: Bedingung"],
    )
    assert _stufe(alt, _paket(kurse=[kurs(a1, {**b1, "text": "neu"})]))[0] == MITTEL


def test_plaene_und_ergaenzungen() -> None:
    ex = [{"key": "a", "name": "A", "description": "x"}]
    plan = {"key": "p", "name": "P", "uebungen": [{"uebung": "a"}]}
    alt = _paket(exercises=ex, plaene=[plan])
    assert _stufe(alt, _paket(exercises=ex))[0] == GROSS
    assert _stufe(alt, _paket(exercises=ex, plaene=[{**plan, "name": "P2"}]))[0] == MITTEL
    erg = {"uebung": "kniebeuge", "description": "## R\nr"}
    mit = _paket(exercises=ex, plaene=[plan], ergaenzungen=[erg])
    assert _stufe(alt, mit)[0] == MITTEL
    assert _stufe(mit, alt)[0] == GROSS
    ziel = _paket(exercises=ex, plaene=[plan], ergaenzungen=[{**erg, "default_target": {"r": 1}}])
    assert _stufe(mit, ziel)[0] == KLEIN


def test_modi() -> None:
    assert [automatisch("auto", s) for s in (KLEIN, MITTEL, GROSS)] == [True, True, False]
    assert [automatisch("klein", s) for s in (KLEIN, MITTEL, GROSS)] == [True, False, False]
    assert not automatisch("manuell", KEINE)


def test_werkzeug_prueft_gegen_die_veroeffentlichte_fassung(tmp_path) -> None:
    from trainingsapp.paket_werkzeug import gegen_pruefen

    alt = tmp_path / "alt.json"
    alt.write_text(
        json.dumps(
            _paket(
                version="1.4.0",
                exercises=[
                    {"key": "wandsitz", "name": "Wandsitz", "description": "x"},
                    {"key": "baum", "name": "Baum", "description": "y"},
                ],
            )
        ),
        "utf-8",
    )
    neu = tmp_path / "neu.json"

    def schreiben(version: str, exercises: list[dict]) -> None:
        neu.write_text(json.dumps(_paket(version=version, exercises=exercises)), "utf-8")

    baum = {"key": "baum", "name": "Baum", "description": "y"}
    schreiben("1.4.1", [baum])  # Wandsitz fällt weg — die Nummer reicht nicht
    fehler, _ = gegen_pruefen(neu, str(alt))
    assert fehler == ["große Änderung („Wandsitz“ fällt weg) → mindestens 2.0.0, steht 1.4.1"]
    schreiben("2.0.0", [baum])
    fehler, hinweise = gegen_pruefen(neu, str(alt))
    assert fehler == [] and hinweise == ["gegen 1.4.0: große Änderung („Wandsitz“ fällt weg)"]
