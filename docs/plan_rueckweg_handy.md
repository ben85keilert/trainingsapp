# Planung: Rückweg vom Handy — am Handy bauen, am Laptop einpflegen, veröffentlichen (17.11.2026)

Ben, 17.11.2026: „wenn ich mit dem Smartphone einen Kurs/Plan erstelle lässt sich dieser
exportieren und wieder einlesen. Überprüfe einmal die Rückwege […] Zuerst brauche ich die
Gewissheit, dass nicht Pakete unnütz überschrieben werden — dann brauche ich die
rückkonvertierten Pakete/Pläne/Kurse auf der Laptopplatte und so verarbeitet, dass die Medien
über Links bereitgestellt werden […] am Ende möchte ich mit veroeffentlichen.sh diese sauber
auf den Server laden.“

Zwei Zwecke (Ben, 17.11.2026):

- **A — Serverpakete überarbeiten:** „alte Pakete, die fest auf dem Server sind überarbeiten
  und aktualisieren“ — das Paket ist am Handy installiert, wird dort verändert und läuft zurück.
- **B — Pakete für andere:** „individuelle Pakete für andere User erstellen, die dann als
  private Pakete hochgeladen und gedownloadet werden können. Evtl. wird aus einem Standardpaket
  ein Plan/Kurs erstellt und nur das ist anders […] (Paketverlinkungen müssen passen)“.

**Stand 18.11.2026: Stufe 1–8 gebaut** (§6; seit 18.11. auch V4/V5 und `sha256` am Link); offen der Gerätetest
(Stufe 9, Katalog T146). Die Inhalte liegen im privaten Repo
`trainingsapp-inhalte` (`pakete/*.toml`, `veroeffentlichen.sh`); Werkzeug und App hier.

---

## 1. Was heute gilt

| Befund | Beleg | geprüft |
|---|---|---|
| `uebernehmen` liest keine ZIP — ein eigenes Paket mit Datei exportiert das Handy immer als ZIP | „Das ist keine Paketdatei (kein JSON)“; `_quelle_lesen` liest JSON mit `paket_lesen` | Versuch 17.11. |
| `uebernehmen` vergleicht nur zwei Stände: Ein älterer Export gleicher Version holt eine am Laptop geänderte Beschreibung zurück | Ausgabe „Baum: Beschreibung“ | Versuch 17.11. |
| `uebernehmen` legt keine neuen Übungen, Kurse, Kapitel oder Pläne an | `paket_werkzeug.py`, `_uebungen_uebernehmen` | Code |
| Bringt ein Update genau den Wert, den die Person geändert hatte, gibt es keinen Hinweis — das Feld gilt danach wieder als Paketstand | `core/abgleich.py:250-253`, `core/pakete.abweichungen` | Code |
| Eine Paketübung mit der ID einer **eigenen** Übung wird nicht eingespielt — die eigene bleibt, Updates erreichen sie nie | `uebungspakete.md` (Tabelle „Die Übung (gleiche ID)“) | Doku, nicht nachgestellt |
| Paketpläne haben die ID aus Paket, `plan:<key>` und Profil; ein Paketplan, dessen `key` die ID eines eigenen Plans ist, entsteht neben ihm ein zweites Mal | `core/pakete.py:262`, `data/pakete._plaene_planen` | Code, nicht nachgestellt |
| Ein eigenes Paket nimmt Übungen anderer Pakete nur als Ergänzung mit — sechs Felder (Beschreibung, Medien, Eingabe, Ziel, Timer, Takt) | `core/ergaenzungen.py:42` | Code |
| Kurse aus einem Paket lassen sich nur als Kopie bearbeiten; die Kopie bekommt neue IDs und merkt sich das Original nicht | `ui/views/kurs_bearbeiten.py:50-51`, `kurs_kopieren` (:250) | Code |
| Ein Schlüssel aus einem anderen Paket fällt still aus dem Plan | `docs/plan_paketverweise.md` §1 | Versuch 14.11. |
| Die App liest „X.Y.Z“; die Geräte entscheiden nach der Stufe aus dem Unterschied, nicht nach der Nummer; `version_reicht` nutzt nur das Werkzeug; `veroeffentlichen.sh` ruft `pruefen --gegen` nicht | `core/paketversion.py`, `ui/views/updates.py:196`, `paket_werkzeug.py:1054` | Code, grep |
| Paketablage ohne Leichen: `<sha256>.<endung>`, `aufraeumen` löscht, was nichts mehr nennt, auch `.teil` — nach jedem Import und beim Start; nicht im Backup; Einstellungen → Anhänge zeigt sie nicht | `data/paketmedien.py:1-10, 129`, `data/pakete.py:1294`, `ui/state.py:715`, `ui/views/einstellungen_anhaenge.py` | Code |
| Links öffnen im Browser, Paketdateien im eigenen Spieler; der Spieler nimmt auch eine Adresse | `ui/components/medienliste.py:44`, `ui/views/paketmedium.py:80`, `flet_video` `VideoMedia.resource` | Code, nicht ausprobiert |
| „Nur im WLAN“ gibt es schon für App-Updates (das Gerät meldet „getaktet“) | `ui/app_update.py` (`vorbereiten`) | Code |
| Web-Fassung: Daten im Browser; Pakete laden fehlt noch | T140, `docs/plan_web.md` „Was noch fehlt“ | Doku |

