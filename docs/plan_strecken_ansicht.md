# Planung: Strecken in Live und Auswertung — Herzfrequenz, Einfärben, Kilometer-Tabelle (26.10.2026)

Ben: „Lass uns die Strecken in Live und Messung noch verbessern. DFA α1 wird angezeigt. Die
Messung an sich ist einsehbar über den HRV-Link-Button unten. Kannst du die HR trotzdem mit
rein nehmen oberhalb von DFA α1? Für RR braucht es eine Fensterauflösung, das wird dort zu
kompliziert, dann lieber wechseln ins HRV-Analysefenster. — Lässt sich die Kurve mit der
zurückgelegten Strecke einfärben mit der Geschwindigkeit? Einstellung der Farbe in den
Einstellungen, finde gute Standardfarben. — ‚Je Kilometer‘: Zeit und Tempo unterscheiden sich
nur, wenn man Pause gemacht hat … Zeit als Gesamtzeit und in der Zeile ein kleiner Schalter,
um Pausen zu ignorieren … Höhe rein- oder raussetzen, dafür Pause … Was macht Sinn?“

Stand: **gebaut am 26.10.2026** (Ben: „Bau das so, Vorschläge passen, keine Skizzen nötig“) —
Abschnitt 6 nennt, was wo liegt; Gerätetest T79. Katalog P81; löst A17 (GPS-Bereich umbauen)
und den Streckenteil von P50 (HF in der Anzeige) ein. Kein RR in der Auswertung — dafür der Knopf
„HRV-Auswertung öffnen“ (Ben).

---

## 1. Was heute da ist (am Quelltext geprüft)

| Ansicht | Zeigt | Rechnet in |
|---|---|---|
| **Live** (`ausdauer_inhalt`) | große Zahlen: Zeit, Distanz, Tempo, Ø Tempo, Herzfrequenz, DFA α1 (EKG); Karte mit einfarbiger Linie (`StreckenKarte`); Tabellen „Intervalle (vom Timer)“ und „Kilometer (vom GPS)“ | `core.intervalle.live_tabellen`, `StreckenRechner` |
| **Auswertung** (`ausdauer_detail_view`) | Überblick (Distanz, Zeit, Bewegungszeit, Ø Tempo, Höhe), Karte (`ganze_strecke`, einfarbig, Start/Ziel), „Intervalle (vom Timer)“, „Je Kilometer“ (km · Zeit · Tempo · Ø HF · DFA α1 · Höhe), „DFA α1 — Überblick“ (Kurve über Minuten, Minuten je Wertebereich), Karte „HRV“ mit dem Knopf | `_km_tabelle`, `_dfa_teil`, `core.hrv_training` |

„Je Kilometer“ heute: **Zeit** = Dauer des Kilometers mit Pausen (`t_ende − t_start`),
**Tempo** = Bewegungszeit je km (`Split.bewegt_s`, Auto-Pause herausgerechnet). Darum
unterscheiden sie sich nur mit Pause — Bens Beobachtung stimmt.

---

## 2. Herzfrequenz in der Auswertung — eine Karte „Herzfrequenz und Tempo“ über DFA α1

Eine Kurve, zwei Werteachsen (`components.kurve` kann `rechts=Skala`): **links Herzfrequenz**
(Schläge/min, `FARBEN["hf_rr"]`), **rechts Tempo** (min/km bzw. km/h beim Rad, in der
Tempofarbe). Darüber zwei Chips für die x-Achse: **Zeit** (Minuten seit Start, wie die
DFA-Kurve) und **Strecke** (km) — A17: „eine Kurve mit x = Strecke oder Zeit“. Pausen
erscheinen auf der Zeitachse als Lücke im Tempo, auf der Streckenachse verschwinden sie.

Rechnung in `core/hrv_training.py`: `hf_reihe(rec, korr, beginn_s, schritt_s=5)` — Mittel der
Herzfrequenz je 5-s-Fenster aus den korrigierten RR-Werten (wie `hf_je_zeit`, nur als Reihe);
Tempo je Fenster aus `core.forschung.tempo_reihe` (gibt es); Strecke je Zeit aus
`core.intervalle.strecke_auf_achse` (gibt es). **Kein RR, kein Fenster, keine Analyse** — wer
das will, drückt den Knopf „HRV-Auswertung öffnen“ (Ben).

Live bleibt die Herzfrequenz die große Zahl; eine Live-Kurve brächte dort nur Unruhe.

---

## 3. Strecke nach Tempo einfärben

