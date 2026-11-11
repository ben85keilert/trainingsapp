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
- **Update in der App** (seit 9.11.2026, Katalog A8 Stufe 2, nur Android): Auf Tipp
  („Laden und installieren“) lädt die App die APK des neueren Releases selbst — nur von
  den Releases des eigenen GitHub-Repos, nur über https; GitHub (und sein Speicher, auf
  den es weiterleitet) sieht IP-Adresse und den Namen der App, wie vorher der Browser.
  Größe und SHA-256 werden gegen GitHubs Angaben geprüft; die APK liegt im Cache der App
  und wird nach dem Update gelöscht. Android installiert sie nur, wenn sie mit
  **demselben Schlüssel** signiert ist wie die installierte App — eine untergeschobene APK
  wird abgelehnt. Berechtigungen `REQUEST_INSTALL_PACKAGES` (Android fragt einmal je App)
  und `UPDATE_PACKAGES_WITHOUT_USER_ACTION` (ab Android 12 ohne Rückfrage je Update).
  Nie, solange eine Messung, Einheit, ein Training oder Timer läuft.
  **Von selbst** (seit 9.11.2026, Schalter „Updates der App von selbst installieren“ unter
  Einstellungen → Updates, Vorgabe an, beim ersten Mal ein Hinweis mit „Ausschalten“): Findet
  die Prüfung beim Start ein neueres Release, lädt die App es nur im WLAN (Android meldet das
  Netz als nicht getaktet, `ACCESS_NETWORK_STATE`) — dieselbe Verbindung wie auf Tipp, nichts
  geht zusätzlich hinaus. Installiert wird erst, wenn die App eine Minute im Hintergrund war,
  kein Formular offen ist und nichts läuft (Wecker von Android, nicht exakt). Danach eine
  Benachrichtigung „aktualisiert, antippen zum Öffnen“ (nur nach Updates aus der App, ohne
  Ton). Scheitert ein Release (fremde Signatur, Android lehnt ab), versucht die App es nicht
  wieder von selbst.
- **Geräte-Backup** (seit 20.10.2026, Sicherheitsdurchsicht S4): Androids Auto Backup
  sichert nichts aus der App, solange die Person es nicht unter Einstellungen →
  Geräte-Backup einschaltet (Vorgabe aus; GPS-Strecken nur mit zweitem Schalter).
  Eingeschaltet gehen Datenbank und Messungen in das Backup des
  Google-Kontos — Empfänger Google, mit der Gerätesperre verschlüsselt, höchstens
  25 MB (`docs/sicherung.md`). **Anhänge, Paketdateien, Karten, Import/ und Export/ gehen
  nie mit** (seit 11.11.2026, P180). Für iOS gilt dieselbe Regel (iCloud).
- **Bilder in Kurskapiteln** (seit 20.10.2026, S2): Markdown-Bilder aus Paketen laden
  erst, wenn die Person es unter Einstellungen → Updates einschaltet (Vorgabe aus);
  bis dahin stehen sie als Link, der auf Tipp öffnet. Beim Laden erfährt der Anbieter
  des Pakets IP-Adresse und Zeitpunkt.
- **Private Pakete** (seit 9.11.2026, U7, `docs/uebungspakete.md`; Nachtrag 11.11.2026, S33/S34):
  Pakete für eine einzelne Person liegen verschlüsselt unter einem Link mit Zufallsnamen und
  öffnen sich nur mit einem 8-stelligen Code. **In ein Paket gehören keine Personendaten** —
  keine Diagnose, kein voller Name; „für“ ist ein Vorname oder Kürzel. Der Code steht nach dem
  ersten Öffnen im Klartext in der Datenbank der App (`package.access_json`, bei eigenen
  Paketen `own_package.access_code`), damit Updates sich selbst öffnen; er steht in keinem
  Protokoll und keinem Export, geht aber **mit der Datenbank ins Geräte-Backup**, wenn die
  Person es einschaltet. Keine neue Netzverbindung (dieselbe Paketquelle).
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
- **Diagnosemodus** (seit 4.11.2026, `docs/plan_diagnosemodus.md`, beide Editionen): neue
  Datenarten nur auf ausdrücklichen Start je Messung — der **Rohmitschnitt** aller
  Bluetooth-Pakete des gewählten Geräts (`sensor_<ts>_mitschnitt.jsonl`, beim Polar H10 mit
  EKG und **Beschleunigung des Gurts**), **Marken** (Wiederholung, Atemzug, Störung) mit dem
  Kontext der Übung und Zustandsproben (Akku von Gurt und Handy, Verzug der App). Ohne Messung
  die **Geräteprobe** eines unbekannten Geräts (`Diagnose/<ts>_<Modell>/`). Solange
  aufgezeichnet wird, blinkt oben rechts ein roter Punkt; in der Benachrichtigung steht
  „● Diagnose“. Keine Netzverbindung, kein GPS, keine anderen Geräte in der Nähe; die App
  liest nie Seriennummer und Systemkennung und schreibt bei der Geräteprobe nie auf das Gerät.
  Die Beschleunigung des Gurts enthält keine Himmelsrichtung (kein Gyroskop, kein
  Magnetometer) — keine Koppelnavigation. Hinaus nur über „Teilen“ bzw. den Export, dann
  bereinigt (Adressen maskiert, Gerätename auf das Modell gekürzt, Kennungs-Merkmale entfernt;
  `hrv_core.deid.mitschnitt_zeilen`). Aufbewahrung bis zum Löschen; Einstellungen → HRV-Messung
  → Diagnosemodus zeigt Zahl und Größe und löscht alles auf einmal, die Auswertung den
  einzelnen Mitschnitt; nach dem Teilen fragt die App, ob er weg darf (P114). Geräteproben
  mit dem Puls einer anderen Person nur mit deren Einwilligung weitergeben; Proben anderer
  kommen nie in ein Repository (P115).
- **Beschleunigungssensor in Übungen** (seit 4.11.2026, `docs/plan_beschleunigung.md` §8 und
  §10, beide Editionen): Zählt der Sensor die Wiederholungen einer Übung („Wdh. zählen“),
  schaltet die App die Beschleunigung des Geräts erst mit dem Tipp ein und mit dem Ende des
  Zählens wieder aus. Sie rechnet live und speichert im Alltag nur **abgeleitete
  Bewegungsdaten**: die Wiederholungen je Satz mit den Zeiten, zu denen sie gezählt wurden,
  die Korrekturen ±1 mit Zeit, den Grund des Endes und das Gerätemodell (Zeitleiste der
  Einheit), dazu die Zahl im Trainingseintrag — gekennzeichnet als Prototyp. **Keine Rohdaten
  der Beschleunigung:** Die Proben liegen nur in einem Puffer im Arbeitsspeicher, der mit dem
  Ende des Zählens geleert wird; auf den Speicher kommen sie nur im Diagnosemodus (oben). Keine
  Richtung, kein Ort, keine neue Netzverbindung. Die Daten bleiben auf dem Gerät; hinaus gehen
  sie wie die übrige Zeitleiste nur mit dem ausdrücklichen Forschungsexport einer Einheit
  (`einheit-v1`) und mit dem Geräte-Backup, wenn die Person es einschaltet.
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
