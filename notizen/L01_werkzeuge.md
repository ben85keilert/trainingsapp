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

`ft.run(main)` ruft `main` später selbst auf und reicht dabei das Fenster-Objekt
herein — **wir** rufen `main` nie direkt auf. Ohne Annotation wüsste also niemand, was
`page` ist:

- **Editor:** kennt durch `ft.Page` alle Attribute und Methoden → Autovervollständigung
  für `page.title`, `page.add(…)`, `page.theme_mode`; Tippfehler wie `page.titel` werden
  markiert. Ohne Annotation ist `page` ein anonymes Objekt und der Editor schweigt.
- **Leser:** sieht in der Signatur, womit die Funktion arbeitet, ohne `ft.run`
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

### „Abhängigkeiten zeigen nur nach innen"

Nicht die *Tests* zeigen nach innen, sondern die **Abhängigkeiten** — also wer wen
importieren darf:

```
ui → core, data, hrv_core, devices
devices → hrv_core
data → core
core → (nichts)
hrv_core → (nur numpy)
```

Gelesen als Schichten von **außen** (Bildschirm) nach **innen** (Domäne): eine äußere
Schicht darf eine innere kennen, **nie umgekehrt**. Würde `core` etwas aus `ui`
importieren, entstünde ein Zirkelbezug und die Domäne wäre nicht mehr ohne Flet ladbar.

`hrv_core → (nur numpy)` ist die engste Zeile: `hrv_core` darf **nichts** aus dem
eigenen Projekt importieren, auch nicht `core`. Bewusst so eng, weil `hrv_core` auf
Android/iOS läuft und dort so eigenständig wie möglich bleiben soll.

**Wenn `hrv_core` doch etwas aus `core` bräuchte** — es gibt keinen sauberen Import-Weg
dafür. Die Optionen wären:

1. die Definition **nach `hrv_core` verschieben**, wenn sie eigentlich zur HRV-Domäne
   gehört,
2. sie **duplizieren**, wenn sie klein und stabil ist,
3. die Abhängigkeit **umdrehen**: `core` importiert von `hrv_core` (wäre erlaubt, ist
   aktuell aber nicht vorgesehen).

**Wichtig — was der Test *nicht* prüft:** `tests/test_import_regel.py` erzwingt nur die
`flet`/`scipy`-Verbote aus dem `VERBOTEN`-Dict. Der **komplette Abhängigkeitsgraph** oben
ist damit *nicht* abgedeckt: ein `devices`-Modul, das versehentlich `core` importiert,
fiele diesem Test **nicht** auf. Das ist bislang nur dokumentierte Konvention.

### Zweiter Grund für den Test: CI hat gar kein flet

`.github/workflows/ci.yml` installiert nur `numpy pytest ruff mypy` — **kein `flet`**.
Ein `import flet` in `core/units.py` würde in CI deshalb nicht nur den Architektur-Test
kippen, sondern schon beim Import mit `ModuleNotFoundError` abstürzen. Das ist die
härtere Antwort auf „Warum ein Test statt einer Notiz in der Doku?": die Umgebung, in der
die Domäne laufen soll (CI heute, Android später), **hat `flet` schlicht nicht**.

## CI (`.github/workflows/ci.yml`)

CI = *Continuous Integration*: bei jedem Push/PR laufen die Prüfungen automatisch auf
einem **frischen Rechner bei GitHub** — nicht lokal. Statt „lief bei mir" gilt „läuft auf
einer leeren Maschine".

| Zeile | Bedeutung |
|---|---|
| `on: push: branches: [main, "claude/**"]` | läuft bei Push auf `main` und alle `claude/…`-Branches |
| `on: pull_request:` | leerer Wert = **Standard**, nicht „kein Eintrag": jeder PR (opened/synchronize/reopened) |
| `runs-on: ubuntu-latest` | GitHub startet eine **neue, leere Ubuntu-VM** in der Cloud |
| `matrix: python-version: ["3.12","3.13"]` | der ganze Job läuft **zweimal**, je einmal pro Python-Version |
| `fail-fast: false` | fällt 3.12 durch, läuft 3.13 trotzdem zu Ende (man sieht beide Ergebnisse) |
| `actions/checkout@v4` | klont das Repo in die VM |
| `actions/setup-python@v5` + `cache: pip` | installiert Python; cacht die pip-**Downloads** zwischen Läufen |

Danach die Schritte in dieser Reihenfolge: `ruff check .` → `ruff format --check .` →
`pytest -q` → Doctests → die Lernpfad-Beispiele einzeln ausführen.

**Warum `pip install` bei *jedem* Lauf?** Weil die VM jedes Mal neu und leer ist — sie
existiert nur für diesen einen Lauf und wird danach weggeworfen. Genau das ist der Sinn:
gäbe es einen dauerhaften Rechner, würde sich dort mit der Zeit Zustand ansammeln
(Reste alter Installationen), und „grün" hieße nicht mehr „läuft von Null an". `cache:
pip` beschleunigt nur das **Herunterladen** der Pakete, das **Installieren** passiert
weiterhin jedes Mal.

`PYTHONPATH: src` bei den Testschritten ersetzt das lokale `pip install -e .` — die CI
installiert das Projekt selbst nicht, sondern zeigt Python nur, wo `trainingsapp/` liegt.