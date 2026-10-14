package de.praxisebert.flet_ble;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

/**
 * Vordergrunddienst, solange eine Messung läuft.
 *
 * <p>Er tut selbst nichts: Bluetooth, GPS, Python und Flutter laufen weiter im
 * App-Prozess. Der Dienst sorgt nur dafür, dass Android diesen Prozess bei
 * ausgeschaltetem Display oder in einer anderen App nicht einfriert oder
 * beendet — mit einer dauerhaften Benachrichtigung und einer Wake-Lock.
 *
 * <p>Typen (Android 10+): {@code connectedDevice} für den Gurt, {@code location}
 * für GPS — einzeln oder zusammen, je nachdem, was gerade läuft. Ein laufender
 * Dienst vom Typ {@code location} behält den Standortzugriff auch bei Display aus;
 * dafür braucht es kein {@code ACCESS_BACKGROUND_LOCATION}, solange er gestartet
 * wird, während die App sichtbar ist. Ein erneuter Start ändert Typ und Text.
 */
public class MessDienst extends Service {
    static final String EXTRA_TITEL = "titel";
    static final String EXTRA_TEXT = "text";
    static final String EXTRA_GERAET = "geraet";
    static final String EXTRA_STANDORT = "standort";

    private static final String TAG = "FletBleMessDienst";
    private static final String KANAL = "hrv_messung";
    private static final int BENACHRICHTIGUNG_ID = 4712;
    /** Sicherheitsnetz: die Wake-Lock fällt spätestens nach 6 h. */
    private static final long SPERRE_MS = 6L * 60 * 60 * 1000;

    static volatile boolean laeuft = false;
    /** Nur GPS, kein Gurt: anderes Symbol in der Statusleiste. */
    private static volatile boolean nurStandort = false;

    private PowerManager.WakeLock sperre;

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String titel = intent != null ? intent.getStringExtra(EXTRA_TITEL) : null;
        String text = intent != null ? intent.getStringExtra(EXTRA_TEXT) : null;
        boolean geraet = intent == null || intent.getBooleanExtra(EXTRA_GERAET, true);
        boolean standort = intent != null && intent.getBooleanExtra(EXTRA_STANDORT, false);
        try {
            kanalAnlegen(this);
            nurStandort = standort && !geraet;
            Notification n = benachrichtigung(this,
                    titel != null ? titel : "Messung läuft",
                    text != null ? text : "");
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                int typ = 0;
                if (geraet) typ |= ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE;
                if (standort) typ |= ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION;
                if (typ == 0) typ = ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE;
                try {
                    startForeground(BENACHRICHTIGUNG_ID, n, typ);
                } catch (SecurityException e) {
                    // Standort nicht erlaubt: Läuft auch eine Messung, darf sie den
                    // Dienst nicht verlieren — dann eben nur als connectedDevice.
                    if (!(geraet && standort)) throw e;
                    Log.w(TAG, "Standort-Typ abgelehnt, weiter ohne: " + e);
                    nurStandort = false;
                    startForeground(BENACHRICHTIGUNG_ID, n,
                            ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
                }
            } else {
                startForeground(BENACHRICHTIGUNG_ID, n);
            }
        } catch (Exception e) {
            // z. B. Android 14 ohne Bluetooth- oder Standort-Berechtigung: lieber
            // ohne Dienst weitermessen als die App abstürzen lassen.
            Log.w(TAG, "Vordergrunddienst nicht gestartet: " + e);
            stopSelf();
            return START_NOT_STICKY;
        }
        if (sperre == null) {
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            sperre = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "trainingsapp:messung");
            sperre.setReferenceCounted(false);
            sperre.acquire(SPERRE_MS);
        }
        laeuft = true;
        // Stirbt der Prozess, ist auch die Messung weg — ein Neustart des
        // Dienstes allein brächte nichts.
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        laeuft = false;
        if (sperre != null && sperre.isHeld()) {
            sperre.release();
        }
        sperre = null;
        super.onDestroy();
    }

    /**
     * Text der laufenden Benachrichtigung ändern — ohne den Dienst neu zu starten.
     * Geht auch bei ausgeschaltetem Display (ein Neustart des Dienstes wäre aus dem
     * Hintergrund verboten). Ohne laufenden Dienst ein No-op.
     */
    static boolean textAendern(Context kontext, String titel, String text) {
        if (!laeuft) return false;
        NotificationManager nm = kontext.getSystemService(NotificationManager.class);
        if (nm == null) return false;
        nm.notify(BENACHRICHTIGUNG_ID, benachrichtigung(kontext,
                titel != null ? titel : "Messung läuft", text != null ? text : ""));
        return true;
    }

    private static void kanalAnlegen(Context kontext) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationChannel kanal = new NotificationChannel(
                KANAL, "Laufende Messung", NotificationManager.IMPORTANCE_LOW);
        kanal.setDescription(
                "Zeigt an, dass eine Messung oder ein Training im Hintergrund weiterläuft.");
        kanal.setShowBadge(false);
        kontext.getSystemService(NotificationManager.class).createNotificationChannel(kanal);
    }

    @SuppressWarnings("deprecation")
    private static Notification benachrichtigung(Context kontext, String titel, String text) {
        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(kontext, KANAL)
                : new Notification.Builder(kontext);
        b.setContentTitle(titel)
                .setContentText(text)
                .setSmallIcon(nurStandort
                        ? android.R.drawable.ic_menu_mylocation
                        : android.R.drawable.stat_sys_data_bluetooth)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(Notification.CATEGORY_SERVICE);
        Intent start = kontext.getPackageManager()
                .getLaunchIntentForPackage(kontext.getPackageName());
        if (start != null) {
            start.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            b.setContentIntent(PendingIntent.getActivity(kontext, 0, start,
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        }
        return b.build();
    }
}
