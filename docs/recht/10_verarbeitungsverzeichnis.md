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
| Nachrichten | Text zwischen Patient und Therapeut | **ja** |
| Technische Daten | Gerätekennung, Zeitstempel, Protokolle | nein |

> **RR-Intervalle sind Rohdaten des Herzschlags.** Sie sind sensibler als ein
> Herzfrequenzmittelwert und potenziell biometrisch auswertbar. Entsprechend
> behandeln.

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
