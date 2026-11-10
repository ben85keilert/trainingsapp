# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Sprache

Code und Bezeichner englisch, wenn es die verbreitete Schreibweise ist; Kommentare,
Docstrings und Dokumentation deutsch. **Feldnamen des Austauschformats bleiben so,
wie `praxis_gui` sie schreibt** (`intervall_quelle`, `messungen`, …) — dort zählt
Kompatibilität, nicht Konsistenz. Neuer Text (Antworten, Commit-Messages) auf Deutsch.

## Befehle

Das Projekt wird mit [uv](https://docs.astral.sh/uv/) verwaltet (`uv.lock` ist die
Wahrheit, `.python-version` pinnt Python).

Die HRV-Bibliothek **hrv-core** (github `ben85keilert/hrv-core`) ist ein Schwesterrepo und
muss als `../hrv-core` neben diesem Ordner liegen — `pyproject.toml` bindet sie editierbar
ein (`[tool.uv.sources]`, `[tool.flet.dev_packages]`), die CI checkt beide Repos nebeneinander aus.
Lokal gilt der Ordner `../hrv-core`, wie er gerade steht; **CI und APK-Build nehmen den Commit aus
`hrv-core.ref`** (eine Zeile, voller SHA) — bei jeder hrv-core-Änderung, die die App braucht, wird
die Datei bewusst angehoben (`git -C ../hrv-core rev-parse origin/main > hrv-core.ref`), Dependabot
fasst sie nicht an. **Ebenso `../hrv-watch`** (Uhr am Handgelenk, Ben 26.10.2026): die Flet-Erweiterung
`flet_medien` kommt aus `../hrv-watch/flet_medien`, CI und APK-Build nehmen den Commit aus
`hrv-watch.ref` (`git -C ../hrv-watch rev-parse origin/main > hrv-watch.ref`).

```bash
git clone https://github.com/ben85keilert/hrv-core.git ../hrv-core   # einmalig, Schwesterordner (öffentlich, AGPL-3.0)
uv sync --extra desktop                # Entwicklungsumgebung (desktop = bleak für BLE)

uv run flet run src/trainingsapp/ui/app.py    # Desktop-Vorschau der Oberfläche
uv run flet run --android src/trainingsapp/ui/app.py   # Vorschau auf dem Handy (Flet-App aus dem Play Store, gleiches WLAN, QR-Code)
uv run pytest                                  # alle Tests
uv run pytest tests/test_messlauf.py           # eine Datei
uv run pytest tests/test_messlauf.py::test_name -q   # ein einzelner Test
uv run pytest --doctest-modules src/trainingsapp/core src/trainingsapp/devices   # Doctests (laufen in CI)
uv run ruff check . && uv run ruff format --check .   # Linter + Formatprüfung
uv run mypy                                    # Typprüfung (Paket ist in pyproject konfiguriert)
uv run python scripts/pruefe_flet_beispiele.py   # Flet-Skripte des Lernpfads ohne Bildschirm (CI)
```

Vor jedem Pull Request muss laufen:
`uv run ruff check . && uv run ruff format --check . && uv run pytest`.

**Flet-API nachschlagen:** `.mcp.json` registriert den MCP-Server `flet` (`uv run flet mcp`,
Paket `flet-mcp` in der Gruppe `flet-dev`). Er kennt die API der installierten Flet-Version —
vor dem Schreiben von `ui/`- oder Tutorial-Code dort prüfen statt aus dem Gedächtnis, denn
Flet hat zwischen 0.28, 0.80 und 1.0 viel umbenannt und entfernt. `flet-mcp` immer in
derselben Version wie `flet` halten.

`TRAININGSAPP_EDITION=praxis uv run pytest …` bzw. `TRAININGSAPP_DATA_DIR=…` setzen
Edition und Datenpfad zur Laufzeit (siehe `config.py`).

## Die eine Architekturregel

`core/`, `data/` und `devices/` importieren **niemals** `flet`; nichts unter
`trainingsapp/` importiert **jemals** `scipy`. `tests/test_import_regel.py` erzwingt beides
per AST-Scan — es ist kein Stilhinweis, sondern ein grüner Test, der brechen muss, wenn
man dagegen verstößt.

Gründe: Die Domäne bleibt ohne Bildschirm testbar, und Flet-Versionswechsel (zuletzt
0.86 → 1.0) oder ein Umstieg auf das deklarative Modell betreffen nur `ui/`. `scipy`
existiert auf Android/iOS nicht — darum implementiert hrv-core Welch, Lomb-Scargle,
DFA und SampEn selbst in reinem numpy.

**Die HRV-Mathematik ist seit dem 16.10.2026 die externe Bibliothek `hrv_core`**
(Schwesterrepo hrv-core, nur numpy; gemeinsam mit praxis_gui, damit beide Apps dieselben
Zahlen liefern). Algorithmen, Korrekturregeln, Live-Fenster, Aufnahme und das Austauschformat
raw-v1 werden **dort** geändert, nie hier nachgebaut. In der App bleiben nur Anwendungsteile:
`core/hrv_export.py` (ZIP, Diagnoseprotokoll), `core/hrv_training.py` (HRV je Kilometer,
DFA-Überblick), `devices/messlauf.py` (Orchestrierung), `ui/`.

Abhängigkeiten zeigen **nur nach innen**: `ui → core, data, hrv_core, devices`;
`devices → hrv_core, core` (GPS-Punkte: `core.strecke`); `data → core`;
`core → (nur hrv_core)`; `hrv_core → (nur numpy)`.
Keine Rechenlogik in `ui/` — Views rufen Funktionen aus den unteren Schichten auf.

## Aufbau

```
src/trainingsapp/
  config.py    Edition (solo/praxis), Funktionsschalter, Speicherorte
  core/        Domänenmodelle, ResultSpec (Notation), Limit-Regeln, Einheiten
  data/        SQLite (kein ORM), .sql-Migrationen, Seed-Daten
  devices/     Geräte-Port (BLE/Simulator), Geräteprofile
  ui/          Flet — dünn
../hrv-core/src/hrv_core/   HRV-Mathematik + Austauschformat raw-v1 (Schwesterrepo, extern)
```

