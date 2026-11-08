# Verzweigungen im Workout — Ablauf, Einschub, Bedarf, Schleife

Ben, 8.11.2026 (abends): „Es gibt Workoutpläne, die sich linear abarbeiten. Evtl. gibt es
Abweichungen zur Seite: nach einer schweren Isometrieübung sRPE 7/10 (Krämpfe/Druck) kommt
zwischendurch eine Dehnübung, dann geht es weiter. Dabei können Übungen, die im Plan sind, gar
nicht erst vorkommen, weil sie nur bei Bedarf gebraucht werden. Entwickle einen Plan, wie man
das am besten umsetzt, die verschiedenen Kombinationsmöglichkeiten intuitiv einzubauen.“

Dieses Dokument ist der Plan (8.11.2026). Es baut auf `docs/plan_workout.md` (W1–W4, Wege,
Skala) auf und **korrigiert die Logik** der Zweige. Entscheidungen für Ben: **P108–P111** (§7).

## 1. Befund: was heute nicht stimmt

Heute kennt das Workout **Zweige A–D** (Listen), je Schritt „erfüllt →“ / „nicht erfüllt →“,
seit heute Abend **Wege** (Knöpfe) und Verweise auch auf gemachte Übungen (Schleifen). Damit
geht vieles, aber zwei Dinge nicht — und ein drittes nur umständlich:

1. **Kein Zurück.** Wer von Wandsitz zur Dehnung abzweigt, läuft danach dort weiter, wo die
   Dehnung im Plan steht — nicht dort, wo er herkam. „Zwischendurch eine Dehnübung, dann geht
   es weiter“ ist heute nicht abbildbar.
2. **Jede Übung kommt dran.** Eine Dehnung, die nur bei Krämpfen gebraucht wird, steht im
   Hauptzweig und läuft mit — es sei denn, man steckt sie in Zweig B. Dass „Zweig B“ heißt
   „nur bei Bedarf“, versteht niemand ohne Erklärung.
3. **Zweige sind abstrakt.** A–D, „erfüllt →“, „nicht erfüllt →“, Wege — vier Werkzeuge für
   drei Absichten. Die Absichten heißen: *linear weiter*, *kurz zur Seite und zurück*,
   *noch einmal*, selten *woanders weitermachen*.

## 2. Begriffe (statt Zweige)

| Begriff | Bedeutung | Heute |
|---|---|---|
| **Ablauf** | die Planübungen, die von selbst nacheinander drankommen — die Liste des Plans ohne die Bedarfsübungen | Zweig A |
| **Bedarfsübung** | steht im Plan, kommt aber **nie von selbst** dran — nur über einen Einschub oder Abzweig; im Plan-Editor als eigener Block „Bei Bedarf“ | Zweig B–D (versteckt) |
| **Einschub** | ein Schritt zur Seite: eine Bedarfsübung (oder jede andere) **mit Rückkehr** — danach geht es dort weiter, wo man war (Vorgabe: mit der nächsten Übung; wahlweise die unterbrochene noch einmal) | — |
| **Abzweig** | woanders weitermachen, **ohne Rückkehr** (heutiges „erfüllt →“/„nicht erfüllt →“ und Wege) | Verweis |
| **Schleife** | „noch einmal“ — dieselbe Übung erneut, so lange, bis eine Bedingung greift (Skala, Zeit, Wiederholungen) oder die Person wählt | Weg auf sich selbst |
| **Auslöser** | was einen Einschub, Abzweig oder die Schleife anbietet oder auslöst: **von Hand** (Knopf), **Skala ≥ n** (Selbsteinschätzung im Schritt), **Zeit ab**, **n Wiederholungen** | Bedingung + dann/sonst |
| **Anbieten / ausführen** | ein Auslöser kann den Weg nur **anbieten** (Knopf wird betont) oder **ausführen** (geht von selbst, wie der harte Übergang) | hart/weich |

Zweige A–D bleiben im Datenformat (Pakete, alte Pläne), verschwinden aber aus der Oberfläche —
„Bedarfsübung“ ist Zweig B ohne Buchstaben, „Abzweig“ ist ein Verweis ohne Rückkehr (▶ P108).

## 3. Das Modell

### 3.1 Daten

- `PlanItem.bedingung.bedarf: bool` — die Planübung ist eine Bedarfsübung (nicht im Ablauf).
  Alternativ als Feld an der Planübung (`PlanItem.rolle`), aber die Bedingung ist schon der
  Ort für „wie geht es weiter“ — dort bleibt alles zusammen (eine Karte, ein Paketfeld).
- **Verweis** statt nackter ID: `Verweis(ziel, einschub: bool = False, zurueck: bool = False)`
  für `dann`, `sonst` und jeden `Weg`. `einschub` = mit Rückkehr; `zurueck` = nach dem Einschub
  die unterbrochene Übung **noch einmal** (sonst: weiter mit der nächsten im Ablauf).
  Rückwärtskompatibel: ein String im JSON ist ein Verweis ohne Einschub.
