# Übungen einstellen – zwei Orte, ein Weg (P79)

Ben, 22.10.2026: Übungen ließen sich über viele Menüs mit verschiedenen Befugnissen einstellen —
„ein user, der/die die Übung einstellen soll, tut sich damit sicherlich schwer“. Skizzen:
https://claude.ai/artifact/SLbHne6zrpNDYosNKy9fnm (Reihen A–D, Konfliktliste E1). Ben dazu:
„Du kannst das alles übernehmen, außer C2, D4, D5“ (unten eingearbeitet).

## Grundsatz

- **Zwei Orte zum Einstellen.**
  - **Übung bearbeiten** (`/uebung/<id>/bearbeiten`) beschreibt, was die Übung ist, und gilt
    überall. Man erreicht es nur über die Übungsseite → Stift („Übungen → Übung → Bearbeiten“
    bleibt).
  - **Im Plan einstellen** (`<bearbeiten>/ziel/<item>`) legt fest, wie die Übung in diesem einen
    Plan läuft.
- **Ein Weg zur Info.** Das **i** führt überall zur selben **Übungsseite**: aus dem Plan (üben
  und bearbeiten), vom Leistungen-Blatt, aus Verlauf, Tagebuch und Eintrag, aus Paket, Archiv
  und Papierkorb. Die Übungsseite ändert nichts. Kommt man aus einem Plan, steht oben die Karte
  „In diesem Plan“ mit „Im Plan einstellen“. Bis zu Name und Beschreibung sind es so von überall
  zwei Schritte (i → Stift), nie einer.
- **Beim Üben gilt eine Wahl nur für jetzt:** Uhr an/aus, „zählt“, Timerprofil, Timerzeit und
  die Variante des Eintrags. Dauerhaft wird es nur an den zwei Orten (wie P52).
- **Gleich bedient, gleich gespeichert.**
  - Beide Einstellseiten haben Abbrechen und Speichern oben; Zurück speichert.
  - Chips tippt man an (keine Kommaliste).
  - Die i-Seite mit sofort speichernden Knöpfen entfällt.
- **Vererbung sichtbar:** Eine Planübung folgt der Übung, bis man im Plan etwas ändert. Jede
  Einstellung zeigt „wie die Übung“ oder „nur hier“ mit ↺. Unten stehen zwei Knöpfe: „Alles wie
  die Übung“ und „In die Übung übernehmen …“. Übernehmen zeigt vorher, welche Pläne die Änderung
  mitbekommen.

## Entscheidungen (22.10.2026)

| Punkt | Entscheidung |
|---|---|
| A | Parameter holen beim Üben über i → Übungsseite → „Im Plan einstellen“ (statt sofort auf der i-Seite, Setzung 14.10.) |
| A2 | „Neue Variante“ bleibt im Etikett-Blatt beim Üben, mit dem Satz „gilt in allen Plänen“; der versteckte Weg ins Formular wird ein Link zur Übungsseite |
| B1 | Planübungen folgen der Übung ganz, auch Ziel und Parameter (bisher beim Aufnehmen kopiert). Bestehende: gleich → folgt, abweichend → „nur hier“ |
| B2 | Uhr und Timer der Planübung zählen als Abweichung; ↺ setzt sie zurück |
| C | „Variante“ heißt nur das Etikett (Knie, gestreckt). Die Kopie heißt „Kopie anlegen“ bzw. „(Kopie)“, die gemeinsame Kachel „Im Verlauf zusammen mit …“ (P61) — **die gemeinsame Kachel ist seit 26.10.2026 ausgebaut**, jede Kopie hat ihre eigene |
| **C2** (Ben) | Kein „in Plänen anbieten“: **Was die Übung hat, bieten alle Pläne an**; weniger stellt man in der Planübung ein. `default_felder` entfällt |
| D1 | Ein Timer- oder Stoppuhrlauf ist ein **Satz im offenen Eintrag**, wie ein Tipp (ändert P51). Ein neuer Eintrag beginnt nur bei anderer Ausführung, nach „Abschließen“, nach `offen_min` ohne Eintrag, in einem anderen Plan oder an einem anderen Tag |
| D2 | „Timerzeit zählt“ und „zählt als“ stellt man in der Übung ein; beim Üben in der Leiste für jetzt („zählt“); die Einstellung dafür im Plan entfällt |
| D3 | Die beim Üben gestellte Zeit gilt für jetzt |
| **D4** (Ben) | Zeit antippen → **Räder für Minuten und Sekunden** wie ein Zahlenschloss (`CupertinoTimerPicker`, Modus Minuten/Sekunden), dazu ein Tippfeld „m:ss“ |
| **D5** (Ben) | **Kein Unterschied** zwischen Timerzeit und getippter Zeit im Verlauf: Timer zählt als getippt |

## Datenmodell

- `plan_item.target_json` = `null` (JSON) heißt **wie die Übung** (`PlanItem.target is None`).
  Wirksam ist dann `Exercise.default_target` (`core.standards.ziel_von`).
- `plan_item.fields_json` = NULL heißt **alle Parameter der Übung** (C2; bisher deren
  `default_felder`).
- `PlanItem.quick` (fehlender Schlüssel = Chips der Übung) und der Variantenschalter folgen der
  Übung schon heute.
- `exercise.default_fields_json` wird nicht mehr gelesen und bleibt NULL. Das Paketfeld
  `default_felder` wird beim Import überlesen (kein Paket nutzt es) und nicht mehr exportiert.
- `exercise.clock_counts` (neu, 1 = Vorgabe): Timerzeit zählt. „Zählt als“ steht weiter in
  `clock_counts_as`.
