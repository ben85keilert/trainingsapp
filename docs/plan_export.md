# Plan: Export mit Auswahl und vollständige Sicherung

Stand 11.11.2026 — **entschieden (§7), Stufe S1 gebaut**, der Rest ist Plan. Anlass: P180 (Was darf ins Geräte-Backup?) und
Bens Auftrag vom 11.11.2026: „Es wäre gut, user kann ein vollständiges Backup auf Wunsch machen
… Es braucht ohnehin einen Upgrade der Exportfunktion: es soll anklickbar sein, was exportiert
wird, Filter für alle Bereiche und dabei ob Anhänge mitgeliefert werden und Datumsauswahl …
dabei wird unterschieden zwischen sensibel und nicht sensibel.“ Löst A4 (Export/Import je
Inhalt, Abschnitt 5 des Katalogs) ab.

Skizzen X1–X5: <https://claude.ai/artifact/3DfPg1WTYH2F7MDGTZwM6e> (privat, Design-Canvas) —
Stand vor den Entscheidungen; die Wörter in X2–X4 („Sensibel“, „Gesundheit“) werden mit Stufe
S5 nach §7 angepasst. P180 und P182–P187 sind am 11.11.2026 entschieden (§7).

## 0. Grundsatz: drei Wege hinaus, drei Zwecke

| Weg | Wozu | Inhalt | Bereinigt? | Wer löst aus |
|---|---|---|---|---|
| **Export mit Auswahl** | weitergeben (Praxis, Trainerin, eigene Auswertung) | was angekreuzt ist | **ja** — keine Koordinaten, keine Bluetooth-Adresse, Anhänge ohne Ortsangabe | die Person, je Export |
| **Vollständige Sicherung** | wiederherstellen, Gerätewechsel | alles | **nein** — sonst ließe sie sich nicht wiederherstellen | die Person, je Sicherung |
| **Geräte-Backup** (Android/iOS) | Bequemlichkeit | Datenbank und Messungen, klein | — | das Betriebssystem, wenn eingeschaltet |

Die Regeln „GPS-Daten werden nie geteilt“ und „Anhänge nie in Export, Backup oder Sync“
(CLAUDE.md) meinen das **Weitergeben** und das **stille** Hinausgehen. Die vollständige Sicherung
ist keins von beiden: Die Person legt sie selbst an, für sich, mit einer Rückfrage, die sagt,
was drin ist. Dafür braucht der Vertrag einen Satz mehr (P182), sonst widerspricht er sich wie
bei P75.

## 1. Geräte-Backup (löst P180, S23, D20, P75, S12) — gebaut 11.11.2026

Der Backup-Agent (`scripts/apk_bauen.py`, `Sicherung.onFullBackup`) schließt
`Anhaenge`, `Medien/Pakete`, `Karten`, `Import`, `Export` aus — immer, ohne zweiten Schalter.

- Grund 1: Googles Grenze von 25 MB je App. Ein Video genügt, und Android verwirft das **ganze**
  Backup still, auch Datenbank und Messungen.
- Grund 2: Die App sagt an drei Stellen „Anhänge nie ins Backup“.
- Folge nach einer Wiederherstellung: Die Zeilen in `entry_media` zeigen auf Dateien, die
  fehlen. Die Anzeige hält das aus (geprüft 11.11.2026): Kacheln zeigen „fehlt“
  (`components/anhang_reihe.py`), die Ansicht „Die Datei fehlt …“ (`views/anhang.py`),
  Paketdateien „Datei fehlt — das Paket neu importieren“ (`components/medienliste.py`).
  Am Gerät noch zu prüfen: T125.
- Wer die Anhänge sichern will, nimmt die vollständige Sicherung.

## 2. Vollständige Sicherung (Skizze X5)

- **Inhalt:** Datenbank (alle Profile), `Messungen/`, `Medien/Symbole`, `Medien/Bewegung`;
  wählbar `Anhaenge/` (Vorgabe an), `Strecken/` (Vorgabe aus, wie beim Geräte-Backup),
  `Medien/Pakete/` (Vorgabe aus, lässt sich neu laden).
- **Format:** ZIP `trainingsapp-sicherung-<Datum>.zip` mit `sicherung.json` (Formatversion,
  App-Version, `PRAGMA user_version`, Liste der Dateien mit SHA-256). Die Datenbank kommt als
  Kopie über die SQLite-Backup-API (konsistent trotz WAL), nicht als Dateikopie.
- **Kennwort:** auf Wunsch verschlüsselt, mit demselben Verfahren wie private Pakete
  (`core/privat.py`: scrypt, SHAKE-256, HMAC, nur stdlib). Ohne Kennwort sagt die Rückfrage,
  dass jede Person die Datei lesen kann.
