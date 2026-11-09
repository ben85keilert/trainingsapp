package de.praxisebert.flet_installieren

import android.app.ActivityManager
import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.os.Build
import android.os.SystemClock

internal const val AKTION_ERGEBNIS = "de.praxisebert.flet_installieren.ERGEBNIS"
internal const val AKTION_SPAETER = "de.praxisebert.flet_installieren.SPAETER"

/**
 * Was Plugin und Empfänger teilen (Katalog A8, Automatik; Ben 9.11.2026): die vorbereitete
 * Sitzung, der Wecker, der sie später abschickt, und die Benachrichtigungen.
 *
 * Die Automatik läuft in zwei Schritten. **Vorbereiten** (App im Vordergrund): die APK in
 * eine Sitzung schreiben, ohne sie abzuschicken; die Nummer steht in den SharedPreferences.
 * **Abschicken** (ein Wecker eine Minute nach dem Verlassen der App, `SpaeterInstallieren`):
 * nur noch `commit`, ein paar Millisekunden. Python kann dann schon eingefroren sein (Android
 * friert Apps im Hintergrund nach Sekunden ein), der Empfänger braucht es nicht.
 *
 * Vor dem Abschicken steht die erwartete Version in den Einstellungen; `NachUpdate` meldet
 * nach dem Update „aktualisiert, antippen zum Öffnen" — nur dann, nicht nach einem Update
 * aus dem Browser.
 */
internal object Selbstupdate {
    private const val PREFS = "flet_installieren"
    private const val K_SITZUNG = "sitzung"
    private const val K_CODE = "code"
    private const val K_NAME = "name"
    private const val K_ERWARTET_CODE = "erwartet_code"
    private const val K_ERWARTET_NAME = "erwartet_name"
    private const val KANAL = "app_update"
    private const val ID_AKTUALISIERT = 7301
    private const val ID_RUECKFRAGE = 7302

    /** Der Wecker gibt Android zehn Minuten Spielraum (kleiner lässt Android 12 nicht zu). */
    private const val FENSTER_MS = 10 * 60 * 1000L

    private fun prefs(ctx: Context): SharedPreferences =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    // -- Sitzung ------------------------------------------------------------------------------

    /** Die vorbereitete Sitzung merken — mit der Version der APK für die Benachrichtigung. */
    fun merken(ctx: Context, sitzung: Int, code: Long, name: String?) {
        prefs(ctx).edit()
            .putInt(K_SITZUNG, sitzung)
            .putLong(K_CODE, code)
            .putString(K_NAME, name)
            .commit()
    }

    /** Die vorbereitete Sitzung — -1, wenn keine gemerkt ist oder Android sie nicht mehr hat
     * (abgelaufen nach Tagen, verworfen). */
    fun vorbereitet(ctx: Context): Int {
        val id = prefs(ctx).getInt(K_SITZUNG, -1)
        if (id < 0) {
            return -1
        }
        val da = try {
            ctx.packageManager.packageInstaller.getSessionInfo(id) != null
        } catch (e: Exception) {
            false
        }
        return if (da) id else -1
    }

    /** Alle eigenen Sitzungen verwerfen (abgebrochen, veraltet, Automatik aus). */
    fun verwerfen(ctx: Context) {
        val installer = ctx.packageManager.packageInstaller
        for (alt in installer.mySessions) {
            try {
                installer.abandonSession(alt.sessionId)
            } catch (e: Exception) {
                // schon weg — egal
            }
        }
        prefs(ctx).edit().remove(K_SITZUNG).remove(K_CODE).remove(K_NAME).commit()
    }

    /**
     * Die Sitzung abschicken. Vorher steht die erwartete Version fest (`commit`, nicht
     * `apply`: Android beendet den Prozess gleich), danach gehört die Sitzung Android.
     */
    fun abschicken(ctx: Context, sitzung: Int) {
        val p = prefs(ctx)
        p.edit()
            .putLong(K_ERWARTET_CODE, p.getLong(K_CODE, -1))
            .putString(K_ERWARTET_NAME, p.getString(K_NAME, null))
            .remove(K_SITZUNG)
            .commit()
        try {
            ctx.packageManager.packageInstaller.openSession(sitzung).use { s ->
                s.commit(rueckmeldung(ctx, sitzung).intentSender)
            }
        } catch (e: Exception) {
            p.edit().remove(K_ERWARTET_CODE).remove(K_ERWARTET_NAME).commit()
            throw e
        }
    }

