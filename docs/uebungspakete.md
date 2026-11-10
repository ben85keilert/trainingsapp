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
| eine Übung | „Paket „…“, geändert“ hinter der Beschreibung; unten im Abschnitt „Paket“ „Mit dem Paket vergleichen“ (je Feld, Abschnitt und Medium übernehmen, „Ganz auf Paketstand“) |

**Paketstand.** Jede Übung eines Pakets trägt ihre Standardwerte aus dem Paket
(`package_standard_json`, genau die Felder des Dateiformats unten: Name, Beschreibung,
Symbol, Parameter samt Chips, Ziel, Limits, Typen, Regionen, Timer, Uhr, Zählt als,
Beschleunigungssensor, Videos).
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

**Je Abschnitt und je Medium** (U1, Ben 9.11.2026, `docs/plan_paketinhalte.md` §6,
`core/abgleich.py`): Die Beschreibung gleicht die App **je Abschnitt** ab (`## Name`, Schlüssel
der Name ohne Groß/klein), die Medien **je Eintrag** (Schlüssel die Adresse) — ein eigener
Abschnitt oder Link hält keine Korrektur des Pakets mehr fern. Unberührtes bleibt wörtlich. Wo
das Paket eine neue Fassung hat, die eigene aber blieb, merkt die App einen **Hinweis**
(`exercise.package_hints_json`, Migration 045): „· Paket hat Neues“ im Paketmanager, „Das Paket
hat neue Fassungen“ in der Übung. **„Mit dem Paket vergleichen“** (Paketmanager je Übung,
Übungsseite → Paket) zeigt je Feld, Abschnitt und Medium Paket und eigene Fassung mit
**„Paketfassung übernehmen“** (`PaketRepo.paketfassung_uebernehmen`); unten **„Ganz auf
Paketstand“** — der harte Reset (zweiter Tipp bestätigt).

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

## Pakete mit Dateien (ZIP, Formatversion 4 — U3, Ben 9.11.2026)

`docs/plan_paketinhalte.md` §7, Entscheidungen F3/F4. Ein Paket kann Videos, Bilder, Töne und
PDFs mitbringen — an Übungen (`media`), Planübungen (`medien`) und Kurskapiteln (`media`):

- **Datei:** eine ZIP mit `paket.json` (das JSON wie unten, `"version": 4`) und je Datei
  `medien/<sha256>.<endung>` — der Name *ist* die Prüfsumme. Erlaubt: `jpg`/`jpeg`/`png`/`webp`
  (Bild), `mp4`/`m4v`/`mov` (Video), `m4a`/`mp3` (Ton), `pdf`. Ein Medium zeigt mit
  `{ "source": "paket", "uri": "medien/<sha256>.<endung>", "title": "…", "license": "…" }`
  darauf; die Art folgt der Endung. Ohne Dateien bleibt es JSON (Version 1–3) — ältere Apps
  lesen eine ZIP nicht („kein JSON“).
- **Grenzen** (`core/paketmedien.py`): Datei bis 300 MB, ausgepackt bis 400 MB, höchstens 2000
  Einträge, keine verschlüsselten; `paket.json` bis 5 MB. Gelesen wird nur `paket.json` ganz,
  jede Datei geht beim Import mit Prüfsumme in die Ablage (`Paketmedium.kopieren`) — stimmt sie
  nicht, bricht der Import ab, bevor die Datenbank etwas sieht.
- **Ablage** (`data/paketmedien.py`): `Medien/Pakete/<sha256>.<endung>` neben der Datenbank,
  jede Datei einmal (zwei Pakete teilen sie); `aufraeumen` löscht nach jedem Import und beim
  Start, was keine Übung (auch im Papierkorb), kein Plan, Kurs, Paketstand und keine Pläne
  eines Pakets mehr nennen — „Wieder installieren“ findet sie also, solange das Paket bekannt
  ist. Nie in Backup, Export der Messungen oder Sync.
- **Ortsangaben raus** (F4, Grundregel „GPS nie teilen“, `core/bereinigen.py`):
  `trainingsapp-paket bauen` und der Export in der App bereinigen jede Datei — JPEG ohne
  Exif/XMP/IPTC und ohne Anhänge hinter dem Bildende, PNG nur mit Bildblöcken, WebP ohne
  EXIF/XMP, MP4/MOV/M4A mit `udta`/`meta`/`uuid` als `free` (gleiche Größe, Versätze bleiben),
  MP3 ohne ID3; PDF bleibt. **Was sich nicht sicher bereinigen lässt** (andere Formate, ein Video
  mit Metadatenspur), **kommt nicht ins Paket**. Bereinigen ist idempotent: Eine saubere Datei
  behält ihren Namen.
