"""Web-Fassung bauen — die App als statische Seite (Flutter zeichnet, Python über Pyodide).

    uv run python scripts/web_bauen.py --basis /app/<ordner>/     # für den Server der Praxis
    uv run python scripts/web_bauen.py --basis /       # lokal, dann: flet serve dist/web

Ergebnis: ``dist/web/`` — ein Ordner mit ``index.html``, den jeder Webserver ausliefern kann,
und darin ``stand.json`` (Version, Commit, Basisadresse; das Upload-Skript der Praxis prüft sie).

**Die Web-Fassung ist eine Demo** (Ben, 13.11.2026): ohne Konten, die Daten bleiben im Browser,
für das schnelle Üben eines Hausaufgabenprogramms. Was im Browser nicht geht oder nicht sein
soll, schaltet ``config.NICHT_IM_BROWSER`` ab.

Was dieses Skript über ``flet build web`` hinaus tut — jeder Punkt hat einmal gefehlt:

1. **``--no-cdn``.** Ohne lädt die Seite Pyodide von jsdelivr und Schriften von Google — bei
   jedem Besuch eine Anfrage an fremde Server.
2. **Basisadresse.** Sie ist in die Seite eingebaut (``<base href>``, Pfade zu CanvasKit und
   Pyodide). Unter einer anderen Adresse findet die Seite ihre Dateien nicht.
3. **Inline-Skripte auslagern.** Flets ``index.html`` enthält drei kleine Skripte. Eine strenge
   Content-Security-Policy (``script-src 'self'``) blockiert sie — die Seite bleibt weiß. In
   Dateien ausgelagert, braucht die CSP weder ``'unsafe-inline'`` noch Prüfsummen, die sich mit
   jedem Flet-Wechsel ändern.
4. **Ersatzschriften einlegen.** Fehlt Flutter ein Zeichen (der Pfeil „→“ steht nicht in der
   mitgelieferten Roboto), fragt es eine Noto-Schrift an — mit ``--no-cdn`` unter
   ``assets/fonts/``, wo Flet sie nicht ablegt. Die Anfrage scheitert und wiederholt sich in
   Dauerschleife (gemessen 13.11.2026: über 1400 Anfragen je Minute und offenem Tab). Die
   Schriften aus `SCHRIFTEN` lädt dieses Skript **beim Bauen** (nicht beim Besuch), prüft ihre
   Prüfsumme und legt sie an den Ort, an dem Flutter sie sucht. Braucht die App ein Zeichen aus
   einer weiteren Schrift: Die Konsole des Browsers nennt die Datei — hier eintragen.

5. **Das App-Archiv prüfen.** `flet build` packt den ganzen Ordner ``src/`` ein — auch den
   Datenordner der Desktop-Vorschau (``src/trainingsapp/ui/.flet/``: Datenbank, Messungen,
   GPS-Strecken). ``pyproject.toml`` schließt ihn aus (``[tool.flet.app] exclude``), und
   dieses Skript bricht ab, wenn im Archiv etwas liegt, das nicht im Repository steht
   (`archiv_befunde`; so am 14.11.2026 hochgeladen und wieder gesperrt).

**Zahlen über 0xFFFFFFFF** gehen im Browser nicht zwischen Dart und Python hin und her (die
Web-Fassung ist dart2js; ``erweiterungen/flet_ble``, ``_zeit``). Wer einer Erweiterung ein Feld
gibt, das so groß werden kann (Zeitstempel!), verliert dort still jede Nachricht.

Gebaut wird mit dem Python, das Flet für das Web wählt (Pyodide) — nicht mit dem der APK.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.request
import zipfile
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
AUSGABE = PROJEKT / "dist" / "web"
#: Version und Build-Nummer für die laufende App (wie `scripts/apk_bauen.py`)
BUILD_DATEI = PROJEKT / "src" / "trainingsapp" / "_build.py"
#: Geladene Schriften, nach Prüfsumme — bleibt zwischen den Builds liegen (.gitignore: /build/*)
SCHRIFT_ABLAGE = PROJEKT / "build" / "web-schriften"

#: Ersatzschriften, die die App im Browser braucht: Pfad unter ``assets/fonts/`` (so fragt
#: Flutter sie an), Quelle, SHA-256. Alle unter der SIL Open Font License.
SCHRIFTEN: tuple[tuple[str, str, str], ...] = (
    (
        "notosanssymbols/v43/rP2up3q65FkAtHfwd-eIS2brbDN6gxP34F9jRRCe4W3gfQ8gb_VFRkzrbQ.woff2",
        "https://fonts.gstatic.com/s/notosanssymbols/v43/"
        "rP2up3q65FkAtHfwd-eIS2brbDN6gxP34F9jRRCe4W3gfQ8gb_VFRkzrbQ.woff2",
        "08202e258ea583254c036cff46a7077bb5af4f82c41a6c0a6775f6e44d99f1aa",
    ),
)

#: Das App-Archiv im Web-Ordner: der Inhalt von ``src/`` und die Python-Pakete
APP_ARCHIV = Path("assets") / "app" / "app.zip"

_SKRIPT = re.compile(r"<script(?P<attr>[^>]*)>(?P<inhalt>.*?)</script>", re.S)
_FREMD = re.compile(r'(?:src|href)="https?://|Url: "https?://')


def basis_pruefen(basis: str) -> str:
    """Die Basisadresse: beginnt und endet mit „/“, sonst nur Buchstaben, Ziffern, - und _.

    >>> basis_pruefen("/app/AbC-1_x/")
    '/app/AbC-1_x/'
    >>> basis_pruefen("/")
    '/'
    >>> basis_pruefen("app/x")
    Traceback (most recent call last):
    ...
    ValueError: Die Basisadresse beginnt und endet mit „/“ (/app/<ordner>/), nicht 'app/x'
    """
    if not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*", basis):
        raise ValueError(
            f"Die Basisadresse beginnt und endet mit „/“ (/app/<ordner>/), nicht {basis!r}"
        )
    return basis


def skripte_auslagern(ordner: Path) -> int:
    """Inline-Skripte der ``index.html`` nach ``start-<n>.js``; liefert ihre Anzahl.

    Reihenfolge und Zeitpunkt bleiben: Ein gewöhnliches Skript mit ``src`` hält das Lesen der
    Seite an wie ein Inline-Skript. Skripte mit ``src`` und leere bleiben unberührt.
    """
    index = ordner / "index.html"
    n = 0

    def ersetzen(m: re.Match[str]) -> str:
        nonlocal n
        attr, inhalt = m.group("attr"), m.group("inhalt")
        if "src=" in attr or not inhalt.strip():
            return m.group(0)
        n += 1
        name = f"start-{n}.js"
        (ordner / name).write_text(inhalt.strip() + "\n", encoding="utf-8")
        return f'<script{attr} src="{name}"></script>'

    index.write_text(_SKRIPT.sub(ersetzen, index.read_text(encoding="utf-8")), encoding="utf-8")
    return n


def schrift_holen(quelle: str, sha256: str, ablage: Path = SCHRIFT_ABLAGE) -> Path:
    """Eine Schrift aus der Ablage — oder einmal laden, mit geprüfter Prüfsumme."""
    datei = ablage / sha256
    if not datei.is_file():
        if not quelle.startswith("https://"):
            raise ValueError(f"Schriften nur über https: {quelle}")
        ablage.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(quelle, timeout=30) as antwort:
            inhalt = antwort.read()
        if hashlib.sha256(inhalt).hexdigest() != sha256:
            raise ValueError(f"Prüfsumme stimmt nicht: {quelle}")
        datei.write_bytes(inhalt)
    elif hashlib.sha256(datei.read_bytes()).hexdigest() != sha256:
        raise ValueError(f"Prüfsumme der abgelegten Schrift stimmt nicht: {datei}")
    return datei


def schriften_einlegen(ordner: Path, ablage: Path = SCHRIFT_ABLAGE) -> int:
    """Die Ersatzschriften aus `SCHRIFTEN` dorthin, wo Flutter sie sucht; liefert ihre Zahl."""
    for pfad, quelle, sha256 in SCHRIFTEN:
        ziel = ordner / "assets" / "fonts" / pfad
        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(schrift_holen(quelle, sha256, ablage), ziel)
    return len(SCHRIFTEN)


def _startseite(ordner: Path) -> str:
    """``index.html`` samt der ausgelagerten Skripte — dort steht Flets Konfiguration."""
    teile = [ordner / "index.html", *sorted(ordner.glob("start-*.js"))]
    return "\n".join(t.read_text(encoding="utf-8") for t in teile if t.is_file())


def ohne_cdn(ordner: Path) -> bool:
    """Ist die Seite mit ``--no-cdn`` gebaut und nennt sie keine fremde Adresse?"""
    text = _startseite(ordner)
    return "noCdn: true" in text and _FREMD.search(text) is None


#: Was im App-Archiv außerhalb der Pakete liegen darf, ohne versioniert zu sein
_ARCHIV_ERLAUBT = ("trainingsapp/_build.py", "main.py")
_ARCHIV_ERLAUBT_ORDNER = ("trainingsapp.egg-info/",)


def versionierte_dateien() -> set[str] | None:
    """Die versionierten Dateien unter ``src/`` (relativ dazu) — ``None`` ohne git."""
    ausgabe = _git("ls-files", "-z", "src")
    if ausgabe is None:
        return None
    return {name.removeprefix("src/") for name in ausgabe.split("\0") if name}


def archiv_befunde(archiv: Path, versioniert: set[str] | None) -> list[str]:
    """Liegt im App-Archiv nur, was im Repository steht?

    `flet build` packt den ganzen Ordner ``src/`` ein — auch, was dort nur auf diesem Rechner
    liegt. Am 14.11.2026 war das der Datenordner der Desktop-Vorschau
    (``src/trainingsapp/ui/.flet/``, von `flet run` angelegt): Datenbank, Messdateien,
    GPS-Strecken und eine Audioaufnahme standen im Archiv einer hochgeladenen Seite. Darum:
    Außerhalb von ``__pypackages__/`` muss jede Datei versioniert sein (``.pyc`` zählt als
    ihr ``.py``), und kein Ordner oder Dateiname darf mit einem Punkt beginnen.

    Ohne git (``versioniert`` ist ``None``) lässt sich das nicht prüfen — das ist selbst
    ein Befund.
    """
    if not archiv.is_file():
        return [f"{archiv} fehlt"]
    with zipfile.ZipFile(archiv) as z:
        namen = [n for n in z.namelist() if not n.endswith("/")]
    eigene = [n for n in namen if not n.startswith("__pypackages__/")]
    fremd = []
    for name in eigene:
        if any(teil.startswith(".") for teil in name.split("/")):
            fremd.append(name)
            continue
        if versioniert is None:
            continue
        quelle = name[:-1] if name.endswith(".pyc") else name
        if quelle in versioniert or quelle in _ARCHIV_ERLAUBT:
            continue
        if not quelle.startswith(_ARCHIV_ERLAUBT_ORDNER):
            fremd.append(name)
    liste = []
    if fremd:
        zeigen = ", ".join(fremd[:5]) + (
            f" … und {len(fremd) - 5} weitere" if len(fremd) > 5 else ""
        )
        liste.append(
            f"Im App-Archiv liegen {len(fremd)} Datei(en), die nicht im Repository stehen "
            f"(Daten dieses Rechners?): {zeigen}"
        )
    if versioniert is None:
        liste.append("Das App-Archiv ließ sich nicht gegen das Repository prüfen (kein git)")
    return liste


def befunde(ordner: Path) -> list[str]:
    """Was an einem fertigen Web-Ordner nicht stimmt (leer = in Ordnung)."""
    index = ordner / "index.html"
    if not index.is_file():
        return [f"{index} fehlt"]
    liste = []
    for m in _SKRIPT.finditer(index.read_text(encoding="utf-8")):
        if "src=" not in m.group("attr") and m.group("inhalt").strip():
            liste.append("index.html enthält ein Inline-Skript — eine strenge CSP blockiert es")
            break
    text = _startseite(ordner)
    if "noCdn: true" not in text:
        liste.append("Die Seite ist nicht mit --no-cdn gebaut (noCdn: true fehlt)")
    if fremd := _FREMD.search(text):
        liste.append(f"Die Seite nennt eine fremde Adresse: {fremd.group(0)}…")
    for pfad, _quelle, _sha in SCHRIFTEN:
        if not (ordner / "assets" / "fonts" / pfad).is_file():
            liste.append(f"Ersatzschrift fehlt: assets/fonts/{pfad}")
    liste += archiv_befunde(ordner / APP_ARCHIV, versionierte_dateien())
    return liste


def _git(*argumente: str, ordner: Path = PROJEKT) -> str | None:
    """Ausgabe eines git-Befehls — ``None``, wenn er scheitert (kein Repository, kein git)."""
    try:
        ausgabe = subprocess.run(
            ["git", *argumente], cwd=ordner, capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return ausgabe.stdout.strip() if ausgabe.returncode == 0 else None


def version() -> str:
    with (PROJEKT / "pyproject.toml").open("rb") as f:
        return str(tomllib.load(f)["project"]["version"])


def stand(basis: str, ordner: Path | None = None) -> dict[str, object]:
    """Woraus dieser Build entstand — das Upload-Skript der Praxis liest es.

    ``sauber``: keine Änderungen an versionierten Dateien; ``gepusht``: der Commit liegt auf
    einem Zweig des Servers. Nur beides zusammen lässt sich aus dem Repository wiederherstellen.
    """
    schwestern = {}
    for name in ("hrv-core", "hrv-watch"):
        soll = (PROJEKT / f"{name}.ref").read_text(encoding="utf-8").strip()
        ist = _git("rev-parse", "HEAD", ordner=PROJEKT.parent / name) or ""
        schwestern[name] = {"commit": ist, "wie_ref": ist == soll}
    return {
        "version": version(),
        "commit": _git("rev-parse", "HEAD") or "",
        # Scheitert git, gilt der Stand als nicht sauber — nie umgekehrt.
        "sauber": _git("status", "--porcelain", "--untracked-files=no") == "",
        "gepusht": bool(_git("branch", "-r", "--contains", "HEAD")),
        "basis": basis,
        "ohne_cdn": ohne_cdn(ordner) if ordner is not None else False,
        # Nur was im Repository steht — das Upload-Skript der Praxis verlangt True.
        "archiv_geprueft": ordner is not None
        and archiv_befunde(ordner / APP_ARCHIV, versionierte_dateien()) == [],
        "gebaut": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "schwestern": schwestern,
    }


def nachbearbeiten(ordner: Path, basis: str) -> None:
    """Schritte 3 und 4 aus dem Kopf dieser Datei, dann ``stand.json`` — und die Prüfung."""
    n = skripte_auslagern(ordner)
    m = schriften_einlegen(ordner)
    werte = stand(basis, ordner)
    (ordner / "stand.json").write_text(
        json.dumps(werte, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Nachbearbeitet: {n} Inline-Skripte ausgelagert, {m} Ersatzschrift(en) eingelegt")
    if fehler := befunde(ordner):
        sys.exit("Der Web-Ordner ist nicht in Ordnung:\n  - " + "\n  - ".join(fehler))
    for name, schwester in werte["schwestern"].items():  # type: ignore[union-attr]
        if not schwester["wie_ref"]:
            print(f"Hinweis: ../{name} steht nicht auf dem Commit aus {name}.ref")
    if not (werte["sauber"] and werte["gepusht"]):
        print("Hinweis: nicht aus einem sauberen, gepushten Stand gebaut — nur zum Ausprobieren")


def main() -> None:
    parser = argparse.ArgumentParser(description="Web-Fassung der App bauen (statische Seite)")
    parser.add_argument(
        "--basis",
        required=True,
        help="Adresse, unter der die Seite liegt: /app/<ordner>/ auf dem Server, / lokal",
    )
    parser.add_argument("--ausgabe", type=Path, default=AUSGABE, help="Zielordner (dist/web)")
    parser.add_argument(
        "--nur-nachbearbeiten",
        action="store_true",
        help="nicht bauen: einen vorhandenen Ordner nachbearbeiten und prüfen",
    )
    args = parser.parse_args()
    try:
        basis = basis_pruefen(args.basis)
    except ValueError as fehler:
        sys.exit(str(fehler))
    ausgabe: Path = args.ausgabe.resolve()

    if not args.nur_nachbearbeiten:
        nummer = _git("rev-list", "--count", "HEAD") or "0"
        BUILD_DATEI.write_text(
            '"""Von scripts/web_bauen.py geschrieben — nicht bearbeiten, nicht committen."""\n\n'
            f'VERSION = "{version()}"\nBUILD = {nummer}\n',
            encoding="utf-8",
        )
        befehl = ["flet", "build", "web", "--no-cdn", "--yes", "--no-rich-output"]
        befehl += ["--base-url", basis, "--build-number", nummer, "-o", str(ausgabe)]
        print(f"Baue Web-Fassung {version()} (Build {nummer}) für {basis}")
        subprocess.run(befehl, cwd=PROJEKT, check=True)

    nachbearbeiten(ausgabe, basis)
    groesse = sum(d.stat().st_size for d in ausgabe.rglob("*") if d.is_file()) / 1e6
    print(f"Fertig: {ausgabe} ({groesse:.0f} MB)")
    if basis == "/":
        print(f"Ansehen: uv run flet serve {ausgabe}")


if __name__ == "__main__":
    main()
