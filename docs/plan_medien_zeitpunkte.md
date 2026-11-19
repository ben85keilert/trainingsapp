# Planung: Medien zu beliebigen Zeitpunkten, Text und Medien zuordnen, Videos kürzen (18.11.2026)

Ben, 18.11.2026 („Korrekturen für trainingsapp Übungen/Pläne Materialien“):

1. „Begleitvideos werden noch nicht automatisch im Fokusmodus abgespielt. Man muss diese manuell
   starten und dann ist man außerhalb der Uhr.“
2. „Es braucht eine Möglichkeit, im Plan am Anfang des Planes, am Ende oder so Medien bereit zu
   stellen. Bisher geht das vor allem für bestimmte Wege. Die Medien müssen auf beliebige Punkte
   gesetzt werden können. Überprüfe, wo die Medien bereits positioniert werden können, wo sie
   fehlen, und wie man das intuitiv ergänzen kann, zum Plan an Anfang/Ende/zu bestimmten
   Ereignissen usw. Vielleicht eine Bedingung schärfer ausformulieren (wenn Wahl für hier und
   da/Wdh oder Zeit soundso → Video).“
3. „Wenn man die Materialien im Fokusmodus öffnet, kommt das Blatt und die Videos werden unten
   eingeblendet. Die Beschreibungen für Plan und die anderen Medien müssen zugewiesen werden
   können und danach geordnet. Gerne auch Mehrfachzuweisung.“
4. „Wenn es ein Begleitvideo gibt, sollte dieses automatisch abgespielt sein, nicht in voller
   Bildbreite, aber groß genug, dass man es sehen kann. Mit Steuerungsbuttons. Überlegen, ob
   daneben die Animation Sinn macht, eigentlich entweder oder?“
5. „Das Menü, um Takt-Bewegung-HF-Kurve ein- und auszublenden, nicht schließen nach dem ersten
   Klick.“
6. „Video kann bereits hochgeladen und gekürzt werden. Crop wäre gut, also Anfang oder Ende
   wegschneiden.“
7. „Videos, die abgespielt werden können, werden als großes Bild angezeigt, die
   Videosteuerelemente kommen aber erst, wenn man auf das Bild draufklickt. Behalte die
   Videosteuerelemente an, solange kein Play ist.“

**Gebaut am 18.11.2026: 1, 4, 5, 7** — `docs/plan_medienrollen.md` M5 (Stand dort), Gerätetest
**T151**. Dieses Dokument plant **2, 3 und 6**; Fragen im Katalog als **P226**.

**Gebaut am 19.11.2026: 2, 3 und 6** (Ben: „Zu 6: Crop auch im Medieneditor (zum Komprimieren)
ermöglichen. Bau deine Vorschläge ein“ — die Empfehlungen aus §7 gelten als Antworten). Was
gebaut ist und wo es vom Vorschlag abweicht, steht in **§8**; Gerätetest **T152**.

Gesucht im Katalog (Entscheidungszeilen): schneid, trimm, zuschnitt, zuordn + medi, „am Ende
des“, „zum Ende“, „nach dem Workout“, Abschnitt + Video. Kein Treffer zu Kürzen, Zuordnen oder
Medien am Ende; verwandt und gelesen: **P200** (Rollen statt „Vorher · Dabei · Nachher“), **P203**
(„gesehen“ am Ende eines Videos), **P209** (Rollen, Video im Fokus), **P225** (Reiter „Medien“,
Verkleinern). Gelesen: `core/material.py`, `ui/components/material.py`, `core/bedingung.py`
(`Inhalt`), `core/ablauf.py` (`Kante`), `docs/plan_medien_reiter.md` §1 und §4,
`docs/plan_medienrollen.md` §2.1, §4, §5.

## 1. Befund: Wo Medien heute stehen können

