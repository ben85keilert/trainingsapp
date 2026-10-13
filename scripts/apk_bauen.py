"""Android-APK bauen — lokal und in der CI mit denselben Schritten.

    uv run python scripts/apk_bauen.py            # signiert, wenn ein Schlüssel eingerichtet ist
    uv run python scripts/apk_bauen.py --debug    # bewusst mit Debug-Schlüssel

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
"""

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
SIGNIERUNG = PROJEKT / "signierung.toml"
AUSGABE = PROJEKT / "dist"

UMGEBUNG_SCHLUESSEL = "FLET_ANDROID_SIGNING_KEY_STORE"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
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
    befehl = [
        "flet",
        "build",
        "apk",
        "--yes",
        "--no-rich-output",
        "--build-number",
        str(nummer),
    ]
    if os.environ.get("CI"):
        befehl.append("--verbose")
    print(f"Baue Version {version()} (Build {nummer}), {'Debug' if args.debug else 'signiert'}")
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
