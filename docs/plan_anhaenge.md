# Plan: Anhänge an Einträgen — Fotos und Videos der eigenen Übung

Stand 19.10.2026: Vorschlag (Ben: „Plane das erst vor der Freigabe.“). **20.10.2026: Teile
A–E gebaut** (Ben: „Kümmere dich um die Medienablage der Übungen und im Tagebuch“) — die
Entscheidungen G1–G5 wie vorgeschlagen, G6 (Skizzen) entfiel. Was vom Bau abweicht, steht
kursiv in den Abschnitten; Gerätetests T62–T67 in `docs/offene_fragen.md`. F (Hochladen)
kam am 21.10.2026 dazu, **H (Audio und Anhänge am Tag) am 22.10.2026** (Gerätetest T75).
Noch nicht gebaut: Anhänge an Messungen, Praxis-Sync.
Katalog P44 (Knöpfe, Ablage), P45 (e) (Tagebuch), K-F6/Abschnitt 4 (Medien an Übungen
aus Paketen — **bleibt vertagt**, dieser Plan betrifft nur eigene Aufnahmen),
Sicherheitsdurchsicht S4 (Backup) und S1 (Links). Bens Auftrag vom 19.10.:

> Wenn Übungen gemacht sind, soll man Photos/Videos nachtragen können. … Unten kann man
> „+Nachtragen“, „im Verlauf ansehen“. Noch ein Button Anhang hinzufügen … Bild und
> Video … beide Buttons nebeneinander … Kämen zusätzliche Buttons rein, lieber „Anhang“
> und dann Menü. Die Bilder/Videos werden im Tagebuch mit angezeigt, dezent über einen
> Anhangknopf (Büroklammer). Auflösung nicht zu groß, drei Qualitäten, mittlere
> Standard. Speicher muss sich leeren lassen bzw. im Überblick bleiben. Wo werden
> Übungsanhänge abgelegt? Im Tagebuch keine Videos direkt laufen lassen, nur Frontbild
> klickbar. In der Übung nachverfolgen, wie sie im Verlauf ausschaut.

Fünf Teile, jeder für sich lauffähig:

| Teil | Was | Schicht |
|---|---|---|
| A | Ablage, Datenmodell, Qualitätsstufen | `config`, `core/anhaenge.py`, Migration 025, `data/anhaenge.py` |
| B | Aufnehmen in der App (Foto, Video) und Knöpfe im Leistungen-Blatt | `ui/views/anhang_aufnahme.py`, `leistungen.py`, flet-camera |
| C | Ansehen, Löschen; Frontbilder an Eintrag, Tag und Tagebuch | `ui/views/anhang.py`, `leistungen.py`, `tag.py`, `tagebuch.py` |
| D | Verlauf der Übung als Bilderreihe | `uebung_detail.py` |
| E | Einstellungen: Qualität, Speicherübersicht, Aufräumen | `ui/views/einstellungen_anhaenge.py` |

*Gebaut (20.10.) außerdem: `ui/components/anhang_reihe.py` (Kacheln), `ui/views/anhang_verlauf.py`
(Raster in der Übung), Routen ``…/anhang/aufnehmen/<eintrag>/<foto|video>`` und ``…/anhang/<id>``
über jeder Ansicht (`app.ebenen`, wie der Timer), `ui/ausrichtung` erlaubt dort Drehen,
Tagebuch-Art `AUFNAHME` in `core/tagebuch.sammeln`, Tests `tests/test_anhaenge.py`,
`tests/test_ui_anhaenge.py`. Am Rechner steht statt der Kamera „Datei wählen“ (unverkleinert,
nur zum Prüfen des Ablaufs). flet-camera liegt in 1.0.3 vor; ob `camera_android_camerax` die
jni-Override-Falle trifft, zeigt erst Bens APK-Build.*

Danach, getrennt zu entscheiden: Galerie-Import mit Verkleinern (braucht eine eigene
Flutter-Erweiterung, Abschnitt F), Anhänge an Messungen und Notizen, Praxis-Sync.

