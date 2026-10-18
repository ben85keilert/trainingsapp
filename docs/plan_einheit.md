# Einheit: HRV, GPS, Timer und Plan gemeinsam

Ben, 17.10.2026: „HRV, GPS-Aufzeichnung, Timer, Plan/Übungen sind verschiedene
Komponenten, die miteinander gekoppelt werden sollen … Man bereitet alles vor und wenn
man soweit ist, klickt man auf Start und es läuft los.“ Für spätere Auswertungen (Deep
Learning: DFA α1 gegen RMSSD je Belastung, Tempo aus GPS, welche Übung wann) muss
**jedes Ereignis auf einer Zeitachse** liegen.

Skizzen der Oberfläche (21 Bildschirme, Reihe F: Startleiste kompakt, §9):
https://claude.ai/artifact/5m4q9AhyKnw5nMjWcwPjUs

## 1. Begriffe

| Begriff | Bedeutung |
|---|---|
| **Einheit** | die Klammer um alles, was zusammen läuft (`core/einheit.py`, `devices/einheit.py`) |
| **Teil** | HRV-Messung, Timer, Ausdauertraining, Plan-Ablauf (`Baustein`). Das Training ist der Teil `gps` (`devices/strecke_baustein.StreckeBaustein`) — mit GPS eine Strecke, ohne GPS (Laufband, Halle) nur die Zeit, wie eine `Strecke` ohne Datei |
| **Bereitstellen** | ein Teil macht sich fertig und wartet auf den gemeinsamen Start: Gurt verbunden, GPS hat Empfang, Profil geladen. Ein zweiter Knopf neben „Start“ (Ben, 17.10.: nicht der Sammelmodus mit Fahne) |
| **Startleiste** | was bereitsteht: oben auf jeder Seite als **Infoleiste** (eine Zeile), ausführlich als **Startkarte** im Reiter „Einheit“ auf „Heute“ — jeder Teil mit Stand, „Wenn der Timer fertig ist …“, Countdown, „Alle starten“ (§9) |
| **Laufleiste** | dieselbe Stelle nach dem Start: eine Zeit, der laufende Abschnitt, ⏸ ⏹ für alle; im Reiter „Einheit“ statt ihrer die **Übersicht** mit der Fortschrittsleiste des Timers (§9) |
| **Zeitleiste** | die Ereignisse einer Einheit in der Datenbank (Migration 018) |

## 2. Gemeinsamer Start — zwei Schritte

1. **Vorbereiten** (`async vorbereiten`, alle Teile parallel): verbinden, auf den
   GPS-Fix warten (≤ 30 m), Profil oder Plan laden. Darf dauern und scheitern; die
   Startleiste zeigt den Stand je Teil.
2. **Starten** (`starten(t0)`, **synchron**): Die Einheit liest einmal die Uhr und
   gibt allen Teilen in einer Schleife ohne `await` denselben Zeitpunkt. Im
   Event-Loop geschieht dazwischen nichts — **gleichzeitig heißt gleiches t0**, nicht
   „im selben Augenblick angelaufen“.

**Rollen** (`Rolle`):

- `mitstarten`: startet mit „Alle starten“.
- `laeuft_schon`: lief schon (die HRV-Messung seit einer Stunde). Startet nicht neu,
  bekommt eine Marke und läuft danach weiter.

**Ende** — Vorgabe „was ich nicht gestartet habe, stoppe ich nicht“, je Teil
umschaltbar („Wenn der Timer fertig ist: GPS beenden ✓, HRV beenden ☐“) — auch noch im
Lauf, bis der Timer fertig ist (§9). Eine mitstartende HRV-Messung mit Dauer („15 min“)
endet nach Wahl mit dem Timer oder läuft weiter. **Die HRV pausiert nie** — eine Pause ist ein Abschnitt.

**Countdown 3-2-1** (wählbar): t0 ist sein Ende. Eine mitstartende HRV-Aufnahme
beginnt schon beim Countdown (Vorlauf, `versatz_s = −3`), sonst fehlten die ersten
Schläge.

