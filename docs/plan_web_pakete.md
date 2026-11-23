# Web-Fassung: Pakete per Link laden, auch private

Stand 23.11.2026 — **Stufen 0–5 gebaut und im Browser gemessen** (§6); am Handy offen
(Gerätetest T155), auf dem Server erst nach einem neuen Web-Build. Ergänzt `docs/plan_web.md`
(„Was noch fehlt“: „Pakete laden: ein Netzadapter für den Browser; für private Pakete fehlt
der Laufzeit `hashlib.scrypt`“). §1–§4 sind der Plan, wie er vor dem Bauen stand; wo das
Gebaute abweicht, steht es in §6.

## 0. Wozu

Ben, 23.11.2026: Ein privates Paket für eine Person (ein Kurs, ein bis zwei Pläne, laufend
nachgebessert — `trainingsapp-inhalte`, `pakete/privat/…`) soll sich **per Link für die
Web-Fassung freigeben** lassen. Die Person öffnet einen Link, gibt den Code ein und übt im
Browser, ohne die App zu installieren. Bessert Ben das Paket nach, kommt der neue Stand dort an.

Vorgaben, die bleiben (Ben, 12.11.2026): nichts über die Person auf dem Server; gespeichert
wird nur im Browser; der Code bleibt bei 8 Zeichen.

## 1. Was heute geht und was nicht

| Weg | App | Web-Fassung | Woran es hängt |
|---|---|---|---|
| Standardpaket | ja | ja | liegt im App-Archiv (`data/seed/standard.toml`) — kein Netz, kein Code |
| Paket aus einer **Datei**, öffentlich | ja | ja (laut Code; nicht im Browser nachgeprüft) | `views/pakete.py`: `pick_files(with_data=True)` gibt im Browser die Bytes |
| Paket aus einem **Link**, öffentlich | ja | **nein** | `link_importieren` → `asyncio.to_thread(link_lesen)` → `urllib` (`core/paketquelle._laden`); `urllib` hat im Browser-Python keinen Netzweg |
| Quellen, Updates beim Start | ja | **nein** | `paket_quellen` steht in `WEB.ohne` (`config.py:145`) |
| **Privates** Paket (Datei oder Link) | ja | **nein** | `core/privat._schluessel` braucht `hashlib.scrypt`; `privat.moeglich()` ist im Browser falsch |

Was schon passt:

- **Der Lader ist austauschbar.** `link_lesen`, `paket_laden`, `pruefen` nehmen `laden:
  Callable[[str], bytes]`; `link_importieren` reicht `laden` durch. Der Kern muss für den
  Browser nicht umgebaut werden.
- **Derselbe Server.** Die Pakete liegen unter `https://trainingsapp.osteo-ebert.de/pakete/`,
  die Web-Fassung unter derselben Adresse — die Content-Security-Policy (`connect-src 'self'`,
  `plan_web.md` §4) erlaubt das Laden, ohne dass sie gelockert wird.
- **Der Code ist nach dem Import gemerkt** (`package.access_json`) und liegt mit der Datenbank
  in der IndexedDB — Updates entschlüsseln sich von selbst, wie in der App.

## 2. Entwurf

### 2.1 Netz im Browser: erst holen, dann lesen

Im Browser gibt es nur `fetch` — und das ist asynchron, der Kern liest synchron. Statt den Kern
umzuschreiben, holt die Oberfläche **vorab**:

```
ui/browsernetz.py            (neu, nur im Browser — wie ui/browserspeicher.py)
  async holen(url, grenze) -> bytes      js.fetch, same-origin, ohne Zugangsdaten, mit Obergrenze
  async mit_netz(funktion) -> Ergebnis   ruft funktion(laden) auf; laden() liefert Geholtes und
                                         wirft für eine noch fehlende Adresse `Fehlt(url)`;
                                         dann holen und noch einmal — bis nichts mehr fehlt
```

`mit_netz` trägt jeden Weg des Kerns, ohne ihn zu kennen: `link_lesen` braucht eine Adresse,
`pruefen` zwei (Standdatei, dann Paket). Höchstens eine Handvoll Runden, dann Abbruch mit
Meldung. In der App bleibt alles, wie es ist (`asyncio.to_thread` + `urllib`).

Regeln für `holen`:

- **Nur der eigene Server.** Eine Adresse mit anderem Ursprung lehnt die Web-Fassung mit einem
  Satz ab („Im Browser lädt die Seite Pakete nur von diesem Server“) — die CSP blockierte sie
  ohnehin, und „keine Anfrage an fremde Server“ (`plan_web.md` §4) bleibt wahr.
- `https` wie in `netz.verschluesselt`; Weiterleitungen folgt `fetch` nur innerhalb des
  Ursprungs (`redirect: "error"` oder die Zieladresse prüfen — in Stufe 0 klären).