**Ja, das geht** — in Live und Auswertung. flet-map zeichnet eine Linie entweder einfarbig
oder mit einem Farbverlauf über Stützstellen (`gradient_colors`/`colors_stop`); bei Tausenden
Ortungen ist der Verlauf unhandlich. Robuster: **ein Linienstück je ~10 s** (oder je 25 m),
jedes in seiner Farbe (`PolylineLayer` mit einigen hundert `PolylineMarker` — für eine Stunde
etwa 360; die Karte verkraftet das, die Live-Karte baut ohnehin jede Sekunde neu). Stillstand
(Auto-Pause) als graues, gepunktetes Stück. Weiße Randlinie (`border_color`,
`border_stroke_width` 1), damit auch helle Farbtöne auf der Karte stehen.

**Skala relativ je Training:** Das Tempo wird zwischen dem 10. und 90. Perzentil dieses
Trainings auf die Farbskala gelegt — ein Spaziergang und ein Tempolauf färben sich beide voll
aus, und es braucht keine Grenzwerte je Sportart. Unter der Karte eine **Legende**: Farbbalken
mit „langsam 7:40 … schnell 4:50“. *Absolute Grenzen (zum Vergleich zweier Läufe) wären eine
spätere Einstellung.* Glättung: das Doppler-Tempo als gleitendes Mittel über 10 s, sonst
flackert die Linie.

**Einfärben nach:** Tempo (Vorgabe) · Herzfrequenz (A17, dieselbe Mechanik mit `hf_je_zeit`)
· aus (einfarbig wie heute).

**Farbskalen — Vorschlag für die Vorgabe** (fünf Stufen, auf der OSM-Karte geprüft,
dunkel und hell gleich, weil die Karte immer hell ist):

| Name | langsam → schnell | Warum |
|---|---|---|
| **Tempo** (Vorgabe) | `#2166AC` Blau · `#4DAC26` Grün · `#E6A100` Gelb · `#F46D43` Orange · `#D7191C` Rot | die Lesart von Strava/Garmin, auf der Karte kräftig genug; Rot/Grün liegen nicht nebeneinander, dazwischen Gelb und Blau |
| **Viridis** | `#440154` · `#3B528B` · `#21918C` · `#5EC962` · `#FDE725` | farbenblind-sicher, Helligkeit steigt monoton — das Auge liest „heller = schneller“ auch ohne Farbe; Gelb braucht die weiße Randlinie |
| **Glut** | `#2C0F4A` · `#7B2A8A` · `#C64C6B` · `#F38B3A` · `#FBE56A` | dunkel → hell, warm; gut auf heller Karte |

Die Skala steht in `ui/farben.py` (`TEMPO_SKALEN`), die Stufe rechnet `core/strecke_farbe.py`
(reine Mathematik: Perzentile, Stufe je Fenster — mit Doctests). Für die HF-Einfärbung
dieselben Skalen.

---

## 4. „Je Kilometer“ — Zeit, Tempo, Pausen, Spalten

**Vorschlag:**

- **Zeit = Gesamtzeit** am Ende des Kilometers (kumuliert, mit Pausen — die Uhr, die beim
  Start losläuft; wie der Zieleinlauf eines Rennens). Die Dauer des einzelnen Kilometers
  steckt im Tempo.
- **Tempo** je km, **wahlweise ohne oder mit Pausen**: ein kleiner Chip rechts im Titel der
  Karte, „ohne Pausen“ ⇄ „mit Pausen“. Ohne Pausen = Bewegungszeit je km (heute); mit Pausen =
  Echtzeit je km (`t_ende − t_start`). Der Chip gilt sofort, bleibt gemerkt (Einstellung) und
  wirkt auch auf die Live-Tabelle „Kilometer (vom GPS)“, die Tabelle „Intervalle“ und den
  Ø-Tempo-Wert im Überblick — eine Lesart, überall.
- **Pause** als eigene Spalte: Sekunden Stillstand im Kilometer („–“ ohne Pause); zeigt auf
  einen Blick, wo Zeit und Tempo auseinanderlaufen.
- **Spalten wählbar** (Einstellung): km · Zeit · Tempo · Ø HF · DFA α1 · Höhe ↑ · Höhe ↓ ·
  Pause. Vorgabe an: km, Zeit, Tempo, Ø HF, DFA α1 (nur EKG), Höhe ↑; aus: Höhe ↓, Pause.
  Mehr als sechs Spalten passen hochkant nicht; im Querformat (die Auswertung dreht mit)
  alle.

---

## 5. Einstellungen → Training (neue Seite)

Eine eigene Seite neben „HRV-Messung“ und „Timer“, gerätelokal wie `HrvEinstellungen`
(`core/training_einstellungen.py`, JSON in `app_setting`, Schlüssel `training_einstellungen`):

| Einstellung | Werte | Vorgabe |
|---|---|---|
| Strecke einfärben nach | Tempo · Herzfrequenz · aus | Tempo |
| Farbskala | Tempo · Viridis · Glut | Tempo |
| Tempo je km | ohne Pausen · mit Pausen | ohne Pausen |
| Spalten „Je Kilometer“ | Häkchen je Spalte (Abschnitt 4) | wie oben |
| Kurve „Herzfrequenz und Tempo“: x-Achse | Zeit · Strecke | Zeit |
| Auto-Pause | an · aus (Schwelle wie bisher, `STAND_TEMPO_MS`) | an |

