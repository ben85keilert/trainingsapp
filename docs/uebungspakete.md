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
| Liste | importieren, exportieren; installierte Pakete („16 Übungen · 2 geändert · 1 nicht mehr im Paket · Version 2 · 31 kB · 48 MB Fotos/Videos“, deaktivierte ausgegraut), eigene Übungen, entfernte Pakete mit „Wieder installieren“ |
| ein Paket | seine Übungen mit Stand („wie im Paket“, „geändert: Beschreibung, Parameter“, „nicht mehr im Paket“, im Archiv/Papierkorb) und seine Kurse; „Auf Paketstand“ je Übung oder „Alle auf Paketstand“; „Deaktivieren“/„Aktivieren“; „Paket entfernen“; Export; Karte „Nicht mehr im Paket“ mit „Entscheiden“ |
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

**Update lässt Geändertes stehen** (Ben, 16.10.2026). Der Paketstand ist die „Signatur“
dessen, was vom Paket kam. Kommt eine neue Fassung, gilt je Feld
(`core/pakete.zusammenfuehren`): noch wie im alten Paketstand, also nie angefasst → der
neue Wert; abweichend, also selbst geändert → bleibt. Der gespeicherte Paketstand wird
trotzdem der neue; „geändert: Beschreibung“ zeigt danach, wo „Auf Paketstand“ Neues
brächte. Lokale Fotos und Videos bleiben ohnehin.

**Nicht mehr im Paket** (Migration 017). Fehlt eine Übung oder ein Kurs in der neuen
Fassung, löscht die App nichts: Sie markiert sie (`package_dropped_at`) und fragt —
nach dem Import sofort, sonst beim nächsten Start — je Eintrag: **übernehmen** (wird
eigene Übung mit derselben ID; Verlauf und Pläne bleiben, „Teil von Plan …“ steht
dabei) oder **löschen** (Papierkorb, raus aus den Plänen). „Wieder installieren“ holt
Entfallenes nicht zurück. Bis zur Entscheidung zeigt die Paketansicht die Karte
„Nicht mehr im Paket“.

**Deaktivieren** (Migration 017) ist das Gegenteil von Entfernen: nichts geht in den
Papierkorb, aber Übungen und Kurse des Pakets verschwinden aus Katalog, Suche,
Typen/Regionen, Kursliste und Planansichten (die Positionen bleiben im Plan und kommen
mit „Aktivieren“ zurück); der Verlauf sieht weiter alles. Seed, Entwicklungs-Loader
und Paketquellen lassen ein deaktiviertes Paket in Ruhe; ein Datei-Import aktualisiert
es, ohne es zu aktivieren. Gedacht fürs Aufräumen der Ansicht und die Arbeit an
Inhalten am Rechner.

**Größe.** Die Paketzeile nennt, was das Paket belegt: die Texte (Paketstände) und, wenn
vorhanden, eigene Fotos und Videos an seinen Übungen (`PaketRepo.groesse`).

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
| gehört zu **diesem** Paket | bekommt den Stand der Datei — **was man selbst geändert hat, bleibt** (je Feld, siehe oben) |
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
  seine Übungen — Änderungen der Nutzer bleiben dabei (je Feld). Fällt eine Übung aus
  der Datei, wird sie auch ohne Versionssprung als „nicht mehr im Paket“ markiert.
  Ist „Standard“ schon in höherer Version installiert (aus einer Paketquelle oder
  Datei), lässt der Start es ganz in Ruhe: keine Version zurück, keine Markierung
  (K6, 17.10.2026).

## Export

Man wählt Übungen (gruppiert nach Paket und „Eigene Übungen“) und gibt dem Paket
einen Namen. Die Datei enthält **nur Übungen**: Beschreibung, Parameter, Ziel,
Typen, Regionen, Video-Links. Keine Einträge, Messungen, Strecken, Pläne, Profile.
Eigene Fotos und Videos (`local`) bleiben auf dem Gerät. Kurse exportiert der Dialog
noch nicht (sie kommen bisher nur mitgeliefert oder per Import; `paket_bauen` kann
sie schreiben — der Kurseditor bringt den Export mit).

