# Uhren: Stoppuhr, Timer, Takt — ein Ort, eine Sprache, eine Bedienung

Ben, 7.11.2026: „Mach eine Überprüfung der Konsistenz und einer guten Logik des
Timers/Stoppuhr: Auffindbarkeit/Lokalisation der Uhrenorte · Vereinheitlichung der UX · Im
Plan: wenn Übungen Uhren haben, diese zusammenlegen und editieren können in einer View
(+Taktung) · bessere Bedienbarkeit.“ Dieses Dokument ist der Plan dazu (8.11.2026); der Befund
steht in §1, die Vorschläge ab §2, die Stufen in §6. Was eine Entscheidung von Ben braucht,
ist mit **▶ P101 …** markiert und im Katalog (`docs/offene_fragen.md`) eingetragen.

Verwandte Verträge: `plan_stoppuhr.md`, `plan_hrv_timer.md`, `plan_einheit.md` §7,
`plan_taktgeber.md`, `plan_uebungen_einstellen.md`, `plan_planblock.md`, `plan_workout.md`.

## 1. Befund (Kurzfassung)

Heute gibt es **neun Orte**, an denen Uhren vorkommen, mit je eigenem Vokabular und eigenen
Knöpfen:

| Ort | Was man dort tun kann | Problem |
|---|---|---|
| Timer-Seite `/timer` (Pille oben) | Stoppuhr · Einmal-Timer · Profile; Editor; Signale; Karte „Ablauf öffnen“ im Plan | Pille fehlt im Plan-Editor, Workout, Übungsseite, Einstellungen; Ausdauer hat einen eigenen Knopf ohne Restzeit |
| Uhr in der Übung (Zeile oder Knöpfe) | Wahl ▾, Zeit stellen, „zählt“, Takt, Bereitstellen, ▶; laufend: Anhalten/Weiter, Fertig, ✕, ⤢ | „Knöpfe“ können weniger als die Zeile; laufend kein Abschnitt-Sprung, keine Takt-Wahl |
| Timer der Übung `…/timer/uebung/…` | Vorher · Fokus · Danach | kann nichts dauerhaft festlegen („ändern: in Übung bearbeiten“ ohne Link); Chips ohne Stoppuhr; Stoppuhr an der Planübung zeigt „720:00“ |
| Übung bearbeiten → „UHR UND TIMER“ | Uhr an/aus, Timerzeit zählt, Zählt als, Profile (↑, Stift, 🗑), Takt, „Timer hinzufügen“ | „Darstellung der Uhr“ springt an den Anfang der Einstellungen |
| Im Plan einstellen → „UHR UND TIMER“ | Uhr an/aus/wie Übung, Timer-Zeile (nur Anzeige), „Anderen Timer nur hier“, Takt | die eigene Kopie ist **nirgends** bearbeitbar (Route existiert, kein Knopf); „Wie die Übung“ zeigt den Plan-Timer |
| Plan-Editor → Karte „Workout und Ablauf“ | Workout, Übergang, „Timer für alle“, Tipp/auto, Pause/gleich | **keine Sicht auf die Uhren aller Planübungen** — je Übung nur der Untertitel „Timer: …“ |
| Ablauf `/plan/<id>/timer/ablauf` | Übung für Übung, Checkboxen, HRV, Pause-Schalter | zweiter Einstieg zum selben Motor wie das Workout; Laufleiste führt bei Workouts hierher |
| Workout `/plan/<id>/workout` | Übergang, Schritte mit Bedingung, Fokus | Timer je Schritt nur Anzeige; Takt/Sensor werden nicht angebracht (P99) |
| Einstellungen | Uhr-Darstellung, Fokus-Schalter, Vibration; „Timer“ → Timer-Seite; Messung → „Ablauf“ = Timer-Profil | Hinweis nennt „Übung bearbeiten → Timer“, der Abschnitt heißt „Uhr und Timer“ |

