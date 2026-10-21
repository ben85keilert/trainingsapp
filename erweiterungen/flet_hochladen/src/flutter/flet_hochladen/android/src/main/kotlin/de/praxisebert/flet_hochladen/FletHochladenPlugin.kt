package de.praxisebert.flet_hochladen

import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import com.otaliastudios.transcoder.Transcoder
import com.otaliastudios.transcoder.TranscoderListener
import com.otaliastudios.transcoder.source.DataSource
import com.otaliastudios.transcoder.source.DataSourceWrapper
import com.otaliastudios.transcoder.source.FilePathDataSource
import com.otaliastudios.transcoder.strategy.DefaultAudioStrategy
import com.otaliastudios.transcoder.strategy.DefaultVideoStrategy
import com.otaliastudios.transcoder.validator.WriteAlwaysValidator
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Future
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

private const val KANAL = "flet_hochladen"

/**
 * Verkleinert ein gewähltes Video für „Hochladen" (trainingsapp, P74): H.264 mit fester
 * Bitrate und AAC-Ton über Transcoder, **ohne Ortsangabe**, dazu ein Frontbild als JPEG.
 *
 * Methoden (Dart → Kotlin, Kanal „flet_hochladen"): `dauer_ms` {pfad}, `verkleinern`
 * {quelle, ziel, frontbild, kurze_seite, video_bitrate, audio_bitrate, jpeg_qualitaet},
 * `abbrechen`. Fortschritt (Kotlin → Dart): `fortschritt` (0…1).
 *
 * Warum nicht video_compress: Es lässt die Bitrate schätzen (0,14 · Breite · Höhe · fps,
 * bei 720p 3,9 Mbit/s) und schreibt den Ort des Originals ins Ergebnis.
 */