**Nachbarrepos:** `trainingsapp` und `hrv-core` sind öffentlich und hängen **nie** von
einem privaten Repo ab (`trainingsapp-praxis`, `trainingsapp-inhalte`, `hrv-research`) —
nicht in `pyproject.toml`, CI oder Tests. Commit-Nachrichten behalten `Co-Authored-By`
und den Sitzungslink (Ben, 16.10.2026: Nachvollziehbarkeit).

## Zentrale Entwurfsentscheidungen

Diese ergeben sich erst aus mehreren Dateien zusammen — hier verdichtet:

- **Die Datei ist die Wahrheit.** HRV-Rohdaten liegen als `raw-v1`-JSON-Dateien
  (byte-kompatibel zu `praxis_gui`), **nicht** in der Datenbank. Die DB hält nur den
  Verweis (`hrv_recording.file_path`) und einen Kennzahlen-Cache (`hrv_metrics_cache`)
  mit `algo_version`. Ändert sich die Rechenvorschrift (`ALGO_VERSION` in
  `hrv_core/constants.py`), gilt der Cache als veraltet und wird aus den Dateien neu
  berechnet — Rohdaten bleiben unangetastet. Export = Dateikopie. Vertrag:
  `docs/kompatibilitaet.md` — Formatänderungen brauchen dort zuerst einen Eintrag.
  Ausnahme wie in praxis_gui: Metadaten (`titel`, `notiz`, `ereignisse` = Notizen mit
  Anker) werden in die Messdatei zurückgeschrieben (`hrv_core.ereignisse`), nie die
  Messwerte.

- **GPS-Daten werden nie geteilt** (Ben, 14.10.2026): Sync, Export-ZIP,
  Teilen, Diagnose — keine Koordinaten. Strecken liegen getrennt von
  `Messungen/` (`config.streckenverzeichnis()`). Einzige Ausnahme: der
  GPX-Export, den die Person selbst auslöst (`docs/plan_gps.md`, Abschnitt 0) — einzeln
  in der Auswertung, alle unter Aufzeichnungen → Strecken nach Rückfrage, in eigener
  Verantwortung. **Ortsfrei darf mit** (Ben, 26.10.2026): Messungs- und Forschungsexport
  legen zu jedem Training die **Rohspur ohne Ort** unter `Bewegung/` (`core/bewegung.py`,
  `docs/kompatibilitaet.md` §13) — Abstand je Fix, Tempo, Höhe, Genauigkeit roh; nie
  Breite, Länge oder **Richtung** (Abstand plus Richtung wäre Koppelnavigation).
  Dasselbe gilt für **Anhänge** (Ben, 19.10.2026): Fotos und Videos an Einträgen — seit
  22.10.2026 auch Audioaufnahmen (`.m4a`, flet-audio-recorder, abgespielt mit flet-audio) und
  Anhänge am Tag (Notiz zum Tag: `core.anhaenge.Ziel`, Migration 029) — liegen
  unter `Anhaenge/<JJJJ>/<MM>/` (`config.anhaengeverzeichnis()`, Tabelle `entry_media`,
  `core/anhaenge.py`), kommen aus der Kamera der App (flet-camera, drei Qualitäten) oder aus
  der Fotoauswahl (`erweiterungen/flet_hochladen`: keine Berechtigung, verkleinert, **ohne
  Ortsangabe** — die App prüft nach) und gehen nie in Export, Backup oder Sync — nur
  „Teilen“ am Einzelbild. Kein Video läuft
  außerhalb der Ansicht `/anhang/<id>`; Tag, Tagebuch und Übung zeigen Frontbilder
  (`ui/components/anhang_reihe.py`). Vertrag: `docs/plan_anhaenge.md`. **Eigene Bilder als
  Symbol einer Übung** (Ben, 2.11.2026) liegen in der Ablage `Medien/Symbole/`
  (`data/uebungsbilder.py`, `exercise.image_path`; Weg ``uebung/<id>`` in Kamera und
  Fotoauswahl, Blatt `components/symbol_blatt.py`), gezeigt über
  `components/uebungsbild.uebungsbild` statt `ft.Icon(symbol(…))`, quadratisch mit runden
  Ecken (P109, auch PNG) — ebenfalls nie in Paket, Export oder Sync.

- **Zwei Editionen aus einem Quelltext.** `config.ist_aktiv("funktion")` beantwortet
  „darf ich X?" statt „bin ich Edition B?". Ein Schalter je Fähigkeit, nicht je
  Bildschirm. `physiologische_steuerung` ist in `solo` **rechtlich** gesperrt (eine
  Handlungsempfehlung aus Messwerten wäre eine medizinische Aussage — siehe
  `docs/recht/00_zweckbestimmung.md`). Sync-Felder (`outbox`, `external_ref`,
  `origin_device_id`, `deleted_at`) existieren ab Migration 001, obwohl `solo` sie nicht
  nutzt.

- **Konflikte strukturell vermeiden.** `hrv_recording` und `session_entry` sind
  **unveränderlich** — eine Korrektur ist ein neuer Eintrag mit `replaces_entry_id`.
  Nur veränderliche Metadaten nutzen „letzter Schreiber gewinnt" mit serverseitiger
  Revision. Statt `dirty`-Flag eine reihenfolgetreue `outbox`.

