# L05 — Checkliste

## Das kann ich jetzt

- [ ] Ich kann erklären, warum der Seed deterministische IDs benutzt und was
      passiert, wenn der Namensraum sich ändert
- [ ] Ich erkenne ein N+1-Problem und weiß, wie `_mit_medien()` es vermeidet
- [ ] Ich kann eine Suche mit Rang in SQL schreiben
- [ ] Ich kann einen Handler in einer Schleife ohne Lambda-Falle schreiben
      (Fabrikfunktion) und erklären, warum das Lambda scheitert
- [ ] Ich weiß, wie ein Flet-Dienst (`UrlLauncher`) registriert wird
- [ ] Ich kann eine zweite Migration schreiben und erklären, was beim Start mit
      einer alten Datenbank passiert

## Wenn ein Haken fehlt

Punkt 4 ist der, an dem die meisten hängen. Beispiel 3 mit allen drei Reihen
einmal durchklicken und dann **A** erklären, ohne hinzusehen — wer das kann,
hat Closures verstanden. Alles Weitere im Projekt (Formulare in L06, Timer in
L07) baut darauf.

Punkt 6 ist in M2 nebenbei passiert: Deine Datenbank aus L04 hat Migration 002
bekommen, ohne dass du etwas gelöscht hast. Schau mit `sqlite3` hinein:
`PRAGMA user_version;` und `.tables`.

## Was wir als Nächstes bauen

**M3 — Training dokumentieren.** Die spannendste Frage des Projekts: Wie wird
die Eingabe schnell genug, dass man sie tatsächlich benutzt?

- Eingabemaske aus der `ResultSpec` der Übung erzeugt
- Vorbelegung aus dem letzten Eintrag und ein Knopf „Wie zuletzt"
- Chips für die häufigsten Werte
- Jeder Eintrag speichert eine Kopie seiner Spezifikation
- Kennzahlen (`chart_metrics`) wandern in `measurement` — der Rohstoff für den
  Verlauf in L12

**L06** liefert dafür die Bausteine. Danach kommt **L07** mit async und
Timern, und mit beidem zusammen entsteht M3.
