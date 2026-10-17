import 'dart:async';

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

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
        await _chr(a).setNotifyValue(false);
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

  Future<List<Map<String, dynamic>>> _scan(Map a) async {
    final dauer = _sekunden(a["timeout_s"], 8);
    final dienste = <Guid>[
      for (final s in (a["services"] as List? ?? const [])) Guid(s as String)
    ];
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
        "t_mono_us": _jetztUs(),
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

  Future<void> _subscribe(Map a) async {
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
        "t_mono_us": _jetztUs(),
        "t_wall_us": DateTime.now().microsecondsSinceEpoch,
      });
    });
    _abos[schluessel] = abo;
    _dev(a).cancelWhenDisconnected(abo);
    try {
      // Wählt Notifications oder – falls nur die gehen – Indications (Polar PMD Control).
      await c.setNotifyValue(true);
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