**Begriffe** — dieselbe Sache hat mehrere Namen, derselbe Name mehrere Sachen: *Uhr* (Oberbegriff,
Knopf = Stoppuhr, Armbanduhr, Uhrzeit) · *Timer* (Seite, Reiter, Profil, Oberbegriff) · *Profil*
(Timer, Benutzer, HF) · *Einmal-Timer / Einzeltimer / „ohne Ablauf“* · *Ablauf* (sechs
Bedeutungen) · *Weiter* (fortsetzen, nächster Abschnitt, nächster Schritt) · *Pause/Weiter* vs.
*Anhalten/Weiter* vs. *Anhalten/Fortsetzen* · *Nochmal* vs. *Noch einmal* · *zählt* in drei
Bedienformen an vier Orten · *Takt* mit vier Speicherknöpfen.

**Fehler** (aus dem Code gelesen): Laufleiste und Einheit-Karte öffnen bei einem Workout die
Ablauf-Ansicht; die Stoppuhr an einer Planübung zeigt im Übungs-Timer 12 h; zwei Einmal-Timer
tragen dieselbe ID; das Timer-Symbol ist auf der Übungsseite anders gefüllt als im Planblock;
der Kommentar zu „Uhr im Editor“ in `plan.py` widerspricht dem Code.

## 2. Leitsätze

1. **Ein Wort je Sache.** Glossar in §3; es gilt in App, Hilfe, Doku und Katalog.
2. **Ein Ort je Aufgabe.** Benutzen (die Uhr in der Übung, der Fokus), Einstellen (Übung
   bearbeiten · Im Plan einstellen · der Uhrenplan des Plans), Werkzeug (die Timer-Seite für
   Uhren ohne Übung) — und jeder Ort sagt, wohin die anderen führen.
3. **„Für jetzt“ sieht immer gleich aus:** ein Chip mit ↺, der beim Ende der Sitzung verfällt;
   dauerhaft ist nur, was in Übung bearbeiten, Im Plan einstellen oder dem Uhrenplan steht.
4. **Dieselben Knöpfe überall:** eine laufende Uhr hat genau die Knöpfe Pause · Weiter ·
   Nächster · Fertig · Abbrechen — in der Übung, im Fokus, im Workout, auf der Timer-Seite.
5. **Keine zwei Einstiege für einen Motor.** Ablauf und Workout werden eins.

## 3. Glossar (Vorschlag) ▶ P101

| Begriff | Bedeutung | Ersetzt |
|---|---|---|
| **Uhr** | Oberbegriff: Stoppuhr oder Timer einer Übung („Uhr an/aus“, „Uhr beim Üben“) | „Stoppuhr und Timer beim Üben“ |
| **Stoppuhr** | zählt vorwärts | Knopf „Uhr“ |
| **Timer** | zählt herunter — einer oder mehrere Abschnitte | „Timer-Profil“, „Einzeltimer“, „Folge“ |
| **Zeit stellen** | ein Timer mit nur einer Dauer, für jetzt | „Einmal-Timer“, „Timer ohne Ablauf“, „Einmaluhr“ |
| **Abschnitt**, **Runde**, **Teil** | wie heute im Timer; der Messabschnitt heißt in der Messung weiter so (anderer Kontext) | — |
| **Vorlage** | ein gespeicherter Timer in der Bibliothek (Reiter „Vorlagen“) | „Profil“ — das Wort bleibt dem Benutzer- und dem HF-Profil |
| **Takt** | Phasenfolge mit Tempo | „Taktgeber“ (nur Doku) |
| **zählt** | die Zeit geht in den Eintrag — als Chip (für jetzt) oder Schalter (dauerhaft), nie als TextButton | — |
| **Workout** | der Plan läuft von vorn bis hinten | „Ablauf“ in allen sechs Bedeutungen: die Abschnittsliste heißt „Abschnitte“, die Messdauer „Timer“, „nach Ablauf“ → „nach dem Ende“ |
| **Pause / Weiter** | anhalten / fortsetzen — nur dafür | „Anhalten/Fortsetzen“ |
| **Nächster** (⏭) | zum nächsten Abschnitt | „Weiter“ im Fokus |
| **Nächste Übung** | im Workout zum nächsten Schritt | „Weiter: X“ |
| **Fertig / Abbrechen** | beenden und eintragen / beenden ohne Eintrag | ✕ ohne Wort |
| **Noch einmal** | — | „Nochmal“ |
| **Starten / Bereitstellen / Alle starten** | wie heute | „Start“ |

