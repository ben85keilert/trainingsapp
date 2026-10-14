"""Übungspakete: Format (`core/pakete.py`), Import-Regeln (`data/pakete.py`), Seed.

Die Regeln stammen von Ben (14.10.2026): Ein Import aktualisiert die Übungen
desselben Pakets — eigene Änderungen daran gehen verloren, das ist gewollt.
Eigene Übungen ändert er nie; Übungen anderer Pakete und endgültig gelöschte
bleiben, wie sie sind.
"""

from __future__ import annotations

import json
import uuid

import pytest

from trainingsapp.core.models import Exercise, Media
from trainingsapp.core.pakete import (
    GRUNDAUSSTATTUNG,
    NAMENSRAUM,
    Paket,
    PaketFehler,
    paket_bauen,
    paket_id,
    paket_json,
    paket_lesen,
)
from trainingsapp.core.result_spec import SPEC_WINKEL
from trainingsapp.data.db import oeffnen
from trainingsapp.data.pakete import PaketRepo, Status
from trainingsapp.data.repositories import ExerciseRepo, TagRepo
from trainingsapp.data.seed import SEED_DATEI, seed_einspielen, seed_id, seed_inhalt


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    seed_einspielen(verbindung)
    yield verbindung
    verbindung.close()


def qigong(**aenderungen: object) -> dict:
    """Ein von Hand geschriebenes Paket: Schlüssel statt IDs, Tags in eigener Schreibweise."""
    uebungen = [
        {
            "key": "baum",
            "name": "Stehen wie ein Baum",
            "description": "Knie weich, Scheitel nach oben.",
            "typen": ["Qigong", "dehnung"],  # „dehnung“ gibt es schon als „Dehnung“
            "regionen": ["Meridiane"],
            "spec": "halten",
        },
        {
            "key": "baum_tief",
            "name": "Stehen wie ein Baum, tief",
            "typen": ["Qigong"],
            "spec": "halten",
            "variante_von": "baum",
        },
    ]
    roh = {"paket": {"name": "Qigong", "version": 1}, "exercises": uebungen}
    roh["paket"].update(aenderungen)
    return roh


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------


def test_grundausstattung_behaelt_die_ids_von_vor_den_paketen() -> None:
    """Sonst stünde jede mitgelieferte Übung nach dem Update doppelt da."""
    roh = json.loads(SEED_DATEI.read_text(encoding="utf-8"))
    inhalt = seed_inhalt()
    assert inhalt.paket.id == GRUNDAUSSTATTUNG == paket_id("Grundausstattung")
    assert inhalt.paket.name == "Grundausstattung"
    erwartet = [str(uuid.uuid5(NAMENSRAUM, e["key"])) for e in roh["exercises"]]
    assert [u.id for u in inhalt.uebungen] == erwartet
    assert all(u.package_id == GRUNDAUSSTATTUNG and u.is_builtin for u in inhalt.uebungen)


def test_schluessel_und_variante_werden_zu_ids() -> None:
    inhalt = paket_lesen(qigong())
    baum, tief = inhalt.uebungen
    assert inhalt.paket.id == paket_id("Qigong")
    assert baum.id != seed_id("baum")  # eigener Namensraum je Paket
    assert tief.family_id == baum.id
    assert baum.result_spec.fields[0].key == "hold"


