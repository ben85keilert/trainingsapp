"""Übungspakete: Format (`core/pakete.py`), Import-Regeln (`data/pakete.py`), Seed.

Die Regeln stammen von Ben (14.10.2026): Ein Import aktualisiert die Übungen
desselben Pakets — eigene Änderungen daran gehen verloren, das ist gewollt.
Eigene Übungen ändert er nie; Übungen anderer Pakete und endgültig gelöschte
bleiben, wie sie sind.
"""

from __future__ import annotations

import json
import re
import tomllib
import uuid

import pytest

from trainingsapp.core.models import (
    TAG_REGION,
    TAG_TYP,
    Exercise,
    Media,
    MediaKind,
    MediaSource,
    Plan,
    PlanItem,
)
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
from trainingsapp.data.kurse import KursRepo
from trainingsapp.data.pakete import PaketRepo, Status
from trainingsapp.data.repositories import ExerciseRepo, PlanRepo, TagRepo
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
    """Sonst stünde jede mitgelieferte Übung nach dem Update doppelt da.

    Das Paket heißt seit 14.10.2026 „Standard“; ID und Übungs-IDs sind die von
    „Grundausstattung“ geblieben.
    """
    roh = tomllib.loads(SEED_DATEI.read_text(encoding="utf-8"))
    inhalt = seed_inhalt()
    assert inhalt.paket.id == GRUNDAUSSTATTUNG == paket_id("Grundausstattung")
    assert inhalt.paket.name == "Standard"
    erwartet = [str(uuid.uuid5(NAMENSRAUM, e["key"])) for e in roh["exercises"]]
    assert [u.id for u in inhalt.uebungen] == erwartet
    assert all(u.package_id == GRUNDAUSSTATTUNG and u.is_builtin for u in inhalt.uebungen)


#: Typen und Regionen, die das Standardpaket verwenden darf — ein Tippfehler
#: („Kraeftigung“) legte sonst auf jedem Gerät einen neuen Tag an. Neuer Tag
#: gewollt? Hier ergänzen und in der Kopfzeile von standard.toml.
STANDARD_TYPEN = {
    "Atmung", "Entspannung", "HRV", "Mobilisation", "Dehnung", "Kräftigung",
    "Isometrie", "Gleichgewicht", "Ausdauer", "Benchmark", "Messung",
}  # fmt: skip
STANDARD_REGIONEN = {"Nacken", "Schulter", "Arm", "Hand", "Rumpf", "Rücken", "Hüfte", "Bein", "Fuß"}


def test_standardpaket_ist_sauber_gepflegt() -> None:
    """Die Paketdatei wird von Hand gepflegt — hier fallen Tippfehler auf."""
    eintraege = tomllib.loads(SEED_DATEI.read_text(encoding="utf-8"))["exercises"]
    keys = [e.get("key", "") for e in eintraege]
    assert all(re.fullmatch(r"[a-z0-9_]+", k) for k in keys), "key fehlt oder hat Umlaute"
    assert len(keys) == len(set(keys)), "key doppelt"
    for e in eintraege:
        wo = f"Übung „{e['name']}“"
        assert e.get("description"), f"{wo}: Beschreibung fehlt"
        assert set(e.get("typen", [])) <= STANDARD_TYPEN, f"{wo}: unbekannter Typ"
        assert set(e.get("regionen", [])) <= STANDARD_REGIONEN, f"{wo}: unbekannte Region"
        assert e.get("variante_von", keys[0]) in keys, f"{wo}: Original fehlt"
    assert len(seed_inhalt().uebungen) == len(eintraege)  # liest sich auch fehlerfrei


def test_standardpaket_symbole_sind_bekannt() -> None:
    """Jedes ``icon_key`` steht in der kuratierten Auswahl — braucht flet (nicht in der CI)."""
    pytest.importorskip("flet")
    from trainingsapp.ui.components.icons import AUSWAHL

    eintraege = tomllib.loads(SEED_DATEI.read_text(encoding="utf-8"))["exercises"]
    for e in eintraege:
        assert e.get("icon_key") in AUSWAHL, (
            f"Übung „{e['name']}“: Symbol {e.get('icon_key')!r} unbekannt"
        )


def test_tippfehler_im_toml_nennt_die_zeile(tmp_path) -> None:
    datei = tmp_path / "kaputt.toml"
    datei.write_text('[paket]\nname = "X"\n\n[[exercises]]\nname = "A\n', encoding="utf-8")
    with pytest.raises(PaketFehler, match=r"kaputt\.toml: .*line 5"):
        seed_inhalt(datei)


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
# Seed = Paket „Standard“
# ---------------------------------------------------------------------------


def test_seed_installiert_die_grundausstattung(con) -> None:
    pakete = PaketRepo(con).alle()
    assert [(p.name, n) for p, n in pakete] == [("Standard", len(seed_inhalt().uebungen))]
    assert all(u.package_id == GRUNDAUSSTATTUNG for u in ExerciseRepo(con).alle())


