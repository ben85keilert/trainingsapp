# Plan: Beschleunigungssensor in Übungen — Wiederholungen und Atemzüge zählen, Ein- und Ausatmung in der HRV

Stand 4.11.2026: **Entwurf** — Ben: „Plane das beides durch“. Fragen P117–P126 stehen in
Abschnitt 12 und in `docs/offene_fragen.md`. Die Verfahren entstehen in hrv-research (dort
`beschleunigung/docs/PLAN_ZAEHLEN_ATEMPHASEN.md`); hier steht, was die Apps bauen.

Anlass (Ben, 4.11.2026):

> Dann brauche ich bereits die Erweiterung von trainingsapp/praxis_gui um das Zählen der Atmung
> und Wiederholungen. Die algorithmische Entwicklung bleibt in hrv-research, ich würde nur gerne
> nebenbei schon testen, wie gut die Genauigkeit des Beschleunigungssensors funktioniert in Echt.
> D.h. Übungen bekommen in den Einstellungen einen Bereich, wo der Beschleunigungssensor
> eingestellt werden kann. Mindestens einmal – Atmung – Wiederholungen. Langfristig wird es vlt
> verschiedene templates für die Bewegung geben, das muss sich noch entwickeln. Kniebeugen für
> x-Achse, Liegestützen Neigung zy… Am Ende des Umbaus möchte ich, wenn die Übung läuft (z.B.
> Liegestützen mit Stoppuhr/Timer bei laufender Messung) einen Button aktivieren können, der mir
> die Bewegungen zählt. Dazu ein +1, -1 zur Korrektur. Zuerst einmal das. Wenn eine Übung auf
> Atmung/Meditation geht und die Atmung getrackt wird, bräuchte ich die Zusatzinfo der
> Ein-/Ausphase in der HRV, um die HRV zu verbessern.

## 0. Kurzfassung

- **Teil A: Zählen.** Jede Übung bekommt in „Übung bearbeiten“ die Karte
  **„Beschleunigungssensor“**. Darin wählt man das Zählen (*aus · Wiederholungen · Atmung*)
  und die **Bewegung**: zuerst nur „Automatisch“, später Vorlagen aus hrv-core wie
  „Kniebeuge: Hub“ oder „Liegestütz: Neigung z–y“. Läuft die Übung mit Stoppuhr oder Timer,
  und läuft dazu eine Messung mit einem Gurt, der Beschleunigung liefert (H10, Verity Sense),
  dann steht neben der Zeit der Knopf **„Wdh. zählen“** (bei Atemübungen „Atemzüge zählen“).
  Die Zahl wächst mit, **−1** und **+1** korrigieren sie. Am Satzende geht sie als
  Wiederholungen des Satzes in den offenen Eintrag, so wie heute die Zeit. Ein
  **Zählprotokoll** an der Übung zeigt je Satz, was der Gurt zählte, was korrigiert und was
  eingetragen wurde. So sieht man im Alltag, wie genau der Gurt zählt.
- **Teil B: Ein- und Ausatmung in der HRV.** Bei Atemübungen legt die App die Atemphasen über
  die Herzfrequenz. Sie kommen aus dem Takt des Timers (Soll) und aus der Beschleunigung (Ist).
  Daraus entstehen je Atemzug die Atemspanne (Gipfel–Tal), die Phasenlage, das Verhältnis
  Ein:Aus und die Rate. Dazu kommt die Einordnung der Frequenzmaße: Wer langsamer als 9-mal
  pro Minute atmet, atmet im LF-Band. Alles ist beschreibend, als Prototyp gekennzeichnet und
  wird beim Anzeigen aus den Rohdaten gerechnet.
- **Arbeitsteilung.** Die Verfahren entstehen in hrv-research und kommen als **Prototyp** nach
  `hrv_core.prototyp`: ohne `ALGO_VERSION` und nie Grundlage gespeicherter Kennzahlen. Die Apps
  rufen sie nur auf. praxis_gui bekommt dieselben Funktionen und Formate aus hrv-core.
- **Zuerst kommt Stufe A1:** die Einstellung, der Knopf mit ±1 und der Eintrag. Sie nutzt den
  vorhandenen Zähler-Prototyp (`hrv_core.prototyp.wiederholungen`, hrv-core 0.8.0) und braucht
  keine neue Rechnung in hrv-core.

## 1. Was schon steht

