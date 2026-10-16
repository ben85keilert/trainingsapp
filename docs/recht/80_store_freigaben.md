# Freigaben in den App-Stores

> **Auslieferungsblocker, kein Papierkram.** Beide Stores prüfen
> Gesundheits-Apps gesondert. Eine falsche oder fehlende Angabe ist ein
> Ablehnungsgrund — und fällt erst auf, wenn alles fertig ist.

## Google Play

### Erklärung für Gesundheits-Apps

Vor der Veröffentlichung ist das „Health apps declaration form" auszufüllen.
**Seit Januar 2026 verschärft:** Kennzeichnung als Medizinprodukt, und je
genutztem Health-Connect-Datentyp eine Begründung.

Auch wenn wir Health Connect zunächst nicht nutzen, gilt die Erklärungspflicht
für die Verarbeitung von Gesundheitsdaten.

### Datensicherheitsabschnitt

Vollständig und wahrheitsgemäß:

| Frage | Unsere Antwort |
|---|---|
| Werden Daten erhoben? | Edition A: nein (alles bleibt auf dem Gerät). Edition B: ja |
| Werden Daten geteilt? | nein |
| Verschlüsselte Übertragung? | ja |
| Löschung anforderbar? | ja |
| Kategorien | Gesundheit und Fitness |

Die beiden Editionen sind getrennte Einträge im Store mit **unterschiedlichen**
Angaben. Ein gemeinsamer Eintrag wäre für Edition A falsch.

### Berechtigungen

| Berechtigung | Begründung |
|---|---|
| `BLUETOOTH_SCAN` (mit `neverForLocation`) | Herzfrequenzsensor finden |
| `BLUETOOTH_CONNECT` | mit dem Sensor verbinden |
| Foreground Service (`connectedDevice`) | Messung läuft weiter, wenn der Bildschirm aus ist |
| `POST_NOTIFICATIONS` | Benachrichtigung, solange etwas läuft (Messung, Training, Timer) — mit Zeit, ohne Ton und ohne Ortsangaben |
| `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION` (seit 14.10.2026) | Strecke beim Ausdauertraining aufzeichnen (Gehen, Laufen, Rad) — nur während eines Trainings oder GPS-Tests, nur auf dem Gerät gespeichert, nie übertragen |
| Foreground Service (`location`) | GPS läuft weiter, wenn der Bildschirm aus ist |
| `INTERNET` | Kartenkacheln (OpenStreetMap), verlinkte Videos, Update-Prüfung (GitHub-Releases der App, Paketquellen — nur Versionsnummern, abschaltbar, Hinweis beim ersten Mal); keine eigenen Daten |

`neverForLocation` bleibt bei Bluetooth: Die Standortberechtigung gilt dem
Ausdauertraining, nicht dem Sensor. Im Store-Formular „Standort“ ehrlich
angeben: erhoben, nicht geteilt, nicht zu Werbezwecken, Löschung durch die
Person. Die Datenschutzerklärung nennt die Kartenkacheln (grobe
Kachelkoordinaten an OpenStreetMap, abschaltbar).

### Datenschutzerklärung

URL in Store-Eintrag, App und Website muss **identisch** sein.

## Apple App Store

### Richtlinie 5.1.3

- Keine Nutzung von HealthKit-Daten für Werbung oder Data-Mining
- **Keine Speicherung von HealthKit-Daten in iCloud**
- Datenschutzerklärung verpflichtend
- Bei medizinischen Aussagen deutlich strengere Prüfung — ein weiterer Grund,
  die Zweckbestimmung sauber zu halten (`00_zweckbestimmung.md`)

### Info.plist

`NSBluetoothAlwaysUsageDescription` mit einer Begründung, die ein Mensch
versteht — nicht „App benötigt Bluetooth".

Bei späterer HealthKit-Nutzung zusätzlich `NSHealthShareUsageDescription` und
`NSHealthUpdateUsageDescription`.

### Voraussetzung

Apple-Developer-Programm, 99 USD im Jahr. **Ohne das kein Test auf einem echten
Gerät und kein TestFlight.** Deshalb steht iOS im Plan hinter Android.

## Checkliste vor der ersten Veröffentlichung

- [ ] Zweckbestimmung formuliert und im Store-Text konsistent
- [ ] Datenschutzerklärung veröffentlicht, URL überall gleich
- [ ] Google-Play-Erklärung für Gesundheits-Apps eingereicht
- [ ] Datensicherheitsabschnitt je Edition getrennt ausgefüllt
- [ ] Berechtigungen begründet, `neverForLocation` gesetzt
- [ ] Pflichthinweise beim ersten Start eingebaut
- [ ] Altersfreigabe festgelegt
