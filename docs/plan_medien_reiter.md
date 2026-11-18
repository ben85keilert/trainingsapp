# Planung: Reiter „Medien“ im Plan, Übersicht, Medien am Plan, Verkleinern (17.11.2026)

Ben, 17.11.2026, in mehreren Schritten:

- „In den Plänen gibt es drei Reiter Übungen – Timer – Ablauf. Lohnt sich ein weiterer Reiter
  ‚Material‘, wo alle Dateien zu einer Übung, für den Plan oder von dem korrespondierenden Kurs
  verfügbar sind?“
- „Medien ist kürzer als Material als Text für den Reiter, wenn man Text auch als Medium
  akzeptiert. Eine Übersicht der Links/Videos/evtl. Anweisungen/Texte in dem zusätzlichen
  Reiter, eine Übersicht über die Bilder/Videos/Texte/Animationen der Übungen, dem Plan
  zugehörig, vom Kurs kommend wäre hilfreich. Ein Medieneditor ebenfalls, um Videos z. B. per
  ffmpeg zu komprimieren, wenn sie zu groß sind. Schneiden und Editing dann extern, aber
  Verkleinern.“
- Auf drei Rückfragen: „1. Medien überall. Beim Bearbeiten einer Übung gibt es schon den
  Materialreiter. 2. Ja [erst die Übersicht aus dem, was es gibt, dann eigene Medien am Plan,
  dann Verkleinern]. 3. Ja [am Handy der vorhandene Umwandler, am Rechner ffmpeg im
  Paketwerkzeug], berücksichtige, dass es Android und Apple geben wird am Smartphone.“
- Auf die Fragen a–f (§6) und zum Verkleinern: „Ist es nicht möglich, z. B. Framerate, dpi,
  Auflösung usw. nach grobem Schema einzustellen mit Angabe, wie groß das Video sein wird? Das
  konvertierte Video wird erstmal kopiert, das ursprüngliche bleibt, damit man das neue
  anschauen kann und neu erstellen, falls es doch zu unscharf ist.“ — dann: „Finde gute
  Lösungen und arbeite das selbständig aus.“

**Stand:** Stufe 0 gebaut (17.11.2026), Stufe 1 gebaut (17.11.2026, Gerätetest T148), Stufe 2
gebaut (18.11.2026, Gerätetest T149), Stufe 3 gebaut für Rechner und Android (18.11.2026,
Gerätetest T150; dazu der Werkzeugschritt `trainingsapp-paket verkleinern`; iPhone offen, §5). Gebaut auf dem Zweig
`worktree-medien-reiter` (eigener Worktree, `CLAUDE.md` „Große Änderungen im eigenen
Worktree“). Skizzen:
<https://claude.ai/artifact/CvfAkLSzXyQfip8BMftrWD>. Katalog **P225**.

**Bens Antworten, 17.11.2026 abends** (Fragen aus §6):

| Frage | Antwort | Folge |
|---|---|---|
| a) Reihenfolge der Reiter | „ja“ (Plan · Uhren · Medien · Ablauf) | §3 |
| b) Medien am Plan: wann zeigen? | „ja“ (Knopf am Kopf des Plans und im Start-Bild des Workouts; von selbst nur vor dem Start) | §4 |
| c) Ab wann „groß“? | „Ist noch zu groß. Das Bild muss auf ein Tablet/Smartphone passen.“ | §3 „Groß“: über „Mittel“ (720p) mit einem Viertel Spielraum — meine Lesart, unten begründet |
| d) Plan gelöscht → Medien privat? | „ok“ | §4 |
| e) Kursplan: welche Kapitel? | „nur erreichte“ | §3 |
| f) Inhalte der Wege? | „mit rein beim Workout/Kurs, wo sie hingehören. Es wäre gut, wenn man sieht, was wo angeboten wird, unterteilt nach Herkunft“ | §3: Gruppen nach Herkunft, je Stück „wo“ |
| Verkleinern | Schema mit Größenangabe; Original bleibt, das neue ansehen, neu erstellen | §5 |

