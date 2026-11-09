# Pakete mit Inhalten: Updates, Medien, Ergänzungen, modulare Pläne

Stand: 9.11.2026 — **entschieden, wird gebaut** (Ben: „Setze U1–U7 nacheinander um. Lass dir
Zeit“); Antworten in §10, Stand der Stufen in §13. Ben vorher: „erstelle eine Übersicht über die
Updatemöglichkeiten und erstelle daraufhin einen Plan, wie man das am besten umsetzt, wir werden
evtl. mehrmals hin und her schreiben müssen.“ Verteilen und Schutz: §11. Baut auf `docs/plan_paketversionen.md` (17.10.2026) und `docs/uebungspakete.md`.

## 0. Anlass

Ben, 9.11.2026:

> Die Übungen ändern sich regelmäßig. Die Übungen haben jetzt auch den Textbereich
> Beschreibung und evtl. Medien. Für die Grundübungen passt es, dass Updates automatisch
> durchgehen können. Für Pakete würde es sich lohnen, dass mit diesen zusätzliche Inhalte
> kommen, Beschreibungen und evtl. auch Medien. Es ist leichter für mich, wenn ich ein Paket
> erstelle, darin Videos reinlade, dieses Paket exportiere und dann jemandem mitgebe. Eine
> Paketübung kann auch eigene Inhalte haben, ein Paket liefert einen Mod für eine Übung.
> Alternativ braucht man wieder Kopien von Übungen, damit ein User Dinge üben kann, die
> individualisiert sind. Am liebsten wäre es mir,
> - wenn Pläne zu den Übungen modularer gehalten werden — eigene Beschreibungen. Wenn man die
>   Übung aus einem Plan löscht, kann man den Plan/Kurs neu laden und es wäre wieder da, wenn
>   die Quelle existiert
> - eigene Änderungen an Übungen bleiben in Beschreibung, Medien und co gespeichert.
>   Hard-Reset ist aber möglich

---

## 1. Übersicht: wie Inhalte heute auf ein Gerät kommen

| Weg | Wann | Was passiert |
|---|---|---|
| **Standard** (`data/seed/standard.toml`) | bei jedem Start | Steigt die Version, wird eingespielt (je Feld abgeglichen); ist schon eine höhere installiert, setzt der Start aus (K6) |
| **Paketquelle** (Index per HTTPS, Einstellungen → Updates) | beim Start (abschaltbar) und „Jetzt prüfen“ | Je Paket der Modus **Alle · Kleine · Manuell** (seit 0.3.73); Vorgemerktes holt der Pfeil mit Vorschau |
| **Datei** (Paketmanager → Importieren) | von Hand | Vorschau, dann „Übernehmen“ — immer mit Nachfrage |
| **Link** (Index oder Paketdatei) | von Hand | wie Datei; ein **Index** wird zur Quelle (seine Pakete stehen unter „Neu in den Quellen“ zur Wahl), ein **Link auf eine Paketdatei** bindet nur dieses eine Paket — die App fragt bei jeder Prüfung nur diese Datei (seit 28.10.2026) |
| `TRAININGSAPP_PAKETE=<ordner>` | Start, nur Entwicklung | TOML-Dateien aus dem Inhalte-Repo |
| `trainingsapp-paket` | am Rechner | prüfen, bauen (JSON), Index schreiben, `uebernehmen` (App → TOML) |
| **Export aus der App** (Paketmanager → Exportieren) | von Hand | gewählte Übungen und Pläne als **JSON**, ohne Medien |

## 2. Übersicht: was ein Update je Inhalt tut

