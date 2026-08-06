# Einwilligung in die Verarbeitung von Gesundheitsdaten

> Vorlage. Der Text ist vor Verwendung juristisch zu prüfen.

## Anforderungen

Für Gesundheitsdaten braucht es eine **ausdrückliche** Einwilligung
(Art. 9 Abs. 2 lit. a DSGVO). Sie muss:

- **freiwillig** sein — die Behandlung darf nicht davon abhängen
- **informiert** sein — verständlich, ohne Fachjargon
- **bestimmt** sein — je Datenart getrennt, nicht pauschal
- **nachweisbar** sein — Zeitpunkt und Textfassung protokollieren
- **jederzeit widerrufbar** sein, so einfach wie die Erteilung

Deshalb im Code: Tabelle `consent` mit `scope`, `granted_at`, `revoked_at` und
`text_version`. Eine Zeile je Datenart, nicht eine für alles.

## Granulare Freigaben

In der App einzeln zu bestätigen:

| Freigabe (`scope`) | Was geteilt wird |
|---|---|
| `training` | Welche Übungen wann und wie ausgeführt wurden |
| `hrv_kennzahlen` | Berechnete Werte: Herzfrequenz, RMSSD, SDNN … |
| `hrv_rohdaten` | Die einzelnen Schlagabstände (RR-Intervalle) |
| `medien` | Selbst aufgenommene Fotos und Videos |
| `nachrichten` | Textnachrichten an die Praxis |

`hrv_rohdaten` bewusst getrennt von `hrv_kennzahlen`: Rohdaten sind deutlich
sensibler und für die meisten Zwecke nicht erforderlich.

## Textvorlage

> **Einwilligung in die Übermittlung meiner Trainings- und Gesundheitsdaten**
>
> Ich möchte, dass die Praxis _(Name)_ meinen Trainingsverlauf einsehen kann,
> um mich besser zu begleiten. Dazu werden die von mir freigegebenen Daten
> verschlüsselt an einen Server der Praxis übertragen und dort gespeichert.
>
> Ich entscheide selbst, welche Daten das sind, und kann jede Freigabe einzeln
> erteilen und jederzeit zurücknehmen. Ohne Freigabe bleiben alle Daten auf
> meinem Gerät.
>
> Mir ist bekannt:
> - Die Teilnahme ist freiwillig. Meine Behandlung hängt nicht davon ab.
> - Ich kann meine Einwilligung jederzeit ohne Angabe von Gründen widerrufen.
>   Der Widerruf gilt ab dem Zeitpunkt, an dem er eingeht; bis dahin erfolgte
>   Verarbeitungen bleiben rechtmäßig.
> - Nach dem Widerruf werden meine übertragenen Daten gelöscht, soweit keine
>   gesetzliche Aufbewahrungspflicht entgegensteht. Auf meinem Gerät bleiben
>   sie erhalten, bis ich sie dort selbst lösche.
> - Ich habe ein Recht auf Auskunft, Berichtigung, Löschung, Einschränkung der
>   Verarbeitung und Datenübertragbarkeit sowie ein Beschwerderecht bei einer
>   Aufsichtsbehörde.
>
> Ich gebe frei: ☐ Training ☐ HRV-Kennzahlen ☐ HRV-Rohdaten ☐ Medien ☐ Nachrichten

## Widerruf in der App

- Erreichbar in **einem** Schritt aus den Einstellungen — nicht versteckt
- Wirkt sofort: keine weitere Übertragung
- Löst die Löschung auf dem Server aus (`60_betroffenenrechte.md`)
- Die lokalen Daten bleiben. Das ist ausdrücklich zu erklären, sonst entsteht
  der Eindruck, ein Widerruf lösche die eigenen Aufzeichnungen.

## Minderjährige

Bei Patienten unter 16 Jahren ist die Einwilligung der Sorgeberechtigten
erforderlich (Art. 8 DSGVO). _(Verfahren festlegen.)_
