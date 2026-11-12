# Plan: Verlauf → „Notizen“ statt „Tagebuch“, „Tage“ als Zeitleiste

Stand: 12.11.2026 — **Entwurf, noch nichts gebaut.** Offene Punkte P195–P198 in
`docs/offene_fragen.md`.

> Ben, 12.11.2026: „Der Oberreiter Tagebuch wird zu ‚Notizen‘. In den Notizen gibt es eine
> chronologische Abhandlung von allem, was geschrieben wurde. Mit den Filtern kann man sich da
> durcharbeiten. Wichtig: die Tagesnotizen mit Tagebuch müssen gesondert super schnell
> erreichbar sein. Das wirkliche ‚Tagebuch‘ muss ohne große Umwege erreichbar sein. Weil dann
> die Felder fehlen in der Chronologie, kann man im Hauptreiter Tage die Wochenansicht evtl.
> zu einer Zeitleiste wandeln.“ — Anforderungen: (1) Tagesnotizen, Tagesfelder, Übungen,
> Pläne, Planfelder usw. einsehbar und abrufbar, (2) keine Doppelungen, (3) Tagebuch (Notizen
> mit Tag „Tagebuch“) schnell einsehbar. Dazu: „Es kann passieren, dass für eine Übung öfter
> Dinge notiert werden. Die handgeschriebenen Notizen sollen schnell gefunden werden können
> … die Tagesfelder/Übungsfelder und andere unterscheidbar.“

## 1. Grundsatz: jede Ansicht beantwortet eine Frage

| Ansicht | Frage | Inhalt |
|---|---|---|
| Heute, `/tag/<datum>` | Was mache und schreibe ich an **diesem Tag**? | alles des Tags, bearbeitbar (Übersicht · Zeitleiste) — unverändert |
| Verlauf → **Tage** | Was war **wann**? | Woche, darunter der gewählte Tag **nach der Uhr**: Zahlen (Übungen, Tagesfelder, Workouts), kein Fließtext |
| Verlauf → **Übungen** | Wie entwickelt sich **eine Übung**? | Liste mit Suche und Filter → Kurve, Ergebnisse je Tag, ihre Notizen — unverändert |
| Verlauf → **Zum Tag** | Wie entwickelt sich **ein Tagesfeld**? | Liste → Säulen/Linie, Einträge mit Notiz — unverändert |
| Verlauf → **Notizen** | Was habe ich **geschrieben**? | alles Geschriebene, chronologisch, Suche und Filter; „Tagebuch“ mit einem Tipp |

Zahlen stehen in „Tage“, Text in „Notizen“. Wo beides zusammengehört (die Notiz an einem
Wert), trägt die Zeile in „Tage“ nur ein Notiz-Zeichen, die Karte in „Notizen“ nur den Titel
des Werts („Ibu 400“).

## 2. Reiter „Notizen“ (bisher „Tagebuch“)

**2.1 Eine Liste, keine Segmente.** „Tage · Übungen · Notizen“ entfällt. Die Liste ist immer
fortlaufend nach Tagen (neuester oben, im Tag nach der Uhr) — wie bisher „Tage“, mit
Wochenleiste (ein/aus), „Ältere zeigen“ und „+“ (neue Notiz zu heute).

**2.2 Kopf.** Eine Zeile wie in der Übungsauswahl: Suchfeld, Filterknopf (mit Zahl),
Kalendersymbol, „+“. Darunter **fest** die Schnellwahl, darunter die Labels der wirkenden
Filter (✕ nimmt einen heraus).

**2.3 Schnellwahl „Tagebuch“ (Anforderung 3).** Zwei Chips, immer sichtbar: **Tagebuch** ·
**Alles**. „Tagebuch“ = Notizen zum Tag mit dem festen Tag „Tagebuch“ — ein Tipp, kein Blatt.
Die Wahl bleibt über Reiter- und Ansichtswechsel stehen (wie heute `tagebuch_ordnung`): Wer
zuletzt im Tagebuch war, landet wieder dort. Dazu ein zweiter Weg ohne Umweg über den Verlauf
(P196): unter Heute im Block „Zum Tag“ ein Buch-Symbol → Verlauf → Notizen mit „Tagebuch“.

**2.4 Filterblatt** (Bauart `components/uebungsfilter.py`: Chips je Bereich, wirkt sofort,
Trefferzahl, „Alles leeren“ · „Fertig“):

