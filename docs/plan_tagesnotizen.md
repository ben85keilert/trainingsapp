# Plan: Notizen zum Tag – mehrere je Tag, mit Tags, im Tagebuch ohne Popup

Stand 2.11.2026: **gebaut** (Migration 036, 0.3.39) nach Bens Antworten vom selben Tag auf
P98–P105 (unten, „Entschieden“). Anlass sind Bens fünf Punkte vom 2.11.2026 zum Textfeld
unter Heute:

> 1) Füge den zum Tag Notizen Tags (Merkmale) hinzu. Feste implementiert ist erstmal
>    „Tagebuch“. Ich möchte meine persönlichen Gedanken ebenfalls hier festhalten und brauche
>    dafür eine bessere Organisation. Gleichzeitig möchte ich spezielles Training, Kraft,
>    Ausdauer, Isometrie … direkt beschreiben können. Tags lassen sich löschen, die Nachricht
>    selbst bleibt dann aber, verliert einfach den Tag. Der Tag Tagebuch lässt sich nicht
>    löschen, aber deaktivieren.
> 2) Die Tagebuchnotizen zum Tag lassen sich fertig stellen und nachbearbeiten, aber es sollen
>    mehrere erstellbar sein mit einem „+“. So können unterschiedliche Notizen zum Tag erstellt
>    werden und später danach gesucht werden.
> 3) In Verlauf Tagebuch sind die Notizen nicht abgeschnitten dargestellt. Das ist umständlich
>    für den Überblick. Gib den Tag-Tagesnotizen die gleiche Größe wie in Heute.
> 4) In Verlauf → Tagebuch gibt es die Reiter Tage und Übungen+Felder. Ich brauche einen
>    dritten Reiter nur für die Tagesnotizen filterbar nach Tags. Die Ansicht dort soll
>    fortlaufend sein, aber mit dem gleichen ein-/ausblendbaren Kalender oben wie in Tage.
> 5) Der Edit von Tagesnotizen in Verlauf ist als Popup unpraktisch/unübersichtlich und
>    ungemütlich. Wie lässt sich das ohne Popup lösen und ggf. die Anhänge wie in der
>    „Heute“-View hinzufügen.

**Lesart** (bitte widersprechen, wenn falsch): „Reiter Tage und Übungen+Felder“ sind die zwei
Abschnitte **im** Reiter Tagebuch (`SegmentedButton` in `ui/views/tagebuch.py`, dazu die
ein-/ausblendbare Wochenleiste). Der Verlauf selbst hat die Reiter Tage · Übungen · Zum Tag ·
Tagebuch; die bleiben. Der dritte Abschnitt „Notizen“ kommt ins Tagebuch.

**Entschieden (Ben, 2.11.2026):** P98 kein Tag vorgewählt. P99 Anhänge an der Notiz
(`entry_media.day_note_id`); eine Notiz darf leer sein, wenn sie Anhänge trägt, ihr leerer
Text wird nirgends gezeigt. P100 zehn Zeilen wie unter Heute. P101 bearbeiten in der Liste,
mit demselben Editor wie auf der Tagesseite. P102 ja — Filter ODER, Aufnahmen dabei, dazu
die Suche („möglichst clever“: jedes Wort muss vorkommen, im Text oder in einem Tag, ohne
Groß und klein). P103 alle Popups für Schreibnotizen weg (`components/notiz.py` gelöscht):
Notiz zum Tag und zum Plan unter Heute und im Tagebuch an Ort und Stelle
(`components/notizeditor.py`, `Textnotiz`). P104 beides bleibt — Ben: „Die Tagebuchtags sind
super speziell und langlebig und sollen abgesichert sein gegen Löschung. Die ‚Zum Tag‘-Notiz-
Tagesfelder könnten als Stapel gelöscht werden, wenn das Feld wieder entfernt wird.“ Darum
zwei Dinge: Ein **Tag** ist ein Etikett am Tagebuchtext, das lange lebt und dessen Löschen
nie Text mitnimmt; ein **Tagesfeld „nur Text“** ist ein Feld mit Einträgen, das mitsamt
seinen Einträgen gelöscht werden darf („Löschen mit allen Einträgen“,
`docs/plan_tagesfelder.md` P69). P105 ja, Suchfeld im Abschnitt „Notizen“.

