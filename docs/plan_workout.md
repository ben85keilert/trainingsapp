# Workout: der Plan läuft von vorn bis hinten

Ben, 7.11.2026 („Abläufe sollen zu Workouts werden, d. h. man gibt einen Plan vor, der …
durchgeht“). Vertrag für den **Modus Workout** — der zweite Trainingsmodus neben
„Standard“ (`docs/plan_planblock.md` §A). Der heutige **Ablauf** (`core/plan_durchlauf.py`,
`devices/plan_ablauf.py`, `ui/plan_ablauf.py`, `views/plan_ablauf.py`, `docs/plan_einheit.md`
§7) ist der Kern; das Workout gibt ihm Start-Bild, Fokus, Übergang, Klammer in der Messung und
Bedingungen. Skizzen: https://claude.ai/artifact/THG2KrMi4jET9N2XkHRk3J, Reihe C.

Rechtlicher Rahmen: Weg A (`docs/recht/00_zweckbestimmung.md`, Entscheidung 7.11.2026).
Bedingungen rechnen aus **Leistungen** (Zeit, Wiederholungen, Abhaken), nie aus Messwerten;
HF-Zonen nur als Anzeige, der Zielbereich-Ton (Entscheidung C) ist Information.

## 1. Begriffe

- **Workout** = ein Plan, der als Folge durchläuft. Zwei Wege hinein: der Schalter
  **„Workout“ am Plan** (Vorgabe: der Plan öffnet mit dem Start-Bild) und **▶ „Als Workout“**
  in jedem Plan für heute (Gesamtplan-Blatt und Plan-Menü).
- **Schritt** = eine Planübung im Workout, mit Timer (Profil der Planübung/des Plans/der
  Übung) oder ohne (dann „Weiter“ von Hand). `core/plan_durchlauf.Schritt`.
- **Übergang** (vor dem Start wählbar, Vorgabe am Plan):
  - **hart — läuft durch:** Ist der Timer ab (oder die Bedingung erfüllt), geht es sofort
    weiter; nur Pause oder Abbrechen halten an. Schritte ohne Timer warten auf „Weiter“.
  - **weich — nachtrainieren:** Nach Ablauf zählt der Timer **ins Minus** („−0:23 · über der
    Zeit“), man trainiert weiter; „Weiter“ tippt man. Eingetragen wird die tatsächliche Zeit.
- **Bedingung** je Schritt (W2): `keine` · `zeit` (Timer ab) · `wdh(n)` · `wdh_in_zeit(n, s)`
  · `gemacht`. **Härte**: weich = „Weiter“ geht immer, die Bedingung ist nur Vorschlag und
  Auto-Weiter; hart = Freischaltung: „Weiter“ erst bei Erfüllung, ein **Inhalt** (Video,
  Auftrag, Text) erscheint erst dann. **Abbrechen immer** — eine App hält niemanden fest.
- **Bleiben** (Ben, 8.11.2026 abends: „auch bei einem linearen Ablauf kann man Bedingungen
  setzen, um weiterzumachen — Standard: bei der Übung bleiben“): Ist die Zeit ab (oder „Fertig“
  getippt) und die Bedingung nicht erfüllt, endet der Schritt nicht — die Person bleibt bei der
  Übung (`PlanAblaufBaustein.wartet`, mit Timer in der Überzeit): eintragen, „Noch einmal
  versuchen“, weich „Trotzdem weiter“ (nie gegen eine Pflicht), Abbrechen. Hart geht es von
  selbst weiter, sobald es reicht. Keine Pause mehr im Workout.
- **Eintragen im Schritt**: Wo weder Sensor noch Takt zählen, trägt man Wiederholungen von Hand
  ein (``person/wdh`` → Bedingung und Eintrag); die Skala per Chips. Jeder Schritt zeigt den
  **Fokus** mit Kurven — ohne Timer läuft eine Stoppuhr mit („Zeit ab“ heißt dort: „Fertig“).
