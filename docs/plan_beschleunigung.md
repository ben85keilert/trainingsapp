# Plan: Beschleunigungssensor in Übungen — Wiederholungen zählen, Atmung erfassen, Ein- und Ausatmung in der HRV

Stand 5.11.2026: **A1, A2, A3 und B1 gebaut** (Version 0.3.46, Abschnitt 13); T, B2, A5 und A6
folgen. Der Plan ist **angenommen** — Ben: „Plane das beides durch“, danach P117–P126 entschieden
(Abschnitt 12) und „Falls nicht [noch Fragen offen], kannst du anfangen den Plan umzusetzen“. Die Verfahren
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
| hrv-watch | nichts Neues: ⏯ je Wiederholung bleibt Diagnose und Algorithmusentwicklung (P121) |
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
| Band (hrv-watch) | kein Zählen am Band (P121): „Wer tippt 30 mal auf eine Uhr, um fit zu werden?“ ⏯ je Wiederholung bleibt im Diagnosemodus |

Umsetzung A1 (`ui/components/zaehlen.py`, Zustand ohne flet in `components/zaehl_stand.py`):
Zeigt die Karte „Eintragen“ die laufende Uhr und zählt der Sensor in ihrer Einheit, steht die
Zahl mit ±1 und „Zählen abbrechen“ in der Uhr — die Zählzeile darunter wiederholt sie nicht,
und „Fertig“ der Uhr beendet beides. Unter dem Knopf stehen die Zählläufe von heute, deren
Wiederholungen noch fehlen, mit „Nachtragen“ (`components/laeufe_heute.py`, dieselbe Zeile wie
„Läufe heute“ im Timer, dort „Eintragen“ — in dieser Karte heißt schon „Eintragen“ der Sätze ×
Wert so) — so auch an einer Übung ohne Uhr. Die Meldung „… nicht eingetragen“
zeigt der Start, der das Zählen beendete, oder der nächste Aufbau der Ansicht, nie über einem
Dialog. Auf „Heute“ hakt der Chip mit den gezählten Wiederholungen ab, ohne „Rückgängig“.
Den Knopf gibt es in einer Planübung nur, wenn sie ein Wiederholungsfeld anbietet (P79: keiner =
nur abhaken; auch eines, das nur der Plan hat) — und Uhr und Zählen kommen nur zusammen, wenn
die (Plan-)Übung der Uhr eines anbietet, denn eingetragen wird, wo die Uhr läuft; sonst macht
das Zählen Platz wie für eine andere Übung. Endet nur das Zählen und die Uhr läuft weiter,
bleibt dort die Zahl ohne −1/+1 stehen; „Eintragen“ der Meldung trägt dann nur die
Wiederholungen ein, die Zeit kommt mit dem Ende der Uhr. Solange der Sensor in ein Feld zählt,
hat dessen Zeile weder Chips noch eigenen Wert und die Karte kein „Wie geplant“ (4.4; im
Diagnosemodus Chips und eigener Wert: ein Satz von Hand beendet dort den Satz des Sensors, der
ihn dann nicht noch einmal einträgt — mit der Uhr den ihres Abschnitts; Sätze davor, die nur der
Sensor zählte, kommen vor ihm ins Tagebuch). Steht eine Einheit bereit oder läuft ein
Plan-Ablauf, gibt es keinen Knopf. Die Zählläufe von heute, deren Wiederholungen fehlen, lassen
sich auch ohne verbundenes Gerät eintragen.

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
   | **Keine Bewegung:** 60 s ohne gezählte Wiederholung (Ben: „evtl. mit Timer“) | abgebrochen wie oben; dazu die Meldung „Kniebeuge · 12 Wdh. nicht eingetragen — 60 s ohne Bewegung“ (5 s, „Eintragen“). Die 60 s sind ein Startwert; reicht das bei langen Pausen im Satz nicht, wird er einstellbar |
   | Nur Atmung: das Gerät liefert 2 min lang keinen erkennbaren Atemzug (abgelegt, verrutscht) | abgebrochen wie oben. „Keine Bewegung“ gilt hier nicht, denn bei einer Atemübung ist Stille gewollt |
   | Das Gerät wird getrennt (Umsetzung A1), auch ein Funkabriss, den die Quelle selbst neu verbindet | abgebrochen wie oben, sofort, mit dem Grund `abbruch` — nicht erst 60 s später als „keine Bewegung“; die Meldung endet auf „— Sensor getrennt“ |
   | Verbunden, aber 15 s keine Beschleunigung (`KEINE_DATEN_S`; abgelehnt, nicht erprobt) | abgebrochen wie oben (`abbruch`), „— keine Daten vom Sensor“ |
   | Der Satz läuft länger, als der Puffer hält (gut 10 min, `ACC_PUFFER_RAHMEN`) | abgebrochen wie oben (`abbruch`) mit der letzten ganzen Zahl, „— Satz zu lang für den Sensor“ — sonst zählte der Prototyp still nur das Ende |

   Abgehakt wird auch mit einem Chip, der einen Wert einträgt (Zeit, Strecke, Seite): Der Wert
   kommt zu den Wiederholungen in denselben Eintrag, der dann schließt — nicht noch das Ziel.
   Wo abgehakt wird, dort steht der Eintrag: Begann das Zählen auf der Übungsseite und wird auf
   „Heute“ am Chip eines Plans abgehakt, gehört er in diesen Plan (mit ihm die Zeit der Uhr,
   die in derselben Einheit läuft). Bietet die Planübung dort kein Wiederholungsfeld an (P79),
   endet das Zählen abgebrochen und bleibt nachtragbar, wo es begann; das Abhaken stempelt wie
   sonst.
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
- **Die Atmung läuft nebenbei** (Ben, 5.11.2026, P133): Sie hängt nicht an Sätzen, Chips oder
  Timer-Abschnitten — ein Chip beendet den Satz des Wiederholungszählers, nie die Atem-Erfassung.
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
  (`frame_t_ns`). Umsetzung A1: Die Rate eines Rahmens ist die, mit der die Quelle gerade
  sendet (`PolarQuelle.acc_gestartet`), nicht der neue Wunsch — bis zum Neustart kommen noch
  Rahmen der alten. Ein Fenster über einen Wechsel kommt in der jüngsten Rate: die übrigen
  Rahmen umgetaktet (`Messlauf.acc_reihe`, `umtakten`; herunter vorher gemittelt), nicht
  weggelassen, mit der Zeit jeder Probe — auch über eine Lücke im Strom hinweg. Umsetzung A1:
  ein Beobachter der Quelle (`Messlauf._acc_empfangen`) füllt den gemeinsamen Puffer, die
  Abnehmer melden sich über `acc_anfordern` an; den Mitschnitt schreibt der Transport
  (`devices/mitschnitt.MitschnittTransport`) aus den Rohbytes — so streitet niemand um den
  Platz, eine Liste von Beobachtern braucht es nicht.
  **Gespeichert wird aus dem Puffer im Alltag nichts** (P123).
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
  - `zaehlung` steht je Satz, mit `satz`, `zaehlart` (wdh oder atem — `art` ist ein Feld des
    Ereignisses), `sensor`, `korrektur`, `wert`, `feld`, `vorlage`, `zeiten_s` (die gezählten
    Umkehrpunkte), `geraet` (Profil, von dem die Beschleunigung kam) und `prototyp` (Modul und
    hrv-core-Version). Umsetzung A1, gegen den Absturz: Ein Satz steht da, sobald er endet, ein
    laufender alle 15 s als Zwischenstand, wenn er sich änderte, und eine Korrektur in der
    Pause schreibt ihn neu — es gilt die letzte je Satz (`core.zaehlen_eintrag.zaehlungen`).
  - `korrektur` kommt von der Quelle `person`, mit `delta` (±1) und `satz`.
  - `zaehlen_ende` trägt den Grund: `fertig`, `abgehakt`, `abbruch`, `andere_uebung`,
    `keine_bewegung`, `kein_atem`.

  Messwerte stehen dort nicht, nur Ergebnisse mit Zeiten, wie bei `km`.
