# L02 — Übung

## Aufgabe 1: update() begreifen

Starte `beispiel_02.py`. Klick erst den Zähler oben ein paarmal, dann starte
die Messung und schau beiden Anzeigen eine Weile zu. Klick zum Schluss — bei
laufender Messung — noch einmal irgendeinen Knopf.

**Fragen:**
1. Der Handler des Zählers ruft kein `update()` auf. Warum funktioniert er
   trotzdem?
2. Der Hintergrund-Task setzt **beide** Anzeigen auf denselben Wert — warum
   friert nur eine ein?
3. Warum springt die eingefrorene Anzeige auf den aktuellen Wert, sobald du
   irgendeinen Knopf klickst?
4. Im Task steht `anzeige_mit.update()`. Es ginge auch `page.update()`.
   Wann ist welches besser?

## Aufgabe 2: Karte lesen

Öffne `beispiel_03.py` und zeichne den Control-Baum von `uebungskarte()` auf
Papier.

**Fragen:**
1. Warum hat die mittlere `Column` ein `expand=True`?
2. Was passiert, wenn du es entfernst? Probier es aus.
3. Was bewirken `max_lines=2` und `overflow=ELLIPSIS`? Lösch sie testweise und
   schau dir eine Übung mit langer Beschreibung an.

## Aufgabe 3: Karte erweitern

Ergänze `uebungskarte()` um die **Kategorie** als kleine Markierung
(z. B. „Atmung, Entspannung"). Sie steht in `uebung["typen"]` — einer Liste, die du mit `", ".join(…)` zu einem Text machst.

Anforderungen:
- klein und dezent, sie darf den Namen nicht erschlagen
- eigene Hintergrundfarbe aus dem Theme
- sie soll sich auch im Dunkelmodus richtig verhalten

Tipp: ein `Container` mit `padding`, `border_radius` und `bgcolor` um einen
kleinen `Text`. Zum Prüfen `page.theme_mode` auf `ft.ThemeMode.DARK` stellen.

## Aufgabe 4: Ein Zähler zum Training

Schreibe `wiederholungen.py`: ein Zähler für Wiederholungen während einer Übung.

- große Zahl in der Mitte
- ein großer „+1"-Knopf (er wird beim Training getroffen, nicht in Ruhe)
- ein kleiner „−1" für Vertipper
- ein „Zurücksetzen"
- unter der Zahl das Ziel: „von 15"
- **wenn das Ziel erreicht ist, wird die Zahl grün**

Das ist die Vorstufe dessen, was in M3 wirklich gebraucht wird.

Tipp für die Farbe:

```python
anzeige.color = ft.Colors.PRIMARY if stand >= ziel else None
```

## Zum Nachdenken

Der Übungskatalog wird später 200 Einträge haben.

1. Was wäre schlecht daran, bei jeder Änderung `page.update()` aufzurufen?
2. `beispiel_03.py` benutzt `ft.ListView` statt `ft.Column`. Warum wohl?

[Lösungen](loesung/)