Abweichungen vom Plan unten beim Bauen: Anhänge hängen an der Notiz, nicht am Tag (A, C);
`Tagesnotiz` ist eine Unterklasse des allgemeinen `Notizeditor`; der Editor in der
Tagebuchliste lebt in `AppState.tagebuch_editor`, die bearbeitete Notiz in
`AppState.tagebuch_bearbeitet` (``tag:<id>``, ``plan:<session>``, ``neu``).

## Was heute gilt

- **Eine Notiz je Profil und Tag** (`day_note`, Migration 003, `UNIQUE (subject_id, date)`),
  veränderlich, „letzter Schreiber gewinnt“. Leer heißt entfernt (`text = ''`).
- Unter Heute und in `/tag/<datum>` schreibt man sie direkt (`components/tagesnotiz.py`):
  Autosave, ↶ ↷, Abbrechen, Fertig; daneben Foto · Video · Audio **am Tag**
  (`entry_media.day`, Migration 029 — Anhänge gehören zum Tag, nicht zur Notiz).
- Das Tagebuch (`core/tagebuch.py`, `ui/views/tagebuch.py`) ist eine Abfrage über die Notizen
  zum Tag, zum Plan und zur Übung, dazu Aufnahmen und Tagesfelder. Die Karte einer Notiz
  zeigt den **ganzen** Text (`ft.Text` ohne `max_lines`); Antippen öffnet den Dialog
  `components/notiz.notiz_dialog` (AlertDialog, 3–8 Zeilen, Abbrechen/Speichern).
- Tags gibt es bisher nur an Übungen (Typ und Region, Tabelle `tag`, global, nicht je Profil;
  Löschen nimmt sie aus den Übungen). **Tagesfelder** (`day_field`, Migration 027) sind Bens
  „Tag-Label“ vom 21.10. mit Wert — ein Feld „nur Text“ („Ernährung“) ist einer getaggten
  Notiz nahe, aber ein Feld, kein Tag am Text (P104).

## Der Begriff

Eine **Notiz zum Tag** ist ein Text mit Uhrzeit (wann angelegt — ihr Anker in der Zeitleiste)
und **Tags**. Je Tag beliebig viele. Ein **Tag** (Merkmal) ist ein frei benanntes Etikett je
Profil: „Tagebuch“, „Kraft“, „Ausdauer“, „Isometrie“, „Gedanken“ … Eine Notiz trägt keinen,
einen oder mehrere Tags. Ein Tag ist **aktiv** (wird beim Schreiben angeboten, steht im Filter),
**ausgeschaltet** (wird nicht mehr angeboten; Notizen behalten ihn, der Filter zeigt ihn weiter)
oder **gelöscht** (die Notizen bleiben und verlieren ihn — Ben, Punkt 1). **„Tagebuch“ ist fest:**
jedes Profil hat ihn, er lässt sich nicht löschen und nicht umbenennen, nur ausschalten.

„Fertig stellen und nachbearbeiten“ (Punkt 2) braucht **keinen** gespeicherten Zustand: Fertig
schließt die Tastatur und klappt die Notiz zur Karte; Antippen der Karte öffnet sie wieder.
Gespeichert ist ohnehin laufend (Autosave). Eine Notiz ohne Text wird beim Fertig/Verlassen
nicht angelegt bzw. gelöscht.

## A. Datenmodell (Migration 036)

- **`day_note` ohne `UNIQUE (subject_id, date)`** — Neubau der Tabelle wie in Migration 029
  (SQLite kann einen Constraint nicht fallen lassen); Zeilen bleiben. Neuer Index
  `(subject_id, date) WHERE deleted_at IS NULL`. Entfernen wird **weich** (`deleted_at`) statt
  `text = ''` — eine Notiz unter mehreren muss verschwinden können.
