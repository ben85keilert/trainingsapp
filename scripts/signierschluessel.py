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
import os
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
            "-storepass:env",
            "TRAININGSAPP_STOREPASS",  # nicht als Argument — stünde sonst in `ps`/`/proc`
            "-dname",
            "CN=Trainingsassistent, O=Praxis Ebert, C=DE",
        ],
        check=True,
        env={**os.environ, "TRAININGSAPP_STOREPASS": passwort},
    )
    # Nur für den Besitzer lesbar — mit der Standard-Umask wäre die Datei 0644
    fd = os.open(SIGNIERUNG, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(
            "# Lokale Signierung für scripts/apk_bauen.py — NICHT einchecken "
            "(steht in .gitignore).\n"
            f'key_store = "{ziel.as_posix()}"\n'
            f'alias = "{ALIAS}"\n'
            f'password = "{passwort}"\n'
        )

    print(f"\nSchlüssel: {ziel}\nLokale Angaben: {SIGNIERUNG.name} (Passwort steht nur dort)\n")
    print("Für GitHub (Repository → Settings → Secrets and variables → Actions):\n")
    print(f"  ANDROID_KEYSTORE_PASSWORD = (password aus {SIGNIERUNG.name})")
    print(f"  ANDROID_KEY_ALIAS         = {ALIAS}")
    print("  ANDROID_KEYSTORE_BASE64   = Ausgabe von:  base64 -w0 " + str(ziel))
    print("\nSchlüssel und Passwort sicher aufbewahren (Passwortmanager) — keine Kopien im Repo!")


if __name__ == "__main__":
    main()