**Nachgesehen, ob es dazu schon etwas gibt.** Katalog, nur Entscheidungszeilen
(`grep -n "^| P" docs/offene_fragen.md | grep -i …`): Stichwörter *material · von selbst
zeigen · gesehen · erklärvideo* und *verkleiner · komprim · iOS · Apple · Reiter · Dateigröße ·
zu groß*. **Ganz gelesen:** P200, T134; `docs/plan_medienrollen.md` (Kopf, §1, §2.2, §2.3, §4–§6),
`docs/plan_uhr_fokus.md` §10.6. **Nur gefunden:** P160, P181 (Videos fürs Paket bereinigen),
P203, P209, P27 (iOS: Laufendes), P44. **Code gelesen:** `core/material.py`, `core/models.py`
(`Media`, `Plan`), `core/paketmedien.py` (Endungen, Grenzen, `groesse_text`),
`core/anhaenge.py` (`Qualitaet`), `core/kursbloecke.py` (`Block`, Weg-Bausteine mit Kante),
`core/kursplan.py` (wie ein Weg-Baustein Wege setzt), `data/kurse.py` (Kapitelstände,
`kurs_und_kapitel`), `data/paketmedien.py` (Ablage, Aufräumen, geladene Link-Videos),
`data/repositories.py` (Papierkorb und Grabstein eines Plans), `ui/paketdatei.py`,
`ui/components/material.py`, `material_rolle.py`, `medienliste.py`, `plan_reiter.py`,
`editor_reiter.py`, `views/plan_einstellen.py` (Reiter „Medien“), `erweiterungen/flet_hochladen`
(Python-Seite ganz, Dart- und Kotlin-Seite beim Verkleinern). **Nicht gelesen:**
`core/bereinigen.py` über die Fundstellen hinaus, `paket_werkzeug.py`.

---

## 1. Befund: Wo heute Medien liegen

| Wo | Was | Fundstelle | Reist im Paket |
|---|---|---|---|
| **Übung** | Links, Paketdateien (Bild, Video, Ton, PDF) mit Rolle, „von selbst zeigen“, „ersetzt“ | `Exercise.media`, `core/models.py` | ja |
| Übung | Beschreibung in Abschnitten (Text) | `core/beschreibung.py` | ja |
| Übung | **Bild der Bewegung** (Animation), **Symbol** als eigenes Bild | `source = local`; `exercise.image_path` | **nein** — nur auf dem Gerät |
| **Planübung** | Anweisungen (Abschnitte) und eigene Links/Dateien; kann ein Stück der Übung ersetzen | `PlanItem.description`, `PlanItem.media` | ja |
| **Plan** | nur der Beschreibungstext — **keine Medien**; gezeigt wird er nirgends | `Plan.description` | ja |
| **Weg im Ablauf** | Text und **ein** Link; ein Weg-Baustein des Kurses kann ihn mitbringen | `Kante.inhalt` (`core/ablauf.py`), `Block.kante` | ja |
| **Kurs** | Blöcke „Text“ und „Medium“ im Kapitel; der Editor nimmt für ein Medium nur eine https-Adresse | `core/kursbloecke.py`, `views/kurs_bearbeiten.py:331` | ja |

Was fehlt:

- **Kein Ort zeigt alles auf einmal.** Welche Übungen eines Plans Medien haben, was davon von
  selbst aufgeht und wie groß die Dateien zusammen sind, sieht man nur, indem man jede
  Planübung öffnet.
- **Größe ist nirgends sichtbar**, bevor man exportiert. Ein Paket darf höchstens 300 MB
  haben (`core/paketmedien.py:58`, `MAX_ZIP_BYTES`).
- **„Datei wählen …“ nimmt die Datei, wie sie ist** (`views/plan_einstellen.py:384-390`,
  `ui/paketdatei.ablegen`: bereinigt, nicht verkleinert). Die **Kamera der App** nimmt dagegen
  schon mit fester Bitrate auf (`core/anhaenge.Qualitaet`: rund 3,4 · 6,5 · 15,7 MB je Minute),
  und die **Fotoauswahl** verkleinert Videos auf dieselben Stufen
  (`erweiterungen/flet_hochladen`: eigene Kotlin-Klasse mit der Bibliothek
  `com.otaliastudios.transcoder`, H.264 und AAC, ohne Ort).
