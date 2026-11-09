# Timer stellen: für jetzt mit Abschnitten, Editor mit Reitern Zeiten · Klänge

Stand: 9.11.2026 — **gebaut (0.3.73)**, Ben: „Zu Timern, alles so wie vorgeschlagen. Bau das
so“ — S1–S3, P151–P154 wie vorgeschlagen (§5). Skizzen: **Reihe G (G1–G5)** auf der Fläche der
Uhren (https://claude.ai/artifact/THG2KrMi4jET9N2XkHRk3J, unter Reihe F). Am Gerät: T107.

## 0. Anlass

Ben, 9.11.2026, zu zwei Bildschirmfotos (Uhr-Blatt „Für jetzt“, „Neuer Timer der Übung“):

1. „beim Übungstimer lässt sich für den Einmaltimer kein Timer setzen mit mehreren Abschnitten.
   Ermögliche den Abschnittstimer auch dort. Der wird dann nicht gespeichert, außer man klickt
   auf den Button. Standardmäßig kommt ein ‚Zeit stellen‘ Doppeldrehbereich für min:ss. Mit
   einem Button soll man in ein erweitertes Fenster kommen.“
2. „Die Timereinstellung ist ziemlich hässlich“ — Erklärtext ins „i“; Abschnitte und Klänge
   trennen (je Abschnitt Name, Zeit, zählt, entfernen in einer Zeile, Takt-Symbol links vom
   Uhrsymbol, ein Takt darunter in einer zweiten Zeile); zwei Reiter Zeiten · Klänge, der Reiter
   Klänge spiegelt die Zeiten mit gleichen Namen, Wischen wechselt — „am besten auf die gleiche
   Höhe … ist das umsetzbar?“; „Abschnitt hinzufügen“ bleibt unter den Abschnitten; Teile
   kopieren (Symbol neben dem Mülleimer); Gesamtzeit je Teil mit „Runden − X +“ in einer Zeile;
   Gesamtzeit des ganzen Timers oben rechts neben dem Namen, fest beim Scrollen; „finde eine
   Möglichkeit, das Layout schöner zu gestalten, am besten Skizzen“.

## 1. Für jetzt mit Abschnitten (G1, G2)

- **G1:** „Für jetzt → Zeit stellen …“ öffnet wie heute das Zeit-Blatt (Räder min:ss,
  Schnellzeiten, Tippfeld, `components/zeit_stellen.zeit_blatt`). Neu darunter die Zeile
  **„Mit Abschnitten …“** — sie schließt das Blatt und öffnet das erweiterte Fenster.
- **G2:** Das erweiterte Fenster ist **derselbe Editor** wie G3 (Reiter, Zeilen, Teile, Takt,
  Ausführung je Abschnitt), ohne Namen, Titel „Für jetzt · <Übung>“. **„Übernehmen“** stellt den
  Timer für jetzt — gilt wie heute die gestellte Zeit, bis die App neu startet, nichts kommt in
  die Datenbank. **„Als Timer der Übung speichern …“** fragt nach dem Namen und hängt ihn an die
  Übung (wie „+ Neuer Timer“ unter „Übung“) — nur dieser Knopf speichert.
- Technisch: `AppState.uhr_einmal[key]` hält künftig ein `TimerProfil` statt Sekunden (eine
  gestellte Zeit = ein Profil mit einem Abschnitt, `einmal_timer`); ein `Profilziel` „für jetzt“
  (`views/timer.py`) schreibt dorthin, `als_profil` an die Übung. `components/uhr.gesetzt`
  liest das Profil.

## 2. Der Editor (G3–G5)

**Fest oben** (scrollt nicht): Name des Timers und rechts daneben die **Gesamtzeit** des ganzen
Timers („6:30 gesamt“), darunter die Reiter **Zeiten | Klänge** und das **i** (der Erklärtext,
der heute als Absatz über den Abschnitten steht, kommt nach `components/hilfe.py`).

**Reiter Zeiten (G3)** — je Teil eine Karte:
- Kopf: Name des Teils (randloses Feld), **Kopieren** (der Teil noch einmal dahinter) und
  **Papierkorb**.
- Je Abschnitt **eine Zeile**: Name (randloses Feld) · **Takt-Knopf** (gefüllt, wenn der
  Abschnitt einen Takt hat; öffnet das Takt-Blatt) · **Zeit** (⏱ 0:30, öffnet das Zeit-Blatt) ·
  **zählt** (Chip; durchgestrichen = zählt nicht) · **entfernen**.
- Zweite Zeile, nur wenn es etwas gibt: der **Takt** („Atem 4 · 4 — nur in diesem Abschnitt“, ✎)
  und — an Timern einer Übung mit Ausprägungen — die **Ausführung** (Links · Rechts · Beide,
  Gewicht …).
- **„Abschnitt hinzufügen“** unter den Abschnitten.
- Fußzeile: **Gesamtzeit des Teils** („6:00 · 8 × 0:45“) und **Runden − 8 +** in einer Zeile.
- Unter den Karten „Teil anhängen“ und (mit Ausführung) die Vorschau „je Ausführung ein
  Eintrag“.

**Reiter Klänge (G4)** — dieselben Karten und Zeilen **auf derselben Höhe**:
- Je Abschnitt rechts der **Klang** (Auswahl spielt vor) und ▶ Vorspielen; der Name steht dort,
  wo er unter „Zeiten“ steht.
- Zweite Zeile: beim Takt „Klang je Phase“ (✎ öffnet das Takt-Blatt).
- Der Platz von „Abschnitt hinzufügen“ bleibt frei; die Fußzeile zeigt nur Gesamtzeit und
  Runden.
- Unten eine Karte **für den ganzen Timer**: Klang zu Beginn jeder **neuen Runde**
  (`runden_klang`) und **am Ende** (`ende_klang`), dazu **„Signale ›“** zu Countdown, Vibration
  und Lautstärke aller Timer (`timer_signale_view`).

**Wischen (G5)** — umsetzbar, und zwar so, dass die Höhe nie springt: Es gibt **eine**
Scrollfläche, keine zwei Seiten. Jede Zeile hat links den Namen und rechts beide Teile
nebeneinander in einem beschnittenen Container; ein Wechsel verschiebt sie mit `offset` und
`animate_offset` (Flet 1.0.3 — `AnimatedSwitcher` kann nur überblenden, drehen, skalieren). Eine
Wischgeste über der Liste (`GestureDetector.on_horizontal_drag_end`, Richtung aus
`primary_velocity`) oder ein Tipp auf den Reiter schiebt alle rechten Spalten auf einmal. Die Zeilen haben feste Höhen (48 · 30 · 40 · 48 px), Zeilen, die es nur in
einem Reiter gibt, lassen im anderen ihren Platz frei — Abschnitt Y steht nach dem Wischen genau
dort, wo er war.

## 3. Umsetzung

- Der Editor bleibt in `ui/views/timer.py` (`timer_bearbeiten_view`) — ein eigenes Modul hätte
  die Klang-Helfer der Signale-Seite mitziehen müssen. `_Zeile`/`_TeilFelder` halten jetzt
  **Werte** (Name, Klang als Text), keine Controls: Jeder Aufbau legt Felder neu an, ein
  umgehängtes Textfeld nähme in Flet 1.0 keine Eingaben mehr an. Die Höhen (`KOPF_H`, `ZEILE_H`,
  `ZUSATZ_H`, `FUSS_H`) sind in beiden Reitern gleich; die rechte Spalte (`RECHTS_B`) liegt als
  Stapel mit zwei Teilen, die `offset`/`animate_offset` schieben; Wischen ab 250 px/s
  (`WISCH_V`). „Signale ›“ öffnet die drei Karten der Signale-Seite als Blatt.
- `core/timer.py`: keine neue Datenform — Kopieren eines Teils ist eine tiefe Kopie
  (`Teil`, `Abschnitt` mit Takt und Ausführung).
- Uhr-Blatt (`components/uhr_blatt.py`) und Zeit-Blatt: Parameter `erweitert` am `zeit_blatt`
  für „Mit Abschnitten …“ (bekommt die gestellte Zeit, `AppState.uhr_einmal_start`) — im Uhr-Blatt
  „Für jetzt“, beim Tipp auf die Zeit der Uhr-Zeile und im Timer der Übung (P153). Das Uhr-Blatt
  zeigt eine gestellte Uhr als Zeile „Für jetzt“ mit ✎ (nur in der Geltung „Für jetzt“
  wählbar).
- Tests: Editor (Reiter, Wischen, gleiche Zeilen in beiden Reitern, Kopieren, Gesamtzeiten,
  i), Uhr-Blatt (für jetzt mit Abschnitten, nichts gespeichert, Speichern nur per Knopf).

## 4. Stufen

| Stufe | Inhalt | Skizzen |
|---|---|---|
| S1 | Editor: fester Kopf mit Gesamtzeit, i, eine Zeile je Abschnitt, Takt-/Ausführungszeile, Fußzeile je Teil, Teile kopieren | G3 |
| S2 | Reiter Klänge, Wischen, Klänge für den ganzen Timer | G4, G5 |
| S3 | Für jetzt mit Abschnitten | G1, G2 |

## 5. Fragen (Katalog P151–P154) — entschieden 9.11.2026 wie vorgeschlagen

- **P151** Kopieren: nur Teile (Symbol neben dem Papierkorb) — oder auch einzelne Abschnitte,
  per langem Druck auf die Zeile (Kopieren · Entfernen)? Vorschlag: beides; die Zeile bleibt
  ohne weiteres Symbol.
- **P152** Unter „Klänge“ die Namen nur lesen (Vorschlag) — umbenannt wird unter „Zeiten“.
- **P153** „Mit Abschnitten …“ auch dort, wo das Zeit-Blatt sonst für jetzt aufgeht (Tipp auf
  die Zeit in der Uhr-Zeile der Übung)? Vorschlag: ja, überall dort; nicht im Editor selbst (dort
  stellt das Blatt nur die Dauer eines Abschnitts).
- **P154** „zählt“ als Chip in der Zeile, durchgestrichen = zählt nicht (Vorschlag) — oder nur
  ein Häkchen-Symbol, damit der Name mehr Platz hat?
