---
paths:
  - "**/*update*"
  - "**/*paketquelle*"
  - "**/*paketversion*"
  - "**/*paketstufe*"
  - "erweiterungen/flet_installieren/**"
---

# Updates der App und der Pakete

Ausgelagert aus `CLAUDE.md` (11.11.2026); dort steht je Absatz die Kurzfassung mit den festen Regeln.

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
