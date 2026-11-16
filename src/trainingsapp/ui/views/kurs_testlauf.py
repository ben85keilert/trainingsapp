"""Der **Testlauf** eines Kurses — ein Test mit Vorgabe läuft mit der Uhr (Ben, 16.11.2026,
`docs/plan_kurs_ablauf.md` §3.3, Skizzen T1–T4). Route
``/kurse/<Kurs>/<Kapitel>/test/<Block>/<Übung>``, über Kurs und Kapitel gelegt: Zurück führt
ins Kapitel.

Eine Ansicht, drei Zustände:

- **bereit** — es läuft kein Testlauf: Vorgabe, Anleitung, „Start“;
- **läuft** (T1, T2) — die Vorgabe groß, die Zeit sehr groß, unten der Knopf, der den Lauf
  beendet (`core.kurstest.knopf_text`), und „Vorher aufgehört …“; ✕ bricht ab;
- **Ergebnis** (T3) — was vorgegeben war, was die Uhr gemessen hat, was die Person dazusagt;
  „Eintragen und zurück zum Kapitel“, „Nochmal“, „Verwerfen“.

Was gezeigt und gefragt wird, sagt `core/kurstest.py`; hier wird gezeichnet und der Lauf
geführt.

**Der Lauf ist ein echter Lauf der Übung** — Übung und Stoppuhr als Einheit
(`ui.uebung_lauf.starten`), damit Benachrichtigung, Wachhalten und die Marken einer laufenden
HRV-Aufnahme stimmen:

- **Gestartet** wird nur in einem Handler (`starten`: „Test starten“ im Kapitel, „Start“
  hier) — nie beim Aufbau der Ansicht, die bei jedem Routen-Aufbau neu entsteht. Was läuft,
  hält `AppState.kurs_test` (`Kurstestlauf`).
- **Angehalten** (`anhalten`: der große Knopf, „Vorher aufgehört …“, von selbst) hält die
  Stoppuhr an — die Zeit steht fest, in der Zeitleiste und in der Aufnahme „…: Pause“ an
  dieser Stelle. Die Einheit läuft weiter, bis eingetragen oder verworfen ist: „…: Ende“ der
  Übung steht darum erst dort, nicht beim Tipp, der die Uhr anhält.
- **Zurück** (die Systemtaste) beendet nichts — wie überall wechselt nur die Ansicht. Die
  Testkarte im Kapitel führt mit „Zum Test“ wieder her (`laeuft_fuer`).
- **Eingetragen** (`eintragen`) wird ein **eigener, abgeschlossener Eintrag**
  (`core.kurstest.eintrag`, `SessionRepo.eintrag_anlegen` mit Anfang und Ende) — nicht über
  den offenen Eintrag der Uhr: Dort gingen nur Wiederholungen und Zeit mit, und frühere Sätze
  des Tages stünden im selben Eintrag. Danach steht ``person/eintrag`` mit ``teil`` „uhr“
  (zählte jemand mit, auch „zaehlen“) in der Zeitleiste, dann endet die Uhr als fertig: Das
  Ende der Einheit (`ui.uebung_lauf.nach_dem_ende`) trägt so nichts ein zweites Mal ein, und
  „Läufe heute“ zeigt den Lauf als eingetragen.
- **Verworfen** (`verwerfen`: ✕, „Verwerfen“, „Nochmal“) bricht die Uhr ab — nichts wird
  eingetragen; der Lauf bleibt wie jeder abgebrochene unter „Läufe heute“.
- **Vorgabe Zeit:** dieselbe Stoppuhr; ein Wächter (`pruefen`, solange der Test läuft) hält
  sie bei n Sekunden an und spielt Countdown und Endsignal des Timers. Ein Einmal-Timer
  beendete mit seinem Ende die Einheit und trüge selbst ein, bevor Wiederholungen und Skala
  gefragt sind; ohne dieses Ende ließe sich ein abgelaufener Timer nicht mehr verwerfen.
- **Zählen:** Zählt bei dieser Übung schon der Sensor (die Uhr tritt seinem Zähllauf bei,
  `ui.uebung_lauf.starten`) oder der Takt, steht statt „Du zählst selbst“ die Zahl da, und
  eine Menge als Vorgabe endet von selbst. Einen eigenen Weg, das Zählen zu starten, gibt es
  hier nicht; der Takt der Übung läuft im Test nicht mit.

Die Skala ist Selbstauskunft: Die Ansicht nennt die Regel des Kurses und deutet keine Zahl
(`docs/recht/00_zweckbestimmung.md`).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import flet as ft

from trainingsapp.core import kurstest
from trainingsapp.core.einheit import Ereignis
from trainingsapp.core.kursbloecke import AUSWAHL, MENGE, TEST, ZEIT, Block, Vorgabe
from trainingsapp.core.kurse import Kapitel, Kurs
from trainingsapp.core.models import Exercise, SessionEntry, lokaler_tag
from trainingsapp.core.timer import COUNTDOWN, ENDE, TimerStand, dauer_text, signal, stoppuhr
from trainingsapp.core.uebung_timer import zeit_werte
from trainingsapp.core.zaehlen import quelle_name
from trainingsapp.devices.einheit import Einheitslauf
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui import uebung_lauf
from trainingsapp.ui.components import zaehl_stand, zaehlen
from trainingsapp.ui.components.dialoge import meldung
from trainingsapp.ui.components.fokus import FOKUS_ANSICHT
from trainingsapp.ui.components.karte import hinweis, karte, titel
from trainingsapp.ui.components.layout import sicher
from trainingsapp.ui.state import AppState
from trainingsapp.ui.timer_takt import TICK_S, ton_spielen

#: Das Routenstück zwischen Kapitel und Block
SEGMENT = "test"
#: Die Zustände eines Testlaufs — „bereit“ ist: es gibt keinen
LAEUFT = "laeuft"
ERGEBNIS = "ergebnis"
#: Unter diesem Namen frischt der Ticker die laufende Ansicht auf (`AppState.timer_beobachter`)
BEOBACHTER = "kurs_test"
#: Der Balken der Anstrengung hat die Stufen 1 bis hier
STUFEN = 10
#: So viele Stufen der Skala stehen im Ergebnis in einer Zeile (T3)
JE_ZEILE = 6


@dataclass
class Kurstestlauf:
    """Der Testlauf, der gerade läuft oder auf sein Ergebnis wartet (`AppState.kurs_test`) —
    am Zustand gehalten, weil die Ansicht bei jedem Aufbau neu entsteht."""

    kurs_id: str
    kapitel_id: str
    block: Block
    uebung_id: str
    #: die Einheit aus Übung und Stoppuhr — endet sie anderswo, gibt es den Testlauf nicht mehr
    einheit_id: str
    vorgabe: Vorgabe
    felder: kurstest.Felder
    phase: str = LAEUFT
    #: ab dem Anhalten: wo die Uhr hielt (Achse der Einheit) — das Ende des Eintrags
    ende_t_s: float = 0.0
    #: ab dem Anhalten: was feststeht und was die Person dazusagt (`core.kurstest.am_ende`)
    sekunden: float = 0.0
    wdh: int | None = None
    skala: int | None = None
    #: „Vorher aufgehört …“ — die Vorgabe ist nicht erreicht
    vorher: bool = False
    #: Sensor oder Takt zählten: Die Wiederholungen werden nicht gefragt
    gezaehlt: bool = False


def route_zum_test(kurs_id: str, kapitel_id: str, block_id: str, uebung_id: str) -> str:
    """Die Route des Testlaufs.

    >>> route_zum_test("k", "c", "b", "u")
    '/kurse/k/c/test/b/u'
    """
    return f"/kurse/{kurs_id}/{kapitel_id}/{SEGMENT}/{block_id}/{uebung_id}"


def aus_route(
    state: AppState, kurs: Kurs, kapitel: Kapitel, rest: Sequence[str]
) -> tuple[Block, Exercise] | None:
    """Block und Übung zu ``test/<Block>/<Übung>`` hinter dem Kapitel — ``None``, wenn es den
    Test nicht gibt, er keine Vorgabe hat oder die Übung nicht zu ihm gehört (die feste, bei
    einem Test „der gewählten“ eine aus seiner Auswahl)."""
    if len(rest) < 3 or rest[0] != SEGMENT:
        return None
    block = next(
        (b for b in kapitel.bloecke if b.id == rest[1] and b.art == TEST and b.vorgabe), None
    )
    if block is None:
        return None
    if block.aus:
        auswahl = next(
            (b for k in kurs.kapitel for b in k.bloecke if b.id == block.aus and b.art == AUSWAHL),
            None,
        )
        erlaubt = list(auswahl.uebungen) if auswahl is not None else []
    else:
        erlaubt = [block.uebung]
    uebung = state.uebungen.laden(rest[2]) if rest[2] in erlaubt else None
    return (block, uebung) if uebung is not None else None


# ---------------------------------------------------------------------------
# Der Lauf
# ---------------------------------------------------------------------------


def laufender(state: Any) -> tuple[Kurstestlauf, Einheitslauf] | None:
    """Der Testlauf und seine Einheit — ``None``, wenn keiner läuft. Endete die Einheit
    anderswo (⏹ in der Laufleiste, „Fertig“ im Timer der Übung), ist der Testlauf vorbei."""
    stand = getattr(state, "kurs_test", None)
    if not isinstance(stand, Kurstestlauf):
        return None
    e = einheit_ui.laeuft(state)
    if e is None or e.id != stand.einheit_id or e.timer is None:
        state.kurs_test = None
        return None
    return stand, e


def laeuft_fuer(state: Any) -> tuple[str, str] | None:
    """Block und Übung des laufenden Testlaufs — für die Testkarte im Kapitel („Zum Test“)."""
    gefunden = laufender(state)
    return (gefunden[0].block.id, gefunden[0].uebung_id) if gefunden is not None else None


def _melden(page: Any, text: str) -> None:
    with contextlib.suppress(Exception):
        page.show_dialog(meldung(text))


def _gezaehlt(state: Any, stand: Kurstestlauf) -> tuple[int, str] | None:
    """Was Sensor oder Takt in diesem Lauf zählten und wer zählt („Sensor“, „Takt“) —
    ``None``: Niemand zählt Wiederholungen. Gezählt wird, was die Einheit am Ende eintrüge:
    alle Sätze des Zähl-Teils (`ZaehlBaustein.summe`)."""
    z = zaehl_stand.zaehl_teil(state, stand.uebung_id)
    if z is None or not z.wdh:
        return None
    return z.summe, quelle_name(z.quelle)


def starten(
    page: Any, state: Any, kurs: Kurs, kapitel: Kapitel, block: Block, uebung: Exercise
) -> Kurstestlauf | None:
    """Den Testlauf starten — nur aus einem Handler. Läuft dieser Test schon (oder wartet er
    auf sein Ergebnis), bleibt es bei ihm. ``None``: Es läuft etwas anderes — die Meldung
    steht unten (wie im Timer der Übung)."""
    gefunden = laufender(state)
    if gefunden is not None and (gefunden[0].block.id, gefunden[0].uebung_id) == (
        block.id,
        uebung.id,
    ):
        return gefunden[0]
    v = block.vorgabe
    if v is None:
        return None
    f = kurstest.felder(block, uebung)
    # Die Zeit zählt immer (sie ist Vorgabe oder Messwert), in das Feld, das der Eintrag nimmt
    kontext = uebung_lauf.kontext_fuer(uebung, zeit_eintragen=True, feld=f.zeit)
    try:
        e = uebung_lauf.starten(page, state, kontext, stoppuhr())
    except RuntimeError as fehler:
        _melden(page, str(fehler))
        return None
    stand = Kurstestlauf(kurs.id, kapitel.id, block, uebung.id, e.id, v, f)
    state.kurs_test = stand
    state.uebung_laeufe[uebung.id] = e.id
    zaehlen.meldung_zeigen(page, state)  # ein Zählen einer anderen Übung endete
    if v.art in (MENGE, ZEIT):  # eine Skala endet nie von selbst
        with contextlib.suppress(Exception):
            page.run_task(_wachen, page, state, stand)
    return stand


def anhalten(page: Any, state: Any, *, vorher: bool = False) -> bool:
    """Der Lauf ist zu Ende gelaufen: Die Uhr hält, die Zeit steht fest, das Ergebnis wartet
    (`core.kurstest.am_ende`). ``vorher``: „Vorher aufgehört …“. Die Einheit läuft weiter, bis
    eingetragen (`eintragen`) oder verworfen (`verwerfen`) ist."""
    gefunden = laufender(state)
    if gefunden is None or gefunden[0].phase != LAEUFT:
        return False
    stand, e = gefunden
    assert e.timer is not None  # `laufender`
    lauf = e.timer.lauf
    if lauf.laeuft:  # in der Laufleiste schon angehalten: dabei bleibt es
        einheit_ui.anhalten_oder_weiter(page, state)
    gezaehlt = _gezaehlt(state, stand)
    stand.wdh, stand.sekunden, stand.skala = kurstest.am_ende(
        stand.vorgabe,
        stand.felder,
        gelaufen_s=lauf.vergangen_s(),
        vorher=vorher,
        gezaehlt=gezaehlt[0] if gezaehlt is not None else None,
    )
    stand.gezaehlt = gezaehlt is not None
    stand.vorher = vorher
    stand.ende_t_s = max(e.dauer_s(), 0.0)
    stand.phase = ERGEBNIS
    e.takt()  # die Pause steht gleich in der Zeitleiste und in der Aufnahme
    einheit_ui.melden(state)
    return True


def eintragen(page: Any, state: Any) -> SessionEntry | None:
    """„Eintragen“: ein eigener, abgeschlossener Eintrag bei der Übung — dann ``person/eintrag``
    in die Zeitleiste und die Uhr fertig (Moduldocstring). ``None``: Es wartet kein Ergebnis,
    oder dem Eintrag fehlt noch der Wert des Tests (`core.kurstest.fehlt`)."""
    gefunden = laufender(state)
    if gefunden is None or gefunden[0].phase != ERGEBNIS:
        return None
    stand, e = gefunden
    uebung = state.uebungen.laden(stand.uebung_id, mit_geloeschten=True)
    if uebung is None or e.zeitbasis is None or e.timer is None:
        return None
    wdh, sekunden, skala = stand.wdh, stand.sekunden, stand.skala
    if kurstest.fehlt(stand.block, uebung, wdh=wdh, sekunden=sekunden, skala=skala):
        return None
    mit, werte = kurstest.eintrag(stand.block, uebung, wdh=wdh, sekunden=sekunden, skala=skala)
    anker = e.zeitbasis.anker_utc
    sitzung = state.sitzungen.session_fuer(
        e.subject_id or state.profil.id, None, lokaler_tag(anker)
    )
    eintrag: SessionEntry = state.sitzungen.eintrag_anlegen(
        sitzung,
        mit,
        werte,
        started_at=anker,
        ended_at=anker + timedelta(seconds=stand.ende_t_s),
    )
    # In die Zeitleiste, was eingetragen wurde — nichts kommt zweimal hinein (``teil``)
    jetzt_s = max(e.dauer_s(), 0.0)
    f = stand.felder
    e.nachtragen(
        Ereignis(
            jetzt_s,
            "person",
            "eintrag",
            uebung.name,
            {
                "eintrag": eintrag.id,
                "werte": zeit_werte(mit, werte),
                "teil": uebung_lauf.TEIL_UHR,
                "zeitfeld": f.zeit,
            },
        )
    )
    if e.teil("zaehlen") is not None:
        # Zählte jemand mit, trüge das Ende der Einheit seine Wiederholungen in den offenen
        # Eintrag — sie stehen schon in diesem
        e.nachtragen(
            Ereignis(
                jetzt_s,
                "person",
                "eintrag",
                uebung.name,
                {
                    "eintrag": eintrag.id,
                    "werte": [stand.wdh] if stand.wdh else [],
                    "feld": f.wdh or "",
                    "teil": uebung_lauf.TEIL_ZAEHLEN,
                },
            )
        )
    e.timer.lauf.fertig_machen()
    e.takt()  # die Einheit endet mit der Uhr — eingetragen ist schon
    state.kurs_test = None
    einheit_ui.melden(state)
    return eintrag


def verwerfen(page: Any, state: Any) -> bool:
    """Den Testlauf abbrechen — ✕, „Verwerfen“, „Nochmal“: Die Uhr bricht ab, nichts wird
    eingetragen. ``False``: Es lief keiner."""
    gefunden = laufender(state)
    state.kurs_test = None
    if gefunden is None:
        return False
    _, e = gefunden
    assert e.timer is not None  # `laufender`
    lauf = e.timer.lauf
    if not lauf.begonnen:
        lauf.fortsetzen()  # bei 0:00 angehalten gälte er als nie gestartet — und liefe weiter
    lauf.abbrechen()
    e.takt()  # die Einheit endet mit der Uhr, abgebrochen
    einheit_ui.melden(state)
    return True


def pruefen(page: Any, state: Any) -> bool:
    """Endet der Lauf von selbst? Eine Zeit, sobald sie ab ist; eine Menge, sobald Sensor oder
    Takt sie gezählt haben (`core.kurstest.erreicht`) — dann hält die Uhr an. ``True``: eben
    angehalten."""
    gefunden = laufender(state)
    if gefunden is None or gefunden[0].phase != LAEUFT:
        return False
    stand, e = gefunden
    assert e.timer is not None  # `laufender`
    gezaehlt = _gezaehlt(state, stand)
    if not kurstest.erreicht(
        stand.vorgabe,
        wdh=gezaehlt[0] if gezaehlt is not None else None,
        gelaufen_s=e.timer.lauf.vergangen_s(),
    ):
        return False
    return anhalten(page, state)


def _zeitstand(stand: Kurstestlauf, e: Einheitslauf) -> TimerStand | None:
    """Die Vorgabe Zeit, wie ein Einmal-Timer sie zeigte — für Countdown und Endsignal
    (`core.timer.signal`). ``None``: Die Vorgabe ist keine Zeit."""
    if stand.vorgabe.art != ZEIT or e.timer is None:
        return None
    lauf = e.timer.lauf
    rest = max(stand.vorgabe.n - lauf.vergangen_s(), 0.0)
    return TimerStand(1, 0, "", stand.vorgabe.n, rest, rest, lauf.laeuft, rest <= 0)


async def _signal(state: Any, art: str) -> None:
    """Ton und Vibration wie beim Timer (`ui.timer_takt`): der Countdown 3-2-1, wenn
    eingestellt, und das Endsignal mit zweimal Vibrieren."""
    signale = state.timer_signale()
    if art == COUNTDOWN and not signale.countdown:
        return
    if signale.ton:
        await ton_spielen(state, art, signale)  # die Klänge heißen wie die Signale
    haptik = getattr(state, "haptik", None)
    if signale.vibration and haptik is not None and art != COUNTDOWN:
        with contextlib.suppress(Exception):
            await haptik.vibrate()
            await asyncio.sleep(0.35)
            await haptik.vibrate()


async def _wachen(page: Any, state: Any, stand: Kurstestlauf) -> None:
    """Solange dieser Testlauf läuft: Countdown der Vorgabe Zeit, und das Ende von selbst
    (`pruefen`) mit dem Endsignal — unabhängig davon, welche Ansicht offen ist."""
    alt: TimerStand | None = None
    while getattr(state, "kurs_test", None) is stand and stand.phase == LAEUFT:
        gefunden = laufender(state)
        if gefunden is None:
            return
        neu = _zeitstand(stand, gefunden[1])
        art = signal(alt, neu) if alt is not None and neu is not None else None
        alt = neu
        if pruefen(page, state):
            await _signal(state, ENDE)
            # nicht über ein Formular mit ungespeicherten Eingaben hinweg (N78)
            zeichnen = getattr(state, "neu_zeichnen_von_aussen", None) or state.neu_zeichnen
            with contextlib.suppress(Exception):
                zeichnen()
            return
        if art == COUNTDOWN:
            await _signal(state, COUNTDOWN)
        await asyncio.sleep(TICK_S)


def starter(
    page: Any, state: Any, kurs: Kurs, kapitel: Kapitel, block: Block, uebung: Exercise
) -> Callable[..., Awaitable[None]]:
    """Der Handler „Test starten“ / „Nochmal“ der Testkarte im Kapitel: starten, dann in den
    Testlauf."""

    async def handler(_e: Any = None) -> None:
        if starten(page, state, kurs, kapitel, block, uebung) is None:
            return
        await page.push_route(route_zum_test(kurs.id, kapitel.id, block.id, uebung.id))

    return handler


# ---------------------------------------------------------------------------
# Die Ansicht
# ---------------------------------------------------------------------------

_GROSS = ft.ButtonStyle(
    shape=ft.RoundedRectangleBorder(radius=32),
    text_style=ft.TextStyle(size=18, weight=ft.FontWeight.W_700),
)
_MITTEL = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=24))


def _seite(oben: Sequence[ft.Control], unten: Sequence[ft.Control]) -> ft.Control:
    """Der Inhalt rollt, die Knöpfe stehen fest am unteren Rand."""
    return sicher(
        ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Column(
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Container(
                            padding=16,
                            content=ft.Column(
                                spacing=16,
                                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                                controls=list(oben),
                            ),
                        )
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.only(left=16, right=16, top=8, bottom=16),
                    content=ft.Column(
                        spacing=10,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        controls=list(unten),
                    ),
                ),
            ],
        )
    )


def _kopf(v: Vorgabe, f: kurstest.Felder) -> ft.Control:
    """„VORGABE“, die Vorgabe groß, darunter der Satz der Anleitung."""
    return ft.Column(
        spacing=4,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            titel("Vorgabe"),
            ft.Text(
                kurstest.vorgabe_text(v, f.skala_name),
                size=24,
                weight=ft.FontWeight.W_700,
                data="test_vorgabe",
            ),
            ft.Text(kurstest.anleitung(v, zaehlt_wdh=f.wdh is not None), size=14, opacity=0.85),
        ],
    )


def _balken(m: kurstest.Marke) -> ft.Control:
    """Der Balken 1–10 der Anstrengung mit der Marke des Kurses (T2)."""

    def stufe(k: int) -> ft.Control:
        in_marke = m.von <= k <= m.bis
        farbe = (
            ft.Colors.PRIMARY
            if in_marke
            else ft.Colors.OUTLINE
            if k < m.von
            else ft.Colors.OUTLINE_VARIANT
        )
        return ft.Container(expand=1, height=18 if in_marke else 10, border_radius=3, bgcolor=farbe)

    return ft.Column(
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Row(
                spacing=4,
                height=18,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[stufe(k) for k in range(1, STUFEN + 1)],
                data="test_balken",
            ),
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text("1 · leicht", size=12, opacity=0.65),
                    ft.Text(m.text, size=12, weight=ft.FontWeight.W_600),
                    ft.Text(str(STUFEN), size=12, opacity=0.65),
                ],
            ),
        ],
    )


def _skala_karte(v: Vorgabe, f: kurstest.Felder) -> ft.Control | None:
    m = kurstest.marke(v)
    if m is None:
        return None
    return karte(
        titel(f.skala_name),
        _balken(m),
        hinweis("Die Marke ist die Regel des Kurses. Wie es sich anfühlt, weißt nur du."),
        abstand=10,
    )


def kurs_test_view(
    page: Any, state: AppState, kurs: Kurs, kapitel: Kapitel, block: Block, uebung: Exercise
) -> ft.View:
    """Der Testlauf zu ``block`` bei ``uebung`` — bereit, läuft oder Ergebnis (Moduldocstring).
    Der Aufbau startet nichts."""
    route = route_zum_test(kurs.id, kapitel.id, block.id, uebung.id)
    zum_kapitel = f"/kurse/{kurs.id}/{kapitel.id}"
    v = block.vorgabe
    assert v is not None  # die Route gibt es nur für Tests mit Vorgabe (`aus_route`)
    f = kurstest.felder(block, uebung)
    gefunden = laufender(state)
    if gefunden is not None and (gefunden[0].block.id, gefunden[0].uebung_id) != (
        block.id,
        uebung.id,
    ):
        gefunden = None  # ein anderer Test läuft — dieser ist bereit, „Start“ sagt, warum nicht
    stand = gefunden[0] if gefunden is not None else None

    def neu_zeichnen() -> None:
        with contextlib.suppress(Exception):
            state.neu_zeichnen()

    async def zurueck() -> None:
        await page.push_route(zum_kapitel)

    async def abbrechen(_e: Any = None) -> None:
        """✕ und „Verwerfen“: nichts wird eingetragen, zurück ins Kapitel."""
        verwerfen(page, state)
        await zurueck()

    def start(_e: Any = None) -> None:
        if starten(page, state, kurs, kapitel, block, uebung) is not None:
            neu_zeichnen()

    def nochmal(_e: Any = None) -> None:
        """Verwerfen und wieder bereit — gestartet wird mit dem nächsten Tipp."""
        verwerfen(page, state)
        neu_zeichnen()

    kreuz = ft.IconButton(
        ft.Icons.CLOSE,
        tooltip="Test abbrechen" if stand is None or stand.phase == LAEUFT else "Test verwerfen",
        on_click=abbrechen,
        data="test_abbrechen",
    )

    # -- bereit ---------------------------------------------------------------------------------

    def bereit() -> ft.Control:
        skala = _skala_karte(v, f)
        return _seite(
            [_kopf(v, f), *([skala] if skala is not None else [])],
            [
                ft.FilledButton(
                    "Start",
                    icon=ft.Icons.PLAY_ARROW,
                    height=64,
                    style=_GROSS,
                    on_click=start,
                    data="test_start",
                ),
                ft.Text(
                    "Die Uhr läuft mit dem Tipp los.",
                    size=12,
                    opacity=0.65,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
        )

    # -- läuft (T1, T2) -------------------------------------------------------------------------

    def laeuft(e: Einheitslauf, s: Kurstestlauf) -> ft.Control:
        assert e.timer is not None  # `laufender`
        lauf = e.timer.lauf
        zeit = ft.Text(
            kurstest.zeit_anzeige(v, lauf.vergangen_s()),
            size=96,
            weight=ft.FontWeight.W_700,
            text_align=ft.TextAlign.CENTER,
            data="test_zeit",
        )
        zahl = ft.Text(size=28, weight=ft.FontWeight.W_700, data="test_zahl")
        wer_zaehlt = ft.Text(size=15, weight=ft.FontWeight.W_600)
        dazu = ft.Text(size=12, opacity=0.65)
        symbol = ft.Icon(ft.Icons.PERSON_OUTLINE, size=26)

        def zaehlen_zeigen() -> None:
            gezaehlt = _gezaehlt(state, s)
            wer_zaehlt.value, dazu.value = kurstest.zaehl_text(
                v, gezaehlt[1] if gezaehlt is not None else ""
            )
            dazu.visible = bool(dazu.value)
            zahl.value = str(gezaehlt[0]) if gezaehlt is not None else ""
            zahl.visible = gezaehlt is not None
            symbol.icon = ft.Icons.SENSORS if gezaehlt is not None else ft.Icons.PERSON_OUTLINE

        def auffrischen() -> None:
            """Jeder Tick der Uhr: die Zeit und, wenn jemand zählt, die Zahl."""
            neu = kurstest.zeit_anzeige(v, lauf.vergangen_s())
            vorher_zahl = zahl.value
            zaehlen_zeigen()
            if neu == zeit.value and zahl.value == vorher_zahl:
                return
            zeit.value = neu
            for teil in (zeit, wdh_karte):
                with contextlib.suppress(Exception):
                    teil.update()

        def fertig(_e: Any = None) -> None:
            if anhalten(page, state):
                neu_zeichnen()

        def vorher_aufgehoert(_e: Any = None) -> None:
            if anhalten(page, state, vorher=True):
                neu_zeichnen()

        zaehlen_zeigen()
        # Wiederholungen: wer zählt — nur bei einer Übung, die welche hat
        wdh_karte = karte(
            titel(kurstest.GROESSEN[kurstest.WDH]),
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    symbol,
                    ft.Column(spacing=2, tight=True, expand=True, controls=[wer_zaehlt, dazu]),
                    zahl,
                ],
            ),
            abstand=10,
        )
        skala = _skala_karte(v, f)
        zeigt_wdh = f.wdh is not None and (skala is None or _gezaehlt(state, s) is not None)
        state.timer_beobachter[BEOBACHTER] = auffrischen
        knopf = kurstest.knopf_text(v)
        return _seite(
            [
                _kopf(v, f),
                ft.Container(
                    padding=ft.Padding.symmetric(vertical=12),
                    content=ft.Column(
                        spacing=4,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[zeit, ft.Text(kurstest.zeit_zeile(v), size=13, opacity=0.65)],
                    ),
                ),
                *([skala] if skala is not None else []),
                *([wdh_karte] if zeigt_wdh else []),
            ],
            [
                *(
                    [
                        ft.FilledButton(
                            knopf,
                            icon=ft.Icons.CHECK,
                            height=64,
                            style=_GROSS,
                            on_click=fertig,
                            data="test_fertig",
                        )
                    ]
                    if knopf  # eine Zeit endet von selbst
                    else []
                ),
                ft.TextButton(
                    "Vorher aufgehört …",
                    height=48,
                    on_click=vorher_aufgehoert,
                    data="test_vorher",
                ),
                ft.Text(
                    kurstest.unten_text(v), size=12, opacity=0.65, text_align=ft.TextAlign.CENTER
                ),
            ],
        )

    # -- Ergebnis (T3) --------------------------------------------------------------------------

    def ergebnis(s: Kurstestlauf) -> ft.Control:
        fehlt_text = ft.Text(size=12, color=ft.Colors.ERROR, data="test_fehlt")
        eintragen_knopf = ft.FilledButton(
            "Eintragen und zurück zum Kapitel",
            icon=ft.Icons.CHECK,
            height=56,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=28),
                text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_700),
            ),
            data="test_eintragen",
        )

        def stand_zeigen(aktualisieren: bool = True) -> None:
            """„Eintragen“ geht erst, wenn das Feld des Tests einen Wert hat."""
            fehlt = kurstest.fehlt(block, uebung, wdh=s.wdh, sekunden=s.sekunden, skala=s.skala)
            eintragen_knopf.disabled = bool(fehlt)
            fehlt_text.value = f"Es fehlt noch: {fehlt}." if fehlt else ""
            fehlt_text.visible = bool(fehlt)
            if aktualisieren:
                for teil in (eintragen_knopf, fehlt_text):
                    with contextlib.suppress(Exception):
                        teil.update()

        async def eintragen_klick(_e: Any = None) -> None:
            eintrag = eintragen(page, state)
            if eintrag is None:
                stand_zeigen()
                return
            await zurueck()
            _melden(page, f"{uebung.name}: {eintrag.shorthand() or 'eingetragen'}")

        eintragen_knopf.on_click = eintragen_klick

        def zeile(name: str, woher: str, rechts: ft.Control) -> ft.Control:
            return ft.Container(
                padding=ft.Padding.symmetric(vertical=8),
                content=ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=2,
                            tight=True,
                            expand=True,
                            controls=[
                                ft.Text(name, size=15, weight=ft.FontWeight.W_600),
                                ft.Text(kurstest.WOHER[woher], size=12, opacity=0.65),
                            ],
                        ),
                        rechts,
                    ],
                ),
            )

        def gross(text: str, data: str) -> ft.Control:
            return ft.Text(text, size=24, weight=ft.FontWeight.W_700, data=data)

        def wdh_geaendert(e: Any) -> None:
            roh = str(getattr(e.control, "value", "") or "").strip()
            s.wdh = int(roh) if roh.isdigit() and int(roh) > 0 else None
            stand_zeigen()

        zeilen: list[ft.Control] = []
        woher_wdh = kurstest.woher_wdh(v, f, vorher=s.vorher, gezaehlt=s.gezaehlt)
        if woher_wdh == kurstest.GEFRAGT:
            # Niemand hat gezählt: Die Person sagt, wie viele es waren
            feld = ft.TextField(
                value=str(s.wdh) if s.wdh else "",
                hint_text="Anzahl",
                width=110,
                dense=True,
                border=ft.OutlineInputBorder(border_radius=8),
                keyboard_type=ft.KeyboardType.NUMBER,
                input_filter=ft.InputFilter(regex_string=r"^[0-9]{0,4}$", allow=True),
                text_align=ft.TextAlign.RIGHT,
                on_change=wdh_geaendert,
                data="test_wdh",
            )
            zeilen.append(zeile(kurstest.GROESSEN[kurstest.WDH], woher_wdh, feld))
        elif woher_wdh is not None:
            zeilen.append(
                zeile(kurstest.GROESSEN[kurstest.WDH], woher_wdh, gross(str(s.wdh or 0), "wdh"))
            )
        if zeilen:
            zeilen.append(ft.Divider(height=1, thickness=1, color=ft.Colors.OUTLINE_VARIANT))
        zeilen.append(
            zeile(
                kurstest.GROESSEN[kurstest.DAUER],
                kurstest.woher_zeit(v, vorher=s.vorher),
                gross(dauer_text(s.sekunden), "zeit"),
            )
        )

        # Die Skala: Stufen als Raster, die gewählte gefüllt; noch einmal tippen nimmt sie zurück
        stufen = kurstest.skala_stufen(uebung.result_spec)
        frage, unterzeile = kurstest.skala_frage(f.skala_name, stufen)
        zellen: dict[int, ft.Container] = {}

        def stil(zelle: ft.Container, w: int) -> None:
            gewaehlt = s.skala == w
            zelle.bgcolor = ft.Colors.PRIMARY if gewaehlt else None
            zelle.border = None if gewaehlt else ft.Border.all(1.5, ft.Colors.OUTLINE)
            zelle.content = ft.Text(
                str(w),
                size=15,
                weight=ft.FontWeight.W_700 if gewaehlt else None,
                color=ft.Colors.ON_PRIMARY if gewaehlt else None,
            )

        def waehlen(w: int) -> Callable[..., None]:
            def handler(_e: Any = None) -> None:
                s.skala = None if s.skala == w else w
                for k, zelle in zellen.items():
                    stil(zelle, k)
                stand_zeigen()
                with contextlib.suppress(Exception):
                    raster.update()

            return handler

        for w in stufen:
            zellen[w] = ft.Container(
                expand=1,
                height=44,
                border_radius=10,
                alignment=ft.Alignment.CENTER,
                ink=True,
                on_click=waehlen(w),
                data=("test_skala", w),
            )
            stil(zellen[w], w)
        werte = list(stufen)
        reihen: list[ft.Control] = []
        for i in range(0, len(werte), JE_ZEILE):
            reihe: list[ft.Control] = [zellen[w] for w in werte[i : i + JE_ZEILE]]
            # die letzte Zeile auffüllen: Die Stufen stehen in Spalten untereinander
            reihe.extend(ft.Container(expand=1) for _ in range(JE_ZEILE - len(reihe)))
            reihen.append(ft.Row(spacing=8, controls=reihe))
        raster = ft.Column(spacing=8, tight=True, controls=reihen, data="test_raster")

        stand_zeigen(aktualisieren=False)
        return _seite(
            [
                ft.Text("Dein Test", size=22, weight=ft.FontWeight.W_700),
                karte(*zeilen, padding=14, abstand=0),
                karte(
                    ft.Column(
                        spacing=2,
                        tight=True,
                        controls=[
                            ft.Text(frage, size=15, weight=ft.FontWeight.W_600),
                            ft.Text(unterzeile, size=12, opacity=0.65),
                        ],
                    ),
                    raster,
                    abstand=10,
                ),
                ft.Text(
                    f"Eingetragen wird ein gewöhnlicher Eintrag bei „{uebung.name}“ — er steht "
                    "auch unter Heute. Was der Kurs daraus für deinen Plan vorschlägt, zeigt das "
                    "Kapitel.",
                    size=12,
                    opacity=0.65,
                ),
            ],
            [
                fehlt_text,
                eintragen_knopf,
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.FilledTonalButton(
                            "Nochmal",
                            icon=ft.Icons.PLAY_ARROW,
                            height=48,
                            expand=True,
                            style=_MITTEL,
                            on_click=nochmal,
                            data="test_nochmal",
                        ),
                        ft.TextButton(
                            "Verwerfen",
                            height=48,
                            expand=True,
                            style=_MITTEL,
                            on_click=abbrechen,
                            data="test_verwerfen",
                        ),
                    ],
                ),
            ],
        )

    # -- Zusammensetzen ---------------------------------------------------------------------------

    state.timer_beobachter.pop(BEOBACHTER, None)
    if gefunden is None or stand is None:
        inhalt = bereit()
    elif stand.phase == LAEUFT:
        inhalt = laeuft(gefunden[1], stand)
    else:
        inhalt = ergebnis(stand)
    return ft.View(
        route=route,
        # Im Lauf und im Ergebnis ein Fokus: keine Laufleiste (`components.fokus`)
        data=FOKUS_ANSICHT if stand is not None else None,
        appbar=ft.AppBar(
            title=ft.Text(f"Test · {uebung.name}"),
            # bereit: der Pfeil zurück ins Kapitel; sonst ✕ — der Lauf endet ohne Eintrag
            leading=kreuz if stand is not None else None,
            automatically_imply_leading=stand is None,
        ),
        padding=0,
        controls=[inhalt],
    )


__all__ = [
    "ERGEBNIS",
    "LAEUFT",
    "Kurstestlauf",
    "anhalten",
    "aus_route",
    "eintragen",
    "kurs_test_view",
    "laeuft_fuer",
    "laufender",
    "pruefen",
    "route_zum_test",
    "starten",
    "starter",
    "verwerfen",
]
