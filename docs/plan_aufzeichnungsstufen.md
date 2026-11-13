# Plan: Aufzeichnung „normal“ oder „ausführlich“ — die Wahl am Start der Messung (13.11.2026)

Stand 13.11.2026: **angenommen, nichts gebaut.** Ben hat am 13.11.2026 die Grundzüge
(P207–P210) und die Einzelfragen (P211–P216: „so wie vorgeschlagen“) entschieden — Abschnitt 9.
Der Plan schreibt `docs/plan_diagnosemodus.md`
fort: Was dort zu Rohmitschnitt, Sensorblatt, rotem Punkt, Marken und Geräteprobe steht, gilt
weiter. Neu ist nur, **wo** man die ausführliche Aufzeichnung einschaltet und was die Ansicht
dazu sagt.

Anlass, Ben am 13.11.2026 (gekürzt):

> Ich brauche einen Aufzeichnungsmodus für die User (sparsam) und einen zum Debugging und zur
> Verfahrensverbesserung. Welchen Sinn hat es, dazwischen noch abzustufen?

> Im Moment ist der Diagnosemodus auf den Polar H10 zugeschnitten. Kann ja sein, dass User
> eigene Geräte haben. […] Und wenn man von einem User einen Komplettrohmitschnitt möchte,
> braucht es dann eine ausführlichere Aufzeichnung. Ein Grund wäre vielleicht die UX. Debugging
> muss in den Settings erst eingestellt werden. Modus normal–ausführlich kann direkt zum
> Startort der Messung gesetzt werden. […] Das Debugging kann man auch individuell umstellen
> lassen, je nachdem, was das Gerät an Einstellungen hergibt, 50 Hz, 200 Hz.

> Der Unterschied normal–ausführlich muss in der Viewbeschreibung vorhanden sein.

---

## 0. Kurzfassung

- **Zwei Aufzeichnungstiefen, kein Mittelweg.** „Normal“ ist der sparsame Alltag, „ausführlich“
  schreibt alle Rohdaten des Geräts mit. Eine dritte Stufe dazwischen sparte gegenüber
  „ausführlich“ bei 50 Hz fast nichts und bräuchte ein eigenes Dateiformat samt Dekoder je Gerät.
- **Die Wahl steht an der Gerätezeile der Messung**, sobald ein Gerät verbunden ist — ohne
  Umweg über die Einstellungen. Sie merkt sich den Stand.
- **Die Ansicht sagt, was der Unterschied ist:** unter der Wahl steht in zwei bis drei Zeilen,
  was die gewählte Stufe speichert und was sie kostet; das (i) daneben erklärt beide Stufen
  nebeneinander (Abschnitt 3).
- **Der Schalter in den Einstellungen bleibt für die Werkzeuge:** Marken-Leiste, Marken an der
  Uhr, Zähler-Vergleich, Suche nach unbekannten Geräten. Er heißt künftig „Entwicklerwerkzeuge“
  und entscheidet nicht mehr darüber, ob Rohdaten aufgezeichnet werden können.
- **Kein neues Dateiformat.** „Ausführlich“ schreibt, was der Diagnosemodus heute schreibt:
  den Rohmitschnitt `mitschnitt-v1` (Vertrag `docs/kompatibilitaet.md` §14) und das EKG-Beiwerk.
  `raw-v1` bleibt unverändert.
- **Vorher zu erledigen:** die Seriennummer des Geräts aus allem, was das Handy verlässt
  (Abschnitt 6), und ein Export, der mit mehreren Gigabyte umgehen kann (Abschnitt 7).

## 1. Warum zwei Stufen und nicht drei

Geprüft am 13.11.2026 an Bens Sammelexport (109 Messungen, 302 h, 15.10.–13.11.2026; Auswertung
in hrv-research):

| Befund | Folge |
|---|---|
| Nur 1 von 109 Messungen hat einen Rohmitschnitt, obwohl der Diagnosemodus seit dem 4.11. da ist | Der Weg „Einstellungen → Knopf → Sensorblatt“ je Messung kostet Daten. Die Wahl muss am Start stehen und sich merken |
| Vom Atem-Prototyp bleiben nur Phasen und Raten (4 Dateien, zusammen 33 min); das Rohsignal ist weg | Verfahren lassen sich an alten Messungen nicht neu rechnen. Dafür braucht es Rohdaten über lange Zeit, nicht nur in einzelnen Diagnosesitzungen |
| Außerhalb der 24 GPS-Trainings (16,8 h) gibt es kein Bewegungssignal | Haltung, Aktivität, Schrittfrequenz brauchen die Beschleunigung im Alltag |
| Diagnose mit 50 Hz: rund 6,5 MB je Stunde (`core/diagnose.menge_mb_h`), mit 200 Hz 14,5 MB | Ein entschlüsseltes Zwischenformat läge bei etwa 5 MB je Stunde — kein Gewinn, der eine Stufe trägt |
| 50 Hz liefern beim Zählen und bei den Atemphasen dieselben Werte wie 200 Hz (hrv-research, Entscheidungen 24 und 26) | 50 Hz als Vorgabe für „ausführlich“ |

