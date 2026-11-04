# Plan: Diagnosemodus — Sensoren, Rohmitschnitt, Marken, unbekannte Geräte (4.11.2026)

Stand 4.11.2026: **angenommen** (Ben: „Der Plan ist gut“, Fragen P110–P116 entschieden — Abschnitt 11;
„Mach gleich alles“: Stufen 0–8) und **umgesetzt** — Abschnitt 12 sagt, was gebaut ist und was offen. Er schreibt den Diagnosemodus
aus `docs/plan_diagnose.md` (17.10.2026, P30) fort; was dort zu H18, Protokoll und
Zustandsproben steht, gilt weiter und ist hier eingeordnet (Abschnitt 4 und 10).

Anlass, Ben am 4.11.2026 (zwei Nachrichten, gekürzt):

> hier in HRV-Research soll weiterhin das Entwicklungszentrum für bessere Algorithmen bleiben.
> In HRV-core können gerne Prototypen mit rein nach moderater Reife.
> Kannst du trainingsapp so umbauen, dass man dort einen Debugmodus hat, mit dem man Daten
> sammeln kann. Wenn HRV-Messung läuft und Übungen starten (die Stoppuhr/Timer), möchte ich per
> Buttondruck […] (der wird dann gut drückbar auf die View drauf gebaut, und scrollt mit, stört
> aber die Sicht nicht, oder er nimmt unten 1/3 der Appansicht und oben kann man weiter
> scrollen). Auch eine Anpassung der Uhr hrv-watch wäre möglich, dann ist der Startbutton ein
> Setzen eines Markers, um den Umkehrpunkt einer Bewegung zu setzen. […] Lohnt sich eine
> Unterscheidung Wiederholung, Atmung? Plane das einmal und ich seh mir den Plan an.

> Am besten soll der Diagnosemodus in den Einstellungen eingeschaltet werden können. Wenn das
> passiert ist, ist bei Messungen, bei der Geräteverbindung ein Button „Diagnosemodus“, den man
> anklicken kann. Wenn aufgezeichnet wird im Diagnosemodus (wichtig zu wissen + das kostet mehr
> Batterie) blinkt oben links/rechts ein roter Punkt wie bei einem Recording. Wenn das Gerät
> verbunden ist, sollte vor der Aufzeichnung angezeigt sein, welche Sensoren sich einschalten
> lassen, welche nicht. Ist das Gerät unbekannt, wäre es gut, man könnte einfach einen
> Rohmitschnitt machen, den man dann hinterher ausgeben kann. trainingsapp wird vielleicht ein
> Communityprojekt. […] Von diesen soll dann über die mitgeschickten Daten die Treiber für die
> Geräte in hrv-core hinterlegt werden.

---

## 0. Kurzfassung

**Was gebaut wird:** Ein Schalter in den Einstellungen bietet den Diagnosemodus an. An der
Gerätezeile der Messung startet ihn ein Knopf **„Diagnosemodus“** — je Messung, nicht für
immer. Vorher zeigt ein Blatt, **welche Sensoren das Gerät hat** und welche sich einschalten
lassen. Während der Aufnahme blinkt oben rechts ein **roter Punkt**. Aufgezeichnet wird ein
**Rohmitschnitt** jedes Bluetooth-Pakets (beim H10 mit EKG und Beschleunigung), dazu
**Marken**, die man mit einer großen **Marken-Leiste** unten am Bildschirm oder mit ⏯ an der
**Uhr** setzt: je Wiederholung am Umkehrpunkt, je Atemzug, bei einer Störung. Ein
**unbekanntes Gerät** lässt sich ohne Messung roh mitschneiden und als **Geräteprobe** teilen —
daraus entstehen später **Treiber in hrv-core**.

**Die Rollen der Repos** (Ben, 4.11.2026):

| Repo | Rolle im Diagnosemodus |
|---|---|
| **hrv-research** (privat) | Entwicklungszentrum: liest die Diagnosepakete ein, prüft Zähler und Atemverfahren gegen die Marken, entwickelt Algorithmen (Entscheidung 21, `docs/KONZEPT_GENAUIGKEIT.md`) |
| **hrv-core** (öffentlich) | Formate (Rohmitschnitt), Dekoder und **Treiber**; Prototypen nach moderater Reife in einem eigenen, gekennzeichneten Bereich |
| **trainingsapp** | sammelt im echten Training, zeigt an, bewertet nicht |
| **hrv-watch** | ⏯ am Band setzt die Marke |

**Wiederholung und Atmung unterscheiden? Ja — als Art der Marke, nicht als zweiter Knopf.**
Die beiden meinen Verschiedenes (unterer Umkehrpunkt einer Bewegung gegen Beginn des
Einatmens), gehen in verschiedene Zähler und haben ein anderes Tempo; eine Marke ohne Art wäre
in jedem Satz mehrdeutig. Ein großer Knopf genügt trotzdem, denn die Art folgt dem Kontext:
Läuft die Uhr einer Übung mit Wiederholungen, heißt ein Tipp „Wiederholung“; bei Halte- und
Atemübungen, in Satzpausen und in einer Messung ohne Übung „Atemzug“. Ein Chip in der Leiste
schaltet um. Dazu ein kleiner Knopf **„Störung“** (Husten, Gurt gerichtet, Handy aufgehoben) —
Gegenwahrheit, die jeder Zähler kennen muss. Beides in einem Satz zu tippen ist ohnehin
unrealistisch; Atemzüge in den Satzpausen zu tippen hat im Pilot gut geklappt (hrv-research,
Satzpausen: 95 % der Fenster beantwortet).

**Stufen** (Abschnitt 10): 0 Voraussetzungen · 1 Schalter, Sensorblatt, roter Punkt ·
2 Rohmitschnitt (Format in hrv-core) · 3 Marken-Leiste · 4 Uhr · 5 Auswertung in hrv-research ·
6 unbekannte Geräte · 7 Treiber in hrv-core · 8 Zähler-Vergleich nach dem Satz.