- **Eintrag:** `core/zaehlen_eintrag.py` (wie `core/timer_eintrag.py`) liest die Wiederholungen
  je Satz aus den `zaehlung`-Ereignissen; `lauf_eintragen` nimmt `reps` mit. Ein abgebrochener
  Zähllauf lässt sich unter „Läufe heute“ nachträglich eintragen.
- **Messdatei:** In die Notizen kommt nichts Neues; die Notiz zum Satz entsteht wie bisher beim
  Eintragen (Umsetzung A1: `person/leistung` wie nach einem Chip, an der Stelle, an der der Satz
  endete), eine Marke je Wiederholung gibt es nicht. Die Atemphasen kommen als Ergebnis neben
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
  erweitert um die Korrektur). Umsetzung A2: nach einem Satz von Hand (Chip) mit dem Wert des
  Zähl-Teils, wenn er dieselbe Übung zählt; nach einem Zähllauf am Ende je Satz
  (`Messlauf.zaehlsatz_vergleichen`) — „eingetragen“ ist dann der Satzwert, wenn das Zählen
  mit `fertig` oder `abgehakt` endet, sonst „–“.
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
| Phasenlage | **Sekunden ab Beginn des Einatmens** bis zum Gipfel der Herzfrequenz (P135, Ben 5.11.2026; der Gipfel ist der eines an den Atemzug angepassten Sinus, der Winkel 0–360° steht im Tooltip) | wandert mit der Dauer des Atemzugs; bei Resonanzatmung das wichtigste Kriterium |
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
| **A6** | „Im Plan einstellen“; praxis_gui | trainingsapp, praxis_gui | M |
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
| P121 | Am Band eine Seite „Zählen“, ⏯ = +1? | **nein:** „Das Klicken für eine Wiederholung ist eigentlich nur für Diagnose und Algorithmusentwicklung. In einer Übung selbst macht das keinen Sinn, wer tippt 30 mal auf eine Uhr, um fit zu werden?“ |
| P122 | Wahrheit beim Zählen | **entweder–oder:** „Entweder zähle ich, oder der Sensor. Beides gleichzeitig ist nur Überprüfung und Debugging“ |
| P123 | Beschleunigung im Alltag mitschreiben? | **nie**, nur im Diagnosemodus: „Die reguläre Anwendung soll zeigen, dass die App smart ist. Brute force alles aufzeichnen ist für die Entwicklung“ — gespeichert werden Ergebnisse (Abschnitt 8) |
| P124 | Was heißt „HRV verbessern“? | **(a) und (b):** Auswertung und Biofeedback, „und: Auswertung von DFA a1, LF/HF und co“ |
| P125 | Protokollfeld „Atmung“ | **ja**, aber es gibt noch keine Taktung: Taktgeber im Timer als neue Aufgabe (7.6, A18) |
| P126 | Vorlagen schon am Anfang? | **erst nur „Automatisch“** |

P117 bestätigt (Ben): die Schalter sitzen an jeder Übung, nicht einer für alle.

## 13. Umsetzungsstand (5.11.2026, Version 0.3.47)

A1 und A2 sind gebaut, ohne Änderung an hrv-core (0.8.0): Der Zähler ist
`hrv_core.prototyp.wiederholungen`, die Kontextzeilen nutzen nur Felder, die `hrv_core.deid`
schon kennt. **A3** (5.11.2026) nimmt hrv-core 0.9.1 (`hrv-core.ref` angehoben; 0.9.1 behebt den Rechenfehler nach Stillstand):
`prototyp.atemzuege` (Entscheidung 24 in hrv-research) und das Beiwerk `atem-v1`. **B1**
(5.11.2026, 0.3.46) zeigt das Beiwerk in Auswertung und live und schreibt das Protokollfeld
„Atmung“ — ohne neue Rechenvorschrift (hrv-core bleibt 0.9.1; die fünfte Prüfrunde zu A3/B1
hebt auf 0.9.2: `deid` kennt den Backup-Schlüssel `_journal`, keine Rechenänderung).

