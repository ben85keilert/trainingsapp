# Planung: Einstellungen → „Medien“ — alles, was auf dem Gerät liegt (20.11.2026)

Ben, 20.11.2026: „In den Einstellungen → Anhänge sind die Medien der Tagesnotizen gelistet. Dort
fehlen aber die Medien aus Übungen/Pläne/Kurse usw. Benenne Anhänge in Medien um (Audio, Video,
PDFs, usw.) (Unnützes weglassen) und nimm die Medien aus der App dort mit auf. Gedownloadete
Videos sollen sich löschen lassen, bei Bedarf kann man wieder downloaden. Eigene Videos
(Tagesnotizen und Co.) löschen mit Rückfrage.“

**Stand: Plan, nichts gebaut.** Fragen an Ben in §5 (Katalog P230). **Nachgezogen am
27.11.2026** auf den Stand nach Version 0.3.103 und dem Umbau des Kapitel-Editors
(`plan_kurs_uebungen.md` §14.6, §15) — §1.1; die Fragen in §5 sind weiter offen.

Gesucht im Katalog: `medien`, `speicher`, `herunterlad`, `download`, „anhänge verwalten“.
Gelesen: P225, P227 (Entscheidungszeilen), `plan_medien_reiter.md` §1, `plan_medien_einheitlich.md`
§1.1. Nur gefunden: P159, P160, P180, P200, P209, P226, `plan_anhaenge.md` Teil E.
Code gelesen: `ui/views/einstellungen_anhaenge.py` (ganz), `data/paketmedien.py`,
`config.py` (Verzeichnisse), Signaturen von `data/anhaenge.py`, `data/uebungsbilder.py`,
`core/medien_uebersicht.py`.

## 1. Befund

Die Seite `/einstellungen/anhaenge` zeigt heute:

| Karte | Inhalt | Quelle |
|---|---|---|
| Aufnahmen | Qualität, längste Videoaufnahme | `app_setting` |
| Überblick | **nur `entry_media`** — Aufnahmen an Einträgen und Notizen zum Tag, nach Monaten, Mehrfachauswahl, Löschen mit Rückfrage | `data/anhaenge.py` |
| Geladene Videos | Videos hinter Links, Löschen ohne Rückfrage | `Paketablage.links()` |
| Aufräumen | verwaiste und fehlende Dateien der Anhänge | `core.anhaenge` |
| Wo liegen die Aufnahmen? | Erklärtext | — |

Auf dem Gerät liegen aber vier Ablagen:

| Ablage | Ordner | Was | Auf der Seite |
|---|---|---|---|
| Anhänge | `Anhaenge/<JJJJ>/<MM>/` | Foto, Video, Audio, PDF an Eintrag und Tagesnotiz | ja |
| Paketablage | `Medien/Pakete/<sha256>.<endung>` | Dateien an Übung, Planübung, Plan, Weg im Ablauf, Kurs — **aus Paketen und selbst hinzugefügte**, dazu Originale verkleinerter Dateien | **nein** |
| — darin | `link_download` | Videos hinter Links | ja (eigene Karte) |
| Symbole, Bilder der Bewegung | `Medien/Symbole/`, Ablage der Bewegungsbilder | eigene Bilder an Übungen | **nein** |

Was für das Löschen zählt:

- **Die Paketablage kennt keine Herkunft.** Ob eine Datei aus einem Paket kam oder selbst
  hinzugefügt wurde (`Paketablage.aufnehmen`), steht nirgends. Ableiten lässt es sich: Nennt ein
  Paketstand die Datei (`exercise/plan/course.package_standard_json`, `package.plans_json`), kam
  sie mit einem Paket; sonst ist sie eigen. Keine Migration nötig.