def test_herkunft_wird_fuer_alte_datenbanken_nachgetragen(con) -> None:
    """Stand vor Migration 014: Übungen ohne Paket — Änderungen daran bleiben."""
    repo = ExerciseRepo(con)
    u = repo.laden(seed_id("wadenheben"))
    u.description = "Meine Fassung"
    repo.speichern(u)
    con.execute("UPDATE exercise SET package_id = NULL")
    con.execute("DELETE FROM course")  # Kurse gab es damals auch nicht
    con.execute("DELETE FROM package")

    assert seed_einspielen(con) == 0
    u = repo.laden(seed_id("wadenheben"))
    assert u.package_id == GRUNDAUSSTATTUNG
    assert u.description == "Meine Fassung"  # erste Registrierung ist kein Update


def test_hoehere_version_aktualisiert_die_grundausstattung(con, tmp_path) -> None:
    """Paket-Update bringt neue Paketfelder, lässt Geändertes stehen — gleiche Version nichts."""
    repo = ExerciseRepo(con)
    pakete = PaketRepo(con)
    u = repo.laden(seed_id("wadenheben"))
    u.description = "Meine Fassung"
    repo.speichern(u)

    roh = tomllib.loads(SEED_DATEI.read_text(encoding="utf-8"))
    datei = tmp_path / "exercises.json"
    datei.write_text(json.dumps(roh), encoding="utf-8")
    seed_einspielen(con, datei)
    assert repo.laden(u.id).description == "Meine Fassung"

    roh["paket"]["version"] += 1
    wade = next(e for e in roh["exercises"] if e["key"] == "wadenheben")
    wade["description"] = "Neu im Paket"
    wade["name"] = "Wadenheben (neu)"
    datei.write_text(json.dumps(roh), encoding="utf-8")
    seed_einspielen(con, datei)
    u = repo.laden(u.id)
    assert u.description == "Meine Fassung"  # selbst geändert: bleibt
    assert u.name == "Wadenheben (neu)"  # nie angefasst: neuer Paketstand
    assert pakete.standard(u.id)["description"] == "Neu im Paket"  # „Auf Paketstand“ holt es
    assert pakete.abweichungen(u) == ["Beschreibung"]
    assert pakete.laden(GRUNDAUSSTATTUNG).version == roh["paket"]["version"]


def test_seed_laesst_neuere_installation_stehen(con) -> None:
    """K6: „Standard“ kam in höherer Version aus einer Quelle — der Start ändert nichts.

    Sonst setzte er Version und Beschreibung zurück, hielte, was nur die Quelle kennt, für
    entfallen und holte zurück, was dort gestrichen ist; die Quelle spielte es wieder ein.
    """
    pakete = PaketRepo(con)
    roh = tomllib.loads(SEED_DATEI.read_text(encoding="utf-8"))
    roh["paket"]["version"] += 1
    roh["paket"]["beschreibung"] = "Aus der Quelle"
    roh["exercises"] = [e for e in roh["exercises"] if e["key"] != "wadenheben"]
    roh["exercises"].append({"key": "nur_in_der_quelle", "name": "Nur in der Quelle"})
    pakete.importieren(paket_lesen(roh))
    assert [u.id for u in pakete.entfallene(GRUNDAUSSTATTUNG)] == [seed_id("wadenheben")]

    assert seed_einspielen(con) == 0
    paket = pakete.laden(GRUNDAUSSTATTUNG)
    assert (paket.version, paket.beschreibung) == (roh["paket"]["version"], "Aus der Quelle")
    assert [u.id for u in pakete.entfallene(GRUNDAUSSTATTUNG)] == [seed_id("wadenheben")]


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


def test_update_behaelt_aenderungen_und_laesst_den_ort(con) -> None:
    """Drei-Wege-Abgleich (Ben, 16.10.2026): Geändertes bleibt, der Rest kommt aus dem
    Paket; Archiv und Papierkorb bleiben; der Paketstand ist danach der neue."""
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    baum, tief = (repo.laden(u.id) for u in inhalt.uebungen)
    baum.description = "Meine Notiz"
    baum.archived = True
    repo.speichern(baum)
    repo.in_papierkorb(tief.id)

    # Gleiches Paket, nur die Version höher: an „baum“ ist nichts Neues → nichts zu schreiben
    vorschau = pakete.importieren(paket_lesen(qigong(version=2)))
    assert vorschau.anzahl(Status.GEAENDERT) == 0
    assert vorschau.anzahl(Status.UNVERAENDERT) == 2
    assert repo.laden(baum.id).description == "Meine Notiz"
    assert pakete.laden(inhalt.paket.id).version == 2

    # Das Paket ändert Beschreibung (von mir geändert → bleibt) und Regionen (nie angefasst → neu)
    roh = qigong(version=3)
    roh["exercises"][0]["description"] = "Neu aus dem Paket"
    roh["exercises"][0]["regionen"] = ["Meridiane", "Rumpf"]
    vorschau = pakete.importieren(paket_lesen(roh))
    assert vorschau.anzahl(Status.GEAENDERT) == 1  # nur „baum“ bekommt etwas
    baum = repo.laden(baum.id)
    assert baum.description == "Meine Notiz"
    assert baum.regionen == ["Meridiane", "Rumpf"]
    assert baum.archived
    assert pakete.abweichungen(baum) == ["Beschreibung"]  # „Auf Paketstand“ holt die neue
    assert pakete.zuruecksetzen([baum.id]) == 1
    assert repo.laden(baum.id).description == "Neu aus dem Paket"
    assert repo.laden(tief.id) is None  # weiter im Papierkorb


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
    assert [p.name for p, _ in pakete.alle()] == ["Standard"]