- **In der App:** Import nimmt `.json`, `.toml` (ohne Dateien) und `.zip` (über den Pfad, nie
  ganz über die Leitung); die Rückfrage nennt Zahl und Größe der Dateien. Übungsseite, „i“ der
  Planübung, Material beim Üben und Kurskapitel zeigen sie in einer Zeile
  (`components/medienliste.py`): Video, Bild, Ton öffnen `…/paketmedium/<datei>`
  (`views/paketmedium.py`), ein PDF „Öffnen mit …“ (Teilen-Menü). „Übung bearbeiten“ und „Im Plan
  einstellen“ zeigen sie ohne Adressfeld — nur herausnehmen. Der Export wird eine ZIP, sobald
  eine gewählte Übung oder ein Plan eine Paketdatei nennt.
- **TOML mit Dateien** (Inhalte-Repo): `media = [{ datei = "medien/kniebeuge.mp4", title = "…" }]`
  — Pfad neben der TOML; `trainingsapp-paket pruefen` bereinigt probeweise und meldet Fehler,
  `bauen` schreibt `uebungspaket_<Name>.zip` (reproduzierbar: feste Zeitstempel, feste
  Reihenfolge), `index` nennt sie mit `format_version: 4` und Größe. `TRAININGSAPP_PAKETE` liest
  `.zip` und TOML mit Dateien ebenso.
- **Quellen:** ein Index darf `.zip`-Pakete nennen (Download bis 300 MB, Prüfsumme wie immer);
  die Liste zeigt die Größe, und Pakete über 20 MB spielt die App **nicht von selbst** ein — sie
  bleiben vorgemerkt, bis man sie lädt. *Am Server* (Homepage, Caddy) gehen seit 9.11.2026 `*.json`
  und `*.zip` durch, mit `noindex` (P164/P165, Homepage ADR-0022 Nachtrag) — wirksam, sobald der Stand
  dort eingespielt ist (Runbook `trainingsapp-pakete.md`, Teil G).

## Private Pakete (U7, Ben 9.11.2026, F9)

`docs/plan_paketinhalte.md` §11. „Ich möchte für User Pakete bereithalten, die nur diese Person
betreffen … vor allem gegen Bots und andere absichern.“ Zwei Schlösser:

- **Link** — ein Ordner mit langem Zufallsnamen (22 Zeichen, ~130 Bit, `privat.ordner_neu`):
  `…/pakete/p/<ordner>/paket.json` (mit Dateien `paket.zip`); nicht im öffentlichen Index
  (`trainingsapp-paket index` lässt private Dateien aus), keine Ordnerliste.
- **Code** — 8 Zeichen ohne Verwechsler (`K7QM-9XA2`, Alphabet ohne 0/O/1/I), getrennt vom
  Link weitergeben. Die Datei liegt **verschlüsselt** (`core/privat.py`: scrypt N=2¹⁵ → Schlüssel,
  SHAKE-256 je MiB als Schlüsselstrom, HMAC-SHA256 über alles; Kopf `TAPRIV`): ohne Code
  Zeichensalat, falscher Code oder verfälschte Datei → „Der Code passt nicht“. Der Server prüft
  nichts.
- **Werkzeug:** In der TOML `[privat]` mit `fuer = "Max"`; `trainingsapp-paket bauen
  [--basis-url …]` legt beim ersten Mal Ordner und Code an und merkt sie sich neben der TOML
  (`<name>.zugang.json` — **nur im privaten Inhalte-Repo**), verschlüsselt nach
  `dist/p/<ordner>/paket.json` und gibt die **Zugangskarte** aus (Link + Code — nur am
  Terminal; umgeleitet, etwa in der CI, nennt die Ausgabe bloß die Datei; immer als
  `<name>.zugangskarte.txt`, mit `segno` am Rechner zusätzlich ein QR-Code des Links als SVG).
  Jede neue Fassung: derselbe Link, derselbe Code. `pruefen`, `bauen` und `index` übergehen die
  `.zugang.json` (`pakete/*.json` sammelt sie mit ein); `index` ohne Dateien schreibt einen leeren
  Index. `veroeffentlichen.sh` lädt `dist/p/…` mit hoch.
- **App:** Datei oder Link importieren → „Privates Paket — Code?“ (klein, mit Leerzeichen oder
  Bindestrich geht) → die Rückfrage wie immer. Die App merkt sich Code und „für wen“
  (`package.access_json`, Migration 050) und **entschlüsselt Updates aus dem Link von selbst**.
  Der Paketmanager zeigt „privat · für Max · x.de/pakete/p/7Hq3…/paket.json“ und **„Zugang
  anzeigen“** (Link und Code für ein zweites Gerät). Große private ZIPs entschlüsselt die App
  über `<Daten>/Import/`.
- **Eigene Pakete** (U4) lassen sich ebenso privat teilen: Schalter „Privat — nur mit Code zu
  öffnen“; der Code bleibt für jede Fassung (`own_package.access_code`) und steht nach dem
  Export da.