    /**
     * Ausdrücklich an den eigenen Empfänger (nicht exportiert): Android 14 lässt eine
     * veränderliche PendingIntent nur mit festem Ziel zu, und der Installer muss Status und
     * Rückfrage hineinschreiben können (FLAG_MUTABLE).
     */
    private fun rueckmeldung(ctx: Context, sitzung: Int): PendingIntent {
        val absicht = Intent(ctx, InstallErgebnis::class.java).setAction(AKTION_ERGEBNIS)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or
            (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
        return PendingIntent.getBroadcast(ctx, sitzung, absicht, flags)
    }

    /** Ein Abschicken ging schief: keine Benachrichtigung „aktualisiert" erwarten. */
    fun nichtsErwarten(ctx: Context) {
        prefs(ctx).edit().remove(K_ERWARTET_CODE).remove(K_ERWARTET_NAME).apply()
    }

    // -- Wecker ------------------------------------------------------------------------------

    private fun wecker(ctx: Context): PendingIntent =
        PendingIntent.getBroadcast(
            ctx,
            0,
            Intent(ctx, SpaeterInstallieren::class.java).setAction(AKTION_SPAETER),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

    /** In ``sekunden`` (frühestens) die vorbereitete Sitzung abschicken — ersetzt einen
     * früheren Wecker. Nicht exakt: dafür braucht es keine Berechtigung. */
    fun weckerStellen(ctx: Context, sekunden: Long) {
        val am = ctx.getSystemService(AlarmManager::class.java) ?: return
        am.setWindow(
            AlarmManager.ELAPSED_REALTIME_WAKEUP,
            SystemClock.elapsedRealtime() + sekunden * 1000L,
            FENSTER_MS,
            wecker(ctx),
        )
    }

    fun weckerAbbestellen(ctx: Context) {
        ctx.getSystemService(AlarmManager::class.java)?.cancel(wecker(ctx))
    }

    // -- Wird die App gerade benutzt? -------------------------------------------------------

    /**
     * Sichtbar oder mit Vordergrunddienst (Messung, Training, Timer: `flet_ble.MessDienst`)
     * — dann nie installieren. Ein Prozess, der nur für einen Empfänger aufwacht, steht
     * dahinter (Dienst, im Speicher, Bildschirm aus).
     */
    fun inBenutzung(): Boolean {
        val info = ActivityManager.RunningAppProcessInfo()
        ActivityManager.getMyMemoryState(info)
        return info.importance <= ActivityManager.RunningAppProcessInfo.IMPORTANCE_PERCEPTIBLE
    }

    // -- Benachrichtigungen -------------------------------------------------------------------

    fun benachrichtigungenAn(ctx: Context): Boolean =
        ctx.getSystemService(NotificationManager::class.java)?.areNotificationsEnabled() ?: false

    private fun melden(ctx: Context, id: Int, titel: String, text: String, ziel: PendingIntent) {
        val nm = ctx.getSystemService(NotificationManager::class.java) ?: return
        val b = if (Build.VERSION.SDK_INT >= 26) {
            // Leise: Android installiert gern nachts bei ausgeschaltetem Bildschirm
            nm.createNotificationChannel(
                NotificationChannel(KANAL, "App-Updates", NotificationManager.IMPORTANCE_LOW),
            )
            Notification.Builder(ctx, KANAL)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(ctx)
        }
        b.setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle(titel)
            .setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text))
            .setContentIntent(ziel)
            .setAutoCancel(true)
        try {
            nm.notify(id, b.build())
        } catch (e: SecurityException) {
            // Benachrichtigungen nicht erlaubt (Android 13+) — dann eben ohne
        }
    }

