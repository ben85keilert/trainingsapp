"""``trainingsapp-paket`` — Paketdateien prüfen, bauen und einen Index schreiben.

Das Werkzeug für das Inhalte-Repo (`docs/uebungspakete.md`, „Inhalte pflegen“):
Pakete werden als TOML von Hand gepflegt, die App liest sie beim Start direkt
(``TRAININGSAPP_PAKETE``) — fürs Handy und für Paketquellen braucht es JSON.

    trainingsapp-paket pruefen pakete/*.toml
    trainingsapp-paket bauen pakete/*.toml --ziel dist/
    trainingsapp-paket index dist/*.json --ziel dist/index.json --basis-url https://…/pakete/

Es importiert kein flet (die Symbolprüfung läuft nur, wenn flet da ist) und
liegt in der trainingsapp, nicht im privaten Inhalte-Repo: Öffentliche Repos
hängen nie von privaten ab, umgekehrt schon.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trainingsapp.core.pakete import (
    FORMAT_VERSION,
    PaketFehler,
    Paketinhalt,
    dateiname,
    paket_json,
)
from trainingsapp.core.paketquelle import INDEX_FORMAT, INDEX_VERSION
from trainingsapp.data.seed import seed_inhalt

#: Typen und Regionen des Pakets „Standard“ — ein Paket darf eigene mitbringen
#: (Qigong, Meridiane …), das Werkzeug merkt es nur an: Ein Tippfehler legte
#: sonst auf jedem Gerät einen neuen Tag an.
STANDARD_TYPEN: frozenset[str] = frozenset(
    {
        "Atmung",
        "Entspannung",
        "HRV",
        "Mobilisation",
        "Dehnung",
        "Kräftigung",
        "Isometrie",
        "Gleichgewicht",
        "Ausdauer",
        "Benchmark",
        "Messung",
    }
)
STANDARD_REGIONEN: frozenset[str] = frozenset(
    {"Nacken", "Schulter", "Arm", "Hand", "Rumpf", "Rücken", "Hüfte", "Bein", "Fuß"}
)
_KEY = re.compile(r"[a-z0-9_]+")


def _roh(datei: Path) -> dict[str, Any]:
    """Die Datei als Wörterbuch, TOML oder JSON — wie `data.seed.seed_inhalt` sie liest."""
    import tomllib

    text = datei.read_text(encoding="utf-8")
    return tomllib.loads(text) if datei.suffix == ".toml" else json.loads(text)


def pruefen(datei: Path, symbole: Iterable[str] | None = None) -> tuple[list[str], list[str]]:
    """``(Fehler, Hinweise)`` zu einer Paketdatei — dieselben Regeln wie der Test des
    Standardpakets: Schlüssel klein und ohne Umlaute, eindeutig; Beschreibung da; Original
    einer Variante vorhanden; Symbol aus der Auswahl (``symbole``, sonst ungeprüft).
    Typen und Regionen außerhalb des Standardpakets sind Hinweise, keine Fehler."""
    fehler: list[str] = []
    hinweise: list[str] = []
    try:
        inhalt = seed_inhalt(datei)
    except PaketFehler as f:
        return [str(f)], []
    try:
        roh = _roh(datei)
    except (ValueError, OSError) as f:
        return [f"{datei.name}: {f}"], []
    eintraege = roh.get("exercises", [])
    keys = [str(e.get("key", "")) for e in eintraege if isinstance(e, dict)]
    for k in keys:
        if not _KEY.fullmatch(k):
            fehler.append(f"key {k!r}: nur a-z, 0-9 und _ (nie ändern — die ID folgt daraus)")
    doppelt = {k for k in keys if keys.count(k) > 1}
    for k in sorted(doppelt):
        fehler.append(f"key {k!r} kommt mehrfach vor")
    symbolmenge = set(symbole) if symbole is not None else None
    for e in eintraege:
        if not isinstance(e, dict):
            continue
        wo = f"Übung „{e.get('name', e.get('key', '?'))}“"
        if not str(e.get("description", "")).strip():
            fehler.append(f"{wo}: Beschreibung fehlt")
        if symbolmenge is not None and e.get("icon_key") not in symbolmenge:
            fehler.append(f"{wo}: Symbol {e.get('icon_key')!r} ist nicht in der Auswahl")
        if (orig := e.get("variante_von")) and orig not in keys:
            fehler.append(f"{wo}: Original {orig!r} der Variante fehlt im Paket")
        for typ in set(e.get("typen", [])) - STANDARD_TYPEN:
            hinweise.append(f"{wo}: Typ „{typ}“ ist nicht im Standardpaket (gewollt?)")
        for region in set(e.get("regionen", [])) - STANDARD_REGIONEN:
            hinweise.append(f"{wo}: Region „{region}“ ist nicht im Standardpaket (gewollt?)")
    if inhalt.paket.version is None:
        hinweise.append("Kopf ohne `version` — ohne sie erkennt kein Gerät ein Update")
    return fehler, hinweise


def bauen(datei: Path, ziel: Path) -> Path:
    """Schreibt die JSON-Paketdatei (Austauschformat) nach ``ziel`` und gibt den Pfad zurück."""
    inhalt: Paketinhalt = seed_inhalt(datei)
    ziel.mkdir(parents=True, exist_ok=True)
    pfad = ziel / dateiname(inhalt.paket)
    pfad.write_bytes(paket_json(inhalt.paket, inhalt.uebungen, inhalt.kurse))
    return pfad


def index(dateien: Iterable[Path], basis_url: str = "", quelle: str = "") -> dict[str, Any]:
    """Der Index einer Paketquelle: je Paketdatei ID, Name, Version, URL, SHA-256, Größe,
    Neuigkeiten. ``basis_url`` + Dateiname = Download-Adresse. ``signatur`` ist
    reserviert (Ben, 16.10.2026: erst, wenn Pakete von Dritten kommen).

    >>> sorted(index([]).keys())
    ['format', 'pakete', 'quelle', 'version']
    """
    pakete: list[dict[str, Any]] = []
    for datei in dateien:
        daten = datei.read_bytes()
        inhalt = seed_inhalt(datei)
        pakete.append(
            {
                "id": inhalt.paket.id,
                "name": inhalt.paket.name,
                "beschreibung": inhalt.paket.beschreibung,
                "version": inhalt.paket.version,
                "url": basis_url.rstrip("/") + "/" + datei.name if basis_url else datei.name,
                "sha256": hashlib.sha256(daten).hexdigest(),
                "bytes": len(daten),
                "uebungen": len(inhalt.uebungen),
                "kurse": len(inhalt.kurse),
                "neuigkeiten": inhalt.paket.neuigkeiten,
                "veroeffentlicht": datetime.now(UTC).date().isoformat(),
                "format_version": FORMAT_VERSION if inhalt.kurse else 1,
                "signatur": None,
            }
        )
    return {
        "format": INDEX_FORMAT,
        "version": INDEX_VERSION,
        "quelle": {"name": quelle},
        "pakete": pakete,
    }


def _symbole() -> list[str] | None:
    try:
        from trainingsapp.ui.components.icons import AUSWAHL
    except ImportError:  # kein flet: Symbole bleiben ungeprüft
        return None
    return list(AUSWAHL)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trainingsapp-paket", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="befehl", required=True)
    p = sub.add_parser("pruefen", help="Paketdateien prüfen (TOML oder JSON)")
    p.add_argument("dateien", nargs="+", type=Path)
    b = sub.add_parser("bauen", help="JSON-Paketdateien schreiben")
    b.add_argument("dateien", nargs="+", type=Path)
    b.add_argument("--ziel", type=Path, default=Path("dist"))
    i = sub.add_parser("index", help="Index einer Paketquelle schreiben")
    i.add_argument("dateien", nargs="+", type=Path)
    i.add_argument("--ziel", type=Path, default=Path("dist/index.json"))
    i.add_argument("--basis-url", default="", help="Adresse, unter der die Dateien liegen")
    i.add_argument("--quelle", default="", help="Name der Quelle, wie die App ihn zeigt")
    args = parser.parse_args(argv)

    if args.befehl == "pruefen":
        symbole = _symbole()
        schlecht = 0
        for datei in args.dateien:
            fehler, hinweise = pruefen(datei, symbole)
            for text in hinweise:
                print(f"{datei}: Hinweis: {text}")
            for text in fehler:
                print(f"{datei}: FEHLER: {text}")
            schlecht += bool(fehler)
            if not fehler:
                print(f"{datei}: in Ordnung")
        if symbole is None:
            print("(Symbole ungeprüft — flet nicht installiert)")
        return 1 if schlecht else 0
    if args.befehl == "bauen":
        for datei in args.dateien:
            fehler, _ = pruefen(datei)
            if fehler:
                print(f"{datei}: nicht gebaut — " + "; ".join(fehler))
                return 1
            print(bauen(datei, args.ziel))
        return 0
    if args.befehl == "index":
        daten = index(args.dateien, args.basis_url, args.quelle)
        args.ziel.parent.mkdir(parents=True, exist_ok=True)
        args.ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(f"{args.ziel}: {len(daten['pakete'])} Paket(e)")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
