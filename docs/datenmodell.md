# Datenmodell

Schema: `src/trainingsapp/data/migrations/001_init.sql`.
Migrationen sind nummerierte `.sql`-Dateien, die Version steht in
`PRAGMA user_version`. Kein ORM — `sqlite3` reicht und zeigt, was passiert.
`data.db.migrieren` legt um jede Datei `BEGIN … PRAGMA user_version … COMMIT`
— die Dateien selbst enthalten **kein** `BEGIN`/`COMMIT` (Python-`executescript`
committet eine offene Transaktion sonst still vorher).

IDs sind **UUIDv7** als TEXT: zeitsortiert, dadurch gute Index-Lokalität und
natürliche Sortierung ohne Zusatzspalte (`core/models.py::new_id`).

## Überblick

```
subject ──┬── session ──── session_entry ──── entry_media
          │                      │
          │                      └──────────── measurement
          ├── hrv_recording ──── hrv_metrics_cache
          ├── plan ──────── plan_item
          ├── einheit ──┬── einheit_baustein   (Teile: HRV, Timer, GPS, Plan — Migration 018)
          │             └── einheit_ereignis   (Zeitleiste, unveränderlich)
          ├── strecke        (Ausdauertraining, Migration 012 — nie synchronisiert)
          └── consent

exercise ──┬── exercise_media
           ├── exercise_spec_version
           ├── exercise_tag ──── tag
           └── package       (Herkunft: aus welchem Übungspaket, Migration 014)

device        external_ref     outbox     tombstone

app_setting   (gerätelokal, Migration 002 — wird nie synchronisiert)
day_note      (Tagesnotiz je Profil und lokalem Tag, Migration 003)
```

**Parameter im Plan** (Migration 004, seit Migration 010 so): Die Übung legt in
`result_spec_json` ihre Felder und Standard-Chips fest (Feldvorrat in
`core/result_spec.py`, Satzfeld mit Notation `3x15`, `30`, `15/15/20` — siehe
`docs/notation.md`). Der Plan wählt je Übung in `plan_item.fields_json`, welche
**Parameter** er anbietet (`NULL` = wie die Übung, `[]` = keiner → nur abhaken),
je Parameter eigene Chips (`quick_json`; eine leere Liste heißt „keine Chips,
nur das freie Feld") und ein Ziel (`target_json`). Das freie Feld gibt es beim
Üben für jeden Messwert ohnehin. Die alte Stufe `plan_item.input_mode`
(`haken`, `chips`, `frei`) bleibt für ältere Stände stehen und folgt den
Parametern (`haken` bei `[]`, sonst `chips`). Der Eintrag übernimmt den Plan und
darf im Formular abweichen. Ein „+20" im Plan ist eine Korrektur des heutigen
Eintrags (`replaces_entry_id`), der Eintrag selbst bleibt unveränderlich; ebenso
ein Skalenwert nach der Übung (`SitzungRepo.wert_setzen`).

**Archiv, Papierkorb, endgültig** (Migration 005): `exercise.archived` nimmt eine
Übung aus dem Katalog, Pläne zeigen sie weiter. `deleted_at` heißt „im
Papierkorb": Die Übung verschwindet auch aus den Plänen (die Planübung bleibt
gespeichert und kehrt beim Wiederherstellen zurück). Nach 30 Tagen löscht die App
endgültig (`purged_at`, abschaltbar über `app_setting.papierkorb_auto`) — aber nur
Übungen **ohne** Einträge; bei Übungen mit Verlauf fragt sie, ob die Einträge
bleiben oder mitgehen. Die Zeile bleibt auch nach dem endgültigen Löschen als
Grabstein stehen, damit alte Einträge ihren Namen behalten und der Seed eine
mitgelieferte Übung nicht neu anlegt. Pläne funktionieren genauso.

