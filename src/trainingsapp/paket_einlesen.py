"""`trainingsapp-paket einlesen` — ein Export der App als TOML ins Inhalte-Repo (Stufe 2,
`docs/plan_rueckweg_handy.md`, Ben 17.11.2026).

Ben: „ich möchte also einen Kurs/Plan erstellen, teils kompliziert mit den Bedingungen und
einigen Medien und am Ende möchte ich mit veroeffentlichen.sh diese sauber auf den Server
laden.“ Am Handy entsteht ein **eigenes Paket** (U4, JSON oder mit Dateien ZIP); `einlesen`
macht daraus eine TOML, die sich lesen, weiterbearbeiten und mit `bauen` wieder zur selben
Paketdatei bauen lässt:

- **Neues Paket** (``--neu``, die Vorgabe, Ben: „Meistens wird es letzteres sein“): eigene
  Paket-ID (nicht die des Entwurfs — auf dem Handy stünden sonst Entwurf und Paket mit
  derselben ID), ``version = "1.0.0"``, wahlweise ``[privat]`` mit ``fuer``. Übungen, Pläne,
  Kurse und Kapitel bekommen einen ``key`` aus ihrem Namen; ihre IDs folgen daraus, nicht die
  des Geräts (E3: der Entwurf bleibt am Handy daneben, bis Ben ihn löscht).
- **Verweise** auf Übungen anderer Pakete werden ``uebung = "<key>", paket = "<Name>"`` (V1,
  `docs/plan_paketverweise.md`), wenn jenes Paket als TOML daneben liegt; sonst bleibt die ID.
- **Dateien** aus der ZIP liegen danach unter ``medien/<paket>/`` neben der TOML (Name =
  Prüfsumme) und stehen als ``datei = "…"`` darin — nie im git (Inhalte-Repo, Regel 6).
- **``einlesen/<paket>.json``** daneben (wird committet) hält fest, aus welchem eigenen Paket
  die Datei kam, welche ID vom Handy zu welchem Schlüssel gehört und den eingelesenen Stand
  der Übungen — die Basis der nächsten Runde: Ein späterer Export desselben Entwurfs findet
  so sein Ziel und gleicht seine Übungen in drei Wegen ab (`uebernehmen`); Pläne und Kurse
  einer zweiten Runde werden genannt, nicht geschrieben.
- **Ins bestehende Paket** (``--in``, Zweck A: ein Export des installierten Pakets): wie
  `uebernehmen`.
"""

from __future__ import annotations

import json
import tempfile
import tomllib
import uuid
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trainingsapp.core.models import MediaSource
from trainingsapp.core.paketdatei import (
    PAKET_JSON,
    medienlisten,
    nachbar_tomls,
    paket_oeffnen,
    paketwurzel,
)
from trainingsapp.core.pakete import (
    MARKENFELDER,
    PaketFehler,
    Paketinhalt,
    paket_id,
    plan_schluessel,
    stand,
    uebung_id,
)
from trainingsapp.core.paketmedien import Paketmedium
from trainingsapp.core.paketversion import version_text

#: Die erste Fassung eines neuen Pakets aus dem Handy (Paketversionen „X.Y.Z“, Ben 17.11.2026)
ERSTE_VERSION = "1.0.0"
#: Der Ordner der Merkdateien neben den TOML — ein Unterordner, damit weder der Start der App
#: (`data.seed.pakete_aus_ordner`) noch `veroeffentlichen.sh` sie für ein Paket hält
MERK_ORDNER = "einlesen"


def merkdatei(toml: Path) -> Path:
    """``pakete/fuer_a.toml`` → ``pakete/einlesen/fuer_a.json``."""
    return toml.parent / MERK_ORDNER / f"{toml.stem}.json"


def _roh_lesen(quelle: Path) -> dict[str, Any]:
    """Das JSON der Paketdatei, wie die App es schrieb (aus der ZIP ``paket.json``)."""
    if zipfile.is_zipfile(quelle):
        with zipfile.ZipFile(quelle) as z:
            roh = json.loads(z.read(PAKET_JSON))
    else:
        roh = json.loads(quelle.read_bytes())
    if not isinstance(roh, dict):
        raise PaketFehler(f"{quelle.name}: keine Paketdatei")
    return roh


