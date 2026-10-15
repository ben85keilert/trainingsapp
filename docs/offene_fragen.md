# Offene Fragen

Katalog der Entscheidungen, die Ben noch treffen muss, und der Befunde, die
noch nicht behoben sind. Angelegt am 15.10.2026 nach der Durchsicht der
Änderungen vom 14./15.10. Was entschieden ist, wandert mit Datum in den
Abschnitt „Entschieden“ am Ende (oder in die zuständige Doku) — der Katalog
hält nur Offenes.

Regel: Neues Offenes kommt **hier** hinein, nicht verstreut in Plan-Dateien.
Je Eintrag: Woher, Frage, Stand/Vorschlag.

Schwere der Befunde: **hoch** = Datenverlust, Absturz im Normalgebrauch,
Datenschutz · **mittel** = falscher Wert, Leak, spürbare Last · **niedrig** =
Schönheit, Wartung.

---

## 1. Produktentscheidungen (Ben)

| # | Woher | Frage | Stand / Vorschlag |
|---|---|---|---|
| P1 | Plan, 14.10. | **Planblock: welche der drei Darstellungen** (untereinander = Vorgabe, umschalten, aufklappen) bleibt? Die anderen beiden sind dann zu entfernen (`ui.state.PLAN_DARSTELLUNGEN`). | Wahl steht aus. |
| P2 | Paket „Standard“, 15.10. | **Auswahl der 33 Übungen** in `data/seed/standard.toml` durchsehen (16 alte, 17 neue, neuer Typ „Mobilisation“, Katze-Kuh dorthin). | Erster Entwurf, ungeprüft. |
| P3 | Pakete | Weitere mitgelieferte Pakete (Dehnung, Kräftigung …): je Paket eine TOML neben `standard.toml` — welche zuerst, wer pflegt sie? | Offen. |
| P4 | „Heute“, `plan_hrv_timer.md` | „Heute“ fasst Pläne doppelt zusammen (Bilanz oben, Plan darunter). Welche Stellen wirken noch gedrängt? | Am besten mit Bildschirmfotos klären. |
| P5 | HRV-Timer | Kopplung Timer ↔ HRV-Messung ↔ Plan: Abschnitte schreiben Notizen — soll der Timer auch Pläne abhaken oder eine Messung starten? | Offen seit 13.10. |
| P6 | GPS-Plan, Abschnitt 8 | DFA-α1-Wertebereiche für die Übersicht (neutral) — die vorgeschlagenen übernehmen? | Offen. |
| P7 | GPS-Plan | Eigene Kachelquelle (Protomaps-Ausschnitt) erst mit Phase 5 — bis dahin Online-Kacheln? (Siehe Befund G-Kacheln unten.) | Offen. |
| P8 | GPS-Plan | Play Store: Vordergrunddienst als `health` statt `location` deklarieren? | Später. |
| P9 | Verity Sense beim Training | HF-Modus ohne PPI fürs Training (PPI stoppen, danach wieder starten) braucht einen Test am Gerät. | Offen, Test durch Ben. |
| P10 | Korrektur, `korrektur.md` „Offen“ | Eichung gegen das EKG in Bewegung; dürfen verworfene Intervalle in Ruhe zählen; Fehlerschwelle 30 ms (Polar) oder 50 ms? | Braucht Messungen. |
| P11 | Recht, `00_zweckbestimmung.md` | Weg A/B/C für Edition B (Dokumentationswerkzeug / Klasse I / IIa) — vor dem Bau von Edition B. | Empfehlung Weg A. |
| P12 | Recht, `30_avv.md` | Hoster der Praxisdatenbank (EU?) und AVV. | Offen. |
| P13 | Praxis-Edition | PIN-Sperre beim Profilwechsel (`ist_aktiv("profil_sperre")`) ist bisher nur ein Hinweistext — Umsetzung mit oder ohne Fingerabdruck? | Erst mit Edition B. |
| P14 | M10 | Video-Download (hängt am Hosting), Fotos für eigene Übungen. | Offen. |
| P15 | Live-Wischen, 15.10. | Nach dem Fix (ganzer Fingerweg zählt, siehe Befund H-Wischen) ist 1 Fingerbreite = 1 Fensterbreite. Reicht das, oder zusätzlich Schwung (Fling über `primary_velocity`) bzw. ein Faktor > 1? | Erst am Handy probieren. |

Fragen aus der Durchsicht vom 15.10. (Details beim jeweiligen Befund in Abschnitt 3):