| Ort | Wann es aufgeht | Was es tragen kann | Fundstelle |
|---|---|---|---|
| **Plan** | vor dem **ersten** Start (erstes ▶ einer Übung, „Workout starten“), bis abgehakt; sonst Buch-Symbol am Kopf und im Start-Bild | Beschreibung in Abschnitten, beliebig viele Stücke, **nur Erklärung** | `Plan.media`, `components/material.plan_neu_zeigen` |
| **Übung / Planübung** | Erklärung: vor dem ersten ▶ (wenn „von selbst“), bis abgehakt, sonst Knopf „Medien“; Begleitung: läuft mit (seit heute im Fokus) | Abschnitte (nur der Planübung), Stücke mit Rolle, „ersetzt“ | `PlanItem.media`, `Exercise.media`, `material.neu_zeigen` |
| **Weg im Ablauf** (nur Workout) | wenn der Weg gegangen wird — Auslöser frei · Zeit ab · Wdh. · Wdh. in einer Zeit · Skala · Antwort einer Frage | **ein** Text und **ein** Link — keine Paketdatei, keine Rolle | `Kante.inhalt` → `core/bedingung.Inhalt` |
| **Kurs** | im Kapitel | Blöcke Text und Medium | `core/kursbloecke.py` (laut `plan_medien_reiter.md` §1) |

**Was fehlt:**

- **Am Ende** — nach der letzten Übung bzw. nach „Workout beenden“ (Dehnen zum Ausklang, eine
  Hausaufgabe). Es gibt keinen Zeitpunkt „nachher“, weder am Plan noch an der Planübung.
- **Jedes Mal am Anfang** — der Plan zeigt nur beim ersten Mal von selbst (bis abgehakt); eine
  Einstimmung, die bei jedem Start kommt, geht nicht.
- **Zwischen zwei Übungen einer Liste** — eine Liste hat keine Wege (P170); ein Medium zwischen
  zwei Übungen gibt es nur im Workout über einen Weg.
- **Während einer Übung zu einem Ereignis** — wenn ein Timer-Abschnitt beginnt (etwa die Pause:
  „so geht die nächste Übung“), bei Satz n, nach n Wiederholungen, nach t Sekunden.
- **Ein Medium aus einer Bedingung, ohne den Weg zu ändern** — „wenn die Antwort ‚Knie zwickt‘
  ist → Video“: heute nur, wenn man dafür einen eigenen Weg baut.
- **Am Weg nur ein Link** — keine Datei aus dem Paket, keine zwei Stücke, keine Rolle.

## 2. Vorschlag: ein Zeitpunkt am Medium statt neuer Orte (Punkt 2)

Statt weiterer Orte bekommt **jedes Stück einen Zeitpunkt** — dieselben drei Wörter überall,
dazu „Bei …“ für Ereignisse:

| Zeitpunkt | am Plan | an der Planübung | heute entspricht |
|---|---|---|---|
| **Vorher** | vor dem Start des Plans | vor dem ▶ der Übung | Erklärung mit „von selbst“ |
| **Dabei** | — (es läuft keine Übung) | läuft mit der Uhr | Begleitung |
| **Nachher** | nach der letzten Übung / „Workout beenden“ | nach „Fertig“ der Übung | — **neu** |
| **Bei …** | bei einer Antwort einer Frage des Ablaufs | wenn ein Timer-Abschnitt beginnt · bei Satz n · ab n Wdh. · ab t Sekunden | Inhalt am Weg (nur Workout) |

Und **wie oft**: *jedes Mal* · *bis abgehakt* (heute „von selbst zeigen“) · *nur auf Tipp*
(heute eine Erklärung ohne „von selbst“).

- **Bedingungen schärfer** (Bens Satz): „Bei …“ nimmt **dieselben Auslöser wie ein Weg**
  (`core/ablauf.AUSLOESER`: Zeit ab, Wdh., Wdh. in einer Zeit, Skala, Antwort) und den
  Timer-Abschnitt — gerechnet aus Einträgen, Wahl und Uhr, **nie aus Messwerten**
  (`docs/recht/00_zweckbestimmung.md`). Ein Medium aus einer Bedingung ändert den Weg nicht; es
  geht nur auf. Damit braucht es keinen Weg mehr, nur um ein Video zu zeigen.
- **Daten:** zwei Felder am Medium neben `rolle`, `zeigen`, `ersetzt` — `wann` (``vorher`` ·
  ``dabei`` · ``nachher`` · ``bei``) und `ausloeser` (wie an einer Kante). `rolle` bleibt für
  Bewegung und Symbol; Erklärung/Begleitung lesen sich als vorher/dabei, damit Pakete von heute
  gelten. Am Weg wird aus `Inhalt` (ein Link) eine Liste von Stücken. Ältere Apps übergehen
  unbekannte Felder (`models.medien_zusatz`) — **keine neue Formatversion**.
