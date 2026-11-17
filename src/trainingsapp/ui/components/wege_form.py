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
auf diesem Weg, die anderen sind zugeklappt; mit ``allein`` (der Griff eines Wegs im Bild
angetippt, Ben 10.11.2026) steht **nur** er da — „Alle Wege …“ holt den Rest.

Das Formular hält nichts selbst: ``lesen`` liefert den Ablauf, ``setzen`` nimmt den geänderten —
wann gespeichert wird, sagt der Ort (Speichern der Seite bzw. Schließen des Blatts).

**Die Leiste eines Wegs** (`weg_leiste`, Ben 16.11.2026: „möglichst ohne die Blätter schon viel
machen“): Ein Weg, im Bild an seinem Punkt angetippt, steht **unter dem Bild** — Marke und
„von → nach“, die Auslöser als Chips, die Zahl dazu mit − und +, „Pflicht“; „Mehr …“ führt ins
Blatt (Ziel, Beschriftung, anbieten oder von selbst, Inhalt). Welche Zahl nach einem Wechsel
des Auslösers gilt und wie weit − und + gehen, rechnet `core.ablauf` (`ausloeser_wechsel`,
`kante_schritt`) — für Blatt und Leiste dasselbe.
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
#: Die Auslöser in Kurzform — in der Leiste unter dem Bild stehen alle fünf in einer Zeile
AUSLOESER_KURZ: dict[str, str] = {
    ab.FREI: "frei",
    ab.ZEIT: "Zeit ab",
    ab.WDH: "Wdh.",
    ab.WDH_IN_ZEIT: "in Zeit",
    ab.SKALA: "Skala",
}
#: Die Wege **einer Frage** (Ben, 17.11.2026): Sie verzweigt nach der Antwort — Zeit und
#: Wiederholungen gibt es dort nicht. Ein Weg gilt für einen Bereich der Skala oder für jede
#: Antwort, die kein anderer Weg trifft.
ANTWORT_KURZ: dict[str, str] = {ab.SKALA: "Bereich", ab.FREI: "jede andere"}
ANTWORT_TEXT: dict[str, str] = {ab.SKALA: "Bereich der Skala", ab.FREI: "Jede andere Antwort"}
BEI_ANTWORT = "Bei welcher Antwort?"
#: Hinweis im Feld der Beschriftung eines Wegs aus einer Frage — der Satz, den der Plan sagt
ANTWORT_HINWEIS = "Für heute reicht es"
#: Je Weg einer Frage (Ben, 17.11.2026: „Frage soll beides können, von selbst weiter + Weg
#: vorschlagen“): Trifft die Antwort ihn, geht es von selbst weiter — oder er steht nur als
#: Vorschlag da, und die Person tippt (`Kante.vorschlagen`)
VORSCHLAGEN_TIPP = (
    "An: Trifft die Antwort diesen Weg, schlägt der Plan ihn nur vor — du tippst ihn oder einen "
    "anderen. Aus: Es geht von selbst weiter."
)


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
    allein: bool = False,
) -> ft.Control:
    """Herkunft und Wege von ``knoten``. ``namen``: jeder Knoten mit Nummer („3 · Planke“), in
    Planfolge, Fragen dahinter; ``ohne_timer``: die Übung hat keinen Timer (Hinweis zu „Zeit
    ab“); ``merken``: hält über das Neuzeichnen, welche Inhalte aufgeklappt sind.

    ``fokus``: das Ziel des angetippten Wegs (Ben, 9.11.2026: „Wenn es mehrere Wege von einer
    Übung aus gibt, soll das Blatt von unten einfach auf diesen ausgewählten Weg positioniert
    sein“) — er steht offen und hervorgehoben, die anderen zugeklappt als eine Zeile.
    ``allein``: nur dieser eine Weg, ohne Herkunft und ohne die anderen (Ben, 10.11.2026: „dann
    öffnet sich der entsprechende Eintrag der Übersicht halber alleine“), bis „Alle Wege …“."""
    a = lesen()
    offen: dict[str, Any] = merken if merken is not None else {}
    nur = (
        allein
        and fokus is not None
        and not offen.get("alle")
        and any(k.von == knoten and k.nach == fokus for k in a.kanten)
    )

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
            kanten = lesen().kanten
            skala = 0 <= i < len(kanten) and kanten[i].ausloeser == ab.SKALA
            if wert < 0 and (feld == "sekunden" or not skala):
                e.control.error = "ab 0"  # nur eine Skala kennt negative Werte (N72)
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
    teile: list[ft.Control] = [_abschnitt(ft.Icons.LOGIN, "KOMMT VON")]
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
                        ft.Icons.DELETE_OUTLINE,
                        icon_size=18,
                        icon_color=ft.Colors.ERROR,
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
    if nur:
        teile.clear()  # nur der eine Weg — die Herkunft steht bei „Alle Wege …“
    raus = [(i, k) for i, k in enumerate(a.kanten) if k.von == knoten]
    zahl_wege = "" if nur or len(raus) < 2 else f"{len(raus)} Wege"
    teile.append(_abschnitt(ft.Icons.ALT_ROUTE, "WEITER ZU", zahl_wege))
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

    def alle_zeigen(_e: Any = None) -> None:
        offen["alle"] = True
        neu_zeichnen()

    for n, (i, k) in enumerate(raus):
        if nur and k.nach != fokus:
            continue
        gewaehlt = fokus is not None and len(raus) > 1 and k.nach == fokus and not nur
        if (
            fokus is not None
            and not nur
            and not offen.get("alle")
            and len(raus) > 1
            and not gewaehlt
            and not offen.get(f"auf{i}")
        ):
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
        karte = _weg(
            i, k, n, ziele, aendern, weg_entfernen, zum_hauptweg, zahl, offen, ohne_timer, a
        )
        if gewaehlt and isinstance(karte, ft.Container):
            karte.border = ft.Border.all(2, ft.Colors.PRIMARY)
            karte.data = ("weg_gewaehlt", k.nach)
        teile.append(karte)
    if nur:
        andere = len(raus) - 1
        teile.append(
            ft.TextButton(
                f"Alle Wege dieser Übung ({andere} weitere)"
                if andere
                else "Herkunft und neue Wege",
                icon=ft.Icons.UNFOLD_MORE,
                on_click=alle_zeigen,
                data="alle_wege",
            )
        )
    else:
        teile.append(ft.TextButton("Weg", icon=ft.Icons.ADD, on_click=weg_dazu))
    return ft.Column(spacing=8, tight=True, controls=teile)