    /** Nach dem Update (`NachUpdate`): „aktualisiert, antippen zum Öffnen". */
    fun aktualisiertMelden(ctx: Context) {
        val p = prefs(ctx)
        val erwartet = p.getLong(K_ERWARTET_CODE, -1)
        val name = p.getString(K_ERWARTET_NAME, null)
        p.edit().remove(K_ERWARTET_CODE).remove(K_ERWARTET_NAME).commit()
        if (erwartet < 0) {
            return // kein Update aus der App (Browser, adb) — Android hat selbst gemeldet
        }
        val jetzt = eigeneVersion(ctx) ?: return
        if (jetzt < erwartet) {
            return
        }
        val start = ctx.packageManager.getLaunchIntentForPackage(ctx.packageName) ?: return
        start.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val ziel = PendingIntent.getActivity(
            ctx,
            ID_AKTUALISIERT,
            start,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val app = ctx.applicationInfo.loadLabel(ctx.packageManager).toString()
        val version = if (name.isNullOrBlank()) "Die neue Version" else "Version $name"
        melden(ctx, ID_AKTUALISIERT, "$app aktualisiert", "$version ist installiert — antippen zum Öffnen.", ziel)
    }

    /** Android fragt nach, die App ist aber nicht zu sehen: die Rückfrage als Benachrichtigung
     * (aus dem Hintergrund darf keine Activity starten). */
    fun rueckfrageMelden(ctx: Context, rueckfrage: Intent) {
        val ziel = PendingIntent.getActivity(
            ctx,
            ID_RUECKFRAGE,
            rueckfrage,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val app = ctx.applicationInfo.loadLabel(ctx.packageManager).toString()
        melden(ctx, ID_RUECKFRAGE, "Update für $app bereit", "Antippen zum Installieren.", ziel)
    }

    /** Die App ist offen: alte Meldungen, Wecker und Erwartungen wegräumen. */
    fun beimStart(ctx: Context) {
        weckerAbbestellen(ctx)
        ctx.getSystemService(NotificationManager::class.java)?.let {
            it.cancel(ID_AKTUALISIERT)
            it.cancel(ID_RUECKFRAGE)
        }
        val p = prefs(ctx)
        val erwartet = p.getLong(K_ERWARTET_CODE, -1)
        val jetzt = eigeneVersion(ctx)
        if (erwartet >= 0 && jetzt != null && jetzt >= erwartet) {
            nichtsErwarten(ctx) // NachUpdate kam nicht (oder schon) — jedenfalls erledigt
        }
    }

    // -- Pakete --------------------------------------------------------------------------------

    fun eigeneVersion(ctx: Context): Long? = try {
        versionCode(paketInfo(ctx.packageManager, ctx.packageName, 0))
    } catch (e: PackageManager.NameNotFoundException) {
        null
    }

    @Suppress("DEPRECATION")
    fun paketInfo(pm: PackageManager, name: String, flags: Int): PackageInfo =
        if (Build.VERSION.SDK_INT >= 33) {
            pm.getPackageInfo(name, PackageManager.PackageInfoFlags.of(flags.toLong()))
        } else {
            pm.getPackageInfo(name, flags)
        }

    @Suppress("DEPRECATION")
    fun archivInfo(pm: PackageManager, pfad: String, flags: Int): PackageInfo? =
        if (Build.VERSION.SDK_INT >= 33) {
            pm.getPackageArchiveInfo(pfad, PackageManager.PackageInfoFlags.of(flags.toLong()))
        } else {
            pm.getPackageArchiveInfo(pfad, flags)
        }

    @Suppress("DEPRECATION")
    fun versionCode(info: PackageInfo): Long =
        if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()
}

/**
 * Nimmt das Ergebnis einer Installationssitzung entgegen (im Manifest, nicht exportiert —
 * nur die eigene PendingIntent erreicht ihn). Bei -1 zeigt er die Rückfrage von Android:
 * als Dialog, wenn die App zu sehen ist, sonst als Benachrichtigung.
 */
class InstallErgebnis : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != AKTION_ERGEBNIS) {
            return
        }
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        var meldung = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
        val sitzung = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1)
        val plugin = FletInstallierenPlugin.aktiv
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            val rueckfrage = rueckfrage(intent)
            try {
                if (rueckfrage == null) {
                    meldung = "Android hat keine Rückfrage geschickt"
                } else if (!Selbstupdate.inBenutzung()) {
                    Selbstupdate.rueckfrageMelden(context, rueckfrage)
                } else if (plugin != null) {
                    plugin.bestaetigen(context, rueckfrage)
                } else {
                    rueckfrage.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    context.startActivity(rueckfrage)
                }
            } catch (e: Exception) {
                meldung = "Rückfrage nicht zu zeigen: ${e.message ?: e}"
            }
        } else if (status != PackageInstaller.STATUS_SUCCESS) {
            Selbstupdate.nichtsErwarten(context)
        }
        plugin?.melden(status, meldung, sitzung)
    }

    @Suppress("DEPRECATION")
    private fun rueckfrage(intent: Intent): Intent? =
        if (Build.VERSION.SDK_INT >= 33) {
            intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
        } else {
            intent.getParcelableExtra(Intent.EXTRA_INTENT)
        }
}

/**
 * Der Wecker der Automatik (`Selbstupdate.weckerStellen`): die vorbereitete Sitzung
 * abschicken — nicht, wenn die App gerade benutzt wird oder etwas läuft. Dann stellt Python
 * beim nächsten Verlassen der App einen neuen.
 */
class SpaeterInstallieren : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != AKTION_SPAETER) {
            return
        }
        val sitzung = Selbstupdate.vorbereitet(context)
        if (sitzung < 0 || Selbstupdate.inBenutzung()) {
            return
        }
        try {
            Selbstupdate.abschicken(context, sitzung)
        } catch (e: Exception) {
            // Sitzung weg (Neustart, abgelaufen): beim nächsten Start lädt die App neu
            Selbstupdate.verwerfen(context)
        }
    }
}

/**
 * Nach dem Update (`MY_PACKAGE_REPLACED`, schickt nur das System — darum nicht exportiert):
 * „aktualisiert, antippen zum Öffnen", wenn die App das Update selbst eingespielt hat.
 */
class NachUpdate : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            Selbstupdate.aktualisiertMelden(context)
        }
    }
}
