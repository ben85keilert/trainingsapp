# Stoppuhr — Zeit vorwärts für Übungen, Pläne und den Timer (18.10.2026)

Ben, 18.10.2026: „Ein Timer zählt runter. Die Uhr soll aber auch einfach raufzählen …
beim Trainieren von Übungen — einzelne oder aus dem Starten heraus von Plänen — soll die
Zeit laufen und gestoppt werden können, um die Trainingszeit festzuhalten und um bei
laufenden HRV-Messungen Notizen zu setzen.“ Dazu: in den Übungseinstellungen festlegen,
ob und wie die Zeit zählt; ein Platz für Uhr und Timer in der Übung, ohne dass ▶ wie
„Timer starten“ aussieht; bei mehreren Timern gilt der zuletzt gestartete; die Stoppuhr
auch bereitstellen, auch im Timer-Menü; Timer und ihre Wirkung in der Info-Ansicht.

**Gebaut am 18.10.2026** nach Bens Antworten auf P49–P54 (Katalog `docs/offene_fragen.md`,
„Entschieden“). Skizzen, an denen er entschied (elf Bildschirme, Reihen A–D):
https://claude.ai/artifact/7JovPxSaffvxwWjjv8WVvP — Reihe A und B2 sind gebaut; wo die
Skizzen „Pause beendet den Satz“ oder vier Stufen zeigen, gilt, was hier steht.

---

## 1. Begriffe

- **Stoppuhr** — zählt ab 0:00 vorwärts und endet nie von selbst: **Anhalten** hält nur an,
  **Weiter** zählt weiter, **Fertig** beendet und trägt ein, **Abbrechen** beendet ohne
  Rückfrage und ohne Eintrag (Ben: „Pause pausiert und beendet nicht. Man soll weiter
  klicken können und komplett abbrechen - dann ohne Rückfrage.“).
- **Timer** — zählt rückwärts, wie bisher (Profile, Folgen, Runden).
- **Uhr der Übung** — was in einer Übung startet: die Stoppuhr oder einer ihrer Timer.

## 2. Kern (ohne flet)

- `core.timer.stoppuhr()` — ein eingebautes Profil (ID und Art `stoppuhr`, ein Abschnitt,
  der erst nach 12 h von selbst endet). Es läuft in `TimerLauf` wie jeder Timer: Pause,
  Weiter, Fertig, Abbrechen, Marken und Zeitleiste kommen von dort. `TimerLauf.vorwaerts`
  und `anzeige()` lassen Leiste, Reiter „Einheit“, Benachrichtigung, Timer-Ansicht,
  Plan-Ablauf und die Übung die gelaufene Zeit zeigen; keine Töne.
- **Ein Lauf ist ein Satz bzw. eine Zeit**: Pausen zählen nicht, unter 5 s fällt weg
  (`core.timer_eintrag`). Seit 22.10.2026 **im offenen Eintrag** wie ein Tipp (P79 D1,
  `SessionRepo.lauf_eintragen`); ob die Zeit zählt, legt die Übung fest
  (`Exercise.zeit_zaehlt`), beim Üben der Knopf „zählt“ in der Leiste für jetzt
  (`docs/plan_uebungen_einstellen.md`).

## 3. Uhr an der Übung und „Zählt als“

Ben: „Der Parameter Gesamtzeit wird programmweit zu Zeit. Es soll geben Zeit+Haltezeit.
Wenn Haltezeit aktiviert ist, gibt es eine Auswahl. Wenn Haltezeit nicht aktiviert ist,
automatisch ‚Zeit‘. Parameter Zeit muss auch nicht aktiviert sein … die Uhr kann mit dem
neuen System separat ein/abgeschalten werden. Ist die Uhr ein, hat man automatisch Zeit mit
dabei, auch ohne Chips/Kachel/wasauchimmer.“

- **Uhr in der Übung** (an/aus, Vorgabe an): Ohne Uhr gibt es in der Übung weder Zeile noch
  Knöpfe, und im Plan-Ablauf hakt „Gemacht“ bei Übungen ohne Timer nur ab.
- **„Zählt als“**: Bietet die Übung (bzw. die Planübung) Haltezeit an, Haltezeit je Satz
  oder Zeit (Vorgabe Haltezeit); sonst immer **Zeit** — auch ohne den Parameter Zeit. Die
  Kopie im Eintrag bekommt das Feld dann dazu (`core.uebung_timer.mit_zeitfeldern`).
- Wo: Übung bearbeiten → Timer; Planübung einstellen → „Uhr in diesem Plan“ (wie die Übung,
  an, aus; „Zählt als“ wie die Übung, Haltezeit, Zeit) — Vorrang Planübung > Übung
  (`core.uebung_timer.uhr_an`, `zaehlt_als`).
- Speicher: Migration 022 `exercise.clock_on`, `exercise.clock_counts_as`; die Planübung in
  `plan_item.timer_json` (`TimerWahl.uhr`, `zeitfeld`). Im Paket die Felder `uhr` und
  `zaehlt_als` (`docs/uebungspakete.md`), im Drei-Wege-Abgleich je ein Feld.
- **„Zeit gesamt“ heißt überall „Zeit“** — gespeicherte Übungen und die Kopien in Einträgen
  lesen den alten Namen als neuen (`core.result_spec.ALTE_NAMEN`).

## 4. In der Übung: Zeile oder Knöpfe

Ben: „Kannst du Variante A und B2 einbauen. In den Haupt-Einstellungen kann man beides
umstellen, Standard ist A.“ — Einstellungen → Übungen → „Stoppuhr und Timer in der Übung“
(`ui/components/uhr.py`):