def _kopf(roh: Mapping[str, Any]) -> dict[str, Any]:
    kopf = roh.get("paket")
    return kopf if isinstance(kopf, dict) else {}


def nachbar_schluessel(ziel: Path) -> dict[str, tuple[str, str]]:
    """Übungs-ID → ``(Paketname, Schlüssel)`` der TOML-Pakete neben ``ziel`` — so wird aus der
    ID einer Standard-Übung im Export wieder ``uebung = "kniebeuge", paket = "Standard"``.
    Die ID rechnet wie der Leser: eine eigene ``id`` vor dem Schlüssel. Neben heißt
    `nachbar_tomls`: unter ``pakete/`` auch in anderen Unterordnern."""
    out: dict[str, tuple[str, str]] = {}
    for datei in nachbar_tomls(ziel):
        if datei.resolve() == ziel.resolve():
            continue
        try:
            roh = tomllib.loads(datei.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
        kopf = _kopf(roh)
        name = " ".join(str(kopf.get("name") or datei.stem).split())
        pid = str(kopf.get("id") or "").strip().lower() or paket_id(name)
        for e in roh.get("exercises") or []:
            if isinstance(e, dict) and e.get("key"):
                key = str(e["key"]).strip()
                uid = str(e.get("id") or "").strip().lower() or uebung_id(pid, key)
                out[uid] = (name, key)
    return out


def _eindeutig(basis: str, vergeben: set[str]) -> str:
    key, n = basis, 2
    while key in vergeben:
        key, n = f"{basis}-{n}", n + 1
    vergeben.add(key)
    return key


def _uebungs_key(name: str, vergeben: set[str]) -> str:
    from trainingsapp.paket_werkzeug import neuer_key  # ohne Kreis beim Laden

    key = neuer_key(name, vergeben)
    vergeben.add(key)
    return key


class _Uebersetzung:
    """IDs vom Handy → Schlüssel der TOML."""

    def __init__(self, nachbarn: Mapping[str, tuple[str, str]]) -> None:
        self.uebungen: dict[str, str] = {}
        self.plaene: dict[str, str] = {}
        self.kurse: dict[str, str] = {}
        self.nachbarn = nachbarn
        self.unbekannt: set[str] = set()

    def verweis(self, uid: str) -> tuple[str, str]:
        """``(uebung, paket)`` für einen Verweis — ``paket`` leer für Übungen dieses Pakets
        und für IDs, die kein Paket daneben kennt (die bleiben, wie sie sind)."""
        if uid in self.uebungen:
            return self.uebungen[uid], ""
        if uid in self.nachbarn:
            name, key = self.nachbarn[uid]
            return key, name
        if uid and not uid.startswith("$"):
            self.unbekannt.add(uid)
        return uid, ""

    def umschreiben(self, x: Any) -> Any:
        """Jeden Übungsverweis (``uebung``, Marken) und jede ``grundlage`` übersetzen."""
        if isinstance(x, list):
            return [self.umschreiben(e) for e in x]
        if not isinstance(x, dict):
            return x
        neu = {k: self.umschreiben(v) for k, v in x.items()}
        uid = neu.get("uebung")
        if isinstance(uid, str) and uid.strip() and not neu.get("paket"):
            key, paket = self.verweis(uid.strip())
            neu["uebung"] = key
            if paket:
                neu["paket"] = paket
        for feld in MARKENFELDER:
            marke = neu.get(feld)
            if isinstance(marke, str) and ":" in marke:
                block, _, rest = marke.partition(":")
                if rest in self.uebungen or rest in self.nachbarn:
                    key, paket = self.verweis(rest)
                    neu[feld] = f"{block}:{paket}/{key}" if paket else f"{block}:{key}"
        grundlage = neu.get("grundlage")
        if isinstance(grundlage, str) and grundlage in self.plaene:
            neu["grundlage"] = self.plaene[grundlage]
        return neu


def _medien_ablegen(
    roh: dict[str, Any],
    medien: Mapping[str, Paketmedium],
    ordner: Path,
    wurzel: Path,
    schreiben: bool,
) -> tuple[int, list[str]]:
    """Jede Paketdatei (``source = "paket"``) aus der ZIP nach ``ordner`` legen und den Eintrag
    ``datei = "<Pfad>"`` nennen lassen — ``(Zahl der Dateien, was fehlte)``."""
    abgelegt: set[str] = set()
    fehlen: list[str] = []
    for liste in medienlisten(roh):
        for eintrag in liste:
            if not isinstance(eintrag, dict) or eintrag.get("source") != MediaSource.PAKET:
                continue
            name = str(eintrag.get("uri") or "")
            if name not in medien:
                fehlen.append(str(eintrag.get("title") or name))
                continue
            ziel = ordner / name.removeprefix("medien/")
            if schreiben and not ziel.is_file():
                ordner.mkdir(parents=True, exist_ok=True)
                medien[name].kopieren(ziel)
            for k in ("kind", "source", "uri"):
                eintrag.pop(k, None)
            eintrag["datei"] = ziel.relative_to(wurzel).as_posix()
            abgelegt.add(name)
    return len(abgelegt), fehlen


def _ohne_none(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _ohne_none(v) for k, v in x.items() if v is not None}
    if isinstance(x, list):
        return [_ohne_none(v) for v in x if v is not None]
    return x


def _toml_block(d: Mapping[str, Any]) -> Any:
    """Ein Wörterbuch als TOML-Tabelle — Werte zuerst, dann Untertabellen und ``[[…]]``
    (sonst landete ein Wert nach einer Untertabelle in ihr). Listen von Wörterbüchern
    werden ``[[…]]``-Blöcke, wenn ein Eintrag selbst Tabellen enthält, sonst Inline-Tabellen."""
    from trainingsapp.paket_werkzeug import _toml_wert, _tomlkit

    tomlkit = _tomlkit()
    t = tomlkit.table()
    spaeter: list[tuple[str, Any]] = []
    for k, v in d.items():
        if (isinstance(v, dict) and any(isinstance(w, dict | list) for w in v.values())) or (
            isinstance(v, list) and v and all(isinstance(e, dict) for e in v)
        ):
            spaeter.append((k, v))
        else:
            t[k] = _toml_wert(v)
    for k, v in spaeter:
        if isinstance(v, dict):
            t[k] = _toml_block(v)
        else:
            aot = tomlkit.aot()
            for e in v:
                aot.append(_toml_block(e))
            t[k] = aot
    return t


def _toml_text(roh: dict[str, Any], kopfzeilen: list[str]) -> str:
    from trainingsapp.paket_werkzeug import _TABELLE_OHNE_LEERZEILE, _tomlkit

    tomlkit = _tomlkit()
    dok = tomlkit.document()
    for zeile in kopfzeilen:
        dok.add(tomlkit.comment(zeile))
    dok.add(tomlkit.nl())
    dok["paket"] = _toml_block(roh["paket"])
    if "privat" in roh:
        dok["privat"] = _toml_block(roh["privat"])
    for liste in ("exercises", "ergaenzungen", "plaene", "kurse"):
        if roh.get(liste):
            aot = tomlkit.aot()
            for e in roh[liste]:
                aot.append(_toml_block(e))
            dok[liste] = aot
    return _TABELLE_OHNE_LEERZEILE.sub(r"\1\n\n\2", tomlkit.dumps(dok))


def neu_einlesen(
    quelle: Path,
    ziel: Path,
    *,
    name: str = "",
    privat: bool = False,
    fuer: str = "",
    schreiben: bool = True,
    jetzt: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[list[str], list[str]]:
    """Ein eigenes Paket aus der App als **neue** TOML ``ziel`` — ``(Zeilen, Fehler)``."""
    from trainingsapp.paket_werkzeug import pruefen

    if ziel.exists():
        return [], [f"{ziel.name} gibt es schon — eine weitere Runde gleicht `--in` ab"]
    with tempfile.TemporaryDirectory() as arbeit:
        try:
            inhalt: Paketinhalt = paket_oeffnen(quelle, quelle.stem, arbeit=Path(arbeit))
            roh = _roh_lesen(quelle)
        except (PaketFehler, OSError, ValueError, KeyError, zipfile.BadZipFile) as grund:
            return [], [f"{quelle.name}: {grund}"]
        zeilen, roh_neu, merk = _umwandeln(roh, inhalt, ziel, name=name, privat=privat, fuer=fuer)
        anzahl, fehlen = _medien_ablegen(
            roh_neu, inhalt.medien, ziel.parent / "medien" / ziel.stem, ziel.parent, schreiben
        )
        if anzahl:
            zeilen.append(f"{anzahl} Datei(en) nach medien/{ziel.stem}/ — nie committen")
        if fehlen:
            zeilen.append("Dateien fehlen in der Quelle, fallen weg: " + ", ".join(fehlen))
        kopf = [
            f" {roh_neu['paket']['name']} — eingelesen am {jetzt():%d.%m.%Y} aus {quelle.name}",
            f" (eigenes Paket „{inhalt.paket.name}“, "
            f"Version {version_text(inhalt.paket.version) or '—'}) — trainingsapp-paket einlesen.",
            " Schlüssel (key) nie ändern — die IDs folgen daraus. Mediendateien liegen unter",
            f" medien/{ziel.stem}/ und kommen nie ins git.",
        ]
        text = _toml_text(roh_neu, kopf)
        if not schreiben:
            return zeilen, []
        ziel.write_text(text, encoding="utf-8")
        merk["eingelesen"] = jetzt().isoformat(timespec="seconds")
        _merk_schreiben(ziel, merk)
    zeilen.append(
        f"{ziel}: geschrieben, dazu {MERK_ORDNER}/{merkdatei(ziel).name} (beides committen)"
    )
    fehler, hinweise = pruefen(ziel)
    zeilen += [f"Hinweis: {h}" for h in hinweise]
    return zeilen, [f"{ziel.name}: {f}" for f in fehler]


def _umwandeln(
    roh: dict[str, Any],
    inhalt: Paketinhalt,
    ziel: Path,
    *,
    name: str,
    privat: bool,
    fuer: str,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    """Das JSON der App in die Form der TOML: Schlüssel statt IDs, eigener Kopf.
    ``(Zeilen, neues roh, Merkdatei)``."""
    u = _Uebersetzung(nachbar_schluessel(ziel))
    zeilen: list[str] = []
    keys: set[str] = set()
    uebungen: list[dict[str, Any]] = []
    for e in roh.get("exercises") or []:
        if not isinstance(e, dict):
            continue
        alt = str(e.get("id") or "")
        key = _uebungs_key(str(e.get("name") or ""), keys)
        if alt:
            u.uebungen[alt] = key
        uebungen.append({"key": key, **{k: v for k, v in e.items() if k not in ("id", "key")}})
    plan_keys: set[str] = set()
    for p in roh.get("plaene") or []:
        if isinstance(p, dict):
            alt = str(p.get("key") or "")
            u.plaene[alt] = _eindeutig(
                plan_schluessel(str(p.get("name") or "plan").casefold()), plan_keys
            )
    kurs_keys: set[str] = set()
    for k in roh.get("kurse") or []:
        if isinstance(k, dict):
            alt = str(k.get("id") or "")
            u.kurse[alt] = _eindeutig(
                plan_schluessel(str(k.get("name") or "kurs").casefold()), kurs_keys
            )
    plaene = []
    for p in roh.get("plaene") or []:
        if isinstance(p, dict):
            neu = u.umschreiben(p)
            neu["key"] = u.plaene[str(p.get("key") or "")]
            plaene.append(neu)
    kurse = []
    for k in roh.get("kurse") or []:
        if not isinstance(k, dict):
            continue
        neu = u.umschreiben({f: w for f, w in k.items() if f != "id"})
        neu = {
            "key": u.kurse[str(k.get("id") or "")],
            **{f: w for f, w in neu.items() if f != "key"},
        }
        kap_keys: set[str] = set()
        kapitel = []
        for kap in neu.get("kapitel") or []:
            if isinstance(kap, dict):
                kkey = _eindeutig(
                    plan_schluessel(str(kap.get("titel") or "kapitel").casefold()), kap_keys
                )
                kapitel.append(
                    {"key": kkey, **{f: w for f, w in kap.items() if f not in ("id", "key")}}
                )
        neu["kapitel"] = kapitel
        kurse.append(neu)
    ergaenzungen = [u.umschreiben(e) for e in roh.get("ergaenzungen") or [] if isinstance(e, dict)]
    uebungen = [u.umschreiben(e) for e in uebungen]  # „variante_von“ u. ä.
    kopf_alt = _kopf(roh)
    paketname = " ".join((name or str(kopf_alt.get("name") or ziel.stem)).split())
    kopf: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": paketname,
        "version": ERSTE_VERSION,
    }
    for feld in ("beschreibung", "neuigkeiten"):
        if str(kopf_alt.get(feld) or "").strip():
            kopf[feld] = str(kopf_alt[feld]).strip()
    roh_neu: dict[str, Any] = {"paket": kopf}
    if privat or fuer:
        roh_neu["privat"] = {"fuer": fuer} if fuer else {}
    roh_neu |= {
        "exercises": uebungen,
        "ergaenzungen": ergaenzungen,
        "plaene": plaene,
        "kurse": kurse,
    }
    roh_neu = _ohne_none(roh_neu)
    zeilen.append(
        f"„{paketname}“: {len(uebungen)} Übung(en), {len(plaene)} Plan/Pläne, "
        f"{len(kurse)} Kurs(e), {len(ergaenzungen)} Ergänzung(en)"
    )
    fremd = sorted({f"{n}: {k}" for n, k in (u.nachbarn[i] for i in _verwiesen(roh, u))})
    if fremd:
        zeilen.append("Verweise auf andere Pakete: " + ", ".join(fremd))
    if u.unbekannt:
        zeilen.append(
            f"{len(u.unbekannt)} Verweis(e) auf Übungen, die kein Paket daneben kennt — bleiben "
            "als ID (fehlt das Paket auf einem Gerät, fällt die Übung dort aus dem Plan)"
        )
    merk: dict[str, Any] = {
        "eigenes_paket": str(kopf_alt.get("id") or inhalt.paket.id),
        "version_handy": version_text(inhalt.paket.version),
        "paket": kopf["id"],
        "uebungen": u.uebungen,
        "plaene": u.plaene,
        "kurse": u.kurse,
        "stand": {u.uebungen[x.id]: stand(x) for x in inhalt.uebungen if x.id in u.uebungen},
    }
    return zeilen, roh_neu, merk


def _verwiesen(roh: Mapping[str, Any], u: _Uebersetzung) -> set[str]:
    """Die IDs aus Paketen daneben, auf die der Export zeigt."""
    gefunden: set[str] = set()

    def gehe(x: Any) -> None:
        if isinstance(x, list):
            for e in x:
                gehe(e)
        elif isinstance(x, dict):
            uid = x.get("uebung")
            if isinstance(uid, str) and uid in u.nachbarn:
                gefunden.add(uid)
            for v in x.values():
                gehe(v)

    gehe([roh.get("plaene"), roh.get("kurse"), roh.get("ergaenzungen")])
    return gefunden


def _merk_schreiben(ziel: Path, merk: Mapping[str, Any]) -> None:
    pfad = merkdatei(ziel)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(merk, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def eigenes_ziel(quelle: Path, ziel: Path) -> Path | None:
    """Die TOML, in die ein früherer Export desselben eigenen Pakets eingelesen wurde — gesucht
    in den Merkdateien unter ``pakete/`` (`paketwurzel`, auch die anderer Unterordner), ohne
    einen solchen Ordner nur in denen neben ``ziel``."""
    try:
        roh = _roh_lesen(quelle)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, PaketFehler):
        return None
    kopf = _kopf(roh)
    pid = str(kopf.get("id") or "")
    if not pid:
        return None
    wurzel = paketwurzel(ziel)
    merkdateien = (
        wurzel.rglob(f"{MERK_ORDNER}/*.json")
        if wurzel is not None
        else (ziel.parent / MERK_ORDNER).glob("*.json")
    )
    for merk in sorted(merkdateien):
        try:
            if json.loads(merk.read_text("utf-8")).get("eigenes_paket") == pid:
                return merk.parent.parent / f"{merk.stem}.toml"
        except (OSError, ValueError, AttributeError):
            continue
    return None


def einlesen(
    quelle: Path,
    ziel: Path,
    *,
    name: str = "",
    privat: bool = False,
    fuer: str = "",
    schreiben: bool = True,
) -> tuple[list[str], list[str]]:
    """Ein Export der App nach ``ziel`` — ``(Zeilen, Fehler)``: neu (``ziel`` gibt es noch
    nicht), die nächste Runde desselben Entwurfs (die Merkdatei kennt ihn) oder — für einen
    Export des installierten Pakets — wie `uebernehmen`."""
    from trainingsapp.paket_werkzeug import uebernehmen

    bisher = eigenes_ziel(quelle, ziel)
    if not ziel.exists():
        if bisher is not None:
            # unter ``pakete/`` absolut gefunden — gezeigt wie eingegeben, relativ zum Ordner
            zeigen = bisher.relative_to(Path.cwd()) if bisher.is_relative_to(Path.cwd()) else bisher
            return [], [
                f"Dieser Entwurf wurde schon nach {bisher.name} eingelesen — "
                f"`einlesen {quelle.name} {zeigen}` gleicht ab"
            ]
        return neu_einlesen(quelle, ziel, name=name, privat=privat, fuer=fuer, schreiben=schreiben)
    if bisher is not None and bisher.resolve() == ziel.resolve():
        return weitere_runde(quelle, ziel, schreiben=schreiben)
    return uebernehmen(quelle, ziel, schreiben)


def weitere_runde(
    quelle: Path, ziel: Path, *, schreiben: bool = True
) -> tuple[list[str], list[str]]:
    """Ein späterer Export desselben eigenen Pakets: Die Übungen bekommen die IDs aus den
    Schlüsseln der ersten Runde, Basis ist der Stand, der damals eingelesen wurde — dann
    gleicht `uebernehmen` in drei Wegen ab (die TOML gewinnt). Neue Übungen bekommen einen
    Schlüssel; Pläne und Kurse einer weiteren Runde werden genannt, nicht geschrieben."""
    from trainingsapp.paket_werkzeug import Quelle, neuer_key, uebernehmen

    merk = json.loads(merkdatei(ziel).read_text("utf-8"))
    pid = str(merk.get("paket") or "")
    zuordnung: dict[str, str] = dict(merk.get("uebungen") or {})
    try:
        roh_ziel = tomllib.loads(ziel.read_text(encoding="utf-8"))
    except (OSError, ValueError) as grund:
        return [], [f"{ziel.name}: {grund}"]
    keys = {
        str(e.get("key"))
        for e in roh_ziel.get("exercises") or []
        if isinstance(e, dict) and e.get("key")
    }
    with tempfile.TemporaryDirectory() as arbeit:
        try:
            inhalt = paket_oeffnen(quelle, quelle.stem, arbeit=Path(arbeit))
        except (PaketFehler, OSError) as grund:
            return [], [f"{quelle.name}: {grund}"]
        uebungen = []
        for u in inhalt.uebungen:
            if u.id not in zuordnung:
                zuordnung[u.id] = neuer_key(u.name, keys)
                keys.add(zuordnung[u.id])
            uebungen.append(replace(u, id=uebung_id(pid, zuordnung[u.id]), package_id=pid))
        basis = {uebung_id(pid, k): s for k, s in (merk.get("stand") or {}).items()}
        q = Quelle(
            paket=replace(inhalt.paket, id=pid),
            uebungen=uebungen,
            basis=basis,
            medien=inhalt.medien,
        )
        zeilen, fehler = uebernehmen(q, ziel, schreiben)
    if inhalt.plaene or inhalt.kurse:
        zeilen.append(
            f"Pläne ({len(inhalt.plaene)}) und Kurse ({len(inhalt.kurse)}) vom Handy werden in "
            "einer weiteren Runde nicht abgeglichen — Änderungen an ihnen bitte in der TOML"
        )
    if schreiben and not fehler:
        merk["uebungen"] = zuordnung
        merk["stand"] = {zuordnung[u.id]: stand(u) for u in inhalt.uebungen}
        merk["version_handy"] = version_text(inhalt.paket.version)
        merk["eingelesen"] = datetime.now(UTC).isoformat(timespec="seconds")
        _merk_schreiben(ziel, merk)
    return zeilen, fehler