| Stufe | Gebaut | Wo |
|---|---|---|
| A1 Karte | `SensorWahl` (Wiederholungen, Atmung als ``bool \| None`` = Vorgabe aus der Übung, `vorlage`, `feld`), Vorgaben, Texte, Ende-Gründe und Grenzen (`KEINE_BEWEGUNG_S` 60, `KEIN_ATEM_S` 120, `MIN_RATE_HZ` 50, `BEREICH_G` 8); Migration 037 (`exercise.acc_json`, `einheit_baustein.art` `zaehlen`); Paketfeld `beschleunigung` im Drei-Wege-Abgleich; Karte „Beschleunigungssensor“ nach „Uhr und Timer“ mit Prototyp und (i), „Zählt in“ ab zwei Wiederholungsfeldern; Zeile an der Übungsseite | `core/zaehlen.py`, `core/models.py`, `data/migrations/037_beschleunigung.sql`, `data/repositories.py`, `core/pakete.py`, `views/uebung_bearbeiten.py`, `views/uebung_detail.py`, `components/hilfe.py` |
| A1 Strom | `acc_anfordern`/`acc_freigeben` mit den Zwecken `diagnose` und `zaehlen` (höchste Rate gewinnt, die letzte Freigabe stellt den Stand von vorher her und leert den Puffer); Zeiten aus dem Gerätezeitstempel mit Anker; über einen Ratenwechsel umgetaktet auf die jüngste Rate (`acc_reihe`); Neustart der ACC beim Ratenwechsel (`PolarQuelle.acc_gestartet`); `trennen()` beendet das Zählen sofort als `abbruch`; Simulator mit synthetischer Beschleunigung (`bewegung_setzen`) | `devices/messlauf.py`, `devices/polar.py`, `devices/simulated.py` |
| A1 Zähl-Dienst | `ZaehlBaustein`, Teil `zaehlen` der Einheit: Strom ab dem Tipp (H10 50 Hz, Verity Sense 52 Hz), jede Sekunde der Prototyp auf dem Satzfenster, ein Satz je Zähllauf bzw. je zählendem Timer-Abschnitt (über `beobachten`), „Anhalten“ der Uhr hält an, ±1 je Satz, Ende-Regeln aus 4.3; `Einheitslauf.ende_mit_zaehlen`; Uhr und Zählen derselben Übung teilen eine Einheit (`UebungBaustein.kontext_setzen`); Zeitleiste `zaehlung`, `person/korrektur`, `zaehlen_ende` (Vertrag `docs/plan_einheit.md` §4) | `devices/zaehlen.py`, `devices/einheit.py`, `core/einheit.py` |
| A1 Eintrag | Wiederholungen je Satz in den offenen Eintrag (bei `saetze=False` die Summe), Zeit und Wiederholungen in **einen** Eintrag, `person/eintrag` je Teil mit `teil` (nie doppelt); „Abhaken“ trägt sofort ein und schließt den Eintrag; eine andere Übung beendet ein Zählen ohne Uhr mit `andere_uebung` und der Meldung „… nicht eingetragen“ (5 s, „Eintragen“), eine laufende Uhr nie still; „Läufe heute“ mit „Satz 1 · 12 Wdh. (Sensor 11, +1)“ trägt abgebrochene Zählläufe nach, auch ohne Uhr an der Übung und ohne Gerät | `core/zaehlen_eintrag.py`, `SessionRepo.lauf_eintragen`, `ui/uebung_lauf.py`, `ui/einheit.py`, `components/laeufe_heute.py` |
| A1 Oberfläche | Zählzeile in der Karte „Eintragen“ unter der Uhr (Knopf `knopf_text`, große Zahl, −1/+1 als Flächen, „Sensor 11 · +1 · Prototyp“, „Fertig“, „Zählen abbrechen“), Zustand ohne flet; Zahl mit ±1 in der laufenden Uhr und im Timer „Während“, „Sätze“ mit Zeit und Wiederholungen; Zähl-Dienst in Info- und Laufleiste und in der Benachrichtigung (`docs/plan_einheit.md` §9); Abhaken in Plan und auf „Heute“ | `components/zaehlen.py`, `components/zaehl_stand.py`, `components/uhr.py`, `views/uebung_timer.py`, `components/startleiste.py`, `views/plan.py`, `views/tag.py`, `ui/app.py` |
| A2 | „Sensor 11“ live in der Marken-Leiste; nach dem Satz „Marken 12 · Sensor 11 · Korrektur +1 · eingetragen 12“ mit dem Wert des Zähl-Teils (nur dieselbe Übung), nach einem Zähllauf je Satz (`zaehlsatz_vergleichen`); Kontextzeilen `zaehler`, `zaehlung`, `korrektur`, `zaehlen_ende` (`docs/kompatibilitaet.md` §14) | `components/marken_leiste.py`, `marken_stand.py`, `devices/messlauf.py`, `core/diagnose.py` |
| A3 Atem-Spur | Ist „Atmung“ an, läuft im `ZaehlBaustein` neben den Sätzen die **Atem-Spur**: `hrv_core.prototyp.atemzuege.AtemLive` in der Rate des Laufs (50/52 Hz; wechselt die Rate, taktet `Messlauf.acc_reihe` um), jeden Takt nur die neuen Proben (nie gedrosselt — unter 1 ms, das Prüffenster alle 5 s einige ms), je lückenlosem Stück ein Rahmen. Phasen „ein“/„aus“ und Fenster gehen ans Beiwerk `_atem.json` der laufenden Messung (`Messlauf.atem_sammler`, `atem_lauf_beginn/ende`, `atem_phase`, `atem_fenster`, Vertrag §15; ohne Aufnahme fehlen nur sie). Stand: `atemzuege` (Sensor + Korrektur), `atem_sensor`, `atem_rate` (letztes gültiges Fenster), `atem_phase` (▲/▼/–). **Läuft nebenbei** (P133): Sätze, Chips, Abschnitte, „Anhalten“ berühren sie nicht; das Ende des Laufs beendet beide Spuren (`AtemLive.abschluss`). Nur Atmung: ±1 korrigiert die Atemzüge (`person/korrektur` mit `zaehlart` atem, `satz` 0), `KEIN_ATEM_S` ohne Atemzug → `kein_atem` mit Meldung „— 2 min kein Atemzug erkannt“ (ohne „Eintragen“); `ohne_daten`/`getrennt` für beide Spuren. Zeitleiste: `zaehlung` mit `zaehlart` atem, `satz` 0 (= der ganze Lauf), `sensor`, `korrektur`, `wert`, `rate`, `zeiten_s` (Einatemzeiten), `geraet`, `prototyp` `hrv_core.prototyp.atemzuege@<hrv_core.__version__>` — am Ende und alle 15 s; `core.zaehlen_eintrag` übergeht sie (nichts ins Tagebuch, P120). Diagnosemodus: eine Kontextzeile `atem` (Atemzüge, `satz` 0, Rate als `phase`) am Ende, keine je Atemzug. Wirft der Prototyp, zählt ein frischer weiter (`atem_fehler`, die Zahl bleibt). Simulator und Gurt-Attrappe mit dem Vorzeichen der Brust: z fällt beim Einatmen, (x − z) steigt; RSA dazu konsistent (RR zu Beginn des Einatmens am längsten, an dessen Ende am kürzesten) | `devices/zaehlen.py`, `devices/messlauf.py`, `core/zaehlen.py` (`rate_text`, `phase_pfeil`, `atem_text`), `core/einheit.py` (`rate`), `core/zaehlen_eintrag.py`, `devices/simulated.py`, `tests/attrappen.py` |
| A3 Oberfläche | Nur Atmung: große Zahl = Atemzüge mit ±1-Flächen („Ein Atemzug mehr“), darunter „Atmung 14 · 12/min ▲ · Prototyp“; Wdh + Atmung: Zahl = Wiederholungen, dritte Zeile „Atmung 12/min ▲“ (`ZaehlAnzeige.atem`, nur Texte nachgezogen); Status „Box Breathing · Atmung · 14 · 12/min ▲“ bzw. „Kniebeuge · 12 · Atmung 12/min ▲“ in Info-, Laufleiste und Benachrichtigung; Hilfetext „Beschleunigungssensor“ mit einem Absatz zur Atmung | `components/zaehl_stand.py`, `components/zaehlen.py`, `components/hilfe.py`, `ui/einheit.py` (`ZaehlMeldung.atmung`) |

