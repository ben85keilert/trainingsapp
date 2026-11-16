# Planung: Kurse als Plan-Baukasten (15.11.2026, Durchsicht 16.11.2026)

Bens Auftrag vom 15.11.2026: Die Gestaltung der Kurse überarbeiten — zusammen mit den
Bedingungen in Plänen und Workouts. „Kurse liefern Informationen und Übungsmaterial und können
im Erstellen individueller Pläne helfen. Dabei sind alle Werte, die einen Plan ausmachen, über
die Kurse einstellbar.“ Dazu zwei Fragen: Konflikte (Kursplan existiert schon · Kurs wird noch
einmal durchlaufen) und ob ein **Ablaufeditor wie beim Workout** für Kurse lohnt — auch bei
Verschachtelungen in den Entscheidungen.

**Stand 16.11.2026: Stufe 0 ist gebaut** („Von vorn“ fragt Test und Auswahl neu, §5.2, §7),
**alles andere ist Plan.** Bens Setzung vom 21.10.2026 („Pläne und Kurse nicht ohne Rückfrage
ändern“) gilt: Jede berührte Stelle steht in §9, die Fragen in §10 (Katalog P207). Die
Korrekturen am Workout-Bildschirm aus demselben Auftrag stehen in `plan_uhr_fokus.md` §10, die
Kennzeichnung der Medien und die Animation beim Üben in `plan_medienrollen.md`.

**Durchsicht 16.11.2026** (Ben: „gehe den Plan noch einmal durch“). Für die erste Fassung
waren `plan_verzweigungen.md` und die Zweckbestimmung nur angelesen; jetzt sind beide ganz
gelesen. Das hat fünf Stellen geändert:

| Stelle | Erste Fassung | Jetzt |
|---|---|---|
| §2, Wege | „Der Kurs kann Wege nur ohne Auslöser liefern“ | Eine Vorlage trägt schon einen **ganzen Ablauf** mit Auslösern; nur was die Auswahl erzeugt, ist „frei“ |
| §2.1 (neu) | fehlte — obwohl Bens erster Satz die Bedingungen nennt | Workout und Kurs nebeneinander: dieselbe Logik, zwei Wortlisten |
| §3.3, §8 Recht | „Test bis Anstrengung n wartet auf P204“ | In Solo unter vier Bedingungen erlaubt; offen ist nur der Patientenmodus. Dazu neu: Antworten, die lenken |
| §6 Wiederverwendung | „Das Bild zeichnet aus Lage und Kante“ | Die Zeichnung ist an Planübungen gebunden — der Knoten-Darsteller muss heraus |
| §6 Aufwand | unausgesprochen „groß“ | Der Workout-Editor entstand in einer Sitzung; teuer waren drei Korrekturrunden am Gerät |

**Bens Antworten, 16.11.2026** (Fragen aus §10) — das Grundmodell ist bestätigt:

| Frage | Antwort | Folge im Plan |
|---|---|---|
| 1 Kursplan wächst | „Ja“ | §3.1 gilt |
| 2 Kurs noch einmal durchlaufen | „Ja“ | §5.2 gilt; Stufe 0 ist baubar |
| 3 Antworten speichern, Folgen | „Ja, aber ohne ‚Kurs deutet die Antwort nicht‘. Das ist übertrieben.“ | die Regel ist aus §8 gestrichen |
| 4 Test nach Anstrengung | „Lege die Idee vom Patientenmodus erst einmal auf Eis. Das wird nicht weiter verfolgt. Wir bleiben erst einmal in einer einzigen Edition, ausgelegt auf User, die alleine oder mit Anleitung üben wollen — keine Unterscheidung zwischen zwei Editionen im Moment.“ | §3.3, §7: kein Vorbehalt für einen Patientenmodus mehr. Zur Lesart von „30 Wiederholungen vorher getestet“ am selben Tag: „Anstrengung kann Menge, Zeit, Skala sein. Skala kann ab, bis oder dazwischen sein.“ → §3.3: ein Test mit **einer Vorgabe** (Menge · Zeit · Skala ab/bis/dazwischen), die anderen Größen werden gemessen |
| 5 Kursbild | „Ja, im Kursedit alles anzeigen lassen. Im laufenden Kurs nur den Teil einblenden, der gerade aktiv ist.“ | §6: zwei Sichten |
| 6 hart/weich | „Genau, der Charakter der Übung ist Eigenverantwortung. Man soll auch jederzeit hin und her wechseln können.“ | §2.1 Nr. 1 entschieden; das Umschalten **im laufenden Workout** ist gebaut (`plan_uhr_fokus.md` §10.5, §10.6) |
| 6b Tor als Kapitel-Auslöser | nach der Erklärung: „Der Haken ist gut. Man kann überspringen, muss das aber jedes Mal separat machen. Das motiviert zum Lösen der Aufgabe. Ja“ | §2.1 Nr. 3 gilt; Stufe 5 |
| 7 laufender Kurs | „Bleibt sichtbar; man soll alte Inhalte anschauen können“ | §6 „Zwei Sichten“: Der gegangene Weg bleibt in der Kapitelliste, und seine Kapitel lassen sich wieder öffnen |
| 8 Bauen | „Fang an, und arbeite dich soweit wie möglich durch, bis du gegenfragen musst“ | **Stufe 0 gebaut** (§7); vor Stufe 1 braucht es die Skizzen |

Gelesen: `plan_kurse.md`, `plan_kurseditor.md`, `plan_verzweigungen.md`,
`docs/recht/00_zweckbestimmung.md`, `plan_planblock.md` §B/§C (alle ganz),
`.claude/rules/ablauf_workout.md`, `core/kursbloecke.py`, `core/kurse.py` (Vorlage, Kurs),
`data/kurse.py` (Erreichen, Anlegen, Zurücksetzen), `core/ablauf.py` (Kanten, Prüfung, Struktur),
Kopf und Signaturen von `ui/components/ablaufbild.py`.

---

## 1. Zielbild

Ein Kurs erklärt **und baut mit der Person Schritt für Schritt ihren Plan**. Jedes Kapitel kann
am Plan etwas ändern, und jede Änderung bestätigt die Person mit einem Tipp (Ben, 12.11.2026:
„die Änderung muss geklickt werden“).

Bens Beispiel, damit die Begriffe stimmen:

| Kapitel | Was die Person sieht | Was am Plan geschieht (nach Tipp) |
|---|---|---|
| 1 | Text, Video; „Übung A, 60 Sekunden“ | A kommt in den Plan, Ziel 60 s |
| 2 | Text; **3 Übungen zur Auswahl**; Übung D wird vorher **getestet** (30 Wiederholungen) | die gewählte Übung (z. B. D) wird **hinter A** angehängt; der Test setzt ihr Ziel; die Verbindung A → D bekommt ihren Auslöser (hart/weich) |
| je nach Wahl | **anderes Medium** (Video zu D, nicht zu E) | — |

Was ein Kapitel am Plan einstellen darf, ist **alles, was der Plan-Editor kennt**: Übungen und
ihre Reihenfolge, Ziel, Parameter, Timer (Runden, Klänge), Takt, Wege mit Auslöser, hart oder
weich, Pflicht (§3.2).

## 2. Was es gibt und was fehlt