@pytest.mark.parametrize(
    ("daten", "meldung"),
    [
        (b"kein json", "kein JSON"),
        (b"[]", "keine Paketdatei"),
        (b'{"format": "raw-v1", "exercises": []}', "keine Paketdatei"),
        (b'{"version": 99, "paket": {"name": "X"}, "exercises": [{"name": "A"}]}', "neuer"),
        (b'{"paket": {"name": "X"}, "exercises": []}', "keine Übungen"),
        (b'{"paket": {"name": "X"}, "exercises": [{"description": "ohne Namen"}]}', "Name"),
        (b'{"paket": {"name": "X"}, "exercises": [{"name": "A", "spec": "?"}]}', "Eingabe"),
        (b'{"paket": {"name": "Eigene"}, "exercises": [{"name": "A"}]}', "kein Paketname"),
        (b'{"paket": {"name": "X"}, "exercises": [{"name": "A"}, {"name": "A"}]}', "doppelt"),
    ],
)
def test_kaputte_dateien_melden_sich_verstaendlich(daten: bytes, meldung: str) -> None:
    with pytest.raises(PaketFehler, match=meldung):
        paket_lesen(daten)


def test_name_aus_dem_dateinamen_wenn_der_kopf_fehlt() -> None:
    inhalt = paket_lesen(b'{"exercises": [{"name": "A"}]}', name_vorgabe="yoga_morgens")
    assert inhalt.paket.name == "yoga_morgens"


# ---------------------------------------------------------------------------
# Seed = Paket „Grundausstattung“
# ---------------------------------------------------------------------------


def test_seed_installiert_die_grundausstattung(con) -> None:
    pakete = PaketRepo(con).alle()
    assert [(p.name, n) for p, n in pakete] == [("Grundausstattung", len(seed_inhalt().uebungen))]
    assert all(u.package_id == GRUNDAUSSTATTUNG for u in ExerciseRepo(con).alle())


def test_herkunft_wird_fuer_alte_datenbanken_nachgetragen(con) -> None:
    """Stand vor Migration 014: Übungen ohne Paket — Änderungen daran bleiben."""
    repo = ExerciseRepo(con)
    u = repo.laden(seed_id("wadenheben"))
    u.description = "Meine Fassung"
    repo.speichern(u)
    con.execute("UPDATE exercise SET package_id = NULL")
    con.execute("DELETE FROM package")

    assert seed_einspielen(con) == 0
    u = repo.laden(seed_id("wadenheben"))
    assert u.package_id == GRUNDAUSSTATTUNG
    assert u.description == "Meine Fassung"  # erste Registrierung ist kein Update


def test_hoehere_version_aktualisiert_die_grundausstattung(con, tmp_path) -> None:
    """Paket-Update überschreibt Änderungen (Ben: erstmal erwünscht) — gleiche Version nicht."""
    repo = ExerciseRepo(con)
    u = repo.laden(seed_id("wadenheben"))
    u.description = "Meine Fassung"
    repo.speichern(u)

    roh = json.loads(SEED_DATEI.read_text(encoding="utf-8"))
    datei = tmp_path / "exercises.json"
    datei.write_text(json.dumps(roh), encoding="utf-8")
    seed_einspielen(con, datei)
    assert repo.laden(u.id).description == "Meine Fassung"

    roh["paket"]["version"] += 1
    datei.write_text(json.dumps(roh), encoding="utf-8")
    seed_einspielen(con, datei)
    assert repo.laden(u.id).description != "Meine Fassung"
    assert PaketRepo(con).laden(GRUNDAUSSTATTUNG).version == roh["paket"]["version"]


def test_seed_holt_endgueltig_geloeschte_nicht_zurueck(con) -> None:
    repo = ExerciseRepo(con)
    repo.in_papierkorb(seed_id("wadenheben"))
    repo.endgueltig_loeschen(seed_id("wadenheben"))
    assert seed_einspielen(con) == 0
    assert repo.laden(seed_id("wadenheben")) is None


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def test_import_legt_an_und_ergaenzt_tags(con) -> None:
    pakete = PaketRepo(con)
    inhalt = paket_lesen(qigong())
    vorschau = pakete.vorschau(inhalt)
    assert vorschau.anzahl(Status.NEU) == 2
    assert vorschau.neue_typen == ["Qigong"]
    assert vorschau.neue_regionen == ["Meridiane"]
    assert vorschau.zusammenfassung()[0] == "2 neu"

    pakete.importieren(inhalt)
    baum = ExerciseRepo(con).laden(inhalt.uebungen[0].id)
    assert baum.package_id == inhalt.paket.id
    assert baum.typen == ["Qigong", "Dehnung"]  # vorhandene Schreibweise
    assert baum.regionen == ["Meridiane"]
    assert ExerciseRepo(con).laden(inhalt.uebungen[1].id).family_id == baum.id
    assert "Qigong" in TagRepo(con).namen("typ")
    assert ("Qigong", 2) in [(p.name, n) for p, n in pakete.alle()]


