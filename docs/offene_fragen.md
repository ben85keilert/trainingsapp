# Offene Fragen

Katalog der Entscheidungen, die Ben noch treffen muss, und der Befunde, die
noch nicht behoben sind. Angelegt am 15.10.2026 nach der Durchsicht der
Änderungen vom 14./15.10. Was entschieden ist, wandert mit Datum in den
Abschnitt „Entschieden“ am Ende (oder in die zuständige Doku) — der Katalog
hält nur Offenes.

Regel: Neues Offenes kommt **hier** hinein, nicht verstreut in Plan-Dateien.
Je Eintrag: Woher, Frage, Stand/Vorschlag.

Schwere der Befunde: **hoch** = Datenverlust, Absturz im Normalgebrauch,
Datenschutz · **mittel** = falscher Wert, Leak, spürbare Last · **niedrig** =
Schönheit, Wartung.

---

## 1. Produktentscheidungen (Ben)

| # | Woher | Frage | Stand / Vorschlag |
|---|---|---|---|
| P1 | Plan, 14.10. | **Planblock: welche der drei Darstellungen** (untereinander = Vorgabe, umschalten, aufklappen) bleibt? Die anderen beiden sind dann zu entfernen (`ui.state.PLAN_DARSTELLUNGEN`). | Wahl steht aus. |
| P2 | Paket „Standard“, 15.10. | **Auswahl der 33 Übungen** in `data/seed/standard.toml` durchsehen (16 alte, 17 neue, neuer Typ „Mobilisation“, Katze-Kuh dorthin). | Erster Entwurf, ungeprüft. |
| P3 | Pakete | Weitere mitgelieferte Pakete (Dehnung, Kräftigung …): je Paket eine TOML neben `standard.toml` — welche zuerst, wer pflegt sie? | Offen. |
| P4 | „Heute“, `plan_hrv_timer.md` | „Heute“ fasst Pläne doppelt zusammen (Bilanz oben, Plan darunter). Welche Stellen wirken noch gedrängt? | Am besten mit Bildschirmfotos klären. |
| P6 | GPS-Plan, Abschnitt 8 | DFA-α1-Wertebereiche für die Übersicht (neutral) — die vorgeschlagenen übernehmen? | Offen. |
| P7 | GPS-Plan | Eigene Kachelquelle (Protomaps-Ausschnitt) erst mit Phase 5 — bis dahin Online-Kacheln? (Siehe Befund G-Kacheln unten.) | Offen. |
| P8 | GPS-Plan | Play Store: Vordergrunddienst als `health` statt `location` deklarieren? | Später. |
| P9 | Verity Sense beim Training | HF-Modus ohne PPI fürs Training (PPI stoppen, danach wieder starten) braucht einen Test am Gerät. | Offen, Test durch Ben. |
| P10 | Korrektur, `korrektur.md` „Offen“ | Eichung gegen das EKG in Bewegung; dürfen verworfene Intervalle in Ruhe zählen; Fehlerschwelle 30 ms (Polar) oder 50 ms? | Braucht Messungen. |
| P11 | Recht, `00_zweckbestimmung.md` | Weg A/B/C für Edition B (Dokumentationswerkzeug / Klasse I / IIa) — vor dem Bau von Edition B. | Empfehlung Weg A. |
| P12 | Recht, `30_avv.md` | Hoster der Praxisdatenbank (EU?) und AVV. (Rahmen entschieden 15.10.: Solo speichert nichts auf dem Server, nur Video-Streaming — siehe „Entschieden“.) | Offen. |
| P13 | Praxis-Edition | PIN-Sperre beim Profilwechsel (`ist_aktiv("profil_sperre")`) ist bisher nur ein Hinweistext — Umsetzung mit oder ohne Fingerabdruck? | Erst mit Edition B. |
| P14 | M10 | Video-Download (hängt am Hosting), Fotos für eigene Übungen. Rahmen entschieden 15.10. (lokal **und** Fremdquelle); Umsetzung hängt an K-F6 (Abschnitt 4). | Offen. |
| P15 | Live-Wischen, 15.10. | Nach dem Fix (ganzer Fingerweg zählt, siehe Befund H-Wischen) ist 1 Fingerbreite = 1 Fensterbreite. Reicht das, oder zusätzlich Schwung (Fling über `primary_velocity`) bzw. ein Faktor > 1? | Erst am Handy probieren. |
| P16 | Kurse, `plan_kurse.md` § 2 | **Pläne im Kurs:** gebaut sind mehrere Pläne je Kapitel, Wochentage am Plan. Bens Alternative: Wochentage je Planübung (ein Plan mit „Atmung Mo/Mi/Fr, Kräftigung Di/Do“) — allgemein einbauen? | Vorschlag: so lassen; Planübung ohne Wochentag. |
| P17 | Kurse, § 4 | **Rückfrage beim Überspringen:** einmal (gebaut) oder zweimal? Modus `streng` nur für zugewiesene Kurse (Edition B)? | Einmal. |
| P18 | Kurse, § 3 | **Zählung der Bedingung:** ab Kapitelstart (gebaut — „100 Liegestützen seit du das Kapitel geöffnet hast“) oder gesamt über die ganze Zeit? | Ab Kapitelstart. |
| P19 | Kurse, § 5 | **Ort in der Oberfläche:** dritter Unterreiter unter „Übungen“ (gebaut) oder eigener Hauptreiter? Kurszeile auf „Heute“ („Kurs HRV, Kapitel 3 von 7“)? | Unterreiter; Heute-Zeile später. |
| P20 | Kurse, § 5 | **Ton in Kapiteln:** Medien sind Links; für Ton fehlt ein Spieler (flet-audio wegen Audiofokus abgelehnt, `flet_ton` nur kurze WAV). Welcher Weg — eigene Erweiterung, Systemplayer per Link, gar nicht? | Mit K-F6 entscheiden. |
| P21 | Kurse, `standard.toml` | **Inhalte des ersten Kurses** „HRV-Messung verstehen“ (7 Kapitel) sind ein erster Entwurf — durchsehen, kürzen, Bilder/Videos ergänzen? Kapitel-`key`s dabei nicht ändern (Fortschritt hängt daran). | Durchsicht durch Ben. |
| P22 | Vollbild, 16.10. | **Vorgabe der rechten Achse:** gebaut ist RMSSD (links das Tachogramm). Lieber leer, oder die erste Kurve der Analyse unter der Hauptkurve? Die Wahl bleibt je Ansicht gespeichert. | RMSSD lassen. |
| P23 | Vollbild, 16.10. | **Ablesen live hält die Kurve an** (wie eine Pause, „−0:12 · Live“ in der Kopfzeile); „Live“ läuft wieder mit und beendet das Ablesen. So lassen, oder soll der Strich mitlaufen? | So lassen. |
| P24 | Vollbild, 16.10. | **Etikett auch hochkant?** Der Tipp auf eine Notizmarke oder einen Abschnittsbalken zeigt sein Etikett bisher nur quer; hochkant steht die Liste direkt unter der Kurve. Ebenso: die rechte Achse hochkant (dort wohl zu schmal). | Hochkant ohne. |
| P27 | iOS, 16.10. | **Laufendes auf dem iPhone anzeigen:** iOS kennt keine dauerhafte Benachrichtigung. Das Gegenstück ist eine Live-Aktivität (Sperrbildschirm, Dynamic Island; ActivityKit ab iOS 16.1) — sie braucht eine Widget-Erweiterung in Swift, also ein eigenes Plugin wie `flet_ble`. GPS im Hintergrund zeigt iOS selbst an (Standortpfeil bzw. blaue Pille); Bluetooth darf mit `bluetooth-central` im Hintergrund weiterlaufen, ein Timer nicht (nur vorab geplante lokale Benachrichtigungen). Wegwischen beendet eine iOS-App immer — dort bleibt nur das Crash-Backup. | Erst mit einer iOS-Fassung. |
| P25 | Ben, 16.10. | **Spektrum oder Nichtlinear neben der Kurve (quer)?** „Vielleicht relevant“: Frequenz (Spektrum) bzw. Nichtlinear (Poincaré) zusammen mit der Kurve im Querformat. Nur vermerkt — **nicht bauen**, bis Ben es sagt. | Falls ja: als weitere Seitenleiste neben der Kurve, Analysefenster wie hochkant (Alles, Abschnitt, Band). |
| P28 | Einheit, 17.10. | **Begriff „Einheit“:** Die Klammer um HRV, Timer, GPS und Plan heißt in Startleiste, Rückfrage („Einheit beenden?“) und Benachrichtigung „Einheit“. Passt das Wort — oder lieber „Training“, „Ablauf“, „Session“? Im Code steht „Einheit“ auch für Maßeinheiten (`ResultSpec`); dort ist es `Einheitslauf`. | Vorschlag: „Einheit“ lassen (Trainingseinheit). |
| P29 | Einheit, 17.10. | **„Start“ mit gefüllter Startleiste:** Im Timer startet „Start“ den Timer allein und nimmt ihn aus der Startleiste; „Training starten“, der Timer einer Übung und „Ablauf starten“ starten alles aus der Startleiste mit (ein Hinweis unter dem Knopf sagt es). Gleich machen — und wenn, in welche Richtung? | Vorschlag: so lassen — der Timer allein ist oft ein Werkzeug nebenher, die anderen wollen die HRV ohnehin mit. |
| P30 | Ben über hrv-research, 17.10. | **Diagnosemodus** (Plan `docs/plan_diagnose.md` — „wir machen das aber noch nicht“): (a) Schaltet er sich selbst ab — nach der nächsten Messung, nach 24 h, nie? (b) Gehören Rohmitschnitt-Format und Prüfbericht für beide Apps nach hrv-core (gemeinsames Format mit praxis_gui)? (c) Sollen hrv-core (`deid`, `deid_export`) und hrv-research (`scripts/einlesen.py`) `_diagnose` de-identifiziert mitnehmen? (d) Vorabtest vor jeder Messung im Modus oder nur per Knopf? | Vorschlag: (a) nach der nächsten Messung, (b) ja, (c) ja, Adresse pseudonymisiert, (d) per Knopf. H18 vorab beheben, ohne Modus (Plan §1). |
| P31 | Paketversionen, 17.10. | **Name des Feldes für die Textversion:** Im TOML steht die Version als Text (`1.2.0`), in JSON und Index die Zahl für den Vergleich (X·10000+Y·100+Z) und der Text daneben — heißt das Feld `versionsname`? | Vorschlag `versionsname` (`docs/plan_paketversionen.md`, Abschnitt 5). |
| P32 | Paketversionen, 17.10. | **Variante (`variante_von`) als patch?** Sie bestimmt, mit welcher Übung eine Variante die Kachel im Verlauf teilt. | Vorgeschlagen, nicht eigens entschieden. |
| P33 | Paketversionen, 17.10. | **Wo steht der Hinweis nach einem minor-Update?** Heute sagt das Label unter dem Zahnrad „aktualisiert: Standard“ (`AppState.updates_label`) — reicht das, oder dazu die Seite „Updates“ und die Übung selbst? | Offen. |
| P34 | Paketversionen, 17.10. | **Freischaltung eines Kurses ändern:** immer major (Nachfrage) — oder nur, wenn sie strenger wird? | Offen. |
| P35 | Paketversionen, 17.10. | **Kapitel ans Ende eines Kurses, den jemand schon abgeschlossen hat:** Der Kurs ist danach wieder offen. | Vorschlag minor. |