def test_fremde_und_geloeschte_bleiben(con) -> None:
    """Eine Übung aus „Standard“ in einem anderen Paket: gehört weiter ihrem Paket."""
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
    assert da.default_target == {"angle": 90}
    # „default_felder“ entfällt (P79, C2): kein Feld mehr im Export, ein altes wird überlesen
    assert b"default_felder" not in datei
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
    assert [p.name for p, _ in pakete.alle()] == ["Standard"]
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
    assert [p.name for p, _ in pakete.alle()] == ["Standard", "Qigong"]
    assert pakete.entfernte() == []


def test_entfernen_nimmt_uebungen_aus_plaenen_oder_kopiert_sie(con) -> None:
    """Ben, 15.10.2026: Paket entfernen nimmt die Übungen aus den Plänen; wer sie behalten
    will, kopiert sie — die Kopie ist eine eigene Übung und übernimmt die Planposition."""
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    plaene = PlanRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    baum, tief = inhalt.uebungen
    plan = Plan(
        name="Morgens", items=[PlanItem(exercise_id=baum.id), PlanItem(exercise_id=tief.id)]
    )
    plaene.speichern(plan)
    verwendungen = pakete.verwendungen(inhalt.paket.id)
    assert [(p.name, u.id) for p, _i, u in verwendungen] == [
        ("Morgens", baum.id),
        ("Morgens", tief.id),
    ]

    assert pakete.entfernen(inhalt.paket.id, kopieren={baum.id}) == 2
    geladen = plaene.laden(plan.id)
    assert len(geladen.items) == 1  # „tief" ist raus, „baum" lebt als Kopie weiter
    kopie = repo.laden(geladen.items[0].exercise_id)
    assert kopie is not None and kopie.id != baum.id
    assert kopie.name == baum.name and kopie.package_id is None and kopie.family_id == baum.id
    assert pakete.standard(kopie.id) is None  # eigene Übung, kein Paketstand
    assert repo.laden(baum.id) is None  # das Original liegt im Papierkorb
    assert pakete.verwendungen(inhalt.paket.id) == []
    # Wieder installieren holt die Übungen zurück, der Plan behält die Kopie
    pakete.importieren(pakete.inhalt(inhalt.paket.id))
    assert repo.laden(baum.id) is not None
    assert [i.exercise_id for i in plaene.laden(plan.id).items] == [kopie.id]


def test_tag_umbenennen_und_loeschen_ziehen_den_paketstand_mit(con) -> None:
    """K-F4 (Ben, 15.10.2026): Nach „Qigong → Qi Gong" gilt keine Paketübung als geändert,
    und „Auf Paketstand setzen" legt den alten Namen nicht wieder an — auch nicht der Start."""
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    tags = TagRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    baum = inhalt.uebungen[0]
    assert tags.umbenennen(TAG_TYP, "Qigong", "Qi Gong") is None
    assert pakete.abweichungen(repo.laden(baum.id)) == []
    assert pakete.standard(baum.id)["typen"] == ["Qi Gong", "Dehnung"]
    assert pakete.zuruecksetzen([baum.id]) == 0
    assert tags.loeschen(TAG_REGION, "Meridiane") == 1
    assert pakete.abweichungen(repo.laden(baum.id)) == []
    assert pakete.standard(baum.id)["regionen"] == []
    # Zusammenführen auf einen vorhandenen Namen: der Stand trägt dann dessen Schreibweise
    assert tags.umbenennen(TAG_TYP, "Qi Gong", "Dehnung") is None
    assert pakete.standard(baum.id)["typen"] == ["Dehnung"]
    assert pakete.abweichungen(repo.laden(baum.id)) == []
    # Das Standard-Paket beim nächsten Start: der Stand aus dem TOML überschreibt nicht
    nacken = repo.laden(seed_id("nacken_dehnung"))
    assert "Dehnung" in nacken.typen
    assert tags.umbenennen(TAG_TYP, "Dehnung", "Stretching") is None
    seed_einspielen(con)
    nacken = repo.laden(seed_id("nacken_dehnung"))
    assert "Stretching" in nacken.typen and "Dehnung" not in nacken.typen
    assert pakete.abweichungen(nacken) == []
    assert pakete.zuruecksetzen([nacken.id]) == 0