- ~~**Zweig** (W3)~~ und ~~**Wege**~~ (bis 8.11.2026 abends): Zweige A–D, „erfüllt →“, „nicht
  erfüllt →“ und Wege sind seit P108 **Kanten im gezeichneten Ablauf**
  (`docs/plan_verzweigungen.md` §8); Altbestand übersetzt Datenschritt 6. Der Reihe nach gibt es
  nur die Bedingung. Was bis dahin galt:
- **Wege** (Ben, 8.11.2026): Neben der Bedingung bietet ein Schritt **alternative Pfade** an,
  vorher gesetzt („Weiter mit B: Dehnung — Beine krampfen“, „Weiter mit C: Planke“), im Workout
  als Knöpfe; ein Weg darf zu einer schon gemachten Übung oder zur laufenden selbst führen
  („Noch einmal“). So entstehen **Schleifen**: Wandsitz 60 s, Pause, Wandsitz … Eine
  Endlosschleife ist nur ein Problem, wenn es keinen Weg hinaus gibt — `core.bedingung.schleifen`
  warnt dann (Start-Bild, „Im Plan einstellen“); Abbrechen geht immer. Verweise (`dann`,
  `sonst`, Wege) gelten auch zu gemachten Übungen und zum Schritt selbst
  (`PlanAblaufBaustein.ziel_index`).
- **Bedingung „Skala“** (Ben, 8.11.2026): „bis es unangenehm wird, 6/10 — dann Wechsel“. Die
  Person wählt im Schritt einen Wert (Chips über die Skala der Übung, sonst 0–10, je Durchlauf
  neu); ab `n` ist die Bedingung erfüllt. Eine **Selbsteinschätzung**, kein Messwert (Weg A);
  die Wahl steht als ``person/skala`` in der Zeitleiste und geht in das Skalenfeld des Eintrags.
- **„Weiter, wenn …“ gehört allein dem Plan** (Ben, 8.11.2026: „in Einzelübungen macht das
  keinen Sinn“ — P107 vom Vortag zurückgenommen): kein Abschnitt in „Übung bearbeiten“, kein
  Paketfeld an der Übung; `exercise.bedingung_json` (Migration 042) bleibt als leere Spalte.

## 2. Bilder (Reihe C)

- **C1 Start:** Titel „Plan · Workout“, „n Schritte · etwa x min“; Hinweis, wenn eine
  Aufnahme läuft („das Workout wird ein Abschnitt“); Umschalter **hart · läuft durch /
  weich · nachtrainieren** mit Erklärsatz; die Schritte mit Bedingung („Timer 2 × 30 s ·
  weiter, wenn Zeit ab“, „15 Wdh. (Sensor)“, „12 in 40 s · sonst → B“, Schloss am
  freigeschalteten Inhalt, „nur abhaken“); „Workout starten“, „Bereitstellen“, „Als Plan
  üben“. Was heute schon gemacht ist, ist abgehakt und kommt nicht dran (wie der Ablauf);
  „Noch einmal“, wenn alles abgehakt ist.
- **C2 Fokus je Übung:** wie der Fokus der Übung (`docs/plan_planblock.md` §B) mit
  Fortschrittsbalken „Schritt k von n“, Chips Takt · Bewegung · HF; weich zeigt nach Ablauf
  **−m:ss** in Warnfarbe; Bedingungskarte (grün „erfüllt“, mit ±1 des Sensors); Schrittliste
  (erledigt · läuft · offen); großer Knopf „Weiter: <nächster>“, darunter Pause ·
  Überspringen · Abbrechen. **Kurven** (Ben, 7.11.2026): neben dem HF-Wert eine
  Kurven-Einblendung der letzten 2 Minuten mit wählbaren Reihen — HF, RR, RMSSD, SDNN,
  Atemfrequenz, RSA/Atemspanne (die Live-Reihen des Messlaufs, nur Anzeige); welche Reihen
  stehen, merkt das Gerät (`AppState.fokus_kurven`), die feinere Regelung (je Übung? je
  Workout? Skalen?) ist **P96**.
