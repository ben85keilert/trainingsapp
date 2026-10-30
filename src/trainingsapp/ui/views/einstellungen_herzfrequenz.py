"""Einstellungen → Herzfrequenz — Route `/einstellungen/herzfrequenz` (Ben, 29.10.2026).

Der größere Einstellungsbereich für die HF, mit Shortlink aus der Messung
(hrv-research `KONZEPT_HF_APP.md` §5, Entscheidungen 10–13):

- **Profil:** Jahrgang und Geschlecht (w/m/d) des aktiven Profils — für die HFmax-Formel
  und die TRIMP-Gewichte; mehr nicht.
- **Ruhe-HF, HFmax, Schwellen:** der geltende Wert mit Quelle, Datum und Unsicherheit; der
  Verlauf der Einträge (festsetzen, lösen, entfernen); ein Formular für eigene Einträge.
  Die Formel steht als **Startwert** dabei („geschätzt ± 10,8“), nie als Messung.
- **Bereiche:** das Modell (automatisch, drei, fünf, zehn, eigene) mit Vorschau der Grenzen
  in bpm und ihrer Unsicherheit; eigene Grenzen in bpm oder % der Reserve, mit Namen.
- **Sicht:** welche Sicht die Hauptkarte öffnet (Herzfrequenz oder HRV) und ob die zuletzt
  gewählte gemerkt wird.
- **Nicht mitgerechnet:** die Tage, Einheiten und Messungen, die aus der Automatik fallen.

Keine Bewertung, keine Empfehlung (`docs/recht/00_zweckbestimmung.md`): Vorschlagswerte
heißen Vorschlag, Grenzen sind Werte der Person.
"""

from __future__ import annotations

import contextlib
from datetime import date, timedelta
from typing import Any

import flet as ft
from hrv_core import herzfrequenz as hz

from trainingsapp.core.hf_einstellungen import (
    EIGENE_MAX,
    FORMEL_NAMEN,
    FORMELN,
    MODELL_ERKLAERUNG,
    MODELL_NAMEN,
    MODELLE,
    EigeneGrenze,
)
from trainingsapp.core.hf_profil import (
    EINTRAG_QUELLEN,
    GESCHLECHTER,
    GROESSEN,
    QUELLEN,
    Profilwert,
    bereiche_fuer,
    wirksames_modell,
)
from trainingsapp.core.hrv_einstellungen import SICHT_HF, SICHT_HRV
from trainingsapp.data.hf_profil import RechenAusnahmeRepo
from trainingsapp.ui.components.hf_sicht import stufenfarbe
from trainingsapp.ui.components.karte import hinweis, info_knopf, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState

ROUTE = "/einstellungen/herzfrequenz"

HIERARCHIE_MD = """\
**Welcher Wert gilt?** Für jede Größe der **genaueste vorhandene** Eintrag; innerhalb einer
Quelle der jüngste, solange er nicht zu alt ist.

- Ruhe-HF: festgesetzt › Nacht (tiefstes 2-h-Mittel) › Morgenmessung 10 min › Morgenmessung
  5 min › eingetragen › Tagesminimum › Tagesfeld „Ruhepuls“ (Messungen 14 Tage, Eintrag 90).
- HFmax: festgesetzt › Spiroergometrie › Ergometrie › Feld-Maximaltest › Feldmaximum ›
  eingetragen › Formel (Startwert mit Streuung ± 11 bpm).
- Schwellen: Labor › Talk-Test › Schätzung aus Ruhe- und Spitzen-HF › 42 / 77 % der Reserve.

Eine Messung schlägt jede Schätzung. **Festsetzen** („selbst eingestellt“) pinnt einen
Eintrag über alle Quellen — bis du ihn löst. Ein Wechsel der Quelle wird angezeigt, weil
die Nacht-HF tiefer liegt als die Morgenmessung und alle Grenzen verschiebt.
"""


def _zahl_lesen(text: str | None) -> float | None:
    try:
        return float((text or "").strip().replace(",", "."))
    except ValueError:
        return None


