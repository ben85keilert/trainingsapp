"""Zustand der Zählzeile ohne flet — Zahl, Korrektur, Satz und Phase des Zählens.

Ben, 4.11.2026 (``docs/plan_beschleunigung.md`` §4.2, §5.2): Während der Sensor zählt, steht
in der Karte „Eintragen“ groß die Zahl, links −1, rechts +1, klein darunter „Sensor 11 · +1 ·
Prototyp“; Info- und Laufleiste zeigen „Zählen · Kniebeuge · 12“, die Marken-Leiste im
Diagnosemodus „Sensor 11“ neben der Zahl der Tipps. Was dort steht, hängt nicht am Bildschirm —
wie `components.marken_stand` liegt es darum hier ohne ``import flet`` (auch nicht in einer
Funktion): Die CI testet es flet-frei, und die Uhr am Band nimmt später denselben Weg.

- Wann es die Zählzeile gibt (`sichtbar`, `geraet_kann_zaehlen`, `zaehlen_an`) und wie ihr
  Knopf heißt (`knopf`).
- Welcher Zähl-Teil zu einer Übung gehört (`passt`, `zaehl_teil`).
- Die Texte: `zahl_text` (die große Zahl), `klein_text` (darunter), `kurz_text` (Laufleiste und
  Benachrichtigung), `leisten_text` (Teile der Laufleiste), `sensor_text` (Marken-Leiste).
  Atmung (A3): nur Atmung ist die große Zahl die der Atemzüge, darunter „Atmung 14 · 12/min ▲ ·
  Prototyp“; bei Wdh + Atmung bleibt die Zahl die der Wiederholungen, und eine Zeile
  `atem_text` („Atmung 12/min ▲“) kommt dazu (`atemzuege`, `atem_rate_text`, `atem_phase`).
- ±1 (`korrigieren`) und das Nachziehen (`ZaehlAnzeige`, `anmelden`, `nachziehen`): nur Texte,
  nie neu gebaute Knöpfe — ein Tipp ginge sonst verloren.

Die Controls legt die Zählzeile (flet) in einer `ZaehlAnzeige` ab und meldet sie an; vor ±1
ruft sie ``ohne_auto_update()`` (V1) — das gehört zu flet und bleibt dort. Starten, Beenden und
Eintragen führt `ui.uebung_lauf`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from trainingsapp.core import atem_protokoll
from trainingsapp.core import zaehlen as zl
from trainingsapp.core.einheit import Zustand
from trainingsapp.core.kurzcode import katalog_aufloesen
from trainingsapp.core.result_spec import basis_key
from trainingsapp.core.zaehlen_eintrag import ende_text
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.plan_ablauf import PlanAblaufBaustein
from trainingsapp.devices.profiles import CAP_PMD_ACC
from trainingsapp.devices.zaehlen import (
    PHASE_ATMUNG,
    PHASE_ENDE,
    PHASE_PAUSE,
    PHASE_SAMMELT,
    PHASE_STARTET,
    ZaehlBaustein,
)

if TYPE_CHECKING:
    import flet as ft

    from trainingsapp.core.models import Exercise, PlanItem
    from trainingsapp.devices.einheit import UebungKontext

#: Unter diesem Namen frischt die Einheit die Zählzeilen auf (``state.einheit_beobachter``)
BEOBACHTER = "zaehl_stand"


# ---------------------------------------------------------------------------
# Wann es die Zählzeile gibt
# ---------------------------------------------------------------------------


def geraet_kann_zaehlen(lauf: Any) -> bool:
    """Ob das verbundene Gerät einen Beschleunigungssensor hat (heute H10 und Verity Sense,
    §4.1) — verbunden genügt, eine Aufnahme braucht es nicht.

    >>> from types import SimpleNamespace as NS
    >>> from trainingsapp.devices.profiles import POLAR_H10, UHR_BROADCAST
    >>> verbunden = NS(verbindung=Verbindung.VERBUNDEN)
    >>> geraet_kann_zaehlen(NS(status=verbunden, profil=POLAR_H10))
    True
    >>> geraet_kann_zaehlen(NS(status=verbunden, profil=UHR_BROADCAST)), geraet_kann_zaehlen(None)
    (False, False)
    >>> geraet_kann_zaehlen(NS(status=NS(verbindung=Verbindung.GETRENNT), profil=POLAR_H10))
    False
    """
    if lauf is None:
        return False
    status = getattr(lauf, "status", None)
    if status is None or status.verbindung != Verbindung.VERBUNDEN:
        return False
    profil = getattr(lauf, "profil", None)
    return profil is not None and bool(profil.kann(CAP_PMD_ACC))


def zaehlen_an(uebung: Exercise, item: PlanItem | None = None) -> bool:
    """Ob an der Übung „Wiederholungen“ oder „Atmung“ an ist (Karte „Beschleunigungssensor“) —
    mit ``item`` so, wie die Planübung sie sieht: Wiederholungen nur, wenn sie ein
    Wiederholungsfeld anbietet (`core.zaehlen.wiederholungen_an`).

    >>> from trainingsapp.core.models import Exercise, PlanItem
    >>> from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    >>> zaehlen_an(Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps")])))
    True
    >>> planke = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("hold")]))
    >>> zaehlen_an(planke), zaehlen_an(planke, PlanItem(felder=["hold", "reps"]))
    (False, True)
    >>> kniebeuge = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("reps")]))
    >>> zaehlen_an(kniebeuge, PlanItem(felder=[]))  # nur abhaken
    False
    """
    return zl.wiederholungen_an(uebung, item) or zl.atmung_an(uebung)


def knopf(uebung: Exercise, item: PlanItem | None = None) -> str:
    """Der Knopf der Zählzeile — „Wdh. zählen“, „Atmung erfassen“, „Wdh. zählen · Atmung“
    (mit ``item``: wie die Planübung sie sieht).

    >>> from trainingsapp.core.models import Exercise
    >>> knopf(Exercise(typen=["Atmung"]))
    'Atmung erfassen'
    """
    return zl.knopf_text(zl.wiederholungen_an(uebung, item), zl.atmung_an(uebung))


def im_plan_ablauf(state: Any) -> bool:
    """Läuft gerade ein Plan-Ablauf? Darin zählt der Sensor noch nicht (Plan §13: der Ablauf
    trägt je Übung selbst ein, `ui.plan_ablauf.nach_der_uebung`) — einen Knopf, der dort nur
    „Es läuft schon eine Einheit“ meldete, gibt es darum nicht.

    >>> from types import SimpleNamespace as NS
    >>> im_plan_ablauf(NS(einheit=None))
    False
    """
    e = getattr(state, "einheit", None)
    return e is not None and e.laeuft and isinstance(e.teil("plan"), PlanAblaufBaustein)


def bereitgestellt(state: Any) -> bool:
    """Steht eine Einheit bereit (Infoleiste „Bereitgestellt“, noch nicht gestartet)? Dann
    zählt der Sensor nicht (`ui.uebung_lauf.zaehlen_starten`: „erst oben starten oder
    leeren“) — einen Knopf, der nur das meldete, gibt es darum nicht.

    >>> from types import SimpleNamespace as NS
    >>> bereitgestellt(NS(einheit=None))
    False
    """
    e = getattr(state, "einheit", None)
    return e is not None and e.zustand in (Zustand.VORBEREITUNG, Zustand.BEREIT)


def sichtbar(
    state: Any, uebung: Exercise, *, item: PlanItem | None = None, nachtrag: Any = None
) -> bool:
    """Ob die Karte „Eintragen“ den Knopf der Zählzeile zeigt: nicht beim Nachtragen, an der
    (Plan-)Übung ein Schalter an, ein Gerät mit Beschleunigungssensor verbunden (P118: sonst
    gibt es weder Knopf noch ±1), kein Plan-Ablauf im Gang (`im_plan_ablauf`) und nichts
    bereitgestellt (`bereitgestellt`)."""
    return (
        nachtrag is None
        and zaehlen_an(uebung, item)
        and geraet_kann_zaehlen(getattr(state, "messlauf", None))
        and not im_plan_ablauf(state)
        and not bereitgestellt(state)
    )


# ---------------------------------------------------------------------------
# Welcher Zähl-Teil
# ---------------------------------------------------------------------------


def passt(kontext: UebungKontext, uebung_id: str, item_id: str | None = None) -> bool:
    """Gehört ein Lauf zu dieser (Plan-)Übung? Dieselbe Übung — und mit Planübung dieselbe
    oder eine ohne Planübung (wie die Uhr in der Übung, `components.uhr.laufende`).

    >>> from trainingsapp.devices.einheit import UebungKontext
    >>> k = UebungKontext("u1", "Kniebeuge", "p1", "i1")
    >>> passt(k, "u1"), passt(k, "u1", "i1"), passt(k, "u1", "i2"), passt(k, "u2")
    (True, True, False, False)
    >>> passt(UebungKontext("u1", "Kniebeuge"), "u1", "i2")
    True
    """
    if kontext.uebung_id != uebung_id:
        return False
    return item_id is None or kontext.item_id in (None, item_id)


def zaehl_teil(
    state: Any, uebung_id: str, item_id: str | None = None, *, nur_aktiv: bool = False
) -> ZaehlBaustein | None:
    """Der Zähl-Teil dieser Übung in der laufenden Einheit — auch, wenn er schon endete und
    die Uhr weiterläuft; mit ``nur_aktiv`` nur, solange er zählt."""
    e = getattr(state, "einheit", None)
    if e is None or not e.laeuft:
        return None
    z = e.teil("zaehlen")
    if not isinstance(z, ZaehlBaustein) or not passt(z.kontext, uebung_id, item_id):
        return None
    if nur_aktiv and not z.aktiv:
        return None
    return z


def zaehlt_in(
    state: Any, uebung_id: str, item_id: str | None, feld_key: str
) -> ZaehlBaustein | None:
    """Der Zähl-Teil, der gerade in dieses Feld dieser (Plan-)Übung zählt — sonst ``None``."""
    z = zaehl_teil(state, uebung_id, item_id, nur_aktiv=True)
    if z is None or not z.wdh:
        return None
    if z.feld != feld_key and not (z.feld is None and basis_key(feld_key) == zl.WDH_ART):
        return None
    return z


def zaehlt_der_sensor(state: Any, uebung_id: str, item_id: str | None, feld_key: str) -> bool:
    """Zählt der Sensor gerade in dieses Feld dieser (Plan-)Übung? Dann gibt es dafür keine
    Eingabe von Hand (P122, Plan §4.4: entweder die Person oder der Sensor — „die Person
    korrigiert höchstens mit ±1“); ein Chip „+10“ hängte sonst einen zweiten Satz neben den
    gezählten. Beides zugleich gibt es nur zum Prüfen, im Diagnosemodus (Abschnitt 6) — dort
    ``False`` (ein Satz von Hand beendet dann den des Sensors, `von_hand_eingetragen`)."""
    if zaehlt_in(state, uebung_id, item_id, feld_key) is None:
        return False
    lauf = getattr(state, "messlauf", None)
    return not (lauf is not None and getattr(lauf, "diagnose_aktiv", False))


def von_hand_eingetragen(state: Any, uebung_id: str, item_id: str | None, feld_key: str) -> bool:
    """Diagnosemodus: Die Person trug eben einen Satz von Hand in das Feld ein, in das der
    Sensor zählt (ein Chip) — sein Satz gilt damit als eingetragen und endet hier
    (`ZaehlBaustein.von_hand`); am Ende trägt der Sensor ihn nicht noch einmal ein. Aufzurufen
    nach der Notiz zum Satz (deren Vergleich nimmt noch den Satz des Sensors), je Satz einmal
    — „2 × 6“ sind zwei. Davor `ui.uebung_lauf.vor_dem_satz_von_hand`. ``False``, wenn der
    Sensor dort nicht zählt."""
    z = zaehlt_in(state, uebung_id, item_id, feld_key)
    return z is not None and z.von_hand()


def zaehl_notizen(state: Any) -> contextlib.AbstractContextManager[None]:
    """Die Notizen zu Sätzen, die der Sensor zählte, kommen (`Messlauf.zaehl_notizen`): Im
    Diagnosemodus stehen ihre Zeilen ``satz`` und Vergleiche schon im Mitschnitt — die Notiz
    schreibt keine zweite. Ohne Messlauf ein leerer Rahmen."""
    haken = getattr(getattr(state, "messlauf", None), "zaehl_notizen", None)
    return haken() if callable(haken) else contextlib.nullcontext()


# ---------------------------------------------------------------------------
# Texte
# ---------------------------------------------------------------------------


def zahl_text(z: ZaehlBaustein) -> str:
    """Die große Zahl: Sensor plus Korrektur des Satzes, nie unter 0 (`core.zaehlen.anzeige`)
    — nur Atmung: die Atemzüge."""
    return str(z.atemzuege if not z.wdh else z.wert)


def atemzuege(z: ZaehlBaustein) -> int:
    """Atemzüge, Sensor plus Korrektur (`ZaehlBaustein.atemzuege`)."""
    return z.atemzuege


def atem_rate_text(z: ZaehlBaustein) -> str:
    """„12/min“ — „–“, solange kein gültiges Fenster eine Rate nannte."""
    return zl.rate_text(z.atem_rate)


def atem_phase(z: ZaehlBaustein) -> str:
    """▲ beim Einatmen, ▼ beim Ausatmen, leer sonst."""
    return zl.phase_pfeil(z.atem_phase)


def atem_zeile(z: ZaehlBaustein) -> str:
    """„12/min ▲ · Spanne 58 ms“ — Rate, Phase und, mit Aufnahme, die Atemspanne des letzten
    Atemzugs (B2, `ZaehlBaustein.atem_spanne_ms`; `core.zaehlen.atem_text`)."""
    return zl.atem_text(z.atem_rate, z.atem_phase, getattr(z, "atem_spanne_ms", None))


def atem_text(z: ZaehlBaustein) -> str:
    """Die Zeile der Atem-Spur bei Wdh + Atmung: „Atmung 12/min ▲ · Spanne 58 ms“ — leer ohne
    „Atmung“ oder solange keine Proben kamen; nach dem Ende die Atemzüge."""
    if not (z.wdh and z.atem) or z.atem_sensor is None:
        return ""
    if z.phase == PHASE_ENDE:
        return f"Atmung {z.atemzuege} · {atem_rate_text(z)}"
    return f"Atmung {atem_zeile(z)}"


def _atem_klein(z: ZaehlBaustein) -> str:
    """Nur Atmung, unter der Zahl: „Atmung 14 · 12/min ▲ · Prototyp“, mit Korrektur „Atmung 13
    · +1 · 12/min ▲ · Prototyp“; „…“, bis die ersten Phasen da sind."""
    sensor, korrektur = z.atem_sensor, z.atem_korrektur
    if sensor is None and not korrektur:
        return "…"
    zahl = f"Atmung {'…' if sensor is None else sensor}"
    if korrektur:
        zahl = f"{zahl} · {zl.mit_vorzeichen(korrektur)}"
    return f"{zahl} · {atem_zeile(z)} · Prototyp"


def klein_text(z: ZaehlBaustein) -> str:
    """Die kleine Zeile unter der Zahl: „Sensor 11 · +1 · Prototyp“ — bis die ersten Proben
    kommen „Sensor startet …“, ohne erkennbare Periode „…“; in der Pause des Timers „Pause“
    (davor, was der letzte Satz zählte), nach dem Ende der Grund. Nur Atmung: `_atem_klein`."""
    phase = z.phase
    if phase == PHASE_ENDE:
        return f"{'Zählen' if z.wdh else 'Atmung'} {ende_text(z.grund)}"
    if phase == PHASE_ATMUNG:
        return _atem_klein(z)
    if phase == PHASE_STARTET and not (z.korrektur or z.atem_korrektur):
        return "Sensor startet …"
    if phase == PHASE_PAUSE:
        if z.satz is None:
            return "Pause"
        return f"Pause · {zl.korrektur_text(z.sensor, z.korrektur)} · Prototyp"
    if z.sensor is None and not z.korrektur:
        return "…"
    return f"{zl.korrektur_text(z.sensor, z.korrektur)} · Prototyp"


def kurz_text(z: ZaehlBaustein) -> str:
    """Kurz für die Laufleiste und die Benachrichtigung, wenn keine Uhr läuft („Kniebeuge:
    0:42 · 12 Wdh.“) — nach dem Ende die Summe aller Sätze."""
    phase = z.phase
    if phase == PHASE_ATMUNG:
        return f"Atmung {z.atemzuege} · {zl.atem_text(z.atem_rate, z.atem_phase)}"
    if phase == PHASE_ENDE:
        return f"{z.summe} Wdh." if z.wdh else f"{z.atemzuege} Atemzüge"
    if phase == PHASE_STARTET and not (z.korrektur or z.atem_korrektur):
        return "Sensor startet …"
    if phase == PHASE_SAMMELT and not z.korrektur:
        return "…"
    return f"{z.wert} Wdh."


def leisten_text(z: ZaehlBaustein) -> str:
    """Das Zählen unter den Teilen der Laufleiste: „Zählen · Kniebeuge · 12“."""
    return f"Zählen · {z.status()}"


def wdh_im_abschnitt(z: ZaehlBaustein | None, von_s: float, bis_s: float | None) -> int | None:
    """Für die Karte „Sätze“ im Timer: was das Zählen in einem Abschnitt der Uhr zählte — die
    Sätze, die in ``[von_s, bis_s)`` begannen (Achse der Einheit; tritt das Zählen mitten im
    Abschnitt bei, beginnt sein Satz dort). ``None``: dort wurde nicht gezählt.

    >>> from types import SimpleNamespace as NS
    >>> z = NS(wdh=True, saetze=[NS(von_s=0.0, wert=12), NS(von_s=34.0, wert=10)])
    >>> wdh_im_abschnitt(z, 0.0, 20.0), wdh_im_abschnitt(z, 30.0, None)
    (12, 10)
    >>> wdh_im_abschnitt(z, 20.0, 30.0) is None, wdh_im_abschnitt(None, 0.0, 9.0) is None
    (True, True)
    """
    if z is None or not z.wdh:
        return None
    # Eine halbe Sekunde Spiel: Satz und Abschnitt beginnen im selben Takt, nicht im selben ms
    saetze = [s for s in z.saetze if s.von_s >= von_s - 0.5 and (bis_s is None or s.von_s < bis_s)]
    return sum(s.wert for s in saetze) if saetze else None


def atem_teil(state: Any) -> ZaehlBaustein | None:
    """Der Zähl-Teil der laufenden Einheit, solange er die Atmung erfasst — sonst ``None``
    (für die Schattierung des Einatmens live, Plan §7.3)."""
    e = getattr(state, "einheit", None)
    z = e.teil("zaehlen") if e is not None and e.laeuft else None
    if not isinstance(z, ZaehlBaustein) or not z.aktiv or not z.atem:
        return None
    return z


def atem_phasen_live(state: Any) -> list[tuple[float, str]]:
    """Die bestätigten Atemphasen des laufenden Atem-Laufs auf der Achse des Messlaufs
    (`Messlauf.jetzt_s`) — leer, wenn keine Atmung erfasst wird."""
    z = atem_teil(state)
    if z is None:
        return []
    return [(z.auf_messlauf(t), art) for t, art in z.atem_phasen_s]


def atem_kopf_text(state: Any) -> str:
    """Für den Kopf des Live-Vollbilds: „Atmung 12/min ▲ · Spanne 58 ms“ (die Spanne nur mit
    Aufnahme, B2) — leer ohne Atem-Lauf oder solange keine Proben kamen."""
    z = atem_teil(state)
    if z is None or z.atem_sensor is None:
        return ""
    return f"Atmung {atem_zeile(z)}"


def atmung_protokoll(state: Any) -> Callable[[list[dict[str, Any]]], dict[str, Any] | None]:
    """Der Haken `Messlauf.atmung_protokoll` mit dem Übungskatalog: Ereignisse der Aufnahme →
    Protokollfeld „Atmung“ (`core.atem_protokoll.protokoll`, Vertrag §5). Ein Kurzcode zählt
    als Atemübung, wenn an der Übung „Atmung“ an ist (`core.zaehlen.atmung_an`); Unbekanntes
    (gelöscht, fremd) als andere Übung. Gerufen im Loop (Backup, Speichern), nie im Thread."""

    def haken(ereignisse: list[dict[str, Any]]) -> dict[str, Any] | None:
        nach_id = {u.id: u for u in state.uebungen.alle(mit_archivierten=True)}

        def ist_atemuebung(code: str) -> bool | None:
            ids = katalog_aufloesen([code], nach_id)
            return zl.atmung_an(nach_id[ids[0]]) if ids else None

        return atem_protokoll.protokoll(ereignisse, ist_atemuebung)

    return haken


def sensor_text(state: Any) -> str:
    """Für die Marken-Leiste im Diagnosemodus (A2): „Sensor 11“ live neben der Zahl der Tipps
    — leer, solange nichts zählt."""
    e = getattr(state, "einheit", None)
    z = e.teil("zaehlen") if e is not None and e.laeuft else None
    if not isinstance(z, ZaehlBaustein) or not z.aktiv or not z.wdh:
        return ""
    return f"Sensor {'…' if z.sensor is None else z.sensor}"


# ---------------------------------------------------------------------------
# ±1 und Nachziehen
# ---------------------------------------------------------------------------


@dataclass
class ZaehlAnzeige:
    """Die Controls einer Zählzeile, die `nachziehen` auffrischt — je Ort (Karte „Eintragen“,
    laufende Uhr, Timer „Während“) eine, unter ihrem Namen angemeldet (`anmelden`)."""

    uebung_id: str
    item_id: str | None = None
    #: die große Zahl
    zahl: ft.Text | None = None
    #: die kleine Zeile darunter
    klein: ft.Text | None = None
    #: die Zeile der Atem-Spur bei Wdh + Atmung („Atmung 12/min ▲“, `atem_text`)
    atem: ft.Text | None = None


def anzeigen(state: Any) -> dict[str, ZaehlAnzeige]:
    """Die angemeldeten Zählzeilen im `AppState` (legt das Verzeichnis beim ersten Mal an)."""
    verzeichnis = getattr(state, "zaehl_anzeigen", None)
    if not isinstance(verzeichnis, dict):
        verzeichnis = {}
        state.zaehl_anzeigen = verzeichnis
    return verzeichnis


def anmelden(state: Any, name: str, anzeige: ZaehlAnzeige) -> None:
    """Eine Zählzeile anmelden (eine gleichen Namens ersetzt sie): Die Einheit frischt sie
    dann mit jedem Takt auf (``state.einheit_beobachter``)."""
    anzeigen(state)[name] = anzeige
    beobachter = getattr(state, "einheit_beobachter", None)
    if isinstance(beobachter, dict):
        beobachter[BEOBACHTER] = lambda: nachziehen(state)


def abmelden(state: Any, name: str) -> None:
    anzeigen(state).pop(name, None)


def nachziehen(state: Any) -> None:
    """Zahl und kleine Zeile jeder angemeldeten Zählzeile nachziehen — nur ``value`` und
    ``update()``; ohne Zähl-Teil ihrer Übung geschieht nichts. Wirft nie."""
    for a in list(anzeigen(state).values()):
        z = zaehl_teil(state, a.uebung_id, a.item_id)
        if z is None:
            continue
        if a.zahl is not None:
            a.zahl.value = zahl_text(z)
        if a.klein is not None:
            a.klein.value = klein_text(z)
        if a.atem is not None:
            a.atem.value = atem_text(z)
        with contextlib.suppress(Exception):
            for c in (a.zahl, a.klein, a.atem):
                if c is not None:
                    c.update()


def korrigieren(state: Any, uebung_id: str, item_id: str | None, delta: int) -> bool:
    """±1 am laufenden Satz dieser Übung (`ZaehlBaustein.korrigieren`, nie unter 0) — die
    Zeitleiste bekommt ``person/korrektur`` mit dem nächsten Takt. ``False``, wenn es nichts
    zu korrigieren gab (zählt nicht, schon 0)."""
    z = zaehl_teil(state, uebung_id, item_id, nur_aktiv=True)
    if z is None or not z.korrigieren(delta):
        return False
    nachziehen(state)
    return True


__all__ = [
    "BEOBACHTER",
    "ZaehlAnzeige",
    "abmelden",
    "anmelden",
    "anzeigen",
    "atem_kopf_text",
    "atem_phase",
    "atem_phasen_live",
    "atem_rate_text",
    "atem_teil",
    "atem_text",
    "atem_zeile",
    "atemzuege",
    "atmung_protokoll",
    "bereitgestellt",
    "geraet_kann_zaehlen",
    "im_plan_ablauf",
    "klein_text",
    "knopf",
    "korrigieren",
    "kurz_text",
    "leisten_text",
    "nachziehen",
    "passt",
    "sensor_text",
    "sichtbar",
    "von_hand_eingetragen",
    "wdh_im_abschnitt",
    "zaehl_teil",
    "zaehlen_an",
    "zaehlt_der_sensor",
    "zahl_text",
]
