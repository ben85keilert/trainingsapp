# Lernpfad

Hier lernst du Flet, und nebenbei entsteht der Trainingsassistent.

**So läuft es ab:** Du arbeitest eine Lektion durch — lesen, Beispiele
ausprobieren, Übung lösen. Danach bauen wir gemeinsam den nächsten Teil der App.
Die Lektion erklärt das Werkzeug, der Meilenstein benutzt es für etwas Echtes.

Vorausgesetzt werden Python-Grundlagen: Funktionen, Klassen, Listen, ein wenig
`numpy` und `sqlite3`. Alles Flet-Spezifische, async, BLE und Packaging wird von
Grund auf erklärt.

---

## Aufbau einer Lektion

```
L04_daten_und_sqlite/
├─ README.md        Erklärung, Hintergrund, Stolperfallen
├─ beispiel_01.py   lauffähig:  uv run python docs/tutorial/L04.../beispiel_01.py
├─ uebung.md        Aufgabe
├─ loesung/         erst nach dem eigenen Versuch öffnen
└─ checkliste.md    „Das kann ich jetzt" + was wir als Nächstes bauen
```

Die Beispiele sind eigenständig ausführbar. Verändere sie ruhig — dafür sind sie da.

---

## Die Lektionen

### Stufe 1 — Flet verstehen

| | Lektion | danach bauen wir |
|---|---|---|
| **L01** | [Werkzeuge und Projektaufbau](L01_werkzeuge/) | — |
| **L02** | [Das Flet-Modell](L02_flet_modell/) | M1 |
| **L02b** | [Rauchtest: aufs Handy bauen](L02b_aufs_handy/) | — |
| **L03** | [Navigation und Zustand](L03_navigation/) | M1 |
| **L04** | [Datenmodell und SQLite](L04_daten_und_sqlite/) | M2 |

### Stufe 2 — Die App füllt sich

| | Lektion | danach |
|---|---|---|
| L05 | Übungskatalog: Seed-Daten, Suche, Filter, Medien | M2 |
| L06 | Flexible Notation: Formulare aus einer Spezifikation | M3 |
| L07 | async in Flet: Timer, Aufgaben, sauberes Abbrechen | M3 |

### Stufe 3 — HRV

| | Lektion | danach |
|---|---|---|
| L08 | RR-Intervalle, die zwei Uhren, Lücken, Zeitbereich | M4 |
| L09 | Welch und Lomb-Scargle in numpy, DFA, SampEn | M4 |
| L10 | BLE, Geräte, der Sensor-Prüfstand | M5 |
| L11 | Live-Messung, Diagramme, Limit-Regeln | M6/M7 |

### Stufe 4 — Ausliefern

| | Lektion | danach |
|---|---|---|
| L12 | Auswertung, Export, Round-Trip, Packaging | M8 |

### Ausblick

- **A** — Eigene Flet-Extension: BLE und Foreground Service auf Android/iOS
- **B** — Edition B: Synchronisation, Anmeldung, Verschlüsselung, DSGVO

Diese beiden entstehen, wenn wir dort ankommen. Vorher wüssten wir noch nicht
genau genug, wogegen sie geschrieben werden.

### Zusatz — Grundlagen zum Nachlesen

Kein Teil des Lernpfads, sondern Hintergrund, wenn ein Begriff unklar ist.

- [Generator, Coroutine, Task](Z_grundlagen/asyncio.md) — was `async`/`await`
  eigentlich tut; hilfreich vor L07 und L10.

---

## Warum die Reihenfolge so ist

**Packaging ganz nach vorn (L02b).** Nach der zweiten Lektion bauen wir die App
einmal aufs Handy. Nicht weil sie dann etwas kann, sondern weil ein erst spät
entdecktes Build-Problem Monate entwerten würde. Dabei prüfen wir auch gleich,
ob man von Python aus überhaupt an einen BLE-Sensor kommt — davon hängt die
gesamte Mobilstrategie ab.

**Tests ab L04.** HRV-Tests werden in L08 gebraucht, nicht am Ende.

**BLE relativ früh (L10).** In `praxis_gui` existiert funktionierender Code —
das ist eher Lesen und Übertragen als Neuentwicklung. Eine vergleichsweise
leichte Lektion mit einem sehr sichtbaren Ergebnis.

---

## Wenn etwas nicht funktioniert

1. `uv sync` erneut ausführen — das bringt die Umgebung wieder auf den Stand
   von `uv.lock`.
2. Lief der Befehl mit `uv run` davor? Ohne läuft er in der falschen Umgebung.
3. `uv run pytest` — sind alle Tests grün? Wenn nein, liegt es meist dort.
4. In der Lektion nachsehen: unter „Stolperfallen" steht, was üblicherweise schiefgeht.
5. Für Icon-Namen, Flet-Docs und andere externe Quellen:
   [`docs/nachschlagen.md`](../nachschlagen.md).
