# Planung: Bewegungsdaten im Messungs-Export — ohne Ort (26.10.2026)

Bens Frage: „Unter Messungen → HRV lassen sich alle HRV-Daten exportieren. Wie ist das
mit den GPS-Daten? Gibt es auch dafür Exports? Bzw. lassen sich die HRV-Exports mit den
GPS-Daten koppeln, damit man später zusammen untersuchen kann, wie sich die HRV in Bezug
auf die Geschwindigkeit usw. geändert hat?“ Später soll ein Deep-Learning-Modell aus GPS-
und HRV-Daten Muster finden: zu viel oder zu wenig Training, Überlastung, Hinweis auf
Infekt, Trainingszustand.

**Entschieden (Ben, 26.10.2026):**

> „Für HRV reicht die Entfernung — bitte keine GPS-Koordinaten. Wer unbedingt die
> GPS-Koordinaten braucht, kann sich diese separat exportieren, das geht dann aber auf
> Eigenverantwortung. Nimm die Höhe mit.“

Also: **keine Checkbox, keine Koordinaten im Messungs-Export** — Regel 0 bleibt
unverändert. Mit geht je Training eine **Rohspur ohne Ort**: die Streckendatei als Kopie,
ohne Breite, Länge und Richtung, dafür mit dem Abstand je Fix; Höhe und Genauigkeit roh.
Koordinaten gibt es weiter nur über „GPX exportieren“ in der Auswertung des Trainings.

Dazu (Ben, gleicher Tag): **F4** „Alle exportieren“ auch unter Aufzeichnungen → „Laufen“, der
Reiter wird umbenannt (→ „Strecken“); **F6** der Forschungsexport je Einheit bekommt die Rohspur
— „das ist der wichtige Teil“: ein 10-km-Lauf mit Dehnübungen zwischendurch, und man will
wissen, wie schnell man in der Erholung nach der Dehnung war; **F7** Tagesdaten als Etiketten
bleiben weg („super intim“ — höchstens später versteckt, nur für Ben; an Daten von
Patienten und Kunden will er nicht heran).

Stand: **gebaut am 26.10.2026** (Ben: „MSL umschalten, Annahme bei F4 stimmt, bau das alles“) — Abschnitt 5 nennt, was wo liegt; Gerätetest T78. Katalog P80.

---

## 1. Was es heute gibt (am Quelltext geprüft)

| Export | Wo | Inhalt | Ort dabei? |
|---|---|---|---|
| **Alle Messungen** | Messung → Aufzeichnungen → HRV → „Alle exportieren“ (`views/messung.py`, `_hrv_liste`) | ZIP mit jeder Messdatei samt Beiwerk (`core.hrv_export.export_zip`), Pfade `Messungen/<Gerät>/…`, ohne Bluetooth-Adresse | nein — keine Strecke, keine Bewegungsdaten |
| **Eine Messung** | Aufzeichnung → Menü ⋮ (`views/messung_detail.py`) | dasselbe für eine Messung | nein |
| **GPX je Training** | Auswertung eines Trainings → „GPX exportieren“ (`views/ausdauer.py`, `data.strecken.gpx`) | Strecke mit Höhe, Zeit und Herzfrequenz je Ortung, Sportart | **ja** — die einzige Stelle, auf Eigenverantwortung |
| **Forschungsexport je Einheit** | Auswertung eines Trainings oder einer Messung mit Einheit → „Für die Auswertung exportieren (ohne Ort)“ (`core/forschung.py`, `einheit-v1`) | Messdateien der Einheit, Zeitleiste (Timer, Kilometer, Übungen), Tempo als 5-s-Mittel | nein |

Die Kopplung HRV ↔ Tempo gibt es also schon, aber nur je Einheit, von Hand, als 5-s-Mittel
und nur für Trainings seit dem 17.10.2026. „Alle exportieren“ kennt die Trainings nicht,
und nichts im ZIP sagt, welche Strecke zu welcher Messung gehört — das steht nur in der
Datenbank (`strecke.hrv_recording_id`, `strecke.einheit_id`).