- **`note_tag`** je Profil: `id`, `subject_id`, `name`, `sort`, `fest` (1 = Tagebuch),
  `active` (0 = ausgeschaltet), `created_at`, `updated_at`, `revision`, `origin_device_id`,
  `deleted_at`; `UNIQUE INDEX (subject_id, name) WHERE deleted_at IS NULL`.
  Veränderlich wie `day_field` („letzter Schreiber gewinnt“).
- **`day_note_tag`** (`note_id` → `day_note` `ON DELETE CASCADE`, `tag_id` → `note_tag`,
  Primärschlüssel beide). Ein gelöschter Tag bleibt verknüpft, aber unsichtbar (Abfragen
  nehmen `note_tag.deleted_at IS NULL`) — die Notiz „verliert einfach den Tag“, und ein
  späteres Wiederherstellen wäre möglich.
- **Bestand:** je vorhandenem Profil ein Tag „Tagebuch“ (`fest = 1`); jede bestehende Notiz
  mit Text bekommt ihn — die eine Notiz je Tag war bisher das Tagebuch. Für neue Profile legt
  `NoteTagRepo.sicherstellen(subject_id)` ihn beim ersten Lesen an (keine Logik im Anlegen
  eines Profils, kein Seed).
- **Warum nicht die Tabelle `tag` der Übungen:** global statt je Profil, Art Typ/Region, und
  Löschen nimmt sie aus den Übungen — genau das Gegenteil von Punkt 1.
- **Anhänge bleiben am Tag** (`entry_media.day`), nicht an der Notiz — Stufe 1 ohne Änderung
  an `entry_media`. Wer ein Foto einer bestimmten Notiz zuordnen will, braucht später eine
  Spalte `day_note_id` (P99).
- Sync-Felder (`revision`, `origin_device_id`, `deleted_at`) wie überall; Export und Backup
  ändern sich nicht (Tagesnotizen sind in keinem Export, `docs/offene_fragen.md` §5).

`core/models.DayNote` bekommt `created_at` und `tag_ids: tuple[str, ...]`; neu `NoteTag`
(`id`, `subject_id`, `name`, `sort`, `fest`, `active`). `DayNoteRepo`:

| heute | neu |
|---|---|
| `lesen(subject, tag) -> str` | `zum_tag(subject, tag) -> list[DayNote]` (nach `created_at`) |
| `setzen(subject, tag, text)` (Upsert je Tag) | `speichern(DayNote)` (Upsert je `id`, inkl. Tags), `loeschen(id)` (weich) |
| `alle(subject) -> (tag, text, created_at)` | `alle(subject, tag_ids=None) -> list[DayNote]` — Filter ODER über die Tags |
| `angelegt(subject, tag)` | entfällt (`DayNote.created_at`) |

`NoteTagRepo`: `alle(subject, mit_ausgeschalteten=False)`, `anlegen(subject, name)`,
`umbenennen`, `umschalten(id, active)`, `loeschen(id)` (weich; „Tagebuch“ wirft einen
`ValueError`), `anzahl_notizen(id)` für die Rückfrage beim Löschen.

## B. Kern (`core/`, ohne Datenbank, ohne Flet)

- `core/tagebuch.Notiz` bekommt `tags: tuple[str, ...]` (Namen, aktive und ausgeschaltete; keine
  gelöschten) und `bezug_id` = `DayNote.id` (bisher `None` bei `TAG`). `sammeln` nimmt
  `list[DayNote]` statt `(tag, text, created_at)`.
- **Reihenfolge im Tag:** bisher „zuerst die Notiz zum Tag, dann nach der Uhr“. Mit Uhrzeit je
  Notiz stehen die Notizen zum Tag **an ihrer Uhrzeit** zwischen den anderen — sonst stünden
  fünf Notizen eines Tags als Block über dem Training, das zwischen ihnen lag. Alte Notizen
  haben `created_at` schon. (In der Zeitleiste unter Heute ist das heute schon so.)
