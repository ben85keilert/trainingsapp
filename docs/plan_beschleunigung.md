# Plan: Beschleunigungssensor in Übungen — Wiederholungen zählen, Atmung erfassen, Ein- und Ausatmung in der HRV

Stand 4.11.2026: **Entwurf mit Bens Entscheidungen** — Ben: „Plane das beides durch“. P117–P120
und P122–P126 sind entschieden (Abschnitt 12), offen ist nur P121 (das Band). Die Verfahren
entstehen in hrv-research (dort `beschleunigung/docs/PLAN_ZAEHLEN_ATEMPHASEN.md`); hier steht,
was die Apps bauen. Neu daraus als eigene Aufgabe: der **Taktgeber** im Timer (Abschnitt 7.6,
`docs/offene_fragen.md` A18).

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

Und zum Knopf: „Wenn ein Gerät einen Beschleunigungssensor hat, soll die Wiederholung damit
gemessen werden. Das ist der Knopf. +/-1 ist die Korrektur dafür.“

## 0. Kurzfassung

- **Teil A: Zählen.** Jede Übung bekommt in „Übung bearbeiten“ die Karte
  **„Beschleunigungssensor“** mit zwei kleinen Schaltern: **Wiederholungen** (bei Übungen mit
  Wiederholungen) und **Atmung** (in jeder Übung, denn jede kann eine Atemkomponente haben). Hat
  das verbundene Gerät einen Beschleunigungssensor (heute H10 und Verity Sense), steht an der
  Übung der Knopf **„Wdh. zählen“**. Er misst die Wiederholungen mit diesem Sensor; **−1** und
  **+1** sind die Korrektur dafür. Das Zählen läuft **unabhängig von der Uhr** als eigener Dienst
  in der Infoleiste oben. Es beginnt mit dem Tipp und endet mit „Fertig“, mit dem Abschluss der
  Übung, mit einem Abbruch, beim Start einer anderen Übung oder wenn sich nichts mehr bewegt.
  Der Satzwert geht in den offenen Eintrag. Entweder zählt die Person oder der Sensor; beides
  zugleich ist Prüfung im Diagnosemodus.
- **Teil B: Ein- und Ausatmung in der HRV.** Ist „Atmung“ an, erfasst der Sensor die Atemzüge
  mit ihren Phasen. Die Auswertung zeigt sie als Abbildung über der Herzfrequenz, dazu je Atemzug
  Atemspanne, Phasenlage, Ein:Aus und Rate. DFA α1, LF/HF und die übrigen Kennzahlen werden im
  Licht der Atmung eingeordnet. Live gibt es Biofeedback, beschreibend. Ins Tagebuch kommt die
  Atmung erst, wenn klar ist, was daran wichtig ist.
- **Smart statt alles aufzeichnen** (Ben: „Brute force alles aufzeichnen ist für die
  Entwicklung“). Im Alltag speichert die App keine Rohdaten der Beschleunigung. Sie rechnet live
  und behält nur die Ergebnisse: Wiederholungen mit ihren Zeiten, Korrekturen und Atemphasen,
  gekennzeichnet als Prototyp. Rohdaten gibt es nur im Diagnosemodus.
- **Arbeitsteilung.** Die Verfahren entstehen in hrv-research und kommen als **Prototyp** nach
  `hrv_core.prototyp`. Die Apps rufen sie nur auf; praxis_gui bekommt dieselben Funktionen und
  Formate.
- **Zuerst kommt Stufe A1:** Karte, Knopf mit ±1, Dienst in der Leiste und Eintrag. Sie nutzt den
  vorhandenen Zähler-Prototyp (`hrv_core.prototyp.wiederholungen`, hrv-core 0.8.0).

## 1. Was schon steht

| Baustein | Stand | Wo |
|---|---|---|
| Beschleunigung des Geräts | PMD-Strom (Vorgabe 200 Hz, 8 g), eingeschaltet nur im Diagnosemodus; ein Beobachter (`acc_beobachter`), Puffer für gut 10 min | `devices/polar.py` (`stroeme_setzen`), `devices/messlauf.py` (`_acc_puffer`, `_acc_fenster`), Dekoder `hrv_core.geraete.pmd` |
| Fähigkeit je Gerät | `CAP_PMD_ACC` bei H10 und Verity Sense; im Treiber von hrv-core der Strom `acc` (H10 25–200 Hz, erprobt; Verity Sense 52 Hz, nicht erprobt) | `devices/profiles.py`, `hrv_core.geraete.treiber` |
| Zähler-Prototyp | `wiederholungen.zaehlen(xyz, rate_hz, t0_s)` → `Zaehlung(anzahl, zeiten_s, periode_s, gleichmaessigkeit, art="prototyp")`; zählt einen ganzen Satz | `hrv_core.prototyp.wiederholungen` (0.8.0) |
| Vergleich nach dem Satz | im Diagnosemodus „Marken · Zähler (Prototyp) · eingetragen“ | `Messlauf._satz_vergleichen`, `components/marken_leiste.py` |
| Marken als Wahrheit | ein Tipp je Wiederholung bzw. Atemzug, ↶, ⏯ an der Uhr; der Zustand liegt ohne flet | `components/marken_stand.py`, `core/diagnose.py` |
| Einheit und Dienste | Teile (HRV, Timer, GPS) laufen gemeinsam oder einzeln; Infoleiste und Laufleiste zeigen, was bereitsteht und läuft, auch „Läuft außerdem: …“ | `devices/einheit.py`, `core/einheit.py`, `ui/einheit.py`, `components/startleiste.py` |
| Zeit in den Eintrag | die Zeitleiste ist die Provenienz; die Zeit kommt als Haltezeit bzw. Zeit in den offenen Eintrag; ein abgebrochener Lauf bleibt unter „Läufe heute“ und lässt sich dort eintragen | `core/timer_eintrag.py`, `SessionRepo.lauf_eintragen`, `views/uebung_timer.py` |
| Laufende Uhr | als Zeile in der Karte „Eintragen“ oder als Knöpfe; Timer-Ansicht „Während“ | `components/uhr.py`, `views/uebung_timer.py` |
| Wiederholungen | ein Feld der Art `reps` (auch `reps_2`, P106); ohne Sätze (`saetze=False`) eine Liste, angezeigt als Summe | `core.diagnose.hat_wiederholungen`, `core.result_spec` |
| Atemübungen | Typ „Atmung“ (`Exercise.typen`; im Paket „Standard“ vier Übungen) | `core/models.TYPEN`, `data/seed/standard.toml` |
| Atemfrequenz | aus den RR-Abständen mit Prüfkette (stabil); aus der Beschleunigung (K1–K4) bisher nur in hrv-research | `hrv_core.atmung`; hrv-research `hrv_research.beschleunigung.brustgurt_atem` |
| Taktgeber | **fehlt.** Timer-Abschnitte haben Dauer und Klang, aber keinen Atemtakt; Abschnitte unter 5 s bekommen keine Marke | `core/timer.py`, `core.einheit.MIN_MARKE_S` |
| Beiwerk als Vorbild | `sensor_<ts>_ecg.json` neben der Messdatei, mit Journal gegen Absturz | `hrv_core.ekg` |

