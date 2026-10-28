# Plan: Abschnitte und Notizen — ein Modell (Ben, 27.10.2026)

Ben: „Es braucht eine gute Logik, um Abschnitte und Notizen neu zu ordnen … Was sicher
ist, ist, dass auch Live einen Abschnitt braucht. Abschnitte bei Live und Aufzeichnungen
brauchen auch einen Scrollbereich wie Notizen. Wenn Abschnitte eingeklappt werden, sollen
die klickbaren Bereiche bleiben. … Sind die Anfangs- und Endteile der Abschnitte
gleichzeitig Notizen? Häufig muss ich für die Arbeit Abschnitte bestimmen für
Behandlungstermine. Dann kann ich Start–Ende tippen und habe den Bereich. Gleichzeitig
brauche ich vielleicht zusätzliche Aufzeichnung von Kopf und Ende, um die Wirkung und den
Verlauf besser bestimmen zu können.“ — Entscheidungen vom 27.10.: Reihe A und B der
Bildergeschichte (https://claude.ai/artifact/39QdbehmadFijvaU7YXjeL) so; bei C „Kopf/Endteil
genauer einstellbar, Kopf/Endabschnitte erst auf Buttonklick erscheinend. Die Rechnungen
nehmen Kopf und Ende mit. Keine 3 separaten Bereiche.“ Vorzeichen: positiv = außerhalb
(davor/danach), negativ = innerhalb (Ben: „stimmt“).

Katalog: P86. Vertrag: `docs/kompatibilitaet.md` §4 (Marke) und §9b (Abschnitte).

## 1. Bisher: drei Herkünfte

| Herkunft | Live | Datei | Sidecar | Bearbeiten |
|---|---|---|---|---|
| Timer, Plan-Ablauf, Übung (Stoppuhr), km | Notiz mit Marke je Grenze (`art=abschnitt`, `uebung_start` …) | ja | beim Speichern aus den Grenzen (`spuren_speichern`) | nur im Sidecar (Grenzen verschieben) |
| selbst gesetzt („+ Abschnitt“ in der Auswertung) | — | **nein** | ja | nur im Sidecar |
| „Ganze Messung“ | — | — | praxis_gui (`gesamt`) | — |

Live gab es weder „+ Abschnitt“ noch eine Abschnittsliste; selbst gesetzte Abschnitte
fehlten in der Notizliste.

## 2. Das Modell: ein Abschnitt ist ein Paar Grenz-Notizen

- **Jeder Abschnitt beginnt mit einer Notiz mit Marke und endet mit einer** — beim Timer
  wie bisher die Kette (jede Grenze beendet die vorige), bei einem **eigenen Abschnitt** ein
  Paar: `{"quelle": "person", "art": "abschnitt", "spur": "seg-1a2b3c4d", "name":
  "Behandlung", "kopf_s": -120, "endteil_s": 300}` und `{"quelle": "person", "art": "ende",
  "spur": "seg-1a2b3c4d", "name": "Behandlung"}`. Die **Spur ist die Kennung** des
  Abschnitts (dieselbe wie `id` im Sidecar): So schneidet kein eigener Abschnitt einen
  anderen, Überlappen ist erlaubt, und das Sidecar-Segment behält über jede Änderung seine
  `id` (praxis_gui-Kennzahlen bleiben, bis sich die Grenzen bewegen).
- Die Notizen stehen in der **Messdatei** (`ereignisse`, wie jede Notiz: Anker, `wall_time`,
  Text „Behandlung: Start“ / „Behandlung: Ende“). Sie erscheinen in der Notizliste live und
  nachträglich, sind dort verschiebbar, umbenennbar, löschbar.
- Das **Sidecar wird daraus abgeleitet** (`ausschnitte.spuren_speichern` beim Speichern der
  Aufnahme, `zusatz_speichern` in der Auswertung): `segments` mit `t_start_s`/`t_end_s` =
  die **getippten** Grenzen (der Kern — was praxis_gui als Abschnitt sieht), dazu das
  Zusatzfeld `rand: {"kopf_s", "endteil_s"}`. praxis_gui behält unbekannte Felder nicht
  (§9b) — die Wahrheit für Kopf und Endteil ist die Marke der Start-Notiz.
- **Kopf und Endteil** (`kopf_s`, `endteil_s`, Sekunden mit Vorzeichen) hängen an der
  **Start-Notiz** des Abschnitts — bei eigenen Abschnitten und bei jedem Abschnitt, dessen
  Anfang auf einer Notiz mit Marke liegt (Timer, Übung). Der **Rechenbereich** eines
  Abschnitts ist `von_s − kopf_s` bis `bis_s + endteil_s` (`Abschnitt.rechenbereich`),
  begrenzt auf die Messung bzw. den Zuschnitt: Kopf +5:00 nimmt fünf Minuten davor mit,
  Kopf −2:00 lässt die ersten zwei Minuten weg. **Alle Werte eines Abschnitts** (Liste,
  Tabelle, Analysefenster „Abschnitt“, Spektrum) rechnen auf dem Rechenbereich — keine
  getrennten Teile.
- **Zu kurze Fenster** verstecken nichts: Was das Fenster nicht trägt, steht grau mit der
  Mindestlänge (hrv-core `BAND_MIN_DAUER_S`: HF ab 3 min, LF ab 5 min, VLF ab 20 min —
  darunter liefert hrv-core schon heute `None`); RMSSD und Ø HF gibt es immer.
- **Bestehende Messungen**: Beim Öffnen der Auswertung bekommt jedes Sidecar-Segment ohne
  Notizpaar, dessen Anfang auf **keiner** Notiz mit Marke liegt (also ein früher selbst
  gesetzter Abschnitt), einmalig sein Paar Grenz-Notizen (`core.abschnitte.nachtragen`);
  Timer-Segmente bleiben, wie sie sind (ihre Grenzen sind schon Notizen).

## 3. Live (Reihe B)

- In der Karte der Hauptkurve über den Breitenknöpfen das Klappfeld **„Abschnitte · n“**:
  Kopfzeile mit Pfeil und dem Knopf **„Abschnitt: Start“**; darunter die **Chip-Zeile**
  (Ganze Messung · je Abschnitt) — sie bleibt auch eingeklappt stehen; darunter die
  **Liste** (Name, von–bis, Dauer), die ab `notizen_zeilen` Zeilen rollt (dieselbe
  Einstellung wie die Notizen).
- „Abschnitt: Start“ setzt die Start-Notiz bei jetzt (Name: Vorschlag aus den gespeicherten
  Überschriften, eigener Text, oder „Abschnitt n“) und wird zu **„‹Name› · Ende“** mit
  laufender Zeit; der Tipp darauf setzt die Ende-Notiz. Nur ein eigener Abschnitt läuft
  zugleich (ein zweiter Start beendet den ersten).
- Ein Chip rückt das Fenster auf den Abschnitt (Breite = Dauer, mindestens 1 min).
- `Messlauf.abschnitt_markieren(spur=<Kennung>)` reiht die Grenzen wie beim Timer ein —
  das Sidecar entsteht beim Speichern wie bisher, mit `id` = Kennung und `rand`.

## 4. Auswertung (Reihe C)

- Beim Laden: Abschnitte = Sidecar-Segmente **zusammengeführt** mit den Notizpaaren
  (`core.abschnitte.zusammenfuehren`): Kennung ↔ `id`; Name, Grenzen, Kopf und Endteil aus
  den Notizen, wo es sie gibt. Segmente ohne Paar und ohne Marken-Notiz am Anfang →
  Notizpaar nachtragen (einmal, `metadaten_schreiben`).
- Klappfeld wie live: eingeklappt bleibt die Chip-Zeile, Liste und Werte klappen zu; die
  Liste rollt ab `notizen_zeilen`.
- **Bereichseditor**: wie heute (Anfang/Ende, Pfeile an den Rand, ±1/±5 s, An Notiz). Neu
  ein Knopf **„Kopf · Endteil“**; erst er blendet die Zeile ein: zwei Knöpfe ⟷ mit dem
  Wert („−2:00“ / „+5:00“), dazwischen der Rechenbereich. Ein Tipp öffnet ein Blatt mit
  Rädern (Minuten, Sekunden, wie `zeit_stellen`), Vorzeichen davor/innerhalb und Tippfeld
  („−2:00“, „5:00“, „300“); Schnellwahl −5 · −2 · −1 · 0 · +1 · +2 · +5 · +10 min. In der
  Kurve liegt der Rechenbereich als blasser Balken unter dem Kernbalken.
- **Speichern** eines eigenen Abschnitts schreibt die Notizen (Start, Ende, Marke mit
  Kopf/Endteil) und danach das Sidecar; eines Timer-Abschnitts die Marke seiner Start-Notiz
  (Kopf/Endteil) und das Sidecar. Löschen entfernt Paar und Segment.

## 5. Schritte — alle gebaut am 27.10.2026 (hrv-core 74d00f6, Gerätetest T82)

1. hrv-core: `MARKE_FELDER` + `kopf_s`, `endteil_s`; `Abschnitt.kopf_s/endteil_s/rechenbereich`;
   `Grenze.id/kopf_s/endteil_s`; `spuren_speichern` liest Kennung und Ränder aus der Marke;
   Sidecar-Feld `rand`; `paare_aus_notizen`; `docs/formate.md`; Tests. Ref anheben.
2. App `core/abschnitte.py`: Kennung, Start-/Ende-Marke, Text, offener Abschnitt,
   `zusammenfuehren`, `nachtragen` (Doctests, ohne flet).
3. Live: Klappfeld, Start/Ende-Knopf, Chips, Liste (`Messlauf.abschnitt_starten/beenden`).
4. Auswertung: Zusammenführen, Nachtragen, Editor mit Kopf/Endteil, Rechenbereich in Werten
   und Kurve, Liste rollt, Chips bleiben.
5. Vertrag §4/§9b, Katalog (P86 → Entschieden, Gerätetest), Bildergeschichte Reihe C.

## 6. Was anders kam als geplant

- Die Zeile „Kopf · Endteil“ steht im Editor hinter einem **Knopf** und erscheint erst
  auf Tipp (Ben: „erst auf Buttonklick erscheinend“); ist ein Rand gesetzt, ist sie gleich
  da. Ein Tipp auf einen der beiden Knöpfe ⟷ öffnet ein **Blatt** (`ui/components/
  abschnitte.rand_blatt`): Richtung davor/danach (+) · innerhalb (−), Räder für Minuten
  und Sekunden, Tippfeld, Schnellwahl — kein Menü.
- **Ein** Rechenbereich je Abschnitt — Liste, Analysefenster „Abschnitt“ und der blasse
  Balken in der Kurve; keine Tabelle Kopf · Abschnitt · Endteil (Ben: „Keine 3 separaten
  Bereiche“).
- Das Nachtragen alter eigener Abschnitte geschieht beim Laden im Thread (`_laden`), nicht
  in der Ansicht; ein Segment gilt als Ablauf-Abschnitt, wenn sein Anfang auf **irgendeiner**
  Notiz liegt (auch „Aus Notizen …“), nicht nur auf einer mit Marke.
- Ein laufender eigener Abschnitt steht live von der ersten Sekunde an in Chip und Liste
  (`paare_aus_notizen` ohne Mindestdauer für Offene).
- Eine Leistungs-Notiz (`person/leistung`, `person/abschluss`) bleibt aus der Notizliste;
  die Grenz-Notizen der Person stehen darin (`messung_detail._ist_leistung`).
- Seit 28.10.2026 steht das Live-Abschnittsfeld auch quer: `components/live_abschnitte.LiveAbschnitte`
  ist ein Objekt für Live-Karte (Klappfeld) und Live-Vollbild (Seitenleiste neben den Notizen).
