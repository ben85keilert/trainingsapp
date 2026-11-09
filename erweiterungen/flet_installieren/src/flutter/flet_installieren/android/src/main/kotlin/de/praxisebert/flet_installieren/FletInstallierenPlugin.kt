package de.praxisebert.flet_installieren

import android.app.Activity
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.content.pm.Signature
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest

private const val KANAL = "flet_installieren"
internal const val AKTION_ERGEBNIS = "de.praxisebert.flet_installieren.ERGEBNIS"

/**
 * Die App installiert ihr eigenes Update (trainingsapp, Katalog A8 Stufe 2): eine geladene
 * APK über den `PackageInstaller` von Android.
 *
 * Methoden (Dart → Kotlin, Kanal „flet_installieren"):
 * - `stand` → {sdk, darf, still, paket, version_code, version_name, installiert_von}
 *   — `darf`: „Unbekannte Apps installieren" ist für diese App erlaubt (ab Android 8 je App);
 *   `still`: Android 12+, das Update kann ohne Rückfrage laufen.
 * - `erlauben` öffnet die Seite der Einstellungen, auf der man das erlaubt.
 * - `pruefen` {pfad} → {paket, eigenes_paket, version_code, version_name, eigener_code,
 *   signatur, gleiche_signatur} — liest die APK, ohne sie zu installieren.
 * - `installieren` {pfad} → Nummer der Sitzung; das Ergebnis kommt später als Ereignis.
 *
 * Ereignis (Kotlin → Dart): `ergebnis` {status, meldung, sitzung} mit den Codes von
 * `PackageInstaller.STATUS_*`. Bei -1 (Rückfrage) zeigt das Plugin selbst den Dialog von
 * Android.
 *
 * **Still ab Android 12:** `USER_ACTION_NOT_REQUIRED` plus die Berechtigung
 * `UPDATE_PACKAGES_WITHOUT_USER_ACTION` — Android verzichtet auf die Rückfrage, wenn die App
 * sich selbst aktualisiert (oder der Installer der App ist) und ihr targetSdk aktuell genug
 * ist. Sonst fragt Android doch (Status -1), und es kostet einen Tipp. Die APK muss mit
 * demselben Schlüssel signiert sein, sonst lehnt Android sie ab (Status 5).
 *
 * **Beim Installieren beendet Android den Prozess** — und öffnet die App danach nicht von
 * selbst. Wann das passieren darf (nie während einer Messung), entscheidet die App.
 */
class FletInstallierenPlugin : FlutterPlugin, MethodChannel.MethodCallHandler, ActivityAware {
    private var kanal: MethodChannel? = null
    private var kontext: Context? = null
    private var activity: Activity? = null
    private val haupt = Handler(Looper.getMainLooper())

    @Volatile
    private var beschaeftigt = false

