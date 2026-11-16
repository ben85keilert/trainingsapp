"""``trainingsapp-paket`` — Paketdateien prüfen, bauen und einen Index schreiben.

Das Werkzeug für das Inhalte-Repo (`docs/uebungspakete.md`, „Inhalte pflegen“):
Pakete werden als TOML von Hand gepflegt, die App liest sie beim Start direkt
(``TRAININGSAPP_PAKETE``) — fürs Handy und für Paketquellen braucht es JSON.

    trainingsapp-paket pruefen pakete/*.toml [--wortliste DATEI [--geprueft DATEI]] [--streng]
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
ihm gibt — eine Zeile je Begriff, ``#`` leitet Kommentare ein. Stellen, die ein Mensch
geprüft hat (ein Treffer, aber keine Bewertung), stehen in einer zweiten Datei
(``--geprueft``, `geprueft_lesen`) — sie gelten nur, solange der Text derselbe ist.

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
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trainingsapp.core.ablauf import ablauf_pruefen
from trainingsapp.core.bedingung import bedingung_pruefen
from trainingsapp.core.ergaenzungen import ERGAENZBAR
from trainingsapp.core.gps_wahl import gps_pruefen
from trainingsapp.core.kursbloecke import (
    ARTEN,
    AUSWAHL,
    BAUSTEINE,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    ZU_ENDE,
    Block,
)
from trainingsapp.core.kurse import Kapitel, Kurs, PlanVorlage, VorlageItem
from trainingsapp.core.kursplan import GRUNDLAGE
from trainingsapp.core.links import erlaubt as links_erlaubt
from trainingsapp.core.models import Exercise, Plan
from trainingsapp.core.paketdatei import (
    dateien_einbinden,
    medienlisten,
    paket_oeffnen,
    paket_zip,
    sha256_datei,
    toml_oeffnen,
)
from trainingsapp.core.pakete import (
    FELDNAMEN,
    NAMENSRAUM,
    Paket,
    PaketFehler,
    Paketinhalt,
    dateiname,
    noetige_version,
    nutzt_kursplan,
    paket_json,
    paket_lesen,
    stand,
)
from trainingsapp.core.paketmedien import medium_aus_paket
from trainingsapp.core.paketquelle import (
    INDEX_FORMAT,
    INDEX_VERSION,
    STAND_ENDUNG,
    QuellenFehler,
    index_laden,
    link_lesen,
    paket_laden,
    stand_json,
)
from trainingsapp.core.paketquelle import _laden as netz_laden
from trainingsapp.core.paketstufe import STUFE_TEXT, mindestens, stufen_text, version_reicht
from trainingsapp.core.paketstufe import stufe as paket_stufe
from trainingsapp.core.paketversion import version_text
from trainingsapp.core.privat import (
    ZUGANG_ENDUNG,
    code_neu,
    code_text,
    datei_verschluesseln,
    ist_privat,
    ordner_neu,
    zugangsdatei,
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
        if isinstance(k.get("kursplan"), dict):  # so heißt der Plan, den der Kurs baut
            texte.append((f"{wo}, Kursplan, Name", str(k["kursplan"].get("name") or "")))
        for kap in k.get("kapitel", []):
            if isinstance(kap, dict):
                titel = kap.get("titel", kap.get("key", "?"))
                texte.append((f"{wo}, Kapitel „{titel}“, Titel", str(kap.get("titel") or "")))
                texte.append((f"{wo}, Kapitel „{titel}“, Text", str(kap.get("text") or "")))
    return texte


def _plaene_mit_ort(roh: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """``(Wo, Plan)`` aller Pläne eines Pakets: ``plaene[]``, die der Kurskapitel und die
    Vorlage eines Kursplans (``kurse[].kursplan.vorlage``).

    >>> roh = {"plaene": [{"name": "Morgen"}], "kurse": [{"name": "K", "kapitel": [
    ...     {"titel": "T", "plaene": [{"name": "Stehen"}]}], "kursplan": {"vorlage": {}}}]}
    >>> [wo for wo, _ in _plaene_mit_ort(roh)]
    ['Plan „Morgen“', 'Kurs „K“, Kursplan, Vorlage', 'Kurs „K“, Kapitel „T“, Plan „Stehen“']
    """
    out: list[tuple[str, dict[str, Any]]] = []
    for pl in roh.get("plaene") or []:
        if isinstance(pl, dict):
            out.append((f"Plan „{pl.get('name', pl.get('key', '?'))}“", pl))
    for k in roh.get("kurse") or []:
        if not isinstance(k, dict):
            continue
        wo = f"Kurs „{k.get('name', k.get('key', '?'))}“"
        kursplan = k.get("kursplan")
        if isinstance(kursplan, dict) and isinstance(kursplan.get("vorlage"), dict):
            out.append((f"{wo}, Kursplan, Vorlage", kursplan["vorlage"]))
        for kap in k.get("kapitel") or []:
            if not isinstance(kap, dict):
                continue
            titel = kap.get("titel", kap.get("key", "?"))
            for pl in kap.get("plaene") or []:
                if isinstance(pl, dict):
                    name = pl.get("name", "?")
                    out.append((f"{wo}, Kapitel „{titel}“, Plan „{name}“", pl))
    return out


def textkennung(text: str) -> str:
    """Acht Zeichen, die sich mit jedem geänderten Buchstaben ändern — daran hängt eine
    geprüfte Stelle der Wortliste (`geprueft_lesen`).

    >>> textkennung("Die Auswertung bietet …"), textkennung("Die Auswertung zeigt …")
    ('e6a6b7af', '17d92cf6')
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def wortliste_treffer(roh: dict[str, Any], begriffe: Iterable[str]) -> list[tuple[str, str, str]]:
    """``(Wo, Begriff, Kennung des Textes)`` je Treffer der Wortliste — Groß/klein egal.

    >>> wortliste_treffer({"exercises": [{"name": "A", "description": "Die Analyse zeigt …"}]},
    ...                   ["Analyse"])
    [('Übung „A“, Beschreibung', 'Analyse', 'c620fb80')]
    """
    treffer: list[tuple[str, str, str]] = []
    begriffe = list(begriffe)
    for wo, text in _texte(roh):
        klein = text.casefold()
        for begriff in begriffe:
            if begriff.casefold() in klein:
                treffer.append((wo, begriff, textkennung(text)))
    return treffer


