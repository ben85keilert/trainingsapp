# Plan: Taktgeber — Phasen für Atmung und Bewegung in Uhr, Timer und Übung

Stand 5.11.2026: **angenommen**, Teil 1 (T1–T3) gebaut (Version 0.3.50, Abschnitt 9), Teil 2
(T4–T6) gebaut (Version 0.3.51, Abschnitt 10) (Ben: „So bauen“; Aufgabe A18, Ben 4.11.2026: „z. B. 3 min und dann Phasen setzen
können, diese optisch interessant gestalten … Animation/Visualisierung getakteter Übung mit
Geschwindigkeitsregler“; 5.11.2026: „Takt ist in der Uhr/Timer (beides). Dieser sollte doch direkt
(Uhr) oder über die Übung zugänglich sein? Evtl. Wiederholungszähler auch ohne Stoppuhr, aber mit
Phasen, auch mehr als 3. Entwirf ein gutes ausbaufähiges Konzept“; „Erstelle verschiedene
Animationen für 1–4 Phasen“). Verträge, die er berührt: `docs/plan_beschleunigung.md` §7.2/§7.6
(Soll-Phasen für die Atem-HRV), `docs/kompatibilitaet.md` §4 (Marke), §5 (`atmung` getaktet),
§15 (`atem-v1`), `docs/plan_einheit.md` §4/§7, `docs/plan_stoppuhr.md`, `docs/uebungspakete.md`.

## 0. Kurzfassung

Ein **Takt** ist eine Folge von **Phasen** mit Namen, Dauer und Klang — ein bis beliebig viele
(ein · halten · aus · halten; ab · halten · auf; ein Metronomschlag). Er hat ein **Tempo**
(Faktor, mit dem alle Dauern skalieren; der Geschwindigkeitsregler) und läuft als Schleife, solange
die Uhr läuft. Er hängt an drei Orten, die denselben Kern nutzen:

| Ort | Was | Gilt |
|---|---|---|
| **Übung** (`Exercise.takt`) | die Vorgabe der Übung („4-7-8-Atmung“, „Kniebeuge 2-1-2“) | überall, wo die Übung geübt wird; reist im Paket |
| **Timer-Abschnitt** (`Abschnitt.takt`) | ein Takt je Abschnitt eines Timer-Profils („3 min Atmen 4-6“, dann Pause ohne Takt) | in diesem Abschnitt; überschreibt die Vorgabe der Übung |
| **Uhr, für jetzt** (`AppState.uhr_takt`) | der Takt-Knopf neben der Uhr: Vorlage oder eigene Phasen, Tempo mit Regler | diese Sitzung, wie „zählt“ und der Einmal-Timer (P79) |

Die Anzeige ist eine **Animation nach Phasenzahl** (Kreis, Welle, Pendel, Balken) mit Farbe je
Phase, Restsekunden und Klang am Phasenwechsel. **Der Takt zählt** auf Wunsch: Jede volle Runde
ist eine Wiederholung — ein Zähler mit Phasen, auch ohne Sensor und ohne Stoppuhr-Zeit. In der
Messdatei steht der Takt als Protokoll (`atmung` getaktet), als eine Marke (`atemtakt`) und als
Soll-Phasen im Beiwerk `atem-v1`, damit die Auswertung Soll gegen Ist (Sensor) legen kann.

## 1. Begriffe

- **Phase:** Name (frei, Vorschläge „ein“, „halten“, „aus“, „ab“, „auf“), Dauer in Sekunden
  (auch Zehntel), Klang zu Beginn (aus `core.klang.KLAENGE`, leer = Vorgabe), **Art** als
  Kennung für die Auswertung: `ein`, `aus`, `halten`, `ab`, `auf`, `frei`. Die Art sagt, was die
  Phase bedeutet (Atmung oder Bewegung), der Name, was angezeigt wird.
- **Takt:** Liste von Phasen (mindestens eine), Name, Tempo (Faktor, Vorgabe 1,0), optional
  Rundenzahl (sonst endlos bis zum Ende des Abschnitts/der Uhr). Rundendauer = Summe der Dauern
  mal Tempo; „Rate pro Minute“ = 60 / Rundendauer (für Atmung die Atemfrequenz).
- **Vorlagen** (`core.takt.VORLAGEN`, feste Schlüssel): Atmung 4-6 (6/min), Box 4-4-4-4,
  4-7-8, Gleichtakt 5-5 (6/min), Gleichtakt 2,5-2,5 (12/min), Metronom 1 s, Kniebeuge 2-1-2
  (ab · halten · auf), Liegestütz 2-0-1 … Eigene Takte speichert die Person in der Bibliothek
  (`app_setting`, wie die Timer-Bibliothek) oder direkt an Übung/Abschnitt.
- **Taktlauf:** die Lage im Takt zu einem Zeitpunkt — Phase, Anteil in der Phase, Runde. Sie
  wird **aus der Uhr gerechnet**, nie mitgezählt: Zeit seit Beginn des Abschnitts (bzw. der
  Stoppuhr) modulo Rundendauer. Darum driftet nichts, und „Anhalten“ hält den Takt mit an.

## 2. Kern (ohne flet)

`core/takt.py`:

- `Phase(name, dauer_s, art="frei", klang="")`, `Takt(phasen, name="", tempo=1.0,
  runden=None)` mit `als_dict`/`aus_dict` (defensiv wie `TimerProfil`), `rundendauer_s`,
  `rate_pro_min`, `mit_tempo(faktor)`, `VORLAGEN`, `ist_atmung()` (nur Arten ein/aus/halten),
  `ist_bewegung()`.
- `lage(takt, t_s) -> Lage(phase_index, phase, anteil, runde, rest_s, t_runde_s)` — rein.
- `wechsel(alt: Lage, neu: Lage) -> list[Ereignis]` (Phasenwechsel, Rundenende) für Klang,
  Vibration, Zählung und Zeitleiste.
- `soll_phasen(takt, von_s, bis_s) -> list[(t_s, "ein"|"aus")]` für das Beiwerk `atem-v1`
  (nur Takte mit Atem-Arten; „halten“ verlängert die laufende Phase).
- Doctests; keine Bewertung, keine Empfehlung (ein Takt ist eine Vorgabe der Person, keine aus
  Messwerten — das Resonanzprotokoll, das eine Rate *wählt*, bleibt gesperrt wie in
  `docs/plan_beschleunigung.md` §10).