- **Art:** Zum Tag · Übung · Plan · Workout · Tagesfeld · mit Aufnahmen. Jede Art hat ihr
  Symbol und ihre Label-Farbe — dieselben wie an der Karte, so bleiben Tagesfelder,
  Übungsnotizen und Tagesnotizen auf einen Blick unterscheidbar.
- **Notiz-Tags:** die Tags der Notizen zum Tag, dazu „ohne Tag“ (bisher die Chip-Zeile des
  Segments „Notizen“).
- Innerhalb eines Bereichs oder, zwischen den Bereichen und — wie beim Übungsfilter.

**2.5 Suche.** Jedes Wort muss vorkommen — im Text, im **Titel** (Name der Übung, des Plans,
des Workouts, des Tagesfelds samt Variante) oder in einem Tag. „Kniebeuge“ findet damit alle
Notizen zur Kniebeuge. Die Suche füllt nur die Liste neu (Fokus bleibt), nicht mehr erst auf
Enter.

**2.6 „Alle Notizen hierzu“.** Im Blatt der Wege einer Karte (Zielsymbol, Gedrückthalten) ein
Eintrag „Notizen zu ‚Kniebeuge‘“ → setzt die Suche auf den Namen. Das ersetzt die Ordnung
„nach Übungen“ (P195).

**2.7 Was hineinkommt** (Regel seit 12.11.2026: nur selbst Geschriebenes, unverändert):
Notizen zum Tag, Plan-Notizen, Notizen an Übungseinträgen, Workout-Notizen (Skalen als Zeile
darunter), Texte der Tagesfelder und Notizen an einem Wert, Aufnahmen. Keine Werte ohne Text.

**2.8 Technik.** `core/tagebuch.py`: `nach_uebungen` und `Gruppe` entfallen; `nur_tag` wird zu
`filtern(notizen, arten, tag_ids, suche, titel=)` (Aufnahmen bleiben bei ihrer Notiz wie
bisher, N90). `ui/views/tagebuch.py` → `views/notizen_verlauf.py` (Name `tagebuch` bleibt in
`core/`, damit Importe und Tests nicht ohne Not wandern); `gruppen_block`, `filter_zeile`,
`ordnung_gewaehlt` entfallen. Neue kleine Komponente `components/notizfilter.py` nach dem
Muster der `FilterLeiste` — oder die `FilterLeiste` bekommt frei benennbare Bereiche (P197).
`AppState`: `tagebuch_ordnung` weg, dafür `tagebuch_arten: set[str]`; `tagebuch_tags`,
`tagebuch_suche` bleiben; Profilwechsel leert alle drei. Reiter-Label in `views/verlauf.py`.

## 3. Reiter „Tage“: der Tag nach der Uhr

Heute zeigt „Tage“ unter der Woche zwei Blöcke: „Zum Tag“ (Tagesfelder) und die Übungen, ohne
Uhrzeit. Neu: **eine** Liste des gewählten Tags nach der Uhr, mit Uhrzeit links
(`components/zeitstrahl.zeitpunkt`, wie im bisherigen Tagebuch):

- **Übung:** die Zeile wie bisher (Wert, Sätze, Mini-Kurve; Tipp = Kurve), an der Uhrzeit
  ihres ersten Eintrags; Übungen eines Plans als Block unter dem Plannamen
  (`core.tag.zeitleiste` rechnet das schon für Heute).
- **Tagesfeld:** „einmal am Tag“ oben ohne Uhrzeit, „mehrmals“ an seiner Uhrzeit (gleiche
  hintereinander in einer Zeile, wie in der Zeitleiste unter Heute); Tipp = Feld im Verlauf.
- **Workout:** eine Zeile „Workout Beine · Anstrengung 6“ an seinem Beginn, Tipp = der
  Workout-Eintrag. Das ist der neue Ort für Workouts ohne Notiz, die seit heute nicht mehr im
  Tagebuch stehen.
- **Geschriebenes:** kein Text, nur ein Notiz-Zeichen an der Zeile; Notizen zum Tag als eine
  Zeile „2 Notizen“ → Tipp öffnet Verlauf → Notizen an diesem Tag.
- „Tag öffnen“ bleibt (führt zur bearbeitbaren Tagesansicht).

**Aufwand:** klein. Die Daten liest `_Daten` schon (Einträge, Tageswerte); dazu kommen die
Sessions für die Planblöcke und `EinheitRepo.workout_zeilen`. Gerechnet wird in `core/verlauf.py`
(neue Funktion `tag_nach_uhr`), gezeichnet in `_tage_inhalt`. Keine Migration.

