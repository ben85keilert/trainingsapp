# Plan: Herzfrequenz — zwei Sichten, Profil mit Herkunft, Bereiche (Ben, 29.10.2026)

Ben: „Wir brauchen ein Upgrade der trainingsapp hinsichtlich der Messung. HRV ist
wissenschaftlich noch nicht ausgereift, HF-basiertes Training ist weit verbreiteter. … In
der Aufzeichnung zwei Reiter Heart Rate und HRV, HR Standard, HRV als Standard einstellbar
… Ruhe-HF bestimmen (selbst eintragen, aus den Aufzeichnungen, aktive Messung) … HFmax
(Formel, Hunt am genauesten, aus Belastungstests) … HRR-Grenzen, HRR30/60 … kontinuierlich
oder nur für die Übung messen — wie lässt sich das am besten lösen.“

Konzept und Entscheidungen liegen im privaten Forschungsrepo hrv-research
(`docs/KONZEPT_HF_TRAINING.md` vom 22.10., `docs/KONZEPT_HF_APP.md` vom 28./29.10.,
`docs/ENTSCHEIDUNGEN.md` 10–18); die Rechnung in hrv-core `herzfrequenz.py`
(`docs/hrv_algorithmen.md`, Kapitel „Herzfrequenz“). Hier steht, was die App daraus baut.
Rechtsrahmen: `docs/recht/00_zweckbestimmung.md` — **anzeigen ja, bewerten nein.**

Leitsatz: **Die HF ist der Träger, nicht das Urteil.** Die App rechnet aus Werten, die die
Person kennt und bestätigt hat (Ruhe-HF, HFmax, Grenzen), und zeigt, was war. Bereiche sind
ihre Werte wie ein Timer: „Bereich 1…n“ oder eigene Namen, Stufen **einer** Farbe, kein
Ampelrot, kein „zu hoch“, kein Rat. Eine Formel setzt nie stillschweigend — sie steht als
Startwert mit „geschätzt ± 11“ dabei.

## 1. Stufe 1 — gebaut am 29.10.2026 (Version 0.3.31)

### 1.1 Zwei Sichten auf einen Messlauf (Entscheidung 10)

In der Live-Hauptkarte (`ui/views/messung.py`, `_live_teil`) steht oben der Umschalter
`[ Herzfrequenz | HRV ]` (`components/hf_sicht.sicht_wahl`). Es läuft **ein** `Messlauf`;
die Sicht ändert nur, was gerechnet und gezeigt wird. Vorgabe Herzfrequenz
(`HrvEinstellungen.standard_sicht`), die zuletzt gewählte wird gemerkt
(`sicht_merken`, Schlüssel `hrv_sicht`); reine Pulsgeber (`nur_puls`) öffnen immer die
Herzfrequenz, HRV ist dort ausgegraut.

**Herzfrequenz-Sicht** (von oben): große Zahl aus RR im 5-s-Mittel (bpm-Rückfall), daneben
% der Reserve und der Bereich; die **Skala** Ruhe-HF … HFmax mit den Bereichen als Stufen,
dem Unsicherheitsband je Grenze und dem Zeiger; **Zeit je Bereich** für den Bezug
Aufnahme · Abschnitt · 5 min (Entscheidung 15, „Fenster = Abschnitt“) mit Shortlink ⚙ zu
Einstellungen → Herzfrequenz; **Erholung**: „Belastung endet jetzt“ setzt t0 und eine Notiz
mit Marke `person/erholung` (`kontext`, `haltung` — Pflichtfelder, Entscheidung 14), dann
HF am Ende und HRR30/60/120, darunter die früheren Erholungen der Aufnahme. Die Hauptkurve
ist die HF-Kurve mit den Grenzen als gestrichelten Linien; Kacheln: Herzfrequenz, Reserve,
Zeit im Bereich, Ø, Gipfel (5-s-Mittel), Ø Reserve, TRIMP — je mit dem Bezug in der
Beschriftung. Die HRV-Analyse unter der Kurve bleibt im Baum, nur unsichtbar.

**HRV-Sicht**: die bisherige Hauptkarte unverändert.