**Warum die Kopplung über die Zeit funktioniert:** Jede Ortung trägt die UTC-Zeit des
Empfängers (`Punkt.t`), jeder Herzschlag die Wanduhr seit `start_utc` der Messdatei
(`t_wall_s`, `docs/kompatibilitaet.md` §4). Beide liegen damit auf einer Achse, auf die
Sekunde genau (`start_utc` hat ganze Sekunden). Kennt die Einheit die Versätze beider
Teile (`docs/plan_einheit.md` §3), ist es genauer; beides kommt in den Kopf der Rohspur.

---

## 2. Warum roh, und was „roh ohne Ort“ heißt

**Auflösung:** Für Muster über Tage und Wochen (Überlastung, Infekt, Trainingszustand)
braucht das Modell nicht die Kurve, sondern die Antwort des Herzens auf die äußere Last:
Herzfrequenz und HRV bei gegebenem Tempo und gegebener Steigung, und wie sich dieses
Verhältnis über die Zeit verschiebt. Dafür reichen Fenster von 5 bis 30 s. Ein Einzelfix
rauscht 3–5 m, Weg je Sekunde ist bei 3 m/s Lauftempo kaum brauchbar — das Tempo kommt
aus dem Doppler-Wert des Empfängers, den es je Fix gibt.

**Trotzdem roh:** Was der Export wegwirft, ist weg. Welches Fenster, welcher Filter,
welche Höhenglättung richtig sind, weiß man erst mit dem Modell. Die HRV liegt aus
demselben Grund als raw-v1 und nicht als Kennzahlen vor („Die Datei ist die Wahrheit“);
die GPS-Seite vorgerechnet mitzugeben wäre inkonsequent. Der Preis ist null: Eine Stunde
Lauf sind 3600 Zeilen, *im ZIP etwa 40 kB*.

**Ohne Ort** heißt: ohne Breite, Länge und **Richtung**. Abstand plus Richtung je Sekunde
ist Koppelnavigation — daraus ließe sich die Strecke bis auf Drehung und Verschiebung
exakt zurückrechnen. Der Abstand allein ist eindimensional und verrät nichts. Die **Höhe**
geht roh mit (Ben): Eine Höhenreihe ist zwar ein Profil, aber für eigene Daten in eigener
Auswertung ein kleines Risiko, und ohne Steigung fehlt dem Modell die halbe Last.

Damit wird die Liste der ortsfreien Werte in Regel 0 (`docs/plan_gps.md` §0) um **Abstand
je Fix, Höhe und Genauigkeit je Fix** erweitert; „keine Höhenreihe“ aus dem
Forschungsexport (`docs/plan_einheit.md` §8) gilt für das neue Format nicht mehr (F6).

---

## 3. Format: Rohspur ohne Ort (`spur-ohne-ort-v1`)

**Eine Dateikopie, kein Rechenformat.** Je Training eine `.jsonl` wie die Streckendatei
der App (`data/strecken.py`: Kopfzeile, dann eine Zeile JSON je Ortung), im ZIP unter
`Bewegung/<Name der Streckendatei>` — z. B. `Bewegung/strecke_2026-10-18_090507.jsonl`.
Eigener Ordner neben `Messungen/`, damit weder praxis_gui noch `ist_messdatei()` sie je
anfassen; die Messdateien bleiben byteidentisch (Kompatibilitätsvertrag).

**Kopfzeile** `{"kopf": {…}}` — der Kopf der Streckendatei, ergänzt:

