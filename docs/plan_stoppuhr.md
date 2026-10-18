# Planung: Stoppuhr — Zeit vorwärts für Übungen, Pläne und den Timer (18.10.2026)

Ben, 18.10.2026: „Ein Timer zählt runter. Die Uhr soll aber auch einfach raufzählen …
beim Trainieren von Übungen — einzelne oder aus dem Starten heraus von Plänen — soll die
Zeit laufen und gestoppt werden können, um die Trainingszeit festzuhalten und um bei
laufenden HRV-Messungen Notizen zu setzen.“ Dazu: in den Übungseinstellungen festlegen,
ob die Übung abgehakt wird und ob die Zeit zur Haltezeit oder zur Zeit gesamt kommt; ein
Platz für Uhr und Timer in der Übung, ohne dass ▶ wie „Timer starten“ aussieht; bei
mehreren Timern gilt der zuletzt gestartete; die Stoppuhr auch bereitstellen, auch im
Timer-Menü. Nachgereicht: Die Info-Ansicht der Übung soll Timer und ihre Wirkung auf das
„Gemacht“ zeigen. „Erst der Plan, dann die Umsetzung.“

**Noch nicht gebaut.** Offene Entscheidungen: Katalog P49–P54. Skizzen (elf
Handy-Bildschirme, Reihen A–D): https://claude.ai/artifact/7JovPxSaffvxwWjjv8WVvP

---

## 1. Was es heute gibt

| Was | Wo |
|---|---|
| Timer an der Übung: mehrere Profile, das erste ist die Vorgabe; Vorrang Planübung > Plan > Übung | `exercise.timer_json` (Migration 020), `core/uebung_timer.timer_fuer` |
| Ein Lauf der Übung ist eine Einheit aus Übung und Timer; ist er fertig, gilt die Übung als gemacht, die Zeit kommt als Haltezeit je Satz oder Zeit gesamt ins Tagebuch; „Abbrechen“ trägt nichts ein; unter 5 s fällt weg | `ui/uebung_lauf.py`, `core/timer_eintrag.py` |
| „Zeit eintragen“ und das Zeitfeld: in einem Plan an der Planübung gespeichert (`TimerWahl`), **ohne Plan nur im Speicher** der App — nach einem Neustart wieder die Vorgabe | `core/uebung_timer.TimerWahl`, `views/uebung_timer.py` |
| Die Uhr neben dem i öffnet den Timer der Übung (Profile, „zählt“, Läufe heute) | `views/plan.py`, `views/uebung_timer.py` |
| Die Info-Ansicht (`/uebung/<id>`, hinter dem i im Plan) zeigt Beschreibung, Eingabe, Standard für Pläne und Videos — die Timer nur als Symbol in der Leiste | `views/uebung_detail.py`, `views/plan_info.py` |
| Plan-Ablauf: Übungen **ohne** Timer zählen schon vorwärts; „Gemacht“ trägt nur „gemacht“ ein, keine Zeit | `devices/plan_ablauf.seit_s` |
| HRV: „Planke beginnt/fertig“ mit Kurzcode der Übung (A15), Timer-Abschnitte als Marken (Name, Runde, zählt) | `core/einheit.projektion`, `docs/kompatibilitaet.md` §4 |

Eine Uhr, die nur vorwärts zählt, gibt es nicht: `core.timer.TimerLauf` rechnet alles aus
festen Abschnittsdauern.

## 2. Begriffe

- **Stoppuhr** — zählt ab 0:00 vorwärts und endet nie von selbst: ⏸ hält an, ▶ geht
  weiter, **Fertig** beendet und trägt ein, **Abbrechen** beendet ohne Eintrag. Der Name
  statt „Infinite-Uhr“: So heißt die Funktion auf jedem Handy.
- **Timer** — zählt rückwärts, wie bisher (Profile, Folgen, Runden).
- **Uhr der Übung** — was in einer Übung startet: die Stoppuhr oder einer ihrer Timer.

## 3. Kern (ohne flet)

- `TimerProfil.art`: `"timer"` (Vorgabe) oder `"stoppuhr"`. Ein eingebautes Profil
  **Stoppuhr** (ID `stoppuhr`) — immer da, nicht bearbeitbar, reist nicht in Paketen.
- `StoppuhrLauf` — eine Unterklasse von `TimerLauf` mit derselben Schnittstelle (Einheit,
  Laufleiste, Benachrichtigung und Timer-Ansicht bleiben, wie sie sind): Die Zeit läuft
  vorwärts, „fertig“ wird sie nur mit Fertig, keine 3-2-1-Töne.
- **Jedes Laufstück ist ein Abschnitt** — von Start bzw. Weiter bis Pause bzw. Fertig.
  Damit stimmt das Eintragen ohne weiteren Knopf (`core.timer_eintrag.ergebnis`):
  - **Haltezeit je Satz:** ein Satz je Laufstück — ▶ halten, ⏸ ausruhen, ▶ halten,
    Fertig = zwei Sätze.
  - **Zeit gesamt:** die Summe der Laufstücke, Pausen zählen nicht.
  - Ein Laufstück unter 5 s fällt weg (wie beim Timer). → **P51**
