"""Zielbereich, Tonfolge und Wertebereich der Herzfrequenz-Sicht (Ben, 10.11.2026, A22;
Vertrag `docs/plan_hf_vollbild.md`).

Reine Rechnung für die Ansichten (`ui/hf_live.py`, Vollbild, Messansicht, Fokus):

- **Zielbereich**: zwei selbst gesetzte Linien in bpm (`HfEinstellungen.alarm_bpm` oben,
  `ziel_unten_bpm` unten). Außerhalb klingt ein Ton — darüber ein anderer als darunter —,
  und die **Tonfolge wird mit dem Abstand schneller** (`tonfolge_s`). Ein Ton als
  Information wie bei einem Timer, **keine Steuerung und keine Wertung**
  (`docs/recht/00_zweckbestimmung.md`, Entscheidung C): die App sagt nur, wo die Zahl zu den
  eigenen Linien liegt.
- **Stumm**: für eine Zeit oder bis zum Ende der Messung (`Stumm`).
- **Wertebereich der Achse**: oben und unten je für sich (`wertebereich`).
- **Trend** der letzten Minute und die Zeit zwischen den Linien — nur Zahlen.

>>> [tonfolge_s(a) for a in (0, 0.4, 1, 4.9, 5, 8, 12, 15, 40)]
[None, 6.0, 6.0, 6.0, 4.0, 3.0, 2.0, 1.0, 1.0]
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from trainingsapp.core.hf_einstellungen import (
    ACHSE_AUTO,
    ACHSE_FEST,
    ACHSE_PROFIL,
    ALARM_MAX_BPM,
    ALARM_MIN_BPM,
    TAKT_NACH_ABSTAND,
    HfEinstellungen,
)

#: Tonfolge nach Abstand zum Zielbereich: ab so vielen bpm alle so viele Sekunden
TONFOLGE: Final[tuple[tuple[float, float], ...]] = (
    (1.0, 6.0),
    (5.0, 4.0),
    (8.0, 3.0),
    (12.0, 2.0),
    (15.0, 1.0),
)
#: Kleinster Abstand der beiden Linien (bpm) — sie tauschen nie die Seiten
ZIEL_SPANNE_MIN: Final[float] = 2.0
#: Stumm-Zeiten zum Antippen (s); `BIS_MESSENDE` = bis die Messung endet
STUMM_ZEITEN_S: Final[tuple[int, ...]] = (300, 900)
BIS_MESSENDE: Final[float] = math.inf
#: Trend: Steigung über so viele Sekunden, ab so vielen Werten
TREND_S: Final[float] = 60.0
TREND_MIN_WERTE: Final[int] = 10
#: Die Achse zeigt nie weniger als so viele bpm
ACHSE_SPANNE_MIN: Final[float] = 20.0


def tonfolge_s(abstand_bpm: float) -> float | None:
    """Sekunden zwischen zwei Tönen bei diesem Abstand zum Zielbereich — None innerhalb.

    Stufen statt einer Formel, damit man sie nachlesen kann (`TONFOLGE`): bis unter 5 bpm
    alle 6 s, ab 5 alle 4 s, ab 8 alle 3 s, ab 12 alle 2 s, ab 15 jede Sekunde.

    >>> tonfolge_s(-3), tonfolge_s(7.9), tonfolge_s(15)
    (None, 4.0, 1.0)
    """
    if abstand_bpm <= 0:
        return None
    takt = TONFOLGE[0][1]
    for ab, sekunden in TONFOLGE:
        if abstand_bpm >= ab:
            takt = sekunden
    return takt


def abstand(hf: float | None, oben: float | None, unten: float | None) -> float:
    """Abstand zum Zielbereich in bpm: positiv darüber, negativ darunter, 0 darin.

    >>> abstand(156, 150, 130), abstand(121, 150, 130), abstand(140, 150, 130)
    (6.0, -9.0, 0.0)
    >>> abstand(99, 150, None)
    0.0
    """
    if hf is None:
        return 0.0
    if oben is not None and hf > oben:
        return float(hf - oben)
    if unten is not None and hf < unten:
        return float(hf - unten)
    return 0.0


def lage_text(hf: float | None, e: HfEinstellungen) -> str:
    """„156 · 6 über dem Zielbereich“ — leer im Zielbereich oder ohne ihn.

    >>> e = HfEinstellungen(alarm_an=True, alarm_bpm=150, ziel_unten_bpm=130)
    >>> lage_text(156, e), lage_text(121.4, e), lage_text(140, e)
    ('156 · 6 über dem Zielbereich', '121 · 9 unter dem Zielbereich', '')
    """
    oben, unten = ziel_grenzen(e)
    a = abstand(hf, oben, unten)
    if hf is None or a == 0:
        return ""
    return f"{hf:.0f} · {abs(a):.0f} {'über' if a > 0 else 'unter'} dem Zielbereich"


def ziel_grenzen(e: HfEinstellungen) -> tuple[float | None, float | None]:
    """``(oben, unten)`` — die gesetzten Linien, auch bei ausgeschaltetem Ton.

    >>> ziel_grenzen(HfEinstellungen(alarm_bpm=150, ziel_unten_bpm=130))
    (150.0, 130.0)
    """
    return (
        float(e.alarm_bpm) if e.alarm_bpm else None,
        float(e.ziel_unten_bpm) if e.ziel_unten_bpm else None,
    )


def ziel_text(e: HfEinstellungen) -> str:
    """„130–150“, „bis 150“, „ab 130“ — leer ohne Linien.

    >>> ziel_text(HfEinstellungen(alarm_bpm=150, ziel_unten_bpm=130))
    '130–150'
    >>> ziel_text(HfEinstellungen(alarm_bpm=150)), ziel_text(HfEinstellungen())
    ('bis 150', '')
    """
    oben, unten = ziel_grenzen(e)
    if oben is not None and unten is not None:
        return f"{unten:.0f}–{oben:.0f}"
    if oben is not None:
        return f"bis {oben:.0f}"
    if unten is not None:
        return f"ab {unten:.0f}"
    return ""


def ziel_setzen(
    e: HfEinstellungen, *, oben: float | None = None, unten: float | None = None
) -> None:
    """Eine oder beide Linien setzen — geklemmt auf den erlaubten Bereich; die Linie, die
    gesetzt wird, schiebt die andere vor sich her (`ZIEL_SPANNE_MIN`).

    >>> e = HfEinstellungen(alarm_bpm=150, ziel_unten_bpm=130)
    >>> ziel_setzen(e, unten=155); (e.alarm_bpm, e.ziel_unten_bpm)
    (157.0, 155.0)
    >>> ziel_setzen(e, oben=500, unten=10); (e.alarm_bpm, e.ziel_unten_bpm)
    (230.0, 40.0)
    >>> ziel_setzen(e, oben=40); (e.alarm_bpm, e.ziel_unten_bpm)
    (42.0, 40.0)
    >>> ziel_setzen(e, unten=230); (e.alarm_bpm, e.ziel_unten_bpm)
    (230.0, 228.0)
    """

    def klemmen(w: float) -> float:
        return float(min(max(round(w), ALARM_MIN_BPM), ALARM_MAX_BPM))

    # Am Anschlag bleibt der Mindestabstand: die gesetzte Linie weicht selbst zurück, statt
    # auf der anderen zu liegen (H105: ``oben=40`` ergab 40/40)
    if oben is not None:
        e.alarm_bpm = klemmen(oben)
        if e.ziel_unten_bpm:
            e.alarm_bpm = max(e.alarm_bpm, ALARM_MIN_BPM + ZIEL_SPANNE_MIN)
            e.ziel_unten_bpm = min(e.ziel_unten_bpm, e.alarm_bpm - ZIEL_SPANNE_MIN)
    if unten is not None:
        e.ziel_unten_bpm = klemmen(unten)
        if e.alarm_bpm:
            e.ziel_unten_bpm = min(e.ziel_unten_bpm, ALARM_MAX_BPM - ZIEL_SPANNE_MIN)
            e.alarm_bpm = max(e.alarm_bpm, e.ziel_unten_bpm + ZIEL_SPANNE_MIN)
            if e.alarm_bpm - e.ziel_unten_bpm < ZIEL_SPANNE_MIN:
                e.ziel_unten_bpm = e.alarm_bpm - ZIEL_SPANNE_MIN


@dataclass
class Stumm:
    """Der Ton schweigt — bis ``bis`` (Uhr des Aufrufers, s) oder, mit `BIS_MESSENDE`, solange
    die Messung ``messung`` dieselbe bleibt.

    >>> s = Stumm(bis=100.0, messung=7)
    >>> s.gilt(99.0, 7), s.gilt(100.0, 7), s.gilt(50.0, 8)
    (True, False, False)
    >>> Stumm(bis=BIS_MESSENDE, messung=7).text(0.0), s.text(40.0)
    ('stumm bis Messende', 'stumm noch 1:00')
    """

    bis: float
    messung: int

    def gilt(self, jetzt: float, messung: int) -> bool:
        return messung == self.messung and jetzt < self.bis

    def text(self, jetzt: float) -> str:
        if math.isinf(self.bis):
            return "stumm bis Messende"
        rest = max(0, math.ceil(self.bis - jetzt))
        return f"stumm noch {rest // 60}:{rest % 60:02d}"


@dataclass
class Zielton:
    """Wann ein Ton fällig ist — eine Uhr für alle Ansichten (Messung, Vollbild, Fokus), damit
    ein Wechsel der Ansicht die Tonfolge nicht verdoppelt.

    >>> e = HfEinstellungen(alarm_an=True, alarm_bpm=150, ziel_unten_bpm=130)
    >>> z = Zielton()
    >>> z.faellig(156, e, 10.0), z.faellig(156, e, 13.0), z.faellig(156, e, 14.0)
    ('schale', None, 'schale')
    >>> z.faellig(120, e, 17.5), z.faellig(140, e, 30.0), z.faellig(170, e, 31.0, stumm=True)
    ('glocke3', None, None)
    >>> fest = HfEinstellungen(alarm_an=True, alarm_bpm=150, alarm_takt_s=10)
    >>> y = Zielton()
    >>> y.faellig(190, fest, 0.0), y.faellig(190, fest, 9.0), y.faellig(190, fest, 10.0)
    ('schale', None, 'schale')
    """

    zuletzt: float = -math.inf

    def faellig(
        self, hf: float | None, e: HfEinstellungen, jetzt: float, *, stumm: bool = False
    ) -> str | None:
        """Der Klang, der jetzt zu spielen ist — None im Zielbereich, ohne Schalter, stumm
        oder wenn der letzte Ton noch nicht lange genug her ist."""
        if hf is None or stumm or not e.alarm_an:
            return None
        a = abstand(hf, e.alarm_grenze(), e.ziel_unten())
        if a == 0:
            return None
        takt = tonfolge_s(abs(a)) if e.alarm_takt_s == TAKT_NACH_ABSTAND else float(e.alarm_takt_s)
        if takt is None or jetzt - self.zuletzt < takt - 1e-6:
            return None
        self.zuletzt = jetzt
        return e.alarm_klang if a > 0 else e.alarm_klang_tief


def wertebereich(
    e: HfEinstellungen,
    ruhe_bpm: float | None,
    hfmax_bpm: float | None,
    werte: Sequence[float] = (),
) -> tuple[float | None, float | None]:
    """``(unten, oben)`` der HF-Achse, **je Seite für sich** — None heißt Automatik (die
    Kurve bestimmt die Seite).

    Profil: unten die Ruhe-HF, oben die HFmax; fehlt der Wert im Profil, gilt Automatik.
    Eine gesetzte Seite weicht der Kurve: liegt ein Wert darüber bzw. darunter, reicht die
    Achse bis dorthin — nichts wird abgeschnitten. Liegen beide Seiten fest und zu eng
    (`ACHSE_SPANNE_MIN`), rückt die obere.

    >>> e = HfEinstellungen()
    >>> wertebereich(e, 52, 186, [110, 150]), wertebereich(e, None, 186, [110, 150])
    ((52.0, 186.0), (None, 186.0))
    >>> f = HfEinstellungen(achse_oben="auto", achse_unten="fest", achse_unten_bpm=60)
    >>> wertebereich(f, 52, 186, [110, 150]), wertebereich(f, 52, 186, [55, 150])
    ((60.0, None), (55.0, None))
    >>> g = HfEinstellungen(achse_oben="fest", achse_oben_bpm=180, achse_unten="auto")
    >>> wertebereich(g, 52, 186, [110, 191])
    (None, 191.0)
    """

    def seite(modus: str, profil: float | None, fest: float) -> float | None:
        if modus == ACHSE_FEST:
            return float(fest)
        if modus == ACHSE_PROFIL and profil:
            return float(profil)
        return None

    unten = seite(e.achse_unten, ruhe_bpm, e.achse_unten_bpm)
    oben = seite(e.achse_oben, hfmax_bpm, e.achse_oben_bpm)
    if werte:
        if unten is not None:
            unten = min(unten, float(min(werte)))
        if oben is not None:
            oben = max(oben, float(max(werte)))
    if unten is not None and oben is not None and oben - unten < ACHSE_SPANNE_MIN:
        oben = unten + ACHSE_SPANNE_MIN
    return unten, oben


def achse_text(e: HfEinstellungen, ruhe_bpm: float | None, hfmax_bpm: float | None) -> str:
    """„Achse 52 – Automatik“ für die Beschriftung des Knopfs.

    >>> achse_text(HfEinstellungen(achse_oben="auto"), 52, 186)
    'Achse 52 – Automatik'
    """
    unten, oben = wertebereich(e, ruhe_bpm, hfmax_bpm)

    def t(w: float | None) -> str:
        return "Automatik" if w is None else f"{w:.0f}"

    return f"Achse {t(unten)} – {t(oben)}"


def trend_bpm_min(punkte: Sequence[tuple[float, float]], jetzt_s: float) -> float | None:
    """Steigung der Herzfrequenz über die letzten `TREND_S` in bpm je Minute (Ausgleichsgerade)
    — None mit zu wenigen Werten oder wenn sie weniger als die halbe Spanne decken.

    >>> round(trend_bpm_min([(t, 100 + t / 20) for t in range(0, 61, 2)], 60.0), 1)
    3.0
    >>> trend_bpm_min([(59.0, 100.0), (60.0, 101.0)], 60.0) is None
    True
    """
    im = [(t, w) for t, w in punkte if jetzt_s - TREND_S <= t <= jetzt_s]
    if len(im) < TREND_MIN_WERTE or im[-1][0] - im[0][0] < TREND_S / 2:
        return None
    n = len(im)
    mt = sum(t for t, _ in im) / n
    mw = sum(w for _, w in im) / n
    nenner = sum((t - mt) ** 2 for t, _ in im)
    if nenner <= 0:
        return None
    return sum((t - mt) * (w - mw) for t, w in im) / nenner * 60.0


def trend_text(steigung: float | None) -> str:
    """„↗ +3 bpm/min“, „↘ −4 bpm/min“, „→ gleichbleibend“ — leer ohne Wert.

    >>> trend_text(3.2), trend_text(-4.4), trend_text(0.3), trend_text(None)
    ('↗ +3 bpm/min', '↘ −4 bpm/min', '→ gleichbleibend', '')
    """
    if steigung is None:
        return ""
    if abs(steigung) < 1.0:
        return "→ gleichbleibend"
    if steigung > 0:
        return f"↗ +{steigung:.0f} bpm/min"
    return f"↘ −{abs(steigung):.0f} bpm/min"


def zeit_im_ziel(
    punkte: Sequence[tuple[float, float]], oben: float | None, unten: float | None
) -> tuple[float, float]:
    """``(Sekunden zwischen den Linien, Sekunden mit Wert)`` aus einer Kurve im festen oder
    losen Raster — jeder Wert zählt bis zum nächsten, höchstens 5 s (eine Lücke zählt nicht).

    >>> zeit_im_ziel([(0, 120), (1, 131), (2, 140), (3, 151), (4, 150)], 150, 130)
    (2.0, 4.0)
    """
    drin = gesamt = 0.0
    for (t, w), (t2, _) in pairwise(punkte):
        dt = min(max(t2 - t, 0.0), 5.0)
        gesamt += dt
        if abstand(w, oben, unten) == 0:
            drin += dt
    return drin, gesamt


def ziel_anteil_text(drin_s: float, gesamt_s: float) -> str:
    """„4:10 · 62 %“ — „–“ ohne Werte.

    >>> ziel_anteil_text(250, 403), ziel_anteil_text(0, 0)
    ('4:10 · 62 %', '–')
    """
    if gesamt_s <= 0:
        return "–"
    s = round(drin_s)
    return f"{s // 60}:{s % 60:02d} · {drin_s / gesamt_s * 100:.0f} %"


# ---------------------------------------------------------------------------
# Abgelesene Erholung (`hrv_core.herzfrequenz.intervall_erholung`) — nur die Texte
# ---------------------------------------------------------------------------

#: Ab so vielen bpm über dem tiefsten Wert weist die Ansicht darauf hin
UEBER_TAL_HINWEIS_BPM: Final[float] = 3.0
BEZUG_NAMEN: Final[dict[str, str]] = {"spitze": "Spitze", "anfang": "Anfang"}


def _bpm(w: float | None) -> str:
    return "–" if w is None else f"{w:.0f}"


def dauer_kurz(sekunden: float | None) -> str:
    """„95 s“ bis unter zwei Minuten, darüber „2:05“.

    >>> dauer_kurz(95.4), dauer_kurz(125), dauer_kurz(None)
    ('95 s', '2:05', '–')
    """
    if sekunden is None:
        return "–"
    s = round(sekunden)
    return f"{s} s" if s < 120 else f"{s // 60}:{s % 60:02d}"


def hrr_text(hrr: float | None, x_s: float | None) -> str:
    """„HRR 95 s: −31 bpm“ — ein Anstieg trägt ein Plus; „–“ ohne Wert.

    >>> hrr_text(31.2, 95), hrr_text(-4, 30), hrr_text(None, None)
    ('HRR 95 s: −31 bpm', 'HRR 30 s: +4 bpm', 'HRR –')
    """
    if hrr is None or x_s is None:
        return "HRR –"
    zeichen = "−" if hrr >= 0 else "+"
    return f"HRR {dauer_kurz(x_s)}: {zeichen}{abs(hrr):.0f} bpm"


def delta_text(delta: float | None) -> str:
    """„Δ −36“ (gefallen), „Δ +4“.

    >>> delta_text(-36.2), delta_text(4), delta_text(None)
    ('Δ −36', 'Δ +4', 'Δ –')
    """
    if delta is None:
        return "Δ –"
    return f"Δ {'−' if delta < 0 else '+'}{abs(delta):.0f}"


def tal_hinweis(ueber_tal: float | None, tal_zeit: str) -> str:
    """„Ende liegt 5 bpm über dem tiefsten Wert (bei 1:12)“ — leer unter
    `UEBER_TAL_HINWEIS_BPM`.

    >>> tal_hinweis(5.2, "1:12"), tal_hinweis(2.0, "1:12")
    ('Ende liegt 5 bpm über dem tiefsten Wert (bei 1:12)', '')
    """
    if ueber_tal is None or ueber_tal <= UEBER_TAL_HINWEIS_BPM:
        return ""
    return f"Ende liegt {ueber_tal:.0f} bpm über dem tiefsten Wert (bei {tal_zeit})"


def intervall_notiz(
    hrr: float | None, x_s: float | None, von_hf: float | None, bis_hf: float | None, bezug: str
) -> str:
    """Der Text der Notiz zu einer abgelesenen Erholung.

    >>> intervall_notiz(39.4, 87, 151.2, 111.8, "spitze")
    'HRR 87 s: −39 bpm (151 → 112, ab Spitze)'
    """
    return (
        f"{hrr_text(hrr, x_s)} ({_bpm(von_hf)} → {_bpm(bis_hf)}, "
        f"ab {BEZUG_NAMEN.get(bezug, bezug)})"
    )


__all__ = [
    "ACHSE_AUTO",
    "ACHSE_FEST",
    "ACHSE_PROFIL",
    "BEZUG_NAMEN",
    "BIS_MESSENDE",
    "STUMM_ZEITEN_S",
    "TONFOLGE",
    "UEBER_TAL_HINWEIS_BPM",
    "ZIEL_SPANNE_MIN",
    "Stumm",
    "Zielton",
    "abstand",
    "achse_text",
    "dauer_kurz",
    "delta_text",
    "hrr_text",
    "intervall_notiz",
    "lage_text",
    "tal_hinweis",
    "tonfolge_s",
    "trend_bpm_min",
    "trend_text",
    "wertebereich",
    "zeit_im_ziel",
    "ziel_anteil_text",
    "ziel_grenzen",
    "ziel_setzen",
    "ziel_text",
]
