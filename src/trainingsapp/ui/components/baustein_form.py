"""Bausteine am Kursplan im Kurs-Editor — das Blatt (Ben, 16.11.2026;
`docs/plan_kurs_ablauf.md` §11.6, Skizze K6).

Ein Kurs mit `Kurs.kursplan` baut einen Plan, der über die Kapitel wächst; die Kapitel tragen
dafür **Bausteine** (`core.kursbloecke`: ``plan_uebung``, ``plan_einstellen``, ``plan_weg``).
Hier steht nur die Oberfläche: `baustein_blatt` — je Art ein Formular („Übung in den Plan“,
„Am Plan einstellen“, „Weg im Plan“), darunter die Vorschau „So steht es in der Karte“
(`vorschau_zeilen`). Das Blatt hält einen Entwurf des Bausteins; „Übernehmen“ gibt ihn an das
Kapitel-Formular zurück, gespeichert wird erst dort.

**Gerechnet wird in `core/kursbau.py`** (`Kurssicht`): welche Marken zur Wahl stehen, welche
Verweise ins Leere zeigen, die Zeilen der Vorschau — das Blatt zeichnet sie und reicht die
Eingaben durch.

**Parameter, Takt und Timer** (Ben, 16.11.2026: „muss ebenfalls behoben werden“) stellt das
Blatt mit dem ein, was es dafür schon gibt:

- Parameter wie in „Im Plan einstellen“: Knöpfe je Parameter der Übung, darunter „Weitere
  Parameter holen“ aus dem Feldvorrat (`Kurssicht.parameter`) — oder „nur abhaken“.
- Takt über das Takt-Blatt (`components/takt_blatt.py`), das über diesem Blatt aufgeht.
- Timer: keiner, einer aus der Timer-Bibliothek oder ein **eigener** — bearbeitet im
  Timer-Editor (`components/timer_editor.py`: Zeiten · Klänge, Teile, Runden), aufgeklappt an
  Ort und Stelle wie in „Im Plan einstellen“. Der Baustein trägt ihn eingebettet
  (`core.kursbau.timer_einbetten`), nie als Verweis in die Bibliothek.

Vereinfacht bleibt der Weg: ein eigenes schmales Formular mit denselben Auslösern wie
`components/wege_form.py` (jenes bearbeitet alle Wege eines Knotens samt Herkunft — ein
Baustein ist genau eine Kante); der Inhalt eines Wegs bleibt, wie er ist.
"""

from __future__ import annotations

import contextlib
import copy
import inspect
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import replace
from typing import Any, Final

import flet as ft

from trainingsapp.core import ablauf as ab
from trainingsapp.core.kursbau import (
    Kurssicht,
    kante_dict,
    kante_von,
    timer_einbetten,
    timer_kern,
    timer_text,
)
from trainingsapp.core.kursbloecke import (
    HART,
    PLAN_EINSTELLEN,
    PLAN_ENTFERNEN,
    PLAN_TAUSCHEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    WEICH,
    ZU_ENDE,
    Block,
)
from trainingsapp.core.kursplan import ANKER_FEHLT, ENTFAELLT, OFFEN, UEBERNOMMEN
from trainingsapp.core.models import Exercise
from trainingsapp.core.result_spec import FieldSpec, ResultSpec
from trainingsapp.core.standards import ziel_bereinigen
from trainingsapp.core.takt import AUS, Takt
from trainingsapp.core.timer import TimerProfil, dauer_text
from trainingsapp.core.varianten import VARIANTE
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.karte import hinweis
from trainingsapp.ui.components.spec_form import SpecForm
from trainingsapp.ui.components.takt_blatt import takt_blatt, takt_zeile_text
from trainingsapp.ui.components.timer_editor import TimerEditor, timer_editor
from trainingsapp.ui.components.timer_zeile import neuer_timer
from trainingsapp.ui.components.wenn_form import wenn_fehler, wenn_teil

#: Titel des Blatts je Art
BLATT_TITEL: Final[dict[str, str]] = {
    PLAN_UEBUNG: "Übung in den Plan",
    PLAN_EINSTELLEN: "Am Plan einstellen",
    PLAN_WEG: "Weg im Plan",
    PLAN_ENTFERNEN: "Übung aus dem Plan nehmen",
    PLAN_TAUSCHEN: "Übung im Plan tauschen",
}

#: Schlüssel in den Auswahlfeldern für „nichts“ — eine Marke beginnt nie so
KEIN: Final = "@kein"
FEST: Final = "@fest"
ABHAKEN: Final = "@abhaken"
WAEHLEN: Final = "@waehlen"
#: Timer: ein eigener Timer des Bausteins (statt keinem oder einem aus der Bibliothek)
EIGEN: Final = "@eigen"
#: Takt: ausdrücklich keiner bzw. ein eingestellter (die Wahl öffnet das Takt-Blatt)
KEIN_TAKT: Final = "@kein_takt"
TAKT: Final = "@takt"

_STAND_SYMBOL: Final[dict[str, ft.IconData]] = {
    OFFEN: ft.Icons.HOURGLASS_EMPTY,
    ANKER_FEHLT: ft.Icons.WARNING_AMBER,
    ENTFAELLT: ft.Icons.LINK_OFF,
    UEBERNOMMEN: ft.Icons.CHECK,
}
_STAND_ZUSATZ: Final[dict[str, str]] = {
    UEBERNOMMEN: "steht im Beispielplan schon so — wird dann nicht angeboten",
}


def _unter(control: Any) -> Iterator[Any]:
    """Das Control und alles darunter (Inhalt und Kinder)."""
    yield control
    for name in ("content", "controls"):
        kind = getattr(control, name, None)
        for k in kind if isinstance(kind, list) else [kind] if kind is not None else []:
            if isinstance(k, ft.BaseControl):
                yield from _unter(k)


