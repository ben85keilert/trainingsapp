"""Stellungen einer Paketübung (Ben, 12.11.2026, P188, `core/ergaenzungen.py`): Standard und
Erweiterungen nebeneinander — Beschreibung, Medien und Timer zusammengelegt, die
Trainingsumgebung (Parameter, Ziel, Takt) aus **einer** gewählten Stellung; je Stellung ein
eigener Stand der Person, Updates gleichen je Stellung ab."""

from __future__ import annotations

import pytest

from trainingsapp.core.abgleich import schluessel_abschnitte
from trainingsapp.core.ergaenzungen import STANDARD
from trainingsapp.core.pakete import paket_lesen
from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
from trainingsapp.data.db import oeffnen
from trainingsapp.data.pakete import PaketRepo
from trainingsapp.data.repositories import ExerciseRepo
from trainingsapp.data.seed import seed_einspielen, seed_id

KRAFT_SPEC = ResultSpec(fields=[vorrat_feld("reps"), vorrat_feld("weight")]).to_dict()


@pytest.fixture
def con(tmp_path):
    verbindung = oeffnen(tmp_path / "test.db")
    seed_einspielen(verbindung)
    yield verbindung
    verbindung.close()


def _reha(version: int = 1, reps: int = 8) -> dict:
    return {
        "paket": {"name": "Knie-Reha", "version": version},
        "ergaenzungen": [
            {
                "uebung": "kniebeuge",
                "description": "## Reha\nLangsam.",
                "default_target": {"reps": [reps, reps]},
                "timer": [{"name": "Reha-Uhr", "abschnitte": [{"name": "Ab", "dauer_s": 30}]}],
            }
        ],
    }


def _kraft(version: int = 1, reps: int = 5, spec: dict | None = None) -> dict:
    return {
        "paket": {"name": "Kraft", "version": version},
        "ergaenzungen": [
            {
                "uebung": "kniebeuge",
                "description": "## Kraft\nSchwer.",
                "result_spec": spec or KRAFT_SPEC,
                "default_target": {"reps": [reps, reps, reps]},
            }
        ],
    }


def _video() -> dict:
    return {
        "paket": {"name": "Videos", "version": 1},
        "ergaenzungen": [
            {"uebung": "kniebeuge", "media": [{"uri": "https://x.org/v", "title": "Video"}]}
        ],
    }


def _felder(u) -> list[str]:
    return [f.key for f in u.result_spec.fields]


def _stellungen(pakete: PaketRepo, uebung_id: str) -> list[tuple[str, bool, bool]]:
    return [(s.name, s.aktiv, s.geaendert) for s in pakete.stellungen(uebung_id)]


def test_schalter_statt_spaeter_gewinnt(con) -> None:
    pakete, uebungen = PaketRepo(con), ExerciseRepo(con)
    knie_id = seed_id("kniebeuge")
    grund = uebungen.laden(knie_id)
    assert pakete.stellungen(knie_id) == []  # nur Standard: nichts zu schalten
    # Eine Erweiterung nur mit Medien ist keine Stellung
    pakete.importieren(paket_lesen(_video()))
    assert pakete.stellungen(knie_id) == []
    reha = paket_lesen(_reha()).paket
    kraft = paket_lesen(_kraft()).paket
    pakete.importieren(paket_lesen(_reha()))
    pakete.importieren(paket_lesen(_kraft()))
    # Vorgabe: die zuletzt installierte Erweiterung mit Trainingsumgebung
    assert _stellungen(pakete, knie_id) == [
        ("Standard", False, False),
        ("Knie-Reha", False, False),
        ("Kraft", True, False),
    ]
    knie = uebungen.laden(knie_id)
    assert _felder(knie) == ["reps", "weight"] and knie.default_target == {"reps": [5, 5, 5]}
    # Geteilt: Abschnitte und Medien aller Erweiterungen, die Timer in einer Liste
    abschnitte = {k for k, _ in schluessel_abschnitte(knie.description)}
    assert {"reha", "kraft"} <= abschnitte
    assert "https://x.org/v" in [m.uri for m in knie.media]
    assert "Reha-Uhr" in [t["name"] for t in knie.timer]
    assert pakete.abweichungen(knie) == []

    # Umschalten: nur die Trainingsumgebung wechselt
    assert pakete.stellung_waehlen(knie_id, reha.id)
    knie = uebungen.laden(knie_id)
    assert _felder(knie) == _felder(grund) and knie.default_target == {"reps": [8, 8]}
    assert {"reha", "kraft"} <= {k for k, _ in schluessel_abschnitte(knie.description)}
    assert knie.timer[0]["name"] == "Reha-Uhr"  # die Uhr der Stellung zuerst = Vorgabe
    assert pakete.abweichungen(knie) == []
    assert pakete.stellung_waehlen(knie_id, STANDARD)
    knie = uebungen.laden(knie_id)
    assert _felder(knie) == _felder(grund) and knie.default_target == grund.default_target
    assert [s.name for s in pakete.stellungen(knie_id) if s.aktiv] == ["Standard"]
    assert not pakete.stellung_waehlen(knie_id, "gibt-es-nicht")
    # Die Wahl bleibt, wenn eine neue Erweiterung kommt oder sich eine ändert
    pakete.importieren(paket_lesen(_kraft(version=2, reps=6)))
    assert uebungen.laden(knie_id).default_target == grund.default_target
    # Fällt die gewählte Stellung weg, gilt wieder die Vorgabe
    pakete.stellung_waehlen(knie_id, kraft.id)
    pakete.entfernen(kraft.id)
    assert [s.name for s in pakete.stellungen(knie_id) if s.aktiv] == ["Knie-Reha"]
    assert uebungen.laden(knie_id).default_target == {"reps": [8, 8]}


