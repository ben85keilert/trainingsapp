# Planung: Medien kennzeichnen — Rollen, und die Animation beim Üben (16.11.2026)

Ben, 15./16.11.2026: „Schau dir dabei gleichzeitig an, wie man die Medien entsprechend
kennzeichnen kann als Erklärmaterial · als Begleitvideo beim Abspielen · ein Hintergrundbanner
zusätzlich zu dem Symbol im oberen Bildschirmrand · was es sonst so geben könnte an
Medienabschnitten.“ Kurz darauf: „**Vergiss das Hintergrundbanner.** Kostet zu viel Platz und
bringt nicht viel. Die Animation, die abgespielt werden kann beim Üben, müssen wir nur noch
einmal durchgehen.“

**Stand 18.11.2026: M1 und M2 gebaut, ohne Video als Bewegung; dazu das Symbol aus dem Paket**
(Ben, 18.11.2026: „mache das so, wie vorgeschlagen“ — Designbereich im Inhalte-Repo,
`pakete_design/`). Was gebaut ist, steht in §4 bei M1/M2. Ursprünglich: **nichts gebaut.** Dieses Papier ordnet, was es gibt (§1), schlägt **eine**
Kennzeichnung vor (§2) und geht die Animation durch (§3). Fragen an Ben: Katalog **P209**; es
führt den älteren Vorschlag **P94** (`plan_planblock.md` §C) mit dem am 12.11. Gebauten (P200)
zusammen.

**Bens Antworten, 16.11.2026** (Fragen aus §6):

| Frage | Antwort | Folge |
|---|---|---|
| a) Paket/Kurs bringt Animation mit | „Ja, Paket/Kurs darf und muss mitbringen. So kann man am Telefon einen Kurs erstellen, exportieren und am Laptop nacharbeiten, z. B. für die Medien gute Onlineorte finden. Bilder haben eine Zugehörigkeit: automatisch auf privat/eigene, man kann sie aber auch der Übung/Plan (falls letzterer gelöscht wird, Weitergabe an Übung) oder dem Kurs übergeben. So kann man selbst Material generieren.“ | neu §2.3 **Zugehörigkeit**; §3.3 |
| b) Form | „Bildfolge, Video, GIF, mehrere“ | drei Formen gleichberechtigt, **mehrere je Übung** (§3.3) |
| c) Wie entsteht sie | „Rechner, kurzes Video“ | am Rechner (Bildfolge, GIF) oder am Handy als kurzes Video (§3.3) |
| d) Je Planübung/Variante | „Keine Pflicht, kann aber haben. Material kann auf Variante übertragen werden. Fällt Variante weg, ist Material trotzdem verfügbar.“ | §2.3 Rückfall auf die Übung |
| e) Begleitvideo im Fokus | „Wenn Begleitvideo, wird die Uhr deutlich kleiner. Video hat Vollbildfunktion, Uhr kommt dann in eine Ecke mit Buttons. Erstelle Skizzen dafür.“ | §2.1; Skizzen V1–V6: <https://claude.ai/artifact/Jfw5MAsuQ4Y3q5PnmYdmaG> |

Nachgesehen, ob es dazu schon etwas gibt: `plan_planblock.md` §B/§C (P94),
`core/material.py`, `core/models.py` (`Media`), `ui/components/material.py`,
`material_rolle.py`, `medienliste.py`, `views/paketmedium.py`, `core/bewegungsbild.py`,
`ui/components/bewegungsbild.py`, `data/uebungsbilder.py`, `plan_taktgeber.md` (Stellen zum
Bild der Bewegung), `plan_anhaenge.md` (Video-Regel), Katalog P94/P200/P202–P205/T94.
**Nicht** gelesen: die Dart-Seite von `flet_hochladen` (wie genau sie skaliert).

---

## 1. Befund: ein Feld, zwei Wortlisten, zwei Sonderwege