- Gleicher Name wie ein installiertes Paket → dessen ID und Version; sonst folgt die
  ID aus dem Namen (`paket_id`). Ein späterer Export unter demselben Namen
  aktualisiert das Paket also bei allen, die die neue Datei importieren.
- Auf dem eigenen Gerät bleiben exportierte eigene Übungen eigene Übungen.
- „Eigene“ und „Eigene Übungen“ sind als Paketname gesperrt.

## Dateiformat

JSON, UTF-8. Version 1 (Übungen); **Version 2** fügt `kurse[]` hinzu — eine Datei
ohne Kurse wird weiter als Version 1 geschrieben, ältere Apps lesen sie:

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
| `paket.neuigkeiten` | nein | kurzer Text: was in dieser Version neu ist — die App zeigt ihn unter „Updates“ |
| `exportiert` | nein | Zeitpunkt des Exports, nur zur Information |
| `exercises[]` | ja* | Übungen — *darf fehlen, wenn `kurse[]` da ist |
| `kurse[]` | nein | Kurse (Version 2, `docs/plan_kurse.md`) — Felder unten |

Je Übung:

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `name` | ja | |
| `id` | nein | schreibt der Export; behält die Übung auf allen Geräten. Jede `id` im Paket (Paket, Übung, Kurs, Kapitel) besteht nur aus Buchstaben, Ziffern, `-` und `_`, 1–64 Zeichen (`^[A-Za-z0-9_-]{1,64}$`, UUIDs erfüllen das) — sonst lehnt der Import das Paket ab |
| `key` | nein | für Pakete von Hand: ID = UUIDv5 aus Paket-ID und Schlüssel (ohne `id` und `key` zählt der Name) |
| `description`, `icon_key` | nein | Symbolnamen wie im Editor (`ui/components/icons.py`) |
| `typen`, `regionen` | nein | Listen von Namen |
| `spec` | nein | Kurzname einer Vorlage: `saetze_wdh` (Vorgabe), `halten`, `wdh_oder_halten`, `winkel`, `benchmark_zeit` |
| `result_spec` | nein | die vollständige Eingabe (`ResultSpec.to_dict()`), geht vor `spec`; schreibt der Export |
| `limit_spec`, `default_target` | nein | Objekte wie in der Datenbank |
| `timer[]` | nein | Timer-Profile der Übung (Ben, 17.10.2026; `docs/plan_einheit.md`, Stufe 3): je Profil `name`, `abschnitte[]` (`name`, `dauer_s`, `klang`, `zaehlt` — fehlt `zaehlt`, zählt der Abschnitt), `runden`, für eine Folge `teil_name` und `teile[]` (`name`, `runden`, `abschnitte[]`). `id` schreibt der Export; ohne sie eine feste aus Übung und Stelle. Fehlt `timer`, gilt eine Timer-Regel im `limit_spec` als Einzeltimer. Im Drei-Wege-Abgleich ein Feld |
| `uhr` | nein | Stoppuhr und Timer stehen in der Übung bereit (Ben, 18.10.2026; `docs/plan_stoppuhr.md`); fehlt = an, `false` = aus. Im Drei-Wege-Abgleich ein Feld |
| `zaehlt_als` | nein | „Zählt als“, wenn die Übung Haltezeit anbietet: `hold` (Haltezeit, ein Satz je Lauf) oder `duration` (Zeit); fehlt = Haltezeit. Ohne Haltezeit zählt die Uhr immer als Zeit. Im Drei-Wege-Abgleich ein Feld |
| `default_felder` | nein | Parameter neuer Planübungen; `[]` = nur abhaken, fehlt = alle |
| `media[]` | nein | `{kind, source, uri, title, license}`; leere `uri` und `source: "local"` fallen weg. `uri` nur `https://…` oder `mailto:…` — andere Schemata (`http://`, `intent://`, `tel:`, `file://`) verwirft der Import still, die Übung bleibt; die App öffnet außerdem vor jedem Tipp nur solche Adressen (`core/links.py`, auch für Links im Kapiteltext) |
| `variante_von` | nein | Schlüssel oder ID des Originals (im Paket oder schon auf dem Gerät) |

