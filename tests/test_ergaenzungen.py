"""Ergänzungen („Mods“, U5, Ben 9.11.2026, `docs/plan_paketinhalte.md` §8, F2): ein Paket ergänzt
Übungen eines anderen — Abschnitte, Medien, Parameter, Ziel, Timer, Takt. Eigenes bleibt bei
jedem Kommen, Ändern und Gehen der Ergänzung; eine Ergänzung wartet, bis ihre Übung da ist."""

from __future__ import annotations

import pytest

from trainingsapp.core.abgleich import schluessel_abschnitte
from trainingsapp.core.pakete import (
    GRUNDAUSSTATTUNG,
    paket_bauen,
    paket_id,
    paket_lesen,
    uebung_id,
)
from trainingsapp.data.db import oeffnen
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.repositories import ExerciseRepo
from trainingsapp.data.seed import seed_einspielen, seed_id


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    seed_einspielen(verbindung)
    yield verbindung
    verbindung.close()


def _reha(version: int = 1, text: str = "Langsam, Knie über dem Fuß.", reps: int = 8) -> dict:
    return {
        "paket": {"name": "Knie-Reha", "version": version},
        "ergaenzungen": [
            {
                "uebung": "kniebeuge",  # ohne „paket“: aus „Standard“
                "description": f"## Reha\n{text}",
                "default_target": {"reps": [reps, reps]},
                "media": [{"uri": "https://x.org/reha", "title": "Reha-Video"}],
                "name": "darf eine Ergänzung nicht",
            },
            {"uebung": "baum", "paket": "Qigong", "description": "## Reha\nKürzer stehen."},
        ],
    }


def _abschnitte(text: str) -> dict[str, str]:
    return {k: a.text for k, a in schluessel_abschnitte(text)}


def test_ergaenzung_kommt_bleibt_eigen_geht_und_wartet(con) -> None:
    pakete, uebungen = PaketRepo(con), ExerciseRepo(con)
    knie_id = seed_id("kniebeuge")
    grund = uebungen.laden(knie_id)
    assert grund is not None and "reha" not in _abschnitte(grund.description)
    # Format: eine Datei nur mit Ergänzungen ist ein Paket (Version 5); fremde Felder fallen weg
    inhalt = paket_lesen(_reha())
    assert [e.uebung_id for e in inhalt.ergaenzungen] == [
        knie_id,
        uebung_id(paket_id("Qigong"), "baum"),
    ]
    assert "name" not in inhalt.ergaenzungen[0].daten
    assert paket_bauen(inhalt.paket, [], ergaenzungen=inhalt.ergaenzungen)["version"] == 5
    vorschau = pakete.vorschau(inhalt)
    assert vorschau.ergaenzt == [knie_id] and len(vorschau.ergaenzung_wartet) == 1
    assert "ergänzt 1 Übung eines anderen Pakets — was du daran geändert hast, bleibt" in (
        vorschau.zusammenfassung()
    )
    pakete.importieren(inhalt)
    knie = uebungen.laden(knie_id)
    assert _abschnitte(knie.description)["reha"] == "Langsam, Knie über dem Fuß."
    assert knie.default_target == {"reps": [8, 8]} and knie.name == grund.name
    assert "https://x.org/reha" in [m.uri for m in knie.media]
    assert pakete.abweichungen(knie) == []  # die Ergänzung gehört zum Paketstand
    # Eigenes: die Person schreibt den Reha-Abschnitt um
    knie.description = knie.description.replace("Knie über dem Fuß", "Knie leicht nach außen")
    uebungen.speichern(knie)
    # Update der Ergänzung: Ziel 10 (unberührt → kommt), Reha-Text neu (eigener bleibt)
    pakete.importieren(paket_lesen(_reha(version=2, text="Sehr langsam.", reps=10)))
    knie = uebungen.laden(knie_id)
    assert _abschnitte(knie.description)["reha"] == "Langsam, Knie leicht nach außen."
    assert knie.default_target == {"reps": [10, 10]}
    assert [h.teil for h in pakete.hinweise(knie_id)] == ["reha"]
    # Deaktivieren: was nur aus der Ergänzung kam, geht; der eigene Abschnitt bleibt
    reha = paket_lesen(_reha()).paket
    pakete.deaktivieren(reha.id)
    knie = uebungen.laden(knie_id)
    assert knie.default_target == grund.default_target
    assert "https://x.org/reha" not in [m.uri for m in knie.media]
    assert _abschnitte(knie.description)["reha"] == "Langsam, Knie leicht nach außen."
    pakete.aktivieren(reha.id)
    assert uebungen.laden(knie_id).default_target == {"reps": [10, 10]}
    # „Wieder installieren“ kennt die Ergänzungen und den Grundstand der Übungen
    wieder = pakete.inhalt(reha.id)
    assert wieder is not None and len(wieder.ergaenzungen) == 2
    standard = pakete.inhalt(GRUNDAUSSTATTUNG)
    knie_grund = next(u for u in standard.uebungen if u.id == knie_id)
    assert "reha" not in _abschnitte(knie_grund.description)
    # Die wartende Ergänzung greift, sobald ihr Paket kommt
    pakete.importieren(
        paket_lesen(
            {
                "paket": {"name": "Qigong", "version": 1},
                "exercises": [{"key": "baum", "name": "Baum", "description": "Stehen."}],
            }
        )
    )
    baum = next(u for u in uebungen.alle() if u.name == "Baum")
    assert _abschnitte(baum.description) == {"": "Stehen.", "reha": "Kürzer stehen."}
    # Ein Update des Grundpakets behält die Ergänzung obenauf
    pakete.importieren(
        paket_lesen(
            {
                "paket": {"name": "Qigong", "version": 2},
                "exercises": [{"key": "baum", "name": "Baum", "description": "Ruhig stehen."}],
            }
        )
    )
    baum = next(u for u in uebungen.alle() if u.name == "Baum")
    assert _abschnitte(baum.description) == {"": "Ruhig stehen.", "reha": "Kürzer stehen."}
    # Entfernen der Ergänzung: der Baum ist wieder der des Grundpakets
    pakete.entfernen(reha.id)
    baum = next(u for u in uebungen.alle() if u.name == "Baum")
    assert _abschnitte(baum.description) == {"": "Ruhig stehen."}


