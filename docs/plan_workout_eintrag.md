# Workout-Eintrag

Stand: 10.11.2026 — Stufen 1 und 2 gebaut (Migration 053), Stufe 3 teilweise. Skizzen E1–E4:
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
  Weitere Felder je Plan sind vorgesehen, noch nicht gebaut.
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
4. **Messung:** nur, wenn eine Aufnahme mitlief — führt zu ihrem Abschnitt „Workout …“.
5. **Zuletzt:** der vorige Durchlauf desselben Workouts, eine Zeile, Tipp öffnet ihn.

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
- **Stufe 2 (gebaut):** Herkunftszeile an der Übung, Notiz zum Workout, Karte „Messung“ (Link;
  die kleine HF-Kurve mit Schrittgrenzen aus Skizze E3 fehlt noch).
- **Stufe 3:** „Zuletzt“ (gebaut); offen: alle Durchläufe eines Workouts als Reihe, weitere
  Felder je Plan, der gegangene Weg im Ablaufbild, Workout-Einträge im Tagebuch.

## 8. Offen

- P179: Soll der höchste Workout-Wert des Tags zusätzlich ins Tagesfeld gespiegelt werden, damit
  die sRPE-Last im HF-Verlauf ihn sieht? (Hängt an der zurückgestellten Lastrechnung.)
- Export/Sync: `workout_entry` liegt nur in der Datenbank; in den Export gehört es, sobald
  Einheiten dort mitgehen.
- Gerätetest T123.