def test_update_und_reset_behalten_eigene_fotos_und_lokale_videos(con) -> None:
    """K-F5 (Ben, 15.10.2026): Das Paket kennt lokale Medien nicht — sie bleiben trotzdem."""
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    pakete.importieren(paket_lesen(qigong()))
    baum = repo.laden(paket_lesen(qigong()).uebungen[0].id)
    baum.media.append(Media(kind=MediaKind.IMAGE, source=MediaSource.LOCAL, uri="fotos/baum.jpg"))
    baum.image_path = "fotos/baum.jpg"
    repo.speichern(baum)
    assert pakete.abweichungen(repo.laden(baum.id)) == []  # Lokales zählt nicht als Abweichung

    neu = qigong(version=2)
    neu["exercises"][0]["description"] = "Zweite Fassung."
    vorschau = pakete.importieren(paket_lesen(neu))
    assert vorschau.status[baum.id] == Status.GEAENDERT
    baum = repo.laden(baum.id)
    assert baum.description == "Zweite Fassung."
    assert [m.uri for m in baum.media if m.source == MediaSource.LOCAL] == ["fotos/baum.jpg"]
    assert baum.image_path == "fotos/baum.jpg"

    baum.description = "Meine Fassung"
    repo.speichern(baum)
    assert pakete.zuruecksetzen([baum.id]) == 1
    baum = repo.laden(baum.id)
    assert baum.description == "Zweite Fassung."
    assert [m.uri for m in baum.media if m.source == MediaSource.LOCAL] == ["fotos/baum.jpg"]
    assert baum.image_path == "fotos/baum.jpg"


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


# ---------------------------------------------------------------------------
# Migration 017: nicht mehr im Paket, deaktivieren, Größe (Ben, 16.10.2026)
# ---------------------------------------------------------------------------


def test_entfallene_uebung_bleibt_bis_zur_entscheidung(con) -> None:
    """Fällt eine Übung aus dem Paket, wird nichts gelöscht: Markierung, dann übernehmen."""
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    plaene = PlanRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    baum, tief = inhalt.uebungen
    plan = Plan(name="Morgens", subject_id=None)
    plaene.speichern(plan)
    plaene.uebung_hinzufuegen(plan.id, tief.id)

    roh = qigong(version=2)
    roh["exercises"] = roh["exercises"][:1]  # „baum_tief“ fehlt
    vorschau = pakete.vorschau(paket_lesen(roh))
    assert vorschau.entfallen == [tief.id]
    assert any("nicht mehr im Paket" in z for z in vorschau.zusammenfassung())
    pakete.importieren(paket_lesen(roh))
    assert [u.id for u in pakete.entfallene(inhalt.paket.id)] == [tief.id]
    assert repo.laden(tief.id) is not None  # nichts gelöscht
    assert [i.exercise_id for i in plaene.laden(plan.id).items] == [tief.id]
    assert all(z.entfallen == (z.uebung.id == tief.id) for z in pakete.uebersicht(inhalt.paket.id))
    assert [u.id for u in pakete.inhalt(inhalt.paket.id).uebungen] == [baum.id]  # nicht zurück
    assert [(p.id, [u.id for u in us], ks) for p, us, ks in pakete.entfallene_offen()] == [
        (inhalt.paket.id, [tief.id], [])
    ]

    # Wieder in der Datei: die Markierung fällt
    pakete.importieren(paket_lesen(qigong(version=3)))
    assert pakete.entfallene(inhalt.paket.id) == []
    pakete.importieren(paket_lesen(roh | {"paket": {"name": "Qigong", "version": 4}}))

    # Übernehmen: eigene Übung mit derselben ID — Plan und Verlauf hängen daran
    assert pakete.entfallene_uebernehmen([tief.id]) == 1
    u = repo.laden(tief.id)
    assert u.package_id is None and pakete.standard(tief.id) is None
    assert [i.exercise_id for i in plaene.laden(plan.id).items] == [tief.id]
    assert pakete.anzahl_eigene() == 1
    assert pakete.entfallene_uebernehmen([tief.id]) == 0  # nur Markierte


def test_entfallene_uebung_loeschen(con) -> None:
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    plaene = PlanRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    baum, tief = inhalt.uebungen
    plan = Plan(name="Morgens", subject_id=None)
    plaene.speichern(plan)
    plaene.uebung_hinzufuegen(plan.id, tief.id)
    roh = qigong(version=2)
    roh["exercises"] = roh["exercises"][:1]
    pakete.importieren(paket_lesen(roh))

    assert pakete.entfallene_loeschen([tief.id, baum.id]) == 1  # „baum“ ist nicht entfallen
    assert repo.laden(tief.id) is None and repo.laden(tief.id, mit_geloeschten=True) is not None
    assert plaene.laden(plan.id).items == []
    assert repo.laden(tief.id, mit_geloeschten=True).package_id is None
    assert pakete.entfallene(inhalt.paket.id) == []
    assert [u.id for u in pakete.inhalt(inhalt.paket.id).uebungen] == [baum.id]