## 4. Zielbild je Ort

### 4.1 Die Timer-Pille — ein Werkzeug, überall gleich
- Pille in **jeder** AppBar (auch Plan-Editor, Workout, Übungsseite, Einstellungen, Ausdauer),
  immer mit Restzeit, immer `<route>/timer`. Der eigene Knopf in Ausdauer entfällt.
- Timer-Seite: Reiter **Stoppuhr · Zeit · Vorlagen**; die Karte „Ablauf“ heißt
  **„Abschnitte“**; die Plan-Karte „Ablauf öffnen“ wird **„Als Workout starten“** (§4.6).
- Untere Leiste auch auf `/timer`, Editor und Signale (heute weg) ▶ P102.

### 4.2 Die Uhr in der Übung — eine Darstellung
- Die Einstellung „Zeile/Knöpfe“ entfällt; es bleibt die **Zeile** (sie kann alles) ▶ P103.
  Alternativ die Knöpfe um Bereitstellen und Zeit stellen ergänzen — mehr Code für weniger
  Klarheit.
- Laufende Karte bekommt **⏭ Nächster** (Abschnitt) und den **Takt-Knopf** (Takt für jetzt
  wie auf der Timer-Seite); Knöpfe Pause · Weiter · Nächster · Fertig · Abbrechen (Glossar).
- Der Fokus (⤢) ist dieselbe laufende Uhr, nur groß — gleiche Knöpfe, gleiche Reihenfolge.

### 4.3 Der Übungs-Timer wird die „Uhr dieser Übung“
- Chips: **Stoppuhr · Zeit stellen · Timer der Übung … · Plan-Timer**, wie das ▾ der Zeile
  (eine Quelle: `core.uebung_timer.profile_zur_wahl` mit Stoppuhr).
- Ohne Timer trotzdem **Starten** (Stoppuhr) statt nur Hinweis.
- Profil-Karte mit **Link „In der Übung festlegen“** (→ Übung bearbeiten, Abschnitt Uhr) bzw.
  **„Im Plan einstellen“**; die eigene Kopie der Planübung bekommt den **Stift** (Route gibt es,
  `uebung_timer.py` Editor-Ziel „Timer der Planübung“).
- Stoppuhr an der Planübung: keine „720:00“ — `dauer_text` der Stoppuhr ist „—“/„0:00“.

### 4.4 Übung bearbeiten → „Uhr“
- Abschnitt heißt **„UHR“**; Schalter „Uhr beim Üben“, „zählt“ (Schalter), „Zählt als“, Takt,
  Timer-Liste wie heute. „Darstellung der Uhr“ entfällt mit 4.2 (sonst Sprung an die Stelle).

### 4.5 Im Plan einstellen → „Uhr“
- Dieselbe Ordnung wie 4.4 (P107-Regel): Uhr beim Üben · Timer (mit **Stift** zur eigenen Kopie)
  · Takt · **zählt** als Planübungs-Wahl ▶ P104 (D2 hatte „nur für jetzt“ festgelegt — mit dem
  Uhrenplan lohnt eine dauerhafte Wahl je Planübung).
- Dialog „Anderen Timer nur hier“: „Wie die Übung“ zeigt den Timer **der Übung**, der
  Plan-Timer steht als eigene Zeile.