| Feld | Bedeutung |
|---|---|
| `schema` | `"spur-ohne-ort-v1"` |
| `app` | `"trainingsapp 0.3.18 (Build …)"` |
| `sportart`, `start_utc`, `ende_utc` | wie `strecke` |
| `strecke_id`, `einheit_id` | Kennungen (`einheit_id` `null` bei Trainings vor dem 17.10.) |
| `kennzahlen` | `distanz_m`, `dauer_s`, `bewegt_s`, `hoehe_auf_m`, `hoehe_ab_m` — **wie die App sie zeigt**, ausdrücklich als Komfort markiert; die Wahrheit sind die Zeilen |
| `messungen[]` | je verknüpfter Messung `datei` (Pfad im ZIP, `Messungen/<Gerät>/sensor_….json`), `recording_id`, `versatz_s`, `versatz_quelle`: Ortungszeit `t` + `versatz_s` = `t_wall_s` dieser Messdatei. Aus der Einheit (`"einheit"`), wenn sie beide Versätze kennt, sonst `-start_utc` der Messdatei (`"uhr"`, ±1 s) |
| `felder` | `["t", "ds_m", "tempo_ms", "genauigkeit_m", "hoehe_m", "hoehe_genauigkeit_m", "t_empfang", "simuliert"]` — was in den Zeilen stehen kann |
| `entfernt` | `["lat", "lon", "richtung_grad"]` — was fehlt, damit ein Leser es nicht sucht |

**Eine Zeile je Ortung**, Werte wie in der Rohdatei (Felder mit `None`/`False` fehlen, wie
beim `StreckenSchreiber`):

| Feld | roh? | Bedeutung |
|---|---|---|
| `t` | roh | UTC-Sekunden des Empfängers |
| `ds_m` | abgeleitet | **Abstand zum vorigen Fix** in Metern — Haversine (`core.strecke.abstand_m`), ungefiltert, jede Ortung, auch die ungenauen; erste Zeile ohne `ds_m` |
| `tempo_ms` | roh | Doppler-Tempo des Empfängers |
| `genauigkeit_m` | roh | horizontaler Fehler — der Leser filtert selbst (die App nimmt 30 m, `MAX_GENAUIGKEIT_M`) |
| `hoehe_m`, `hoehe_genauigkeit_m` | roh | Höhe wie vom Empfänger (heute Ellipsoid, G-F7 offen — der Kopf sagt `"hoehe_bezug": "ellipsoid"`) |
| `t_empfang` | roh | monotone Uhr der App beim Eintreffen — Lücken und Stau |
| `simuliert` | roh | Ortung aus einer Test-App |

`ds_m` ist die eine Ableitung, und sie ist eine Zeile Mathematik, die im Code steht und
einen Doctest hat. Alles Weitere — Genauigkeitsfilter, Auto-Pause, Steigung mit Hysterese,
Kilometer, Tempo je Fenster — rechnet man hinterher nachvollziehbar mit demselben Code wie
die App (`core/strecke.py`: `StreckenRechner`, `core/forschung.py`: `tempo_reihe`).

**Ein Test sichert es:** Keine Zeile und kein Kopf enthält `lat`, `lon`, `richtung_grad`
oder eine der Testkoordinaten; aus `ds_m` und den Zeilen lässt sich die App-Distanz
(`distanz_m`) mit dem `StreckenRechner` reproduzieren.

**Im Forschungsexport je Einheit** (`einheit-v1`, `docs/plan_einheit.md` §8) liegt dieselbe
Datei unter demselben Pfad `Bewegung/…jsonl`, und die GPS-Beteiligung in `teile[]` nennt sie
(`datei`, bisher ausdrücklich weggelassen). Die 5-s-Reihe `tempo` bleibt als Komfort — das
Feld kommt hinzu, das Format bleibt `einheit-v1` (additiv, Eintrag in `kompatibilitaet.md`).
Damit steht das, was Ben will, in einem ZIP: die Zeitleiste sagt, wann die Dehnübung
begann und endete (`ereignisse[]`, Quelle `plan`/`timer`, auf `t_s`), die Rohspur sagt über
`versatz_s` je Sekunde, wie schnell man danach war, die Messdatei, was das Herz dabei tat.
Ein Test spielt genau das durch: Einheit mit Lauf, Marke „Dehnung“ 2 min, Rohspur → Tempo
in den 2 min nach der Marke lässt sich aus dem ZIP allein berechnen.

---

## 4. Oberfläche

