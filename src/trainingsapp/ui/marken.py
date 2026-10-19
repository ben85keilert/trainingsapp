"""Leistungen der Person als Marken in Zeitleiste und laufender HRV-Aufnahme.

Ben, 19.10.2026 (`docs/plan_eintraege_hrv.md`, Teil B): „50 Liegestützen → commit → Pause,
gucken, wie die Kurve reagiert → 50 Liegestützen → Klick“. Jeder Tipp, der eine Menge
einträgt, und jedes Abschließen wird ein Ereignis der laufenden Einheit (``person/leistung``,
``person/abschluss``); läuft eine Aufnahme darin, projiziert die Einheit daraus eine Notiz
mit Marke `person/leistung` (Vertrag §4: ``feld``, ``wert``). Die Zeit ist die **Tippzeit** —
Pi mal Daumen das Ende des Satzes, nie der Beginn.

Der erste Satz eines Eintrags beginnt den Abschnitt der Übung auf der Spur ``uebung``, das
Abschließen beendet ihn — außer die Uhr der Übung läuft schon (sie klammert mit „Planke:
Start/Ende“), dann kommen nur die Notizen (``grenze=False``).

Ohne laufende Einheit geschieht nichts: Nachträge und Korrekturen haben keine Marke, ihre
Zeit ist geschätzt.
"""

from __future__ import annotations

from typing import Any

from trainingsapp.core.einheit import Ereignis
from trainingsapp.core.models import Exercise, SessionEntry
from trainingsapp.ui import einheit as einheit_ui


def aufnahme_laeuft(state: Any) -> bool:
    """Bekommt ein Tipp jetzt eine Marke in einer HRV-Aufnahme? (Für das Herz im Block.)"""
    e = einheit_ui.laeuft(state)
    hrv = e.hrv if e is not None else None
    return hrv is not None and hrv.aktiv


def _text(uebung: Exercise, auspraegung: str, rest: str) -> str:
    kopf = f"{uebung.name} {auspraegung}" if auspraegung else uebung.name
    return f"{kopf}: {rest}"


def leistung(
    state: Any,
    uebung: Exercise,
    eintrag: SessionEntry,
    feld: str,
    wert: float,
    *,
    erster: bool,
    grenze: bool = True,
    auspraegung: str = "",
) -> bool:
    """Ein Mengen-Tipp in die Zeitleiste der laufenden Einheit — ``True``, wenn eine läuft.

    ``erster``: der erste Satz dieses Eintrags (beginnt den Abschnitt der Übung, wenn
    ``grenze``); ``auspraegung``: „10 kg · links“ für den Notiztext.
    """
    e = einheit_ui.laeuft(state)
    if e is None or e.t0 is None:
        return False
    rest = (
        f"{wert:g}" if isinstance(wert, int | float) and not isinstance(wert, bool) else str(wert)
    )
    e.nachtragen(
        Ereignis(
            e.dauer_s(),
            "person",
            "leistung",
            _text(uebung, auspraegung, rest),
            {
                "eintrag": eintrag.id,
                "uebung": uebung.id,
                "name": uebung.name,
                "feld": feld,
                "wert": wert,
                "erster": erster,
                "grenze": grenze,
            },
        )
    )
    return True


def abschluss(
    state: Any,
    uebung: Exercise,
    eintrag: SessionEntry,
    *,
    grenze: bool = True,
    auspraegung: str = "",
) -> bool:
    """„Abschließen“ oder „Gemacht“ in die Zeitleiste — ``True``, wenn eine Einheit läuft."""
    e = einheit_ui.laeuft(state)
    if e is None or e.t0 is None:
        return False
    e.nachtragen(
        Ereignis(
            e.dauer_s(),
            "person",
            "abschluss",
            _text(uebung, auspraegung, "fertig"),
            {"eintrag": eintrag.id, "uebung": uebung.id, "name": uebung.name, "grenze": grenze},
        )
    )
    return True


__all__ = ["abschluss", "aufnahme_laeuft", "leistung"]