## 3. Eine Achse, je Uhrdomäne ein Anker

- `Zeitbasis`: monotone Uhr und UTC einmal nacheinander gelesen. Jedes Ereignis trägt
  `t_s` = Sekunden seit t0 auf der monotonen Uhr; UTC folgt als `anker_utc + t_s`,
  nie aus einem zweiten `now()`.
- Die Uhr der Einheit ist `Messlauf.uhr`, wenn die HRV dabei ist (beim Simulator läuft
  sie schneller), sonst `time.monotonic`. Der Timer bekommt dieselbe Uhr.
- **Beteiligung** (`einheit_baustein`): Zeit des Teils + `versatz_s` = `t_s`. Bei der
  HRV ist die Zeit des Teils `t_wall_s` der Messdatei. Versätze stehen nur monoton —
  `start_utc` der Messdatei hat ganze Sekunden.
- GPS: Fix-Zeit über `UhrAbgleich().umrechnen(p.t, jetzt=p.t_empfang)`, nicht die
  Verarbeitungszeit. ``t_empfang`` steht auf der Uhr der Quelle; führt die Einheit
  eine andere (Simulator, GPS-Simulator, Wiedergabe), rechnet der Teil sie über den
  Abstand beider Uhren um. Die Beteiligung `gps` trägt den Versatz der Empfängeruhr
  (`Punkt.t` + `versatz_s` = `t_s`) — am Ende nachgetragen, dann ist der Abgleich am
  genauesten.
- **Tiefschlaf:** Die monotone Uhr steht, wenn Android die CPU schlafen legt. Darum hält
  jede Einheit den Vordergrunddienst (Gurt: `connectedDevice`, GPS: `location`, sonst
  `health` — Ben, 17.10.; ein Timer allein ebenso). Liegt zwischen zwei Takten doch
  Tiefschlaf, steht `einheit/schlaf` in der Zeitleiste.

## 4. Zeitleiste und Projektionen

Die **Zeitleiste ist die Provenienz** („was die App beobachtet hat“): sofort
geschrieben, unveränderlich, `nr` fortlaufend (`data/einheiten.py`). Daraus werden
**Projektionen**, die nie zurückgelesen werden — die Person darf sie bearbeiten:

| Ereignis | in der Messdatei | Spur |
|---|---|---|
| `einheit/start`, `einheit/ende` | Notiz „Start: …“, Abschnitt der Einheit — nur wenn die HRV schon lief | `einheit` |
| `timer/abschnitt` | Notiz mit Marke, Abschnitt „Belastung (Runde 2/8)“ | `timer` |
| `timer/pause`, `timer/weiter` | Notiz, Abschnitt endet bzw. geht weiter | `timer` |
| `timer/ende` | „Timer fertig“, letzter Abschnitt endet | `timer` |
| `gps/start` | stille Grenze: „km 1“ (Rad „km 5“) beginnt mit der ersten gezählten Ortung | `km` |
| `gps/km` | Notiz „km N“ zur Split-Zeit; der nächste Abschnitt heißt nach seinem Ende („km 2“, Rad „km 10“) | `km` |
| `gps/ende` | stille Grenze, letzter km endet | `km` |
| `plan/uebung_start`, `plan/uebung_ende` | Notiz „Planke beginnt“ / „Planke fertig“ mit dem Kurzcode der Übung (`uebungen`, Vertrag §4), Abschnitt der Übung | `uebung` |
| `plan/pause` | Pause zwischen zwei Übungen eines Plan-Ablaufs, bis „Weiter“ — Abschnitt „Pause“ | `uebung` |
| `plan/ende`, `person/eintrag` | — (nur Zeitleiste: Ende des Ablaufs, was eingetragen wurde) | |

- **Marken** in der Messdatei: `docs/kompatibilitaet.md` §4. **Spuren**: §9b — eine
  Grenze teilt nur ihre Spur, Abschnitte verschiedener Spuren überlappen sich.
