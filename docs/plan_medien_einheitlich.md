# Planung: Medien einheitlich — hinzufügen, Stellen im Ablauf, Fälliges im Fokus, überall verkleinern (19.11.2026)

Ben, 19.11.2026 („Zur Bereitstellung der Medien in der App“):

1. „Medien gibt es für Übungen, Pläne, Kurse und für die Tagesdokumentation. Schau nach, wo es
   noch Medien gibt. Die Medienverwaltung und Gestaltung sollte einheitlich verlaufen.
   Videos/Fotos sollen überall komprimiert und gecroppt werden können.“
2. „Wenn Medien hinzugefügt werden, sollen alle Typen gleichermaßen angeboten werden: Links,
   Fotos, Videos, ‚aus der Fotoauswahl‘, Datei wählen. Bei Plan → Übung einstellen → ‚Inhalt bei
   diesem Weg‘ wird ein Link angeboten, aber es kann kein Video hinterlegt werden, und
   hinterlegte Videos aus dem Reiter ‚Medien‘ können nicht eingebunden werden.“
3. „Die Verwaltung der Medien in den Abläufen müsste vereinfacht werden: ermittle, wann wo
   Videos bereitgestellt werden können … Dann muss jede Position einfach zugänglich gemacht
   werden. Am besten ist im Ablauf angezeigt, wo Medien liegen, z. B. im Icon der Übung oben
   rechts (Medium am Anfang), unten rechts (Medium am Ende) oder am Übungsausgang am Knoten.“
4. „Medien, die erstellt werden, sollen gleich benannt und beschriftet werden können.“
5. „In Plan → Medien werden auch die Abschnitte wie ‚Beschreibung‘ gelistet. Übungsbeschreibungen
   sind unnötig. Textbausteine für die Wege oder individuelle Übungsanweisungen sind etwas
   anderes, die werden gebraucht.“
6. Fokus: „Wenn Videos bereitstehen, kommt ein Blatt von unten. Das ist unpraktisch, wenn man das
   Video … erst einmal aus der Liste herausklicken soll. Wenn ein Video abgespielt werden sollte,
   wird es einfach eingeblendet. Die, die nicht dran sind, sollen nicht gezeigt werden, da es dazu
   verleitet, sich vorzeitig etwas anzuschauen, dem man sowieso begegnet.“

**Stand 19.11.2026:** Ben: „Empfehlungen a–h gelten, bau E1 und E2. Wenn alles geklappt hat,
mach den ganzen Rest danach gleich mit, außer es gibt Skizzen mit Alternativen und einer
erforderlichen Auswahl.“ **Gebaut: E1–E6** (20.11.2026; ohne den Ausschnitt am Telefon, Frage i) — was gebaut
ist und wo es abweicht, steht in **§5**.
Fragen im Katalog als **P227** (a–h entschieden wie empfohlen).

Gesucht im Katalog (Entscheidungszeilen): medien, medium, verkleiner, zuschneid, crop, begleit.
Gelesen: **P226** (Zeitpunkte, gebaut 19.11.), **P225** (Reiter „Medien“), dazu ganz
`docs/plan_medien_zeitpunkte.md` (Vertrag der Stellen, die sich ändern). Nur gefunden: P94, P160,
P200, P203, P209. Am Code gelesen: `core/material.py`, `core/models.py` (`Media`),
`core/bedingung.py` (`Inhalt`), `ui/components/material.py` (`material_blatt`),
`ui/components/wege_form.py` (:895–1010), `core/medien_uebersicht.py` (:360–475),
`ui/components/ablaufbild.py` (:640–700). Die zwei Inventare in §1 stammen aus Suchläufen über
`ui/` und `core/verkleinern.py`; ihre Fundstellen sind **nicht einzeln nachgeprüft** — vor jeder
Stufe wird die betroffene Stelle neu gelesen.

## 1. Befund

### 1.1 Wo es Medien gibt — vier Datenmodelle

| Modell | Wo | Felder zum Benennen |
|---|---|---|
| `core.models.Media` | Übung (`exercise_media`), Planübung (`plan_item.media_json`), Plan (`plan.media_json`), Kurs-Block (`course_chapter.blocks_json`) | `title` — **keine Beschriftung** |
| `core.anhaenge.Anhang` | Einträge und Notizen zum Tag (`entry_media`, `Anhaenge/`) | `note` — **kein Titel** |
| `Inhalt`/`Stueck` | Weg im Ablauf (`Kante.inhalt`) | `title`, ohne Art und Quelle — **nur Links** |
| Pfad an der Übung | Symbol (`exercise.image_path`), Bild der Bewegung (`Media`, lokal) | nichts |