| Wunsch | Bestand (Fundstelle) | Lücke |
|---|---|---|
| Übungen zur Auswahl | `auswahl`-Block (`core/kursbloecke.py:276` `vorlage_anwenden`) | Die Gewählten kommen in den Plan **desselben Kapitels**, hinter eine Position; ein Plan aus einem früheren Kapitel ist nicht erreichbar — jedes Kapitel legt eigene Pläne an und deaktiviert sie beim Abschluss (`plan_kurse.md` §2, `data/kurse.py:373-374`) |
| Wege mit Bedingungen | Die Plan-Vorlage eines Kapitels kann einen **ganzen gezeichneten Ablauf** tragen — Auslöser, Pflicht, „von selbst“, Fragen (`PlanVorlage.ablauf`, `core/kurse.py:362-364`; `plan_verzweigungen.md` §8.7 G4: „Kurse frei Haus“) | Nur was die **Auswahl** erzeugt, ist immer „frei“ (`_wege`, `kursbloecke.py:338`). Hat die Vorlage schon einen Ablauf, kommen die Gewählten ans Ende und werden **nicht verbunden** (`:326-327`) |
| Ziel durch Test | `test`-Block: jüngster Eintrag, bei Sätzen der beste, × Faktor (`wert_im_test`, `ziel_aus_test`) | nur „wie viel schaffst du“; nicht „bis Anstrengung 7“ |
| Timer, Übergang | der Plan-Editor kann sie | `VorlageItem` hat Ziel, Felder, Sensor, Takt, Bedingung, Beiname, Beschreibung, Medien (`core/kurse.py:144-166`) — **keinen Timer, keine Chips**; `PlanVorlage` hat Name, Wochentage, Übungen, Ablauf, Anpassung (`:356-367`) — **keinen Plan-Timer, kein hart/weich, keine „Pause ohne Timer“**. Der Rest von B2 aus `plan_kurseditor.md` §5; `eigenes_uebernehmen` schützt genau diese Felder, „weil die Vorlage sie nicht kennt“ (`data/kurse.py:445`) |
| Antwort lenkt etwas | `frage`-Block „**erklärt, prüft nicht**: nichts wird gespeichert“ (`kursbloecke.py:8-9`) | Antworten bleiben ohne Folge |
| Medium je Wahl | — | fehlt |
| Wege zwischen Kapiteln | Kapitel linear, eine Bedingung je Kapitel (`plan_kurse.md` §1, §4) | fehlt |

### 2.1 Bedingungen: dieselbe Logik, zwei Wortlisten

Ben: „Das geht zusammen mit der Präzisierung der Bedingungen in Plänen/Workouts, um im Ablauf
weiterzukommen.“ Und am 12.11.2026 (Katalog P200): „Kurse und Pläne (Workouts) angleichen,
damit sich Kurse leichter bauen lassen?“ Nebeneinander gelegt:

| | Workout (`core/ablauf.py`) | Kurs (`core/kurse.py`) |
|---|---|---|
| Knoten | Planübung · Frage (Skala) | Kapitel · Frage-Block (ohne Folge) |
| Auslöser | frei · Zeit ab · Wdh. · Wdh. in einer Zeit · Skala n–m — **innerhalb eines Durchlaufs** | gelesen · summe · tage · messung — **über Tage** |
| streng | **Pflicht** am Weg: sperrt die anderen Wege | Freischaltung `streng`: kein Überspringen |
| nachgiebig | **weich**: auch unerfüllte Wege wählbar, nie gegen eine Pflicht | `rueckfrage`: „Trotzdem freischalten“; `frei`: alles offen |
| von selbst | „von selbst“: hart sofort, weich erst bei Zeit ab | — (immer „Weiter“) |
| dauerhaft offen | **Tor**: einmal mit erfüllter Pflicht verlassen → in der Liste frei, „wie bei einem Kurs“ (`plan_verzweigungen.md` §8.10) | Kapitel erreicht / abgeschlossen (`course_progress`) |
| mehrere Wege | erst fragen (`wahl_offen`) | — |
| noch einmal | Schleife · ◀ zurück · „Fortsetzen“ · Durchlauf | „Von vorn beginnen“ (§5.2) |

Drei Präzisierungen folgen daraus:

1. **„Hart oder weich“ meint drei verschiedene Dinge.** (a) Der **Übergang des Workouts**, den
   die Person **am Start für heute** wählt („Heute: Hart | Weich“, `ui/views/workout.py:212-215`,
   `:314-321`; Vorgabe aus `plan.weiter_automatisch`). (b) Die **Pflicht** je Weg. (c) **Von
   selbst** je Weg. Ein Kurs kann (b) und (c) schon heute über den Ablauf der Vorlage setzen,
   (a) nicht. **Entschieden (Ben, 16.11.2026):** Der Kurs setzt für (a) nur die **Vorgabe** —
   „der Charakter der Übung ist Eigenverantwortung. Man soll auch jederzeit hin und her
   wechseln können.“ Heute geht der Wechsel nur vor dem Start (der Baustein bekommt den Übergang
   beim Anlegen, `devices/plan_ablauf.py:100-130`); das Umschalten im Lauf steht in
   `plan_uhr_fokus.md` §10.5. Die Pflicht an einem Weg bleibt, was sie ist; wer trotzdem weiter
   will, überspringt — das öffnet kein Tor (`pflicht_offen`, `data/einheiten.py:347-360`).
2. **Ein Wortschatz für beide.** „Auslöser“, „Pflicht“, „von selbst“, „erst fragen“ heißen im
   Kurs genauso; neu sind dort nur die Auslöser über Tage. `streng · rueckfrage · frei` wird
   die Vorgabe für die Pflicht aller Kapitel-Wege — kein zweiter Mechanismus daneben.
3. **Die Brücke gibt es schon: das Tor.** Eine Kapitel-Bedingung „Summe ≥ 100“ und ein Tor
   „Pflicht: Skala ≥ 5“ unterscheiden sich nur im Zeitmaß. Ein wachsender Kursplan (§3.1) kann
   den Fortschritt darum **aus dem Plan lesen** — neuer Kapitel-Auslöser „Tor der Planübung X
   ist offen“ (`EinheitRepo.tore_offen`) — statt daneben eine zweite Zählung zu führen. Er
   rechnet aus `plan/kante`-Ereignissen, also aus Zeit, Wiederholungen und Selbstauskunft,
   nie aus einem Messwert.

## 3. Bausteine am Plan

### 3.1 Der Kursplan wächst (Entscheidung W)

Heute: ein Kapitel = eigene Pläne (**Kapitelplan**). Bens Beispiel („D wird an A angehängt“)
braucht **einen Plan, der über die Kapitel wächst**.

Vorschlag: ein Schalter am Kurs, `plan = kapitel` (Bestand, bleibt Vorgabe — bestehende Kurse
ändern sich nicht) oder `plan = wachsend`:

- Ein **Kursplan je Profil**; seine Herkunft ist der Kurs (neue Spalte `plan.course_id`), nicht
  das Kapitel.
- Jede Planübung und jeder Weg, den ein Baustein erzeugt, trägt eine **Marke** (ID des
  Bausteins). Anker („hinter A“) sind Marken, nie Positionen — löscht die Person A, fällt ein
  Baustein ans Ende und sagt es (nie Fehler, nie still; wie `_ziel` im Workout „durch einen
  fehlenden Knoten hindurch“, `devices/plan_ablauf.py:343`).
- Der Abschluss eines Kapitels deaktiviert den Plan **nicht**; am Ende des Kurses fragt die App,
  ob der Plan aktiv bleibt.

### 3.2 Bausteine

Neue Blockarten neben `text · medium · frage · test · auswahl` (`core/kursbloecke.py:33-37`).
Jeder Baustein, der den Plan ändert, ist **eine Zeile in einer Sammelkarte** „Das ändert sich an
deinem Plan“ — einzeln abwählbar, ein Tipp „Übernehmen“. Nichts ändert sich von selbst.

