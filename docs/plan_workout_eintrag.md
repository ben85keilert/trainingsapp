# Workout-Eintrag

Stand: 10.11.2026 abends — Stufen 1 bis 3 gebaut (Migrationen 053, 054); offen nur die
Lastrechnung (P179, zurückgestellt). Skizzen E1–E4:
https://claude.ai/artifact/PpEBhBSSWcAWDY7kTqDEgd

Ben, 10.11.2026: „Die Anstrengung sRPE müsste in Bezug auf das Workout notiert werden, d. h. ein
Feld für das Workout. … Vielleicht kann man ein gemachtes Workout in die Tagesliste mit aufnehmen
und den Wert dort abspeichern. … Eine Zusammenfassung des Workouts erscheint mir plausibel. Das
darf in der Ansicht aber nicht überladen sein, die Übungen werden eh separat gelistet. Am besten
einsehbar, wenn man den Workouteintrag direkt klickt.“

## 1. Grundregel

**Werte gehören der Übung, der Verlauf gehört dem Workout.**

- Was in einem Schritt geleistet wurde, steht im Tagebucheintrag der Übung (`session_entry`) —
  jeder Satz, Korrigieren, Kurve im Verlauf. Ob einzeln oder im Workout geübt, macht dort keinen
  Unterschied; der Eintrag nennt nur seine Herkunft („im Workout Beine · Schritt 1“).
- Das Workout zeigt seine Übungen nur als Liste mit Kurzwert. Es fügt hinzu, was eine Übung nicht
  wissen kann: gegangene Reihenfolge, Zeit je Schritt, Übersprungenes, Fragen mit Antwort, ob es
  vorzeitig endete — und Werte zum Ganzen.

## 2. Was ein Workout-Eintrag ist

Ein **Durchlauf**: eine beendete Einheit (Migration 018), deren Zeitleiste mit `plan/start`
(`workout`) beginnt und aus der mindestens eine Übung ins Tagebuch kam. Gelesen wird er aus der
Zeitleiste (`core/workout_eintrag.durchlauf`), gespeichert wird dafür nichts Neues.

- Gleich wieder abgebrochen (nichts eingetragen): kein Eintrag.
- Vorzeitig beendet und fortgesetzt: zwei Einträge, der zweite trägt „fortgesetzt“
  (`fortsetzungen_markieren`).
- Ein Workout-Plan, der von Hand als Liste geübt wird: kein Workout-Eintrag, der Planblock bleibt
  wie bisher.
- „6 von 7 Schritten“ gibt es bewusst nicht — in einem Ablauf mit Abzweigen muss nicht jede Übung
  drankommen. Gezählt werden die eingetragenen Übungen.

## 3. Werte zum Workout

Tabelle `workout_entry` (Migration 053), gebaut wie `session_entry`: Ergebnis, Kopie der Felder,
Notiz; unveränderlich — eine Änderung ist eine neue Zeile mit `replaces_id`, es gilt die jüngste
(`EinheitRepo.workout_eintragen`, `workout_wert`, `workout_werte`).

- Erstes Feld: **Anstrengung (sRPE)**, 0–10 (`core.workout_eintrag.spec`, Schlüssel `srpe`).
- **Eigene Skalen je Workout** (Migration 054, `plan.workout_felder_json`): bis zu vier frei
  benannte Skalen 0–10 („Schmerz danach“), gesetzt auf der Seite über „Felder …“
  (`PlanRepo.workout_felder`/`workout_felder_setzen`) — sie gelten für alle Durchläufe dieses
  Workouts. Schlüssel `skala:<Name>` (`feld_key`). Gerätelokal wie `freischaltung_seit`: kein
  Paketfeld, `PlanRepo.speichern` fasst die Spalte nicht an. Wird eine Skala entfernt, bleibt ein
  eingetragener Wert mit seinem Namen stehen (die Kopie der Felder am Eintrag).
- Ein Tipp auf den gewählten Wert nimmt ihn zurück.
- Eintragen in „Workout fertig“ und jederzeit im Workout-Eintrag (auch an vergangenen Tagen).
- **Das Tagesfeld „Anstrengung (sRPE)“ bleibt, wie es ist** (einmal am Tag, für den Tag als
  Ganzes). Das Workout schreibt nicht mehr hinein — mehrere Workouts füllen weder „Zum Tag“ noch
  die Tagesfelder. Die sRPE-Last im HF-Verlauf rechnet weiter nur mit dem Tagesfeld; die
  Lastrechnung ist zurückgestellt (Ben, 10.11.2026: „noch zu vage“), offen P179.
- Keine Deutung, keine Vorgabe, keine Erinnerung (`docs/recht/00_zweckbestimmung.md`).

## 4. Wo was steht