`core/timer.py`: `Abschnitt.takt: Takt | None` (im Dict nur, wenn gesetzt; `_abschnitte_lesen`
und `als_dict` nehmen ihn mit — Rundreisen in Kopie, Paketimport und Editor). `core/models.py`:
`Exercise.takt: Takt | None` (Migration 038 `exercise.takt_json TEXT NOT NULL DEFAULT '{}'`),
Paketfeld `takt` (`docs/uebungspakete.md`, Drei-Wege-Abgleich ein Feld, ältere Apps übergehen
es), `FELDNAMEN["takt"] = "Takt"`. `core/uebung_timer.takt_fuer(uebung, abschnitt, wahl,
item)`: Vorrang Uhr-für-jetzt > Abschnitt > **Planübung** > Übung > keiner — die Planübung
(`PlanItem.takt`, Migration 039 `plan_item.takt_json`, NULL = wie die Übung, `{}` = ausdrücklich
keiner; A6, 5.11.2026) ist die Stufe „Übung“ aus Sicht des Laufs
(`core.uebung_timer.takt_der_uebung(uebung, item)` → `TimerLauf.takt_uebung`).

## 3. Lauf: Klang, Vibration, Zeitleiste

- `ui/timer_takt.py` (der 0,2-s-Ticker) rechnet je Tick die `Lage` aus dem `TimerLauf`
  (`stand.abschnitt_s − stand.rest_s`; bei der Stoppuhr die gelaufene Zeit) und spielt über
  `ton_spielen` den Klang der neuen Phase (Vorgabe: ein → Glocke hell, aus → Glocke tief, halten →
  Klangholz, ab/auf → Piep, frei → Klangschale), dazu eine kurze Vibration; der Abschnittsklang
  bleibt. Die Verzögerung von bis zu 200 ms ist hier schon bekannt (Timer-Signale).
- `devices/einheit.TimerBaustein` schreibt beim Start eines Abschnitts mit Takt ein Ereignis
  `timer/takt` (`name`, `wert` = Rate/min, `soll_s` = Rundendauer, `tempo`, `phasen_s`
  [Dauern], `arten` „ein/aus“ als Text) und bei einer Tempoänderung noch eins; Rundenenden
  nicht (zu viele). `core/einheit.ARTEN` += `takt`, `DATEN_SCHLUESSEL` += `tempo`, `phasen_s`,
  `arten`. Vertrag `docs/plan_einheit.md` §4 zuerst.
- Läuft eine Aufnahme, bekommt sie **eine Marke** `quelle=timer, art=takt, spur=atemtakt`
  (Felder, die `hrv_core.ereignisse.MARKE_FELDER` schon kennt: `name`, `wert`, `soll_s`,
  `profil`) am Beginn und am Ende des Takts — nie eine je Phase (`MIN_MARKE_S` = 5 s). Vertrag
  `docs/kompatibilitaet.md` §4 zuerst (neuer `art`-Wert `takt`, neue `spur` `atemtakt`).
- Das Protokollfeld `atmung` wird `getaktet` mit `takt_pro_min`, wenn ein Atemtakt lief
  (`core.atem_protokoll`: Takt-Ereignisse vor der Übungsregel). Mit Bewegungstakt bleibt es
  wie bisher.
- Die **Soll-Phasen** gehen ins Beiwerk `atem-v1` als neues, optionales Feld
  `takt: {"name", "rate_pro_min", "phasen": [[t_s, "ein"|"aus"], …]}` (Vertrag §15 und
  hrv-core `atem.py`/`deid` zuerst; ältere Leser übergehen es). So legt die Auswertung Soll
  gegen Ist (Sensor) und die Atem-HRV rechnet die Phasenlage gegen beides
  (`docs/plan_beschleunigung.md` §7.2, Entscheidung 25 Frage 7).

## 4. Der Takt zählt (Wiederholungszähler mit Phasen)

- Hat der Takt Bewegungs-Arten (ab/auf) oder ist „Takt zählt“ an, ist jede volle Runde eine
  Wiederholung. Das läuft als **Zähl-Teil mit Quelle `takt`** über denselben Weg wie der
  Sensor (`devices/zaehlen.ZaehlBaustein`, Zeitleiste `zaehlung` mit `quelle`-Feld `takt`,
  Satz je zählendem Abschnitt, ±1, Eintrag in den offenen Eintrag beim Ende) — die Zählzeile
  zeigt „Takt 12“ statt „Sensor 12“. Ohne Sensor ist das der Handzähler, den P118 verwarf, **nur
  mit Takt**: Die Zahl kommt aus der Vorgabe, nicht aus einer Messung, und die Zählzeile sagt
  das („Takt · 12“, kein „Prototyp“).
- Mit Sensor **und** Takt zählt der Sensor; der Takt steht daneben („Takt 12 · Sensor 11“) —
  beide in der Zeitleiste, nur der Sensor im Eintrag (entweder Person/Takt oder Sensor, P122
  sinngemäß). Im Diagnosemodus ist der Takt eine dritte Spalte im Vergleich nach dem Satz.
- Ohne Stoppuhr: „Takt starten“ an der Übung startet einen Einmal-Timer ohne Ablauf mit diesem
  Takt (es gibt also immer eine Uhr; sie zählt nur, wenn „zählt“ an ist).

## 5. Anzeige und Bedienung

**Takt-Knopf an der Uhr** (Zeile und Knöpfe, `components/uhr.py`): ein Metronom-Symbol neben
„zählt“; der Tipp öffnet das **Takt-Blatt** (`components/takt_blatt.py`, `blatt_spalte`):
Vorlagen als Chips, darunter die Phasen des gewählten Takts als Zeilen (Name, Sekunden, Art,
Klang), „+ Phase“, „Phase entfernen“, der **Tempo-Regler** (0,5×–2× als **Geschwindigkeit**:
rechts schneller, 2× = halbe Dauern — gespeichert bleibt der Faktor auf die Dauern,
`core.takt.geschwindigkeit`/`faktor_von`; Ben, 7.11.2026: „kleineres Tempo … langsamerer
Ablauf“; mit Rate/min und Rundendauer als Text; eine **Bildfolge** — der Hinweg als Streifen quadratischer Bilder — läuft seit dem 7.11.2026 im Fokus je Takt-Lage vor und zurück, `core.bewegungsbild.bild_fuer_lage`, `docs/plan_planblock.md` §B), Vorschau (die Animation läuft im Blatt), „Für jetzt“ / „In die Übung“ /
„In die Bibliothek“. Während die Uhr läuft, wirkt der Tempo-Regler sofort (die Lage springt
nicht: die gelaufene Rundenzeit bleibt, die Phase wird neu skaliert).