| Baustein | Stand | Wo |
|---|---|---|
| Beschleunigung des Gurts | PMD-Strom (Vorgabe 200 Hz, 8 g), eingeschaltet nur im Diagnosemodus; ein Beobachter (`acc_beobachter`), Puffer für gut 10 min | `devices/polar.py` (`stroeme_setzen`), `devices/messlauf.py` (`_acc_puffer`, `_acc_fenster`), Dekoder `hrv_core.geraete.pmd` |
| Fähigkeit je Gerät | `CAP_PMD_ACC` bei H10 und Verity Sense | `devices/profiles.py` |
| Zähler-Prototyp | `wiederholungen.zaehlen(xyz, rate_hz, t0_s)` → `Zaehlung(anzahl, zeiten_s, periode_s, gleichmaessigkeit, art="prototyp")`; zählt einen ganzen Satz | `hrv_core.prototyp.wiederholungen` (0.8.0) |
| Vergleich nach dem Satz | im Diagnosemodus „Marken · Zähler (Prototyp) · eingetragen“ | `Messlauf._satz_vergleichen`, `components/marken_leiste.py` |
| Marken als Wahrheit | ein Tipp je Wiederholung bzw. Atemzug, ↶, ⏯ an der Uhr; der Zustand liegt ohne flet | `components/marken_stand.py`, `core/diagnose.py` |
| Übungslauf | eine Einheit aus Übung und Timer, dazu die HRV; die Zeitleiste ist die Provenienz; die Zeit kommt als Haltezeit bzw. Zeit in den offenen Eintrag | `devices/einheit.py`, `core/einheit.py`, `core/timer_eintrag.py`, `SessionRepo.lauf_eintragen` |
| Laufende Uhr | als Zeile in der Karte „Eintragen“ oder als Knöpfe; Timer-Ansicht „Während“ | `components/uhr.py`, `views/uebung_timer.py` |
| Wiederholungen | ein Feld der Art `reps` (auch `reps_2`, P106); ohne Sätze (`saetze=False`) eine Liste, angezeigt als Summe | `core.diagnose.hat_wiederholungen`, `core.result_spec` |
| Atemübungen | Typ „Atmung“ (`Exercise.typen`; im Paket „Standard“ vier Übungen) | `core/models.TYPEN`, `data/seed/standard.toml` |
| Atemfrequenz | aus den RR-Abständen mit Prüfkette (stabil); aus der Beschleunigung (K1–K4) bisher nur in hrv-research | `hrv_core.atmung`; hrv-research `hrv_research.beschleunigung.brustgurt_atem` |
| EKG-Beiwerk | `sensor_<ts>_ecg.json` neben der Messdatei, mit Journal gegen Absturz | `hrv_core.ekg` |

## 2. Wer was macht

| Repo | Aufgabe |
|---|---|
| hrv-research (privat) | Verfahren entwickeln und prüfen: Live-Zählen, Vorlagen, Atemzüge und Atemphasen, Atem-HRV. Die Wahrheit kommt aus Video, Marken, Metronom und den eingetragenen Werten. Dazu das Einlesen der neuen Quellen. Plan dort: `beschleunigung/docs/PLAN_ZAEHLEN_ATEMPHASEN.md`. |
| hrv-core (öffentlich) | Prototypen (`prototyp.wiederholungen` erweitert, `prototyp.atemzuege` und `prototyp.atem_hrv` neu), der Katalog der Vorlagen und das Rohdatenformat `acc-v1` (stabil wie `ekg`). Nur numpy. |
| trainingsapp | Einstellung an der Übung, Strom, Zähl-Baustein, Knopf, Eintrag, Zählprotokoll, Atem-Ebene. Keine Rechenlogik in `ui/`. |
| hrv-watch | später die Seite „Zählen“ am Band (A6) |
| praxis_gui | dieselben Funktionen und Formate aus hrv-core; die Bedienung baut es selbst (Abschnitt 9) |

## 3. A1: Die Karte „Beschleunigungssensor“ an der Übung

### 3.1 Was man einstellt

| Einstellung | Werte | Vorgabe |
|---|---|---|
| Zählen | Aus · Wiederholungen · Atmung | leer = aus der Übung: Feld `reps` → Wiederholungen, Typ „Atmung“ → Atmung, sonst aus |
| Bewegung (nur Wiederholungen) | „Automatisch“ (Hauptachse, wie der Prototyp heute); später Vorlagen aus hrv-core | Automatisch |
| Zählt in (nur bei mehreren Wdh.-Feldern) | `reps`, `reps_2` … unter den Namen ihrer Karten | das erste Wdh.-Feld |
| Atemphasen in der Auswertung (nur Atmung, Teil B) | an · aus | an |

„Wiederholungen“ braucht ein Feld der Art `reps`. Fehlt es, ist der Chip ausgegraut, und das
(i) erklärt warum. Zählen ist **Anzeige und Vorschlag** für den Eintrag; das letzte Wort hat
die Person.

### 3.2 Vorlagen (langfristig)

Ben: „Kniebeugen für x-Achse, Liegestützen Neigung zy…“ Eine Vorlage ist eine Signalwahl mit
Parametern, kein Code in der App:

- **Signal:** Hauptachse (gerätefrei), Betrag, eine feste Achse (x, y, z) oder die Neigung in
  einer Ebene (z–y, z–x). Die Neigung zählt gegen die Lage zu Satzbeginn, damit der Sitz des
  Gurts weniger stört.
- **Zähltyp** (Konzept B2 in hrv-research): periodisch oder als Zustandsfolge (Burpee). Dazu
  kommen die erwartete Dauer einer Wiederholung, der Umkehrpunkt (oben oder unten) und der
  Mindesthub.

Der Katalog liegt in hrv-core (`prototyp.wiederholungen.VORLAGEN`, Schlüssel → Vorlage). Die
App speichert nur den Schlüssel und bietet an, was hrv-core kennt; praxis_gui sieht dieselbe
Liste. Ein unbekannter Schlüssel (älteres hrv-core) gilt als „Automatisch“.

**Achsen sind gerätebezogen:** x am H10 ist nicht x an einem Garmin-Gurt. Eine Vorlage mit
fester Achse nennt sie darum je Geräteprofil; sonst gilt das gerätefreie Signal. Welche
Vorlage wofür taugt, klärt hrv-research offline an aufgezeichneten Sätzen (A4). Ben muss das
nicht Satz für Satz am Gerät ausprobieren (P126).

### 3.3 Ablage

- `Exercise.beschleunigung: SensorWahl` (neu in `core/zaehlen.py`: `zaehlen` = ``None``,
  `wdh` oder `atem`, dazu `vorlage`, `feld`, `atemphasen`, `als_dict` und `aus_dict`) mit
  **Migration 037** `exercise.acc_json TEXT NOT NULL DEFAULT '{}'`.
- Paketfeld **`beschleunigung`**, eine TOML-Tabelle, etwa
  `beschleunigung = { zaehlen = "wiederholungen", vorlage = "auto" }`. Im Drei-Wege-Abgleich ist
  es ein Feld (`core/pakete.zusammenfuehren`), Eintrag in `docs/uebungspakete.md`. Ältere Apps
  übergehen es, denn der Leser nimmt nur bekannte Schlüssel (`core/pakete._uebung_lesen`). Eine
  neue Formatversion braucht es nicht.
- Die Planübung folgt der Übung (P79). „Im Plan einstellen“ bekommt die Karte erst in A6.

### 3.4 Oberfläche

- „Übung bearbeiten“ (`views/uebung_bearbeiten.py`): die Karte steht nach „Uhr und Timer“ (Teil
  E in `docs/plan_uebung_bearbeiten.md`). Oben die Chips *Aus · Wiederholungen · Atmung*,
  darunter je nach Wahl „Bewegung“ und „Zählt in“. Rechts oben stehen „Prototyp“ und das (i)
  mit dem Hilfethema `beschleunigung` (`components/hilfe.py`). Das (i) sagt, was gezählt wird,
  welche Gurte es können, dass es ein Prototyp ist und dass die Daten auf dem Gerät bleiben.
- Übungsseite (`views/uebung_detail.py`): eine Zeile „Zählt mit dem Gurt: Wiederholungen
  (Prototyp)“, dazu das Zählprotokoll (Abschnitt 6).
- Einstellungen → Training: der Schalter **„Zählen mit dem Gurt (Prototyp)“** (P117), Vorgabe
  aus. Ohne ihn erscheinen weder die Karte noch der Knopf.

## 4. A1: Der Knopf in der laufenden Übung

### 4.1 Wann er erscheint

- Der Schalter ist an (P117), die Übung zählt (3.1), eine Messung läuft, und ihre Quelle kann
  Beschleunigung (`profil.kann(CAP_PMD_ACC)`). Sonst gibt es keinen Knopf (P118: ein Handzähler
  ohne Gurt?).
- **Name:** „Wdh. zählen“ bzw. „Atemzüge zählen“, nicht „Zählen“. Daneben steht schon „zählt“:
  ob die Zeit in den Eintrag geht (P79 D1).

### 4.2 Wo

| Ort | Was |
|---|---|
| Laufende Uhr in der Karte „Eintragen“ und als Knöpfe (`components/uhr.py`) | der Knopf neben „zählt“. Während er zählt, steht dort groß die Zahl, links **−1**, rechts **+1**, als große Flächen (beim Liegestütz liegt das Handy am Boden); klein darunter „Gurt 11 · +1 · Prototyp“ |
| Timer der Übung (`views/uebung_timer.py`, „Während“) | die Zahl unter der Zeit, −1 und +1 darunter; die Karte „Sätze“ zeigt je Satz Zeit und Wiederholungen |
| Laufleiste oben (`ui/einheit.py`) | „Liegestütz · 0:42 · 12 Wdh.“ |
| Marken-Leiste im Diagnosemodus | „Gurt 11“ live neben der Zahl der Tipps |
| Band (hrv-watch) | später (A6, P121) |