- **C3 Bedingung nicht erfüllt:** Zeit ab, „9 von 12“; Karte „nicht erfüllt … Du
  entscheidest“; Wege: **Zweig B** (gefüllt, „danach zurück nach A“), **„Trotzdem weiter“**
  (nur weich), „Noch einmal versuchen“; der gesperrte Inhalt mit Schloss. Bei **hart** nur
  Zweig B, Noch einmal, Abbrechen.
- **C4 Ende:** „Workout fertig · Dauer · n Schritte, k eingetragen, j über Zweig“; Ergebnis je
  Schritt (Zweig markiert, „Inhalt freigeschaltet“); **Aufnahme-Karte** mit dem Abschnitt
  „Workout <Plan>“ und den Übungen als Abschnitte darin (HF, RMSSD), „Öffnen ›“ zur Messung;
  sRPE wie heute; „Zum Plan“ / „Noch einmal“.

## 3. Technik

- **Daten:** `plan.workout` (Schalter), `plan.uebergang_hart` (Vorgabe), Migration 040; für
  heute `AppState.workout_uebergang[plan_id]`. W2/W3 ergänzen je Planübung `bedingung_json`
  (Art, Zahl, Sekunden, hart, Inhalt, dann, sonst) und `zweig`; Paketfelder entsprechend
  (`docs/uebungspakete.md`, Drei-Wege-Abgleich je Feld).
- **Lauf:** `PlanAblaufBaustein` bleibt der Motor (je Schritt ein `TimerBaustein` auf einer
  Achse, `plan/uebung_start|ende`, `plan/pause`, `plan/ende`). Neu: `uebergang`
  (`hart`/`weich`): hart = nach `timer/ende` sofort `_beginnen(nächster)`; weich = der Timer
  läuft **über** (`TimerLauf.ueber_s()`), kein Pausenbild, `weiter()` von Hand. Eingetragen
  wird je Schritt beim Ende wie heute (`ui/plan_ablauf.nach_der_uebung`); die Überzeit zählt
  zur gelaufenen Zeit.
- **Fokus:** der „Während“-Teil des Übungs-Timers wird eine Komponente
  (`ui/components/fokus.py`, einmal gebaut, je Tick nachgezogen) und dient dem Übungs-Timer
  wie dem Workout (`views/workout.py`, Route `/plan/<id>/workout`). Kurven aus
  `Messlauf.live` über `components/kurve.kurve` (keine Rechnung in `ui/`, nur Reihen des
  Live-Fensters).
- **Messung:** Beginnt das Workout, setzt es ein Paar Grenz-Notizen „Workout: Start/Ende“
  (Spur `einheit`, wie Kopf-/Endteil-Abschnitte, `docs/plan_abschnitte.md`); die Übungen
  behalten ihre Marken (`ui/marken`), so liegen sie als Abschnitte **im** Workout-Abschnitt.
  Die Auswertung zeigt beides (Chip „Workout <Plan>“, darunter die Übungen).
- **Ende-Bild:** `views/workout.py` `danach` aus `ergebnis_der_einheit`, sRPE
  (`components/srpe.py`), Aufnahme-Karte mit Kurve des Abschnitts.

## 4. Stufen