| B1 Auswertung | Gibt es das Beiwerk `_atem.json`, lädt die Auswertung es im Thread (wie EKG und Diagnose): die **Ebene „Atmung“** (`EBENE_ATMUNG`, Chip in der Farbe der Atemfrequenz, Knopf im Vollbild, gemerkt wie die anderen Ebenen; nur angeboten, wenn das Beiwerk da ist) schattiert das **Einatmen** über dem Tachogramm und im Vollbild und legt die Läufe „Atmung erfassen“ als feines Band oben — außerhalb der Läufe nichts (Vertrag §15). Die **Karte „Atmung (Prototyp)“** (nach dem HRV-Teil, vor EKG und Diagnose) nennt je Messung und je Abschnitt (Rechenbereich wie `werte_von`, nur wo erfasst wurde): Atemzüge (Phasen „ein“), Rate (Median der gültigen Fenster, „–“ ohne), Ein:Aus („1 : 1,4“, Median des Ausatmens je Einatmen), Gleichmäßigkeit (CV der Atemzugdauern), gültige Fenster, Dauer erfasst, Quelle „Sensor · Prototyp · Gerät“, das Protokollfeld in Worten und daneben die **Atmung aus RR** als Vergleich — eine Abweichung über 2/min wird genannt, nicht gewertet. Alles beim Anzeigen gerechnet (`core/atem_auswertung.py`, flet-frei), nichts gespeichert (§7.4), keine Wertung (§10) | `core/atem_auswertung.py`, `core/hrv_einstellungen.py`, `views/messung_detail.py` |
| B1 Hinweis | **„Atmung < 9/min — liegt im LF-Band“** (§7.1): Kacheln LF/HF und DFA α1 bekommen den Hinweis als Grundzeile, die Kachel HF-Power zeigt „–“ mit „nicht ausgewiesen“; in den Tabellen Frequenz und Nichtlinear steht er unter den Zeilen, die HF-Zeile als „nicht ausgewiesen“; die Karte „Atmung“ sagt es dazu. Welche Rate gilt, ist die **Startregel F6** (in hrv-research offen, `atem_auswertung.hinweis_rate`): die Rate des Sensors, wenn mindestens die Hälfte der Prüffenster gültig war, sonst die Atmung aus RR (`hrv_core.atmung`, vorhandene Kachel), sonst keine | `core/atem_auswertung.py`, `views/messung_detail.py` |
| B1 Live | Erfasst ein Zähl-Teil die Atmung, liegt im Live-Vollbild (`doppelkurve(hinten=…)`) und in der HF-Kurve der Messung das **Einatmen der letzten 60 s** als Schatten hinter den Kurven, die laufende Einatmung bis jetzt; im Kopf des Vollbilds „Atmung 12/min ▲“. Die Phasen hält der `ZaehlBaustein` selbst (`atem_phasen_s`, Achse der Einheit; `auf_messlauf` bringt sie auf die Achse der Kurven) — das geht auch **ohne Aufnahme**; `zaehl_stand.atem_teil`/`atem_phasen_live`/`atem_kopf_text` sind flet-frei, `components/atem_live.einatem_schatten` baut die Reihen. Nachgezogen über die vorhandenen Beobachter (Messlauf je Schlag, Einheit je Takt unter `einheit_beobachter["live_vollbild"]`), nur Reihen und Texte, keine Knöpfe. Beschreibend (P124): keine Atemspanne, keine Wertung — die Atemspanne des letzten Atemzugs kommt mit B2 | `devices/zaehlen.py`, `components/zaehl_stand.py`, `components/atem_live.py`, `views/live_vollbild.py`, `views/messung.py` |
| B1 Protokollfeld | **`atmung`** im Kopf der Messdatei (Vertrag §5, P125), direkt hinter `datenqualitaet`: `Messlauf.atmung_protokoll` ist ein Haken (Ereignisse der Aufnahme → Feld), den die Oberfläche mit dem Übungskatalog belegt (`zaehl_stand.atmung_protokoll`: Kurzcodes aus `uebungen` der Notizen, `core.zaehlen.atmung_an`); die Regel in `core/atem_protokoll.py`: Atemübung gelaufen → `uebung` mit Kurzcode, gar keine Übung → `spontan`, nur andere Übungen → kein Feld (unbekannt, es wird nicht geraten); `getaktet` erst mit dem Taktgeber (A18). Bestimmt im Loop (Backup alle 15 s im Block `_wiederherstellung`, vor dem Speichern), geschrieben nach `Aufnahme.speichern` an seinen Platz (`kopffeld_schreiben`); `backup_wiederherstellen` nimmt es aus dem Backup. `Recording.extra` hält es, `deid` behält es; Altdateien ohne Feld bleiben lesbar | `core/atem_protokoll.py`, `devices/messlauf.py`, `components/zaehl_stand.py`, `views/messung.py` |

Tests (ohne flet, wo es geht; die flet-freien laufen auch im gesperrten Kindprozess von
`tests/test_import_regel.py`): `test_zaehlen.py`, `test_zaehlen_geraete.py` (A3: Abschnitt
„Atmung“ — Atemzüge, Rate, Phasen im Beiwerk, ±1, `kein_atem`, Wdh + Atmung, Chip und
Anhalten, Trennen, Ratenwechsel, Rechenzeit, Simulator, Kontextzeile, Fehler im Prototyp),
`test_zaehlen_eintrag.py`, `test_zaehl_ablauf.py`, `test_zaehl_stand.py`, `test_ui_zaehlen.py`,
dazu Migration 037 und die Paket-Rundreise in `test_repositories.py`, `test_pakete.py`,
`test_paket_werkzeug.py`. B1: `test_atem_auswertung.py` (Größen je Messung und Abschnitt,
Schattenbereiche, F6, Vergleich), `test_atem_protokoll.py` (Regel, Platz im Kopf, Rundreise
über `Recording.extra` und `deid`, Messlauf: Backup, Speichern synchron und im Thread,
Wiederherstellen, Haken ohne und mit Fehler), `test_ui_atmung.py` (Auswertung: Ebene, Karte,
Hinweis, Schatten-Reihen, Chip; live: Schatten und Kopf mit der Gurt-Attrappe ohne Aufnahme,
Live-Vollbild), dazu die Doctests der beiden Kernmodule.

**B2** (5.11.2026, 0.3.47, hrv-core 0.10.0 — `hrv-core.ref` angehoben; Entscheidung 25 in
hrv-research, P134–P136): die **Atem-HRV je Atemzug** aus `hrv_core.prototyp.atem_hrv`.