| Inhalt | Update heute | Eigene Änderungen | Zurücksetzen |
|---|---|---|---|
| **Paketübung** | je Feld Drei-Wege-Abgleich gegen den gespeicherten Paketstand (`core/pakete.zusammenfuehren`, 14 Felder: Name, Beschreibung, Symbol, Typen, Regionen, Parameter, Ziel, Limits, Timer, Uhr, Zählt als, Sensor, Takt, Videos) | Ein geändertes Feld bleibt — als **ganzes Feld** | „Auf Paketstand setzen“: die ganze Übung (hart) |
| … Beschreibung | **ein** Feld, auch mit Abschnitten (P108) | Eine eigene Zeile hält **alle** künftigen Textkorrekturen des Pakets fern | nur ganz |
| … Medien | nur **Links** (`media`, ein Feld); eigene Fotos und lokale Videos gehen nie ins Paket und überleben Update und Reset (`_lokales_behalten`) | Ein eigener Link hält alle neuen Links des Pakets fern | nur ganz |
| Übung fällt aus dem Paket | Nachfrage: übernehmen (eigene Übung) oder löschen | — | — |
| **Eigene Übung** (auch Kopie) | nie | — | — |
| **Paketplan** (je Profil) | ganz ersetzt, wenn unverändert (`plan_stand`) | **Ein** Eingriff → bleibt für immer bei der eigenen Fassung („von dir geändert — bleibt“) | keins |
| … gelöschter Paketplan | kommt **nie** wieder (Grabstein), auch nicht für neue Profile | — | — |
| … gelöschte Planübung | kommt nie wieder | — | — |
| **Planübung** | folgt der Übung (P79: `target`/`felder`/`acc`/`takt` leer = wie die Übung) | „nur hier“ ↺ je Wert; dazu eine kurze **Notiz** (`note`) | ↺ je Wert |
| **Kurs** | ganz ersetzt, wenn unverändert (`kurs_stand`); Kapitel behalten die ID (Fortschritt) | — (Kurseditor offen) | — |
| … Kapitelplan | wird beim Erreichen ein gewöhnlicher Plan, danach **nie** aktualisiert | wie Plan | keins |
| Paketkopf | Name, Beschreibung, Neuigkeiten gehen mit | — | — |

## 3. Versionen und Modi — zwei Stände

- **Gebaut (0.3.73, heute):** Versionen „X.Y.Z“ reisen als Zahl X·10000 + Y·100 + Z
  (`core/paketversion.py`); Modus je Paket **Alle** (jedes Update) · **Kleine** (nur, wenn
  bloß Z steigt) · **Manuell**; „Für alle Pakete“ unter Updates.
- **Geplant am 17.10.** (`docs/plan_paketversionen.md`, Entscheidungen §8, Phasen 3–5 offen):
  Die **App bestimmt die Stufe aus dem Unterschied**, nicht aus der Nummer — **major** (etwas
  fällt weg, ein Kurs ändert seinen Ablauf) fragt nach, **minor** (Texte, Links, neue Übungen,
  Felder der Eingabe) kommt automatisch mit Hinweis, **patch** (Chips, Ziel, Timer, Symbol,
  Typen) bleibt still: „hier kommen nur Änderungen für Neuinstallationen oder manuelle Updates“.
  Dazu: Hinweis bei Feldkonflikt, Vergleich je Feld mit „übernehmen“, Eingabe in zwei Teilen,
  Links je `uri`.
- **Widerspruch:** Heute heißt „Kleine automatisch“ = Z kommt von selbst; am 17.10. hieß Z =
  „kommt nie von selbst an vorhandene Übungen“. → Frage F8.

## 4. Was Bens Wünsche heute verhindert

1. **Medien nur als Links.** Videos und Bilder aus der Kamera oder Fotoauswahl gehen nie in
   ein Paket (CLAUDE.md: Symbole, Bewegungsbild, Anhänge „nie in Paket, Export oder Sync“);
   eine Paketdatei ist JSON bis **5 MB** (`MAX_PAKET_BYTES`).
2. **Beschreibung als ein Feld:** Wer eine Zeile ergänzt, bekommt keine Korrektur des Pakets
   mehr — obwohl P108 die Abschnitte genau für „Paket, Praxis, Patient untereinander“ gedacht hat.
