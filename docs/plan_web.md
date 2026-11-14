# Web-Fassung — die App als statische Seite im Browser

Stand 14.11.2026. Vertrag für `scripts/web_bauen.py`, `config.NICHT_IM_BROWSER` und den
Web-Weg von `erweiterungen/flet_ble`.

## 0. Wozu

Ben, 13.11.2026: Die App soll auch **im Browser** laufen, am Smartphone und am Laptop —
„als Demo … um zu demonstrieren oder für schnelle Übungen, um ein Hausaufgabenprogramm, für
das man die App nicht extra installieren will, anzuschauen und zu üben“. **Ohne Konten.** Was
im Browser gespeichert wird, darf mit dem Browserspeicher verschwinden. Bluetooth nur, weil
die Messdaten das Gerät nicht verlassen.

Die Web-Fassung ist **dieselbe App aus demselben Quelltext**: `flet build web` erzeugt eine
statische Seite, in der Flutter zeichnet und Python über Pyodide (WebAssembly) im Browser
läuft. Ein Server liefert nur Dateien aus — er rechnet nichts, speichert nichts, bekommt nichts
zurück. Flets zweiter Web-Modus (Python auf dem Server) ist **nicht** gemeint und nicht gewollt:
Er hielte Daten der Nutzer auf einem Server.

Wo sie liegt und wie sie dorthin kommt, steht nicht hier, sondern beim Server der Praxis
(privates Repository der Homepage, ADR-0024). Dieses Repository liefert nur den Ordner.

## 1. Bauen

```bash
uv run python scripts/web_bauen.py --basis /                 # lokal: uv run flet serve dist/web
uv run python scripts/web_bauen.py --basis /app/<ordner>/    # für einen Server
```

Ergebnis `dist/web/` mit `stand.json` (Version, Commit, `sauber`, `gepusht`, Basisadresse,
`ohne_cdn`). Was das Skript über `flet build web` hinaus tut, steht in seinem Kopf; kurz:

| Schritt | Ohne ihn |
|---|---|
| `--no-cdn` | Pyodide käme von jsdelivr, Schriften von Google — Anfragen an fremde Server bei jedem Besuch |
| Basisadresse (`--base-url`) | die Seite findet CanvasKit und Pyodide nicht |
| Inline-Skripte der `index.html` nach `start-<n>.js` | eine strenge Content-Security-Policy blockiert sie, die Seite bleibt weiß |
| Ersatzschriften einlegen (`SCHRIFTEN`, mit Prüfsumme, beim Bauen geladen) | Flutter fragt die fehlende Schrift in Dauerschleife an (gemessen: über 1400 Anfragen je Minute und Tab); „→“ erscheint als Kästchen |

Braucht die App ein Zeichen aus einer weiteren Schrift, nennt die Konsole des Browsers die
Datei (`assets/fonts/…`) — in `SCHRIFTEN` eintragen.

**Gebaut wird mit dem Python, das Flet für das Web wählt** (13.11.2026: Pyodide 314, also
Python 3.14) — APK und Tests laufen mit 3.12. Bisher ohne Befund; wer ein Verhalten nur im
Browser sieht, prüft das zuerst.

## 2. Was im Browser anders ist

`config.im_browser()` (`sys.platform == "emscripten"`; am Rechner `TRAININGSAPP_WEB=1`) und
`config.NICHT_IM_BROWSER` — `ist_aktiv` liefert dort für diese Funktionen `False`:

| Funktion | Warum nicht |
|---|---|
| `update_pruefung` | fragte GitHub; eine Seite braucht kein Update |
| `paket_quellen` | der Netzzugriff der App (`urllib`) geht im Browser-Python nicht |
| `hrv_bewertung` | die Web-Fassung dient dem Hausaufgabenprogramm — Grenze des Patientenmodus: Zahlen und Kurven, keine Deutung (`docs/recht/00_zweckbestimmung.md`) |
| `geraete_sicherung` | Androids Geräte-Backup gibt es dort nicht |