| # | Bereich | Frage | Vorschlag |
|---|---|---|---|
| K-F1 | Pakete (K2) | Paketübungen vom automatischen Papierkorb-Aufräumen ausnehmen, solange das Paket nur „entfernt“ ist, damit „Wieder installieren“ auch Planpositionen zurückbringt? | Ja. |
| K-F2 | Pakete (K5) | Paket-Identität über den Namen: zwei fremde Pakete gleichen Namens = dasselbe Paket? Alternative: zufällige ID beim ersten Export plus Autor-Kennung, Name nur Anzeige. | Zufällige ID, Vertrag anpassen. |
| K-F3 | Pakete (K5) | Darf eine beliebige Datei die Standard-ID tragen und so „Standard“ überschreiben? | Nein — Standard-ID beim Import ablehnen. |
| K-F4 | Pakete (K3) | Tag umbenennen/löschen: Paketstand mitziehen (nie „geändert“) oder als Abweichung werten? | Mitziehen. |
| K-F5 | Pakete (K4) | Lokale Fotos/Videos an Paketübungen beim Update/Reset behalten? | Behalten. |
| K-F6 | Pakete (K1) | Video-Links: nur `http(s)` beim Import filtern und im Editor erzwingen, oder auch App-Schemata (`vnd.youtube:`)? | Nur `http(s)`. |
| K-F7 | Pakete (K6) | Import einer älteren Paketversion über eine neuere: zulassen, warnen, sperren? | Warnen. |
| K-F8 | Pakete (K12) | Archivierte Paketübungen nicht exportierbar — gewollt? | — |
| G-F1 | GPS (G1) | Online-Karte = Kachelkoordinaten an OSMF: Hinweis in Regel 0 und UI, Schalter „Karte aus“ im Training, Karte erst nach Antippen laden? | Hinweis + Schalter. |
| G-F2 | GPS (G2) | `docs/recht` (TOMs, Store-Freigaben, Datenschutzerklärung) für Standortberechtigung, INTERNET und Vordergrunddienst `location` nachziehen. | Vor dem nächsten Release. |
| G-F3 | GPS (G5) | Verhalten ohne Doppler-Tempo (Tempo 0 = „fehlt“): Rückfall auf reinen 10-m-Schritt oder Gerät ablehnen? | Rückfall per `speed_accuracy`. |
| G-F4 | GPS (G4) | Prozess-Tod im Training: verwaiste `.jsonl` beim Start erkennen und nachträglich anlegen (wie HRV-Backup) oder bewusst verlieren? | Nachträglich anlegen. |
| G-F5 | GPS (G8) | Strecken löschen: Papierkorb mit endgültigem Löschen der Koordinatendatei wie bei Messungen? Vorabtest-Dateien aufräumen? | Ja, beides. |
| G-F6 | GPS (G18) | Live-Karte folgt jede Sekunde, Wegwischen unmöglich — bewusst? | „Folgen“ nach Pan aussetzen. |
| G-F7 | GPS (G10) | GPX-Höhe: MSL (`use_msl_altitude=True`) oder Ellipsoid belassen? | MSL (Strava/Komoot erwarten NN). |
| G-F8 | GPS (G18) | `strecke.title` + `titel_setzen` ohne Oberfläche — geplant oder Rest? | — |
| G-F9 | GPS (G6) | GPS-/Vordergrunddienst-Fehler im Training anzeigen (Banner wie im GPS-Test)? | Ja. |
| H-F1 | HRV (H2) | Abschnitte länger als `LANG_AB_S`: langer Spektralweg auch dort, oder LF/HF sperren? | Langer Weg. |
| H-F2 | HRV (H1) | Unlesbares Sidecar: neu anlegen (heute) oder Schreiben verweigern mit Hinweis? | Verweigern. |
| H-F3 | HRV (H5) | praxis_gui-Felder je Segment (`visible`, `active`, `metrics`, `computed_utc`) durchreichen oder normieren? | Durchreichen. |
| H-F4 | HRV (H3) | Atemfrequenz/LF/HF je Abschnitt über Nähte hinweg oder Nähte respektieren? | Respektieren. |
| H-F5 | HRV (H7) | `hrv_metrics_cache` ungenutzt lassen (Doku anpassen) oder für die Öffnungszeit nutzen? | — |
| H-F6 | HRV (H8) | Rechnen beim Öffnen synchron (Plan: akzeptiert) oder per `asyncio.to_thread`? | Am Handy messen. |
| H-F7 | HRV (H6) | Beschreibung: DB-Kopie als Rückfall oder strikt Datei? | Strikt Datei. |
| N-F1 | Profile (N3) | Profilwechsel bei laufender Messung: sperren, Profil im `Messlauf` merken oder Rückfrage? | Profil im Messlauf merken + Hinweis. |
| N-F2 | Notation (N1, N2) | Obergrenzen: maximale Satzzahl (Plan 50, Notation unbegrenzt) und maximaler Wert je Satz/Zeit — eine Zahl für beide Wege? | 50 Sätze, Zeit ≤ 24 h, Werte ≤ 10⁶. |
| N-F3 | Tags (N5) | „dehnung“ = „Dehnung“ überall (UNIQUE `COLLATE NOCASE`) oder nirgends? | Überall. |
| N-F4 | Tags (K3) | Gelöschter Typ steckt weiter in `package_standard_json`; Reset/Re-Import legt ihn wieder an — gewollt? | Siehe K-F4. |
| N-F5 | Pläne (N6) | `plan.revision` als Sync-Anker für Items oder eigene Item-Revision? | Erst mit Edition B. |
| N-F6 | Timer (N7) | Timer-Profil bearbeiten, während der Timer läuft: warnen, blockieren, weiterlaufen? | Weiterlaufen, neues Profil beim nächsten Start. |
| N-F7 | Dialoge (N4) | `Nachher` als verbindliches Muster für jeden Bestätigen-Dialog? | Ja. |
| N-F8 | Darstellung (N15) | `app_setting darstellung:<profil-id>` nach Profil-Löschen belassen? | Belassen (Profile nur ausgeblendet). |

