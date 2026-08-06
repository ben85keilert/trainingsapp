# Datenschutz-Folgenabschätzung (Art. 35 DSGVO)

## Ist sie erforderlich?

**Sehr wahrscheinlich ja.** Art. 35 Abs. 3 lit. b nennt die umfangreiche
Verarbeitung besonderer Datenkategorien ausdrücklich. Gesundheitsdaten von
Patienten über eine mobile App fallen darunter.

Zusätzliche Risikomerkmale hier:

- besondere Datenkategorie (Art. 9)
- schutzbedürftige Betroffene (Patientenverhältnis, Abhängigkeit)
- neuartige Technik (kontinuierliche Sensormessung)
- Zusammenführung von Daten aus mehreren Quellen

## Zu beschreiben

1. **Verarbeitung und Zwecke** — siehe `10_verarbeitungsverzeichnis.md`
2. **Notwendigkeit und Verhältnismäßigkeit** — warum reicht Papier nicht?
3. **Risiken für die Betroffenen**
4. **Abhilfemaßnahmen**

## Risiken (Erstentwurf)

| Risiko | Auswirkung | Maßnahme |
|---|---|---|
| Unbefugter Zugriff auf den Server | Offenlegung von Gesundheitsdaten vieler Patienten | Verschlüsselung, Zugriffskonzept, Protokollierung, `40_toms.md` |
| Geräteverlust | Zugriff auf lokale Daten einer Person | Geräteverschlüsselung, app-privates Verzeichnis, kein Klartext-Token |
| Abfluss der HRV-Rohdaten | RR-Intervalle sind sensibler als Mittelwerte und potenziell wiedererkennbar | eigene Freigabe, standardmäßig **aus** |
| Fehlinterpretation der Werte | Verunsicherung, falsche Selbstbehandlung | keine Bewertung in Edition A, Hinweise, `00_zweckbestimmung.md` |
| Druck zur Teilnahme | Einwilligung nicht mehr freiwillig | Behandlung ausdrücklich unabhängig; Widerruf ohne Nachteil |
| Ungewollte Übertragung | Daten verlassen das Gerät ohne Wissen | Standard: keine Übertragung; sichtbare Anzeige des Synchronisationsstands |

## Vorabkonsultation

Bleibt trotz aller Maßnahmen ein hohes Restrisiko, ist die Aufsichtsbehörde vor
Beginn zu konsultieren (Art. 36).

## Fortschreibung

Bei jeder wesentlichen Änderung neu zu bewerten — insbesondere bei Anbindung
einer Hersteller-Cloud, bei neuen Datenarten und bei automatischer Auswertung.