| Ort | Workout | Übung |
|---|---|---|
| Heute · Übersicht | Abschnitt „Workouts · n“, je Durchlauf eine Zeile: Name, Uhrzeit, Dauer, Übungen, Anstrengung oder „eintragen“ | wie bisher unter „Gemacht“, über den Tag zusammengefasst |
| Heute · Zeitleiste | je Durchlauf ein Block, sein Kopf ist der Workout-Eintrag | darunter Name und Kurzwert; der Planblock zeigt nur noch, was in der Liste geübt wurde |
| Workout-Eintrag `/workout/<einheit>` | Kopf, „Zum Workout“, Verlauf, Messung, Zuletzt | Liste in gegangener Reihenfolge, Tipp → Einträge der Übung (`…/leistungen/<übung>`) |
| Einträge der Übung | Herkunftszeile statt „vom Timer“ | alle genauen Werte |

## 5. Die Seite

1. Datum, Uhrzeit, drei Kacheln: Dauer · Übungen · Ende (durch/vorzeitig).
2. **Zum Workout:** Anstrengung 0–10, Notiz an Ort und Stelle (`Textnotiz`, kein Popup).
3. **Verlauf:** je Schritt Nummer im Plan, Name („· 2. Mal“ bei Schleifen), Kurzwert aus dem
   gültigen Eintrag (eine Korrektur zählt, `SessionRepo.eintrag_aktuell`), Dauer; Fragen mit
   Antwort und Übersprungenes als blasse Zeilen.
4. **Messung:** nur, wenn eine Aufnahme mitlief — die Herzfrequenz über dem Workout (5-s-Mittel,
   korrigiert wie in der Auswertung; ein Thread liest die Messdatei, `hf_lesen`) mit senkrechten
   Grenzen der Schritte, darunter der Weg zum Abschnitt „Workout …“ in der Auswertung.
5. **Gegangener Weg:** nur bei einem Ablauf mit Abzweigen oder Fragen, eingeklappt — das
   Ablaufbild (`components/ablaufbild`), Nichtbesuchtes blass, an den genommenen Wegen die Zahl
   (`Durchlauf.kanten`, `besucht`).
6. **Zuletzt:** der vorige Durchlauf desselben Workouts, eine Zeile, Tipp öffnet ihn; darunter
   **„Alle Durchläufe ›“** (`/workout/<einheit>/alle`): Datum, Dauer, Übungen, Eingetragenes,
   Notiz — der jüngste zuerst, ohne Wertung.

Außerhalb der Seite: Das **Tagebuch** zeigt Workouts, zu denen eine **Notiz** geschrieben ist
— die Skalen stehen als Zeile darunter; ein Workout nur mit Anstrengung steht dort nicht (Ben,
12.11.2026: im Tagebuch nur selbst Geschriebenes)
(`core.tagebuch.WORKOUT`, `EinheitRepo.workout_zeilen`; nach Tagen an ihrer Uhrzeit, nach Übungen
als Gruppe je Workout), Tipp → der Eintrag. In der **Zeitleiste** zeigt bei mehreren Workouts nur
das jüngste seine Übungen, die älteren klappen auf Tipp auf.

## 6. Technik

- `core/workout_eintrag.py`: `Durchlauf`, `Zeile`, `WorkoutWerte`, `durchlauf`,
  `fortsetzungen_markieren`, `kurz` — flet-frei, nur aus Ereignissen.
- `data/einheiten.py`: `zwischen`, `workout_davor`, `workout_werte`, `workout_wert`,
  `workout_eintragen`.
- `ui/views/workout_eintrag.py`: `durchlaeufe_am_tag`, `eintrag_kopf` (die Zeile),
  `workout_eintrag_view`; `components/srpe.workout_srpe_zeile`.
- `ui/views/tag.py`: `workout_teile` (Übersicht), `workout_block` (Zeitleiste);
  `ui/views/leistungen.py`: Herkunft; `ui/views/workout.py`: „Workout fertig“.

## 7. Stufen

- **Stufe 1 (gebaut):** Zeile in Übersicht und Zeitleiste, Seite mit Kopf, Anstrengung, Verlauf.
- **Stufe 2 (gebaut):** Herkunftszeile an der Übung, Notiz zum Workout, Karte „Messung“ mit
  HF-Kurve und Schrittgrenzen.
- **Stufe 3 (gebaut 10.11.2026 abends):** „Zuletzt“, alle Durchläufe als Reihe, eigene Skalen je
  Workout, der gegangene Weg im Ablaufbild, Workouts im Tagebuch, Einklappen in der Zeitleiste.

## 8. Offen

- P179: Soll der höchste Workout-Wert des Tags zusätzlich ins Tagesfeld gespiegelt werden, damit
  die sRPE-Last im HF-Verlauf ihn sieht? (Hängt an der zurückgestellten Lastrechnung.)
- Export/Sync: `workout_entry` liegt nur in der Datenbank; in den Export gehört es, sobald
  Einheiten dort mitgehen.
- Die HF-Kurve nimmt die Wanduhr der Messdatei; das Fenster kommt aus dem Versatz der
  HRV-Beteiligung der Einheit — am Gerät prüfen, ob Kurve und Schrittgrenzen zusammenpassen.
- Eigene Skalen reisen nicht in Paketen; ob sie das sollen, ist nicht entschieden.
- Gerätetests T123, T124.
