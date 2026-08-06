# Roadmap

Die App entsteht entlang des Lernpfads (`docs/tutorial/`). Jede Lektion führt zu
einem sichtbaren Fortschritt in der App.

| M | Inhalt | nach Lektion | Stand |
|---|---|---|---|
| **M0** | Repo, Kompatibilitätsvertrag, Schema, Verträge, CI | — | **fertig** |
| M1 | Flet-Hülle: Navigation, Theme, Ansichten — einmal aufs Handy gebaut | L03 | offen |
| M2 | Übungskatalog aus der Datenbank, Suche, Detailansicht, Videoverweise | L05 | offen |
| M3 | Training dokumentieren: spec-getriebene Eingabe, „Wie zuletzt", Sitzungen | L07 | offen |
| M4 | `hrv_core` vollständig + Simulator, Golden-Tests grün | L09 | teilweise |
| M5 | Echte Geräte auf dem Desktop + Sensor-Prüfstand | L10 | offen |
| M6 | Live-Messung mit Diagrammen, Aufzeichnung nach `raw-v1` | L11 | offen |
| M7 | Limits und Trainingssteuerung | L11 | teilweise |
| M8 | Auswertung, Benchmarks, Verlaufsdiagramme, Export-Round-Trip | L12 | offen |
| M9 | Eigene Flet-Extension: BLE und Foreground Service auf Android | Ausblick A | offen |
| M10 | Medien: eigene Übungen mit Foto, Dokumentationsvideos | — | offen |
| M11 | Edition B: Outbox-Sync, Anmeldung, Nachrichten, Übungszuweisung | Ausblick B | offen |

## Was in M0 bereits steht

- `main` mit Grundgerüst, AGPL-3.0 und CLA
- **`docs/kompatibilitaet.md`** — der Datenformat-Vertrag mit praxis_gui
- Vollständiges Datenbankschema (`001_init.sql`) inklusive Synchronisationsfelder
- `hrv_core`: `raw-v1` lesen/schreiben, Plausibilitätsfilter, Boundary-Skip,
  Lückenerkennung, Segmentierung, Zeitbereich, Malik-Korrektur, Poincaré
- `core`: Datenmodell, `ResultSpec`, Kurzschrift-Parser, Limit-Regeln
- `devices`: Port, Bluetooth-Parser, Geräteprofile, Simulator
- 81 Tests, Linter sauber, CI

## Teilweise: was noch fehlt

- `hrv_core/frequency.py` — Welch und Lomb-Scargle in numpy (**L09**)
- `hrv_core/nonlinear.py` — DFA α1 und Sample Entropy (**L09**)
- `data/repositories.py` — Lesen und Schreiben der Domänenobjekte (**L04**)
- `devices/bleak_source.py` — Desktop-BLE (**L10**)
- Alle Ansichten in `ui/views/` (**ab L03**)

## Bewusst nicht eingeplant

- **Fitbit Web API** — Abschaltung im September 2026; der Nachfolger liefert
  ohnehin nur aggregierte Werte
- **Garmin Enhanced BBI, Suunto-API, Samsung Privileged Health SDK,
  Withings Raw Data** — Partnerprogramme mit Vertrag und Kosten
- **Health Connect / Apple Health als HRV-Quelle** — es gibt dort keinen
  Datentyp für Schlag-zu-Schlag-Intervalle. Als Kontextquelle (Schlaf,
  Ruhepuls, Schritte) später sinnvoll.
