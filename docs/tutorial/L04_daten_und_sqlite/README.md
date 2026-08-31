# L04 — Datenmodell und SQLite

**Ziel:** Übungen kommen aus der Datenbank statt aus einer JSON-Datei. Und du
schreibst ab jetzt Tests.

Zeit: zwei bis drei Stunden.

Hier bist du im Vorteil — `sqlite3` und QtSQL kennst du. Neu sind vor allem die
**Migrationen**, das **Repository-Muster** und die Frage, was überhaupt in die
Datenbank gehört.

---

## 1. Migrationen ohne Verwaltungstabelle

Das Schema wird sich ändern. Nach dem ersten Nutzer geht „Datenbank löschen und
neu anlegen" nicht mehr.

SQLite bringt dafür alles mit: `PRAGMA user_version` ist ein Integer, den man
frei belegen kann. Wir nutzen ihn als Schemaversion. Keine zusätzliche Tabelle,
keine Bibliothek.

```
data/migrations/
├─ 001_init.sql       ← Ausgangsschema
├─ 002_....sql        ← kommt später
```

```python
def migrieren(con, ordner=MIGRATIONS_DIR) -> int:
    aktuell = schema_version(con)
    for nummer, datei in verfuegbare_migrationen(ordner):
        if nummer <= aktuell:
            continue  # schon eingespielt
        con.execute("BEGIN")
        try:
            con.executescript(datei.read_text(encoding="utf-8"))
        except Exception:
            con.execute("ROLLBACK")  # lieber alt als halb migriert
            raise
        con.execute(f"PRAGMA user_version = {nummer}")
        aktuell = nummer
    return aktuell
```

Regeln:
- Eine eingespielte Migration wird **nie** verändert. Korrekturen sind eine neue Datei.
- Jede läuft in einer eigenen Transaktion.
- Wiederholtes Ausführen tut nichts — `tests/test_core.py` prüft das.

---

## 2. Zwei PRAGMAs, die man setzen muss

```python
con.execute("PRAGMA foreign_keys = ON")
con.execute("PRAGMA journal_mode = WAL")
```

**`foreign_keys`** — SQLite prüft Fremdschlüssel standardmäßig **nicht**. Die
Einschränkungen stehen im Schema und werden ignoriert. Aus
Kompatibilitätsgründen, seit Jahrzehnten. Ohne dieses PRAGMA sind alle
`REFERENCES` reine Dokumentation.

**`journal_mode = WAL`** — Lesen blockiert nicht während des Schreibens. Wichtig,
wenn während einer laufenden Messung Diagramme gezeichnet werden.

---

## 3. Repository statt SQL in der Oberfläche

Das Muster kennst du von QtSQL. Der Punkt ist: **SQL an einer Stelle.**

```python
class ExerciseRepo:
    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def alle(self, kategorie: str | None = None) -> list[Exercise]:
        sql = "SELECT * FROM exercise WHERE deleted_at IS NULL"
        params: list[object] = []
        if kategorie:
            sql += " AND category = ?"
            params.append(kategorie)
        return [self._zeile(r) for r in self.con.execute(sql + " ORDER BY name", params)]
```

Die Ansicht ruft `repo.alle(kategorie="Schulter")` und weiß nichts von SQL.
Ändert sich das Schema, ist eine Datei betroffen.

**Platzhalter, immer:**

```python
con.execute("SELECT * FROM exercise WHERE name = ?", (name,))  # richtig
con.execute(f"SELECT * FROM exercise WHERE name = '{name}'")  # falsch
```

Das ist nicht nur wegen SQL-Injection. Platzhalter behandeln auch Anführungszeichen,
`NULL` und Typen korrekt — eine Übung namens „Dehnung n' Halt" bricht die zweite
Variante sofort.

---

## 4. Objekte aus Zeilen

`sqlite3.Row` erlaubt Zugriff über Spaltennamen. Die Umwandlung in Dataclasses
gehört ins Repository:

```python
def _zeile(self, r: sqlite3.Row) -> Exercise:
    return Exercise(
        id=r["id"],
        name=r["name"],
        category=r["category"],
        # JSON-Spalten werden hier ausgepackt, nicht in der Ansicht
        result_spec=ResultSpec.from_dict(json.loads(r["result_spec_json"])),
        is_builtin=bool(r["is_builtin"]),  # SQLite kennt kein bool
        created_at=datetime.fromisoformat(r["created_at"]),
    )
```

Zwei Dinge, die SQLite nicht kann und die deshalb hier passieren:

- **Kein `bool`** — 0 und 1 sind Integer. `bool(r["is_builtin"])`.
- **Kein `datetime`** — wir speichern ISO-8601-Text (`2026-08-06T08:15:00+00:00`).
  Das sortiert korrekt als Text und ist lesbar, wenn man mit `sqlite3` direkt
  hineinschaut.

---

## 5. Was NICHT in die Datenbank gehört

Die HRV-Rohdaten. Eine Stunde Messung sind rund 4200 Herzschläge. Trotzdem gibt
es **keine** Tabelle dafür. Die Gründe stehen in `docs/architektur.md`, kurz:

- Der Kompatibilitätsvertrag mit `praxis_gui` hinge sonst an einer
  Übersetzungsschicht. So ist der Export ein Dateikopiervorgang.
- Während der Messung wäre es ein `INSERT` pro Schlag, gleichzeitig zu Rechnen
  und Zeichnen. Eine Datei alle 15 Sekunden zu schreiben ist robuster gegen
  Absturz und leeren Akku.

Stattdessen: `hrv_recording` speichert den **Pfad** und einen SHA-1 der Datei.
`hrv_metrics_cache` hält die berechneten Kennzahlen — mit einer `algo_version`,
damit sie bei einer Änderung der Rechenvorschrift neu berechnet werden.

Das ist eine bewusste Ausnahme vom Naheliegenden. Sie hat einen konkreten Grund,
und der ist dokumentiert.

---

## 6. Tests — ab hier immer

Ab jetzt gehört zu jeder Funktion ein Test. Nicht aus Prinzip, sondern weil das
Folgende ohne Tests nicht mehr beherrschbar ist: die HRV-Formeln in L08/L09
lassen sich am Bildschirm nicht auf Richtigkeit prüfen.

```python
def test_migration_erzeugt_das_schema(tmp_path):
    con = oeffnen(tmp_path / "test.db")  # tmp_path räumt pytest auf
    assert schema_version(con) == 1
    tabellen = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "exercise" in tabellen
```

`tmp_path` ist eine pytest-Einrichtung: ein frisches Verzeichnis je Test, das
danach verschwindet. Jeder Test bekommt eine eigene Datenbank und beeinflusst
keinen anderen.

Nützlich:

```bash
pytest                          # alles
pytest tests/test_core.py -v    # eine Datei, ausführlich
pytest -k migration             # alles, dessen Name "migration" enthält
pytest -x                       # beim ersten Fehler abbrechen
```

---

## 7. Beispiele

```bash
uv run python docs/tutorial/L04_daten_und_sqlite/beispiel_01.py   # Migrationen
uv run python docs/tutorial/L04_daten_und_sqlite/beispiel_02.py   # Repository
uv run python docs/tutorial/L04_daten_und_sqlite/beispiel_03.py   # Fremdschlüssel & Fallen
```

---

## Stolperfallen

**Fremdschlüssel greifen nicht** — `PRAGMA foreign_keys = ON` fehlt. Muss bei
**jeder** Verbindung gesetzt werden, es ist keine Eigenschaft der Datei.

**`sqlite3.OperationalError: database is locked`** — eine andere Verbindung
schreibt. WAL entschärft das; ansonsten Transaktionen kurz halten.

**`datetime` kommt als String zurück** — richtig so. `datetime.fromisoformat()`
im Repository.

**`bool` ist plötzlich `0`** — SQLite kennt keinen Wahrheitswert.
`bool(r["spalte"])`.

**`executescript` und Transaktionen** — `executescript` schließt eine offene
Transaktion selbst. Ein `COMMIT` danach ist je nach Skriptinhalt ein Fehler.
Deshalb setzt `db.py` die Version in einer eigenen Anweisung.

---

## Weiter

→ [Übung](uebung.md) → [Checkliste](checkliste.md) → **L05: Übungskatalog**
