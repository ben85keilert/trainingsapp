# Plan: Tagesfelder – Parameter und Tags an der Tagesnotiz

Stand 21.10.2026: **Gebaut** (Teile A–H, Migration 027), Gerätetest T70 offen, P68 (Recht)
offen. Ben zu den Skizzen, am selben Tag:

> - A1 ist gut, aber der Block "Zum Tag" muss runter unter gemacht ans Ende
> - A3: Skalen sollen als Schiebebalken dargestellt werden
> - nach A3 alle A gut
> B und C gut
> - E1 gut
> - F: VOllständig bei Umgebungsvariablen, gut
> - G: nachtragen auch gut, Zeit festlegen, dabei soll die alte Zeit genommen werden als
>   VOrlage, rest auch gut, bitte einbauen

Umgesetzt:
- **Platz**: Der Block „Zum Tag“ (Notiz zum Tag + Felder) steht ganz unten unter Heute,
  hinter „Gemacht“ und den Plannotizen. In der Zeitleiste stehen die Felder unten ohne die
  Notiz, denn die steht dort schon an ihrer Uhrzeit.
- **Skalen** als Schiebebalken (`ui/components/skala_regler.py`), statt des Rasters aus A3.
  Die Sitzung „Nachtragen in Übungen“ nimmt dieselbe Komponente, falls Übungen sie bekommen.
- **E1**: eigener Reiter „Zum Tag“ im Verlauf. **F**: Tagebuch wie beschrieben, „Übungen
  und Felder“.
- **G**: Beim Nachtragen ist die alte Zeit vorbelegt (`core.tagesfelder.uhrzeit_vorlage`):
  - an einem vergangenen Tag die des letzten Werts dieses Felds an dem Tag, sonst die des
    letzten Werts überhaupt, sonst 12:00;
  - beim Ändern eines Eintrags seine bisherige Uhrzeit.

  In der Zeitleiste stehen Werte desselben Felds hintereinander in einer Zeile
  („Trinken 1,25 l · 5× · 08:00–12:30“), ein Wert mit Notiz für sich.
- Ohne ausdrückliche Antwort nach Vorschlag:
  - Name „Tagesfelder“/„Zum Tag“ (P64);
  - je Profil (P67);
  - die Art ist gesperrt, sobald es Werte gibt (P66).
- **Löschen „mit allen Einträgen“** (P69) ist wie bei Einträgen weich: Die Zeilen bleiben
  mit `deleted_at` als Grabstein in der Datenbank (für den Abgleich) und sind überall
  unsichtbar. Ein endgültiges Entfernen wie im Papierkorb gibt es nicht.

Skizzen: https://claude.ai/artifact/NmRnqbA954N6fwjKQ1Ytk5

| Reihe | Bilder | Teile |
|---|---|---|
| A | A1–A5: Heute mit „Zum Tag“ oben (A1) oder unten (A2), Skala, Anzahl mit Varianten, nur Text | C |
| B | B1–B3: Einstellungen → Tagesfelder, neues Feld, Löschen | D |
| C | C1–C4: Verlauf → Tage, Reiter „Zum Tag“, ein Feld als Säulen, Tagebuch | E, F |

Anlass ist Bens Notiz „Tagesnotiz“ vom 21.10.:

> Auch hier Parameter und Tags ermöglichen:
> - wichtig z.B. zum Tracking von Beschwerden mit Skalen 0-10 oder anderweitig
> - Festlegung von Dingen, vlt auch mit frei wählbarem Tag-Label, das solange aktiv
>   getrackt werden kann, z.B. Trinkmenge
> - Parameter kann für ganzen Tag oder mehrfach gesetzt werden. Das ganze darf aber auch
>   nicht zu kompliziert werden
> - damit kann man z.B. die Medikamenteneinnahme täglich beschreiben Ibu 400 1,2,3,... mit
>   Variante ließe sich z.B. darstellen wieviele Ibu 400 oder 800 (Variante) man in der
>   letzten Zeit genommen hat
> - oder man hat ein Label um spezielle Dinge nieder zu schreiben, z.B. Themenspezifisch
>   tag-"Ernährung", "Spazieren", "Meditation"
> - die Tages-tags und Parameter sollen sich aktivieren und deaktivieren lassen, es soll
>   eine Auswahl geben, man soll sie löschen können, so dass sie im Kalender bleiben oder
>   gelöscht werden können

