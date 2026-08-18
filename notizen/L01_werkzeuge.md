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

## Typannotationen: `def main(page: ft.Page) -> None:`

Zur **Laufzeit passiert dadurch nichts**. Python prüft Annotationen nicht und erzwingt
sie nicht — ein `main("kein Page-Objekt")` liefe ungehindert los und schlüge erst beim
ersten `page.title = …` fehl. Annotationen richten sich an Werkzeuge (mypy, Editor) und
an Menschen, nicht an den Interpreter.

### Der Doppelpunkt — dieselbe Notation, vier Bedeutungen

Der `:` ist in Python stark überladen; entscheidend ist **wo** er steht:

| Schreibweise | Bedeutung | Vererbung? |
|---|---|---|
| `def f(x: int):` | Typannotation eines **Parameters** | nein |
| `def f() -> int:` | Typannotation des **Rückgabewerts** (Pfeil, nicht Doppelpunkt) | nein |
| `x: int = 5` | Typannotation einer **Variablen** | nein |
| `class A(B):` | Klassendefinition, `A` **erbt** von `B` | **ja** |

Vererbung steht immer in **runden Klammern hinter dem Klassennamen** — nie hinter einem
Doppelpunkt. Der Doppelpunkt am Zeilenende (`if …:`, `def …:`, `class …:`) eröffnet
zusätzlich einfach einen eingerückten Block; das ist nochmal eine andere Rolle desselben
Zeichens.

### Was `page: ft.Page` konkret bringt

`ft.app(target=main)` ruft `main` später selbst auf und reicht dabei das Fenster-Objekt
herein — **wir** rufen `main` nie direkt auf. Ohne Annotation wüsste also niemand, was
`page` ist:

- **Editor:** kennt durch `ft.Page` alle Attribute und Methoden → Autovervollständigung
  für `page.title`, `page.add(…)`, `page.theme_mode`; Tippfehler wie `page.titel` werden
  markiert. Ohne Annotation ist `page` ein anonymes Objekt und der Editor schweigt.
- **Leser:** sieht in der Signatur, womit die Funktion arbeitet, ohne `ft.app`
  nachschlagen zu müssen.
- **mypy:** kann Aufrufe gegen die echte Flet-API prüfen.

### Für wen das `-> None`

`main` gibt ohnehin implizit `None` zurück — insofern beschreibt `-> None` nur, was
sowieso passiert. Redundant ist es trotzdem nicht, aus zwei Gründen:

**1. Es schaltet die mypy-Prüfung des Funktionsrumpfs überhaupt erst ein.** In der
Standardeinstellung (und `[tool.mypy]` in `pyproject.toml` setzt kein
`disallow_untyped_defs`) überspringt mypy den **Rumpf jeder gar nicht annotierten
Funktion** komplett. Nachgemessen mit derselben Zeile in beiden Funktionen:

```python
def ohne_annotation(x):          # Rumpf wird NICHT geprüft
    return "text" + 1            # → mypy schweigt

def mit_annotation(x: int) -> None:   # Rumpf wird geprüft
    return "text" + 1            # → error: Unsupported operand types for + ("str" and "int")
```

Eine Funktion ohne jede Annotation ist für mypy also ein blinder Fleck. Erst die
Annotation macht sie sichtbar.

**2. Es macht „gibt nichts zurück" zur prüfbaren Zusage.** Käme später versehentlich ein
`return` mit Wert hinzu, meldet mypy das — aber nur wegen des expliziten `-> None`:

```python
def ohne_rueckgabetyp(x: int):   # mypy leitet den Typ selbst ab
    return x * 2                 # → kein Fehler

def mit_none(x: int) -> None:
    return x * 2                 # → error: No return value expected
```

Gelesen heißt `-> None` darum: „Der Rückgabewert ist *absichtlich* uninteressant — ruf
diese Funktion nicht auf, um ihr Ergebnis zu verwenden."

> **Einschränkung:** `[tool.mypy]` prüft nur `packages = ["trainingsapp"]`, also
> `src/trainingsapp/`. Die Tutorial-Beispiele unter `docs/tutorial/` sieht mypy nicht —
> sie schreiben die Annotationen trotzdem mit, damit die Gewohnheit stimmt, wenn es in
> `src/` zählt.

## Hot Reload: `flet run` braucht `-d`

```bash
flet run -d docs/tutorial/L01_werkzeuge/beispiel_02.py
```

**Ohne `-d` bleibt der Reload beim Speichern oft aus.** Grund (nachgesehen in
`flet_cli/commands/run.py`): ohne die Option löst Flet nur dann neu, wenn das
Dateisystem-Ereignis **exakt den Skriptpfad** als Quelle meldet. Editoren, die *atomar*
speichern — erst eine temporäre Datei schreiben, dann über die Zieldatei verschieben, so
z. B. VS Code unter Linux — melden dabei den Pfad der temporären Datei. Die Prüfung
schlägt fehl, nichts passiert, und die Änderung erscheint erst nach einem Neustart.

`-d` beobachtet das ganze Verzeichnis und lässt jede Änderung darin einen Reload
auslösen; `-r` täte dasselbe zusätzlich rekursiv für Unterordner.

Merksatz: `python beispiel_02.py` kann **nie** Hot Reload — das kann nur `flet run`.

## Die eine Architekturregel (Wiederholung aus L01)

> `core/`, `data/`, `hrv_core/` und `devices/` importieren **niemals** `flet`;
> `hrv_core/` zusätzlich **niemals** `scipy`.

Erzwungen durch `tests/test_import_regel.py`. Grund: Domäne bleibt ohne Bildschirm
testbar, spätere Umstellung auf Flet 1.0 betrifft nur `ui/`; scipy gibt es nicht auf
Android/iOS.