| Baustein | Tut am Plan | Wer legt fest |
|---|---|---|
| `plan_uebung` | Planübung dazu, hinter Marke X, mit Ziel/Feldern | Autor |
| `auswahl` (Bestand, erweitert) | n aus m, hinter Marke X; verbunden als Reihe oder als Wege **mit Auslöser** — auch in einem Plan, der schon einen Ablauf hat | Person wählt |
| `test` (Bestand, erweitert) | siehe §3.3 → Ziel | Person bestätigt den Wert |
| `plan_einstellen` | Timer (als **Verweis** auf die Timer-Bibliothek, `{"ref": …}`), Klang, Takt, Ziel, Parameter, Pause ohne Timer; Übergang hart/weich als **Vorgabe** (§2.1 Nr. 1); **welche Animation die Vorgabe ist** (Ben, 16.11.2026: „Kann von Kurs auch geändert werden im Plan, darauf muss es Zugriff geben, damit man eine Bewegung entwickeln kann“ — `plan_medienrollen.md` §3.3) | Autor |
| `plan_weg` | Weg zwischen zwei Marken: Auslöser (frei · Zeit ab · Wdh. · Wdh. in Zeit · Skala ≥ n bis m), Pflicht, „von selbst“ | Autor |

`VorlageItem` und `PlanVorlage` brauchen dafür die fehlenden Felder (Timer, Plan-Timer,
Übergang, Pause ohne Timer; Chips und Notiz je Planübung) — das ist der Rest von **B2** aus
`plan_kurseditor.md` und wird dort mit gelöst, nicht doppelt.

### 3.3 Tests: eine Größe ist vorgegeben, die anderen werden gemessen

Ben, 16.11.2026: „Anstrengung kann Menge, Zeit, Skala sein. Skala kann ab, bis oder dazwischen
sein.“ Damit ist ein Test nicht mehr eine von zwei Arten, sondern **ein Lauf der Übung im
Fokus mit einer Vorgabe** — in demselben Wortschatz wie die Wege im Workout (`core.ablauf.Kante`:
Wdh., Zeit ab, Skala n bis m):

| Vorgabe des Tests | Der Lauf endet, wenn … | Gemessen wird | Beispiel |
|---|---|---|---|
| **Menge** | n Wiederholungen gemacht sind | Zeit, Anstrengung | „30 Wiederholungen — wie lange, wie anstrengend?“ |
| **Zeit** | die Zeit ab ist | Wiederholungen, Anstrengung | „60 Sekunden halten — wie anstrengend?“ |
| **Skala ab n** | die Anstrengung n erreicht | Wiederholungen, Zeit | „bis es bei 7 liegt — wie viele?“ |
| **Skala bis m** | die Anstrengung über m ginge | Wiederholungen, Zeit | „solange es höchstens 4 ist“ |
| **Skala von n bis m** | die Anstrengung den Bereich verlässt | Wiederholungen, Zeit im Bereich | „bleib zwischen 5 und 7“ |
| *ohne Vorgabe* (Bestand `bestwert`) | die Person aufhört | bester Satz aus dem jüngsten Eintrag | „wie viel schaffst du?“ |

Aus dem Gemessenen wird das **Ziel im Plan** (× Faktor), mit „Als Ziel übernehmen“ — eine Zeile
der Sammelkarte (§3.2). Bens Beispiel „D mit 30 Wiederholungen vorher getestet“ ist die erste
Zeile.

Gebaut wird auf dem, was die Zeitleiste schon trägt: `person/skala`, `person/wdh` und
`core.bedingung.Stand(zeit_ab, gelaufen_s, wdh, skala, wdh_bei)`; die Prüfung der Vorgabe ist
`core.ablauf.kante_pruefen`. Der Rechenkern kommt nach `core/kursbloecke.py`, flet-frei.

**Rechtlich** (Zweckbestimmung ganz gelesen): Der Test ist derselbe Fall wie der „Vorschlag
nach der Belastung“ (`docs/recht/00_zweckbestimmung.md`, Z. 100–112) und in Solo unter dessen
vier Bedingungen erlaubt:

- Grundlage ist nur die **Selbstauskunft**, nie Puls oder HRV;
- die App **nennt die Regel** der Autorin und **deutet die Zahl nicht** („zu schwer“,
  „überlastet“ kommen nicht vor);
- geändert wird nur auf Tipp;
- abschaltbar.

Der Vorbehalt für einen Patientenmodus (Z. 107–110, Katalog P204) ist **keine Baubedingung
mehr**: Ben, 16.11.2026 — der Patientenmodus liegt auf Eis, es bleibt bei einer Edition. Die
vier Bedingungen oben gelten.

## 4. Fragen, Antworten, Folgen · Medien je Auswahl

Ben: „Fragen liefern Antworten, die unterschiedliches zulassen können, aber nicht müssen.“

- Jede **Antwort** darf **Folgen** tragen, keine ist Pflicht. Eine Antwort ohne Folge tut nichts;
  der Kurs geht weiter wie sonst. Folgen: ① `zeige` — Blöcke einblenden (Text, Medium) ② `baustein`
  — einen Plan-Baustein dieses Kapitels anbieten ③ `weg` — das nächste Kapitel (§6).
- **Ein** Mechanismus für „anderes Medium je Wahl“: **`zeigen_wenn`** an jedem Block —
  „Antwort n der Frage F“, „Übung U gewählt in Auswahl A“, „Testwert ab w“. Mehrere Bedingungen
  verketten sich; eine Entscheidung in einer Entscheidung ist so nur eine Kette von
  `zeigen_wenn`, **kein neuer Knoten**.
- **Antworten werden gespeichert** (bisher nichts): Selbstauskunft der Person, nie ein Messwert,
  nur auf dem Gerät (wie „gesehen“ bei Material — Setzung 12.11.2026, im Katalog P200; nicht in
  Paket, Export oder Sync). Tabelle `course_answer(subject, course, block, antwort, am)`.
- Die Frage heißt weiter „erklärt, prüft nicht“ — `richtig` und `hinweis` bleiben; eine Folge
  ist eine **Wahl der Person**, keine Bewertung.

## 5. Konflikte

Bens zwei Fälle — und was der Code heute tut (Fundstellen in Klammern):

### 5.1 Der Kurs hat schon einen Plan

| Fall | Heute | Vorschlag |
|---|---|---|
| Kapitel wird erneut erreicht / „Plan anlegen“ ein zweites Mal | Vorhandene Pläne werden reaktiviert bzw. zurückgegeben (`data/kurse.py:284-296`, `:316-318`) — gut, **kein Duplikat** | bleibt; „anlegen“ ist idempotent **innerhalb eines Durchlaufs** |
| Die Person hat den Kursplan geändert, ein späteres Kapitel will dasselbe ändern | gibt es nicht (Kapitelpläne sind unabhängig) | **Drei-Wege-Abgleich wie bei Paketen** (`plan_abgleichen`, `eigenes_uebernehmen`; `data/kurse.py:429-446`): Was die Person geändert hat, bleibt; kollidiert ein Baustein, zeigt die Karte „Dein Plan weicht ab: X statt Y — Vorschlag übernehmen · so lassen“ |
| Anker fehlt (Person hat A gelöscht) | — | ans Ende + sichtbarer Hinweis (§3.1) |
| Ein eigener Plan heißt wie der Kursplan | Zuordnung über den **Namen**, dann die Reihenfolge (`_kapitel_zuordnen`, `data/kurse.py:484`); bricht nach Umbenennen (B3 in `plan_kurseditor.md`) | Herkunft über Spalte + Marke, nie über den Namen; ein fremder Plan gleichen Namens wird nie überschrieben |
| Zwei Kurse wollen in denselben Plan | — | nein: Ein Plan gehört höchstens einem Kurs; der zweite legt seinen an |
| Paket-Update ändert Kapitel mitten im Kurs | `kurs_neu_laden` (hart/weich) | bleibt der **einzige** Weg; nie stilles Nachziehen |

