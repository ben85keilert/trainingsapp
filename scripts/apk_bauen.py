"""Android-APK bauen — lokal und in der CI mit denselben Schritten.

    uv run python scripts/apk_bauen.py            # signiert, wenn ein Schlüssel eingerichtet ist
    uv run python scripts/apk_bauen.py --debug    # bewusst mit Debug-Schlüssel
    uv run python scripts/apk_bauen.py --alle-architekturen   # auch armeabi-v7a und x86_64

**Nur arm64** (Ben, 14.10.2026): vorerst baut das Skript nur für arm64-v8a — das
Pixel 10 und praktisch jedes Handy seit 2017. Mit allen drei Architekturen war
die APK 225 MB groß (x86_64 80 MB, armeabi-v7a 59 MB, arm64 70 MB an nativem
Code); nur arm64 spart rund 140 MB. Die anderen kommen später dazu
(``--alle-architekturen``, für die Play-Store-Fassung eher ein App Bundle).

Ergebnis: ``dist/trainingsapp-<version>-<build>.apk``.

**Signieren.** Android installiert ein Update nur, wenn es mit demselben
Schlüssel signiert ist wie die installierte App — sonst heißt es deinstallieren,
und mit der App verschwinden ihre Daten (Messungen, eigene Übungen). Deshalb
signiert dieses Skript mit dem festen Schlüssel, sobald einer eingerichtet ist:

1. Umgebungsvariablen ``FLET_ANDROID_SIGNING_KEY_STORE``,
   ``…_KEY_STORE_PASSWORD``, ``…_KEY_ALIAS`` (so macht es die CI), sonst
2. ``signierung.toml`` im Projektordner (von ``scripts/signierschluessel.py``
   angelegt, steht in ``.gitignore``).

Ohne beides bricht das Skript ab, statt still eine APK zu bauen, die sich nicht
über die bisherige installieren lässt — außer mit ``--debug``.

**Build-Nummer** (Android ``versionCode``) ist die Zahl der Commits auf dem
aktuellen Stand. Sie steigt mit jedem Commit, lokal wie in der CI, und Android
verlangt für ein Update eine mindestens gleich große Nummer.

**Eigene MainActivity** (Ben, 16.10.2026: Wegwischen in der App-Übersicht beendete
die Messung). Android beendet dabei die Activity; mit Flets Vorlage stirbt die
Flutter-Engine mit — und mit ihr die Bluetooth-Verbindung (flutter_blue_plus trennt
alle Geräte). Läuft eine Messung, hält der Vordergrunddienst den Prozess am Leben;
die eigene MainActivity (`MAIN_ACTIVITY`) hält dann auch die Engine und gibt sie
der nächsten Activity (Benachrichtigung, Startsymbol) zurück. Dafür baut
`vorlage_bauen` aus Flets Vorlage eine Kopie mit dieser Datei
(``build/vorlage/…zip``) und übergibt sie ``flet build --template``. Ändert Flet
seine MainActivity, bricht das Skript ab, statt still eine andere zu ersetzen.

Berichtigt am 18.10.2026 (Ben: „Die App lässt sich bei laufender Messung immer noch
gelegentlich schließen“): Bis dahin lieferte die MainActivity die Engine nur über
``provideFlutterEngine``. FlutterFragmentActivity baut das Fragment dann mit
``withNewEngine()``, also mit ``destroy_engine_with_fragment=true`` — das Ende der
Activity zerstörte die Engine trotzdem, sie blieb tot im Cache, und die nächste
Activity stürzte an ihr ab („FlutterJNI is not attached to native“). Jetzt holt das
Fragment die Engine über ``getCachedEngineId``, ``shouldDestroyEngineWithHost`` ist
``false``, und eine zerstörte Engine fliegt aus dem Cache. Übersetzen lässt sich die
Klasse ohne APK-Bau mit dem Kotlin-Compiler aus dem Gradle-Cache (so am 18.10. gegen
Flutter 3.44.8 geprüft); `tests/test_apk_bauen.py` hält die tragenden Stellen fest.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
SIGNIERUNG = PROJEKT / "signierung.toml"
AUSGABE = PROJEKT / "dist"
#: Version und Build-Nummer für die laufende App (config.app_version) — pyproject.toml
#: wandert nicht in die APK. Nicht versioniert (.gitignore).
BUILD_DATEI = PROJEKT / "src" / "trainingsapp" / "_build.py"

UMGEBUNG_SCHLUESSEL = "FLET_ANDROID_SIGNING_KEY_STORE"
#: Vorerst nur diese Architektur (Pixel 10) — siehe Moduldocstring
ARCHITEKTUR = "arm64-v8a"

#: Hier liegt die Vorlage mit eigener MainActivity (`vorlage_bauen`); ``build/`` ist ignoriert
VORLAGE_ORDNER = PROJEKT / "build" / "vorlage"
#: Die MainActivity in Flets Vorlage (cookiecutter) — und wie sie dort aussehen muss
MAIN_ACTIVITY_PFAD = (
    "build/{{cookiecutter.out_dir}}/android/app/src/main/kotlin/"
    "{{ cookiecutter.kotlin_dir }}/MainActivity.kt"
)
MAIN_ACTIVITY_FLET = """package {{ cookiecutter.org_name_2 }}.{{ cookiecutter.package_name }}

