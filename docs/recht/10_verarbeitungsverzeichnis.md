# Verzeichnis von Verarbeitungstätigkeiten (Art. 30 DSGVO)

> Vorlage. Vor Inbetriebnahme von Edition B auszufüllen und laufend zu pflegen.

## Verantwortlicher

| | |
|---|---|
| Name, Anschrift | _(Praxis)_ |
| Vertreter | _(Inhaber)_ |
| Datenschutzbeauftragter | _(benannt? bei umfangreicher Verarbeitung von Gesundheitsdaten regelmäßig Pflicht — Art. 37 Abs. 1 lit. c)_ |

## Verarbeitungstätigkeit: „Trainingsassistent, Edition Praxis"

### Zwecke

Übungspläne zuweisen, Trainingsverlauf einsehen, Rückmeldung geben,
HRV-Messungen zur Verlaufsbeurteilung heranziehen.

### Kategorien betroffener Personen

Patientinnen und Patienten der Praxis.

### Kategorien personenbezogener Daten

| Kategorie | Beispiele | Besondere Kategorie (Art. 9)? |
|---|---|---|
| Stammdaten | Name, Geburtsjahr, Kennung | nein |
| Trainingsdaten | Übungen, Wiederholungen, Notizen | **ja** — Gesundheitsdaten |
| Messwerte | Herzfrequenz, RR-Intervalle, HRV-Kennzahlen | **ja** |
| Medien | selbst aufgenommene Übungsvideos, Fotos | **ja** |
| Tagesfelder | Beschwerden auf einer Skala, Einnahmen (Anzahl), Trinkmenge, Texte zu Themen wie Ernährung | **ja** — Gesundheitsdaten |
| Nachrichten | Text zwischen Patient und Therapeut | **ja** |
| Technische Daten | Gerätekennung, Zeitstempel, Protokolle | nein |

> **RR-Intervalle sind Rohdaten des Herzschlags.** Sie sind sensibler als ein
> Herzfrequenzmittelwert und potenziell biometrisch auswertbar. Entsprechend
> behandeln.

**Medien** (gebaut 20.10.2026, `docs/plan_anhaenge.md`): Fotos und Videos der eigenen
Übungsausführung, die die Person mit der Kamera der App an einen Trainingseintrag hängt —
oder seit 21.10.2026 aus der Fotoauswahl von Android hochlädt (P74): Die App bekommt nur
die gewählte Datei, verkleinert sie und speichert sie **ohne Ortsangabe** (Exif/GPS im Foto,
Ortsboxen im Video); die Kopie der Auswahl wird danach gelöscht. Zweck ausschließlich Dokumentation für die Person selbst (kein Vergleich, keine Bewertung
der Haltung durch die App). Speicherort: app-privater Speicher des Geräts
(`Anhaenge/<Jahr>/<Monat>/`), ohne Ortsstempel; sie gehen in **keinen** Export, kein
Geräte-Backup und keine Synchronisation — hinaus nur über „Teilen“ am einzelnen Bild, das
die Person selbst auslöst. Löschung jederzeit durch die Person, endgültig (Einstellungen →
Anhänge). Eine Übertragung an die Praxis gibt es nicht; käme sie, braucht sie eine eigene
Einwilligung (`20_einwilligung.md`).

**Tagesfelder** (gebaut 21.10.2026, `docs/plan_tagesfelder.md`): Werte, die die Person
selbst je Tag festhält — frei benannt, etwa Schmerz 0–10, Einnahmen eines Medikaments je
Dosis, Trinkmenge, Texte zur Ernährung. Zweck ausschließlich Dokumentation für die Person
selbst; die App bewertet nichts, zeigt keine Grenzen und erinnert an nichts
(`00_zweckbestimmung.md`). Speicherort wie die Trainingsdaten (Datenbank im app-privaten
Speicher, Tabellen `day_field`, `day_value`); sie folgen den Trainingsdaten in Geräte-Backup
(nur wenn eingeschaltet) und künftiger Synchronisation. Löschung durch die Person je Wert
oder je Feld „mit allen Einträgen“.

### Rechtsgrundlage

- Art. 9 Abs. 2 lit. a — **ausdrückliche Einwilligung** (der tragende Weg, siehe `20_einwilligung.md`)
- ergänzend Art. 9 Abs. 2 lit. h i. V. m. Art. 88 — Behandlung durch
  Berufsgeheimnisträger

### Empfänger

| Empfänger | Rolle | Grundlage |
|---|---|---|
| VServer-Hoster | Auftragsverarbeiter | AVV, `30_avv.md` |
| _(keine weiteren)_ | | |

Keine Übermittlung in Drittländer, solange keine Hersteller-Cloud-Schnittstelle
angebunden wird. **Wird eine angebunden** (Garmin, Fitbit, Oura, Whoop), ist
dieser Abschnitt neu zu bewerten — dann liegt in der Regel eine Übermittlung in
die USA vor.

### Löschfristen

| Daten | Frist |
|---|---|
| Trainings- und Messdaten | _(Aufbewahrungsfrist der Behandlungsdokumentation, § 630f BGB: 10 Jahre)_ |
| Nachrichten | _(festzulegen)_ |
| Technische Protokolle | 30 Tage |
| Daten nach Widerruf der Einwilligung | unverzüglich, siehe `60_betroffenenrechte.md` |

### Technische und organisatorische Maßnahmen

Siehe `40_toms.md`.
