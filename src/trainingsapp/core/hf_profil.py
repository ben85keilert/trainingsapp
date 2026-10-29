"""Profilwerte der Herzfrequenz: Ruhe-HF, HFmax, Schwellen — mit Herkunft und Hierarchie.

Ben, 29.10.2026 (hrv-research `docs/KONZEPT_HF_APP.md` §5, Entscheidungen 11–13): Jede
Größe hat einen Verlauf, eine Quelle und eine Unsicherheit. Nichts wird stillschweigend aus
einer Formel gesetzt — die Formel steht als **Startwert** mit ihrer Streuung dabei, bis ein
gemessener oder eingetragener Wert vorliegt. Welcher Eintrag gilt, entscheidet die
Wertehierarchie in `hrv_core.herzfrequenz` (festgesetzt > genaueste Quelle > jüngster),
damit praxis_gui dieselbe Wahl trifft.

Kein flet, kein SQL: Datenmodell und Rechnung; die Tabelle ``profil_wert`` liest
`data/hf_profil.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Final

from hrv_core import herzfrequenz as hz

from trainingsapp.core.hf_einstellungen import MODELL_AUTO, HfEinstellungen
from trainingsapp.core.models import Subject, jetzt, new_id

#: Die Größen im Profil mit Anzeigename
GROESSEN: Final[dict[str, str]] = {
    hz.GROESSE_RUHE: "Ruhe-HF",
    hz.GROESSE_MAX: "HFmax",
    hz.GROESSE_VT1: "Schwelle 1 (VT1)",
    hz.GROESSE_VT2: "Schwelle 2 (VT2)",
}
#: Quellen mit Anzeigename — die Schlüssel sind die aus `hrv_core.herzfrequenz.RANGFOLGE`
QUELLEN: Final[dict[str, str]] = {
    "eintrag": "eingetragen",
    "nacht": "Nacht (tiefstes 2-h-Mittel)",
    "messung_morgen_10": "Morgenmessung 10 min",
    "messung_morgen_5": "Morgenmessung 5 min",
    "tagesminimum": "Tagesminimum (10 min)",
    "tagesfeld": "Tagesfeld „Ruhepuls“",
    "spiroergometrie": "Spiroergometrie",
    "ergometrie": "Ergometrie",
    "laktat": "Laktattest",
    "test_maximal": "Feld-Maximaltest",
    "feldmaximum": "Feldmaximum (höchstes 30-s-Mittel)",
    "formel_nes": "Formel Nes/HUNT",
    "formel_tanaka": "Formel Tanaka",
    "formel_gulati": "Formel Gulati",
    "talk_test": "Talk-Test",
    "schaetzung_milani": "Schätzung (Milani)",
    "prozent_hrr": "% der Reserve (42/77)",
}
#: Quellen, die die Person von Hand einträgt (Formular), je Größe
EINTRAG_QUELLEN: Final[dict[str, tuple[str, ...]]] = {
    hz.GROESSE_RUHE: ("eintrag",),
    hz.GROESSE_MAX: ("eintrag", "ergometrie", "spiroergometrie", "test_maximal"),
    hz.GROESSE_VT1: ("spiroergometrie", "laktat", "talk_test"),
    hz.GROESSE_VT2: ("spiroergometrie", "laktat"),
}
GESCHLECHTER: Final[dict[str, str]] = {"w": "weiblich", "m": "männlich", "d": "divers"}


@dataclass(slots=True)
class Profilwert:
    """Eine Zeile aus ``profil_wert`` — unveränderlich, Korrektur = neue Zeile."""

    subject_id: str
    groesse: str
    wert: float
    quelle: str
    datum: date
    id: str = field(default_factory=new_id)
    einheit: str = "bpm"
    unsicherheit: float | None = None
    fest: bool = False
    geraet: str | None = None
    hrv_recording_id: str | None = None
    #: Herkunftsliste einer Automatik: Fenster, Messungen, Rechenweg (Frage 5)
    herkunft: dict[str, Any] = field(default_factory=dict)
    note: str = ""
    created_at: datetime = field(default_factory=jetzt)
    replaces_id: str | None = None
    deleted_at: datetime | None = None

    def eintrag(self) -> hz.ProfilEintrag:
        """Die Sicht der Wertehierarchie auf diese Zeile."""
        return hz.ProfilEintrag(
            groesse=self.groesse,
            wert=float(self.wert),
            quelle=self.quelle,
            datum=self.datum,
            unsicherheit_bpm=self.unsicherheit,
            fest=self.fest,
            geraet=self.geraet,
            kennung=self.id,
        )

    @property
    def unsicherheit_wirksam(self) -> float:
        return self.eintrag().unsicherheit

    @property
    def quelle_text(self) -> str:
        return QUELLEN.get(self.quelle, self.quelle)

    @property
    def misst(self) -> bool:
        return self.quelle in hz.MESSENDE_QUELLEN


#: Wie weit zurück Einträge des Tagesfelds „Ruhepuls“ in die Hierarchie gehen (Tage)
TAGESFELD_TAGE: Final[int] = 14


def tagesfeld_eintraege(
    subject_id: str,
    werte: Sequence[Any],
    *,
    ausgenommen: set[date] | None = None,
) -> list[Profilwert]:
    """Werte des festen Tagesfelds „Ruhepuls“ als Einträge der Ruhe-HF (Quelle
    ``tagesfeld``, Rang zuletzt) — nicht gespeichert, nur zur Rechnung; ausgenommene Tage
    zählen nicht (Rechen-Ausnahme). ``werte``: `core.tagesfelder.Tageswert` mit ``tag``,
    ``wert``, ``id``, ``zeit``."""
    aus = ausgenommen or set()
    out: list[Profilwert] = []
    for w in werte:
        if w.tag in aus:
            continue
        try:
            bpm = float(w.wert)
        except (TypeError, ValueError):
            continue
        if not 20 <= bpm <= 250:
            continue
        out.append(
            Profilwert(
                subject_id,
                hz.GROESSE_RUHE,
                bpm,
                "tagesfeld",
                w.tag,
                id=f"tagesfeld:{w.id}",
                herkunft={"tagesfeld": w.id},
                created_at=w.zeit,
            )
        )
    return out


def alter(subject: Subject, heute: date) -> int | None:
    """Alter aus dem Jahrgang (ganze Jahre, ohne Geburtstag: ``heute.year − birth_year``).

    >>> alter(Subject(birth_year=1985), date(2026, 10, 29)), alter(Subject(), date(2026, 1, 1))
    (41, None)
    """
    if subject.birth_year is None:
        return None
    return int(heute.year - subject.birth_year)


def formel_fuer(geschlecht: str | None, wunsch: str = "auto") -> str:
    """Welche HFmax-Formel: ausdrücklich gewählt, sonst Gulati für Frauen, sonst Nes.

    >>> formel_fuer("w"), formel_fuer("m"), formel_fuer(None), formel_fuer("w", "nes")
    ('gulati', 'nes', 'nes', 'nes')
    """
    if wunsch in hz.FORMELN:
        return wunsch
    return "gulati" if geschlecht == "w" else "nes"


@dataclass(slots=True)
class HfProfil:
    """Die geltenden Werte einer Person am Stichtag — Grundlage von %HRR und Bereichen.

    ``hfmax`` ist ein Eintrag der Hierarchie oder None; dann gilt, wenn das Alter bekannt
    ist, die Formel als Startwert (``formel``). ``vollstaendig``: Ruhe-HF **und** eine
    HFmax (Eintrag oder Formel) liegen vor — erst dann gibt es %HRR und Bereiche.
    """

    heute: date
    ruhe: Profilwert | None = None
    hfmax: Profilwert | None = None
    vt1: Profilwert | None = None
    vt2: Profilwert | None = None
    formel: hz.Formelwert | None = None
    geschlecht: str | None = None
    alter: int | None = None

    @property
    def ruhe_bpm(self) -> float | None:
        return None if self.ruhe is None else float(self.ruhe.wert)

    @property
    def hfmax_bpm(self) -> float | None:
        if self.hfmax is not None:
            return float(self.hfmax.wert)
        if self.formel is not None and self.formel.gueltig and self.formel.wert is not None:
            return float(self.formel.wert)
        return None

    @property
    def hfmax_quelle(self) -> str:
        """Schlüssel der geltenden HFmax-Quelle (``formel_nes`` …) oder ``""``."""
        if self.hfmax is not None:
            return self.hfmax.quelle
        if self.formel is not None and self.formel.gueltig:
            return f"formel_{self.formel.formel}"
        return ""

    @property
    def hfmax_unsicherheit(self) -> float:
        if self.hfmax is not None:
            return self.hfmax.unsicherheit_wirksam
        if self.formel is not None:
            return self.formel.see
        return 0.0

    @property
    def hfmax_geschaetzt(self) -> bool:
        """Die HFmax kommt aus einer Formel — die Anzeige sagt „geschätzt ± SEE“."""
        return self.hfmax is None and self.formel is not None and self.formel.gueltig

    @property
    def vollstaendig(self) -> bool:
        r, m = self.ruhe_bpm, self.hfmax_bpm
        return r is not None and m is not None and m > r

    @property
    def hrr_bpm(self) -> float | None:
        if not self.vollstaendig:
            return None
        return float(self.hfmax_bpm) - float(self.ruhe_bpm)  # type: ignore[arg-type]

    def prozent(self, hf: float | None) -> float | None:
        """%HRR einer Herzfrequenz — None ohne vollständiges Profil."""
        if hf is None or not self.vollstaendig:
            return None
        return float(hz.prozent_hrr(float(hf), self.ruhe_bpm, self.hfmax_bpm))  # type: ignore[arg-type]

    def hf_bei(self, prozent: float) -> float | None:
        if not self.vollstaendig:
            return None
        return hz.hf_aus_prozent(prozent, self.ruhe_bpm, self.hfmax_bpm)  # type: ignore[arg-type]

    @property
    def individuelle_schwelle(self) -> bool:
        """Eine Schwelle aus Labor oder Talk-Test liegt vor (dann ist „drei“ die Vorgabe)."""
        return any(
            s is not None and s.quelle in ("spiroergometrie", "laktat", "talk_test")
            for s in (self.vt1, self.vt2)
        )


def hf_profil(
    eintraege: list[Profilwert],
    subject: Subject,
    heute: date,
    *,
    formel: str = "auto",
) -> HfProfil:
    """Die geltenden Werte aus allen Einträgen eines Profils (`hz.geltender_wert`).

    >>> s = Subject(name="Ich", birth_year=1986, geschlecht="m")
    >>> p = hf_profil([], s, date(2026, 10, 29))
    >>> p.ruhe_bpm, p.hfmax_bpm, p.hfmax_geschaetzt, p.vollstaendig
    (None, 185.4, True, False)
    >>> r = Profilwert(s.id, "ruhe_hf", 55, "messung_morgen_5", date(2026, 10, 28))
    >>> p = hf_profil([r], s, date(2026, 10, 29))
    >>> p.vollstaendig, round(p.prozent(120.2), 1), p.hfmax_quelle
    (True, 50.0, 'formel_nes')
    """
    je_id = {e.id: e for e in eintraege}
    liste = [e.eintrag() for e in eintraege if e.deleted_at is None]

    def geltend(groesse: str) -> Profilwert | None:
        g = hz.geltender_wert(liste, groesse, heute)
        return None if g is None else je_id.get(g.kennung)

    a = alter(subject, heute)
    f = None
    if a is not None:
        f = hz.formel_hfmax(a, formel_fuer(subject.geschlecht, formel))
    return HfProfil(
        heute=heute,
        ruhe=geltend(hz.GROESSE_RUHE),
        hfmax=geltend(hz.GROESSE_MAX),
        vt1=geltend(hz.GROESSE_VT1),
        vt2=geltend(hz.GROESSE_VT2),
        formel=f,
        geschlecht=subject.geschlecht,
        alter=a,
    )


# ---------------------------------------------------------------------------
# Bereiche aus Profil und Einstellung
# ---------------------------------------------------------------------------

#: Unsicherheit einer Schwellen-Grenze in % HRR je Quelle (Entscheidung 13)
_SCHWELLEN_UNSICHERHEIT: Final[dict[str, float]] = {
    "spiroergometrie": hz.GRENZE_UNSICHERHEIT_PROZENT["labor"],
    "laktat": hz.GRENZE_UNSICHERHEIT_PROZENT["labor"],
    "talk_test": hz.GRENZE_UNSICHERHEIT_PROZENT["talk_test"],
    "schaetzung_milani": hz.GRENZE_UNSICHERHEIT_PROZENT["milani"],
}


def wirksames_modell(profil: HfProfil, einst: HfEinstellungen) -> str:
    """Das Bereichsmodell: gewählt, oder bei „auto“ drei Bereiche mit individueller
    Schwelle, sonst zehn Cluster (Ben, 29.10.2026, Frage 2).

    >>> wirksames_modell(HfProfil(date(2026, 1, 1)), HfEinstellungen())
    'cluster'
    >>> wirksames_modell(HfProfil(date(2026, 1, 1)), HfEinstellungen(modell="acsm"))
    'acsm'
    """
    if einst.modell != MODELL_AUTO:
        return einst.modell
    return hz.MODELL_DREI if profil.individuelle_schwelle else hz.MODELL_CLUSTER


def bereiche_fuer(profil: HfProfil, einst: HfEinstellungen) -> list[hz.Bereich]:
    """Die Bereiche in bpm mit Unsicherheitsband — leer ohne vollständiges Profil.

    Drei Bereiche: die Grenzen kommen aus den Schwellen des Profils (Labor, Talk-Test,
    Schätzung), wo es sie gibt, sonst aus 42 / 77 % HRR (±6 %); dazu der anteilige
    HFmax-Fehler. Eigene Bereiche: Grenzen der Person (in bpm oder % HRR), ohne Band.

    >>> s = Subject(birth_year=1986)
    >>> r = Profilwert(s.id, "ruhe_hf", 60, "eintrag", date(2026, 10, 1))
    >>> m = Profilwert(s.id, "hf_max", 180, "ergometrie", date(2026, 10, 1), unsicherheit=3)
    >>> p = hf_profil([r, m], s, date(2026, 10, 29))
    >>> [round(b.bis_bpm) for b in bereiche_fuer(p, HfEinstellungen(modell="drei"))]
    [110, 152, 180]
    """
    if not profil.vollstaendig:
        return []
    ruhe, hfmax = float(profil.ruhe_bpm), float(profil.hfmax_bpm)  # type: ignore[arg-type]
    u_max = profil.hfmax_unsicherheit
    modell = wirksames_modell(profil, einst)
    if modell == hz.MODELL_EIGEN:
        if not einst.eigene:
            return []
        bpm = [
            g.bpm if g.bpm is not None else profil.hf_bei(g.prozent or 0.0) for g in einst.eigene
        ]
        namen = einst.namen if len(einst.namen) == len(bpm) + 1 else None
        return hz.bereiche(
            hz.MODELL_EIGEN,
            ruhe,
            hfmax,
            eigene_bpm=[float(x) for x in bpm if x is not None],
            namen=namen,
        )
    if modell == hz.MODELL_DREI:
        grenzen: list[float] = []
        unsicher: list[float] = []
        for schwelle, vorgabe in ((profil.vt1, 42.0), (profil.vt2, 77.0)):
            if schwelle is not None and ruhe < schwelle.wert < hfmax:
                grenzen.append(float(schwelle.wert))
                unsicher.append(
                    _SCHWELLEN_UNSICHERHEIT.get(
                        schwelle.quelle, hz.GRENZE_UNSICHERHEIT_PROZENT["prozent_hrr"]
                    )
                )
            else:
                grenzen.append(hz.hf_aus_prozent(vorgabe, ruhe, hfmax))
                unsicher.append(hz.GRENZE_UNSICHERHEIT_PROZENT["prozent_hrr"])
        if grenzen[0] >= grenzen[1]:  # eine Schwelle passt nicht zur anderen: Vorgabe
            grenzen = [hz.hf_aus_prozent(42.0, ruhe, hfmax), hz.hf_aus_prozent(77.0, ruhe, hfmax)]
            unsicher = [hz.GRENZE_UNSICHERHEIT_PROZENT["prozent_hrr"]] * 2
        return hz.bereiche(
            hz.MODELL_EIGEN,
            ruhe,
            hfmax,
            eigene_bpm=grenzen,
            namen=["Bereich 1", "Bereich 2", "Bereich 3"],
            unsicherheit_hfmax_bpm=u_max,
            unsicherheit_grenze_prozent=unsicher,
        )
    return hz.bereiche(
        modell,
        ruhe,
        hfmax,
        unsicherheit_hfmax_bpm=u_max,
        unsicherheit_grenze_prozent=hz.GRENZE_UNSICHERHEIT_PROZENT["prozent_hrr"],
    )


def grenzen_bpm(bereiche: list[hz.Bereich]) -> list[float]:
    """Die inneren Grenzen (obere Grenze jedes Bereichs außer dem letzten).

    >>> grenzen_bpm(hz.bereiche("drei", 60, 180))
    [110.4, 152.4]
    """
    return [b.bis_bpm for b in bereiche[:-1]]


def bereich_von(hf: float | None, bereiche: list[hz.Bereich]) -> hz.Bereich | None:
    """Der Bereich, in dem ``hf`` liegt — unter dem ersten der erste, über dem letzten der
    letzte; None ohne Bereiche oder Wert."""
    if hf is None or not bereiche:
        return None
    for b in bereiche:
        if hf < b.bis_bpm:
            return b
    return bereiche[-1]


__all__ = [
    "EINTRAG_QUELLEN",
    "GESCHLECHTER",
    "GROESSEN",
    "QUELLEN",
    "TAGESFELD_TAGE",
    "HfProfil",
    "Profilwert",
    "alter",
    "bereich_von",
    "bereiche_fuer",
    "formel_fuer",
    "grenzen_bpm",
    "hf_profil",
    "tagesfeld_eintraege",
    "wirksames_modell",
]
