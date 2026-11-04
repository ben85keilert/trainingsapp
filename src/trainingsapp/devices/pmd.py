"""Polar Measurement Data (PMD) — seit hrv-core 0.6.0 aus `hrv_core.geraete.pmd`.

Kommandos, Steuerantworten, Einstellungen und Rahmen-Parser (EKG, PPI, Beschleunigung) liegen
in hrv-core, gemeinsam mit praxis_gui und der Brustgurt-Diagnose (Plan Diagnosemodus, Stufe
2); hier bleibt nur, was an den Messwerten der App hängt: `ppi_messwerte`. Der Rest wird
durchgereicht, damit ``from trainingsapp.devices.pmd import …`` weiter gilt. **Geparst wird
in Python**; die Flet-Erweiterung reicht nur rohe Bytes durch.

Stand der Verifikation: EKG (Typ 0) und Beschleunigung (Typ 2) am Polar H10, PPI (Typ 3) am
Verity Sense — Einzelheiten im Modultext von `hrv_core.geraete.pmd`.
"""

from __future__ import annotations

from collections.abc import Sequence

from hrv_core.geraete.pmd import *  # noqa: F403 — die Schnittstelle bleibt dieselbe
from hrv_core.geraete.pmd import PpiProbe
from hrv_core.geraete.pmd import __all__ as _HRV_CORE_ALL

from .base import Messwert, PpiPaket, rr_auf_zeitachse


def ppi_messwerte(
    device_id: str, proben: Sequence[PpiProbe], t_capture: float
) -> tuple[PpiPaket, list[Messwert]]:
    """Ein PPI-Paket in das Rohpaket und die brauchbaren Messwerte zerlegen.

    Die Zeitpunkte werden über **alle** Intervalle des Pakets zurückgerechnet,
    erst danach fallen blockierte und 0-Werte heraus: auch ein verworfenes
    Intervall hat gedauert. Nur über die brauchbaren gerechnet, lägen alle
    Schläge davor um genau diese Dauer zu spät. ``hf_bpm`` ist das HF-Byte der
    letzten brauchbaren Probe (wie praxis_gui).

    >>> proben = [PpiProbe(62, 968, 3, False, True, True),
    ...           PpiProbe(62, 1400, 400, True, True, True),
    ...           PpiProbe(63, 970, 5, False, True, True)]
    >>> paket, werte = ppi_messwerte("v", proben, 100.0)
    >>> paket.blocker, paket.kontakt
    ((0, 1, 0), (1, 1, 1))
    >>> [(m.rr_ms, m.hf_bpm, m.t_capture, m.tw_src) for m in werte]
    [(968, 63, 97.63, 'r'), (970, 63, 100.0, 'm')]
    """
    paket = PpiPaket(
        device_id=device_id,
        t_capture=t_capture,
        ppi_ms=tuple(p.ppi_ms for p in proben),
        fehler_ms=tuple(p.fehler_ms for p in proben),
        blocker=tuple(int(p.blocker) for p in proben),
        kontakt=tuple(int(p.hautkontakt) for p in proben),
    )
    brauchbare = [p for p in proben if p.brauchbar]
    if not brauchbare:
        return paket, []
    hf = brauchbare[-1].hf_bpm
    zeiten = rr_auf_zeitachse([p.ppi_ms for p in proben], t_capture)
    werte = [
        Messwert(device_id, rr, hf, t, "r" if rekonstruiert else "m")
        for p, (rr, t, rekonstruiert) in zip(proben, zeiten, strict=True)
        if p.brauchbar
    ]
    return paket, werte


__all__ = [*_HRV_CORE_ALL, "ppi_messwerte"]