| Stufe | Gebaut | Wo |
|---|---|---|
| B2 Auswertung | `atem_hrv_zuege` rechnet je Lauf „Atmung erfassen“ (nie über die Pause, je Lauf ein Prototyp) auf den Phasen des Beiwerks, den Prüffenstern (`FENSTER_S` lang bis zu ihrem Ende) und den RR-Abständen der **korrigierten Reihe** (wie die übrigen Kennzahlen; Schlagzeiten auf der Wanduhr, `hf_auswertung.achse_zu_wand_reihe`) alle Atemzüge; `atem_hrv` fasst je Bereich zusammen (`AtemHrvBereich`): Atemspanne (Median, Quartile ms; Median bpm; `ln`-Mittel), **Phasenlage als Sekunden ab Beginn des Einatmens** (P135: Median von Winkel/360 · Dauer je gültigem Atemzug; der Winkel als zirkuläres Mittel), RR je Phase (Mediane ein/aus, Differenz), Ein:Aus, Rate, Anteil gültig, Gründe mit Anzahl (`GRUND_TEXTE`). Die Karte „Atmung (Prototyp)“ zeigt je Messung vier Zeilen — „Atemspanne 62 ms (IQR 50–75) · 5,1 bpm“, „HF-Gipfel 4,0 s nach Einatembeginn“ (Tooltip „290°“), „RR ein 905 · aus 950 ms (Δ +45)“, „12 von 15 Atemzügen gültig — 2 zu wenig Schläge, 1 Lücke“ — und je Abschnitt eine Kurzzeile (`atem_hrv_kurz`); gemerkt je Korrektur-Auswahl (`z.merken("atem_hrv")`), nichts gespeichert (§7.4), keine Wertung | `core/atem_auswertung.py`, `core/hf_auswertung.py`, `views/messung_detail.py` |
| B2 Licht | **„Kennzahlen im Licht der Atmung“** (7.1): unter den Kacheln die Zeile „Atmung 6,1/min (Sensor) · Ein:Aus 1 : 1,4 · Atemübung Box Breathing“ (`licht_text`: Rate nach F6 mit Quelle, Ein:Aus aus dem Beiwerk, Protokollfeld in Worten) — nur mit Beiwerk oder Protokollfeld | `core/atem_auswertung.py`, `views/messung_detail.py` |
| B2 Regel F6 | **nach P136**: die Sensor-Rate gilt, wenn mindestens `MIN_FENSTER` = 3 Prüffenster gültig sind **und** mindestens `MIN_FENSTER_ANTEIL` = 25 % aller Fenster **und** die Läufe die Hälfte des Bereichs abdecken (`MIN_ABDECKUNG`); sonst die Atmung aus RR desselben Bereichs — im Modus **Atemübung, wenn das Protokollfeld `atmung` eine Übung oder getaktet nennt**, bei `spontan` Ruhe, die Benutzereinstellung nur ohne Feld (`rr_modus`; `messung_detail.atem_modus` für Kacheln, Abschnitte, Vergleich und Vollbild); Widerspruch über 2/min: der Sensor gilt, die Abweichung steht im Vergleich; unter 9/min bleiben LF/HF und α1 **als Zahl mit Hinweis** stehen, HF-Power wird nicht ausgewiesen (wie B1) | `core/atem_auswertung.py`, `views/messung_detail.py` |
| B2 Live | Läuft eine **Aufnahme**, rechnet der `ZaehlBaustein` neben der Atem-Spur `AtemHrvLive` (Phasen von der Achse der Einheit über `auf_messlauf`, Prüffenster von der Uhr der Quelle, Schläge aus `Messlauf.live` — korrigiertes RR, Verworfenes als NaN; beginnt eine Aufnahme, wechselt die Achse und der Prototyp fängt neu an); `atem_spanne_ms` ist die Spanne des letzten vollständigen Atemzugs (``None`` ohne Aufnahme, vor dem ersten, wenn er ungültig war). Angezeigt als „Spanne 58 ms“ neben Rate und Phase (`core.zaehlen.atem_text`, `zaehl_stand.atem_zeile`) — im Kopf des Live-Vollbilds (Tooltip: nach dem nächsten Prüffenster), in der Zählzeile und im Timer „Während“ (nur Atmung die kleine Zeile, Wdh + Atmung die dritte Zeile); Laufleiste und Benachrichtigung bleiben ohne. Ohne Aufnahme keine Spanne. Verzug bis zu einem Prüffenster (Entscheidung 25, Frage 6 offen — so gelassen) | `devices/zaehlen.py`, `core/zaehlen.py`, `components/zaehl_stand.py`, `views/live_vollbild.py` |

Tests B2: `test_atem_auswertung.py` (Abschnitt „Atem-HRV“: synthetische RR mit RSA und Phasen —
Spanne und Phasenlage bekannt, je Lauf, Lücke; Regel F6 in allen Fällen: 3 Fenster und 25 %,
Abdeckung, Modus aus dem Protokollfeld, Widerspruch; Texte), `test_ui_atmung.py` (Karte mit
den vier Zeilen, Phasenlage in Sekunden mit Winkel im Tooltip, Abschnittszeile, Licht-Zeile,
Modus aus dem Protokollfeld; LF/HF und α1 bleiben als Zahl mit Hinweis; live: Spanne mit der
Gurt-Attrappe und laufender Aufnahme, ohne Aufnahme keine), Doctests in
`core/atem_auswertung.py`, `core/zaehlen.py`, `core/hf_auswertung.py`.

**Grenzen von B2** (Entscheidung 25 in hrv-research, Eingang mit Ausnahme): geprüft an **einer
Sitzung mit Takt** (Simulator und Mensch) und einer unter Störung — nicht an zwei unabhängigen;
bei 15–20/min sind es nur etwa vier Schläge je Atemzug, die Spanne je Atemzug ist dann grob (der
Sinus ist die zweite Zahl) — **der Median über den Bereich trägt**, nicht der Einzelwert; ein
verpasster oder gespaltener Atemzug fällt über `dauer_untypisch` heraus; live hinkt die Spanne
bis zu einem Prüffenster nach, und der erste Atemzug einer Aufnahme fehlt meist (seine Schläge
kamen vor seiner Phase). Takt (Soll gegen Ist) und `getaktet` kommen mit T.

**Grenzen von A3** (Entscheidung 24 in hrv-research, `hrv_core.prototyp.atemzuege`): Der
Prototyp ist an **zwei Sitzungen eines Menschen** mit dem H10 am unteren Brustbein eingestellt
und geprüft (sitzend, liegend); die Verity Sense am Arm ist ungeprüft — die feste Richtung
(x − z) gilt nur für die Brust, der Knopf erscheint trotzdem (4.5). Langsames **und** flaches
Atmen (6/min flach) zeigt Doppeltäler, die Zahl stimmt dort nicht und die Fenster bleiben
ungültig (keine Rate). Der **erste Atemzug je ruhigem Stück** fehlt oder verschiebt sich
(Anlauf des Hochpasses) — nach jeder Bewegung beginnt ein Stück neu. Befunde beim Bau
(5.11.2026, für hrv-research): (1) aus Rauschen ohne Atemwelle (Simulator, 15 mG je Achse,
auch noch 2 mG) zählt der Prototyp Pseudo-Atemzüge, die Fenster bleiben ungültig — die Zahl
läuft, die Rate zeigt „–“; (2) `math domain error` in `_Summe` beim Übergang von der Welle zu
einem konstanten Signal (Rundung der laufenden Summe unter 0 vor `sqrt`) — die App fängt es
(`ZaehlBaustein.atem_fehler`, frischer Prototyp), die Korrektur gehört nach hrv-core.

**Bewusst noch nicht gebaut** (Abschnitt 11):

- **B1 Rest** das Resonanzprotokoll (nur Praxis, `physiologische_steuerung`, 7.1 b); die
  Atemspanne live ist mit B2 da.
- **T** Taktgeber im Timer (A18, eigener Plan).
- **A5** Live-Zähler je Wiederholung, Vorlagen (heute nur „Automatisch“), Umkehrpunkt; bis dahin
  zählt der Prototyp jede Sekunde das ganze Satzfenster neu.
