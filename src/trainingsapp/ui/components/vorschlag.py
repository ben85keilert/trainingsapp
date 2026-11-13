"""Vorschlag nach der Belastung in „Workout fertig“ (Ben, 12.11.2026, `core/anpassung.py`).

Trägt der Plan eine Regel und ist die Anstrengung des Durchlaufs eingetragen, zeigt die Karte,
welche Zeitziele die Regel ändern würde — mit „Übernehmen“ und „So lassen“. **Nichts ändert
sich von selbst.** „Keine Vorschläge mehr“ schaltet sie ab (Einstellungen → Übungen schaltet
sie wieder an). Je Durchlauf wird einmal gefragt: Nach einer Antwort schweigt die Karte, sonst
schlüge sie auf das neue Ziel gleich noch einmal vor.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.core.anpassung import Regel, Vorschlag, vorschlaege, ziel_mit
from trainingsapp.core.models import Plan
from trainingsapp.core.tagesbilanz import menge_text
from trainingsapp.core.workout_eintrag import SRPE
from trainingsapp.data.repositories import SettingRepo
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.kursblock import feld_von


def an(state: Any) -> bool:
    """Ob Vorschläge gezeigt werden — Vorgabe an."""
    return state.einstellungen.lesen(SettingRepo.PLAN_VORSCHLAEGE, "1") != "0"


def an_setzen(state: Any, ja: bool) -> None:
    state.einstellungen.setzen(SettingRepo.PLAN_VORSCHLAEGE, "1" if ja else "0")


def _erledigt(state: Any) -> set[str]:
    """Durchläufe, zu denen schon geantwortet ist (Sitzung)."""
    werte = getattr(state, "vorschlag_erledigt", None)
    if not isinstance(werte, set):
        werte = set()
        with contextlib.suppress(Exception):
            state.vorschlag_erledigt = werte
    return werte


def wert_text(uebung: Any, feld: str, wert: Any) -> str:
    """„48 s Haltezeit“ bzw. je Satz „45 / 45 s Haltezeit“."""
    f = feld_von(uebung, feld)
    if isinstance(wert, list):
        if len(wert) == 1:
            return menge_text(f, float(wert[0]))
        return " / ".join(f"{float(w):g}" for w in wert) + f" {f.unit or f.label}"
    return menge_text(f, float(wert))


@dataclass
class VorschlagKarte:
    """Die Karte (unsichtbar ohne Vorschlag) und ``neu`` zum Nachziehen, wenn die
    Anstrengung eingetragen ist."""

    control: ft.Control
    neu: Callable[[], None]


def vorschlag_karte(page: Any, state: Any, plan: Plan, einheit_id: str) -> VorschlagKarte:
    """Der Vorschlag zu diesem Durchlauf."""
    regel = Regel.aus_dict(plan.anpassung)
    katalog = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}
    spalte = ft.Column(spacing=8, tight=True)
    huelle = ft.Container(visible=False, data="vorschlag", content=karte(spalte))

    def liste() -> tuple[int | None, list[Vorschlag]]:
        if regel is None or not an(state) or einheit_id in _erledigt(state):
            return None, []
        wert = state.einheiten.workout_wert(einheit_id).wert(SRPE)
        stufe = int(wert) if isinstance(wert, int | float) else None
        frisch = state.plaene.laden(plan.id)
        items = frisch.items if frisch is not None else plan.items
        return stufe, vorschlaege(regel, items, katalog, stufe)

    def schweigen() -> None:
        _erledigt(state).add(einheit_id)
        zeichnen()

    def uebernehmen(_e: Any = None) -> None:
        _stufe, offen = liste()
        frisch = state.plaene.laden(plan.id)
        nach_id = {i.id: i for i in (frisch.items if frisch is not None else plan.items)}
        for v in offen:
            item = nach_id.get(v.item_id)
            uebung = katalog.get(item.exercise_id) if item is not None else None
            if item is None or uebung is None:
                continue
            ziel = ziel_mit(item, uebung, v)
            state.plaene.ziel_setzen(item.id, ziel)
            item.target = ziel
        page.show_dialog(ft.SnackBar(ft.Text("Übernommen — gilt ab dem nächsten Mal")))
        schweigen()

    def abschalten(_e: Any = None) -> None:
        an_setzen(state, False)
        page.show_dialog(
            ft.SnackBar(ft.Text("Keine Vorschläge mehr — wieder an: Einstellungen → Übungen"))
        )
        zeichnen()

    def zeichnen() -> None:
        stufe, offen = liste()
        huelle.visible = bool(offen)
        if offen and regel is not None and stufe is not None:
            kuerzer = regel.richtung(stufe) < 0
            spalte.controls = [
                titel("Vorschlag aus dem Plan"),
                ft.Text(
                    f"Du hast {stufe} gewählt. Der Plan schlägt "
                    f"{'ab ' + str(regel.ab) if kuerzer else 'bis ' + str(regel.bis)} "
                    f"ein {'kürzeres' if kuerzer else 'längeres'} Ziel vor:"
                ),
                *(
                    ft.Text(
                        f"{v.name}: {wert_text(katalog.get(v.uebung_id), v.feld, v.alt)} → "
                        f"{wert_text(katalog.get(v.uebung_id), v.feld, v.neu)}",
                        weight=ft.FontWeight.W_600,
                        data=("vorschlag_zeile", v.item_id),
                    )
                    for v in offen
                ),
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.OutlinedButton(
                            "So lassen",
                            on_click=lambda _e=None: schweigen(),
                            expand=True,
                            data="vorschlag_lassen",
                        ),
                        ft.FilledButton(
                            "Übernehmen",
                            on_click=uebernehmen,
                            expand=True,
                            data="vorschlag_uebernehmen",
                        ),
                    ],
                ),
                hinweis(
                    f"Die Regel gehört zum Plan ({regel.text()}). Nichts ändert sich von selbst."
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.TextButton(
                            "Keine Vorschläge mehr", on_click=abschalten, data="vorschlag_aus"
                        )
                    ],
                ),
            ]
        else:
            spalte.controls = []
        with contextlib.suppress(Exception):
            huelle.update()

    zeichnen()
    return VorschlagKarte(huelle, zeichnen)


__all__ = ["VorschlagKarte", "an", "an_setzen", "vorschlag_karte", "wert_text"]