### 4.3 Ablauf

1. **Einschalten.** Vor dem Start gedrückt, ist der Zähler vorgemerkt: ▶ startet Uhr und Zähler
   zusammen. Läuft keine Uhr, startet der Knopf die Stoppuhr mit; ein Tipp heißt dann „der Satz
   beginnt“. Mitten im Lauf gedrückt, zählt er rückwirkend ab Satzbeginn, wenn der Strom schon
   lief, sonst ab jetzt (P119).
2. **Strom.** Der Messlauf schaltet die Beschleunigung ein. Vorschlag: 50 Hz und 8 g, denn
   Sprünge überschreiten 2 g; ob 50 Hz reichen, prüft hrv-research an den 200-Hz-Mitschnitten.
   Bis der Gurt Proben schickt, vergehen ein bis zwei Sekunden; so lange steht dort „Gurt
   startet …“. Läuft der Diagnosemodus, gilt seine Wahl (200 Hz). Mit P119 läuft der Strom ab
   dem Start der Uhr jeder Zählübung.
3. **Satz.** Mit der Stoppuhr ist der ganze Lauf ein Satz. Mit dem Timer ist jeder Abschnitt
   ein Satz, der zählt (`core.timer.Abschnitt.zaehlt`); Pausen zählen nicht. „Anhalten“ hält
   auch den Zähler an.
4. **Live.** Jede Sekunde zählt der Prototyp das Satzfenster neu; in Stufe A1 ist das `zaehlen`
   auf dem wachsenden Fenster. Die Zahl erscheint, sobald eine Periode erkennbar ist, meist ab
   der dritten Wiederholung (vorher „…“). Anfangs kann sie springen. Mit A5 kommt ein
   Live-Zähler, der jede Wiederholung zählt, wenn sie geschieht.
5. **Korrektur.** +1 heißt eine Wiederholung mehr, −1 eine weniger; beides wird mit Zeit und
   Satz festgehalten. Angezeigt wird Gurt plus Korrektur, nie weniger als 0. Ab A5 hängt eine
   Korrektur an der Wiederholung, die sie meint: −1 nimmt die zuletzt gezählte weg.
6. **Satzende** („Weiter“, Abschnitt fertig, „Fertig“). Der Prototyp zählt das Fenster ein
   letztes Mal bis zum Ende. Eingetragen wird, was dasteht: Gurt plus Korrektur, als
   Wiederholungen dieses Satzes im offenen Eintrag (`lauf_eintragen`: ein Wert je Satz,
   angehängt wie die Haltezeit; bei `saetze=False` zählt die Summe). Die Zeit kommt wie bisher
   dazu, wenn „zählt“ an ist. „Abbrechen“ trägt nichts ein.
7. **Danach** („Läufe heute“): „Satz 1 · 12 Wdh. (Gurt 11, +1)“. Ändern geht wie immer unter
   „Heute geleistet“; die Zeitleiste behält, was der Gurt zählte.

### 4.4 Atmung

Atemübungen bekommen denselben Ablauf mit „Atemzüge zählen“ (ab A3; das braucht
`prototyp.atemzuege`). Angezeigt werden die Atemzüge, die Rate je Minute und die Phase jetzt
(▲ ein / ▼ aus, Teil B); ±1 wirkt wie oben. Eingetragen wird nichts, denn Atemzüge sind kein
Parameter der Übung (P120). Sie stehen in der Zeitleiste und, mit Teil B, an der Messung.

## 5. A1: Technik

### 5.1 Ein Strom, mehrere Abnehmer

- Der Messlauf bekommt `acc_anfordern(zweck, rate_hz, bereich_g)` und `acc_freigeben(zweck)`,
  mit den Zwecken `diagnose` und `zaehlen`. Gestellt wird die höchste gewünschte Rate. Nach der
  letzten Freigabe läuft der Strom 30 s nach, damit zwischen zwei Sätzen nichts neu startet;
  danach geht es zurück auf den Stand von vorher (`_stroeme_zurueck`). Auch der Diagnosemodus
  nimmt diesen Weg, statt `stroeme_setzen` direkt zu rufen.
- Der Puffer füllt sich mit jedem ACC-Rahmen, nicht nur im Diagnosemodus. Je Rahmen merkt er
  sich die Rate, falls sie mitten im Satz wechselt (50 → 200 Hz). Die Zeiten der Proben kommen
  aus dem Gerätezeitstempel (`zeitstempel_ns`), die Ankunft dient nur als Anker, wie beim EKG
  (`frame_t_ns`). Statt eines Beobachters gibt es eine Liste, damit Mitschnitt und Zähler nicht
  um den Platz streiten.
- Der Simulator (`devices/simulated.py`) bekommt eine synthetische Beschleunigung:
  Wiederholungen als Sinus mit Streuung, dazu Atmung und Rauschen. Sie dient den Tests und der
  Vorschau am Rechner.