Sonst nirgends: Timer-Klänge, HRV-Aufzeichnungen, Workout-Eintrag, Fragen im Ablauf und
Kurs-Bausteine haben keine Stelle zum Hinzufügen.

### 1.2 Hinzufügen — jede Stelle baut ihr eigenes Menü

| Stelle | Link | Kamera Foto/Video | Fotoauswahl | Datei wählen | Ton · Dokument | aus Vorhandenem | Name beim Anlegen |
|---|---|---|---|---|---|---|---|
| Übung bearbeiten → Medien | ja | ja¹ | ja¹ | ja | nur als Datei | nein | Link, Datei: Titel; Kamera: „Foto vom TT.MM.“, die Notiz der Kamera-Seite wird **verworfen** |
| Im Plan einstellen → Medien | ja | ja¹ | ja¹ | ja | nur als Datei | nein | wie Übung |
| Plan → Reiter „Medien“ | ja | **nein** | **nein** | ja | nur als Datei | nein | Link sofort; Datei erst über den Stift |
| **Weg** („Inhalt bei diesem Weg“) | ja | **nein** | **nein** | **nein** | nein | **nein** | erster Link ohne Titel |
| Kurs → Block „Medium“ | ja | **nein** | **nein** | **nein** | nein | nein | Titel |
| Notiz zum Tag, Eintrag | **nein** | ja | ja¹ | nur am Rechner | aufnehmen | nein | nur „Notiz (optional)“ |
| Symbol, Bild der Bewegung | nein | Foto | ja | ja | — | **ja** (Ablage) | nichts |

¹ nur wo das Gerät es kann (Kamera: Android, iOS, Web; Fotoauswahl: mit `flet_hochladen`).

Gemeinsam sind nur Bausteine (`ui/paketdatei.py`, die Kamera- und die Fotoauswahl-Seite mit
`core.anhaenge.Ziel`, `material_rolle.rollen_zeile`). Die Linkzeile ist fünfmal gebaut, das
Datei-Menü zweimal (fast wörtlich), das Anhang-Menü dreimal.

**Warum am Weg kein Video geht** (Bens Punkt 2): `Stueck` kennt nur Adresse und Titel; das
Formular hat nur Textfelder (`wege_form.py:915–1008`); das Workout öffnet Weg-Stücke nur als
`https`/`mailto` (`views/workout.py`, `components/links.py`); und weder das Aufräumen der
Paketablage (`data/paketmedien._ABFRAGEN`) noch der Export (`core.pakete.paketmedien_in`) noch
„Videos laden“ sehen in `ablauf_json` nach — eine Datei am Weg würde weggeräumt und reiste nicht
mit.

### 1.3 Verkleinern, Kürzen, Zuschneiden

- **Verkleinern und Kürzen:** nur **Paket-Videos** (MP4, M4V, MOV), nur von zwei Stellen aus —
  Plan → Reiter „Medien“ (Tipp auf die Größe) und Übungsseite. Nicht aus den Editoren, nicht im
  Kurs, nicht in der Ansicht der Paketdatei.
- **Fotos:** werden nur beim Hochladen aus der Fotoauswahl verkleinert; ein bestehendes Foto
  nirgends. Die Kamera nimmt in der gewählten Stufe auf. Ton: nie.
- **Anhänge** (Notiz, Eintrag): gar nicht. Es fehlen Route, das Ersetzen der Datei an der Zeile
  (`AnhangRepo` kann nur `note_setzen`), das neue Frontbild, ein Vermerk fürs Original
  (`medien_originale` nimmt nur Paketnamen) und eine Ausnahme beim Aufräumen.
- **Bildausschnitt:** nur beim Dokument-Scan, als `/CropBox` (nichts wird kleiner). Für Fotos und
  Videos nirgends; das Übungssymbol wird immer mittig beschnitten.
- **Wege:** Android über `flet_hochladen` (Umwandler), Rechner über ffmpeg (nur `scale`, `fps`,
  `-ss`/`-t`), **iPhone und Web: kein Weg**.

### 1.4 Wann ein Medium gezeigt werden kann — die Stellen von heute

| Stelle | Am Plan | An Übung / Planübung | Am Weg |
|---|---|---|---|
| **vorher** | vor dem Start | vor dem ▶ | — |
| **dabei** | — | Begleitung, läuft im Fokus mit | — |
| **bei …** | bei der Antwort einer Frage | Timer-Abschnitt beginnt · Satz n · ab t Sekunden · ab n Wdh. | wenn der Weg gegangen wird |
| **nachher** | am Ende | nach „Fertig“ | — |