## 2. Am Gerät zu prüfen (Ben)

| # | Woher | Was | Stand |
|---|---|---|---|
| T1 | Timer-Signale | Lautstärke-Wahl Medien/Wecker/Klingelton und Klänge — Dart-Teil von `flet_ton` geändert, braucht neuen APK-Build; auf dem Handy ungetestet. iOS: nur ein Regler. | offen |
| T2 | Pakete | Import am Handy (FilePicker) und Paket entfernen auf dem Gerät noch nicht getestet. | offen |
| T3 | GPS-Vorabtest | Gang mit ausgeschaltetem Bildschirm (Verbrauch im Hintergrund), siehe `plan_gps.md` 9a. | offen |
| T4 | Live-Wischen | Wischweg nach dem Fix vom 15.10. am Handy prüfen (vorher kam nur ~⅙ der Bewegung an). | offen |

## 3. Befunde aus der Durchsicht vom 15.10.2026

Durchgesehen: Commits `59f3149..ed8bf8f` (14./15.10., alle mit Claude Opus).
Lint, Format, mypy und 573 Tests waren vor der Durchsicht grün.

Was hier steht, ist **nicht behoben** — behobene Befunde stehen nur noch im
Commit. Jeder Befund trägt eine Stelle zum Nachlesen; „Frage“ heißt, dass
Bens Entscheidung vor dem Fix nötig ist.

### 3.1 Datenbank und Migrationen

| # | Stelle | Befund | Schwere |
|---|---|---|---|
| D1 | `data/db.py:66-74` | Migrationen laufen **nicht** in eigener Transaktion: `executescript` committet die mit `BEGIN` eröffnete Transaktion erst und läuft dann im Autocommit. Mehrstatement-Migrationen (013: ALTER + INSERT; 015: 2× ALTER) sind nicht atomar; stirbt die App dazwischen oder zwischen Skript und `PRAGMA user_version`, scheitert jeder weitere Start an „duplicate column“. Der Kommentar in Z. 72 behauptet das Gegenteil. Fix: `BEGIN`/`COMMIT` in die `.sql`-Dateien oder je Statement `execute` in einer Transaktion samt Version. | **hoch** |

### 3.2 Übungspakete, Seed, Paketmanager

