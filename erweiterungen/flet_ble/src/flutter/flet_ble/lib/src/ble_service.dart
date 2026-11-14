import 'dart:async';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
// Im Browser spricht der Dienst den Plattformteil direkt an (_abonnieren, _subscribeWeb).
// ignore: depend_on_referenced_packages
import 'package:flutter_blue_plus_platform_interface/flutter_blue_plus_platform_interface.dart';

/// Flet-Service „FletBle": generisches BLE über flutter_blue_plus 1.36.8.
///
/// Methoden (Python → Dart, über `invokeMethod`): scan, stop_scan, connect,
/// disconnect, bond, bond_state, discover_services, request_mtu, read, write,
/// subscribe, unsubscribe, adapter_state, hintergrund_starten, hintergrund_beenden,
/// hintergrund_text, benachrichtigung_zeigen, benachrichtigung_verbergen, akku.
///
/// Ereignisse (Dart → Python, nur wenn `on_<name>` in Python gesetzt ist):
/// - `notification`     {device_id, service, characteristic, value (Uint8List → bytes),
///                       seq, t_mono_us, t_wall_us}
/// - `connection_state` {device_id, state, reason, t_mono_us}
/// - `adapter_state`    {state}
///
/// UUIDs gehen immer als volle 128-bit-Form in Kleinschrift hinaus; Eingaben
/// werden über `Guid(...).str128` normalisiert. Protokolle parst Python.
/// Keine Messwerte und keine Geräteadressen ins Log.
///
/// Im Browser (Web Bluetooth, nur Chrome und Edge): Statt eines Scans öffnet `scan` das
/// Auswahlfenster des Browsers (`_scanWeb`); Abos und Zeitstempel gehen eigene Wege
/// (`_abonnieren`, `_subscribeWeb`, `_zeit`). Vordergrunddienst, Kopplung und MTU gibt
/// es dort nicht.
class FletBleService extends FletService {
  FletBleService({required super.control});

  /// Monotone Uhr für Empfangszeitpunkte (Start beim Anlegen des Dienstes).
  final Stopwatch _uhr = Stopwatch()..start();

  /// Fortlaufende Nummer aller Notifications dieses Dienstes.
  int _seq = 0;

  /// Abos: "<device>|<service>|<characteristic>" für Werte,
  /// "verbindung|<device>" für den Verbindungszustand.
  final Map<String, StreamSubscription<dynamic>> _abos = {};
  StreamSubscription<BluetoothAdapterState>? _adapterAbo;

  /// Vordergrunddienst (android/…/MessDienst.java) — Messung bei Display aus.
  static const MethodChannel _hintergrund =
      MethodChannel("flet_ble/hintergrund");

  static bool get _istAndroid =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  @override
  void init() {
    super.init();
    debugPrint("FletBleService(${control.id}).init");
    unawaited(FlutterBluePlus.setLogLevel(LogLevel.none));
    control.addInvokeMethodListener(_invoke);
    _adapterAbo = FlutterBluePlus.adapterState.listen(
      (s) => control.triggerEvent("adapter_state", {"state": s.name}),
    );
  }

  // -- Hilfen ---------------------------------------------------------------

  static String _uuid(dynamic s) => Guid(s as String).str128;

  static BluetoothDevice _dev(Map a) =>
      BluetoothDevice.fromId(a["device_id"] as String);

  static String _key(Map a) =>
      "${a["device_id"]}|${_uuid(a["service"])}|${_uuid(a["characteristic"])}";

  static Duration _sekunden(dynamic wert, double standard) =>
      Duration(milliseconds: (((wert as num?) ?? standard) * 1000).round());

