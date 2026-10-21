# Plan: Offener Eintrag, Leistungen in der HRV-Kurve, Übungsausschnitte

Stand 19.10.2026: **alle Teile gebaut** — A und B in v0.3.6, C–F danach auf main (Gerätetest T60). Ben hat die vier
offenen Punkte am 19.10. bejaht
(Katalog „Entschieden“); Skizzen: https://claude.ai/artifact/HRPrwTvS5M2bEW4qJrgmAX
(Reihe A = Teil A, Reihe D = Teile B–D, Reihe F = Teile E–F). Anlass: Bens
Notizen „Übungsausführung – Einträge“ (Katalog P41) und seine Ergänzung vom selben Tag:

> Langfristig möchte ich eruieren können, wie Belastung auf das Stresslevel im Körper
> wirkt. Dabei ist es hilfreich, wenn man weiß, was man wann belastet hat. … 50
> Liegestützen → commit → Pause, gucken, wie die Kurve reagiert → 50 Liegestützen →
> Klick → Kurve beobachten.

Sechs Teile, in dieser Reihenfolge zu bauen; jeder für sich lauffähig:

| Teil | Was | Schicht |
|---|---|---|
| A | Offener Eintrag in der Übungsausführung | `data/repositories`, `ui/views/plan.py`, Leistungen-Blatt |
| B | Jede Leistung als Marke in Zeitleiste und laufender Aufnahme | `core/einheit`, `ui/plan_ablauf`-Nachbar, hrv-core (`MARKE_FELDER`) |
| C | Eintrag ↔ HRV-Aufnahme finden, nachträglich ansehen | `data/einheiten`, Leistungen-Blatt, Übung, Messung |
| D | Kurve: Notizen gelb, Leistungen in sanftem Blau, einblendbar | `ui/components/notizen`, `messung_detail`, Vollbild |
| E | In den Ausschnitt einer Übung zoomen statt stückeln | `messung_detail` (Zeitfenster, Analysefenster) |
| F | Breitenknöpfe 1 · 2 · 5 · 10 Min, Abschnitte einblenden, eigene x-Achse | `messung_detail`, `zeitfenster`, Vollbild |

Voraussetzung: Befunde **D3** (eingefrorenes „heute“) und **D7** (Mehrfachstelle) aus
Katalog §7 — Teil A ersetzt die Stellenlogik und beseitigt D7 dabei; D3 kommt vorweg.

---

## A. Offener Eintrag

**Heute** gibt es keinen Begriff „aktiver Eintrag“, nur vier Zielregeln nebeneinander:
ein Mengen-Chip hängt an den *jüngsten* Eintrag der Übung von heute in diesem Plan an
(`satz_anhaengen`; weicht die Ausprägung ab, still ein neuer); „Gemacht“ legt immer einen
leeren neuen an; die Notiz geht in den *frühesten* Eintrag mit Text (`notiz_eintrag`);
Skala und Freitext in den jüngsten bzw. dorthin, wo der Text schon steht. Zeitabstand
spielt keine Rolle. „Heute geleistet“ zeigt Bündel je Ausprägung, keine Einträge — man
sieht nie, wohin der nächste Tipp geht.

**Regel in einem Satz:** Ein Tipp geht in den markierten (offenen) Eintrag; ist keiner
markiert, entsteht ein neuer.

### A1. Was „offen“ heißt

- Ein Eintrag ist offen, solange `ended_at` leer ist. Chip-Einträge haben heute nie ein
  Ende, Timer-Einträge immer — das passt: Was der Timer schrieb, ist fertig.
- **Schließen** = Korrektur mit `ended_at = jetzt` (unveränderlicher Eintrag, wie jedes
  „+Satz“ eine Korrekturzeile ist). **Wieder öffnen** = Korrektur mit `ended_at = NULL`.
- Je Übung, Tag und Plan höchstens **ein** offener Eintrag. Öffnet ein neuer, schließt
  die Datenschicht den alten mit (`eintrag_oeffnen` schließt vorher).

### A2. Wann ein neuer Eintrag entsteht (Schließgründe)