---

## 1. Was sich gegenüber bisher ändert

- **Die Brustgurt-Diagnose-App in hrv-research** (Entscheidung 21) sammelte bisher getrennt, weil
  die trainingsapp für das Experiment nicht umgebaut werden sollte. Der Pilot hat gezeigt, dass
  die Beschleunigung des H10 Atmung und Wiederholungen trägt; jetzt soll im echten Training
  gesammelt werden — also in der trainingsapp. Die Diagnose-App bleibt für **geführte
  Protokolle** (Atemtakt, Wiederholungstempo, Video), bis die trainingsapp das kann.
- **Der Diagnosemodus aus `plan_diagnose.md`** war als Schalter „für immer an“ gedacht
  (Selbstabschaltung offen, P30 a). Neu: Der Schalter **bietet an**, gestartet wird **je
  Messung** — damit ist P30 a erledigt. P30 b (gemeinsames Format in hrv-core) und P30 c
  (de-identifiziert in hrv-core und hrv-research) gelten als angenommen (Abschnitt 8).
- **Marken mit Art** gab es bisher nur als Notiz: ⏯ am Band schreibt heute eine Notiz ohne Text
  und ohne `marke` — in der Datei nicht von anderen leeren Notizen zu unterscheiden
  (`ui/geraete/flet_medien_kanal.py`, `marke`). Diagnosemarken gehen in den Rohmitschnitt, nicht
  in die Notizen (Abschnitt 3.4).

## 2. Bedienung, vom Schalter bis zum Teilen

### 2.1 Einstellungen → HRV-Messung → „Diagnosemodus“

Eigene Karte am Ende der Seite (`ui/views/einstellungen_hrv.py`), Vorgabe aus:

- **„Diagnosemodus anbieten“** — danach steht an der Gerätezeile der Knopf. Darunter in einem
  Satz, was er kostet: mehr Akku an Gurt und Handy, etwa 15 MB je Stunde, alles bleibt auf dem
  Handy, hinaus nur über „Teilen“.
- **Marken-Leiste:** „unten (ein Drittel)“ oder „schwebender Knopf“ (Vorgabe unten, P111).
- **Uhr am Handgelenk:** „⏯ setzt Diagnosemarken“ (nur sichtbar, wenn die Uhr an ist).
- **Ablage:** Zahl und Größe der Mitschnitte, „Alle Diagnosedaten löschen“ (Rückfrage).

Gespeichert in `HrvEinstellungen` (`core/hrv_einstellungen.py`, Felder in `als_dict`/`aus_dict`)
und je Edition hinter `config.ist_aktiv("diagnosemodus")` (P112).

### 2.2 Messung → Gerät verbunden → Knopf „Diagnosemodus“

In der Gerätezeile der Messansicht neben dem Protokollknopf (`ui/views/messung.py`,
`diagnose_knopf`), nur wenn angeboten und noch keine Aufnahme läuft. Ein Tipp öffnet das
Sensorblatt.

### 2.3 Sensorblatt: was das Gerät kann, was sich einschalten lässt

Ein Blatt von unten (`components/blatt.blatt_spalte`; vor der Aufnahme darf es modal sein):

```
Polar H10 · verbunden · Akku 90 %
──────────────────────────────────────────────────────────────
Sensor                       am Gerät      im Diagnosemodus
Herzfrequenz und RR          ✓ geprüft     immer         < 1 MB/h
EKG 130 Hz                   ✓ geprüft     [an]          ~ 4 MB/h
Beschleunigung 200 Hz, 8 g   ✓ geprüft     [an]          ~11 MB/h · Akku des Gurts
PPG, PPI, Gyroskop, Magnet   – hat dieses Gerät nicht
──────────────────────────────────────────────────────────────
Rohmitschnitt aller Pakete, zusammen etwa 15 MB je Stunde
Marken: Leiste unten · Uhr ⏯              [Mit Diagnose aufnehmen]
```

Die Mengen sind die des Rohmitschnitts (Hex je Paket, gerechnet aus dem Pilot); das
entschlüsselte EKG (`_ecg.json`, etwa 3 MB je Stunde) kommt wie heute dazu.

- **Woher die Häkchen kommen:** zuerst das Profil (`devices/profiles.py`, Fähigkeiten
  `CAP_*`), dann das Gerät selbst — gemeldete Dienste (Herzfrequenz, Akku, PMD) und beim
  Polar-PMD die Merkmalsliste (heute bei benannten H10 übersprungen, `polar.py` `typen`; im
  Diagnosemodus gelesen). „✓ geprüft“ heißt: am Gerät gesehen, „laut Profil“: nur erwartet.
- **Was die App noch nicht entschlüsseln kann** (etwa PPG komprimiert beim Verity Sense), steht
  als „✓ vorhanden · nur Rohmitschnitt“: Es wird mitgeschnitten, aber nicht angezeigt.
- Ein **kurzer Vorabtest** (höchstens 20 s, endet von selbst, sobald jeder gewählte Strom mit
  seiner Rate läuft — erprobt in der Diagnose-App) prüft vor der Aufnahme, ob wirklich kommt,
  was die Häkchen versprechen; fehlt etwas, nennt das Blatt es und man kann trotzdem starten.
- „Mit Diagnose aufnehmen“ startet die Aufnahme wie „Aufnahme starten“, nur mit den
  zusätzlichen Strömen und dem Mitschnitt.

### 2.4 Während der Aufnahme: der rote Punkt

- **Oben rechts** blinkt ein roter Punkt (1 Hz), in jeder Ansicht, solange der Diagnosemodus
  aufzeichnet (oben links liegt der Zurück-Pfeil; P110). In der Benachrichtigung der laufenden
  Messung steht „● Diagnose“ (`ui/laufend.py`).
