# Planung: Diagnosemodus (17.10.2026)

Ben, 17.10.2026 (über die Auswertung eigener Messungen in hrv-research): In den
Einstellungen soll es eine **Diagnosefunktion** geben, die mehr Akku kosten darf und
dafür ausführlicher protokolliert und prüft. **Noch nicht bauen** („wir machen das aber
noch nicht“) — das hier ist der Plan. Offene Entscheidungen stehen im Katalog
`docs/offene_fragen.md` (P30), der Anlass als Befund H18.

---

## 1. Anlass: die Neuverbinden-Schleife (H18)

Nach einem Neuverbinden durch den Watchdog reißt der Datenstrom nach etwa 2 s wieder
ab; die App verbindet dann im festen 16-s-Takt neu (8 s ohne Daten, 3 s Pause,
Neuaufbau, etwa 2 s Daten) — rund 80 % der Messung fehlen. Die angekommenen Schläge
sind sauber: kein Sensorfehler, sondern die Übertragung.

Warum es nicht eskaliert (`devices/polar.py`): Jedes Paket ruft `_daten_da`, das
`_fehlversuche` auf 0 setzt und die Warnung des Watchdogs zurücknimmt. Der nächste
Versuch ist darum immer Versuch 1 mit `wartezeit(1)` = 3 s, und keine Warnung bleibt
stehen. Das heutige Protokoll zeigt die Ursache nicht: nur die letzten
`PROTOKOLL_ZEILEN` = 500 Zeilen, Zeiten als `%H:%M:%S` (ohne Datum, ohne
Millisekunden, nicht auf `t_wall_s` der Messung zu legen), beim Trennen nur der Text
der Plattform, keine Pakete.

**Unabhängig vom Diagnosemodus** (Vorschlag, kostet keinen Akku): `_fehlversuche` erst
nach einer stabilen Phase zurücksetzen (etwa 30 s durchgehend Daten), die Schleife
erkennen (mehrmals Neuverbinden mit nur kurzen Datenstücken) und eine Warnung zeigen,
die stehen bleibt — „Die Verbindung bricht immer wieder ab (5 × in 2 min): Gurt
anfeuchten, Polar Flow oder eine Uhr trennen, Energiesparen des Handys prüfen“.

## 2. Was es heute gibt

| Was | Wo |
|---|---|
| Protokoll der Verbindung (deque, 500 Zeilen), Watchdog 1 Hz (Warnung nach 3 s, Neuverbinden nach 8 s), Pause `min(3·n, 10)` s | `devices/polar.py` |
| `sensor_<ts>_diagnose.txt` neben der Messdatei, beim Stopp geschrieben — Kopf mit App, Gerät und Adresse, Profil, Status | `devices/messlauf.py`, `core/hrv_export.diagnose_text` |
| Diagnose-Symbol bei der Gerätekopplung: die letzten Zeilen, Teilen | `ui/views/messung.py` (v0.2.2) |
| Messungs-Export und Forschungsexport packen `_diagnose.txt` mit | `core/hrv_export.zugehoerige_dateien` |
| Trennen mit Begründung der Plattform (Text, kein Code); RSSI nur beim Suchen | `erweiterungen/flet_ble` (`connection_state.reason`, Scan) |
| Akku und Ladezustand des Handys, Energiesparmodus | Flet `Battery` (`get_battery_level`, `get_battery_state`, `is_in_battery_save_mode`) |
| App im Vordergrund | Lebenszyklus der Seite (`AppState.im_vordergrund`) |

## 3. Was der Modus tut

1. **Ganzes Protokoll, laufend in die Datei** — nicht nur die letzten 500 Zeilen und
   nicht erst beim Stopp (ein Absturz verliert sonst gerade das Interessante). JSON
   Lines neben der Messdatei, je Zeile: monotone Uhr (dieselbe Domäne wie
   `t_capture`, also auf `t_wall_s` der Messung umzurechnen), UTC mit Datum und
   Millisekunden, Quelle, Art, Text.
2. **Wer getrennt hat:** Gerät bzw. Android (Begründung **und Code** — die Erweiterung
   reicht heute nur den Text durch), die App selbst, der Watchdog (Grund, Zähler,
   Wartezeit, Länge der Lücke).
