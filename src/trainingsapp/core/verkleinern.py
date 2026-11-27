"""Videos verkleinern nach grobem Schema (Ben, 17.11.2026, `docs/plan_medien_reiter.md` §5):
„Ist es nicht möglich, z. B. Framerate, dpi, Auflösung usw. nach grobem Schema einzustellen mit
Angabe, wie groß das Video sein wird? Das konvertierte Video wird erstmal kopiert, das
ursprüngliche bleibt, damit man das neue anschauen kann und neu erstellen, falls es doch zu
unscharf ist.“

- **Schema** (`Schema`): Auflösung (kurze Seite 360 · 480 · 720 · 1080), Bildrate (15 · 24 · 30),
  Bildqualität (sparsam · normal · scharf), Ton (ohne · Sprache · normal · gut). Drei
  **Vorlagen** mit den Namen der Kamera der App (`VORLAGEN`): Klein, Mittel (die Vorgabe — passt
  auf Handy und Tablet), Groß.
- **Ziel** (`ziel`): was daraus für **dieses** Video wird — nie größer, schneller oder mit mehr
  Ton als das Original. Die Bitraten liegen fest; der Umwandler hält sie, darum trifft die
  Schätzung auf wenige Prozent (`Ziel.bytes`). Wäre das Ergebnis nicht kleiner, sagt
  `Ziel.nicht_kleiner` das vorher.
- **ffmpeg** (`ffmpeg_befehl`, `mit_ffmpeg`): der Weg am Rechner — H.264 und AAC, ohne
  Metadaten, Kopf vorn. Android nimmt dieselben Zahlen über den Umwandler der Fotoauswahl
  (`erweiterungen/flet_hochladen`), das iPhone später über einen eigenen Teil. ffmpeg wird nur
  aufgerufen, wenn es installiert ist — nie mitgeliefert.

**dpi gibt es bei Videos nicht:** Ein Bildschirm zeigt Pixel; was „dpi“ meint, ist hier die
Auflösung (kurze Seite). dpi zählt nur beim Drucken.

Dieses Modul kennt kein flet.
"""

from __future__ import annotations

import queue
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path
from typing import Final

from .anhaenge import Qualitaet
from .bewegungsbild import png_masse
from .dokument import gezeigte_masse
from .videoinfo import Videoinfo

#: Die Auflösungen zur Wahl — Pixel der kürzeren Seite
KURZE_SEITEN: Final = (360, 480, 720, 1080)
#: Bildbitrate je Auflösung bei 30 Bildern/s und Bildqualität „normal“ — 480, 720 und 1080 wie
#: die Stufen der Kamera (`core.anhaenge.Qualitaet`), 360 darunter
BASIS: Final[dict[int, int]] = {
    360: 250_000,
    480: Qualitaet.KLEIN.video_bitrate,
    720: Qualitaet.MITTEL.video_bitrate,
    1080: Qualitaet.GROSS.video_bitrate,
}
#: Die Bildraten zur Wahl und was sie an Bitrate brauchen (weniger Bilder, weniger Bit — nicht
#: im gleichen Maß, weil jedes Bild für sich mehr ändert)
BILDRATEN: Final = (15, 24, 30)
_BILDRATE_FAKTOR: Final[dict[int, float]] = {15: 0.6, 24: 0.85, 30: 1.0}

SPARSAM: Final = "sparsam"
NORMAL: Final = "normal"
SCHARF: Final = "scharf"
#: Bildqualität: ein Faktor auf die Bitrate
BILD: Final[dict[str, float]] = {SPARSAM: 0.7, NORMAL: 1.0, SCHARF: 1.5}
BILD_NAMEN: Final[dict[str, str]] = {SPARSAM: "sparsam", NORMAL: "normal", SCHARF: "scharf"}

OHNE: Final = "ohne"
SPRACHE: Final = "sprache"
GUT: Final = "gut"
#: Ton: Bitrate und Kanäle — „Sprache“ einkanalig, wie die Tonaufnahmen der App
TON: Final[dict[str, tuple[int, int]]] = {
    OHNE: (0, 0),
    SPRACHE: (48_000, 1),
    NORMAL: (Qualitaet.MITTEL.audio_bitrate, 2),
    GUT: (Qualitaet.GROSS.audio_bitrate, 2),
}
TON_NAMEN: Final[dict[str, str]] = {OHNE: "ohne", SPRACHE: "Sprache", NORMAL: "normal", GUT: "gut"}