- **Grenze:** Wer die Datei hat und gezielt Rechenzeit einsetzt, braucht für 8 Zeichen
  (32⁸ ≈ 10¹² Möglichkeiten, je Versuch ein scrypt) Jahre — ein Bot tut das nicht. Darum gilt
  auch hier „keine Personendaten in Paketen“ (Homepage ADR-0022): Übungen für eine Person, aber
  keine Diagnose und kein voller Name — „für“ ist ein Vorname oder Kürzel. Der Server schickt für
  `/pakete/` `X-Robots-Tag: noindex`, damit ein durchgesickerter Link in keiner Suchmaschine
  landet (P165).

## Ergänzungen (U5, Ben 9.11.2026, Formatversion 5)

`docs/plan_paketinhalte.md` §8, F2 („auch Parameter, Ziel, Timer, Takt — hier wird
individualisiert“). Ein Paket ergänzt **Übungen anderer Pakete**, ohne sie zu übernehmen:

```toml
[[ergaenzungen]]
uebung = "kniebeuge"            # Schlüssel — ohne `paket` aus „Standard“; oder eine ID
# paket = "Qigong"              # Name oder ID des Pakets der Übung
description = """
## Reha
Langsam, Knie über dem Fuß."""
default_target = { reps = [8, 8] }
media = [{ uri = "https://…", title = "Reha-Video" }]   # auch datei = "…" (ZIP)
```

- **Was sie darf** (`core/ergaenzungen.py`, `ERGAENZBAR`): `description` — ein benannter
  Abschnitt ersetzt den gleichnamigen, sonst kommt er hinten dazu, einer ohne Namen immer dazu;
  `media` — was die Übung (nach Adresse) nicht hat, kommt dazu; `result_spec`,
  `default_target`, `timer`, `takt` — ersetzen. Alles andere (Name, Typen …) fällt weg
  (`trainingsapp-paket pruefen` gibt einen Hinweis). Eine Ergänzung einer Übung desselben Pakets
  gibt es nicht (dann schreibt man die Übung).
- **Schichten:** Grundpaket → Ergänzungen in der Reihenfolge ihrer Installation (die spätere
  gewinnt je Feld) → Eigenes. Der **wirksame Paketstand** (`package_standard_json`) ist Grund +
  Ergänzungen, der Grund liegt daneben (`package_base_json`, Migration 049); kommt, ändert oder
  geht eine Ergänzung, gleicht die App ab wie bei einem Update — **Eigenes bleibt** (U1),
  „Auf Paketstand“ nimmt die Ergänzungen mit, „Wieder installieren“ den Grund.
- **Gespeichert** je Paket und Übung (`exercise_addon`): Deaktivieren und Entfernen nehmen die
  Ergänzungen heraus, Aktivieren bringt sie zurück; ein Update ersetzt nur die eigenen.
  **Fehlt die Übung** (ihr Paket ist nicht installiert), wartet die Ergänzung und greift, sobald
  es kommt; die Rückfrage beim Import sagt es, der Paketmanager zeigt die Karte **„Ergänzt“**.
- **Anzeige:** Die Übungsseite nennt „ergänzt von „Knie-Reha““ und je Abschnitt klein „aus
  „Knie-Reha““.
- **Eigene Pakete (U4):** Was man an Übungen **anderer** Pakete geändert hat, reist als
  Ergänzung (`core.ergaenzungen.ergaenzung_aus` gegen den wirksamen Paketstand) — eine ganze
  fremde Übung bliebe beim Empfänger, wie sie ist; unveränderte fremde Übungen reisen gar nicht.

## Eigene Pakete (U4, Ben 9.11.2026)

`docs/plan_paketinhalte.md` §7, F5 („Übungen, Pläne und Kurse sollen exportiert werden
können“). Im Paketmanager die Karte **Eigene Pakete** (`views/eigene_pakete.py`, Route
`<basis>/eigen/<id>` bzw. `…/eigen/neu`): Kopf (Name, Beschreibung, „Was ist neu?“) und Inhalt —
Übungen (eigene und aus Paketen), Pläne des Profils, Kurse; was ein Plan oder Kurs braucht,
kommt von selbst mit (`core.eigenes_paket.noetige_uebungen`). Gespeichert in `own_package`
(Migration 048, `data/eigene_pakete.py`) mit **fester, zufälliger ID** — jede neue Fassung ist
bei allen, die das Paket haben, ein Update desselben Pakets; Pläne reisen mit ihrer ID als
Schlüssel, beim Empfänger bleibt es derselbe Plan.

- **Dateien:** „Datei fürs Paket“ in „Übung bearbeiten“ (Karte „Videos, Links und Dateien“) und
  in „Im Plan einstellen“ (Karte „Anweisungen“): Datei wählen (Bild, Video, Ton, PDF), Foto oder
  Video aufnehmen, aus der Fotoauswahl — jede Datei wird **sofort bereinigt** (keine
  Ortsangaben, `Paketablage.aufnehmen`) und als Paketdatei (`source = "paket"`) angehängt;
  der Titel lässt sich ändern. Kamera und Fotoauswahl nehmen das Ziel
  `paketdatei/<Übung>` bzw. `planpaketdatei/<Planübung>` (`core.anhaenge.Ziel`).