    companion object {
        /** Das Plugin der laufenden Engine — `InstallErgebnis` meldet ihm das Ergebnis. */
        @Volatile
        internal var aktiv: FletInstallierenPlugin? = null
    }

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        kontext = binding.applicationContext
        val k = MethodChannel(binding.binaryMessenger, KANAL)
        k.setMethodCallHandler(this)
        kanal = k
        aktiv = this
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        if (aktiv === this) {
            aktiv = null
        }
        kanal?.setMethodCallHandler(null)
        kanal = null
        kontext = null
    }

    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        activity = binding.activity
    }

    override fun onDetachedFromActivityForConfigChanges() {
        activity = null
    }

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) {
        activity = binding.activity
    }

    override fun onDetachedFromActivity() {
        activity = null
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        val ctx = kontext
        if (ctx == null) {
            result.error("kontext", "Die Erweiterung ist nicht verbunden", null)
            return
        }
        when (call.method) {
            "stand" -> result.success(stand(ctx))
            "erlauben" -> erlauben(ctx, result)
            "pruefen" -> imHintergrund(result) { pruefen(ctx, pfad(call)) }
            "installieren" -> {
                if (beschaeftigt) {
                    result.error("belegt", "Es wird schon installiert", null)
                    return
                }
                beschaeftigt = true
                imHintergrund(result, { beschaeftigt = false }) {
                    sitzungSchreiben(ctx, File(pfad(call)))
                }
            }
            else -> result.notImplemented()
        }
    }

    // -- Stand und Erlaubnis -----------------------------------------------------------

    private fun stand(ctx: Context): Map<String, Any?> {
        val eigen = eigeneInfo(ctx)
        val darf = if (Build.VERSION.SDK_INT >= 26) {
            ctx.packageManager.canRequestPackageInstalls()
        } else {
            true // bis Android 7 gilt die Einstellung für das ganze Gerät
        }
        return mapOf(
            "sdk" to Build.VERSION.SDK_INT,
            "darf" to darf,
            "still" to (Build.VERSION.SDK_INT >= 31),
            "paket" to ctx.packageName,
            "version_code" to eigen?.let { versionCode(it) },
            "version_name" to eigen?.versionName,
            "installiert_von" to installer(ctx),
        )
    }

    /** Die Seite „Unbekannte Apps installieren" für diese App (ab Android 8). */
    private fun erlauben(ctx: Context, result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < 26) {
            result.success(false)
            return
        }
        val absicht = Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:${ctx.packageName}"),
        )
        try {
            starten(ctx, absicht)
            result.success(true)
        } catch (e: Exception) {
            result.error("erlauben", e.message ?: e.toString(), null)
        }
    }

    // -- APK prüfen ------------------------------------------------------------------------

    private fun pruefen(ctx: Context, pfad: String): Map<String, Any?> {
        val datei = File(pfad)
        require(datei.isFile) { "Keine Datei: $pfad" }
        val pm = ctx.packageManager
        val apk = archivInfo(pm, pfad, signaturFlag())
            ?: throw IllegalArgumentException("Android kann die APK nicht lesen")
        val eigen = eigeneInfo(ctx)
        val fremde = aktuelleSigner(apk).map { fingerabdruck(it) }.toSet()
        val eigene = eigen?.let { aktuelleSigner(it) }?.map { fingerabdruck(it) }?.toSet()
        return mapOf(
            "paket" to apk.packageName,
            "eigenes_paket" to (apk.packageName == ctx.packageName),
            "version_code" to versionCode(apk),
            "version_name" to apk.versionName,
            "eigener_code" to eigen?.let { versionCode(it) },
            "signatur" to fremde.sorted().joinToString(" "),
            // null: unbekannt (eine Seite ohne lesbare Signatur) — dann entscheidet Android
            "gleiche_signatur" to if (fremde.isEmpty() || eigene.isNullOrEmpty()) null else fremde == eigene,
        )
    }

    // -- Installieren ----------------------------------------------------------------------

    /** Schreibt die APK in eine Sitzung des PackageInstallers und schickt sie ab. */
    private fun sitzungSchreiben(ctx: Context, datei: File): Int {
        require(datei.isFile) { "Keine Datei: ${datei.path}" }
        val installer = ctx.packageManager.packageInstaller
        // Reste früherer Versuche (abgebrochen, App beendet) wegräumen
        for (alt in installer.mySessions) {
            try {
                installer.abandonSession(alt.sessionId)
            } catch (e: Exception) {
                // schon weg — egal
            }
        }
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(ctx.packageName)
        params.setSize(datei.length())
        if (Build.VERSION.SDK_INT >= 31) {
            params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
        }
        val id = installer.createSession(params)
        installer.openSession(id).use { sitzung ->
            try {
                FileInputStream(datei).use { ein ->
                    sitzung.openWrite("update.apk", 0, datei.length()).use { aus ->
                        ein.copyTo(aus, 1 shl 16)
                        sitzung.fsync(aus)
                    }
                }
                // Ausdrücklich an den eigenen Empfänger (nicht exportiert): Android 14 lässt
                // eine veränderliche PendingIntent nur mit festem Ziel zu, und der Installer
                // muss Status und Rückfrage hineinschreiben können (FLAG_MUTABLE).
                val absicht = Intent(ctx, InstallErgebnis::class.java).setAction(AKTION_ERGEBNIS)
                val flags = PendingIntent.FLAG_UPDATE_CURRENT or
                    (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
                val rueckmeldung = PendingIntent.getBroadcast(ctx, id, absicht, flags)
                sitzung.commit(rueckmeldung.intentSender)
            } catch (e: Exception) {
                sitzung.abandon()
                throw e
            }
        }
        return id
    }

    /** Vom Empfänger: Android braucht eine Bestätigung — den Dialog zeigen. */
    internal fun bestaetigen(ctx: Context, absicht: Intent) {
        starten(kontext ?: ctx, absicht)
    }

    /** Vom Empfänger: das Ergebnis an Dart (Hauptthread — onReceive läuft dort). */
    internal fun melden(status: Int, meldung: String?, sitzung: Int) {
        kanal?.invokeMethod(
            "ergebnis",
            mapOf("status" to status, "meldung" to meldung, "sitzung" to sitzung),
        )
    }

    // -- Helfer -----------------------------------------------------------------------------

    private fun starten(ctx: Context, absicht: Intent) {
        val a = activity
        if (a != null) {
            a.startActivity(absicht)
        } else {
            absicht.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(absicht)
        }
    }

    private fun pfad(call: MethodCall): String =
        call.argument<String>("pfad") ?: throw IllegalArgumentException("pfad fehlt")

    /** Arbeit abseits des Hauptthreads (eine APK hat ~90 MB), Antwort auf dem Hauptthread. */
    private fun imHintergrund(
        result: MethodChannel.Result,
        danach: () -> Unit = {},
        arbeit: () -> Any?,
    ) {
        Thread {
            try {
                val wert = arbeit()
                haupt.post { result.success(wert) }
            } catch (e: Exception) {
                haupt.post { result.error("fehler", e.message ?: e.toString(), null) }
            } finally {
                danach()
            }
        }.start()
    }

    private fun eigeneInfo(ctx: Context): PackageInfo? = try {
        paketInfo(ctx.packageManager, ctx.packageName, signaturFlag())
    } catch (e: PackageManager.NameNotFoundException) {
        null
    }

    private fun installer(ctx: Context): String? = try {
        if (Build.VERSION.SDK_INT >= 30) {
            ctx.packageManager.getInstallSourceInfo(ctx.packageName).installingPackageName
        } else {
            @Suppress("DEPRECATION")
            ctx.packageManager.getInstallerPackageName(ctx.packageName)
        }
    } catch (e: Exception) {
        null
    }

    @Suppress("DEPRECATION")
    private fun signaturFlag(): Int =
        if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES

    @Suppress("DEPRECATION")
    private fun paketInfo(pm: PackageManager, name: String, flags: Int): PackageInfo =
        if (Build.VERSION.SDK_INT >= 33) {
            pm.getPackageInfo(name, PackageManager.PackageInfoFlags.of(flags.toLong()))
        } else {
            pm.getPackageInfo(name, flags)
        }

    @Suppress("DEPRECATION")
    private fun archivInfo(pm: PackageManager, pfad: String, flags: Int): PackageInfo? =
        if (Build.VERSION.SDK_INT >= 33) {
            pm.getPackageArchiveInfo(pfad, PackageManager.PackageInfoFlags.of(flags.toLong()))
        } else {
            pm.getPackageArchiveInfo(pfad, flags)
        }

    @Suppress("DEPRECATION")
    private fun versionCode(info: PackageInfo): Long =
        if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()

    /** Wer die APK jetzt signiert: bei einem Schlüssel der letzte der Rotationsgeschichte. */
    @Suppress("DEPRECATION")
    private fun aktuelleSigner(info: PackageInfo): List<Signature> {
        if (Build.VERSION.SDK_INT >= 28) {
            val s = info.signingInfo ?: return emptyList()
            return if (s.hasMultipleSigners()) {
                s.apkContentsSigners?.toList() ?: emptyList()
            } else {
                listOfNotNull(s.signingCertificateHistory?.lastOrNull())
            }
        }
        return info.signatures?.toList() ?: emptyList()
    }

    private fun fingerabdruck(s: Signature): String =
        MessageDigest.getInstance("SHA-256").digest(s.toByteArray())
            .joinToString(":") { "%02X".format(it) }
}

/**
 * Nimmt das Ergebnis einer Installationssitzung entgegen (im Manifest, nicht exportiert —
 * nur die eigene PendingIntent erreicht ihn). Bei -1 zeigt er die Rückfrage von Android.
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
                } else if (plugin != null) {
                    plugin.bestaetigen(context, rueckfrage)
                } else {
                    rueckfrage.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    context.startActivity(rueckfrage)
                }
            } catch (e: Exception) {
                meldung = "Rückfrage nicht zu zeigen: ${e.message ?: e}"
            }
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
