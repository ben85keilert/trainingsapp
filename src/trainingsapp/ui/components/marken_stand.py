"""Zustand der Marken-Leiste ohne flet — die Leiste und der Uhrkanal teilen ihn.

Plan `docs/plan_diagnosemodus.md` §2.5 und §2.6. Was eine Marke ist (Art aus dem Kontext,
Nummer im Satz, Zeile im Mitschnitt) und was die Seite „Diagnose“ am Band zeigt, hängt nicht am
Bildschirm: ⏯ an der Uhr (`ui.geraete.flet_medien_kanal`) setzt Marken über dieselben
Funktionen wie ein Tipp in der Leiste (`components.marken_leiste`). Darum liegt das hier ohne
``import flet`` — die CI testet den Uhrkanal flet-frei (``uv sync --only-group ci``).

Die Controls, die ein Tipp nachzieht (Zahl, Kopfzeile, Chips), legt die Leiste im
`LeistenStand` ab; ohne Leiste (nur Uhr) bleiben sie ``None``.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hrv_core import mitschnitt as mt

from trainingsapp.core import diagnose as dg
from trainingsapp.core.kurzcode import kurzcode

if TYPE_CHECKING:
    import flet as ft


@dataclass
class LeistenStand:
    """Was die Leiste über Neuaufbauten hinweg weiß (lebt im `AppState`)."""

    zaehler: dg.MarkenZaehler = field(default_factory=dg.MarkenZaehler)
    #: Wahl im Chip: (Art, Kontext-Schlüssel) — gilt, bis sich der Kontext ändert
    wahl: tuple[str, tuple[Any, ...]] | None = None
    #: IDs der gesetzten Marken, neueste zuletzt (für ↶)
    marken: list[int] = field(default_factory=list)
    #: Wiederholungen je Kurzcode (aus dem Katalog, einmal gelesen)
    wdh_je_code: dict[str, bool] | None = None
    #: die Controls, die ein Tipp nachzieht
    zahl: ft.Text | None = None
    kopf: ft.Text | None = None
    #: der Vergleich nach dem letzten Satz (Marken · Zähler · eingetragen, Stufe 8)
    vergleich: ft.Text | None = None
    chips: dict[str, ft.Control] = field(default_factory=dict)


def leistenstand(state: Any) -> LeistenStand:
    """Der `LeistenStand` im `AppState` (legt ihn beim ersten Mal an)."""
    stand = getattr(state, "diagnose_leiste", None)
    if not isinstance(stand, LeistenStand):
        stand = LeistenStand()
        state.diagnose_leiste = stand
    return stand


def diagnose_lauf(state: Any) -> Any:
    """Der `Messlauf`, solange der Diagnosemodus aufzeichnet — sonst ``None``."""
    lauf = getattr(state, "messlauf", None)
    return lauf if lauf is not None and getattr(lauf, "diagnose_aktiv", False) else None


def _wiederholungen(state: Any, stand: LeistenStand) -> Callable[[str], bool]:
    if stand.wdh_je_code is None:
        tabelle: dict[str, bool] = {}
        with contextlib.suppress(Exception):
            for u in state.uebungen.alle(mit_archivierten=True):
                tabelle[kurzcode(u.id)] = dg.hat_wiederholungen(u.result_spec)
        stand.wdh_je_code = tabelle
    tabelle = stand.wdh_je_code
    return lambda code: bool(tabelle.get(code) or tabelle.get(code[:6]))


def kontext(state: Any) -> tuple[dg.MarkenKontext, str]:
    """Der Kontext der nächsten Marke und ihre Art (mit der Wahl im Chip)."""
    stand = leistenstand(state)
    lauf = diagnose_lauf(state)
    ereignisse = list(lauf.ereignisse()) if lauf is not None else []
    k = dg.kontext_aus_notizen(ereignisse, _wiederholungen(state, stand))
    art = k.art
    if stand.wahl is not None:
        if stand.wahl[1] == k.schluessel:
            art = stand.wahl[0]
        else:
            stand.wahl = None  # der Kontext hat sich geändert
    return k, art


def marke_setzen(
    state: Any,
    *,
    quelle: str = mt.QUELLE_HANDY,
    typ: str | None = None,
    t_ns: int | None = None,
    tm: int | None = None,
) -> dict[str, Any] | None:
    """Eine Marke in den Mitschnitt — ``typ=None``: die Art aus dem Kontext (mit Nummer im
    Satz), sonst etwa eine Störung. ``t_ns``: Zeitpunkt auf der Uhr der Messung (⏯ an der
    Uhr: der Druck, umgerechnet), ``tm``: Zeit der Dart-Seite (µs). ``None`` ohne Diagnose."""
    lauf = diagnose_lauf(state)
    if lauf is None:
        return None
    stand = leistenstand(state)
    k, art = kontext(state)
    wahl = typ or art
    nr = stand.zaehler.weiter(wahl, k) if typ is None else None
    zeile = lauf.marke(wahl, quelle=quelle, nr=nr, kontext=k.als_dict(), t=t_ns, tm=tm)
    if zeile is not None and typ is None:
        stand.marken.append(int(zeile["id"]))
    nachziehen(state, k, art)
    return zeile


def uhr_zeilen(state: Any) -> tuple[str, str] | None:
    """Zeile 1 und 2 der Seite „Diagnose“ am Band: („Wdh 12“, „Kniebeuge S2“) — ``None``
    ohne Diagnose."""
    if diagnose_lauf(state) is None:
        return None
    stand = leistenstand(state)
    k, art = kontext(state)
    kurz = {dg.WDH: "Wdh", dg.ATEM: "Atem"}.get(art, art)
    if k.uebung:
        zweite = k.uebung + (f" S{k.satz}" if k.satz else "")
    else:
        zweite = "Pause" if k.phase == "pause" else "Messung"
    return f"{kurz} {stand.zaehler.stand(art, k)}", zweite


def art_waehlen(state: Any, art: str) -> None:
    """Chip: diese Art, bis sich der Kontext ändert."""
    stand = leistenstand(state)
    k, _ = kontext(state)
    stand.wahl = (art, k.schluessel)
    nachziehen(state, k, art)


def nachziehen(state: Any, k: dg.MarkenKontext, art: str) -> None:
    """Zahl, Kopfzeile und Chips der Leiste nachziehen — ohne Leiste geschieht nichts."""
    stand = leistenstand(state)
    if stand.zahl is not None:
        stand.zahl.value = str(stand.zaehler.stand(art, k))
    if stand.kopf is not None:
        stand.kopf.value = k.text(art)
    for name, chip in stand.chips.items():
        chip.selected = name == art  # type: ignore[attr-defined]
    with contextlib.suppress(Exception):
        for c in (stand.zahl, stand.kopf, *stand.chips.values()):
            if c is not None:
                c.update()


__all__ = [
    "LeistenStand",
    "art_waehlen",
    "diagnose_lauf",
    "kontext",
    "leistenstand",
    "marke_setzen",
    "nachziehen",
    "uhr_zeilen",
]
