# Plan: Wohin ein Tipp führt — Zielsymbol und Langdruck-Menü (Ben, 28.10.2026)

Ben: „In ‚Heute‘ sind die gemachten Übungen gelistet. Ein Klick führt auf den Eintragsedit.
In Verlauf sind unter ‚Tage‘ und ‚Übungen‘ die Übungen gelistet. Ein Klick führt auf die
graphische Übersicht. Unter ‚Tagebuch‘ führt ein Klick auf den Eintragsedit. Einerseits ist
es gut, wenn unterschiedliche Orte unterschiedliches Routing haben, aber es ist verwirrend.
Der Pfeil nach rechts zeigt jedes Mal etwas anderes. Ist es möglich, links vom Pfeil ein
kleines Symbol zu setzen für Bearbeiten/Tag usw., um anzuzeigen, wo das Routing hinführt?
Ein Gedrückthalten auf die Übung könnte auch ein Menü öffnen, um die Routings auszuwählen:
Üben – Eintrag editieren – Tagesverlauf – Tag – was es sonst so gibt.“

Stand: gegengeprüft (§7), Bens Antworten (§9) eingearbeitet, **gebaut am 28.10.2026**. Katalog: P87 → Entschieden, Gerätetest T85.

## 1. Bestand — wohin Zeilen heute führen

| Ort | Zeile | Tipp | Gedrückt halten |
|---|---|---|---|
| Heute / Tag, „Gemacht“ (`views/tag.py` `ziel`) | Übung (`uebungszeile`) | **Leistungen-Blatt**: die Einträge des Tages, darin „Nachtragen“, „Im Verlauf ansehen“, i → Übungsseite | — |
| Heute / Tag, „Gemacht“ | Training (dieselbe `uebungszeile`, Etikett „Training“) | `/ausdauer/<id>` (Strecke) | — |
| Heute / Tag, Zeitleiste | Übung im Planblock (`block_zeile`, ohne Pfeil) | Leistungen-Blatt | — |
| Heute / Tag, Zeitleiste | Training (eigene Karte) | `/ausdauer/<id>` | — |
| Heute / Tag, „Steht an“ | Chip einer Planübung | gemacht (abhaken) | Nachtragen (`nachtragen_route`) — gibt es schon (18.10.) |
| Heute / Tag, Zeitleiste | Planblock | „Weiter mit …“ → `/plan/<id>` bei der Übung | — |
| Verlauf → Tage (`views/verlauf.py`) | Übung eines Tages, je Variante (`uebungszeile`) | `/verlauf/<kachel>` (Kurve) | — |
| Verlauf → Übungen | Übung **über alle Tage**, je Variante — kein Tag | `/verlauf/<kachel>` | — |
| Verlauf → Zum Tag | Tagesfeld | `/verlauf/tagesfeld/<id>` | — |
| Verlauf → Tagebuch (`views/tagebuch.py`) | Übungsnotiz, Aufnahme an Übung | Leistungen-Blatt — **ohne** `nachtragen=`, also ohne „Nachtragen“ und „Im Verlauf“ (anders als unter Heute) | — |
| Verlauf → Tagebuch | Notiz zum Tag, zum Plan | Notiz-Dialog | — |
| Verlauf → Tagebuch | Tagesfeld | Tagesfeld-Blatt | — |

Überall derselbe Pfeil ›. Das ist das Problem.

## 2. Grundregel

- **Tipp** = das, wofür die Liste da ist: unter Heute und im Tagebuch die Einträge
  bearbeiten, im Verlauf die Kurve. Das bleibt (Ben: „einerseits gut“).
- **Links vom Pfeil ein Zielsymbol**, klein und blass, das sagt, wohin der Tipp führt.
  Dasselbe Symbol steht überall für dasselbe Ziel (Tabelle §3).
- **Gedrückt halten** öffnet ein Blatt mit allen Zielen dieser Übung, das Tipp-Ziel zuerst.

## 3. Die Ziele — `ui/components/ziele.py`