### 5.2 Der Kurs wird noch einmal durchlaufen — **Befund, behoben am 16.11.2026**

**Gebaut wie unten vorgeschlagen** (Migration 063): `KursRepo.zuruecksetzen` markiert den Plan
eines Kapitels mit Test/Auswahl als früheren Durchlauf und benennt ihn um
(`core.kurse.durchlauf_name`); `kapitel_plaene` und `_kapitel_zuordnen` übergehen ihn;
`fruehere_plaene` und `letzte_wahl` lesen ihn; die Kapitelansicht bietet „Wie beim letzten Mal“
an und listet frühere Durchläufe; der Plan-Editor nennt die Herkunft „… · früherer Durchlauf“
ohne „Neu laden …“; `trainingsapp-paket uebernehmen` übergeht ihn. Die Nummer zählt je Kurs
(nicht je Kapitel), damit alle Pläne eines Durchlaufs dieselbe tragen. Was folgt, ist der Befund
und der Vorschlag, wie sie vor dem Bau standen.

Am 15.11.2026 mit einer Wegwerf-Probe nachgestellt (Kapitel mit `test` + `auswahl`, Durchlauf 1
wählt c und Testwert 20, „Von vorn“, Durchlauf 2 wählt d und Testwert 50):

```
nach Von vorn, Plan aktiv:        [False]       ← deaktiviert, nicht gelöscht
Run 2 nach starten:               1 Plan, aktiv, mit Wahl c   ← kapitel_erreichen reaktiviert ihn
Run 2 plaene_anlegen (d / 50):    d drin: False · c drin: True · 1 Plan
```

`zuruecksetzen` (`data/kurse.py:380`) deaktiviert die Kapitelpläne, `kapitel_erreichen` holt sie
wieder, `plaene_anlegen` gibt die vorhandenen zurück, und die Oberfläche zeigt wegen
`angelegt = bool(kapitel_plaene(…))` (`ui/views/kurse.py:478`) kein „Plan anlegen“ mehr. **Die neue
Wahl und der neue Test gelten nie** — Durchlauf 2 läuft still mit Plan und Ziel von Durchlauf 1.
`plan_kurse.md` §7 behauptet das Gegenteil („Die Auswahl ist fest, bis man den Kurs von vorn
beginnt“). Die Probe liegt nicht im Repo; mit dem Fix wird sie ein Test in `tests/test_kurse.py`.

Dagegen steht Bens Entscheidung vom 15.10.2026 (`plan_kurse.md` §2): „Von vorn beginnen“
deaktiviert, und „ein neuer Start aktiviert dieselben Pläne wieder (kein Duplikat)“. Sie war für
Kapitel ohne Test und Auswahl gedacht und bleibt dort richtig.

**Vorschlag (Frage 2):** Nur Kapitel **mit `test`/`auswahl`** (`Kapitel.braucht_eingabe`)
behandeln den alten Plan als **Durchlauf, der zu Ende ging**:

- Beim „Von vorn“ wird ihr Plan **archiviert**: bleibt deaktiviert und unverändert in der
  Planverwaltung, heißt „‹Name› · Durchlauf 1“ und bekommt die **Marke „Durchlauf beendet“**
  (neue Spalte am Plan, Zeitstempel). Die Kapitelherkunft **bleibt** — sonst ließe sich weder
  „Wie beim letzten Mal“ noch die Nummer des Durchlaufs finden (die erste Fassung wollte
  `course_chapter_id` leeren; das hätte beides abgeschnitten). `kapitel_plaene` und
  `_kapitel_zuordnen` übergehen markierte Pläne. Die Einträge bleiben am Plan; das Ziel „damals
  60 s, jetzt 75 s“ bleibt vergleichbar.
- Das Kapitel fragt Test und Auswahl **neu**; ein Knopf „Wie beim letzten Mal“ belegt die
  Auswahl vor (die Person bestätigt trotzdem).
- Kapitel ohne Test/Auswahl bleiben wie in §2 von `plan_kurse.md`.
- Das ist eine **Migration** (eine Spalte) — danach der volle Testlauf lokal (CLAUDE.md, „Wann
  welche Tests“).
- Der Zähler „Durchlauf n“ kommt aus der Zahl der archivierten Pläne; eine eigene Tabelle
  `course_run` erst, wenn die Antworten je Durchlauf aufbewahrt werden sollen (dafür müsste
  `course_progress.UNIQUE(subject_id, chapter_id)`, benutzt in `data/kurse.py:369`, um die
  Durchlaufnummer erweitert werden — Tabellenneubau in SQLite).

## 6. Ablaufeditor für Kurse — lohnt er? Und bei Verschachtelungen?

**Empfehlung: ja — die Logik ist dieselbe (§2.1) —, aber als dritter Schritt und zuerst nur
als Bild.**

Warum nicht sofort:

- Im Workout **geht die Person durch den Graphen, in Echtzeit**, und muss sehen, wo sie ist. Im
  Kurs liest sie Kapitel für Kapitel; der Graph ist ein **Werkzeug des Autors**.
- Heute gibt es auf Kurs-Ebene gar keine Verzweigung (Kapitel linear, `core.kurse.naechstes`).
  Ein Bild für etwas, das es nicht gibt, hilft nicht.
- Der Plan zeigt seine eigene Verzweigung schon im Ablaufbild des Plans (Auswahl → Wege).

**Was sich wiederverwenden lässt** (nach `plan_verzweigungen.md` §8 und dem Code):

- die **Rechnung** — `core/ablauf.py` kennt nur Knoten-IDs (`Kante.von/nach`, `layout`,
  `erreichbar`, `hauptpfad`, `warnungen`, `wahl_offen`) — und die **Geometrie**
  (`core/ablauf_geometrie.py`: Stamm, Abzweig, Griffe, Gassen);
- die **Bedienregeln**, die sich am Gerät bewährt haben: **keine freien Positionen**, gezogen
  wird nur in Slots, Wege entstehen über „Routing ▾“, nicht durch Ziehen einer Linie (§8.2,
  §8.8; V5 „Kanten ziehen — bewusst nicht“).

**Was Umbau braucht:**

- die **Auslöser**: `Zeit ab`, `Wdh.`, `Skala` sind Workout-Begriffe (`core/ablauf.py:72-127`);
  der Kurs braucht `gelesen · summe · tage · messung · antwort · test · tor` — also eine
  gemeinsame Graph-Schicht mit zwei Auslösersätzen, kein Kopieren;
- die **Zeichnung**: `zeichnung(state, ablauf, items: Sequence[PlanItem], katalog:
  Mapping[str, Exercise], …)` (`ui/components/ablaufbild.py:119-123`) ist an Planübungen und
  Übungen gebunden. Für Kapitel muss der Knoten-Darsteller (Bild, Nummer, Beiname) herausgelöst
  werden.

**Zum Aufwand:** Der Workout-Editor (G1–G4) entstand in **einer** Sitzung (8.11.2026). Danach
brauchte er **drei Korrekturrunden am Gerät** (§8.8, §8.9, §8.11 in `plan_verzweigungen.md`).
Teuer ist nicht der erste Bau, sondern das Einschleifen — ein Grund mehr, erst zu zeichnen, wenn
es etwas zu zeichnen gibt.