def _datum_lesen(text: str | None, vorgabe: date) -> date | None:
    """„29.10.2026“ oder „2026-10-29“; leer = Vorgabe; unlesbar = None."""
    t = (text or "").strip()
    if not t:
        return vorgabe
    for form in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        with contextlib.suppress(ValueError):
            from datetime import datetime

            return datetime.strptime(t, form).date()
    return None


def wert_text(p: Profilwert | None, *, formel: hz.Formelwert | None = None) -> str:
    """„58 bpm · Morgenmessung 5 min · 28.10.2026 · ± 3“ — oder der Formel-Startwert."""
    if p is not None:
        fest = " · festgesetzt" if p.fest else ""
        return (
            f"{p.wert:.0f} {p.einheit} · {p.quelle_text} · {p.datum:%d.%m.%Y} · "
            f"± {p.unsicherheit_wirksam:.0f}{fest}"
        )
    if formel is not None and formel.gueltig and formel.wert is not None:
        return f"{formel.wert:.0f} bpm · geschätzt ({formel.name}) · ± {formel.see:.1f}"
    return "kein Wert"


def herkunft_text(p: Profilwert, state: AppState) -> str:
    """Die Herkunft eines Werts in Worten statt als Kennungen (Ben, 30.10.2026): „Messung
    29.10.2026 21:03 · Polar H10 · Fenster 02:14–04:14 · Abschnitt „Schlafen“ · Artefakte
    1,2 %“ — leer bei einem Eintrag von Hand ohne Notiz."""
    h = p.herkunft or {}
    teile: list[str] = []
    start = None
    if p.hrv_recording_id:
        rec = state.hrv.laden(p.hrv_recording_id)
        if rec is not None:
            start = rec.started_at.astimezone()
            teile.append(f"Messung {start:%d.%m.%Y %H:%M}")
        else:
            teile.append("Messung (nicht mehr vorhanden)")
    if p.geraet:
        teile.append(p.geraet)

    def uhr(t: Any) -> str | None:
        if start is None or isinstance(t, bool) or not isinstance(t, int | float):
            return None
        return (start + timedelta(seconds=float(t))).strftime("%H:%M")

    f = h.get("fenster")
    if isinstance(f, list | tuple) and len(f) == 2:
        a, b = uhr(f[0]), uhr(f[1])
        if a and b:
            teile.append(f"Fenster {a}–{b}")
    if h.get("grundlage") == "nachtfenster":
        teile.append("Nachtfenster 20–10 Uhr")
    if name := h.get("abschnitt_name"):
        teile.append(f"Abschnitt „{name}“")
    elif h.get("abschnitt"):
        teile.append("Abschnitt der Messung")
    if marke := uhr(h.get("t_wall_s")):
        teile.append(f"Marke um {marke}")
    ziel = h.get("ziel")
    if isinstance(ziel, int | float) and not isinstance(ziel, bool):
        a1 = f"α1 = {float(ziel):g}".replace(".", ",")
        if h.get("n"):
            a1 += f" · {int(h['n'])} Fenster"
        if isinstance(h.get("r2"), int | float):
            a1 += f" · r² {float(h['r2']):.2f}".replace(".", ",")
        teile.append(a1)
    art = h.get("artefaktanteil")
    if isinstance(art, int | float) and not isinstance(art, bool):
        teile.append(f"Artefakte {100 * art:.1f} %".replace(".", ","))
    if h.get("tagesfeld"):
        teile.append(f"aus dem Tagesfeld „Ruhepuls“ vom {p.datum:%d.%m.%Y}")
    if p.note:
        teile.append(p.note)
    return " · ".join(teile)