- **ResultSpec = flexible Notation.** Jede Übung bringt eine `ResultSpec`
  (`core/result_spec.py`) mit, aus der die Eingabemaske erzeugt wird — „3x15", „45°",
  „30 s halten" sind derselbe Mechanismus. Felder kommen aus dem `FELDVORRAT`; das
  Satzfeld (`SET_LIST`) speichert eine Liste je Satz und nimmt die Notation aus
  `docs/notation.md` entgegen (`3x15`, `30`, `15/15/20`, `+20`). Hierarchie: Übung →
  Plan → Eintrag; die **Planübung folgt der Übung**, bis man im Plan etwas ändert (Ben,
  22.10.2026, P79: `target`/`felder` ``None`` = wie die Übung, „nur hier“ ↺,
  `core/standards.py`; keiner = nur abhaken). **Zwei Orte zum Einstellen** — „Übung
  bearbeiten“ (gilt überall, über Übungsseite → Stift) und „Im Plan einstellen“ (gilt nur
  dort); das i führt überall zur Übungsseite, die nichts ändert; beim Üben gilt eine Wahl
  für jetzt (`docs/plan_uebungen_einstellen.md`). Jeder `SessionEntry` speichert eine Kopie der
  Spec, mit der er erfasst wurde (`spec_snapshot_json`); angezeigt wird **immer** mit der
  Kopie, nie mit der aktuellen Definition. Neuer `FieldType` → hier ergänzen und in
  `ui/components/spec_form.py` ein Widget registrieren. **„Übung bearbeiten“** (Ben,
  2.11.2026, `docs/plan_uebung_bearbeiten.md`): Parameter als Knöpfe, je eingeschaltetem
  eine Karte mit eigenem Namen (`FieldSpec.label` gehört der Übung), Chips (✕ nimmt einen
  ungenutzten aus der Wahl), Sätze und dem **Ziel** (`default_target`); Erklärtexte im (i)
  (`components/hilfe.py`), keine inline. **Mehrfachfelder einer Art** (P106, Ben 2.11.2026):
  ``hold_2``, ``scale_2`` … — die Schlüssel des Vorrats bleiben die *Art*
  (`core.result_spec.basis_key`, `vorrat_feld`, `naechster_key`); wer nach der Art fragt
  (Haltezeit, Zeit, Timer „zählt als“ je Zeitfeld), vergleicht `basis_key`, nie den
  Schlüssel. **Beschreibung in Abschnitten** (P108): ein Text mit ``## Name``-Zeilen
  (`core/beschreibung.py`), nie ein zweites Feld. „Im Plan einstellen“ hat dieselbe Ordnung
  (P107). Vertrag: `docs/plan_uebung_bearbeiten.md`.

- **Übungen kommen über Pakete** (Ben, 14.10.2026). Der mitgelieferte Katalog ist
  das Paket „Standard“ (`data/seed/standard.toml` — TOML, weil von Hand gepflegt; IDs per UUIDv5
  aus dem Schlüssel); weitere kommen per Import, der Export schreibt nur Übungen.
  `exercise.package_id` = Herkunft, `NULL` = eigene Übung (auch Kopien). Ein Import
  aktualisiert nur die Übungen desselben Pakets — **was die Person geändert hat, bleibt**
  (Ben, 16.10.2026: Drei-Wege-Abgleich je Feld gegen den Paketstand,
  `core/pakete.zusammenfuehren`; seit 9.11.2026 die Beschreibung **je Abschnitt** und Medien
  **je Eintrag**, `core/abgleich.py`, mit Hinweisen und „Mit dem Paket vergleichen“ —
  `docs/plan_paketinhalte.md`, Stufen U1–U7); eigene Übungen ändert er nie. **Paketpläne je
  Planübung** (U2, 9.11.2026): `core.pakete.plan_abgleichen` (Planübung = Übung + wievieltes
  Vorkommen, IDs bleiben, mit Ablauf/Zweigen und verschobenen Stellen bleibt die eigene Fassung),
  „Neu laden …“ im Plan-Editor (`components/neu_laden.py`: Fehlendes zurückholen · Auf
  Paketstand bzw. Wie im Kapitel), „Wieder anlegen“ im Paketmanager, „Kurs neu laden …“;
  **Anweisungen je Planübung** (`plan_item.description`/`media_json`, Migration 046, Paketfeld
  `beschreibung`/`medien`) in „Im Plan einstellen“ und im „i“, beim Üben der Knopf **Material**
  (`core/material.py`, `components/material.py`) — **solange das Blatt offen ist, steht die Uhr
  dieser Übung** (`einheit_ui.uhr_fuer_material_anhalten`), Schließen lässt sie weiterlaufen. **Pakete mit
  Dateien** (U3, 9.11.2026): ZIP (Formatversion 4) mit `paket.json` und
  `medien/<sha256>.<endung>`, Medium `source = "paket"` (Migration 047), Ablage
  `Medien/Pakete/` neben der Datenbank (`data/paketmedien.py`, räumt auf), Lesen/Schreiben
  `core/paketdatei.py` (auch TOML mit `datei = "…"`), **jede Datei vor dem Weitergeben ohne
  Ortsangaben** (`core/bereinigen.py` — was nicht sicher geht, kommt nicht ins Paket; im PDF
  werden die Exif-Blöcke eingebetteter JPEGs an Ort und Stelle geleert), Anzeige
  `components/medienliste.py` und `…/paketmedium/<datei>`. **Eigene Pakete** (U4): Karte im
  Paketmanager (`views/eigene_pakete.py`, Migration 048 `own_package`, feste ID, Version
  vorschlagen nach Inhalts-Prüfsumme), „Datei fürs Paket“ in beiden Editoren (sofort bereinigt,
  `ui/paketdatei.py`, Ziel `paketdatei/…` für Kamera und Fotoauswahl). Datenbank nie in
  `asyncio.to_thread` — dort nur Dateien (SQLite gehört dem Event-Loop). **Ergänzungen**
  (U5): `ergaenzungen[]` (Formatversion 5) ergänzen Übungen anderer Pakete — Abschnitte, Medien,
  Parameter, Ziel, Timer, Takt (`core/ergaenzungen.py`); wirksamer Paketstand = Grund
  (`package_base_json`) + Ergänzungen (`exercise_addon`, Migration 049), abgeglichen wie ein
  Update (`PaketRepo.ergaenzungen_anwenden`) — Eigenes bleibt. **Private Pakete** (U7):
  verschlüsselt mit einem 8-stelligen Code (`core/privat.py`, nur stdlib: scrypt, SHAKE-256,
  HMAC), Link in einem Ordner mit Zufallsnamen; die App fragt beim Import nach dem Code
  (`CodeNoetig`/`ZugangNoetig`), merkt ihn sich (`package.access_json`, Migration 050) und
  öffnet Updates selbst; das Werkzeug legt Ordner und Code einmal an (`[privat]`, Zugangskarte — Link und
  Code nur am Terminal, nie in umgeleiteter Ausgabe) und schreibt daneben `paket.stand.json`
  (Version, Prüfsumme, Größe): Pakete aus einem Datei-Link fragen beim Prüfen nur sie
  (`paketquelle.stand_url`), eine ZIP ohne Standdatei lädt nur „Jetzt prüfen“; große Pakete
  aus dem Netz gehen über eine Datei in `Import/`, nie durch den Arbeitsspeicher, und wie der
  Klartext eines privaten Pakets liegen sie dort nur, bis die Rückfrage zu ist
  (`Paketinhalt.raeumen`). Paketmanager: Jede
  Paketübung trägt ihren Paketstand (`package_standard_json`) für „Auf Paketstand setzen“;
  Entfernen legt die Übungen in den Papierkorb, „Wieder installieren“ holt sie zurück;
  **Deaktivieren** (Migration 017) versteckt alles, ohne zu löschen; was beim Update aus
  dem Paket fällt, wird nie gelöscht, sondern erfragt (übernehmen = eigene Übung mit
  gleicher ID, oder löschen). Inhalte entstehen im privaten `trainingsapp-inhalte` als
  TOML; `TRAININGSAPP_PAKETE=<ordner>` spielt sie beim Start ein, `trainingsapp-paket`
  (`paket_werkzeug.py`) prüft, baut JSON und schreibt den Quellen-Index. Vertrag:
  `docs/uebungspakete.md`.

