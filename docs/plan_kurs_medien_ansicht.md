# Planung: Kurs — Medien sichtbar, Titelbild, übersichtlicher bauen, direkter durchspielen (27.11.2026)

Ben, 27.11.2026: „In den Skizzen von vorher hast du bei B eine Videovorschau und eine
übersichtlichere Trennung der Bereiche. … für mich schaut die Kursentwicklung und die
Kursanwendung verschieden aus. Lass uns beides, Kurserstellung und Kurs durchspielen, noch
einmal aufwerten: Medienvorschau — im laufenden Kurs sind Videos/Bilder und Co. in das Kapitel
direkt eingebunden. Man kann sie vergrößern oder auch klein abspielen. Mediengestaltung — ein
Video soll ein Titelbild bekommen können … entweder ein eingefügtes Bild aus dem Video selbst
oder einfach der Titeltext. Wie gestaltet sich das Frontbild auf einem Video bei YouTube? …
Auch in der Kursgestaltung soll das Medium namentlich sichtbar sein … Man kann gar nicht
erkennen, was Audio-Video-Bild ist. … Mache weitere Vorschläge, wie man Kursgestaltung
übersichtlicher machen kann. Der Ablauf genauso direkter, weniger Rumgeklicke, direkteres
Starten.“

**Stand: Plan mit Skizzen, nichts gebaut.** Fragen an Ben in §8 (Katalog P231).

Gesucht im Katalog: `frontbild`, `titelbild`, `vorschaubild`, `thumbnail`, `medienvorschau`,
`eingebettet` — kein Treffer zur Sache (nur P44, P175 am Wort). Gelesen: P225, P227, P229,
P230 (Entscheidungszeilen); `plan_kurs_uebungen.md` §14.7, §15. Code gelesen:
`components/kursblock.py` (Block „Medium“, Zeile 822), `components/medienliste.py`
(`medium_zeile`, `_zeile`), `core/models.py` (`Media`), `ui/verkleinern.py` (Frontbild beim
Verkleinern), `views/anhang_aufnahme.py` (Frontbild der Aufnahme), `views/kurs_bearbeiten.py`
(`zeile`, `block_editor`). Nur gefunden: `components/videospieler.py`, `core/videoinfo.py`.

## 1. Befund

| Stelle | Heute | Quelle |
|---|---|---|
| Medium im laufenden Kapitel | **eine Zeile**: Symbol, Titel, Pfeil — der Tipp öffnet die Ansicht `…/paketmedium/…`. Kein Bild, kein Abspielen im Kapitel | `kursblock.py:822`, `medienliste._zeile` |
| Medium „vorher“ im Lauf | dieselbe Zeile. In Skizze B2 war es eine große Kachel — am 26.11. als „bewusst nicht gebaut“ vermerkt (`plan_kurs_uebungen.md` §14.7). **Das war eine Abweichung von der Skizze, keine Erfüllung** | — |
| Zeile im Kapitel-Editor | „**Medium**“ fett, darunter der Titel blass, ein Abspiel-Symbol für jede Art. Art, Dauer, Größe, Herkunft: nicht zu sehen | `kurs_bearbeiten.zeile`, `ART_SYMBOL` |
| Karte im Editor | Titel, Beschriftung, „Foto — liegt auf dem Gerät“ (seit 0.3.104). Kein Bild, nichts zum Ansehen | `block_editor` |
| Titelbild eines Videos | **Anhänge** (Eintrag, Notiz) haben ein Frontbild: Die Kamera nimmt beim Start ein Foto, Android schreibt beim Verkleinern das erste Bild der Kopie. **Paketdateien** (Übung, Plan, Kurs) haben keins; `Media` hat kein Feld dafür | `anhang_aufnahme.py:693`, `ui/verkleinern.py:60` |
| Dauer, Maße eines Videos | lesbar ohne Abspielen | `core/videoinfo.py` |
| Abspielen | nur in der eigenen Ansicht (`paketmedium`, `/anhang/<id>`) — so steht es als Regel in CLAUDE.md und `plan_medien_einstellungen.md` §2.4 | — |