Die Akkumulatoren (`core/hf_training.py`: `HfAkkumulator`, `LiveHf`) rechnen
**inkrementell** aus den Schlägen der Aufnahme je Sekunde (RR vor Geräte-HF derselben
Sekunde, wie `hf_reihe`), für Aufnahme und laufenden Abschnitt; sie liegen in `AppState`
(`live_hf`, Schlüssel aus Profil, Ruhe, HFmax, Grenzen) und überleben den Neuaufbau der
Ansicht. „5 min“ rechnet aus dem Live-Puffer mit `hrv_core.herzfrequenz`. Live ist das
eine Näherung ohne Artefaktkorrektur; die Auswertung rechnet nach dem Speichern auf der
Datei nach (Stufe 2).

### 1.2 Profil mit Herkunft und Wertehierarchie (Entscheidungen 11–13)

Tabelle `profil_wert` (Migration 034, `core/hf_profil.py`, `data/hf_profil.py`): je
Zeile Größe (`ruhe_hf`, `hf_max`, `hf_vt1`, `hf_vt2`), Wert, **Quelle**, Datum,
Unsicherheit, Gerät, Messung, Herkunftsliste (`herkunft_json`: woraus eine Automatik den
Wert nahm), `fest`. **Unveränderlich** wie `session_entry`: Korrektur und Festsetzen sind
neue Zeilen mit `replaces_id`; „Rückgängig“ löscht nur die neue Zeile.

Welcher Eintrag gilt, entscheidet `hrv_core.herzfrequenz.geltender_wert` (Ben: „die
genauere Variante schlägt die ungenauere … was da ist, ist verlässlicher als
Bauchgefühl“): festgesetzt › genaueste Quelle mit gültigem Eintrag, dort der jüngste ›
sonst der jüngste überhaupt. Ruhe-HF: Nacht › Morgenmessung 10 min › 5 min › Eintrag ›
Tagesminimum › Tagesfeld „Ruhepuls“. HFmax: Spiroergometrie › Ergometrie › Feld-Maximaltest
› Feldmaximum › Eintrag › **Formel als Startwert** (Nes/HUNT 211 − 0,64·Alter, Frauen
Gulati, Tanaka wählbar; ohne Jahrgang keine Formel). `HfProfil` (`core/hf_profil.py`)
bündelt die geltenden Werte, %HRR und `vollstaendig`.

`subject.geschlecht` (w/m/d, Migration 034) und der Jahrgang werden unter Einstellungen →
Herzfrequenz eingetragen — nur für Formel und TRIMP-Gewichte; „d“ und „keine Angabe“
rechnen wie Männer, mit Hinweis.

### 1.3 Bereiche (Entscheidung 13, Ben: „alle vier, einstellbar“)

`core/hf_einstellungen.py`, **je Profil** (`app_setting` `hf_einstellungen:<profil-id>`):
Modell `auto` (drei Bereiche, sobald eine eigene Schwelle aus Talk-Test oder Labor vorliegt,
sonst zehn Cluster), `drei` (Schwellen aus dem Profil, sonst 42 / 77 % HRR), `acsm`
(30 / 40 / 60 / 90 %, Leitlinienbegriffe), `cluster`, `eigen` (bis 8 Grenzen in bpm oder
% der Reserve, eigene Namen). `bereiche_fuer(profil, einstellungen)` rechnet die Grenzen
in bpm mit Unsicherheitsband (Quellfehler + anteiliger HFmax-Fehler); ohne vollständiges
Profil gibt es keine Bereiche, die Sicht sagt dann „Ruhe-HF und HFmax eintragen“.

### 1.4 Einstellungen → Herzfrequenz (`/einstellungen/herzfrequenz`)

Karten: Profil (Jahrgang, Geschlecht, Formel-Startwert) · Ruhe-HF · HFmax · Schwelle 1 ·
Schwelle 2 (je: geltender Wert mit Quelle, Datum, ±; Verlauf mit Festsetzen/Lösen und
Entfernen; Formular Wert · Datum · Herkunft · Notiz; bei den Schwellen die Milani-Schätzung
als Hinweis, wenn eine gemessene HFmax vorliegt) · Bereiche (Modell, Vorschau mit Band,
eigene Grenzen, Formelwahl; „i“: Welcher Wert gilt?) · Sicht (Vorgabe, merken) · Nicht
mitgerechnet. Zeile „Herzfrequenz“ unter Einstellungen → Messung und Werkzeuge.

### 1.5 Feste Tagesfelder und Rechen-Ausnahmen (Ben, Fragen 1 und 5)

