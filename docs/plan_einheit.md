# Einheit: HRV, GPS, Timer und Plan gemeinsam

Ben, 17.10.2026: „HRV, GPS-Aufzeichnung, Timer, Plan/Übungen sind verschiedene
Komponenten, die miteinander gekoppelt werden sollen … Man bereitet alles vor und wenn
man soweit ist, klickt man auf Start und es läuft los.“ Für spätere Auswertungen (Deep
Learning: DFA α1 gegen RMSSD je Belastung, Tempo aus GPS, welche Übung wann) muss
**jedes Ereignis auf einer Zeitachse** liegen.

Skizzen der Oberfläche (15 Bildschirme): https://claude.ai/artifact/5m4q9AhyKnw5nMjWcwPjUs

## 1. Begriffe

| Begriff | Bedeutung |
|---|---|
| **Einheit** | die Klammer um alles, was zusammen läuft (`core/einheit.py`, `devices/einheit.py`) |
| **Teil** | HRV-Messung, Timer, Ausdauertraining, Plan-Ablauf (`Baustein`). Das Training ist der Teil `gps` (`devices/strecke_baustein.StreckeBaustein`) — mit GPS eine Strecke, ohne GPS (Laufband, Halle) nur die Zeit, wie eine `Strecke` ohne Datei |
| **Bereitstellen** | ein Teil macht sich fertig und wartet auf den gemeinsamen Start: Gurt verbunden, GPS hat Empfang, Profil geladen. Ein zweiter Knopf neben „Start“ (Ben, 17.10.: nicht der Sammelmodus mit Fahne) |
| **Startleiste** | unter der Titelleiste, auf jeder Seite: alles Bereitgestellte, sein Stand, „Wenn der Timer fertig ist …“, Countdown, „Alle starten“ |
| **Laufleiste** | dieselbe Stelle nach dem Start: eine Zeit, der laufende Abschnitt, ⏸ ⏹ für alle |
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
umschaltbar („Wenn der Timer fertig ist: GPS beenden ✓, HRV beenden ☐“). Eine
mitstartende HRV-Messung mit Dauer („15 min“) endet nach Wahl mit dem Timer oder läuft
weiter. **Die HRV pausiert nie** — eine Pause ist ein Abschnitt.

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
| `plan/uebung_start`, `plan/uebung_ende` | Notiz „Planke beginnt“ / „Planke fertig“, Abschnitt der Übung | `uebung` |
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
| 1 | Zeitleiste, `Einheitslauf` mit HRV, Timer, GPS; Startleiste, Laufleiste, Bereitstellen; Dienst `health` | gebaut 17.10.; offen: Messung mit Dauer und Ablauf (Katalog A11) |
| 2 | Ausdauertraining als Einheit (verknüpft auch eine schon laufende HRV, Abgleich über `versatz_s`, Wiederherstellung H16) | gebaut 17.10.; Tabellen „Intervalle“ und „Kilometer“ live und in der Auswertung (A10, `core/intervalle.py`) |
| 3 | Timer an Übung, Planübung und Plan (mehrere Profile, „zählt“, Abbrechen), Plan-Ablauf, Einträge mit Anfang und Ende — Migration 020 | gebaut 17.10. (§7); „vom Timer“ unter „Heute geleistet“ gebaut (A13) |
| 4 | Forschungsexport (ausdrückliche Handlung): Messdateien, Zeitleiste `einheit-v1.json`, ortsfreies Tempo | gebaut 17.10. (§8) in der Auswertung des Trainings; offen: aus der HRV-Auswertung, für Einheiten ohne GPS (A14) |

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
Auswertung eines Trainings das Symbol „Für die Auswertung exportieren (ohne Ort)“, ein
Dialog sagt, was hineingeht, dann das Teilen-Menü (`ui/training.forschung_export`,
`core/forschung.py`).

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