Ein `Ziel` ist Schlüssel, Text, Symbol und „öffnen“ (Route oder Blatt). Ein Katalog, eine
Schreibweise:

| Schlüssel | Text im Menü | Symbol | Öffnet |
|---|---|---|---|
| `ueben` | Üben | `PLAY_ARROW` | `/plan/<plan>` bei dieser Übung — nur, wenn der Plan noch existiert und ein Item mit dieser Übung hat (`plan_ziel`/`plan_offen` = **Item-ID** wie „Weiter mit“; bei mehreren Plänen der letzte der Zeile, wie `nachtragen`); sonst `/training/<übung>` — entfällt bei archivierten oder gelöschten Übungen |
| `eintraege` | Einträge des Tages | `FACT_CHECK_OUTLINED` (Liste mit Haken) | Leistungen-Blatt (`leistungen_blatt`, **immer** mit `nachtragen=`, auch im Tagebuch) — ein Blatt, die Ansicht darunter bleibt (Ben, 18.10.2026) |
| `nachtragen` | Nachtragen | `ADD` (wie der runde Knopf und das Blatt) | `[/tag/<datum>]/nachtragen/<übung>[/<plan>]` — ohne Tag (Verlauf → Übungen): heute |
| `verlauf` | Verlauf (Kurve) | `SHOW_CHART` (wie der Reiter) | `/verlauf/<kachel>` |
| `tag` | Tag | `TODAY` (wie der Reiter Heute) | `/tag/<datum>` — nur mit Tag |
| `uebung` | Übungsseite | `INFO_OUTLINE` (das i) | `/uebung/<übung>` (ändert nichts, P79) |
| `strecke` | Strecke | `ROUTE` (wie der Reiter Strecken) | `/ausdauer/<id>` (nur Trainings) |
| `notiz` | Notiz | `EDIT_NOTE` (wie „Notiz zum Tag“) | Notiz-Dialog (Tagebuch: Tag, Plan) |

Die Symbole folgen dem Vokabular, das die App schon hat (Prüfung §7, Befund 6): der
Stift-Umriss `EDIT_OUTLINED` bleibt „Übung bearbeiten“ und kommt hier nicht vor.

`ziele_fuer(state, uebung, tag: date | None, plan_id, *, hier)` liefert die Liste für eine
Zeile: alle, die es für diese Übung gibt, **ohne** das, wo man schon steht (`hier`: auf der
Tagesansicht kein „Tag“, im Verlauf-Reiter „Übungen“ kein „Verlauf“). Ohne Tag (Verlauf →
Übungen) entfallen `eintraege` und `tag`. Gelöschte oder archivierte Übung: ohne `ueben`.
Nur Routen und Repo-Abfragen, keine Rechnung; keine Untertitel je Ziel in der ersten
Fassung (sie zögen Abfragen je Zeile nach sich, Befund 11d).

## 4. Die Zeile — `uebungszeile(…, ziel=…, weitere=…)`

- `ziel`: das Tipp-Ziel; `on_click` entfällt, die Zeile ruft `ziel.oeffnen(page)`.
- Rechts: **Zielsymbol** (18 px, Deckkraft 0,5) und dahinter der Pfeil › wie bisher.
  Tooltip auf der Zeile (Desktop): „Antippen: Einträge des Tages · Gedrückt halten: mehr“.
- `weitere`: die übrigen Ziele. `on_long_press` (`ft.Container` kann das; Tipp und
  Langdruck schließen sich aus) öffnet das **Zielblatt** (`ziele_blatt`): Titel „‹Übung› ·
  ‹Tag›“, je Ziel eine Zeile mit Symbol und Text; das Tipp-Ziel steht zuerst mit Vermerk
  „Antippen“. **Das Zielsymbol selbst ist antippbar** und öffnet dasselbe Blatt — so ist
  das Menü auch mit Maus und ohne Erklärung erreichbar (Befund 10).