- **Exportieren und teilen:** Die App schlägt die Version vor — die erste 1.0.0; ist der
  Inhalt seit der letzten Fassung gleich (`inhalt_sha`, ohne Version, Neuigkeiten,
  Zeitstempel), dieselbe; sonst eine Stufe höher: **klein**, **mittel** oder **groß** (die
  Empfänger sehen die Stufe ohnehin am Unterschied, U6). Geschrieben wird JSON
  oder, mit Dateien, eine ZIP (`core.paketdatei.export_schreiben`, Dateien im Hintergrund, die
  Datenbank im Event-Loop), weitergegeben über das Teilen-Menü; gemerkt werden Version und
  Prüfsumme der Fassung.
- **Löschen** nimmt nur die Zusammenstellung weg — Übungen, Pläne, Kurse bleiben, und wer das
  Paket hat, behält es.

## Dateiformat

JSON, UTF-8. Version 1 (Übungen); **Version 2** fügt `kurse[]` hinzu, **Version 3**
`plaene[]` (Ben, 28.10.2026), **Version 4** Dateien (nur in einer ZIP, Abschnitt oben) — eine
Datei ohne Kurse und Pläne wird weiter als Version 1 geschrieben, ohne Pläne als Version 2;
ältere Apps lesen sie:

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
      "spec": "halten"
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
| `paket.version` | nein | vom Autor gepflegt: **„X.Y.Z“** (Y und Z unter 100) oder eine ganze Zahl wie bisher. Gespeichert und in Paketdatei und Index geschrieben wird immer die Zahl X·10000 + Y·100 + Z — ältere Apps vergleichen so weiter richtig; eine bisherige Version 4 ist 0.0.4. Angezeigt wird „X.Y.Z“ (Ben, 9.11.2026, `core/paketversion.py`). Text nur in der vollen Form („3“ wäre sonst 3.0.0, die Zahl 3 aber 0.0.3) |
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
| `timer[]` | nein | Timer-Profile der Übung (Ben, 17.10.2026; `docs/plan_einheit.md`, Stufe 3): je Profil `name`, `abschnitte[]` (`name`, `dauer_s`, `klang`, `zaehlt` — fehlt `zaehlt`, zählt der Abschnitt; seit 8.11.2026 wahlweise `ausfuehrung` = Tabelle Feld → Wert, etwa `{ variant = "links", weight = 10 }` — die Ausführung dieser Runde, eingetragen je Ausführung, nur `variant`, `weight`, `angle`, `side`; ältere Apps übergehen sie, `docs/plan_uhr_fokus.md` §3), `runden`, für eine Folge `teil_name` und `teile[]` (`name`, `runden`, `abschnitte[]`). `id` schreibt der Export; ohne sie eine feste aus Übung und Stelle. Fehlt `timer`, gilt eine Timer-Regel im `limit_spec` als Einzeltimer. Im Drei-Wege-Abgleich ein Feld |
| `uhr` | nein | Stoppuhr und Timer stehen in der Übung bereit (Ben, 18.10.2026; `docs/plan_stoppuhr.md`); fehlt = an, `false` = aus. Im Drei-Wege-Abgleich ein Feld |
| `zaehlt_als` | nein | „Zählt als“, wenn die Übung Haltezeit anbietet: `hold` (Haltezeit, ein Satz je Lauf) oder `duration` (Zeit); fehlt = Haltezeit. Ohne Haltezeit zählt die Uhr immer als Zeit. Im Drei-Wege-Abgleich ein Feld |
| `beschleunigung` | nein | Die Karte „Beschleunigungssensor“ (Ben, 4.11.2026; `docs/plan_beschleunigung.md` §3): eine Tabelle, etwa `beschleunigung = { wiederholungen = true, atmung = true }`, mit `wiederholungen` (Wahrheitswert; fehlt = an, wenn die Übung ein Feld der Art `reps` hat — ohne eins nie), `atmung` (Wahrheitswert; fehlt = an bei Typ „Atmung“), `vorlage` (Bewegung; fehlt = `auto`, „Automatisch“ — ein Schlüssel, den hrv-core nicht kennt, zählt wie `auto`) und `feld` („Zählt in“ bei mehreren Wiederholungsfeldern, etwa `reps_2`; fehlt = das erste). Fehlt das Feld, gilt überall die Vorgabe; der Export schreibt nur, was davon abweicht. Unbrauchbare Werte gelten als Vorgabe, das Paket bleibt lesbar — `trainingsapp-paket pruefen` meldet einen falschen Typ als Fehler, einen unbekannten Schlüssel als Hinweis; ältere Apps übergehen das Feld (keine neue Formatversion). In der App `exercise.acc_json` (Migration 037). Im Drei-Wege-Abgleich ein Feld — seit A6 (5.11.2026) auch **je Planübung** in `plaene[].uebungen[]` (fehlt = wie die Übung) |
| `bedingung` | — | **Nur je Planübung** (`plaene[].uebungen[]`, siehe unten) — an der Übung seit 8.11.2026 nicht mehr (Ben: „in Einzelübungen macht das keinen Sinn“); ein `bedingung` an der Übung übergeht die App |
| `takt` | nein | Der **Takt** der Übung (Ben, 5.11.2026; `docs/plan_taktgeber.md` §2): eine Tabelle `takt = { name = "4-7-8", phasen = [{ name = "ein", dauer_s = 4, art = "ein" }, { name = "halten", dauer_s = 7, art = "halten" }, { name = "aus", dauer_s = 8, art = "aus" }], tempo = 1.0 }` — je Phase `name`, `dauer_s` (Sekunden, auch Zehntel, 0,1–600), `art` (`ein`, `aus`, `halten`, `ab`, `auf`, `frei`; fehlt = `frei`), `klang` (Schlüssel wie beim Timer; fehlt = Vorgabe je Art); am Takt `name`, `tempo` (Faktor 0,5–2, fehlt = 1), `runden` (Zahl; fehlt = endlos), `animation` (`puls`, `kreis`, `kreis_halten`, `box`, `balken`, `welle`; fehlt = nach Phasenzahl), `zaehlt` (Wahrheitswert, „Takt zählt“ — jede volle Runde eine Wiederholung, Zähl-Teil mit Quelle `takt`, seit Teil 2; fehlt = false, die Vorlagen Kniebeuge und Liegestütz haben es an), je Phase wahlweise `bild` (Pfad in der App-Ablage — nur vorbereitet, reist nicht sinnvoll im Paket). Fehlt das Feld oder ist keine Phase brauchbar, hat die Übung keinen Takt; unbrauchbare Phasen fallen weg, Unbekanntes gilt als Vorgabe, das Paket bleibt lesbar — `trainingsapp-paket pruefen` meldet einen falschen Typ als Fehler, einen unbekannten Schlüssel, eine unbekannte Art oder einen unbekannten Klang als Hinweis; ältere Apps übergehen das Feld (keine neue Formatversion). In der App `exercise.takt_json` (Migration 038). Im Drei-Wege-Abgleich ein Feld. Ein Takt je Timer-Abschnitt steht in `timer[].abschnitte[].takt` (gleiches Format) und geht der Übung vor — seit A6 (5.11.2026) auch **je Planübung** in `plaene[].uebungen[]` (fehlt = wie die Übung) |
| `default_felder` | — | **überlesen** seit 22.10.2026 (P79, C2): Was die Übung hat, bieten alle Pläne an; weniger stellt man in der Planübung ein. Der Export schreibt es nicht mehr |
| `media[]` | nein | `{kind, source, uri, title, license}`; leere `uri` und `source: "local"` fallen weg. `uri` nur `https://…` oder `mailto:…` — andere Schemata (`http://`, `intent://`, `tel:`, `file://`) verwirft der Import still, die Übung bleibt; die App öffnet außerdem vor jedem Tipp nur solche Adressen (`core/links.py`, auch für Links im Kapiteltext). Seit U3 auch **Dateien aus dem Paket**: `source = "paket"`, `uri = "medien/<sha256>.<endung>"` (Abschnitt „Pakete mit Dateien“) |
| `variante_von` | — | **überlesen** seit 26.10.2026: „Im Verlauf zusammen mit“ (Kopie teilt die Kachel des Originals) ist ausgebaut; der Export schreibt es nicht mehr, `trainingsapp-paket pruefen` prüft es nicht mehr |

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
(Markdown; Bilder `![…](https://…)` darin lädt die App erst, wenn die Person es unter Einstellungen → Updates einschaltet — bis dahin stehen sie als Link „[Bild: …]“, `core/kapiteltext.py`, Sicherheitsdurchsicht S2), `media[]` (wie bei Übungen, zusätzlich `kind: "audio"`), `plaene[]`
(`{name, wochentage: [0..6], uebungen: [{uebung: <key|id>, ziel?, felder?, beschleunigung?,
takt?, bedingung?}]}` — `beschleunigung` und `takt` je Planübung wie an der Übung, A6 5.11.2026: fehlt =
wie die Übung, `takt = {}` = ausdrücklich keiner; was keine Tabelle ist, gilt als „wie die
Übung“ — ebenso ein `takt` ohne brauchbare Phase (Prüfrunde A6: nie „keiner“, sonst schaltete
ein Tippfehler den Takt der Übung ab); eine Tabelle `beschleunigung` ist immer eine eigene
Karte, Unbrauchbares darin die Vorgabe wie an der Übung; `trainingsapp-paket pruefen` meldet
beides auch hier, mit Plan und Übung als Ort. Ältere Apps übergehen beide, der Export schreibt
sie nur, wo die Planübung eigene hat) und
`bedingung` (`{art: "gelesen"}` Vorgabe · `{art: "summe", uebung, feld, soll}` ·
`{art: "tage", soll}` · `{art: "messung", soll}` in Minuten). `uebung` ist der
Schlüssel einer Übung desselben Pakets oder eine ID.

