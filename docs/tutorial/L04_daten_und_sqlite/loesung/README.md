# L04 — Lösungen

## Aufgabe 1: Schema

**1. `spec_snapshot_json`**

Die Eingabemaske einer Übung kann sich ändern. Wird aus „Sätze × Wiederholungen"
später „Sätze × Wiederholungen × Gewicht", oder wird ein Feld umbenannt, dann
passt ein alter `result_json` nicht mehr zur aktuellen Spezifikation — die
Anzeige wäre falsch oder leer.

Mit der Kopie wird jeder Eintrag so dargestellt, wie er erfasst wurde. Ein
Eintrag von vor einem Jahr bleibt lesbar, auch wenn die Übung inzwischen
dreimal umgebaut wurde.

**2. `replaces_entry_id`**

Einträge sind unveränderlich. Eine Korrektur ist ein neuer Eintrag, der auf den
alten zeigt.

Der Gewinn zeigt sich in Edition B: Wenn Handy und Praxisserver denselben
Eintrag ändern könnten, bräuchte es eine Konfliktauflösung — und jede solche
Regel verliert im Zweifel Daten. Wenn nichts geändert werden kann, gibt es
nichts zu kollidieren. Konflikte sind nicht *gelöst*, sondern *unmöglich*.

Nebenbei bleibt die Historie erhalten: man sieht, dass korrigiert wurde.

**3. `subject`**

Ein Handy wird geteilt — Partner, Kinder. Und Edition B braucht die Zuordnung
ohnehin.

Der eigentliche Grund ist aber die Alternative: `subject_id` nachträglich
einzuführen hieße, jede Tabelle zu ändern, jede Abfrage anzupassen und alle
bestehenden Daten einem neu erfundenen Standardprofil zuzuordnen. Eine Spalte
jetzt kostet nichts; später kostet sie einen Nachmittag und ein Risiko.

**4. `tombstone` ohne Daten**

Ein echter Zielkonflikt:

- DSGVO Art. 17 verlangt **echtes Löschen** auf Verlangen.
- Die Synchronisation braucht eine **Spur des Gelöschten**, sonst kann ein
  zweites Gerät die Löschung nicht nachvollziehen — und schiebt den Datensatz
  beim nächsten Abgleich wieder hoch.

Auflösung: Der Grabstein enthält nur, was zum Nachziehen nötig ist — Kennung
und Zeitpunkt. Beides ist für sich genommen kein Gesundheitsdatum. Was gelöscht
werden musste, ist gelöscht.

## Aufgabe 2

**Suche findet die Nackendehnung**

Weil `suchen()` auch `description` durchsucht, und dort steht „Gegenschulter".

Gewollt? Für einen Katalog eher ja — man sucht nach Themen, nicht nach exakten
Namen. Wer „schulter" tippt, will vermutlich alles Schulterbezogene sehen.

Nur Namen durchsuchen:

```python
"WHERE deleted_at IS NULL AND name LIKE ? ORDER BY name", (muster,)
```

Besser wäre beides mit Gewichtung — Namenstreffer zuerst:

```sql
SELECT *, (CASE WHEN name LIKE ? THEN 0 ELSE 1 END) AS rang
FROM exercise
WHERE deleted_at IS NULL AND (name LIKE ? OR description LIKE ?)
ORDER BY rang, name
```

**`PRAGMA foreign_keys` bei jeder Verbindung**

Es ist eine Eigenschaft der *Verbindung*, nicht der Datei. Aus
Rückwärtskompatibilität: als SQLite Fremdschlüssel bekam, hätte ein
standardmäßiges Einschalten bestehende Programme zerbrochen, deren Daten die
Regeln verletzten.

Deshalb setzt `db.py::verbinden` es, und ein Test prüft, dass es wirkt.

## Aufgabe 3: ExerciseRepo