## Der Begriff

Ein **Tagesfeld** ist Bens „Tag-Label“: frei benannt („Schmerz“, „Trinken“, „Ibu“,
„Ernährung“), mit oder ohne Wert, und es gehört zum Profil (P67). Es ist **aktiv** (steht
unter Heute), **ausgeschaltet** (steht nicht unter Heute, alles bleibt) oder **gelöscht**
(mit oder ohne seine Einträge).

Je Feld gibt es **genau eine Art**. So bleibt es einfach; wer Schmerz und Schlaf will, legt
zwei Felder an.

| Art | Feldtyp (`core/result_spec`) | Tageswert bei „mehrmals“ | Beispiel |
|---|---|---|---|
| Skala | `SCALE`, Bereich frei (Vorgabe 0–10) | Mittel | Schmerz, Stimmung |
| Anzahl | `INT`, Schnellknopf „+1“ | Summe | Ibu |
| Menge | `FLOAT` mit Einheit, Schnellknöpfe | Summe | Trinken (ml) |
| Dauer | `DURATION`, Schnellknöpfe | Summe | Meditation, Spazieren |
| Ja/Nein | `BOOL` | „ja“, wenn einmal ja | Mittagsschlaf |
| nur Text | kein Wertfeld, nur die Notiz | – | Ernährung |

Dazu kommen:
- **Varianten**, wahlweise: dasselbe CHOICE-Feld `variant` wie bei den Übungen
  (`core/varianten.py`). Jede Variante wird getrennt gezählt, etwa Ibu 400 und 800 oder
  Schmerz Knie und Rücken.
- **eine Notiz je Wert**: Sie steht dann im Tagebuch.

**Wie oft** wird je Feld eingestellt:
- **einmal am Tag**: ein Wert je Tag und Variante; ein neuer Tipp korrigiert ihn.
- **mehrmals mit Uhrzeit**: Jeder Tipp ist ein eigener Eintrag mit Uhrzeit (jetzt oder
  früher).

Vorgabe: Skala, Ja/Nein und Text einmal am Tag, Anzahl, Menge und Dauer mehrmals.

| Teil | Was | Schicht |
|---|---|---|
| A | Datenmodell: `day_field`, `day_value` | `data/migrations/027_…`, `data/tagesfelder.py` |
| B | Kern: Arten, Tagesstand, Anzeige, Brücke zum Verlauf | `core/tagesfelder.py` |
| C | Heute: Block „Zum Tag“, Blätter, Schnellknopf | `ui/views/tag.py`, neue `ui/components/tagesfeld_blatt.py` |
| D | Verwalten: Liste, Neu/Bearbeiten, Löschen | neue `ui/views/tagesfelder.py`, `einstellungen.py` |
| E | Verlauf: Tage, Reiter „Zum Tag“, Feldansicht | `ui/views/verlauf.py`, `verlauf_kachel.py`, `components/wochenleiste.py` |
| F | Tagebuch: Werte und Texte der Felder | `core/tagebuch.py`, `ui/views/tagebuch.py` |
| G | Zeitleiste: „mehrmals“-Werte nach der Uhr | `core/tag.py`, `ui/views/tag.py` |
| H | Doku und Recht | `docs/datenmodell.md`, `docs/recht/00_…`, `10_…` |

**Unberührt bleiben Pläne, Kurse, Pakete und der Übungskatalog** (Bens Setzung vom
21.10.: Pläne und Kurse nur mit Rückfrage). Tagesfelder sind keine Übungen:
- Sie stehen in keinem Plan.
- Sie zählen in keiner Kursbedingung.
- Sie reisen nicht in Paketen.
- Sie erscheinen nicht unter „Übungen“ und nicht in „Nachtragen“.