- **Wohin:** über den Speicherdialog des Systems („Datei speichern“) — die Person wählt den
  Ort (Telefonspeicher, Karte, Cloud-Ordner). Kein Teilen-Blatt als Vorgabe, weil 400 MB durch
  einen Messenger nichts verloren haben.
- **Groß:** nie durch den Arbeitsspeicher. Geschrieben wird in einem Thread in eine Datei unter
  `Export/`, Stück für Stück (wie große Pakete, `core/paketdatei.py`); die Datenbank bleibt im
  Event-Loop, nur die Backup-Kopie liest der Thread von einer eigenen Verbindung.
- **Wiederherstellen:** eigene Stufe (S4). Nur in eine leere App oder nach Rückfrage „ersetzt
  alles“; Datenbank einer neueren App-Version wird abgelehnt, eine ältere läuft durch die
  Migrationen. Kein Zusammenführen — das wäre Sync.
- **Nie** läuft die Sicherung, solange eine Aufnahme oder ein Training läuft (die Messdatei
  wäre halb).

## 3. Export mit Auswahl (Skizzen X1–X4)

### 3.1 Bereiche und ihre Einstufung

Die Liste (Ben, 11.11.2026: „für sensibel brauchen wir eine Liste … Persönliches und Werte, die
einen Rückschluss auf den Gesundheitszustand liefern, sind sensibel. Übungsabläufe usw. nicht,
Wdh und Zeit einer Übung …“):

| Bereich | Quelle | Filter (X3) | Einstufung | Vorgabe |
|---|---|---|---|---|
| Übungseinträge: Übung, Plan, Sätze, Wiederholungen, Zeit, Last, Strecke, **Skalen und Ausprägungen** (auch Schmerz, Anstrengung/sRPE — Ben, 11.11.2026: „nicht-sensibel“) | `session_entry` (gültiger Stand der Kette) | Übungen, Pläne, Typ, Region | normal | an |
| Workouts: Verlauf, Zeiten, gegangener Weg, Skalen des Durchlaufs | `workout_entry`, Zeitleiste | Pläne | normal | an |
| Pläne und Abläufe (was geübt wird) | `plan`, `plan_item` | Pläne | normal | an |
| Trainings ohne Ort: Abstand, Tempo, Höhe | Rohspur (`core/bewegung.py`) | Sportart | normal | aus |
| Notizen **an Messungen** (Titel, Beschreibung, Notizen mit Anker) | Messdatei | Häkchen „Notizen der Messung mitgeben“ | normal, abwählbar | an |
| **Tagesfelder** — alle Werte und ihr Text (Schmerzskala, Blutdruck, Ruhepuls, Mengen …) | `day_field`/`day_value` | **einzelne Felder**, Text ja/nein | **sensibel** | aus |
| **Notizen zum Tag, Tagebuch, Notizen an Einträgen und Workouts** (freier Text) | Tagesnotizen, `session_entry.note`, `workout_entry` | Notiz-Tags, Art | **sensibel** | aus |
| **Anhänge** (Fotos, Videos, Audio) | `entry_media`, `Anhaenge/` | Art, nur zu gewählten Bereichen | **sensibel** | aus |
| **Profilwerte** (Ruhe-HF, HFmax, Schwellen, Zielbereich) | Einstellungen des Profils | — | **sensibel** | aus |
| **HRV- und HF-Messungen** (Messdateien, Kennzahlen) | `Messungen/`, wie heute `core/hrv_export.py` | einzelne Messungen, Gerät | **sensibel** (Ben, 11.11.2026: „HRV und HF persönlich, ja“) | aus — vorgewählt, wenn der Export von einer Messung aus geöffnet wird |

Skalen an Übungen sind **nicht** sensibel (Ben, 11.11.2026) — ein Übungseintrag geht mit
allen seinen Feldern hinaus.

Nie im Export mit Auswahl: Koordinaten und Richtung, Bluetooth-Adresse, andere Profile,
Codes privater Pakete, Einstellungen des Geräts. GPX bleibt der eigene Knopf unter
Aufzeichnungen → Strecken.

**Keine medizinische Note** (Ben, 11.11.2026): „Sensibel“ ist der Name im Code
(`core/export_auswahl.py`, je Bereich bzw. Feldart, nicht je Datensatz). **In der Oberfläche
heißt die Gruppe „Persönlich“**; kein Text spricht von Gesundheit, Befund oder Diagnose, nichts
wird bewertet — es steht nur da, was hinausgeht. Die Gruppe ist beim ersten Mal aus, hat ein
Schloss, und der Prüfschritt (X4) nennt sie jedes Mal.