---

## 0. Grundsätze

- **Die Datei ist die Wahrheit.** Fotos und Videos liegen als Dateien im Datenverzeichnis,
  die Datenbank hält den Verweis (`entry_media.uri`, relativ) und Kennzahlen — wie
  `hrv_recording.file_path`. Löschen löscht die Datei; ohne Datei zeigt die Zeile „fehlt“.
- **Ablage: `<Datenverzeichnis>/Anhaenge/<JJJJ>/<MM>/<zeit>_<kurz-id>.jpg|.mp4`**, Frontbild
  eines Videos daneben als `…_bild.jpg` (`config.anhaengeverzeichnis()`). Getrennt von
  `Messungen/` (praxis_gui liest und synchronisiert diesen Ordner), getrennt von
  `Medien/` (für Übungsfotos aus Paketen reserviert, `exercise.image_path`) und
  `Strecken/`. Auf Android ist das der app-private Speicher: nichts in der Galerie,
  für andere Apps unsichtbar; Monatsordner halten Verzeichnisse klein und machen
  „älter als“ im Dateisystem sichtbar.
- **Nie geteilt** (Regel wie GPS): nicht im Messungs-Export, nicht im Forschungsexport,
  nicht in Diagnose, nicht im späteren Sync ohne eigene Entscheidung. Einzige Ausnahme:
  „Teilen“ am einzelnen Anhang, das die Person selbst drückt (wie der GPX-Export).
  Kein Backup: S4 muss vorher stehen (`allowBackup="false"`), sonst wandern die Videos
  in Googles Cloud.
- **Kein Ortsstempel.** Die Kamera-Erweiterung liefert nackte Bytes (JPEG/MP4), die wir
  selbst schreiben — es entsteht kein EXIF-GPS. Beim späteren Galerie-Import (F) wird
  EXIF beim Verkleinern verworfen.
- **Nur Dokumentation, keine Bewertung.** Die App zeigt die Aufnahmen chronologisch;
  sie beurteilt keine Haltung und vergleicht nichts automatisch
  (`docs/recht/00_zweckbestimmung.md`, wie `physiologische_steuerung`).
- Keine Rechenlogik in `ui/`: Dateinamen, Qualitätsstufen, Größenformat, Aufräumregeln
  in `core/anhaenge.py` (flet-frei, Doctests), Datenbank in `data/anhaenge.py`.

## A. Ablage, Datenmodell, Qualitätsstufen

**Tabelle `entry_media`** gibt es seit Migration 001 (`id`, `session_entry_id`, `kind`
video|image, `uri`, `recorded_at`) — bisher schreibt und liest sie niemand
(`SessionEntry.media` bleibt leer). Migration **025_anhaenge.sql** ergänzt additiv:

```sql
ALTER TABLE entry_media ADD COLUMN bytes      INTEGER NOT NULL DEFAULT 0;
ALTER TABLE entry_media ADD COLUMN dauer_s    REAL;            -- nur Video
ALTER TABLE entry_media ADD COLUMN breite     INTEGER;
ALTER TABLE entry_media ADD COLUMN hoehe      INTEGER;
ALTER TABLE entry_media ADD COLUMN vorschau   TEXT;            -- Frontbild eines Videos, relativ
ALTER TABLE entry_media ADD COLUMN qualitaet  TEXT NOT NULL DEFAULT 'mittel';
ALTER TABLE entry_media ADD COLUMN note       TEXT NOT NULL DEFAULT '';
ALTER TABLE entry_media ADD COLUMN created_at TEXT NOT NULL DEFAULT '';
CREATE INDEX idx_entry_media_recorded ON entry_media(recorded_at);
```

`session_entry` bleibt unverändert und unveränderlich — ein Anhang ist eine eigene Zeile,
wie eine Notiz mit Anker. Sync-Felder (`outbox`) kommen, wenn die Praxis-Edition Anhänge
überhaupt überträgt (Entscheidung offen, Abschnitt G).

