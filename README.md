# Trainingsassistent

Eine App für Bewegungsübungen mit begleitender HRV-Messung — gebaut mit
[Flet](https://flet.dev) (Python steuert eine Flutter-Oberfläche).

Das Datenformat ist kompatibel zu [`praxis_gui`](https://github.com/ben85keilert/praxis_gui),
sodass Messungen dort weiterverarbeitet werden können.

---

## Was die App können soll

- **Übungskatalog** — ein mitgelieferter, erweiterbarer Satz Übungen mit Erklärvideos.
  Eigene Übungen mit Symbol oder Foto anlegen.
- **Trainingsdokumentation** — sehr flexible Notation (`3x15`, Gradangaben,
  Haltezeiten, Gewichte …) mit möglichst wenig Klicks.
- **Fortschritt** — Messwerte und Benchmarks grafisch über die Zeit.
- **Live-HRV** — Messung über BLE-Sensoren, mit Zugriff auf die **Rohdaten**,
  nicht nur auf Endergebnisse.
- **Limits** — Timer, Zähler und pulsbasierte Regeln zur Trainingssteuerung.

Zwei Ausbaustufen:

| Edition | Zweck |
|---|---|
| **A — „solo"** | autark, alle Daten bleiben auf dem Gerät |
| **B — „praxis"** | Anbindung an die Praxisdatenbank, Therapeut↔Patient |

---

## Das hier ist ein Lernprojekt

Die App entsteht Schritt für Schritt entlang eines Lernpfads. Jede Lektion
erklärt ein Thema, lässt dich üben — und danach bauen wir den nächsten Teil
der App.

**→ Start: [`docs/tutorial/README.md`](docs/tutorial/README.md)**

Der Lernpfad setzt Python-Grundlagen voraus (Funktionen, Klassen, Listen,
etwas `numpy`/`sqlite3`). Flet, async, BLE und Packaging werden von Grund auf
erklärt.

---

## Schnellstart

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

flet run src/trainingsapp/ui/app.py     # Desktop-Vorschau
pytest                                   # Tests
ruff check .                             # Linter
```

---

## Wo was liegt

```
src/trainingsapp/
  core/       Domänenmodelle, Notationsspezifikation, Limit-Regeln
  data/       SQLite, Migrationen, Repositories, Seed-Daten
  hrv_core/   HRV-Mathematik (reines numpy, kein scipy)
  devices/    Sensoranbindung (BLE, Simulator)
  ui/         alles Flet-Spezifische
docs/
  kompatibilitaet.md   ← der Datenformat-Vertrag mit praxis_gui
  architektur.md       Aufbau und Leitregeln
  datenmodell.md       Datenbankschema
  hrv_algorithmen.md   Formeln, Konstanten, Fallstricke
  roadmap.md           Meilensteine
  recht/               DSGVO, MDR, Store-Freigaben
  tutorial/            der Lernpfad
```

**Die wichtigste Regel des Projekts:** `core/`, `data/`, `hrv_core/` und
`devices/` importieren **niemals** `flet`. Ein Test erzwingt das. Dadurch
bleibt alles ohne Oberfläche testbar, und ein späterer Umstieg auf Flet 1.0
betrifft nur `ui/`.

---

## Lizenz

[AGPL-3.0](LICENSE). Beiträge unterliegen der CLA in [CONTRIBUTING.md](CONTRIBUTING.md),
die dem Projektinhaber die Dual-Lizenzierung offenhält.