- **5-s-Regel** (Ben, 17.10.): Ein Abschnitt, der kürzer als `MIN_MARKE_S` lief,
  bekommt keine Marke und keinen Abschnitt. Die Einheit hält eine Anfangsmarke zurück,
  bis ihr Abschnitt 5 s lief, und setzt sie dann an seine echte Anfangszeit. Die
  Zeitleiste behält alles.
- Tagebuch: Einträge mit Anfang und Ende (Stufe 3, §7).
- **Training ↔ Einheit** (Migration 019): Die Zeile `strecke` trägt `einheit_id`.
  Über die Einheit findet die Auswertung die HRV-Aufnahme auch, wenn sie schon vorher
  lief und weiterläuft (`hrv_recording_id` bleibt dann leer), und legt Ortungen und
  Schläge über die Versätze aufeinander (`ui/training.hrv_bezug`): `t_wall_s` =
  `Punkt.t` + `versatz_gps` − `versatz_hrv`. Nach einem Absturz nennt die Zeitleiste
  beide Dateien — Backup und verwaiste Strecke finden einander (H16).

## 5. Regeln

- **Ortsfrei** (`docs/plan_gps.md` §0): Ereignisse tragen nur Felder aus
  `DATEN_SCHLUESSEL` (`core/einheit.py`) — keine Koordinate, keine Richtung, keine
  Höhenreihe; Tempo und Distanz ja. Die `datei` einer GPS-Beteiligung wird nie
  synchronisiert.
- **Keine Messwerte** in der Zeitleiste — die Messdatei ist die Wahrheit.
- **Steuerung geht vom Ablauf aus**, die Messung wird nur markiert. Steuerung aus
  Messwerten nur über `core/limits.auswerten` mit Edition (Praxis,
  `physiologische_steuerung`), keine Zonen.
- Ein Teil kennt die anderen nicht; die Einheit sammelt im Takt (`Baustein.takt`),
  schreibt, projiziert und meldet einem Beobachter („Stern statt Netz“).
- GPS hat einen Konsumenten: Eine Einheit mit GPS läuft nicht neben GPS-Test oder
  Ausdauertraining; der Timer einer Einheit wird nicht von `lauf_fuer` ersetzt.

## 6. Stufen

| Stufe | Inhalt | Stand |
|---|---|---|
| 0 | hrv-core: `spuren_speichern`, `notiz(..., marke=)`; Vertrag §4/§9b | gebaut 17.10. |
| 1 | Zeitleiste, `Einheitslauf` mit HRV, Timer, GPS; Startleiste, Laufleiste, Bereitstellen; Dienst `health` | gebaut 17.10.; Messung mit Dauer und Ablauf (A11): „Dauer der Messung“ in der Gerätekarte, Start als Einheit aus HRV und Timer, „Bereitstellen“; Startleiste kompakt — Infoleiste, Reiter „Einheit“, Übersicht mit Fortschrittsleiste (§9) |
| 2 | Ausdauertraining als Einheit (verknüpft auch eine schon laufende HRV, Abgleich über `versatz_s`, Wiederherstellung H16) | gebaut 17.10.; Tabellen „Intervalle“ und „Kilometer“ live und in der Auswertung (A10, `core/intervalle.py`) |
| 3 | Timer an Übung, Planübung und Plan (mehrere Profile, „zählt“, Abbrechen), Plan-Ablauf, Einträge mit Anfang und Ende — Migration 020 | gebaut 17.10. (§7); „vom Timer“ unter „Heute geleistet“ gebaut (A13) |
| 4 | Forschungsexport (ausdrückliche Handlung): Messdateien, Zeitleiste `einheit-v1.json`, ortsfreies Tempo | gebaut 17.10. (§8), in der Auswertung des Trainings und der HRV-Messung |

## 7. Timer an der Übung und Plan-Ablauf (Stufe 3)

Ben, 17.10.2026: „Grundsätzlich sollte man dem Plan auch einen Timer geben können oder der
einzelnen Übung“ — und: „Aus dem Text heraus weiß die App nicht, was Übungszeit ist.“

