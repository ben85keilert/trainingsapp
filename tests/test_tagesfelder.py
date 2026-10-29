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


# ---------------------------------------------------------------------------
# Messwert, Tageswert, Standardfelder (Ben, 28.10.2026)
# ---------------------------------------------------------------------------


def _blutdruck(profil: Subject) -> tf.Tagesfeld:
    return next(v for v in tf.STANDARDFELDER if v.standard_key == "blutdruck").feld(profil.id)


def test_migration_032_tageswert_und_standard(con) -> None:
    assert schema_version(con) >= 32
    spalten = {r["name"] for r in con.execute("PRAGMA table_info(day_field)")}
    assert {"tageswert", "standard_key"} <= spalten


def test_messwert_eintragen_stand_und_tageswert(felder, werte, profil) -> None:
    bd = _blutdruck(profil)
    felder.speichern(bd)
    geladen = felder.laden(bd.id)
    assert geladen.art == tf.MESSWERT and geladen.standard_key == "blutdruck"
    assert geladen.tageswert == tf.TW_MITTEL and len(geladen.teile) == 3
    werte.hinzufuegen(bd, TAG, _um(8), wert=(128, 82, 70))
    werte.hinzufuegen(bd, TAG, _um(19), wert=(124, 80, None))
    liste = [w for w in werte.am_tag(profil.id, TAG) if w.feld_id == bd.id]
    assert [w.werte for w in liste] == [(128, 82, 70), (124, 80, None)]
    assert tf.eintrag_text("Blutdruck", liste[0]) == "Blutdruck 128/82 mmHg · 70 bpm"
    assert tf.eintrag_text("Blutdruck", liste[1]) == "Blutdruck 124/80 mmHg"
    (stand,) = tf.tagesstand(bd, liste)
    assert stand.wert == (126.0, 81.0, 70.0) and stand.anzahl == 2
    assert tf.stand_text(bd, [stand]) == "Ø 126/81 mmHg · 70 bpm · 2×"
    # Tageswert umstellen: Letzter des Tages
    bd.tageswert = tf.TW_LETZTER
    felder.speichern(bd)
    (stand,) = tf.tagesstand(felder.laden(bd.id), liste)
    assert stand.wert == (124.0, 80.0, 70.0)
    assert tf.stand_text(bd, [stand]) == "124/80 mmHg · 70 bpm · 2×"
    # Höchster je Teil — nicht die Messung mit dem höchsten ersten Teil
    bd.tageswert = tf.TW_MAX
    (stand,) = tf.tagesstand(bd, liste)
    assert stand.wert == (128.0, 82.0, 70.0)
    # Kacheln: Mittel der Tageswerte je Teil
    (s,) = tf.summen(bd, liste)
    assert s.teile[:2] == (128.0, 82.0) and tf.summe_text(bd, s).startswith("Ø 128/82")


def test_tageswert_bei_menge(felder, werte, profil) -> None:
    trinken = tf.Tagesfeld(
        subject_id=profil.id,
        name="Trinken",
        spec=tf.spec_bauen(tf.MENGE, einheit="ml"),
        mehrmals=True,
    )
    felder.speichern(trinken)
    for ml in (250, 500, 250):
        werte.hinzufuegen(trinken, TAG, _um(8), wert=ml)
    liste = werte.am_tag(profil.id, TAG)
    assert tf.tagesstand(trinken, liste)[0].wert == 1000.0
    trinken.tageswert = tf.TW_MAX
    assert tf.tagesstand(trinken, liste)[0].wert == 500.0
    trinken.tageswert = "unsinn"  # unbekannt: die Vorgabe der Art
    assert trinken.wirksamer_tageswert == tf.TW_SUMME


def test_null_ist_ein_wert(felder, werte, profil) -> None:
    kaffee = tf.Tagesfeld(subject_id=profil.id, name="Kaffee", spec=tf.spec_bauen(tf.ANZAHL))
    felder.speichern(kaffee)
    assert tf.wert_lesen(kaffee.spec, "0") == 0
    werte.einmal_setzen(kaffee, TAG, wert=0)
    (w,) = werte.am_tag(profil.id, TAG)
    assert w.wert == 0 and tf.stand_text(kaffee, tf.tagesstand(kaffee, [w])) == "0"
    assert tf.dauer_lesen("0") == 0.0


def test_standardfelder_je_profil_loeschen_und_wiederherstellen(felder, werte, con) -> None:
    profile = SubjectRepo(con)
    a, b = Subject(name="A"), Subject(name="B")
    profile.speichern(a)
    profile.speichern(b)
    assert [f.name for f in felder.standard_einspielen(a.id)] == [
        "Anstrengung (sRPE)",
        "Blutdruck",
        "Gewicht",
        "Ruhepuls",
        "Störung",
    ]
    assert felder.standard_einspielen(a.id) == []  # nichts doppelt
    assert felder.alle(b.id) == []  # je Profil
    alle = felder.alle(a.id)
    assert all(f.fest and not f.aktiv for f in alle)  # fest, ausgeschaltet angelegt
    bd = tf.standardfeld(alle, "blutdruck")
    werte.hinzufuegen(bd, TAG, _um(8), wert=(120, 80, None))
    # Feste Felder (Ben, 29.10.2026) lassen sich nicht löschen, nur ausschalten
    with pytest.raises(ValueError):
        felder.loeschen(bd.id, mit_werten=True)
    assert len(felder.alle(a.id)) == 5 and felder.standard_geloeschte(a.id) == []
    felder.schalten(bd.id, True)
    assert felder.laden(bd.id).aktiv
    # Nie angelegt (Profil B): Wiederherstellen legt an
    fehlend = felder.standard_geloeschte(b.id)
    assert [v.standard_key for v, zeile in fehlend] == [
        "srpe",
        "blutdruck",
        "gewicht",
        "ruhepuls",
        "stoerung",
    ] and all(zeile is None for _, zeile in fehlend)
    neu = felder.wiederherstellen(fehlend[1][0], b.id)
    assert neu.standard_key == "blutdruck" and neu.fest and felder.alle(b.id) == [neu]


def test_vorlagen_in_gruppen_und_messwert_lesen() -> None:
    gruppen = tf.vorlagen_in_gruppen()
    assert [g for g, _ in gruppen] == list(tf.GRUPPEN)
    assert all(v.gruppe for v in tf.VORLAGEN)
    bd = next(v for v in tf.VORLAGEN if v.name == "Blutdruck").feld()
    assert tf.messwert_lesen(bd.spec, ["128/82/70"]) == (128, 82, 70)
    assert tf.messwert_lesen(bd.spec, ["128", "82"]) == (128, 82, None)
    assert tf.messwert_lesen(bd.spec, ["500", "82"]) is None  # außerhalb 30–300
    assert tf.teile_lesen(bd.spec)[2].optional
    with pytest.raises(ValueError):
        tf.teile_pruefen([tf.Teil("a", "x", 10, 5)])
