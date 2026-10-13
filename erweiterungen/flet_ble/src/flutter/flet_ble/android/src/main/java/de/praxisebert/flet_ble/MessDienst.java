package de.praxisebert.flet_ble;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

/**
 * Vordergrunddienst, solange eine Messung läuft.
 *
 * <p>Er tut selbst nichts: Bluetooth, Python und Flutter laufen weiter im
 * App-Prozess. Der Dienst sorgt nur dafür, dass Android diesen Prozess bei
 * ausgeschaltetem Display oder in einer anderen App nicht einfriert oder
 * beendet — mit einer dauerhaften Benachrichtigung und einer Wake-Lock.
 */
public class MessDienst extends Service {
    static final String EXTRA_TITEL = "titel";
    static final String EXTRA_TEXT = "text";

    private static final String TAG = "FletBleMessDienst";
    private static final String KANAL = "hrv_messung";
    private static final int BENACHRICHTIGUNG_ID = 4712;
    /** Sicherheitsnetz: die Wake-Lock fällt spätestens nach 6 h. */
    private static final long SPERRE_MS = 6L * 60 * 60 * 1000;

    static volatile boolean laeuft = false;

    private PowerManager.WakeLock sperre;

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String titel = intent != null ? intent.getStringExtra(EXTRA_TITEL) : null;
        String text = intent != null ? intent.getStringExtra(EXTRA_TEXT) : null;
        try {
            kanalAnlegen();
            Notification n = benachrichtigung(
                    titel != null ? titel : "Messung läuft",
                    text != null ? text : "");
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(BENACHRICHTIGUNG_ID, n,
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
            } else {
                startForeground(BENACHRICHTIGUNG_ID, n);
            }
        } catch (Exception e) {
            // z. B. Android 14 ohne Bluetooth-Berechtigung: lieber ohne Dienst
            // weitermessen als die App abstürzen lassen.
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

    private void kanalAnlegen() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationChannel kanal = new NotificationChannel(
                KANAL, "Laufende Messung", NotificationManager.IMPORTANCE_LOW);
        kanal.setDescription("Zeigt an, dass eine HRV-Messung im Hintergrund weiterläuft.");
        kanal.setShowBadge(false);
        getSystemService(NotificationManager.class).createNotificationChannel(kanal);
    }

    @SuppressWarnings("deprecation")
    private Notification benachrichtigung(String titel, String text) {
        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, KANAL)
                : new Notification.Builder(this);
        b.setContentTitle(titel)
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(Notification.CATEGORY_SERVICE);
        Intent start = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (start != null) {
            start.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            b.setContentIntent(PendingIntent.getActivity(this, 0, start,
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        }
        return b.build();
    }
}