| Grund | Wer | Wirkung |
|---|---|---|
| **„Gemacht“** | die Person | schließt den offenen Eintrag (= Abschicken, Fixieren). Ohne offenen: leerer Eintrag, gleich geschlossen (wie heute „abgehakt“). |
| **Ausprägung geändert** (20 kg → 30 kg, rechts → links, kurz → lang) | die Person | die Markierung verschwindet, Hinweis „Der nächste Wert beginnt einen neuen Eintrag“; der nächste Mengen-Tipp öffnet einen neuen — **der alte bleibt offen** (seit 21.10.2026, P57: je Ausführung ein offener Eintrag, `docs/plan_varianten.md` Teil C). Zurück zur alten Ausprägung → ihr Eintrag ist wieder markiert, der nächste Wert geht dorthin. |
| **Zeitabstand** | die App | Liegt der letzte Satz länger als `EINTRAG_OFFEN_MIN` zurück (Vorgabe **30 min**, Einstellungen → Übungen), gilt der Eintrag als geschlossen; die Datenschicht schließt ihn beim nächsten Tipp nach. |
| **Übung endet im Ablauf / Timer fertig** | Ablauf | wie heute: `ended_at` aus der Zeitleiste. |
| **Tageswechsel** | die App | ein offener Eintrag von gestern ist zu (D3 vorausgesetzt). |
| **Spätere Stelle einer Mehrfachübung** | Plan | ersetzt `eigener_eintrag`/`stelle`: die zweite Stelle öffnet immer einen neuen Eintrag. Damit entfällt D7. |

### A3. Wohin was geht

- **Menge** (Chip, Sätze × Wert, Summe): in den offenen Eintrag; keiner → neuer.
- **Skala, Ja/Nein** (Beiwerk): in den offenen Eintrag; keiner → neuer (wie heute `wert_setzen`).
- **Notiz und Freitext**: in den offenen Eintrag — nicht mehr in den frühesten mit Text.
  Ältere Notizen bleiben im Leistungen-Blatt änderbar. Ist keiner offen, öffnet die
  Notiz einen neuen (heute: leerer „gemacht“-Eintrag; A2 im Katalog, „abgehakt als
  eigener Speicherwert“, bleibt davon unberührt).
- **Ausprägungs-Chips** zeigen den Zustand des offenen Eintrags (Vorbelegung aus ihm,
  nicht aus `state.auspraegung_wahl` allein).

### A4. Anzeige im Übungsblock

- „Heute geleistet“ zeigt **Einträge statt Bündel**, jeder als Zeile: Uhrzeit (von–bis),
  Ausprägung, Mengen in Notation („20 kg · links · 2×15“), Notiz kursiv.
- Der **offene** Eintrag: Rand und Kopf in Primärfarbe, Zeile „offen seit 10:07“, darunter
  die Chips. Geschlossene: grau, ohne Rand.
- Würde der nächste Tipp einen neuen Eintrag anlegen (Ausprägung geändert, Zeitabstand
  überschritten, keiner offen): **nichts markiert**; unter den Chips nur eine Zeile
  „Beginnt einen neuen Eintrag (15 kg · links)“. Die Erklärung dazu (warum, was „Gemacht“
  tut, Zeitabstand) hängt als **„i“ im Kopf von „Heute geleistet“** — ein Tipp öffnet sie
  (Ben, 19.10.2026: „sonst nimmt das zu viel Platz ein“; wie die „i“ in der Messansicht).
- Tipp auf einen geschlossenen Eintrag → Blatt mit „Wieder öffnen“, „Bearbeiten“
  (Leistungen-Blatt), „Löschen“.
- „Gemacht“ bekommt den Text **„Abschließen“** mit Haken, solange ein Eintrag *markiert*
  ist. Ist keiner markiert (keiner offen, Ausprägung geändert, Zeitabstand überschritten),
  heißt er „Gemacht“: er legt einen leeren, gleich geschlossenen Eintrag mit der gewählten
  Ausprägung an und schließt einen noch offenen **derselben Ausführung** dabei mit (Skizze
  A2/A3; seit 21.10.2026 bleiben offene Einträge anderer Ausführung offen, P57).

### A5. Datenschicht

- `SessionRepo.offener_eintrag(subject, exercise, tag, plan_id, hoechstalter)`,
  `eintrag_schliessen(id)`, `eintrag_oeffnen(id)`; `satz_anhaengen`/`wert_setzen`/
  `text_setzen`/Notiz bekommen den Zieleintrag vom Aufrufer (`ziel: SessionEntry | None`)
  statt `neu: bool` + Kontextvergleich — die Regel lebt an **einer** Stelle
  (`core/eintraege.py`: `ziel_fuer(offener, kontext, jetzt, hoechstalter) → offener | None`,
  reiner Kern mit Doctests).