def _melden(wurzel: ft.Control, geaendert: Callable[[], None]) -> None:
    """Ruft ``geaendert``, wenn unter ``wurzel`` ein Textfeld verlassen oder ein Chip getippt
    wird — die Maske aus `SpecForm` meldet Änderungen nicht selbst."""

    def nach(alt: Callable[..., Any]) -> Callable[..., None]:
        ohne_ereignis = not inspect.signature(alt).parameters

        def handler(e: Any = None) -> None:
            if ohne_ereignis:
                alt()
            else:
                alt(e)
            geaendert()

        return handler

    for c in _unter(wurzel):
        if isinstance(c, ft.TextField) and c.on_blur is None:
            c.on_blur = lambda _e=None: geaendert()
        elif isinstance(c, ft.Chip) and c.on_click is not None:
            c.on_click = nach(c.on_click)


def vorschau_zeilen(sicht: Kurssicht, block: Block) -> list[ft.Control]:
    """Der Inhalt der Karte „So steht es in der Karte“ für ``block`` — ``sicht`` enthält ihn
    schon (`Kurssicht.mit`)."""
    if sicht.kurs.kursplan is None:
        return [
            hinweis(
                "Der Kurs baut keinen Plan — der Baustein bewirkt nichts. Einschalten unter "
                "„Kurs bearbeiten“ → „Der Kurs baut einen Plan“."
            )
        ]
    vorschau = sicht.vorschau()
    zeilen = [z for z in vorschau.zeilen if z.block_id == block.id]
    if not zeilen:
        return [hinweis("Noch keine Zeile — dem Baustein fehlt etwas.")]
    teile: list[ft.Control] = []
    for z in zeilen:
        unter = " — ".join(t for t in (z.unter, _STAND_ZUSATZ.get(z.stand, "")) if t)
        teile.append(
            ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
                data=("vorschau_zeile", z.id),
                controls=[
                    ft.Icon(
                        _STAND_SYMBOL.get(z.stand, ft.Icons.CHECK_BOX),
                        size=20,
                        color=ft.Colors.PRIMARY if z.anwendbar else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Column(
                        spacing=1,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Text(z.titel, size=14, weight=ft.FontWeight.W_600),
                            *([ft.Text(unter, size=12, opacity=0.7)] if unter else []),
                        ],
                    ),
                ],
            )
        )
    beispiel = sicht.beispiel_text(block, vorschau)
    teile.append(
        hinweis(
            " ".join(
                t for t in (beispiel, "Jede Zeile lässt sich im Kapitel einzeln abwählen.") if t
            )
        )
    )
    return teile


def timer_editor_teil(editor: TimerEditor, daten: str) -> ft.Control:
    """Der Timer-Editor (`components/timer_editor.py`) zum Einsetzen in ein Blatt: die Reiter
    Zeiten · Klänge, daneben die Gesamtzeit, darunter die Teile — Wischen wechselt den Reiter.
    Für den eigenen Timer eines Bausteins und den eines Tests
    (`views/kurs_bearbeiten.lauf_timer_blatt`). ``daten``: die Kennung des Teils."""
    return ft.Container(
        data=daten,
        content=ft.Column(
            spacing=8,
            tight=True,
            controls=[
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(expand=True, content=editor.reiter),
                        ft.Column(
                            spacing=0,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[editor.gesamt, ft.Text("gesamt", size=11, opacity=0.7)],
                        ),
                    ],
                ),
                ft.GestureDetector(on_horizontal_drag_end=editor.gewischt, content=editor.inhalt()),
            ],
        ),
    )