- **Aus dem Blatt heraus** geht es wie in `leistungen_blatt.weiter_nach`: `Nachher` sammelt
  das Ziel, `schliessen(blatt)` schließt genau dieses Blatt, erst `on_dismiss` ruft
  `push_route` bzw. `show_dialog(leistungen_blatt)` — nie bei offenem Blatt die Route
  wechseln (Geist-Dialog, Befund 1). Ein Leistungen-Blatt aus Verlauf → Tage bekommt
  `danach=` einen Rücksetzer, der die Tagesdaten neu liest (Befund 8).
- **Kein Tooltip auf der Zeile**: Flets Tooltip löst am Handy selbst auf Langdruck aus und
  stritte mit dem Menü (Befund 2). Stattdessen die Hilfezeile unter „Gemacht“ und der
  Tooltip nur am Zielsymbol mit `trigger_mode=MANUAL` (Desktop zeigt ihn beim Hovern). Den
  Chip „Steht an“ (Tipp = gemacht, Langdruck = Nachtragen) ebenso von seinem Tooltip
  befreien — sein Langdruck ist in T42 noch unbestätigt.
- Dieselbe Erweiterung für die Karten, die keine `uebungszeile` sind: die Übungszeilen der
  Zeitleiste (`block_zeile`, `ziel=eintraege`), die Trainingskarte der Zeitleiste
  (`ziel=strecke`), die Übungs- und Aufnahmezeilen im Tagebuch (`ziel=eintraege`, dort das
  Blatt künftig mit `nachtragen=` wie unter Heute, Befund 4c), die Notizzeilen im Tagebuch
  (`ziel=notiz`, Weitere: Tag). Der Planblock der Zeitleiste bekommt das Symbol `ueben`
  („Weiter mit“).
- **Nicht** angefasst: Katalog, Pläne, Kurse, Einstellungen, Pakete, Aufzeichnungen —
  dort ist der Pfeil eindeutig („öffnen“), und die Zeilen sind keine Übungen eines Tages.
- Der Chip „Steht an“ behält Tipp = gemacht, Gedrückt halten = Nachtragen (eingeführt
  18.10., in der Hilfezeile erklärt) — er ist keine Liste gemachter Übungen.

## 5. Was sich für Ben ändert

- Heute: hinter jeder gemachten Übung ein kleiner Stift vor dem Pfeil; Tipp wie bisher ins
  Blatt; gedrückt halten → Üben · Nachtragen · Verlauf · Übungsseite (Tag entfällt, man
  steht auf ihm).
- Verlauf → Tage/Übungen: kleine Kurve vor dem Pfeil; gedrückt halten → Üben · Einträge
  des Tages (Tage) · Nachtragen · Tag · Übungsseite.
- Tagebuch: Stift (Einträge) bzw. Stift-Umriss (Notiz) vor dem Pfeil; gedrückt halten →
  Tag · Verlauf · Üben · Übungsseite.

## 6. Schritte

1. `ui/components/ziele.py`: `Ziel`, `ziele_fuer`, `zielsymbol`, `ziele_blatt`; Test mit
   den Attrappen (Zeile → Tipp öffnet das Ziel, Langdruck zeigt das Blatt mit der Liste,
   „hier“ fehlt).
2. `uebungszeile` erweitern; `views/tag.py`, `views/verlauf.py`, `views/tagebuch.py`
   anschließen; Trainingskarte, Zeitleiste.
3. Doku: `app.py` (Routen-Docstring), Katalog (P87 → Entschieden, Gerätetest), Hilfe-Zeile
   unter Heute („Antippen = Einträge · gedrückt halten = mehr“).
4. Skizze: Reihe D in der Bildergeschichte (Zeile mit Symbol und Pfeil, das Zielblatt).

## 7. Gegenprüfung (unabhängiger Prüfer, 28.10.2026)

Urteil: **bauen mit Änderungen**. Eingearbeitet (oben):

1. Aus dem Zielblatt heraus Route oder Blatt nur über `Nachher` + `schliessen` (sonst
   Geist-Dialog, Memory „Flet-Dialoge verwaisen“).