| # | Stelle | Befund | Schwere |
|---|---|---|---|
| K1 | `ui/views/uebung_detail.py:114`, `core/pakete.py:297-311`, `uebung_bearbeiten.py:450-459` | Video-URIs aus fremden Paketen (und aus dem Editor) werden ohne Schema-Prüfung übernommen und per `launch_url` geöffnet — `intent://`, `file://`, `tel:`, im Web `javascript:`. **Frage K-F6:** beim Import auf `http(s)` filtern oder beim Öffnen warnen? Vorschlag: beim Import filtern, Editor nur `http(s)` annehmen. | mittel |
| K2 | `repositories.py:290`, `data/pakete.py:244-249, 348-357` | „Paket entfernen“ → Papierkorb; nach der Frist löscht das Aufräumen **`plan_item` endgültig**. „Wieder installieren“ holt die Übung zurück, die Planpositionen nicht. `docs/uebungspakete.md:38-40` („holt alles zurück“) stimmt für Pläne nicht. **Frage K-F1:** Paketübungen vom automatischen Aufräumen ausnehmen, solange das Paket nur „entfernt“ ist? | mittel |
| K3 | `core/pakete.py:400`, `repositories.py:1742-1823`, `data/pakete.py:300, 471` | Tag umbenennen/löschen ändert die Übungs-Tags, nicht den gespeicherten Paketstand → alle Paketübungen zeigen „geändert: Typen“; „Auf Paketstand setzen“ legt den alten Tag-Namen wieder an. Beim Standard-Paket wird der Stand jeden Start aus dem TOML neu berechnet, der alte Name bleibt Referenz. **Frage K-F4:** Paketstand mitziehen (nie „geändert“) oder als Abweichung werten? | mittel |
| K4 | `repositories.py:112, 140`, `core/pakete.py:351` | Update/Reset läuft über `speichern`: `exercise_media` wird komplett ersetzt, `image_path` auf `None` gesetzt. Eigene lokale Fotos/Videos an einer Paketübung verschwinden still — und weil `stand()` LOCAL ausfiltert, zeigte „geändert“ das vorher nicht an. **Frage K-F5:** lokale Medien beim Update behalten? | mittel |
| K5 | `core/pakete.py:95-105, 249`, `data/pakete.py:422-427, 512-519` | Paket-ID = UUIDv5 aus dem Namen, Übungs-ID aus Paket-ID + `key`: zwei fremde Pakete „Yoga“ mit `key` „baum“ gelten als dasselbe Paket, der zweite Import überschreibt den ersten. Jede Datei kann die Standard-ID tragen (steht in jedem Export) und so alle Standard-Übungen überschreiben, bekommt sogar `is_builtin=1` (Z. 253). Vertragskonform, aber ohne Autor-Bindung. **Fragen K-F2/K-F3:** zufällige Paket-ID beim ersten Export plus Autor-Kennung, Name nur Anzeige? Darf eine fremde Datei „Standard“ überschreiben? | niedrig (Vertrag) |
| K6 | `data/pakete.py:390-430` | Kein Versionsvergleich: eine ältere Paketdatei überschreibt eine neuere Installation (Downgrade), die Version wird zurückgesetzt. **Frage K-F7:** zulassen, warnen, sperren? | niedrig |
| K7 | `core/pakete.py:166-168`, `ui/views/pakete.py:158, 162-172` | `json.loads` wirft bei tief verschachtelter Datei `RecursionError` (kein `ValueError`) → nicht als `PaketFehler` gefangen; `read_bytes()` ohne `OSError`-Fang; Dateigröße ungedeckelt. | niedrig |
| K8 | `core/pakete.py:237-244, 255-256` | Innenwerte von `result_spec` (`min`, `max`, `step`, `quick`, `default`), `limit_spec`, `default_target` werden nur auf Objekt/Liste geprüft, nicht typisiert (`"seconds": "abc"`) → landen in der DB, Absturz erst in Eingabemaske/Timer (`core/limits.py:144`). | niedrig |
| K9 | `ui/views/pakete.py:82-97`, `uebung_detail.py:203-206` | `importieren()`/`zuruecksetzen()` ohne `try`: ein sqlite-Fehler lässt den Dialog offen, ohne Rückmeldung. | niedrig |
| K10 | `ui/views/pakete.py:190, 332` | Paketliste lädt je Übung einzeln (~4·N Abfragen je Paket), nur um „n geändert“ zu zählen. Bei 33 Übungen harmlos. | niedrig |
| K11 | `ui/components/tagwahl.py:66-88` | `neuer_name` dupliziert die Namensprüfung aus `TagRepo.anlegen` (casefold, Art-Kollision) in `ui/`. | niedrig |
| K12 | `ui/views/pakete.py:526` | Archivierte Paketübungen sind nicht exportierbar (`alle()` ohne Archiv). **Frage K-F8:** gewollt? | niedrig |
| K13 | Doku | `uebungspakete.md:72` „gleicher Name wie ein *installiertes* Paket“ ↔ `mit_namen` nimmt auch entfernte; `:27-29` Paketstand umfasst auch Name, Symbol, Limits; `014_pakete.sql:2-3` nennt noch `exercises.json`; `einstellungen_tags.py:9-10` „Später bringen Pakete …“ veraltet. | niedrig |

Geprüft und in Ordnung: SQL nur mit Platzhaltern; Export-Dateiname bereinigt; eigene Übungen (`package_id IS NULL`) werden nie angefasst; zweiter Start überschreibt nichts; UUIDv5-Stabilität; Flet-API der Pakete-Ansichten; keine `flet`-Importe in `core/`/`data/`.

### 3.3 GPS, Strecken, Ausdauertraining

Regel 0 („GPS nie teilen“) hält in Export, Diagnose, Teilen, Notizen und
Vorabtest-Bericht; Strecken liegen unter `Strecken/`; GPX nur per Knopf.
Eine Ausnahme ist nicht geregelt:

