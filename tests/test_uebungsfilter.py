"""Filter der Übungsauswahl ohne Oberfläche (`core/uebungsfilter.py`, Ben 9.11.2026)."""

from __future__ import annotations

from trainingsapp.core.models import Exercise
from trainingsapp.core.uebungsfilter import EIGENE, EIGENE_TEXT, Uebungsfilter, paket_wahl
from trainingsapp.data.db import oeffnen
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.repositories import ExerciseRepo
from trainingsapp.data.seed import seed_einspielen


def test_innerhalb_oder_zwischen_und() -> None:
    a = Exercise(typen=["Atmung"], regionen=["Brust"], package_id="std")
    b = Exercise(typen=["Dehnung"], regionen=["Bein"], package_id="qi")
    c = Exercise(typen=["Atmung"], regionen=["Bein"])  # eigene
    f = Uebungsfilter(typen={"Atmung", "Dehnung"})
    assert [f.passt(u) for u in (a, b, c)] == [True, True, True]
    f.pakete = {"std", EIGENE}
    assert [f.passt(u) for u in (a, b, c)] == [True, False, True]
    f.regionen = {"Bein"}
    assert [f.passt(u) for u in (a, b, c)] == [False, False, True]
    assert f.anzahl == 5


def test_paketwahl_aus_dem_katalog(tmp_path) -> None:
    """Mit der echten Datenbank: Standard ist installiert, eine eigene Übung kommt dazu."""
    con = oeffnen(tmp_path / "app.db")
    try:
        seed_einspielen(con)
        uebungen, pakete = ExerciseRepo(con), PaketRepo(con)
        alle_pakete = [p for p, _ in pakete.alle()]
        standard = next(p for p in alle_pakete if p.name == "Standard")
        assert paket_wahl(uebungen.alle(), alle_pakete) == [(standard.id, "Standard")]
        uebungen.speichern(Exercise(name="Eigene"))
        wahl = paket_wahl(uebungen.alle(), alle_pakete)
        assert wahl == [(standard.id, "Standard"), (EIGENE, EIGENE_TEXT)]
        # Deaktiviert: die Übungen sind aus dem Katalog — und das Paket aus der Wahl
        pakete.deaktivieren(standard.id)
        assert paket_wahl(uebungen.alle(), alle_pakete) == [(EIGENE, EIGENE_TEXT)]
    finally:
        con.close()
