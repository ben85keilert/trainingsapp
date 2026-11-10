"""Der Timer-Editor als Baustein (Ben, 10.11.2026, `docs/plan_timer_zuordnen.md` §3, Skizze Z2):
derselbe Editor wie beim Haupttimer — Reiter **Zeiten · Klänge**, je Abschnitt eine Zeile,
Teile, Runden —, aber auch **im Fenster**: aufgeklappt in der Karte des Uhrenplans und in „Im
Plan einstellen“, damit der Überblick über die anderen Zeiten bleibt.

Aus `views/timer.timer_bearbeiten_view` gelöst (`docs/plan_timer_editor.md`, Skizzen G3–G5);
die Ansicht ist nur noch sein Rahmen (Titelleiste, Speichern, Löschen, Zurück speichert). Der
Baustein hält **Werte, keine Controls** (`_Zeile`, `_TeilFelder`): jeder Aufbau legt die Felder
neu an — ein umgehängtes Textfeld nähme sonst keine Eingaben mehr (Flet 1.0).

``geaendert``: eingebettet speichert der Ort nach jeder Änderung selbst (`bauen`); die Ansicht
speichert mit „Speichern“ bzw. Zurück (`stand`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

import flet as ft

from trainingsapp.core.result_spec import FieldType, ResultSpec
from trainingsapp.core.takt import Takt
from trainingsapp.core.timer import MAX_RUNDEN, Abschnitt, Teil, TimerProfil, dauer_text
from trainingsapp.core.uebung_timer import (
    ausfuehrung_text,
    ausfuehrungs_vorschau,
    ausfuehrungsfelder,
)
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.hilfe import TIMER_EDITOR_MD
from trainingsapp.ui.components.karte import info_knopf
from trainingsapp.ui.components.takt_blatt import takt_blatt, takt_zeile_text
from trainingsapp.ui.components.zeit_stellen import zeit_blatt


@dataclass
class _Zeile:
    """Ein Abschnitt im Editor — Werte, keine Controls: jeder Aufbau legt die Felder neu an
    (ein umgehängtes Textfeld nähme sonst keine Eingaben mehr, Flet 1.0)."""

    name: str
    #: die Dauer in Sekunden — gestellt über das Zeit-Blatt (Ben, 8.11.2026: kein Eingabefeld)
    dauer_s: int
    #: Klang zu Beginn — leer: der Standardklang der Signale
    klang: str = ""
    zaehlt: bool = True
    #: Der Takt dieses Abschnitts (`docs/plan_taktgeber.md`) — ``None``: wie die Übung
    takt: Takt | None = None
    #: Die Ausführung dieser Runde (Feld → Wert) — leer: wie im Block gewählt
    ausfuehrung: dict[str, Any] = field(default_factory=dict)

    def kopie(self) -> _Zeile:
        return replace(self, ausfuehrung=dict(self.ausfuehrung))


@dataclass
class _TeilFelder:
    """Ein Teil im Editor — sein Name, seine Abschnitte und Runden."""

    name: str
    zeilen: list[_Zeile] = field(default_factory=list)
    runden: int = 1

    def kopie(self) -> _TeilFelder:
        return _TeilFelder(self.name, [z.kopie() for z in self.zeilen], self.runden)

    def runde_s(self) -> int:
        return sum(z.dauer_s for z in self.zeilen)


#: Die Höhen der Zeilen — gleich in beiden Reitern, damit ein Abschnitt nach dem Wischen auf
#: derselben Höhe steht (Ben, 9.11.2026, `docs/plan_timer_editor.md` §2)
KOPF_H = 40
ZEILE_H = 48
ZUSATZ_H = 40
FUSS_H = 48
#: Die rechte Spalte jeder Zeile, die beim Wischen gleitet
RECHTS_B = 236
WISCH_MS = 220
#: Ab dieser Geschwindigkeit (px/s) zählt eine waagerechte Bewegung als Wischen
WISCH_V = 250
REITER_ZEITEN, REITER_KLAENGE = "zeiten", "klaenge"


@dataclass
class TimerEditor:
    """Der gebaute Editor: seine Teile zum Einsetzen und der Zugriff auf die Werte."""

    #: Das Namensfeld (unsichtbar bei ``ohne_name``)
    name: ft.TextField
    #: Fest oben in der Ansicht: Name, Gesamtzeit, Reiter und „i“
    kopf: ft.Control
    #: Nur die Reiter Zeiten · Klänge mit dem „i“ — für die Karte, die Name und Zeit selbst zeigt
    reiter: ft.Control
    #: Die Gesamtzeit des ganzen Timers
    gesamt: ft.Text
    #: Die Teile mit ihren Abschnitten
    teile: ft.Column
    #: Unter den Teilen: „Teil anhängen“, Vorschau (Zeiten) bzw. die Klänge des ganzen Timers
    zeiten_unten: ft.Column
    klaenge_unten: ft.Control
    #: Wischen: links zu den Klängen, rechts zurück (`on_horizontal_drag_end`)
    gewischt: Callable[[Any], None]
    #: Alles, was man ändern kann — für „Zurück speichert“
    stand: Callable[[], tuple[Any, ...]]
    #: Das Profil aus den Feldern (ID, Name) — oder der Grund, warum nicht
    bauen: Callable[[str, str], TimerProfil | str]

    def inhalt(self) -> ft.Control:
        """Teile und was darunter steht — eine Spalte, zum Einsetzen in Ansicht oder Karte."""
        return ft.Column(spacing=12, controls=[self.teile, self.zeiten_unten, self.klaenge_unten])


def timer_editor(
    page: Any,
    state: Any,
    profil: TimerProfil,
    *,
    spec: ResultSpec | None = None,
    ohne_name: bool = False,
    hinweis_text: str = "",
    geaendert: Callable[[], None] | None = None,
) -> TimerEditor:
    """Baut den Editor für ``profil`` (es selbst bleibt unberührt). ``spec``: die Felder der
    (Plan-)Übung — je Abschnitt lässt sich ihre Ausführung festlegen; ``ohne_name``: der
    Einmal-Timer, oben steht ``hinweis_text`` statt des Namens."""
    # Klänge, Vorspielen und die Signal-Karten liegen bei der Timer-Seite (sie importiert diesen
    # Baustein — darum erst hier)
    from trainingsapp.ui.views.timer import (
        _klang_feld,
        _klang_karte,
        _lautstaerke_karte,
        _signale_karte,
        _vorspielen,
    )

    name = ft.TextField(
        label="Name",
        value=profil.name,
        hint_text="z. B. Intervall, Planke",
        dense=True,
        expand=True,
        visible=not ohne_name,
    )
    teile_ed: list[_TeilFelder] = []
    teile_spalte = ft.Column(spacing=12)
    klang_ganz = {"runde": profil.runden_klang, "ende": profil.ende_klang}
    gesamt_text = ft.Text(
        size=22, weight=ft.FontWeight.W_700, color=ft.Colors.PRIMARY, data="gesamt"
    )
    reiter = {"modus": REITER_ZEITEN}
    #: je Zeile: die rechte Spalte gleiten lassen und Texte tauschen (Wischen, §2)
    umschalter: list[Callable[[bool], None]] = []
    #: Was eine Runde festlegen kann — nur am Timer einer Übung (§3)
    felder_aus = ausfuehrungsfelder(spec) if spec is not None else []
    vorschau = ft.Text(size=13, visible=False)

    def klaenge() -> bool:
        return reiter["modus"] == REITER_KLAENGE

    def gesamt() -> None:
        summe = sum(t.runde_s() * t.runden for t in teile_ed)
        gesamt_text.value = dauer_text(summe)
        # Je Ausführung ein Eintrag — was der Timer einträgt (`ausfuehrungs_vorschau`)
        teile = [
            Teil(
                [
                    Abschnitt("", z.dauer_s, zaehlt=z.zaehlt, ausfuehrung=dict(z.ausfuehrung))
                    for z in t.zeilen
                    if z.dauer_s
                ],
                t.runden,
            )
            for t in teile_ed
        ]
        je = (
            ausfuehrungs_vorschau(
                TimerProfil(abschnitte=teile[0].abschnitte, runden=teile[0].runden, teile=teile[1:])
            )
            if teile and teile[0].abschnitte
            else []
        )
        vorschau.visible = bool(je)
        vorschau.value = "Eingetragen wird je Ausführung ein Eintrag: " + " · ".join(
            f"{ausfuehrung_text(a, felder_aus) or 'wie gewählt'} {dauer_text(sek)}" for a, sek in je
        )

    def zeile(a: Abschnitt) -> _Zeile:
        return _Zeile(
            a.name,
            max(1, int(a.dauer_s)),
            a.klang,
            a.zaehlt,
            a.takt,
            {k: v for k, v in a.ausfuehrung.items() if any(f.key == k for f in felder_aus)},
        )

    def teil_felder(teil: Teil) -> _TeilFelder:
        return _TeilFelder(teil.name, [zeile(a) for a in teil.abschnitte], max(teil.runden, 1))

    def melden() -> None:
        """Etwas wurde geändert — eingebettet speichert der Ort sofort (``geaendert``)."""
        if geaendert is not None:
            geaendert()

    def neu_zeichnen() -> None:
        zeichnen()
        with contextlib.suppress(Exception):  # eingebettet vor dem ersten Anzeigen
            page.update()
        melden()

    def entferner(k: int, i: int) -> Callable[[], None]:
        def handler() -> None:
            if len(teile_ed[k].zeilen) > 1:
                del teile_ed[k].zeilen[i]
                neu_zeichnen()

        return handler

    def zaehlt_umschalter(k: int, i: int) -> Callable[[], None]:
        def handler() -> None:
            z = teile_ed[k].zeilen[i]
            z.zaehlt = not z.zaehlt
            neu_zeichnen()

        return handler

    def dauer_knopf(k: int, i: int) -> ft.Control:
        """Die Dauer als antippbares Etikett — ein Tipp öffnet das Zeit-Blatt (§4.6a)."""
        z = teile_ed[k].zeilen[i]

        def gestellt(sekunden: int) -> None:
            teile_ed[k].zeilen[i].dauer_s = sekunden
            neu_zeichnen()

        def stellen() -> None:
            page.show_dialog(
                zeit_blatt(
                    z.dauer_s,
                    starten=gestellt,
                    untertitel=z.name.strip() or f"Abschnitt {i + 1}",
                    start_text="Übernehmen",
                    schnell=state.schnellzeiten(),
                )
            )

        return ft.OutlinedButton(
            dauer_text(z.dauer_s),
            icon=ft.Icons.SCHEDULE,
            tooltip="Zeit stellen",
            on_click=stellen,
            style=ft.ButtonStyle(padding=ft.Padding.only(left=8, right=10)),
            data=("dauer", k, i),
        )

    def takt_setzer(k: int, i: int) -> Callable[[Takt | None], None]:
        def handler(takt: Takt | None) -> None:
            teile_ed[k].zeilen[i].takt = takt if takt is not None and not takt.leer else None
            neu_zeichnen()

        return handler

    def takt_entferner(k: int, i: int) -> Callable[[], None]:
        return lambda: takt_setzer(k, i)(None)

    def takt_bearbeiter(k: int, i: int) -> Callable[[], None]:
        def handler() -> None:
            z = teile_ed[k].zeilen[i]
            page.show_dialog(
                takt_blatt(
                    page,
                    state,
                    takt=z.takt,
                    titel=f"Takt: {z.name.strip() or 'Abschnitt'}",
                    in_den_abschnitt=takt_setzer(k, i),
                )
            )

        return handler

    def hinzufuegen(k: int) -> Callable[[], None]:
        def handler() -> None:
            teile_ed[k].zeilen.append(zeile(Abschnitt("", 60)))
            neu_zeichnen()

        return handler

    def abschnitt_menue(k: int, i: int) -> Callable[..., None]:
        """Langes Drücken auf eine Zeile (P151, Ben 9.11.2026: „alles so wie vorgeschlagen“):
        den Abschnitt kopieren (dahinter) oder entfernen."""

        def handler(_e: Any = None) -> None:
            z = teile_ed[k].zeilen[i]
            nachher = Nachher()
            dialog: ft.AlertDialog

            def kopieren(_e: Any = None) -> None:
                teile_ed[k].zeilen.insert(i + 1, z.kopie())
                nachher.danach(neu_zeichnen)
                schliessen(dialog)

            def entfernen(_e: Any = None) -> None:
                if len(teile_ed[k].zeilen) > 1:
                    del teile_ed[k].zeilen[i]
                nachher.danach(neu_zeichnen)
                schliessen(dialog)

            dialog = ft.AlertDialog(
                title=ft.Text(z.name.strip() or f"Abschnitt {i + 1}"),
                content=ft.Column(
                    tight=True,
                    spacing=0,
                    controls=[
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.CONTENT_COPY),
                            title=ft.Text("Kopieren"),
                            subtitle=ft.Text("dahinter einfügen", size=12),
                            on_click=kopieren,
                        ),
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.REMOVE_CIRCLE_OUTLINE),
                            title=ft.Text("Entfernen"),
                            disabled=len(teile_ed[k].zeilen) <= 1,
                            on_click=entfernen,
                        ),
                    ],
                ),
                actions=[ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog))],
                on_dismiss=nachher.bei_schliessen,
            )
            page.show_dialog(dialog)

        return handler

    def ausfuehrung_setzen(k: int, i: int, key: str, wert: Any) -> None:
        """Ein Wert der Ausführung — derselbe noch einmal oder ``None`` nimmt ihn heraus. Der
        Name folgt („Links“), solange er leer ist oder dem alten Vorschlag entspricht."""
        z = teile_ed[k].zeilen[i]
        alt = dict(z.ausfuehrung)
        if wert is None or alt.get(key) == wert:
            z.ausfuehrung.pop(key, None)
        else:
            z.ausfuehrung[key] = wert
        jetzt = z.name.strip()
        if not jetzt or jetzt == ausfuehrung_text(alt, felder_aus):
            z.name = ausfuehrung_text(z.ausfuehrung, felder_aus).capitalize()
        neu_zeichnen()

    def ausfuehrung_waehler(k: int, i: int, key: str, wert: Any) -> Callable[[], None]:
        return lambda: ausfuehrung_setzen(k, i, key, wert)

    def ausfuehrung_zahl(k: int, i: int, key: str) -> Callable[[Any], None]:
        """Gewicht oder Winkel getippt — leer heißt „wie gewählt“."""

        def handler(e: Any) -> None:
            text = str(getattr(e.control, "value", "") or "").strip().replace(",", ".")
            try:
                zahl = float(text) if text else None
            except ValueError:
                zahl = None
            z = teile_ed[k].zeilen[i]
            if zahl is None and key not in z.ausfuehrung:
                return
            wert = None if zahl is None else (int(zahl) if zahl.is_integer() else zahl)
            if z.ausfuehrung.get(key) != wert:
                z.ausfuehrung.pop(key, None)
                ausfuehrung_setzen(k, i, key, wert)

        return handler

    def ausfuehrung_zeile(k: int, i: int) -> ft.Control:
        """„Ausführung“ je Runde: die Chips der Variante bzw. Seite, Felder für Gewicht und
        Winkel — nichts gewählt heißt „wie gewählt“ (der Block)."""
        z = teile_ed[k].zeilen[i]
        teile: list[ft.Control] = [ft.Text("Ausführung", size=12, opacity=0.7)]
        for f in felder_aus:
            if f.type == FieldType.CHOICE:
                teile.extend(
                    ft.Chip(
                        label=ft.Text(str(o), size=12),
                        selected=z.ausfuehrung.get(f.key) == o,
                        show_checkmark=False,
                        tooltip=f"{f.label}: {o} — noch einmal tippen: wie gewählt",
                        on_select=ausfuehrung_waehler(k, i, f.key, o),
                    )
                    for o in f.quick
                )
            else:
                wert = z.ausfuehrung.get(f.key)
                teile.append(
                    ft.TextField(
                        label=f.label,
                        value="" if wert is None else str(wert).replace(".", ","),
                        hint_text="wie gewählt",
                        suffix=f.unit or None,
                        dense=True,
                        width=120,
                        keyboard_type=ft.KeyboardType.NUMBER,
                        on_blur=ausfuehrung_zahl(k, i, f.key),
                        on_submit=ausfuehrung_zahl(k, i, f.key),
                    )
                )
        if not z.ausfuehrung:
            teile.append(ft.Text("wie gewählt", size=12, italic=True, opacity=0.6))
        return ft.Row(
            wrap=True,
            spacing=6,
            run_spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=teile,
        )

    def runden_aendern(k: int, delta: int) -> Callable[[], None]:
        def handler() -> None:
            t = teile_ed[k]
            t.runden = min(max(t.runden + delta, 1), MAX_RUNDEN)
            neu_zeichnen()

        return handler

    def teil_hinzufuegen() -> None:
        teile_ed.append(_TeilFelder("Cooldown", [_Zeile("Cooldown", 60, zaehlt=False)], 1))
        neu_zeichnen()

    def teil_kopierer(k: int) -> Callable[[], None]:
        """⧉ neben dem Papierkorb (Ben, 9.11.2026): der Teil noch einmal, gleich dahinter."""

        def handler() -> None:
            teile_ed.insert(k + 1, teile_ed[k].kopie())
            neu_zeichnen()

        return handler

    def teil_entferner(k: int) -> Callable[[], None]:
        def handler() -> None:
            if len(teile_ed) > 1:
                del teile_ed[k]
                neu_zeichnen()

        return handler

    # -- Bausteine einer Karte ---------------------------------------------------------------

    def gleitend(zeiten: ft.Control, klaenge_teil: ft.Control, hoehe: int) -> ft.Control:
        """Die rechte Spalte: beide Teile übereinander, sichtbar nur einer — Wischen schiebt
        sie (`offset`, `animate_offset`; `AnimatedSwitcher` kann in Flet 1.0.3 nicht schieben).
        Was hinausgeschoben ist, fängt keine Tipps: der Stapel schneidet ab."""
        kl = klaenge()
        bewegung = ft.Animation(WISCH_MS, ft.AnimationCurve.EASE_OUT)
        a = ft.Container(
            left=0,
            top=0,
            width=RECHTS_B,
            height=hoehe,
            alignment=ft.Alignment.CENTER_RIGHT,
            offset=ft.Offset(-1 if kl else 0, 0),
            animate_offset=bewegung,
            content=zeiten,
        )
        b = ft.Container(
            left=0,
            top=0,
            width=RECHTS_B,
            height=hoehe,
            alignment=ft.Alignment.CENTER_RIGHT,
            offset=ft.Offset(0 if kl else 1, 0),
            animate_offset=bewegung,
            content=klaenge_teil,
        )

        def umschalten(nach_klaengen: bool) -> None:
            a.offset = ft.Offset(-1 if nach_klaengen else 0, 0)
            b.offset = ft.Offset(0 if nach_klaengen else 1, 0)

        umschalter.append(umschalten)
        return ft.Stack(
            controls=[a, b],
            width=RECHTS_B,
            height=hoehe,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    def name_links(
        wert: str,
        platzhalter: str,
        setzen: Callable[[str], None],
        *,
        groesse: int = 15,
        fett: bool = False,
        farbe: str | None = None,
        data: Any = None,
    ) -> ft.Control:
        """Links: unter „Zeiten“ ein Feld, unter „Klänge“ derselbe Name zum Lesen (P152) — an
        derselben Stelle."""
        kl = klaenge()

        def geaendert(e: Any) -> None:
            setzen(str(e.control.value or ""))
            lesen.value = str(e.control.value or "").strip() or platzhalter
            melden()

        feld = ft.TextField(
            value=wert,
            hint_text=platzhalter,
            dense=True,
            border=ft.UnderlineInputBorder(),
            content_padding=ft.Padding.only(left=2, right=2, top=6, bottom=6),
            expand=True,
            visible=not kl,
            on_change=geaendert,
            text_size=groesse,
            text_style=ft.TextStyle(weight=ft.FontWeight.W_700) if fett else None,
            color=farbe,
            data=data,
        )
        lesen = ft.Text(
            wert.strip() or platzhalter,
            expand=True,
            visible=kl,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            size=groesse,
            weight=ft.FontWeight.W_700 if fett else None,
            color=farbe,
        )

        def umschalten(nach_klaengen: bool) -> None:
            feld.visible = not nach_klaengen
            lesen.visible = nach_klaengen

        umschalter.append(umschalten)
        return ft.Row(expand=True, spacing=0, controls=[feld, lesen])

    def zaehlt_chip(k: int, i: int, z: _Zeile) -> ft.Control:
        """„zählt“ als Chip (P154) — durchgestrichen: zählt nicht als Übungszeit."""
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=9, vertical=5),
            border_radius=15,
            bgcolor=ft.Colors.PRIMARY_CONTAINER if z.zaehlt else None,
            border=None if z.zaehlt else ft.Border.all(1, ft.Colors.OUTLINE),
            tooltip="zählt als Übungszeit — tippen schaltet um"
            if z.zaehlt
            else "zählt nicht als Übungszeit — tippen schaltet um",
            on_click=lambda _e=None: zaehlt_umschalter(k, i)(),
            data=("zaehlt", k, i),
            content=ft.Text(
                "zählt",
                size=12,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_PRIMARY_CONTAINER if z.zaehlt else None,
                opacity=1.0 if z.zaehlt else 0.7,
                style=None if z.zaehlt else ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH),
            ),
        )

    def abschnitt(k: int, i: int, z: _Zeile, t: _TeilFelder) -> list[ft.Control]:
        """Eine Zeile je Abschnitt — Name · Takt · Zeit · zählt · ⊖ (Skizze G3); darunter,
        wenn es sie gibt, der Takt und die Ausführung."""

        def name_setzen(wert: str, z: _Zeile = z) -> None:
            z.name = wert

        zeiten_teil = ft.Row(
            spacing=2,
            alignment=ft.MainAxisAlignment.END,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(
                    ft.Icons.GRAPHIC_EQ,
                    icon_size=20,
                    tooltip=takt_zeile_text(z.takt),
                    style=ft.ButtonStyle(bgcolor=ft.Colors.SECONDARY_CONTAINER)
                    if z.takt is not None
                    else None,
                    icon_color=ft.Colors.ON_SECONDARY_CONTAINER if z.takt is not None else None,
                    on_click=takt_bearbeiter(k, i),
                    data=("takt", k, i),
                ),
                dauer_knopf(k, i),
                zaehlt_chip(k, i, z),
                ft.IconButton(
                    ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    icon_size=20,
                    tooltip="Abschnitt entfernen — lange drücken: kopieren",
                    on_click=entferner(k, i),
                    disabled=len(t.zeilen) <= 1,
                ),
            ],
        )

        def klang_setzen(wert: str, z: _Zeile = z) -> None:
            z.klang = wert
            melden()

        klaenge_teil = ft.Row(
            spacing=2,
            alignment=ft.MainAxisAlignment.END,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                _klang_feld(page, state, z.klang, "Standardklang", klang_setzen),
                ft.IconButton(
                    ft.Icons.PLAY_ARROW,
                    icon_size=22,
                    tooltip="Vorspielen",
                    on_click=lambda _e=None, z=z: _vorspielen(
                        page, state, z.klang or state.timer_signale().klang
                    ),
                ),
            ],
        )
        out: list[ft.Control] = [
            ft.Container(
                height=ZEILE_H,
                padding=ft.Padding.only(left=12, right=4),
                border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                on_long_press=abschnitt_menue(k, i),
                data=("abschnitt", k, i),
                content=ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        name_links(z.name, f"Abschnitt {i + 1}", name_setzen, data=("name", k, i)),
                        gleitend(zeiten_teil, klaenge_teil, ZEILE_H),
                    ],
                ),
            )
        ]
        if z.takt is not None:
            hinweis_zeit = "nur in diesem Abschnitt"
            hinweis_klang = "Klang je Phase — ✎"
            zusatz = ft.Text(
                hinweis_klang if klaenge() else hinweis_zeit,
                size=12,
                opacity=0.7,
                expand=True,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )

            def zusatz_tauschen(nach_klaengen: bool, zusatz: ft.Text = zusatz) -> None:
                zusatz.value = hinweis_klang if nach_klaengen else hinweis_zeit

            umschalter.append(zusatz_tauschen)
            out.append(
                ft.Container(
                    padding=ft.Padding.only(left=16, right=4),
                    content=ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.GRAPHIC_EQ, size=14, color=ft.Colors.PRIMARY),
                            ft.Text(
                                takt_zeile_text(z.takt).removeprefix("Takt: "),
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.PRIMARY,
                            ),
                            zusatz,
                            ft.IconButton(
                                ft.Icons.EDIT_OUTLINED,
                                icon_size=16,
                                tooltip="Takt einstellen: Phasen, Tempo, Klang",
                                on_click=takt_bearbeiter(k, i),
                            ),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                icon_size=16,
                                tooltip="Takt entfernen",
                                on_click=takt_entferner(k, i),
                            ),
                        ],
                    ),
                )
            )
        if felder_aus:
            out.append(
                ft.Container(
                    padding=ft.Padding.only(left=16, right=8, bottom=6),
                    content=ausfuehrung_zeile(k, i),
                )
            )
        return out

    def teil_karte(k: int, t: _TeilFelder) -> ft.Control:
        kl = klaenge()

        def name_setzen(wert: str, t: _TeilFelder = t) -> None:
            t.name = wert

        knoepfe = ft.Row(
            spacing=0,
            visible=not kl,
            controls=[
                ft.IconButton(
                    ft.Icons.CONTENT_COPY,
                    icon_size=18,
                    tooltip="Teil kopieren — dahinter",
                    on_click=teil_kopierer(k),
                    data=("teil_kopieren", k),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_size=18,
                    tooltip="Teil entfernen",
                    on_click=teil_entferner(k),
                    disabled=len(teile_ed) <= 1,
                ),
            ],
        )
        hinzu = ft.TextButton(
            "Abschnitt hinzufügen", icon=ft.Icons.ADD, on_click=hinzufuegen(k), visible=not kl
        )
        runden = ft.Row(
            spacing=0,
            visible=not kl,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("Runden", size=13, opacity=0.75),
                ft.IconButton(ft.Icons.REMOVE, on_click=runden_aendern(k, -1)),
                ft.Text(
                    str(t.runden),
                    size=16,
                    weight=ft.FontWeight.W_700,
                    width=28,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.IconButton(ft.Icons.ADD, on_click=runden_aendern(k, 1)),
            ],
        )
        runden_lesen = ft.Text(
            "1 Runde" if t.runden == 1 else f"{t.runden} Runden",
            size=13,
            opacity=0.75,
            visible=kl,
        )

        def umschalten(nach_klaengen: bool) -> None:
            knoepfe.visible = hinzu.visible = runden.visible = not nach_klaengen
            runden_lesen.visible = nach_klaengen

        umschalter.append(umschalten)
        zeilen: list[ft.Control] = []
        for i, z in enumerate(t.zeilen):
            zeilen.extend(abschnitt(k, i, z, t))
        return ft.Container(
            border_radius=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            data=("teil", k),
            content=ft.Column(
                spacing=0,
                controls=[
                    ft.Container(
                        height=KOPF_H,
                        padding=ft.Padding.only(left=12, right=4),
                        content=ft.Row(
                            spacing=2,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                name_links(
                                    t.name,
                                    "Abschnitte" if len(teile_ed) == 1 else f"Teil {k + 1}",
                                    name_setzen,
                                    groesse=13,
                                    fett=True,
                                    farbe=ft.Colors.PRIMARY,
                                    data=("teil_name", k),
                                ),
                                knoepfe,
                            ],
                        ),
                    ),
                    *zeilen,
                    ft.Container(
                        height=ZUSATZ_H,
                        padding=ft.Padding.only(left=4),
                        alignment=ft.Alignment.CENTER_LEFT,
                        content=hinzu,
                    ),
                    ft.Container(
                        height=FUSS_H,
                        padding=ft.Padding.only(left=14, right=6),
                        border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                        content=ft.Row(
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text(
                                    dauer_text(t.runde_s() * t.runden),
                                    size=16,
                                    weight=ft.FontWeight.W_700,
                                    data=("teil_gesamt", k),
                                ),
                                ft.Text(
                                    f"{t.runden} × {dauer_text(t.runde_s())}",
                                    size=12,
                                    opacity=0.7,
                                    expand=True,
                                ),
                                runden,
                                runden_lesen,
                            ],
                        ),
                    ),
                ],
            ),
        )

    def zeichnen() -> None:
        umschalter.clear()
        teile_spalte.controls = [teil_karte(k, t) for k, t in enumerate(teile_ed)]
        gesamt()

    # -- Reiter und Wischen ----------------------------------------------------------------

    def modus_setzen(modus: str) -> None:
        if modus == reiter["modus"]:
            return
        reiter["modus"] = modus
        kl = modus == REITER_KLAENGE
        wahl.selected = [modus]
        for umschalten in umschalter:
            umschalten(kl)
        zeiten_unten.visible = not kl
        klaenge_unten.visible = kl
        with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
            page.update()

    def reiter_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
        if e.control.selected:
            modus_setzen(str(e.control.selected[0]))

    def gewischt(e: Any) -> None:
        """Nach links zu den Klängen, nach rechts zurück zu den Zeiten (Ben, 9.11.2026)."""
        v = getattr(e, "primary_velocity", None) or 0
        if v < -WISCH_V:
            modus_setzen(REITER_KLAENGE)
        elif v > WISCH_V:
            modus_setzen(REITER_ZEITEN)

    wahl = ft.SegmentedButton(
        selected=[REITER_ZEITEN],
        show_selected_icon=False,
        segments=[
            ft.Segment(
                value=REITER_ZEITEN, label=ft.Text("Zeiten"), icon=ft.Icon(ft.Icons.SCHEDULE)
            ),
            ft.Segment(
                value=REITER_KLAENGE,
                label=ft.Text("Klänge"),
                icon=ft.Icon(ft.Icons.MUSIC_NOTE_OUTLINED),
            ),
        ],
        on_change=reiter_gewaehlt,
        expand=True,
        data="reiter",
    )

    def stand() -> tuple[Any, ...]:
        """Alles, was man hier ändern kann — für „Zurück speichert“ (Ben, 16.10.2026)."""
        return (
            name.value or "",
            [
                (
                    t.name,
                    [
                        (
                            z.name,
                            z.dauer_s,
                            z.klang,
                            z.zaehlt,
                            z.takt.als_dict() if z.takt is not None else None,
                            sorted(z.ausfuehrung.items()),
                        )
                        for z in t.zeilen
                    ],
                    t.runden,
                )
                for t in teile_ed
            ],
            klang_ganz["runde"],
            klang_ganz["ende"],
        )

    def bauen(profil_id: str, profil_name: str) -> TimerProfil | str:
        """Das Profil aus den Feldern — oder der Grund, warum nicht."""
        teile_neu: list[Teil] = []
        for t in teile_ed:
            abschnitte = [
                Abschnitt(
                    z.name.strip(),
                    z.dauer_s,
                    z.klang,
                    z.zaehlt,
                    takt=z.takt,
                    ausfuehrung=dict(z.ausfuehrung),
                )
                for z in t.zeilen
                if z.dauer_s
            ]
            teile_neu.append(Teil(abschnitte, t.runden, t.name.strip()))
        if not all(t.abschnitte for t in teile_neu):
            return "Eine Dauer fehlt — tippe auf die Zeit eines Abschnitts."
        erster, *weitere = teile_neu
        return TimerProfil(
            id=profil_id,
            name=profil_name,
            abschnitte=erster.abschnitte,
            runden=erster.runden,
            runden_klang=klang_ganz["runde"],
            ende_klang=klang_ganz["ende"],
            teil_name=erster.name if weitere else "",
            teile=weitere,
            name_in_marken=profil.name_in_marken if ohne_name else True,
            bibliothek=profil.bibliothek,
        )

    def signale_zeigen(_e: Any = None) -> None:
        """„Signale ›“: Countdown, Vibration, Lautstärke für alle Timer — als Blatt über dem
        Editor, damit nichts Ungespeichertes verloren geht."""
        page.show_dialog(
            ft.BottomSheet(
                scrollable=True,
                content=blatt_spalte(
                    [
                        ft.Text("Signale für alle Timer", size=17, weight=ft.FontWeight.W_600),
                        _klang_karte(page, state),
                        _lautstaerke_karte(page, state),
                        _signale_karte(page, state),
                    ]
                ),
            )
        )

    def ganz_klang(schluessel: str) -> Callable[[str], None]:
        def setzen(wert: str) -> None:
            klang_ganz[schluessel] = wert
            melden()

        return setzen

    def ganz_vorspielen(schluessel: str) -> Callable[..., None]:
        def handler(_e: Any = None) -> None:
            klang = klang_ganz[schluessel]
            if not klang:
                erster = teile_ed[0].zeilen[0].klang if teile_ed and teile_ed[0].zeilen else ""
                vorgabe = state.timer_signale().klang
                klang = (erster or vorgabe) if schluessel == "runde" else "ende"
            _vorspielen(page, state, klang)

        return handler

    def ganz_zeile(text: str, schluessel: str, vorgabe: str) -> ft.Control:
        return ft.Container(
            height=ZEILE_H,
            padding=ft.Padding.only(left=14, right=4),
            border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
            content=ft.Row(
                spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(text, size=14, expand=True),
                    _klang_feld(
                        page, state, klang_ganz[schluessel], vorgabe, ganz_klang(schluessel)
                    ),
                    ft.IconButton(
                        ft.Icons.PLAY_ARROW,
                        icon_size=22,
                        tooltip="Vorspielen",
                        on_click=ganz_vorspielen(schluessel),
                    ),
                ],
            ),
        )

    teile_ed.extend(teil_felder(t) for t in profil.alle_teile())
    zeichnen()
    zeiten_unten = ft.Column(
        spacing=10,
        controls=[
            ft.OutlinedButton(
                "Teil anhängen",
                icon=ft.Icons.ADD,
                tooltip="Eine Folge: Vorbereitung, Training, Cooldown …",
                on_click=teil_hinzufuegen,
            ),
            vorschau,
        ],
    )
    klaenge_unten = ft.Container(
        visible=False,
        border_radius=16,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        data="klaenge_ganz",
        content=ft.Column(
            spacing=0,
            controls=[
                ft.Container(
                    height=36,
                    padding=ft.Padding.only(left=14, right=4),
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                "FÜR DEN GANZEN TIMER",
                                size=11,
                                weight=ft.FontWeight.W_700,
                                opacity=0.7,
                                expand=True,
                            ),
                            ft.TextButton("Signale ›", on_click=signale_zeigen),
                        ],
                    ),
                ),
                ganz_zeile("Neue Runde", "runde", "wie Abschnitt 1"),
                ganz_zeile("Am Ende", "ende", "Fanfare"),
            ],
        ),
    )
    reiter_zeile = ft.Row(
        spacing=6,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[wahl, info_knopf(page, "Timer bearbeiten", TIMER_EDITOR_MD)],
    )
    # Ein Control hat einen Platz: in der Ansicht steht die Reiterzeile im Kopf, in der Karte
    # allein — wer ``reiter`` einsetzt, lässt ``kopf`` weg
    reiter_im_kopf = ft.Container(content=reiter_zeile)
    kopf = ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=6, bottom=10),
        border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        name,
                        ft.Container(
                            visible=ohne_name,
                            expand=True,
                            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                            border_radius=12,
                            bgcolor=ft.Colors.SECONDARY_CONTAINER,
                            content=ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Icon(ft.Icons.SCHEDULE, size=18),
                                    ft.Text(hinweis_text, size=13, expand=True),
                                ],
                            ),
                        ),
                        ft.Column(
                            spacing=0,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[gesamt_text, ft.Text("gesamt", size=11, opacity=0.7)],
                        ),
                    ],
                ),
                reiter_im_kopf,
            ],
        ),
    )

    return TimerEditor(
        name=name,
        kopf=kopf,
        reiter=reiter_zeile,
        gesamt=gesamt_text,
        teile=teile_spalte,
        zeiten_unten=zeiten_unten,
        klaenge_unten=klaenge_unten,
        gewischt=gewischt,
        stand=stand,
        bauen=bauen,
    )


__all__ = [
    "FUSS_H",
    "KOPF_H",
    "RECHTS_B",
    "REITER_KLAENGE",
    "REITER_ZEITEN",
    "ZEILE_H",
    "ZUSATZ_H",
    "TimerEditor",
    "timer_editor",
]