- **Eintragen, intuitiv:** im Reiter „Medien“ des Plans eine **Zeitleiste** statt der Gruppen nach
  Herkunft beim Eintragen — „Vor dem Start · 1 Kniebeuge (vorher · dabei · nachher · bei …) ·
  2 Planke … · Am Ende“, je Punkt „+ Medium“. Je Stück zwei Felder: **Wann** (Segment) und **Wie
  oft**. Die Übersicht nach Herkunft bleibt als zweite Sicht.
- **Zeigen:** „Nachher“ öffnet das Blatt nach „Fertig“ bzw. auf dem Abschlussbild des Workouts;
  „Bei …“ öffnet beim Üben ein **kleines Banner unter der Uhr** („Video zur Pause — ansehen“), kein
  Blatt über dem Fokus — die Uhr läuft weiter, ein Tipp öffnet. Eine Begleitung („dabei“) kann zu
  einem Ereignis **wechseln** (Abschnitt „Pause“ → anderes Video in derselben Fläche).

## 3. Text und Medien einander zuordnen (Punkt 3)

Heute steht im Blatt beim Üben **erst aller Text** (Abschnitte der Planübung), **dann alle
Stücke** (Erklärung, Begleitung, Ersetztes) — `ui/components/material.material_blatt`; das Blatt
des Plans ebenso (`plan_blatt`).

**Vorschlag:** Ein Stück nennt die **Abschnitte**, zu denen es gehört — ein Feld `abschnitte`
mit den Namen der ``## Name``-Zeilen, **mehrere erlaubt**. Im Blatt dann je Abschnitt:
Überschrift · Text · **darunter seine Stücke**; ein Stück mit zwei Abschnitten steht unter beiden;
Stücke ohne Abschnitt folgen unter „Weitere Medien“. Eintragen im Blatt eines Stücks
(`components/material_rolle.py`): die Abschnitte als Chips zum Ankreuzen.

- Nach Namen, nicht nach einer Kennung: in der TOML lesbar (`abschnitte = ["Ausführung"]`); das
  Werkzeug `pruefen` meldet einen Namen, den es nicht gibt. Wer einen Abschnitt umbenennt, muss
  die Zuordnung nachziehen — der Editor kann das beim Umbenennen anbieten.
- Ältere Apps übergehen das Feld (wie `wann`).
- **Offen (Frage e):** Bens „Beschreibungen für Plan und die anderen Medien“ — gehören die
  Abschnitte der **Übungsbeschreibung** (Ausführung, Hinweise) auch ins Blatt beim Üben? Heute
  stehen dort nur die der Planübung; die der Übung bleiben im „i“.

## 4. Videos kürzen — Anfang und Ende (Punkt 6)

Heute: „Verkleinern“ macht eine **Kopie** nach Schema, das Original bleibt gerätelokal vermerkt
(`core/verkleinern.py`, `views/verkleinern.py`; am Rechner ffmpeg, am Handy der Umwandler der
Fotoauswahl). Kürzen gehört in dasselbe Blatt — es ist dieselbe Kopie mit zwei Zahlen mehr:

- **Im Blatt zwei Marken „Anfang“ und „Ende“** — im Videospieler an die Stelle spulen und „Anfang
  hier“ / „Ende hier“ tippen (die Position fragt der Spieler auf Tipp ab, nie je Bild), dazu
  Feinstellen in Sekunden. Die Schätzung der Größe rechnet mit der gekürzten Dauer (die Bitraten
  liegen fest, `Ziel.bytes`).
- **Am Rechner:** ffmpeg mit `-ss`/`-to` — es wird ohnehin neu kodiert, also bildgenau.
- **Am Handy:** Der Umwandler kann es schon — **nachgesehen**: `com.otaliastudios:transcoder:0.10.5`
  (`erweiterungen/flet_hochladen/.../android/build.gradle:67`) enthält `TrimDataSource` und
  `ClipDataSource` (Klassenliste der AAR im Gradle-Cache). Braucht eine Änderung im Kotlin-Teil
  und eine APK; ob der Schnitt bildgenau oder am Schlüsselbild liegt, ist **ungeprüft**.