**YouTube** (nachgesehen, Quelle unten): Jedes Video hat ein Vorschaubild im Format 16:9.
YouTube schlägt selbst Bilder aus dem Video vor; wer mag, lädt ein eigenes hoch (JPG oder PNG,
Mindestbreite 640 px). In Listen steht darauf unten rechts die Dauer. Nicht gefunden: wie
viele Vorschläge es sind und in welcher Größe.
Quelle: <https://support.google.com/youtube/answer/72431?hl=en>

Daraus für uns: **16:9, immer ein Bild, drei Wege dahin** — aus dem Video, ein eigenes, oder
(unser Zusatz, wo es kein Bild gibt) eine Karte nur mit dem Titel.

## 2. Die Medienkarte — ein Baustein für Kurs, Lauf und Editor

Ein neuer Baustein `components/medienkarte.py` ersetzt die Zeile überall, wo ein Kurs ein
Medium **zeigt**: Block „Medium“ im Kapitel, Medien „vorher“ und „nachher“ im Lauf, Folgen im
Ergebnis — und die Vorschau im Editor. Derselbe Baustein an allen Stellen ist der Kern von
„Entwicklung und Anwendung sehen gleich aus“.

| Art | Im Kapitel | Tipp | Groß |
|---|---|---|---|
| **Video** (Datei) | Fläche 16:9 mit Titelbild, ▶ in der Mitte, Dauer unten rechts; darunter Titel fett, Beschriftung | spielt **in der Karte** — Leiste mit Pause, Position, ⤢ | ⤢ öffnet `paketmedium` an derselben Stelle des Videos |
| **Bild** | das Bild in voller Breite (höchstens 4:3 hoch, sonst beschnitten) | öffnet groß, mit Zoom | — |
| **Ton** | schmale Leiste: ▶, Titel, Dauer, Fortschritt — kein leeres Bildfeld | spielt in der Leiste | — |
| **PDF** | Titelkarte mit „PDF · 3 Seiten“ | öffnet die Ansicht | — |
| **Link auf ein Video** | wie Video, sobald geladen; vorher Titelkarte mit „von <Server> — laden“ | lädt bzw. spielt | wie Video |
| **Link auf eine Seite** | Titelkarte mit Server und ↗ | öffnet den Browser | — |

Regeln:

- **Es spielt immer nur eines.** Startet ein zweites, hält das erste an; verlässt man das
  Kapitel, hält alles an.
- Der Videospieler entsteht **erst mit dem Tipp** — bis dahin ist die Karte ein Bild. Zehn
  Videos im Kapitel sind zehn Bilder, kein Spieler.
- Oben links auf jeder Karte ein kleines Etikett mit der Art: VIDEO · BILD · TON · PDF · LINK.
- **Die Regel „Videos laufen nur in ihrer eigenen Ansicht“ ändert sich** für Kurse (Frage a).
  Übung, Plan und Fokus bleiben, wie sie sind — dort gilt weiter das Material-Blatt.
- „Gesehen“ (Material, `core/material.py`) hakt ab, sobald das Stück wirklich spielt bzw. groß
  offen ist — wie heute `beim_oeffnen`.

**Ungeprüft, darum Stufe 0:** ob `flet_video` in einer scrollenden Liste am Gerät sauber
spielt, anhält und wieder verschwindet (Android-Fläche über Flutter). Erst ein Versuch am
Pixel, dann der Bau.

## 3. Titelbild

### 3.1 Feld

`Media.titelbild` (neu, Text):

| Wert | Bedeutung |
|---|---|
| leer | **automatisch**: das Bild, das beim Aufnehmen oder Hinzufügen entstand; gibt es keins, die Titelkarte |
| `medien/<sha256>.jpg` | ein Bild in der Paketablage — bereinigt ohne Ortsangabe wie jede Paketdatei, reist im Paket mit |
| `text` | **nur der Titel**: eine Fläche in der Farbe des Profils mit dem Titel groß und der Art klein |

Das automatische Bild liegt gerätelokal neben der Datei (`<sha256>.jpg` im Ordner der Ablage)
und reist **nicht** mit — der Empfänger eines Pakets erzeugt es selbst oder sieht die
Titelkarte. Ein gewähltes Titelbild reist mit. Paket-Formatversion 10 (`docs/uebungspakete.md`
bekommt zuerst den Eintrag); ältere Apps überlesen das Feld.