- `Weg` bekommt den **Auslöser**: `Weg(ziel, text, ausloeser: "hand" | "skala", n, ausfuehren)`.
  Mit `skala` wird der Weg ab `n` betont (anbieten) oder ausgeführt (`ausfuehren=True`).
- Die Bedingung behält `art` (Zeit, Wiederholungen, Skala, Abhaken) für „erfüllt →“ — das ist
  der **reguläre** Weiterweg; die Wege sind die **Seitenwege**.

### 3.2 Der Baustein (`devices/plan_ablauf.py`)

- **Ablauf** = `naechster_im_zweig` über die Schritte **ohne** `bedarf` (ein Bedarfsschritt ist
  nie „nächster von selbst“ und zählt nicht als offen fürs Ende).
- **Rückkehr-Stapel** `_rueckkehr: list[tuple[int, bool]]`: Geht es über einen Einschub zu
  Schritt k, wird (Ursprung, zurück?) gemerkt. Endet k und hat selbst kein „erfüllt →“, kommt
  der Stapel dran: zurück zum Ursprung (noch einmal) oder zur nächsten Übung nach ihm. Einschub
  im Einschub stapelt (Dehnung → Atmung → zurück → zurück). Abbrechen leert den Stapel.
- **Schleife**: Verweis auf sich selbst (gibt es seit heute); die Zahl der Durchläufe steht im
  Fokus („2. Durchlauf“), jeder Durchlauf ein Eintrag.
- **Auslöser Skala**: der Skalenwert des Schritts (`person/skala`) prüft die Wege mit
  `ausloeser="skala"`: anbieten = Knopf betont + Satz „Skala 7 — Dehnung angeboten“; ausführen =
  Schritt endet sofort als fertig, Einschub beginnt (nur, wenn kein Timer mehr läuft oder im
  harten Übergang; weich wartet auf den Tipp — Prinzip „eine App hält niemanden fest“ gilt
  umgekehrt genauso: sie schubst auch niemanden).

### 3.3 Das Workout (Fokus)

- Im Schritt: die reguläre Karte (Bedingung), die **Skala-Chips**, wenn irgendein Weg des
  Schritts Skala als Auslöser hat (nicht nur bei Bedingung „Skala“), darunter die Wege als
  Knöpfe — Einschübe mit dem Zusatz „— danach weiter“ bzw. „— danach noch einmal“, Abzweige mit
  „→“, die Schleife „Noch einmal“.
- Im Einschub steht oben „Einschub · danach: Kniebeuge“ und die Schrittliste zeigt die
  Bedarfsübung eingerückt unter dem Ursprung.
- Die Schrittliste trennt **Ablauf** (nummeriert) und **Bei Bedarf** (ohne Nummer, grau, mit
  ihren Auslösern: „bei Skala ≥ 7 nach Wandsitz · von Hand nach Planke“).

### 3.4 Der Eintrag und die Messung

Nichts Neues: jeder Durchlauf eines Schritts ein Eintrag (`nach_der_uebung`), der Skalenwert
im Skalenfeld; der Einschub ist eine Übung wie jede andere im Workout-Abschnitt. Die Zeitleiste
bekommt `plan/einschub` (Ursprung, Ziel) für die Auswertung („Krämpfe nach Wandsitz: 3 von 5
Workouts“ — später, nicht jetzt).

## 4. Der Editor — intuitiv, drei Stellen

### 4.1 Plan-Editor: zwei Blöcke

Die Übungsliste des Plans bekommt einen zweiten Block **„Bei Bedarf“** unter dem Ablauf. Jede
Planübung hat im Kopf einen Chip **„im Ablauf“ / „bei Bedarf“** (ein Tipp wechselt; die Übung
rutscht in den anderen Block). Ziehen zwischen den Blöcken geht ebenso. Die Zeile „Uhren“
zeigt „5 im Ablauf · 2 bei Bedarf“.

### 4.2 „Im Plan einstellen“ → Karte „Weiter“ mit Mustern

Die Karte „Weiter, wenn …“ heißt **„Weiter“** und beginnt mit **Mustern** als Chips — ein Tipp
füllt die Karte vor, alles bleibt danach änderbar:

| Muster | Was es setzt |
|---|---|
| **Weiter** (Vorgabe) | nichts — Zeit ab oder „Fertig“, dann die nächste im Ablauf |
| **Einschub bei Bedarf** | ein Weg zu einer Bedarfsübung (Dropdown: die Bedarfsübungen zuerst), Auslöser „von Hand“ oder „Skala ≥ n“, Rückkehr „weiter“ |
| **Noch einmal, bis …** | Weg auf sich selbst mit Auslöser „von Hand“, dazu die Bedingung (Skala ≥ n, n Wdh., Zeit) mit „erfüllt → nächste“; optional „Pause dazwischen“ = Einschub einer Bedarfsübung „Pause“ |
| **Pflicht mit Inhalt** | Bedingung hart, Inhalt (Text, Link) |
| **Abzweig** (fortgeschritten) | „erfüllt →“/„nicht erfüllt →“ auf eine andere Planübung ohne Rückkehr |

Darunter die ausgefüllte Karte in **Sätzen**, nicht in Feldern: „Zeit ab → weiter mit *Dehnung*“
· „Skala ≥ 7 → Einschub *Dehnung Beine*, danach weiter“ · „Von Hand: *Planke* (Beine krampfen)
→ Einschub, danach noch einmal“ · „Noch einmal, bis Skala ≥ 6“. Jeder Satz ist antippbar
(öffnet seine Felder) und hat ein ✕. „+ Satz“ fügt einen hinzu. Das ersetzt Dropdown „Zweig“,
„erfüllt →“, „nicht erfüllt →“ und den Wege-Block.

### 4.3 Uhrenplan: eine Zeile je Schritt

Die aufklappbare Karte zeigt die Sätze aus 4.2 gekürzt („Skala ≥ 7 → Dehnung (Einschub) · von
Hand → Planke · noch einmal bis Skala 6“); Bedarfsübungen stehen unten im Block „Bei Bedarf“
mit „kommt dran: nach Wandsitz (Skala 7), nach Planke (von Hand)“ — der **Rückblick**: wer ruft
mich? Das fehlt heute völlig und ist für den Therapeuten die wichtigste Kontrolle.

### 4.5 Das Ablaufbild — scrollen, zoomen, Wege vernebeln

Ben (8.11., Nachtrag): „Ermögliche für den Überblick des Ablaufes eine scroll- und zoombare
Zeichnung mit den Übungsbildern und Übungslabels, wo die verschiedenen Wege sichtbar sind, wenn
es mehrere Wege gibt, auch mit der Möglichkeit, Wege zu vernebeln/verdunkeln.“

- **Ort:** eine eigene Ansicht `<Plan bearbeiten>/ablauf` (Knopf „Ablaufbild“ im Plan-Editor
  neben „Uhren“), dieselbe Zeichnung schreibgeschützt im **Start-Bild des Workouts** (Tipp auf
  die Schrittliste öffnet sie) und als Miniatur im Uhrenplan-Kopf (▶ P112: auch im Fokus, klein
  oben, „wo bin ich“?).
- **Zeichnung:** `ft.InteractiveViewer` (ziehen, zoomen, 0,5–3×) um einen `ft.Stack`: eine
  `ft.Canvas` für die Linien (vorhanden: `components/verlaufskurve.py`), darüber je Planübung
  ein **Knoten** — `components/uebungsbild.uebungsbild` (quadratisch, runde Ecken) mit dem
  Label darunter, Ablauf-Nummer in der Ecke; Bedarfsübungen gestrichelt umrandet. Kein
  Layout-Algorithmus: der **Ablauf** liegt als Spalte von oben nach unten (Reihenfolge des
  Plans), **Bedarfsübungen** rechts daneben auf Höhe ihres ersten Rufers, **Schleifen** als
  Bogen links am Knoten. So bleibt die Zeichnung ruhig und folgt der Liste.
- **Wege als Linien:** Ablauf = kräftige Linie Knoten zu Knoten; Einschub = gestrichelte Linie
  zur Bedarfsübung mit Pfeil **und zurück** (gepunktet zum Rückkehrpunkt); Abzweig = Linie mit
  Pfeil ohne Rückkehr; Schleife = Bogen; am Linienanfang der **Auslöser** als Etikett („Skala ≥ 7“,
  „von Hand: Beine krampfen“, „Zeit ab“). Farben aus `ui/farben.FARBEN` je Art, kein Farbcode
  ohne Form (Strich, Punkt, Bogen) — lesbar auch in Grau.
- **Vernebeln:** ein Tipp auf eine Linie oder einen Knoten **dimmt** den Weg (Linie und alle
  Knoten, die nur über ihn erreichbar sind, auf 25 %); nochmals tippen holt ihn zurück; langes
  Drücken = „nur diesen Weg“ (alles andere vernebelt). Die Wahl gilt für diese Sitzung
  (`AppState.ablauf_vernebelt[plan_id]`), ein Knopf „Alles zeigen“. Im Workout-Start-Bild zeigt
  dieselbe Vernebelung, was heute abgehakt ist (erledigte Schritte grau).