- Nur Kürzen oder auch gleich verkleinern: beides in einem Lauf, Vorgabe „Größe wie bisher“.
- **„Crop“** heißt bei Videos meist der **Bildausschnitt**; Ben meint Anfang/Ende. Den Ausschnitt
  (etwa ein Hochkantvideo auf das Wesentliche) erst auf Wunsch.

## 5. Rest von M5 (Begleitung im Fokus)

Gebaut ist die Fläche mit Knöpfen; nach dem Gerätetest T151, in der Reihenfolge der Skizzen
V2–V6 (`plan_medienrollen.md` §2.1): die Uhr kleiner, solange ein Video läuft (V2, Ben
16.11.2026); Vollbild mit Uhr-Ecke (V3–V5 — heute das Vollbild von media_kit ohne Uhr); Hoch- und
Querformat (Maße beim Ablegen aus dem Kopf der Datei); Ton als Zeile (V6).

## 6. Stufen (nach Bens Ja)

| Stufe | Inhalt | Braucht |
|---|---|---|
| Z1 | Zuordnung Text ↔ Medium (§3): Feld, Blatt nach Abschnitten, Chips im Editor, `pruefen` | e |
| Z2 | Zeitpunkt „Nachher“ und „Wie oft“ an Plan und Planübung (§2), Zeitleiste im Reiter „Medien“ | a, c |
| Z3 | „Bei …“: Timer-Abschnitt und Antwort zuerst, Banner unter der Uhr; Weg mit Liste von Stücken | b, d |
| Z4 | Kürzen am Rechner (ffmpeg) und im Blatt; dann Android (Kotlin, APK) | f |
| Z5 | Rest von M5 (§5) | T151, g |

## 7. Fragen an Ben (Katalog P226) — meine Empfehlung zuerst

- **a)** Ein **Zeitpunkt je Stück** — Vorher · Dabei · Nachher · Bei … — statt neuer Orte, und
  **„Am Ende“** des Plans neu? *Ja.*
- **b)** „Bei …“: welche Ereignisse zuerst? *Timer-Abschnitt beginnt und Antwort einer Frage*; dann
  Satz n, ab n Wdh., ab t Sekunden.
- **c)** **Wie oft:** jedes Mal · bis abgehakt · nur auf Tipp? *Ja*, Vorgabe „nur auf Tipp“ wie heute.
- **d)** Am Weg **mehrere Stücke** (auch Paketdateien) statt eines Links? *Ja.*
- **e)** Zuordnung nach **Abschnittsnamen, mehrfach**; und kommen im Blatt beim Üben auch die
  Abschnitte der **Übungsbeschreibung** dazu? *Ja zur Zuordnung; die Übungsbeschreibung nur, wenn
  ein Stück ihr zugeordnet ist.*
- **f)** **Kürzen im Blatt „Verkleinern“** (eine Kopie, Original bleibt) — oder ein eigener Knopf
  „Kürzen“? Bildausschnitt auch? *Im selben Blatt; Ausschnitt später.*
- **g)** Die **Uhr kleiner** neben dem Video (V2) gleich bauen oder erst nach T151? *Nach T151* —
  ob 320 × 180 am Handy reicht, zeigt erst das Gerät.

## 8. Gebaut am 19.11.2026 — und wo es vom Vorschlag abweicht