class FletHochladenPlugin : FlutterPlugin, MethodChannel.MethodCallHandler {
    private var kanal: MethodChannel? = null
    private var laufend: Future<Void>? = null

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        val k = MethodChannel(binding.binaryMessenger, KANAL)
        k.setMethodCallHandler(this)
        kanal = k
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        laufend?.cancel(true)
        laufend = null
        kanal?.setMethodCallHandler(null)
        kanal = null
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "dauer_ms" -> dauer(call, result)
            "verkleinern" -> verkleinern(call, result)
            "abbrechen" -> {
                laufend?.cancel(true)
                result.success(null)
            }
            else -> result.notImplemented()
        }
    }

    private fun dauer(call: MethodCall, result: MethodChannel.Result) {
        val pfad = call.argument<String>("pfad")
        if (pfad == null) {
            result.error("argument", "pfad fehlt", null)
            return
        }
        val leser = MediaMetadataRetriever()
        try {
            leser.setDataSource(pfad)
            val ms = leser.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
            result.success(ms?.toLongOrNull())
        } catch (e: Exception) {
            result.error("dauer", e.message ?: e.toString(), null)
        } finally {
            freigeben(leser)
        }
    }

    private fun verkleinern(call: MethodCall, result: MethodChannel.Result) {
        val quelle = call.argument<String>("quelle")
        val ziel = call.argument<String>("ziel")
        val frontbild = call.argument<String>("frontbild")
        if (quelle == null || ziel == null || frontbild == null) {
            result.error("argument", "quelle, ziel und frontbild gehören dazu", null)
            return
        }
        if (laufend != null) {
            result.error("belegt", "Es wird schon ein Video verkleinert", null)
            return
        }
        val kurz = call.argument<Int>("kurze_seite") ?: 720
        val bildrate = call.argument<Number>("video_bitrate")?.toLong() ?: 800_000L
        val tonrate = call.argument<Number>("audio_bitrate")?.toLong() ?: 64_000L
        val qualitaet = call.argument<Int>("jpeg_qualitaet") ?: 85
        File(ziel).parentFile?.mkdirs()

        // Kurze Seite höchstens `kurz`, lange höchstens 16:9 dazu; ein Hochkant-Video bekommt
        // dieselben Grenzen gedreht. Keyframes alle 5 s: Transcoder reicht ein Video nur
        // durch, wenn dessen Abstand schon so groß ist — Handyvideos haben ~1 s, werden also
        // neu kodiert (die Bitrate allein verhindert das Durchreichen nicht).
        val video = DefaultVideoStrategy.atMost(kurz, kurz * 16 / 9)
            .bitRate(bildrate)
            .frameRate(30)
            .keyFrameInterval(5f)
            .build()
        val ton = DefaultAudioStrategy.builder()
            .channels(DefaultAudioStrategy.CHANNELS_AS_INPUT)
            .sampleRate(DefaultAudioStrategy.SAMPLE_RATE_AS_INPUT)
            .bitRate(tonrate)
            .build()
        laufend = Transcoder.into(ziel)
            .addDataSource(OhneOrt(FilePathDataSource(quelle)))
            .setVideoTrackStrategy(video)
            .setAudioTrackStrategy(ton)
            .setValidator(WriteAlwaysValidator())
            .setListener(object : TranscoderListener {
                override fun onTranscodeProgress(progress: Double) {
                    kanal?.invokeMethod("fortschritt", progress)
                }

                override fun onTranscodeCompleted(successCode: Int) {
                    laufend = null
                    try {
                        val (breite, hoehe, ms) = frontbildSchreiben(ziel, frontbild, kurz, qualitaet)
                        result.success(
                            mapOf(
                                "bytes" to File(ziel).length(),
                                "breite" to breite,
                                "hoehe" to hoehe,
                                "dauer_ms" to ms,
                            )
                        )
                    } catch (e: Exception) {
                        result.error("frontbild", e.message ?: e.toString(), null)
                    }
                }

                override fun onTranscodeCanceled() {
                    laufend = null
                    File(ziel).delete()
                    result.success(mapOf("abgebrochen" to true))
                }

                override fun onTranscodeFailed(exception: Throwable) {
                    laufend = null
                    File(ziel).delete()
                    result.error("verkleinern", exception.message ?: exception.toString(), null)
                }
            })
            .transcode()
    }

    /** Das Frontbild: ein Bild eine Sekunde hinein (bei kurzen Videos aus der Mitte), mit
     *  der kurzen Seite `kurz`. Gibt Breite, Höhe und Länge (ms) des Videos zurück. */
    private fun frontbildSchreiben(
        video: String,
        ziel: String,
        kurz: Int,
        qualitaet: Int,
    ): Triple<Int, Int, Long> {
        val leser = MediaMetadataRetriever()
        try {
            leser.setDataSource(video)
            val ms = leser.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
                ?.toLongOrNull() ?: 0L
            val zeitUs = min(1_000_000L, ms * 500L)
            val bild = leser.getFrameAtTime(zeitUs, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
                ?: throw IllegalStateException("Kein Bild im Video")
            val breite = bild.width
            val hoehe = bild.height
            val faktor = max(1f, min(breite, hoehe).toFloat() / kurz)
            val klein = if (faktor > 1f) {
                Bitmap.createScaledBitmap(
                    bild,
                    (breite / faktor).roundToInt(),
                    (hoehe / faktor).roundToInt(),
                    true,
                )
            } else {
                bild
            }
            FileOutputStream(ziel).use { klein.compress(Bitmap.CompressFormat.JPEG, qualitaet, it) }
            return Triple(breite, hoehe, ms)
        } finally {
            freigeben(leser)
        }
    }

    private fun freigeben(leser: MediaMetadataRetriever) {
        try {
            leser.release()
        } catch (e: Exception) {
            // schon freigegeben — egal
        }
    }
}

/** Die Spuren der Quelle, aber nie ihr Ort: Transcoder schriebe ihn sonst ins Ergebnis
 *  (`DefaultTranscodeEngine`: `dataSink.setLocation`). */
private class OhneOrt(quelle: DataSource) : DataSourceWrapper(quelle) {
    override fun getLocation(): DoubleArray? = null
}
