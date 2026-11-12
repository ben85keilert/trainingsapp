"""Profile — Route `/einstellungen/profile`.

Das aktive Profil wählen (der Kreis vor dem Namen — bis 11.11.2026 lag die Wahl vorn auf
der Hauptseite der Einstellungen), anlegen, umbenennen, löschen (mit Rückfrage). Gelöschte
Profile werden
ausgeblendet (`SubjectRepo.loeschen`) — ihre Einträge und Messungen bleiben
auf dem Gerät, wie überall in der App. Das letzte Profil bleibt.

Ein geänderter Name gilt auch, wenn man einfach zurückgeht (Ben, 16.10.2026,
`components/zurueck.py`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

import flet as ft

from trainingsapp.config import ist_aktiv
from trainingsapp.core.models import Subject
from trainingsapp.ui.components.dialoge import Nachher, obersten_schliessen
from trainingsapp.ui.components.karte import hinweis, info_knopf, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState

INFO_MD = """\
- **Der Kreis** vor dem Namen wählt das aktive Profil. Beim Start wird das zuletzt aktive
  geladen. Jedes Profil hat seine Pläne, Einträge, Messungen und seine Darstellung.
- **Namen ändern:** ✓, Eingabe oder Zurück speichert.
- **Löschen** blendet ein Profil aus — das letzte bleibt.
- Läuft gerade eine Messung, bleibt sie bei dem Profil, mit dem sie begann.
"""


def _messung_laeuft(state: AppState) -> bool:
    """Läuft gerade eine HRV-Aufnahme oder ein Ausdauertraining?"""
    messlauf = state.messlauf
    if messlauf is not None and messlauf.aufnahme is not None:
        return True
    ausdauer = state.ausdauer
    return ausdauer is not None and not ausdauer.fertig


def profile_view(page: ft.Page, state: AppState) -> ft.View:
    liste = ft.Column(spacing=10)
    neuer_name = ft.TextField(
        label="Neues Profil", hint_text="wird gleich aktiv", dense=True, expand=True
    )
    #: Die Namensfelder der Liste, wie sie gerade stehen — für „Zurück speichert“
    felder: dict[str, tuple[Subject, ft.TextField]] = {}

    def zeichnen() -> None:
        profile = state.profile.alle()
        felder.clear()
        liste.controls = [zeile(p, len(profile) > 1) for p in profile]
        with contextlib.suppress(Exception):
            liste.update()

    def umbenenner(profil: Subject, feld: ft.TextField) -> Callable[[], None]:
        def handler() -> None:
            name = (feld.value or "").strip()
            if not name:
                feld.error = "Ein Name muss sein."
                feld.update()
                return
            feld.error = None
            state.profil_umbenennen_id(profil.id, name)
            page.show_dialog(ft.SnackBar(ft.Text(f"Umbenannt in „{name}“")))
            zeichnen()

        return handler

    def wechsler(profil: Subject) -> Callable[[], None]:
        def handler() -> None:
            if profil.id == state.profil.id:
                return
            namen_sichern()  # Geändertes gilt, bevor alles neu gebaut wird
            vorher = state.profil
            state.profil_wechseln(profil.id)
            if _messung_laeuft(state):
                # Messlauf und Ausdauerlauf haben sich ihr Startprofil gemerkt
                page.show_dialog(
                    ft.SnackBar(ft.Text(f"Die laufende Messung bleibt bei „{vorher.name}“."))
                )
            zeichnen()
            state.neu_zeichnen()  # jedes Profil bringt sein Farbprofil mit

        return handler

    def loeschen(profil: Subject) -> Callable[[], None]:
        nachher = Nachher()  # neu zeichnen erst, wenn der Dialog zu ist (`components/dialoge.py`)

        def ausfuehren() -> None:
            try:
                state.profil_loeschen(profil.id)
            except ValueError as fehler:
                obersten_schliessen(page)
                page.show_dialog(ft.SnackBar(ft.Text(str(fehler))))
                return
            nachher.danach(zeichnen)
            nachher.danach(state.neu_zeichnen)  # war es aktiv, gilt jetzt ein anderes Farbprofil
            obersten_schliessen(page)
            page.show_dialog(ft.SnackBar(ft.Text(f"Profil „{profil.name}“ gelöscht")))

        def fragen() -> None:
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    on_dismiss=nachher.bei_schliessen,
                    title=ft.Text(f"„{profil.name}“ löschen?"),
                    content=ft.Text(
                        "Das Profil verschwindet aus der App, mit seinen Plänen, "
                        "Einträgen und Messungen. Die Daten bleiben auf dem Gerät "
                        "gespeichert, werden aber nicht mehr angezeigt."
                    ),
                    actions=[
                        ft.TextButton("Abbrechen", on_click=lambda: obersten_schliessen(page)),
                        ft.FilledButton("Löschen", on_click=ausfuehren),
                    ],
                )
            )

        return fragen

    def zeile(profil: Subject, loeschbar: bool) -> ft.Control:
        feld = ft.TextField(value=profil.name, dense=True, expand=True)
        felder[profil.id] = (profil, feld)
        feld.on_submit = lambda _: umbenenner(profil, feld)()
        aktiv = profil.id == state.profil.id
        return ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(
                    ft.Icons.RADIO_BUTTON_CHECKED if aktiv else ft.Icons.RADIO_BUTTON_UNCHECKED,
                    tooltip="Aktives Profil" if aktiv else "Zu diesem Profil wechseln",
                    icon_color=ft.Colors.PRIMARY if aktiv else None,
                    on_click=wechsler(profil),
                    data=profil.id,
                ),
                feld,
                ft.IconButton(
                    ft.Icons.CHECK, tooltip="Namen speichern", on_click=umbenenner(profil, feld)
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="Profil löschen" if loeschbar else "Das letzte Profil bleibt",
                    disabled=not loeschbar,
                    on_click=loeschen(profil),
                ),
            ],
        )

    def anlegen() -> None:
        name = (neuer_name.value or "").strip()
        if not name:
            neuer_name.error = "Ein Name muss sein."
            neuer_name.update()
            return
        neuer_name.error = None
        state.profil_anlegen(name)
        neuer_name.value = ""
        page.show_dialog(ft.SnackBar(ft.Text(f"„{name}“ angelegt und aktiv")))
        zeichnen()
        state.neu_zeichnen()  # das neue Profil beginnt mit der Vorgabe-Darstellung
        with contextlib.suppress(Exception):
            neuer_name.update()

    zeichnen()
    teile: list[ft.Control] = [
        karte(
            titel("Profile", info_knopf(page, "Profile", INFO_MD)),
            liste,
        ),
        karte(
            titel("Neues Profil"),
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    neuer_name,
                    ft.FilledTonalButton("Anlegen", icon=ft.Icons.PERSON_ADD, on_click=anlegen),
                ],
            ),
        ),
    ]
    if ist_aktiv("profil_sperre"):
        # Praxis-Edition: Profile mehrerer Personen auf einem Gerät — gesperrt per PIN
        teile.append(hinweis("Profilwechsel ist durch PIN geschützt."))

    def geaendert() -> list[tuple[Subject, ft.TextField]]:
        return [
            (profil, feld)
            for profil, feld in felder.values()
            if (feld.value or "").strip() != profil.name
        ]

    def namen_sichern() -> str | None:
        """Geänderte Namen übernehmen — ein leerer bleibt stehen und wird gemeldet."""
        for profil, feld in geaendert():
            name = (feld.value or "").strip()
            if not name:
                feld.error = "Ein Name muss sein."
                page.update()
                return "Ein Profil braucht einen Namen."
            state.profil_umbenennen_id(profil.id, name)
        return None

    return zurueck_speichert(
        page,
        ft.View(
            route="/einstellungen/profile",
            appbar=ft.AppBar(title=ft.Text("Profile")),
            scroll=ft.ScrollMode.AUTO,
            padding=16,
            controls=[sicher(ft.Column(spacing=14, controls=teile), expand=False)],
        ),
        geaendert=lambda: bool(geaendert()),
        speichern=namen_sichern,
        meldung="Namen gespeichert",
    )


__all__ = ["profile_view"]
