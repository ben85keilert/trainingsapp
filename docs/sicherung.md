# Geräte-Backup: Vorgabe aus, einschaltbar

Stand 20.10.2026 (Sicherheitsdurchsicht S4; Ben: „Backups ermöglichen, standardmäßig
aber aus haben“ — und die GPS-Strecken einstellbar). Die App läuft auf Android und soll
auf iPhone laufen; die Regel gilt für beide.

## Warum

Android sichert den app-privaten Speicher von sich aus (Auto Backup) in das
Google-Konto und überträgt ihn beim Gerätewechsel — Datenbank, Messdateien, Anhänge,
GPS-Strecken. iOS tut dasselbe über iCloud. Das widerspricht dem Versprechen der
Solo-Edition, dass nichts das Gerät verlässt, was die Person nicht selbst auslöst
(`docs/recht/40_toms.md`), und „GPS-Daten werden nie geteilt“. Umgekehrt ärgert sich,
wer auf das Backup baut und es nach dem Gerätewechsel nicht hat. Darum: aus als
Vorgabe, an auf Wunsch, Strecken gesondert.

## Wie (Android)

- **Einstellungen → Geräte-Backup**: „Mit dem Gerät sichern“ (Vorgabe aus) und, wenn
  an, „GPS-Strecken einschließen“ (Vorgabe aus). Nur in der Solo-Edition
  (`config.ist_aktiv("geraete_sicherung")`).
- **Die Marke ist die Wahrheit:** `core/sicherung.py` schreibt
  `geraete_sicherung.txt` in das Datenverzeichnis (`an`, dazu `strecken`) oder löscht
  sie. Keine Datenbankeinstellung — das Backup läuft, wenn die App nicht läuft, und
  Android ruft dafür Kotlin, nicht Python.
- **BackupAgent `Sicherung`** (`scripts/apk_bauen.py`, als zweite Datei neben der
  eigenen MainActivity in die Flet-Vorlage gelegt; `pyproject.toml` trägt ihn über
  `[tool.flet.android.manifest_application]` als `backupAgent` mit `fullBackupOnly`
  ins Manifest ein): `onFullBackup` sucht die Marke bis drei Ebenen unter `dataDir`
  (Flet legt das Datenverzeichnis unter `app_flutter/…` ab). Ohne Marke schreibt er
  nichts. Mit Marke geht alles unter `dataDir` außer `cache`, `code_cache`, `lib`,
  `no_backup` — und außer `Strecken/`, wenn die Marke `strecken` nicht enthält.
  Wiederherstellung: `BackupAgent.onRestoreFile`, Datei für Datei dorthin, wo sie lag.
  Gilt für Cloud-Backup und für die Übertragung von Gerät zu Gerät.
- Grenzen: Googles Cloud-Backup nimmt höchstens 25 MB je App; darüber scheitert die
  Sicherung still. Messungen und Anhänge werden schnell größer — der Export bleibt der
  verlässliche Weg (`docs/kompatibilitaet.md`).
- Prüfen: `adb shell bmgr backupnow <paket>` und `bmgr restore`, oder Gerätewechsel.
  Gerätetest im Katalog (T-Nummer).

## iOS (noch nicht gebaut)

Dieselbe Regel über das Backup-Attribut des Datenordners: Solange der Schalter aus
ist, trägt der Ordner `NSURLIsExcludedFromBackupKey`; schaltet die Person ein, wird das
Attribut entfernt (und für `Strecken/` gesetzt, wenn die Strecken draußen bleiben
sollen). Das braucht wenige Zeilen Swift in einer Flet-Erweiterung beim ersten
iOS-Build (`erweiterungen/`), gesteuert über dieselbe Marke. Apples Richtlinie 5.1.3
(`docs/recht/80_store_freigaben.md`): keine Gesundheitsdaten aus HealthKit in iCloud —
betrifft uns nur, falls HealthKit je gelesen wird.

## Rechtliches

`docs/recht/40_toms.md` (Datensparsamkeit) und `80_store_freigaben.md`
(Datensicherheitsabschnitt): Backup nur nach Einschalten, verschlüsselt mit der
Gerätesperre, Empfänger Google bzw. Apple; Strecken gesondert.
