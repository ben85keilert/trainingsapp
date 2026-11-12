"""„In ein Paket verschieben / kopieren“ im Editor der Übung (Ben, 12.11.2026).

„Für Wechsel in anderes Paket (Eigene und co) noch Bereich mit dazu … Verschieben oder Kopie.
Zum Pakete erstellen ist das für mich ganz praktisch.“ Der Bereich steht im Reiter „Übung“
unter „Ordnen“:

- **Kopieren** geht mit jeder Übung: eine eigene Übung mit neuer ID (wie „Kopie anlegen“ auf
  der Übungsseite) — nach „Eigene“ oder gleich in ein eigenes Paket (`own_package`, U4). Kein
  Paket-Update ändert die Kopie.
- **Verschieben** geht mit **eigenen** Übungen: zwischen „Eigene“ (in keinem eigenen Paket)
  und den eigenen Paketen — die Übung selbst bleibt, wie sie ist, nur die Auswahl der Pakete
  ändert sich. Eine **Paketübung** gehört ihrem Paket (`exercise.package_id`): Sie lässt sich
  kopieren, nicht herauslösen — mit derselben ID bliebe sie beim Empfänger eines eigenen
  Pakets „aus einem anderen Paket“ und käme nicht an.

Die Rechnung (`ziele`, `kopieren`, `verschieben`) kennt kein flet-Control; gezeichnet wird in
`paket_bereich`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, new_id
from trainingsapp.ui.components.dialoge import Nachher, schliessen

#: Das Ziel „in keinem eigenen Paket“
EIGENE = ""
EIGENE_NAME = "Eigene"


@dataclass(frozen=True)
class Paketziel:
    """Wohin eine Übung kann: „Eigene“ (``id`` leer) oder ein eigenes Paket."""

    id: str
    name: str
    #: Die Übung steht schon dort (beim Verschieben ausgegraut)
    dabei: bool = False


def ziele(state: Any, uebung: Exercise) -> list[Paketziel]:
    """„Eigene“ und die eigenen Pakete — mit dem Vermerk, wo die Übung schon steht. In
    „Eigene“ steht eine eigene Übung, die in keinem eigenen Paket ist."""
    pakete = state.eigene_pakete.alle()
    in_paketen = [p for p in pakete if uebung.id in p.uebungen]
    eigen = uebung.package_id is None
    return [
        Paketziel(EIGENE, EIGENE_NAME, dabei=eigen and not in_paketen),
        *(Paketziel(p.id, p.name or "Paket ohne Namen", dabei=p in in_paketen) for p in pakete),
    ]


def gehoert_zu(state: Any, uebung: Exercise) -> str:
    """„Standard“, „Eigene“ oder die eigenen Pakete, in denen die Übung steht."""
    namen = [z.name for z in ziele(state, uebung) if z.dabei and z.id]
    if uebung.package_id:
        paket = state.pakete.laden(uebung.package_id)
        namen.insert(0, paket.name if paket is not None else "einem Paket")
    return ", ".join(namen) or EIGENE_NAME


def kopieren(state: Any, uebung: Exercise, ziel: str) -> Exercise:
    """Eine eigene Kopie (neue ID, ohne Herkunft) — mit ``ziel`` gleich im eigenen Paket."""
    kopie = replace(
        uebung,
        id=new_id(),
        name=f"{uebung.name} (Kopie)",
        is_builtin=False,
        package_id=None,
        media=[replace(m, id=new_id()) for m in uebung.media],
        typen=list(uebung.typen),
        regionen=list(uebung.regionen),
        archived=False,
    )
    state.uebungen.speichern(kopie)
    if ziel:
        paket = state.eigene_pakete.laden(ziel)
        if paket is not None:
            paket.uebungen = [*paket.uebungen, kopie.id]
            state.eigene_pakete.speichern(paket)
    return kopie


def verschieben(state: Any, uebung: Exercise, ziel: str) -> bool:
    """Eine **eigene** Übung steht danach nur noch in ``ziel`` — „Eigene“: in keinem eigenen
    Paket. ``False``: eine Paketübung, nichts geändert."""
    if uebung.package_id is not None:
        return False
    for paket in state.eigene_pakete.alle():
        hat = uebung.id in paket.uebungen
        soll = paket.id == ziel
        if hat == soll:
            continue
        paket.uebungen = (
            [*paket.uebungen, uebung.id] if soll else [i for i in paket.uebungen if i != uebung.id]
        )
        state.eigene_pakete.speichern(paket)
    return True


def paket_bereich(
    page: Any,
    state: Any,
    uebung: Exercise,
    *,
    sichern: Callable[[], str | None],
    verlassen: Callable[[], None],
) -> list[ft.Control]:
    """Die Zeilen unter „PAKET“: wozu die Übung gehört und „In ein Paket [verschieben]
    [kopieren]“. ``sichern`` speichert das Formular vorher (``None`` = gespeichert) — kopiert
    und verschoben wird der gespeicherte Stand; ``verlassen`` räumt auf, bevor es zur Kopie
    geht."""
    zugehoerig = ft.Text(f"Gehört zu: {gehoert_zu(state, uebung)}", size=13, data="gehoert_zu")
    paketuebung = uebung.package_id is not None

    def frisch() -> Exercise:
        return state.uebungen.laden(uebung.id) or uebung

    def waehlen(titel: str, hinweis: str, tun: Callable[[str], None], sperren: bool) -> None:
        nachher = Nachher()
        dialog: ft.AlertDialog

        def nehmen(ziel: str) -> Callable[[], None]:
            def handler() -> None:
                nachher.danach(lambda: tun(ziel))
                schliessen(dialog)

            return handler

        dialog = ft.AlertDialog(
            on_dismiss=nachher.bei_schliessen,
            title=ft.Text(titel),
            content=ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text(hinweis, size=12, opacity=0.75),
                    *(
                        ft.ListTile(
                            leading=ft.Icon(
                                ft.Icons.INVENTORY_2_OUTLINED if z.id else ft.Icons.PERSON_OUTLINE
                            ),
                            title=ft.Text(z.name),
                            trailing=ft.Text("steht hier", size=12)
                            if sperren and z.dabei
                            else None,
                            disabled=sperren and z.dabei,
                            data=f"paketziel_{z.id}",
                            on_click=None if sperren and z.dabei else nehmen(z.id),
                        )
                        for z in ziele(state, frisch())
                    ),
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
        )
        page.show_dialog(dialog)

    def kopie_anlegen(ziel: str) -> None:
        kopie = kopieren(state, frisch(), ziel)
        wo = next((z.name for z in ziele(state, kopie) if z.id == ziel), EIGENE_NAME)
        page.show_dialog(ft.SnackBar(ft.Text(f"Kopie in „{wo}“ angelegt. Jetzt anpassen.")))
        verlassen()
        page.run_task(page.push_route, f"/uebung/{kopie.id}/bearbeiten")

    def umziehen(ziel: str) -> None:
        verschieben(state, frisch(), ziel)
        wo = next((z.name for z in ziele(state, frisch()) if z.id == ziel), EIGENE_NAME)
        zugehoerig.value = f"Gehört zu: {gehoert_zu(state, frisch())}"
        page.show_dialog(ft.SnackBar(ft.Text(f"„{uebung.name}“ steht jetzt in „{wo}“")))
        page.update()

    def kopieren_fragen() -> None:
        if sichern() is not None:
            return
        waehlen(
            "Kopie in ein Paket",
            "Die Kopie ist eine eigene Übung mit eigenem Verlauf — kein Paket-Update ändert sie.",
            kopie_anlegen,
            sperren=False,
        )

    def verschieben_fragen() -> None:
        if sichern() is not None:
            return
        waehlen(
            "In ein Paket verschieben",
            "Die Übung bleibt, wie sie ist, mit Verlauf und Plänen. Sie steht danach nur noch "
            "im gewählten Paket.",
            umziehen,
            sperren=True,
        )

    return [
        zugehoerig,
        ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("In ein Paket", weight=ft.FontWeight.W_600),
                ft.OutlinedButton(
                    "verschieben",
                    data="paket_verschieben",
                    disabled=paketuebung,
                    on_click=verschieben_fragen,
                ),
                ft.OutlinedButton("kopieren", data="paket_kopieren", on_click=kopieren_fragen),
            ],
        ),
        ft.Text(
            "Eine Paketübung gehört ihrem Paket — sie lässt sich kopieren, nicht verschieben."
            if paketuebung
            else "Verschieben ändert nur, in welchem eigenen Paket die Übung steht.",
            size=12,
            opacity=0.7,
        ),
    ]


__all__ = [
    "EIGENE",
    "Paketziel",
    "gehoert_zu",
    "kopieren",
    "paket_bereich",
    "verschieben",
    "ziele",
]