Noch offene Fragen aus der Durchsicht vom 15.10. (Details beim jeweiligen Befund in
Abschnitt 3; die beantworteten stehen unter „Entschieden“):

| # | Bereich | Frage | Vorschlag |
|---|---|---|---|
| K-F6 | Medien (K1) | **Vertagt (Ben, 15.10.):** Rechtefragen, Sicherheit, Injections — gesondert besprechen. Fakten stehen in Abschnitt 4. | Entscheidung folgt. |
| K-F8 | Pakete (K12) | Archivierte Paketübungen nicht exportierbar — gewollt? | — |
| G-F5 | GPS (G8) | Strecken löschen: Papierkorb mit endgültigem Löschen der Koordinatendatei wie bei Messungen? Vorabtest-Dateien aufräumen? | Ja, beides. |
| G-F6 | GPS (G18) | Live-Karte folgt jede Sekunde, Wegwischen unmöglich — bewusst? | „Folgen“ nach Pan aussetzen. |
| G-F7 | GPS (G10) | GPX-Höhe: MSL (`use_msl_altitude=True`) oder Ellipsoid belassen? | MSL (Strava/Komoot erwarten NN). |
| G-F8 | GPS (G18) | `strecke.title` + `titel_setzen` ohne Oberfläche — geplant oder Rest? | — |
| H-F3 | HRV (H5) | praxis_gui-Felder je Segment (`visible`, `active`, `metrics`, `computed_utc`) durchreichen oder normieren? | Durchreichen. |
| H-F5 | HRV (H7) | `hrv_metrics_cache` ungenutzt lassen (Doku anpassen) oder für die Öffnungszeit nutzen? | — |
| H-F6 | HRV (H8) | Rechnen beim Öffnen synchron (Plan: akzeptiert) oder per `asyncio.to_thread`? | Am Handy messen. |
| H-F7 | HRV (H6) | Beschreibung: DB-Kopie als Rückfall oder strikt Datei? | Strikt Datei. |
| H-F8 | HRV-Einstellungen | Die Frequenzanalyse ist seit 14.10. ein Schalter unter Einstellungen → HRV-Messung (`HrvEinstellungen.frequenz`, **Vorgabe aus**; ebenso „Nichtlinear“). Ben fragte am 15.10., ob sie „rausgefallen“ sei. Soll die Vorgabe **an** sein, zumindest für Brustgurt-Messungen? | Vorschlag: an für `rr_ekg`, aus für optisch. |
| N-F3 | Tags (N5) | „dehnung“ = „Dehnung“ überall (UNIQUE `COLLATE NOCASE`) oder nirgends? | Überall. |
| N-F5 | Pläne (N6) | `plan.revision` als Sync-Anker für Items oder eigene Item-Revision? | Erst mit Edition B. |
| N-F6 | Timer (N7) | Timer-Profil bearbeiten, während der Timer läuft: warnen, blockieren, weiterlaufen? | Weiterlaufen, neues Profil beim nächsten Start. |
| N-F8 | Darstellung (N15) | `app_setting darstellung:<profil-id>` nach Profil-Löschen belassen? | Belassen (Profile nur ausgeblendet). |

## 2. Am Gerät zu prüfen (Ben)

- **T13** (Kurse, 15.10.): Übungen → Kurse → „HRV-Messung verstehen“: Kapitel lesen, Markdown-Darstellung, „Weiter“, Kapitel 3 ohne Messung → „Trotzdem freischalten“, Kapitel 6 legt den Plan „Kurs: Ruhig atmen“ auf „Heute“; nach Abschluss ist er deaktiviert. „Von vorn beginnen“ im Menü.

