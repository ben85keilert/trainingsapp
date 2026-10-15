# Übungspakete

Übungen kommen über Pakete (Ben, 14.10.2026). Die mitgelieferten stehen im Paket
**„Standard“** (`src/trainingsapp/data/seed/standard.toml`, bis 14.10. „Grundausstattung“
als JSON — siehe [Mitgelieferte Pakete pflegen](#mitgelieferte-pakete-pflegen-toml)); weitere —
Qigong, Pilates, Yoga, die Sammlung von jemand anderem — kommen per Import dazu,
und ausgewählte Übungen gehen per Export als Datei hinaus.

In der App: der **Paketmanager** unter *Einstellungen* oder unten im Übungskatalog.
Aus welchem Paket eine Übung stammt, steht klein in Klammern hinter ihrer
Beschreibung (mit „geändert“, wenn sie vom Paketstand abweicht); was man selbst
anlegt oder kopiert, ist eine **eigene Übung**.

Code: Format in `core/pakete.py`, Paketmanager und Import-Regeln in
`data/pakete.py`, Seed in `data/seed.py`, Oberfläche in `ui/views/pakete.py`.
Tabelle `package` und Spalte `exercise.package_id` seit Migration 014,
`exercise.package_standard_json` und `package.removed_at` seit Migration 015.

## Paketmanager

| Ansicht | Was man dort tut |
|---|---|
| Liste | importieren, exportieren; installierte Pakete („16 Übungen · 2 geändert“), eigene Übungen, entfernte Pakete mit „Wieder installieren“ |
| ein Paket | seine Übungen mit Stand („wie im Paket“, „geändert: Beschreibung, Parameter“, im Archiv/Papierkorb); „Auf Paketstand“ je Übung oder „Alle auf Paketstand“; „Paket entfernen“; Export |
| eine Übung | „Paket „…“, geändert“ hinter der Beschreibung; unten „Auf Paketstand zurücksetzen“ |

**Paketstand.** Jede Übung eines Pakets trägt ihre Standardwerte aus dem Paket
(`package_standard_json`, genau die Felder des Dateiformats unten: Name, Beschreibung,
Symbol, Parameter samt Chips, Ziel, Planparameter, Limits, Typen, Regionen, Videos,
Variante).
Jeder Import frischt ihn auf; der Start trägt ihn beim Paket „Standard“ nur nach, wo er
fehlt. Wer einen Typ oder eine Region umbenennt oder löscht, ändert ihn mit — die
Paketübungen gelten danach nicht als „geändert“ (Ben, 15.10.2026). „Auf Paketstand
setzen“ schreibt ihn zurück — was man geändert hat, geht verloren; der Ort
(Katalog, Archiv, Papierkorb) bleibt, Pläne behalten ihre eigenen Einstellungen,
Einträge bleiben.

**Entfernen.** Alle Übungen des Pakets kommen in den Papierkorb und fliegen aus den
Plänen; Einträge bleiben, nach der Frist endgültig gelöscht (nur ohne Einträge). Steht
eine Übung noch in einem Plan, sagt die Rückfrage „Teil von Plan …“ und bietet an, sie
zu **kopieren**: Die Kopie ist eine eigene Übung (gleicher Name, gleiche Kachel im
Verlauf) und übernimmt die Planposition (Ben, 15.10.2026). Das Paket steht danach
unter „Entfernt“. „Wieder installieren“ (ohne Datei, aus dem Paketstand) oder ein
neuer Import holt die **Übungen** zurück, auch endgültig gelöschte — Planpositionen
nur über die Kopien. Ein entferntes Paket „Standard“ legt der Start nicht nach.

**Update und Reset behalten Eigenes an der Übung:** eigene Fotos (`image_path`) und
lokale Videos (`source = local`) kennt das Paket nicht; sie bleiben, wenn die Übung
den Paketstand bekommt (Ben, 15.10.2026).

**„Standard“ ist offen** (Ben, 15.10.2026): Eine Datei mit der ID des mitgelieferten
Pakets darf es ersetzen — die Rückfrage sagt das deutlich und nennt die Zahl der
überschriebenen Übungen; der eingebaute Stand kommt jederzeit per „Wieder installieren“
zurück.

## Regeln beim Import

| Die Übung (gleiche ID) … | Was passiert |
|---|---|
| gibt es hier nicht | wird angelegt |
| gehört zu **diesem** Paket | bekommt den Stand der Datei — **eigene Änderungen daran gehen verloren** (gewollt) |
| ist eine **eigene Übung** | bleibt, wie sie ist — ein Paket „Eigene“ gibt es nicht |
| gehört zu einem **anderen** Paket | bleibt, wie sie ist — sie folgt ihrem Paket |
| wurde **endgültig gelöscht** | bleibt weg (Grabstein) — außer das Paket war entfernt |
| gehört zu diesem Paket, und das Paket war **entfernt** | kommt zurück (aus Papierkorb oder Grabstein) |

- Archivierte Übungen und solche im Papierkorb werden aktualisiert, bleiben aber dort.
- Einträge im Verlauf ändert ein Import nie — sie tragen ihre eigene Kopie der Parameter.
- Fehlende Typen und Regionen legt der Import an (oben in der Liste). Groß/klein
  trennt keine Tags: „dehnung“ landet bei „Dehnung“; ein Name, den es schon als
  Region gibt, bleibt Region.
- Vor dem Schreiben zeigt die App, was passiert (neu, aktualisiert, unverändert, …).
  Schreibt der Import nichts — etwa der eigene Export, wieder eingelesen —, entsteht
  auch kein Paket.
- **Standard:** Beim Start kommen nur fehlende Übungen dazu. Erst wenn
  `paket.version` in `standard.toml` steigt, aktualisiert der nächste Start alle
  seine Übungen — wer die Version erhöht, überschreibt damit Änderungen der Nutzer.

## Export

Man wählt Übungen (gruppiert nach Paket und „Eigene Übungen“) und gibt dem Paket
einen Namen. Die Datei enthält **nur Übungen**: Beschreibung, Parameter, Ziel,
Typen, Regionen, Video-Links. Keine Einträge, Messungen, Strecken, Pläne, Profile.
Eigene Fotos und Videos (`local`) bleiben auf dem Gerät.

- Gleicher Name wie ein installiertes Paket → dessen ID und Version; sonst folgt die
  ID aus dem Namen (`paket_id`). Ein späterer Export unter demselben Namen
  aktualisiert das Paket also bei allen, die die neue Datei importieren.
- Auf dem eigenen Gerät bleiben exportierte eigene Übungen eigene Übungen.
- „Eigene“ und „Eigene Übungen“ sind als Paketname gesperrt.

## Dateiformat

JSON, UTF-8. Version 1:

```json
{
  "format": "trainingsapp-uebungspaket",
  "version": 1,
  "paket": {
    "id": "…",
    "name": "Qigong",
    "beschreibung": "Acht Brokate und Stehen",
    "version": 2
  },
  "exportiert": "2026-10-14T18:00:00+00:00",
  "exercises": [
    {
      "key": "baum",
      "name": "Stehen wie ein Baum",
      "description": "Knie weich, Scheitel nach oben.",
      "icon_key": "self_improvement",
      "typen": ["Qigong"],
      "regionen": ["Rücken"],
      "spec": "halten"
    },
    {
      "key": "baum_tief",
      "name": "Stehen wie ein Baum, tief",
      "typen": ["Qigong"],
      "spec": "halten",
      "variante_von": "baum"
    }
  ]
}
```

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `format` | nein | `"trainingsapp-uebungspaket"`; fehlt es, gilt die Datei als Paket |
| `version` | nein | Formatversion (1). Höher → „App aktualisieren“ |
| `paket.name` | ja* | Anzeigename. *Fehlt der Kopf, gilt der Dateiname |
| `paket.id` | nein | sonst aus dem Namen (UUIDv5, Groß/klein egal) |
| `paket.beschreibung` | nein | ein Satz, erscheint in der Paketliste und beim Import |
| `paket.version` | nein | ganze Zahl, vom Autor gepflegt |
| `exportiert` | nein | Zeitpunkt des Exports, nur zur Information |
| `exercises[]` | ja | mindestens eine Übung |

Je Übung:

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `name` | ja | |
| `id` | nein | schreibt der Export; behält die Übung auf allen Geräten |
| `key` | nein | für Pakete von Hand: ID = UUIDv5 aus Paket-ID und Schlüssel (ohne `id` und `key` zählt der Name) |
| `description`, `icon_key` | nein | Symbolnamen wie im Editor (`ui/components/icons.py`) |
| `typen`, `regionen` | nein | Listen von Namen |
| `spec` | nein | Kurzname einer Vorlage: `saetze_wdh` (Vorgabe), `halten`, `wdh_oder_halten`, `winkel`, `benchmark_zeit` |
| `result_spec` | nein | die vollständige Eingabe (`ResultSpec.to_dict()`), geht vor `spec`; schreibt der Export |
| `limit_spec`, `default_target` | nein | Objekte wie in der Datenbank |
| `default_felder` | nein | Parameter neuer Planübungen; `[]` = nur abhaken, fehlt = alle |
| `media[]` | nein | `{kind, source, uri, title, license}`; leere `uri` und `source: "local"` fallen weg |
| `variante_von` | nein | Schlüssel oder ID des Originals (im Paket oder schon auf dem Gerät) |

**IDs von „Standard“:** Sie bleiben, wie sie vor den Paketen waren —
UUIDv5 nur aus dem Schlüssel (`seed_id`); die Paket-ID stammt aus dem früheren
Namen „Grundausstattung“ (Konstante `GRUNDAUSSTATTUNG`). Für alle anderen Pakete
gehört die Paket-ID in die Ableitung, damit zwei Pakete denselben Schlüssel
verwenden dürfen.

**Varianten:** `variante_von` gilt, wenn das Original nach dem Import da ist. Ist
das Original selbst Variante, hängt die Übung an dessen Original (keine Ketten);
eine Übung, die Original anderer ist, bleibt eigenständig.

## Mitgelieferte Pakete pflegen (TOML)

Was mit der App kommt, wird von Hand gepflegt — darum steht es nicht als JSON im
Repository, sondern als **TOML** (Ben, 14.10.2026): eine Übung je
`[[exercises]]`-Block, Kommentare und Abschnitte zur Übersicht, keine Klammern
und Kommas, die beim Korrigieren brechen. Die Felder sind **dieselben** wie oben;
`data/seed.py` liest die Datei mit `tomllib` (Standardbibliothek, läuft also auch
auf dem Handy) und gibt das Ergebnis an denselben Leser wie ein Import.
Austauschformat (Import, Export) bleibt JSON.

```toml
[paket]
id = "2c1194ea-67ba-536d-aa7d-bf74bc3c73d4"
name = "Standard"
version = 1

# ── Dehnung ──────────────────────────────
[[exercises]]
key = "waden_dehnung"          # nie ändern — die ID folgt daraus
name = "Wade dehnen"
typen = ["Dehnung"]
regionen = ["Bein", "Fuß"]
spec = "halten"
icon_key = "directions_walk"
description = "Hände an der Wand, ein Bein weit nach hinten. … Je Seite."
```

- **Neue Übung:** Block kopieren, neuen `key` vergeben — sie kommt beim nächsten
  Start auf jedes Gerät, ohne Versionswechsel.
- **Korrektur an einer vorhandenen Übung:** landet sofort im Paketstand („Auf
  Paketstand setzen“ bietet sie an); überschrieben wird erst, wenn `paket.version`
  steigt — dann auch Änderungen der Nutzer.
- **`key` nie ändern:** Ein neuer Schlüssel ist eine neue Übung; die alte bliebe
  auf allen Geräten stehen.
- `tests/test_pakete.py` prüft die Datei: Schlüssel eindeutig und ohne Umlaute,
  Symbol aus `ui/components/icons.py`, Typen und Regionen aus einer festen Liste
  (Tippfehler legten sonst auf jedem Gerät einen neuen Tag an), Original einer
  Variante vorhanden. Ein TOML-Syntaxfehler meldet sich mit Zeile und Spalte.

Warum nicht YAML: braucht eine Zusatzbibliothek auf dem Handy, und YAML deutet
unsere Notation um — `1:30` wird zu `90`, `+20` zu `20`, `no` zu `false`.

Weitere mitgelieferte Pakete (Dehnung, Kräftigung, …) kommen als eigene Datei
daneben, je Paket eine.