- **`flet_hochladen` gibt es nur für Android** — der Ordner der Erweiterung hat `android/`,
  kein `ios/`; die Dart-Seite spricht `image_picker_android` an.

## 2. Stufe 0 — „Medien“ überall (gebaut 17.11.2026)

Das Wort am Bildschirm heißt überall **„Medien“** (Text zählt als Medium): der fünfte Reiter
in „Übung bearbeiten“ und „Im Plan einstellen“, der Knopf („Medien“, „Medien · neu“) und das
Blatt beim Üben, der Eintrag in der Zeile „Verwalten“, der Hinweis unter der Rolle, die Hilfe
„Anweisungen im Plan“.

**Im Code bleibt „Material“** (`core/material.py`, `Material`, `material_von`,
`components/material.py`, Kennungen wie `data="material"`): Es ist dort der Begriff für „alles,
was es zu einer Übung zu sehen gibt“; umbenannt wäre es nur Unruhe. **Ältere Dokumente sagen
weiter „Material“** — gemeint ist dasselbe.

## 3. Stufe 1 — der Reiter „Medien“: eine Übersicht nach Herkunft

**Ein vierter Reiter:** Plan · Uhren · **Medien** · Ablauf (Ben: „a) ja“). „Medien“ gibt es in
jedem Plan; „Ablauf“ kommt mit „Workout“ wie bisher als letzter dazu, sein Platz bleibt sonst
frei.

**Nur ansehen und hinführen — kein dritter Ort zum Einstellen.** Es bleibt bei den zwei Orten
(„Übung bearbeiten“ gilt überall, „Im Plan einstellen“ gilt nur dort). Tippen öffnet ein Stück
(Link, Datei, Text im Blatt), der Stift führt dorthin, wo man es ändert — mit dem Reiter, in dem
es steht, vorn. Auch der Haken „gesehen“ ändert sich hier nicht.

**Gruppen nach Herkunft** (Ben, f: „unterteilt nach Herkunft“), je Stück in Farbe, **wo es
angeboten wird**:

| Gruppe | Was | Wo angeboten (Beispiele) | Stift führt nach |
|---|---|---|---|
| **Aus den Übungen** | Beschreibung, Links und Dateien, Bild der Bewegung (eigen: „nur auf diesem Gerät“, mitgeliefert: „in der App“) | „im „i“ bei 1 · Kniebeuge“, „bei 1 und 4 · Kniebeuge“, „im Fokus bei 1 · Kniebeuge“ | „Übung bearbeiten“, Reiter Medien (Beschreibung: Übung; Animation: Uhr) |
| **Aus diesem Plan** | Beschreibung des Plans; Anweisungen und Stücke der Planübungen, mit „ersetzt „…““ | „bei 2 · Katze-Kuh“ | „Im Plan einstellen“, Reiter Medien |
| **Im Workout** | Inhalt an einem Weg (Text, Link), den das Workout setzte | „am Weg von 1 · Kniebeuge zu 3 · Planke“ | Reiter „Ablauf“ |
| **Aus dem Kurs „…“** | Text- und Medienblöcke der **erreichten** Kapitel (Ben, e); Wege, deren Inhalt ein Weg-Baustein mitbrachte | „im Kapitel 2 · Hüfte“, „am Weg von … zu … · aus Kapitel 2“ | das Kapitel |

- **Ein Weg gehört dorthin, woher sein Inhalt kommt:** Steht am Weg genau der Inhalt, den ein
  Weg-Baustein eines erreichten Kapitels zwischen diesen Planübungen setzt, gehört er zum Kurs;
  sonst — selbst gezeichnet oder im Workout geändert — zum Workout.
- **Ein Stück der Übung, das eine Planübung ersetzt,** steht blass („bei 1 · Kniebeuge
  ersetzt — siehe „Aus diesem Plan““); ersetzt es nur eine von zwei, steht das dahinter.