| # | Woher | Was | Stand |
|---|---|---|---|
| T1 | Timer-Signale | Lautstärke-Wahl Medien/Wecker/Klingelton und Klänge — Dart-Teil von `flet_ton` geändert, braucht neuen APK-Build; auf dem Handy ungetestet. iOS: nur ein Regler. | offen |
| T2 | Pakete | Import am Handy (FilePicker) und Paket entfernen auf dem Gerät noch nicht getestet. | offen |
| T3 | GPS-Vorabtest | Gang mit ausgeschaltetem Bildschirm (Verbrauch im Hintergrund), siehe `plan_gps.md` 9a. | offen |
| T4 | Live-Wischen | Wischweg nach dem Fix vom 15.10. am Handy prüfen (vorher kam nur ~⅙ der Bewegung an). | offen |
| T5 | GPS ohne Doppler | Training auf einem Gerät ohne Tempogenauigkeit (oder Netzwerk-Fix): zählt die Strecke per 10-m-Schritt, greift die Auto-Pause? Am Pixel 10 kommt Tempo, dort ändert sich nichts. | offen |
| T6 | GPS-Abbruch | App während eines Trainings beenden → beim nächsten Start Dialog „Unvollständiges Training gefunden“, Übernehmen trägt Strecke und Tagebuch nach. Seit 16.10. läuft das Training beim Wegwischen weiter (T15) — zum Prüfen „Beenden erzwingen“ in den App-Infos nehmen. | offen |
| T7 | Karte im Training | Schalter „Karte zeigen“, einmaliger Hinweis beim ersten Training mit Karte; rote Warnzeile bei GPS-Fehler/fehlendem Vordergrunddienst. | offen |
| T8 | Paket entfernen | Rückfrage mit „Teil von Plan …“ und Kästchen „kopieren“ am Handy durchspielen. | offen |
| T9 | Ausrichtung | Sperre je Ansicht (`ui/ausrichtung.py`): Heute/Pläne bleiben hochkant auch bei Auto-Drehen an; Ausdauer, GPS-Test und Messungs-Auswertung drehen mit; Zurück aus dem Vollbild stellt hochkant wieder her. Tablets ab Android 16 (≥ 600 dp) ignorieren die Sperre — erwartet. | offen |
| T10 | Live-Vollbild | Knopf an der Tachogramm-Karte dreht quer (auch bei Auto-Drehen aus?), Kurve füllt die Fläche nach dem Drehen (gemessen). Seit 16.10.: **zwei Achsen** — ‹ › und Liste je Achse (kein Hoch/runter-Wischen mehr), gleiche Skala kommt dazu, „Seiten tauschen“; Werkzeugleiste rechts: Ablesen (hält an, „Live“ läuft weiter), Notiz ohne Text, Notizen (Seitenleiste mit Tastatur — frisst sie quer zu viel?), Fenster & Darstellung; Tipp auf eine Marke zeigt ihr Etikett (Toleranz 2 % der Fensterbreite — zu eng/zu weit?), Marke mit dem Finger ziehen. | offen |
| T11 | Auswertung quer | Vollbild-Knopf: zwei Achsen wie live; Seitenleiste (330 px, scrollbar) für Editor, Notizen und Abschnitte; Etikett per Tipp auf Marke bzw. Abschnittsbalken (oben in der Kurve — trifft man ihn?); Ablesewerte schweben über der Kurve; Zuschneiden aus der Werkzeugleiste. Systemtaste Zurück verlässt nur das Vollbild (`can_pop`/`on_confirm_pop` — am Handy prüfen, am Rechner nicht testbar). | offen |
| T14 | Updates (16.10.) | Erster Start mit der neuen APK: Hinweis „Updates beim Start prüfen“ (Verstanden/Ausschalten); Label unter dem Zahnrad nach einem Release; Einstellungen → Updates: eigene Quelle eintragen (z. B. `python -m http.server` mit `dist/index.json` aus `trainingsapp-paket index`), „Jetzt prüfen“, Modus manuell → Pfeil → Vorschau; Paket deaktivieren → Katalog leer; „Nicht mehr im Paket“-Dialog. | offen |
| T12 | Ausdauer quer | Laufendes Training gedreht: Zahlen links, Karte rechts in voller Höhe; zurückgedreht wieder untereinander (Umbau über `page.on_resize`, Karte wird neu angelegt — Kacheln laden nach). | offen |
| T15 | Wegwischen (16.10.) | Während einer HRV-Messung (oder eines Trainings) die App in der Übersicht wegwischen: Die Benachrichtigung bleibt, die Messung läuft weiter; ein Tipp auf die Benachrichtigung oder das Startsymbol zeigt sie wieder — ohne Lücke in der Aufnahme. Ohne laufende Messung beendet Wegwischen die App wie bisher. Braucht eine APK aus `scripts/apk_bauen.py` (eigene MainActivity, die die Flutter-Engine hält). Prüfen: Reiter, Timer und Bluetooth danach (neu verbinden, suchen). | offen |
| T16 | Benachrichtigung (16.10.) | Sobald etwas läuft, ein Herz in der Statusleiste neben der Uhr; eingeklappt „HRV 12:34 · Timer 0:12“, ausgeklappt eine Zeile je Tätigkeit mit Zeit, oben eine Stoppuhr; kein Ton beim Erscheinen. Nur der Timer: gewöhnliche Benachrichtigung, verschwindet am Ende. Unter App-Info → Benachrichtigungen steht danach ein neuer Kanal „Laufende Messung“ (der alte, stille ist weg). | offen |
| T17 | Autosave (16.10.) | Zurück (Pfeil und Systemtaste) speichert: Übung bearbeiten, neue Übung (ohne Namen: Rückfrage), Planübung einstellen, Timer-Profil, Eintrag korrigieren, Profilnamen, Korrektur einer Aufzeichnung (nur nach eigener Änderung). Titel-Blatt und Übungsnotiz speichern beim Wegwischen bzw. Danebentippen. „Abbrechen“ verwirft. | offen |
| T18 | Backup-Dialog (16.10.) | Start mit liegengebliebenem Backup: Beim Wiederherstellen dreht ein Ring statt der Knöpfe, die App bleibt bedienbar, danach öffnet sich die Messung; „Löschen“ nimmt die Zeile weg, „Später“ schließt den Dialog. | offen |
| T19 | Messung (16./17.10.) | Vor „Aufnahme starten“: „Titel hinzufügen“ unter dem Knopf → Titel und Beschreibung eintragen; die Aufnahme übernimmt beide, die gespeicherte Messung zeigt sie. Notiz mit Zeitpunkt vor dem Start (auch getippt, ohne ✓): steht danach am Anfang der Aufnahme. Beim Start beginnen Kurven, Kacheln und Analyse leer bei 0:00. Knöpfe der Statuskarte reagieren beim ersten Tipp (vorher gingen Tipps verloren, weil die Karte bis zu 2×/s neu entstand). Reiter „Übungen · Pläne · Kurse“ und „Live · Aufzeichnungen“ gleich breit. | offen |
| T20 | Übungsausführung (17.10.) | Im Plan Notiz schreiben, dann „Gemacht“ oder einen Satz eintragen, dann wieder „Notiz“: Es öffnet dieselbe Notiz zum Weiterschreiben (keine zweite); Freitext als Parameter ebenso. „Heute geleistet“ antippen oder „Bearbeiten“: alle Einträge der Übung von heute mit Werten und Notizen, alles auf einmal ändern, Zurück speichert, Papierkorb löscht einen Eintrag (Rückfrage). | offen |
| T21 | Messansicht aufgeräumt (17.10.) | Vor dem Start: Unter dem Titel steht die erste Zeile der Beschreibung, der Pfeil klappt sie ganz auf und wieder zu (auch während der Aufnahme). Im Kartentitel des Tachogramms öffnet das „i“ links vom Regler die Farberklärung (der graue Text darunter ist weg), ebenso in einer Aufzeichnung; dort auch in den Karten Abschnitte, Korrektur und Verlauf (live: Verlauf) — unter den Tabellen steht nur noch, was die Zahlen einschränkt (gesperrt, optisch nicht belastbar). Das Protokoll-Symbol rechts in der Gerätezeile öffnet die Diagnose (unten gibt es kein Klappfeld mehr), „Protokoll teilen“ geht. Uhr oder Band mit Herzfrequenz-Übertragung (z. B. Garmin „HF übertragen“): Hauptkurve „Herzfrequenz“ in bpm, ohne „korrigiert“ und Regler; die gespeicherte Messung zeigt den Puls über die echte Dauer. Einstellungen → HRV-Messung → Atmung: „?“ erklärt „Atemübung“ (auch unter Einstellungen → App). | offen |
| T22 | Einheit (17.10.) | Timer → „Bereitstellen“: oben die Infoleiste (T39), auf „Heute“ im Reiter „Einheit“ die Startkarte (Teil, Stand, Marke „bereit“, ✕ nimmt heraus, „Leeren“). Countdown 3 – 2 – 1 an → „Alle starten“: „Start in 3 …“ (kein ▶ im Countdown), danach die Laufleiste mit Zeit, Abschnitt, ⏸ ⏹. Die Benachrichtigung zeigt die Einheit. | offen |
| T23 | Einheit mit HRV (17.10.) | Die HRV-Aufnahme läuft schon, Timer bereitstellen, „Alle starten“: In der Messung stehen die Abschnitte des Timers auf eigener Spur (unter 5 s keine Marke), nach dem Timer läuft die HRV weiter. „Wenn der Timer fertig ist: HRV-Messung beenden“ angekreuzt → sie endet und wird gespeichert. ⏹ fragt nach. | offen |
| T24 | Dienst `health` (17.10.) | Timer allein und Timer als Einheit, Display aus oder andere App: Töne kommen weiter, die Benachrichtigung zählt. Braucht eine neue APK (Manifest: `FOREGROUND_SERVICE_HEALTH`, `HIGH_SAMPLING_RATE_SENSORS`). Lehnt Android 14 den Dienst ab, steht im Protokoll „Vordergrunddienst nicht gestartet“. | offen |
| T25 | Ausdauer als Einheit (17.10.) | Ausdauer → „Bereitstellen“: Das GPS sucht in der Startleiste Empfang (Genauigkeit), ein verbundener Gurt kommt mit; oben das Timer-Symbol → Intervall bereitstellen → „Alle starten“. Ton je km; Runden und Kilometer in der Messung auf eigenen Spuren; „Beenden“ → Auswertung mit HF und DFA α1 je km. Lief die HRV schon: Sie läuft weiter, die Auswertung sagt „läuft noch“, nach dem Speichern stehen die Werte da. Laufband (ohne GPS) ebenso. | offen |
| T26 | Absturz im Training (17.10.) | Während eines Trainings mit HRV die App hart beenden (Einstellungen → Apps → Beenden erzwingen): Beim nächsten Start Backup und Strecke übernehmen — die Auswertung der Strecke zeigt die HRV (H16). | offen |
| T27 | Timer an der Übung (17.10.) | Plan üben: Uhr neben dem i (ausgefüllt mit Timer, sonst umrandet, Untertitel „Timer: …“) → „Timer · Planke“: Profil-Chips, je Abschnitt „zählt / zählt nicht“ (farbige Leiste, Summen), „Zeit eintragen“, Haltezeit je Satz oder Zeit gesamt → Starten: Restzeit, „Satz 1 von 3“, Weiter, Fertig, Abbrechen → „Planke gemacht“ mit dem Eingetragenen; im Plan unter „Heute geleistet“. Ebenso aus der Übung im Katalog (Symbol oben). | offen |
| T28 | Abbrechen und Läufe heute (17.10.) | Im Timer einer Übung „Abbrechen“: nichts eingetragen, unter „Läufe heute“ steht der Lauf mit „Eintragen“ — ein Tipp trägt die gelaufene Zeit nach. Eine laufende HRV bekommt „Planke beginnt“ / „Planke fertig“ und die Abschnitte (unter 5 s keine Marke). | offen |
| T29 | Timer-Editor (17.10.) | „+ Profil“ → „Neues Profil“ oder eines aus der Bibliothek; Bearbeiten (Stift): „Teil anhängen“ (Cooldown, zählt nicht), je Teil Runden, je Abschnitt „zählt“. Im Plan gespeichert ändert es nur die Planübung (eigene Kopie), im Katalog die Übung. | offen |
| T30 | Plan-Ablauf (17.10.) | Plan üben → Timer oben → „Ablauf öffnen“: Liste mit Timer je Übung, HRV mit dabei (wenn verbunden) und „Wenn der Ablauf fertig ist“ → „Ablauf starten“: laufende Übung mit Restzeit, „Fertig“ / „Überspringen“, ohne Timer „Gemacht“; danach „Pause — Weiter mit …“; am Ende „<Plan> fertig“ mit den Einträgen. Töne bei jeder Übung; Laufleiste „Übung 2 von 5“. | offen |
| T31 | Plan bearbeiten (17.10.) | Karte „Ablauf“: „Timer für alle Übungen“ (aus der Bibliothek), „Nach dem Timer einer Übung: Auf Tipp warten \| Automatisch weiter“; die Uhr neben dem i auch beim Bearbeiten (Timer der Planübung wählen). | offen |
| T32 | Intervalle im Training (17.10.) | Ausdauer → Timer oben (Intervall 30/15) → „Bereitstellen“ → „Training starten“: unter den Zahlen „Intervalle (vom Timer)“ — je Abschnitt Runde, Name, Zeit, km, Tempo, Ø HF, Punkt in der Farbe der Messung, der laufende fett; ab dem ersten Kilometer „Kilometer (vom GPS)“ mit Zeit, Tempo, Ø HF. Quer stehen die Tabellen links unter den Zahlen. Danach in der Auswertung „Intervalle (vom Timer)“ mit DFA α1 (H10). | offen |
| T33 | Forschungsexport (17.10.) | Training mit Gurt (gern mit Timer) → Auswertung → Kolben-Symbol oben („Für die Auswertung exportieren (ohne Ort)“) → Dialog → „Exportieren“: Teilen-Menü mit `einheit_<Datum>.zip`. Darin `einheit-v1.json` und die Messdatei unter `Messungen/…`; keine Strecke, keine Koordinate. | offen |
| T34 | Timer im Übungsformular (17.10.) | Übung → Bearbeiten → Abschnitt „Timer“: Profile mit Kurztext, das erste „Vorgabe“; Pfeil nach oben, Papierkorb, „Timer hinzufügen“ (neues Profil oder Kopie aus der Bibliothek). Stift → Editor über dem Formular (vorher gespeichert) → Speichern → zurück im Formular mit dem geänderten Profil. „Abbrechen“ im Formular verwirft Reihenfolge und Entfernen. | offen |
| T35 | „vom Timer“ (17.10.) | Plan üben → Uhr neben dem i → Timer bis zum Ende: unter „Heute geleistet“ die Werte und darunter mit Uhr-Symbol „vom Timer, 10:07“ (Anfang des Laufs); zwei Läufe: „vom Timer, 10:07 und 10:31“. Antippen → „Leistungen“: die Karte zeigt „10:07–10:09 Uhr · vom Timer“. Ein von Hand eingetragener Satz trägt den Hinweis nicht. | offen |
| T36 | Forschungsexport aus der Messung (17.10.) | Eine HRV-Messung, die mit einem Timer oder Training lief → Aufzeichnungen → Messung: Kolben-Symbol oben → Dialog (lief sie über mehrere Einheiten: Auswahl, vorgewählt die jüngste) → „Exportieren“ → Teilen-Menü mit `einheit_<Datum>.zip`. Eine Messung ohne Einheit zeigt das Symbol nicht. | offen |
| T37 | Seed und Paketquelle (17.10.) | Mit der ersten App nach v0.2.2 (Updates beim Start an): App zwei-, dreimal neu starten — in der Paketliste steht „Standard“ weiter auf „Version 2“, das Label unter dem Zahnrad meldet nicht bei jedem Start „aktualisiert: Standard“, im Modus „manuell“ steht kein „verfügbar: Version 2“. | offen |
| T38 | Messung mit Dauer (17.10.) | Messung → Gurt verbinden → „Dauer der Messung“: „5 min“ → „Wenn die 5 min um sind: Messung beenden“ → „Aufnahme starten“: Laufleiste mit Restzeit, Ton am Ende, die Messung endet und steht unter „Aufzeichnungen“ mit dem Abschnitt „5 min“. Mit „Weiterlaufen“ läuft sie weiter. „Ablauf“: Profil wählen (Abschnitte, Gesamt), Abschnitte werden Abschnitte der Messung. „Bereitstellen“ legt Messung und Timer in die Startleiste. „Stopp & speichern“ beendet auch den Timer. | offen |
| T39 | Startleiste kompakt (17.10.) | Timer, Messung (Gurt) und Training bereitstellen: auf Messung, Übungen, Timer usw. oben nur eine Zeile — Symbole der Teile (der nicht bereite mit Rand), „2 von 3 bereit“, der Stand des langsamsten Teils, ▶ (grau, bis alles bereit ist); Antippen öffnet „Heute“ im Reiter „Einheit · 3“ mit der Startkarte. Zum Reiter „Heute“ wechseln: der Tag wie sonst, oben nichts. „Alle starten“: „Heute“ öffnet wieder auf „Einheit“ — die Übersicht mit Laufzeit, „seit 15:31“, ⏸ ⏹, Timer mit Fortschrittsleiste (Stücke nach Dauer, Farbe nach Name, das laufende anteilig), „Wenn der Timer fertig ist – auch jetzt noch änderbar“, je Teil ein Live-Wert, Intervalle. Im Reiter „Heute“ oben die Laufleiste, antippen → Übersicht. „Einheit beenden“ im Lauf abwählen → nach dem Timer läuft sie weiter. Messung mit 5 min: in der laufenden Aufnahme „Weiterlaufen“ wählen → sie läuft nach 5 min weiter. | offen |

