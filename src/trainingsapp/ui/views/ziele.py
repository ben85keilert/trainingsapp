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

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core.models import Plan
from trainingsapp.ui.components import ziele as z
from trainingsapp.ui.components.tagesfeld_blatt import tagesfeld_blatt
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.leistungen import leistungen_blatt
from trainingsapp.ui.views.nachtragen import nachtragen_route

TAGESFELDER_EINSTELLUNGEN = "/einstellungen/tagesfelder"


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
    bearbeiten: bool = False,
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
    if bearbeiten and uebung is not None and uebung.deleted_at is None:
        out.append(z.Ziel(z.BEARBEITEN, _route(page, f"/uebung/{uebung_id}/bearbeiten")))
    return out


def tagesfeld_ziele(
    page: Any,
    state: AppState,
    feld: tf.Tagesfeld,
    *,
    tag: date | None,
    hier: Iterable[str] = (),
    danach: Callable[[], Any] | None = None,
) -> list[z.Ziel]:
    """Die Wege zu einem Tagesfeld: Eintragen (Blatt, an ``tag`` — ohne Tag heute) · Verlauf
    · Feld bearbeiten · Tag (Ben, 28.10.2026: „bei ‚Zum Tag‘ die Tagesfelder“)."""
    weg = set(hier)
    out: list[z.Ziel] = []
    an = tag or state.heute()
    if z.EINTRAGEN not in weg and feld.deleted_at is None:

        def blatt() -> None:
            page.show_dialog(
                tagesfeld_blatt(
                    page,
                    state,
                    feld,
                    an,
                    danach=danach,
                    bearbeiten=_route(page, f"{TAGESFELDER_EINSTELLUNGEN}/{feld.id}"),
                )
            )

        out.append(z.Ziel(z.EINTRAGEN, blatt, untertitel="" if tag is None else f"{an:%d.%m.%Y}"))
    if z.VERLAUF not in weg:
        out.append(z.Ziel(z.VERLAUF, _route(page, f"/verlauf/tagesfeld/{feld.id}")))
    if z.FELD not in weg and feld.deleted_at is None:
        out.append(z.Ziel(z.FELD, _route(page, f"{TAGESFELDER_EINSTELLUNGEN}/{feld.id}")))
    if tag is not None and z.TAG not in weg:
        out.append(
            z.Ziel(z.TAG, _route(page, f"/tag/{tag.isoformat()}"), untertitel=f"{tag:%d.%m.%Y}")
        )
    return out


def plan_ziele(
    page: Any,
    state: AppState,
    plan: Plan,
    *,
    hier: Iterable[str] = (),
    ueben: Callable[[], Any] | None = None,
) -> list[z.Ziel]:
    """Die Wege zu einem Plan: Üben (``ueben``: nimmt den Plan für heute auf, sonst nur
    öffnen) · Bearbeiten · Ablauf starten."""
    weg = set(hier)
    out: list[z.Ziel] = []
    if z.UEBEN not in weg:
        out.append(z.Ziel(z.UEBEN, ueben or _route(page, f"/plan/{plan.id}"), untertitel="heute"))
    if z.BEARBEITEN not in weg:
        out.append(z.Ziel(z.BEARBEITEN, _route(page, f"/plaene/{plan.id}")))
    if z.ABLAUF not in weg and plan.items:
        out.append(z.Ziel(z.ABLAUF, _route(page, f"/plan/{plan.id}/timer/ablauf")))
    return out


__all__ = ["plan_ziele", "tagesfeld_ziele", "ueben_ziele", "ziele_fuer"]