Die Stellen gibt es also (P226). Was fehlt, ist der Zugang: Eingetragen wird in drei Editoren und
einem Formular, und **im Ablaufbild sieht man nichts davon** — die Kachel zeigt Nummer und
„fertig“, sonst nichts (`ablaufbild.py:695`).

### 1.5 Fokus

Wird etwas fällig, öffnet `material_blatt` — das Fällige steht oben, **darunter alles andere**:
Abschnitte, Begleitung, „Nach der Übung“, „Zu einem Ereignis“, Ersetztes
(`components/material.py:300–330`). Ein Video ist eine Zeile, die man antippen muss; eine
Paketdatei öffnet dann eine eigene Ansicht.

## 2. Vorschlag

### 2.1 Ein Blatt „Medium hinzufügen“ — überall dasselbe (Punkte 1, 2, 4)

Eine Komponente (`ui/components/medium_dazu.py`) ersetzt alle Menüs aus §1.2. Sie bietet immer
dieselbe Reihe und blendet nur aus, was das Gerät nicht kann:

**Link · Foto aufnehmen · Video aufnehmen · Aus der Fotoauswahl · Datei wählen · Ton aufnehmen ·
Aus vorhandenen Medien …**

- **Aus vorhandenen Medien** listet, was Plan, Planübungen und Übungen schon tragen
  (`core.medien_uebersicht.uebersicht` liefert es), dazu die Dateien der Ablage. Gewählt wird ein
  **Verweis auf dieselbe Datei** (gleicher `medien/<sha>`-Name), keine Kopie — so kommt ein Video
  aus dem Reiter „Medien“ an den Weg.
- **Benennen und beschriften gleich danach:** Nach Aufnahme, Auswahl oder Link folgt ein Schritt
  mit **Titel**, **Beschriftung** und — wo es Zeitpunkte gibt — **Wann**. Die Notiz der
  Kamera-Seite wird nicht mehr verworfen, sie wird die Beschriftung.
- **Daten:** `Media` bekommt ein Feld `text` (Beschriftung), geschrieben wie die anderen Zusätze
  (nur wenn gesetzt; ältere Apps übergehen es — nachgesehen: `core.models.zeit_zusatz_lesen`
  liest nur die Felder, die es kennt). Der Anhang hat `note` als Beschriftung; ob er zusätzlich einen Titel braucht,
  ist Frage c.
- Kurs-Block „Medium“ nimmt dieselbe Komponente und behält dabei das ganze `Media` (heute gehen
  Rolle, Art und Quelle beim Bearbeiten verloren).

### 2.2 Der Weg trägt echte Stücke (Punkt 2)

`Inhalt.medien` hält künftig ganze Stücke (Art, Quelle, Titel, Beschriftung) statt nur Adressen.
Dazu gehört zwingend: Aufräumen, Export und „Videos laden“ lesen `ablauf_json` mit; das Workout
zeigt Weg-Stücke mit `medienliste.medium_zeile` statt nur als Link. Der Text am Weg
(„Inhalt bei diesem Weg“) bleibt, wie er ist.

**Offen, vor dem Bau zu prüfen:** Eine ältere App läse `medien/<sha>.mp4` am Weg als Link und
wiese ihn ab. Ob das eine neue Paket-Formatversion braucht (`core.pakete.noetige_version`), ist
**nicht nachgesehen**.

### 2.3 Marken im Ablauf — sehen, wo etwas liegt (Punkt 3)

Jede Stelle aus §1.4 bekommt einen festen Platz im Bild; die Lage sagt das Wann:

| Marke | Platz | Bedeutung |
|---|---|---|
| ● oben rechts an der Kachel | Ecke | **vorher** — vor der Übung |
| ▶ rechts in der Mitte | Rand | **dabei** — Begleitung |
| ◆ rechts in der Mitte, darunter | Rand | **bei …** — zu einem Ereignis in der Übung |
| ● unten rechts an der Kachel | Ecke | **nachher** — nach der Übung |
| ● am Griff eines Wegs | auf der Linie | Inhalt **an diesem Weg** |
| ● an „Start“ / an „Ende“ | Knoten | **vor dem Start** / **am Ende** des Plans |
| ◆ an einer Frage | Knoten | Stück des Plans **bei dieser Antwort** |

- Eine leere Stelle zeigt nichts. **Tipp auf eine Marke** öffnet das Blatt „Medien an dieser
  Stelle“: die Stücke dort, je Stück Stift und Herausnehmen, unten „+ Medium“ (§2.1) — schon mit
  dem richtigen Wann.
- **Leere Stellen erreichen:** im Menü der Kachel (gedrückt halten) „Medien …“ — ein Blatt mit den
  vier Stellen der Übung untereinander (Vorher · Dabei · Bei … · Nachher), jede mit „+“. Am Weg
  bleibt „Mehr …“ in der Weg-Leiste, an Start und Ende ein Tipp auf den Knoten.