def test_erneuter_import_ohne_aenderung_schreibt_nichts(con) -> None:
    pakete = PaketRepo(con)
    pakete.importieren(paket_lesen(qigong()))
    revision = con.execute("SELECT SUM(revision) FROM exercise").fetchone()[0]

    vorschau = pakete.importieren(paket_lesen(qigong()))
    assert vorschau.anzahl(Status.UNVERAENDERT) == 2
    assert not vorschau.zu_tun
    assert con.execute("SELECT SUM(revision) FROM exercise").fetchone()[0] == revision


def test_update_ueberschreibt_aenderungen_und_laesst_den_ort(con) -> None:
    """Archiv und Papierkorb bleiben, der Inhalt kommt aus dem Paket."""
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    baum, tief = (repo.laden(u.id) for u in inhalt.uebungen)
    baum.description = "Meine Notiz"
    baum.archived = True
    repo.speichern(baum)
    repo.in_papierkorb(tief.id)

    vorschau = pakete.importieren(paket_lesen(qigong(version=2)))
    assert vorschau.anzahl(Status.GEAENDERT) == 1  # nur „baum“ weicht ab
    baum = repo.laden(baum.id)
    assert baum.description == "Knie weich, Scheitel nach oben."
    assert baum.archived
    assert repo.laden(tief.id) is None  # weiter im Papierkorb
    assert pakete.laden(inhalt.paket.id).version == 2


def test_eigene_uebungen_aendert_kein_import(con) -> None:
    """Der eigene Export, wieder eingelesen: nichts passiert, kein Paket entsteht."""
    repo = ExerciseRepo(con)
    eigene = Exercise(name="Wandsitz 45°", typen=["Kräftigung"], result_spec=SPEC_WINKEL)
    repo.speichern(eigene)
    datei = paket_json(Paket(id=paket_id("Meins"), name="Meins"), [eigene])
    eigene.description = "seither geändert"
    repo.speichern(eigene)

    pakete = PaketRepo(con)
    vorschau = pakete.importieren(paket_lesen(datei))
    assert vorschau.status == {eigene.id: Status.EIGENE}
    assert repo.laden(eigene.id).description == "seither geändert"
    assert repo.laden(eigene.id).package_id is None
    assert [p.name for p, _ in pakete.alle()] == ["Grundausstattung"]


def test_fremde_und_geloeschte_bleiben(con) -> None:
    """Eine Übung der Grundausstattung in einem anderen Paket: gehört weiter ihrem Paket."""
    repo = ExerciseRepo(con)
    wade = repo.laden(seed_id("wadenheben"))
    nacken = repo.laden(seed_id("nacken_dehnung"))
    repo.in_papierkorb(nacken.id)
    repo.endgueltig_loeschen(nacken.id)
    wade.description = "anders"
    roh = paket_bauen(Paket(id="p", name="Auswahl"), [wade, nacken])

    vorschau = PaketRepo(con).importieren(paket_lesen(roh))
    assert vorschau.status == {wade.id: Status.FREMD, nacken.id: Status.GELOESCHT}
    assert repo.laden(wade.id).package_id == GRUNDAUSSTATTUNG
    assert repo.laden(wade.id).description != "anders"
    assert repo.laden(nacken.id) is None