def _abschnitt(symbol: ft.IconData, text: str, zusatz: str = "") -> ft.Control:
    """Die Überschrift eines Abschnitts im Wege-Formular — deutlich statt klein und grau (Ben,
    16.11.2026: „die Überschriften fallen in den Hintergrund“): Symbol und kräftige Schrift in
    der Hauptfarbe, darunter eine Linie. ``zusatz``: rechts daneben, z. B. „2 Wege“."""
    return ft.Container(
        padding=ft.Padding.only(top=6, bottom=4),
        border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        data=("abschnitt", text),
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(symbol, size=18, color=ft.Colors.PRIMARY),
                ft.Text(
                    text,
                    size=13,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.PRIMARY,
                    expand=True,
                ),
                *([ft.Text(zusatz, size=12, opacity=0.7)] if zusatz else []),
            ],
        ),
    )


def _zeilentitel(text: str) -> ft.Control:
    """Der kleine Titel über einer Gruppe in der Weg-Karte („Wann geht es weiter?“)."""
    return ft.Text(text, size=12, weight=ft.FontWeight.W_600, opacity=0.8)


def _marke(n: int) -> ft.Control:
    """Die Marke eines Wegs: der Hauptweg (``n`` = 0) gefüllt, „Weg 2“, „Weg 3“ umrandet."""
    haupt = n == 0
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
        border_radius=10,
        bgcolor=ft.Colors.PRIMARY if haupt else None,
        border=None if haupt else ft.Border.all(1, ft.Colors.OUTLINE),
        data="weg_marke",
        content=ft.Text(
            "Hauptweg" if haupt else f"Weg {n + 1}",
            size=11,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.ON_PRIMARY if haupt else None,
        ),
    )


def _wechseln(
    aendern: Callable[..., None], i: int, k: Kante, art: str, ablauf: Ablauf | None = None
) -> None:
    """Der Weg ``i`` bekommt den Auslöser ``art`` — mit der Zahl, die dann gilt. Ein Weg aus
    einer Frage bekommt bei „Bereich“ das Stück der Skala, das noch frei ist
    (`core.ablauf.antwort_bereich`)."""
    neu = _gewechselt(k, art, ablauf)
    aendern(i, zeichnen=True, ausloeser=neu.ausloeser, n=neu.n, bis=neu.bis, sekunden=neu.sekunden)


