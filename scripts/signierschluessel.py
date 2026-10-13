"""Festen Android-Signierschlüssel einmalig anlegen.

    uv run python scripts/signierschluessel.py

Legt einen Schlüsselspeicher (PKCS12) **außerhalb** des Repos an, standardmäßig
``~/.trainingsapp-signierung/upload-keystore.jks``, schreibt ``signierung.toml``
für lokale Builds (`scripts/apk_bauen.py`) und gibt die vier Werte aus, die als
GitHub-Secrets für den Workflow „APK" gebraucht werden.

Braucht ``keytool`` aus einem JDK (für den Build ohnehin nötig: JDK 17).

**Den Schlüssel sichern** (Passwortmanager, zweiter Datenträger). Geht er
verloren, lässt sich keine neue Version mehr über die installierte App spielen —
nur noch deinstallieren, und mit der App verschwinden ihre Daten.
Niemals ins Repository einchecken.
"""

import argparse
import base64
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
SIGNIERUNG = PROJEKT / "signierung.toml"
ALIAS = "upload"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--ziel",
        type=Path,
        default=Path.home() / ".trainingsapp-signierung" / "upload-keystore.jks",
        help="Pfad der Schlüsseldatei (außerhalb des Repos!)",
    )
    args = parser.parse_args()
    ziel: Path = args.ziel.expanduser().resolve()

    if ziel.exists() or SIGNIERUNG.exists():
        sys.exit(
            f"Es gibt schon einen Schlüssel ({ziel if ziel.exists() else SIGNIERUNG}). "
            "Ein neuer würde Updates der installierten App unmöglich machen — abgebrochen."
        )
    if PROJEKT in ziel.parents:
        sys.exit("Die Schlüsseldatei gehört nicht ins Repository — anderen --ziel wählen.")
    keytool = shutil.which("keytool")
    if keytool is None:
        sys.exit("keytool nicht gefunden — ein JDK 17 installieren (z. B. Temurin).")

    # PKCS12 kennt nur ein Passwort für Speicher und Schlüssel.
    passwort = secrets.token_urlsafe(24)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            keytool,
            "-genkeypair",
            "-keystore",
            str(ziel),
            "-storetype",
            "PKCS12",
            "-alias",
            ALIAS,
            "-keyalg",
            "RSA",
            "-keysize",
            "4096",
            "-validity",
            "10000",
            "-storepass",
            passwort,
            "-dname",
            "CN=Trainingsassistent, O=Praxis Ebert, C=DE",
        ],
        check=True,
    )
    SIGNIERUNG.write_text(
        "# Lokale Signierung für scripts/apk_bauen.py — NICHT einchecken (steht in .gitignore).\n"
        f'key_store = "{ziel.as_posix()}"\n'
        f'alias = "{ALIAS}"\n'
        f'password = "{passwort}"\n',
        encoding="utf-8",
    )

    print(f"\nSchlüssel: {ziel}\nLokale Angaben: {SIGNIERUNG.name}\n")
    print("Für GitHub (Repository → Settings → Secrets and variables → Actions):\n")
    print(f"  ANDROID_KEYSTORE_PASSWORD = {passwort}")
    print(f"  ANDROID_KEY_ALIAS         = {ALIAS}")
    print("  ANDROID_KEYSTORE_BASE64   = (Inhalt der Datei unten)")
    b64 = ziel.with_suffix(".jks.base64.txt")
    b64.write_text(base64.b64encode(ziel.read_bytes()).decode("ascii"), encoding="ascii")
    print(f"                              {b64}")
    print("\nDanach die .base64.txt-Datei löschen. Schlüssel und Passwort sicher aufbewahren!")


if __name__ == "__main__":
    main()