**Notizen an Messungen** sind nicht sensibel (P184): Sie gehen wie heute mit der Messdatei
hinaus. Der Messungsexport bekommt das Häkchen „Notizen der Messung mitgeben“ (Vorgabe an) —
ohne es entfallen in der Exportkopie Titel, Beschreibung und freie Notizen; Marken der Einheit
(Abschnitte, Timer, Übungen) bleiben, sonst stimmten die Abschnitte nicht mehr.

### 3.2 Zeitraum, Profil

Ein Zeitraum für alles (Vorgabe: letzte 6 Wochen; Schnellwahl 7 Tage · 6 Wochen · dieses
Jahr · alles), je Bereich im Filter überschreibbar. Exportiert wird das aktive Profil.

### 3.3 Format (P185, entschieden 11.11.2026)

Ben: „ZIP; Format so, dass es gut mit Python ausgewertet werden kann und ggf. wieder importiert
werden kann.“ Darum ist **JSON die Wahrheit** und CSV die bequeme Ableitung:

- `export.json` — Formatversion `auswahl-v1`, App-Version, Auswahl, Zeitraum, was bewusst fehlt
  (`ausgelassen`), Liste der Dateien mit SHA-256.
- `daten/<bereich>.json` je Bereich (`eintraege`, `workouts`, `plaene`, `tagesfelder`,
  `notizen`, `profil`) — **verlustfrei und wieder importierbar**: feste IDs (die UUIDs der
  App), Zeiten als ISO 8601 in UTC plus lokaler Tag, je Eintrag `result` und die Spec-Kopie
  (`spec_snapshot`), Bezüge über IDs (Übung, Plan, Einheit). Ein Import (Stufe S7) liest nur
  diese Dateien.
- `tabellen/<bereich>.csv` — dieselben Daten flach für `pandas.read_csv`: eine Zeile je Wert
  (Eintrag × Feld × Satz), feste Spaltennamen wie im JSON, UTF-8, Komma,
  Dezimalpunkt, ISO-Zeiten; kein Import liest sie.
- `Messungen/…` wie heute (raw-v1, byte-kompatibel zu praxis_gui; mit `hrv_core` oder `json`
  zu lesen), `Bewegung/…` wie heute.
- `Anhaenge/…` — jede Datei durch `core/bereinigen.py` (Weißliste seit 11.11.2026); was sich
  nicht sicher bereinigen lässt, bleibt draußen und steht in `export.json` unter `ausgelassen`.
- `LIESMICH.md` mit drei Zeilen Python zum Einlesen.

Vertrag: neuer Abschnitt in `docs/kompatibilitaet.md`, **bevor** gebaut wird.

### 3.4 Ablauf in der Oberfläche

- **X1** Einstellungen → „Export & Sicherung“: die drei Wege aus Abschnitt 0 an einem Ort. Die
  heutigen Knöpfe an Messung und Aufzeichnungen bleiben als Abkürzung (sie öffnen X2 mit
  vorgewählter Messung).
- **X2** Bereiche ankreuzen, Zeitraum, Zeile „Anhänge mitliefern“. Unten laufend Zahl und Größe.
- **X3** Filter je Bereich als Blatt (`components/blatt.blatt_spalte`), Muster wie der
  Übungsfilter (`components/uebungsfilter.py`).
- **X4** **Vollständige Übersicht vor dem Export** (Ben, 11.11.2026: „dass man sieht, was
  rausgeht“): je Bereich Zahl und Zeitraum, aufklappbar bis zur einzelnen Zeile — welche
  Übungen, welche Felder, welche Messungen, welche Notizen (Anfang des Texts), welche Anhänge
  (Vorschaubild) —, dazu jede Datei des ZIP mit Größe, was hierbleibt, und das Format. Es geht
  genau das hinaus, was dort steht: Die Übersicht wird aus derselben Liste gebaut, die gepackt
  wird (`core.export_auswahl.vorschau`), nie aus einer zweiten Abfrage. Dann Teilen oder
  Speichern.
- Die letzte Auswahl merkt sich die App je Profil — die ganze, auch die Häkchen der Gruppe
  „Persönlich“ (P186, Ben 11.11.2026: „Auswahl bleibt gemerkt, lässt sich aber
  zurücksetzen“). Vorgabe beim ersten Mal: aus. **„Zurücksetzen“** in X2 stellt die Vorgaben
  wieder her (Persönliches aus, Zeitraum 6 Wochen, Filter leer).

