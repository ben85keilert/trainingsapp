"""Übungspakete — das Dateiformat.

Übungen kommen über Pakete (Ben, 14.10.2026): Die mitgelieferten stehen im
Paket „Standard“ (`data/seed/standard.toml`); weitere — Qigong,
Pilates, Yoga, die Sammlung von jemand anderem — kommen per Import dazu, und
ausgewählte Übungen gehen per Export als Datei hinaus. Eine Paketdatei ist JSON::

    {
      "format": "trainingsapp-uebungspaket",
      "version": 1,
      "paket": {"id": "…", "name": "Qigong", "beschreibung": "…", "version": 2},
      "exercises": [{"key": "baum", "name": "Stehen wie ein Baum", …}, …]
    }

Hier steht nur das Format: JSON → `Exercise` und zurück, ohne Datenbank.
Was ein Import mit vorhandenen Übungen macht, entscheidet `data/pakete.py`.
Alle Felder: `docs/uebungspakete.md`.

**IDs.** Eine Übung behält ihre ID auf jedem Gerät — nur so erkennt ein
zweiter Import „dieselbe Übung, neuer Stand“. Exportierte Übungen tragen
ihre ID (``"id"``). Wer ein Paket von Hand schreibt, gibt stattdessen einen
Schlüssel an (``"key"``, sonst zählt der Name); die ID folgt per UUIDv5 aus
Paket und Schlüssel. „Standard“ (früher „Grundausstattung“) behält die IDs von vor den
Paketen (nur aus dem Schlüssel) — sonst stünde jede mitgelieferte Übung nach
dem Update doppelt da.

**Kurse** (Ben, 15.10.2026; `core/kurse.py`) kommen seit Formatversion 2 im
Feld ``kurse`` mit: Kapitel mit Text, Medien, Plan-Vorlagen und Bedingung. Übungen
darin heißen wie im Paket (``key``) oder tragen eine ID. Ein Paket darf auch nur
Kurse enthalten.

**Was nicht hineinkommt:** Einträge, Messungen, Strecken, eigene Pläne, der
Kursfortschritt — ein Paket beschreibt Übungen und Kurse, nicht Training. Eigene
Fotos und Videos (``local``) liegen nur auf dem Gerät und bleiben draußen;
Video-Links kommen mit.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .kurse import (
    BEDINGUNGEN,
    FREISCHALTUNGEN,
    RUECKFRAGE,
    Bedingung,
    Kapitel,
    Kurs,
    PlanVorlage,
    medien_from_list,
    medien_to_list,
)
from .models import Exercise, Media, MediaKind, MediaSource, jetzt
from .result_spec import VORLAGEN, ResultSpec

#: Kennung im Feld ``format`` — andere JSON-Dateien (Messungen) sind kein Paket
FORMAT = "trainingsapp-uebungspaket"
#: Höchste Formatversion, die diese App liest — 2 seit es Kurse gibt (``kurse``);
#: eine Datei ohne Kurse wird weiter als Version 1 geschrieben
FORMAT_VERSION = 2

#: Namensraum der UUIDv5-IDs — derselbe wie für den Seed vor den Paketen.
#: Einmal gewählt, nie ändern, sonst bekäme jede Übung eine neue ID.
NAMENSRAUM = uuid.UUID("6f1c2b3a-7d4e-4a5b-9c8d-1e2f3a4b5c6d")

#: Das Paket der mitgelieferten Übungen, „Standard“ — die ID stammt aus seinem
#: früheren Namen (= ``paket_id("Grundausstattung")``)
GRUNDAUSSTATTUNG = "2c1194ea-67ba-536d-aa7d-bf74bc3c73d4"

#: Eingabe ohne Angabe im Paket: Wiederholungen je Satz (wie beim Seed bisher)
STANDARD_SPEC = "saetze_wdh"

#: Kein Paket heißt so — eigene Übungen gehören zu keinem Paket (Ben, 14.10.2026)
_EIGENE = {"eigene", "eigene übungen"}


#: Größer ist kein Übungspaket mehr (33 Übungen = 30 kB; 5 MB lassen Platz für Texte)
MAX_PAKET_BYTES = 5_000_000


class PaketFehler(ValueError):
    """Die Datei ist kein lesbares Übungspaket — der Text sagt, warum."""


@dataclass(slots=True)
class Paket:
    """Kopf einer Paketdatei bzw. ein installiertes Paket (Tabelle ``package``)."""

    id: str
    name: str
    beschreibung: str = ""
    #: Setzt, wer das Paket schreibt (optional). Ein Export übernimmt die installierte.
    version: int | None = None
    installiert: datetime | None = None
    aktualisiert: datetime | None = None
    #: Im Paketmanager entfernt (Migration 015) — die Übungen liegen im Papierkorb
    entfernt: datetime | None = None


@dataclass(slots=True)
class Paketinhalt:
    """Eine gelesene Paketdatei.

    Jede Übung trägt ``package_id`` = Paket. ``family_id`` ist die Angabe
    ``variante_von`` als ID — ob sie gilt, entscheidet der Import.
    """

    paket: Paket
    uebungen: list[Exercise] = field(default_factory=list)
    #: Kurse des Pakets (Formatversion 2) — jeder trägt ``package_id`` = Paket
    kurse: list[Kurs] = field(default_factory=list)


def paket_id(name: str) -> str:
    """Die ID eines Pakets, das nur einen Namen hat — gleicher Name, gleiches Paket.

    Groß/klein und Leerzeichen zählen nicht:

    >>> paket_id("Grundausstattung") == GRUNDAUSSTATTUNG
    True
    >>> paket_id(" qigong ") == paket_id("Qigong")
    True
    """
    return str(uuid.uuid5(NAMENSRAUM, "paket:" + " ".join(name.split()).casefold()))


def uebung_id(paket: str, key: str) -> str:
    """Die ID einer Übung, die im Paket nur einen Schlüssel hat.

    >>> uebung_id("p1", "baum") == uebung_id("p1", "baum")
    True
    >>> uebung_id("p1", "baum") != uebung_id("p2", "baum")
    True
    >>> uebung_id(GRUNDAUSSTATTUNG, "wadenheben") == str(uuid.uuid5(NAMENSRAUM, "wadenheben"))
    True
    """
    if paket == GRUNDAUSSTATTUNG:  # die IDs von vor den Paketen
        return str(uuid.uuid5(NAMENSRAUM, key))
    return str(uuid.uuid5(NAMENSRAUM, f"{paket}/{key}"))


def kurs_id(paket: str, key: str) -> str:
    """Die ID eines Kurses, der im Paket nur einen Schlüssel hat.

    >>> kurs_id("p1", "hrv") != uebung_id("p1", "hrv")
    True
    """
    return str(uuid.uuid5(NAMENSRAUM, f"{paket}/kurs:{key}"))


def kapitel_id(kurs: str, key: str) -> str:
    """Die ID eines Kapitels aus Kurs-ID und Schlüssel (oder Nummer) — der
    Fortschritt hängt daran, darum muss sie auf jedem Gerät gleich sein."""
    return str(uuid.uuid5(NAMENSRAUM, f"{kurs}/kapitel:{key}"))


def name_pruefen(name: str) -> str | None:
    """Fehlertext, wenn ``name`` kein Paketname sein kann — sonst ``None``.

    >>> name_pruefen("Qigong") is None
    True
    >>> name_pruefen("  ")
    'Ein Paket braucht einen Namen.'
    >>> name_pruefen("eigene übungen") is not None
    True
    """
    name = " ".join(name.split())
    if not name:
        return "Ein Paket braucht einen Namen."
    if name.casefold() in _EIGENE:
        return "„Eigene“ ist kein Paketname — eigene Übungen gehören zu keinem Paket."
    return None


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------


def paket_lesen(daten: bytes | str | dict[str, Any], name_vorgabe: str = "") -> Paketinhalt:
    """Liest eine Paketdatei; wirft `PaketFehler` mit einem Satz für Menschen.

    ``name_vorgabe`` (etwa der Dateiname) gilt, wenn die Datei keinen Paketkopf hat.

    >>> inhalt = paket_lesen('{"paket": {"name": "Test"}, "exercises": [{"name": "Baum"}]}')
    >>> inhalt.paket.name, [u.name for u in inhalt.uebungen]
    ('Test', ['Baum'])
    >>> inhalt.uebungen[0].package_id == inhalt.paket.id == paket_id("Test")
    True
    >>> try:
    ...     paket_lesen('{"exercises": []}')
    ... except PaketFehler as fehler:
    ...     print(fehler)
    Das Paket enthält keine Übungen.
    """
    if isinstance(daten, dict):
        roh: Any = daten
    else:
        if len(daten) > MAX_PAKET_BYTES:
            raise PaketFehler(
                f"Die Datei ist zu groß für ein Übungspaket ({len(daten) / 1e6:.0f} MB)."
            )
        try:
            roh = json.loads(daten)
        except (ValueError, RecursionError):  # auch UnicodeDecodeError, tief verschachtelt
            raise PaketFehler("Das ist keine Paketdatei (kein JSON).") from None
    if not isinstance(roh, dict) or roh.get("format", FORMAT) != FORMAT:
        raise PaketFehler("Das ist keine Paketdatei.")
    version = roh.get("version", 1)
    if not _ganzzahl(version):
        raise PaketFehler("Das ist keine Paketdatei (Formatversion unlesbar).")
    if version > FORMAT_VERSION:
        raise PaketFehler("Das Paket ist neuer als diese App — bitte die App aktualisieren.")
    eintraege = roh.get("exercises", [])
    if not isinstance(eintraege, list):
        raise PaketFehler("Das ist keine Paketdatei (keine Übungsliste).")
    kurs_eintraege = roh.get("kurse", [])
    if not isinstance(kurs_eintraege, list):
        raise PaketFehler("Das ist keine Paketdatei (Kursliste unlesbar).")
    if not eintraege and not kurs_eintraege:
        raise PaketFehler("Das Paket enthält keine Übungen.")

    kopf = roh.get("paket", {})
    if not isinstance(kopf, dict):
        raise PaketFehler("Der Paketkopf ist unlesbar.")
    name = " ".join(str(kopf.get("name") or name_vorgabe).split())
    if (fehler := name_pruefen(name)) is not None:
        raise PaketFehler(fehler)
    pversion = kopf.get("version")
    if pversion is not None and not _ganzzahl(pversion):
        raise PaketFehler("Die Paketversion muss eine ganze Zahl sein.")
    paket = Paket(
        id=str(kopf.get("id") or "").strip() or paket_id(name),
        name=name,
        beschreibung=str(kopf.get("beschreibung") or "").strip(),
        version=pversion,
    )

    uebungen: list[Exercise] = []
    ids: set[str] = set()
    schluessel: dict[str, str] = {}  # Schlüssel → ID, für „variante_von"
    probleme: list[str] = []
    for nr, eintrag in enumerate(eintraege, start=1):
        try:
            uebung, key = _uebung_lesen(eintrag, paket.id)
        except (KeyError, TypeError, ValueError) as grund:
            titel = eintrag.get("name") if isinstance(eintrag, dict) else None
            probleme.append(f"Übung {nr}{f' („{titel}“)' if titel else ''}: {grund}")
            continue
        if uebung.id in ids:
            probleme.append(f"Übung {nr} („{uebung.name}“) steht doppelt im Paket.")
            continue
        ids.add(uebung.id)
        if key:
            schluessel[key] = uebung.id
        uebungen.append(uebung)
    if probleme:
        rest = len(probleme) - 3
        raise PaketFehler("\n".join(probleme[:3]) + (f"\n… und {rest} weitere" if rest > 0 else ""))
    for u in uebungen:  # „variante_von" darf Schlüssel oder ID sein
        if u.family_id is not None:
            u.family_id = schluessel.get(u.family_id, u.family_id)
            if u.family_id == u.id:
                u.family_id = None

    kurse: list[Kurs] = []
    kurs_ids: set[str] = set()
    for nr, eintrag in enumerate(kurs_eintraege, start=1):
        try:
            kurs = _kurs_lesen(eintrag, paket.id, schluessel)
        except (KeyError, TypeError, ValueError) as grund:
            titel = eintrag.get("name") if isinstance(eintrag, dict) else None
            probleme.append(f"Kurs {nr}{f' („{titel}“)' if titel else ''}: {grund}")
            continue
        if kurs.id in kurs_ids:
            probleme.append(f"Kurs {nr} („{kurs.name}“) steht doppelt im Paket.")
            continue
        kurs_ids.add(kurs.id)
        kurse.append(kurs)
    if probleme:
        rest = len(probleme) - 3
        raise PaketFehler("\n".join(probleme[:3]) + (f"\n… und {rest} weitere" if rest > 0 else ""))
    return Paketinhalt(paket, uebungen, kurse)


def _kurs_lesen(eintrag: Any, paket: str, schluessel: Mapping[str, str]) -> Kurs:
    """Ein Kurs aus der Datei. ``schluessel`` löst Übungsschlüssel des Pakets in IDs auf."""
    if not isinstance(eintrag, dict):
        raise ValueError("kein Eintrag mit Feldern")
    name = " ".join(str(eintrag.get("name") or "").split())
    if not name:
        raise ValueError("der Name fehlt")
    key = str(eintrag.get("key") or "").strip()
    kid = str(eintrag.get("id") or "").strip() or kurs_id(paket, key or name)
    freischaltung = str(eintrag.get("freischaltung") or RUECKFRAGE)
    if freischaltung not in FREISCHALTUNGEN:
        raise ValueError(f"unbekannte Freischaltung „{freischaltung}“")
    kapitel: list[Kapitel] = []
    ids: set[str] = set()
    for nr, roh in enumerate(_liste(eintrag.get("kapitel", []), "kapitel"), start=1):
        if not isinstance(roh, dict):
            raise ValueError(f"Kapitel {nr} ist kein Eintrag mit Feldern")
        titel = " ".join(str(roh.get("titel") or roh.get("title") or "").split())
        if not titel:
            raise ValueError(f"Kapitel {nr}: der Titel fehlt")
        kkey = str(roh.get("key") or "").strip() or str(nr)
        k = Kapitel(
            id=str(roh.get("id") or "").strip() or kapitel_id(kid, kkey),
            kurs_id=kid,
            order=nr - 1,
            titel=titel,
            text=str(roh.get("text") or ""),
            media=medien_from_list(_liste(roh.get("media", []), "media")),
            plaene=[_vorlage_lesen(v, schluessel) for v in _liste(roh.get("plaene", []), "plaene")],
            bedingung=_bedingung_lesen(roh.get("bedingung", {}), schluessel),
        )
        if k.id in ids:
            raise ValueError(f"Kapitel {nr} („{titel}“) steht doppelt")
        ids.add(k.id)
        kapitel.append(k)
    if not kapitel:
        raise ValueError("der Kurs hat kein Kapitel")
    return Kurs(
        id=kid,
        name=name,
        beschreibung=str(eintrag.get("beschreibung") or "").strip(),
        freischaltung=freischaltung,
        kapitel=kapitel,
        package_id=paket,
    )


def _vorlage_lesen(roh: Any, schluessel: Mapping[str, str]) -> PlanVorlage:
    vorlage = PlanVorlage.from_dict(_objekt(roh, "plaene"))
    if not vorlage.items:
        raise ValueError(f"Plan „{vorlage.name}“ hat keine Übung")
    for item in vorlage.items:
        item.exercise_id = schluessel.get(item.exercise_id, item.exercise_id)
        _werte_pruefen(item.target, "ziel")
    return vorlage


def _bedingung_lesen(roh: Any, schluessel: Mapping[str, str]) -> Bedingung:
    b = Bedingung.from_dict(_objekt(roh, "bedingung"))
    art = str(roh.get("art") or "gelesen") if isinstance(roh, dict) else "gelesen"
    if art not in BEDINGUNGEN:
        raise ValueError(f"unbekannte Bedingung „{art}“")
    if art != "gelesen" and b.soll <= 0:
        raise ValueError(f"Bedingung „{art}“ braucht ein Soll größer 0")
    if art == "summe" and not b.exercise_id:
        raise ValueError("Bedingung „summe“ braucht eine Übung")
    b.exercise_id = schluessel.get(b.exercise_id, b.exercise_id)
    return b


def _uebung_lesen(eintrag: Any, paket: str) -> tuple[Exercise, str]:
    """Eine Übung aus der Datei — samt Schlüssel (leer, wenn keiner da ist)."""
    if not isinstance(eintrag, dict):
        raise ValueError("kein Eintrag mit Feldern")
    name = " ".join(str(eintrag.get("name") or "").split())
    if not name:
        raise ValueError("der Name fehlt")
    key = str(eintrag.get("key") or "").strip()
    if "result_spec" in eintrag:
        try:
            spec = ResultSpec.from_dict(_objekt(eintrag["result_spec"], "result_spec"))
        except (KeyError, TypeError, ValueError) as grund:
            raise ValueError("die Parameter (result_spec) sind unlesbar") from grund
    else:
        kurz = str(eintrag.get("spec") or STANDARD_SPEC)
        if kurz not in VORLAGEN:
            raise ValueError(f"unbekannte Eingabe „{kurz}“")
        spec = ResultSpec.from_dict(VORLAGEN[kurz][1].to_dict())  # Kopie, nicht die Vorlage
    _spec_zahlen_pruefen(spec)
    limit_spec = _objekt(eintrag.get("limit_spec", {}), "limit_spec")
    _werte_pruefen(limit_spec, "limit_spec")
    default_target = _objekt(eintrag.get("default_target", {}), "default_target")
    _werte_pruefen(default_target, "default_target")
    felder = eintrag.get("default_felder")
    variante = str(eintrag.get("variante_von") or "").strip()
    return (
        Exercise(
            id=str(eintrag.get("id") or "").strip() or uebung_id(paket, key or name),
            name=name,
            description=str(eintrag.get("description") or "").strip(),
            icon_key=str(eintrag["icon_key"]) if eintrag.get("icon_key") else None,
            is_builtin=paket == GRUNDAUSSTATTUNG,
            result_spec=spec,
            limit_spec=limit_spec,
            default_target=default_target,
            default_felder=None if felder is None else _texte(felder, "default_felder"),
            media=[
                m
                for m in (_medium(d) for d in _liste(eintrag.get("media", []), "media"))
                if m is not None
            ],
            typen=_texte(eintrag.get("typen", []), "typen"),
            regionen=_texte(eintrag.get("regionen", []), "regionen"),
            package_id=paket,
            family_id=variante or None,
        ),
        key,
    )


def _ganzzahl(wert: Any) -> bool:
    return isinstance(wert, int) and not isinstance(wert, bool)


def _zahl(wert: Any) -> bool:
    return isinstance(wert, int | float) and not isinstance(wert, bool) and math.isfinite(wert)


def _spec_zahlen_pruefen(spec: ResultSpec) -> None:
    """``min``, ``max``, ``step`` sind Zahlen; ``default`` und ``quick`` Zahlen, Texte oder
    Satzlisten — ``"seconds": "abc"`` stürzte sonst erst in der Eingabemaske ab (K8)."""
    for f in spec.fields:
        for name in ("min", "max", "step"):
            wert = getattr(f, name)
            if wert is not None and not _zahl(wert):
                raise ValueError(f"Parameter „{f.key}“: „{name}“ ist keine Zahl")
        for wert in [f.default, *f.quick]:
            if wert is None or isinstance(wert, str | bool) or _zahl(wert):
                continue
            if isinstance(wert, list) and all(_zahl(x) for x in wert):
                continue
            raise ValueError(f"Parameter „{f.key}“: Vorgabe oder Chip „{wert}“ ist keine Zahl")


def _werte_pruefen(obj: Any, feld: str) -> None:
    """Nur JSON-einfache Werte: Zahlen (endlich), Texte, Wahrheitswerte, Listen, Objekte."""
    if obj is None or isinstance(obj, str | bool) or _zahl(obj):
        return
    if isinstance(obj, list):
        for x in obj:
            _werte_pruefen(x, feld)
        return
    if isinstance(obj, dict):
        for x in obj.values():
            _werte_pruefen(x, feld)
        return
    raise ValueError(f"„{feld}“ enthält einen ungültigen Wert: {obj!r}")


def _objekt(wert: Any, feld: str) -> dict[str, Any]:
    if not isinstance(wert, dict):
        raise ValueError(f"„{feld}“ ist kein Objekt")
    return dict(wert)


def _liste(wert: Any, feld: str) -> list[Any]:
    if not isinstance(wert, list):
        raise ValueError(f"„{feld}“ ist keine Liste")
    return wert


def _texte(wert: Any, feld: str) -> list[str]:
    """Eine Liste von Namen — Leerzeichen bereinigt, Leeres raus."""
    return [" ".join(str(t).split()) for t in _liste(wert, feld) if str(t).strip()]


def _medium(roh: Any) -> Media | None:
    """Ein Video-Link. Leere Platzhalter und Dateien vom Ursprungsgerät fallen weg."""
    if not isinstance(roh, dict):
        raise ValueError("ein Medium ist kein Objekt")
    uri = str(roh.get("uri") or "").strip()
    try:
        quelle = MediaSource(roh.get("source", "url"))
        art = MediaKind(roh.get("kind", "video"))
    except ValueError:
        raise ValueError(f"Medium „{uri}“: unbekannte Art oder Quelle") from None
    if art == MediaKind.AUDIO:
        raise ValueError(f"Medium „{uri}“: Ton gibt es nur an Kurskapiteln")
    if not uri or quelle == MediaSource.LOCAL:
        return None
    return Media(
        kind=art,
        source=quelle,
        uri=uri,
        title=str(roh.get("title") or ""),
        license=str(roh.get("license") or ""),
    )


# ---------------------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------------------


def stand(u: Exercise) -> dict[str, Any]:
    """Was ein Paket über eine Übung festlegt — ohne ID, Herkunft und Zustand.

    Der Export schreibt genau das; gleicher Stand heißt für den Import
    „unverändert“.

    >>> stand(Exercise(name="Baum", typen=["Qigong"]))["typen"]
    ['Qigong']
    """
    d: dict[str, Any] = {"name": u.name}
    if u.description:
        d["description"] = u.description
    if u.icon_key:
        d["icon_key"] = u.icon_key
    d["typen"] = list(u.typen)
    d["regionen"] = list(u.regionen)
    d["result_spec"] = u.result_spec.to_dict()
    if u.limit_spec:
        d["limit_spec"] = u.limit_spec
    if u.default_target:
        d["default_target"] = u.default_target
    if u.default_felder is not None:
        d["default_felder"] = list(u.default_felder)
    medien = [
        {
            "kind": str(m.kind),
            "source": str(m.source),
            "uri": m.uri,
            "title": m.title,
            **({"license": m.license} if m.license else {}),
        }
        for m in u.media
        if m.uri and m.source != MediaSource.LOCAL
    ]
    if medien:
        d["media"] = medien
    if u.family_id:
        d["variante_von"] = u.family_id
    return d


def aus_stand(uebung_id: str, paket: str, standard: dict[str, Any]) -> Exercise:
    """Die Übung so, wie das Paket sie festlegt — das Gegenstück zu `stand`.

    Für „Auf Paketstand setzen“ und „Wieder installieren“: Der Paketstand liegt je
    Übung in der Datenbank (Migration 015).

    >>> u = Exercise(name="Baum", description="Knie weich.", typen=["Qigong"])
    >>> zurueck = aus_stand(u.id, "p1", stand(u))
    >>> (zurueck.id == u.id, zurueck.description, zurueck.package_id)
    (True, 'Knie weich.', 'p1')
    """
    return _uebung_lesen({**standard, "id": uebung_id}, paket)[0]


#: Feld im Paketstand → wie es in der App heißt (Reihenfolge = Anzeige)
FELDNAMEN: dict[str, str] = {
    "name": "Name",
    "description": "Beschreibung",
    "icon_key": "Symbol",
    "typen": "Typen",
    "regionen": "Regionen",
    "result_spec": "Parameter",
    "default_target": "Ziel",
    "default_felder": "Planparameter",
    "limit_spec": "Limits",
    "media": "Videos",
    "variante_von": "Variante",
}


def stand_tag_nachziehen(
    standard: dict[str, Any], feld: str, alt: str, neu: str | None
) -> dict[str, Any] | None:
    """Ein umbenannter (``neu``) oder gelöschter (``None``) Tag im Paketstand.

    ``feld`` ist ``"typen"`` oder ``"regionen"``. Zurück kommt der neue Stand —
    oder ``None``, wenn der Tag dort nicht vorkam. Sonst zeigte jede Paketübung
    nach „Dehnung → Stretching“ dauerhaft „geändert: Typen“, und „Auf Paketstand
    setzen“ legte den alten Namen wieder an (K-F4, Ben 15.10.2026: mitziehen).

    >>> stand_tag_nachziehen({"typen": ["Dehnung", "HRV"]}, "typen", "Dehnung", "Stretching")
    {'typen': ['Stretching', 'HRV']}
    >>> stand_tag_nachziehen({"typen": ["HRV", "Dehnung"]}, "typen", "Dehnung", None)
    {'typen': ['HRV']}
    >>> stand_tag_nachziehen({"typen": ["HRV"]}, "typen", "Dehnung", None) is None
    True
    """
    namen = standard.get(feld)
    if not isinstance(namen, list) or alt not in namen:
        return None
    danach: list[str] = []
    for name in namen:
        ersatz = neu if name == alt else name
        if ersatz is not None and ersatz not in danach:
            danach.append(ersatz)
    return {**standard, feld: danach}


def abweichungen(u: Exercise, standard: dict[str, Any]) -> list[str]:
    """Was an der Übung anders ist als im Paket — in Worten, leer = wie im Paket.

    >>> u = Exercise(name="Baum", description="Knie weich.")
    >>> standard = stand(u)
    >>> u.description = "Meine Fassung"
    >>> abweichungen(u, standard)
    ['Beschreibung']
    """
    jetzt = stand(u)
    return [text for feld, text in FELDNAMEN.items() if jetzt.get(feld) != standard.get(feld)]


def kurs_stand(k: Kurs) -> dict[str, Any]:
    """Was ein Paket über einen Kurs festlegt — ohne ID, Herkunft und Zustand.

    Kapitel tragen ihre ID: Daran hängt der Fortschritt, sie muss ein Update
    überleben.

    >>> k = Kurs(name="HRV", kapitel=[Kapitel(titel="Was ist das?")])
    >>> kurs_stand(k)["kapitel"][0]["titel"]
    'Was ist das?'
    """
    d: dict[str, Any] = {"name": k.name}
    if k.beschreibung:
        d["beschreibung"] = k.beschreibung
    d["freischaltung"] = k.freischaltung
    kapitel: list[dict[str, Any]] = []
    for kap in k.kapitel:
        e: dict[str, Any] = {"id": kap.id, "titel": kap.titel}
        if kap.text:
            e["text"] = kap.text
        if medien := medien_to_list(kap.media):
            e["media"] = medien
        if kap.plaene:
            e["plaene"] = [p.to_dict() for p in kap.plaene]
        e["bedingung"] = kap.bedingung.to_dict()
        kapitel.append(e)
    d["kapitel"] = kapitel
    return d


def kurs_aus_stand(kurs_id: str, paket: str, standard: dict[str, Any]) -> Kurs:
    """Der Kurs so, wie das Paket ihn festlegt — Gegenstück zu `kurs_stand`.

    >>> k = Kurs(name="HRV", kapitel=[Kapitel(titel="A")])
    >>> zurueck = kurs_aus_stand(k.id, "p1", kurs_stand(k))
    >>> (zurueck.id == k.id, zurueck.kapitel[0].id == k.kapitel[0].id, zurueck.package_id)
    (True, True, 'p1')
    """
    return _kurs_lesen({**standard, "id": kurs_id}, paket, {})


def paket_bauen(
    paket: Paket,
    uebungen: list[Exercise],
    exportiert: datetime | None = None,
    kurse: list[Kurs] | None = None,
) -> dict[str, Any]:
    """Die Paketdatei als Wörterbuch — `paket_json` macht Bytes daraus.

    Ohne Kurse bleibt die Datei Formatversion 1 — ältere Apps lesen sie weiter.

    >>> u = Exercise(name="Baum", typen=["Qigong"])
    >>> zurueck = paket_lesen(paket_bauen(Paket(id="p1", name="Qigong"), [u])).uebungen[0]
    >>> (zurueck.id == u.id, zurueck.name, zurueck.typen, zurueck.package_id)
    (True, 'Baum', ['Qigong'], 'p1')
    >>> k = Kurs(name="HRV", kapitel=[Kapitel(titel="A")])
    >>> roh = paket_bauen(Paket(id="p1", name="Qigong"), [u], kurse=[k])
    >>> roh["version"], paket_lesen(roh).kurse[0].name
    (2, 'HRV')
    """
    kopf: dict[str, Any] = {"id": paket.id, "name": paket.name}
    if paket.beschreibung:
        kopf["beschreibung"] = paket.beschreibung
    if paket.version is not None:
        kopf["version"] = paket.version
    roh: dict[str, Any] = {
        "format": FORMAT,
        "version": FORMAT_VERSION if kurse else 1,
        "paket": kopf,
        "exportiert": (exportiert or jetzt()).isoformat(timespec="seconds"),
        "exercises": [{"id": u.id, **stand(u)} for u in uebungen],
    }
    if kurse:
        roh["kurse"] = [{"id": k.id, **kurs_stand(k)} for k in kurse]
    return roh


def paket_json(paket: Paket, uebungen: list[Exercise], kurse: list[Kurs] | None = None) -> bytes:
    """Die Datei zum Weitergeben: lesbar eingerückt, Umlaute im Klartext."""
    roh = paket_bauen(paket, uebungen, kurse=kurse)
    return (json.dumps(roh, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


_UMLAUTE = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
)


def dateiname(paket: Paket) -> str:
    """Ein Dateiname, den jedes Ziel (Cloud, E-Mail, Dateimanager) verträgt.

    >>> dateiname(Paket(id="x", name="Qigong für Anfänger"))
    'uebungspaket_Qigong_fuer_Anfaenger.json'
    """
    teil = re.sub(r"[^A-Za-z0-9-]+", "_", paket.name.translate(_UMLAUTE)).strip("_")
    return f"uebungspaket_{teil or 'export'}.json"


__all__ = [
    "FELDNAMEN",
    "FORMAT",
    "FORMAT_VERSION",
    "GRUNDAUSSTATTUNG",
    "NAMENSRAUM",
    "Paket",
    "PaketFehler",
    "Paketinhalt",
    "abweichungen",
    "aus_stand",
    "dateiname",
    "kapitel_id",
    "kurs_aus_stand",
    "kurs_id",
    "kurs_stand",
    "name_pruefen",
    "paket_bauen",
    "paket_id",
    "paket_json",
    "paket_lesen",
    "stand",
    "stand_tag_nachziehen",
    "uebung_id",
]