  /// Characteristic aus den zuletzt entdeckten Diensten.
  static BluetoothCharacteristic _chr(Map a) {
    final dienst = _uuid(a["service"]);
    final merkmal = _uuid(a["characteristic"]);
    for (final s in _dev(a).servicesList) {
      if (s.uuid.str128 != dienst) continue;
      for (final c in s.characteristics) {
        if (c.uuid.str128 == merkmal) return c;
      }
    }
    throw Exception(
        "Characteristic $merkmal im Dienst $dienst nicht gefunden – zuerst discover_services aufrufen");
  }

  int _jetztUs() => _uhr.elapsedMicroseconds;

  /// Zeitstempel so verpacken, dass die Web-Fassung sie senden kann. Sie ist JavaScript
  /// (dart2js) und kennt keine 64-Bit-Ganzzahlen in ByteData („Uint64 accessor not
  /// supported by dart2js“): Das Verpacken einer Zahl über 0xFFFFFFFF wirft, und das
  /// ganze Ereignis geht nie hinaus — still (gemessen 13.11.2026: Dart reichte 81
  /// Pakete weiter, in Python kam keines an; `t_wall_us` liegt bei 1,8 · 10^15, und
  /// `t_mono_us` überschreitet die Grenze nach 71 Minuten). Eine Zahl mit Nachkomma
  /// geht als 64-Bit-Kommazahl hinaus; Python macht wieder ganze Mikrosekunden daraus
  /// (`FletBleTransport`). Bis 2^52 ist „+ 0,5“ exakt. Gilt für jedes neue Feld:
  /// Zahlen über 0xFFFFFFFF gehen im Browser nur so — auch in der Gegenrichtung.
  static Object _zeit(int us) => kIsWeb && us > 0xFFFFFFFF ? us + 0.5 : us;

  // -- Methoden ---------------------------------------------------------------

  Future<dynamic> _invoke(String name, dynamic roh) async {
    final Map a = (roh is Map) ? roh : const {};
    switch (name) {
      case "adapter_state":
        return FlutterBluePlus.adapterStateNow.name;
      case "scan":
        return await _scan(a);
      case "stop_scan":
        await FlutterBluePlus.stopScan();
        return null;
      case "connect":
        return await _connect(a);
      case "disconnect":
        await _dev(a).disconnect(timeout: 10);
        return null;
      case "bond":
        return await _bond(a);
      case "bond_state":
        return _istAndroid
            ? (await _dev(a).bondState.first).name
            : "nicht_noetig";
      case "discover_services":
        return await _discover(a);
      case "request_mtu":
        return await _dev(a).requestMtu((a["mtu"] as num).toInt());
      case "read":
        return Uint8List.fromList(await _chr(a).read());
      case "write":
        await _chr(a).write(
          List<int>.from(a["data"] as List),
          withoutResponse: a["with_response"] == false,
        );
        return null;
      case "subscribe":
        await _subscribe(a);
        return null;
      case "hintergrund_starten":
        if (!_istAndroid) return false;
        return await _hintergrund.invokeMethod<bool>("starten", {
              ..._inhalt(a),
              "geraet": a["geraet"] as bool? ?? true,
              "standort": a["standort"] as bool? ?? false,
              "gesundheit": a["gesundheit"] as bool? ?? false,
            }) ??
            false;
      case "hintergrund_beenden":
        if (_istAndroid) await _hintergrund.invokeMethod<void>("beenden");
        return null;
      case "hintergrund_text":
        if (!_istAndroid) return false;
        return await _hintergrund.invokeMethod<bool>("text", _inhalt(a)) ??
            false;
      case "benachrichtigung_zeigen":
        if (!_istAndroid) return false;
        return await _hintergrund.invokeMethod<bool>("zeigen", _inhalt(a)) ??
            false;
      case "benachrichtigung_verbergen":
        if (_istAndroid) await _hintergrund.invokeMethod<void>("verbergen");
        return null;
      case "akku":
        if (!_istAndroid) return null;
        final werte = await _hintergrund.invokeMethod<Map>("akku");
        return werte == null ? null : Map<String, dynamic>.from(werte);
      case "unsubscribe":
        await _abos.remove(_key(a))?.cancel();
        await _abonnieren(_chr(a), false);
        return null;
      default:
        throw Exception("Unbekannte FletBle-Methode: $name");
    }
  }