Die Standardfelder sind **fest** (`day_field.fest`): Anstrengung (sRPE, Skala 0–10,
Tageswert Höchster), Blutdruck, Gewicht, Ruhepuls (Messwert bpm, Tageswert Niedrigster),
Störung (Ja/Nein mit Varianten Infekt, Alkohol, Hitze, Reise, wenig Schlaf) — nicht
löschbar (`TagesfeldRepo.loeschen` wirft, langes Drücken sagt es), nur ausschaltbar, bei
jedem Profil angelegt (ausgeschaltet). Bisher gelöschte Standardfelder kommen durch die
Migration ausgeschaltet zurück. Die Kopplung (Morgenmessung → Vorschlag ins Feld
„Ruhepuls“, Eintrag im Feld → Profil mit Quelle `tagesfeld`, sRPE nach der Einheit) kommt in
Stufe 2.

Tabelle `rechen_ausnahme` (`RechenAusnahmeRepo`): Tag, Einheit, Messung oder Strecke, die
„nicht mitgerechnet“ wird (Baseline, Median, Feldmaximum). Datenlage und Liste in den
Einstellungen sind da; das lange Drücken am Tag und an der Einheit kommt mit den ersten
Automatiken (Stufe 2/3).

### 1.6 Sonstiges

- Unterreiter unter Aufzeichnungen heißt **„Messungen“** (dort liegen auch reine
  HF-Aufnahmen; Frage 7).
- `core/einheit.py`: Art `erholung` und Datenschlüssel `kontext`/`haltung` in der Zeitleiste;
  hrv-core `MARKE_FELDER` um beide erweitert (Vertrag §4).
- Hilfe-Thema „herzfrequenz“ (`components/hilfe.py`), Info-Text der Sicht
  (`hf_sicht.HF_INFO`).
- hrv-core 0.4.0 (Arbeitskopie): Modul `herzfrequenz`, `Recording.dauer_s` fällt bei reinen
  Pulsgebern auf die Wanduhr zurück (Befund B2), `bpm_only`-Fixture mit Golden. Kein Sprung
  der `ALGO_VERSION` (keine bestehende Zahl ändert sich). `hrv-core.ref` wird angehoben,
  sobald der Stand auf `origin/main` liegt.

## 2. Stufe 2 — gebaut am 29.10.2026

- **Auswertung `/messung/<id>`** (`components/hf_auswertung_sicht.py`, Kontext aus
  `views/messung_detail.py`): derselbe Umschalter; dahinter Kacheln der Aufnahme (Ø, Gipfel als
  5-s-Mittel, Minimum, gültige Zeit, Ø Reserve, TRIMP, HF je Tempo), die HF-Kurve mit Grenzen
  und Abschnittsbändern, Zeit je Bereich, **Abschnittstabelle** (Ø, Gipfel, Ø Reserve, HRR60 am
  Ende, wenn die HF danach fällt; Drift ab 20 min; Entkopplung mit Strecke), Erholungen aus den
  Marken, **Vorschläge fürs Profil** (Ruhe-HF einer 4–20-min-Messung als tiefstes 30-s-Mittel →
  Profil oder Tagesfeld „Ruhepuls“; HFmax als höchstes 30-s-Mittel mit Plateau; Talk-Test-HF →
  Schwelle 1; Nacht-HF eines Abschnitts „Schlaf“), **vorgeschlagene Abschnitte** aus der HF
  (Belastung, Ruhe, Schlaf) mit „Übernehmen“ (Notizpaar + Sidecar wie „+ Abschnitt“),
  Tagesprofil ab 16 h, sRPE-Zeile, „Diese Messung nicht mitrechnen“.
- **Rechnung** `core/hf_auswertung.py` (`auswerten`, Wanduhr; `achse_zu_wand` für Abschnitte),
  **Cache** `hf_cache` (Migration 035, `data/hf_cache.py`) mit `algo_version` und
  `profil_stand`: alte Aufnahmen behalten ihr damaliges Profil; „Mit heutigem Profil
  nachrechnen“ zeigt neu, „Speichern“ fragt (Frage 4).
- **Talk-Test live**: Knopf „Sprechen wird schwer“ in der HF-Sicht setzt die Marke
  `person/talk`; die Auswertung bietet die HF der 30 s davor als Schwelle 1 an.