### 5.2 Der Zähl-Baustein

- `devices/zaehlen.ZaehlBaustein` (Teil `zaehlen`, ohne flet) tritt der Einheit des
  Übungslaufs bei (`Einheitslauf.beitreten`). Die Satzgrenzen sieht er nur als Ereignisse der
  Einheit, über eine neue, freiwillige Methode `beobachten(ereignisse)` am `Baustein`. Die
  Teile kennen einander also weiterhin nicht.
- `takt` holt das Fenster aus dem Puffer und ruft den Prototyp aus hrv-core. Die Laufzeit wird
  am Handy gemessen: Ziel unter 20 ms je Takt, sonst alle 2 s oder über `asyncio.to_thread`.
  Die Ereignisschleife trägt auch Bluetooth.
- Den Zustand für die Oberfläche (Zahl, Korrektur, Satz, Phase) hält
  `ui/components/zaehl_stand.py` ohne flet, wie `marken_stand`. So nimmt die Uhr am Band
  später denselben Weg, und die CI testet ihn ohne flet.
- `_satz_vergleichen` (Diagnosemodus, Stufe 8) nimmt den Wert des Bausteins, wenn er lief. Es
  gibt einen Zähler, nicht zwei.

### 5.3 Zeitleiste, Eintrag, Messdatei

- **Zeitleiste** (Vertrag `docs/plan_einheit.md` §4, **zuerst** dort eintragen): Teil und
  Quelle `zaehlen` mit zwei neuen Arten. `zaehlung` steht einmal je Satz, mit `satz`, `art`
  (wdh oder atem), `gurt`, `korrektur`, `wert`, `feld`, `vorlage`, `zeiten_s` (die gezählten
  Umkehrpunkte) und `prototyp` (Modul und hrv-core-Version). `korrektur` kommt von der Quelle
  `person`, mit `delta` (±1) und `satz`. Messwerte stehen dort nicht, nur ein Ergebnis mit
  Zeiten, wie bei `km`.
- **Eintrag:** `core/zaehlen_eintrag.py` (wie `core/timer_eintrag.py`) liest die Wiederholungen
  je Satz aus den `zaehlung`-Ereignissen; `lauf_eintragen` nimmt `reps` mit.
- **Messdatei:** nichts Neues. Die Notiz zum Satz entsteht wie bisher beim Eintragen. Eine Marke
  je Wiederholung kommt **nicht** in die Notizen, wie im Diagnosemodus.
- **Diagnosemodus:** zusätzlich stehen `zaehlung` und `korrektur` als Kontextzeilen im
  Mitschnitt. Damit liegen Gurt, Korrektur, die Tipps der Leiste und die Rohdaten auf einer
  Achse; hrv-research liest sie mit `trainingsapp_diagnose.py`.
- Der Forschungsexport `einheit-v1` (`docs/plan_einheit.md` §8) trägt die Zeitleiste und damit
  die Zählungen mit.

## 6. A2: Wie genau zählt der Gurt? (Zählprotokoll)

- Die Übungsseite bekommt den Abschnitt „Zähler (Prototyp)“. Er listet die letzten Sätze mit
  Tag, Vorlage, Gurt, Korrektur und eingetragenem Wert; darüber steht „exakt n von m ·
  höchstens 1 daneben k von m“. Das ist eine Aussage über den Zähler, nicht über die Person.
- **Die Wahrheit ist der eingetragene Wert.** Sie ist nur so gut wie die Korrektur: Wer nicht
  mitzählt, lässt den Gurt genauer aussehen, als er ist (P122).
- Teilen: das Protokoll als CSV (Übung, Zeit, Vorlage, Gurt, Korrektur, eingetragen; kein Ort)
  über „Teilen“, für das Einlesen in hrv-research.
- Rohdaten für bessere Zähler liefert der Diagnosemodus ohnehin (Mitschnitt). Im Alltag kommt
  mit A4 das Beiwerk `_acc.json` dazu. Dann wird jeder korrigierte Satz ein Lernbeispiel
  (Konzept „Kreislauf“ in hrv-research).

## 7. Teil B: Ein- und Ausatmung in der HRV

### 7.1 Worum es geht

Beim Einatmen schlägt das Herz schneller, beim Ausatmen langsamer (respiratorische
Sinusarrhythmie, RSA). Wer weiß, wann eingeatmet wird, kann die HRV je Atemzug lesen statt nur
über Fenster:

| Größe | Was | Wofür |
|---|---|---|
| Rate und Gleichmäßigkeit | Atemzüge je Minute, Streuung ihrer Dauer | Einordnung jeder Kennzahl; wie gut ein Takt eingehalten wird |
| Ein:Aus | Dauer des Einatmens zu der des Ausatmens | RMSSD und SD1 ändern sich damit |
| Atemspanne je Atemzug | Gipfel–Tal: höchste minus tiefste Herzfrequenz (bpm) bzw. längster minus kürzester RR (ms) im Atemzug, nach Trendbereinigung | die anschaulichste Größe der RSA; sie braucht Atemgrenzen, und die liefert der Gurt |
| Phasenlage | Zeit (oder Winkel) vom Ende des Einatmens bis zum Gipfel der Herzfrequenz | wandert mit der Dauer des Atemzugs; bei Resonanzatmung das wichtigste Kriterium |
| RR je Phase | mittlerer RR beim Ein- und beim Ausatmen | die Differenz als einfache Zahl |
| Frequenzmaße | Atmung unter 9/min (0,15 Hz) liegt im LF-Band | HF-Power und LF/HF dann nicht ausweisen; die LF-Spitze ist dann Atmung |

Grundlagen stehen in hrv-research `literatur/atmung/06_atmung_hrv.md`: §1 (wie man die RSA
beziffert), §5 (Resonanzfrequenz), §8 (Kandidaten für hrv-core).

**„Um die HRV zu verbessern“** lässt zwei Lesarten zu (P124):

- **(a) Die Auswertung verbessern:** genauer und besser deutbar, mit den Größen oben, der
  Einordnung der Frequenzmaße und dem Protokollfeld „Atmung“. Das ist der Kern dieses Teils.
- **(b) Die eigene HRV mit der Atmung beeinflussen (Biofeedback):** Phasen und Herzfrequenz
  live zu zeigen ist beschreibend und geht. Eine Atemfrequenz *aus Messwerten auszuwählen*
  geht nicht ohne Weiteres. Das Resonanzprotokoll etwa misst fünf Stufen, und die mit der
  größten Atemspanne gewinnt. Das ist eine Handlungsempfehlung aus Messwerten: in Solo
  gesperrt wie `physiologische_steuerung`, in Praxis nur mit diesem Schalter.

### 7.2 Woher die Phasen kommen

| Quelle | Wie | Güte |
|---|---|---|
| **Takt** (Soll) | Timer der Atemübung mit Abschnitten „Ein“ und „Aus“ und Klang | exakt, solange die Person folgt; aber Soll, nicht Ist |
| **Gurt** (Ist) | Wendepunkte der Atemwelle aus der Beschleunigung (K3 mit der Prüfung aus K2, hrv-research). Das Vorzeichen der Achse („was ist ein?“) kommt aus dem Takt oder aus der RSA | gut in Ruhe; bei Bewegung keine Zahl |
| Herz | Phasen aus der RSA allein | nur zur Anzeige; für Phasenlage und Atemspanne wäre es ein Zirkelschluss |
| später EKG | Atmung aus dem EKG (EDR, Entscheidung 1 in hrv-research) | offen |

Mit Takt **und** Gurt zeigt die Auswertung Soll gegen Ist, also wie genau dem Takt gefolgt
wurde. Auch das ist beschreibend.

**Stolperstein:** Timer-Abschnitte unter 5 s bekommen keine Marke
(`core.einheit.MIN_MARKE_S`, gegen ein versehentliches „Weiter“). Ein Atemtakt von 4 s ein und
6 s aus fiele damit weg. Darum geht der Takt als eine Angabe in die Messdatei: eine Spur
`atemtakt` mit Beginn, Ein-Sekunden, Aus-Sekunden und Runden, Halte-Abschnitte eingeschlossen.
Eine Marke je Abschnitt gibt es dafür nicht. Der Vertrag `docs/kompatibilitaet.md` §4 kommt
zuerst.

### 7.3 Anzeige

- **Live** (Timer der Atemübung, Live-Vollbild): die Herzfrequenz der letzten 60 s mit
  hinterlegtem Einatmen, die Phase jetzt (▲ ein / ▼ aus), die Atemspanne des letzten Atemzugs
  und die Rate. Nur Zahlen und Kurven, keine Wertung wie „gut“ oder „kohärent“.
- **Auswertung** (`views/messung_detail.py`): eine Ebene „Atmung“ über dem Tachogramm, wie die
  Marken-Ebene des Diagnosemodus. Das Einatmen ist schattiert, die Taktgrenzen sind feine
  Linien. Dazu je Abschnitt oder Übung eine Karte „Atmung (Prototyp)“ mit den Größen aus 7.1
  und der Quelle (Takt · Gurt · Herz).
- **Frequenzmaße:** Liegt die Rate (aus Gurt oder Takt) unter 9/min, steht bei HF-Power und
  LF/HF der Hinweis „Atmung im LF-Band“. Welche Quelle gilt, wenn die Atmung aus den RR-Abständen
  und die vom Gurt sich widersprechen, entscheidet hrv-research. Danach geht die Regel auf dem
  Weg aus hrv-research `docs/UEBERNAHME.md` nach hrv-core.

