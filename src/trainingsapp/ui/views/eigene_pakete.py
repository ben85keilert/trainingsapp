"""Eigene Pakete in der App bauen (U4, Ben 9.11.2026, `docs/plan_paketinhalte.md` §7, F5).

„Es ist leichter für mich, wenn ich ein Paket erstelle, darin Videos reinlade, dieses Paket
exportiere und dann jemandem mitgebe.“ Im Paketmanager die Karte **Eigene Pakete**; ein Paket
(``<basis>/eigen/<id>``, ``…/eigen/neu``) hat Kopf (Name, Beschreibung, Neuigkeiten) und Inhalt —
Übungen, Pläne, Kurse; was ein Plan oder Kurs braucht, kommt von selbst mit. **Dateien** (Videos,
Bilder, PDFs) hängen an den Übungen und Planübungen („Datei fürs Paket“ in „Übung bearbeiten“
und „Im Plan einstellen“). **Exportieren und teilen** schlägt die Version vor (erste 1.0.0,
danach klein · mittel · groß; unverändert = dieselbe), schreibt JSON oder ZIP und gibt sie weiter.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.core.eigenes_paket import (
    GROSS,
    KLEIN,
    MITTEL,
    STUFEN,
    EigenesPaket,
    naechste_version,
    noetige_uebungen,
)
from trainingsapp.core.models import Exercise
from trainingsapp.core.paketdatei import export_schreiben
from trainingsapp.core.pakete import name_pruefen, paketmedien_in
from trainingsapp.core.paketmedien import groesse_text
from trainingsapp.core.paketversion import version_text
from trainingsapp.core.privat import code_neu, code_text, datei_verschluesseln
from trainingsapp.ui.components.dialoge import Nachher, schliessen
from trainingsapp.ui.components.formular import formular_leiste
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.weitergeben import datei_weitergeben
from trainingsapp.ui.components.zurueck import zurueck_speichert, zurueck_ziel
from trainingsapp.ui.state import AppState

#: Das Segment unter dem Paketmanager
SEGMENT = "eigen"
NEU = "neu"


def eigene_pakete_karte(
    state: AppState, basis: str, oeffner: Callable[[str], Callable[[], object]]
) -> ft.Control:
    """Die Karte im Paketmanager: die eigenen Pakete und „Neues eigenes Paket“."""
    zeilen: list[ft.Control] = [titel("Eigene Pakete")]
    for ep in state.eigene_pakete.alle():
        stand = (
            f"Version {version_text(ep.version)}"
            if ep.version is not None
            else "noch nicht geteilt"
        )
        teile = [stand, f"{len(ep.uebungen)} Übungen"]
        if ep.plaene:
            teile.append("1 Plan" if len(ep.plaene) == 1 else f"{len(ep.plaene)} Pläne")
        if ep.kurse:
            teile.append("1 Kurs" if len(ep.kurse) == 1 else f"{len(ep.kurse)} Kurse")
        zeilen.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED),
                title=ft.Text(ep.name or "Ohne Namen"),
                subtitle=ft.Text("  ·  ".join(teile), size=12),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, opacity=0.5),
                on_click=oeffner(f"{basis}/{SEGMENT}/{ep.id}"),
                content_padding=ft.Padding.only(left=0, right=0),
                data=("eigenes_paket", ep.id),
            )
        )
    if len(zeilen) == 1:
        zeilen.append(
            hinweis(
                "Ein eigenes Paket bündelt Übungen, Pläne und Kurse — mit Videos, Bildern und "
                "PDFs — zum Weitergeben. Jede neue Fassung ist ein Update bei allen, die es haben."
            )
        )
    zeilen.append(
        ft.Row(
            controls=[
                ft.TextButton(
                    "Neues eigenes Paket",
                    icon=ft.Icons.ADD,
                    on_click=oeffner(f"{basis}/{SEGMENT}/{NEU}"),
                    data="eigenes_paket_neu",
                )
            ]
        )
    )
    return karte(*zeilen)


def _verschluesseln(datei: Path, code: str) -> None:
    """Die Exportdatei verschlüsselt an ihrem Platz (im Hintergrund)."""
    teil = datei.with_name(datei.name + ".teil")
    datei_verschluesseln(datei, teil, code)
    teil.replace(datei)


def code_gezeigt(name: str, code: str, text: str) -> ft.AlertDialog:
    """Nach dem Teilen eines privaten Pakets: der Code — getrennt weitergeben."""
    dialog: ft.AlertDialog = ft.AlertDialog(
        title=ft.Text(f"„{name}“ ist privat"),
        content=ft.Column(
            tight=True,
            spacing=10,
            controls=[
                ft.Text(text, size=13),
                ft.Text("Code", size=12, opacity=0.7),
                ft.Text(
                    code_text(code),
                    size=26,
                    weight=ft.FontWeight.W_600,
                    font_family="monospace",
                    selectable=True,
                ),
                hinweis(
                    "Den Code getrennt vom Paket weitergeben (mündlich, eigene Nachricht). Wer "
                    "die Datei ohne Code hat, sieht nur Zeichensalat."
                ),
            ],
        ),
        actions=[ft.TextButton("OK", on_click=lambda _e=None: schliessen(dialog))],
    )
    return dialog


def eigenes_paket_view(page: Any, state: AppState, basis: str, paket_id: str) -> ft.View:
    """Ein eigenes Paket bearbeiten, exportieren und teilen."""
    repo = state.eigene_pakete
    vorhanden = repo.laden(paket_id) if paket_id != NEU else None
    ep = vorhanden if vorhanden is not None else EigenesPaket()
    route = f"{basis}/{SEGMENT}/{paket_id}"

    name = ft.TextField(
        label="Name des Pakets",
        value=ep.name,
        hint_text="z. B. Knie-Reha für Anna",
        capitalization=ft.TextCapitalization.SENTENCES,
        autofocus=vorhanden is None,
    )
    beschreibung = ft.TextField(
        label="Beschreibung (optional)",
        value=ep.beschreibung,
        multiline=True,
        min_lines=1,
        max_lines=4,
        capitalization=ft.TextCapitalization.SENTENCES,
    )
    neuigkeiten = ft.TextField(
        label="Was ist neu? (für die nächste Fassung)",
        value=ep.neuigkeiten,
        multiline=True,
        min_lines=1,
        max_lines=4,
        capitalization=ft.TextCapitalization.SENTENCES,
    )
    # Privat weitergeben (U7): verschlüsselt, der Code bleibt für jede Fassung
    zugang = {"code": ep.code}
    privat_text = ft.Text(size=12, opacity=0.75)

    def privat_text_neu() -> None:
        privat_text.value = (
            f"Code: {code_text(zugang['code'])} — getrennt vom Paket weitergeben; er bleibt für "
            "jede Fassung."
            if zugang["code"]
            else "Offen: Wer die Datei hat, kann sie öffnen."
        )

    def privat_umschalten(e: Any) -> None:
        zugang["code"] = (zugang["code"] or code_neu()) if e.control.value else None
        privat_text_neu()
        with contextlib.suppress(Exception):
            privat_text.update()

    privat_schalter = ft.Switch(
        label="Privat — nur mit Code zu öffnen",
        value=zugang["code"] is not None,
        on_change=privat_umschalten,
        data="privat",
    )
    privat_text_neu()
    gewaehlt: dict[str, set[str]] = {
        "uebungen": set(ep.uebungen),
        "plaene": set(ep.plaene),
        "kurse": set(ep.kurse),
    }
    uebungen = state.uebungen.alle()
    plaene = [p for p in state.plaene.alle(state.profil.id) if p.items and not p.kurs_kapitel_id]
    kurse = state.kurse.alle()
    info = ft.Text(size=12, opacity=0.75)

    def stand() -> EigenesPaket:
        ep.name = " ".join((name.value or "").split())
        ep.beschreibung = (beschreibung.value or "").strip()
        ep.neuigkeiten = (neuigkeiten.value or "").strip()
        ep.uebungen = [u.id for u in uebungen if u.id in gewaehlt["uebungen"]]
        ep.plaene = [p.id for p in plaene if p.id in gewaehlt["plaene"]]
        ep.kurse = [k.id for k in kurse if k.id in gewaehlt["kurse"]]
        ep.code = zugang["code"]
        return ep

    anfang = (ep.name, ep.beschreibung, ep.neuigkeiten, *(sorted(v) for v in gewaehlt.values()))
    code_anfang = ep.code

    def geaendert() -> bool:
        s = stand()
        if s.code != code_anfang:
            return True
        return (s.name, s.beschreibung, s.neuigkeiten, s.uebungen, s.plaene, s.kurse) != (
            anfang[0],
            anfang[1],
            anfang[2],
            [u.id for u in uebungen if u.id in anfang[3]],
            [p.id for p in plaene if p.id in anfang[4]],
            [k.id for k in kurse if k.id in anfang[5]],
        )

    def info_neu() -> None:
        s = stand()
        a = repo.inhalt(s)
        noetig = (
            set(
                noetige_uebungen(
                    [p for p in plaene if p.id in gewaehlt["plaene"]],
                    [k for k in kurse if k.id in gewaehlt["kurse"]],
                )
            )
            - gewaehlt["uebungen"]
        )
        namen = paketmedien_in(a.uebungen, a.kurse, a.plaene, a.ergaenzungen)
        ablage = state.pakete.ablage
        groesse = sum(ablage.groesse(n) for n in namen) if ablage is not None else 0
        teile = [
            f"{len(a.uebungen)} Übungen"
            + (f" (davon {len(noetig)} für Pläne/Kurse)" if noetig else "")
        ]
        if a.ergaenzungen:  # geänderte Übungen anderer Pakete (U5)
            n = len(a.ergaenzungen)
            teile.append("1 Ergänzung" if n == 1 else f"{n} Ergänzungen")
        if namen:
            teile.append(f"{len(namen)} Dateien · {groesse_text(groesse)}")
        info.value = "  ·  ".join(teile)
        with contextlib.suppress(Exception):
            info.update()

    def umschalter(art: str, eid: str) -> Callable[[Any], None]:
        def handler(e: Any) -> None:
            if getattr(e, "control", None) is not None and e.control.value:
                gewaehlt[art].add(eid)
            else:
                gewaehlt[art].discard(eid)
            info_neu()

        return handler

    def haken(art: str, eid: str, text: str) -> ft.Control:
        return ft.Checkbox(
            label=text,
            value=eid in gewaehlt[art],
            on_change=umschalter(art, eid),
            data=(art, eid),
        )

    # Übungen: eigene zuerst, dann je Paket
    gruppen: list[tuple[str, list[Exercise]]] = []
    eigene = [u for u in uebungen if u.package_id is None]
    if eigene:
        gruppen.append(("Eigene Übungen", eigene))
    for paket, _ in state.pakete.alle():
        if paket.id == ep.id:
            continue
        mitglieder = [u for u in uebungen if u.package_id == paket.id]
        if mitglieder:
            gruppen.append((f"Aus „{paket.name}“", mitglieder))

    def uebungsgruppe(text: str, mitglieder: list[Exercise]) -> ft.Control:
        return ft.ExpansionTile(
            title=ft.Text(text),
            subtitle=ft.Text(f"{len(mitglieder)} Übungen", size=12),
            expanded=text == "Eigene Übungen"
            or any(u.id in gewaehlt["uebungen"] for u in mitglieder),
            controls=[haken("uebungen", u.id, u.name) for u in mitglieder],
        )

    # -- Export -------------------------------------------------------------------------

    def melden(text: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(text)))

    def speichern_ohne_weg() -> str | None:
        s = stand()
        if (fehler := name_pruefen(s.name)) is not None:
            name.error = fehler
            with contextlib.suppress(Exception):
                page.update()
            return fehler
        name.error = None
        repo.speichern(s)
        return None

    async def teilen(version: int) -> None:
        from trainingsapp.ui.views.pakete import export_ordner

        ablage = state.pakete.ablage
        # Die Datenbank im Event-Loop (die Verbindung gehört ihm), nur die Dateien im Thread
        a = repo.inhalt(ep, version)
        sha = repo.sha(ep)
        try:
            datei, meldungen = await asyncio.to_thread(
                export_schreiben,
                export_ordner(),
                a.paket,
                a.uebungen,
                plaene=a.plaene,
                kurse=a.kurse,
                ergaenzungen=a.ergaenzungen,
                quelle=ablage.pfad if ablage is not None else (lambda _n: None),
            )
        except (OSError, ValueError) as fehler:
            melden(f"Export fehlgeschlagen: {fehler}")
            return
        if ep.code:  # privat (U7): verschlüsselt mit dem Code des Pakets
            await asyncio.to_thread(_verschluesseln, datei, ep.code)
        mime = "application/zip" if datei.suffix == ".zip" else "application/json"
        await datei_weitergeben(page, datei, datei.name, mime)
        repo.exportiert(ep.id, version, sha)
        ep.version, ep.exportiert_sha = version, sha
        text = " ".join([f"„{ep.name}“ Version {version_text(version)} weitergegeben.", *meldungen])
        if ep.code:
            page.show_dialog(code_gezeigt(ep.name, ep.code, text))
        else:
            melden(text)
        state.neu_zeichnen()

    def exportieren_fragen(_e: Any = None) -> None:
        if speichern_ohne_weg() is not None:
            return
        if ep.leer:
            melden("Erst Übungen, Pläne oder Kurse wählen.")
            return
        unveraendert = ep.version is not None and ep.exportiert_sha == repo.sha(ep)
        stufe = {"wahl": KLEIN}
        vorschau = ft.Text(weight=ft.FontWeight.W_600)
        nachher = Nachher()

        def version() -> int:
            if unveraendert and ep.version is not None:
                return ep.version
            return naechste_version(ep.version, stufe["wahl"])

        def vorschau_neu() -> None:
            vorschau.value = f"Version {version_text(version())}"
            with contextlib.suppress(Exception):
                vorschau.update()

        def stufe_waehlen(e: Any) -> None:
            if e.control.selected:
                stufe["wahl"] = str(e.control.selected[0])
            vorschau_neu()

        def los(_e: Any = None) -> None:
            v = version()
            nachher.danach(lambda: page.run_task(teilen, v))
            schliessen(dialog)

        inhalt: list[ft.Control] = [vorschau]
        if ep.version is None:
            inhalt.append(ft.Text("Die erste Fassung.", size=13))
        elif unveraendert:
            inhalt.append(
                ft.Text(
                    f"Unverändert seit Version {version_text(ep.version)} — noch einmal teilen.",
                    size=13,
                )
            )
        else:
            inhalt += [
                ft.Text(
                    f"Seit Version {version_text(ep.version)} geändert. Wie groß ist die "
                    "Änderung? Die Geräte sehen es selbst am Unterschied — die Nummer sagt es "
                    "von selbst.",
                    size=13,
                ),
                ft.SegmentedButton(
                    selected=[KLEIN],
                    show_selected_icon=False,
                    segments=[
                        ft.Segment(value=s, label=ft.Text(t.split(" (")[0]), tooltip=t)
                        for s, t in STUFEN.items()
                        if s in (KLEIN, MITTEL, GROSS)
                    ],
                    on_change=stufe_waehlen,
                    data="stufe",
                ),
            ]
        inhalt.append(
            ft.Text(
                "Dateien gehen ohne Ortsangaben hinaus. Wer das Paket bekommt, importiert die "
                "Datei — eine neue Fassung ist ein Update desselben Pakets.",
                size=12,
                opacity=0.7,
            )
        )
        vorschau_neu()
        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            on_dismiss=nachher.bei_schliessen,
            title=ft.Text(f"„{ep.name}“ teilen"),
            content=ft.Column(tight=True, spacing=10, controls=inhalt),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Exportieren", icon=ft.Icons.IOS_SHARE, on_click=los, data="los"),
            ],
        )
        page.show_dialog(dialog)

    def loeschen_fragen(_e: Any = None) -> None:
        nachher = Nachher()

        def weg() -> None:
            repo.loeschen(ep.id)
            nachher.danach(lambda: page.run_task(page.push_route, basis))
            schliessen(dialog)

        dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            on_dismiss=nachher.bei_schliessen,
            title=ft.Text("Eigenes Paket löschen?"),
            content=ft.Text(
                "Nur die Zusammenstellung hier geht — Übungen, Pläne und Kurse bleiben, und "
                "wer das Paket hat, behält es."
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda: schliessen(dialog)),
                ft.FilledButton("Löschen", on_click=weg),
            ],
        )
        page.show_dialog(dialog)

    async def abbrechen() -> None:
        await page.push_route(zurueck_ziel(page, ansicht))

    async def speichern() -> None:
        if speichern_ohne_weg() is None:
            await page.push_route(zurueck_ziel(page, ansicht))

    stand_text = (
        "Noch nicht geteilt."
        if ep.version is None
        else f"Zuletzt geteilt: Version {version_text(ep.version)}"
        + (f" am {ep.exportiert_am.astimezone():%d.%m.%Y}" if ep.exportiert_am else "")
    )
    info_neu()
    inhalt_karten: list[ft.Control] = [
        karte(
            titel("Übungen"),
            hinweis(
                "Übungen, die ein gewählter Plan oder Kurs braucht, kommen von selbst mit. Was "
                "du an Übungen anderer Pakete geändert hast, reist als Ergänzung — wer das "
                "Paket bekommt, sieht es an seiner Übung."
            ),
            *[uebungsgruppe(t, m) for t, m in gruppen],
        )
    ]
    if plaene:
        inhalt_karten.append(
            karte(titel("Pläne"), *[haken("plaene", p.id, p.name) for p in plaene])
        )
    if kurse:
        inhalt_karten.append(karte(titel("Kurse"), *[haken("kurse", k.id, k.name) for k in kurse]))
    ansicht = ft.View(
        route=route,
        appbar=formular_leiste("Eigenes Paket", abbrechen=abbrechen, speichern=speichern),
        scroll=ft.ScrollMode.AUTO,
        padding=16,
        controls=[
            sicher(
                ft.Column(
                    spacing=14,
                    controls=[
                        name,
                        beschreibung,
                        neuigkeiten,
                        ft.Text(stand_text, size=12, opacity=0.75),
                        privat_schalter,
                        privat_text,
                        *inhalt_karten,
                        info,
                        hinweis(
                            "Videos, Bilder und PDFs hängst du an die Übung („Übung bearbeiten“ "
                            "→ Datei fürs Paket) oder an die Planübung („Im Plan einstellen“)."
                        ),
                        ft.Row(
                            wrap=True,
                            spacing=10,
                            controls=[
                                ft.FilledButton(
                                    "Exportieren und teilen …",
                                    icon=ft.Icons.IOS_SHARE,
                                    on_click=exportieren_fragen,
                                    data="exportieren",
                                ),
                                *(
                                    [
                                        ft.TextButton(
                                            "Löschen",
                                            icon=ft.Icons.DELETE_OUTLINE,
                                            style=ft.ButtonStyle(color=ft.Colors.ERROR),
                                            on_click=loeschen_fragen,
                                        )
                                    ]
                                    if vorhanden is not None
                                    else []
                                ),
                            ],
                        ),
                    ],
                ),
                expand=False,
            )
        ],
    )
    return zurueck_speichert(page, ansicht, geaendert=geaendert, speichern=speichern_ohne_weg)


__all__ = ["NEU", "SEGMENT", "eigene_pakete_karte", "eigenes_paket_view"]
