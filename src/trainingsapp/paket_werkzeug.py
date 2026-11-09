"""``trainingsapp-paket`` — Paketdateien prüfen, bauen und einen Index schreiben.

Das Werkzeug für das Inhalte-Repo (`docs/uebungspakete.md`, „Inhalte pflegen“):
Pakete werden als TOML von Hand gepflegt, die App liest sie beim Start direkt
(``TRAININGSAPP_PAKETE``) — fürs Handy und für Paketquellen braucht es JSON.

    trainingsapp-paket pruefen pakete/*.toml [--wortliste DATEI] [--streng]
    trainingsapp-paket bauen pakete/*.toml --ziel dist/
    trainingsapp-paket index dist/*.json --ziel dist/index.json --basis-url https://…/pakete/
    trainingsapp-paket quelle https://…/pakete/index.json   # wie die App: Index + Prüfsummen
    trainingsapp-paket uebernehmen export.json pakete/standard.toml [--probe]
    trainingsapp-paket uebernehmen .daten/trainingsapp.db pakete/standard.toml [--probe]

``uebernehmen`` holt, was in der App eingestellt wurde, in die TOML-Datei zurück (Ben,
27.10.2026): aus dem Export des Paketmanagers (JSON mit IDs) die Übungen, aus der
Datenbank der App (nur lesend) Übungen und die Pläne, die Kurskapitel angelegt haben.
Je Übung über die ID dem ``[[exercises]]``-Block zugeordnet, geänderte Felder dort
eingetragen — ``key``, Kommentare, Abschnitte und Kurse bleiben (``tomlkit``, nur im
Werkzeug).

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
import sqlite3
import sys
import tempfile
import tomllib
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trainingsapp.core.ablauf import ablauf_pruefen
from trainingsapp.core.bedingung import bedingung_pruefen
from trainingsapp.core.ergaenzungen import ERGAENZBAR
from trainingsapp.core.kurse import Kapitel, Kurs, PlanVorlage, VorlageItem
from trainingsapp.core.links import erlaubt as links_erlaubt
from trainingsapp.core.models import Exercise, Plan
from trainingsapp.core.paketdatei import (
    dateien_einbinden,
    medienlisten,
    paket_oeffnen,
    paket_zip,
    toml_oeffnen,
)
from trainingsapp.core.pakete import (
    FELDNAMEN,
    NAMENSRAUM,
    Paket,
    PaketFehler,
    Paketinhalt,
    dateiname,
    paket_json,
    paket_lesen,
    stand,
)
from trainingsapp.core.paketmedien import medium_aus_paket
from trainingsapp.core.paketquelle import (
    INDEX_FORMAT,
    INDEX_VERSION,
    QuellenFehler,
    index_laden,
    link_lesen,
    paket_laden,
)
from trainingsapp.core.paketquelle import _laden as netz_laden
from trainingsapp.core.paketstufe import STUFE_TEXT, mindestens, stufen_text, version_reicht
from trainingsapp.core.paketstufe import stufe as paket_stufe
from trainingsapp.core.paketversion import version_text
from trainingsapp.core.privat import (
    code_neu,
    code_text,
    datei_verschluesseln,
    ist_privat,
    ordner_neu,
)
from trainingsapp.core.result_spec import VORLAGEN
from trainingsapp.core.takt import takt_pruefen
from trainingsapp.core.zaehlen import wahl_pruefen
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
    for pl in roh.get("plaene", []):
        if isinstance(pl, dict):
            wo = f"Plan „{pl.get('name', pl.get('key', '?'))}“"
            texte.append((f"{wo}, Name", str(pl.get("name") or "")))
            texte.append((f"{wo}, Beschreibung", str(pl.get("beschreibung") or "")))
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


def _plaene_mit_ort(roh: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """``(Wo, Plan)`` aller Pläne eines Pakets: ``plaene[]`` und die der Kurskapitel.

    >>> roh = {"plaene": [{"name": "Morgen"}], "kurse": [{"name": "K", "kapitel": [
    ...     {"titel": "T", "plaene": [{"name": "Stehen"}]}]}]}
    >>> [wo for wo, _ in _plaene_mit_ort(roh)]
    ['Plan „Morgen“', 'Kurs „K“, Kapitel „T“, Plan „Stehen“']
    """
    out: list[tuple[str, dict[str, Any]]] = []
    for pl in roh.get("plaene") or []:
        if isinstance(pl, dict):
            out.append((f"Plan „{pl.get('name', pl.get('key', '?'))}“", pl))
    for k in roh.get("kurse") or []:
        if not isinstance(k, dict):
            continue
        wo = f"Kurs „{k.get('name', k.get('key', '?'))}“"
        for kap in k.get("kapitel") or []:
            if not isinstance(kap, dict):
                continue
            titel = kap.get("titel", kap.get("key", "?"))
            for pl in kap.get("plaene") or []:
                if isinstance(pl, dict):
                    name = pl.get("name", "?")
                    out.append((f"{wo}, Kapitel „{titel}“, Plan „{name}“", pl))
    return out


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
    Standardpakets: Schlüssel klein und ohne Umlaute, eindeutig; Beschreibung da; Symbol
    aus der Auswahl (``symbole``, sonst ungeprüft).
    Typen und Regionen außerhalb des Standardpakets sind Hinweise, keine Fehler; Treffer der
    ``wortliste`` ebenso — mit ``streng`` werden sie Fehler. In ``beschleunigung`` (Karte
    „Beschleunigungssensor“) ist ein falscher Typ ein Fehler, ein unbekannter Schlüssel ein
    Hinweis (`core.zaehlen.wahl_pruefen`) — die App läse beides still als Vorgabe. Für ``takt``
    (`core.takt.takt_pruefen`) ebenso: unbrauchbare Dauer oder Tempo ein Fehler, unbekannte
    Art, Klang oder Schlüssel ein Hinweis. Beides auch **je Planübung** in
    ``plaene[].uebungen[]`` und ``kurse[].kapitel[].plaene[].uebungen[]`` (A6) — mit dem Weg
    dorthin; ein unlesbarer Takt heißt dort „die Planübung folgt der Übung“."""
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
        for typ in set(e.get("typen", [])) - STANDARD_TYPEN:
            hinweise.append(f"{wo}: Typ „{typ}“ ist nicht im Standardpaket (gewollt?)")
        for region in set(e.get("regionen", [])) - STANDARD_REGIONEN:
            hinweise.append(f"{wo}: Region „{region}“ ist nicht im Standardpaket (gewollt?)")
        if "beschleunigung" in e:
            f_acc, h_acc = wahl_pruefen(e["beschleunigung"])
            fehler.extend(f"{wo}: beschleunigung: {x}" for x in f_acc)
            hinweise.extend(f"{wo}: beschleunigung: {x}" for x in h_acc)
        if "takt" in e:
            f_takt, h_takt = takt_pruefen(e["takt"])
            fehler.extend(f"{wo}: takt: {x}" for x in f_takt)
            hinweise.extend(f"{wo}: takt: {x}" for x in h_takt)
        if "bedingung" in e:
            f_bed, h_bed = bedingung_pruefen(e["bedingung"])
            fehler.extend(f"{wo}: bedingung: {x}" for x in f_bed)
            hinweise.extend(f"{wo}: bedingung: {x}" for x in h_bed)
    for wo, pl in _plaene_mit_ort(roh):
        if "ablauf" in pl:
            f_ab, h_ab = ablauf_pruefen(pl["ablauf"])
            fehler.extend(f"{wo}: ablauf: {x}" for x in f_ab)
            hinweise.extend(f"{wo}: ablauf: {x}" for x in h_ab)
        for pe in pl.get("uebungen") or []:
            if not isinstance(pe, dict):
                continue
            wo_pe = f"{wo}, Übung „{pe.get('uebung', '?')}“"
            if "beschleunigung" in pe:
                f_acc, h_acc = wahl_pruefen(pe["beschleunigung"])
                fehler.extend(f"{wo_pe}: beschleunigung: {x}" for x in f_acc)
                hinweise.extend(f"{wo_pe}: beschleunigung: {x}" for x in h_acc)
            if "takt" in pe and pe["takt"] != {}:  # `takt = {}` = ausdrücklich keiner
                f_takt, h_takt = takt_pruefen(pe["takt"], ohne="die Planübung folgt der Übung")
                fehler.extend(f"{wo_pe}: takt: {x}" for x in f_takt)
                hinweise.extend(f"{wo_pe}: takt: {x}" for x in h_takt)
            if "bedingung" in pe:
                f_bed, h_bed = bedingung_pruefen(pe["bedingung"], im_plan=True)
                fehler.extend(f"{wo_pe}: bedingung: {x}" for x in f_bed)
                hinweise.extend(f"{wo_pe}: bedingung: {x}" for x in h_bed)
            hinweise.extend(f"{wo_pe}: {x}" for x in _planmedien_pruefen(pe.get("medien")))
    if datei.suffix == ".toml" and _nennt_dateien(roh):
        with tempfile.TemporaryDirectory() as arbeit:
            try:
                dateien = dateien_einbinden(roh, datei.parent, Path(arbeit))
            except PaketFehler as f:
                fehler.append(f"Dateien: {f}")
            else:
                groesse = sum(p.stat().st_size for p in dateien.values())
                hinweise.append(
                    f"{len(dateien)} Datei(en), bereinigt {groesse / 1e6:.1f} MB — "
                    "`bauen` schreibt eine ZIP (Formatversion 4)"
                )
    for x in roh.get("ergaenzungen") or []:  # U5: was eine Ergänzung nicht darf, fällt weg
        if isinstance(x, dict):
            fremd = sorted(k for k in x if k not in ("uebung", "paket", *ERGAENZBAR))
            if fremd:
                hinweise.append(
                    f"Ergänzung „{x.get('uebung')}“: {', '.join(fremd)} — darf eine Ergänzung "
                    "nicht setzen, fällt weg"
                )
    if inhalt.paket.version is None:
        hinweise.append("Kopf ohne `version` — ohne sie erkennt kein Gerät ein Update")
    for treffer in wortliste_pruefen(roh, wortliste):
        (fehler if streng else hinweise).append(f"Wortliste: {treffer}")
    return fehler, hinweise