- **Liste** (ohne Ablauf): dieselben Marken in der Zeile der Planübung im Reiter „Plan“, dasselbe
  Blatt.
- Rechnung in `core/medien_uebersicht.py` (eine Funktion „Stellen je Knoten“), `ui/` zeichnet nur.
  Geändert wird weiter am selben Datum wie heute (Planübung, Plan, Weg) — das Blatt ist ein
  zweiter Zugang, kein dritter Ort. Was aus der **Übung** kommt, zeigt das Blatt mit „aus der
  Übung“ und führt zum Ändern dorthin (gilt überall).
- Der Reiter „Medien“ bleibt die Übersicht nach Herkunft.
- **Zu prüfen beim Bau:** oben rechts sitzt heute der Haken „fertig“ (`ablaufbild.py:697`) — im
  Editor gibt es ihn nicht, im Workout-Bild schon; dort hat der Haken Vorrang.

Skizzen dazu als Bildergeschichte, bevor gebaut wird.

### 2.4 Reiter „Medien“ ohne Übungsbeschreibungen (Punkt 5)

Die Zeilen „Beschreibung · ‹Übung›“ fallen weg (`medien_uebersicht._aus_uebungen`). Es bleiben:
Anweisungen der Planübung, Texte an Wegen, Blöcke des Kurses. Ein Abschnitt der
Übungsbeschreibung erscheint nur noch als Vermerk am Stück, das ihm zugeordnet ist („zu:
Ausführung“). Die „Beschreibung des Plans“: Frage e.

### 2.5 Fokus: Fälliges wird eingeblendet, anderes bleibt verborgen (Punkt 6)

- **Was fällig ist, kommt direkt:** kein Blatt mit Liste, sondern das Stück selbst — ein Video
  (Paketdatei oder direkter Videolink) startet im Spieler über dem Fokus, ein Bild steht da, Text
  steht da; darunter nur Titel, Beschriftung, „Gesehen“ und „Weiter“. Sind mehrere fällig, eins
  nach dem anderen („1 von 2“).
- **Was nicht dran ist, wird nicht gezeigt** — kein „Nach der Übung“, kein „Zu einem Ereignis“,
  kein Ersetztes in dieser Ansicht.
- Gilt für alle vier Anlässe: vor dem ▶, „bei …“ („Ansehen“ unter der Uhr öffnet das Stück, nicht
  das Blatt), nach „Fertig“, und am Plan (Start, Antwort, Ende).
- **Die Uhr** steht wie bisher, solange eine Erklärung offen ist; die Begleitung läuft weiter mit.
- **Ein Link auf eine Videoseite** (kein direktes Video) lässt sich nicht einblenden: Er steht als
  eine Karte mit einem Knopf „Öffnen“.
- **Das Buch-Symbol im Fokus:** zeigt nur, was schon dran war (Vorher, bereits Gekommenes) und die
  Begleitung — Frage f. Außerhalb des Übens (Übungsseite, Editoren, Reiter „Medien“) bleibt alles
  sichtbar.
- Wie bisher: nur aus einem Tipp oder dem Takt geöffnet, nie beim Aufbau einer Ansicht
  (Geister-Dialog); gerechnet aus Uhr, Zählung und Wahl, **nie aus Messwerten**.

### 2.6 Verkleinern und Zuschneiden überall (Punkt 1)

Ein Knopf „Bearbeiten …“ an jedem Foto und Video — in beiden Editoren, im Reiter „Medien“, im
Kurs, in der Ansicht der Paketdatei, in der Anhang-Ansicht. Er führt in die eine Ansicht
(`views/verkleinern.py`), die drei Dinge kann: **Größe · Kürzen · Ausschnitt**.

| Teil | Braucht | Geprüft? |
|---|---|---|
| Knopf an allen Stellen für Paket-Videos | nur Oberfläche | ja — die Route legt sich über jede Ansicht |
| **Fotos** verkleinern | Rechner: ffmpeg; Android: `flet_hochladen` kann `art = bild` schon | Android-Weg für eine bestehende Datei **ungeprüft** |
| **Anhänge** | `AnhangRepo.ersetzen` (Datei, Größe, Maße, Frontbild), Vermerk fürs Original, Ausnahme beim Aufräumen | Entwurf, siehe Frage g |
| **Ausschnitt Foto/Video am Rechner** | ffmpeg `crop=` vor `scale` | Filter bekannt, hier **nicht ausprobiert** |
| **Ausschnitt am Handy** | Kotlin in `flet_hochladen`, neue APK | **ungeprüft**, ob Umwandler und Bildverkleinerer zuschneiden können — vor der Stufe klären, sonst nur am Rechner |
| iPhone, Web | — | kein Weg, bleibt so; die Ansicht sagt es |

