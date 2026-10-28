"""Welche Wege es zu einer Übung gibt — die Ziele einer Zeile (Ben, 28.10.2026).

`ziele_fuer` baut aus Übung, Tag und Plänen die Liste der `Ziel`e für das Zielblatt
(`components/ziele.py`), in Bens Reihenfolge (28.10.2026): Einträge des Tages (Blatt),
Nachtragen, Üben — je Plan der Zeile einer, dann die Standardübung (Ben: „Montag sieht
vielleicht Kniebeugen dynamisch vor, Dienstag Kniebeugen statisch … das Routing muss an den
Ursprung des Übungseintrags gekoppelt sein“) —, Verlauf, Tag, Übungsseite. Nur Routen und
Repo-Abfragen, keine Rechnung.
Was man schon sieht (``hier``), fehlt. Plan: `docs/plan_routing_ziele.md`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

from trainingsapp.ui.components import ziele as z
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.leistungen import leistungen_blatt
from trainingsapp.ui.views.nachtragen import nachtragen_route


def _route(page: Any, pfad: str) -> Callable[[], Any]:
    async def handler() -> None:
        await page.push_route(pfad)

    return handler


def ueben_ziele(
    state: AppState, uebung_id: str, plan_ids: Iterable[str], page: Any
) -> list[z.Ziel]:
    """„Üben“ je Plan, in dem die Übung heute noch steht (bei der Übung, wie „Weiter mit“),
    dann die Standardübung — nichts für gelöschte oder archivierte Übungen."""
    aktuell = state.uebungen.laden(uebung_id)
    if aktuell is None or aktuell.archived:
        return []
    out: list[z.Ziel] = []
    gesehen: set[str] = set()
    for plan_id in plan_ids:
        if not plan_id or plan_id in gesehen:
            continue
        gesehen.add(plan_id)
        plan = state.plaene.laden(plan_id)
        if plan is None:
            continue
        item = next((i for i in plan.items if i.exercise_id == uebung_id), None)
        if item is None:
            continue

        def oeffnen(plan_id: str = plan.id, item_id: str = item.id) -> Any:
            state.plan_offen = item_id
            state.plan_ziel = item_id
            return page.push_route(f"/plan/{plan_id}")

        out.append(z.Ziel(z.UEBEN, oeffnen, untertitel=f"Plan „{plan.name}“"))
    out.append(z.Ziel(z.UEBEN, _route(page, f"/training/{uebung_id}"), untertitel="Standardübung"))
    return out


def ziele_fuer(
    page: Any,
    state: AppState,
    uebung_id: str,
    *,
    tag: date | None,
    plan_ids: Iterable[str] = (),
    hier: Iterable[str] = (),
    strecke_id: str | None = None,
    danach: Callable[[], Any] | None = None,
) -> list[z.Ziel]:
    """Alle Wege zu dieser Übung, in fester Folge: Einträge · Üben … · Nachtragen · Verlauf ·
    Tag · Übungsseite (Strecke statt Einträge bei einem Training). ``hier``: Schlüssel
    der Ziele, auf denen man schon steht. ``danach``: läuft, wenn das Blatt „Einträge des
    Tages“ zu ist (die Liste neu lesen)."""
    weg = set(hier)
    plan_ids = [p for p in plan_ids if p]
    basis = "" if tag is None or tag == state.heute() else f"/tag/{tag.isoformat()}"
    letzter_plan = plan_ids[-1] if plan_ids else None
    uebung = state.uebungen.laden(uebung_id, mit_geloeschten=True)
    out: list[z.Ziel] = []
    if strecke_id is not None and z.STRECKE not in weg:
        out.append(z.Ziel(z.STRECKE, _route(page, f"/ausdauer/{strecke_id}")))
    elif tag is not None and uebung is not None and z.EINTRAEGE not in weg:
        tag_ = tag

        def blatt() -> None:
            page.show_dialog(
                leistungen_blatt(
                    page,
                    state,
                    uebung,
                    tag_,
                    nachtragen=nachtragen_route(basis, uebung_id, letzter_plan),
                    danach=danach,
                )
            )

        out.append(z.Ziel(z.EINTRAEGE, blatt))
    # Ben, 28.10.2026: Einträge · Nachtragen · Üben (Plan 1 · Plan 2 · Standardübung) · …
    if z.NACHTRAGEN not in weg and uebung is not None and uebung.deleted_at is None:
        route = nachtragen_route(basis, uebung_id, letzter_plan)
        out.append(z.Ziel(z.NACHTRAGEN, _route(page, route)))
    if z.UEBEN not in weg:
        out.extend(ueben_ziele(state, uebung_id, plan_ids, page))
    if z.VERLAUF not in weg:
        out.append(z.Ziel(z.VERLAUF, _route(page, f"/verlauf/{uebung_id}")))
    if tag is not None and z.TAG not in weg:
        out.append(
            z.Ziel(z.TAG, _route(page, f"/tag/{tag.isoformat()}"), untertitel=f"{tag:%d.%m.%Y}")
        )
    if uebung is not None and z.UEBUNG not in weg:
        out.append(z.Ziel(z.UEBUNG, _route(page, f"/uebung/{uebung_id}")))
    return out


__all__ = ["ueben_ziele", "ziele_fuer"]