def _nennt_dateien(roh: dict[str, Any]) -> bool:
    """Nennt die TOML Dateien (``datei = "…"``)?"""
    return any(isinstance(e, dict) and "datei" in e for liste in medienlisten(roh) for e in liste)


def _planmedien_pruefen(roh: Any) -> list[str]:
    """Hinweise zu ``medien`` einer Planübung (U2): was die App beim Import still weglässt —
    keine Liste, ein Link ohne https, eine Datei vom Gerät, ein Ton.

    >>> _planmedien_pruefen([{"uri": "https://x.org/v"}, {"uri": "http://x.org/a"}])
    ['medien: „http://x.org/a“ fällt weg (nur https-Adressen)']
    >>> _planmedien_pruefen("x"), _planmedien_pruefen(None)
    (['medien: keine Liste — fällt weg'], [])
    """
    if roh is None:
        return []
    if not isinstance(roh, list):
        return ["medien: keine Liste — fällt weg"]
    out: list[str] = []
    for e in roh:
        if isinstance(e, dict) and "datei" in e:
            continue  # eine Datei neben der TOML — prüft `dateien_einbinden`
        if isinstance(e, dict) and e.get("source") == "paket":
            if not medium_aus_paket(e):
                out.append(f"medien: „{e.get('uri')}“ ist kein Name einer Paketdatei")
            continue
        uri = str(e.get("uri") or "").strip() if isinstance(e, dict) else ""
        if not isinstance(e, dict) or not uri:
            out.append("medien: ein Eintrag ohne Adresse fällt weg")
        elif e.get("source") == "local" or e.get("kind") == "audio":
            out.append(f"medien: „{uri}“ fällt weg (keine Datei vom Gerät, kein Ton)")
        elif not links_erlaubt(uri):
            out.append(f"medien: „{uri}“ fällt weg (nur https-Adressen)")
    return out