3. **Links als ein Feld** (wie 2).
4. **Keine Ergänzung fremder Übungen:** Wer zur Standard-Kniebeuge eigene Texte und ein Video
   mitgeben will, braucht eine **Kopie** (bekommt dann nie mehr Updates) oder ändert die
   Übung (dann bleibt nur die eigene Fassung).
5. **Pläne alles oder nichts:** ein Eingriff, und der Plan bekommt nie wieder ein Update; was
   man herausgenommen hat, kommt nicht zurück; kein „Plan neu laden“.
6. **Planübung ohne eigene Inhalte:** nur eine kurze Notiz, keine Abschnitte, keine Medien.
7. **Export ohne Paket-Bearbeitung:** kein Paketkopf, keine Version, keine Neuigkeiten, keine
   Medien — die Datei taugt zum Weitergeben, nicht zum Pflegen.

## 5. Ziele (aus §0)

| # | Ziel |
|---|---|
| Z1 | Grundübungen (Standard) aktualisieren sich von selbst — wie heute |
| Z2 | Pakete bringen Inhalte mit: Beschreibungen **und Medien** (Videos, Bilder) |
| Z3 | Ben baut ein Paket **in der App**: Videos hinein, exportieren, weitergeben |
| Z4 | Ein Paket **ergänzt** Übungen anderer Pakete („Mod“) — ohne Kopie |
| Z5 | Pläne modular: Planübungen mit **eigenen Beschreibungen**; Herausgenommenes kommt mit **„Plan/Kurs neu laden“** zurück, solange die Quelle existiert |
| Z6 | Eigene Änderungen an Übungen (Beschreibung, Medien, …) überleben Updates; **harter Reset** bleibt möglich |

---

## 6. Vorschlag: Schichten statt Kopien

Eine Übung, wie man sie sieht, setzt sich aus **Schichten** zusammen — von unten nach oben:

```
Kniebeuge
  Paket „Standard“          ← Grundlage: Name, Parameter, Timer, Beschreibung, Medien
  Ergänzung „Knie-Reha“     ← Abschnitte und Medien eines anderen Pakets (Z4)
  Eigenes                   ← was die Person geändert oder dazugeschrieben hat (Z6)
Im Plan „Knie-Reha Woche 1“
  Paketplan                 ← Abschnitte/Medien der Planübung aus dem Paket (Z5)
  Eigenes im Plan           ← „nur hier“
```

**Abgleich je Abschnitt und je Medium** (Z6, ohne Formatwechsel): Die Beschreibung bleibt *ein*
Text mit `## Name`-Abschnitten — aber der Drei-Wege-Abgleich zerlegt Paketstand, eigene Fassung
und neuen Paketstand in Abschnitte und gleicht **je Abschnittsname** ab: Was die Person nicht
angefasst hat, bekommt das Update; ein eigener Abschnitt bleibt; ein Paketabschnitt, den sie
geändert hat, bleibt mit dem Hinweis „das Paket hat eine neue Fassung“ (‚übernehmen‘).
Medien ebenso **je Medium** (Link nach `uri`, Datei nach Prüfsumme): neue des Pakets kommen
dazu, eigene bleiben, ausgeblendete bleiben ausgeblendet. Der gespeicherte Paketstand
(`package_standard_json`) reicht dafür — keine Migration.

**Harter Reset** bleibt: „Auf Paketstand setzen“ für die ganze Übung; neu dazu „übernehmen“ je
Feld bzw. je Abschnitt (der Vergleich aus `plan_paketversionen.md` §4).

## 7. Pakete mit Medien (Z2, Z3)

- **Drei Formen, alle lesbar** (Ben, F3): **TOML** (von Hand, Inhalte-Repo), **JSON** (ohne
  Medien) und **ZIP** mit Medien (Formatversion 4): `paket.json` wie heute plus
  `medien/<sha256>.<endung>`. Ohne Medien bleibt es JSON (ältere Apps lesen sie weiter; eine
  ZIP lehnen sie mit „Das Paket ist neuer als diese App“ ab).