- Keine Migration: `ended_at` gibt es; `EINTRAG_OFFEN_MIN` in `app_setting`.
- Tests: Zielregel (Ausprägung, Zeitabstand, Tageswechsel, Mehrfachstelle), Schließen und
  Wiederöffnen als Korrekturen, Notiz in den offenen.

---

## B. Leistungen als Marken („Commit“)

**Ziel:** Jeder Tipp, der eine Leistung eintragt, hinterlässt einen Zeitpunkt in der
laufenden HRV-Aufnahme — maschinenlesbar, nicht als Flut gelber Notizen.

**Heute:** Chip-Tipps schreiben nur in die Datenbank. Nur Timer und Plan-Ablauf schreiben
`person/eintrag` in die Zeitleiste und Marken in die Datei. Eine laufende Aufnahme ist
seit 18.10. immer eine Einheit (`einzeln_starten`) — die Zeitleiste ist da.

### B1. Was ein Commit ist

- Ein Commit = **ein Tipp, der eine Menge einträgt** (Chip, Sätze × Wert, Summe, Einzelwert)
  und **Abschließen/Gemacht**. Nicht: Ausprägung wählen, Skala, Notiz (die ist selbst eine
  Notiz).
- Die Zeit ist die **Tippzeit** — Pi mal Daumen das Ende des Satzes. Das steht so in der
  Marke (`art: leistung` = „geleistet bis hierher“), nie als Beginn gedeutet.
  Den genauen Beginn liefert nur die Uhr der Übung (Stoppuhr/Timer, T51), die es schon gibt;
  mit ihr gibt es „Planke: Start“/„Planke: Ende“ wie bisher, die Commits liegen dazwischen.
- Nachträglich verschiebbar wie jede Notiz (±1/±5 s, „In Kurve“) — die Marke bleibt.

### B2. Was geschrieben wird

Zeitleiste (immer, auch ohne Aufnahme — sie ist die Provenienz):

```
person/leistung   text="Liegestütze: 50"   daten={eintrag, uebung, feld, wert, auspraegung}
person/abschluss  text="Liegestütze: fertig"   daten={eintrag, uebung}
```

Läuft eine Aufnahme in derselben Einheit, projiziert `core.einheit.projektion` daraus eine
Notiz mit Marke (Vertrag §4, Erweiterung):

```json
{ "text": "Liegestütze: 50", "uebungen": ["2ATPZCAY"],
  "marke": { "quelle": "person", "art": "leistung", "einheit": "…",
             "name": "Liegestütze", "feld": "reps", "wert": 50 } }
```

- Neue Werte in `MARKE_FELDER` (hrv-core): `quelle: person`, `art: leistung | abschluss`,
  Felder `feld` (Text) und `wert` (Zahl). Ausprägungen kommen als `name`-Zusatz in den Text
  („Kniebeuge 20 kg: 10“), nicht als eigene Felder — die Liste bleibt flach und klein.
  Zuerst der Eintrag in `docs/kompatibilitaet.md` §4, dann hrv-core (`marke_bereinigen`,
  `docs/ereignisse`), dann die App.
- **Spur `uebung` ohne Uhr:** Erster Commit eines offenen Eintrags → Abschnittsanfang
  „Liegestütze“ auf der Spur `uebung`, Abschließen → Ende. Läuft die Uhr der Übung, kommt
  kein zweiter Abschnitt (die Uhr klammert schon). Damit ist jeder Eintrag in der
  Aufnahme ein Abschnitt — Grundlage für E.
- Commits sind **Notizen mit Marke** in der Datei — praxis_gui zeigt sie als normale
  Notizen (es liest `marke` nicht). Das ist gewollt: Die Datei ist die Wahrheit, die
  Auswertung in hrv-research braucht sie dort. Wie viele es werden, löst D (eigene Ebene,
  ausblendbar), nicht das Weglassen.

### B3. Live

- Der Tipp im Plan erscheint sofort in der Live-Kurve (bestehender Weg der Timer-Notizen,
  `timer_notiz_beobachter`).