### Verschachtelte Entscheidungen — wie das Bild klein bleibt

Eine Entscheidung gehört in genau **eine** von drei Stufen; nur die dritte braucht einen Graphen:

| Die Entscheidung ändert … | Sie ist … | Bild |
|---|---|---|
| nur, **was angezeigt wird** (Medium, Text) | `zeigen_wenn` am Block (§4) | keins |
| den **Plan** (welche Übung, welches Ziel, welcher Weg im Plan) | ein Baustein mit Bedingung | das Ablaufbild des **Plans** (gibt es) |
| die **Folge der Kapitel** | eine Kante im Kursbild | **Kursbild** |

Dazu vier Regeln, damit es nicht zum Baum wird:

1. **Zusammenführen statt verdoppeln:** Zweige münden wieder in ein gemeinsames Kapitel (Raute,
   kein Baum). Was sich danach unterscheidet, löst `zeigen_wenn` — **Antworten gelten für den
   ganzen Kurs**, ein späteres Kapitel darf auf eine frühere Wahl schauen.
2. **Höchstens zwei Ebenen im Bild:** Kursebene (Kapitel) und — nur im Plan — die Wege. Ein
   Zweig aus mehreren Kapiteln darf zu **einem** Knoten „Zweig ‹Name› (4 Kapitel)“ einklappen
   (Tipp öffnet ihn); tiefer nicht.
3. **Mehrere gleichwertige Wege: erst fragen** — wie im Workout (`core.ablauf.wahl_offen`,
   Ben 9.11.2026). Eine Antwort ohne Kante nimmt den Standardweg (Kapitel darunter).
4. **Prüfung beim Bauen** wie `core.ablauf.warnungen`: Kapitel nicht erreichbar · Kreis ohne
   Ausweg · Antwort verweist auf ein gelöschtes Kapitel · `zeigen_wenn` zeigt auf eine Frage
   hinter dem Block. Dazu **„Als Teilnehmer ansehen“**: Der Autor wählt Antworten durch und sieht
   den Pfad („Pfad abspielen“ aus dem Workout-Editor als Vorbild).

Staffelung: **K1** Liste mit „Wenn …“-Zeilen und Pfad-Vorschau · **K2** Kursbild **lesend**
(aus den Folgen gezeichnet, Tipp → Kapitel bearbeiten) · **K3** Kursbild **zeichnen** — wenn
ein eigener Kurs ≥ 2 Verzweigungen hat und die Liste nicht mehr trägt. Die Entscheidung über K3
fällt nach K2 an Bens echten Kursen.

### Zwei Sichten (Ben, 16.11.2026)

„Im Kursedit alles anzeigen lassen. Im laufenden Kurs nur den Teil einblenden, der gerade aktiv
ist.“

- **Kurs-Editor** (`ui/views/kurs_bearbeiten.py`): das ganze Bild — jeder Zweig, jede Bedingung,
  jede Folge einer Antwort; dazu „Als Teilnehmer ansehen“. K2 und K3 gehören hierher.
- **Laufender Kurs** (`ui/views/kurse.py`): **kein Kursbild.** Die Person sieht ihr Kapitel,
  was `zeigen_wenn` für sie einblendet, und in der Kapitelliste den Weg, den sie gegangen ist.
  Zweige, die sie nicht gewählt hat, erscheinen nicht; hinter einer Entscheidung, die noch
  aussteht, endet die Liste („wie es weitergeht, hängt von deiner Wahl ab“).
- „Der Teil, der gerade aktiv ist“ heißt: das laufende Kapitel **und der eigene Weg bis
  dorthin** — Ben, 16.11.2026: „bleibt sichtbar; man soll alte Inhalte anschauen können.“
  Abgeschlossene Kapitel des eigenen Wegs lassen sich wieder öffnen und lesen.

## 7. Stufen (Grundmodell bestätigt 16.11.2026; gebaut wird auf Bens Wort)

| Stufe | Inhalt | Braucht |
|---|---|---|
| 0 | **Von vorn bei Test/Auswahl** (§5.2): Marke „Durchlauf beendet“ (Migration 063, `plan.course_run_ended_at`), neu fragen, „Wie beim letzten Mal“; Tests `tests/test_kurse.py`, `tests/test_ui_kursbloecke.py` | **gebaut 16.11.2026** — Gerätetest T141 |
| 1 | Kursplan wächst (`plan = wachsend`, Marken, Spalte `plan.course_id`), Bausteine `plan_uebung`, `plan_einstellen`, `plan_weg`; Rest von B2 (Timer, Übergang … in `VorlageItem`/`PlanVorlage`); Sammelkarte „Das ändert sich an deinem Plan“; **Kurs-Editor** (`views/kurs_bearbeiten.py`: Baustein hinzufügen) und **Werkzeug** (`trainingsapp-paket pruefen`); neue Formatversion nur für Pakete, die das nutzen (Formatversion 6) | **gebaut 16.11.2026** — Bauplan §11, Abweichungen §11.8; Gerätetest T142; P211 und P212 entschieden (Ben: „Ja“), P212 noch zu bauen; Grenzen N171 |
| 2 | Test im Fokus mit Vorgabe Menge · Zeit · Skala ab/bis/dazwischen (§3.3), „Als Ziel übernehmen“ | Frage 4: beantwortet; Stufe 1 |
| 3 | Antworten speichern, Folgen (`zeige`, `baustein`), `zeigen_wenn`; Tabelle `course_answer`; Editor (Liste mit „Wenn …“) = **K1**; im laufenden Kurs nur der eigene Weg (§6 „Zwei Sichten“) | Frage 3: **ja** |
| 4 | Kursbild lesend **im Kurs-Editor** = **K2** (Knoten-Darsteller aus `ablaufbild` herauslösen) | Frage 5: **ja**; Stufe 3 |
| 5 | Kursbild zeichnen = **K3**, gemeinsame Graph-Schicht, Kapitel-Auslöser „Tor offen“ | Entscheidung nach Stufe 4 |

Vor Stufe 1: **T134** (Material, Kurse aus Blöcken am Gerät, `offene_fragen.md` §2) sollte
durch sein — alles hier baut auf den Blöcken auf, und am Gerät ist sie ungeprüft. (Ben,
16.11.2026: T134 „nach dem nächsten Build“ — Stufe 1 ist davor gebaut; T134 und T142 stehen
zusammen an.)

Jede Stufe: Tests zuerst für die flet-freie Rechnung (`core/`), dann die Ansicht, danach
Web-Fotos (`web-fotos`) der Karten; Gerätetest im Katalog; Doku in `plan_kurse.md` §7 nachführen.

## 8. Regeln, die gelten

- **Bedingungen rechnen aus Einträgen, Selbstauskunft und eigener Wahl — nie aus Messwerten**
  (`plan_kurse.md` §3, §7; `docs/recht/00_zweckbestimmung.md`). Die Skala ist Selbstauskunft.
- **Nichts am Plan ohne Tipp**; Vorschläge abschaltbar (Ben, 12.11.2026).
- **Eine Edition** (Ben, 16.11.2026): Der Patientenmodus liegt auf Eis; neue Funktionen
  bekommen keinen Zweig dafür. Es gelten die Regeln der Zweckbestimmung für Edition A.
- **Erklären, nicht bewerten** (Kurstexte, `plan_kurseditor.md` §1) — die bestehende Regel für
  Texte. Eine eigene Regel „der Kurs deutet die Antwort nicht“ gibt es **nicht** (Ben,
  16.11.2026: „Das ist übertrieben“).