def einstellungen_herzfrequenz(page: Any, state: AppState) -> ft.View:
    inhalt = ft.Column(spacing=14)

    def neu_zeichnen() -> None:
        inhalt.controls = teile()
        with contextlib.suppress(Exception):
            inhalt.update()

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    # -- Profil: Jahrgang, Geschlecht -------------------------------------------------

    def profil_karte() -> ft.Control:
        p = state.profil
        jahrgang = ft.TextField(
            label="Jahrgang",
            value=str(p.birth_year) if p.birth_year else "",
            dense=True,
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        def jahrgang_sichern(_e: object = None) -> None:
            text = (jahrgang.value or "").strip()
            if not text:
                p.birth_year = None
            else:
                try:
                    jahr = int(text)
                except ValueError:
                    jahrgang.error = "Eine Jahreszahl."
                    with contextlib.suppress(Exception):
                        jahrgang.update()
                    return
                if not 1900 <= jahr <= state.heute().year:
                    jahrgang.error = "Eine Jahreszahl."
                    with contextlib.suppress(Exception):
                        jahrgang.update()
                    return
                p.birth_year = jahr
            jahrgang.error = None
            state.profil_speichern(p)
            neu_zeichnen()

        jahrgang.on_submit = jahrgang_sichern
        jahrgang.on_blur = jahrgang_sichern

        def geschlecht_gewaehlt(e: ft.Event[ft.SegmentedButton]) -> None:
            wahl = str(e.control.selected[0]) if e.control.selected else ""
            p.geschlecht = wahl if wahl in GESCHLECHTER else None
            state.profil_speichern(p)
            neu_zeichnen()

        geschlecht = ft.SegmentedButton(
            selected=[p.geschlecht or "-"],
            show_selected_icon=False,
            on_change=geschlecht_gewaehlt,
            segments=[
                *[ft.Segment(value=k, label=ft.Text(v)) for k, v in GESCHLECHTER.items()],
                ft.Segment(value="-", label=ft.Text("keine Angabe")),
            ],
        )
        hf = state.hf_profil()
        formel_zeile = (
            f"HFmax-Formel: {hf.formel.name} → {hf.formel.wert:.0f} bpm (± {hf.formel.see:.1f})"
            if hf.formel is not None and hf.formel.gueltig
            else "Ohne Jahrgang gibt es keinen Formel-Startwert für die HFmax."
        )
        return karte(
            titel(f"Profil „{p.name}“"),
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[jahrgang, ft.Text(f"Alter {hf.alter}" if hf.alter else "", size=12)],
            ),
            geschlecht,
            hinweis(
                "Nur für die HFmax-Formel (Frauen: Gulati) und die TRIMP-Gewichte; „divers“ und "
                "„keine Angabe“ rechnen mit den Männer-Koeffizienten. " + formel_zeile
            ),
        )

    # -- Eine Größe: geltender Wert, Verlauf, Formular ----------------------------------

    def groesse_karte(groesse: str) -> ft.Control:
        hf = state.hf_profil()
        geltend = {
            hz.GROESSE_RUHE: hf.ruhe,
            hz.GROESSE_MAX: hf.hfmax,
            hz.GROESSE_VT1: hf.vt1,
            hz.GROESSE_VT2: hf.vt2,
        }[groesse]
        formel = hf.formel if groesse == hz.GROESSE_MAX else None
        # Auch die Werte des Tagesfelds „Ruhepuls“ stehen hier — sie zählen mit und lassen
        # sich hier entfernen (Ben, 30.10.2026: „Einträge Ruhe-HF lassen sich nicht löschen“:
        # der geltende Wert kam aus dem Tagesfeld und stand in keiner Liste)
        alle = sorted(
            (e for e in state.hf_eintraege() if e.groesse == groesse),
            key=lambda e: (e.datum, e.created_at),
        )
        verlauf: list[ft.Control] = []
        for p in reversed(alle[-6:]):
            gilt = geltend is not None and p.id == geltend.id
            aus_tagesfeld = p.quelle == "tagesfeld"
            knoepfe: list[ft.Control] = [
                ft.IconButton(
                    ft.Icons.PUSH_PIN if p.fest else ft.Icons.PUSH_PIN_OUTLINED,
                    icon_size=18,
                    tooltip="Festsetzung lösen" if p.fest else "Festsetzen (gilt über alles)",
                    visible=not aus_tagesfeld,
                    on_click=lambda _=None, wid=p.id, f=p.fest: festsetzen(wid, not f),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_size=18,
                    tooltip="Tageswert entfernen" if aus_tagesfeld else "Eintrag entfernen",
                    on_click=lambda _=None, wid=p.id: entfernen(wid),
                ),
            ]
            if p.hrv_recording_id and state.hrv.laden(p.hrv_recording_id) is not None:
                knoepfe.insert(
                    0,
                    ft.IconButton(
                        ft.Icons.OPEN_IN_NEW,
                        icon_size=18,
                        tooltip="Messung öffnen",
                        on_click=lambda _=None, rid=p.hrv_recording_id: page.run_task(
                            messung_oeffnen, rid
                        ),
                    ),
                )
            zeile: ft.Control = ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE if gilt else ft.Icons.CIRCLE_OUTLINED,
                        size=16,
                        opacity=1 if gilt else 0.4,
                        tooltip="gilt" if gilt else None,
                    ),
                    ft.Text(wert_text(p), size=12, expand=True),
                    *knoepfe,
                ],
            )
            # Die Herkunft leserlich direkt darunter (Ben, 30.10.2026) — Tag, Uhrzeit,
            # Fenster, Abschnitt — statt einer Kennung
            herkunft = herkunft_text(p, state)
            if herkunft:
                zeile = ft.Column(
                    spacing=0,
                    tight=True,
                    controls=[
                        zeile,
                        ft.Container(
                            padding=ft.Padding.only(left=22, bottom=4),
                            content=ft.Text(herkunft, size=11, opacity=0.7),
                        ),
                    ],
                )
            verlauf.append(zeile)
        quellen = EINTRAG_QUELLEN[groesse]
        wert = ft.TextField(
            label="Wert (bpm)", dense=True, width=120, keyboard_type=ft.KeyboardType.NUMBER
        )
        datum = ft.TextField(
            label="Datum", dense=True, width=130, value=f"{state.heute():%d.%m.%Y}"
        )
        quelle = ft.Dropdown(
            label="Herkunft",
            value=quellen[0],
            dense=True,
            expand=True,
            options=[ft.DropdownOption(key=q, text=QUELLEN[q]) for q in quellen],
        )
        notiz = ft.TextField(label="Notiz", dense=True, expand=True)

        def eintragen(_e: object = None) -> None:
            w = _zahl_lesen(wert.value)
            if w is None or not 20 <= w <= 250:
                wert.error = "20–250"
                with contextlib.suppress(Exception):
                    wert.update()
                return
            tag = _datum_lesen(datum.value, state.heute())
            if tag is None:
                datum.error = "TT.MM.JJJJ"
                with contextlib.suppress(Exception):
                    datum.update()
                return
            q = str(quelle.value or quellen[0])
            state.profilwerte.hinzufuegen(
                Profilwert(
                    state.profil.id,
                    groesse,
                    w,
                    q if q in quellen else quellen[0],
                    tag,
                    note=(notiz.value or "").strip(),
                )
            )
            melden(f"{GROESSEN[groesse]} {w:.0f} bpm eingetragen.")
            neu_zeichnen()

        zusatz: list[ft.Control] = []
        if groesse == hz.GROESSE_MAX and hf.hfmax is None:
            zusatz.append(
                hinweis(
                    "Solange keine Messung oder kein Eintrag vorliegt, rechnet die App mit dem "
                    "Formelwert — als Startwert, mit seiner Streuung. Ein Feldmaximum aus deinen "
                    "Aufzeichnungen wird in der Auswertung vorgeschlagen, nie von selbst gesetzt."
                )
            )
        if (
            groesse in (hz.GROESSE_VT1, hz.GROESSE_VT2)
            and hf.vollstaendig
            and not hf.hfmax_geschaetzt
        ):
            s = hz.schwellen_milani(float(hf.hfmax_bpm), float(hf.ruhe_bpm))  # type: ignore[arg-type]
            v = s.vt1 if groesse == hz.GROESSE_VT1 else s.vt2
            u = s.unsicherheit_vt1 if groesse == hz.GROESSE_VT1 else s.unsicherheit_vt2
            zusatz.append(
                hinweis(
                    f"Schätzung aus Ruhe- und Spitzen-HF (Milani, ESC-Reha 2026): "
                    f"{v:.0f} bpm ± {u:.0f}. Herkunft: Fahrradergometrie bei Patienten; für "
                    "Gesunde eine Extrapolation."
                )
            )
        return karte(
            titel(GROESSEN[groesse]),
            ft.Text(wert_text(geltend, formel=formel), size=14, weight=ft.FontWeight.W_600),
            *verlauf,
            *zusatz,
            ft.Row(spacing=8, controls=[wert, datum, quelle]),
            ft.Row(
                spacing=8,
                controls=[
                    notiz,
                    ft.FilledTonalButton("Eintragen", icon=ft.Icons.ADD, on_click=eintragen),
                ],
            ),
        )

    async def messung_oeffnen(recording_id: str) -> None:
        await page.push_route(f"/messung/{recording_id}")

    def festsetzen(wert_id: str, fest: bool) -> None:
        state.profilwerte.festsetzen(wert_id, fest)
        melden("Festgesetzt — gilt über alle Quellen." if fest else "Festsetzung gelöst.")
        neu_zeichnen()

    def entfernen(wert_id: str) -> None:
        if wert_id.startswith("tagesfeld:"):
            state.tageswerte.loeschen(wert_id.removeprefix("tagesfeld:"))
            melden("Tageswert „Ruhepuls“ entfernt.")
        else:
            state.profilwerte.loeschen(wert_id)
            melden("Eintrag entfernt.")
        neu_zeichnen()

    # -- Bereiche -------------------------------------------------------------------

    def bereiche_karte() -> ft.Control:
        e = state.hf_einstellungen()
        hf = state.hf_profil()

        def modell_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
            wahl = str(ev.control.value or "")
            if wahl in MODELLE:
                e.modell = wahl
                state.hf_einstellungen_setzen(e)
                neu_zeichnen()

        def formel_gewaehlt(ev: ft.Event[ft.Dropdown]) -> None:
            wahl = str(ev.control.value or "")
            if wahl in FORMELN:
                e.formel = wahl
                state.hf_einstellungen_setzen(e)
                neu_zeichnen()

        modell = ft.Dropdown(
            label="Bereichsmodell",
            value=e.modell,
            options=[ft.DropdownOption(key=m, text=MODELL_NAMEN[m]) for m in MODELLE],
            on_select=modell_gewaehlt,
            dense=True,
            expand=True,
        )
        formel = ft.Dropdown(
            label="HFmax-Formel (Startwert)",
            value=e.formel,
            options=[ft.DropdownOption(key=f, text=FORMEL_NAMEN[f]) for f in FORMELN],
            on_select=formel_gewaehlt,
            dense=True,
            expand=True,
        )
        wirksam = wirksames_modell(hf, e)
        bereiche = bereiche_fuer(hf, e)
        vorschau: list[ft.Control] = []
        n = len(bereiche)
        for i, b in enumerate(bereiche):
            band = f" (± {b.unsicherheit_bpm:.0f})" if b.unsicherheit_bpm > 0 else ""
            vorschau.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Container(
                            width=12, height=12, bgcolor=stufenfarbe(i, n), border_radius=2
                        ),
                        ft.Text(b.name, size=13, expand=True),
                        ft.Text(f"{b.von_bpm:.0f}–{b.bis_bpm:.0f} bpm{band}", size=13),
                        ft.Text(
                            f"{b.von_prozent:.0f}–{b.bis_prozent:.0f} %",
                            size=12,
                            opacity=0.6,
                            width=70,
                        ),
                    ],
                )
            )
        if not bereiche:
            vorschau.append(
                hinweis(
                    "Ohne Ruhe-HF und HFmax gibt es keine Bereiche."
                    if not hf.vollstaendig
                    else "Eigene Bereiche: unten Grenzen anlegen."
                )
            )
        eigene: list[ft.Control] = []
        if e.modell == hz.MODELL_EIGEN:
            eigene = eigene_bearbeiten(e)
        return karte(
            titel("Bereiche", info_knopf(page, "Welcher Wert gilt?", HIERARCHIE_MD)),
            modell,
            hinweis(
                MODELL_ERKLAERUNG[e.modell]
                + (f" Gerade wirksam: {MODELL_NAMEN[wirksam]}." if e.modell == "auto" else "")
            ),
            *vorschau,
            *eigene,
            formel,
            hinweis(
                "Die Bereiche sind deine Werte wie ein Timer. Die App zeigt, wo du bist und "
                "warst — sie bewertet nichts und empfiehlt nichts."
            ),
        )

    def eigene_bearbeiten(e) -> list[ft.Control]:
        zeilen: list[ft.Control] = [ft.Text("Eigene Grenzen", size=12, opacity=0.8)]
        for i, g in enumerate(e.eigene):
            text = f"{g.bpm:.0f} bpm" if g.bpm is not None else f"{g.prozent:.0f} % der Reserve"
            zeilen.append(
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(f"Grenze {i + 1}: {text}", size=13, expand=True),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            icon_size=18,
                            tooltip="Grenze entfernen",
                            on_click=lambda _=None, k=i: grenze_entfernen(k),
                        ),
                    ],
                )
            )
        wert = ft.TextField(
            label="Grenze", dense=True, width=110, keyboard_type=ft.KeyboardType.NUMBER
        )
        einheit = ft.SegmentedButton(
            selected=["bpm"],
            show_selected_icon=False,
            segments=[
                ft.Segment(value="bpm", label=ft.Text("bpm")),
                ft.Segment(value="prozent", label=ft.Text("% Reserve")),
            ],
        )

        def grenze_anlegen(_e: object = None) -> None:
            w = _zahl_lesen(wert.value)
            art = str(einheit.selected[0]) if einheit.selected else "bpm"
            if (
                w is None
                or (art == "bpm" and not 30 <= w <= 230)
                or (art != "bpm" and not 1 <= w <= 99)
            ):
                wert.error = "bpm 30–230, % 1–99"
                with contextlib.suppress(Exception):
                    wert.update()
                return
            if len(e.eigene) >= EIGENE_MAX:
                melden(f"Höchstens {EIGENE_MAX} Grenzen.")
                return
            e.eigene.append(EigeneGrenze(bpm=w) if art == "bpm" else EigeneGrenze(prozent=w))
            e.eigene.sort(key=lambda g: (g.bpm is None, g.bpm or 0, g.prozent or 0))
            state.hf_einstellungen_setzen(e)
            neu_zeichnen()

        namen = ft.TextField(
            label="Namen der Bereiche (mit Komma)",
            value=", ".join(e.namen),
            dense=True,
            expand=True,
        )

        def namen_sichern(_e: object = None) -> None:
            e.namen = [n.strip()[:40] for n in (namen.value or "").split(",") if n.strip()]
            state.hf_einstellungen_setzen(e)
            neu_zeichnen()

        namen.on_submit = namen_sichern
        namen.on_blur = namen_sichern
        zeilen.append(
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    wert,
                    einheit,
                    ft.FilledTonalButton("Hinzufügen", icon=ft.Icons.ADD, on_click=grenze_anlegen),
                ],
            )
        )
        zeilen.append(namen)
        zeilen.append(
            hinweis(
                f"Eine Grenze mehr braucht einen Namen mehr ({len(e.eigene) + 1} Bereiche); "
                "ohne Namen heißen sie „Bereich 1…n“."
            )
        )
        return zeilen

    def grenze_entfernen(k: int) -> None:
        e = state.hf_einstellungen()
        if 0 <= k < len(e.eigene):
            del e.eigene[k]
            state.hf_einstellungen_setzen(e)
            neu_zeichnen()

    # -- Sicht ----------------------------------------------------------------------

    def sicht_karte() -> ft.Control:
        e = state.hrv_einstellungen()

        def sicht_gewaehlt(ev: ft.Event[ft.SegmentedButton]) -> None:
            if ev.control.selected:
                e.standard_sicht = str(ev.control.selected[0])
                state.hrv_einstellungen_setzen(e)

        def merken_gewechselt(ev: ft.Event[ft.Switch]) -> None:
            e.sicht_merken = bool(ev.control.value)
            state.hrv_einstellungen_setzen(e)

        return karte(
            titel("Sicht der Messung"),
            ft.SegmentedButton(
                selected=[e.standard_sicht],
                show_selected_icon=False,
                on_change=sicht_gewaehlt,
                segments=[
                    ft.Segment(value=SICHT_HF, label=ft.Text("Herzfrequenz")),
                    ft.Segment(value=SICHT_HRV, label=ft.Text("HRV")),
                ],
            ),
            ft.Switch(
                label="Zuletzt gewählte Sicht merken",
                value=e.sicht_merken,
                on_change=merken_gewechselt,
            ),
            hinweis(
                "Die Hauptkarte der Messung hat zwei Sichten auf dieselbe Aufnahme. Reine "
                "Pulsgeber öffnen immer die Herzfrequenz."
            ),
        )

    # -- Ausnahmen -------------------------------------------------------------------

    def ausnahmen_karte() -> ft.Control:
        alle = state.ausnahmen.alle(state.profil.id)
        namen = {
            RechenAusnahmeRepo.TAG: "Tag",
            RechenAusnahmeRepo.EINHEIT: "Einheit",
            RechenAusnahmeRepo.MESSUNG: "Messung",
            RechenAusnahmeRepo.STRECKE: "Strecke",
        }
        zeilen: list[ft.Control] = []
        for ziel, ids in alle.items():
            for zid in sorted(ids):
                zeilen.append(
                    ft.Row(
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(f"{namen.get(ziel, ziel)} {zid}", size=13, expand=True),
                            ft.TextButton(
                                "Wieder mitrechnen",
                                on_click=lambda _=None, z=ziel, i=zid: ausnahme_loesen(z, i),
                            ),
                        ],
                    )
                )
        if not zeilen:
            zeilen.append(hinweis("Nichts ausgenommen."))
        return karte(
            titel("Nicht mitgerechnet"),
            *zeilen,
            hinweis(
                "Ein Tag oder eine Einheit, die du lange drückst und „nicht mitrechnen“ "
                "markierst, geht in keinen Mittelwert, keine Baseline und kein Feldmaximum ein."
            ),
        )

    def ausnahme_loesen(ziel: str, zid: str) -> None:
        state.ausnahmen.loesen(state.profil.id, ziel, zid)
        neu_zeichnen()

    async def zum_verlauf() -> None:
        await page.push_route("/verlauf/herzfrequenz")

    def verlauf_karte() -> ft.Control:
        return karte(
            titel("Verlauf"),
            ft.ListTile(
                dense=True,
                content_padding=ft.Padding.only(left=0, right=0),
                leading=ft.Icon(ft.Icons.SHOW_CHART),
                title=ft.Text("Herzfrequenz im Verlauf"),
                subtitle=ft.Text("Ruhe-/Nacht-HF mit Baseline, Wochenlast, Tests", size=12),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                on_click=lambda _=None: page.run_task(zum_verlauf),
            ),
        )

    def teile() -> list[ft.Control]:
        return [
            profil_karte(),
            verlauf_karte(),
            groesse_karte(hz.GROESSE_RUHE),
            groesse_karte(hz.GROESSE_MAX),
            groesse_karte(hz.GROESSE_VT1),
            groesse_karte(hz.GROESSE_VT2),
            bereiche_karte(),
            sicht_karte(),
            ausnahmen_karte(),
        ]

    inhalt.controls = teile()
    return ft.View(
        route=ROUTE,
        appbar=ft.AppBar(title=ft.Text("Herzfrequenz")),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[sicher(inhalt, expand=False)],
    )


__all__ = ["ROUTE", "einstellungen_herzfrequenz", "wert_text"]
