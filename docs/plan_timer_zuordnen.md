# Timer: eine Wahl überall, Editor im Fenster, Bibliothek mit Zuordnung

Stand: 10.11.2026 — **Entwurf, nichts gebaut.** Offen: P171–P176 (`docs/offene_fragen.md`).
Skizzen: noch keine.

## 0. Anlass

Ben, 10.11.2026, zu zwei Bildschirmfotos („Im Plan einstellen“ → Uhr beim Üben; Uhrenplan,
Karte „Planke“):

1. „Aus dem Plan heraus sollte es möglich sein, wieder alle 3 Möglichkeiten: nur jetzt – Plan –
   Übung. Das muss vereinheitlicht werden, auch hier (Bild 2).“
2. „Man kann Timer reinladen und diese für nur hier abändern, aber die Modifikation der Timer
   klappt noch nicht intuitiv. Die Klänge fehlen als Einstellmöglichkeit. Hier wäre es gut, wenn
   die Timereditfunktion ähnlich aussieht wie beim Haupttimer, aber im Fenster bleiben, dass man
   einen schönen Überblick über die verschiedenen Zeiten hat.“
3. „Es wäre gut, wenn man die Timer noch zuordnen könnte. Das wird vermutlich mit einer
   Datenbankschemaänderung einhergehen?“
4. „Wenn ein Timer in 3 Übungen verwendet wird und dieser dann geändert und gespeichert wird,
   soll es einen Infodialog geben: Überall ändern · nur hier: Kopie anlegen.“

## 1. Befund: wie es heute ist

**Ablage.** Ein Timer ist ein `TimerProfil` (`core/timer.py`) und liegt als **eingebettete
Kopie** an vier Orten:

| Ort | Ablage | Bedeutung |
|---|---|---|
| Vorlage | Einstellung `TIMER_PROFILE` (`state.timer_profile`) | Bibliothek des Haupttimers |
| Übung | `exercise.timer_json` (Liste, Migration 020) | gilt überall, erstes Profil = Vorgabe |
| Plan | `plan.timer_json` | „Timer für alle Übungen“ |
| Planübung | `plan_item.timer_json` (`TimerWahl`) | `profil` = ID eines Profils **der Übung**, oder `eigen` = eigene Kopie |

Vorrang (`core.uebung_timer.timer_fuer`): Planübung > Plan > erstes Profil der Übung > keiner.

**Folge für Punkt 3 und 4:** Einen Timer, der „in drei Übungen verwendet wird“, gibt es heute
nicht. „In andere Übung kopieren …“ (`views/alle_timer.py`) und „Vorlage als Kopie“ legen
Kopien an; ändert man eine, bleiben die anderen stehen. Die Seite „Alle“ zeigt zwar „gilt in
…“, aber nur für die Pläne, in denen eine Übung steht — nicht über Übungen hinweg. Zuordnen und
der Dialog „Überall ändern“ setzen also einen **gemeinsamen Timer mit Verweisen** voraus (§4).

**Bedienung.** Dieselbe Frage „welcher Timer gilt wo?“ hat vier verschiedene Oberflächen:

| Wo | Was man sieht | Geltung |
|---|---|---|
| Beim Üben: Uhr-Blatt (`components/uhr_blatt.py`) | Liste zum Antippen, „+ Neuer Timer“ | Für jetzt · In „Plan“ · Übung |
| „Im Plan einstellen“ (`views/plan_einstellen.py`, Bild 1) | „Anderen Timer nur hier …“, „Neuer Timer — nur hier“ | nur Planübung |
| Uhrenplan (`views/plan_uhren.py`, Bild 2) | Name ▾, Zeilen Zeit · Takt · zählt, Chips | nur Planübung, still als Kopie |
| Dialog „Timer in diesem Plan“ (`components/timer_wahl.py`) | Liste | nur Planübung |

Der Editor mit den Reitern Zeiten · Klänge (`views/timer.timer_bearbeiten_view`,
`docs/plan_timer_editor.md`) ist eine eigene Ansicht; die Zeilen im Uhrenplan sind ein zweiter,
kleinerer Editor ohne Klänge, Teile und Namen.

## 2. Stufe Z1 — eine Timer-Zeile, ein Blatt, drei Geltungen

Kein Datenbankschritt.