## 2. Wer was macht

| Repo | Aufgabe |
|---|---|
| hrv-research (privat) | Verfahren entwickeln und prüfen: Live-Zählen, Vorlagen, Atemzüge und Atemphasen, Atem-HRV, später die Atmung je Wiederholung. Die Wahrheit kommt aus Video, Marken und Metronom; die Rohdaten aus dem Diagnosemodus und der Brustgurt-Diagnose. Plan dort: `beschleunigung/docs/PLAN_ZAEHLEN_ATEMPHASEN.md`. |
| hrv-core (öffentlich) | Prototypen (`prototyp.wiederholungen` erweitert, `prototyp.atemzuege` und `prototyp.atem_hrv` neu), der Katalog der Vorlagen und das Ergebnisformat `atem-v1` (Atemphasen neben der Messdatei). Nur numpy. |
| trainingsapp | Karte an der Übung, Strom, Zähl-Dienst, Knopf, Eintrag, Atem-Ebene, Taktgeber. Keine Rechenlogik in `ui/`. |
| hrv-watch | später die Seite „Zählen“ am Band (A6, P121 offen) |
| praxis_gui | dieselben Funktionen und Formate aus hrv-core; die Bedienung baut es selbst (Abschnitt 9) |

## 3. A1: Die Karte „Beschleunigungssensor“ an der Übung

### 3.1 Was man einstellt

Jede Übung hat die Karte, nicht nur Übungen mit Wiederholungen oder vom Typ „Atmung“ (P117,
Ben: „da jede Übung eine Atemkomponente haben kann“).

| Einstellung | Werte | Vorgabe |
|---|---|---|
| **Wiederholungen** (kleiner Schalter) | an · aus; nur bei einem Feld der Art `reps` | an, wenn es ein solches Feld gibt |
| **Atmung** (kleiner Schalter) | an · aus; in jeder Übung | an bei Typ „Atmung“, sonst aus |
| Bewegung (nur Wiederholungen) | „Automatisch“ (Hauptachse, wie der Prototyp heute); Vorlagen später (P126) | Automatisch |
| Zählt in (nur bei mehreren Wdh.-Feldern) | `reps`, `reps_2` … unter den Namen ihrer Karten | das erste Wdh.-Feld |

Sind beide Schalter aus, gibt es an dieser Übung keinen Knopf. Ohne Feld `reps` ist
„Wiederholungen“ ausgegraut, und das (i) erklärt warum.

**Atmung bei bewegten Übungen** misst der Prototyp heute nur in den ruhigen Stücken, denn die
Bewegung überdeckt die Atemwelle. In den Sätzen bleibt eine Lücke statt einer falschen Zahl. Die
Atmung je Wiederholung zu erfassen und zu vergleichen, wie geatmet wurde, ist eine spätere
Forschungsfrage (Ben: „Später wird es interessant werden, auf die Wiederholung die Atmung zu
tracken und herauszufinden, ob man feststellen kann, welche Atmung die beste ist“;
hrv-research Konzept C3). Für die App gilt dabei Abschnitt 10.

### 3.2 Vorlagen (später)

Ben: „Kniebeugen für x-Achse, Liegestützen Neigung zy…“ Zuerst gibt es nur „Automatisch“
(P126). Eine Vorlage ist später eine Signalwahl mit Parametern, kein Code in der App:

- **Signal:** Hauptachse (gerätefrei), Betrag, eine feste Achse (x, y, z) oder die Neigung in
  einer Ebene (z–y, z–x). Die Neigung zählt gegen die Lage zu Satzbeginn, damit der Sitz des
  Sensors weniger stört.
- **Zähltyp** (Konzept B2 in hrv-research): periodisch oder als Zustandsfolge (Burpee). Dazu
  kommen die erwartete Dauer einer Wiederholung, der Umkehrpunkt (oben oder unten) und der
  Mindesthub.

Der Katalog liegt in hrv-core (`prototyp.wiederholungen.VORLAGEN`, Schlüssel → Vorlage). Die
App speichert nur den Schlüssel und bietet an, was hrv-core kennt; praxis_gui sieht dieselbe
Liste. Ein unbekannter Schlüssel (älteres hrv-core) gilt als „Automatisch“.

**Achsen sind gerätebezogen:** x am H10 ist nicht x an einem Garmin-Gurt. Eine Vorlage mit
fester Achse nennt sie darum je Geräteprofil; sonst gilt das gerätefreie Signal. Welche Vorlage
wofür taugt, klärt hrv-research offline an den Rohdaten aus dem Diagnosemodus.

### 3.3 Ablage

