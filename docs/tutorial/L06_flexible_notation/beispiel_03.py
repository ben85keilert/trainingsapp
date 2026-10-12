"""L06, Beispiel 3 — Einträge mit Kopie, Kennzahlen im Verlauf, Korrektur als neuer Eintrag.

Start:  uv run python docs/tutorial/L06_flexible_notation/beispiel_03.py

Ein Mini-Repository, das in Aufgabe 4 zur echten SessionRepo wird.
"""

import json
import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path

from trainingsapp.core.models import Measurement, Session, SessionEntry, Subject, jetzt
from trainingsapp.core.result_spec import ResultSpec
from trainingsapp.data.db import oeffnen, transaktion
from trainingsapp.data.repositories import ExerciseRepo, SubjectRepo
from trainingsapp.data.seed import seed_einspielen, seed_id


def eintrag_anlegen(
    con: sqlite3.Connection,
    session: Session,
    exercise_id: str,
    result: dict,
    ersetzt: str | None = None,
) -> SessionEntry:
    """Legt einen Eintrag an — IMMER mit Kopie der Spezifikation — und schreibt die Kennzahlen."""
    uebung = ExerciseRepo(con).laden(exercise_id)
    assert uebung is not None
    eintrag = SessionEntry(
        session_id=session.id,
        exercise_id=exercise_id,
        result=result,
        spec_snapshot=uebung.result_spec,  # die Kopie
    )
    with transaktion(con):
        con.execute(
            "INSERT INTO session_entry "
            "(id, session_id, exercise_id, result_json, spec_snapshot_json, replaces_entry_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                eintrag.id,
                session.id,
                exercise_id,
                json.dumps(result),
                json.dumps(uebung.result_spec.to_dict()),
                ersetzt,
            ),
        )
        # chart_metrics → measurement: eine Zeile je Kennzahl
        for key in uebung.result_spec.chart_metrics:
            if (wert := result.get(key)) is None:
                continue
            feld = uebung.result_spec.field_by_key(key)
            m = Measurement(
                subject_id=session.subject_id,
                metric_key=f"{exercise_id}:{key}",
                value=float(wert),
                unit=(feld.unit if feld else None) or "",
                recorded_at=session.started_at,
                session_id=session.id,
                session_entry_id=eintrag.id,
                source="exercise",
            )
            con.execute(
                "INSERT INTO measurement "
                "(id, subject_id, metric_key, value, unit, recorded_at, session_id, "
                " session_entry_id, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    m.id,
                    m.subject_id,
                    m.metric_key,
                    m.value,
                    m.unit,
                    m.recorded_at.isoformat(),
                    m.session_id,
                    m.session_entry_id,
                    m.source,
                ),
            )
        if ersetzt is not None:
            # Der alte Eintrag bleibt — aber seine Kennzahlen gelten nicht mehr.
            con.execute("DELETE FROM measurement WHERE session_entry_id = ?", (ersetzt,))
    return eintrag


with tempfile.TemporaryDirectory() as ordner:
    con = oeffnen(Path(ordner) / "demo.db")
    seed_einspielen(con)
    ich = Subject(name="Ich")
    SubjectRepo(con).speichern(ich)
    wadenheben = seed_id("wadenheben")

    # 1. Drei Trainingseinheiten an drei Tagen.
    einheiten = []
    for tage_zurueck, reps in ((14, 12), (7, 15), (0, 15)):
        s = Session(subject_id=ich.id, started_at=jetzt() - timedelta(days=tage_zurueck))
        con.execute(
            "INSERT INTO session (id, subject_id, started_at) VALUES (?, ?, ?)",
            (s.id, s.subject_id, s.started_at.isoformat()),
        )
        eintrag = eintrag_anlegen(con, s, wadenheben, {"sets": 3, "reps": reps})
        einheiten.append((s, eintrag))
        print(f"Eintrag {eintrag.shorthand():6}  am {s.started_at:%d.%m.}")
    print()

    # 2. Der letzte Eintrag war ein Tippfehler: es waren 3x20. Korrektur = neuer Eintrag.
    letzte_session, falsch = einheiten[-1]
    richtig = eintrag_anlegen(
        con, letzte_session, wadenheben, {"sets": 3, "reps": 20}, ersetzt=falsch.id
    )
    print(f"Korrektur: {falsch.shorthand()} → {richtig.shorthand()}")
    print("(replaces_entry_id zeigt auf den alten Eintrag)")
    print(
        "Einträge in der Tabelle:",
        con.execute("SELECT COUNT(*) FROM session_entry").fetchone()[0],
        "— der alte bleibt als Historie",
    )
    print()

    # 3. Beim Lesen gewinnt der neueste: alles ausblenden, was ersetzt wurde.
    gueltige = con.execute(
        """
        SELECT e.result_json, e.spec_snapshot_json
        FROM session_entry e
        WHERE NOT EXISTS (SELECT 1 FROM session_entry n WHERE n.replaces_entry_id = e.id)
        ORDER BY rowid
        """
    ).fetchall()
    print("Gültige Einträge, angezeigt mit ihrer Kopie:")
    for r in gueltige:
        spec = ResultSpec.from_dict(json.loads(r["spec_snapshot_json"]))
        print("  ", spec.format_shorthand(json.loads(r["result_json"])))
    print()

    # 4. Der Verlauf kommt aus measurement — eine Tabelle, eine Abfrage, sortierbar.
    print("Verlauf 'reps' (aus measurement):")
    for r in con.execute(
        "SELECT recorded_at, value FROM measurement WHERE metric_key = ? ORDER BY recorded_at",
        (f"{wadenheben}:reps",),
    ):
        print(f"   {r['recorded_at'][:10]}  {r['value']:.0f}")
    print("Korrigierte Werte sind ersetzt, nicht doppelt.")
    con.close()
