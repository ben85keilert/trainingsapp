# Plan: Import von Links und Plänen, Adresse am Paket, Kurs → Plan aus Auswahl (Ben, 28.10.2026)

Ben: „Es muss möglich sein, auch Links zu importieren. Die App soll das erkennen und den Link
in den Einstellungen mit hinterlegen, aber das mit einem Dialog gegenfragen und Bescheid
geben, wo das hinkommt … In den Einstellungen/Pakete sollte die URL mit hinterlegt sein, zur
Sicherheit für die User, um zu wissen, wo ein Paket hinführt … Pläne ohne Kurse müssen mit
importierbar sein … es wird später möglich sein müssen, dass Pläne aus einer Auswahl per Kurs
zusammengestellt werden … berücksichtige das einmal vor, wir setzen das jetzt noch nicht um.“

Stand: §1–§3 im Bau, §4 nur Vorbereitung (P90). Grundlage: `docs/uebungspakete.md`,
`core/pakete.py`, `core/paketquelle.py`, `data/pakete.py`, `ui/views/pakete.py`,
`ui/views/updates.py`. Sicherheitsfragen zu Caddy und dem Server: später, getrennt.

## 1. Links importieren

Zwei Arten von Links, beide nur `https://` (und `http://localhost` zum Ausprobieren,
`paketquelle.url_pruefen`):

| Was unter dem Link liegt | Erkannt an | Was die App tut |
|---|---|---|
| **Paketindex** (`format = "trainingsapp-paketindex"`) | `index_lesen` | Dialog: „Das ist eine Paketquelle mit n Paketen (Name der Quelle). Sie wird unter **Einstellungen → Updates → Quellen** eingetragen; neue Pakete daraus stehen dort unter ‚Neu in den Quellen‘.“ — Eintragen · Abbrechen. Danach prüft die App die Quellen und öffnet die Seite Updates. |
| **Paketdatei** (`format = "trainingsapp-uebungspaket"`) | `paket_lesen` | Die bekannte Rückfrage vor dem Import (`import_rueckfrage`, mit `quelle = Link`); danach ist der Link die **Quelle des Pakets** (`package.source_url`). Der Dialog sagt: „Die Adresse wird am Paket hinterlegt (**Einstellungen → Übungspakete → ‹Name›**); beim Start fragt die App dort nach einer neueren Version.“ |
| etwas anderes | — | „Unter dieser Adresse liegt weder ein Übungspaket noch ein Paketindex.“ |

- **Wo:** Paketmanager → „Importieren“ öffnet ein Blatt mit zwei Wegen: **Datei wählen** und
  **Link** (Textfeld, Knopf „Einfügen“ liest die Zwischenablage, „Laden“). Die Seite Updates
  behält ihr Feld „Adresse eines Paketindex“; beide landen in derselben Funktion
  (`ui/components/paket_link.py`, `link_importieren`).
- **Updatefähig** (Ben: „updatefähig, wenn die hinterlegte Datei um eine Version angehoben
  wird“): Ein Paket mit Datei-Link als Quelle prüft `pruefung_ausfuehren` beim Start mit —
  es lädt die Datei (höchstens 5 MB), liest die Version und baut daraus einen Eintrag wie aus
  einem Index (`paketquelle.datei_eintrag`): Prüfsumme der geladenen Datei, `quelle_url` =
  der Link. Danach gilt alles wie bei Quellen (nie nach unten, Modus auto/manuell, nur die
  gebundene Quelle). Kosten: je Paket mit Datei-Link ein Download beim Start; wer das nicht
  will, stellt das Paket auf „manuell“ oder schaltet die Prüfung ab.
- **Quellenbindung** (S3) bleibt: Ein Datei-Link darf nur das Paket aktualisieren, das er
  selbst geliefert hat (`quelle_passt` vergleicht die Adresse).

## 2. Adresse am Paket

- Paketmanager, Zeile und Paketseite: „Quelle: https://…“ (Index oder Datei), auswählbar zum
  Kopieren; ohne Quelle „aus Datei“ bzw. „mitgeliefert“. Auf der Paketseite dazu „zuletzt
  geprüft …“ und der Modus (auto/manuell), wie unter Updates.
- Die Rückfrage vor jedem Import aus einem Link nennt die Adresse (steht schon da, `quelle`).

## 3. Pläne im Paket (Formatversion 3)

Pläne reisen heute nur als Vorlage eines Kurskapitels. Neu: `plaene[]` auf oberster Ebene,
dasselbe Format wie die Vorlage im Kapitel (`core.kurse.PlanVorlage`): `key` (oder `id`),
`name`, `wochentage`, `uebungen[]` (`uebung` = Schlüssel oder ID einer Übung des Pakets,
`ziel`, `felder`), dazu wahlweise `beschreibung`, `timer` (Plan-Timer wie `plan.timer_json`),
`weiter_automatisch`, `pause_ohne_timer`.