**Nichts Neues zu bedienen.** „Alle exportieren“ und der Export einer Messung packen die
Rohspur mit, sobald eine Messung ein Training hat. Statt eines Dialogs eine Zeile in der
Meldung bzw. im Erklärtext („… 4 Trainings als Bewegungsdaten ohne Ort“). Der Text unter
dem Knopf „GPX exportieren“ in der Auswertung bekommt den Satz: „Der Messungs-Export
enthält vom Training nur Abstand, Tempo und Höhe — nie den Ort. Die Strecke mit
Koordinaten gibst du nur hier heraus, in eigener Verantwortung.“

Hilfe (`ui/components/hilfe.py`, Kapitel GPS, A3): derselbe Satz.

**Reiter „Laufen“ → „Strecken“** (Ben, F4): Der Unterreiter unter Aufzeichnungen heißt heute
„Laufen“, zeigt aber Gehen, Laufen und Rad (`_aufzeichnungen` in `views/messung.py`,
`strecken_zeilen`). Neuer Name **„Strecken“** — so heißen Tabelle, Ordner und Code; die
Alternative „Ausdauer“ trägt die Seite `/ausdauer` schon. Darüber wie bei HRV eine Zeile
„n Strecken · Alle exportieren“.

Was dieser Sammelexport enthält — *Annahme, von Ben zu bestätigen:* **die Strecken mit
Koordinaten** (`Strecken/<Name>.gpx` je Training, mit Herzfrequenz wie der Einzelexport),
denn die ortsfreie Spur steckt schon im Messungs-Export, und „separat exportieren, auf
Eigenverantwortung“ meint genau diese Stelle. Vor dem Teilen ein kurzer Dialog, jedes Mal:
„n Strecken mit Koordinaten als GPX. Die Strecken verraten, wo du läufst — in eigener
Verantwortung weitergeben.“ Kein Häkchen, nur Abbrechen/Exportieren.

---

## 5. Umsetzung

| Schritt | Wo | Bemerkung |
|---|---|---|
| `data/strecken.py`: `spur_ohne_ort(pfad, kopf) -> bytes` — liest die `.jsonl` zeilenweise, streicht `lat`/`lon`/`richtung_grad`, rechnet `ds_m` zum vorigen Fix, schreibt Kopf + Zeilen im selben Format | data, flet-frei, Doctest | Dateikopie wie `hrv_export.exportkopie`, keine Neuberechnung |
| `core/bewegung.py`: `kopf(strecke, messungen, app)` — Kopfzeile aus `strecke`, Versätze aus der Einheit (Logik von `ui/training.hrv_bezug` wandert nach `core`, vgl. G15) | core | `daten_pruefen` über alles aus Ereignissen |
| `core/hrv_export.export_zip(dateien, basis, *, zusatz: Mapping[str, bytes])` | core | erzeugte Dateien unter frei gewähltem ZIP-Pfad |
| `ui/training.bewegung_dateien(state, aufnahmen) -> dict[str, bytes]` — je Messung die Trainings (`StreckeRepo.zur_hrv` + Einheit), Lesen in `asyncio.to_thread` | ui (flet-frei wie `forschung_export`) | ein Training mit zwei Messungen → eine Datei mit zwei `messungen[]` |
| `views/messung.py` `alle_exportieren`, `views/messung_detail.py` Export: `zusatz` mitgeben, Meldung mit Anzahl | ui | |
| `core/forschung.py`: `_teil` nennt bei `gps` die Rohspur (`datei` = Pfad im ZIP); `ui/training._forschung_teile` legt sie unter `Bewegung/` dazu; `tempo` bleibt | core/ui | `test_forschungsexport_ohne_ort` erweitert: Rohspur ortsfrei, Tempo nach der Dehnung aus dem ZIP |
| Reiter „Laufen“ → „Strecken“, darüber „Alle exportieren“ (GPX aller Strecken, Dialog zur Eigenverantwortung) | `views/messung.py`, `views/ausdauer.strecken_zeilen` | Tests `test_ui_messung` (Reitername), neuer Test: ZIP enthält nur `Strecken/*.gpx` |
| Tests: `test_regel_0_…` erweitert (ZIP mit `Bewegung/`, ortsfrei, keine Richtung); `ds_m` reproduziert `distanz_m`; Versatz aus Einheit vs. Uhr; Training ohne Messung → keine Datei; Rohdatei ohne Kopf (vor 15.10.) → Kopf nur aus `strecke` | tests | |
| Doku: `docs/kompatibilitaet.md` §2 „Export“ (Ordner `Bewegung/`, Messdateien unverändert) + §13 `spur-ohne-ort-v1`; `docs/plan_gps.md` §0 (ortsfreie Werte um Abstand, Höhe, Genauigkeit je Fix erweitert; Satz zur Eigenverantwortung) und §5b; `docs/plan_einheit.md` §8 (Verweis); `CLAUDE.md`; `docs/recht/40_toms.md`; `docs/offene_fragen.md` §5 Inventar | docs | Formatänderung braucht zuerst den Eintrag in `kompatibilitaet.md` |
| hrv-research: `hrv_research/bewegung.py` — Leser (Kopf + Zeilen → DataFrame), Verschnitt mit `hrv_core`-Kennzahlen je Fenster über `t` + `versatz_s`, `StreckenRechner` aus trainingsapp **nicht** importieren (hrv-research hängt nur an hrv-core) — die Filterregeln dort nachbauen und gegen die `kennzahlen` des Kopfs prüfen | privates Repo | Daten nur `daten/selbst/` |