- Im Übungsblock neben „offen seit 10:07“ ein kleines Herz, wenn eine Aufnahme läuft:
  „Marken gehen in die Aufnahme“. Ein Tipp darauf öffnet die Messansicht mit 2-min-Fenster
  am Ende — „Kurve beobachten“ ohne Suchen.

### B4. Was mir dazu noch einfällt

- **Werte in der Marke** erlauben später „Erholung nach 50 Wdh gegen 30 Wdh“ — ohne
  Zeitzuordnung über Tabellen. Eine Kennzahl „RMSSD zur Marke, +60 s, +120 s“ wäre
  beschreibend (wie die DFA-Übersicht, keine Empfehlung); gehört in hrv-core und ist ein
  eigener Schritt (Katalog, nicht hier).
- **Pause ist ein Abschnitt:** Zwischen Abschluss und nächstem Commit entsteht auf der
  Spur `uebung` nichts — die Lücke *ist* die Pause. Werte je Abschnitt (gibt es) zeigen
  Belastung gegen Lücke, sobald man „Lücken als Pause“ wählt (F).
- **Nachgetragene Einträge** (Nachtragen-Seite) bekommen **keine** Marke — ihre Zeit ist
  geschätzt. Ebenso Korrekturen im Leistungen-Blatt.
- **Zu viele Marken?** Eine Einheit mit 30 Commits hat 30 blaue Striche — in D eine Ebene,
  die man ausblendet; in der Notizliste standardmäßig zugeklappt unter „Leistungen · 30“.
- **Doppeltipp** (zweimal „+15“ in 3 s): zwei Marken, zwei Sätze — richtig so; die
  5-s-Regel gilt für Abschnitte, nicht für Notizen.

---

## C. Eintrag ↔ HRV-Aufnahme

**Keine neue Tabelle.** Der Weg existiert für Timer-Einträge schon
(`eintraege_vom_timer`): `person/*`-Ereignis → Einheit → `einheit_baustein` art `hrv` →
`datei` → `hrv_recording.file_path`. Mit B schreibt jeder Commit ein solches Ereignis.

- `EinheitRepo.aufnahme_zu_eintrag(eintrag_id) → (recording, von_s, bis_s) | None`:
  die Aufnahme der Einheit und der Zeitraum des Eintrags auf ihrer Achse (erste Marke bzw.
  Übungsstart bis Abschluss/letzte Marke).
- `EinheitRepo.eintraege_zur_aufnahme(recording_id) → [(eintrag_id, von_s, bis_s)]`.
- **Rückfall über die Zeit** für Einträge ohne Ereignis (vor diesem Stand, Nachträge):
  `started_at` liegt in der Aufnahme → gezeigt mit dem Zusatz „zeitlich“, nie als Marke
  in die Datei geschrieben.

Wo es sichtbar wird:

| Ort | Was |
|---|---|
| Leistungen-Blatt, je Karte | Zeile „♥ Aufnahme 10:02–10:40 · ansehen“ → Messung, gezoomt auf den Eintrag (E) |
| Übungsdetail | Abschnitt „Aufnahmen mit dieser Übung“: Datum, Dauer, Einträge — Liste, keine Kurve (P39: HRV bleibt aus dem Verlauf) |
| Messung (Aufzeichnung) | neues Klappfeld **„Übungen · 4“** unter „Notizen“: je Eintrag Name, Werte, von–bis; Tipp → zoomt auf den Ausschnitt (E) und setzt das Analysefenster darauf |
| Tagebuch | am Tag das Herz-Symbol, wenn Einträge eine Aufnahme haben |

---

## D. Darstellung in der Kurve

- **Notizen** bleiben, wie sie sind (gelb, `FARBEN["notiz"]`), als Überschriften mit Etikett.
- **Leistungen** (Marken `person/leistung|abschluss`): eigene Ebene in sanftem Blau
  (`FARBEN["leistung"]`, hell `LIGHT_BLUE_300`, dunkel gedämpft), kurze Striche am unteren
  Rand mit dem Wert als Etikett („50“), Abschluss als kleiner Haken. Antippen zeigt wie
  bei Notizen Zeit, Text und Werte.