### 3.2 Blatt „Titelbild“ (am Medium, im Editor)

1. **Aus dem Video** — das Video mit Regler; „Dieses Bild nehmen“ hält das Bild an der Stelle
   fest. Dazu drei Vorschläge (Anfang, Mitte, Ende), ein Tipp nimmt einen.
2. **Eigenes Bild** — Kamera, Fotoauswahl oder Datei (das eine Menü „Medium hinzufügen“,
   beschränkt auf Bilder); zugeschnitten auf 16:9.
3. **Nur Titel** — die Titelkarte; der Text ist der Titel des Mediums.
4. **Automatisch** — zurück zur Vorgabe.

### 3.3 Woher das Bild aus dem Video kommt

| Gerät | Weg | Stand |
|---|---|---|
| Aufnahme in der App | die Kamera nimmt beim Start ein Foto — wie bei Anhängen | vorhanden, nur für Paketdateien noch nicht behalten |
| Android, Datei oder Fotoauswahl | `flet_hochladen` schreibt heute nur beim Verkleinern ein Frontbild. Ein eigener Aufruf „Bild an Stelle t“ fehlt (Kotlin: `MediaMetadataRetriever`) | **zu bauen**, Erweiterung |
| Rechner | ffmpeg (`core.verkleinern.frontbild_befehl`) — nur, wo es installiert ist | vorhanden |
| Browser | **ungeprüft** (Bild aus `<video>` über eine Zeichenfläche) | sonst Titelkarte |

Geht es auf einem Gerät nicht, bleibt die Titelkarte — die Karte sieht nie leer aus.

### 3.4 YouTube- und andere Links

Ein Vorschaubild von YouTube zu holen wäre **eine neue Netzverbindung** (zu Googles
Bildservern, schon beim Öffnen des Kapitels, ohne Tipp). Dafür gilt die Regel aus CLAUDE.md:
Schalter, Hinweis, Nachtrag in `docs/recht/40_toms.md`, `80_store_freigaben.md`,
`build/solo.toml`. **Empfehlung: nicht holen.** Ein Link zeigt die Titelkarte oder ein eigenes
Bild (Frage d).

## 4. Kursgestaltung: was ist was

### 4.1 Zeilen der Kapitel-Liste

Heute steht die **Art** fett („Medium“, „Text“, „Frage“) und der Inhalt blass darunter.
Vorschlag: umgekehrt.

- **Erste Zeile: der Inhalt** — Titel des Mediums, Überschrift des Texts, die Frage, die Übung.
- **Zweite Zeile: Art und Eckdaten** — „Video · 0:42 · 3,1 MB“, „Ton · 1:10“, „Bild“, „Link ·
  example.org“, „Text · 3 Zeilen“, „Frage · Auswahl, 3 Antworten“, „Übung machen · 30 s ·
  freiwillig“.
- **Links statt des Symbols:** bei Medien das Titelbild klein (64 × 36) mit dem Art-Symbol in
  der Ecke; bei allem anderen das Symbol der Art auf einer Fläche in der Farbe der Art.

### 4.2 Karte „Medium“ im Editor

Oben die **Medienkarte selbst** (§2, abspielbar), darunter „Anderes Medium“ und „Titelbild …“,
dann Titel und Beschriftung. Eine Zeile Eckdaten: Art, Dauer, Größe, „aufgenommen am …“ bzw.
„aus der Fotoauswahl“ / „Datei“ / „aus Übung Kniebeuge“. Dasselbe klein bei „Medien am Lauf“.

### 4.3 Weitere Vorschläge