| # | Stelle | Befund | Schwere |
|---|---|---|---|
| G1 | `ui/components/karte_strecke.py:24-27, 40-44`, `ausdauer.py:585-590` | Die **Online-Karte sendet Kachelkoordinaten** (z/x/y, bei Zoom 16/17 ≈ 100–600 m) der Live-Position bzw. der ganzen Strecke an `tile.openstreetmap.org`, jede Sekunde nachgeführt. Von Entscheidung 1 in `plan_gps.md:333` gedeckt, aber Regel 0, der Hinweis „Die Strecke bleibt auf dem Handy“ (`ausdauer.py:527-531, 858-861`) und die Legende verschweigen es; im Training fehlt der Schalter „Karte aus“ (der GPS-Test hat ihn, `gps_test.py:536`). **Frage G-F1:** Hinweis + Schalter, Karte erst nach Antippen laden, oder Offline-Kacheln vorziehen (P7)? | mittel |
| G2 | `docs/recht/40_toms.md:30`, `80_store_freigaben.md:36-42` | „Keine Standortdaten“ / „Standortberechtigung, die wir weder brauchen noch begründen könnten“ widerspricht dem Stand: `pyproject.toml:129-131` trägt `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`, `INTERNET`, das Manifest `FOREGROUND_SERVICE_LOCATION`. **Frage G-F2:** Begründungstexte nachziehen (Store, TOMs, Datenschutzerklärung). | mittel (rechtlich) |
| G3 | `ui/views/ausdauer.py:239-245, 286-287` | `_empfangen` ist ein unbeobachteter Task: wirft `datei.schreiben` (Speicher voll) oder `_kilometer`, stirbt er **still**, die Strecke friert ein, `stoppen` unterdrückt die Ausnahme. | mittel |
| G4 | `ui/views/ausdauer.py:330` | Die DB-Zeile `strecke` entsteht nur in `stoppen`. Tötet Android den Prozess, liegt die `.jsonl` verwaist, kein Eintrag, keine Wiederherstellung (HRV hat ein Backup). **Frage G-F4:** beim Start verwaiste Dateien erkennen und nachträglich anlegen, oder bewusst verlieren? | mittel |
| G5 | `ui/geraete/flet_gps.py:121-123`, `core/strecke.py:331-335` | **Tempo 0 gilt als gültig**, aber flet_geolocator meldet „nicht verfügbar“ als `0.0` (auch Genauigkeit/Höhe). Ohne Doppler-Tempo (Netzwerk-Fix, manche Geräte, iOS −1) ist `steht` immer wahr → Strecke bleibt für immer 0. Pixel 10 liefert Tempo, andere Geräte ungeprüft; `speed_accuracy` (0 = fehlt) könnte unterscheiden. **Frage G-F3:** Rückfall auf reinen 10-m-Schritt? | mittel |
| G6 | `ui/geraete/flet_gps.py:117-118`, `ausdauer.py` | Fehler des Positionsstroms (Standort ausgeschaltet, Berechtigung entzogen) landen in `meldung`; `ausdauer.py` liest sie nie (`gps_test.py:195` schon). Ebenso wird der Fehlertext von `transport.hintergrund(...)` verworfen (`ausdauer.py:227-229`): scheitert der Vordergrunddienst, endet GPS bei Display aus stumm. **Frage G-F9:** Banner wie `warnung` im GPS-Test? | mittel |
| G7 | `ui/views/ausdauer.py:406-407` | `state.ausdauer = lauf` **vor** `await lauf.starten()`: wirft `starten`, bleibt ein halb gestarteter Lauf ohne `_takt` im State, die Ansicht zeigt „läuft“. | mittel |
| G8 | `ui/views/ausdauer.py:767-771`, `repositories.py:1886-1890`, `gps_test.py:340` | „Entfernen“ ist Soft-Delete, die Koordinatendatei bleibt unbegrenzt; kein Papierkorb, kein endgültiges Löschen (HRV hat `PAPIERKORB_TAGE`). Vorabtest-Dateien `vorabtest_*.jsonl` werden nie gelistet oder gelöscht. **Frage G-F5.** | niedrig |
| G9 | `core/strecke.py:311, 324-328, 346-347` | Genauigkeit `None` und `0.0` passieren den Filter als perfekt; nach Sprung/Lücke werden `_hoehen` und `_letzte_bewegung` nicht zurückgesetzt; beim Übergang in die Auto-Pause zählt der ganze `dt` samt 10 s Stillstand zur Bewegungszeit (im Test als bekannt vermerkt). | niedrig |
| G10 | `ui/geraete/flet_gps.py:75-79`, `strecken.py:141-142` | `use_msl_altitude` nicht gesetzt → Ellipsoidhöhe; `<ele>` im GPX liegt in Deutschland ≈ 45 m über NN. Höhenmeter (Differenzen) unberührt. **Frage G-F7:** MSL einschalten? | niedrig |
| G11 | `ui/geraete/flet_gps.py:73-84`, `gps.py:68-71` | Zweites `starten` ohne `beenden` ersetzt die Queue, der alte Konsument hängt; heute nur durch UI-Sperren verhindert. | niedrig |
| G12 | `data/strecken.py:63, 100` | `flush()` ohne `fsync` (übersteht App-Absturz, nicht Stromausfall); `Punkt(**werte)` ohne Typprüfung → TypeError bei handbearbeiteter Zeile. | niedrig |
| G13 | `ui/views/ausdauer.py:847-856`, `app.py:406-408` | „HRV-Auswertung öffnen“ prüft nur `hrv_recording_id`, nicht ob die Aufnahme noch existiert; nach Soft-Delete führt die Route ins Leere. | niedrig |
| G14 | `ui/views/ausdauer.py:234, 301-313` | Datei wird vor dem ersten Fix angelegt; bleibt der Fix aus, bleibt eine leere Datei (`file_path=""`). | niedrig |
| G15 | `ui/views/ausdauer.py:172-332`, `gps_test.py:59-203` | `AusdauerLauf`/`GpsTestLauf` (Dateischreiben, DB-Zeile, Tagebucheintrag, Übungsanlage) liegen in `ui/views`; das Pendant `Messlauf` liegt in `devices/`. Ohne flet nicht testbar (`importorskip`). | niedrig |
| G16 | `ui/views/ausdauer.py:444-476, 568`, `karte_strecke.py:88, 91` | Jede Sekunde neue `_gross`-Container statt Textwerte setzen; `rechner.punkte` baut die ganze Liste je Tick; `osm_ebenen()` zweimal aufgerufen. O(n) je Tick, bei 1 h vernachlässigbar. | niedrig |
| G17 | `uv.lock` ↔ `build/site-packages` | Entwicklung auf Flet 1.0.3, APK-Build auf 1.0.4; CLAUDE.md verlangt Gleichstand mit `flet-mcp`. | niedrig |
| G18 | `repositories.py:1883` | `strecke.title` + `titel_setzen` ohne Oberfläche — geplant oder Rest? **Frage G-F8.** Ebenso: Live-Karte folgt jede Sekunde, Wegwischen unmöglich — gewollt? **Frage G-F6.** | niedrig |