- Obergrenze wie `MAX_PAKET_BYTES`; für ZIP eine **eigene, kleinere Grenze im Browser**
  (alles geht dort durch den Arbeitsspeicher) — Wert aus Stufe 0.

### 2.2 scrypt im Browser

Das Dateiformat bleibt (`TAPRIV`, Verfahren 1): Was heute auf dem Server liegt, muss sich im
Browser öffnen lassen, sonst bräuchte jedes private Paket zwei Fassungen.

| Weg | Dafür | Dagegen | Stand |
|---|---|---|---|
| **A: `cryptography` aus Pyodide** (`hazmat…kdf.scrypt.Scrypt`) | fertig, geprüft, OpenSSL in WebAssembly; steht im `pyodide-lock.json` des Builds (47.0.0, braucht `cffi`, `six`, `pycparser`) | liegt **nicht** im gebauten Ordner (`dist/web/pyodide/` hat nur `micropip`, `packaging`) — muss mit `--no-cdn` eingepackt werden; Größe und Ladezeit unbekannt | **empfohlen**, in Stufe 0 messen |
| B: scrypt in JavaScript als eigene Datei (`start-…js`-Art, `script-src 'self'`) | klein, schnell | fremder Krypto-Code, den wir pflegen und prüfen müssen; Brücke Python ↔ JS | Ausweich |
| C: scrypt in reinem Python | kein neues Paket | N = 2¹⁵ heißt rund eine Million Salsa20/8-Runden — geschätzt Minuten im Browser (nicht gemessen) | nur, wenn A und B scheitern |
| D: zweites Verfahren im Format (PBKDF2 über WebCrypto) | Bordmittel des Browsers | schwächer gegen Durchprobieren, zwei Fassungen je Paket | **nicht** |

`core/privat._schluessel` bekommt dafür eine Stelle, an der sich die Ableitung einhängen lässt
(`hashlib.scrypt`, sonst `cryptography`), `moeglich()` fragt beide. Kein `im_browser()` im
Kern — es zählt, was die Laufzeit kann. Ein Test rechnet mit beiden Wegen dieselben
Schlüssel aus (fester Code, festes Salz).

### 2.3 Der Link für die Person

Heute: Link auf `…/pakete/p/<ordner>/paket.json` + Code; in der App „Importieren → Link“.
Für den Browser soll **ein Link** genügen:

```
https://trainingsapp.osteo-ebert.de/#/paket/p/<ordner>
```

- Die Web-Fassung startet, sieht die Route, lädt `/pakete/p/<ordner>/paket.json` (bzw.
  `.zip`), fragt nach dem **Code**, zeigt die übliche Rückfrage und hinterlegt die Adresse am
  Paket.
- Hinter „#“, weil der Browser diesen Teil nie an den Server schickt (`plan_web.md` §1) — der
  Ordner steht dann nur in der Anfrage nach der Paketdatei selbst, wie heute.
- Der Code kommt **nicht** in den Link (zwei Schlösser, getrennt weitergeben).
- Ist das Paket schon da: nichts fragen, zur Paketseite.
- `trainingsapp-paket bauen` schreibt die Zeile „Im Browser: …“ zusätzlich auf die
  Zugangskarte, wenn es die Adresse der Web-Fassung kennt (`--web-url`, im Inhalte-Repo aus
  `.env`).

### 2.4 Updates

Beim Start fragt die Web-Fassung für Pakete **mit hinterlegtem Datei-Link** die Standdatei
(`paket.stand.json`, wenige Bytes) und lädt bei neuer Version das Paket — derselbe Weg wie in
der App (`paketquelle.pruefen`), über `mit_netz`. Öffentliche **Quellen** (Index) bleiben im
Browser vorerst aus: `paket_quellen` wird dafür in zwei Schalter geteilt (`paket_links` an,
`paket_quellen` aus) oder `WEB.ohne` behält ihn und der Link-Weg fragt ihn nicht ab — beim
Bauen entscheiden, die Tabelle in `plan_web.md` §2 zieht mit.

## 3. Stufen

Jede Stufe endet mit grüner CI, Eintrag im Register (`docs/web_abzweigungen.toml`), der Zeile
in `plan_web.md` und einem Web-Foto.

