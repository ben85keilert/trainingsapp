# L01 — Werkzeuge und Projektaufbau

**Ziel:** Die Umgebung läuft, du verstehst den Projektaufbau, und du weißt, wie
wir zusammen am Code arbeiten.

Zeit: ungefähr eine Stunde.

---

## 1. Was Flet eigentlich ist

Das ist die Frage, die beim letzten Projekt offengeblieben ist — deshalb zuerst.

Flutter ist Googles Oberflächen-Baukasten. Er ist in **Dart** geschrieben, malt
alles selbst auf eine Leinwand und läuft dadurch auf Android, iOS, Windows,
macOS, Linux und im Browser gleich.

Flet setzt eine Python-Schicht davor:

```
   Dein Python-Code
        ↕            (Brücke: früher Sockets, seit 0.86 in-process)
   Flutter (Dart)
        ↓
   Bildschirm
```

Du schreibst `ft.Text("Hallo")`. Flet schickt die Beschreibung dieses Elements
über die Brücke, Flutter baut daraus ein echtes `Text`-Widget und zeichnet es.
Klickt jemand darauf, geht das Ereignis den Weg zurück zu deiner Python-Funktion.

**Drei Folgerungen, die den ganzen Rest erklären:**

1. **Deine Logik bleibt Python.** numpy, sqlite3, pandas — alles nutzbar. Das
   ist der Grund, warum wir HRV-Mathematik überhaupt in dieser App rechnen können.
2. **Die Oberfläche ist Flutter.** Was Flutter nicht kann, kann Flet nicht —
   es sei denn, man schreibt eine Extension in Dart. Genau das brauchen wir
   später für Bluetooth.
3. **Nicht jedes Python-Paket läuft auf dem Handy.** Alles mit kompiliertem
   Code braucht ein vorgebautes Wheel für Android. numpy gibt es, scipy nicht.
   Darum steht in `CONTRIBUTING.md`, dass `hrv_core/` kein scipy importieren darf.

---

## 2. Umgebung einrichten

Das Projekt benutzt [uv](https://docs.astral.sh/uv/) — ein Werkzeug, das drei
Dinge auf einmal erledigt: die richtige Python-Version besorgen
(`.python-version`), eine virtuelle Umgebung anlegen (`.venv/`) und alle
Abhängigkeiten exakt so installieren, wie sie in `uv.lock` festgeschrieben sind.
Dadurch hat jeder, der das Projekt auscheckt, dieselbe Umgebung.

```bash
cd trainingsapp
uv sync
```

Das Projekt selbst wird dabei „editierbar" installiert: Python benutzt direkt
`src/`, statt eine Kopie zu machen. Du änderst eine Datei, der nächste Aufruf
sieht die Änderung.

Befehle startest du mit `uv run` davor — das sorgt dafür, dass sie in der
Projektumgebung laufen, ohne dass du sie erst aktivieren musst.

Prüfen:

```bash
uv run python -c "import flet; print(flet.__version__)"
uv run pytest -q
uv run ruff check .
```

`pytest` muss grün sein. Ist es das nicht, stimmt etwas an der Installation —
melde dich, bevor du weitermachst.

---

## 3. Das erste Programm

```bash
uv run python docs/tutorial/L01_werkzeuge/beispiel_01.py
```

Es öffnet sich ein Fenster. Schau dir den Quelltext an — er ist absichtlich
winzig.

Dann:

```bash
uv run flet run -d docs/tutorial/L01_werkzeuge/beispiel_02.py
```

`flet run` kann **Hot Reload**: ändere den Text im Editor, speichere, und das
Fenster aktualisiert sich. Probier das aus, es verändert das Arbeitsgefühl
erheblich.

Die Option `-d` (Verzeichnis beobachten) ist wichtig: Ohne sie löst `flet
run` einen Reload nur aus, wenn das Dateisystem-Ereignis exakt den
Skriptpfad als Quelle meldet. Editoren mit atomarem Speichern (erst eine
temporäre Datei schreiben, dann über die Zieldatei verschieben — z. B.
VS Code unter Linux) melden dabei einen anderen Pfad, wodurch der Reload
ausbleibt und du die Änderung erst nach einem Neustart siehst.

---

## 4. Wie das Projekt aufgebaut ist

```
src/trainingsapp/
├─ config.py      Edition, Funktionsschalter, Speicherorte
├─ core/          Domäne — Modelle, Notation, Regeln
├─ data/          SQLite, Migrationen, Seed-Daten
├─ hrv_core/      HRV-Mathematik, Datenformat
├─ devices/       Sensoren
└─ ui/            alles Flet-Spezifische
```

### Die eine Regel

> `core/`, `data/`, `hrv_core/` und `devices/` importieren **niemals** `flet`.

Das klingt nach Bürokratie, ist aber der Grund, warum 81 Tests ohne Bildschirm
laufen. Und wenn Flet seine API umbaut — das ist zwischen den Versionen
mehrfach passiert —, müssen wir nur `ui/` anfassen.

Ein Test erzwingt die Regel. Probier es aus:

```bash
# Schreib testweise "import flet" in den Kopf von src/trainingsapp/core/units.py
pytest tests/test_import_regel.py
# ... und mach es wieder rückgängig
```

---

## 5. Wie wir zusammenarbeiten

```
main                          ← stabil, fertige Meilensteine
claude/trainingsassistent-…   ← hier entsteht Neues
```

Nützliche Befehle:

```bash
git status                    # was habe ich geändert?
git diff                      # was genau?
git log --oneline -10         # was ist zuletzt passiert?
```

Wenn du etwas ausprobierst und es geht schief: `git checkout -- <datei>` stellt
den letzten committeten Stand wieder her. Du kannst nichts kaputt machen, was
nicht wiederherstellbar wäre.

---

## Stolperfallen

**`flet: command not found`** — der Befehl wurde ohne `uv run` gestartet und
damit außerhalb der Projektumgebung. `uv run flet …` benutzen.

**`ModuleNotFoundError: trainingsapp`** — `uv sync` wurde noch nicht
ausgeführt, oder der Befehl lief ohne `uv run` in der falschen Umgebung.

**Auf Linux öffnet sich kein Fenster** — Flet braucht GTK-Bibliotheken. Zur Not
`uv run flet run --web docs/...` , das läuft im Browser.

**Hot Reload greift nicht** — es funktioniert nur mit `flet run`, nicht mit
`python datei.py`.

---

## Weiter

→ [Übung](uebung.md) → [Checkliste](checkliste.md) → **L02: Das Flet-Modell**