- **Kapitel-`key`s und Block-IDs nie ändern** — Fortschritt, Marken und Antworten hängen daran.
- **Pakete:** Kurse reisen mit Bausteinen im Paket; Antworten, „gesehen“ und Fortschritt nicht.
  Verweise auf Timer als eingebettete Kopie (`ohne_verweise`, `plan_timer_zuordnen.md`).
- **Neue Datenbank-Tabellen/Spalten:** nummerierte Migration, SQL mit `?`.
- Keine neue Netzverbindung (Medien bleiben Links/Paketdateien; P202 ist getrennt).

## 9. Stellen, die berührt werden (Rückfrage-Liste)

Nach Bens Setzung vom 21.10.2026 einzeln — gebaut wird erst nach Ja:

- `core/kurse.py` (`VorlageItem`, `PlanVorlage`, `Kapitel`, Bedingung), `core/kursbloecke.py`
  (`vorlage_anwenden`, neue Blockarten, `zeigen_wenn`), `data/kurse.py` (`kapitel_erreichen`,
  `plaene_anlegen`, `zuruecksetzen`, `_kapitel_zuordnen`), `core/pakete.py` (Format)
- `ui/views/kurse.py`, `ui/views/kurs_bearbeiten.py`, `ui/components/kursblock.py`
- Planteile: `PlanRepo` (Herkunft, Marke), `core/standards.py` nur lesend; `ui/views/plan*.py` nicht
- ab Stufe 4: `ui/components/ablaufbild.py` (Knoten-Darsteller), `core/ablauf.py` (Auslösersätze)
- Paketinhalte: `data/seed/standard.toml` (Einführungskurs) **unverändert** — er bleibt `plan = kapitel`

## 10. Fragen an Ben (Katalog P207) — beantwortet am 16.11.2026

Die Antworten stehen in der Tabelle am Kopf — auch 6b (ja, nach der Erklärung) und die
Nachfrage zum laufenden Kurs. Offen ist hier nichts mehr; die nächste Rückfrage sind die
Skizzen vor Stufe 1.

Die Fragen, wie sie gestellt waren (Frage 3 nannte noch die gestrichene Regel, Frage 4 den
Patientenmodus), mit meiner Empfehlung zuerst:

1. **Kursplan wächst** — als Schalter am Kurs, bestehende Kurse bleiben Kapitelpläne? *Ja.*
2. **Kurs noch einmal durchlaufen** — bei Kapiteln mit Test/Auswahl alten Plan archivieren
   („· Durchlauf 1“), neu fragen, „Wie beim letzten Mal“ als Vorbelegung; Kapitel ohne bleiben wie
   15.10.? *Ja* — das behebt zugleich den Befund aus §5.2. Alternative: Plan weiterverwenden und
   nur die Ziele neu setzen (verliert den Vergleich mit dem ersten Durchlauf).
3. **Antworten speichern** (Selbstauskunft, nur Gerät) und Folgen zulassen — mit der Regel
   „der Kurs deutet die Antwort nicht“ (§8)? *Ja.*
4. **Test „bis Anstrengung n“** in Solo bauen, im Patientenmodus aus, bis P204 geklärt ist?
   *Ja.* Und zu Bens Beispiel „mit 30 Wiederholungen vorher getestet“: meinst du (a) eine
   **feste Menge** (30) ausführen, danach die Anstrengung angeben, und die Menge wird das Ziel —
   oder (b) **so lange üben, bis Anstrengung 7** erreicht ist? *Ich habe (b) als `bis_skala`
   und (a) als `bestwert` mit fester Menge gelesen; bitte bestätigen.*
5. **Kursablauf als Bild:** erst Liste mit „Wenn …“ (K1), dann Bild lesend (K2), Zeichnen (K3)
   nach Erfahrung mit deinen Kursen? *Ja.*
6. **Bedingungen angleichen** (§2.1): (a) Der Kurs setzt „hart/weich“ nur als **Vorgabe**, die
   Wahl „Heute: Hart | Weich“ am Start bleibt bei der Person; verbindlich ist die Pflicht am
   Weg? *Ja.* (b) Kapitel-Auslöser „Tor im Kursplan offen“, damit Kurs und Workout nicht
   doppelt zählen? *Ja, mit Stufe 5.*

Zum Veranschaulichen der Sammelkarte „Das ändert sich an deinem Plan“ und der „Wenn …“-Zeilen
sind **Skizzen als Bildergeschichte** sinnvoll — sobald du das Grundmodell (Fragen 1–3) bestätigt
hast.

## 11. Bauplan Stufe 1 (16.11.2026) — nach Bens Ja zu den Skizzen

Skizzen K1–K6: <https://claude.ai/artifact/13qzjuaHx6GtRTpV9ayE4L>. Ben, 16.11.2026: „Die
Skizzen passen“ · Umfang: „Alles in einem“ (Kern, Teilnehmer-Seite **und** Editor) · zur
Grundlage des Plans: „Es soll flexibel möglich sein, die Pläne zu entwickeln, einen im Paket
existierenden Plan kann man natürlich genauso nehmen, evtl. auch nur einer, der als
‚unsichtbare‘ Vorlage besteht.“

### 11.1 Begriffe und Daten

| Begriff | Bedeutung | Wo |
|---|---|---|
| **Kursplan** | der eine Plan je Profil, den ein Kurs mit `kursplan` baut; gewöhnlicher Plan mit Herkunft Kurs | `plan.course_id` (neu) |
| **Grundlage** | womit der Kursplan beginnt: **leer** · **ein Plan des Pakets** (`plaene[]`, über seinen Schlüssel) · **eine Vorlage im Kurs**, die sonst nirgends erscheint | `Kurs.kursplan` (neu): `name`, `wochentage`, `grundlage` (Schlüssel) **oder** `vorlage` (`PlanVorlage`) |
| **Baustein** | Block der Art `plan_uebung` · `plan_einstellen` · `plan_weg` — eine Änderung am Kursplan | `core/kursbloecke.py` |
| **Marke** | woran der Kurs seine Planübungen wiederfindet: die Block-ID des Bausteins (bei einer Auswahl `block:uebung`, in der Grundlage `g:<n>`) | `plan_item.course_mark` (neu), `PlanItem.kurs_marke` |
| **Kurs-Stand** | was der Kurs an einer Marke zuletzt gesetzt hat (Ziel, Timer …) — daran erkennt er, was die Person geändert hat | `plan.course_state_json` (neu), gerätelokal |
| **Änderung** | eine Zeile der Sammelkarte | `core/kursplan.py` (neu): `Aenderung` |

Ein Kurs **ohne** `kursplan` verhält sich wie bisher (Kapitelpläne); der Einführungskurs im Paket
„Standard“ bleibt so. Migration 064: `course.kursplan_json`, `plan.course_id`,
`plan.course_state_json`, `plan_item.course_mark`. `PlanRepo.speichern` schreibt die Marke der
Planübungen mit (es ersetzt die Liste, sonst gingen die Marken bei jedem Speichern verloren);
`course_id` und den Kurs-Stand fasst es nicht an.

### 11.2 Bausteine (Paketfelder der Blöcke)

