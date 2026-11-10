# Timer: eine Wahl überall, Editor im Fenster, Bibliothek mit Zuordnung

Stand: 10.11.2026 — **Z1–Z4 gebaut** (Ben, 10.11.: „Baue alles andere so ein, wie in der
Skizze“; P171–P176 damit wie vorgeschlagen entschieden). Skizzen Z1–Z4:
https://claude.ai/artifact/HdxYb75e9kzhX3GFQc1Xxp. Was gebaut ist und wo es von §2–§5 abweicht,
steht in **§7**; Gerätetest T119.

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

## 7. Gebaut (10.11.2026) — und was anders ist als oben

**Ablage (Z3).** Migration 052 legt die Tabelle `timer` an (`TimerRepo` in
`data/repositories.py`); die Einstellung `timer_profile` zieht beim ersten Lesen um und ist
danach weg, die IDs bleiben. `AppState.timer_profile()`/`timer_profile_setzen()` lesen und
schreiben die Tabelle — alle bisherigen Aufrufer bleiben. Ohne eigene Timer gibt es weiter die
zwei Beispiele; sie werden Zeilen, sobald einer zugeordnet wird (`AppState.timer_in_bibliothek`).

**Verweis.** Gespeichert wird `{"ref": "<id>"}` — in `exercise.timer_json` (Listeneintrag), in
`plan.timer_json` und in der Planübung unter `eigen` (nicht, wie in §4 gedacht, als
`profil_id`: so bleibt `timer_fuer` unverändert). Das Repo löst beim Laden auf
(`core.timer.verweise_aufloesen`): `core/` und `ui/` sehen das Profil mit dem Vermerk
`TimerProfil.bibliothek`. Beim Speichern wird aus dem Vermerk wieder der Verweis
(`verweise_schreiben`) — **und was am Profil geändert wurde, kommt dabei in die Bibliothek**
(`_timer_json`). „Überall ändern“ ist also einfach Speichern; „Nur hier“ nimmt vorher den
Vermerk weg (`ui/timer_bibliothek.kopie`). Ein Vermerk, zu dem es keinen Timer gibt (gelöscht,
Paket von einem anderen Gerät), bleibt eine eingebettete Kopie; ein Verweis auf einen gelöschten
Timer gilt als „keiner“. Pakete: `core.timer.ohne_verweise` beim Export (P175).

**Wo er gilt.** `core.uebung_timer.stellen` (Übung · Plan „für alle Übungen“ · einzelne
Planübung), `stellen_text` („gilt in 3 Übungen, 1 Plan“); `alle_timer` nennt einen zugeordneten
Timer einmal, in der Bibliothek.

**„Alle Timer“.** Gruppen Bibliothek · Nur an einer Übung · Nur in Plänen. ⋮: Kopieren ·
**In die Bibliothek** (die Stelle verweist danach; mit Ausführungen stattdessen „Kopie in die
Bibliothek“ ohne sie, P174) · **Zuordnen …** · Löschen („Überall löschen“ nennt die Stellen).
**„Gleiche zusammenlegen …“** erscheint nur, wenn es inhaltsgleiche Timer gibt, nennt sie und
legt erst auf Bestätigung zusammen (`core.uebung_timer.gleiche`, `ui/timer_bibliothek.zusammenlegen`
— Planübungen, die eine der Kopien gewählt hatten, wählen den gemeinsamen).

**Zuordnen — anders als die erste Skizze Z3** (Ben, 10.11.: „gleiche den Filter so an, wie bei
der Übungsauswahl … so kann man jeder Isometrieübung einen Timer direkt zuweisen oder nur jeder
Isometrieübung aus dem Paket ‚Bodentraining‘“): eine **Seite** statt eines Blatts
(`views/timer_zuordnen.py`, Route `…/timer/alle/zuordnen/<id>`) — der Filter ist selbst ein
Blatt, und ein Blatt über einem Blatt habe ich nicht erprobt (die App schließt Dialoge gezielt,
`components/dialoge.schliessen`; zwei offene Blätter gibt es bisher nirgends). Suchzeile mit dem
Filterknopf rechts (`FilterLeiste`: Typ · Region · Paket, Labels darunter,
`AppState.zuordnen_filter`), **„Alle n ankreuzen“** für das, was gerade passt, Übungen und Pläne
zum Ankreuzen, Schalter „Neu zugeordnet wird er die Vorgabe der Übung“ (an: er steht vorn und
gilt, wo nichts anderes eingestellt ist). Geschrieben wird mit „Zuordnen“ oder Zurück.