- `TimerWahl` der Planübung: Profil und Uhr bleiben; `zeitfeld` und `zeit_eintragen` entfallen
  (D2). Alte Werte werden überlesen.
- **Migration 028** (reines SQL, ohne JSON-Funktionen):
  - Planübungen ohne eigene Parameter bekommen die alte Planvorgabe der Übung als eigene, damit
    sich nichts ändert.
  - Danach wird `default_fields_json` geleert.
  - Ein Ziel, das wörtlich gleich dem der Übung ist, wird zu `null`.
  - Dazu kommt die Spalte `clock_counts`.
- **Beschleunigungssensor und Takt** (A6, 5.11.2026; `docs/plan_beschleunigung.md` §13,
  `docs/plan_taktgeber.md` §11): `PlanItem.acc: SensorWahl | None` und `PlanItem.takt: Takt |
  None` — ``None`` = wie die Übung. **Migration 039** `plan_item.acc_json TEXT` /
  `plan_item.takt_json TEXT`, NULL = wie die Übung (eigene Spalten wie `timer_json`, nicht im
  Timer-JSON: die Karte und der Takt sind keine Timer-Wahl, und „wie die Übung“ braucht ein
  eigenes NULL); `takt_json = '{}'` = ausdrücklich kein Takt. Aufgelöst wird an einer Stelle im
  Kern: `core.zaehlen.wirksame_wahl(uebung, item)` (Planübung > Übung) und
  `core.uebung_timer.takt_der_uebung(uebung, item)`; beim Takt gilt Uhr für jetzt >
  Timer-Abschnitt > Planübung > Übung (`takt_fuer`). `core.standards`: `sensor_von`/`takt_von`,
  `sensor_eigen`/`takt_eigen` (am Wert gemessen), `abweichungen` nennt „Beschleunigungssensor“
  und „Takt“, `bereinigt`, `vom_standard`, `als_standard` und `uebernehmen_vorschau` nehmen
  beide mit. Im Paket je Planübung `beschleunigung`/`takt` (`docs/uebungspakete.md`).

## Schritte

1. **Wege** (ohne Verhaltensänderung)
   - i → Übungsseite überall, mit Karte „In diesem Plan“.
   - i im Leistungen-Blatt, in der Verlauf-Kurve und am Eintrag.
   - Zeilen in Paket, Archiv und Papierkorb öffnen die Übung, Archiviertes mit
     „Wiederherstellen“.
   - „In Plänen“ öffnet „Im Plan einstellen“; dazu „In einen Plan aufnehmen“ (P43 c) und „Neue
     Übung anlegen“ unter „Übung hinzufügen“.
   - Die Hinweise auf Typen und Regionen, die Darstellung der Uhr und den Papierkorb werden Links.
   - Das Etikett-Blatt bekommt den Link zur Übungsseite.
   - Die Übungsseite: Timer, Stift, Menü ⋮ (Kopie anlegen, Archivieren oder löschen).
2. **Im Plan einstellen**
   - Die Planübung folgt der Übung (Migration 028).
   - Je Einstellung „wie die Übung“ oder „nur hier“ ↺; Uhr und Timer zählen als Abweichung.
   - Unten „Alles wie die Übung“ und „In die Übung übernehmen …“ mit Vorschau.
   - Im Plan-Editor keine Uhr am Block; die Zeile zeigt, was nur hier gilt.
   - „Zählt als“ verschwindet aus dem Plan.
3. **Übung bearbeiten aufräumen**
   - Reihenfolge von häufig nach selten.
   - Eine Zeile je Parameter (Schalter, Chips zum Antippen).
   - Unter „Vorgabe für Pläne“ steht nur das Ziel.
   - Unter „Uhr und Timer“: „Timerzeit zählt“ mit „als Haltezeit/Zeit“.
   - Zuletzt „Ordnen“; die Begriffe nach C.
4. **Timer**
   - Ein Lauf sammelt im offenen Eintrag.
   - In der Leiste ein Knopf „zählt“ (für jetzt).
   - Der Timer zeigt, wofür er zählt.
   - Zeit antippen → Räder plus Tippfeld (Leiste, Timer der Übung, Reiter Timer).
   - Der Verlauf rechnet Timerzeit wie getippte; dabei werden die Befunde aus dem Überblick
     behoben (▶ ohne Plan, veralteter Hinweis, Kurve).

**Nachtrag 5.11.2026 (A6):** „Im Plan einstellen“ hat in „Uhr und Timer“ die Zeile „Takt: …“
(Stift → Takt-Blatt „In diesen Plan“, ✕ = ausdrücklich keiner, Schild mit ↺) und danach die
Karte „Beschleunigungssensor“ wie in „Übung bearbeiten“ (Wiederholungen, Bewegung, Zählt in,
Atmung; Schild mit ↺, Rahmen bei „nur hier“). Der Knopf „Wdh. zählen“ in einer Planübung nur,
wenn sie ein Wiederholungsfeld anbietet. Beim Üben aus dem Plan gilt die Wahl der Planübung,
„für jetzt“ bleibt obenauf; „Alles wie die Übung“ und „In die Übung übernehmen …“ kennen beides.

**Nachtrag 2.11.2026:** „Übung bearbeiten“ ist aufgeräumt — Symbol oder Bild oben, Beschreibung als Editor, Parameter als Knöpfe mit einer Karte je Parameter (Name, Chips, Sätze, Ziel), Erklärtexte im (i). Vertrag: `docs/plan_uebung_bearbeiten.md`.