def wortliste_pruefen(roh: dict[str, Any], begriffe: Iterable[str]) -> list[str]:
    """Treffer der Wortliste in den Texten — Groß/klein egal, je Stelle ein Satz.

    >>> wortliste_pruefen({"exercises": [{"name": "A", "description": "Die Analyse zeigt …"}]},
    ...                   ["Analyse"])
    ['Übung „A“, Beschreibung: „Analyse“']
    """
    return [f"{wo}: „{begriff}“" for wo, begriff, _ in wortliste_treffer(roh, begriffe)]


#: Eine geprüfte Stelle: (Paketdatei, Stelle, Begriff klein, Kennung des Textes)
Geprueft = tuple[str, str, str, str]


def geprueft_lesen(datei: Path) -> set[Geprueft]:
    """Geprüfte Stellen der Wortliste — Treffer, die ein Mensch angesehen hat und die keine
    Bewertung sind („Auswertung“ als Name eines Bildschirms). Eine Zeile je Stelle, fünf
    Spalten, mit `` | `` getrennt; ``#`` am Zeilenanfang ist ein Kommentar::

        standard.toml | Übung „Ruhe-HF“, Beschreibung | Auswertung | e6a6b7af | Warum (wer, wann)

    Die Kennung (`textkennung`) steht am Treffer, den ``pruefen --geprueft`` meldet. Sie bindet
    die Prüfung an den Text: Ändert er sich, meldet sich die Stelle wieder. Ohne Begründung
    gilt eine Zeile nicht — ``ValueError`` nennt sie.
    """
    stellen: set[Geprueft] = set()
    for nummer, zeile in enumerate(datei.read_text(encoding="utf-8").splitlines(), 1):
        if not zeile.strip() or zeile.lstrip().startswith("#"):
            continue
        spalten = [s.strip() for s in zeile.split(" | ", 4)]
        if len(spalten) != 5 or not all(spalten):
            raise ValueError(
                f"{datei.name}, Zeile {nummer}: erwartet "
                "„Paketdatei | Stelle | Begriff | Kennung | Begründung“"
            )
        stellen.add((spalten[0], spalten[1], spalten[2].casefold(), spalten[3]))
    return stellen