## 3. Befunde aus der Durchsicht vom 15.10.2026

Durchgesehen: Commits `59f3149..ed8bf8f` (14./15.10., alle mit Claude Opus).
Lint, Format, mypy und 573 Tests waren vor der Durchsicht grün.

Was hier steht, ist **nicht behoben** — behobene Befunde stehen nur noch im
Commit. Jeder Befund trägt eine Stelle zum Nachlesen; „Frage“ heißt, dass
Bens Entscheidung vor dem Fix nötig ist.

### 3.1 Datenbank und Migrationen

Keine offenen Befunde (D1 behoben, siehe 3.6).

### 3.2 Übungspakete, Seed, Paketmanager

| # | Stelle | Befund | Schwere |
|---|---|---|---|
| K1 | `ui/views/uebung_detail.py:112-116`, `core/pakete.py:293-311`, `uebung_bearbeiten.py:450-459` | Video-URIs aus fremden Paketen (und aus dem Editor) werden ohne Schema-Prüfung übernommen und per `launch_url` geöffnet — `intent://`, `file://`, `tel:`, im Web `javascript:`. **Vertagt (K-F6):** Ben will Medien gesondert besprechen (Rechte, Sicherheit, Injections) — Fakten in Abschnitt 4. Bis dahin unverändert. | mittel |
| K5 | `core/pakete.py:95-105, 249`, `data/pakete.py` | Paket-ID = UUIDv5 aus dem Namen, Übungs-ID aus Paket-ID + `key`: zwei fremde Pakete „Yoga“ mit `key` „baum“ gelten als dasselbe Paket. **Entschieden (K-F2, K-F3):** Paketkennung mit Kürzel (siehe „Offene Arbeiten“ A1); Standard bleibt offen, Rückfrage ist gebaut. | niedrig (Vertrag) |
| K6 | `data/pakete.py` (`_planen`, `_eintragen`) | Kein Versionsvergleich: eine ältere Paketdatei überschreibt eine neuere Installation (Downgrade), die Version wird zurückgesetzt. **Entschieden (K-F7): nachfragen** — kommt mit der Paketkennung (A1). **Seed behoben (17.10.2026):** Der Start lässt eine neuere Installation von „Standard“ in Ruhe (`data/seed.seed_einspielen`); offen bleibt die Rückfrage beim Datei-Import (A1). | niedrig |
| K10 | `ui/views/pakete.py:190, 332` | Paketliste lädt je Übung einzeln (~4·N Abfragen je Paket), nur um „n geändert“ zu zählen. Bei 33 Übungen harmlos. | niedrig |
| K12 | `ui/views/pakete.py:526` | Archivierte Paketübungen sind nicht exportierbar (`alle()` ohne Archiv). **Frage K-F8:** gewollt? | niedrig |

Geprüft und in Ordnung: SQL nur mit Platzhaltern; Export-Dateiname bereinigt; eigene Übungen (`package_id IS NULL`) werden nie angefasst; zweiter Start überschreibt nichts; UUIDv5-Stabilität; Flet-API der Pakete-Ansichten; keine `flet`-Importe in `core/`/`data/`.

### 3.3 GPS, Strecken, Ausdauertraining

Regel 0 („GPS nie teilen“) hält in Export, Diagnose, Teilen, Notizen und
Vorabtest-Bericht; Strecken liegen unter `Strecken/`; GPX nur per Knopf.
Eine Ausnahme ist nicht geregelt:

| # | Stelle | Befund | Schwere |
|---|---|---|---|
| G8 | `ui/views/ausdauer.py:767-771`, `repositories.py:1886-1890`, `gps_test.py:340` | „Entfernen“ ist Soft-Delete, die Koordinatendatei bleibt unbegrenzt; kein Papierkorb, kein endgültiges Löschen (HRV hat `PAPIERKORB_TAGE`). Vorabtest-Dateien `vorabtest_*.jsonl` werden nie gelistet oder gelöscht. **Frage G-F5.** | niedrig |
| G9 | `core/strecke.py:311` | Genauigkeit `None` passiert den Filter als perfekt — ohne Angabe gibt es nichts zu filtern; bleibt so. (Rücksetzen nach Sprung und Stehzeit vor der Auto-Pause seit 15.10. behoben.) | niedrig |
| G10 | `ui/geraete/flet_gps.py:75-79`, `strecken.py:141-142` | `use_msl_altitude` nicht gesetzt → Ellipsoidhöhe; `<ele>` im GPX liegt in Deutschland ≈ 45 m über NN. Höhenmeter (Differenzen) unberührt. **Frage G-F7:** MSL einschalten? | niedrig |
| G12 | `data/strecken.py` (`StreckenSchreiber.schreiben`) | `flush()` ohne `fsync` — übersteht App-Absturz, nicht Stromausfall. (Typprüfung beim Lesen seit 15.10. behoben.) | niedrig |
| G15 | `ui/views/gps_test.py:59-203` | `GpsTestLauf` (Dateischreiben, DB-Zeile) liegt in `ui/views`; das Pendant `Messlauf` liegt in `devices/`. Ohne flet nicht testbar (`importorskip`). Das Ausdauertraining ist seit 17.10. ein Teil der Einheit (`devices/strecke_baustein.py`; Datei, Tagebuch und Nachtragen flet-frei in `ui/training.py`). | niedrig |
| G17 | `uv.lock` ↔ `build/site-packages` | Entwicklung auf Flet 1.0.3, APK-Build auf 1.0.4; CLAUDE.md verlangt Gleichstand mit `flet-mcp`. | niedrig |
| G18 | `repositories.py:1883` | `strecke.title` + `titel_setzen` ohne Oberfläche — geplant oder Rest? **Frage G-F8.** Ebenso: Live-Karte folgt jede Sekunde, Wegwischen unmöglich — gewollt? **Frage G-F6.** | niedrig |

Positiv geprüft: keine Division durch null; leere Strecke abgefangen; Ereignis-Handler laufen bei Flet 1.0 im Loop (`put_nowait` loop-sicher); Dart-Seite kündigt den Stream bei `on_position_change=None`; Zeitbasis durchgehend UTC-aware; Haversine, Pace-Einheiten korrekt; Streckenrechner inkrementell.

### 3.4 HRV-Messung, Analyse, Rohdaten

Zurückschreiben von `titel`/`notiz`/`ereignisse` ist atomar (tmp + fsync +
`os.replace`), Whitelist verhindert Messwert-Änderungen, Schlüsselfolge und
unbekannte Felder bleiben; Crop/Abschnitte liegen nur im Sidecar. Kurze und
leere Messungen sind in allen Rechenwegen geschützt. Kein `flet`/`scipy` in
`hrv_core`. Live vs. Editor schreiben nie gleichzeitig dieselbe Datei.

