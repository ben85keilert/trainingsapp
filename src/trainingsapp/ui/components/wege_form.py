"""Die Wege einer Übung im gezeichneten Ablauf — „Kommt von“ und „Weiter zu“ mit Bedingung
(Ben, 8.11.2026 abends, P108: „Die Einstellungen werden bei Übung und Ablauf gespiegelt. Der
Ursprung der Übung kommt mit Nummer hinzu, und wie es weitergeht mit welcher Bedingung ist
ebenfalls beidseits einstellbar“).

Dasselbe Formular steht in „Im Plan einstellen“ (Abschnitt WEGE) und im Reiter „Ablauf“
(Routing → „Wege einstellen …“, ein Blatt): alle Wege einer Übung auf einmal, untereinander —
„Planke: ‚Rücken tut weh‘ → Langsitzdehnung, ‚Arme tun weh‘ → Armdehnung“. Je Weg: Ziel (eine
Übung mit Nummer, eine Frage, „◀ zurück“ oder das Ende), wann (frei · Zeit ab · Wiederholungen ·
in einer Zeit · Skala), anbieten oder ausführen, Pflicht, Beschriftung, Inhalt. Der erste Weg
ist der **Hauptweg** (er spiegelt sich in die Bedingung), ↑ macht einen anderen dazu — mehrere
gleichwertige Wege fragt das Workout ab (`core.ablauf.wahl_offen`). ``fokus``: das Blatt steht
auf diesem Weg (Punkt einer Verbindung angetippt), die anderen sind zugeklappt.

Das Formular hält nichts selbst: ``lesen`` liefert den Ablauf, ``setzen`` nimmt den geänderten —
wann gespeichert wird, sagt der Ort (Speichern der Seite bzw. Schließen des Blatts).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import ablauf as ab
from trainingsapp.core.ablauf import Ablauf, Kante
from trainingsapp.core.bedingung import ENDE, Inhalt

KARTE = ft.Colors.SURFACE_CONTAINER_HIGHEST


def wege_karte(
    knoten: str,
    lesen: Callable[[], Ablauf],
    setzen: Callable[[Ablauf], None],
    neu_zeichnen: Callable[[], None],
    *,
    namen: Mapping[str, str],
    ohne_timer: bool = False,
    merken: dict[str, Any] | None = None,
    fokus: str | None = None,
) -> ft.Control:
    """Herkunft und Wege von ``knoten``. ``namen``: jeder Knoten mit Nummer („3 · Planke“), in
    Planfolge, Fragen dahinter; ``ohne_timer``: die Übung hat keinen Timer (Hinweis zu „Zeit
    ab“); ``merken``: hält über das Neuzeichnen, welche Inhalte aufgeklappt sind.

    ``fokus``: das Ziel des angetippten Wegs (Ben, 9.11.2026: „Wenn es mehrere Wege von einer
    Übung aus gibt, soll das Blatt von unten einfach auf diesen ausgewählten Weg positioniert
    sein“) — er steht offen und hervorgehoben, die anderen zugeklappt als eine Zeile."""
    a = lesen()
    offen: dict[str, Any] = merken if merken is not None else {}

    def aendern(i: int, *, zeichnen: bool = False, **felder: Any) -> None:
        jetzt = lesen()
        if not 0 <= i < len(jetzt.kanten):
            return
        kanten = list(jetzt.kanten)
        kanten[i] = replace(kanten[i], **felder)
        setzen(replace(jetzt, kanten=tuple(kanten)))
        if zeichnen:
            neu_zeichnen()

    def weg_entfernen(i: int) -> Callable[[Any], None]:
        def handler(_e: Any = None) -> None:
            jetzt = lesen()
            kanten = list(jetzt.kanten)
            if 0 <= i < len(kanten):
                del kanten[i]
            setzen(replace(jetzt, kanten=tuple(kanten)))
            neu_zeichnen()

        return handler

    def zum_hauptweg(i: int) -> Callable[[Any], None]:
        def handler(_e: Any = None) -> None:
            jetzt = lesen()
            kanten = list(jetzt.kanten)
            k = kanten.pop(i)
            erste = next((j for j, x in enumerate(kanten) if x.von == knoten), len(kanten))
            kanten.insert(erste, k)
            setzen(replace(jetzt, kanten=tuple(kanten)))
            neu_zeichnen()

        return handler

    def weg_dazu(_e: Any = None) -> None:
        jetzt = lesen()
        ids = list(namen)
        nach = ids[ids.index(knoten) + 1] if knoten in ids[:-1] else ENDE
        if jetzt.frage(nach) is not None:
            nach = ENDE
        setzen(jetzt.mit_kante(Kante(knoten, nach)))
        neu_zeichnen()

    def herkunft_dazu(von: str) -> Callable[[Any], None]:
        def handler(_e: Any = None) -> None:
            setzen(lesen().mit_kante(Kante(von, knoten)))
            neu_zeichnen()

        return handler

    def zahl(i: int, feld: str, ganz: bool = True) -> Callable[[ft.Event[ft.TextField]], None]:
        def handler(e: ft.Event[ft.TextField]) -> None:
            roh = (e.control.value or "").replace(",", ".").strip()
            if feld == "bis" and not roh:
                aendern(i, bis=None)
                return
            try:
                wert = float(roh)
            except ValueError:
                e.control.error = "Zahl"
                return
            e.control.error = None
            if feld == "n":
                aendern(i, n=int(wert))
            elif feld == "bis":
                aendern(i, bis=int(wert))
            else:
                aendern(i, sekunden=wert if not ganz else float(int(wert)))

        return handler

    # -- Kommt von ---------------------------------------------------------------------------
    teile: list[ft.Control] = [
        ft.Text("KOMMT VON", size=11, weight=ft.FontWeight.BOLD, opacity=0.6)
    ]
    ist_start = a.startknoten([k for k in namen if a.frage(k) is None]) == knoten
    if ist_start:
        teile.append(
            ft.Row(
                spacing=6,
                controls=[
                    ft.Icon(ft.Icons.PLAY_ARROW, size=16, color=ft.Colors.PRIMARY),
                    ft.Text("Start des Workouts", size=13),
                ],
            )
        )
    rein = [(i, k) for i, k in enumerate(a.kanten) if k.nach == knoten and k.von != knoten]
    for i, k in rein:
        teile.append(
            ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.SUBDIRECTORY_ARROW_RIGHT, size=16, opacity=0.7),
                    ft.Text(
                        namen.get(k.von, "?")
                        + (f" — {k.kurztext()}" if k.kurztext() != "frei" else ""),
                        size=13,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        icon_size=16,
                        tooltip="Diesen Weg hierher entfernen",
                        on_click=weg_entfernen(i),
                    ),
                ],
            )
        )
    if not rein and not ist_start:
        teile.append(
            ft.Text(
                "Noch kein Weg hierher — ohne Herkunft kommt die Übung nie dran.",
                size=12,
                opacity=0.7,
            )
        )
    teile.append(
        ft.PopupMenuButton(
            content=ft.Row(
                tight=True,
                spacing=4,
                controls=[ft.Icon(ft.Icons.ADD, size=18), ft.Text("Herkunft", size=13)],
            ),
            tooltip="Ein Weg von einer anderen Übung hierher",
            items=[
                ft.PopupMenuItem(content=name, on_click=herkunft_dazu(k))
                for k, name in namen.items()
                if k != knoten
            ],
        )
    )

    # -- Weiter zu ---------------------------------------------------------------------------
    teile.append(ft.Text("WEITER ZU", size=11, weight=ft.FontWeight.BOLD, opacity=0.6))
    raus = [(i, k) for i, k in enumerate(a.kanten) if k.von == knoten]
    if not raus:
        teile.append(ft.Text("Kein Weg weiter — hier endet das Workout.", size=12, opacity=0.7))
    ziele = [
        *(
            ft.DropdownOption(key=k, text=f"↺ noch einmal: {n}" if k == knoten else n)
            for k, n in namen.items()
        ),
        ft.DropdownOption(key=ab.ZURUECK, text="◀ zurück, wo ich herkam"),
        ft.DropdownOption(key=ENDE, text="Ende des Workouts"),
    ]

    def aufklappen(i: int) -> Callable[[Any], None]:
        def handler(_e: Any = None) -> None:
            offen[f"auf{i}"] = True
            neu_zeichnen()

        return handler

    for n, (i, k) in enumerate(raus):
        gewaehlt = fokus is not None and len(raus) > 1 and k.nach == fokus
        if fokus is not None and len(raus) > 1 and not gewaehlt and not offen.get(f"auf{i}"):
            ziel = "Ende" if k.zum_ende else "◀ zurück" if k.zurueck else namen.get(k.nach, "?")
            teile.append(
                ft.Container(
                    padding=ft.Padding.only(left=12, right=4, top=2, bottom=2),
                    border_radius=12,
                    bgcolor=KARTE,
                    on_click=aufklappen(i),
                    data=("weg_zu", k.nach),
                    content=ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                ("Hauptweg" if n == 0 else f"Weg {n + 1}")
                                + f" → {ziel} · {k.ausloeser_text()}",
                                size=12,
                                expand=True,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.IconButton(
                                ft.Icons.EXPAND_MORE,
                                icon_size=18,
                                tooltip="Aufklappen",
                                on_click=aufklappen(i),
                            ),
                        ],
                    ),
                )
            )
            continue
        karte = _weg(i, k, n, ziele, aendern, weg_entfernen, zum_hauptweg, zahl, offen, ohne_timer)
        if gewaehlt and isinstance(karte, ft.Container):
            karte.border = ft.Border.all(2, ft.Colors.PRIMARY)
            karte.data = ("weg_gewaehlt", k.nach)
        teile.append(karte)
    teile.append(ft.TextButton("Weg", icon=ft.Icons.ADD, on_click=weg_dazu))
    return ft.Column(spacing=8, tight=True, controls=teile)


def _weg(
    i: int,
    k: Kante,
    n: int,
    ziele: list[ft.DropdownOption],
    aendern: Callable[..., None],
    weg_entfernen: Callable[[int], Callable[[Any], None]],
    zum_hauptweg: Callable[[int], Callable[[Any], None]],
    zahl: Callable[..., Callable[[ft.Event[ft.TextField]], None]],
    offen: dict[str, Any],
    ohne_timer: bool,
) -> ft.Control:
    """Ein Weg als Karte — Ziel, wann, anbieten/ausführen, Pflicht, Danach, Beschriftung."""
    kopf = ft.Row(
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(
                "Hauptweg" if n == 0 else f"Weg {n + 1}",
                size=13,
                weight=ft.FontWeight.W_600,
                expand=True,
            ),
            *(
                [
                    ft.IconButton(
                        ft.Icons.ARROW_UPWARD,
                        icon_size=18,
                        tooltip="Zum Hauptweg machen",
                        on_click=zum_hauptweg(i),
                    )
                ]
                if n > 0
                else []
            ),
            ft.IconButton(
                ft.Icons.CLOSE, icon_size=18, tooltip="Weg entfernen", on_click=weg_entfernen(i)
            ),
        ],
    )
    zeilen: list[ft.Control] = [
        kopf,
        ft.Dropdown(
            label="Weiter zu",
            value=k.nach,
            dense=True,
            options=ziele,
            on_select=lambda e: aendern(i, zeichnen=True, nach=str(e.control.value or ENDE)),
        ),
        ft.Row(
            wrap=True,
            spacing=6,
            run_spacing=6,
            controls=[
                ft.Chip(
                    label=ft.Text(text),
                    selected=k.ausloeser == art,
                    show_checkmark=False,
                    on_select=lambda _e, art=art: aendern(
                        i,
                        zeichnen=True,
                        ausloeser=art,
                        n=k.n
                        or (12 if art in (ab.WDH, ab.WDH_IN_ZEIT) else 7 if art == ab.SKALA else 0),
                        sekunden=k.sekunden or (60.0 if art == ab.WDH_IN_ZEIT else 0.0),
                    ),
                )
                for art, text in ab.AUSLOESER_TEXT.items()
            ],
        ),
    ]
    if k.ausloeser in (ab.WDH, ab.WDH_IN_ZEIT, ab.SKALA):
        felder: list[ft.Control] = [
            ft.TextField(
                label="Skala ab" if k.ausloeser == ab.SKALA else "Wiederholungen",
                value=str(k.n),
                dense=True,
                width=130,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_blur=zahl(i, "n"),
                on_submit=zahl(i, "n"),
            )
        ]
        if k.ausloeser == ab.WDH_IN_ZEIT:
            felder.append(
                ft.TextField(
                    label="in Sekunden",
                    value=f"{k.sekunden:g}",
                    dense=True,
                    width=130,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    on_blur=zahl(i, "sekunden", ganz=False),
                    on_submit=zahl(i, "sekunden", ganz=False),
                )
            )
        if k.ausloeser == ab.SKALA:
            felder.append(
                ft.TextField(
                    label="bis (leer = offen)",
                    value="" if k.bis is None else str(k.bis),
                    dense=True,
                    width=150,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    on_blur=zahl(i, "bis"),
                    on_submit=zahl(i, "bis"),
                )
            )
        zeilen.append(ft.Row(wrap=True, spacing=8, run_spacing=6, controls=felder))
    if k.ausloeser == ab.ZEIT and ohne_timer:
        zeilen.append(
            ft.Text(
                "Die Übung hat keinen Timer — „Zeit ab“ gilt, sobald „Fertig“ getippt ist.",
                size=12,
                color=ft.Colors.TERTIARY,
            )
        )
    if k.ausloeser != ab.FREI:
        zeilen.append(
            ft.SegmentedButton(
                selected=["ausfuehren" if k.ausfuehren else "anbieten"],
                show_selected_icon=False,
                segments=[
                    ft.Segment(value="anbieten", label=ft.Text("Anbieten")),
                    ft.Segment(value="ausfuehren", label=ft.Text("Von selbst")),
                ],
                on_change=lambda e: aendern(
                    i, ausfuehren=bool(e.control.selected) and e.control.selected[0] == "ausfuehren"
                ),
            )
        )
    zeilen.append(
        ft.Switch(
            label="Pflicht — andere Wege erst, wenn erfüllt",
            value=k.pflicht,
            on_change=lambda e: aendern(i, zeichnen=True, pflicht=bool(e.control.value)),
        )
    )
    if k.zurueck:
        zeilen.append(
            ft.SegmentedButton(
                selected=["wiederholen" if k.wiederholen else "weiter"],
                show_selected_icon=False,
                segments=[
                    ft.Segment(value="weiter", label=ft.Text("danach die nächste")),
                    ft.Segment(value="wiederholen", label=ft.Text("die unterbrochene noch einmal")),
                ],
                on_change=lambda e: aendern(
                    i,
                    wiederholen=bool(e.control.selected) and e.control.selected[0] == "wiederholen",
                ),
            )
        )
    zeilen.append(
        ft.TextField(
            label="Beschriftung — wann ist dieser Weg gemeint?",
            value=k.text,
            hint_text="Rücken tut weh",
            dense=True,
            on_blur=lambda e: aendern(i, text=(e.control.value or "").strip()),
            on_submit=lambda e: aendern(i, text=(e.control.value or "").strip()),
        )
    )
    if k.pflicht or not k.inhalt.leer or offen.get(f"inhalt{i}"):
        zeilen += [
            ft.TextField(
                label="Inhalt bei diesem Weg (Text, Auftrag)",
                value=k.inhalt.text,
                dense=True,
                multiline=True,
                min_lines=1,
                max_lines=3,
                on_blur=lambda e: aendern(
                    i, inhalt=Inhalt((e.control.value or "").strip(), k.inhalt.url)
                ),
            ),
            ft.TextField(
                label="Link (Video, https://…)",
                value=k.inhalt.url,
                dense=True,
                keyboard_type=ft.KeyboardType.URL,
                on_blur=lambda e: aendern(
                    i, inhalt=Inhalt(k.inhalt.text, (e.control.value or "").strip())
                ),
            ),
        ]
    else:

        def inhalt_auf(_e: Any = None) -> None:
            offen[f"inhalt{i}"] = True
            aendern(i, zeichnen=True)

        zeilen.append(ft.TextButton("Inhalt bei diesem Weg …", on_click=inhalt_auf))
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=12,
        bgcolor=KARTE,
        content=ft.Column(spacing=8, tight=True, controls=zeilen),
    )


__all__ = ["wege_karte"]