- **Profile** (`core/timer.py`): Ein Profil kann eine **Folge** sein — Teile mit eigenen
  Runden (Vorbereitung 1 ×, Halten und Pause 3 ×, Cooldown 1 ×). Je Abschnitt **„zählt“**
  (Vorgabe: alles zählt, die App rät nicht aus dem Namen). `TimerLauf.abbrechen` hält an
  und markiert (kein Eintrag), `fertig_machen` („Fertig“) beendet mit der gelaufenen Zeit.
- **Wo der Timer hängt** (Migration 020, `core/uebung_timer.py`): Profile an der Übung
  (Paketfeld `timer`; ohne eigene gilt eine Timer-Regel im `limit_spec` als Einzeltimer),
  „Timer für alle Übungen“ am Plan, die Wahl der Planübung (`TimerWahl`: Profil der Übung
  oder eigene Kopie, gemerktes Zeitfeld, „Zeit eintragen“). **Vorrang:** Planübung > Plan >
  erstes Profil der Übung > keiner.
- **Übungslauf** (`ui/uebung_lauf.py`, `devices/einheit.UebungBaustein`): Die Uhr neben dem
  i öffnet den Timer der Übung; er läuft als Einheit aus Übung und Timer (eine laufende HRV
  bekommt Marken). Endet er, wird eingetragen — aus der Zeitleiste
  (`core/timer_eintrag.py`): Haltezeit je zählendem Abschnitt oder die Summe als Zeit
  gesamt; Pausen des Timers zählen nicht, unter `MIN_MARKE_S` fällt ein Abschnitt weg.
  Der Eintrag bekommt Anfang und Ende, die Zeitleiste `person/eintrag`. Abgebrochen:
  nichts — „Läufe heute“ bietet „Eintragen“ an (`lauf_eintragen`).
- **Plan-Ablauf** (`core/plan_durchlauf.py`, `devices/plan_ablauf.py`, `ui/plan_ablauf.py`):
  aus dem Timer des Plans („Ablauf öffnen“). Übung für Übung mit ihrem Timer (auf derselben
  Achse: ein `TimerBaustein` je Übung mit Bezug t0), ohne Timer zum Abhaken; danach Pause
  bis „Weiter“ (`plan/pause`) oder automatisch weiter, wie am Plan eingestellt;
  `plan/ende` beendet die Einheit (`ende_mit_plan`). Jede Übung wird eingetragen, **sobald
  sie endet** (`Einheitslauf.nachtragen` schreibt `person/eintrag`). Laufleiste, ⏸ und Töne
  folgen dem Timer der laufenden Übung (`Einheitslauf.timer`).
  Ben, 18.10.2026: Vorher ist abgehakt, was heute schon gemacht ist — es kommt nicht dran
  (`bereitstellen(ohne=…)`, auf Wunsch wieder mitnehmen), ▶ beginnt bei einer Übung
  (`erste`), ist alles abgehakt, heißt der Knopf „Noch einmal“. Nach einer Übung ohne Timer
  kommt die Pause nur, wenn `plan.pause_no_timer` (Migration 021). Eine wartende Übung lässt
  sich jederzeit wählen (`PlanAblaufBaustein.waehlen`): die laufende endet mit
  `plan/uebung_ende` Grund **„gewechselt“** (kein Eintrag, sie bleibt offen; ein laufender
  Countdown fragt vorher), weiter geht es mit der ersten offenen Übung in der Reihenfolge des
  Plans (`naechster`). Ohne Timer läuft die Uhr der Übung vorwärts (`seit_s`).
- **Übungsformular** (Ben, 17.10.2026): Abschnitt „Timer“ mit den Profilen der Übung —
  Reihenfolge (das erste ist die Vorgabe), entfernen, „Timer hinzufügen“ (neu oder eine
  Kopie aus der Bibliothek) gehören zum Formular; der Stift öffnet den Editor (Teile,
  „zählt“) über dem Formular (`…/bearbeiten/timer/profil/<Profil>`), vorher speichert
  das Formular. Ohne eigenes Profil nennt es die Timer-Regel der Übung.
