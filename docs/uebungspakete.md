# Übungspakete

Übungen kommen über Pakete (Ben, 14.10.2026). Die mitgelieferten stehen im Paket
**„Grundausstattung“** (`src/trainingsapp/data/seed/exercises.json`); weitere —
Qigong, Pilates, Yoga, die Sammlung von jemand anderem — kommen per Import dazu,
und ausgewählte Übungen gehen per Export als Datei hinaus.

In der App: *Einstellungen → Übungspakete* oder unten im Übungskatalog. Aus welchem
Paket eine Übung stammt, steht klein in Klammern hinter ihrer Beschreibung; was
man selbst anlegt oder kopiert, ist eine **eigene Übung**.

Code: Format in `core/pakete.py`, Import-Regeln in `data/pakete.py`, Seed in
`data/seed.py`, Oberfläche in `ui/views/pakete.py`. Tabelle `package` und Spalte
`exercise.package_id` seit Migration 014.

## Regeln beim Import

| Die Übung (gleiche ID) … | Was passiert |
|---|---|
| gibt es hier nicht | wird angelegt |
| gehört zu **diesem** Paket | bekommt den Stand der Datei — **eigene Änderungen daran gehen verloren** (gewollt) |
| ist eine **eigene Übung** | bleibt, wie sie ist — ein Paket „Eigene“ gibt es nicht |
| gehört zu einem **anderen** Paket | bleibt, wie sie ist — sie folgt ihrem Paket |
| wurde **endgültig gelöscht** | bleibt weg (Grabstein) |

- Archivierte Übungen und solche im Papierkorb werden aktualisiert, bleiben aber dort.
- Einträge im Verlauf ändert ein Import nie — sie tragen ihre eigene Kopie der Parameter.
- Fehlende Typen und Regionen legt der Import an (oben in der Liste). Groß/klein
  trennt keine Tags: „dehnung“ landet bei „Dehnung“; ein Name, den es schon als
  Region gibt, bleibt Region.
- Vor dem Schreiben zeigt die App, was passiert (neu, aktualisiert, unverändert, …).
  Schreibt der Import nichts — etwa der eigene Export, wieder eingelesen —, entsteht
  auch kein Paket.
- **Grundausstattung:** Beim Start kommen nur fehlende Übungen dazu. Erst wenn
  `paket.version` in `exercises.json` steigt, aktualisiert der nächste Start alle
  ihre Übungen — wer die Version erhöht, überschreibt damit Änderungen der Nutzer.

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

**IDs der Grundausstattung:** Sie bleiben, wie sie vor den Paketen waren —
UUIDv5 nur aus dem Schlüssel (`seed_id`). Für alle anderen Pakete gehört die
Paket-ID in die Ableitung, damit zwei Pakete denselben Schlüssel verwenden dürfen.

**Varianten:** `variante_von` gilt, wenn das Original nach dem Import da ist. Ist
das Original selbst Variante, hängt die Übung an dessen Original (keine Ketten);
eine Übung, die Original anderer ist, bleibt eigenständig.