Positiv geprüft: keine Division durch null; leere Strecke abgefangen; Ereignis-Handler laufen bei Flet 1.0 im Loop (`put_nowait` loop-sicher); Dart-Seite kündigt den Stream bei `on_position_change=None`; Zeitbasis durchgehend UTC-aware; Haversine, Pace-Einheiten korrekt; Streckenrechner inkrementell.

### 3.4 HRV-Messung, Analyse, Rohdaten

Zurückschreiben von `titel`/`notiz`/`ereignisse` ist atomar (tmp + fsync +
`os.replace`), Whitelist verhindert Messwert-Änderungen, Schlüsselfolge und
unbekannte Felder bleiben; Crop/Abschnitte liegen nur im Sidecar. Kurze und
leere Messungen sind in allen Rechenwegen geschützt. Kein `flet`/`scipy` in
`hrv_core`. Live vs. Editor schreiben nie gleichzeitig dieselbe Datei.

| # | Stelle | Befund | Schwere |
|---|---|---|---|
| H1 | `hrv_core/ausschnitte.py:267`, `korrektur.py:842, 766` | `doc = _json_lesen(ziel) or {…}`: ein vorhandenes, aber gerade **nicht lesbares Sidecar** (defekt, halb synchronisiert, Rechte) wird still durch ein neues ersetzt — Korrekturen/Segmente aus praxis_gui wären weg. `zusatz_sichern` (`messung_detail.py:875`) fängt nur `OSError` und erfährt nichts. **Frage H-F2:** Schreiben verweigern und Hinweis zeigen? | mittel |
| H2 | `hrv_core/ausschnitte.py:199-201`, `ui/components/analyse.py:387` | LF/HF eines **Abschnitts** bzw. des Analysefensters „Abschnitt“ laufen über `fensterspektrum` → Raster auf `MAX_GRID_BINS` gedeckelt. Für Abschnitte länger als `LANG_AB_S` (≈ 67 min) gilt genau der Fehler, den ALGO 5 für die Gesamtmessung behob (LF/HF ×3,6 bei 4 h), plus ein Lomb über alle Schläge × 2000 Bins (Sekunden am Handy). **Frage H-F1:** langen Spektralweg auch dort, oder LF/HF für lange Abschnitte sperren („lieber Lücke“)? | mittel |
| H3 | `hrv_core/ausschnitte.py:190-201` | Atemfrequenz und LF/HF je Abschnitt rechnen auf `teil.t_s` (korrigierte Herzuhr, rückt hinter ausgeschlossenen Ketten zusammen) und ignorieren `teil.breaks` — Lücken und Nähte werden zusammengenäht, die Gesamtmessung macht es richtig. **Frage H-F4:** Nähte respektieren wie bei der Gesamtmessung? | mittel |
| H4 | `hrv_core/ppi.py` (`_gemerkt`) | Modulcache hält bis zu 4 `Recording`-Objekte samt `beats`/`ppi_pakete` stark referenziert, auch nach Verlassen der Ansicht; bei Stundenmessungen am Handy zweistellige MB. | niedrig–mittel |
| H5 | `hrv_core/ausschnitte.py:282-295, 231-248` | Beim Speichern werden alle Nicht-„gesamt“-Segmente mit `metrics: None, computed_utc: None, active: True, visible: True` neu geschrieben; praxis_gui-eigene Werte dieser Felder gehen verloren, `zusatz_lesen` liest sie nicht. **Frage H-F3:** durchreichen oder bewusst normieren? | niedrig |
| H6 | `ui/views/messung_detail.py:338` | `beschreibung = rec.notiz or eintrag.note`: eine in der Datei (praxis_gui) geleerte Notiz wird von der DB-Kopie überdeckt — „Datei ist die Wahrheit“ hier nicht ganz. Titel wird dagegen gespiegelt. **Frage H-F7.** | niedrig |
| H7 | `hrv_metrics_cache` | Wird im Code **nirgends** gelesen oder geschrieben (nur Migration 001); alle Kennzahlen werden bei jedem Öffnen neu gerechnet. CLAUDE.md beschreibt den Cache als tragendes Element. **Frage H-F5:** ungenutzt lassen (dann Doku anpassen) oder die Öffnungszeit der Detailansicht damit tragen? | niedrig |
| H8 | `ui/views/messung_detail.py:305-329, 385-409, 375, 1661` | Laden, Vorschläge, Kacheln (Atmung über bis zu 2000 Minutenfenster, SampEn bis 3000 Schläge) laufen synchron im Event-Loop beim Aufbau; laut `plan_analyse_leistung.md` bewusst so belassen. **Frage H-F6:** `hrv_core`-Rechnungen per `asyncio.to_thread` (flet-frei, thread-tauglich)? | niedrig |
| H9 | `ui/views/messung_detail.py:1361-1376` | `nachrechnen_planen` → `page.run_task(spaeter)` ohne Abbruch beim Verlassen: rechnet nach der Latenz für die tote Ansicht (kein Crash, `update()` unterdrückt). Live-Pendant ist über `state.live_ansicht` abgesichert. | niedrig |
| H10 | `ui/views/messung_detail.py:798-813` | Cache-Schlüssel der Abschnittswerte enthält weder `atem_modus` noch `pnn_ms`; nach Umschalten der Atemübung zeigt eine offene Ansicht alte Werte. | niedrig |
| H11 | `ui/views/messung_detail.py:385-409` ↔ `ausschnitte.py:192-198` | Atem-Median über Minutenfenster existiert doppelt (UI adaptiv mit Deckel, `ausschnitte` 15 s fest ohne Deckel). Gehört einmal nach `hrv_core`. | niedrig |
| H12 | `tests/test_frequenz.py:275` | Langer Spektralweg (ULF/VLF/LF/HF, ALGO 5) hat nur eine synthetische Reihe im Test (Toleranz 10 %), keine Referenzdatei unter `tests/golden/rr/` und keinen Vergleichswert aus praxis_gui/scipy. | niedrig |
| H13 | `hrv_core/ereignisse.py:337-355` | Jede Notiz liest und schreibt die ganze Rohdatei synchron im Event-Loop (MB bei Stundenmessungen); Absturz zwischen Rohdatei-Write und Sidecar-Update hinterlässt veraltetes `source_file_sha1` (praxis_gui hält Sidecar für veraltet, kein Datenverlust). | niedrig |
| H14 | `hrv_core/frequency.py:477-481` | `_lomb_hann` bei genau 2 Stützstellen: Hann an beiden Enden 0 → Division durch 0 → NaN im VLF-Teilspektrum (maskiert, kein Crash); durch Bandpolitik faktisch unerreichbar. | niedrig |
| H15 | Doku | `tests/golden/rr/README.md` („seit ALGO 4 werden verworfene Intervalle wieder aufgenommen“) ist seit ALGO 6 falsch (Vorgabe `sensor`). `messung_detail.py:1143-1145`: `crop_oeffnen` zeichnet doppelt. | niedrig |