- **„vom Timer“** (Skizze 12): Unter „Heute geleistet“ steht bei einem Eintrag vom Timer
  „vom Timer, 10:07“, auf der Seite „Leistungen“ Anfang und Ende des Laufs — erkannt an
  `person/eintrag` in der Zeitleiste (`EinheitRepo.eintraege_vom_timer`); ein Training
  mit Ende allein zählt nicht.
- **Kurse** zählen Timer-Einträge wie alle anderen (Bedingungen `summe`, `tage`) — nie
  Messwerte.

## 8. Forschungsexport (Stufe 4, `einheit-v1`)

Für die Auswertung außerhalb der App (hrv-research: DFA α1 gegen RMSSD je Belastung, Tempo
aus GPS, welche Übung wann). **Ausdrückliche Handlung** wie „GPX exportieren“: in der
Auswertung eines Trainings oder einer HRV-Messung, die zu einer Einheit gehört, das Symbol
„Für die Auswertung exportieren (ohne Ort)“; ein Dialog sagt, was hineingeht (lief die
Messung über mehrere Einheiten, wählt man eine), dann das Teilen-Menü
(`ui/components/forschung.py`, `ui/training.forschung_export`, `core/forschung.py`).

**Das ZIP** (`einheit_<JJJJ-MM-TT_HHMM>.zip`):

| Pfad | Inhalt |
|---|---|
| `einheit-v1.json` | Kopf, Teile, Zeitleiste, Tempo (unten) |
| `Messungen/<Gerät>/sensor_….json` | jede Messdatei der Einheit **byte-genau**, mit Beiwerk (`_analyzed.json` mit den Korrekturen, `_diagnose.txt`, …) — wie der Messungs-Export (`core/hrv_export.zugehoerige_dateien`) |

**`einheit-v1.json`:**

| Feld | Bedeutung |
|---|---|
| `format` | `"einheit-v1"` |
| `app` | `"trainingsapp 0.2.1 (Build 139)"` |
| `einheit` | `id`, `titel`, `start_utc` (= `t_s` 0, ISO 8601), `ende_utc` (`null`: abgebrochen und nicht geschlossen) |
| `teile[]` | je Beteiligung `art` (`hrv`, `gps`, `timer`, `plan`), `rolle`, `versatz_s` (Zeit des Teils + `versatz_s` = `t_s`; HRV: `t_wall_s` der Messdatei; GPS: UTC-Sekunden der Ortung), `von_s`, `bis_s`, `daten`; HRV dazu `datei` = Pfad im ZIP (`null`: Messung lief beim Export noch) |
| `ereignisse[]` | die Zeitleiste in ihrer Folge: `nr` (ab 1), `t_s`, `quelle`, `art`, `text`, `daten` (§4, nur `DATEN_SCHLUESSEL`) |
| `tempo` | `schritt_s` (5), `einheit` (`"m/s"`), `reihe`: `[[t_s, m/s oder null], …]` je Fenster ab `t_s` = 0 — Mittel des Doppler-Tempos, ohne Doppler Weg je Zeit zwischen den Ortungen; Ortungen über 30 m Genauigkeit zählen nicht; `null` = keine Ortung (Tunnel) |

Einen Herzschlag auf die Achse: `t_s` = `t_wall_s` + `versatz_s` des HRV-Teils; eine Marke
der Messdatei (`marke.einheit`, §4) nennt ihre Einheit.

**Ortsfrei** (`docs/plan_gps.md` §0): keine Koordinate, keine Richtung, keine Höhenreihe,
nicht die Strecke und nicht der Dateiname der GPS-Beteiligung. Ein Test prüft das ZIP
(`tests/test_ausdauer.py::test_forschungsexport_ohne_ort`).

## 9. Leisten und Reiter „Einheit“ (Skizzen 16–19)

Ben, 17.10.2026: „Wenn mehrere Dinge abgelegt werden, nimmt das schnell viel Platz ein …
der halbe Screen ist mit den bereitgestellten Dingen belegt.“ Entschieden: **Variante B** —
ausführlich steht die Einheit nur noch auf „Heute“, überall sonst eine Zeile
(`ui/components/startleiste.py`).