#: Was der Container (MP4) über Bild und Ton hinaus braucht
CONTAINER: Final = 1.02


@dataclass(frozen=True, slots=True)
class Schema:
    """Was die Person wählt."""

    kurze_seite: int = 720
    bildrate: int = 30
    bild: str = NORMAL
    ton: str = NORMAL


#: Die Vorlagen — dieselben Namen wie bei der Kamera der App
VORLAGEN: Final[dict[str, Schema]] = {
    "klein": Schema(480, 24, NORMAL, SPRACHE),
    "mittel": Schema(720, 30, NORMAL, NORMAL),
    "gross": Schema(1080, 30, NORMAL, GUT),
}
VORLAGE_NAMEN: Final[dict[str, str]] = {"klein": "Klein", "mittel": "Mittel", "gross": "Groß"}
VORGABE: Final = "mittel"


#: Der **Bildausschnitt** (Ben, 19.11.2026: „Videos/Fotos sollen überall komprimiert und
#: gecroppt werden können“, `docs/plan_medien_einheitlich.md` §2.6): Anteile der Bildbreite bzw.
#: -höhe — links, oben, rechts, unten; das ganze Bild ist `GANZ`
Ausschnitt = tuple[float, float, float, float]
GANZ: Final[Ausschnitt] = (0.0, 0.0, 1.0, 1.0)
#: So viel bleibt je Richtung mindestens stehen (wie beim Dokument, `core.dokument.MIN_REST`)
MIN_AUSSCHNITT: Final = 0.1


def ausschnitt(links: float, oben: float, rechts: float, unten: float) -> Ausschnitt:
    """Ein gültiger Ausschnitt aus vier Anteilen — innerhalb des Bildes, je Richtung bleiben
    mindestens 10 %; fast das ganze Bild (jede Kante unter 1 %) *ist* das ganze.

    >>> ausschnitt(0.1, 0.2, 0.9, 0.8), ausschnitt(-1, 0, 2, 1), ausschnitt(0.005, 0, 1, 0.999)
    ((0.1, 0.2, 0.9, 0.8), (0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0))
    >>> ausschnitt(0.5, 0.5, 0.52, 0.4)
    (0.5, 0.5, 0.6, 0.6)
    """
    li, ob = min(max(links, 0.0), 1 - MIN_AUSSCHNITT), min(max(oben, 0.0), 1 - MIN_AUSSCHNITT)
    re, un = max(min(rechts, 1.0), li + MIN_AUSSCHNITT), max(min(unten, 1.0), ob + MIN_AUSSCHNITT)
    a = (round(li, 4), round(ob, 4), round(re, 4), round(un, 4))
    if a[0] < 0.01 and a[1] < 0.01 and a[2] > 0.99 and a[3] > 0.99:
        return GANZ
    return a


@dataclass(frozen=True, slots=True)
class Ziel:
    """Was das Schema aus einem bestimmten Video macht."""

    kurze_seite: int
    bildrate: int
    video_bitrate: int
    audio_bitrate: int
    #: 0 = ohne Ton
    kanaele: int
    #: Das Ergebnis wäre nicht kleiner als das Original (dessen Bitrate liegt schon darunter)
    nicht_kleiner: bool = False
    #: **Kürzen** (Ben, 18.11.2026: „Anfang oder Ende wegschneiden“,
    #: `docs/plan_medien_zeitpunkte.md` §4): ab hier … bis hier, in Sekunden ab dem Beginn des
    #: Originals; ``bis_s = 0``: bis zum Ende
    von_s: float = 0.0
    bis_s: float = 0.0
    #: Der Bildausschnitt (`Ausschnitt`) — nur am Rechner (ffmpeg)
    ausschnitt: Ausschnitt = GANZ
    #: Ein **Foto** statt eines Videos: die JPEG-Qualität (1–100), 0 = Video. Bei einem Foto
    #: heißt ``kurze_seite = 0``: Die Größe bleibt (nur zuschneiden bzw. neu packen)
    jpeg: int = 0

    @property
    def gekuerzt(self) -> bool:
        return self.von_s > 0 or self.bis_s > 0

    @property
    def zugeschnitten(self) -> bool:
        return self.ausschnitt != GANZ

    def dauer(self, dauer_s: float) -> float:
        """Wie lang die Kopie wird.

        >>> Ziel(720, 30, 1, 0, 0, von_s=5, bis_s=20).dauer(60), Ziel(720, 30, 1, 0, 0).dauer(60)
        (15.0, 60)
        >>> Ziel(720, 30, 1, 0, 0, von_s=50).dauer(60), Ziel(720, 30, 1, 0, 0, bis_s=90).dauer(60)
        (10.0, 60.0)
        """
        if not self.gekuerzt:
            return dauer_s
        ende = min(self.bis_s, dauer_s) if self.bis_s > 0 else dauer_s
        return max(0.0, float(ende) - self.von_s)

    def bytes(self, dauer_s: float) -> int:
        """Die geschätzte Größe: Bitrate mal Dauer (der gekürzten Kopie), dazu der Container.

        >>> Ziel(720, 30, 800_000, 64_000, 2).bytes(60)
        6609600
        >>> Ziel(720, 30, 800_000, 64_000, 2, von_s=30).bytes(60)
        3304800
        """
        dauer = self.dauer(dauer_s)
        return round((self.video_bitrate + self.audio_bitrate) / 8 * dauer * CONTAINER)

    def text(self) -> str:
        """„720p · 30 fps · Ton Sprache“.

        >>> Ziel(720, 30, 800_000, 0, 0).text(), Ziel(480, 24, 1, 48_000, 1).text()
        ('720p · 30 fps · ohne Ton', '480p · 24 fps · Ton einkanalig')
        """
        ton = "ohne Ton" if not self.kanaele else ("Ton einkanalig" if self.kanaele == 1 else "Ton")
        return f"{self.kurze_seite}p · {self.bildrate} fps · {ton}"