Was eine dritte Stufe hätte und warum es nicht reicht:

- *Eine fertig entschlüsselte Datei*, die ohne Polar-Dekoder lesbar ist. Das zählt erst, wenn
  außer hrv-research jemand Rohdaten auswertet. Und es gilt nur für Geräte, die schon einen
  Dekoder haben — der Rohmitschnitt dagegen nimmt jedes Bluetooth-Paket jedes Geräts mit.
- *Eine Stufe für andere ohne Entwickler-Oberfläche.* Das leistet dieser Plan schon: Die
  Werkzeuge hängen am Schalter in den Einstellungen, nicht an der Aufzeichnungstiefe.

P123 (`docs/plan_beschleunigung.md`) bleibt in der Sache stehen: Im Alltag, also in „normal“,
werden keine Rohdaten der Beschleunigung gespeichert.

## 2. Die zwei Stufen

| | **Normal** (Vorgabe) | **Ausführlich** |
|---|---|---|
| Wofür | messen, üben, auswerten | Verfahren verbessern, Fehler suchen, ein fremdes Gerät kennenlernen |
| Herzfrequenz, RR-Abstände | ja | ja |
| EKG | nur mit dem Schalter „EKG mitschreiben“ (wie heute) | ja, wenn das Gerät es anbietet |
| Beschleunigung | läuft nur, solange gezählt oder die Atmung erfasst wird; **nicht gespeichert** | durchgehend, gespeichert; Vorgabe die kleinste Rate ab 50 Hz |
| Ergebnisse (Wiederholungen, Atemphasen) | ja | ja |
| Jedes Bluetooth-Paket roh, Uhrabgleich, Verzug der App, Akkustände | nein | ja (`mitschnitt-v1`) |
| Speicher | unter 1 MB je Stunde (gemessen 0,6) | H10 mit EKG und 50 Hz: rund 6,5 MB je Stunde Mitschnitt, dazu das EKG-Beiwerk |
| Akku | wie heute | mehr an Gurt und Handy; wie viel, misst der Mitschnitt selbst (Abschnitt 8) |
| Zeichen | keines | roter Punkt oben rechts, „● ausführlich“ in der Benachrichtigung |

„Ausführlich“ ist technisch der heutige Diagnosemodus: `Messlauf` mit Mitschnitt und
Zusatzströmen über `acc_anfordern` (`devices/messlauf.py`). Neu sind die Vorgaben je Gerät:

- **Ströme:** alles, was das Sensorblatt als schaltbar führt (`core/diagnose.sensoren`: heute
  EKG und Beschleunigung am H10).
- **Rate:** die kleinste ab 50 Hz, die der Treiber anbietet — dieselbe Regel wie beim Zählen
  (`core/zaehlen.zaehl_rate`: H10 50 Hz, Verity Sense 52 Hz). Bereich 8 g.
- **Geräte ohne Zusatzströme oder ohne Dekoder:** Der Mitschnitt nimmt die Pakete der
  Verbindung trotzdem mit; das Sensorblatt nennt sie „vorhanden · nur Rohmitschnitt“.
- **Umstellen je Gerät** (P209): „Einzelheiten“ öffnet das Sensorblatt. Dort lassen sich
  Ströme ab- und Raten umschalten (50, 100, 200 Hz, was das Gerät hergibt); die Wahl bleibt
  für dieses Gerät gespeichert.

## 3. Was die Ansicht zeigt und sagt

Bens Vorgabe: Der Unterschied muss in der Ansicht selbst stehen. Er steht deshalb an drei
Stellen, jeweils aus **einer** Textquelle (`core/diagnose.py`, ohne flet testbar), damit die
Zahlen überall dieselben sind.

### 3.1 Gerätezeile der Messansicht (`ui/views/messung.py`)

Sichtbar, sobald ein Gerät verbunden ist und noch keine Aufnahme läuft — unabhängig vom
Schalter in den Einstellungen, weiter hinter `config.ist_aktiv("diagnosemodus")` (P112).

