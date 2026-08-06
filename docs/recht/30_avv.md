# Auftragsverarbeitung (Art. 28 DSGVO)

## Wann nötig

Sobald ein Dritter personenbezogene Daten **in unserem Auftrag** verarbeitet.
Für Edition B trifft das mindestens auf den Betreiber des VServers zu — auch
dann, wenn er die Daten nie ansieht: Der Zugriff auf die Infrastruktur genügt.

**Ohne unterzeichneten Vertrag darf kein Patientendatensatz auf den Server.**

## Checkliste je Auftragsverarbeiter

- [ ] Vertrag nach Art. 28 Abs. 3 geschlossen
- [ ] Verarbeitung ausschließlich innerhalb der EU/des EWR
- [ ] Technische und organisatorische Maßnahmen dokumentiert und geprüft
- [ ] Unterauftragsverhältnisse benannt und genehmigt
- [ ] Regelung zu Löschung und Rückgabe nach Vertragsende
- [ ] Meldeweg bei Datenschutzverletzungen (Art. 33: 72 Stunden!)
- [ ] Im Verarbeitungsverzeichnis eingetragen

## Aktuell vorgesehen

| Dienstleister | Leistung | Sitz | AVV | Status |
|---|---|---|---|---|
| _(VServer-Hoster)_ | Hosting der Praxisdatenbank | _(EU?)_ | ☐ | offen |

## Wenn später Hersteller-Cloud-APIs dazukommen

Garmin, Fitbit/Google, Oura, Whoop und Withings sitzen in den USA. Eine
Anbindung bedeutet in aller Regel eine **Drittlandsübermittlung von
Gesundheitsdaten** und braucht:

- Prüfung des EU-US Data Privacy Framework bzw. Standardvertragsklauseln
- ein Transfer Impact Assessment
- ausdrückliche Aufnahme in Einwilligung und Verarbeitungsverzeichnis

Das ist der Grund, warum der Plan diese Anbindungen bewusst hinten anstellt und
zuerst auf BLE und Dateiimport setzt: dabei verlässt kein Datum das Gerät.