- `Exercise.beschleunigung: SensorWahl` (neu in `core/zaehlen.py`: `wiederholungen` und
  `atmung` als ``bool | None`` mit ``None`` = Vorgabe aus der Übung, dazu `vorlage`, `feld`,
  `als_dict` und `aus_dict`), mit **Migration 037**
  `exercise.acc_json TEXT NOT NULL DEFAULT '{}'`.
- Paketfeld **`beschleunigung`**, eine TOML-Tabelle, etwa
  `beschleunigung = { wiederholungen = true, atmung = true, vorlage = "auto" }`. Im
  Drei-Wege-Abgleich ist es ein Feld (`core/pakete.zusammenfuehren`), Eintrag in
  `docs/uebungspakete.md`. Ältere Apps übergehen es, denn der Leser nimmt nur bekannte
  Schlüssel (`core/pakete._uebung_lesen`). Eine neue Formatversion braucht es nicht.
- Die Planübung folgt der Übung (P79). „Im Plan einstellen“ bekommt die Karte erst in A6.

### 3.4 Oberfläche

- „Übung bearbeiten“ (`views/uebung_bearbeiten.py`): die Karte steht nach „Uhr und Timer“ (Teil
  E in `docs/plan_uebung_bearbeiten.md`), mit den kleinen Schaltern „Wiederholungen“ und
  „Atmung“, darunter bei Wiederholungen „Bewegung“ und „Zählt in“. Rechts oben stehen
  „Prototyp“ und das (i) mit dem Hilfethema `beschleunigung` (`components/hilfe.py`). Das (i)
  sagt, was gemessen wird, welche Geräte es können, dass es ein Prototyp ist und dass im Alltag
  nur Ergebnisse gespeichert werden.
- Übungsseite (`views/uebung_detail.py`): eine Zeile „Beschleunigungssensor: Wiederholungen ·
  Atmung (Prototyp)“.
- Einen Schalter für alle Übungen in den Einstellungen gibt es nicht; die Schalter sitzen an
  jeder Übung.

## 4. A1: Der Knopf und das Zählen

### 4.1 Wann der Knopf erscheint

- **Der Knopf ist die Messung mit dem Beschleunigungssensor.** Er erscheint, wenn das verbundene
  Gerät einen hat und an der Übung „Wiederholungen“ oder „Atmung“ an ist. Heute heißt das
  `profil.kann(CAP_PMD_ACC)`: H10 und Verity Sense. Künftig gilt es für jedes Gerät, dessen
  Treiber in hrv-core einen Strom `acc` nennt. Bei der Verity Sense ist der Strom nur im
  Treiber beschrieben, am Gerät aber noch nicht erprobt; dort ist der erste gezählte Satz
  zugleich die Probe.
- Verbunden genügt; eine laufende Aufnahme ist keine Bedingung. Ohne Aufnahme fehlen nur die
  Notiz zum Satz und die Atemphasen an der Messdatei.
- **±1 ist nur die Korrektur** dieser Messung, kein Handzähler. Ohne Beschleunigungssensor gibt
  es weder Knopf noch ±1 (P118).
- **Name:** „Wdh. zählen“, bei Übungen nur mit Atmung „Atmung erfassen“, mit beidem „Wdh. zählen
  · Atmung“. Nicht bloß „Zählen“, denn neben der Uhr steht schon „zählt“: ob die Zeit in den
  Eintrag geht (P79 D1).

### 4.2 Wo

| Ort | Was |
|---|---|
| Karte „Eintragen“ der Übung (`views/plan.py`, Übungsseite) | eine eigene Zeile mit dem Knopf, unabhängig von der Uhr (P119), direkt unter der Zeile der Uhr. Während gezählt wird, steht dort groß die Zahl, links **−1**, rechts **+1**, als große Flächen (beim Liegestütz liegt das Handy am Boden); klein darunter „Sensor 11 · +1 · Prototyp“; dazu „Fertig“ und „Abbrechen“ |
| Infoleiste und Laufleiste oben (`components/startleiste.py`, `ui/einheit.py`) | das Zählen als eigener Dienst neben HRV, Timer und GPS: „Zählen · Kniebeuge · 12“ (P119). Antippen führt zur Übung zurück |
| Laufende Uhr und Timer der Übung (`components/uhr.py`, `views/uebung_timer.py`) | laufen Uhr und Zählen zugleich, steht die Zahl mit ±1 auch dort; die Karte „Sätze“ zeigt je Satz Zeit und Wiederholungen |
| Marken-Leiste im Diagnosemodus | „Sensor 11“ live neben der Zahl der Tipps (Prüfung, Abschnitt 6) |
| Band (hrv-watch) | später (A6, P121 offen) |

### 4.3 Ablauf

1. **Beginn.** Der Tipp startet das Zählen, und erst ab dann läuft der Sensor (P119: „Akku hat
   in diesem Fall Prio“). Rückwirkend wird nichts gezählt. Eine Uhr braucht es nicht; läuft eine
   oder startet sie später, laufen beide nebeneinander.
2. **Strom.** Der Messlauf schaltet die Beschleunigung mit dem Tipp ein und mit dem Ende des
   Zählens sofort wieder aus. Die Rate ist die kleinste ab 50 Hz, die der Treiber anbietet (H10
   50 Hz, Verity Sense 52 Hz), der Bereich 8 g, denn Sprünge überschreiten 2 g. Ob 50 Hz
   reichen, prüft hrv-research an den 200-Hz-Mitschnitten. Bis das Gerät Proben schickt,
   vergehen ein bis zwei Sekunden; so lange steht dort „Sensor startet …“. Was in dieser Zeit
   geschieht, korrigiert ±1. Läuft der Diagnosemodus, gilt seine Wahl (200 Hz).
3. **Satz.** Ein Zähllauf ist ein Satz. Läuft dazu ein Timer, ist jeder Abschnitt, der zählt
   (`core.timer.Abschnitt.zaehlt`), ein eigener Satz; Pausen zählen nicht. „Anhalten“ der Uhr
   hält auch das Zählen an.