| | Vorschlag | Warum |
|---|---|---|
| G1 | **Folgen eingerückt unter ihrer Frage** — statt „nur wenn … = leicht“ kursiv in einer flachen Liste: unter der Frage bzw. dem Lauf je Antwort eine eingerückte Zeile mit Antwort-Chip („leicht ›“). Bausteine „Am Plan“ stehen dort als Verweiszeile | man sieht den Zusammenhang, ohne zu lesen |
| G2 | **Einfügen an der Stelle** — ein kleines „+“ zwischen zwei Zeilen; „+ Im Kapitel“ am Ende bleibt | heute: ans Ende legen, hochschieben |
| G3 | **Ziehen statt Pfeile** — Griff links, die Pfeile fallen weg; ✕ bleibt | zwei Knöpfe weniger je Zeile, mehr Platz für den Titel |
| G4 | **Vorschau** in der Titelleiste (Auge): das Kapitel, wie die Person es sieht — mit Antworten zum Durchspielen, ohne dass etwas gespeichert oder der Kurs gestartet wird | heute: speichern, zurück, Kurs öffnen, Kapitel öffnen |
| G5 | **‹ Kapitel 2 von 5 ›** im Kopf des Editors | heute: zurück zur Kursseite, nächstes Kapitel antippen |
| G6 | **Block verdoppeln** im ✕-Menü der Zeile | fünf ähnliche Fragen |
| G7 | **Bausteine „Am Plan“ auch an Ort und Stelle** (wie §15 für Blöcke) | zwei Bedienweisen auf einer Seite |
| G8 | **Bearbeiten in der Ansicht** (später, eigene Stufe): Der Editor *ist* die Kapitelansicht mit Stift — ein Tipp auf ein Element öffnet seine Karte | Entwicklung und Anwendung sind dann dasselbe Bild |

G1–G3 und G5–G7 ändern nichts am Verhalten eines Kurses, nur am Editor. G8 ersetzt G4 und
die Liste; es lohnt erst, wenn die Medienkarte und die neuen Zeilen stehen.

## 5. Kurs durchspielen: direkter

**Vor dem Bau nachstellen** (Regel aus CLAUDE.md: Verhalten von Kursen wird nachgestellt, nicht
aus Dokumenten abgeschrieben): die heutige Zahl der Tipps von „App öffnen“ bis „Lauf läuft“
und von „Lauf fertig“ bis „nächstes Kapitel“ — am Probekurs „Probe: Kurs mit Plan“. Die
Vorschläge unten sind bis dahin Annahmen über die Umwege.

| | Vorschlag | Spart |
|---|---|---|
| D1 | **„Weiter machen“** — eine Karte unter Heute und oben auf der Kursseite: Kursname, Kapitel, der nächste offene Schritt; ein Tipp führt genau dorthin | Kursliste → Kurs → Kapitel → suchen |
| D2 | **Ein Fußknopf im Kapitel, der immer den nächsten Schritt nennt:** „Seitstütz ausprobieren ▶“ → „Frage beantworten“ → „Plan übernehmen“ → „Weiter zu Kapitel 3“. Er scrollt zur Stelle oder startet direkt (Skizze B1 hatte die Fußzeile; am 26.11. nicht gebaut) | suchen, wo es weitergeht |
| D3 | **Der Lauf startet ohne Vorseite**, wenn es vorher nichts zu zeigen und nichts zu fragen gibt: Tipp → Countdown → Lauf | einen Bildschirm, einen Tipp |
| D4 | **Ergebnis und Fragen auf einer Seite**, „Fertig“ führt zurück ins Kapitel — an die Stelle, zur nächsten offenen Karte gescrollt | einen Bildschirm; das Suchen danach |
| D5 | **„Übernehmen und weiter“** in der Sammelkarte, wenn die Bedingung des Kapitels damit erfüllt ist — die Zeilen bleiben abwählbar | einen Tipp, einmal Scrollen |
| D6 | **„Weiter“ führt ins nächste Kapitel**, nicht zur Kursseite; das letzte Kapitel endet mit einer Abschlusskarte | einen Bildschirm je Kapitel |
| D7 | **Schritte oben im Kapitel** — eine schmale Leiste: lesen · machen · antworten · Plan; der aktuelle hervorgehoben | Orientierung |

Bleibt, was gilt: **Nichts ändert sich am Plan ohne Tipp** (D5 ist ein Tipp, kein Automatismus);
Überspringen nur auf Rückfrage; ein freiwilliger Lauf bleibt freiwillig (D2 nennt ihn, verlangt
ihn nicht); gerechnet wird nur aus Einträgen, Wahl und Selbstauskunft.