**`core/anhaenge.py`:**

- `Qualitaet` (StrEnum `klein` · `mittel` · `gross`) mit `preset` (flet-camera
  `ResolutionPreset.MEDIUM` 480p · `HIGH` 720p · `VERY_HIGH` 1080p), `video_bitrate`
  (0,4 · 0,8 · 2 Mbit/s), `audio_bitrate` (48 · 64 · 96 kbit/s), `label`, `richtwert`
  („~0,2 MB je Foto · ~6,5 MB je Minute Video“). Foto und Video nutzen dasselbe Preset.
  Vorgabe **mittel** (`app_setting` `anhang_qualitaet`). Bis 21.10.2026 eine Stufe
  größer (720p/1080p/2160p, 1,5/3/6 Mbit/s) — Ben: „Ein 1-Minutenvideo hat 14,6 MB. Das
  ist viel zu viel.“ Gespeicherte Aufnahmen nennen darum nur den Namen der Stufe.
- `MAX_VIDEO_S` = 60 als Vorgabe, einstellbar 30/60/120/180 (`anhang_video_max_s`):
  flet-camera gibt das Video als Bytes zurück, es liegt also einmal ganz im Speicher
  (bei „mittel“ ~22 MB je Minute); über drei Minuten wird das auf alten Geräten eng.
- `dateiname(art, zeit, kurz_id)`, `relativer_pfad(zeit, name)`, `vorschau_name(name)` —
  Zeit aus `recorded_at`, nie aus Nutzertext.
- `groesse_text(bytes)` (nutzt `pakete.groesse_text`), `monatsgruppen(anhaenge)`,
  `aufraeumen_vorschlag(anhaenge, aelter_als)`, `verwaiste(dateien, zeilen)`.

**`data/anhaenge.py` (`AnhangRepo`):** `anlegen(anhang, daten: bytes, vorschau: bytes |
None)` schreibt Datei(en) atomar (`.tmp` → `rename`) und dann die Zeile in einer
Transaktion; `je_eintrag`, `je_eintraege(ids)` (eine Abfrage für Tag und Tagebuch),
`je_uebung(exercise_id, von, bis)` (Join über `session_entry`), `je_tag(subject, tag)`,
`alle(subject)` mit Summen, `loeschen(id)` (Zeile, dann Datei und Frontbild — Reihenfolge
wie beim Papierkorb: lieber eine verwaiste Datei als ein toter Verweis),
`gesamtgroesse`. `SessionEntryRepo` lädt `media` **nicht** mit (Kosten in jeder Liste);
die Ansichten holen Anhänge gezielt.

## B. Aufnehmen in der App

**Weg:** `flet-camera` (Flet-Erweiterung um das Flutter-Plugin `camera`, 1.0.4 verfügbar):
eigene Kameraansicht in der App, `take_picture() -> bytes`, `start_/stop_video_recording()
-> bytes`, Auflösung und Bitrate beim `initialize` — genau die drei Qualitäten, ohne
Umweg über die System-Kamera. Vorteile gegenüber der System-Kamera (image_picker):
Qualität ist steuerbar (die System-Kamera nimmt Video in ihrer Einstellung auf, oft 4K),
nichts landet in der Galerie, kein EXIF-GPS, und der Bildschirm bleibt in der App
(Wegwischen während der Aufnahme fällt unter H19: die Engine überlebt, die Aufnahme
wird beim Zurückkommen verworfen). Preis: Berechtigungen `CAMERA` und `RECORD_AUDIO`
im Manifest (`[tool.flet.android.permission]`, iOS `NSCameraUsageDescription`/
`NSMicrophoneUsageDescription` in `build/*.toml`), Laufzeitabfrage über
flet-permission-handler beim ersten Öffnen; neuer APK-Build (Ben) — vorher prüfen, ob
`camera_android_camerax` die jni-Override-Falle trifft (`docs/offene_fragen.md`, APK-Build).