3. **Rohmitschnitt** jedes Pakets (0x2A37, PMD): Hex und monotone Ankunftszeit, JSON
   Lines. In den Flags von 0x2A37 steckt der Hautkontakt — so trennt die Auswertung
   Sensor- von Übertragungsfehlern. Vorbild: praxis_gui, `docs/ble_uebertragung_pruefen.md`
   (Rohmitschnitt und Prüfbericht in vier Ebenen). Am besten **ein gemeinsames Format**,
   damit eine Auswertung beide Apps liest (P30). Umfang beim H10 etwa ein Paket je
   Sekunde — unter 1 MB je Stunde.
4. **Zustandsproben** in festem Abstand (Vorschlag 30 s), soweit Flet und Android es
   hergeben: Signalstärke (RSSI der Verbindung — `readRssi`, neu in der Erweiterung),
   Akku von Gurt und Handy, Bildschirm an/aus, Energiesparmodus, Doze/Leerlauf, App im
   Vordergrund, Akku-Optimierung für die App an/aus (die letzten drei über Androids
   `PowerManager` — neu in der Erweiterung).
5. **Schleife erkennen** (Abschnitt 1) — im Modus zusätzlich mit allen Zahlen im
   Protokoll.
6. **Prüfen:** ein **Vorabtest** vor der Messung (Berechtigungen, Akku-Optimierung,
   Akku des Gurts, 30–60 s Probeempfang mit Paketrate und Lücken) und/oder ein
   **Prüfbericht** nach der Messung aus Mitschnitt und Messdatei (Ebenen A–C wie in
   praxis_gui; D, der Vergleich mit einem zweiten Gerät, nur mit zweitem Gurt).
7. **Schalter** in den Einstellungen, Vorgabe aus; solange er an ist, ein sichtbarer
   Hinweis in der Messansicht und in der Benachrichtigung. Ob er sich selbst wieder
   abschaltet, entscheidet Ben (P30).

## 4. Grenzen

- **Kein GPS** im Protokoll und keine Adressen **fremder** Geräte in der Nähe — beim
  Suchen nur das gewählte Gerät protokollieren (Regel 0, `docs/plan_gps.md` §0).
- Das Protokoll nennt Name und Adresse des **eigenen** Gurts. Es bleibt auf dem Handy;
  hinaus geht es nur ausdrücklich (Teilen, Export) — dort ein Hinweis darauf.
- Keine neue Netzverbindung; der Modus schreibt nur lokal.
- **Folgen außerhalb der App:** hrv-core (`deid`, `deid_export`) und hrv-research
  (`scripts/einlesen.py`) nehmen `_diagnose` heute nicht mit. Soll die Auswertung es
  lesen, müssen beide es **de-identifiziert** übernehmen (Adresse pseudonymisieren,
  Gerätename kürzen) — Änderung dort, nicht hier.

## 5. Stufen (Vorschlag)

| Stufe | Inhalt |
|---|---|
| 0 | H18 beheben, auch ohne Modus: Zähler erst nach stabiler Phase zurücksetzen, Schleife erkennen, Warnung stehen lassen |
| 1 | Protokoll laufend als Datei, Zeitstempel mit Datum, Millisekunden und monotoner Uhr, Urheber und Code beim Trennen (Erweiterung: Code durchreichen) |
| 2 | Rohmitschnitt in gemeinsamem Format (Vertrag in hrv-core, P30) |
| 3 | Zustandsproben (Flet `Battery`; Erweiterung: RSSI, `PowerManager`) |
| 4 | Vorabtest und Prüfbericht |
| 5 | Schalter, Hinweis, Selbstabschaltung; Nachtrag in `docs/recht/40_toms.md` |

Betroffen: `devices/polar.py`, `devices/messlauf.py`, `core/hrv_export.py`,
`erweiterungen/flet_ble` (Dart und Kotlin — neue APK, Ben baut sie selbst),
`ui/views/einstellungen_hrv.py`, `ui/views/messung.py`; in hrv-core Format und
Prüfbericht, falls gemeinsam.