Je Kurs (`kurse[]`, Formatversion 2):

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `name` | ja | |
| `id` / `key` | nein | wie bei Übungen: ID = UUIDv5 aus Paket-ID und `kurs:<key>` |
| `beschreibung` | nein | |
| `freischaltung` | nein | `frei`, `rueckfrage` (Vorgabe), `streng` |
| `kapitel[]` | ja | mindestens eines, in dieser Reihenfolge |

Je Kapitel: `titel` (Pflicht), `key` (nie ändern — die Kapitel-ID folgt daraus und
der **Fortschritt der Nutzer hängt daran**; ohne `key` zählt die Nummer), `text`
(Markdown), `media[]` (wie bei Übungen, zusätzlich `kind: "audio"`), `plaene[]`
(`{name, wochentage: [0..6], uebungen: [{uebung: <key|id>, ziel?, felder?}]}`) und
`bedingung` (`{art: "gelesen"}` Vorgabe · `{art: "summe", uebung, feld, soll}` ·
`{art: "tage", soll}` · `{art: "messung", soll}` in Minuten). `uebung` ist der
Schlüssel einer Übung desselben Pakets oder eine ID.

Import: Kurse folgen den Regeln der Übungen (neu → anlegen; gleiches Paket →
Stand der Datei, Kapitel gleicher ID behalten den Fortschritt; eigene/fremde →
bleiben). Entfernen nimmt die Kurse aus der Liste, „Wieder installieren“ holt sie
aus dem Paketstand (`course.package_standard_json`) zurück.

**IDs von „Standard“:** Sie bleiben, wie sie vor den Paketen waren —
UUIDv5 nur aus dem Schlüssel (`seed_id`); die Paket-ID stammt aus dem früheren
Namen „Grundausstattung“ (Konstante `GRUNDAUSSTATTUNG`). Für alle anderen Pakete
gehört die Paket-ID in die Ableitung, damit zwei Pakete denselben Schlüssel
verwenden dürfen.

**Varianten:** `variante_von` gilt, wenn das Original nach dem Import da ist. Ist
das Original selbst Variante, hängt die Übung an dessen Original (keine Ketten);
eine Übung, die Original anderer ist, bleibt eigenständig.

## Inhalte pflegen (Inhalte-Repo, `TRAININGSAPP_PAKETE`, `trainingsapp-paket`)

Eigene Pakete entstehen im privaten Repo `trainingsapp-inhalte` als TOML wie
`standard.toml`, eine Datei je Paket. Die App liest sie am Rechner **direkt**: Mit der
Umgebungsvariable `TRAININGSAPP_PAKETE=<ordner>` spielt jeder Start alle `.toml`/`.json`
darin wie einen Import ein — immer auf den Stand der Datei, auch für die ID von
„Standard“ (`data/seed.pakete_aus_ordner`). Entfernte und deaktivierte Pakete bleiben
unangetastet; was aus einer Datei fiel, fragt der Start wie bei jedem Update. Ging eine
Datei nicht (Tippfehler), steht die Meldung mit Zeile oben auf „Heute“.

```bash
cd ../trainingsapp-inhalte
TRAININGSAPP_DATA_DIR=.daten TRAININGSAPP_PAKETE=pakete \
  uv run --project ../trainingsapp flet run ../trainingsapp/src/trainingsapp/ui/app.py
```