```
Polar H10 · verbunden · Akku 90 %                        [Protokoll]
Aufzeichnung   ( Normal )  ( Ausführlich )                       (i)
Herzfrequenz und RR-Abstände. Atmung und Wiederholungen nur als
Ergebnis. Sparsam für Akku und Speicher.
```

Nach dem Tipp auf „Ausführlich“:

```
Aufzeichnung   ( Normal )  ( Ausführlich )                       (i)
Zusätzlich alle Rohdaten des Geräts: EKG 130 Hz, Beschleunigung
50 Hz, jedes Bluetooth-Paket. Etwa 7 MB je Stunde, mehr Akku an
Gurt und Handy. Bleibt auf dem Handy, bis du teilst.   Einzelheiten ›
```

- Die Beschreibung unter der Wahl ist **immer sichtbar**, nicht nur im (i). Sie nennt für
  „ausführlich“ die Ströme **dieses** Geräts mit ihrer Rate und die Menge aus `menge_mb_h` —
  bei einem Gerät ohne Zusatzströme heißt es „jedes Bluetooth-Paket des Geräts“.
- Ist in „normal“ der Schalter „EKG mitschreiben“ an, hängt die Zeile „EKG wird
  mitgeschrieben.“ an.
- „Einzelheiten ›“ öffnet das Sensorblatt (§2.3 des Diagnoseplans) mit der Überschrift
  „Ausführliche Aufzeichnung“ und dem Knopf „Übernehmen“ statt „Mit Diagnose aufnehmen“.
  Gestartet wird mit dem gewohnten Knopf „Aufnahme starten“.
- Während der Aufnahme ist die Wahl gesperrt und zeigt den Stand. „Ausführlich“ lässt sich
  wie heute über den roten Punkt beenden; die Messung läuft dann normal weiter.

### 3.2 Hilfe im (i) (`ui/components/hilfe.py`, neues Thema `aufzeichnung`)

Eine Tabelle „Normal · Ausführlich“ mit den Zeilen aus Abschnitt 2 in Alltagssprache, darunter
drei Sätze: wann man „ausführlich“ braucht (neues Gerät, etwas stimmt nicht, jemand bittet um
einen Mitschnitt), dass nichts das Handy verlässt, bis man teilt, und wo man die Rohdaten
wieder löscht.

### 3.3 Einstellungen → HRV-Messung (`ui/views/einstellungen_hrv.py`)

- Neue Karte **„Aufzeichnung“** mit demselben Zweizeiler je Stufe und dem Hinweis, dass man an
  der Messung wählt. Darunter die **Ablage** (Zahl und Größe der Mitschnitte, „Alle Rohdaten
  löschen“) — sie zieht aus der Diagnose-Karte hierher, weil sie jetzt jeden betrifft.
- Die Karte „Diagnosemodus“ heißt **„Entwicklerwerkzeuge“** (P216): Marken-Leiste, ⏯ an der
  Uhr, Zähler-Vergleich nach dem Satz, Suche nach unbekannten Geräten (Geräteprobe). Der Text
  sagt, dass die Werkzeuge nur zusammen mit „ausführlich“ etwas aufzeichnen.

### 3.4 Aufzeichnungsliste und Auswertung

Eine Messung mit Mitschnitt trägt in der Liste das Zeichen „ausführlich“ und in der Auswertung
die vorhandene Diagnose-Karte mit „Rohdaten teilen“ und „Rohdaten löschen (Messung bleibt)“.

## 4. Was sich im Code ändert

| Schicht | Änderung |
|---|---|
| `core/hrv_einstellungen.py` | neues Feld `aufzeichnung` (Stufe und gewählte Ströme, gemerkt nach P211); `diagnose_anbieten` behält Namen und Bedeutung „Werkzeuge an“; `diagnose_ekg`, `diagnose_acc`, `diagnose_acc_hz`, `diagnose_acc_g` gehen im neuen Feld auf (alte Werte beim Lesen übernehmen) |
| `core/diagnose.py` | `vorgabe(profil, sensoren)` (Ströme und Rate je Gerät), `beschreibung(stufe, …)` (die Texte aus Abschnitt 3), beide mit Doctests |
| `ui/views/messung.py` | Wahl und Beschreibung in der Gerätezeile; „Aufnahme starten“ startet je nach Stufe mit oder ohne Mitschnitt; die Bedingung `diagnose_anbieten` fällt für die Aufzeichnung weg und gilt nur noch für die Leiste |
| `ui/components/sensorblatt.py` | Titel und Knopf nach 3.1; der Vorabtest läuft nur von hier (P214) |
| `ui/components/hilfe.py` | Thema `aufzeichnung` |
| `ui/views/einstellungen_hrv.py` | Karten nach 3.3 |
| `core/hrv_export.py`, `ui/` | Abschnitte 6 und 7 |
| `devices/` | nichts Neues: Mitschnitt, Ströme und Puffer bleiben, wie sie sind |

