# Gerätekompatibilität: welche Pulsmesser über Bluetooth LE laufen

Welche Brustgurte, Sensoren, Uhren und Wearables sich über die **bestehende
BLE-Verbindung** mit der Trainingsapp (Android) und mit `praxis_gui` (Desktop)
nutzen lassen — und welche nicht.

- **Stand:** 2026-10-13
- **Am Gerät getestet:** nur Polar H10 und Polar Verity Sense. Alles andere ist
  eine Einstufung nach Aktenlage (Web-Recherche vom 13.10.2026: Herstellerseiten,
  Kompatibilitätslisten von HRV-Apps, Tests von DC Rainmaker, the5krunner, Marco
  Altini, Foren). Die Quellen sind verlinkt, aber nicht jede einzeln nachgeprüft;
  einige waren nur als Suchauszug lesbar.
- **Abgrenzung:** [`kompatibilitaet.md`](kompatibilitaet.md) ist der
  *Datenformat*-Vertrag mit praxis_gui. Hier geht es um *Hardware*.

> Herstellerangaben zu RR-Intervallen sind unzuverlässig (siehe
> [`architektur.md`](architektur.md), „Sensor-Prüfstand"). Eine Einstufung hier
> ersetzt keinen Test — sie sagt, **wo sich ein Test lohnt und wo nicht**.

---

## 1. Was ein Gerät können muss

Beide Programme sprechen ausschließlich **Bluetooth Low Energy** — die App über
die eigene Erweiterung `flet_ble` (flutter_blue_plus), praxis_gui über `bleak`.
Was sie lesen, ist identisch: das Standardprofil „Heart Rate" plus, bei Polar,
das herstellereigene PMD.

| | Anforderung | Wenn nicht erfüllt |
|---|---|---|
| **A1** | **Bluetooth LE** („Bluetooth Smart", ab BT 4.0) | ANT+, 5-kHz-Analog (Polar T31/T34, codierte Gurte), Bluetooth Classic, USB: **keine Verbindung** |
| **A2** | **Heart Rate Service `0x180D`**, Messwert **`0x2A37`** per Notification über eine GATT-Verbindung — offen, ohne Hersteller-SDK | Puls nur in der Hersteller-App/Cloud oder nur im Advertising (Polar „HF für andere Geräte sichtbar"): **keine Verbindung** |
| **A3** | **RR-Intervalle im `0x2A37`-Paket** (Flags-Byte Bit 4 = `0x10`) | Verbindung steht, Messung läuft, aber **nur Puls** (`bpm_only`) — keine HRV |
| A3′ | *Ausnahme Polar:* Intervalle über **PMD** — PPI (Verity Sense, OH1, Polar-Uhren mit SDK-Freigabe), EKG (H10) | ohne PMD nur das, was `0x2A37` hergibt |
| **A4** | **Freie BLE-Verbindung.** Viele Geräte nehmen nur 1 (manche 2–3) BLE-Verbindungen an; ANT+ zählt nicht mit | Hält eine Uhr, die Hersteller-App oder Zwift die Verbindung, **taucht das Gerät im Scan nicht auf** |
| **A5** | Bei Uhren und Bändern: **Übertragung einschalten** („HF übertragen", „Broadcast", „HR on Equipment"), oft nur im Training | sonst unsichtbar |
| **A6** | **Kopplung**, falls verlangt — beide Programme können koppeln (App: Android `createBond`; praxis_gui: eigener BlueZ-Agent). Garmin HRM 200/600 im **„open"**-Modus | Abbruch nach wenigen Sekunden oder verschlüsselte Characteristic nicht lesbar |
| **A7** | RR-Werte in **1/1024 s**, wie die Norm es verlangt | falsche Intervalle (Verdacht bei Whoop, §4.6) |

**Optische Sensoren** (Armband, Ohr-/Fingerclip, Uhr) liefern im RR-Feld
**Puls-zu-Puls-Intervalle (PPI)**, keine RR aus dem EKG. Das Paket verrät das
nicht — nur das Geräteprofil kennt die Bauart. Siehe §6, Befund 1.

### Plattform

| | Trainingsapp | praxis_gui |
|---|---|---|
| Rechner/Handy | Android mit BLE, APK nur **arm64-v8a**; Bluetooth nur in der gebauten APK, nicht in `flet run --android` | PC mit BLE-Adapter; **Linux (BlueZ) erprobt**, Windows/macOS eingebaut, ungetestet (praxis_gui `docs/geraete.md` §5) |
| Berechtigungen | Android 12+: „Geräte in der Nähe"; ≤ 11: Standort | — |
| iOS | Erweiterung grundsätzlich iOS-fähig, aber nicht gebaut, nicht getestet | — |

### Wo sich App und praxis_gui unterscheiden

| | Trainingsapp | praxis_gui |
|---|---|---|
| Standardgurte (`0x2A37` + RR) | ja | ja |
| H10-EKG (PMD, 130 Hz) | nein — nur RR über `0x2A37` | ja |
| Verity-Sense-PPI (PMD) | ja | ja |
| Polar-Uhren-PPI | Profil `polar_watch` vorhanden, ungetestet | kein Uhrenprofil; die PMD-Erkennung könnte greifen, ungeprüft |
| Uhren-Broadcast | Profil `watch_broadcast` (als PPG gekennzeichnet) | kein Profil → läuft als „Brustgurt" und wird als **EKG** gekennzeichnet |
| Mehrere Geräte gleichzeitig | nein | ja (H10 als Referenz + Prüfling) |

Steht in den Tabellen unten in der Spalte „praxis_gui" ein **=**, gilt dasselbe
wie für die App.

---

## 2. Legende

| Zeichen | Bedeutung |
|---|---|
| ✅ | **getestet** — am Gerät mit dieser App bzw. praxis_gui geprüft |
| 🟢 | **sicher** — RR über BLE belegt (Herstellerangabe „RR über Bluetooth" oder unabhängiger Test mit einer reinen BLE-App), hier noch nicht getestet |
| 🔵 | **wahrscheinlich** — nur indirekt belegt (Kompatibilitätsliste einer HRV-App, Händlertext, Schwestermodell) |
| 🟡 | **unsicher** — BLE-Puls vorhanden oder möglich, RR unbelegt oder widersprüchlich |
| 🟠 | **nur Puls** — verbindet, aber belegt ohne (brauchbare) RR → keine HRV |
| 🔴 | **sicher nicht** — kein BLE-Puls (nur ANT+/analog/Classic/USB/proprietär/Cloud) oder gar kein Pulssensor |

Zusatzmarken:

- **⚠P** — optischer Sensor, der PPI im RR-Feld schickt. Läuft, wird aber derzeit
  als `rr_ekg` gekennzeichnet (§6, Befund 1).
- **¹** — nur **eine** BLE-Verbindung gleichzeitig (A4).

---

## 3. Anbieter im Überblick

| Anbieter | Sparte | Beste Wahl für HRV hier |
|---|---|---|
| **Polar** | Gurte, optische Sensoren, Uhren; Apps Flow/Beat | **H10 ✅**, **Verity Sense ✅**, H9 🟢, H7 🟢 |
| **Garmin** | Gurte, Uhren; App Connect | HRM-Pro 🟢, HRM 600 🟢 |
| **Wahoo** | Gurte, Armband, Uhr | TICKR (Gen 2) 🟢, TICKR X (Gen 2) 🟢 |
| **Suunto** | Gurte, Uhren | Smart Sensor 🟢, Smart Belt 🟢 |
| **Movesense** | Sensorplattform (Suunto-Ausgründung) | HR2 🟢, Medical 🟢, Flash 🟢 |
| **Sigma** | Gurte | R1 Blue/Duo Comfortex+ 🟢 |
| **Zephyr** | Gurte, Module | HxM Smart 🟢 |
| **Mindfield** | Sensor | eSense Pulse 🟢 |
| **Coospo** | Gurte, Armbänder | HW9 🟢⚠P; H6/H9Z/H808S 🔵 |
| **Magene** | Gurte | H603/H64 🔵 |
| **4iiii** | Gurt | Viiiiva 🔵 |
| **Kyto** | Ohr-/Fingerclips, Gurte | HRM-2935/2936 🟢⚠P |
| **Scosche** | optische Armbänder | Rhythm24 (nur HRV-Modus) 🟢⚠P |
| **Elite HRV** | App + Fingersensor | CorSense 🟢⚠P (nicht mehr erhältlich) |
| **HeartMath** | App + Ohrclips | Inner Balance BT / Coherence Plus 🔵⚠P |
| **Optimal HRV** | App + Armband | HRV Monitor 2.0 🔵 |
| **Whoop** | Band + App | Whoop 5.0 🟢 (⚠ RR-Einheit) |
| **Biostrap** | Band, B2B-Sensor | Kairos 🟢 (kaum erhältlich) |
| Coros, Decathlon, Myzone, Peloton, Moofit, XOSS, iGPSport, Bryton, Lezyne, Beurer, Fourth Frontier, Morpheus | Gurte, Armbänder, Uhren | nichts sicher — 🟡/🟠 |
| Amazfit/Zepp, Samsung, Google/Fitbit, Huawei, Xiaomi, Apple, Wear OS | Uhren, Bänder, Ohrhörer | nichts sicher — Broadcast meist ohne RR-Beleg 🟡/🟠/🔴 |
| Oura, Ultrahuman, RingConn, Circular, Samsung Galaxy Ring, Amazfit Helio Ring, Withings | Ringe, Hybriduhren | 🔴 (kein Broadcast) |
| Firstbeat, Bittium, Empatica, Corsano, Wellue, Lief, Muse | Medizin/Forschung | 🔴 bzw. 🟡 (proprietär) |
| Kubios, HRV4Training, Welltory, Strava, Zwift, TrainingPeaks | nur Apps | keine eigene Hardware |

---

## 4. Geräte je Anbieter

### 4.1 Polar

| Gerät | Art · Funk | App | praxis_gui | Anforderungen · Besonderheiten | Beleg |
|---|---|---|---|---|---|
| **H10** | Brustgurt EKG · BLE, ANT+, 5 kHz | ✅ | ✅ | Elektroden anfeuchten; 2 BLE-Verbindungen erst nach Aktivierung in Polar Beat/Flow. EKG nur in praxis_gui | eigener Test; [Polar](https://support.polar.com/ae-en/can-i-pair-h10-with-several-devices) |
| **Verity Sense** | optisch Arm · BLE, ANT+ | ✅ | ✅ | **Kopplung nötig**; PPI über PMD (`0x2A37` hat keine RR); SDK-Modus muss **aus** sein | eigener Test (praxis_gui `docs/verity_sense/`) |
| H9 | Brustgurt EKG · BLE, ANT+, 5 kHz | 🟢 | 🟢 | RR über `0x2A37`, kein PMD; ¹ | [Polar SDK](https://github.com/polarofficial/polar-ble-sdk/blob/master/documentation/products/PolarH9.md) |
| H7 | Brustgurt EKG · BLE, 5 kHz | 🟢 | 🟢 | eingestellt; per BLE gegen EKG validiert | [HRV4Training](https://www.hrv4training.com/blog2/hardware-for-hrv-what-sensor-should-you-use) |
| H6 | Brustgurt EKG · BLE | 🔵 | 🔵 | eingestellt | [Mindfield/Kubios](https://mindfield-shop.com/en/product/kubios-hrv-scientific-software-license-1-year/) |
| OH1 / OH1+ | optisch Arm · BLE (+ANT+) | 🔵 | 🔵 | keine RR in `0x2A37`; **PPI über PMD** wie Verity (Firmware ≥ 2.0.10). App erkennt das Gerät über die PMD-Featuremaske | [Polar SDK](https://github.com/polarofficial/polar-ble-sdk/blob/master/documentation/products/PolarOH1.md) |
| Ignite 3, Pacer, Pacer Pro, Vantage V3, Vantage M3, Grit X2, Grit X2 Pro | Uhr optisch · BLE | 🔵 | 🟡 | PPI über PMD nur mit **SDK-Freigabe** an der Uhr (über „Koppeln und synchronisieren" koppeln → Gekoppelte Geräte → SDK → Freigeben), Start nur aus dem Trainings-Wartebildschirm; ein Trainingsstart beendet PPI. Ob ein PMD-Client ohne Polar-SDK die Freigabe nutzen darf, ist unbelegt | [Polar SDK – Uhren](https://github.com/polarofficial/polar-ble-sdk/blob/master/documentation/UsingSDKWithWatches.md), [Ignite 3](https://github.com/polarofficial/polar-ble-sdk/blob/master/documentation/products/PolarIgnite3.md) |
| Polar 360, Polar Loop (2025) | optisch Handgelenk · BLE | 🔵 | 🟡 | PPI über PMD laut SDK; **nur ein Kopplungspartner** (Wechsel nur per Werksreset) → am selben Handy wie Polar Flow denkbar, am Desktop nur ohne Handy | [Polar 360](https://github.com/polarofficial/polar-ble-sdk/blob/master/documentation/products/Polar360.md) |
| Ignite 2, Unite, Vantage V2, Vantage M2, Grit X, Grit X Pro | Uhr optisch · BLE | 🟡 | 🟡 | „HF-Sensor-Modus" (GATT) im Vor-Training; RR unbelegt; kein SDK. App meldet hier erwartbar „PMD-Dienst fehlt — nur Puls"; ¹ | [DCR](https://dcrainmaker.com/2021/04/polars-broadcasting-peloton.html) |
| Ignite (1), Vantage V/M (1. Gen.), M430, M200, A370, A300, V800, M600 | Uhr · BLE | 🟡 | 🟡 | vermutlich nur „HF für andere sichtbar" = Advertising ohne Verbindung → dann 🔴 | Polar-Handbücher |
| T31, T34, WearLink (5 kHz) | Brustgurt · analog | 🔴 | 🔴 | kein BLE | [Polar](https://support.polar.com/za/compatibility) |
| Loop (alt), Loop 2, Loop Crystal | Aktivitätsband | 🔴 | 🔴 | kein eigener Pulssensor | — |

### 4.2 Garmin

| Gerät | Art · Funk | App | praxis_gui | Anforderungen · Besonderheiten | Beleg |
|---|---|---|---|---|---|
| HRM-Pro | Brustgurt EKG · BLE, ANT+ | 🟢 | 🟢 | 2 BLE-Verbindungen; Garmin-Uhr besser über ANT+ | [DCR](https://www.dcrainmaker.com/2020/09/garmin-hrm-pro-chest-strap-depth-review.html) |
| HRM 600 | Brustgurt EKG, Akku · BLE, ANT+ | 🟢 | 🟢 | Modus **open** nötig (secure = Garmin-eigene Authentifizierung); RMSSD in einem Test ~6,6 ms unter H10 | [the5krunner](https://the5krunner.com/2025/06/11/garmin-hrm-600-review-best-heart-rate-monitor-hrm/) |
| HRM-Pro Plus | Brustgurt EKG · BLE, ANT+ | 🔵 | 🔵 | **RR fehlen zeitweise**, v. a. bei parallelen Verbindungen; Garmin-Uhr über ANT+ koppeln, Handy-BT kurz aus/an hilft laut alphaHRV | [Garmin-Forum](https://forums.garmin.com/sports-fitness/running-multisport/f/accessories-sensors/321480/why-does-hrm-pro-plus-not-tracking-rr-intervals), [intervals.icu](https://forum.intervals.icu/t/alphahrv-update/27239) |
| HRM-Dual | Brustgurt EKG · BLE, ANT+ | 🔵 | 🔵 | widersprüchlich: Garmin „HRV über Bluetooth", DCR 2019 „BLE: keine RR", Welltory/Elite HRV: kompatibel; 2 Verbindungen | [DCR](https://www.dcrainmaker.com/2019/01/garmin-hrm-dual-heart-rate-strap-in-depth-review.html), [Welltory](https://help.welltory.com/articles/4998580) |
| HRM-Fit | Brustgurt (Sport-BH) · BLE, ANT+ | 🔵 | 🔵 | nur Herstellerangabe „HRV über Bluetooth" | [Händler](https://www.mantel.com/be-en/garmin-hrm-fit-heart-rate-monitor) |
| HRM 200 | Brustgurt EKG · BLE, ANT+ | 🔵 | 🔵 | Modus **open** nötig (LED blinkt 3×) | [Garmin](https://www8.garmin.com/manuals-apac/webhelp/hrm200/EN-SG/GUID-34D4135C-679D-4240-8E89-BC430147E018-5637.html) |
| Uhren mit BLE-Broadcast (Forerunner 245/745/945 und neuer, fēnix 6+, Epix, Venu 2+, MARQ; Instinct/Enduro/vívoactive 5–6 ungeprüft) | Uhr optisch · BLE, ANT+ | 🟠 | 🟠 | „Herzfrequenz übertragen" einschalten. RR fehlen (für FR745 belegt, für die übrigen angenommen) | [DCR](https://dcrainmaker.com/2020/04/garmin-wearable-broadcasting.html), [Garmin-Forum FR745](https://forums.garmin.com/sports-fitness/running-multisport/f/forerunner-745/243411/broadcast-heart-rate-r-r-intervals) |
| ältere Uhren (FR 235/645/735/935, vívoactive 3/4, Venu 1, vívosmart 4) | Uhr · nur ANT+-Broadcast | 🔴 | 🔴 | — | [DCR](https://dcrainmaker.com/2020/04/garmin-wearable-broadcasting.html) |
| HRM-Run, HRM-Run2, HRM-Tri, HRM-Swim, HRM Premium/Soft Strap (HRM3-SS), HRM Standard | Brustgurt · nur ANT+ | 🔴 | 🔴 | — | [Garmin-Blog](https://www.garmin.com/cs-CZ/blog/?p=543) |
| Index Sleep Monitor | optisch Oberarm · BLE nur zur Connect-App | 🔴 | 🔴 | kein Sportsensor | [the5krunner](https://the5krunner.com/2025/06/05/garmin-index-sleep-monitor-lots-of-images-and-a-video/) |

### 4.3 Wahoo, Suunto, Movesense, Coros

| Gerät | Art · Funk | App | praxis_gui | Anforderungen · Besonderheiten | Beleg |
|---|---|---|---|---|---|
| **Wahoo** TICKR (Gen 2, 2020) | Brustgurt EKG · BLE, ANT+ | 🟢 | 🟢 | 3 Verbindungen; HRV-Qualität laut Altini mäßig | [DCR](https://dcrainmaker.com/2020/05/wahoos-tickr-review.html), [Kubios](https://www.kubios.com/supported-devices/) |
| Wahoo TICKR X (Gen 2) | Brustgurt + Speicher · BLE, ANT+ | 🟢 | 🟢 | 3 Verbindungen | [DCR](https://dcrainmaker.com/2020/05/wahoos-tickr-review.html) |
| Wahoo TRACKR Heart Rate | Brustgurt EKG, Akku · BLE, ANT+ | 🔵 | 🔵 | Herstellerangabe „HRV mit kompatibler App"; 3 Verbindungen | [the5krunner](https://the5krunner.com/2024/06/25/wahoo-trackr-review-heart-rate-monitor) |
| Wahoo TICKR / TICKR X / TICKR Run (Gen 1) | Brustgurt · BLE, ANT+ | 🔵 | 🔵 | ¹; RR laut Nutzern nur über BLE gültig | [DCR](https://dcrainmaker.com/2014/01/wahoo-fitness-tickr.html) |
| Wahoo TICKR FIT | optisch Arm · BLE, ANT+ | 🟠 | 🟠 | Wahoo bestätigt: keine RR an Dritt-Apps; DCR widersprüchlich | [Elite HRV](https://elitehrv.com/compatible-devices) |
| Wahoo Blue HR | Brustgurt · BLE | 🟠 | 🟠 | laut Hersteller keine RR an Dritt-Apps | [Elite HRV](https://elitehrv.com/compatible-devices) |
| Wahoo ELEMNT Rival | Uhr · BLE-/ANT+-Broadcast | 🟡 | 🟡 | ¹; Broadcast 4 h | [Wahoo](https://support.wahoofitness.com/hc/en-us/articles/11947819498514) |
| **Suunto** Smart Sensor | Brustgurt EKG · BLE | 🟢 | 🟢 | ¹; BLE-Name prüfen (§6, Befund 3) | [Kubios](https://www.kubios.com/supported-devices/) |
| Suunto Smart Heart Rate Belt | Brustgurt EKG · BLE | 🟢 | 🟢 | ¹ | [Elite HRV](https://elitehrv.com/compatible-devices), [Welltory](https://help.welltory.com/articles/4998580) |
| Suunto Smart Heart Rate Belt 2 (ab 09/2026) | Brustgurt EKG · BLE 5.4 | 🔵 | 🔵 | 3 Verbindungen; RR an Dritt-Apps unbelegt | [Suunto-Forum](https://forum.suunto.com/post/197296) |
| Suunto Race, Race S, Race 2, Vertical 2 | Uhr · BLE-Broadcast ab FW 2.53.42 (04/2026) | 🟡 | 🟡 | RR unbelegt; Abbrüche nach ~20 min gemeldet | [Suunto](https://www.suunto.com/Support/Software-updates/Release-notes/suunto-race-2-software-updates/) |
| Suunto 5 Peak, Ocean | Uhr | 🟡 | 🟡 | kein Broadcast gefunden | — |
| Suunto Vertical (1), 9 Peak, 9 Peak Pro, Run | Uhr | 🔴 | 🔴 | kein HR-Broadcast (Run: Stand 08/2026) | [Suunto-Forum](https://forum.suunto.com/topic/6872/broadcast-heart-rate) |
| Suunto ANT Comfort Belt, Dual Comfort Belt | Brustgurt · ANT bzw. ANT + analog | 🔴 | 🔴 | — | [Suunto-Forum](https://forum.suunto.com/topic/8319/suunto-spartan-trainer-and-hr-dual-belt-does-not-work) |
| **Movesense** HR2 | EKG-Pod · BLE | 🟢 | 🟢 | Hersteller: „BLE HR service, RR intervals" | [Datenblatt](https://www.movesense.com/wp-content/uploads/2024/09/Movesense-Sensor-HR2-Spec-Sheet.pdf) |
| Movesense Medical | EKG-Pod (MDR IIa) · BLE | 🟢 | 🟢 | Firmware 2.1.5/2.3.1 | [Movesense](https://www.movesense.com/news/2024/11/medical-out-of-the-box-solution-for-hr-and-hrv-measurement/) |
| Movesense Flash | Logger · BLE | 🟢 | 🟢 | Hersteller-FAQ: HRS mit R-R | Movesense-FAQ |
| Movesense HR+, Sensor (2017) | EKG-Pod · BLE | 🔵 | 🔵 | **Firmware muss den HR-Dienst enthalten** — Entwicklerfirmware kann ihn weglassen | [Movesense](https://www.movesense.com/product/movesense-sensor-hr/) |
| **Coros** Heart Rate Monitor | optisch Arm · nur BLE | 🟠 | 🟠 | DCR „Valid HRV/RR: No", Welltory: ungeeignet | [DCR](https://dcrainmaker.com/2023/07/monitor-optical-review.html) |
| Coros-Uhren (Pace, Apex, Vertix, Nomad) | Uhr · BLE-Broadcast | 🟡 | 🟡 | ¹, Handy muss getrennt sein; RR unbelegt | [Coros](https://support.coros.com/hc/en-us/articles/360040256991-Broadcast-heart-rate) |

### 4.4 Decathlon, Scosche, Myzone, Peloton

| Gerät | Art · Funk | App | praxis_gui | Anforderungen · Besonderheiten | Beleg |
|---|---|---|---|---|---|
| **Decathlon** Kalenji/Geonaute Dual ANT+/BT (≈ 2014) | Brustgurt · BLE, ANT+ | 🟡 | 🟡 | widersprüchlich: Elite HRV „Geonaute: keine RR" (Hersteller), Welltory „Kalenji Dual" kompatibel | [Decathlon](https://support.decathlon.fr/ceinture-cardio-dual-ant-bluetooth) |
| Decathlon/Kiprun HRM Belt (neuer), Kiprun HRB 500 (Arm) | Brustgurt bzw. optisch · BLE, ANT+ | 🟡 | 🟡 | RR unbelegt | — |
| codierte Kalenji-Gurte (5,3 kHz) | Brustgurt · analog | 🔴 | 🔴 | — | — |
| **Scosche** Rhythm24 | optisch Arm · BLE, ANT+ | 🟢⚠P | 🟢⚠P | **nur im HRV-Modus** (in der Rhythm-Sync-App setzen, nur in Ruhe); Vertrieb eingestellt | [Kubios](https://www.kubios.com/supported-devices/), [HRV4Training](https://www.hrv4training.com/blog2/scosches-rhythm24-heart-rate-variability) |
| Scosche Rhythm+ 2.0 | optisch Arm · BLE, ANT+ | 🟠 | 🟠 | leere RR-Liste; ab FW 1.018: 3 Verbindungen | [DCR](https://dcrainmaker.com/2021/03/scosche-rhythm-sensor.html) |
| Scosche Rhythm+ (Gen 1) | optisch Arm · BLE, ANT+ | 🟠 | 🟠 | RR-Feld gefüllt, aber **nicht schlaggenau** — wie „nur Puls" behandeln; ¹ | [HRV4Training](https://hrv4training.substack.com/p/week-28-optical-sensors-for-spot) |
| **Myzone** MZ-3 | Brustgurt · BLE, ANT+, 5,3 kHz | 🟠 | 🟠 | ¹; Hersteller: keine RR an Dritt-Apps | [Elite HRV](https://elitehrv.com/compatible-devices) |
| Myzone MZ-Switch, MZ-1 | Brust/Arm bzw. Brust · BLE (+ANT+) | 🟡 | 🟡 | MZ-1 ¹ | [Myzone](https://buy.myzone.org/en-us/products/mz-switch) |
| Myzone MZ-60 | Anzeigeuhr | 🔴 | 🔴 | kein Sensor | — |
| **Peloton** Heart Rate Band, Brustgurt | optisch Arm bzw. Brustgurt · BLE (+ANT+) | 🟡 | 🟡 | RR unbelegt | [connectthewatts](https://connectthewatts.com/2022/05/19/peloton-heart-rate-band-review/) |

### 4.5 Budget-, Rad- und Nischenmarken

| Gerät | Art · Funk | App | praxis_gui | Anforderungen · Besonderheiten | Beleg |
|---|---|---|---|---|---|
| **Coospo** HW9 | optisch Arm · BLE 5.0, ANT+ | 🟢⚠P | 🟢⚠P | RR/PPI mit HRV Logger aufgezeichnet; 2 Verbindungen | [Altini](https://marcoaltini.substack.com/p/coospo-hw9-for-heart-rate-variability) |
| Coospo H6 / H6M | Brustgurt EKG · BLE 5.0, ANT+ | 🔵 | 🔵 | Suunto ZoneSense (braucht RR) lief | [Coospo](https://www.coospo.com/products/h6-chest-strap-heart-rate-monitor), [Suunto-Forum](https://forum.suunto.com/topic/11678/suunto-zonesense/846) |
| Coospo H9Z | Brustgurt EKG, Akku · BLE 5.0, ANT+ | 🔵 | 🔵 | 2 Verbindungen | [the5krunner](https://the5krunner.com/2023/08/08/coospo-hw9-review-h9z/) |
| Coospo H808S | Brustgurt EKG · BLE, ANT+ | 🔵 | 🔵 | Validitätsstudie gegen H10 (IJSPP 2025: „limited validity") | [Coospo](https://www.coospo.com/products/h808s-chest-strap-heart-rate-monitor) |
| Coospo HW807 | optisch Arm · BLE, ANT+ | 🟡 | 🟡 | Hersteller „HRV: Yes", kein Messbeleg | [Coospo](https://www.coospo.com/products/hw807-armband-heart-rate-monitor) |
| Coospo HW706 | optisch Arm · BLE, ANT+ | 🟠 | 🟠 | Hersteller: „HRV: No" | [Coospo](https://www.coospo.com/products/hw706-armband-heart-rate-monitor) |
| Coospo H7 | Brustgurt | 🟡 | 🟡 | nicht mehr im Sortiment | — |
| **Magene** H603, H64 | Brustgurt · BLE, ANT+ | 🔵 | 🔵 | Hersteller nennt Elite HRV/Selfloops; Modellnamen werden vermischt | [Händler](https://www.pushys.com.au/magene-h603-heart-rate-monitor) |
| Magene H303, H003 | Brustgurt · BLE, ANT+ | 🟡 | 🟡 | nur ANT+-HRV belegt | [Garmin-Forum](https://forums.garmin.com/sports-fitness/running-multisport/f/accessories-sensors/307455/magene-h303-supports-hrv) |
| **Sigma** R1 Blue Comfortex+ | Brustgurt EKG · BLE | 🟢 | 🟢 | Anleitung: sendet RR-Intervalle; in der App koppeln, nicht in den Systemeinstellungen | [Anleitung](https://www.manualsdir.com/manuals/404540/sigma-r1-blue-comfortex.html) |
| Sigma R1 Duo Comfortex+ | Brustgurt EKG · BLE, ANT+ | 🟢 | 🟢 | „RR-Intervalle in ms über Bluetooth Smart" | [Händler](https://www.bike24.com/p2245883.html) |
| Sigma R1 Comfortex+ (ohne Blue/Duo), STS, 5-kHz-Sender | Brustgurt · analog/STS | 🔴 | 🔴 | den Funk bestimmt der Sender, nicht der Gurt | — |
| **4iiii** Viiiiva | Brustgurt EKG · BLE, ANT+ | 🔵 | 🔵 | ¹; Elite HRV und Welltory: kompatibel | [DCR](https://dcrainmaker.com/2013/07/viiiiva-bluetooth-bridge.html) |
| **Kyto** HRM-2935 / 2931 / 2936 | optisch Ohr-/Fingerclip · BLE | 🟢⚠P | 🟢⚠P | RMSSD systematisch etwas niedriger als H10 | [Altini 2935](https://marcoaltini.substack.com/p/kyto-2935-a-decent-cheap-sensor-for), [Altini 2936](https://marcoaltini.substack.com/p/kyto-2936-another-decent-cheap-sensor) |
| Kyto HRM-2809 | Brustgurt · BLE, ANT+ | 🟡 | 🟡 | Welltory: kompatibel; Habr: Original-Firmware meldet **Phantomschläge** | [Habr](https://habr.com/ru/post/493384) |
| **Moofit** HW401, H6-Varianten · **XOSS** X2/X2 Pro · **iGPSport** HR40/HR60/HR70 · **Bryton** Smart HRM · **Lezyne** Heart Rate Flow | Brustgurte/Armbänder · BLE, ANT+ | 🟡 | 🟡 | RR unbelegt; Lezyne laut Elite HRV „nur Puls" (Tendenz 🟠) | [XOSS](https://help.xoss.co/hc/support/articles/1694686144-x2-pro-support), [Elite HRV](https://elitehrv.com/compatible-devices) |
| No-Name-Gurte (Amazon/Alibaba) | Brustgurt · meist BLE, ANT+ | 🟡 | 🟡 | Elite HRV: meist nur Puls; Altini: viele gehen nicht | [Elite HRV](https://elitehrv.com/compatible-devices) |
| **Beurer** PM 235, PM 250 | Brustgurt · BLE (+5,3 kHz) | 🟡 | 🟡 | RR unbelegt | [Anleitung PM 235](https://www.medaval.ie/docs/manuals/Beurer-PM235-Manual.pdf) |
| Beurer PO 60 | Fingerpulsoximeter · BLE, proprietär | 🔴 | 🔴 | **in praxis_gui am Gerät erkundet** (6 Läufe, 08/2026): kein Live-Strom, nur gespeicherte Mittelwerte, keine Schlag-zu-Schlag-Werte | praxis_gui `docs/beurerPO60/README.md` |
| Beurer, reine Analoggurte | Brustgurt · 5,3 kHz | 🔴 | 🔴 | — | — |
| **Zephyr** HxM Smart | Brustgurt EKG · BLE 4.0 | 🟢 | 🟢 | Standard-HR-Profil mit R-R | [Zephyr](https://www.zephyranywhere.com/resources/developer-user-tools) |
| Zephyr HxM BT, BioHarness 3 | Gurt/Modul · Bluetooth Classic, proprietär | 🔴 | 🔴 | — | [Handbuch BioHarness](https://www.zephyranywhere.com/media/download/bioharness3-user-manual.pdf) |
| **Mindfield** eSense Pulse | Brustgurt · BLE | 🟢 | 🟢 | bei Kubios als RRI-kompatibel geführt | [Kubios](https://www.kubios.com/supported-devices/) |
| **Fourth Frontier** X2 / X2 Plus | Brustgurt EKG · BLE 5.0 | 🟡 | 🟡 | widersprüchlich: Support laut Suunto-Forum „keine RR im BLE-Strom", Welltory: kompatibel; 3 Verbindungen | [Suunto-Forum](https://forum.suunto.com/post/156720) |
| **Morpheus** M7 | Brustgurt EKG · BLE, ANT+ | 🟡 | 🟡 | HRV offiziell nur in der Morpheus-App | [Morpheus](https://trainwithmorpheus.com/m7-user-guide/) |

### 4.6 Uhren, Bänder, Ohrhörer, Ringe

| Gerät | Art | App | praxis_gui | Anforderungen · Besonderheiten | Beleg |
|---|---|---|---|---|---|
| **Whoop** 5.0 | Band optisch | 🟢 | 🟢 | Broadcast in der Whoop-App starten; ¹; Flags `0x10` belegt. **⚠ RR-Einheit:** zwei Quellen sagen Millisekunden statt 1/1024 s (→ 2,3 % zu kurz), eine widerspricht; **keine RR bei Bewegung** | [GitHub elsayed85](https://github.com/elsayed85/whoop/blob/main/README.md), [NOOP](https://github.com/ryanbr/noop/releases) |
| Whoop 4.0, Whoop MG | Band optisch | 🔵 | 🔵 | wie 5.0; Welltory misst HRV über den Broadcast | [Welltory](https://help.welltory.com/articles/4275991) |
| Whoop 3.0 | Band optisch | 🟢 | 🟢 | RR in ms (Altini) | Altini (Medium) |
| **Amazfit** Helio Strap / Strap Pro | Band optisch · BLE | 🟡 | 🟡 | RR unbelegt; meldet sich als „Secure BLE" → Kopplung beachten | [DCR](https://www.dcrainmaker.com/2025/06/amazfit-helio-band-in-depth-review-99-no-sub-fee-but-worth-it.html) |
| Amazfit-Uhren (Balance, Active 2, Cheetah, T-Rex 3, GTR/GTS 4, Bip) | Uhr | 🟡 | 🟡 | Broadcast nur im Training; RR unbelegt | — |
| Amazfit Helio Ring | Ring | 🔴 | 🔴 | kein Broadcast | — |
| **Google** Fitbit Charge 6, Fitbit Air | Band | 🟡 | 🟡 | „HR on Equipment" bzw. Google-Health-App → „Share heart rate"; Bestätigung/Kopplung am Gerät; ¹ (Charge 6); RR unbelegt | [Google](https://support.google.com/fitbit/answer/14236705) |
| Google Pixel Watch 2–5 | Uhr | 🟡 | 🟡 | Kachel „Connected Fitness"; PW2 erst ab Wear OS 6; PW3+ 2 Verbindungen, ggf. PIN | [Google](https://support.google.com/fitbit/answer/14236705) |
| Pixel Watch 1, übrige Fitbits | Uhr/Band | 🔴 | 🔴 | kein Broadcast | [Elite HRV](https://help.elitehrv.com/article/254-is-your-heart-rate-monitor-compatible-with-elite-hrv) |
| **Huawei** Watch GT 2–5, Watch Fit, Band | Uhr/Band | 🟡 | 🟡 | Einstellungen → „HF-Datenübertragung"; RR unbelegt | [Huawei](https://consumer.huawei.com/ca/support/content/en-us15827504/) |
| **Xiaomi** Mi Band 6 | Band | 🟠 | 🟠 | Mitschnitt: Flags `0x00`, keine RR | [GitHub](https://github.com/maocomet/xiaomiheart-ble) |
| Xiaomi Smart Band 7–10, Redmi Watch | Band/Uhr | 🟡 | 🟡 | „Herzfrequenz übertragen" manuell; Tendenz nur Puls | [GitHub](https://github.com/Tnze/miband-heart-rate) |
| **Samsung** Galaxy Watch 4–8 / Ultra, Wear-OS-Uhren | Uhr | 🟡 | 🟡 | **kein nativer Broadcast**, nur über Dritt-Apps (HR2VP, Heart for Bluetooth, HrmApp); RR unbelegt | [Cadence](https://getcadence.app/support/can-i-use-my-samsung-galaxy-or-wearos-watch-for-heart-rate-readings/) |
| Samsung Galaxy Ring, Galaxy Fit | Ring/Band | 🔴 | 🔴 | kein Broadcast | — |
| **Apple** Watch | Uhr | 🔴 | 🔴 | kein Standard-HR-Profil; Relais-Apps laufen über das **iPhone** und liefern nur Puls | [HRV Logger](https://www.hrv.tools/hrv-logger-faq.html), [Kubios](https://www.kubios.com/hrv-app/) |
| Apple Powerbeats Pro 2 | Ohrhörer | 🟡 | 🟡 | sendet als BLE-HR-Profil, nur im Training; ¹; RR unbelegt | [DCR](https://dcrainmaker.com/2025/02/apple-beats-powerbeats-2-pro-sports-fitness-heart-rate-in-depth-review.html) |
| Apple AirPods Pro 3 | Ohrhörer | 🔴 | 🔴 | kein Standardsensor, nur iPhone-Relais | [TrainerRoad-Forum](https://www.trainerroad.com/forum/t/airpods-pro-3-heart-rate-tr-support/105594) |
| **Oura**, Ultrahuman, RingConn, Circular | Ring | 🔴 | 🔴 | nur Hersteller-App | [Oura](https://ouraring.com/blog/it/live-activity-tracking/) |
| **Withings** ScanWatch 1/2, Steel HR, Pulse HR | Hybriduhr | 🔴 | 🔴 | kein Broadcast | — |

### 4.7 HRV-App-Anbieter mit eigener Hardware, Medizin und Forschung

| Gerät | Art · Funk | App | praxis_gui | Anforderungen · Besonderheiten | Beleg |
|---|---|---|---|---|---|
| **Elite HRV** CorSense | Finger-PPG · BLE | 🟢⚠P | 🟢⚠P | „HR und R-R offen an jede App"; **nicht mehr erhältlich** | [Elite HRV](https://help.elitehrv.com/article/228-data-from-corsense) |
| **HeartMath** Inner Balance Bluetooth | Ohr-PPG · BLE | 🔵⚠P | 🔵⚠P | in Drittlisten HRV-fähig; HeartMath rät, **nicht** in den Systemeinstellungen zu koppeln | [Elite HRV](https://elitehrv.com/compatible-devices), [Welltory](https://help.welltory.com/articles/4998580) |
| HeartMath Inner Balance Coherence Plus | Ohr-PPG · BLE oder USB-C | 🔵⚠P | 🔵⚠P | „funktioniert mit jeder HRV-App, die das Standardprofil nutzt"; nur die BLE-Variante zählt | [HeartMath](https://store.heartmath.com/innerbalance) |
| HeartMath emWave Pro, emWave2 | PPG · USB | 🔴 | 🔴 | — | [HeartMath](https://heartcloud.com/library/emwave_desktop_tour.html) |
| **Optimal HRV** HRV Monitor 2.0 | Armband · BLE 5.0, ANT+ | 🔵 | 🔵 | nur Herstelleraussage; Bauart (optisch?) offen | [Optimal HRV](https://www.optimalhrv.com/product-page/hrv-monitor-2-0) |
| **Biostrap** Kairos | Sensor (B2B) · BLE | 🟢 | 🟢 | Standardprofil, RR deckungsgleich mit H10; für Privatkunden kaum erhältlich | [Altini](https://marcoaltini.substack.com/p/biostrap-kairos) |
| Biostrap EVO | Handgelenk-PPG | 🔴 | 🔴 | keine Echtzeitdaten an Dritte | [Elite HRV](https://elitehrv.com/compatible-devices) |
| **Firstbeat** Sports Sensor | Teamgurt · BLE | 🟡 | 🟡 | Standard-HR, RR nur intern belegt | [Firstbeat](https://content.firstbeat.com/hubfs/Sports/Firstbeat-Sports-Hardware-Technical-Specs.pdf) |
| Firstbeat Bodyguard 2/3 | EKG-Logger · USB | 🔴 | 🔴 | nur Offline-Auslese | [Firstbeat](https://content.firstbeat.com/hubfs/Life%20for%20Research/ENG%20Firstbeat%20Bodyguard%203%20For%20Research.pdf) |
| **Bittium** Faros 180/360 (auch eMotion Faros) | EKG-Holter · Bluetooth Classic | 🔴 | 🔴 | Kubios nur als Dateiimport | [Bittium](https://bittium.com/wp-content/uploads/2024/10/Bittium_Faros_tech_pocket_2022_web.pdf) |
| **Wellue** DuoEK, ArmFit | EKG-Kurzmesser bzw. Blutdruck · BLE | 🟡 | 🟡 | vermutlich proprietär (ViHealth) | [MedM](https://www.medm.com/sensors/wellue/duoek-connect-app.html) |
| **Empatica** E4/EmbracePlus, **Corsano** 287 | Medizin-Wearable · BLE, proprietäres SDK | 🔴 | 🔴 | IBI nur per Hersteller-SDK | [Empatica](https://developer.empatica.com/ios-sdk-api-reference-070.html), [Corsano](https://corsano.com/faq/) |
| **Lief** Smart Patch | EKG-Patch · BLE | 🟡 | 🟡 | vermutlich proprietär | [Lief](https://lief.ai/) |
| **InteraXon** Muse 2/S | EEG-Stirnband mit PPG · BLE, proprietär | 🔴 | 🔴 | — | [amused](https://pypi.org/project/amused/) |

### 4.8 Weitere Geräte aus Kompatibilitätslisten (meist eingestellt)

| Gerät | App | praxis_gui | Beleg |
|---|---|---|---|
| BlueLeza HRM Blue, Cardiosport TP3, Ambiotex-Shirt, Aidlab, Topeak DB-HRM, Vitalmonitor Nano/Flow | 🔵 | 🔵 | [Elite HRV](https://elitehrv.com/compatible-devices), [Welltory](https://help.welltory.com/articles/4998580) |
| UA Heart Rate, TomTom BLE HRM, Vernier Go Wireless (Hersteller: keine RR) · Mio ALPHA, LifeBEAM | 🟠 | 🟠 | [Elite HRV](https://elitehrv.com/compatible-devices), [HRV4Training](https://www.hrv4training.com/faq.html) |

---

## 5. Testliste

Abhaken, sobald ein Gerät an App bzw. praxis_gui geprüft ist. Ergebnis mit
Datum, Firmware und Handy/Rechner in die Tabelle in §4 eintragen und dort das
Zeichen auf ✅ (oder ehrlich auf 🟠/🔴) setzen.

**Erledigt**

- [x] Polar H10 — App ✅ · praxis_gui ✅
- [x] Polar Verity Sense — App ✅ · praxis_gui ✅

**Priorität 1 — verbreitet, Belege widersprüchlich**

- [ ] Garmin HRM-Pro Plus — RR mit und ohne gleichzeitig verbundene Garmin-Uhr?
- [ ] Garmin HRM-Dual
- [ ] Garmin HRM 600 / HRM 200 — Modus open gegen secure, Kopplung
- [ ] Wahoo TICKR (Gen 2) / TRACKR — mehrere RR je Paket über 60 bpm?
- [ ] Coospo H6/H6M, H9Z (günstig, nur indirekt belegt)
- [ ] Magene H603/H64
- [ ] Polar H9 (gut belegt — kurzer Bestätigungstest genügt)

**Priorität 2 — Kennzeichnung, Profil, Format**

- [ ] Polar OH1/OH1+ — PPI über PMD mit dem Verity-Pfad, Firmware auslesen
- [ ] Polar-Uhr mit SDK-Freigabe (Pacer Pro oder Ignite 3) — PMD-PPI; danach der HF-Sensor-Modus: RR in `0x2A37`?
- [ ] Whoop 5.0 — RR-Einheit (Summe der RR gegen Wanduhr, H10 parallel), Anteil Pakete ohne RR
- [ ] Scosche Rhythm24 — Normalmodus gegen HRV-Modus
- [ ] Kyto HRM-2935, Coospo HW9, CorSense — PPI über `0x2A37`, Kennzeichnung prüfen
- [ ] Suunto Smart Sensor / Smart Belt — BLE-Name, Kennzeichnung
- [ ] Movesense HR2 — HR-Dienst in der Werksfirmware?
- [ ] Sigma R1 Duo — günstige Gegenprobe zu einem „sicheren" Gurt

**Priorität 3 — Uhren-Broadcast, voraussichtlich nur Puls**

- [ ] eine Garmin-Uhr (Forerunner/fēnix)
- [ ] Fitbit Charge 6 / Pixel Watch — Kopplung, RR?
- [ ] Amazfit Helio Strap
- [ ] Huawei Watch GT / Xiaomi Band 8–10
- [ ] Suunto Race (Broadcast seit FW 2.53.42), eine Coros-Uhr, Polar Ignite 2
- [ ] Frontier X2 mit aktueller Firmware

**Kein Test nötig** — alles mit 🔴: es fehlt BLE oder das Standardprofil.

### So wird geprüft

1. **Schnelltest ohne App:** nRF Connect (Android) → Gerät verbinden → Heart
   Rate Measurement abonnieren → Flags-Byte ansehen. `0x10` gesetzt = RR im
   Paket. Bei mehr als 60 bpm sollten manche Pakete mehrere RR tragen.
2. **In der App:** verbinden, mindestens 5 min ruhig sitzen, speichern. Das
   Diagnoseprotokoll `sensor_<ts>_diagnose.txt` (Teilen-Menü) zeigt Dienste,
   „0x2A37 abonniert", PMD-Features und Kopplung. Steht die Messung danach auf
   „nur Puls", kamen keine RR.
3. **Plausibilität:** Summe der RR ≈ Messdauer (sonst Einheit falsch, siehe
   Whoop)? RR nicht starr ≈ 60000/bpm (sonst aus dem Puls zurückgerechnet)?
4. **Goldstandard:** in praxis_gui den H10 als Hauptgerät, den Prüfling
   „＋ Zusätzlich", 5 min, dann `tools/ble_pruefbericht.py` — vier Ebenen bis zum
   Bland-Altman gegen den H10 (praxis_gui `docs/ble_uebertragung_pruefen.md`).

---

## 6. Befunde für Code und Geräteprofile

Beim Abgleich mit `devices/profiles.py` aufgefallen. **Nichts davon ist
umgesetzt**; die Profil-IDs sind mit praxis_gui geteilt, Änderungen also erst
in [`kompatibilitaet.md`](kompatibilitaet.md) eintragen.

1. **Optische Sensoren werden als EKG gekennzeichnet.** Rhythm24, CorSense,
   Inner Balance, Kyto 29xx und Coospo HW9 schicken PPI im RR-Feld von `0x2A37`.
   Ohne passendes Namensmuster landen sie im Profil `ble_generic`
   (`intervall_quelle = ekg_rr`, Ausreißerschwelle 0,20). `"scosche"` steht
   sogar ausdrücklich in dessen Mustern. Die Aufnahme wird dann als `rr_ekg`
   gespeichert, weil `_qualitaet_raten` die Stufe aus Intervallquelle und
   RR-Vorhandensein ableitet. Abhilfe: ein Profil „optischer Sensor
   (Standardprofil)" mit `ppg_ppi` und Schwelle 0,30. Die Muster erst am echten
   BLE-Namen ablesen.
2. **Whoop: RR möglicherweise in Millisekunden.** `parse_hr_measurement` rechnet
   normgerecht in 1/1024 s. Stimmt der Verdacht, ist jedes Intervall 2,3 % zu
   kurz, und RMSSD/SDNN erben den Fehler. Erst messen (§5), dann gegebenenfalls
   einen Profilschalter „RR in ms" einführen.
3. **Suunto-Gurte könnten als PPG gelten.** `"suunto"` steht in den Mustern von
   `watch_broadcast` (`ppg_ppi`). Meldet sich ein Smart Sensor oder Smart Belt
   mit „Suunto" im Namen, wird ein EKG-Gurt als optisch gekennzeichnet. Den
   BLE-Namen am Gerät prüfen.
4. **Gemischte Pakete.** HRM-Pro Plus (zeitweise) und Whoop (bei Bewegung)
   senden mal mit, mal ohne RR. Die Diagnose sollte den Anteil der Pakete ohne
   RR ausweisen.
5. **RR-Bit gesetzt heißt nicht schlaggenau.** Rhythm+ Gen 1, Kyto 2809
   (Phantomschläge) und ältere Coospo-Sensoren füllen das Feld mit unbrauchbaren
   Werten. Der geplante Sensor-Prüfstand (M5) sollte deshalb auch die
   Plausibilität prüfen (§5, Schritt 3). `profil_verfeinern` wird bisher
   nirgends aufgerufen.
6. **Belegte Verbindung.** Viele Geräte nehmen nur eine BLE-Verbindung an. Ein
   Hinweis im Scan („nicht gefunden? Gurt von Uhr oder Hersteller-App trennen")
   würde die häufigste Fehlerursache abfangen.
7. **Polar-Uhren: SDK-Modus ist nicht gleich SDK-Freigabe.** Uhren kennen keinen
   SDK-Modus; sie brauchen die SDK-*Freigabe*. Der Profilhinweis von
   `polar_watch` beschreibt das richtig. Die Meldung „SDK-Modus aktiv? …" in
   `devices/polar.py` trifft dagegen nur auf Sensoren zu.

---

## 7. Kompatibilitätslisten Dritter — und warum sie sich widersprechen

| Liste | Stand | Bemerkung |
|---|---|---|
| [Kubios](https://www.kubios.com/supported-devices/) | ohne Datum (© 2026) | empfiehlt H10, Verity Sense, Movesense; dazu eSense Pulse, Rhythm24 (HRV-Modus), Suunto Smart Sensor, Wahoo TICKR. „ANT+ nicht unterstützt", Apple Watch ungeeignet |
| [Elite HRV](https://elitehrv.com/compatible-devices) | ohne Datum, erkennbar alt | Markierung „Hersteller bestätigt: keine RR" ist wertvoll; sonst teils überholt (Whoop, Rhythm24) |
| [Welltory](https://help.welltory.com/articles/4998580) | 04.07.2026 | die aktuellste Liste; führt aber H9 und Verity als ungeeignet |
| [HRV4Training/Altini](https://marcoaltini.substack.com/p/recommended-sensors-for-heart-rate) | 16.05.2023 | Qualitätsurteile mit eigenen Messungen |
| [Optimal HRV](https://www.optimalhrv.com/compatible-hrv-monitors) | © 2026 | fast eine Kopie der Elite-HRV-Liste |
| [Polar BLE SDK](https://github.com/polarofficial/polar-ble-sdk) | laufend | maßgeblich für PMD/PPI und die Polar-Uhren |

**Warum die Listen auseinanderlaufen:**

- **Verity Sense und OH1** stehen bei Elite HRV, Optimal HRV und Welltory als
  „keine HRV", weil `0x2A37` bei ihnen keine RR trägt. Kubios — und diese App —
  holen die PPI über PMD. Für uns gilt deshalb: Polar-Optik geht nur über den
  PMD-Pfad.
- **Polar H9** steht bei Welltory als ungeeignet. Das Polar-SDK und alle anderen
  Listen sagen RR über `0x2A37` — Welltory irrt hier vermutlich.
- **Garmin HRM-Dual/Pro Plus:** Keine Liste schließt die Gurte aus, die
  Nutzerberichte schon. Das Verhalten hängt offenbar vom Verbindungszustand ab.
- **Whoop:** Elite HRV führt Whoop als geschlossen. Welltory und Altini
  nutzen den Broadcast — die Elite-Liste ist hier veraltet.
- **Kalenji Dual, Frontier X2:** Eine Liste sagt ja, eine Quelle nein. Beide
  bleiben 🟡, bis jemand das Flags-Byte gesehen hat.
