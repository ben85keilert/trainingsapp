"""Foto oder Video an einen Eintrag hängen — Route
``<basis>/anhang/aufnehmen/<ziel>/<foto|video>`` (Ben, 19.10.2026; `docs/plan_anhaenge.md`,
Teil B). ``<ziel>`` ist die ID des Eintrags oder, seit 2.11.2026, ``notiz/<id>`` für die
Notiz zum Tag (`core.anhaenge.Ziel`); ``…/audio`` führt zum Rekorder (`views/anhang_ton.py`).

Die Kamera läuft **in der App** (`flet-camera`): So sind die drei Qualitätsstufen
(`core.anhaenge.Qualitaet`) beim Aufnehmen steuerbar, nichts landet in der Galerie des
Telefons, und die Bytes tragen keinen Ortsstempel. Vor dem Start eines Videos wird ein
Foto geschossen — das ist das Frontbild (`vorschau`), ohne Thumbnail-Bibliothek.

Ablauf: Vorschau vollflächig, unten Auslöser bzw. Aufnahme/Stopp mit laufender Zeit und
Restzeit bis zur Höchstdauer, Kamera wechseln (Front ist für Übungen vor dem Handy die
Regel). Oben im Bild (Ben, 21.10.2026, P73, Skizzen H1/H2: „Timer, Qualität direkt an der
Kamera, Blitz … nicht zu viel“): Blitz (Foto aus · automatisch · an, Video Licht), Timer
(ein Tipp: aus → 1 → 3 → 5 → 10 s; dann zählt die Mitte groß herunter, je Sekunde ein Ton,
„Abbrechen“ hält an) und die Qualität dieser Aufnahme (die Vorgabe bleibt in den
Einstellungen). Mehr nicht — für Profiaufnahmen und lange Videos ist die Kamera des
Telefons da. Nach der Aufnahme: Vorschau, Notizzeile, „Behalten“ / „Verwerfen“. Die
Vorschau liegt **über** der Kamera (`Camera.content`), nie an ihrer Stelle — ein aus dem
Baum genommenes Kamera-Control verliert seinen Controller.
„Behalten“ schreibt die Dateien in einem Thread (die Bytes sind groß,
`AnhangRepo.dateien_schreiben`), die Zeile danach im Event-Loop (`AnhangRepo.eintragen` —
die SQLite-Verbindung darf den Thread nicht wechseln) und geht zurück zur Ansicht darunter.

Am Rechner gibt es keine Kamera-Erweiterung (`Camera` wirft dort beim Anzeigen) — dort
steht „Datei wählen“: Ein Bild oder Video vom Rechner, **unverkleinert**, nur zum Prüfen
des Ablaufs in der Entwicklung. Am Handy kommt ein vorhandenes Foto oder Video über
„Hochladen“ (`views/anhang_hochladen.py`, Erweiterung `flet_hochladen`: verkleinert, ohne
Ortsangabe; Plan, Abschnitt F).

**Dokument** (Ben, 13.11.2026, Plan Teil I; Route ``…/dokument``): dieselbe Kamera, Seite für
Seite — Rückkamera zuerst, Vorgabe „Groß“, damit Text lesbar bleibt. Nach jedem Auslösen
liegt die Seite über der Kamera: „Neu aufnehmen“, „Nächste Seite“ oder „Fertig“. „Fertig“ baut
aus den Seiten ein PDF (`core.dokument.pdf_aus_jpegs`, die JPEG unverändert — die Größe
bestimmt die Qualität oben im Bild); die erste Seite ist das Frontbild. Entzerrt wird nichts.
Daneben „PDF wählen“: eine Datei vom Gerät, bereinigt (`core.dokument.pdf_pruefen`).
Seit P206: Streifen der Seiten unter dem Bild (Tipp öffnet eine), an der offenen Seite ← →,
Zuschneiden (zwei Regler, ein Rechteck — im PDF die ``/CropBox``), Löschen; Zurück fragt,
solange Seiten da sind.
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import time
from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from trainingsapp.core.anhaenge import (
    AUDIO,
    BILD,
    DOKUMENT,
    ENDUNG,
    VIDEO,
    Anhang,
    Qualitaet,
    Ziel,
    bild_ohne_metadaten,
    blitz_text,
    blitz_weiter,
    countdown_text,
    dauer_text,
    groesse_text,
    neuer_anhang,
    timer_text,
    timer_weiter,
)
from trainingsapp.core.bereinigen import NichtBereinigbar
from trainingsapp.core.dokument import (
    MAX_SEITEN,
    OHNE_ZUSCHNITT,
    Zuschnitt,
    gezeigte_masse,
    pdf_aus_jpegs,
    pdf_pruefen,
    seite_bereinigt,
    seiten_text,
    zuschnitt_gueltig,
)
from trainingsapp.core.models import jetzt
from trainingsapp.core.timer import COUNTDOWN
from trainingsapp.data.anhaenge import qualitaet_lesen, video_max_s
from trainingsapp.ui import paketdatei, systemdialog
from trainingsapp.ui.components.dialoge import loeschen_rueckfrage
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.components.zurueck import zurueck_speichert, zurueck_ziel
from trainingsapp.ui.state import AppState
from trainingsapp.ui.timer_takt import ton_spielen

#: Routenteile
ANHANG, AUFNEHMEN = "anhang", "aufnehmen"
ARTEN = {"foto": BILD, "video": VIDEO, "audio": AUDIO, "dokument": DOKUMENT}
#: Womit eine Aufnahme im Titel und in der Meldung heißt
TITEL = {BILD: "Foto", VIDEO: "Video", DOKUMENT: "Dokument"}
WORT = {art: wort for wort, art in ARTEN.items()}
#: Takt des Selbstauslösers (s) — eine Zahl, ein Ton
COUNTDOWN_TAKT_S = 1.0


def aufnahme_route(basis: str, ziel: Ziel | str, art: str) -> str:
    """``<basis>/anhang/aufnehmen/<ziel>/<foto|video|audio>`` — ``basis`` ``""`` oder ``/`` =
    Heute; ``ziel`` eine Eintrags-ID oder ein `Ziel` (auch der Tag).

    >>> aufnahme_route("/", "e1", BILD), aufnahme_route("/tag/2026-10-20", "e1", VIDEO)
    ('/anhang/aufnehmen/e1/foto', '/tag/2026-10-20/anhang/aufnehmen/e1/video')
    >>> from datetime import date
    >>> aufnahme_route("/", Ziel.fuer_notiz("p", date(2026, 10, 22), "n1"), AUDIO)
    '/anhang/aufnehmen/notiz/n1/audio'
    """
    teil = ziel.teil if isinstance(ziel, Ziel) else ziel
    return f"{basis.rstrip('/')}/{ANHANG}/{AUFNEHMEN}/{teil}/{WORT.get(art, 'foto')}"


def ziel_name(state: AppState, ziel: Ziel) -> str:
    """Wofür aufgenommen wird — der Name der Übung des Eintrags, beim Tag „Zum Tag · 22.10.“,
    beim Bild einer Übung „Symbol: Kniebeuge“."""
    if ziel.uebung_id is not None:
        u = state.uebungen.laden(ziel.uebung_id, mit_geloeschten=True)
        return f"Symbol: {u.name if u is not None else 'Übung'}"
    if ziel.bewegung_id is not None:
        u = state.uebungen.laden(ziel.bewegung_id, mit_geloeschten=True)
        return f"Bewegung: {u.name if u is not None else 'Übung'}"
    if ziel.ist_paketdatei:
        uebung_id = ziel.paket_uebung_id
        if uebung_id is None and (item := state.plaene.item_laden(ziel.paket_item_id or "")):
            uebung_id = item.exercise_id
        u = state.uebungen.laden(uebung_id, mit_geloeschten=True) if uebung_id else None
        return f"Fürs Paket: {u.name if u is not None else 'Übung'}"
    if ziel.zum_tag is not None:
        return f"Zum Tag · {ziel.zum_tag:%d.%m.}"
    eintrag = state.sitzungen.eintrag_laden(ziel.eintrag_id) if ziel.eintrag_id else None
    uebung = (
        state.uebungen.laden(eintrag.exercise_id, mit_geloeschten=True)
        if eintrag is not None
        else None
    )
    return uebung.name if uebung is not None else "Übung"


def kamera_moeglich(page: Any) -> bool:
    """Nur Android, iOS und Web haben die Kamera-Erweiterung (flet-camera `before_update`)."""
    plattform = getattr(page, "platform", None)
    return bool(getattr(page, "web", False)) or plattform in (
        ft.PagePlatform.ANDROID,
        ft.PagePlatform.IOS,
    )


class _Aufnahme:
    """Zustand der Seite: Kamera, laufende Aufnahme, Ergebnis."""

    def __init__(self, page: Any, state: AppState, ziel: Ziel, art: str) -> None:
        self.page, self.state, self.ziel, self.art = page, state, ziel, art
        # Ein Dokument beginnt „Groß“ (1080p): Darunter wird Text unleserlich; oben im Bild
        # lässt es sich für diese Aufnahme kleiner stellen
        self.qualitaet: Qualitaet = (
            Qualitaet.GROSS if art == DOKUMENT else qualitaet_lesen(state.einstellungen)
        )
        #: Dokument: die behaltenen Seiten (bereinigte JPEG) und die gerade aufgenommene,
        #: die noch über der Kamera liegt
        self.seiten: list[bytes] = []
        #: je Seite ihr Zuschnitt (`core.dokument.Zuschnitt`)
        self.schnitte: list[Zuschnitt] = []
        #: die Seite, die gerade über der Kamera liegt (Index) — ``None``: die Kamera
        self.offen: int | None = None
        #: die offene Seite ist die eben aufgenommene („Neu aufnehmen“ statt „Löschen“)
        self.frisch = False
        #: die offene Seite wird zugeschnitten (Regler statt Knöpfe)
        self.schneidet = False
        self.streifen = ft.Row(spacing=6, scroll=ft.ScrollMode.AUTO, visible=False)
        self.werkzeuge = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=0, visible=False)
        self.regler_breite = ft.RangeSlider(
            min=0, max=100, start_value=0, end_value=100, on_change=self._schnitt_geaendert
        )
        self.regler_hoehe = ft.RangeSlider(
            min=0, max=100, start_value=0, end_value=100, on_change=self._schnitt_geaendert
        )
        self.regler = ft.Column(
            spacing=0,
            visible=False,
            controls=[
                ft.Row(
                    spacing=4,
                    controls=[
                        ft.Text(name, size=12, width=44),
                        ft.Container(expand=True, content=c),
                    ],
                )
                for name, c in (("Breite", self.regler_breite), ("Höhe", self.regler_hoehe))
            ],
        )
        #: Was vom Zuschnitt wegfällt, dunkel über der Seite — einmal gebaut, nur die Anteile
        #: ändern sich (`_blende_setzen`)
        dunkel = ft.Colors.with_opacity(0.6, ft.Colors.BLACK)
        self.blende_teile = [ft.Container(bgcolor=dunkel) for _ in range(4)]  # l, o, r, u
        self.blende_frei = ft.Container(border=ft.Border.all(1, ft.Colors.WHITE))
        self.blende_mitte = ft.Row(
            spacing=0,
            controls=[self.blende_teile[0], self.blende_frei, self.blende_teile[2]],
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.blende = ft.Column(
            spacing=0,
            controls=[self.blende_teile[1], self.blende_mitte, self.blende_teile[3]],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.max_s: int = video_max_s(state.einstellungen)
        self.kamera: Any = None  # flet_camera.Camera
        self.kameras: list[Any] = []
        self.kamera_index = 0
        self.bereit = False
        #: Der zuletzt gemeldete Fehler der Kamera — er steht in jedem weiteren Zustand
        self.letzter_fehler: str | None = None
        self.laeuft_seit: float | None = None
        #: Ergebnis: Daten, Frontbild (Video), Dauer
        self.daten: bytes | None = None
        self.frontbild: bytes | None = None
        self.dauer_s: float | None = None
        self.notiz = ft.TextField(
            label="Notiz (optional)", hint_text="z. B. links, Seitenansicht", dense=True
        )
        self.status = ft.Text("", size=13, opacity=0.75)
        self.zeit = ft.Text("", size=28, weight=ft.FontWeight.W_600)
        self.flaeche = ft.Container(expand=True, alignment=ft.Alignment.CENTER)
        self.knoepfe = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=16)
        self.ticker: asyncio.Task[None] | None = None
        #: Oben im Bild (P73): Blitz (flet-camera ``FlashMode`` als Text) und Selbstauslöser
        #: (s) — nur für diese Seite; die Qualität oben gilt nur für diese Aufnahme
        self.blitz = "off"
        self.timer_s = 0
        self.leiste = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=8)
        #: Countdown des Selbstauslösers: Sekunden bis zum Auslösen, groß in der Mitte
        self.countdown_rest: int | None = None
        self.countdown_aufgabe: Any = None
        self.gross = ft.Text("", size=120, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE)
        #: die Seite, sobald sie gebaut ist (für Zurück)
        self.ansicht: Any = None

    # -- Kamera --------------------------------------------------------------------------

    async def kamera_starten(self) -> None:
        """Kamera anlegen, Berechtigung holen, mit der eingestellten Qualität öffnen."""
        try:
            from flet_camera import Camera, ResolutionPreset
        except ImportError:
            self.melden("Kamera-Erweiterung fehlt in diesem Build.")
            return
        try:
            from flet_permission_handler import Permission, PermissionHandler, PermissionStatus

            ph = PermissionHandler()
            self.page.services.append(ph)
            noetig = [Permission.CAMERA] + ([Permission.MICROPHONE] if self.art == VIDEO else [])
            for p in noetig:
                status = await ph.request(p)
                if status not in (PermissionStatus.GRANTED, PermissionStatus.LIMITED, None):
                    self.melden(
                        "Ohne Kamera-Berechtigung geht es nicht — in den Systemeinstellungen "
                        "der App erlauben."
                    )
                    return
        except ImportError:
            pass  # ohne Handler fragt das Kamera-Plugin selbst
        self.kamera = Camera(expand=True, on_state_change=self._zustand)
        self.flaeche.content = self.kamera
        self.flaeche.update()
        try:
            self.kameras = await self.kamera.get_available_cameras()
        except Exception as fehler:
            self.melden(f"Keine Kamera gefunden: {fehler}")
            return
        if not self.kameras:
            self.melden("Keine Kamera gefunden.")
            return
        # Front zuerst — Übungen vor dem aufgestellten Handy sind die Regel; ein Dokument
        # liegt vor einem, dafür ist die Rückkamera da
        zuerst = "back" if self.art == DOKUMENT else "front"
        self.kamera_index = next(
            (i for i, k in enumerate(self.kameras) if str(k.lens_direction.value) == zuerst),
            0,
        )
        await self._oeffnen(ResolutionPreset(self.qualitaet.preset))

    async def _oeffnen(self, preset: Any) -> None:
        assert self.kamera is not None
        try:
            await self.kamera.initialize(
                self.kameras[self.kamera_index],
                preset,
                enable_audio=self.art == VIDEO,
                video_bitrate=self.qualitaet.video_bitrate,
                audio_bitrate=self.qualitaet.audio_bitrate,
            )
        except Exception as fehler:
            self.melden(f"Kamera lässt sich nicht öffnen: {fehler}")
            return
        await self._blitz_setzen()  # ein neuer Controller beginnt mit seinem eigenen Blitz
        self.bereit = True
        self.status.value = self.kamera_text()
        self.zeichnen()

    async def _blitz_setzen(self) -> bool:
        """Den gewählten Blitz an die Kamera geben — ``False``, wenn sie keinen hat."""
        if self.kamera is None:
            return False
        try:
            from flet_camera import FlashMode

            await self.kamera.set_flash_mode(FlashMode(self.blitz))
        except Exception:
            return False
        return True

    def kamera_text(self) -> str:
        """„Mittel · 720p · Frontkamera · Timer 3 s“ — was gerade eingestellt ist."""
        teile = [self.qualitaet.label, self._richtung()]
        if self.seiten:
            teile.insert(0, seiten_text(len(self.seiten)))
        if self.timer_s:
            teile.append(f"Timer {self.timer_s} s")
        return " · ".join(t for t in teile if t)

    def _zustand(self, e: Any) -> None:
        """Ein Fehler im Zustand der Kamera. flet-camera trägt ihn in **jedem** weiteren
        Zustand mit (``errorDescription`` bleibt stehen) — darum zählt nur ein neuer, und
        die Kamera bleibt bereit, solange sie geöffnet ist. Blitzfehler (keine Lampe an
        dieser Kamera) meldet `blitz_tippen` selbst. Bis 21.10.2026 machte schon das
        „Blitz aus“ beim Öffnen einer Kamera ohne Lampe („torchModeNotSupported“) jeden
        späteren Zustand zum Fehler: Auslöser gesperrt, „Verwerfen“ verließ die Seite."""
        if not getattr(e, "has_error", False):
            return
        text = str(getattr(e, "error_description", "") or "Fehler")
        if text == self.letzter_fehler:
            return
        self.letzter_fehler = text
        if "torch" in text.lower() or "flash" in text.lower():
            return
        if getattr(e, "is_initialized", True):
            self.status.value = f"Kamera: {text}"
            self.zeichnen()
        else:
            self.melden(f"Kamera: {text}")

    def _richtung(self) -> str:
        if not self.kameras:
            return ""
        wert = str(self.kameras[self.kamera_index].lens_direction.value)
        return {"front": "Frontkamera", "back": "Rückkamera"}.get(wert, "Kamera")

    async def wechseln(self) -> None:
        if self.kamera is None or len(self.kameras) < 2 or self.laeuft_seit is not None:
            return
        self.kamera_index = (self.kamera_index + 1) % len(self.kameras)
        try:
            await self.kamera.set_description(self.kameras[self.kamera_index])
        except Exception as fehler:
            self.melden(f"Kamera wechseln: {fehler}")
            return
        await self._blitz_setzen()
        self.status.value = self.kamera_text()
        self.zeichnen()

    # -- Oben im Bild: Blitz, Timer, Qualität (P73, Skizze H1) ---------------------------

    async def blitz_tippen(self) -> None:
        """Blitz weiterschalten: Foto aus → automatisch → an, Video Licht aus ↔ an."""
        if self.kamera is None or not self.bereit:
            return
        self.blitz = blitz_weiter(self.art, self.blitz)
        if await self._blitz_setzen():
            self.status.value = self.kamera_text()
        else:  # die Frontkamera hat meist keinen
            self.blitz = "off"
            self.status.value = f"{self.kamera_text()} · ohne Blitz"
        self.zeichnen()

    def timer_tippen(self) -> None:
        """Selbstauslöser weiterschalten: aus → 1 → 3 → 5 → 10 s → aus."""
        self.timer_s = timer_weiter(self.timer_s)
        self.status.value = self.kamera_text()
        self.zeichnen()

    def qualitaet_waehler(self, q: Qualitaet) -> Callable[[], Awaitable[None]]:
        async def handler() -> None:
            await self.qualitaet_setzen(q)

        return handler

    async def qualitaet_setzen(self, q: Qualitaet) -> None:
        """Die Qualität dieser Aufnahme: Die Kamera öffnet mit dem anderen Preset neu
        (flet-camera tauscht den Controller); die Vorgabe in den Einstellungen bleibt."""
        if (
            q == self.qualitaet
            or self.kamera is None
            or not self.kameras
            or self.laeuft_seit is not None
            or self.countdown_rest is not None
        ):
            return
        from flet_camera import ResolutionPreset

        self.qualitaet = q
        self.bereit = False
        self.status.value = "Kamera wird neu geöffnet …"
        self.zeichnen()
        await self._oeffnen(ResolutionPreset(q.preset))

    # -- Auslösen, mit Selbstauslöser (Skizze H2) ----------------------------------------

    async def ausloesen(self) -> None:
        """Der Auslöser: gleich — oder nach dem Countdown des Selbstauslösers."""
        if (
            self.kamera is None
            or not self.bereit
            or self.countdown_rest is not None
            or self.laeuft_seit is not None
            or self.offen is not None
            or len(self.seiten) >= MAX_SEITEN
        ):
            return
        if self.timer_s <= 0:
            await self._jetzt_ausloesen()
            return
        self.countdown_rest = self.timer_s
        self.zeichnen()  # gleich „Abbrechen“ statt des Auslösers
        self.countdown_aufgabe = self.page.run_task(self._countdown)

    async def _jetzt_ausloesen(self) -> None:
        await (self.video_start() if self.art == VIDEO else self.foto())

    async def _countdown(self) -> None:
        """Je Sekunde die Zahl groß in der Mitte und ein kurzer Ton (der Countdown-Ton des
        Timers, mit dessen Lautstärke) — danach Foto bzw. Videostart."""
        for rest in range(self.timer_s, 0, -1):
            if self.countdown_rest is None:  # abgebrochen
                return
            self.countdown_rest = rest
            self.gross.value = str(rest)
            self.status.value = countdown_text(self.art, rest, self.max_s)
            self.zeichnen()
            await ton_spielen(self.state, COUNTDOWN)
            await asyncio.sleep(COUNTDOWN_TAKT_S)
        if self.countdown_rest is None:
            return
        self.countdown_ende()
        await self._jetzt_ausloesen()

    def countdown_ende(self) -> None:
        self.countdown_rest = None
        self.countdown_aufgabe = None
        self.gross.value = ""
        self.status.value = self.kamera_text()
        self.zeichnen()

    def abbrechen(self) -> None:
        """„Abbrechen“ hält den Countdown an — aufgenommen wird nichts."""
        aufgabe = self.countdown_aufgabe
        self.countdown_ende()
        if aufgabe is not None:
            with contextlib.suppress(Exception):
                aufgabe.cancel()

    # -- Aufnehmen -----------------------------------------------------------------------

    async def foto(self) -> None:
        if self.kamera is None or not self.bereit:
            return
        try:
            daten = await self.kamera.take_picture()
        except Exception as fehler:
            self.melden(f"Foto fehlgeschlagen: {fehler}")
            return
        if self.art == DOKUMENT:
            self.seite_zeigen(daten)
            return
        self.daten = daten
        self.ergebnis_zeigen()

    # -- Dokument: Seite für Seite (Plan Teil I) -----------------------------------------

    def _ueber_die_kamera(self, inhalt: ft.Control | None) -> None:
        """Etwas über die Kamera legen, nicht an ihre Stelle (siehe `ergebnis_zeigen`)."""
        decke = (
            None
            if inhalt is None
            else ft.Container(
                expand=True, bgcolor=ft.Colors.BLACK, alignment=ft.Alignment.CENTER, content=inhalt
            )
        )
        if self.kamera is not None:
            self.kamera.content = decke
        else:
            self.flaeche.content = decke

    def seite_zeigen(self, daten: bytes) -> None:
        """Die eben aufgenommene Seite kommt ins Dokument und liegt über der Kamera — „Neu
        aufnehmen“ nimmt sie wieder heraus."""
        try:
            seite = seite_bereinigt(daten)
        except NichtBereinigbar as fehler:
            self.status.value = f"Seite nicht lesbar: {fehler}"
            self.zeichnen()
            return
        self.seiten.append(seite)
        self.schnitte.append(OHNE_ZUSCHNITT)
        self.seite_oeffnen(len(self.seiten) - 1, frisch=True)

    def seite_oeffner(self, nummer: int) -> Callable[[], None]:
        return lambda: self.seite_oeffnen(nummer)

    def seite_oeffnen(self, nummer: int, *, frisch: bool = False) -> None:
        """Eine Seite über die Kamera legen: ansehen, verschieben, zuschneiden, löschen."""
        if not 0 <= nummer < len(self.seiten) or self.daten is not None:
            return
        self.offen, self.frisch, self.schneidet = nummer, frisch, False
        breite, hoehe = gezeigte_masse(self.seiten[nummer])
        self._blende_setzen()
        self._ueber_die_kamera(
            ft.Container(
                aspect_ratio=breite / hoehe,
                content=ft.Stack(
                    fit=ft.StackFit.EXPAND,
                    controls=[
                        ft.Image(src=self.seiten[nummer], fit=ft.BoxFit.FILL, expand=True),
                        self.blende,
                    ],
                ),
            )
        )
        self.status.value = self.seite_text()
        self.zeichnen()

    def seite_text(self) -> str:
        """„Seite 2 von 3 · 0,4 MB · zugeschnitten“."""
        if self.offen is None:
            return self.kamera_text()
        teile = [
            f"Seite {self.offen + 1} von {len(self.seiten)}",
            groesse_text(len(self.seiten[self.offen])),
        ]
        if self.schnitte[self.offen] != OHNE_ZUSCHNITT:
            teile.append("zugeschnitten")
        return " · ".join(teile)

    def zur_kamera(self) -> None:
        """„Nächste Seite“: Die Seite bleibt im Dokument, die Kamera ist wieder da."""
        self.offen, self.frisch, self.schneidet = None, False, False
        self._ueber_die_kamera(None)
        self.status.value = self.kamera_text()
        self.zeichnen()

    def seite_loeschen(self) -> None:
        """Die offene Seite aus dem Dokument nehmen („Neu aufnehmen“ bei der eben
        aufgenommenen) — zurück zur Kamera."""
        if self.offen is not None:
            del self.seiten[self.offen]
            del self.schnitte[self.offen]
        self.zur_kamera()

    def seite_schieber(self, schritt: int) -> Callable[[], None]:
        return lambda: self.seite_schieben(schritt)

    def seite_schieben(self, schritt: int) -> None:
        """Die offene Seite um einen Platz nach vorn (−1) oder hinten (+1)."""
        if self.offen is None:
            return
        ziel = self.offen + schritt
        if not 0 <= ziel < len(self.seiten):
            return
        a, b = self.offen, ziel
        self.seiten[a], self.seiten[b] = self.seiten[b], self.seiten[a]
        self.schnitte[a], self.schnitte[b] = self.schnitte[b], self.schnitte[a]
        self.offen, self.frisch = ziel, False
        self.status.value = self.seite_text()
        self.zeichnen()

    # -- Zuschneiden (P206): ein Rechteck, kein Entzerren -------------------------------

    def schneiden(self) -> None:
        """Die Regler für Breite und Höhe statt der Knöpfe — der Zuschnitt gilt sofort."""
        if self.offen is None:
            return
        self.schneidet = True
        links, oben, rechts, unten = self.schnitte[self.offen]
        self.regler_breite.start_value, self.regler_breite.end_value = (
            round(links * 100),
            round((1 - rechts) * 100),
        )
        self.regler_hoehe.start_value, self.regler_hoehe.end_value = (
            round(oben * 100),
            round((1 - unten) * 100),
        )
        self.zeichnen()

    def _schnitt_geaendert(self, _e: object = None) -> None:
        if self.offen is None:
            return
        self.schnitte[self.offen] = zuschnitt_gueltig(
            (
                float(self.regler_breite.start_value) / 100,
                float(self.regler_hoehe.start_value) / 100,
                1 - float(self.regler_breite.end_value) / 100,
                1 - float(self.regler_hoehe.end_value) / 100,
            )
        )
        self._blende_setzen()
        self.status.value = self.seite_text()
        for c in (self.blende, self.status):
            with contextlib.suppress(Exception):
                c.update()

    def schnitt_fertig(self) -> None:
        self.schneidet = False
        self.status.value = self.seite_text()
        self.zeichnen()

    def schnitt_weg(self) -> None:
        """„Ganze Seite“: der Zuschnitt fällt weg."""
        if self.offen is not None:
            self.schnitte[self.offen] = OHNE_ZUSCHNITT
        self._blende_setzen()
        self.schnitt_fertig()

    def _blende_setzen(self) -> None:
        """Die dunklen Ränder nach dem Zuschnitt der offenen Seite — als Anteile (Promille),
        damit niemand die Pixel der Seite kennen muss."""
        schnitt = self.schnitte[self.offen] if self.offen is not None else OHNE_ZUSCHNITT
        links, oben, rechts, unten = (round(x * 1000) for x in schnitt)
        for teil, anteil in zip(self.blende_teile, (links, oben, rechts, unten), strict=True):
            teil.visible = anteil > 0
            teil.expand = max(anteil, 1)
        self.blende_frei.expand = max(1000 - links - rechts, 1)
        self.blende_mitte.expand = max(1000 - oben - unten, 1)
        self.blende_frei.border = (
            ft.Border.all(1, ft.Colors.WHITE) if schnitt != OHNE_ZUSCHNITT else None
        )

    async def dokument_fertig(self) -> None:
        """„Fertig“: aus den Seiten ein PDF bauen — im Thread, die Bytes sind groß — und es wie
        jede Aufnahme zum Behalten zeigen."""
        if getattr(self, "_baut", False) or not self.seiten:
            return
        self._baut = True
        self.offen, self.frisch, self.schneidet = None, False, False
        self.status.value = "Dokument wird gebaut …"
        self.zeichnen()
        try:
            self.daten = await asyncio.to_thread(
                pdf_aus_jpegs, list(self.seiten), list(self.schnitte)
            )
        except NichtBereinigbar as fehler:
            self.status.value = f"Dokument nicht gebaut: {fehler}"
            self.zeichnen()
            return
        finally:
            self._baut = False
        self.frontbild = self.seiten[0]
        self.ergebnis_zeigen()

    def seiten_fragen(self) -> str:
        """Zurück mit aufgenommenen Seiten (P206): erst fragen — ``""`` heißt für
        `zurueck_speichert` „selbst gefragt, bleiben“."""
        self.page.show_dialog(
            loeschen_rueckfrage(
                "Seiten verwerfen?",
                f"{seiten_text(len(self.seiten))} aufgenommen, aber noch nicht als Dokument "
                "behalten.",
                lambda: self.page.run_task(self.zurueck),
                knopf="Verwerfen",
            )
        )
        return ""

    async def video_start(self) -> None:
        if self.kamera is None or not self.bereit or self.laeuft_seit is not None:
            return
        try:
            # Das Frontbild: ein Foto direkt vor dem Start
            self.frontbild = await self.kamera.take_picture()
            with contextlib.suppress(Exception):
                await self.kamera.prepare_for_video_recording()
            await self.kamera.start_video_recording()
        except Exception as fehler:
            self.melden(f"Video fehlgeschlagen: {fehler}")
            return
        self.laeuft_seit = time.monotonic()
        self.zeichnen()
        self.ticker = self.page.run_task(self._ticken)

    async def _ticken(self) -> None:
        while self.laeuft_seit is not None:
            vergangen = time.monotonic() - self.laeuft_seit
            self.zeit.value = f"{dauer_text(vergangen)} · noch {dauer_text(self.max_s - vergangen)}"
            with contextlib.suppress(Exception):
                self.zeit.update()
            if vergangen >= self.max_s:
                await self.video_stopp()
                return
            await asyncio.sleep(0.5)

    async def video_stopp(self) -> None:
        if self.kamera is None or self.laeuft_seit is None:
            return
        self.dauer_s = time.monotonic() - self.laeuft_seit
        self.laeuft_seit = None
        try:
            self.daten = await self.kamera.stop_video_recording()
        except Exception as fehler:
            self.melden(f"Video fehlgeschlagen: {fehler}")
            return
        self.ergebnis_zeigen()

    async def datei_waehlen(self) -> None:
        """Am Rechner: ein Bild oder Video von der Platte — unverkleinert, zum Prüfen. Beim
        Dokument überall: eine PDF-Datei vom Gerät, bereinigt (`core.dokument.pdf_pruefen`)."""
        endungen = {BILD: ["jpg", "jpeg"], DOKUMENT: ["pdf"]}.get(self.art, ["mp4"])
        try:
            dateien = await systemdialog.mit(
                ft.FilePicker().pick_files(
                    dialog_title=f"{'PDF' if self.art == DOKUMENT else TITEL[self.art]} wählen",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=endungen,
                    with_data=False,
                )
            )
        except Exception as fehler:
            self.melden(f"Dateiauswahl: {fehler}")
            return
        if not dateien or not dateien[0].path:
            return
        from pathlib import Path

        pfad = Path(dateien[0].path)
        try:
            daten = await asyncio.to_thread(pfad.read_bytes)
            if self.art == BILD:
                # Die Datei kommt an Kamera und Erweiterung vorbei — das Netz darunter gilt
                # auch hier (N117): Exif, XMP und alles hinter dem Bildende fallen weg
                daten = bild_ohne_metadaten(daten)
            elif self.art == DOKUMENT:
                daten = await asyncio.to_thread(pdf_pruefen, daten)
        except (NichtBereinigbar, OSError) as fehler:
            # Die Kamera bleibt, wie sie ist — nur die Meldung wechselt
            self.status.value = f"Nicht übernommen: {fehler}"
            self.zeichnen()
            return
        self.daten = daten
        if self.art == DOKUMENT:
            self.seiten, self.schnitte, self.offen, self.frontbild = [], [], None, None
        if self.art == VIDEO:
            self.frontbild = None  # kein Frontbild ohne Kamera — die Kachel zeigt „fehlt“
            self.dauer_s = None
        self.ergebnis_zeigen()

    # -- Ergebnis ------------------------------------------------------------------------

    def ergebnis_zeigen(self) -> None:
        assert self.daten is not None
        bild = self.daten if self.art == BILD else self.frontbild
        vorschau: ft.Control = (
            ft.Image(src=bild, fit=ft.BoxFit.CONTAIN, expand=True)
            if bild
            else ft.Icon(
                ft.Icons.PICTURE_AS_PDF_OUTLINED if self.art == DOKUMENT else ft.Icons.VIDEOCAM,
                size=64,
                color=ft.Colors.WHITE,
                opacity=0.5,
            )
        )
        # Über die Kamera legen, nicht an ihre Stelle: Aus dem Baum genommen gibt das Plugin
        # den Controller frei, und nach „Verwerfen“ war die Kamera tot (Ben, 21.10.2026 —
        # flet-camera `dispose` → „Camera is not initialized“)
        self._ueber_die_kamera(vorschau)
        teile = [groesse_text(len(self.daten)), self.qualitaet.label]
        if self.art == DOKUMENT:
            teile = [
                seiten_text(len(self.seiten)) if self.seiten else "PDF-Datei",
                groesse_text(len(self.daten)),
            ]
        if self.art == VIDEO and self.dauer_s is not None:
            teile.insert(0, dauer_text(self.dauer_s))
        self.status.value = " · ".join(teile)
        self.zeit.value = ""
        self.zeichnen()

    def dokument_weiter(self) -> None:
        """Vom fertigen Dokument zurück zur Kamera — die Seiten bleiben, eine weitere geht."""
        self.daten, self.frontbild, self.offen = None, None, None
        self._ueber_die_kamera(None)
        self.status.value = self.kamera_text()
        self.zeichnen()

    async def behalten(self) -> None:
        """„Behalten“ — einmal: Ein zweiter Tipp, während die Datei noch geschrieben wird
        (Video: spürbar lang), legte sonst einen zweiten Anhang an (N88)."""
        if self.daten is None or getattr(self, "_speichert", False):
            return
        self._speichert = True
        try:
            await self._behalten()
        finally:
            self._speichert = False

    async def _behalten(self) -> None:
        if self.daten is None:
            return
        if self.ziel.ist_paketdatei:
            # Eine Datei fürs Paket (U4): bereinigt in die Ablage, als Medium an die Übung
            try:
                name = await paketdatei.ablegen(self.state, self.daten, ENDUNG[self.art])
                if not paketdatei.anhaengen(self.state, self.ziel, paketdatei.medium_fuer(name)):
                    self.melden("Die Übung gibt es nicht mehr.")
                    return
            except (NichtBereinigbar, OSError, sqlite3.Error) as fehler:
                self.melden(f"Nicht gespeichert: {fehler}")
                return
            self.daten = None
            self.page.show_dialog(ft.SnackBar(ft.Text("Fürs Paket gespeichert — ohne Ortsangabe")))
            await self.zurueck()
            return
        bild_von = self.ziel.uebung_id or self.ziel.bewegung_id
        if bild_von is not None:
            # Das Bild einer Übung (2.11.2026) oder das Bild der Bewegung (5.11.2026, T6): in
            # die Ablage, nicht an einen Eintrag
            daten = self.daten
            repo = (
                self.state.bewegungsbilder
                if self.ziel.bewegung_id is not None
                else self.state.uebungsbilder
            )
            try:
                # Nur die Bytes im Thread — die SQLite-Verbindung gehört dem Event-Loop
                rel = await asyncio.to_thread(repo.schreiben, daten)
                repo.setzen(bild_von, rel)
            except (NichtBereinigbar, OSError, sqlite3.Error) as fehler:
                self.melden(f"Nicht gespeichert: {fehler}")
                return
            self.daten = None
            self.page.show_dialog(ft.SnackBar(ft.Text("Bild gespeichert")))
            await self.zurueck()
            return
        a: Anhang = neuer_anhang(
            self.ziel,
            self.art,
            self.qualitaet,
            jetzt(),
            dauer_s=self.dauer_s,
            note=self.notiz.value or "",
            frontbild=self.art == DOKUMENT and self.frontbild is not None,
            seiten=len(self.seiten) if self.art == DOKUMENT and self.seiten else None,
        )
        daten, frontbild = self.daten, self.frontbild
        try:
            # Nur die Bytes im Thread — die SQLite-Verbindung gehört dem Event-Loop
            await asyncio.to_thread(self.state.anhaenge.dateien_schreiben, a, daten, frontbild)
            self.state.anhaenge.eintragen(a)
        except (OSError, sqlite3.Error) as fehler:
            self.melden(f"Nicht gespeichert: {fehler}")
            return
        self.daten = None
        self.seiten, self.schnitte = [], []  # behalten — Zurück fragt nicht mehr
        self.page.show_dialog(ft.SnackBar(ft.Text(f"{TITEL[self.art]} gespeichert")))
        await self.zurueck()

    async def verwerfen(self) -> None:
        """Zurück zur Kamera — sie lief unter dem Ergebnis weiter, ein neuer Versuch geht
        sofort."""
        self.daten, self.frontbild, self.dauer_s = None, None, None
        self.seiten, self.schnitte, self.offen = [], [], None
        if self.kamera is not None and self.bereit:
            self.kamera.content = None
            self.status.value = self.kamera_text()
            self.zeichnen()
        else:
            await self.zurueck()

    async def zurueck(self) -> None:
        await self.aufraeumen()
        # Eine Notiz zum Tag, die nur für diesen Anhang entstand, verschwindet wieder, wenn
        # nichts behalten wurde (`components/tagesnotiz.py`)
        if self.ziel.notiz_id is not None:
            self.state.tagesnotizen.aufraeumen(self.ziel.notiz_id)
        await self.page.push_route(zurueck_ziel(self.page, self.ansicht))

    async def aufraeumen(self) -> None:
        """Eine laufende Aufnahme beim Verlassen verwerfen (Zurück, Wegwischen)."""
        if self.countdown_rest is not None:
            self.abbrechen()
        if self.ticker is not None:
            self.ticker.cancel()
            self.ticker = None
        if self.kamera is not None and self.laeuft_seit is not None:
            self.laeuft_seit = None
            with contextlib.suppress(Exception):
                await self.kamera.stop_video_recording()

    # -- Darstellung ---------------------------------------------------------------------

    def melden(self, text: str) -> None:
        self.status.value = text
        self.bereit = False
        self.zeichnen()

    def zeichnen(self) -> None:
        self.knoepfe.controls = self._knoepfe()
        self.leiste.controls = self._leiste()
        self.notiz.visible = self.daten is not None
        self._seiten_zeichnen()
        for c in (
            self.streifen,
            self.werkzeuge,
            self.regler,
            self.knoepfe,
            self.leiste,
            self.gross,
            self.status,
            self.zeit,
            self.notiz,
            self.flaeche,
        ):
            with contextlib.suppress(Exception):  # vor dem ersten Anzeigen
                c.update()

    def _knoepfe(self) -> list[ft.Control]:
        if self.daten is not None:
            if self.art == DOKUMENT and self.seiten and self.kamera is not None:
                return [
                    ft.OutlinedButton(
                        "Weitere Seite", icon=ft.Icons.ADD, on_click=self.dokument_weiter
                    ),
                    ft.FilledButton("Behalten", icon=ft.Icons.CHECK, on_click=self.behalten),
                ]
            return [
                ft.OutlinedButton(
                    "Verwerfen", icon=ft.Icons.DELETE_OUTLINE, on_click=self.verwerfen
                ),
                ft.FilledButton("Behalten", icon=ft.Icons.CHECK, on_click=self.behalten),
            ]
        if not kamera_moeglich(self.page):
            return [
                ft.FilledButton(
                    "PDF wählen" if self.art == DOKUMENT else "Datei wählen",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=self.datei_waehlen,
                )
            ]
        if self.countdown_rest is not None:
            return [ft.OutlinedButton("Abbrechen", icon=ft.Icons.CLOSE, on_click=self.abbrechen)]
        if self.art == DOKUMENT:
            return self._knoepfe_dokument()
        wechsel = ft.IconButton(
            ft.Icons.FLIP_CAMERA_ANDROID,
            tooltip="Kamera wechseln",
            on_click=self.wechseln,
            disabled=len(self.kameras) < 2 or self.laeuft_seit is not None,
        )
        if self.art == BILD:
            return [
                wechsel,
                ft.IconButton(
                    ft.Icons.CAMERA,
                    icon_size=56,
                    tooltip="Foto aufnehmen",
                    on_click=self.ausloesen,
                    disabled=not self.bereit,
                ),
                ft.Container(width=48),
            ]
        if self.laeuft_seit is not None:
            return [
                ft.IconButton(
                    ft.Icons.STOP_CIRCLE,
                    icon_size=56,
                    icon_color=ft.Colors.ERROR,
                    tooltip="Aufnahme beenden",
                    on_click=self.video_stopp,
                )
            ]
        return [
            wechsel,
            ft.IconButton(
                ft.Icons.FIBER_MANUAL_RECORD,
                icon_size=56,
                icon_color=ft.Colors.ERROR,
                tooltip="Video aufnehmen",
                on_click=self.ausloesen,
                disabled=not self.bereit,
            ),
            ft.Container(width=48),
        ]

    def _seiten_zeichnen(self) -> None:
        """Dokument: der Streifen der Seiten (ein Tipp öffnet eine), die Werkzeuge der offenen
        Seite und die Regler des Zuschnitts — je nach Zustand sichtbar."""
        in_arbeit = self.art == DOKUMENT and self.daten is None and bool(self.seiten)
        self.streifen.visible = in_arbeit and not self.schneidet
        self.werkzeuge.visible = in_arbeit and self.offen is not None and not self.schneidet
        self.regler.visible = in_arbeit and self.offen is not None and self.schneidet
        if not in_arbeit:
            return
        self.streifen.controls = [
            ft.Container(
                width=38,
                height=50,
                border_radius=6,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                border=ft.Border.all(
                    2, ft.Colors.PRIMARY if i == self.offen else ft.Colors.OUTLINE
                ),
                tooltip=f"Seite {i + 1}",
                on_click=self.seite_oeffner(i),
                content=ft.Stack(
                    fit=ft.StackFit.EXPAND,
                    controls=[
                        ft.Image(src=seite, fit=ft.BoxFit.COVER, cache_width=114),
                        ft.Container(
                            alignment=ft.Alignment.BOTTOM_RIGHT,
                            padding=2,
                            content=ft.Text(
                                str(i + 1),
                                size=10,
                                color=ft.Colors.WHITE,
                                bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
                            ),
                        ),
                    ],
                ),
            )
            for i, seite in enumerate(self.seiten)
        ]
        if self.offen is None:
            return
        self.werkzeuge.controls = [
            ft.IconButton(
                ft.Icons.ARROW_BACK,
                tooltip="Seite nach vorn",
                on_click=self.seite_schieber(-1),
                disabled=self.offen == 0,
            ),
            ft.IconButton(
                ft.Icons.ARROW_FORWARD,
                tooltip="Seite nach hinten",
                on_click=self.seite_schieber(1),
                disabled=self.offen >= len(self.seiten) - 1,
            ),
            ft.IconButton(ft.Icons.CROP, tooltip="Zuschneiden", on_click=self.schneiden),
            ft.IconButton(
                ft.Icons.REPLAY if self.frisch else ft.Icons.DELETE_OUTLINE,
                tooltip="Neu aufnehmen" if self.frisch else "Seite löschen",
                on_click=self.seite_loeschen,
            ),
        ]

    def _knoepfe_dokument(self) -> list[ft.Control]:
        """Dokument: über einer offenen Seite „Nächste Seite · Fertig“ (beim Zuschneiden „Ganze
        Seite · Übernehmen“), sonst links „PDF wählen“ (solange keine Seite da ist), der
        Auslöser, rechts „Fertig“."""
        eng = ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=10))
        if self.offen is not None and self.schneidet:
            return [
                ft.OutlinedButton("Ganze Seite", on_click=self.schnitt_weg, style=eng),
                ft.FilledButton(
                    "Übernehmen", icon=ft.Icons.CHECK, on_click=self.schnitt_fertig, style=eng
                ),
            ]
        anzahl = len(self.seiten)
        voll = anzahl >= MAX_SEITEN
        if self.offen is not None:
            return [
                ft.OutlinedButton(
                    "Nächste Seite",
                    icon=ft.Icons.ADD,
                    on_click=self.zur_kamera,
                    disabled=voll,
                    tooltip=f"Höchstens {MAX_SEITEN} Seiten" if voll else None,
                    style=eng,
                ),
                ft.FilledButton(
                    f"Fertig · {seiten_text(anzahl)}",
                    icon=ft.Icons.CHECK,
                    on_click=self.dokument_fertig,
                    style=eng,
                ),
            ]
        return [
            ft.IconButton(
                ft.Icons.FOLDER_OPEN,
                tooltip="PDF wählen",
                on_click=self.datei_waehlen,
                disabled=bool(self.seiten),
            ),
            ft.IconButton(
                ft.Icons.CAMERA,
                icon_size=56,
                tooltip="Seite aufnehmen",
                on_click=self.ausloesen,
                disabled=not self.bereit or voll,
            ),
            ft.FilledButton(
                f"Fertig · {anzahl}",
                icon=ft.Icons.CHECK,
                on_click=self.dokument_fertig,
                style=eng,
            )
            if self.seiten
            else ft.Container(width=48),
        ]

    def _leiste(self) -> list[ft.Control]:
        """Oben im Bild (Skizze H1): Blitz, Timer, Qualität — nur mit Kamera und solange
        kein Ergebnis dasteht. Während der Aufnahme bleibt nur das Licht schaltbar."""
        if (
            self.kamera is None
            or not self.kameras
            or self.daten is not None
            or self.offen is not None
        ):
            return []
        frei = self.bereit and self.laeuft_seit is None and self.countdown_rest is None
        symbol = {
            "auto": ft.Icons.FLASH_AUTO,
            "always": ft.Icons.FLASH_ON,
            "torch": ft.Icons.FLASHLIGHT_ON,
        }.get(self.blitz, ft.Icons.FLASHLIGHT_OFF if self.art == VIDEO else ft.Icons.FLASH_OFF)
        return [
            _schalter(
                symbol,
                blitz_text(self.art, self.blitz),
                "Licht" if self.art == VIDEO else "Blitz",
                self.blitz_tippen,
                aus=not self.bereit or self.countdown_rest is not None,
            ),
            _schalter(
                ft.Icons.TIMER if self.timer_s else ft.Icons.TIMER_OFF,
                timer_text(self.timer_s),
                "Selbstauslöser",
                self.timer_tippen,
                aus=not frei,
            ),
            ft.PopupMenuButton(
                tooltip="Qualität dieser Aufnahme",
                disabled=not frei,
                content=_schalter(ft.Icons.HD, self.qualitaet.label, None, None, aus=not frei),
                items=[
                    ft.PopupMenuItem(
                        content=q.label,
                        checked=q == self.qualitaet,
                        on_click=self.qualitaet_waehler(q),
                    )
                    for q in Qualitaet
                ],
            ),
        ]


def _schalter(
    symbol: Any, text: str, tooltip: str | None, on_click: Any, *, aus: bool = False
) -> ft.Control:
    """Ein Knopf oben im Bild: hell auf dunklem, halbdurchsichtigem Grund."""
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=18,
        bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
        opacity=0.5 if aus else 1.0,
        tooltip=tooltip,
        ink=on_click is not None,
        on_click=None if aus else on_click,
        content=ft.Row(
            tight=True,
            spacing=6,
            controls=[
                ft.Icon(symbol, size=18, color=ft.Colors.WHITE),
                ft.Text(text, size=13, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
            ],
        ),
    )


def anhang_aufnahme_view(page: Any, state: AppState, route: str, ziel: Ziel, art: str) -> ft.View:
    """Die Seite. ``art``: `BILD`, `VIDEO` oder `DOKUMENT`; ``ziel``: woran die Aufnahme
    hängt."""
    a = _Aufnahme(page, state, ziel, art)
    titel = f"{TITEL[art]}: {ziel_name(state, ziel)}"
    hinweis = {
        VIDEO: (
            f"Höchstens {dauer_text(a.max_s)} min · Vorgabe der Qualität: Einstellungen → Anhänge"
        ),
        DOKUMENT: (
            f"Seite für Seite, höchstens {MAX_SEITEN} · wird ein PDF · kleiner: Qualität oben"
        ),
    }.get(art, "Vorgabe der Qualität: Einstellungen → Anhänge")
    if kamera_moeglich(page):
        a.status.value = "Kamera wird geöffnet …"
        a.flaeche.content = ft.ProgressRing()
        page.run_task(a.kamera_starten)
    else:
        a.status.value = (
            "Am Rechner gibt es keine Kamera in der App — eine PDF-Datei wählen."
            if art == DOKUMENT
            else "Am Rechner gibt es keine Kamera in der App — zum Prüfen eine Datei wählen "
            "(unverkleinert)."
        )
    a.zeichnen()

    async def schliessen() -> None:
        if a.seiten:
            a.seiten_fragen()  # aufgenommene Seiten gehen nicht ohne Rückfrage verloren
        else:
            await a.zurueck()

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
                            # Über dem Bild: der Countdown groß in der Mitte, oben die Leiste
                            content=ft.Stack(
                                expand=True,
                                fit=ft.StackFit.EXPAND,
                                controls=[
                                    a.flaeche,
                                    ft.Container(alignment=ft.Alignment.CENTER, content=a.gross),
                                    ft.Container(top=10, left=8, right=8, content=a.leiste),
                                ],
                            ),
                        ),
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=16),
                            content=ft.Column(
                                spacing=6,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    a.zeit,
                                    a.status,
                                    a.notiz,
                                    a.streifen,
                                    a.werkzeuge,
                                    a.regler,
                                    a.knoepfe,
                                    ft.Text(hinweis, size=11, opacity=0.55),
                                    ft.Container(height=8),
                                ],
                            ),
                        ),
                    ],
                )
            )
        ],
    )

    # Zurück über die Systemtaste: Flutter nimmt die Seite samt Kamera weg, eine laufende
    # Aufnahme ist damit verworfen (H19: die Engine lebt weiter)
    a.ansicht = ansicht
    if art == DOKUMENT:
        # Auch die Systemtaste fragt, solange Seiten da sind (P206); ohne Seiten wie bisher
        return zurueck_speichert(
            page, ansicht, geaendert=lambda: bool(a.seiten), speichern=a.seiten_fragen, meldung=""
        )
    return ansicht


__all__ = [
    "ANHANG",
    "ARTEN",
    "AUFNEHMEN",
    "WORT",
    "anhang_aufnahme_view",
    "aufnahme_route",
    "ziel_name",
]