**Animation** (`components/takt_anzeige.py`), gewählt nach Phasenzahl, umschaltbar:

| Phasen | Vorgabe | Bewegung |
|---|---|---|
| 1 | **Puls**: ein Ring füllt sich über die Phase und blitzt am Schlag (Metronom) | – |
| 2 | **Kreis**: wächst beim Einatmen, schrumpft beim Ausatmen (ab/auf: sinkt und steigt ein Pendel) | `animate_scale` je Phase, kein Neubau |
| 3 | **Kreis mit Halten**: wächst, bleibt (leuchtender Rand, Restsekunden), schrumpft | – |
| 4 | **Box**: Kreis wächst, hält, schrumpft, hält; die vier Phasen als Rahmenseiten mit Lauflicht | – |
| ≥ 5 | **Balken**: die Phasen als Segmente nebeneinander, der laufende Abschnitt füllt sich | – |
| alle | **Welle**: eine Sinuslinie, der Punkt wandert; **Balken** als Alternative | wählbar |

Farbe je Art (ein = kühl, aus = warm, halten = neutral, ab/auf = Übungsfarbe), Name der Phase
und Restsekunden in der Mitte, Runde und Rate darunter. Die Flutter-Animation läuft nativ über
die ganze Phase (`animate_scale`/`animate` mit der Phasendauer, `EASE_IN_OUT`); der Ticker setzt
nur am Phasenwechsel neue Zielwerte und die Texte — keine Knöpfe werden neu gebaut (V1-Regel).
Die Anzeige steht im Timer („Während“), in der laufenden Uhr (klein, antippen → groß) und im
Live-Vollbild der Messung (neben Phase ▲/▼ des Sensors: Soll und Ist).

**Takt · Zeit in einer Zeile** (Ben, 9.11.2026: „nebeneinander, den Takt etwas kleiner als die
Uhrzeit, vereinheitlicht mit den anderen Timern“): Timer-Seite, Fokus (Übung und Workout) und
laufende Uhr in der Übung nehmen dieselbe Zeile `components/takt_anzeige.ZeitMitTakt` — links
der Takt, seine Fläche so groß wie die Schrift der Zeit (`NEBEN_DER_ZEIT` = 1,0; Timer-Seite 84,
Fokus 64, Uhr in der Übung 40), rechts die Zeit; unter 56 px die kompakte Form (Text neben dem
Kreis). Auf der Timer-Seite stehen beide zusammen in der Mitte, im Fokus die Zeit mittig vor
Material und Ebenen, in der Übung links. Ein Tipp auf den Takt zeigt ihn überall groß
(`takt_gross`); eine Zeit mit Stunden wird neben dem Takt um ein Viertel kleiner.

**Übung bearbeiten:** in „Uhr und Timer“ die Zeile „Takt: 4-7-8-Atmung · 4/min“ mit Stift
(öffnet das Takt-Blatt) und ✕; im Timer-Editor je Abschnitt dieselbe Zeile. Das (i) erklärt
Takt, Tempo und „Takt zählt“. **Im Plan einstellen** (A6, 5.11.2026): dieselbe Zeile in „Uhr
und Timer“ mit dem Schild „wie die Übung“ / „nur hier“ ↺ — der Stift öffnet das Blatt mit dem
Knopf „In diesen Plan“, ✕ heißt in diesem Plan ausdrücklich kein Takt (auch wenn die Übung
einen hat), ↺ holt die Übung zurück; „In die Übung übernehmen …“ nimmt den Takt mit. Beim
Üben aus dem Plan (Uhr, Timer der Übung) gilt der Takt der Planübung, die Wahl für jetzt bleibt
obenauf. Im Plan-Ablauf gibt es wie beim Sensor noch keinen Takt (A19).

**GIFs und Bilder der Bewegung** (Ben: „gehen auf die Übung, nicht den Timer“): ein Medium der
Art `bild`/`gif` an der Übung (`core/models.Media`, Ablage wie die eigenen Symbole unter
`Medien/`), gezeigt neben der Takt-Anzeige im „Während“; es läuft als Schleife, nicht
synchron zum Takt (ein GIF hat sein eigenes Tempo). Später: eine Bildfolge je Phase (ein Bild
je Phase der Bewegung), die der Takt schaltet — das ist dann synchron.

## 6. Recht

Ein Takt ist eine Vorgabe, die die Person wählt; die App bewertet nichts und empfiehlt keine
Rate aus Messwerten (`docs/recht/00_zweckbestimmung.md`; das Resonanzprotokoll bleibt wie in
`docs/plan_beschleunigung.md` §10). Vorlagen sind feste Zahlen ohne Wirkversprechen.

## 7. Stufen

| Stufe | Inhalt | Umfang |
|---|---|---|
| **T1** | Kern `core/takt.py`, `Abschnitt.takt`, `Exercise.takt` (Migration 038, Paketfeld), Vorlagen, Bibliothek; Takt-Blatt und Zeilen in „Übung bearbeiten“ und im Timer-Editor; Vertrag `docs/uebungspakete.md` | M |
| **T2** | Lauf: Lage aus der Uhr, Klang und Vibration je Phase, Takt-Knopf an der Uhr „für jetzt“, Tempo-Regler live, „Takt starten“ ohne Timer; Zeitleiste `timer/takt` (Vertrag `plan_einheit` §4) | M |
| **T3** | Animationen 1–4+ Phasen (Puls, Kreis, Kreis mit Halten, Box, Balken, Welle), Übungsfarbe, in Timer, Uhr und Live-Vollbild | M |
| **T4** | Messung: Marke `atemtakt` (Vertrag §4), `atmung` getaktet, Soll-Phasen in `atem-v1` (Vertrag §15, hrv-core), Auswertung Soll gegen Ist, Phasenlage gegen Soll/Ist (Entscheidung 25 Frage 7) | M |
| **T5** | „Takt zählt“: Zähl-Teil mit Quelle `takt`, Zählzeile „Takt 12“, neben dem Sensor, Diagnose-Vergleich | M |
| **T6** | GIF/Bild der Bewegung an der Übung, Bildfolge je Phase | S |