Spätere Ideen (Paket liefert Tagesfeld-Vorlagen, Kursbedingung „an n Tagen ausgefüllt“)
nur auf Bens Wunsch.

---

## A. Datenmodell (Migration 027)

Tagesfelder bekommen **eigene Tabellen**, nicht `exercise` und `session_entry`. Gut 20
Stellen lesen „die Einträge eines Tages“, und jede müsste Tagesfelder herausfiltern:
- `core/plaene.py` und `core/kurse.py` (mit Rückfrage-Pflicht);
- Tagesbilanz und Bezüge;
- HRV-Marken, Nachtragen, Verlauf.

Eigene Tabellen lassen all das unberührt. Die Technik bleibt dieselbe wie bei Übungen:
`ResultSpec`, Spec-Kopie je Wert, Korrektur als neue Zeile.

```sql
-- Was jemand an jedem Tag festhalten will (veränderlich: letzter Schreiber gewinnt)
CREATE TABLE day_field (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL REFERENCES subject(id),
    name              TEXT NOT NULL,
    -- ResultSpec: ein Wertfeld (keins bei „nur Text“), wahlweise `variant`
    spec_json         TEXT NOT NULL DEFAULT '{}',
    mehrmals          INTEGER NOT NULL DEFAULT 0,
    sort_order        INTEGER NOT NULL DEFAULT 0,
    active            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    revision          INTEGER NOT NULL DEFAULT 0,
    origin_device_id  TEXT,
    deleted_at        TEXT
);

-- Ein Wert — UNVERÄNDERLICH wie session_entry, Korrektur über replaces_value_id
CREATE TABLE day_value (
    id                  TEXT PRIMARY KEY,
    subject_id          TEXT NOT NULL REFERENCES subject(id),
    field_id            TEXT NOT NULL REFERENCES day_field(id),
    date                TEXT NOT NULL,          -- lokaler Tag wie day_note.date
    recorded_at         TEXT NOT NULL,          -- UTC über models.iso_utc
    result_json         TEXT NOT NULL DEFAULT '{}',
    spec_snapshot_json  TEXT NOT NULL DEFAULT '{}',
    note                TEXT NOT NULL DEFAULT '',
    replaces_value_id   TEXT REFERENCES day_value(id),
    created_at          TEXT NOT NULL,
    origin_device_id    TEXT,
    deleted_at          TEXT
);
CREATE INDEX idx_day_value_tag  ON day_value(subject_id, date) WHERE deleted_at IS NULL;
CREATE INDEX idx_day_value_feld ON day_value(field_id, date)   WHERE deleted_at IS NULL;
```

- Gültig ist eine Zeile, die nicht ersetzt und nicht gelöscht ist. Das gleiche Muster
  wie bei den Einträgen steht in `SessionRepo`.
- „Einmal am Tag“ ändert den Wert, indem eine neue Zeile die alte ersetzt
  (`replaces_value_id`). Der Wert ist also eine Korrektur wie bei den Einträgen.
- **Ausschalten**: `active = 0`.
- **Löschen, Einträge behalten**: `day_field.deleted_at` wird gesetzt, die Werte
  bleiben, ihr Name kommt aus der Spec-Kopie bzw. aus der gelöschten Feldzeile.
- **Mit Einträgen löschen**: Zusätzlich bekommen die Werte `deleted_at`.
  „Rückgängig“ nimmt beides zurück.
- `data/tagesfelder.py`: `TagesfeldRepo` (alle, aktive, anlegen, ändern, umordnen,
  schalten, löschen) und `TageswertRepo` (am_tag, im_zeitraum, setzen, hinzufügen,
  korrigieren, löschen). SQL nur mit `?`.

## B. Kern (`core/tagesfelder.py`, ohne Datenbank, ohne Flet)

