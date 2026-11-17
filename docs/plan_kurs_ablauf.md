# Planung: Kurse als Plan-Baukasten (15.11.2026, Durchsicht 16.11.2026)

Bens Auftrag vom 15.11.2026: Die Gestaltung der Kurse überarbeiten — zusammen mit den
Bedingungen in Plänen und Workouts. „Kurse liefern Informationen und Übungsmaterial und können
im Erstellen individueller Pläne helfen. Dabei sind alle Werte, die einen Plan ausmachen, über
die Kurse einstellbar.“ Dazu zwei Fragen: Konflikte (Kursplan existiert schon · Kurs wird noch
einmal durchlaufen) und ob ein **Ablaufeditor wie beim Workout** für Kurse lohnt — auch bei
Verschachtelungen in den Entscheidungen.

**Stand 16.11.2026 nachts** (die Übersicht steht in §7, das Leitbild in §16): **gebaut** sind
Stufe 0 („Von vorn“ fragt neu), Stufe 1 (der Kurs baut einen Plan: Kursplan, Bausteine,
Sammelkarte, Kurs-Editor, §11), Stufe 2 (der Test läuft mit der Uhr, §13), A1 („Das kommt
noch“, §13.6), das Bild des Kursplans im Editor (§14) und der Testwert als **Variable des
Kurses** (§15.1), der flexibel gestaltete Test (§15.2–15.5) und das Bedienen des Plan-Bilds
mit denselben Gesten wie im Plan (§16.3). **17.11.2026:** der **Wert für den Plan** nach dem
Test — ganz, Anteil oder von Hand (W3, §17). **Plan** bleiben Stufe 3–5 und A2.
Bens Setzung vom 21.10.2026 („Pläne und Kurse nicht ohne Rückfrage ändern“) gilt: Jede
berührte Stelle steht in §9, die Fragen in §10 (Katalog P207). Die Korrekturen am
Workout-Bildschirm aus demselben Auftrag stehen in `plan_uhr_fokus.md` §10, die Kennzeichnung
der Medien und die Animation beim Üben in `plan_medienrollen.md`.

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
| 2 | Test im Fokus mit Vorgabe Menge · Zeit · Skala ab/bis/dazwischen (§3.3), „Als Ziel übernehmen“ | **gebaut 16.11.2026** — §13; Skizzen T1–T5; Gerätetest T143 |
| 2a | **Der Testwert ist eine Variable des Kurses** (§15.1): Tabelle `course_variable` (Migration 065); der Lauf setzt sie, „Nochmal“ überschreibt, das abgeschlossene Kapitel hält den Wert eines Tests ohne Lauf fest; jeder Baustein danach kann sie verwenden (`ziel_aus`) | **gebaut 16.11.2026** — Ben: „Testwert wird als Variable gespeichert“ |
| 2b | **Der Test, flexibel gestaltet** (§15.2): Uhr (Stoppuhr · Timer der Übung · eigener Timer), Takt, Ausführung (vorgegeben oder frei), Hinweis vor dem Start — jede Einstellung mit Vorgabe, „wie die Übung“ oder eigener Angabe | **gebaut 16./17.11.2026** — §15.2–15.5; Skizzen F1–F4; Gerätetest T143 |
| 3 | Antworten speichern, Folgen (`zeige`, `baustein`), `zeigen_wenn`; Tabelle `course_answer`; Editor (Liste mit „Wenn …“) = **K1**; im laufenden Kurs nur der eigene Weg (§6 „Zwei Sichten“) | Frage 3: **ja** |
| 4 | Kursbild lesend **im Kurs-Editor** = **K2** (Knoten-Darsteller aus `ablaufbild` herauslösen) | Frage 5: **ja**; Stufe 3 |
| 5 | Kursbild zeichnen = **K3**, gemeinsame Graph-Schicht, Kapitel-Auslöser „Tor offen“ | Entscheidung nach Stufe 4 |
| A1 | **Vorschau „Das kommt noch“** auf der Kursseite: was spätere Kapitel am Plan ändern werden, gerechnet aus ihren Bausteinen — ohne Sperren (§12) | **gebaut 16.11.2026** — §13.6; Skizze V1; Gerätetest T143 |
| B1 | **Das Plan-Bild bedienen wie im Plan** (§16.3, Katalog P217): im Kurs-Editor dieselben Gesten wie im Reiter „Ablauf“ — den Punkt einer Übung auf eine andere ziehen legt nach kurzer Bestätigung den Baustein „Weg“ im bearbeiteten Kapitel an; gedrückt halten öffnet das Menü an der Übung | **gebaut 16.11.2026** — Skizze G4; Gerätetest T144 |
| W3 | **Wert für den Plan** (§17): direkt nach dem Test und im Kapitel hinter „Wert ändern“ sagt die Person, wie der Testwert in den Plan geht — **ganz · Anteil · von Hand** (− / + und Tastatur); vorgewählt, was der Kurs sagt; ohne Wahl rechnet der Kurs wie bisher; die Sammelkarte bietet das neue Ziel wieder an (Migration 066) | **gebaut 17.11.2026** — Ben: „Nimm W3. Die Werteintragung kommt normal direkt nach einem Test“; Skizze W3; Gerätetest T143 |
| V | **Variablen weiter verwenden** (§16.2): andere Abnehmer als das Ziel (Auslöser eines Wegs „ab deinem Testwert“, Dauer eines Timers), die Antwort einer Frage als Variable (trifft Stufe 3); der Wert von Hand ist als W3 gebaut | Vorschlag — Bens Wort |
| A2 | **Autorenwerkzeug „vom fertigen Plan aus“**: Zielplan im Plan- und Ablauf-Editor bauen, jede Übung, jeden Weg und jede Einstellung einem Kapitel zuordnen („ab Kapitel 2“); der Editor erzeugt daraus die Bausteine (§12) | Skizzen; Bens Wort |

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
- **Vorgabe und Überschreiben** (Ben, 16.11.2026: „Wir dürfen hier gar nicht zu kompliziert
  sein, Dinge mit Standardwerten versehen. Überschreiben ist möglich“): Jede Einstellung eines
  Bausteins hat eine Vorgabe, die ohne Zutun gilt. Wer nichts einstellt, bekommt einen
  brauchbaren Baustein; die Übung bringt ihre Umgebung (Timer, Takt, Parameter) mit, der
  Baustein überschreibt nur, was anders sein soll (§16.1).
- **Werte sind Variablen des Kurses** (§15.1): Was ein Baustein erzeugt (heute: der Wert eines
  Tests), steht unter einem Namen am Kurs und lässt sich in jedem Kapitel danach verwenden.
- **Der Wert für den Plan gehört der Person** (§17, Ben 17.11.2026): Nach dem Test sagt sie,
  wie er in den Plan geht — ganz, ein Anteil, von Hand. Vorgewählt ist, was der Kurs sagt;
  ohne Wahl rechnet er wie bisher. Der Eintrag des Tests bleibt, und am Plan ändert auch
  diese Wahl nichts ohne Tipp. Die App nimmt die Zahl und deutet sie nicht.
- **Kapitel-`key`s und Block-IDs nie ändern** — Fortschritt, Marken, Antworten und die Namen
  der Variablen hängen daran.
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
    Der Hinweis nennt, **warum** sie fehlt (N172, Ben 16.11.2026; `_Lauf._fehlt`): „… ist
    nicht mehr in deinem Plan.“ nur, wenn der Kurs sie gebracht und die Person sie
    herausgenommen hat; „Deine Auswahl fehlt noch.“, wenn sie aus einer Auswahl kommt und die
    Wahl fehlt (auch die eines früheren Kapitels); sonst „… ist noch nicht in deinem Plan.“
    (nie übernommen, oder sie wartet hinter einer Auswahl). Der Stand der Zeile bleibt.
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

