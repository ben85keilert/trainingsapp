"""Der Durchlauf eines Workouts aus der Zeitleiste (`core/workout_eintrag.py`) — ohne flet."""

from __future__ import annotations


def test_eintrag_haengt_bei_einer_schleife_am_beendeten_durchgang() -> None:
    """N50: a→a — `uebung_ende(a)` und `uebung_start(a)` stehen im selben Takt, der Eintrag
    wird danach nachgetragen (mit der Zeit des Endes): er gehört zum ersten Durchgang."""
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace as E

    from trainingsapp.core.workout_eintrag import durchlauf

    p = {"plan": "p", "workout": True}

    def u(t, art, **d):
        daten = {**p, "planuebung": "a", "name": "A", "stelle": 1, **d}
        return E(t_s=t, quelle="plan", art=art, text="", daten=daten)

    def eintrag(t, eid):
        daten = {"eintrag": eid, "planuebung": "a"}
        return E(t_s=t, quelle="person", art="eintrag", text="", daten=daten)

    roh = [
        E(t_s=0.0, quelle="plan", art="start", text="Beine", daten=p),
        u(0.0, "uebung_start"),
        u(60.0, "uebung_ende", grund="fertig"),
        u(60.0, "uebung_start"),
        eintrag(60.0, "e1"),
        u(90.0, "uebung_ende", grund="fertig"),
        eintrag(90.0, "e2"),
        E(t_s=90.0, quelle="plan", art="ende", text="Beine", daten=p),
    ]
    t0 = datetime(2026, 11, 10, 10, 5, tzinfo=UTC)
    d = durchlauf("x", t0, t0 + timedelta(seconds=90), roh)
    assert [(z.mal, z.eintrag_ids) for z in d.zeilen] == [(1, ("e1",)), (2, ("e2",))]


def test_entfernte_skala_bleibt_auch_als_fuenfte_in_der_kopie(tmp_path) -> None:
    """N75: Vier Skalen am Workout und eine entfernte mit Wert — die Feldkopie am Eintrag
    schneidet nicht bei `FELDER_MAX` ab; ein Wert ohne Feld in einer früheren Kopie bleibt
    über seinen Schlüssel sichtbar und kommt beim nächsten Schreiben in die Kopie zurück."""
    from datetime import UTC, datetime

    from trainingsapp.core import workout_eintrag as we
    from trainingsapp.core.models import Subject
    from trainingsapp.data.db import oeffnen
    from trainingsapp.data.einheiten import EinheitRepo
    from trainingsapp.data.repositories import SubjectRepo

    con = oeffnen(tmp_path / "t.db")
    profil = Subject(name="Ben")
    SubjectRepo(con).speichern(profil)
    r = EinheitRepo(con)
    r.einheit_beginnen("e-1", profil.id, datetime(2026, 11, 10, 8, 0, tzinfo=UTC), "Workout")
    r.workout_eintragen("e-1", result={we.feld_key("Alt"): 3}, felder=["Alt"])
    vier = ["A", "B", "C", "D"]  # „Alt“ ist vom Workout genommen, vier neue stehen dort
    werte = r.workout_eintragen("e-1", result={we.feld_key("A"): 5}, felder=vier)
    assert [f.label for f in werte.spec.fields] == ["Anstrengung (sRPE)", *vier, "Alt"]
    assert r.workout_wert("e-1").skalen_mit_wert() == [
        (we.feld_key("A"), "A"),
        (we.feld_key("Alt"), "Alt"),
    ]
    # eine Zeile von früher, deren Kopie abgeschnitten war: der Wert steht nur im Ergebnis
    alt = we.WorkoutWerte("e", {we.feld_key("Alt"): 3}, spec=we.spec(vier))
    assert alt.skalen_mit_wert() == [(we.feld_key("Alt"), "Alt")]
    assert len(we.spec([*vier, "Alt"]).fields) == 1 + we.FELDER_MAX  # am Workout bleibt es bei vier
    con.close()
