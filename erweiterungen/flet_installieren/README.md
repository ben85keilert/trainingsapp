# flet-installieren

Flet-Erweiterung der Trainingsapp (Katalog A8 Stufe 2, Ben 9.11.2026): **die App installiert
ihr eigenes Update.** Gemeint ist eine geladene APK, die über den `PackageInstaller` von
Android eingespielt wird. Das geht nur in der gebauten Android-App.

- **Still ab Android 12:** Die Sitzung verlangt `USER_ACTION_NOT_REQUIRED`, das Manifest
  `UPDATE_PACKAGES_WITHOUT_USER_ACTION` (normale Berechtigung, ohne Abfrage). Aktualisiert
  sich die App selbst und ist ihr targetSdk aktuell genug, fragt Android nicht nach.
  Fehlt eine Voraussetzung, kommt doch der Dialog von Android (Status -1, die Erweiterung
  zeigt ihn selbst) — dann kostet es einen Tipp.
- **Einmal erlauben:** `REQUEST_INSTALL_PACKAGES` plus „Unbekannte Apps installieren“ für
  diese App (ab Android 8 je App). `erlauben` öffnet die Seite dafür.
- **Vorher prüfen:** `pruefen` liest die APK (Paket, Versionsnummer, SHA-256 der Signatur)
  und vergleicht die Signatur mit der installierten App. Die eigentliche Sicherung bleibt
  Androids Signaturprüfung: Eine APK mit anderem Schlüssel nimmt es nie als Update an.
- **Android beendet die App beim Installieren** und öffnet sie danach nicht von selbst.
  Wann installiert wird (nie während einer Messung), entscheidet die App
  (`trainingsapp/ui/app_update.py`).
- **Automatik** (`Selbstupdate.kt`): `vorbereiten` schreibt die APK in eine Sitzung, ohne
  sie abzuschicken; `spaeter` stellt einen Wecker (`AlarmManager`, nicht exakt), dessen
  Empfänger `SpaeterInstallieren` sie abschickt — nur, wenn die App dann weder zu sehen ist
  noch einen Vordergrunddienst hat (Messung, Training, Timer). Python braucht es dazu nicht;
  Android friert Apps im Hintergrund ohnehin nach Sekunden ein. Vor dem Abschicken steht die
  erwartete Version in den SharedPreferences, und `NachUpdate` (`MY_PACKAGE_REPLACED`) meldet
  „aktualisiert, antippen zum Öffnen“ — nach einem Update aus dem Browser nicht. Fragt
  Android doch nach, während die App nicht zu sehen ist, kommt die Rückfrage als
  Benachrichtigung (aus dem Hintergrund darf keine Activity starten).
- **Nicht für Google Play:** Dort darf sich eine App nicht selbst aktualisieren. Eine
  Play-Fassung bindet diese Erweiterung nicht ein (`docs/recht/80_store_freigaben.md`).

Python: `FletInstallieren` (Service) mit `stand`, `erlauben`, `pruefen`, `installieren`,
für die Automatik `vorbereiten`, `abschicken`, `spaeter`, `nicht_spaeter`, `verwerfen`,
`benachrichtigung_erlauben`, und dem Ereignis `on_ergebnis` (Codes von
`PackageInstaller.STATUS_*`); `verfuegbar(page)`.
Laden, Prüfsumme und Texte zu den Codes liegen flet-frei in `trainingsapp/core/update.py`.

Eingebunden wie flet_hochladen: `pyproject.toml` der App (`dependencies`,
`[tool.uv.sources]`, `[tool.flet.dev_packages]`).