def pruefen(
    datei: Path,
    symbole: Iterable[str] | None = None,
    wortliste: Iterable[str] = (),
    streng: bool = False,
    geprueft: Collection[Geprueft] | None = None,
) -> tuple[list[str], list[str]]:
    """``(Fehler, Hinweise)`` zu einer Paketdatei — dieselben Regeln wie der Test des
    Standardpakets: Schlüssel klein und ohne Umlaute, eindeutig; Beschreibung da; Symbol
    aus der Auswahl (``symbole``, sonst ungeprüft).
    Typen und Regionen außerhalb des Standardpakets sind Hinweise, keine Fehler — einer je
    Typ, nicht je Übung; Treffer der ``wortliste`` ebenso — mit ``streng`` werden sie Fehler.
    Mit ``geprueft`` (`geprueft_lesen`) nennt jeder Treffer seine Kennung, und die geprüften
    Stellen schrumpfen auf einen Hinweis mit ihrer Zahl. In ``beschleunigung`` (Karte
    „Beschleunigungssensor“) ist ein falscher Typ ein Fehler, ein unbekannter Schlüssel ein
    Hinweis (`core.zaehlen.wahl_pruefen`) — die App läse beides still als Vorgabe. Für ``takt``
    (`core.takt.takt_pruefen`) ebenso: unbrauchbare Dauer oder Tempo ein Fehler, unbekannte
    Art, Klang oder Schlüssel ein Hinweis. In ``gps`` (Karte „GPS“, `core.gps_wahl.gps_pruefen`)
    sind eine fehlende Rechenart und unbrauchbare Tempo-Grenzen Fehler, eine unbekannte
    Rechenart ein Hinweis. Sensor und Takt auch **je Planübung** in
    ``plaene[].uebungen[]`` und ``kurse[].kapitel[].plaene[].uebungen[]`` (A6) — mit dem Weg
    dorthin; ein unlesbarer Takt heißt dort „die Planübung folgt der Übung“. **Kursplan und
    Bausteine** (Formatversion 6) prüft `kursplan_pruefen`: feste und eindeutige Block-IDs,
    Marken, die es an ihrer Stelle schon gibt, ``aus`` mit Auswahl, ``ziel_aus`` mit Test,
    eine ``grundlage``, die ein Plan des Pakets ist."""
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
    eigene: dict[tuple[str, str], list[str]] = {}  # (Typ|Region, Name) → Übungen
    for e in eintraege:
        if not isinstance(e, dict):
            continue
        wo = f"Übung „{e.get('name', e.get('key', '?'))}“"
        if not str(e.get("description", "")).strip():
            fehler.append(f"{wo}: Beschreibung fehlt")
        if symbolmenge is not None and e.get("icon_key") not in symbolmenge:
            fehler.append(f"{wo}: Symbol {e.get('icon_key')!r} ist nicht in der Auswahl")
        for typ in sorted(set(e.get("typen", [])) - STANDARD_TYPEN):
            eigene.setdefault(("Typ", typ), []).append(wo)
        for region in sorted(set(e.get("regionen", [])) - STANDARD_REGIONEN):
            eigene.setdefault(("Region", region), []).append(wo)
        if "beschleunigung" in e:
            f_acc, h_acc = wahl_pruefen(e["beschleunigung"])
            fehler.extend(f"{wo}: beschleunigung: {x}" for x in f_acc)
            hinweise.extend(f"{wo}: beschleunigung: {x}" for x in h_acc)
        if "takt" in e:
            f_takt, h_takt = takt_pruefen(e["takt"])
            fehler.extend(f"{wo}: takt: {x}" for x in f_takt)
            hinweise.extend(f"{wo}: takt: {x}" for x in h_takt)
        if "gps" in e:
            f_gps, h_gps = gps_pruefen(e["gps"])
            fehler.extend(f"{wo}: gps: {x}" for x in f_gps)
            hinweise.extend(f"{wo}: gps: {x}" for x in h_gps)
        if "bedingung" in e:
            f_bed, h_bed = bedingung_pruefen(e["bedingung"])
            fehler.extend(f"{wo}: bedingung: {x}" for x in f_bed)
            hinweise.extend(f"{wo}: bedingung: {x}" for x in h_bed)
    # Ein Hinweis je eigenem Typ, nicht je Übung (Ben, 14.11.2026: vier Zeilen „Qigong“) —
    # ein Tippfehler fällt als eigener Typ mit einer einzelnen Übung weiter auf
    for (art, wert), bei in eigene.items():
        wo = bei[0] if len(bei) == 1 else f"{len(bei)} Übungen"
        hinweise.append(f"{art} „{wert}“ ist nicht im Standardpaket ({wo} — gewollt?)")
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
    for kurs in roh.get("kurse") or []:  # K41: die Kapitel-ID hängt sonst an der Nummer
        kapitel = kurs.get("kapitel") if isinstance(kurs, dict) else None
        ohne = [
            n
            for n, k in enumerate(kapitel if isinstance(kapitel, list) else [], 1)
            if isinstance(k, dict) and not k.get("key") and not k.get("id")
        ]
        if ohne:
            hinweise.append(
                f"Kurs „{kurs.get('name') or kurs.get('key') or '?'}“: Kapitel "
                f"{', '.join(map(str, ohne))} ohne `key` — ohne ihn zählt die Nummer: Ein "
                "eingeschobenes Kapitel verschiebt dann Fortschritt und Kapitelpläne aller "
                "dahinter auf das falsche Kapitel"
            )
    f_kurs, h_kurs = kursplan_pruefen(roh, inhalt)
    fehler.extend(f_kurs)
    hinweise.extend(h_kurs)
    if any(nutzt_kursplan(k) for k in inhalt.kurse):
        hinweise.append(
            "Formatversion 6 (Kursplan) — eine App, die sie nicht kennt, lehnt das Paket ab "
            "(„… neuer als diese App“) und behält ihren Stand"
        )
    if inhalt.paket.version is None:
        hinweise.append("Kopf ohne `version` — ohne sie erkennt kein Gerät ein Update")
    angenommen = 0
    for wo, begriff, kennung in wortliste_treffer(roh, wortliste):
        text = f"Wortliste: {wo}: „{begriff}“"
        if geprueft is not None:
            stelle = (datei.name, wo, begriff.casefold())
            if (*stelle, kennung) in geprueft:
                angenommen += 1
                continue
            anders = any(g[:3] == stelle for g in geprueft)
            text += f" (Kennung {kennung}{'; geprüft war ein anderer Text' if anders else ''})"
        (fehler if streng else hinweise).append(text)
    if angenommen:
        stellen = "1 geprüfte Stelle" if angenommen == 1 else f"{angenommen} geprüfte Stellen"
        hinweise.append(f"Wortliste: {stellen} (Text unverändert)")
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


#: Eine Block-ID, die als Marke taugt — wie jede ID im Paket (`core.pakete`): Die Marke im
#: Plan trennt Block und Übung mit „:“ (`core.kursplan`), die Zeilen der Karte hängen „#…“ an
_MARKEN_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_GRUNDLAGE_NR = re.compile(r"[1-9][0-9]*")
#: Je Baustein die Felder, die eine Marke nennen
_MARKENFELDER: dict[str, tuple[str, ...]] = {
    PLAN_UEBUNG: ("hinter",),
    PLAN_EINSTELLEN: ("an",),
    PLAN_WEG: ("von", "zu"),
}