2. Tooltip auf der Zeile frisst den Langdruck am Handy (Flet-Vorgabe `LONG_PRESS`) → kein
   Tooltip auf der Zeile, am Symbol nur `MANUAL`; Chip „Steht an“ gleich mit.
3. `ueben` braucht die **Item-ID** des Plans (`plan_ziel`), eine Prüfung, ob Plan und Item
   noch da sind, und entfällt bei gelöschten/archivierten Übungen.
4. Bestandstabelle berichtigt: Training in „Gemacht“ ist dieselbe Zeile; die Zeitleiste hat
   eigene Übungszeilen ohne Pfeil; das Tagebuch öffnet das Leistungen-Blatt ohne
   „Nachtragen“/„Im Verlauf“ — wird angeglichen.
5. Verlauf → Übungen hat keinen Tag → `tag` optional, `eintraege`/`tag` entfallen dort.
6. Symbole nach dem Vokabular der App: Einträge = `FACT_CHECK_OUTLINED`, Nachtragen = `ADD`,
   Notiz = `EDIT_NOTE`; `EDIT_OUTLINED` bleibt „bearbeiten“.
8. Verlauf → Tage liest einmal je Aufbau → `danach=` nach dem Leistungen-Blatt neu lesen.
9. Flet: `on_click` + `on_long_press` + `ink` an `ft.Container` schließen sich aus, Scrollen
   bricht den Langdruck ab (erwünscht); kein Rechtsklick an `ft.Container`.
10. Langdruck ist versteckt → das Zielsymbol ist selbst antippbar.
11. Katalog P87 anlegen; `tests/test_ui_tag.py` prüft heute „kein Langdruck an einem
    vergangenen Tag“ → auf Chips einschränken; Hinweistexte und Docstrings (`tag.py`,
    `verlauf.py`, `tagebuch.py`, `uebungszeile.py`) nachziehen; keine Untertitel je Ziel.
12. „Zurück = Weg“ trägt alles; `/tag/d` → Verlauf → „Tag“ geht **zurück** auf den Stapel
    (gewollt). „Üben“ aus dem Menü verhält sich wie „Weiter mit“, `heute_haelt` greift erst
    beim Verlassen über die Leiste.

Als Frage an Ben (§8): Befund 7 — das Symbol **ersetzt** den Pfeil, wenn der Tipp ein
Blatt öffnet (Einträge, Notiz: die Ansicht bleibt stehen), der Pfeil steht allein, wenn
eine Seite kommt (Kurve, Strecke, Plan). Sonst stünden in abgehakten Zeilen ✓ · Stift · ›
nebeneinander.

Reihenfolge laut Prüfer: Skizze und Bens Antwort → `ziele.py` + `uebungszeile` + nur
Heute (Übersicht und Zeitleiste) → Gerätetest Langdruck/Tooltip/Blatt-aus-Blatt → Verlauf
(mit 5 und 8) und Tagebuch (mit 4) → Doku, Katalog.

## 8. Offen für Ben

- **Symbol und Pfeil** (Skizze D1, dein Vorschlag) — oder nach Befund 7: Symbol **statt**
  Pfeil, wenn ein Blatt aufgeht; Pfeil allein, wenn eine Seite kommt?
- „Einträge des Tages“ bleibt ein Blatt von unten (Ansicht darunter bleibt stehen) — oder
  eine Seite, wenn es über das Menü aufgerufen wird?
- Reihenfolge im Blatt: Einträge · Üben · Nachtragen · Verlauf · Tag · Übungsseite (Skizze
  D2: das Tipp-Ziel zuerst)?
- Bei mehreren Plänen an einem Tag: „Üben“ im letzten Plan der Zeile — oder je Plan ein
  Eintrag im Blatt?

## 9. Bens Antworten (28.10.2026) und was gebaut wurde

- **Symbol statt Pfeil** („Der Pfeil ist tatsächlich überflüssig, wenn ohnehin ein Symbol
  dasteht“): In `uebungszeile` ersetzt das Zielsymbol den Pfeil; der Pfeil bleibt nur in
  Listen, die keine Übungen eines Tages sind (Katalog, Einstellungen …).