Die Architekturregel bleibt gewahrt: Vorgaben und Texte liegen in `core/`, die Ansicht ruft sie
nur auf.

## 5. Andere Geräte und der Mitschnitt für den Support

- **Bekanntes Gerät mit Herzfrequenz-Dienst:** „Ausführlich“ wählen, messen, in der Auswertung
  „Rohdaten teilen“. Das ist der Satz, den man einem Nutzer schreiben kann.
- **Gerät mit eigenen Sensoren, aber ohne Dekoder:** wie oben; die Pakete stehen im Mitschnitt,
  der Treiber entsteht daraus in hrv-core (Diagnoseplan §8.3).
- **Gerät ohne Herzfrequenz-Dienst:** Dafür bleibt die Geräteprobe (Diagnoseplan §2.8) hinter
  den Entwicklerwerkzeugen — sie abonniert alles und braucht die Sicherheitsregeln dort (nie
  schreiben, nie die Seriennummer lesen).
- **Neue Verfahren je Gerät** prüft hrv-research an den Mitschnitten; die App bewertet nicht.

## 6. Voraussetzung: die Seriennummer bleibt auf dem Handy

Befund vom 13.11.2026: Der Export maskiert die Bluetooth-Adresse (S10), aber der Gerätename
mit Seriennummer steht im Klartext im Feld `geraet` der Messdatei und im Kopf und in den
Zeilen von `sensor_<ts>_diagnose.txt`. Im Mitschnitt wird er schon auf das Modell gekürzt
(`hrv_core.deid.mitschnitt_zeilen`). Sobald Nutzer Pakete schicken, ist die Seriennummer
dieselbe Art Kennung wie die Adresse.

Entschieden (P212): `core/hrv_export.exportkopie` kürzt den Gerätenamen in beiden Dateien auf das
Modell (`hrv_core.deid.geraet_modell`), wie es die Adresse maskiert. Die Dateien auf dem Gerät
bleiben unverändert. Ein Test wie bei S10: Kein Export-ZIP enthält die Seriennummer. Dazu in
hrv-core: `deid` kopiert Textdateien heute unverändert; das Diagnoseprotokoll bekommt dort
dieselbe Kürzung, damit auch das Einlesen in hrv-research sie nicht durchlässt.

## 7. Voraussetzung: Export bei großen Mengen

Mit „ausführlich“ im Dauerbetrieb entstehen bei Bens Nutzung (rund 10 h am Tag) etwa 2,5 GB im
Monat. Der Sammelexport „Alle exportieren“ baut das ZIP heute im Arbeitsspeicher
(`core/hrv_export.export_zip`, `io.BytesIO`) und reicht es als Bytes weiter
(`ui/components/weitergeben.weitergeben`).

- **Zeitraum wählen:** „Alle exportieren“ fragt nach „seit dem letzten Export · letzte 7 Tage ·
  Zeitraum · alles“ und nennt die Größe vor dem Packen.
- **In eine Datei packen** statt in den Speicher und die Datei teilen. Ob das Teilen-Menü auf
  Android eine Datei dieser Größe annimmt, ist am Gerät zu prüfen (Abschnitt 8).
- **Mit oder ohne Rohdaten:** ein Häkchen „Rohdaten mitgeben“; ohne bleibt der Export so klein
  wie heute.
- Der Hinweis ab 500 MB (`core/diagnose.HINWEIS_AB_BYTES`) bleibt; nach dem Teilen die
  vorhandene Frage „jetzt löschen?“ (P114).

## 8. Am Gerät zu prüfen

| # | Was | Wie |
|---|---|---|
| G1 | Akku des Gurts: normal · EKG · EKG und 50 Hz · EKG und 200 Hz | je Einstellung eine frische Batterie über mehrere Stunden; der Mitschnitt schreibt alle 30 s den Stand von Gurt und Handy (`probe`). Bens Daten bis zum 13.11. geben keine belastbare Zahl: ohne EKG rund 1 % je Stunde, mit EKG zwischen 0,5 und 5,6 % (Anzeige in 10-%-Schritten) |
| G2 | Zehn Stunden „ausführlich“ am Stück | Datei wächst auf rund 65 MB: Schreiben, Speicher, Hintergrunddienst, Wiederverbinden mit Neustart der Ströme |
| G3 | Wahl an der Gerätezeile auf dem schmalen Handy | Zeilenumbruch, Lesbarkeit der Beschreibung, (i) |
| G4 | Teilen einer großen ZIP-Datei | Android-Teilen-Menü mit 500 MB und mehr |
| G5 | Ein zweites Gerät (Verity Sense, 52 Hz) | Vorgabe greift, Sensorblatt zeigt die richtigen Raten |