```python
"""Repositories — Lesen und Schreiben der Domänenobjekte."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from ..core.models import Exercise, jetzt
from ..core.result_spec import ResultSpec


class ExerciseRepo:
    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # -- Schreiben ---------------------------------------------------------

    def speichern(self, uebung: Exercise) -> None:
        """Legt an oder aktualisiert. `revision` steigt bei jeder Änderung."""
        uebung.updated_at = jetzt()
        self.con.execute(
            """
            INSERT INTO exercise
                (id, name, category, description, icon_key, image_path,
                 is_builtin, result_spec_json, limit_spec_json,
                 default_target_json, archived, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                category = excluded.category,
                description = excluded.description,
                icon_key = excluded.icon_key,
                image_path = excluded.image_path,
                result_spec_json = excluded.result_spec_json,
                limit_spec_json = excluded.limit_spec_json,
                default_target_json = excluded.default_target_json,
                archived = excluded.archived,
                updated_at = excluded.updated_at,
                revision = revision + 1
            """,
            (
                uebung.id,
                uebung.name,
                uebung.category,
                uebung.description,
                uebung.icon_key,
                uebung.image_path,
                int(uebung.is_builtin),
                json.dumps(uebung.result_spec.to_dict(), ensure_ascii=False),
                json.dumps(uebung.limit_spec, ensure_ascii=False),
                json.dumps(uebung.default_target, ensure_ascii=False),
                int(uebung.archived),
                uebung.created_at.isoformat(),
                uebung.updated_at.isoformat(),
            ),
        )

    def archivieren(self, uebung_id: str) -> None:
        """Aus den Listen nehmen, aber nicht löschen — alte Einträge
        verweisen darauf."""
        self.con.execute(
            "UPDATE exercise SET archived = 1, updated_at = ? WHERE id = ?",
            (jetzt().isoformat(), uebung_id),
        )

    # -- Lesen -------------------------------------------------------------

    def laden(self, uebung_id: str) -> Exercise | None:
        zeile = self.con.execute(
            "SELECT * FROM exercise WHERE id = ? AND deleted_at IS NULL",
            (uebung_id,),
        ).fetchone()
        return self._zeile(zeile) if zeile else None

    def alle(self, kategorie: str | None = None, mit_archivierten: bool = False) -> list[Exercise]:
        sql = "SELECT * FROM exercise WHERE deleted_at IS NULL"
        params: list[object] = []
        if not mit_archivierten:
            sql += " AND archived = 0"
        if kategorie:
            sql += " AND category = ?"
            params.append(kategorie)
        return [self._zeile(r) for r in self.con.execute(sql + " ORDER BY name", params)]

    def suchen(self, text: str) -> list[Exercise]:
        muster = f"%{text}%"
        return [
            self._zeile(r)
            for r in self.con.execute(
                """
                SELECT *, (CASE WHEN name LIKE ? THEN 0 ELSE 1 END) AS rang
                FROM exercise
                WHERE deleted_at IS NULL AND archived = 0
                  AND (name LIKE ? OR description LIKE ?)
                ORDER BY rang, name
                """,
                (muster, muster, muster),
            )
        ]

    def kategorien(self) -> list[str]:
        return [
            r["category"]
            for r in self.con.execute(
                "SELECT DISTINCT category FROM exercise "
                "WHERE deleted_at IS NULL AND archived = 0 AND category != '' "
                "ORDER BY category"
            )
        ]

    # -- Umwandlung --------------------------------------------------------

    @staticmethod
    def _zeile(r: sqlite3.Row) -> Exercise:
        return Exercise(
            id=r["id"],
            name=r["name"],
            category=r["category"],
            description=r["description"],
            icon_key=r["icon_key"],
            image_path=r["image_path"],
            is_builtin=bool(r["is_builtin"]),
            result_spec=ResultSpec.from_dict(json.loads(r["result_spec_json"])),
            limit_spec=json.loads(r["limit_spec_json"]),
            default_target=json.loads(r["default_target_json"]),
            archived=bool(r["archived"]),
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )
```

Tests:

```python
import pytest

from trainingsapp.core.models import Exercise
from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
from trainingsapp.data.db import oeffnen
from trainingsapp.data.repositories import ExerciseRepo


@pytest.fixture
def repo(tmp_path):
    return ExerciseRepo(oeffnen(tmp_path / "test.db"))


def test_speichern_und_laden(repo):
    u = Exercise(name="Testübung", category="Test", result_spec=SPEC_SAETZE_WDH)
    repo.speichern(u)

    zurueck = repo.laden(u.id)
    assert zurueck is not None
    assert zurueck.name == "Testübung"
    assert zurueck.result_spec.shorthand == "{sets}x{reps}"


def test_unbekannte_id_liefert_none(repo):
    """None, keine Ausnahme — die Ansicht soll das behandeln können."""
    assert repo.laden("gibt-es-nicht") is None


def test_nach_kategorie_filtern(repo):
    repo.speichern(Exercise(name="A", category="Schulter"))
    repo.speichern(Exercise(name="B", category="Nacken"))
    assert [u.name for u in repo.alle(kategorie="Schulter")] == ["A"]


def test_archivierte_verschwinden_aus_der_liste(repo):
    u = Exercise(name="Alt", category="Test")
    repo.speichern(u)
    repo.archivieren(u.id)

    assert repo.alle() == []
    assert len(repo.alle(mit_archivierten=True)) == 1
    # Direkt ladbar bleibt sie — alte Einträge verweisen darauf.
    assert repo.laden(u.id) is not None


def test_apostroph_im_namen(repo):
    u = Exercise(name="Dehnung n' Halt", category="Test")
    repo.speichern(u)
    assert repo.laden(u.id).name == "Dehnung n' Halt"
    assert len(repo.suchen("n' Halt")) == 1


def test_aktualisieren_erhoeht_revision(repo):
    u = Exercise(name="Vorher", category="Test")
    repo.speichern(u)
    u.name = "Nachher"
    repo.speichern(u)

    assert len(repo.alle()) == 1  # kein Duplikat
    assert repo.laden(u.id).name == "Nachher"
```

