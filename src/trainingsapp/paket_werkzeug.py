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
import subprocess
import sys
import tempfile
import tomllib
import uuid
import zipfile
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trainingsapp.core.abgleich import Hinweis, abgleichen
from trainingsapp.core.ablauf import ablauf_pruefen
from trainingsapp.core.bedingung import bedingung_pruefen
from trainingsapp.core.bewegungsbild import bilder_in, png_masse
from trainingsapp.core.ergaenzungen import ERGAENZBAR
from trainingsapp.core.gps_wahl import gps_pruefen
from trainingsapp.core.kursbloecke import (
    ARTEN,
    AUSWAHL,
    BAUSTEINE,
    MENGE,
    PLAN_EINSTELLEN,
    PLAN_ENTFERNEN,
    PLAN_TAUSCHEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    SKALA,
    TEST,
    VORGABEN,
    WIE_UEBUNG,
    WIE_UHR,
    ZEIT,
    ZU_ENDE,
    Block,
    Vorgabe,
)
from trainingsapp.core.kurse import Kapitel, Kurs, PlanVorlage, VorlageItem
from trainingsapp.core.kursplan import GRUNDLAGE
from trainingsapp.core.links import erlaubt as links_erlaubt
from trainingsapp.core.linkvideos import direkt, mit_pruefsumme, nennt_pruefsumme, pruefsumme
from trainingsapp.core.models import BEGLEITUNG, BEWEGUNG, ROLLEN, Exercise, MediaSource, Plan
from trainingsapp.core.paketdatei import (
    PAKET_JSON,
    dateien_einbinden,
    medienlisten,
    nachbar_namen,
    nachbar_tomls,
    paket_oeffnen,
    paket_zip,
    sha256_datei,
    toml_oeffnen,
)
from trainingsapp.core.pakete import (
    FELDNAMEN,
    MARKENFELDER,
    NAMENSRAUM,
    Paket,
    PaketFehler,
    Paketinhalt,
    PaketPlan,
    Voraussetzung,
    dateiname,
    ergaenzung_ziel,
    kurs_stand,
    noetige_version,
    nutzt_kursplan,
    paket_json,
    paket_lesen,
    paket_ziel,
    paketplan_aus,
    plan_abgleichen,
    plan_schluessel,
    plan_stand,
    stand,
    stand_normieren,
)
from trainingsapp.core.paketmedien import Paketmedium, medium_aus_paket
from trainingsapp.core.paketquelle import (
    INDEX_FORMAT,
    INDEX_VERSION,
    STAND_ENDUNG,
    QuellenFehler,
    index_laden,
    link_lesen,
    paket_laden,
    seitenroute,
    stand_json,
)
from trainingsapp.core.paketquelle import _laden as netz_laden
from trainingsapp.core.paketstufe import STUFE_TEXT, mindestens, stufen_text, version_reicht
from trainingsapp.core.paketstufe import stufe as paket_stufe
from trainingsapp.core.paketversion import version_text, version_zahl
from trainingsapp.core.privat import (
    ZUGANG_ENDUNG,
    code_neu,
    code_text,
    datei_verschluesseln,
    ist_privat,
    ordner_neu,
    zugangsdatei,
)
from trainingsapp.core.result_spec import VORLAGEN, basis_key
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
    # Prüfsumme am Link (`verlinken`, ``#sha256=…``): unlesbar hieße, die App prüft nichts
    for liste in medienlisten(roh):
        for e in liste:
            uri = str(e.get("uri") or "") if isinstance(e, dict) else ""
            if nennt_pruefsumme(uri) and not pruefsumme(uri):
                fehler.append(
                    f"Medium „{e.get('title') or uri}“: Prüfsumme am Link unlesbar "
                    "(#sha256= und 64 Zeichen 0–9, a–f)"
                )
    f_rollen, h_rollen = rollen_pruefen(roh, datei.parent)  # vor dem Einbinden (nimmt `datei`)
    fehler.extend(f_rollen)
    hinweise.extend(h_rollen)
    hinweise.extend(zeitpunkte_pruefen(roh))
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
    f_verw, h_verw = verweise_pruefen(datei, roh, inhalt)
    fehler.extend(f_verw)
    hinweise.extend(h_verw)
    if not f_verw and (braucht := voraussetzungen(datei, inhalt)):
        hinweise.append(
            "braucht "
            + ", ".join(
                f"„{v.name}“" + (f" ab {version_text(v.version)}" if v.version else "")
                for v in braucht
            )
            + " — steht beim Bauen im Kopf, die App lädt es beim Import nach"
        )
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