Import: Kurse folgen den Regeln der Übungen (neu → anlegen; gleiches Paket →
Stand der Datei, Kapitel gleicher ID behalten den Fortschritt; eigene/fremde →
bleiben). Entfernen nimmt die Kurse aus der Liste, „Wieder installieren“ holt sie
aus dem Paketstand (`course.package_standard_json`) zurück.

Je Plan (`plaene[]`, Formatversion 3, `docs/plan_import_links_plaene.md` §3): `name`
(Pflicht), `key` (nie ändern — die Plan-ID folgt daraus, je Profil: UUIDv5 aus Paket,
`plan:<key>` und Profil), `beschreibung`, `wochentage`, `uebungen[]` wie in der
Kapitel-Vorlage (seit 8.11.2026 auch **`bedingung` je Planübung**, `docs/plan_workout.md` §1:
`{ art = "wdh" | "wdh_in_zeit" | "zeit" | "gemacht" | "skala", n, sekunden, hart, inhalt = { text, url },
zweig = "A"…"D", dann, sonst, wege = [{ ziel, text }] }` — `dann`, `sonst` und `wege[].ziel` als
**Position** `"#n"` der Planübung im Plan (auch die eigene: Schleife), der Import übersetzt sie
in IDs; `skala` ist eine Selbsteinschätzung ab `n`; P97), dazu `timer` (Plan-Timer),
`weiter_automatisch` (seit Migration 043 = Übergang **hart**), `pause_ohne_timer`.