def test_eigener_stand_je_stellung_und_abgleich_beim_update(con) -> None:
    pakete, uebungen = PaketRepo(con), ExerciseRepo(con)
    knie_id = seed_id("kniebeuge")
    reha = paket_lesen(_reha()).paket
    kraft = paket_lesen(_kraft()).paket
    pakete.importieren(paket_lesen(_reha()))
    pakete.importieren(paket_lesen(_kraft()))
    # In „Kraft“ ändert die Person das Ziel und schreibt einen eigenen Abschnitt
    knie = uebungen.laden(knie_id)
    knie.default_target = {"reps": [4, 4]}
    knie.description += "\n## Für mich\nBreit stehen."
    uebungen.speichern(knie)
    assert _stellungen(pakete, knie_id)[2] == ("Kraft", True, True)
    # Umschalten nimmt das Ziel nicht mit — der eigene Abschnitt (geteilt) bleibt
    pakete.stellung_waehlen(knie_id, reha.id)
    knie = uebungen.laden(knie_id)
    assert knie.default_target == {"reps": [8, 8]}
    assert "Breit stehen." in knie.description
    assert _stellungen(pakete, knie_id) == [
        ("Standard", False, False),
        ("Knie-Reha", True, False),
        ("Kraft", False, True),  # dort liegt Eigenes
    ]
    # Update von „Kraft“, während es nicht gilt: Parameter neu (unberührt), Ziel neu (berührt)
    neue_spec = ResultSpec(
        fields=[vorrat_feld("reps"), vorrat_feld("weight"), vorrat_feld("scale")]
    ).to_dict()
    pakete.importieren(paket_lesen(_kraft(version=2, reps=6, spec=neue_spec)))
    assert uebungen.laden(knie_id).default_target == {"reps": [8, 8]}  # Reha gilt weiter
    # Zurück nach „Kraft“: das eigene Ziel ist wieder da, die neuen Parameter kommen
    pakete.stellung_waehlen(knie_id, kraft.id)
    knie = uebungen.laden(knie_id)
    assert knie.default_target == {"reps": [4, 4]}
    assert _felder(knie) == ["reps", "weight", "scale"]
    assert _stellungen(pakete, knie_id)[2] == ("Kraft", True, True)
    # „Zurücksetzen“ nur dieser Stellung: Ziel wie im Paket, der eigene Abschnitt bleibt
    assert pakete.stellung_zuruecksetzen(knie_id)
    knie = uebungen.laden(knie_id)
    assert knie.default_target == {"reps": [6, 6, 6]} and "Breit stehen." in knie.description
    assert _stellungen(pakete, knie_id)[2] == ("Kraft", True, False)
    assert not pakete.stellung_zuruecksetzen(knie_id)
    # … und einer Stellung, die gerade nicht gilt
    knie.default_target = {"reps": [3]}
    uebungen.speichern(knie)
    pakete.stellung_waehlen(knie_id, STANDARD)
    assert _stellungen(pakete, knie_id)[2] == ("Kraft", False, True)
    assert pakete.stellung_zuruecksetzen(knie_id, kraft.id)
    assert _stellungen(pakete, knie_id)[2] == ("Kraft", False, False)
    pakete.stellung_waehlen(knie_id, kraft.id)
    assert uebungen.laden(knie_id).default_target == {"reps": [6, 6, 6]}


