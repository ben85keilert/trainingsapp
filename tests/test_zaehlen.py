"""`core.zaehlen`: die Karte „Beschleunigungssensor“ an der Übung (`SensorWahl`), ihre
Vorgaben und die Texte der Zählzeile (Ben, 4.11.2026, `docs/plan_beschleunigung.md` §3, §4)."""

from __future__ import annotations

import dataclasses
import json
import tomllib

import pytest
from hrv_core.geraete.treiber import treiber

from trainingsapp.core import zaehlen
from trainingsapp.core.models import Exercise, PlanItem
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
from trainingsapp.core.zaehlen import (
    EINGETRAGEN,
    ENDE_GRUENDE,
    SensorWahl,
    anzeige,
    atmung_an,
    hat_wdh_feld,
    knopf_text,
    korrektur_text,
    rate_waehlen,
    wdh_felder,
    wiederholungen_an,
    zaehlt_in,
)


def _uebung(*keys: str, typen: list[str] | None = None, **kw) -> Exercise:
    return Exercise(
        name="Kniebeuge",
        result_spec=ResultSpec(fields=[vorrat_feld(k) for k in keys]),
        typen=typen or [],
        **kw,
    )


# ---------------------------------------------------------------------------
# SensorWahl
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "wahl",
    [
        SensorWahl(),
        SensorWahl(wiederholungen=True),
        SensorWahl(wiederholungen=False, atmung=True),
        SensorWahl(atmung=False, vorlage="neigung_zy", feld="reps_2"),
    ],
)
def test_sensorwahl_rundreise_ueber_json_und_toml(wahl: SensorWahl) -> None:
    """Was `als_dict` schreibt, liest `aus_dict` gleich zurück — auch über JSON (Datenbank)
    und TOML (Paketdatei), denn ``None`` steht nie darin."""
    d = wahl.als_dict()
    assert None not in d.values()
    assert SensorWahl.aus_dict(json.loads(json.dumps(d))) == wahl
    toml = "x = {" + ", ".join(f"{k} = {json.dumps(v)}" for k, v in d.items()) + "}"
    assert SensorWahl.aus_dict(tomllib.loads(toml)["x"]) == wahl


def test_sensorwahl_schreibt_nur_abweichungen() -> None:
    assert SensorWahl().als_dict() == {}
    assert SensorWahl(vorlage="auto", feld=None).als_dict() == {}
    assert SensorWahl(wiederholungen=False).als_dict() == {"wiederholungen": False}
    assert SensorWahl(vorlage="kniebeuge_x").als_dict() == {"vorlage": "kniebeuge_x"}


@pytest.mark.parametrize(
    "roh",
    [None, "kaputt", 3, [], {"wiederholungen": "ja"}, {"atmung": 1}, {"vorlage": ""}, {"feld": 2}],
)
def test_sensorwahl_liest_unbrauchbares_als_vorgabe(roh) -> None:
    assert SensorWahl.aus_dict(roh) == SensorWahl()