- **Eine Paketdatei löschen lässt den Verweis stehen** — die Stelle zeigt „Datei fehlt — das
  Paket neu importieren“ (`components/medienliste.py:163`). Zurück kommt sie mit „Wieder
  installieren“ nur, wenn die ZIP-Datei oder die Quelle sie liefert (`data/pakete.py:283`: „sie
  kommen mit der ZIP-Datei des Pakets“). **Ungeprüft:** ob eine Paketquelle fehlende Dateien von
  selbst nachlädt.
- **`Paketablage.aufraeumen` löscht nur, was nichts mehr nennt.** Wer eine genannte eigene Datei
  löschen will, muss das Stück an jeder Stelle herausnehmen — das kann die Ablage heute nicht
  (`ersetzen` tauscht Namen in allen Spalten, herausnehmen gibt es nicht).
- „Einstellungen → Anhänge“ steht als Text in acht Quelldateien (`anhang.py`, `verkleinern.py`,
  `anhang_aufnahme.py` …), die Route in `ui/app.py`, Tests in `test_ui_anhaenge.py`,
  `test_linkvideos.py`.

### 1.1 Was sich seit dem 20.11. geändert hat (27.11.2026)

Am Code nachgesehen: `data/paketmedien.py` (`_ABFRAGEN`), `ui/paketdatei.py`,
`ui/views/kurs_bearbeiten.py` (`block_editor`, `block_aufnehmen`, `block_mit_stueck`).

- **Kurse nehmen eigene Aufnahmen an zwei Stellen:** am Block „Medium“ (seit 23.11.) und als
  **Medien am Lauf** eines Blocks „Übung machen“ (seit 26.11., `Block.medien`) — Kamera,
  Rekorder, Fotoauswahl, Datei. Beides steht in `course_chapter.blocks_json`, das die Ablage
  schon liest; für „wo genannt“ muss `nennungen()` darin **zwei Orte** unterscheiden
  („Kurs Rumpf · Kapitel 2 · Medium“ und „… · Übung machen: Seitstütz“).
- **Eigene Kurse haben keinen Paketstand** — ihre Dateien gelten nach §2.3 als „selbst
  hinzugefügt“. Das Herausnehmen an allen Stellen (M3) braucht darum auch den Kursblock
  „Medium“ (der Block fällt dann ganz weg — er hat ohne Stück keinen Inhalt; die Rückfrage
  nennt das) und die Liste `medien` am Lauf (nur das Stück fällt weg).
- **Ein neues Stück ist bis zum Speichern des Kapitels nur vorgemerkt**
  (`Paketablage.entwurf_merken`, gilt bis zum Ende des Laufs der App). Die Seite „Medien“
  zeigt es dann unter „Aufräumen“ als „nichts nennt es“ — der Abschnitt lässt Dateien dieses
  Laufs darum aus (dieselbe Menge, die `aufraeumen` behält).
- **Bearbeitet wird im Kapitel an Ort und Stelle** (§15 dort): „wo genannt“ führt bei einem
  eigenen Kurs zu `/kurse/<id>/<kapitel>/bearbeiten`; den Block dort gleich zu öffnen ist ein
  eigener Schritt (heute öffnet die Seite nur einen wartenden Entwurf).
- **Private Pakete und Pakete per Link im Browser** (23.11.) ändern an der Ablage nichts; im
  Browser liegt sie im Browserspeicher — die Seite „Medien“ gilt dort genauso, „Geladene
  Videos“ gibt es dort nicht (**ungeprüft**, vor M1 im Web-Profil `config.WEB` nachsehen).

## 2. Vorschlag

### 2.1 Name und Route

- Zeile in den Einstellungen: **„Medien“** (Symbol `PERM_MEDIA`), Unterzeile „<Größe gesamt> ·
  Qualität, Aufräumen“ — die Größe zählt alle Ablagen.
- Route `/einstellungen/medien`, Datei `views/einstellungen_medien.py`; die alte Route leitet
  um (gemerkte Scroll-Stände, Verweise in älteren Texten). Alle sichtbaren „Einstellungen →
  Anhänge“ werden „Einstellungen → Medien“.