def test_varianten_ohne_ketten(con) -> None:
    """A → B → C im Paket wird A → C und B → C; ein Original bleibt Original."""
    roh = {
        "paket": {"name": "Kette"},
        "exercises": [
            {"key": "a", "name": "A", "variante_von": "b"},
            {"key": "b", "name": "B", "variante_von": "c"},
            {"key": "c", "name": "C"},
        ],
    }
    inhalt = paket_lesen(roh)
    PaketRepo(con).importieren(inhalt)
    a, b, c = (ExerciseRepo(con).laden(u.id) for u in inhalt.uebungen)
    assert (a.family_id, b.family_id, c.family_id) == (c.id, c.id, None)


# ---------------------------------------------------------------------------
# Export → Import auf einem anderen Gerät
# ---------------------------------------------------------------------------


def test_export_und_import_auf_einem_anderen_geraet(con, tmp_path) -> None:
    repo = ExerciseRepo(con)
    original = Exercise(
        name="Wandsitz 90°",
        description="Rücken an der Wand.",
        typen=["Kräftigung", "Isometrie"],
        regionen=["Bein"],
        result_spec=SPEC_WINKEL,
        default_target={"angle": 90},
        default_felder=[],
        media=[Media(uri="https://example.org/wandsitz", title="Video")],
    )
    repo.speichern(original)
    variante = Exercise(name="Wandsitz 45°", family_id=original.id, typen=["Kräftigung"])
    repo.speichern(variante)
    datei = paket_json(Paket(id=paket_id("Beine"), name="Beine"), [original, variante])

    anderes = oeffnen(tmp_path / "anderes.db")
    seed_einspielen(anderes)
    PaketRepo(anderes).importieren(paket_lesen(datei))
    da = ExerciseRepo(anderes).laden(original.id)
    assert (da.name, da.description, da.typen, da.regionen) == (
        "Wandsitz 90°",
        "Rücken an der Wand.",
        ["Kräftigung", "Isometrie"],
        ["Bein"],
    )
    assert da.result_spec.to_dict() == SPEC_WINKEL.to_dict()
    assert (da.default_target, da.default_felder) == ({"angle": 90}, [])
    assert [(m.uri, m.title) for m in da.media] == [("https://example.org/wandsitz", "Video")]
    assert da.package_id == paket_id("Beine")
    assert ExerciseRepo(anderes).laden(variante.id).family_id == original.id
    # Nur Übungen — keine Einträge, Profile, Messungen oder Strecken
    assert set(json.loads(datei)) == {"format", "version", "paket", "exportiert", "exercises"}
    anderes.close()


# ---------------------------------------------------------------------------
# Paketmanager: Paketstand, Auf Paketstand setzen, Entfernen, Wieder installieren
# ---------------------------------------------------------------------------


def test_import_merkt_sich_den_paketstand(con) -> None:
    pakete = PaketRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    baum = ExerciseRepo(con).laden(inhalt.uebungen[0].id)
    assert pakete.standard(baum.id)["description"] == "Knie weich, Scheitel nach oben."
    assert pakete.standard(baum.id)["typen"] == ["Qigong", "Dehnung"]  # wie hier geschrieben
    assert pakete.abweichungen(baum) == []
    assert pakete.abweichungen(Exercise(name="eigene")) is None


def test_auf_standard_setzen(con) -> None:
    """Ben: In den Übungen sind die Standardwerte aus dem Paket vorhanden."""
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    pakete.importieren(paket_lesen(qigong()))
    baum = repo.laden(paket_lesen(qigong()).uebungen[0].id)
    baum.description = "Meine Fassung"
    baum.result_spec.fields[0].quick = [5]
    baum.default_target = {"hold": [60]}
    baum.archived = True
    repo.speichern(baum)
    assert pakete.abweichungen(repo.laden(baum.id)) == ["Beschreibung", "Parameter", "Ziel"]

    assert pakete.zuruecksetzen([baum.id]) == 1
    baum = repo.laden(baum.id)
    assert baum.description == "Knie weich, Scheitel nach oben."
    assert baum.result_spec.fields[0].quick == [15, 30, 45, 60]
    assert baum.default_target == {}
    assert baum.archived  # der Ort bleibt
    assert pakete.abweichungen(baum) == []
    assert pakete.zuruecksetzen([baum.id]) == 0  # nichts mehr zu tun