@dataclass(frozen=True)
class _Blockstelle:
    """Ein Block und wo er im Kurs steht — Kapitel und Block von 1 gezählt."""

    kapitel: int
    block: int
    titel: str
    art: str
    roh: dict[str, Any]

    @property
    def id(self) -> str:
        """Die ``id``, wie `core.kursbloecke.Block.from_dict` sie liest — leer = keine."""
        return str(self.roh.get("id") or "")

    @property
    def ort(self) -> str:
        return f"Kapitel „{self.titel}“, Block {self.block}" + (f" „{self.id}“" if self.id else "")

    def vor(self, andere: _Blockstelle) -> bool:
        return (self.kapitel, self.block) < (andere.kapitel, andere.block)


def _marke_roh(roh: Any) -> str:
    """Eine Marke oder Block-ID aus den Rohdaten — gelesen wie in `core.kursbloecke`: Text
    ohne Rand (auch eine Zahl), alles andere ist keine.

    >>> _marke_roh(" a "), _marke_roh(7), _marke_roh(True), _marke_roh(None)
    ('a', '7', '', '')
    """
    return str(roh).strip() if isinstance(roh, str | int) and not isinstance(roh, bool) else ""


def _marke_pruefen(
    feld: str,
    wert: str,
    hier: _Blockstelle,
    je_id: Mapping[str, _Blockstelle],
    grundlage: int | None,
    schluessel: Mapping[str, str],
) -> str | None:
    """Fehlertext, wenn ``wert`` keine Marke ist, die es an dieser Stelle schon gibt — sonst
    ``None``. Marken: die ``id`` eines ``plan_uebung`` davor (in diesem oder einem früheren
    Kapitel), ``<id>:<übung>`` für eine der Gewählten, ``g:<n>`` für die n-te Planübung der
    Grundlage (``grundlage``: wie viele sie hat — ``None``: der Kurs hat keinen Kursplan),
    bei ``zu`` auch ``ende``."""
    if feld == "zu" and wert.lower() == ZU_ENDE:
        return None
    vorn = f"`{feld}` „{wert}“"
    if wert.startswith(GRUNDLAGE):
        if grundlage is None:
            return f"{vorn}: Der Kurs hat keinen `kursplan`, also keine Grundlage"
        nummer = wert[len(GRUNDLAGE) :]
        if _GRUNDLAGE_NR.fullmatch(nummer) and int(nummer) <= grundlage:
            return None
        if not grundlage:
            return f"{vorn} gibt es nicht — der Kursplan beginnt leer (keine Grundlage)"
        return (
            f"{vorn} gibt es nicht — die Grundlage hat {grundlage} "
            f"Planübung{'' if grundlage == 1 else 'en'} (`g:1` bis `g:{grundlage}`)"
        )
    kopf, trenner, uebung = wert.partition(":")
    ziel = je_id.get(kopf)
    if ziel is None:
        ende = ", `ende`" if feld == "zu" else ""
        return (
            f"{vorn} nennt keine bekannte Marke (die `id` eines `plan_uebung` davor, `g:<n>`{ende})"
        )
    if ziel.art != PLAN_UEBUNG:
        return (
            f"{vorn} ist ein Block `{ziel.art}`, kein `plan_uebung` — nur der bringt eine "
            "Planübung in den Plan"
        )
    if ziel.kapitel > hier.kapitel:
        return (
            f"{vorn} steht erst in Kapitel {ziel.kapitel} („{ziel.titel}“) — die Planübung "
            "gibt es hier noch nicht"
        )
    if not ziel.vor(hier):
        return (
            f"{vorn} steht nicht vor diesem Baustein — Bausteine gelten in der Reihenfolge, "
            "in der sie dastehen"
        )
    if trenner:
        aus = _marke_roh(ziel.roh.get("aus"))
        if not aus:
            return f"{vorn}: „{kopf}“ bringt eine feste Übung — ihre Marke heißt „{kopf}“"
        auswahl = je_id.get(aus)
        zur_wahl = auswahl.roh.get("uebungen") if auswahl is not None else None
        if isinstance(zur_wahl, list) and schluessel.get(uebung, uebung) not in {
            schluessel.get(str(u), str(u)) for u in zur_wahl
        }:
            return f"{vorn}: „{uebung}“ steht in der Auswahl „{aus}“ nicht zur Wahl"
    return None


