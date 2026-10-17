"""Übung anlegen oder bearbeiten — Route `/uebung/neu` bzw. `/uebung/<id>/bearbeiten`.

Die Parameter einer Übung kommen aus dem **Feldvorrat** (`core/result_spec.py`):
Jedes Feld bringt Typ und Einheit mit, hier schaltet man es ein und legt die
Chips fest. Was eingeschaltet ist, kann man in der Ausführung als geleistet
antippen. (Vorlagen gibt es im Editor nicht mehr — die Schalter sind schneller
als ein Umweg.) Felder, die eine Übung aus früheren Zeiten trägt und die nicht
im Vorrat stehen, bleiben erhalten. Die Skala trägt einen eigenen Namen
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

Zurück speichert (Ben, 16.10.2026, `components/zurueck.py`); „Abbrechen“ verwirft.
"""

from __future__ import annotations

import contextlib
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
    new_id,
)
from trainingsapp.core.parameter import (
    chips_sortiert,
    gewaehlte_felder,
    modus_aus_felder,
    planbare_felder,
)
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
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.hilfe import hilfe_knopf
from trainingsapp.ui.components.icons import AUSWAHL, symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.parameter_wahl import parameter_wahl
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.tagwahl import TagWahl
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.uebung_timer import formular_profil_route

#: Auswahlwert „keine Variante" — ein leerer Schlüssel ist im Dropdown heikel
EIGENSTAENDIG = "eigenstaendig"


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
        chart_metrics=kennzahl_keys(felder),
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
            # Ein neues Feld kommt in den Plan-Standard, solange der „alle“ heißt
            if not schalter[key].value:
                plan_wahl.discard(key)
            elif standard_alle["ja"] and vorlage.type not in (FieldType.BOOL, FieldType.TEXT):
                plan_wahl.add(key)
            standard_zeichnen()
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

    # Welche Parameter ein neuer Plan anbietet — dieselben Knöpfe wie in der
    # Planübung (Ben, 14.10.2026: Übung und Planübung vereinheitlichen). Keiner
    # heißt nur abhaken. Die Planübung übernimmt das beim Aufnehmen und weicht
    # danach nach Belieben ab; „Als Standard setzen“ schiebt zurück.
    plan_wahl: set[str] = (
        {f.key for f in gewaehlte_felder(uebung.result_spec, uebung.default_felder)}
        if uebung is not None
        else {"reps"}
    )
    #: Heißt der Standard „alle“? Dann kommt ein neu eingeschaltetes Feld dazu.
    standard_alle = {"ja": uebung is None or uebung.default_felder is None}
    standard_wahl = ft.Container()

    def eingeschaltete_felder() -> list[FieldSpec]:
        return [
            *(f for f in FELDVORRAT if schalter[f.key].value),
            *fremde,
        ]

    def standard_umschalten(key: str) -> None:
        plan_wahl.symmetric_difference_update({key})
        planbar = {f.key for f in planbare_felder(ResultSpec(fields=eingeschaltete_felder()))}
        standard_alle["ja"] = plan_wahl == planbar
        standard_zeichnen()
        page.update()

    def standard_zeichnen() -> None:
        felder = eingeschaltete_felder()
        standard_wahl.content = (
            parameter_wahl(felder, plan_wahl, standard_umschalten)
            if felder
            else ft.Text("Erst oben Felder einschalten.", size=12, opacity=0.6)
        )

    standard_zeichnen()

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

    async def timer_editor(profil_id: str | None) -> None:
        """Den Profil-Editor öffnen — das Formular speichert vorher (beim Zurückkommen
        entsteht es aus der Datenbank neu). Fehlt etwas (Name), bleibt es hier."""
        if sichern() is not None:
            return
        formular = f"/uebung/{gespeichert['id']}/bearbeiten"
        await page.push_route(formular_profil_route(formular, profil_id))

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
        ziel.result_spec = spec_bauen(felder_lesen())
        im_plan = [f.key for f in ziel.result_spec.fields if f.key in plan_wahl]
        alle = [f.key for f in planbare_felder(ziel.result_spec)]
        ziel.default_felder = None if im_plan == alle else im_plan
        ziel.default_input_mode = modus_aus_felder(ziel.default_felder)
        ziel.default_target = ziel_lesen(ziel.result_spec)
        ziel.regionen = regionen_lesen()
        ziel.timer = [p.als_dict() for p in timer_liste]
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
            [(k, bool(s.value), chipfelder[k].value or "") for k, s in schalter.items()],
            skala_name.value or "",
            skala_bereich.value or "",
            familie.value,
            sorted(plan_wahl),
            ziel_form.werte() if ziel_form is not None else None,
            gewaehlt,
            [(t.value or "", a.value or "") for t, a in medien_zeilen],
            [p.als_dict() for p in timer_liste],
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
        gespeichert["id"] = ziel.id
        return None

    #: Die ID nach dem ersten Speichern — eine neue Übung hat erst dann eine
    gespeichert: dict[str, str] = {}

    async def speichern() -> None:
        if sichern() is not None:
            return
        page.show_dialog(ft.SnackBar(ft.Text("Gespeichert")))
        await page.push_route(f"/uebung/{gespeichert['id']}")

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

    anfang = stand()
    ansicht = ft.View(
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
                        abschnitt("TYP UND REGION (OPTIONAL)"),
                        tagwahl.control,
                        ft.Text(
                            "Der erste Typ ist die Kategorie. Neue unten in der Liste; "
                            "umbenennen und löschen in den Einstellungen unter "
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
                        abschnitt("VERLAUF", hilfe_knopf(page, thema="uebungen")),
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
                        ft.Text(
                            "Welche Parameter ein neuer Plan anbietet — keiner heißt nur "
                            "abhaken. Im Plan lässt sich das je Planübung ändern, auch beim "
                            "Üben über das i-Symbol; „Als Standard der Übung setzen“ schiebt "
                            "es hierher zurück.",
                            size=12,
                            opacity=0.7,
                        ),
                        standard_wahl,
                        ft.Text(
                            "Ziel (optional): das übernimmt eine neue Planübung als „Wie "
                            "geplant“; leer heißt kein Ziel.",
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
                        abschnitt("TIMER"),
                        ft.Text(
                            "Die Uhr neben dem i startet den Timer der Übung — im Plan und in "
                            "der Übung. Das erste Profil ist die Vorgabe; ein Plan kann je "
                            "Planübung ein anderes wählen. Teile (Vorbereitung, Training, "
                            "Cooldown) und „zählt“ je Abschnitt stellst du im Editor ein — er "
                            "speichert vorher die Übung.",
                            size=12,
                            opacity=0.7,
                        ),
                        timer_spalte,
                        ft.TextButton(
                            "Timer hinzufügen", icon=ft.Icons.MORE_TIME, on_click=timer_hinzufuegen
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
    return zurueck_speichert(page, ansicht, geaendert=lambda: stand() != anfang, speichern=sichern)


__all__ = ["chips_lesen", "spec_bauen", "uebung_bearbeiten"]