| Art | Felder | Zeile in der Karte |
|---|---|---|
| `plan_uebung` | `uebung` (Schlüssel/ID) **oder** `aus` (Block-ID einer Auswahl: „die gewählte“), `hinter` (Marke; leer = ans Ende), `ziel` (Tabelle) oder `ziel_aus` (Block-ID eines Tests) mit `faktor`, `felder`, `timer`, `takt` | „Käfer kommt dazu — hinter Planke“ |
| `plan_einstellen` | `an` (Marke; leer = der Plan), dazu eines oder mehrere von `ziel`/`ziel_aus`+`faktor`, `timer`, `takt`, `felder`, `uebergang` (`hart`/`weich`, nur Vorgabe), `pause_ohne_timer` | „Ziel für Käfer: 30 Wiederholungen — aus deinem Test“ · „Timer für Käfer: 3 Runden …“ |
| `plan_weg` | `von`, `zu` (Marke oder `ende`), `kante` (wie `core.ablauf.Kante.als_dict` ohne `von`/`nach`) | „Von Planke weiter zu Käfer nach 60 s — Pflicht“ |

`auswahl` und `test` ändern im Kursplan-Kurs nichts von selbst: Sie liefern Wahl und Wert, auf
die sich Bausteine beziehen (`aus`, `ziel_aus`). Ein Baustein mit `ziel`, `timer` usw. an einer
`plan_uebung` erzeugt je Angabe eine eigene Zeile, damit sich jede einzeln abwählen lässt (K2).

### 11.3 Rechnung (`core/kursplan.py`, flet-frei, mit Doctests)

- `grundplan(kurs, paketplan) -> Plan` — der Kursplan am Anfang (leer, aus dem Paketplan oder
  aus der Vorlage; die Planübungen der Grundlage tragen `g:<n>`).
- `aenderungen(plan, bloecke, werte, wahl, kurs_stand, namen) -> list[Aenderung]` — je Zeile
  `id`, `titel`, `unter`, `stand`:
  - **neu** — noch nicht im Plan;
  - **übernommen** — steht schon so im Plan (nicht mehr angeboten, höchstens als erledigt gezeigt);
  - **offen** — die Wahl oder der Test, auf den sie sich bezieht, fehlt noch;
  - **weicht ab** — die Person hat den Wert seit dem letzten Kurs-Stand geändert: Beide Werte
    stehen da, Vorgabe „lassen“ (K3);
  - **Anker fehlt** — die Planübung, hinter die etwas soll, gibt es nicht mehr: ans Ende, mit
    Hinweis (K3); ein `plan_einstellen` oder `plan_weg` ohne seine Marke entfällt mit Hinweis.
- `anwenden(plan, bloecke, werte, wahl, gewaehlt, uebernehmen_trotz, kurs_stand) -> (Plan,
  kurs_stand)` — nur die gewählten Zeilen; **zweimal anwenden ändert nichts** (Marken).
  Wege entstehen im Ablauf des Plans (`core.ablauf`); folgt der Ablauf noch der Liste, bleibt
  er dabei, solange kein `plan_weg` etwas anderes sagt.

### 11.4 Datenbank (`data/kurse.py`)

- `kursplan(kurs, profil)` — der laufende Kursplan (ohne frühere Durchläufe) oder `None`;
  `kursplan_anlegen` beim Start des Kurses, **wenn die Grundlage Übungen hat**, sonst mit dem
  ersten „Übernehmen“.
- `plan_aenderungen(kurs, kapitel, profil)` und `plan_uebernehmen(kurs, kapitel, profil, ids,
  trotz)` — rufen die Rechnung, speichern Plan und Kurs-Stand in einer Transaktion.
- Kapitel abschließen deaktiviert den Kursplan **nicht**; „Von vorn“ macht ihn immer zum
  früheren Durchlauf (wie §5.2); Kurs löschen deaktiviert ihn; die Bedingung „Tage“ zählt die
  Übungen des Kursplans.

### 11.5 Teilnehmer-Seite (K1–K4)

- `ui/components/kursplan_karte.py`: die Sammelkarte — Zeilen mit Haken, die Karte „Dein Plan
  weicht ab“ mit zwei Knöpfen, Hinweiszeilen, „Übernehmen“/„Später“, darunter der Satz „Nichts
  ändert sich ohne deinen Tipp“. Eingebaut in die Kapitelansicht (`views/kurse.py`), wenn der
  Kurs einen Kursplan baut.
- Kursseite: Karte „Dein Kursplan“ mit „Trainieren“ (K4); die Kapitelliste bleibt, wie sie ist
  (Wege zwischen Kapiteln kommen erst mit Stufe 3).
- **Nicht in Stufe 1:** `zeigen_wenn` (K1 zeigt es schon — das Video „weil du Käfer gewählt
  hast“ ist Stufe 3) und der Test mit Vorgabe (Stufe 2); der Test bleibt vorerst „jüngster
  Eintrag“.

### 11.6 Editor (K5, K6) und Pakete

- Kurs bearbeiten: Karte „Der Kurs baut einen Plan“ — an/aus, Name, Grundlage (leer · einer der
  eigenen Pläne als Vorlage). Kapitel bearbeiten: zwei Abschnitte, „Im Kapitel“ und „Am Plan“;
  je Baustein ein Formular wie K6 mit der Vorschau „So steht es in der Karte“.
- Paket: `kurse[].kursplan`, die drei Blockarten; **Formatversion 6** nur für Pakete, die das
  nutzen; `trainingsapp-paket pruefen` meldet unbekannte Marken, einen `aus`-Verweis ohne
  Auswahl, einen `ziel_aus`-Verweis ohne Test, eine `grundlage` ohne Paketplan;
  `docs/uebungspakete.md` nachführen.

### 11.7 Reihenfolge und Prüfung

1. Rechnung + Tests · 2. Migration, Repos + Tests · 3. Teilnehmer-Seite + Tests + Web-Fotos ·
4. Paketformat, Werkzeug + Tests · 5. Editor + Tests + Web-Fotos · 6. voller Testlauf
(Migration), Doku (`plan_kurse.md`, `datenmodell.md`, `uebungspakete.md`, Katalog, Gerätetest).
Nach jedem Schritt ist der Baum grün.

### 11.8 Gebaut am 16.11.2026 — was anders ist als oben geplant

Der Bauplan oben bleibt, wie er vor dem Bau stand; hier steht, wo der Code davon abweicht.
Maßgeblich ist der Code (`core/kursplan.py`, `data/kurse.py`, `tests/test_kursplan.py`,
`tests/test_kurse.py`, `tests/test_ui_kursplan.py`, `tests/test_paket_kursplan.py`).

**Rechnung und Datenbank**

- **Übernommenes bleibt übernommen.** Der Kurs-Stand merkt je Marke die angewendeten Zeilen
  (`erledigt`); eine solche Zeile wird nicht wieder angeboten, auch wenn der Wert später anders
  ist. „Weicht ab“ gibt es darum nur für Zeilen, die noch nie übernommen wurden — sonst böte
  Kapitel 1 seine 60 s nach Kapitel 3 wieder an, und ein Ziel aus dem Test wäre nach jedem
  Training wieder „neu“ (der Testwert ist der jüngste Eintrag).
- **„Lassen“ wird gemerkt** (`anwenden(..., lassen=)`, `KursRepo.plan_uebernehmen(..., lassen=)`):
  Die Zeile gilt als erledigt, der Plan bleibt; ein späteres Kapitel mit einem anderen Vorschlag
  fragt wieder.
- **Aus dem Plan genommen** (nicht im Bauplan): Eine feste Übung, die der Kurs gebracht und die
  Person aus dem Plan genommen hat, kommt nicht als „neu“ mit Haken wieder — der Kurs fragt als
  Abweichung („… übernehmen“ · „Plan so lassen“, Vorgabe lassen), nach „lassen“ nicht noch
  einmal. Eine **gewählte** Übung gibt ihre Auswahl wieder frei; noch einmal gewählt ist sie neu.
