"""Der Timer einer Übung als Einheit — bereitstellen, starten, eintragen (ohne flet).

Ben, 17.10.2026 (Skizzen 12–15): Die Uhr neben dem i öffnet den Timer der Übung. Ist er
fertig, gilt die Übung als **gemacht**, und die gelaufene Zeit kommt ins Tagebuch — als
Haltezeit je Satz oder als Zeit (`core.timer_eintrag`), seit 22.10.2026 **in den offenen
Eintrag** wie ein Tipp (P79 D1, `SessionRepo.lauf_eintragen`). Ob sie zählt, legt die Übung
fest (`Exercise.zeit_zaehlt`); beim Üben gilt die Wahl in der Leiste für jetzt
(`AppState.uhr_zaehlt`). **Abbrechen** trägt nichts ein; der Lauf bleibt unter „Läufe
heute“ und lässt sich dort doch eintragen.
Läuft eine HRV-Aufnahme, bekommt sie die Übung und ihre Abschnitte als Marken.

Ein Lauf ist eine Einheit aus Übung (`devices.einheit.UebungBaustein`) und Timer, dazu
die HRV, wenn sie schon aufnimmt. Die Zeitleiste ist die Grundlage: Aus ihr kommen die
gelaufenen Zeiten, und ``person/eintrag`` hält fest, was eingetragen wurde.

**Wiederholungen zählen** (Ben, 4.11.2026, ``docs/plan_beschleunigung.md`` §4.3): Der Knopf
„Wdh. zählen“ startet einen **Zähllauf** — eine Einheit aus Übung und Zählen
(`devices.zaehlen.ZaehlBaustein`), dazu die HRV, die schon aufnimmt (`zaehlen_starten`).

- **Uhr und Zählen derselben Übung teilen eine Einheit:** Läuft die Uhr, tritt das Zählen ihr
  bei; zählt es schon, tritt die Uhr dem Zähllauf bei (`starten`) — die Einheit endet dann mit
  der Uhr, das Zählen gilt als ``fertig``. Bricht die Uhr ab, ist der ganze Lauf abgebrochen.
- **Eine andere Übung** (ihr Zählen, ihre Uhr) beendet ein Zählen ohne Uhr mit
  ``andere_uebung`` (`ui.einheit.platz_machen`) — die Meldung „Kniebeuge · 12 Wdh. nicht
  eingetragen“ mit „Eintragen“ holt `meldung_abholen`. Eine laufende Uhr wird nie still beendet.
- **Eingetragen wird an einer Stelle** (`nach_dem_ende`, am Ende der Einheit): Zeit und
  Wiederholungen zusammen in den offenen Eintrag. ``person/eintrag`` trägt ``teil`` (``uhr``
  oder ``zaehlen``, `core.zaehlen_eintrag.eingetragen`) — so kommt nichts doppelt hinein. Nur
  **abgehakt** trägt sofort ein (`zaehlen_beenden`), damit der Eintrag danach geschlossen
  werden kann; solange die Einheit läuft, schreibt das `Einheitslauf.nachtragen`. Eingetragen
  wird dort, wo abgehakt wurde (``ort``: Plan und Planübung des Abhakens gewinnen).
- **Abgebrochen** (``abbruch``, ``andere_uebung``, ``keine_bewegung``) bleibt der Lauf unter
  „Läufe heute“ mit seinen Sätzen und lässt sich dort eintragen (`lauf_eintragen`).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from trainingsapp.core import zaehlen as zl
from trainingsapp.core import zaehlen_eintrag as ze
from trainingsapp.core.einheit import AUSFUEHRUNG_SCHLUESSEL, Ereignis, Zustand
from trainingsapp.core.models import (
    Exercise,
    Plan,
    PlanItem,
    SessionEntry,
    lokaler_tag,
    tagesgrenzen,
)
from trainingsapp.core.parameter import kontextfelder
from trainingsapp.core.plaene import auspraegung_vorgabe, einzel_plan
from trainingsapp.core.result_spec import basis_key, ist_leer
from trainingsapp.core.standards import aktive_felder, mit_plan_spec
from trainingsapp.core.timer import TimerLauf, TimerProfil
from trainingsapp.core.timer_eintrag import (
    ZEITFELDER,
    Gelaufen,
    abgebrochen,
    ergebnis,
    gelaufene_zeiten,
)
from trainingsapp.core.uebung_timer import (
    mit_zeitfeldern,
    zaehlt_als,
    zeit_werte,
    zeit_zusammenlegen,
)
from trainingsapp.devices.einheit import (
    Einheitslauf,
    TimerBaustein,
    UebungBaustein,
    UebungKontext,
)
from trainingsapp.devices.zaehlen import ZaehlBaustein
from trainingsapp.ui import einheit as einheit_ui
from trainingsapp.ui.components import zaehl_stand
from trainingsapp.ui.einheit import ZaehlMeldung

#: Was eingetragen wird, wenn ein Lauf endet (``teil`` an ``person/eintrag``)
TEIL_UHR = ze.TEIL_UHR
TEIL_ZAEHLEN = ze.TEIL_ZAEHLEN


@dataclass(frozen=True)
class Lauf:
    """Ein Lauf einer Übung — der Uhr, des Zählens oder beider — für „Läufe heute“."""

    einheit_id: str
    beginn: datetime
    zeiten: list[Gelaufen]
    #: abgebrochen: die Uhr — oder, lief keine, das Zählen
    abgebrochen: bool
    #: der Eintrag im Tagebuch — ``None``: nicht eingetragen
    eintrag_id: str | None
    #: was die Uhr eintrug (Haltezeiten bzw. die Zeit)
    werte: list[float]
    #: läuft noch (oder die App starb mitten im Lauf)
    offen: bool = False
    #: Ende des Laufs (UTC) — ``None`` solange er läuft
    ende: datetime | None = None
    #: Wiederholungen je Satz vom Beschleunigungssensor (Sensor plus Korrektur, ohne leere)
    wdh: list[int] = field(default_factory=list)
    #: je gezähltem Satz „Satz 1 · 12 Wdh. (Sensor 11, +1)“ (`core.zaehlen_eintrag.zaehl_text`)
    zaehl_texte: list[str] = field(default_factory=list)
    #: das Zählen brach ab (Abbrechen, andere Übung, keine Bewegung)
    zaehl_abgebrochen: bool = False
    #: welche Teile eingetragen sind (``uhr``, ``zaehlen``)
    eingetragen: frozenset[str] = frozenset()
    #: welche sich noch eintragen lassen (`einzutragen`, nachträglich)
    nachzutragen: frozenset[str] = frozenset()

    @property
    def dauer_s(self) -> float:
        """Was zählte, zusammen — sonst die ganze Laufzeit."""
        zaehlend = [z.sekunden for z in self.zeiten if z.zaehlt]
        return sum(zaehlend) if zaehlend else sum(z.sekunden for z in self.zeiten)

    @property
    def zaehl_text(self) -> str:
        """Die Sätze des Zählens, einer je Zeile — leer ohne gezählten Satz."""
        return "\n".join(self.zaehl_texte)

    @property
    def nachtragbar(self) -> bool:
        """Ob „Eintragen“ etwas einträgt: vorbei, und Zeit oder Wiederholungen fehlen noch."""
        return not self.offen and bool(self.nachzutragen)


def felder_der_uebung(uebung: Exercise, item: PlanItem | None = None) -> list[str]:
    """Welche Parameter die Übung hier anbietet — in einer Planübung die des Plans."""
    if item is not None:
        return [f.key for f in aktive_felder(item, uebung)]
    return [f.key for f in uebung.result_spec.fields]


def kontext_fuer(
    uebung: Exercise,
    plan: Plan | None = None,
    item: PlanItem | None = None,
    *,
    zeit_eintragen: bool | None = None,
    feld: str | None = None,
    auspraegung: Mapping[str, Any] | None = None,
) -> UebungKontext:
    """Wozu der Timer läuft: Übung, Plan, Planübung und das Zeitfeld — ``None``, wenn die
    Timerzeit nicht zählt (nur „gemacht“). Ob sie zählt, legt die Übung fest
    (`Exercise.zeit_zaehlt`, P79 D2); ``zeit_eintragen`` ist die Wahl für jetzt (die Leiste,
    `AppState.uhr_zaehlt`). „Zählt als“ (Ben, 18.10.2026): mit Haltezeit nach der Übung, ohne
    immer Zeit — auch ohne den Parameter (`zaehlt_als`). ``auspraegung``: die Ausführung, die
    im Block gewählt ist (Variante, Gewicht …) — sie kommt mit in den Eintrag (21.10.2026)."""
    eintragen = uebung.zeit_zaehlt if zeit_eintragen is None else zeit_eintragen
    felder = felder_der_uebung(uebung, item)
    if feld and basis_key(feld) in ZEITFELDER and (feld == "duration" or feld in felder):
        gewaehlt: str = feld
    else:
        gewaehlt = zaehlt_als(felder, uebung)
    return UebungKontext(
        uebung_id=uebung.id,
        name=uebung.name,
        plan_id=plan.id if plan is not None else None,
        item_id=item.id if item is not None else None,
        zeitfeld=gewaehlt if eintragen else None,
        auspraegung=dict(auspraegung or {}),
    )


def bereitstellen(
    page: Any, state: Any, kontext: UebungKontext, profil: TimerProfil, *, zeichnen: bool = True
) -> Einheitslauf:
    """Übung und Timer in die Startleiste; eine HRV, die schon aufnimmt, kommt mit (nur
    Marken). Die Einheit endet mit dem Timer.

    Raises:
        RuntimeError: Es läuft schon eine Einheit — auch das Zählen derselben Übung: Ihre Uhr
            tritt ihm mit dem Start bei (`starten`), bereitstellen lässt sie sich nicht.
    """
    if _zaehllauf_von(state, kontext) is not None:
        raise RuntimeError(
            f"{kontext.name}: Das Zählen läuft — die Uhr startet dazu mit ▶, ohne Bereitstellen."
        )
    e = einheit_ui.teil_bereitstellen(page, state, UebungBaustein(kontext), zeichnen=False)
    einheit_ui.timer_bereitstellen(page, state, TimerLauf(profil), zeichnen=False)
    lauf = state.messlauf
    if lauf is not None and lauf.aufnahme is not None and e.hrv is None:
        einheit_ui.hrv_bereitstellen(page, state, zeichnen=False)
    e.ende_mit_timer = True
    if zeichnen:
        state.neu_zeichnen()
    return e


def starten(page: Any, state: Any, kontext: UebungKontext, profil: TimerProfil) -> Einheitslauf:
    """Sofort los — zusammen mit allem, was schon in der Startleiste wartet.

    Zählt schon der Sensor bei dieser Übung (ein Zähllauf ohne Uhr), tritt die Uhr ihm bei:
    eine Einheit, die mit der Uhr endet (Leitentscheidung 2). Zählt er bei einer anderen, endet
    jenes Zählen mit ``andere_uebung`` (`ui.einheit.platz_machen`; die Meldung holt
    `meldung_abholen`).

    Raises:
        RuntimeError: Es läuft schon eine Einheit.
    """
    zaehllauf = _zaehllauf_von(state, kontext)
    if zaehllauf is not None:
        return _uhr_beitreten(page, state, zaehllauf, kontext, profil)
    state.zaehl_meldung = None
    if not einheit_ui.platz_machen(state):
        raise RuntimeError("Es läuft schon eine Einheit — erst oben mit ⏹ beenden.")
    bereitstellen(page, state, kontext, profil, zeichnen=False)  # `alle_starten` zeichnet
    e = einheit_ui.alle_starten(page, state, 0.0)
    assert e is not None
    return e


def _zaehllauf_von(state: Any, kontext: UebungKontext) -> Einheitslauf | None:
    """Der laufende Zähllauf ohne Uhr, wenn er diese Übung ist."""
    e = einheit_ui.laeuft(state)
    if e is None or not einheit_ui.nur_zaehlen(e):
        return None
    u = e.teil("plan")
    if not isinstance(u, UebungBaustein) or not zaehl_stand.passt(
        u.kontext, kontext.uebung_id, kontext.item_id
    ):
        return None
    return e


def _uhr_beitreten(
    page: Any, state: Any, e: Einheitslauf, kontext: UebungKontext, profil: TimerProfil
) -> Einheitslauf:
    """Die Uhr tritt dem Zähllauf ihrer Übung bei — die Einheit endet jetzt mit ihr, das
    Zählen dann als ``fertig`` (bricht die Uhr ab: ``abbruch``). Sie bringt ihre Wahl mit
    (Zeitfeld, Ausführung), denn eingetragen wird mit ihr."""
    u = e.teil("plan")
    if isinstance(u, UebungBaustein):
        u.kontext_setzen(kontext)
    e.ende_mit_timer = True
    e.ende_mit_zaehlen = False
    einheit_ui.teil_beitreten(page, state, e, TimerBaustein(TimerLauf(profil)))
    return e


# ---------------------------------------------------------------------------
# Zählen mit dem Beschleunigungssensor
# ---------------------------------------------------------------------------


def zaehl_baustein(
    state: Any, kontext: UebungKontext, uebung: Exercise, item: PlanItem | None = None
) -> ZaehlBaustein:
    """Der Zähl-Teil, wie die Übung ihn will (Karte „Beschleunigungssensor“): Wiederholungen
    (in einer Planübung nur, wenn sie ein Wiederholungsfeld anbietet), Atmung, das Feld, in das
    gezählt wird (`core.zaehlen.zaehlt_in` — in einer Planübung eines, das sie anbietet), die
    Vorlage der Bewegung."""
    return ZaehlBaustein(
        state.messlauf,
        kontext,
        wiederholungen=zl.wiederholungen_an(uebung, item),
        atmung=zl.atmung_an(uebung),
        feld=zl.zaehlt_in(uebung, item),
        vorlage=uebung.beschleunigung.vorlage,
    )


def zaehlen_starten(
    page: Any,
    state: Any,
    kontext: UebungKontext,
    *,
    uebung: Exercise | None = None,
    item: PlanItem | None = None,
) -> tuple[Einheitslauf, ZaehlMeldung | None]:
    """„Wdh. zählen“ — ab jetzt zählt der Sensor (rückwirkend nichts, P119).

    - Läuft die Uhr dieser Übung, tritt das Zählen ihr bei (Leitentscheidung 2).
    - Zählt er hier schon, bleibt es dabei.
    - Sonst ist es ein eigener Zähllauf: Übung und Zählen, dazu die HRV, wenn sie schon
      aufnimmt; er endet mit dem Zählen (`Einheitslauf.ende_mit_zaehlen`). Zählte er bei einer
      anderen Übung (ohne Uhr), endet jenes Zählen mit ``andere_uebung`` — die zweite Hälfte
      des Ergebnisses ist dann seine Meldung (sonst ``None``).

    ``uebung``/``item``: Übung und Planübung, wenn der Aufrufer sie schon hat (sonst aus dem
    Katalog nach dem Kontext).

    Raises:
        RuntimeError: kein Gerät mit Beschleunigungssensor; an der Übung ist beides aus (in
            einer Planübung: Wiederholungen nur mit einem Wiederholungsfeld des Plans); es
            läuft etwas anderes (die Uhr einer anderen Übung, ein Plan-Ablauf, ein Training)
            oder steht bereit; in diesem Lauf der Uhr wurde schon gezählt.
    """
    if uebung is None:
        uebung = state.uebungen.laden(kontext.uebung_id)
        if uebung is None:
            raise RuntimeError("Die Übung gibt es nicht mehr.")
    if item is None and kontext.item_id:
        item = state.plaene.item_laden(kontext.item_id)
    if not zaehl_stand.geraet_kann_zaehlen(state.messlauf):
        raise RuntimeError("Kein Gerät mit Beschleunigungssensor verbunden.")
    if not zaehl_stand.zaehlen_an(uebung, item):
        if item is not None and zaehl_stand.zaehlen_an(uebung):
            # P79: Die Planübung bietet kein Wiederholungsfeld an (nur abhaken, nur Gewicht …)
            raise RuntimeError(f"„{uebung.name}“ erfasst in diesem Plan keine Wiederholungen.")
        raise RuntimeError(f"An „{uebung.name}“ ist der Beschleunigungssensor aus.")
    e = einheit_ui.laeuft(state)
    if e is not None:
        z = e.teil("zaehlen")
        if (
            isinstance(z, ZaehlBaustein)
            and z.aktiv
            and zaehl_stand.passt(z.kontext, kontext.uebung_id, kontext.item_id)
        ):
            return e, None  # zählt hier schon
        u = e.teil("plan")
        if (
            e.timer is not None
            and isinstance(u, UebungBaustein)
            and zaehl_stand.passt(u.kontext, kontext.uebung_id, kontext.item_id)
        ):
            # Die Uhr dieser Übung läuft: das Zählen tritt bei, die Einheit endet mit der Uhr
            if e.zustand is not Zustand.LAEUFT:
                raise RuntimeError("Die Uhr zählt noch herunter — gleich noch einmal.")
            if z is not None:
                raise RuntimeError(
                    "In diesem Lauf der Uhr wurde schon gezählt — für neue Sätze erst die Uhr "
                    "beenden."
                )
            teil = zaehl_baustein(state, u.kontext, uebung, item)
            einheit_ui.teil_beitreten(page, state, e, teil)
            state.zaehl_laeufe[uebung.id] = e.id
            return e, None
    if einheit_ui.in_vorbereitung(state) is not None:
        raise RuntimeError("Es steht eine Einheit bereit — erst oben starten oder leeren.")
    state.zaehl_meldung = None
    if not einheit_ui.platz_machen(state):
        raise RuntimeError("Es läuft schon eine Einheit — erst oben mit ⏹ beenden.")
    meldung = meldung_abholen(state)
    e = einheit_ui.teil_bereitstellen(page, state, UebungBaustein(kontext), zeichnen=False)
    einheit_ui.teil_bereitstellen(
        page, state, zaehl_baustein(state, kontext, uebung, item), zeichnen=False
    )
    lauf = state.messlauf
    if lauf.aufnahme is not None and e.hrv is None:
        einheit_ui.hrv_bereitstellen(page, state, zeichnen=False)  # nur Marken
    e.ende_mit_zaehlen = True
    gestartet = einheit_ui.alle_starten(page, state, 0.0)  # zeichnet
    assert gestartet is not None
    state.zaehl_laeufe[uebung.id] = gestartet.id
    return gestartet, meldung


def meldung_abholen(state: Any) -> ZaehlMeldung | None:
    """Die Meldung „Kniebeuge · 12 Wdh. nicht eingetragen“, wenn ein Start eben ein Zählen
    beendete (`ui.einheit.platz_machen`) — einmal; danach ``None``."""
    meldung = getattr(state, "zaehl_meldung", None)
    state.zaehl_meldung = None
    return meldung if isinstance(meldung, ZaehlMeldung) else None


def laufendes_zaehlen(
    state: Any, uebung_id: str, item_id: str | None = None
) -> tuple[Einheitslauf, ZaehlBaustein] | None:
    """Die laufende Einheit und ihr Zähl-Teil, solange er bei dieser Übung zählt."""
    z = zaehl_stand.zaehl_teil(state, uebung_id, item_id, nur_aktiv=True)
    e = einheit_ui.laeuft(state)
    return (e, z) if z is not None and e is not None else None


def zaehlen_beenden(
    state: Any,
    uebung_id: str,
    item_id: str | None = None,
    grund: str = zl.ENDE_FERTIG,
    *,
    ort: tuple[str | None, str | None] | None = None,
) -> SessionEntry | None:
    """Das Zählen dieser Übung endet jetzt — „Fertig“ (``fertig``), „Zählen abbrechen“
    (``abbruch``) oder die Übung wird abgehakt (``abgehakt``, `core.zaehlen.ENDE_*`). Die
    Beschleunigung ist sofort frei, die Ereignisse stehen sofort in der Zeitleiste; ein
    Zähllauf ohne Uhr endet damit. Ein Wechsel der Ansicht beendet nichts — dies ruft nur ein
    Knopf.

    Eingetragen wird am Ende der Einheit (`nach_dem_ende`), mit der Zeit der Uhr, wenn sie
    mitlief. **Abgehakt** trägt sofort ein (Leitentscheidung 7): die Wiederholungen in den
    offenen Eintrag (`SessionRepo.lauf_eintragen`), ``person/eintrag`` mit ``teil`` „zaehlen“
    über `Einheitslauf.nachtragen` — die Oberfläche schließt danach diesen Eintrag
    (`SessionRepo.eintrag_schliessen`) statt einen zweiten „gemacht“ zu stempeln. Gibt dann
    den Eintrag zurück; ``None``, wenn nichts zählte, nichts gezählt wurde oder nicht abgehakt.

    ``ort``: (Plan, Planübung), wo abgehakt wird — ``(None, None)`` ohne Plan (Übungsseite).
    **Der Kontext des Abhakens gewinnt** (`_ort_uebernehmen`): Begann das Zählen auf der
    Übungsseite und wird auf „Heute“ am Chip eines Plans abgehakt, landet der Eintrag im Plan,
    nicht in der Sitzung ohne Plan — und mit ihm, was die Uhr derselben Einheit noch einträgt.
    ``None``: wo der Lauf begann.
    """
    gefunden = laufendes_zaehlen(state, uebung_id, item_id)
    if gefunden is None:
        return None
    e, z = gefunden
    if grund == zl.ENDE_ABGEHAKT and ort is not None:
        grund = _ort_uebernehmen(state, e, z, ort)
    if not z.abbrechen(grund):
        return None
    e.takt()  # holt Satz und Ende ab — ein Zähllauf für sich endet damit
    einheit_ui.melden(state)
    if grund != zl.ENDE_ABGEHAKT or e.zeitbasis is None:
        return None
    if TEIL_ZAEHLEN not in einzutragen(e.ereignisse):
        return None  # nichts gezählt: das Abhaken stempelt „gemacht“ wie sonst
    u = e.teil("plan")
    kontext = u.kontext if isinstance(u, UebungBaustein) else z.kontext
    return _eintragen(
        state,
        e.id,
        e.subject_id,
        kontext,
        e.ereignisse,
        e.zeitbasis.anker_utc,
        teile={TEIL_ZAEHLEN},
        einheit=e,
    )


def _ort_uebernehmen(
    state: Any, e: Einheitslauf, z: ZaehlBaustein, ort: tuple[str | None, str | None]
) -> str:
    """Abgehakt wird anderswo, als das Zählen begann: Übung (samt Uhr) und Zählen nehmen den
    Plan und die Planübung des Abhakens an — eingetragen wird dort (`_eintragen` liest sie aus
    dem Kontext), die Beteiligungen nennen sie für „Läufe heute“. Gibt den Ende-Grund zurück.

    Bietet die Planübung dort kein Wiederholungsfeld an (P79: keiner = nur abhaken), gehören
    die Wiederholungen nicht hinein: Das Zählen endet als **abgebrochen** (``abbruch``), bleibt
    unter „Läufe heute“ nachtragbar, wo es begann, und das Abhaken stempelt wie sonst — nie
    stehen sie still in einem Feld, das der Plan nicht anbietet."""
    plan_id, item_id = ort
    u = e.teil("plan")
    uebung_teil = u if isinstance(u, UebungBaustein) else None
    alt = uebung_teil.kontext if uebung_teil is not None else z.kontext
    if (alt.plan_id, alt.item_id) == (plan_id, item_id):
        return zl.ENDE_ABGEHAKT
    if z.wdh and item_id:
        uebung = state.uebungen.laden(z.kontext.uebung_id)
        item = state.plaene.item_laden(item_id)
        if uebung is not None and item is not None and not zl.wdh_felder(uebung, item):
            return zl.ENDE_ABBRUCH
    if uebung_teil is not None:
        uebung_teil.kontext_setzen(replace(uebung_teil.kontext, plan_id=plan_id, item_id=item_id))
    z.kontext_setzen(replace(z.kontext, plan_id=plan_id, item_id=item_id))
    return zl.ENDE_ABGEHAKT


# ---------------------------------------------------------------------------
# Eintragen
# ---------------------------------------------------------------------------


def einzutragen(ereignisse: list[Ereignis], *, nachtraeglich: bool = False) -> frozenset[str]:
    """Welche Teile eines Laufs noch ins Tagebuch gehören — nie, was schon drinsteht
    (`core.zaehlen_eintrag.eingetragen`).

    Am Ende (``nachtraeglich=False``): die Zeit, wenn die Uhr lief und nicht abbrach; die
    Wiederholungen, wenn welche gezählt wurden und das Zählen ``fertig`` oder ``abgehakt``
    endete — bricht die Uhr ab, ist der ganze Lauf abgebrochen (Leitentscheidung 6). Später
    („Eintragen“ unter „Läufe heute“) alles, was fehlt.

    >>> ab = Ereignis(0.0, "timer", "abschnitt", "Halten", {"name": "Halten"})
    >>> satz = Ereignis(20.0, "zaehlen", "zaehlung", "", {"satz": 1, "wert": 12})
    >>> ende = lambda g: Ereignis(20.0, "zaehlen", "zaehlen_ende", "", {"grund": g})
    >>> sorted(einzutragen([ab, satz, ende("fertig")]))
    ['uhr', 'zaehlen']
    >>> sorted(einzutragen([satz, ende("abbruch")])), sorted(einzutragen([satz, ende("abbruch")],
    ...     nachtraeglich=True))
    ([], ['zaehlen'])
    >>> abbruch = Ereignis(30.0, "timer", "ende", "", {"grund": "abgebrochen"})
    >>> sorted(einzutragen([ab, satz, ende("fertig"), abbruch]))
    []
    >>> drin = Ereignis(31.0, "person", "eintrag", "", {"teil": "zaehlen"})
    >>> sorted(einzutragen([ab, satz, ende("abgehakt"), drin]))
    ['uhr']
    """
    schon = ze.eingetragen(ereignisse)
    uhr_abgebrochen = abgebrochen(ereignisse)
    teile: set[str] = set()
    if (
        any(x.quelle == "timer" for x in ereignisse)
        and TEIL_UHR not in schon
        and (nachtraeglich or not uhr_abgebrochen)
    ):
        teile.add(TEIL_UHR)
    if ze.wiederholungen(ereignisse) and TEIL_ZAEHLEN not in schon:
        am_ende = ze.zaehl_ende(ereignisse) in zl.EINGETRAGEN and not uhr_abgebrochen
        if nachtraeglich or am_ende:
            teile.add(TEIL_ZAEHLEN)
    return frozenset(teile)


def nach_dem_ende(state: Any, e: Einheitslauf, kontext: UebungKontext) -> SessionEntry | None:
    """Nach dem Lauf: ins Tagebuch, was die Uhr lief und der Sensor zählte — in einem Eintrag,
    und nur, was noch nicht drinsteht (`einzutragen`); abgebrochen: nichts."""
    if e.zeitbasis is None:
        return None
    teile = einzutragen(e.ereignisse)
    if not teile:
        return None
    return _eintragen(
        state,
        e.id,
        e.subject_id,
        kontext,
        e.ereignisse,
        e.zeitbasis.anker_utc,
        teile=teile,
        einheit=e,
    )


def _zaehl_feld(uebung: Exercise, item: PlanItem | None, ereignisse: list[Ereignis]) -> str | None:
    """Das Feld der Wiederholungen: das der Zählung, wenn die (Plan-)Übung es anbietet — sonst
    ihr erstes Wiederholungsfeld (`core.zaehlen.zaehlt_in`). ``None``, wenn die Planübung keins
    anbietet (P79: keiner = nur abhaken) — dann kommt keine Wiederholung in den Eintrag, auch
    wenn die Übung im Katalog eins hat."""
    felder = set(zl.wdh_felder(uebung, item))
    for z in ze.zaehlungen(ereignisse):
        if (feld := z.get("feld")) in felder:
            return str(feld)
    return zl.zaehlt_in(uebung, item)


def _eintragen(
    state: Any,
    einheit_id: str,
    subject_id: str | None,
    kontext: UebungKontext,
    ereignisse: list[Ereignis],
    anker_utc: datetime,
    *,
    teile: Collection[str] = (TEIL_UHR,),
    einheit: Einheitslauf | None = None,
) -> SessionEntry | None:
    """``teile``: was eingetragen wird — die Zeit der Uhr (``uhr``), die Wiederholungen
    (``zaehlen``) oder beides in einen Eintrag. ``einheit``: die Einheit, wenn sie noch im
    Speicher ist — dann schreibt sie ``person/eintrag`` selbst (`Einheitslauf.nachtragen`; ihre
    Nummern liefen sonst mit einer eigenen zusammen)."""
    uebung = state.uebungen.laden(kontext.uebung_id, mit_geloeschten=True)
    if uebung is None:
        return None
    item = state.plaene.item_laden(kontext.item_id) if kontext.item_id else None
    if item is not None:
        uebung = mit_plan_spec(item, uebung)
    werte: dict[str, Any] = dict(ausfuehrung(uebung, kontext.auspraegung))
    # Die Planübung entscheidet, welches Wiederholungsfeld es gibt (vor `mit_zeitfeldern`)
    feld = _zaehl_feld(uebung, item, ereignisse) if TEIL_ZAEHLEN in teile else None
    if TEIL_UHR in teile:
        werte.update(ergebnis(gelaufene_zeiten(ereignisse), kontext.zeitfeld))
        werte = zeit_zusammenlegen(uebung, werte)  # ins Zeitfeld der Übung (27.10.2026)
        uebung = mit_zeitfeldern(uebung, werte)  # Zeit auch ohne den Parameter (18.10.2026)
    wdh = ze.wiederholungen(ereignisse, feld) if feld else []
    if wdh and feld:
        werte[feld] = list(wdh)  # ein Wert je Satz; ohne Sätze die Summe (`lauf_eintragen`)
    if TEIL_UHR not in teile and not wdh:
        return None  # nichts gezählt — und keine Uhr, die „gemacht“ eintrüge
    ende_s = max(
        (x.t_s for x in ereignisse if x.quelle in ("timer", "plan", "einheit", "zaehlen")),
        default=0.0,
    )
    beginn = anker_utc
    tag = lokaler_tag(beginn)
    sitzung = state.sitzungen.session_fuer(subject_id or state.profil.id, kontext.plan_id, tag)
    # In den offenen Eintrag wie ein Tipp (P79 D1) — die Ausführung trennt wie dort
    eintrag: SessionEntry = state.sitzungen.lauf_eintragen(
        sitzung,
        uebung,
        werte,
        tag,
        ausfuehrung(uebung, kontext.auspraegung),
        beginn=beginn,
        ende=beginn + timedelta(seconds=ende_s),
    )
    # In die Zeitleiste, was eingetragen wurde — „Läufe heute“ liest es zurück, und nichts
    # kommt zweimal hinein (``teil``)
    neu: list[Ereignis] = []
    if TEIL_UHR in teile:
        daten: dict[str, Any] = {
            "eintrag": eintrag.id,
            "werte": zeit_werte(uebung, werte),
            "teil": TEIL_UHR,
        }
        if kontext.zeitfeld:
            daten["zeitfeld"] = kontext.zeitfeld
        neu.append(Ereignis(ende_s, "person", "eintrag", uebung.name, daten))
    if wdh:
        neu.append(
            Ereignis(
                ende_s,
                "person",
                "eintrag",
                uebung.name,
                {"eintrag": eintrag.id, "werte": list(wdh), "feld": feld, "teil": TEIL_ZAEHLEN},
            )
        )
    _zeitleiste(state, einheit_id, neu, einheit)
    return eintrag


def _zeitleiste(
    state: Any, einheit_id: str, neu: list[Ereignis], einheit: Einheitslauf | None
) -> None:
    """``person/eintrag`` in die Zeitleiste — über die Einheit, solange sie im Speicher ist,
    sonst ans Ende ihrer gespeicherten Ereignisse."""
    if einheit is not None and einheit.id == einheit_id and einheit.t0 is not None:
        for x in neu:
            einheit.nachtragen(x)
        return
    if state.einheiten is None or not neu:
        return
    nr = len(state.einheiten.ereignisse(einheit_id))
    state.einheiten.ereignisse_schreiben(einheit_id, [(nr + i, x) for i, x in enumerate(neu)])


def _uebung_teil(teile: list[Any], uebung_id: str | None = None) -> Any:
    """Die Beteiligung, die die Übung nennt: die der Uhr bzw. Übung (``plan``), sonst die des
    Zählens — mit ``uebung_id`` nur für diese Übung."""
    for art in ("plan", "zaehlen"):
        for b in teile:
            if b.art != art or not b.daten.get("uebung"):
                continue
            if uebung_id is None or b.daten.get("uebung") == uebung_id:
                return b
    return None


def laeufe_heute(state: Any, uebung_id: str, tag: Any = None) -> list[Lauf]:
    """Die Läufe einer Übung an einem Tag (Vorgabe heute) — der Uhr, des Zählens oder beider;
    neueste zuerst."""
    if state.einheiten is None:
        return []
    tag = tag or lokaler_tag(datetime.now().astimezone())
    laeufe: list[Lauf] = []
    # Nur ab dem Beginn des Tages (die Zählzeile fragt je Block): was später begann, sortiert
    # die Schleife nach dem lokalen Tag aus
    for kopf in state.einheiten.alle(state.profil.id, seit=tagesgrenzen(tag)[0]):
        kopf_tag = lokaler_tag(kopf.started_at)
        if kopf_tag < tag:
            break  # neueste zuerst: ab hier nur ältere Tage
        if kopf_tag != tag:
            continue
        teile = state.einheiten.beteiligungen(kopf.id)
        if _uebung_teil(teile, uebung_id) is None:
            continue
        ereignisse = state.einheiten.ereignisse(kopf.id)
        eintraege = [x for x in ereignisse if x.quelle == "person" and x.art == "eintrag"]
        uhr_eintrag = next(
            (x for x in eintraege if (x.daten.get("teil") or TEIL_UHR) == TEIL_UHR), None
        )
        uhr = any(b.art == "timer" for b in teile) or any(x.quelle == "timer" for x in ereignisse)
        zaehl_abgebrochen = ze.zaehl_abgebrochen(ereignisse)
        laeufe.append(
            Lauf(
                einheit_id=kopf.id,
                beginn=kopf.started_at,
                zeiten=gelaufene_zeiten(ereignisse),
                abgebrochen=abgebrochen(ereignisse) or (not uhr and zaehl_abgebrochen),
                eintrag_id=str(eintraege[0].daten.get("eintrag")) if eintraege else None,
                werte=list(uhr_eintrag.daten.get("werte") or []) if uhr_eintrag else [],
                offen=kopf.ended_at is None,
                ende=kopf.ended_at,
                wdh=ze.wiederholungen(ereignisse),
                zaehl_texte=ze.zaehl_texte(ereignisse),
                zaehl_abgebrochen=zaehl_abgebrochen,
                eingetragen=ze.eingetragen(ereignisse),
                nachzutragen=einzutragen(ereignisse, nachtraeglich=True),
            )
        )
    return laeufe


def lauf_eintragen(state: Any, einheit_id: str) -> SessionEntry | None:
    """Einen abgebrochenen Lauf doch eintragen — mit der Zeit, die er lief (Skizze 15), und
    den Wiederholungen, die der Sensor zählte; nur, was noch fehlt (``None``: nichts)."""
    kopf = state.einheiten.laden(einheit_id) if state.einheiten is not None else None
    if kopf is None:
        return None
    teil = _uebung_teil(state.einheiten.beteiligungen(einheit_id))
    if teil is None:
        return None
    ereignisse = state.einheiten.ereignisse(einheit_id)
    teile = einzutragen(ereignisse, nachtraeglich=True)
    if not teile:
        return None  # schon eingetragen
    d = teil.daten
    kontext = UebungKontext(
        uebung_id=str(d["uebung"]),
        name=str(d.get("name") or ""),
        plan_id=str(d["plan"]) if d.get("plan") else None,
        item_id=str(d["planuebung"]) if d.get("planuebung") else None,
        zeitfeld=str(d["zeitfeld"]) if d.get("zeitfeld") else None,
        auspraegung={k: d[k] for k in AUSFUEHRUNG_SCHLUESSEL if k in d},
    )
    # Läuft die Einheit noch (Uhr läuft, das Zählen brach ab), schreibt sie selbst
    e = getattr(state, "einheit", None)
    einheit = e if isinstance(e, Einheitslauf) and e.id == einheit_id else None
    return _eintragen(
        state,
        einheit_id,
        kopf.subject_id,
        kontext,
        ereignisse,
        kopf.started_at,
        teile=teile,
        einheit=einheit,
    )


def ausfuehrung(uebung: Exercise, auspraegung: Mapping[str, Any]) -> dict[str, Any]:
    """Die Ausführung, soweit die Übung (wie die Planübung sie sieht) ihre Felder als
    Ausprägung kennt — was sie nicht anbietet, kommt nicht in den Eintrag.

    >>> from trainingsapp.core.result_spec import ResultSpec, vorrat_feld
    >>> u = Exercise(result_spec=ResultSpec(fields=[vorrat_feld("weight"), vorrat_feld("hold")]))
    >>> ausfuehrung(u, {"weight": 10, "side": "links", "hold": [30]})
    {'weight': 10}
    """
    keys = {f.key for f in kontextfelder(uebung.result_spec)}
    return {k: v for k, v in auspraegung.items() if k in keys and not ist_leer(v)}


def gewaehlte_ausfuehrung(state: Any, uebung: Exercise, item: PlanItem | None) -> dict[str, Any]:
    """Die Ausführung, die der Block dieser (Plan-)Übung zeigt — gewählt, sonst aus dem Ziel,
    sonst wie zuletzt (`core.plaene.auspraegung_vorgabe`); ohne Planübung die der einzelnen
    Übung (`einzel_plan`). Uhr, Timer und Ablauf tragen sie mit ein (Ben, 21.10.2026)."""
    planuebung = item if item is not None else einzel_plan(uebung).items[0]
    return auspraegung_vorgabe(
        state.auspraegung_wahl,
        planuebung,
        mit_plan_spec(planuebung, uebung),
        lambda: state.sitzungen.letzter_eintrag(state.profil.id, uebung.id),
    )


__all__ = [
    "TEIL_UHR",
    "TEIL_ZAEHLEN",
    "Lauf",
    "ZaehlMeldung",
    "ausfuehrung",
    "bereitstellen",
    "einzutragen",
    "felder_der_uebung",
    "gewaehlte_ausfuehrung",
    "kontext_fuer",
    "laeufe_heute",
    "lauf_eintragen",
    "laufendes_zaehlen",
    "meldung_abholen",
    "nach_dem_ende",
    "starten",
    "zaehl_baustein",
    "zaehlen_beenden",
    "zaehlen_starten",
]
