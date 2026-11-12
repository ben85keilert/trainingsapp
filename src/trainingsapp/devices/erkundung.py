"""Geräteprobe: Rohmitschnitt eines (unbekannten) Geräts ohne Messung — Diagnosemodus, Stufe 6.

Plan `docs/plan_diagnosemodus.md` §2.8 (Ben, 4.11.2026: „Ist das Gerät unbekannt, wäre es gut,
man könnte einfach einen Rohmitschnitt machen, den man dann hinterher ausgeben kann“). Ablauf:

1. `verbinden` — Verbindung, Dienste samt Merkmalen und Eigenschaften (`dienste`);
2. `starten` — Ordner ``Diagnose/<ts>_<gerät>/``, Mitschnitt ``mitschnitt.jsonl``
   (``mitschnitt-v1``), jedes lesbare Merkmal **einmal** lesen (nie Seriennummer und
   Systemkennung, `hrv_core.geraete.gatt.NIE_LESEN`; nie die Dienste „User Data“ und
   „Generic Access“, `DIENSTE_NIE_LESEN`), jedes mit Benachrichtigung oder Anzeige
   abonnieren. **Nie wird auf das Gerät geschrieben** (wie ``hrv-core/scripts/ble_erkundung.py``);
3. `marke` — „jetzt bewegt“, „jetzt still“ oder eine freie Marke;
4. `beenden` — Formular (Hersteller und Modell, was getan, Vergleichswert) und Zusammenfassung
   als ``probe.json``, Mitschnitt schließen, trennen.

Mitgeschrieben wird nur das gewählte Gerät, nie andere in der Nähe. Die Probe bleibt auf dem
Handy; hinaus nur über „Teilen“ (`probe_zip`, bereinigt wie der Export). Daraus entstehen in
hrv-core Treiber (`hrv_core.geraete.treiber`); Proben anderer Personen kommen nie in ein Repo
(P115). Ohne flet, mit einer Transport-Attrappe testbar (`tests/test_geraeteprobe.py`).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import re
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hrv_core import deid
from hrv_core import mitschnitt as mt
from hrv_core.geraete import gatt

from ..config import app_version
from ..core.diagnose import DIAGNOSE_ORDNER, PROBE_DATEI
from .gatt import BleTransport
from .mitschnitt import MitschnittTransport

#: Datei mit Formular, Dienste-Abbild und Zusammenfassung neben dem Mitschnitt
PROBE_FORMAT = "geraeteprobe-v1"
#: Fristen (s)
TIMEOUT_VERBINDEN_S = 20.0
TIMEOUT_GATT_S = 5.0
#: Dienste, deren Merkmale die Probe **nie liest** (S32): „User Data“ (0x181C — Vorname,
#: Geburtsdatum, Gewicht …) und „Generic Access“ (0x1800 — der Gerätename, oft mit dem Namen
#: der Person). Die Werte stünden sonst im Mitschnitt, und `hrv_core.deid.mitschnitt_zeilen`
#: nimmt beim Teilen nur 0x2A00/0x2A25/0x2A23 heraus. Abonniert wird dort auch nichts.
DIENSTE_NIE_LESEN: frozenset[str] = frozenset({gatt.uuid16(0x181C), gatt.uuid16(0x1800)})
#: Phasen für die Marken der Probe
PHASEN = ("bewegt", "still")


def _ordnername(start: datetime, name: str) -> str:
    """``2026-11-04_061500_Decathlon_HRM`` — ohne Seriennummer, nur sichere Zeichen.

    >>> _ordnername(datetime(2026, 11, 4, 6, 15, tzinfo=UTC), "Polar H10 A1B2C3D4")
    '2026-11-04_061500_Polar_H10'
    """
    modell = str(deid.geraet_modell(name) or "Geraet")
    sicher = re.sub(r"[^A-Za-z0-9]+", "_", modell).strip("_") or "Geraet"
    return f"{start.astimezone(UTC):%Y-%m-%d_%H%M%S}_{sicher[:40]}"


class Geraeteprobe:
    """Ein Rohmitschnitt ohne Messung (siehe Modultext)."""

    def __init__(
        self,
        transport: BleTransport,
        basis: Path,
        *,
        uhr: Callable[[], float] = time.monotonic,
        jetzt_utc: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.transport = MitschnittTransport(transport, uhr=uhr)
        self.basis = Path(basis)
        self._uhr = uhr
        self._jetzt_utc = jetzt_utc
        self.device_id = ""
        self.name = ""
        self.mtu = 0
        self.verbunden = False
        #: Ein Verbindungsaufbau läuft — die Ansicht startet solange keinen zweiten (H108)
        self.verbindet = False
        self.getrennt_grund: str | None = None
        #: Dienste mit Merkmalen: uuid, name, merkmale (uuid, name, eigenschaften)
        self.dienste: list[dict[str, Any]] = []
        self.schreiber: mt.Schreiber | None = None
        self.ordner: Path | None = None
        self.seit: float | None = None
        #: Was gelesen bzw. abonniert wurde, und was nicht ging (UUID → Grund)
        self.gelesen: list[str] = []
        self.abonniert: list[str] = []
        self.fehler: dict[str, str] = {}

    @property
    def laeuft(self) -> bool:
        return self.schreiber is not None and self.schreiber.offen

    # -- Ablauf -----------------------------------------------------------------

    async def verbinden(self, device_id: str, name: str = "") -> list[dict[str, Any]]:
        """Verbinden und die Dienste auflisten — noch ohne Mitschnitt."""
        self.verbindet = True
        try:
            return await self._verbinden(device_id, name)
        finally:
            self.verbindet = False

    async def _verbinden(self, device_id: str, name: str) -> list[dict[str, Any]]:
        self.device_id, self.name = device_id, name or device_id

        def trennung(grund: str | None) -> None:
            self.verbunden = False
            self.getrennt_grund = grund or "ohne Grund"

        self.mtu = await asyncio.wait_for(
            self.transport.connect(device_id, trennung), timeout=TIMEOUT_VERBINDEN_S
        )
        self.verbunden = True
        dienste = await asyncio.wait_for(self.transport.discover(device_id), TIMEOUT_GATT_S)
        abbild = self.transport.dienste_abbild or [
            {"uuid": d, "merkmale": []} for d in sorted(dienste)
        ]
        self.dienste = [
            {
                "uuid": d["uuid"],
                "name": gatt.beschreibung(d["uuid"]),
                "merkmale": [
                    {
                        "uuid": m["uuid"],
                        "name": gatt.beschreibung(m["uuid"]),
                        "eigenschaften": list(m.get("eigenschaften") or []),
                    }
                    for m in d.get("merkmale") or []
                ],
            }
            for d in abbild
        ]
        return self.dienste

    async def starten(self) -> Path:
        """Mitschnitt anlegen, Lesbares einmal lesen, alles Melderische abonnieren."""
        if self.laeuft:
            assert self.ordner is not None
            return self.ordner
        start = self._jetzt_utc()
        ordner = self.basis / DIAGNOSE_ORDNER / _ordnername(start, self.name)
        n = 1
        while ordner.exists():
            n += 1
            ordner = ordner.with_name(f"{ordner.name}_{n}")
        ordner.mkdir(parents=True)
        self.ordner = ordner
        self.schreiber = mt.Schreiber(
            ordner / mt.DATEINAME,
            {
                "app": f"trainingsapp {app_version()[0]}",
                "geraet": {"name": self.name, "id": self.device_id, "art": "unbekannt"},
                "dienste": self.dienste,
            },
            uhr_ns=lambda: round(self._uhr() * 1e9),
        )
        self.transport.anhaengen(self.schreiber)
        self.schreiber.kontext("diagnose_start", phase="probe")
        self.seit = self._uhr()
        for d in self.dienste:
            if str(d["uuid"]).lower() in DIENSTE_NIE_LESEN:
                continue  # Angaben zur Person — weder lesen noch abonnieren
            for m in d["merkmale"]:
                uuid = m["uuid"].lower()
                if "lesen" in m["eigenschaften"] and uuid not in gatt.NIE_LESEN:
                    try:
                        await asyncio.wait_for(
                            self.transport.read(self.device_id, d["uuid"], uuid), TIMEOUT_GATT_S
                        )
                        self.gelesen.append(uuid)
                    except Exception as e:
                        self.fehler[uuid] = f"lesen: {e!r}"[:120]
                if {"benachrichtigen", "anzeigen"} & set(m["eigenschaften"]):
                    try:
                        await asyncio.wait_for(
                            self.transport.subscribe(
                                self.device_id, d["uuid"], uuid, lambda _d, _t: None
                            ),
                            TIMEOUT_GATT_S,
                        )
                        self.abonniert.append(uuid)
                    except Exception as e:
                        self.fehler[uuid] = f"abonnieren: {e!r}"[:120]
        return ordner

    def marke(self, phase: str | None = None) -> dict[str, Any] | None:
        """Eine Marke: ``bewegt``, ``still`` oder frei (``None``)."""
        if self.schreiber is None or not self.schreiber.offen:
            return None
        kontext = {"phase": phase} if phase else None
        return self.schreiber.marke(mt.MARKE_FREI, kontext=kontext)

    def stand(self) -> dict[str, Any]:
        """Für die Ansicht: Laufzeit, Zeilen, Bytes, Pakete je Merkmal."""
        s = self.schreiber
        jetzt = self._uhr()
        return {
            "seit_s": round(jetzt - self.seit, 1) if self.seit is not None else 0.0,
            "zeilen": s.zeilen if s is not None else 0,
            "bytes": s.bytes if s is not None else 0,
            "gelesen": len(self.gelesen),
            "abonniert": len(self.abonniert),
            "fehler": len(self.fehler),
            "pakete": {k: v["pakete"] for k, v in self.transport.zaehler.stand(jetzt).items()},
            "verbunden": self.verbunden,
        }

    async def beenden(self, formular: dict[str, str] | None = None) -> Path | None:
        """Formular und Zusammenfassung schreiben, Mitschnitt schließen, trennen."""
        ordner, schreiber = self.ordner, self.schreiber
        if schreiber is not None:
            # Scheitert das Schreiben (Speicher voll, H108), endet die Probe trotzdem: der
            # Schreiber hängt ab, und `laeuft` wird falsch
            with contextlib.suppress(Exception):
                schreiber.kontext("diagnose_ende", phase="probe")
            self.transport.abhaengen()
            with contextlib.suppress(Exception):
                schreiber.schliessen()
            self.schreiber = None
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.transport.disconnect(self.device_id), TIMEOUT_GATT_S)
        self.verbunden = False
        if ordner is None:
            return None
        zusammenfassung: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            zusammenfassung = mt.zusammenfassen(mt.laden(ordner / mt.DATEINAME))
        doc = {
            "format": PROBE_FORMAT,
            "geraet": {"name": self.name, "modell": deid.geraet_modell(self.name)},
            "formular": {k: str(v) for k, v in (formular or {}).items() if v},
            "dienste": self.dienste,
            "gelesen": self.gelesen,
            "abonniert": self.abonniert,
            "fehler": self.fehler,
            "zusammenfassung": zusammenfassung,
        }
        (ordner / PROBE_DATEI).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return ordner


# ---------------------------------------------------------------------------
# Auf dem Gerät: auflisten, teilen, löschen
# ---------------------------------------------------------------------------


def proben(basis: Path) -> list[dict[str, Any]]:
    """Die Geräteproben auf dem Gerät, neueste zuerst — Ordner, Name, Größe, Formular."""
    wurzel = Path(basis) / DIAGNOSE_ORDNER
    if not wurzel.is_dir():
        return []
    out = []
    for ordner in sorted(wurzel.iterdir(), reverse=True):
        if not (ordner / mt.DATEINAME).is_file():
            continue
        doc: dict[str, Any] = {}
        with contextlib.suppress(OSError, ValueError):
            doc = json.loads((ordner / PROBE_DATEI).read_text(encoding="utf-8"))
        groesse = sum(p.stat().st_size for p in ordner.iterdir() if p.is_file())
        out.append(
            {
                "ordner": ordner,
                "name": (doc.get("geraet") or {}).get("modell") or ordner.name,
                "formular": doc.get("formular") or {},
                "bytes": groesse,
                "fertig": (ordner / PROBE_DATEI).is_file(),
            }
        )
    return out


def probe_zip(ordner: Path) -> bytes:
    """Eine Geräteprobe als ZIP zum Teilen — der Mitschnitt bereinigt (Adressen maskiert,
    Gerätename gekürzt, Kennungs-Merkmale entfernt), ``probe.json`` ohne Adresse."""
    ordner = Path(ordner)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", compression=zipfile.ZIP_DEFLATED) as z:
        zeilen = deid.mitschnitt_zeilen(mt.lesen(ordner / mt.DATEINAME))
        z.writestr(
            f"{DIAGNOSE_ORDNER}/{ordner.name}/{mt.DATEINAME}",
            "".join(
                json.dumps(zeile, ensure_ascii=False, separators=(",", ":")) + "\n"
                for zeile in zeilen
            ),
        )
        if (ordner / PROBE_DATEI).is_file():
            text = deid.adressen_maskieren((ordner / PROBE_DATEI).read_text(encoding="utf-8"))
            with contextlib.suppress(ValueError):
                doc = json.loads(text)
                name = (doc.get("geraet") or {}).get("name")
                if isinstance(name, str):
                    doc["geraet"]["name"] = deid.geraet_modell(name)
                text = json.dumps(doc, ensure_ascii=False, indent=2)
            z.writestr(f"{DIAGNOSE_ORDNER}/{ordner.name}/{PROBE_DATEI}", text)
    return puffer.getvalue()


def probe_loeschen(ordner: Path) -> None:
    """Eine Geräteprobe löschen (Ordner unter ``Diagnose/``)."""
    ordner = Path(ordner)
    if ordner.parent.name != DIAGNOSE_ORDNER:
        raise ValueError(f"keine Geräteprobe: {ordner}")
    for p in ordner.iterdir():
        if p.is_file():
            p.unlink()
    ordner.rmdir()


__all__ = [
    "PHASEN",
    "PROBE_DATEI",
    "PROBE_FORMAT",
    "Geraeteprobe",
    "probe_loeschen",
    "probe_zip",
    "proben",
]