def _verweis_pruefen(
    feld: str,
    wert: str,
    art: str,
    hier: _Blockstelle,
    je_id: Mapping[str, _Blockstelle],
) -> str | None:
    """Fehlertext, wenn ``wert`` nicht die ``id`` eines Blocks der Art ``art`` in diesem oder
    einem früheren Kapitel ist (``aus`` → ``auswahl``, ``ziel_aus`` → ``test``) — sonst
    ``None``. Im selben Kapitel darf der Block auch weiter unten stehen: Wahl und Testwert
    gelten für das ganze Kapitel."""
    vorn = f"`{feld}` „{wert}“"
    wort = "keine Auswahl" if art == AUSWAHL else "keinen Test"
    ziel = je_id.get(wert)
    if ziel is None:
        return (
            f"{vorn} nennt {wort} (ein Block `{art}` mit dieser `id` in diesem oder einem "
            "früheren Kapitel)"
        )
    if ziel.art != art:
        return f"{vorn} nennt {wort}, sondern einen Block `{ziel.art}`"
    if ziel.kapitel > hier.kapitel:
        return (
            f"{vorn} steht erst in Kapitel {ziel.kapitel} („{ziel.titel}“) — ein Baustein "
            "bezieht sich nur auf dieses oder ein früheres Kapitel"
        )
    return None


def _kante_pruefen(roh: Any) -> tuple[list[str], list[str]]:
    """Die ``kante`` eines ``plan_weg`` — geprüft wie eine Kante im Ablauf eines Plans
    (`core.ablauf.ablauf_pruefen`), nur ohne ``von`` und ``nach``: Die stehen als Marken am
    Baustein.

    >>> _kante_pruefen({"ausloeser": "tanz", "n": "x"})
    (['kante: n ist keine Zahl'], ['kante: Auslöser „tanz“ unbekannt — „frei“ gilt'])
    >>> _kante_pruefen({"ausloeser": "zeit", "pflicht": True}), _kante_pruefen("zeit")[0]
    (([], []), ['kante: keine Tabelle — es gälte ein freier Weg'])
    """
    if not isinstance(roh, dict):
        return ["kante: keine Tabelle — es gälte ein freier Weg"], []
    f_ab, h_ab = ablauf_pruefen({"kanten": [{**roh, "von": "#1", "nach": "#2"}]})
    return (
        ["kante: " + x.removeprefix("Kante 1: ") for x in f_ab],
        ["kante: " + x.removeprefix("Kante 1: ") for x in h_ab],
    )