- **Ein Medium im Paket:** `{kind, quelle: "paket", datei, sha256, bytes, titel, lizenz}` —
  an Übung, Ergänzung, Planübung oder Kurskapitel. *Gebaut (U3):* mit den Schlüsseln, die
  Medien schon hatten — `{ source = "paket", uri = "medien/<sha256>.<endung>", title, license }`;
  Prüfsumme steckt im Namen, die Größe in der ZIP, die Art folgt der Endung. Ältere Apps lehnen
  eine ZIP mit „kein JSON“ ab.
- **Ablage:** `Medien/Pakete/<sha256>.<endung>` — gleiche Datei nur einmal, gelöscht, wenn kein
  installiertes Paket sie mehr nennt. Eigene Medien bleiben, wo sie sind.
- **Grenzen:** Paket bis etwa 300 MB, Quelle zeigt die Größe vorher und fragt bei mobilen Daten
  (heute 5 MB JSON).
- **Datenschutz (Grundregel „GPS nie teilen“):** Paketmedien sind *Inhalt*, den die Autorin
  bewusst ins Paket legt — nicht Anhänge an Einträgen (die bleiben nie geteilt). Vor dem Export
  müssen **Ortsangaben raus** (Ben, F4: „Bilder auch bereinigen, falls da eine Ortsangabe ist“):
  Bilder ohne EXIF-GPS, Videos ohne Ortsatome (MP4/MOV `©xyz`, `loci`, ISO-6709-Angaben) — in
  reinem Python beim Export und beim Bauen; was die App nicht sicher bereinigen kann, kommt nicht
  ins Paket. **PDF** kommt als dritte Art dazu (Material, F6).
- **In der App bauen (Z3):** im Paketmanager **„Eigenes Paket“**: Paketkopf (Name,
  Beschreibung, Version, Neuigkeiten), Inhalt — **Übungen, Pläne und Kurse** (Ben, F5),
  eigene Änderungen an fremden Übungen als Ergänzung —, Medien je Übung/Planübung aus Kamera oder
  Fotoauswahl. **Exportieren** schreibt die
  Datei (ZIP) und schlägt die nächste Version vor; **Teilen** gibt sie weiter. Wer sie bekommt,
  importiert wie heute; eine neue Fassung kommt als neue Datei (oder später über eine Quelle).

## 8. Ergänzungen („Mods“, Z4)

- Ein Paket kann zu einer **Übung eines anderen Pakets** Abschnitte und Medien liefern:
  `ergaenzungen = [{ uebung = "<id>", abschnitte = [...], medien = [...] }]`.
- **Angezeigt** werden sie in der Übung unter deren Beschreibung, je Abschnitt mit kleinem
  Paketnamen („aus Knie-Reha“); Medien dazu. Die Übung selbst bleibt die des Grundpakets und
  bekommt dessen Updates weiter.
- **Gespeichert** als eigene Schicht (Tabelle der Ergänzungen je Paket und Übung), nicht in die
  Beschreibung gemischt: Entfernen oder Deaktivieren des Pakets nimmt seine Ergänzungen sauber
  weg; ein Update ersetzt nur seine eigenen Abschnitte.
- **Fehlt die Übung** (Grundpaket nicht installiert), wartet die Ergänzung; der Paketmanager
  sagt es („ergänzt: Kniebeuge — fehlt“).
- **Was eine Ergänzung darf** (Ben, F2: „auch Parameter, Ziel, Timer, Takt — hier wird
  individualisiert“): Abschnitte und Medien **und** Parameter, Ziel, Timer, Takt. Reihenfolge
  der Schichten: Grundpaket → Ergänzungen (in der Reihenfolge ihrer Installation; die spätere
  gewinnt je Feld) → Eigenes. Technisch: Der gespeicherte Paketstand einer Übung ist dann
  „Grundpaket + Ergänzungen“; kommt, ändert oder geht eine Ergänzung, gleicht die App wie bei
  einem Update ab — Eigenes bleibt. Die Herkunft je Abschnitt und Feld zeigt die Übung an.