- Ein Tipp auf den Punkt öffnet den **Stand**: seit wann, wie viele MB, Pakete je Strom und
  Sekunde, Lücken, Akku von Gurt und Handy — und „**Diagnose beenden**“ (die Zusatzströme hören
  auf, die Messung läuft normal weiter) sowie „Marken-Leiste zeigen“.

### 2.5 Die Marken-Leiste

Erscheint, sobald im Diagnosemodus die Uhr einer Übung startet (Stoppuhr oder Timer), und bleibt
bis zum Ende der Diagnose — auch in den Pausen, dann für Atemzüge. Zwei Formen (P111):

```
┌──────────────────────────────────┐        ┌──────────────────────────────────┐
│ ← Kniebeuge                   ●  │        │ ← Kniebeuge                   ●  │
│                                  │        │                                  │
│   (Ansicht scrollt wie immer)    │        │   (Ansicht scrollt wie immer)    │
│                                  │        │                                  │
├──────────────────────────────────┤        │                                  │
│  Wiederholung · Kniebeuge S2     │        │                                  │
│                                  │        │                                  │
│               12                 │        │                         ┌────┐   │
│      Tippen am unteren Punkt     │        │                         │ 12 │   │
│                                  │        │                         └────┘   │
│ [Wdh][Atem]   Störung   ↶   ▾    │        │                                  │
└──────────────────────────────────┘        └──────────────────────────────────┘
   unten ein Drittel (Vorgabe)                 schwebender Knopf (▾ klappt ein)
```

- **Die ganze Fläche ist der Knopf** (blind treffbar, auch mit dem Handy in der Hand). Gezählt
  wird beim **Aufsetzen** des Fingers (`GestureDetector.on_tap_down`), nicht beim Loslassen.
- Rückmeldung ohne Hinsehen: kurzes Vibrieren (`HapticFeedback.selection_click`), wahlweise
  das Klangholz (`core/klang.py`). Die Zahl zählt je Satz ab 1.
- **Art:** folgt dem Kontext (Abschnitt 0) — Übung mit Wiederholungsfeld → „Wiederholung“;
  Halte-, Zeit- und Atemübungen, Pausen, Messung ohne Übung → „Atemzug“. Der Chip schaltet
  um, bis sich der Kontext ändert. „Störung“ ist ein eigener kleiner Knopf, keine Art.
- **↶** nimmt die letzte Marke zurück (als eigene Zeile, nichts wird gelöscht). **▾** klappt zum
  schwebenden Knopf ein, ein Tipp darauf wieder auf.
- **Wo:** einmal für alle Ansichten in `ui/app.zeige_route`, gleich nach `leiste_einsetzen`
  (`components/startleiste.py`) — dasselbe Muster „festes Element, der Rest scrollt“; die
  Ansicht bekommt unten Platz, damit nichts unter der Leiste verschwindet. Zustand (offen,
  Art, Zähler) in `AppState`, weil `zeige_route` bei jedem Wechsel alles neu baut; die Leiste
  wird nie im Sekundentakt neu gebaut, nur ihre Zahl (sonst gehen Tipps verloren,
  `messung.py` `status_auffrischen`).
- **Grenze ehrlich benannt:** Mit den Händen am Boden (Liegestütz, Burpee, Stütz) tippt niemand.
  Dort zählt die Zahl am Satzende, später das Video der Diagnose-App; oder ein
  Bluetooth-Fernauslöser bzw. -Ring, der Mediatasten sendet — er kommt über denselben Weg wie
  die Uhr (Abschnitt 6), ohne neuen Code.

### 2.6 Die Uhr

Im Diagnosemodus eine eigene Seite am Band: `Wdh 12` · `Kniebeuge S2` · `⏯ Marke` — ⏯ setzt
eine Marke der aktuellen Art, Quelle „Uhr“. Startet ein Satz, springt das Band auf diese Seite.
Einzelheiten in Abschnitt 6.

### 2.7 Nach der Aufnahme

Die Messung wird wie immer gespeichert; neben ihr liegt der Mitschnitt. In der Auswertung eine
Zeile „Diagnose: 34 min · 9 MB · 85 Marken (Wdh 60, Atem 25)“ mit **„Diagnosepaket teilen“**
(ZIP: Messung, EKG, Mitschnitt, Marken; Adressen maskiert, nie GPS) und **„Diagnose löschen“**
(nur der Mitschnitt, die Messung bleibt). Die Marken stehen als eigene Ebene über der Kurve,
nicht in der Notizliste.

### 2.8 Unbekanntes Gerät: Rohmitschnitt ohne Messung

- **Suche:** Im Diagnosemodus zeigt „Geräte suchen“ auch Geräte ohne Herzfrequenz-Dienst
  (heute „Unbekanntes Gerät“, `profiles.geraeteart`). Mitgeschrieben wird nur das gewählte
  Gerät, nie die anderen in der Nähe (`plan_diagnose.md` §4).
- **Verbinden → Dienste:** Liste der Dienste und Merkmale mit Namen, wo bekannt (Herzfrequenz,
  Akku, Geräteinformation, Laufsensor, Radleistung, Pulsoximeter, Polar PMD …), herstellereigene
  markiert, je Merkmal lesen/benachrichtigen/schreiben.
- **„Rohmitschnitt starten“:** jedes Merkmal mit Notify oder Indicate abonnieren, Lesbares
  einmal lesen — **nie** die Seriennummer (0x2A25), **nie auf das Gerät schreiben** (wie
  `hrv-core/scripts/ble_erkundung.py`). Marken und Notizen gehen (Leiste mit „Marke“ statt
  Wdh/Atem: „jetzt bewegt“, „jetzt still“).