import io.flutter.embedding.android.FlutterFragmentActivity

class MainActivity : FlutterFragmentActivity()
"""
#: Unsere MainActivity: hält die Flutter-Engine über das Ende der Activity hinaus
MAIN_ACTIVITY = """package {{ cookiecutter.org_name_2 }}.{{ cookiecutter.package_name }}

import android.content.Context
import android.os.Bundle
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.engine.FlutterEngineCache
import io.flutter.embedding.engine.dart.DartExecutor

// Von scripts/apk_bauen.py statt der MainActivity der Flet-Vorlage eingesetzt
// (trainingsapp, 16.10.2026; berichtigt 18.10.2026).
//
// Wischt man die App in der App-Übersicht weg, beendet Android die Activity. Mit der
// Vorlage stürbe dabei die Flutter-Engine - und mit ihr Bluetooth (flutter_blue_plus
// trennt alle Geräte), also die laufende Messung. Hier gehört die Engine nicht der
// Activity: Sie liegt im FlutterEngineCache, und die nächste Activity (Tipp auf die
// Benachrichtigung oder das Startsymbol) nimmt sie wieder. Den Prozess hält während
// einer Messung der Vordergrunddienst (flet_ble, MessDienst) am Leben; ohne ihn
// beendet Android ihn beim Wegwischen wie bisher.
//
// Bis 18.10.2026 lieferte nur provideFlutterEngine die Engine. Dann baut
// FlutterFragmentActivity das Fragment mit withNewEngine(), also mit
// destroy_engine_with_fragment=true: Das Ende der Activity zerstörte die Engine
// trotzdem, sie blieb tot im Cache, und die nächste Activity stürzte an ihr ab
// ("FlutterJNI is not attached to native") - die Messung musste aus dem Backup
// zurück. Jetzt gilt der Weg, den Flutter für eine Engine im Cache vorsieht:
// getCachedEngineId, shouldDestroyEngineWithHost = false, die Engine liegt vor
// super.onCreate bereit und hat Dart selbst gestartet.
class MainActivity : FlutterFragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        // Vor super.onCreate: Dort holt sich das Fragment die Engine aus dem Cache
        engineHolen(applicationContext)
        super.onCreate(savedInstanceState)
    }

    override fun getCachedEngineId(): String = ENGINE

    override fun shouldDestroyEngineWithHost(): Boolean = false

    // Nur für ein Fragment, das Android aus einem früheren Stand der App wiederherstellt
    // (ohne Cache-ID in seinen Argumenten): auch dann diese Engine, nie eine zweite
    override fun provideFlutterEngine(context: Context): FlutterEngine =
        engineHolen(context.applicationContext)

    private companion object {
        const val ENGINE = "trainingsapp"

        fun engineHolen(context: Context): FlutterEngine {
            val cache = FlutterEngineCache.getInstance()
            cache.get(ENGINE)?.let { return it }
            val engine = FlutterEngine(context)
            // Wird sie doch einmal zerstört, fliegt sie aus dem Cache - eine tote Engine
            // ließe die nächste Activity abstürzen, so entsteht eine neue
            engine.addEngineLifecycleListener(
                object : FlutterEngine.EngineLifecycleListener {
                    override fun onPreEngineRestart() {}

                    override fun onEngineWillDestroy() {
                        if (cache.get(ENGINE) === engine) cache.remove(ENGINE)
                    }
                }
            )
            engine.dartExecutor.executeDartEntrypoint(DartExecutor.DartEntrypoint.createDefault())
            cache.put(ENGINE, engine)
            return engine
        }
    }
}
"""
#: Der BackupAgent kommt als zweite Datei neben die MainActivity
SICHERUNG_PFAD = MAIN_ACTIVITY_PFAD.replace("MainActivity.kt", "Sicherung.kt")
#: Geräte-Backup nur auf Wunsch (Sicherheitsdurchsicht S4; Ben, 20.10.2026: Vorgabe aus,
#: einschaltbar). `pyproject.toml` trägt ihn als ``backupAgent`` ins Manifest ein
#: (`[tool.flet.android.manifest_application]`); die Marke schreibt `core/sicherung.py`.
SICHERUNG = """package {{ cookiecutter.org_name_2 }}.{{ cookiecutter.package_name }}