- **Im Workout live:** der laufende Knoten pulsiert leicht (eine Animation, `animate_opacity`),
  der gegangene Weg wird nachgezogen (durchgezogen statt gestrichelt), Einschub-Rückkehr als
  Pfeil zurück. Das Bild ist Anzeige — kein Knopf darin startet etwas (▶ P112: Tipp auf einen
  Knoten = dorthin wechseln, wie die Kachel in der Schrittliste?).
- **Bearbeiten im Bild** (später, V5): Weg ziehen von Knoten zu Knoten = neuer Weg (Blatt fragt
  nach Auslöser und Rückkehr); erst, wenn die Karte „Weiter“ (4.2) steht.

### 4.4 Prüfung

`schleifen` (Ausweg-Prüfung) bleibt, dazu zwei Hinweise: „*Dehnung* ist bei Bedarf, aber
niemand ruft sie“ und „*Planke* ist im Ablauf und wird außerdem als Einschub gerufen — gewollt?“
(gewollt ist möglich: eine Übung im Ablauf **und** als Einschub).

## 5. Bens Beispiel, Schritt für Schritt

Plan „Rumpf“: Wandsitz (Ablauf) · Kniebeuge (Ablauf) · Planke (Ablauf) · **Dehnung Beine (bei
Bedarf)** · **Atmung (bei Bedarf)**.

- Wandsitz: Muster „Einschub bei Bedarf“ → Weg *Dehnung Beine*, Auslöser Skala ≥ 7, anbieten
  (nicht ausführen), danach weiter. Im Workout: nach dem Wandsitz Chips 0–10; bei 7 wird
  „Einschub: Dehnung Beine — danach weiter mit Kniebeuge“ betont. Tipp → Dehnung läuft → danach
  Kniebeuge. Unter 7 → „Weiter: Kniebeuge“.
- Planke: Muster „Noch einmal, bis …“: Skala ≥ 6 → nächste; sonst „Noch einmal“; Einschub
  *Atmung* von Hand („zu viel Druck“), danach noch einmal.
- Dehnung Beine und Atmung kommen nie von selbst dran; das Start-Bild listet sie unter „Bei
  Bedarf“ mit ihren Auslösern.

## 6. Stufen

| Stufe | Inhalt | Aufwand | Braucht |
|---|---|---|---|
| **V1 Kern** | `Verweis` (einschub, zurueck), `bedarf`, Rückkehr-Stapel, Ablauf ohne Bedarfsübungen, `plan/einschub`, Paketfelder (`bedarf`, `einschub`, `zurueck`, `ausloeser`), Prüfung erweitert | mittel | **P108, P110** |
| **V2 Workout** | Fokus: Einschub-Knöpfe mit „danach …“, Skala-Chips bei Skala-Auslösern, betonter/auto Weg, Schrittliste in zwei Blöcke, Start-Bild „Bei Bedarf“ | mittel | **P109** |
| **V3 Editor** | Plan-Editor mit Block „Bei Bedarf“ und Chip, Karte „Weiter“ mit Mustern und Sätzen, Uhrenplan-Rückblick „wer ruft mich“, Hinweise aus 4.4 | groß | **P111** |
| **V4 Ablaufbild** | `InteractiveViewer` + `Canvas` + Knoten mit Übungsbild und Label, Wege als Linien mit Auslöser-Etikett, Vernebeln/„nur diesen Weg“, Start-Bild und Live-Markierung (4.5) | groß | **P112** |
| **V5 Bearbeiten im Bild** | Weg ziehen = neuer Weg, Blatt für Auslöser und Rückkehr | mittel | nach V3/V4 |

Skizzen (Handy-Bilder) für V2 und V3 vor dem Bau — die Karte mit Sätzen und das Start-Bild mit
zwei Blöcken sind Bedienung, die man sehen muss.

## 7. Entscheidungen (Katalog)

- **P108** Zweige A–D aus der Oberfläche nehmen (Daten bleiben), ersetzt durch Ablauf /
  Bedarfsübung / Einschub / Abzweig?
- **P109** Skala-Auslöser: nur **anbieten** (Knopf betont) oder wahlweise **ausführen** (von
  selbst, wie hart)? Vorschlag: beides, Vorgabe anbieten; ausführen nie bei laufendem Timer im
  weichen Übergang.
- **P110** Rückkehr-Vorgabe nach einem Einschub: **weiter mit der nächsten** (Vorschlag) oder
  die unterbrochene noch einmal?
- **P111** Karte „Weiter“ als Sätze mit Mustern statt der Felder (Zweig/erfüllt/nicht erfüllt/
  Wege)? Oder Felder behalten und nur den Block „Bei Bedarf“ ergänzen?
- **P112** Ablaufbild: auch klein im Fokus („wo bin ich“)? Tipp auf einen Knoten im Workout =
  dorthin wechseln (wie die Kachel heute) oder nur Anzeige?