| Was | Woran man es erkennt | Fundstelle | Stand |
|---|---|---|---|
| **Erklärung** | `Media.rolle` leer | `core/models.py:130-132` | gebaut 12.11. (P200) |
| **Begleitung** | `rolle = "begleitung"` | `core/models.py:174-175` | gebaut 12.11. |
| von selbst zeigen · ersetzt · gesehen | `zeigen`, `ersetzt`; „gesehen“ je Profil auf dem Gerät | `core/models.py:133-137`, `data/material.py` | gebaut 12.11. |
| **Bild der Bewegung** (die Animation) | **keine Rolle** — ein eigenes Bild mit `source = local` und `uri` unter `Bewegung/`; dazu eine mitgelieferte Folge je Sensor-Vorlage | `core/bewegungsbild.py` (`ist_bewegungsbild`, `EINGEBAUT`) | gebaut 5./7.11. |
| **Symbol** | **kein Medium** — `icon_key` und `image_path` an der Übung | `ui/components/uebungsbild.py` | gebaut 2.11. |
| Vorschlag P94 (7.11.) | `rolle`: symbol · bewegung · erklaerung · mitmachen · ansage · hinweis | `plan_planblock.md` §C | Vorschlag, offen |

Was daran nicht zusammenpasst:

- **P94 ist zur Hälfte überholt.** `erklaerung` ist gebaut; `mitmachen` ist gebaut, heißt aber
  `begleitung`. Der Katalog führt P94 weiter als offenen Vorschlag mit der alten Wortliste.
- **Die Animation ist kein gekennzeichnetes Medium**, sondern wird am Ablageort erkannt. Für
  eigene Bilder genügt das; ein Paket oder Kurs kann so keine liefern (§3.2 Nr. 2).
- **Was eine ältere App mit einer neuen Rolle tut:** `medien_zusatz` lässt nur `begleitung`
  durch, alles andere wird zur Erklärung (`core/models.py:189-191`). Ein Paket mit einer neuen
  Rolle bleibt lesbar; das Stück stünde dort in der Liste „Material“.

## 2. Vorschlag: eine Kennzeichnung

**Die Rolle sagt, wozu ein Stück dient; die Art (Video, Bild, Ton, PDF) sagt, was es ist.**
Drei Rollen genügen für das, was Ben nennt:

| Rolle | Uhr beim Ansehen | Haken „gesehen“ | Wo | Arten | Im Paket |
|---|---|---|---|---|---|
| **Erklärung** (Bestand, Vorgabe) | steht, solange das Blatt offen ist | ja | Übungsseite, Material-Blatt, Kurs-Block; auf Wunsch beim ersten ▶ von selbst — seit 17.11.2026 auch im Workout, sobald der Schritt beginnt (`plan_uhr_fokus.md` §10.7) | Video, Bild, Ton, PDF, Link | ja |
| **Begleitung** (Bestand) | läuft | nein | Material-Blatt; **neu: im Fokus selbst** (siehe unten) | Video, Ton | ja |
| **Bewegung** (Funktion gebaut, Name neu) | läuft | nein | Fokus, Ebene „Bewegung“, im Takt | Bildfolge, Video, GIF — mehrere (entschieden 16.11.) | heute nein (§3.2 Nr. 2); **entschieden: ja** (§3.3) |

Im Material-Blatt sind die Rollen schon eigene Abschnitte (`ui/components/material.py:217-231`:
Neues oben, „Begleitung“, übrige Erklärungen, unten das Ersetzte) — die „Medienabschnitte“ sind
also die Rollen.

### 2.1 „Begleitvideo beim Abspielen“ — die Lücke

Eine Begleitung lässt die Uhr weiterlaufen, **aber man sieht sie nicht neben der Uhr**: Eine
Paketdatei öffnet die eigene Ansicht `…/paketmedium/<datei>` („Videos laufen hier und nur hier“,
`ui/views/paketmedium.py:3-4`), ein Link den Browser (`ui/components/medienliste.py:46-51`). Uhr,
Takt und „Eintragen“ sind in der Zeit verdeckt. P94 nannte das Ziel: „das Video **ist** die
Fläche, die Uhr läuft daneben“.

Vorschlag: Eine Begleitung aus einer **Paketdatei** läuft **im Fokus** als weitere Ebene — Chip
„Video“ neben Takt · Bewegung · HF · Kurve; ein Ton braucht keine Fläche, nur eine Zeile mit ▶/⏸.
Gestartet wird auf Tipp, nie von selbst. Links bleiben, wie sie sind.