- **Stopp → Geräteprobe** unter Messung → Aufzeichnungen → **Diagnose**: Mitschnitt, Abbild der
  Dienste, ein kurzes Formular (Hersteller und Modell, was getan, Vergleichswert wie „Puls laut
  Uhr 64“). Teilen als ZIP. Daraus entstehen die Treiber (Abschnitt 8.3).

## 3. Was aufgezeichnet wird

### 3.1 Ein Rohmitschnitt-Format für alle: `mitschnitt-v1`

Heute gibt es drei Rohformate mit demselben Kern (Hex des Pakets + monotone Ankunftszeit):
praxis_gui `devices/rohlog.py` (`ble_roh/*.jsonl`), `hrv-core/scripts/ble_erkundung.py`
(`ble-erkundung-v1`) und die Diagnose-App (`roh.jsonl`). Vorschlag: **ein** Format in hrv-core,
JSON Lines, jede Zeile mit `art` und `t` (monoton, ns, dieselbe Uhr wie `t_capture`):

| `art` | Inhalt |
|---|---|
| `kopf` | Format, App und Version, Gerät (Adresse maskiert), Profil, gewählte Ströme und Einstellungen, Abbild der Dienste |
| `n` | Benachrichtigung: Merkmal, Hex, Zeit der Dart-Seite (µs), Folgenummer, Wanduhr |
| `w`, `r` | Schreiben (Kommando) und Lesen, mit Antwort |
| `v` | Verbindung: verbunden, getrennt (mit Code und Grund), Neuverbinden, Watchdog |
| `uhr` | alle 10 s ein Paar monotone Uhr ↔ UTC |
| `log` | Protokollzeilen der Quelle (heute nur die letzten 500, ohne Datum) |
| `probe` | alle 30 s: Akku von Gurt und Handy, Bildschirm, Energiesparen, Verzug der App |
| `marke`, `marke_weg` | Diagnosemarke: Art (`wdh`, `atem`, `stoerung`, `marke`), Quelle (`handy`, `uhr`), Nummer im Satz, Kontext; `_weg` nimmt die letzte zurück |
| `kontext` | Übung Start/Ende (Übung, Plan, Felder), Timer Start/Pause/Abschnitt/Ende, eingetragener Satz (Zahl) |

Das ist eine Obermenge von `roh.jsonl` — hrv-research liest es mit dem Code, der heute die
Diagnose-App liest (`hrv_research/brustgurt.py`), auch den Uhrabgleich je Paket, der Ankunft und
Gerätezeit jedes Rahmens braucht. Das EKG-Beiwerk speichert dafür zu wenig (nur die Ankunft des
ersten Rahmens).

### 3.2 Ablage und Namen

- **Mit Messung:** `Messungen/<Gerät>/sensor_<ts>_mitschnitt.jsonl` neben der Messdatei — so
  nimmt der Export ihn mit (`core/hrv_export.zugehoerige_dateien`). Vorher muss hrv-core die
  Endung kennen: `recording.ist_messdatei` und `deid.format_erkennen` hielten eine neue
  `sensor_<ts>_…`-Datei sonst für eine Messung (`_KEINE_MESSDATEI`, `BEIWERK_SUFFIXE`, eine
  `deid`-Regel, die die Adresse maskiert). Erst der Eintrag in `docs/kompatibilitaet.md` §2 und
  §8, dann hrv-core, dann die App.
- **Ohne Messung (unbekanntes Gerät):** `Diagnose/<ts>_<gerät>/mitschnitt.jsonl` und
  `probe.json` — nicht unter `Messungen/`, damit keine Liste dort eine Messung erwartet.

### 3.3 Entschlüsselte Ströme

EKG wie bisher als `_ecg.json`. Die Beschleunigung bekommt **zunächst keine eigene Datei**: Der
Mitschnitt ist die Wahrheit, entschlüsselt wird beim Lesen (hrv-core, Abschnitt 8.1). Eine
`_acc.json` folgt erst, wenn die App die Beschleunigung selbst anzeigen oder zählen soll
(Stufe 8).

### 3.4 Marken: im Mitschnitt, nicht in den Notizen

Viele hundert Marken je Messung würden die Notizliste und praxis_gui fluten; raw-v1 bleibt
unverändert. Die Marken stehen im Mitschnitt (`marke`-Zeilen) und werden in der Auswertung als
eigene Ebene gezeigt. Die eingetragene Zahl eines Satzes steht schon heute in der Messdatei
(`person/leistung` mit `feld` und `wert`, `ui/marken.py`) — die Wahrheit „Zahl“ ist also da;
die Marken liefern die Zeitpunkte. (P113: Soll das ⏯ außerhalb des Diagnosemodus künftig eine
`marke` mit `quelle: uhr` tragen, damit es unterscheidbar ist?)

### 3.5 Zeit

- Pakete: Dart-Stoppuhr je Paket (`t_mono_us`, schon heute in `flet_ble`), umgerechnet mit
  `devices/gatt.UhrAbgleich`; dazu Folgenummer und Wanduhr (`seq`, `t_wall_us`, heute
  ungenutzt).
- Tipp in der Leiste: Ankunft in Python beim Aufsetzen (Flets Tippereignis trägt keinen
  Zeitstempel; ob ein Zeiger-Ereignis mit Zeitstempel trägt, beim Bauen prüfen). Der Verzug der
  App wird mitgeschrieben (`probe`), wie der Lastwächter der Diagnose-App.
- ⏯ an der Uhr: Zeitstempel der Dart-Seite im Tasten-Ereignis von `flet_medien` (neu),
  umgerechnet wie die Pakete. Der Weg Band → Handy ist unbekannt lang; er wird aus den Daten
  geschätzt (Abschnitt 7).

### 3.6 Menge, Akku, Sicherheit beim Schreiben

