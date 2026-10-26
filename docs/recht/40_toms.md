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
  Person (`docs/plan_gps.md`, Regel 0) — einzeln aus der Auswertung oder alle Strecken
  nach Rückfrage (seit 26.10.2026, Hinweis auf die eigene Verantwortung). Der
  Forschungsexport einer Einheit (ebenfalls nur ausdrücklich, seit 17.10.2026) und der
  Messungs-Export enthalten aus der Strecke nur Ortsfreies: das Tempo als 5-s-Mittel und
  seit 26.10.2026 die Rohspur ohne Ort — je Ortung Abstand zum vorigen Fix, Tempo, Höhe
  und Genauigkeit, nie Breite, Länge oder Richtung (`docs/kompatibilitaet.md` §13,
  `docs/plan_einheit.md` §8). Bei der Bluetooth-Berechtigung weiter
  `neverForLocation`. Verbindungen nach außen, alle abschaltbar und mit einmaligem
  Hinweis, nie mit eigenen Daten: die Karte holt Kacheln von OpenStreetMap (grobe
  Kachelkoordinaten); die Update-Prüfung fragt beim Start die GitHub-Releases der
  App und die eingetragenen Paketquellen nur nach Versionsnummern — übertragen
  werden IP-Adresse und der Name der App (`docs/uebungspakete.md`, „Paketquellen“;
  seit 16.10.2026). Ein Paket nimmt Updates nur von der Quelle an, die es zuletzt
  lieferte (seit 20.10.2026, Sicherheitsdurchsicht S3) — eine fremde Quelle kann
  mitgelieferte oder bereits installierte Inhalte nicht ersetzen.
- **Geräte-Backup** (seit 20.10.2026, Sicherheitsdurchsicht S4): Androids Auto Backup
  sichert nichts aus der App, solange die Person es nicht unter Einstellungen →
  Geräte-Backup einschaltet (Vorgabe aus; GPS-Strecken nur mit zweitem Schalter).
  Eingeschaltet gehen Datenbank, Messungen und Anhänge in das Backup des
  Google-Kontos — Empfänger Google, mit der Gerätesperre verschlüsselt, höchstens
  25 MB (`docs/sicherung.md`). Für iOS gilt dieselbe Regel (iCloud).
- **Bilder in Kurskapiteln** (seit 20.10.2026, S2): Markdown-Bilder aus Paketen laden
  erst, wenn die Person es unter Einstellungen → Updates einschaltet (Vorgabe aus);
  bis dahin stehen sie als Link, der auf Tipp öffnet. Beim Laden erfährt der Anbieter
  des Pakets IP-Adresse und Zeitpunkt.
- **Fotos und Videos an Einträgen** (seit 20.10.2026, `docs/plan_anhaenge.md`): mit der
  Kamera der App aufgenommen, als nackte JPEG/MP4-Bytes ohne Ortsstempel in den
  app-privaten Ordner `Anhaenge/` geschrieben; nicht in Galerie, Export, Diagnose,
  Synchronisation; ins Geräte-Backup nur, wenn die Person es einschaltet (unten).
  Hinaus nur über „Teilen“ am einzelnen Anhang nach Rückfrage.
  Drei Aufnahmequalitäten, mittlere als Vorgabe — Datensparsamkeit auch beim Speicherplatz;
  Speicherübersicht und endgültiges Löschen in Einstellungen → Anhänge.
- **Audioaufnahmen** (seit 22.10.2026, an Einträgen und an der Notiz zum Tag): mit dem
  Mikrofon der App aufgenommen, direkt in den app-privaten Ordner `Anhaenge/` geschrieben
  (bis „Behalten“ in `Anhaenge/.aufnahme/`, beim Verlassen ohne „Behalten“ gelöscht);
  dieselben Regeln wie für Fotos und Videos. Aufgenommen wird nur nach Tipp auf ● und nur,
  solange die Seite offen ist; Verlassen bricht die Aufnahme ab.
  **Hochladen** (seit 21.10.2026, P74): aus der Fotoauswahl von Android — keine
  Berechtigung für Fotos oder Speicher, die App sieht nur die gewählte Datei. Verkleinert
  auf die Qualitätsstufe (Videos höchstens zehn Minuten, feste Bitrate) und **ohne
  Ortsangabe**: Die Erweiterung `flet_hochladen` schreibt Fotos ohne Exif und Videos ohne
  Ort, die App prüft beides noch einmal (`jpeg_ohne_metadaten`, `mp4_ort_entfernen`). Die
  Kopie der Auswahl (trägt den Ort des Originals) wird gleich nach dem Verkleinern gelöscht;
  wird die App dabei beendet, bleibt sie app-privat im Cache, bis Android ihn leert.
- **Bluetooth-Adresse des Sensors** (seit 20.10.2026, Sicherheitsdurchsicht S10): Die
  Messdatei auf dem Gerät hält die Adresse (MAC/UUID) des Brustgurts oder der Uhr fest,
  damit sich das Gerät wiedererkennen lässt. Sie ist eine Gerätekennung, über die sich
  Messungen einer Person zusammenführen ließen — darum verlässt sie das Gerät nicht:
  Der Export einer Messung, der Forschungsexport einer Einheit und das geteilte
  Verbindungsprotokoll enthalten die Kopie ohne das Feld `adresse` bzw. mit maskierter
  Adresse (`core/hrv_export.py`, `docs/kompatibilitaet.md`, „Export“).
- **Vorgabe-Paketquelle** `trainingsapp.osteo-ebert.de` (seit 16.10.2026; Übergang,
  bis die Website der App steht): ein angemieteter Server in Deutschland, den der
  Hersteller selbst betreibt; Anbieter Hetzner Online GmbH, mit Vertrag zur
  Auftragsverarbeitung nach Art. 28 DSGVO. Der Server hält je Abruf IP-Adresse,
  Zeitpunkt, abgerufene Adresse, Antwort und den Namen der App
  (`trainingsapp-pakete`) in einem Protokoll fest; es wird täglich bereinigt und
  nach höchstens sieben Tagen gelöscht. Ein Programm zur Angriffserkennung
  (CrowdSec) prüft das Protokoll ausschließlich auf diesem Server; IP-Adressen gehen
  nicht an Dritte. Dieselben Angaben wie in der Datenschutzerklärung von
  osteo-ebert.de (Server-Protokolle, Hosting).

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