| Stufe | Inhalt | Stand |
|---|---|---|
| W1 | Schalter und ▶, Start-Bild mit hart/weich, Fokus je Übung (Komponente), Minus-Timer, Workout-Abschnitt, Ende-Bild, Kurven-Einblendung HF/RR/RMSSD/SDNN/Atemfrequenz/RSA | **gebaut 7.11.2026 (0.3.60)** — Ende-Bild ohne Kurve der Aufnahme (Hinweis statt Karte, P98) |
| W2 | Bedingungen `zeit` · `wdh` · `wdh_in_zeit` · `gemacht`, Härte als Freischaltung mit Inhalt (Text, Link), Karte „Weiter, wenn …“ in „Im Plan einstellen“ | **gebaut 7.11.2026 (0.3.61)** — Kurse unverändert (hart = `zugewiesene_kurse`, P97) |
| W3 | Zweige A–D je Planübung, „erfüllt →“/„nicht erfüllt →“ auf jede Planübung, C3-Wahl in der Ansicht, Schleifenprüfung (`core.bedingung.schleifen`, noch ohne Hinweis im Editor) | **gebaut 7.11.2026 (0.3.61)** |
| W4 | HF-Zone als Anzeige (Zone · % HRR · Zeit in Zone) in der HF-Kachel des Fokus; Zielbereich-Ton oben/unten (Entscheidung C, Einstellungen → Herzfrequenz) | **gebaut 7.11.2026 (0.3.61)** — im Patientenmodus bleibt der Ton (Ben, 13.11.2026; bis dahin „Ton aus“ — `docs/recht/00_zweckbestimmung.md`, „Zielbereich-Ton im Patientenmodus“) |

## 4a. Umsetzungsstand W1 (7.11.2026)

- `core/timer.py`: `TimerLauf.ueber_s()`, `laeuft_roh`; `devices/plan_ablauf.py`: Phase
  `UEBERZEIT`, `uebergang=HART|WEICH`, `workout=True` → `plan/start`/`plan/ende` mit
  ``workout``; `core/einheit.py`: Spur `workout`, Daten ``ueber_s``/``workout``, Projektion;
  `ui/plan_ablauf.nach_der_uebung` addiert die Überzeit auf den letzten zählenden Abschnitt.
- `ui/components/fokus.py`: Klasse `Fokus` (Übungs-Timer und Workout), Kurven-Einblendung
  (`kurven_reihen` über `hrv_core.trends.verlauf`, 2 min, 1 Hz), `AppState.fokus_kurven`.
- `ui/views/workout.py`: Vorher/Während/Danach, Route `/plan/<id>/workout`; ein Plan mit
  `workout` öffnet so (`/plan/<id>`), bis „Als Plan üben“ (`AppState.plan_als_plan`);
  ▶ „Als Workout“ in der Planleiste und im Gesamtplan-Blatt; Übergang für heute
  `AppState.workout_uebergang`. Migration 040 (`plan.workout`, `plan.uebergang_hart`), Karte
  „Workout und Ablauf“ im Plan-Editor (`views/plan_ablauf.plan_timer_karte`).
- Der alte Ablauf (`/plan/<id>/timer/ablauf`) bleibt bis W2 bestehen — gleicher Motor.
- Tests: `tests/test_workout.py`, `tests/test_ui_workout.py`, `tests/test_ui_fokus.py`.

## 4b. Umsetzungsstand W2–W4 (7.11.2026, 0.3.61)

- `core/bedingung.py`: `Bedingung` (art, n, sekunden, hart, inhalt, zweig, dann, sonst),
  `pruefen(Bedingung, Stand) → Erfuellung` (erfüllt · verfehlt · unprüfbar), `naechster_im_zweig`,
  `schleifen`; `PlanItem.bedingung`, Migration 041 (`plan_item.bedingung_json`),
  `PlanRepo.bedingung_setzen`/`item_speichern`; `Schritt.bedingung`.
- `devices/plan_ablauf.py`: `naechster` folgt ``dann`` → Zweig → Hauptzweig (`ziel_index`);
  `weiter(ziel)` auch mitten in der Übung (Zweig, „trotzdem weiter“), `wiederholen()`; „Fertig“
  im weichen Übergang endet die Übung (keine Überzeit, `_fertig_gewollt`).
