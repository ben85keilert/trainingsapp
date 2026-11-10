# HF-Vollbild, Zielbereich mit Tonfolge, Wertebereich, Erholung und Ablese-Intervall

Stand: 10.11.2026 — **gebaut** (Katalog A22), am Gerät ungeprüft. Skizzen H1–H4
(https://claude.ai/artifact/HdxYb75e9kzhX3GFQc1Xxp); Ben: „Baue alles so ein, wie in der
Skizze“, dazu das **Intervall zum Ablesen** (§5).

## 0. Anlass

Im HF-Modus zeigte „Vollbild“ die HRV-Kurven (`views/live_vollbild.py` kannte die Sicht nicht).
Gewünscht (Ben, 10.11.2026): eine eigene HF-Vollbild-Ansicht mit den Bereichen als Stufen; der
Wertebereich der HF-Achse mit Automatik **je Seite**; ein Messbereich für die Erholung (HRR30,
60, X); der Zielbereich im Vollbild und hochkant einstellbar, darüber und darunter zwei Töne,
die **Tonfolge schneller mit der Abweichung**; die Knöpfe „Sprechen wird schwer“ und „Belastung
endet jetzt“; ein Wechsel zur HRV; Ton abschalten. Dazu ein Intervall wie das Crosshair in
praxis_gui: Anfang und Ende setzen, Werte an beiden Stellen mit Delta, HF-Max, HF-Min und die
Erholung in diesem Bereich.

## 1. Rahmen

**Die HF ist der Träger, nicht das Urteil** (`docs/recht/00_zweckbestimmung.md`, Entscheidung C):
Die Ansicht zeigt Zahlen und einen Ton zu **selbst gesetzten** Linien — wie ein Timer. Sichtbar
heißt es immer „Zielbereich“, nie „Warnung“, „Grenze“ oder „Alarm“; die Bereiche sind Stufen
einer Farbe; nichts wird aus dem Puls gesteuert, nichts bewertet oder empfohlen. Die
abgelesene Erholung ist eine Ablesung, kein gespeicherter Kennwert.

## 2. Wo was liegt

| Teil | Ort |
|---|---|
| Rechnung der abgelesenen Erholung | hrv-core `herzfrequenz.intervall_erholung` (§5) |
| Tonfolge, Zielton, Stumm, Wertebereich, Trend, Texte | `core/hf_ziel.py` |
| Einstellungen je Profil (Achse je Seite, Erholungsfenster, X, Messen bis, Tonfolge) | `core/hf_einstellungen.py` |
| Werte des Messlaufs für beide Ansichten (Punkte, Kurve, Erholung, Marken, Ton) | `ui/hf_live.py` (`HfLive`) |
| Bausteine: Zielbereich-Seite, -Zeile, -Blatt, Wertebereich, Erholung messen, Karten | `ui/components/hf_sicht.py` |
| HF-Vollbild | `ui/views/hf_vollbild.py`, eingehängt in `views/live_vollbild.py` |
| Hochkant | `ui/views/messung.py` (nutzt `HfLive`) |

Zustand, der den Neuaufbau einer Ansicht überlebt, liegt im `AppState`: `hf_erholung`,
`hf_zielton` (eine Uhr der Tonfolge für Messung, Vollbild und Fokus), `hf_stumm`,
`hf_intervall`. Kein Datenbankschritt; die Einstellungen stehen wie bisher je Profil in
`app_setting` (`hf_einstellungen:<profil>`), neue Felder mit Vorgaben.

## 3. Das Vollbild (Skizzen H1–H3)

Route bleibt ``/live`` (quer). `live_vollbild_view` zeigt das HF-Vollbild, wenn die Sicht
„Herzfrequenz“ gilt oder das Gerät nur den Puls sendet; **„HRV“** oben rechts wechselt die Sicht
(dieselbe Wahl wie hochkant, `state.hrv_sicht_setzen`), das HRV-Vollbild hat dafür ein ♡ neben
dem ✕. Reine Pulsgeber haben den Wechsel nicht.

- **Kopf:** ✕ · „Herzfrequenz“ · Chip **Bezug** (Tipp wechselt Aufnahme → Abschnitt → 5 min;
  bewusst kein Menü — Flutter-Menüs reichen den schließenden Tipp an die Kurve weiter) ·
  Lage zum Zielbereich („156 · 6 über dem Zielbereich“, nur mit Ton) · Zeitbreiten · HRV.
- **Links:** große Zahl, Bereich · % Reserve, Trend der letzten Minute (Ausgleichsgerade,
  „↗ +3 bpm/min“), darunter Ø und Gipfel des Bezugs, Zeit im Zielbereich (im sichtbaren
  Fenster), Drift des laufenden Abschnitts (ab 2 min, `hz.drift`), DFA α1 (Tipp → HRV).
- **Mitte:** die Kurve (Mittel über `hf_mittel_s`) über den Bereichen als Stufen; der
  Zielbereich als zwei Linien — die Linie, hinter der die HF gerade liegt, durchgezogen; am
  rechten Rand je Linie ein **Griff „150 ↕“ zum Ziehen**. Notizen als Marken.
- **Rechts die Leiste:** Sprechen wird schwer (Marke `person/talk`, braucht eine Aufnahme) ·
  Belastung endet jetzt · Notiz (Seitenleiste mit dem Notizfeld) · Ton (öffnet „Zielbereich
  und Ton“; stumm: hebt das Schweigen auf) · Intervall · Fenster & Achse.
- **Zielbereich und Ton** (Seitenleiste, H3): Oben/Unten mit − und + (1 bpm, lang gedrückt
  5), „Aus meinen Bereichen“ (setzt beide Linien auf die Grenzen des Bereichs), Schalter
  „Ton außerhalb“, Klang darüber und darunter, Tonfolge, Stumm 5 min · 15 min · bis Messende.

**Tonfolge nach Abstand** (`core.hf_ziel.TONFOLGE`, Stufen statt Formel, damit man sie nachlesen
kann): bis unter 5 bpm alle 6 s · ab 5 alle 4 s · ab 8 alle 3 s · ab 12 alle 2 s · ab 15 jede
Sekunde. Sie ist die Vorgabe (`alarm_takt_s = 0`); die festen Takte 3/4/5/10 s bleiben wählbar,
ein gespeicherter fester Takt bleibt. „Stumm bis Messende“ gilt, solange dieselbe Aufnahme
(ohne Aufnahme: dieselbe Verbindung) läuft.

## 4. Erholung (Skizze H2) und Wertebereich (Skizze H4)

**Erholung.** „Belastung endet jetzt“ merkt den Zeitpunkt (Marke `person/erholung` wie
bisher). Fenster: die festen **30 · 60 · 120 s** (einzeln abwählbar) und das freie **X**
(Vorgabe 180 s, 10–900 s, abschaltbar); **„Messen bis“** (1 · 2 · 3 · 5 · 10 min, nie kürzer
als das längste Fenster) beendet die Erholung von selbst. Im Vollbild: Kopf „Erholung · seit
Belastungsende 0:42 · Messen bis 3:00“ (Tipp stellt weiter), Marken an Ende und Fenstern, eine
Karte, in der sich die Werte füllen („in 0:18“ → „−24 bpm“), blass dahinter die vorige
Erholung dieser Aufnahme, auf das jetzige Ende geschoben; links HF am Ende, Haltung, Woran.
Leiste: „Erholung beenden“ · „Neue Belastung beginnt“ (beendet und schreibt eine schlichte
Notiz). Ein Fensterwert steht erst, wenn sein 5-s-Mittel ganz vorliegt — er ändert sich
danach nicht mehr.

**Wertebereich** (`core.hf_ziel.wertebereich`): oben und unten **je für sich** Automatik ·
Profilwert (HFmax bzw. Ruhe-HF) · fester Wert. Vorgabe Profil/Profil (Ruhe-HF bis HFmax;
fehlt der Wert, Automatik). Eine gesetzte Seite weicht der Kurve — nichts wird abgeschnitten.
Gilt hochkant und im Vollbild; ersetzt „Bereiche im Bild | alle“ und die feste HF-Werteachse
(reine Pulsgeber behalten sie: ihre Kurve ist die des Geräts).

**Hochkant** (`views/messung.py`): Zeile „Zielbereich 130–150 − + Ton an“ (− und + rücken den
ganzen Bereich um 5 bpm, Tipp auf den Text öffnet das Blatt „Zielbereich und Ton“), die Linien
in der Kurve, die Knöpfe „Sprechen wird schwer“ und „Belastung endet jetzt“ nebeneinander,
im Blatt „Fenster & Darstellung“ die Gruppen Wertebereich · Herzfrequenz · Zielbereich und Ton ·
Erholung messen.

## 5. Das Intervall — abgelesene Erholung

**Bedienung.** „Intervall“ hält die Kurve an und setzt zwei Linien: den Anfang auf das letzte
„Belastung endet jetzt“ (wenn es im Bild liegt, sonst ins erste Drittel), das Ende kurz vor
jetzt. Ziehen greift die nähere Linie (nur nahe an ihr — sonst blättert die Geste), ein Tipp
rückt die nähere dorthin. Die Karte zeigt: HF am Anfang und am Ende mit Zeit und Δ, **HF-Max**
und **HF-Min** mit Zeit, die Wahl des Bezugs und die Erholung („HRR 95 s: −31 bpm“).

**Logik** (`hrv_core.herzfrequenz.intervall_erholung`, hrv-core `docs/hrv_algorithmen.md`):

1. **Nie Einzelschläge.** Jeder Wert ist ein 5-s-Mittel um seine Stelle — dieselbe Mittelung
   wie bei HRR30/60 (`HF_ERHOLUNG_MITTEL_S`, mindestens 60 % der Zellen). Fehlt zu viel, steht
   „–“: lieber eine Lücke als ein falscher Wert.
2. **Nur zwei Werte zählen: Bezug und Ende.** Erholung = HF_Bezug − HF_Ende, X = Ende −
   Zeitpunkt des Bezugs. Die Erholung muss nicht monoton sein (ein Atemzug hebt die HF kurz);
   ein Zwischenanstieg in der Mitte ändert darum nichts.
3. **Bezug wählbar: Spitze (Vorgabe) oder Anfang.** Die Spitze ist das höchste 5-s-Mittel im
   Intervall — auf einem Plateau dessen **letzte** Stelle (höchstens 0,5 bpm darunter), denn von
   dort an fällt die HF. Die HF steigt nach dem Belastungsende oft noch kurz; wer den Anfang
   etwas zu früh setzt, bekommt mit „Spitze“ trotzdem denselben Wert. „Anfang“ nimmt genau die
   gesetzte Stelle — für alle, die den Bezug selbst bestimmen wollen.
4. **Das Ende gegen den tiefsten Wert.** HF-Min ist das tiefste 5-s-Mittel ab dem Bezug.
   Liegt das Ende mehr als 3 bpm darüber, steht es da („Ende liegt 5 bpm über dem tiefsten
   Wert (bei 1:12)“) mit dem Knopf **„Ende auf den tiefsten Wert“**. Sonst stellt man Anfang
   und Ende selbst.
5. **Nichts wird gespeichert** — außer auf Wunsch „Als Notiz festhalten“ (eine gewöhnliche
   Notiz am Ende des Intervalls, „HRR 87 s: −39 bpm (151 → 112, ab Spitze)“; braucht eine
   Aufnahme).

## 6. Abweichungen von der Skizze

- **Bezug** und **Messen bis** sind Chips, die per Tipp weiterschalten, keine Menüs (▾).
- **„Im Zielbereich“** zählt das sichtbare Fenster, nicht den Bezug (der Akkumulator des
  Bezugs kennt die Linien nicht). **Drift** in bpm, nur mit laufendem Abschnitt ab 2 min.
- **Erholungsfenster:** 30/60/120 abwählbar und **ein** freies X; „+ Fenster“ (weitere freie
  Fenster) gibt es nicht.
- **Wertebereich „Fest“** ist ein Segment plus Feld daneben statt „Fest 180 ✎“.
- **Hochkant:** − und + rücken den ganzen Zielbereich um 5 bpm; einzelne Linien im Blatt.
  Das Intervall gibt es nur im Vollbild.
- **H2 „Bezug: Abschnitt 2 · 6:40“:** der Chip nennt nur die Art des Bezugs.
- Notiz-Etikett und Abschnitte-Leiste des HRV-Vollbilds hat das HF-Vollbild nicht; das
  Notizfeld steht in der Seitenleiste.
- Einstellungen → Herzfrequenz: Karte heißt „Zielbereich und Ton“ (vorher „Signal über einer
  Grenze“), Feld „darüber“ (vorher „Grenze“), „Tonfolge“ mit „nach Abstand“.

## 7. Prüfung

- hrv-core: `tests/test_herzfrequenz.py` (`intervall_erholung`: Spitze/Anfang, Plateau,
  Zwischenanstieg, Lücken), Doctest. Kein `ALGO_VERSION`-Sprung, Golden unberührt.
- App: `tests/test_hf_ziel.py` (ohne flet), `tests/test_ui_hf_vollbild.py`,
  `tests/test_ui_herzfrequenz.py`, `tests/test_ui_vollbild.py`; Doctests in `core/hf_ziel.py`
  und `core/hf_einstellungen.py`.
- **Braucht `hrv-core.ref`** auf dem Stand mit `intervall_erholung` — vorher scheitert die CI
  am Intervall-Test.
- Am Gerät offen (Katalog T): Lage und Ziehen der Griffe, Tonfolge im Lauf, Platz der Leiste
  und der Karten im Querformat, Blatt hochkant.