## 9. Modulare Pläne (Z5)

- **Planübung mit eigenen Inhalten:** Abschnitte und Medien je Planübung — aus dem Paketplan
  oder selbst geschrieben. **Erklärungen stehen im „i“** (Ben, F6); gibt es **Material**
  (Video, Text, PDF …), zeigen Fokus und Übung an, dass es das gibt — **solange man es ansieht,
  pausiert die Uhr**, man startet sie selbst wieder. Die kurze Notiz (`note`) bleibt, wie sie
  ist. *Gebaut so (U2):* Das Blatt „Material“ hält die Uhr **dieser** Übung beim Öffnen an;
  „Uhr weiter“ startet sie von Hand, **beim Schließen läuft sie weiter**, wenn sie für das
  Material stand und niemand sie angefasst hat („solange“). Material = Anweisungen der
  Planübung und Videos/Links der Übung; die Beschreibung der Übung bleibt im „i“ (Gerätetest
  T108).
- **Paketplan-Updates je Planübung** statt alles oder nichts: Was die Person an einer Planübung
  nicht angefasst hat, bekommt das Update; neue Planübungen kommen dazu; was sie
  **herausgenommen** hat, merkt sich der Plan und lässt es weg …
- … bis **„Plan neu laden“** (Menü am Paketplan): Vorschau, was zurückkommt und was sich ändert,
  dann zwei Wege: **„Fehlendes zurückholen“** (Herausgenommenes und Gelöschtes kommt wieder,
  eigene Änderungen bleiben) oder **„Auf Paketstand setzen“** (hart). Geht nur, solange das Paket
  installiert ist („wenn die Quelle existiert“).
- **Gelöschter Paketplan:** im Paketmanager „Plan wieder anlegen“ (heute verhindert der Grabstein
  das für immer).
- **Kurs:** „Kurs neu laden“ holt Kapitelpläne zurück bzw. setzt sie auf den Stand des Kapitels;
  der Fortschritt bleibt.

## 10. Entscheidungen (Ben, 9.11.2026; Katalog P155–P163)

| # | Frage | Entscheidung |
|---|---|---|
| F1 (P155) | Schichten statt Kopien (§6) | **ja** |
| F2 (P156) | Ergänzungen nur Inhalt? | **auch Parameter, Ziel, Timer, Takt** — „hier wird individualisiert“ |
| F3 (P157) | Paketdatei mit Medien als ZIP | **ja — TOML, JSON und ZIP unterstützen** |
| F4 (P158) | Videos bereinigen | **ja, Bilder auch**, falls sie eine Ortsangabe haben |
| F5 (P159) | Paket in der App bauen | **ja — Übungen, Pläne und Kurse** exportierbar |
| F6 (P160) | Planübung mit Abschnitten und Medien | **Erklärungen im „i“**; gibt es Anweisungen, zeigen Fokus und Übung, dass Material existiert (Video, Text, PDF …); **solange man es ansieht, pausiert die Uhr**, man startet sie selbst wieder |
| F7 (P161) | „Plan neu laden“, Updates je Planübung | **ja, beides** |
| F8 (P162) | Was heißt „automatisch“? | **(c):** Stufe aus dem Unterschied und Modus — *Alle* = Y und Z automatisch, X fragt; *Kleine* = nur Z; *Manuell* = alles fragt; Eigenes bleibt |
| F9 (P163) | Privates Paket | **wie §11:** verschlüsselt, Ordner mit Zufallsnamen, **8-stelliger Code**, „Zugang anzeigen“, Zugangskarte mit QR-Code |

## 11. Verteilen: Datei, Link, geschützter Link (Bens Fragen, 9.11.2026)