  /// Inhalt der Benachrichtigung: Titel, eingeklappter und ausgeklappter Text,
  /// Beginn der Stoppuhr (ms seit 1970, 0 = keine).
  static Map<String, dynamic> _inhalt(Map a) => {
        "titel": a["titel"] as String? ?? "Messung läuft",
        "text": a["text"] as String? ?? "",
        "lang": a["lang"] as String? ?? "",
        "seit_ms": (a["seit_ms"] as num?)?.toInt() ?? 0,
      };

  /// Dienste, die die App am Gerät anspricht — Herzfrequenz, Batterie,
  /// Polar PMD. Web Bluetooth gibt nach dem Verbinden nur frei, was bei der
  /// Geräteauswahl genannt wurde; ohne diese Liste ist kein Dienst lesbar.
  static final List<Guid> _webDienste = [
    Guid("0000180d-0000-1000-8000-00805f9b34fb"),
    Guid("0000180f-0000-1000-8000-00805f9b34fb"),
    Guid("fb005c80-02e7-f387-1cad-8acd2d8df0c8"),
  ];

  /// Im Browser gibt es keinen Scan. `startScan` öffnet das
  /// Auswahlfenster des Browsers und kehrt zurück, wenn die Person ein Gerät
  /// gewählt oder abgebrochen hat — das Ergebnis ist höchstens ein Gerät.
  Future<List<Map<String, dynamic>>> _scanWeb(List<Guid> dienste) async {
    // Firefox, Safari, jedes iPhone — und Chromium unter Linux ohne Schalter — haben
    // kein Web Bluetooth. Das sagen, statt „nichts gefunden“ zu melden.
    if (!await FlutterBluePlus.isSupported) {
      throw Exception(
          "Dieser Browser kann kein Bluetooth (Web Bluetooth fehlt oder ist abgeschaltet). "
          "Es geht in Chrome oder Edge; unter Linux nur mit dem Schalter "
          "chrome://flags/#enable-experimental-web-platform-features.");
    }
    final gefunden = <String, ScanResult>{};
    Object? fehler;
    final abo = FlutterBluePlus.onScanResults.listen((liste) {
      for (final r in liste) {
        gefunden[r.device.remoteId.str] = r;
      }
    }, onError: (Object e) {
      fehler = e;
    });
    try {
      await FlutterBluePlus.startScan(
        // Nur Geräte mit Herzfrequenz-Dienst anbieten, nicht alles in Funkreichweite.
        withServices: dienste.isEmpty ? [_webDienste.first] : dienste,
        webOptionalServices: _webDienste,
      );
      // Das Ergebnis läuft über einen Strom; kurz warten, bis es angekommen ist.
      await Future<void>.delayed(const Duration(milliseconds: 400));
    } finally {
      try {
        await FlutterBluePlus.stopScan();
      } catch (_) {
        // Der Web-Teil des Plugins kennt kein stopScan.
      }
      await abo.cancel();
    }
    // Abbruch im Auswahlfenster ist kein Fehler (kein Gerät gewählt); alles andere zeigen.
    final text = fehler?.toString() ?? "";
    if (fehler != null && !text.toLowerCase().contains("cancel")) {
      throw Exception("Geräteauswahl des Browsers fehlgeschlagen: $text");
    }
    return [
      for (final r in gefunden.values)
        {
          "id": r.device.remoteId.str,
          "name": r.device.platformName,
          "rssi": r.rssi,
          "services": [for (final g in _webDienste) g.str128],
        }
    ];
  }