**Standard der Übung ↔ Planübung** (Migration 006): Die Übung trägt einen Standard
für Pläne — `default_target_json`, `default_fields_json` (Parameter, seit 010;
`default_input_mode` folgt), Chips je Feld in der Spezifikation. `PlanRepo.uebung_hinzufuegen` übernimmt ihn; danach sind Plan und
Übung unabhängig. Zurück und hin geht es nur ausdrücklich per Knopf
(`core/standards.py`: `als_standard`, `vom_standard`, `abweichungen`).

**Varianten** (Migration 007): `exercise.family_id` zeigt auf das Original einer
Variantenfamilie (nie auf eine andere Variante). Im Verlauf bilden Original und
Varianten eine Kachel; ihre Mengen werden addiert und je Variante ausgewiesen
(`core/tagesbilanz.py`). Eine Kopie ist zunächst Variante, im Editor lässt sie
sich eigenständig machen. (Seit 21.10.2026 heißen Varianten auch die leichten innerhalb
einer Übung, nächster Absatz; die Texte der Kopien sind offen, P61.)

**Varianten in der Übung** (Ben, 21.10.2026, `core/varianten.py`, ohne Migration): ein
Auswahlfeld mit dem Schlüssel `variant` (Name „Variante“) in `exercise.result_spec`. Seine
Chips (`quick`) sind die Namen in Knopfreihenfolge; `optionen` hält je Name Symbol
(Material-Name aus `varianten.SYMBOLE`), Kürzel (bis 3 Zeichen) und Beschreibung — in
`to_dict` nur, wenn gesetzt. Ein Eintrag trägt `result["variant"] = "lang"`, seine
Spec-Kopie das Feld; so bleibt die Anzeige richtig, auch wenn die Übung die Variante
später nicht mehr kennt (`varianten.finden` gibt dann nur den Namen). Das Feld steht nicht
im `FELDVORRAT`: kein Planparameter, nicht in der Parameterliste des Editors. Eine
Planübung schaltet die Zeile mit `quick["variant"] == []` ab (`standards.varianten_an`,
P58). Umbenennen mit „bisherige Einträge mitnehmen“ legt je gültigem Eintrag eine
Korrektur an, alles in einer Transaktion (`SessionRepo.variante_umbenennen`). Pakete
können Varianten über `result_spec` liefern; der Paketabgleich behandelt das ganze Feld
„Parameter“ als eins (P60). Die Zeitleiste einer Einheit hält die Ausführung flach fest
(`core.einheit.AUSFUEHRUNG_SCHLUESSEL`: `variant`, `weight`, `angle`, `side`), damit ein
abgebrochener Lauf sie später einträgt; in die Messdatei kommt sie nicht.

**Übungspakete** (Migration 014): `exercise.package_id` zeigt auf das Paket, aus
dem die Übung auf dieses Gerät kam (`package`: Name, Beschreibung, Version);
`NULL` = eigene Übung, hier angelegt oder kopiert. Ein Import aktualisiert nur die
Übungen *desselben* Pakets — eigene, fremde und endgültig gelöschte bleiben. Der
mitgelieferte Katalog ist das Paket „Standard“ (früher „Grundausstattung“) und behält seine
UUIDv5-IDs. Seit Migration 015 trägt jede Paketübung ihren Paketstand
(`exercise.package_standard_json`, schreibt nur der Import — `ExerciseRepo.speichern`
lässt ihn stehen) für „Auf Paketstand setzen“; `package.removed_at` heißt entfernt
(Übungen im Papierkorb, „Wieder installieren“ holt sie zurück). Migration 017:
`package.disabled_at` = deaktiviert (nichts sichtbar, alles bleibt — Filter in
`ExerciseRepo.alle/suchen/_tags`, `PlanRepo.alle/_mit_items`, `KursRepo.alle`);
`exercise.package_dropped_at`/`course.package_dropped_at` = beim Update nicht mehr im
Paket, bis die Person übernimmt oder löscht; `package.update_mode`, `source_url`,
`available_*`, `checked_at` für Paketquellen (Online-Updates). Format und Regeln:
`docs/uebungspakete.md`.