- **„Anhang“ bleibt das Wort für die Aufnahme an Eintrag und Notiz** (Ansicht `/anhang/<id>`,
  Tabelle, `core/anhaenge.py`, `docs/plan_anhaenge.md`) — umbenannt wird nur die Seite.

### 2.2 Aufbau der Seite

Oben eine Zeile **Gesamtgröße** und **Chips nach Art**: Alle · Fotos · Videos · Audio · PDFs (nur
Arten, die es gibt). Der Chip filtert alle Abschnitte darunter.

| Abschnitt | Inhalt | Löschen |
|---|---|---|
| **Eigene Aufnahmen** | wie heute der Überblick: Anhänge nach Monaten, Kacheln, Mehrfachauswahl, „Videos älter als 3 Monate …“ | **mit Rückfrage**, endgültig (wie heute) |
| **In Übungen, Plänen und Kursen** | Dateien der Paketablage, größte zuerst; je Zeile Titel, Art, Größe und **wo genannt** („Übung Kniebeuge · Plan Rücken“), Tipp öffnet die Datei (`paketmedium`) | je nach Herkunft, §2.3 |
| **Geladene Videos** | wie heute | **ohne Rückfrage** (wie heute), dazu „Alle löschen“ |
| **Aufnahme-Einstellungen** | Qualität, längste Videoaufnahme — zugeklappt ans Ende | — |
| **Aufräumen** | nur sichtbar, wenn es etwas gibt: verwaiste und fehlende Anhänge, dazu Paketdateien, die nichts mehr nennt | wie heute |

**Weg fällt:** die Karte „Wo liegen die Aufnahmen?“ (ein Satz wandert ins (i) am Kopf,
`components/hilfe.py`), der Bedienhinweis im Überblick (ebenfalls ins (i)), der Satz „Nichts
aufzuräumen“ und der Hinweis unter den geladenen Videos (steht dann im (i)).

### 2.3 Löschen in „In Übungen, Plänen und Kursen“

| Herkunft | Erkennung | Löschen |
|---|---|---|
| **aus einem Paket** | ein Paketstand nennt die Datei | Datei weg, Verweis bleibt („Datei fehlt — das Paket neu importieren“). **Rückfrage** mit dem Satz, womit sie wiederkommt — außer das Paket hängt an einer Quelle, die sie wieder liefert (erst nach Prüfung, §1) |
| **selbst hinzugefügt** | kein Paketstand nennt sie | **Rückfrage** „An 2 Stellen: Übung Kniebeuge, Plan Rücken — endgültig“; danach wird das Stück an allen Stellen herausgenommen und die Datei gelöscht |
| **Original einer verkleinerten Datei** | Vermerk `medien_originale` | erscheint als Unterzeile „Original, 48 MB“ mit „Original löschen“ (`original_vergessen`, wie in „Verkleinern“) |

Das Herausnehmen an allen Stellen schreibt in Übung, Planübung, Plan, Ablauf und Kurs. Es läuft
über die Repositories dieser Dinge (nicht über rohes JSON-Ersetzen), damit „was die Person
geändert hat, bleibt“ und der Drei-Wege-Abgleich der Pakete den Unterschied als Änderung der
Person sieht.

### 2.4 Schichten

- `core/medien_speicher.py` (neu, ohne flet): `Stueck` (Name, Art, Bytes, Herkunft, Stellen),
  Ordnen, Filtern nach Art, Summen, Texte der Rückfragen — mit Doctests.
- `data/paketmedien.py`: `nennungen()` (Datei → Stellen mit Art, ID, Name; gleiche Spalten wie
  `_ABFRAGEN`), `aus_paket(name)`, `datei_loeschen(name)`; nur SQL mit Platzhaltern.
- `ui/views/einstellungen_medien.py`: zeichnet; die Liste der Paketdateien baut sich erst beim
  Aufklappen (viele Dateien, `stat` je Datei).
