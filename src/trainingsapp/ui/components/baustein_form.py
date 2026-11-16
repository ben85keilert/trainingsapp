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

Vereinfacht gegenüber dem Plan-Editor (bewusst, 16.11.2026): Der Timer ist eine Wahl aus der
Timer-Bibliothek (eingebettet als Kopie, `core.timer.ohne_verweise`), kein Editor; der Weg hat
ein eigenes schmales Formular mit denselben Auslösern wie `components/wege_form.py` (jenes
bearbeitet alle Wege eines Knotens samt Herkunft — ein Baustein ist genau eine Kante); Takt
und der Inhalt eines Wegs bleiben, wie sie sind, und stehen nur als Zeile da.
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
from trainingsapp.core.kursbau import Kurssicht, kante_dict, kante_von, timer_kern, timer_text
from trainingsapp.core.kursbloecke import (
    HART,
    PLAN_EINSTELLEN,
    PLAN_UEBUNG,
    PLAN_WEG,
    TEST,
    WEICH,
    ZU_ENDE,
    Block,
)
from trainingsapp.core.kursplan import ANKER_FEHLT, ENTFAELLT, OFFEN, UEBERNOMMEN
from trainingsapp.core.models import Exercise
from trainingsapp.core.standards import ziel_bereinigen
from trainingsapp.core.timer import TimerProfil, dauer_text, ohne_verweise
from trainingsapp.core.varianten import ist_variante
from trainingsapp.ui.components.blatt import blatt_spalte
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.karte import hinweis
from trainingsapp.ui.components.spec_form import SpecForm

#: Titel des Blatts je Art
BLATT_TITEL: Final[dict[str, str]] = {
    PLAN_UEBUNG: "Übung in den Plan",
    PLAN_EINSTELLEN: "Am Plan einstellen",
    PLAN_WEG: "Weg im Plan",
}