- **Kurse** (Ben, 15.10.2026): dritte Kategorie neben Übungen und Plänen —
  Kapitel linear, je Kapitel eine Bedingung (`gelesen`, `summe`, `tage`, `messung`),
  Plan-Vorlagen werden beim Erreichen zu echten Plänen (`plan.course_chapter_id`,
  beim Abschluss deaktiviert, nie gelöscht), Überspringen nur auf Rückfrage.
  Bedingungen rechnen aus Einträgen und Messdauer, **nie aus Messwerten**
  (rechtlich wie `physiologische_steuerung`). Kurse reisen in Paketen
  (`kurse[]`, Formatversion 2). Vertrag: `docs/plan_kurse.md`.

- **Tagesfelder** (Ben, 21.10.2026): Parameter und Tags an der Tagesnotiz. Das sind frei
  benannte Felder je Profil:
  - Art: Skala, Anzahl, Menge, Dauer, Ja/Nein oder nur Text;
  - wahlweise Varianten;
  - einmal am Tag oder mehrmals mit Uhrzeit.

  Unter Heute stehen sie im Block „Zum Tag“. Sie haben eigene Tabellen `day_field`/
  `day_value` (Migration 027) und sind **keine Übungen**: Pläne, Kurse, Pakete und die
  Tagesabfragen über `session_entry` sehen sie nie. Kurven entstehen über
  `core.tagesfelder.als_eintraege` → `core.verlauf`. Es gibt nur Zahlen, keine Bewertung,
  Grenze oder Erinnerung (`docs/recht/00_zweckbestimmung.md`). Vertrag:
  `docs/plan_tagesfelder.md`. **Nicht dasselbe wie die Notiz-Tags** (Ben, 2.11.2026, P104):
  Ein Tagesfeld „nur Text“ ist ein Feld mit Einträgen, das mitsamt ihnen als Stapel gelöscht
  werden darf; ein Notiz-Tag ist ein langlebiges Etikett am Tagebuchtext, abgesichert gegen
  Löschen — es nimmt nie Text mit. Beides bleibt nebeneinander.

- **Updates** (Ben, 16.10.2026): `core/update.py` fragt die GitHub-Releases der App ab
  (Version und Build-Nummer gegen `config.app_version()` — in der gebauten App aus
  `_build.py`, die `scripts/apk_bauen.py` schreibt, aus dem Quelltext aus `pyproject.toml`;
  APK-Link im Browser, nur Android). `core/paketquelle.py`
  fragt **Paketquellen** (Index-JSON per HTTPS, Format von `trainingsapp-paket index`,
  SHA-256 geprüft, Signaturfeld reserviert). Paketversionen „X.Y.Z“ reisen als Zahl
  X·10000 + Y·100 + Z (`core/paketversion.py`, ältere Apps vergleichen weiter); die **Stufe**
  eines Updates kommt aus dem Unterschied, nicht aus der Nummer (U6, `core/paketstufe.py`: groß
  = etwas fällt weg, mittel = Neues/Texte/Medien, klein = Vorgaben); Modus je Paket **Alle**
  (klein + mittel von selbst, groß fragt) · **Kleine** · Manuell, „Für alle Pakete“ unter
  Updates; `trainingsapp-paket pruefen --gegen` lehnt eine zu kleine Nummer ab. `ui/views/updates.py` macht beides beim Start
  (abschaltbar, einmaliger Hinweis — jede neue Netzverbindung in Solo braucht Schalter,
  Hinweis und einen Nachtrag in `docs/recht/40_toms.md`, `80_store_freigaben.md`,
  `build/solo.toml`), spielt Pakete im Modus „auto“ ein und hängt das Label unter das
  Zahnrad (`AppState.updates_label`, einmal je Stand). Schalter `update_pruefung` und
  `paket_quellen` nur Solo. **Stufe 2** (Ben, 9.11.2026, Katalog A8): „Laden und installieren“
  in der Karte „App“ — `core.update.apk_laden` (nur von den Releases des Repos, Größe und
  SHA-256 aus GitHubs `digest`), Ablauf `ui/app_update.py`, Installieren über die Erweiterung
  `erweiterungen/flet_installieren` (`PackageInstaller`, ab Android 12 ohne Rückfrage; nie,
  solange etwas läuft — Android beendet die App dabei). **Automatik** (Schalter
  `AppState.app_update_auto`, Vorgabe an, einmaliger Hinweis): nach der Prüfung im WLAN laden,
  Sitzung vorbereiten (nicht abschicken), beim Verlassen der App einen Wecker der Erweiterung
  stellen, der sie nach `app_update.WARTEN_S` abschickt — nie mit offenem Formular, laufendem
  Vordergrunddienst oder sichtbarer App; danach Benachrichtigung über `MY_PACKAGE_REPLACED`.
  Nicht für eine Fassung in Google Play.

