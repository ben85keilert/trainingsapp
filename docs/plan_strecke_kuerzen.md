# Plan: Ende der Strecke kürzen — GPS lief weiter (Ben, 28.10.2026)

Ben: „Wenn am Ende nicht mehr viel bewegt wurde, wurde vermutlich vergessen, das GPS
auszumachen. Kannst du beim Speichern und auch für danach es ermöglichen, nach hinten raus
einen Crop zu setzen, um die Teile, wo es keine Änderung mehr gab, aus der Aufzeichnung
rauszunehmen. Wichtig dabei ist vor allem das korrekte Setzen der Notizen in der
HRV-Messung. Also einmal beim Speichern oder auch danach noch ein Dialog, der per Button
aktivierbar ist, um die Strecke zu croppen.“

Code: `core/nachlauf.py` (erkennen, Notizen, Sidecar), `ui/training.py`
(`training_kuerzen`, `nachlauf_der_strecke`), `ui/components/kuerzen.py` (das Blatt),
`ui/einheit.py` (`_nachlauf_fragen`), `ui/views/ausdauer.py` (Knopf „Ende kürzen“).
Gerätetest T88.

## 1. Erkennen

`core.nachlauf.nachlauf(punkte, sportart)` lässt alle Ortungen durch denselben
`StreckenRechner` wie die Auswertung und liest `letzte_bewegung_t` (die letzte Ortung, die
Strecke zählte oder Doppler-Tempo über dem Stand hatte). Liegt die letzte Ortung mindestens
`NACHLAUF_MIN_S` (60 s) dahinter, ist das der **Nachlauf**: `Nachlauf(erste_t,
letzte_bewegung_t, letzte_ortung_t)` mit `dauer_s`, `vorschlag_s` (neues Ende, Sekunden seit
der ersten Ortung) und `bisher_s`.

## 2. Wann gefragt wird

- **Beim Speichern** (`ui.einheit._laufen` → `_nachlauf_fragen`): nach dem Eintragen und
  dem Neuzeichnen, und erst, wenn kein anderer Dialog mehr offen ist (Reste, Rückfragen —
  nie darüber, sonst bliebe ein Geist). Nur bei Nachlauf ≥ 60 s.
- **Danach** in der Auswertung des Trainings: Knopf ✂ „Ende kürzen“ in der Titelleiste —
  immer, vorgeschlagen ist die letzte Bewegung; gab es nie Bewegung, sagt es die Meldung.

Das Blatt (`kuerzen_blatt`): ein Satz („Die letzten 7:42 ohne Bewegung — vermutlich lief
GPS noch, als das Training vorbei war.“), Feld „Ende bei (Zeit seit Start)“ mit dem
Vorschlag, Chips „Letzte Bewegung“ · „Ganze Aufzeichnung“, ein Satz dazu, was geschieht,
„So lassen“ · „Kürzen“. Das Feld nimmt „44:28“, „1:02:03“ oder Sekunden.

## 3. Was „Kürzen“ tut (`training_kuerzen`)

| Schritt | Was | Wo |
|---|---|---|
| 1 | **Streckendatei** neu schreiben: Kopf bleibt, nur Ortungen bis zum neuen Ende (atomar, `os.replace`). Die entfernten Ortungen sind weg — GPS-Daten, nie geteilt, kein Backup | `data/strecken.StreckenSchreiber` |
| 2 | **Zeile** `strecke`: Ende = altes Ende − entfernte Zeit; Dauer, Bewegungszeit, Strecke, Höhe neu aus den verbliebenen Ortungen | `StreckeRepo.kuerzen` |
| 3 | **Tagebucheintrag**: Korrektur (`eintrag_korrigieren`, der alte bleibt in der Kette) mit `duration`/`distance` neu und dem neuen Ende; die Zeile zeigt auf den neuen | `SessionRepo` |
| 4 | **HRV-Messung**: siehe §4 | `core/nachlauf.py` |

Grenzen: ohne Datei, unter 10 s, oder das Ende liegt schon dort → `ValueError`, das Blatt
zeigt den Satz am Feld. Die **Zeitleiste der Einheit** (`einheit`, `einheit_ereignis`)
bleibt unverändert: Sie dokumentiert, was geschah; die Tabelle „Intervalle“ nennt darum
weiter das ursprüngliche Ende.

## 4. Die HRV-Messung — „korrektes Setzen der Notizen“

Die Zeit des neuen Endes wandert von der Ortungsuhr über `HrvBezug.ortung_zu_wand` auf die
Wanduhr der Messdatei (`t_wall_s`) — mit den Versätzen der Einheit, sonst über die
Startzeiten. Dann gilt (`ereignisse_kuerzen`):

- **„‹Einheit›: Ende“** (`marke.quelle = einheit`, `art = ende`) rückt auf das neue Ende:
  Anker und `wall_time` neu, Text und Marke bleiben (`hrv_core.ereignisse.notiz(alt=…)`).
  Diese Notiz gibt es nur, wenn die Messung **vor** dem Training lief (`einheit_spur`);
  begann sie mit ihm, markiert nichts das Ende — dann sagt es der Zuschnitt (unten).
- **km-Notizen** nach dem Ende fallen weg — vorsorglich; ohne Bewegung entsteht keiner.
- **Alles andere bleibt**, auch Notizen der Person nach dem Ende. Die Messwerte werden nie
  angefasst (Rohdaten bleiben, `docs/kompatibilitaet.md`).
- **Sidecar** (`sidecar_kuerzen`): Abschnitte der Abläufe (Einheit, km, Timer, Übung) enden
  spätestens am neuen Ende, einer, der erst danach begänne, fällt weg; **eigene Abschnitte**
  der Person (Notizpaar, `core.abschnitte.kennung_von`) bleiben. Zeiten im Sidecar stehen
  auf der Herzuhr — `achsen_position` übersetzt.
- **Zuschnitt**: Endete die Messung mit dem Training (`strecke.hrv_recording_id` gesetzt),
  bekommt das Sidecar `active_crop` bis zum neuen Ende — die Kennzahlen der Auswertung
  rechnen dann ohne den Stillstand; nicht zerstörend, in der Auswertung → Zuschneiden →
  „Ganze Messung“ aufzuheben. Lief sie weiter, wird nichts zugeschnitten.
- **Läuft die Messung noch** (Blatt beim Speichern, HRV lief vorher): Die Notiz rückt in der
  laufenden Aufnahme (dasselbe Objekt hält `Messlauf._grenzen`) — Datei und Sidecar folgen
  beim Speichern von selbst.

Nach dem Schreiben bekommt die Zeile `hrv_recording` die neue Prüfsumme (`sha1_setzen`), das
Sidecar ebenso (`metadaten_schreiben`).

## 5. Offen

- Der Vorschlag ist die letzte Bewegung; ein paar Sekunden Auslaufen danach gehören
  eigentlich noch dazu. Wer das will, tippt die Zeit ins Feld — ein fester Zuschlag wäre
  geraten.
- Ein Anfang zum Kürzen („vorne“, GPS zu früh gestartet) ist nicht gebaut: Das Training
  beginnt mit dem Start der Einheit, da ist selten etwas falsch.
