# Web-Fassung — die App als statische Seite im Browser

Stand 15.11.2026. Vertrag für `scripts/web_bauen.py`, das Web-Profil (`config.WEB`), das
Register der Abzweigungen (`docs/web_abzweigungen.toml`), den Web-Weg von
`erweiterungen/flet_ble` und das Speichern im Browser (`ui/browserspeicher.py`).

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
uv run python scripts/web_bauen.py --basis /app/<ordner>/    # für einen Unterordner eines Servers
```

Ergebnis `dist/web/` mit `stand.json` (Version, Commit, `sauber`, `gepusht`, Basisadresse,
`ohne_cdn`, `archiv_geprueft`). Was das Skript über `flet build web` hinaus tut, steht in seinem Kopf; kurz:

| Schritt | Ohne ihn |
|---|---|
| `--no-cdn` | Pyodide käme von jsdelivr, Schriften von Google — Anfragen an fremde Server bei jedem Besuch |
| Basisadresse (`--base-url`) | die Seite findet CanvasKit und Pyodide nicht |
| Inline-Skripte der `index.html` nach `start-<n>.js` | eine strenge Content-Security-Policy blockiert sie, die Seite bleibt weiß |
| Ersatzschriften einlegen (`SCHRIFTEN`, mit Prüfsumme, beim Bauen geladen) | Flutter fragt die fehlende Schrift in Dauerschleife an (gemessen: über 1400 Anfragen je Minute und Tab); „→“ erscheint als Kästchen |
| Adressen mit „#“ (`--route-url-strategy hash`) | ein statischer Server kennt die Ansichten nicht: Neuladen in einer Unteransicht ist 404, und die aufgerufene Ansicht stünde im Protokoll des Servers |
| App-Archiv gegen das Repository prüfen (`archiv_befunde`; dazu `[tool.flet.app] exclude` in `pyproject.toml`) | `flet build` packt ganz `src/` ein — auch den Datenordner der Desktop-Vorschau (`src/trainingsapp/ui/.flet/`: Datenbank, Messungen, GPS-Strecken, Anhänge dieses Rechners). So am 14.11.2026 hochgeladen und wieder gesperrt |

Braucht die App ein Zeichen aus einer weiteren Schrift, nennt die Konsole des Browsers die
Datei (`assets/fonts/…`) — in `SCHRIFTEN` eintragen.

**Gebaut wird mit dem Python, das Flet für das Web wählt** (13.11.2026: Pyodide 314, also
Python 3.14) — APK und Tests laufen mit 3.12. Bisher ohne Befund; wer ein Verhalten nur im
Browser sieht, prüft das zuerst.

## 2. Was im Browser anders ist

**Das Web-Profil** (`config.WEB`, Ben, 14.11.2026) ist die eine Stelle, an der steht, was die
Web-Fassung anders hält als die App. Es gilt, wenn `config.im_browser()` wahr ist
(`sys.platform == "emscripten"`; am Rechner und in Tests `TRAININGSAPP_WEB=1`).

`WEB.ohne` (alter Name `config.NICHT_IM_BROWSER`) — `ist_aktiv` liefert dort für diese
Funktionen `False`:

| Funktion | Warum nicht |
|---|---|
| `update_pruefung` | fragte GitHub; eine Seite braucht kein Update |
| `paket_quellen` | der Netzzugriff der App (`urllib`) geht im Browser-Python nicht |
| `hrv_bewertung` | die Web-Fassung dient dem Hausaufgabenprogramm — Grenze des Patientenmodus: anzeigen ja, Messwerte einordnen nein (`docs/recht/00_zweckbestimmung.md`). Stand 14.11.2026 hängt in der Oberfläche nichts an dem Schalter |
| `geraete_sicherung` | Androids Geräte-Backup gibt es dort nicht |

`WEB.verweise` — die Karte „Rechtliches“ am Ende der Einstellungen: Impressum,
Datenschutzerklärung, Quelltext. Wer die Adresse der Web-Fassung direkt öffnet, kommt an keiner
anderen Seite der Praxis vorbei; das Impressum muss von der App aus erreichbar sein. In der
installierten App gibt es die Karte nicht.

`WEB.vorgaben` (Ben, 15.11.2026) — was im Browser gilt, solange die Person nichts gewählt hat:

| Vorgabe | Web-Fassung | App |
|---|---|---|
| `profilname` | Gast | Ich |
| `palette` | Nachtblau | Petrol |
| `helligkeit` | Hell | wie das System |

Wer die Seite öffnet, ist zu Gast; Name und Farben lassen sich unter Profil und Darstellung
ändern wie in der App. Eine weitere Vorgabe ist eine Zeile hier und in `WEB.vorgaben` und eine
Stelle, die `config.web_vorgabe(name, sonst)` fragt.

Dazu in `ui/app.py`: Bluetooth auch im Browser, **GPS nicht** (Kartenkacheln wären Anfragen an
fremde Server), und der Speicher im Browser (§5).

### Regel: Abzweigungen sind dokumentiert, gezählt und getestet

Ben, 14.11.2026: „Abzweigungen streng dokumentiert und getrackt, damit diese wirklich getestet
werden.“ Jeder Unterschied zwischen Web-Fassung und App muss in beiden Fassungen stimmen — und
niemand klickt beide bei jeder Änderung durch. Deshalb:

1. **Erst das Web-Profil.** Was sich als Wert ausdrücken lässt (eine Funktion aus, eine Vorgabe,
   ein Text, eine Liste), kommt nach `config.WEB` — nicht als `if im_browser()` in eine Ansicht.
2. **Sonst ins Register.** Jede Datei, die für den Browser abzweigt, steht in
   `docs/web_abzweigungen.toml`: Zahl der Stellen, was dort anders ist, und der Test, der den
   Web-Zweig durchläuft — oder der Gerätetest, wenn es nur im echten Browser zu sehen ist.
3. **Der Test zählt nach.** `tests/test_web_abzweigungen.py` vergleicht das Register mit dem
   Quelltext (Marken: `im_browser(`, `"emscripten"`, `_web`, `web_verweise(`, `web_vorgabe(`,
   `TRAININGSAPP_WEB`, das Wort `browserspeicher`, in Dart `kIsWeb`). Eine neue Abzweigung ohne Eintrag, eine falsche Zahl, ein Eintrag ohne Test
   oder ein Test, den es nicht gibt: Der Lauf scheitert, lokal und in der CI.
4. **Wer eine neue Marke erfindet** (eine andere Art, den Browser zu erkennen), trägt sie im Test
   und im Kopf des Registers nach — sonst zählt niemand sie.

Was das Register nicht kann: Es beweist, dass es einen Test gibt, nicht, dass er gut ist. Und was
nur über einen Schalter aus `WEB.ohne` läuft, zählt es nicht als Abzweigung — dafür steht die
Tabelle oben (der Test prüft, dass jede Funktion aus `WEB.ohne` dort steht).

**Was noch fehlt** (Stand 15.11.2026):

- **`hrv_bewertung` wird in der Oberfläche nirgends abgefragt — und muss es derzeit nicht.**
  Ben, 14.11.2026 (`docs/recht/00_zweckbestimmung.md`, „HF-Auswertung und DFA α1“): Was eine
  Messung ausgibt und die Person selbst übernimmt (Ruhe-HF, HFmax), und Zahlen ohne Schwelle
  (Wochenlast, Tests) sind Anzeige, keine Deutung, und bleiben. DFA α1 bleibt in Web-Fassung
  und App sichtbar und ist überall als „experimentell“ gekennzeichnet (`core/experimentell.py`
  — keine Abzweigung für den Browser). Der Schalter bleibt für alles, was Messwerte künftig
  einordnen würde.
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

## 5. Speichern im Browser

Ben, 15.11.2026: „Die Speicherfähigkeit im Browser müsste herausgearbeitet werden.“ Bis dahin
lag alles im Arbeitsspeicher des Tabs und war mit dem Neuladen weg.

**Was gespeichert wird:** das ganze Datenverzeichnis (`config.datenverzeichnis()`, im Browser
`/home/pyodide/.trainingsapp`) — Datenbank, Messungen, Anhänge, Dateien aus Paketen. **Wo:** in
der IndexedDB des Browsers, unter dem Namen dieser Seite, auf diesem Gerät. **Wohin nicht:** an
keinen Server; die IndexedDB ist kein Netzweg, und die Content-Security-Policy der Seite
(`connect-src 'self'`) bleibt, wie sie ist.

**Wie** (`ui/browserspeicher.py`): Das Verzeichnis liegt auf IDBFS, Emscriptens Dateisystem,
das im Arbeitsspeicher arbeitet und sich auf Zuruf mit der IndexedDB abgleicht. SQLite und die
Dateizugriffe der App bleiben, wie sie sind.

| Wann | Was |
|---|---|
| Start, **vor** dem Öffnen der Datenbank (`ui/app.py:einstieg`) | einhängen, Sperre nehmen, Gespeichertes holen |
| alle 2 s, solange die Seite offen ist | schreiben — nur wenn sich im Verzeichnis etwas geändert hat (Zahl, Größe, jüngste Änderung der Dateien) und in SQLite keine Transaktion offen ist |
| Tab geht in den Hintergrund | sofort schreiben |
| „Alles löschen“ (Einstellungen → Daten und Sicherung) | die IndexedDB der Seite entfernen; bis zum Schließen oder Neuladen schreibt der Tab nichts mehr |

**Entschieden von Ben am 15.11.2026: „von selbst speichern“.** Ohne Rückfrage — so stand es
hier seit dem 14.11.2026 („Abgleich mit IndexedDB und ein Knopf „Alles löschen“ für fremde
Geräte“). Die Seite ist ein Trainingstagebuch; wer etwas einträgt, will es beim nächsten Besuch
wiederfinden. Verworfen: beim ersten Besuch fragen — eine Rückfrage vor dem ersten Blick auf
die App.

**Was schiefgehen kann:**

- **Zwei Tabs.** Jeder Tab hat sein eigenes Python; der zweite überschriebe den Stand des ersten.
  Der erste Tab hält eine Sperre des Browsers (Web Locks, `trainingsapp-speicher`); der zweite
  zeigt den gespeicherten Stand, sagt beim Start „Hier wird nicht gespeichert“ und schreibt nicht.
- **Der Browser lässt es nicht zu** (Speicher voll, gesperrt): Die App läuft weiter, sagt es beim
  Start und unter „Daten und Sicherung“.
- **Die App startet mit dem Gespeicherten nicht** (kaputte Datei, misslungene Migration): Statt
  einer weißen Seite erscheint „Die gespeicherten Daten lassen sich nicht öffnen“ mit dem Knopf
  „Gespeichertes löschen“ (`ui/app.py:notausgang`) — sonst bliebe die Seite auf diesem Gerät
  für immer kaputt.
- **Der Tab wird geschlossen, bevor geschrieben ist:** Bis zu 2 s können fehlen. Ein „Tab wird
  geschlossen“ meldet der Browser dem Python nicht verlässlich.
- **Der Browser räumt auf.** Websitedaten löschen, privates Fenster, wenig Platz, Safari nach
  sieben Tagen ohne Besuch: Dann ist alles weg. Das ist so gewollt (§0) und steht in der App
  (Karte „Speicher im Browser“, das „i“).

**Die Datenbank läuft auch im Browser im WAL-Modus** (`data/db.py`): Gespeichert werden
`trainingsapp.db`, `-wal` und `-shm`. Der Abgleich liest alle Dateien in einem Zug und schreibt
sie in einer Transaktion der IndexedDB; beim nächsten Start liest SQLite das WAL wie nach einem
Absturz. Ein frischer Stand sind rund 1,8 MB (fast alles im WAL).

**Gemessen** (15.11.2026, kopfloses Chromium 156 am Laptop, Probekopie des Builds mit dem
Quelltext als App-Archiv, hinter der Content-Security-Policy des Servers):

| Probe | Ergebnis |
|---|---|
| erster Besuch | IndexedDB `/home/pyodide/.trainingsapp`, 3 Dateien, 1 795 944 Bytes; keine Anfrage an fremde Server, kein CSP-Verstoß |
| Browser beenden, neu starten | dieselbe Datenbank (Zeitstempel unverändert), nicht neu angelegt |
| Schalter umlegen, 4 s warten, neu laden | der Schalter steht, wie er gestellt wurde |
| „Alles löschen“ → bestätigen | IndexedDB der Seite ist weg; eine Änderung danach wird nicht gespeichert; nach dem Neuladen frischer Stand |
| zweiter Tab | zeigt „… in einem zweiten Tab offen, und dort wird gespeichert“ |

**Nicht gemessen:** am Handy; Firefox und Safari; wie lange das Schreiben während einer langen
Messung dauert; ob der Wechsel in den Hintergrund im Browser gemeldet wird; Anhänge (Foto,
Ton) — Gerätetest T140.

**Recht:** Die Daten bleiben auf dem Gerät der Person; die Praxis bekommt nichts davon. Dass
die Seite etwas im Browser ablegt, muss in der Datenschutzerklärung der Praxis stehen, **bevor**
ein Build mit Speicher hochgeladen wird (privates Repository der Homepage, ADR-0024, Nachtrag
„Speichern im Browser“).
