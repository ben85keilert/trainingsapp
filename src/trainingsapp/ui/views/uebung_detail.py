"""Die Übungsseite — eine Route auf dem Stapel (`/uebung/<id>`, unter einem Plan `…/info/<item>`).

Ben, 22.10.2026 (P79, `docs/plan_uebungen_einstellen.md`): Das i führt überall hierher — aus
dem Plan, von Heute, aus Verlauf, Tagebuch, Paket, Archiv und Papierkorb. Die Seite zeigt alles
und ändert nichts; geändert wird über den Stift („Übung bearbeiten“, gilt überall) oder, aus
einem Plan, über „Im Plan einstellen“ (Karte „In diesem Plan“ oben, Abschnitt „In Plänen“).

Aus welchem Paket die Übung kommt, steht unscheinbar in Klammern hinter der
Beschreibung (Ben, 14.10.2026) — „eigene Übung“, wenn sie hier angelegt oder
kopiert wurde. Weicht eine Paketübung von ihrem Paketstand ab, steht dort
„geändert“ und unten, was abweicht; zurück führt „Auf Paketstand zurücksetzen“ unter
„Übung bearbeiten“ (Ben, 7.11.2026, `PaketRepo.zuruecksetzen`). Die Erklärung der Varianten
stand früher in jeder Übung; sie steht jetzt allgemein in der Hilfe
(`ui/components/hilfe.UEBUNGEN_MD`).

Übersichtlicher (Ben, 7.11.2026): Die Regionen stehen ohne Überschrift unter dem Typ, das Bild
ist groß (`KOPF_BILD`), „Videos und Links“ und „Aufnahmen mit dieser Übung“ erscheinen nur mit
Inhalt, und Erklärtexte stehen nicht mehr auf der Seite, sondern hinter **einem** „i“ oben
(`seitenhilfe`) — auch die zu „Zählt als“.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import flet as ft

from trainingsapp.core import varianten as var
from trainingsapp.core import zaehlen as zl
from trainingsapp.core.beschreibung import abschnitte
from trainingsapp.core.models import (
    Exercise,
    MediaSource,
    Plan,
    PlanItem,
    new_id,
)
from trainingsapp.core.result_spec import basis_key, format_wert
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
    takt_der_uebung,
    timer_fuer,
    uhr_an,
    zaehlt_als,
)
from trainingsapp.ui.components.dialoge import Nachher, meldung
from trainingsapp.ui.components.hilfe import text_dialog
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.medienliste import medium_zeile
from trainingsapp.ui.components.paketvergleich import vergleich_blatt
from trainingsapp.ui.components.planstand import stand_zeile
from trainingsapp.ui.components.uebungsbild import uebungsbild
from trainingsapp.ui.components.varianten import etikett
from trainingsapp.ui.state import AppState
from trainingsapp.ui.views.anhang_verlauf import aufnahmen_raster
from trainingsapp.ui.views.timer import timer_knopf
from trainingsapp.ui.views.uebung_timer import uebung_timer_route

#: Kantenlänge des Übungsbilds im Kopf (Ben, 7.11.2026: „deutlich größer, dass man
#: Symbole/Grafiken usw. gut erkennen könnte“ — vorher 64)
KOPF_BILD = 128


def _beschreibung(uebung: Exercise, herkunft: str) -> ft.Control:
    """Die Beschreibung in ihren Abschnitten (Name fett, darunter der Inhalt — Ben,
    2.11.2026, P108), dahinter leise die Herkunft: „(Paket „Standard“)“."""
    teile = abschnitte(uebung.description)
    herkunft_span = ft.TextSpan(
        f"  ({herkunft})",
        style=ft.TextStyle(size=12, color=ft.Colors.with_opacity(0.55, ft.Colors.ON_SURFACE)),
    )
    if not teile:
        return ft.Text("—", spans=[herkunft_span])
    zeilen: list[ft.Control] = []
    for k, a in enumerate(teile):
        if a.name:
            zeilen.append(ft.Text(a.name, size=13, weight=ft.FontWeight.W_600, opacity=0.8))
        zeilen.append(ft.Text(a.text or "—", spans=[herkunft_span] if k == len(teile) - 1 else []))
    return ft.Column(spacing=2, tight=True, controls=zeilen)


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
    takt = takt_der_uebung(uebung, item)
    if takt is not None and not takt.leer:
        # Der Takt der Übung (`docs/plan_taktgeber.md`): Phasen und Rate — gilt überall, wo sie
        # geübt wird; in einer Planübung ihr eigener (A6), ein Timer-Abschnitt oder die Uhr
        # „für jetzt“ gehen vor
        zeilen.append(
            _uhr_zeile(
                ft.Icons.GRAPHIC_EQ,
                f"Takt: {takt.anzeigename}",
                takt.kurztext() + " · " + " · ".join(p.anzeigename for p in takt.phasen),
            )
        )
    zaehlt, _erklaerung = zaehlt_als_text(uebung, item)
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
                ],
            ),
        )
    )
    wahl = TimerWahl.aus_dict(item.timer) if item is not None else TimerWahl()
    if item is not None and (wahl.uhr is not None or wahl.profil_id or wahl.eigen):
        zeilen.append(ft.Text("In diesem Plan eingestellt (Einstellen).", size=12, opacity=0.6))
    return ft.Column(spacing=8, controls=zeilen)


def zaehlt_als_text(uebung: Exercise, item: PlanItem | None = None) -> tuple[str, str]:
    """Was die Uhr einträgt — („Zeit“, Erklärung). Die Erklärung steht im „i“ der Seite
    (`seitenhilfe`), nicht mehr unter dem Kasten (Ben, 7.11.2026)."""
    if not uhr_an(uebung, item):
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
        wohin = basis_key(zaehlt_als(felder, uebung))
        zaehlt = "Haltezeit je Satz" if wohin == "hold" else "Zeit"
        # Ein Lauf geht in den offenen Eintrag wie ein Tipp (P79 D1)
        erklaerung = (
            "„Fertig“ trägt in den offenen Eintrag ein: "
            + (
                "jeder Lauf der Stoppuhr und jeder zählende Abschnitt eines Timers ist ein Satz"
                if wohin == "hold"
                else "jeder Lauf ist eine eigene Zeit, auch ohne den Parameter Zeit"
            )
            + ". Pausen zählen nicht, unter 5 s fällt weg; „Abbrechen“ trägt nichts ein."
        )
    return zaehlt, erklaerung


def seitenhilfe(uebung: Exercise, item: PlanItem | None = None) -> str:
    """Das eine „i“ der Übungsseite (Ben, 7.11.2026: „In dieser View reicht ein ‚i‘ für die
    ganze Seite“) — was die Abschnitte bedeuten, samt der Erklärung zu „Zählt als“."""
    zaehlt, erklaerung = zaehlt_als_text(uebung, item)
    aendern = "Geändert wird über den Stift („Übung bearbeiten“, gilt überall)" + (
        " oder über „Im Plan einstellen“ (gilt nur in diesem Plan)." if item is not None else "."
    )
    teile = [
        f"**Diese Seite zeigt die Übung und ändert nichts.** {aendern}",
        "**Oben** stehen Typ und Regionen, darunter die Beschreibung — in Klammern, woher die "
        "Übung kommt (Paket oder eigene Übung).",
        "**Parameter**: was beim Üben eingetragen wird. Die Kästchen sind die Chips zum "
        "schnellen Tippen, „z. B.“ der Vorschlag im Feld.",
    ]
    if var.varianten(uebung.result_spec):
        teile.append(
            "**Varianten** werden jede für sich gezählt; ein langer Druck auf ein Schild zeigt "
            "die Beschreibung, angelegt werden sie unter „Übung bearbeiten“."
        )
    teile.append(f"**Zählt als: {zaehlt}.** {erklaerung}")
    if sensor_text(uebung, item) is not None:
        teile.append(
            "**Beschleunigungssensor** (Prototyp): Hat das verbundene Gerät einen, zählt er "
            "beim Üben mit — „Wdh. zählen“ startet, ±1 korrigiert."
        )
    teile += [
        "**In Plänen**: wo die Übung steht — „nur hier“ heißt, der Plan stellt etwas anders "
        "ein als die Übung; ein Tipp öffnet „Im Plan einstellen“. In einen Plan kommt sie über "
        "den Plan selbst (Bearbeiten → Hinzufügen).",
        "**Aufnahmen mit dieser Übung** (erscheint, sobald es welche gibt): HRV-Messungen, in "
        "denen Sätze dieser Übung liegen. Läuft beim Üben eine Aufnahme, bekommt jeder Satz "
        "dort eine Marke; ein Tipp öffnet die Messung.",
        "**Fotos und Videos**: eigene Aufnahmen aus den Einträgen dieser Übung — sie bleiben "
        "auf diesem Gerät.",
    ]
    return "\n\n".join(teile)


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


def sensor_text(uebung: Exercise, item: PlanItem | None = None) -> tuple[str, str] | None:
    """„Wiederholungen · Atmung“ und „Prototyp · Kniebeuge · zählt in …“ — ``None``, wenn
    beides aus ist. Mit ``item`` so, wie die Planübung es einstellt (A6)."""
    wdh, atem = zl.wiederholungen_an(uebung, item), zl.atmung_an(uebung, item)
    if not (wdh or atem):
        return None
    name = " · ".join(n for n, an in (("Wiederholungen", wdh), ("Atmung", atem)) if an)
    text = "Prototyp"
    wahl = zl.wirksame_wahl(uebung, item)
    if wdh and wahl.vorlage != zl.VORLAGE_AUTO:
        text += f" · {zl.vorlage_name(wahl.vorlage)}"
    if wdh and len(zl.wdh_felder(uebung, item)) > 1 and (feld := zl.zaehlt_in(uebung, item)):
        spec = plan_spec(item, uebung).field_by_key(feld) if item else None
        spec = spec or uebung.result_spec.field_by_key(feld)
        text += f" · zählt in {spec.label if spec is not None else feld}"
    return name, text


def beschleunigung_zeile(uebung: Exercise, item: PlanItem | None = None) -> ft.Control | None:
    """„Beschleunigungssensor: Wiederholungen · Atmung (Prototyp)“ (Ben, 4.11.2026,
    ``docs/plan_beschleunigung.md`` §3.4) — ``None``, wenn beides aus ist. Mit einer Vorlage
    der Bewegung ihr Name (A5), bei mehreren Wiederholungsfeldern dazu, in welches gezählt
    wird. Mit ``item`` so, wie die Planübung es einstellt (A6)."""
    paar = sensor_text(uebung, item)
    if paar is None:
        return None
    return _uhr_zeile(ft.Icons.SENSORS, *paar)


def aufnahmen_liste(page: Any, state: AppState, uebung: Exercise) -> ft.Control | None:
    """HRV-Aufnahmen, in denen Einträge dieser Übung liegen (Skizze D3, Plan C) — nur die
    Liste; Kurven und Kennzahlen stehen in der Aufnahme. Ein Tipp öffnet sie, gezoomt auf
    die Einträge. Die HRV bleibt aus dem Verlauf der Übung (Katalog P39). ``None`` ohne
    Aufnahmen — dann fehlt der Abschnitt (Ben, 7.11.2026), der Hinweis steht im „i“."""
    if state.bezuege is None:
        return None
    je_aufnahme = state.bezuege.zur_uebung(state.profil.id, uebung.id)
    if not je_aufnahme:
        return None
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
    """Die Varianten als Schilder nebeneinander (Ben, 7.11.2026: „als Tag-Labels
    nebeneinander“ — vorher je eine Zeile mit Beschreibung); die Beschreibung ist der Tipp
    des Schilds. Gezählt wird jede für sich; angelegt werden sie unter „Bearbeiten“."""
    return ft.Row(wrap=True, spacing=6, run_spacing=6, controls=[etikett(v) for v in liste])


def _anweisungen(page: Any, state: AppState, item: PlanItem, browser: Any) -> list[ft.Control]:
    """Die Anweisungen der Planübung (U2, F6: „Erklärungen beim i“) — Abschnitte, darunter Videos
    und Links; leer ohne."""
    zeilen: list[ft.Control] = []
    for a in abschnitte(item.description):
        if a.leer:
            continue
        if a.name:
            zeilen.append(ft.Text(a.name, size=13, weight=ft.FontWeight.W_600, opacity=0.8))
        if a.text:
            zeilen.append(ft.Text(a.text))
    zeilen.extend(medium_zeile(page, state, m, browser=browser) for m in item.media if m.uri)
    if zeilen:
        zeilen.insert(
            0,
            ft.Text("ANWEISUNGEN IN DIESEM PLAN", size=11, weight=ft.FontWeight.BOLD, opacity=0.6),
        )
    return zeilen


def _plan_karte(
    uebung: Exercise,
    plan: Plan,
    item: PlanItem,
    einstellen: Callable[[], object] | None,
    anweisungen: list[ft.Control] | None = None,
) -> ft.Control:
    """Oben auf der Übungsseite, wenn man aus einem Plan kommt: was dort gilt (P79, Skizze A2).

    Grau „wie die Übung“, sonst „nur hier“; „Im Plan einstellen“ öffnet die Seite dafür.
    ``anweisungen``: Abschnitte und Links der Planübung (U2), unter den Einstellungen.
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
    # Sensor-Karte und Takt der Planübung (A6) — nur, wenn etwas gilt oder nur hier abweicht
    sensor = sensor_text(uebung, item)
    if sensor is not None or "Beschleunigungssensor" in unterschiede:
        zeilen.append(
            stand_zeile(
                "Sensor", sensor[0] if sensor else "aus", "Beschleunigungssensor" in unterschiede
            )
        )
    takt = takt_der_uebung(uebung, item)
    if takt is not None or "Takt" in unterschiede:
        zeilen.append(
            stand_zeile(
                "Takt",
                f"{takt.anzeigename} · {takt.kurztext()}" if takt is not None else "keiner",
                "Takt" in unterschiede,
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
                *(anweisungen or []),
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


def _kopf(state: AppState, uebung: Exercise) -> ft.Control:
    """Bild groß links, rechts Name, Typ und darunter die Regionen ohne Überschrift (Ben,
    7.11.2026: „Bein/Hüfte würde unter Kräftigung gesetzt“)."""
    mit_bild = state.uebungsbilder.vorhanden(uebung.image_path)
    return ft.Row(
        spacing=16,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(
                width=KOPF_BILD,
                height=KOPF_BILD,
                border_radius=KOPF_BILD * 0.22,
                bgcolor=None if mit_bild else ft.Colors.SECONDARY_CONTAINER,
                alignment=ft.Alignment.CENTER,
                content=uebungsbild(
                    state,
                    uebung.icon_key,
                    uebung.image_path,
                    groesse=KOPF_BILD if mit_bild else KOPF_BILD * 0.55,
                ),
            ),
            ft.Column(
                spacing=2,
                expand=True,
                controls=[
                    ft.Text(uebung.name, size=22, weight=ft.FontWeight.BOLD),
                    ft.Text(", ".join(uebung.typen) or "ohne Typ", opacity=0.7),
                    *(
                        [ft.Text(", ".join(uebung.regionen), size=13, opacity=0.6)]
                        if uebung.regionen
                        else []
                    ),
                ],
            ),
        ],
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

    def gehe_zu(ziel: str) -> Callable[[], object]:
        async def handler() -> None:
            await page.push_route(ziel)

        return handler

    async def duplizieren() -> None:
        """Kopie — für „links/rechts“, 45° statt 90° und Ähnliches.

        Sie ist eine eigene Übung mit eigener Kachel im Verlauf — kein Paket-Update ändert
        sie. „Variante“ heißt seit 22.10.2026 nur noch das Etikett (P61); „Im Verlauf
        zusammen mit“ ist seit 26.10.2026 ausgebaut.
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
        )
        state.uebungen.speichern(kopie)
        page.show_dialog(ft.SnackBar(ft.Text("Kopie angelegt. Jetzt anpassen.")))
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

    # -- In Plänen (P79): jede Zeile öffnet „Im Plan einstellen“ dieses Plans --------------

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
    if not verwendungen:
        # Aufgenommen wird im Plan selbst (Ben, 7.11.2026: „gehört zu den Plänen“)
        verwendungen.append(ft.Text("In keinem Plan.", size=13, opacity=0.6))
    if uebung.default_target:
        vorgabe = uebung.result_spec.format_shorthand(uebung.default_target)
        verwendungen.append(ft.Text(f"Vorgabe für Pläne: Ziel {vorgabe}", size=12, opacity=0.7))

    # Links und Dateien aus dem Paket (U3) — das Bild der Bewegung (T6, lokal) nicht
    videos: list[ft.Control] = [
        medium_zeile(page, state, m, browser=browser)
        for m in uebung.media
        if m.uri and m.source != MediaSource.LOCAL
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
            _plan_karte(
                uebung,
                plan,
                item,
                gehe_zu(einstellen) if einstellen else None,
                _anweisungen(page, state, item, browser),
            )
        )
    abschnitte += [
        _kopf(state, uebung),
        _abschnitt("Beschreibung", _beschreibung(uebung, herkunft)),
        # Nur mit Inhalt (Ben, 7.11.2026: „spart Platz und verwirrt weniger“)
        *(
            [_abschnitt("Videos und Links", ft.Column(spacing=0, controls=videos))]
            if videos
            else []
        ),
        _abschnitt("Parameter", _notation(uebung)),
        *(
            [_abschnitt("Varianten", _varianten(liste))]
            if (liste := var.varianten(uebung.result_spec))
            else []
        ),
        _abschnitt("Uhr", uhr_und_timer(uebung, item)),
        *(
            [_abschnitt("Beschleunigungssensor", zeile)]
            if (zeile := beschleunigung_zeile(uebung, item)) is not None
            else []
        ),
        _abschnitt("In Plänen", ft.Column(spacing=0, controls=verwendungen)),
        *(
            [_abschnitt("Aufnahmen mit dieser Übung", liste_hrv)]
            if (liste_hrv := aufnahmen_liste(page, state, uebung)) is not None
            else []
        ),
        # Eigene Fotos und Videos (Ben, 19.10.2026; `views/anhang_verlauf.py`) — nur mit Aufnahmen
        *(
            [_abschnitt("Fotos und Videos", raster)]
            if (raster := aufnahmen_raster(page, state, uebung)) is not None
            else []
        ),
    ]
    if paket is not None and geaendert:
        neu_im_paket = state.pakete.hinweise(uebung.id)
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
                        *(
                            [
                                ft.Text(
                                    "Das Paket hat neue Fassungen — deine sind geblieben.",
                                    size=13,
                                    color=ft.Colors.PRIMARY,
                                )
                            ]
                            if neu_im_paket
                            else []
                        ),
                        # Je Feld und Abschnitt vergleichen und übernehmen, oder ganz zurück
                        # (U1, Ben 9.11.2026, `components/paketvergleich.py`)
                        ft.TextButton(
                            "Mit dem Paket vergleichen",
                            icon=ft.Icons.COMPARE_ARROWS,
                            on_click=lambda _e=None: page.show_dialog(
                                vergleich_blatt(page, state, uebung, danach=state.neu_zeichnen)
                            ),
                        ),
                    ],
                ),
            )
        )

    # Oben das i (die ganze Seite, 7.11.2026), Timer, Stift und ⋮ (P79, Skizze C1) — im
    # Papierkorb nur das i
    info = ft.IconButton(
        ft.Icons.INFO_OUTLINE,
        tooltip="Zu dieser Seite",
        on_click=lambda: page.show_dialog(
            text_dialog("Zu dieser Seite", seitenhilfe(uebung, item))
        ),
    )
    aktionen: list[ft.Control] = [info] + (
        []
        if geloescht
        else [
            timer_knopf(page, state, "uebung"),
            ft.IconButton(
                # Gefüllt, wenn hier ein Timer gilt — wie im Planblock (`timer_fuer`), K0
                ft.Icons.TIMER
                if timer_fuer(uebung, plan, item) is not None
                else ft.Icons.TIMER_OUTLINED,
                tooltip="Uhr dieser Übung",
                # Aus dem Plan der Timer der Planübung (Takt, Profil der Planübung), wie die
                # Uhr im Plan (`views/plan.py`) — über dieser Seite, Zurück führt hierher
                on_click=gehe_zu(uebung_timer_route(route or f"/uebung/{uebung.id}", uebung, item)),
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