def test_entfallener_kurs(con) -> None:
    pakete = PaketRepo(con)
    kurse = KursRepo(con)
    roh = qigong()
    roh["kurse"] = [
        {"key": "k1", "name": "Kurs A", "kapitel": [{"key": "a", "titel": "A", "text": "x"}]},
        {"key": "k2", "name": "Kurs B", "kapitel": [{"key": "b", "titel": "B", "text": "y"}]},
    ]
    inhalt = paket_lesen(roh)
    pakete.importieren(inhalt)
    meine = lambda: [k for k in kurse.alle() if k.package_id == inhalt.paket.id]  # noqa: E731
    assert len(meine()) == 2
    roh["kurse"] = roh["kurse"][:1]
    roh["paket"]["version"] = 2
    vorschau = pakete.importieren(paket_lesen(roh))
    kurs_b = inhalt.kurse[1].id
    assert vorschau.kurse_entfallen == [kurs_b]
    assert [k.id for k in pakete.entfallene_kurse(inhalt.paket.id)] == [kurs_b]
    assert len(meine()) == 2  # bleibt sichtbar, bis entschieden ist
    assert pakete.entfallene_uebernehmen(kurse=[kurs_b]) == 1
    assert kurse.laden(kurs_b).package_id is None
    assert pakete.entfallene_loeschen(kurse=[inhalt.kurse[0].id]) == 0  # nicht entfallen


def test_deaktivieren_versteckt_alles_und_haelt_die_daten(con) -> None:
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    plaene = PlanRepo(con)
    kurse = KursRepo(con)
    roh = qigong()
    roh["kurse"] = [
        {"key": "k1", "name": "Kurs A", "kapitel": [{"key": "a", "titel": "A", "text": "x"}]}
    ]
    inhalt = paket_lesen(roh)
    pakete.importieren(inhalt)
    baum, _tief = inhalt.uebungen
    plan = Plan(name="Morgens", subject_id=None)
    plaene.speichern(plan)
    plaene.uebung_hinzufuegen(plan.id, baum.id)
    plaene.uebung_hinzufuegen(plan.id, seed_id("wadenheben"))
    vorher = con.execute("SELECT SUM(revision) FROM exercise").fetchone()[0]

    pakete.deaktivieren(inhalt.paket.id)
    assert pakete.laden(inhalt.paket.id).deaktiviert is not None
    assert not pakete.laden(inhalt.paket.id).aktiv
    assert baum.id not in {u.id for u in repo.alle()}
    assert repo.suchen("Baum") == []
    assert "Qigong" not in repo.typen() and "Meridiane" not in repo.regionen()
    assert [i.exercise_id for i in plaene.laden(plan.id).items] == [seed_id("wadenheben")]
    assert [k.package_id for k in kurse.alle()] == [GRUNDAUSSTATTUNG]  # nur der Standardkurs
    assert repo.laden(baum.id) is not None  # Daten da
    assert baum.id in {u.id for u in repo.alle(mit_geloeschten=True)}  # der Verlauf sieht alles
    assert [p.name for p, _ in pakete.alle()] == ["Standard", "Qigong"]  # bleibt in der Liste
    assert pakete.importieren(paket_lesen(qigong(version=2))).installiert is not None
    assert pakete.laden(inhalt.paket.id).deaktiviert is not None  # ein Import aktiviert nicht

    pakete.aktivieren(inhalt.paket.id)
    assert baum.id in {u.id for u in repo.alle()}
    assert [i.exercise_id for i in plaene.laden(plan.id).items] == [baum.id, seed_id("wadenheben")]
    assert len(kurse.alle()) == 2
    assert con.execute("SELECT SUM(revision) FROM exercise").fetchone()[0] == vorher


def test_seed_laesst_deaktiviertes_standardpaket_in_ruhe(con) -> None:
    pakete = PaketRepo(con)
    pakete.deaktivieren(GRUNDAUSSTATTUNG)
    con.execute("DELETE FROM exercise WHERE id = ?", (seed_id("wadenheben"),))
    assert seed_einspielen(con) == 0
    assert ExerciseRepo(con).laden(seed_id("wadenheben")) is None


def test_groesse_zaehlt_texte_und_lokale_dateien(con, tmp_path) -> None:
    pakete = PaketRepo(con)
    repo = ExerciseRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    texte, dateien = pakete.groesse(inhalt.paket.id, tmp_path)
    assert texte > 100 and dateien == 0
    (tmp_path / "foto.jpg").write_bytes(b"x" * 1000)
    (tmp_path / "clip.mp4").write_bytes(b"y" * 5000)
    baum = repo.laden(inhalt.uebungen[0].id)
    baum.image_path = "foto.jpg"
    baum.media.append(Media(kind=MediaKind.VIDEO, source=MediaSource.LOCAL, uri="clip.mp4"))
    baum.media.append(Media(kind=MediaKind.VIDEO, source=MediaSource.LOCAL, uri="fehlt.mp4"))
    repo.speichern(baum)
    assert pakete.groesse(inhalt.paket.id, tmp_path) == (texte, 6000)


