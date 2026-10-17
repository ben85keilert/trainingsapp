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

**M3 — Pläne, Abarbeiten, Tagebuch.** Der Kern der App:

| Datei | Inhalt |
|---|---|
| `ui/components/spec_form.py` | aus Aufgabe 3 |
| `data/repositories.py` | `PlanRepo`, `SessionRepo` (Aufgabe 4), `DayNoteRepo` |
| `ui/views/heute.py` | Pläne mit „x von n heute", darunter der Tag; seit 18.10.2026 der Tag aus `tag.py` mit „Nachtragen“ |
| `ui/views/plan.py` | abhaken (Tipp = gemacht, Ziel-Chip = wie geplant), bearbeiten |
| `ui/views/tag.py` | Tagesansicht: nach Plan, Zeit oder Übung; Notizen je Ebene (seit 18.10.2026: Übersicht und Zeitleiste, `core/tag.py`) |
| `ui/views/eintrag.py` | ansehen, korrigieren, löschen mit Rückfrage |
| `ui/views/verlauf.py` | Woche, Tag und Übungen; die Kurve je Übung in `verlauf_kachel.py` (seit 17.10.2026) |

Kein Timer — der kommt mit **L07** (async) als eigener Schritt in die
Planansicht. Wer die Übungen 3 und 4 gemacht hat, hat die Datenschicht von
M3 bereits im Repository.