- **Menge:** Pilot mit EKG und Beschleunigung: 7,6 MB in 30 min, also etwa 15 MB je Stunde;
  gepackt (ZIP) rund 4 MB. Nur Herzfrequenz: unter 1 MB je Stunde (`plan_diagnose.md`), mit
  EKG etwa 4 MB.
- **Akku:** Mit EKG und Beschleunigung kommen beim H10 etwa acht Pakete je Sekunde statt
  einem — dafür der rote Punkt.
- **Schreiben:** nur anhängen, jede Zeile sofort geschrieben, `fsync` alle 5 s, eine halbe
  letzte Zeile wird beim Lesen übergangen (wie die Diagnose-App). Ein Absturz kostet höchstens
  Sekunden, nie die Datei.

## 4. Voraussetzungen und Fallstricke (Stufe 0)

Gefunden bei der Erkundung am 4.11.2026; ohne sie wird der Diagnosemodus langsam oder unzuverlässig.

| # | Befund | Folge | Abhilfe |
|---|---|---|---|
| V1 | `FletBleTransport._notification` ruft kein `ohne_auto_update` — Flet vergleicht nach **jedem** Paket die ganze Seite | in der Diagnose-App die Ursache der „riesen Lag“ (dort am Rechner 17–44 ms je Ereignis); in der trainingsapp wächst die Last mit jeder Ansicht und jedem Strom, mit EKG schon heute | `ohne_auto_update()` im Handler (`ui/components/layout.py`); dasselbe für GPS-Ereignisse prüfen |
| V2 | PMD-Pakete halten den Watchdog wach (`polar.py` `_daten_da`) | mit Beschleunigung würde ein toter Herzfrequenz-Strom nie neu verbinden | Watchdog je Strom: 0x2A37 muss kommen |
| V3 | Beschleunigung fehlt ganz: kein `SET_RANGE`, kein Start/Stopp, keine Antwortbehandlung; eine Ablehnung setzt „Gerät lehnt ab“ | — | `devices/pmd.py`, `polar.py` (`acc=` wie `ekg=`); Kommandos und Rahmenformat erprobt in der Diagnose-App (200 Hz, 16 bit, 8 g; Rahmen-Typ 0x01 am H10) |
| V4 | EKG und „Teil speichern & weiter“: Teil 1 ohne `_ecg.json`, Journal bleibt liegen, Kopfzeile fehlt | der Mitschnitt hätte denselben Fehler | mitbeheben, Test mit EKG |
| V5 | „Löschen“ im Wiederherstellen-Dialog löscht nur den Kopf, nicht die Journale | Reste im Speicher | alle Begleitdateien löschen |
| V6 | EKG-Journal ohne `fsync` und ohne Schutz gegen eine halbe Zeile | Datenverlust bei Absturz | wie 3.6 |
| V7 | H18: Neuverbinden-Schleife (`plan_diagnose.md` §1) | — | wie dort |
| V8 | Die Diagnose-App prüft Innereien der trainingsapp (`tests/test_vertrag.py`) und startet die Beschleunigung selbst | ändert sich `PolarQuelle`, bricht ihr Vertragstest; doppelter Start | dort anpassen (hrv-research), `trainingsapp.ref` erst danach heben |

## 5. Oberfläche, wer was baut

| Teil | Was | Dateien |
|---|---|---|
| A | Karte „Diagnosemodus“ in den Einstellungen (2.1) | `ui/views/einstellungen_hrv.py`, `core/hrv_einstellungen.py`, `config.py` |
| B | Knopf „Diagnosemodus“ in der Gerätezeile, Sensorblatt mit Vorabtest (2.2, 2.3) | `ui/views/messung.py`, neu `ui/components/diagnose_blatt.py`, `devices/polar.py` (Merkmale lesen) |
| C | Roter Punkt in jeder Ansicht, Stand-Blatt (2.4) — als Überlagerung der Seite, damit kein Neuaufbau ihn stört (Flet-API beim Bauen prüfen) | neu `ui/components/diagnose_punkt.py`, `ui/app.py`, `ui/laufend.py` |
| D | Marken-Leiste (2.5) | neu `ui/components/marken_leiste.py`, `ui/app.zeige_route`, `ui/state.py` |
| E | Auswertung: Diagnosezeile, Marken-Ebene, Teilen, Löschen (2.7) | `ui/views/messung_detail.py`, `core/hrv_export.py` |
| F | Unbekanntes Gerät: Suche, Dienste-Liste, Geräteprobe (2.8) | `ui/views/messung.py`, neu `ui/views/geraeteprobe.py`, neu `devices/erkundung.py` |

Ohne flet und darum testbar: `devices/mitschnitt.py` — ein `BleTransport`, der alles an den echten
Transport weiterreicht und jede Zeile mitschreibt (aus der Diagnose-App übernommen, dort an zwei
echten Sitzungen erprobt) — sowie die Kontextregeln der Marken (`core/diagnose.py`: welche Art
zu welcher Übung, Zähler je Satz). Tests nach dem Muster `tests/test_uhr_kanal.py` und
`tests/attrappen.py`; der Simulator bekommt Beschleunigungsrahmen (die Diagnose-App hat einen
`SimGurt` mit Atmung, Bewegung und Klopfen).

## 6. Die Uhr (hrv-watch, `flet_medien`)

- **Seite „Diagnose“** in `core/uhr_seiten.py`, nur im Diagnosemodus in der Folge: Zeile 1
  `Wdh 12`, Zeile 2 Übung und Satz, Zeile 3 `⏯ Marke` (kurz genug ohne Laufschrift,
  TESTPLAN_fit3 F4). `TASTE_JE_SEITE["diagnose"]` → Diagnosemarke der aktuellen Art, Quelle
  „Uhr“. Startet ein Satz, wählt die App diese Seite.