- **Kopfzeile:** „6 Stücke · 2 Dateien · 96 MB“ — die Paketdateien, die mit dem Plan reisen
  würden; darunter „Dateien reisen mit, wenn du den Plan als Paket weitergibst; Links nicht.“
- **Groß** (Ben, c: „Ist noch zu groß. Das Bild muss auf ein Tablet/Smartphone passen.“):
  **Meine Lesart:** Die Stufe „Mittel“ (720p, 0,8 Mbit/s Bild + 64 kbit/s Ton, rund 6,5 MB je
  Minute) passt auf Handy und Tablet. Groß ist, was **mehr als ein Viertel darüber** liegt — ein
  Video über rund **8,1 MB je Minute** (zwei Minuten: über 16 MB statt der vorgeschlagenen
  26 MB), ein Bild mit mehr als **900 Pixeln an der kürzeren Seite**. Ohne Dauer bzw. Maße
  heißt nichts groß — geraten wird nicht. Eine Stelle zum Nachstellen:
  `core.medien_uebersicht.SPIELRAUM`.
- **Woher Dauer und Maße kommen:** `core/videoinfo.py` liest die Köpfe von MP4, M4V, MOV und
  M4A (Dauer, Bildgröße, Bildrate, Tonspur) in reinem Python — kein ffprobe, gleich auf
  Android, iPhone, Rechner und im Browser. Gegengeprüft am 17.11.2026 mit ffprobe an vier
  Dateien (1080p mit Ton, Kopf am Ende · 720 × 1280 hochkant · 640 × 480 mit 23,976 fps als MOV
  · nur Ton). Bildmaße: `core.bewegungsbild.png_masse` (JPEG, PNG).
- **Geladene Videos hinter Links** (Stufe 7 des Rückwegs, Migration 068) zeigen ihre Größe mit
  „auf dem Gerät“; sie zählen nicht zu den Dateien des Pakets.

- **Der Weg in Worten** („am Weg von … zu …“, „… zum Ende“): Der Pfeil fehlt manchen Schriften
  — im kopflosen Browser stand ein Kästchen, die Web-Fassung lädt ohne CDN keine Ersatzschrift.
- **Ein Weg mit Text und Link** öffnet ein Blatt mit dem Text und „Öffnen“ für den Link; ein
  Stück nur mit Link öffnet ihn direkt; Text (auch die Abschnitte einer Anweisung) im Blatt.

**Gebaut 17.11.2026.** Web-Fotos (412 × 860): die vier Reiter passen, auch bei einer Liste; die
Gruppen mit grünem „wo“, „84 MB · groß“ am Video (1080p · 30 fps · 2:10), Kopfzeile „9 Stücke ·
2 Dateien · 85 MB“, das Blatt eines Wegs mit „Öffnen“. Gerätetest **T148**.

**Bau:** `core/medien_uebersicht.py` (Rechnung, flet-frei, Doctests), `core/videoinfo.py`,
`views/plan_medien.py` (holt Kurs und Kapitel, misst Dateien aus, zeichnet),
`components/plan_reiter.py` (vier Plätze), Route `<Plan bearbeiten>/medien` (`ui/app.py`),
Hilfe `PLAN_MEDIEN_MD`, `medienliste.oeffner` (der Handler der Medienzeile ohne die Zeile).
**Keine Migration, kein neues Paketfeld, kein Verhalten ändert sich.** Keine Abzweigung für den
Browser.

## 4. Stufe 2 — Medien am Plan selbst

Der Plan bekommt eigene Stücke (Links, Dateien) und seine Beschreibung wird sichtbar: „So läuft
das Workout“, ein Übersichtsblatt als PDF, ein Video zur Einstimmung.

