# L01 — Werkzeuge (eigene Notizen)

## Prüfbefehle

| Befehl | Was es macht |
|---|---|
| `pytest` | führt alle Tests in `tests/` aus. Grün = alles bestanden. |
| `pytest -q` | dieselbe Prüfung, kompaktere Ausgabe. |
| `pytest tests/test_hrv_core.py` | nur eine Testdatei. |
| `pytest tests/test_hrv_core.py::test_name -q` | nur ein einzelner Test. |
| `ruff check .` | Linter — findet Fehler/Stilprobleme, ohne den Code auszuführen. |
| `ruff format --check .` | prüft Formatierung (Einrückung, Zeilenlänge …), ändert nichts. |
| `ruff format .` | wie oben, aber formatiert die Dateien tatsächlich um. |

Alle drei (`ruff check .`, `ruff format --check .`, `pytest`) laufen genauso in der CI
(`.github/workflows/ci.yml`). Lokal grün → PR i. d. R. auch dort grün.

## Golden Tests

- Vergleichen die Ausgabe einer Berechnung gegen eine fest hinterlegte, bekannt-korrekte
  Referenz ("golden" = Referenz gilt als Wahrheit).
- Liegen hier unter `tests/golden/rr/`.
- Grund: HRV-Formeln (SDNN, RMSSD, DFA, …) sind fehleranfällig genug, dass "läuft ohne
  Absturz" nicht reicht — der Golden Test stellt sicher, dass dieselben Eingabedaten
  immer dieselbe bekannt-richtige Zahl ergeben.
- **Regel:** Jede Änderung an der HRV-Mathematik (`hrv_core/`) braucht einen
  Golden-Test — bestehenden anpassen (mit Begründung) oder neuen Fall ergänzen.

## Die eine Architekturregel (Wiederholung aus L01)

> `core/`, `data/`, `hrv_core/` und `devices/` importieren **niemals** `flet`;
> `hrv_core/` zusätzlich **niemals** `scipy`.

Erzwungen durch `tests/test_import_regel.py`. Grund: Domäne bleibt ohne Bildschirm
testbar, spätere Umstellung auf Flet 1.0 betrifft nur `ui/`; scipy gibt es nicht auf
Android/iOS.