  Future<List<Map<String, dynamic>>> _scan(Map a) async {
    final dauer = _sekunden(a["timeout_s"], 8);
    final dienste = <Guid>[
      for (final s in (a["services"] as List? ?? const [])) Guid(s as String)
    ];
    if (kIsWeb) return _scanWeb(dienste);
    final gefunden = <String, ScanResult>{};
    final abo = FlutterBluePlus.onScanResults.listen((liste) {
      for (final r in liste) {
        gefunden[r.device.remoteId.str] = r;
      }
    });
    try {
      await FlutterBluePlus.startScan(withServices: dienste, timeout: dauer);
      // startScan kehrt sofort zurück; das Ende meldet isScanning.
      await FlutterBluePlus.isScanning
          .where((laeuft) => !laeuft)
          .first
          .timeout(dauer + const Duration(seconds: 5));
    } on TimeoutException {
      await FlutterBluePlus.stopScan();
    } finally {
      await abo.cancel();
    }
    return [
      for (final r in gefunden.values)
        {
          "id": r.device.remoteId.str,
          "name": r.advertisementData.advName.isNotEmpty
              ? r.advertisementData.advName
              : r.device.platformName,
          "rssi": r.rssi,
          "services": [
            for (final g in r.advertisementData.serviceUuids) g.str128
          ],
        }
    ];
  }

  Future<int> _connect(Map a) async {
    final dev = _dev(a);
    final id = dev.remoteId.str;
    // Manche Telefone verbinden schlecht, solange gescannt wird.
    if (FlutterBluePlus.isScanningNow) {
      await FlutterBluePlus.stopScan();
    }
    final schluessel = "verbindung|$id";
    await _abos.remove(schluessel)?.cancel();
    // skip(1): der Strom liefert zuerst den gecachten Zustand.
    _abos[schluessel] = dev.connectionState.skip(1).listen((s) {
      control.triggerEvent("connection_state", {
        "device_id": id,
        "state": s.name,
        "reason": dev.disconnectReason?.description,
        "t_mono_us": _zeit(_jetztUs()),
      });
    });
    await dev.connect(
      timeout: _sekunden(a["timeout_s"], 15),
      mtu: (a["mtu"] as num?)?.toInt(),
    );
    return dev.mtuNow;
  }

  Future<String> _bond(Map a) async {
    if (!_istAndroid) return "nicht_noetig";
    final dev = _dev(a);
    try {
      await dev.createBond(timeout: 60);
    } catch (e) {
      // Schon gekoppelt ist kein Fehler.
      if (!e.toString().toLowerCase().contains("already")) rethrow;
    }
    return (await dev.bondState.first).name;
  }

  Future<List<Map<String, dynamic>>> _discover(Map a) async {
    final dienste = await _dev(a).discoverServices();
    return [
      for (final s in dienste)
        {
          "uuid": s.uuid.str128,
          "characteristics": [
            for (final c in s.characteristics)
              {
                "uuid": c.uuid.str128,
                "properties": {
                  "read": c.properties.read,
                  "write": c.properties.write,
                  "write_without_response": c.properties.writeWithoutResponse,
                  "notify": c.properties.notify,
                  "indicate": c.properties.indicate,
                },
              }
          ],
        }
    ];
  }

  /// Abo ein- oder ausschalten. Im Browser am Kern von flutter_blue_plus vorbei,
  /// direkt an den Web-Teil: Der meldet nach `startNotifications`, es sei noch ein
  /// CCCD-Schreibvorgang abzuwarten, schickt dessen Bestätigung aber nie
  /// (flutter_blue_plus_web 7.0.2) — `setNotifyValue` des Kerns läuft dort immer in
  /// seine Frist und hält so lange die Sperre für alle BLE-Aufrufe (am Verity Sense
  /// gemessen, 13.11.2026: 10 s Hänger beim Abonnieren, danach „Trennen hakt“).
  static Future<void> _abonnieren(BluetoothCharacteristic c, bool an) async {
    if (!kIsWeb) {
      await c.setNotifyValue(an);
      return;
    }
    await FlutterBluePlusPlatform.instance.setNotifyValue(BmSetNotifyValueRequest(
      remoteId: c.remoteId,
      primaryServiceUuid: c.primaryServiceUuid,
      serviceUuid: c.serviceUuid,
      characteristicUuid: c.characteristicUuid,
      instanceId: c.instanceId,
      forceIndications: false,
      enable: an,
    ));
  }