### 3.5 Pläne, Notation, Timer, Profile, App-Hülle

Flet-1.0-API in diesem Bereich geprüft, keine falsche Nutzung. `spec_snapshot_json`
immer gesetzt, keine `UPDATE` auf `result_json`/Snapshot, Korrektur nur über
`replaces_entry_id`, `reihenfolge_setzen` lückenlos, Migration 010 Backfill
getestet, SQL ohne Nutzereingaben im Text.

| # | Stelle | Befund | Schwere |
|---|---|---|---|
| N1 | `core/units.py:51-62, 139-150, 166`, `result_spec.py:243` | `parse_dauer("1e400")` und sehr lange Ziffernfolgen liefern `inf`; `format_dauer` wirft dann `OverflowError` (reproduziert). `format_wert` fängt nur `TypeError/ValueError`. Ein solcher Wert im Zeitfeld (Plan, SpecForm) wird **gespeichert**, danach stürzen Plan- und Tagesansicht für diesen Tag bei jedem Aufbau ab, bis der Eintrag gelöscht ist. Gleiches Muster `core/timer.py:104-109` (`dauer_lesen("1,e400")`) → Absturz beim Speichern des Timer-Profils. | **hoch** |
| N2 | `core/units.py:100-104`, `spec_form.py:286` | `parse_sets("999999999x1")` baut `[wert] * anzahl` ohne Obergrenze (3·10⁶ Sätze in 0,03 s gemessen; 10⁹ ≈ 8 GB → OOM am Handy). Im Planblock gilt 1–50 (`plan.py:437`), in der Notation nicht. **Frage N-F2:** eine Obergrenze (Sätze, Wert, Zeit) für beide Eingabewege? | mittel |
| N3 | `ui/views/einstellungen.py:37-44`, `messung.py:240` | **Profilwechsel während laufender HRV-Messung** wird nicht verhindert; `aufnahme_eintragen` nimmt `state.profil.id` zum Speicherzeitpunkt → die Aufnahme landet beim neuen Profil. `state.py:267-273` setzt beim Wechsel `auspraegung_wahl`, `parameter_wahl`, `plan_offen`, `verlauf_metrik/_uebung`, `scroll_offsets` nicht zurück (meist harmlos). **Frage N-F1:** sperren, Profil im `Messlauf` merken oder Rückfrage? | mittel |
| N4 | `ui/views/profile.py:48-57`; ähnlich `plan.py:539-545`, `timer.py:875-882`, `uebung_detail.py:150-166` | `pop_dialog()` direkt gefolgt von `neu_zeichnen()` (dazwischen eine SnackBar) — das Muster, das `components/dialoge.py` als Ursache des „hängenden Dialogs“ beschreibt; der `Nachher`-Weg aus Commit 19b7436 ist hier nicht angewandt (die anderen drei nutzen `push_route`, Wirkung offen). **Frage N-F7:** `Nachher` als Regel für jeden Bestätigen-Dialog? | mittel |
| N5 | `data/repositories.py:172-178` ↔ `:1725-1727` | `ExerciseRepo.speichern` legt Tags mit `ON CONFLICT(name)` (case-sensitiv) an, `TagRepo.anlegen` prüft `COLLATE NOCASE`: über Editor/Paketimport entstehen „dehnung“ und „Dehnung“ nebeneinander. **Frage N-F3:** UNIQUE-Index `COLLATE NOCASE` per Migration? | niedrig |
| N6 | `data/repositories.py:742-770` | `ziel_setzen`/`eingabe_setzen` erhöhen `plan.revision`/`updated_at` nicht (`_beruehrt` fehlt), anders als `umbenennen`/`aktiv_setzen` — für „letzter Schreiber gewinnt“ unsichtbar. **Frage N-F5:** `plan.revision` als Anker für Items oder eigene Item-Revision? | niedrig |
| N7 | `ui/views/timer.py:178-186, 91-93` | Timer-Profil bearbeiten und speichern, während der Timer läuft: `lauf_fuer` ersetzt den Lauf, der Ticker vergleicht Stände zweier Läufe (möglicher Geister-Ton), danach stoppt der Timer still. **Frage N-F6:** warnen, blockieren oder weiterlaufen lassen? | niedrig |
| N8 | `ui/views/timer.py:201-202, 446` | `state.timer_aufgabe = True` vor `page.run_task`; schlägt es fehl, startet bis zum Neustart kein Ticker mehr. `timer_beobachter["ansicht"]` wird beim Verlassen nicht ausgetragen (5×/s Arbeit umsonst, kein Leak). | niedrig |
| N9 | `ui/views/plan.py:435` | `"²".isdigit()` ist wahr, `int("²")` wirft → Absturz im Handler „Sätze × Wert“ bei Unicode-Ziffern. | niedrig |
| N10 | `ui/views/app.py:424-428` | `zurueck`: `page.views.pop()` und dann `page.views[-1]` — bei nur einer Ansicht `IndexError` (ob Flet `on_view_pop` auf der Wurzel feuert, ungeprüft). | niedrig |
| N11 | `data/repositories.py:666-677, 928, 901` | `PlanRepo.speichern`: versteckte Items behalten alte `sort_order`, neue ab `versteckt` nummeriert → Duplikate möglich, kein Tiebreak; ein noch im Objekt enthaltenes verstecktes Item → `IntegrityError`. Einziger UI-Aufrufer schreibt leere Pläne. | niedrig |
| N12 | `data/repositories.py:1263-1268` | `wert_setzen` modernisiert `result`, ersetzt die Spec-Kopie aber nur bei fehlendem `feld_key`; Alt-Einträge vor M3 mit `scale`-Feld geraten in den Zustand, den `satz_anhaengen` vermeidet. | niedrig |
| N13 | `ui/views/plan.py:122-135, 431-441`, `_stellen` dreifach | Parse-Logik in `ui/` (`_zahl_lesen`, Sätze×Wert-Expansion mit Regel 1–50) dupliziert `core/units.parse_sets`; gehört als `parse_satz_eingabe(...)` nach `core/units` — dann sitzt auch die Obergrenze (N2) an einer Stelle. `timer.py:774` summiert in der UI. | niedrig |
| N14 | `repositories.py:881-885, 1172-1174`, `tag.py:284`, `plan.py:253`, `tag.py:74` | N+1: `verwendungen` lädt je Item den Plan; `heutiger_eintrag` je Zeile eine Session; Tagesansicht je Gruppe den Plan; Plan/Tag laden bei jedem Aufbau den ganzen Katalog mit Tags und Medien. Bei 33 Übungen egal. | niedrig |
| N15 | `config.py` | `physiologische_steuerung` wird nirgends abgefragt (korrekt, es gibt keine solche Funktion); ein Test, der `ist_aktiv("physiologische_steuerung")` in `solo` als False fixiert, fehlt. `app_setting darstellung:<profil-id>` bleibt nach Profil-Löschen stehen (**Frage N-F8**). | niedrig |

### 3.6 Behoben am 15.10.2026 (nur zur Einordnung)

- **H-Wischen** — `ui/components/zeitfenster.py`: Flets Drossel (`drag_interval`) verwirft Zwischenereignisse ohne Aufsummieren; `primary_delta` war nur der letzte Touch-Frame (≈ ⅙ der Bewegung). Jetzt zählt `local_delta` (Weg seit dem letzten gesendeten Ereignis). Siehe P15/T4.

---

## Entschieden

| Datum | Frage | Entscheidung |
|---|---|---|
| 14.10.2026 | GPS-Takt | Sekundentakt, keine Sparstufe (Ben). |