def _uebungsverweise(roh: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """``(Wo, Übung, Paket)`` jedes Übungsverweises in Plänen und Kursen — Planübungen,
    Kursplan, Bedingungen, Blöcke (``uebung``, wahlweise ``paket``) und Marken in der Form
    ``<block>:<Paket>/<schlüssel>`` (V1).

    >>> roh = {"plaene": [{"name": "P", "uebungen": [{"uebung": "a"}]}], "kurse": [{"name":
    ...     "K", "kapitel": [{"titel": "T", "bedingung": {"uebung": "b", "paket": "Standard"},
    ...     "bloecke": [{"an": "dazu:Qigong/c"}]}]}]}
    >>> _uebungsverweise(roh)  # doctest: +NORMALIZE_WHITESPACE
    [('Plan „P“', 'a', ''), ('Kurs „K“, Kapitel „T“', 'b', 'Standard'),
     ('Kurs „K“, Kapitel „T“', 'c', 'Qigong')]
    """
    out: list[tuple[str, str, str]] = []

    def gehe(x: Any, wo: str) -> None:
        if isinstance(x, list):
            for e in x:
                gehe(e, wo)
            return
        if not isinstance(x, dict):
            return
        uebung = x.get("uebung")
        if isinstance(uebung, str) and uebung.strip():
            out.append((wo, uebung.strip(), str(x.get("paket") or "").strip()))
        for feld in MARKENFELDER:
            marke = x.get(feld)
            if isinstance(marke, str) and ":" in marke:
                vorn, schraeg, key = marke.partition(":")[2].rpartition("/")
                if schraeg and vorn.strip() and key.strip():
                    out.append((wo, key.strip(), vorn.strip()))
        for wert in x.values():
            if isinstance(wert, dict | list):
                gehe(wert, wo)

    for pl in roh.get("plaene") or []:
        if isinstance(pl, dict):
            gehe(pl, f"Plan „{pl.get('name', pl.get('key', '?'))}“")
    for k in roh.get("kurse") or []:
        if not isinstance(k, dict):
            continue
        wo = f"Kurs „{k.get('name', k.get('key', '?'))}“"
        gehe({f: w for f, w in k.items() if f != "kapitel"}, wo)
        for kap in k.get("kapitel") or []:
            if isinstance(kap, dict):
                gehe(kap, f"{wo}, Kapitel „{kap.get('titel', kap.get('key', '?'))}“")
    return out


def _nachbar_uebungen(datei: Path) -> dict[str, tuple[str, set[str]]]:
    """Paket-ID → ``(Name, IDs der Übungen)`` der TOML-Pakete neben ``datei``
    (`nachbar_tomls`: unter ``pakete/`` auch in anderen Unterordnern)."""
    out: dict[str, tuple[str, set[str]]] = {}
    for anderes in nachbar_tomls(datei):
        if anderes.resolve() == datei.resolve():
            continue
        try:
            inh = seed_inhalt(anderes)
        except (PaketFehler, OSError):
            continue
        out[inh.paket.id] = (inh.paket.name, {u.id for u in inh.uebungen})
    return out


def verweise_pruefen(
    datei: Path, roh: Mapping[str, Any], inhalt: Paketinhalt
) -> tuple[list[str], list[str]]:
    """``(Fehler, Hinweise)``: Geht jeder Übungsverweis auf (V2, `docs/plan_paketverweise.md`)?
    Ein Schlüssel ohne ``paket`` muss einer dieses Pakets sein — sonst fiele die Übung auf
    dem Gerät still aus dem Plan; mit ``paket`` muss es den Schlüssel in jenem Paket geben,
    wenn es als TOML daneben liegt (sonst ein Hinweis „nicht prüfbar“); eine ID ohne Paket,
    die weder hier noch daneben vorkommt, ist ein Hinweis."""
    eigene = {u.id for u in inhalt.uebungen}
    keys = {
        str(e.get("key")).strip()
        for e in roh.get("exercises") or []
        if isinstance(e, dict) and e.get("key")
    }
    toml = datei.suffix == ".toml"
    nachbarn = _nachbar_uebungen(datei) if toml else {}
    namen = nachbar_namen(datei) if toml else {}
    fehler: list[str] = []
    hinweise: list[str] = []
    gesehen: set[tuple[str, str, str]] = set()
    for wo, uebung, paket in _uebungsverweise(roh):
        if (wo, uebung, paket) in gesehen or uebung.startswith("$"):
            continue
        gesehen.add((wo, uebung, paket))
        if paket:
            uid, pid = ergaenzung_ziel(uebung, paket, namen), paket_ziel(paket, namen)
            if uid in eigene or uid in nachbarn.get(pid, ("", set()))[1]:
                continue
            if pid in nachbarn:
                fehler.append(f"{wo}: „{uebung}“ gibt es in „{nachbarn[pid][0]}“ nicht")
            else:
                hinweise.append(
                    f"{wo}: „{paket}“ liegt nicht neben {datei.name} — „{uebung}“ nicht prüfbar"
                )
        elif _UUID_TEXT.fullmatch(uebung):
            if uebung.lower() not in eigene and not any(
                uebung.lower() in ids for _, ids in nachbarn.values()
            ):
                hinweise.append(f"{wo}: Übung {uebung} kennt kein Paket hier — nicht prüfbar")
        elif uebung not in keys:
            fehler.append(
                f"{wo}: „{uebung}“ ist kein Schlüssel dieses Pakets — aus einem anderen Paket "
                '`paket = "…"` dazuschreiben (sonst fällt die Übung auf dem Gerät still weg)'
            )
    return fehler, hinweise


#: Eine ID (UUID) statt eines Schlüssels
_UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


#: Endungen einer Bewegung: ein Streifen (PNG, JPEG), ein GIF; WebP zeigt die App als Standbild
_BEWEGUNG_ENDUNGEN = frozenset({"png", "jpg", "jpeg", "gif", "webp"})
#: Endungen eines Symbols: SVG (eingefärbt) oder PNG (wie es ist)
_SYMBOL_ENDUNGEN = frozenset({"svg", "png"})


def zeitpunkte_pruefen(roh: Mapping[str, Any]) -> list[str]:
    """Hinweise zu Zeitpunkt und Abschnitten der Medien (Ben, 18.11.2026,
    `docs/plan_medien_zeitpunkte.md` §2/§3): ein ``wann`` oder ``oft``, das die App nicht kennt;
    ein ``wann = "bei"`` ohne lesbares Ereignis (die App zeigt das Stück dann nur auf Tipp); an
    einer Übung ein Abschnitt, den ihre Beschreibung nicht hat (das Stück steht dann unter
    „Weitere“). Kein Fehler — die App liest alles davon, nur anders als gemeint.

    >>> roh = {"exercises": [{"name": "Baum", "description": "## Ausführung\\nstehen", "media": [
    ...     {"uri": "https://x.org/a", "abschnitte": ["Ausführung", "Hinweise"]},
    ...     {"uri": "https://x.org/b", "wann": "morgen", "oft": "nie"},
    ...     {"uri": "https://x.org/c", "wann": "bei", "bei": {"art": "satz"}},
    ...     {"uri": "https://x.org/d", "wann": "bei", "bei": {"art": "zeit", "sekunden": 90}}]}]}
    >>> for zeile in zeitpunkte_pruefen(roh):
    ...     print(zeile[:78])
    Übung „Baum“: Medium „https://x.org/a“: Abschnitt „Hinweise“ hat die Beschreib
    Medium „https://x.org/b“: wann = „morgen“ kennt die App nicht (nachher, bei) —
    Medium „https://x.org/b“: oft = „nie“ kennt die App nicht (immer) — es gilt „z
    Medium „https://x.org/c“: wann = „bei“ ohne lesbares Ereignis (bei = { art = …
    """
    from trainingsapp.core.beschreibung import abschnitte
    from trainingsapp.core.models import BEI, IMMER, ZEITPUNKTE, Ereignis

    hinweise: list[str] = []
    for e in roh.get("exercises") or []:
        if not isinstance(e, dict) or not isinstance(e.get("media"), list):
            continue
        da = {a.name.casefold() for a in abschnitte(str(e.get("description") or "")) if a.name}
        for m in e["media"]:
            if not isinstance(m, dict):
                continue
            liste = m.get("abschnitte") or []
            for name in [liste] if isinstance(liste, str) else liste:
                if str(name).strip().casefold() not in da:
                    hinweise.append(
                        f"Übung „{e.get('name', e.get('key', '?'))}“: Medium "
                        f"„{m.get('title') or m.get('datei') or m.get('uri') or '?'}“: Abschnitt "
                        f"„{name}“ hat die Beschreibung nicht — das Stück steht dann unter den "
                        "übrigen"
                    )
    for liste in medienlisten(roh):
        for m in liste:
            if not isinstance(m, dict):
                continue
            name = str(m.get("title") or m.get("datei") or m.get("uri") or "?")
            wann = str(m.get("wann") or "")
            if wann and wann not in ZEITPUNKTE:
                hinweise.append(
                    f"Medium „{name}“: wann = „{wann}“ kennt die App nicht (nachher, bei) — sie "
                    "zeigt es vorher"
                )
            oft = str(m.get("oft") or "")
            if oft and oft != IMMER:
                hinweise.append(
                    f"Medium „{name}“: oft = „{oft}“ kennt die App nicht (immer) — es gilt „zeigen“"
                )
            if wann == BEI and Ereignis.aus(m.get("bei")) is None:
                hinweise.append(
                    f"Medium „{name}“: wann = „bei“ ohne lesbares Ereignis (bei = {{ art = … }}: "
                    "abschnitt mit name, satz oder wdh mit n, zeit mit sekunden, antwort mit "
                    "antworten) — die App zeigt es nur auf Tipp"
                )
    return hinweise


def rollen_pruefen(roh: Mapping[str, Any], ordner: Path) -> tuple[list[str], list[str]]:
    """``(Fehler, Hinweise)`` zu den Rollen der Medien (M1/M2, Ben 18.11.2026,
    `docs/plan_medienrollen.md`): Eine **Bewegung** ist eine Bilddatei des Pakets — ein Streifen
    (Breite ein Vielfaches der Höhe, sonst ein Standbild: Hinweis) oder ein GIF; ein Link oder ein
    Video zeigt die App als Bewegung nicht (Fehler). Ein **Symbol** ist ein SVG oder PNG an der
    Übung, höchstens eines. Eine unbekannte Rolle liest die App als Erklärung (Hinweis).
    ``ordner``: wo die Dateien liegen (neben der TOML) — für die Maße eines Streifens.

    >>> roh = {"exercises": [{"name": "Kniebeuge", "media": [
    ...     {"datei": "medien/k.gif", "rolle": "bewegung"},
    ...     {"uri": "https://x.org/k.mp4", "rolle": "bewegung"},
    ...     {"datei": "medien/k.svg", "rolle": "symbol"},
    ...     {"datei": "medien/k2.svg", "rolle": "symbol"},
    ...     {"uri": "https://x.org/a", "rolle": "tanz"}]}],
    ...     "plaene": [{"uebungen": [{"medien": [{"datei": "x.svg", "rolle": "symbol"}]}]}]}
    >>> f, h = rollen_pruefen(roh, Path("."))
    >>> for zeile in f + h:
    ...     print(zeile[:70])
    Übung „Kniebeuge“: Medium „https://x.org/k.mp4“: eine Bewegung ist ein
    Übung „Kniebeuge“: 2 Symbole — höchstens eines
    Medien: „x.svg“: ein Symbol gehört an die Übung
    Übung „Kniebeuge“: Medium „https://x.org/a“: Rolle „tanz“ kennt die Ap
    """
    fehler: list[str] = []
    hinweise: list[str] = []

    def stueck(wo: str, e: Mapping[str, Any], an_uebung: bool) -> int:
        """Ein Medium prüfen — 1, wenn es ein Symbol ist."""
        rolle = str(e.get("rolle") or "")
        if not rolle or rolle == BEGLEITUNG:
            return 0
        datei = str(e.get("datei") or "")
        name = str(e.get("title") or datei or e.get("uri") or "?")
        if rolle not in ROLLEN:
            hinweise.append(
                f"{wo}: Medium „{name}“: Rolle „{rolle}“ kennt die App nicht — sie zeigt es als "
                "Erklärung"
            )
            return 0
        ist_datei = bool(datei) or e.get("source") == "paket"
        endung = Path(datei or str(e.get("uri") or "")).suffix.lower().lstrip(".")
        if rolle == BEWEGUNG:
            if not ist_datei or endung not in _BEWEGUNG_ENDUNGEN:
                was = "ein Link" if not ist_datei else f"„.{endung}“"
                fehler.append(
                    f"{wo}: Medium „{name}“: eine Bewegung ist eine Bilddatei des Pakets "
                    f"(Bildfolge als PNG oder JPEG, GIF) — {was} zeigt die App nicht"
                )
            elif endung == "webp":
                hinweise.append(
                    f"{wo}: Medium „{name}“: WebP zeigt die App als Standbild, nicht als Bildfolge"
                )
            elif datei and endung != "gif" and (ordner / datei).is_file():
                with (ordner / datei).open("rb") as f:
                    masse = png_masse(f.read(64 * 1024))
                if masse is not None and bilder_in(*masse) < 2:
                    hinweise.append(
                        f"{wo}: Medium „{name}“: {masse[0]} × {masse[1]} ist kein Streifen (Breite "
                        "kein Vielfaches der Höhe) — die App zeigt ein Standbild"
                    )
            return 0
        if not an_uebung:
            fehler.append(f"{wo}: „{name}“: ein Symbol gehört an die Übung")
        elif not ist_datei or endung not in _SYMBOL_ENDUNGEN:
            fehler.append(f"{wo}: Medium „{name}“: ein Symbol ist eine Datei, SVG oder PNG")
        return 1

    an_uebungen: set[int] = set()
    for e in roh.get("exercises") or []:
        if not isinstance(e, dict) or not isinstance(e.get("media"), list):
            continue
        an_uebungen.add(id(e["media"]))
        wo = f"Übung „{e.get('name', e.get('key', '?'))}“"
        n = sum(stueck(wo, m, True) for m in e["media"] if isinstance(m, dict))
        if n > 1:
            fehler.append(f"{wo}: {n} Symbole — höchstens eines")
    for liste in medienlisten(roh):
        if id(liste) not in an_uebungen:
            for m in liste:
                if isinstance(m, dict):
                    stueck("Medien", m, False)
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
    PLAN_ENTFERNEN: ("an",),
    PLAN_TAUSCHEN: ("an",),
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
    felder: Mapping[str, Collection[str]] | None = None,
) -> tuple[list[str], list[str]]:
    """Kursplan und Bausteine **eines** Kurses — ``kurs_roh`` aus der Datei, ``kurs`` wie die
    App ihn liest; ``plaene``: Schlüssel der Paketpläne → Zahl ihrer Planübungen; ``felder``:
    Schlüssel der Übungen dieses Pakets → die Felder ihrer Eingabe."""
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

    # ``wenn`` (Formatversion 8, `docs/plan_kurs_uebungen.md` §10.3): Die Bedingung nennt eine
    # Frage, die es im Kurs gibt — eine Frage im Kapitel mit gespeicherter Antwort (ihre
    # `id`) oder eine Frage an einem Lauf (`<test>.f:<frage>`); ein Feld eines Laufs
    # (`<test>.<feld>`) geht mit `ab`/`bis`. Ein Verweis ins Leere gälte nie
    for s in stellen:
        bedingungen = s.roh.get("wenn")
        for w in bedingungen if isinstance(bedingungen, list) else []:
            name = _marke_roh(w.get("frage")) if isinstance(w, dict) else ""
            block_id, _, rest = name.partition(".")
            quelle = je_id.get(block_id)
            if not name or quelle is None:
                fehler.append(
                    f"{s.ort}: `wenn` nennt die Frage „{name}“ — die gibt es im Kurs nicht"
                )
                continue
            fragen = quelle.roh.get("fragen")
            ids = {
                str(f.get("id"))
                for f in (fragen if isinstance(fragen, list) else [])
                if isinstance(f, dict)
            }
            if rest.startswith("f:") and rest[2:] not in ids:
                fehler.append(
                    f"{s.ort}: `wenn` nennt die Frage „{name}“ — der Lauf „{block_id}“ hat keine "
                    f"Frage „{rest[2:]}“"
                )
            elif not rest and not isinstance(quelle.roh.get("frage"), dict):
                fehler.append(
                    f"{s.ort}: `wenn` nennt „{name}“ — das ist keine Frage, deren Antwort "
                    "gespeichert wird (`frage` mit `art`)"
                )

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
            elif s.art in (PLAN_ENTFERNEN, PLAN_TAUSCHEN):
                probleme.append(f"`{feld}` fehlt — welche Planübung? Der Baustein fällt weg")
        if s.art == PLAN_TAUSCHEN and not str(b.get("uebung") or "").strip():
            probleme.append("`uebung` fehlt — wogegen getauscht wird. Der Baustein fällt weg")
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

    # Ein Test mit Vorgabe (`vorgabe`) ist ein Lauf mit der Uhr: Sie muss etwas vorgeben, und
    # ins Ziel kann nur, was der Lauf vorgibt oder misst
    for s in stellen:
        if s.art != TEST or "vorgabe" not in s.roh:
            continue
        f_vorgabe, h_vorgabe = _vorgabe_pruefen(s.roh, felder)
        fehler.extend(f"{s.ort}: {x}" for x in f_vorgabe)
        hinweise.extend(f"{s.ort}: {x}" for x in h_vorgabe)

    # Ein gestalteter Test (Timer, Takt, Ausführung, „wie die Übung“): was er festlegt, muss
    # zum Lauf passen
    for s in stellen:
        if s.art != TEST:
            continue
        f_frei, h_frei = _gestaltung_pruefen(s.roh)
        fehler.extend(f"{s.ort}: {x}" for x in f_frei)
        hinweise.extend(f"{s.ort}: {x}" for x in h_frei)

    # Ein Test, der „die gewählte“ misst (`aus`), braucht seine Auswahl — hier oder davor
    for s in stellen:
        aus = _marke_roh(s.roh.get("aus")) if s.art == TEST else ""
        if not aus:
            continue
        if str(s.roh.get("uebung") or "").strip():
            fehler.append(
                f"{s.ort}: `uebung` und `aus` zugleich — nur eines davon (die App nähme `aus`)"
            )
        if text := _verweis_pruefen("aus", aus, AUSWAHL, s, je_id):
            fehler.append(f"{s.ort}: {text}")
            continue
        auswahl = je_id[aus]
        if grundlage is None and auswahl.kapitel != s.kapitel:
            # mit Kapitelplänen kennt ein Kapitel nur die Wahl aus seinen eigenen Blöcken — im
            # Kursplan-Kurs steht sie im Kursplan
            fehler.append(
                f"{s.ort}: `aus` „{aus}“ steht in einem anderen Kapitel ({auswahl.ort}) — ohne "
                "`kursplan` muss die Auswahl im selben Kapitel stehen wie der Test"
            )
        feld = str(s.roh.get("feld") or "hold").strip() or "hold"
        zur_wahl = auswahl.roh.get("uebungen")
        ohne = [
            str(u)
            for u in (zur_wahl if isinstance(zur_wahl, list) else [])
            if felder is not None and str(u) in felder and feld not in felder[str(u)]
        ]
        if ohne:
            hinweise.append(
                f"{s.ort}: Das Feld `{feld}` hat nicht jede Übung der Auswahl „{aus}“ "
                f"({', '.join(ohne)}) — für sie gibt es keinen Testwert, ihr Ziel bliebe offen"
            )

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


