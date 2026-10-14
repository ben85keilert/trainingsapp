package de.praxisebert.flet_ble;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.BatteryManager;
import android.os.Build;

import androidx.annotation.NonNull;

import java.util.HashMap;
import java.util.Map;

import io.flutter.embedding.engine.plugins.FlutterPlugin;
import io.flutter.embedding.engine.plugins.activity.ActivityAware;
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;

/**
 * Kanal {@code flet_ble/hintergrund}: startet und beendet den {@link MessDienst}.
 *
 * <p>Methoden: {@code starten} (titel, text, geraet, standort) → bool, {@code beenden},
 * {@code aktiv} → bool, {@code text} (titel, text) → bool — Benachrichtigung ändern, ohne
 * den Dienst neu zu starten —, {@code akku} → Map für Strommessungen (Prozent, Ladung in µAh,
 * Strom in µA; ein Wert fehlt, wenn das Gerät ihn nicht liefert).
 */
public class FletBlePlugin implements FlutterPlugin, MethodChannel.MethodCallHandler, ActivityAware {
    private static final int ANFRAGE_BENACHRICHTIGUNG = 4711;

    private MethodChannel kanal;
    private Context kontext;
    private Activity activity;

    @Override
    public void onAttachedToEngine(@NonNull FlutterPluginBinding binding) {
        kontext = binding.getApplicationContext();
        kanal = new MethodChannel(binding.getBinaryMessenger(), "flet_ble/hintergrund");
        kanal.setMethodCallHandler(this);
    }

    @Override
    public void onDetachedFromEngine(@NonNull FlutterPluginBinding binding) {
        kanal.setMethodCallHandler(null);
        kanal = null;
    }

    @Override
    public void onMethodCall(@NonNull MethodCall call, @NonNull MethodChannel.Result result) {
        try {
            switch (call.method) {
                case "starten": {
                    benachrichtigungErlauben();
                    Boolean geraet = call.argument("geraet");
                    Boolean standort = call.argument("standort");
                    Intent i = new Intent(kontext, MessDienst.class)
                            .putExtra(MessDienst.EXTRA_TITEL, (String) call.argument("titel"))
                            .putExtra(MessDienst.EXTRA_TEXT, (String) call.argument("text"))
                            .putExtra(MessDienst.EXTRA_GERAET, geraet == null || geraet)
                            .putExtra(MessDienst.EXTRA_STANDORT, standort != null && standort);
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        kontext.startForegroundService(i);
                    } else {
                        kontext.startService(i);
                    }
                    result.success(true);
                    break;
                }
                case "beenden":
                    kontext.stopService(new Intent(kontext, MessDienst.class));
                    result.success(null);
                    break;
                case "aktiv":
                    result.success(MessDienst.laeuft);
                    break;
                case "text":
                    result.success(MessDienst.textAendern(kontext,
                            (String) call.argument("titel"), (String) call.argument("text")));
                    break;
                case "akku":
                    result.success(akku());
                    break;
                default:
                    result.notImplemented();
            }
        } catch (Exception e) {
            // Android 12+: aus dem Hintergrund darf kein Vordergrunddienst starten.
            result.error("hintergrund", e.toString(), null);
        }
    }

    /**
     * Akkustand fein genug für Strommessungen: die Prozentanzeige allein ist zu grob,
     * um GPS jede Sekunde gegen alle 10 s zu vergleichen. Die Ladung (µAh) zählt der
     * Ladestandsmesser des Akkus mit; fehlt ein Wert, liefert Android
     * {@code Integer.MIN_VALUE} oder 0 — der fehlt dann in der Map.
     */
    private Map<String, Object> akku() {
        Map<String, Object> m = new HashMap<>();
        BatteryManager bm = (BatteryManager) kontext.getSystemService(Context.BATTERY_SERVICE);
        if (bm == null) return m;
        wert(m, "prozent", bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY));
        wert(m, "ladung_uah", bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER));
        wert(m, "strom_ua", bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CURRENT_NOW));
        wert(m, "strom_mittel_ua",
                bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CURRENT_AVERAGE));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) m.put("laedt", bm.isCharging());
        return m;
    }

    private static void wert(Map<String, Object> m, String name, int wert) {
        if (wert != Integer.MIN_VALUE && wert != 0) m.put(name, wert);
    }

    /** Android 13+: ohne Erlaubnis bleibt die Benachrichtigung unsichtbar (der Dienst läuft trotzdem). */
    private void benachrichtigungErlauben() {
        if (Build.VERSION.SDK_INT < 33 || activity == null) return;
        if (activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED) return;
        activity.requestPermissions(
                new String[] {Manifest.permission.POST_NOTIFICATIONS}, ANFRAGE_BENACHRICHTIGUNG);
    }

    @Override
    public void onAttachedToActivity(@NonNull ActivityPluginBinding binding) {
        activity = binding.getActivity();
    }

    @Override
    public void onDetachedFromActivityForConfigChanges() {
        activity = null;
    }

    @Override
    public void onReattachedToActivityForConfigChanges(@NonNull ActivityPluginBinding binding) {
        activity = binding.getActivity();
    }

    @Override
    public void onDetachedFromActivity() {
        activity = null;
    }
}
