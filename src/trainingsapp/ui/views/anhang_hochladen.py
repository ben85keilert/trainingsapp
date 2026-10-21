"""Ein Foto oder Video aus der Fotoauswahl an einen Eintrag hängen — Route
``<basis>/anhang/hochladen/<eintrag>`` (Ben, 21.10.2026, P74: „Ermögliche das Hochladen von
Anhängen. Dabei Vorsicht mit den Nutzerrechten, hier nicht zu aggressiv sein“; Skizzen
I1/I2 https://claude.ai/artifact/7JzRndHG41e3ZfeCm7huCH).

Die Seite öffnet gleich die Fotoauswahl von Android (`flet_hochladen`): Die App bekommt nur
die gewählte Datei, eine Berechtigung für Fotos oder Speicher braucht sie nicht. Danach wird
verkleinert — auf die Qualität aus den Einstellungen, ein Video mit fester Bitrate — und
**ohne Ortsangabe** gespeichert: Die Erweiterung schreibt ohne Exif und ohne Ort, und hier
prüft `jpeg_datei_ohne_metadaten` bzw. `mp4_ort_entfernen` noch einmal (Regel wie GPS). Die
Kopie der Auswahl, die den Ort noch trägt, wird gleich danach gelöscht.

Videos dürfen höchstens zehn Minuten lang sein (`HOCHLADEN_VIDEO_MAX_S`); was länger ist,
kürzt man vorher in der Galerie. Nach dem Verkleinern: Vorschau, „312 MB → 17 MB“, Notiz,
„Behalten“ / „Verwerfen“ — wie bei der Kamera (`views/anhang_aufnahme.py`). „Behalten“
verschiebt die fertigen Dateien an ihren Platz, statt die Bytes durch den Speicher zu tragen.
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from pathlib import Path
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import (
    BILD,
    ENDUNG,
    HOCHLADEN_VIDEO_MAX_S,
    VIDEO,
    Anhang,
    Qualitaet,
    art_der_datei,
    dauer_text,
    geschaetzte_bytes,
    groesse_text,
    neuer_anhang,
)
from trainingsapp.core.models import SessionEntry, jetzt, new_id
from trainingsapp.data.anhaenge import (
    jpeg_datei_ohne_metadaten,
    mp4_ort_entfernen,
    qualitaet_lesen,
)
from trainingsapp.ui.components.anhang_reihe import bild_laden
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_ziel
from trainingsapp.ui.state import AppState

#: Routenteil
HOCHLADEN = "hochladen"


def hochladen_route(basis: str, eintrag_id: str) -> str:
    """``<basis>/anhang/hochladen/<eintrag>`` — ``basis`` ``""`` oder ``/`` = Heute.

    >>> hochladen_route("/", "e1"), hochladen_route("/tag/2026-10-20", "e1")
    ('/anhang/hochladen/e1', '/tag/2026-10-20/anhang/hochladen/e1')
    """
    return f"{basis.rstrip('/')}/anhang/{HOCHLADEN}/{eintrag_id}"


def _art(gewaehlt: dict[str, Any]) -> str | None:
    """Foto oder Video — nach dem Namen, sonst nach dem MIME-Typ der Auswahl."""
    art = art_der_datei(str(gewaehlt.get("name") or gewaehlt.get("pfad") or ""))
    if art is not None:
        return art
    mime = str(gewaehlt.get("mime") or "")
    return BILD if mime.startswith("image/") else VIDEO if mime.startswith("video/") else None


class _Hochladen:
    """Zustand der Seite: Auswahl, Verkleinern, Ergebnis."""

    def __init__(self, page: Any, state: AppState, eintrag: SessionEntry) -> None:
        self.page, self.state, self.eintrag = page, state, eintrag
        self.qualitaet: Qualitaet = qualitaet_lesen(state.einstellungen)
        self.art: str | None = None
        #: Die Kopie der Auswahl (trägt den Ort noch) und was daraus wird
        self.quelle: Path | None = None
        self.ziel: Path | None = None
        self.frontbild: Path | None = None
        self.vorher: int = 0
        self.dauer_s: float | None = None
        self.masse: tuple[int | None, int | None] = (None, None)
        #: Verkleinert und bereit zum Behalten
        self.fertig = False
        self.laeuft = False
        self.notiz = ft.TextField(
            label="Notiz (optional)", hint_text="z. B. links, Seitenansicht", dense=True
        )
        self.titel = ft.Text("", size=15, weight=ft.FontWeight.W_600)
        self.status = ft.Text("", size=13, opacity=0.75)
        self.ort = ft.Row(
            spacing=6,
            visible=False,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.LOCATION_OFF_OUTLINED, size=16, opacity=0.7),
                ft.Text("ohne Ortsangabe gespeichert", size=12, opacity=0.7),
            ],
        )
        self.balken = ft.ProgressBar(value=None, visible=False)
        self.flaeche = ft.Container(expand=True, alignment=ft.Alignment.CENTER)
        self.knoepfe = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=16)
        #: die Seite, sobald sie gebaut ist (für Zurück)
        self.ansicht: Any = None

    # -- Ablauf -----------------------------------------------------------------------------

    async def starten(self) -> None:
        """Die Fotoauswahl öffnen; Abbrechen dort führt zurück."""
        dienst = self.state.hochladen
        if dienst is None:
            self.melden("Hochladen gibt es nur in der App am Handy.")
            return
        self.flaeche.content = ft.Icon(ft.Icons.PHOTO_LIBRARY_OUTLINED, size=64, opacity=0.4)
        self.status.value = "Fotoauswahl ist offen …"
        self.zeichnen()
        try:
            gewaehlt = await dienst.waehlen()
        except Exception as fehler:
            self.melden(f"Auswahl: {fehler}")
            return
        if not gewaehlt:
            await self.zurueck()
            return
        self.quelle = Path(str(gewaehlt["pfad"]))
        self.vorher = int(gewaehlt.get("bytes") or 0)
        self.art = _art(gewaehlt)
        if self.art is None:
            self.quelle_loeschen()
            self.melden("Nur Fotos und Videos lassen sich anhängen.")
            return
        if self.art == VIDEO:
            try:
                ms = await dienst.dauer_ms(str(self.quelle))
            except Exception:
                ms = None
            self.dauer_s = ms / 1000 if ms else None
            if self.dauer_s is not None and self.dauer_s > HOCHLADEN_VIDEO_MAX_S:
                self.quelle_loeschen()
                self.melden(
                    f"Das Video ist {dauer_text(self.dauer_s)} lang — höchstens "
                    f"{dauer_text(HOCHLADEN_VIDEO_MAX_S)}. In der Galerie kürzen "
                    "(Bearbeiten → Zuschneiden), dann noch einmal."
                )
                return
        await self.verkleinern()

    async def verkleinern(self) -> None:
        dienst = self.state.hochladen
        assert dienst is not None and self.quelle is not None and self.art is not None
        ordner = self.state.anhaenge.hochladen_ordner()
        stamm = new_id()
        self.ziel = ordner / f"{stamm}.{ENDUNG[self.art]}"
        self.frontbild = ordner / f"{stamm}_bild.jpg" if self.art == VIDEO else None
        self.laeuft = True
        self.balken.visible = True
        self.balken.value = None
        self.titel.value = self.beschreibung()
        self.status.value = self.vergleich(geschaetzt=True)
        self.state.hochladen_beobachter = self.fortschritt
        self.zeichnen()
        try:
            ergebnis = await dienst.verkleinern(
                str(self.quelle),
                "video" if self.art == VIDEO else "bild",
                str(self.ziel),
                frontbild=str(self.frontbild) if self.frontbild else None,
                kurze_seite=self.qualitaet.kurze_seite,
                jpeg_qualitaet=self.qualitaet.jpeg_qualitaet,
                video_bitrate=self.qualitaet.video_bitrate,
                audio_bitrate=self.qualitaet.audio_bitrate,
            )
        except Exception as fehler:
            self.ergebnis_loeschen()
            self.melden(f"Verkleinern: {fehler}")
            return
        finally:
            self.laeuft = False
            self.state.hochladen_beobachter = None
            self.quelle_loeschen()  # die Kopie trägt den Ort noch — nie liegen lassen
        if ergebnis.get("abgebrochen"):
            self.ergebnis_loeschen()
            return
        try:
            # Netz darunter: Exif und Ortsboxen, auch wenn die Erweiterung sie weglässt
            await asyncio.to_thread(self.ort_entfernen)
        except OSError as fehler:
            self.ergebnis_loeschen()
            self.melden(f"Nicht lesbar: {fehler}")
            return
        if ergebnis.get("dauer_ms"):
            self.dauer_s = float(ergebnis["dauer_ms"]) / 1000
        self.masse = (ergebnis.get("breite"), ergebnis.get("hoehe"))
        self.ergebnis_zeigen()

    def ort_entfernen(self) -> None:
        """`jpeg_datei_ohne_metadaten` und `mp4_ort_entfernen` — im Thread (Dateien)."""
        assert self.ziel is not None
        if self.art == VIDEO:
            mp4_ort_entfernen(self.ziel)
        else:
            jpeg_datei_ohne_metadaten(self.ziel)
        if self.frontbild is not None and self.frontbild.is_file():
            jpeg_datei_ohne_metadaten(self.frontbild)

    def fortschritt(self, anteil: float) -> None:
        self.balken.value = min(max(anteil, 0.0), 1.0)
        self.status.value = f"Wird verkleinert … {round(self.balken.value * 100)} %"
        with contextlib.suppress(Exception):
            self.balken.update()
            self.status.update()

    def ergebnis_zeigen(self) -> None:
        assert self.ziel is not None
        self.fertig = True
        self.balken.visible = False
        # Die Bytes wie bei der Kamera (`anhang_aufnahme`): klein (Frontbild, verkleinertes
        # Foto) und auf jeder Plattform sichtbar
        bild = self.frontbild if self.art == VIDEO else self.ziel
        daten = bild_laden(bild) if bild is not None else None
        vorschau: ft.Control = (
            ft.Image(src=daten, fit=ft.BoxFit.CONTAIN, expand=True)
            if daten
            else ft.Icon(ft.Icons.VIDEOCAM, size=64, opacity=0.5)
        )
        self.flaeche.content = vorschau
        self.titel.value = self.beschreibung()
        self.status.value = self.vergleich()
        self.ort.visible = True
        self.zeichnen()

    async def behalten(self) -> None:
        if not self.fertig or self.ziel is None or self.art is None:
            return
        a: Anhang = neuer_anhang(
            self.eintrag.id,
            self.art,
            self.qualitaet,
            jetzt(),
            dauer_s=self.dauer_s if self.art == VIDEO else None,
            note=self.notiz.value or "",
        )
        a.breite, a.hoehe = self.masse
        try:
            # Verschieben im Thread, die Zeile im Event-Loop (die Verbindung gehört ihm)
            await asyncio.to_thread(
                self.state.anhaenge.dateien_uebernehmen, a, self.ziel, self.frontbild
            )
            self.state.anhaenge.eintragen(a)
        except (OSError, sqlite3.Error) as fehler:
            self.melden(f"Nicht gespeichert: {fehler}")
            return
        self.fertig = False
        self.ziel = self.frontbild = None
        self.page.show_dialog(
            ft.SnackBar(ft.Text("Foto gespeichert" if self.art == BILD else "Video gespeichert"))
        )
        await self.zurueck()

    async def verwerfen(self) -> None:
        self.ergebnis_loeschen()
        await self.zurueck()

    async def zurueck(self) -> None:
        await self.aufraeumen()
        await self.page.push_route(zurueck_ziel(self.page, self.ansicht))

    async def aufraeumen(self) -> None:
        """Beim Verlassen: ein laufendes Verkleinern anhalten, nichts Halbes liegen lassen."""
        if self.laeuft and self.state.hochladen is not None:
            with contextlib.suppress(Exception):
                await self.state.hochladen.abbrechen()
        self.quelle_loeschen()
        if not self.fertig:
            self.ergebnis_loeschen()

    def quelle_loeschen(self) -> None:
        if self.quelle is not None:
            with contextlib.suppress(OSError):
                self.quelle.unlink(missing_ok=True)
            self.quelle = None

    def ergebnis_loeschen(self) -> None:
        for pfad in (self.ziel, self.frontbild):
            if pfad is not None:
                with contextlib.suppress(OSError):
                    pfad.unlink(missing_ok=True)
        self.ziel = self.frontbild = None
        self.fertig = False

    # -- Texte und Darstellung --------------------------------------------------------------

    def beschreibung(self) -> str:
        """„Video · 2:40 · aus der Fotoauswahl“."""
        teile = ["Video" if self.art == VIDEO else "Foto"]
        if self.art == VIDEO and self.dauer_s:
            teile.append(dauer_text(self.dauer_s))
        teile.append("aus der Fotoauswahl")
        return " · ".join(teile)

    def vergleich(self, geschaetzt: bool = False) -> str:
        """„312 MB → etwa 17 MB (Mittel · 720p)“ — vorher geschätzt, danach gemessen."""
        if geschaetzt:
            if self.art == VIDEO and self.dauer_s:
                nachher = f"etwa {groesse_text(geschaetzte_bytes(self.qualitaet, self.dauer_s))}"
                return f"{groesse_text(self.vorher)} → {nachher} ({self.qualitaet.label})"
            return f"Wird verkleinert … ({self.qualitaet.label})"
        groesse = self.ziel.stat().st_size if self.ziel is not None and self.ziel.is_file() else 0
        return f"{groesse_text(self.vorher)} → {groesse_text(groesse)} ({self.qualitaet.label})"

    def melden(self, text: str) -> None:
        self.status.value = text
        self.balken.visible = False
        self.fertig = False
        self.zeichnen()

    def zeichnen(self) -> None:
        self.knoepfe.controls = self._knoepfe()
        self.notiz.visible = self.fertig
        for c in (
            self.knoepfe,
            self.titel,
            self.status,
            self.ort,
            self.balken,
            self.notiz,
            self.flaeche,
        ):
            with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
                c.update()

    def _knoepfe(self) -> list[ft.Control]:
        if self.fertig:
            return [
                ft.OutlinedButton(
                    "Verwerfen", icon=ft.Icons.DELETE_OUTLINE, on_click=self.verwerfen
                ),
                ft.FilledButton("Behalten", icon=ft.Icons.CHECK, on_click=self.behalten),
            ]
        if self.laeuft:
            return [ft.OutlinedButton("Abbrechen", icon=ft.Icons.CLOSE, on_click=self.zurueck)]
        return [ft.OutlinedButton("Zurück", icon=ft.Icons.ARROW_BACK, on_click=self.zurueck)]


def anhang_hochladen_view(page: Any, state: AppState, route: str, eintrag: SessionEntry) -> ft.View:
    """Die Seite — sie öffnet beim Aufbau die Fotoauswahl."""
    uebung = state.uebungen.laden(eintrag.exercise_id, mit_geloeschten=True)
    h = _Hochladen(page, state, eintrag)
    titel = "Hochladen: " + (uebung.name if uebung else "Übung")
    h.zeichnen()
    page.run_task(h.starten)

    async def schliessen() -> None:
        await h.zurueck()

    ansicht = ft.View(
        route=route,
        appbar=ft.AppBar(
            title=ft.Text(titel),
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=schliessen),
        ),
        padding=0,
        controls=[
            sicher(
                ft.Column(
                    expand=True,
                    spacing=8,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Container(
                            expand=True,
                            bgcolor=ft.Colors.BLACK,
                            alignment=ft.Alignment.CENTER,
                            content=h.flaeche,
                        ),
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=16),
                            content=ft.Column(
                                spacing=6,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    h.titel,
                                    h.balken,
                                    h.status,
                                    h.ort,
                                    h.notiz,
                                    h.knoepfe,
                                    ft.Text(
                                        "Die App sieht nur, was du auswählst — keine "
                                        "Berechtigung für alle Fotos. Qualität: "
                                        "Einstellungen → Anhänge.",
                                        size=11,
                                        opacity=0.55,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.Container(height=8),
                                ],
                            ),
                        ),
                    ],
                )
            )
        ],
    )
    h.ansicht = ansicht

    # Auch die Systemtaste räumt auf: Die Kopie der Auswahl trägt den Ort, ein laufendes
    # Verkleinern soll nicht weiterrechnen (`components/zurueck.py`, gleiche Technik)
    async def zurueck_gedrueckt(_e: object = None) -> None:
        await ansicht.confirm_pop(False)
        await h.zurueck()

    ansicht.can_pop = False
    ansicht.on_confirm_pop = zurueck_gedrueckt
    return ansicht


__all__ = ["HOCHLADEN", "anhang_hochladen_view", "hochladen_route"]