## 2. Entscheidungen (Ben, 17.11.2026)

- **E1 — Medien je Stück** als Datei im Paket oder als Link: „Kann sein, dass andere User Videos
  erstellen, dann laden sie ihren Kram vlt auf GDrive oder Dropbox.“ Mediendateien kommen nie
  ins git (Inhalte-Repo, CLAUDE.md Regel 6).
- **E2 — Die TOML ist Herr,** „aber die ältere Handyversion darf keinen Konflikt bekommen“.
- **E3 — Entwürfe bleiben neben dem Paket:** „nebeneinander. Entwurf muss ich selbst löschen.“
  Das Ziel wählt man: altes Paket oder neues — „Meistens wird es letzteres sein, weil ich so
  leichter Inhalte für andere User erstellen kann.“ Folge: Neues vom Handy bekommt am Laptop
  IDs aus seinem `key` (nicht die ID vom Handy — sonst käme die Paketfassung beim Autor nie
  an, §1), ein neues Paket eine eigene Paket-ID.
- **E4 — Alles kommt zurück:** alle Felder, und Paketpläne wie Paketkurse werden am Handy
  geändert, nicht nur neue angelegt („beides“).
- **E5 — Versionen „X.Y.Z“**, „6 → 0.0.6“. Manuell bleibt möglich: am Gerät der Modus
  „Manuell“, am Laptop setzt der Autor die Nummer.
- **E6 — Videolinks in der App:** für jeden Server, „je Server“ gemerkt (Whitelist).
  „Videos speichern wäre gut, dafür ein Button (Download) und das wird in den Anhängen
  entsprechend angezeigt, um Platz machen zu können. Kurse/Pläne sollen als Ganzes
  gedownloadet werden können. Dabei dürfen keine Leichen von alten Dateien entstehen, falls
  Medien herausgenommen werden.“ Laden „erstmal nur WLAN mit Möglichkeit auf Umstellung“.
  Damit sind P202 und P14 entschieden.
- **E7 — Fotos und Videos dürfen Menschen zeigen** („Tatsächlich brauche ich aber die Videos
  und Photos“) — mit Einwilligung der Abgebildeten, ohne Vorher-Nachher-Bilder (Inhalte-Repo,
  Regel 6). Pakete tragen keine Einträge, Messungen, Strecken, Profile (`uebungspakete.md`,
  „Export“); Dateien reisen nur, wenn man sie als „Datei fürs Paket“ anhängt, bereinigt.
- **E8 — Verweise zwischen Paketen:** `docs/plan_paketverweise.md` F1–F3 wie vorgeschlagen,
  F4: fehlende Übungen werden nachgeladen (dort §4, Stufe V6); fehlt ein **privates** Paket,
  fragt die App nach seinem Code (P220: „a)“).

## 3. Ablauf