def zeit_text(sekunden: float) -> str:
    """„1:05“ bzw. mit Zehnteln „0:07,5“ — die Marken beim Kürzen.

    >>> zeit_text(65), zeit_text(7.5), zeit_text(0)
    ('1:05', '0:07,5', '0:00')
    """
    zehntel = round(max(0.0, sekunden) * 10)
    ganz, rest = divmod(zehntel, 10)
    text = f"{ganz // 60}:{ganz % 60:02d}"
    return f"{text},{rest}" if rest else text


def zeit_lesen(text: str) -> float | None:
    """Eine Marke aus dem Feld: „1:05“, „65“, „7,5“ — ``None``, wenn es keine Zeit ist.

    >>> zeit_lesen("1:05"), zeit_lesen("65"), zeit_lesen(" 0:07,5 "), zeit_lesen("7.5")
    (65.0, 65.0, 7.5, 7.5)
    >>> zeit_lesen("eins"), zeit_lesen("1:75"), zeit_lesen("-3"), zeit_lesen("")
    (None, None, None, 0.0)
    """
    text = text.strip().replace(",", ".")
    if not text:
        return 0.0
    teile = text.split(":")
    try:
        if len(teile) == 2:
            minuten, sekunden = int(teile[0]), float(teile[1])
            if minuten < 0 or not 0 <= sekunden < 60:
                return None
            return minuten * 60 + sekunden
        if len(teile) == 1:
            wert = float(teile[0])
            return wert if wert >= 0 else None
    except ValueError:
        return None
    return None


def schnitt(von_s: float, bis_s: float, dauer_s: float | None) -> tuple[float, float]:
    """Anfang und Ende, wie sie gelten: innerhalb des Videos, das Ende hinter dem Anfang (sonst
    bis zum Schluss), ein Ende am Schluss ist „kein Ende“ (0) — mindestens eine Sekunde bleibt.

    >>> schnitt(5, 20, 60), schnitt(5, 60, 60), schnitt(5, 3, 60), schnitt(70, 0, 60)
    ((5.0, 20.0), (5.0, 0.0), (5.0, 0.0), (59.0, 0.0))
    >>> schnitt(0, 0, 60), schnitt(10, 10.4, 60)
    ((0.0, 0.0), (10.0, 11.0))
    """
    von = float(max(0.0, von_s))
    if dauer_s:
        von = min(von, float(max(0.0, dauer_s - 1)))
    bis = float(bis_s)
    if bis <= von or (dauer_s and bis >= dauer_s):
        return von, 0.0
    return von, max(bis, von + 1)


def _basis(kurz: int) -> int:
    """Bildbitrate für eine kurze Seite — zwischen den Stufen nach der Pixelzahl.

    >>> _basis(720), _basis(540), _basis(200)
    (800000, 450000, 100000)
    """
    for stufe in KURZE_SEITEN:
        if kurz <= stufe:
            return max(100_000, round(BASIS[stufe] * (kurz / stufe) ** 2))
    return BASIS[KURZE_SEITEN[-1]]