| Zustand | „Heute“, Reiter „Einheit“ | „Heute“, Reiter „Heute“ | jede andere Seite |
|---|---|---|---|
| keine Einheit | — (kein Reiter) | der Tag | — |
| bereitgestellt | **Startkarte**: die Teile mit Stand, Marke und ✕, „Leeren“, „Wenn der Timer fertig ist“, Countdown, „Alle starten“ | der Tag | **Infoleiste** |
| Countdown, läuft | **Übersicht** | **Laufleiste** über dem Tag | **Laufleiste** |

- **Infoleiste** (eine Zeile): die Teile als Symbole (der nicht bereite mit Rand), „2 von 3
  bereit“ bzw. „Alles bereit“, darunter der Stand des langsamsten Teils („GPS sucht
  Empfang … 24 m“), ein Fehler rot, sonst was startet. ▶ = „Alle starten“ mit der
  Countdown-Einstellung, grau, bis alles bereit ist („Trotzdem starten“ nur in der
  Startkarte). Antippen öffnet „Heute“ im Reiter „Einheit“ — ebenso die Laufleiste.
- **Reiter** „Einheit · 3“ mit Punkt (orange: es bereitet noch etwas vor, grün: bereit), im
  Lauf „Einheit läuft“ mit rotem Punkt.
- **Reiterregel** (`ui.einheit.heute_reiter`): Erscheint eine Einheit oder beginnt sie,
  öffnet „Heute“ auf „Einheit“; wer auf den Tag wechselt, bleibt dort bis zur nächsten
  Änderung; endet sie, verschwindet der Reiter.
- **Übersicht:** Kopf mit Name, Startzeit („seit 15:31“), Laufzeit, ⏸ ⏹; der Timer mit
  Abschnitt, Runde, Restzeit und Fortschrittsleiste; „Wenn der Timer fertig ist – auch
  jetzt noch änderbar“, solange er läuft; je Teil ein Live-Wert (HRV „seit 54:29 · HF 158“,
  Training „2,10 km · 4:41 /km“, Plan-Ablauf „Übung 2 von 5“); „Intervalle (vom Timer)“,
  sobald Strecke oder Herz dazukommen — dieselbe Rechnung wie in der Ausdaueransicht
  (`ui/components/tabellen.live_tabellen`).
- **Fortschrittsleiste** (A17; `TimerLauf.fortschritt`, `ui/components/fortschritt.py`):
  je Abschnitt der ausgerollten Folge (Teile × Runden × Abschnitte) ein Stück, Breite nach
  Dauer, Farbe nach Name wie in der Messung (`hrv_core.ausschnitte.FARBEN`, gleicher Name —
  gleiche Farbe); fertige voll, das laufende anteilig, kommende blass. Darunter „Belastung
  2:24 / 4:00 · danach Pause 3:00“ und „11:24 von 28:00“; bei nur einem Abschnitt nur
  rechts.
- **Ende im Lauf ändern:** `Einheitslauf.ende_mit_timer` und `am_ende_stoppen` wirken erst
  am Ende des Timers bzw. der Einheit und dürfen bis dahin wechseln (Ben: „Das soll
  nachträglich auch deaktiviert werden können“). In der Übersicht die beiden Haken; in der
  Messung mit Dauer oder Ablauf (nur HRV und Timer) in der Statuskarte „Wenn die 5 min um
  sind – auch jetzt noch änderbar: Messung beenden | Weiterlaufen“ (`core.timer.ende_frage`).
  Ist der Timer durch, verschwindet die Wahl.
- Alles frischt sich im Sekundentakt der Einheit auf (`ui.einheit.melden`) und baut Knöpfe
  nur neu, wenn sich an ihnen etwas ändert; Verdecktes (anderer Reiter, eine Seite darüber)
  frischt nicht auf. Nach einem Wechsel der Navigationsleiste ohne Neuaufbau zeigt
  `leiste_auffrischen` die passende Leiste.