## 8. Entschieden (Ben, 5.11.2026)

Konzept angenommen („So bauen“: T1–T6 hintereinander, dann Prüfrunde).

| # | Frage | Entscheidung |
|---|---|---|
| P138 | „Takt zählt“ trägt Wiederholungen ohne Sensor ins Tagebuch ein (jede Runde eine) — gewollt, obwohl die Zahl eine Vorgabe ist, keine Messung? | **ja**, gekennzeichnet „Takt“; mit Sensor zählt der Sensor |
| P139 | Tempo-Regler während des Laufs: sofort wirksam und nur „für jetzt“ (nicht gespeichert), oder speichert er in Übung/Abschnitt? | **für jetzt**; speichern nur über das Blatt |
| P140 | Vibration am Phasenwechsel zusätzlich zum Klang? | offen (nicht gefragt) — Vorschlag: ja, kurz, abschaltbar |
| P141 | Soll-Phasen ins Beiwerk `atem-v1` (Feld `takt`, Format-Erweiterung) oder nur die Marke `atemtakt` in der Messdatei? | **ins Beiwerk** (Format-Erweiterung `atem-v1`, Vertrag §15 zuerst) |

## 9. Umsetzungsstand (5.11.2026, Version 0.3.50) — Teil 1: T1–T3

hrv-core bleibt 0.13.0 (`hrv-core.ref` unverändert); Teil 1 braucht nichts aus der Bibliothek.
Die Vibration am Phasenwechsel ist **so gebaut, Vorgabe an** (P140 offen, Schalter unter
Einstellungen → Übungen).

| Stufe | Gebaut | Wo |
|---|---|---|
| T1 Kern | `core/takt.py` (flet-frei, Doctests): `Phase(name, dauer_s, art, klang)`, `ART_*`, `Takt(phasen, name, tempo, runden, animation, zaehlt)` — unveränderlich wie `SensorWahl`, `als_dict`/`aus_dict` defensiv (unbrauchbare Phasen fallen weg, Unbekanntes wird Vorgabe, nie eine Ausnahme), `rundendauer_s`, `rate_pro_min`, `mit_tempo` (Faktor 0,5–2, `tempo_lesen` begrenzt), `ist_atmung`, `ist_bewegung`, `kurztext` („4-7-8 · 3,2/min“); `AUS` = der leere Takt („für jetzt keiner“); `VORLAGEN` (acht feste Schlüssel; Liegestütz 2-0-1 als `liegestuetz_2_1`, eine Phase von 0 s gibt es nicht); `animation_fuer` (Puls 1, Kreis 2, Kreis mit Halten 3, Box 4, Balken ≥ 5; `Takt.animation` überschreibt, etwa Welle); `lage(takt, t_s)` rein aus der Uhr (mit `fertig` bei erreichter Rundenzahl), `wechsel(alt, neu)` → `TaktEreignis` (`phase`, `runde`, `ende`), `soll_phasen` (nur Atemtakte, „halten“ verlängert), `TaktLauf` (Tempoänderung ohne Sprung: gelaufene Runden samt Anteil bleiben), `takt_pruefen` fürs Werkzeug, Bibliothek `takte_lesen`/`takte_schreiben`/`in_bibliothek`, `takt_waehlen` (für jetzt > Abschnitt > Übung) | `core/takt.py` |
| T1 Modell | `Abschnitt.takt` (im Dict nur gesetzt; `_abschnitte_lesen` tolerant — Rundreise in Kopie, Paket und Editor), `Exercise.takt` (Migration 038 `exercise.takt_json TEXT NOT NULL DEFAULT '{}'`, `ExerciseRepo`), Paketfeld `takt` (`_uebung_lesen` tolerant, `stand()` nur gesetzt, `FELDNAMEN["takt"] = "Takt"` nach `beschleunigung`; `trainingsapp-paket pruefen` meldet falsche Typen als Fehler, unbekannte Art/Klang/Schlüssel als Hinweis), `core.uebung_timer.takt_fuer(uebung, abschnitt, wahl)`, Bibliothek eigener Takte in `app_setting` (`takt_bibliothek`), Schalter `takt_vibration` | `core/timer.py`, `core/models.py`, `data/migrations/038_takt.sql`, `data/repositories.py`, `core/pakete.py`, `paket_werkzeug.py`, `core/uebung_timer.py`, `ui/state.py` |
| T1 Blatt und Zeilen | `components/takt_blatt.py` (`blatt_spalte`): Vorlagen und eigene Takte als Chips, Name, Phasen-Zeilen (Name, Sekunden mit Zehnteln, Art, Klang mit der Vorgabe je Art im Menü, ✕), „+ Phase“ (Art wechselt ein ↔ aus, ab ↔ auf), Animation wählbar, Tempo-Regler 0,5×–2× mit Rate, Rundendauer und Phasenzahl, die **Vorschau** läuft im Blatt (eigene Aufgabe, endet mit dem Blatt), Knöpfe nach Herkunft: „Takt starten“, „Für jetzt“, „In den Abschnitt“, „In die Übung „…““, „In die Bibliothek“ (braucht einen Namen; gleicher Name ersetzt), „Kein Takt“, „Wie eingestellt“ (nimmt die Wahl für jetzt zurück). „Übung bearbeiten“ → Uhr und Timer: die Zeile „Takt: 4-7-8 · 4-7-8 · 3,2/min“ mit Stift, ✕ und (i) (`hilfe.THEMEN["takt"]`), im Formular gehalten, Zurück speichert; Timer-Editor: dieselbe Zeile je Abschnitt (`_Zeile.takt`); die Übungsseite nennt den Takt unter „Uhr und Timer“ | `components/takt_blatt.py`, `components/hilfe.py`, `views/uebung_bearbeiten.py`, `views/timer.py`, `views/uebung_detail.py` |
| T2 Lauf | `TimerLauf.takt_jetzt`/`takt_uebung`/`tempo_faktor`, `takt_aktuell(nummer)`, `takt_lage()` (Zeit im Abschnitt = `abschnitt_s − rest_s`, Stoppuhr: gelaufene Zeit; angehalten steht sie; je Abschnitt ein `TaktLauf`), `tempo_setzen` (P139, für jetzt; `tempo_aenderungen` für die Zeitleiste). Der Ticker (`ui/timer_takt.py`) rechnet je Tick die Lage, `wechsel` → `takt_melden`: Klang der neuen Phase (eigener, sonst Vorgabe je Art: ein Glocke 1, aus Glocke 3, halten Klangholz, ab/auf Piep, frei Klangschale) über `ton_spielen` mit Regler und Lautstärke der Signale, Vibration kurz (Schalter, Vorgabe an); nicht über ein Timer-Signal desselben Takts (der Abschnittsklang bleibt), nach „Weiter“ tönt die laufende Phase nicht erneut (`_lage_beim_start`). `TimerBaustein._takt_melden`: `timer/takt` am Abschnittsbeginn mit Takt (zur Zeit der Marke) und je Tempoänderung (`core.einheit.ARTEN` += `takt`, `DATEN_SCHLUESSEL` += `tempo`, `phasen_s`, `arten`; Vertrag `docs/plan_einheit.md` §4). Takt-Knopf an der Uhr (`takt_knopf`, Zeile und Knöpfe neben „zählt“; im Timer der Übung über den Chips; im Reiter „Timer“ in der Steuerung, Schlüssel `timer`): „Für jetzt“ → `AppState.uhr_takt[key]` (`AUS` = keiner), „Takt starten“ startet die gesetzte Uhr (ohne Timer die Stoppuhr; im Timer der Übung ein Timer ohne Ablauf) mit diesem Takt; `takt_anbringen` hängt Wahl, Vorgabe der Übung und `uhr_tempo` beim Start und Bereitstellen an den Lauf; der **Tempo-Regler live** (`TempoRegler`) steht in der laufenden Uhr, im Timer der Übung und im Reiter „Timer“, solange ein Takt läuft — sofort wirksam, nur für jetzt | `core/timer.py`, `ui/timer_takt.py`, `devices/einheit.py`, `core/einheit.py`, `components/takt_blatt.py`, `components/uhr.py`, `views/uebung_timer.py`, `views/timer.py` |
| T3 Animation | `components/takt_anzeige.TaktAnzeige(groesse, klein, on_click)`: Puls (Ring füllt sich, die Mitte blitzt am Schlag), Kreis (`animate_scale` mit der Phasendauer, `EASE_IN_OUT`: ein/auf groß, aus/ab klein, halten bleibt mit leuchtendem Rand, frei wechselt), Box (dazu vier Rahmenseiten mit Lauflicht), Balken (Segmente nach Dauer, der laufende füllt sich), Welle (32 Stützstellen einer Sinuslinie, der Punkt wandert); Farbe je Art (ein kühl, aus warm, halten neutral, ab/auf Primärfarbe), Name und Restsekunden in der Mitte, Runde, Rate und Tempo darunter. **Einmal gebaut**, `nachziehen(takt, lage)` setzt je Tick nur Werte, baut nur beim Wechsel von Takt oder Animation neu (V1). Steht im Reiter „Timer“, im Fokus und in der laufenden Uhr **neben der Zeit** (seit 9.11.2026 `ZeitMitTakt`, §5; antippen → groß, `takt_gross`, ein Dialog am Ticker) und im Live-Vollbild als Kopfzeile „Soll ▲ ein 3 s“ neben der Atmung des Sensors (`takt_kopf_text`) | `components/takt_anzeige.py`, `views/timer.py`, `views/uebung_timer.py`, `components/uhr.py`, `views/live_vollbild.py` |