import android.app.backup.BackupAgent
import android.app.backup.BackupDataInput
import android.app.backup.BackupDataOutput
import android.app.backup.FullBackupDataOutput
import android.os.ParcelFileDescriptor
import java.io.File

// Von scripts/apk_bauen.py in die Flet-Vorlage gelegt (trainingsapp, 20.10.2026).
//
// Android sichert den app-privaten Speicher von sich aus in Googles Cloud-Backup und
// überträgt ihn beim Gerätewechsel - Datenbank, Messdateien, Anhänge, GPS-Strecken.
// Die App verspricht, dass nichts das Gerät verlässt, was die Person nicht selbst
// auslöst. Darum sichert dieser Agent nur, wenn die App die Marke
// geraete_sicherung.txt (core/sicherung.py) in ihr Datenverzeichnis geschrieben hat;
// steht "strecken" darin, gehen auch die GPS-Strecken (Ordner Strecken/) mit, sonst
// bleiben sie draußen. Ohne Marke wird nichts geschrieben - weder ins Cloud-Backup
// noch bei der Übertragung von Gerät zu Gerät.
//
// Kein Schlüssel-Wert-Backup (onBackup/onRestore leer): android:fullBackupOnly="true"
// im Manifest lässt Android allein onFullBackup rufen. Die Wiederherstellung übernimmt
// BackupAgent.onRestoreFile, Datei für Datei dorthin, wo sie lag.
class Sicherung : BackupAgent() {
    override fun onBackup(
        oldState: ParcelFileDescriptor?,
        data: BackupDataOutput?,
        newState: ParcelFileDescriptor?,
    ) {}

    override fun onRestore(
        data: BackupDataInput?,
        appVersionCode: Int,
        newState: ParcelFileDescriptor?,
    ) {}

    override fun onFullBackup(data: FullBackupDataOutput) {
        val wurzel = dataDir
        val marke = markeFinden(wurzel, TIEFE) ?: return
        val strecken = marke.readLines().any { it.trim() == STRECKEN_ZEILE }
        wurzel
            .walkTopDown()
            .onEnter { ordner ->
                ordner === wurzel ||
                    (ordner.name !in AUSGESCHLOSSEN && (strecken || ordner.name != STRECKEN_ORDNER))
            }
            .filter { it.isFile }
            .forEach { fullBackupFile(it, data) }
    }