Wie bisher: immer eine **Kopie**, das Original bleibt gerätelokal vermerkt, übernommen wird erst
auf Tipp. Der Ausschnitt wird am Bild gezogen (wie beim Dokument-Scan: zwei Bereichsregler,
abgedunkelte Ränder), dazu „Quadrat“ für Symbole.

## 3. Stufen (nach Bens Ja)

| Stufe | Inhalt | Größe | Braucht |
|---|---|---|---|
| E1 | Reiter „Medien“ ohne Übungsbeschreibungen (§2.4) | klein | e |
| E2 | Fokus: Fälliges eingeblendet, anderes verborgen (§2.5) | mittel | f |
| E3 | Blatt „Medium hinzufügen“ an Übung, Planübung, Plan, Kurs-Block, Anhängen; Titel und Beschriftung (§2.1) | groß | a, b, c |
| E4 | Weg mit echten Stücken, „Aus vorhandenen Medien“ (§2.2) | mittel | Prüfung Formatversion, d |
| E5 | Marken im Ablauf und in der Liste, Blatt „Medien an dieser Stelle“ (§2.3) | groß | Skizzen, h |
| E6 | „Bearbeiten …“ überall: Knöpfe, Fotos, Anhänge, Ausschnitt (§2.6) | groß, in Teilen | g, Prüfung Handy |

E1 und E2 zuerst — sie hängen an nichts. E3 vor E4 und E5 (beide brauchen das Blatt). Jede große
Stufe im eigenen Worktree; Web-Fotos je Stufe; ein Gerätetest (T153) für Fokus, Kamera-Wege und
Zuschneiden am Handy.

## 4. Fragen an Ben (Katalog P227) — meine Empfehlung zuerst

- **a)** Ein Blatt mit immer derselben Reihe (Link · Foto · Video · Fotoauswahl · Datei · Ton · aus
  Vorhandenem), auch an **Notiz und Eintrag** — dort also neu auch ein **Link**? *Ja zum Blatt;
  Link am Anhang nein* (Anhänge sind Dateien des Geräts, ein Link gehört in den Text der Notiz).
- **b)** Neues Feld **Beschriftung** am Medium (neben dem Titel), gezeigt unter dem Stück beim
  Üben? *Ja.*
- **c)** Bekommt ein **Anhang** auch einen Titel, oder reicht dort die Notiz als Beschriftung?
  *Notiz reicht.*
- **d)** „Aus vorhandenen Medien“: Verweis auf dieselbe Datei (keine Kopie) — und ein geändertes
  Wann oder ein anderer Titel gilt nur an der neuen Stelle? *Ja.*
- **e)** Reiter „Medien“: Auch die **Beschreibung des Plans** heraus, oder nur die der Übungen?
  *Nur die der Übungen.*
- **f)** Fokus: Zeigt das **Buch-Symbol** beim Üben nur, was schon dran war — oder soll es dort
  ganz verschwinden, solange nichts fällig ist? *Nur was schon dran war, plus Begleitung.*
- **g)** Anhänge verkleinern: Das **Original** eines Fotos oder Videos am Eintrag behalten (wie bei
  Paketdateien, bis man es löscht) oder gleich ersetzen? *Behalten, mit „Original löschen“.*
- **h)** Marken im Ablauf: die Lage aus §2.3 (oben rechts = vorher, unten rechts = nachher, Griff =
  Weg) — und Zugang zu leeren Stellen über das Menü der Kachel? *Ja; Skizzen vorab.*
- **i)** *(20.11.2026)* **Ausschnitt am Telefon:** Der Umwandler kann nur mittig auf ein
  Seitenverhältnis zuschneiden. „Format wählen“ für Videos am Telefon bauen — oder Zuschneiden
  nur am Rechner lassen? **Entschieden (Ben, 20.11.2026): „Lass das Zuschneiden nur am Rechner.
  Vermerke aber, dass es am Smartphone fehlt und warum.“**

## 5. Gebaut — und wo es vom Vorschlag abweicht