### 7.4 Ablage

- **Nichts Berechnetes wird gespeichert** (Prototyp-Regel). Phasen und Atem-Größen entstehen
  beim Anzeigen aus den Rohdaten: dem Beiwerk `_acc.json` (Abschnitt 8), den RR-Abständen der
  Messdatei und der Spur `atemtakt`. Wird der Prototyp besser, werden auch alte Messungen
  besser ausgewertet.
- Ohne Beiwerk (alte Messungen, Gurt ohne Beschleunigung) gibt es nur Takt und Herz.
- **Protokollfeld „Atmung“** an der Messung (spontan · getaktet mit Rate · Übung), automatisch
  aus der Übung und dem Takt. Ohne diese Angabe sind HF-Power, LF/HF und DFA α1 zwischen
  Messungen nicht vergleichbar. Es wird eine Erweiterung von `raw-v1`, die praxis_gui mitliest
  (P125); der Vertrag kommt zuerst.

### 7.5 hrv-core

- `prototyp.atemzuege` (neu) findet Atemzüge und Phasen in der Beschleunigung:
  `atemzuege(xyz, rate_hz, t0_s, *, rr=None, takt=None)` liefert
  `Atemzuege(ein_s, aus_s, rate_pro_min, gleichmaessigkeit, gueltig, gruende, art="prototyp")`.
  Dazu kommt eine Live-Fassung für die Anzeige.
- `prototyp.atem_hrv` (neu) rechnet aus Phasen und RR-Abständen je Atemzug Atemspanne,
  Phasenlage, Ein:Aus und RR je Phase. Bewertet wird nichts.
- Der Eingang folgt den Regeln in `hrv_core.prototyp`: zwei Sitzungen, die nicht zum
  Einstellen dienten, und ein Befund in hrv-research. Soll eine Größe zur Kennzahl werden,
  geht sie nach hrv-research `docs/UEBERNAHME.md`, mit Golden Master und `ALGO_VERSION`.

## 8. A4: Beiwerk `acc-v1`, die Beschleunigung neben der Messung

- `sensor_<ts>_acc.json` liegt neben der Messdatei und ist gebaut wie `_ecg.json`
  (`hrv_core.ekg`): `sample_rate_hz`, `bereich_g`, `mg[]` (x, y, z hintereinander),
  `frame_offsets[]`, `frame_sample_counts[]`, `frame_t_ns[]`, `t_wall_start_s`, `gaps[]` (der
  Strom ist zwischen den Sätzen aus, das ist eine Lücke), dazu Gerätemodell und Achsenangabe.
  Ein Journal `.jsonl` neben dem Backup schützt gegen Abstürze.
- Geschrieben wird nur in Zählfenstern und während Atemübungen (P123). Bei 50 Hz sind das grob
  2–3 MB je Stunde Strom.
- Das Format gehört nach hrv-core, als stabiles Modul und nicht als Prototyp, denn es ist ein
  Rohdatum. `ist_messdatei` kennt die Endung, `deid` behält die Felder. **Zuerst** kommen die
  Einträge in `docs/kompatibilitaet.md` (§15) und in `docs/formate.md` von hrv-core.
- Export und Backup wie beim EKG-Beiwerk. Nie Ort, nie Magnetometer (Richtung).

## 9. praxis_gui

praxis_gui misst Patienten mit dem H10 (PySide6, der Expertenmodus ist sichtbar). Gleich bleibt
alles, was in hrv-core liegt: PMD-Dekoder, Format `acc-v1`, Zähler- und Atem-Prototypen,
Vorlagen und die Kennzeichnung „Prototyp“. Selbst baut praxis_gui, in einer eigenen Sitzung im
Repo praxis_gui (hier nicht erreichbar):

- den ACC-Strom in seiner Polar-Anbindung,
- die Atem-Ebene über der Kurve,
- Knopf und ±1 nach diesem Muster, wenn dort Übungen mit Wiederholungen laufen.

Für Patientendaten gilt Regel 2 von hrv-research: Kein Verfahren wird in einer Sitzung an
Patientenmessungen entwickelt; Läufe darauf startet Ben selbst.

## 10. Recht und Datenschutz

- Zählen und Atemphasen sind **beschreibend**: Zahlen, kein Rat, in beiden Editionen. Nichts
  wird aus Messwerten gewertet („gut“, „kohärent“), nichts empfohlen („langsamer atmen“, „noch
  zwei Wiederholungen“); siehe `docs/recht/00_zweckbestimmung.md`.
- Das Resonanzprotokoll wählt eine Atemfrequenz aus Messwerten und ist damit eine
  Handlungsempfehlung: in Solo gesperrt (`physiologische_steuerung`), in Praxis nur mit dem
  Schalter (P124).