- Videos laufen weiter nur in `/anhang/<id>` und `…/paketmedium/…`; die Seite zeigt Frontbilder
  und Zeilen. (Seit 27.11.2026 spielt ein Video im **Kurs** auch in seiner
  Medienkarte, `plan_kurs_medien_ansicht.md` §10.1 — für diese Seite ändert das nichts; sie
  kann für Paketdateien dieselbe Miniatur zeigen, `medienkarte.miniatur`.)

## 3. Stufen

| Stufe | Inhalt | Tests |
|---|---|---|
| **M1** | Umbenennen: Zeile, Titel, Route mit Umleitung, alle Verweistexte; Unnützes weg; Chips nach Art über die Anhänge; Gesamtgröße über alle Ablagen | `test_ui_anhaenge.py` → `test_ui_medien_einstellungen.py`, Route alt → neu |
| **M2** | Abschnitt „In Übungen, Plänen und Kursen“ **zum Ansehen**: Liste, Herkunft, „wo genannt“, Öffnen; „Alle löschen“ bei geladenen Videos; Paketdateien ohne Nennung unter Aufräumen | `test_paketmedien.py` (`nennungen`, `aus_paket`), `core`-Doctests |
| **M3** | Löschen nach §2.3: Paketdatei (Datei weg), eigene Datei (überall herausnehmen), Original | je Stelle ein Test: Übung, Planübung, Plan, Weg, Kursblock „Medium“, Medium am Lauf; Papierkorb-Übung; Paketstand bleibt unberührt |
| **M4** | Web-Foto der Seite in Handybreite (Skill `web-fotos`), Gerätetest in `docs/offene_fragen.md` Abschnitt 2 | — |

Keine Migration, kein neues Paketformat, keine neue Netzverbindung.

## 4. Regeln, die gelten

- Anhänge und Paketdateien gehen nie in Export, Backup oder Sync — die Seite ändert daran nichts.
- Löschen von Anhängen bleibt endgültig, ohne Papierkorb (`plan_anhaenge.md` G3).
- Nichts ändert sich an einem Plan ohne Tipp; die Rückfrage nennt die Stellen, bevor sie
  herausnimmt.
- Im Browser (Web-Fassung) gibt es keine Kamera — braucht die Seite dort eine Abzweigung,
  kommt sie mit Test ins Register `docs/web_abzweigungen.toml`.

## 5. Fragen an Ben (Katalog P230) — meine Empfehlung zuerst

a) **Eigene Datei an Übung/Plan/Kurs löschen: überall herausnehmen?** Empfehlung: ja, nach
   Rückfrage mit den Stellen. Sonst bliebe an jeder Stelle „Datei fehlt“.
b) **Dateien aus Paketen: löschbar?** Empfehlung: ja, mit Rückfrage („kommt mit dem Paket
   wieder“); ohne Rückfrage nur, wenn eine Quelle sie nachweislich wieder liefert.
c) **Symbole und Bilder der Bewegung mit aufnehmen?** Empfehlung: nein — klein, und beide haben
   ihr eigenes Blatt zum Löschen; nur ihre Größe zählt in der Gesamtsumme.
d) **Ordnung:** Abschnitte nach Herkunft, Chips nach Art (wie oben) — oder umgekehrt Abschnitte
   Fotos · Videos · Audio · PDFs? Empfehlung: wie oben, weil die Löschregel an der Herkunft hängt.
e) **„Anhang“ bleibt** das Wort an Eintrag und Notiz; nur die Seite heißt „Medien“. Recht so?
f) (27.11.) **Eigene Datei löschen, die ein Kursblock „Medium“ zeigt:** Der Block fällt mit
   weg. Empfehlung: ja, die Rückfrage nennt ihn; Folgen an Antworten, die nur ihn zeigten,
   entfallen damit.
