"""``trainingsapp-paket verkleinern`` — die großen Videos einer Paketdatei am Rechner verkleinern
(Ben, 17.11.2026, `docs/plan_medien_reiter.md` §5: „am Rechner ffmpeg im Paketwerkzeug“).

Für den Rückweg vom Handy: Am Telefon ein Paket bauen und exportieren, am Laptop die Videos
kleiner machen, dann weitergeben oder einlesen (``einlesen``). Gelesen wird die **ZIP** aus dem
Export der App — ein TOML nennt seine Dateien nur beim Bauen (erst ``bauen``, dann die ZIP
verkleinern). Verkleinert wird jedes **große** Video
(`core.medien_uebersicht.gross`: mehr als „Mittel“ mit einem Viertel Spielraum) — mit
``alle`` jedes — nach einer Vorlage (`core.verkleinern.VORLAGEN`, Vorgabe Mittel), mit ffmpeg.

**Das Original bleibt:** Die neue Paketdatei entsteht in einem eigenen Ordner (Vorgabe
``verkleinert/`` neben der alten). Jede Datei darin ist bereinigt und heißt nach ihrer neuen
Prüfsumme; alle Verweise ziehen mit (`core.paketdatei.export_schreiben` — derselbe Weg wie der
Export der App). Die Version des Pakets bleibt — wer es veröffentlicht, hebt sie vorher an.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from trainingsapp.core import videoinfo
from trainingsapp.core.material import VIDEO
from trainingsapp.core.medien_uebersicht import Dateiinfo, gross
from trainingsapp.core.paketdatei import export_schreiben, paket_oeffnen
from trainingsapp.core.paketmedien import dateiname, groesse_text
from trainingsapp.core.verkleinern import VORGABE, VORLAGEN, ffmpeg, mit_ffmpeg, ziel

#: Endungen, die als Video verkleinert werden (M4A ist Ton)
VIDEO_ENDUNGEN = frozenset({"mp4", "m4v", "mov"})


def verkleinern(
    quelle: Path,
    ordner: Path,
    *,
    vorlage: str = VORGABE,
    alle: bool = False,
    schreiben: bool = True,
) -> tuple[list[str], list[str]]:
    """Verkleinert die Videos von ``quelle`` in eine neue Paketdatei in ``ordner`` —
    ``(Zeilen, Fehler)``. ``schreiben=False``: nur zeigen, was geschähe (ohne ffmpeg)."""
    zeilen: list[str] = []
    if vorlage not in VORLAGEN:
        return zeilen, [f"Unbekannte Vorlage „{vorlage}“ — {', '.join(sorted(VORLAGEN))}"]
    if schreiben and ffmpeg() is None:
        return zeilen, ["ffmpeg ist nicht installiert — es wird nur aufgerufen, nie mitgeliefert"]
    if ordner.resolve() == quelle.parent.resolve():
        return zeilen, [
            "Der Ordner der neuen Datei darf nicht der der alten sein (das Original bleibt)"
        ]
    with tempfile.TemporaryDirectory() as arbeit_str:
        arbeit = Path(arbeit_str)
        inhalt = paket_oeffnen(quelle)
        try:
            dateien: dict[str, Path] = {}
            vorher = nachher = 0
            for name, medium in sorted(inhalt.medien.items()):
                datei = arbeit / (dateiname(name) or name.replace("/", "_"))
                medium.kopieren(datei)
                dateien[name] = datei
                endung = datei.suffix.lower().lstrip(".")
                if endung not in VIDEO_ENDUNGEN:
                    continue
                groesse = datei.stat().st_size
                info = videoinfo.lesen(datei)
                kurz = f"{name[-16:]} ({info.text() if info else '?'}, {groesse_text(groesse)})"
                if not alle and not gross(VIDEO, Dateiinfo(groesse, video=info)):
                    zeilen.append(f"bleibt: {kurz} — nicht groß")
                    continue
                z = ziel(VORLAGEN[vorlage], info, groesse)
                if z.nicht_kleiner:
                    zeilen.append(f"bleibt: {kurz} — wäre nicht kleiner")
                    continue
                schaetzung = (
                    f"etwa {groesse_text(z.bytes(info.dauer_s))}" if info and info.dauer_s else "?"
                )
                if not schreiben:
                    zeilen.append(f"würde verkleinern: {kurz} → {z.text()}, {schaetzung}")
                    continue
                neu = arbeit / f"klein_{datei.name}"
                mit_ffmpeg(datei, neu, z, dauer_s=info.dauer_s if info else None)
                dateien[name] = neu
                vorher += groesse
                nachher += neu.stat().st_size
                zeilen.append(
                    f"verkleinert: {kurz} → {z.text()}, {groesse_text(neu.stat().st_size)}"
                )
            if not schreiben:
                return zeilen, []
            if not inhalt.medien:
                return zeilen, ["Die Paketdatei bringt keine Dateien mit — nichts zu verkleinern"]
            ordner.mkdir(parents=True, exist_ok=True)
            ziel_datei, meldungen = export_schreiben(
                ordner,
                inhalt.paket,
                inhalt.uebungen,
                plaene=inhalt.plaene,
                kurse=inhalt.kurse,
                ergaenzungen=inhalt.ergaenzungen,
                quelle=dateien.get,
            )
        finally:
            inhalt.raeumen()
    zeilen.extend(meldungen)
    if vorher:
        zeilen.append(f"Videos zusammen: {groesse_text(vorher)} → {groesse_text(nachher)}")
    version = inhalt.paket.version
    zeilen.append(
        f"Neue Paketdatei: {ziel_datei} — die Version bleibt {version}; vor dem "
        "Veröffentlichen anheben"
        if version is not None
        else f"Neue Paketdatei: {ziel_datei}"
    )
    return zeilen, []


__all__ = ["VIDEO_ENDUNGEN", "verkleinern"]