Nicht vorgeschlagen: die Zeitleiste von Heute (`tagesansicht`) in den Verlauf einzubetten —
sie ist die bearbeitbare Ansicht mit Editoren und Gestenfänger; zweimal dieselbe Ansicht wäre
genau die Doppelung, die vermieden werden soll.

## 4. Abdeckung: wo steht was?

| Inhalt | einsehen (ein Tag) | abrufen (über die Zeit) | Text dazu |
|---|---|---|---|
| Notiz zum Tag, Tagebuch | Heute/Tag → „Zum Tag“ | **Notizen** (Schnellwahl „Tagebuch“) | Notizen |
| Tagesfeld: Wert | Heute/Tag; **Tage** (nach der Uhr) | **Zum Tag** → Feld | — |
| Tagesfeld: Text, Notiz am Wert | Heute/Tag (Blatt des Felds) | Zum Tag → Feld (Einträge) | Notizen (Art Tagesfeld) |
| Übung: Werte | Heute/Tag; **Tage** | **Übungen** → Kurve | — |
| Übung: Notiz am Eintrag | Heute/Tag (Leistungen) | Übungen → Ergebnisse je Tag | Notizen (Art Übung, Suche nach Name) |
| Plan: was gemacht wurde | Heute/Tag (Plankarte, Zeitleiste) | **Tage** (Planblock) | — |
| Plan: Notiz zum Training | Heute/Tag | — | Notizen (Art Plan) |
| Workout: Durchlauf, Skalen („Planfelder“) | Workout-Eintrag `/workout/<einheit>` | „Alle Durchläufe“; **Tage** (neu) | Notizen (Art Workout, nur mit Notiz) |
| Aufnahmen (Foto, Video, Audio) | Heute/Tag, an Eintrag oder Notiz | Übung → Aufnahmen im Verlauf | Notizen (Filter „mit Aufnahmen“) |
| HRV-Aufzeichnung, Strecke | Messung → Aufzeichnungen | dort | dort (Notizen der Messung) — nicht im Verlauf, wie bisher (P39) |

**Doppelungen, die wegfallen:** drei Segmente mit denselben Notizen; die Gruppen „nach
Übungen“ (stehen schon in Übungen → Ergebnisse je Tag und Zum Tag → Feld); Wertezeile im
Tagebuch (erledigt 12.11.). **Bleibt bewusst doppelt:** Eine Notiz steht am Tag (zum
Schreiben) und in „Notizen“ (zum Finden) — dieselbe Notiz, zwei Wege.

**Lücken, die der Plan nicht schließt** (zur Entscheidung, P198):

1. **Verlauf eines Plans** über die Zeit (wie oft, welche Übungen) gibt es nirgends — nur je
   Tag. „Tage“ zeigt künftig den Planblock, mehr nicht.
2. **Notizen der Messungen** (HRV, Strecke) stehen nur bei der Aufzeichnung. Sollen sie in
   „Notizen“ erscheinen (Art „Messung“), wäre das eine weitere Quelle in `sammeln` — ohne
   Messwerte, nur Text.
3. **Notizen an Aufnahmen** (Text an einem Foto) erscheinen in „Notizen“ nicht als Text, nur
   das Bild.

## 5. Reihenfolge

1. Reiter „Notizen“: Segmente weg, Kopf mit Suche, Schnellwahl, Filterblatt, Suche im Titel
   (2.1–2.5, 2.8) — Tests: `test_ui_tagebuch.py`, `test_ui_tagesnotiz.py`,
   `test_ui_tagesfelder.py`, `test_ui_workout_eintrag.py`, Doctests `core/tagebuch.py`.
2. „Tage“ nach der Uhr mit Workouts (3) — `test_ui_verlauf.py`, Doctests `core/verlauf.py`.
3. „Notizen zu …“ im Blatt der Wege (2.6) und das Buch-Symbol unter Heute (2.3, nach P196).
4. Web-Fotos der drei Ansichten bei 412 px (Skill `web-fotos`), Gerätetest, Verträge
   (`plan_tagesnotizen.md` Abschnitt E, `plan_tagesfelder.md` F, CLAUDE.md „Zurück speichert“:
   „im Tagebuch der Abschnitt ‚Notizen‘“ → Reiter „Notizen“).

Jeder Schritt ist für sich lauffähig und einzeln zu committen.