def test_quellenfelder_am_paket(con) -> None:
    pakete = PaketRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    pid = inhalt.paket.id
    assert pakete.laden(pid).verfuegbar is None and pakete.laden(pid).update_modus == "auto"
    pakete.verfuegbar_setzen(pid, 2, "https://x/q.json", "ab", "Neu: Lotus")
    p = pakete.laden(pid)
    assert (p.verfuegbar, p.verfuegbar_url, p.verfuegbar_sha256, p.verfuegbar_neuigkeiten) == (
        2,
        "https://x/q.json",
        "ab",
        "Neu: Lotus",
    )
    assert p.geprueft is not None
    pakete.update_modus_setzen(pid, "manuell")
    assert pakete.laden(pid).update_modus == "manuell"
    with pytest.raises(ValueError):
        pakete.update_modus_setzen(pid, "sofort")
    pakete.quelle_setzen(pid, "https://x/q.json")
    pakete.verfuegbar_loeschen(pid)
    p = pakete.laden(pid)
    assert p.quelle == "https://x/q.json" and p.verfuegbar is None and p.verfuegbar_url is None
    pakete.importieren(paket_lesen(qigong(version=2)))  # ein Import rührt die Felder nicht an
    assert pakete.laden(pid).update_modus == "manuell" and pakete.laden(pid).quelle is not None
    pakete.geprueft_setzen()
    assert all(p.geprueft is not None for p, _ in pakete.alle())


def test_uhr_und_zaehlt_als_reisen_im_paket(con) -> None:
    """Ben, 18.10.2026: Uhr an/aus und „Zählt als“ gehören zur Übung — sie reisen im Paket
    (nur, wenn sie von der Vorgabe abweichen), und wer sie hier ändert, behält sie."""
    from trainingsapp.core.pakete import aus_stand, stand, zusammenfuehren

    u = Exercise(name="Dehnen", uhr=False, zaehlt_als="duration")
    d = stand(u)
    assert d["uhr"] is False and d["zaehlt_als"] == "duration"
    assert "uhr" not in stand(Exercise(name="Planke"))  # die Vorgabe schreibt sich nicht
    zurueck = aus_stand(u.id, "p1", d)
    assert (zurueck.uhr, zurueck.zaehlt_als) == (False, "duration")
    # Drei-Wege-Abgleich: hier eingeschaltet, im Paket unverändert → bleibt eingeschaltet
    hier = {**d, "uhr": True}
    neu = {**d, "description": "Länger halten."}
    gemischt = zusammenfuehren(d, hier, neu)
    assert gemischt.get("uhr", True) is True and gemischt["description"] == "Länger halten."
    # In der Datenbank
    from trainingsapp.data.repositories import ExerciseRepo

    repo = ExerciseRepo(con)
    repo.speichern(u)
    geladen = repo.laden(u.id)
    assert geladen is not None and (geladen.uhr, geladen.zaehlt_als) == (False, "duration")


def test_plan_speichern_behaelt_uebungen_deaktivierter_pakete(con) -> None:
    """D4: `laden` blendet Übungen deaktivierter Pakete aus, `speichern` darf sie nicht
    löschen — Aktivieren stellt den Plan vollständig her (Migration 017)."""
    pakete = PaketRepo(con)
    plaene = PlanRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    baum, _tief = inhalt.uebungen
    plan = Plan(name="Morgens", subject_id=None)
    plaene.speichern(plan)
    plaene.uebung_hinzufuegen(plan.id, baum.id)
    plaene.uebung_hinzufuegen(plan.id, seed_id("wadenheben"))

    pakete.deaktivieren(inhalt.paket.id)
    geladen = plaene.laden(plan.id)
    assert [i.exercise_id for i in geladen.items] == [seed_id("wadenheben")]
    geladen.name = "Morgens neu"
    plaene.speichern(geladen)

    pakete.aktivieren(inhalt.paket.id)
    assert [i.exercise_id for i in plaene.laden(plan.id).items] == [
        baum.id,
        seed_id("wadenheben"),
    ]


