# L03 — Checkliste

## Das kann ich jetzt

- [ ] Ich kann Ansichten über eine Navigationsleiste wechseln
- [ ] Ich verstehe `page.views` als Stapel und weiß, wie der Zurück-Knopf entsteht
- [ ] Ich kann Zustand von der Oberfläche trennen und begründen, warum
- [ ] Ich kenne das Muster „Handler ändert Zustand, `zeichnen()` leitet Anzeige ab"
- [ ] Ich weiß, warum eine laufende Messung nicht in einer Ansicht liegen darf

## Wenn ein Haken fehlt

Punkt 3 und 5 hängen zusammen und sind wichtig. Sie entscheiden darüber, ob die
Live-Messung später funktioniert oder bei jedem Ansichtswechsel abreißt.

## Was wir als Nächstes bauen

**M1 — die Hülle der App.** Endlich echter Code:

| Datei | Inhalt |
|---|---|
| `ui/state.py` | `AppState` mit Datenbankverbindung, Person, Übungen |
| `ui/app.py` | Navigation, Routen, Theme |
| `ui/views/heute.py` | Startbildschirm |
| `ui/views/katalog.py` | Übungsliste (aus deinem L02-Beispiel) |
| `ui/views/uebung_detail.py` | Detailansicht über eine Route |
| `ui/views/messung.py` | Platzhalter bis L11 |
| `ui/views/verlauf.py` | Platzhalter bis L12 |

Danach ist die App zwar noch leer, aber sie hat ihre endgültige Form. Alles
Weitere füllt Ansichten, statt die Struktur umzubauen.

**L04** kommt direkt danach: Woher die Übungen kommen — Datenbank statt
JSON-Datei. Damit wird aus M1 dann M2.
