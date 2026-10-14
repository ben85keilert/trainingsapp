"""Übung anlegen oder bearbeiten — Route `/uebung/neu` bzw. `/uebung/<id>/bearbeiten`.

Die Parameter einer Übung kommen aus dem **Feldvorrat** (`core/result_spec.py`):
Jedes Feld bringt Typ und Einheit mit, hier schaltet man es ein und legt die
Chips fest. Was eingeschaltet ist, kann man in der Ausführung als geleistet
antippen. (Vorlagen gibt es im Editor nicht mehr — die Schalter sind schneller
als ein Umweg.) Felder, die eine Übung aus früheren Zeiten trägt und die nicht
im Vorrat stehen, bleiben erhalten. Die Skala trägt einen eigenen Namen
(Vorgabe „Skala“) und einen Bereich.

Typen und Regionen: Chips aus der eigenen Liste (Einstellungen → Typen und
Regionen); ein neuer kommt über das Feld mit „+“ dazu und steht oben — keine
Kommaliste mehr.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core.models import (
    TAG_REGION,
    TAG_TYP,
    Exercise,
    Media,
    MediaKind,
    MediaSource,
)
from trainingsapp.core.parameter import chips_sortiert, modus_aus_felder
from trainingsapp.core.result_spec import (
    FELDVORRAT,
    FieldSpec,
    FieldType,
    Layout,
    ResultSpec,
    basis_label,
    skala_bereich_text,
    skala_lesen,
    vorrat_feld,
)
from trainingsapp.core.standards import ziel_bereinigen, ziel_spec
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import AUSWAHL, symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.state import AppState

#: Auswahlwert „keine Variante" — ein leerer Schlüssel ist im Dropdown heikel
EIGENSTAENDIG = "eigenstaendig"

KENNZAHL_TYPEN = {
    FieldType.SET_LIST,
    FieldType.INT,
    FieldType.FLOAT,
    FieldType.DURATION,
    FieldType.DEGREES,
    FieldType.WEIGHT,
    FieldType.DISTANCE,
    FieldType.SCALE,
}


def chips_text(werte: list[Any]) -> str:
    return ", ".join(
        str(int(w)) if isinstance(w, float) and w.is_integer() else str(w) for w in werte
    )


def chips_lesen(text: str, f: FieldSpec) -> list[Any]:
    """„10, 15, 20“ → Zahlen; bei Auswahlfeldern Texte."""
    teile = [t.strip() for t in text.replace(";", ",").split(",") if t.strip()]
    if f.type in (FieldType.CHOICE, FieldType.TEXT):
        return teile
    werte: list[Any] = []
    for t in teile:
        try:
            zahl = float(t.replace(",", "."))
        except ValueError:
            continue
        werte.append(int(zahl) if zahl.is_integer() else zahl)
    return werte


def spec_bauen(felder: list[FieldSpec]) -> ResultSpec:
    """Aus den eingeschalteten Feldern die Spezifikation — Kennzahlen automatisch."""
    keys = [f.key for f in felder]
    layout = Layout.SETS if "reps" in keys else Layout.TIMED if "hold" in keys else Layout.SINGLE
    return ResultSpec(
        layout=layout,
        fields=felder,
        chart_metrics=[f.key for f in felder if f.type in KENNZAHL_TYPEN],
    )


def uebung_bearbeiten(page: ft.Page, state: AppState, uebung: Exercise | None) -> ft.View:
    neu = uebung is None
    route = "/uebung/neu" if uebung is None else f"/uebung/{uebung.id}/bearbeiten"
    vorhanden = {f.key: f for f in (uebung.result_spec.fields if uebung else [])}
    # Eine neue Übung beginnt mit Wiederholungen — der häufigste Fall.
    eingeschaltet = set(vorhanden) if uebung is not None else {"reps"}

    # -- Stammdaten --------------------------------------------------------

    name = ft.TextField(label="Name", value=uebung.name if uebung else "", autofocus=neu)
    beschreibung = ft.TextField(
        label="Beschreibung",
        value=uebung.description if uebung else "",
        multiline=True,
        min_lines=3,
        max_lines=8,
    )

    # -- Typen und Regionen ------------------------------------------------
    # Zwei Tag-Arten, beide optional und mehrfach: Chips aus der eigenen Liste
    # (Einstellungen → Typen und Regionen), dazu ein Feld mit „+“ für einen
    # neuen — er steht oben und ist gleich gewählt. Angelegt wird er erst beim
    # Speichern; wer abbricht, hinterlässt nichts.

    def tag_auswahl(
        art: str, aktiv: list[str], beschriftung: str
    ) -> tuple[ft.Control, Callable[[], list[str]]]:
        # In der Reihenfolge des Antippens: Der erste Typ ist die Kategorie.
        gewaehlt = list(aktiv)
        angebot = list(dict.fromkeys([*state.tags.namen(art), *aktiv]))
        andere_art = state.tags.namen(TAG_REGION if art == TAG_TYP else TAG_TYP)
        reihe = ft.Row(wrap=True, spacing=6, run_spacing=4)
        feld = ft.TextField(
            label=beschriftung,
            dense=True,
            expand=True,
            capitalization=ft.TextCapitalization.SENTENCES,
        )

        def schalter(name: str) -> Callable[[], None]:
            def handler() -> None:
                if name in gewaehlt:
                    gewaehlt.remove(name)
                else:
                    gewaehlt.append(name)
                zeichnen()
                page.update()

            return handler

        def zeichnen() -> None:
            reihe.controls = [
                ft.Chip(
                    label=ft.Text(name),
                    selected=name in gewaehlt,
                    show_checkmark=False,
                    on_click=schalter(name),
                )
                for name in angebot
            ]

        def hinzufuegen() -> None:
            text = (feld.value or "").strip()
            gleich = [n for n in angebot if n.casefold() == text.casefold()]
            fremd = [n for n in andere_art if n.casefold() == text.casefold()]
            if not text:
                feld.error = "Name?"
            elif fremd:
                andere = "eine Region" if art == TAG_TYP else "ein Typ"
                feld.error = f"„{fremd[0]}“ ist schon {andere}."
            else:
                name = gleich[0] if gleich else text
                if not gleich:
                    angebot.insert(0, name)  # neu: oben
                if name not in gewaehlt:
                    gewaehlt.append(name)
                feld.value, feld.error = "", None
                zeichnen()
            page.update()

        feld.on_submit = lambda _: hinzufuegen()
        zeichnen()
        bereich = ft.Column(
            spacing=8,
            controls=[
                reihe,
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        feld,
                        ft.FilledTonalIconButton(
                            ft.Icons.ADD, tooltip=f"{beschriftung} anlegen", on_click=hinzufuegen
                        ),
                    ],
                ),
            ],
        )
        return bereich, lambda: [n for n in gewaehlt if n in angebot]

    typ_auswahl, typen_lesen = tag_auswahl(
        TAG_TYP, list(uebung.typen) if uebung else [], "Neuer Typ"
    )
    region_auswahl, regionen_lesen = tag_auswahl(
        TAG_REGION, list(uebung.regionen) if uebung else [], "Neue Region"
    )

    # -- Felder aus dem Vorrat ---------------------------------------------
    # Je Vorratsfeld ein Schalter und ein Chip-Feld. Eingeschaltet, wenn die
    # Übung das Feld schon hat; Chips aus der Übung, sonst aus dem Vorrat.

    schalter: dict[str, ft.Switch] = {}
    chipfelder: dict[str, ft.TextField] = {}
    zeilen: list[ft.Control] = []
    # Skala: eigener Bereich statt fest 0–10 — auch negativ, Kommazahlen als solche
    skala_alt = vorhanden.get("scale")
    # Name der Skala (Ben, 14.10.2026): Vorgabe „Skala“, frei änderbar —
    # „Anstrengung“, „Schmerz“, „Stabilität“. Alte heißen „Skala 0–10“.
    skala_name = ft.TextField(
        label="Name der Skala",
        value=basis_label(skala_alt) if skala_alt is not None else "Skala",
        hint_text="z. B. Anstrengung, Schmerz, Stabilität",
        dense=True,
        capitalization=ft.TextCapitalization.SENTENCES,
    )
    skala_bereich = ft.TextField(
        label="Bereich",
        value=skala_bereich_text(
            skala_alt or vorrat_feld("scale") or FieldSpec("scale", FieldType.SCALE, "Skala")
        ),
        hint_text="0 - 10 · -5 - 5 · 0.0 - 10.0",
        helper="Kommazahlen so: 0.0 - 10.0",
        dense=True,
    )
    skala_felder = ft.Container(
        padding=ft.Padding.only(left=56, bottom=6),
        visible="scale" in eingeschaltet,
        content=ft.Column(spacing=12, controls=[skala_name, skala_bereich]),
    )

    def sichtbarkeit(key: str) -> Callable[[], None]:
        def handler() -> None:
            vorlage = next(f for f in FELDVORRAT if f.key == key)
            chipfelder[key].visible = bool(schalter[key].value) and vorlage.type not in (
                FieldType.BOOL,
                FieldType.TEXT,
                FieldType.SCALE,
            )
            if key == "scale":
                skala_felder.visible = bool(schalter[key].value)
            page.update()

        return handler

    for vorlage in FELDVORRAT:
        aktiv = vorlage.key in eingeschaltet
        quelle = vorhanden.get(vorlage.key, vorlage)
        schalter[vorlage.key] = ft.Switch(
            label="Skala"
            if vorlage.type == FieldType.SCALE
            else f"{vorlage.label}{f' ({vorlage.unit})' if vorlage.unit else ''}",
            value=aktiv,
            on_change=sichtbarkeit(vorlage.key),
        )
        chipfelder[vorlage.key] = ft.TextField(
            label="Chips (mit Komma)" if vorlage.type != FieldType.CHOICE else "Optionen",
            value=chips_text(quelle.quick),
            dense=True,
            visible=aktiv,
        )
        if vorlage.type == FieldType.SCALE:
            chipfelder[vorlage.key].visible = False
            zeilen.append(
                ft.Column(
                    spacing=4,
                    controls=[schalter[vorlage.key], skala_felder],
                )
            )
        elif vorlage.type in (FieldType.BOOL, FieldType.TEXT):
            chipfelder[vorlage.key].visible = False
            zeilen.append(schalter[vorlage.key])
        else:
            # Schalter oben, Chips darunter eingerückt — nebeneinander passte
            # beides am Handy nicht, das Chip-Feld lief über den Rand.
            zeilen.append(
                ft.Column(
                    spacing=4,
                    controls=[
                        schalter[vorlage.key],
                        ft.Container(
                            padding=ft.Padding.only(left=56, bottom=6),
                            content=chipfelder[vorlage.key],
                        ),
                    ],
                )
            )
    # Felder, die nicht im Vorrat stehen (ältere oder besondere), bleiben erhalten.
    fremde = [f for key, f in vorhanden.items() if key not in schalter]
    if fremde:
        zeilen.append(
            ft.Text(
                "Weitere Felder dieser Übung bleiben erhalten: "
                + ", ".join(f.label for f in fremde),
                size=12,
                opacity=0.6,
            )
        )

    # -- Standard für Pläne ----------------------------------------------------

    # Welche Parameter ein neuer Plan anbietet: alle — oder keinen (nur abhaken).
    # Eine feinere Wahl trifft man im Plan („Einstellen") und schiebt sie per
    # „Als Standard der Übung setzen" hierher.
    nur_abhaken = ft.Switch(
        label="In Plänen nur abhaken (keine Werte)",
        value=bool(uebung is not None and uebung.default_felder == []),
    )

    # -- Kachel im Verlauf -----------------------------------------------------
    # Eine Variante zeigt auf ein Original; wer selbst Varianten hat, ist ein
    # Original und kann nicht gleichzeitig Variante sein (keine Ketten).

    eigene_varianten = state.uebungen.varianten(uebung.id, mit_papierkorb=True) if uebung else []
    originale = [
        u
        for u in state.uebungen.alle(mit_archivierten=True)
        if u.family_id is None and (uebung is None or u.id != uebung.id)
    ]
    # Liegt das Original im Papierkorb, bleibt es wählbar — sonst zeigte der
    # Dropdown einen Wert ohne Eintrag.
    weg = (
        state.uebungen.laden(uebung.family_id, mit_geloeschten=True)
        if uebung is not None and uebung.family_id
        else None
    )
    if weg is not None and all(u.id != weg.id for u in originale):
        originale.append(replace(weg, name=f"{weg.name} (gelöscht)"))
    familie = ft.Dropdown(
        label="Kachel im Verlauf",
        value=uebung.family_id if uebung and uebung.family_id else EIGENSTAENDIG,
        options=[
            ft.DropdownOption(key=EIGENSTAENDIG, text="Eigenständig (eigene Liste)"),
            *[ft.DropdownOption(key=u.id, text=f"Variante von „{u.name}“") for u in originale],
        ],
        disabled=bool(eigene_varianten),
        expand=True,
    )

    # Das Standard-Ziel bezieht sich auf die *gespeicherten* Parameter — wer
    # oben Schalter umlegt, sieht das Ziel dafür nach dem Speichern.
    ziel_form = (
        SpecForm(ziel_spec(uebung.result_spec), dict(uebung.default_target), page=page)
        if uebung is not None and uebung.result_spec.fields
        else None
    )

    def ziel_lesen(spec: ResultSpec) -> dict[str, Any]:
        """Nur Werte, die es in der neuen Spezifikation noch gibt und die etwas sagen."""
        if ziel_form is None:
            return ziel_bereinigen(dict(uebung.default_target) if uebung else {}, spec)
        return ziel_bereinigen(ziel_form.werte(), spec)

    # -- Symbolauswahl -------------------------------------------------------

    gewaehlt: str = uebung.icon_key if uebung and uebung.icon_key else AUSWAHL[0]
    kacheln: dict[str, ft.Container] = {}

    def waehler(key: str) -> Callable[[], None]:
        def handler() -> None:
            nonlocal gewaehlt
            gewaehlt = key
            for k, kachel in kacheln.items():
                kachel.bgcolor = ft.Colors.PRIMARY_CONTAINER if k == key else None
            page.update()

        return handler

    for key in AUSWAHL:
        kacheln[key] = ft.Container(
            width=48,
            height=48,
            border_radius=10,
            alignment=ft.Alignment.CENTER,
            ink=True,
            bgcolor=ft.Colors.PRIMARY_CONTAINER if key == gewaehlt else None,
            content=ft.Icon(symbol(key)),
            on_click=waehler(key),
        )
    symbole = ft.Row(wrap=True, spacing=4, run_spacing=4, controls=list(kacheln.values()))

    # -- Videolinks ----------------------------------------------------------

    medien_zeilen: list[tuple[ft.TextField, ft.TextField]] = []
    medien_spalte = ft.Column(spacing=6)

    def entferner(zeile: tuple[ft.TextField, ft.TextField]) -> Callable[[], None]:
        def handler() -> None:
            medien_zeilen.remove(zeile)
            medien_zeichnen()
            page.update()

        return handler

    def medien_zeichnen() -> None:
        medien_spalte.controls = [
            ft.Row(
                spacing=6,
                controls=[
                    ft.Container(content=titel, expand=2),
                    ft.Container(content=adresse, expand=3),
                    ft.IconButton(
                        ft.Icons.CLOSE, tooltip="Entfernen", on_click=entferner((titel, adresse))
                    ),
                ],
            )
            for titel, adresse in medien_zeilen
        ]

    def zeile_anlegen(medium: Media | None = None) -> None:
        medien_zeilen.append(
            (
                ft.TextField(label="Titel", value=medium.title if medium else "", dense=True),
                ft.TextField(
                    label="Adresse (https://…)",
                    value=medium.uri if medium else "",
                    dense=True,
                    keyboard_type=ft.KeyboardType.URL,
                ),
            )
        )
        medien_zeichnen()

    def link_hinzufuegen() -> None:
        zeile_anlegen()
        page.update()

    for m in uebung.media if uebung else []:
        zeile_anlegen(m)

    # -- Speichern -------------------------------------------------------------

    def felder_lesen() -> list[FieldSpec]:
        felder: list[FieldSpec] = []
        for vorlage_feld in FELDVORRAT:
            if not schalter[vorlage_feld.key].value:
                continue
            alt = vorhanden.get(vorlage_feld.key)
            chips = chips_lesen(chipfelder[vorlage_feld.key].value or "", vorlage_feld)
            feld = replace(
                vorlage_feld,
                quick=chips_sortiert(chips)
                if chips or vorlage_feld.type == FieldType.CHOICE
                else vorlage_feld.quick,
                default=alt.default if alt is not None else vorlage_feld.default,
            )
            if feld.type == FieldType.SCALE:
                lo, hi, schritt = skala_lesen(skala_bereich.value or "") or (0.0, 10.0, 1.0)
                ganz = float(schritt).is_integer()
                feld = replace(
                    feld,
                    label=(skala_name.value or "").strip() or "Skala",
                    min=int(lo) if ganz else lo,
                    max=int(hi) if ganz else hi,
                    step=int(schritt) if ganz else schritt,
                    default=None,
                )
            felder.append(feld)
        felder.extend(fremde)
        return felder

    def eingelesen() -> Exercise:
        ziel = uebung if uebung is not None else Exercise()
        ziel.name = (name.value or "").strip()
        ziel.typen = typen_lesen()
        ziel.category = ziel.typen[0] if ziel.typen else ""
        ziel.description = (beschreibung.value or "").strip()
        ziel.icon_key = gewaehlt
        if not eigene_varianten:
            ziel.family_id = None if familie.value in (None, EIGENSTAENDIG) else familie.value
        if nur_abhaken.value:
            ziel.default_felder = []
        elif ziel.default_felder == []:
            ziel.default_felder = None  # wieder alle
        ziel.default_input_mode = modus_aus_felder(ziel.default_felder)
        ziel.result_spec = spec_bauen(felder_lesen())
        ziel.default_target = ziel_lesen(ziel.result_spec)
        ziel.regionen = regionen_lesen()
        ziel.media = [
            Media(
                kind=MediaKind.VIDEO,
                source=MediaSource.URL,
                uri=(adresse.value or "").strip(),
                title=(titel.value or "").strip(),
            )
            for titel, adresse in medien_zeilen
            if (adresse.value or "").strip()
        ]
        return ziel

    async def speichern() -> None:
        if not (name.value or "").strip():
            name.error = "Ein Name muss sein."
            page.update()
            return
        name.error = None
        if schalter["scale"].value and skala_lesen(skala_bereich.value or "") is None:
            skala_bereich.error = "z. B. 0 - 10 oder -5 - 5 oder 0.0 - 10.0"
            page.update()
            return
        skala_bereich.error = None
        ziel = eingelesen()
        state.uebungen.speichern(ziel)
        page.show_dialog(ft.SnackBar(ft.Text("Gespeichert")))
        await page.push_route(f"/uebung/{ziel.id}")

    async def abbrechen() -> None:
        await page.push_route("/" if uebung is None else f"/uebung/{uebung.id}")

    def abschnitt(text: str, rechts: ft.Control | None = None) -> ft.Control:
        return ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                rechts or ft.Container(),
            ],
        )

    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text("Neue Übung" if neu else "Übung bearbeiten")),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[
            sicher(
                ft.Column(
                    spacing=18,
                    controls=[
                        name,
                        beschreibung,
                        abschnitt("TYP — WAS IST DAS FÜR EINE ÜBUNG? (OPTIONAL)"),
                        typ_auswahl,
                        abschnitt("REGION (OPTIONAL)"),
                        region_auswahl,
                        ft.Text(
                            "Umbenennen und Löschen: in den Einstellungen unter "
                            "„Typen und Regionen“.",
                            size=12,
                            opacity=0.6,
                        ),
                        abschnitt("PARAMETER — WAS KANN MAN LEISTEN?", hilfe_knopf(page)),
                        ft.Text(
                            "Eingeschaltete Parameter tippst du beim Training als geleistet an. "
                            "Winkel, Gewicht und Seite beschreiben die Ausführung und trennen "
                            "Einträge (45° ≠ 90°); Wiederholungen und Zeiten werden addiert.",
                            size=12,
                            opacity=0.7,
                        ),
                        ft.Column(spacing=6, controls=zeilen),
                        abschnitt("VERLAUF"),
                        ft.Row(controls=[familie]),
                        ft.Text(
                            "Varianten (Wandsitz 45° und 90°) teilen sich eine Kachel: Mengen "
                            "werden addiert, die Variante wird dazugeschrieben. Weicht eine "
                            "Variante stark ab (Liegestütz einarmig), mach sie eigenständig."
                            if not eigene_varianten
                            else "Diese Übung ist das Original ihrer Varianten: "
                            + ", ".join(v.name for v in eigene_varianten),
                            size=12,
                            opacity=0.7,
                        ),
                        abschnitt("STANDARD FÜR PLÄNE"),
                        nur_abhaken,
                        ft.Text(
                            "Ein neuer Plan bietet alle Parameter oben an — oder, mit dem "
                            "Schalter, keinen (nur abhaken). Welche genau und mit welchen "
                            "Chips, stellt man im Plan ein und schiebt es mit „Als Standard "
                            "der Übung setzen“ hierher. Ziel (optional): das übernimmt eine "
                            "neue Planübung als „Wie geplant“; leer heißt kein Ziel.",
                            size=12,
                            opacity=0.7,
                        ),
                        ziel_form.control
                        if ziel_form is not None
                        else ft.Text(
                            "Ein Ziel lässt sich nach dem ersten Speichern festlegen.",
                            size=12,
                            opacity=0.6,
                        ),
                        abschnitt("SYMBOL"),
                        symbole,
                        abschnitt("VIDEOS"),
                        medien_spalte,
                        ft.TextButton(
                            "Video-Link hinzufügen",
                            icon=ft.Icons.ADD_LINK,
                            on_click=link_hinzufuegen,
                        ),
                        ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.TextButton("Abbrechen", on_click=abbrechen),
                                ft.FilledButton(
                                    "Speichern", icon=ft.Icons.CHECK, on_click=speichern
                                ),
                            ],
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )


__all__ = ["chips_lesen", "spec_bauen", "uebung_bearbeiten"]