4. **Live.** Jede Sekunde zählt der Prototyp das Satzfenster neu; in Stufe A1 ist das `zaehlen`
   auf dem wachsenden Fenster. Die Zahl erscheint, sobald eine Periode erkennbar ist, meist ab
   der dritten Wiederholung (vorher „…“). Anfangs kann sie springen. Mit A5 kommt ein
   Live-Zähler, der jede Wiederholung zählt, wenn sie geschieht.
5. **Korrektur.** +1 heißt eine Wiederholung mehr, −1 eine weniger; beides wird mit Zeit und
   Satz festgehalten. Angezeigt wird Sensor plus Korrektur, nie weniger als 0. Ab A5 hängt eine
   Korrektur an der Wiederholung, die sie meint: −1 nimmt die zuletzt gezählte weg.
6. **Ende** (P119). Wechselt man nur die Ansicht, etwa zu „Messung“, um etwas nachzusehen, zählt
   es weiter; die Leiste zeigt es. Sonst gilt:

   | Was geschieht | Folge |
   |---|---|
   | „Fertig“ am Zähler; die Übung wird abgehakt („Gemacht“); „Fertig“ der Uhr; der Timer ist durch (auch mit „automatisch weiter“ im Plan) | **abgeschlossen:** der Satzwert (Sensor plus Korrektur) geht als Wiederholungen des Satzes in den offenen Eintrag (`lauf_eintragen`: ein Wert je Satz, angehängt wie die Haltezeit; bei `saetze=False` zählt die Summe), die Zeit wie bisher, wenn „zählt“ an ist |
   | „Abbrechen“ | **abgebrochen:** nichts wird eingetragen; der Lauf bleibt mit seiner Zahl unter „Läufe heute“ und lässt sich dort mit einem Tipp eintragen, wie bei der Uhr |
   | Eine andere Übung startet (ihr Zählen, ihre Uhr, ihr Timer) | abgebrochen wie oben; dazu 5 s lang die Meldung „Kniebeuge · 12 Wdh. nicht eingetragen“ mit „Eintragen“ |
   | **Keine Bewegung:** 60 s ohne gezählte Wiederholung (Ben: „evtl. mit Timer“) | abgebrochen wie oben. Die 60 s sind ein Startwert; reicht das bei langen Pausen im Satz nicht, wird er einstellbar |
   | Nur Atmung: das Gerät liefert 2 min lang keinen erkennbaren Atemzug (abgelegt, verrutscht) | abgebrochen wie oben. „Keine Bewegung“ gilt hier nicht, denn bei einer Atemübung ist Stille gewollt |

7. **Danach** („Läufe heute“): „Satz 1 · 12 Wdh. (Sensor 11, +1)“. Ändern geht wie immer unter
   „Heute geleistet“; die Zeitleiste behält, was der Sensor zählte.

### 4.4 Entweder die Person oder der Sensor

Ben: „Es ist ein entweder oder. Entweder zähle ich, oder der Sensor. Beides gleichzeitig ist nur
Überprüfung und Debugging“ (P122).

- Ohne Knopf zählt die Person wie heute (Chips, „Wie geplant“).
- Mit Knopf zählt der Sensor; die Person korrigiert höchstens mit ±1. Der Satzwert kommt aus der
  Messung, und die App tut nicht so, als hätte jemand nachgezählt.
- Beides zugleich gibt es nur zum Prüfen, im Diagnosemodus (Abschnitt 6).

### 4.5 Atmung

Ist „Atmung“ an, erfasst derselbe Dienst die Atemzüge (ab A3; das braucht
`prototyp.atemzuege`). Angezeigt werden die Atemzüge, die Rate je Minute und die Phase jetzt
(▲ ein / ▼ aus, Teil B); ±1 korrigiert die Zahl der Atemzüge, wenn nur „Atmung“ an ist.

- **Festgehalten wird die Atmung an der Messung, nicht im Tagebuch** (P120): als Abbildung in den
  Messaufzeichnungen (Teil B, 7.3). Ins Tagebuch kommt sie erst, wenn klar ist, was an der
  Atmung wichtig ist.
- Die Atemwelle sieht ein Sensor an der Brust am deutlichsten (Gurt). Ob ein Sensor am Arm
  (Verity Sense) genügt, prüft hrv-research. Der Knopf folgt trotzdem Bens Regel: Hat das Gerät
  einen Beschleunigungssensor, erscheint er.

## 5. A1: Technik

### 5.1 Ein Strom, mehrere Abnehmer

- Der Messlauf bekommt `acc_anfordern(zweck, rate_hz, bereich_g)` und `acc_freigeben(zweck)`,
  mit den Zwecken `diagnose` und `zaehlen`. Gestellt wird die höchste gewünschte Rate. Mit der
  letzten Freigabe geht der Strom sofort zurück auf den Stand von vorher (`_stroeme_zurueck`),
  ohne Nachlauf, denn der Akku geht vor. Auch der Diagnosemodus nimmt diesen Weg, statt
  `stroeme_setzen` direkt zu rufen.
- Der Puffer füllt sich mit jedem ACC-Rahmen, nicht nur im Diagnosemodus. Je Rahmen merkt er
  sich die Rate, falls sie mitten im Satz wechselt (50 → 200 Hz). Die Zeiten der Proben kommen
  aus dem Gerätezeitstempel (`zeitstempel_ns`), die Ankunft dient nur als Anker, wie beim EKG
  (`frame_t_ns`). Statt eines Beobachters gibt es eine Liste, damit Mitschnitt und Zähler nicht
  um den Platz streiten. **Gespeichert wird aus dem Puffer im Alltag nichts** (P123).
- Der Simulator (`devices/simulated.py`) bekommt eine synthetische Beschleunigung:
  Wiederholungen als Sinus mit Streuung, dazu Atmung und Rauschen. Sie dient den Tests und der
  Vorschau am Rechner.