| # | Stelle | Befund | Schwere |
|---|---|---|---|
| H5 | `hrv_core/ausschnitte.py:282-295, 231-248` | Beim Speichern werden alle Nicht-„gesamt“-Segmente mit `metrics: None, computed_utc: None, active: True, visible: True` neu geschrieben; praxis_gui-eigene Werte dieser Felder gehen verloren, `zusatz_lesen` liest sie nicht. **Frage H-F3:** durchreichen oder bewusst normieren? | niedrig |
| H6 | `ui/views/messung_detail.py:338` | `beschreibung = rec.notiz or eintrag.note`: eine in der Datei (praxis_gui) geleerte Notiz wird von der DB-Kopie überdeckt — „Datei ist die Wahrheit“ hier nicht ganz. Titel wird dagegen gespiegelt. **Frage H-F7.** | niedrig |
| H7 | `hrv_metrics_cache` | Wird im Code **nirgends** gelesen oder geschrieben (nur Migration 001); alle Kennzahlen werden bei jedem Öffnen neu gerechnet. CLAUDE.md beschreibt den Cache als tragendes Element. **Frage H-F5:** ungenutzt lassen (dann Doku anpassen) oder die Öffnungszeit der Detailansicht damit tragen? | niedrig |
| H8 | `ui/views/messung_detail.py:305-329, 385-409, 375, 1661` | Laden, Vorschläge, Kacheln (Atmung über bis zu 2000 Minutenfenster, SampEn bis 3000 Schläge) laufen synchron im Event-Loop beim Aufbau; laut `plan_analyse_leistung.md` bewusst so belassen. **Frage H-F6:** `hrv_core`-Rechnungen per `asyncio.to_thread` (flet-frei, thread-tauglich)? | niedrig |
| H11 | `ui/views/messung_detail.py:385-409` ↔ `ausschnitte.py:192-198` | Atem-Median über Minutenfenster existiert doppelt (UI adaptiv mit Deckel, `ausschnitte` 15 s fest ohne Deckel). Gehört einmal nach `hrv_core`. | niedrig |
| H12 | `tests/test_frequenz.py:275` | Langer Spektralweg (ULF/VLF/LF/HF, ALGO 5) hat nur eine synthetische Reihe im Test (Toleranz 10 %), keine Referenzdatei unter `tests/golden/rr/` und keinen Vergleichswert aus praxis_gui/scipy. | niedrig |
| H13 | `hrv_core/ereignisse.py:337-355` | Jede Notiz liest und schreibt die ganze Rohdatei synchron im Event-Loop (MB bei Stundenmessungen); Absturz zwischen Rohdatei-Write und Sidecar-Update hinterlässt veraltetes `source_file_sha1` (praxis_gui hält Sidecar für veraltet, kein Datenverlust). | niedrig |
| H17 | `tests/test_ui_messung.py::test_live_notiz_eingefroren_und_jetzt` | Unter Last wackelig: Simulator mit `tempo=30`, die Toleranz von 2 s Simulatorzeit sind 67 ms echte Zeit — schlug am 17.10. in einem vollen isolierten Lauf einmal fehl, allein 3 von 3 grün. Vorschlag: Zeit über eine Uhr-Attrappe statt echter Wartezeiten (`tests/attrappen.py`). | niedrig |
| H18 | `devices/polar.py` (`_daten_da`, `watchdog_pruefen`, `_neu_verbinden`); Auswertung eigener Messungen, hrv-research, 17.10.2026 | Nach dem Neuverbinden durch den Watchdog reißt der Datenstrom nach etwa 2 s wieder ab. Die App verbindet dann im festen 16-s-Takt neu: 8 s ohne Daten, 3 s Wartezeit, Neuaufbau, etwa 2 s Daten — rund 80 % der Messung fehlen. Die angekommenen Schläge sind sauber, ein Sensorfehler ist es also nicht. Jedes kurze Datenstück setzt in `_daten_da` den Zähler zurück und nimmt die Warnung zurück; darum bleibt es immer bei Versuch 1 mit 3 s Wartezeit, und keine Warnung bleibt stehen. Der Zustand hielt über mehrere Messungen an. Zu prüfen: Diagnoseprotokoll, eine zweite Verbindung zum Gurt (Polar Flow, Uhr), Bluetooth und Energiesparen des Handys. Vorschlag: Zähler erst nach einer stabilen Phase zurücksetzen, die Schleife erkennen, Warnung stehen lassen (`docs/plan_diagnose.md` §1). | hoch |

### 3.5 Pläne, Notation, Timer, Profile, App-Hülle

Flet-1.0-API in diesem Bereich geprüft, keine falsche Nutzung. `spec_snapshot_json`
immer gesetzt, keine `UPDATE` auf `result_json`/Snapshot, Korrektur nur über
`replaces_entry_id`, `reihenfolge_setzen` lückenlos, Migration 010 Backfill
getestet, SQL ohne Nutzereingaben im Text.

| # | Stelle | Befund | Schwere |
|---|---|---|---|
| N5 | `data/repositories.py:172-178` ↔ `:1725-1727` | `ExerciseRepo.speichern` legt Tags mit `ON CONFLICT(name)` (case-sensitiv) an, `TagRepo.anlegen` prüft `COLLATE NOCASE`: über Editor/Paketimport entstehen „dehnung“ und „Dehnung“ nebeneinander. **Frage N-F3:** UNIQUE-Index `COLLATE NOCASE` per Migration? | niedrig |
| N6 | `data/repositories.py:742-770` | `ziel_setzen`/`eingabe_setzen` erhöhen `plan.revision`/`updated_at` nicht (`_beruehrt` fehlt), anders als `umbenennen`/`aktiv_setzen` — für „letzter Schreiber gewinnt“ unsichtbar. **Frage N-F5:** `plan.revision` als Anker für Items oder eigene Item-Revision? | niedrig |
| N7 | `ui/views/timer.py:178-186, 91-93` | Timer-Profil bearbeiten und speichern, während der Timer läuft: `lauf_fuer` ersetzt den Lauf, der Ticker vergleicht Stände zweier Läufe (möglicher Geister-Ton), danach stoppt der Timer still. **Frage N-F6:** warnen, blockieren oder weiterlaufen lassen? | niedrig |
| N14 | `repositories.py:881-885, 1172-1174`, `tag.py:284`, `plan.py:253`, `tag.py:74` | N+1: `verwendungen` lädt je Item den Plan; `heutiger_eintrag` je Zeile eine Session; Tagesansicht je Gruppe den Plan; Plan/Tag laden bei jedem Aufbau den ganzen Katalog mit Tags und Medien. Bei 33 Übungen egal. | niedrig |
| N15 | `app_setting darstellung:<profil-id>` | Bleibt nach Profil-Löschen stehen (**Frage N-F8**, Vorschlag: belassen, Profile werden nur ausgeblendet). Test für `physiologische_steuerung` in solo seit 15.10. vorhanden. | niedrig |

### 3.6 Behoben am 15.10.2026 (nur zur Einordnung)

Je Paket ein Commit auf `main`; Tests dazu in den genannten Dateien.

- **H-Wischen** (765b4a4) — `zeitfenster.py`: Flets Drossel verwirft Zwischenereignisse; jetzt zählt `local_delta`. Siehe P15/T4.
- **D1** (df51dfc) — Migrationen laufen in `BEGIN … user_version … COMMIT` im Skript; Test mit kaputter Migration.
- **N1, N2, N9** (c2b7951) — Notation mit Grenzen 100 Sätze / 48 h / 100 000; `inf`/`nan` abgelehnt; `parse_anzahl` mit `isdecimal`; Altbestand zeigt „–“.
- **N3** (a965f68) — `Messlauf.subject_id`, `AusdauerLauf.subject_id`; Hinweis beim Profilwechsel.
- **N4** (1d56acc) — `Nachher` in Profil, Plan, Timer-Profil, Übung entfernen.
- **H1–H4** (19582e8) — `SidecarFehler` statt stillem Ersatz; Abschnitte über `frequenzbereich` (ALGO 7, Nähte, langer Weg); `ppi._gemerkt` mit Weakrefs.
- **G1–G7, G12 (Typprüfung), G2** (3cfbcb8) — Kopfzeile + Nachtragen verwaister Strecken; Warnzeile; `abbrechen`; Tempo 0 = fehlt; Karten-Schalter und einmaliger Hinweis; TOMs/Store-Freigaben nachgezogen.
- **K2, K3, K4, K-F3-Rückfrage** (4fd7a54) — Entfernen mit Plan-Rückfrage und Kopie; Paketstand folgt Tags; Lokales bleibt; Standard-Hinweis beim Import.
- **Nachtrag HRV** — Abschnitte rechnen auf der Kurvenachse wie das Band (Verity-Abschnitte hatten über den Teilstück-Weg kein Spektrum mehr); H9, H10, H14, H15.
- **Niedrige Befunde ohne Entscheidung** — K7, K8, K9, K11, K13, G9 (Teile), G11, G13, G14, G16, N8, N10, N11, N12, N13, N15 (Test).
- **Crash-Backup wiederherstellen** — das 15-s-Backup gab es, aber nichts fand es wieder (Ben: Akku während 4-h-Aufnahme leer, Messung weg). Jetzt: Dialog beim Start, `backup_wiederherstellen`, Profil und Timer-Abschnitte im Backup (`_wiederherstellung`), Sicherung beim Hintergrundwechsel. Offen: H16.

## 4. Medien an Übungen — Fakten für die vertagte Entscheidung (K-F6, P14)

Ben (15.10.): gesondert besprechen wegen Rechten, Sicherheit und Injections. Stand des Codes:

- Modell `core/models.py:81-101`: `Media(kind: video|image, source: url|asset|local, uri, title, license)`; `Exercise.image_path`.
- Import `core/pakete.py` `_medium`: übernimmt jede nicht leere `uri` ohne Schema-Prüfung (`intent://`, `file://`, `tel:`, `javascript:`); `source = local` wird verworfen. Export (`stand`) gibt URL- und ASSET-Medien weiter.
- Editor `ui/views/uebung_bearbeiten.py:450-459`: baut beim Speichern **alle** Medien als `url`/`video` neu — `source`, `kind`, `license` und die Medien-ID gehen verloren (ein LOCAL-Medium würde zu URL).
- Detail `ui/views/uebung_detail.py:112-116`: `launch_url(medium.uri)` ohne Prüfung; die Liste unterscheidet nicht nach `kind`/`source`.
- `image_path` wird in `ui/` nirgends gelesen oder gesetzt; LOCAL-Medien legt kein Code an — beides existiert nur im Datenmodell (seit 15.10. überleben sie Update/Reset).
- Zu entscheiden: erlaubte Schemata (nur `https`? YouTube-App-Links?), Lizenz-/Rechtefeld im Paket (Pflicht?), Ablage lokaler Dateien (Datenverzeichnis, Größe, Export?), Streaming von der Praxis (P12: Solo speichert nichts auf dem Server), Anzeige von Fotos in Beschreibung und Tagebuch.
- Seit 15.10. betrifft das auch **Kurskapitel** (`course_chapter.media_json`, zusätzlich `kind = audio`): dieselben Links, dieselbe Anzeige (`ui/views/kurse.py`), dieselben offenen Fragen — plus P20 (Tonspieler).