def gegen_pruefen(
    datei: Path, gegen: str, laden: Callable[[str], bytes] | None = None
) -> tuple[list[str], list[str]]:
    """``(Fehler, Hinweise)``: Passt die Version von ``datei`` zur Stufe ihres Unterschieds zur
    veröffentlichten Fassung ``gegen`` (eine Datei, ein Link auf eine Paketdatei oder ein Index —
    U6, `core/paketstufe.py`)? Eine zu kleine Nummer ist ein Fehler („Kniebeuge fällt weg →
    mindestens 2.0.0, steht 1.4.0“)."""
    laden = laden or netz_laden
    with tempfile.TemporaryDirectory() as arbeit:
        try:
            neu = (
                toml_oeffnen(datei, Path(arbeit))
                if datei.suffix == ".toml"
                else paket_oeffnen(datei)
            )
            if Path(gegen).is_file():
                alt = paket_oeffnen(Path(gegen))
            else:
                art, wert = link_lesen(gegen, laden)
                if art == "paket":
                    alt = wert[1]
                else:
                    eintrag = next((e for e in wert[1] if e.id == neu.paket.id), None)
                    if eintrag is None:
                        return [], [
                            f"„{neu.paket.name}“ steht noch nicht in {gegen} — die erste Fassung"
                        ]
                    alt = paket_laden(eintrag, laden)
        except (PaketFehler, QuellenFehler) as f:
            return [f"--gegen: {f}"], []
    s = paket_stufe(alt, neu)
    if not version_reicht(alt.paket.version, neu.paket.version, s.stufe):
        return [
            f"{STUFE_TEXT[s.stufe]} ({stufen_text(s.gruende)}) → mindestens "
            f"{mindestens(alt.paket.version, s.stufe)}, steht {version_text(neu.paket.version)}"
        ], []
    return [], [
        f"gegen {version_text(alt.paket.version)}: {STUFE_TEXT[s.stufe]}"
        + (f" ({stufen_text(s.gruende)})" if s.gruende else "")
    ]


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
            f"  {eintrag.name} Version {version_text(eintrag.version)}: "
            f"{len(inhalt.uebungen)} Übungen, "
            f"{len(inhalt.kurse)} Kurs(e), {len(inhalt.plaene)} Plan/Pläne, {eintrag.bytes} B, "
            "Prüfsumme in Ordnung"
        )
    return zeilen, fehler