- **Diagnosemodus** (Ben, 4.11.2026, `docs/plan_diagnosemodus.md`, Vertrag §14): in den
  Einstellungen angeboten, je Messung gestartet (Sensorblatt mit Vorabtest), roter Punkt oben
  rechts im Overlay. Rohmitschnitt `mitschnitt-v1` aus hrv-core (`hrv_core.mitschnitt`) über
  `devices/mitschnitt.MitschnittTransport`, Beschleunigung in `PolarQuelle` (`acc=`,
  `stroeme_setzen`), Lebenszyklus im `Messlauf` (neben dem Backup, beim Speichern Beiwerk);
  **Marken** (Wdh/Atem/Störung, `core/diagnose.kontext_aus_notizen`) aus der Leiste im Overlay
  (`components/marken_leiste`, Tipp beim Aufsetzen) oder mit ⏯ an der Uhr (Seite „Diagnose“,
  Dart-Stempel) — **nie in den Notizen**, immer im Mitschnitt; nach dem Satz Marken · Sensor
  (Zähl-Teil, sonst `hrv_core.prototyp`; nur angezeigt) · Korrektur · eingetragen. Unbekannte Geräte: Geräteprobe ohne
  Messung (`devices/erkundung.py`, `/geraeteprobe`), nie schreiben, nie 0x2A25/0x2A23 lesen.
  Hinaus nur bereinigt (`hrv_core.deid.mitschnitt_zeilen`). In hochfrequenten Ereignissen
  immer `ohne_auto_update()` (V1).

- **Beschleunigungssensor in Übungen** (Ben, 4.11.2026, Vertrag `docs/plan_beschleunigung.md`):
  je Übung die Karte „Beschleunigungssensor“ (Wiederholungen, Atmung; `core/zaehlen.SensorWahl`,
  `exercise.acc_json`, Migration 037, Paketfeld `beschleunigung`). Hat das Gerät einen
  (`CAP_PMD_ACC`), ist **der Knopf die Messung** („Wdh. zählen“), **±1 nur ihre Korrektur** —
  ohne Sensor kein Knopf, kein Handzähler. Das Zählen ist der Einheit-Teil `zaehlen`
  (`devices/zaehlen.ZaehlBaustein`), **unabhängig von der Uhr** (mit der Uhr derselben Übung in
  einer Einheit), Strom erst ab dem Tipp, aus mit dem Ende (`Messlauf.acc_anfordern`/
  `acc_freigeben`). Ende: „Fertig“, Abhaken, Timer durch = eingetragen (`person/eintrag` mit
  `teil`, nie doppelt); Abbrechen, andere Übung, 60 s ohne Bewegung, Trennen = abgebrochen,
  nachtragbar unter „Läufe heute“; ein Wechsel der Ansicht beendet nichts. **Entweder zählt die
  Person oder der Sensor** (P122; beides nur im Diagnosemodus, A2). Im Alltag nur Ergebnisse
  (Zeitleiste `zaehlung`/`korrektur`/`zaehlen_ende`, `reps` im Eintrag), **nie Rohdaten der
  Beschleunigung** (P123). **Atmung** (A3, Ben 5.11.2026): dieselbe Einheit, die **Atem-Spur**
  neben den Sätzen (`hrv_core.prototyp.atemzuege.AtemLive`, Phasen ▲/▼ und Fenster ins Beiwerk
  `_atem.json` der laufenden Messung, Zeitleiste `zaehlung` mit `zaehlart` atem / `satz` 0) —
  sie läuft nebenbei (P133: Chips, Sätze, Anhalten berühren sie nicht), nur Atmung ±1 und
  `kein_atem`, **nie ins Tagebuch** (P120). **B1** (5.11.2026): die Auswertung zeigt das
  Beiwerk als Ebene „Atmung“ (Einatmen schattiert) und Karte „Atmung (Prototyp)“ mit dem
  Hinweis „Atmung < 9/min — liegt im LF-Band“ an HF-Power, LF/HF und DFA α1 (Startregel F6 in
  `core/atem_auswertung.py`, nichts gespeichert, keine Wertung), live liegt das Einatmen der
  letzten 60 s hinter den Kurven (`components/atem_live.py`), und die Messdatei bekommt das
  Protokollfeld `atmung` (`core/atem_protokoll.py`: Atemübung → `uebung`, keine Übung →
  `spontan`, sonst kein Feld; Vertrag §5). **B2** (5.11.2026, hrv-core 0.10.0): die Atem-HRV je
  Atemzug aus `hrv_core.prototyp.atem_hrv` — Atemspanne, **Phasenlage als Sekunden ab
  Einatembeginn** (P135), RR je Phase — rechnet `core/atem_auswertung.py` beim Anzeigen je
  Messung und Abschnitt (korrigierte Reihe, Wanduhr) und der `ZaehlBaustein` live („Spanne 58
  ms“, nur mit Aufnahme); Regel F6 nach P136 (Sensor ab 3 gültigen Fenstern und 25 %, sonst
  RR-Atmung im Modus aus dem Protokollfeld, `rr_modus`), nichts gespeichert. **A5** (5.11.2026,
  hrv-core 0.11.0): je Satz zählt der Live-Zähler `prototyp.wiederholungen.WdhLive` jede
  Wiederholung sofort, **Umkehrpunkt oben** (P143, `core.zaehlen.vorlage_waehlen` überschreibt
  den Katalogwert), halbe daneben, nie mitgezählt; Vorlagen in der Karte nur Automatisch ·
  Kniebeuge · Liegestütz (`VORLAGEN_ANGEBOT`), die Achsen eines anderen Geräts → Automatisch mit
  Grund; `zaehlen_fenster` nur noch als Rückfall im Diagnose-Vergleich ohne Zähl-Teil. **B2b**
  (5.11.2026, hrv-core 0.12.0, `ALGO_VERSION` bleibt 8): dieselbe Rate nach F6 geht an
  `frequenzbereich(atemrate_pro_min=)` — Kacheln „HF (Atemband)“/„LF/HF (Atemband)“, Tabelle und
  Bandleiste zeigen `hf_atem`/`lf_hf_atem` **neben** den festen Bändern (Fensterspektren über
  `core.atem_auswertung.mit_atemband`), kein Cache; die **Atemlage** (`hrv_core.atmung.atemlage`)
  steht unter DFA α1, und Schwellen aus α1 (`core/hf_auswertung`, `AUSWERTUNG_VERSION` 4) gelten
  nur bei spontaner Atmung ab 9/min oder unbekannter Lage — sonst Grund statt Schwelle.

