---
paths:
  - "**/*ablauf*"
  - "**/*workout*"
  - "**/plan_durchlauf.py"
  - "**/wege_form.py"
  - "**/modus_wahl.py"
  - "**/srpe.py"
  - "**/planstand.py"
  - "src/trainingsapp/ui/views/plan*.py"
  - "docs/plan_verzweigungen.md"
---

# Liste, Workout, gezeichneter Ablauf

Ausgelagert aus `CLAUDE.md` (11.11.2026); dort steht je Absatz die Kurzfassung mit den festen Regeln.

- **Liste oder Workout — Workout = Ablauf** (Ben, 10.11.2026, P170, Vertrag
  `docs/plan_verzweigungen.md` §8.12): Ein Plan ist eine **Liste** (frei abhaken, **keine
  Bedingungen** — Eingestelltes ruht, „Im Plan einstellen“ zeigt nur den Hinweis) oder ein
  **Workout**; jedes Workout hat den Reiter „Ablauf“, Bedingungen gibt es nur als Wege dort.
  Schalter „Liste | Workout“ (`views/ablauf.modus_zeile`, derselbe unter Uhren). **Der Ablauf
  folgt der Liste, bis man im Ablauf etwas ändert** (`core.ablauf.kette_der_liste`,
  `folgt_der_liste`, `fuer_plan` beim Laden in `PlanRepo._mit_items`; gespeichert nur
  ``{"an": true}``; vor jeder Änderung der Liste `PlanRepo._folgt_merken`) — neue Planübungen
  gehören dazu, Umordnen ordnet um; ein Abzweig macht den Ablauf eigen. Pläne von früher mit
  dem Schalter ``workout`` bekommen die Kette beim Laden, ohne Datenschritt. Ob ein Plan ein
  Workout ist, sagt ``plan.ablauf.an`` (`startet_als_workout`); „Trainieren“ zeigt es am Symbol.

- **Workout-Eintrag** (Ben, 10.11.2026, Vertrag `docs/plan_workout_eintrag.md`, Migration 053):
  **Werte gehören der Übung, der Verlauf gehört dem Workout.** Ein Durchlauf (beendete Einheit mit
  `plan/start` + `workout`, aus der etwas ins Tagebuch kam) wird aus der Zeitleiste gelesen
  (`core/workout_eintrag.py`, flet-frei) und steht je Durchlauf als **eine Zeile** unter Heute
  (Übersicht „Workouts · n“, Zeitleiste: Kopf des Blocks; `views/tag.workout_teile`/
  `workout_block`), Tipp → `/workout/<einheit>` (`views/workout_eintrag.py`: Kacheln, „Zum
  Workout“, Verlauf in gegangener Reihenfolge, Messung, Zuletzt). Die Übungen zeigt das Workout nur
  mit Kurzwert; die Werte bleiben in `session_entry`, dort nennt eine Zeile die Herkunft
  (`views/leistungen.py`). **Die Anstrengung (sRPE) gehört zum Durchlauf** — `workout_entry`
  (Ergebnis + Spec-Kopie + Notiz, unveränderlich mit `replaces_id`, `EinheitRepo.
  workout_eintragen`), eingetragen in „Workout fertig“ oder nachträglich im Eintrag
  (`components/srpe.workout_srpe_zeile`); das Tagesfeld „Anstrengung (sRPE)“ bleibt für den Tag,
  das Workout schreibt nicht hinein, keine Lastrechnung daraus (P179). **Eigene Skalen 0–10 je
  Workout** (Migration 054, `plan.workout_felder_json`, gerätelokal wie `freischaltung_seit` —
  `PlanRepo.workout_felder`/`workout_felder_setzen`, nie über `speichern`; „Felder …“ auf der
  Seite, Schlüssel `core.workout_eintrag.feld_key`, die Kopie der Felder am Eintrag hält auch
  entfernte lesbar). Die Seite hat dazu die HF-Kurve mit Schrittgrenzen (Thread, `hf_lesen`),
  den gegangenen Weg im Ablaufbild (nur mit Abzweig, eingeklappt; `Durchlauf.kanten`) und
  `/workout/<einheit>/alle`; das Tagebuch zeigt Workouts mit Eintrag (`core.tagebuch.WORKOUT`,
  `EinheitRepo.workout_zeilen`), die Zeitleiste klappt ältere Workout-Blöcke ein. **Ein Workout bleibt ein
  Workout:** „Trainieren“ öffnet es immer als Workout (`uebungen.heute_trainieren` nimmt
  `plan_als_plan` zurück), die Liste gibt es nur von Hand.

