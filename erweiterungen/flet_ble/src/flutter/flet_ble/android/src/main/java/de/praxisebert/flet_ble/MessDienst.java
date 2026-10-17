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
 *
 * <p><b>Die Benachrichtigung</b> (Ben, 16.10.2026): Was läuft, steht im Titel;
 * eingeklappt eine kurze Zeile, ausgeklappt eine Zeile je Tätigkeit mit ihrer
 * Zeit; im Kopf eine Stoppuhr, die Android selbst weiterzählt. In der Statusleiste
 * steht ein Symbol der App ({@code ic_stat_trainingsapp}, einfarbig). Dafür hat
 * der Kanal die Wichtigkeit „Standard“ ohne Ton und Vibration: Benachrichtigungen
 * mit „niedrig“ gelten als still, und stille zeigt die Statusleiste (Pixel:
 * „Lautlose Benachrichtigungen in der Statusleiste ausblenden“) nicht an. Läuft
 * nur der Timer, steht dieselbe Benachrichtigung ohne Dienst da ({@link #zeigen}).
 */
public class MessDienst extends Service {
    static final String EXTRA_TITEL = "titel";
    static final String EXTRA_TEXT = "text";
    static final String EXTRA_LANG = "lang";
    static final String EXTRA_SEIT = "seit_ms";
    static final String EXTRA_GERAET = "geraet";
    static final String EXTRA_STANDORT = "standort";
    /** Typ {@code health}: Timer oder Plan allein (Einheit ohne Gurt und GPS), ab Android 14. */
    static final String EXTRA_GESUNDHEIT = "gesundheit";

    private static final String TAG = "FletBleMessDienst";
    /** Wichtigkeit „Standard“, ohne Ton — die eines bestehenden Kanals lässt sich nicht anheben. */
    private static final String KANAL = "laufend";
    /** Bis 16.10.2026: still (Wichtigkeit „niedrig“), darum ohne Symbol in der Statusleiste. */
    private static final String KANAL_ALT = "hrv_messung";
    private static final int BENACHRICHTIGUNG_ID = 4712;
    /** Ohne Dienst (nur der Timer): eigene Nummer — das Ende des Dienstes nimmt 4712 mit. */
    private static final int EINFACH_ID = 4713;
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
        String lang = intent != null ? intent.getStringExtra(EXTRA_LANG) : null;
        long seitMs = intent != null ? intent.getLongExtra(EXTRA_SEIT, 0L) : 0L;
        boolean geraet = intent == null || intent.getBooleanExtra(EXTRA_GERAET, true);
        boolean standort = intent != null && intent.getBooleanExtra(EXTRA_STANDORT, false);
        boolean gesundheit = intent != null && intent.getBooleanExtra(EXTRA_GESUNDHEIT, false);
        try {
            kanalAnlegen(this);
            Notification n = benachrichtigung(this, titel, text, lang, seitMs);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                int typ = 0;
                if (geraet) typ |= ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE;
                if (standort) typ |= ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION;
                if (gesundheit && Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                    typ |= ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH;
                }
                // Vor Android 14 gibt es health nicht — connectedDevice braucht dort nichts
                if (typ == 0) typ = ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE;
                try {
                    startForeground(BENACHRICHTIGUNG_ID, n, typ);
                } catch (SecurityException e) {
                    // Standort nicht erlaubt: Läuft auch eine Messung, darf sie den
                    // Dienst nicht verlieren — dann eben nur als connectedDevice.
                    if (!(geraet && standort)) throw e;
                    Log.w(TAG, "Standort-Typ abgelehnt, weiter ohne: " + e);
                    startForeground(BENACHRICHTIGUNG_ID, n,
                            ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
                }
            } else {
                startForeground(BENACHRICHTIGUNG_ID, n);
            }
            verbergen(this);  // die Benachrichtigung ohne Dienst (Timer) — jetzt steht diese da
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
     * Inhalt der laufenden Benachrichtigung ändern — ohne den Dienst neu zu starten.
     * Geht auch bei ausgeschaltetem Display (ein Neustart des Dienstes wäre aus dem
     * Hintergrund verboten). Ohne laufenden Dienst ein No-op.
     */
    static boolean textAendern(Context kontext, String titel, String text, String lang, long seitMs) {
        if (!laeuft) return false;
        NotificationManager nm = kontext.getSystemService(NotificationManager.class);
        if (nm == null) return false;
        nm.notify(BENACHRICHTIGUNG_ID, benachrichtigung(kontext, titel, text, lang, seitMs));
        return true;
    }

    /**
     * Dieselbe Benachrichtigung ohne Dienst — z. B. wenn nur der Timer läuft. Hält
     * nichts am Leben. Läuft der Dienst, ändert sie dessen Inhalt.
     */
    static boolean zeigen(Context kontext, String titel, String text, String lang, long seitMs) {
        if (laeuft) return textAendern(kontext, titel, text, lang, seitMs);
        NotificationManager nm = kontext.getSystemService(NotificationManager.class);
        if (nm == null) return false;
        kanalAnlegen(kontext);
        nm.notify(EINFACH_ID, benachrichtigung(kontext, titel, text, lang, seitMs));
        return true;
    }

    /** Die Benachrichtigung ohne Dienst wegnehmen; die des Dienstes bleibt. */
    static void verbergen(Context kontext) {
        NotificationManager nm = kontext.getSystemService(NotificationManager.class);
        if (nm != null) nm.cancel(EINFACH_ID);
    }

    private static void kanalAnlegen(Context kontext) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = kontext.getSystemService(NotificationManager.class);
        if (nm == null) return;
        try {
            nm.deleteNotificationChannel(KANAL_ALT);
        } catch (Exception e) {
            // Steht dort noch eine Benachrichtigung eines Dienstes, verweigert Android das
            Log.w(TAG, "Alter Kanal bleibt vorerst: " + e);
        }
        NotificationChannel kanal = new NotificationChannel(
                KANAL, "Laufende Messung", NotificationManager.IMPORTANCE_DEFAULT);
        kanal.setDescription(
                "Zeigt, was gerade läuft — Messung, Training, Timer — mit Zeit. Ohne Ton.");
        kanal.setSound(null, null);
        kanal.enableVibration(false);
        kanal.setShowBadge(false);
        nm.createNotificationChannel(kanal);
    }

    @SuppressWarnings("deprecation")
    private static Notification benachrichtigung(
            Context kontext, String titel, String text, String lang, long seitMs) {
        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(kontext, KANAL)
                : new Notification.Builder(kontext);
        String kurz = text != null ? text : "";
        b.setContentTitle(titel != null && !titel.isEmpty() ? titel : "Messung läuft")
                .setContentText(kurz)
                .setSmallIcon(R.drawable.ic_stat_trainingsapp)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(Notification.CATEGORY_SERVICE);
        if (lang != null && !lang.isEmpty() && !lang.equals(kurz)) {
            b.setStyle(new Notification.BigTextStyle().bigText(lang));
        }
        if (seitMs > 0) {
            // Die Stoppuhr zählt Android selbst — auch wenn die App gerade nichts schickt
            b.setWhen(seitMs).setShowWhen(true).setUsesChronometer(true);
        } else {
            b.setShowWhen(false);
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            b.setPriority(Notification.PRIORITY_DEFAULT);  // vor den Kanälen: wie „Standard“
        }
        Intent start = kontext.getPackageManager()
                .getLaunchIntentForPackage(kontext.getPackageName());
        if (start != null) {
            // addFlags, nicht setFlags: FLAG_ACTIVITY_NEW_TASK aus dem Start-Intent muss
            // bleiben — nach dem Wegwischen gibt es keine Aufgabe, in die es zurückgeht.
            start.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            b.setContentIntent(PendingIntent.getActivity(kontext, 0, start,
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        }
        return b.build();
    }
}
