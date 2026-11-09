import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Flet-Service „FletInstallieren" (trainingsapp, Katalog A8 Stufe 2): die App installiert
/// ihr eigenes Update. Die Arbeit macht die Kotlin-Klasse `FletInstallierenPlugin`
/// (Kanal „flet_installieren"); hier wird nur durchgereicht.
///
/// Methoden (Python → Dart): `stand`, `erlauben`, `pruefen` {pfad}, `installieren` {pfad};
/// für die Automatik `vorbereiten` {pfad}, `abschicken`, `spaeter` {sekunden},
/// `nicht_spaeter`, `verwerfen`, `benachrichtigung_erlauben`.
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

  /// Reicht jede Methode an Kotlin weiter — welche es gibt, steht dort
  /// (`FletInstallierenPlugin`); eine unbekannte endet dort mit „not implemented".
  Future<dynamic> _invoke(String name, dynamic args) async {
    final a = Map<String, dynamic>.from((args as Map?) ?? const {});
    final antwort = await _kanal.invokeMethod<dynamic>(name, a);
    return antwort is Map ? _karte(antwort) : antwort;
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