#: Was ein Testlauf liefert — nur diese Felder können mit `vorgabe` ins Ziel
_LAUF_FELDER = ("reps", "hold", "duration")


def _vorgabe_pruefen(
    block: Mapping[str, Any], felder: Mapping[str, Collection[str]] | None = None
) -> tuple[list[str], list[str]]:
    """``(Fehler, Hinweise)`` zur ``vorgabe`` eines Tests (`core.kursbloecke.Vorgabe`,
    `docs/uebungspakete.md` „Test mit Vorgabe“). Die App liest nachsichtig — eine Vorgabe, die
    nichts vorgibt, fiele still weg und der Test wäre wieder „der jüngste Eintrag“.

    >>> _vorgabe_pruefen({"art": "test", "feld": "reps", "vorgabe": {"art": "skala", "n": 7}})
    ([], [])
    >>> _vorgabe_pruefen({"art": "test", "vorgabe": {"art": "menge"}})[0][0][:37]
    '`vorgabe`: `n` (Wiederholungen) fehlt'
    >>> zeit = {"art": "zeit", "n": 60}
    >>> _vorgabe_pruefen({"art": "test", "feld": "weight", "vorgabe": zeit})[0][0][:44]
    '`feld` „weight“ liefert ein Testlauf nicht —'
    """
    roh = block.get("vorgabe")
    if not isinstance(roh, Mapping):
        return ["`vorgabe` ist keine Tabelle (`art`, `n`, bei `skala` auch `bis`)"], []
    art = str(roh.get("art") or "").strip().lower()
    if art not in VORGABEN:
        bekannt = ", ".join(VORGABEN)
        return [f"`vorgabe`: `art` „{roh.get('art')}“ ist unbekannt (bekannt: {bekannt})"], []
    fehler: list[str] = []
    hinweise: list[str] = []
    if Vorgabe.from_dict(roh) is None:
        was = {
            MENGE: "`n` (Wiederholungen) fehlt oder ist 0",
            ZEIT: "`n` (Sekunden) fehlt oder ist 0",
            SKALA: "`n` (ab) und `bis` (höchstens) geben nichts vor — eines davon zwischen 1 und "
            "9, `bis` nicht kleiner als `n`",
        }[art]
        fehler.append(f"`vorgabe`: {was} — der Test liefe ohne Vorgabe")
    feld = str(block.get("feld") or "hold").strip() or "hold"
    if basis_key(feld) not in _LAUF_FELDER:
        fehler.append(
            f"`feld` „{feld}“ liefert ein Testlauf nicht — mit `vorgabe` nur `reps`, `hold` "
            "oder `duration`"
        )
    uebung = str(block.get("uebung") or "").strip()
    eigene = felder.get(uebung) if felder is not None and uebung else None
    if eigene is not None and art == MENGE and not any(basis_key(k) == "reps" for k in eigene):
        hinweise.append(
            f"`vorgabe` Menge, aber „{uebung}“ hat kein Wiederholungsfeld — der Eintrag des "
            "Tests bringt es mit, im Plan zeigt die Übung es nicht"
        )
    return fehler, hinweise


#: Was der Lauf eines Tests misst — das kann nicht zur Ausführung gehören (nach der Art)
_GEMESSEN = ("reps", "hold", "duration", "seconds", "scale")


