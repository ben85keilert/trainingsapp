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

**Stand: nur geplant, nichts gebaut.** Fragen im Katalog als **P227**.

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
  (nur wenn gesetzt; ältere Apps übergehen es — wie bei `wann`, **für `text` noch nicht
  nachgeprüft**). Der Anhang hat `note` als Beschriftung; ob er zusätzlich einen Titel braucht,
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