### 5.2 Der Zähl-Dienst

- `devices/zaehlen.ZaehlBaustein` (Teil `zaehlen`, ohne flet) ist ein eigener Teil der Einheit
  wie HRV, Timer und GPS. Er wird einzeln gestartet und tritt einer laufenden Einheit bei
  (`Einheitslauf.beitreten`); sonst entsteht eine, die von selbst endet, wenn nichts mehr in ihr
  läuft. So zeigen Infoleiste, Laufleiste und der Reiter „Einheit“ ihn ohne Sonderweg. Die
  Übung kennt er über `UebungKontext`.
- Satzgrenzen eines Timers sieht er nur als Ereignisse der Einheit, über eine neue, freiwillige
  Methode `beobachten(ereignisse)` am `Baustein`. Die Teile kennen einander also weiterhin
  nicht.
- `takt` holt das Fenster aus dem Puffer, ruft den Prototyp aus hrv-core und prüft „keine
  Bewegung“. Die Laufzeit wird am Handy gemessen: Ziel unter 20 ms je Takt, sonst alle 2 s
  oder über `asyncio.to_thread`. Die Ereignisschleife trägt auch Bluetooth.
- Das Ende beim Start einer anderen Übung und beim Abhaken löst die Oberfläche aus
  (`ui/uebung_lauf.py`), der Baustein selbst kennt nur „Fertig“, „Abbrechen“ und die beiden
  Zeitgrenzen.
- Den Zustand für die Oberfläche (Zahl, Korrektur, Satz, Phase) hält
  `ui/components/zaehl_stand.py` ohne flet, wie `marken_stand`. So nimmt die Uhr am Band
  später denselben Weg, und die CI testet ihn ohne flet.
- `_satz_vergleichen` (Diagnosemodus, Stufe 8) nimmt den Wert des Bausteins, wenn er lief. Es
  gibt einen Zähler, nicht zwei.

### 5.3 Zeitleiste, Eintrag, Messdatei

- **Zeitleiste** (Vertrag `docs/plan_einheit.md` §4, **zuerst** dort eintragen): Teil und
  Quelle `zaehlen` mit drei neuen Arten.
  - `zaehlung` steht einmal je Satz, mit `satz`, `art` (wdh oder atem), `sensor`, `korrektur`,
    `wert`, `feld`, `vorlage`, `zeiten_s` (die gezählten Umkehrpunkte), `geraet` (Profil, von
    dem die Beschleunigung kam) und `prototyp` (Modul und hrv-core-Version).
  - `korrektur` kommt von der Quelle `person`, mit `delta` (±1) und `satz`.
  - `zaehlen_ende` trägt den Grund: `fertig`, `abgehakt`, `abbruch`, `andere_uebung`,
    `keine_bewegung`, `kein_atem`.

  Messwerte stehen dort nicht, nur Ergebnisse mit Zeiten, wie bei `km`.
- **Eintrag:** `core/zaehlen_eintrag.py` (wie `core/timer_eintrag.py`) liest die Wiederholungen
  je Satz aus den `zaehlung`-Ereignissen; `lauf_eintragen` nimmt `reps` mit. Ein abgebrochener
  Zähllauf lässt sich unter „Läufe heute“ nachträglich eintragen.
- **Messdatei:** In die Notizen kommt nichts Neues; die Notiz zum Satz entsteht wie bisher beim
  Eintragen, eine Marke je Wiederholung gibt es nicht. Die Atemphasen kommen als Ergebnis neben
  die Messdatei (Abschnitt 8).
- **Diagnosemodus:** Zusätzlich stehen `zaehlung` und `korrektur` als Kontextzeilen im
  Mitschnitt. Damit liegen Sensor, Korrektur, die Tipps der Leiste und die Rohdaten auf einer
  Achse; hrv-research liest sie mit `trainingsapp_diagnose.py`.
- Der Forschungsexport `einheit-v1` (`docs/plan_einheit.md` §8) trägt die Zeitleiste und damit
  die Zählungen mit.

## 6. A2: Prüfen, wie genau der Sensor zählt

Weil entweder die Person oder der Sensor zählt (P122), gibt es eine Genauigkeit nur dort, wo
beide zählen: im **Diagnosemodus**.

- Die Person tippt in der Marken-Leiste jede Wiederholung (die Wahrheit), der Sensor zählt mit.
  Die Leiste zeigt „Sensor 11“ live neben der Zahl der Tipps.
- Nach dem Satz steht „Marken 12 · Sensor 11 · Korrektur +1 · eingetragen 12“ (Stufe 8,
  erweitert um die Korrektur).
- Der Mitschnitt hat dazu die Rohdaten. hrv-research rechnet daraus die Genauigkeit je Übung und
  Gerät (`diagnose_bericht.py`) und prüft dort neue Verfahren.
- Im Alltag zeigt die App keine Trefferquote, denn niemand hat nachgezählt. Sie zeigt nur, was
  der Sensor zählte und was korrigiert wurde. Wie oft korrigiert wird, ist ein Hinweis, kein Maß.

## 7. Teil B: Ein- und Ausatmung in der HRV

### 7.1 Worum es geht

Beim Einatmen schlägt das Herz schneller, beim Ausatmen langsamer (respiratorische
Sinusarrhythmie, RSA). Wer weiß, wann eingeatmet wird, kann die HRV je Atemzug lesen statt nur
über Fenster. Ben will beides (P124): **(a)** die Auswertung verbessern und **(b)**
Biofeedback, dazu die Einordnung von DFA α1, LF/HF und den übrigen Kennzahlen.

**(a) Größen je Atemzug:**