- `ARTEN`: Art → `FieldSpec` (Schlüssel `value`; Einheit, Bereich und Schnellknöpfe
  stehen im Feld).
- `VORSCHLAEGE`: die Auswahl in B2, als Daten mit Name, Art, Bereich bzw. Einheit,
  Schnellknöpfen und „wie oft“. Ob „Schmerz“ und „Medikament“ darunter stehen dürfen,
  klärt P68.
- `Tagesfeld` und `Tageswert` als Wertetypen.
- `tagesstand(feld, werte)`: je Variante Summe, Mittel oder letzter Wert, nach Art und
  „wie oft“.
- `stand_text(...)`: „400 × 2“, „1,25 l“, „3“, „–“.
- `als_eintraege(werte)`: Werte als `SessionEntry`-Objekte nur im Speicher. Damit
  rechnen `core/verlauf.kennzahlen`, `linien`, `tageswerte` und `haeufigkeit` ohne eine
  zweite Kurvenrechnung.
- Doctests für alles; ein Test in `test_import_regel.py` ist nicht nötig, die Regel
  gilt ohnehin.

## C. Heute (A1–A5)

- Für den Platz gibt es zwei Vorschläge (P63):
  - **A1**: ein Block „Zum Tag“ oben. Darin steht die Notiz zum Tag, darunter je aktivem
    Feld ein Knopf.
  - **A2**: Die Knöpfe stehen klein in der bisherigen Karte „Zum Tag“ unter
    „Notizen“.
- **Knopf** je Feld: Name (mit Variante), Stand von heute.
  - Ein Tipp öffnet das Blatt.
  - Hat das Feld einen Schnellknopf („+250“, „+1“), trägt der kleine Knopf daneben
    sofort ein. Danach steht „Rückgängig“ (`dialoge.meldung`, nicht persistent).
  - Bei Varianten gilt die zuletzt gewählte Variante.
- **Blätter** (`ui/components/tagesfeld_blatt.py`):
  - Skala: Raster 0–10 in zwei Reihen, ✕ löscht.
  - Anzahl, Menge und Dauer: großer „+“-Knopf, Uhrzeit „jetzt“ oder früher, die Liste
    von heute (antippen ändert, ✕ löscht).
  - Ja/Nein: zwei Knöpfe.
  - Text: wie `notiz_dialog`, speichert beim Schließen („Zurück speichert“).
  - Varianten stehen oben als Segment wie in der Übung.
- Ein **vergangener Tag** (`/tag/<datum>`) zeigt dieselben Knöpfe. Die Uhrzeit ist mit
  12:00 vorbelegt wie beim Nachtragen.
- Kopfzeile: „2 Übungen · 1 Notiz · 4 Tageswerte“ (`core/tag.zusammenfassung`).
- Ohne aktive Felder ändert sich unter Heute nichts außer einem Link
  „Tagesfelder …“ neben „Notiz zum Tag“.

## D. Verwalten (B1–B3)

- Einstellungen → **Tagesfelder** (`/einstellungen/tagesfelder`), außerdem über das
  Symbol am Block „Zum Tag“.
  - „Aktiv“: Reihenfolge = Reihenfolge unter Heute, Schalter.
  - „Ausgeschaltet“: kommt mit dem Schalter zurück.
- **Neu und Bearbeiten** (`/einstellungen/tagesfelder/<id>`):
  - Speichern und Abbrechen stehen in der Titelleiste, Zurück speichert.
  - Oben stehen die Vorschläge, darunter Name, Art, Einzelheiten der Art, Varianten und
    „wie oft“.
  - Eine Vorschau zeigt den Knopf, wie er unter Heute steht.
- **Die Art ist gesperrt**, sobald es Werte gibt (Vorschlag, P66). Name, Bereich,
  Einheit, Schnellknöpfe und Varianten bleiben änderbar. Alte Werte zeigen sich weiter
  mit ihrer Spec-Kopie.
- **Löschen** (lang drücken oder im Formular) fragt nach den drei Wegen aus B3 (P69).