- „Im Plan einstellen“: Karte „Weiter, wenn …“ (Art, Zahl, Sekunden, hart, Inhalt, Zweig,
  erfüllt →, nicht erfüllt →); „Alles wie die Übung“ setzt sie zurück. Hilfethema `workout`.
- `views/workout.py`: Bedingungskarte je Tick (Wiederholungen aus dem Zähl-Teil der Planübung,
  sonst „niemand zählt — von Hand bestätigen“), harte Bedingung sperrt „Weiter“ (Abbrechen
  bleibt), Inhalt „Freigeschaltet“ bei Erfüllung, C3: „Zweig B: …“ · „Trotzdem weiter“ (nur
  weich) · „Noch einmal versuchen“; Start-Bild und Schrittliste zeigen Bedingung, Zweig,
  Schloss. **P98:** Ende-Bild findet die Aufnahme der Einheit (`EinheitRepo.beteiligungen`,
  `HrvRepo.zur_datei`) und öffnet sie mit Zoom auf den Workout-Abschnitt.
- Fokus: HF-Kachel „Zone · % · Zeit“ (`core.hf_profil.bereiche_fuer`/`bereich_von`, Bereiche
  einmal beim Bauen), Zielbereich-Ton hoch/tief gedrosselt (`HfEinstellungen.ziel_unten_bpm`,
  `alarm_klang_tief`; `components/hf_sicht.alarm_zeilen` mit „darunter“).
- Nicht gebaut: Bedingungen im Paket (P97), Zähl-Teil startet im Workout nicht von selbst —
  „Wdh. zählen“ bzw. Takt-Zählen wie beim Übungs-Timer anbringen (P99); Hinweis auf Schleifen
  im Editor (P100).

## 4c. Uhren K4 (8.11.2026, 0.3.62)

Die alte Ablauf-Ansicht (`views/plan_ablauf.py`) ist weg — das Workout ist der eine Einstieg
(Heute → „Start“, Ziele, Timer-Karte, Laufleiste; `…/timer/ablauf` zeigt es). Hart/weich ist
**eine Haltung mit drei Folgen** (Timer läuft ab · Übung ohne Timer · Bedingung verfehlt), im
Start-Bild in einem Satz, dazu die HRV-Schalter. „Auf Tipp warten/automatisch“ und „Pause ohne
Timer“ sind darin aufgegangen (Migration 043: `auto_next` → `uebergang_hart`). Die harte
Bedingung heißt in der Oberfläche **Pflicht**. Je Schritt kommt der Takt der Planübung an den
Timer (P99 Teil 1). Vertrag und Stand: `docs/plan_uhren.md` §4.7, §6a.

## 4d. Verzweigungen, zweiter Anlauf (8.11.2026 abends)

Ben: lineare Pläne mit Abweichungen zur Seite (Einschub mit Rückkehr), Übungen nur bei Bedarf,
Schleifen — die Zweige A–D sind dafür zu abstrakt. Plan: `docs/plan_verzweigungen.md`
(Ablauf · Bedarfsübung · Einschub · Abzweig · Schleife · Auslöser; Stufen V1–V3; P108–P111).

## 5. Offen

- P83 (Workouts) → dieses Dokument. P96: welche Kurven im Fokus, je Gerät/Übung/Workout,
  Skalen. P97: Bedingungen in Paketen (Formatversion?). P95: Name „Fokus“. P98: Aufnahme-Karte
  im Ende-Bild mit der Kurve des Workout-Abschnitts (C4) — braucht die gespeicherte Messung.
- Gerätetest T95: Workout hart/weich am Gerät, Minus-Timer, Abschnitt in der Aufnahme.
- P97, P99 und P100 sind am 8.11.2026 gebaut (0.3.63, `docs/plan_uhren.md` §8): Bedingungen im
  Paket, Zählen je Schritt im Workout, Schleifenhinweis. Gerätetests T96 (W2–W4), T97.