| Stufe | Gebaut | Fundstelle |
|---|---|---|
| E1 | Der Reiter „Medien“ listet die Beschreibung der Übung nicht mehr; Anweisungen der Planübung, Texte an Wegen, Beschreibung des Plans und Kurs-Blöcke bleiben | `core/medien_uebersicht._aus_uebungen` |
| E2 | Was fällig ist (vor dem ▶, „bei …“, nach „Fertig“; am Plan vor dem Start, zu einer Antwort, am Ende), steht **selbst** im Blatt: ein Video auf dem Gerät läuft im Spieler, ein Bild steht da — sonst nichts. „Gesehen“ hakt ab, „Später“ schließt nur; was jedes Mal kommt, hat „Weiter“. Das Buch-Symbol im Fokus zeigt nur Abschnitte, Begleitung, Vorher und was „bei …“ in diesem Lauf schon kam | `components/material.py` (`faellig_blatt`, `plan_faellig_blatt`, `_faellig_inhalt`), `core.material.beim_ueben`, `Fokus._ereignis_hinweis` |
| E3 | **Ein Menü „Medium hinzufügen“** in „Übung bearbeiten“, „Im Plan einstellen“ und im Reiter „Medien“ des Plans: Link · Foto · Video · Fotoauswahl · Datei · Audio · **aus vorhandenen Medien** (Blatt mit Suche; ein Verweis auf dieselbe Datei). **Beschriftung** am Medium (`Media.text`, in allen drei Editoren unter dem Titel, gezeigt unter der Zeile und unter dem eingeblendeten Stück). Kamera, Fotoauswahl und Rekorder fragen bei einem Medium **Titel und Beschriftung**; neu als Ziel: der Plan und „Ablage“ (für E4), neu als Art: Audio. Der Kurs-Block „Medium“ nimmt Datei und Vorhandenes und behält Art, Quelle und Rolle. Die Anhang-Menüs an Notiz und Eintrag nehmen Namen und Symbole aus derselben Tabelle | `components/medium_dazu.py`, `core/medien_vorrat.py`, `core.anhaenge.Ziel` (`fuer_plan`, `fuer_ablage`), `ui/paketdatei.py` (`medium_mit`, `abholen`), `components/material_rolle.py`, `views/kurs_bearbeiten.block_dialog` |
| E4 | **Der Weg trägt echte Stücke:** im Wege-Formular (Reiter „Ablauf“ und „Im Plan einstellen“) dasselbe Menü — Link · Foto · Video · Fotoauswahl · Datei · Audio · aus vorhandenen Medien (die Stücke des Plans vorn); je Stück Titel und Beschriftung. Im Workout steht eine Datei als Medienzeile (ein Tipp öffnet sie in der App). Ablage (Aufräumen, Verkleinern) und Paket-Export lesen die Dateien an Wegen mit; der Reiter „Medien“ zeigt sie mit Größe | `core.bedingung.Stueck` (`kind`, `source`, `text`), `core.ablauf.wegdateien`, `core.pakete.paketmedien_in`, `data/paketmedien._ABFRAGEN`, `components/wege_form.py` (`WegMedien`, `stuecke_abholen`), `views/workout.inhalt_karte` |
| E5 | **Marken im Ablaufbild:** am rechten Rand der Kachel von oben nach unten vorher (Punkt) · dabei (▶) · bei … (Blitz) · nachher (Punkt); ein Weg mit Inhalt trägt einen Ring um seinen Punkt; an „Start“ eine Marke für die Medien des Plans (leer als „+“). Tipp auf eine Marke oder „Medien …“ im Menü der Kachel öffnet das **Blatt „Medien an dieser Stelle“**: die Stellen untereinander, je Stück Stift (zum Editor) und ✕, je Stelle „Medium hinzufügen“ — das neue Stück bekommt Rolle und Zeitpunkt der Stelle und kommt dort von selbst. In der **Liste** (Plan bearbeiten) dieselben vier Marken in der Zeile der Planübung, gefüllt oder als Umriss | `core/medien_stellen.py`, `components/medien_stellen.py` (`stellen_blatt`, `marken_knopf`, `abholen`), `components/ablaufbild.py` (`marken`, `wege_mit_inhalt`, `on_marke`), `views/ablauf.py`, `views/plan.py` |
| E6, Teil 1 | **Bildausschnitt für Videos** in der Ansicht „Verkleinern“: zwei Regler (Breite, Höhe) und das Bild als Schema, dieselbe Kopie wie beim Verkleinern und Kürzen — **nur am Rechner** (ffmpeg `crop` vor `scale`; mit echtem ffmpeg-Lauf getestet). **Erreichbar von überall:** Knopf in der Ansicht jeder Paket-Videodatei (dort landet, wer ein Video antippt), an der Datei-Zeile in „Übung bearbeiten“ und „Im Plan einstellen“, wie bisher im Reiter „Medien“ und auf der Übungsseite; Dateien an Wegen und in Kurs-Blöcken ziehen beim Übernehmen mit | `core/verkleinern.py` (`Ausschnitt`, `ausschnitt`, `Ziel.ausschnitt`, `ffmpeg_befehl`), `views/verkleinern.py`, `views/paketmedium.py`, `data/paketmedien.ersetzen` |
| E6, Teil 2 | **Fotos** (JPEG, PNG) in derselben Ansicht: die drei Stufen der Kamera (Klein · Mittel · Groß) und am Rechner „Volle Größe“ (nur zuschneiden) mit demselben Ausschnitt; die Kopie behält ihr Format, die Drehung aus dem Kopf wird angewandt, Metadaten fallen weg. **Anhänge** (Foto, Video an Notiz und Eintrag): Knopf in der Ansicht des Anhangs → `…/anhang/<id>/verkleinern`; „Übernehmen“ setzt die Kopie an die Stelle der Datei, das **Original bleibt vermerkt** (Migration 073, `entry_media.original`) mit „Original wieder nehmen“ und „Original löschen“ (Frage g); Aufräumen lässt es liegen, Löschen des Anhangs nimmt es mit. Der Knopf steht jetzt auch an Fotos: Paketdatei, beide Editoren, Reiter „Medien“, Übungsseite | `core/verkleinern.py` (`bildziel`, `bild_befehl`), `views/verkleinern.py` (`Quelle`, `_paket`, `_anhang`), `data/anhaenge.AnhangRepo.ersetzen`, `tests/test_ui_verkleinern.py`, `tests/test_anhaenge.py` |