## 6. Schichten

- `core/titelbild.py` (neu, ohne flet): Wert des Feldes lesen, Ort des automatischen Bildes,
  Eckdaten-Satz einer Zeile („Video · 0:42 · 3,1 MB“) — mit Doctests.
- `core/kursschritt.py` (neu): der nächste offene Schritt eines Kapitels aus Blöcken, Einträgen,
  Antworten und Stand der Sammelkarte (D1, D2, D7) — eine Rechnung für alle drei.
- `data/paketmedien.py`: Titelbild ablegen und nennen; ein gewähltes Titelbild zählt als
  „genannt“ (Aufräumen, P230).
- `ui/components/medienkarte.py`: die Karte; der Spieler aus `components/videospieler.py`.
- Bilder aus Dateien im Browser nur über `components/bildquelle.bildquelle`.

## 7. Stufen

| Stufe | Inhalt | Prüfung |
|---|---|---|
| **K0** | Versuch am Gerät: ein Video spielt in einer scrollenden Liste, hält an, verschwindet | Ben am Pixel 10, eine Probeseite |
| **K1** | Medienkarte im Kapitel, im Lauf und im Ergebnis — Bild direkt, Ton als Leiste, Video mit automatischem Bild oder Titelkarte, „spielt in der Karte“, ⤢ | Tests je Art, Web-Fotos, Gerätetest |
| **K2** | Editor: Zeilen nach §4.1, Karte „Medium“ mit Vorschau und Eckdaten (§4.2) | Tests, Web-Fotos |
| **K3** | Titelbild: Feld, Blatt, Bild aus dem Video (Erweiterung, ffmpeg), Paketformat 10 | Tests, Rundreise Paket, Gerätetest |
| **K4** | Editor: G1 Folgen eingerückt, G2 einfügen an der Stelle, G3 ziehen, G5 Kapitel wechseln, G6 verdoppeln | Tests, Web-Fotos |
| **K5** | Durchspielen: erst nachstellen und zählen, dann D1–D7 nach Bens Wahl | Probe am Probekurs vorher/nachher |
| **K6** | G4 Vorschau, G7 Bausteine an Ort und Stelle; G8 nur auf eigenes Wort | — |

K1 und K2 zusammen sind das, was Ben als Unterschied zwischen Skizze und App gesehen hat.
Keine Migration (das Feld steht im JSON der Medien). Große Stufen im eigenen Worktree.

## 8. Fragen an Ben (Katalog P231) — meine Empfehlung zuerst

a) **Videos spielen im Kapitel selbst** (klein, in der Karte), nicht mehr nur in der eigenen
   Ansicht — für Kurse. Empfehlung: ja; Übung, Plan und Fokus bleiben beim Material-Blatt.
b) **Titelbild überall oder nur im Kurs?** Das Feld gehört zum Medium und gilt damit auch an
   Übung und Plan. Empfehlung: Feld überall, das Blatt zuerst nur im Kurs-Editor; der Reiter
   „Medien“ im Plan zeigt das Bild, sobald es da ist.
c) **Automatisches Bild:** bei eigenen Aufnahmen das Foto vom Start, bei Dateien die Mitte des
   Videos. Recht so — oder lieber immer die Titelkarte, bis man selbst wählt?
d) **YouTube-Vorschaubilder holen?** Empfehlung: nein (neue Netzverbindung zu Google schon
   beim Öffnen). Titelkarte oder eigenes Bild.
e) **Zeilen im Editor: Inhalt fett, Art klein** (§4.1). Recht so?
f) **Welche von G1–G8?** Empfehlung: G1, G2, G5 zuerst; G3 und G6 danach; G4 vor G8.
g) **Welche von D1–D7?** Empfehlung: D2, D4, D6 zuerst (der größte Gewinn im Kapitel), D1 und
   D3 danach; D5 nur, wenn dir ein Knopf für zwei Dinge recht ist.
h) **Reihenfolge:** K0 → K1 → K2, dann Titelbild (K3) — oder das Titelbild vor dem Editor?