- **A6** die Karte in „Im Plan einstellen“ und praxis_gui. Die Planübung folgt der Übung;
  den Knopf gibt es in einer Planübung nur, wenn sie ein Wiederholungsfeld anbietet.
- **Zählen im Plan-Ablauf** (4.3 Punkt 6, „automatisch weiter“): Der Ablauf trägt je Übung
  selbst ein (`ui.plan_ablauf.nach_der_uebung`); solange er läuft, gibt es keinen Knopf
  (`zaehl_stand.im_plan_ablauf`), der Start sagt „Im Plan-Ablauf zählt der Sensor noch nicht“.

**Nicht am Gerät geprüft:** Laufzeit je Rechnung am Handy (Ziel unter 20 ms; am Rechner etwa
2–11 ms bei kurzen Sätzen, bei 10 min mit 200 Hz bis gut 250 ms — dann rechnet der Teil seltener,
bis alle 5 s, `devices.zaehlen.takt_nach`; eine Rechnung selbst hält die Schleife so lange auf),
STOP/START der ACC beim Ratenwechsel am echten H10 und an der Verity Sense (nur gegen
den Fake-Transport), Größe der Flächen ±1 und die Breite der Zählzeile, die Meldung nach einem
Blatt. Ob das Umtakten 200 → 50 Hz den Prototyp verfälscht, prüft hrv-research an den
200-Hz-Mitschnitten.

**Lücken der ersten Runde — erledigt** (4.11.2026, zweite Runde; jede mit einem Test, der
ohne die Änderung scheitert):

- **Chip mit Wert** (`chip_erlediger` in `views/plan.py`): Zählt der Sensor, endet das Zählen
  zuerst als `abgehakt` (`uebung_lauf.zaehlen_beenden`); der Wert des Chips kommt beim
  Schließen in den Eintrag mit den Wiederholungen (`SessionRepo.eintrag_schliessen` mit
  ``werte``, eine Korrektur) — kein zweiter Stempel, nicht noch das Ziel (wie „Wie geplant“).
  Tests: `test_ui_zaehlen.py::test_chip_mit_wert_beendet_das_zaehlen_und_schliesst_einen_eintrag`,
  `test_repositories.py::test_abschliessen_mit_werten_in_einer_korrektur`.
- **Laufleiste in den Plan** (`ui.einheit.ziel_merken`, aufgerufen von
  `components/startleiste._oeffner` beim Tipp): Das Zählen einer Planübung setzt
  `state.plan_ziel` und `plan_offen` — die Liste beginnt bei der Übung, aufgeklappt, wie
  „Weiter mit …“ auf „Heute“. Test: `test_ui_zaehlen.py::test_laufleiste_fuehrt_im_plan_zur_uebung`.
- **Der Kontext des Abhakens gewinnt** (`zaehlen_beenden(…, ort=(Plan, Planübung))`,
  `_ort_uebernehmen`; `UebungBaustein`/`ZaehlBaustein.kontext_setzen`): Begann das Zählen auf
  der Übungsseite und wird auf „Heute“ oder im Plan abgehakt, landet der Eintrag in der
  Sitzung dieses Plans, einmal; die Uhr derselben Einheit trägt später ebenfalls dort ein, die
  Beteiligungen nennen den Plan. Bietet die Planübung kein Wiederholungsfeld an (P79), endet
  das Zählen als `abbruch` und bleibt nachtragbar, wo es begann. Tests:
  `test_zaehl_ablauf.py::test_abhaken_im_plan_nach_dem_start_ohne_plan_landet_im_plan`,
  `…::test_abhaken_im_plan_neben_der_uhr_nimmt_die_uhr_mit`,
  `…::test_abhaken_in_einer_planuebung_ohne_wiederholungen_bricht_das_zaehlen_ab`,
  `test_ui_zaehlen.py::test_abhaken_auf_heute_nach_dem_start_auf_der_uebungsseite`.
- **Meldung, wenn das Zählen von selbst endet** (`ui.einheit._von_selbst_melden`,
  `core.zaehlen_eintrag.von_selbst_text`, `ZaehlBaustein.getrennt`): 60 s ohne Bewegung oder
  das Gerät getrennt, abgebrochen, etwas gezählt — 5 s „Kniebeuge · 12 Wdh. nicht eingetragen
  — 60 s ohne Bewegung“ bzw. „— Sensor getrennt“ mit „Eintragen“, dieselbe `ZaehlMeldung` wie
  bei einer anderen Übung: gezeigt beim nächsten Aufbau der Ansicht (`ui.app`), nie über einem
  Dialog, einmal (`meldung_abholen`). Auf einen Tipp („Zählen abbrechen“, Abhaken) und beim
  Abbruch der Uhr gibt es keine. Tests: `test_zaehl_ablauf.py::test_von_selbst_beendet_meldet_sich_einmal`,
  `…::test_getrennt_meldet_sich_mit_grund`,
  `test_ui_zaehlen.py::test_von_selbst_beendet_zeigt_die_meldung_einmal`.
- **`trainingsapp-paket pruefen`** prüft `beschleunigung` (`core.zaehlen.wahl_pruefen`): ein
  falscher Typ (`wiederholungen = "nein"`, `atmung = 1`, keine Tabelle) ist ein Fehler wie eine
  fehlende Beschreibung — die Wahl ginge beim Einlesen still verloren —, ein unbekannter
  Schlüssel ein Hinweis wie ein Typ außerhalb des Standardpakets (Tippfehler oder neuere App).
  Die App liest weiter tolerant. Test:
  `test_paket_werkzeug.py::test_pruefen_meldet_unsinn_in_beschleunigung`, Doctests in
  `core/zaehlen.py`.

**Dritte Prüfrunde** (5.11.2026; jede Korrektur mit einem Test, der ohne sie scheitert):

- „Eintragen“ der Meldung, während die Uhr derselben Einheit weiterläuft, trägt nur die
  Wiederholungen ein; die Zeit kommt mit dem Ende der Uhr in denselben Eintrag
  (`uebung_lauf._laufende_teile`).
- P122 in der Karte „Eintragen“: Solange der Sensor in ein Feld zählt, hat dessen Zeile weder
  Chips noch eigenen Wert, ein alter Knopf hängt nichts an (`zaehl_stand.zaehlt_der_sensor`);
  im Diagnosemodus zählen beide.
- P79 auch, wenn Uhr und Zählen zusammenkommen: Eingetragen wird, wo die Uhr läuft — bietet ihre
  (Plan-)Übung kein Wiederholungsfeld an, tritt das Zählen nicht bei bzw. macht Platz
  (`_zaehllauf_von`, `zaehlen_starten`).
- Zählen im Plan-Ablauf: kein Knopf mehr, der nie zählte (oben unter „noch nicht gebaut“).
- Notiz zum Satz: Mit laufender Aufnahme bekommt jeder eingetragene Satz `person/leistung`
  (`uebung_lauf._satz_notizen`); im Diagnosemodus vergleicht sie nicht noch einmal
  (`Messlauf._schon_verglichen`).
