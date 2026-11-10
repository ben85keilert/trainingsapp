"""Die Timer-Zeile und der Editor im Fenster (Ben, 10.11.2026, `docs/plan_timer_zuordnen.md`
§2/§3, Skizzen Z1/Z2): **eine Zeile überall** — `Name ▾ · Gesamtzeit · Herkunft · ✎` — in „Im
Plan einstellen“ und im Uhrenplan.

- Tipp auf den Namen öffnet das **Uhr-Blatt** (`components/uhr_blatt.py`) mit den drei
  Geltungen Für jetzt · In „Plan“ · Übung.
- **✎ klappt den Editor an Ort und Stelle auf** (`components/timer_editor.py`: Zeiten ·
  Klänge wie beim Haupttimer) — die anderen Karten bleiben sichtbar. Darunter „Geändert
  gilt:“ mit denselben drei Geltungen:
  *In „Plan“* macht aus dem Timer die **eigene Kopie der Planübung** (sichtbar: „nur hier“),
  *Übung* schreibt an die Übung — gilt der Timer an mehreren Stellen, fragt der Dialog
  „Überall ändern · Nur hier: Kopie anlegen“ einmal —, *Für jetzt* stellt nur die Uhr dieser
  Sitzung (`AppState.uhr_einmal`) und speichert nichts.

Jede Änderung im Fenster gilt sofort (`wahl_setzen` schreibt in die Datenbank bzw. in das
Formular darunter); gerechnet wird nichts — welcher Timer gilt, sagt
`core.uebung_timer.timer_fuer`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from trainingsapp.core.models import Exercise, Plan, PlanItem, new_id
from trainingsapp.core.timer import EINMAL, Abschnitt, TimerProfil, dauer_text
from trainingsapp.core.uebung_timer import TimerWahl, plan_timer, profile_der_uebung
from trainingsapp.ui.components.timer_editor import timer_editor
from trainingsapp.ui.components.timer_stellen import AB_STELLEN, HIER, ueberall_oder_hier
from trainingsapp.ui.components.uhr_blatt import JETZT, PLAN, UEBUNG
from trainingsapp.ui.timer_bibliothek import (
    in_uebung_speichern,
    kopie,
    kopie_name,
    nur_in_uebung,
    stellen_von,
)

#: Warum „Für jetzt“ im Plan-Editor nicht geht, solange nicht geübt wird (P171)
JETZT_GRUND = "gilt erst beim Üben"


def jetzt_grund(state: Any) -> str:
    """Leer, wenn gerade eine Einheit läuft oder vorbereitet ist — sonst der Grund, warum
    „Für jetzt“ ausgegraut ist: Wer nur den Plan baut, hat kein „jetzt“ (P171)."""
    from trainingsapp.ui import einheit as einheit_ui

    return "" if einheit_ui.aktuell(state) is not None else JETZT_GRUND


def herkunft(
    uebung: Exercise, plan: Plan | None, wahl: TimerWahl, profil: TimerProfil | None
) -> str:
    """Woher der Timer kommt, der gilt — der Chip der Zeile.

    >>> from trainingsapp.core.timer import Abschnitt
    >>> h = TimerProfil(id="h", name="Halten", abschnitte=[Abschnitt("H", 30)])
    >>> u = Exercise(name="Planke", timer=[h.als_dict()])
    >>> herkunft(u, None, TimerWahl(), h), herkunft(u, None, TimerWahl("", h), h)
    ('Übung', 'nur hier')
    >>> herkunft(u, Plan(timer=h.als_dict()), TimerWahl(), h), herkunft(u, None, TimerWahl(), None)
    ('Plan', '')
    """
    if profil is None:
        return ""
    if wahl.eigen is not None:
        return "Bibliothek · nur hier" if wahl.eigen.bibliothek else "nur hier"
    if wahl.profil_id:
        return "nur hier"
    if plan_timer(plan) is not None:
        return "Plan"
    return "Bibliothek" if profil.bibliothek else "Übung"


def timer_zeile(
    *,
    uebung: Exercise,
    plan: Plan | None,
    wahl: TimerWahl,
    profil: TimerProfil | None,
    offen: bool,
    blatt_oeffnen: Callable[..., Any],
    editor_umschalten: Callable[..., Any],
) -> ft.Control:
    """Die Zeile: Name ▾ (Uhr-Blatt), Gesamtzeit und Abschnitte, Herkunft, ✎ (Editor auf/zu)."""
    hat_ablauf = profil is not None and not profil.ist_stoppuhr
    name = profil.anzeigename if profil is not None else "kein Timer"
    if profil is not None and hat_ablauf:
        n = len(profil.alle_abschnitte())
        unter = f"{dauer_text(profil.gesamt_s())} · {n} Abschnitt{'e' if n != 1 else ''}"
    elif profil is not None:
        unter = "zählt vorwärts"
    else:
        unter = "die Übung hat keinen — tippen und wählen"
    woher = herkunft(uebung, plan, wahl, profil)
    return ft.Container(
        data="timer_zeile",
        border_radius=12,
        border=ft.Border.all(
            1.5 if offen else 1, ft.Colors.PRIMARY if offen else ft.Colors.OUTLINE
        ),
        padding=ft.Padding.only(left=4, right=2, top=2, bottom=2),
        content=ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    expand=True,
                    on_click=blatt_oeffnen,
                    padding=ft.Padding.only(left=8, top=4, bottom=4),
                    tooltip="Timer wählen — für jetzt, im Plan oder für die Übung",
                    data="timer_name",
                    content=ft.Column(
                        spacing=0,
                        tight=True,
                        controls=[
                            ft.Row(
                                spacing=2,
                                controls=[
                                    ft.Icon(
                                        ft.Icons.TIMER_OUTLINED, size=16, color=ft.Colors.PRIMARY
                                    ),
                                    ft.Text(
                                        name,
                                        weight=ft.FontWeight.W_600,
                                        color=ft.Colors.PRIMARY,
                                        max_lines=1,
                                        no_wrap=True,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        expand=True,
                                        expand_loose=True,
                                    ),
                                    ft.Icon(
                                        ft.Icons.ARROW_DROP_DOWN, size=20, color=ft.Colors.PRIMARY
                                    ),
                                ],
                            ),
                            ft.Text(unter, size=12, opacity=0.7),
                        ],
                    ),
                ),
                *(
                    [
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                            border_radius=10,
                            bgcolor=ft.Colors.TERTIARY_CONTAINER
                            if "nur hier" in woher
                            else ft.Colors.SECONDARY_CONTAINER,
                            content=ft.Text(woher, size=11, weight=ft.FontWeight.W_600),
                            data="timer_herkunft",
                        )
                    ]
                    if woher
                    else []
                ),
                ft.IconButton(
                    ft.Icons.EXPAND_LESS if offen else ft.Icons.EDIT_OUTLINED,
                    tooltip="Editor schließen"
                    if offen
                    else "Timer hier bearbeiten: Zeiten · Klänge",
                    on_click=editor_umschalten,
                    visible=hat_ablauf,
                    data="timer_editor_auf",
                ),
            ],
        ),
    )


def timer_im_fenster(
    page: Any,
    state: Any,
    *,
    uebung: Exercise,
    plan: Plan,
    item: PlanItem,
    profil: TimerProfil,
    wahl: Callable[[], TimerWahl],
    wahl_setzen: Callable[[TimerWahl], None],
    geltung: dict[str, str],
    spec: Any = None,
) -> ft.Control:
    """Der aufgeklappte Editor für ``profil`` (der Timer, der gerade gilt) samt „Geändert
    gilt:“. ``wahl``/``wahl_setzen``: die Timer-Wahl der Planübung lesen und schreiben (Datenbank
    oder Formular); ``geltung``: ``{"g": …}`` — überlebt den Neuaufbau der Karte."""
    grund = jetzt_grund(state)
    if geltung.get("g") not in (PLAN, UEBUNG, JETZT) or (geltung.get("g") == JETZT and grund):
        geltung["g"] = PLAN
    #: Wohin die Geltung „Übung“ schreibt: das Profil der Übung mit dieser ID (``""`` = noch
    #: keins: der Timer kommt neu an die Übung); ``frage``: „Überall · Nur hier“ beantwortet
    merker: dict[str, Any] = {"plan_id": "", "uebung_id": "", "frage": "", "fragt": False}
    eigene_ids = {p.id for p in profile_der_uebung(uebung) if uebung.timer}
    if profil.id in eigene_ids:
        merker["uebung_id"] = profil.id
    hinweis_text = ft.Text(size=12, opacity=0.7)

    def hinweis_setzen() -> None:
        g = geltung["g"]
        if g == PLAN:
            hinweis_text.value = (
                f"Gilt nur in „{plan.name}“ — aus dem Timer wird die eigene Kopie dieser "
                "Planübung (nur hier ↺)."
            )
        elif g == UEBUNG:
            orte = stellen_von(state, profil.bibliothek) if profil.bibliothek else []
            hinweis_text.value = (
                f"Gilt überall, wo „{uebung.name}“ steht."
                if len(orte) < AB_STELLEN
                else f"Der Timer gilt an {len(orte)} Stellen — beim ersten Ändern wird gefragt: "
                "überall ändern oder nur hier."
            )
        else:
            hinweis_text.value = (
                "Gilt nur jetzt — bis die App neu startet. Nichts wird gespeichert."
            )

    def bauen() -> TimerProfil | None:
        neu = editor.bauen(profil.id, profil.name or "Timer")
        return None if isinstance(neu, str) else neu

    def in_plan(neu: TimerProfil) -> None:
        w = wahl()
        if w.eigen is not None and not w.eigen.bibliothek and w.eigen.id == profil.id:
            neu.id, neu.name, neu.bibliothek = w.eigen.id, w.eigen.name, ""
        else:
            # die Kopie entsteht beim ersten Ändern — eine ID für alle weiteren
            if not merker["plan_id"]:
                merker["plan_id"] = new_id()
                merker["plan_name"] = kopie_name(profil, plan.name)
            neu.id, neu.name, neu.bibliothek = merker["plan_id"], merker["plan_name"], ""
        wahl_setzen(TimerWahl("", neu, uhr=w.uhr, zaehlt=w.zaehlt))

    def in_uebung(neu: TimerProfil) -> None:
        if merker["uebung_id"]:
            neu.id = merker["uebung_id"]
            if merker["frage"] == HIER:
                neu.bibliothek, neu.name = "", merker["kopie_name"]
            in_uebung_speichern(state, uebung, neu)
        else:  # der Timer des Plans oder eine eigene Kopie: er kommt neu an die Übung
            merker["uebung_id"] = neu.id = new_id()
            neu.bibliothek = ""
            in_uebung_speichern(state, uebung, neu)
        w = wahl()
        if w.eigen is not None or w.profil_id:
            # die Planübung wählt jetzt diesen Timer der Übung statt ihrer Kopie
            wahl_setzen(TimerWahl(neu.id, None, uhr=w.uhr, zaehlt=w.zaehlt))

    async def erst_fragen(neu: TimerProfil, orte: list[Any]) -> None:
        name_kopie = kopie_name(profil, uebung.name)
        try:
            wie = await ueberall_oder_hier(
                page, profil, orte, hier=uebung.name, kopie_name=name_kopie
            )
        finally:
            merker["fragt"] = False
        if not wie:  # abgebrochen: nichts an die Übung — weiter nur im Plan
            geltung["g"] = PLAN
            wahl_seg.selected = [PLAN]
            hinweis_setzen()
            with contextlib.suppress(Exception):
                page.update()
            return
        merker["frage"] = wie
        if wie == HIER:
            eigene = kopie(profil, name_kopie)
            nur_in_uebung(state, uebung, profil, eigene)
            merker["uebung_id"], merker["kopie_name"] = eigene.id, name_kopie
        frisch = bauen()
        if frisch is not None:
            in_uebung(frisch)

    def geaendert() -> None:
        neu = bauen()
        if neu is None:
            return  # unvollständig (eine Dauer fehlt) — bleibt im Editor, bis es stimmt
        g = geltung["g"]
        if g == PLAN:
            in_plan(neu)
        elif g == UEBUNG:
            orte = (
                stellen_von(state, profil.bibliothek)
                if profil.bibliothek and merker["uebung_id"] == profil.id and not merker["frage"]
                else []
            )
            if len(orte) >= AB_STELLEN:
                if not merker["fragt"]:
                    merker["fragt"] = True
                    page.run_task(erst_fragen, neu, orte)
                return
            in_uebung(neu)
        else:
            from trainingsapp.ui.components.uhr import schluessel

            key = schluessel(uebung, item)
            neu.id, neu.bibliothek = EINMAL, ""
            state.uhr_einmal[key] = neu
            state.uhr_wahl[key] = EINMAL
            state.uhr_einmal_start.pop(key, None)

    def geltung_gewaehlt(e: Any) -> None:
        wert = e.control.selected[0] if e.control.selected else geltung["g"]
        if wert == JETZT and grund:
            wert = geltung["g"]
            e.control.selected = [wert]
        geltung["g"] = wert
        hinweis_setzen()
        with contextlib.suppress(Exception):
            page.update()

    # Ausführungen je Abschnitt gehören zur Übung — ein gemeinsamer Timer trägt keine (P174)
    editor = timer_editor(
        page, state, profil, spec=None if profil.bibliothek else spec, geaendert=geaendert
    )
    wahl_seg = ft.SegmentedButton(
        selected=[geltung["g"]],
        allow_empty_selection=False,
        show_selected_icon=False,
        segments=[
            ft.Segment(
                value=JETZT,
                label=ft.Text("Für jetzt", opacity=0.45 if grund else 1.0),
                tooltip=grund or None,
            ),
            ft.Segment(value=PLAN, label=ft.Text(f"In „{plan.name}“")),
            ft.Segment(value=UEBUNG, label=ft.Text("Übung")),
        ],
        on_change=geltung_gewaehlt,
        data="geaendert_gilt",
    )
    hinweis_setzen()
    return ft.Container(
        data=("timer_fenster", item.id),
        padding=ft.Padding.only(top=4),
        content=ft.Column(
            spacing=8,
            tight=True,
            controls=[
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(expand=True, content=editor.reiter),
                        ft.Column(
                            spacing=0,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[editor.gesamt, ft.Text("gesamt", size=11, opacity=0.7)],
                        ),
                    ],
                ),
                ft.GestureDetector(on_horizontal_drag_end=editor.gewischt, content=editor.inhalt()),
                ft.Divider(height=1),
                ft.Text("Geändert gilt:", size=12, opacity=0.7),
                wahl_seg,
                hinweis_text,
            ],
        ),
    )


def kopie_fuer_plan(profil: TimerProfil) -> TimerProfil:
    """Eine eigene Kopie mit neuer ID — für die Planübung (vorher `timer_wahl.kopie_von`)."""
    return kopie(profil)


def neuer_timer() -> TimerProfil:
    """Der Anfang eines neuen Timers: Belastung 30 s, Pause 15 s."""
    return TimerProfil(
        id=new_id(), name="Timer", abschnitte=[Abschnitt("Belastung", 30), Abschnitt("Pause", 15)]
    )


__all__ = [
    "JETZT_GRUND",
    "herkunft",
    "jetzt_grund",
    "kopie_fuer_plan",
    "neuer_timer",
    "timer_im_fenster",
    "timer_zeile",
]