**Zeitplan eines Plans** (Migration 008): `plan.active` und `plan.weekdays_json`
(0 = Montag … 6 = Sonntag, Standard alle). Ein Plan erscheint auf „Heute", wenn er
aktiv ist und der Wochentag passt (`Plan.steht_an`), oder wenn es an dem Tag eine
Session dieses Plans gibt — so wird ein nicht anstehender Plan „für heute
aufgenommen", ohne eigene Tabelle (`core/plaene.py`, `SessionRepo.plaene_am_tag`).
Eine aufgenommene Session ohne Eintrag lässt sich wieder entfernen.

**Kurse** (Migration 016, `docs/plan_kurse.md`): `course` (Name, Freischaltmodus,
Herkunft `package_id` + Paketstand wie bei Übungen), `course_chapter` (Reihenfolge,
Titel, Markdown-Text, `gate_json` = Bedingung, `plans_json` = Plan-Vorlagen,
`media_json`), `course_progress` (je Profil und Kapitel: erreicht, abgeschlossen,
übersprungen; `UNIQUE(subject_id, chapter_id)`). Pläne, die ein Kapitel anlegt,
tragen `plan.course_chapter_id` und werden beim Abschluss des Kapitels deaktiviert,
nie gelöscht. Bedingungen rechnen aus `session_entry` und `hrv_recording`, nie aus
Messwerten (`core/kurse.py`, `data/kurse.py`).

**Einheit** (Migration 018, `docs/plan_einheit.md`): was zusammen lief — HRV-Messung,
Timer, Ausdauertraining, Plan-Ablauf. `einheit.started_at` ist der Nullpunkt (`t_s` = 0),
`ended_at` `NULL` heißt „läuft“ bzw. beim nächsten Start abgebrochen.
`einheit_baustein` nennt je Teil seine Datei (HRV relativ zu `Messungen/`, Strecke
relativ zu `Strecken/`) und `versatz_s` (Zeit des Teils + Versatz = `t_s`) — über den
**Dateipfad**, weil eine HRV-Aufnahme über mehrere Einheiten laufen kann.
`einheit_ereignis` ist die Zeitleiste (`nr` fortlaufend, `daten_json` nur ortsfrei,
`core.einheit.DATEN_SCHLUESSEL`). Migration 019: `strecke.einheit_id` verbindet ein
Training mit seiner Einheit — so findet die Auswertung auch eine HRV-Aufnahme, die
vorher begann und weiterlief. Die Datei einer GPS-Beteiligung wird nie mitgeschickt.

**Timer an Übung, Planübung und Plan** (Migration 020, `docs/plan_einheit.md` §7):
`exercise.timer_json` = die Profile der Übung (Paketfeld `timer`), `plan.timer_json` =
„Timer für alle Übungen“, `plan.auto_next` = nach dem Timer einer Übung automatisch
weiter, `plan_item.timer_json` = die Wahl der Planübung (Profil der Übung oder eigene
Kopie, Zeitfeld, „Zeit eintragen“). Vorrang: Planübung > Plan > erstes Profil der
Übung. Ein Eintrag vom Timer trägt Anfang und Ende (`session_entry.started_at`,
`ended_at`) — sonst steht dort nur der Zeitpunkt des Tippens. Migration 021:
`plan.pause_no_timer` = im Ablauf auch nach einer Übung ohne Timer auf „Weiter“ warten
(Vorgabe 1; 0 = nach „Gemacht“ gleich die nächste).