**Stand E6 — geprüft und offen:**

- **Geprüft mit echtem ffmpeg (8.1.3):** Foto 1600 × 1200 mit Drehung im Kopf → Mittel 720 × 960,
  Ausschnitt und „Volle Größe“ mit den erwarteten Maßen; Video-Anhang 720p → Klein mit eigenem
  Frontbild; Tests `test_foto_zuschneiden_…`, `test_anhang_verkleinern_original_bleibt`.
- **Ausschnitt am Telefon: fehlt, mit Absicht** (Frage i, Ben 20.11.2026: nur am Rechner).
  **Warum:** Der Umwandler der APK (`com.otaliastudios:transcoder:0.10.5`, Klassen in
  `resize/`, nachgesehen im Gradle-Cache) hat nur `AspectRatioResizer` — einen **mittigen**
  Zuschnitt auf ein Seitenverhältnis, kein freies Rechteck; der Bildverkleinerer für Fotos
  (`flutter_image_compress`) schneidet gar nicht zu. Ein freier Ausschnitt bräuchte einen
  anderen Umwandler (eigener Kotlin-Teil, neue APK). Die Ansicht sagt es am Telefon in einem
  Satz an der Stelle des Ausschnitts (`ausschnitt_fehlt`); Verkleinern und Kürzen gehen dort.
- **Fotos am Telefon verkleinern: ungeprüft.** Derselbe Aufruf wie in der Fotoauswahl
  (`art = "bild"`), hier mit einer Datei der App statt einer gewählten; immer JPEG (ein PNG wird
  dort zum JPEG), ohne „Volle Größe“. Gerätetest T154.
- **Am Bildschirm** (Web-Foto, 412 px) geprüft: die Foto-Fassung der Ansicht (Ausschnitt,
  vier Vorlagen, Satz zur Größe) und ihr Ergebnis. Nicht fotografiert: der neue Knopf in der
  Titelleiste des Anhangs; Bilder selbst zeigt das Web-Werkzeug nicht.

**Abweichungen (E6):**

- **Die Größe eines Fotos steht erst nach dem Erstellen da** (JPEG lässt sich nicht vorab
  schätzen); ist die Kopie nicht kleiner, sagt die Ansicht das in Rot — übernehmen kann man
  trotzdem.
- **Kein „Quadrat“-Knopf** für Symbole (§2.6): Symbole haben ihr eigenes Blatt mit Zuschnitt.
- **Im Kurs** steht kein eigener Knopf: Wer die Datei antippt, landet in der Ansicht der
  Paketdatei, dort ist er.
- **Der Speicher unter Einstellungen → Anhänge** zählt die Kopie, nicht das behaltene Original.
- **Audio und Dokumente** lassen sich nicht verkleinern, GIF, WebP und SVG auch nicht.
- **Ein Entwurf zu einem Anhang** liegt bis „Übernehmen“ oder „Verwerfen“ im Ordner der
  Fotoauswahl; bricht die App vorher ab, zeigt ihn „Aufräumen“ als verwaiste Datei.

**Abweichungen (E5):**

- **Vier Marken am rechten Rand** statt nur zweier Ecken: Die Lage von oben nach unten ist die
  Reihenfolge beim Üben; „dabei“ und „bei …“ tragen ein Zeichen, vorher und nachher sind Punkte
  (Bens Vorschlag: oben rechts = Anfang, unten rechts = Ende — so geblieben).