| Größe | Was | Wofür |
|---|---|---|
| Rate und Gleichmäßigkeit | Atemzüge je Minute, Streuung ihrer Dauer | Einordnung jeder Kennzahl; wie gut ein Takt eingehalten wird |
| Ein:Aus | Dauer des Einatmens zu der des Ausatmens | RMSSD und SD1 ändern sich damit |
| Atemspanne je Atemzug | Gipfel–Tal: höchste minus tiefste Herzfrequenz (bpm) bzw. längster minus kürzester RR (ms) im Atemzug, nach Trendbereinigung | die anschaulichste Größe der RSA; sie braucht Atemgrenzen, und die liefert der Sensor |
| Phasenlage | Zeit (oder Winkel) vom Ende des Einatmens bis zum Gipfel der Herzfrequenz | wandert mit der Dauer des Atemzugs; bei Resonanzatmung das wichtigste Kriterium |
| RR je Phase | mittlerer RR beim Ein- und beim Ausatmen | die Differenz als einfache Zahl |

**Kennzahlen im Licht der Atmung** (P124, Ben: „Auswertung von DFA a1, LF/HF und co“):

- Je Abschnitt oder Übung stehen RMSSD, SD1, HF- und LF-Power, LF/HF und DFA α1 zusammen mit der
  Atmung: Rate, Ein:Aus, spontan oder getaktet.
- **Atmung unter 9/min (0,15 Hz)** liegt im LF-Band. Dann treiben schon die Atemzüge LF/HF und
  DFA α1 nach oben, ohne dass sich im Nervensystem etwas ändert. Die App schreibt das als Hinweis
  an diese Kennzahlen und weist HF-Power nicht aus.
- Getaktet und spontan werden getrennt verglichen (Protokollfeld „Atmung“, 7.4).
- Später, als Änderung einer Rechenvorschrift: das HF-Band an der gemessenen Atemrate
  ausrichten, α1 je Atemlage einordnen. Das entscheidet hrv-research; danach geht es auf dem Weg
  aus hrv-research `docs/UEBERNAHME.md` nach hrv-core, mit Golden Master und `ALGO_VERSION`.

**(b) Biofeedback** (beschreibend, beide Editionen): Atemphasen, Herzfrequenz und die Atemspanne
des letzten Atemzugs live (7.3). Eine Atemfrequenz *aus Messwerten auszuwählen* bleibt eine
Handlungsempfehlung. Das Resonanzprotokoll etwa misst fünf Stufen, und die mit der größten
Atemspanne gewinnt. Es ist darum in Solo gesperrt wie `physiologische_steuerung` und in Praxis
nur mit diesem Schalter verfügbar.

Grundlagen stehen in hrv-research `literatur/atmung/06_atmung_hrv.md`: §1 (wie man die RSA
beziffert), §5 (Resonanzfrequenz), §8 (Kandidaten für hrv-core), §9 (was davon in der Praxis
zählt).

### 7.2 Woher die Phasen kommen

| Quelle | Wie | Güte |
|---|---|---|
| **Sensor** (Ist) | Wendepunkte der Atemwelle aus der Beschleunigung (K3 mit der Prüfung aus K2, hrv-research). Das Vorzeichen der Achse („was ist ein?“) kommt aus dem Takt oder aus der RSA | gut in Ruhe und an der Brust; bei Bewegung keine Zahl |
| **Takt** (Soll) | der neue Taktgeber im Timer (7.6) | exakt, solange die Person folgt; aber Soll, nicht Ist |
| Herz | Phasen aus der RSA allein | nur zur Anzeige; für Phasenlage und Atemspanne wäre es ein Zirkelschluss |
| später EKG | Atmung aus dem EKG (EDR, Entscheidung 1 in hrv-research) | offen |

Mit Takt **und** Sensor zeigt die Auswertung Soll gegen Ist, also wie genau dem Takt gefolgt
wurde. Auch das ist beschreibend.

### 7.3 Anzeige

- **Live** (Atemübung, Live-Vollbild): die Herzfrequenz der letzten 60 s mit hinterlegtem
  Einatmen, die Phase jetzt (▲ ein / ▼ aus), die Atemspanne des letzten Atemzugs und die Rate.
  Nur Zahlen und Kurven, keine Wertung wie „gut“ oder „kohärent“.
- **Auswertung** (`views/messung_detail.py`), die Abbildung, die Ben sich wünscht (P120):
  - eine Ebene „Atmung“ über dem Tachogramm, wie die Marken-Ebene des Diagnosemodus, mit
    schattiertem Einatmen und dem Takt als feinen Linien;
  - je Abschnitt oder Übung eine Karte „Atmung (Prototyp)“ mit den Größen aus 7.1 und der
    Quelle (Sensor · Takt · Herz);
  - die Kennzahlen mit den Hinweisen aus 7.1.

### 7.4 Ablage

- **Ergebnisse, keine Rohdaten** (P123). Die Atemphasen rechnet die App live und schreibt sie
  als Ergebnis des Prototyps neben die Messdatei (Abschnitt 8). Die Größen je Atemzug und die
  Hinweise entstehen beim Anzeigen aus den Phasen und den RR-Abständen der Messdatei. Gespeichert
  werden sie nicht.
- Folge, bewusst so gewollt: Wird der Prototyp besser, behalten alte Messungen ihre alten
  Phasen. Die Datei nennt Modul und hrv-core-Version, darum ist immer klar, womit gerechnet
  wurde. Neu rechnen lässt sich nur, was im Diagnosemodus mit Rohdaten aufgenommen wurde.
- **Protokollfeld „Atmung“** an der Messung (P125: ja): spontan · getaktet (mit Takt) · Übung,
  automatisch aus der Übung und dem Taktgeber. Ohne diese Angabe sind HF-Power, LF/HF und DFA α1
  zwischen Messungen nicht vergleichbar. Es wird eine Erweiterung von `raw-v1`, die praxis_gui
  mitliest; der Vertrag kommt zuerst.

### 7.5 hrv-core