> In Quellen werden ja Links abgelegt. Ist es möglich, in der TOML vom Link nur das eine Paket
> anzugeben? — Wenn Pakete auf dem Server liegen, sind diese dann öffentlich? Kann man diese
> auch mit Link + Passwort irgendwie absichern, d. h. im HTTPS-Link am Ende was anfügen, damit
> der Server die Datei freigibt?

**Nur ein Paket per Link — geht heute:** Statt des Index den **Link auf die Paketdatei**
weitergeben (`…/pakete/uebungspaket_Knie-Reha.json`). Die App installiert nur dieses Paket und
fragt für Updates nur diese Datei; steigt dort die Version, kommt das Update (Modus wie
eingestellt). Ein Index-Link dagegen zeigt alle Pakete des Index zur Wahl.

**Öffentlich?** Ja: Der Server (Homepage-Repo, `infra/Caddyfile`, Block „Paketquelle“) liefert
unter `/pakete/` jede JSON-Datei an jeden, der die Adresse kennt; eine Ordnerliste gibt es nicht
(`/pakete/` ist 404). Der öffentliche `index.json` nennt aber alle Pakete mit Adresse — was
darin steht, ist öffentlich.

**Ben dazu (9.11.2026):** „Ein geheimer Ordner wäre einem Bot doch egal. Wenn alles gecrawled
wird, dann auch der geheime Ordner?“ — „Ich möchte für User Pakete bereithalten, die nur diese
Person betreffen. Wenn man ein Paket passwortsichert, ginge das? Einfach eine Zeichenfolge mit 6
Zeichen? Vielleicht kann man die TOMLs auch so bauen, dass mit der Datei der Link und das Passwort
gleich mitkommt?“ — Benutzername + Passwort: „extremst umständlich und neue Architektur“;
ablaufender Link: „hilft nicht, wenn mehrere Dateien lange rumliegen“. **„Ich möchte mich vor
allem gegen Bots und andere absichern.“**

**Was Bots finden:** Ein Crawler kennt nur, was irgendwo verlinkt oder aufgelistet ist. Eine
Ordnerliste gibt der Server nicht heraus; ein Ordner mit **langem Zufallsnamen** (22 Zeichen, etwa
130 Bit) ist nicht zu erraten — auch nicht von Bots, die Adressen durchprobieren. Ein Bot findet
ihn nur, wenn der Link irgendwo **durchsickert**: Vorschau im Messenger, Virenscanner im Postfach,
öffentlich gepostet. Ein Ordnername aus **6 Zeichen** dagegen ist zu erraten (rund 2 Mrd.
Möglichkeiten — ein hartnäckiger Scanner schafft das in Monaten, bei vielen solchen Ordnern
schneller). Darum zwei Schlösser:

**Vorschlag „privates Paket“ — verschlüsselt, mit Code:**

| Teil | Wie |
|---|---|
| **Link** (gegen Bots) | Paket unter einem Ordner mit langem Zufallsnamen: `…/pakete/p/7Hq3vX9…/paket` — nicht im öffentlichen Index, keine Ordnerliste |
| **Code** (gegen andere) | **6–8 Zeichen** aus einem Alphabet ohne Verwechsler (kein 0/O, 1/I/l), z. B. `K7QM-9XA2`; getrennt vom Link weitergeben (mündlich, Zettel, eigene Nachricht) |
| **Ablage** | Die Paketdatei liegt **verschlüsselt** auf dem Server — der Schlüssel entsteht aus dem Code. Wer die Datei ohne Code hat (Bot, Vorschau, Scanner), sieht nur Zeichensalat. Der Server prüft nichts: keine neue Architektur, für JSON keine Änderung am Caddyfile |
| **TOML** | `[privat] fuer = "Max"` — `trainingsapp-paket` legt beim ersten Bauen Ordner und Code an und merkt sie sich (im privaten Inhalte-Repo), verschlüsselt, lädt hoch und gibt eine **Zugangskarte** aus: Link + Code (auf Wunsch als QR-Code). Updates: derselbe Link, derselbe Code |
| **App** | Link eingeben (oder QR) → „Privates Paket — Code?“ → einmal eingeben → installiert; die App merkt sich den Code, **Updates entschlüsselt sie von selbst**. Unter „Installierte Pakete“: „privat · für Max“, der Link gekürzt; **„Zugang anzeigen“** zeigt Link und Code (für ein zweites Gerät) |