def test_sensorwahl_ist_unveraenderlich_und_wird_beim_kopieren_nicht_geteilt() -> None:
    """`dataclasses.replace` kopiert flach („Kopie anlegen“, Paket entfernen mit Kopie) —
    eine veränderliche Wahl wäre zwischen Original und Kopie geteilt."""
    wahl = SensorWahl(atmung=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        wahl.atmung = False  # type: ignore[misc]
    u = _uebung("reps", beschleunigung=wahl)
    kopie = dataclasses.replace(u, id="kopie")
    kopie.beschleunigung = dataclasses.replace(kopie.beschleunigung, atmung=False)
    assert u.beschleunigung.atmung is True and kopie.beschleunigung.atmung is False


def test_uebung_hat_von_haus_aus_die_vorgabe() -> None:
    assert Exercise().beschleunigung == SensorWahl()
    assert Exercise().beschleunigung.als_dict() == {}


# ---------------------------------------------------------------------------
# Vorgaben aus der Übung
# ---------------------------------------------------------------------------


def test_wiederholungen_folgen_dem_feld_der_art_reps() -> None:
    """Vorgabe: an, wenn es ein Feld der Art ``reps`` gibt (auch ``reps_2``, P106) — ohne
    eins nie, auch nicht ausdrücklich eingeschaltet (der Schalter ist dann ausgegraut)."""
    assert hat_wdh_feld(_uebung("reps")) and wiederholungen_an(_uebung("reps"))
    assert hat_wdh_feld(_uebung("weight", "reps_2")) and wiederholungen_an(_uebung("reps_2"))
    assert not hat_wdh_feld(_uebung("hold")) and not wiederholungen_an(_uebung("hold"))
    assert not wiederholungen_an(_uebung("reps", beschleunigung=SensorWahl(wiederholungen=False)))
    assert not wiederholungen_an(_uebung("hold", beschleunigung=SensorWahl(wiederholungen=True)))


def test_atmung_folgt_dem_typ() -> None:
    """Vorgabe: an bei Typ „Atmung“ (groß/klein egal); in jeder Übung einschaltbar (P117)."""
    assert atmung_an(_uebung(typen=["Atmung", "Entspannung"]))
    assert atmung_an(_uebung(typen=["atmung"]))
    assert not atmung_an(_uebung("reps", typen=["Kräftigung"]))
    assert atmung_an(_uebung("reps", typen=["Kräftigung"], beschleunigung=SensorWahl(atmung=True)))
    assert not atmung_an(_uebung(typen=["Atmung"], beschleunigung=SensorWahl(atmung=False)))


def test_wdh_felder_und_zaehlt_in() -> None:
    u = _uebung("reps", "weight", "reps_2")
    assert wdh_felder(u) == ["reps", "reps_2"]
    assert zaehlt_in(u) == "reps"  # ohne Wahl das erste
    gewaehlt = dataclasses.replace(u, beschleunigung=SensorWahl(feld="reps_2"))
    assert zaehlt_in(gewaehlt) == "reps_2"
    # Ein Feld, das es nicht (mehr) gibt, fällt aufs erste zurück
    weg = dataclasses.replace(u, beschleunigung=SensorWahl(feld="reps_3"))
    assert zaehlt_in(weg) == "reps"
    assert wdh_felder(_uebung("hold")) == [] and zaehlt_in(_uebung("hold")) is None


def test_planuebung_zaehlt_in_ihre_aktiven_felder() -> None:
    """In der Planübung gelten die Felder, die sie anbietet (P79) — auch eins, das nur der
    Plan hat; bietet sie das gewählte nicht an, das erste, das sie anbietet."""
    u = _uebung("reps", "reps_2", beschleunigung=SensorWahl(feld="reps_2"))
    assert wdh_felder(u, PlanItem()) == ["reps", "reps_2"]  # folgt der Übung
    assert zaehlt_in(u, PlanItem()) == "reps_2"
    assert zaehlt_in(u, PlanItem(felder=["reps"])) == "reps"
    assert zaehlt_in(u, PlanItem(felder=[])) is None  # nur abhaken
    halten = _uebung("hold")
    assert zaehlt_in(halten, PlanItem(felder=["hold", "reps"])) == "reps"


# ---------------------------------------------------------------------------
# Texte und Zahlen der Zählzeile
# ---------------------------------------------------------------------------


def test_knopf_heisst_nie_bloss_zaehlen() -> None:
    assert knopf_text(True, False) == "Wdh. zählen"
    assert knopf_text(False, True) == "Atmung erfassen"
    assert knopf_text(True, True) == "Wdh. zählen · Atmung"
    assert knopf_text(False, False) == ""
    u = _uebung("reps", typen=["Atmung"])
    assert knopf_text(wiederholungen_an(u), atmung_an(u)) == "Wdh. zählen · Atmung"


def test_anzeige_und_korrektur() -> None:
    """Angezeigt und eingetragen wird Sensor plus Korrektur, nie weniger als 0 (§4.3)."""
    assert anzeige(11, 1) == 12
    assert anzeige(11, 0) == 11
    assert anzeige(1, -3) == 0
    assert anzeige(None, 1) == 1
    assert korrektur_text(11, 1) == "Sensor 11 · +1"
    assert korrektur_text(11, 0) == "Sensor 11"
    assert korrektur_text(11, -1) == "Sensor 11 · −1"
    assert korrektur_text(None, 0) == "Sensor …"


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------


def test_ende_gruende_und_grenzen() -> None:
    assert ENDE_GRUENDE == (
        "fertig",
        "abgehakt",
        "abbruch",
        "andere_uebung",
        "keine_bewegung",
        "kein_atem",
    )
    assert sorted(EINGETRAGEN) == ["abgehakt", "fertig"]
    assert EINGETRAGEN.issubset(ENDE_GRUENDE)
    assert zaehlen.KEINE_BEWEGUNG_S == 60.0 and zaehlen.KEIN_ATEM_S == 120.0
    assert zaehlen.MIN_RATE_HZ == 50 and zaehlen.BEREICH_G == 8


def test_rate_aus_dem_treiber() -> None:
    """Die kleinste Rate ab 50 Hz, die der Treiber in hrv-core nennt (H10 50, Verity 52)."""
    raten = {}
    for profil in ("polar_h10", "verity_sense"):
        t = treiber(profil)
        strom = t.strom("acc") if t is not None else None
        assert strom is not None, profil
        raten[profil] = rate_waehlen(strom.raten_hz)
    assert raten == {"polar_h10": 50, "verity_sense": 52}
    assert rate_waehlen([25]) == 50 and rate_waehlen([]) == 50
