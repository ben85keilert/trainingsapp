# Uhr und Fokus beim Üben (Plan, 8.11.2026 abends)

Ben, 8.11.2026, nach dem Üben eines Plans: Der Fokus beim Üben unterscheidet sich vom Workout
(es fehlen die Eingaben), ▶ soll gleich in den Fokus führen, die Uhr einer Übung braucht
**Parameter je Runde** (Variante, Gewicht, Winkel — mit eigenem Takt oder ohne), sie muss sich
**von der Übung aus schnell einstellen** lassen, alle Timer gehören **gesammelt in die
Einstellungen**, und nach einer Übung braucht der Fokus oben **feste Pfeile**. „Entwirf einen
Plan wieder mit Skizzen.“

Skizzen: **Reihe F (F1–F7)** auf der Fläche der Uhren
(https://claude.ai/artifact/THG2KrMi4jET9N2XkHRk3J, unter Reihe E). Offene Fragen: P145–P150
in `docs/offene_fragen.md`. Verwandt: `docs/plan_uhren.md` (Glossar, Zeit-Blatt, Uhrenplan),
`docs/plan_taktgeber.md` (Takt je Abschnitt), `docs/plan_varianten.md` (je Ausführung ein
offener Eintrag), `docs/plan_planblock.md` (Pfeilzeile, Gesamtplan).

## 0. Wie es heute ist

- **Uhr-Zeile** in der Karte „Eintragen“ (`components/uhr.py`): Menü Stoppuhr/Timer, Zeit,
  „zählt“, Takt, ⧗ Bereitstellen, ▶. Auf 412 px wird der Name zu „S…“ (Bens Bild). ▶ startet;
  den Fokus öffnet es nur mit „Fokus beim Start der Uhr öffnen“ (Vorgabe aus, 7.11.2026).
- **Fokus** (`components/fokus.py`): im Timer der Übung (`views/uebung_timer.py`, „Während“)
  ohne Eingaben; im Workout (`views/workout.py`) seit 0.3.67 mit Wiederholungen von Hand und
  Skala-Chips.
- **Timer an vier Orten:** Vorlagen (Einstellungen → Timer → Vorlagen), an der Übung
  (`exercise.timer`, mehrere Profile, bearbeitet in „Übung bearbeiten“), am Plan („für alle
  Übungen“, `plan.timer`) und an der Planübung (`PlanItem.timer`: Wahl oder eigene Kopie). Die
  Planübung kann nur **wählen** („Anderen Timer nur hier …“, `components/timer_wahl.py`),
  einen neuen anlegen geht dort nicht. Das ⏱ am Block öffnet die Timer-Seite der Übung — dort
  stellt man eine Einmal-Zeit, aber nicht die Uhr selbst.
- **Abschnitt** (`core.timer.Abschnitt`): Name, Dauer, Klang, zählt, Takt — **keine
  Ausführung**. Der Lauf trägt ein, was der Block beim Start zeigt
  (`UebungKontext.auspraegung`), für den ganzen Lauf gleich.
- **Einträge:** je Ausführung (Variante, Gewicht, Seite, Winkel) ein offener Eintrag
  (`core/eintraege.py`).

## 1. Ein Fokus, überall mit „Eintragen“ (Skizze F2)

Der Fokus bekommt unter Zeit, Takt und Kurven die Karte **„Eintragen“** — dieselbe für den
Timer der Übung und das Workout (das Workout verliert seine eigenen Wdh.- und Skala-Teile, sie
gehen in die Karte auf):

- **Felder wie im Block** (SpecForm der Planübung, schmal): Ausprägungen (Variante, Gewicht,
  Winkel, Seite) als Segmente bzw. −/+, Skala als Chips, Wiederholungen mit −/+ und
  Schnell-Chips (Ziel, 5, 10, 12, 15, 20). **Vorbelegt** mit dem, was der Block zeigt bzw. der
  laufende Abschnitt vorgibt (§3).
- **Zeitfelder** füllt die Uhr — sie stehen nur lesend da („kommt von der Uhr“), solange die
  Zeit zählt.
- **Wer zählt, zählt** (P122): Zählt der Sensor oder der Takt, steht dort dessen Zahl mit
  −1/+1 (wie heute); nur sonst die Eingabe von Hand.
- **Je Satz:** Die Sätze sind die zählenden Abschnitte; eingegebene Wiederholungen gehören zum
  laufenden Satz (wie der Sensor, Karte „Sätze“).
- **Gespeichert** wird mit „Fertig“ (bzw. wenn ein hartes Workout weitergeht), zusammen mit der
  Zeit, in den offenen Eintrag **der Ausführung** (§3). Abbrechen verwirft wie heute;
  nachtragen unter „Läufe heute“ (P150).
- Im Workout liest die Bedingung aus der Karte (Wdh., Skala) — wie heute aus den Teilen.

## 2. Die Uhr-Zeile: ▶ heißt Fokus (F1, F7)

- **Zeile:** `Uhr ▾ · Zeit · Takt · ▶` — „zählt“ wandert ins Uhr-Blatt (§4) und als kleiner
  Chip in den Kopf des Fokus, ⧗ „Bereitstellen“ ins Menü (P148). Der Name hat dann Platz
  („Stoppuhr ▾“, „Seiten L·R·B ▾“).
- **Menü ▾:** Stoppuhr · die Timer (Übung, Planübung, Plan; je mit Kurztext) · **Ohne Uhr —
  nur Fokus** · ─ · **Uhr einstellen …** (§4) · Bereitstellen für „Alle starten“. Die Wahl gilt
  für jetzt (wie heute, P79).
- **▶ öffnet den Fokus** mit allem Vorbelegten (Ausführung, Ziel, Takt) und startet die Uhr.
  Der Schalter „Fokus beim Start der Uhr öffnen“ bekommt die Vorgabe **an** (P145).
- **Ohne Uhr** (F7): ▶ öffnet den Fokus ohne Zeit — Kurven, Takt, Bewegung, „Eintragen“,
  „Fertig“. Intern läuft die Einheit mit einer Stoppuhr, die **nicht zählt und nicht
  angezeigt** wird: Marken in Messung und Strecke, „Läufe heute“ und die Pfeile bleiben gleich,
  ins Tagebuch kommt keine Zeit. „Uhr aus“ an Übung bzw. Planübung (`uhr_an`) heißt künftig
  „Ohne Uhr“ — die Zeile bleibt schmal mit ▶ stehen (P146).

## 3. Ausführung je Abschnitt (F4)

Bens Beispiel: Variante links/rechts/beide — „1 min links, Runde 2 2 min rechts, Runde 3 30 s
beide, jede Runde mit eigenem Takt oder nicht“.

- **Modell:** `Abschnitt.ausfuehrung: dict[str, Any]` — Schlüssel sind die Ausprägungsfelder
  der Übung (`core.parameter.AUSPRAEGUNGS_TYPEN` und die Variante), leer = „wie gewählt“ (der
  Block). Im JSON nur, wenn gesetzt — ältere Profile bleiben gleich. Ein Takt je Abschnitt gibt
  es schon (`Abschnitt.takt`).
- **Wo:** nur an Timern, die zu einer Übung gehören — Profile der Übung und eigene Kopien der
  Planübung. Vorlagen und der Plan-Timer kennen keine Felder; als Kopie in eine Übung geholt,
  bekommen ihre Abschnitte die Zeile „Ausführung“ dazu.
- **Runden:** Eine Runde mit eigener Dauer und Ausführung ist ein **Abschnitt**; „× n Runden“
  wiederholt eine Gruppe gleich. Mit Ausführung schlägt der Editor den Namen vor („Links“).
- **Editor** (Timer-Editor, Profilziel der Übung): je Abschnitt unter Name · Dauer · Takt ·
  zählt die Zeile **Ausführung** — Chips der Variante, −/+ für Gewicht, Winkel; „wie gewählt“
  als Vorgabe. Unten die Vorschau „Eingetragen wird: Links 1:00 · Rechts 2:00 · Beide 0:30“.
- **Lauf:** Zu Beginn jedes Abschnitts schreibt die Einheit `timer/abschnitt` mit
  `ausfuehrung`; der Fokus zeigt sie groß („Runde 2 · Rechts · 10 kg“), die Karte „Eintragen“
  schaltet auf sie um.
- **Eintragen:** `core/timer_eintrag.gelaufene_zeiten` behält die Ausführung je Abschnitt;
  „Fertig“ schreibt **je Ausführung** in deren offenen Eintrag — links Haltezeit [1:00],
  rechts [2:00], beide [0:30]; Runden ergeben mehr Sätze je Ausführung. Wiederholungen eines
  Abschnitts gehen in den Eintrag seiner Ausführung.
- **Weggefallen:** Nennt eine Ausführung eine Variante, die es nicht mehr gibt, gilt „wie
  gewählt“ — der Editor zeigt einen Hinweis.
- **Paket:** `timer[].abschnitte[].ausfuehrung` (Tabelle Feld → Wert), keine neue
  Formatversion, ältere Apps übergehen es (`docs/uebungspakete.md`).
- Nur Ausprägungen, keine Ziel-Wiederholungen je Abschnitt (P149).

## 4. Das Uhr-Blatt: einstellen, wo man übt (F3)

Ein Blatt von unten, **dieselbe Sprache wie das Takt-Blatt** (Geltung, K5):

- **Öffnen:** das ⏱ am Block (statt der Timer-Seite), „Uhr einstellen …“ im Menü ▾, das ⚙ im
  Kopf des Fokus, die Timer-Zelle im Uhrenplan (ersetzt den Dialog aus
  `components/timer_wahl.py`).
- **Geltung** oben: **Für jetzt** · **In „Rumpf“** (nur aus einem Plan) · **Übung** (überall).
  Vorbelegt nach dem Ort: aus dem Plan „In „Rumpf““, sonst „Übung“.
- **Liste** zum Antippen: Stoppuhr · die Timer der Übung (je ✎) · Timer des Plans · Vorlage als
  Kopie … · Ohne Uhr. **„+ Neuer Timer“** öffnet den Editor (§3) gleich — gespeichert nach der
  Geltung: Übung → `exercise.timer`, In „Rumpf“ → eigene Kopie der Planübung, Für jetzt →
  nicht gespeichert (wie die Einmal-Zeit).
- Darunter: **Zeit zählt als Haltezeit** (Schalter, mit Geltung), die Takt-Zeile (öffnet das
  Takt-Blatt), **„Übernehmen“**.
- **„Im Plan einstellen“** bekommt im Abschnitt „Uhr“ dieselbe Liste mit „+ Neuer Timer nur
  hier“ — das fehlte (Bens „Timer hinzufügen geht in der Übung im Plan nicht wirklich“).
- Die Timer-Seite der Übung bleibt der Fokus (Vorher · Während · Danach); man erreicht sie
  mit ▶.

## 5. Einstellungen → Timer → „Alle Timer“ (F5)

Wie die Vorlagen, nur für alle: eine Seite unter Einstellungen → Timer, Reiter **„Alle“**
neben Stoppuhr · Zeit · Vorlagen.

- **Gruppen:** Vorlagen · An Übungen (je Übung ihre Timer, gelten überall) · Nur in Plänen
  (eigene Kopien der Planübungen, „Rumpf › Seitstütz“, und der Timer „für alle Übungen“ eines
  Plans). Suche oben, Chips zum Filtern.
- **Je Zeile:** Name, Kurztext (Abschnitte, Ausführungen), **„benutzt in …“** (Planübungen, die
  ihn wählen), ✎ (Editor an seinem Ort), ⋮: Kopieren · Als Vorlage speichern · In andere
  Übung kopieren … · Löschen.
- **Löschen fragt** und nennt, wer ihn benutzt; diese Planübungen fallen zurück (Planübung >
  Plan > Übung, `timer_fuer`). Inhalte von Plänen ändern sich nur so, auf ausdrücklichen Tipp.
- Rechnen (wer benutzt was) in `core/uebung_timer.py`, nie in `ui/`.

## 6. Fokus nach der Übung: feste Pfeilzeile (F6)

- Dieselbe Zeile wie beim Üben im Plan (seit 67b9129 fest über der Liste):
  `‹ vorige · 3/6 ▾ · nächste ›` — als eigene Komponente (`components/planpfeile.py`) für Plan
  und Fokus, fest oben im Fokus.
- **Wann:** im Fokus mit Plan **vor** dem Start und **nach** dem Ende; während die Uhr läuft
  nicht (dort Pause · Nächster · Fertig).
- Nach „Fertig“ ist › betont; die Mitte öffnet den Gesamtplan (`components/planblatt.py`), ein
  Tipp wechselt. „Nächste Übung“ in der Ergebniskarte entfällt, „Noch einmal“ bleibt.
- **Wohin:** Man bleibt im Fokus — die nächste Übung steht bereit (Vorher: Zeit, Ausführung,
  ▶); Zurück führt in den Plan zur gezeigten Übung (P147).

## 7. Stufen

| Stufe | Inhalt | Skizzen |
|---|---|---|
| U1 | Karte „Eintragen“ im Fokus (gemeinsam für Timer der Übung und Workout), Pfeilzeile als Komponente, fest im Fokus vorher/nachher | F2, F6 |
| U2 | Uhr-Zeile: Menü mit „Ohne Uhr“ und „Uhr einstellen …“, ▶ = Fokus, „zählt“ und ⧗ umgezogen | F1, F7 |
| U3 | Uhr-Blatt mit Geltung und „+ Neuer Timer“ (⏱, Menü, Fokus, Uhrenplan, „Im Plan einstellen“) | F3 |
| U4 | Ausführung je Abschnitt: Modell, Editor, Lauf, Eintragen je Ausführung, Paketfeld | F4 |
| U5 | Einstellungen → Timer → „Alle“ | F5 |

Jede Stufe mit Tests (flet-frei, wo es geht: Ausführung je Abschnitt und „benutzt in“ im
Kern), Doku und Gerätetest-Eintrag.

## 8. Offene Fragen (Katalog P145–P150)

- **P145** ▶ öffnet immer den Fokus — Schalter „Fokus beim Start der Uhr öffnen“ entfällt
  oder bleibt mit Vorgabe an? *Vorschlag: bleibt, Vorgabe an.*
- **P146** „Uhr aus“ an Übung/Planübung wird „Ohne Uhr“ — die Zeile bleibt schmal mit ▶ für
  den Fokus? *Vorschlag: ja.*
- **P147** › im Fokus nach dem Ende: im Fokus bleiben (nächste Übung bereit) oder zurück zum
  Block im Plan? *Vorschlag: im Fokus bleiben.*
- **P148** „zählt“ ins Uhr-Blatt und den Fokus-Kopf, ⧗ ins Menü — damit der Name der Uhr Platz
  hat? *Vorschlag: ja.*
- **P149** Je Abschnitt nur Ausprägungen oder auch Ziel-Wiederholungen („Runde 1: 12 Wdh.“)?
  *Vorschlag: erst nur Ausprägungen.*
- **P150** Eingaben im Fokus: erst mit „Fertig“ gespeichert oder sofort in den offenen
  Eintrag? *Vorschlag: mit „Fertig“; Abbrechen verwirft, „Läufe heute“ holt nach.*
