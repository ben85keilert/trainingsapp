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
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trainingsapp.core.kurse import Kapitel, Kurs, PlanVorlage, VorlageItem
from trainingsapp.core.models import Exercise, Plan
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
from trainingsapp.core.paketquelle import (
    INDEX_FORMAT,
    INDEX_VERSION,
    QuellenFehler,
    index_laden,
    paket_laden,
)
from trainingsapp.core.paketquelle import _laden as netz_laden
from trainingsapp.core.result_spec import VORLAGEN
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
            f"{len(inhalt.kurse)} Kurs(e), {len(inhalt.plaene)} Plan/Pläne, {eintrag.bytes} B, "
            "Prüfsumme in Ordnung"
        )
    return zeilen, fehler


def bauen(datei: Path, ziel: Path) -> Path:
    """Schreibt die JSON-Paketdatei (Austauschformat) nach ``ziel`` und gibt den Pfad zurück."""
    inhalt: Paketinhalt = seed_inhalt(datei)
    ziel.mkdir(parents=True, exist_ok=True)
    pfad = ziel / dateiname(inhalt.paket)
    # ohne Zeitstempel: derselbe Quelltext ergibt dieselbe Datei und Prüfsumme (K28)
    pfad.write_bytes(
        paket_json(
            inhalt.paket,
            inhalt.uebungen,
            inhalt.kurse,
            mit_zeitstempel=False,
            plaene=inhalt.plaene or None,
        )
    )
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
                "plaene": len(inhalt.plaene),
                "neuigkeiten": inhalt.paket.neuigkeiten,
                "veroeffentlicht": bekannt.get(sha256) or datetime.now(UTC).date().isoformat(),
                "format_version": 3 if inhalt.plaene else 2 if inhalt.kurse else 1,
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
    """Der Plan, wie ihn ein Kapitel anlegen würde — Ziel und Felder nur, wo der Plan
    eigene hat (sonst folgt die Planübung der Übung, P79)."""
    return PlanVorlage(
        name=plan.name,
        wochentage=list(plan.wochentage),
        items=[
            VorlageItem(
                exercise_id=i.exercise_id,
                target=dict(i.target) if i.target else {},
                felder=None if i.felder is None else list(i.felder),
            )
            for i in sorted(plan.items, key=lambda i: i.order)
        ],
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
            [
                {"uebung": schluessel.get(i.exercise_id, i.exercise_id)}
                | ({"ziel": i.target} if i.target else {})
                | ({"felder": i.felder} if i.felder is not None else {})
                for i in neu.items
            ]
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
            f"{quelle.name} hat Version {inhalt_quelle.paket.version}, {datei.name} Version "
            f"{inhalt_datei.paket.version} — erst die App mit diesem Stand starten "
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