- **Abschnitte** als Balken wie heute (Spuren übereinander).
- **Einblenden:** über der Kurve eine Chip-Zeile „Notizen · Leistungen · Abschnitte“
  (Filter-Chips, je an/aus), gemerkt in der Ansichtseinstellung; Vorgabe alle an. Im
  Vollbild dieselbe Zeile in der Werkzeugleiste.
- Notizliste: Leistungen stehen nicht zwischen den Notizen, sondern als eigenes
  Klappfeld „Übungen“ (C).

---

## E. In den Ausschnitt der Übung zoomen

Kein Stückeln: Die Aufnahme bleibt eine Datei, die Übung ist ein Abschnitt (B2, Spur
`uebung`).

- `zoom_auf(von_s, bis_s)`: Fensterbreite = Dauer + 2 × 30 s Rand, Mitte auf den
  Abschnitt; die Breitenknöpfe zeigen dann keine Wahl (gibt es: „Ein Abschnitt kann jede
  Breite haben“). Analysefenster `AW_ABSCHNITT` auf den Abschnitt → Spektrum, Poincaré,
  Werte je Abschnitt zeigen die Übung.
- Erreichbar aus C (Leistungen-Blatt, Klappfeld „Übungen“) und aus F (Abschnitt-Chip).
- Länger als 10 min → F übernimmt (Fenster 10 Min, Achse an den Abschnitt gebunden).

---

## F. Breitenknöpfe, Abschnitte, eigene x-Achse

### F1. Knöpfe

- `BREITEN = 1 Min · 2 Min · 5 Min · 10 Min` — „Min“ hinten dran, die Knöpfe
  **gestreckt über die volle Breite** (`expand`), im Vollbild dieselben in kompakter Form.
- **„Alles“** verschwindet aus der Reihe (Ben nennt vier Knöpfe). Die ganze Messung
  erreicht man über den Abschnitt-Chip „Ganze Messung“ (F2) — *Annahme, bitte bestätigen.*
- Die Startbreite bleibt 2 Min; Live-Einstellung (`Zeitfenster live`) bekommt 10 Min dazu.

### F2. Abschnitte einblenden

- Unter den Breitenknöpfen eine **waagrecht scrollende Chip-Zeile**: „Ganze Messung“,
  dann je Abschnitt ein Chip in seiner Farbe („Liegestütze 10:07“, „Belastung 2/8“,
  „km 3“) — Übungen sind Abschnitte (B2), keine Sonderform. Zusammenklappbar
  („Abschnitte ▾“), gemerkt.
- Tipp auf einen Chip = **eigene x-Achse**: Das Fenster ist an den Abschnitt gebunden
  (`Fenster.anfang`/`ende` gibt es schon als Grenzen): nicht breiter als der Abschnitt
  + Rand, Wischen bleibt darin; die Achse zählt **ab Abschnittsbeginn** (0:00, 1:00 …),
  der Kopf nennt den Abschnitt und die Uhrzeit. Ist er länger als die gewählte Breite,
  wischt man **minutenweise** darin (Pfeile ‹ › neben dem Chip springen um eine
  Fensterbreite — wie die Pfeile im Vollbild). So bleibt die Ansicht bei einer
  70-min-Messung mit 20 Abschnitten übersichtlich: ein Abschnitt, ein Fenster.
- „Ganze Messung“ löst die Bindung (heutiges Verhalten, Achse ab Messbeginn).
- Analysefenster folgt dem gebundenen Abschnitt (`AW_ABSCHNITT`), solange man nicht
  „Fenster“ wählt.

### F3. Was sich nicht ändert

- Wischen, Drossel, Rastpunkte, Bereichseditor (`zeitfenster.py`, `bereich.py`).
- Sidecar-Format (9b): die Bindung ist Ansicht, nichts wird gespeichert.

---

## Reihenfolge und Umfang

1. D3 beheben (klein) → A (Datenschicht + Kern mit Tests, dann Block und Blatt).
2. Vertrag §4 + hrv-core (`MARKE_FELDER`, Doku, Golden-Test unberührt) → B.
3. C (Repo-Abfragen, drei Oberflächen) → D (Ebene, Chips) → E → F.
4. Skizzen vor A4, D und F (Bildergeschichte, wie bei P41), wenn Ben sie sehen will.
5. Am Handy: T-Einträge im Katalog je Teil (Commit im laufenden Gurt, Zoom, Chips).

Die Entscheidungen stehen im Katalog unter „Entschieden“ (19.10.2026).
