"""Ein Tagesfeld eintragen — das Blatt von unten (Ben, 21.10.2026, Skizzen A3–A5).

- **Skala** als Schiebebalken (Ben: „Skalen sollen als Schiebebalken dargestellt
  werden“, `components/skala_regler.py`). Einmal am Tag schreibt das Loslassen den Wert
  (eine Korrektur, wenn es schon einen gab); mehrmals trägt „Eintragen“ ihn mit Uhrzeit ein.
- **Anzahl, Menge, Dauer**: die Schnellknöpfe („+1 · 400“, „+250“), dazu ein freier Wert.
  Mehrmals ist jeder Tipp ein eigener Eintrag; einmal am Tag zählen sie zum Wert des Tags.
- **Ja/Nein**: zwei Knöpfe. **Nur Text**: ein Textfeld, das beim Schließen speichert.
- **Varianten** oben als Segment; die Wahl gilt auch für den Schnellknopf unter Heute
  (`AppState.tagesfeld_varianten`).
- **Uhrzeit** (mehrmals): heute leer = jetzt. An einem vergangenen Tag ist die alte Zeit
  vorbelegt (Ben: „Zeit festlegen, dabei soll die alte Zeit genommen werden als
  Vorlage“, `core.tagesfelder.uhrzeit_vorlage`); ein geänderter Eintrag behält seine Zeit,
  bis man sie ändert.
- **Messwert** (Ben, 28.10.2026): die Teile als Zahlenfelder nebeneinander („sys · dia ·
  Puls“), „128/82“ ins erste Feld verteilt sich; kein Schnellknopf, nichts addiert sich.
- Die Einträge des Tags stehen darunter — auch bei „einmal am Tag“ (Plan §5, Punkt 4):
  antippen ändert Uhrzeit, Variante (auch eine inzwischen entfernte), Wert und Notiz, ✕
  löscht. Einheiten stehen an jedem Feld (Ben: „Immer Einheiten mit angeben“).

Was sofort geschrieben wird (Tipps, Loslassen), steht sofort in der Datenbank; Texte
(Notiz, nur Text, freier Wert bei „einmal“) speichern beim Schließen („Zurück speichert“).
Die Ansicht darunter frischt erst auf, wenn das Blatt zu ist (`dialoge.Nachher`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any, cast

import flet as ft

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core.models import jetzt
from trainingsapp.core.tag import uhrzeit_lesen
from trainingsapp.core.verlauf import WOCHENTAGE
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.skala_regler import skala_regler
from trainingsapp.ui.state import AppState


def tag_text(tag: date, heute: date) -> str:
    """„heute“, „gestern“ oder „Mo 19.10.“."""
    if tag == heute:
        return "heute"
    if (heute - tag).days == 1:
        return "gestern"
    return f"{WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}"


def gewaehlte_variante(state: AppState, feld: tf.Tagesfeld) -> str:
    """Die zuletzt gewählte Variante — gibt es sie nicht (mehr), die erste; ohne leer."""
    namen = feld.varianten
    gemerkt = state.tagesfeld_varianten.get(feld.id, "")
    if gemerkt in namen:
        return gemerkt
    return namen[0] if namen else ""


def werte_des_felds(state: AppState, feld: tf.Tagesfeld, tag: date) -> list[tf.Tageswert]:
    return [w for w in state.tageswerte.am_tag(state.profil.id, tag) if w.feld_id == feld.id]


def vorlage_zeit(state: AppState, feld: tf.Tagesfeld, tag: date) -> time:
    """Die alte Zeit als Vorlage beim Nachtragen (`core.tagesfelder.uhrzeit_vorlage`)."""
    frueher = state.tageswerte.zwischen(state.profil.id, None, tag, [feld.id])
    return tf.uhrzeit_vorlage(werte_des_felds(state, feld, tag), frueher)


def neue_zeit(state: AppState, feld: tf.Tagesfeld, tag: date) -> datetime:
    """Wann ein Schnellknopf einträgt: heute jetzt, an einem anderen Tag die Vorlage."""
    if tag == state.heute():
        return jetzt()
    return tf.zeitpunkt(tag, vorlage_zeit(state, feld, tag))


def schnell_eintragen(
    state: AppState, feld: tf.Tagesfeld, tag: date, menge: float
) -> tuple[tf.Tageswert, str]:
    """Ein Schnellknopf: mehrmals ein neuer Eintrag, einmal am Tag dazu zum Wert des Tags.
    Gibt den neuen Wert (für „Rückgängig“) und den Text der Meldung zurück."""
    variante = gewaehlte_variante(state, feld)
    f = tf.wertfeld(feld.spec)
    knopf = tf.schnell_text(f, menge) if f is not None else f"+{menge:g}"
    if feld.mehrmals:
        w = state.tageswerte.hinzufuegen(
            feld,
            tag,
            neue_zeit(state, feld, tag),
            wert=tf.plus(feld.spec, None, menge),
            variante=variante,
        )
    else:
        alt = tf.einmal_ziel(werte_des_felds(state, feld, tag), variante)
        w = state.tageswerte.einmal_setzen(
            feld,
            tag,
            wert=tf.plus(feld.spec, alt.wert if alt else None, menge),
            variante=variante,
            zeit=None if alt else neue_zeit(state, feld, tag),
        )
    name = f"{feld.name} {variante}".strip()
    stand = tf.stand_text(feld, tf.tagesstand(feld, werte_des_felds(state, feld, tag)))
    return w, f"{name} {knopf} → {stand}"


def tagesfeld_blatt(
    page: Any,
    state: AppState,
    feld: tf.Tagesfeld,
    tag: date,
    *,
    danach: Callable[[], Any] | None = None,
    bearbeiten: Callable[[], Any] | None = None,
) -> ft.BottomSheet:
    """Das Blatt eines Tagesfelds an ``tag``. ``danach`` läuft, wenn es zu ist und sich
    etwas geändert hat; ``bearbeiten`` öffnet die Einstellungen des Felds (nach dem
    Schließen)."""
    heute = state.heute()
    nachher = Nachher()
    geaendert: list[bool] = []
    #: Texte, die beim Schließen speichern — je Name eine Funktion
    ausstehend: dict[str, Callable[[], None]] = {}
    #: Welcher Eintrag gerade aufgeklappt bearbeitet wird
    offen: dict[str, str | None] = {"id": None}
    #: Die zuletzt hier eingetippte Uhrzeit — Vorlage für den nächsten Eintrag
    zuletzt: dict[str, time | None] = {"uhr": None}
    art = feld.art
    f = tf.wertfeld(feld.spec)
    inhalt = ft.Column(tight=True, spacing=14, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    fehler = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False)

    #: Nur Text, mehrmals: der nächste Text — bleibt beim Neuzeichnen stehen, das Schließen
    #: trägt ihn ein
    neuer_text = ft.TextField(
        label="Text", hint_text="Tippen oder diktieren", multiline=True, min_lines=2
    )

    def werte() -> list[tf.Tageswert]:
        return werte_des_felds(state, feld, tag)

    def neuen_text_sichern() -> None:
        text = (neuer_text.value or "").strip()
        if text and art == tf.TEXT and feld.mehrmals:
            neuer_text.value = ""
            state.tageswerte.hinzufuegen(
                feld, tag, neue_zeit(state, feld, tag), variante=variante(), note=text
            )
            merken()

    def variante() -> str:
        return gewaehlte_variante(state, feld)

    def ziel() -> tf.Tageswert | None:
        return tf.einmal_ziel(werte(), variante())

    def merken() -> None:
        if not geaendert:
            geaendert.append(True)
            if danach is not None:
                nachher.danach(danach)

    def zeichnen() -> None:
        ausstehende_speichern()
        inhalt.controls = teile()
        with contextlib.suppress(Exception):  # noch nicht oder nicht mehr auf der Seite
            blatt.update()

    def melden(text: str) -> None:
        fehler.value = text
        fehler.visible = bool(text)
        with contextlib.suppress(Exception):
            fehler.update()

    def ausstehende_speichern() -> None:
        aktionen = list(ausstehend.values())
        ausstehend.clear()
        for aktion in aktionen:
            aktion()

    async def geschlossen(e: object = None) -> None:
        ausstehende_speichern()
        neuen_text_sichern()
        await nachher.bei_schliessen(e)

    def fertig(_e: object = None) -> None:
        ausstehende_speichern()
        neuen_text_sichern()
        schliessen(blatt)

    def feld_oeffnen(_e: object = None) -> None:
        ausstehende_speichern()
        neuen_text_sichern()
        if bearbeiten is not None:
            nachher.danach(bearbeiten)
        schliessen(blatt)

    # -- Uhrzeit -----------------------------------------------------------------------

    uhrzeit = ft.TextField(
        label="Uhrzeit",
        width=110,
        dense=True,
        keyboard_type=ft.KeyboardType.DATETIME,
        hint_text="jetzt" if tag == heute else None,
        value="" if tag == heute else f"{vorlage_zeit(state, feld, tag):%H:%M}",
    )

    def zeit_lesen() -> datetime | None:
        """Die Uhrzeit des nächsten Eintrags — ``None`` (mit Meldung) bei Unsinn."""
        text = (uhrzeit.value or "").strip()
        if not text:
            if tag == heute:
                return jetzt()
            text = f"{vorlage_zeit(state, feld, tag):%H:%M}"
        t = uhrzeit_lesen(text)
        if t is None:
            melden("Uhrzeit wie 8:30 oder 1845.")
            return None
        zeitpunkt = tf.zeitpunkt(tag, t)
        if tag == heute and zeitpunkt > jetzt():
            melden("Die Uhrzeit liegt in der Zukunft.")
            return None
        zuletzt["uhr"] = t
        melden("")
        return zeitpunkt

    def eintragen(wert: Any, note: str = "") -> None:
        """Mehrmals: ein neuer Eintrag mit der gewählten Uhrzeit."""
        zeit = zeit_lesen()
        if zeit is None:
            return
        state.tageswerte.hinzufuegen(feld, tag, zeit, wert=wert, variante=variante(), note=note)
        if zuletzt["uhr"] is not None and tag != heute:
            uhrzeit.value = f"{zuletzt['uhr']:%H:%M}"
        merken()
        zeichnen()

    def einmal(wert: Any, note: str | None = None) -> None:
        """Einmal am Tag: den Wert dieses Tags (und der Variante) setzen."""
        alt = ziel()
        state.tageswerte.einmal_setzen(
            feld,
            tag,
            wert=wert,
            variante=variante(),
            note=note,
            zeit=None if alt else neue_zeit(state, feld, tag),
        )
        merken()
        zeichnen()

    def einmal_loeschen() -> None:
        alt = ziel()
        if alt is not None:
            state.tageswerte.loeschen(alt.id)
            merken()
        zeichnen()

    # -- Teile -------------------------------------------------------------------------

    def kopf() -> ft.Control:
        stand = tf.stand_text(feld, tf.tagesstand(feld, werte()))
        return ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=0,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Text(
                            f"{feld.name} · {tag_text(tag, heute)}",
                            size=20,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(stand if stand != "–" else "noch nichts", size=12, opacity=0.7),
                    ],
                ),
                ft.IconButton(ft.Icons.CLOSE, tooltip="Schließen", on_click=fertig),
            ],
        )

    def varianten_wahl() -> ft.Control | None:
        if not feld.varianten:
            return None

        def gewechselt(e: ft.Event[ft.SegmentedButton]) -> None:
            if e.control.selected:
                ausstehende_speichern()
                state.tagesfeld_varianten[feld.id] = str(e.control.selected[0])
                offen["id"] = None
                zeichnen()

        je: dict[str, list[tf.Tageswert]] = {}
        for w in werte():
            je.setdefault(w.variante, []).append(w)

        def beschriftung(name: str) -> str:
            """„Knie 3“, „400 × 2“ — der Stand nennt die Variante schon; ohne Wert der Name."""
            liste = je.get(name, [])
            if not liste or art == tf.TEXT:
                return name
            stand = tf.stand_text(feld, tf.tagesstand(feld, liste))
            return name if stand == "–" else stand

        return ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            content=ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Text("VARIANTE", size=11, weight=ft.FontWeight.BOLD, opacity=0.7),
                    ft.SegmentedButton(
                        selected=[variante()],
                        segments=[
                            ft.Segment(value=n, label=ft.Text(beschriftung(n)))
                            for n in feld.varianten
                        ],
                        on_change=gewechselt,
                    ),
                ],
            ),
        )

    def notiz_feld(alt: tf.Tageswert | None) -> ft.Control:
        """Einmal am Tag: die Notiz zum Wert — speichert beim Schließen."""
        anfang = alt.note if alt else ""
        eingabe = ft.TextField(
            label="Notiz (optional)", value=anfang, multiline=True, min_lines=1, max_lines=4
        )

        def sichern() -> None:
            neu = (eingabe.value or "").strip()
            if neu == anfang.strip():
                return
            jetzt_ziel = ziel()
            if jetzt_ziel is not None:
                state.tageswerte.korrigieren(jetzt_ziel.id, note=neu)
            elif neu:
                state.tageswerte.einmal_setzen(
                    feld, tag, variante=variante(), note=neu, zeit=neue_zeit(state, feld, tag)
                )
            merken()

        ausstehend[f"notiz:{variante()}"] = sichern
        return eingabe

    def skala_teile() -> list[ft.Control]:
        assert f is not None
        if not feld.mehrmals:
            alt = ziel()

            def gesetzt(x: float | int | None) -> None:
                ausstehende_speichern()
                if x is None:
                    einmal_loeschen()
                else:
                    einmal(x)

            return [
                skala_regler(f, alt.wert if alt else None, gesetzt),
                ft.Text(
                    "Einmal am Tag: Ein neuer Wert ändert den von "
                    f"{tag_text(tag, heute)}"
                    + (f" (gesetzt um {alt.zeit.astimezone():%H:%M})." if alt else "."),
                    size=12,
                    opacity=0.7,
                ),
                notiz_feld(alt),
            ]
        gewaehlt: dict[str, float | int | None] = {"x": None}

        def bewegt(x: float | int | None) -> None:
            gewaehlt["x"] = x

        def los(_e: object = None) -> None:
            if gewaehlt["x"] is None:
                melden("Erst den Wert am Balken wählen.")
                return
            eintragen(gewaehlt["x"])

        return [
            skala_regler(f, None, bewegt, loeschbar=False),
            ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    uhrzeit,
                    ft.FilledButton("Eintragen", icon=ft.Icons.ADD, on_click=los, expand=True),
                ],
            ),
        ]

    def summen_teile() -> list[ft.Control]:
        assert f is not None
        v = variante()
        knoepfe: list[ft.Control] = [
            ft.FilledButton(
                f"{tf.schnell_text(f, q)}" + (f" · {v}" if v else ""),
                icon=ft.Icons.ADD,
                on_click=schnell(q),
                height=48,
            )
            for q in feld.schnell
        ]
        frei = ft.TextField(
            label={tf.ANZAHL: "Anzahl", tf.MENGE: "Menge", tf.DAUER: "Dauer"}[art]
            + (f" in {f.unit}" if f.unit and art != tf.DAUER else ""),
            hint_text="Minuten oder 1:30" if art == tf.DAUER else None,
            keyboard_type=ft.KeyboardType.TEXT if art == tf.DAUER else ft.KeyboardType.NUMBER,
            expand=True,
            dense=True,
        )
        teile: list[ft.Control] = []
        if knoepfe:
            teile.append(ft.Row(wrap=True, spacing=8, run_spacing=8, controls=knoepfe))
        if feld.mehrmals:

            def frei_eintragen(_e: object = None) -> None:
                wert = tf.wert_lesen(feld.spec, frei.value or "")
                if wert is None:
                    melden("Diesen Wert verstehe ich nicht.")
                    return
                frei.value = ""
                eintragen(wert)

            frei.on_submit = frei_eintragen
            teile.append(
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        frei,
                        uhrzeit,
                        ft.IconButton(ft.Icons.CHECK, tooltip="Eintragen", on_click=frei_eintragen),
                    ],
                )
            )
            return teile
        alt = ziel()
        frei.label = "Wert des Tages"
        frei.value = tf.eingabe_text(feld.spec, alt.wert if alt else None)
        anfang = frei.value

        def frei_setzen() -> None:
            text = (frei.value or "").strip()
            if text == anfang:
                return
            if not text:
                einmal_loeschen()
                return
            wert = tf.wert_lesen(feld.spec, text)
            if wert is not None:
                einmal(wert)

        def bestaetigt(_e: object = None) -> None:
            ausstehend.pop(f"wert:{v}", None)
            text = (frei.value or "").strip()
            if text and tf.wert_lesen(feld.spec, text) is None:
                melden("Diesen Wert verstehe ich nicht.")
                return
            frei_setzen()

        frei.on_submit = bestaetigt
        ausstehend[f"wert:{v}"] = frei_setzen
        teile.insert(
            0,
            ft.Text(
                tf.wert_text(feld.spec, alt.wert) if alt and alt.wert is not None else "–",
                size=28,
                weight=ft.FontWeight.W_700,
            ),
        )
        teile.append(
            ft.Row(
                controls=[
                    frei,
                    ft.IconButton(ft.Icons.CHECK, tooltip="Setzen", on_click=bestaetigt),
                ]
            )
        )
        teile.append(
            ft.Text(
                "Einmal am Tag: Die Knöpfe zählen zum Wert des Tages dazu.", size=12, opacity=0.7
            )
        )
        teile.append(notiz_feld(alt))
        return teile

    def messwert_teile() -> list[ft.Control]:
        """Messwert: je Teil ein Zahlenfeld, der erste nimmt auch „128/82“ für alle."""
        teile_spec = tf.teile_von(feld.spec)
        alt = None if feld.mehrmals else ziel()

        def feld_fuer(i: int, f: Any) -> ft.TextField:
            wert = alt.werte[i] if alt is not None and i < len(alt.werte) else None
            return ft.TextField(
                label=f.label + (f" ({f.unit})" if f.unit else ""),
                value="" if wert is None else tf.zahl(float(wert)),
                hint_text="optional"
                if not f.required
                else ("128/82" if i == 0 and len(teile_spec) > 1 else None),
                width=max(96, 12 * len(f.label) + 40),
                dense=True,
                keyboard_type=ft.KeyboardType.NUMBER
                if len(teile_spec) == 1
                else ft.KeyboardType.TEXT,
            )

        felder = [feld_fuer(i, f) for i, f in enumerate(teile_spec)]

        def lesen() -> tuple[Any, ...] | None:
            werte_ = tf.messwert_lesen(feld.spec, [x.value or "" for x in felder])
            if werte_ is None:
                grenzen = ", ".join(
                    f"{f.label} {tf.zahl(f.min)}–{tf.zahl(f.max)}"
                    for f in teile_spec
                    if f.min is not None and f.max is not None
                )
                melden("Bitte alle Pflichtteile als Zahl" + (f" ({grenzen})." if grenzen else "."))
                return None
            melden("")
            return werte_

        if feld.mehrmals:

            def los(_e: object = None) -> None:
                werte_ = lesen()
                if werte_ is None:
                    return
                for x in felder:
                    x.value = ""
                eintragen(werte_)

            for x in felder:
                x.on_submit = los
            return [
                ft.Row(
                    wrap=True, spacing=8, run_spacing=8, controls=cast(list[ft.Control], felder)
                ),
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        uhrzeit,
                        ft.FilledButton("Eintragen", icon=ft.Icons.ADD, on_click=los, expand=True),
                    ],
                ),
            ]

        def setzen(_e: object = None) -> None:
            ausstehend.pop("messwert", None)
            if all(not (x.value or "").strip() for x in felder):
                einmal_loeschen()
                return
            werte_ = lesen()
            if werte_ is not None:
                einmal(werte_)

        def still_sichern() -> None:
            """Zurück speichert: lesbare Teile übernehmen, sonst lassen."""
            if all(not (x.value or "").strip() for x in felder):
                return
            werte_ = tf.messwert_lesen(feld.spec, [x.value or "" for x in felder])
            if werte_ is not None and (alt is None or werte_ != alt.werte[: len(werte_)]):
                einmal(werte_)

        for x in felder:
            x.on_submit = setzen
        ausstehend["messwert"] = still_sichern
        return [
            ft.Text(
                tf.wert_text(feld.spec, alt.werte) if alt is not None else "–",
                size=28,
                weight=ft.FontWeight.W_700,
            ),
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=8,
                controls=[
                    *felder,
                    ft.IconButton(ft.Icons.CHECK, tooltip="Setzen", on_click=setzen),
                ],
            ),
            ft.Text("Einmal am Tag: Ein neuer Wert ändert den des Tages.", size=12, opacity=0.7),
            notiz_feld(alt),
        ]

    def schnell(menge: float) -> Callable[[object], None]:
        def handler(_e: object = None) -> None:
            ausstehende_speichern()
            if feld.mehrmals:
                eintragen(tf.plus(feld.spec, None, menge))
                return
            alt = ziel()
            einmal(tf.plus(feld.spec, alt.wert if alt else None, menge))

        return handler

    def ja_nein_teile() -> list[ft.Control]:
        if feld.mehrmals:
            return [
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.FilledButton("Ja", on_click=lambda: eintragen(True), expand=True),
                        ft.OutlinedButton("Nein", on_click=lambda: eintragen(False), expand=True),
                        uhrzeit,
                    ],
                )
            ]
        alt = ziel()
        gesetzt = None if alt is None or alt.wert is None else bool(alt.wert)

        def gewechselt(e: ft.Event[ft.SegmentedButton]) -> None:
            ausstehende_speichern()
            if not e.control.selected:
                einmal_loeschen()
            else:
                einmal(e.control.selected[0] == "ja")

        return [
            ft.SegmentedButton(
                selected=[] if gesetzt is None else ["ja" if gesetzt else "nein"],
                allow_empty_selection=True,
                show_selected_icon=True,
                segments=[
                    ft.Segment(value="ja", label=ft.Text("Ja")),
                    ft.Segment(value="nein", label=ft.Text("Nein")),
                ],
                on_change=gewechselt,
            ),
            notiz_feld(alt),
        ]

    def text_teile() -> list[ft.Control]:
        if feld.mehrmals:

            def los(_e: object = None) -> None:
                text = (neuer_text.value or "").strip()
                if not text:
                    melden("Erst etwas schreiben.")
                    return
                neuer_text.value = ""
                eintragen(None, note=text)

            return [
                neuer_text,
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        uhrzeit,
                        ft.FilledButton("Eintragen", icon=ft.Icons.ADD, on_click=los, expand=True),
                    ],
                ),
            ]
        alt = ziel()
        anfang = alt.note if alt else ""
        eingabe = ft.TextField(
            value=anfang,
            hint_text="Tippen oder diktieren (Mikrofon der Tastatur)",
            multiline=True,
            min_lines=5,
            max_lines=14,
        )

        def sichern() -> None:
            neu = (eingabe.value or "").strip()
            if neu == anfang.strip():
                return
            jetzt_ziel = ziel()
            if not neu and jetzt_ziel is not None:
                state.tageswerte.loeschen(jetzt_ziel.id)
            elif jetzt_ziel is not None:
                state.tageswerte.korrigieren(jetzt_ziel.id, note=neu)
            elif neu:
                state.tageswerte.hinzufuegen(
                    feld, tag, neue_zeit(state, feld, tag), variante=variante(), note=neu
                )
            merken()

        ausstehend[f"text:{variante()}"] = sichern
        return [eingabe, ft.Text("Schließen speichert.", size=12, opacity=0.7)]

    def eintrag_zeile(w: tf.Tageswert) -> ft.Control:
        uhr = f"{w.zeit.astimezone():%H:%M}"
        # „400“, „400 × 2“, „250 ml“, „Knie 3“ — wie in der Zeitleiste, ohne den Feldnamen
        oben = tf.eintrag_text("", w).strip() or feld.name
        unter = [ft.Text(w.note, size=12, opacity=0.75)] if w.note and art != tf.TEXT else []
        if art == tf.TEXT:
            oben = w.note or "–"

        def loeschen(_e: object = None) -> None:
            state.tageswerte.loeschen(w.id)
            if offen["id"] == w.id:
                offen["id"] = None
            merken()
            zeichnen()

        def aufklappen(_e: object = None) -> None:
            ausstehende_speichern()
            offen["id"] = None if offen["id"] == w.id else w.id
            zeichnen()

        zeile = ft.Container(
            ink=True,
            on_click=aufklappen,
            border_radius=10,
            padding=ft.Padding.only(left=12, right=0, top=4, bottom=4),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(uhr, size=14, weight=ft.FontWeight.W_600, width=48),
                    ft.Column(
                        spacing=0,
                        tight=True,
                        expand=True,
                        controls=[ft.Text(oben, size=14), *unter],
                    ),
                    ft.IconButton(ft.Icons.CLOSE, tooltip="Eintrag löschen", on_click=loeschen),
                ],
            ),
        )
        if offen["id"] != w.id:
            return zeile
        return ft.Column(spacing=6, tight=True, controls=[zeile, bearbeiter(w)])

    def bearbeiter(w: tf.Tageswert) -> ft.Control:
        """Ein Eintrag aufgeklappt: Uhrzeit (die alte als Vorlage), Variante, Wert, Notiz."""
        zeit_feld = ft.TextField(
            label="Uhrzeit", value=f"{w.zeit.astimezone():%H:%M}", width=110, dense=True
        )
        f_alt = tf.wertfeld(w.spec)
        einheit = (
            f" in {f_alt.unit}" if f_alt is not None and f_alt.unit and art != tf.DAUER else ""
        )
        wert_feld = ft.TextField(
            label=("Dauer" if art == tf.DAUER else "Wert") + einheit,
            value=tf.eingabe_text(w.spec, w.wert),
            hint_text="Minuten oder 1:30" if art == tf.DAUER else None,
            expand=True,
            dense=True,
            visible=art in tf.SUMMIERT or art == tf.SKALA,
        )
        teil_felder: list[ft.TextField] = []
        if art == tf.MESSWERT:
            for i, f in enumerate(tf.teile_von(w.spec)):
                wert_i = w.werte[i] if i < len(w.werte) else None
                teil_felder.append(
                    ft.TextField(
                        label=f.label + (f" ({f.unit})" if f.unit else ""),
                        value="" if wert_i is None else tf.zahl(float(wert_i)),
                        width=max(96, 12 * len(f.label) + 40),
                        dense=True,
                    )
                )
        notiz = ft.TextField(
            label="Text" if art == tf.TEXT else "Notiz",
            value=w.note,
            multiline=True,
            min_lines=1,
            max_lines=6,
        )
        # Eine inzwischen entfernte Variante bleibt wählbar (Plan §5, Punkt 7)
        namen = list(feld.varianten)
        if w.variante and w.variante not in namen:
            namen.append(w.variante)
        wahl = (
            ft.Dropdown(
                label="Variante",
                value=w.variante or None,
                options=[
                    ft.DropdownOption(key=n, text=n if n in feld.varianten else f"{n} (entfernt)")
                    for n in namen
                ],
                dense=True,
            )
            if namen
            else None
        )

        def uebernehmen(_e: object = None) -> None:
            t = uhrzeit_lesen(zeit_feld.value or "")
            if t is None:
                melden("Uhrzeit wie 8:30 oder 1845.")
                return
            neue = tf.zeitpunkt(w.tag, t)
            if w.tag == heute and neue > jetzt():
                melden("Die Uhrzeit liegt in der Zukunft.")
                return
            wert: Any = w.wert
            if teil_felder:
                wert = tf.messwert_lesen(w.spec, [x.value or "" for x in teil_felder])
                if wert is None:
                    melden("Bitte alle Pflichtteile als Zahl.")
                    return
            elif wert_feld.visible:
                wert = tf.wert_lesen(w.spec, wert_feld.value or "")
                if wert is None:
                    melden("Diesen Wert verstehe ich nicht.")
                    return
            neue_variante = str(wahl.value or "") if wahl is not None else w.variante
            state.tageswerte.korrigieren(
                w.id,
                result=tf.ergebnis(wert, neue_variante),
                note=notiz.value or "",
                zeit=neue,
            )
            offen["id"] = None
            melden("")
            merken()
            zeichnen()

        zeile1: list[ft.Control] = [zeit_feld, *(teil_felder or [wert_feld])]
        if wahl is not None:
            zeile1.append(wahl)
        return ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=12,
            padding=10,
            content=ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    ft.Row(spacing=8, wrap=True, controls=zeile1),
                    notiz,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Abbrechen", on_click=aufklapper_zu),
                            ft.FilledButton(
                                "Übernehmen", icon=ft.Icons.CHECK, on_click=uebernehmen
                            ),
                        ],
                    ),
                ],
            ),
        )

    def aufklapper_zu(_e: object = None) -> None:
        offen["id"] = None
        zeichnen()

    def liste() -> list[ft.Control]:
        eintraege = sorted(werte(), key=lambda w: w.zeit, reverse=True)
        if not eintraege:
            return []
        return [
            ft.Text(
                f"{tag_text(tag, heute).upper()} EINGETRAGEN",
                size=11,
                weight=ft.FontWeight.BOLD,
                opacity=0.7,
            ),
            ft.Container(
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
                border_radius=12,
                content=ft.Column(spacing=0, controls=[eintrag_zeile(w) for w in eintraege]),
            ),
            ft.Text("Antippen ändert Uhrzeit, Variante, Wert oder Notiz.", size=12, opacity=0.7),
        ]

    def teile() -> list[ft.Control]:
        ausstehend.clear()
        mitte: list[ft.Control]
        if art == tf.SKALA:
            mitte = skala_teile()
        elif art == tf.MESSWERT:
            mitte = messwert_teile()
        elif art in tf.SUMMIERT:
            mitte = summen_teile()
        elif art == tf.JA_NEIN:
            mitte = ja_nein_teile()
        else:
            mitte = text_teile()
        wahl = varianten_wahl()
        unten: list[ft.Control] = []
        if bearbeiten is not None:
            unten.append(ft.TextButton("Feld bearbeiten", on_click=feld_oeffnen))
        unten.append(ft.Container(expand=True))
        unten.append(ft.FilledTonalButton("Fertig", on_click=fertig))
        return [
            kopf(),
            *([wahl] if wahl is not None else []),
            *mitte,
            fehler,
            *liste(),
            ft.Row(controls=unten),
        ]

    inhalt.controls = teile()
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        draggable=True,
        on_dismiss=geschlossen,
        # Viele Einträge am Tag: Der Inhalt scrollt, statt unter der Navigationsleiste zu
        # verschwinden (Ben, 22.10.2026, `components/blatt.py`)
        content=blatt_spalte(inhalt, rand=ft.Padding.only(left=16, right=16, bottom=20)),
    )
    return blatt


__all__ = [
    "gewaehlte_variante",
    "neue_zeit",
    "schnell_eintragen",
    "tag_text",
    "tagesfeld_blatt",
    "vorlage_zeit",
    "werte_des_felds",
]
