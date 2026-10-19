"""Verlauf: Woche, Tag und Übung — was sich aus den Einträgen zeichnen lässt.

Ben, 17.10.2026 (Skizzen zu P37, Variante A + B): oben eine **Woche** statt des
Monats, darunter die Übungen eines Tages; eine Übung öffnet ihre **Kurve mit den
Ergebnissen** je Tag; ein zweiter Reiter listet alle Übungen mit Mini-Kurve und Trend
(`ui/views/verlauf.py`, `verlauf_kachel.py`). Hier steht die Rechnung dazu, ohne
Datenbank und ohne Oberfläche:

- **Kennzahlen** einer Übung (`kennzahlen`): je Feld, das Kurven liefert
  (`ResultSpec.chart_metrics`), der Wert je Tag — Satzlisten als Summe und als bester
  Satz, Skalen als Mittel, Gewicht und Winkel als höchster Wert. Eine Auswahl braucht
  es nur, wenn es mehrere gibt.
- **Tageswerte** (`tageswerte`): ein Wert je Tag — dreimal 50 Liegestütze sind 150.
- Die **Zeitachse** (`datum_marken`) beschriftet Tage, Montage, Monatserste oder Jahre —
  so fein, wie es passt, und nie am Rand (sonst stand „0“ über dem ersten Datum, N16).
- **Häufigkeit** (`haeufigkeit`) für Übungen, die nur abgehakt werden: an wie vielen
  Tagen je Woche bzw. Monat.

Zwei X-Achsen: die **Zeit** (Vorgabe seit 17.10.2026, ein Datum an der Achse) und die
**Trainingsnummer** (gleiche Abstände, egal ob ein Tag oder drei Wochen dazwischen
lagen). Die Nummer wird hier gezählt, nicht gespeichert.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from .models import SessionEntry
from .result_spec import (
    KENNZAHL_TYPEN,
    FieldSpec,
    FieldType,
    ResultSpec,
    basis_label,
    ist_leer,
    kennzahl_keys,
    skala_bereich_text,
)
from .tagesbilanz import kacheln
from .units import format_dauer

MODUS_NUMMER = "nummer"
MODUS_ZEIT = "zeit"

#: Zeiträume der Kurve: Schlüssel → (Beschriftung, Tage bis heute; ``None`` = alles)
ZEITRAEUME: dict[str, tuple[str, int | None]] = {
    "4w": ("4 Wochen", 28),
    "3m": ("3 Monate", 91),
    "jahr": ("Jahr", 365),
    "alles": ("Alles", None),
}
ZEITRAUM_VORGABE = "3m"

WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
WOCHENTAGE_LANG = (
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
)
MONATE = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)
MONATE_KURZ = (
    "Jan",
    "Feb",
    "März",
    "Apr",
    "Mai",
    "Juni",
    "Juli",
    "Aug",
    "Sep",
    "Okt",
    "Nov",
    "Dez",
)

#: Wie ein Tag zu einem Wert wird
SUMME, BESTER, MITTEL, HOECHSTER = "summe", "bester", "mittel", "hoechster"

#: Über so viele Wochen zählt die Häufigkeit je Monat statt je Woche
HAEUFIGKEIT_WOCHEN_MAX = 16


# ---------------------------------------------------------------------------
# Woche und Zeitraum
# ---------------------------------------------------------------------------


def montag(tag: date) -> date:
    """Der Montag der Woche.

    >>> montag(date(2026, 10, 17))  # ein Samstag
    datetime.date(2026, 10, 12)
    """
    return tag - timedelta(days=tag.weekday())


def wochen_titel(beginn: date) -> str:
    """„12. – 18. Oktober“; über Monats- und Jahresgrenzen kurz mit beiden Monaten.

    >>> wochen_titel(date(2026, 10, 12)), wochen_titel(date(2026, 9, 28))
    ('12. – 18. Oktober', '28. Sep – 4. Okt')
    >>> wochen_titel(date(2026, 12, 28))
    '28. Dez – 3. Jan 2027'
    """
    ende = beginn + timedelta(days=6)
    if beginn.month == ende.month:
        return f"{beginn.day}. – {ende.day}. {MONATE[ende.month - 1]}"
    jahr = f" {ende.year}" if beginn.year != ende.year else ""
    links = f"{beginn.day}. {MONATE_KURZ[beginn.month - 1]}"
    return f"{links} – {ende.day}. {MONATE_KURZ[ende.month - 1]}{jahr}"


def tag_titel(tag: date) -> str:
    """„Freitag, 16.10.“ — für die Überschrift des gewählten Tags.

    >>> tag_titel(date(2026, 10, 16))
    'Freitag, 16.10.'
    """
    return f"{WOCHENTAGE_LANG[tag.weekday()]}, {tag:%d.%m.}"


def zeitraum_beginn(zeitraum: str, heute: date) -> date | None:
    """Der erste Tag des Zeitraums (heute zählt mit) — ``None`` bei „Alles“.

    >>> zeitraum_beginn("4w", date(2026, 10, 17)), zeitraum_beginn("alles", date(2026, 10, 17))
    (datetime.date(2026, 9, 20), None)
    """
    tage = ZEITRAEUME.get(zeitraum, ZEITRAEUME[ZEITRAUM_VORGABE])[1]
    return None if tage is None else heute - timedelta(days=tage - 1)


# ---------------------------------------------------------------------------
# Kennzahlen und Tageswerte
# ---------------------------------------------------------------------------


def zahl(wert: float) -> str:
    """Eine Zahl, wie man sie liest: ganze ohne Komma, sonst mit höchstens zwei Stellen.

    >>> zahl(43.0), zahl(2.5), zahl(12500.0), zahl(1.234)
    ('43', '2,5', '12500', '1,23')
    """
    if float(wert).is_integer():
        return str(int(wert))
    return f"{wert:.2f}".rstrip("0").rstrip(".").replace(".", ",")


@dataclass(frozen=True, slots=True)
class Kennzahl:
    """Was eine Kurve zeigt: ein Feld und wie ein Tag zu einem Wert wird (`SUMME` …)."""

    feld: str
    art: str
    #: „Wiederholungen je Tag“, „Haltezeit – längster Satz“
    label: str
    #: „Summe aller Sätze“ — die zweite Zeile in der Auswahl
    hinweis: str
    #: „Wdh.“, „kg“; bei Zeiten leer (sie stehen als „3:06“ da)
    einheit: str = ""
    dauer: bool = False

    @property
    def schluessel(self) -> str:
        return f"{self.feld}:{self.art}"

    def text(self, wert: float) -> str:
        """„3:06“ bei Zeiten, sonst die Zahl: „43“, „2,5“."""
        return format_dauer(wert) if self.dauer else zahl(wert)


def _felder(spec: ResultSpec) -> list[FieldSpec]:
    """Die Felder, aus denen Kurven entstehen — ohne Angabe der Übung alle Zahlenfelder."""
    keys = spec.chart_metrics or kennzahl_keys(spec.fields)
    felder = [spec.field_by_key(k) for k in keys]
    return [f for f in felder if f is not None and f.type in KENNZAHL_TYPEN]


def _kennzahlen_des_felds(f: FieldSpec) -> list[Kennzahl]:
    name = basis_label(f)
    dauer = f.unit == "s" or f.type == FieldType.DURATION
    einheit = "" if dauer else (f.unit or "")
    if f.type == FieldType.SET_LIST and not f.saetze:  # ohne Sätze zählt nur die Summe
        return [Kennzahl(f.key, SUMME, f"{name} je Tag", "Summe des Tages", einheit, dauer)]
    if f.type == FieldType.SET_LIST:
        bester = "längster Satz" if dauer else "bester Satz"
        am_stueck = "am Stück gehalten" if dauer else "die meisten am Stück"
        return [
            Kennzahl(f.key, SUMME, f"{name} je Tag", "Summe aller Sätze", einheit, dauer),
            Kennzahl(f.key, BESTER, f"{name} – {bester}", am_stueck, einheit, dauer),
        ]
    if f.type == FieldType.SCALE:
        return [Kennzahl(f.key, MITTEL, name, f"{skala_bereich_text(f)}, Mittel des Tages")]
    if f.type in (FieldType.DEGREES, FieldType.WEIGHT):
        return [Kennzahl(f.key, HOECHSTER, f"{name} – höchster Wert", "des Tages", einheit)]
    return [Kennzahl(f.key, SUMME, f"{name} je Tag", "Summe des Tages", einheit, dauer)]


def kennzahlen(eintraege: Iterable[SessionEntry]) -> list[Kennzahl]:
    """Was sich zeichnen lässt — nur Felder, in denen auch etwas steht; die Felder in der
    Reihenfolge der jüngsten Spezifikation.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> e = SessionEntry(result={"reps": [15, 15]}, spec_snapshot=SPEC_SAETZE_WDH)
    >>> [k.label for k in kennzahlen([e])]
    ['Wiederholungen je Tag', 'Wiederholungen – bester Satz']
    >>> kennzahlen([SessionEntry(spec_snapshot=SPEC_SAETZE_WDH)])  # nur abgehakt
    []
    """
    gefunden: dict[str, Kennzahl] = {}
    for e in reversed(list(eintraege)):
        if e.spec_snapshot is None:
            continue
        for f in _felder(e.spec_snapshot):
            if ist_leer(e.result.get(f.key)):
                continue
            for k in _kennzahlen_des_felds(f):
                gefunden.setdefault(k.schluessel, k)
    return list(gefunden.values())


def _einzelwerte(e: SessionEntry, feld: str) -> list[float]:
    """Die Zahlen eines Felds in einem Eintrag — eine Satzliste als einzelne Sätze."""
    wert = e.result.get(feld)
    if ist_leer(wert):
        return []
    werte: list[float] = []
    for w in wert if isinstance(wert, list) else [wert]:
        if w is None:
            continue
        try:
            x = float(w)
        except (TypeError, ValueError):
            continue
        if isinstance(wert, list) and x == 0:
            continue  # 0 heißt in einer Satzliste „ohne Angabe“
        werte.append(x)
    return werte


def tageswert(eintraege: Iterable[SessionEntry], k: Kennzahl) -> float | None:
    """Der Wert eines Tages aus seinen Einträgen — ``None``, wenn keiner einen hat."""
    werte: list[float] = []
    for e in eintraege:
        einzeln = _einzelwerte(e, k.feld)
        if einzeln and k.art == SUMME:
            werte.append(sum(einzeln))
        else:
            werte.extend(einzeln)
    if not werte:
        return None
    if k.art == SUMME:
        return float(sum(werte))
    if k.art == MITTEL:
        return round(sum(werte) / len(werte), 2)
    return max(werte)


def tageswerte(
    eintraege: Iterable[tuple[date, SessionEntry]], k: Kennzahl
) -> list[tuple[date, float]]:
    """Ein Wert je Tag, nach Tagen sortiert — Tage ohne Wert (nur abgehakt) fehlen.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> def e(*n): return SessionEntry(result={"reps": list(n)}, spec_snapshot=SPEC_SAETZE_WDH)
    >>> summe, bester = kennzahlen([e(1)])
    >>> tage = [(date(2026, 10, 2), e(50)), (date(2026, 10, 1), e(15, 20)),
    ...         (date(2026, 10, 2), e(30))]
    >>> [w for _, w in tageswerte(tage, summe)], [w for _, w in tageswerte(tage, bester)]
    ([35.0, 80.0], [20.0, 50.0])
    """
    je_tag: dict[date, list[SessionEntry]] = {}
    for tag, e in eintraege:
        je_tag.setdefault(tag, []).append(e)
    werte = ((tag, tageswert(liste, k)) for tag, liste in sorted(je_tag.items()))
    return [(tag, w) for tag, w in werte if w is not None]


def saetze_text(eintraege: Iterable[SessionEntry], k: Kennzahl) -> str:
    """„3 Sätze · 15 · 15 · 13“ — die Sätze eines Tages; leer, wenn das Feld keine Satzliste ist.

    >>> from trainingsapp.core.result_spec import SPEC_HALTEN, SPEC_SAETZE_WDH
    >>> def e(spec, key, *n): return SessionEntry(result={key: list(n)}, spec_snapshot=spec)
    >>> summe, _ = kennzahlen([e(SPEC_SAETZE_WDH, "reps", 1)])
    >>> saetze_text([e(SPEC_SAETZE_WDH, "reps", 15, 15), e(SPEC_SAETZE_WDH, "reps", 13)], summe)
    '3 Sätze · 15 · 15 · 13'
    >>> halten, _ = kennzahlen([e(SPEC_HALTEN, "hold", 65)])
    >>> saetze_text([e(SPEC_HALTEN, "hold", 65)], halten)
    '1 Satz · 1:05'
    """
    saetze: list[float] = []
    for e in eintraege:
        f = e.spec_snapshot.field_by_key(k.feld) if e.spec_snapshot is not None else None
        if f is not None and f.type == FieldType.SET_LIST and f.saetze:
            saetze.extend(_einzelwerte(e, k.feld))
    if not saetze:
        return ""
    wort = "Satz" if len(saetze) == 1 else "Sätze"
    return f"{len(saetze)} {wort} · " + " · ".join(k.text(s) for s in saetze)


def kurven_punkte(
    werte: Sequence[tuple[date, float]], modus: str, von: date | None = None
) -> list[tuple[float, float, date]]:
    """x je Tag: Tage seit ``von`` (Vorgabe: der erste Wert) oder die laufende Nummer.

    >>> w = [(date(2026, 10, 1), 5.0), (date(2026, 10, 8), 6.0)]
    >>> [(x, y) for x, y, _ in kurven_punkte(w, MODUS_ZEIT)]
    [(0.0, 5.0), (7.0, 6.0)]
    >>> [(x, y) for x, y, _ in kurven_punkte(w, MODUS_NUMMER)]
    [(1.0, 5.0), (2.0, 6.0)]
    """
    if not werte:
        return []
    beginn = von or werte[0][0]
    if modus == MODUS_NUMMER:
        return [(float(i + 1), w, tag) for i, (tag, w) in enumerate(werte)]
    return [(float((tag - beginn).days), w, tag) for tag, w in werte]


# ---------------------------------------------------------------------------
# Zeitachse
# ---------------------------------------------------------------------------


def _jeden_tag(von: date, bis: date) -> list[date]:
    return [von + timedelta(days=i) for i in range((bis - von).days + 1)]


def _monatserste(von: date, bis: date, jeder: int) -> list[date]:
    tage = []
    jahr, monat = von.year, von.month
    while date(jahr, monat, 1) <= bis:
        if (monat - 1) % jeder == 0:
            tage.append(date(jahr, monat, 1))
        jahr, monat = (jahr + 1, 1) if monat == 12 else (jahr, monat + 1)
    return [t for t in tage if t >= von]


def _tagestext(tag: date) -> str:
    return f"{tag.day}.{tag.month}."


def _monatstext(tag: date) -> str:
    name = MONATE_KURZ[tag.month - 1]
    return f"{name} {tag.year % 100:02d}" if tag.month == 1 else name


#: Stufen der Zeitachse, von fein nach grob: (Marken zwischen ``von`` und ``bis``, Text)
_STUFEN: tuple[tuple[Callable[[date, date], list[date]], Callable[[date], str]], ...] = (
    (_jeden_tag, _tagestext),
    (lambda v, b: [t for t in _jeden_tag(v, b) if t.weekday() == 0], _tagestext),
    (
        lambda v, b: [
            t for t in _jeden_tag(v, b) if t.weekday() == 0 and (t.toordinal() // 7) % 2 == 0
        ],
        _tagestext,
    ),
    (lambda v, b: _monatserste(v, b, 1), _monatstext),
    (lambda v, b: _monatserste(v, b, 2), _monatstext),
    (lambda v, b: _monatserste(v, b, 3), _monatstext),
    (lambda v, b: _monatserste(v, b, 6), _monatstext),
    (lambda v, b: _monatserste(v, b, 12), lambda t: str(t.year)),
)


def datum_marken(von: date, bis: date, max_marken: int = 6) -> list[tuple[date, str]]:
    """Wo die Zeitachse beschriftet wird: Tage, Montage, Monatserste oder Jahre — so fein,
    wie höchstens ``max_marken`` passen. Nie am linken Rand und nicht im letzten
    Zwanzigstel rechts, wo die Beschriftung abgeschnitten würde.

    >>> [t for _, t in datum_marken(date(2026, 9, 5), date(2026, 10, 17))]
    ['7.9.', '14.9.', '21.9.', '28.9.', '5.10.', '12.10.']
    >>> [t for _, t in datum_marken(date(2026, 4, 20), date(2026, 10, 17))]
    ['Mai', 'Juni', 'Juli', 'Aug', 'Sep', 'Okt']
    >>> [t for _, t in datum_marken(date(2025, 3, 1), date(2026, 10, 17))]
    ['Apr', 'Juli', 'Okt', 'Jan 26', 'Apr', 'Juli']
    >>> datum_marken(date(2026, 10, 17), date(2026, 10, 17))
    []
    """
    spanne = (bis - von).days
    if spanne <= 0:
        return []
    letzter = von + timedelta(days=int(spanne * 0.95))
    erster = von + timedelta(days=1)
    for marken, text in _STUFEN:
        tage = [t for t in marken(erster, letzter) if erster <= t <= letzter]
        if len(tage) <= max_marken:
            return [(t, text(t)) for t in tage]
    jahre = [date(j, 1, 1) for j in range(erster.year + 1, letzter.year + 1)]
    schritt = max(1, -(-len(jahre) // max_marken))
    return [(t, str(t.year)) for t in jahre[::schritt]]


# ---------------------------------------------------------------------------
# Häufigkeit, Überblick, Trend
# ---------------------------------------------------------------------------


def haeufigkeit(
    tage: Iterable[date], von: date, bis: date
) -> tuple[str, list[tuple[date, str, int]]]:
    """An wie vielen Tagen je Woche etwas eingetragen ist — über `HAEUFIGKEIT_WOCHEN_MAX`
    Wochen je Monat: ``(„Woche“ | „Monat“, [(Beginn, Beschriftung, Anzahl)])``.

    >>> tage = [date(2026, 10, 12), date(2026, 10, 17), date(2026, 10, 5), date(2026, 10, 17)]
    >>> einheit, saeulen = haeufigkeit(tage, date(2026, 10, 1), date(2026, 10, 17))
    >>> einheit, [(t, n) for _, t, n in saeulen]
    ('Woche', [('28.9.', 0), ('5.10.', 1), ('12.10.', 2)])
    """
    gezaehlt = {t for t in tage if von <= t <= bis}
    erste_woche = montag(von)
    wochen = (montag(bis) - erste_woche).days // 7 + 1
    if wochen <= HAEUFIGKEIT_WOCHEN_MAX:
        saeulen = []
        for i in range(wochen):
            beginn = erste_woche + timedelta(days=7 * i)
            n = sum(1 for t in gezaehlt if beginn <= t < beginn + timedelta(days=7))
            saeulen.append((beginn, _tagestext(beginn), n))
        return "Woche", saeulen
    monate = _monatserste(date(von.year, von.month, 1), bis, 1)
    saeulen = []
    for beginn in monate:
        n = sum(1 for t in gezaehlt if (t.year, t.month) == (beginn.year, beginn.month))
        saeulen.append((beginn, _monatstext(beginn), n))
    return "Monat", saeulen


@dataclass(frozen=True, slots=True)
class Ueberblick:
    """Die drei Zahlen unter der Kurve."""

    #: der höchste Tageswert und sein Tag (bei Gleichstand der jüngste)
    hoechster: tuple[date, float] | None
    #: Mittel der Tageswerte der letzten vier Wochen
    mittel_4w: float | None
    #: Tage mit der Übung im Zeitraum — auch nur abgehakte
    trainings: int


def ueberblick(werte: Sequence[tuple[date, float]], trainings: int, heute: date) -> Ueberblick:
    """Höchster Wert, Mittel der letzten vier Wochen, Zahl der Trainingstage.

    >>> w = [(date(2026, 9, 1), 30.0), (date(2026, 10, 12), 57.0), (date(2026, 10, 16), 43.0)]
    >>> u = ueberblick(w, 4, date(2026, 10, 17))
    >>> u.hoechster, u.mittel_4w, u.trainings
    ((datetime.date(2026, 10, 12), 57.0), 50.0, 4)
    """
    hoechster = max(werte, key=lambda tw: (tw[1], tw[0])) if werte else None
    seit = heute - timedelta(days=27)
    letzte = [w for t, w in werte if t >= seit]
    mittel = round(sum(letzte) / len(letzte), 1) if letzte else None
    return Ueberblick(hoechster, mittel, trainings)


def je_tag_der_woche(
    eintraege: Iterable[tuple[date, SessionEntry]],
    kachel_von: Callable[[str], str],
    beginn: date,
) -> dict[date, set[str]]:
    """Welche Übungen (Kacheln) an welchem Tag der Woche ab ``beginn`` dran waren.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> mo = date(2026, 10, 12)
    >>> liste = [(mo, SessionEntry(exercise_id="a")), (mo + timedelta(days=8), SessionEntry())]
    >>> je_tag_der_woche(liste, lambda k: k, mo)
    {datetime.date(2026, 10, 12): {'a'}}
    """
    ende = beginn + timedelta(days=6)
    out: dict[date, set[str]] = {}
    for t, e in eintraege:
        if beginn <= t <= ende:
            out.setdefault(t, set()).add(kachel_von(e.exercise_id))
    return out


def kuerzlich(tage: Iterable[date], heute: date, wochen: int) -> int:
    """Wie viele Trainingstage in den letzten ``wochen`` Wochen (heute eingeschlossen) liegen.

    >>> heute = date(2026, 10, 19)
    >>> kuerzlich([heute, heute - timedelta(days=41), heute - timedelta(days=42)], heute, 6)
    2
    """
    seit = heute - timedelta(days=7 * wochen - 1)
    return sum(1 for t in tage if t >= seit)


def ist_neu(werte: Sequence[tuple[date, float]], heute: date, tage: int = 28) -> bool:
    """„neu“: Der erste Wert ist jünger als ``tage`` Tage — zu kurz für einen Trend.

    >>> heute = date(2026, 10, 19)
    >>> ist_neu([(heute - timedelta(days=10), 1.0)], heute), ist_neu([], heute)
    (True, False)
    """
    return bool(werte) and werte[0][0] > heute - timedelta(days=tage)


def saetze_kurz(eintraege: Iterable[SessionEntry], k: Kennzahl) -> str:
    """Nur die Sätze eines Tages ohne die Zählung: „15 · 15 · 13“ (leer wie `saetze_text`).

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> e = SessionEntry(result={"reps": [15, 13]}, spec_snapshot=SPEC_SAETZE_WDH)
    >>> saetze_kurz([e], kennzahlen([e])[0])
    '15 · 13'
    """
    text = saetze_text(eintraege, k)
    return text.split(" · ", 1)[1] if " · " in text else ""


def trend(werte: Sequence[tuple[date, float]], heute: date, tage: int = 28) -> float | None:
    """Das Mittel der letzten ``tage`` gegen das der ``tage`` davor: 0,19 = 19 % mehr.
    ``None``, wenn eine Seite leer ist oder das frühere Mittel 0.

    >>> w = [(date(2026, 9, 10), 30.0), (date(2026, 10, 1), 40.0), (date(2026, 10, 15), 44.0)]
    >>> trend(w, date(2026, 10, 17)), trend(w[1:], date(2026, 10, 17))
    (0.4, None)
    """
    grenze = heute - timedelta(days=tage)
    jetzt = [w for t, w in werte if grenze < t <= heute]
    vorher = [w for t, w in werte if grenze - timedelta(days=tage) < t <= grenze]
    if not jetzt or not vorher or sum(vorher) == 0:
        return None
    a, b = sum(jetzt) / len(jetzt), sum(vorher) / len(vorher)
    return round((a - b) / b, 3)


# ---------------------------------------------------------------------------
# Ein Tag: je Übung eine Zeile
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tageszeile:
    """Eine Übung an einem Tag — Varianten zusammen wie in der Tagesbilanz."""

    kachel_id: str
    #: die erste Kennzahl der Übung — ``None``: nur abgehakt
    kennzahl: Kennzahl | None
    wert: float | None
    #: „3 Sätze · 15 · 15 · 13“, sonst die Zusammenfassung („408 m · 5:05 Zeit“)
    zeile: str
    #: woraus sie besteht (Varianten, Ausprägungen) oder „zusätzlich abgehakt“
    zusatz: str = ""


def tageszeilen(
    eintraege: Iterable[SessionEntry],
    kachel_von: Callable[[str], str],
    namen: dict[str, str],
) -> list[Tageszeile]:
    """Die Übungen eines Tages, in der Reihenfolge ihres ersten Eintrags.

    >>> from trainingsapp.core.result_spec import SPEC_SAETZE_WDH
    >>> def e(x, *n): return SessionEntry(exercise_id=x, result={"reps": list(n)},
    ...                                   spec_snapshot=SPEC_SAETZE_WDH)
    >>> z = tageszeilen([e("lgs", 15, 15), e("lgs", 13), e("kb")], lambda x: x, {})
    >>> [(t.kachel_id, t.wert, t.zeile) for t in z]
    [('lgs', 43.0, '3 Sätze · 15 · 15 · 13'), ('kb', None, 'abgehakt')]
    """
    zeilen = []
    for k in kacheln(eintraege, kachel_von):
        alle = [e for b in k.teile for e in b.eintraege]
        kz = kennzahlen(alle)
        erste = kz[0] if kz else None
        wert = tageswert(alle, erste) if erste is not None else None
        saetze = saetze_text(alle, erste) if erste is not None else ""
        zusatz = k.aufschluesselung(namen)
        if saetze and k.abgehakt and not zusatz:
            zusatz = "zusätzlich abgehakt"
        zeilen.append(Tageszeile(k.kachel_id, erste, wert, saetze or k.zusammenfassung(), zusatz))
    return zeilen


__all__ = [
    "BESTER",
    "HOECHSTER",
    "MITTEL",
    "MODUS_NUMMER",
    "MODUS_ZEIT",
    "MONATE",
    "MONATE_KURZ",
    "SUMME",
    "WOCHENTAGE",
    "WOCHENTAGE_LANG",
    "ZEITRAEUME",
    "ZEITRAUM_VORGABE",
    "Kennzahl",
    "Tageszeile",
    "Ueberblick",
    "datum_marken",
    "haeufigkeit",
    "kennzahlen",
    "kurven_punkte",
    "montag",
    "saetze_text",
    "tag_titel",
    "tageswert",
    "tageswerte",
    "tageszeilen",
    "trend",
    "ueberblick",
    "wochen_titel",
    "zahl",
    "zeitraum_beginn",
]