- **Daten:** `plan.media_json` (Migration 069), `Plan.media`; schmale Setzer
  `PlanRepo.medien_setzen` und `beschreibung_setzen` (der Rest des Plans bleibt). Im Paket das
  Feld `plaene[].medien` wie die Medien eines Kapitels (`medien_to_list`/`medien_from_list`) —
  **keine neue Formatversion**: Ältere Apps übergehen es, wie bei den Medien der Planübung
  (`docs/uebungspakete.md`). Im Drei-Wege-Abgleich ein Feld (`PLANFELDER`). Mit dem Paket reisen
  die Dateien (`paketmedien_in`, `medienlisten`, Umbenennen beim Export); ein Kursplan übernimmt
  sie aus seinem Grundplan.
- **Eintragen:** im Reiter „Medien“, Gruppe „Aus diesem Plan“ — sie steht immer da: „Beschreibung
  …“ und „Medium zum Plan“ (**Link …**, **Datei wählen …**), je Stück im Blatt Titel, Adresse,
  „Vor dem Start beim ersten Mal zeigen“ und „Herausnehmen“; gespeichert beim Schließen. Eine
  Begleitung gibt es am Plan nicht (es läuft keine Übung daneben) — aus dem Paket wird sie zur
  Erklärung. **Noch nicht:** Foto, Video und Fotoauswahl direkt an den Plan (das Ziel der Kamera
  kennt nur Übung und Planübung, `core.anhaenge.Ziel`) — über „Datei wählen …“ geht es.
- **Zeigen** (Ben, b: „ja“): ein dezenter Knopf (Buch-Symbol) **am Kopf des Plans** und **im
  Start-Bild des Workouts** — nur, wenn der Plan eine Beschreibung oder Stücke hat; gefüllt und
  in der Akzentfarbe, solange etwas neu ist (`components/material.plan_knopf`). **„Beim ersten Mal
  von selbst“ geht das Blatt beim ersten Start auf** — beim ersten ▶ einer Übung des Plans bzw.
  bei „Workout starten“; der nächste Tipp startet (`plan_neu_zeigen`, wie bei der Übung).
  **Abweichung vom ersten Entwurf** („beim Öffnen des Plans“): Ein Blatt, das beim Aufbau einer
  Ansicht aufgeht, bleibt in Flet als Geist stehen (`components/dialoge.py`) — der erste Start
  ist derselbe Moment „vor dem Start“, nur sicher. **Nie im Lauf**, einmal je Sitzung, bis es
  abgehakt ist.
- **Fällt der Plan weg** (Ben, d: „ok“): Seine Dateien gehen nicht verloren. Ein endgültig
  gelöschter Plan bleibt als Grabstein stehen (`PlanRepo.endgueltig_loeschen`), seine
  `media_json` mit ihm — die Ablage räumt Dateien, die er nennt, nicht weg. Sie sind damit
  **privat**: an keinem Plan mehr zu sehen, aber auf dem Gerät. Zeigen und wieder übergeben
  kann sie erst die private Ablage (`plan_medienrollen.md` Stufe M3).
- **Paket:** Drei-Wege-Abgleich wie bei den Medien einer Planübung; jede Datei ohne
  Ortsangaben (`core/bereinigen.py`).

**Gebaut 18.11.2026.** Tests: `tests/test_plan_medien_daten.py` (speichern, Setzer, Ablage auch
nach dem endgültigen Löschen, ZIP hin und zurück, Abgleich), `tests/test_ui_plan_medien.py`
(Link dazu, falsche Adresse, Herausnehmen, Beschreibung; Blatt vor dem ersten Start, Knopf),
`tests/test_ui_uhr.py` (erstes ▶ im Plan), `tests/test_ui_workout.py` („Workout starten“, Knopf
nur vor dem Lauf). Gerätetest **T149**.

## 5. Stufe 3 — Verkleinern: grobes Schema, Größe vorher, Original bleibt

**Kein Medieneditor.** Schneiden und Bearbeiten bleiben außerhalb (Ben). Es gibt eine Aktion:
ein Video (und ein Bild) kleiner machen — nach einem groben Schema, mit der Größe vorher.

**Das Schema** (Ben: „Framerate, dpi, Auflösung usw. nach grobem Schema … mit Angabe, wie groß
das Video sein wird“):