**Nachgezogen am 16.11.2026** — Ben zu drei Grenzen der ersten Fassung: „gleichwertige Wege
müssen gleichwertig sein; Verkettung ist dann nicht gegeben, in der Liste aber machbar“ · „muss
behoben werden“ (Test) · „muss ebenfalls behoben werden“ (Editor); dazu P212 („Ja“).

- **Gleichwertige Wege:** Führen von einer Planübung mehrere Wege zu den Gewählten desselben
  Bausteins, geht man im Workout einen davon — die Kette der Liste zwischen den Gewählten
  entfällt, jede führt dorthin, wohin die letzte von ihnen führt, mit ihrer eigenen Bedingung
  (`core.kursplan._Lauf._gleichwertig`; nur, wenn in diesem Gang ein Weg übernommen wurde — was
  die Person sonst gezeichnet hat, bleibt). In der Liste stehen alle und lassen sich abhaken.
  Wählt die Person nur einen der Wege, bleibt die Kette. So macht es `vorlage_anwenden` für
  Kapitelpläne seit dem 12.11.
- **Der Test misst die gewählte Übung:** Ein `test` darf statt `uebung` ein `aus` tragen (die
  `id` einer Auswahl, auch aus einem früheren Kapitel). Je Übung der Auswahl gibt es einen Wert
  (`<test>:<übung>`, `core.kursbloecke.wert_schluessel`, `KursRepo.testwerte`); ein Baustein
  mit `ziel_aus` nimmt den seiner Übung, im Kapitelplan bekommt die Gewählte ihr Ziel aus ihrem
  eigenen Test. Formatversion 6. Ein Test mit fester `uebung` bleibt, wie er war.
- **Die offene Wahl bleibt für die Sitzung** (P212): `AppState.kurs_wahl`, je Profil und
  Kapitel, nur im Speicher; verworfen, sobald sie übernommen ist, bei „Von vorn“, wenn der Kurs
  gespeichert oder entfernt wird (Stempel aus `updated_at` und dem Erreichen des Kapitels) und
  mit dem Neustart der App. Gilt auch für Kapitelpläne („Plan anlegen“).
- **Editor:** Parameter (Knöpfe wie in „Im Plan einstellen“, „wie die Übung“ · „nur abhaken“ ·
  auswählen), Takt (das Takt-Blatt, über dem Baustein-Blatt) und ein **eigener Timer** je
  Baustein (der volle Timer-Editor, eingebettet; daneben weiter „keiner“ und die Bibliothek)
  sind einstellbar. Der Test-Dialog bietet „die gewählte aus ‹Auswahl›“ — im Kursplan-Kurs aus
  diesem oder einem früheren Kapitel, mit Kapitelplänen nur aus demselben (ein späteres Kapitel
  kennt die Wahl eines früheren dort nicht; `Kurssicht.auswahlen_fuer_test`, das Werkzeug meldet
  es als Fehler). „Was wird gemessen“ bietet die Felder, die alle Übungen der Auswahl haben.

**Bekannte Grenzen** (Katalog N171)

- Hat die Person den Ablauf selbst gezeichnet, ist eine neue Planübung dort unverbunden, bis
  ein `plan_weg` sie anschließt.
- Steht zwischen zwei Gewählten eine Übung, die die Person selbst eingefügt hat, bleibt deren
  Kette stehen (die Gewählten sind dann über sie verbunden).
- Ein Test mit fester Übung gilt weiter dieser Übung, auch wenn ein Baustein sein Ergebnis an
  einer anderen Planübung als Ziel setzt — gewollt ist dann `aus`.
- Ein Test mit `aus` hat **ein** Feld für alle Übungen der Auswahl; hat eine es nicht, bekommt
  sie keinen Wert und ihr Ziel bleibt offen (der Editor sagt es, das Werkzeug gibt einen Hinweis).
- Übernommenes gilt als erledigt: Eine Korrektur an einem früheren Kapitel (Paket-Update)
  erreicht niemanden mehr, der schon weiter ist (§12).

## 12. Wachsen oder bereitliegen? (Ben, 16.11.2026)

Bens Frage: Macht es mehr Sinn, wenn sich der Plan durch den Kurs erst aufbaut — oder wenn er
vorher existiert und der Kurs ihn editiert bzw. freigibt („Manipulation“ oder „doch eher
kreationistisch“)? Betrachtet für die Erstellung, die Änderung und den Umgang im Verlauf.
Ben danach: „Nimm die letzten Überlegungen mit rein.“ — als Richtung aufgenommen; gebaut ist
davon nichts außer dem, was Stufe 1 schon tut.

**Richtung:** Für die **Teilnehmenden wächst** der Plan (Stufe 1). Für die **Autorin oder den
Autor** wäre es besser, **vom fertigen Plan auszugehen**. Gesperrte Übungen kommen **nicht**
in den Plan der Person.

| | Wachsend (Bausteine je Kapitel) | Bereitliegend (fertiger Plan, Kurs schaltet frei) |
|---|---|---|
| **Erstellung** | mühsam: Der Zielplan ist nie als Ganzes zu sehen, Verweise werden von Hand gepflegt | leicht: Plan- und Ablauf-Editor gibt es, der Plan lässt sich als Workout ausprobieren |
| **Änderung durch die Person** | klar im Vorteil: Der Kurs weiß je Planübung, was er zuletzt gesetzt hat, und fragt nur bei Abweichung | der ganze Plan müsste mit dem geänderten abgeglichen werden; bei gezeichnetem Ablauf gewinnt heute die eigene Fassung — Updates kämen nicht an |
| **Änderung durch den Kurs** | jede Änderung bleibt in ihrem Kapitel; aber Übernommenes gilt als erledigt | ein Abgleich für alle auf einmal, mit denselben Konflikten wie bei Paketplänen |
| **Im Verlauf** | es gibt nichts, bevor es dran ist — nichts durchzusetzen; „Trotzdem freischalten“ am Kapitel gibt es schon | braucht einen Sperrzustand je Planübung, der überall gelten muss (Heute, Liste, Workout, Plan-Editor, Kopieren, Export, Bedingung „Tage“) — jede vergessene Stelle ist ein Schlupfloch |

**Was daraus folgt**

- **Keine Sperren im Plan.** Freischalten hat seinen Platz **innerhalb** eines Workouts
  (Pflichtwege, Tore) und am Kapitel („Trotzdem freischalten“), nicht zwischen den Kapiteln im
  Plan der Person — das passt zu Bens Linie der Eigenverantwortung.
- **Auswahl und Test bleiben Bausteine** — die gewählte Übung und ihr Ziel gibt es vorher nicht.
- **A2, das Autorenwerkzeug** (§7): Man baut den Zielplan im Plan- und Ablauf-Editor und ordnet
  jede Übung, jeden Weg und jede Einstellung einem Kapitel zu; der Editor erzeugt die Bausteine.
  So verbindet sich beides: bauen wie ein fertiger Plan, ausliefern als wachsender.
- **A1, die Vorschau „Das kommt noch“** (§7): Der eine echte Vorteil des fertigen Plans — man
  sieht, was kommt — geht ohne Sperren: gerechnet aus den Bausteinen der späteren Kapitel
  (`core.kursplan.aenderungen` auf dem Plan, wie er nach den Kapiteln davor wäre — der Editor
  rechnet seine Vorschau schon so, `core.kursbau.Kurssicht.vorschau`).