def test_eigenes_paket_bringt_geaenderte_fremde_uebung_als_ergaenzung(tmp_path, con) -> None:
    """U4 + U5: Was ich an einer Übung aus „Standard“ geändert habe, reist als Ergänzung — eine
    ganze fremde Übung bliebe beim Empfänger, wie sie ist."""
    from trainingsapp.core.eigenes_paket import EigenesPaket, naechste_version
    from trainingsapp.core.paketdatei import paket_oeffnen
    from trainingsapp.data.eigene_pakete import EigenesPaketRepo

    uebungen = ExerciseRepo(con)
    knie_id, planke_id = seed_id("kniebeuge"), seed_id("unterarmstuetz")
    knie = uebungen.laden(knie_id)
    knie.description += "\n## Für Anna\nNur bis 90°."
    knie.default_target = {"reps": [12]}
    uebungen.speichern(knie)
    repo = EigenesPaketRepo(con)
    ep = EigenesPaket(name="Für Anna", uebungen=[knie_id, planke_id])
    repo.speichern(ep)
    a = repo.inhalt(ep)
    assert a.uebungen == []  # beide gehören zu „Standard“
    ((erg),) = a.ergaenzungen  # die Planke ist unverändert — nichts zu ergänzen
    assert erg.uebung_id == knie_id and erg.daten["default_target"] == {"reps": [12]}
    assert erg.daten["description"] == "## Für Anna\nNur bis 90°."
    datei, _, _ = repo.exportieren(ep, naechste_version(None), tmp_path / "E", lambda _n: None)
    # Beim Empfänger: Standard ist da, die Kniebeuge bekommt Annas Abschnitt und Ziel
    con2 = oeffnen(tmp_path / "andere.db")
    seed_einspielen(con2)
    PaketRepo(con2).importieren(paket_oeffnen(datei))
    knie2 = ExerciseRepo(con2).laden(knie_id)
    assert _abschnitte(knie2.description)["für anna"] == "Nur bis 90°."
    assert knie2.default_target == {"reps": [12]}
    con2.close()