Dazu in `ui/app.py`: Bluetooth auch im Browser, **GPS nicht** (Kartenkacheln wären Anfragen an
fremde Server).

**Was noch fehlt** (Stand 14.11.2026, alles vor einem öffentlichen Start):

- **Nichts bleibt.** Die Datenbank liegt im Arbeitsspeicher des Tabs; nach dem Neuladen sind
  Einträge, Messungen und Einstellungen weg. Gebraucht: Abgleich mit IndexedDB und ein Knopf
  „Alles löschen“ für fremde Geräte.
- **`hrv_bewertung` wird in der Oberfläche noch nirgends abgefragt** — der Schalter ist aus,
  die Deutungen sind trotzdem zu sehen. Das ist dieselbe Arbeit wie der Patientenmodus.
- **Pakete laden:** ein Netzadapter für den Browser; für private Pakete fehlt der Laufzeit
  `hashlib.scrypt` (`core/privat.moeglich()` meldet es).
- Kamera, Mikrofon und Ortung hängen am Server: Eine `Permissions-Policy` kann sie sperren.

## 3. Bluetooth im Browser (Web Bluetooth)

Derselbe `FletBle`-Dienst; der Web-Teil von flutter_blue_plus 1.36.8 ist im Build. Es geht in
**Chrome und Edge** (Android, Windows, macOS; Chromium unter Linux nur mit
`--enable-features=WebBluetooth`), nicht in Firefox, nicht in Safari, auf keinem iPhone — die
Suche sagt es dann. Nur über HTTPS oder `localhost`.

Der Weg der Messdaten: Sensor → Bluetooth des Geräts → Browser → Python im Browser. Ein
Server sieht davon nichts.

Drei Fallen, alle am Verity Sense gefunden (13./14.11.2026) und im Code beschrieben:

1. **Kein Scan.** `scan` öffnet das Auswahlfenster des Browsers (`_scanWeb`). Dabei müssen
   die Dienste genannt werden, die die App später anspricht (`_webDienste`: Herzfrequenz,
   Batterie, Polar PMD) — Web Bluetooth gibt sonst nach dem Verbinden nichts frei. **Ein
   neuer Dienst gehört in diese Liste.**
2. **Abonnieren am Kern vorbei.** Der Web-Teil bestätigt `setNotifyValue` nie; der Kern
   wartet 15 s und hält so lange die Sperre für alle BLE-Aufrufe (`_abonnieren`,
   `_subscribeWeb`).
3. **Keine Zahlen über 4 294 967 295 zwischen Dart und Python.** Die Web-Fassung ist
   JavaScript (dart2js): Das Verpacken einer größeren Ganzzahl wirft, das Ereignis geht
   **still** nie hinaus — der Zeitstempel in jedem Messpaket war so eine Zahl (`_zeit`,
   `FletBleTransport._ganz`, `_seit_ms`). **Gilt für jede Erweiterung und beide Richtungen.**

Was es im Browser nicht gibt: Vordergrunddienst und Benachrichtigung (die Messung läuft, solange
der Tab vorn ist), Kopplung aus der App (der Verity Sense muss einmal in den
Bluetooth-Einstellungen des Geräts gekoppelt werden), MTU-Anfrage. Ein Abriss der Verbindung
fällt erst dem Watchdog auf — der Web-Teil meldet Trennungen nicht.

## 4. Geprüft und nicht geprüft

Geprüft (kopfloses Chromium, Laptop; Verity Sense in Chromium mit Schalter): Start,
Migrationen, Katalog, Üben mit Eintrag, Stoppuhr, Einstellungen, Paketmanager; Puls im
Sekundentakt und Pulsintervalle; keine Anfrage an fremde Server von der Hauptseite; die Seite
unter `default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'
'unsafe-inline'; …` ohne Verstoß.

Nicht geprüft: Bluetooth am Handy über HTTPS, H10 mit EKG, iPhone, Videos und Bilder aus
Paketen, lange Messungen — Gerätetest T139.