- **Gezeichneter Ablauf** (Ben, 8.11.2026, Vertrag `docs/plan_verzweigungen.md` §8, Stand
  §8.8; Migration 044, Datenschritt 6): Der Plan-Editor hat die Reiter **Plan · Uhren**, der
  Schalter **„Der Reihe nach | Mit Abzweigen“** (`views/ablauf.modus_zeile`) bringt **„Ablauf“**.
  *Der Reihe nach* = Planfolge, je Übung nur die Bedingung (`PlanItem.bedingung`); **Zweige
  A–D, dann/sonst/Wege sind veraltet** (P108) — Altbestand wird zum Ablauf. *Mit Abzweigen* =
  `core/ablauf.py`: `Ablauf(an, start, kanten, fragen)`, `plan.ablauf_json`; **Knoten** sind
  Planübungen (Nummer = Stelle in der Liste, `nummern`; `beiname`) und **Fragen**, **Kanten**
  tragen den Auslöser (frei · Zeit ab · Wdh. · Wdh. in einer Zeit · Skala ≥ n bis m), Pflicht,
  „von selbst“ (hart sofort, weich erst bei Zeit ab), Ziel auch `ENDE`/`ZURUECK`. Bedingung und
  Hauptweg werden **gespiegelt** (`views/ablauf.ablauf_speichern`, `hauptwege_spiegeln`); „Im
  Plan einstellen“ zeigt dasselbe Wege-Formular (`components/wege_form.py`) mit „Kommt von“.
  Im Workout **bleibt** man bei der Übung, solange die Bedingung fehlt bzw. kein Weg frei ist
  (`PlanAblaufBaustein.wartet`, keine Pause), hart geht es von selbst weiter, sobald es reicht;
  jeder Schritt hat eine Uhr (ohne Timer `core.timer.stoppuhr`, „Zeit ab“ = „Fertig“) und damit
  den Fokus; Wiederholungen von Hand (`person/wdh`), wo niemand zählt. Rechnung nur in
  `core/ablauf.py` und `devices/plan_ablauf.py`; `ui/` zeichnet (`components/ablaufbild.py`:
  Fläche einmal bauen, Inhalt tauschen, Lagen bleiben bis „Neu anordnen“, Eltern mittig;
  `views/ablauf.py`: Seite scrollt nicht, Palette = Planübungen mit `Draggable.affinity`
  senkrecht, Knöpfe unter dem Bild). Zeitleiste `plan/kante|frage|antwort`, `person/wdh`;
  Paket `plaene[].ablauf` mit Positionen. **Korrekturen 9.11.2026** (§8.9): „Aus dem Ablauf
  nehmen“ lässt die Planübung im Plan (aus dem Plan: Kachel gedrückt halten), jede Kante hat
  einen Punkt zum Antippen (Blatt auf diesem Weg), Warnungen `core.ablauf.warnungen` sichtbar
  beim Zeichnen; **mehrere gleichwertige Wege — erst fragen**, hart wie weich
  (`core.ablauf.wahl_offen`, `PlanAblaufBaustein.wahl_noetig`, Karte „Wie geht es weiter?“);
  der Workout-Fokus liegt über dem Plan (`/plan/<id>/workout`, Zurück = Plan, Hinweis „Workout
  läuft“). **Durcharbeiten statt abarbeiten** (Ben, 9.11.2026, §8.10, P166–P169): mit Ablauf zählt
  „heute gemacht“ nie, ein vorzeitig beendetes Workout setzt heute fort (`plan/ende` mit `bei`,
  `core.ablauf.fortsetzung`); in der Liste ist nur frei, was keine nie erfüllte Pflicht versperrt
  (`core.ablauf.gesperrt`, Tore aus `plan/kante`, Migration 051 zum Zurücksetzen) — wie ein
  Kurs; „Trainieren“ öffnet so einen Plan als Workout (`plan_durchlauf.startet_als_workout`),
  oben wechselt **Workout · Liste** (`components/modus_wahl.py`).

- **Uhr und Fokus beim Üben** (Ben, 8.11.2026 spät, Vertrag `docs/plan_uhr_fokus.md`, Stand §9):
  Die Uhr-Zeile ist `Uhr ▾ · Zeit · Takt · ▶` (`components/uhr.py`); **▶ öffnet den Fokus**
  (`AppState.fokus_auto`, Vorgabe an, Schalter rechts in der Zeile von „Gemacht“), „Uhr aus“
  heißt **„Ohne Uhr“** (`core.timer.ohne_uhr`: Stoppuhr, die nicht zählt). Das ⏱ öffnet das
  **Uhr-Blatt** mit Geltung Für jetzt · In „Plan“ · Übung (`components/uhr_blatt.py`). Der Fokus
  hat die Karte **„Eintragen“** (`components/fokus_eintragen.py`, auch im Workout): Eingaben als
  `person/wdh|skala|auspraegung`, eingetragen erst mit dem Ende des Laufs; Wiederholungen mit
  den Knöpfen des Blocks — **jeder Tipp ein Satz dazu**, „−“ nimmt den letzten zurück
  (`person/wdh` mit `dazu`). Im laufenden Fokus nur, was gerade passiert: keine „Läufe heute“,
  Erklärungen im „i“, Takt · Zeit · Ebenen-Knopf in einer Zeile, die **beim Scrollen oben stehen
  bleibt** (`fokus.OBEN`); Fokus-Ansichten (``data = FOKUS_ANSICHT``) bekommen **keine
  Laufleiste**. **Messung läuft weiter** ist Vorgabe (`Einheitslauf.stoppt_am_ende`): nach Timer,
  Übung, Workout und GPS-Training läuft eine mitgestartete Messung weiter — außer sie ist allein
  oder die Einheit begann als reine Messung (`beitreten`); die Strecke findet sie dann über die
  Einheit (`hrv_bezug`). Ein Timer-Abschnitt
  kann eine **Ausführung** tragen (`Abschnitt.ausfuehrung`, flach in `timer/abschnitt`) —
  eingetragen wird **je Ausführung ein Eintrag** (`core.timer_eintrag.nach_ausfuehrung`,
  `Eingaben`; beim Üben und im Workout). Pfeilzeile `components/planpfeile.py` im Plan und im
  Fokus; alle Timer unter Einstellungen → Timer → „Alle“ (`views/alle_timer.py`,
  `core.uebung_timer.alle_timer`). **Timer-Editor** (Ben, 9.11.2026, `docs/plan_timer_editor.md`,
  Skizzen G1–G5): fest oben Name und Gesamtzeit, Reiter **Zeiten · Klänge** (Wischen: eine
  Scrollfläche, die Namen bleiben stehen, nur die rechte Spalte gleitet — feste Zeilenhöhen),
  je Abschnitt eine Zeile, Teile ⧉ kopieren, Abschnitte per langem Druck; die Felder halten
  Werte, nicht Controls (jeder Aufbau legt sie neu an). **Für jetzt mit Abschnitten**: das
  Zeit-Blatt hat „Mit Abschnitten …“ (`zeit_blatt(erweitert=)`), `…/bearbeiten/einmal` mit
  `views.uebung_timer.jetzt_profilziel` — `AppState.uhr_einmal` hält Profile, gespeichert wird nur
  per „Als Timer der Übung speichern …“.