*Aufwand (geschätzt): App ein halber Tag, hrv-research ein halber. Keine Migration, keine
Änderung an hrv-core, keine neue Bedienung.*

---

## 6. Entschieden und noch offen

| # | Frage | Stand |
|---|---|---|
| F4 | „Alle exportieren“ auch unter Aufzeichnungen → „Laufen“? | **Ja** (Ben). Reiter → „Strecken“. Inhalt GPX mit Koordinaten — Annahme bestätigt (Ben, 26.10.). |
| F6 | Forschungsexport je Einheit mit Rohspur? | **Ja, das ist der wichtige Teil** (Ben). `einheit-v1` additiv, Abschnitt 3. |
| F7 | Export der Tagesdaten als Etiketten? | **Weg** (Ben: „super intim“). Höchstens später versteckt, nur für Ben, aus den Einstellungen; nie für Daten von Patienten und Kunden. Kein Katalogpunkt. |
| G-F7 | Höhe als Ellipsoid oder MSL? | **MSL** (Ben, 26.10.). `use_msl_altitude=True`, Kopf nennt `hoehe_bezug`. Erklärung: Abschnitt 7. |

---

## 7. Zur Höhe: Ellipsoid oder Meeresspiegel (G-F7)

Ein GPS-Empfänger misst die Höhe über dem **Ellipsoid** — der mathematischen Erdkugel
des Systems WGS 84. Die Höhe „über dem Meeresspiegel“ (über NN, MSL) bezieht sich auf das
**Geoid**, die Fläche gleicher Schwere, der der Meeresspiegel folgt. Beide liegen
auseinander, in Deutschland um rund 45 m (Ellipsoid liegt höher), in anderen Weltgegenden
bis ±100 m; innerhalb einer Region ändert sich der Abstand nur um Meter.

Android liefert die Ellipsoidhöhe; die Erweiterung `flet-geolocator` kann mit
`use_msl_altitude=True` auf NN umrechnen (Befund G10, `ui/geraete/flet_gps.py`). Heute
steht die App auf Ellipsoid — eine Höhe von „95 m“ im Taunus ist also eigentlich 50 m.

Was davon abhängt:

- **Höhenmeter und Steigung: nichts.** Differenzen sind in beiden Bezügen gleich.
- **GPX-Export:** Strava, Komoot, Garmin erwarten NN und zeigen sonst 45 m zu viel.
- **Rohspur:** Vergleicht das Modell absolute Höhen über Trainings und Regionen hinweg
  (Höhenlage als Belastungsfaktor), müssen alle denselben Bezug haben. Darum nennt der
  Kopf `hoehe_bezug` (`"ellipsoid"` oder `"msl"`), und alte Dateien bleiben lesbar.

Vorschlag: MSL einschalten, bevor viele Trainings gesammelt sind — ein Schalter in der
Erweiterung, keine Umrechnung alter Dateien.