```
Handy:  Paket installiert → ändern, Pläne/Kurse bauen, Fotos/Videos aufnehmen
        → exportieren mit Ziel „neues Paket“ (Vorgabe) oder „Änderungen für Paket X“ (ZIP)
Laptop: trainingsapp-paket einlesen ZIP → Eingang: entwuerfe/eingang/<name>-<datum>/
        (TOML + Medien, nicht im git) + Bericht
        ├─ A: in pakete/<x>.toml — drei Wege, TOML gewinnt, Wert vom Handy gemeldet,
        │     Neues angehängt, nichts gelöscht
        └─ B: pakete/<neu>.toml — eigene Paket-ID, [privat] fuer = "Kürzel",
              Verweise uebung = "…", paket = "Standard", Ergänzungen für Standard-Übungen
        → je Medium: Datei bleibt oder wird Link (Medientabelle)
        → Version vorgeschlagen → Commit → ./veroeffentlichen.sh (prüft mit --gegen)
Handy des Autors: Update kommt; Änderungen an Paketübungen lösen sich auf (§1),
        der Entwurf steht daneben und wird von Hand gelöscht
```

## 4. Laptop: das Werkzeug

1. **`uebernehmen` mit drei Wegen.** Basis ist der Paketstand (`package_standard_json` aus der
   Datenbank) oder die Basisdatei (Punkt 2). Haben Handy und TOML dieselbe Stelle geändert,
   gewinnt die TOML, der Wert vom Handy steht im Bericht; nichts hält an. Neue Übungen, Pläne,
   Kurse und Kapitel legt es an (`key` aus dem Namen, wie `plan_schluessel`); es löscht nie.
   Test: der Versuch aus §1 (älterer Export holt nichts zurück).
2. **`einlesen ZIP [--in pakete/<x>.toml | --neu pakete/<y>.toml]`.** Liest ZIP und JSON
   (`paket_oeffnen`), schreibt den Eingang, übersetzt IDs zurück: Für Übungen anderer Pakete
   rechnet das Werkzeug die IDs aus `pakete/*.toml` nach und schreibt `uebung` + `paket`.
   Ein neues Paket bekommt eine eigene Paket-ID; der Kopf merkt sich, aus welchem eigenen
   Paket es kam (nur fürs Werkzeug, `bauen` lässt es weg), damit ein späterer Export desselben
   Entwurfs sein Ziel findet. `pakete/<name>.basis.json` (committet) hält den eingelesenen
   Stand und die Zuordnung Handy-ID → `key` — die Basis der nächsten Runde.
3. **Verweise V1 + V2** aus `docs/plan_paketverweise.md`.
4. **Versionen.** Die TOML trägt „X.Y.Z“ (Standard „0.0.6“, Qigong „0.0.2“ — dieselben Zahlen);
   Regel 4 im Inhalte-Repo wird umgestellt. `einlesen` schlägt die Nummer aus der Stufe vor
   (`core/paketstufe.stufe` gegen die veröffentlichte Fassung). `veroeffentlichen.sh` ruft
   `pruefen --gegen <Index>`: **gesperrt** wird nur, wenn sich der Inhalt geändert hat und die
   Nummer nicht gestiegen ist (kein Gerät sähe das Update); eine zu kleine Stufe ist ein
   **Hinweis** — die Geräte rechnen die Stufe selbst (§1, `ui/views/updates.py:196`).
5. **Medientabelle** `pakete/<name>.medien.toml`: je Datei (SHA-256) „Datei“ oder „Link“;
   beim Bauen ersetzt das Werkzeug `datei` durch `uri` und schreibt `sha256` dazu. Titel,
   Rolle, Lizenz bleiben. Gehört zu M3 in `docs/plan_medienrollen.md` §4.

## 5. App

