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
