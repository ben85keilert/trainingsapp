# flet-hochladen

Flet-Erweiterung der Trainingsapp (P74, Ben 21.10.2026): **ein Foto oder Video aus der
Fotoauswahl von Android**, verkleinert und ohne Ortsangabe. Nur in der gebauten Android-App.

- **Auswahl:** image_picker mit dem Android Photo Picker — die App bekommt nur die gewählte
  Datei und braucht keine Berechtigung für Fotos oder Speicher (kein `READ_MEDIA_*`).
- **Fotos:** flutter_image_compress, kurze Seite wie die Qualitätsstufe (480/720/1080 px),
  JPEG **ohne Exif** (`keepExif: false`). image_picker selbst kopierte beim Verkleinern die
  GPS-Felder mit (`ExifDataCopier`) und verkleinert darum hier nicht.
- **Videos:** eigene Kotlin-Klasse mit Transcoder 0.10.5 — feste Bitrate (wie die Kamera
  der App), AAC-Ton, Keyframes alle 5 s, und eine Datenquelle ohne Ort (`OhneOrt`).
  video_compress schätzte die Bitrate (720p: 3,9 Mbit/s) und übernahm den Ort.
- **Netz darunter (App):** `core.anhaenge.jpeg_ohne_metadaten` und
  `data.anhaenge.mp4_ort_entfernen` prüfen das Ergebnis noch einmal.

Python: `FletHochladen` (Service) mit `waehlen`, `dauer_ms`, `verkleinern`, `abbrechen`
und dem Ereignis `on_fortschritt`; `verfuegbar(page)`.

Eingebunden wie flet_ton: `pyproject.toml` der App (`dependencies`, `[tool.uv.sources]`,
`[tool.flet.dev_packages]`).
