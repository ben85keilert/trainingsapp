"""Übung bearbeiten — Route `/uebung/neu` bzw. `/uebung/<id>/bearbeiten`.

Der eine Ort, an dem man die Übung selbst ändert (Ben, 22.10.2026, P79: „Der Zugang von
Übungen → Übung → Bearbeiten ist sinnvoll und gut“) — erreichbar über die Übungsseite, nie
direkt aus dem Üben. Von häufig nach selten: Name, Beschreibung, Videos und Links; Parameter;
Varianten; Uhr und Timer; Vorgabe für Pläne (das Ziel); zuletzt Ordnen (Typ und Region,
Symbol, „Im Verlauf zusammen mit“). Aus „Übung hinzufügen“ im Plan-Editor angelegt
(`<bearbeiten>/hinzufuegen/neu`), steht die neue Übung danach gleich im Plan.

Die Parameter einer Übung kommen aus dem **Feldvorrat** (`core/result_spec.py`):
Jedes Feld bringt Typ und Einheit mit, hier schaltet man es ein und tippt die
Chips an (wie in der Planübung, `components/chips_wahl.py`). Was eingeschaltet ist, bieten
alle Pläne an (C2: „Was in der Orginalübung steht wird überall angeboten, sonst muss
Planübung geändert werden“) und kann man in der Ausführung als geleistet antippen.
(Vorlagen gibt es im Editor nicht mehr — die Schalter sind schneller als ein Umweg.)
Felder, die eine Übung aus früheren Zeiten trägt und die nicht im Vorrat stehen, bleiben
erhalten. Die Skala trägt einen eigenen Namen
(Vorgabe „Skala“) und einen Bereich.

Typen und Regionen: dieselbe Auswahl wie im Katalog (`ui/components/tagwahl.py`,
Ben 15.10.2026) — zwei Kästen, Mehrfachauswahl in der Reihenfolge des
Antippens (der erste Typ ist die Kategorie); „Neuer Typ …“ bzw. „Neue Region …“
steht unten in der Liste, ein neuer Tag steht oben und ist gleich gewählt.

**Timer** (Ben, 17.10.2026): die Profile der Übung — Einzeltimer oder Folge mit Teilen;
das erste ist die Vorgabe (Vorrang Planübung > Plan > Übung, `core/uebung_timer.py`).
Hinzufügen aus der Timer-Bibliothek, Reihenfolge und Entfernen gehören zum Formular;
der Editor (Teile, „zählt“ je Abschnitt) ist eine eigene Seite — vor dem Sprung dorthin
speichert das Formular, denn beim Zurückkommen entsteht es neu.

**Varianten** (Ben, 21.10.2026; Skizzen D3, D4): Etiketten innerhalb der Übung — kurz und
lang. Je Variante Name, Symbol oder Kürzel und eine Beschreibung; die Reihenfolge ist die
der Knöpfe beim Eintragen. Gehalten im Formular wie die Timer; wer umbenennt, kann die
bisherigen Einträge mitnehmen — das geschieht erst beim Speichern (`core.varianten`).

Zurück speichert (Ben, 16.10.2026, `components/zurueck.py`); „Abbrechen“ verwirft.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import varianten as var
from trainingsapp.core.models import (
    TAG_REGION,
    TAG_TYP,
    Exercise,
    Media,
    MediaKind,
    MediaSource,
    Plan,
    new_id,
)
from trainingsapp.core.parameter import chips_sortiert
from trainingsapp.core.result_spec import (
    FELDVORRAT,
    FieldSpec,
    FieldType,
    Layout,
    ResultSpec,
    basis_label,
    kennzahl_keys,
    skala_bereich_text,
    skala_lesen,
    vorrat_feld,
)
from trainingsapp.core.standards import ziel_bereinigen, ziel_spec
from trainingsapp.core.timer import TimerProfil
from trainingsapp.core.uebung_timer import profile_der_uebung
from trainingsapp.ui.components.chips_wahl import chips_zeile
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import AUSWAHL, symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.tagwahl import TagWahl
from trainingsapp.ui.components.varianten import plakette
from trainingsapp.ui.components.varianten import symbol as varianten_symbol
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.uebung_timer import formular_profil_route

#: Auswahlwert „keine Variante" — ein leerer Schlüssel ist im Dropdown heikel
EIGENSTAENDIG = "eigenstaendig"


def _saetze_knopf(key: str, saetze_an: dict[str, bool], sichtbar: bool) -> ft.Chip:
    """„Sätze“ (Ben, 18.10.2026): ausgegraut = aus, eine Zahl je Eintrag („263“);
    angetippt = an, Eingabe je Satz („3 × 15“)."""
    text = ft.Text("Sätze", opacity=1.0 if saetze_an[key] else 0.55)

    def umschalten() -> None:
        saetze_an[key] = not saetze_an[key]
        knopf.selected = saetze_an[key]
        text.opacity = 1.0 if saetze_an[key] else 0.55
        with contextlib.suppress(Exception):
            knopf.update()

    knopf = ft.Chip(
        label=text,
        selected=saetze_an[key],
        show_checkmark=True,
        on_select=umschalten,
        visible=sichtbar,
        tooltip="An: Eingabe je Satz (3 × 15) · aus: eine Zahl je Eintrag (263)",
    )
    return knopf


def spec_bauen(felder: list[FieldSpec]) -> ResultSpec:
    """Aus den eingeschalteten Feldern die Spezifikation — Kennzahlen automatisch."""
    keys = [f.key for f in felder]
    layout = Layout.SETS if "reps" in keys else Layout.TIMED if "hold" in keys else Layout.SINGLE
    return ResultSpec(
        layout=layout,
        fields=felder,
        chart_metrics=kennzahl_keys(felder),
    )


def uebung_bearbeiten(
    page: ft.Page,
    state: AppState,
    uebung: Exercise | None,
    *,
    plan: Plan | None = None,
    basis: str | None = None,
) -> ft.View:
    """``plan``/``basis``: neu angelegt aus „Übung hinzufügen“ im Plan-Editor (P79) — beim
    ersten Speichern kommt die Übung in den Plan, danach geht es zurück dorthin."""
    neu = uebung is None
    im_plan = plan is not None and basis is not None and neu
    if im_plan:
        route = f"{basis}/hinzufuegen/neu"
    else:
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
    # Die Tag-Auswahl wie im Katalog: zwei Kästen, Mehrfachauswahl in der
    # Reihenfolge des Antippens — der erste Typ ist die Kategorie. Was die Übung
    # trägt, steht immer zur Wahl (auch Tags, die es in der Liste nicht mehr
    # gibt). Ein neuer Tag wird erst beim Speichern angelegt; wer abbricht,
    # hinterlässt nichts.

    tagwahl = TagWahl(
        [*state.tags.namen(TAG_TYP), *(uebung.typen if uebung else [])],
        [*state.tags.namen(TAG_REGION), *(uebung.regionen if uebung else [])],
        uebung.typen if uebung else [],
        uebung.regionen if uebung else [],
        on_change=lambda _typen, _regionen: None,  # gelesen wird beim Speichern
        neu_anlegen=True,
        page=page,
    )

    def typen_lesen() -> list[str]:
        return list(tagwahl.typen)

    def regionen_lesen() -> list[str]:
        return list(tagwahl.regionen)

    # -- Felder aus dem Vorrat ---------------------------------------------
    # Je Vorratsfeld ein Schalter und ein Chip-Feld. Eingeschaltet, wenn die
    # Übung das Feld schon hat; Chips aus der Übung, sonst aus dem Vorrat.

    schalter: dict[str, ft.Switch] = {}
    #: Je Parameter die Chips zur Wahl und die angetippten (P79: antippen wie in der
    #: Planübung statt einer Kommaliste); eingerückt darunter, sichtbar, solange er an ist
    chips_kandidaten: dict[str, list[Any]] = {}
    chips_wahl: dict[str, list[Any]] = {}
    chips_reihen: dict[str, ft.Container] = {}
    chips_bereiche: dict[str, ft.Container] = {}
    #: Satzlisten: zählen die Sätze? Aus = eine Zahl je Eintrag (Ben, 18.10.2026)
    saetze_an: dict[str, bool] = {}
    saetze_knoepfe: dict[str, ft.Chip] = {}
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
            if key in chips_bereiche:
                chips_bereiche[key].visible = bool(schalter[key].value)
            if key in saetze_knoepfe:
                saetze_knoepfe[key].visible = bool(schalter[key].value)
            if key == "scale":
                skala_felder.visible = bool(schalter[key].value)
            uhr_zeichnen()
            page.update()

        return handler

    def chips_zeichnen(key: str) -> None:
        vorlage = next(f for f in FELDVORRAT if f.key == key)

        def umschalten(wert: Any) -> None:
            liste = chips_wahl[key]
            chips_wahl[key] = [w for w in liste if w != wert] if wert in liste else [*liste, wert]
            chips_neu(key)

        def ergaenzen(neue: list[Any]) -> None:
            chips_kandidaten[key] = chips_sortiert([*chips_kandidaten[key], *neue])
            chips_wahl[key] = chips_sortiert([*chips_wahl[key], *neue])
            chips_neu(key)

        chips_reihen[key].content = chips_zeile(
            vorlage,
            chips_sortiert(chips_kandidaten[key]),
            chips_wahl[key],
            umschalten=umschalten,
            ergaenzen=ergaenzen,
        )

    def chips_neu(key: str) -> None:
        chips_zeichnen(key)
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            chips_reihen[key].update()

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
        if vorlage.type == FieldType.SCALE:
            zeilen.append(ft.Column(spacing=4, controls=[schalter[vorlage.key], skala_felder]))
            continue
        if vorlage.type in (FieldType.BOOL, FieldType.TEXT):
            zeilen.append(schalter[vorlage.key])
            continue
        # Leer heißt leer (Ben, 18.10.2026): ohne angetippten Chip nur das freie Feld
        chips_kandidaten[vorlage.key] = chips_sortiert([*vorlage.quick, *quelle.quick])
        chips_wahl[vorlage.key] = chips_sortiert(list(quelle.quick))
        chips_reihen[vorlage.key] = ft.Container()
        chips_zeichnen(vorlage.key)
        unten: list[ft.Control] = [chips_reihen[vorlage.key]]
        if vorlage.type == FieldType.SET_LIST:
            saetze_an[vorlage.key] = quelle.saetze
            saetze_knoepfe[vorlage.key] = _saetze_knopf(vorlage.key, saetze_an, aktiv)
            unten.append(saetze_knoepfe[vorlage.key])
        # Schalter oben, Chips darunter eingerückt — nebeneinander passte beides am Handy nicht
        chips_bereiche[vorlage.key] = ft.Container(
            padding=ft.Padding.only(left=56, bottom=6),
            visible=aktiv,
            content=ft.Column(spacing=6, controls=unten),
        )
        zeilen.append(
            ft.Column(spacing=4, controls=[schalter[vorlage.key], chips_bereiche[vorlage.key]])
        )
    # Felder, die nicht im Vorrat stehen (ältere oder besondere), bleiben erhalten — die
    # Varianten haben ihren eigenen Abschnitt.
    fremde = [f for key, f in vorhanden.items() if key not in schalter and not var.ist_variante(f)]
    if fremde:
        zeilen.append(
            ft.Text(
                "Weitere Felder dieser Übung bleiben erhalten: "
                + ", ".join(f.label for f in fremde),
                size=12,
                opacity=0.6,
            )
        )

    # -- Varianten (Ben, 21.10.2026; Skizzen D3, D4) -----------------------------------------
    # Gehalten im Formular — „Abbrechen“ verwirft auch hier. Bisherige Einträge umbenennen
    # (Skizze A5) geschieht erst beim Speichern, sonst passten Übung und Einträge nach einem
    # Abbrechen nicht mehr zusammen.

    varianten_liste: list[var.Variante] = var.varianten(uebung.result_spec) if uebung else []
    #: (alt, neu): bisherige Einträge beim Speichern mitnehmen
    umbenennen: list[tuple[str, str]] = []
    varianten_spalte = ft.Column(spacing=2)

    def varianten_zeichnen() -> None:
        reihen: list[ft.Control] = []
        for k, v in enumerate(varianten_liste):
            texte: list[ft.Control] = [ft.Text(v.name, weight=ft.FontWeight.W_600)]
            if v.text:
                texte.append(ft.Text(v.text, size=12, opacity=0.7))
            reihen.append(
                ft.Container(
                    padding=ft.Padding.only(left=8, top=4, bottom=4),
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
                    content=ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            plakette(v, 36),
                            ft.Column(spacing=0, expand=True, controls=texte),
                            ft.IconButton(
                                ft.Icons.ARROW_UPWARD,
                                tooltip="Nach oben — die Reihenfolge der Knöpfe beim Eintragen",
                                visible=k > 0,
                                on_click=varianten_schieber(v.name),
                            ),
                            ft.IconButton(
                                ft.Icons.EDIT_OUTLINED,
                                tooltip=f"„{v.name}“ bearbeiten",
                                on_click=varianten_bearbeiter(v.name),
                            ),
                        ],
                    ),
                )
            )
        if not varianten_liste:
            reihen.append(
                ft.Text(
                    "Noch keine. Beim Üben legt das Etikett neben „Notiz“ auch eine an.",
                    size=12,
                    opacity=0.6,
                )
            )
        varianten_spalte.controls = reihen

    def varianten_neu_zeichnen() -> None:
        varianten_zeichnen()
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            varianten_spalte.update()

    def varianten_schieber(name_: str) -> Callable[[], None]:
        def handler() -> None:
            varianten_liste[:] = var.verschoben(varianten_liste, name_, -1)
            varianten_neu_zeichnen()

        return handler

    def varianten_bearbeiter(name_: str | None) -> Callable[[], None]:
        return lambda: variante_dialog(name_)

    def variante_dialog(bisher: str | None) -> None:
        """Skizze D4: Symbol (oder Kürzel), Name, Beschreibung — und Entfernen."""
        alt = next((v for v in varianten_liste if v.name == bisher), None)
        symbol_wahl = {"key": alt.symbol if alt is not None else ""}
        name_feld = ft.TextField(
            label="Name",
            value=alt.name if alt is not None else "",
            autofocus=alt is None,
            capitalization=ft.TextCapitalization.NONE,
        )
        kuerzel_feld = ft.TextField(
            label="oder Kürzel",
            value=alt.kuerzel if alt is not None else "",
            hint_text="z. B. UA",
            width=130,
            dense=True,
            max_length=var.KUERZEL_MAX,
        )
        text_feld = ft.TextField(
            label="Beschreibung (optional)",
            value=alt.text if alt is not None else "",
            multiline=True,
            min_lines=1,
            max_lines=3,
        )
        bisherige = (
            state.sitzungen.variante_zaehlen(state.profil.id, uebung.id, alt.name)
            if alt is not None and uebung is not None
            else 0
        )
        mitnehmen = ft.Checkbox(
            label=f"Auch die {bisherige} bisherigen Einträge mit „{bisher}“ umbenennen",
            value=True,
            visible=False,
        )

        def name_geaendert(_e: object = None) -> None:
            mitnehmen.visible = bisherige > 0 and (name_feld.value or "").strip() != bisher
            with contextlib.suppress(Exception):
                mitnehmen.update()

        name_feld.on_change = name_geaendert
        kacheln: dict[str, ft.Container] = {}

        def symbol_waehler(key: str) -> Callable[[], None]:
            def handler() -> None:
                symbol_wahl["key"] = key
                for k, kachel in kacheln.items():
                    kachel.bgcolor = ft.Colors.PRIMARY_CONTAINER if k == key else None
                with contextlib.suppress(Exception):
                    page.update()

            return handler

        for key in (*var.SYMBOLE, ""):
            icon = varianten_symbol(key)
            kacheln[key] = ft.Container(
                width=44,
                height=44,
                border_radius=10,
                alignment=ft.Alignment.CENTER,
                ink=True,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                bgcolor=ft.Colors.PRIMARY_CONTAINER if key == symbol_wahl["key"] else None,
                tooltip="Kein Symbol — dann gilt das Kürzel" if not key else None,
                content=ft.Icon(icon) if icon is not None else ft.Text("keins", size=11),
                on_click=symbol_waehler(key),
            )
        nachher = Nachher()

        def uebernehmen(_e: object = None) -> None:
            fehler = False
            try:
                neuer_name = var.name_pruefen(
                    name_feld.value or "", [v.name for v in varianten_liste], bisher=bisher
                )
                name_feld.error = None
            except ValueError as grund:
                name_feld.error, fehler = str(grund), True
            try:
                kuerzel = var.kuerzel_pruefen(kuerzel_feld.value or "")
                kuerzel_feld.error = None
            except ValueError as grund:
                kuerzel_feld.error, fehler = str(grund), True
            try:
                text = var.text_pruefen(text_feld.value or "")
                text_feld.error = None
            except ValueError as grund:
                text_feld.error, fehler = str(grund), True
            if fehler:
                with contextlib.suppress(Exception):
                    page.update()
                return
            neu = var.Variante(neuer_name, symbol_wahl["key"], kuerzel, text)
            varianten_liste[:] = var.ersetzen(varianten_liste, bisher, neu)
            if (
                bisher is not None
                and neuer_name != bisher
                and mitnehmen.visible
                and mitnehmen.value
            ):
                umbenennen.append((bisher, neuer_name))
            nachher.danach(varianten_neu_zeichnen)
            schliessen(dialog)

        def entfernen(_e: object = None) -> None:
            if bisher is not None:
                varianten_liste[:] = var.entfernen(varianten_liste, bisher)
            nachher.danach(varianten_neu_zeichnen)
            schliessen(dialog)

        aktionen: list[ft.Control] = []
        if alt is not None:
            aktionen.append(
                ft.TextButton(
                    "Entfernen",
                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                    tooltip="Bisherige Einträge behalten ihre Variante",
                    on_click=entfernen,
                )
            )
        aktionen += [
            ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
            ft.FilledButton("Übernehmen", icon=ft.Icons.CHECK, on_click=uebernehmen),
        ]
        dialog: ft.AlertDialog = ft.AlertDialog(
            on_dismiss=nachher.bei_schliessen,
            # Der Dialog scrollt selbst — eine scrollende Spalte darin ließ eine Lücke über
            # den Knöpfen (Web-Foto, 21.10.2026)
            scrollable=True,
            title=ft.Text("Variante bearbeiten" if alt is not None else "Neue Variante"),
            content=ft.Column(
                tight=True,
                spacing=12,
                controls=[
                    ft.Text("SYMBOL", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                    ft.Row(wrap=True, spacing=6, run_spacing=6, controls=list(kacheln.values())),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            kuerzel_feld,
                            ft.Text("gilt ohne Symbol", size=12, opacity=0.6, expand=True),
                        ],
                    ),
                    name_feld,
                    mitnehmen,
                    text_feld,
                    ft.Text(
                        "Steht im Blatt hinter dem Etikett, unter der Variantenzeile und in "
                        "der Übungsinfo.",
                        size=12,
                        opacity=0.7,
                    ),
                ],
            ),
            actions=aktionen,
        )
        page.show_dialog(dialog)

    varianten_zeichnen()

    # -- Im Verlauf zusammen mit (P61; bis 22.10.2026 „Kachel im Verlauf“) ------------------
    # Eine Kopie zeigt auf ein Original; wer selbst Kopien hat, ist ein Original und kann
    # nicht gleichzeitig zu einem anderen gehören (keine Ketten).

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
        label="Im Verlauf zusammen mit",
        value=uebung.family_id if uebung and uebung.family_id else EIGENSTAENDIG,
        options=[
            ft.DropdownOption(key=EIGENSTAENDIG, text="keiner — eigene Kachel"),
            *[ft.DropdownOption(key=u.id, text=f"„{u.name}“") for u in originale],
        ],
        disabled=bool(eigene_varianten),
        expand=True,
    )

    # Vorgabe für Pläne: nur noch das Ziel (C2). Es bezieht sich auf die *gespeicherten*
    # Parameter — wer oben Schalter umlegt, sieht das Ziel dafür nach dem Speichern.
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

    # -- Timer (Ben, 17.10.2026) -------------------------------------------------
    # Die eigenen Profile der Übung, im Formular gehalten: „Abbrechen“ verwirft auch hier.

    timer_liste: list[TimerProfil] = (
        profile_der_uebung(uebung) if uebung is not None and uebung.timer else []
    )
    timer_spalte = ft.Column(spacing=6)

    def regel_profil() -> TimerProfil | None:
        """Ohne eigenes Profil gilt die Timer-Regel der Übung als Einzeltimer (Paket
        „Standard“) — als Hinweis, nicht als Zeile."""
        if uebung is None:
            return None
        return next(iter(profile_der_uebung(replace(uebung, timer=[]))), None)

    def timer_zeichnen() -> None:
        reihen: list[ft.Control] = []
        for k, p in enumerate(timer_liste):
            vorgabe = " · Vorgabe" if k == 0 and len(timer_liste) > 1 else ""
            reihen.append(
                ft.Container(
                    padding=ft.Padding.only(left=12, top=4, bottom=4),
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
                    content=ft.Row(
                        spacing=4,
                        controls=[
                            ft.Icon(ft.Icons.TIMER, size=20),
                            ft.Column(
                                expand=True,
                                spacing=0,
                                controls=[
                                    ft.Text(
                                        (p.name or "Timer") + vorgabe, weight=ft.FontWeight.W_600
                                    ),
                                    ft.Text(p.kurztext(), size=12, opacity=0.7),
                                ],
                            ),
                            ft.IconButton(
                                ft.Icons.ARROW_UPWARD,
                                tooltip="Nach oben — das erste ist die Vorgabe",
                                on_click=timer_nach_oben(k),
                                visible=k > 0,
                            ),
                            ft.IconButton(
                                ft.Icons.EDIT_OUTLINED,
                                tooltip="Bearbeiten: Teile, Abschnitte, „zählt“",
                                on_click=timer_bearbeiter(p.id),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="Aus der Übung entfernen",
                                on_click=timer_entferner(k),
                            ),
                        ],
                    ),
                )
            )
        if not timer_liste:
            regel = regel_profil()
            reihen.append(
                ft.Text(
                    f"Ohne eigenes Profil gilt die Timer-Regel der Übung: {regel.kurztext()}."
                    if regel is not None
                    else "Noch kein Timer — „Timer hinzufügen“ legt einen an oder übernimmt "
                    "einen aus der Timer-Bibliothek.",
                    size=12,
                    opacity=0.6,
                )
            )
        timer_spalte.controls = reihen

    def timer_neu_zeichnen() -> None:
        timer_zeichnen()
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            timer_spalte.update()

    def timer_nach_oben(k: int) -> Callable[[], None]:
        def handler() -> None:
            timer_liste.insert(0, timer_liste.pop(k))
            timer_neu_zeichnen()

        return handler

    def timer_entferner(k: int) -> Callable[[], None]:
        def handler() -> None:
            timer_liste.pop(k)
            timer_neu_zeichnen()

        return handler

    # -- Die Uhr in der Übung (Ben, 18.10.2026: „die Uhr kann … separat ein/abgeschalten
    # werden. Ist die Uhr ein, hat man automatisch Zeit mit dabei“) ----------------------
    uhr_vorher = uebung.zaehlt_als if uebung is not None else ""
    uhr_schalter = ft.Switch(
        label="Stoppuhr und Timer beim Üben",
        value=uebung.uhr if uebung is not None else True,
        on_change=lambda: uhr_zeichnen(),
    )
    # Ob Timerzeit zählt (Ben, 22.10.2026, P79 D2): hier die Vorgabe, beim Üben in der Leiste
    # für jetzt umschaltbar
    zaehlt_schalter = ft.Switch(
        label="Timerzeit zählt",
        value=uebung.zeit_zaehlt if uebung is not None else True,
        on_change=lambda: uhr_zeichnen(),
    )
    zaehlt_als_wahl = ft.SegmentedButton(
        segments=[
            ft.Segment(value="hold", label=ft.Text("Haltezeit")),
            ft.Segment(value="duration", label=ft.Text("Zeit")),
        ],
        selected=[uhr_vorher or "hold"],
        allow_empty_selection=False,
        show_selected_icon=False,
    )
    zaehlt_als_zeile = ft.Row(
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[ft.Text("Zählt als", weight=ft.FontWeight.W_600), zaehlt_als_wahl],
    )
    uhr_text = ft.Text(size=12, opacity=0.7)
    uhr_spalte = ft.Column(
        spacing=8, controls=[uhr_schalter, zaehlt_schalter, zaehlt_als_zeile, uhr_text]
    )

    def uhr_zeichnen() -> None:
        """„Zählt als“ nur mit Haltezeit — sonst zählt die Uhr immer als Zeit."""
        an = bool(uhr_schalter.value)
        zaehlt = bool(zaehlt_schalter.value)
        halten = bool(schalter["hold"].value)
        zaehlt_schalter.visible = an
        zaehlt_als_zeile.visible = an and zaehlt and halten
        if not an:
            uhr_text.value = "Aus: keine Uhr in der Übung — „Gemacht“ hakt nur ab."
        elif not zaehlt:
            uhr_text.value = "Läufe tragen nur „gemacht“ ein. Beim Üben in der Leiste umschaltbar."
        elif halten:
            uhr_text.value = (
                "Jeder Lauf ist ein Satz Haltezeit (oder die Zeit) im offenen Eintrag. Beim "
                "Üben schaltest du „zählt“ in der Leiste für jetzt um."
            )
        else:
            uhr_text.value = "Läufe zählen als Zeit im offenen Eintrag — auch ohne den Parameter."
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            uhr_spalte.update()

    def zaehlt_als_lesen() -> str:
        """Die Vorgabe (Haltezeit) bleibt leer, solange nie etwas anderes gewählt war — eine
        Paketübung gilt sonst als „geändert: Zählt als“."""
        wahl = next(iter(zaehlt_als_wahl.selected or []), "hold")
        return "" if wahl == "hold" and not uhr_vorher else str(wahl)

    async def wechseln(ziel: str | None = None, profil_id: str | None = None) -> None:
        """Weiter zu ``ziel`` (sonst in den Profil-Editor) — das Formular speichert vorher
        (beim Zurückkommen entsteht es aus der Datenbank neu). Fehlt etwas (Name), bleibt es
        hier."""
        if sichern() is not None:
            return
        formular = f"/uebung/{gespeichert['id']}/bearbeiten"
        if uebung is None and state.navigation[-1:] == [route]:
            # Die neue Übung ist jetzt gespeichert: An die Stelle von „Neue Übung“ tritt ihr
            # Formular — Zurück führt dorthin, nicht in ein leeres Formular und nicht an ihm
            # vorbei (`ui/navigation.py`)
            state.navigation[-1] = formular
        await page.push_route(ziel or formular_profil_route(formular, profil_id))

    async def timer_editor(profil_id: str | None) -> None:
        await wechseln(profil_id=profil_id)

    def gehe_zu(ziel: str) -> Callable[[], Any]:
        """Ein Link aus dem Formular (P79: Wege statt Wegbeschreibungen) — speichert vorher."""

        async def handler() -> None:
            await wechseln(ziel)

        return handler

    def timer_bearbeiter(profil_id: str) -> Callable[[], Any]:
        async def handler() -> None:
            await timer_editor(profil_id)

        return handler

    def timer_hinzufuegen() -> None:
        """„Timer hinzufügen“: ein neues Profil im Editor oder eine Kopie aus der
        Timer-Bibliothek. Weiter geht es erst, wenn der Dialog zu ist (`Nachher`)."""
        dialog: ft.AlertDialog
        nachher = Nachher()

        def nehmen(vorlage: TimerProfil) -> Callable[[], None]:
            def handler() -> None:
                kopie = TimerProfil.aus_dict(vorlage.als_dict())
                if kopie is not None:
                    kopie.id = new_id()
                    timer_liste.append(kopie)
                nachher.danach(timer_neu_zeichnen)
                schliessen(dialog)

            return handler

        def neues() -> None:
            nachher.danach(lambda: timer_editor(None))
            schliessen(dialog)

        dialog = ft.AlertDialog(
            on_dismiss=nachher.bei_schliessen,
            title=ft.Text("Timer für diese Übung"),
            content=ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.ADD),
                        title=ft.Text("Neues Profil"),
                        subtitle=ft.Text(
                            "Einzeltimer oder Folge mit Teilen — speichert vorher die Übung",
                            size=12,
                        ),
                        on_click=neues,
                    ),
                    ft.Text(
                        "Oder aus der Timer-Bibliothek — die Übung bekommt eine eigene Kopie.",
                        size=12,
                        opacity=0.7,
                    ),
                    *(
                        ft.ListTile(
                            title=ft.Text(p.name),
                            subtitle=ft.Text(p.kurztext(), size=12),
                            on_click=nehmen(p),
                        )
                        for p in state.timer_profile()
                    ),
                ],
            ),
            actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog))],
        )
        page.show_dialog(dialog)

    timer_zeichnen()
    uhr_zeichnen()

    # -- Speichern -------------------------------------------------------------

    def felder_lesen() -> list[FieldSpec]:
        felder: list[FieldSpec] = []
        for vorlage_feld in FELDVORRAT:
            if not schalter[vorlage_feld.key].value:
                continue
            alt = vorhanden.get(vorlage_feld.key)
            chips = chips_wahl.get(
                vorlage_feld.key, list((alt or vorlage_feld).quick)
            )  # Skala, Ja/Nein, Freitext: wie sie sind
            feld = replace(
                vorlage_feld,
                quick=chips_sortiert(chips),
                default=alt.default if alt is not None else vorlage_feld.default,
                saetze=saetze_an.get(vorlage_feld.key, True),
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
        ziel.result_spec = var.mit_varianten(spec_bauen(felder_lesen()), varianten_liste)
        ziel.default_target = ziel_lesen(ziel.result_spec)
        ziel.regionen = regionen_lesen()
        ziel.timer = [p.als_dict() for p in timer_liste]
        ziel.uhr = bool(uhr_schalter.value)
        ziel.zeit_zaehlt = bool(zaehlt_schalter.value)
        ziel.zaehlt_als = zaehlt_als_lesen()
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

    def stand() -> tuple[Any, ...]:
        """Alles, was man hier ändern kann — für „Zurück speichert“ (geändert oder nicht)."""
        return (
            name.value or "",
            beschreibung.value or "",
            typen_lesen(),
            regionen_lesen(),
            [(k, bool(s.value), list(chips_wahl.get(k, []))) for k, s in schalter.items()],
            sorted(saetze_an.items()),
            skala_name.value or "",
            skala_bereich.value or "",
            familie.value,
            ziel_form.werte() if ziel_form is not None else None,
            gewaehlt,
            [(t.value or "", a.value or "") for t, a in medien_zeilen],
            [p.als_dict() for p in timer_liste],
            bool(uhr_schalter.value),
            bool(zaehlt_schalter.value),
            zaehlt_als_lesen(),
            [(v.name, v.symbol, v.kuerzel, v.text) for v in varianten_liste],
            list(umbenennen),
        )

    def sichern() -> str | None:
        """Prüfen und speichern — ``None`` = gespeichert, sonst warum nicht."""
        if not (name.value or "").strip():
            name.error = "Ein Name muss sein."
            page.update()
            return "Ein Name muss sein."
        name.error = None
        if schalter["scale"].value and skala_lesen(skala_bereich.value or "") is None:
            skala_bereich.error = "z. B. 0 - 10 oder -5 - 5 oder 0.0 - 10.0"
            page.update()
            return "Der Bereich der Skala ist unlesbar (z. B. 0 - 10)."
        skala_bereich.error = None
        ziel = eingelesen()
        state.uebungen.speichern(ziel)
        if im_plan and plan is not None and not gespeichert.get("im_plan"):
            # Aus „Übung hinzufügen“: Sie kommt gleich in den Plan — und folgt der Übung (P79)
            state.plaene.uebung_hinzufuegen(plan.id, ziel.id)
            gespeichert["im_plan"] = plan.id
        gespeichert["id"] = ziel.id
        # Umbenannte Varianten: die bisherigen Einträge erst jetzt mitnehmen (Skizze A5)
        for alt, neu in umbenennen:
            state.sitzungen.variante_umbenennen(state.profil.id, ziel.id, alt, neu)
        umbenennen.clear()
        return None

    #: Die ID nach dem ersten Speichern — eine neue Übung hat erst dann eine
    gespeichert: dict[str, str] = {}

    async def speichern() -> None:
        if sichern() is not None:
            return
        if im_plan and plan is not None and basis is not None:
            page.show_dialog(ft.SnackBar(ft.Text(f"Angelegt — steht jetzt in „{plan.name}“")))
            await page.push_route(basis)
            return
        page.show_dialog(ft.SnackBar(ft.Text("Gespeichert")))
        await page.push_route(f"/uebung/{gespeichert['id']}")

    async def abbrechen() -> None:
        if im_plan:
            await page.push_route(f"{basis}/hinzufuegen")
            return
        await page.push_route("/" if uebung is None else f"/uebung/{uebung.id}")

    def abschnitt(text: str, rechts: ft.Control | None = None) -> ft.Control:
        return ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text(text, size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
                rechts or ft.Container(),
            ],
        )

    anfang = stand()
    ansicht = ft.View(
        route=route,
        appbar=formular_leiste(
            "Neue Übung" if neu else "Übung bearbeiten",
            abbrechen=abbrechen,
            speichern=speichern,
        ),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[
            sicher(
                ft.Column(
                    spacing=18,
                    controls=[
                        name,
                        beschreibung,
                        abschnitt("VIDEOS UND LINKS"),
                        medien_spalte,
                        ft.TextButton(
                            "Link hinzufügen",
                            icon=ft.Icons.ADD_LINK,
                            on_click=link_hinzufuegen,
                        ),
                        abschnitt("PARAMETER", hilfe_knopf(page)),
                        ft.Text(
                            "Eingeschaltete Parameter tippst du beim Training als geleistet an "
                            "— in jedem Plan; weniger stellst du in der Planübung ein. Winkel, "
                            "Gewicht und Seite beschreiben die Ausführung und trennen Einträge "
                            "(45° ≠ 90°); Wiederholungen und Zeiten werden addiert.",
                            size=12,
                            opacity=0.7,
                        ),
                        ft.Column(spacing=6, controls=zeilen),
                        abschnitt("VARIANTEN", hilfe_knopf(page, thema="varianten")),
                        ft.Text(
                            "Wie du die Übung ausführst, z. B. kurz und lang. Jede Variante "
                            "wird für sich gezählt und steht beim Eintragen oben als Knopf — "
                            "in dieser Reihenfolge. Passen die Namen nicht in eine Zeile, "
                            "stehen dort nur Symbole oder Kürzel.",
                            size=12,
                            opacity=0.7,
                        ),
                        varianten_spalte,
                        ft.TextButton(
                            "Variante hinzufügen",
                            icon=ft.Icons.SELL_OUTLINED,
                            on_click=varianten_bearbeiter(None),
                        ),
                        abschnitt("UHR UND TIMER"),
                        uhr_spalte,
                        ft.Text(
                            "Das erste Profil ist die Vorgabe; ein Plan kann in „Im Plan "
                            "einstellen“ ein anderes nehmen. Teile (Vorbereitung, Training, "
                            "Cooldown) und „zählt“ je Abschnitt stellst du im Editor ein — er "
                            "speichert vorher die Übung.",
                            size=12,
                            opacity=0.7,
                        ),
                        timer_spalte,
                        ft.Row(
                            wrap=True,
                            spacing=8,
                            controls=[
                                ft.TextButton(
                                    "Timer hinzufügen",
                                    icon=ft.Icons.MORE_TIME,
                                    on_click=timer_hinzufuegen,
                                ),
                                ft.TextButton(
                                    "Darstellung der Uhr",
                                    icon=ft.Icons.CHEVRON_RIGHT,
                                    on_click=gehe_zu("/einstellungen"),
                                ),
                            ],
                        ),
                        abschnitt("VORGABE FÜR PLÄNE"),
                        ft.Text(
                            "Das Ziel (optional) gilt in jedem Plan, der kein eigenes hat — "
                            "„Wie geplant“ trägt es ein; leer heißt kein Ziel.",
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
                        abschnitt("ORDNEN"),
                        tagwahl.control,
                        ft.Row(
                            wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text(
                                    "Der erste Typ ist die Kategorie; neue unten in der Liste.",
                                    size=12,
                                    opacity=0.6,
                                ),
                                ft.TextButton(
                                    "Typen und Regionen verwalten",
                                    icon=ft.Icons.CHEVRON_RIGHT,
                                    on_click=gehe_zu("/einstellungen/tags"),
                                ),
                            ],
                        ),
                        ft.Text("Symbol", weight=ft.FontWeight.W_600),
                        symbole,
                        ft.Row(controls=[familie]),
                        ft.Row(
                            spacing=6,
                            controls=[
                                ft.Text(
                                    "Eine Kopie (Wandsitz 45° und 90°) steht im Verlauf mit "
                                    "dem Original auf einer Kachel: Mengen werden addiert, die "
                                    "Kopie wird dazugeschrieben. Weicht sie stark ab "
                                    "(Liegestütz einarmig), nimm „keiner“."
                                    if not eigene_varianten
                                    else "Mit dieser Übung zusammen im Verlauf: "
                                    + ", ".join(v.name for v in eigene_varianten),
                                    size=12,
                                    opacity=0.7,
                                    expand=True,
                                ),
                                hilfe_knopf(page, thema="uebungen"),
                            ],
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )
    return zurueck_speichert(page, ansicht, geaendert=lambda: stand() != anfang, speichern=sichern)


__all__ = ["spec_bauen", "uebung_bearbeiten"]