def _zugang(datei: Path) -> dict[str, str]:
    """Ordner und Code eines privaten Pakets (U7) — beim ersten Bauen angelegt und neben der
    TOML gemerkt (``<name>.zugang.json``, nur im privaten Inhalte-Repo!); danach dieselben:
    derselbe Link, derselbe Code für jede neue Fassung."""
    pfad = datei.with_name(datei.stem + ".zugang.json")
    if pfad.is_file():
        try:
            wert = json.loads(pfad.read_text("utf-8"))
        except ValueError:
            wert = None
        if isinstance(wert, dict) and wert.get("ordner") and wert.get("code"):
            return {"ordner": str(wert["ordner"]), "code": str(wert["code"])}
    zugang = {"ordner": ordner_neu(), "code": code_neu()}
    pfad.write_text(json.dumps(zugang, indent=2) + "\n", "utf-8")
    return zugang


def privat_bauen(datei: Path, ziel: Path, basis_url: str = "") -> tuple[Path, str]:
    """Ein privates Paket (U7, TOML mit ``[privat] fuer = "…"``): bauen wie immer, dann
    verschlüsselt nach ``<ziel>/p/<ordner>/paket.json`` (bzw. ``.zip``) — ``(Datei,
    Zugangskarte)``. Die Karte (Link + Code) steht zusätzlich neben der TOML."""
    roh = tomllib.loads(datei.read_text("utf-8"))
    fuer = " ".join(str((roh.get("privat") or {}).get("fuer") or "").split())
    zugang = _zugang(datei)
    with tempfile.TemporaryDirectory() as arbeit:
        klar = bauen(datei, Path(arbeit), fuer=fuer)
        ordner = ziel / "p" / zugang["ordner"]
        ordner.mkdir(parents=True, exist_ok=True)
        pfad = ordner / ("paket" + klar.suffix)
        datei_verschluesseln(klar, pfad, zugang["code"])
    rel = f"p/{zugang['ordner']}/{pfad.name}"
    link = basis_url.rstrip("/") + "/" + rel if basis_url else rel
    name = paket_oeffnen(pfad, code=zugang["code"]).paket.name
    karte = "\n".join(
        [
            f"Privates Paket „{name}“" + (f" für {fuer}" if fuer else ""),
            f"Link: {link}",
            f"Code: {code_text(zugang['code'])}",
            "Link und Code getrennt weitergeben (z. B. Link per Nachricht, Code mündlich).",
        ]
    )
    datei.with_name(datei.stem + ".zugangskarte.txt").write_text(karte + "\n", "utf-8")
    try:  # QR-Code des Links, wenn `segno` da ist — nur am Rechner, nie in der App
        import segno

        segno.make(link).save(str(datei.with_name(datei.stem + ".zugang.svg")), scale=6)
    except ImportError:
        pass
    return pfad, karte