- Ströme: Kommt ein Zurück, während der ältere Auftrag noch umschaltet, räumt nur der jüngste
  auf (`Messlauf._stroeme_nr`) — vorher liefen EKG und Beschleunigung nach dem Vorabtest bzw.
  nach „Zählen abbrechen“ gleich nach dem Tipp weiter.
- Ende: ein Funkabriss sofort als „Sensor getrennt“, 15 s ohne Beschleunigung als „keine Daten
  vom Sensor“ (`KEINE_DATEN_S`), ein Satz länger als der Puffer als „Satz zu lang für den
  Sensor“ (`Messlauf.acc_verloren_bis`) — jeweils `abbruch`, nachtragbar.
- Absturz: Die `zaehlung` steht mit dem Ende des Satzes in der Zeitleiste (ein laufender alle
  15 s, `ZWISCHENSTAND_S`) — passend zur Zeit der Uhr nachtragbar.
- Laufzeit: Dauert eine Rechnung länger als 20 ms, wird seltener gerechnet (§5.2, `takt_nach`).

**Vierte Prüfrunde** (5.11.2026; jede Korrektur mit einem Test, der ohne sie scheitert):

- Mitschnitt: Die Kontextzeile `satz` eines gezählten Satzes, der mit dem Ende eingetragen wird,
  schreibt `Messlauf.zaehlsatz_vergleichen` an seinem Ende, vor `uebung_ende` (mit `satz`); die
  Notiz zum Satz, die erst nach dem Ende der Einheit kommt, schreibt keine zweite. Vorher stand
  sie hinter `uebung_ende`, hrv-research legte jeden gezählten Satz in eine Gruppe ohne Übung.
- Diagnosemodus: Wird ein abgebrochener Satz neben der laufenden Uhr doch eingetragen („Eintragen“
  der Meldung), bekommt sein Vergleich den Wert, statt dass ein zweiter mit leerem Fenster ihn
  ersetzt (`Messlauf._nachgetragen`); nicht eingetragene Sätze warten darauf nur, solange ihre
  Einheit lebt (`Messlauf.zaehlsaetze_vergessen`).
- Diagnosemodus, beide zählen: Ein Chip im Feld, in das der Sensor zählt, ist der Satz des
  Sensors — er endet dort (`ZaehlBaustein.von_hand`, in der Pause der Uhr der letzte), `zaehlung`
  bekommt `von_hand` (`docs/plan_einheit.md` §4), und am Ende trägt der Sensor ihn nicht noch
  einmal ein. Vorher stand jeder Satz doppelt da.
- Absturz mitten in einem zählenden Abschnitt: Werden Zeit und Wiederholungen zusammen
  nachgetragen, zählt der Abschnitt bis zum letzten Zwischenstand seines Satzes
  (`core.zaehlen_eintrag.zeiten_der_uhr`) — ein Stand für beide; vorher fehlte seine Haltezeit,
  die Listen waren verschoben. Ohne die Wiederholungen fehlt er wie bisher.
- Gedrosselt (`takt_nach`) zählt der Prototyp vor dem Urteil „keine Bewegung“ bis jetzt — vorher
  urteilte ein bis zu 5 s alter Stand.
- Die Stoppuhr, gestartet, während ein Satz schon zählt, misst diesen Satz (ein Lauf der
  Stoppuhr ist ein Satz); Intervall-Timer beginnen weiter je zählendem Abschnitt einen.
- Marken-Leiste im Diagnosemodus: Während eines Zähllaufs kommt die Satznummer der Marken aus dem
  Zähl-Teil derselben Übung (`Messlauf.zaehl_satz` → `core.diagnose.kontext_aus_notizen`);
  eine Notiz zum Satz während des Laufs (ein Chip, `von_hand`) zählt nicht noch einmal.
  Vergleich und Kontextzeilen tragen dieselbe Nummer. Vorher trugen mit der Uhr (mehrere
  zählende Abschnitte, kein Chip) alle Marken „S1“, Kopfzeile und Uhr ebenso, und hrv-research
  legte sie alle zu Satz 1. (Seit der fünften Runde kommt die Nummer aus den Zeilen ``satz``.)
- Wechselt der Kontext mitten im Lauf (die Uhr tritt bei, abgehakt in einem Plan), steht er sofort
  in der Zeitleiste (`Einheitslauf.fortschreiben`), und „Eintragen“ einer lebenden Einheit nimmt
  den im Speicher — nach einem Absturz wie ohne ihn derselbe Plan, dasselbe Zeitfeld.
- Oberfläche: Im Reiter „Einheit“ hat ein Zähllauf ohne Uhr keine Zeile „Übung · … — trägt die
  Zeit ein“ mehr; „Wie geplant“ fehlt, solange der Sensor zählt; kein Knopf „Wdh. zählen“, solange
  etwas bereitsteht; „Läufe heute“ nennt einen Zähllauf ohne Zahl „nichts gezählt“ bzw. „Atmung“
  statt „gemacht“, ohne Nullsatz, „Fertig“ der Atmung verspricht kein Eintragen; in der Karte
  „Eintragen“ heißt der Knopf eines Laufs „Nachtragen“.

**Fünfte Prüfrunde** (5.11.2026; Diagnosemodus, beide zählen — jede Korrektur mit einem Test,
der ohne sie scheitert):

- Die Satznummer der Marken, des Vergleichs und der Kontextzeilen ist die der Zeile ``satz``, die
  hrv-research dem Satz zuordnet (die k-te nach ``uebung_start``): `Messlauf.marken_satz`,
  `naechster_satz`, `ZaehlSatz.diag_nr` — die Zeilen seit dem Start plus die gezählten Sätze,
  deren Zeile erst mit dem Ende kommt. Jeder gezählte Satz bekommt eine Zeile, ein nicht
  eingetragener ohne ``feld``/``wert`` (`docs/kompatibilitaet.md` §14); vorher rückten die
  Eingaben nach einem leeren Satz um einen.
- Satz von Hand neben dem Sensor (`ZaehlBaustein.von_hand`): Mit der Uhr beginnt der nächste Satz
  erst mit dem nächsten zählenden Abschnitt — nicht mitten darin, nicht bei angehaltener Uhr
  (vorher zählte der Rest als eigener Satz bzw. dieselben Daten doppelt); ein Satz von Hand unter
  5 s bleibt einer; „2 × 6“ sind zwei Sätze (`views/plan.anhaengen` je Wert). Gingen ihm Sätze
  voraus, die nur der Sensor zählte, kommen sie zuerst ins Tagebuch und in den Mitschnitt
  (`ZaehlBaustein.vorziehen`, `ui.uebung_lauf.vor_dem_satz_von_hand`; ``von_hand`` in der
  Zeitleiste); das Zählen läuft weiter. Ein Satz von Hand hat eine Zeile ``zaehler``, nicht zwei.
- Nur die Notizen beim Eintragen eines gezählten Satzes gehören zu ihm (`Messlauf.zaehl_notizen`
  um `ui.uebung_lauf._eintragen`): Ein Chip mit zufällig gleichem Wert galt sonst als Nachtrag
  eines abgebrochenen Satzes und wurde nie verglichen.