**Gezeichneter Ablauf** (8.11.2026 spät, `docs/plan_verzweigungen.md` §8, G4): je Plan — auch
in Kurskapiteln — wahlweise `ablauf = { an = true, start = "#1", kanten = [{ von, nach, ausloeser
= "frei" | "zeit" | "wdh" | "wdh_in_zeit" | "skala", n, sekunden, bis, pflicht, ausfuehren,
wiederholen, text, inhalt = { text, url } }], fragen = [{ id = "?1", text, min, max }] }`
(`sekunden` nur bei `wdh_in_zeit`, seit 8.11.2026 abends). Knoten sind **Positionen**:
Planübungen `"#n"`, Fragen (Entscheidungsknoten) `"?n"`, dazu `"__ende__"` (Ende des Workouts)
und `"__zurueck__"` (dorthin, wo man herkam — Einschub; `wiederholen` = die unterbrochene noch
einmal). Der Import übersetzt in IDs (eine fehlende Übung nimmt ihre Kanten mit), der Export
schreibt den Ablauf nur, wenn der Plan einen hat; ohne `an` läuft der Plan als Kette mit den
`bedingung`-Feldern. Eine ältere Fassung mit `zweig`, `dann`, `sonst` oder `wege` an der
Planübung liest die App als diesen Ablauf (P108, `PlanVorlage.zweige_als_ablauf`; die Prüfung
gibt einen Hinweis). `trainingsapp-paket pruefen` meldet eine Kante ohne Position als Fehler,
einen unbekannten Auslöser als Hinweis; ältere Apps übergehen das Feld. Je Planübung dazu
`beiname` (Text, unterscheidet zwei gleiche Übungen im Bild: „2. Durchgang“).

**Anweisungen je Planübung** (U2, Ben 9.11.2026, `docs/plan_paketinhalte.md` §9, F6) — in
`plaene[].uebungen[]` und in Kurskapiteln: `beschreibung` (ein Text mit `## Name`-Zeilen wie die
Beschreibung der Übung, `core/beschreibung.py`) und `medien` (eine Liste wie `media` der Übung:
`{ uri, title, kind, source, license }`). Was die App nicht öffnen darf (nur `https://` und
`mailto:`), Dateien vom Gerät und Töne fallen beim Import still weg; `trainingsapp-paket
pruefen` gibt dazu einen Hinweis. Die Anweisungen gelten nur in diesem Plan — die Beschreibung
der Übung bleibt im „i“; beim Üben zeigt der Knopf **Material** (Buch-Symbol neben dem „i“ und
im Fokus), dass es welche gibt (`core/material.py`, `components/material.py`). In der App
`plan_item.description`/`media_json` (Migration 046), bearbeitet in „Im Plan einstellen“, Karte
„Anweisungen“. Ältere Apps übergehen beide Felder (keine neue Formatversion).

Import: Ein Paketplan wird **im aktiven Profil** angelegt; andere Profile bekommen ihn beim
nächsten Start (`PaketRepo.plaene_nachlegen`). Ein neuer Stand geht **je Feld und je
Planübung** (U2, 9.11.2026, `core.pakete.plan_abgleichen`): Was die Person nicht angefasst hat
(Vergleich mit `plan.package_standard_json`), bekommt das Update; neue Planübungen kommen dazu;
was sie geändert oder **herausgenommen** hat, bleibt so. Eine Planübung wird über ihre Übung und
ihr wievieltes Vorkommen erkannt (`baum#2`) und behält ihre ID (Einträge und Wege zeigen
darauf). Hat der Plan einen gezeichneten Ablauf oder Zweige und verschöben sich die
Planübungen, bleibt die eigene Fassung ganz — sonst zeigten die Wege auf andere Übungen. Im
Papierkorb bleibt ein Plan dort.

