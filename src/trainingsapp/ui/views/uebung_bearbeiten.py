"""Übung bearbeiten — Route `/uebung/neu` bzw. `/uebung/<id>/bearbeiten`.

Der eine Ort, an dem man die Übung selbst ändert (Ben, 22.10.2026, P79: „Der Zugang von
Übungen → Übung → Bearbeiten ist sinnvoll und gut“) — erreichbar über die Übungsseite, nie
direkt aus dem Üben. Aufgeräumt am 2.11.2026 (`docs/plan_uebung_bearbeiten.md`: „alles dort,
wo es hingehört“), von oben nach unten:

- **Kopf:** das Symbol oder eigene Bild groß (ein Tipp öffnet das Blatt „Symbol oder Bild“,
  `components/symbol_blatt.py`: Ablage, Hochladen, Kamera, Symbole), daneben der Name.
- **Beschreibung** als Karte; ein Tipp öffnet den Editor an Ort und Stelle (↶ ↷ Abbrechen
  Fertig, `components/notizeditor.Textnotiz`) — er schreibt in den Formularstand, gespeichert
  wird mit dem Formular.
- **Parameter** als Knöpfe: ein Chip je Feld des **Feldvorrats** (`core/result_spec.py`), ein
  Tipp schaltet ein oder aus. Darunter je eingeschaltetem Parameter eine **Karte**: eigener
  Name (`FieldSpec.label` gehört der Übung), die Chips (angetippt = angeboten, ein ungenutzter
  trägt ✕, `components/chips_wahl.py`), „Sätze“ bei Satzfeldern, Bereich bei der Skala — und
  das **Ziel** für diesen Parameter (was „Wie geplant“ beim Üben einträgt; es gilt in jedem
  Plan ohne eigenes, C2/P79). Felder, die eine Übung aus früheren Zeiten trägt und die nicht
  im Vorrat stehen, bleiben erhalten.
- **Varianten** (Ben, 21.10.2026): Etiketten innerhalb der Übung, je Variante Name, Symbol
  oder Kürzel und Beschreibung, dazu die Ziel-Variante; wer umbenennt, kann die bisherigen
  Einträge mitnehmen — das geschieht erst beim Speichern (`core.varianten`).
- **Uhr und Timer** (Ben, 17./18.10.2026): Stoppuhr und Timer an/aus, Timerzeit zählt, zählt
  als (Haltezeit oder Zeit); die Profile der Übung — das erste ist die Vorgabe, der Editor
  (Teile, „zählt“ je Abschnitt) ist eine eigene Seite, vor dem Sprung dorthin speichert das
  Formular.
- **Videos und Links**, zuletzt **Ordnen** (Typ und Region: dieselbe Auswahl wie im Katalog,
  `components/tagwahl.py`; der erste Typ ist die Kategorie).

Die Erklärtexte stehen nicht mehr unter den Überschriften, sondern im (i) je Abschnitt
(`components/hilfe.py`: parameter, varianten, uhr, symbol). Aus „Übung hinzufügen“ im
Plan-Editor angelegt (`<bearbeiten>/hinzufuegen/neu`), steht die neue Übung danach gleich im
Plan. Zurück speichert (Ben, 16.10.2026, `components/zurueck.py`); „Abbrechen“ verwirft.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.core import varianten as var
from trainingsapp.core.anhaenge import BILD, Ziel
from trainingsapp.core.beschreibung import Abschnitt, abschnitte, zusammen
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
    basis_key,
    basis_label,
    instanzen,
    kennzahl_keys,
    naechster_key,
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
from trainingsapp.ui.components.icons import AUSWAHL
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.notizeditor import Textnotiz
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.symbol_blatt import symbol_blatt
from trainingsapp.ui.components.tagwahl import TagWahl
from trainingsapp.ui.components.uebungsbild import uebungsbild
from trainingsapp.ui.components.varianten import plakette
from trainingsapp.ui.components.varianten import symbol as varianten_symbol
from trainingsapp.ui.components.zurueck import zurueck_speichert
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.anhang_aufnahme import aufnahme_route
from trainingsapp.ui.views.anhang_hochladen import hochladen_route
from trainingsapp.ui.views.uebung_timer import formular_profil_route

#: Die Karte eines Parameters und die Beschreibung
KARTE = ft.Colors.SURFACE_CONTAINER_LOWEST
#: Kantenlänge des Symbols im Kopf (px)
SYMBOL_GROESSE = 72


def _saetze_knopf(
    key: str, saetze_an: dict[str, bool], sichtbar: bool, danach: Callable[[], None]
) -> ft.Chip:
    """„Sätze“ (Ben, 18.10.2026): ausgegraut = aus, eine Zahl je Eintrag („263“);
    angetippt = an, Eingabe je Satz („3 × 15“). ``danach`` läuft nach jedem Umschalten."""
    text = ft.Text("Sätze", opacity=1.0 if saetze_an[key] else 0.55)

    def umschalten() -> None:
        saetze_an[key] = not saetze_an[key]
        knopf.selected = saetze_an[key]
        text.opacity = 1.0 if saetze_an[key] else 0.55
        with contextlib.suppress(Exception):
            knopf.update()
        danach()

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


def parameter_name(vorlage: FieldSpec) -> str:
    """So heißt der Knopf eines Vorratsfelds: der Name ohne Bereich („Skala“)."""
    return "Skala" if vorlage.type == FieldType.SCALE else vorlage.label


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
    #: Die ID nach dem ersten Speichern — eine neue Übung hat erst dann eine
    gespeichert: dict[str, str] = {}

    # -- Kopf: Symbol oder Bild, Name ----------------------------------------------------

    bild_stand: dict[str, Any] = {
        "key": uebung.icon_key if uebung and uebung.icon_key else AUSWAHL[0],
        "bild": uebung.image_path if uebung else None,
    }
    symbol_kachel = ft.Container(
        width=SYMBOL_GROESSE,
        height=SYMBOL_GROESSE,
        border_radius=18,
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
        alignment=ft.Alignment.CENTER,
        ink=True,
        tooltip="Symbol oder Bild wählen",
    )

    def symbol_zeichnen() -> None:
        mit_bild = bool(bild_stand["bild"])
        symbol_kachel.content = uebungsbild(
            state,
            bild_stand["key"],
            bild_stand["bild"],
            groesse=SYMBOL_GROESSE if mit_bild else 40,
        )
        symbol_kachel.bgcolor = None if mit_bild else ft.Colors.SECONDARY_CONTAINER
        with contextlib.suppress(Exception):
            symbol_kachel.update()

    def gewaehlt_setzen(key: str, bild: str | None) -> None:
        bild_stand["key"], bild_stand["bild"] = key, bild
        symbol_zeichnen()

    async def foto_hochladen() -> None:
        """Am Handy die Fotoauswahl (verkleinert, ohne Ort — `views/anhang_hochladen.py`),
        am Rechner der Dateidialog; die Übung wird vorher gespeichert (sie braucht eine ID)."""
        if state.hochladen is not None:
            await wechseln(
                lambda formular: hochladen_route(formular, Ziel.fuer_uebung(gespeichert["id"]))
            )
            return
        try:
            dateien = await ft.FilePicker().pick_files(
                dialog_title="Bild als Symbol", allowed_extensions=["jpg", "jpeg", "png"]
            )
        except Exception as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Auswahl: {fehler}")))
            return
        pfad = next((d.path for d in dateien or [] if getattr(d, "path", None)), None)
        if not pfad:
            return
        try:
            rel = state.uebungsbilder.schreiben(Path(pfad).read_bytes())
        except OSError as fehler:
            page.show_dialog(ft.SnackBar(ft.Text(f"Nicht gespeichert: {fehler}")))
            return
        gewaehlt_setzen(bild_stand["key"], rel)

    async def foto_aufnehmen() -> None:
        await wechseln(
            lambda formular: aufnahme_route(formular, Ziel.fuer_uebung(gespeichert["id"]), BILD)
        )

    def symbol_waehlen() -> None:
        page.show_dialog(
            symbol_blatt(
                page,
                state,
                uebung_id=uebung.id if uebung is not None else None,
                icon_key=bild_stand["key"],
                bild=bild_stand["bild"],
                waehlen=gewaehlt_setzen,
                hochladen=foto_hochladen,
                aufnehmen=foto_aufnehmen,
            )
        )

    symbol_kachel.on_click = symbol_waehlen
    symbol_zeichnen()
    name = ft.TextField(
        label="Name",
        value=uebung.name if uebung else "",
        autofocus=neu,
        text_size=20,
        expand=True,
        capitalization=ft.TextCapitalization.SENTENCES,
    )

    # -- Beschreibung: Abschnitte (Name + Inhalt), Editor an Ort und Stelle (P108) -------
    # Ben, 2.11.2026: „den Text als ‚Name‘ + ‚Inhalt‘ setzen … Nur die Reihenfolge ist wichtig“
    # — gespeichert bleibt ein Text mit ``## Name``-Zeilen (`core/beschreibung.py`).

    abschnitt_stand: list[dict[str, Any]] = [
        {"id": new_id(), "name": a.name, "text": a.text}
        for a in abschnitte(uebung.description if uebung else "")
    ]
    beschreibung_spalte = ft.Column(spacing=8, tight=True)
    #: Der offene Abschnitt (seine ID), je Abschnitt sein Editor und sein Namensfeld
    beschreibung_offen: dict[str, str | None] = {"id": None}
    editoren: dict[str, Textnotiz] = {}
    abschnitt_namen: dict[str, ft.TextField] = {}

    def abschnitt_text(a: dict[str, Any]) -> str:
        e = editoren.get(a["id"])
        if e is not None and beschreibung_offen["id"] == a["id"]:
            return e.text.strip()
        return str(a["text"]).strip()

    def abschnitt_name(a: dict[str, Any]) -> str:
        feld = abschnitt_namen.get(a["id"])
        return ((feld.value if feld is not None else a["name"]) or "").strip()

    def beschreibung_text() -> str:
        return zusammen(Abschnitt(abschnitt_name(a), abschnitt_text(a)) for a in abschnitt_stand)

    def beschreibung_neu() -> None:
        beschreibung_zeichnen()
        with contextlib.suppress(Exception):
            beschreibung_spalte.update()

    def abschnitt_geschlossen() -> None:
        aid = beschreibung_offen["id"]
        a = next((x for x in abschnitt_stand if x["id"] == aid), None)
        if a is not None:
            a["text"], a["name"] = abschnitt_text(a), abschnitt_name(a)
        beschreibung_offen["id"] = None
        beschreibung_neu()

    def abschnitt_oeffner(a: dict[str, Any]) -> Callable[[], None]:
        def handler() -> None:
            beschreibung_offen["id"] = a["id"]
            e = editoren.get(a["id"])
            if e is None:

                def sichern_text(text: str, ziel: dict[str, Any] = a) -> None:
                    ziel["text"] = text

                e = editoren[a["id"]] = Textnotiz(
                    page,
                    state,
                    str(a["text"]),
                    sichern_text,
                    schluessel=f"uebung:{uebung.id if uebung is not None else 'neu'}:{a['id']}",
                    hinweis="Inhalt … Ausführung, worauf achten. Tippen oder diktieren.",
                    danach=abschnitt_geschlossen,
                )
            e.fokus = True
            beschreibung_neu()

        return handler

    def abschnitt_hoch(a: dict[str, Any]) -> Callable[[], None]:
        def handler() -> None:
            k = abschnitt_stand.index(a)
            if k > 0:
                abschnitt_stand.insert(k - 1, abschnitt_stand.pop(k))
            beschreibung_neu()

        return handler

    def abschnitt_entferner(a: dict[str, Any]) -> Callable[[], None]:
        def handler() -> None:
            abschnitt_stand.remove(a)
            editoren.pop(a["id"], None)
            abschnitt_namen.pop(a["id"], None)
            if beschreibung_offen["id"] == a["id"]:
                beschreibung_offen["id"] = None
            beschreibung_neu()

        return handler

    def abschnitt_hinzufuegen() -> None:
        a = {"id": new_id(), "name": "", "text": ""}
        abschnitt_stand.append(a)
        abschnitt_oeffner(a)()

    def abschnitt_karte(a: dict[str, Any], k: int) -> ft.Control:
        aid = a["id"]
        offen = beschreibung_offen["id"] == aid
        if aid not in abschnitt_namen:
            abschnitt_namen[aid] = ft.TextField(
                label="Name des Abschnitts",
                value=str(a["name"]),
                hint_text="z. B. Ausführung, Worauf achten, Für mich",
                dense=True,
                expand=True,
                capitalization=ft.TextCapitalization.SENTENCES,
            )
        if offen:
            inhalt: list[ft.Control] = [
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        abschnitt_namen[aid],
                        ft.IconButton(
                            ft.Icons.ARROW_UPWARD,
                            tooltip="Nach oben",
                            visible=k > 0,
                            on_click=abschnitt_hoch(a),
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            tooltip="Abschnitt entfernen",
                            on_click=abschnitt_entferner(a),
                        ),
                    ],
                ),
                editoren[aid].control(),
            ]
            return ft.Container(
                bgcolor=KARTE,
                border_radius=14,
                padding=ft.Padding.only(left=12, right=10, top=8, bottom=10),
                content=ft.Column(spacing=6, tight=True, controls=inhalt),
            )
        name_ = abschnitt_name(a)
        text = abschnitt_text(a)
        return ft.Container(
            bgcolor=KARTE,
            border_radius=14,
            padding=ft.Padding.only(left=12, right=10, top=8, bottom=10),
            ink=True,
            on_click=abschnitt_oeffner(a),
            content=ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                name_ or ("Beschreibung" if k == 0 else "Abschnitt"),
                                size=12,
                                weight=ft.FontWeight.W_600,
                                opacity=0.7,
                            ),
                            ft.Icon(ft.Icons.EDIT_OUTLINED, size=16, opacity=0.5),
                        ],
                    ),
                    ft.Text(
                        text or "Noch nichts — antippen und beschreiben.",
                        size=14,
                        opacity=1.0 if text else 0.55,
                    ),
                ],
            ),
        )

    def beschreibung_zeichnen() -> None:
        karten: list[ft.Control] = [abschnitt_karte(a, k) for k, a in enumerate(abschnitt_stand)]
        if not abschnitt_stand:
            karten.append(
                ft.Text("Noch keine Beschreibung — „Abschnitt hinzufügen“.", size=12, opacity=0.6)
            )
        karten.append(
            ft.Row(
                controls=[
                    ft.TextButton(
                        "Abschnitt hinzufügen",
                        icon=ft.Icons.ADD,
                        tooltip="Ein Abschnitt mit Name und Inhalt — z. B. vom Paket, für dich",
                        on_click=abschnitt_hinzufuegen,
                    )
                ]
            )
        )
        beschreibung_spalte.controls = karten

    beschreibung_zeichnen()

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

    # -- Parameter: Knöpfe oben, je eingeschaltetem eine Karte --------------------------
    # Ein Knopf je **Art** aus dem Feldvorrat; eingeschaltet, wenn die Übung ein Feld dieser
    # Art hat. Seit 2.11.2026 (P106) darf eine Übung mehrere Felder derselben Art tragen —
    # ``hold`` und ``hold_2``, zwei Skalen (`core.result_spec.naechster_key`): „+“ auf der
    # Karte legt das nächste an, ✕ nimmt eins weg. Zur Wahl stehen die Chips der Übung und
    # die des Vorrats; das ✕ an einem ungenutzten Chip nimmt ihn aus der Wahl (Punkt 4): ein
    # eigener Chip ist damit weg, ein Vorschlag des Vorrats steht beim nächsten Öffnen wieder
    # da (Ben, 18.10.2026: „leer heißt leer“ — die Vorschläge bleiben Vorschläge).

    #: Ein Chip je Art — ``selected`` ist der Schalter
    schalter: dict[str, ft.Chip] = {}
    #: Je Art die eingeschalteten Felder (``hold``, ``hold_2`` …) — und was zuletzt an war,
    #: damit ein Aus- und Einschalten der Art sie zurückbringt
    aktiv: dict[str, list[str]] = {v.key: [] for v in FELDVORRAT}
    gemerkt_aktiv: dict[str, list[str]] = {}
    #: Je Feld der eigene Name (`FieldSpec.label`) — Punkt 6: „Einheiten benennen“
    namen: dict[str, ft.TextField] = {}
    #: Je Feld die Chips zur Wahl und die angetippten (P79: antippen statt Kommaliste)
    chips_kandidaten: dict[str, list[Any]] = {}
    chips_wahl: dict[str, list[Any]] = {}
    chips_reihen: dict[str, ft.Container] = {}
    #: Satzlisten: zählen die Sätze? Aus = eine Zahl je Eintrag (Ben, 18.10.2026)
    saetze_an: dict[str, bool] = {}
    saetze_knoepfe: dict[str, ft.Chip] = {}
    #: Skala: eigener Bereich statt fest 0–10 — auch negativ, Kommazahlen als solche
    skala_bereiche: dict[str, ft.TextField] = {}
    #: Das Ziel je Feld — ein kleines Formular je Karte, die Werte gemerkt über ein Aus-
    #: und wieder Einschalten (Punkt 7: Einstellung und Ziel auf einer Karte)
    ziel_formulare: dict[str, SpecForm] = {}
    ziel_gemerkt: dict[str, Any] = dict(uebung.default_target) if uebung else {}
    karten_spalte = ft.Column(spacing=10)

    def instanz_anlegen(key: str) -> None:
        """Der Stand eines Felds (Name, Chips, Sätze, Bereich) — aus der Übung oder, neu, aus
        dem Vorrat."""
        if key in namen:
            return
        vorlage = vorrat_feld(key)
        assert vorlage is not None
        quelle = vorhanden.get(key)
        namen[key] = ft.TextField(
            label="Name",
            value=basis_label(quelle) if quelle is not None else parameter_name(vorlage),
            dense=True,
            expand=True,
            capitalization=ft.TextCapitalization.SENTENCES,
        )
        if vorlage.type == FieldType.SCALE:
            skala_bereiche[key] = ft.TextField(
                label="Bereich",
                value=skala_bereich_text(quelle or vorlage),
                hint_text="0 - 10 · -5 - 5 · 0.0 - 10.0",
                helper="Kommazahlen so: 0.0 - 10.0",
                dense=True,
                width=200,
            )
        elif vorlage.type not in (FieldType.BOOL, FieldType.TEXT):
            # Leer heißt leer (Ben, 18.10.2026): ohne angetippten Chip nur das freie Feld
            chips_kandidaten[key] = chips_sortiert(
                [*vorlage.quick, *(quelle.quick if quelle is not None else [])]
            )
            chips_wahl[key] = chips_sortiert(list((quelle or vorlage).quick))
            chips_reihen[key] = ft.Container()
        if vorlage.type == FieldType.SET_LIST:
            saetze_an[key] = quelle.saetze if quelle is not None else True

    # (``basis`` ist der Weg zum Plan — die Art heißt hier ``art``)
    for key in vorhanden:
        art = basis_key(key)
        if art in aktiv and not var.ist_variante(vorhanden[key]):
            instanz_anlegen(key)
            aktiv[art].append(key)
    for art, keys in aktiv.items():
        aktiv[art] = instanzen(art, keys)
    if uebung is None:
        instanz_anlegen("reps")
        aktiv["reps"] = ["reps"]

    def aktive_keys() -> list[str]:
        """Alle eingeschalteten Felder in der Ordnung des Vorrats, je Art nach Nummer."""
        return [k for v in FELDVORRAT for k in aktiv[v.key]]

    def an(basis: str) -> bool:
        return bool(aktiv[basis])

    def chips_zeichnen(key: str) -> None:
        vorlage = vorrat_feld(key)
        assert vorlage is not None

        def umschalten(wert: Any) -> None:
            liste = chips_wahl[key]
            chips_wahl[key] = [w for w in liste if w != wert] if wert in liste else [*liste, wert]
            chips_neu(key)
            ziel_neu()

        def ergaenzen(neue: list[Any]) -> None:
            chips_kandidaten[key] = chips_sortiert([*chips_kandidaten[key], *neue])
            chips_wahl[key] = chips_sortiert([*chips_wahl[key], *neue])
            chips_neu(key)
            ziel_neu()

        def entfernen(wert: Any) -> None:
            chips_kandidaten[key] = [w for w in chips_kandidaten[key] if w != wert]
            chips_wahl[key] = [w for w in chips_wahl[key] if w != wert]
            chips_neu(key)

        dazu: list[ft.Control] = []
        if key in saetze_knoepfe:
            dazu.append(saetze_knoepfe[key])
        chips_reihen[key].content = chips_zeile(
            vorlage,
            chips_sortiert(chips_kandidaten[key]),
            chips_wahl[key],
            umschalten=umschalten,
            ergaenzen=ergaenzen,
            entfernen=entfernen,
            dazu=dazu,
        )

    def chips_neu(key: str) -> None:
        chips_zeichnen(key)
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            chips_reihen[key].update()

    def schalter_zeichnen(basis: str) -> None:
        schalter[basis].selected = an(basis)
        with contextlib.suppress(Exception):
            schalter[basis].update()

    def parameter_umschalter(basis: str) -> Callable[[Any], None]:
        def handler(_e: object = None) -> None:
            if aktiv[basis]:
                gemerkt_aktiv[basis] = list(aktiv[basis])
                aktiv[basis] = []
            else:
                aktiv[basis] = gemerkt_aktiv.get(basis) or [basis]
                for key in aktiv[basis]:
                    instanz_anlegen(key)
            schalter_zeichnen(basis)
            karten_neu()
            uhr_zeichnen()

        return handler

    def noch_eine(basis: str) -> Callable[[], None]:
        """„+“ auf der Karte: ein weiteres Feld dieser Art — gleicher Typ, eigener Name,
        eigene Chips (P106)."""

        def handler() -> None:
            key = naechster_key(basis, aktive_keys())
            instanz_anlegen(key)
            aktiv[basis] = instanzen(basis, [*aktiv[basis], key])
            karten_neu()
            uhr_zeichnen()

        return handler

    def instanz_entferner(key: str) -> Callable[[], None]:
        def handler() -> None:
            basis = basis_key(key)
            aktiv[basis] = [k for k in aktiv[basis] if k != key]
            schalter_zeichnen(basis)
            karten_neu()
            uhr_zeichnen()

        return handler

    for vorlage in FELDVORRAT:
        schalter[vorlage.key] = ft.Chip(
            label=ft.Text(parameter_name(vorlage)),
            selected=an(vorlage.key),
            show_checkmark=True,
            tooltip=f"{vorlage.label}{f' ({vorlage.unit})' if vorlage.unit else ''}",
            on_select=parameter_umschalter(vorlage.key),
        )
    parameter_knoepfe = ft.Row(
        wrap=True, spacing=6, run_spacing=6, controls=list(schalter.values())
    )
    # Felder, die nicht im Vorrat stehen (ältere oder besondere), bleiben erhalten — die
    # Varianten haben ihren eigenen Abschnitt.
    fremde = [
        f for key, f in vorhanden.items() if basis_key(key) not in aktiv and not var.ist_variante(f)
    ]

    def ziel_werte() -> dict[str, Any]:
        """Alles, was in den Zielformularen steht — auch für ausgeschaltete gemerkt."""
        for form in ziel_formulare.values():
            ziel_gemerkt.update(form.werte())
        return dict(ziel_gemerkt)

    def ziel_feld_fuer(key: str) -> FieldSpec | None:
        return next((f for f in ziel_spec(spec_aktuell()).fields if f.key == key), None)

    def karte(key: str) -> ft.Control:
        """Die Karte eines eingeschalteten Felds: Name und Einheit, „+“ für ein weiteres
        dieser Art, ✕ (ab dem zweiten), Chips (mit „Sätze“), Bereich der Skala — und das
        Ziel."""
        vorlage = vorrat_feld(key)
        assert vorlage is not None
        basis = basis_key(key)
        kopf: list[ft.Control] = [namen[key]]
        if vorlage.unit:
            kopf.append(ft.Text(vorlage.unit, size=13, opacity=0.7))
        if vorlage.type not in (FieldType.BOOL, FieldType.TEXT):
            kopf.append(
                ft.IconButton(
                    ft.Icons.ADD,
                    icon_size=20,
                    tooltip=f"Noch ein Feld „{parameter_name(vorlage)}“ — eigener Name und Chips",
                    on_click=noch_eine(basis),
                )
            )
        if len(aktiv[basis]) > 1:
            kopf.append(
                ft.IconButton(
                    ft.Icons.CLOSE,
                    icon_size=18,
                    tooltip="Dieses Feld entfernen",
                    on_click=instanz_entferner(key),
                )
            )
        teile: list[ft.Control] = [
            ft.Row(spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=kopf)
        ]
        if vorlage.type == FieldType.SCALE:
            teile.append(skala_bereiche[key])
        elif key in chips_reihen:
            if key in saetze_an and key not in saetze_knoepfe:
                saetze_knoepfe[key] = _saetze_knopf(key, saetze_an, True, ziel_neu)
            chips_zeichnen(key)
            teile.append(chips_reihen[key])
        elif vorlage.type == FieldType.BOOL:
            teile.append(
                ft.Text("Ein Haken beim Üben — für den offenen Eintrag.", size=12, opacity=0.6)
            )
        elif vorlage.type == FieldType.TEXT:
            teile.append(
                ft.Text("Ein Textfeld beim Üben — für den offenen Eintrag.", size=12, opacity=0.6)
            )
        ziel_feld = ziel_feld_fuer(key)
        if ziel_feld is not None:
            form = SpecForm(
                ResultSpec(fields=[replace(ziel_feld, label="Ziel")]),
                {key: ziel_gemerkt.get(key)},
                page=page,
                vorgaben=False,
            )
            ziel_formulare[key] = form
            teile.append(
                ft.Container(
                    padding=ft.Padding.only(top=4),
                    content=form.control,
                    tooltip="Was „Wie geplant“ beim Üben einträgt — in jedem Plan ohne eigenes",
                )
            )
        return ft.Container(
            bgcolor=KARTE,
            border_radius=14,
            padding=ft.Padding.only(left=12, right=10, top=6, bottom=10),
            content=ft.Column(spacing=8, tight=True, controls=teile),
        )

    def karten_zeichnen() -> None:
        ziel_werte()  # die Werte der alten Formulare merken, bevor sie ersetzt werden
        ziel_formulare.clear()
        karten: list[ft.Control] = [karte(k) for k in aktive_keys()]
        if fremde:
            karten.append(
                ft.Text(
                    "Weitere Felder dieser Übung bleiben erhalten: "
                    + ", ".join(f.label for f in fremde),
                    size=12,
                    opacity=0.6,
                )
            )
        if not karten:
            karten.append(ft.Text("Kein Parameter — „Gemacht“ hakt nur ab.", size=12, opacity=0.6))
        karten_spalte.controls = karten

    def karten_neu() -> None:
        karten_zeichnen()
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            karten_spalte.update()

    def ziel_neu() -> None:
        """Chips, „Sätze“ oder Varianten haben sich geändert: die Zielformulare folgen."""
        karten_neu()
        ziel_variante_neu()

    # -- Varianten (Ben, 21.10.2026; Skizzen D3, D4) -----------------------------------------
    # Gehalten im Formular — „Abbrechen“ verwirft auch hier. Bisherige Einträge umbenennen
    # (Skizze A5) geschieht erst beim Speichern, sonst passten Übung und Einträge nach einem
    # Abbrechen nicht mehr zusammen.

    varianten_liste: list[var.Variante] = var.varianten(uebung.result_spec) if uebung else []
    #: (alt, neu): bisherige Einträge beim Speichern mitnehmen
    umbenennen: list[tuple[str, str]] = []
    varianten_spalte = ft.Column(spacing=2)
    #: Die Ziel-Variante (das Ziel kann eine Variante vorgeben) — unter den Varianten
    ziel_variante_bereich = ft.Container()

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

    def ziel_variante_zeichnen() -> None:
        ziel_werte()
        ziel_formulare.pop(var.VARIANTE, None)
        feld = ziel_feld_fuer(var.VARIANTE)
        if feld is None:
            ziel_variante_bereich.content = None
            ziel_variante_bereich.visible = False
            return
        form = SpecForm(
            ResultSpec(fields=[replace(feld, label="Ziel-Variante")]),
            {var.VARIANTE: ziel_gemerkt.get(var.VARIANTE)},
            page=page,
            vorgaben=False,
        )
        ziel_formulare[var.VARIANTE] = form
        ziel_variante_bereich.visible = True
        ziel_variante_bereich.content = ft.Container(
            padding=ft.Padding.only(top=4),
            content=form.control,
            tooltip="Welche Variante „Wie geplant“ wählt — leer: keine Vorgabe",
        )

    def ziel_variante_neu() -> None:
        ziel_variante_zeichnen()
        with contextlib.suppress(Exception):
            ziel_variante_bereich.update()

    def varianten_neu_zeichnen() -> None:
        varianten_zeichnen()
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            varianten_spalte.update()
        ziel_neu()

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
            neu_ = var.Variante(neuer_name, symbol_wahl["key"], kuerzel, text)
            varianten_liste[:] = var.ersetzen(varianten_liste, bisher, neu_)
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
                ],
            ),
            actions=aktionen,
        )
        page.show_dialog(dialog)

    varianten_zeichnen()

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
        segments=[ft.Segment(value="hold", label=ft.Text("Haltezeit"))],
        selected=[uhr_vorher or "hold"],
        allow_empty_selection=False,
        show_selected_icon=False,
    )

    def zeitfelder() -> list[str]:
        """Die Zeitfelder der Übung (Haltezeiten, Zeiten) — „Zeit“ immer, auch ohne den
        Parameter (die Uhr trägt sie ein)."""
        keys = [k for k in aktive_keys() if basis_key(k) in ("hold", "duration")]
        return keys if "duration" in keys else [*keys, "duration"]

    def zaehlt_als_zeichnen() -> None:
        """Die Wahl „zählt als“ folgt den Zeitfeldern (P106: je Zeitfeld ein Knopf, mit
        seinem Namen)."""
        keys = zeitfelder()

        def beschriftung(k: str) -> str:
            if k not in namen:
                return "Zeit"
            vorlage = vorrat_feld(k)
            return (namen[k].value or "").strip() or (vorlage.label if vorlage else k)

        zaehlt_als_wahl.segments = [
            ft.Segment(value=k, label=ft.Text(beschriftung(k))) for k in keys
        ]
        gewaehlt = next(iter(zaehlt_als_wahl.selected or []), "")
        if gewaehlt not in keys:
            halten = [k for k in keys if basis_key(k) == "hold"]
            zaehlt_als_wahl.selected = [halten[0] if halten else "duration"]

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
        """„Zählt als“ nur mit Haltezeit — sonst zählt die Uhr immer als Zeit. Der Stand in
        einem Satz; die Erklärung steht im (i)."""
        an_ = bool(uhr_schalter.value)
        zaehlt = bool(zaehlt_schalter.value)
        halten = an("hold")
        zaehlt_als_zeichnen()
        zaehlt_schalter.visible = an_
        zaehlt_als_zeile.visible = an_ and zaehlt and halten
        if not an_:
            uhr_text.value = "Keine Uhr — „Gemacht“ hakt nur ab."
        elif not zaehlt:
            uhr_text.value = "Läufe tragen nur „gemacht“ ein."
        elif halten:
            uhr_text.value = "Jeder Lauf: ein Satz im offenen Eintrag."
        else:
            uhr_text.value = "Jeder Lauf zählt als Zeit im offenen Eintrag."
        with contextlib.suppress(Exception):  # noch nicht auf der Seite
            uhr_spalte.update()

    def zaehlt_als_lesen() -> str:
        """Die Vorgabe (Haltezeit) bleibt leer, solange nie etwas anderes gewählt war — eine
        Paketübung gilt sonst als „geändert: Zählt als“."""
        wahl = str(next(iter(zaehlt_als_wahl.selected or []), "hold"))
        vorgabe = next((k for k in zeitfelder() if basis_key(k) == "hold"), "hold")
        return "" if wahl == vorgabe and not uhr_vorher else wahl

    async def wechseln(
        ziel: str | Callable[[str], str] | None = None, profil_id: str | None = None
    ) -> None:
        """Weiter zu ``ziel`` (ein Weg, oder einer aus dem Weg des Formulars; sonst in den
        Profil-Editor) — das Formular speichert vorher (beim Zurückkommen entsteht es aus der
        Datenbank neu). Fehlt etwas (Name), bleibt es hier."""
        if sichern() is not None:
            return
        formular = f"/uebung/{gespeichert['id']}/bearbeiten"
        if uebung is None and state.navigation[-1:] == [route]:
            # Die neue Übung ist jetzt gespeichert: An die Stelle von „Neue Übung“ tritt ihr
            # Formular — Zurück führt dorthin, nicht in ein leeres Formular und nicht an ihm
            # vorbei (`ui/navigation.py`)
            state.navigation[-1] = formular
        if callable(ziel):
            ziel = ziel(formular)
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
        for key in aktive_keys():
            vorlage_feld = vorrat_feld(key)
            assert vorlage_feld is not None
            alt = vorhanden.get(key)
            chips = chips_wahl.get(
                key, list((alt or vorlage_feld).quick)
            )  # Skala, Ja/Nein, Freitext: wie sie sind
            label = (namen[key].value or "").strip() or parameter_name(vorlage_feld)
            feld = replace(
                vorlage_feld,
                label=label,
                quick=chips_sortiert(chips),
                default=alt.default if alt is not None else vorlage_feld.default,
                saetze=saetze_an.get(key, True),
            )
            if feld.type == FieldType.SCALE:
                bereich = skala_bereiche[key].value or ""
                lo, hi, schritt = skala_lesen(bereich) or (0.0, 10.0, 1.0)
                ganz = float(schritt).is_integer()
                feld = replace(
                    feld,
                    min=int(lo) if ganz else lo,
                    max=int(hi) if ganz else hi,
                    step=int(schritt) if ganz else schritt,
                    default=None,
                )
            felder.append(feld)
        felder.extend(fremde)
        return felder

    def spec_aktuell() -> ResultSpec:
        """Die Spezifikation, wie „Speichern“ sie jetzt schriebe — für das Ziel."""
        return var.mit_varianten(spec_bauen(felder_lesen()), varianten_liste)

    def ziel_lesen(spec: ResultSpec) -> dict[str, Any]:
        """Nur Werte, die es in der neuen Spezifikation noch gibt und die etwas sagen."""
        return ziel_bereinigen(ziel_werte(), spec)

    karten_zeichnen()
    ziel_variante_zeichnen()

    def eingelesen() -> Exercise:
        ziel = uebung if uebung is not None else Exercise()
        ziel.name = (name.value or "").strip()
        ziel.typen = typen_lesen()
        ziel.category = ziel.typen[0] if ziel.typen else ""
        ziel.description = beschreibung_text()
        ziel.icon_key = bild_stand["key"]
        ziel.image_path = bild_stand["bild"]
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
            beschreibung_text(),
            typen_lesen(),
            regionen_lesen(),
            [
                (
                    k,
                    list(chips_wahl.get(k, [])),
                    namen[k].value or "",
                    (skala_bereiche[k].value or "") if k in skala_bereiche else "",
                )
                for k in aktive_keys()
            ],
            sorted(saetze_an.items()),
            ziel_werte(),
            bild_stand["key"],
            bild_stand["bild"],
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
        for key in aktiv["scale"]:
            feld = skala_bereiche[key]
            if skala_lesen(feld.value or "") is None:
                feld.error = "z. B. 0 - 10 oder -5 - 5 oder 0.0 - 10.0"
                page.update()
                return "Der Bereich der Skala ist unlesbar (z. B. 0 - 10)."
            feld.error = None
        ziel = eingelesen()
        state.uebungen.speichern(ziel)
        if im_plan and plan is not None and not gespeichert.get("im_plan"):
            # Aus „Übung hinzufügen“: Sie kommt gleich in den Plan — und folgt der Übung (P79)
            state.plaene.uebung_hinzufuegen(plan.id, ziel.id)
            gespeichert["im_plan"] = plan.id
        gespeichert["id"] = ziel.id
        # Umbenannte Varianten: die bisherigen Einträge erst jetzt mitnehmen (Skizze A5)
        for alt, neu_ in umbenennen:
            state.sitzungen.variante_umbenennen(state.profil.id, ziel.id, alt, neu_)
        umbenennen.clear()
        return None

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
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
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
                        ft.Row(
                            spacing=14,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[symbol_kachel, name],
                        ),
                        abschnitt("BESCHREIBUNG"),
                        beschreibung_spalte,
                        abschnitt("PARAMETER", hilfe_knopf(page, thema="parameter")),
                        parameter_knoepfe,
                        karten_spalte,
                        abschnitt("VARIANTEN", hilfe_knopf(page, thema="varianten")),
                        varianten_spalte,
                        ziel_variante_bereich,
                        ft.TextButton(
                            "Variante hinzufügen",
                            icon=ft.Icons.SELL_OUTLINED,
                            on_click=varianten_bearbeiter(None),
                        ),
                        abschnitt("UHR UND TIMER", hilfe_knopf(page, thema="uhr")),
                        uhr_spalte,
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
                        abschnitt("VIDEOS UND LINKS"),
                        medien_spalte,
                        ft.TextButton(
                            "Link hinzufügen",
                            icon=ft.Icons.ADD_LINK,
                            on_click=link_hinzufuegen,
                        ),
                        abschnitt("ORDNEN", hilfe_knopf(page, thema="uebungen")),
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
                    ],
                ),
                expand=False,
            )
        ],
    )
    return zurueck_speichert(page, ansicht, geaendert=lambda: stand() != anfang, speichern=sichern)


__all__ = ["KARTE", "SYMBOL_GROESSE", "parameter_name", "spec_bauen", "uebung_bearbeiten"]