## 5. Export und Import — Inventar (Ben, 15.10.: „wir kümmern uns gesondert darum“)

Anlass: Wer Inhalte in ein anderes Profil will, soll exportieren und dort importieren (N-F1).

| Inhalt | Export heute | Import heute |
|---|---|---|
| HRV-Messungen (raw-v1 + Sidecar) | ZIP je Messung oder alle (`hrv_core/export.py`, `messung.py:874`, `messung_detail.py:261`) | — (Dateien in `Messungen/` werden beim Start erkannt, kein Knopf) |
| Diagnoseprotokoll | Teilen (`messung.py:76`) | — |
| Strecken | nur GPX per Knopf (`ausdauer.py:749`, `gps_test.py:401`) | — |
| Übungen | Paket (`pakete.py:517-623`) | Paket |
| Pläne, Planparameter | — | — |
| Kurse (ohne Fortschritt) | Paket (`kurse[]`, Formatversion 2) — nur mitgelieferte/importierte, kein Export-Dialog | Paket |
| Kursfortschritt | — | — |
| Tagebuch (Sitzungen, Einträge, Notizen, Tagesnotizen) | — | — |
| Timer-Profile und Signale | — | — |
| HRV-Einstellungen, Korrekturregeln, Ansichten | — | — |
| Profile, Farbprofile | — | — |
| Typen/Regionen | nur mit Übungen im Paket | nur mit Übungen im Paket |

Offen: Reihenfolge, Format (ein Archiv je Profil?) und was ein Import mit vorhandenen IDs tut (Konflikt-Regel wie bei Paketen).

## 6. Offene Arbeiten — entschieden, noch zu bauen

| # | Woher | Was | Hinweise |
|---|---|---|---|
| A1 | K-F2, K-F7 (15.10.) | **Paketkennung:** gleicher Name = gleiches Paket, dazu ein Kürzel bis 6 Zeichen (`DEH-01`, `KRA-01`); gleicher Name + Kürzel = Update. Namenspolicy festlegen. **Downgrade** (ältere Version über neuere) fragt nach. Policy geänderte Übungen: stark variiert → kopieren (eigene Übung); Material bleibt an der Übungs-ID. | Braucht: Spalte `package.kuerzel` (nächste freie Migration: 020 — 018 ist die Einheit, 019 Strecke ↔ Einheit), Kopffeld in `paket_lesen`/`paket_bauen` (`core/pakete.py:182-196, 413-417`), `Paket`-Dataclass, `_eintragen`/`_zeile` (`data/pakete.py`), Eingabe im Export-Dialog, Version beim Export hochzählen, Doku-Tabelle `uebungspakete.md:114-123`. |
| A2 | Ben, 15.10. | **„abgehakt“ als eigener Speicherwert:** separat gespeichert und löschbar; gibt man Werte ein, bleibt „abgehakt“ stehen, lässt sich aber herausnehmen. | Datenmodell `session_entry` (Flag + Migration), `core/plaene.erledigte`, Tagesbilanz, Planblock („Heute geleistet“), Formular. Heute: „gemacht“ = leerer Eintrag. |
| A3 | G-F1 (15.10.), Ben 17.10. | **Hilfedatei** anlegen, Kapitel GPS/Kartenaufzeichnung (Karte holt Kacheln online, Schalter, Regel 0). Kapitel **Atemfrequenz und Atemübung** kommt auf jeden Fall hinein (Ben, 17.10.: was „unter 8/min“ und der Knopf „Atemübung“ heißen). | Vorhandene Hilfetexte: `ui/components/hilfe.py` (Notation, Varianten und Pakete, Atemfrequenz und Atemübung — `ATMUNG_MD`). Die Erklärtexte hinter den „i“-Knöpfen der Messansicht (`TACHOGRAMM_INFO`, `PULS_INFO`, `_kurven_info`) gehören mit hinein. |
| A4 | N-F1 (15.10.) | **Export/Import je Inhalt** (Abschnitt 5) für den Transfer zwischen Profilen. | Reihenfolge und Format offen. |
| A5 | P12/P14 (15.10.) | Edition B: Solo speichert nichts auf dem Server, einzige Verbindung ist Video-Streaming; eigene Fotos/Videos lokal **und** aus Fremdquelle. | Rahmen für Medien (Abschnitt 4) und `docs/recht`. |
| A8 | Updates (16.10.) | **Update-Stufe 2:** Download und Installation in der App statt über den Browser. Braucht eine Kotlin-Erweiterung wie `flet_ton` (Intent `ACTION_VIEW`/`PackageInstaller`, FileProvider), Berechtigung `REQUEST_INSTALL_PACKAGES`; Android fragt trotzdem einmal je App „aus dieser Quelle erlauben?“ und je Update „Installieren?“. Gewinn gegenüber Stufe 1 (gebaut: `core/update.py`, Einstellungen → App): ein Tipp weniger. Erst, wenn der Browserumweg im Alltag stört. iOS: nur TestFlight/App Store. | Stufe 1 gebaut 16.10. |
| A7 | Umzug hrv-core (16.10.), H11 | **Rechenlogik aus `ui/views/messung_detail.py`** (`_Zustand`, Atem-Median über Minutenfenster, SampEn-Deckel 3000) in die Bibliothek — gehört nach hrv-core, nicht hierher. | Nach dem Umzug beider Apps; Expertenmodus (Korrekturregeln sichtbar) kommt als Zuschaltung, Automatik bleibt Vorgabe. |
| A9 | Paketquelle (16.10.) | **Paketquelle in Betrieb nehmen:** Ort übergangsweise `https://trainingsapp.osteo-ebert.de/pakete/` auf dem Server der Praxis, bis die Website der App steht. Die Einrichtung auf dem Server (Ordner, Upload-Schlüssel, DNS, Caddy) steht im privaten Repo der Homepage (ADR-0022, OP-48); hochgeladen wird aus `trainingsapp-inhalte` (`veroeffentlichen.sh`). Danach hier: `QUELLE_VORGABE = "https://trainingsapp.osteo-ebert.de/pakete/index.json"` (`core/paketquelle.py`), Release, T14 am Handy, Datenschutz-Information nennt die Quelle (G-F2). **Vor einem späteren Umzug der Adresse:** Die alte leitet per 301 weiter, damit ältere App-Versionen und von Hand eingetragene Quellen weiter Updates finden — vorher `core/paketquelle._laden` so bauen, dass es Weiterleitungen nur auf `https://` folgt (heute folgt `urllib` jeder). | Reihenfolge: Server (OP-48 S2–S4) → erstes Paket veröffentlichen → Vorgabe setzen → Release. |
| A16 | Ben, 17.10. | **Paketversionen major.minor.patch** (`docs/plan_paketversionen.md`): Die App bestimmt die Stufe aus dem Unterschied; major fragt nach, minor kommt automatisch mit Hinweis, patch nur bei Neuinstallation oder „Auf Paketstand“. Phasen 2–5: Format, Stufe und Verhalten, Oberfläche, Werkzeug. | Gehört zu A1 (Paketkennung, Downgrade). Phase 1 (K6, Seed) gebaut 17.10.; offen P31–P35. Bis Phase 2 bleibt `paket.version` eine ganze Zahl. |

---

## Entschieden