Tests: `tests/test_takt.py` (flet-frei, in `test_import_regel` geführt: Vorlagen, Lage, Wechsel,
Tempo ohne Sprung, Soll-Phasen, Rundreise, Prüfung, Vorrang, Paket, Werkzeug, Lage aus der
Uhr, Zeitleiste, `takt_melden`, Ticker), `tests/test_ui_takt.py` (Blatt, Bibliothek, Formular,
Timer-Editor, Anzeige ohne Neubau je Tick, Takt-Knopf, laufende Uhr, Reiter „Timer“,
Einstellung, Vollbild), `tests/test_repositories.py` (Rundreise, Migration 038), Doctests.

**Beim Bauen entschieden:** (1) Der Tempo-Regler im Lauf ist ein eigener Faktor am
`TimerLauf` (`tempo_faktor`, Takt-Tempo × Regler, begrenzt auf 0,5–2) — der gespeicherte Takt
behält sein Tempo; im Blatt stellt der Regler das Tempo des Takts, das mitgespeichert wird.
(2) „Kein Takt“ für jetzt ist `takt.AUS` in `uhr_takt` (schaltet auch Abschnitt und Übung ab);
„Wie eingestellt“ nimmt die Wahl zurück — ohne diesen dritten Zustand käme man nicht zur
Vorgabe zurück. (3) `timer/takt` schreibt die Dauern **mit Tempo** (`phasen_s`, `soll_s`), dazu
`tempo` — so ist das Ereignis für sich lesbar. (4) Die Animation ist am Takt gespeichert
(`Takt.animation`, auch im Paket); leer heißt nach Phasenzahl. (5) `Takt.zaehlt` ist im Format
schon da (Paketfeld, Dict), aber ohne Wirkung und ohne Schalter — T5 nimmt es. (6) Die Stoppuhr
mit Takt rechnet ab ihrem Start; ein Abschnitt ohne Takt (Pause) beendet den Takt (`ende`), die
nächste Runde beginnt ihn von vorn. (7) Material kennt kein Metronom-Symbol — `GRAPHIC_EQ`
steht für den Takt.

**Offen aus Teil 1:** P140 (Vibration am Phasenwechsel — gebaut mit Schalter, Vorgabe an;
nicht entschieden); die Zeile in „Im Plan einstellen“ (ein Takt je Planübung) kam mit A6 in
0.3.53 (Abschnitt 11); das Querformat/Live-Vollbild zeigt den Takt nur als Kopfzeile, nicht als
Animation (Platz). Teil 2 steht in Abschnitt 10.

## 10. Umsetzungsstand (5.11.2026, Version 0.3.51) — Teil 2: T4–T6

