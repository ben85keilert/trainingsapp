import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Flet-Service „FletInstallieren" (trainingsapp, Katalog A8 Stufe 2): die App installiert
/// ihr eigenes Update. Die Arbeit macht die Kotlin-Klasse `FletInstallierenPlugin`
/// (Kanal „flet_installieren"); hier wird nur durchgereicht.
///
/// Methoden (Python → Dart): `stand`, `erlauben`, `pruefen` {pfad}, `installieren` {pfad}.
/// Ereignis (Dart → Python): `ergebnis` {status, meldung, sitzung}.
class FletInstallierenService extends FletService {
  FletInstallierenService({required super.control});

  static const _kanal = MethodChannel("flet_installieren");

  @override
  void init() {
    super.init();
    debugPrint("FletInstallierenService(${control.id}).init");
    _kanal.setMethodCallHandler(_vonAndroid);
    control.addInvokeMethodListener(_invoke);
  }

  Future<dynamic> _vonAndroid(MethodCall call) async {
    if (call.method == "ergebnis") {
      control.triggerEvent(
          "ergebnis", Map<String, dynamic>.from(call.arguments as Map));
    }
    return null;
  }

  Future<dynamic> _invoke(String name, dynamic args) async {
    final a = (args as Map?) ?? const {};
    switch (name) {
      case "stand":
        return _karte(await _kanal.invokeMethod<Map>("stand"));
      case "erlauben":
        return _kanal.invokeMethod<bool>("erlauben");
      case "pruefen":
        return _karte(
            await _kanal.invokeMethod<Map>("pruefen", {"pfad": a["pfad"]}));
      case "installieren":
        return _kanal.invokeMethod<int>("installieren", {"pfad": a["pfad"]});
      default:
        throw Exception("Unbekannte Methode: $name");
    }
  }

  static Map<String, dynamic> _karte(Map? m) =>
      Map<String, dynamic>.from(m ?? const {});

  @override
  void dispose() {
    debugPrint("FletInstallierenService(${control.id}).dispose");
    control.removeInvokeMethodListener(_invoke);
    _kanal.setMethodCallHandler(null);
    super.dispose();
  }
}
