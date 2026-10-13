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

Benötigt [uv](https://docs.astral.sh/uv/) — es kümmert sich um Python-Version,
virtuelle Umgebung und Abhängigkeiten (gepinnt in `uv.lock`).

```bash
uv sync                                        # Umgebung anlegen + alles installieren

uv run flet run src/trainingsapp/ui/app.py     # Desktop-Vorschau
uv run flet run --android src/trainingsapp/ui/app.py   # auf dem Smartphone (siehe unten)
uv run pytest                                  # Tests
uv run ruff check .                            # Linter
```

**Auf dem Smartphone testen, ohne APK zu bauen:** Auf dem Android-Gerät die
App „Flet" aus dem Play Store installieren, Handy und Rechner ins selbe WLAN,
dann `uv run flet run --android src/trainingsapp/ui/app.py`. Im Terminal
erscheint ein QR-Code; den mit der Flet-App scannen. Der Python-Code läuft
dabei auf dem Rechner, das Handy zeigt nur die Oberfläche — Änderungen am
Code sind nach Neustart des Befehls sofort sichtbar (mit `-d` auch ohne). Für
Bluetooth braucht es eine gebaute APK (siehe unten und Lernpfad L02b).

Alternativ lässt sich die Umgebung klassisch aktivieren — dann entfällt das
`uv run`-Präfix:

```bash
source .venv/bin/activate        # Windows: .venv\Scripts\activate
flet run src/trainingsapp/ui/app.py
```

Der Unterschied: `uv run` prüft vor jedem Aufruf, ob die Umgebung noch zu
`uv.lock` passt, und synct bei Bedarf automatisch nach. Im aktivierten venv
entfällt diese Prüfung — ändert sich `uv.lock` (z. B. durch `git pull`), muss
man selbst an `uv sync` denken.

---

## APK bauen und Updates einspielen

Android spielt ein Update nur ein, wenn es mit **demselben Schlüssel** signiert
ist wie die installierte App. Ein anderer Schlüssel heißt: deinstallieren, und
mit der App verschwinden ihre Daten (Messungen, eigene Übungen). Darum
signieren Skript und CI immer mit dem festen Schlüssel.

**Lokal bauen** (braucht JDK 17 und das Android SDK; Flutter lädt `flet build`
beim ersten Lauf selbst, ein Build dauert rund 10 Minuten):

```bash
uv run python scripts/apk_bauen.py          # signiert → updatefähig
uv run python scripts/apk_bauen.py --debug  # Wegwerf-Build, NICHT updatefähig
```

Ergebnis: `dist/trainingsapp-<version>-<build>.apk`. Die APK aufs Handy
kopieren und antippen; eine schon installierte App wird dabei aktualisiert,
ihre Daten bleiben.

Das Skript findet den Schlüssel über `signierung.toml` im Projektordner (nicht
eingecheckt). Fehlt die Datei, bricht es ab, statt still eine APK zu bauen,
die sich nicht über die bisherige installieren lässt.

- **Build-Nummer** = Zahl der Commits. Android nimmt ein Update nur mit
  gleicher oder höherer Nummer an, also vom committeten Stand bauen.
  Uncommittete Änderungen erhöhen die Nummer nicht.
- **Neuer Rechner:** `~/.trainingsapp-signierung/upload-keystore.jks` und
  `signierung.toml` aus der Sicherung zurückkopieren.
  `scripts/signierschluessel.py` nur beim allerersten Einrichten ausführen:
  Ein neuer Schlüssel macht Updates der installierten App unmöglich.
- **Schlüssel sichern** (Passwortmanager, zweiter Datenträger). Ohne ihn gibt
  es kein Update mehr, nur noch Neuinstallation.
- `build/` nie komplett löschen (`build/*.toml` ist versioniert), sondern
  `git clean -fdX build/`.

**Über GitHub bauen:** Der Workflow „APK“ nutzt dasselbe Skript und dieselben
Schritte. Den Schlüssel bekommt er aus den Repository-Secrets
`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD` und `ANDROID_KEY_ALIAS`.

```bash
gh workflow run apk.yml                     # APK als Artefakt am Lauf (ZIP, 30 Tage)

# Release mit herunterladbarer APK: Version in pyproject.toml anheben, committen, dann
git tag v0.2.0 && git push origin v0.2.0
```

Das Release erscheint als Pre-Release unter „Releases“. Das Repository ist
privat, darum braucht der Download am Handy eine GitHub-Anmeldung im Browser.

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
  nachschlagen.md      externe Links (Flet-Icons, Docs, Spezifikationen)
  recht/               DSGVO, MDR, Store-Freigaben
  tutorial/            der Lernpfad
```

**Die wichtigste Regel des Projekts:** `core/`, `data/`, `hrv_core/` und
`devices/` importieren **niemals** `flet`. Ein Test erzwingt das. Dadurch
bleibt alles ohne Oberfläche testbar, und Flet-Versionswechsel betreffen nur
`ui/`.

---

## Lizenz

[AGPL-3.0](LICENSE). Beiträge unterliegen der CLA in [CONTRIBUTING.md](CONTRIBUTING.md),
die dem Projektinhaber die Dual-Lizenzierung offenhält.
