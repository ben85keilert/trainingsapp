"""Verlauf: Kennzahlen, Tageswerte, Zeitachse, Häufigkeit und Trend (core/verlauf.py).

Ben, 17.10.2026 (P37, Variante A + B): eine Kurve je Übung statt zweier Kurvenwelten, die
Kennzahl als Auswahl nur bei mehreren, Datum an der Achse ohne Randwerte (N16).
"""

from __future__ import annotations

from datetime import date

from trainingsapp.core.models import SessionEntry
from trainingsapp.core.result_spec import (
    SPEC_SAETZE_WDH,
    FieldSpec,
    FieldType,
    ResultSpec,
    vorrat_feld,
)
from trainingsapp.core.verlauf import (
    BESTER,
    HOECHSTER,
    MITTEL,
    SUMME,
    datum_marken,
    haeufigkeit,
    kennzahlen,
    tageswerte,
    tageszeilen,
    trend,
    zeitraum_beginn,
)


def _e(spec: ResultSpec, x: str = "u", **werte) -> SessionEntry:
    return SessionEntry(exercise_id=x, result=werte, spec_snapshot=spec)


def test_kennzahlen_folgen_den_feldern_der_uebung() -> None:
    """Satzlisten: Summe und bester Satz; Zeiten ohne Einheit (sie stehen als 1:30 da);
    Skala als Mittel, Gewicht als höchster Wert; ``chart_metrics`` begrenzt die Felder."""
    skala = FieldSpec("stab", FieldType.SCALE, "Stabilität", min=1, max=10, step=1)
    spec = ResultSpec(
        fields=[vorrat_feld("reps"), vorrat_feld("hold"), vorrat_feld("weight"), skala]
    )
    e = _e(spec, reps=[10, 12], hold=[30], weight=20, stab=6)
    ks = kennzahlen([e])
    assert [(k.feld, k.art) for k in ks] == [
        ("reps", SUMME),
        ("reps", BESTER),
        ("hold", SUMME),
        ("hold", BESTER),
        ("weight", HOECHSTER),
        ("stab", MITTEL),
    ]
    halten = ks[3]
    assert halten.label == "Haltezeit – längster Satz" and halten.dauer and halten.einheit == ""
    assert halten.text(90) == "1:30" and ks[0].einheit == "Wdh."
    assert ks[5].hinweis == "1 bis 10, Mittel des Tages"
    nur_reps = ResultSpec(fields=spec.fields, chart_metrics=["reps"])
    assert [k.schluessel for k in kennzahlen([_e(nur_reps, reps=[5], hold=[9])])] == [
        "reps:summe",
        "reps:bester",
    ]


def test_tageswerte_mittel_und_hoechster_wert() -> None:
    skala = FieldSpec("stab", FieldType.SCALE, "Stabilität", min=0, max=10)
    spec = ResultSpec(fields=[vorrat_feld("weight"), skala])
    tag = date(2026, 10, 16)
    tage = [(tag, _e(spec, weight=20, stab=4)), (tag, _e(spec, weight=25, stab=7))]
    gewicht, stab = kennzahlen([e for _, e in tage])
    assert tageswerte(tage, gewicht) == [(tag, 25.0)]
    assert tageswerte(tage, stab) == [(tag, 5.5)]


def test_tageszeilen_mit_varianten_und_abgehakt() -> None:
    """Varianten laufen in einer Zeile zusammen und werden ausgewiesen; ein zusätzliches
    „Gemacht“ ohne Werte steht dahinter."""
    namen = {"lgs": "Liegestützen", "wand": "an der Wand"}
    eintraege = [
        _e(SPEC_SAETZE_WDH, "lgs", reps=[14, 14]),
        _e(SPEC_SAETZE_WDH, "wand", reps=[15]),
    ]
    (z,) = tageszeilen(eintraege, lambda _: "lgs", namen)
    assert z.wert == 43.0 and z.zeile == "3 Sätze · 14 · 14 · 15"
    assert z.zusatz.startswith("davon Liegestützen: 28 Wdh.")
    (z,) = tageszeilen(
        [_e(SPEC_SAETZE_WDH, "lgs", reps=[10]), _e(SPEC_SAETZE_WDH, "lgs")], lambda x: x, namen
    )
    assert z.zusatz == "zusätzlich abgehakt"


def test_zeitachse_ohne_randwerte() -> None:
    """Kurze Spannen je Tag, lange je Monat oder Jahr — der Januar mit Jahreszahl; keine
    Marke am linken Rand und keine im letzten Zwanzigstel rechts (N16)."""
    tage = datum_marken(date(2026, 10, 12), date(2026, 10, 17))
    assert [t for _, t in tage] == ["13.10.", "14.10.", "15.10.", "16.10."]
    winter = datum_marken(date(2026, 10, 20), date(2027, 3, 20))
    assert [t for _, t in winter] == ["Nov", "Dez", "Jan 27", "Feb", "März"]
    jahre = datum_marken(date(2018, 5, 1), date(2026, 10, 17))
    assert jahre[0][1] == "2019" and len(jahre) <= 6
    for von, bis in ((date(2026, 9, 5), date(2026, 10, 17)), (date(2025, 1, 1), date(2026, 1, 1))):
        for tag, _ in datum_marken(von, bis):
            assert von < tag and (tag - von).days <= 0.95 * (bis - von).days


def test_haeufigkeit_ueber_vier_monate_je_monat() -> None:
    tage = [date(2026, 5, 3), date(2026, 5, 9), date(2026, 8, 1)]
    einheit, saeulen = haeufigkeit(tage, date(2026, 4, 1), date(2026, 10, 17))
    assert einheit == "Monat"
    assert [(t, n) for _, t, n in saeulen] == [
        ("Apr", 0),
        ("Mai", 2),
        ("Juni", 0),
        ("Juli", 0),
        ("Aug", 1),
        ("Sep", 0),
        ("Okt", 0),
    ]


def test_trend_und_zeitraum() -> None:
    heute = date(2026, 10, 17)
    weniger = [(date(2026, 9, 10), 50.0), (date(2026, 10, 10), 40.0)]
    assert trend(weniger, heute) == -0.2
    assert trend([(date(2026, 9, 10), 0.0), (date(2026, 10, 10), 4.0)], heute) is None
    assert zeitraum_beginn("unbekannt", heute) == zeitraum_beginn("3m", heute) == date(2026, 7, 19)
