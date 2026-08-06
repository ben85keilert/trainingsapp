# L04 — Checkliste

## Das kann ich jetzt

- [ ] Ich kann eine Migration schreiben und weiß, warum eingespielte nie
      verändert werden
- [ ] Ich weiß, warum `PRAGMA foreign_keys = ON` bei jeder Verbindung nötig ist
- [ ] Ich kann ein Repository schreiben, das SQL an einer Stelle hält
- [ ] Ich weiß, wie `bool` und `datetime` in SQLite behandelt werden müssen
- [ ] Ich kann erklären, warum die HRV-Rohdaten **nicht** in der Datenbank liegen
- [ ] Ich schreibe Tests mit `tmp_path` und lasse sie mit `pytest` laufen

## Wenn ein Haken fehlt

Punkt 5 ist der, der am ehesten Widerspruch auslöst — SQLite wäre technisch
völlig in der Lage dazu. Wenn die Begründung nicht überzeugt, sprich es an; es
ist eine Entscheidung, keine Naturkonstante.

## Was wir als Nächstes bauen

**M2 — der Übungskatalog wird echt.**

- Beim ersten Start wird der Seed-Katalog eingespielt
- Die Liste kommt aus der Datenbank statt aus der JSON-Datei
- Suche und Filter nach Kategorie
- Detailansicht mit Beschreibung und Videoverweis
- Eigene Übungen anlegen — mit Symbolauswahl

Damit ist die App zum ersten Mal wirklich benutzbar: Du kannst nachschlagen,
was du trainieren wolltest.

**L05** liefert dazu die restlichen Bausteine: Seed-Daten, Suche, Filter und
Medienverweise. Danach kommt mit **L06** die Trainingsdokumentation — und damit
die spannendste Frage des Projekts: wie wird die Eingabe schnell genug, dass man
sie tatsächlich benutzt?
