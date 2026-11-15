"""Speichern im Browser — das Datenverzeichnis der Web-Fassung liegt in der IndexedDB.

Ben, 15.11.2026 („Die Speicherfähigkeit im Browser müsste herausgearbeitet werden“); Vertrag:
`docs/plan_web.md` §5.

In der Web-Fassung läuft Python im Browser (Pyodide), und sein Dateisystem ist
Arbeitsspeicher: Datenbank, Messungen und Anhänge waren mit dem Neuladen weg. Hier wird das
Datenverzeichnis (`config.datenverzeichnis()`) auf **IDBFS** gelegt — Emscriptens
Dateisystem, das weiter im Arbeitsspeicher arbeitet und sich auf Zuruf mit der IndexedDB
des Browsers abgleicht. SQLite und alles, was Dateien schreibt, merken davon nichts.

Der Ablauf:

1. **Vor** dem Öffnen der Datenbank: einhängen und holen, was der Browser von früher hat
   (`starten`). Das ist der einzige Schritt, auf den die App warten muss — darum ruft ihn
   `ui/app.py:einstieg` vor `main`.
2. Solange die Seite offen ist: alle `TAKT_S` Sekunden nachsehen, ob sich im Verzeichnis
   etwas geändert hat (`signatur`), und nur dann schreiben (`takt`). Dazu sofort, wenn der
   Tab in den Hintergrund geht — ein „Tab wird geschlossen“ meldet der Browser nicht
   verlässlich.
3. „Alles löschen“ (`loeschen`): die IndexedDB dieser Seite entfernen und für den Rest des
   Besuchs nichts mehr schreiben — für fremde und geteilte Geräte.

Zwei Dinge, die schiefgehen könnten, und was dagegen steht:

- **Zwei Tabs.** Jeder Tab hat sein eigenes Python und sein eigenes Dateisystem; der zweite
  überschriebe beim Schreiben, was der erste gespeichert hat. Der erste Tab hält deshalb
  eine Sperre des Browsers (Web Locks); wer sie nicht bekommt, zeigt den gespeicherten Stand
  und schreibt nicht (`ANDERER_TAB`).
- **Halbe Datenbank.** Der Abgleich liest alle Dateien in einem Zug und schreibt sie in
  einer Transaktion der IndexedDB; geschrieben wird nur, wenn in SQLite gerade keine
  Transaktion offen ist (`ruhig`).

Was der Browser speichert, kann er auch wieder wegnehmen (Websitedaten löschen, privates
Fenster, Safari nach sieben Tagen ohne Besuch) — das ist so gewollt (`docs/plan_web.md` §0).

Dieses Modul importiert kein ``flet``. Den Zugang zum Browser (`PyodideZugang`) gibt es nur
dort; die Tests nehmen einen nachgebauten (`tests/test_browserspeicher.py`), der echte ist im
Browser gemessen (`docs/plan_web.md` §5, Gerätetest T140).
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)

#: So oft sieht der Takt nach, ob etwas zu schreiben ist (Sekunden)
TAKT_S = 2.0
#: Name der Sperre, die der schreibende Tab hält
SPERRE = "trainingsapp-speicher"

#: Zustände — was die Seite „Daten und Sicherung“ dazu sagt, steht in `TEXTE`
AUS = "aus"  # noch nicht gestartet
AN = "an"  # speichert
ANDERER_TAB = "anderer_tab"  # ein anderer Tab speichert; dieser zeigt nur
GELOESCHT = "geloescht"  # „Alles löschen“ — für diesen Besuch aus
FEHLER = "fehler"  # der Browser lässt es nicht zu (voll, gesperrt)

TEXTE: dict[str, str] = {
    AUS: "Hier wird nichts gespeichert. Mit dem Schließen der Seite ist alles weg.",
    AN: (
        "Einträge, Messungen und Einstellungen bleiben in diesem Browser auf diesem Gerät. "
        "Sie gehen an keinen Server. Löscht der Browser seine Websitedaten, sind sie weg."
    ),
    ANDERER_TAB: (
        "Die Seite ist in einem zweiten Tab offen, und dort wird gespeichert. Was du hier "
        "änderst, bleibt nicht. Schließe einen der beiden Tabs und lade die Seite neu."
    ),
    GELOESCHT: (
        "Alles Gespeicherte ist gelöscht. Bis du die Seite schließt oder neu lädst, wird "
        "nichts mehr gespeichert."
    ),
    FEHLER: (
        "Der Browser lässt das Speichern nicht zu (Speicher voll oder gesperrt). Was du "
        "einträgst, ist mit dem Schließen der Seite weg."
    ),
}


class Zugang(Protocol):
    """Was der Speicher vom Browser braucht — echt: `PyodideZugang`."""

    def einhaengen(self, pfad: str) -> None:
        """Legt ``pfad`` auf ein Dateisystem, das sich mit der IndexedDB abgleichen lässt."""

    async def abgleichen(self, holen: bool) -> None:
        """``holen``: IndexedDB → Dateisystem (Start); sonst Dateisystem → IndexedDB."""

    async def sperre(self, name: str) -> bool:
        """Hält die Sperre, bis der Tab schließt. ``False``: Ein anderer Tab hat sie."""

    async def entfernen(self, pfad: str) -> None:
        """Löscht, was zu ``pfad`` in der IndexedDB liegt."""


@dataclass
class Browserspeicher:
    """Hält das Datenverzeichnis mit dem Browser im Gleichgewicht.

    >>> import tempfile
    >>> class Nichts:
    ...     def einhaengen(self, pfad): pass
    ...     async def abgleichen(self, holen): pass
    ...     async def sperre(self, name): return True
    ...     async def entfernen(self, pfad): pass
    >>> s = Browserspeicher(Path(tempfile.mkdtemp()), Nichts())
    >>> asyncio.run(s.starten()); s.zustand, s.vorhanden, s.geaendert()
    ('an', False, False)
    >>> _ = (s.ordner / "trainingsapp.db").write_bytes(b"x"); s.geaendert()
    True
    >>> asyncio.run(s.sichern()), s.geaendert()
    (True, False)
    >>> asyncio.run(s.loeschen()); s.zustand, asyncio.run(s.sichern())
    ('geloescht', False)
    """

    ordner: Path
    zugang: Zugang
    zustand: str = AUS
    #: Lag beim Start schon etwas im Browser? (Dann gehört ein Startfehler den alten Daten.)
    vorhanden: bool = False
    #: Die Meldung des Browsers zum letzten Fehler — für das Protokoll, nicht für die Anzeige
    fehler: str = ""
    _stand: tuple[int, int, int] | None = field(default=None, repr=False)

    @property
    def aktiv(self) -> bool:
        return self.zustand == AN

    @property
    def text(self) -> str:
        return TEXTE[self.zustand]

    async def starten(self) -> None:
        """Einhängen, die Sperre nehmen, holen. Scheitert etwas, läuft die App ohne Speicher."""
        try:
            self.zugang.einhaengen(str(self.ordner))
            frei = await self.zugang.sperre(SPERRE)
            await self.zugang.abgleichen(True)
        except Exception as fehler:
            self._gescheitert(fehler)
            return
        self.vorhanden = any(self.ordner.iterdir()) if self.ordner.is_dir() else False
        self._stand = self.signatur()
        self.zustand = AN if frei else ANDERER_TAB

    def signatur(self) -> tuple[int, int, int]:
        """Zahl der Dateien, ihre Größe und die jüngste Änderung — ändert sich mit jedem
        Schreiben ins Verzeichnis, auch mit jedem ``COMMIT`` der Datenbank."""
        anzahl = groesse = juengste = 0
        stapel = [str(self.ordner)]
        while stapel:
            try:
                with os.scandir(stapel.pop()) as eintraege:
                    for eintrag in eintraege:
                        if eintrag.is_dir(follow_symlinks=False):
                            stapel.append(eintrag.path)
                            continue
                        st = eintrag.stat(follow_symlinks=False)
                        anzahl += 1
                        groesse += st.st_size
                        juengste = max(juengste, st.st_mtime_ns)
            except OSError:
                continue  # ein Ordner verschwand zwischen Auflisten und Lesen
        return anzahl, groesse, juengste

    def geaendert(self) -> bool:
        return self.signatur() != self._stand

    async def sichern(self) -> bool:
        """Schreibt den Stand des Verzeichnisses in den Browser. ``False``: nicht geschrieben
        (aus, anderer Tab, gelöscht) oder gescheitert — dann ist der Speicher danach aus."""
        if not self.aktiv:
            return False
        stand = self.signatur()  # vor dem Schreiben: Was währenddessen dazukommt, zählt neu
        try:
            await self.zugang.abgleichen(False)
        except Exception as fehler:
            self._gescheitert(fehler)
            return False
        self._stand = stand
        return True

    async def takt(self, ruhig: Callable[[], bool]) -> None:
        """Läuft, solange die Seite offen ist: schreibt, wenn sich etwas geändert hat und
        ``ruhig()`` wahr ist (keine offene Transaktion)."""
        while True:
            await asyncio.sleep(TAKT_S)
            if self.aktiv and ruhig() and self.geaendert():
                await self.sichern()

    async def loeschen(self) -> None:
        """Entfernt alles Gespeicherte aus dem Browser; danach schreibt dieser Besuch nichts
        mehr. Was die App gerade zeigt, liegt nur noch im Arbeitsspeicher des Tabs."""
        war = self.zustand
        self.zustand = GELOESCHT  # zuerst: Der Takt darf nicht dazwischen schreiben
        try:
            await self.zugang.entfernen(str(self.ordner))
        except Exception as fehler:
            self.zustand = war
            self.fehler = str(fehler)
            raise

    def _gescheitert(self, fehler: Exception) -> None:
        self.zustand = FEHLER
        self.fehler = str(fehler)
        log.error("Speichern im Browser: %s", fehler)


class PyodideZugang:
    """Der echte Zugang: Emscriptens IDBFS, IndexedDB und Web Locks — nur in Pyodide.

    Jede Methode hier ist eine Stelle, die nur im Browser läuft; gemessen in Chromium
    (`docs/plan_web.md` §5), am Handy steht es aus (T140).
    """

    def __init__(self) -> None:
        import js
        import pyodide_js

        self._js: Any = js
        self._fs: Any = pyodide_js.FS

    def einhaengen(self, pfad: str) -> None:
        self._fs.mkdirTree(pfad)
        self._fs.mount(self._fs.filesystems.IDBFS, self._js.Object.new(), pfad)

    async def abgleichen(self, holen: bool) -> None:
        from pyodide.ffi import create_once_callable

        fertig: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

        def zurueck(fehler: Any = None) -> None:
            if not fertig.done():
                fertig.set_result(fehler)

        self._fs.syncfs(holen, create_once_callable(zurueck))
        if fehler := await fertig:
            raise OSError(str(fehler))

    async def sperre(self, name: str) -> bool:
        from pyodide.ffi import create_proxy

        sperren = getattr(self._js.navigator, "locks", None)
        if not sperren:
            return True  # der Browser kennt keine Sperren — dann gilt der eine Tab
        erhalten: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

        def halter(sperre: Any = None) -> Any:
            bekommen = bool(sperre)
            if not erhalten.done():
                erhalten.set_result(bekommen)
            if not bekommen:
                return None
            # Ein Versprechen, das nie eingelöst wird: Die Sperre gilt, bis der Tab schließt.
            return self._js.Promise.new(create_proxy(lambda ja, nein: None))

        optionen = self._js.Object.new()
        optionen.ifAvailable = True
        sperren.request(name, optionen, create_proxy(halter))
        return await erhalten

    async def entfernen(self, pfad: str) -> None:
        from pyodide.ffi import create_once_callable

        # IDBFS hält seine Verbindung offen; solange sie steht, wartet das Löschen.
        offene = self._fs.filesystems.IDBFS.dbs
        if verbindung := self._js.Reflect.get(offene, pfad):
            verbindung.close()
            self._js.Reflect.deleteProperty(offene, pfad)
        fertig: asyncio.Future[str] = asyncio.get_running_loop().create_future()

        def ausgang(text: str) -> Callable[..., None]:
            def melden(*_: Any) -> None:
                if not fertig.done():
                    fertig.set_result(text)

            return create_once_callable(melden)

        anfrage = self._js.indexedDB.deleteDatabase(pfad)
        anfrage.onsuccess = ausgang("")
        anfrage.onerror = ausgang("Der Browser hat das Löschen abgelehnt.")
        anfrage.onblocked = ausgang("Ein anderer Tab hält den Speicher offen.")
        if text := await fertig:
            raise OSError(text)


__all__ = [
    "AN",
    "ANDERER_TAB",
    "AUS",
    "FEHLER",
    "GELOESCHT",
    "SPERRE",
    "TAKT_S",
    "TEXTE",
    "Browserspeicher",
    "PyodideZugang",
    "Zugang",
]
