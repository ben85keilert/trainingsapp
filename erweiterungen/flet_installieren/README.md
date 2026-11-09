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
- **Nicht für Google Play:** Dort darf sich eine App nicht selbst aktualisieren. Eine
  Play-Fassung bindet diese Erweiterung nicht ein (`docs/recht/80_store_freigaben.md`).

Python: `FletInstallieren` (Service) mit `stand`, `erlauben`, `pruefen`, `installieren`
und dem Ereignis `on_ergebnis` (Codes von `PackageInstaller.STATUS_*`); `verfuegbar(page)`.
Laden, Prüfsumme und Texte zu den Codes liegen flet-frei in `trainingsapp/core/update.py`.

Eingebunden wie flet_hochladen: `pyproject.toml` der App (`dependencies`,
`[tool.uv.sources]`, `[tool.flet.dev_packages]`).