- **Marke bei `aus` ist immer `<block>:<übung>`**, auch bei einer einzigen Gewählten.
- **Was an einer Übung hängt, die erst dazukommt** (Ziel, Timer, Weg), nennt deren Zeile
  (`Aenderung.braucht`) — die Karte wählt es mit ab. Kommen bei einem Weg beide Enden erst dazu,
  steht nur das Ziel darin.
- **Wahl einer Auswahl:** Was als Marke im Kursplan steht, gilt und ist fest
  (`wahl_im_plan`, über die Blöcke des ganzen Kurses); bis dahin gibt die Ansicht die Wahl mit
  (`plan_aenderungen(..., wahl=)`).
- **Wege:** Der Hauptweg wird in die Bedingung der Planübung gespiegelt wie im Ablauf-Editor;
  solange nur Hauptwege gesetzt sind, folgt der Ablauf weiter der Liste. „Weicht ab“ gibt es
  auch für einen Weg, den die Person geändert hat.
- **Texte:** „30 Wiederholungen“, „45 s“ (eigener Formatierer statt der Kurzformen); „nach 60 s“
  am Weg nur, wenn die Planübung einen eigenen Timer hat, sonst „…, wenn die Zeit ab ist“.
- Der Kursplan entsteht beim Start des Kurses nur, wenn die Grundlage Übungen hat, sonst mit
  dem ersten „Übernehmen“; im Kursplan-Kurs ruft der Tipp auf das erste Kapitel `starten`.

**Teilnehmer-Seite**

- Die Karte steht in jedem erreichten Kapitel, auch in abgeschlossenen — sonst ginge verloren,
  was man mit „Später“ liegen ließ. „Später“ klappt sie zu („Wieder zeigen“).
- Nur „lassen“ gewählt: Meldung „Dein Plan bleibt, wie er ist“ statt „Plan geändert“.
- **„Plan anlegen“ bleibt in einem Sonderfall:** Kapitel mit eigenen Plan-Vorlagen **und** Test
  oder Auswahl in einem Kursplan-Kurs (die Kapitelpläne entstünden sonst nie).
- „Anker fehlt“ lässt sich nicht einzeln abwählen (Symbol statt Haken, gilt mit „Übernehmen“).

**Kurs-Editor**

- **Die Formulare der Bausteine sind Blätter**, keine eigene Seite (K6): Das Kapitel-Formular
  hält seine Liste ungespeichert; „Übernehmen“ im Blatt, Wegtippen verwirft. Die Vorschau „So
  steht es in der Karte“ rechnet mit `core.kursplan.aenderungen` auf einem Beispielplan
  (Grundlage, Kapitel davor übernommen, erste Übung jeder Auswahl gewählt, Beispielwert je Test).
- **Baustein-IDs** sind lesbar und fest: `uebung-<n>`, `einstellen-<n>`, `weg-<n>`, eindeutig im
  ganzen Kurs; die Nummer ist die höchste bekannte + 1 (auch gegenüber den Marken in den
  Kursplänen dieses Profils). Die Auswahllisten bieten nur an, was `trainingsapp-paket pruefen`
  annimmt (nur Bausteine davor, „Ende“ nur bei „Zu“).
- **Löschen mit Verweisen:** Die Rückfrage nennt jeden betroffenen Baustein mit Kapitel und
  Folge. Geleert wird ein Verweis nur, wo der Baustein danach noch etwas ist (`hinter` → ans
  Ende, `ziel_aus` → ohne Ziel); verliert er `aus`, `an`, `von`/`zu` oder seine letzte Angabe,
  wird er **mit gelöscht** — `Block.from_dict` verwürfe ihn beim nächsten Laden sonst still, und
  ein leeres `an` hieße „am ganzen Plan“. Dieselbe Rückfrage beim Löschen eines Kapitels und
  beim Entfernen oder Verkürzen der Grundlage (`g:<n>`).
- **Zwei Speicherprüfungen gelten im Kursplan-Kurs nicht:** „Test und Auswahl brauchen einen
  Plan im Kapitel“ und „Tage zählt die Pläne des Kapitels“. Dort liefern Test und Auswahl an
  die Bausteine (§11.2), und „Tage“ zählt die Übungen des Kursplans
  (`tests/test_kurse.py::test_stand_tage_zaehlt_die_uebungen_des_kursplans`). Ohne Kursplan
  gelten beide weiter (getestet in `tests/test_ui_kurs_bausteine.py`).
- **Wege:** ein eigenes schmales Formular für genau eine Kante statt `wege_karte`; **Timer** nur
  aus der Bibliothek (eingebettet, `ohne_verweise`); **Takt und Parameter** eines Bausteins sind
  im Editor nicht einstellbar, vorhandene Werte bleiben.
- `kurs_kopieren` nimmt den Kursplan mit und schreibt alle Verweise auf die neuen Block-IDs um;
  ein Paketplan als Grundlage wird in der Kopie zur Vorlage.
- **Die Rechnung des Editors liegt im Kern** (`core/kursbau.py`, flet-frei, Tests
  `tests/test_kursbau.py`): Verweise lesen und umschreiben, Baustein-IDs, Löschfolgen, die
  Vorschau (`Kurssicht`) und die Kopie eines Kurses (`kurs_kopie`). In `ui/` bleibt das Blatt
  (`components/baustein_form.py`). Noch in der Ansicht, obwohl flet-frei: `block_kurz`,
  `block_fehler`, `antworten_text`/`antworten_lesen` in `views/kurs_bearbeiten.py` (lagen zum
  Teil schon vorher dort).

**Paket (Formatversion 6)**

- `core.pakete.noetige_version` bestimmt die Version aus dem Inhalt; 6 nur mit `kursplan` oder
  einem `plan_*`-Block. Die App 0.3.94 lehnt Version 6 ab („Das Paket ist neuer als diese
  App“, nachgesehen in `git show v0.3.94:src/trainingsapp/core/pakete.py`).
- Marken `<block-id>:<übung>` mit Paketschlüssel werden beim Lesen zur Übungs-ID.
- `trainingsapp-paket pruefen` prüft mehr als geplant (Liste in `docs/uebungspakete.md`), u. a.
  Verweise auf Bausteine weiter unten im selben Kapitel und Baustein-IDs, die nicht als Marke
  taugen (`ende`, `g`).
- **Update-Stufe** (`core/paketstufe.py`, Ben 16.11.2026: „Ja“, Katalog P211,
  `docs/plan_paketversionen.md` §2): Kursplan kommt
  dazu oder fällt weg → groß; geänderte Blöcke eines Kapitels → mittel; Name, Wochentage,
  Grundlage → klein. Vorher galt ein Update, das nur Blöcke änderte, als „unverändert“.
- Eigene Pakete nehmen die Übungen aus Blöcken und Kursplan-Vorlage mit
  (`core.eigenes_paket.noetige_uebungen`); Dateien an den Planübungen der Vorlage reisen mit und
  bleiben beim Aufräumen (`core.paketdatei.medienlisten`, `data/paketmedien.py`).

**Bekannte Grenzen** (Katalog N171)

- Mehrere Gewählte als gleichwertige Wege: Die Kette zwischen den Gewählten bleibt stehen —
  ein `plan_weg` setzt Wege, er nimmt keine weg.
- Hat die Person den Ablauf selbst gezeichnet, ist eine neue Planübung dort unverbunden, bis
  ein `plan_weg` sie anschließt.
- Der Test misst die Übung, die er nennt — auch wenn die Person in der Auswahl eine andere
  wählt (Stufe 2 und 3).
- Die offene Wahl einer Auswahl hält nur die Ansicht: Wer zum Test in die Übung geht und
  zurückkommt, wählt noch einmal (Katalog P212).