| Datum | Frage | Entscheidung |
|---|---|---|
| 17.10.2026 | Startleiste kompakt | **Variante B** (Ben, Skizzen 16–21; „der halbe Screen ist mit den bereitgestellten Dingen belegt“): Bereitgestellt steht auf jeder Seite außer „Heute“ nur die Infoleiste (eine Zeile, ▶, Antippen → Reiter „Einheit“); „Heute“ hat mit einer Einheit die Reiter „Einheit“ (Startkarte, im Lauf die Übersicht) und „Heute“ (der Tag, im Lauf mit der schmalen Laufleiste). „Heute“ öffnet auf die Einheit, sobald eine erscheint oder beginnt; wer auf den Tag wechselt, bleibt dort bis zur nächsten Änderung. „Wenn der Timer fertig ist“ (Einheit beenden, HRV beenden) und in der Messung „Messung beenden \| Weiterlaufen“ sind auch im Lauf änderbar (Ben). Die Fortschrittsleiste (A17) steht in der Übersicht statt in der Messansicht — die Marken zeigt die Messung selbst. `docs/plan_einheit.md` §9. Gebaut; T39. |
| 17.10.2026 | Paketversionen | **major.minor.patch** (Ben): major — etwas fällt weg (Übung, Kurs, Kapitel) oder ein Kurs ändert seinen Ablauf → Nachfrage; minor — etwas kommt dazu oder wird korrigiert (Texte, Links, neue Übungen und Kurse, Felder der Eingabe) → automatisch, danach ein Hinweis; patch — nur Vorgaben (Chips, Timer, Symbol, Typen, Regionen, Ziel, Planparameter) → still, für Neuinstallationen und „Auf Paketstand“. Eigene Chips bleiben, außer bei „Auf Paketstand“. Feldkonflikt: Die eigene Fassung bleibt, dazu ein Hinweis und in der Übung ein Vergleich je Feld; Hierarchie Paket → Übung → Planübung. `docs/plan_paketversionen.md`; zu bauen A16. |
| 17.10.2026 | Seed neben Paketquelle (K6) | Ist „Standard“ schon in höherer Version installiert (Quelle, Datei), lässt der Start das Paket in Ruhe (`seed_einspielen`). Die Datei der App entspricht einem veröffentlichten Stand: gleiche Version, gleicher Inhalt. Gebaut nach v0.2.2; T37. |
| 17.10.2026 | P5 Kopplung HRV, GPS, Timer, Plan | **Einheit** (Ben: „Man bereitet alles vor und wenn man soweit ist, klickt man auf Start“): Jeder Bereich kann bereitstellen statt starten; die Startleiste unter der Titelleiste startet alles auf denselben Zeitpunkt (ein t0, wahlweise Countdown 3-2-1); eine HRV, die schon läuft, bekommt nur Marken und läuft weiter. Eine Zeitachse, Zeitleiste in der Datenbank (Migration 018), typisierte Marken und Abschnitte je Spur in der Messdatei (`docs/kompatibilitaet.md` §4, §9b), unter 5 s keine Marke. Vertrag `docs/plan_einheit.md`. Gebaut: Stufen 0–2; Messung mit Dauer → A11, Timer an der Übung → A12. |
| 17.10.2026 | Bereitstellen: Knopf oder Fahne | Ein zweiter Knopf „Bereitstellen“ neben „Start“ (Ben), nicht der Sammelmodus mit Fahne (Skizze 11). Gebaut. |
| 17.10.2026 | P26 Timer im Hintergrund | Vordergrunddienst Typ `health` (Ben) — für einen Timer allein und für Einheiten ohne Gurt und GPS; `FOREGROUND_SERVICE_HEALTH` und `HIGH_SAMPLING_RATE_SENSORS`, Begründung in `docs/recht/80_store_freigaben.md`. Gebaut; T24. |
| 17.10.2026 | Ausdauer als Einheit | Das Training ist ein Teil der Einheit: bereitstellen, Intervalle mit dem Timer, Kilometer zur Split-Zeit auf eigener Spur; eine laufende HRV wird verknüpft (`strecke.einheit_id`, Migration 019) und läuft weiter; die Auswertung legt Ortungen und Schläge über die Versätze aufeinander; Nachtragen nach einem Absturz verknüpft Strecke und Messung (H16). Gebaut; T25, T26. Tabellen „Intervalle“ und „Kilometer“ (Skizze 6, A10) live und in der Auswertung — `core/intervalle.py`; T32. |
| 17.10.2026 | Timer an der Übung | Ben: Timer an Katalog- oder Planübung, am Plan „für alle“; mehrere Profile; Uhr neben dem i; fertig = gemacht, die Zeit wird eingetragen; erst einmal zählt alles, je Abschnitt umschaltbar (farbig), „Zeit eintragen“ abschaltbar; „Abbrechen“ statt „Entfernen“, gelöscht wird über „Heute geleistet“; „Weiter“/„Fertig“ nehmen die gelaufene Zeit; unter 5 s keine Marke; Vorrang Planübung > Plan > Übung. Gebaut (Migration 020; Plan-Ablauf aus dem Timer, `docs/plan_einheit.md` §7); T27–T31, offen A13. |
| 17.10.2026 | Forschungsexport (Stufe 4) | Ausdrückliche Handlung wie GPX: ein ZIP mit den Messdateien der Einheit byte-genau und `einheit-v1.json` (Zeitleiste, Teile mit Versätzen, Tempo als 5-s-Mittel), ohne Ort (`docs/plan_einheit.md` §8, `core/forschung.py`). Gebaut in der Auswertung des Trainings; T33, offen A14. |
| 14.10.2026 | GPS-Takt | Sekundentakt, keine Sparstufe (Ben). |
| 16.10.2026 | Wegwischen während einer Messung | Die Messung läuft weiter (Ben). Eine eigene MainActivity hält die Flutter-Engine über das Ende der Activity hinaus — Bluetooth bleibt verbunden; den Prozess hält der Vordergrunddienst (`scripts/apk_bauen.py`, Vorlage mit eigener MainActivity). Gebaut; T15. |
| 16.10.2026 | Was läuft, anzeigen | In der Benachrichtigung (Ben: „das wäre am besten“): ein App-Symbol in der Statusleiste, je Tätigkeit eine Zeile mit Zeit — HRV, Training/Karte, GPS-Test, Timer (`core/laufend.py`, `ui/laufend.py`). Kanal mit Wichtigkeit „Standard“ ohne Ton, sonst zeigt die Statusleiste kein Symbol. Gebaut; T16. Timer allein ohne Vordergrunddienst → P26; iOS → P27. |
| 16.10.2026 | Ungespeichertes beim Zurück | Autosave (Ben: „am besten wäre ein Autosave“): Zurück speichert, was geändert wurde; ist es unvollständig, fragt ein Dialog „Weiter bearbeiten“ oder „Verwerfen“; „Abbrechen“ verwirft (`ui/components/zurueck.py`). Blätter und Notizdialoge speichern beim Schließen. Gebaut; T17. |
| 17.10.2026 | Notizen und Korrekturen in der Übungsausführung | Eine Notiz je Übung, Tag und Plan: Der Notiz-Knopf öffnet immer dieselbe (die früheste mit Text, sonst am jüngsten Eintrag — `SessionRepo.notiz_eintrag`), der Freitext ersetzt den von heute (`text_setzen`). „Heute geleistet“ zeigt alle Einträge der Übung von heute auf einer Seite, alles auf einmal bearbeitbar (Korrekturen, der alte Stand bleibt im Verlauf), einzeln löschbar (`views/leistungen.py`). Gebaut; T20. |
| 17.10.2026 | Messansicht entrümpeln | Erklärtexte hinter ein „i“ im Kartentitel (`components/karte.info_knopf`, Blatt mit Markdown) statt grauer Text unter der Kurve, ebenso in Abschnitte, Korrektur und Verlauf (Ben, 17.10.: „noch in v0.2.2“; sichtbar bleibt, was die Zahlen einschränkt); die Diagnose hinter ein Protokoll-Symbol in der Gerätezeile (`views/messung.diagnose_blatt`) statt Klappfeld ganz unten; die Beschreibung als einzeiliger Auszug unter dem Titel, aufklappbar (`titel_kopf(klein=True, offen=…)`) — Ben: „damit es nicht überladen ist“. Gebaut; T21. |
| 17.10.2026 | Geräte nur mit Herzfrequenz | Uhren und Sensoren ohne RR/PPI bekommen den Puls (bpm) als Hauptkurve — live und in der Aufzeichnung (Achse = Wanduhr `t_wall_s`; Korrektur, Zuschneiden und Abschnitte entfallen). Hinterlegt im Geräteprofil (`UHR_BROADCAST`, `hrv_moeglich=False`, Muster um Garmin-Schreibweisen, Xiaomi, Huawei ergänzt); ohne Angabe im Profil erkannt nach `NUR_PULS_NACH` = 10 Paketen ohne Intervall. Kommt ein Intervall, wird es das Tachogramm (`views/messung.nur_puls`). Gebaut; T21. |
| 17.10.2026 | Titel und Beschreibung vor der Aufnahme | Das war mit „Notizen vor der Aufnahme“ gemeint (Ben, 17.10.): „Titel hinzufügen“ steht schon vor dem Start unter „Aufnahme starten“, der Start übernimmt Titel und Beschreibung (`Messlauf.titel_notiz`). Der Timer schreibt weiter nur in eine laufende Aufnahme („braucht die Notiz nicht“). Gebaut; T19. |
| 16.10.2026 | Notizen vor der Aufnahme | Möglich, live wie während der Aufnahme (Ben). Beim Start rücken sie an den Anfang der Aufnahme (Zeitpunkt 0; Text und Übungen bleiben); eine gerade getippte Notiz kommt mit (`Messlauf.ereignisse`). Gebaut; T19. |
| 16.10.2026 | Neue Aufnahme | Leert die Kurven (Ben): Live-Fenster leer, die Live-Achse beginnt bei 0 — Kurven, Kacheln und Analyse zeigen nur die neue Aufnahme (`Messlauf.aufnahme_starten`). Gebaut; T19. |
| 16.10.2026 | Reiter | „Übungen · Pläne · Kurse“ und „Live · Aufzeichnungen“ gleichmäßig über die ganze Zeile (Ben). Gebaut. |
| 16.10.2026 | Vollbild: zwei Achsen | Wie praxis_gui eine Werteachse links und eine rechts, je Achse eine Skala; gleiche Skala teilt sie (HF Gerät + Ø HF), andere ersetzt; über die Analysebereiche hinweg kombinierbar (RMSSD links, DFA α1 rechts). Vorgabe: Tachogramm links, RMSSD rechts (`Ansicht.links/rechts`, Formatstand 4); beide Achsen auf demselben Raster mit runden Werten (`kurve.doppel_raster`). Live und in der Aufzeichnung gleich (`components/vollbild.py`). Gebaut; T10/T11. |
| 16.10.2026 | Vollbild: Kurvenwechsel | Nur noch Pfeile und Liste je Achse — hoch/runter wischen ist entfernt (störte beim Zeitwischen). Ersetzt „Pfeile + Liste und hoch/runter wischen“ vom 15.10. Gebaut. |
| 16.10.2026 | Vollbild: Notizen und Abschnitte | Quer dieselben Funktionen wie hochkant, in einer Seitenleiste (dasselbe Notizfeld mit Text, Zeit, Übungen; Abschnittsliste mit „+ Abschnitt“, „Aus Notizen …“, „Alle löschen“); Tipp auf Marke oder Balken zeigt ein Etikett (Zeit und Text bzw. Name und Werte) mit Bearbeiten und Löschen (Rückgängig). Ersetzt „Textansicht nur hochkant“ vom 15.10. Gebaut. |
| 16.10.2026 | Vollbild: Ablesen | Auch im Live-Vollbild; quer schweben die Werte über der Kurve (auf der Seite ohne Strich). Gebaut. |
| 16.10.2026 | Querformat: Zweck | Querformat ist für die bessere Kurvenansicht — Kurven, Notizen, Abschnitte, Ablesen, Zuschneiden. Das Drumherum bleibt hochkant und kommt nicht ins Vollbild: Aufnahme starten/stoppen, Titel, „korrigiert“ und Korrektur, Kacheln, Export, Entfernen usw. (Ben). Vielleicht später: Spektrum bzw. Nichtlinear neben der Kurve → P25. |
| 16.10.2026 | Paketmanager: Update-Konflikt | Nutzeränderung bleibt — Drei-Wege-Abgleich je Feld gegen den gespeicherten Paketstand (`core/pakete.zusammenfuehren`), für Datei-Import und Online-Update gleich; ersetzt „Änderungen gehen verloren (gewollt)“. Gebaut (Migration 017). |
| 16.10.2026 | Paketmanager: entfallene Übungen | Nie löschen: markieren, Dialog „nicht mehr Teil des Pakets — übernehmen (eigene Übung, gleiche ID, Verlauf und Pläne bleiben) oder löschen“; nach dem Import sofort, sonst beim Start. Pakete sauber halten hat Vorrang. Gebaut. |
| 16.10.2026 | Paketmanager: Deaktivieren | Zerstörungsfrei: nichts sichtbar (Katalog, Suche, Tags, Kurse, Pläne), alles bleibt; Größe mit Fotos/Videos in der Paketzeile. Gebaut. |
| 16.10.2026 | Inhalte-Repo | `trainingsapp-inhalte` (privat) hält TOML-Pakete; die App startet direkt damit (`TRAININGSAPP_PAKETE`); Werkzeug `trainingsapp-paket` in der trainingsapp. Gebaut; Gerüst liegt lokal unter `../trainingsapp-inhalte`. |
| 16.10.2026 | Paketquelle: Ort | Übergangsweise `trainingsapp.osteo-ebert.de/pakete/` auf dem Server der Praxis, bis die Website der App steht; Upload aus dem privaten `trainingsapp-inhalte` mit einem Schlüssel, der nur in den Paketordner darf (wie die Website der Praxis). Einrichtung: Homepage, ADR-0022. → A9. |
| 16.10.2026 | Paketquellen (Schritt 2) | Index-JSON von beliebiger HTTPS-Adresse, Vorgabe Bens Server (Adresse kommt mit der Homepage, Repo „Homepage“), weitere Quellen eintragbar, später GitHub als Community-Quelle; SHA-256 + HTTPS, Signaturfeld reserviert; Label unter dem Zahnrad, Seite „Updates“, Benachrichtigung aus/Updates/Updates+Neuigkeiten; Modus auto/manuell je Paket; Schalter `paket_quellen` nur Solo. Gebaut (16.10.); `QUELLE_VORGABE` bleibt leer, bis die Adresse mit der Homepage feststeht. |
| 16.10.2026 | Dependabot `pub` | Dart-Seite der Erweiterungen bleibt unüberwacht: flutter_blue_plus wegen Lizenz nie über 1.36.8, Dart-flet im Gleichschritt, `flet build` löst neu auf. Begründung und Vorlage: `docs/dependabot.md`. |
| 16.10.2026 | A6 erster APK-Build mit hrv-core | Erledigt: Release v0.2.0 (Build 124, 87 MB, arm64) über den APK-Workflow mit Schwester-Checkout von hrv-core gebaut; die Update-Abfrage der App findet es. |
| 16.10.2026 | Öffentlich machen, Updates | trainingsapp wird öffentlich, sobald README/Nachbarrepo-Regel/Update-Stufe 1 durch sind (Ben stellt um, dann Secret-Scanning und Dependabot). Mailadresse in der Historie bleibt; `docs/recht` bleibt drin (wer die App in der eigenen Praxis nutzt, muss Bescheid wissen); Sitzungslinks in Commits bleiben (Nachvollziehbarkeit). Updates: Stufe 1 über GitHub-Releases, Stufe 2 vorgemerkt (A8). |
| 16.10.2026 | hrv-core öffentlich, Lizenz | Repo öffentlich; AGPL-3.0 mit CLA wie die trainingsapp (Eigenbedarf frei, geschlossene Kommerzialisierung nur mit Lizenz des Inhabers). Eigene anonymisierte Aufnahmen bleiben als Fixtures, werden nach und nach durch verlässlichere ersetzt. |
| 16.10.2026 | HRV-Mathematik auslagern | `trainingsapp.hrv_core` wird die Bibliothek `hrv_core` (Schwesterrepo hrv-core, gemeinsam mit praxis_gui). App behält nur `core/hrv_export.py`, `core/hrv_training.py`; Golden-Tests und Algorithmendoku liegen in hrv-core. EKG-Auswertung entfällt (kein neurokit2); Dateinamen bleiben UTC-Start; Automatik bleibt Vorgabe, Expertenmodus zuschaltbar. Gebaut auf `refactor/hrv-core`. |
| 15.10.2026 | K-F1 Paket entfernen ↔ Pläne | Übungen fliegen aus den Plänen; Rückfrage zeigt „Teil von Plan …“ und bietet „kopieren“ an, Kopien sind eigene Übungen und übernehmen die Planposition. Gebaut (4fd7a54). |
| 15.10.2026 | K-F2 Paket-Identität | Gleicher Name = gleiches Paket, mit Kürzel bis 6 Zeichen (`DEH-01`); gleicher Name + Kürzel = Update; Namenspolicy nötig. → A1. |
| 15.10.2026 | K-F3 Standard-ID | Offen für alle — mit deutlicher Rückfrage beim Import; eingebauter Stand per „Wieder installieren“ zurück. Gebaut. |
| 15.10.2026 | K-F4 Tags ↔ Paketstand | Mitziehen. Gebaut. |
| 15.10.2026 | K-F5 Lokale Medien | Behalten bei Update/Reset. Gebaut. |
| 15.10.2026 | K-F6 Medien-Links | Vertagt — gesondert besprechen (Rechte, Sicherheit, Injections). Fakten in Abschnitt 4. |
| 15.10.2026 | K-F7 Downgrade | Nachfragen; Policy für geänderte Übungen: stark variiert → kopieren, Material bleibt an der ID. → A1. |
| 15.10.2026 | N-F1 Profilwechsel in der Messung | Startprofil merken + Hinweis; Transfer zwischen Profilen per Export/Import → Inventar (Abschnitt 5, A4). Gebaut (a965f68). |
| 15.10.2026 | N-F2 Grenzen der Notation | 100 Sätze, 48 h, Werte ≤ 100 000. Gebaut (c2b7951). |
| 15.10.2026 | N-F4 Gelöschter Tag im Paketstand | Durch K-F4 erledigt: der Stand verliert den Tag. |
| 15.10.2026 | N-F7 Dialog-Muster | `Nachher` für jeden Bestätigen-Dialog. Gebaut (1d56acc). |
| 15.10.2026 | G-F1 Karte online | Schalter „Karte zeigen“, Hinweis **einmal** (nicht je Aufzeichnung), Infotext später in der Hilfe (A3). Gebaut (3cfbcb8). |
| 15.10.2026 | G-F2 docs/recht | TOMs und Store-Freigaben nachgezogen (3cfbcb8); Datenschutzerklärung folgt mit dem Store-Eintrag. |
| 15.10.2026 | G-F3 Tempo ohne Doppler | Tempo zählt nur mit Tempogenauigkeit; sonst Weg je Zeit, 10-m-Schritt. Gebaut; T5 am Gerät. |
| 15.10.2026 | G-F4 Prozess-Tod im Training | Beim Start erkennen und anbieten (Übernehmen/Löschen). Gebaut; T6. |
| 15.10.2026 | G-F9 Fehler im Training | Rote Warnzeile unter den Zahlen. Gebaut. |
| 15.10.2026 | H-F1 Lange Abschnitte | Langer Spektralweg wie die Gesamtmessung (ALGO 7). Gebaut (19582e8). |
| 15.10.2026 | H-F2 Unlesbares Sidecar | Schreiben verweigern, Hinweis zeigen (`SidecarFehler`). Gebaut. |
| 15.10.2026 | H-F4 Nähte in Abschnitten | Respektieren wie die Gesamtmessung (ALGO 7). Gebaut. |
| 15.10.2026 | „abgehakt“ | Eigener Speicherwert, löschbar; bleibt bei Werteeingabe stehen, herausnehmbar. → A2. |
| 15.10.2026 | P12 | Solo-Edition speichert nichts auf dem Server; einzige Verbindung = Video-Streaming. → A5. |
| 15.10.2026 | P14 | Eigene Fotos/Videos lokal **und** Streaming/Laden aus Fremdquelle. → A5, Abschnitt 4. |
| 15.10.2026 | Querformat: Sperre | Hochkant ist die Regel; drehen dürfen Ausdauer (live, Auswertung), GPS-Test, Messungs-Auswertung. `ui/ausrichtung.py`. Gebaut; T9. |
| 15.10.2026 | Querformat: Live-Vollbild | Knopf erzwingt quer (wie ein Videoplayer), Route `/live`; Kurvenwechsel über Pfeile + Liste **und** hoch/runter wischen (waagrecht bleibt die Zeit); eine Kurve je Seite: Tachogramm, dann je Gruppe der aktiven Verlaufskurven. Gebaut; T10. Ersetzt 16.10. (zwei Achsen, ohne Wischen). |
| 15.10.2026 | Querformat: Notizen | Textansicht nur hochkant; im Querformat Notiz **ohne Text** per rundem Symbol setzen und Marken mit dem Finger ziehen („Modifikation der Notizen und Abschnitte ist eine Hauptaufgabe im Querformat“). Notiz ohne Text steht hochkant als „(ohne Text — antippen)“ in der Liste. Gebaut; T10/T11. Ersetzt 16.10. (Text auch quer, Seitenleiste). |
| 15.10.2026 | Querformat: Auswertung | Vollbild als Modus in derselben Ansicht (kein Neubau, Editorzustand bleibt): Rohkurve groß, Editor daneben, Ablesewerte darunter; Abschnittsgrenzen und Marken ziehen. Gebaut; T11. Erweitert 16.10. (zwei Achsen, Seitenleiste, Etiketten). |
| 15.10.2026 | Querformat: Ausdauer | Zahlen links, Karte rechts in voller Höhe. Gebaut; T12. |