- Neu `nur_tag(notizen, tag_ids)`: Notizen der Art `TAG` (und `AUFNAHME` am Tag, P102), bei
  nicht leerem Filter nur die mit mindestens einem der Tags (ODER). `nach_tagen` darauf ergibt
  den dritten Abschnitt; `zahl_je_tag` daraus die Zahlen der Wochenleiste.
- Konstante `NOTIZ_ZEILEN = 10` an einem Ort (`core/tagebuch.py`), die beide Ansichten
  nehmen: das Feld unter Heute (`max_lines`) und die Karte im Tagebuch (Punkt 3).

## C. Heute und `/tag/<datum>` (Punkt 1 und 2)

- Der Block „Zum Tag“ zeigt statt **des** Feldes **die Notizen des Tags**: jede fertige als
  Karte (Uhrzeit, Tags als kleine Chips, Text bis `NOTIZ_ZEILEN`, Antippen öffnet sie wieder),
  darunter die offene als Editor (das heutige `Tagesnotiz`-Control), unter allem **„+ Notiz“**.
  Ohne Notiz steht gleich der Editor da (wie heute). Es ist höchstens eine Notiz offen.
- **Tags im Editor:** eine Chip-Zeile über dem Feld (`ft.Chip`, angetippt = an) mit den
  aktiven Tags in ihrer Reihenfolge, am Ende „Neuer Tag …“ (kleines Blatt: Name; legt an und
  wählt). Vorgewählt bei einer neuen Notiz: „Tagebuch“, solange er aktiv ist (P98). Ein Tipp
  auf einen Chip speichert sofort (Autosave wie der Text). Ausgeschaltete Tags, die die Notiz
  schon trägt, stehen mit dabei (abwählbar), neue bekommen sie nicht.
- `components/tagesnotiz.Tagesnotiz` wird **eine Notiz** (`notiz_id`), nicht „die des Tags“:
  `SICHERN`-Schlüssel je Notiz (`tagesnotiz:<id>`), `notiz_stand` in `views/tag.py` je Notiz;
  Textverlauf, Autosave, Abbrechen, Fertig, Daneben-Tippen, Scrollen, Gestenfänger bleiben
  wie sie sind (CLAUDE.md, 2.11.2026). „+“ legt ein neues `Tagesnotiz` mit leerem Text an
  und gibt ihm den Fokus; eine leere Notiz wird beim Fertig/Verlassen nicht gespeichert.
- Die Anhang-Leiste (Foto · Video · Audio · Fotoauswahl) steht **einmal** unter den Notizen
  des Tags, nicht je Notiz — Anhänge gehören zum Tag (A). Die Kacheln ebenso.
- **Zeitleiste:** jede Notiz an ihrer Uhrzeit (heute schon `angelegt`), der Editor bzw. „+“
  am Ende wie bisher. `core/tag.py` liefert die Notizen statt des einen Textes.
- **Nachtragen** bleibt unberührt (Übungen); Tagesfelder bleiben im Block „Zum Tag“ darunter.

## D. Tags verwalten (Punkt 1)

- **Einstellungen → „Notiz-Tags“** (neue `ui/views/einstellungen_notiz_tags.py`, Muster
  `einstellungen_tags.py` und `tagesfelder.py`): Liste mit Anzahl der Notizen; anlegen (+),
  antippen = umbenennen, Schalter = aus/ein, Papierkorb = löschen mit Rückfrage „n Notizen
  verlieren den Tag, die Texte bleiben“. „Tagebuch“ ganz oben, ohne Stift und Papierkorb, nur
  mit dem Schalter.
- Reihenfolge: „Tagebuch“, dann nach `sort` (neue oben wie bei Typen, Migration 013) — ohne
  Ziehen; umordnen später, wenn es nötig wird.
- Keine Vorschläge außer „Tagebuch“ (P98): Kraft, Ausdauer, Isometrie legt man selbst an —
  einmal, in der Chip-Zeile beim Schreiben.

## E. Tagebuch (Punkt 3, 4, 5)

