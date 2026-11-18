"""Übungen, die auf ihr Paket warten (V4, `docs/plan_paketverweise.md`, Ben 17.11.2026).

Ein Plan oder Kapitel kann Übungen eines anderen Pakets nennen (V1). Fehlt dieses Paket, lässt
die App die Übungen nicht mehr still weg: Kapitel und Plan sagen, wie viele fehlen und woher sie
kämen — aus ``braucht`` des installierten Pakets (Migration 070) —, mit „… laden“, wenn die
Voraussetzung eine Adresse nennt (V6; ein privates Paket fragt dort nach seinem Code, P220).
Kommt das Paket, trägt der Import die Übungen von selbst nach (`PaketRepo.fehlendes_nachtragen`)
— Ben, 17.11.2026, F3: „von selbst“.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import flet as ft

from trainingsapp.core.kurse import Kapitel, Kurs
from trainingsapp.core.models import Plan
from trainingsapp.core.pakete import Voraussetzung
from trainingsapp.core.paketversion import version_text
from trainingsapp.ui.components.karte import karte, titel


def wartet_text(anzahl: int, wo: str, fehlt: Sequence[tuple[Voraussetzung, int | None]]) -> str:
    """Der Satz: wie viele fehlen, woher sie kämen, und dass sie von selbst kommen.

    >>> wartet_text(2, "dieses Kapitels", [(Voraussetzung("a", "Grundlagen"), None)])
    '2 Übungen dieses Kapitels fehlen hier — sie kommen aus „Grundlagen“ (nicht installiert). \
Kommt das Paket, trägt die App sie von selbst nach.'
    >>> wartet_text(1, "des Plans", [(Voraussetzung("a", "A", 10000), 6)])
    '1 Übung des Plans fehlt hier — sie kommt aus „A“ (hier 0.0.6, gebraucht ab 1.0.0). \
Kommt das Paket, trägt die App sie von selbst nach.'
    >>> wartet_text(1, "des Plans", [])
    '1 Übung des Plans fehlt hier — aus einem Paket, das hier nicht installiert ist.'
    """
    zahl = "1 Übung" if anzahl == 1 else f"{anzahl} Übungen"
    satz = f"{zahl} {wo} {'fehlt' if anzahl == 1 else 'fehlen'} hier — "
    if not fehlt:
        return satz + "aus einem Paket, das hier nicht installiert ist."
    teile = []
    for v, da in fehlt:
        if da is None:
            teile.append(f"„{v.name}“ (nicht installiert)")
        else:
            teile.append(
                f"„{v.name}“ (hier {version_text(da)}, gebraucht ab {version_text(v.version)})"
            )
    woher = "sie kommt aus " if anzahl == 1 else "sie kommen aus "
    return (
        satz
        + woher
        + " oder ".join(teile)
        + ". Kommt das Paket, trägt die App sie von selbst nach."
    )


def wartet_zeilen(
    page: Any, state: Any, fehlen: Sequence[str], paket_id: str | None, wo: str
) -> list[ft.Control]:
    """Der Satz und je Voraussetzung mit Adresse „… laden“ — leer, wenn nichts fehlt."""
    if not fehlen:
        return []
    fehlt = state.pakete.wartet_auf(paket_id)
    zeilen: list[ft.Control] = [
        ft.Text(wartet_text(len(fehlen), wo, fehlt), size=13, data="wartet")
    ]
    for v, da in fehlt:
        if v.quelle:
            zeilen.append(
                ft.TextButton(
                    f"„{v.name}“ laden",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=_laden(page, state, v, da is None),
                    data="wartet_laden",
                )
            )
    return zeilen


def _laden(page: Any, state: Any, v: Voraussetzung, neu: bool) -> Any:
    def handler(_e: Any = None) -> None:
        from trainingsapp.ui.components.paket_link import link_importieren

        async def danach() -> None:
            state.neu_zeichnen()  # der Import hat nachgetragen — die Seite zeigt es

        page.run_task(link_importieren, page, state, v.quelle, herkunft=neu, danach=danach)

    return handler


def im_kapitel(page: Any, state: Any, kurs: Kurs, kapitel: Kapitel) -> ft.Control | None:
    """Die Karte „Wartet auf ein Paket“ im Kapitel — ``None``, wenn alles da ist."""
    zeilen = wartet_zeilen(
        page, state, state.kurse.fehlende_uebungen(kapitel), kurs.package_id, "dieses Kapitels"
    )
    return karte(titel("Wartet auf ein Paket"), *zeilen) if zeilen else None


def im_plan(page: Any, state: Any, plan: Plan) -> list[ft.Control]:
    """Unter „Aus Paket …“ im Plan: was von seiner Vorlage fehlt (Paket- oder Kapitelplan)."""
    if plan.package_id:
        return wartet_zeilen(
            page, state, state.pakete.fehlende_im_plan(plan), plan.package_id, "des Plans"
        )
    if plan.kurs_kapitel_id and plan.kurs_durchlauf_beendet is None:
        woher = state.kurse.kurs_und_kapitel(plan)
        paket_id = woher[0].package_id if woher is not None else None
        return wartet_zeilen(page, state, state.kurse.fehlende_im_plan(plan), paket_id, "des Plans")
    return []


__all__ = ["im_kapitel", "im_plan", "wartet_text", "wartet_zeilen"]