- Die Zeitleiste der Einheit bekommt dieselben Ereignisse wie vom Timer
  (`timer/abschnitt`, `pause`, `weiter`, `ende`), dazu `daten.art = "stoppuhr"`.

## 4. Einstellung an der Übung: „Uhr und Timer zählen als“

Eine Auswahl im Übungsformular, Abschnitt „Timer“ (**Skizze C1**) — sie gilt für die
Stoppuhr **und** die Timer der Übung, einzeln wie im Plan-Ablauf:

| Wahl | Ins Tagebuch, wenn die Uhr mit „Fertig“ endet |
|---|---|
| Nichts | nichts — die Uhr misst nur (Anzeige, Marken in der HRV-Messung) |
| Gemacht | „gemacht“ ohne Zeit |
| Haltezeit je Satz | gemacht, je Laufstück bzw. zählendem Abschnitt ein Satz Haltezeit |
| Zeit gesamt | gemacht, die gelaufene Zeit als Zeit gesamt |

- Angeboten wird nur, was die Übung hat; ohne Zeitfeld nur „Nichts“ und „Gemacht“, mit
  dem Hinweis, „Zeit gesamt“ unter Parameter hinzuzufügen.
- **Vorgabe** für alle Übungen, die nichts eingestellt haben: wie bisher — gemacht und das
  erste Zeitfeld der Übung (Haltezeit vor Zeit gesamt).
- Eine Wahl statt zwei Schalter, weil sich „Zeit eintragen“ ohne „abhaken“ nicht
  unterscheidet: Ein Eintrag mit Zeit ist immer auch gemacht. → **P50**
- Die Planübung kann abweichen (heute `TimerWahl.zeit_eintragen`/`zeitfeld`, künftig
  dieselben vier Werte) — Vorrang Planübung > Übung, wie beim Timer.
- **Migration 022:** `exercise.zeitwertung TEXT NOT NULL DEFAULT ''` (`''` = Vorgabe,
  sonst `nichts`, `abhaken`, `hold`, `duration`). Im Paket ein neues, optionales Feld
  `zeitwertung` (`docs/uebungspakete.md`), im Drei-Wege-Abgleich ein Feld.
- Der Name des Feldes („Zählt als“) ist **P53**.

## 5. In der Übung: die Uhr-Zeile

Das Problem: Ein ▶ neben dem Timer-Symbol liest sich wie „Timer starten“. Vorschlag
(**Skizzen A1–A4**): eine eigene Zeile unter „Gemacht | Notiz“:

- **Links steht als Text, was startet:** ein Chip „Stoppuhr ▾“ oder „Halten 3 × 1 min ▾“,
  daneben die Zeit (0:00 bzw. 3:00). **Rechts ein einziger ▶** — er startet immer, was
  links steht. Daneben die Sanduhr für „Bereitstellen“ (wie im Timer).
- **▾ wählt um** (A2): Stoppuhr, die Timer der Übung, „Timer der Übung …“ (die heutige
  Ansicht mit Profilen, „zählt“ und Läufen heute).
- **Läuft sie** (A3), wird die Zeile zur Anzeige: „0:42 · Satz 2“ bzw. „Halten · Runde
  1/3 · noch 0:18“, dazu Anhalten und **Fertig**; „Abbrechen“ im Menü ⋮. Oben die
  Laufleiste wie immer, der Knopf „Timer“ in der Leiste zeigt die Zeit.
- **Nach Fertig** (A4): „Heute geleistet“ zeigt den Eintrag, eine Meldung „2 Sätze
  Haltezeit eingetragen“ mit „Rückgängig“.
- Die Uhr neben dem i bleibt: Sie öffnet den Timer der Übung wie bisher.
- **Eine Uhr zur Zeit:** Läuft schon eine in einer anderen Übung, fragt ▶ nach („Planke
  läuft — beenden, eintragen und Kniebeuge starten?“). Läuft ein Plan-Ablauf, steuert er
  die Uhren; die Zeile zeigt dann nur an.

Alternativen (**Skizzen B1, B2**): zwei beschriftete Knöpfe „▶ Stoppuhr“ und „Timer:
Halten ▾“; oder Bens Variante — „Uhr“ und „Timer“ zwischen „Gemacht“ und „Notiz“, vier
Knöpfe in einer Reihe. → **P49**

## 6. Info-Ansicht der Übung: „Uhr und Timer“

Ben, 18.10.2026: „wenn eine Übung einen Timer hat, wird der in der Übungseinstellung
gezeigt, aber nicht in der Informationsview. Dort sollte auch stehen …, wie sich Timer und
Zeit auf die Zählung und das ‚Gemacht‘-Feld auswirken.“ (**Skizze C2**)

