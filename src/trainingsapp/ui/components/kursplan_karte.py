"""Die Sammelkarte „Das ändert sich an deinem Plan“ (Ben, 16.11.2026,
`docs/plan_kurs_ablauf.md` §11.5, Skizzen K2 und K3).

Ein Kurs mit Kursplan baut mit der Person **einen** Plan, der über die Kapitel wächst. Was ein
Kapitel daran ändern will, steht in dieser Karte — je Änderung eine Zeile
(`core.kursplan.Aenderung`), und **nichts ändert sich ohne Tipp**:

- **neu** — Zeile mit Haken (an). Abwählen lässt sie weg; hängt eine Zeile an einer anderen
  (das Ziel einer Übung, die erst dazukommt: `Aenderung.braucht`), geht sie mit aus.
- **weicht ab** — die abgesetzte Karte „Dein Plan weicht ab“ mit dem Satz der Änderung und
  zwei Knöpfen: „‹Kurswert› übernehmen“ und „‹eigener Wert› lassen“. Vorgabe ist **lassen**.
- **Anker fehlt** — Hinweiszeile ohne Haken: Das Neue kommt ans Ende, die Zeile sagt, warum.
- **entfällt** — Hinweiszeile: Es gibt nichts mehr, woran es hinge.
- **offen** — ausgegraut, ohne Haken: Die Wahl oder der Test dazu fehlt noch.
- **übernommen** — keine Zeile, nur unten „n schon übernommen“.

„Übernehmen“ meldet, was gewählt ist — die Zeilen mit Haken (und die ohne Anker), die
Abweichungen, bei denen der Vorschlag gelten soll, und die, bei denen der eigene Wert bleibt.
„Später“ klappt die Karte zu; gespeichert wird dabei nichts, beim nächsten Öffnen des Kapitels
steht sie wieder da.

Hier wird nur gezeichnet: Die Zeilen kommen fertig aus `KursRepo.plan_aenderungen`, das
Anwenden macht `KursRepo.plan_uebernehmen`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import flet as ft

from trainingsapp.core.kursplan import (
    ANKER_FEHLT,
    ENTFAELLT,
    NEU,
    OFFEN,
    UEBERNOMMEN,
    WEICHT_AB,
    Aenderung,
)
from trainingsapp.ui.components.karte import hinweis, karte

#: „Übernehmen“: ``(gewählt, trotz, lassen)`` — die IDs wie in `KursRepo.plan_uebernehmen`
Uebernehmen = Callable[[set[str], set[str], set[str]], Any]

#: Breite der Spalte vor dem Text — ein Haken oder ein Symbol, damit die Texte fluchten
_VORN = 40


@dataclass
class KursplanKarte:
    """Die Karte und ``zeigen`` zum Neuaufbau mit anderen Zeilen — ändert die Person ihre
    Auswahl im Kapitel, sind es andere Änderungen (ihre IDs hängen an der Wahl)."""

    control: ft.Control
    zeigen: Callable[[Sequence[Aenderung]], None]


def kursplan_karte(
    zeilen: Sequence[Aenderung], *, planname: str, uebernehmen: Uebernehmen
) -> KursplanKarte:
    """Die Sammelkarte zu ``zeilen``. ``planname``: wie der Kursplan heißt (Unterzeile);
    ``uebernehmen`` bekommt beim Tipp auf „Übernehmen“ die IDs der gewählten Zeilen, die der
    Abweichungen mit „übernehmen“ und die der Abweichungen mit „lassen“."""
    spalte = ft.Column(spacing=10, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    huelle = ft.Container(data="kursplan_karte", content=karte(spalte))
    #: der Stand der Karte — mit jedem `zeigen` neu
    lage: dict[str, Any] = {"zeilen": [], "an": {}, "trotz": {}, "spaeter": False, "knopf": None}
    haken: dict[str, ft.Checkbox] = {}
    #: der Text neben jedem Haken — blass, solange die Zeile an einer abgewählten hängt
    schrift: dict[str, ft.Container] = {}

    def neu_malen() -> None:
        with contextlib.suppress(Exception):
            huelle.update()

    def grund(z: Aenderung) -> Aenderung | None:
        """Die Zeile, ohne die ``z`` nichts bewirkt — ``None``, wenn es keine (mehr) gibt."""
        if not z.braucht or z.braucht == z.id:
            return None
        return next((a for a in lage["zeilen"] if a.id == z.braucht), None)

    def gilt(z: Aenderung) -> bool:
        """Wird die Zeile mit „Übernehmen“ angewandt? Eine, die an einer anderen hängt, nur
        mit ihr."""
        if z.stand == NEU:
            selbst = bool(lage["an"].get(z.id, True))
        elif z.stand == WEICHT_AB:
            selbst = bool(lage["trotz"].get(z.id, False))
        else:
            selbst = z.stand == ANKER_FEHLT
        vorher = grund(z)
        return selbst and (vorher is None or gilt(vorher))

    def grund_fehlt(z: Aenderung) -> bool:
        vorher = grund(z)
        return vorher is not None and not gilt(vorher)

    def gewaehlt() -> set[str]:
        return {z.id for z in lage["zeilen"] if z.anwendbar and gilt(z)}

    def trotz() -> set[str]:
        return {z.id for z in lage["zeilen"] if z.stand == WEICHT_AB and lage["trotz"].get(z.id)}

    def lassen() -> set[str]:
        return {
            z.id for z in lage["zeilen"] if z.stand == WEICHT_AB and not lage["trotz"].get(z.id)
        }

    def stand_zeigen() -> None:
        """Haken und „Übernehmen“ nach dem Stand der Karte — ohne Neuaufbau."""
        for z in lage["zeilen"]:
            box = haken.get(z.id)
            if box is not None:
                box.value = gilt(z)
                box.disabled = grund_fehlt(z)
                schrift[z.id].opacity = 0.5 if box.disabled else 1.0
        knopf = lage["knopf"]
        if knopf is not None:
            # ohne gewählte Zeile und ohne Abweichung täte der Tipp nichts
            knopf.disabled = not (gewaehlt() or lassen())

    # -- Zeilen ------------------------------------------------------------------------------

    def texte(z: Aenderung, oben: float = 1.0, unten: float = 0.7) -> ft.Column:
        return ft.Column(
            spacing=2,
            tight=True,
            controls=[
                ft.Text(z.titel, size=15, weight=ft.FontWeight.W_600, opacity=oben),
                *([ft.Text(z.unter, size=12, opacity=unten)] if z.unter else []),
            ],
        )

    def zeile_neu(z: Aenderung) -> ft.Control:
        def umschalten(_e: Any = None) -> None:
            if grund_fehlt(z):
                return
            lage["an"][z.id] = not lage["an"].get(z.id, True)
            stand_zeigen()
            neu_malen()

        box = ft.Checkbox(value=True, on_change=umschalten, data=("kursplan_zeile", z.id))
        haken[z.id] = box
        # der Text schaltet mit um, wie das Etikett eines Hakens
        schrift[z.id] = ft.Container(expand=True, on_click=umschalten, content=texte(z))
        return ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(width=_VORN, alignment=ft.Alignment.CENTER_LEFT, content=box),
                schrift[z.id],
            ],
        )

    def zeile_hinweis(z: Aenderung, symbol: ft.IconData, oben: float = 1.0) -> ft.Control:
        return ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            data=("kursplan_hinweis", z.id),
            controls=[
                ft.Container(
                    width=_VORN,
                    alignment=ft.Alignment.CENTER_LEFT,
                    padding=ft.Padding.only(left=8),
                    content=ft.Icon(symbol, size=22, opacity=0.8 * oben),
                ),
                ft.Container(expand=True, content=texte(z, oben)),
            ],
        )

    def abweichung(z: Aenderung) -> ft.Control:
        """„Dein Plan weicht ab“ — zwei Knöpfe, einer ist gewählt (Vorgabe: lassen)."""
        farbe = ft.Colors.ON_TERTIARY_CONTAINER
        reihe = ft.Row(wrap=True, spacing=8, run_spacing=8)
        # schmaler als die Vorgabe: So stehen „Planke übernehmen“ und „Plan so lassen“ bei
        # Handybreite nebeneinander (Web-Foto 16.11.2026); lange Werte brechen weiter um
        innen = ft.Padding.symmetric(horizontal=14)

        def wahlknopf(text: str, an: bool, wert: bool, kennung: str) -> ft.Control:
            def tippen(_e: Any = None) -> None:
                lage["trotz"][z.id] = wert
                knoepfe()
                stand_zeigen()
                neu_malen()

            if an:  # der gewählte ist gefüllt und trägt den Haken
                return ft.FilledButton(
                    text,
                    icon=ft.Icons.CHECK,
                    on_click=tippen,
                    data=(kennung, z.id),
                    style=ft.ButtonStyle(
                        bgcolor=farbe, color=ft.Colors.TERTIARY_CONTAINER, padding=innen
                    ),
                )
            return ft.OutlinedButton(
                text,
                on_click=tippen,
                data=(kennung, z.id),
                style=ft.ButtonStyle(color=farbe, side=ft.BorderSide(1.5, farbe), padding=innen),
            )

        def knoepfe() -> None:
            nimmt = bool(lage["trotz"].get(z.id, False))
            reihe.controls = [
                wahlknopf(f"{z.kurs} übernehmen", nimmt, True, "kursplan_trotz"),
                wahlknopf(f"{z.eigen} lassen", not nimmt, False, "kursplan_lassen"),
            ]

        knoepfe()
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            border_radius=12,
            bgcolor=ft.Colors.TERTIARY_CONTAINER,
            data=("kursplan_abweichung", z.id),
            content=ft.Column(
                spacing=8,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.INFO_OUTLINE, size=20, color=farbe),
                            ft.Text(
                                "Dein Plan weicht ab",
                                size=15,
                                weight=ft.FontWeight.W_600,
                                color=farbe,
                                expand=True,
                            ),
                        ],
                    ),
                    ft.Text(z.titel, size=14, color=farbe),
                    reihe,
                ],
            ),
        )

    # -- Aufbau ------------------------------------------------------------------------------

    def unterzeile() -> ft.Text:
        return ft.Text(f"{planname} · dein Kursplan", size=12, opacity=0.7)

    def kopf() -> ft.Control:
        return ft.Column(
            spacing=2,
            tight=True,
            controls=[
                ft.Text("Das ändert sich an deinem Plan", size=17, weight=ft.FontWeight.W_600),
                unterzeile(),
            ],
        )

    def spaeter(_e: Any = None) -> None:
        lage["spaeter"] = True
        bauen()
        neu_malen()

    def wieder(_e: Any = None) -> None:
        lage["spaeter"] = False
        bauen()
        neu_malen()

    def druecken(_e: Any = None) -> Any:
        if not (gewaehlt() or lassen()):
            return None
        return uebernehmen(gewaehlt(), trotz(), lassen())

    def bauen() -> None:
        alle: list[Aenderung] = lage["zeilen"]
        haken.clear()
        schrift.clear()
        lage["knopf"] = None
        anbieten = [z for z in alle if z.anwendbar]
        sichtbar = [z for z in alle if z.stand != UEBERNOMMEN]
        schon = sum(1 for z in alle if z.stand == UEBERNOMMEN)
        if not sichtbar:
            # nichts anzubieten, nichts offen: nur der eine Satz. Er sagt nicht, der Plan sei
            # „auf dem Stand des Kapitels“ — nach „lassen“ (eine Übung aus dem Plan genommen,
            # ein eigener Wert) ist er das nicht, offen ist trotzdem nichts mehr
            spalte.controls = [
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    data="kursplan_stand",
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=ft.Colors.PRIMARY),
                        ft.Column(
                            spacing=2,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text("Aus diesem Kapitel ist nichts mehr offen."),
                                unterzeile(),
                            ],
                        ),
                    ],
                )
            ]
            return
        if lage["spaeter"]:
            spalte.controls = [
                kopf(),
                hinweis("Später — die Änderungen warten hier, bis du sie übernimmst."),
                ft.Row(
                    controls=[
                        ft.TextButton(
                            "Wieder zeigen",
                            icon=ft.Icons.EXPAND_MORE,
                            on_click=wieder,
                            data="kursplan_zeigen",
                        )
                    ]
                ),
            ]
            return
        inhalt: list[ft.Control] = [kopf()]
        for z in sichtbar:
            if z.stand == NEU:
                inhalt.append(zeile_neu(z))
            elif z.stand == WEICHT_AB:
                inhalt.append(abweichung(z))
            elif z.stand == ANKER_FEHLT:
                inhalt.append(zeile_hinweis(z, ft.Icons.ARROW_DOWNWARD))
            elif z.stand == ENTFAELLT:
                inhalt.append(zeile_hinweis(z, ft.Icons.BLOCK, 0.85))
            elif z.stand == OFFEN:
                inhalt.append(zeile_hinweis(z, ft.Icons.PENDING_OUTLINED, 0.5))
        if anbieten:
            # jedes Mal ein neuer Knopf: Ein Control, das den Elternteil wechselt, nimmt in
            # Flet nicht immer wieder Eingaben an
            lage["knopf"] = ft.FilledButton(
                "Übernehmen",
                icon=ft.Icons.CHECK,
                expand=True,
                on_click=druecken,
                data="kursplan_uebernehmen",
            )
            inhalt.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        lage["knopf"],
                        ft.TextButton("Später", on_click=spaeter, data="kursplan_spaeter"),
                    ],
                )
            )
            inhalt.append(
                hinweis(
                    "Was du selbst geändert hast, bleibt — außer du übernimmst den Vorschlag."
                    if any(z.stand == WEICHT_AB for z in anbieten)
                    else "Nichts ändert sich ohne deinen Tipp. Einzelnes kannst du abwählen."
                )
            )
        if schon:
            inhalt.append(
                ft.Text(f"{schon} schon übernommen", size=12, opacity=0.6, data="kursplan_schon")
            )
        spalte.controls = inhalt
        stand_zeigen()

    def zeigen(neue: Sequence[Aenderung]) -> None:
        lage.update(zeilen=list(neue), an={}, trotz={}, spaeter=False)
        bauen()
        neu_malen()

    lage["zeilen"] = list(zeilen)
    bauen()
    return KursplanKarte(control=huelle, zeigen=zeigen)


__all__ = ["KursplanKarte", "Uebernehmen", "kursplan_karte"]