- **Drei Vorlagen mit einem Tipp** — dieselben Namen wie bei der Kamera der App: **Klein**
  (480p, 24 Bilder/s), **Mittel** (720p, 30 Bilder/s — passt auf Handy und Tablet, die
  Vorgabe), **Groß** (1080p, 30 Bilder/s). Jede zeigt die geschätzte Größe **für dieses
  Video**: „Mittel · etwa 14 MB“.
- **„Genauer …“** klappt vier Einstellungen auf, die Schätzung läuft mit:
  - **Auflösung:** 360p · 480p · 720p · 1080p — nur, was nicht größer ist als das Original;
  - **Bildrate:** 15 · 24 · 30 Bilder je Sekunde — nie mehr als das Original;
  - **Bildqualität:** sparsam · normal · scharf (Bitrate × 0,7 · 1 · 1,5);
  - **Ton:** ohne · Sprache (einkanalig, 48 kbit/s) · normal (64 kbit/s) · gut (96 kbit/s).
- **dpi gibt es bei Videos nicht** — ein Bildschirm zeigt Pixel; was „dpi“ meint, ist hier die
  Auflösung. dpi zählt nur beim Drucken (PDF).
- **Wie geschätzt wird:** Die Bitrate liegt fest (Basis je Auflösung aus `Qualitaet`: 360p
  250 · 480p 400 · 720p 800 · 1080p 2000 kbit/s, mal Bildqualität, mal Bildrate: 30 → 1,
  24 → 0,85, 15 → 0,6), dazu der Ton; Größe ≈ Bitrate × Dauer + 2 % für den Container. Der
  Umwandler hält die Bitrate, die Schätzung trifft darum auf wenige Prozent. Liegt das Original
  schon darunter, steht „wäre nicht kleiner“ da und die Bitrate des Originals gilt.

**Ablauf** (Ben: „Das konvertierte Video wird erstmal kopiert, das ursprüngliche bleibt, damit
man das neue anschauen kann und neu erstellen, falls es doch zu unscharf ist“):

1. **Wo man es trifft:** Menü an jeder Video- oder Bilddatei in „Übung bearbeiten → Medien“
   und „Im Plan einstellen → Medien“ („Verkleinern …“); die Übersicht führt bei „groß“
   dorthin; nach „Datei wählen …“ fragt ein Blatt, wenn die Datei groß ist.
2. **Erstellen:** Das Original bleibt unberührt; die Kopie entsteht daneben, mit Fortschritt
   und „Abbrechen“.
3. **Vergleichen:** „Neu: 720p · 30 fps · 13 MB (vorher 84 MB)“ — „Neu ansehen“, „Original
   ansehen“, „Anders erstellen …“ (zurück zum Schema; die Kopie wird ersetzt).
4. **Übernehmen:** Das Stück zeigt auf die neue Datei; „ersetzt“, das auf die alte zeigte, und
   der Haken „gesehen“ ziehen mit. **Das Original bleibt auf dem Gerät** — es reist nie mit, und
   am Stück stehen „Original wieder nehmen“ und „Original löschen“. **Verwerfen:** Die Kopie
   geht weg, alles bleibt, wie es war.
5. **Paketübungen:** Eine verkleinerte Datei an einer Übung aus einem fremden Paket gilt als
   Änderung der Person (Drei-Wege-Abgleich: sie bleibt beim nächsten Update). Das Blatt sagt
   es dazu.

**Ein Vertrag, vier Wege dorthin** (Ben: „berücksichtige, dass es Android und Apple geben
wird“) — die Oberfläche fragt nur „kann dieses Gerät das?“ und gibt das Schema weiter:

