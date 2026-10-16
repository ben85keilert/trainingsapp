# Mitwirken

Danke für dein Interesse! Bitte lies vor einem Pull Request die folgenden Punkte.

## Lizenzvereinbarung für Beiträge (CLA)

Dieses Projekt steht unter der [AGPL-3.0](LICENSE), soll aber für den Projektinhaber **dual-lizenzierbar** bleiben (z. B. für eine spätere kommerzielle Lizenz). Deshalb gilt:

**Mit dem Einreichen eines Beitrags (Pull Request, Patch) erklärst du dich einverstanden, dass:**

1. dein Beitrag unter der AGPL-3.0 veröffentlicht wird, **und**
2. du dem Projektinhaber (Benjamin Ebert) ein unwiderrufliches, weltweites, unentgeltliches Recht einräumst, deinen Beitrag auch **unter anderen Lizenzbedingungen** zu verwenden und weiterzulizenzieren (Dual Licensing),
3. du bestätigst, dass du der Urheber des Beitrags bist bzw. das Recht hast, ihn unter diesen Bedingungen einzureichen.

Wer damit nicht einverstanden ist, kann das Projekt selbstverständlich trotzdem unter den Bedingungen der AGPL-3.0 forken.

## Technische Konventionen

### Die Importregel

`core/`, `data/` und `devices/` importieren **niemals** `flet` — und nichts
unter `trainingsapp/` importiert jemals `scipy`. `tests/test_import_regel.py`
erzwingt beides.

Begründung: Die Domänenlogik muss ohne Oberfläche testbar bleiben, und `scipy`
existiert auf Android/iOS nicht. Die HRV-Mathematik liegt darum als reine
numpy-Bibliothek im Schwesterrepo hrv-core (`../hrv-core`, gemeinsam mit
praxis_gui); Änderungen an Algorithmen gehören dorthin, samt Golden-Test.

### Weitere Regeln

- **Datenformat:** Alles, was Messdateien schreibt, hält sich an
  `docs/kompatibilitaet.md`. Änderungen am Format brauchen dort zuerst einen Eintrag.
- **Datenbank:** SQLite über `sqlite3`, kein ORM. Migrationen als nummerierte
  `.sql`-Dateien, Version über `PRAGMA user_version`.
- **SQL** immer mit Platzhaltern (`?`) — nie String-Interpolation.
- **UI dünn halten:** keine Rechenlogik in `ui/`. Views rufen Funktionen aus
  `core/`, `data/`, `hrv_core` auf.
- **Tests:** `pytest` muss grün sein. HRV-Änderungen brauchen einen Golden-Test
  in hrv-core.
- **Stil:** `ruff check .` und `ruff format .` ohne Beanstandung.
- **Sprache:** Code und Bezeichner englisch, wenn es die verbreitete Schreibweise
  ist; Kommentare, Docstrings und Dokumentation deutsch. Feldnamen des
  Austauschformats bleiben so, wie `praxis_gui` sie schreibt (`intervall_quelle`,
  `messungen`, …) — dort zählt Kompatibilität, nicht Konsistenz.

## Vor dem Pull Request

```bash
ruff check . && ruff format --check . && pytest
```