def bauen(datei: Path, ziel: Path, *, fuer: str = "") -> Path:
    """Schreibt die Paketdatei nach ``ziel`` und gibt den Pfad zurück — JSON, oder eine ZIP
    (Formatversion 4), wenn die TOML Dateien nennt (``datei = "…"``, U3): jede bereinigt
    (`core/bereinigen.py`), benannt nach ihrer Prüfsumme. Wirft `PaketFehler`."""
    ziel.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as arbeit:
        if datei.suffix == ".toml":
            inhalt: Paketinhalt = toml_oeffnen(datei, Path(arbeit))
        else:
            inhalt = paket_oeffnen(datei)
        if fuer:  # privates Paket (U7): für wen — die App zeigt es
            inhalt.paket.fuer = fuer
        # ohne Zeitstempel: derselbe Quelltext ergibt dieselbe Datei und Prüfsumme (K28)
        json_daten = paket_json(
            inhalt.paket,
            inhalt.uebungen,
            inhalt.kurse,
            mit_zeitstempel=False,
            plaene=inhalt.plaene or None,
            ergaenzungen=inhalt.ergaenzungen or None,
        )
        namen = inhalt.medien_namen()
        if not namen:
            pfad = ziel / dateiname(inhalt.paket)
            pfad.write_bytes(json_daten)
            return pfad
        if fehlen := sorted(namen - set(inhalt.medien)):
            raise PaketFehler(f"Dateien fehlen: {', '.join(fehlen)}")
        dateien: dict[str, Path] = {}
        for name in namen:  # aus der ZIP bzw. der Arbeitskopie in eine Datei
            pfad_ = Path(arbeit) / ("z_" + name.removeprefix("medien/"))
            if not pfad_.is_file():
                inhalt.medien[name].kopieren(pfad_)
            dateien[name] = pfad_
        pfad = ziel / dateiname(inhalt.paket, "zip")
        paket_zip(pfad, json_daten, dateien)
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
        if ist_privat(daten[:8]):
            continue  # private Pakete (U7) stehen nie im öffentlichen Index
        inhalt = paket_oeffnen(datei)  # JSON, TOML oder ZIP (U3)
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
                "plaene": len(inhalt.plaene),
                "neuigkeiten": inhalt.paket.neuigkeiten,
                "veroeffentlicht": bekannt.get(sha256) or datetime.now(UTC).date().isoformat(),
                "format_version": 5
                if inhalt.ergaenzungen
                else 4
                if inhalt.medien
                else 3
                if inhalt.plaene
                else 2
                if inhalt.kurse
                else 1,
                "signatur": None,
            }
        )
    return {
        "format": INDEX_FORMAT,
        "version": INDEX_VERSION,
        "quelle": {"name": quelle},
        "pakete": pakete,
    }


# ---------------------------------------------------------------------------
# Übernehmen: aus der App zurück ins TOML
# ---------------------------------------------------------------------------

#: Vor jeder Tabelle auf oberster Ebene eine Leerzeile — tomlkit lässt sie nach einer
#: eingefügten Untertabelle weg
_TABELLE_OHNE_LEERZEILE = re.compile(r"([^\n])\n(\[\[?[A-Za-z_]+\]\]?\n)")


def _tomlkit() -> Any:
    try:
        import tomlkit
    except ImportError as fehler:  # nur im Werkzeug nötig, nicht in der App
        raise PaketFehler(
            "tomlkit fehlt — in der trainingsapp `uv sync` ausführen (Gruppe dev)"
        ) from fehler
    return tomlkit


def _toml_wert(wert: Any) -> Any:
    """Ein Wert fürs TOML: Wörterbücher als Inline-Tabellen (`limit_spec = { rules = … }`),
    Listen als Arrays in einer Zeile."""
    tomlkit = _tomlkit()
    if isinstance(wert, dict):
        t = tomlkit.inline_table()
        for k, v in wert.items():
            t[k] = _toml_wert(v)
        return t
    if isinstance(wert, list):
        a = tomlkit.array()
        for v in wert:
            a.append(_toml_wert(v))
        return a
    return wert


def _toml_tabelle(wert: dict[str, Any]) -> Any:
    """Ein Wörterbuch als eigene Tabelle (`[exercises.result_spec]`): verschachtelte
    Wörterbücher werden Untertabellen, Listen von Wörterbüchern `[[…]]`-Blöcke."""
    tomlkit = _tomlkit()
    t = tomlkit.table()
    for k, v in wert.items():
        if isinstance(v, dict):
            t[k] = _toml_tabelle(v)
        elif isinstance(v, list) and v and all(isinstance(e, dict) for e in v):
            aot = tomlkit.aot()
            for e in v:
                aot.append(_toml_tabelle(e))
            t[k] = aot
        else:
            t[k] = _toml_wert(v)
    return t


def _timer_fuers_toml(profile: list[dict[str, Any]], uebung: str) -> list[dict[str, Any]]:
    """Timer-Profile ohne die IDs, die der Leser ohnehin aus Übung und Stelle rechnet."""
    ergebnis: list[dict[str, Any]] = []
    for i, p in enumerate(profile):
        d = dict(p)
        if d.get("id") == str(uuid.uuid5(NAMENSRAUM, f"{uebung}/timer/{i}")):
            del d["id"]
        ergebnis.append(d)
    return ergebnis