**E1. Dritter Abschnitt „Notizen“** (`state.tagebuch_ordnung = "notizen"`, Konstante `NOTIZEN`):
- Segment neben „Tage“ und „Übungen und Felder“. Drei Segmente müssen auf 360 px passen;
  sonst „Übungen · Felder“ kürzen (prüfen im Desktop-Vorschau bei 360 px Breite).
- Darunter die **Filterzeile**: ein Chip je Tag (aktive und ausgeschaltete, wenn Notizen sie
  tragen), Mehrfachwahl = ODER, nichts gewählt = alle; `state.tagebuch_tags: set[str]` (P102).
  Außerdem ein Chip „ohne Tag“ für Notizen ohne Etikett.
- Die Liste ist **fortlaufend wie „Tage“**: Tagesblöcke mit `tag_kopf`, darin nur Notizen zum
  Tag (und die Aufnahmen am Tag), `zeitpunkt` wie heute; „Ältere zeigen“ (`SEITE`), eigener
  Scroll-Merkschlüssel `tagebuch-notizen`.
- **Dieselbe Wochenleiste** wie in „Tage“: `mit_leiste` für `TAGE` **oder** `NOTIZEN`, der
  Knopf `CALENDAR_VIEW_WEEK` sichtbar in beiden; die Zahlen der Zellen aus den gefilterten
  Notizen; Springen, ‹ ›, Mitlaufen beim Scrollen unverändert (`leiste_bauen`, `gescrollt`).

**E2. Kürzen** (Punkt 3): die Karte einer Notiz zum Tag zeigt höchstens `NOTIZ_ZEILEN` (= 10,
wie das Feld unter Heute) mit `TextOverflow.ELLIPSIS` — in „Tage“ und „Notizen“. Mehr gibt
es beim Antippen (E3). P100 fragt, ob 10 Zeilen für den Überblick nicht noch zu viel sind.

**E3. Bearbeiten ohne Popup** (Punkt 5): Antippen einer Notiz zum Tag ersetzt **ihre Karte
in der Liste** durch den Editor von Heute — dasselbe `Tagesnotiz`-Control mit ↶ ↷
Abbrechen Fertig, der Chip-Zeile der Tags und darunter Foto · Video · Audio zum Tag.
- Zustand `state.tagebuch_bearbeitet: str | None` (die Notiz-ID); „Fertig“, Daneben-Tippen und
  Zurück setzen ihn zurück — die Karte kommt wieder. Zurück und Reiterwechsel speichern über
  `AppState.vor_dem_verlassen` wie unter Heute. Nur der Tagesblock baut sich neu, nicht die
  Liste (Scrollposition, Muster `views/plan.auffrischen`).
- Die Anhang-Routen bekommen `basis="/"`: Nach Foto oder Audio landet man wieder im Verlauf,
  weil `state.reiter` und `tagebuch_ordnung` stehen bleiben (im Gerätetest prüfen).
- Der Kopfknopf `EDIT_NOTE` („Notiz zum Tag (heute)“) wird **„+“**: legt eine neue Notiz zu
  heute an und öffnet sie oben in der Liste — in „Tage“ und „Notizen“.
- `notiz_dialog` bleibt für Plan- und Übungsnotizen (P103) und für die Notizen an Anhängen.
- **Ausweichweg**, falls das Einbetten in der Liste am Gerät hakt (Fokus, Tastatur, Scrollen):
  Antippen öffnet `/tag/<datum>` mit der Notiz offen — null neue Oberfläche, nur eine Route
  mit Anker (`?notiz=<id>`).

## F. Sonstiges

- **Suche** (Punkt 2, „später danach gesucht werden“): Stufe 1 ist der Tag-Filter. Eine
  Volltextsuche über alle Notizen (SQLite `LIKE`, bei Bedarf FTS5) ist P105 — als Suchfeld über
  dem Abschnitt „Notizen“ vorbereitet, aber nicht in diesem Plan.
- **Recht:** Tags sind Etiketten, die die Person vergibt; keine Auswertung, kein Hinweis, keine
  Bewertung (`docs/recht/00_zweckbestimmung.md`, wie die Tagesfelder). Nichts Neues.