def _kurs_pruefen(
    kurs_roh: Mapping[str, Any],
    kurs: Kurs,
    plaene: Mapping[str, int],
    schluessel: Mapping[str, str],
) -> tuple[list[str], list[str]]:
    """Kursplan und Bausteine **eines** Kurses — ``kurs_roh`` aus der Datei, ``kurs`` wie die
    App ihn liest; ``plaene``: Schlüssel der Paketpläne → Zahl ihrer Planübungen."""
    fehler: list[str] = []
    hinweise: list[str] = []
    kursplan = kurs_roh.get("kursplan")
    grundlage: int | None = None  # wie viele Planübungen die Grundlage hat — None: kein Kursplan
    if isinstance(kursplan, dict):
        g_roh, vorlage = kursplan.get("grundlage"), kursplan.get("vorlage")
        g = g_roh.strip() if isinstance(g_roh, str) else ""
        if g_roh is not None and not g:
            fehler.append(
                "kursplan: `grundlage` ist kein Schlüssel — gemeint ist der `key` eines Plans "
                "aus `plaene`"
            )
        if g and vorlage is not None:
            fehler.append(
                "kursplan: `grundlage` und `vorlage` zugleich — nur eines davon (die App nähme "
                "die Vorlage)"
            )
        if g and g not in plaene:
            bekannt = ", ".join(sorted(plaene)) or "das Paket hat keine `plaene`"
            fehler.append(
                f"kursplan: `grundlage` „{g}“ nennt keinen Plan des Pakets (bekannt: {bekannt})"
            )
        gelesen = kurs.kursplan.vorlage if kurs.kursplan is not None else None
        if vorlage is not None and gelesen is None:
            hinweise.append("kursplan: `vorlage` ohne Übung — der Plan beginnt leer")
        grundlage = len(gelesen.items) if gelesen is not None else plaene.get(g, 0)

    # Erst alle Blöcke des Kurses: Ein Baustein darf auf einen Block weiter vorn zeigen, und
    # die Meldung soll sagen können, wo der gemeinte steht
    stellen: list[_Blockstelle] = []
    je_id: dict[str, _Blockstelle] = {}
    mit_plaenen: list[str] = []
    kapitel = kurs_roh.get("kapitel")
    for kn, kap in enumerate(kapitel if isinstance(kapitel, list) else [], start=1):
        if not isinstance(kap, dict):
            continue
        titel = str(kap.get("titel", kap.get("key", "?")))
        if kap.get("plaene"):
            mit_plaenen.append(titel)
        bloecke = kap.get("bloecke")
        for bn, b in enumerate(bloecke if isinstance(bloecke, list) else [], start=1):
            if not isinstance(b, dict):
                continue
            s = _Blockstelle(kn, bn, titel, str(b.get("art") or ""), b)
            if s.art.startswith("plan_") and s.art not in BAUSTEINE:
                fehler.append(
                    f"{s.ort}: unbekannter Baustein `{s.art}` (bekannt: {', '.join(BAUSTEINE)}) "
                    "— der Block fällt weg"
                )
            if s.art not in ARTEN and s.art not in BAUSTEINE:
                continue  # überliest die App
            stellen.append(s)
            if not s.id:
                continue
            if s.id in je_id:
                fehler.append(
                    f"{s.ort}: Die `id` gibt es im Kurs schon ({je_id[s.id].ort}) — Block-IDs "
                    "sind je Kurs eindeutig"
                )
            else:
                je_id[s.id] = s

    steine = [s for s in stellen if s.art in BAUSTEINE]
    for s in steine:
        b = s.roh
        probleme: list[str] = []
        if not s.id:
            probleme.append(
                "Baustein ohne feste `id` — andere Bausteine zeigen auf sie, und sie steht als "
                "Marke im Plan (die App vergäbe bei jedem Lesen eine andere)"
            )
        elif not _MARKEN_ID.fullmatch(s.id) or s.id.lower() == ZU_ENDE or s.id + ":" == GRUNDLAGE:
            # „ende“ ist das Ziel eines Wegs, „g:…“ sind die Marken der Grundlage
            probleme.append(
                "Die `id` taugt nicht als Marke: nur Buchstaben, Ziffern, „-“ und „_“ (1–64 "
                "Zeichen), nicht „ende“ und nicht „g“"
            )
        if s.art == PLAN_UEBUNG:
            uebung, aus = str(b.get("uebung") or "").strip(), _marke_roh(b.get("aus"))
            if uebung and aus:
                probleme.append(
                    "`uebung` und `aus` zugleich — nur eines davon (die App nähme `aus`)"
                )
            elif not uebung and not aus:
                probleme.append(
                    "weder `uebung` (eine feste Übung) noch `aus` (die `id` einer Auswahl) — "
                    "der Baustein fällt weg"
                )
            if aus and (text := _verweis_pruefen("aus", aus, AUSWAHL, s, je_id)):
                probleme.append(text)
        for feld in _MARKENFELDER[s.art]:
            wert = _marke_roh(b.get(feld))
            if wert:
                text = _marke_pruefen(feld, wert, s, je_id, grundlage, schluessel)
                if text is not None:
                    probleme.append(text)
            elif s.art == PLAN_WEG:  # `hinter` und `an` dürfen fehlen: ans Ende, am Plan
                probleme.append(
                    f"`{feld}` fehlt — ein Weg braucht `von` und `zu`, der Baustein fällt weg"
                )
        if s.art == PLAN_EINSTELLEN and Block.from_dict(b) is None:
            hinweise.append(f"{s.ort}: stellt nichts ein — der Baustein fällt weg")
        if s.art in (PLAN_UEBUNG, PLAN_EINSTELLEN):
            ziel_aus = _marke_roh(b.get("ziel_aus"))
            if ziel_aus and (text := _verweis_pruefen("ziel_aus", ziel_aus, TEST, s, je_id)):
                probleme.append(text)
        if s.art == PLAN_WEG and "kante" in b:
            f_kante, h_kante = _kante_pruefen(b["kante"])
            probleme.extend(f_kante)
            hinweise.extend(f"{s.ort}: {x}" for x in h_kante)
        fehler.extend(f"{s.ort}: {x}" for x in probleme)

    if steine and grundlage is None:
        hinweise.append(
            f"{len(steine)} Baustein{'' if len(steine) == 1 else 'e'} (`plan_*`) in einem Kurs "
            "ohne `kursplan` — sie bewirken dort nichts"
        )
    if grundlage is not None and mit_plaenen:
        hinweise.append(
            "`kursplan` und `plaene` in Kapiteln ("
            + ", ".join(f"„{t}“" for t in mit_plaenen)
            + ") — beides gilt nebeneinander: Die Kapitelpläne entstehen wie bisher, der "
            "Kursplan wächst daneben"
        )
    return fehler, hinweise