## 9. Entscheidungen

Entschieden (Ben, 13.11.2026):

| # | Frage | Entscheidung |
|---|---|---|
| P207 | Wie viele Aufzeichnungstiefen? | **zwei**: normal (sparsam) und ausführlich (Debugging und Verfahrensverbesserung); kein Mittelweg |
| P208 | Wo wählt man? | **am Startort der Messung**, nicht erst nach einem Schalter in den Einstellungen |
| P209 | Raten und Ströme | **je Gerät umstellbar**, je nachdem, was das Gerät hergibt (50 Hz, 200 Hz) |
| P210 | Erklärung | Der Unterschied normal–ausführlich **steht in der Ansicht** |

Einzelfragen, entschieden wie vorgeschlagen (Ben, 13.11.2026):

| # | Frage | Entscheidung |
|---|---|---|
| P211 | Merkt sich die Wahl je Gerät oder für alle? | **je Geräteprofil** — ein neues Gerät beginnt mit „normal“ |
| P212 | Seriennummer in Exportkopien kürzen (Messdatei und Diagnoseprotokoll)? | **ja**, wie die Adresse (S10) |
| P213 | Bleibt „EKG mitschreiben“ ein eigener Schalter für „normal“? | **ja**, unverändert |
| P214 | Vorabtest (bis 20 s) bei jedem Start in „ausführlich“? | **nein**, nur über „Einzelheiten“; fehlt ein Strom, zeigt es der Stand am roten Punkt |
| P215 | Roter Punkt auch im Dauerbetrieb? | **ja** — er sagt, dass mehr Akku verbraucht wird |
| P216 | Name der Karte in den Einstellungen | **„Entwicklerwerkzeuge“** |

## 10. Stufen

| Stufe | Inhalt | Hängt ab von |
|---|---|---|
| 0 | Seriennummer aus den Exportkopien (Abschnitt 6), Test | P212; hrv-core für das Diagnoseprotokoll |
| 1 | `aufzeichnung` in den Einstellungen, Vorgaben und Texte in `core/diagnose.py` | P211 |
| 2 | Wahl und Beschreibung an der Gerätezeile, Sensorblatt als „Einzelheiten“, Hilfe-Thema | 1 |
| 3 | Einstellungen: Karte „Aufzeichnung“ mit Ablage, „Entwicklerwerkzeuge“ | 2, P216 |
| 4 | Export nach Zeitraum, in eine Datei, mit oder ohne Rohdaten | G4 |
| 5 | Gerätetests G1–G5, Zahlen in dieses Dokument | APK |
| 6 | Doku nachziehen: `CLAUDE.md`, `.claude/rules/sensor_takt.md`, Nachtrag in `plan_diagnosemodus.md` und `plan_beschleunigung.md` (P123: „nur in ausführlich“), `docs/offene_fragen.md` (P207–P216, G1–G5), Tutorial | — |

Stufen 0 bis 3 sind eine Lieferung; 4 kann folgen, sobald die ersten langen Mitschnitte da
sind.

## 11. Nicht Teil dieses Plans

- Ein Beiwerk `_acc.json` mit entschlüsselter Beschleunigung (Diagnoseplan §3.3 bleibt: erst,
  wenn die App sie selbst anzeigen soll).
- Ganztägige Bewegungsergebnisse in „normal“ (Haltung, Aktivität, Schrittfrequenz): Die
  Verfahren entstehen erst in hrv-research aus den ausführlichen Aufzeichnungen; ob die
  Beschleunigung dafür im Alltag dauernd laufen darf, entscheidet G1 (P119: der Akku geht vor).
- Luftdruck des Handys für die Höhenmeter und eine Übungstabelle im Export — eigene Punkte
  aus derselben Auswertung, in `docs/offene_fragen.md` einzutragen.
- Das Einlesen in hrv-research: Mitschnitte liegen dort außerhalb von git (zu groß für
  GitHub), versioniert werden Messdatei, Ergebnisse und Bewegungsspur.