hrv-core bleibt 0.13.0 (`hrv-core.ref` unverändert): das Feld `takt` im Beiwerk `atem-v1`,
die Journalzeilen `t`/`q`/`u` und `Atem.takt` sind dort seit 0.13.0 — Teil 2 nimmt sie.
Verträge zuerst: `docs/kompatibilitaet.md` §4 (Marke, `art` `takt`, `spur` `atemtakt`, keine
5-s-Regel), §5 (`getaktet`, Takt vor Übungsregel), §15 (Feld `takt`); `docs/plan_einheit.md` §4
(`zaehlung` mit `quelle`, `takt`, `takt_zeiten_s`; der Takt geht nicht über die Zeitleiste).

| Stufe | Gebaut | Wo |
|---|---|---|
| T4 Lauf | `devices/takt_lauf.py` (flet-frei, Doctests): `TaktVerfolger(lauf)` rechnet je Tick der Einheit aus `TimerLauf.takt_lage` (nie mitgezählt), was seit dem letzten Tick geschah — `TaktNeu`: **Takt-Lauf** begann/endete (je Abschnitt mit Takt und je Tempoänderung ein Lauf, wie `timer/takt`; der Beginn rückgerechnet auf den Abschnittsanfang, eine Tempoänderung meldet die laufende Phase nicht noch einmal), **Soll-Phasen** `(Uhr, ein/aus)` eines Atemtakts (Zeit = jetzt − verstrichene Phasenzeit, auf Zehntel genau trotz 0,25-s-Tick; „halten“ verlängert; Bewegungstakte liefern keine), **volle Runden** `(Uhr, Runde, zaehlt)`; angehalten geschieht nichts, die Rundenzahl erreicht endet der Lauf. `TimerBaustein` führt ihn (`takt_abholen`), `Einheitslauf._takt_verteilen` bringt ihn je Takt an die HRV (`in_die_messung`) und an den Zähl-Teil (`takt_runden`) — **nicht über die Zeitleiste** (Phasen und Runden wären zu viele). Ein Timer **ohne** Einheit (nur, wenn eine andere Einheit bereitsteht) füttert die Messung aus dem Ticker (`ui/timer_takt._takt_in_messung`, wie seine Abschnittsnotizen, mit dem Schalter „Notizen“) | `devices/takt_lauf.py`, `devices/einheit.py`, `ui/timer_takt.py` |
| T4 Messung | `Messlauf.atem_takt_beginn(t, name=, rate_pro_min=, soll_s=, profil=)` / `atem_takt_phase(t, art)` / `atem_takt_ende(t)` (Quelluhr → Wanduhr wie `atem_phase`): Takt-Lauf und Soll-Phasen in den `AtemSammler` (angelegt mit `quelle = takt` und leerem `prototyp`, wenn nur der Takt schreibt; meldet sich der Sensor, wird er zum Sensor-Sammler), dazu das **Paar Notizen** `timer/takt` („Takt Atmung 4-6: Start“, `name`, `wert` = Rate, `soll_s`, `profil`) und `timer/ende` auf der Spur `atemtakt` — sofort, keine Abschnittsgrenze (die Läufe stehen im Beiwerk), nie ohne Beginn-Notiz ein Ende. `takt_laufend` merkt den Takt auch ohne Aufnahme: eine Aufnahme, die mitten im Takt beginnt (zweite Aufnahme, Teil 2 nach dem Teilen), bekommt Lauf und Beginn-Notiz bei 0; Stopp und Teilen schließen den offenen Lauf. Nur Atemtakte (`in_die_messung` prüft `Takt.ist_atmung`). **Protokollfeld** `getaktet` mit `takt_pro_min` = Rate des längsten Takt-Laufs aus den Marken (`core.atem_protokoll.takt_laeufe`/`takt_rate`, vor der Übungsregel; ein offener Lauf reicht bis `ende_s`) | `devices/messlauf.py`, `core/atem_protokoll.py` |
| T4 Auswertung | Ebene „Atmung“: die Soll-„ein“ als feine Linien, Soll-„aus“ gestrichelt, über dem Ist-Schatten, die Takt-Läufe als zweites Band; Karte „Atmung“: Zeile „Takt: Atmung 4-6 · 6,0/min · 1:30 · Soll–Ist Versatz Median +0,4 s (IQR …, 9 Atemzüge)“ (`core.atem_auswertung.soll_ist_versatz`: je Ist-„ein“ innerhalb eines Takt-Laufs das nächste Soll-„ein“, Vorzeichen Ist − Soll; ohne Sensor „kein Sensor, nur Soll“), die Phasenlage **gegen Ist und Soll** („HF-Gipfel 4,0 s nach Einatembeginn (Ist) · 3,6 s (Soll)“, `soll_atem` macht aus dem Takt ein zweites `Atem` für `atem_hrv_zuege`; ohne Sensor die Atem-HRV nur gegen Soll), Quelle „nur Takt (Soll) — kein Sensor“; **Regel F6**: `getaktet` → Modus Atemübung (war schon so), die Takt-Rate als **dritte Quelle** (`hinweis_rate(…, takt_rate=)`, `takt_rate`/`takt_rate_in` je Bereich; Text „(Takt)“ in der Licht-Zeile) — nur, wenn Sensor und RR-Atmung nichts hergeben: ein Soll ist keine Messung | `core/atem_auswertung.py`, `views/messung_detail.py` |
| T5 Takt zählt | `ZaehlBaustein(messlauf, kontext, quelle="takt" \| "sensor", takt_zaehlt=)`: Quelle `takt` ohne Strom, ohne „keine Bewegung“, ohne Prototyp — auch **ohne Gerät** (`messlauf=None`, Stand-in `_OhneGeraet`, die Uhr folgt der Einheit); `takt_runden` nimmt die vollen Runden der Einheit (nur Takte mit `zaehlt`, nur im laufenden Satz, nicht angehalten), `ZaehlSatz.takt`/`takt_zeiten_s`, `wert` = Takt + Korrektur, ±1 wie beim Sensor, Satz je zählendem Abschnitt, Ende mit der Uhr; `zaehlung` mit `quelle`, `takt`, `takt_zeiten_s` (bei `takt` ohne `sensor`, `prototyp`, `vorlage`), `core.zaehlen_eintrag` trägt den Wert wie beim Sensor ein („Satz 1 · 12 Wdh. (Takt)“). **Mit Sensor** (`takt_zaehlt=True` am Sensor-Teil) zählt der Sensor, der Takt steht daneben („Sensor 11 · Takt 12 · Prototyp“, Status „Kniebeuge · 11 · Takt 12“), beide in der Zeitleiste, nur der Sensor im Eintrag; `sensor_dazu()` wechselt einen Takt-Zähler mitten im Lauf auf den Sensor — über „Wdh. zählen“ (`uebung_lauf.zaehlen_starten`) oder den Knopf „Sensor dazu“ in der Zählzeile (nur mit Gerät, das zählen kann). Diagnose: `zaehlsatz_vergleichen(…, takt=)`, `satz_text` „Marken 12 · Sensor 11 · Takt 12 · eingetragen 11“, Kontextzeile `zaehler` mit `phase` takt. **Oberfläche:** Schalter „Takt zählt Wiederholungen“ im Takt-Blatt (`Takt.zaehlt`; die Bewegungs-Vorlagen Kniebeuge und Liegestütz bringen ihn an, Atemtakte aus — einschaltbar, Atemzüge in ein Wiederholungsfeld), `uebung_lauf.takt_zaehlen_anbringen` tritt nach `takt_anbringen` an: läuft die Uhr der Übung mit einem zählenden Takt (`core.takt.zaehlender_takt`: Wahl für jetzt, Abschnitte, Übung) und hat sie ein Wiederholungsfeld, tritt ein Zähl-Teil mit Quelle `takt` bei (oder steht bereit); die Zählzeile sagt „Takt 12“, Kopf „Takt zählt · Vorgabe“ (nie „Prototyp“), in der Marken-Leiste „Takt 12“ | `devices/zaehlen.py`, `core/zaehlen.py`, `core/zaehlen_eintrag.py`, `core/einheit.py`, `core/diagnose.py`, `devices/messlauf.py`, `components/takt_blatt.py`, `components/zaehl_stand.py`, `components/zaehlen.py`, `ui/uebung_lauf.py`, `components/uhr.py`, `views/uebung_timer.py` |
| T6 Bild | Das **Bild der Bewegung** ist ein Medium der Übung (`core/bewegungsbild.py`: `kind` image, `source` local, `uri` `Bewegung/bewegung_<id>.jpg|png|gif`, `title` „Bewegung“ — `bewegungsbild`, `mit_bewegungsbild`), Ablage `Medien/Bewegung/` (`data.uebungsbilder.BewegungsbildRepo`, GIF bleibt GIF; `setzen` schreibt die `exercise_media`-Zeile), Wege `Ziel.fuer_bewegung` → `bewegung/<id>` in Kamera und Fotoauswahl (Fotoauswahl verkleinert zu JPEG — ein GIF kommt nur am Rechner oder von Hand in den Ordner), Blatt „Bild der Bewegung“ (`components/bewegungsbild.py`: Ablage, Hochladen, Aufnehmen, Kein Bild) in „Übung bearbeiten“ unter dem Takt, gezeigt neben der Takt-Anzeige im „Während“ als `ft.Image` mit `gapless_playback` (Flutter spielt ein GIF als Schleife, nicht synchron zum Takt). Nie in Paket, Export, Sync (`core.pakete` lässt `local` weg); die Übungsseite zeigt es nicht als Link. `Phase.bild` ist vorbereitet (Dict-Rundreise, keine Oberfläche) | `core/bewegungsbild.py`, `data/uebungsbilder.py`, `core/anhaenge.py`, `components/bewegungsbild.py`, `views/uebung_bearbeiten.py`, `views/uebung_timer.py`, `views/anhang_hochladen.py`, `views/anhang_aufnahme.py` |