- **Verlauf → Tage** zeigt keine Notizen zum Tag — bleibt so.
- `AppState`-Kommentar zu `verlauf_tab` berichtigen (Tagebuch ist Reiter 3, nicht 2).

## G. Doku

`docs/datenmodell.md` (day_note ohne UNIQUE, `note_tag`, `day_note_tag`), `CLAUDE.md`
(Absatz zur Notiz zum Tag: mehrere, Tags, im Tagebuch in der Liste), `docs/offene_fragen.md`
(P98–P105, später „Entschieden“), `docs/plan_anhaenge.md` (Anhänge weiter am Tag).

## Tests

- `tests/test_repositories.py`: mehrere Notizen je Tag; weiches Löschen; Tags anlegen,
  umschalten, löschen → die Notiz behält den Text und verliert den Tag; „Tagebuch“ fest;
  `sicherstellen` für ein neues Profil; Migration 036 auf einer Datenbank mit Bestand
  (Notizen bekommen „Tagebuch“).
- `tests/test_core.py` / `test_tagebuch.py`: `sammeln` mit `DayNote`, Reihenfolge nach Uhr,
  `nur_tag` (ODER, „ohne Tag“), `zahl_je_tag`.
- `tests/test_ui_tagesnotiz.py`: zwei Notizen am Tag, „+“, Fertig → Karte, Karte → Editor,
  Chip-Zeile (Vorgabe „Tagebuch“, Chip speichert), leere Notiz wird nicht angelegt,
  `vor_dem_verlassen` je Notiz.
- `tests/test_ui_tagebuch.py`: Abschnitt „Notizen“, Filter, Wochenleiste sichtbar und gezählt,
  Kürzen auf `NOTIZ_ZEILEN`, Bearbeiten in der Liste, „+“ im Kopf; `test_ui_einstellungen.py`
  für die Tag-Verwaltung.
- `tests/test_import_regel.py` läuft ohnehin (kein Flet in `core/`, `data/`).

## Reihenfolge und Aufwand

| Stufe | Teile | Inhalt | Schätzung |
|---|---|---|---|
| 1 | A, B, C | Migration 036, Repos, mehrere Notizen und Tags unter Heute und `/tag/<datum>`, Zeitleiste | 1 Tag |
| 2 | D, E1, E2 | Tag-Verwaltung, Abschnitt „Notizen“ mit Filter und Wochenleiste, Kürzen | ½ Tag |
| 3 | E3, F, G | Bearbeiten in der Liste (oder Ausweichweg), „+“ im Kopf, Doku | ½ Tag |

Jede Stufe ein Commit mit Version; Gerätetest je Stufe (Tastatur und Fokus beim Einbetten in
die Tagebuchliste sind das Risiko — darum der Ausweichweg in E3).

## Offene Fragen (Vorschläge in `docs/offene_fragen.md`)

| # | Frage | Vorschlag |
|---|---|---|
| P98 | Neue Notiz: „Tagebuch“ vorgewählt? Weitere Tags als Vorgabe? | ja, solange aktiv; keine weiteren Vorgaben |
| P99 | Anhänge am Tag (wie heute) oder je Notiz? | am Tag; `day_note_id` später, wenn gewünscht |
| P100 | Kürzen auf 10 Zeilen (wie Heute) oder kürzer? | 10 wie gewünscht; 4–5 wären übersichtlicher |
| P101 | Bearbeiten in der Liste oder die Tagesseite öffnen? | in der Liste; Tagesseite als Ausweichweg |
| P102 | Abschnitt „Notizen“: Filter ODER, Aufnahmen am Tag mit dabei? | ODER; ja |
| P103 | Plan- und Übungsnotizen auch ohne Popup? | später, eigener Punkt |
| P104 | Tagesfeld „nur Text“ neben getaggter Notiz — beides lassen? | ja; keine Umwandlung |
| P105 | Volltextsuche über Notizen? | später (LIKE, ggf. FTS5), Suchfeld über „Notizen“ |
