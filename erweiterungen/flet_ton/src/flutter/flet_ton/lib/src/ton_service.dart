import 'dart:convert';

import 'package:audioplayers/audioplayers.dart';
import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';

/// Flet-Service „FletTon": kurze Signaltöne über audioplayers.
///
/// Methoden (Python → Dart): `laden` {name, daten (Base64-WAV)},
/// `spielen` {name, lautstaerke}.
///
/// Ein Spieler je Ton, Quelle bleibt geladen (ReleaseMode.stop) — ein Ton
/// startet sofort und lässt sich beliebig oft wiederholen. Der Audiokontext
/// fordert den Fokus nur kurz und duckend an: Musik anderer Apps wird für
/// den Ton leiser und spielt danach weiter (Vorgabe von audioplayers wäre
/// AUDIOFOCUS_GAIN — Musik-Apps hielten an).
class FletTonService extends FletService {
  FletTonService({required super.control});

  final Map<String, AudioPlayer> _spieler = {};

  static final AudioContext _kontext = AudioContext(
    android: const AudioContextAndroid(
      isSpeakerphoneOn: false,
      stayAwake: false,
      contentType: AndroidContentType.sonification,
      usageType: AndroidUsageType.assistanceSonification,
      audioFocus: AndroidAudioFocus.gainTransientMayDuck,
    ),
    iOS: AudioContextIOS(
      category: AVAudioSessionCategory.ambient,
      options: const {},
    ),
  );

  @override
  void init() {
    super.init();
    debugPrint("FletTonService(${control.id}).init");
    control.addInvokeMethodListener(_invoke);
  }

  Future<dynamic> _invoke(String name, dynamic args) async {
    final a = (args as Map?) ?? const {};
    switch (name) {
      case "laden":
        final schluessel = a["name"] as String;
        final daten = base64Decode(a["daten"] as String);
        final alt = _spieler.remove(schluessel);
        await alt?.dispose();
        final spieler = AudioPlayer();
        await spieler.setAudioContext(_kontext);
        await spieler.setReleaseMode(ReleaseMode.stop);
        await spieler.setSourceBytes(daten, mimeType: "audio/wav");
        _spieler[schluessel] = spieler;
        return null;
      case "spielen":
        final spieler = _spieler[a["name"] as String];
        if (spieler == null) {
          throw Exception("Ton ${a["name"]} ist nicht geladen");
        }
        final lautstaerke = (a["lautstaerke"] as num?)?.toDouble() ?? 1.0;
        await spieler.stop();
        await spieler.setVolume(lautstaerke);
        await spieler.resume();
        return null;
      default:
        throw Exception("Unbekannte Methode: $name");
    }
  }

  @override
  void dispose() {
    debugPrint("FletTonService(${control.id}).dispose");
    control.removeInvokeMethodListener(_invoke);
    for (final spieler in _spieler.values) {
      spieler.dispose();
    }
    _spieler.clear();
    super.dispose();
  }
}
