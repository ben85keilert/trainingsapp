---
paths:
  - "**/*hf_*"
  - "**/messung*.py"
  - "**/*messlauf*"
  - "**/live_vollbild.py"
  - "**/training.py"
  - "**/einstellungen_herzfrequenz.py"
  - "docs/plan_herzfrequenz.md"
---

# Herzfrequenz-Sicht und Speichern der Messung

Ausgelagert aus `CLAUDE.md` (11.11.2026); dort steht je Absatz die Kurzfassung mit den festen Regeln.

- **Herzfrequenz-Sicht und HF-Vollbild** (Ben, 10.11.2026, A22, Vertrag
  `docs/plan_hf_vollbild.md`): `/live` zeigt in der Sicht „Herzfrequenz“ (und bei reinen
  Pulsgebern) `views/hf_vollbild.py`, sonst das HRV-Vollbild; ein Knopf wechselt
  (`state.hrv_sicht_setzen`). Werte, Erholung, Marken und Ton teilen hochkant und Vollbild über
  `ui/hf_live.HfLive`; Zustand im `AppState` (`hf_erholung`, `hf_zielton`, `hf_stumm`,
  `hf_intervall`). **Zielbereich** = zwei selbst gesetzte Linien
  (`HfEinstellungen.alarm_bpm`/`ziel_unten_bpm`), Ton darüber/darunter verschieden, **Tonfolge
  nach Abstand** (`core.hf_ziel.TONFOLGE`, Takt 0; feste Takte bleiben), eine Uhr für Messung,
  Vollbild und Fokus (`Zielton`), Stumm für eine Zeit oder bis Messende — sichtbar immer
  „Zielbereich“, nie „Warnung/Grenze/Alarm“, keine Steuerung. **Wertebereich** der HF-Achse je
  Seite (Automatik · Profil · fest, `core.hf_ziel.wertebereich`), weicht der Kurve.
  **Erholung:** Fenster 30/60/120 und ein freies X, „Messen bis“ beendet sie. **Intervall**
  (nur Vollbild): abgelesene Erholung aus hrv-core `intervall_erholung` — nur 5-s-Mittel, Bezug
  Spitze (Plateau: letzte Stelle) oder Anfang, HRR = Bezug − Ende, Hinweis, wenn das Ende über
  dem tiefsten Wert liegt; nichts gespeichert außer auf Wunsch als Notiz.

- **Speichern, ohne zu beenden** (Ben, 10.11.2026, A21): Das Menü neben „Stopp & speichern“
  hat **„Zwischenstand speichern“** — die Aufnahme bis hier wird eine Aufzeichnung
  (`Messlauf.aufnahme_zwischenstand_async`, Datei `…_zwischen.json`, ohne Beiwerk), **dieselbe
  Aufnahme läuft weiter**, am Ende steht alles in einer Datei (lange Ströme für VLF/ULF). Die
  ganze Messdatei **ersetzt** ihre Zwischenstände (`Gespeichert.ersetzt` →
  `views.messung.aufnahme_eintragen` nimmt Zeile und Dateien weg); am Zwischenstand ergänzte
  Notizen und Abschnitte kommen vorher in die Aufnahme, Zuschnitt und Korrektur nicht.
  „Teil speichern, weiter aufnehmen“ (zwei Dateien) steht daneben; **„Zusammenfügen …“** über
  der Liste der Aufzeichnungen macht aus Teilen wieder eine Datei (`…_zusammen.json`,
  `devices.messlauf.teile_zusammenfuegen` über `hrv_core.zusammenfuegen`, Teile bleiben).
  **Training:** läuft die Messung eines gespeicherten Trainings noch, liest die Auswertung
  ihren jüngsten Zwischenstand (`ui.training.hrv_bezug`); „Bis hier auswerten“ zeigt das
  **laufende** Training (`/ausdauer/unterwegs`, `AppState.strecke_unterwegs` — steht in keiner
  Tabelle, nichts wird gespeichert).
  **Messansicht** (A21): Bereich Zeit · Frequenz · Nichtlinear und die Kurven-Chips stehen im
  Blatt „Fenster & Darstellung“ (`verlauf.Kurvenwahl`), nicht zwischen den Kurven; die
  Poincaré-Wolke ist dort abschaltbar, die Notizliste hat einen Griff für ihre Höhe.