1. **Export mit Ziel und Herkunft** (für A). Im Dialog des eigenen Pakets wählt man das Ziel:
   neues Paket (wie heute, U4) oder „Änderungen für Paket X“. Dann schreibt der Export jede
   geänderte Paketübung **ganz**, mit ihrem Paketstand als Basis; Paketpläne mit Paket-ID und
   Plan-`key` (die App kennt ihre Paketpläne, `state.pakete.paketplaene`; ob der `key` am Plan
   steht, beim Bauen prüfen); die Basisversion. `kurs_kopieren` merkt sich Original-Kurs und
   Zuordnung der Kapitel (`core.kursbau.kurs_kopie` bildet Blöcke schon alt → neu ab) — sonst
   entstünde am Laptop ein neuer Kurs, und der Fortschritt an den Kapitel-IDs ginge verloren.
   Formatänderung: zuerst ein Eintrag in `docs/kompatibilitaet.md`.
2. **Videolinks in der App** (E6).
   - **Abspielen:** in der App, wenn die Adresse nach einer Videodatei aussieht oder das
     Werkzeug sie markiert hat; sonst der Browser wie heute; scheitert der Spieler, „Im Browser
     öffnen“.
   - **Je Server erlaubt:** beim ersten Mal ein Hinweis („lädt von <Server> — der Server sieht
     deine IP-Adresse“), gemerkt je Gerät; die Liste unter Einstellungen → Updates neben dem
     Schalter für Bilder in Kapiteltexten, einzeln löschbar.
   - **Sicherheit:** genauer Servername (ähnlich aussehende Zeichen als `xn--…`); Umleitungen
     nur über https, ein neuer Server fragt neu — wie Dropbox und Google Drive umleiten, wird
     mit echten Links geprüft, bevor feststeht, was „ein Server“ ist. Die **App lädt selbst**,
     nicht der Spieler: Obergrenze, Dateiname aus der Prüfsumme, keine halben Dateien;
     `sha256` am Link wird nach dem Download verglichen — passt sie nicht, spielt die App die
     Datei nicht ab. Bleibt: Eine präparierte Datei könnte den Spieler angreifen (gilt heute
     schon für ZIP-Pakete) — den Spieler aktuell halten.
   - **Herunterladen:** Knopf am Video, „Alle Videos laden“ an Kurs und Plan (vorher Anzahl
     und Größe). Nur im WLAN wie die App-Updates, Schalter „auch über mobile Daten“. Ablage ist
     die Paketablage, dazu die Zuordnung Link → Datei; `aufraeumen` kennt sie — fällt ein
     Medium weg oder bekommt es einen neuen Link, verschwindet die alte Datei. Nicht im Backup.
     Einstellungen → Anhänge bekommt „Heruntergeladen“: je Kurs, Plan oder Paket mit Größe,
     löschen (der Link bleibt).
   - **Recht:** eine neue Netzverbindung in Solo — Schalter, Hinweis und Nachtrag in
     `docs/recht/40_toms.md`, `80_store_freigaben.md`, `build/solo.toml` (CLAUDE.md, Updates).
     `docs/plan_medienrollen.md` §5 („Keine neue Netzverbindung“) gilt bis dahin.
3. **Verweise V3–V6** aus `docs/plan_paketverweise.md` (`braucht`, Nachladen, Fehlendes
   sichtbar, Export schreibt `braucht`).

Nicht Teil dieses Plans: Herunterladen in der Web-Fassung; eine eigene Ablage für Medien auf
dem Server (nur, wenn Ben sie will — dann Caddy, `veroeffentlichen.sh`, rsync mit Zeitstempeln).

## 6. Stufen

