# flet-ble

Flet-Erweiterung (Flet ≥ 1.0.3) für die trainingsapp: **Bluetooth Low Energy auf Android** als
Flet-Service. Grund: `bleak` läuft unter Flets Android-Laufzeit (serious_python) nicht
(`docs/tutorial/L02b_aufs_handy/`).

Bewusst generisch — scannen, verbinden, koppeln, Dienste entdecken, MTU anfragen, lesen,
schreiben, Notifications/Indications abonnieren. Über die Brücke gehen **rohe Bytes**; die
Protokolle (Heart Rate 0x2A37, Polar PMD) parst die App in Python (`trainingsapp.devices`).

- Flutter-Seite: `src/flutter/flet_ble` (Service `FletBleService`, Paket `flutter_blue_plus` **1.36.8**)
- Python-Seite: `src/flet_ble` (`FletBle`, ein `ft.Service`)

```python
from flet_ble import FletBle, verfuegbar

def bei_wert(e):                       # synchron halten — dann bleibt die Reihenfolge erhalten
    print(e.characteristic, e.value.hex(), e.seq, e.t_mono_us)

if verfuegbar(page):                   # nur in der gebauten Android-App
    ble = FletBle(on_notification=bei_wert)        # in main(page) anlegen, Referenz behalten!
    treffer = await ble.scan(8.0, services=["180d"])
    mtu = await ble.connect(treffer[0].id)
    await ble.discover_services(treffer[0].id)
    await ble.subscribe(treffer[0].id, "180d", "2a37")
```

**Messen im Hintergrund:** `await ble.hintergrund_starten("HRV-Messung läuft", "Verbunden mit …")`
startet einen Android-Vordergrunddienst (`android/…/MessDienst.java`, Typ `connectedDevice`) mit
dauerhafter Benachrichtigung und Wake-Lock; `hintergrund_beenden()` stoppt ihn, erneutes
`hintergrund_starten` ändert nur den Text. Dafür ist das Flutter-Paket zugleich ein
**Android-Plugin** (Java, `FletBlePlugin`, Kanal `flet_ble/hintergrund`) — nur so landet der
`<service>`-Eintrag samt Berechtigungen per Manifest-Merger in der App; die Flet-Vorlage kann
keine Dienste eintragen. Nur aus dem Vordergrund starten (Android 12+).

**Die Benachrichtigung** (seit 16.10.2026) zeigt, was läuft: `hintergrund_starten` und
`hintergrund_text` nehmen außer Titel und Text auch `lang` (ausgeklappt, eine Zeile je
Tätigkeit) und `seit_ms` (Beginn in ms seit 1970 — Android zählt ab da eine Stoppuhr im Kopf).
`benachrichtigung_zeigen(...)` zeigt dieselbe Benachrichtigung **ohne** Dienst (etwa nur für den
Timer; hält nichts am Leben), `benachrichtigung_verbergen()` nimmt sie weg. In der Statusleiste
steht ein eigenes, einfarbiges Symbol (`res/drawable/ic_stat_trainingsapp.xml`). Der Kanal
`laufend` hat die Wichtigkeit „Standard“ ohne Ton und Vibration: Benachrichtigungen mit
„niedrig“ gelten als still, und stille zeigt die Statusleiste (Pixel) nicht als Symbol — der
frühere Kanal `hrv_messung` wird beim ersten Start gelöscht. Was hineinkommt, setzt die App
zusammen (`trainingsapp.ui.laufend`).

Stolperfallen:

- **Referenz halten.** Flet entfernt Dienste, auf die in Python niemand mehr zeigt, nach dem
  nächsten Ereignis — die Dart-Seite trennt dann alle Verbindungen.
- **Handler im Konstruktor übergeben**, sonst `update()` danach; ohne gesetztes `on_…` sendet
  Dart das Ereignis gar nicht.
- **Kein `from __future__ import annotations`** in Modulen mit Flet-Diensten/Ereignissen —
  Flet löst die `on_…`-Typen zur Laufzeit auf und scheitert an String-Annotationen.
- Fehler der Dart-Seite kommen als `RuntimeError`, abgelaufene Python-Fristen als `TimeoutError`.
- `flet run --android` (Flet-App am Handy) hat die Erweiterung nicht; nur `flet build apk`.
- Berechtigungen stehen in der `pyproject.toml` der App (`[tool.flet.android.permission]`,
  `BLUETOOTH_SCAN` mit `neverForLocation` — ohne das Flag filtert Android 12+ die
  Scan-Ergebnisse). flutter_blue_plus fragt die Laufzeitberechtigungen beim ersten Scan selbst an.

Dart prüfen:

```bash
cd erweiterungen/flet_ble/src/flutter/flet_ble
~/flutter/3.44.8/bin/flutter pub get && ~/flutter/3.44.8/bin/dart analyze
```

Java prüfen, ohne eine APK zu bauen (Android-SDK und Gradle-Cache wie auf Bens Rechner; `R` als
Stummel, weil die Ressourcen erst der Build erzeugt):

```bash
A=erweiterungen/flet_ble/src/flutter/flet_ble/android/src/main/java/de/praxisebert/flet_ble
C=~/.gradle/caches/modules-2/files-2.1; mkdir -p /tmp/fb/de/praxisebert/flet_ble
printf 'package de.praxisebert.flet_ble;\npublic final class R { public static final class drawable { public static int ic_stat_trainingsapp; } }\n' > /tmp/fb/de/praxisebert/flet_ble/R.java
javac --release 11 -d /tmp/fb/out -cp "$HOME/Android/sdk/platforms/android-36/android.jar:$(find $C -name 'flutter_embedding_release-*.jar' | head -1):$(find $C -name 'annotation-jvm-*.jar' | head -1)" /tmp/fb/de/praxisebert/flet_ble/R.java $A/*.java
```

## Lizenz von flutter_blue_plus — wichtig

> Darum überwacht Dependabot die Dart-Pakete nicht (`docs/dependabot.md`, „Dart-Pakete (pub)“):
> er würde den Sprung auf 2.x jede Woche vorschlagen.

`flutter_blue_plus` ist **exakt auf 1.36.8 gepinnt** (kein `^`). Das ist die letzte Version
unter **BSD-3-Clause**; sie pinnt ihre Plattformpakete (`flutter_blue_plus_android` 7.0.4 usw.)
selbst exakt, ebenfalls BSD-3-Clause. Ab **2.0.0** gilt die proprietäre „FlutterBluePlus
License": kostenlos nur für registrierte Gemeinnützige, Bildungseinrichtungen und
Privatpersonen; jede gewinnorientierte Nutzung — auch Entwicklung und Test — braucht eine
Kauflizenz, `connect()` verlangt einen `license:`-Parameter, und der Build sendet Telemetrie
(Paketname, App-Name, Version). Für eine Praxis (gewinnorientiert) daher **nicht** auf 2.x
aktualisieren. Ausweg, falls 1.36.8 einmal nicht mehr baut: `flutter_reactive_ble`
(BSD-3-Clause) — die Python-API bleibt gleich, nur `ble_service.dart` ändert sich.
(Einschätzung Stand 2026-10, keine Rechtsberatung.)

Die Erweiterung selbst ist Teil der trainingsapp und steht unter deren Lizenz.
