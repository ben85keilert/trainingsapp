"""Paketdateien öffnen und schreiben: JSON, TOML und ZIP mit Medien (U3, Ben 9.11.2026, F3:
„toml, json, ZIP unterstützen“; `docs/plan_paketinhalte.md` §7).

- **JSON** — das Austauschformat seit jeher (`core.pakete.paket_lesen`), ohne Dateien.
- **TOML** — so, wie Pakete von Hand entstehen (Inhalte-Repo); in der App ohne Dateien (die
  liegen neben der TOML, die App sieht nur die eine Datei — eine ZIP baut
  `trainingsapp-paket bauen`).
- **ZIP** (Formatversion 4) — ``paket.json`` und ``medien/<sha256>.<endung>``. Gelesen wird
  nur ``paket.json`` ganz; jede Datei bleibt in der ZIP, bis der Import sie mit Prüfsumme in
  die Ablage kopiert (`Paketmedium.kopieren`). Grenzen: Datei bis `MAX_ZIP_BYTES`, ausgepackt
  bis `MAX_ENTPACKT_BYTES`, höchstens `MAX_EINTRAEGE` Einträge, keine verschlüsselten.
  Ältere Apps lesen eine ZIP nicht („kein JSON“) — darum wird nur mit Dateien eine ZIP daraus.

`paket_zip` schreibt die ZIP reproduzierbar: feste Zeitstempel, ``paket.json`` zuerst, die
Dateien nach Namen — dieselben Inhalte ergeben dieselbe Prüfsumme (wie K28 für JSON).

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

import hashlib
import io
import secrets
import shutil
import tempfile
import tomllib
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import IO, Any, Final

from .bereinigen import NichtBereinigbar, datei_bereinigen
from .ergaenzungen import Ergaenzung
from .kurse import Kurs
from .models import Exercise, Media, MediaSource
from .pakete import (
    MAX_PAKET_BYTES,
    Paket,
    PaketFehler,
    Paketinhalt,
    PaketPlan,
    dateiname,
    paket_json,
    paket_lesen,
    paketmedien_in,
)
from .paketmedien import (
    MAX_EINTRAEGE,
    MAX_ENTPACKT_BYTES,
    MAX_ZIP_BYTES,
    Paketmedium,
    art_fuer,
    name_fuer,
    name_lesen,
)
from .privat import (
    CodeFalsch,
    PrivatNichtMoeglich,
    datei_entschluesseln,
    entschluesseln,
    ist_privat,
)

#: Der Paketinhalt in der ZIP
PAKET_JSON: Final = "paket.json"
#: So beginnt jede ZIP-Datei
ZIP_KOPF: Final = b"PK\x03\x04"
#: Fester Zeitstempel der Einträge (reproduzierbar)
_ZEIT: Final = (1980, 1, 1, 0, 0, 0)


class CodeNoetig(PaketFehler):
    """Ein privates Paket (U7) — ohne seinen Code nicht zu lesen."""

    def __init__(self) -> None:
        super().__init__("Ein privates Paket — es braucht seinen Code.")


#: So heißen Arbeitsdateien des Imports: der Klartext eines privaten Pakets
#: (`_entschluesselt`) und ein aus dem Netz geladenes großes Paket (`paketquelle`)
KLARTEXT: Final = "klartext_"
GELADEN: Final = "geladen_"


def klartext_aufraeumen(arbeit: Path) -> int:
    """Löscht liegengebliebene Arbeitsdateien des Imports aus ``arbeit`` — den Klartext
    privater Pakete (U7) und geladene große Pakete. Beim Start, falls die App mitten im Import
    endete; im Betrieb räumt jeder Import seine eigenen (`Paketinhalt.raeumen`). Wie viele.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as t:
    ...     _ = (Path(t) / "klartext_ab12.zip").write_bytes(b"x")
    ...     _ = (Path(t) / "anderes.txt").write_bytes(b"x")
    ...     klartext_aufraeumen(Path(t)), sorted(p.name for p in Path(t).iterdir())
    (1, ['anderes.txt'])
    """
    weg = 0
    try:
        dateien = [
            d for d in arbeit.iterdir() if d.name.startswith((KLARTEXT, GELADEN)) and d.is_file()
        ]
    except OSError:
        return 0
    for datei in dateien:
        try:
            datei.unlink()
            weg += 1
        except OSError:
            continue
    return weg


class _Strom(io.RawIOBase):
    """Ein Eintrag der ZIP als Strom — schließt beim Schließen auch die ZIP."""

    def __init__(self, zf: zipfile.ZipFile, name: str) -> None:
        super().__init__()
        self._zf = zf
        self._f = zf.open(name)

    def readable(self) -> bool:
        return True

    def readinto(self, puffer: Any) -> int:
        daten = self._f.read(len(puffer))
        puffer[: len(daten)] = daten
        return len(daten)

    def close(self) -> None:
        try:
            self._f.close()
        finally:
            self._zf.close()
            super().close()


def _toml(daten: bytes, name_vorgabe: str) -> Paketinhalt:
    try:
        roh = tomllib.loads(daten.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as fehler:
        raise PaketFehler(f"Das ist keine Paketdatei (TOML unlesbar: {fehler}).") from None
    return paket_lesen(roh, name_vorgabe=name_vorgabe)


#: Der Ende-Satz einer ZIP: Kennung, dann u. a. Zahl der Einträge (+10) und Größe des
#: Inhaltsverzeichnisses (+12); höchstens 22 Bytes + 65535 Bytes Kommentar vor dem Dateiende
_ZIP_ENDE: Final = b"PK\x05\x06"
_ZIP_ENDE_BEREICH: Final = 22 + 0xFFFF
#: So groß darf das Inhaltsverzeichnis sein: `MAX_EINTRAEGE` Einträge mit langen Namen. Ein
#: Eintrag braucht dort mindestens 46 Bytes — mehr als gut 40 000 liest `zipfile` so nie
_MAX_VERZEICHNIS_BYTES: Final = MAX_EINTRAEGE * 1024


def _zip_vorpruefen(quelle: bytes | Path, groesse: int) -> None:
    """Zahl der Einträge und Größe des Inhaltsverzeichnisses aus dem Ende-Satz lesen und
    ablehnen, **bevor** `zipfile` das ganze Verzeichnis in den Speicher holt (S26: 400 000
    leere Einträge kosteten 170 MB). `zipfile` liest nach der Größe, nicht nach der Zahl —
    darum zählt beides. Ohne Ende-Satz sagt `zipfile` danach selbst „unlesbar“."""
    if isinstance(quelle, Path):
        with quelle.open("rb") as f:
            f.seek(max(0, groesse - _ZIP_ENDE_BEREICH))
            schluss = f.read(_ZIP_ENDE_BEREICH)
    else:
        schluss = quelle[-_ZIP_ENDE_BEREICH:]
    i = schluss.rfind(_ZIP_ENDE)
    if i < 0 or i + 22 > len(schluss):
        return
    eintraege = int.from_bytes(schluss[i + 10 : i + 12], "little")
    verzeichnis = int.from_bytes(schluss[i + 12 : i + 16], "little")
    if eintraege > MAX_EINTRAEGE or verzeichnis > _MAX_VERZEICHNIS_BYTES:
        raise PaketFehler("Das Paket hat zu viele Dateien.")


def _zip(quelle: bytes | Path, groesse: int, name_vorgabe: str) -> Paketinhalt:
    if groesse > MAX_ZIP_BYTES:
        raise PaketFehler(
            f"Die Datei ist zu groß für ein Übungspaket ({groesse / 1e6:.0f} MB, höchstens "
            f"{MAX_ZIP_BYTES / 1e6:.0f} MB)."
        )

    def oeffner() -> zipfile.ZipFile:
        return zipfile.ZipFile(quelle if isinstance(quelle, Path) else io.BytesIO(quelle))

    try:
        _zip_vorpruefen(quelle, groesse)
        with oeffner() as zf:
            eintraege = zf.infolist()
            if len(eintraege) > MAX_EINTRAEGE:
                raise PaketFehler("Das Paket hat zu viele Dateien.")
            if sum(e.file_size for e in eintraege) > MAX_ENTPACKT_BYTES:
                raise PaketFehler("Das Paket ist ausgepackt zu groß.")
            namen = [e.filename for e in eintraege]
            if len(set(namen)) != len(namen):
                raise PaketFehler("Das ist keine Paketdatei (Einträge doppelt).")
            if any(e.flag_bits & 0x1 for e in eintraege):
                raise PaketFehler("Das Paket ist verschlüsselt — so liest diese App es nicht.")
            kopf = next((e for e in eintraege if e.filename == PAKET_JSON), None)
            if kopf is None:
                raise PaketFehler("Das ist keine Paketdatei (paket.json fehlt in der ZIP).")
            if kopf.file_size > MAX_PAKET_BYTES:
                raise PaketFehler("Die Paketbeschreibung in der ZIP ist zu groß.")
            json_daten = zf.read(PAKET_JSON)
            dateien = {
                e.filename: e.file_size
                for e in eintraege
                if name_lesen(e.filename) is not None and not e.is_dir()
            }
    except zipfile.BadZipFile:
        raise PaketFehler("Das ist keine Paketdatei (ZIP unlesbar).") from None
    inhalt = paket_lesen(json_daten, name_vorgabe=name_vorgabe)

    def strom(name: str) -> Callable[[], IO[bytes]]:
        def oeffnen() -> IO[bytes]:
            return io.BufferedReader(_Strom(oeffner(), name))

        return oeffnen

    inhalt.medien = {
        name: Paketmedium(name, groesse_, strom(name)) for name, groesse_ in dateien.items()
    }
    return inhalt


def _entschluesselt(
    quelle: bytes | Path, code: str | None, arbeit: Path | None, name_vorgabe: str, endung: str
) -> Paketinhalt:
    """Ein privates Paket (U7) entschlüsseln und lesen — ohne Code `CodeNoetig`, mit falschem
    `PaketFehler`. Große Dateien gehen über ``arbeit`` (der Klartext liegt dort, bis der Import
    fertig ist — dann räumt der Aufrufer mit `Paketinhalt.raeumen`), sonst im Speicher."""
    if code is None:
        raise CodeNoetig()
    try:
        if isinstance(quelle, Path) and arbeit is not None:
            arbeit.mkdir(parents=True, exist_ok=True)
            ziel = arbeit / f"{KLARTEXT}{secrets.token_hex(6)}{endung or '.paket'}"
            datei_entschluesseln(quelle, ziel, code)
            try:
                inhalt = paket_oeffnen(ziel, name_vorgabe, endung=endung)
            except BaseException:
                ziel.unlink(missing_ok=True)  # kein Paket darin — der Klartext bleibt nicht
                raise
            inhalt.arbeitsdateien.append(ziel)
        else:
            daten = quelle.read_bytes() if isinstance(quelle, Path) else quelle
            inhalt = paket_oeffnen(entschluesseln(daten, code), name_vorgabe, endung=endung)
    except CodeFalsch:
        raise PaketFehler("Der Code passt nicht.") from None
    except PrivatNichtMoeglich as fehler:
        raise PaketFehler(str(fehler)) from None
    inhalt.code = code
    return inhalt


def paket_oeffnen(
    quelle: bytes | Path,
    name_vorgabe: str = "",
    *,
    endung: str = "",
    code: str | None = None,
    arbeit: Path | None = None,
) -> Paketinhalt:
    """Eine Paketdatei lesen — ZIP (am Kopf erkannt), TOML (Endung ``.toml``, sonst wenn kein
    JSON) oder JSON; ein privates Paket (U7) mit ``code`` (sonst `CodeNoetig`). Wirft
    `PaketFehler` mit einem Satz für Menschen.

    >>> paket_oeffnen(b'{"paket": {"name": "T"}, "exercises": [{"name": "A"}]}').paket.name
    'T'
    >>> paket_oeffnen(b'[paket]\\nname = "T2"\\n[[exercises]]\\nname = "B"\\n').paket.name
    'T2'
    """
    if isinstance(quelle, Path):
        try:
            groesse = quelle.stat().st_size
            with quelle.open("rb") as f:
                kopf = f.read(8)
        except OSError as fehler:
            raise PaketFehler(f"Die Datei ließ sich nicht lesen: {fehler}") from None
        name_vorgabe = name_vorgabe or quelle.stem
        endung = endung or quelle.suffix
        if ist_privat(kopf):
            if groesse > MAX_ZIP_BYTES + 1024:
                raise PaketFehler("Die Datei ist zu groß für ein Übungspaket.")
            return _entschluesselt(quelle, code, arbeit, name_vorgabe, endung)
        if kopf[:4] == ZIP_KOPF:
            return _zip(quelle, groesse, name_vorgabe)
        if groesse > MAX_PAKET_BYTES:
            raise PaketFehler(
                f"Die Datei ist zu groß für ein Übungspaket ({groesse / 1e6:.0f} MB)."
            )
        daten = quelle.read_bytes()
    else:
        daten = quelle
        if ist_privat(daten[:8]):
            return _entschluesselt(daten, code, None, name_vorgabe, endung)
        if daten[:4] == ZIP_KOPF:
            return _zip(daten, len(daten), name_vorgabe)
    if endung.lower().lstrip(".") == "toml":
        return _toml(daten, name_vorgabe)
    try:
        return paket_lesen(daten, name_vorgabe=name_vorgabe)
    except PaketFehler as json_fehler:
        if "kein JSON" not in str(json_fehler) or len(daten) > MAX_PAKET_BYTES:
            raise
        try:
            return _toml(daten, name_vorgabe)
        except PaketFehler:
            raise json_fehler from None


def medienlisten(roh: Mapping[str, Any]) -> Iterator[list[Any]]:
    """Alle Medienlisten der Rohdaten: Übungen (``media``), Planübungen (``medien``), Kapitel
    (``media``) und die Planübungen in Kapiteln."""

    def aus_plaenen(plaene: Any) -> Iterator[list[Any]]:
        for pl in plaene if isinstance(plaene, list) else []:
            for pe in (pl.get("uebungen") if isinstance(pl, dict) else None) or []:
                if isinstance(pe, dict) and isinstance(pe.get("medien"), list):
                    yield pe["medien"]

    for e in roh.get("exercises") or []:
        if isinstance(e, dict) and isinstance(e.get("media"), list):
            yield e["media"]
    yield from aus_plaenen(roh.get("plaene"))
    for e in roh.get("ergaenzungen") or []:  # U5
        if isinstance(e, dict) and isinstance(e.get("media"), list):
            yield e["media"]
    for k in roh.get("kurse") or []:
        for kap in (k.get("kapitel") if isinstance(k, dict) else None) or []:
            if not isinstance(kap, dict):
                continue
            if isinstance(kap.get("media"), list):
                yield kap["media"]
            yield from aus_plaenen(kap.get("plaene"))


def sha256_datei(pfad: Path) -> str:
    """Die Prüfsumme einer Datei, ohne sie ganz zu lesen."""
    h = hashlib.sha256()
    with pfad.open("rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def dateien_einbinden(roh: dict[str, Any], basis: Path, arbeit: Path) -> dict[str, Path]:
    """Medien mit ``datei = "<Pfad neben der TOML>"`` werden Paketdateien: bereinigt nach
    ``arbeit`` (`core/bereinigen.py`), benannt nach ihrer Prüfsumme; der Eintrag bekommt
    ``source = "paket"``, ``uri`` und ``kind`` nach der Endung. Liefert Name → bereinigte Datei.
    Wirft `PaketFehler`: Datei fehlt, liegt außerhalb des Paketordners, ist keine erlaubte Art
    oder lässt sich nicht von Ortsangaben befreien."""
    dateien: dict[str, Path] = {}
    wurzel = basis.resolve()
    for liste in medienlisten(roh):
        for eintrag in liste:
            if not isinstance(eintrag, dict) or "datei" not in eintrag:
                continue
            rel = str(eintrag.pop("datei"))
            quelle = (basis / rel).resolve()
            if wurzel not in quelle.parents:
                raise PaketFehler(f"Datei „{rel}“ liegt außerhalb des Paketordners.")
            endung = quelle.suffix.lower().lstrip(".")
            art = art_fuer(endung)
            if art is None:
                raise PaketFehler(f"Datei „{rel}“: „.{endung}“ geht nicht in ein Paket.")
            if not quelle.is_file():
                raise PaketFehler(f"Datei „{rel}“ fehlt.")
            if quelle.stat().st_size > MAX_ZIP_BYTES:
                raise PaketFehler(f"Datei „{rel}“ ist zu groß für ein Paket.")
            zwischen = arbeit / f"{len(dateien)}_{quelle.name}"
            try:
                datei_bereinigen(quelle, zwischen, endung)
            except NichtBereinigbar as fehler:
                raise PaketFehler(f"Datei „{rel}“: {fehler}") from None
            name = name_fuer(sha256_datei(zwischen), endung)
            ziel = arbeit / name.removeprefix("medien/")
            zwischen.replace(ziel)
            dateien[name] = ziel
            eintrag.update({"source": "paket", "uri": name, "kind": str(art)})
    return dateien


def toml_oeffnen(pfad: Path, arbeit: Path) -> Paketinhalt:
    """Eine TOML aus dem Inhalte-Repo **mit** ihren Dateien (``datei = "…"``, bereinigt nach
    ``arbeit``) — wie eine ZIP: ``medien`` zeigt auf die bereinigten Dateien. ``arbeit`` muss
    bestehen bleiben, bis der Import fertig ist."""
    try:
        roh = tomllib.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as fehler:
        raise PaketFehler(f"{pfad.name}: {fehler}") from None
    dateien = dateien_einbinden(roh, pfad.parent, arbeit)
    inhalt = paket_lesen(roh, name_vorgabe=pfad.stem)

    def oeffner(datei: Path) -> Callable[[], IO[bytes]]:
        return lambda: datei.open("rb")

    inhalt.medien = {
        name: Paketmedium(name, datei.stat().st_size, oeffner(datei))
        for name, datei in dateien.items()
    }
    return inhalt


def medien_fuer_export(
    namen: Iterable[str], quelle: Callable[[str], Path | None], arbeit: Path
) -> tuple[dict[str, Path], dict[str, str | None], list[str]]:
    """Die Paketdateien für eine Export-ZIP (U3, F4): jede noch einmal bereinigt (idempotent —
    eine saubere Datei behält ihren Namen). ``quelle``: wo die Datei auf dem Gerät liegt.

    Returns:
        ``(Name → Datei für die ZIP, alter Name → neuer Name bzw. None = bleibt draußen,
        Meldungen)`` — was fehlt oder sich nicht bereinigen lässt, kommt nicht ins Paket.
    """
    dateien: dict[str, Path] = {}
    umbenennung: dict[str, str | None] = {}
    meldungen: list[str] = []
    for name in sorted(set(namen)):
        teile = name_lesen(name)
        pfad = quelle(name)
        if teile is None or pfad is None or not pfad.is_file():
            umbenennung[name] = None
            meldungen.append("Eine Datei fehlt auf diesem Gerät — sie bleibt draußen.")
            continue
        zwischen = arbeit / f"{teile[0]}.{teile[1]}"
        try:
            datei_bereinigen(pfad, zwischen, teile[1])
        except NichtBereinigbar as fehler:
            umbenennung[name] = None
            meldungen.append(f"Eine Datei bleibt draußen: {fehler}.")
            continue
        neu = name_fuer(sha256_datei(zwischen), teile[1])
        dateien[neu] = zwischen
        umbenennung[name] = neu
    return dateien, umbenennung, meldungen


def medien_umbenennen(
    medien: Iterable[Media], umbenennung: Mapping[str, str | None]
) -> list[Media]:
    """Die Medienliste mit den Namen aus `medien_fuer_export` — Weggefallenes fehlt.

    >>> m = Media(source=MediaSource.PAKET, uri="medien/" + "a" * 64 + ".png")
    >>> [x.uri[-8:] for x in medien_umbenennen([m], {m.uri: "medien/" + "b" * 64 + ".png"})]
    ['bbbb.png']
    >>> medien_umbenennen([m], {m.uri: None})
    []
    """
    out: list[Media] = []
    for m in medien:
        if m.source == MediaSource.PAKET and m.uri in umbenennung:
            neu = umbenennung[m.uri]
            if neu is None:
                continue
            m = replace(m, uri=neu)
        out.append(m)
    return out


def export_schreiben(
    ordner: Path,
    paket: Paket,
    uebungen: list[Exercise],
    *,
    plaene: list[PaketPlan] | None = None,
    kurse: list[Kurs] | None = None,
    ergaenzungen: list[Ergaenzung] | None = None,
    quelle: Callable[[str], Path | None],
    mit_zeitstempel: bool = True,
) -> tuple[Path, list[str]]:
    """Die Paketdatei zum Weitergeben in ``ordner`` — eine ZIP mit den Paketdateien, jede noch
    einmal bereinigt (`medien_fuer_export`), oder JSON, wenn keine Datei dabei ist bzw. übrig
    blieb. ``quelle``: wo eine Paketdatei auf dem Gerät liegt. ``(Datei, Meldungen)``."""
    plaene = plaene or []
    kurse = kurse or []
    ergaenzungen = ergaenzungen or []
    ordner.mkdir(parents=True, exist_ok=True)
    namen = paketmedien_in(uebungen, kurse, plaene, ergaenzungen)
    if not namen:
        ziel = ordner / dateiname(paket)
        ziel.write_bytes(
            paket_json(
                paket,
                uebungen,
                kurse or None,
                plaene=plaene or None,
                ergaenzungen=ergaenzungen or None,
                mit_zeitstempel=mit_zeitstempel,
            )
        )
        return ziel, []
    with tempfile.TemporaryDirectory() as arbeit:
        dateien, umbenennung, meldungen = medien_fuer_export(namen, quelle, Path(arbeit))

        def plan_neu(pp: PaketPlan) -> PaketPlan:
            return replace(
                pp,
                vorlage=replace(
                    pp.vorlage,
                    items=[
                        replace(i, medien=medien_umbenennen(i.medien, umbenennung))
                        for i in pp.vorlage.items
                    ],
                ),
            )

        kurse_neu = [
            replace(
                k,
                kapitel=[
                    replace(
                        kap,
                        media=medien_umbenennen(kap.media, umbenennung),
                        plaene=[plan_neu(PaketPlan("k", v)).vorlage for v in kap.plaene],
                        bloecke=[
                            b if b.medium is None else replace(b, medium=neu[0])
                            for b in kap.bloecke
                            if b.medium is None
                            or (neu := medien_umbenennen([b.medium], umbenennung))
                        ],
                    )
                    for kap in k.kapitel
                ],
            )
            for k in kurse
        ]

        def erg_neu(e: Ergaenzung) -> Ergaenzung:
            medien = [
                roh
                for roh in (e.daten.get("media") or [])
                if not (isinstance(roh, dict) and umbenennung.get(roh.get("uri", ""), "") is None)
            ]
            medien = [
                {**roh, "uri": umbenennung.get(roh.get("uri", ""), roh.get("uri"))}
                if isinstance(roh, dict) and roh.get("uri") in umbenennung
                else roh
                for roh in medien
            ]
            daten = {**e.daten, "media": medien} if "media" in e.daten else dict(e.daten)
            return replace(e, daten=daten)

        json_daten = paket_json(
            paket,
            [replace(u, media=medien_umbenennen(u.media, umbenennung)) for u in uebungen],
            kurse_neu or None,
            plaene=[plan_neu(pp) for pp in plaene] or None,
            ergaenzungen=[erg_neu(e) for e in ergaenzungen] or None,
            mit_zeitstempel=mit_zeitstempel,
        )
        if not dateien:
            ziel = ordner / dateiname(paket)
            ziel.write_bytes(json_daten)
            return ziel, meldungen
        ziel = ordner / dateiname(paket, "zip")
        paket_zip(ziel, json_daten, dateien)
        return ziel, meldungen


def paket_zip(ziel: Path, json_daten: bytes, medien: Mapping[str, Path]) -> None:
    """Die ZIP schreiben: ``paket.json`` (gepackt), dann je Datei ``medien/<sha256>.<endung>``
    (ungepackt — Bilder und Videos sind es schon). Reproduzierbar: feste Zeitstempel, feste
    Reihenfolge. Die Dateien müssen schon bereinigt sein (`core/bereinigen.py`)."""
    teil = ziel.with_name(ziel.name + ".teil")
    try:
        with zipfile.ZipFile(teil, "w") as zf:
            kopf = zipfile.ZipInfo(PAKET_JSON, date_time=_ZEIT)
            kopf.compress_type = zipfile.ZIP_DEFLATED
            kopf.external_attr = 0o644 << 16
            zf.writestr(kopf, json_daten)
            for name in sorted(medien):
                if name_lesen(name) is None:
                    raise ValueError(f"kein Name für eine Paketdatei: {name}")
                info = zipfile.ZipInfo(name, date_time=_ZEIT)
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o644 << 16
                with medien[name].open("rb") as quelle, zf.open(info, "w") as aus:
                    shutil.copyfileobj(quelle, aus, 1 << 20)
        teil.replace(ziel)
    except BaseException:
        teil.unlink(missing_ok=True)
        raise


__all__ = [
    "GELADEN",
    "KLARTEXT",
    "PAKET_JSON",
    "ZIP_KOPF",
    "CodeNoetig",
    "dateien_einbinden",
    "export_schreiben",
    "klartext_aufraeumen",
    "medien_fuer_export",
    "medien_umbenennen",
    "medienlisten",
    "paket_oeffnen",
    "paket_zip",
    "sha256_datei",
    "toml_oeffnen",
]