#: Schlüssel in den Auswahlfeldern für „nichts“ — eine Marke beginnt nie so
KEIN: Final = "@kein"
FEST: Final = "@fest"
BISHER: Final = "@bisher"
ABHAKEN: Final = "@abhaken"
WAEHLEN: Final = "@waehlen"

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
    bisher_timer = dict(block.timer)
    bibliothek: list[TimerProfil] = list(state.timer_profile())
    zustand: dict[str, Any] = {
        "ziel": TEST if block.ziel_aus else FEST if block.ziel else KEIN,
        "parameter": KEIN if block.felder is None else WAEHLEN if block.felder else ABHAKEN,
        "kante": kante_von(block),
        "form": None,
    }
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

    def fertig() -> Block:
        """Der Baustein, wie er übernommen würde — nur, was zu seinen Angaben gehört."""
        b = copy.deepcopy(entwurf)
        if b.art == PLAN_WEG:
            b.kante = kante_dict(zustand["kante"])
            return b
        if b.art == PLAN_UEBUNG and b.aus:
            b.uebung = ""
        ohne_uebung = b.art == PLAN_EINSTELLEN and not b.an
        if zustand["ziel"] != TEST or ohne_uebung:
            b.ziel_aus, b.faktor = "", 1.0
        if zustand["ziel"] != FEST or ohne_uebung:
            b.ziel = {}
        if b.art == PLAN_EINSTELLEN:
            if ohne_uebung or zustand["parameter"] == KEIN:
                b.felder = None
            elif zustand["parameter"] == ABHAKEN:
                b.felder = []
        return b

    def pruefen(b: Block) -> str | None:
        if b.art == PLAN_UEBUNG and not b.aus and not b.uebung:
            return "Wähle eine Übung."
        if b.art == PLAN_WEG and (not b.von or not b.zu):
            return "Ein Weg braucht „Von“ und „Zu“."
        if b.art == PLAN_EINSTELLEN and not b.stellt_ein:
            return "Stell mindestens eines ein — Ziel, Parameter, Timer, Übergang oder Pause."
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

    def parameter_teil() -> list[ft.Control]:
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
                    (KEIN, "keine Angabe"),
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
        angebot: dict[str, str] = {}
        for u in uebungen_hier:
            for f in sicht.katalog[u].result_spec.fields:
                if not ist_variante(f):
                    angebot.setdefault(f.key, f.label)
        for key in gewaehlt:
            angebot.setdefault(key, jetzt().feld(uebungen_hier, key).label)

        def schalter(key: str) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                jetzt_gewaehlt = list(entwurf.felder or [])
                if key in jetzt_gewaehlt:
                    jetzt_gewaehlt.remove(key)
                else:
                    jetzt_gewaehlt.append(key)
                entwurf.felder = [k for k in angebot if k in jetzt_gewaehlt]
                ziel_merken()
                neu_zeichnen()

            return handler

        teile.append(
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=[
                    ft.Chip(
                        label=ft.Text(name),
                        selected=key in gewaehlt,
                        on_select=schalter(key),
                        data=("baustein_feld", key),
                    )
                    for key, name in angebot.items()
                ]
                or [hinweis("Die Übung hat keine Parameter.")],
            )
        )
        return teile

    def timer_teil(label: str) -> ft.Control:
        """Keiner, einer aus der Timer-Bibliothek — oder der, den der Baustein schon trägt und
        den die Bibliothek nicht kennt („aus dem Kurs“)."""
        angebot = [p for p in bibliothek if not p.ist_stoppuhr]

        def bekannt(timer: Mapping[str, Any]) -> TimerProfil | None:
            kern = timer_kern(timer)
            return next((p for p in angebot if timer_kern(p.als_dict()) == kern), None)

        optionen = [
            (KEIN, "keiner"),
            *((f"t:{p.id}", f"{p.anzeigename} · {dauer_text(p.gesamt_s())}") for p in angebot),
        ]
        if bisher_timer and bekannt(bisher_timer) is None:
            optionen.append((BISHER, f"{timer_text(bisher_timer)} — aus dem Kurs"))
        passend = bekannt(entwurf.timer) if entwurf.timer else None
        wert = KEIN if not entwurf.timer else f"t:{passend.id}" if passend is not None else BISHER

        def setzen(key: str) -> None:
            if key == BISHER:
                entwurf.timer = dict(bisher_timer)
            elif key.startswith("t:"):
                profil = next((p for p in angebot if p.id == key[2:]), None)
                entwurf.timer = dict(ohne_verweise(profil.als_dict())) if profil is not None else {}
            else:
                entwurf.timer = {}

        return wahl(label, wert, optionen, setzen, "baustein_timer")

    def bleibt_teil() -> list[ft.Control]:
        """Was der Baustein trägt, das Blatt aber nicht einstellt — es bleibt, wie es ist."""
        teile: list[str] = []
        if entwurf.takt is not None:
            teile.append("kein Takt" if entwurf.takt.leer else f"Takt {entwurf.takt.kurztext()}")
        if entwurf.art == PLAN_UEBUNG and entwurf.felder is not None:
            namen = ", ".join(jetzt().feld(ziel_uebungen(), k).label for k in entwurf.felder)
            teile.append(f"Parameter: {namen}" if entwurf.felder else "nur abhaken")
        if not teile:
            return []
        return [
            hinweis("Bleibt, wie es im Kurs steht (hier nicht einstellbar): " + " · ".join(teile))
        ]

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
            timer_teil("Timer"),
            *bleibt_teil(),
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
            teile += [*ziel_teil(), *parameter_teil(), timer_teil("Timer der Übung")]
        else:
            teile.append(timer_teil("Timer für alle Übungen"))
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
        return [*teile, *bleibt_teil()]

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

    def bauen() -> list[ft.Control]:
        zustand["form"] = None  # die Zielmaske gibt es nur, wenn `ziel_teil` sie neu anlegt
        if entwurf.art == PLAN_UEBUNG:
            return uebung_form()
        if entwurf.art == PLAN_EINSTELLEN:
            return einstellen_form()
        return weg_form()

    # -- Knöpfe --------------------------------------------------------------------------

    def uebernehmen_getippt(_e: Any = None) -> None:
        ziel_merken()
        ergebnis = fertig()
        grund = pruefen(ergebnis)
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
    "BISHER",
    "BLATT_TITEL",
    "FEST",
    "KEIN",
    "WAEHLEN",
    "baustein_blatt",
    "vorschau_zeilen",
]
