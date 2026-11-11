# Plan: Export mit Auswahl und vollständige Sicherung

Stand 11.11.2026 — **Entwurf, nichts gebaut.** Anlass: P180 (Was darf ins Geräte-Backup?) und
Bens Auftrag vom 11.11.2026: „Es wäre gut, user kann ein vollständiges Backup auf Wunsch machen
… Es braucht ohnehin einen Upgrade der Exportfunktion: es soll anklickbar sein, was exportiert
wird, Filter für alle Bereiche und dabei ob Anhänge mitgeliefert werden und Datumsauswahl …
dabei wird unterschieden zwischen sensibel und nicht sensibel.“ Löst A4 (Export/Import je
Inhalt, Abschnitt 5 des Katalogs) ab.

Skizzen X1–X5: <https://claude.ai/artifact/3DfPg1WTYH2F7MDGTZwM6e> (privat, Design-Canvas).
Offene Fragen dazu: P182–P187 in `docs/offene_fragen.md`.

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

## 1. Geräte-Backup (löst P180, S23, D20, P75, S12)

Vorschlag: Der Backup-Agent (`scripts/apk_bauen.py`, `Sicherung.onFullBackup`) schließt
`Anhaenge`, `Medien/Pakete`, `Import`, `Export` aus — immer, ohne zweiten Schalter.

- Grund 1: Googles Grenze von 25 MB je App. Ein Video genügt, und Android verwirft das **ganze**
  Backup still, auch Datenbank und Messungen.
- Grund 2: Die App sagt an drei Stellen „Anhänge nie ins Backup“.
- Folge nach einer Wiederherstellung: Die Zeilen in `entry_media` zeigen auf Dateien, die
  fehlen. Die Anzeige muss das aushalten („Datei fehlt — aus einer Sicherung wiederherstellen“),
  Paketdateien lädt die App neu. Das ist vor dem Umstellen zu prüfen (Stufe S1).
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

| Bereich | Quelle | Filter (X3) | Einstufung | Vorgabe |
|---|---|---|---|---|
| Übungseinträge | `session_entry` (gültiger Stand der Kette) | Übungen, Pläne, Typ, Region | normal | an |
| Workouts | `workout_entry`, Zeitleiste | Pläne | normal | an |
| HRV-Messungen | `Messungen/`, wie heute `core/hrv_export.py` | einzelne Messungen, Gerät | normal | an |
| Trainings | Rohspur ohne Ort (`core/bewegung.py`), Kennzahlen | Sportart | normal | aus |
| Tagesfelder | `day_field`/`day_value` | **einzelne Felder** (Schmerzskala …), Text ja/nein | **sensibel** | aus |
| Notizen und Tagebuch | Notizen zum Tag, an Einträgen, an Messungen | Notiz-Tags, Art | **sensibel** | aus |
| Anhänge | `entry_media`, `Anhaenge/` | Art (Foto, Video, Audio), nur zu gewählten Bereichen | **sensibel** | aus |
| Profilwerte | Ruhe-HF, HFmax, Schwellen | — | **sensibel** | aus |

Nie im Export mit Auswahl: Koordinaten und Richtung, Bluetooth-Adresse, andere Profile,
Codes privater Pakete, Einstellungen des Geräts. GPX bleibt der eigene Knopf unter
Aufzeichnungen → Strecken.

**Sensibel** heißt hier: Gesundheitsangaben oder freier Text, in dem alles stehen kann. Die
Einstufung steht je Bereich im Code (`core/export_auswahl.py`), nicht je Datensatz; ein
Tagesfeld ist als Ganzes sensibel, auch wenn es „Schritte“ heißt (P183). Sensibles ist aus,
steht in einer eigenen Gruppe mit Schloss, und der Prüfschritt (X4) nennt es noch einmal.

Notizen an Messungen stehen heute **in der Messdatei** (`ereignisse`, `titel`, `notiz`) und
gehen mit jedem Messungsexport hinaus. Mit der Einstufung müssen sie in der Exportkopie
entfallen, solange „Notizen“ aus ist — Marken der Einheit (Abschnitte, Timer) bleiben (P184).

### 3.2 Zeitraum, Profil

Ein Zeitraum für alles (Vorgabe: letzte 6 Wochen; Schnellwahl 7 Tage · 6 Wochen · dieses
Jahr · alles), je Bereich im Filter überschreibbar. Exportiert wird das aktive Profil.

### 3.3 Format (P185)

ZIP mit `export.json` (Auswahl, Zeitraum, Formatversion `auswahl-v1`, was bewusst fehlt) und

- `eintraege.csv`, `workouts.csv`, `tagesfelder.csv`, `notizen.csv` — eine Zeile je Wert, Spalten
  mit festen Namen, UTF-8, Semikolon; dazu dieselben Daten als `daten.json` für Programme;
- `Messungen/…` wie heute (raw-v1, byte-kompatibel zu praxis_gui), `Bewegung/…` wie heute;
- `Anhaenge/…` — jede Datei durch `core/bereinigen.py` (Weißliste seit 11.11.2026); was sich
  nicht sicher bereinigen lässt, bleibt draußen und steht in `export.json` unter `ausgelassen`.

Vertrag: neuer Abschnitt in `docs/kompatibilitaet.md`, **bevor** gebaut wird.

### 3.4 Ablauf in der Oberfläche

- **X1** Einstellungen → „Export & Sicherung“: die drei Wege aus Abschnitt 0 an einem Ort. Die
  heutigen Knöpfe an Messung und Aufzeichnungen bleiben als Abkürzung (sie öffnen X2 mit
  vorgewählter Messung).
- **X2** Bereiche ankreuzen, Zeitraum, Zeile „Anhänge mitliefern“. Unten laufend Zahl und Größe.
- **X3** Filter je Bereich als Blatt (`components/blatt.blatt_spalte`), Muster wie der
  Übungsfilter (`components/uebungsfilter.py`).
- **X4** Prüfen: was hinausgeht, was hierbleibt, Hinweis bei Sensiblem, Format. Dann Teilen
  oder Speichern.
- Die letzte Auswahl merkt sich die App je Profil (ohne die sensiblen Häkchen — die sind
  jedes Mal aus, P186).

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
| **S1** | Geräte-Backup ohne Anhänge und Paketdateien; Texte vereinheitlichen; fehlende Anhangdatei aushalten | P180 |
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