- **Taktgeber** (Ben, 5.11.2026, Vertrag `docs/plan_taktgeber.md`; Teil 1 T1–T3 gebaut): ein
  **Takt** ist eine Folge von Phasen (Name, Sekunden, Art `ein`/`aus`/`halten`/`ab`/`auf`/`frei`,
  Klang) mit Tempo, als Schleife, solange die Uhr läuft. Die Rechnung lebt **nur** in `core/takt.py`
  (`Takt`, `lage` aus der Uhr — nie mitgezählt —, `wechsel`, `TaktLauf` für Tempo ohne Sprung,
  `VORLAGEN`, `animation_fuer`, `soll_phasen`); `ui/` zeichnet nur. Drei Orte, Vorrang Uhr „für
  jetzt“ (`AppState.uhr_takt`, `takt.AUS` = keiner) > Timer-Abschnitt (`Abschnitt.takt`) > Übung
  (`Exercise.takt`, Migration 038 `takt_json`, Paketfeld `takt`, Drei-Wege-Abgleich ein Feld) —
  `core.uebung_timer.takt_fuer`, am Lauf `TimerLauf.takt_aktuell`/`takt_lage`. Der Ticker
  (`ui/timer_takt.py`) spielt je neuer Phase ihren Klang (Vorgabe je Art, `KLANG_VORGABE`) und
  vibriert kurz (Einstellungen → Übungen, Vorgabe an, P140 offen); `TimerBaustein` schreibt
  `timer/takt` am Abschnittsbeginn und je Tempoänderung (`plan_einheit` §4). Takt-Blatt
  (`components/takt_blatt.py`, `blatt_spalte`) mit Vorschau und Tempo-Regler; der Regler **im
  Lauf** (`TempoRegler`) ist `TimerLauf.tempo_setzen` — für jetzt (P139). Die Animation
  (`components/takt_anzeige.TaktAnzeige`, nach Phasenzahl: Puls, Kreis, Kreis mit Halten, Box,
  Balken, Welle) wird **einmal gebaut**, `nachziehen` setzt je Tick nur Werte, `animate_scale` mit
  der Phasendauer (V1). **Teil 2** (5.11.2026, 0.3.51, `docs/plan_taktgeber.md` §10): der
  `TaktVerfolger` (`devices/takt_lauf.py`) sagt je Tick der Einheit, was im Takt geschah
  (Takt-Lauf begann/endete, Soll-Phasen, volle Runden) — die Einheit bringt es **nicht über die
  Zeitleiste**, sondern direkt zur HRV (`Messlauf.atem_takt_beginn/phase/ende`: Feld `takt` im
  Beiwerk `atem-v1`, ein Paar Notizen `timer/takt` … `timer/ende` auf der Spur `atemtakt` ohne
  Abschnittsgrenze und ohne 5-s-Regel, Protokollfeld `atmung` `getaktet` mit der Rate des
  längsten Laufs — nur Atemtakte) und zum Zähl-Teil (`ZaehlBaustein.takt_runden`). Die
  Auswertung legt Soll über Ist (feine Linien, Versatz-Median je Atemzug, Phasenlage gegen Ist
  und Soll, `core/atem_auswertung.soll_ist_versatz`/`soll_atem`), die Takt-Rate ist für F6 die
  **dritte** Quelle (ein Soll ist keine Messung). **Takt zählt** (P138): `Takt.zaehlt`
  (Schalter im Blatt, Bewegungs-Vorlagen an) → `uebung_lauf.takt_zaehlen_anbringen` lässt mit
  der Uhr der Übung einen Zähl-Teil mit `quelle="takt"` antreten, auch **ohne Gerät**
  (`messlauf=None`, `_OhneGeraet`); jede volle Runde eine Wiederholung, Zählzeile „Takt 12“ (nie
  „Prototyp“), mit Sensor zählt der Sensor und der Takt steht daneben (`zaehlung` mit `quelle`,
  `takt`, `takt_zeiten_s`; nur der Sensor im Eintrag). Das **Bild der Bewegung** ist ein Medium
  der Übung (`core/bewegungsbild.py`, Ablage `Medien/Bewegung/`, `BewegungsbildRepo`, Weg
  `bewegung/<id>`), läuft als `ft.Image`-Schleife neben der Takt-Anzeige im „Während“ — nie in
  Paket, Export oder Sync. **Planübung folgt der Übung auch hier** (A6, 5.11.2026):
  `PlanItem.acc`/`PlanItem.takt` (Migration 039, NULL = wie die Übung, `takt_json = '{}'` =
  keiner), aufgelöst nur in `core.zaehlen.wirksame_wahl` und `core.uebung_timer.takt_der_uebung`
  (Uhr für jetzt > Abschnitt > Planübung > Übung) — „Im Plan einstellen“ hat Karte und Takt-Zeile
  mit ↺, den Knopf „Wdh. zählen“ nur mit Wiederholungsfeld; Paketfeld je Planübung.

- **Geräte-Port pull-basiert.** `devices/base.py`: alle Quellen (bleak/Desktop,
  spätere Flet-Extension/Mobil, Simulator) *pushen*; der Konsument *pullt* per `async for`
  über eine begrenzte `asyncio.Queue`. Messwerte und Status laufen getrennt — Batterie
  darf den RR-Strom nicht verstopfen; bei Überlauf verfällt Status, nie ein Messwert.
  `parse_hr_measurement` liest **alle** RR-Werte eines Pakets (mehrere pro Notification
  bei >60 bpm) — nur den ersten zu lesen verlöre die Hälfte.

