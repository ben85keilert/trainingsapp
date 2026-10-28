"""Werte über der Hauptkurve — als ruhige Übersicht (Vorgabe) oder als Kacheln.

Welche Werte, in welcher Reihenfolge und welche groß hervorgehoben sind, stellt
man unter Einstellungen → HRV-Messung ein — vollständig. Werte einer
Verlaufskurve tragen deren Farbe (Punkt bzw. Streifen) und rechnen mit
demselben Fenster wie die Kurve (`core.hrv_ansicht.Ansicht`). Gerechnet wird
nicht hier: Die Werte kommen fertig herein (`KachelWert`).

**Übersicht:** Die großen Werte stehen oben in einer Reihe, die übrigen
darunter als Liste — Name links, Wert rechts, feine Linien dazwischen. Gibt es
keinen Wert (Atemfrequenz bei undeutlicher Atmung), steht der Grund klein unter
dem Namen; manchmal mit einem Knopf, der weiterhilft („Atemübung").

**Feste Höhen** auch in der Übersicht (Ben, 26.10.2026): Die Atemfrequenz hat mal
einen Wert, mal einen Grund — kam eine Zeile dazu oder fiel weg, sprang die ganze
Ansicht darunter und flackerte. Jede Zeile und jeder große Wert ist darum gleich hoch,
der Grund bleibt einzeilig.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import flet as ft
from hrv_core.atmung import ATEMUEBUNG, RUHE, kurzgrund
from hrv_core.trends import KENNZAHLEN, aktuell, atmung_aktuell, titel

from trainingsapp.core.hrv_ansicht import Ansicht
from trainingsapp.core.hrv_einstellungen import HrvEinstellungen
from trainingsapp.devices.base import Verbindung
from trainingsapp.devices.messlauf import Messlauf
from trainingsapp.ui.components.verlauf import fenster_text
from trainingsapp.ui.farben import FARBEN

#: Feste Höhen — ein gleichmäßiges Raster statt Kacheln, die je nach Inhalt springen
HOEHE = 74
HOEHE_GROSS = 90
#: Übersicht: Höhe einer Zeile (Name, darunter ggf. der Grund) und eines großen Werts
ZEILE_HOEHE = 44
HAUPTWERT_HOEHE = 84


@dataclass(frozen=True, slots=True)
class KachelArt:
    """Ein wählbarer Wert."""

    titel: str
    #: Schlüssel der Verlaufskurve, deren aktuellen Wert er zeigt
    kennzahl: str | None = None
    erklaerung: str = ""


def _aus_kurve(kennzahl: str) -> KachelArt:
    k = KENNZAHLEN[kennzahl]
    return KachelArt(k.titel, kennzahl=kennzahl, erklaerung=k.erklaerung)


#: Alle Werte. Schlüssel bleiben stabil — sie stehen in den Einstellungen.
KACHELN: dict[str, KachelArt] = {
    "hf": KachelArt("Herzfrequenz", erklaerung="Zuletzt vom Gerät gemeldet."),
    "rr": KachelArt("RR", erklaerung="Letzter Abstand zweier Herzschläge."),
    "artefakte": KachelArt(
        "Artefakte", erklaerung="Markierte Schläge im Puffer bzw. korrigierte in der Messung."
    ),
    "schwankung": KachelArt(
        "Schwankung 60 s",
        erklaerung="Mittlere Spannweite der Herzfrequenz je 10 s — beschreibend, keine Bewertung.",
    ),
    **{k: _aus_kurve(k) for k in ("atemfrequenz", "rsa")},
    **{k: _aus_kurve(k) for k in ("hf_rr", "mean_rr", "rmssd", "sdnn", "pnnx")},
    **{k: _aus_kurve(k) for k in ("lf_power", "hf_power", "lf_hf", "gipfel", "vlf_power")},
    # ULF braucht Stunden (mindestens 4 h) — nur als Wert der ganzen Aufzeichnung
    "ulf": KachelArt(
        "ULF-Band",
        erklaerung="Leistung unter 0,003 Hz — Tagesrhythmus. Erst ab 4 h Messung, "
        "nur in der Aufzeichnung.",
    ),
    **{k: _aus_kurve(k) for k in ("sd1", "sd2", "dfa_alpha1")},
}

#: Gruppen für die Auswahl in den Einstellungen
GRUPPEN: list[tuple[str, list[str]]] = [
    ("Grundwerte", ["hf", "rr", "artefakte"]),
    ("Atmung", ["atemfrequenz", "rsa", "schwankung"]),
    ("Zeit", ["hf_rr", "mean_rr", "rmssd", "sdnn", "pnnx"]),
    ("Frequenz", ["lf_power", "hf_power", "lf_hf", "gipfel", "vlf_power", "ulf"]),
    ("Nichtlinear", ["sd1", "sd2", "dfa_alpha1"]),
]


@dataclass(frozen=True, slots=True)
class KachelWert:
    """Was ein Wert der Übersicht (oder eine Kachel) zeigt."""

    titel: str
    wert: str
    einheit: str = ""
    zusatz: str = ""
    farbe: str | None = None
    gross: bool = False
    #: Warum es keinen Wert gibt („Atemschwankung zu schwach")
    grund: str = ""
    #: Ein Knopf, der weiterhilft: (Beschriftung, Handler)
    aktion: tuple[str, Callable[[], object]] | None = None


#: Kacheln, die auch ohne Intervalle etwas zeigen — der Puls und seine Schwankung
PULS_KACHELN = frozenset({"hf", "schwankung"})
#: Grund in allen anderen, wenn das Gerät nur den Puls sendet (Ben, 17.10.2026)
NUR_PULS_GRUND = "Gerät sendet nur den Puls"


def ohne_intervalle(w: KachelWert) -> KachelWert:
    """Die Kachel eines reinen Pulsgebers: kein Wert, dafür der Grund.

    Ohne Intervalle hieße „zu wenige gute Schläge“ etwas anderes, als es ist.

    >>> w = ohne_intervalle(KachelWert("RMSSD 30 s", "42", "ms"))
    >>> w.wert, w.grund
    ('–', 'Gerät sendet nur den Puls')
    """
    return replace(w, wert="–", zusatz="", grund=NUR_PULS_GRUND, aktion=None)


def zahl(wert: float | int | None, nachkomma: int = 0) -> str:
    """„–" für fehlende Werte, sonst mit deutschem Komma.

    >>> zahl(None), zahl(12.345, 1), zahl(60)
    ('–', '12,3', '60')
    """
    if wert is None:
        return "–"
    return f"{wert:.{nachkomma}f}".replace(".", ",")


def kachel(w: KachelWert) -> ft.Control:
    # Der Farbstreifen ist ein eigenes Kästchen: Ein Rahmen nur links verträgt
    # sich in Flutter nicht mit runden Ecken.
    inhalt = ft.Container(
        expand=True,
        padding=ft.Padding.only(left=10, right=8, top=8, bottom=8),
        content=ft.Column(
            spacing=2,
            tight=True,
            controls=[
                ft.Text(w.titel, size=11, opacity=0.7, max_lines=1, no_wrap=True),
                ft.Row(
                    spacing=3,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(w.wert, size=28 if w.gross else 19, weight=ft.FontWeight.BOLD),
                        ft.Text(w.einheit, size=11, opacity=0.65),
                    ],
                ),
                ft.Text(
                    w.zusatz or w.grund,
                    size=10,
                    opacity=0.6,
                    max_lines=1,
                    visible=bool(w.zusatz or w.grund),
                ),
            ],
        ),
    )
    return ft.Container(
        col={"xs": 6} if w.gross else {"xs": 4},
        height=HOEHE_GROSS if w.gross else HOEHE,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Row(
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Container(width=4, bgcolor=w.farbe or ft.Colors.TRANSPARENT),
                inhalt,
            ],
        ),
    )


def raster(werte: list[KachelWert]) -> ft.Control:
    """Große Kacheln zu zweit, die übrigen zu dritt — mit gleichmäßigem Abstand."""
    if not werte:
        return ft.Container()
    return ft.ResponsiveRow(spacing=10, run_spacing=10, controls=[kachel(w) for w in werte])


def uebersicht(werte: list[KachelWert]) -> ft.Control:
    """Große Werte oben in einer Reihe, die übrigen als ruhige Liste darunter."""
    if not werte:
        return ft.Container()
    gross = [w for w in werte if w.gross]
    liste = [w for w in werte if not w.gross]
    teile: list[ft.Control] = []
    if gross:
        teile.append(
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[_hauptwert(w) for w in gross],
            )
        )
    for i, w in enumerate(liste):
        if teile or i:
            teile.append(
                ft.Divider(
                    height=1,
                    thickness=0.5,
                    color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
                )
            )
        teile.append(_zeile(w))
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        border_radius=16,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
        content=ft.Column(spacing=6, tight=True, controls=teile),
    )


def _hauptwert(w: KachelWert) -> ft.Control:
    return ft.Container(
        expand=True,
        height=HAUPTWERT_HOEHE,
        padding=ft.Padding.only(bottom=4),
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                ft.Row(
                    spacing=4,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(w.wert, size=34, weight=ft.FontWeight.BOLD, color=w.farbe),
                        ft.Text(w.einheit, size=13, opacity=0.65),
                    ],
                ),
                ft.Text(w.titel, size=12, opacity=0.7, max_lines=1),
                # Immer da, auch leer — so bleibt die Höhe, wenn der Grund kommt oder geht
                ft.Text(
                    w.grund or w.zusatz,
                    size=11,
                    opacity=0.55,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
        ),
    )


def _zeile(w: KachelWert) -> ft.Control:
    links: list[ft.Control] = [
        ft.Text(w.titel, size=14, max_lines=1),
    ]
    if w.grund:
        links.append(
            ft.Text(w.grund, size=11, opacity=0.6, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        )
    rechts: list[ft.Control] = []
    if w.aktion is not None:
        text, handler = w.aktion
        rechts.append(
            ft.TextButton(
                text,
                on_click=handler,
                style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8)),
            )
        )
    rechts.append(
        ft.Row(
            spacing=3,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.END,
            controls=[
                ft.Text(w.wert, size=17, weight=ft.FontWeight.W_600),
                ft.Text(f"{w.einheit} {w.zusatz}".strip(), size=12, opacity=0.65),
            ],
        )
    )
    return ft.Container(
        height=ZEILE_HOEHE,
        content=ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=8,
                    height=8,
                    border_radius=4,
                    bgcolor=w.farbe or ft.Colors.TRANSPARENT,
                ),
                ft.Column(spacing=0, tight=True, expand=True, controls=links),
                *rechts,
            ],
        ),
    )


def anzeige(werte: list[KachelWert], darstellung: str) -> ft.Control:
    """Übersicht oder Kacheln — wie eingestellt."""
    return raster(werte) if darstellung == "kacheln" else uebersicht(werte)


def kachel_werte(
    lauf: Messlauf,
    einst: HrvEinstellungen,
    ansicht: Ansicht,
    verity: bool,
    atemuebung_an: Callable[[], object] | None = None,
    *,
    puls_allein: bool = False,
) -> list[KachelWert]:
    """Die eingestellten Werte der Übersicht mit den aktuellen Live-Werten.

    Werte einer Verlaufskurve rechnen mit deren Fenster — der Wert ist der
    letzte Punkt der Kurve. Die Atemfrequenz gibt es nur bei deutlicher Atmung;
    sonst steht der Grund da (bei langsamer Schwingung mit dem Knopf
    „Atemübung", ``atemuebung_an``). Vom Sensor verworfene Intervalle (Verity
    Sense) erscheinen von selbst, sobald es welche gibt. Sendet das Gerät nur den
    Puls (``puls_allein``, `nur_puls`), sagen die übrigen Kacheln das statt eines
    Grunds, der nicht stimmt (`ohne_intervalle`).
    """
    k = lauf.live.kennzahlen()
    t, rr, naht = lauf.live.verlaufsreihe()
    modus = ATEMUEBUNG if einst.atemuebung else RUHE
    gross = set(einst.gross)
    atmung = None
    out: list[KachelWert] = []
    for key in einst.kacheln:
        art = KACHELN.get(key)
        if art is None:
            continue
        g = key in gross
        bisher = len(out)
        if key == "hf":
            hf = k.hf_bpm if k.hf_bpm is not None else lauf.status.hf_bpm
            out.append(KachelWert("Herzfrequenz", zahl(hf), "bpm", gross=g))
        elif key == "rr":
            out.append(KachelWert("PPI" if verity else "RR", zahl(k.rr_ms), "ms", gross=g))
        elif key == "artefakte":
            out.append(
                KachelWert("Artefakte", str(k.artefakte), zusatz=f"von {k.schlaege}", gross=g)
            )
        elif key == "schwankung":
            out.append(KachelWert(art.titel, zahl(k.schwankung_60s, 1), "bpm", gross=g))
        elif key == "ulf":
            out.append(
                KachelWert(art.titel, "–", "ms²", gross=g, grund="ab 4 h, in der Aufzeichnung")
            )
        elif key in ("atemfrequenz", "rsa"):
            kz = KENNZAHLEN[key]
            fenster = ansicht.fenster_fuer(key, kz.fenster_s)
            if atmung is None:
                atmung = atmung_aktuell(t, rr, fenster, atem_modus=modus)
            wert = atmung.rate_pro_min if key == "atemfrequenz" else atmung.rsa_bpm
            grund = "" if atmung.gueltig else kurzgrund(atmung.gruende)
            aktion = None
            if key == "atemfrequenz" and atemuebung_an is not None:
                if einst.atemuebung:
                    aktion = ("Atemübung aus", atemuebung_an)
                elif "langsame Schwingung" in grund:
                    aktion = ("Atemübung", atemuebung_an)
            out.append(
                KachelWert(
                    f"{kz.titel} {fenster_text(fenster)}",
                    zahl(wert if atmung.gueltig else None, kz.nachkomma),
                    kz.einheit,
                    farbe=FARBEN[key],
                    gross=g,
                    grund=grund,
                    aktion=aktion,
                )
            )
        elif art.kennzahl is not None:
            kz = KENNZAHLEN[art.kennzahl]
            fenster = ansicht.fenster_fuer(art.kennzahl, kz.fenster_s)
            wert = (
                aktuell(t, rr, naht, art.kennzahl, fenster, pnn_ms=ansicht.pnn_ms)
                if t.size
                else None
            )
            out.append(
                KachelWert(
                    f"{titel(art.kennzahl, ansicht.pnn_ms)} {fenster_text(fenster)}",
                    zahl(wert, kz.nachkomma),
                    kz.einheit,
                    farbe=FARBEN[art.kennzahl],
                    gross=g,
                )
            )
        if puls_allein and key not in PULS_KACHELN and len(out) > bisher:
            out[-1] = ohne_intervalle(out[-1])
    if k.verworfen:
        zusatz = (
            "vom Sensor · selbst geprüft"
            if lauf.regeln.selbst_pruefen
            else f"vom Sensor · von {k.schlaege + k.verworfen}"
        )
        out.append(KachelWert("Verworfen", str(k.verworfen), zusatz=zusatz))
    return out


def leisten_werte(state: Any) -> list[KachelWert]:
    """Die Werte für die Laufleiste im Live-Vollbild (Ben, 28.10.2026: „die aktuellen Werte
    für Gerätetransmit (RR, HF, PPG) und das, was zusätzlich zur Kurve dazugeschaltet ist,
    groß und leserlich … in die Titelzeile“): Herzfrequenz, RR bzw. PPI und je gezeigter
    Verlaufskurve ihr aktueller Wert — mit dem Fenster der Kurve, wie die Kacheln."""
    lauf = getattr(state, "messlauf", None)
    if lauf is None or lauf.status.verbindung == Verbindung.GETRENNT:
        return []
    ansicht = state.ansicht()
    kurven = [
        k for k in (*ansicht.links, *ansicht.rechts) if k in KACHELN and k not in ("hf", "rr")
    ]
    einst = replace(
        state.hrv_einstellungen(), kacheln=["hf", "rr", *dict.fromkeys(kurven)], gross=[]
    )
    verity = bool(lauf.profil and lauf.profil.kann("pmd_ppi"))
    return kachel_werte(lauf, einst, ansicht, verity, puls_allein=lauf.nur_puls())


__all__ = [
    "GRUPPEN",
    "KACHELN",
    "NUR_PULS_GRUND",
    "PULS_KACHELN",
    "KachelArt",
    "KachelWert",
    "anzeige",
    "kachel",
    "kachel_werte",
    "leisten_werte",
    "ohne_intervalle",
    "raster",
    "uebersicht",
    "zahl",
]
