"""Die dezente sRPE-Zeile nach einer Einheit (Ben, 29.10.2026, Frage 8) — zum Tag
(`srpe_zeile`, Tagesfeld) und seit dem 10.11.2026 zum Workout (`workout_srpe_zeile`).

Ben: „sRPE soll nach der Einheit sichtbar eingetragen werden können und wenn, kommt das als
Tagesfeld mit, aber kein Dialog. Nach dem Ende der Einheit steht das oben/unten einfach
ausfüllbar mit dabei.“ — Eine Linie mit den Stufen 0–10 (CR10), die in das feste Tagesfeld
„Anstrengung (sRPE)“ schreibt (`core.tagesfelder.STANDARD_SRPE`, einmal am Tag, Tageswert
Höchster). Zusammen mit den Minuten der Einheit ergibt das die sRPE-Last
(`core.hf_verlauf.tageslasten`). Keine Deutung, keine Vorgabe.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any

import flet as ft

from trainingsapp.core import tagesfelder as tf
from trainingsapp.core.workout_eintrag import SRPE
from trainingsapp.ui.components.skala_linie import SkalaLinie, skala_feld

#: Die Stufen der CR10-Skala mit Kurzwort (Foster 2001), nur als Hilfe unter der Linie
STUFEN: tuple[tuple[int, str], ...] = (
    (0, "Ruhe"),
    (1, "sehr leicht"),
    (2, "leicht"),
    (3, "moderat"),
    (4, "etwas anstrengend"),
    (5, "anstrengend"),
    (6, ""),
    (7, "sehr anstrengend"),
    (8, ""),
    (9, ""),
    (10, "maximal"),
)


def srpe_feld(state: Any) -> tf.Tagesfeld | None:
    """Das feste Tagesfeld „Anstrengung (sRPE)“ des aktiven Profils — auch ausgeschaltet."""
    return tf.standardfeld(state.tagesfelder.alle(state.profil.id), tf.STANDARD_SRPE)


def srpe_wert(state: Any, tag: date) -> int | None:
    """Der eingetragene Wert des Tags, falls vorhanden."""
    feld = srpe_feld(state)
    if feld is None:
        return None
    werte = [w for w in state.tageswerte.am_tag(state.profil.id, tag) if w.feld_id == feld.id]
    ziel = tf.einmal_ziel(werte, "")
    if ziel is None:
        return None
    wert = ziel.result.get(tf.WERT)
    try:
        return None if wert is None else int(wert)
    except (TypeError, ValueError):
        return None


def srpe_zeile(
    page: Any, state: Any, tag: date, *, danach: Callable[[], None] | None = None
) -> ft.Control | None:
    """Die Zeile zum **Tag**: Titel und die Linie 0–10 mit Wertefenster. ``None``, wenn es das
    Feld nicht gibt (gelöscht gab es nur vor Migration 034)."""
    feld = srpe_feld(state)
    if feld is None:
        return None

    def schreiben(stufe: int) -> None:
        state.tageswerte.einmal_setzen(feld, tag, wert=stufe)

    return stufen_zeile(srpe_wert(state, tag), schreiben, danach=danach, worte=WORTE)


def workout_srpe_zeile(
    state: Any,
    einheit_id: str,
    *,
    danach: Callable[[], None] | None = None,
    felder: Sequence[str] = (),
) -> ft.Control:
    """Die Zeile zum **Workout** (Ben, 10.11.2026, `docs/plan_workout_eintrag.md`): Die
    Anstrengung gehört zum Durchlauf, nicht zum Tag — sie steht im Workout-Eintrag
    (`EinheitRepo.workout_eintragen`), mehrere Workouts am Tag tragen je ihre eigene, und das
    Tagesfeld bleibt, wie es ist. Nachtragen und Ändern jederzeit."""

    return workout_skala_zeile(
        state,
        einheit_id,
        SRPE,
        danach=danach,
        felder=felder,
        hinweis="0 Ruhe · 10 maximal — wie anstrengend war das Workout insgesamt?",
        worte=WORTE,
    )


def workout_skala_zeile(
    state: Any,
    einheit_id: str,
    key: str,
    *,
    titel: str = "Anstrengung (sRPE)",
    hinweis: str = "0–10",
    danach: Callable[[], None] | None = None,
    felder: Sequence[str] = (),
    worte: Mapping[int, str] | None = None,
) -> ft.Control:
    """Eine Skala 0–10 am Workout — die Anstrengung oder eine eigene (`core.workout_eintrag.
    feld_key`). Das Wertefenster leeren nimmt den Wert zurück (Nachtragen: ein Vertipper
    soll nicht stehen bleiben). ``felder``: die Skalen des Workouts von jetzt, für
    die Kopie der Felder am Eintrag."""

    def schreiben(stufe: int | None) -> None:
        state.einheiten.workout_eintragen(einheit_id, result={key: stufe}, felder=felder)

    return stufen_zeile(
        state.einheiten.workout_wert(einheit_id).wert(key),
        schreiben,
        danach=danach,
        titel=titel,
        hinweis=hinweis,
        leerbar=True,
        worte=worte,
        kennung=key,
    )


def stufen_zeile(
    wert: int | None,
    schreiben: Callable[[Any], None],
    *,
    danach: Callable[[], None] | None = None,
    titel: str = "Anstrengung (sRPE)",
    hinweis: str = "0 Ruhe · 10 maximal — wie anstrengend war die Einheit insgesamt?",
    leerbar: bool = False,
    worte: Mapping[int, str] | None = None,
    kennung: Any = "srpe",
) -> ft.Control:
    """Titel, Hinweis und die Skala 0–10 als Linie mit Wertefenster (Ben, 28.11.2026 —
    vorher elf Knöpfe). ``schreiben`` bekommt die Stufe; mit ``leerbar`` nimmt das geleerte
    Fenster sie zurück (``schreiben(None)``), sonst bleibt der Wert stehen. ``worte``: das
    Kurzwort der Stufe unter der Linie („5 · anstrengend“)."""
    stand: dict[str, int | None] = {"wert": wert}

    def gemeldet(x: float | int | None) -> None:
        if x is None and not leerbar:
            linie.setzen(stand["wert"])  # hier lässt sich nichts zurücknehmen
            return
        neu = None if x is None else int(x)
        schreiben(neu)
        stand["wert"] = neu
        if danach is not None:
            danach()

    linie = SkalaLinie(skala_feld(0, 10), wert, gemeldet, worte=worte, data=("stufe", kennung))
    return ft.Column(
        spacing=4,
        tight=True,
        controls=[
            # Titel über dem Hinweis: Nebeneinander nahm der lange Hinweis die ganze Breite,
            # der Titel brach Buchstabe für Buchstabe um (Web-Foto „Workout fertig“ bei 412 px,
            # 17.11.2026)
            ft.Text(titel, size=12, opacity=0.8),
            ft.Text(hinweis, size=11, opacity=0.55),
            linie.control,
        ],
    )


#: Die Kurzwörter der CR10-Stufen für die Linie
WORTE: dict[int, str] = {stufe: wort for stufe, wort in STUFEN if wort}


__all__ = [
    "STUFEN",
    "WORTE",
    "srpe_feld",
    "srpe_wert",
    "srpe_zeile",
    "stufen_zeile",
    "workout_skala_zeile",
    "workout_srpe_zeile",
]