- Ein Abschnitt **„Uhr und Timer“** in `uebung_detail` zwischen „Eingabe“ und „Standard
  für Pläne“ — damit auch hinter dem i im Plan (`plan_info` übernimmt die Ansicht).
- Darin: die Stoppuhr, die Timer der Übung mit Kurztext und „zuletzt gestartet“, und das
  Feld **„Zählt als“** mit einem Satz, was „Fertig“ einträgt („hakt die Übung ab; jedes
  Laufstück und jeder zählende Abschnitt wird ein Satz; Pausen zählen nicht, unter 5 s
  fällt weg; Abbrechen trägt nichts ein“).
- Im Plan zusätzlich, wenn die Planübung abweicht: „Im Plan „…“: Zeit gesamt“.
- „Ändern“ führt ins Übungsformular, Abschnitt „Timer“.
- Name des Feldes: **„Zählt als“** (Vorschlag) — kurz, und es passt zu „zählt / zählt
  nicht“ der Abschnitte. Andere: „Wirkung auf das Tagebuch“, „Zeit eintragen als“. → **P53**

## 7. Mehrere Timer: welcher gilt

- **Gesetzt ist, was zuletzt gestartet wurde** — je Übung gemerkt, in einem Plan an der
  Planübung (`TimerWahl.profil_id`, darf `stoppuhr` sein), ohne Plan in den Einstellungen
  des Profils (wie das zuletzt benutzte Timer-Profil). Läuft eine Uhr, ist es die laufende.
- **Ohne Vorgeschichte** die bisherige Regel: Planübung > Plan > erstes Profil der Übung;
  hat die Übung keinen Timer, die Stoppuhr.
- **Umschalten** über ▾ — gilt ab dem nächsten Start; eine laufende Uhr wird nicht
  getauscht (erst Fertig oder Abbrechen). → **P52**
- Der Plan-Ablauf nimmt dieselbe Wahl: Wer an der Planübung die Stoppuhr gewählt hat,
  bekommt sie auch im Ablauf.

## 8. Timer-Menü: Profil „Stoppuhr“

- Im Timer (Leiste → Timer) steht **„Stoppuhr“ als erster Chip** vor den Profilen —
  eingebaut, ohne Stift und Löschen (**Skizze C3**). Gewählt zeigt der Timer 0:00
  vorwärts, „Start“ und **„Bereitstellen“** wie jedes Profil.
- Der Knopf „Timer“ in der Leiste zeigt dann die gelaufene Zeit, die Benachrichtigung
  „Stoppuhr 12:34“, die Laufleiste und der Reiter „Einheit“ eine Karte ohne Restzeit.
- Für sich gestartet wie ein Timer: eine eigene Einheit, oder sie tritt der laufenden bei
  (seit 18.10., `ui.einheit.einzeln_starten`). Ohne Übung trägt sie nichts ein — sie setzt
  nur die Marken in der Messung.

## 9. Plan-Ablauf

- Übungen ohne Timer zählen schon vorwärts. Neu: **„Gemacht“ trägt die gelaufene Zeit
  ein**, wie die Übung es will (§4); ⏸ hält die Uhr an, jedes Laufstück ist ein Satz.
- Ist an der Planübung die Stoppuhr gewählt, läuft sie statt des Timers.

## 10. HRV-Marken

- Wie heute „Planke beginnt“ und „Planke fertig“ mit dem Kurzcode der Übung.
- Die Laufstücke der Stoppuhr sind Abschnitte auf der Spur „timer“ (Name der Übung, ab
  dem zweiten mit Nummer: „Planke 2“); eine Pause beendet den Abschnitt. Allein (Timer-Menü)
  heißen sie „Stoppuhr“.
- Bens Frage, was die Marken tragen sollen (Timername, Kurzcode, Soll-Dauer) — **P54**,
  Vorschlag dort und in den **Skizzen D1, D2**. Eine Formaterweiterung über hrv-core —
  erst nach seiner Antwort.

## 11. Umsetzung in Schritten (nach Freigabe)

1. Kern: `TimerProfil.art`, `StoppuhrLauf`, Laufstücke als Abschnitte, Eintragen;
   Doctests und Tests.
2. Migration 022 `exercise.zeitwertung`, Modell, Repository, Paketfeld und Abgleich;
   Auswahl im Übungsformular, Abschnitt „Uhr und Timer“ in der Info-Ansicht.
3. Eintragen nach der Zeitwertung: Übungs-Lauf (`ui/uebung_lauf.kontext_fuer`) und
   Plan-Ablauf (auch ohne Timer).
4. Oberfläche: Uhr-Zeile in der Übung, die Wahl merken, Chip „Stoppuhr“ im Timer-Menü,
   Laufleiste, Reiter „Einheit“ und Benachrichtigung vorwärts.
5. HRV-Marken nach P54.
6. Doku (`plan_einheit.md` §7, `uebungspakete.md`, Katalog: Gerätetests), Prüfung im
   Browser, CI ohne flet.