## Aufgabe 4: Seed

Die spannende Frage ist nicht das Einlesen, sondern: **Woran erkennt der Seed
beim zweiten Start, was schon da ist?** Das Schema hat keine Spalte für den
Seed-Schlüssel, und die IDs sind zufällig.

Drei Wege:

1. Den Schlüssel irgendwo unterbringen, etwa in `default_target_json`. Geht,
   ist aber ein Notbehelf — ein Feld, das für etwas anderes gedacht ist.
2. Eine Migration `002` mit Spalte `seed_key`. Sauber, kostet eine Migration.
3. **Die ID aus dem Schlüssel ableiten.** UUIDv5 erzeugt aus einem Namensraum
   und einem Text immer dieselbe UUID. „wadenheben" hat damit auf jedem Gerät
   dieselbe ID — ohne Zusatzspalte, und mit einem Nebeneffekt, der später in
   Edition B Gold wert ist: Der Praxisserver und das Handy meinen mit
   derselben ID dieselbe Übung.

So steht es in `src/trainingsapp/data/seed.py`:

```python
SEED_NAMENSRAUM = uuid.UUID("6f1c2b3a-7d4e-4a5b-9c8d-1e2f3a4b5c6d")


def seed_id(key: str) -> str:
    return str(uuid.uuid5(SEED_NAMENSRAUM, key))


def seed_einspielen(con: sqlite3.Connection, datei: Path = SEED_DATEI) -> int:
    repo = ExerciseRepo(con)
    neu = 0
    for uebung in seed_laden(datei):      # baut Exercise-Objekte mit seed_id()
        if repo.existiert(uebung.id):
            continue                       # vorhanden → unangetastet lassen
        repo.speichern(uebung)
        neu += 1
    return neu
```

Der Namensraum darf sich **nie** ändern — sonst bekämen alle mitgelieferten
Übungen beim nächsten Start neue IDs und würden ein zweites Mal angelegt.

`seed_laden()` ist bewusst von der Datenbank getrennt: Es liest das JSON und
baut Domänenobjekte. So lässt sich der Katalog testen, ohne eine Datenbank
anzulegen, und `seed_einspielen()` bleibt drei Zeilen Logik.

Tests dazu in `tests/test_repositories.py`:

```python
def test_seed_ist_wiederholbar(con) -> None:
    erste = seed_einspielen(con)
    assert erste > 0
    assert seed_einspielen(con) == 0           # nichts Neues
    assert len(ExerciseRepo(con).alle()) == erste


def test_seed_ueberschreibt_keine_aenderungen(con) -> None:
    seed_einspielen(con)
    repo = ExerciseRepo(con)
    u = repo.laden(seed_id("wadenheben"))
    u.description = "Meine eigene Beschreibung"
    repo.speichern(u)

    seed_einspielen(con)
    assert repo.laden(u.id).description == "Meine eigene Beschreibung"
```

## Zum Nachdenken

**1. Datei gelöscht, Datenbank behalten**

`hrv_recording` zeigt ins Leere. Die Kennzahlen im Cache bleiben lesbar — der
Verlauf ist also nicht weg. Aber die Rohdaten sind verloren, und eine
Neuberechnung ist unmöglich.

Die App sollte das erkennen und deutlich sagen: „Rohdaten nicht gefunden,
Kennzahlen stammen aus dem Cache." Stillschweigend so tun, als sei alles in
Ordnung, wäre schlecht — besonders bei Patientendaten.

**2. Wozu `sha1`?**

Um zu erkennen, dass eine Datei sich geändert hat. Dann ist der Kennzahlen-Cache
ungültig und muss neu berechnet werden.

Das ist kein hypothetischer Fall: In praxis_gui kann man eine Aufzeichnung
nachträglich beschneiden oder Artefakte korrigieren. Danach sind alle
abgeleiteten Werte falsch. `praxis_gui` macht es genauso — sein Sidecar trägt
ein `source_file_sha1`.

**3. Wann wäre eine Tabelle für Schläge doch besser?**

Wenn man **über viele Messungen hinweg** auf Schlagebene abfragen wollte, etwa:
„Zeig mir alle Schläge über 120 bpm aus dem letzten Jahr." Das ist mit SQL
trivial und mit 300 Dateien mühsam.

Das ist eine echte Abwägung. Für unseren Fall — eine Messung analysieren, viele
Messungen im Verlauf vergleichen — überwiegt der Kompatibilitätsgewinn. Käme
später eine Auswertung über alle Rohdaten hinzu, wäre ein zusätzlicher,
aufbaubarer Index vertretbar. **Zusätzlich**, nicht statt: die Datei bliebe die
Wahrheit.