## E. Verlauf (C1–C3)

- **Tage**: Über den Übungen des gewählten Tags steht „Zum Tag“ mit den Werten. In der
  Woche bekommt ein Tag mit Tageswerten eine kleine Raute
  (`components/wochenleiste.tageszelle`).
- Für die Liste der Felder gibt es zwei Wege (P65):
  - **Reiter „Zum Tag“**: je Feld eine Zeile mit Mini-Kurve und letztem Wert;
    ausgeschaltete und gelöschte (mit behaltenen Einträgen) stehen darunter.
  - **Abschnitt unter „Übungen“** als Alternative.
- **Feldansicht** (`/verlauf/tagesfeld/<id>`):
  - Anzahl, Menge und Dauer: Säulen je Tag, je Variante eine Farbe (`ui/farben`).
  - Skala: eine Linie je Variante (mehrere Werte am Tag: das Mittel).
  - Ja/Nein: Häufigkeit.
  - Text: nur die Liste.
  - Darunter stehen Kacheln (Summe je Variante im Zeitraum, Tage mit Eintrag) und die
    Einträge je Tag mit Uhrzeit und Notiz.
- **Kein Trendpfeil, keine Bewertung, keine Grenzlinie** (P68): nur Zahlen.

## F. Tagebuch (C4)

- `core/tagebuch.sammeln` bekommt die Tageswerte. Daraus entstehen zwei Dinge:
  - Text-Felder und Werte mit Notiz werden eine Notiz der neuen Art `TAGESFELD`. Der
    Titel ist „Feld · Variante“, dazu kommt der Wert.
  - An der Notiz zum Tag steht eine Zeile mit den Werten des Tags. Ein Tag nur mit
    Werten erscheint dann auch ohne Text.
- „Nach Übungen“ heißt dann „Übungen und Felder“ und bekommt je Tagesfeld eine Gruppe.
- `zahl_je_tag` zählt Texte und Werte mit Notiz, nicht jeden Tipp auf „+1“.

## G. Zeitleiste

- Werte, die „mehrmals“ gesetzt werden, stehen als kleine Punkte nach der Uhr
  („14:30 Ibu 400“).
- Werte „einmal am Tag“ stehen an der Notiz zum Tag.
- Kann nach dem ersten Wurf kommen.

## H. Doku und Recht

- `docs/datenmodell.md`: die beiden Tabellen.
- `docs/recht/10_verarbeitungsverzeichnis.md`: eine neue Kategorie „Tagesfelder
  (Beschwerden, Einnahmen, Ernährung, …)“, Art. 9: ja.
- `docs/recht/00_zweckbestimmung.md`, Abgrenzung (P68):
  - Erlaubt ist Dokumentieren.
  - Nicht erlaubt: Erinnerung an Einnahmen, Hinweise zur Dosis, Grenzwerte, Bewertung,
    Trend als Urteil.
- Geräte-Backup und Export: Tagesfelder liegen in der Datenbank. Sie gehen dorthin, wohin
  auch die Einträge gehen (Backup nur, wenn eingeschaltet).
- `config`: keine eigene Sperre nötig, solange beide Editionen es dürfen. Für die
  Praxisanbindung (Sync) gibt es die Sync-Felder schon.

## Tests

- `core/tagesfelder.py`: Doctests zu Arten, Tagesstand, Text und Brücke zum Verlauf.
- `tests/test_tagesfelder.py`: Repo (anlegen, schalten, umordnen, „einmal am Tag“
  korrigiert statt doppelt, mehrmals, drei Löschwege und Rückgängig, Tagesgrenzen mit
  Zeitumstellung).
- `tests/test_ui_tag.py`, `test_ui_tagebuch.py`, `test_ui_verlauf.py`: Knöpfe,
  Schnellknopf mit Rückgängig, Blätter, Reiter, Tagebuch-Art.
- Migration 027 in der vorhandenen Migrationsprüfung (`tests/test_repositories.py`).