- **Blatt von unten** bleibt für „Einträge des Tages“ („orientierungsmäßig am
  übersichtlichsten“).
- **Reihenfolge im Blatt:** Einträge des Tages · Nachtragen · Üben (je Plan der Zeile:
  „Plan 1“, „Plan 2“, dann „Standardübung“) · Verlauf · Tag · Übungsseite. Üben ist an den
  Ursprung des Eintrags gekoppelt („Montag Kniebeugen dynamisch, Dienstag statisch“):
  `ueben_ziele` öffnet den Plan bei dieser Übung (`plan_ziel` = Item-ID), nur wenn Plan und
  Item noch existieren; die Standardübung ist `/training/<übung>`.
- Gebaut: `ui/components/ziele.py` (Ziel, Zielsymbol, Zielblatt mit `Nachher`),
  `ui/views/ziele.py` (`ziele_fuer`, `ueben_ziele`), `uebungszeile(ziel=…, weitere=…)`;
  Heute (Übersicht mit Hilfezeile, Zeitleiste), Verlauf → Tage (ohne Pläne: nur die
  Standardübung) und Übungen (ohne Tag), Tagebuch (Übung/Aufnahme → Einträge mit
  `nachtragen=`, Notiz zum Tag/Plan/Tagesfeld → Notiz + Tag). Chip „Steht an“ ohne Tooltip.
  Tests `tests/test_ui_ziele.py`.

## 10. Zweite Runde (28.10.2026): überall, wo es mehr als einen Weg gibt

Ben: „Schau wo es sonst sinnvoll sein kann, so ein Routingmenü aufzumachen, z. B. bei ‚Zum
Tag‘ die Tagesfelder oder anderswo“ — und zur Bestandsaufnahme: 1 bis 7 bauen, 8 nicht.

Neue Ziele: Eintragen (`EDIT`, Tagesfeld-Blatt), Feld bearbeiten (`TUNE`), Auswertung
(`ANALYTICS_OUTLINED`), Bearbeiten (`EDIT_OUTLINED`, wie überall), Ablauf starten
(`PLAYLIST_PLAY`). Helfer `views/ziele.tagesfeld_ziele`, `plan_ziele`, `ziele_fuer(…,
bearbeiten=True)`, `ui/ziele_liste.auswertung_und_tag`.

| Ort | Tipp (Symbol) | Gedrückt halten / Symbol |
|---|---|---|
| Heute → Zum Tag, Tagesfeld | Eintragen (Blatt) | Verlauf · Feld bearbeiten — kein Tooltip mehr |
| Verlauf → Zum Tag | Verlauf (Kurve) | Eintragen (heute) · Feld bearbeiten |
| Tagebuch, Tagesfeld | Eintragen | Verlauf · Feld bearbeiten · Tag |
| Übungen → Übungen (Katalog) | Übungsseite; Knopf „Trainieren“ bleibt | Nachtragen · Üben (Standardübung) · Verlauf · Bearbeiten |
| Verlauf-Kurve einer Übung, Liste unten | Tag | Einträge des Tages · Nachtragen · Üben · Übungsseite |
| Verlauf-Kurve eines Tagesfelds, Liste unten | Tag | Eintragen an dem Tag · Feld bearbeiten |
| Aufzeichnungen → HRV, Strecken | Auswertung | Tag |
| Übungen → Pläne | Bearbeiten; Knopf „Trainieren“ bleibt | Üben (heute) · Ablauf starten |
| Heute → „Steht an“, Chip | gemacht (kein Symbol) | Nachtragen · Üben im Plan · Verlauf · Übungsseite — vorher direkt Nachtragen |
| Zeitleiste, Planblock-Kopf | heute: Üben; sonst nur das Blatt | Bearbeiten · Ablauf starten |

Nicht angefasst (Punkt 8, siehe Erklärung an Ben): Einheit-Karten, Kurse, Pakete,
Einstellungen — dort führt der Tipp zu genau einer Seite, es gibt keinen zweiten Weg.