- Beschleunigung außerhalb des Diagnosemodus (A4) ist eine neue Datenart im Alltag. Sie braucht
  Nachträge in `docs/recht/40_toms.md` und `10_verarbeitungsverzeichnis.md` sowie einen Hinweis in
  den Einstellungen. Sie bleibt auf dem Gerät, ohne Netzverbindung.
- „Prototyp“ steht an jeder Zahl, die ein Prototyp liefert.

## 11. Stufen

| Stufe | Inhalt | Repos | Umfang |
|---|---|---|---|
| **A1** | Schalter; Karte „Beschleunigungssensor“ (Migration 037, Paketfeld); Strom mit mehreren Abnehmern; Simulator mit Beschleunigung; Zähl-Baustein mit dem vorhandenen Prototyp; Knopf mit −1/+1 an Uhr und Timer; Wiederholungen je Satz in den Eintrag; Zeitleiste | trainingsapp | L |
| **A2** | Zählprotokoll an der Übung, als CSV teilbar; Live-Zahl in der Marken-Leiste | trainingsapp | S |
| **A3** | Atemzüge: K3 mit Prüfung → `prototyp.atemzuege`; „Atemzüge zählen“ | hrv-research → hrv-core → trainingsapp | M |
| **A4** | Beiwerk `acc-v1`: Format, Schreiber mit Journal, Einlesen in hrv-research | hrv-core, trainingsapp, hrv-research | M |
| **B1** | Spur `atemtakt`; Phasen aus Takt und Gurt; Ebene „Atmung“ in der Auswertung; Live-Anzeige | trainingsapp, hrv-core | M |
| **B2** | Atem-HRV (`prototyp.atem_hrv`); Protokollfeld „Atmung“; Hinweis „Atmung im LF-Band“ mit der Rate des Gurts | hrv-research → hrv-core → trainingsapp | M |
| **A5** | Live-Zähler, der jede Wiederholung zählt, wenn sie geschieht; Vorlagen; Umkehrpunkt | hrv-research → hrv-core → trainingsapp | L |
| **A6** | Band (Seite „Zählen“); „Im Plan einstellen“; praxis_gui | hrv-watch, trainingsapp, praxis_gui | M |

A1 und A2 brauchen nichts Neues aus hrv-core. Damit lässt sich sofort im Alltag prüfen, wie gut
der Gurt Wiederholungen zählt. Jede Stufe endet mit Tests (ohne flet, wo es geht), Doku und,
wo nötig, einer APK.

## 12. Fragen an Ben (P117–P126)

| # | Frage | Vorschlag |
|---|---|---|
| P117 | Ein Schalter „Zählen mit dem Gurt (Prototyp)“ in den Einstellungen, oder sind Karte und Knopf immer da? | Schalter, Vorgabe aus (die App ist öffentlich, der Zähler ein Prototyp) |
| P118 | Ohne Gurt mit Beschleunigung: kein Knopf, oder ein Handzähler (nur +1/−1)? | in A1 kein Knopf; ein Handzähler später, wenn gewünscht |
| P119 | Startet der Knopf ohne laufende Uhr die Stoppuhr mit? Und mitten im Satz: rückwirkend ab Satzbeginn (dann läuft der Strom ab dem Start der Uhr jeder Zählübung) oder ab jetzt? | ja; rückwirkend |
| P120 | Atemzüge eintragen (als eigener Parameter), oder nur anzeigen und an der Messung festhalten? | nur anzeigen und an der Messung |
| P121 | Am Band eine Seite „Zählen“ mit der Zahl, und ⏯ ist auf dieser Seite +1 (sonst eine Marke wie heute, P113)? | ja, in A6 |
| P122 | Gilt jeder eingetragene Wert als nachgezählt, oder brauchst du am Satzende ein „✓ stimmt“? | kein Extra-Tipp; beim Testen zählst du mit und korrigierst |
| P123 | Die Beschleunigung im Alltag mitschreiben (Beiwerk `_acc.json`): nur in Zählfenstern und Atemübungen, immer bei laufendem Strom, oder nie (nur im Diagnosemodus)? | nur in Zählfenstern und Atemübungen |
| P124 | „Um die HRV zu verbessern“: die Auswertung (B1, B2), oder auch Biofeedback und Resonanzatmung? | beides beschreibend; das Resonanzprotokoll nur in Praxis mit Schalter, später |
| P125 | Ein Protokollfeld „Atmung“ (spontan · getaktet · Übung) an jeder HRV-Messung, als Erweiterung von `raw-v1`? | ja, automatisch aus Übung und Takt |
| P126 | Vorlagen: schon in A1 feste Achsen oder Neigung zum Ausprobieren wählbar, oder nur „Automatisch“, und hrv-research vergleicht die Signale offline? | nur „Automatisch“; die Vorlagen kommen mit A5 aus hrv-research |
