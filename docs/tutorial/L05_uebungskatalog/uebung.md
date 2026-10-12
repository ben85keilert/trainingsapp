# L05 — Übung

## Aufgabe 1: Code lesen

Beantworte anhand des Codes, nicht aus dem Gedächtnis:

1. `ExerciseRepo.suchen("")` — was passiert bei leerem Suchtext, und warum ist
   das für `katalog.py` bequem?
2. In `AppState._aktives_profil()` gibt es drei Stufen. Welche greift, wenn
   `app_setting` auf ein Profil zeigt, das inzwischen gelöscht wurde?
3. `uebung_bearbeiten.py` erkennt die Vorlage einer Übung an der Kurzschrift
   (`_vorlage_von`). Was passiert mit einer Übung, deren Spezifikation zu
   keiner Vorlage passt — etwa einer, die in L06 mit eigenen Feldern angelegt
   wird?
4. In `app.py` steht `zeige_route()` am Ende von `main()` einmal direkt. Was
   würde ohne diesen Aufruf passieren?

## Aufgabe 2: Beispiel 3 umbauen

Füge in Beispiel 3 eine vierte Reihe hinzu, die `functools.partial` benutzt:

```python
from functools import partial
ft.Button(n, on_click=partial(melden_mit_ereignis, n))
```

Dafür brauchst du eine Funktion, die zwei Parameter nimmt — den Namen und das
Ereignis. Warum muss der Name **vor** dem Ereignis stehen?

## Aufgabe 3: Tags im Katalog

Der Seed trägt Tags (`"tags": ["Atmung", "HRV"]`), das Schema hat `tag` und
`exercise_tag`, aber nichts davon landet bisher in der Datenbank.

1. Erweitere `ExerciseRepo.speichern()`, sodass die Tags einer Übung
   gespeichert werden. Fehlende Tags in `tag` anlegen, die Zuordnung in
   `exercise_tag` komplett ersetzen (wie bei den Medien).
2. Erweitere `_mit_medien()` — oder schreibe eine Schwester `_mit_tags()` —
   sodass `laden()` und `alle()` die Tags zurückbringen. **Eine** Abfrage für
   alle Übungen, nicht eine je Übung.
3. Zeige die Tags in der Detailansicht als Chips an.

Tests in `tests/test_repositories.py`:
- speichern und laden bringt dieselben Tags in derselben Reihenfolge
- zwei Übungen mit demselben Tag erzeugen nur **eine** Zeile in `tag`
- Tag entfernen und speichern entfernt die Zuordnung

## Aufgabe 4: Archivierte wiederherstellen

Archivierte Übungen verschwinden aus dem Katalog und sind nicht mehr erreichbar.
Baue in die Einstellungen einen Abschnitt „Archivierte Übungen" mit einer
Liste und je einem Knopf „Wiederherstellen". `ExerciseRepo.wiederherstellen()`
existiert bereits.

Welche Methode des Repositories brauchst du für die Liste? Reicht sie, oder
fehlt etwas?

## Zum Nachdenken

1. Der Seed erkennt Übungen an der ID. Was passiert, wenn ein Nutzer eine
   mitgelieferte Übung **archiviert** und dann die App aktualisiert? Ist das
   gewollt?
2. Die Suche läuft in SQL. Wann wäre es besser, alle Übungen einmal zu laden
   und in Python zu filtern?
3. `AppState` hält Suchtext und Filter des Katalogs. Sollte er auch die
   Scrollposition halten? Was spricht dagegen?

[Lösungen](loesung/)