def _bildrate_faktor(fps: int) -> float:
    """Zwischen 15, 24 und 30 Bildern/s geradlinig, darunter anteilig.

    >>> _bildrate_faktor(30), _bildrate_faktor(25), _bildrate_faktor(10)
    (1.0, 0.875, 0.4)
    """
    if fps in _BILDRATE_FAKTOR:
        return _BILDRATE_FAKTOR[fps]
    if fps < BILDRATEN[0]:
        return round(_BILDRATE_FAKTOR[BILDRATEN[0]] * fps / BILDRATEN[0], 4)
    for unten, oben in pairwise(BILDRATEN):
        if unten < fps < oben:
            a, b = _BILDRATE_FAKTOR[unten], _BILDRATE_FAKTOR[oben]
            return round(a + (b - a) * (fps - unten) / (oben - unten), 4)
    return 1.0


def ziel(
    schema: Schema,
    original: Videoinfo | None = None,
    original_bytes: int = 0,
    bild: Ausschnitt = GANZ,
) -> Ziel:
    """Was ``schema`` aus dem Video macht — nie größer, schneller oder mit mehr Ton als das
    Original. ``bild``: der Bildausschnitt — die kurze Seite ist dann höchstens die des
    Ausschnitts (es wird nie hochgerechnet).

    >>> hoch = Videoinfo(dauer_s=10, breite=1080, hoehe=1920, bildrate=30, ton=True)
    >>> z = ziel(VORLAGEN["gross"], hoch, 9_000_000, (0.0, 0.25, 1.0, 0.5))
    >>> z.kurze_seite, z.zugeschnitten
    (480, True)

    >>> v = Videoinfo(dauer_s=130, breite=1920, hoehe=1080, bildrate=60, ton=True)
    >>> z = ziel(VORLAGEN["mittel"], v, 84_000_000)
    >>> (z.kurze_seite, z.bildrate, z.video_bitrate, z.audio_bitrate, z.nicht_kleiner)
    (720, 30, 800000, 64000, False)
    >>> round(z.bytes(130) / 1e6, 1)
    14.3

    Ein kleines Original bleibt so klein; ohne Ton kein Ton:

    >>> klein = Videoinfo(dauer_s=60, breite=640, hoehe=480, bildrate=24, ton=False)
    >>> z = ziel(VORLAGEN["gross"], klein, 2_000_000)
    >>> (z.kurze_seite, z.bildrate, z.kanaele, z.nicht_kleiner)
    (480, 24, 0, True)
    """
    kurz = schema.kurze_seite
    fps = schema.bildrate
    ton, kanaele = TON.get(schema.ton, TON[NORMAL])
    if original is not None:
        if original.kurze_seite:
            kurz = min(kurz, original.kurze_seite)
        if bild != GANZ and original.breite and original.hoehe:
            # die kurze Seite des Ausschnitts, gerade (H.264 mit 4:2:0 braucht gerade Maße)
            breit = original.breite * (bild[2] - bild[0])
            hoch = original.hoehe * (bild[3] - bild[1])
            kurz = min(kurz, max(2, int(min(breit, hoch)) // 2 * 2))
        if original.bildrate:
            fps = min(fps, max(1, round(original.bildrate)))
        if not original.ton:
            ton, kanaele = 0, 0
    video = round(_basis(kurz) * BILD.get(schema.bild, 1.0) * _bildrate_faktor(fps))
    z = Ziel(kurz, fps, video, ton, kanaele, ausschnitt=bild)
    if original is not None and original.dauer_s and original_bytes:
        z = replace(z, nicht_kleiner=z.bytes(original.dauer_s) >= original_bytes)
    return z


def wahl(original: Videoinfo | None) -> tuple[tuple[int, ...], tuple[int, ...], bool]:
    """Was zur Wahl steht: Auflösungen und Bildraten nicht über dem Original (die kleinste
    bleibt immer), ob es Ton gibt.

    >>> wahl(Videoinfo(breite=1280, hoehe=720, bildrate=25, ton=False))
    ((360, 480, 720), (15, 24), False)
    >>> wahl(None)
    ((360, 480, 720, 1080), (15, 24, 30), True)
    """
    seiten: tuple[int, ...] = KURZE_SEITEN
    raten: tuple[int, ...] = BILDRATEN
    ton = True
    if original is not None:
        if original.kurze_seite:
            seiten = tuple(s for s in KURZE_SEITEN if s <= original.kurze_seite) or KURZE_SEITEN[:1]
        if original.bildrate:
            raten = tuple(r for r in BILDRATEN if r <= round(original.bildrate)) or BILDRATEN[:1]
        ton = original.ton
    return seiten, raten, ton


# -- Am Rechner: ffmpeg -------------------------------------------------------------------------


def ffmpeg() -> str | None:
    """Der Pfad zu ffmpeg — ``None``, wenn es nicht installiert ist."""
    return shutil.which("ffmpeg")


def ffmpeg_befehl(quelle: Path, ziel_pfad: Path, z: Ziel, programm: str = "ffmpeg") -> list[str]:
    """Der Aufruf: kurze Seite und Bildrate, H.264 mit der Bitrate des Ziels (Spitzen bis zum
    Anderthalbfachen), AAC oder kein Ton, **keine Metadaten** (Ort, Gerät, Kapitel), Kopf vorn
    (spielt, bevor die Datei ganz geladen ist); der Fortschritt kommt über die Standardausgabe.

    >>> b = ffmpeg_befehl(Path("a.mov"), Path("b.mp4"), Ziel(720, 24, 680_000, 0, 0))
    >>> b[b.index("-vf") + 1]
    "scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)',fps=24"
    >>> "-an" in b, b[b.index("-b:v") + 1], b[b.index("-map_metadata") + 1], b[-1]
    (True, '680000', '-1', 'b.mp4')
    >>> "-ss" in b or "-t" in b
    False

    Gekürzt (von 5 s bis 20 s): der Sprung vor der Eingabe, die Länge dahinter.

    >>> b = ffmpeg_befehl(Path("a.mov"), Path("b.mp4"), Ziel(720, 24, 1, 0, 0, von_s=5, bis_s=20))
    >>> b[b.index("-ss") : b.index("-ss") + 3], b[b.index("-t") + 1]
    (['-ss', '5.000', '-i'], '15.000')

    Mit Bildausschnitt: erst zuschneiden, dann auf die kurze Seite rechnen.

    >>> z = Ziel(480, 30, 1, 0, 0, ausschnitt=(0.1, 0.25, 0.9, 0.75))
    >>> b = ffmpeg_befehl(Path("a.mov"), Path("b.mp4"), z)
    >>> b[b.index("-vf") + 1].split(",scale")[0]
    'crop=iw*0.8000:ih*0.5000:iw*0.1000:ih*0.2500'
    """
    k = z.kurze_seite
    li, ob, re, un = z.ausschnitt
    schneiden = (
        f"crop=iw*{re - li:.4f}:ih*{un - ob:.4f}:iw*{li:.4f}:ih*{ob:.4f},"
        if z.zugeschnitten
        else ""
    )
    befehl = [
        programm,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        # Kürzen: vor der Eingabe springt ffmpeg zum Schlüsselbild davor und verwirft bis zum
        # Anfang — beim Neukodieren bildgenau; die Länge steht hinter der Eingabe
        *(["-ss", f"{z.von_s:.3f}"] if z.von_s > 0 else []),
        "-i",
        str(quelle),
        *(["-t", f"{z.bis_s - z.von_s:.3f}"] if z.bis_s > z.von_s else []),
        "-map",
        "0:v:0",
        *(["-map", "0:a:0?"] if z.kanaele else []),
        "-vf",
        f"{schneiden}scale='if(gt(iw,ih),-2,{k})':'if(gt(iw,ih),{k},-2)',fps={z.bildrate}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-b:v",
        str(z.video_bitrate),
        "-maxrate",
        str(round(z.video_bitrate * 1.5)),
        "-bufsize",
        str(z.video_bitrate * 2),
    ]
    if z.kanaele:
        befehl += ["-c:a", "aac", "-b:a", str(z.audio_bitrate), "-ac", str(z.kanaele)]
    else:
        befehl += ["-an"]
    befehl += [
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        str(ziel_pfad),
    ]
    return befehl


class Abgebrochen(Exception):
    """Das Verkleinern wurde abgebrochen — die halbe Datei ist weg."""


def fortschritt_aus(zeile: str, dauer_s: float | None) -> float | None:
    """Der Anteil (0…1) aus einer Zeile von ``-progress`` — ``None`` für andere Zeilen.

    >>> fortschritt_aus("out_time_us=65000000", 130), fortschritt_aus("speed=2x", 130)
    (0.5, None)
    >>> fortschritt_aus("out_time_us=N/A", 130), fortschritt_aus("out_time_us=9", None)
    (None, None)
    """
    if not dauer_s or not zeile.startswith("out_time_us="):
        return None
    try:
        us = int(zeile.split("=", 1)[1].strip())
    except ValueError:
        return None
    return max(0.0, min(1.0, us / 1e6 / dauer_s))


def mit_ffmpeg(
    quelle: Path,
    ziel_pfad: Path,
    z: Ziel,
    *,
    dauer_s: float | None = None,
    fortschritt: Callable[[float], None] | None = None,
    abbruch: threading.Event | None = None,
    programm: str | None = None,
) -> None:
    """Verkleinert ``quelle`` nach ``ziel_pfad`` — blockiert (im Thread aufrufen). Wirft
    `Abgebrochen` oder `RuntimeError` (mit der letzten Zeile von ffmpeg); die halbe Datei
    bleibt nie liegen.

    Der Abbruch gilt bis zuletzt, auch im zweiten Durchgang (``+faststart``), in dem ffmpeg
    keine Fortschrittszeilen mehr schreibt. Die Fehlerausgabe geht in eine Datei: Über eine
    Leitung, die erst am Ende gelesen wird, hingen ffmpeg und die App bei einem kaputten Video
    beide, sobald 64 KB Meldungen zusammenkommen (Prüfrunde 18.11.2026).
    """
    programm = programm or ffmpeg()
    if programm is None:
        raise RuntimeError("ffmpeg ist nicht installiert")
    befehl = ffmpeg_befehl(quelle, ziel_pfad, z, programm)

    def abgebrochen() -> bool:
        return abbruch is not None and abbruch.is_set()

    try:
        with (
            tempfile.TemporaryFile() as meldungen,
            subprocess.Popen(
                befehl,
                stdout=subprocess.PIPE,
                stderr=meldungen,
                text=True,
                encoding="utf-8",
                errors="replace",
            ) as proc,
        ):
            zeilen: queue.SimpleQueue[str | None] = queue.SimpleQueue()

            def lesen() -> None:
                assert proc.stdout is not None
                for zeile in proc.stdout:
                    zeilen.put(zeile)
                zeilen.put(None)

            leser = threading.Thread(target=lesen, name="ffmpeg-fortschritt", daemon=True)
            leser.start()
            try:
                while True:
                    if abgebrochen():
                        raise Abgebrochen
                    try:
                        zeile = zeilen.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if zeile is None:
                        break
                    anteil = fortschritt_aus(zeile, dauer_s)
                    if anteil is not None and fortschritt is not None:
                        fortschritt(anteil)
                while True:  # die Ausgabe ist zu — ffmpeg schreibt vielleicht noch die Datei
                    try:
                        code = proc.wait(timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        if abgebrochen():
                            raise Abgebrochen from None
                if abgebrochen():
                    raise Abgebrochen
                if code != 0:
                    meldungen.seek(0)
                    text = meldungen.read().decode("utf-8", errors="replace")
                    letzte = [x for x in text.splitlines() if x.strip()]
                    raise RuntimeError(letzte[-1] if letzte else "ffmpeg brach ab")
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                leser.join(timeout=5)
    except BaseException:
        ziel_pfad.unlink(missing_ok=True)
        raise
    if fortschritt is not None:
        fortschritt(1.0)


# -- Fotos (Ben, 19.11.2026: „Videos/Fotos sollen überall komprimiert und gecroppt werden
# können“, `docs/plan_medien_einheitlich.md` §2.6) ----------------------------------------------

#: „Volle Größe“ — nur zuschneiden bzw. neu packen, nichts kleiner rechnen
VOLL: Final = "voll"
#: Die Vorlagen für Fotos: die drei Stufen der Kamera (kurze Seite, JPEG-Qualität) und `VOLL`
BILD_VORLAGEN: Final[dict[str, tuple[int, int]]] = {
    **{q.value: (q.kurze_seite, q.jpeg_qualitaet) for q in Qualitaet},
    VOLL: (0, Qualitaet.GROSS.jpeg_qualitaet),
}
BILD_VORLAGE_NAMEN: Final[dict[str, str]] = {**VORLAGE_NAMEN, VOLL: "Volle Größe"}
#: Diese Fotos lassen sich verkleinern — die Kopie behält ihr Format (PNG bleibt PNG, mit
#: Durchsicht; dort zählt nur die Größe in Pixeln, eine Qualitätsstufe gibt es nicht)
BILD_ENDUNGEN: Final = ("jpg", "jpeg", "png")


def bild_masse_lesen(pfad: Path) -> tuple[int, int] | None:
    """Breite und Höhe eines Fotos, **wie man es sieht** (ein JPEG nach der Drehung aus seinem
    Kopf) — ``None``, wenn es sich nicht lesen lässt."""
    try:
        daten = pfad.read_bytes()
    except OSError:
        return None
    if daten.startswith(b"\xff\xd8"):
        try:
            return gezeigte_masse(daten)
        except ValueError:
            return None
    return png_masse(daten)


def bildziel(vorlage: str, breite: int, hoehe: int, bild: Ausschnitt = GANZ) -> Ziel:
    """Was eine Vorlage aus einem Foto von ``breite`` × ``hoehe`` macht — nie größer als das
    Original bzw. sein Ausschnitt (dann bleibt die Größe: ``kurze_seite = 0``).

    >>> z = bildziel("mittel", 3000, 4000)
    >>> z.kurze_seite, z.jpeg, bild_masse(z, 3000, 4000)
    (720, 85, (720, 960))
    >>> z = bildziel("gross", 3000, 4000, (0.0, 0.0, 0.25, 0.5))
    >>> z.kurze_seite, bild_masse(z, 3000, 4000)
    (0, (750, 2000))
    >>> bildziel("voll", 800, 600).kurze_seite, bildziel("quatsch", 800, 600).kurze_seite
    (0, 0)
    """
    kurz, jpeg = BILD_VORLAGEN.get(vorlage, BILD_VORLAGEN[VOLL])
    b, h = breite * (bild[2] - bild[0]), hoehe * (bild[3] - bild[1])
    if kurz and kurz >= int(min(b, h)):
        kurz = 0
    return Ziel(kurz, 0, 0, 0, 0, ausschnitt=bild, jpeg=jpeg)


def bild_masse(z: Ziel, breite: int, hoehe: int) -> tuple[int, int]:
    """Breite und Höhe der Kopie (gerundet; ffmpeg rechnet die lange Seite auf gerade Zahlen).

    >>> bild_masse(Ziel(480, 0, 0, 0, 0, jpeg=80), 4000, 3000)
    (640, 480)
    >>> bild_masse(Ziel(0, 0, 0, 0, 0, ausschnitt=(0.5, 0.0, 1.0, 1.0), jpeg=80), 4000, 3000)
    (2000, 3000)
    """
    li, ob, re, un = z.ausschnitt
    b, h = breite * (re - li), hoehe * (un - ob)
    if z.kurze_seite and min(b, h) > 0:
        faktor = z.kurze_seite / min(b, h)
        b, h = b * faktor, h * faktor
    return max(1, round(b)), max(1, round(h))


def _jpeg_q(qualitaet: int) -> int:
    """Die Stufe von ffmpeg (``-q:v``, 2 = beste … 31) zu einer JPEG-Qualität von 1–100 —
    eine Annäherung: 90 → 2, 85 → 4, 80 → 5.

    >>> [_jpeg_q(q) for q in (100, 90, 85, 80, 50, 1)]
    [2, 2, 4, 5, 12, 25]
    """
    return max(2, min(31, round((100 - qualitaet) / 4)))


def bild_befehl(quelle: Path, ziel_pfad: Path, z: Ziel, programm: str = "ffmpeg") -> list[str]:
    """Der Aufruf für ein Foto: erst zuschneiden, dann auf die kurze Seite rechnen, **keine
    Metadaten** (Ort, Gerät). Die Drehung aus dem Kopf eines JPEG wendet ffmpeg vorher an —
    der Ausschnitt gilt für das Bild, wie man es sieht. Das Format bestimmt die Endung von
    ``ziel_pfad``.

    >>> z = Ziel(720, 0, 0, 0, 0, ausschnitt=(0.1, 0.25, 0.9, 0.75), jpeg=85)
    >>> b = bild_befehl(Path("a.jpg"), Path("b.jpg"), z)
    >>> b[b.index("-vf") + 1]
    "crop=iw*0.8000:ih*0.5000:iw*0.1000:ih*0.2500,scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)'"
    >>> b[b.index("-q:v") + 1], b[b.index("-map_metadata") + 1], b[-1]
    ('4', '-1', 'b.jpg')

    Volle Größe ohne Ausschnitt: kein Filter; ein PNG hat keine Qualitätsstufe.

    >>> b = bild_befehl(Path("a.png"), Path("b.png"), Ziel(0, 0, 0, 0, 0, jpeg=85))
    >>> "-vf" in b, "-q:v" in b
    (False, False)
    """
    k = z.kurze_seite
    li, ob, re, un = z.ausschnitt
    filter_: list[str] = []
    if z.zugeschnitten:
        filter_.append(f"crop=iw*{re - li:.4f}:ih*{un - ob:.4f}:iw*{li:.4f}:ih*{ob:.4f}")
    if k:
        filter_.append(f"scale='if(gt(iw,ih),-2,{k})':'if(gt(iw,ih),{k},-2)'")
    jpeg = ziel_pfad.suffix.lower() in (".jpg", ".jpeg")
    return [
        programm,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(quelle),
        *(["-vf", ",".join(filter_)] if filter_ else []),
        "-frames:v",
        "1",
        "-update",
        "1",
        *(["-q:v", str(_jpeg_q(z.jpeg or 85))] if jpeg else []),
        "-map_metadata",
        "-1",
        str(ziel_pfad),
    ]


def frontbild_befehl(video: Path, ziel_pfad: Path, programm: str = "ffmpeg") -> list[str]:
    """Das erste Bild eines Videos als JPEG — das Frontbild zu einer verkleinerten Kopie.

    >>> frontbild_befehl(Path("a.mp4"), Path("a_bild.jpg"))[-7:]
    ['-frames:v', '1', '-update', '1', '-q:v', '4', 'a_bild.jpg']
    """
    return [
        programm,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-update",
        "1",
        "-q:v",
        "4",
        str(ziel_pfad),
    ]


def standbild_befehl(
    video: Path, ziel_pfad: Path, sekunden: float, programm: str = "ffmpeg"
) -> list[str]:
    """Das Bild an der Stelle ``sekunden`` als JPEG, kurze Seite höchstens 720 — das
    **Titelbild** aus dem Video (Ben, 27.11.2026, `docs/plan_kurs_medien_ansicht.md` §3.3).

    >>> b = standbild_befehl(Path("a.mp4"), Path("t.jpg"), 12.5)
    >>> b[b.index("-ss") + 1], b[-1]
    ('12.500', 't.jpg')
    >>> standbild_befehl(Path("a.mp4"), Path("t.jpg"), -3)[6]
    '0.000'
    """
    return [
        programm,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(sekunden, 0.0):.3f}",
        "-y",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-update",
        "1",
        "-vf",
        "scale='if(gt(iw,ih),-2,min(720,iw))':'if(gt(iw,ih),min(720,ih),-2)'",
        "-q:v",
        "4",
        str(ziel_pfad),
    ]


def einmal_mit_ffmpeg(befehl: list[str], ziel_pfad: Path, *, wartezeit_s: float = 120) -> None:
    """Ein kurzer Aufruf (Foto, Frontbild) — blockiert (im Thread aufrufen). Wirft
    `RuntimeError` mit der letzten Zeile von ffmpeg; die halbe Datei bleibt nie liegen."""
    try:
        lauf = subprocess.run(
            befehl,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=wartezeit_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as fehler:
        ziel_pfad.unlink(missing_ok=True)
        raise RuntimeError(str(fehler)) from fehler
    if lauf.returncode != 0 or not ziel_pfad.is_file():
        ziel_pfad.unlink(missing_ok=True)
        text = lauf.stderr.decode("utf-8", errors="replace")
        letzte = [x for x in text.splitlines() if x.strip()]
        raise RuntimeError(letzte[-1] if letzte else "ffmpeg brach ab")


__all__ = [
    "BASIS",
    "BILD",
    "BILDRATEN",
    "BILD_ENDUNGEN",
    "BILD_NAMEN",
    "BILD_VORLAGEN",
    "BILD_VORLAGE_NAMEN",
    "GANZ",
    "GUT",
    "KURZE_SEITEN",
    "MIN_AUSSCHNITT",
    "NORMAL",
    "OHNE",
    "SCHARF",
    "SPARSAM",
    "SPRACHE",
    "TON",
    "TON_NAMEN",
    "VOLL",
    "VORGABE",
    "VORLAGEN",
    "VORLAGE_NAMEN",
    "Abgebrochen",
    "Ausschnitt",
    "Schema",
    "Ziel",
    "ausschnitt",
    "bild_befehl",
    "bild_masse",
    "bild_masse_lesen",
    "bildziel",
    "einmal_mit_ffmpeg",
    "ffmpeg",
    "ffmpeg_befehl",
    "fortschritt_aus",
    "frontbild_befehl",
    "mit_ffmpeg",
    "schnitt",
    "standbild_befehl",
    "wahl",
    "zeit_lesen",
    "zeit_text",
    "ziel",
]