- `prototyp.atemzuege` (neu) findet Atemzüge und Phasen in der Beschleunigung:
  `atemzuege(xyz, rate_hz, t0_s, *, rr=None, takt=None)` liefert
  `Atemzuege(ein_s, aus_s, rate_pro_min, gleichmaessigkeit, gueltig, gruende, art="prototyp")`.
  Dazu kommt eine Live-Fassung für die Anzeige und das Schreiben.
- `prototyp.atem_hrv` (neu) rechnet aus Phasen und RR-Abständen je Atemzug Atemspanne,
  Phasenlage, Ein:Aus und RR je Phase. Bewertet wird nichts.
- Das Ergebnisformat `atem-v1` (Abschnitt 8) bekommt Schreiber und Leser in hrv-core, damit
  praxis_gui dieselben Dateien liest.
- Der Eingang folgt den Regeln in `hrv_core.prototyp`: zwei Sitzungen, die nicht zum
  Einstellen dienten, und ein Befund in hrv-research.

### 7.6 Taktgeber und getaktete Übungen (neue Aufgabe, „demnächst“)

Ben (P125): „Es gibt noch keine Taktung. Das wäre eine sinnvolle Erweiterung für den Timer: z. B.
3 min und dann Phasen setzen können, diese optisch interessant gestalten. Evtl. erstelle ich GIFs
für die Übungen (Kniebeugen), um die Bewegung anzuzeigen, das geht aber auf die Übung, nicht den
Timer. Merke dir das einmal als Aufgabe für demnächst (Animation/Visualisierung getakteter Übung
mit Geschwindigkeitsregler).“ Vorgemerkt als **A18** in `docs/offene_fragen.md`; ein eigener
Plan (`docs/plan_taktgeber.md`) folgt, wenn es losgeht. Der Rahmen:

- **Taktgeber im Timer:** eine Dauer (etwa 3 min) und Phasen mit Sekunden (ein · halten · aus ·
  halten), mit Klang je Phase und einer Animation, die das Atmen zeigt (ein Kreis oder eine
  Welle, die wächst und schrumpft, eine Farbe je Phase).
- **Getaktete Übung allgemein:** ein Tempo je Wiederholung (etwa Kniebeuge 2 s ab · 1 s halten ·
  2 s auf) mit Animation und einem **Geschwindigkeitsregler**, der den Takt schneller oder
  langsamer stellt.
- **GIFs der Bewegung** (etwa Kniebeugen, von Ben erstellt) gehören an die Übung, nicht an den
  Timer. Sie laufen zum Takt mit, wenn einer läuft.
- **Für Teil B:** Der Taktgeber schreibt seinen Takt als eine Angabe in die Messdatei (Spur
  `atemtakt`: Beginn, Phasen mit Sekunden, Tempo, Runden), nicht als Marke je Abschnitt. Sonst
  fielen Abschnitte unter 5 s weg (`core.einheit.MIN_MARKE_S`). Daraus kommen die Soll-Phasen
  und die Angabe „getaktet“ im Protokollfeld. Der Vertrag `docs/kompatibilitaet.md` §4 kommt
  zuerst.

## 8. Was gespeichert wird: Ergebnisse statt Rohdaten

Ben (P123): „Die reguläre Anwendung soll zeigen, dass die App smart ist. Brute force alles
aufzeichnen ist für die Entwicklung.“

| Was | Wo | Wann |
|---|---|---|
| Wiederholungen je Satz, ihre Zeiten, Korrekturen, Ende-Grund | Zeitleiste (`zaehlung`, `korrektur`, `zaehlen_ende`), Eintrag (`reps`) | im Alltag |
| Atemphasen (Beginn von Ein- und Ausatmen), Rate je Fenster, gültige Stücke | `sensor_<ts>_atem.json` neben der Messdatei (`atem-v1`) | im Alltag, wenn „Atmung“ an war und eine Aufnahme lief |
| Rohdaten der Beschleunigung | Mitschnitt `mitschnitt-v1` | **nur im Diagnosemodus** |

`atem-v1` ist gebaut wie die anderen Beiwerke (`hrv_core.ekg` als Vorbild, Journal gegen
Absturz). Die Datei enthält:

- `art = "prototyp"`, `prototyp` (Modul) und `hrv_core` (Version);
- `quelle` (sensor oder takt) und `geraet` (Profil);
- `phasen[]` mit `[t_s, "ein" | "aus"]` auf der Wanduhr der Messung, `fenster[]` mit Rate und
  Gültigkeit.

`ist_messdatei` kennt die Endung, `deid` behält die Felder. **Zuerst** kommen die Einträge in
`docs/kompatibilitaet.md` (§15) und in `docs/formate.md` von hrv-core. Export und Backup gehen
wie beim EKG-Beiwerk. Die Datei enthält nie einen Ort und nichts vom Magnetometer (Richtung).

## 9. praxis_gui

praxis_gui misst Patienten mit dem H10 (PySide6, der Expertenmodus ist sichtbar). Gleich bleibt
alles, was in hrv-core liegt: PMD-Dekoder, Format `atem-v1`, Zähler- und Atem-Prototypen,
Vorlagen und die Kennzeichnung „Prototyp“. Selbst baut praxis_gui, in einer eigenen Sitzung im
Repo praxis_gui (hier nicht erreichbar):

- den ACC-Strom in seiner Polar-Anbindung,
- die Atem-Ebene über der Kurve mit den Kennzahlen im Licht der Atmung,
- Knopf und ±1 nach diesem Muster, wenn dort Übungen mit Wiederholungen laufen,
- das Resonanzprotokoll, wenn Ben es dort will (Abschnitt 10).

Für Patientendaten gilt Regel 2 von hrv-research: Kein Verfahren wird in einer Sitzung an
Patientenmessungen entwickelt; Läufe darauf startet Ben selbst.

## 10. Recht und Datenschutz

