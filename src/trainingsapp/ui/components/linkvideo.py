"""Videos hinter Links: in der App abspielen und auf dem Gerät speichern (Stufe 7,
`docs/plan_rueckweg_handy.md`, Ben 17.11.2026; Kern: `core/linkvideos.py`).

- **Antippen** eines Links auf eine Videodatei (`core.linkvideos.direkt`): Liegt das Video schon
  auf dem Gerät, spielt es im Spieler der Paketdateien. Sonst lädt die App es — beim ersten Mal
  von einem Server erst nach einer Rückfrage („… sieht deine IP-Adresse“); „Laden“ merkt den
  Server (Ben: „Ein einmal geklickter Link soll gespeichert werden, whitelist“ — „je Server“).
  „Im Browser“ geht immer.
- **Nur im WLAN** (Ben: „Erstmal nur WLAN mit Möglichkeit auf Umstellung“): Meldet das Gerät
  ein getaktetes Netz (`flet_installieren`, wie die App-Updates) und ist „auch über mobile
  Daten“ aus, lädt nichts. Ohne den Dienst (Rechner, Web-Fassung) gilt das Netz als frei.
- **Kurs oder Plan als Ganzes** (`alle_laden`): erst eine Rückfrage für alle neuen Server, dann
  eins nach dem anderen, mit Fortschritt und „Abbrechen“.
- Gespeichert in der Paketablage (`data.paketmedien.Paketablage.link_merken`), angezeigt unter
  Einstellungen → Anhänge; fällt das Medium weg, räumt die Ablage es weg.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

import flet as ft

from trainingsapp.core.linkvideos import LinkFehler, direkt, laden, server
from trainingsapp.core.models import Media
from trainingsapp.core.paketmedien import dateiname, groesse_text
from trainingsapp.ui.components.dialoge import schliessen
from trainingsapp.ui.components.links import oeffnen as link_oeffnen

#: Der Satz, der beim ersten Laden von einem Server steht
HINWEIS = (
    "Die App lädt das Video von {server} auf dieses Gerät und spielt es hier ab. Der Server "
    "sieht dabei deine IP-Adresse und welches Video du lädst. „Laden“ merkt sich den Server — "
    "ändern unter Einstellungen → Updates."
)


async def netz_frei(state: Any) -> bool:
    """Darf jetzt geladen werden — WLAN, oder mobile Daten sind erlaubt?"""
    if state.link_mobil() or getattr(state, "installieren", None) is None:
        return True
    try:
        geraet = dict(await state.installieren.stand())
    except Exception:
        return True  # ohne Antwort des Geräts wie am Rechner
    return not geraet.get("getaktet")


def _melden(page: Any, text: str) -> None:
    page.show_dialog(ft.SnackBar(ft.Text(text)))


class _Fortschritt:
    """Der Dialog „Video laden“ — mit Balken, aus dem Ladefaden gezählt, im Event-Loop
    gezeichnet; „Abbrechen“ hält den Faden beim nächsten Block an."""

    def __init__(self, page: Any, titel: str) -> None:
        self.page = page
        self.abbruch = threading.Event()
        self.n = 0
        self.gesamt: int | None = None
        self.titel = ft.Text(titel, weight=ft.FontWeight.W_500)
        self.balken = ft.ProgressBar(value=None)
        self.zahl = ft.Text("", size=12, opacity=0.7)
        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Video laden"),
            content=ft.Column(tight=True, spacing=8, controls=[self.titel, self.balken, self.zahl]),
            actions=[ft.TextButton("Abbrechen", on_click=lambda _e=None: self.abbruch.set())],
        )

    def melden(self, n: int, gesamt: int | None) -> None:  # im Ladefaden
        if self.abbruch.is_set():
            raise LinkFehler("abgebrochen")
        self.n, self.gesamt = n, gesamt

    def zeichnen(self) -> None:
        self.balken.value = self.n / self.gesamt if self.gesamt else None
        self.zahl.value = groesse_text(self.n) + (
            f" von {groesse_text(self.gesamt)}" if self.gesamt else ""
        )
        with contextlib.suppress(Exception):
            self.dialog.update()


async def _laden_mit_fortschritt(
    page: Any, state: Any, eintraege: list[tuple[str, str]]
) -> tuple[list[str], list[str]]:
    """Lädt ``(url, titel)`` eins nach dem anderen — ``(Namen der geladenen Dateien,
    Fehlertexte)``. Gemeldet wird erst, wenn der Dialog zu ist: Eine Meldung über ihm nähme
    `page.pop_dialog` statt seiner, er bliebe stehen (K47, Release-Durchsicht 18.11.2026)."""
    ablage = state.pakete.ablage
    if ablage is None:
        return [], []
    fertig: list[str] = []
    fehler_texte: list[str] = []
    fort = _Fortschritt(page, "")
    page.show_dialog(fort.dialog)
    try:
        for url, titel in eintraege:
            if fort.abbruch.is_set():
                break
            fort.titel.value = titel or url
            fort.n, fort.gesamt = 0, None
            aufgabe = asyncio.create_task(
                asyncio.to_thread(laden, url, ablage.ordner, fortschritt=fort.melden)
            )
            while not aufgabe.done():
                fort.zeichnen()
                await asyncio.sleep(0.4)
            try:
                name, groesse = aufgabe.result()
            except LinkFehler as fehler:
                if not fort.abbruch.is_set():
                    fehler_texte.append(f"„{titel or url}“: {fehler}")
                continue
            ablage.link_merken(url, name, titel, groesse)
            fertig.append(name)
    finally:
        schliessen(fort.dialog)  # genau diesen — nie den obersten Eintrag
    return fertig, fehler_texte


def _fehler_text(fehler_texte: list[str]) -> str:
    """Ein Satz für alle Fehler — eine Meldung, nicht eine je Video.

    >>> _fehler_text(["„A“: zu groß"]), _fehler_text(["„A“: x", "„B“: y", "„C“: z"])
    ('„A“: zu groß', '„A“: x (und 2 weitere)')
    """
    if not fehler_texte:
        return ""
    rest = len(fehler_texte) - 1
    return fehler_texte[0] + (f" (und {rest} weitere)" if rest else "")


def _server_fragen(
    page: Any, state: Any, server_neu: list[str], weiter: Callable[[], None]
) -> None:
    """Die Rückfrage für Server, die noch nicht erlaubt sind — „Laden“ merkt sie alle."""

    def laden_(_e: Any = None) -> None:
        for s in server_neu:
            state.link_server_erlauben(s)
        schliessen(dialog)
        weiter()

    dialog: ft.AlertDialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Video in der App laden?"),
        content=ft.Text(HINWEIS.format(server=", ".join(server_neu)), data="server_hinweis"),
        actions=[
            ft.TextButton("Abbrechen", on_click=lambda _e=None: schliessen(dialog)),
            ft.FilledButton("Laden", icon=ft.Icons.DOWNLOAD, on_click=laden_),
        ],
    )
    page.show_dialog(dialog)


async def video_oeffnen(
    page: Any,
    state: Any,
    medium: Media,
    *,
    browser: Any = None,
    uebergeben: Callable[[Callable[[], Awaitable[None]]], None] | None = None,
) -> None:
    """Antippen eines Videolinks: abspielen, was schon da ist; sonst (nach Rückfrage) laden und
    dann abspielen. „Im Browser“ bleibt der Weg für alles, was nicht geht."""
    from trainingsapp.ui.views.paketmedium import paketmedium_route

    ablage = state.pakete.ablage
    titel = medium.title or "Video"

    async def abspielen(name: str) -> None:
        state.paketmedium_titel[dateiname(name) or ""] = titel
        ziel = paketmedium_route(page.route, name)

        async def gehen() -> None:
            await page.push_route(ziel)

        if uebergeben is not None:
            uebergeben(gehen)
        else:
            await gehen()

    if ablage is not None and (name := ablage.link_datei(medium.uri)) is not None:
        await abspielen(name)
        return

    async def browser_oeffnen() -> None:
        dienst = browser if browser is not None else state.browser
        if dienst is not None:
            await link_oeffnen(page, dienst, medium.uri)

    if ablage is None or not direkt(medium.uri):
        await browser_oeffnen()
        return
    await link_laden(page, state, medium, abspielen)


async def link_laden(
    page: Any, state: Any, medium: Media, danach: Callable[[str], Awaitable[None]]
) -> None:
    """Ein Videolink auf das Gerät — nur im WLAN (oder erlaubt), beim ersten Mal von einem
    Server erst nach der Rückfrage; ``danach`` bekommt den Namen der Datei in der Ablage. Für
    `video_oeffnen` und das Begleitvideo im Fokus (`components/fokus.py`)."""
    titel = medium.title or "Video"

    async def los() -> None:
        if not await netz_frei(state):
            _melden(
                page,
                "Videos lädt die App nur im WLAN — umstellen unter Einstellungen → Updates "
                "(„Videos auch über mobile Daten“).",
            )
            return
        fertig, fehler_texte = await _laden_mit_fortschritt(page, state, [(medium.uri, titel)])
        if fehler_texte:
            _melden(page, _fehler_text(fehler_texte))
        if fertig:
            await danach(fertig[0])

    if state.link_server_erlaubt(server(medium.uri)):
        await los()
        return
    _server_fragen(page, state, [server(medium.uri)], lambda: page.run_task(los))


def videolinks(medien: Iterable[Media]) -> list[Media]:
    """Die Videolinks, die die App selbst laden kann — je Adresse einmal; im Browser keine
    (`config.WEB.ohne`: ``link_videos``)."""
    from trainingsapp.config import ist_aktiv

    if not ist_aktiv("link_videos"):
        return []
    gesehen: set[str] = set()
    out: list[Media] = []
    for m in medien:
        if m.uri not in gesehen and direkt(m.uri):
            gesehen.add(m.uri)
            out.append(m)
    return out


def alle_laden(page: Any, state: Any, medien: Iterable[Media]) -> None:
    """„Videos laden“ für einen Kurs oder Plan (Ben: „Kurse/Pläne sollen als Ganzes
    gedownloadet werden können“): was noch nicht da ist, nach einer Rückfrage für neue Server."""
    ablage = state.pakete.ablage
    offen = [m for m in videolinks(medien) if ablage is None or ablage.link_datei(m.uri) is None]
    if not offen:
        _melden(page, "Alle Videos sind schon auf dem Gerät.")
        return

    async def los() -> None:
        if not await netz_frei(state):
            _melden(
                page, "Videos lädt die App nur im WLAN — umstellen unter Einstellungen → Updates."
            )
            return
        fertig, fehler_texte = await _laden_mit_fortschritt(
            page, state, [(m.uri, m.title) for m in offen]
        )
        text = f"{len(fertig)} von {len(offen)} Video(s) auf dem Gerät."
        if fehler_texte:
            text += f" Nicht geladen: {_fehler_text(fehler_texte)}"
        _melden(page, text)

    neu = sorted({server(m.uri) for m in offen} - set(state.link_server()))
    if neu:
        _server_fragen(page, state, neu, lambda: page.run_task(los))
    else:
        page.run_task(los)


__all__ = ["HINWEIS", "alle_laden", "link_laden", "netz_frei", "video_oeffnen", "videolinks"]