Tests: `tests/test_takt_messung.py` (flet-frei: Verfolger, Beiwerk mit `takt`, Journal, Marken,
`getaktet`, Takt zählt ohne und mit Sensor, Eintrag, `sensor_dazu`, Vergleich, ohne Gerät,
Ticker ohne Einheit), `tests/test_bewegungsbild.py` (Kern, Ablage mit GIF, Medium, Paket, Ziel),
`tests/test_ui_takt2.py` (Schalter im Blatt, Zählzeile, Zähl-Teil mit der Uhr und Eintrag,
Auswertung Soll gegen Ist mit und ohne Sensor, Bild der Bewegung im Formular, Blatt und
„Während“), dazu Erweiterungen in `test_atem_auswertung.py`-Doctests.

**Beim Bauen entschieden:** (1) Die Marke des Atemtakts ist ein **Paar Notizen ohne
Abschnittsgrenze** (`art` `takt` / `ende`, `spur` `atemtakt`, keine 5-s-Regel): Die Läufe
stehen vollständig im Beiwerk; eine weitere Spur mit Abschnitten füllte die Abschnittsliste der
Auswertung mit jedem Tempowechsel. (2) Der Takt geht **nicht über die Zeitleiste** zur HRV und
zum Zähl-Teil, sondern Tick für Tick aus dem Timer-Teil — `plan_einheit` §4 bleibt bei
`timer/takt` am Abschnittsbeginn und je Tempoänderung. (3) **Atemtakte dürfen zählen**
(Schalter), Vorgabe aus: Wer „10 Atemzüge Box“ als Wiederholungen führt, bekommt sie —
gekennzeichnet „Takt“; Bewegungs-Vorlagen zählen von Haus aus. (4) Ohne Sensor gibt es keinen
Knopf „Wdh. zählen“ (§4.1 bleibt): Der Takt-Zähler tritt **von selbst** mit der Uhr an, sobald
ein zählender Takt gilt — die Uhr ist der Knopf. (5) Ohne Gerät steht `_OhneGeraet` für den
Messlauf: der Zähl-Teil braucht keine Quelle, nur eine Uhr. (6) Die Takt-Rate ist für F6 die
**dritte** Quelle, nie die erste: ein Soll ist keine Messung. (7) Das GIF kommt über die
Fotoauswahl **nicht** animiert an (`flet_hochladen` verkleinert zu JPEG — Dart-Änderung,
eigener Schritt); die Ablage und `ft.Image` spielen es, wenn es da ist.

**Nicht gebaut:** die Bildfolge je Phase (nur `Phase.bild`); eine GIF-Durchreiche in
`flet_hochladen`; der Takt-Zähler im Plan-Ablauf (dort zählt auch der Sensor noch nicht, §13);
Soll-Phasen im Live-Vollbild als Linien (nur die Kopfzeile aus Teil 1); ein Timer ohne Einheit
bekommt den Takt nur mit dem Schalter „Notizen“ in die Messung, und eine Aufnahme, die nach dem
Start einer Einheit ohne HRV-Teil beginnt, bekommt weder Abschnittsnotizen noch Takt (wie bisher
bei den Abschnitten).