## 4. Architektur

- `core/export_auswahl.py` (flet-frei): `Auswahl` (Bereiche, Filter, Zeitraum, Anhänge),
  `BEREICHE` mit Einstufung, `vorschau(auswahl, zahlen)` für die Zeile unten, `tabellen(...)`
  baut Zeilen aus Modellen. Reine Funktionen, Doctests.
- `data/export.py`: liest je Bereich aus den Repos (im Event-Loop, SQL mit `?`), liefert Modelle
  und Dateilisten — keine Dateien.
- `core/sicherung_voll.py`: Manifest, Packen in eine Datei, Prüfen beim Wiederherstellen.
- `ui/views/export.py`, `ui/views/sicherung.py`, Blätter unter `ui/components/`.
- Packen in `asyncio.to_thread`, nur Dateien; Fortschritt über eine Zahl, die die Ansicht
  liest (kein Neuaufbau je Datei).

## 5. Stufen

| Stufe | Inhalt | Hängt ab von |
|---|---|---|
| **S1** ✔ 11.11.2026 | Geräte-Backup ohne Anhänge und Paketdateien; Texte vereinheitlichen; fehlende Anhangdatei aushalten | P180 |
| **S2** | Vollständige Sicherung anlegen (X5), mit Kennwort | P182 |
| **S3** | Export mit Auswahl: Kern, Übungseinträge/Workouts/Messungen, Zeitraum (X1, X2, X4) | P185 |
| **S4** | Wiederherstellen aus der Sicherung | S2 |
| **S5** | Sensible Bereiche mit Filtern (X3): Tagesfelder, Notizen, Profilwerte; Notizen aus der Messdatei-Kopie | P183, P184 |
| **S6** | Anhänge im Export (bereinigt) | S3, S5 |
| **S7** | Import eines Auswahl-Exports in ein anderes Profil (der alte Anlass N-F1) | S3, eigene Fragen |

Jede Stufe mit Tests, Nachtrag in `docs/recht/40_toms.md` und `80_store_freigaben.md` (kein
neuer Netzweg, aber ein neuer Weg hinaus) und Gerätetest.

## 6. Recht

Kein Export bewertet etwas; Tagesfelder und Schmerzskala gehen als Zahlen hinaus
(`docs/recht/00_zweckbestimmung.md`). Der Export ist ein Werkzeug der Person, kein Bericht für
Dritte: keine Zusammenfassung, keine Ampel. Die vollständige Sicherung enthält alle Profile
des Geräts — in der Praxis-Edition wäre das ein eigenes Thema und bleibt dort aus.

## 7. Entschieden am 11.11.2026

Ben: „manueller Export kann alles sichern, für sensibel brauchen wir eine Liste. Wichtig ist,
dass die App keine medizinische Note bekommt. Persönliches und Werte, die einen Rückschluss auf
den Gesundheitszustand liefern, sind sensibel. Übungsabläufe usw. nicht, Wdh und Zeit einer
Übung … Messungsnotizen heißen Notizen, sind aber nicht sensibel. Bei Export der Messdateien
kann aber Häkchen entfernt werden, um Notizen rauszunehmen. P185: ZIP; Format so, dass es gut
mit Python ausgewertet werden kann und ggf. wieder importiert werden kann. P186: App merkt sich
Auswahl. P187: ja.“

| Frage | Entscheidung | Wo |
|---|---|---|
| P180 | Anhänge, Paketdateien, Karten, Import, Export nie ins Geräte-Backup | §1, gebaut |
| P182 | Die Sicherung, die die Person selbst anlegt, darf alles enthalten (Anhänge; Strecken wählbar) | §2; Satz für CLAUDE.md und `plan_anhaenge.md` mit S2 |
| P183 | Liste der sensiblen Bereiche; keine medizinische Note, in der Oberfläche „Persönlich“ | §3.1 |
| P184 | Notizen an Messungen sind nicht sensibel; Häkchen zum Weglassen | §3.1 |
| P185 | ZIP, JSON als Wahrheit (importierbar), CSV daneben | §3.3 |
| P186 | Die App merkt sich die ganze Auswahl je Profil; „Zurücksetzen“ stellt die Vorgaben her | §3.4 |
| — | Skalen an Übungen sind nicht sensibel; vor dem Export eine vollständige Übersicht | §3.1, §3.4 (X4) |
| P187 | Reihenfolge S1–S7 | §5 |

Alle Fragen sind beantwortet (Nachträge vom selben Tag: Skalen an Übungen nicht sensibel,
HRV und HF persönlich, Auswahl zurücksetzbar, vollständige Übersicht vor dem Export).