- **Zeile** (Vorgabe, Skizzen A1–A4): unter „Gemacht | Notiz“ links als Text, was startet
  („Stoppuhr ▾“ oder „Halten 3 × 1 min ▾“), daneben die Zeit, rechts „Bereitstellen“ und
  ein einziger Start. ▾ wählt um; dort auch „Timer der Übung …“.
- **Knöpfe** (Skizze B2): „Uhr“ (Stoppuhr) und „Timer“ zwischen „Gemacht“ und „Notiz“; der
  Timer-Knopf startet den einen Timer, wählt bei mehreren und führt ohne einen zum Timer
  der Übung.
- **Läuft die Uhr**, zeigen beide dieselbe Anzeige: Zeit, Anhalten bzw. Weiter, Fertig,
  Abbrechen (ohne Rückfrage). Fertig trägt ein, „Heute geleistet“ zeigt es.
- **Welche gilt**: die in dieser Sitzung gewählte oder zuletzt gestartete
  (`AppState.uhr_wahl`) — „wenn im Übungsfeld ein anderer Timer ausgewählt wurde, ändert
  sich keine Einstellung“; sonst Planübung > Plan > erster Timer der Übung, ohne Timer die
  Stoppuhr.
- Eine Uhr zur Zeit: Läuft schon eine andere Übung, sagt es eine Meldung.

## 5. Info-Ansicht: „Uhr und Timer“

Abschnitt in `uebung_detail` (auch hinter dem i im Plan): Stoppuhr, Timer der Übung, Feld
**„Zählt als“** (Bens Frage nach einem Namen für „Auswirkung von Zeit/Timer“) mit dem Satz,
was „Fertig“ einträgt; im Plan der Hinweis, wenn die Planübung abweicht.

## 6. Timer-Menü

**Seit 19.10.2026 drei Reiter: Stoppuhr · Timer · Profile** (Ben: „Einmaluhren der
Standard, Profile sind komplexer gebaut“). Stoppuhr und Timer sind *Einmaluhren*
(`core.timer.stoppuhr`, `einmal_timer`; gemerkt in `app_setting` ``timer_einmal``, nicht
in der Bibliothek) mit einem **Namen** (optional) und dem Schalter **„Name in die Marken
(HRV, Strecke)“** — aus heißt: in Messung, Strecke und Titel der Einheit steht nur
„Stoppuhr“ bzw. „Timer“ (`TimerProfil.markenname`), auf dem Bildschirm bleibt der Name
(`anzeigename`). Der Timer zählt eine **Dauer** rückwärts (Feld mm:ss, Chips 1–15 min,
Vorgabe 5:00); „Abschnitte und Runden …“ öffnet den Editor im Einmal-Modus
(``…/timer/bearbeiten/einmal``, `views.timer.einmaluhr`): ohne Namensfeld, „Übernehmen“
statt „Speichern“, das Lesezeichen oben fragt erst beim **„Als Profil speichern“** nach
einem Namen. „Nur eine Dauer“ verwirft die Abschnitte wieder. Läuft die Einmaluhr, bleiben
Dauer und Abschnitte gesperrt; Name und Schalter gelten sofort (`_in_lauf_uebernehmen`),
und `lauf_fuer` ersetzt eine laufende Einmaluhr nicht durch neue Einstellungen.

Die Stoppuhr gewählt: 0:00 vorwärts, Start, Bereitstellen, Anhalten/Weiter, ↺ und Fertig;
statt der Ablaufliste „So zählt sie“. Für sich gestartet tritt sie einer laufenden Einheit
bei (eine Messung bekommt ihre Marken) oder ist eine eigene; ohne Übung trägt sie nichts
ein. Der Reiter „Profile“ zeigt die Bibliothek als Chips (Stift, Plus) — zuletzt gewähltes
Profil in ``timer_bibliothek_aktiv``. Marken: `marke.profil` ist ``stoppuhr`` bzw.
``einmal`` (`docs/kompatibilitaet.md` §4).

## 7. Plan-Ablauf

Übungen ohne Timer zählen vorwärts; mit Uhr an trägt „Gemacht“ die Zeit von Beginn bis
„Gemacht“ ein (wie „Zählt als“), mit Uhr aus nur „gemacht“. Timer tragen immer ihre Zeit
ein.

## 8. HRV-Marken (P54)

Ben: „Aus Transparenzgründen HRV-Kachel so wie oben. Später wird der Code der Übung
versteckt werden können“:

- Läuft eine Übung, tragen **alle** ihre Marken den Kurzcode (`uebungen`), auch die
  Abschnitte des Timers; der Text nennt den Timer nicht mehr, „Timer fertig“ fällt in einer
  Übung als Notiz weg (`core.einheit.in_uebung`).
- `marke.soll_s` (geplante Dauer) und `marke.profil` (Kurzcode des Profils, Stoppuhr
  `stoppuhr`) — Formaterweiterung in hrv-core (`MARKE_FELDER`), Vertrag
  `docs/kompatibilitaet.md` §4.
- Unter jeder Notiz stehen diese Angaben als kleine Etiketten (`core.einheit.marke_angaben`,
  `ui/components/notizen.py`) — live und in der Auswertung. Den Kurzcode auszublenden kommt
  später.

## 9. Nebenbei behoben

In v0.3.4 verweigerten Übungs-Timer, Plan-Ablauf und Ausdauertraining den Start, solange
eine für sich gestartete Messung lief (sie war seit diesem Stand eine eigene Einheit). Jetzt
macht ihre Einheit Platz, die Aufnahme läuft weiter und kommt als „läuft schon“ mit; danach
steht sie wieder für sich in der Leiste (`ui.einheit.platz_machen`, Befund H22).
