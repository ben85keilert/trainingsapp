---
paths:
  - "**/*paket*"
  - "**/abgleich.py"
  - "**/*ergaenzungen*"
  - "**/*privat*"
  - "**/*bereinigen*"
  - "**/material.py"
  - "**/neu_laden.py"
  - "**/medienliste.py"
  - "**/code_dialog.py"
  - "src/trainingsapp/data/seed/**"
---

# Übungspakete

Ausgelagert aus `CLAUDE.md` (11.11.2026); dort steht je Absatz die Kurzfassung mit den festen Regeln.

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
  Update (`PaketRepo.ergaenzungen_anwenden`) — Eigenes bleibt. **Stellungen** (Ben, 12.11.2026,
  P188, Migration 058): zwei Stufen, „Standard“ und „Erweiterung“ nebeneinander — Beschreibung,
  Medien und Timer zusammengelegt, die Trainingsumgebung (`BUENDEL`: Parameter, Ziel, Takt)
  nur aus der gewählten Stellung (`core.ergaenzungen.wirksam`, Schalter
  `components/stellung.py` hinter dem „i“ der Übungsseite); je Stellung ein eigener Stand
  (`exercise_addon_state`), nie wieder still „die spätere gewinnt“. **Private Pakete** (U7):
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