Fürs Handy und für Paketquellen braucht es JSON — das Werkzeug `trainingsapp-paket`
(`src/trainingsapp/paket_werkzeug.py`, kein flet) liegt in der trainingsapp, nicht im
Inhalte-Repo (öffentliche Repos hängen nie von privaten ab, umgekehrt schon):

```bash
uv run --project ../trainingsapp trainingsapp-paket pruefen pakete/*.toml
uv run --project ../trainingsapp trainingsapp-paket bauen pakete/*.toml --ziel dist/
uv run --project ../trainingsapp trainingsapp-paket index dist/*.json \
  --ziel dist/index.json --basis-url https://…/pakete/ --quelle "Praxis Ebert"
```

`pruefen` wendet die Regeln des Standardpakets an (Schlüssel, Beschreibung, Variante,
Symbol — Symbole nur mit flet); Typen und Regionen außerhalb des Standardpakets sind
Hinweise. `--wortliste DATEI` sucht Begriffe, die in Pakettexten nichts verloren haben
(Sprachregelung der Praxis-Website: erklären, nicht bewerten — die Liste liegt im privaten
Repo der Homepage, `docs/wortliste-zone3.txt`); Treffer sind Hinweise, mit `--streng`
Fehler. `index` schreibt den Index einer Paketquelle (ID, Name, Version, URL, SHA-256,
Größe, Neuigkeiten, reserviertes Feld `signatur`) — das Format, das die App für Updates
liest. `quelle URL` liest einen veröffentlichten Index wie die App und prüft jede
Paketdatei samt Prüfsumme. Wie die Dateien auf den Server kommen: Homepage,
`docs/runbooks/trainingsapp-pakete.md` (rsync mit beschränktem Schlüssel).

## Paketquellen — Updates online (Ben, 16.10.2026)

Eine **Quelle** ist eine HTTPS-Adresse, unter der ein **Index** liegt — die JSON, die
`trainingsapp-paket index` schreibt: je Paket `id`, `name`, `beschreibung`, `version`,
`url` (Paketdatei), `sha256`, `bytes`, `uebungen`, `kurse`, `neuigkeiten`,
`veroeffentlicht` (Datum des letzten Inhaltswechsels: bei gleicher Prüfsumme bleibt es
aus dem vorigen Index am `--ziel` stehen, K30), `signatur` (reserviert, `null`). Kopf:
`format = "trainingsapp-paketindex"`, `version = 1`, `quelle.name`. Das Format ist bewusst so
einfach, dass es von jedem Webserver, von GitHub Pages oder aus einem Release kommen
kann (`core/paketquelle.py`).

- **Quellen** stehen unter Einstellungen → Updates: die Vorgabe (der Server des
  Herstellers, `QUELLE_VORGABE` = `https://trainingsapp.osteo-ebert.de/pakete/index.json`,
  seit 16.10.2026 — Übergang, bis die Website der App steht; Inhalte aus
  `trainingsapp-inhalte`, siehe oben) und eigene, nur `https://` (zum Ausprobieren auch `http://localhost`/`127.0.0.1`,
  etwa `python -m http.server` im `dist/`-Ordner des Inhalte-Repos).
- **Prüfung** beim Start (abschaltbar, beim ersten Mal ein Hinweis; nur Versionsnummern,
  es gehen IP-Adresse und der Name der App hinaus) oder per „Jetzt prüfen“. Nennen
  zwei Quellen dasselbe Paket, zählt die erste; nur aktive Pakete bekommen Updates,
  nie nach unten. Ein Paket, das es hier nicht gibt, erscheint unter „Neu in den
  Quellen“ zum Installieren.
- **Modus je Paket:** `automatisch` (Vorgabe) spielt ein Update beim Start ein,
  `manuell` merkt es nur vor (`package.available_*`) — der Pfeil holt es mit der
  Vorschau des Datei-Imports. Was man an Übungen geändert hat, bleibt (Drei-Wege-
  Abgleich); Entfallenes fragt nach wie immer.