def kursplan_pruefen(roh: Mapping[str, Any], inhalt: Paketinhalt) -> tuple[list[str], list[str]]:
    """``(Fehler, Hinweise)`` zu **Kursplan und Bausteinen** aller Kurse einer Paketdatei
    (Formatversion 6; `docs/uebungspakete.md`, „Kursplan“; `docs/plan_kurs_ablauf.md` §11) —
    ``roh`` ist die Datei, ``inhalt`` dieselbe, wie die App sie liest. Die App liest
    nachsichtig: Was sie nicht versteht, fällt still weg oder ergibt später die Zeile „… ist
    nicht mehr in deinem Plan“. Darum hier **Fehler**:

    - ein Baustein (``plan_uebung``, ``plan_einstellen``, ``plan_weg``) ohne feste ``id``
      oder mit einer, die nicht als Marke taugt; eine Block-ID, die es im Kurs zweimal gibt;
    - ``hinter``, ``an``, ``von``, ``zu`` ohne bekannte Marke — die ``id`` eines
      ``plan_uebung`` **davor** (früheres Kapitel oder weiter oben), ``g:<n>`` innerhalb der
      Grundlage, bei ``zu`` auch ``ende``; ein ``plan_weg`` ohne ``von`` oder ``zu``;
    - ``aus`` ohne Auswahl, ``ziel_aus`` ohne Test in diesem oder einem früheren Kapitel;
    - ``plan_uebung`` ohne ``uebung`` und ohne ``aus`` — oder mit beidem;
    - ``kursplan.grundlage`` ohne Plan dieses Schlüssels in ``plaene[]``; ``grundlage`` und
      ``vorlage`` zugleich;
    - in der ``kante`` eines Wegs, was `core.ablauf.ablauf_pruefen` als Fehler meldet.

    **Hinweise:** Bausteine in einem Kurs ohne ``kursplan`` (sie bewirken dort nichts),
    Kapitel-Vorlagen (``plaene``) neben einem ``kursplan`` (beides gilt nebeneinander), ein
    unbekannter Auslöser einer ``kante`` (es gilt „frei“), ein ``plan_einstellen``, das
    nichts einstellt, eine ``vorlage`` ohne Übung.

    >>> from trainingsapp.core.pakete import paket_lesen
    >>> roh = {"paket": {"name": "Q"}, "exercises": [{"key": "planke", "name": "Planke"}],
    ...        "kurse": [{"name": "Rumpf", "kursplan": {"grundlage": "basis"}, "kapitel": [
    ...            {"titel": "Eins", "bloecke": [
    ...                {"art": "plan_uebung", "uebung": "planke", "hinter": "g:1"}]}]}]}
    >>> for zeile in kursplan_pruefen(roh, paket_lesen(roh))[0]:
    ...     print(zeile)
    Kurs „Rumpf“: kursplan: `grundlage` „basis“ nennt keinen Plan des Pakets (bekannt: das \
Paket hat keine `plaene`)
    Kurs „Rumpf“: Kapitel „Eins“, Block 1: Baustein ohne feste `id` — andere Bausteine zeigen \
auf sie, und sie steht als Marke im Plan (die App vergäbe bei jedem Lesen eine andere)
    Kurs „Rumpf“: Kapitel „Eins“, Block 1: `hinter` „g:1“ gibt es nicht — der Kursplan \
beginnt leer (keine Grundlage)
    """
    fehler: list[str] = []
    hinweise: list[str] = []
    plaene = {pp.key: len(pp.vorlage.items) for pp in inhalt.plaene}
    # Paketschlüssel → ID, wie der Leser sie auflöst (dieselbe Datei, dieselbe Reihenfolge)
    eintraege = [e for e in roh.get("exercises") or [] if isinstance(e, dict)]
    schluessel = {
        str(e["key"]).strip(): u.id
        for e, u in zip(eintraege, inhalt.uebungen, strict=False)
        if e.get("key")
    }
    kurse = [k for k in roh.get("kurse") or [] if isinstance(k, dict)]
    for kurs_roh, kurs in zip(kurse, inhalt.kurse, strict=False):
        wo = f"Kurs „{kurs_roh.get('name', kurs_roh.get('key', '?'))}“"
        f_kurs, h_kurs = _kurs_pruefen(kurs_roh, kurs, plaene, schluessel)
        fehler.extend(f"{wo}: {x}" for x in f_kurs)
        hinweise.extend(f"{wo}: {x}" for x in h_kurs)
    return fehler, hinweise


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
    pfad = datei.with_name(datei.stem + ZUGANG_ENDUNG)
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
    gebaut = paket_oeffnen(pfad, code=zugang["code"]).paket
    name = gebaut.name
    # Die Standdatei daneben: Version, Prüfsumme, Größe — die App fragt sie statt der ganzen
    # Datei (`paketquelle.stand_url`); kein Name, kein Inhalt
    pfad.with_name(pfad.stem + STAND_ENDUNG).write_bytes(
        stand_json(gebaut.version, sha256_datei(pfad), pfad.stat().st_size)
    )
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
        if zugangsdatei(datei) or datei.name.endswith(STAND_ENDUNG):
            continue
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
                # wie `paket_bauen` sie schreibt; eine ZIP ist immer mindestens Version 4
                "format_version": max(
                    noetige_version(
                        inhalt.uebungen, inhalt.kurse, inhalt.plaene, inhalt.ergaenzungen
                    ),
                    4 if inhalt.medien else 1,
                ),
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
    #: Übungen (IDs), die in der Datenbank ein **anderes** Paket ergänzt (U5): Ihr Stand dort
    #: ist Grund + Ergänzungen — die ergänzbaren Felder gehören nicht ins Grundpaket (K44)
    ergaenzt: frozenset[str] = frozenset()


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
                    # ein Plan aus einem früheren Durchlauf (Migration 063) ist keine Vorlage mehr
                    if plan.kurs_kapitel_id and plan.kurs_durchlauf_beendet is None:
                        plaene[plan.id] = plan
            try:
                ergaenzt = frozenset(
                    str(r[0])
                    for r in con.execute(
                        "SELECT DISTINCT exercise_id FROM exercise_addon WHERE package_id != ?",
                        (paket_id,),
                    )
                )
            except sqlite3.OperationalError:  # eine Datenbank von vor den Ergänzungen (U5)
                ergaenzt = frozenset()
        finally:
            con.close()
        return Quelle(paket, uebungen, list(plaene.values()), ergaenzt)
    inhalt = paket_lesen(quelle.read_bytes(), quelle.stem)
    return Quelle(inhalt.paket, inhalt.uebungen)