**Plan neu laden** (U2, F7): Im Plan-Editor steht unter dem Namen, woher ein Plan kommt
(„Aus Paket „Qigong““, „Aus Kurs „…“ · Kapitel“), mit **„Neu laden …“** — ein Blatt mit
**„Fehlendes zurückholen“** (Herausgenommenes kommt wieder, eigene Änderungen bleiben) und
**„Auf Paketstand setzen“** bzw. **„Wie im Kapitel“** (alles wie in der Quelle, zweiter Tipp).
Geht nur, solange das Paket installiert und aktiv ist bzw. den Kurs gibt; ein Plan im Papierkorb
kommt dabei zurück, Einträge bleiben (`PaketRepo.plan_neu_laden`,
`KursRepo.kapitelplan_neu_laden`). Der Paketmanager zeigt je Paket die Karte **„Pläne“** mit
Zustand (wie im Paket · von dir geändert · im Papierkorb · gelöscht); ein gelöschter Plan lässt
sich dort **„Wieder anlegen“** (`PaketRepo.plan_wieder_anlegen`, auch hinter dem Grabstein).
Die Kursseite hat im Menü **„Kurs neu laden …“** (`KursRepo.kurs_neu_laden`): die Pläne aller
erreichten Kapitel — vorhandene wie oben, gelöschte entstehen neu (aktiv nur im laufenden
Kapitel); der Fortschritt bleibt. Mit gezeichnetem Ablauf holt „Fehlendes zurückholen“ nichts
zurück, wenn sich dafür Positionen verschieben müssten — dann hilft nur der harte Weg. Entfernen des Pakets legt seine Pläne in den Papierkorb, Deaktivieren
versteckt sie wie die Übungen. Nicht mehr im Paket → bleibt (ein Plan ist etwas Eigenes,
sobald er geübt wird). Export: die Gruppe „Pläne“ im Exportdialog — ein Plan nimmt seine
Übungen mit. **Platzhalter** (`$auswahl`, `$test.duration` — Kurs stellt den Plan aus
einer Auswahl zusammen, P90, nicht gebaut) überliest diese App, statt die Datei abzulehnen.

**IDs von „Standard“:** Sie bleiben, wie sie vor den Paketen waren —
UUIDv5 nur aus dem Schlüssel (`seed_id`); die Paket-ID stammt aus dem früheren
Namen „Grundausstattung“ (Konstante `GRUNDAUSSTATTUNG`). Für alle anderen Pakete
gehört die Paket-ID in die Ableitung, damit zwei Pakete denselben Schlüssel
verwenden dürfen.

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
uv run --project ../trainingsapp trainingsapp-paket uebernehmen .daten/trainingsapp.db \
  pakete/standard.toml [--probe]          # oder ein Export: ~/Downloads/uebungspaket_Standard.json
