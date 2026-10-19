"""``trainingsapp-paket`` — Paketdateien prüfen, bauen und einen Index schreiben.

Das Werkzeug für das Inhalte-Repo (`docs/uebungspakete.md`, „Inhalte pflegen“):
Pakete werden als TOML von Hand gepflegt, die App liest sie beim Start direkt
(``TRAININGSAPP_PAKETE``) — fürs Handy und für Paketquellen braucht es JSON.

    trainingsapp-paket pruefen pakete/*.toml [--wortliste DATEI] [--streng]
    trainingsapp-paket bauen pakete/*.toml --ziel dist/
    trainingsapp-paket index dist/*.json --ziel dist/index.json --basis-url https://…/pakete/
    trainingsapp-paket quelle https://…/pakete/index.json   # wie die App: Index + Prüfsummen

Die Wortliste (Sprachregelung der Praxis-Website, Zone 3: erklären, nicht bewerten)
liegt im privaten Repo der Homepage; das Werkzeug liest nur die Datei, die man
ihm gibt — eine Zeile je Begriff, ``#`` leitet Kommentare ein.

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
from collections.abc import Callable, Iterable
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
from trainingsapp.core.paketquelle import (
    INDEX_FORMAT,
    INDEX_VERSION,
    QuellenFehler,
    index_laden,
    paket_laden,
)
from trainingsapp.core.paketquelle import _laden as netz_laden
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


def wortliste_lesen(datei: Path) -> list[str]:
    """Begriffe aus einer Wortliste — eine Zeile je Begriff, ``#`` leitet Kommentare ein."""
    begriffe: list[str] = []
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        text = zeile.split("#", 1)[0].strip()
        if text:
            begriffe.append(text)
    return begriffe


def _texte(roh: dict[str, Any]) -> list[tuple[str, str]]:
    """``(Wo, Text)`` aller Texte eines Pakets, die jemand liest: Kopf, Übungen, Kurse."""
    texte: list[tuple[str, str]] = []
    kopf = roh.get("paket") or {}
    if isinstance(kopf, dict):
        for feld in ("name", "beschreibung", "neuigkeiten"):
            texte.append((f"Paket, {feld}", str(kopf.get(feld) or "")))
    for e in roh.get("exercises", []):
        if isinstance(e, dict):
            wo = f"Übung „{e.get('name', e.get('key', '?'))}“"
            texte.append((f"{wo}, Name", str(e.get("name") or "")))
            texte.append((f"{wo}, Beschreibung", str(e.get("description") or "")))
    for k in roh.get("kurse", []):
        if not isinstance(k, dict):
            continue
        wo = f"Kurs „{k.get('name', k.get('key', '?'))}“"
        texte.append((f"{wo}, Name", str(k.get("name") or "")))
        texte.append((f"{wo}, Beschreibung", str(k.get("beschreibung") or "")))
        for kap in k.get("kapitel", []):
            if isinstance(kap, dict):
                titel = kap.get("titel", kap.get("key", "?"))
                texte.append((f"{wo}, Kapitel „{titel}“, Titel", str(kap.get("titel") or "")))
                texte.append((f"{wo}, Kapitel „{titel}“, Text", str(kap.get("text") or "")))
    return texte


def wortliste_pruefen(roh: dict[str, Any], begriffe: Iterable[str]) -> list[str]:
    """Treffer der Wortliste in den Texten — Groß/klein egal, je Stelle ein Satz.

    >>> wortliste_pruefen({"exercises": [{"name": "A", "description": "Die Analyse zeigt …"}]},
    ...                   ["Analyse"])
    ['Übung „A“, Beschreibung: „Analyse“']
    """
    treffer: list[str] = []
    for wo, text in _texte(roh):
        klein = text.casefold()
        for begriff in begriffe:
            if begriff.casefold() in klein:
                treffer.append(f"{wo}: „{begriff}“")
    return treffer


def pruefen(
    datei: Path,
    symbole: Iterable[str] | None = None,
    wortliste: Iterable[str] = (),
    streng: bool = False,
) -> tuple[list[str], list[str]]:
    """``(Fehler, Hinweise)`` zu einer Paketdatei — dieselben Regeln wie der Test des
    Standardpakets: Schlüssel klein und ohne Umlaute, eindeutig; Beschreibung da; Original
    einer Variante vorhanden; Symbol aus der Auswahl (``symbole``, sonst ungeprüft).
    Typen und Regionen außerhalb des Standardpakets sind Hinweise, keine Fehler; Treffer der
    ``wortliste`` ebenso — mit ``streng`` werden sie Fehler."""
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
    for treffer in wortliste_pruefen(roh, wortliste):
        (fehler if streng else hinweise).append(f"Wortliste: {treffer}")
    return fehler, hinweise