**Dialog (Z4).** `components/timer_stellen.ueberall_oder_hier`: ab zwei Stellen und nur, wenn
etwas geändert wurde — im Editor der Übung, der Bibliothek („Als Kopie speichern“: eine neue,
nirgends zugeordnete Vorlage) und für einen Timer, der einer einzelnen Planübung zugeordnet ist;
auch bei „Zurück speichert“ (`zurueck_speichert`: ein leerer Grund heißt „selbst gefragt,
bleiben“). „Nur hier“ an der Übung: die Kopie nimmt den Platz ein, Planübungen dieser Übung, die
ihn gewählt hatten, wählen die Kopie. Im Plan geändert (Editor der Planübung) wird ein Timer der
Übung **ohne Frage** die eigene Kopie der Planübung. Löschen an der Übung heißt für einen
zugeordneten Timer „nur hier entfernen“.

**Timer-Zeile und Uhr-Blatt (Z1).** `components/timer_zeile.timer_zeile` in „Im Plan einstellen“
(statt „Anderen Timer nur hier …“ und „Neuer Timer — nur hier“) und in jeder Karte des
Uhrenplans; der Dialog `components/timer_wahl.py` ist entfernt. Das Uhr-Blatt hat im Editor
(`im_editor`) die Zeile „Wie die Übung“ (mit einem Plan-Timer: „Wie der Plan“), keine Stifte
(✎ steht in der Zeile), „Zeit zählt“ und Takt bleiben im Editor; **„Aus der Bibliothek …“
ordnet zu** (vorher „Vorlage als Kopie …“) — auch beim Üben. „Für jetzt“ ist ausgegraut,
solange keine Einheit läuft oder vorbereitet ist (P171, `timer_zeile.jetzt_grund`). In „Im Plan
einstellen“ schreibt „In Plan“ ins Formular (gespeichert mit Speichern oder Zurück), „Übung“
gleich an die Übung. „Uhr beim Üben“ und „Zeit zählt“ haben weiter nur „nur hier ↺“ — die
Geltung dafür bietet das Uhr-Blatt beim Üben (Abweichung von §2, letzter Punkt).

**Editor im Fenster (Z2).** `components/timer_editor.timer_editor` ist der Editor des
Haupttimers als Baustein (Werte, keine Controls); `views/timer.timer_bearbeiten_view` ist sein
Rahmen. `timer_zeile.timer_im_fenster` setzt ihn in die Karte des Uhrenplans und in „Im Plan
einstellen“: Reiter Zeiten · Klänge, Gesamtzeit, darunter **„Geändert gilt:“ Für jetzt · In
„Plan“ · Übung**. Jede Änderung gilt sofort: *In Plan* → eigene Kopie der Planübung („Name
(Plan)“, sichtbar „nur hier“), *Übung* → an die Übung (ein zugeordneter Timer mit mehreren
Stellen fragt beim ersten Ändern einmal), *Für jetzt* → `AppState.uhr_einmal`. Der Name wird im
Fenster nicht geändert (dafür die ganze Ansicht aus „Alle Timer“ bzw. der Übung); ein gemeinsamer
Timer zeigt keine Ausführungen (P174). Zugeklappt steht unter der Zeile der Kurztext der Zeiten.

**Tests.** `tests/test_timer_bibliothek.py` (Umzug, Verweise, Löschen, Export),
`tests/test_ui_timer_zuordnen.py` (Filter + alle ankreuzen, Pläne, Zusammenlegen, Dialog),
`tests/test_ui_plan_uhren.py`, `tests/test_ui_uebung_einstellen.py`.
