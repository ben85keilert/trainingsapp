# L06 — Checkliste

## Das kann ich jetzt

- [ ] Ich kann eine `ResultSpec` lesen und schreiben und weiß, was `fields`,
      `shorthand` und `chart_metrics` jeweils bewirken
- [ ] Ich kann aus einer Spezifikation Widgets bauen und aus den Widgets ein
      Dict zurücklesen — mit Umwandlung je Feldtyp
- [ ] Ich kann die drei Stufen der Beschleunigung nennen und begründen, warum
      der Kurzschrift-Parser die letzte ist
- [ ] Ich kann erklären, warum jeder Eintrag eine Kopie seiner Spezifikation
      speichert, und ein Szenario nennen, in dem sie Daten rettet
- [ ] Ich weiß, warum `chart_metrics` nach `measurement` kopiert werden statt
      beim Zeichnen aus JSON gelesen
- [ ] Ich kann begründen, warum Einträge nicht geändert, sondern ersetzt werden

## Wenn ein Haken fehlt

Punkt 3 ist der, der sich nur auf dem Handy erschließt. Beispiel 2 einmal mit
`flet run --android` starten und „3x12" auf alle drei Arten eingeben. Wer
danach noch den Parser zuerst bauen will, hat ein gutes Argument, das ich
hören möchte.

Punkt 4 und 6 sind dieselbe Idee aus zwei Richtungen: Was einmal erfasst
wurde, bleibt so lesbar, wie es erfasst wurde.

## Was wir als Nächstes bauen

Noch nicht M3 — dafür fehlt **L07**: async in Flet. Ein Timer, der pausiert,
weiterläuft und sauber abgebrochen wird, ist die Voraussetzung für Übungen mit
Haltezeit.

Mit L06 und L07 zusammen entsteht dann **M3 — Training dokumentieren**:

| Datei | Inhalt |
|---|---|
| `ui/components/spec_form.py` | aus Aufgabe 3 |
| `data/repositories.py` | `SessionRepo` aus Aufgabe 4 |
| `ui/views/training.py` | Sitzung starten, Übung wählen, Formular, „Wie zuletzt" |
| `ui/views/heute.py` | zeigt die letzten Einträge statt Kacheln |
| `core/limits.py` | Timer-Regeln, die L07 zum Laufen bringt |

Wer die Übungen 3 und 4 gemacht hat, hat die Hälfte von M3 bereits im
Repository.
