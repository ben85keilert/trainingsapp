"""Eine Kachel im Verlauf — Route `/verlauf/<kachel_id>`.

Die Kurve zeigt **Tagessummen**: Wer an einem Tag dreimal 50 Liegestütze
gemacht hat, sieht einen Punkt bei 150. Varianten einer Übung (gleiche
Kachel) laufen zusammen; die Auswahl „Variante“ zeigt eine einzeln. Darunter
die Tage als Liste, auch die, an denen nur abgehakt wurde.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import flet as ft

from trainingsapp.core.models import SessionEntry
from trainingsapp.core.tagesbilanz import kachel, kacheln, mengen
from trainingsapp.core.verlauf import MODUS_NUMMER, MODUS_ZEIT, tages_punkte, tagessummen
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.verlauf import WOCHENTAGE, kachel_von, liniendiagramm

#: Auswahlwert „alle Varianten zusammen"
ALLE = "alle"


def verlauf_kachel_view(page: ft.Page, state: AppState, kachel_id: str) -> ft.View:
    katalog = {u.id: u for u in state.uebungen.alle(mit_geloeschten=True)}
    namen = {k: u.name for k, u in katalog.items()}
    mitglieder = [u for u in katalog.values() if kachel(u, u.id) == kachel_id]
    original = katalog.get(kachel_id)
    eintraege = state.sitzungen.eintraege_zwischen(
        state.profil.id, None, state.heute(), exercise_ids=[u.id for u in mitglieder]
    )

    # -- Auswahl: Variante, Feld, X-Achse ------------------------------------------

    mit_daten = list(dict.fromkeys(e.exercise_id for _, e in eintraege))
    variante = state.verlauf_variante if state.verlauf_variante in mit_daten else None
    gefiltert = [(t, e) for t, e in eintraege if variante is None or e.exercise_id == variante]

    felder: dict[str, str] = {}  # key → Beschriftung, in der Reihenfolge des Auftretens
    einheiten: dict[str, str] = {}
    for _, e in gefiltert:
        for key in mengen(e.spec_snapshot, e.result):
            f = e.spec_snapshot.field_by_key(key) if e.spec_snapshot else None
            felder.setdefault(key, f.label if f else key)
            einheiten.setdefault(key, (f.unit or "") if f else "")
    feld = state.verlauf_feld if state.verlauf_feld in felder else next(iter(felder), None)

    def variante_waehlen(e: ft.Event[ft.Dropdown]) -> None:
        state.verlauf_variante = None if e.control.value in (None, ALLE) else e.control.value
        state.neu_zeichnen()

    def feld_waehlen(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.verlauf_feld = e.control.selected[0]
            state.neu_zeichnen()

    def modus_wechseln(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            state.verlauf_modus = e.control.selected[0]
            state.neu_zeichnen()

    def oeffner(pfad: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(pfad)

        return handler

    inhalt: list[ft.Control] = []
    if len(mit_daten) > 1:
        inhalt.append(
            ft.Row(
                controls=[
                    ft.Dropdown(
                        label="Variante",
                        value=variante or ALLE,
                        options=[
                            ft.DropdownOption(key=ALLE, text="Alle Varianten zusammen"),
                            *[ft.DropdownOption(key=x, text=namen.get(x, "?")) for x in mit_daten],
                        ],
                        on_select=variante_waehlen,
                        dense=True,
                        expand=True,
                    )
                ]
            )
        )
    if len(felder) > 1:
        inhalt.append(
            ft.SegmentedButton(
                selected=[feld] if feld else [],
                segments=[ft.Segment(value=k, label=ft.Text(t)) for k, t in felder.items()],
                on_change=feld_waehlen,
            )
        )

    # -- Kurve der Tagessummen --------------------------------------------------

    if feld is not None:
        werte = tagessummen(gefiltert, feld)
        punkte = tages_punkte(werte, state.verlauf_modus)
        einheit = einheiten.get(feld, "")
        inhalt.extend(
            [
                ft.Text(
                    f"{felder[feld]} je Tag (Summe{', ' + einheit if einheit else ''})",
                    size=13,
                    weight=ft.FontWeight.W_600,
                ),
                liniendiagramm(punkte, einheit, state.verlauf_modus),
                ft.SegmentedButton(
                    selected=[state.verlauf_modus],
                    segments=[
                        ft.Segment(value=MODUS_NUMMER, label=ft.Text("Trainingstag Nr.")),
                        ft.Segment(value=MODUS_ZEIT, label=ft.Text("Zeit (Tage)")),
                    ],
                    on_change=modus_wechseln,
                ),
            ]
        )
    else:
        inhalt.append(
            ft.Text(
                "Noch keine Werte zum Zeichnen — bisher nur abgehakt. Trag Wiederholungen "
                "oder Zeiten ein, dann entsteht hier die Kurve.",
                opacity=0.7,
            )
        )

    # -- Die Tage als Liste --------------------------------------------------------

    nach_tag: dict[date, list[SessionEntry]] = {}
    for t, e in gefiltert:
        nach_tag.setdefault(t, []).append(e)
    tage: list[ft.Control] = []
    for t in sorted(nach_tag, reverse=True):
        for k in kacheln(nach_tag[t], kachel_von(katalog)):
            untertitel: list[ft.Control] = [ft.Text(k.zusammenfassung(), size=12)]
            if aufschluesselung := k.aufschluesselung(namen):
                untertitel.append(ft.Text(aufschluesselung, size=11, opacity=0.6))
            tage.append(
                ft.ListTile(
                    leading=ft.Icon(
                        ft.Icons.CHECK_CIRCLE if k.leistungen else ft.Icons.CHECK_CIRCLE_OUTLINE,
                        color=ft.Colors.PRIMARY if k.leistungen else None,
                        opacity=1 if k.leistungen else 0.55,
                    ),
                    title=ft.Text(f"{WOCHENTAGE[t.weekday()]}, {t:%d.%m.%Y}"),
                    subtitle=ft.Column(spacing=0, controls=untertitel),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.4),
                    dense=True,
                    on_click=oeffner(f"/tag/{t.isoformat()}"),
                )
            )
    inhalt.append(ft.Text("TAGE", size=11, weight=ft.FontWeight.BOLD, opacity=0.6))
    inhalt.extend(tage or [ft.Text("Noch keine Einträge.", opacity=0.6)])

    varianten = [u.name for u in mitglieder if u.id != kachel_id]
    if varianten:
        inhalt.insert(
            0,
            ft.Text("Mit Varianten: " + ", ".join(varianten), size=12, opacity=0.7),
        )

    return ft.View(
        route=f"/verlauf/{kachel_id}",
        appbar=ft.AppBar(title=ft.Text(original.name if original else "Verlauf")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(ft.Column(spacing=12, controls=inhalt), expand=False)],
    )


__all__ = ["verlauf_kachel_view"]
