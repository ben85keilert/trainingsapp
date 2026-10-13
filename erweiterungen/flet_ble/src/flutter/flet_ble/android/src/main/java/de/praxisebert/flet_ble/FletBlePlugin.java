package de.praxisebert.flet_ble;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;

import androidx.annotation.NonNull;

import io.flutter.embedding.engine.plugins.FlutterPlugin;
import io.flutter.embedding.engine.plugins.activity.ActivityAware;
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;

/**
 * Kanal {@code flet_ble/hintergrund}: startet und beendet den {@link MessDienst}.
 *
 * <p>Methoden: {@code starten} (titel, text) → bool, {@code beenden}, {@code aktiv} → bool.
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
                    Intent i = new Intent(kontext, MessDienst.class)
                            .putExtra(MessDienst.EXTRA_TITEL, (String) call.argument("titel"))
                            .putExtra(MessDienst.EXTRA_TEXT, (String) call.argument("text"));
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
                default:
                    result.notImplemented();
            }
        } catch (Exception e) {
            // Android 12+: aus dem Hintergrund darf kein Vordergrunddienst starten.
            result.error("hintergrund", e.toString(), null);
        }
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