| Stufe | Gebaut | Fundstelle |
|---|---|---|
| Z1 | Feld `abschnitte` am Medium (mehrere); das Blatt beim Üben und das des Plans stellen je Abschnitt den Text und darunter seine Stücke; ein Abschnitt der **Übungsbeschreibung** kommt ins Blatt, wenn ein Stück zu ihm gehört (Frage e); im Editor „Zu Abschnitt …“ mit Chips, die Namen frisch aus der Beschreibung; `pruefen` gibt Hinweise | `core/material.py` (`nach_abschnitten`, `material_von`), `components/material.py`, `components/material_rolle.py`, `paket_werkzeug.zeitpunkte_pruefen` |
| Z2 | `wann = "nachher"`: nach dem Ende einer Übung (auch wenn die Uhr von selbst abläuft), eines Workout-Schritts, der letzten Übung einer Liste und des Workouts — Blatt „Nach der Übung“ bzw. „Zum Abschluss“; nicht nach einem Abbruch. `oft = "immer"`: kommt bei jedem Start wieder (am ▶ wie bisher: erst das Blatt, der nächste Tipp startet) | `ui/einheit._medien_nachher`, `views/workout.material_zeigen`, `material._neue` |
| Z3 | `wann = "bei"` mit `bei` (`core.models.Ereignis`): Timer-Abschnitt beginnt · Satz n · Zeit · Wiederholungen — ein **Hinweis unter der Uhr** im Fokus, die Uhr läuft weiter, „Ansehen“ öffnet das Blatt; am Plan die **Antwort** einer Frage im Workout — das Blatt geht auf, der Weg bleibt. Am Weg **weitere Links** mit Titel (`Inhalt.medien`) | `Material.faellig`, `core.material.Lage`, `Fokus._ereignisse_nachziehen`, `material.plan_antwort_zeigen`, `core/bedingung.py`, `components/wege_form.py` |
| Z4 | Kürzen im Blatt „Verkleinern“: das Original im Spieler, „Anfang hier“ / „Ende hier“ oder die Zeit von Hand; ffmpeg mit `-ss`/`-t`; Android über `ClipDataSource` (`von_ms`/`bis_ms` an `flet_hochladen`) | `core/verkleinern.py` (`Ziel.von_s/bis_s`, `schnitt`), `views/verkleinern.py`, `erweiterungen/flet_hochladen` |

Daten: Übung in `exercise_media.zusatz_json` (Migration 071), Planübung und Plan in ihrem JSON,
im Paket dieselben Felder (`docs/uebungspakete.md`) — keine neue Formatversion.

**Abweichungen vom Vorschlag:**

- **Editor:** Die Rolle (Erklärung · Begleitung · Bewegung) bleibt, wie sie ist; darunter steht für
  eine Erklärung **Wann** (Vorher · Nachher · Bei …) und statt dreier Stufen „Wie oft“ zwei
  Schalter („Beim ersten Mal von selbst zeigen“, „Jedes Mal, nicht nur beim ersten“). Am Plan
  heißen die Zeitpunkte „Vor dem Start · Am Ende · Bei …“.
- **Keine Zeitleiste** im Reiter „Medien“: Die Übersicht nennt je Stück den Zeitpunkt („nachher“,
  „wenn ‚Pause‘ beginnt“, „jedes Mal“, „zu: Ausführung“); eingetragen wird weiter an den zwei
  Orten und am Plan. Die Zeitleiste als eigene Sicht ist offen.
- **Am Weg nur Links**, keine Paketdateien (die müssten mit dem Plan reisen und von der Ablage
  gehalten werden — eigener Schritt). Dateien an beliebigen Punkten gehen über Planübung und Plan.
- **Eine Begleitung wechselt nicht** zu einem Ereignis; „Bei …“ gibt es nur für Erklärungen.
- **„Bei …“ kommt immer von selbst** — bis es abgehakt ist oder jedes Mal; „nur auf Tipp“ gibt
  es dort nicht.
- **Ende einer Liste:** „Am Ende“ des Plans kommt, wenn die **letzte Planübung** über die Uhr
  endet; wer die Liste nur abhakt, findet es hinter dem Buch-Symbol.
- **Ende des Workouts:** Es kommt das Blatt des Plans; das „Nachher“ der letzten Übung steht im
  Blatt der Übung, kommt dort aber nicht mehr von selbst.
- **Kürzen am Handy ist ungeprüft** (braucht die APK aus diesem Stand): ob der Schnitt bildgenau
  sitzt oder am Schlüsselbild davor, zeigt T152.
- **Rest von M5** (§5) wartet wie empfohlen auf T151.

Tests: `tests/test_ui_medien_zeitpunkte.py`, `tests/test_ui_weg_stuecke.py`,
`tests/test_ui_fokus.py` (Hinweis unter der Uhr), `tests/test_ui_verkleinern.py` (Kürzen mit
ffmpeg), `tests/test_medien_uebersicht.py`, Doctests in `core/models.py`, `core/material.py`,
`core/bedingung.py`, `core/verkleinern.py`. Am Bildschirm geprüft (Web-Foto, 412 px): die Zeilen
unter einem Stück in „Übung bearbeiten“.
