"""Die Übungsseite — eine Route auf dem Stapel (`/uebung/<id>`, unter einem Plan `…/info/<item>`).

Ben, 22.10.2026 (P79, `docs/plan_uebungen_einstellen.md`): Das i führt überall hierher — aus
dem Plan, von Heute, aus Verlauf, Tagebuch, Paket, Archiv und Papierkorb. Die Seite zeigt alles
und ändert nichts; geändert wird über den Stift („Übung bearbeiten“, gilt überall) oder, aus
einem Plan, über „Im Plan einstellen“ (Karte „In diesem Plan“ oben, Abschnitt „In Plänen“).

Aus welchem Paket die Übung kommt, steht unscheinbar in Klammern hinter der
Beschreibung (Ben, 14.10.2026) — „eigene Übung“, wenn sie hier angelegt oder
kopiert wurde. Weicht eine Paketübung von ihrem Paketstand ab, steht dort
„geändert“, und ganz unten führt „Auf Paketstand zurücksetzen“ zurück
(`PaketRepo.zuruecksetzen`). Die Erklärung der Varianten stand früher in jeder
Übung; sie steht jetzt allgemein in der Hilfe (`ui/components/hilfe.UEBUNGEN_MD`).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import varianten as var
from trainingsapp.core.models import (
    Exercise,
    Media,
    Plan,
    PlanItem,
    new_id,
)
from trainingsapp.core.result_spec import format_wert
from trainingsapp.core.standards import (
    abweichungen,
    aktive_felder,
    plan_spec,
    varianten_an,
    ziel_von,
)
from trainingsapp.core.uebung_timer import (
    TimerWahl,
    profile_der_uebung,
    timer_fuer,
    uhr_an,
    zaehlt_als,
)
from trainingsapp.ui.components.dialoge import Nachher, meldung, schliessen
from trainingsapp.ui.components.icons import symbol
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.links import oeffnen as link_oeffnen
from trainingsapp.ui.components.planstand import stand_zeile
from trainingsapp.ui.components.varianten import plakette
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.anhang_verlauf import aufnahmen_raster
from trainingsapp.ui.views.uebung_timer import uebung_timer_route


def _beschreibung(uebung: Exercise, herkunft: str) -> ft.Control:
    """Die Beschreibung, dahinter leise die Herkunft: „(Paket „Standard“)“."""
    return ft.Text(
        uebung.description or "—",
        spans=[
            ft.TextSpan(
                f"  ({herkunft})",
                style=ft.TextStyle(
                    size=12, color=ft.Colors.with_opacity(0.55, ft.Colors.ON_SURFACE)
                ),
            )
        ],
    )


def _abschnitt(titel: str, inhalt: ft.Control) -> ft.Control:
    return ft.Column(
        spacing=6,
        controls=[
            ft.Text(titel.upper(), size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            inhalt,
        ],
    )


def uhr_und_timer(uebung: Exercise, item: PlanItem | None = None) -> ft.Control:
    """Uhr und Timer der Übung — und was sie eintragen (Ben, 18.10.2026: „wenn eine Übung
    einen Timer hat, wird der in der Übungseinstellung gezeigt, aber nicht in der
    Informationsview. Dort sollte auch stehen …, wie sich Timer und Zeit auf die Zählung und
    das ‚Gemacht‘-Feld auswirken“). Mit ``item`` so, wie die Planübung es einstellt."""
    an = uhr_an(uebung, item)
    zeilen: list[ft.Control] = []
    if an:
        zeilen.append(_uhr_zeile(ft.Icons.AV_TIMER, "Stoppuhr", "zählt vorwärts, immer dabei"))
    for k, p in enumerate(profile_der_uebung(uebung)):
        name = p.name + (" · Vorgabe" if k == 0 and len(uebung.timer) > 1 else "")
        zeilen.append(_uhr_zeile(ft.Icons.TIMER_OUTLINED, name, p.kurztext()))
    if not an:
        zaehlt, erklaerung = "nichts (Uhr aus)", "Keine Uhr in der Übung — „Gemacht“ hakt nur ab."
    elif not uebung.zeit_zaehlt:
        zaehlt = "nichts — nur „gemacht“"
        erklaerung = "Timerzeit zählt nicht; beim Üben in der Leiste für jetzt umschaltbar."
    else:
        felder = (
            [f.key for f in aktive_felder(item, uebung)]
            if item is not None
            else [f.key for f in uebung.result_spec.fields]
        )
        wohin = zaehlt_als(felder, uebung)
        zaehlt = "Haltezeit je Satz" if wohin == "hold" else "Zeit"
        # Ein Lauf geht in den offenen Eintrag wie ein Tipp (P79 D1)
        erklaerung = (
            "„Fertig“ trägt in den offenen Eintrag ein: "
            + (
                "jeder Lauf der Stoppuhr und jeder zählende Abschnitt eines Timers ist ein Satz"
                if wohin == "hold"
                else "die gelaufene Zeit kommt dazu, auch ohne den Parameter Zeit"
            )
            + ". Pausen zählen nicht, unter 5 s fällt weg; „Abbrechen“ trägt nichts ein."
        )
    zeilen.append(
        ft.Container(
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            content=ft.Column(
                spacing=2,
                controls=[
                    ft.Text("Zählt als", size=12, opacity=0.7),
                    ft.Text(zaehlt, size=17, weight=ft.FontWeight.W_600),
                    ft.Text(erklaerung, size=12, opacity=0.75),
                ],
            ),
        )
    )
    wahl = TimerWahl.aus_dict(item.timer) if item is not None else TimerWahl()
    if item is not None and (wahl.uhr is not None or wahl.profil_id or wahl.eigen):
        zeilen.append(ft.Text("In diesem Plan eingestellt (Einstellen).", size=12, opacity=0.6))
    return ft.Column(spacing=8, controls=zeilen)


def _uhr_zeile(icon: ft.IconData, name: str, text: str) -> ft.Control:
    return ft.Row(
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.Icon(icon, size=20, opacity=0.85),
            ft.Column(
                spacing=0,
                expand=True,
                controls=[ft.Text(name, weight=ft.FontWeight.W_600), ft.Text(text, size=12)],
            ),
        ],
    )


def aufnahmen_liste(page: Any, state: AppState, uebung: Exercise) -> ft.Control:
    """HRV-Aufnahmen, in denen Einträge dieser Übung liegen (Skizze D3, Plan C) — nur die
    Liste; Kurven und Kennzahlen stehen in der Aufnahme. Ein Tipp öffnet sie, gezoomt auf
    die Einträge. Die HRV bleibt aus dem Verlauf der Übung (Katalog P39)."""
    if state.bezuege is None:
        return ft.Text("—", opacity=0.6)
    je_aufnahme = state.bezuege.zur_uebung(state.profil.id, uebung.id)
    if not je_aufnahme:
        return ft.Text(
            "Noch keine — läuft eine Aufnahme, bekommt jeder Satz dort eine Marke.",
            size=13,
            opacity=0.6,
        )
    heute = state.heute()
    zeilen: list[ft.Control] = []
    for aufnahme, bezuege in je_aufnahme[:12]:
        beginn = aufnahme.started_at.astimezone()
        wann = "Heute" if beginn.date() == heute else f"{beginn:%d.%m.}"
        dauer = f"{int(aufnahme.duration_s // 60)} min"
        werte = " · ".join(
            " ".join(t for t in (b.eintrag.shorthand(),) if t) or "abgehakt" for b in bezuege
        )
        zeitlich = all(b.zeitlich for b in bezuege)
        n = len(bezuege)
        unten = f"{n} Eintr{'ag' if n == 1 else 'äge'} · {werte}" + (
            " · zeitlich zugeordnet" if zeitlich else ""
        )

        def oeffner(a=aufnahme, bz=bezuege) -> Callable[[], object]:
            async def handler() -> None:
                von = min(b.fenster()[0] for b in bz)
                bis = max(b.fenster()[1] for b in bz)
                state.messung_zoom = (a.id, von, bis)
                await page.push_route(f"/messung/{a.id}")

            return handler

        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(
                    ft.Icons.FAVORITE_BORDER if zeitlich else ft.Icons.FAVORITE,
                    color=ft.Colors.OUTLINE if zeitlich else ft.Colors.ERROR,
                ),
                title=ft.Text(f"{wann}, {beginn:%H:%M} · {dauer} · {aufnahme.geraet or 'Gurt'}"),
                subtitle=ft.Text(unten, size=12),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                on_click=oeffner(),
                content_padding=ft.Padding.only(left=0, right=0),
            )
        )
    return ft.Column(spacing=0, controls=zeilen)


def _notation(uebung: Exercise) -> ft.Control:
    """Je Parameter ein eigener Block: Name und Einheit, darunter Chips und Beispiel.

    Früher stand alles in einer Zeile („Wiederholungen (Wdh.) · Chips 10, 15 ·
    z. B. 3x15") — bei mehreren Parametern war nicht zu erkennen, was wozu gehört.
    """
    spec = uebung.result_spec
    felder = [f for f in spec.fields if not var.ist_variante(f)]  # eigener Abschnitt
    if not felder:
        return ft.Text("Keine Felder — nur „gemacht“.")
    bloecke: list[ft.Control] = []
    for f in felder:
        beispiel = format_wert(f, f.default) if f.default is not None else ""
        unten: list[ft.Control] = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                border_radius=8,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                content=ft.Text(str(q), size=12),
            )
            for q in f.quick
        ]
        if beispiel:
            unten.append(ft.Text(f"z. B. {beispiel}", size=12, opacity=0.65))
        bloecke.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                border_radius=10,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                content=ft.Column(
                    spacing=6,
                    tight=True,
                    controls=[
                        ft.Row(
                            spacing=6,
                            controls=[
                                ft.Text(f.label, weight=ft.FontWeight.W_600),
                                ft.Text(f.unit or "", size=12, opacity=0.65),
                            ],
                        ),
                        ft.Row(wrap=True, spacing=6, run_spacing=6, controls=unten)
                        if unten
                        else ft.Container(),
                    ],
                ),
            )
        )
    return ft.Column(spacing=8, controls=bloecke)


def _varianten(liste: list[var.Variante]) -> ft.Control:
    """Je Variante Zeichen, Name und Beschreibung (Ben, 21.10.2026, Skizze D3) — gezählt wird
    jede für sich; angelegt und beschrieben unter „Bearbeiten“."""
    return ft.Column(
        spacing=8,
        controls=[
            ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    plakette(v),
                    ft.Column(
                        spacing=1,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(v.name, weight=ft.FontWeight.W_600),
                            *([ft.Text(v.text, size=12, opacity=0.75)] if v.text else []),
                        ],
                    ),
                ],
            )
            for v in liste
        ],
    )


def _plan_karte(
    uebung: Exercise, plan: Plan, item: PlanItem, einstellen: Callable[[], object] | None
) -> ft.Control:
    """Oben auf der Übungsseite, wenn man aus einem Plan kommt: was dort gilt (P79, Skizze A2).

    Grau „wie die Übung“, sonst „nur hier“; „Im Plan einstellen“ öffnet die Seite dafür.
    """
    unterschiede = abweichungen(item, uebung)
    parameter = [f for f in aktive_felder(item, uebung) if not var.ist_variante(f)]
    spec = plan_spec(item, uebung)
    ziel = ziel_von(item, uebung)
    ziel_text = spec.format_shorthand(ziel) if ziel else "kein Ziel"
    if "Ziel" in unterschiede and uebung.default_target:
        ziel_text += f"  (Übung {uebung.result_spec.format_shorthand(uebung.default_target)})"
    zeilen: list[ft.Control] = [
        stand_zeile(
            "Parameter",
            " · ".join(f.label for f in parameter) or "nur abhaken",
            "Parameter" in unterschiede or any(u.startswith("Chips") for u in unterschiede),
        ),
        stand_zeile("Ziel", ziel_text, "Ziel" in unterschiede),
    ]
    if var.varianten(uebung.result_spec):
        an = varianten_an(item)
        zeilen.append(stand_zeile("Varianten", "gezeigt" if an else "nicht gezeigt", not an))
    profil = timer_fuer(uebung, plan, item)
    uhr = uhr_an(uebung, item)
    zeilen.append(
        stand_zeile(
            "Uhr, Timer",
            ("an" + (f" · {profil.name}" if profil is not None else "")) if uhr else "aus",
            "Uhr" in unterschiede or "Timer" in unterschiede,
        )
    )
    return ft.Container(
        padding=ft.Padding.only(left=14, top=10, right=14, bottom=10),
        border_radius=16,
        border=ft.Border.all(2, ft.Colors.PRIMARY),
        content=ft.Column(
            spacing=8,
            controls=[
                ft.Row(
                    spacing=6,
                    controls=[
                        ft.Text("In diesem Plan", size=15, weight=ft.FontWeight.BOLD),
                        ft.Text(f"„{plan.name}“", size=13, opacity=0.75),
                    ],
                ),
                *zeilen,
                *(
                    [
                        ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.FilledTonalButton(
                                    "Im Plan einstellen", icon=ft.Icons.TUNE, on_click=einstellen
                                )
                            ],
                        )
                    ]
                    if einstellen is not None
                    else []
                ),
            ],
        ),
    )


def uebung_detail(
    page: ft.Page,
    state: AppState,
    uebung: Exercise,
    browser: ft.UrlLauncher,
    item: PlanItem | None = None,
    *,
    plan: Plan | None = None,
    route: str | None = None,
    einstellen: str | None = None,
) -> ft.View:
    """Die Übungsseite — überall dieselbe (Ben, 22.10.2026, P79: „ein Weg zur Info“).

    Sie zeigt alles und ändert nichts: geändert wird über den Stift („Übung bearbeiten“) oder,
    aus einem Plan, über „Im Plan einstellen“ (``einstellen``: dessen Route). ``route`` ist
    die eigene Route — unter einem Plan (`…/info/<item>`) führt Zurück wieder dorthin. Mit
    ``plan`` und ``item`` steht oben die Karte „In diesem Plan“, und „Uhr und Timer“ zeigt,
    was die Planübung einstellt. `browser` ist ein Flet-Dienst, den `main()` einmal an der
    Seite registriert.
    """
    geloescht = uebung.deleted_at is not None

    def oeffner(medium: Media) -> Callable[[], object]:
        async def handler() -> None:
            await link_oeffnen(page, browser, medium.uri)

        return handler

    def gehe_zu(ziel: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(ziel)

        return handler

    async def duplizieren() -> None:
        """Kopie — für „links/rechts“, 45° statt 90° und Ähnliches.

        Eine Kopie steht im Verlauf mit dem Original zusammen: Ihre Mengen addieren sich, die
        Kopie wird ausgewiesen. Im Editor lässt sie sich lösen („Im Verlauf zusammen mit“;
        Liegestütz einarmig ist eine eigene Liste wert). Sie ist eine eigene Übung — kein
        Paket-Update ändert sie. „Variante“ heißt seit 22.10.2026 nur noch das Etikett (P61).
        """
        kopie = replace(
            uebung,
            id=new_id(),
            name=f"{uebung.name} (Kopie)",
            is_builtin=False,
            package_id=None,
            media=[replace(m, id=new_id()) for m in uebung.media],
            typen=list(uebung.typen),
            regionen=list(uebung.regionen),
            archived=False,
            family_id=uebung.family_id or uebung.id,
        )
        state.uebungen.speichern(kopie)
        page.show_dialog(
            ft.SnackBar(
                ft.Text(
                    f"Kopie angelegt — im Verlauf zusammen mit „{uebung.name}“. Jetzt anpassen."
                )
            )
        )
        await page.push_route(f"/uebung/{kopie.id}/bearbeiten")

    def abbrechen() -> None:
        page.pop_dialog()

    entfernt = Nachher()  # Routenwechsel erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def archivieren() -> None:
        state.uebungen.archivieren(uebung.id)
        entfernt.danach(lambda: page.push_route("/"))
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(f"„{uebung.name}“ archiviert")))

    def loeschen() -> None:
        state.uebungen.in_papierkorb(uebung.id)
        entfernt.danach(lambda: page.push_route("/"))
        page.pop_dialog()
        page.show_dialog(meldung(f"„{uebung.name}“ liegt im Papierkorb", rueckgaengig))

    def rueckgaengig() -> None:
        state.uebungen.aus_papierkorb(uebung.id)
        state.neu_zeichnen()

    def entfernen_fragen() -> None:
        page.show_dialog(dialog)

    dialog = ft.AlertDialog(
        modal=True,
        on_dismiss=entfernt.bei_schliessen,
        title=ft.Text("Übung entfernen?"),
        content=ft.Text(
            "Archivieren: verschwindet aus dem Katalog, bleibt in Plänen — jederzeit zurück.\n\n"
            "Löschen: kommt in den Papierkorb und verschwindet auch aus den Plänen. "
            "Von dort lässt sie sich wiederherstellen; endgültig weg ist sie erst, "
            "wenn der Papierkorb geleert wird. Bereits Dokumentiertes bleibt im Verlauf."
        ),
        actions=[
            ft.TextButton("Abbrechen", on_click=abbrechen),
            ft.TextButton(
                "Löschen", style=ft.ButtonStyle(color=ft.Colors.ERROR), on_click=loeschen
            ),
            ft.FilledButton("Archivieren", on_click=archivieren),
        ],
    )

    def wiederherstellen() -> None:
        """Aus Archiv oder Papierkorb zurück in den Katalog (P79: Zeilen dort öffnen die Übung)."""
        if geloescht:
            state.uebungen.aus_papierkorb(uebung.id)
        else:
            state.uebungen.wiederherstellen(uebung.id)
        page.show_dialog(ft.SnackBar(ft.Text(f"„{uebung.name}“ ist wieder im Katalog")))
        state.neu_zeichnen()

    paket = state.pakete.laden(uebung.package_id) if uebung.package_id else None
    geaendert = state.pakete.abweichungen(uebung) if paket is not None else None
    herkunft = (
        f"Paket „{paket.name}“" + (", geändert" if geaendert else "")
        if paket is not None
        else "eigene Übung"
    )

    nachher = Nachher()  # neu zeichnen erst, wenn der Dialog zu ist (`components/dialoge.py`)

    def zuruecksetzen() -> None:
        try:
            state.pakete.zuruecksetzen([uebung.id])
        except sqlite3.Error as fehler:
            page.pop_dialog()
            page.show_dialog(ft.SnackBar(ft.Text(f"Nicht zurückgesetzt: {fehler}")))
            return
        nachher.danach(state.neu_zeichnen)
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text("Auf den Paketstand gesetzt")))

    def zuruecksetzen_fragen() -> None:
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                on_dismiss=nachher.bei_schliessen,
                title=ft.Text("Auf Paketstand zurücksetzen?"),
                content=ft.Text(
                    f"„{uebung.name}“ bekommt wieder den Stand aus dem Paket. Verloren geht "
                    f"deine Änderung an: {', '.join(geaendert or [])}. Einträge bleiben."
                ),
                actions=[
                    ft.TextButton("Abbrechen", on_click=lambda: page.pop_dialog()),
                    ft.FilledButton("Zurücksetzen", on_click=zuruecksetzen),
                ],
            )
        )

    # -- In Plänen (P79): jede Zeile öffnet „Im Plan einstellen“ dieses Plans --------------

    aufgenommen = Nachher()
    auswahl: ft.AlertDialog

    def aufnehmer(ziel: Plan) -> Callable[[], None]:
        def handler() -> None:
            state.plaene.uebung_hinzufuegen(ziel.id, uebung.id)
            aufgenommen.danach(
                lambda: page.show_dialog(
                    ft.SnackBar(ft.Text(f"„{uebung.name}“ steht jetzt in „{ziel.name}“"))
                )
            )
            aufgenommen.danach(state.neu_zeichnen)
            schliessen(auswahl)

        return handler

    auswahl = ft.AlertDialog(
        title=ft.Text("In einen Plan aufnehmen"),
        on_dismiss=aufgenommen.bei_schliessen,
        actions=[ft.TextButton("Abbrechen", on_click=lambda: schliessen(auswahl))],
    )

    def aufnehmen_fragen() -> None:
        plaene = sorted(state.plaene.alle(state.profil.id), key=lambda p: (not p.aktiv, p.name))
        auswahl.content = ft.Column(
            tight=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.LIST_ALT_OUTLINED),
                    title=ft.Text(p.name),
                    subtitle=None if p.aktiv else ft.Text("deaktiviert", size=12),
                    on_click=aufnehmer(p),
                )
                for p in plaene
            ]
            or [ft.Text("Noch kein Plan — unter Übungen → Pläne anlegen.")],
        )
        page.show_dialog(auswahl)

    verwendungen: list[ft.Control] = []
    for p, it in state.plaene.verwendungen(uebung.id, state.profil.id):
        unterschiede = abweichungen(it, uebung)
        verwendungen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.LIST_ALT_OUTLINED),
                title=ft.Text(p.name),
                subtitle=ft.Text(
                    "nur hier: " + ", ".join(unterschiede) if unterschiede else "wie die Übung",
                    size=12,
                    color=ft.Colors.TERTIARY if unterschiede else None,
                ),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                tooltip="Im Plan einstellen",
                on_click=gehe_zu(f"/plaene/{p.id}/ziel/{it.id}"),
                content_padding=ft.Padding.only(left=0, right=0),
            )
        )
    if uebung.default_target:
        vorgabe = uebung.result_spec.format_shorthand(uebung.default_target)
        verwendungen.append(ft.Text(f"Vorgabe für Pläne: Ziel {vorgabe}", size=12, opacity=0.7))
    if not geloescht:
        verwendungen.append(
            ft.TextButton("In einen Plan aufnehmen", icon=ft.Icons.ADD, on_click=aufnehmen_fragen)
        )

    videos: list[ft.Control] = [
        ft.ListTile(
            leading=ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE),
            title=ft.Text(m.title or m.uri),
            subtitle=ft.Text(m.uri, size=11, opacity=0.6) if m.title else None,
            trailing=ft.Icon(ft.Icons.OPEN_IN_NEW, size=18, opacity=0.6),
            on_click=oeffner(m),
        )
        for m in uebung.media
        if m.uri
    ]

    abschnitte: list[ft.Control] = []
    if geloescht or uebung.archived:
        abschnitte.append(
            ft.Container(
                padding=ft.Padding.only(left=14, top=6, right=6, bottom=6),
                border_radius=12,
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
                content=ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(
                            ft.Icons.DELETE_OUTLINE if geloescht else ft.Icons.ARCHIVE_OUTLINED,
                            size=20,
                        ),
                        ft.Text(
                            "Im Papierkorb" if geloescht else "Archiviert — nicht im Katalog",
                            expand=True,
                        ),
                        ft.TextButton("Wiederherstellen", on_click=wiederherstellen),
                    ],
                ),
            )
        )
    if plan is not None and item is not None:
        abschnitte.append(
            _plan_karte(uebung, plan, item, gehe_zu(einstellen) if einstellen else None)
        )
    abschnitte += [
        ft.Row(
            spacing=16,
            controls=[
                ft.Container(
                    width=64,
                    height=64,
                    border_radius=16,
                    bgcolor=ft.Colors.SECONDARY_CONTAINER,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(symbol(uebung.icon_key), size=36),
                ),
                ft.Column(
                    spacing=2,
                    expand=True,
                    controls=[
                        ft.Text(uebung.name, size=22, weight=ft.FontWeight.BOLD),
                        ft.Text(", ".join(uebung.typen) or "ohne Typ", opacity=0.7),
                    ],
                ),
            ],
        ),
        _abschnitt("Beschreibung", _beschreibung(uebung, herkunft)),
        _abschnitt(
            "Videos und Links",
            ft.Column(spacing=0, controls=videos)
            if videos
            else ft.Text("Noch keine Videos oder Links hinterlegt.", opacity=0.6),
        ),
        _abschnitt(
            "Regionen",
            ft.Row(
                wrap=True, spacing=6, controls=[ft.Chip(label=ft.Text(t)) for t in uebung.regionen]
            )
            if uebung.regionen
            else ft.Text("—"),
        ),
        _abschnitt("Parameter", _notation(uebung)),
        *(
            [_abschnitt("Varianten", _varianten(liste))]
            if (liste := var.varianten(uebung.result_spec))
            else []
        ),
        _abschnitt("Uhr und Timer", uhr_und_timer(uebung, item)),
        _abschnitt("In Plänen", ft.Column(spacing=0, controls=verwendungen)),
        _abschnitt("Aufnahmen mit dieser Übung", aufnahmen_liste(page, state, uebung)),
        # Eigene Fotos und Videos (Ben, 19.10.2026; `views/anhang_verlauf.py`) — nur mit Aufnahmen
        *(
            [_abschnitt("Fotos und Videos", raster)]
            if (raster := aufnahmen_raster(page, state, uebung)) is not None
            else []
        ),
    ]
    if paket is not None and geaendert:
        abschnitte.append(
            _abschnitt(
                "Paket",
                ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text(
                            f"Weicht vom Paket „{paket.name}“ ab: {', '.join(geaendert)}.",
                            size=13,
                        ),
                        ft.TextButton(
                            "Auf Paketstand zurücksetzen",
                            icon=ft.Icons.RESTORE,
                            on_click=zuruecksetzen_fragen,
                        ),
                    ],
                ),
            )
        )

    # Oben nur Timer, Stift und ⋮ (P79, Skizze C1) — im Papierkorb nichts davon
    aktionen: list[ft.Control] = (
        []
        if geloescht
        else [
            ft.IconButton(
                ft.Icons.TIMER if profile_der_uebung(uebung) else ft.Icons.TIMER_OUTLINED,
                tooltip="Timer dieser Übung",
                on_click=gehe_zu(uebung_timer_route(f"/uebung/{uebung.id}", uebung)),
            ),
            ft.IconButton(
                ft.Icons.EDIT_OUTLINED,
                tooltip="Übung bearbeiten",
                on_click=gehe_zu(f"/uebung/{uebung.id}/bearbeiten"),
            ),
            ft.PopupMenuButton(
                icon=ft.Icons.MORE_VERT,
                tooltip="Mehr",
                items=[
                    ft.PopupMenuItem(
                        content="Kopie anlegen", icon=ft.Icons.CONTENT_COPY, on_click=duplizieren
                    ),
                    ft.PopupMenuItem(
                        content="Archivieren oder löschen",
                        icon=ft.Icons.DELETE_OUTLINE,
                        on_click=entfernen_fragen,
                    ),
                ],
            ),
        ]
    )
    return ft.View(
        route=route or f"/uebung/{uebung.id}",
        appbar=ft.AppBar(title=ft.Text(uebung.name), actions=aktionen),
        scroll=ft.ScrollMode.AUTO,
        padding=20,
        controls=[sicher(ft.Column(spacing=22, controls=abschnitte), expand=False)],
    )


__all__ = ["uebung_detail"]