**Knöpfe im Leistungen-Blatt** (`leistungen._nachtragen_zeile`, Skizzen 1GXkdH1CKtExVtxKiYXcrC
Reihe C): unter „Nachtragen · Im Verlauf“ eine zweite Zeile mit zwei `OutlinedButton`
„Foto“ (`CAMERA_ALT`) und „Video“ (`VIDEOCAM`) — zwei Knöpfe füllen die Zeile. Kommt
ein dritter Weg (Galerie, F), wird daraus ein Knopf „Anhang“ (`ATTACH_FILE`) mit Menü
(Foto · Video · Aus der Galerie). Die Zeile hängt am **jüngsten Eintrag des Tages**
dieser Übung; außerdem trägt jede Eintragskarte (`karte_bauen`) eine kleine
Büroklammer rechts neben dem Löschen-Symbol, die den Anhang gezielt an **diesen**
Eintrag hängt. Ohne Eintrag an dem Tag: „Erst eintragen (Nachtragen), dann anhängen.“

**Aufnahmeseite `/anhang/aufnehmen/<eintrag>/<foto|video>`** (`views/anhang_aufnahme.py`):
Vorschau vollflächig, unten Auslöser bzw. Aufnahme/Stopp mit laufender Zeit und
Restzeit bis `MAX_VIDEO_S`, Kamera wechseln (Rück/Front — Front ist für Übungen vor dem
Handy die Regel). Das Ergebnis liegt über der Kamera (`Camera.content`), nie an ihrer
Stelle — aus dem Baum genommen gibt flet-camera den Controller frei, und nach „Verwerfen“
war die Kamera tot (21.10.2026).

