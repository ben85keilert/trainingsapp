"""Paketverweise V4 (`docs/plan_paketverweise.md`, Ben 17.11.2026, F3: „von selbst“): Fehlt beim
Import das Paket, auf dessen Übungen Pläne und Kapitel verweisen, warten die Übungen — die App
sagt, woher sie kämen (``braucht`` bleibt am installierten Paket, Migration 070). Kommt das
Paket, trägt der Import sie in die Paketpläne und Kapitelpläne nach; was die Person am Plan
geändert oder herausgenommen hat, bleibt."""

from __future__ import annotations

import pytest

from trainingsapp.core.models import Subject
from trainingsapp.core.pakete import paket_id, paket_lesen, uebung_id
from trainingsapp.data.db import oeffnen
from trainingsapp.data.kurse import KursRepo
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.repositories import PlanRepo, SubjectRepo

A_ID = paket_id("Grundlagen")
A1, A2 = uebung_id(A_ID, "a1"), uebung_id(A_ID, "a2")


def _paket_a(version: int = 1) -> dict:
    return {
        "paket": {"id": A_ID, "name": "Grundlagen", "version": version},
        "exercises": [
            {"key": "a1", "name": "A eins", "description": "x"},
            {"key": "a2", "name": "A zwei", "description": "x"},
        ],
    }


def _paket_b() -> dict:
    """Ein Plan und ein Kurs, die Übungen aus „Grundlagen“ nennen (wie ``bauen`` sie schreibt:
    IDs) — und ``braucht``."""
    uebungen = [{"uebung": A1}, {"uebung": "b1"}, {"uebung": A2}]
    return {
        "paket": {
            "name": "Für Anna",
            "version": 1,
            "braucht": [{"id": A_ID, "name": "Grundlagen", "quelle": "https://x.invalid/a.json"}],
        },
        "exercises": [{"key": "b1", "name": "B eins", "description": "x"}],
        "plaene": [{"key": "morgens", "name": "Morgens", "uebungen": uebungen}],
        "kurse": [
            {
                "key": "kurs",
                "name": "Kurs",
                "kapitel": [
                    {
                        "key": "eins",
                        "titel": "Eins",
                        "plaene": [{"name": "Kapitel", "uebungen": uebungen}],
                    },
                    {
                        "key": "zwei",
                        "titel": "Nur fremde",
                        "plaene": [{"name": "Fremd", "uebungen": [{"uebung": A1}]}],
                    },
                ],
            }
        ],
    }


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    yield verbindung
    verbindung.close()


@pytest.fixture
def profil(con) -> Subject:
    s = Subject(name="Test")
    SubjectRepo(con).speichern(s)
    return s


def test_fehlende_uebungen_warten_und_kommen_mit_ihrem_paket(con, profil) -> None:
    pakete, kurse, plaene = PaketRepo(con), KursRepo(con), PlanRepo(con)
    b = paket_lesen(_paket_b())
    pakete.importieren(b, subject_id=profil.id)
    b1 = b.uebungen[0].id

    # Wartet: der Paketplan ohne die fremden Übungen, das Paket merkt sich, was es braucht
    (plan,) = pakete.des_pakets_plaene(b.paket.id, profil.id)
    assert [i.exercise_id for i in plan.items] == [b1]
    assert pakete.fehlende_im_plan(plan) == [A1, A2]
    assert [(v.name, da) for v, da in pakete.wartet_auf(b.paket.id)] == [("Grundlagen", None)]
    assert pakete.laden(b.paket.id).braucht[0].quelle == "https://x.invalid/a.json"

    (kurs,) = kurse.des_pakets(b.paket.id)
    eins, zwei = kurs.kapitel
    kurse.starten(kurs, profil.id)
    kurse.kapitel_erreichen(kurs, zwei, profil.id)  # frei geöffnet: sein Plan hätte nichts
    (kapitelplan,) = kurse.kapitel_plaene(eins.id, profil.id)
    assert [i.exercise_id for i in kapitelplan.items] == [b1]
    assert kurse.kapitel_plaene(zwei.id, profil.id) == []
    assert kurse.fehlende_uebungen(eins) == [A1, A2]
    assert kurse.fehlende_im_plan(kapitelplan) == [A1, A2]

    # Die Person nimmt im Kapitelplan „B eins“ heraus und gibt dem Paketplan ein Ziel
    kapitelplan.items = []
    plaene.speichern(kapitelplan)
    plan.items[0].target = {"reps": 12}
    plaene.speichern(plan)

    # „Grundlagen“ kommt: nachgetragen in drei Plänen, Eigenes bleibt
    ergebnis = pakete.importieren(paket_lesen(_paket_a()), subject_id=profil.id)
    assert ergebnis.nachgetragen == 3
    plan = plaene.laden(plan.id)
    assert [(i.exercise_id, i.target) for i in plan.items] == [
        (A1, None),
        (b1, {"reps": 12}),
        (A2, None),
    ]
    kapitelplan = plaene.laden(kapitelplan.id)
    assert [i.exercise_id for i in kapitelplan.items] == [A1, A2], "B eins bleibt draußen"
    (fremd,) = kurse.kapitel_plaene(zwei.id, profil.id)
    assert [i.exercise_id for i in fremd.items] == [A1] and fremd.aktiv
    assert pakete.fehlende_im_plan(plan) == [] and kurse.fehlende_uebungen(eins) == []
    assert pakete.wartet_auf(b.paket.id) == []

    # Ein weiteres Update von „Grundlagen“ trägt nichts mehr nach
    assert pakete.importieren(paket_lesen(_paket_a(2)), subject_id=profil.id).nachgetragen == 0


def test_ein_plan_im_papierkorb_bleibt_wie_er_ist(con, profil) -> None:
    pakete, plaene = PaketRepo(con), PlanRepo(con)
    b = paket_lesen(_paket_b())
    pakete.importieren(b, subject_id=profil.id)
    (plan,) = pakete.des_pakets_plaene(b.paket.id, profil.id)
    plaene.loeschen(plan.id)
    assert pakete.importieren(paket_lesen(_paket_a()), subject_id=profil.id).nachgetragen == 0
    assert len(plaene.laden(plan.id, mit_geloeschten=True).items) == 1


def test_braucht_bleibt_am_paket_und_faellt_mit_der_naechsten_fassung(con) -> None:
    """Migration 070: Was die Datei braucht, gilt bis zur nächsten Fassung — eine Fassung ohne
    ``braucht`` räumt es weg."""
    pakete = PaketRepo(con)
    roh = _paket_b()
    pakete.importieren(paket_lesen(roh))
    pid = paket_lesen(roh).paket.id
    assert [v.id for v in pakete.laden(pid).braucht] == [A_ID]
    del roh["paket"]["braucht"]
    roh["paket"]["version"] = 2
    pakete.importieren(paket_lesen(roh))
    assert pakete.laden(pid).braucht == []