- **Datenqualitätsstufen** (`intervall_quelle`): `rr_ekg` (Brustgurt, volle HRV),
  `ppi_optisch` (optisch, Frequenzwerte mit Vorbehalt), `bpm_only` (keine HRV). Enthält
  eine Messung keinen RR-Wert, ist sie `bpm_only` — egal was das Geräteprofil versprach
  (`Recording.effektive_qualitaet()`).

- **Zurück speichert** (Ben, 16.10.2026): Formulare mit „Speichern“ hängen an
  `ui/components/zurueck.zurueck_speichert` (`can_pop`/`on_confirm_pop`) — Zurück speichert
  Geändertes, Unvollständiges fragt, „Abbrechen“ verwirft; Blätter und Notizdialoge speichern
  beim Schließen. Neue Formulare ebenso. **Schreibnotizen nie als Popup** (Ben, 2.11.2026,
  P103): `components/notizeditor.py` ist der Editor an Ort und Stelle — Autosave nach 1 s,
  vor jedem Neuaufbau und vor dem Hintergrund (`AppState.vor_dem_verlassen`), ↶ ↷ aus
  `core/textverlauf.py`, „Abbrechen“ = Text vom Antippen, „Fertig“ = Karte — das Speichern
  frischt die Ansicht nie auf (Fokus). Darauf die **Notizen zum Tag**
  (`components/tagesnotiz.py`, `docs/plan_tagesnotizen.md`): mehrere je Tag mit „+“, Tags
  als Chips (Migration 036, „Tagebuch“ fest, Einstellungen → Notiz-Tags), Anhänge an der
  Notiz, Karten gekürzt auf `core.tagebuch.NOTIZ_ZEILEN`; im Tagebuch der Abschnitt
  „Notizen“ mit Tag-Filter und Suche, bearbeitet wird in der Liste (`Textnotiz` für die
  Plan-Notiz).
  Tippen daneben = „Fertig“, Scrollen daneben nicht (Ben, 2.11.2026: `AppState.schreib_gesten`
  — `components/scroll.py` meldet Ziehen, der Gestenfänger in `views/tag.py` den kurzen Tipp;
  der runde Knopf verschwindet beim Schreiben); die Tastatur schließt `Notizfeld.blur` — nie
  den Fokus an einen Knopf geben, der danach verschwindet (Flutter gibt ihn dem Feld zurück). Flutter-Menüs
  reichen den Tipp, der sie schließt, an das Darunter weiter — darum filtern Katalog und „Übung
  hinzufügen“ mit einem modalen Blatt: Knopf in der Suchzeile, Labels darunter, Typ · Region ·
  Paket und „Alles leeren“ (`components/uebungsfilter.py`, `core/uebungsfilter.py`, Ben
  9.11.2026). **Dialoge exakt schließen:** `page.pop_dialog()`
  trifft den obersten Eintrag — auch eine SnackBar —, darum `components/dialoge.schliessen`
  und keine SnackBar, solange ein Dialog offen ist (`Nachher`, `reste_dialog`).
  **Meldungen gehen nach 5 s** (Ben, 22.10.2026), auch mit „Rückgängig“ — zentral in
  `ui/flet_absicherung.snackbars_absichern` (`persist=False` beim Zeigen; Flutter ließe sie
  sonst stehen). **Blätter von unten** nehmen `components/blatt.blatt_spalte`: Inhalt
  scrollt, gemessene Höhe, Knöpfe fest über der Navigationsleiste — keine Höhenschätzung.

- **Laufende Messung überlebt das Wegwischen** (Ben, 16.10.2026): `scripts/apk_bauen.py`
  setzt in Flets Vorlage eine eigene MainActivity, die die Flutter-Engine im
  `FlutterEngineCache` hält — Bluetooth bleibt verbunden, den Prozess hält der
  Vordergrunddienst (`flet_ble`, `MessDienst`). APKs darum nur über das Skript bauen. Was
  läuft, steht jede Sekunde in dessen Benachrichtigung (`core/laufend.py`, `ui/laufend.py`).
  Die Engine kommt über `getCachedEngineId` mit `shouldDestroyEngineWithHost = false` —
  `provideFlutterEngine` allein ließ das Fragment sie mit der Activity zerstören und tot im
  Cache liegen (Absturz beim Wiederöffnen bis v0.3.4, Befund H19).

## Datenbank-Konventionen

SQLite über `sqlite3`, kein ORM. Migrationen sind nummerierte `.sql`-Dateien in
`data/migrations/`; Version über `PRAGMA user_version` (keine Verwaltungstabelle). Jede
Migration läuft in eigener Transaktion. Verbindungen über `data.db.oeffnen()` — setzt
`foreign_keys=ON`, `journal_mode=WAL`. **SQL immer mit Platzhaltern (`?`)**, nie
String-Interpolation.

## HRV-Änderungen

Die HRV-Mathematik lebt in hrv-core — Änderungen dort, mit **Golden-Test**
(`hrv-core/tests/golden/`, Toleranz 1e-9 gegen den Stand beim Umzug) und Eintrag in
`hrv-core/docs/hrv_algorithmen.md` bzw. `korrektur.md` (Grundsatz der Korrektur:
**lieber eine Lücke als ein falscher Wert**). `docs/hrv_algorithmen.md` und
`docs/korrektur.md` hier sind nur noch Verweise. `tests/golden/rr/` bleibt für die
App-Tests (Notizen, Export, UI), die eine echte Messdatei brauchen.

## Lernprojekt

Die App entsteht entlang eines Lernpfads (`docs/tutorial/`); `ui/` ist bewusst noch eine
Hülle mit Platzhalteransichten. Die Tutorial-Beispielskripte laufen in CI mit — wenn ein
Beispiel bricht, ist der Lernpfad kaputt. Flet-freie Beispiele stehen als Liste im Schritt
„Beispiele des Lernpfads“; jedes Skript, das `flet` importiert (dazu `src/main.py`), findet
`scripts/pruefe_flet_beispiele.py` am Ende des Jobs `test` selbst — mit den
Laufzeitabhängigkeiten wie in der gebauten App, Control-Baum mit `page`-Attrappe,
`DeprecationWarning` = Fehler. Ereignis-Handler und Code in `.md`-Dateien prüft es nicht.