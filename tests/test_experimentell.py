"""DFA α1 ist überall als „experimentell“ gekennzeichnet (Ben, 14.11.2026).

Die Kennzeichnung kommt aus einer Stelle (`core/experimentell.py`). Geprüft wird: Die
Namensquellen der App geben DFA α1 gekennzeichnet aus, und im Quelltext steht der Name nirgends
als eigenes Literal — außer in Fließtext, der unter einem gekennzeichneten Namen steht
(`FLIESSTEXT`). Regel: `docs/recht/00_zweckbestimmung.md`, „HF-Auswertung und DFA α1“.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from trainingsapp.core import experimentell as ex
from trainingsapp.core.hf_profil import QUELLEN
from trainingsapp.core.hrv_einstellungen import ACHSEN_NAMEN
from trainingsapp.core.training_einstellungen import SPALTEN_TEXT
from trainingsapp.core.uhr_seiten import SEITE_HF, SEITEN_NAMEN

QUELLTEXT = Path(__file__).resolve().parents[1] / "src" / "trainingsapp"

#: Fließtext mit „DFA α1“ ohne Marke — je Datei die Zahl der Zeichenketten und warum sie
#: bleiben dürfen. Eine neue Zeichenkette mit dem Namen lässt den Test scheitern: Namen kommen
#: aus `core/experimentell.py`.
FLIESSTEXT: dict[str, tuple[int, str]] = {
    "core/atem_auswertung.py": (1, "Zeile unter dem Überblick „DFA α1 (experimentell)“"),
    "ui/components/analyse.py": (1, "Erklärtext, endet mit dem Hinweissatz (`mit_hinweis`)"),
    "ui/views/ausdauer.py": (
        3,
        "Erklärtext mit Hinweissatz; zwei Hinweise zum Zwischenstand in der Auswertung, deren "
        "Karte „DFA α1 (experimentell) — Überblick“ heißt",
    ),
    "ui/views/messung_detail.py": (2, "Atemlage unter der Tabelle, deren Zeile gekennzeichnet ist"),
}


def test_kennzeichnung_kurz_und_lang() -> None:
    assert ex.DFA_KURZ == "DFA α1 (exp.)" and ex.DFA_LANG == "DFA α1 (experimentell)"
    assert ex.titel("dfa_alpha1") == ex.DFA_KURZ
    assert ex.titel("dfa_alpha1", lang=True) == ex.DFA_LANG
    assert ex.titel("rmssd") == "RMSSD" and ex.titel("pnnx", 20) == "pNN20"  # andere unberührt
    assert ex.HINWEIS.startswith("Experimentell:") and "nicht gesichert" in ex.HINWEIS
    assert ex.mit_hinweis("Text.") == f"Text. {ex.HINWEIS}"


def test_namensquellen_des_kerns_sind_gekennzeichnet() -> None:
    assert SPALTEN_TEXT["dfa"] == ex.DFA_LANG  # Einstellungen → Training, Spalten
    assert ACHSEN_NAMEN["alpha"][0] == ex.DFA_LANG  # Einstellungen → HRV, Achsen
    assert QUELLEN["dfa_alpha1"] == "DFA α1 (Rogers 2021, experimentell)"  # Quelle im Profil
    assert SEITEN_NAMEN[SEITE_HF] == "HF, RR, DFA α1 (exp.)"  # Seiten der Uhr


def test_kachel_und_kurven_sind_gekennzeichnet() -> None:
    pytest.importorskip("flet")
    from trainingsapp.core.hrv_ansicht import Ansicht
    from trainingsapp.ui.components import vollbild
    from trainingsapp.ui.components.kacheln import KACHELN
    from trainingsapp.ui.components.verlauf import bezeichnung

    kachel = KACHELN["dfa_alpha1"]
    assert kachel.titel == ex.DFA_KURZ and kachel.erklaerung.endswith(ex.HINWEIS)
    assert KACHELN["rmssd"].titel == "RMSSD" and ex.HINWEIS not in KACHELN["rmssd"].erklaerung
    assert bezeichnung("dfa_alpha1", Ansicht()).startswith(ex.DFA_KURZ)  # Legende, Ablesewert
    assert vollbild.name("dfa_alpha1", 50.0, "RR") == ex.DFA_KURZ


def _literale(datei: Path) -> list[str]:
    """Zeichenketten einer Datei ohne Docstrings (auch die festen Teile von f-Strings)."""
    baum = ast.parse(datei.read_text(encoding="utf-8"))
    doku = {
        id(k.body[0].value)
        for k in ast.walk(baum)
        if isinstance(k, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and k.body
        and isinstance(k.body[0], ast.Expr)
        and isinstance(k.body[0].value, ast.Constant)
    }
    return [
        k.value
        for k in ast.walk(baum)
        if isinstance(k, ast.Constant) and isinstance(k.value, str) and id(k) not in doku
    ]


def test_der_name_steht_nirgends_als_eigenes_literal() -> None:
    funde: dict[str, int] = {}
    for datei in sorted(QUELLTEXT.rglob("*.py")):
        pfad = datei.relative_to(QUELLTEXT).as_posix()
        if pfad == "core/experimentell.py":
            continue
        if n := sum(1 for text in _literale(datei) if ex.DFA in text):
            funde[pfad] = n
    assert funde == {pfad: n for pfad, (n, _warum) in FLIESSTEXT.items()}, (
        "„DFA α1“ steht als eigenes Literal im Quelltext. Namen, Überschriften, Spaltenköpfe "
        "und Vorschläge nehmen ihn aus core/experimentell.py (DFA_KURZ, DFA_LANG, titel); "
        "Fließtext unter einem gekennzeichneten Namen gehört mit Grund nach FLIESSTEXT."
    )