def _uebungen_uebernehmen(
    quelle: Quelle, bloecke: list[Any], uebungen: list[Exercise]
) -> tuple[list[str], list[str], list[str]]:
    """Je Übung der Quelle den Block mit derselben ID: anders als in der Datei → eintragen.
    ``(Zeilen je übernommener Übung, Namen ohne Block, Hinweise)``.

    Ergänzt in der Datenbank ein anderes Paket die Übung (`Quelle.ergaenzt`), ist ihr Stand
    dort der **wirksame** (Grund + Ergänzungen): Die Felder, die eine Ergänzung setzen darf
    (`ERGAENZBAR`), werden dann nicht übernommen — sonst landeten Abschnitte, Medien oder
    Timer des anderen Pakets als Inhalt dieses Pakets in der Datei (K44)."""
    je_id = {u.id: (block, u) for block, u in zip(bloecke, uebungen, strict=True)}
    zeilen: list[str] = []
    fremd: list[str] = []
    hinweise: list[str] = []
    for u in quelle.uebungen:
        if u.id not in je_id:
            fremd.append(u.name)
            continue
        block, alt = je_id[u.id]
        alt_stand, neu_stand = stand(alt), stand(u)
        geaendert = [
            feld for feld in FELDNAMEN if _anders(feld, alt_stand.get(feld), neu_stand.get(feld))
        ]
        if u.id in quelle.ergaenzt and (aus := [f for f in geaendert if f in ERGAENZBAR]):
            geaendert = [f for f in geaendert if f not in ERGAENZBAR]
            hinweise.append(
                f"{alt.name}: von einem anderen Paket ergänzt — nicht übernommen: "
                + ", ".join(FELDNAMEN[f] for f in aus)
            )
        if not geaendert:
            continue
        for feld in geaendert:
            _feld_setzen(block, feld, neu_stand.get(feld), u)
        zeilen.append(f"{alt.name}: " + ", ".join(FELDNAMEN[feld] for feld in geaendert))
    return zeilen, fremd, hinweise


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
    zeilen, fremd, ergaenzt = _uebungen_uebernehmen(inhalt_quelle, bloecke, inhalt_datei.uebungen)
    schluessel = {
        u.id: str(block.get("key") or "")
        for block, u in zip(bloecke, inhalt_datei.uebungen, strict=True)
        if block.get("key")
    }
    plan_zeilen, hinweise = _plaene_uebernehmen(
        inhalt_quelle, kurs_bloecke, inhalt_datei.kurse, schluessel
    )
    zeilen += plan_zeilen
    hinweise = ergaenzt + hinweise
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
    p.add_argument(
        "--geprueft",
        type=Path,
        help="geprüfte Stellen der Wortliste (Paketdatei | Stelle | Begriff | Kennung | Warum)",
    )
    b = sub.add_parser("bauen", help="Paketdateien schreiben (JSON, mit Dateien ZIP)")
    b.add_argument("dateien", nargs="+", type=Path)
    b.add_argument("--ziel", type=Path, default=Path("dist"))
    b.add_argument("--basis-url", default="", help="für die Zugangskarte privater Pakete")
    i = sub.add_parser("index", help="Index einer Paketquelle schreiben")
    i.add_argument("dateien", nargs="*", type=Path, help="keine = leerer Index (nur Privates)")
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
        geprueft: set[Geprueft] | None = None
        if args.geprueft:
            try:
                geprueft = geprueft_lesen(args.geprueft)
            except (OSError, ValueError) as lese_fehler:
                print(f"FEHLER: {lese_fehler}")
                return 2
        schlecht = 0
        for datei in args.dateien:
            if zugangsdatei(datei):
                print(f"{datei}: übersprungen — Zugang eines privaten Pakets, kein Paket")
                continue
            fehler, hinweise = pruefen(datei, symbole, begriffe, args.streng, geprueft)
            if args.gegen and not fehler:
                f_gegen, h_gegen = gegen_pruefen(datei, args.gegen)
                fehler, hinweise = fehler + f_gegen, hinweise + h_gegen
            # Erst das Urteil je Datei, darunter eingerückt das Warum (Ben, 14.11.2026)
            print(f"{datei}: " + (f"{len(fehler)} FEHLER" if fehler else "in Ordnung"))
            for text in fehler:
                print(f"    FEHLER: {text}")
            for text in hinweise:
                print(f"    Hinweis: {text}")
            schlecht += bool(fehler)
        if symbole is None:
            print("(Symbole ungeprüft — flet nicht installiert)")
        return 1 if schlecht else 0
    if args.befehl == "bauen":
        for datei in args.dateien:
            if zugangsdatei(datei):
                continue
            fehler, _ = pruefen(datei)
            if fehler:
                print(f"{datei}: nicht gebaut — " + "; ".join(fehler))
                return 1
            try:
                if datei.suffix == ".toml" and "privat" in tomllib.loads(datei.read_text("utf-8")):
                    pfad, karte = privat_bauen(datei, args.ziel, args.basis_url)
                    # Ordner (der Link) und Code nur am Terminal — umgeleitet (CI,
                    # Protokolldatei) stünden sie sonst in einem Log, das andere lesen
                    if sys.stdout.isatty():
                        print(pfad)
                        print("\n".join(f"    {zeile}" for zeile in karte.splitlines()))
                    else:
                        kurz = pfad.parent.with_name(pfad.parent.name[:4] + "…") / pfad.name
                        print(kurz)
                        print(
                            "    Zugangskarte: "
                            f"{datei.with_name(datei.stem + '.zugangskarte.txt')}"
                            " (Link und Code stehen nur dort, nicht in dieser Ausgabe)"
                        )
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