**Wie sicher:** Gegen Bots doppelt — finden können sie den Ordner nicht, lesen könnten sie die
Datei nicht. Gegen andere mit dem Link: Sie brauchen den Code. **Grenze:** Wer die Datei hat und
gezielt Rechenzeit einsetzt, kann einen 6-stelligen Code in Stunden bis Tagen durchprobieren —
das tut kein Bot, nur ein Angreifer mit Absicht. **8 Zeichen** machen daraus Jahre und bleiben gut
zu tippen (`K7QM-9XA2`). Zusätzlich sinnvoll: `X-Robots-Tag: noindex` für `/pakete/` im Caddyfile,
damit ein durchgesickerter Link in keiner Suchmaschine landet.

**Technisch:** geht mit den Bordmitteln von Python (scrypt für den Schlüssel, SHAKE-256 als
Schlüsselstrom, HMAC-SHA256 gegen Verfälschung) — kein neues Paket in der App; vor dem Bau auf
dem Gerät prüfen. Für Pakete **mit Medien** (§7) lässt der Server dann statt „nur JSON“ auch die
verschlüsselte Datei durch (Homepage-Repo).

**Verworfen** (Ben, 9.11.2026): Benutzername + Passwort (umständlich, neue Architektur),
ablaufender Link (Dateien liegen lange), geheimer Ordner allein (kein Schutz, sobald der Link
durchsickert), 6-stelliger Ordnername ohne Verschlüsselung (zu erraten).

## 12. Umsetzung in Stufen (nach Bens Antworten)

| Stufe | Inhalt | braucht |
|---|---|---|
| U1 | Abgleich **je Abschnitt** und **je Medium**, Hinweis bei eigener Fassung, „übernehmen“ je Feld/Abschnitt | F1 |
| U2 | **Planübung** mit Abschnitten und Medien; Paketplan-Updates je Planübung; **„Plan neu laden“**; gelöschte Paketpläne wieder anlegen; „Kurs neu laden“ | F6, F7 |
| U3 | **Medien im Paket:** ZIP (Format 4), Ablage, Import, Export mit Bereinigung, Grenzen, Quelle mit Größe | F3, F4 |
| U4 | **Eigenes Paket in der App:** Paketkopf, Version, Inhalt wählen, Medien, Export/Teilen | F5 |
| U5 | **Ergänzungen** (Format, Ablage, Anzeige, Paketmanager) | F2 |
| U6 | **Stufen aus dem Unterschied** mit den Modi (`plan_paketversionen.md` Phasen 3–5) | F8 |
| U7 | **Private Pakete** (§11): Verschlüsselung im Werkzeug und in der App, Code-Abfrage beim Link, Zugangskarte (Link + Code, QR), „Zugang anzeigen“, `noindex` am Server | F9 |

Jede Stufe mit Vertrag (`docs/uebungspakete.md`, CLAUDE.md), Tests und Gerätetest; U1 und U2
ändern kein Dateiformat, U3–U5 erhöhen die Formatversion. U7 geht unabhängig von den anderen —
für JSON-Pakete schon vor U3.

## 13. Stand der Stufen