def baustein_blatt(
    page: Any,
    state: Any,
    sicht: Kurssicht,
    block: Block,
    *,
    neu: bool,
    uebungen: Sequence[Exercise],
    uebernehmen: Callable[[Block], None],
    loeschen: Callable[[], None] | None = None,
) -> ft.BottomSheet:
    """Das Formular eines Bausteins als Blatt von unten.

    Args:
        sicht: der Kurs, wie er im Kapitel-Formular steht (`Kurssicht`) — ohne den neuen
            Baustein, mit dem alten.
        block: der Baustein; bleibt unverändert — das Blatt arbeitet auf einer Kopie.
        neu: Er steht noch nicht in der Liste des Kapitels.
        uebungen: die Übungen zur Wahl (sortiert, ohne archivierte).
        uebernehmen: bekommt den fertigen Baustein — wann gespeichert wird, sagt das Kapitel.
        loeschen: „Baustein löschen“ — läuft, sobald das Blatt zu ist (die Rückfrage dazu ist
            ein eigener Dialog).
    """
    entwurf = copy.deepcopy(block)
    #: Die Timer-Bibliothek zur Wahl — ohne die Stoppuhr (sie ist kein Ablauf)
    bibliothek: list[TimerProfil] = [p for p in state.timer_profile() if not p.ist_stoppuhr]

    def aus_bibliothek(timer: Mapping[str, Any]) -> TimerProfil | None:
        """Der Timer der Bibliothek mit demselben Inhalt — ``None``: ein eigener."""
        kern = timer_kern(timer)
        return next((p for p in bibliothek if timer_kern(p.als_dict()) == kern), None)

    bekannt = aus_bibliothek(block.timer) if block.timer else None
    zustand: dict[str, Any] = {
        "ziel": TEST if block.ziel_aus else FEST if block.ziel else KEIN,
        "parameter": KEIN if block.felder is None else WAEHLEN if block.felder else ABHAKEN,
        "kante": kante_von(block),
        "form": None,
        #: die Ziel-Variante neben einem Ziel aus dem Test (`Kurssicht.variante_spec`)
        "form_variante": None,
        #: Der Timer: `KEIN`, ``t:<id>`` (aus der Bibliothek) oder `EIGEN`; ob der Editor des
        #: eigenen aufgeklappt ist; der Editor selbst, solange er steht
        "timer": KEIN if not block.timer else f"t:{bekannt.id}" if bekannt is not None else EIGEN,
        "timer_offen": False,
        "editor": None,
    }
    timer_kurz = ft.Text(size=13, expand=True, data="baustein_timer_kurz")
    nachher = Nachher()
    blatt: ft.BottomSheet
    felder = ft.Column(spacing=12, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    vorschau_spalte = ft.Column(spacing=8, tight=True, data="baustein_vorschau")
    meldung = ft.Text("", size=12, color=ft.Colors.ERROR, visible=False)

    def jetzt() -> Kurssicht:
        return sicht.mit(entwurf)

    # -- Entwurf lesen -------------------------------------------------------------------

    def ziel_uebungen() -> list[str]:
        if entwurf.art == PLAN_UEBUNG:
            return jetzt().uebungen_von(entwurf)
        return jetzt().uebungen_der_marke(entwurf.an) if entwurf.an else []

    def ziel_merken() -> None:
        """Was in der Zielmaske steht, in den Entwurf — vor Vorschau und Neuaufbau."""
        form = zustand["form"]
        if form is not None and zustand["ziel"] == FEST:
            entwurf.ziel = ziel_bereinigen(form.werte(), form.spec)
        neben = zustand["form_variante"]
        if neben is not None and zustand["ziel"] == TEST:
            gewaehlt = ziel_bereinigen(neben.werte(), neben.spec).get(VARIANTE)
            entwurf.ziel.pop(VARIANTE, None)
            if gewaehlt:
                entwurf.ziel[VARIANTE] = gewaehlt

    def fertig() -> Block:
        """Der Baustein, wie er übernommen würde — nur, was zu seinen Angaben gehört."""
        b = copy.deepcopy(entwurf)
        if b.art == PLAN_WEG:
            b.kante = kante_dict(zustand["kante"])
            return b
        if b.art in (PLAN_ENTFERNEN, PLAN_TAUSCHEN):
            return b
        if b.art == PLAN_UEBUNG and b.aus:
            b.uebung = ""
        ohne_uebung = b.art == PLAN_EINSTELLEN and not b.an
        if zustand["ziel"] != TEST or ohne_uebung:
            b.ziel_aus, b.faktor = "", 1.0
        if zustand["ziel"] == TEST and not ohne_uebung:
            # neben dem Ziel aus dem Test bleibt nur die Variante fest
            b.ziel = {k: w for k, w in b.ziel.items() if k == VARIANTE}
        elif zustand["ziel"] != FEST or ohne_uebung:
            b.ziel = {}
        if ohne_uebung or zustand["parameter"] == KEIN:
            b.felder = None
        elif zustand["parameter"] == ABHAKEN:
            b.felder = []
        return b

    def timer_merken() -> str | None:
        """Was im aufgeklappten Timer-Editor steht, in den Entwurf — oder der Grund, warum es
        so nicht geht (eine Dauer fehlt). Der eigene Timer heißt ``kurs-<block>``, wie beim
        Lesen eines Pakets (`core.kursbau.timer_einbetten`)."""
        editor = zustand["editor"]
        if editor is None or zustand["timer"] != EIGEN:
            return None
        bisher = TimerProfil.aus_dict(dict(entwurf.timer)) if entwurf.timer else None
        name = (bisher.name if bisher is not None else "") or "Timer"
        neu = editor.bauen(f"kurs-{entwurf.id}", name)
        if isinstance(neu, str):
            return neu
        entwurf.timer = timer_einbetten(neu, entwurf.id)
        return None

    def pruefen(b: Block) -> str | None:
        if b.art == PLAN_UEBUNG and not b.aus and not b.uebung:
            return "Wähle eine Übung."
        if b.art == PLAN_WEG and (not b.von or not b.zu):
            return "Ein Weg braucht „Von“ und „Zu“."
        if b.art in (PLAN_ENTFERNEN, PLAN_TAUSCHEN) and not b.an:
            return "Wähle die Planübung."
        if b.art == PLAN_TAUSCHEN and not b.uebung:
            return "Wähle die Übung, die an ihre Stelle tritt."
        if grund := wenn_fehler(b.wenn):
            return grund
        if b.art == PLAN_EINSTELLEN and not b.stellt_ein:
            return "Stell mindestens eines ein — Ziel, Parameter, Timer, Takt, Übergang oder Pause."
        form = zustand["form"]
        if form is not None and zustand["ziel"] == FEST and (probleme := form.pruefen()):
            return "Ungültig: " + ", ".join(probleme)
        # Ein Verweis ins Leere (nach dem Umordnen, aus einem Kurs von früher) wird hier nicht
        # noch einmal bestätigt — die Paketprüfung nähme ihn nicht an
        if fehlt := sicht.mit(b).haengt(b):
            return "Verweis fehlt: " + ", ".join(fehlt) + " — bitte neu wählen."
        return None

    # -- Zeichnen ------------------------------------------------------------------------

    def vorschau_zeichnen() -> None:
        ziel_merken()
        b = fertig()
        vorschau_spalte.controls = [
            ft.Text("SO STEHT ES IN DER KARTE", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            *vorschau_zeilen(sicht.mit(b), b),
        ]

    def vorschau_neu() -> None:
        vorschau_zeichnen()
        with contextlib.suppress(Exception):
            vorschau_spalte.update()

    def neu_zeichnen() -> None:
        meldung.visible = False
        felder.controls = bauen()
        vorschau_zeichnen()
        for c in (felder, vorschau_spalte, meldung):
            with contextlib.suppress(Exception):
                c.update()

    def wahl(
        label: str,
        wert: str,
        optionen: Sequence[tuple[str, str]],
        setzen: Callable[[str], None],
        daten: str,
        *,
        filtern: bool = False,
        daneben: Sequence[ft.Control] = (),
    ) -> ft.Control:
        """Ein Auswahlfeld in voller Breite; die Wahl geht in den Entwurf, dann wird neu
        gezeichnet (andere Felder hängen davon ab)."""
        feld = ft.Dropdown(
            label=label,
            value=wert if wert in [k for k, _ in optionen] else None,
            options=[ft.DropdownOption(key=k, text=t) for k, t in optionen],
            enable_filter=filtern,
            editable=filtern,
            menu_height=320,
            expand=True,
            data=daten,
        )

        def gewaehlt(_e: Any = None) -> None:
            ziel_merken()
            setzen(str(feld.value or KEIN))
            neu_zeichnen()

        feld.on_select = gewaehlt
        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[feld, *daneben],
        )

    def zahlfeld(
        label: str,
        wert: str,
        setzen: Callable[[str], None],
        daten: str,
        breite: int = 130,
        leer: str | None = None,
    ) -> ft.TextField:
        """Ein Zahlenfeld: Jede Eingabe geht in den Entwurf, die Vorschau folgt beim Verlassen.
        ``leer``: was im leeren Feld steht (ein langes Label bräche im schmalen Feld um)."""
        feld = ft.TextField(
            label=label,
            value=wert,
            hint_text=leer,
            width=breite,
            dense=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            data=daten,
        )

        def getippt(_e: Any = None) -> None:
            setzen(str(feld.value or "").replace(",", ".").strip())

        def verlassen(_e: Any = None) -> None:
            getippt()
            vorschau_neu()

        feld.on_change = getippt
        feld.on_blur = verlassen
        return feld

    def marken_optionen(wert: str, davor: str = "", ende: bool = False) -> list[tuple[str, str]]:
        """Die Marken zur Wahl: nur, was die Paketprüfung annimmt (`Kurssicht.marken_davor` —
        die Grundlage und „Übung dazu“ **davor**; ``ende``: das Feld kennt auch „Ende“). Eine
        gesetzte, die es hier nicht gibt, bleibt sichtbar — „Übernehmen“ verlangt dann eine
        neue Wahl."""
        optionen = [(m, f"{davor}{n}") for m, n in jetzt().marken_davor(entwurf.id)]
        if wert and not (ende and wert == ZU_ENDE) and wert not in dict(optionen):
            optionen.append((wert, f"{davor}{jetzt().marke_name(wert, lang=True)} — fehlt hier"))
        return optionen

    # -- Ziel, Parameter, Timer ----------------------------------------------------------------

    def ziel_teil() -> list[ft.Control]:
        tests = jetzt().tests()
        optionen = [
            (KEIN, "keins"),
            (FEST, "fester Wert"),
            *((f"{TEST}:{k}", f"aus dem Test „{n}“") for k, n in tests),
        ]
        wert = f"{TEST}:{entwurf.ziel_aus}" if zustand["ziel"] == TEST else str(zustand["ziel"])
        if zustand["ziel"] == TEST and entwurf.ziel_aus not in dict(tests):
            optionen.append((wert, "aus einem Test, den es hier nicht gibt"))

        def setzen(key: str) -> None:
            if key.startswith(f"{TEST}:"):
                zustand["ziel"], entwurf.ziel_aus = TEST, key.split(":", 1)[1]
            else:
                zustand["ziel"], entwurf.ziel_aus = (FEST if key == FEST else KEIN), ""

        def faktor_setzen(roh: str) -> None:
            with contextlib.suppress(ValueError):
                entwurf.faktor = min(max(float(roh), 0.1), 3.0)

        daneben = (
            [
                zahlfeld(
                    "mal",
                    f"{entwurf.faktor:g}".replace(".", ","),
                    faktor_setzen,
                    "baustein_faktor",
                    breite=96,
                )
            ]
            if zustand["ziel"] == TEST
            else []
        )
        teile: list[ft.Control] = [
            wahl("Ziel", wert, optionen, setzen, "baustein_ziel", daneben=daneben)
        ]
        if zustand["ziel"] == TEST:
            # „mal“ ist eine Vorgabe (W3, Ben 17.11.2026): Nach dem Test steht sie auf der
            # Karte „Wert für den Plan“ — die Person kann sie ändern
            teile.append(
                hinweis(
                    "„mal“ ist die Vorgabe: Nach dem Test sieht die Person, was der Plan "
                    "nimmt, und kann es ändern — ganz, Anteil oder von Hand."
                )
            )
            # Die Variante lässt sich daneben fest setzen (Ben, 25.11.2026)
            neben_spec = jetzt().variante_spec(ziel_uebungen())
            if neben_spec is not None:
                neben = SpecForm(
                    neben_spec,
                    {VARIANTE: entwurf.ziel.get(VARIANTE)},
                    page=page,
                    vorgaben=False,
                )
                _melden(neben.control, vorschau_neu)
                zustand["form_variante"] = neben
                teile.append(
                    ft.Container(
                        padding=ft.Padding.only(left=12),
                        content=neben.control,
                        data="baustein_zielvariante",
                    )
                )
        if zustand["ziel"] == FEST:
            spec = jetzt().ziel_spec(ziel_uebungen())
            if spec.fields:
                form = SpecForm(spec, dict(entwurf.ziel), page=page, vorgaben=False)
                _melden(form.control, vorschau_neu)
                zustand["form"] = form
                teile.append(
                    ft.Container(
                        padding=ft.Padding.only(left=12),
                        content=form.control,
                        data="baustein_zielwerte",
                    )
                )
            else:
                teile.append(
                    hinweis(
                        "Dafür gibt es kein Feld: Wähle zuerst die Übung — bei einer Auswahl "
                        "geht ein fester Wert nur in einem Feld, das alle ihre Übungen haben."
                    )
                )
        return teile

    def parameter_teil(leer: str) -> list[ft.Control]:
        """Die Parameter der Planübung wie in „Im Plan einstellen“: ``leer`` (keine Angabe —
        die Planübung folgt der Übung bzw. bleibt, wie sie ist), „nur abhaken“ oder eine
        Auswahl — Knöpfe je Parameter der Übung, darunter der übrige Feldvorrat („Weitere
        Parameter holen“), in der Ordnung des Vorrats (`Kurssicht.parameter`)."""
        uebungen_hier = ziel_uebungen()

        def setzen(key: str) -> None:
            zustand["parameter"] = key
            if key == WAEHLEN and entwurf.felder is None:
                entwurf.felder = []

        teile: list[ft.Control] = [
            wahl(
                "Parameter",
                str(zustand["parameter"]),
                [
                    (KEIN, leer),
                    (ABHAKEN, "nur abhaken — ohne Eingabe"),
                    (WAEHLEN, "auswählen …"),
                ],
                setzen,
                "baustein_parameter",
            )
        ]
        if zustand["parameter"] != WAEHLEN:
            return teile
        gewaehlt = list(entwurf.felder or [])
        eigene, vorrat = jetzt().parameter(uebungen_hier)
        bekannte = {f.key for f in (*eigene, *vorrat)}
        #: gewählt, aber nicht (mehr) im Angebot — ein Feld einer Übung von früher: bleibt
        #: sichtbar, damit man es abwählen kann
        fremde = [jetzt().feld(uebungen_hier, k) for k in gewaehlt if k not in bekannte]

        def schalter(key: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                ziel_merken()
                wahl_jetzt = set(entwurf.felder or []) ^ {key}
                entwurf.felder = jetzt().felder_wahl(
                    uebungen_hier, [k for k in (*gewaehlt, key) if k in wahl_jetzt]
                )
                neu_zeichnen()

            return handler

        def chips(felder_: Sequence[FieldSpec]) -> ft.Control:
            return ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=[
                    ft.Chip(
                        label=ft.Text(f.label),
                        selected=f.key in gewaehlt,
                        show_checkmark=True,
                        on_select=schalter(f.key),
                        data=("baustein_feld", f.key),
                    )
                    for f in felder_
                ],
            )

        if eigene or fremde:
            teile.append(chips([*eigene, *fremde]))
        elif not uebungen_hier:
            teile.append(hinweis("Wähle zuerst die Übung — dann stehen ihre Parameter hier."))
        teile += [ft.Text("Weitere Parameter holen", size=12, opacity=0.7), chips(vorrat)]
        if not gewaehlt:
            teile.append(hinweis("Kein Parameter gewählt — das heißt „nur abhaken“."))
        return teile

    def timer_spec() -> ResultSpec | None:
        """Die Felder der Übung für den Timer-Editor (je Abschnitt eine Ausführung) — nur, wenn
        es genau eine Übung ist; am Plan und bei „der gewählten“ gibt es keine."""
        bekannte = [u for u in dict.fromkeys(ziel_uebungen()) if u in sicht.katalog]
        return sicht.katalog[bekannte[0]].result_spec if len(bekannte) == 1 else None

    def timer_kurz_setzen() -> None:
        """Der eigene Timer in einer Zeile, wie die Karte ihn nennt — zugeklappt mit der
        Gesamtzeit (aufgeklappt zeigt sie der Editor darunter)."""
        profil = TimerProfil.aus_dict(dict(entwurf.timer)) if entwurf.timer else None
        gesamt = (
            f" · gesamt {dauer_text(profil.gesamt_s())}"
            if profil is not None and not zustand["timer_offen"]
            else ""
        )
        timer_kurz.value = f"{timer_text(entwurf.timer)}{gesamt}"

    def timer_geaendert() -> None:
        """Der Timer-Editor meldet jede Änderung — sie gilt sofort im Entwurf; solange eine
        Dauer fehlt, bleibt der letzte vollständige Stand."""
        if timer_merken() is None:
            timer_kurz_setzen()
            with contextlib.suppress(Exception):
                timer_kurz.update()
            vorschau_neu()

    def timer_umschalten(_e: Any = None) -> None:
        ziel_merken()
        timer_merken()
        zustand["timer_offen"] = not zustand["timer_offen"]
        neu_zeichnen()

    def timer_teil(label: str) -> list[ft.Control]:
        """Keiner, einer aus der Timer-Bibliothek — oder ein **eigener** Timer dieses
        Bausteins, bearbeitet im Timer-Editor an Ort und Stelle (`components/timer_editor.py`,
        derselbe wie in „Im Plan einstellen“). Ausgangspunkt des eigenen ist der Timer, der
        gerade gewählt ist, sonst Belastung 30 s · Pause 15 s."""
        optionen = [
            (KEIN, "keiner"),
            *((f"t:{p.id}", f"{p.anzeigename} · {dauer_text(p.gesamt_s())}") for p in bibliothek),
            (EIGEN, "eigener Timer …"),
        ]

        def setzen(key: str) -> None:
            timer_merken()
            zustand["timer"] = KEIN
            if key == EIGEN:
                profil = TimerProfil.aus_dict(dict(entwurf.timer)) if entwurf.timer else None
                entwurf.timer = timer_einbetten(profil or neuer_timer(), entwurf.id)
                zustand["timer"], zustand["timer_offen"] = EIGEN, True
            elif key.startswith("t:"):
                profil = next((p for p in bibliothek if p.id == key[2:]), None)
                entwurf.timer = timer_einbetten(profil) if profil is not None else {}
                zustand["timer"] = key if profil is not None else KEIN
            else:
                entwurf.timer = {}

        teile: list[ft.Control] = [
            wahl(label, str(zustand["timer"]), optionen, setzen, "baustein_timer")
        ]
        zustand["editor"] = None
        if zustand["timer"] != EIGEN:
            return teile
        offen = bool(zustand["timer_offen"])
        timer_kurz_setzen()
        teile.append(
            ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.TIMER_OUTLINED, size=18, opacity=0.8),
                    timer_kurz,
                    ft.IconButton(
                        ft.Icons.EXPAND_LESS if offen else ft.Icons.EDIT_OUTLINED,
                        tooltip="Editor schließen"
                        if offen
                        else "Timer bearbeiten: Zeiten · Klänge",
                        icon_size=20,
                        on_click=timer_umschalten,
                        data="baustein_timer_editor_auf",
                    ),
                ],
            )
        )
        if not offen:
            return teile
        profil = TimerProfil.aus_dict(dict(entwurf.timer)) or neuer_timer()
        profil.bibliothek = ""
        editor = timer_editor(page, state, profil, spec=timer_spec(), geaendert=timer_geaendert)
        zustand["editor"] = editor
        teile.append(timer_editor_teil(editor, "baustein_timer_editor"))
        return teile

    def takt_teil(leer: str, wer: str) -> ft.Control:
        """Der Takt: ``leer`` (keine Angabe), ausdrücklich keiner — oder einer aus dem
        Takt-Blatt (`components/takt_blatt.py`: Vorlagen, Phasen, Tempo, Klang), das über
        diesem Blatt aufgeht. Gerechnet wird nur in `core/takt.py`."""
        takt = entwurf.takt
        hat = takt is not None and not takt.leer

        def uebernommen(neu_takt: Takt | None) -> None:
            entwurf.takt = AUS if neu_takt is None or neu_takt.leer else neu_takt
            neu_zeichnen()

        def oeffnen(_e: Any = None) -> None:
            ziel_merken()
            timer_merken()
            start = entwurf.takt if entwurf.takt is not None and not entwurf.takt.leer else None
            page.show_dialog(
                takt_blatt(
                    page,
                    state,
                    takt=start or jetzt().takt_vorgabe(ziel_uebungen()),
                    titel=f"Takt · {wer}",
                    in_den_plan=uebernommen,
                )
            )

        def setzen(key: str) -> None:
            if key == TAKT:
                oeffnen()  # der Entwurf bleibt, bis das Takt-Blatt „Übernehmen“ meldet
            else:
                entwurf.takt = AUS if key == KEIN_TAKT else None

        optionen = [
            (KEIN, leer),
            (KEIN_TAKT, "kein Takt"),
            # der Takt heißt wie in „Im Plan einstellen“ (`takt_zeile_text`)
            (TAKT, takt_zeile_text(takt).removeprefix("Takt: ") if hat else "einstellen …"),
        ]
        wert = KEIN if takt is None else TAKT if hat else KEIN_TAKT
        stift = ft.IconButton(
            ft.Icons.EDIT_OUTLINED,
            tooltip="Takt einstellen: Phasen, Tempo, Klang",
            on_click=oeffnen,
            data="baustein_takt_stift",
        )
        return wahl("Takt", wert, optionen, setzen, "baustein_takt", daneben=[stift])

    # -- Die drei Formulare ------------------------------------------------------------------

    def uebung_form() -> list[ft.Control]:
        auswahlen = jetzt().auswahlen()
        optionen = [
            *((f"aus:{k}", f"die gewählte aus „{n}“") for k, n in auswahlen),
            *((f"u:{u.id}", u.name) for u in uebungen),
        ]
        if entwurf.aus:
            wert = f"aus:{entwurf.aus}"
            if entwurf.aus not in dict(auswahlen):
                optionen.append((wert, "die gewählte — die Auswahl fehlt hier"))
        elif entwurf.uebung:
            wert = f"u:{entwurf.uebung}"
            if wert not in dict(optionen):
                optionen.append((wert, f"{jetzt().name(entwurf.uebung)} (archiviert)"))
        else:
            wert = KEIN

        def uebung_setzen(key: str) -> None:
            if key.startswith("aus:"):
                entwurf.aus, entwurf.uebung = key[4:], ""
            elif key.startswith("u:"):
                entwurf.uebung, entwurf.aus = key[2:], ""

        def hinter_setzen(key: str) -> None:
            entwurf.hinter = "" if key == KEIN else key

        return [
            wahl("Übung", wert, optionen, uebung_setzen, "baustein_uebung", filtern=True),
            wahl(
                "Wohin im Plan",
                entwurf.hinter or KEIN,
                [(KEIN, "ans Ende"), *marken_optionen(entwurf.hinter, "hinter ")],
                hinter_setzen,
                "baustein_hinter",
            ),
            *ziel_teil(),
            *parameter_teil("wie die Übung"),
            *timer_teil("Timer"),
            takt_teil("wie die Übung", jetzt().wer(entwurf)),
        ]

    def einstellen_form() -> list[ft.Control]:
        def an_setzen(key: str) -> None:
            entwurf.an = "" if key == KEIN else key

        def uebergang_setzen(key: str) -> None:
            entwurf.uebergang = key if key in (HART, WEICH) else ""

        def pause_setzen(key: str) -> None:
            entwurf.pause_ohne_timer = {"an": True, "aus": False}.get(key)

        teile: list[ft.Control] = [
            wahl(
                "An",
                entwurf.an or KEIN,
                [(KEIN, "dem Plan — für alle Übungen"), *marken_optionen(entwurf.an)],
                an_setzen,
                "baustein_an",
            )
        ]
        if entwurf.an:
            teile += [
                *ziel_teil(),
                *parameter_teil("keine Angabe"),
                *timer_teil("Timer der Übung"),
                takt_teil("keine Angabe", jetzt().marke_name(entwurf.an)),
            ]
        else:
            teile += [
                *timer_teil("Timer für alle Übungen"),
                takt_teil("keine Angabe", "alle Übungen"),
            ]
        pause = entwurf.pause_ohne_timer
        if not entwurf.an or entwurf.uebergang or pause is not None:
            teile += [
                ft.Text(
                    "IM WORKOUT — GILT FÜR DEN GANZEN PLAN",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    opacity=0.6,
                ),
                wahl(
                    "Übergang",
                    entwurf.uebergang or KEIN,
                    [
                        (KEIN, "keine Angabe"),
                        (HART, "hart — geht von selbst weiter"),
                        (WEICH, "weich — man tippt weiter"),
                    ],
                    uebergang_setzen,
                    "baustein_uebergang",
                ),
                hinweis("Nur die Vorgabe — umschalten kann man im Workout jederzeit."),
                wahl(
                    "Pause nach Übungen ohne Timer",
                    KEIN if pause is None else "an" if pause else "aus",
                    [(KEIN, "keine Angabe"), ("an", "an"), ("aus", "aus")],
                    pause_setzen,
                    "baustein_pause",
                ),
            ]
        return teile

    def weg_form() -> list[ft.Control]:
        kante: ab.Kante = zustand["kante"]

        def kante_setzen(**werte: Any) -> None:
            zustand["kante"] = replace(zustand["kante"], **werte)

        def von_setzen(key: str) -> None:
            entwurf.von = "" if key == KEIN else key

        def zu_setzen(key: str) -> None:
            entwurf.zu = "" if key == KEIN else key

        def ausloeser(art: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                alt: ab.Kante = zustand["kante"]
                # Die Zahl wandert nur zwischen den beiden Wiederholungs-Auslösern mit — wie
                # im Wege-Formular des Ablaufs (`components/wege_form.py`, N72)
                zahl = (
                    alt.n
                    if alt.n and {art, alt.ausloeser} <= {ab.WDH, ab.WDH_IN_ZEIT}
                    else 12
                    if art in (ab.WDH, ab.WDH_IN_ZEIT)
                    else 7
                    if art == ab.SKALA
                    else 0
                )
                kante_setzen(
                    ausloeser=art,
                    n=zahl,
                    bis=alt.bis if art == ab.SKALA else None,
                    sekunden=(alt.sekunden or 60.0) if art == ab.WDH_IN_ZEIT else 0.0,
                    ausfuehren=alt.ausfuehren and art != ab.FREI,
                )
                neu_zeichnen()

            return handler

        def ganz(name: str) -> Callable[[str], None]:
            def setzen(roh: str) -> None:
                if name == "bis" and not roh:
                    kante_setzen(bis=None)
                    return
                with contextlib.suppress(ValueError):
                    wert = float(roh)
                    skala = zustand["kante"].ausloeser == ab.SKALA
                    if name == "sekunden":
                        if wert > 0:
                            kante_setzen(sekunden=wert)
                    elif skala or wert >= 1:  # nur eine Skala kennt 0 und negative Werte
                        kante_setzen(**{name: int(wert)})

            return setzen

        def selbst_gewaehlt(e: Any) -> None:
            gewaehlt = list(e.control.selected or [])
            kante_setzen(ausfuehren=bool(gewaehlt) and gewaehlt[0] == "ausfuehren")
            vorschau_neu()

        def pflicht_gewaehlt(e: Any) -> None:
            kante_setzen(pflicht=bool(e.control.value))
            vorschau_neu()

        def text_getippt(e: Any) -> None:
            kante_setzen(text=str(e.control.value or "").strip())

        teile: list[ft.Control] = [
            wahl(
                "Von", entwurf.von or KEIN, marken_optionen(entwurf.von), von_setzen, "baustein_von"
            ),
            wahl(
                "Zu",
                entwurf.zu or KEIN,
                [*marken_optionen(entwurf.zu, ende=True), (ZU_ENDE, "Ende des Plans")],
                zu_setzen,
                "baustein_zu",
            ),
            ft.Text("WEITER, WENN", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=[
                    ft.Chip(
                        label=ft.Text(text),
                        selected=kante.ausloeser == art,
                        show_checkmark=False,
                        on_select=ausloeser(art),
                        data=("baustein_ausloeser", art),
                    )
                    for art, text in ab.AUSLOESER_TEXT.items()
                ],
            ),
        ]
        zahlen: list[ft.Control] = []
        if kante.ausloeser in (ab.WDH, ab.WDH_IN_ZEIT, ab.SKALA):
            zahlen.append(
                zahlfeld(
                    "Skala ab" if kante.ausloeser == ab.SKALA else "Wiederholungen",
                    str(kante.n),
                    ganz("n"),
                    "baustein_n",
                )
            )
        if kante.ausloeser == ab.WDH_IN_ZEIT:
            zahlen.append(
                zahlfeld(
                    "in Sekunden", f"{kante.sekunden:g}", ganz("sekunden"), "baustein_sekunden"
                )
            )
        if kante.ausloeser == ab.SKALA:
            zahlen.append(
                zahlfeld(
                    "Skala bis",
                    "" if kante.bis is None else str(kante.bis),
                    ganz("bis"),
                    "baustein_bis",
                    leer="offen",
                )
            )
        if zahlen:
            teile.append(ft.Row(wrap=True, spacing=8, run_spacing=6, controls=zahlen))
        if kante.ausloeser == ab.ZEIT:
            teile.append(
                hinweis("Ohne Timer an der Übung gilt „Zeit ab“, sobald „Fertig“ getippt ist.")
            )
        if kante.ausloeser != ab.FREI:
            teile.append(
                ft.SegmentedButton(
                    selected=["ausfuehren" if kante.ausfuehren else "anbieten"],
                    show_selected_icon=False,
                    segments=[
                        ft.Segment(value="anbieten", label=ft.Text("Anbieten")),
                        ft.Segment(value="ausfuehren", label=ft.Text("Von selbst")),
                    ],
                    on_change=selbst_gewaehlt,
                    data="baustein_selbst",
                )
            )
        teile += [
            ft.Switch(
                label="Pflicht — andere Wege erst, wenn erfüllt",
                value=kante.pflicht,
                on_change=pflicht_gewaehlt,
                data="baustein_pflicht",
            ),
            ft.TextField(
                label="Beschriftung — wann ist dieser Weg gemeint?",
                value=kante.text,
                dense=True,
                on_change=text_getippt,
                on_blur=lambda _e=None: vorschau_neu(),
                data="baustein_text",
            ),
        ]
        if not kante.inhalt.leer:
            teile.append(
                hinweis("Der Inhalt dieses Wegs (Text, Link) bleibt, wie er im Kurs steht.")
            )
        return teile

    def entfernen_form() -> list[ft.Control]:
        """Herausnehmen (Ben, 23.11.2026): welche Planübung geht — mehr braucht es nicht."""

        def an_setzen(key: str) -> None:
            entwurf.an = "" if key == KEIN else key

        return [
            wahl(
                "Welche Planübung",
                entwurf.an or KEIN,
                marken_optionen(entwurf.an),
                an_setzen,
                "baustein_an",
            ),
            ft.Text(
                "Sie geht aus dem Plan — auf Tipp in der Karte „Das ändert sich an deinem "
                "Plan“. Die Einträge der Übung bleiben.",
                size=12,
                opacity=0.7,
            ),
        ]

    def tauschen_form() -> list[ft.Control]:
        """Tauschen: Die Planübung wird eine andere Übung; Ziel und Parameter beginnen neu."""

        def an_setzen(key: str) -> None:
            entwurf.an = "" if key == KEIN else key

        def uebung_setzen(key: str) -> None:
            entwurf.uebung = key[2:] if key.startswith("u:") else ""

        optionen = [(f"u:{u.id}", u.name) for u in uebungen]
        wert = f"u:{entwurf.uebung}" if entwurf.uebung else KEIN
        if entwurf.uebung and wert not in dict(optionen):
            optionen.append((wert, f"{jetzt().name(entwurf.uebung)} (archiviert)"))
        return [
            wahl(
                "Welche Planübung",
                entwurf.an or KEIN,
                marken_optionen(entwurf.an),
                an_setzen,
                "baustein_an",
            ),
            wahl("Wird zu", wert, optionen, uebung_setzen, "baustein_uebung", filtern=True),
            ft.Text(
                "Die Planübung bleibt an ihrer Stelle und folgt der neuen Übung — ihr Ziel und "
                "ihre Parameter beginnen neu.",
                size=12,
                opacity=0.7,
            ),
        ]

    def bauen() -> list[ft.Control]:
        # Zielmaske und Timer-Editor gibt es nur, wenn ihr Teil sie neu anlegt
        zustand["form"] = zustand["form_variante"] = zustand["editor"] = None
        if entwurf.art == PLAN_UEBUNG:
            teile = uebung_form()
        elif entwurf.art == PLAN_EINSTELLEN:
            teile = einstellen_form()
        elif entwurf.art == PLAN_ENTFERNEN:
            teile = entfernen_form()
        elif entwurf.art == PLAN_TAUSCHEN:
            teile = tauschen_form()
        else:
            teile = weg_form()
        # „Nur wenn …“ (Ben, 23.11.2026): Der Baustein gilt nur bei bestimmten Antworten
        return [
            *teile,
            wenn_teil(
                jetzt().fragen(entwurf.id), entwurf.wenn, vorschau_neu, kennung="baustein_wenn"
            ),
        ]

    # -- Knöpfe --------------------------------------------------------------------------

    def uebernehmen_getippt(_e: Any = None) -> None:
        ziel_merken()
        grund = timer_merken()
        ergebnis = fertig()
        grund = grund or pruefen(ergebnis)
        if grund is not None:
            meldung.value, meldung.visible = grund, True
            with contextlib.suppress(Exception):
                meldung.update()
            return
        uebernehmen(ergebnis)
        schliessen(blatt)

    def loeschen_getippt(_e: Any = None) -> None:
        if loeschen is not None:
            nachher.danach(loeschen)
        schliessen(blatt)

    # „Baustein löschen“ steht wie in K6 unten links im Inhalt — neben „Abbrechen“ und
    # „Übernehmen“ passte es bei 412 px nicht in die Zeile (Web-Foto, 16.11.2026)
    weg: list[ft.Control] = []
    if loeschen is not None and not neu:
        weg.append(
            ft.Row(
                controls=[
                    ft.TextButton(
                        "Baustein löschen",
                        icon=ft.Icons.DELETE_OUTLINE,
                        style=ft.ButtonStyle(color=ft.Colors.ERROR),
                        on_click=loeschen_getippt,
                        data="baustein_loeschen",
                    )
                ]
            )
        )
    fuss: list[ft.Control] = [
        ft.Container(expand=True),
        ft.TextButton("Abbrechen", on_click=lambda: schliessen(blatt), data="baustein_abbrechen"),
        ft.FilledButton(
            "Übernehmen",
            icon=ft.Icons.CHECK,
            on_click=uebernehmen_getippt,
            data="baustein_uebernehmen",
        ),
    ]
    felder.controls = bauen()
    vorschau_zeichnen()
    blatt = ft.BottomSheet(
        show_drag_handle=True,
        scrollable=True,
        on_dismiss=nachher.bei_schliessen,
        data=("baustein_blatt", block.id),
        content=blatt_spalte(
            [
                ft.Text(
                    BLATT_TITEL.get(block.art, "Baustein"), size=20, weight=ft.FontWeight.W_500
                ),
                felder,
                ft.Container(
                    padding=14,
                    border_radius=16,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    content=vorschau_spalte,
                ),
                meldung,
                *weg,
            ],
            [ft.Row(spacing=4, controls=fuss)],
            geschaetzt=520,
        ),
    )
    return blatt


__all__ = [
    "ABHAKEN",
    "BLATT_TITEL",
    "EIGEN",
    "FEST",
    "KEIN",
    "KEIN_TAKT",
    "TAKT",
    "WAEHLEN",
    "baustein_blatt",
    "timer_editor_teil",
    "vorschau_zeilen",
]
