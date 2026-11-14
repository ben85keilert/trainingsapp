"""Experimentelle Kennzahlen — die eine Stelle für ihre Kennzeichnung (Ben, 14.11.2026).

Ben: „DFA a1 dagegen ist sehr experimentell“ und „DFA a1 kennzeichnen mit experimentell“.
DFA α1 bleibt in App und Web-Fassung sichtbar, in Solo wie im Patientenmodus — aber unter
jedem Namen, unter dem die Oberfläche es zeigt, steht dabei, dass es experimentell ist: nicht
gesichert, keine Grundlage für Entscheidungen (`docs/recht/00_zweckbestimmung.md`,
„HF-Auswertung und DFA α1“).

**Regel:** Wer eine experimentelle Kennzahl anzeigt, nimmt ihren Namen von hier — nie als
eigenes Literal.

- **Kurz** („DFA α1 (exp.)“), wo wenig Platz ist: Kachel, Spaltenkopf, Zeile einer Tabelle,
  Legende, Achse.
- **Ausgeschrieben** („DFA α1 (experimentell)“), wo erklärt, gewählt oder vorgeschlagen wird:
  Einstellungen, Überschrift einer Karte, Schwellen-Vorschlag, Quelle eines Profilwerts.
- **Der Hinweissatz** (`HINWEIS`) gehört in jeden Erklärtext zu der Kennzahl.

Fließtext, der auf derselben Karte unter einem gekennzeichneten Namen steht, wiederholt die
Marke nicht. Die Kennzeichnung ersetzt keine andere Regel: Auch ein experimenteller Wert wird
nicht bewertet und steuert nichts. Sie gilt in beiden Fassungen gleich — keine Abzweigung für
den Browser.

Der Name selbst kommt aus `hrv_core.trends.KENNZAHLEN` (Schwesterrepo, auch von praxis_gui
genutzt) und bleibt dort, wie er ist; gekennzeichnet wird in der Anzeige der App.
"""

from __future__ import annotations

from typing import Final

from hrv_core import trends
from hrv_core.constants import PNN_THRESHOLD_MS

#: Schlüssel der Verlaufskennzahlen (`hrv_core.trends.KENNZAHLEN`), die experimentell sind
EXPERIMENTELL: Final[frozenset[str]] = frozenset({"dfa_alpha1"})

WORT: Final[str] = "experimentell"
KURZ: Final[str] = "exp."

#: DFA α1 — der Name ohne Marke (nur für Text, der die Marke selbst setzt), kurz und lang
DFA: Final[str] = "DFA α1"
DFA_KURZ: Final[str] = f"{DFA} ({KURZ})"
DFA_LANG: Final[str] = f"{DFA} ({WORT})"

#: Der eine Satz für Erklärtexte
HINWEIS: Final[str] = (
    "Experimentell: DFA α1 und alles, was die App daraus vorschlägt, ist nicht gesichert."
)


def gekennzeichnet(name: str, lang: bool = False) -> str:
    """``name`` mit der Marke — kurz oder ausgeschrieben.

    >>> gekennzeichnet("DFA α1"), gekennzeichnet("DFA α1", lang=True)
    ('DFA α1 (exp.)', 'DFA α1 (experimentell)')
    >>> gekennzeichnet("DFA α1") == DFA_KURZ, gekennzeichnet("DFA α1", lang=True) == DFA_LANG
    (True, True)
    """
    return f"{name} ({WORT if lang else KURZ})"


def anzeigename(kennzahl: str, name: str, lang: bool = False) -> str:
    """Der Name einer Kennzahl für die Anzeige: experimentelle gekennzeichnet, alle anderen
    unverändert.

    >>> anzeigename("dfa_alpha1", "DFA α1"), anzeigename("rmssd", "RMSSD")
    ('DFA α1 (exp.)', 'RMSSD')
    >>> anzeigename("dfa_alpha1", "DFA α1", lang=True)
    'DFA α1 (experimentell)'
    """
    return gekennzeichnet(name, lang) if kennzahl in EXPERIMENTELL else name


def titel(kennzahl: str, pnn_ms: float = PNN_THRESHOLD_MS, lang: bool = False) -> str:
    """Anzeigename einer Verlaufskennzahl — wie `hrv_core.trends.titel`, experimentelle
    gekennzeichnet. Die Oberfläche nimmt diese Funktion statt der aus hrv-core.

    >>> titel("dfa_alpha1"), titel("rmssd"), titel("pnnx", 20)
    ('DFA α1 (exp.)', 'RMSSD', 'pNN20')
    """
    return anzeigename(kennzahl, trends.titel(kennzahl, pnn_ms), lang)


def mit_hinweis(text: str) -> str:
    """Ein Erklärtext, ergänzt um den Hinweissatz.

    >>> mit_hinweis("DFA α1 braucht 100 Schläge.").endswith(HINWEIS)
    True
    >>> mit_hinweis("")
    'Experimentell: DFA α1 und alles, was die App daraus vorschlägt, ist nicht gesichert.'
    """
    return f"{text} {HINWEIS}".strip()


__all__ = [
    "DFA",
    "DFA_KURZ",
    "DFA_LANG",
    "EXPERIMENTELL",
    "HINWEIS",
    "KURZ",
    "WORT",
    "anzeigename",
    "gekennzeichnet",
    "mit_hinweis",
    "titel",
]
