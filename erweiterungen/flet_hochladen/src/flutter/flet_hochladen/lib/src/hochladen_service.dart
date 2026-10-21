// flet exportiert dart:io mit — hier ausdrücklich, damit File nicht an flet hängt
// ignore: unnecessary_import
import 'dart:io' show File;
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_image_compress/flutter_image_compress.dart';
import 'package:image_picker/image_picker.dart';
import 'package:image_picker_android/image_picker_android.dart';
import 'package:image_picker_platform_interface/image_picker_platform_interface.dart';

/// Flet-Service „FletHochladen" (trainingsapp, P74): ein Foto oder Video aus der
/// Fotoauswahl von Android, verkleinert und ohne Ortsangabe.
///
/// Methoden (Python → Dart): `waehlen`, `dauer_ms` {pfad}, `verkleinern` {quelle, art,
/// ziel, frontbild, kurze_seite, jpeg_qualitaet, video_bitrate, audio_bitrate},
/// `abbrechen`. Ereignis (Dart → Python): `fortschritt` {anteil}.
///
/// Fotos verkleinert flutter_image_compress ohne Exif (keepExif: false) — image_picker
/// kopierte beim Verkleinern die GPS-Felder mit (ExifDataCopier). Videos verkleinert die
/// Kotlin-Klasse `FletHochladenPlugin` (Kanal „flet_hochladen").
class FletHochladenService extends FletService {
  FletHochladenService({required super.control});

  static const _kanal = MethodChannel("flet_hochladen");

  @override
  void init() {
    super.init();
    debugPrint("FletHochladenService(${control.id}).init");
    // Fotoauswahl statt ACTION_GET_CONTENT — ab Android 16 ohnehin die Regel
    final plattform = ImagePickerPlatform.instance;
    if (plattform is ImagePickerAndroid) {
      plattform.useAndroidPhotoPicker = true;
    }
    _kanal.setMethodCallHandler(_vonAndroid);
    control.addInvokeMethodListener(_invoke);
  }

  Future<dynamic> _vonAndroid(MethodCall call) async {
    if (call.method == "fortschritt") {
      control.triggerEvent("fortschritt", {"anteil": call.arguments});
    }
    return null;
  }

  Future<dynamic> _invoke(String name, dynamic args) async {
    final a = (args as Map?) ?? const {};
    switch (name) {
      case "waehlen":
        return _waehlen();
      case "dauer_ms":
        return _kanal.invokeMethod<int>("dauer_ms", {"pfad": a["pfad"]});
      case "verkleinern":
        return _verkleinern(a);
      case "abbrechen":
        await _kanal.invokeMethod("abbrechen");
        return null;
      default:
        throw Exception("Unbekannte Methode: $name");
    }
  }

  Future<Map<String, dynamic>?> _waehlen() async {
    final datei = await ImagePicker().pickMedia(requestFullMetadata: false);
    if (datei == null) {
      return null;
    }
    return {
      "pfad": datei.path,
      "name": datei.name,
      "mime": datei.mimeType,
      "bytes": await File(datei.path).length(),
    };
  }

  Future<Map<String, dynamic>> _verkleinern(Map a) async {
    final quelle = a["quelle"] as String;
    final ziel = a["ziel"] as String;
    final kurz = (a["kurze_seite"] as num).toInt();
    final qualitaet = (a["jpeg_qualitaet"] as num).toInt();
    if (a["art"] == "bild") {
      final ergebnis = await FlutterImageCompress.compressAndGetFile(
        quelle,
        ziel,
        minWidth: kurz,
        minHeight: kurz,
        quality: qualitaet,
        inSampleSize: await _stichprobe(quelle, kurz),
        format: CompressFormat.jpeg,
        keepExif: false,
        autoCorrectionAngle: true,
      );
      if (ergebnis == null) {
        throw Exception("Das Foto ließ sich nicht verkleinern");
      }
      return {"bytes": await ergebnis.length()};
    }
    final antwort = await _kanal.invokeMethod<Map>("verkleinern", {
      "quelle": quelle,
      "ziel": ziel,
      "frontbild": a["frontbild"],
      "kurze_seite": kurz,
      "jpeg_qualitaet": qualitaet,
      "video_bitrate": a["video_bitrate"],
      "audio_bitrate": a["audio_bitrate"],
    });
    return Map<String, dynamic>.from(antwort ?? const {});
  }

  /// Jedes wievielte Pixel beim Dekodieren — ein 48-MP-Foto passte sonst ganz in den
  /// Speicher, bevor es auf die kurze Seite schrumpft. Ohne lesbare Größe (HEIC): 1.
  static Future<int> _stichprobe(String pfad, int kurz) async {
    try {
      final puffer = await ui.ImmutableBuffer.fromFilePath(pfad);
      final beschreibung = await ui.ImageDescriptor.encoded(puffer);
      final seite = math.min(beschreibung.width, beschreibung.height);
      beschreibung.dispose();
      puffer.dispose();
      var n = 1;
      while (seite ~/ (n * 2) >= kurz) {
        n *= 2;
      }
      return n;
    } catch (_) {
      return 1;
    }
  }

  @override
  void dispose() {
    debugPrint("FletHochladenService(${control.id}).dispose");
    control.removeInvokeMethodListener(_invoke);
    _kanal.setMethodCallHandler(null);
    super.dispose();
  }
}