### 4.6 **Der Uhrenplan des Plans** — Bens Kernwunsch
Neue Ansicht `/plan/<id>/bearbeiten/uhren` (Knopf „Uhren“ im Plan-Editor, Symbol ⏱ in dessen
AppBar; Vertrag hier):

```
Uhren · Plan „Beine“                                  Workout ▾  Übergang weich ▾
Timer für alle: — ▾        Takt für alle: — ▾        [Signale ⚙]
┌────────────────────────────────────────────────────────────────────┐
│ 1  Hüftbeuger dehnen   Uhr an   Halten 2×30 s ▾   Takt: — ▾   zählt ✓  Zeit ab      │
│ 2  Kniebeuge           Uhr an   Satz 30 s ▾       Kniebeuge ▾ zählt ✓  15 Wdh. (B)  │
│ 3  Planke              Uhr an   45 s ▾            Atmung 4-6 ▾ zählt ✓  hart 🔒       │
│ 4  Katze–Kuh           Uhr aus  —                 —           —        abhaken      │
└────────────────────────────────────────────────────────────────────┘
Gesamt etwa 14 min · 3 mit Timer · 2 mit Takt                     [Alles wie die Übung ↺]
```
- Je Zeile: **Uhr** (an/aus/wie Übung), **Timer** (▾: wie Übung · Stoppuhr · Timer der Übung ·
  Plan-Timer · Vorlage als Kopie · Stift = Editor der Kopie), **Takt** (▾: wie Übung · Vorlagen ·
  Bibliothek · keiner · Stift = Takt-Blatt), **zählt** (Schalter, P104), **Bedingung**
  (Kurztext, Tipp → Karte „Weiter, wenn …“ als Blatt). Schild „nur hier“ je Zelle wie heute,
  ↺ je Zeile.
- Kopf: Workout-Schalter und Übergang (aus „Workout und Ablauf“), **Timer für alle**, neu
  **Takt für alle** (ein Takt für Planübungen ohne eigenen — gleiche Vorrangstufe wie der
  Plan-Timer ▶ P105), Signale.
- Alles speichert sofort je Zelle (`PlanRepo.item_speichern`, `workout_setzen`,
  `plan_timer_setzen`); Zurück ist nur Zurück. Die Karte „Workout und Ablauf“ im Plan-Editor
  wird zur Zeile „Uhren: 3 Timer · 2 Takte · Workout weich ›“.
- Im Planblock (Üben) bleibt alles, wie es ist; der Untertitel nennt **Timer und Takt**.

### 4.7 Workout und Ablauf werden eins
- `views/plan_ablauf.py` (Ansicht) entfällt; der Motor bleibt. Einstiege („Ablauf öffnen“ auf
  der Timer-Seite, Heute → „Start“, Ziel „Ablauf starten“, Laufleiste, Einheit-Karte) führen
  zum Workout (`einheit.teil_route`). Die Checkboxen „heute erledigt“ und „Mit dabei: HRV“ des
  alten Vorher-Bilds wandern ins Workout-Start-Bild (die Checkboxen gibt es dort schon).
- „Pause auch nach Übungen ohne Timer“ und „Auf Tipp warten/automatisch“ gehen im Übergang
  hart/weich auf ▶ P106 (weich = Tipp, hart = automatisch; ohne Timer immer Tipp).
- Takt und Sensor werden je Schritt angebracht wie beim Übungs-Timer (P99).

### 4.8 Takt — ein Blatt, vier Geltungen
- Das Takt-Blatt bekommt oben **Reiter nach Geltung**, je nach Ort vorbelegt: *Für jetzt* ·
  *Übung* · *Planübung* · *Abschnitt*. Ein Speicherknopf („Übernehmen“) statt vier.
- Takt-Bibliothek: Reiter „Vorlagen“ der Timer-Seite bekommt einen Unterreiter **Takte**
  (umbenennen, löschen, Reihenfolge) — heute nur befüllbar.
- Takt-Knopf auch in der laufenden Uhr und im Fokus (4.2).