def test_update_des_grundpakets_behaelt_die_stellung(con) -> None:
    pakete, uebungen = PaketRepo(con), ExerciseRepo(con)
    pakete.importieren(
        paket_lesen(
            {
                "paket": {"name": "Qigong", "version": 1},
                "exercises": [{"key": "baum", "name": "Baum", "description": "Stehen."}],
            }
        )
    )
    zusatz = {
        "paket": {"name": "Baum-Reha", "version": 1},
        "ergaenzungen": [{"uebung": "baum", "paket": "Qigong", "default_target": {"duration": 60}}],
    }
    pakete.importieren(paket_lesen(zusatz))
    baum = next(u for u in uebungen.alle() if u.name == "Baum")
    assert baum.default_target == {"duration": 60}
    pakete.stellung_waehlen(baum.id, STANDARD)
    assert not uebungen.laden(baum.id).default_target
    pakete.importieren(
        paket_lesen(
            {
                "paket": {"name": "Qigong", "version": 2},
                "exercises": [{"key": "baum", "name": "Baum", "description": "Ruhig stehen."}],
            }
        )
    )
    baum = uebungen.laden(baum.id)
    assert baum.description == "Ruhig stehen." and not baum.default_target
    assert [s.name for s in pakete.stellungen(baum.id) if s.aktiv] == ["Standard"]


def test_planuebung_ruht_wo_das_feld_in_der_stellung_fehlt(con) -> None:
    """Eine Einstellung der Planübung („nur hier“) für ein Feld, das die geltende Stellung
    nicht hat, zeigt nicht ins Leere: Ziel und Chips ruhen und gelten wieder, sobald die
    Stellung mit dem Feld zurück ist. An der Planübung wird nichts geändert."""
    from trainingsapp.core.models import PlanItem
    from trainingsapp.core.plaene import ziel_ohne_kontext
    from trainingsapp.core.standards import aktive_keys, eigene_chips, ziel_von, ziel_wirksam

    pakete, uebungen = PaketRepo(con), ExerciseRepo(con)
    knie_id = seed_id("kniebeuge")
    spec = ResultSpec(fields=[vorrat_feld("hold")]).to_dict()
    halten = {
        "paket": {"name": "Halten", "version": 1},
        "ergaenzungen": [
            {"uebung": "kniebeuge", "result_spec": spec, "default_target": {"hold": [30]}}
        ],
    }
    pakete.importieren(paket_lesen(halten))
    paket = paket_lesen(halten).paket
    item = PlanItem(exercise_id=knie_id, target={"hold": [45, 45]}, quick={"hold": [20, 40]})
    knie = uebungen.laden(knie_id)
    assert _felder(knie) == ["hold"]
    assert ziel_wirksam(item, knie) == {"hold": [45, 45]}
    assert eigene_chips(item, knie) == {"hold": [20, 40]}
    # Standard hat keine Haltezeit: Ziel und Chips der Planübung ruhen
    pakete.stellung_waehlen(knie_id, STANDARD)
    knie = uebungen.laden(knie_id)
    assert "hold" not in _felder(knie) and "hold" not in aktive_keys(item, knie)
    assert ziel_wirksam(item, knie) == {} and ziel_ohne_kontext(item, knie) == {}
    assert eigene_chips(item, knie) == {}
    assert ziel_von(item, knie) == {"hold": [45, 45]}  # steht weiter an der Planübung
    # Zurück: es gilt wieder
    pakete.stellung_waehlen(knie_id, paket.id)
    assert ziel_wirksam(item, uebungen.laden(knie_id)) == {"hold": [45, 45]}
