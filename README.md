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
```

**Release veröffentlichen** (eine APK, die die App als Update findet):

1. Version in `pyproject.toml` anheben (`uv lock` zieht `uv.lock` nach), committen,
   auf `main` pushen. Bei gleicher Version entscheidet nur die Build-Nummer —
   sauberer ist ein Versionssprung.
2. Tag setzen, **erst wenn `main` den Versionscommit enthält** (sonst steht die
   alte Version im Dateinamen):

   ```bash
   git pull && git tag v0.2.0 && git push origin v0.2.0
   ```

   Oder auf GitHub: Releases → „Draft a new release“ → „Choose a tag“ → `v0.2.0`
   eintippen → „Create new tag on publish“. Beides startet den Workflow.
3. Der Workflow baut rund eine Viertelstunde, signiert mit dem festen Schlüssel
   und hängt die APK an das Release (Pre-Release). Download ohne Anmeldung.


**Update aus der App heraus (Android):** Einstellungen → App → „Nach Updates
suchen“ fragt die GitHub-Releases ab (`core/update.py`). Gibt es eine neuere
Version, öffnet „Herunterladen“ die APK im Browser; antippen installiert sie
als Update über die bestehende App, die Daten bleiben (gleicher
Signierschlüssel). Dazu muss die Version in `pyproject.toml` angehoben sein —
bei gleicher Version entscheidet die Build-Nummer. iOS kennt keinen Weg am App
Store vorbei; dort bleibt es bei TestFlight/App Store. Download und Installation
innerhalb der App (Stufe 2) sind vorgemerkt (`docs/offene_fragen.md`, A8).

---

## Wo was liegt

```
src/trainingsapp/
  core/       Domänenmodelle, Notationsspezifikation, Limit-Regeln
  data/       SQLite, Migrationen, Repositories, Seed-Daten
  devices/    Sensoranbindung (BLE, Simulator)
  ui/         alles Flet-Spezifische
../hrv-core/  HRV-Mathematik (reines numpy, kein scipy) — Schwesterrepo, gemeinsam mit praxis_gui
docs/
  kompatibilitaet.md   ← der Datenformat-Vertrag mit praxis_gui
  architektur.md       Aufbau und Leitregeln
  datenmodell.md       Datenbankschema
  hrv_algorithmen.md   Verweis → hrv-core/docs (Formeln, Konstanten, Fallstricke)
  korrektur.md         Verweis → hrv-core/docs (automatische Korrektur)
  roadmap.md           Meilensteine
  offene_fragen.md     Katalog offener Entscheidungen und Befunde
  nachschlagen.md      externe Links (Flet-Icons, Docs, Spezifikationen)
  dependabot.md        Abhängigkeiten überwachen: Alerts, Sicherheits- und Versionsupdates
  recht/               DSGVO, MDR, Store-Freigaben
  tutorial/            der Lernpfad
```

**Die wichtigste Regel des Projekts:** `core/`, `data/` und `devices/`
importieren **niemals** `flet`. Ein Test erzwingt das. Dadurch bleibt alles ohne
Oberfläche testbar, und Flet-Versionswechsel betreffen nur `ui/`.

Die HRV-Bibliothek hrv-core muss als Schwesterordner `../hrv-core` neben dem
Projekt liegen (`git clone https://github.com/ben85keilert/hrv-core.git ../hrv-core`),
bevor `uv sync` läuft.

---

## Nachbarrepos

| Repo | Sichtbarkeit | Inhalt |
|---|---|---|
| [`hrv-core`](https://github.com/ben85keilert/hrv-core) | öffentlich | HRV-Mathematik, Austauschformat raw-v1 — Schwesterordner `../hrv-core`, einzige Abhängigkeit außerhalb von PyPI |
| [`praxis_gui`](https://github.com/ben85keilert/praxis_gui) | — | Praxissoftware, mit der das Datenformat kompatibel ist |
| `trainingsapp-praxis` | privat | Edition B (Praxisanbindung) |
| `trainingsapp-inhalte` | privat | Kurse und Übungspakete, die nicht mitgeliefert werden |
| `hrv-research` | privat | de-identifizierte Messungen, Notebooks |

**Regel:** Die öffentlichen Repos (`trainingsapp`, `hrv-core`) hängen nie von
einem privaten ab — nicht in `pyproject.toml`, nicht in der CI, nicht in Tests.
Die privaten Repos dürfen umgekehrt auf die öffentlichen aufbauen. Wer die App
baut, braucht nur dieses Repo und `hrv-core`.

**Inhalte pflegen** (`trainingsapp-inhalte`): Pakete als TOML, die App startet
direkt damit — `TRAININGSAPP_PAKETE=pakete` liest den Ordner bei jedem Start ein;
`uv run trainingsapp-paket pruefen|bauen|index` prüft die Dateien, schreibt JSON
fürs Handy und den Index einer Paketquelle. Details: `docs/uebungspakete.md`,
„Inhalte pflegen“.

Commit-Nachrichten tragen bei KI-unterstützter Arbeit `Co-Authored-By` und
einen Link auf die Claude-Code-Sitzung — bewusst sichtbar, damit nachvollziehbar
bleibt, was wie entstanden ist.

## Repo-Einstellungen (Sicherheit)

Beide öffentlichen Repos (`trainingsapp`, `hrv-core`) sind gleich eingestellt
(16.10.2026):

- **Dependabot:** Alerts und Sicherheitsupdates an; `.github/dependabot.yml`
  bündelt wöchentliche Versionsupdates für `uv.lock` (und hier die Actions) in
  einen PR. Die flet-Pakete sind ausgenommen — die wechseln bewusst, mit
  Build-Test und `flet-mcp` im Gleichschritt.
- **Secret-Scanning mit Push-Schutz:** ein Push mit erkanntem Token wird
  abgewiesen. Optional, nur über die Weboberfläche: Nicht-Anbieter-Muster und
  Gültigkeitsprüfung.
- **Ruleset „main schützen“:** kein Force-Push, kein Löschen. Normale Pushes
  auf `main` bleiben erlaubt.
- **Actions:** nur GitHub-eigene und verifizierte Ersteller, dazu
  `astral-sh/setup-uv` und `softprops/action-gh-release`. Workflow-Token nur
  lesend (das Release-Job hebt `contents: write` selbst an); Fork-PRs von
  Erstbeitragenden laufen erst nach Freigabe.
- **Signierschlüssel** nur in den Repository-Secrets (Fork-PRs sehen sie nicht)
  und lokal unter `~/.trainingsapp-signierung/`.

Ausführlich mit Beispielen: [docs/dependabot.md](docs/dependabot.md).
Wer eine Dependabot-Meldung bekommt: `uv lock --upgrade-package <paket>`, Tests,
committen. Zieht ein Paket eine verwundbare Version fest (wie `neurokit2 0.2.13`
→ `setuptools < 82` in hrv-core), hilft `uv lock --upgrade-package '<paket>>=<fix>'`,
uv weicht dann auf einen passenden Stand aus.

## Lizenz

[AGPL-3.0](LICENSE). Beiträge unterliegen der CLA in [CONTRIBUTING.md](CONTRIBUTING.md),
die dem Projektinhaber die Dual-Lizenzierung offenhält.