Was ich **nicht** vorschlage: Zonen oder Grenzwerte für Herzfrequenz und Tempo (eine
Bewertung — `docs/recht/00_zweckbestimmung.md`), eine Einstellung je Sportart (erst, wenn
es Rad-Trainings gibt), absolute Farbgrenzen (später, Abschnitt 3).

---

## 6. Umsetzung

| Schritt | Wo |
|---|---|
| `core/training_einstellungen.py` (Dataclass, `als_dict`/`aus_dict`, Vorgaben, Doctests); `AppState.training_einstellungen()` | core, ui/state |
| `core/strecke_farbe.py`: `tempo_fenster(punkte, schritt_s)` (gleitendes Mittel), `spanne(werte)` (Perzentile), `stufe(wert, spanne, n)`; `ui/farben.TEMPO_SKALEN` | core, ui |
| `components/karte_strecke.py`: `StreckenKarte` und `ganze_strecke` mit `faerbung=` (Liste je Stück: Punkte, Farbe, gestrichelt); Legende als eigenes Control | ui |
| `core/hrv_training.hf_reihe`; Karte „Herzfrequenz und Tempo“ in `ausdauer_detail_view` vor „DFA α1 — Überblick“, Chips Zeit/Strecke | core, ui |
| `_km_tabelle` und `core/intervalle` (Live-Tabelle): Gesamtzeit, Tempo nach Einstellung, Spalten, Pause; Chip im Kartentitel | core, ui |
| `views/einstellungen_training.py` + Eintrag in `einstellungen.py` | ui |
| Tests: Farbstufen und Perzentile (Doctests), Tabelle mit/ohne Pausen auf einer Strecke mit Auto-Pause (`tests/test_ausdauer.py`), HF-Reihe, Einstellungen-Roundtrip, Seite baut | tests |
| Doku: `docs/plan_gps.md` §1 (Danach), Katalog (A17, P50-Streckenteil erledigt), Gerätetest | docs |

*Aufwand (geschätzt): ein Tag. Keine Migration (JSON in `app_setting`).*

---

## 7. Fragen an Ben

| # | Frage | Vorschlag |
|---|---|---|
| F1 | Tempo-Skala relativ je Training (Perzentile) statt fester Grenzen? | Ja, relativ; Legende nennt die Werte. |
| F2 | Welche Skala als Vorgabe: „Tempo“ (blau→rot) oder „Viridis“ (farbenblind-sicher)? | „Tempo“ — die bekannte Lesart; Viridis wählbar. |
| F3 | Zeit in „Je Kilometer“ als Gesamtzeit — und die Dauer des einzelnen km nur über das Tempo? | Ja. |
| F4 | Der Pausen-Chip wirkt überall (Live-Tabelle, Intervalle, Ø Tempo) oder nur in dieser Tabelle? | Überall, eine Lesart. |
| F5 | Soll ich vor dem Bau Skizzen der Auswertung (Karte mit Legende, HF/Tempo-Kurve, Tabelle mit Chip) als Bilder zeigen? | Nein (Ben). |

**Alle fünf entschieden wie vorgeschlagen (Ben, 26.10.2026).** Gebaut: `core/training_einstellungen.py`,
`core/strecke_farbe.py`, `Split.pause_s`/`Split.tempo(mit_pausen=…)`, `intervalle.kilometer(mit_pausen=…)`
mit `gesamt_s`/`pause_s`, `hrv_training.hf_reihe`, `ui/farben.TEMPO_SKALEN`,
`components/karte_strecke` (`faerbung_aus`, `legende`, `StreckenKarte.faerben`, `ganze_strecke(faerbung=…)`),
`views/ausdauer.py` (Live: Linie nach Tempo, Legende, Ø Tempo nach Einstellung; Auswertung: gefärbte Karte mit
Legende, Karte „Herzfrequenz und Tempo“ mit Achsenwahl vor „DFA α1 — Überblick“, „Je Kilometer“ mit Gesamtzeit,
Spalten und Chip „ohne/mit Pausen“), `views/einstellungen_training.py` (Route `/einstellungen/training`),
`StreckeBaustein(stillstand_s=…)`/`rechnen(stillstand_s=…)` für die Auto-Pause. Tests
`tests/test_training_einstellungen.py`, `test_ausdauer.py::test_auswertung_und_liste_zeigen_das_training`.
Live färbt nur nach Tempo — die Herzfrequenz je Ortung bräuchte die laufende Aufnahme je Sekunde; sie kommt in
der Auswertung dazu.