def _feld_setzen(block: Any, feld: str, wert: Any, uebung: Exercise) -> None:
    """Ein Feld des Paketstands in den TOML-Block schreiben — fehlt der Wert, fällt das
    Feld weg (Vorgabe). Parameter, die einer Vorlage entsprechen, werden `spec = "…"`."""
    if feld == "result_spec":
        for kurz, (_, vorlage) in VORLAGEN.items():
            if vorlage.to_dict() == wert:
                block.pop("result_spec", None)
                block["spec"] = kurz
                return
        block.pop("spec", None)
        block["result_spec"] = _toml_tabelle(wert)
        return
    if feld == "timer":
        wert = _timer_fuers_toml(wert or [], uebung.id)
        if wert:
            block["timer"] = _toml_tabelle({"timer": wert})["timer"]
        else:
            block.pop("timer", None)
        return
    if wert is None or wert == "" or wert == [] or wert == {}:
        block.pop(feld, None)
        return
    block[feld] = _toml_wert(wert)


def _anders(feld: str, alt: Any, neu: Any) -> bool:
    """Typen und Regionen sind Mengen — die App führt sie in anderer Reihenfolge als die Datei.

    >>> _anders("typen", ["A", "B"], ["B", "A"]), _anders("name", "A", "B")
    (False, True)
    """
    if feld in ("typen", "regionen"):
        return set(alt or []) != set(neu or [])
    return alt != neu


@dataclass
class Quelle:
    """Was aus der App kommt: der Paketkopf (Version!), Übungen, bei einer Datenbank auch
    die Pläne, die Kurskapitel angelegt haben."""

    paket: Paket
    uebungen: list[Exercise]
    plaene: list[Plan] = field(default_factory=list)