def quelle_pruefen(
    url: str, laden: Callable[[str], bytes] | None = None
) -> tuple[list[str], list[str]]:
    """Index einer Quelle lesen und jedes Paket holen — ``(Zeilen, Fehler)``, wie die App."""
    laden = laden or netz_laden
    zeilen: list[str] = []
    fehler: list[str] = []
    try:
        name, eintraege = index_laden(url, laden)
    except QuellenFehler as f:
        return [], [f"{url}: {f}"]
    zeilen.append(f"Quelle „{name}“: {len(eintraege)} Paket(e)")
    for eintrag in eintraege:
        try:
            inhalt = paket_laden(eintrag, laden)
        except QuellenFehler as f:
            fehler.append(f"{eintrag.name} ({eintrag.url}): {f}")
            continue
        zeilen.append(
            f"  {eintrag.name} Version {eintrag.version}: {len(inhalt.uebungen)} Übungen, "
            f"{len(inhalt.kurse)} Kurs(e), {eintrag.bytes} B, Prüfsumme in Ordnung"
        )
    return zeilen, fehler


def bauen(datei: Path, ziel: Path) -> Path:
    """Schreibt die JSON-Paketdatei (Austauschformat) nach ``ziel`` und gibt den Pfad zurück."""
    inhalt: Paketinhalt = seed_inhalt(datei)
    ziel.mkdir(parents=True, exist_ok=True)
    pfad = ziel / dateiname(inhalt.paket)
    # ohne Zeitstempel: derselbe Quelltext ergibt dieselbe Datei und Prüfsumme (K28)
    pfad.write_bytes(paket_json(inhalt.paket, inhalt.uebungen, inhalt.kurse, mit_zeitstempel=False))
    return pfad


def index(
    dateien: Iterable[Path],
    basis_url: str = "",
    quelle: str = "",
    vorher: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Der Index einer Paketquelle: je Paketdatei ID, Name, Version, URL, SHA-256, Größe,
    Neuigkeiten. ``basis_url`` + Dateiname = Download-Adresse. ``signatur`` ist
    reserviert (Ben, 16.10.2026: erst, wenn Pakete von Dritten kommen).

    ``veroeffentlicht`` ist das Datum des letzten Inhaltswechsels je Paket, nicht das
    Build-Datum (K30): Paketdateien sind reproduzierbar (`paket_bauen` ohne
    Zeitstempel), darum bleibt bei gleicher Prüfsumme das Datum aus dem vorigen
    Index ``vorher`` stehen.

    >>> sorted(index([]).keys())
    ['format', 'pakete', 'quelle', 'version']
    """
    bekannt: dict[str, str] = {}
    for e in (vorher or {}).get("pakete") or []:
        if isinstance(e, dict) and e.get("sha256") and e.get("veroeffentlicht"):
            bekannt[str(e["sha256"])] = str(e["veroeffentlicht"])
    pakete: list[dict[str, Any]] = []
    for datei in dateien:
        daten = datei.read_bytes()
        inhalt = seed_inhalt(datei)
        sha256 = hashlib.sha256(daten).hexdigest()
        pakete.append(
            {
                "id": inhalt.paket.id,
                "name": inhalt.paket.name,
                "beschreibung": inhalt.paket.beschreibung,
                "version": inhalt.paket.version,
                "url": basis_url.rstrip("/") + "/" + datei.name if basis_url else datei.name,
                "sha256": sha256,
                "bytes": len(daten),
                "uebungen": len(inhalt.uebungen),
                "kurse": len(inhalt.kurse),
                "neuigkeiten": inhalt.paket.neuigkeiten,
                "veroeffentlicht": bekannt.get(sha256) or datetime.now(UTC).date().isoformat(),
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
    p.add_argument("--wortliste", type=Path, help="Begriffe, die in Texten nichts verloren haben")
    p.add_argument("--streng", action="store_true", help="Treffer der Wortliste sind Fehler")
    b = sub.add_parser("bauen", help="JSON-Paketdateien schreiben")
    b.add_argument("dateien", nargs="+", type=Path)
    b.add_argument("--ziel", type=Path, default=Path("dist"))
    i = sub.add_parser("index", help="Index einer Paketquelle schreiben")
    i.add_argument("dateien", nargs="+", type=Path)
    i.add_argument("--ziel", type=Path, default=Path("dist/index.json"))
    i.add_argument("--basis-url", default="", help="Adresse, unter der die Dateien liegen")
    i.add_argument("--quelle", default="", help="Name der Quelle, wie die App ihn zeigt")
    q = sub.add_parser("quelle", help="Index einer Quelle lesen und alle Pakete prüfen")
    q.add_argument("url")
    args = parser.parse_args(argv)

    if args.befehl == "pruefen":
        symbole = _symbole()
        begriffe = wortliste_lesen(args.wortliste) if args.wortliste else []
        schlecht = 0
        for datei in args.dateien:
            fehler, hinweise = pruefen(datei, symbole, begriffe, args.streng)
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
    if args.befehl == "quelle":
        zeilen, fehler = quelle_pruefen(args.url)
        for z in zeilen:
            print(z)
        for f in fehler:
            print(f"FEHLER: {f}")
        return 1 if fehler else 0
    if args.befehl == "index":
        vorher = None
        if args.ziel.is_file():  # Datum unveränderter Pakete übernehmen (K30)
            try:
                vorher = json.loads(args.ziel.read_text("utf-8"))
            except ValueError:
                vorher = None
        daten = index(args.dateien, args.basis_url, args.quelle, vorher)
        args.ziel.parent.mkdir(parents=True, exist_ok=True)
        args.ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(f"{args.ziel}: {len(daten['pakete'])} Paket(e)")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