| Stufe | Was | Fertig, wenn |
|---|---|---|
| **0 Probe** | Im kopflosen Chromium am aktuellen Build messen, nichts einbauen: (a) `js.fetch` einer Datei unter `/pakete/` hinter der CSP des Servers, binär, mit Größe; (b) `cryptography` mit `--no-cdn` einpacken — geht das mit `flet build web`, wie groß, wie lange lädt es; (c) scrypt N = 2¹⁵ im Browser: Zeit und Speicher, auch am Handy; (d) läuft `asyncio.to_thread` in Pyodide überhaupt (der Datei-Import benutzt es); (e) liest Flet beim Start die Route hinter „#“ | Zahlen stehen in diesem Plan; Weg A, B oder C ist gewählt |
| **1 Link, öffentlich** | `ui/browsernetz.py`, `link_importieren` im Browser über `mit_netz`; Ablehnung fremder Ursprünge; „Importieren → Link“ im Browser sichtbar | ein öffentliches JSON-Paket vom eigenen Server ist im Browser importiert; Tests mit einem falschen `laden` für `mit_netz` (eine, zwei Adressen, Fehler, Abbruch nach n Runden) |
| **2 Privat** | scrypt nach Stufe 0; `privat.moeglich()` im Browser wahr; Code-Dialog bei Datei und Link | „Qigong Basis“ vom Server öffnet sich im Browser mit seinem Code; falscher Code → „Der Code passt nicht“ |
| **3 Ein Link** | Route `#/paket/p/<ordner>`; Zeile auf der Zugangskarte (`paket_werkzeug`) | Link in frischem Browser → Code → Paket da; zweiter Aufruf fragt nicht mehr |
| **4 Updates** | Standdatei beim Start, neue Fassung mit gemerktem Code; was die Person geändert hat, bleibt (Abgleich je Feld wie in der App) | Version im Inhalte-Repo heben, veröffentlichen, Seite neu laden → Update steht da |
| **5 Dateien** | ZIP-Pakete (Fotos, Bewegung) im Browser: Grenze, Speicherbedarf in der IndexedDB, Videos hinter Links öffnen weiter im Browser | ein Paket mit Bildern läuft; Grenze und Meldung stehen fest |

Stufe 1–3 sind das, was der Auftrag braucht (ein Kurs, Pläne, ohne Dateien). Stufe 4 macht
„laufend aktualisieren“ wahr; ohne sie hieße ein neuer Stand: Link noch einmal öffnen.

## 4. Offen — vor dem Bauen zu klären

1. **Braucht-Angabe.** Ein Paket mit Verweisen auf Standard-Übungen trägt „braucht Standard
   ab x.y.z“ (V6); die App lädt das Gebrauchte „beim Import zuerst“. Woher im Browser, wo das
   Standardpaket das eingebaute ist und Quellen aus sind? Nicht nachgelesen. Mindestens: Ist
   das eingebaute älter als verlangt, sagt die Rückfrage es, statt still Übungen offen zu lassen.
2. **Gemeinsame Geräte.** Der Code liegt nach dem Import im Browser (IndexedDB). Am eigenen
   Handy gewollt; an einem geliehenen Rechner bleibt das Paket lesbar, bis jemand „Alles
   löschen“ tippt. Reicht der Hinweis in der Karte „Speicher im Browser“, oder fragt die
   Web-Fassung beim privaten Paket einmal „Auf diesem Gerät merken?“ — Bens Entscheidung.
3. **Datenschutzerklärung.** Die Seite lädt dann eine Datei aus einem Ordner, der einer Person
   zugeordnet ist; im Protokoll des Servers stehen IP und Ordner (wie heute bei der App). Ob
   der Text der Praxis das deckt, steht im privaten Repository der Homepage — vor dem Hochladen
   eines Builds mit Stufe 1 nachsehen (wie beim Speichern, `plan_web.md` §5 „Recht“).
4. **Zwei Tabs** (`plan_web.md` §5): Der zweite Tab speichert nicht — ein Import dort wäre nach
   dem Neuladen weg. Den Link-Import im zweiten Tab mit dem vorhandenen Hinweis ablehnen.
5. **Gerätetest**: neuer Eintrag in `docs/offene_fragen.md` (Handy, Safari/iPhone, Firefox) —
   Nummer beim Bauen vergeben.

## 5. Nicht in diesem Plan

Öffentliche Paketquellen (Index) und fremde Server im Browser; Videos aus Paketen in der
Web-Fassung abspielen (`link_videos`, T139); ein neues Verschlüsselungsverfahren.

## 6. Gebaut und gemessen (23.11.2026)

**Stufe 0 — gemessen** (kopfloses Chromium am Laptop, Pyodide 314.0.7 / Python 3.14.2 aus dem
Build 0.3.94, hinter `default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src
'self'; …`):

| Frage | Ergebnis |
|---|---|
| `hashlib.scrypt` im Browser | fehlt — ebenso `hashlib.pbkdf2_hmac`; SHAKE-256 und HMAC sind da |
| `fetch` einer Datei unter `/pakete/`, binär | geht (9 ms lokal); fremder Server und eine Weiterleitung dorthin: von der CSP blockiert |
| `cryptography` nachladen | 47.0.0 aus Pyodides Liste, mit `cffi`, `six`, `pycparser` — zusammen 2,4 MB, 0,7 s |
| scrypt N = 2¹⁵, r = 8 | 0,14–0,20 s; derselbe Schlüssel wie `hashlib` (eine Datei des Werkzeugs entschlüsselt) |
| `asyncio.to_thread` in Pyodide | läuft (ohne echten Thread) |
| Route hinter „#“ beim Start | Flet liest sie; auch ein Wechsel bei offener Seite kommt als Routenwechsel an |