def _gestaltung_pruefen(block: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """``(Fehler, Hinweise)`` zu einem **gestalteten** Test (`core.kursbloecke.Block.gestaltet`,
    `docs/uebungspakete.md` „Test, flexibel gestaltet“): ``wie_uebung``, ``timer``, ``takt``,
    ``ziel`` (vorgegebene Ausführung) und ``felder`` (frei gewählte Parameter).

    >>> _gestaltung_pruefen({"art": "test", "wie_uebung": ["uhr", "takt"]})
    ([], [])
    >>> _gestaltung_pruefen({"art": "test", "wie_uebung": ["uhr", "wetter"]})[0][0][:36]
    '`wie_uebung`: „wetter“ ist unbekannt'
    >>> _gestaltung_pruefen({"art": "test", "ziel": {"reps": 10}, "felder": ["weight"]})[0][0][:39]
    '`ziel`: „reps“ misst der Lauf des Tests'
    >>> zeit = {"art": "zeit", "n": 60}
    >>> _gestaltung_pruefen({"art": "test", "vorgabe": zeit, "wie_uebung": ["uhr"]})[1][0][:36]
    'Der Test läuft mit einem Timer — die'
    """
    fehler: list[str] = []
    hinweise: list[str] = []
    wie = block.get("wie_uebung")
    if wie is not None:
        if not isinstance(wie, list):
            fehler.append("`wie_uebung` ist keine Liste (aus: " + ", ".join(WIE_UEBUNG) + ")")
            wie = []
        for w in wie:
            if str(w) not in WIE_UEBUNG:
                bekannt = ", ".join(WIE_UEBUNG)
                fehler.append(f"`wie_uebung`: „{w}“ ist unbekannt (bekannt: {bekannt})")
    if "ziel" in block:
        ziel = block["ziel"]
        if not isinstance(ziel, Mapping):
            fehler.append("`ziel` ist keine Tabelle (beim Test: die vorgegebene Ausführung)")
        else:
            for k in ziel:
                if basis_key(str(k)) in _GEMESSEN:
                    fehler.append(
                        f"`ziel`: „{k}“ misst der Lauf des Tests — beim Test gibt `ziel` nur "
                        "die Ausführung vor (Variante, Seite, Gewicht …); was den Lauf beendet, "
                        "steht in `vorgabe`"
                    )
    if "felder" in block:
        felder = block["felder"]
        if not isinstance(felder, list):
            fehler.append("`felder` ist keine Liste (beim Test: frei gewählte Parameter)")
        else:
            for k in felder:
                if basis_key(str(k)) in _GEMESSEN:
                    fehler.append(
                        f"`felder`: „{k}“ misst der Lauf des Tests — frei wählen lässt sich nur "
                        "die Ausführung"
                    )
    if "takt" in block and block["takt"] != {}:
        f_takt, h_takt = takt_pruefen(block["takt"])
        fehler.extend(f"takt: {x}" for x in f_takt)
        hinweise.extend(f"takt: {x}" for x in h_takt)
    if "timer" in block and not isinstance(block["timer"], Mapping):
        fehler.append("`timer` ist keine Tabelle (ein Timer wie bei einer Planübung)")
    mit_timer = bool(block.get("timer")) or WIE_UHR in [str(w) for w in wie or []]
    vorgabe = block.get("vorgabe")
    zeit_vorgegeben = (
        isinstance(vorgabe, Mapping) and str(vorgabe.get("art") or "").strip().lower() == ZEIT
    )
    if mit_timer and zeit_vorgegeben:
        hinweise.append(
            "Der Test läuft mit einem Timer — die Vorgabe „Zeit“ gilt dann nicht (der Timer "
            "ist die Zeit)"
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

    - ``wenn`` an einem Block, das eine Frage nennt, die es im Kurs nicht gibt (Formatversion 8,
      `docs/plan_kurs_uebungen.md` §10.3); ``plan_entfernen``/``plan_tauschen`` ohne ``an``,
      ``plan_tauschen`` ohne ``uebung``.

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
    felder = {
        str(e["key"]).strip(): {f.key for f in u.result_spec.fields}
        for e, u in zip(eintraege, inhalt.uebungen, strict=False)
        if e.get("key")
    }
    kurse = [k for k in roh.get("kurse") or [] if isinstance(k, dict)]
    for kurs_roh, kurs in zip(kurse, inhalt.kurse, strict=False):
        wo = f"Kurs „{kurs_roh.get('name', kurs_roh.get('key', '?'))}“"
        f_kurs, h_kurs = _kurs_pruefen(kurs_roh, kurs, plaene, schluessel, felder)
        fehler.extend(f"{wo}: {x}" for x in f_kurs)
        hinweise.extend(f"{wo}: {x}" for x in h_kurs)
    return fehler, hinweise


def gegen_pruefen(
    datei: Path,
    gegen: str,
    laden: Callable[[str], bytes] | None = None,
    stufe_als_hinweis: bool = False,
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
        text = (
            f"{STUFE_TEXT[s.stufe]} ({stufen_text(s.gruende)}) → mindestens "
            f"{mindestens(alt.paket.version, s.stufe)}, steht {version_text(neu.paket.version)}"
        )
        # Mit ``stufe_als_hinweis`` (veroeffentlichen.sh, Ben 17.11.2026) sperrt nur eine Nummer,
        # die nicht gestiegen ist — dann sähe kein Gerät das Update. Eine zu kleine Stufe ist
        # ein Hinweis: Die Geräte rechnen die Stufe selbst aus dem Unterschied
        # (`ui/views/updates.py`, `core.paketstufe.automatisch`), die Nummer zeigen sie nur.
        gestiegen = (neu.paket.version or 0) > (alt.paket.version or 0)
        if stufe_als_hinweis and gestiegen:
            return [], [f"gegen {version_text(alt.paket.version)}: {text}"]
        return [text], []
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


def privat_bauen(
    datei: Path, ziel: Path, basis_url: str = "", web_url: str = ""
) -> tuple[Path, str]:
    """Ein privates Paket (U7, TOML mit ``[privat] fuer = "…"``): bauen wie immer, dann
    verschlüsselt nach ``<ziel>/p/<ordner>/paket.json`` (bzw. ``.zip``) — ``(Datei,
    Zugangskarte)``. Die Karte (Link + Code) steht zusätzlich neben der TOML. Mit ``web_url``
    (Adresse der Web-Fassung auf demselben Server) nennt sie auch den Link, der das Paket im
    Browser öffnet (`paketquelle.seitenroute`, `docs/plan_web_pakete.md` §2.3)."""
    roh = tomllib.loads(datei.read_text("utf-8"))
    fuer = " ".join(str((roh.get("privat") or {}).get("fuer") or "").split())
    zugang = _zugang(datei)
    with tempfile.TemporaryDirectory() as arbeit:
        klar = bauen(datei, Path(arbeit), fuer=fuer, basis_url=basis_url, privat=True)
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
    # Im Browser: die Web-Fassung mit der Route hinter „#“ — den Teil schickt der Browser nie
    # an den Server, und die Seite lädt das Paket von dort selbst
    web_link = f"{web_url.rstrip('/')}/#{seitenroute(zugang['ordner'])}" if web_url else ""
    karte = "\n".join(
        [
            f"Privates Paket „{name}“" + (f" für {fuer}" if fuer else ""),
            f"Link: {link}",
            *([f"Im Browser: {web_link}"] if web_link else []),
            f"Code: {code_text(zugang['code'])}",
            "Link und Code getrennt weitergeben (z. B. Link per Nachricht, Code mündlich).",
            *(
                ["„Link“ ist für die App (Importieren → Link), „Im Browser“ öffnet die Seite."]
                if web_link
                else []
            ),
        ]
    )
    datei.with_name(datei.stem + ".zugangskarte.txt").write_text(karte + "\n", "utf-8")
    try:  # QR-Code des Links, wenn `segno` da ist — nur am Rechner, nie in der App
        import segno

        segno.make(link).save(str(datei.with_name(datei.stem + ".zugang.svg")), scale=6)
        if web_link:
            segno.make(web_link).save(str(datei.with_name(datei.stem + ".zugang.web.svg")), scale=6)
    except ImportError:
        pass
    return pfad, karte


def voraussetzungen(
    datei: Path, inhalt: Paketinhalt, basis_url: str = "", privat: bool = False
) -> list[Voraussetzung]:
    """V3 (`docs/plan_paketverweise.md`, Ben 17.11.2026): die Pakete neben ``datei``, auf deren
    Übungen ``inhalt`` verweist — in Plänen, Kursen, Bedingungen, Blöcken und Ergänzungen. Je
    Paket die Version, die daneben steht (die kleinste, von der sicher ist, dass sie die
    Schlüssel hat), und die Paketdatei, aus der die App es laden kann: ``<basis_url>/<datei>``
    für ein öffentliches Paket; für ein privates nur, wenn auch dieses privat ist (sonst stünde
    der geheime Ordner offen im Paket) — den Code nie, nach ihm fragt die App (P220)."""
    if datei.suffix != ".toml":
        return []
    try:
        roh = tomllib.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    namen = nachbar_namen(datei)
    eigene = {u.id for u in inhalt.uebungen}
    keys = {
        str(e.get("key")).strip(): None
        for e in roh.get("exercises") or []
        if isinstance(e, dict) and e.get("key")
    }
    verwiesen: set[str] = set()
    for _, uebung, paket in _uebungsverweise(roh):
        if uebung.startswith("$") or (not paket and uebung in keys):
            continue
        verwiesen.add(ergaenzung_ziel(uebung, paket, namen) if paket else uebung.lower())
    verwiesen |= {e.uebung_id for e in inhalt.ergaenzungen}
    verwiesen -= eigene
    if not verwiesen:
        return []
    out: list[Voraussetzung] = []
    for anderes in nachbar_tomls(datei):
        if anderes.resolve() == datei.resolve():
            continue
        try:
            fremd = seed_inhalt(anderes)
            fremd_roh = tomllib.loads(anderes.read_text(encoding="utf-8"))
        except (PaketFehler, OSError, ValueError):
            continue
        if not verwiesen & {u.id for u in fremd.uebungen}:
            continue
        mit_dateien = _nennt_dateien(fremd_roh)
        quelle = ""
        if basis_url and "privat" not in fremd_roh:
            endung = "zip" if mit_dateien else "json"
            quelle = f"{basis_url.rstrip('/')}/{dateiname(fremd.paket, endung)}"
        elif basis_url and privat:
            zugang = anderes.with_name(anderes.stem + ZUGANG_ENDUNG)
            try:
                ordner = str(json.loads(zugang.read_text("utf-8")).get("ordner") or "")
            except (OSError, ValueError, AttributeError):
                ordner = ""
            if ordner:
                endung = "zip" if mit_dateien else "json"
                quelle = f"{basis_url.rstrip('/')}/p/{ordner}/paket.{endung}"
        out.append(Voraussetzung(fremd.paket.id, fremd.paket.name, fremd.paket.version, quelle))
    return out


def bauen(
    datei: Path, ziel: Path, *, fuer: str = "", basis_url: str = "", privat: bool = False
) -> Path:
    """Schreibt die Paketdatei nach ``ziel`` und gibt den Pfad zurück — JSON, oder eine ZIP
    (Formatversion 4), wenn die TOML Dateien nennt (``datei = "…"``, U3): jede bereinigt
    (`core/bereinigen.py`), benannt nach ihrer Prüfsumme. Verweist das Paket auf Übungen
    anderer Pakete daneben, steht im Kopf, welche es braucht (`voraussetzungen`; mit
    ``basis_url`` auch wo). Wirft `PaketFehler`."""
    ziel.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as arbeit:
        if datei.suffix == ".toml":
            inhalt: Paketinhalt = toml_oeffnen(datei, Path(arbeit))
            inhalt.paket.braucht = voraussetzungen(datei, inhalt, basis_url, privat)
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


#: Wohin `uebernehmen` und `einlesen` Dateien aus einer ZIP der App legen — neben die TOML,
#: je Paket ein Ordner (``pakete/medien/<paket>/``). Mediendateien kommen nie ins git
#: (Inhalte-Repo, CLAUDE.md Regel 6) — der Ordner gehört in dessen ``.gitignore``.
MEDIENORDNER = "medien"
#: Schlüssel einer Übung, wie `pruefen` sie verlangt
_UMLAUTE_KEY = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


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
    #: Der Paketstand je Übung (ID), wie das Gerät ihn bekam — die Basis des Drei-Wege-
    #: Abgleichs; aus der Datenbank (`Exercise.package_standard`). ``None`` = nicht dabei
    basis: dict[str, dict[str, Any]] | None = None
    #: Wann die Datei exportiert wurde (``exportiert``) — wählt die Basis in der Geschichte
    exportiert: datetime | None = None
    #: Die Dateien einer ZIP (Name → Datei) — `uebernehmen` legt neue neben die TOML
    medien: Mapping[str, Paketmedium] = field(default_factory=dict)
    #: Die Datenbank der App — dort ist jede Paketübung aus der Datei gekommen; was der
    #: Datei fehlt, wurde am Laptop gestrichen und kommt nicht zurück
    aus_datenbank: bool = False
    #: Die Pläne des Pakets (``plaene[]``, je Schlüssel) — aus einem Export (die App schreibt
    #: Paketpläne mit ihrem Paketschlüssel, `core.pakete.paketplan_aus`) oder aus der Datenbank
    paketplaene: list[PaketPlan] = field(default_factory=list)
    #: Ihr Paketstand je Schlüssel (`core.pakete.plan_stand`) — aus der Datenbank
    #: (`Plan.package_standard`); ``None`` = nicht dabei
    plan_basis: dict[str, dict[str, Any]] | None = None
    #: Kurse — zählen nur als **Kopie eines Kurses der Datei** (`Kurs.kopie_von`, Stufe 6)
    kurse: list[Kurs] = field(default_factory=list)
    #: Der Paketstand der Originale je Kurs-ID (`core.pakete.kurs_stand`) — aus der Datenbank
    kurs_basis: dict[str, dict[str, Any]] = field(default_factory=dict)


def _exportiert(quelle: Path) -> datetime | None:
    """``exportiert`` aus einer JSON- oder ZIP-Datei der App — ``None``, wenn es fehlt (eine
    mit `bauen` gebaute Datei hat keinen Zeitstempel, K28)."""
    try:
        if zipfile.is_zipfile(quelle):
            with zipfile.ZipFile(quelle) as z:
                roh = json.loads(z.read(PAKET_JSON))
        else:
            roh = json.loads(quelle.read_bytes())
        wert = datetime.fromisoformat(str(roh.get("exportiert")))
    except (OSError, KeyError, ValueError, AttributeError, zipfile.BadZipFile):
        return None
    return wert if wert.tzinfo else wert.replace(tzinfo=UTC)


def _quelle_lesen(quelle: Path, paket_id: str, arbeit: Path) -> Quelle:
    """Ein Export (JSON oder ZIP) oder eine Datenbank der App (nur lesend, ``mode=ro``)."""
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
            paketplaene: dict[str, PaketPlan] = {}
            plan_basis: dict[str, dict[str, Any]] = {}
            for subject in SubjectRepo(con).alle():
                for plan in PlanRepo(con).alle(subject.id):
                    # ein Plan aus einem früheren Durchlauf (Migration 063) ist keine Vorlage mehr
                    if plan.kurs_kapitel_id and plan.kurs_durchlauf_beendet is None:
                        plaene[plan.id] = plan
                    # ein Plan des Pakets (`plaene[]`): je Schlüssel der erste, der vom
                    # Paketstand abweicht — in einem anderen Profil kann er unverändert sein
                    if plan.package_id == paket_id and plan.package_key:
                        pp = paketplan_aus(plan)
                        geaendert = plan.package_standard not in (None, plan_stand(pp))
                        if pp.key not in paketplaene or geaendert:
                            paketplaene[pp.key] = pp
                            if plan.package_standard is not None:
                                plan_basis[pp.key] = plan.package_standard
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
            repo = PaketRepo(con)
            basis = {
                u.id: stand_normieren(standard)
                for u in uebungen
                if (standard := repo.standard(u.id)) is not None
            }
            from trainingsapp.data.kurse import KursRepo

            kurs_repo = KursRepo(con)
            kopien = [
                k
                for k in kurs_repo.alle()
                if k.kopie_von is not None and k.kopie_von.get("paket") == paket_id
            ]
            kurs_basis = {
                k.kopie_von["kurs"]: s
                for k in kopien
                if k.kopie_von is not None
                and (s := kurs_repo.standard(k.kopie_von["kurs"])) is not None
            }
        finally:
            con.close()
        return Quelle(
            paket,
            uebungen,
            list(plaene.values()),
            ergaenzt,
            basis,
            aus_datenbank=True,
            paketplaene=list(paketplaene.values()),
            plan_basis=plan_basis,
            kurse=kopien,
            kurs_basis=kurs_basis,
        )
    arbeit.mkdir(parents=True, exist_ok=True)
    inhalt = paket_oeffnen(quelle, quelle.stem, arbeit=arbeit)
    return Quelle(
        inhalt.paket,
        inhalt.uebungen,
        exportiert=_exportiert(quelle),
        medien=inhalt.medien,
        paketplaene=list(inhalt.plaene),
        kurse=list(inhalt.kurse),
    )


def _git(ordner: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ordner), *args], capture_output=True, text=True, check=True, timeout=60
    ).stdout


def _dateien_merken(roh: dict[str, Any], ordner: Path, arbeit: Path) -> dict[str, str]:
    """`dateien_einbinden` — und dazu, welche Paketdatei (``medien/<sha>.<endung>``) aus
    welchem ``datei = "…"`` kam: So schreibt `uebernehmen` sie wieder als Pfad zurück."""
    vorher = [
        (e, str(e["datei"]))
        for liste in medienlisten(roh)
        for e in liste
        if isinstance(e, dict) and "datei" in e
    ]
    arbeit.mkdir(parents=True, exist_ok=True)
    dateien_einbinden(roh, ordner, arbeit)
    return {str(e["uri"]): rel for e, rel in vorher}


def _basis_aus_git(
    datei: Path, version: int | None, bis: datetime | None, namen: Mapping[str, str], arbeit: Path
) -> (
    tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], str, dict[str, dict[str, Any]]]
    | None
):
    """Der Paketstand je Übung und je Plan der Fassung ``version`` aus der Geschichte von
    ``datei`` — der jüngste Commit mit dieser Version, der **vor dem Export** (``bis``) lag:
    Was danach committet wurde, kann das Gerät nicht haben. ``(Stand je Übungs-ID, Stand je
    Planschlüssel, woher)``; ``None`` ohne git, ohne passenden Commit oder unlesbar."""
    if version is None:
        return None
    try:
        wurzel = Path(_git(datei.parent, "rev-parse", "--show-toplevel").strip())
        rel = datei.resolve().relative_to(wurzel.resolve()).as_posix()
        # --follow: auch über ein Umziehen hinweg (``pakete/x.toml`` → ``pakete/x/x.toml``,
        # Ben 18.11.2026) — je Commit mit dem Pfad, den die Datei damals hatte
        log = _git(
            wurzel,
            *("-c", "core.quotePath=false", "log", "--follow", "--name-only"),
            *("--format=%x00%H %ct", "--", rel),
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    staende: list[tuple[str, str, str]] = []
    for zeile in log.splitlines():
        if zeile.startswith("\x00"):
            commit, _, zeit = zeile[1:].partition(" ")
            staende.append((commit, zeit, rel))
        elif zeile and staende:
            staende[-1] = (*staende[-1][:2], zeile)
    for commit, zeit, damals in staende:
        if not commit or not zeit.isdigit():
            continue
        if bis is not None and int(zeit) > bis.timestamp():
            continue
        try:
            roh = tomllib.loads(_git(wurzel, "show", f"{commit}:{damals}"))
            kopf = roh.get("paket")
            if version_zahl(kopf.get("version") if isinstance(kopf, dict) else None) != version:
                continue
            dateien_einbinden(roh, datei.parent, arbeit)
            inhalt = paket_lesen(roh, name_vorgabe=datei.stem, pakete=namen)
        except (OSError, ValueError, subprocess.SubprocessError, PaketFehler):
            return None
        datum = datetime.fromtimestamp(int(zeit), UTC)
        return (
            {u.id: stand(u) for u in inhalt.uebungen},
            {p.key: plan_stand(p) for p in inhalt.plaene},
            f"Version {version_text(version)} aus Commit {commit[:7]} vom {datum:%d.%m.%Y}",
            {k.id: kurs_stand(k) for k in inhalt.kurse},
        )
    return None


def _sortiert(s: Mapping[str, Any]) -> dict[str, Any]:
    """Typen und Regionen sind Mengen — sortiert, damit eine andere Reihenfolge der App
    nicht als Änderung zählt."""
    return {
        k: sorted(v) if k in ("typen", "regionen") and isinstance(v, list) else v
        for k, v in s.items()
    }


def dreiwege(
    basis: Mapping[str, Any],
    datei: Mapping[str, Any],
    quelle: Mapping[str, Any],
    felder: Iterable[str],
) -> tuple[dict[str, Any], list[Hinweis]]:
    """``(Felder mit neuem Wert, Stellen, die beide geändert haben)`` — **die Datei gewinnt**
    (Ben, 17.11.2026: „TOML, aber die ältere Handyversion darf keinen Konflikt bekommen“).
    Derselbe Abgleich wie beim Update auf dem Gerät (`core.abgleich.abgleichen`), nur mit
    vertauschten Rollen: Die Datei ist „die Person“, die App „das Paket“. Was die App
    geändert hat, kommt, wo die Datei seit der Basis gleich blieb; Beschreibung je
    Abschnitt, Medien je Adresse.

    >>> b = {"name": "Baum", "description": "Knie weich."}
    >>> neu, konflikt = dreiwege(b, {**b, "name": "Baum stehen"},
    ...                          {"name": "Baum tief", "description": "Knie weich, tief."},
    ...                          ["name", "description"])
    >>> neu, [h.feld for h in konflikt]
    ({'description': 'Knie weich, tief.'}, ['name'])
    """
    felder = list(felder)
    d = _sortiert(datei)
    ergebnis, hinweise = abgleichen(_sortiert(basis), d, _sortiert(quelle), felder)
    neu = {f: ergebnis.get(f) for f in felder if _anders(f, d.get(f), ergebnis.get(f))}
    return neu, hinweise


def _kurz(wert: Any, laenge: int = 80) -> str:
    if isinstance(wert, list | dict):
        return f"{len(wert)} Einträge" if isinstance(wert, list) else "eine Tabelle"
    text = " ".join(str(wert if wert is not None else "—").split())
    return text if len(text) <= laenge else text[: laenge - 1] + "…"


def neuer_key(name: str, vergeben: Collection[str]) -> str:
    """Ein Schlüssel aus dem Namen, wie `pruefen` ihn verlangt (a–z, 0–9, ``_``) — eindeutig.

    >>> neuer_key("Rücken stark!", {"ruecken_stark"}), neuer_key("…", set())
    ('ruecken_stark_2', 'uebung')
    """
    roh = re.sub(r"[^a-z0-9]+", "_", name.casefold().translate(_UMLAUTE_KEY)).strip("_")
    basis = roh[:56] or "uebung"
    key, n = basis, 2
    while key in vergeben:
        key, n = f"{basis}_{n}", n + 1
    return key


def _medien_fuers_toml(
    medien: Any,
    rueck: Mapping[str, str],
    quelle_medien: Mapping[str, Paketmedium],
    ordner: Path,
    wurzel: Path,
    schreiben: bool,
    fehlen: list[str],
) -> list[dict[str, Any]]:
    """Medien aus dem Abgleich zurück in die Form der TOML: eine Paketdatei, die die Datei
    schon nennt, wieder als ``datei = "<Pfad>"``; eine neue aus der ZIP der App wird unter
    ``ordner`` abgelegt (Name = Prüfsumme) und so genannt; Links bleiben, wie sie sind. Eine
    Paketdatei, die es weder hier noch in der Quelle gibt, fällt weg (``fehlen``)."""
    out: list[dict[str, Any]] = []
    for m in medien or []:
        if not isinstance(m, dict) or m.get("source") != MediaSource.PAKET:
            out.append(m)
            continue
        name = str(m.get("uri") or "")
        rest = {k: v for k, v in m.items() if k not in ("kind", "source", "uri")}
        if name in rueck:
            out.append({"datei": rueck[name], **rest})
        elif name in quelle_medien:
            ziel = ordner / name.removeprefix("medien/")
            if schreiben and not ziel.is_file():
                ordner.mkdir(parents=True, exist_ok=True)
                quelle_medien[name].kopieren(ziel)
            out.append({"datei": ziel.relative_to(wurzel).as_posix(), **rest})
        else:
            fehlen.append(str(m.get("title") or name))
    return out


def _uebungsblock(u: Exercise, key: str, medien: Callable[[Any], list[dict[str, Any]]]) -> Any:
    """Ein neuer ``[[exercises]]``-Block aus einer Übung der App — ``key`` vorn, die ID folgt
    daraus (nicht die des Geräts: Ben, 17.11.2026, E3 in `docs/plan_rueckweg_handy.md`)."""
    block = _tomlkit().table()
    block["key"] = key
    s = stand(u)
    for feld in FELDNAMEN:
        wert = s.get(feld)
        if feld == "media":
            wert = medien(wert)
        elif feld == "timer":  # die IDs rechnet der Leser aus Übung und Stelle
            wert = [{k: v for k, v in p.items() if k != "id"} for p in wert or []]
        _feld_setzen(block, feld, wert, u)
    return block


#: Was ein Paketplan im Abgleich hat — alles außer dem Schlüssel
def _planfelder(*staende: Mapping[str, Any]) -> list[str]:
    return sorted({f for s in staende for f in s} - {"key"})


def _paketplaene_uebernehmen(
    plaene: list[PaketPlan],
    dokument: Any,
    inhalt_datei: Paketinhalt,
    plan_basis: Mapping[str, dict[str, Any]] | None,
    ohne_basis: bool,
    ids: Mapping[str, str],
    datei: Path,
    medien: Callable[[Any], list[dict[str, Any]]],
) -> tuple[list[str], list[str], list[str]]:
    """Paketpläne (``plaene[]``) der Quelle in die Datei — Stufe 6, Ben 17.11.2026 („beides“:
    am Handy werden auch die Pläne des Pakets geändert). Zugeordnet über den Schlüssel; je
    Feld und je Planübung in drei Wegen (`core.pakete.plan_abgleichen`, die Datei ist „die
    Person“). Übungen im Plan schreibt es als ``key`` bzw. ``uebung`` + ``paket``. Ein Plan,
    den die Basis nicht kennt, wird angehängt; einer, den die Basis kennt und der Datei
    fehlt, wurde dort gestrichen. ``(Zeilen, Hinweise, ohne Basis)``."""
    from trainingsapp.paket_einlesen import _toml_block, _Uebersetzung, nachbar_schluessel

    zeilen: list[str] = []
    hinweise: list[str] = []
    ohne: list[str] = []
    if not plaene:
        return zeilen, hinweise, ohne
    tomlkit = _tomlkit()
    bloecke = list(dokument.get("plaene") or [])
    if len(bloecke) != len(inhalt_datei.plaene):
        return zeilen, [f"{datei.name}: Planblöcke passen nicht — Pläne nicht übernommen"], ohne
    je_key = {p.key: (b, p) for b, p in zip(bloecke, inhalt_datei.plaene, strict=True)}
    u = _Uebersetzung(nachbar_schluessel(datei))
    u.uebungen = dict(ids)

    def fuers_toml(feld: str, wert: Any) -> Any:
        if feld != "uebungen":
            return u.umschreiben(wert)
        out = []
        for e in u.umschreiben(wert) or []:
            if isinstance(e, dict) and "medien" in e:
                e = {**e, "medien": medien(e["medien"])}
            out.append(e)
        return out

    for pp in plaene:
        q = plan_stand(pp)
        name = pp.vorlage.name
        if pp.key in je_key:
            block, alt = je_key[pp.key]
            d = plan_stand(alt)
            b = plan_basis.get(pp.key) if plan_basis is not None else None
            if b is None and not ohne_basis:
                if q != d:
                    ohne.append(f"Plan „{name}“")
                continue
            if b is None:
                neu = dict(q)
            else:
                neu = plan_abgleichen(b, d, q)
                for f in _planfelder(b, d, q):
                    bf, df, qf = b.get(f), d.get(f), q.get(f)
                    if df != bf and qf != bf and qf != df:
                        hinweise.append(
                            f"Plan „{name}“: {f} — in der Datei und in der App geändert, "
                            "die Datei bleibt"
                        )
            felder = [f for f in _planfelder(neu, d) if neu.get(f) != d.get(f)]
            if not felder:
                continue
            for f in felder:
                if neu.get(f) is None:
                    block.pop(f, None)
                else:
                    block[f] = _toml_wert(fuers_toml(f, neu[f]))
            zeilen.append(f"Plan „{name}“: " + ", ".join(felder))
        elif plan_basis is not None and pp.key in plan_basis:
            hinweise.append(f"Plan „{name}“: in der Datei gestrichen, bleibt weg")
        elif plan_basis is None and not ohne_basis:
            ohne.append(f"Plan „{name}“ (neu?)")
        else:
            roh = {f: fuers_toml(f, w) for f, w in pp.to_dict().items()}
            if "plaene" not in dokument:
                dokument["plaene"] = tomlkit.aot()
            dokument["plaene"].append(_toml_block(roh))
            zeilen.append(f"Neuer Plan „{name}“ (key „{pp.key}“)")
    return zeilen, hinweise, ohne


_KOPIE = " (Kopie)"


def kurs_zurueck(kopie: Kurs) -> Kurs:
    """Die Kopie eines Paketkurses mit den IDs ihres Originals (`Kurs.kopie_von`): Kurs,
    Kapitel und Blöcke samt ihrer Verweise (`core.kursbau.umschreiben`); „ (Kopie)“ fällt vom
    Namen. Ein Kapitel, das erst in der Kopie entstand, behält seine ID.

    >>> from trainingsapp.core.kursbau import kurs_kopie
    >>> original = Kurs(name="Rumpf", package_id="p", kapitel=[Kapitel(titel="Eins")])
    >>> z = kurs_zurueck(kurs_kopie(original))
    >>> z.id == original.id, z.name, z.kapitel[0].id == original.kapitel[0].id
    (True, 'Rumpf', True)
    """
    from trainingsapp.core.kursbau import umschreiben

    h = kopie.kopie_von or {}
    kapitel_alt: Mapping[str, str] = h.get("kapitel") or {}
    bloecke_alt: Mapping[str, str] = h.get("bloecke") or {}
    return replace(
        kopie,
        id=str(h.get("kurs") or kopie.id),
        name=kopie.name.removesuffix(_KOPIE),
        kopie_von=None,
        kapitel=[
            replace(
                k,
                id=kapitel_alt.get(k.id, k.id),
                bloecke=[umschreiben(b, bloecke_alt) for b in k.bloecke],
            )
            for k in kopie.kapitel
        ],
    )


def _kurse_uebernehmen(
    quelle: Quelle,
    dokument: Any,
    inhalt_datei: Paketinhalt,
    ohne_basis: bool,
    ids: Mapping[str, str],
    datei: Path,
    medien: Callable[[Any], list[dict[str, Any]]],
    namen: Mapping[str, str],
    arbeit: Path,
) -> tuple[list[str], list[str], list[str]]:
    """Kopien von Kursen der Datei (`Kurs.kopie_von`) zurück in ihren Kurs — Stufe 6, Ben
    17.11.2026. Kurse eines Pakets bearbeitet man in der App als Kopie; hier bekommt die Kopie
    die IDs des Originals zurück (`kurs_zurueck`) und wird **als Ganzes** gegen die Basis
    abgeglichen — wie ein Update der App einen Kurs ganz ersetzt (`docs/plan_paketversionen.md`
    §2): Ist der Kurs in der Datei seit der Basis gleich, kommt die Kopie hinein (Kapitel
    behalten ihren ``key``, neue bekommen einen; Übungen als ``key`` bzw. ``uebung`` +
    ``paket``); haben beide ihn geändert, bleibt die Datei. Basis: der Paketstand des
    Originals in der Datenbank, sonst die Version, aus der die Kopie entstand, aus der
    git-Geschichte. ``(Zeilen, Hinweise, ohne Basis)``."""
    from trainingsapp.paket_einlesen import _toml_block, _Uebersetzung, nachbar_schluessel

    zeilen: list[str] = []
    hinweise: list[str] = []
    ohne: list[str] = []
    kopien = [k for k in quelle.kurse if k.kopie_von is not None]
    if not kopien:
        return zeilen, hinweise, ohne
    bloecke = list(dokument.get("kurse") or [])
    je_id = {
        k.id: (i, b, k) for i, (b, k) in enumerate(zip(bloecke, inhalt_datei.kurse, strict=True))
    }
    u = _Uebersetzung(nachbar_schluessel(datei))
    u.uebungen = dict(ids)
    git_basis: dict[int | None, dict[str, dict[str, Any]]] = {}
    for kopie in kopien:
        h = kopie.kopie_von or {}
        if h.get("kurs") not in je_id:
            hinweise.append(
                f"Kurs „{kopie.name}“: Kopie eines Kurses, den die Datei nicht hat — nicht "
                "übernommen"
            )
            continue
        i, block, original = je_id[h["kurs"]]
        zurueck = kurs_zurueck(kopie)
        b = quelle.kurs_basis.get(original.id)
        if b is None:
            version = h.get("version")
            if version not in git_basis:
                gefunden = _basis_aus_git(datei, version, None, namen, arbeit / f"k{version}")
                git_basis[version] = gefunden[3] if gefunden is not None else {}
            b = git_basis[version].get(original.id)
        d, q = kurs_stand(original), kurs_stand(zurueck)
        if b is not None and q == b:
            continue  # die Kopie ist unverändert
        if b is None and not ohne_basis:
            if q != d:
                ohne.append(f"Kurs „{original.name}“ (aus der Kopie)")
            continue
        if b is not None and d != b:
            if q != d:
                hinweise.append(
                    f"Kurs „{original.name}“: in der Datei und in der Kopie geändert, die Datei "
                    "bleibt"
                )
            continue
        neu = _kurs_fuers_toml(q, block, original, u, medien)
        dokument["kurse"][i] = _toml_block(neu)
        zeilen.append(
            f"Kurs „{original.name}“: aus der Kopie übernommen ({len(q['kapitel'])} Kapitel) — "
            "Kommentare im Kursblock gehen dabei verloren"
        )
    return zeilen, hinweise, ohne


def _kurs_fuers_toml(
    stand_: Mapping[str, Any],
    block: Any,
    original: Kurs,
    u: Any,
    medien: Callable[[Any], list[dict[str, Any]]],
) -> dict[str, Any]:
    """Ein Kurs (`kurs_stand`) in der Form der TOML: ``key``/``id`` wie im alten Block,
    Kapitel mit ihrem ``key`` (aus der ID zurückgerechnet), neue mit einem aus dem Titel."""
    alte_keys: dict[str, str] = {}
    for kap_roh, kap in zip(list(block.get("kapitel") or []), original.kapitel, strict=False):
        if kap_roh.get("key"):
            alte_keys[kap.id] = str(kap_roh["key"])
    vergeben = set(alte_keys.values())
    kapitel: list[dict[str, Any]] = []
    for e in stand_.get("kapitel") or []:
        e = dict(e)
        cid = str(e.pop("id", ""))
        if cid in alte_keys:
            key = alte_keys[cid]
        else:
            key = plan_schluessel(str(e.get("titel") or "kapitel").casefold())
            n, basis_key = 2, key
            while key in vergeben:
                key, n = f"{basis_key}-{n}", n + 1
            vergeben.add(key)
        kap_neu: dict[str, Any] = {"key": key, **u.umschreiben(e)}
        if isinstance(kap_neu.get("media"), list):
            kap_neu["media"] = medien(kap_neu["media"])
        for pl in kap_neu.get("plaene") or []:
            for pe in pl.get("uebungen") or []:
                if isinstance(pe, dict) and isinstance(pe.get("medien"), list):
                    pe["medien"] = medien(pe["medien"])
        for blk in kap_neu.get("bloecke") or []:
            if isinstance(blk, dict) and isinstance(blk.get("medium"), dict):
                umgesetzt = medien([blk["medium"]])
                if umgesetzt:
                    blk["medium"] = umgesetzt[0]
        kapitel.append(kap_neu)
    kopf: dict[str, Any] = {}
    for feld in ("key", "id"):
        if block.get(feld):
            kopf[feld] = str(block[feld])
    rest = {f: w for f, w in stand_.items() if f != "kapitel"}
    return {**kopf, **u.umschreiben(rest), "kapitel": kapitel}


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


def uebernehmen(
    quelle: Path | Quelle, datei: Path, schreiben: bool = True, ohne_basis: bool = False
) -> tuple[list[str], list[str]]:
    """Was in der App eingestellt wurde, in die TOML-Datei übernehmen — ``(Zeilen, Fehler)``.
    ``quelle`` ist ein Export der App (JSON oder ZIP) oder ihre Datenbank (``.db``, nur
    lesend: Übungen und die Pläne aus Kurskapiteln). Ohne ``schreiben`` nur zeigen.

    **Drei Wege** (Ben, 17.11.2026, `docs/plan_rueckweg_handy.md` Stufe 1): Je Übung zählt,
    was die App **seit ihrer Basis** geändert hat — nur das kommt in die Datei, und nur
    dort, wo die Datei seit der Basis gleich blieb; haben beide dieselbe Stelle geändert,
    **bleibt die Datei** und die Zeile nennt den Wert der App (`dreiwege`). Die Basis ist der
    Paketstand der Datenbank oder — bei einem Export — die Fassung mit seiner Version aus
    der git-Geschichte, die vor dem Export committet war (`_basis_aus_git`). Ohne Basis
    übernimmt es nichts und nennt nur, was abweicht; ``ohne_basis`` übernimmt dann die Werte
    der Quelle (wie bis 17.11.2026).

    Neue Übungen eines Exports (in keiner Basis, in keinem Paket daneben) bekommen einen
    Block mit einem ``key`` aus dem Namen; ihre Dateien aus der ZIP liegen danach unter
    ``medien/<paket>/`` neben der TOML. Was die Basis kennt und der Datei fehlt, wurde am
    Laptop gestrichen und kommt nicht zurück. Kapitelpläne (Datenbank) wie bisher."""
    tomlkit = _tomlkit()
    with tempfile.TemporaryDirectory() as arbeit_text:
        arbeit = Path(arbeit_text)
        try:
            text = datei.read_text(encoding="utf-8")
            namen = nachbar_namen(datei)
            roh_datei = tomllib.loads(text)
            rueck = _dateien_merken(roh_datei, datei.parent, arbeit / "datei")
            inhalt_datei = paket_lesen(roh_datei, name_vorgabe=datei.stem, pakete=namen)
            inhalt_quelle = (
                quelle
                if isinstance(quelle, Quelle)
                else _quelle_lesen(quelle, inhalt_datei.paket.id, arbeit / "quelle")
            )
        except (PaketFehler, OSError, ValueError, sqlite3.Error) as grund:
            return [], [str(grund)]
        basis: dict[str, dict[str, Any]] | None = inhalt_quelle.basis
        plan_basis = inhalt_quelle.plan_basis
        woher = "Paketstand der Datenbank"
        if basis is None and inhalt_quelle.paket.id == inhalt_datei.paket.id:
            gefunden = _basis_aus_git(
                datei, inhalt_quelle.paket.version, inhalt_quelle.exportiert, namen, arbeit / "b"
            )
            if gefunden is not None:
                basis, plan_basis, woher, _ = gefunden
        dokument = tomlkit.parse(text)
        bloecke = list(dokument.get("exercises") or [])
        kurs_bloecke = list(dokument.get("kurse") or [])
        if len(bloecke) != len(inhalt_datei.uebungen) or len(kurs_bloecke) != len(
            inhalt_datei.kurse
        ):
            return [], [f"{datei.name}: Blöcke und gelesene Übungen passen nicht zusammen"]
        je_id = {u.id: (block, u) for block, u in zip(bloecke, inhalt_datei.uebungen, strict=True)}
        keys = {str(b.get("key")) for b in bloecke if b.get("key")}
        nachbarn = {uid: name for name, ids in _nachbar_uebungen(datei).values() for uid in ids}
        ordner = datei.parent / MEDIENORDNER / datei.stem
        fehlen: list[str] = []

        def medien(wert: Any) -> list[dict[str, Any]]:
            return _medien_fuers_toml(
                wert, rueck, inhalt_quelle.medien, ordner, datei.parent, schreiben, fehlen
            )

        zeilen: list[str] = []
        hinweise: list[str] = []
        ohne: list[str] = []
        neu_angelegt: list[str] = []
        gestrichen: list[str] = []
        fremd: list[str] = []
        neue_ids: dict[str, str] = {}
        for u in inhalt_quelle.uebungen:
            if u.id not in je_id:
                if u.id in nachbarn:
                    fremd.append(f"{u.name} (aus „{nachbarn[u.id]}“)")
                elif basis is None or inhalt_quelle.aus_datenbank:
                    (gestrichen if inhalt_quelle.aus_datenbank else fremd).append(u.name)
                elif u.id in basis:
                    gestrichen.append(u.name)
                else:
                    key = neuer_key(u.name, keys)
                    keys.add(key)
                    if "exercises" not in dokument:
                        dokument["exercises"] = tomlkit.aot()
                    dokument["exercises"].append(_uebungsblock(u, key, medien))
                    neu_angelegt.append(f"{u.name} (key „{key}“)")
                    neue_ids[u.id] = key
                continue
            block, alt = je_id[u.id]
            felder = list(FELDNAMEN)
            if u.id in inhalt_quelle.ergaenzt:
                aus = [
                    f
                    for f in felder
                    if f in ERGAENZBAR and _anders(f, stand(alt).get(f), stand(u).get(f))
                ]
                felder = [f for f in felder if f not in ERGAENZBAR]
                if aus:
                    hinweise.append(
                        f"{alt.name}: von einem anderen Paket ergänzt — nicht übernommen: "
                        + ", ".join(FELDNAMEN[f] for f in aus)
                    )
            d_stand, q_stand = stand(alt), stand(u)
            b_stand = basis.get(u.id) if basis is not None else None
            if b_stand is None and not ohne_basis:
                abw = [f for f in felder if _anders(f, d_stand.get(f), q_stand.get(f))]
                if abw:
                    ohne.append(f"{alt.name}: " + ", ".join(FELDNAMEN[f] for f in abw))
                continue
            if b_stand is None:
                neu = {
                    f: q_stand.get(f) for f in felder if _anders(f, d_stand.get(f), q_stand.get(f))
                }
                konflikte: list[Hinweis] = []
            else:
                neu, konflikte = dreiwege(b_stand, d_stand, q_stand, felder)
            for h in konflikte:
                teil = f" „{h.teil}“" if h.teil else ""
                hinweise.append(
                    f"{alt.name}: {FELDNAMEN.get(h.feld, h.feld)}{teil} — in der Datei und in "
                    f"der App geändert, die Datei bleibt (App: {_kurz(q_stand.get(h.feld))})"
                )
            if not neu:
                continue
            for feld, wert in neu.items():
                _feld_setzen(block, feld, medien(wert) if feld == "media" else wert, u)
            zeilen.append(f"{alt.name}: " + ", ".join(FELDNAMEN[feld] for feld in neu))
        ids = {
            u.id: str(block.get("key"))
            for block, u in zip(bloecke, inhalt_datei.uebungen, strict=True)
            if block.get("key")
        } | neue_ids
        p_zeilen, p_hinweise, p_ohne = _paketplaene_uebernehmen(
            inhalt_quelle.paketplaene,
            dokument,
            inhalt_datei,
            plan_basis,
            ohne_basis,
            ids,
            datei,
            medien,
        )
        zeilen += p_zeilen
        hinweise += p_hinweise
        ohne += p_ohne
        k_zeilen, k_hinweise, k_ohne = _kurse_uebernehmen(
            inhalt_quelle, dokument, inhalt_datei, ohne_basis, ids, datei, medien, namen, arbeit
        )
        zeilen += k_zeilen
        hinweise += k_hinweise
        ohne += k_ohne
    schluessel = {
        u.id: str(block.get("key") or "")
        for block, u in zip(bloecke, inhalt_datei.uebungen, strict=True)
        if block.get("key")
    }
    plan_zeilen, plan_hinweise = _plaene_uebernehmen(
        inhalt_quelle, kurs_bloecke, inhalt_datei.kurse, schluessel
    )
    zeilen += plan_zeilen
    if neu_angelegt:
        zeilen.append("Neu angelegt: " + ", ".join(neu_angelegt))
    uebernommen = len(zeilen)
    if not uebernommen:
        zeilen.append("Keine Änderung")
    if gestrichen:
        zeilen.append("In der Datei gestrichen, bleibt weg: " + ", ".join(gestrichen))
    if fremd:
        zeilen.append("Nicht übernommen (kein Block mit dieser ID): " + ", ".join(fremd))
    if ohne:
        zeilen.append(
            "Keine Basis (weder Paketstand noch die Version in der git-Geschichte) — nichts "
            "übernommen, nur gemeldet; `--ohne-basis` übernimmt die Werte der Quelle:"
        )
        zeilen += [f"    {z}" for z in ohne]
    zeilen += hinweise + plan_hinweise
    if fehlen:
        zeilen.append("Dateien fehlen in der Quelle, fallen weg: " + ", ".join(fehlen))
    unberuehrt = len(bloecke) - len({u.id for u in inhalt_quelle.uebungen} & schluessel.keys())
    if unberuehrt:
        zeilen.append(f"{unberuehrt} Übung(en) der Datei sind nicht in der Quelle — unverändert")
    if (uebernommen or hinweise) and basis is not None:
        zeilen.append(f"Basis: {woher}")
    if schreiben and uebernommen:
        toml_text = _TABELLE_OHNE_LEERZEILE.sub(r"\1\n\n\2", tomlkit.dumps(dokument))
        datei.write_text(toml_text, encoding="utf-8")
        fehler, _ = pruefen(datei)
        if (vorschlag := versionsvorschlag(datei)) is not None:
            zeilen.append(vorschlag)
        if ordner.is_dir() and not _ignoriert(ordner):
            zeilen.append(
                f"ACHTUNG: {ordner} ist nicht in .gitignore — Mediendateien nie committen"
            )
        return zeilen, [f"{datei.name} nach dem Übernehmen: {text}" for text in fehler]
    return zeilen, []


def versionsvorschlag(datei: Path) -> str | None:
    """Passt die Version der Datei zu dem, was sich seit dem letzten Commit geändert hat
    (`core.paketstufe`)? Eine Zeile mit dem Vorschlag, sonst ``None`` — auch ohne git oder
    ohne committete Fassung. Dateien (``datei = "…"``) zählen dabei nicht mit."""
    try:
        wurzel = Path(_git(datei.parent, "rev-parse", "--show-toplevel").strip())
        rel = datei.resolve().relative_to(wurzel.resolve()).as_posix()
        namen = nachbar_namen(datei)
        alt = paket_lesen(tomllib.loads(_git(wurzel, "show", f"HEAD:{rel}")), pakete=namen)
        neu = paket_lesen(tomllib.loads(datei.read_text(encoding="utf-8")), pakete=namen)
    except (OSError, ValueError, subprocess.SubprocessError, PaketFehler):
        return None
    s = paket_stufe(alt, neu)
    if version_reicht(alt.paket.version, neu.paket.version, s.stufe):
        return None
    return (
        f"Version: steht {version_text(neu.paket.version) or '—'}, für diese Änderungen "
        f"mindestens {mindestens(alt.paket.version, s.stufe)} — {STUFE_TEXT[s.stufe]} "
        f"({stufen_text(s.gruende)}); `version` heben, wenn der Stand auf die Geräte soll"
    )


#: Größte Datei, die `link_pruefen` lädt (ein Video von 20 Minuten in 1080p passt)
LINK_MAX_BYTES = 2_000_000_000


def link_laden(url: str, grenze: int = LINK_MAX_BYTES) -> tuple[str, str, int]:
    """``(SHA-256, Content-Type, Bytes)`` dessen, was hinter ``url`` liegt — gestreamt, nur
    https (auch nach Umleitungen: `netz.OEFFNER` bricht vor einer http-Anfrage ab, S35),
    höchstens ``grenze`` Bytes. Wirft `OSError`/`ValueError`."""
    import urllib.request

    from trainingsapp.core.netz import OEFFNER

    if not url.startswith("https://"):
        raise ValueError("nur https-Adressen")
    anfrage = urllib.request.Request(url, headers={"User-Agent": "trainingsapp-paket"})
    with OEFFNER.open(anfrage, timeout=60) as antwort:
        if not str(antwort.geturl()).startswith("https://"):
            raise ValueError(f"umgeleitet auf {antwort.geturl()} — nicht https")
        art = str(antwort.headers.get("Content-Type") or "")
        h, n = hashlib.sha256(), 0
        while block := antwort.read(1 << 20):
            n += len(block)
            if n > grenze:
                raise ValueError(f"größer als {grenze / 1e9:.0f} GB")
            h.update(block)
    return h.hexdigest(), art, n


def verlinken(
    datei: Path,
    medium: str,
    url: str,
    *,
    pruefen_mit: Callable[[str], tuple[str, str, int]] | None = None,
    schreiben: bool = True,
) -> tuple[list[str], list[str]]:
    """Eine Datei des Pakets (``datei = "<medium>"``) durch einen Link ersetzen — Stufe 5,
    `docs/plan_rueckweg_handy.md` (Ben 17.11.2026: Medien je Stück als Datei oder Link). Jeder
    Eintrag, der die Datei nennt, bekommt ``uri = "<url>"``; Titel und alles andere bleiben.
    Mit ``pruefen_mit`` (`link_laden`) wird der Link einmal geladen: Dieselbe Prüfsumme wie
    die Datei heißt, der Link liefert genau sie (für das Abspielen in der App); eine andere
    oder eine Webseite (``text/html``) ist ein Fehler — dann bleibt die Datei.
    ``(Zeilen, Fehler)``."""
    tomlkit = _tomlkit()
    if not links_erlaubt(url) or not url.startswith("https://"):
        return [], [f"„{url}“ ist kein https-Link"]
    pfad = (datei.parent / medium).resolve()
    if datei.parent.resolve() not in pfad.parents or not pfad.is_file():
        return [], [f"„{medium}“ liegt nicht im Paketordner"]
    try:
        dokument = tomlkit.parse(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError) as grund:
        return [], [f"{datei.name}: {grund}"]
    treffer = [
        e
        for liste in medienlisten(dokument)
        for e in liste
        if isinstance(e, dict)
        and "datei" in e
        and (datei.parent / str(e["datei"])).resolve() == pfad
    ]
    if not treffer:
        return [], [f"{datei.name} nennt „{medium}“ nicht"]
    zeilen: list[str] = []
    if pruefen_mit is not None:
        try:
            sha, art, groesse = pruefen_mit(url)
        except (OSError, ValueError) as grund:
            return [], [f"{url}: {grund}"]
        if "text/html" in art:
            return [], [
                f"{url} liefert eine Webseite ({art}), nicht die Datei — bei Dropbox `raw=1` "
                "statt `dl=0`; die Datei bleibt"
            ]
        if sha != sha256_datei(pfad):
            return [], [
                f"{url} liefert eine andere Datei ({groesse / 1e6:.1f} MB, {art or '?'}) — "
                "die Datei bleibt"
            ]
        zeilen.append(f"Link geprüft: dieselbe Datei ({groesse / 1e6:.1f} MB, {art or '?'})")
    if direkt(url):
        # Ein Video, das die App selbst lädt: Sie vergleicht nach dem Laden (Stufe 7)
        url = mit_pruefsumme(url, sha256_datei(pfad))
        zeilen.append("Prüfsumme am Link (#sha256=…): Die App spielt nur genau diese Datei")
    for e in treffer:
        del e["datei"]
        e["uri"] = url
    zeilen.append(f"{datei.name}: {len(treffer)} Eintrag/Einträge nennen jetzt {url}")
    if schreiben:
        text = _TABELLE_OHNE_LEERZEILE.sub(r"\1\n\n\2", tomlkit.dumps(dokument))
        datei.write_text(text, encoding="utf-8")
        zeilen.append(
            f"Die Datei {medium} braucht das Paket nicht mehr — löschen, wenn nichts sie nennt"
        )
    return zeilen, []


def _ignoriert(pfad: Path) -> bool:
    """Ignoriert git den Pfad? Ohne git (kein Repo): ja — dann gibt es nichts zu committen."""
    try:
        subprocess.run(
            ["git", "-C", str(pfad.parent), "rev-parse", "--git-dir"],
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    lauf = subprocess.run(
        ["git", "-C", str(pfad.parent), "check-ignore", "-q", str(pfad)],
        capture_output=True,
        timeout=30,
    )
    return lauf.returncode == 0


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
    p.add_argument(
        "--stufe-als-hinweis",
        action="store_true",
        help="mit --gegen: nur eine nicht gestiegene Nummer ist ein Fehler",
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
    b.add_argument(
        "--web-url",
        default="",
        help="Adresse der Web-Fassung auf demselben Server — die Zugangskarte privater Pakete "
        "nennt dann auch den Link, der das Paket im Browser öffnet",
    )
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
    u.add_argument(
        "--ohne-basis",
        action="store_true",
        help="ohne Basis (Paketstand, git-Geschichte) die Werte der Quelle übernehmen",
    )
    v = sub.add_parser("verlinken", help="eine Datei des Pakets durch einen https-Link ersetzen")
    v.add_argument("datei", type=Path, help="die TOML-Datei des Pakets")
    v.add_argument("medium", help="der Pfad, den `datei = …` nennt (relativ zur TOML)")
    v.add_argument("url", help="wo die Datei jetzt liegt (https)")
    v.add_argument(
        "--pruefen", action="store_true", help="den Link einmal laden und die Prüfsumme vergleichen"
    )
    v.add_argument("--probe", action="store_true", help="nur zeigen, nichts schreiben")
    e = sub.add_parser(
        "einlesen",
        help="einen Export der App (eigenes Paket, JSON oder ZIP) als TOML einlesen",
    )
    e.add_argument("quelle", type=Path, help="die Datei vom Handy (JSON oder ZIP)")
    e.add_argument(
        "datei", type=Path, help="die TOML — neu, oder die einer früheren Runde (gleicht ab)"
    )
    e.add_argument("--name", default="", help="Name des neuen Pakets (sonst der vom Handy)")
    e.add_argument("--privat", action="store_true", help="privates Paket ([privat])")
    e.add_argument("--fuer", default="", help="für wen (Vorname oder Kürzel) — macht es privat")
    e.add_argument("--probe", action="store_true", help="nur zeigen, nichts schreiben")
    k = sub.add_parser(
        "verkleinern",
        help="große Videos einer Paketdatei (ZIP) mit ffmpeg verkleinern — neue Datei daneben",
    )
    k.add_argument("quelle", type=Path, help="die Paketdatei (ZIP aus dem Export der App)")
    k.add_argument(
        "--ordner", type=Path, help="wohin die neue Datei kommt (Vorgabe: verkleinert/ daneben)"
    )
    k.add_argument("--vorlage", default="mittel", help="klein, mittel (Vorgabe) oder gross")
    k.add_argument("--alle", action="store_true", help="auch Videos, die nicht groß sind")
    k.add_argument("--probe", action="store_true", help="nur zeigen, nichts schreiben")
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
                f_gegen, h_gegen = gegen_pruefen(
                    datei, args.gegen, stufe_als_hinweis=args.stufe_als_hinweis
                )
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
                    pfad, karte = privat_bauen(datei, args.ziel, args.basis_url, args.web_url)
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
                    print(bauen(datei, args.ziel, basis_url=args.basis_url))
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
        zeilen, fehler = uebernehmen(
            args.quelle, args.datei, schreiben=not args.probe, ohne_basis=args.ohne_basis
        )
        for z in zeilen:
            print(z)
        for f in fehler:
            print(f"FEHLER: {f}")
        if not fehler and not args.probe and zeilen and zeilen[0] != "Keine Änderung":
            print(f"{args.datei}: geschrieben — `git diff` zeigt, was aus der App kam")
        return 1 if fehler else 0
    if args.befehl == "verlinken":
        zeilen, fehler = verlinken(
            args.datei,
            args.medium,
            args.url,
            pruefen_mit=link_laden if args.pruefen else None,
            schreiben=not args.probe,
        )
        for z in zeilen:
            print(z)
        for f in fehler:
            print(f"FEHLER: {f}")
        return 1 if fehler else 0
    if args.befehl == "einlesen":
        from trainingsapp.paket_einlesen import einlesen

        zeilen, fehler = einlesen(
            args.quelle,
            args.datei,
            name=args.name,
            privat=args.privat,
            fuer=args.fuer,
            schreiben=not args.probe,
        )
        for z in zeilen:
            print(z)
        for f in fehler:
            print(f"FEHLER: {f}")
        return 1 if fehler else 0
    if args.befehl == "verkleinern":
        # P225 Stufe 3, `docs/plan_medien_reiter.md` §5 — das Original bleibt
        from trainingsapp.paket_verkleinern import verkleinern

        try:
            zeilen, fehler = verkleinern(
                args.quelle,
                args.ordner or args.quelle.parent / "verkleinert",
                vorlage=args.vorlage,
                alle=args.alle,
                schreiben=not args.probe,
            )
        except (PaketFehler, RuntimeError, OSError) as abbruch:
            zeilen, fehler = [], [str(abbruch)]
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
