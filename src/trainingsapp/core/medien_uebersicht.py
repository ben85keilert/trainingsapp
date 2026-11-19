"""Die Übersicht im Reiter „Medien“ des Plan-Editors (Ben, 17.11.2026,
`docs/plan_medien_reiter.md` §3): was es zu einem Plan zu sehen gibt — **unterteilt nach
Herkunft**, und je Stück, **wo es angeboten wird** (Ben: „Es wäre gut, wenn man sieht, was wo
angeboten wird, unterteilt nach Herkunft“).

Die Gruppen, in dieser Folge:

- **Aus den Übungen** — was die Übung mitbringt und überall gilt, wo sie vorkommt: ihre
  Beschreibung (im „i“), Links und Dateien (beim Üben hinter dem Buch-Symbol), das Bild der
  Bewegung (im Fokus). Ein Stück, das eine Planübung ersetzt, steht hier blass.
- **Aus diesem Plan** — nur hier: die Beschreibung des Plans, die Anweisungen und Stücke der
  Planübungen.
- **Im Workout** — der Inhalt an einem Weg des Ablaufs (Text, Link); er geht auf, wenn der Weg
  frei ist.
- **Aus dem Kurs** — Text- und Medienblöcke der **erreichten** Kapitel (Ben: „nur erreichte“)
  und Wege, die der Kurs mit Inhalt gesetzt hat — ein Weg gehört dorthin, woher sein Inhalt
  kommt (Ben: „beim Workout/Kurs, wo sie hingehören“).

**Nur ansehen und hinführen:** Jede Zeile nennt, wo man sie ändert (`Ziel`); geändert wird
weiter an den zwei Orten „Übung bearbeiten“ und „Im Plan einstellen“, im Ablauf und im Kurs.

Größen und Köpfe der Dateien kommen als Funktion herein (`Dateiinfo`) — dieses Modul liest weder
Datenbank noch Dateien. Es kennt kein flet.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from .ablauf import ZURUECK, Kante, nummern
from .anhaenge import Qualitaet
from .bedingung import ENDE
from .beschreibung import abschnitte
from .bewegungsbild import EINGEBAUT, bewegungsbild
from .kursbloecke import MEDIUM, PLAN_WEG, TEXT, ZU_ENDE, Block, bloecke_von
from .kurse import Kapitel
from .material import BILD, LINK, PDF, TON, VIDEO, art, material_von
from .models import (
    BEGLEITUNG,
    BEI,
    BEWEGUNG,
    IMMER,
    NACHHER,
    SYMBOL,
    Exercise,
    Media,
    MediaSource,
    Plan,
    PlanItem,
)
from .paketmedien import groesse_text, ist_paketmedium
from .videoinfo import Videoinfo
from .zaehlen import wirksame_wahl

# -- Herkunft (die Gruppen) -------------------------------------------------------------------

AUS_UEBUNG: Final = "uebung"
AUS_PLAN: Final = "plan"
IM_WORKOUT: Final = "workout"
AUS_KURS: Final = "kurs"

# -- Arten einer Zeile über die des Materials hinaus (`core.material`: video, pdf, bild, ton,
# link) ---------------------------------------------------------------------------------------

#: Text (Beschreibung, Anweisungen, Textblock im Kurs, Inhalt eines Wegs ohne Link)
TEXTART: Final = "text"
#: das Bild der Bewegung
ANIMATION: Final = "animation"

#: Wie eine Datei heißt, je Art
DATEI_WORT: Final[dict[str, str]] = {
    VIDEO: "Video-Datei",
    PDF: "PDF-Datei",
    BILD: "Bild-Datei",
    TON: "Ton-Datei",
}

#: Spielraum über der Stufe „Mittel“, ab dem ein Stück **groß** heißt (Ben, 17.11.2026, Frage c:
#: „Das Bild muss auf ein Tablet/Smartphone passen“ — meine Lesart: „Mittel“, 720p, passt auf
#: beide; was deutlich mehr braucht, ist groß)
SPIELRAUM: Final = 1.25

# -- Wo man eine Zeile ändert -----------------------------------------------------------------

#: „Übung bearbeiten“ (``id``: die Übung)
ZIEL_UEBUNG: Final = "uebung"
#: „Im Plan einstellen“ (``id``: die Planübung)
ZIEL_PLANUEBUNG: Final = "planuebung"
#: der Reiter „Plan“ des Plan-Editors
ZIEL_PLAN: Final = "plan"
#: der Reiter „Ablauf“
ZIEL_ABLAUF: Final = "ablauf"
#: das Kapitel eines Kurses (``id``: der Kurs, ``kapitel``)
ZIEL_KURS: Final = "kurs"

#: Wo Beschreibung und Medien des Plans selbst angeboten werden (Stufe 2)
AM_PLAN: Final = "am Plan · vor dem Start"
#: Der Satz unter „Aus diesem Plan“
PLAN_HINWEIS: Final = (
    "Gilt nur hier — die Planübungen ändert „Im Plan einstellen“, den Plan selbst der Stift hier."
)


@dataclass(frozen=True, slots=True)
class Ziel:
    """Wohin „Ändern“ führt."""

    art: str
    id: str = ""
    kapitel: str = ""


@dataclass(frozen=True, slots=True)
class Dateiinfo:
    """Was die Oberfläche über eine Datei auf dem Gerät weiß."""

    bytes: int
    #: der Kopf eines Videos oder Tons (`core.videoinfo`)
    video: Videoinfo | None = None
    #: Breite und Höhe eines Bilds
    bild: tuple[int, int] | None = None
    #: ein Video hinter einem Link, auf dem Gerät gespeichert (Stufe 7, Migration 068)
    geladen: bool = False


@dataclass(frozen=True, slots=True)
class Zeile:
    """Ein Stück der Übersicht."""

    art: str
    titel: str
    #: „Video-Datei · Erklärung · zeigt sich beim ersten Mal“
    unter: str
    #: wo es angeboten wird: „bei 1 · Kniebeuge“, „am Weg 1 · Kniebeuge → 3 · Planke“
    wo: str
    ziel: Ziel
    medium: Media | None = None
    #: bei Text: der ganze Text, zum Lesen
    text: str = ""
    #: ``text`` ist Markdown (Kurs)
    markdown: bool = False
    #: die Datei auf dem Gerät — Paketdatei oder geladenes Video hinter einem Link
    datei: Dateiinfo | None = None
    #: mehr, als „Mittel“ bräuchte (`gross`)
    gross: bool = False
    #: steht hier, gilt aber nirgends: eine Planübung ersetzt es überall
    ersetzt: bool = False

    @property
    def paketdatei(self) -> bool:
        return self.medium is not None and ist_paketmedium(self.medium)


@dataclass(frozen=True, slots=True)
class Gruppe:
    herkunft: str
    titel: str
    #: ein Satz darunter: wo es gilt, wo man es ändert
    hinweis: str
    zeilen: tuple[Zeile, ...]


@dataclass(frozen=True, slots=True)
class KursTeil:
    """Ein **erreichtes** Kapitel des Kurses, zu dem der Plan gehört."""

    kurs_id: str
    kurs_name: str
    kapitel: Kapitel
    #: 1-basiert, wie im Kurs
    nummer: int


@dataclass(frozen=True, slots=True)
class Uebersicht:
    gruppen: tuple[Gruppe, ...] = ()

    @property
    def zeilen(self) -> tuple[Zeile, ...]:
        return tuple(z for g in self.gruppen for z in g.zeilen)

    @property
    def stuecke(self) -> int:
        """Was angeboten wird — ohne Ersetztes."""
        return sum(1 for z in self.zeilen if not z.ersetzt)

    def dateien(self) -> dict[str, int]:
        """Die Paketdateien (je Adresse einmal) mit ihrer Größe — was mit dem Plan reisen würde."""
        out: dict[str, int] = {}
        for z in self.zeilen:
            if z.paketdatei and z.medium is not None and z.datei is not None:
                out[z.medium.uri] = z.datei.bytes
        return out

    def kopf(self) -> str:
        """„6 Stücke · 2 Dateien · 96 MB“ — ohne Stücke „Noch keine Medien“.

        >>> Uebersicht().kopf()
        'Noch keine Medien'
        """
        if not self.stuecke:
            return "Noch keine Medien"
        teile = [f"{self.stuecke} Stück" if self.stuecke == 1 else f"{self.stuecke} Stücke"]
        dateien = self.dateien()
        if dateien:
            n = len(dateien)
            teile.append("1 Datei" if n == 1 else f"{n} Dateien")
            teile.append(groesse_text(sum(dateien.values())))
        return " · ".join(teile)


# -- Groß -------------------------------------------------------------------------------------


def grenze_video(dauer_s: float) -> int:
    """Ab wie vielen Byte ein Video dieser Dauer **groß** ist: mehr als ein Viertel über dem,
    was „Mittel“ (720p, Bild und Ton) bräuchte.

    >>> grenze_video(60), grenze_video(120)
    (8100000, 16200000)
    """
    mittel = Qualitaet.MITTEL
    return round(SPIELRAUM * (mittel.video_bitrate + mittel.audio_bitrate) / 8 * dauer_s)


def gross(medium_art: str, datei: Dateiinfo | None) -> bool:
    """Braucht das Stück deutlich mehr Platz, als es auf einem Handy oder Tablet braucht?

    Ein Video, wenn es mehr Byte hat als `grenze_video` seiner Dauer; ein Bild, wenn seine
    kürzere Seite um mehr als ein Viertel über der von „Mittel“ (720 px) liegt. Ohne Dauer bzw.
    Maße: nicht groß — geraten wird nicht.

    >>> lang = Dateiinfo(bytes=84_000_000, video=Videoinfo(dauer_s=130))
    >>> gross(VIDEO, lang), gross(VIDEO, Dateiinfo(bytes=14_000_000, video=Videoinfo(dauer_s=130)))
    (True, False)
    >>> gross(BILD, Dateiinfo(bytes=4_000_000, bild=(3024, 4032))), gross(VIDEO, None)
    (True, False)
    >>> gross(VIDEO, Dateiinfo(bytes=84_000_000))  # Dauer unbekannt
    False
    """
    if datei is None:
        return False
    if medium_art == VIDEO and datei.video is not None and datei.video.dauer_s:
        return datei.bytes > grenze_video(datei.video.dauer_s)
    if medium_art == BILD and datei.bild is not None:
        return min(datei.bild) > SPIELRAUM * Qualitaet.MITTEL.kurze_seite
    return False


# -- Texte ------------------------------------------------------------------------------------


def _stellen(nummern_: Sequence[int]) -> str:
    """„1“, „1 und 4“, „1, 4 und 6“."""
    teile = [str(n) for n in nummern_]
    if len(teile) <= 1:
        return "".join(teile)
    return ", ".join(teile[:-1]) + " und " + teile[-1]


def _art_wort(m: Media) -> str:
    """„Link“ oder „Video-Datei“ …"""
    if m.source == MediaSource.URL:
        return "Link"
    return DATEI_WORT.get(art(m), "Datei")


def _zustand(m: Media, gesehen: Collection[str]) -> list[str]:
    """Rolle und Zustand: „Erklärung · zeigt sich beim ersten Mal“, „Begleitung“."""
    if m.rolle == BEGLEITUNG:
        return ["Begleitung"]
    if m.rolle == BEWEGUNG:
        return ["Bewegung"]
    if m.rolle == SYMBOL:
        return ["Symbol"]
    teile = ["Erklärung"]
    # Wann (Ben, 18.11.2026, `docs/plan_medien_zeitpunkte.md` §2): vorher ist die Vorgabe
    if m.wann == NACHHER:
        teile.append("nachher")
    elif m.wann == BEI and m.bei is not None:
        teile.append(m.bei.text())
    if m.oft == IMMER:
        teile.append("jedes Mal")
    elif m.uri in gesehen:
        teile.append("gesehen")
    elif m.zeigen and m.wann != BEI:
        teile.append("zeigt sich beim ersten Mal")
    if m.abschnitte:
        teile.append("zu: " + ", ".join(m.abschnitte))
    return teile


def _datei_teile(datei: Dateiinfo | None) -> list[str]:
    if datei is None:
        return []
    teile = []
    if datei.video is not None and datei.video.text():
        teile.append(datei.video.text())
    elif datei.bild is not None:
        teile.append(f"{datei.bild[0]} × {datei.bild[1]}")
    if datei.geladen:
        teile.append("auf dem Gerät")
    return teile


def _medium_art(m: Media) -> str:
    """Die Art der Zeile — ein Link ohne erkennbare Datei ist ein Link."""
    a = art(m)
    if m.source == MediaSource.URL and a == VIDEO:
        return LINK
    return a


# -- Die Übersicht ----------------------------------------------------------------------------


@dataclass(slots=True)
class _Bau:
    plan: Plan
    uebungen: Mapping[str, Exercise]
    gesehen: Collection[str]
    datei: Callable[[Media], Dateiinfo | None]
    #: Nummer je Planübung (Stelle in der Liste)
    nummer: dict[str, int] = field(default_factory=dict)

    def name(self, item: PlanItem) -> str:
        u = self.uebungen.get(item.exercise_id)
        return u.name if u is not None else "Übung"

    def bei(self, item: PlanItem) -> str:
        return f"bei {self.nummer.get(item.id, 0)} · {self.name(item)}"

    def knoten(self, kid: str) -> str:
        """„3 · Planke“, „? · Wie geht es dir?“."""
        item = next((i for i in self.plan.items if i.id == kid), None)
        if item is not None:
            return f"{self.nummer.get(item.id, 0)} · {self.name(item)}"
        frage = self.plan.ablauf.frage(kid)
        return f"? · {frage.text}" if frage is not None else "?"

    def medium_zeile(
        self, m: Media, wo: str, ziel: Ziel, *, ersetzt: bool = False, vorn: Sequence[str] = ()
    ) -> Zeile:
        datei = self.datei(m)
        a = _medium_art(m)
        teile = [*vorn, _art_wort(m), *_zustand(m, self.gesehen), *_datei_teile(datei)]
        titel = m.title or (m.uri if m.source == MediaSource.URL else DATEI_WORT.get(a, "Datei"))
        return Zeile(
            art=a,
            titel=titel,
            unter=" · ".join(teile),
            wo=wo,
            ziel=ziel,
            medium=m,
            datei=datei,
            gross=gross(a, datei),
            ersetzt=ersetzt,
        )


def _aus_uebungen(bau: _Bau) -> list[Zeile]:
    """Je Übung (in der Folge ihres ersten Auftritts im Plan) Beschreibung, Medien, Animation."""
    zeilen: list[Zeile] = []
    je_uebung: dict[str, list[PlanItem]] = {}
    for item in bau.plan.items:
        je_uebung.setdefault(item.exercise_id, []).append(item)
    for uebung_id, items in je_uebung.items():
        u = bau.uebungen.get(uebung_id)
        if u is None:
            continue
        ziel = Ziel(ZIEL_UEBUNG, u.id)
        stellen = [bau.nummer.get(i.id, 0) for i in items]
        bei = f"bei {_stellen(stellen)} · {u.name}"
        teile = [a for a in abschnitte(u.description) if not a.leer]
        if teile:
            zeilen.append(
                Zeile(
                    art=TEXTART,
                    titel=f"Beschreibung · {u.name}",
                    unter="Text" if len(teile) == 1 else f"Text · {len(teile)} Abschnitte",
                    wo=f"im „i“ {bei}",
                    ziel=ziel,
                    text=u.description,
                )
            )
        # Was eine Planübung ersetzt, gilt dort nicht (`core.material.material_von`)
        weg = {i.id: {x.uri for x in material_von(u, i).ersetzt} for i in items}
        for m in u.media:
            if not m.uri or m.source == MediaSource.LOCAL:
                continue
            frei = [i for i in items if m.uri not in weg[i.id]]
            nicht = [i for i in items if m.uri in weg[i.id]]
            if frei:
                wo = f"bei {_stellen([bau.nummer.get(i.id, 0) for i in frei])} · {u.name}"
                if nicht:
                    wo += f" — bei {_stellen([bau.nummer.get(i.id, 0) for i in nicht])} ersetzt"
            else:
                wo = f"bei {_stellen(stellen)} · {u.name} ersetzt — siehe „Aus diesem Plan“"
            zeilen.append(bau.medium_zeile(m, wo, ziel, ersetzt=not frei))
        # Das Bild der Bewegung — das eigene reist nicht mit, das mitgelieferte hat jedes Gerät
        if bewegungsbild(u.media) is not None:
            zeilen.append(
                Zeile(
                    art=ANIMATION,
                    titel=f"Bild der Bewegung · {u.name}",
                    unter="Animation · nur auf diesem Gerät",
                    wo=f"im Fokus {bei}",
                    ziel=ziel,
                )
            )
        else:
            eingebaut = [i for i in items if EINGEBAUT.get(wirksame_wahl(u, i).vorlage)]
            if eingebaut:
                st = _stellen([bau.nummer.get(i.id, 0) for i in eingebaut])
                zeilen.append(
                    Zeile(
                        art=ANIMATION,
                        titel=f"Bild der Bewegung · {u.name}",
                        unter="Animation · in der App",
                        wo=f"im Fokus bei {st} · {u.name}",
                        ziel=ziel,
                    )
                )
    return zeilen


def _aus_plan(bau: _Bau) -> list[Zeile]:
    """Der Plan selbst (Beschreibung, Medien — Stufe 2, gezeigt am Kopf des Plans und im
    Start-Bild), dann je Planübung Anweisungen und Stücke."""
    zeilen: list[Zeile] = []
    plan_teile = [a for a in abschnitte(bau.plan.description) if not a.leer]
    if plan_teile:
        zeilen.append(
            Zeile(
                art=TEXTART,
                titel="Beschreibung des Plans",
                unter="Text" if len(plan_teile) == 1 else f"Text · {len(plan_teile)} Abschnitte",
                wo=AM_PLAN,
                ziel=Ziel(ZIEL_PLAN),
                text=bau.plan.description,
            )
        )
    for m in bau.plan.media:
        if m.uri and m.source != MediaSource.LOCAL:
            zeilen.append(bau.medium_zeile(m, AM_PLAN, Ziel(ZIEL_PLAN, m.uri)))
    for item in bau.plan.items:
        u = bau.uebungen.get(item.exercise_id)
        ziel = Ziel(ZIEL_PLANUEBUNG, item.id)
        teile = [a for a in abschnitte(item.description) if not a.leer]
        if teile:
            namen = [a.name for a in teile if a.name]
            zeilen.append(
                Zeile(
                    art=TEXTART,
                    titel=" · ".join(namen) if namen else "Anweisung",
                    unter="Text" if len(teile) == 1 else f"Text · {len(teile)} Abschnitte",
                    wo=bau.bei(item),
                    ziel=ziel,
                    text=item.description,
                )
            )
        titel_der_uebung = {m.uri: m.title or m.uri for m in (u.media if u else [])}
        for m in item.media:
            if not m.uri or m.source == MediaSource.LOCAL:
                continue
            vorn = []
            if m.ersetzt and m.ersetzt in titel_der_uebung:
                vorn.append(f"ersetzt „{titel_der_uebung[m.ersetzt]}“")
            zeilen.append(bau.medium_zeile(m, bau.bei(item), ziel, vorn=vorn))
    return zeilen


def _weg_zeilen(bau: _Bau, k: Kante, ziel: Ziel, *, aus: str = "") -> list[Zeile]:
    """Der Inhalt an einem Weg und je weiterem Stück (`Inhalt.medien`) eine eigene Zeile."""
    erste = _weg_zeile(bau, k, ziel, aus=aus)
    zeilen = [erste] if (k.inhalt.text.strip() or k.inhalt.url.strip()) else []
    zeilen += [
        bau.medium_zeile(Media(uri=s.uri, title=s.title or s.uri), erste.wo, ziel)
        for s in k.inhalt.medien
    ]
    return zeilen


def _weg_zeile(bau: _Bau, k: Kante, ziel: Ziel, *, aus: str = "") -> Zeile:
    """Der Inhalt an einem Weg: ein Link (mit dem Text als Satz) oder nur Text. Der Weg in
    Worten („von … zu …“) — der Pfeil fehlt manchen Schriften (Web-Fassung ohne CDN)."""
    if k.nach == ENDE:
        wo = f"am Weg von {bau.knoten(k.von)} zum Ende"
    elif k.nach == ZURUECK:
        wo = f"am Weg von {bau.knoten(k.von)} zurück"
    else:
        wo = f"am Weg von {bau.knoten(k.von)} zu {bau.knoten(k.nach)}"
    if aus:
        wo += f" · {aus}"
    titel = k.text or k.inhalt.text.split("\n", 1)[0][:60] or "Inhalt am Weg"
    if k.inhalt.url:
        m = Media(uri=k.inhalt.url, title=titel)
        teile = ["Link"]
        if k.inhalt.text:
            teile.insert(0, "Text")
        datei = bau.datei(m)
        teile += _datei_teile(datei)
        return Zeile(
            art=LINK,
            titel=titel,
            unter=" · ".join(teile),
            wo=wo,
            ziel=ziel,
            medium=m,
            text=k.inhalt.text,
            datei=datei,
        )
    return Zeile(art=TEXTART, titel=titel, unter="Text", wo=wo, ziel=ziel, text=k.inhalt.text)


def _marke_passt(item: PlanItem | None, marke: str) -> bool:
    """Gehört die Planübung zur Marke eines Bausteins (auch „die Gewählten“ einer Auswahl)?"""
    if marke == ZU_ENDE:
        return item is None
    if item is None or not marke:
        return False
    return item.kurs_marke == marke or item.kurs_marke.startswith(f"{marke}:")


def _vom_kurs(bau: _Bau, k: Kante, kurs: Sequence[KursTeil]) -> KursTeil | None:
    """Das Kapitel, dessen Weg-Baustein diesen Weg mit **diesem** Inhalt setzte — ``None``, wenn
    der Inhalt im Workout entstand oder dort geändert wurde."""
    von = next((i for i in bau.plan.items if i.id == k.von), None)
    nach = None if k.nach == ENDE else next((i for i in bau.plan.items if i.id == k.nach), None)
    if von is None or (nach is None and k.nach != ENDE):
        return None
    for teil in kurs:
        for b in teil.kapitel.bloecke:
            if b.art != PLAN_WEG or not _marke_passt(von, b.von):
                continue
            if not _marke_passt(nach, b.zu):
                continue
            inhalt = b.kante.get("inhalt") if isinstance(b.kante, Mapping) else None
            if not isinstance(inhalt, Mapping):
                continue
            if (str(inhalt.get("text") or ""), str(inhalt.get("url") or "")) == (
                k.inhalt.text,
                k.inhalt.url,
            ):
                return teil
    return None


def _kurs_block(bau: _Bau, b: Block, teil: KursTeil) -> Zeile | None:
    ziel = Ziel(ZIEL_KURS, teil.kurs_id, teil.kapitel.id)
    wo = f"im Kapitel {teil.nummer} · {teil.kapitel.titel}".rstrip(" ·")
    if b.art == TEXT and b.text.strip():
        return Zeile(
            art=TEXTART,
            titel=b.titel or "Text",
            unter="Text",
            wo=wo,
            ziel=ziel,
            text=b.text,
            markdown=True,
        )
    if b.art == MEDIUM and b.medium is not None and b.medium.uri:
        return bau.medium_zeile(b.medium, wo, ziel)
    return None


def uebersicht(
    plan: Plan,
    uebungen: Mapping[str, Exercise],
    *,
    kurs: Sequence[KursTeil] = (),
    gesehen: Collection[str] = frozenset(),
    datei: Callable[[Media], Dateiinfo | None] = lambda _m: None,
) -> Uebersicht:
    """Die Gruppen zu ``plan``. ``uebungen``: die Übungen seiner Planübungen; ``kurs``: die
    erreichten Kapitel des Kurses, zu dem er gehört; ``gesehen``: die Adressen, die das Profil
    abgehakt hat; ``datei``: Größe und Kopf einer Datei auf dem Gerät (sonst ``None``).

    >>> u = Exercise(id="u", name="Kniebeuge", description="## Ausführung\\nTief",
    ...              media=[Media(uri="https://x.org/technik", title="Technik", zeigen=True)])
    >>> p = Plan(items=[PlanItem(id="i", exercise_id="u", description="## Im Plan\\nlangsam")])
    >>> ue = uebersicht(p, {"u": u})
    >>> [(g.titel, [z.titel for z in g.zeilen]) for g in ue.gruppen]
    [('AUS DEN ÜBUNGEN', ['Beschreibung · Kniebeuge', 'Technik']), ('AUS DIESEM PLAN', ['Im Plan'])]
    >>> ue.zeilen[1].unter, ue.zeilen[1].wo, ue.kopf()
    ('Link · Erklärung · zeigt sich beim ersten Mal', 'bei 1 · Kniebeuge', '3 Stücke')
    """
    bau = _Bau(plan, uebungen, gesehen, datei, nummern([i.id for i in plan.items]))
    gruppen: list[Gruppe] = []
    if zeilen := _aus_uebungen(bau):
        gruppen.append(
            Gruppe(
                AUS_UEBUNG,
                "AUS DEN ÜBUNGEN",
                "Gilt überall, wo die Übung vorkommt — geändert in „Übung bearbeiten“.",
                tuple(zeilen),
            )
        )
    if zeilen := _aus_plan(bau):
        gruppen.append(Gruppe(AUS_PLAN, "AUS DIESEM PLAN", PLAN_HINWEIS, tuple(zeilen)))
    kurs_wege: dict[str, list[Zeile]] = {}
    workout: list[Zeile] = []
    if plan.ablauf.an:
        for k in plan.ablauf.kanten:
            if k.inhalt.leer:
                continue
            teil = _vom_kurs(bau, k, kurs)
            if teil is not None:
                ziel = Ziel(ZIEL_KURS, teil.kurs_id, teil.kapitel.id)
                aus = f"aus Kapitel {teil.nummer}"
                kurs_wege.setdefault(teil.kurs_id, []).extend(_weg_zeilen(bau, k, ziel, aus=aus))
            else:
                workout.extend(_weg_zeilen(bau, k, Ziel(ZIEL_ABLAUF)))
    if workout:
        gruppen.append(
            Gruppe(
                IM_WORKOUT,
                "IM WORKOUT",
                "Geht auf, wenn der Weg frei ist — geändert im Reiter „Ablauf“.",
                tuple(workout),
            )
        )
    je_kurs: dict[str, list[KursTeil]] = {}
    for teil in kurs:
        je_kurs.setdefault(teil.kurs_id, []).append(teil)
    for kurs_id, teile in je_kurs.items():
        zeilen = []
        for teil in sorted(teile, key=lambda t: t.nummer):
            kap = teil.kapitel
            for b in bloecke_von(kap.bloecke, kap.text, kap.media):
                if (z := _kurs_block(bau, b, teil)) is not None:
                    zeilen.append(z)
        zeilen += kurs_wege.get(kurs_id, [])
        if zeilen:
            gruppen.append(
                Gruppe(
                    AUS_KURS,
                    f"AUS DEM KURS „{teile[0].kurs_name}“",
                    "Nur erreichte Kapitel — geändert im Kurs.",
                    tuple(zeilen),
                )
            )
    return Uebersicht(tuple(gruppen))


__all__ = [
    "AM_PLAN",
    "ANIMATION",
    "AUS_KURS",
    "AUS_PLAN",
    "AUS_UEBUNG",
    "IM_WORKOUT",
    "PLAN_HINWEIS",
    "SPIELRAUM",
    "TEXTART",
    "ZIEL_ABLAUF",
    "ZIEL_KURS",
    "ZIEL_PLAN",
    "ZIEL_PLANUEBUNG",
    "ZIEL_UEBUNG",
    "Dateiinfo",
    "Gruppe",
    "KursTeil",
    "Uebersicht",
    "Zeile",
    "Ziel",
    "grenze_video",
    "gross",
    "uebersicht",
]