def test_grundausstattung_hat_ihren_paketstand(con) -> None:
    """Jeder Start frischt ihn auf — auch Datenbanken von vor Migration 015."""
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    con.execute("UPDATE exercise SET package_standard_json = NULL")
    seed_einspielen(con)
    wade = repo.laden(seed_id("wadenheben"))
    assert pakete.abweichungen(wade) == []
    original = wade.description
    wade.description = "Meine Fassung"
    repo.speichern(wade)
    assert pakete.abweichungen(repo.laden(wade.id)) == ["Beschreibung"]
    assert pakete.zuruecksetzen([wade.id]) == 1
    assert repo.laden(wade.id).description == original


def test_eigene_uebungen_haben_keinen_paketstand(con) -> None:
    pakete = PaketRepo(con)
    eigene = Exercise(name="Meine")
    ExerciseRepo(con).speichern(eigene)
    assert pakete.standard(eigene.id) is None
    assert pakete.zuruecksetzen([eigene.id]) == 0


def test_entfernen_und_wieder_installieren(con) -> None:
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    baum, tief = inhalt.uebungen

    assert pakete.entfernen(inhalt.paket.id) == 2
    assert [p.name for p, _ in pakete.alle()] == ["Grundausstattung"]
    assert [(p.name, n) for p, n in pakete.entfernte()] == [("Qigong", 2)]
    assert repo.laden(baum.id) is None  # im Papierkorb
    assert {u.id for u in repo.papierkorb()} >= {baum.id, tief.id}

    # Ohne Datei: aus dem Paketstand der Übungen
    zurueck = pakete.inhalt(inhalt.paket.id)
    vorschau = pakete.vorschau(zurueck)
    assert vorschau.entfernt is not None and vorschau.installiert is None
    assert vorschau.anzahl(Status.ZURUECK) == 2
    pakete.importieren(zurueck)
    assert repo.laden(baum.id) is not None
    assert repo.laden(tief.id).family_id == baum.id
    assert [p.name for p, _ in pakete.alle()] == ["Grundausstattung", "Qigong"]
    assert pakete.entfernte() == []


def test_wieder_installieren_holt_auch_endgueltig_geloeschte(con) -> None:
    """Der Papierkorb leert sich nach 30 Tagen — danach muss das Paket trotzdem zurückkommen."""
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    baum = inhalt.uebungen[0]
    pakete.entfernen(inhalt.paket.id)
    repo.endgueltig_loeschen(baum.id)
    assert con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (baum.id,)).fetchone()

    vorschau = pakete.importieren(paket_lesen(qigong()))  # neuer Import der Datei
    assert vorschau.status[baum.id] == Status.ZURUECK
    assert repo.laden(baum.id).description == "Knie weich, Scheitel nach oben."
    assert not con.execute("SELECT 1 FROM tombstone WHERE entity_id = ?", (baum.id,)).fetchone()


def test_entfernte_grundausstattung_kommt_beim_start_nicht_zurueck(con) -> None:
    pakete = PaketRepo(con)
    n = pakete.entfernen(GRUNDAUSSTATTUNG)
    assert n == len(seed_inhalt().uebungen)
    assert seed_einspielen(con) == 0
    assert ExerciseRepo(con).alle() == []
    assert pakete.alle() == []

    pakete.importieren(pakete.inhalt(GRUNDAUSSTATTUNG))  # „Wieder installieren“
    assert len(ExerciseRepo(con).alle()) == n