def test_entfernen_beendet_plaene_aus_kurskapiteln(con) -> None:
    """K22: Pläne aus Kapiteln eines entfernten Pakets stehen nicht mehr als Tagesplan."""
    from trainingsapp.core.models import Subject
    from trainingsapp.data.repositories import SubjectRepo

    pakete = PaketRepo(con)
    kurse = KursRepo(con)
    plaene = PlanRepo(con)
    ich = Subject(name="Ich")
    SubjectRepo(con).speichern(ich)
    roh = qigong()
    roh["kurse"] = [
        {
            "key": "k1",
            "name": "Kurs A",
            "kapitel": [
                {
                    "key": "a",
                    "titel": "A",
                    "text": "x",
                    "plaene": [{"name": "Täglich", "uebungen": [{"uebung": "baum"}]}],
                }
            ],
        }
    ]
    inhalt = paket_lesen(roh)
    pakete.importieren(inhalt)
    kurs = kurse.laden(inhalt.kurse[0].id)
    kurse.starten(kurs, ich.id)
    assert [p.name for p in plaene.alle(ich.id) if p.kurs_kapitel_id] == ["Täglich"]

    pakete.entfernen(inhalt.paket.id)
    assert [p.name for p in plaene.alle(ich.id) if p.kurs_kapitel_id] == []
    zeile = con.execute(
        "SELECT active FROM plan WHERE course_chapter_id = ?", (kurs.kapitel[0].id,)
    ).fetchone()
    assert zeile["active"] == 0


def test_herkunft_nachtragen_installiert_entferntes_paket_nicht(con) -> None:
    """K25: Nur ein Import holt ein entferntes Paket zurück."""
    pakete = PaketRepo(con)
    inhalt = paket_lesen(qigong())
    pakete.importieren(inhalt)
    pakete.entfernen(inhalt.paket.id)
    assert pakete.laden(inhalt.paket.id).entfernt is not None
    pakete.herkunft_nachtragen(inhalt)
    assert pakete.laden(inhalt.paket.id).entfernt is not None
    pakete.importieren(inhalt)
    assert pakete.laden(inhalt.paket.id).entfernt is None


def test_paket_lesen_faengt_kaputte_felder_statt_abzustuerzen() -> None:
    """K15–K17: Fremddaten enden in `PaketFehler` oder einem Problemtext — nie in
    AttributeError, OverflowError oder einem Absturz beim Anzeigen."""
    faelle = [
        {"result_spec": {"fields": ["abc"]}},
        {"result_spec": {"fields": "x"}},
        {"timer": [{"name": "T", "abschnitte": [{"name": "a", "dauer_s": 1e400}]}]},
        {"timer": [{"name": "T", "abschnitte": [{"name": "a", "dauer_s": 30}], "runden": 1e400}]},
    ]
    for extra in faelle:
        roh = qigong()
        roh["exercises"][0] |= extra
        try:
            paket_lesen(roh)
        except PaketFehler:
            continue
        # gelesen — nur die Rundenzahl wird still auf ihr Maximum gedeckelt
        assert "runden" in extra["timer"][0]


def test_medien_mit_fremdem_schema_fallen_beim_import_weg() -> None:
    """S1: ``intent://``, ``tel:``, ``http://`` öffnet die App nicht — das Medium fällt weg,
    Übung und Kapitel bleiben (keine Fehlermeldung, nur https:// und mailto: zählen)."""
    roh = qigong()
    roh["exercises"][0]["media"] = [
        {"uri": "intent://scan/#Intent;scheme=zxing;end"},
        {"uri": "https://example.org/baum.mp4", "title": "Video"},
        {"uri": "tel:+4912345"},
        {"uri": "http://example.org/unverschluesselt.mp4"},
    ]
    roh["kurse"] = [
        {
            "key": "k",
            "name": "K",
            "kapitel": [
                {
                    "key": "a",
                    "titel": "A",
                    "text": "x",
                    "media": [
                        {"kind": "audio", "uri": "file:///sdcard/a.mp3"},
                        {"kind": "audio", "uri": "mailto:praxis@example.org"},
                        {"kind": "audio", "uri": "HTTPS://example.org/a.mp3"},
                    ],
                }
            ],
        }
    ]
    inhalt = paket_lesen(roh)
    (baum, _) = inhalt.uebungen
    assert [(m.uri, m.title) for m in baum.media] == [("https://example.org/baum.mp4", "Video")]
    (kurs,) = inhalt.kurse
    assert [m.uri for m in kurs.kapitel[0].media] == [
        "mailto:praxis@example.org",
        "HTTPS://example.org/a.mp3",
    ]