```

`pruefen` wendet die Regeln des Standardpakets an (Schlüssel, Beschreibung, Variante,
Symbol — Symbole nur mit flet); Typen und Regionen außerhalb des Standardpakets sind
Hinweise. In `beschleunigung` ist ein falscher Typ ein Fehler (die App läse ihn still als
Vorgabe), ein unbekannter Schlüssel ein Hinweis — an Übungen wie an Planübungen
(`plaene[].uebungen[]`, auch in Kurskapiteln; seit Prüfrunde A6). `--wortliste DATEI` sucht Begriffe, die in Pakettexten nichts verloren haben
(Sprachregelung der Praxis-Website: erklären, nicht bewerten — die Liste liegt im privaten
Repo der Homepage, `docs/wortliste-zone3.txt`); Treffer sind Hinweise, mit `--streng`
Fehler. `index` schreibt den Index einer Paketquelle (ID, Name, Version, URL, SHA-256,
Größe, Neuigkeiten, reserviertes Feld `signatur`) — das Format, das die App für Updates
liest. `quelle URL` liest einen veröffentlichten Index wie die App und prüft jede
Paketdatei samt Prüfsumme. Wie die Dateien auf den Server kommen: Homepage,
`docs/runbooks/trainingsapp-pakete.md` (rsync mit beschränktem Schlüssel).

**Aus der App zurück ins TOML** (Ben, 27.10.2026): Chips, Ziele, Timer und Varianten
stellt man leichter in der App ein als in der Datei. `uebernehmen` liest die Quelle und
trägt je Übung die Felder, die vom Stand der Datei abweichen, in ihren
`[[exercises]]`-Block ein. Quelle ist die **Datenbank der App** (`.db`, nur lesend —
im Inhalte-Repo `.daten/trainingsapp.db` nach `./start.sh`): Übungen des Pakets und die
Pläne, die Kurskapitel angelegt haben; oder ein **Export** aus dem Paketmanager (JSON,
nur Übungen — die App schreibt kein TOML, `tomllib` liest nur). Zugeordnet wird über die
ID, die der Leser aus `key` rechnet; `key`, Kommentare, Abschnitte, Reihenfolge und Kurse
bleiben (`tomlkit`, nur in der Gruppe `dev`). Parameter, die einer Vorlage entsprechen,
werden wieder `spec = "…"`, andere ein vollständiges `result_spec`. Die Ausgabe nennt je
Übung die Felder; `git diff` zeigt den Stand. Regeln:

- Gleiches Paket, andere Version → nichts: Die App hat den Stand der Datei nie gesehen,
  die Quelle brächte Altes zurück. Erst `version` heben, App starten, dann übernehmen.
- Übungen der Quelle ohne Block (eigene, aus anderen Paketen) werden nur genannt; Übungen
  der Datei, die nicht in der Quelle sind, bleiben unverändert — ein Export darf eine
  Auswahl sein.
- Typen und Regionen gelten als Mengen (die App führt sie in anderer Reihenfolge).
- **Pläne** (nur aus der Datenbank): Ein Plan mit `kurs_kapitel_id` gehört zur Vorlage
  gleichen Namens in seinem Kapitel (`plaene[]`); Wochentage und Übungen (mit `key`,
  Ziel und Felder nur, wo der Plan eigene hat) ersetzen die der Vorlage. Ein Plan ohne
  Vorlage dieses Namens wird genannt, nicht angelegt; eigene Pläne ohne Kapitel haben im
  Paketformat keinen Platz. Timer, „automatisch weiter“ und Chips je Planübung kennt
  die Vorlage nicht — sie bleiben in der App (Erweiterung des Formats: offen).
- `--probe` zeigt nur. Nach dem Schreiben läuft `pruefen` über die Datei.

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
- **Stufe aus dem Unterschied** (U6, Ben 9.11.2026, F8 c, `core/paketstufe.py`): Die App lädt
  ein Update (nicht bei „Manuell“, nicht über 20 MB) und vergleicht es mit dem gespeicherten
  Paketstand — **groß**: etwas fällt weg (Übung, Kurs, Kapitel, Plan, Ergänzung), ein Kapitel
  wandert oder wird dazwischengeschoben, eine Kapitelbedingung oder Freischaltung ändert sich;
  **mittel**: etwas kommt dazu, Texte, Medien, Felder der Eingabe, Pläne; **klein**: nur
  Vorgaben (Chips, Ziel, Timer, Symbol, Typen, Regionen, Takt, Plan-Vorlagen). Die Nummer
  entscheidet nichts — das Werkzeug hält sie ehrlich (`trainingsapp-paket pruefen --gegen
  <Datei|Link|Index>`: „Wandsitz fällt weg → mindestens 2.0.0, steht 1.4.1“).
- **Modus je Paket:** **Alle** (`auto`, Vorgabe) spielt kleine und mittlere Updates beim Start
  ein und merkt große vor, **Kleine** (`klein`) nur kleine, **Manuell** merkt alles nur vor
  (`package.available_*`) — der Pfeil holt Vorgemerktes mit der Vorschau des Datei-Imports; die
  Liste nennt die Stufe, der Pfeil ihre Gründe, die Vorschau beides.
  Unter Updates setzt **„Für alle Pakete“** (Alle · Kleine · Manuell) jedes installierte Paket
  und die Vorgabe für neu installierte (Einstellung `paket_update_modus`); je Paket lässt es
  sich dort und im Paketmanager anders wählen, ein Update lässt den Modus stehen. Was man an
  Übungen geändert hat, bleibt (Drei-Wege-Abgleich); Entfallenes fragt nach wie immer.
- **Sicherheit:** HTTPS sichert die Herkunft, die Prüfsumme den Download (stimmt sie
  nicht, wird nichts geschrieben), die Datei muss zur ID im Index passen, maximal
  5 MB. Eine Signatur kommt, wenn Pakete von Dritten kommen.
- **Links importieren** (Ben, 28.10.2026, `docs/plan_import_links_plaene.md` §1):
  Paketmanager → „Importieren“ → Link (oder die Adresse unter Updates → Quellen). Liegt
  dort ein **Index**, fragt die App „Als Quelle eintragen?“ und nennt den Ort
  (Einstellungen → Updates → Quellen); liegt dort eine **Paketdatei**, kommt die bekannte
  Rückfrage, und die Adresse bleibt am Paket (`package.source_url`, `source_kind =
  'datei'`) — beim Start lädt die App die Datei und prüft die Version wie bei einem Index
  (`paketquelle.datei_eintrag`). Wo ein Paket herkommt, steht in Liste und Paketseite
  („Quelle: …“, „Quelle (Paketdatei): …“, „aus Datei importiert“, „mitgeliefert“).
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