Regeln (bewusst einfacher als bei Übungen — Ben: Pläne nur mit Rückfrage, hier gewünscht):

| Fall | Was passiert |
|---|---|
| Plan-ID gibt es im aktiven Profil nicht | wird angelegt — **im aktiven Profil** (Pläne gehören dem Profil; die ID ist UUIDv5 aus Paket, `plan:<key>` und Profil, damit zwei Profile denselben Paketplan haben können) |
| gibt es, unverändert gegenüber dem Paketstand (`plan.package_standard_json`) | bekommt den neuen Stand |
| gibt es, von der Person geändert (Übungen, Ziel, Tage) | bleibt — die Paketseite zeigt „Plan geändert“, „Auf Paketstand“ setzt ihn zurück |
| im Papierkorb | bleibt dort (kein Zurückholen, wie bei Kursplänen) |
| nicht mehr im Paket | bleibt, wird nicht markiert (ein Plan ist etwas Eigenes, sobald er geübt wird) |
| Paket entfernen | seine Pläne gehen in den Papierkorb (`PaketRepo.entfernen`) |
| Paket deaktivieren | seine Pläne verschwinden aus der Liste wie die Übungen (`active = 0`, kommt mit „Aktivieren“ zurück) |
| anderes Profil später aktiv | bekommt den Plan beim nächsten Start aus dem Paketstand (`herkunft_nachtragen`-artig: `PaketRepo.plaene_nachlegen(subject_id)`), außer es hat ihn schon gelöscht (Grabstein `plan.deleted_at` + `package_id`) |

Datenmodell (Migration 032): `plan.package_id TEXT`, `plan.package_key TEXT`,
`plan.package_standard_json TEXT`. Export: der Exportdialog bekommt die Gruppe **„Pläne“**
(Checkboxen) — ein Plan nimmt seine Übungen automatisch mit (ohne Übung kein Plan). `Vorschau`
bekommt `plaene: dict[str, Status]`, die Rückfrage eine Zeile „n Pläne neu/aktualisiert“.
Das Werkzeug `trainingsapp-paket` (Inhalte-Repo) muss `plaene[]` prüfen und bauen — das
ändert Ben dort nach (eigener Commit in `trainingsapp-inhalte`).

## 4. Später: Kurs stellt den Plan aus einer Auswahl zusammen (P90, nicht gebaut)

Bens Fall: „Ein Patient bekommt 3 Übungen vorgeschlagen, wählt daraus eine aus, testet, wie
lange trainiert werden kann, bis auf der Belastungsskala 6/10 erreicht ist, und trägt den
Wert dann ein als Zeitvorgabe.“ Das sind drei Dinge, die ein Kapitel heute nicht kann:

1. **Auswahl**: Das Kapitel bietet Übungen an, die Person wählt (eine oder mehrere). —
   Kapitelfeld `auswahl: {uebungen: [key…], waehle: 1, text: "Welche fällt dir leicht?"}`;
   gespeichert im Kursfortschritt (`course_progress`, neue Spalte `auswahl_json`).
2. **Test**: Die gewählte Übung wird mit der Stoppuhr geübt, bis ein Wert erreicht ist
   (Belastung 6/10 — eine **Skala, die die Person selbst bewertet**; die App stoppt nicht,
   sie fragt nur „Wert erreicht? → Stopp“). Ergebnis: die Zeit. — Kapitelbedingung neuer
   Art `test: {uebung: <aus der Auswahl>, feld: "duration", skala: "Belastung 0–10", bis: 6}`;
   erfüllt, sobald ein Eintrag der Übung mit Zeit **und** Skalenwert da ist (die Skala wird
   ein Feld der Übung im Test-Eintrag, kein Tagesfeld).
3. **Plan mit Platzhaltern**: Die Plan-Vorlage des Kapitels nennt statt fester Übungen
   `{"uebung": "$auswahl"}` und als Ziel `{"duration": "$test.duration"}` — beim Anlegen
   setzt `plan_aus_vorlage` die Wahl und den gemessenen Wert ein (als **Zeitvorgabe** im
   Ziel; kein Prozentsatz, keine Steigerung — das wäre eine Steuerung, P68).

Was das Format **jetzt** schon reserviert, damit ein späterer Kurs nicht an einer alten App
scheitert: Ein Kapitel darf die Felder `auswahl` und eine Bedingung `art = "test"` tragen;
diese App **überliest** sie (Kapitel gilt als `gelesen`, Platzhalter-Übungen fallen aus der
Vorlage), statt die Datei abzulehnen. Formatversion bleibt 3; der Kursbau sagt in
`neuigkeiten`, ab welcher App-Version der Kurs voll läuft. Rechtlich (Solo): Auswahl und
Test sind Dokumentation der eigenen Entscheidung; der Praxis-Kurs, der daraus eine
Vorgabe macht, gehört in die Praxisanbindung (`docs/plan_praxisanbindung.md`).