Gewählt: **Weg A** (`cryptography`). Nicht im App-Archiv, sondern **neben Pyodide**
(`scripts/web_bauen.py`, `NACHLADEN`): beim Bauen von jsdelivr geladen, Prüfsumme aus Pyodides
`pyodide-lock.json`; die Seite lädt es erst, wenn ein privates Paket geholt ist — wer keins
hat, lädt die 2,4 MB nie.

**Was gebaut ist:**

| Stufe | Wo | Abweichung vom Plan |
|---|---|---|
| 1 Link | `ui/browsernetz.py` (`vorab`, `ausfuehren`, `PyodideNetz`), `components/paket_link.link_importieren` | Obergrenze im Browser 40 MB je Datei (`MAX_BYTES`), höchstens 64 Adressen je Lauf; eine Paketquelle (Index) per Link lehnt die Web-Fassung mit einem Satz ab |
| 2 Privat | `core/privat._scrypt`, `moeglich`; `browsernetz.privat_bereit` | geladen wird beim Holen eines privaten Pakets (Kopf `TAPRIV`), beim Datei-Import mit dem Code; die Speichergrenze von scrypt steht jetzt vor dem Rechnen, für beide Wege |
| 3 Ein Link | `core/paketquelle.seitenroute`, `ordner_aus_route`; `paket_link.seitenlink_oeffnen`; `ui/app.py:zeige_route`; `trainingsapp-paket bauen --web-url` | die Route bleibt nicht stehen (`#/pakete` bzw. die Paketseite); zweiter QR-Code `<name>.zugang.web.svg`; im zweiten Tab kein Import |
| 4 Updates | `views/updates.py` (`beim_start`, `pruefung_ausfuehren`), Schalter `paket_links` | `paket_quellen` bleibt im Browser aus, `paket_links` ist an; die Seite „Updates“ gibt es jetzt auch im Browser (ohne Karte „Quellen“, eigener Text zur App); kein Hinweisdialog — gefragt wird nur der eigene Server. Auch in der App werden Datei-Links jetzt geprüft, wenn die Quellenliste leer ist |
| 5 Dateien | `components/bildquelle.py` in `paketmedium`, `material`, `bewegungsbild`, `uebungsbild` | Befund beim Messen: Flutter fragte den Dateipfad beim Server an (404), das Bild blieb leer — im Browser bekommt `ft.Image` die Bytes |

**Gemessen im Browser** (Probekopie des Builds 0.3.94 mit diesem Quelltext als App-Archiv,
Pakete mit `trainingsapp-paket bauen --web-url` gebaut):

| Probe | Ergebnis |
|---|---|
| Seite mit `#/paket/p/<ordner>` öffnen | Paketmanager, „Privates Paket — Code?“; Adresszeile danach `#/pakete` |
| Code eingeben | `cryptography` kommt vom eigenen Server, Rückfrage „… importieren?“ mit Kurs und Plan, importiert |
| Version heben, bauen, Seite neu laden | Anfragen: `paket.stand.json`, dann `paket.json`; das Paket steht auf 0.2.0, ohne Rückfrage, ohne erneutes Laden von `cryptography` bei unverändertem Stand |
| derselbe Link noch einmal | Paketseite, keine Anfrage außer den Standdateien |
| privates Paket mit Bild (ZIP, 44 kB) | erst `paket.json` → 404, dann `paket.zip`; importiert, das Bild erscheint (vor `bildquelle`: leer) |
| Anfragen an fremde Server | keine |

**Nicht gemessen:** am Handy, Safari, Firefox; Bildfolge einer Bewegung und SVG-Symbol aus
einem Paket; große ZIPs nahe der Grenze; der Build selbst (`flet build web` und das Einlegen
der Pakete sind nur über `nachladen_einlegen` an der Probekopie gelaufen) — T155.

**Zu §4:** (1) Braucht-Angabe — das Werkzeug schreibt die Adresse des gebrauchten Pakets in
den Kopf (`paket.braucht[].quelle`); „… laden“ im Kapitel oder Plan geht im Browser über
denselben Weg, weil die Datei auf demselben Server liegt. Das eingebaute Standardpaket der
Seite ist das des Builds; verlangt ein Paket ein neueres, steht es dort als „wartet“.
(2) gemeinsame Geräte und (3) Datenschutzerklärung: **offen, Bens Entscheidung** — vor dem
Hochladen eines Builds mit diesem Stand. (4) zweiter Tab: gebaut. (5) Gerätetest: T155.
