# L01 — Übung

## Aufgabe 1: Umgebung prüfen

Führe aus und halte die Ausgaben fest:

```bash
python -c "import flet; print(flet.__version__)"
pytest -q
ruff check .
```

Alle drei müssen ohne Fehler durchlaufen.

## Aufgabe 2: Hot Reload erleben

Starte `uv run flet run -d docs/tutorial/L01_werkzeuge/beispiel_02.py` und ändere bei
laufendem Fenster:

- den Text der Überschrift
- die Schriftgröße (`size=28`)
- die Hintergrundfarbe (`ft.Colors.BLUE_100` → probier `GREEN_100`, `AMBER_100`)

**Frage:** Was passiert, wenn du einen Syntaxfehler einbaust und speicherst?
Repariere ihn wieder — läuft es weiter?

## Aufgabe 3: Die Importregel testen

Baue absichtlich einen Verstoß:

```python
# ganz oben in src/trainingsapp/core/units.py
import flet
```

Dann:

```bash
pytest tests/test_import_regel.py -v
```

**Fragen:**
1. Wie lautet die Fehlermeldung?
2. Warum ist so ein Test besser als eine Notiz in der Dokumentation?

Mach die Änderung rückgängig (`git checkout -- src/trainingsapp/core/units.py`).

## Aufgabe 4: Eigenes Beispiel

Schreibe `mein_erstes.py` in diesem Ordner. Es soll:

- ein Fenster mit dem Titel „Mein Trainingsassistent" öffnen
- deinen Namen anzeigen
- darunter drei Übungsnamen deiner Wahl untereinander

Tipp: `ft.Column(controls=[...])` stapelt Elemente untereinander.

## Zum Nachdenken

`beispiel_03.py` rechnet HRV-Kennzahlen, ohne dass ein Fenster aufgeht.

1. Warum ist das für dieses Projekt wichtig?
2. Was wäre der Nachteil, wenn `compute_time_domain` in einer Flet-Ansicht stünde?

Die Antworten stehen in der [Lösung](loesung/).
