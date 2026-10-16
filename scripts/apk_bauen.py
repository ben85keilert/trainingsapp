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
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.engine.FlutterEngineCache

// Von scripts/apk_bauen.py statt der MainActivity der Flet-Vorlage eingesetzt
// (trainingsapp, 16.10.2026).
//
// Wischt man die App in der App-Übersicht weg, beendet Android die Activity. Mit der
// Vorlage stürbe dabei die Flutter-Engine - und mit ihr Bluetooth (flutter_blue_plus
// trennt alle Geräte), also die laufende Messung. Hier gehört die Engine nicht der
// Activity: Sie liegt im FlutterEngineCache, und die nächste Activity (Tipp auf die
// Benachrichtigung oder das Startsymbol) nimmt sie wieder. Den Prozess hält während
// einer Messung der Vordergrunddienst (flet_ble, MessDienst) am Leben; ohne ihn
// beendet Android ihn beim Wegwischen wie bisher.
class MainActivity : FlutterFragmentActivity() {
    override fun provideFlutterEngine(context: Context): FlutterEngine =
        FlutterEngineCache.getInstance().get(ENGINE)
            ?: FlutterEngine(context.applicationContext).also {
                FlutterEngineCache.getInstance().put(ENGINE, it)
            }

    private companion object {
        const val ENGINE = "trainingsapp"
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
    pruefsumme = hashlib.sha256(MAIN_ACTIVITY.encode("utf-8")).hexdigest()[:8]
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