- Zählt ein Satz, gelten in der Leiste seine Übung und die Phase „Übung“ (``offen``) — vorher
  waren die Tipps der ersten 5 s jedes Abschnitts Atemzüge (die Notizen warten 5 s). Die Uhr
  allein (ohne Zählen) hat diese 5 s weiter.
- Absturz, nachdem das Zählen mitten im Abschnitt endete und die Uhr weiterlief: keine Haltezeit
  bis zum Ende des Zählens mehr (`core.zaehlen_eintrag.uhr_bis`), lieber eine Lücke.
- Der Einmal-Timer (eine Runde) misst wie die Stoppuhr den Satz, der schon zählt.

**Fünfte Prüfrunde zu A3/B1** (5.11.2026, drei Prüfer: Atem-Spur, Auswertung, Vertrag — jede
Korrektur mit einem Test, der ohne sie scheitert):

- Beiwerk auch, wenn die Aufnahme erst nach dem Start der Atem-Spur beginnt oder eine zweite
  folgt: `Messlauf.atem_aktiv` merkt die laufende Spur, jede Aufnahme legt ihren Sammler mit
  einem Lauf ab 0 an (`_atem_laufend_anlegen` — Start, Teil 2, zweite Aufnahme); Stopp schließt
  den offenen Lauf am Stopp (vorher am letzten Fenster, bis 5 s früher). Tests:
  `test_messlauf.py::test_aufnahme_waehrend_laufender_atem_spur_bekommt_beiwerk`,
  `::test_stopp_schliesst_den_atem_lauf_am_stopp`.
- Keine negativen Zeiten: Eine Phase, deren Ansatz vor der Naht lag und die danach bestätigt
  wurde, fällt in Teil 2 weg (`Messlauf.atem_phase`/`atem_fenster`); Lauf-Grenzen von davor liegen
  bei 0 (`::test_phasen_von_vor_dem_aufnahmestart_fallen_weg`).
- Der Lauf im Beiwerk beginnt mit der ersten Probe, nicht mit dem Tipp (`ZaehlBaustein._atem_begonnen`);
  ohne eine Probe kein Lauf, kein Beiwerk und keine ``zaehlung`` der Atem-Spur
  (`test_zaehlen_geraete.py::test_atem_lauf_erst_mit_dem_ersten_rahmen`).
- `core.zaehlen_eintrag.uhr_bis` nimmt nur die ``zaehlung`` eines Satzes (``zaehlart`` wdh), nie den
  Zwischenstand der Atem-Spur (`test_zaehlen_eintrag.py::test_uhr_bis_uebergeht_den_zwischenstand_der_atem_spur`).
- Auswertung: Phasen werden nur innerhalb eines Laufs gepaart (`atem_auswertung.je_lauf`; kein
  Atemzug, kein Schatten über die Pause, ein letztes „ein“ schattiert bis zum Laufende); die
  Startregel F6 gilt **je Bereich** — Sensor-Rate nur, wenn die Läufe mindestens die Hälfte des
  Bereichs abdecken (`MIN_ABDECKUNG`, `AtemKennzahlen.abdeckung`) und die Hälfte der Fenster gültig
  ist, sonst die Atmung aus RR desselben Bereichs (`messung_detail.rr_atmung_in`); der Hinweis steht
  auch in der Zeile eines Abschnitts („Atmung im LF-Band“), die Bandleiste des Analysefensters
  (`components.spektrum.band_leiste`, `Analyse(atem_hinweis=…)`) und „HF n.u.“ in der Frequenztabelle
  folgen ihm; der Vergleich in der Karte nimmt die Atmung aus RR der erfassten Läufe; die Karte
  nennt die Atemübung mit Namen. Die Ebene „Atmung“ ist auch bei bestehenden Installationen an
  (`hrv_einstellungen.ebenen_lesen`, Merkliste ``ebenen_bekannt``). Tests: `test_atem_auswertung.py`,
  `test_ui_atmung.py`, `test_hrv_einstellungen.py::test_neue_ebene_ist_bei_alter_installation_an`.
- Vertrag: §15 nennt die Grund-Codes wie der Prototyp sie schreibt (`ungleichmaessig`,
  `gipfel_undeutlich`, `zyklen_passen_nicht`; der erste der Prüfreihenfolge), `rate_hz` als
  int/float/null, den Laufbeginn mit der ersten Probe, die deid-Kopie als inhaltlich gleich;
  §3/§5 den Platz von `atmung` nach `Recording.to_dict`; hrv-core 0.9.2 (`deid` entfernt
  `_journal` wie `_wiederherstellung`, `docs/formate.md`); `test_atem_auswertung.py` und
  `test_atem_protokoll.py` laufen im flet-gesperrten Kindprozess mit.
- Nicht geändert (Vorbestand, hier nur genannt): Die Verlaufskurve `hf_power` und der
  Kennzahlen-Cache kennen den Hinweis nicht (nicht Teil von B1); ein zweiter Lauf mit anderer
  Rate behält im Kopf des Beiwerks `rate_hz` des ersten (die Rate steht je Messung, nicht je Lauf).

**Entschieden (Ben, 5.11.2026)** zu den Fragen aus den Prüfrunden:

| # | Frage | Entscheidung |
|---|---|---|
| P127 | „Prototyp“ an jeder Zahl (§10) — Leiste, Benachrichtigung, „Läufe heute“, Meldungen tragen es nicht | **lassen**, wie in 4.2/4.3 gebaut; §10 gilt für Karten und Zählzeile |
| P128 | Zählen im Plan-Ablauf | **später** (Katalog A19); der Knopf bleibt dort ausgeblendet |
| P129 | Zwischenstände der `zaehlung` alle 15 s, es gilt die letzte je Satz | **ja** |
| P130 | Funkabriss oder 15 s ohne Daten: sofort abgebrochen, Meldung mit „Eintragen“, keine Schonfrist | **passt** |
| P131 | Lange Sätze: Rechnung gedrosselt bis alle 5 s, dauerhaft der Live-Zähler (A5) | **gut** |
| P132 | Chip im Diagnosemodus neben dem Sensor | **„Chip und Satz sollen sich ergänzen“**: der Chip ist der eingetragene Wert des Satzes, den der Sensor zählte (`von_hand`), das Zählen läuft weiter. Wer von Hand eintragen oder nachtragen will, bricht das Sensorzählen ab und macht es direkt in den Leistungen — der Sensor und die Chips teilen sich außerhalb der Diagnose nie ein Feld (P122) |
| P133 | Mit der Uhr beendet ein Chip den Satz seines Abschnitts; der Rest des Abschnitts zählt nicht mehr | **genau** — **außer die Atmung**: Wird sie für die HRV erfasst, läuft sie nebenbei weiter, unabhängig von Sätzen, Chips und Abschnitten (ein Chip rührt einen Atem-Lauf nicht an, `von_hand` gilt nur für Wiederholungen; für A3 verbindlich) |