| Stufe | Wo | Inhalt | Zweck |
|---|---|---|---|
| 1 | Werkzeug | `uebernehmen` mit drei Wegen, legt Neues an — **gebaut** (Übungen; Kapitelpläne wie bisher) | A |
| 2 | Werkzeug | `einlesen`: Eingang, Ziel, Basisdatei, IDs → `paket` + `key` — **gebaut** (neue TOML direkt unter `pakete/`, Merkdatei `pakete/einlesen/<paket>.json`; weitere Runde: Übungen in drei Wegen, Pläne/Kurse nur genannt) | A, B |
| 3 | Werkzeug | Verweise V1 + V2 — **gebaut** | B |
| 4 | Werkzeug, Inhalte | X.Y.Z, Vorschlag der Nummer, `veroeffentlichen.sh` mit `--gegen` — **gebaut** (`--stufe-als-hinweis`, Vorschlag nach `uebernehmen`) | A, B |
| 5 | Werkzeug | Medientabelle Datei → Link mit `sha256` — **gebaut als `verlinken`** (je Datei, `--pruefen` lädt und vergleicht). **`sha256` am Link seit 18.11.2026:** Für ein Video, das die App selbst lädt, hängt `verlinken` `#sha256=<Prüfsumme der Datei>` an die Adresse — ein Fragment, das nie an den Server geht: kein neues Feld, keine Formatänderung, Browser und ältere Apps öffnen den Link wie bisher; `pruefen` meldet eine unlesbare Prüfsumme | Medien |
| 6 | App, Werkzeug | Export mit Ziel und Herkunft, Kurskopie merkt das Original — **gebaut** anders als geplant: Der Export eines installierten Pakets (Paketmanager → Paket → Exportieren) trug schon alle Felder der Übungen und Paketpläne mit ihrem Schlüssel; dazu hakt er jetzt die Pläne des Pakets an. `uebernehmen` gleicht Paketpläne ab; eine Kurs-Kopie merkt sich ihr Original (`kopie_von`, Migration 067) und kehrt zurück. Die Wahl „Ziel“ im Dialog entfiel: neues Paket = eigenes Paket + `einlesen`, altes Paket = Export des Pakets + `uebernehmen` | A |
| 7 | App | Videolinks: je Server, Abspielen, Herunterladen, Anhänge, Aufräumen — **gebaut** (`core/linkvideos.py`, `ui/components/linkvideo.py`, Migration 068): Abspielen heißt laden und vom Gerät spielen (die App lädt, nicht der Spieler); Kurs-Menü und Plan „Videos laden“; Einstellungen → Updates: mobile Daten, erlaubte Server; Anhänge: „Geladene Videos“; in der Web-Fassung aus (`WEB.ohne`). **`sha256` am Link seit 18.11.2026** (`core.linkvideos.pruefsumme`): Nach dem Laden vergleicht die App; ein anderes Video spielt sie nicht ab („… ein anderes Video als im Paket“), nichts bleibt liegen. Liegt dieselbe Datei schon in der Ablage (aus einer Paketdatei, einem anderen Link), lädt sie nichts | Medien |
| 8 | App | Verweise V3–V6 — **gebaut** (`braucht` beim Bauen, Rückfrage beim Import mit „Erst … laden“, danach das Paket noch einmal; seit 18.11.2026 V4: fehlende Übungen warten sichtbar und kommen von selbst, wenn das Paket später kommt, Migration 069; V5: `braucht` im Export eigener Pakete) — `docs/plan_paketverweise.md` §3 | B |
| 9 | Gerät | A und B durchspielen; dazu ein Update, das ein Video herausnimmt (keine Leiche) — Katalog **T146** | — |

Zweck B geht nach Stufe 1–5 schon ohne neue App-Version: am Handy neu bauen; was an
Standard-Übungen anders ist, reist als Ergänzung — dafür sind Ergänzungen da.

Bis Stufe 1–2 gebaut sind: `uebernehmen` nur mit `--probe` und danach `git diff`; das
veröffentlichte Paket nicht auf dem Handy mit dem Entwurf installieren, wenn der Entwurf
weiterbearbeitet werden soll.

## 7. Offen

- Was bei Umleitungen der Cloud-Anbieter „ein Server“ ist — mit echten Links prüfen (Stufe 7).
- Gerätetests (Stufe 9).

## 8. Gesucht und gelesen

Katalog: `grep -n "^| P" docs/offene_fragen.md | grep -i "rückweg\|übernehmen\|einlesen\|download\|whitelist\|paketverweis"`
→ P202, P14 gelesen; K-F6 (Abschnitt 1, Medien). Ganz gelesen: `docs/plan_paketverweise.md`.
Abschnitte: `docs/uebungspakete.md` (Export, Eigene Pakete, Ergänzungen, Pläne, private
Pakete), `docs/plan_paketversionen.md` §2, `docs/plan_web.md` „Was noch fehlt“,
`docs/plan_medienrollen.md` §5. Code wie in §1 genannt.
