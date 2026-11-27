"""Rolle eines Stücks Material in den Editoren (Ben, 12.11.2026, P200).

Unter jedem Link und jeder Datei in „Übung bearbeiten“ und „Im Plan einstellen“:

- **Erklärung | Begleitung | Bewegung** — eine Erklärung sieht man an und hakt sie ab, eine
  Begleitung läuft beim Üben mit (`core.material`), eine Bewegung zeigt der Fokus als Animation
  (nur bei einer Bilddatei aus dem Paket, M2, 18.11.2026); ein **Symbol** aus dem Paket wird nur
  genannt, nicht gewählt;
- **Beim ersten Mal von selbst zeigen** — nur bei einer Erklärung;
- **Ersetzt** — ein anderes Stück, das hier nicht mehr angeboten wird: an der Planübung eines
  der Übung, an der Übung ein anderes der Übung (die Erweiterung ersetzt das Standard-Video).

Seit 19.11.2026 (Ben, 18.11.: „Die Medien müssen auf beliebige Punkte gesetzt werden können …
zugewiesen werden können und danach geordnet“, `docs/plan_medien_zeitpunkte.md` §2/§3) für eine
Erklärung dazu:

- **Wann: Vorher | Nachher | Bei …** — vor dem ▶, nach „Fertig“ oder zu einem Ereignis (ein
  Timer-Abschnitt beginnt, Satz n, nach einer Zeit, ab n Wiederholungen; am Plan: eine Antwort);
- **Von selbst zeigen: nein | beim ersten Mal | jedes Mal** (statt des Schalters);
- **Zu Abschnitt …** — die Abschnitte der Beschreibung, zu denen das Stück gehört (mehrere);
  die Namen liest das Blatt beim Öffnen frisch (``abschnitte`` ist eine Funktion — die
  Beschreibung steht im selben Formular und ändert sich).

Die Zeile hält keine eigenen Werte: Sie schreibt in das Wörterbuch des Aufrufers (``rolle``,
``zeigen``, ``ersetzt``, ``wann``, ``oft``, ``bei``, ``abschnitte`` — über `gelesen` die
Argumente von `Media`), das Formular liest es beim Speichern.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

import flet as ft

from trainingsapp.core.models import (
    BEGLEITUNG,
    BEI,
    BEWEGUNG,
    E_ABSCHNITT,
    E_ANTWORT,
    E_SATZ,
    E_WDH,
    E_ZEIT,
    IMMER,
    NACHHER,
    ROLLEN,
    SYMBOL,
    ZEITPUNKTE,
    Ereignis,
    Media,
    titelbild_lage_lesen,
)

ERKLAERUNG = "erklaerung"
NICHTS = ""
VORHER = "vorher"
#: Die Ereignisse an Übung und Planübung bzw. am Plan — mit dem Wort der Auswahl und dem Hinweis
#: im Feld daneben
EREIGNISSE_UEBUNG = (E_ABSCHNITT, E_SATZ, E_ZEIT, E_WDH)
EREIGNISSE_PLAN = (E_ANTWORT,)
EREIGNIS_WORT = {
    E_ABSCHNITT: ("Timer-Abschnitt beginnt", "Name, z. B. Pause"),
    E_SATZ: ("Satz beginnt", "Nummer, z. B. 2"),
    E_ZEIT: ("Zeit seit dem Start", "z. B. 1:30 oder 90"),
    E_WDH: ("Wiederholungen", "Anzahl, z. B. 10"),
    E_ANTWORT: ("Antwort einer Frage", "Antworten, mit Komma getrennt"),
}


def ereignis_aus(art: str, wert: str) -> Ereignis | None:
    """Das Ereignis aus der Auswahl und dem Text daneben — ``None``, wenn der Text nicht passt.

    >>> ereignis_aus("zeit", "1:30").sekunden, ereignis_aus("zeit", "90").sekunden
    (90.0, 90.0)
    >>> ereignis_aus("abschnitt", " Pause ").name, ereignis_aus("satz", "2").n
    ('Pause', 2)
    >>> ereignis_aus("antwort", "Knie zwickt, Rücken").antworten
    ('Knie zwickt', 'Rücken')
    >>> ereignis_aus("satz", "zwei") is None, ereignis_aus("zeit", "") is None
    (True, True)
    """
    wert = wert.strip()
    if art == E_ABSCHNITT:
        return Ereignis.aus({"art": art, "name": wert})
    if art in (E_SATZ, E_WDH):
        return Ereignis.aus({"art": art, "n": wert if wert.isdigit() else 0})
    if art == E_ZEIT:
        teile = wert.split(":")
        if not all(x.isdigit() for x in teile) or len(teile) > 2:
            return None
        sekunden = int(teile[0]) * 60 + int(teile[1]) if len(teile) == 2 else int(teile[0])
        return Ereignis.aus({"art": art, "sekunden": sekunden})
    if art == E_ANTWORT:
        return Ereignis.aus({"art": art, "antworten": wert.split(",")})
    return None


def ereignis_text(e: Ereignis | None) -> str:
    """Der Text im Feld neben der Auswahl.

    >>> ereignis_text(Ereignis("zeit", sekunden=90)), ereignis_text(Ereignis("satz", n=2))
    ('1:30', '2')
    >>> ereignis_text(Ereignis("antwort", antworten=("Ja", "Nein"))), ereignis_text(None)
    ('Ja, Nein', '')
    """
    if e is None:
        return ""
    if e.art == E_ABSCHNITT:
        return e.name
    if e.art in (E_SATZ, E_WDH):
        return str(e.n)
    if e.art == E_ZEIT:
        s = int(e.sekunden)
        return f"{s // 60}:{s % 60:02d}"
    return ", ".join(e.antworten)


def werte_von(medium: Media | None) -> dict[str, Any]:
    """Die Angaben eines Stücks als Wörterbuch für `rollen_zeile` — das Ereignis als Auswahl
    (``bei_art``) und Text (``bei_wert``), wie es im Formular steht.

    >>> w = werte_von(Media(uri="https://x/a", rolle="begleitung"))
    >>> w["rolle"], w["zeigen"], w["ersetzt"], w["wann"], w["abschnitte"]
    ('begleitung', False, '', '', ())
    >>> w = werte_von(Media(uri="https://x/a", wann="bei", bei=Ereignis("satz", n=2)))
    >>> w["wann"], w["bei_art"], w["bei_wert"]
    ('bei', 'satz', '2')
    >>> werte_von(None)["rolle"], werte_von(None)["oft"]
    ('', '')
    """
    if medium is None:
        medium = Media()
    return {
        "rolle": medium.rolle,
        "zeigen": medium.zeigen,
        "ersetzt": medium.ersetzt,
        "wann": medium.wann,
        "oft": medium.oft,
        "bei_art": medium.bei.art if medium.bei is not None else "",
        "bei_wert": ereignis_text(medium.bei),
        "abschnitte": tuple(medium.abschnitte),
        "text": medium.text,
        "titelbild": medium.titelbild,
        "titelbild_text": medium.titelbild_text,
        "titelbild_lage": medium.titelbild_lage,
    }


def gelesen(werte: dict[str, Any]) -> dict[str, Any]:
    """Was gespeichert wird — die Argumente von `Media`. „Von selbst zeigen“ und der Zeitpunkt
    gelten nur für eine Erklärung; ein „Bei …“ ohne lesbares Ereignis fällt auf „Vorher“ zurück
    (das Stück liegt dann still hinter „Medien“); ein „Bei …“ kommt immer von selbst.

    >>> g = gelesen({"rolle": "begleitung", "zeigen": True, "ersetzt": "", "wann": "nachher"})
    >>> g["rolle"], g["zeigen"], g["wann"]
    ('begleitung', False, '')
    >>> gelesen({"rolle": "symbol"})["rolle"], gelesen({"rolle": "tanz"})["rolle"]
    ('symbol', '')
    >>> g = gelesen({"wann": "bei", "bei_art": "abschnitt", "bei_wert": "Pause"})
    >>> g["wann"], g["bei"].name, g["zeigen"], g["oft"]
    ('bei', 'Pause', True, '')
    >>> g = gelesen({"wann": "bei", "bei_art": "satz", "bei_wert": "x", "oft": "immer"})
    >>> g["wann"], g["bei"], g["oft"], g["zeigen"]
    ('', None, 'immer', True)
    >>> gelesen({"abschnitte": ("Ausführung",)})["abschnitte"]
    ('Ausführung',)
    >>> gelesen({"text": " Knie über dem Fuß "})["text"]
    'Knie über dem Fuß'
    """
    rolle = str(werte.get("rolle") or "")
    rolle = rolle if rolle in ROLLEN else ""
    wann = str(werte.get("wann") or "")
    wann = wann if wann in ZEITPUNKTE and not rolle else ""
    ereignis = (
        ereignis_aus(str(werte.get("bei_art") or ""), str(werte.get("bei_wert") or ""))
        if wann == BEI
        else None
    )
    if wann == BEI and ereignis is None:
        wann = ""
    oft = IMMER if werte.get("oft") == IMMER and not rolle else ""
    return {
        "rolle": rolle,
        # „jedes Mal“ setzt auch `zeigen`: Eine ältere App zeigt es dann wenigstens beim ersten Mal
        "zeigen": (bool(werte.get("zeigen")) or bool(oft) or wann == BEI) and not rolle,
        "ersetzt": str(werte.get("ersetzt") or ""),
        "wann": wann,
        "oft": oft,
        "bei": ereignis,
        "abschnitte": tuple(werte.get("abschnitte") or ()) if rolle in ("", BEGLEITUNG) else (),
        # die Beschriftung (Ben, 19.11.2026) — an jedem Stück, gleich welcher Rolle
        "text": str(werte.get("text") or "").strip(),
        # das Titelbild (Ben, 27.11.2026) — an jedem Stück dasselbe Blatt
        "titelbild": str(werte.get("titelbild") or ""),
        "titelbild_text": str(werte.get("titelbild_text") or "").strip(),
        "titelbild_lage": titelbild_lage_lesen(werte.get("titelbild_lage")),
    }


def titelbild_stand_text(werte: dict[str, Any]) -> str:
    """„automatisch“, „gewähltes Bild“, „nur Text“ — was neben dem Knopf „Titelbild …“ steht.

    >>> titelbild_stand_text({}), titelbild_stand_text({"titelbild": "text"})
    ('automatisch', 'nur Text')
    """
    from trainingsapp.core import titelbild as tb

    bild = str(werte.get("titelbild") or "")
    art = tb.wahl(Media(uri="x", titelbild=bild)).art
    wort = {tb.AUTO: "automatisch", tb.BILD: "gewähltes Bild", tb.TEXT: "nur Text"}[art]
    mit_text = str(werte.get("titelbild_text") or "").strip() and art != tb.TEXT
    return wort + (", mit Text" if mit_text else "")


def rollen_zeile(
    werte: dict[str, Any],
    *,
    ersetzbar: Sequence[tuple[str, str]] = (),
    kennung: str = "",
    bewegung: bool = False,
    abschnitte: Callable[[], Sequence[str]] | None = None,
    plan: bool = False,
    titelbild: Callable[[str, str, tuple[float, float, float], Callable[..., None]], Any]
    | None = None,
) -> ft.Control:
    """Die Zeilen unter einem Stück. ``titelbild``: öffnet das Blatt „Titelbild“
    (`components/titelbild_blatt.py`) mit dem jetzigen Bild und Text und einem Setzer — ohne
    es gibt es den Knopf nicht. ``ersetzbar``: (Adresse, Titel) der Stücke, die dieses
    ersetzen kann — ohne sie gibt es die Auswahl nicht. ``kennung`` unterscheidet die Zeilen
    für Tests (``data``). ``bewegung``: „Bewegung“ zur Wahl (eine Bilddatei aus dem Paket).
    ``abschnitte``: liefert die Namen der Abschnitte der Beschreibung — ohne sie keine
    Zuordnung. ``plan``: ein Stück am Plan selbst — keine Rolle (es läuft keine Übung daneben),
    die Zeitpunkte heißen „Vor dem Start“ und „Am Ende“, das Ereignis ist eine Antwort."""
    if werte.get("rolle") == SYMBOL:
        return ft.Container(
            padding=ft.Padding.only(left=28, bottom=10),
            content=ft.Text("Symbol der Übung — kommt aus dem Paket", size=12, opacity=0.7),
        )
    bewegung = bewegung or werte.get("rolle") == BEWEGUNG
    ereignisse = EREIGNISSE_PLAN if plan else EREIGNISSE_UEBUNG
    if werte.get("bei_art") not in ereignisse:
        werte["bei_art"] = ereignisse[0]

    def erklaerung() -> bool:
        return not werte.get("rolle")

    def wann() -> str:
        w = str(werte.get("wann") or "")
        return w if w in ZEITPUNKTE and erklaerung() else ""

    # -- Wie oft ---------------------------------------------------------------------------

    def zeigen_umgestellt(e: ft.Event[ft.Switch]) -> None:
        werte["zeigen"] = bool(e.control.value)
        if not werte["zeigen"]:
            werte["oft"] = ""
        sichtbar_setzen()

    zeigen = ft.Switch(
        label="Beim ersten Mal von selbst zeigen",
        value=bool(werte.get("zeigen")),
        on_change=zeigen_umgestellt,
        data=("material_zeigen", kennung),
    )

    def immer_umgestellt(e: ft.Event[ft.Switch]) -> None:
        werte["oft"] = IMMER if e.control.value else ""

    immer = ft.Switch(
        label="Jedes Mal, nicht nur beim ersten",
        value=werte.get("oft") == IMMER,
        on_change=immer_umgestellt,
        data=("material_immer", kennung),
    )

    # -- Wann ------------------------------------------------------------------------------

    def wann_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        wahl = str(e.control.selected[0]) if e.control.selected else VORHER
        werte["wann"] = wahl if wahl in ZEITPUNKTE else ""
        sichtbar_setzen()

    wann_wahl = ft.SegmentedButton(
        selected=[wann() or VORHER],
        show_selected_icon=False,
        segments=[
            ft.Segment(value=VORHER, label=ft.Text("Vor dem Start" if plan else "Vorher")),
            ft.Segment(value=NACHHER, label=ft.Text("Am Ende" if plan else "Nachher")),
            ft.Segment(value=BEI, label=ft.Text("Bei …")),
        ],
        on_change=wann_gewaehlt,
        data=("material_wann", kennung),
    )

    def art_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
        werte["bei_art"] = str(e.control.value or ereignisse[0])
        wert_feld.hint_text = EREIGNIS_WORT[werte["bei_art"]][1]
        sichtbar_setzen()

    def wert_geaendert(e: ft.Event[ft.TextField]) -> None:
        werte["bei_wert"] = e.control.value or ""

    wert_feld = ft.TextField(
        value=str(werte.get("bei_wert") or ""),
        hint_text=EREIGNIS_WORT[werte["bei_art"]][1],
        dense=True,
        expand=True,
        on_change=wert_geaendert,
        data=("material_bei_wert", kennung),
    )
    # Auswahl und Feld untereinander: Nebeneinander schnitt die Handybreite beide ab (Web-Foto
    # 19.11.2026: „Timer-Abschnitt“, „Name, z. B. P…“)
    ereignis_zeile = ft.Column(
        spacing=6,
        tight=True,
        controls=[
            ft.Row(
                controls=[
                    ft.Dropdown(
                        value=werte["bei_art"],
                        options=[
                            ft.DropdownOption(key=a, text=EREIGNIS_WORT[a][0]) for a in ereignisse
                        ],
                        dense=True,
                        expand=True,
                        border=ft.OutlineInputBorder(border_radius=8),
                        on_select=art_gewaehlt,
                        disabled=len(ereignisse) == 1,
                        data=("material_bei_art", kennung),
                    )
                ]
            ),
            ft.Row(controls=[wert_feld]),
        ],
    )

    # -- Abschnitte ------------------------------------------------------------------------

    chips = ft.Row(wrap=True, spacing=6, run_spacing=0, visible=False)

    def abschnitt_text() -> str:
        gewaehlt = tuple(werte.get("abschnitte") or ())
        return "Zu Abschnitt: " + ", ".join(gewaehlt) if gewaehlt else "Zu Abschnitt …"

    def abschnitt_umgestellt(name: str) -> Callable[[Any], None]:
        def handler(e: Any) -> None:
            gewaehlt = [n for n in (werte.get("abschnitte") or ()) if n != name]
            if getattr(e.control, "selected", False):
                gewaehlt.append(name)
            werte["abschnitte"] = tuple(gewaehlt)
            abschnitt_knopf.content = abschnitt_text()
            sichtbar_setzen()

        return handler

    def abschnitte_zeigen(_e: Any = None) -> None:
        """Auf- und zuklappen — die Namen frisch aus der Beschreibung, wie sie jetzt dasteht."""
        if chips.visible:
            chips.visible = False
            sichtbar_setzen()
            return
        gewaehlt = tuple(werte.get("abschnitte") or ())
        namen = [n for n in (abschnitte() if abschnitte is not None else ()) if n]
        namen += [n for n in gewaehlt if n not in namen]
        chips.controls = [
            ft.Chip(
                label=ft.Text(n),
                selected=n in gewaehlt,
                on_select=abschnitt_umgestellt(n),
                data=("material_abschnitt", kennung, n),
            )
            for n in namen
        ] or [
            ft.Text(
                "Noch keine benannten Abschnitte — in der Beschreibung „Abschnitt hinzufügen“.",
                size=12,
                opacity=0.7,
            )
        ]
        chips.visible = True
        sichtbar_setzen()

    abschnitt_knopf = ft.TextButton(
        abschnitt_text(),
        icon=ft.Icons.LABEL_OUTLINE,
        on_click=abschnitte_zeigen,
        visible=abschnitte is not None,
        data=("material_abschnitte", kennung),
    )

    # -- Rolle -----------------------------------------------------------------------------

    hinweis = ft.Text(size=12, opacity=0.7)

    def hinweis_setzen() -> None:
        if werte.get("rolle") == BEGLEITUNG:
            hinweis.value = "Läuft beim Üben mit, die Uhr läuft weiter."
        elif werte.get("rolle") == BEWEGUNG:
            hinweis.value = "Im Fokus als Bewegung: eine Bildfolge im Takt, ein GIF als Schleife."
        elif wann() == NACHHER:
            hinweis.value = (
                "Am Ende des Plans — nach der letzten Übung."
                if plan
                else "Nach „Fertig“ der Übung."
            )
        elif wann() == BEI:
            hinweis.value = (
                "Geht nach dieser Antwort auf."
                if plan
                else "Zeigt sich beim Üben unter der Uhr, die Uhr läuft weiter."
            )
        else:
            hinweis.value = "Ansehen und abhaken — danach liegt es still hinter „Medien“."

    def sichtbar_setzen() -> None:
        wann_wahl.visible = erklaerung()
        ereignis_zeile.visible = wann() == BEI
        zeigen.visible = erklaerung() and wann() != BEI
        immer.visible = erklaerung() and (bool(werte.get("zeigen")) or wann() == BEI)
        abschnitt_knopf.visible = abschnitte is not None and werte.get("rolle") in ("", BEGLEITUNG)
        chips.visible = bool(chips.visible) and bool(abschnitt_knopf.visible)
        hinweis_setzen()
        with contextlib.suppress(Exception):
            spalte.update()

    def rolle_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        wahl = str(e.control.selected[0]) if e.control.selected else ERKLAERUNG
        werte["rolle"] = wahl if wahl in (BEGLEITUNG, BEWEGUNG) else ""
        sichtbar_setzen()

    def beschriftet(e: ft.Event[ft.TextField]) -> None:
        werte["text"] = (e.control.value or "").strip()

    # Die Beschriftung (Ben, 19.11.2026: „gleich benannt und beschriftet“) — steht beim Üben
    # unter dem Stück; `on_change`, damit auch Zurück-speichert den letzten Stand hat
    beschriftung = ft.TextField(
        label="Beschriftung (optional)",
        hint_text="Worauf achten? Was ist zu sehen?",
        value=str(werte.get("text") or ""),
        dense=True,
        multiline=True,
        min_lines=1,
        max_lines=3,
        on_change=beschriftet,
        data=("material_text", kennung),
    )
    titelbild_stand = ft.Text(
        titelbild_stand_text(werte),
        size=12,
        opacity=0.7,
        data=("material_titelbild_stand", kennung),
    )

    def titelbild_gesetzt(
        bild: str, text: str, lage: tuple[float, float, float] = (1.0, 0.0, 0.0)
    ) -> None:
        werte["titelbild"], werte["titelbild_text"], werte["titelbild_lage"] = bild, text, lage
        titelbild_stand.value = titelbild_stand_text(werte)
        with contextlib.suppress(Exception):
            titelbild_stand.update()

    def titelbild_tipp(_e: Any = None) -> Any:
        if titelbild is None:
            return None
        return titelbild(
            str(werte.get("titelbild") or ""),
            str(werte.get("titelbild_text") or ""),
            titelbild_lage_lesen(werte.get("titelbild_lage")),
            titelbild_gesetzt,
        )

    teile: list[ft.Control] = [
        beschriftung,
        *(
            [
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.TextButton(
                            "Titelbild …",
                            icon=ft.Icons.IMAGE_OUTLINED,
                            on_click=titelbild_tipp,
                            data=("material_titelbild", kennung),
                        ),
                        titelbild_stand,
                    ],
                )
            ]
            if titelbild is not None
            else []
        ),
        ft.SegmentedButton(
            selected=[str(werte.get("rolle") or "") or ERKLAERUNG],
            show_selected_icon=False,
            segments=[
                ft.Segment(value=ERKLAERUNG, label=ft.Text("Erklärung")),
                ft.Segment(value=BEGLEITUNG, label=ft.Text("Begleitung")),
                *([ft.Segment(value=BEWEGUNG, label=ft.Text("Bewegung"))] if bewegung else []),
            ],
            on_change=rolle_gewaehlt,
            visible=not plan,
            data=("material_rolle", kennung),
        ),
        wann_wahl,
        ereignis_zeile,
        zeigen,
        immer,
    ]
    andere = [(uri, titel) for uri, titel in ersetzbar if uri]
    if andere:
        bekannt = {uri for uri, _ in andere}
        wahl = werte.get("ersetzt") or NICHTS

        def ersetzt_gewaehlt(e: ft.Event[ft.Dropdown]) -> None:
            werte["ersetzt"] = str(e.control.value or "")

        teile.append(
            ft.Row(
                controls=[
                    ft.Dropdown(
                        label="Ersetzt",
                        value=wahl if wahl in bekannt else NICHTS,
                        options=[
                            ft.DropdownOption(key=NICHTS, text="nichts"),
                            *(
                                ft.DropdownOption(key=uri, text=titel or uri)
                                for uri, titel in andere
                            ),
                        ],
                        dense=True,
                        expand=True,
                        border=ft.OutlineInputBorder(border_radius=8),
                        on_select=ersetzt_gewaehlt,
                        data=("material_ersetzt", kennung),
                    )
                ]
            )
        )
    teile += [abschnitt_knopf, chips, hinweis]
    spalte = ft.Column(spacing=6, tight=True, controls=teile)
    sichtbar_setzen()
    return ft.Container(padding=ft.Padding.only(left=28, bottom=10), content=spalte)


__all__ = [
    "ERKLAERUNG",
    "VORHER",
    "ereignis_aus",
    "ereignis_text",
    "gelesen",
    "rollen_zeile",
    "werte_von",
]