### 4.9 Kleine Fehler (sofort)
- Laufleiste/Einheit-Karte → Workout statt Ablauf (`einheit.teil_route`).
- Stoppuhr an Planübung: „720:00“.
- Einmal-Timer: zwei Dinge, eine ID — `EINMAL_SITZUNG` für `uhr_einmal`.
- Timer-Symbol einheitlich nach `timer_fuer` füllen (Übungsseite wie Planblock).
- `plan.py` Kommentar zu „Uhr im Editor“ an den Code angleichen.
- Hinweise: Einstellungen → „Übung bearbeiten → Uhr“; „Darstellung der Uhr“.

### 4.10 Doku nachziehen
`plan_stoppuhr.md` §3/§6, `plan_einheit.md` §7, `plan_taktgeber.md` §5/§11, T31/T34/T52/T53
im Katalog, `hilfe.UHR_MD`/`TAKT_MD`/`KNOPF_LEGENDE`.

## 5. Was sich dadurch vereinfacht

- Von neun Orten bleiben **fünf**: Zeile in der Übung (Benutzen), Fokus (Benutzen groß),
  Timer-Seite (Werkzeug), Übung bearbeiten → Uhr und Im Plan einstellen → Uhr (Einstellen je
  Übung), **Uhrenplan** (Einstellen je Plan). Workout ist die laufende Form des Plans.
- Jede Uhr lässt sich an **einem** Ort dauerhaft festlegen, und von jedem Benutz-Ort führt ein
  Link dorthin.
- Zwei Darstellungen, zwei Ablauf-Ansichten, vier Takt-Speicherknöpfe, drei Wortpaare fürs
  Anhalten und sechs Bedeutungen von „Ablauf“ entfallen.

## 6. Stufen

| Stufe | Inhalt | Aufwand | Braucht |
|---|---|---|---|
| **K0** | Fehler aus 4.9, Pille überall (4.1 ohne Reiter-Umbenennung), Doku-Nachzug | klein | — |
| **K1** | Glossar in der Oberfläche: Knopfworte, Reiter „Zeit/Vorlagen“, „Abschnitte“, „zählt“ als Chip/Schalter, Hilfetexte | mittel | **P101** |
| **K2** | Uhr in der Übung: eine Darstellung, ⏭ und Takt in der laufenden Karte, Fokus mit denselben Knöpfen; Übungs-Timer mit Stoppuhr-Chip, Links, Stift für die Kopie | mittel | **P103** |
| **K3** | **Uhrenplan** `/plan/<id>/bearbeiten/uhren` mit Takt für alle, zählt je Planübung | groß | **P104, P105** |
| **K4** | Workout und Ablauf eins; Takt/Sensor im Workout (P99) | mittel | **P106** |
| **K5** | Takt-Blatt mit Geltungs-Reitern, Takt-Bibliothek verwalten | mittel | — |

Skizzen (Handy-Bilder) lohnen für K2 (laufende Karte/Fokus) und K3 (Uhrenplan) — vor dem Bau.

## 7. Entscheidungen für Ben (Katalog)

- **P101** Glossar §3 — so übernehmen? Insbesondere: „Vorlage“ statt „Timer-Profil“, „Zeit
  stellen“ statt „Einmal-Timer“, „Pause/Weiter/Nächster“, „Workout“ statt „Ablauf“.
- **P102** Untere Leiste auf Timer-Seite, Editor und Signalen zeigen?
- **P103** Darstellung „Knöpfe“ entfernen (nur die Zeile)?
- **P104** „zählt“ dauerhaft je Planübung (hebt D2 teilweise auf)?
- **P105** „Takt für alle Übungen“ am Plan, gleiche Stufe wie der Plan-Timer?
- **P106** „Auf Tipp warten/automatisch“ und „Pause ohne Timer“ im Übergang hart/weich aufgehen
  lassen (Migration: `auto_next` → `uebergang_hart`)?
