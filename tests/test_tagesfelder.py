"""Tagesfelder (Ben, 21.10.2026, `docs/plan_tagesfelder.md`): `core/tagesfelder.py` und
`data/tagesfelder.py` — anlegen, schalten, umordnen, „einmal am Tag“ korrigiert statt
doppelt, mehrmals mit Uhrzeit, Rückgängig und die drei Wege beim Löschen."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core import varianten as var
from trainingsapp.core.models import Subject
from trainingsapp.core.verlauf import kennzahlen, linien
from trainingsapp.data.db import oeffnen, schema_version
from trainingsapp.data.repositories import SubjectRepo
from trainingsapp.data.tagesfelder import TagesfeldRepo, TageswertRepo

TAG = date(2026, 10, 21)


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    yield verbindung
    verbindung.close()


@pytest.fixture
def profil(con) -> Subject:
    s = Subject(name="Ich")
    SubjectRepo(con).speichern(s)
    return s


@pytest.fixture
def felder(con) -> TagesfeldRepo:
    return TagesfeldRepo(con)


@pytest.fixture
def werte(con) -> TageswertRepo:
    return TageswertRepo(con)


def _ibu(profil: Subject) -> tf.Tagesfeld:
    return tf.Tagesfeld(
        subject_id=profil.id,
        name="Ibu",
        spec=tf.spec_bauen(tf.ANZAHL, schnell=[1], varianten=["400", "800"]),
        mehrmals=True,
    )


def _um(stunde: int, minute: int = 0, tag: date = TAG) -> datetime:
    return datetime(tag.year, tag.month, tag.day, stunde, minute).astimezone(UTC)


def test_migration_legt_die_tabellen_an(con) -> None:
    assert schema_version(con) >= 27
    tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"day_field", "day_value"} <= tabellen


def test_anlegen_laden_reihenfolge(felder, profil) -> None:
    ibu = _ibu(profil)
    felder.speichern(ibu)
    schmerz = tf.Vorschlag("Schmerz", tf.SKALA).feld(profil.id)
    felder.speichern(schmerz)
    assert [f.name for f in felder.alle(profil.id)] == ["Ibu", "Schmerz"]
    zurueck = felder.laden(ibu.id)
    assert zurueck is not None
    assert zurueck.art == tf.ANZAHL
    assert zurueck.varianten == ["400", "800"]
    assert zurueck.mehrmals and zurueck.aktiv
    felder.umordnen([schmerz.id, ibu.id])
    assert [f.name for f in felder.alle(profil.id)] == ["Schmerz", "Ibu"]


def test_ausschalten_nimmt_nur_aus_heute(felder, werte, profil) -> None:
    ibu = _ibu(profil)
    felder.speichern(ibu)
    werte.hinzufuegen(ibu, TAG, _um(8), wert=1, variante="400")
    felder.schalten(ibu.id, False)
    assert felder.aktive(profil.id) == []
    assert [f.name for f in felder.alle(profil.id)] == ["Ibu"]
    assert len(werte.am_tag(profil.id, TAG)) == 1


def test_mehrmals_jeder_tipp_ein_wert(felder, werte, profil) -> None:
    ibu = _ibu(profil)
    felder.speichern(ibu)
    werte.hinzufuegen(ibu, TAG, _um(14, 30), wert=1, variante="400", note="nach dem Laufen")
    werte.hinzufuegen(ibu, TAG, _um(8, 10), wert=1, variante="400")
    am_tag = werte.am_tag(profil.id, TAG)
    assert [w.zeit.astimezone().strftime("%H:%M") for w in am_tag] == ["08:10", "14:30"]
    assert tf.stand_text(ibu, tf.tagesstand(ibu, am_tag)) == "400 × 2"
    assert tf.tageszeile(ibu, am_tag) == "Ibu 400 × 2"


def test_einmal_am_tag_korrigiert_statt_doppelt(felder, werte, profil) -> None:
    schmerz = tf.Tagesfeld(
        subject_id=profil.id,
        name="Schmerz",
        spec=tf.spec_bauen(tf.SKALA, varianten=["Knie", "Rücken"]),
    )
    felder.speichern(schmerz)
    erst = werte.einmal_setzen(schmerz, TAG, wert=5, variante="Knie", zeit=_um(8, 40))
    werte.einmal_setzen(schmerz, TAG, wert=3, variante="Knie")
    werte.einmal_setzen(schmerz, TAG, wert=2, variante="Rücken")
    am_tag = werte.am_tag(profil.id, TAG)
    assert sorted((w.variante, w.wert) for w in am_tag) == [("Knie", 3), ("Rücken", 2)]
    knie = next(w for w in am_tag if w.variante == "Knie")
    assert knie.ersetzt == erst.id  # Korrektur, nicht überschrieben
    assert knie.zeit == erst.zeit  # die alte Uhrzeit bleibt
    assert tf.stand_text(schmerz, tf.tagesstand(schmerz, am_tag)) == "Knie 3 · Rücken 2"


def test_rueckgaengig_holt_den_alten_wert(felder, werte, profil) -> None:
    trinken = tf.Vorschlag("Trinken", tf.MENGE, einheit="ml", schnell=(250,)).feld(profil.id)
    trinken.mehrmals = False
    felder.speichern(trinken)
    werte.einmal_setzen(trinken, TAG, wert=500)
    neu = werte.einmal_setzen(trinken, TAG, wert=tf.plus(trinken.spec, 500, 250))
    assert [w.wert for w in werte.am_tag(profil.id, TAG)] == [750]
    werte.rueckgaengig(neu.id)
    assert [w.wert for w in werte.am_tag(profil.id, TAG)] == [500]


def test_wert_loeschen_nimmt_die_kette(felder, werte, profil) -> None:
    schmerz = tf.Vorschlag("Schmerz", tf.SKALA).feld(profil.id)
    felder.speichern(schmerz)
    werte.einmal_setzen(schmerz, TAG, wert=5)
    neu = werte.einmal_setzen(schmerz, TAG, wert=3)
    werte.loeschen(neu.id)
    assert werte.am_tag(profil.id, TAG) == []


def test_loeschen_einträge_behalten(felder, werte, profil) -> None:
    ibu = _ibu(profil)
    felder.speichern(ibu)
    werte.hinzufuegen(ibu, TAG, _um(8), wert=1, variante="400")
    felder.loeschen(ibu.id, mit_werten=False)
    assert felder.alle(profil.id) == []
    assert [f.name for f in felder.alle(profil.id, mit_geloeschten=True)] == ["Ibu"]
    assert len(werte.zwischen(profil.id, None, None)) == 1  # bleibt im Verlauf


def test_loeschen_mit_werten_und_rueckgaengig(felder, werte, profil) -> None:
    ibu = _ibu(profil)
    felder.speichern(ibu)
    werte.hinzufuegen(ibu, TAG, _um(8), wert=1, variante="400")
    werte.hinzufuegen(ibu, TAG - timedelta(days=2), _um(9, tag=TAG - timedelta(days=2)), wert=1)
    assert werte.umfang(ibu.id) == (2, 2, TAG - timedelta(days=2))
    stempel = felder.loeschen(ibu.id, mit_werten=True)
    assert werte.zwischen(profil.id, None, None) == []
    felder.loeschen_rueckgaengig(ibu.id, stempel)
    assert len(werte.zwischen(profil.id, None, None)) == 2
    assert [f.name for f in felder.alle(profil.id)] == ["Ibu"]


def test_zwischen_und_tage_mit_werten(felder, werte, profil) -> None:
    ibu = _ibu(profil)
    felder.speichern(ibu)
    gestern = TAG - timedelta(days=1)
    werte.hinzufuegen(ibu, gestern, _um(21, tag=gestern), wert=1, variante="800")
    werte.hinzufuegen(ibu, TAG, _um(8), wert=1, variante="400")
    assert len(werte.zwischen(profil.id, TAG, TAG)) == 1
    assert len(werte.zwischen(profil.id, None, TAG, feld_ids=[ibu.id])) == 2
    assert werte.zwischen(profil.id, None, TAG, feld_ids=[]) == []
    assert werte.tage_mit_werten(profil.id, gestern, TAG) == {gestern, TAG}


def test_spec_kopie_bleibt_nach_aenderung(felder, werte, profil) -> None:
    """Ändert man das Feld (andere Varianten), zeigen alte Werte sich mit ihrer Kopie."""
    ibu = _ibu(profil)
    felder.speichern(ibu)
    werte.hinzufuegen(ibu, TAG, _um(8), wert=1, variante="400")
    ibu.spec = tf.mit_varianten(ibu.spec, ["200"])
    felder.speichern(ibu)
    (alt,) = werte.am_tag(profil.id, TAG)
    assert var.namen(alt.spec) == ["400", "800"]


def test_verlauf_rechnet_mit_den_werten(felder, werte, profil) -> None:
    ibu = _ibu(profil)
    felder.speichern(ibu)
    werte.hinzufuegen(ibu, TAG, _um(8), wert=1, variante="400")
    werte.hinzufuegen(ibu, TAG, _um(14), wert=1, variante="400")
    werte.hinzufuegen(ibu, TAG, _um(20), wert=1, variante="800")
    eintraege = tf.als_eintraege(werte.zwischen(profil.id, None, TAG))
    (k,) = kennzahlen([e for _, e in eintraege])
    assert [(x.variante, x.werte[0][1]) for x in linien(eintraege, k)] == [
        ("400", 2.0),
        ("800", 1.0),
    ]
    assert [
        (s.variante, tf.summe_text(ibu, s)) for s in tf.summen(ibu, werte.am_tag(profil.id, TAG))
    ] == [
        ("400", "2 Stück"),
        ("800", "1 Stück"),
    ]


def test_name_pruefen_gegen_vorhandene(felder, profil) -> None:
    felder.speichern(_ibu(profil))
    vorhandene = [f.name for f in felder.alle(profil.id)]
    with pytest.raises(ValueError, match="gibt es schon"):
        tf.name_pruefen("ibu", vorhandene)
    assert tf.name_pruefen("Ibu", vorhandene, bisher="Ibu") == "Ibu"


def test_profile_getrennt(felder, profil, con) -> None:
    anderes = Subject(name="Kind")
    SubjectRepo(con).speichern(anderes)
    felder.speichern(_ibu(profil))
    assert felder.alle(anderes.id) == []


def test_vorschlaege_sind_gueltig() -> None:
    for v in tf.VORSCHLAEGE:
        f = v.feld()
        assert f.art == v.art
        assert f.zusammenfassung()
