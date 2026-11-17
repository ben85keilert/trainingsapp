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
  `/workout/<einheit>/alle`; Verlauf → „Notizen“ zeigt Workouts **mit Notiz** (`core.tagebuch.WORKOUT`), Verlauf → „Tage“
  jedes Workout als Zeile nach der Uhr, die Anstrengung dahinter — „—“ ohne Eintrag (`EinheitRepo.workout_zeilen(mit_leeren=True)`, Ben 13.11.2026), die Zeitleiste klappt ältere Workout-Blöcke ein. **Ein Workout bleibt ein
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
  `views/ablauf.py`: Seite scrollt nicht, Palette = Übungen des Plans mit `Draggable.affinity`
  senkrecht; bedient wird **im Bild**, siehe unten „Im Bild bedienen“). Zeitleiste `plan/kante|frage|antwort`, `person/wdh`;
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
  oben wechselt **Workout · Liste** (`components/modus_wahl.py`). **Workout-Bildschirm** (Ben,
  15./16.11.2026, `docs/plan_uhr_fokus.md` §10): **Wege erst nach der Übung** — solange sie
  läuft, weder Wege noch „danach“; beendet rücken sie nach vorn (`views/workout.waehrend`:
  `vorn`). Der **Streifen je Übung nur bei linearem Ablauf** (`core.ablauf.ist_linear`), gefüllt
  nur Gemachtes. **Hart | Weich jederzeit** (`PlanAblaufBaustein.uebergang_setzen`, Umschalter
  in der Unterzeile; der Übergang steht im Schlüssel des Aufbaus) — ein Kurs setzt ihn nur als
  Vorgabe („Eigenverantwortung“); kein Ereignis in der Zeitleiste (Ben, 16.11.2026: „nein“).
  **Material von selbst** (Ben, 17.11.2026, §10.7): Eine Erklärung mit „beim ersten Mal von
  selbst zeigen“ öffnet das Blatt, sobald ihr Schritt beginnt — die Uhr steht solange, auch
  bei „hart“ (`views/workout.material_zeigen`); nur aus dem Takt und nur, wenn der Fokus oben
  liegt, nie beim Aufbau der Ansicht (Geister-Dialog).
  **Reiter „Ablauf“, drei Punkte** (Ben, 16.11.2026, §8.13): **Die Palette ist ein Vorrat an
  Übungen** — eine Kachel je Übung, „2×“ bei Mehrfachverwendung; Tippen oder Ziehen nimmt eine
  freie Planübung, sonst entsteht eine neue derselben Übung (`core.ablauf.vorrat`,
  `views/ablauf.ins_bild`), im Bild bleibt jede Planübung ein Knoten mit Nummer = Stelle in der
  Liste. **Eine Kachel bringt immer einen neuen Knoten** (Ben, 16.11.2026 abends: „einheitlich,
  neue Übung erstellen“) — hinter den gewählten (die Wahl geht auf den neuen: Kachel für Kachel
  eine Kette), auf eine Übung im Bild gezogen oder auf „Start“. **Ein eindeutiger Weg hat einen
  Punkt:** Der Abzweig steht nur ab zwei Wegen (`Geometrie.abzweige`; `austritte` für alle),
  sonst nur der Griff. **Im Bild bedienen** (Ben, 16.11.2026 nachts, P217, §8.13 Punkt 6 —
  „Menü“ · „Slot weglassen“ · „Ja. Hauptknoten wieder Blatt“): Jede Übung hat ihren **Punkt**
  (`Geometrie.punkte`); ihn auf eine Übung ziehen = Weg, auf sich selbst = noch einmal, auf
  „Ende“/„zurück“ (nur beim Ziehen sichtbar), von „Start“ auf eine Übung = Start
  (`core.ablauf.verbinden`, `on_verbinden`). **Gedrückt halten = Menü an der Übung**
  (`abbild.Menue`, eigene Karte in der Fläche — kein Flutter-Menü), nie verschieben. **Tipp auf
  den Punkt eines Wegs = Leiste unter dem Bild** (`wege_form.weg_leiste`: Auslöser, Zahl,
  Pflicht, „Mehr …“ = Blatt); **Tipp auf den Hauptknoten mit mehreren Wegen = Blatt** mit
  allen. Kachel „Frage“ in der Leiste. **Slots, das Menü „Routing“ und die Knopfzeile gibt es
  nicht mehr.** Alles Neue der Zeichnung ist nur an, wenn der Aufrufer den Rückruf gibt — der
  Kurs-Editor nutzt dieselben (`components/kursplan_bild.py`: Ziehen = Baustein „Weg“ nach
  Bestätigung, Menü = „Weg von hier“, „Weg zum Ende“, „Einstellen“).
  **Leeren heißt leer, den Start setzt die Person:** `Ablauf.ohne_start` (``{"an": true,
  "ohne_start": true}``) — fällt die Startübung weg (herausgenommen, gelöscht, „Lücke
  schließen“, beim Bereinigen nicht mehr da), **rückt nichts nach**: weder ihr Hauptweg noch
  die erste Planübung (`Ablauf.ohne_knoten`, `luecke_schliessen`, `bereinigt`; Ben: „Start wird
  selbst verbunden … sonst ändert sich was und man merkt es nicht“). Ohne Start beginnt kein
  Workout und sagt, dass der Plan korrigiert werden muss (`core.ablauf.START_FEHLT`,
  `ohne_start_text`, `PlanAblaufBaustein` lehnt ab; rote Karte im Reiter „Plan“ und über dem
  Bild, Knopf „Als Start“ am gewählten Knoten). Ein Workout, das der Liste folgt, beginnt
  weiter bei ihrer ersten Übung. **Ein unvollständiger Plan wird nicht durchgeführt** (Ben,
  16.11.2026: „… bis das repariert ist. Sonst ist es möglich, dass ein Plan durcheinander
  gerät“, §8.13 Punkt 5): Zeigt ein eigener Ablauf auf eine Planübung, die es gerade nicht
  gibt (Papierkorb, Paket aus — `core.ablauf.fehlende`), oder fehlt der Start, gibt es weder
  Starten noch Bereitstellen noch Fortsetzen (`core.ablauf.startet_nicht`,
  `ui/plan_ablauf.bereitstellen`); kein Rückfall auf die erste sichtbare Planübung
  (`startknoten`). Reparieren: zurückholen oder „… aus dem Plan nehmen“ an der roten Karte
  (`views/ablauf.reparatur_knoepfe`). **Die Frage** (Ben, 17.11.2026, §8.13 Punkt 7): Der
  Punkt eines Knotens liegt bei ihm — ist sein einer Weg ein Rückweg, am Austritt, nie am
  fernen Griff (`Geometrie.punkte`). Wege einer Frage fragen „Bei welcher Antwort?“ (Bereich
  der Skala · jede andere; Vorgabe `core.ablauf.antwort_bereich`), ohne „Pflicht“. **Eine
  Frage kann beides — je Weg** (Ben: „von selbst weiter + Weg vorschlagen“,
  `Kante.vorschlagen`, Schalter „nur vorschlagen“): Trifft die Antwort einen solchen Weg, geht
  nichts von selbst — er steht betont mit der Regel des Plans („Bei 7–10 schlägt der Plan
  vor:“, `core.ablauf.vorschlag_text` — nennt die Regel, deutet die Zahl nie), die Person
  tippt; ohne den Vermerk wird der Weg sofort gegangen, kein Plan von früher ändert sich. In
  der Weg-Leiste steht „Entfernen“ ausgeschrieben (Ben: „mach aus x --> entfernen“), im Blatt
  der Papierkorb. **Fragearten** (Ben, 17.11.2026, §8.13 Punkt 9): `Frage.art` Skala · Ja/Nein ·
  Auswahl (`antworten`, `mehrfach`); Wege daraus mit `ausloeser = "antwort"` und
  `Kante.antworten` (Wortlaut), frei = „jede andere“. Neue Wege nur über `core.ablauf.weg_neu`
  (nächste freie Antwort), eine geänderte Frage nur über `frage_ersetzen` (die Wege ziehen
  mit). **Führt eine Antwort zu mehreren Wegen, wählt die Person** (`antwort_wege`,
  `PlanAblaufBaustein.antwort_geben`/`antwort_waehlt`) — die Skala geht wie bisher den ersten.
  Eine Antwort ohne Weg warnt beim Bauen (`ohne_weg`). Was angekreuzt ist, liegt am Baustein
  (`kreuze`) und im Aufbau-Schlüssel der Workout-Ansicht — sonst antwortet „Weiter“ mit dem
  Stand vom Aufbau. **Die Leiste zeigt den ganzen Katalog** (Punkt 8): Suche, Filter
  (`state.hinzufuegen_filter`), Plan vor Katalog, Deckel 40; eine Katalog-Kachel legt die
  Planübung an (`ins_bild`). **Der Punkt eines Knotens** liegt nur bei einem Weg abwärts an
  dessen Griff, sonst unter dem Knoten (Punkt 10). **Gleichwertige Wege** (Punkt 11,
  `core.ablauf.gleichwertige`): mehrere freie Wege und alle Wege einer Frage gehören zum
  Ablauf — „bei Bedarf“ ist nur, was allein ein Weg mit Auslöser neben dem regulären erreicht.
  **Herausnehmen** (Punkt 12, P224): „Aus dem Ablauf nehmen“ lässt die Übung im Plan („frei“,
  Ben 9.11.2026) — **außer sie steht mehrfach im Plan**: Dann geht die herausgenommene
  Planübung mit aus dem Plan; hat sie Eigenes (`core.standards.eigenes`), wird gefragt
  (Vorgabe: bleibt frei, „1 frei“ an der Kachel). Die letzte Planübung einer Übung bleibt.

- **Neue Ereignisse der Zeitleiste** (Ben, 16.11.2026): Wer eines plant, sieht **vorher** in
  `core/einheit.py` nach — `ARTEN` und `DATEN_SCHLUESSEL` sind eine feste Liste, alles andere
  fällt weg (`daten_pruefen`) — und in der Tabelle von `docs/plan_einheit.md`. Ein Plan, der
  „schreibt … in die Zeitleiste“ sagt, ohne das geprüft zu haben, verspricht etwas, das der
  Vertrag nicht hergibt (so geschehen bei `plan/uebergang`, `docs/plan_uhr_fokus.md` §10.6).