- **Sicherheit:** HTTPS sichert die Herkunft, die Prüfsumme den Download (stimmt sie
  nicht, wird nichts geschrieben), die Datei muss zur ID im Index passen, maximal
  5 MB. Eine Signatur kommt, wenn Pakete von Dritten kommen.
- **Quellenbindung** (Sicherheitsdurchsicht S3, Ben, 20.10.2026): Ein Paket bekommt
  Updates nur aus der Quelle, die es zuletzt lieferte — `package.source_url` hält die
  Adresse ihres Index (seit Migration 026; die Bindung entsteht beim ersten Einspielen
  aus einer Quelle, auch im Modus „automatisch“). Pakete ohne Bindung — per Datei
  importiert oder über `TRAININGSAPP_PAKETE` — bekommen von keiner Quelle Updates; wer
  per Datei holt, holt weiter per Datei. Einzige Ausnahme: das mitgelieferte „Standard“
  darf aus `QUELLE_VORGABE` aktualisiert werden. So kann eine eingetragene Fremdquelle
  kein vertrautes Paket „aktualisieren“, auch nicht beim Start (`paketquelle.quelle_passt`).
  Ein **Datei-Import**, dessen `id` zu einem Paket aus einer Quelle oder zu „Standard“
  gehört, sagt es in der Rückfrage deutlich („Diese Datei gibt sich als ‚Standard‘ aus
  (bisher mitgeliefert). Nur fortfahren, wenn du der Datei vertraust.“,
  `paketquelle.fremde_identitaet`) — entscheiden tut die Person, kein Verbot.
- **Label unter dem Zahnrad:** „Updates verfügbar: 2 Pakete, App“ — einmal je Stand,
  bis die Seite „Updates“ geöffnet wurde. Einstellbar: aus / nur Updates / Updates und
  Neuigkeiten (dann auch neue Pakete in den Quellen).
- Edition B bekommt ihre Pakete von der Praxis (`ist_aktiv("paket_quellen")` nur Solo).

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

- **`paket.version`:** Die Datei entspricht einem veröffentlichten Stand (Paketquelle):
  gleiche Version, gleicher Inhalt. Wo „Standard“ schon in höherer Version installiert
  ist, lässt der Start das Paket in Ruhe (K6) — Neues kommt dort über die Quelle.
- **Neue Übung:** Block kopieren, neuen `key` vergeben — sie kommt beim nächsten
  Start auf jedes Gerät, ohne Versionswechsel (außer dort ist „Standard“ schon neuer).
- **Korrektur an einer vorhandenen Übung:** wirkt erst, wenn `paket.version`
  steigt — dann je Feld: unveränderte Felder bekommen die Korrektur, selbst
  geänderte bleiben („Auf Paketstand setzen“ holt die Korrektur ganz).
- **`key` nie ändern:** Ein neuer Schlüssel ist eine neue Übung; die alte wird auf
  allen Geräten „nicht mehr im Paket“ und fragt nach „übernehmen oder löschen“.
- **Übung streichen:** Block löschen — sie wird auf allen Geräten „nicht mehr im
  Paket“ (siehe Paketmanager); niemand verliert Verlauf oder Pläne.
- **`neuigkeiten`** im Kopf: ein Satz je Version, was neu ist.
- `tests/test_pakete.py` prüft die Datei: Schlüssel eindeutig und ohne Umlaute,
  Symbol aus `ui/components/icons.py`, Typen und Regionen aus einer festen Liste
  (Tippfehler legten sonst auf jedem Gerät einen neuen Tag an), Original einer
  Variante vorhanden. Ein TOML-Syntaxfehler meldet sich mit Zeile und Spalte.

Warum nicht YAML: braucht eine Zusatzbibliothek auf dem Handy, und YAML deutet
unsere Notation um — `1:30` wird zu `90`, `+20` zu `20`, `no` zu `false`.

Weitere mitgelieferte Pakete (Dehnung, Kräftigung, …) kommen als eigene Datei
daneben, je Paket eine.