  /// Abo im Browser: direkt am Strom des Web-Teils, gefiltert nach Gerät, Dienst und
  /// Characteristic — so am Gerät geprüft (Verity Sense, 14.11.2026: 0x2A37 und PPI).
  /// Ob `onValueReceived` des Kerns im Browser ebenso liefert, ist nicht geprüft.
  Future<void> _subscribeWeb(Map a) async {
    final c = _chr(a);
    final schluessel = _key(a);
    final geraet = a["device_id"] as String;
    final dienst = c.serviceUuid.str128;
    final merkmal = c.uuid.str128;
    await _abos.remove(schluessel)?.cancel();
    final abo =
        FlutterBluePlusPlatform.instance.onCharacteristicReceived.listen((p) {
      if (!p.success ||
          p.remoteId.str != geraet ||
          p.serviceUuid.str128 != dienst ||
          p.characteristicUuid.str128 != merkmal) {
        return;
      }
      control.triggerEvent("notification", {
        "device_id": geraet,
        "service": dienst,
        "characteristic": merkmal,
        "value": Uint8List.fromList(p.value),
        "seq": _seq++,
        "t_mono_us": _zeit(_jetztUs()),
        "t_wall_us": _zeit(DateTime.now().microsecondsSinceEpoch),
      });
    });
    _abos[schluessel] = abo;
    try {
      await _abonnieren(c, true);
    } catch (_) {
      await _abos.remove(schluessel)?.cancel();
      rethrow;
    }
  }

  Future<void> _subscribe(Map a) async {
    if (kIsWeb) return _subscribeWeb(a);
    final c = _chr(a);
    final schluessel = _key(a);
    final geraet = a["device_id"] as String;
    final dienst = c.serviceUuid.str128;
    final merkmal = c.uuid.str128;
    // Ein bestehendes Abo derselben Characteristic ersetzen.
    await _abos.remove(schluessel)?.cancel();
    final abo = c.onValueReceived.listen((wert) {
      control.triggerEvent("notification", {
        "device_id": geraet,
        "service": dienst,
        "characteristic": merkmal,
        "value": Uint8List.fromList(wert),
        "seq": _seq++,
        "t_mono_us": _zeit(_jetztUs()),
        "t_wall_us": _zeit(DateTime.now().microsecondsSinceEpoch),
      });
    });
    _abos[schluessel] = abo;
    _dev(a).cancelWhenDisconnected(abo);
    try {
      // Wählt Notifications oder – falls nur die gehen – Indications (Polar PMD Control).
      await _abonnieren(c, true);
    } catch (_) {
      await _abos.remove(schluessel)?.cancel();
      rethrow;
    }
  }

  @override
  void dispose() {
    debugPrint("FletBleService(${control.id}).dispose()");
    control.removeInvokeMethodListener(_invoke);
    for (final abo in _abos.values) {
      abo.cancel();
    }
    _abos.clear();
    _adapterAbo?.cancel();
    if (_istAndroid) {
      unawaited(
          _hintergrund.invokeMethod<void>("beenden").catchError((Object e) {
        debugPrint("FletBleService: Hintergrunddienst nicht beendet: $e");
      }));
    }
    for (final d in FlutterBluePlus.connectedDevices) {
      unawaited(d.disconnect().catchError((Object e) {
        debugPrint("FletBleService: Trennen beim Aufräumen fehlgeschlagen: $e");
      }));
    }
    super.dispose();
  }
}
