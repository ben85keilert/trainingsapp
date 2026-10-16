# Technische und organisatorische Maßnahmen (Art. 32 DSGVO)

## Verschlüsselung

| Wo | Maßnahme | Stand |
|---|---|---|
| Übertragung | TLS 1.3, Zertifikatsprüfung, kein Fallback | geplant |
| Ruhend, Server | Festplattenverschlüsselung + verschlüsselte Datenbank | geplant |
| Ruhend, Gerät | app-privates Verzeichnis; Geräteverschlüsselung des Betriebssystems | teilweise |
| Zugangsdaten | `flet-secure-storage` (Keychain / Android Keystore) — **nie** im Klartext | geplant |

> **Zu prüfen:** Ende-zu-Ende-Verschlüsselung der Nachrichten. Sie würde den
> Serverbetreiber vollständig aus der Kenntnisnahme herausnehmen und die
> Anforderungen aus § 203 StGB deutlich entspannen. Kostet Schlüsselverwaltung
> und erschwert Wiederherstellung nach Geräteverlust.

## Zugriff

- Anmeldung am Server mit persönlichem Konto, kein geteiltes Praxiskonto
- Zweiter Faktor für den Therapeutenzugang
- Ein Patient sieht ausschließlich eigene Daten — serverseitig erzwungen,
  nicht nur in der Oberfläche
- Zugriffsprotokoll: wer hat wann welchen Datensatz gelesen

## Datensparsamkeit

- Standardmäßig wird **nichts** übertragen. Jede Datenart braucht eine eigene
  Freigabe (`20_einwilligung.md`)
- Rohdaten der HRV nur bei ausdrücklicher Freigabe — Kennzahlen genügen meist
- Standortdaten verlassen das Gerät nicht: Strecken (Ausdauertraining, seit
  14.10.2026) liegen getrennt von den Messungen und gehen weder in Export,
  Synchronisation noch Diagnose; hinaus nur per ausdrücklichem GPX-Export der
  Person (`docs/plan_gps.md`, Regel 0). Bei der Bluetooth-Berechtigung weiter
  `neverForLocation`. Verbindungen nach außen, alle abschaltbar und mit einmaligem
  Hinweis, nie mit eigenen Daten: die Karte holt Kacheln von OpenStreetMap (grobe
  Kachelkoordinaten); die Update-Prüfung fragt beim Start die GitHub-Releases der
  App und die eingetragenen Paketquellen (Vorgabe: der Server des Herstellers) nur
  nach Versionsnummern — übertragen werden IP-Adresse und der Name der App
  (`docs/uebungspakete.md`, „Paketquellen“; seit 16.10.2026).

## Verfügbarkeit

- Tägliche Sicherung, verschlüsselt, getrennt vom Produktivsystem
- Wiederherstellung mindestens jährlich erproben — eine ungeprüfte Sicherung ist
  keine Sicherung
- Die App bleibt ohne Serververbindung voll funktionsfähig; sie ist ein
  eigenständiger Datenspeicher, kein Anzeigegerät

## Löschkonzept

| Anlass | Wirkung |
|---|---|
| Widerruf einer Freigabe | Übertragung stoppt sofort; serverseitige Daten dieser Art werden gelöscht |
| Löschverlangen (Art. 17) | vollständige Löschung, soweit keine Aufbewahrungspflicht entgegensteht |
| Ende der Behandlung | Aufbewahrung nach § 630f BGB, danach Löschung |
| Kontolöschung | Daten weg, `tombstone` behält nur ID und Zeitstempel |

> **Der Zielkonflikt, ausdrücklich aufgelöst:** Die Synchronisation braucht eine
> Spur des Gelöschten, damit andere Geräte nachziehen. In `tombstone` stehen
> deshalb ausschließlich Kennung und Zeitpunkt — **niemals Gesundheitsdaten**.

## Verletzungen des Schutzes personenbezogener Daten

Meldung an die Aufsichtsbehörde binnen **72 Stunden** (Art. 33), bei hohem
Risiko zusätzlich an die Betroffenen (Art. 34). Meldeweg und Zuständigkeit
schriftlich festhalten, **bevor** etwas passiert.