    private companion object {
        // Wörtlich wie core/sicherung.py (MARKE) und config.streckenverzeichnis()
        const val MARKE = "geraete_sicherung.txt"
        const val STRECKEN_ZEILE = "strecken"
        const val STRECKEN_ORDNER = "Strecken"
        // Flet legt das Datenverzeichnis wenige Ebenen unter dataDir ab (app_flutter/…)
        const val TIEFE = 3
        // Was Android selbst nie sichert - und was wir nicht brauchen
        val AUSGESCHLOSSEN = setOf("cache", "code_cache", "lib", "no_backup")

        fun markeFinden(ordner: File, tiefe: Int): File? {
            val direkt = File(ordner, MARKE)
            if (direkt.isFile) return direkt
            if (tiefe == 0) return null
            val kinder = ordner.listFiles() ?: return null
            for (kind in kinder) {
                if (kind.isDirectory && kind.name !in AUSGESCHLOSSEN) {
                    markeFinden(kind, tiefe - 1)?.let { return it }
                }
            }
            return null
        }
    }
}
"""


def version() -> str:
    with (PROJEKT / "pyproject.toml").open("rb") as f:
        return str(tomllib.load(f)["project"]["version"])


def build_nummer() -> int:
    """Commits bis HEAD — braucht die volle Historie (CI: ``fetch-depth: 0``)."""
    ausgabe = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=PROJEKT,
        check=True,
        capture_output=True,
        text=True,
    )
    return int(ausgabe.stdout.strip())


def signier_umgebung() -> dict[str, str] | None:
    """Signierangaben als Umgebungsvariablen für ``flet build`` — oder ``None``."""
    if os.environ.get(UMGEBUNG_SCHLUESSEL):
        return {}  # schon gesetzt (CI), flet liest sie selbst
    if not SIGNIERUNG.exists():
        return None
    with SIGNIERUNG.open("rb") as f:
        s = tomllib.load(f)
    pfad = Path(s["key_store"]).expanduser()
    if not pfad.exists():
        sys.exit(f"Schlüsseldatei aus {SIGNIERUNG.name} fehlt: {pfad}")
    return {
        UMGEBUNG_SCHLUESSEL: str(pfad),
        "FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD": str(s["password"]),
        "FLET_ANDROID_SIGNING_KEY_PASSWORD": str(s["password"]),
        "FLET_ANDROID_SIGNING_KEY_ALIAS": str(s.get("alias", "upload")),
    }


def vorlage_patchen(quelle: Path, ziel: Path) -> None:
    """Flets Vorlage (ZIP) nach ``ziel`` kopieren — mit `MAIN_ACTIVITY` statt ihrer eigenen.

    Reihenfolge und Einträge bleiben, wie sie sind (cookiecutter verlangt den
    Ordner ``build/`` als ersten Eintrag). Weicht Flets MainActivity von
    `MAIN_ACTIVITY_FLET` ab oder fehlt sie, bricht das Skript ab.
    """
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ersetzt = False
    with zipfile.ZipFile(quelle) as rein, zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as raus:
        for info in rein.infolist():
            daten = rein.read(info.filename)
            if info.filename == MAIN_ACTIVITY_PFAD:
                if daten.decode("utf-8").strip() != MAIN_ACTIVITY_FLET.strip():
                    sys.exit(
                        f"Flets MainActivity hat sich geändert ({quelle}) — "
                        "MAIN_ACTIVITY in scripts/apk_bauen.py prüfen und anpassen."
                    )
                daten = MAIN_ACTIVITY.encode("utf-8")
                ersetzt = True
            raus.writestr(info, daten)
            if ersetzt and info.filename == MAIN_ACTIVITY_PFAD:
                # Der BackupAgent direkt dahinter, im selben Kotlin-Ordner (S4)
                raus.writestr(SICHERUNG_PFAD, SICHERUNG.encode("utf-8"))
    if not ersetzt:
        sys.exit(f"Keine MainActivity in {quelle} — scripts/apk_bauen.py anpassen.")


def vorlage_bauen() -> Path:
    """Die Vorlage der installierten Flet-Version mit eigener MainActivity, als ZIP.

    Der Name trägt eine Prüfsumme der MainActivity: Ändert sie sich, ist es ein
    anderer Pfad — ``flet build`` merkt sich die Vorlage am Pfad und legt das
    Flutter-Projekt nur dann neu an.
    """
    import flet.version
    from flet_cli.commands.build_base import DEFAULT_TEMPLATE_URL
    from flet_cli.utils.template_cache import get_cached_template_zip

    version = flet.version.flet_version
    quelle = get_cached_template_zip(DEFAULT_TEMPLATE_URL.format(version=version), version)
    pruefsumme = hashlib.sha256((MAIN_ACTIVITY + SICHERUNG).encode("utf-8")).hexdigest()[:8]
    ziel = VORLAGE_ORDNER / f"flet-build-template-{version}-{pruefsumme}.zip"
    if not ziel.exists():
        vorlage_patchen(Path(quelle), ziel)
    return ziel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--alle-architekturen",
        action="store_true",
        help="auch armeabi-v7a und x86_64 (Vorgabe: nur arm64-v8a)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="ohne festen Schlüssel bauen (Update über eine signierte APK geht dann nicht)",
    )
    args = parser.parse_args()

    umgebung = dict(os.environ)
    signierung = None if args.debug else signier_umgebung()
    if signierung is None and not args.debug:
        sys.exit(
            "Kein Signierschlüssel eingerichtet. Einmalig "
            "`uv run python scripts/signierschluessel.py` ausführen — "
            "oder mit --debug bauen."
        )
    if signierung:
        umgebung |= signierung
    if args.debug:
        for name in list(umgebung):
            if name.startswith("FLET_ANDROID_SIGNING_"):
                del umgebung[name]

    nummer = build_nummer()
    BUILD_DATEI.write_text(
        '"""Von scripts/apk_bauen.py geschrieben — nicht bearbeiten, nicht committen."""\n\n'
        f'VERSION = "{version()}"\nBUILD = {nummer}\n',
        encoding="utf-8",
    )
    befehl = [
        "flet",
        "build",
        "apk",
        "--yes",
        "--no-rich-output",
        "--build-number",
        str(nummer),
        "--template",
        str(vorlage_bauen()),
    ]
    if not args.alle_architekturen:
        befehl += ["--arch", ARCHITEKTUR]
    if os.environ.get("CI"):
        befehl.append("--verbose")
    arch = "alle Architekturen" if args.alle_architekturen else ARCHITEKTUR
    art = "Debug" if args.debug else "signiert"
    print(f"Baue Version {version()} (Build {nummer}), {art}, {arch}")
    subprocess.run(befehl, cwd=PROJEKT, env=umgebung, check=True)

    apks = sorted((PROJEKT / "build" / "apk").glob("*.apk"))
    if not apks:
        sys.exit("flet build lief durch, aber in build/apk liegt keine APK")
    AUSGABE.mkdir(exist_ok=True)
    ziel = AUSGABE / f"trainingsapp-{version()}-{nummer}{'-debug' if args.debug else ''}.apk"
    shutil.copyfile(apks[0], ziel)
    print(f"Fertig: {ziel.relative_to(PROJEKT)}")


if __name__ == "__main__":
    main()