| Plattform | Womit | Stand |
|---|---|---|
| **Android** | der Umwandler der Fotoauswahl (`flet_hochladen`: `verkleinern(quelle=…)` nimmt jede Datei; kurze Seite, Bild- und Tonbitrate gibt es schon). Neu: Bildrate und einkanaliger Ton als Argumente (Dart reicht durch, Kotlin `.frameRate(…)`, `.channels(…)`) — ohne sie wie bisher | Gerätetest |
| **iPhone/iPad** | ein **eigener iOS-Teil** von `flet_hochladen` (Swift, AVFoundation) mit demselben Vertrag. Hier nicht baubar (kein Mac, kein Xcode) und vor dem Bau nachzulesen; bis dahin fehlt „Verkleinern“ auf Apple-Geräten — die Übersicht zeigt „groß“ trotzdem | offen |
| **Rechner** (App am Bildschirm und Paketwerkzeug) | **ffmpeg**, wenn es installiert ist (`libx264`, AAC, `-map_metadata -1`); nie mitgeliefert, keine neue Abhängigkeit | gebaut mit Stufe 3 |
| **Web-Fassung** | nichts — im Browser fehlt „Verkleinern“ (kein Umwandler) | — |

- **Gleiches Ergebnis überall:** MP4 mit H.264 und AAC, ohne Ortsangaben; danach bereinigt und
  nach Prüfsumme abgelegt wie jede Paketdatei (`core/bereinigen.py`, `data/paketmedien.py`).
- **Wo das Original vermerkt ist:** gerätelokal (Einstellung, JSON neu → Original); die Ablage
  räumt ein so vermerktes Original nicht weg. Nicht in Export, Backup oder Sync.
- **Nichts geschieht von selbst:** Verkleinert wird nur auf Tipp. **Keine neue
  Netzverbindung.**

**Reihenfolge:** 3a Schema, Schätzung und Ablauf mit ffmpeg am Rechner (testbar) · 3b Android
(Gerätetest) · 3c iPhone, sobald es einen iOS-Build gibt.

**Gebaut 18.11.2026 (3a und 3b):**

| Teil | Wo | Stand |
|---|---|---|
| Schema, Ziel, Schätzung, „wäre nicht kleiner“, Wahl nie über dem Original | `core/verkleinern.py` (Doctests) | getestet |
| ffmpeg-Aufruf und -Lauf (Fortschritt aus `-progress`, Abbruch ohne halbe Datei) | `core/verkleinern.mit_ffmpeg` | getestet mit echtem ffmpeg 8.1.3 (Auflösung, Bildrate, ohne Ton, Ort weg); in der CI übersprungen |
| Womit: Android vor ffmpeg, sonst keiner | `ui/verkleinern.py` (`weg`, `ausfuehren`, `abbrechen`) | — |
| Ansicht: Vorlagen mit Größe, „Genauer …“, Erstellen, Jetzt · Neu im Spieler, Anders erstellen, Verwerfen, Übernehmen, „Original wieder nehmen“, „Original löschen“ (fragt) | `views/verkleinern.py`, Route `…/verkleinern/<datei>` über jeder Ansicht | getestet; Web-Fotos |
| Einstieg: Tipp auf die Größe eines Videos im Reiter „Medien“ (bei „groß“ betont) | `views/plan_medien.py` | getestet |
| Übernehmen: jedes Stück auf die neue Datei — Übung, Planübung, Plan, Kurskapitel, auch „ersetzt“; „gesehen“ geht mit; das Original gerätelokal vermerkt (`app_setting` `medien_originale`), die Ablage räumt es nicht weg | `data/paketmedien.Paketablage.ersetzen`, `original`, `original_vergessen`, `verwerfen` | getestet |
| Android: Bildrate und Kanäle (0 = ohne Ton) als neue, wahlfreie Argumente | `erweiterungen/flet_hochladen` (Python, Dart, Kotlin) | Kotlin kompiliert gegen Transcoder 0.10.5 (`RemoveTrackStrategy` ist dort), `flutter analyze` ohne Befund; **am Gerät ungeprüft** (T150) |

Web-Fotos am 18.11.2026 (412 px): ein 1080p-Video von 31 MB — „Mittel · etwa 2 MB“, nach
„Erstellen“ „720p · 30 fps · 0:20 · 2 MB (vorher 31 MB)“; „Übernehmen“ → die Übersicht zeigt die
neue Fassung ohne „groß“; die Ansicht der neuen Datei nennt das Original (31 MB) mit „Original
wieder nehmen“ und „Original löschen“, Mittel und Groß „wäre nicht kleiner“. Der Spieler bleibt im
kopflosen Browser schwarz (kein Video-Dekoder) — abspielen ist Gerätetest.