- **Eine Zeile überall:** `⏱ Name ▾ · Gesamtzeit · Herkunft · ✎` — Herkunft als Chip: „Übung“,
  „Plan“, „nur hier ↺“, „für jetzt“. Sie ersetzt in „Im Plan einstellen“ die Zeile „Timer keiner
  / wie die Übung“ samt den beiden Knöpfen und im Uhrenplan die Kopfzeile der Karte.
- **Ein Blatt:** Der Tipp auf den Namen öffnet überall das **Uhr-Blatt** — oben die Geltung
  **Für jetzt · In „Plan“ · Übung**, darunter die Liste (Stoppuhr, Timer der Übung, Timer des
  Plans, eigene Kopie, aus der Bibliothek, Ohne Uhr), „+ Neuer Timer“ nach der Geltung. Der
  Dialog `timer_wahl.py` entfällt.
- **Vorbelegung der Geltung:** beim Üben wie heute (im Plan „In Plan“, sonst „Übung“); in „Im
  Plan einstellen“ und im Uhrenplan „In Plan“. „Übung“ aus dem Plan heraus schreibt an die
  Übung und sagt das („gilt überall, wo die Übung steht“).
- **„Für jetzt“ aus dem Plan-Editor** (P171): Vorschlag — angeboten, aber nur, wenn man aus
  dem Üben oder dem Workout in den Editor kam; sonst ausgegraut mit dem Satz „gilt erst beim
  Üben“. Wer nur den Plan baut, hat kein „jetzt“.
- **„Uhr beim Üben“ (Wie die Übung · An · Aus)** und **„Zeit zählt“** bleiben, bekommen aber
  dieselbe Geltung wie das Blatt statt des festen „nur hier“.

## 3. Stufe Z2 — der Editor im Fenster

Kein Datenbankschritt.

- **Ein Baustein:** Kopf (Name, Gesamtzeit), Reiter **Zeiten · Klänge**, Zeilen je Abschnitt,
  Teile, Runden werden aus `timer_bearbeiten_view` in eine Komponente gelöst
  (`components/timer_editor.py`). Die Ansicht des Haupttimers ist dann nur noch ihr Rahmen.
- **Im Fenster:** ✎ in der Timer-Zeile klappt den Baustein **an Ort und Stelle** auf — in der
  Karte des Uhrenplans und in „Im Plan einstellen“. Die anderen Karten bleiben sichtbar, der
  Überblick über alle Zeiten des Plans bleibt. Zugeklappt zeigt die Karte je Abschnitt eine
  Zeile „Name · Zeit“ (nur lesen), aufgeklappt den Editor.
- **Klänge:** der Reiter „Klänge“ wie im Haupttimer (spiegelt die Zeiten, gleiche Zeilenhöhen).
- **Speichern:** Der eingebettete Editor gehört zum Formular der Ansicht („Zurück speichert“);
  wohin, sagt die Geltung der Zeile. Ändert man einen Timer der Übung mit Geltung „In Plan“,
  entsteht wie heute die eigene Kopie — aber sichtbar benannt („nur hier ↺“), nicht still.
- **Beim Üben** bleibt ✎ im Uhr-Blatt der Weg in die ganze Ansicht (ein Blatt ist zu klein für
  den Editor).

## 4. Stufe Z3 — Bibliothek mit Zuordnung (Migration 052)

**Ja, eine Schemaänderung — eine kleine.**

- **Tabelle `timer`** (Migration 052): `id`, `profile_id`, `name`, `json` (`TimerProfil`),
  `updated_at`, dazu die Sync-Felder wie überall (`deleted_at`, `origin_device_id`,
  `external_ref`). Die heutigen Vorlagen ziehen in einem Datenschritt aus der Einstellung
  dorthin; ihre IDs bleiben.
- **Verweis statt Kopie:** Ein Eintrag in `exercise.timer_json` ist entweder wie heute ein
  eingebettetes Profil oder `{"ref": "<timer-id>"}`. Ebenso `plan.timer_json` und in der
  Planübung `TimerWahl.profil_id` (darf künftig auch eine Bibliotheks-ID sein). **Keine
  Zuordnungstabelle:** Wo ein Timer gilt, wird wie heute gerechnet
  (`core.uebung_timer.alle_timer`) — sonst gäbe es zwei Wahrheiten.