- Zählen, Atemphasen und die Einordnung der Kennzahlen sind **beschreibend**: Zahlen, kein Rat,
  in beiden Editionen. Nichts wird aus Messwerten gewertet („gut“, „kohärent“), nichts empfohlen
  („langsamer atmen“, „noch zwei Wiederholungen“); siehe `docs/recht/00_zweckbestimmung.md`.
- Das Resonanzprotokoll wählt eine Atemfrequenz aus Messwerten und ist damit eine
  Handlungsempfehlung: in Solo gesperrt (`physiologische_steuerung`), in Praxis nur mit dem
  Schalter (P124).
- „Welche Atmung die beste ist“ (3.1) ist in hrv-research eine Forschungsfrage. Sagt die App
  einer Person aus *ihren* Messwerten, wie sie atmen soll, ist das wieder eine
  Handlungsempfehlung, mit denselben Grenzen.
- Im Alltag entstehen neue abgeleitete Daten (Wiederholungen mit Zeiten, Atemphasen), aber keine
  Rohdaten der Beschleunigung (P123). Nachträge kommen in `docs/recht/40_toms.md` und
  `10_verarbeitungsverzeichnis.md`. Die Daten bleiben auf dem Gerät, ohne Netzverbindung.
- „Prototyp“ steht an jeder Zahl, die ein Prototyp liefert.

## 11. Stufen

| Stufe | Inhalt | Repos | Umfang |
|---|---|---|---|
| **A1** | Karte mit den Schaltern Wiederholungen und Atmung (Migration 037, Paketfeld); Strom mit mehreren Abnehmern, ab dem Tipp; Simulator mit Beschleunigung; Zähl-Dienst in Info- und Laufleiste, unabhängig von der Uhr; Ende-Regeln; Knopf mit −1/+1; Wiederholungen je Satz in den Eintrag; Zeitleiste | trainingsapp | L |
| **A2** | Prüfen im Diagnosemodus: Sensor live in der Marken-Leiste, nach dem Satz Marken · Sensor · Korrektur · eingetragen | trainingsapp | S |
| **A3** | Atemzüge: K3 mit Prüfung → `prototyp.atemzuege`; „Atmung erfassen“; Ergebnis `atem-v1` | hrv-research → hrv-core → trainingsapp | M |
| **B1** | Abbildung in der Auswertung (Ebene „Atmung“, Karte), Live-Anzeige und Biofeedback; Protokollfeld „Atmung“ | trainingsapp, hrv-core | M |
| **T** | Taktgeber im Timer, Animation getakteter Übungen mit Geschwindigkeitsregler, GIFs an der Übung, Spur `atemtakt` (A18, eigener Plan) | trainingsapp | M |
| **B2** | Atem-HRV (`prototyp.atem_hrv`); Kennzahlen im Licht der Atmung (DFA α1, LF/HF …) | hrv-research → hrv-core → trainingsapp | M |
| **A5** | Live-Zähler, der jede Wiederholung zählt, wenn sie geschieht; Vorlagen; Umkehrpunkt | hrv-research → hrv-core → trainingsapp | L |
| **A6** | Band (Seite „Zählen“, P121); „Im Plan einstellen“; praxis_gui | hrv-watch, trainingsapp, praxis_gui | M |
| später | Atmung je Wiederholung; vergleichen, wie geatmet wurde (Konzept C3) | hrv-research | — |

A1 und A2 brauchen nichts Neues aus hrv-core. Damit lässt sich sofort prüfen, wie gut der Sensor
Wiederholungen zählt. Jede Stufe endet mit Tests (ohne flet, wo es geht), Doku und, wo nötig,
einer APK.

## 12. Entscheidungen (Ben, 4.11.2026)

| # | Frage | Entscheidung |
|---|---|---|
| P117 | Ein Schalter für Karte und Knopf? | **kleiner Schalter an jeder Übung**, „da jede Übung eine Atemkomponente haben kann“: Wiederholungen und Atmung je Übung schaltbar (3.1) |
| P118 | Ohne Beschleunigungssensor ein Handzähler (nur +1/−1)? | nein: „Wenn ein Gerät einen Beschleunigungssensor hat, soll die Wiederholung damit gemessen werden. Das ist der Knopf. +/-1 ist die Korrektur dafür.“ |
| P119 | Wie startet und endet das Zählen? | **unabhängig von der Uhr**, als Dienst in der Infoleiste. Es endet bei Abbruch, beim Start einer anderen Übung, bei „Fertig“ oder dem Abhaken, und ohne Bewegung (mit Zeitgrenze); ein Wechsel der Ansicht beendet es nicht. Gezählt wird **erst ab dem Tipp**: „Akku hat in diesem Fall Prio“ |
| P120 | Atemzüge eintragen? | erst einmal **an der Messung** festhalten, mit Abbildung in den Messaufzeichnungen; ins Tagebuch, wenn klar ist, was an der Atmung wichtig ist |
| P122 | Wahrheit beim Zählen | **entweder–oder:** „Entweder zähle ich, oder der Sensor. Beides gleichzeitig ist nur Überprüfung und Debugging“ |
| P123 | Beschleunigung im Alltag mitschreiben? | **nie**, nur im Diagnosemodus: „Die reguläre Anwendung soll zeigen, dass die App smart ist. Brute force alles aufzeichnen ist für die Entwicklung“ — gespeichert werden Ergebnisse (Abschnitt 8) |
| P124 | Was heißt „HRV verbessern“? | **(a) und (b):** Auswertung und Biofeedback, „und: Auswertung von DFA a1, LF/HF und co“ |
| P125 | Protokollfeld „Atmung“ | **ja**, aber es gibt noch keine Taktung: Taktgeber im Timer als neue Aufgabe (7.6, A18) |
| P126 | Vorlagen schon am Anfang? | **erst nur „Automatisch“** |

**Offen:** P121. Kommt am Band eine Seite „Zählen“ mit der Zahl, auf der ⏯ +1 ist (auf den
anderen Seiten bleibt ⏯ die Marke wie heute, P113)? Vorschlag: ja, in A6.