- **Offen:** wie eine Korrektur an einem schon übernommenen Kapitel die Person erreicht (heute
  gar nicht) — Katalog P213.

## 13. Stufe 2 und A1 (16.11.2026) — der Test läuft mit der Uhr, „Das kommt noch“

Ben, 16.11.2026: „mach weiter. Wenn es Fragen gibt, bitte stellen“ — Antworten auf die
Rückfrage: **Stufe 2 und Vorschau** in einem Zug · Skizzen T1–T5 und V1 **„Passen“**
(https://claude.ai/artifact/MXp93v2Ya2uYJxvW7Nvc5J; K1–K6 der Stufe 1:
https://claude.ai/artifact/13qzjuaHx6GtRTpV9ayE4L) · was ins Ziel kommt, **legt die Autorin
fest** · bei Vorgabe Anstrengung beendet **ein Knopf** den Lauf.

Vor dem Plan gesucht (Katalog, Entscheidungszeilen): „test“, „bestwert“, „vorschau“, P207–P213,
T141/T142, N171. Gelesen: P207, P213, N171, T142 und §3.3, §7, §12 dieses Dokuments. Nur
gefunden: P90 (Kurs stellt den Plan aus einer Auswahl zusammen, 28.10.), P200 (Material).

### 13.1 Die Vorgabe am Test

`core.kursbloecke.Vorgabe(art, n, bis)` am Test-Block (`Block.vorgabe`, Paketfeld `vorgabe`):
**Eine Größe steht fest und beendet den Lauf, die anderen werden gemessen.** Ohne Vorgabe
bleibt der Test, wie er war (der jüngste Eintrag der Übung, Knopf „Zur Übung“).

| Vorgabe | Paket | der Lauf endet | gemessen |
|---|---|---|---|
| Menge | `{ art = "menge", n = 30 }` | „Fertig — 30 gemacht“; zählt jemand (Sensor, Takt), bei 30 von selbst | Zeit, Skala |
| Zeit | `{ art = "zeit", n = 60 }` | wenn die Zeit ab ist | Wiederholungen, Skala |
| Skala ab n | `{ art = "skala", n = 7 }` | „Bei 7 angekommen“ | Wiederholungen, Zeit |
| Skala höchstens m | `{ art = "skala", bis = 4 }` | „Jetzt über 4“ | Wiederholungen, Zeit |
| Skala von n bis m | `{ art = "skala", n = 5, bis = 7 }` | „Nicht mehr zwischen 5 und 7“ | Wiederholungen, Zeit |

„Bis 10“ gilt als nach oben offen; eine Vorgabe, die nichts vorgibt (0 bis 10, Menge 0), gibt
es nicht (`Vorgabe.from_dict` → `None`, das Werkzeug meldet es als Fehler).

**Was ins Ziel kommt, legt die Autorin fest** (Ben): `feld` am Test — `reps`, `hold` oder
`duration`, also die Vorgabe selbst oder eine gemessene Größe —, mal `faktor`. Die Skala kommt
nie ins Ziel.

### 13.2 Der Lauf und sein Eintrag (`core/kurstest.py`, flet-frei)

- Der Testlauf ist ein **echter Lauf der Übung** — dieselbe Uhr wie beim Üben (Einheit,
  Benachrichtigung, Marken in einer laufenden HRV-Aufnahme), mit einer eigenen, schlanken
  Ansicht (`ui/views/kurs_testlauf.py`, Route `/kurse/<kurs>/<kapitel>/test/<block>/<übung>`).
- Am Ende steht **ein gewöhnlicher, abgeschlossener Eintrag** bei der Übung
  (`core.kurstest.eintrag`): Wiederholungen, Zeit und Skala in ihren Feldern. Bietet die Übung
  eines nicht an, bringt der Eintrag es in **seiner Kopie der Felder** mit (wie die Uhr die
  Zeit) — die Übung selbst ändert sich nicht.
- **Nicht über den offenen Eintrag der Uhr:** `SessionRepo.lauf_eintragen` hängt an einen
  offenen Eintrag nur Wiederholungen und Zeiten an (eine Skala ginge verloren), und frühere
  Sätze desselben Tages stünden im selben Eintrag — der beste Satz wäre dann nicht der Test.
  Der Lauf schreibt darum selbst und vermerkt es in der Zeitleiste (`person/eintrag` mit
  `teil`), damit die Uhr am Ende nichts doppelt einträgt (`ui.uebung_lauf.einzutragen`).
  Neue Ereignisarten gibt es nicht.
- **Der Ablauf** (`ui/views/kurs_testlauf.py`, Stand in `AppState.kurs_test`): „Test starten“
  im Kapitel startet eine **Stoppuhr** der Übung (nie der Aufbau der Ansicht; seit §15.3 bei
  einem gestalteten Test erst die Seite „bereit“, und statt der Stoppuhr wahlweise ein Timer)
  → der Knopf der Vorgabe bzw. „Vorher aufgehört …“ **hält die Uhr an** → die Ergebnis-Seite fragt, was fehlt
  (Wiederholungen, wenn niemand zählte; die Skala — bei „bis n“ ist n vorbelegt) → „Eintragen
  und zurück zum Kapitel“ schreibt den Eintrag, vermerkt ihn und beendet den Lauf; „Verwerfen“
  und „Nochmal“ brechen ab (nichts eingetragen, der Lauf steht unter „Läufe heute“). Ohne
  laufenden Lauf zeigt die Ansicht „bereit“ mit „Start“.
- **Vorgabe Zeit:** dieselbe Stoppuhr, ein Wächter hält sie bei n an (auch wenn die Ansicht
  nicht offen ist) und spielt Countdown und Endsignal nach den Timer-Einstellungen; die Anzeige
  zählt rückwärts. Ein Einmal-Timer ginge nicht: Er trüge selbst ein, bevor Wiederholungen und
  Skala gefragt sind.
- **Vorgabe Menge mit Sensor:** Zählt der Sensor schon bei dieser Übung, tritt die Uhr dem
  Zählen bei, die Karte zeigt die Zahl, und bei n hält die Uhr von selbst an. Den Takt der
  Übung bringt der Test **von sich aus** nicht an — seit §15.2 lässt er sich einstellen („wie
  die Übung“ oder ein eigener); er führt dann, zählt aber nicht.
- **Zurück** (Geste) verlässt die Ansicht, der Lauf läuft weiter; das Kapitel zeigt „Zum
  Test“. ✕ bricht ab.
- **Der Kurs liest wie bisher:** `KursRepo.testwerte` nimmt aus dem jüngsten Eintrag der Übung
  den Wert des Feldes — ein von Hand geschriebener Eintrag zählt darum weiter. Was der Lauf
  sonst gemessen hat, liest die Karte aus demselben Eintrag (`KursRepo.testeintraege`,
  `core.kurstest.lauf_aus`, `neben_text`). Die Folge davon — ein **späterer** gewöhnlicher
  Eintrag löste den Wert des Laufs ab (Katalog P214 a) — ist seit §15.1 behoben: Der Lauf
  hinterlässt seinen Wert als Variable des Kurses.
- **Die Skala ist die der Übung** (ihr Name gilt in allen Texten); hat die Übung keine oder
  heißt sie wie im Vorrat, heißt sie „Anstrengung“. Sie ist Selbstauskunft — die App misst
  sie nicht und deutet sie nicht (§3.3 „Rechtlich“).

### 13.3 Karte und Sammelkarte

- Testkarte (T4): Überschrift „Käfer: bis Anstrengung 7“, der Wert groß, daneben klein, was
  sonst gemessen wurde („in 1:12 · Anstrengung 7“); Knopf „Test starten“ bzw. „Nochmal“.
- Sammelkarte: Die Zeile nennt **die Regel des Kurses** (`core.kurstest.herkunft`): „80 % von
  deinem Test (22 Wdh. bis Anstrengung 7)“. Das gilt auch für Tests ohne Vorgabe, sobald der
  Faktor nicht 1 ist („50 % von deinem Test (90 s)“ — vorher stand dort nur „aus deinem
  Test“); mit Faktor 1 und ohne Vorgabe bleibt „aus deinem Test“, übernommene Zeilen auch.

### 13.4 Editor (T5)

Im Test-Dialog (`ui/views/kurs_bearbeiten.py`, Rechnung `core/kursbau.py`: `Vorgabenwahl`,
`Kurssicht.zielfelder`, `misst`, `test_vorschau`, `test_kurz`):

- **Vorgabe** als Chips **Ohne · Menge · Zeit · Anstrengung** (ein Segmentknopf macht alle
  Segmente gleich breit, „Anstrengung“ passte nicht); Menge als Zahl, Zeit über das vorhandene
  Zeit-Blatt, Anstrengung **ab · höchstens · von–bis** mit −/+. „höchstens 10“ und „von n bis
  10“ bietet der Dialog nicht an — das Paket läse sie als nichts bzw. als „ab n“.
- **„Gemessen wird“** nur lesend; bei einer Übung ohne Wiederholungen fehlen sie.
- **„Ins Ziel kommt“**: Wiederholungen (wenn die Übung welche hat oder die Vorgabe Menge ist)
  und die Zeitfelder der Übung bzw. „Zeit“ — nie die Skala. Beim Umschalten vorbelegt mit den
  Wiederholungen, ohne solche mit dem Zeitfeld; von Hand Gewähltes und das Feld eines
  gespeicherten Tests bleiben, solange sie zur Wahl stehen.
- **Der Faktor („mal“)** steht am Test nur im Kurs mit **Kapitelplänen** (dort rechnet
  `vorlage_anwenden` mit dem des Tests). Im **Kursplan-Kurs** zählt der Faktor des Bausteins,
  der sein Ziel aus dem Test nimmt (`core.kursplan._ziel_aus_test`) — der Dialog verweist
  darauf, statt ein „mal“ ohne Wirkung zu zeigen (Abweichung von Skizze T5).
- **Vorschau „So steht es im Kapitel“**: die Überschrift der Testkarte und, im Kursplan-Kurs,
  die Ziel-Zeilen der Bausteine mit `ziel_aus` auf diesen Test — aus `Kurssicht.vorschau()`,
  nicht nachgebaut. Beispielwert ist die Vorgabe selbst, wenn sie im Feld steht.

### 13.5 Paket

Ein `test` mit `vorgabe` braucht **Formatversion 6** (`core.pakete.nutzt_kursplan`) — eine
ältere App überläse die Vorgabe und nähme irgendeinen Eintrag. `trainingsapp-paket pruefen`
meldet als Fehler eine Vorgabe, die nichts vorgibt, und ein `feld`, das ein Lauf nicht liefert;
als Hinweis eine Vorgabe Menge an einer Übung ohne Wiederholungsfeld. Das Beispiel in
`docs/uebungspakete.md` trägt jetzt eine Vorgabe („bis Anstrengung 7“, davon 80 %).

### 13.6 A1 — „Das kommt noch“ (Skizze V1)

Auf der Kursseite eines Kursplan-Kurses, unter „Dein Kursplan“: je späterem Kapitel, was es am
Plan vorschlagen wird — „+“ Übung dazu, „~“ Einstellung, „→“ Weg. Gerechnet in
`core/kursvorschau.py` mit `core.kursplan.aenderungen`/`anwenden` auf dem Plan, wie er wäre,
wenn man alles übernimmt; wo eine Wahl oder ein Test noch fehlt, steht nur, **dass** etwas
kommt. Nichts wird geschrieben, nichts gesperrt (§12).

## 14. Das Bild des Kursplans im Kurs-Editor (Ben, 16.11.2026)

Ben: „Ist es irgendwie möglich die Karte aus dem Ablauf beim Erstellen des Kurses mit
einzubauen. Beim fertigen Plan sowieso, wo auch dargestellt wird, wieviel vom Plan freigegeben
ist. Beim neu erstellten Kursplan ließen sich dort die Beziehungen setzen. Was ist dafür nötig,
wenn das gut geht, weil schon alles vorhanden ist, bitte einbauen.“

**Was dafür nötig war — und schon da ist:**

- Das **Ablaufbild** der Pläne (`ui/components/ablaufbild.py`) zeichnet jeden Plan aus
  `Ablauf` + Planübungen, kennt „blass“ (`vernebelt`) und meldet Tipps auf Übung und Weg — es
  wird unverändert wiederverwendet, nur gelesen.
- Der **Zielplan** entsteht aus derselben Rechnung wie die Sammelkarte
  (`core.kursplan.aenderungen`/`anwenden`), mit Beispielwahl und Beispielwerten der Vorschau
  im Editor (`Kurssicht.vorschau`). Neu ist nur `core/kursbild.py`: der Plan **nach allen
  Kapiteln** und dazu, welches Kapitel jede Planübung und jeden Weg bringt.
- Die Blätter der Bausteine („Weg“) gibt es im Kapitel-Formular — das Bild öffnet sie.

**Was gebaut ist** (Karte „So wächst der Plan“, `ui/components/kursplan_bild.py`):

- Der Zielplan als Bild; darüber Chips je Kapitel („Anfang“, wenn die Grundlage Übungen hat).
  Was erst ein **späteres** Kapitel bringt, steht blass; darunter „Bis Kapitel 2
  „Erweiterung“: 2 von 3 Übungen im Plan.“ — so ist zu sehen, wie viel vom Plan freigegeben ist.
- Eine Liste (kein Weg) wird der Reihe nach gezeichnet, mit dem Hinweis, dass der erste Weg sie
  zum Workout macht.
- Bei einer Auswahl steht als Beispiel die erste Übung, die zur Wahl steht (wie in der
  Vorschau der Sammelkarte).
- **Wo sie steht:** im Kurs-Formular unter „Der Kurs baut einen Plan“ (nur zum Ansehen, bis
  zum letzten Kapitel; neu gerechnet bei Schalter, Grundlage und Änderungen an den Kapiteln) und
  im Kapitel-Formular unter den Listen und den Knöpfen „+ Im Kapitel / + Am Plan“ (bis zu
  diesem Kapitel; gerechnet aus den **ungespeicherten** Blöcken, neu mit jeder Änderung der
  Bausteine). Die Grundlage aus einem eigenen Plan ist im Bild (Chip „Anfang“, Marken `g:<n>`).
- **Beziehungen setzen** im Kapitel-Formular: Tipp auf eine Übung → das Blatt „Weg im Plan“
  für einen neuen Baustein dieses Kapitels, „Von“ vorbelegt (`Kurssicht.marke_fuer_weg`: eine
  der Gewählten wird zur Block-ID ihrer „Übung dazu“ — der Weg gilt dann für alle Gewählten);
  Tipp auf den Punkt eines Wegs → sein Baustein, wenn er zu diesem Kapitel gehört, sonst die
  Meldung, aus welchem Kapitel er kommt. Eine **blasse** Übung (erst ein späteres Kapitel
  bringt sie) öffnet kein Blatt — ein Weg dieses Kapitels könnte sie nicht nennen. Ein Schritt,
  der nur die Reihenfolge der Liste ist, gehört zu keinem Baustein — die Karte sagt es.
- **Übungen ohne Weg:** Sobald ein Weg den Ablauf eigen macht (er folgt nicht mehr der Reihe
  der Liste), hängt eine spätere „Übung dazu“ nicht mehr von selbst an der Kette — im Workout
  käme sie nicht dran. Das Ablaufbild zeichnet sie nicht; die Karte nennt sie darunter („Ohne
  Weg im Ablauf …“, `Planbild.lose`), ein Tipp ist „Weg von hier“. Das Paket-Werkzeug meldet
  den Fall noch nicht.
- **Höhe und Gesten:** Das Bild ist so hoch wie die Zeichnung (bis 900 px), das Formular rollt.
  Zoomen ist in dieser Karte aus (Mausrad und zwei Finger bewegen die Seite); seitlich schieben
  geht, wenn die Zeichnung breiter ist als die Karte.

**Was es nicht ist** (bleibt bei §7, Stufe 4/5 und A2): kein Bild der **Kapitel** (Kursablauf
mit „Wenn …“), kein Ziehen von Übungen im Bild, kein Bauen „vom fertigen Plan aus“ mit
Zuordnung zu Kapiteln. Die Lagen im Bild ordnet es selbst (`core.ablauf.layout`); gemerkt wird
nichts.


## 15. Der Test, flexibel gestaltet · der Testwert als Variable (Ben, 16.11.2026 spät)

Ben, auf die Fragen zu Stufe 2 (P214) und die Skizzen F1–F4: „Der Test muss flexibel gestaltet
werden können“ · „Mach das“ · „Ja, aber Timer ist tatsächlich das wichtigste“ · Ausführung:
„beides. Kann vorgegeben sein; Varianten können vorgegeben sein, oder frei“ · Takt führt nur,
die Person bestätigt die Zahl: „Ok“ · „Übungsumgebung/Parameter können mit in den Test“ ·
„Testwert wird als Variable gespeichert und kann irgendwo verwendet werden im Kurs/Planbau“ ·
„Die Übung hat erstmal ihren eigenen Wert. Wenn man eine Übung macht, kann man diesen Wert
weitergeben und übernehmen. Nimm den Plan-/Kursbauplan als grafisches Programmieren, ähnlich
wie bei LabView. Wir dürfen hier gar nicht zu kompliziert sein, Dinge mit Standardwerten
versehen. Überschreiben ist möglich.“

**Leitbild daraus:** Ein Baustein hat Eingänge und einen Ausgang wie ein Knoten im
grafischen Programmieren. Jede Einstellung hat eine **Vorgabe**, die ohne Zutun gilt, und lässt
sich **überschreiben**. Ein Test gibt einen Wert aus; den kann jeder Baustein danach
verwenden.

### 15.1 Der Testwert ist eine Variable des Kurses (Migration 065)

- **Bisher** las der Kurs den Wert eines Tests jedes Mal neu aus dem jüngsten Eintrag der
  Übung seit dem Erreichen des Kapitels. Wer nach dem Test gewöhnlich weiterübte, hatte einen
  anderen „Test“ (P214 a, nachgestellt: 22 im Test, danach 10 geübt → „Dein Test: 10“).
- **Jetzt** hinterlässt der Test seinen Wert: Tabelle `course_variable` (je Profil und Kurs,
  gerätelokal wie `course_progress`; `name` = `core.kursbloecke.wert_schluessel` — die Block-ID
  des Tests, bei „die gewählte“ `<block>:<übung>`; `value` ohne Faktor; `entry_id` = der
  Eintrag des Laufs). `KursRepo.variablen`, `variable_setzen`.
  - **Der Testlauf** setzt sie beim „Eintragen“ (`ui/views/kurs_testlauf.eintragen`);
    **„Nochmal“** überschreibt sie.
  - **Ohne Lauf** (ein Test ohne Vorgabe und ohne Gestaltung) gilt die Vorgabe „der eigene Wert
    der Übung“: ihr jüngster Eintrag seit dem Kapitel — wie bisher. **Mit dem Abschließen des
    Kapitels** wird er festgehalten (`KursRepo._variablen_festhalten`); danach ändert
    gewöhnliches Weiterüben ihn nicht mehr.
  - **Verwenden:** `KursRepo.testwerte` nimmt die Variable vor dem jüngsten Eintrag,
    `testeintraege` zeigt den Eintrag der Variable (nie einen späteren). Die Rechnung des
    Kursplans bekommt die Werte **aller** erreichten Kapitel (`_kursplan_eingaben`) — ein
    Baustein mit `ziel_aus` darf den Test eines früheren Kapitels nennen, in jedem Kapitel
    danach. Der Faktor gehört dem, der verwendet, nicht der Variable.
  - **„Von vorn beginnen“** löscht die Variablen des Kurses — der neue Durchlauf misst neu.
- **Der Wert für den Plan** — ganz, Anteil, von Hand — ist am 17.11.2026 dazugekommen (§17,
  Migration 066). Nicht gebaut: weitere Abnehmer als das Ziel (Bedingungen an Wegen, Dauer
  eines Timers).

### 15.2 Was am Test einstellbar ist (`core/kursbloecke.Block`, `art = "test"`)

| Einstellung | Vorgabe (nichts gesetzt) | wie die Übung | eigene Angabe |
|---|---|---|---|
| **Uhr** — womit der Test läuft | Stoppuhr | `wie_uebung` enthält `"uhr"`: ihr Timer | `timer` (wie bei einer Planübung, eingebettet) |
| **Takt** | keiner | `"takt"`: ihr Takt | `takt` |
| **Ausführung** — Variante, Seite, Gewicht … | keine | `"parameter"`: ihre Parameter, die Person wählt frei | `ziel` = **vorgegeben** (Feld → Wert), `felder` = **frei** zu wählen |
| **Hinweis vor dem Start** | keiner | — | `text` |

- Eine eigene Angabe geht vor „wie die Übung“. Ohne jede Angabe ist der Test der von §13 —
  bestehende Tests ändern sich nicht.
- **`Block.gestaltet`**: irgendetwas davon ist gesetzt. **`Block.laeuft`**: Vorgabe **oder**
  gestaltet — dann ist der Test ein Lauf mit der Uhr, auch ohne Vorgabe (ein Timer beendet
  ihn, sonst „Fertig“).
- **Timer und Vorgabe „Zeit“ zusammen gibt es nicht:** Läuft der Test mit einem Timer, ist der
  Timer die Zeit. Der Editor bietet „Zeit“ dann nicht an; kommt die Kombination aus einem
  Paket, gilt der Timer (`trainingsapp-paket pruefen` gibt einen Hinweis). Vorgabe Menge und
  Anstrengung gelten mit Timer weiter und können vorher beenden.
- **Der Takt führt, er zählt nicht** („Ein Soll ist keine Messung“,
  `.claude/rules/sensor_takt.md`): Der Test endet nicht von selbst mit dem Takt. Seine Runden
  stehen im Ergebnis als **Vorschlag** bei den Wiederholungen; die Person bestätigt oder ändert.
- **Ausführung** ist, was der Lauf nicht misst: nicht Wiederholungen, Halte- und Zeitfelder,
  Skala (nach der Art verglichen, `core.result_spec.basis_key`), nicht Freitext, nicht
  „Vollständig“. Sie kommt in den Eintrag des Tests; bietet die Übung ein Feld nicht an,
  bringt der Eintrag es in seiner Kopie mit (wie Zeit und Skala in §13.2).

### 15.3 Der Lauf (`core/kurstest.py`, `ui/views/kurs_testlauf.py`; Skizzen F2–F4)

- **Rechnung** (flet-frei): `uhr_fuer(block, uebung)` (eigener Timer → Timer der Übung →
  Stoppuhr), `vorgabe_fuer(block, profil)` (neben einem Timer keine „Zeit“),
  `takt_fuer(block, uebung)`, `takt_runden(profil, takt, gelaufen_s)` (nur Runden aus
  zählenden Abschnitten), `ausfuehrung_fuer(block, uebung)` → `Ausfuehrung(fest, frei,
  vorbelegt)`, `ausfuehrung_aus(result, spec)`, `lauf_satz` (der Satz der Testkarte),
  `karten_ueberschrift`.
- **Bereit:** Ein gestalteter Test startet nicht sofort, sondern zeigt erst die Seite vor dem
  Start: Vorgabe, der Hinweis des Kurses, „So machst du den Test“ (Vorgegebenes zum Lesen,
  Freies zum Wählen — Chips für Variante und Seite, − / + für Zahlen), „Takt läuft mit“,
  „Start“. Ein Test nur mit Vorgabe startet wie bisher mit dem Tipp im Kapitel.
- **Läuft mit Timer:** Es ist der echte Timer der Einheit — Abschnitte, Klänge und Marken wie
  beim Üben. Ist er durch, erscheint das Ergebnis von selbst („Der Timer ist durch“, die Zeit
  „vom Timer“); die Einheit beenden erst „Eintragen“ und „Verwerfen“. „Vorher aufgehört …“
  bleibt.
- **Läuft mit Takt:** sichtbar und hörbar wie im Fokus der Übung; er zählt nicht und beendet
  nichts. Im Ergebnis stehen seine Runden als Vorschlag („Der Takt lief 7 Runden. Stimmt die
  Zahl?“) mit − / +; „Eintragen“ bestätigt. Zählt der Sensor, gilt der wie bisher.
- **Ausführung:** Was vor dem Start gewählt ist, steht im Lauf unter der Vorgabe, im Ergebnis
  und im Eintrag; die Testkarte nennt sie danach neben dem Wert.
- **Die Sammelkarte nennt, wie der Test gemacht wurde** (Skizze F4 unten, gebaut
  17.11.2026): „Ziel für Käfer: 18 Wiederholungen — 80 % von deinem Test (22 Wdh. bis
  Anstrengung 7 · links · 10 kg)“. Die Ausführung kommt aus dem Eintrag des Tests
  (`KursRepo._test_ausfuehrung`, `core.kurstest.ausfuehrung_aus`) und geht als ``zusatz`` in
  die Rechnung (`core.kursplan.aenderungen`, `anwenden`); ins Ziel der Planübung kommt weiter
  nur die Zahl.

### 15.4 Der Editor (`core/kursbau.py`, `ui/views/kurs_bearbeiten.py`; Skizze F1)

- Im Test-Dialog der Abschnitt **„So läuft der Test“**: Uhr · Takt · Ausführung, je ein
  Auswahlfeld mit Vorgabe · „Wie die Übung“ · eigene Angabe; darunter klein, was gilt. Die
  eigene Angabe öffnet ein Blatt über dem Dialog: den Timer-Editor (derselbe wie am Baustein,
  `baustein_form.timer_editor_teil`), das Takt-Blatt („Gilt: In diesem Test“), für die
  Ausführung je Parameter „vorgegeben“ (mit Wert) oder „frei“. Dazu „Hinweis vor dem Start“
  (`text`).
- **Mit einem Timer steht „Zeit“ nicht zur Wahl**; eine gesetzte Vorgabe „Zeit“ wird beim
  Wechsel zu „Ohne“, und eine Zeile sagt es (`core.kursbau.vorgabe_wahl`, `Laufwahl`).
- **„Die gewählte“:** frei wählbar ist, was irgendeine Übung der Auswahl hat; vorgeben lässt
  sich nur, was alle haben, und nie die Variante — wie am Baustein „Übung dazu“.
- „Gemessen wird“, „Ins Ziel kommt“ und die Vorschau fragen den Lauf (`kurstest.gemessen`);
  die Vorschau und die Zeile der Liste nennen Takt und Timer („· mit Takt · Timer 2:15“).

### 15.5 Paket und Adressen

- Der gestaltete Test braucht Formatversion 6 (`core.pakete.nutzt_kursplan`);
  `trainingsapp-paket pruefen` meldet Unbekanntes in `wie_uebung`, gemessene Felder in `ziel`
  und `felder` und einen Timer neben der Vorgabe „Zeit“ (`paket_werkzeug._gestaltung_pruefen`).
- **IDs in der Adresse des Tests sind frei wählbar:** Ein Test-Block namens „timer“ öffnete
  die Timer-Ansicht statt des Tests. Die Wörter „timer“, „anhang“, „paketmedium“ zählen in
  ``/kurse/<kurs>/<kapitel>/test/<block>/<übung>`` jetzt erst hinter den IDs (`ui/app.py`).

## 16. Der Kursbau als grafisches Programm (Ben, 16.11.2026) — Leitbild und nächste Schritte

Ben: „Nimm den Plan-/Kursbauplan als grafisches Programmieren, ähnlich wie bei LabView. Wir
dürfen hier gar nicht zu kompliziert sein, Dinge mit Standardwerten versehen. Überschreiben ist
möglich.“ · „Die Übung hat erstmal ihren eigenen Wert. Wenn man eine Übung macht, kann man
diesen Wert weitergeben und übernehmen.“ · „Testwert wird als Variable gespeichert und kann
irgendwo verwendet werden im Kurs/Planbau.“

Dieser Abschnitt ordnet, was gebaut ist, nach diesem Bild — und sagt, was daraus als Nächstes
folgt. Er ändert kein Verhalten; Neues steht als Vorschlag da.

### 16.1 Bausteine als Knoten: Eingänge, Ausgang, Vorgaben

Ein Baustein nimmt etwas entgegen, tut eines und gibt etwas weiter. Jede Einstellung hat eine
**Vorgabe**; überschrieben wird nur, was anders sein soll.

| Baustein | Eingänge | Ausgang | Vorgabe ohne Angabe | Überschreiben |
|---|---|---|---|---|
| **Auswahl** (`auswahl`) | Übungen zur Wahl, wie viele | die **Wahl** der Person | 1 aus den genannten | Anzahl |
| **Test** (`test`) | eine Übung — fest oder „die gewählte“ einer Auswahl | ein **Wert** (Variable, §15.1) | jüngster Eintrag der Übung; als Lauf: Stoppuhr, kein Takt, keine Ausführung | Vorgabe (Menge · Zeit · Skala), Uhr, Takt, Ausführung, Hinweis (§15.2) |
| **Übung dazu** (`plan_uebung`) | eine Übung — fest oder die gewählte; hinter welcher Marke; optional ein Wert (`ziel_aus`) | eine **Planübung** mit Marke | ans Ende; sie folgt der Übung (Ziel, Parameter, Timer, Takt wie dort) | Platz, Ziel (fest oder Wert × Faktor), Parameter, Timer, Takt |
| **Einstellen** (`plan_einstellen`) | eine Marke oder der Plan; optional ein Wert | — (ändert, was da ist) | nichts — nur was genannt ist | Ziel, Parameter, Timer, Takt, Übergang, Pause |
| **Weg** (`plan_weg`) | zwei Marken (von, zu) | ein **Weg** im Ablauf | ein freier Weg | Auslöser, Pflicht, von selbst, Beschriftung |

Verbunden sind sie über **Namen**: die Block-ID einer Auswahl (`aus`), die Marke einer
Planübung (`hinter`, `an`, `von`, `zu`) und die Variable eines Tests (`ziel_aus`). Ein
Baustein darf nur nennen, was davor entsteht (`trainingsapp-paket pruefen` meldet es).

**Die Person bleibt am Schalter:** Aus dem Ausgang eines Bausteins wird am Plan erst etwas,
wenn sie die Zeile der Sammelkarte übernimmt (§3, „Nichts am Plan ohne Tipp“).

### 16.2 Variablen — was es gibt und was folgen kann

- **Gebaut:** Der Wert eines Tests (§15.1). Abnehmer ist das Ziel einer Planübung
  (`ziel_aus` mit `faktor`), in jedem Kapitel nach dem Test.
- **Vorschlag (Stufe V, nichts davon gebaut):**
  1. **Auslöser eines Wegs aus einer Variable** — „weiter nach 80 % deiner Test-Wiederholungen“
     statt einer festen Zahl im Baustein „Weg“ (`kante.n` aus einer Variable × Faktor).
  2. **Dauer eines Timers aus einer Variable** — „halte 80 % deiner Testzeit“ als Abschnitt
     des Timers, nicht nur als Ziel.
  3. **Ein Wert von Hand** — die Person trägt den Wert selbst ein oder ändert ihn, ohne den
     Test zu wiederholen („Überschreiben ist möglich“). **Gebaut 17.11.2026 als W3 (§17).**
  4. **Die Antwort einer Frage als Variable** — das ist Stufe 3 (Antworten speichern, Folgen)
     in diesem Bild: Die Antwort ist ein Ausgang wie der Testwert.
  5. **Im Editor sichtbar:** bei „Ziel aus …“ die Liste der Variablen des Kurses mit ihrem
     Baustein und Kapitel, statt nur der Tests desselben Kapitels.
- **Grenze bleibt:** Variablen kommen aus Einträgen, Selbstauskunft und eigener Wahl — nie aus
  Messwerten (§8; `docs/recht/00_zweckbestimmung.md`). Eine Variable aus Herzfrequenz oder HRV,
  die Plan oder Workout steuert, gibt es nicht.

### 16.3 Ein Bild, dieselben Gesten — Plan und Kurs (Katalog P217)

Ben, 16.11.2026: „Versuche den Ablaufplan in Plan und Kurs noch weiter zu vereinheitlichen“;
auf die Skizzen G1–G4: gedrückt halten = „Menü“ · „Slot weglassen“ · Weg-Leiste unter dem Bild
„Ja. Hauptknoten wieder Blatt“ · im Kurs-Editor dieselben Gesten: „ja“.

| Geste im Bild | im Plan (Reiter „Ablauf“) | im Kurs-Editor („So wächst der Plan“) |
|---|---|---|
| Punkt unter einer Übung auf eine andere ziehen | ein Weg | nach kurzer Bestätigung der Baustein „Weg“ im bearbeiteten Kapitel |
| Tipp auf den Punkt eines Wegs | seine Einstellungen in der Leiste unter dem Bild | sein Baustein |
| Tipp auf den Hauptknoten mit mehreren Wegen | das Blatt mit allen Wegen | — |
| gedrückt halten auf einer Übung | ihr Menü (einstellen, Beiname, nur ihren Weg, Start, herausnehmen) | ihr Menü (Weg von hier, Weg zum Ende, Einstellen als Baustein) |
| Kachel aus der Leiste auf eine Übung | neue Übung dahinter | — (Übungen bringt der Baustein „Übung dazu“) |

**Stand 16.11.2026 nachts: gebaut** — im Plan-Reiter (`docs/plan_verzweigungen.md` §8.13
Punkt 6) und im Kapitel-Formular (`ui/components/kursplan_bild.py`,
`ui/views/kurs_bearbeiten.weg_gezogen`, `einstellen_an`; Rechnung
`core.kursbild.weg_baustein`). Im Kurs steht „Weg zum Ende“ im Menü statt als Ziel am Bildrand
(das Bild ist oft höher als der Bildschirm), „noch einmal“ und „zurück“ gibt es dort nicht
als Baustein, und „Start“ lässt sich nicht versetzen. Im Kurs-Formular (ohne Kapitel) bleibt
das Bild zum Ansehen.

Die Zeichnung ist dieselbe (`ui/components/ablaufbild.py`); was eine Geste bewirkt, sagt der
Aufrufer über Rückrufe. Im Plan ändert sie den Ablauf sofort, im Kurs entsteht ein Baustein —
am Plan der Person ändert sich dadurch nichts ohne ihren Tipp.

### 16.4 Reihenfolge, wie ich sie vorschlage

1. **Fertig bauen, was entschieden ist:** flexibler Test (Editor, Lauf), Bedienen im Bild im
   Plan-Reiter, danach im Kurs-Editor (B1). Web-Fotos, Gerätetests T143/T144.
2. **Stufe V, Punkte 5 und 3** (Variablen im Editor sichtbar; Wert von Hand) — klein, macht
   das Bild von §16.1 im Editor erst sichtbar. Punkt 3 ist als **W3** gebaut (§17, 17.11.2026);
   Punkt 5 braucht Bens Wort (Skizzen W1, W2).
3. **Stufe 3** (Antworten als Variable, Folgen) — der nächste große Baustein; mit Skizzen.
4. **A2** („vom fertigen Plan aus“) — liegt nach B1 näher: Wer im Bild Wege ziehen kann, kann
   dort auch Übungen einem Kapitel zuordnen. Mit Skizzen.
5. Stufe V 1–2, Stufe 4/5 nach Bedarf.

## 17. Wert für den Plan — ganz, Anteil, von Hand (W3; Ben, 17.11.2026)

> „Nimm W3. Die Werteintragung kommt normal direkt nach einem Test. Wichtig dabei – im Moment
> geht die prozentuale Angabe. Für viele ist das verwirrend. Wenn ein Test gemacht wird bis 7,
> ist das für eine Runde schon fast zu viel, dann braucht es eine Abstufung, ok. Wegen
> Ehrgeizprobleme werden viele nicht bei 5 Schluss machen, wenn man danach fragt. Aber: Testen
> – Wert wird genommen und kann ganz genommen werden – prozentual abgeändert – manuell
> eingegeben (mit Klick und per Tastatur)“

Bis hierher rechnete der Kurs still: „80 % von deinem Test“ stand erst in der Sammelkarte. Jetzt
sagt die Person **direkt nach dem Test**, mit welcher Zahl ihr Plan weitergeht — und sieht die
Zahl, bevor sie etwas übernimmt.

### 17.1 Die Karte „Wert für den Plan“ (`ui/components/planwert.py`)

- **Drei Wege, einer ist gewählt:** **Ganz** (der gemessene Wert) · **Anteil** (Prozent vom
  Wert, − / + in 5-%-Schritten oder getippt; daneben steht die Zahl, die herauskommt) · **Von
  Hand** (eine Zahl in der Einheit des Felds, − / + oder getippt: Wiederholungen in Einern,
  eine Zeit in 5-Sekunden-Schritten und als ``m:ss``).
- **Vorgewählt ist, was der Kurs sagt** (`core.kursbloecke.anteil_vorgabe`,
  `planwert_vorgabe`): im Kursplan der Faktor des ersten Bausteins, der sein Ziel aus dem Test
  nimmt, im Kapitelplan der Faktor des Tests — „Anteil 80 %“, wenn der Kurs mindert, sonst
  „Ganz“. „Anteil“ beginnt beim Anteil des Kurses (ohne einen: 100 %), „Von Hand“ bei der
  Zahl, die gerade dasteht. Die App erfindet keinen Abschlag.
- **Ein Satz:** „Der Plan nimmt 18 Wdh.“ — darunter klein „Dein Eintrag vom Test bleibt, wie
  er ist.“ Alles Weitere steht hinter dem (i) (`components/hilfe.PLANWERT_MD`).
- **Wo sie steht:**
  1. auf der **Ergebnis-Seite des Testlaufs** (`ui/views/kurs_testlauf.py`), unter der Skala
     und vor „Eintragen“. Sie erscheint, sobald der Test einen Wert hat (bei „bis Anstrengung
     7“: wenn die Wiederholungen getippt sind) und folgt ihm. „Eintragen“ speichert Eintrag,
     Variable und Wahl.
  2. im **Kapitel** an der Testkarte hinter **„Wert ändern“** (`ui/components/kursblock.py`,
     Skizze W3): Die Karte klappt in der Testkarte auf, „Übernehmen“ merkt die Wahl,
     „Abbrechen“ nicht. Unter dem Testwert steht dann „Für den Plan: 20 Wdh. — von Hand“.
- **Nur, wo aus dem Wert ein Ziel wird** (`core.kursbloecke.wert_wird_ziel`): Ein Baustein
  nimmt sein Ziel aus dem Test, oder das Kapitel hat Plan-Vorlagen. Hinterlässt ein Test nur
  seinen Wert, gibt es weder Karte noch „Wert ändern“.

### 17.2 Die Rechnung (flet-frei: `core/kursbloecke.py`, `core/kursplan.py`, `core/kurstest.py`)

- **Ohne Wahl bleibt alles, wie es war:** Kapitelplan = Testwert × Faktor des Tests, Kursplan
  = Testwert × Faktor des Bausteins. Kein Kurs von früher ändert sein Verhalten. Wer in der
  Karte wieder wählt, was der Kurs sagt, hat keine Wahl getroffen (`ist_vorgabe`).
- **Mit Wahl ist ihr Wert das Ziel** (`Planwert`, `planwert`, `ziel_im_plan`) — überall, wo der
  Kurs sonst aus diesem Test rechnet, statt Testwert × Faktor. „Ganz“ und „Anteil“ folgen dem
  Testwert, „von Hand“ bleibt die Zahl der Person. Auf ganze Einheiten, mindestens 1 (wie
  `ziel_aus_test`).
- **Die Sammelkarte nennt die Wahl statt der Regel des Kurses** (`core.kurstest.herkunft`):
  „dein Wert von Hand (20 Wdh.) — Test: 22 Wdh. bis Anstrengung 7 · links · 10 kg“ · „90 % von
  deinem Test (22 Wdh. …)“ · „dein Test, ganz (22 Wdh. …)“.
- **Eine neue Wahl wird wieder angeboten** (`core.kursplan._Lauf._ziel_aus_test`): Die Zeile
  des Ziels trägt mit einer Wahl deren Stempel in der ID (``<marke>#ziel@<stempel>``) — sie
  ist eine eigene Zeile, auch wenn das Ziel aus dem Test schon übernommen war. Nichts ändert
  sich ohne Tipp; hat die Person das Ziel im Plan selbst geändert, fragt die Zeile wie jede
  andere („Du hast 15 eingestellt. Der Kurs schlägt 22 vor.“, Vorgabe „lassen“). Ohne Wahl
  bleibt ein übernommenes Ziel übernommen — auch nach „Nochmal“.
- **Kapitelplan:** „Plan anlegen“ setzt die Wahl als Ziel (`core.kursbloecke.vorlage_anwenden`
  mit ``planwerte``). Ist der Plan angelegt, steht das Ziel im Plan und wird dort geändert —
  „Wert ändern“ gibt es dann nicht mehr.
- **Die Vorschau „Das kommt noch“** rechnet mit denselben Zielen (`core.kursvorschau`).

### 17.3 Daten (Migration 066, gerätelokal wie die Tabelle)

- `course_variable` bekommt ``wie`` (leer = Vorgabe · ``ganz`` · ``anteil`` · ``hand``),
  ``plan_value`` (die Zahl von Hand), ``anteil``, ``plan_set_at`` (der Stempel der Wahl) und
  ``floating``. `core.kurse.Kursvariable` trägt sie (`planwert`); `KursRepo.planwerte`,
  `planwert_setzen`, `planwert_loeschen`.
- **Ein neuer Testlauf („Nochmal“) setzt die Wahl zurück** (`variable_setzen`) — die Karte
  kommt gleich wieder. „Von vorn beginnen“ löscht sie mit den Variablen.
- **Ein Test ohne Lauf** hat bis zum Abschluss des Kapitels keine Variable; die Wahl braucht
  trotzdem einen Platz. Sie steht in einer **schwebenden** Zeile (``floating = 1``): Der
  Testwert bleibt der jüngste Eintrag der Übung, „ganz“ und „Anteil“ folgen ihm, „von Hand“
  bleibt. Der Abschluss des Kapitels hält den Wert fest, die Wahl bleibt
  (`_variablen_festhalten`); „zurück zur Vorgabe“ löscht eine schwebende Zeile ganz.
- **Paket, Export, Sync:** nichts — die Wahl gehört dem Profil auf dem Gerät. Am Paketformat
  ändert sich nichts.

### 17.4 Recht

Grundlage sind der Wert des Tests als Zahl (ein gewöhnlicher Eintrag, mit der Skala als
Selbstauskunft) und die Wahl der Person — nie Messwerte (§8, `docs/recht/00_zweckbestimmung.md`
„Vorschlag nach der Belastung“). Die App nennt die Regel und deutet die Zahl nicht: „zu viel“,
„überlastet“ kommen nicht vor, sie schlägt auch keinen Abschlag von sich aus vor. Geändert wird
der Plan nur auf Tipp.

### 17.5 Offen

- **Mehrere Abnehmer mit verschiedenen Faktoren:** Rechnet ein Kurs an mehreren Stellen mit
  verschiedenen Anteilen aus demselben Test (Kapitel 2: 80 %, Kapitel 3: 90 %), gilt die Wahl
  der Person an **allen** — die Stufung des Kurses ist damit weg. Vorgewählt wird der Anteil
  des ersten Abnehmers. Ob die Wahl stattdessen den Testwert ersetzen soll (und die Faktoren
  obenauf bleiben), ist Bens Entscheidung.
- **Im Editor** steht der Anteil weiter am Baustein („Ziel aus dem Test × 0,8“) bzw. am Test
  („Ziel in % des Tests“). Dort steht seit dem 17.11.2026 dabei, dass er die Vorgabe ist:
  „Nach dem Test sieht die Person, was der Plan nimmt, und kann es ändern — ganz, Anteil oder
  von Hand“ (`views/kurs_bearbeiten.ANTEIL_IST_VORGABE`, `components/baustein_form.py`).
- Gerätetest T143: Tastatur (verdeckt sie die Karte auf der Ergebnis-Seite?), Zahlentastatur
  mit Doppelpunkt bei einer Zeit.