**Der Tag ist die Bezugsgröße.** Zeitstempel sind UTC, aber „heute" ist ein
lokaler Kalendertag. `core.models.tagesgrenzen()` rechnet die lokale
Mitternacht nach UTC um; alle Tagesabfragen (Tagesansicht, Kalender,
„x von n heute") vergleichen `session_entry.started_at` mit diesen Grenzen.
`day_note.date` speichert den lokalen Tag als `YYYY-MM-DD`. Eine Session ist
„ein Plan an einem Tag" und entsteht beim ersten Eintrag automatisch.

## Die wichtigen Entscheidungen

**Es gibt keine Tabelle für einzelne Herzschläge.** `hrv_recording` verweist mit
`file_path` auf eine `raw-v1`-Datei; `sha1` erkennt nachträgliche Änderungen.
Begründung in `docs/architektur.md`. `title` und `note` (Migration 011) sind
Kopien von `titel` und `notiz` der Datei — für die Liste, die sonst jede
Messdatei lesen müsste; beim Öffnen gleicht die App sie an die Datei an.

**`hrv_metrics_cache` ist reiner Cache.** Er trägt eine `algo_version` und ist
jederzeit aus den Dateien neu berechenbar.

**`session_entry.spec_snapshot_json`** speichert die Eingabespezifikation, mit
der ein Eintrag erfasst wurde. Ohne sie wäre ein alter Eintrag nach einer
Änderung der Übungsdefinition nicht mehr interpretierbar.

**`session_entry` und `hrv_recording` sind unveränderlich.** Eine Korrektur
entsteht als neuer Eintrag mit `replaces_entry_id`. Damit sind
Synchronisationskonflikte strukturell ausgeschlossen.

**`subject` gibt es von Anfang an**, auch in Edition A — eine Familie teilt sich
ein Gerät. Nachträglich einzuführen wäre eine Migration über alles.

**`measurement` ist normalisiert** (`metric_key`, `value`, `unit`,
`recorded_at`) und speist sämtliche Verlaufsdiagramme: Übungsergebnisse über
`ResultSpec.chart_metrics`, Benchmarks wie „Luft anhalten" und HRV-Kennzahlen.
Entspricht in praxis_gui `Dokumentation_Skalen_Werte`.

## Synchronisation (Edition B)

| Tabelle | Zweck |
|---|---|
| `external_ref` | ordnet unsere UUIDs den INTEGER-Schlüsseln von praxis_gui zu — ohne sie kein Round-Trip |
| `outbox` | reihenfolgetreue Ausgangswarteschlange statt eines `dirty`-Flags |
| `tombstone` | Grabsteine gelöschter Datensätze |
| `consent` | Einwilligungen je Datenart |

**Nicht synchronisiert** wird `app_setting`: Schlüssel/Wert-Paare, die nur
dieses Gerät betreffen — das zuletzt aktive Profil, später Anzeige- und
Geräteeinstellungen. Was auf einem anderen Gerät wertlos wäre, gehört dorthin
und nirgends sonst.

| Schlüssel | Inhalt |
|---|---|
| `aktives_profil` | ID des zuletzt aktiven Profils |
| `papierkorb_auto` | „1" = Papierkorb nach 30 Tagen leeren |
| `hrv_einstellungen` | Kacheln, Fenster, Analysebereiche der Messung (JSON, `core.hrv_einstellungen`) |
| `hrv_ansicht`, `hrv_ansichten` | aktuelle und gespeicherte Kurvenansichten (JSON, `core.hrv_ansicht`) |
| `hrv_korrektur` | Vorgabe der automatischen Korrektur (JSON, `hrv_core.regeln`) |
| `timer_profile`, `timer_aktiv` | Timer-Profile (JSON, `core.timer`) und das zuletzt benutzte |

Die freie Timer-Bibliothek liegt hier, ein Werkzeug des Geräts. Profile, die an einer
Übung, einem Plan oder einer Planübung hängen (Migration 020), stehen als JSON in deren
Zeilen und reisen mit ihnen — eine eigene Tabelle braucht es dafür nicht.

Dazu auf allen synchronisierten Tabellen: `origin_device_id` (Mehrgerätebetrieb),
`revision` (serverseitig vergeben), `deleted_at` (Soft-Delete).

> **Zielkonflikt, der bewusst aufgelöst ist:** DSGVO Art. 17 verlangt echtes
> Löschen, die Synchronisation verlangt eine Spur des Gelöschten. In `tombstone`
> stehen deshalb ausschließlich ID und Zeitstempel — **niemals Gesundheitsdaten**.

## Fremdschlüssel

SQLite prüft Fremdschlüssel **nur**, wenn `PRAGMA foreign_keys = ON` gesetzt ist.
`data/db.py::verbinden` tut das, und `tests/test_core.py` prüft, dass es wirkt.