def _gewechselt(k: Kante, art: str, ablauf: Ablauf | None) -> Kante:
    if ablauf is not None and art == ab.SKALA and ablauf.frage(k.von) is not None:
        return ab.antwort_bereich(ablauf, k)
    return ab.ausloeser_wechsel(k, art)


def ziel_name(k: Kante, namen: Mapping[str, str]) -> str:
    """Wohin ein Weg führt, in Worten: der Knoten mit Nummer, „Ende“, „◀ zurück“ oder — bei
    einer Schleife — „noch einmal“."""
    if k.zum_ende:
        return "Ende"
    if k.zurueck:
        return "◀ zurück"
    if k.schleife:
        return "noch einmal"
    return namen.get(k.nach, "?")


def weg_leiste(
    k: Kante,
    nummer: int,
    *,
    namen: Mapping[str, str],
    aendern: Callable[[Kante], Any],
    entfernen: Callable[[], Any],
    mehr: Callable[[], Any],
    ohne_timer: bool = False,
    ablauf: Ablauf | None = None,
) -> ft.Control:
    """Ein Weg als **Leiste unter dem Bild** (Reiter „Ablauf“, Ben 16.11.2026): das Wichtigste
    ohne Blatt. ``nummer``: seine Stelle unter den Wegen seiner Übung (0 = Hauptweg);
    ``aendern(kante)`` nimmt den geänderten Weg — der Ort speichert sofort und zeichnet neu;
    ``entfernen()`` nimmt ihn heraus, ``mehr()`` öffnet das Blatt mit nur diesem Weg.
    ``ohne_timer``: die Übung hat keinen Timer (Hinweis zu „Zeit ab“).

    ``ablauf``: Kommt der Weg **aus einer Frage**, fragt die Leiste „Bei welcher Antwort?“ —
    ein Bereich der Skala oder jede andere —, hat an der Stelle von „Pflicht“ den Schalter
    **„nur vorschlagen“** (`Kante.vorschlagen`: aus = die Antwort geht den Weg von selbst) und
    zeigt die Beschriftung (was der Plan bei dieser Antwort sagt; Tipp = Blatt). Zeit und
    Wiederholungen gibt es dort nicht (Ben, 17.11.2026)."""
    frage = ablauf.frage(k.von) if ablauf is not None else None

    def stufe(feld: str, text: str, vor: str = "") -> ft.Control:
        """Eine Zahl mit − und + — wie weit es geht, sagt `core.ablauf.kante_schritt`."""

        def knopf(schritt: int) -> ft.Control:
            return ft.IconButton(
                ft.Icons.REMOVE if schritt < 0 else ft.Icons.ADD,
                icon_size=18,
                width=36,
                height=36,
                padding=0,
                style=ft.ButtonStyle(bgcolor=ft.Colors.SURFACE),
                tooltip="weniger" if schritt < 0 else "mehr",
                on_click=lambda _e: aendern(ab.kante_schritt(k, feld, schritt)),
                data=("schritt", feld, schritt),
            )

        return ft.Row(
            tight=True,
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                *([ft.Text(vor, size=12, opacity=0.75)] if vor else []),
                knopf(-1),
                ft.Text(
                    text,
                    size=14,
                    weight=ft.FontWeight.W_600,
                    text_align=ft.TextAlign.CENTER,
                    data=("zahl", feld),
                ),
                knopf(1),
            ],
        )

    zahlen: list[ft.Control] = []
    if k.ausloeser in (ab.WDH, ab.WDH_IN_ZEIT):
        zahlen.append(stufe("n", f"{k.n} Wdh."))
    if k.ausloeser == ab.WDH_IN_ZEIT:
        zahlen.append(stufe("sekunden", ab.sekunden_text(k.sekunden), "in"))
    if k.ausloeser == ab.SKALA:
        zahlen.append(stufe("n", str(k.n), "ab"))
        offen_bis = "offen" if frage is None else str(frage.max)
        zahlen.append(stufe("bis", offen_bis if k.bis is None else str(k.bis), "bis"))
    pflicht = ft.Row(
        tight=True,
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text("Pflicht", size=13),
            ft.Switch(
                value=k.pflicht,
                tooltip="Andere Wege erst, wenn dieser erfüllt ist",
                on_change=lambda e: aendern(replace(k, pflicht=bool(e.control.value))),
                data="pflicht",
            ),
        ],
    )
    vorschlagen = ft.Row(
        tight=True,
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text("nur vorschlagen", size=13),
            ft.Switch(
                value=k.vorschlagen,
                tooltip=VORSCHLAGEN_TIPP,
                on_change=lambda e: aendern(replace(k, vorschlagen=bool(e.control.value))),
                data="vorschlagen",
            ),
        ],
    )
    zeilen: list[ft.Control] = [
        ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                _marke(nummer),
                # von → nach: der Pfeil als Symbol (das Zeichen „→“ fehlt der fetten Schrift)
                ft.Text(
                    namen.get(k.von, "?"),
                    size=14,
                    weight=ft.FontWeight.W_600,
                    expand_loose=True,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    data="weg_von",
                ),
                ft.Icon(ft.Icons.ARROW_FORWARD, size=16),
                ft.Text(
                    ziel_name(k, namen),
                    size=14,
                    weight=ft.FontWeight.W_600,
                    expand=True,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    data="weg_nach",
                ),
            ],
        ),
        # „Pflicht“ steht neben dem Titel — so kostet der Schalter keine eigene Zeile, und das
        # Bild darüber bleibt hoch genug (412 px breit, Web-Foto 16.11.2026)
        ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    content=_zeilentitel(
                        BEI_ANTWORT if frage is not None else "Wann geht es weiter?"
                    ),
                    expand=True,
                ),
                vorschlagen if frage is not None else pflicht,
            ],
        ),
        # alle in einer Zeile; reicht die Breite nicht, lässt sie sich schieben
        ft.Row(
            spacing=6,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Chip(
                    label=ft.Text(text, size=12),
                    selected=k.ausloeser == art,
                    show_checkmark=True,
                    selected_color=ft.Colors.PRIMARY_CONTAINER,
                    visual_density=ft.VisualDensity.COMPACT,
                    label_padding=ft.Padding.symmetric(horizontal=2),
                    tooltip=(ANTWORT_TEXT if frage is not None else ab.AUSLOESER_TEXT)[art],
                    on_select=lambda _e, art=art: aendern(_gewechselt(k, art, ablauf)),
                    data=("ausloeser", art),
                )
                for art, text in (ANTWORT_KURZ if frage is not None else AUSLOESER_KURZ).items()
            ],
        ),
    ]
    if zahlen:
        zeilen.append(
            ft.Row(
                wrap=True,
                spacing=14,
                run_spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=zahlen,
            )
        )
    if k.ausloeser == ab.ZEIT and ohne_timer:
        zeilen.append(
            ft.Text(
                "Die Übung hat keinen Timer — „Zeit ab“ gilt, sobald „Fertig“ getippt ist.",
                size=12,
                color=ft.Colors.TERTIARY,
            )
        )
    if frage is not None:
        # Was der Plan bei dieser Antwort sagt — die Beschriftung des Wegs, hier zu sehen und
        # mit einem Tipp im Blatt zu ändern (ein Textfeld unter dem Bild verschwände hinter
        # der Tastatur)
        zeilen.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=4, vertical=4),
                border_radius=8,
                ink=True,
                on_click=lambda _e: mehr(),
                tooltip="Beschriftung im Blatt ändern",
                data="weg_text",
                content=ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE, size=16, opacity=0.75),
                        ft.Text(
                            f"„{k.text}“" if k.text else "Was sagt der Plan bei dieser Antwort? …",
                            size=13,
                            opacity=1.0 if k.text else 0.7,
                            italic=not k.text,
                            expand=True,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Icon(ft.Icons.EDIT_OUTLINED, size=16, opacity=0.6),
                    ],
                ),
            )
        )
    zeilen.append(
        ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER_LEFT,
                    content=ft.TextButton(
                        "Mehr … (Ziel, Beschriftung, Inhalt)",
                        tooltip="Ziel, Beschriftung, anbieten oder von selbst, Inhalt",
                        style=ft.ButtonStyle(
                            padding=ft.Padding.symmetric(horizontal=4, vertical=0)
                        ),
                        on_click=lambda _e: mehr(),
                        data="weg_mehr",
                    ),
                ),
                # ausgeschrieben statt ✕ (Ben, 17.11.2026: „mach aus x --> entfernen“) — ein
                # ✕ liest sich wie „Leiste schließen“
                ft.TextButton(
                    "Entfernen",
                    icon=ft.Icons.DELETE_OUTLINE,
                    tooltip="Diesen Weg entfernen",
                    style=ft.ButtonStyle(
                        color=ft.Colors.ERROR,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=0),
                    ),
                    on_click=lambda _e: entfernen(),
                    data="weg_entfernen",
                ),
            ],
        )
    )
    return ft.Container(
        padding=ft.Padding.only(left=12, right=8, top=6, bottom=4),
        border_radius=14,
        bgcolor=KARTE,
        data="weg_leiste",
        content=ft.Column(spacing=4, tight=True, controls=zeilen),
    )


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
    ablauf: Ablauf | None = None,
) -> ft.Control:
    """Ein Weg als Karte — Ziel, wann, anbieten/ausführen, Pflicht, Danach, Beschriftung.
    Kommt er **aus einer Frage** (``ablauf`` kennt sie), fragt die Karte, bei welcher Antwort
    er gilt — ein Bereich der Skala oder jede andere — und was danach geschieht: von selbst
    weiter oder nur vorschlagen (`Kante.vorschlagen`). Zeit, Wiederholungen und „Pflicht“ gibt
    es dort nicht."""
    ziel = next((str(o.text) for o in ziele if o.key == k.nach), "?")
    frage = ablauf.frage(k.von) if ablauf is not None else None
    arten = ANTWORT_TEXT if frage is not None else ab.AUSLOESER_TEXT
    kopf = ft.Row(
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            # Die Marke sagt, welcher Weg es ist; daneben groß, wohin er führt (Ben,
            # 16.11.2026: „die Überschriften fallen in den Hintergrund“)
            _marke(n),
            ft.Icon(ft.Icons.ARROW_FORWARD, size=16),
            ft.Text(
                ziel,
                size=15,
                weight=ft.FontWeight.W_600,
                expand=True,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                data="weg_ziel",
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
            # der Papierkorb statt ✕ — ein ✕ liest sich wie „schließen“ (Ben, 17.11.2026)
            ft.IconButton(
                ft.Icons.DELETE_OUTLINE,
                icon_size=18,
                icon_color=ft.Colors.ERROR,
                tooltip="Weg entfernen",
                on_click=weg_entfernen(i),
                data="weg_entfernen",
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
        _zeilentitel(BEI_ANTWORT if frage is not None else "Wann geht es weiter?"),
        ft.Row(
            wrap=True,
            spacing=6,
            run_spacing=6,
            controls=[
                ft.Chip(
                    label=ft.Text(text),
                    selected=k.ausloeser == art,
                    # der gewählte Auslöser mit Haken und kräftiger Fläche — vorher hob er
                    # sich kaum ab
                    show_checkmark=True,
                    selected_color=ft.Colors.PRIMARY_CONTAINER,
                    # welche Zahl dann gilt, sagt `core.ablauf.ausloeser_wechsel` (N72)
                    on_select=lambda _e, art=art: _wechseln(aendern, i, k, art, ablauf),
                    data=("ausloeser", art),
                )
                for art, text in arten.items()
            ],
        ),
    ]
    if k.ausloeser in (ab.WDH, ab.WDH_IN_ZEIT, ab.SKALA):
        felder: list[ft.Control] = [
            ft.TextField(
                label=("Antwort ab" if frage is not None else "Skala ab")
                if k.ausloeser == ab.SKALA
                else "Wiederholungen",
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
    if k.ausloeser != ab.FREI and frage is None:
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
    if frage is None:
        zeilen.append(
            ft.Switch(
                label="Pflicht — andere Wege erst, wenn erfüllt",
                value=k.pflicht,
                on_change=lambda e: aendern(i, zeichnen=True, pflicht=bool(e.control.value)),
            )
        )
    else:
        zeilen += [
            _zeilentitel("Nach dieser Antwort"),
            ft.SegmentedButton(
                selected=["vorschlagen" if k.vorschlagen else "selbst"],
                show_selected_icon=False,
                segments=[
                    ft.Segment(value="selbst", label=ft.Text("Von selbst weiter")),
                    ft.Segment(value="vorschlagen", label=ft.Text("Nur vorschlagen")),
                ],
                on_change=lambda e: aendern(
                    i,
                    zeichnen=True,
                    vorschlagen=bool(e.control.selected) and e.control.selected[0] == "vorschlagen",
                ),
                data="weg_vorschlagen",
            ),
        ]
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
            label="Beschriftung — was sagt der Plan bei dieser Antwort?"
            if frage is not None
            else "Beschriftung — wann ist dieser Weg gemeint?",
            value=k.text,
            hint_text=ANTWORT_HINWEIS if frage is not None else "Rücken tut weh",
            dense=True,
            data="weg_text",
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


__all__ = ["ANTWORT_KURZ", "AUSLOESER_KURZ", "weg_leiste", "wege_karte", "ziel_name"]