**Nachgezogen am 18.11.2026 (Ben: „mach weiter“): der Werkzeugschritt**
`trainingsapp-paket verkleinern <export>.zip [--vorlage …] [--alle] [--probe]`
(`paket_verkleinern.py`, eingehängt in `paket_werkzeug.main` neben `einlesen`): liest die ZIP aus
dem Export der App, verkleinert jedes große Video mit ffmpeg und schreibt eine **neue** ZIP nach
`verkleinert/` — derselbe Weg wie der Export der App (`export_schreiben`: bereinigt, nach
Prüfsumme benannt, alle Verweise gezogen); das Original bleibt, die Version auch (vor dem
Veröffentlichen anheben). Ein TOML nennt seine Dateien erst beim Bauen: erst `bauen`, dann die
ZIP verkleinern. Tests: `tests/test_paket_verkleinern.py` (mit echtem ffmpeg, in der CI
übersprungen).

**Noch nicht gebaut:**

- **iPhone (3c):** ein Swift-Teil von `flet_hochladen` mit demselben Vertrag; hier weder baubar
  noch prüfbar. Bis dahin steht auf Apple-Geräten statt „Erstellen“ ein Satz dazu.
- **Nach „Datei wählen …“ fragen:** Die Formulare halten ihre Medien bis zum Speichern selbst;
  ein Ersetzen darunter ginge verloren. Verkleinert wird darum aus der Übersicht.
- **Bilder** verkleinern (die Fotoauswahl tut es schon) — auf Wunsch.
- **Übungen ohne Plan** erreicht die Übersicht nicht; ein Einstieg auf der Übungsseite wäre der
  nächste kleine Schritt.

Gerätetest **T150**.

## 6. Fragen an Ben (Katalog P225) — a bis f beantwortet am 17.11.2026

Die Antworten stehen in der Tabelle am Kopf. **Selbst entschieden** (Ben: „Finde gute Lösungen
und arbeite das selbständig aus“), zum Nachprüfen:

- die Lesart von c) (Groß = über „Mittel“ + ein Viertel, §3);
- „Original bleibt auf dem Gerät“ nach „Übernehmen“, mit „Original wieder nehmen/löschen“ (§5);
- keine Begleitung am Plan (§4);
- die Bitraten des Schemas (§5).

## 7. Regeln, die gelten

- Zwei Orte zum Einstellen bleiben; die Übersicht ändert nichts (Ausnahme Stufe 2: „Zum Plan“).
- Was im Paket reist, ist ohne Ortsangaben; Eigenes bleibt privat, bis die Person es übergibt
  (`plan_medienrollen.md` §2.3 und §5).
- Kein Video startet von selbst.
- „gesehen“ bleibt auf dem Gerät.
- Pläne und Kurse ändern ihr Verhalten nicht ohne Bens Ja; Stufe 1 ändert keines.

## 8. Tests und Gerät

- Stufe 0: `tests/test_ui_editor_reiter.py`, `tests/test_ui_material_rollen.py`,
  `tests/test_ui_workout.py` (Wortlaut „Medien“).
- Stufe 1: Doctests in `core/videoinfo.py` und `core/medien_uebersicht.py`,
  `tests/test_videoinfo.py` (künstliche Köpfe aus `tests/mp4_bau.py`; die CI hat kein ffmpeg),
  `tests/test_medien_uebersicht.py`, `tests/test_ui_plan_medien.py`; die Reiterzeile in
  `tests/test_ui_plan_uhren.py` und `tests/test_ui_ablauf_editor.py`; Web-Fotos.
- Stufe 3: Schema und Schätzung als Doctests; ffmpeg-Lauf als Test, der ohne ffmpeg
  übersprungen wird; „Datei ersetzen“ und „Original wieder nehmen“ als Test; der Umwandler am
  Handy ist **Gerätetest** (Android; iPhone, sobald es den Build gibt).