- **Gezeichneter Ablauf** (Ben, 8.11.2026, Vertrag `docs/plan_verzweigungen.md` §8, Stand
  §8.8; Migration 044, Datenschritt 6): Der Plan-Editor hat die Reiter **Plan · Uhren**, mit
  „Workout“ dazu **„Ablauf“**. **Zweige A–D, dann/sonst/Wege sind veraltet** (P108) —
  Altbestand wird zum Ablauf; die Karte „Weiter, wenn …“ je Planübung gibt es nicht mehr.
  `core/ablauf.py`: `Ablauf(an, start, kanten, fragen)`, `plan.ablauf_json`; **Knoten** sind
  Planübungen (Nummer = Stelle in der Liste, `nummern`; `beiname`) und **Fragen**, **Kanten**
  tragen den Auslöser (frei · Zeit ab · Wdh. · Wdh. in einer Zeit · Skala ≥ n bis m), Pflicht,
  „von selbst“ (hart sofort, weich erst bei Zeit ab), Ziel auch `ENDE`/`ZURUECK`. Bedingung und
  Hauptweg werden **gespiegelt** (`views/ablauf.ablauf_speichern`, `hauptwege_spiegeln`); „Im
  Plan einstellen“ zeigt dasselbe Wege-Formular (`components/wege_form.py`) mit „Kommt von“.
  Im Workout **bleibt** man bei der Übung, solange die Bedingung fehlt bzw. kein Weg frei ist
  (`PlanAblaufBaustein.wartet`, keine Pause), hart geht es von selbst weiter, sobald es reicht;
  jeder Schritt hat eine Uhr (ohne Timer `core.timer.stoppuhr`, „Zeit ab“ = „Fertig“) und damit
  den Fokus; Wiederholungen von Hand (`person/wdh`), wo niemand zählt. Rechnung nur in
  `core/ablauf.py`, `core/ablauf_geometrie.py` (wo Stamm, Abzweig, Wege und Griffe liegen —
  **Wege wie ein Nerv**, Ben 10.11.2026, §8.11: ein Austrittspunkt je Übung; Tipp auf den
  Abzweig = alle Wege, auf den Griff eines Wegs = nur dieser, `wege_karte(allein=)`; Rückwege
  in Gassen zwischen den Spalten) und `devices/plan_ablauf.py`; `ui/` zeichnet (`components/ablaufbild.py`:
  Fläche einmal bauen, Inhalt tauschen, Lagen bleiben bis „Neu anordnen“, Eltern mittig;
  `views/ablauf.py`: Seite scrollt nicht, Palette = Planübungen mit `Draggable.affinity`
  senkrecht, Knöpfe unter dem Bild). Zeitleiste `plan/kante|frage|antwort`, `person/wdh`;
  Paket `plaene[].ablauf` mit Positionen. **Korrekturen 9.11.2026** (§8.9): „Aus dem Ablauf
  nehmen“ lässt die Planübung im Plan (aus dem Plan: Kachel gedrückt halten), jede Kante hat
  einen Punkt zum Antippen (Blatt auf diesem Weg), Warnungen `core.ablauf.warnungen` sichtbar
  beim Zeichnen; **mehrere gleichwertige Wege — erst fragen**, hart wie weich
  (`core.ablauf.wahl_offen`, `PlanAblaufBaustein.wahl_noetig`, Karte „Wie geht es weiter?“);
  der Workout-Fokus liegt über dem Plan (`/plan/<id>/workout`, Zurück = Plan, Hinweis „Workout
  läuft“). **Durcharbeiten statt abarbeiten** (Ben, 9.11.2026, §8.10, P166–P169): mit Ablauf zählt
  „heute gemacht“ nie, ein vorzeitig beendetes Workout setzt heute fort (`plan/ende` mit `bei`,
  `core.ablauf.fortsetzung`); in der Liste ist nur frei, was keine nie erfüllte Pflicht versperrt
  (`core.ablauf.gesperrt`, Tore aus `plan/kante`, Migration 051 zum Zurücksetzen) — wie ein
  Kurs; „Trainieren“ öffnet so einen Plan als Workout (`plan_durchlauf.startet_als_workout`),
  oben wechselt **Workout · Liste** (`components/modus_wahl.py`).