def test_ids_aus_paketen_sind_eng_gefasst() -> None:
    """S6: `/`, `?`, Leerzeichen oder Kilobytes in einer ID brächen Routen und Datenbank —
    `^[A-Za-z0-9_-]{1,64}$`, sonst `PaketFehler` mit Hinweis; UUIDs und Schlüssel gehen."""
    kaputt = ["baum/tief", "a b", "x?y=1", "ä", "i" * 65, "<script>"]
    for falsch in kaputt:
        with pytest.raises(PaketFehler, match="ID des Pakets"):
            paket_lesen(qigong(id=falsch))
        roh = qigong()
        roh["exercises"][0]["id"] = falsch
        with pytest.raises(PaketFehler, match="ID der Übung"):
            paket_lesen(roh)
        kurs = {"key": "k", "name": "K", "kapitel": [{"key": "a", "titel": "A", "text": "x"}]}
        roh = qigong()
        roh["kurse"] = [kurs | {"id": falsch}]
        with pytest.raises(PaketFehler, match="ID des Kurses"):
            paket_lesen(roh)
        roh = qigong()
        roh["kurse"] = [kurs | {"kapitel": [kurs["kapitel"][0] | {"id": falsch}]}]
        with pytest.raises(PaketFehler, match="ID von Kapitel 1"):
            paket_lesen(roh)
    # Gültig: UUIDs, Schlüssel, 64 Zeichen; leer = keine ID (dann aus dem Schlüssel)
    roh = qigong(id="2c1194ea-67ba-536d-aa7d-bf74bc3c73d4")
    roh["exercises"][0]["id"] = "i" * 64
    roh["exercises"][1]["id"] = ""
    inhalt = paket_lesen(roh)
    assert inhalt.paket.id == "2c1194ea-67ba-536d-aa7d-bf74bc3c73d4"
    from trainingsapp.core.pakete import uebung_id

    assert [u.id for u in inhalt.uebungen] == ["i" * 64, uebung_id(inhalt.paket.id, "baum_tief")]


def test_kurzform_liest_keine_attribute_und_keine_formatangaben() -> None:
    """S7 (vorher K18): Die Kurzform ersetzt nur ``{feldschlüssel}`` — ``{a.__class__}``,
    ``{reps:d}`` oder ``{reps[0]}`` zeigen nie Internes, sondern lassen die Vorlage
    „nicht passen“; angezeigt werden dann die Felder. Das gilt auch für Vorlagen aus
    `spec_snapshot_json`, darum braucht der Import keine eigene Prüfung mehr."""
    from trainingsapp.core.result_spec import FieldSpec, FieldType, ResultSpec

    for vorlage in ("{a.__class__}", "{a.__class__.__mro__}", "{a:d}", "{a[0]}", "{a!r}"):
        roh = qigong()
        roh["exercises"][0]["result_spec"] = {
            "fields": [{"key": "a", "type": "int", "label": "A"}],
            "shorthand": vorlage,
        }
        (u, _) = paket_lesen(roh).uebungen
        text = u.result_spec.format_shorthand({"a": 12})
        assert text == "12" and "class" not in text, vorlage
    # Gültige Vorlagen wie bisher — auch die Fälle, in denen sie nicht zu den Werten passt
    spec = ResultSpec(
        fields=[
            FieldSpec("sets", FieldType.INT, "Sätze"),
            FieldSpec("reps", FieldType.INT, "Wdh."),
        ],
        shorthand="{sets}x{reps}",
    )
    assert spec.format_shorthand({"sets": 3, "reps": 15}) == "3x15"
    assert spec.format_shorthand({"reps": 15}) == "15"
    assert SPEC_WINKEL.format_shorthand({"angle": 45}) == "45°"


def test_kursbedingung_mit_unendlichem_soll_wird_abgelehnt() -> None:
    """K17: `int(inf)` stürzte beim Anzeigen des Kurses ab."""
    for soll in (1e400, "1e400", float("nan")):
        roh = qigong()
        roh["kurse"] = [
            {
                "key": "k",
                "name": "K",
                "kapitel": [
                    {
                        "key": "a",
                        "titel": "A",
                        "text": "x",
                        "bedingung": {"art": "tage", "soll": soll},
                    }
                ],
            }
        ]
        with pytest.raises(PaketFehler):
            paket_lesen(roh)


def test_kennzahlen_ueberstehen_none_und_text_in_satzliste() -> None:
    """K19: `result={"reps": [15, None]}` stürzte das Speichern jedes Eintrags ab."""
    from trainingsapp.core.result_spec import SPEC_SAETZE_WDH

    assert SPEC_SAETZE_WDH.kennzahlen({"reps": [15, None, "abc", 5]}) == [
        ("reps:sum", 20.0, "Wdh."),
        ("reps:max", 15.0, "Wdh."),
    ]
    assert SPEC_SAETZE_WDH.kennzahlen({"reps": [None]}) == []
    assert SPEC_WINKEL.format_shorthand({"angle": [1, 2]}) != ""  # Vorlage passt nicht → Felder


def test_paketstand_mit_altem_feldnamen_gilt_als_unveraendert() -> None:
    """K20: „Zeit gesamt“ im gespeicherten Paketstand ist dasselbe wie „Zeit“ heute."""
    from trainingsapp.core.pakete import abweichungen, stand, zusammenfuehren
    from trainingsapp.core.result_spec import FieldSpec, FieldType, ResultSpec

    u = Exercise(
        name="Lauf",
        result_spec=ResultSpec(
            fields=[FieldSpec("duration", FieldType.DURATION, "Zeit", unit="s")]
        ),
    )
    alt = stand(u)
    alt["result_spec"]["fields"][0]["label"] = "Zeit gesamt"
    assert abweichungen(u, alt) == []
    soll = stand(u) | {"description": "neu"}
    assert zusammenfuehren(alt, stand(u), soll)["description"] == "neu"