- **Tests im Paket Standard** (trainingsapp-inhalte `pakete/standard.toml` Version 3 und die
  Seed-Kopie): „Ruhe-HF morgens (10 min)“, „Submaximaltest“ (Stufen 6/6/3 min + 1 min Stehen),
  „Talk-Test (Steigerung)“ (6 × 3 min), „Feld-Maximaltest“ (10 min Einlaufen, 3 × 3 min,
  1 min Alles, 1 min Stehen; Hinweis in der Beschreibung — ein Feld für Pflichthinweise gibt es
  im Paketformat nicht).
- **sRPE** (`components/srpe.py`): Zeile mit den Stufen 0–10 nach einem Plan-Ablauf
  (`plan_ablauf.danach`) und in der HF-Sicht der Auswertung; schreibt ins feste Tagesfeld
  „Anstrengung (sRPE)“. Kein Dialog.
- **Tagesfeld „Ruhepuls“ → Profil**: Einträge der letzten 14 Tage zählen als Quelle
  `tagesfeld` (Rang zuletzt), ohne gespeichert zu werden (`core/hf_profil.tagesfeld_eintraege`).
- **„Nicht mitrechnen“**: im Zielblatt der Messungs- und Streckenliste (langes Drücken), im
  ⋮-Menü der Tagesansicht und als Schalter in der HF-Sicht der Auswertung.

## 3. Stufen 3 und 4 — gebaut am 29.10.2026

- **Verlauf → Herzfrequenz** `/verlauf/herzfrequenz` (`views/verlauf_herzfrequenz.py`, Link
  unter Einstellungen → Herzfrequenz): Ruhe-/Nacht-HF je Quelle als Punkte mit Baseline
  (Median der letzten 7, Band ± 1 SD gestrichelt; ausgenommene Tage zählen nicht),
  **Wochenlast** (Σ TRIMP, Σ sRPE-Last, Minuten, Monotonie, Strain nach Foster — Zahlen),
  **Tests** (Submaximaltest: HRR60 nach „Stufe 3“ und Ø „Stufe 2“; Talk-Test; Feld-Maximaltest:
  HFmax-Kandidat), „Alle nachrechnen“ für Aufnahmen ohne Cache. Rechnung `core/hf_verlauf.py`.
- **Nacht-HF**: ein Abschnitt „Schlaf“ (auch aus dem HF-Vorschlag) liefert das tiefste
  2-h-Mittel; übernommen wird es als Ruhe-HF mit Quelle `nacht` (Rang 1 nach Festsetzung).
- **Kacheln**: Gruppe „Herzfrequenz“ (Reserve, Bereich, Zeit im Bereich, TRIMP) auch in der
  HRV-Sicht (`components/kacheln.py`, Bezug Aufnahme bzw. 5 min).
- **Uhr**: Seite „Bereich“ (Name des Bereichs, % der Reserve, HF) in `core/uhr_seiten.py`,
  gerechnet im 5-s-Takt (`ui/geraete/flet_medien_kanal.py`); unter Einstellungen → HRV-Messung
  → Uhr am Handgelenk ankreuzbar (bestehende Auswahl bleibt, wie sie ist).
- **Forschungsexport**: je Aufnahme `…_hf.json` (`hf-auswertung-v1`: Profilstand, Werte,
  Abschnitte, Erholungen, Kandidaten) aus dem Cache (`ui/training._forschung_teile`).

Offen (bewusst, Fragen 1b/11/`hf_spec`): Signalton an einer eigenen Grenze, Behandlungs-
Dreiteilung in solo, HF-Vorbelegung je Übung.

## 4. Was Stufe A/B/C heißt (Rechtsrahmen)

| Stufe | Bedeutung | In dieser App |
|---|---|---|
| A | Rechnung aus Werten, die die Person eingetragen oder bestätigt hat; Darstellung ohne Urteil | alles in Stufe 1: HF, %HRR, Zeit je Bereich mit benannten Bereichen, HRR als Zahl, TRIMP als Zahl |
| B | vorbelegte Grenzen (erlaubt, Ben 29.10.), Formel-Startwert (so beschriftet); Signalton an eigener Grenze (offen) | Bereichsmodelle, Formel „geschätzt ± 11“ |
| C | Vorgabe, Bewertung, Hinweis — nur zweite App / praxis_gui | Obergrenze vom Therapeuten, Flags, Normgrenzen HRR, Alarme — hier nicht gebaut |