- **Auflösen im Repo:** `UebungRepo`/`PlanRepo` lösen Verweise beim Laden auf (wie
  `fuer_plan` beim Ablauf); `core/` sieht fertige `TimerProfil` mit dem Vermerk
  `bibliothek_id`. `timer_fuer`, Fokus, Workout und Zeitleiste ändern sich nicht. Ein Verweis
  auf einen gelöschten Timer gilt als „keiner“ — der nächste im Vorrang greift, wie heute bei
  einem gelöschten Profil.
- **Zuordnen** (Einstellungen → Timer → „Alle“): je Timer **„Zuordnen …“** — ein Blatt mit
  Suche, Übungen zum Ankreuzen und darunter Pläne („für alle Übungen“). „gilt in …“ nennt dann
  Übungen und Pläne. Umgekehrt nennt das Uhr-Blatt Bibliotheks-Timer mit „auch in 2 Übungen“.
  Die Gruppen der Seite werden **Bibliothek · Nur an einer Übung · Nur in Plänen**.
- **Aus Kopie wird Verweis:** „In andere Übung kopieren …“ heißt künftig „Zuordnen …“; für
  einen Timer, der nur an einer Übung liegt, gibt es „In die Bibliothek“ (er wird gemeinsam,
  die Übung verweist).
- **Bestand** (P173): keine stille Zusammenlegung. „Alle“ bietet **„Gleiche zusammenlegen …“**
  an, wenn Timer inhaltsgleich sind, und nennt sie vorher.
- **Pakete:** Das Format bleibt. Der Export schreibt einen zugeordneten Timer als eingebettete
  Kopie (`timer[]` wie heute); Timer aus einem Paket bleiben eingebettet und gehören dem
  Paket (Drei-Wege-Abgleich, ein Feld). Einer Paketübung einen Bibliotheks-Timer zuzuordnen
  ist eine eigene Änderung und bleibt beim Update (P175).
- **Ausführung je Abschnitt** (`Abschnitt.ausfuehrung`) gehört zur Übung, nicht zum
  gemeinsamen Timer (P174): Bibliotheks-Timer tragen keine; wer in einem zugeordneten Timer
  eine setzt, bekommt den Dialog aus §5 mit nur einer Antwort („Kopie für diese Übung“).

## 5. Stufe Z4 — „Überall ändern“ oder „Nur hier“

Braucht Z3.

- Beim Speichern eines Timers, der an **mehr als einer Stelle** gilt (gerechnet aus
  `alle_timer`), fragt ein Dialog:

  > **„Dehnen 30/15“ gilt an 3 Stellen** — Planke, Seitstütz, Plan „Morgens“.
  > **Überall ändern** · **Nur hier: Kopie anlegen** · Abbrechen

- **Überall ändern** schreibt den Bibliotheks-Timer. **Nur hier** legt eine Kopie an („Dehnen
  30/15 (Planke)“) — an der Übung, oder in einem Plan als eigene Kopie der Planübung — und löst
  hier den Verweis. Abbrechen lässt den Editor offen.
- Gilt der Timer nur an einer Stelle, fragt nichts. Geändert wurde nichts → kein Dialog.
- Auch **„Zurück speichert“** fragt (wie bei Unvollständigem); „Für jetzt“ fragt nie, es
  speichert nichts.
- **Löschen** nennt wie heute die Stellen; neu: „Nur hier entfernen“ (Zuordnung lösen) neben
  „Überall löschen“.

## 6. Reihenfolge und Prüfung

| Stufe | Inhalt | Schema | Tests |
|---|---|---|---|
| Z1 | Timer-Zeile, Uhr-Blatt überall, Geltungen | – | `test_ui_plan_einstellen`, `test_ui_plan_uhren`, Uhr-Blatt |
| Z2 | `components/timer_editor.py`, eingebettet, Klänge | – | Editor-Tests auf den Baustein umziehen |
| Z3 | Tabelle `timer`, Verweise, Zuordnen, Zusammenlegen | 052 + Datenschritt | Repo, `alle_timer`, Paket-Export/-Import, **voller Lauf** |
| Z4 | Dialog beim Speichern und Löschen | – | Dialog je Ort, Zurück |

Jede Stufe eine Version; Z1 und Z2 sind ohne Z3 nützlich. Gerätetests kommen je Stufe in den
Katalog. Nicht berührt: Vorrang, Takt, Zeitleiste, Workout.