def _quelle_lesen(quelle: Path, paket_id: str) -> Quelle:
    """Ein Export (JSON) oder eine Datenbank der App (nur lesend, ``mode=ro``)."""
    if quelle.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
        from trainingsapp.data.pakete import PaketRepo
        from trainingsapp.data.repositories import ExerciseRepo, PlanRepo, SubjectRepo

        con = sqlite3.connect(f"file:{quelle}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            paket = PaketRepo(con).laden(paket_id)
            if paket is None:
                raise PaketFehler(f"{quelle.name}: Paket {paket_id} ist dort nicht installiert")
            uebungen = [
                u for u in ExerciseRepo(con).alle(mit_archivierten=True) if u.package_id == paket_id
            ]
            plaene: dict[str, Plan] = {}
            for subject in SubjectRepo(con).alle():
                for plan in PlanRepo(con).alle(subject.id):
                    if plan.kurs_kapitel_id:
                        plaene[plan.id] = plan
        finally:
            con.close()
        return Quelle(paket, uebungen, list(plaene.values()))
    inhalt = paket_lesen(quelle.read_bytes(), quelle.stem)
    return Quelle(inhalt.paket, inhalt.uebungen)


def _uebungen_uebernehmen(
    quelle: Quelle, bloecke: list[Any], uebungen: list[Exercise]
) -> tuple[list[str], list[str]]:
    """Je Übung der Quelle den Block mit derselben ID: anders als in der Datei → eintragen.
    ``(Zeilen je übernommener Übung, Namen ohne Block)``."""
    je_id = {u.id: (block, u) for block, u in zip(bloecke, uebungen, strict=True)}
    zeilen: list[str] = []
    fremd: list[str] = []
    for u in quelle.uebungen:
        if u.id not in je_id:
            fremd.append(u.name)
            continue
        block, alt = je_id[u.id]
        alt_stand, neu_stand = stand(alt), stand(u)
        geaendert = [
            feld for feld in FELDNAMEN if _anders(feld, alt_stand.get(feld), neu_stand.get(feld))
        ]
        if not geaendert:
            continue
        for feld in geaendert:
            _feld_setzen(block, feld, neu_stand.get(feld), u)
        zeilen.append(f"{alt.name}: " + ", ".join(FELDNAMEN[feld] for feld in geaendert))
    return zeilen, fremd


def _vorlage_aus_plan(plan: Plan) -> PlanVorlage:
    """Der Plan, wie ihn ein Kapitel anlegen würde — Ziel, Felder, Sensor-Karte und Takt nur,
    wo der Plan eigene hat (sonst folgt die Planübung der Übung, P79)."""
    return PlanVorlage(
        name=plan.name,
        wochentage=list(plan.wochentage),
        items=[VorlageItem.aus_planitem(i) for i in sorted(plan.items, key=lambda i: i.order)],
    )


def _plaene_uebernehmen(
    quelle: Quelle, kurs_bloecke: list[Any], kurse: list[Kurs], schluessel: dict[str, str]
) -> tuple[list[str], list[str]]:
    """Pläne, die ein Kurskapitel angelegt hat (``kurs_kapitel_id``), zurück in die Vorlage
    des Kapitels — zugeordnet über Kapitel-ID und Planname; Wochentage und Übungen (mit
    ``key`` statt ID) werden ersetzt. ``(Zeilen, Hinweise)``."""
    kapitel_je_id: dict[str, tuple[Any, Kapitel, str]] = {}
    for kurs_block, kurs in zip(kurs_bloecke, kurse, strict=True):
        for kap_block, kap in zip(list(kurs_block.get("kapitel") or []), kurs.kapitel, strict=True):
            kapitel_je_id[kap.id] = (kap_block, kap, f"{kurs.name}, Kapitel „{kap.titel}“")
    zeilen: list[str] = []
    hinweise: list[str] = []
    for plan in quelle.plaene:
        if plan.kurs_kapitel_id not in kapitel_je_id:
            continue  # ein Kapitel eines anderen Pakets
        kap_block, kap, wo = kapitel_je_id[plan.kurs_kapitel_id]
        neu = _vorlage_aus_plan(plan)
        vorlagen = kap.plaene
        nr = next((i for i, v in enumerate(vorlagen) if v.name == plan.name), None)
        if nr is None:
            hinweise.append(f"{wo}: Plan „{plan.name}“ hat dort keine Vorlage — nicht übernommen")
            continue
        alt = vorlagen[nr]
        geaendert: list[str] = []
        if alt.wochentage != neu.wochentage:
            geaendert.append("Wochentage")
        if alt.to_dict()["uebungen"] != neu.to_dict()["uebungen"]:
            geaendert.append("Übungen")
        if not geaendert:
            continue
        block = kap_block["plaene"][nr]
        block["wochentage"] = _toml_wert(neu.wochentage)
        block["uebungen"] = _toml_wert(
            [i.to_dict(schluessel.get(i.exercise_id, i.exercise_id)) for i in neu.items]
        )
        zeilen.append(f"{wo}, Plan „{plan.name}“: " + ", ".join(geaendert))
    return zeilen, hinweise


def uebernehmen(quelle: Path, datei: Path, schreiben: bool = True) -> tuple[list[str], list[str]]:
    """Was in der App eingestellt wurde, in die TOML-Datei übernehmen — ``(Zeilen, Fehler)``.
    ``quelle`` ist ein Export aus dem Paketmanager (JSON: Übungen) oder die Datenbank der
    App (``.db``, nur lesend: Übungen und die Pläne aus Kurskapiteln). Ohne ``schreiben``
    nur zeigen, was sich änderte.

    Je Übung: der Block mit derselben ID (aus ``key`` gerechnet, wie beim Lesen); je Feld
    des Paketstands (`core.pakete.stand`): anders als in der Datei → eintragen. Übungen
    ohne Block (eigene, aus anderen Paketen) werden nur genannt. Gleiches Paket, andere
    Version → nichts: Dann hat die App den Stand der Datei nie gesehen, und die Quelle
    brächte Altes zurück."""
    tomlkit = _tomlkit()
    try:
        text = datei.read_text(encoding="utf-8")
        inhalt_datei = paket_lesen(_roh(datei))
        inhalt_quelle = _quelle_lesen(quelle, inhalt_datei.paket.id)
    except (PaketFehler, OSError, ValueError, sqlite3.Error) as grund:
        return [], [str(grund)]
    if (
        inhalt_quelle.paket.id == inhalt_datei.paket.id
        and inhalt_quelle.paket.version != inhalt_datei.paket.version
    ):
        return [], [
            f"{quelle.name} hat Version {version_text(inhalt_quelle.paket.version)}, "
            f"{datei.name} Version {version_text(inhalt_datei.paket.version)} — erst die App "
            "mit diesem Stand starten "
            "(`version` heben), dann übernehmen"
        ]
    dokument = tomlkit.parse(text)
    bloecke = list(dokument.get("exercises") or [])
    kurs_bloecke = list(dokument.get("kurse") or [])
    if len(bloecke) != len(inhalt_datei.uebungen) or len(kurs_bloecke) != len(inhalt_datei.kurse):
        return [], [f"{datei.name}: Blöcke und gelesene Übungen passen nicht zusammen"]
    zeilen, fremd = _uebungen_uebernehmen(inhalt_quelle, bloecke, inhalt_datei.uebungen)
    schluessel = {
        u.id: str(block.get("key") or "")
        for block, u in zip(bloecke, inhalt_datei.uebungen, strict=True)
        if block.get("key")
    }
    plan_zeilen, hinweise = _plaene_uebernehmen(
        inhalt_quelle, kurs_bloecke, inhalt_datei.kurse, schluessel
    )
    zeilen += plan_zeilen
    uebernommen = len(zeilen)
    if not uebernommen:
        zeilen.append("Keine Änderung")
    if fremd:
        zeilen.append("Nicht übernommen (kein Block mit dieser ID): " + ", ".join(fremd))
    zeilen += hinweise
    unberuehrt = len(bloecke) - len({u.id for u in inhalt_quelle.uebungen} & schluessel.keys())
    if unberuehrt:
        zeilen.append(f"{unberuehrt} Übung(en) der Datei sind nicht in der Quelle — unverändert")
    if schreiben and uebernommen:
        toml_text = _TABELLE_OHNE_LEERZEILE.sub(r"\1\n\n\2", tomlkit.dumps(dokument))
        datei.write_text(toml_text, encoding="utf-8")
        fehler, _ = pruefen(datei)
        return zeilen, [f"{datei.name} nach dem Übernehmen: {text}" for text in fehler]
    return zeilen, []


def _symbole() -> list[str] | None:
    try:
        from trainingsapp.ui.components.icons import AUSWAHL
    except ImportError:  # kein flet: Symbole bleiben ungeprüft
        return None
    return list(AUSWAHL)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trainingsapp-paket", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="befehl", required=True)
    p = sub.add_parser("pruefen", help="Paketdateien prüfen (TOML, JSON oder ZIP)")
    p.add_argument("dateien", nargs="+", type=Path)
    p.add_argument(
        "--gegen",
        help="die veröffentlichte Fassung (Datei, Link oder Index): Stufe und Version prüfen",
    )
    p.add_argument("--wortliste", type=Path, help="Begriffe, die in Texten nichts verloren haben")
    p.add_argument("--streng", action="store_true", help="Treffer der Wortliste sind Fehler")
    b = sub.add_parser("bauen", help="Paketdateien schreiben (JSON, mit Dateien ZIP)")
    b.add_argument("dateien", nargs="+", type=Path)
    b.add_argument("--ziel", type=Path, default=Path("dist"))
    b.add_argument("--basis-url", default="", help="für die Zugangskarte privater Pakete")
    i = sub.add_parser("index", help="Index einer Paketquelle schreiben")
    i.add_argument("dateien", nargs="+", type=Path)
    i.add_argument("--ziel", type=Path, default=Path("dist/index.json"))
    i.add_argument("--basis-url", default="", help="Adresse, unter der die Dateien liegen")
    i.add_argument("--quelle", default="", help="Name der Quelle, wie die App ihn zeigt")
    q = sub.add_parser("quelle", help="Index einer Quelle lesen und alle Pakete prüfen")
    q.add_argument("url")
    u = sub.add_parser("uebernehmen", help="Übungen aus einem Export der App ins TOML holen")
    u.add_argument(
        "quelle", type=Path, help="Export aus dem Paketmanager (JSON) oder Datenbank der App (.db)"
    )
    u.add_argument("datei", type=Path, help="die TOML-Datei des Pakets")
    u.add_argument("--probe", action="store_true", help="nur zeigen, nichts schreiben")
    args = parser.parse_args(argv)

    if args.befehl == "pruefen":
        symbole = _symbole()
        begriffe = wortliste_lesen(args.wortliste) if args.wortliste else []
        schlecht = 0
        for datei in args.dateien:
            fehler, hinweise = pruefen(datei, symbole, begriffe, args.streng)
            if args.gegen and not fehler:
                f_gegen, h_gegen = gegen_pruefen(datei, args.gegen)
                fehler, hinweise = fehler + f_gegen, hinweise + h_gegen
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
            try:
                if datei.suffix == ".toml" and "privat" in tomllib.loads(datei.read_text("utf-8")):
                    pfad, karte = privat_bauen(datei, args.ziel, args.basis_url)
                    print(pfad)
                    print(karte)
                else:
                    print(bauen(datei, args.ziel))
            except PaketFehler as bau_fehler:
                print(f"{datei}: nicht gebaut — {bau_fehler}")
                return 1
        return 0
    if args.befehl == "quelle":
        zeilen, fehler = quelle_pruefen(args.url)
        for z in zeilen:
            print(z)
        for f in fehler:
            print(f"FEHLER: {f}")
        return 1 if fehler else 0
    if args.befehl == "uebernehmen":
        zeilen, fehler = uebernehmen(args.quelle, args.datei, schreiben=not args.probe)
        for z in zeilen:
            print(z)
        for f in fehler:
            print(f"FEHLER: {f}")
        if not fehler and not args.probe and zeilen[0] != "Keine Änderung":
            print(f"{args.datei}: geschrieben — `git diff` zeigt, was aus der App kam")
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