| Stufe | Stand |
|---|---|
| U1 | **gebaut 9.11.2026 (0.3.74):** `core/abgleich.py` (je Abschnitt, je Medium, Hinweise, Vergleich, übernehmen), Migration 045 `package_hints_json`, `PaketRepo.hinweise/vergleich/paketfassung_uebernehmen`, `components/paketvergleich.py` im Paketmanager und auf der Übungsseite |
| U2 | **gebaut 9.11.2026 (0.3.75):** Migration 046 (`plan_item.description`, `media_json`), Paketfeld `beschreibung`/`medien` je Planübung (keine neue Formatversion), `core.pakete.plan_abgleichen` (je Feld, je Planübung `übung#n`, IDs bleiben), `PaketRepo.plan_neu_laden`/`plan_wieder_anlegen`/`paketplaene_im_profil`, `KursRepo.kapitelplan_neu_laden`/`kurs_neu_laden`, `core/material.py` + `components/material.py` (Knopf neben dem „i“ und im Fokus, Uhr hält an), `components/neu_laden.py` (Plan-Editor), Karte „Pläne“ im Paketmanager, „Kurs neu laden …“ im Kursmenü, Karte „Anweisungen“ in „Im Plan einstellen“ (`components/abschnitt_editor.py`, auch in „Übung bearbeiten“), Anweisungen im „i“ |
| U3 | **gebaut 9.11.2026 (0.3.76):** Migration 047 (`exercise_media` mit `pdf`/`audio` und Quelle `paket`), `core/paketmedien.py` (Namen, Grenzen, `Paketmedium` mit Prüfsumme), `core/bereinigen.py` (JPEG/PNG/WebP/MP4/MOV/M4A/MP3 ohne Ortsangaben, PDF bleibt, sonst abgelehnt), `core/paketdatei.py` (JSON/TOML/ZIP öffnen, TOML mit `datei`, Export-Bereinigung, reproduzierbare ZIP), `data/paketmedien.py` (Ablage, Aufräumen), Import/Export/Quellen (ZIP bis 300 MB, über 20 MB nicht von selbst), `components/medienliste.py`, `views/paketmedium.py`; Server-Freigabe für `.zip` offen (P164) |
| U4 | **gebaut 9.11.2026 (0.3.77):** Migration 048 `own_package`, `core/eigenes_paket.py` (Version vorschlagen, Inhalts-Prüfsumme, nötige Übungen), `data/eigene_pakete.py`, `views/eigene_pakete.py` (Karte im Paketmanager, Kopf, Inhalt mit Kursen, Export mit Stufe), „Datei fürs Paket“ in „Übung bearbeiten“ und „Im Plan einstellen“ (Datei, Kamera, Fotoauswahl — sofort bereinigt, `Paketablage.aufnehmen`, `ui/paketdatei.py`), Ziel `paketdatei/…`; nebenbei: Kamera/Fotoauswahl fürs Bild der Bewegung gingen nie (Router) — behoben |
| U5 | **gebaut 9.11.2026 (0.3.78):** Formatversion 5 `ergaenzungen[]` (`core/ergaenzungen.py`: Schichten, Herkunft, Unterschied; `core.pakete.ergaenzung_lesen`, Übung per ID oder Schlüssel + Paket), Migration 049 (`exercise_addon`, `exercise.package_base_json`), `PaketRepo.ergaenzungen_anwenden` (wirksamer Stand = Grund + Ergänzungen, Drei-Wege-Abgleich), Deaktivieren/Aktivieren/Entfernen ziehen nach, wartende Ergänzungen, Karte „Ergänzt“, Herkunft je Abschnitt, eigene Pakete bringen Änderungen an fremden Übungen als Ergänzung |
| U6 | **gebaut 9.11.2026 (0.3.79):** `core/paketstufe.py` (Stufe und Gründe aus dem Unterschied: Übungen, Eingabe in zwei Teilen, Kurse mit Kapiteln, Pläne, Ergänzungen; `automatisch` je Modus; `version_reicht`/`mindestens`), `PaketRepo.stufe`, Prüfung beim Start lädt und entscheidet nach der Stufe, Liste und Vorschau nennen Stufe und Gründe, `trainingsapp-paket pruefen --gegen`; die Nummern-Regel (`nur_klein`) ist weg |
| U7 | offen |