**Oben im Bild** (Ben, 21.10.2026, P73: „Timer (1, 3, 5, 10 s), Qualität direkt an der
Kamera, Blitz … nicht zu viel“; Skizzen H1/H2 https://claude.ai/artifact/7JzRndHG41e3ZfeCm7huCH)
drei Knöpfe hell auf dunklem Grund (`core.anhaenge.BLITZ`, `TIMER_STUFEN`):
- **Blitz** — Foto aus → automatisch → an, Video „Licht“ aus ↔ an (Dauerlicht, auch während
  der Aufnahme). Beim Öffnen steht er aus; jeder neue Controller (Qualität, Kamera
  wechseln) bekommt ihn wieder. Hat die Kamera keine Lampe (Frontkamera), bleibt er aus,
  und unter dem Bild steht „ohne Blitz“.
- **Timer** — ein Tipp: aus → 1 → 3 → 5 → 10 s. Mit Timer zählt die Mitte groß herunter,
  je Sekunde der Countdown-Ton des Timers (mit dessen Lautstärke); „Abbrechen“ hält an,
  beim Video beginnt danach die Aufnahme („Video in 3 s · danach höchstens 1:00“).
- **Qualität** — Klein · Mittel · Groß **nur für diese Aufnahme**: Die Kamera öffnet mit
  dem anderen Preset neu, die Vorgabe bleibt in Einstellungen → Anhänge.

Mehr nicht: Für Profiaufnahmen und lange Videos ist die Kamera des Telefons da (dann
„Hochladen“, F). **Zustandsfehler:** flet-camera trägt einen Fehler in jedem weiteren
Zustand mit. Bis 21.10.2026 machte schon „Blitz aus“ an einer Kamera ohne Lampe
(„torchModeNotSupported“, im Browser beim Öffnen) jeden späteren Zustand zum Fehler —
Auslöser gesperrt, „Verwerfen“ verließ die Seite. Jetzt zählt nur ein neuer Fehler,
Blitzfehler gar nicht, und die geöffnete Kamera bleibt bereit (`_Aufnahme._zustand`). Drehen erlaubt (`ui/ausrichtung`, wie Ausdauer). Bei Video wird
**direkt vor dem Start ein Foto geschossen** — das ist das Frontbild (`vorschau`); so
braucht es keine Video-Thumbnail-Bibliothek. Nach der Aufnahme: Vorschau mit „Behalten“
/ „Verwerfen“ und einer Notizzeile (`note`, optional, z. B. „links“). „Behalten“
schreibt über `AnhangRepo.anlegen` im Thread (`asyncio.to_thread`, die Bytes sind groß)
und geht zurück ins Blatt, das die Bilderreihe auffrischt.

## C. Ansehen, Löschen, Frontbilder

- **Ansicht `/anhang/<id>`** (`views/anhang.py`): Foto groß mit Zoom
  (`InteractiveViewer`), Video mit `flet-video` (ist schon Abhängigkeit) — **nur hier**
  läuft ein Video, nirgends automatisch. Kopf: Übung, Datum/Uhrzeit, Dauer, Größe,
  Qualität, Notiz (bearbeitbar, „Zurück speichert“). Aktionen in der AppBar: Löschen
  (Rückfrage, endgültig — kein Papierkorb für Dateien, Abschnitt G), Teilen
  (`weitergeben`, bewusste Handlung, Hinweis „Diese Datei verlässt die App“).
  Pfeile links/rechts blättern durch die Anhänge desselben Eintrags.
- **Frontbilder** als wiederverwendbare Komponente `components/anhang_reihe.py`:
  waagrechte Reihe quadratischer Kacheln (64 px, `ft.Image(src=pfad, cache_width=192)`
  — dekodiert klein, Original bleibt liegen), Videos mit Play-Dreieck und Dauer im
  Overlay, antippen → Ansicht. Mehr als sechs: „+3“ als letzte Kachel. Flet zeigt lokale
  Dateien im App-Speicher über den absoluten Pfad; wenn das auf Android hakt
  (Gerätetest), Fallback `src=bytes` eines vorab verkleinerten Frontbilds.
- Wo die Reihe steht: Leistungen-Blatt unter jeder Eintragskarte mit Anhängen; **Tag**
  (`tag.py`, „Heute“ und `/tag/<datum>`): unter der gemachten Übung, in der Übersicht wie in
  der Zeitleiste — ein Tipp öffnet die Ansicht (Ben, 22.10.2026: „Photos erzeugen in
  Verlauf eine Miniaturansicht. In Heute aber nicht … dass man die Anhänge direkter sieht“;
  vorher eine dezente Büroklammer mit Zahl, die Reihe erst im Blatt); **Tagebuch**
  (`tagebuch.py`): im Tagesblock ein eigener Block „Aufnahmen“ je Eintrag (Uhrzeit · Übung
  · Reihe), in der Ordnung „Übungen“ unter der Übung — Notizen und Aufnahmen bleiben
  getrennte Karten, kein Autoplay. Die Kacheln kosten wenig: eine Abfrage für den ganzen
  Tag (`je_eintraegen`), höchstens sechs je Übung, klein dekodiert (`cache_width`).

## D. Verlauf der Übung

`uebung_detail.py` bekommt den Abschnitt **„Aufnahmen“** (nur wenn welche da sind):
Raster mit drei Spalten, neueste oben, je Kachel Datum darunter; Monatsüberschriften ab
zwölf Kacheln; Filter „letzte 4 Wochen · 3 Monate · alle“. Antippen → Ansicht, dort
blättern durch alle Aufnahmen **dieser Übung** chronologisch — das ist das „wie schaut
die Übung im Verlauf aus“. Daten aus `AnhangRepo.je_uebung`; Varianten einer Familie
zählen mit (wie im Verlauf der Mengen).

## E. Einstellungen: Qualität und Speicher

Neue Seite **Einstellungen → Anhänge** (`einstellungen_anhaenge.py`, Karte „Übungen“):

- Qualität: `SegmentedButton` klein · mittel · groß mit Richtwerten je Stufe; gilt für
  künftige Aufnahmen, gespeichert in `app_setting`.
- Maximale Videolänge: 30 s · 1 min · 2 min · 3 min.
- **Überblick:** Gesamtgröße, Anzahl Fotos/Videos, darunter Monatsgruppen mit Größe und
  Anzahl (aus `core/anhaenge.monatsgruppen`), je Gruppe aufklappbar zur Kachelreihe.
  Mehrfachauswahl (lange drücken) und „Löschen“ mit Rückfrage „12 Aufnahmen, 180 MB —
  endgültig“. Schnellwege: „Videos älter als 3 Monate“, „Alles von Übung …“.
- Aufräumen: „Verwaiste Dateien“ (Datei ohne Zeile, nach Absturz zwischen Schreiben und
  Eintragen) und „Fehlende Dateien“ (Zeile ohne Datei) anzeigen und bereinigen.
- Hinweistext: wo die Dateien liegen, dass sie nicht in Export, Backup und Sync gehen,
  und dass „Teilen“ am einzelnen Anhang die bewusste Ausnahme ist.

Die Paketseite zeigt heute die Größe eigener Übungsmedien (`PaketRepo.groesse`);
Anhänge zählen dort nicht mit — sie gehören zu Einträgen, nicht zu Paketen.

## F. Hochladen aus der Fotoauswahl (gebaut 21.10.2026, P74)

Ben, 21.10.2026: „Ermögliche das Hochladen von Anhängen. Dabei Vorsicht mit den
Nutzerrechten, hier nicht zu aggressiv sein.“ Videos höchstens zehn Minuten. Skizzen I1/I2
(https://claude.ai/artifact/7JzRndHG41e3ZfeCm7huCH).

- **Wo:** im Leistungen-Blatt der dritte Knopf „Hochladen“ neben Foto und Video, an der
  Büroklammer „Aus der Fotoauswahl“ — nur, wo die Erweiterung da ist (gebaute Android-App).
  Seite `…/anhang/hochladen/<eintrag>` (`ui/views/anhang_hochladen.py`).
- **Rechte:** image_picker mit dem **Photo Picker** von Android — keine Berechtigung für
  Fotos oder Speicher, die App bekommt nur die gewählte Datei (eine Kopie im Cache).
- **Verkleinern** (Erweiterung `erweiterungen/flet_hochladen`): Fotos mit
  flutter_image_compress auf die kurze Seite der Stufe (480/720/1080 px), JPEG **ohne
  Exif**; Videos mit einer eigenen Kotlin-Klasse über Transcoder 0.10.5 — Bitrate wie die
  Kamera (`Qualitaet.video_bitrate`/`audio_bitrate`), Keyframes alle 5 s (sonst reicht
  Transcoder Videos mit passender Größe unverkleinert durch), Datenquelle **ohne Ort**
  (`OhneOrt`), dazu das Frontbild. Fortschritt in Prozent, „Abbrechen“.
- **Warum nicht die fertigen Pakete:** image_picker kopiert beim Verkleinern die GPS-Felder
  mit (`ExifDataCopier`); video_compress schätzt die Bitrate (0,14 · Breite · Höhe · fps,
  bei 720p 3,9 Mbit/s ≈ 30 MB je Minute) und schreibt den Ort des Originals ins Ergebnis;
  light_compressor kennt nur ganze Mbit/s und lädt seine Bibliothek von JitPack.
- **Netz darunter:** Was die Erweiterung liefert, prüft die App noch einmal:
  `core.anhaenge.jpeg_ohne_metadaten` (APP1/APP13/Kommentare weg, Bilddaten unverändert)
  und `data.anhaenge.mp4_ort_entfernen` (``©xyz``, ``loci``, ``meta`` im ``moov`` werden zu
  ``free`` — gleiche Größe, alle Versätze bleiben gültig). Die Kopie der Auswahl wird gleich
  nach dem Verkleinern gelöscht.
- **Zu lang:** Videos über zehn Minuten (`HOCHLADEN_VIDEO_MAX_S`) werden gar nicht erst
  verkleinert — „In der Galerie kürzen (Bearbeiten → Zuschneiden), dann noch einmal.“
- **Behalten** verschiebt die fertigen Dateien aus `Anhaenge/.hochladen/` an ihren Platz
  (`AnhangRepo.dateien_uebernehmen`) — ein Video von zehn Minuten wiegt bei „Mittel“ gut
  60 MB, das trägt keine Brücke durch den Speicher. Reste in `.hochladen/` findet
  „Aufräumen“.
- **Prüfung ohne Handy:** Dart `flutter analyze` ohne Befund; die Kotlin-Klasse kompiliert
  mit Kotlin 2.2.20 gegen android.jar 36, das Flutter-Embedding und Transcoder 0.10.5. Der
  erste APK-Build mit der Erweiterung ist zugleich ihr erster Gradle-Build (T71).

## H. Audio und Anhänge am Tag (gebaut 22.10.2026)

Ben, 22.10.2026, zur Notiz zum Tag unter Heute: „Auch eine Audioaufnahme soll möglich sein +
Photo + Video. Erweitere die Medien um Audio.“ Zugleich wurde die Notiz selbst direkt
beschreibbar (`ui/components/tagesnotiz.py`, Autosave, ↶ ↷ aus `core/textverlauf.py`).

- **Audio ist die dritte Art** (`core.anhaenge.AUDIO`, Endung ``.m4a``, kein Frontbild): AAC,
  einkanalig, 44,1 kHz, Tonrate der Qualitätsstufe (`Qualitaet.audio_bitrate`: 48 · 64 ·
  96 kbit/s ≈ 0,4 · 0,5 · 0,7 MB je Minute). Höchstens `AUDIO_MAX_S` = 30 min — der Rekorder
  schreibt gleich in die Datei, die Grenze fängt nur ein vergessenes Stopp ab. Am Rechner,
  wo der Rekorder kein AAC kennt, wird es WAV (`neuer_anhang(…, endung="wav")`).
- **Aufnehmen** auf eigener Seite ``…/anhang/aufnehmen/<ziel>/audio``
  (`ui/views/anhang_ton.py`, flet-audio-recorder um das Flutter-Plugin `record`): ● · ⏸/▶ ·
  ⏹, die Zeit groß, danach Anhören, Notiz, „Behalten“/„Verwerfen“. Die Datei entsteht unter
  ``Anhaenge/.aufnahme/`` und wird **vor** dem Start leer angelegt — Flet reicht dem Plugin nur
  einen vorhandenen Pfad unverändert durch (`getAssetSrc` legte einen neuen in den Ordner
  der App-Assets). „Behalten“ verschiebt sie an ihren Platz (`AnhangRepo.dateien_uebernehmen`).
  Der Rekorder ist ein Dienst außerhalb der Seite: Pfeil und Systemtaste brechen eine
  laufende Aufnahme ab und löschen die Datei. Bluetooth-Kopfhörer bleiben außen vor
  (`manage_bluetooth=False`), aufgenommen wird mit dem Mikrofon des Telefons.
- **Abspielen** nur in der Ansicht ``…/anhang/<id>`` und vor dem Behalten
  (`ui/components/tonspieler.py`, flet-audio um `audioplayers`): ▶/⏸, Regler, Zeit. Der Spieler
  bekommt den Pfad; beim Verlassen — auch über die Systemtaste
  (`zurueck_speichert(vorher=…)`) — hält er an. Die Kachel zeigt ein Klangsymbol und die Dauer.
- **Anhänge am Tag:** Ein Anhang hängt an einem Eintrag **oder** am Tag eines Profils
  (`core.anhaenge.Ziel`; Migration 029 baut `entry_media` neu: `kind` mit 'audio',
  `session_entry_id` darf leer sein, dafür `subject_id` + `day`, genau eins von beiden). Die
  Wege tragen das Ziel als ``tag/<datum>`` statt der Eintrags-ID (Aufnehmen, Hochladen; ein Tag
  in der Zukunft gilt nicht). Unter der Notiz zum Tag stehen Foto · Video · Audio
  (· Fotoauswahl) und die Kacheln; in der Ansicht blättern die Pfeile durch die Anhänge
  desselben Tags. Abfragen nach Übungen (`je_eintraegen`, `je_uebung`, `je_tag`) sehen sie
  nicht; Speicherübersicht, Summe, Tagebuch und Aufräumen schon. Im Tagebuch: je Tag eine
  Karte „Aufnahmen · Zum Tag“ (Tipp → der Tag), nach Übungen geordnet bei den Notizen zum Tag.
  Die Anhänge gehören zum Tag, nicht zum Text: Leert man die Notiz, bleiben sie.
- **Leistungen:** Foto · Video · Audio (· Hochladen) — am Handy zu zweit in zwei Zeilen, auf
  breitem Bildschirm in einer; an der Büroklammer „Audio aufnehmen“.
- **Regeln wie bisher:** app-privat, ohne Ort, nie in Export, Diagnose oder Sync; hinaus nur
  über „Teilen“ (MIME ``audio/mp4``). Keine Bewertung, keine Spracherkennung.

## G. Zu entscheiden (Ben)

1. **Kamera in der App** (flet-camera, Qualität steuerbar, nichts in der Galerie, zwei
   Berechtigungen) statt System-Kamera — Empfehlung: in der App.
2. **Videolänge** 60 s als Vorgabe, bis 3 min einstellbar — reicht das für eine Übung?
3. **Löschen endgültig** ohne Papierkorb für Dateien (ein Papierkorb hielte den Speicher
   belegt, den man gerade leeren will) — oder 7 Tage Frist wie bei Übungen?
4. **Knopfzeile → jüngster Eintrag des Tages**, Büroklammer je Karte → gezielt. Richtig so?
5. **Praxis-Edition:** gehen Anhänge jemals zur Praxis? Vorschlag: nein, bis es eine
   Einwilligung und ein Rechtekonzept dafür gibt (`docs/recht/20_einwilligung.md`).
6. Skizzen als Handy-Bildergeschichte (Design-Canvas) vor dem Bau — gewünscht?

## Recht, Build, Tests

- `docs/recht/10_verarbeitungsverzeichnis.md`: neue Datenart „Foto/Video der eigenen
  Übungsausführung“ (Gesundheitsbezug möglich), Zweck Dokumentation, Speicherort,
  Löschung durch die Person. `40_toms.md`: app-privat, kein Backup (S4), kein Export,
  kein Sync. `80_store_freigaben.md`: Begründung für `CAMERA`/`RECORD_AUDIO`.
  `build/solo.toml`, `build/praxis.toml`: iOS-Texte.
- Reihenfolge der Builds: S4 (Backup aus) **vor** oder **mit** dem Kamera-Build.
- Hochladen (F): keine neue Berechtigung (`80_store_freigaben.md`); neue Erweiterung mit
  Android-Teil — `flet build` holt Transcoder (Maven Central) beim ersten Build.
- Audio (H): keine neue Berechtigung — `RECORD_AUDIO` gab es für den Ton der Videos schon, sie
  dient jetzt auch Audioaufnahmen (`80_store_freigaben.md`, iOS-Text in `pyproject.toml` und
  `build/*.toml`); neue Datenart „Audioaufnahme“ in `10_verarbeitungsverzeichnis.md`. Zwei neue
  Flutter-Plugins (`record`, `audioplayers`) — der nächste APK-Build ist ihr erster.
- Tests: Doctests `core/anhaenge` (Namen, Stufen, Gruppen, Aufräumvorschlag);
  `tests/test_anhaenge.py` für Repo (anlegen atomar, löschen entfernt Datei und Frontbild,
  verwaiste/fehlende); Importregel bleibt (core/data flet-frei); Gerätetests T61–T66:
  Berechtigungsdialog, Front/Rück, Drehen, Wegwischen während Aufnahme, Frontbild im
  Tagebuch, Speicherübersicht mit 50 Videos.