**Entschieden (Ben, 16.11.2026):** „Wenn Begleitvideo, wird die Uhr deutlich kleiner. Video hat
Vollbildfunktion, Uhr kommt dann in eine Ecke mit Buttons.“ Skizzen V1–V6
(<https://claude.ai/artifact/Jfw5MAsuQ4Y3q5PnmYdmaG>):

| Bild | Zeigt |
|---|---|
| V1 | heute: Zeit groß, das Video öffnet eine eigene Ansicht |
| V2 | mit Begleitvideo: die Uhr in **einer Zeile** (Zeit klein, Stand und Balken daneben), Steuerzeile, darunter das Video als Fläche mit ⛶; Chips wählen, was die Fläche zeigt (Video · Bewegung · Takt · HF); „Eintragen“ bleibt |
| V3 | Vollbild hochkant: Video über die Breite, die Uhr als Karte in einer Ecke mit Pause · Fertig · Vollbild verlassen |
| V4 | Vollbild quer, Ruhe: nur die Zeit als kleine Pille in der Ecke; Tipp öffnet V5 |
| V5 | Vollbild quer, offen: Zeit, Stand, Pause · Fertig · Überspringen · Vollbild verlassen |
| V6 | Begleitung als Ton: eine Zeile unter der Steuerzeile, die Uhr bleibt groß |

Ben, 16.11.2026: „Die Skizzen schauen gut aus“ und, zu „Eintragen“ im Vollbild: „Ja, im
Vollbild voller Fokus auf die Bewegung. Für Eintragung muss man raus aus dem Fokus und die
Standardansicht.“ Welche Ecke, bleibt beim Bau zu wählen (in V3–V5 als Tweak umstellbar);
Vorgabe wie gezeichnet: hochkant unten rechts, quer oben rechts.

**Hoch- und Querformat** (Bens Frage, 16.11.2026: „Unterscheiden die Videos auch, ob ein Video
im Hoch-/Querformat aufgenommen wurde, und drehen das Bild entsprechend?“): Die Skizzen tun das
noch nicht — V3 zeigt ein Quervideo hochkant, mit schwarzen Rändern. **So soll es werden:** Das
Vollbild richtet sich nach dem Video — ein quer aufgenommenes öffnet quer (die App dreht dafür
wie beim Live-Vollbild der Messung), ein hochkant aufgenommenes bleibt hochkant und füllt den
Bildschirm; in der kleinen Fläche (V2) bekommt ein Hochkantvideo eine höhere Fläche statt
Rändern links und rechts. **Ungeprüft:** woher die App das Format kennt. Die API von
`flet-video` (nachgesehen im MCP-Server) nennt weder Breite noch Höhe des Videos; es bliebe,
sie beim Ablegen der Datei aus ihrem Kopf zu lesen (wie `core.bewegungsbild.png_masse` für
Bilder) und am Medium zu merken — für Links geht das nicht, dort bliebe „quer“ die Annahme.
Videos mit Drehvermerk (Handy hochkant gehalten, Bild quer gespeichert) sind dabei die Falle;
vor dem Bau am Gerät mit einem echten Handyvideo probieren.

Machbarkeit, nachgesehen im MCP-Server `flet` (API der installierten Version): `Video` aus
`flet-video` hat `fullscreen`, `on_enter_fullscreen`/`on_exit_fullscreen`, `play`/`pause` und
nimmt unter `controls` ein **eigenes Control über dem Video** an, auch getrennt je Modus
(normal/Vollbild). Die Uhr-Ecke lässt sich also über das Video legen. **Ungeprüft:** ob dieses
Control im Vollbild je Tick nachzieht (der Fokus aktualisiert alle 0,2 s) und was die
Web-Fassung daraus macht — vor dem Bau eine Probe am Gerät.

Das ändert eine Setzung, darum ausdrücklich: „**nur hier** läuft ein Video, nirgends
automatisch“ steht für Anhänge in `plan_anhaenge.md:178` (Ben, 19.10.2026: „Im Tagebuch keine
Videos direkt laufen lassen, nur Frontbild klickbar“, `:19`) und wurde für Paketmedien
übernommen. Die Begründung dort gilt dem Tagebuch und dem eigenen Video; ein Paketvideo, das die
Person im Fokus antippt, ist ein anderer Fall — die Entscheidung ist trotzdem Bens (Frage e).
**Ungeprüft:** ob `flet-video` im Fokus neben dem Ticker (0,2 s) ruhig läuft und was die
Web-Fassung daraus macht. Vor dem Bau am Gerät probieren.

### 2.2 Was es sonst geben könnte — und was davon keine Rolle braucht

| Idee | Einordnung | Empfehlung |
|---|---|---|
| Merkblatt, Handzettel (PDF) | Erklärung mit der Art PDF — gibt es | keine neue Rolle |
| Fassungen eines Stücks (mit/ohne Untertitel, Sprache; Ben in P200) | `ersetzt` gibt es („die Erweiterung ersetzt das Standard-Video“) | erst mit einem echten Fall |
| Worauf achten (Text) | Beschreibung in Abschnitten — gibt es | keine Rolle |
| Anderes Medium je Wahl im Kurs | `zeigen_wenn` am Block (`plan_kurs_ablauf.md` §4) | dort |
| Inhalt, der mit einem Weg aufgeht | `Kante.inhalt` (Text, Link) — gibt es | — |
| **Ansage** (gesprochene Anleitung, Zählansage; P94) | Ton, der am Start oder je Phase spielt — verwandt mit den Klängen des Takts | später; erst die Begleitung als Ton im Fokus |
| **Video als Uhr** (P205 C; P94: „Timer-Abschnitt wie das Video“) | Begleitung, deren Länge die Uhr ist | Ben, 12.11.: „C erst nach Ausarbeitung“ |
| Symbol als Bild aus dem Paket | heute nur Symbolname im Paket, eigenes Foto lokal | nur auf Wunsch |
| **Hintergrundbanner** | — | **abgewählt** (Ben, 16.11.2026) |

### 2.3 Zugehörigkeit: privat, bis man es übergibt (Ben, 16.11.2026)

„Bilder haben eine Zugehörigkeit: automatisch auf privat/eigene, man kann sie aber auch der
Übung/Plan (falls letzterer gelöscht wird, Weitergabe an Übung) oder dem Kurs übergeben. So kann
man selbst Material generieren.“ Und zu Varianten: „Material kann auf Variante übertragen
werden. Fällt Variante weg, ist Material trotzdem verfügbar.“

| Zugehörigkeit | Wo es hängt | Reist mit | Fällt der Besitzer weg |
|---|---|---|---|
| **privat** (Vorgabe) | Ablage der Person | nie | — |
| **Übung** | Medien der Übung | der Übung im eigenen Paket | → **privat** (Ben, 16.11.) |
| **Variante** | Medium der Übung mit der Marke der Variante | der Übung | → **Übung** |
| **Plan** (Planübung) | Medien der Planübung | dem Plan im Paket bzw. Kurs | → **Übung** |
| **Kurs** | Block im Kapitel | dem Kurs im Paket | → **privat** (Ben, 16.11.) |

Was davon schon da ist: Der Weg „**Datei fürs Paket**“ in beiden Editoren (U4, `ui/paketdatei.py`)
macht aus einer eigenen Datei eine Paketdatei — sofort ohne Ortsangaben, nach Prüfsumme
abgelegt, an Übung oder Planübung gehängt. Das **ist** „der Übung bzw. dem Plan übergeben“,
nur als eigener Aufnahme-Weg. Neu wäre:

- **Übergeben statt neu aufnehmen:** ein Stück aus der privaten Ablage (Symbol, Bild der
  Bewegung, eigene Aufnahme, **Anhang an einem Eintrag**) wählen und übergeben — als
  **bereinigte Kopie**; das private Original bleibt privat und unverändert (Ben, 16.11.2026:
  ja, §6 Nr. 2 und 3).
- **Kurs als Ziel** und **Variante als Marke** am Medium.
- **Rückfall:** Beim endgültigen Löschen eines Plans wandern übergebene Stücke an die Übung
  (heute verschwinden sie mit der Planübung); entfällt eine Variante, fällt nur die Marke.
- **Der Rundweg, den Ben nennt:** am Telefon bauen → als eigenes Paket exportieren (Dateien
  reisen mit) → am Laptop nacharbeiten, etwa eine Datei durch einen Link auf einen Onlineort
  ersetzen. Das Paketwerkzeug kennt dafür noch keinen Schritt „Datei → Link“ (Rolle, Titel und
  „ersetzt“ behalten) — ein kleiner Zusatz.

**Regeln, die damit anders heißen müssen** — erst beim Bau, heute stimmen sie noch: In
CLAUDE.md steht für eigene Symbole, das Bild der Bewegung und Anhänge jeweils „nie in Paket,
Export oder Sync“. Mit Bens Entscheidung wird daraus „**privat, bis die Person es übergibt**“;
was übergeben ist, reist bereinigt. Das gilt auch für **Anhänge** an Einträgen (Ben,
16.11.2026: ja) — der Anhang selbst bleibt privat, hinaus geht die übergebene Kopie.

## 3. Die Animation beim Üben — Durchgang

### 3.1 Was es gibt

| Form | Wie sie läuft | Fundstelle |
|---|---|---|
| **Bildfolge** — ein PNG oder JPEG, dessen Breite ein Vielfaches der Höhe ist: quadratische Bilder nebeneinander, der **Hinweg** der Bewegung | **im Takt**: „ab“/„ein“ vorwärts, „auf“/„aus“ rückwärts, „halten“ steht, „frei“ pendelt; ohne Takt ein Pendel, 1,5 s je Weg | `core/bewegungsbild.py:81-120`, `PENDEL_S` `:39` |
| **GIF** | Schleife mit eigenem Tempo, **nicht** im Takt | `ui/components/bewegungsbild.py:57-69` |
| **Mitgeliefert: Kniebeuge** (12 Bilder) | wie eine Bildfolge; gilt für Übungen mit der Sensor-Vorlage „kniebeuge“ ohne eigenes Bild | `EINGEBAUT`, `core/bewegungsbild.py:36` |

Gezeigt im Fokus als Ebene „Bewegung“ (Chip, je Gerät gemerkt) und im „Während“ des Timers, 180
Pixel hoch. Gewählt in „Übung bearbeiten“ → Blatt „Bild der Bewegung“ (Foto hochladen, Foto
aufnehmen, Ablage `Medien/Bewegung/`). Das eigene Bild ist app-privat: nie in Paket, Export
oder Sync.

### 3.2 Was beim Durchgehen auffällt

1. **Am Handy kommt eine eigene Animation kaum an.**
   - Ein **GIF** aus der Fotoauswahl wird zum stehenden JPEG (bekannt, `plan_taktgeber.md`
     Z. 270–272: „Dart-Änderung, eigener Schritt“).
   - Eine **Bildfolge** geht am Handy denselben Weg: `verkleinern` schreibt „ein Foto als JPEG
     mit der kürzeren Seite `kurze_seite`“ (`erweiterungen/flet_hochladen/…/hochladen.py:9-10`).
     Die Folge wird aber nur erkannt, wenn die Breite **genau** ein Vielfaches der Höhe ist
     (`bilder_in`, `core/bewegungsbild.py:70-78`: 300 × 256 gilt als ein Bild). Ein Pixel
     Rundung beim Skalieren macht aus der Animation ein Standbild; ein durchsichtiger
     Hintergrund geht im JPEG verloren. **Ungeprüft**, ob ein Streifen heil ankommt — die
     Dart-Seite habe ich nicht gelesen, am Gerät ist es nicht probiert.
   - Am Rechner bleibt die Datei, wie sie ist (`ui/views/uebung_bearbeiten.py:309-323`).
   - Folge: Verlässlich ist heute nur die eingebaute Kniebeuge.
2. **Kein Paket und kein Kurs kann eine Animation liefern.** Eingebaut ist genau eine Folge.
   Die Regel „nie in Paket, Export oder Sync“ meint das **eigene** Bild („wie die eigenen
   Symbole … app-privat“, `core/bewegungsbild.py:8-9`); `plan_planblock.md` §C sah schon vor:
   „später im Paket (Bildfolge als Datei neben der TOML)“. Für Kurse, die Übungsmaterial
   liefern sollen, ist das die eigentliche Lücke.
3. **Nur je Übung.** Die Planübung zählt nur für die Sensor-Vorlage
   (`bewegung_im_fokus`, `ui/components/bewegungsbild.py:117-133`); eine Variante oder ein Plan
   kann keine eigene Animation haben.
4. **Ein Bild je Phase ist vorbereitet, nicht gebaut** (`Phase.bild`, `core/takt.py:213`;
   `plan_taktgeber.md` Z. 274). Die Bildfolge deckt Hin und Zurück ab; Bewegungen mit mehr als
   zwei Abschnitten (ab · halten · drehen · auf) kann sie nicht zeigen.
5. **Ohne Takt** pendelt die Folge fest mit 1,5 s je Weg — unabhängig davon, wie schnell die
   Übung gedacht ist.
6. **Niemand kann in der App eine Bildfolge herstellen.** Die Kniebeuge kommt aus einem Skript
   (`scripts/bewegung_kniebeuge.py`). Wer eine eigene will, baut den Streifen außerhalb.
7. **Gerätetest T94** (Kniebeuge-Bildfolge im Takt) steht im Katalog ohne Erledigt-Vermerk.

### 3.3 Was daraus folgt (entschieden 16.11.2026)

- **Animation im Paket und im Kurs — ja, „darf und muss“:** ein Medium mit `rolle = "bewegung"`
  und `source = "paket"`, bereinigt wie jede Paketdatei. Das eigene Bild bleibt privat, bis es
  übergeben wird (§2.3). Ältere Apps zeigen das Stück in der Material-Liste (§1) — unschön,
  nicht falsch.
- **Drei Formen, gleichberechtigt:** Bildfolge (läuft im Takt), **Video** (kurz, als Schleife,
  ohne Ton) und GIF (Schleife). Neu ist das Video als Animation: Das ist am Handy der einfache
  Weg — die Kamera der App nimmt es auf, der Weg „Datei fürs Paket“ kann es schon (§2.3).
- **Mehrere je Übung.** Heute hält die Übung genau eines (`BewegungsbildRepo.setzen` ersetzt das
  vorhandene, `data/uebungsbilder.py:200-218`). Neu: eine Liste; im Fokus zeigt die Fläche eines,
  gewechselt wird durch Blättern. Eine ist die **Vorgabe**; ein Kurs darf sie je Planübung
  umstellen („damit man eine Bewegung entwickeln kann“, §6 Nr. 4), eine Variante bringt ihre
  über die Marke aus §2.3 mit.
- **Entstehen:** am Rechner (Bildfolge, GIF) oder am Handy als kurzes Video. Ich lese „kurzes
  Video“ so, dass **das Video selbst** die Animation ist — nicht, dass die App daraus Bilder
  zieht. Für Bildfolge und GIF vom Handy gilt weiter §3.2 Nr. 1: erst am Gerät prüfen, ob ein
  Streifen die Fotoauswahl übersteht.
- **Je Planübung und Variante:** keine Pflicht, aber möglich; fällt Plan oder Variante weg,
  bleibt das Stück an der Übung (§2.3).
- **Nicht jetzt:** Bild je Phase, Herstellen einer Bildfolge in der App.

## 4. Stufen (nach Bens Ja)

| Stufe | Inhalt | Braucht |
|---|---|---|
| M1 | Wortliste zusammenführen: `rolle = "bewegung"` lesen und schreiben; P94 im Katalog schließen; `uebungspakete.md` nachführen | a: **ja** |
| M2 | Animation im Paket: Bildfolge (Werkzeug prüft „Breite = n × Höhe“), Video, GIF; **mehrere je Übung** mit Blättern im Fokus; Bereinigen; Vorrang | a, b: **ja**; Vorgabe je Planübung (§6 Nr. 4) |
| — | **Gebaut 18.11.2026 (M1, M2):** `BEWEGUNG`/`SYMBOL`/`ROLLEN` in `core/models.py`, beide nicht im Material (`core/material.py`); `bewegungen` in `core/bewegungsbild.py` (Vorrang: Planübung · eigenes Bild · Übung, die eingebaute Folge nur ohne alles); `Bewegungswahl` im Fokus mit „1/2 ›“ (`ui/components/bewegungsbild.py`); „Bewegung“ als Rolle im Editor für Bilddateien (`material_rolle.py`); GIF und SVG im Paket mit Bereinigen (`core/bereinigen.py`), SVG beim Import noch einmal geprüft (`Paketmedium.kopieren`); `rollen_pruefen` im Werkzeug. **Nicht gebaut:** Video als Bewegung (Regel „kein Video startet von selbst“ §5 und Probe am Gerät — `pruefen` meldet es als Fehler), mehrere **eigene** Bilder je Übung (die private Ablage hält weiter eines, M3). **Symbol aus dem Paket** (§2.2 „nur auf Wunsch“ — Bens Wunsch 18.11.2026): `rolle = "symbol"`, SVG eingefärbt, PNG wie es ist, eigenes Foto geht vor (`ui/components/uebungsbild.py`). Tests: `tests/test_medienrollen.py`, `tests/test_ui_medienrollen.py`. | — |
| M3 | **Zugehörigkeit** (§2.3): übergeben aus der privaten Ablage, Kurs als Ziel, Marke der Variante, Rückfall an die Übung; Regeln in CLAUDE.md umformulieren; Werkzeugschritt „Datei → Link“ | a, d: **ja**; §6 Nr. 1–3: ja |
| M4 | Gerät: Streifen und GIF durch die Fotoauswahl (§3.2 Nr. 1); kurzes Video als Animation aufnehmen | c: Rechner + kurzes Video |
| M5 | Begleitung im Fokus nach den Skizzen V2–V6 (Uhr-Zeile, Fläche, Vollbild mit Uhr-Ecke, Ton-Zeile) — erst nach einer Probe mit `flet-video` am Gerät | e: **ja**; Rückmeldung zu den Skizzen |
| später | Ansage, Video als Uhr, Bild je Phase | — |

## 5. Regeln, die gelten

- Eigene Dateien sind **privat, bis die Person sie übergibt** (§2.3; Ben, 16.11.2026) — bis
  das gebaut ist, gilt der heutige Wortlaut in CLAUDE.md („nie in Paket, Export oder Sync“).
- Was im Paket reist, ist bereinigt (ohne Ortsangaben) und trägt eine Lizenz
  (`.claude/rules/pakete.md`).
- Kein Video startet von selbst.
- „gesehen“ bleibt auf dem Gerät; die Rolle reist im Paket (Ben, 12.11.2026).
- Keine neue Netzverbindung (Videos laden: P202, getrennt) — seit 17.11.2026 entschieden und gebaut
  in `docs/plan_rueckweg_handy.md` Stufe 7 (Videos hinter Links: je Server nach Rückfrage, nur im
  WLAN, `core/linkvideos.py`); die Rollen hier ändert das nicht.

## 6. Fragen an Ben (Katalog P209) — a bis e beantwortet am 16.11.2026

Die Antworten stehen in der Tabelle am Kopf. Die Folgefragen daraus hat Ben am selben Tag
beantwortet:

1. **Fällt der Besitzer ganz weg** (Übung oder Kurs gelöscht): das Stück geht zurück in die
   private Ablage — **ja.**
2. **Übergeben als bereinigte Kopie**, das private Original bleibt — **ja.**
3. Die Zugehörigkeit gilt auch für **Anhänge** an Einträgen: Ein Foto oder Video vom eigenen
   Üben darf der Übung als Material übergeben werden — **ja.** Der Anhang selbst bleibt, was er
   ist; hinaus geht nur die übergebene Kopie.
4. **Mehrere Animationen:** „Vorgabe wird gesetzt. Kann von Kurs auch geändert werden im Plan,
   darauf muss es Zugriff geben, damit man eine Bewegung entwickeln kann.“ — Eine Animation ist
   die Vorgabe; ein Kurs darf sie je Planübung umstellen (Baustein `plan_einstellen`,
   `plan_kurs_ablauf.md` §3.2), so dass Kapitel für Kapitel eine andere Bewegung vorn steht.
5. **Vollbild ohne „Eintragen“:** „Ja, im Vollbild voller Fokus auf die Bewegung. Für
   Eintragung muss man raus aus dem Fokus und die Standardansicht.“

Offen ist damit nur noch, was eine Probe am Gerät braucht: das Format der Videos (§2.1), die
Uhr-Ecke im Vollbild im Takt, Streifen und GIF durch die Fotoauswahl (§3.2 Nr. 1).

Die Fragen a bis f, wie sie gestellt waren, mit meiner Empfehlung zuerst:

- **a)** Darf ein **Paket oder Kurs eine Bildfolge mitbringen** (Rolle „Bewegung“)? *Ja* — ohne
  das können Kurse keine Animation liefern. Das eigene Bild bleibt privat.
- **b)** **Bildfolge als Hauptform**, GIF nur geduldet? *Ja.*
- **c)** **Wie entsteht eine Animation?** (i) am Rechner bzw. über Pakete, (ii) in der App aus
  zwei, drei Fotos (Anfang · Ende), (iii) aus einem kurzen Video. *Zuerst (i)* und am Gerät
  prüfen, ob ein Streifen die Fotoauswahl übersteht (§3.2 Nr. 1).
- **d)** Braucht eine **Planübung oder Variante eine eigene Animation**? *Vorerst nein.*
- **e)** **Begleitvideo im Fokus** als Ebene neben der Uhr — ja, obwohl Videos bisher nur in
  der eigenen Ansicht laufen? *Ja, auf Tipp, nach einer Probe am Gerät.* Wenn ja: Animation und
  Video teilen sich **eine** Fläche (der Chip wählt), damit der Fokus nicht voller wird.
- **f)** Fehlt in §2.2 etwas, das du unter „Medienabschnitten“ meintest?