**Prüfrunde 1 (0.3.52)** — 14 Befunde der Prüfung von Teil 1+2, alle behoben, je einer mit
Test, der vorher rot war (`tests/test_takt_messung.py`, `test_takt.py`, `test_ui_takt.py`,
`test_ui_takt2.py`, Abschnitt „Prüfrunde 1“): (1) „Sensor dazu“ nach ≥ 15 s Takt-Zählen brach
sofort ab — `KEINE_DATEN_S` zählt jetzt ab der Anforderung des Stroms (`ZaehlBaustein.
_strom_seit`), nicht ab dem Start. (2, 12) `TimerLauf.zuruecksetzen` vergisst den `TaktLauf`
samt Tempoanker und leert `tempo_aenderungen` — ein zweites ▶ desselben Laufs beginnt in Runde 1,
der Faktor bleibt (P139). (3) Der Tempo-Regler setzt das Tempo erst beim Loslassen
(`on_change_end`), beim Ziehen zieht nur der Text nach — ein `timer/takt`, ein Takt-Lauf, ein
Notizpaar je Änderung. (4) Ein neuer Takt-Lauf beginnt mit seinem Abschnitt, wenn der seit dem
letzten Tick begann (`TimerLauf.abschnitt_uhr`), sonst jetzt; der alte endet am selben Punkt —
nie überlappend, kein Beginn vor einem Ende; der Verfolger des Timers ohne Einheit lebt am
Zustand (`AppState.takt_verfolger`) und überlebt Anhalten/Weiter. (5) Der Zwischenstand gegen
den Absturz vergleicht auch den Takt-Stand (`ZaehlSatz.geschrieben` mit `takt`). (6) Die
senkrechten Seiten der Box liegen rechts und links (um die Mitte gedreht, `TaktAnzeige.rahmen`),
Lauflicht im Uhrzeigersinn. (7) Zählte der Takt **ohne Gerät** und kommt der Gurt später, reicht
„Sensor dazu“/„Wdh. zählen“ den Messlauf nach (`ZaehlBaustein.sensor_dazu(messlauf)`: Profil,
Rate, Vorlage, Diagnose-Haken, neuer Uhren-Anker) — der Sensor misst wirklich, statt den Knopf
zu verstecken: der Teil braucht vom Messlauf nur Puffer und Uhr, beides lässt sich nachreichen.
(8) `atem_auswertung.takt_rate` nennt wie das Protokollfeld den **längsten** Lauf
(`takt_rate_in` über die ganze Spanne); §15 behält `name`/`rate_pro_min` des letzten Laufs im
Format. (9) Anzeigen zeigen den wirksamen Takt (`TimerLauf.takt_effektiv`): „3,0/min · 2,0ד.
(10) `takt_gross` und die Rückfrage im Bewegungsbild-Blatt schließen mit `dialoge.schliessen`.
(11) Ein abgebrochener Timer schließt seinen Takt-Lauf sofort (`TimerBaustein.takt`). (13)
`TaktNeu.ende_danach`: ⏹ im Tick eines Abschnittsbeginns hält Ende · Beginn · Ende. (14)
`takt_pruefen` nennt `bild`.

## 11. Umsetzungsstand (5.11.2026, Version 0.3.53) — Takt je Planübung (A6)

Die Planübung folgt der Übung auch beim Takt (P79, `docs/plan_uebungen_einstellen.md`):
`PlanItem.takt: Takt | None` (Migration 039 `plan_item.takt_json TEXT`, NULL = wie die Übung,
`{}` = ausdrücklich keiner, eigene Spalte wie `timer_json` — kein Versteck im Timer-JSON, denn
der Takt ist keine Timer-Wahl und „wie die Übung“ braucht ein eigenes NULL),
`core.uebung_timer.takt_der_uebung(uebung, item)` (Planübung > Übung; ein leerer Takt im Plan
heißt keiner), `takt_fuer(…, item=)` (Uhr für jetzt > Abschnitt > Planübung > Übung),
`core.standards.takt_von`/`takt_eigen` (am Wert gemessen, „keiner“ gleicht „keiner“),
`abweichungen` nennt „Takt“, `bereinigt` lässt einen Takt wie den der Übung wieder folgen,
`vom_standard` setzt ihn zurück, `als_standard` trägt ihn in die Übung (auch „kein Takt mehr“),
`uebernehmen_vorschau` nennt ihn. Oberfläche: die Zeile in „Im Plan einstellen“ (§5), die
Übungsseite nennt unter „Uhr und Timer“ und in der Karte „In diesem Plan“ den Takt der Planübung.
Beim Üben: `components/uhr.py` und `views/uebung_timer.py` hängen `takt_der_uebung(uebung,
item)` als `TimerLauf.takt_uebung` an den Lauf (`takt_anbringen`), der Takt-Knopf zeigt ihn als
Vorgabe; „Takt zählt“ tritt damit auch mit einem Takt der Planübung an. Paket: je Planübung in
`plaene[].uebungen[]` das Feld `takt` (wie an der Übung; `{}` = keiner; `docs/uebungspakete.md`),
tolerant gelesen, nur geschrieben, wo die Planübung einen eigenen hat. Tests:
`tests/test_planuebung_sensor_takt.py` (flet-frei), `tests/test_ui_plan_sensor_takt.py`.
**Prüfrunde A6** (5.11.2026, 0.3.54): ein Takt ohne brauchbare Phase — im Paketfeld wie in der
Spalte `takt_json` — heißt **wie die Übung** (`None`), nie „keiner“ (`AUS` nur für `{}`); der
Paket-Import trägt den Takt je Planübung (`VorlageItem.als_planitem`), `pruefen` prüft ihn auch
dort („die Planübung folgt der Übung“), und der Timer-Knopf der Übungsseite unter einem Plan
öffnet `…/timer/uebung/<Übung>/<Planübung>` mit dem Takt der Planübung.
**Nicht gebaut:** der Takt im Plan-Ablauf (dort läuft auch der Sensor noch nicht, A19); das
Takt-Blatt aus „Im Plan einstellen“ kennt „In diesen Plan“ und „In die Bibliothek“, nicht
„Für jetzt“ (das gehört an die Uhr).