- **Skizzen vorab gab es nicht:** Die Lage war mit Frage h entschieden, Alternativen zur Auswahl
  entstanden keine. Stattdessen am Bildschirm geprüft (Web-Fotos, 412 px): Marken im Bild, Blatt
  einer Übung, Marken in der Liste.
- **Am Weg** öffnet der Tipp auf den Punkt wie bisher die Leiste des Wegs („Mehr …“ = Blatt mit
  dem Menü aus E4) — kein eigenes Stellen-Blatt.
- **„Bei …“ wird im Blatt nicht angelegt:** Das Ereignis wählt man im Editor (ein Knopf führt
  hin) — das Blatt setzt nichts von selbst.
- **Fragen** tragen keine eigene Marke: Was zu einer Antwort kommt, steht unter „Start“ bei den
  Stellen des Plans („Bei einer Antwort“).
- **Im laufenden Workout-Bild** stehen keine Marken (dort sitzt oben rechts der Haken „fertig“).
- **Titel und Beschriftung** ändert man über den Stift im Editor, nicht im Blatt.

**Abweichungen (E4):**

- **Keine neue Paket-Formatversion** (die offene Prüfung aus §2.2): Eine ältere App liest das
  Stück als Adresse `medien/…` — sein Knopf öffnet dort nichts (`components/links.py` lässt nur
  https zu), die Datei räumt sie weg. Der Plan bleibt lesbar und läuft; nur dieses Stück fehlt.
  Darum keine Schranke wie bei Kursplan (6) oder Antworten (7). **Nachgesehen** im Code von
  heute (`core.bedingung.inhalt_aus`, `views/workout.inhalt_karte`), **nicht** an einer alten
  APK ausprobiert.
- **Kamera vom Weg aus:** Die Seite bzw. das Blatt speichert erst, dann geht es zur Kamera; das
  Stück hängt beim Zurückkommen am Weg (`Ziel.fuer_ablage`) — das Blatt des Wegs ist dann zu.
- **Der erste Link** eines Wegs (Feld „Link“) bleibt, wie er ist, ohne Titel — für Pakete von
  früher.
- **Im Workout wird eine Datei am Weg nicht eingeblendet**, sondern steht als Zeile (die Karte
  entsteht bei jedem Neuzeichnen neu; ein Spieler darin begänne jedes Mal von vorn).
- **„Videos laden“** am Kopf des Plans sammelt die Links an Wegen weiter nicht ein.
- **Kurs-Bausteine „Weg“** tragen weiter nur Text und Link.

**Abweichungen (E3):**

- **Kein eigener Schritt „Benennen“:** Titel und Beschriftung stehen dort, wo das Stück entsteht —
  auf der Seite von Kamera, Fotoauswahl und Rekorder, in der Zeile des Editors, am Plan im Blatt
  des Stücks (es öffnet sich nach „Datei wählen“ und „aus Vorhandenem“ von selbst).
- **Im Kurs-Block keine Kamera:** Der Dialog des Blocks überlebt den Wechsel zur Kamera nicht.
  Dort gibt es Adresse, „Datei wählen“ und „aus vorhandenen Medien“ — ein Foto oder Video nimmt
  man an Übung oder Plan auf und holt es dann hierher.
- **Anhänge** (Notiz, Eintrag) behalten ihre Form (Symbolzeile, Büroklammer, Knopfzeile) — gleich
  sind Reihe, Namen und Symbole; ein Link und „aus Vorhandenem“ gibt es dort nicht (Frage a).
- **Ein Link behält in „Übung bearbeiten“ nicht seine Art** (er wird wie bisher als Video
  gespeichert) — nicht neu, hier nur vermerkt.
- **Symbol und Bild der Bewegung** behalten ihr eigenes Blatt mit Ablage.

**Abweichungen (E2):**

- **Mehrere fällige Stücke stehen untereinander** im selben Blatt (das erste Video läuft von
  selbst), nicht nacheinander mit „1 von 2“ — ein Spieler, der im offenen Blatt gegen den
  nächsten getauscht wird, ist in Flet heikel (ersetzte Controls).
- **Abgehakt wird mit dem Knopf „Gesehen“**, nicht mehr schon beim Öffnen des Stücks — es steht
  ja offen da.
- **Was die App nicht selbst abspielt**, bleibt eine Zeile mit einem Tipp: ein Link auf eine Seite,
  ein Video hinter einem Link, das noch nicht geladen ist, PDF und Ton.
- Das Blatt „Medien“ außerhalb des Übens (Plan, Übungsseite) zeigt weiter alles.