- **Zeitstempel:** `flet_medien` stempelt jede Taste auf der Dart-Seite (wie `flet_ble`); die
  App rechnet mit `UhrAbgleich` um. Neue Erweiterung heißt neue APK; Entscheidung in
  `hrv-watch/docs/ENTSCHEIDUNGEN.md` (#8), `hrv-watch.ref` heben.
- **Am Band prüfen** (TESTPLAN_fit3): Wie lange braucht ⏯ bis zur App? Kommt jedes ⏯ an,
  wenn man jede Sekunde drückt? Schluckt Galaxy Wearable schnelle Folgen?
- Bleibt wie entschieden: ⏯ startet oder stoppt nie die Aufnahme (hrv-watch #6).

## 7. Auswertung in hrv-research

- **Einlesen:** `scripts/diagnose_einlesen.py` (nur eigene Pakete, wie `brustgurt_einlesen.py`)
  nach `daten/selbst/trainingsapp_diagnose/<id>/`; die Datenprüfung (`pruefe_daten.py`) kennt
  `mitschnitt-v1` nach Feldliste (keine unmaskierte Adresse, kein GPS).
- **Lesen:** über den Leser aus hrv-core (8.1) oder übergangsweise `hrv_research.brustgurt`.
- **Je Satz:** Marken gegen eingetragene Zahl gegen Zähler (der Wiederholungszähler mit
  Satzgrenzen aus `docs/KONZEPT_GENAUIGKEIT.md` B3); Zeitversatz der Marke zum Umkehrpunkt im
  Signal, je Quelle (Handy, Uhr) und Übung — das ist auch die Messung des Wegs Band → Handy.
- **Je Pause und Atemübung:** Atemmarken gegen K2–K4 (Notebook 05).
- **Ergebnis:** ein Bericht je Paket (wie der Prüfbericht A–D, dazu Ebene E: Marken) und der
  Zählbarkeitskatalog je Übung; alles im Benchmark mit Sitzungen „einstellen“/„prüfen“ nach Tagen
  (Konzept A).

## 8. hrv-core: Format, Prototypen, Treiber

### 8.1 Sofort nötig (Stufe 2)

- **`mitschnitt-v1`:** Schema in `docs/formate.md`, Schreib-Hilfe und Leser
  (`hrv_core.mitschnitt`: Zeilen bauen, lesen, halbe Zeilen übergehen), `deid`-Regel (Adresse
  maskieren, Gerätename aufs Modell kürzen), Endung in `BEIWERK_SUFFIXE`/`_KEINE_MESSDATEI`.
  Schreiben tun die Apps (trainingsapp, später praxis_gui `rohlog`), lesen alle — auch
  hrv-research.
- **PMD-Dekoder für die Beschleunigung** (Rahmen-Typen 0x00–0x02, Gerätezeit der letzten Probe)
  und die Kommandos (Start mit Rate, Auflösung und Bereich; Stopp; Einstellungen lesen) — aus
  der Diagnose-App, wo sie am echten H10 liefen. Als Fixture ein kurzes Stück aus Bens Pilot
  (eigene Aufnahme ohne Personenbezug, nach hrv-core-Regel erlaubt — aus hrv-research aber nur
  mit Bens Freigabe im Einzelfall, dortige Regel 8) oder synthetische Rahmen nach dem Format.

### 8.2 Ein Bereich für Prototypen

Ben: „In HRV-core können gerne Prototypen mit rein nach moderater Reife.“ Vorschlag:
`hrv_core.prototyp` — gekennzeichnet im Modulkopf, nie Grundlage gespeicherter Kennzahlen oder
Caches, darf sich ohne `ALGO_VERSION` ändern, hat Tests, aber noch keinen Golden Master.
**Eingang:** in hrv-research an mindestens zwei Sitzungen geprüft, die nicht zum Einstellen
dienten, mit Befund in `ENTSCHEIDUNGEN.md`. **Ausgang:** nach `docs/UEBERNAHME.md` ins
Stammmodul, dann mit Golden Master. Erste Kandidaten: der Wiederholungszähler mit Satzgrenzen
und K4 (Atmung aus Beschleunigung und RSA).

### 8.3 Treiber für Geräte der Community

**Was ein Treiber ist** — alles außer dem Bluetooth selbst, darum passt er nach hrv-core (nur
numpy, kein Bluetooth, keine App):

| Teil | Beispiel H10 |
|---|---|
| Erkennung | Name „Polar H10 …“, Dienste 0x180D und PMD |
| Fähigkeiten | HR + RR, EKG 130 Hz, Beschleunigung 25–200 Hz |
| Ablauf | 0x2A37 abonnieren; PMD-Steuerung und -Daten abonnieren; EKG-Start schreiben |
| Dekoder | Bytes → Proben mit Gerätezeit, je Strom und Rahmen-Typ |
| Zeitmodell | Gerätezeit ns seit 2000, Rate aus der Gerätezeit |
| Qualität | `rr_ekg`, Ausreißerschwelle, Hinweise |

Heute steht das verstreut: Profile doppelt in trainingsapp und praxis_gui (`profiles.py`, die
ersten vier „deckungsgleich“), Protokoll und Dekoder in `devices/polar.py`/`pmd.py`. Vorschlag:
Profile und Dekoder ziehen nach `hrv_core.geraete`; die Apps behalten den Transport und führen den
**Ablauf eines Treibers** aus (eine allgemeine Quelle statt einer Klasse je Hersteller). Ein
neues Gerät ist dann ein Treiber in hrv-core und ein `hrv-core.ref` in den Apps — „ein Eintrag,
kein Umbau“, wie `profiles.py` es heute schon verspricht.

**Reifegrade**, in der App sichtbar: *erkannt* (Dienste bekannt, nur Standardströme) →
*Prototyp* (Dekoder an einer Geräteprobe getestet) → *geprüft* (zwei Geräte oder zwei Personen,
gegen den H10 nach `docs/geraete/ble_uebertragung_pruefen.md`) → *empfohlen*.

**Weg einer Geräteprobe zum Treiber:**

1. Jemand schneidet sein Gerät mit (2.8) und teilt die Probe — als Datei, **kein Hochladen aus
   der App** (Solo öffnet keine neue Netzverbindung ohne Schalter, Hinweis und TOM-Nachtrag).
2. Eingang über eine Vorlage „Neues Gerät“ im hrv-core-Repo, mit Einwilligung und CLA
   (`CONTRIBUTING.md`).
3. Entschlüsseln, Befund unter `docs/geraete/<gerät>/` (wie Decathlon, Beurer).
4. Treiber als Prototyp mit Test; als Fixture nur, was die Regel von hrv-core erlaubt (P115).
5. `hrv-core.ref` heben — das Gerät erscheint mit seinem Reifegrad.

**Datenschutz:** Eine Geräteprobe enthält Gesundheitsdaten (Puls, ggf. EKG) einer anderen
Person. Wer Proben annimmt, verarbeitet sie (Art. 9 DSGVO): Einwilligung, Zweck, Löschfrist,
Hinweis vor dem Teilen (was drin ist, Vorschau), Kürzung auf das Nötige (Vorschlag: höchstens
2 min, nur das gewählte Gerät, Adresse maskiert, keine Seriennummer). **Entschieden (P115):**
„vorerst nur meine Proben. Fremde Daten gehen nicht online, aber werden für Korrekturrechnungen
verwendet bzw. zur Treibererstellung“ — fremde Proben bleiben lokal bei Ben und kommen nie in ein
Repo; in hrv-core landen nur der Treiber und synthetische Nachbauten nach dem entschlüsselten
Protokoll. Eine Eingangsvorlage für die Community gibt es erst nach rechtlicher Klärung.

## 9. Editionen, Recht, Datenschutz

- Ein Schalter je Fähigkeit: `diagnosemodus` in `config._FUNKTIONEN`, **in beiden Editionen**
  (P112, Ben: „In Praxis bleiben die Daten erstmal lokal. Ins Repo kommt nur, was ich selbst
  ablege, bzw. Anonymisiertes — trainingsapp ebenso“). Die App gibt nichts von selbst weiter;
  Teilen exportiert maskiert (Adresse, Gerätename), und was in ein Repo geht, entscheidet Ben.
- **Kein GPS** im Mitschnitt. Die Beschleunigung des Gurts enthält keine Himmelsrichtung (ohne
  Gyroskop und Magnetometer keine Koppelnavigation) — im Sinn der Regel „ortsfrei darf mit“
  (Ben, 26.10.2026). Andere Geräte in der Nähe werden nie protokolliert. Ein Gerät mit
  Magnetometer (Verity Sense) bekommt diesen Strom nur ausdrücklich und mit Hinweis.
- **Keine Netzverbindung,** nichts verlässt das Handy außer über „Teilen“; dort ein Hinweis, was
  im Paket ist.
- **Keine Bewertung:** Marken und Zahlen sind Daten, kein Rat (Zweckbestimmung).
- Nachträge: `docs/recht/40_toms.md` (neue Datenarten: Rohmitschnitt, Bewegungssensor,
  Marken), Verarbeitungsverzeichnis, Hinweistext in den Einstellungen.

## 10. Stufen

| Stufe | Inhalt | Repos | Umfang |
|---|---|---|---|
| **0** | V1–V7: Auto-Update, Watchdog je Strom, EKG-Fallstricke, H18 | trainingsapp | M |
| **1** | Schalter, Knopf an der Gerätezeile, Sensorblatt mit Vorabtest (bekannte Geräte), roter Punkt, Stand-Blatt | trainingsapp | M |
| **2** | `mitschnitt-v1` in hrv-core (Schema, Leser, deid, Endung), PMD-Beschleunigung; `devices/mitschnitt.py`, Beschleunigung im Diagnosemodus, Teilen und Löschen; Diagnose-App anpassen (V8) | hrv-core, trainingsapp, hrv-research | L |
| **3** | Marken-Leiste mit Kontext (Art, Satz, Zähler), Marken-Ebene in der Auswertung | trainingsapp | M |
| **4** | Uhr: Seite „Diagnose“, ⏯-Marke, Zeitstempel in `flet_medien` (neue APK) | hrv-watch, trainingsapp | S |
| **5** | Einlesen, Bericht mit Marken, Zähler gegen Marken je Übung, Weg Band → Handy | hrv-research | M |
| **6** | Unbekannte Geräte: Suche, Dienste-Liste, Rohmitschnitt ohne Messung, Geräteprobe | trainingsapp, hrv-core | M |
| **7** | Treiber in hrv-core: Profile und Dekoder umziehen, allgemeine Quelle in den Apps, Reifegrade, Vorlage „Neues Gerät“; Regel für Proben (P115) | hrv-core, trainingsapp, praxis_gui | L |
| **8** | Nach dem Satz: „Marken 12 · Zähler 11 · eingetragen 12“ mit dem Zähler-Prototyp aus hrv-core | hrv-core, trainingsapp | M |

Mit Stufe 0–3 lässt sich sammeln, mit 4 die Uhr nutzen, mit 5 zeigt sich, ob das Zählen
klappt. 6–8 bauen den Community-Weg. Jede Stufe endet mit Tests, Doku und — wo neue
Erweiterungen dabei sind — einer APK, die Ben baut.

## 11. Entschieden (Ben, 4.11.2026)

| # | Frage | Entscheidung |
|---|---|---|
| P110 | Roter Punkt | oben rechts |
| P111 | Marken-Leiste | unten ein Drittel, zum Knopf einklappbar; „schwebender Knopf“ in den Einstellungen wählbar |
| P112 | Praxis-Edition | in beiden Editionen; Daten bleiben lokal, ins Repo nur, was Ben selbst ablegt, oder Anonymisiertes |
| P113 | ⏯ außerhalb des Diagnosemodus | `marke {quelle: uhr, art: marke}` (Vertrag §4 zuerst) |
| P114 | Aufbewahrung | bis zum Löschen; Hinweis ab 500 MB; nach dem Teilen „jetzt löschen?“ |
| P115 | Geräteproben anderer | vorerst nur Bens Proben; fremde nie online, aber lokal für Korrekturrechnungen und Treiber nutzbar |
| P116 | Brustgurt-Diagnose-App | läuft parallel, **gleiche Grundlage** (Format `mitschnitt-v1`, Dekoder und Beschleunigung aus hrv-core bzw. der trainingsapp), verschiedene Eingänge: die Diagnose-App fragegerichtet (Protokolle), die trainingsapp alltagspraktisch |
| — | Umfang | „Mach gleich alles“ — Stufen 0–8 |

## 12. Umsetzungsstand (4.11.2026)

| Stufe | Gebaut | Wo |
|---|---|---|
| 0 | V1 Auto-Update aus in BLE- und GPS-Ereignissen · V2 Watchdog nur am HF-Strom · V4 EKG bei „Teil speichern“ · V5 „Löschen“ räumt alle Journale weg · V6 EKG-Journal mit fsync · V8 Diagnose-App ohne doppelten ACC-Start | trainingsapp 7ff2f12, hrv-core 0.6.0, hrv-research be5b465 |
| 1 | Karte in den Einstellungen, Knopf an der Gerätezeile, Sensorblatt (geprüft/laut Profil/nur roh, MB je Stunde, Vorabtest bis 20 s), roter Punkt mit Stand-Blatt, „● Diagnose“ | `ui/components/sensorblatt.py`, `diagnose_punkt.py` |
| 2 | `mitschnitt-v1` und PMD-Dekoder mit Beschleunigung in hrv-core; `MitschnittTransport`; Beschleunigung in `PolarQuelle`; Mitschnitt neben Backup → Beiwerk; Teilen, Löschen, Export bereinigt; Diagnose-Karte in der Auswertung | hrv-core 0.6.0/0.6.1, `devices/mitschnitt.py`, `messlauf.py` |
| 3 | Marken-Leiste im Overlay (unten ein Drittel/Knopf), Art aus dem Kontext, Chips, Störung, ↶; Kontextzeilen aus allen automatischen Notizen; Marken als Ebene über der Kurve | `ui/components/marken_leiste.py`, `core/diagnose.py` |
| 4 | Seite „Diagnose“ am Band, ⏯ mit Dart-Stempel, Sprung beim neuen Satz; ⏯ außerhalb als `uhr/marke` (P113) | hrv-watch fa8d037 (#8), `core/uhr_seiten.py`, `flet_medien_kanal.py` |
| 5 | Einlesen der Diagnosepakete, Marken je Satz, Uhr gegen Leiste, Bericht; Diagnose-App auf hrv-core-Dekoder; gleiche Ströme aus beiden Lesern geprüft | hrv-research `trainingsapp_diagnose.py`, Entscheidung 22 |
| 6 | Geräteprobe ohne Messung: Dienste mit Namen, Rohmitschnitt, Marken bewegt/still, Formular, Teilen | `devices/erkundung.py`, `ui/views/geraeteprobe.py` |
| 7 | GATT-Namen, Dekoder 0x2A37 und Treiber mit Reifegrad in hrv-core; Reifegrad in Suche und Sensorblatt | hrv-core 0.7.0 (`geraete/gatt.py`, `treiber.py`) |
| 8 | Wiederholungszähler (hrv-research, an Sitzung P: 11/11, 15/15, 20/20) als Prototyp in hrv-core; nach dem Satz „Marken · Zähler (Prototyp) · eingetragen“ | hrv-core 0.8.0, `messlauf._satz_vergleichen` |

**Offen und bewusst zurückgestellt:**

- *Allgemeine Quelle statt `PolarQuelle`* (8.3): Die Apps führen den Ablauf eines Treibers noch
  nicht selbst aus — `PolarQuelle` bleibt; hrv-core liefert Dekoder, Namen und Reifegrad. Ein
  Umbau berührt praxis_gui und den am Gerät erprobten Verbindungsablauf (H18).
- PPG, Gyroskop, Magnetometer sind im Sensorblatt nur „vorhanden · noch nicht einschaltbar“
  (kein am Gerät erprobtes Startkommando; Magnetometer nur ausdrücklich, §9).
- Der Simulator hat keinen Bluetooth-Transport — der Diagnosemodus braucht ein echtes Gerät
  (Tests nutzen eine Attrappe des Transports).
- Zähler: welcher Umkehrpunkt (oben/unten) gezählt wird; Eingang in `hrv_core.prototyp` mit
  Ausnahme (eine Sitzung) — die nächsten entstehen mit diesem Modus.

**Für Ben:** neue APK (`flet_medien` geändert — der Lauf „APK“ am Branch baut sie); am Band
TESTPLAN_fit3 Teil 4 (F10–F13). Die Tags `v0.6.0` bis `v0.8.0` fehlen auf GitHub (der Push von
Tags ist in der Cloud-Sitzung gesperrt) und werden an den Commits gesetzt:

```bash
git -C ../hrv-core pull
git -C ../hrv-core tag v0.6.0 ba9d392
git -C ../hrv-core tag v0.6.1 6e335f7
git -C ../hrv-core tag v0.7.0 e755df8
git -C ../hrv-core tag v0.8.0 dabc777
git -C ../hrv-core push origin v0.6.0 v0.6.1 v0.7.0 v0.8.0
```
