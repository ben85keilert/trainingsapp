# L06 — Lösungen

## Aufgabe 1: Spezifikation lesen

**1.** `format_shorthand({"sets": 3})` ergibt `"Sätze 3"`. Die Vorlage
`"{sets}× {hold}s"` braucht `hold`; `str.format` wirft einen `KeyError`, den
`format_shorthand` fängt. Dann baut es die Aufzählung aus den Feldern, die
vorhanden sind — nur `sets`. Das ist Absicht: lieber eine unvollständige
Anzeige als ein Absturz in einer Liste mit 500 Einträgen.

**2.** Ein Raster wäre gleichmäßig — `8, 10, 12, 14, 16, 18, 20`. Aber die
Werte, die man wirklich benutzt, sind nicht gleichmäßig: 8, 10, 12, 15, 20
sind die üblichen Vorgaben im Krafttraining. Die Liste ist Fachwissen, kein
Rechenergebnis. Außerdem kann die Therapeutin in Edition B so je Übung genau
die Werte anbieten, die sie verordnet.

**3.** Der Verlauf soll zeigen, ob jemand **stärker** wird. Dafür zählen die
Wiederholungen je Satz, nicht die Anzahl Sätze — drei Sätze bleiben drei
Sätze, während die Wiederholungen von 10 auf 20 steigen. `sets` wäre
interessant, wenn das Volumen (`sets × reps`) die Zielgröße ist, etwa im
Ausdauerbereich. Dann wäre ein berechnetes Feld sinnvoller als zwei Kurven.

## Aufgabe 2: Neuer Feldtyp

**Gehstrecke:** An `SpecForm` ändert sich **nichts**. `DISTANCE` und
`DURATION` sind zahlenartig, der Zweig existiert. Nur die Vorlage kommt dazu:

```python
SPEC_GEHSTRECKE = ResultSpec(
    layout=Layout.SINGLE,
    fields=[
        FieldSpec("distance", FieldType.DISTANCE, "Strecke", unit="m",
                  quick=[500, 1000, 2000, 5000]),
        FieldSpec("duration", FieldType.DURATION, "Dauer", unit="s"),
    ],
    shorthand="{distance} m in {duration} s",
    chart_metrics=["distance", "duration"],
)
```

Genau das ist der Gewinn der Spezifikation: Eine neue Übung mit neuer Notation
ist Daten, kein Code.

**`CHOICE`:** In `core/result_spec.py`:

```python
class FieldType(StrEnum):
    ...
    CHOICE = "choice"  # Auswahl aus festen Werten, die Optionen stehen in `quick`
```

In `SpecForm._widget`:

```python
if f.type == FieldType.CHOICE:
    return ft.SegmentedButton(
        selected={str(wert)} if wert is not None else set(),
        segments=[ft.Segment(value=str(q), label=ft.Text(str(q))) for q in f.quick],
    )
```

`_zeile` gibt das Widget ohne Chips zurück (`CHOICE` zu den Ausnahmen neben
`BOOL`/`TEXT`), `_lesen` liefert den ersten Wert aus `widget.selected` oder
`None`, `setzen` setzt `widget.selected = {str(wert)}`.

## Aufgabe 3: `spec_form.py`

Die Kernergänzung — Pflichtfelder und ungültige Eingaben melden:

```python
def pruefen(self) -> list[str]:
    """Labels der Felder, die fehlen oder ungültig sind; markiert sie."""
    probleme: list[str] = []
    for f in self.spec.fields:
        widget = self._widgets[f.key]
        wert = self._lesen(f, widget)
        text = str(getattr(widget, "value", "") or "").strip()
        ungueltig = wert is None and text != "" and f.type not in (FieldType.BOOL, FieldType.SCALE)
        fehlt = f.required and (wert is None or wert == "")
        if isinstance(widget, ft.TextField):
            widget.error = "Ungültig" if ungueltig else ("Pflichtfeld" if fehlt else None)
        if ungueltig or fehlt:
            probleme.append(f.label)
    return probleme
```

Die Ansicht ruft vor dem Speichern `if form.pruefen(): page.update(); return`.

Chips als ausgewählt zeigen: In `_zeile` die Chips in einer Liste behalten und
in einer Methode `_chips_abgleichen(f)` nach jedem Setzen
`chip.selected = (chip.label.value == widget.value)` setzen — aufgerufen aus
`setzer` und aus `setzen`.

**Test ohne Seite:** `setzen()` ruft `self.control.update()`, und ein Control
ohne Seite wirft dabei. Die sauberste Lösung ist ein optionaler Parameter
`aktualisieren: bool = True` — im Test `form.setzen({...}, aktualisieren=False)`.
Alternativ kapselt man den Aufruf in eine Methode `_aktualisieren()`, die der
Test überschreibt. Beides verbiegt die Klasse nicht.

```python
def test_spec_form_rundlauf() -> None:
    from trainingsapp.ui.components.spec_form import SpecForm
    for spec in (SPEC_SAETZE_WDH, SPEC_HALTEN, SPEC_WINKEL, SPEC_BENCHMARK_ZEIT):
        form = SpecForm(spec)
        assert form.werte() == spec.defaults()
    form = SpecForm(SPEC_SAETZE_WDH)
    form.setzen({"sets": 5}, aktualisieren=False)
    assert form.werte()["sets"] == 5
```

## Aufgabe 4: `SessionRepo`

```python
class SessionRepo:
    """Trainingseinheiten und ihre Einträge. Einträge sind unveränderlich."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    # -- Sitzungen ---------------------------------------------------------

    def anlegen(self, session: Session) -> None:
        self.con.execute(
            "INSERT INTO session (id, subject_id, plan_id, started_at, note, mood) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session.id, session.subject_id, session.plan_id,
             session.started_at.isoformat(), session.note, session.mood),
        )

    def beenden(self, session_id: str) -> None:
        self.con.execute(
            "UPDATE session SET ended_at = ? WHERE id = ?", (jetzt().isoformat(), session_id)
        )

    # -- Einträge ----------------------------------------------------------

    def eintrag_anlegen(
        self, session: Session, uebung: Exercise, result: dict[str, Any], note: str = ""
    ) -> SessionEntry:
        eintrag = SessionEntry(
            session_id=session.id,
            exercise_id=uebung.id,
            order=len(self.eintraege(session.id)),
            result=result,
            spec_snapshot=uebung.result_spec,   # die Kopie — immer
            note=note,
            started_at=jetzt(),
        )
        with transaktion(self.con):
            self._eintrag_schreiben(eintrag, ersetzt=None)
            self._kennzahlen_schreiben(session, eintrag)
        return eintrag

    def eintrag_korrigieren(self, alter_eintrag_id: str, result: dict[str, Any]) -> SessionEntry:
        alt = self._eintrag_laden(alter_eintrag_id)
        if alt is None:
            raise KeyError(alter_eintrag_id)
        session = self._session_laden(alt.session_id)
        neu = SessionEntry(
            session_id=alt.session_id,
            exercise_id=alt.exercise_id,
            order=alt.order,
            result=result,
            spec_snapshot=alt.spec_snapshot,    # die Kopie des ALTEN Eintrags
            note=alt.note,
            started_at=alt.started_at,
        )
        with transaktion(self.con):
            self._eintrag_schreiben(neu, ersetzt=alt.id)
            self.con.execute("DELETE FROM measurement WHERE session_entry_id = ?", (alt.id,))
            self._kennzahlen_schreiben(session, neu)
        return neu

    def eintraege(self, session_id: str) -> list[SessionEntry]:
        return [self._zeile(r) for r in self.con.execute(
            f"{_GUELTIGE} AND e.session_id = ? ORDER BY e.sort_order, e.rowid", (session_id,)
        )]

    def letzter_eintrag(self, subject_id: str, exercise_id: str) -> SessionEntry | None:
        r = self.con.execute(
            f"{_GUELTIGE} AND e.exercise_id = ? AND s.subject_id = ? "
            "ORDER BY s.started_at DESC, e.rowid DESC LIMIT 1",
            (exercise_id, subject_id),
        ).fetchone()
        return self._zeile(r) if r else None

    def verlauf(self, subject_id: str, metric_key: str) -> list[Measurement]:
        return [
            Measurement(
                id=r["id"], subject_id=r["subject_id"], metric_key=r["metric_key"],
                value=r["value"], unit=r["unit"],
                recorded_at=datetime.fromisoformat(r["recorded_at"]),
                session_id=r["session_id"], session_entry_id=r["session_entry_id"],
                source=r["source"],
            )
            for r in self.con.execute(
                "SELECT * FROM measurement WHERE subject_id = ? AND metric_key = ? "
                "AND deleted_at IS NULL ORDER BY recorded_at",
                (subject_id, metric_key),
            )
        ]

    # -- intern --------------------------------------------------------------

    def _eintrag_schreiben(self, e: SessionEntry, ersetzt: str | None) -> None:
        assert e.spec_snapshot is not None, "Eintrag ohne Kopie der Spezifikation"
        self.con.execute(
            "INSERT INTO session_entry (id, session_id, exercise_id, sort_order, result_json, "
            "spec_snapshot_json, note, started_at, ended_at, replaces_entry_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (e.id, e.session_id, e.exercise_id, e.order,
             json.dumps(e.result, ensure_ascii=False),
             json.dumps(e.spec_snapshot.to_dict(), ensure_ascii=False),
             e.note,
             e.started_at.isoformat() if e.started_at else None,
             e.ended_at.isoformat() if e.ended_at else None,
             ersetzt),
        )

    def _kennzahlen_schreiben(self, session: Session, e: SessionEntry) -> None:
        spec = e.spec_snapshot
        assert spec is not None
        for key in spec.chart_metrics:
            if (wert := e.result.get(key)) is None:
                continue
            feld = spec.field_by_key(key)
            self.con.execute(
                "INSERT INTO measurement (id, subject_id, metric_key, value, unit, recorded_at, "
                "session_id, session_entry_id, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'exercise')",
                (new_id(), session.subject_id, f"{e.exercise_id}:{key}", float(wert),
                 (feld.unit if feld else None) or "", session.started_at.isoformat(),
                 session.id, e.id),
            )

    def _eintrag_laden(self, eintrag_id: str) -> SessionEntry | None:
        r = self.con.execute(
            "SELECT e.* FROM session_entry e WHERE e.id = ?", (eintrag_id,)
        ).fetchone()
        return self._zeile(r) if r else None

    def _session_laden(self, session_id: str) -> Session:
        r = self.con.execute("SELECT * FROM session WHERE id = ?", (session_id,)).fetchone()
        return Session(
            id=r["id"], subject_id=r["subject_id"],
            started_at=datetime.fromisoformat(r["started_at"]),
            ended_at=datetime.fromisoformat(r["ended_at"]) if r["ended_at"] else None,
            plan_id=r["plan_id"], note=r["note"], mood=r["mood"],
        )

    @staticmethod
    def _zeile(r: sqlite3.Row) -> SessionEntry:
        return SessionEntry(
            id=r["id"], session_id=r["session_id"], exercise_id=r["exercise_id"],
            order=r["sort_order"], result=json.loads(r["result_json"]),
            spec_snapshot=ResultSpec.from_dict(json.loads(r["spec_snapshot_json"])),
            note=r["note"],
            started_at=datetime.fromisoformat(r["started_at"]) if r["started_at"] else None,
            ended_at=datetime.fromisoformat(r["ended_at"]) if r["ended_at"] else None,
        )


# Gültig = nicht gelöscht und nicht durch einen neueren Eintrag ersetzt.
_GUELTIGE = """
    SELECT e.* FROM session_entry e
    JOIN session s ON s.id = e.session_id
    WHERE e.deleted_at IS NULL
      AND NOT EXISTS (SELECT 1 FROM session_entry n WHERE n.replaces_entry_id = e.id)
"""
```

Zwei Entscheidungen darin:

- **Die Korrektur übernimmt die Kopie des alten Eintrags**, nicht die aktuelle
  Spezifikation der Übung. Der Eintrag beschreibt, was damals gemacht wurde —
  mit der Notation von damals. Hätte sich die Übung inzwischen geändert, wäre
  eine Korrektur mit neuer Spezifikation ein stiller Formatwechsel.
- **Ersetzte Kennzahlen werden gelöscht**, nicht markiert. `measurement` ist
  ein abgeleiteter Bestand — die Wahrheit steht in `session_entry`. Was
  abgeleitet ist, darf man neu ableiten.

Tests:

```python
@pytest.fixture
def welt(con):
    """Datenbank mit Seed, einem Profil und einer Sitzung."""
    seed_einspielen(con)
    ich = Subject(name="Ich")
    SubjectRepo(con).speichern(ich)
    sitzung = Session(subject_id=ich.id)
    repo = SessionRepo(con)
    repo.anlegen(sitzung)
    return con, repo, ich, sitzung


def test_eintrag_mit_kopie(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = ExerciseRepo(con).laden(seed_id("wadenheben"))
    repo.eintrag_anlegen(sitzung, uebung, {"sets": 3, "reps": 15})
    assert [e.shorthand() for e in repo.eintraege(sitzung.id)] == ["3x15"]


def test_eintrag_ueberlebt_aenderung_der_uebung(welt) -> None:
    con, repo, ich, sitzung = welt
    uebungen = ExerciseRepo(con)
    uebung = uebungen.laden(seed_id("wadenheben"))
    repo.eintrag_anlegen(sitzung, uebung, {"sets": 3, "reps": 15})

    uebung.result_spec = SPEC_HALTEN       # die Übung wird umgebaut
    uebungen.speichern(uebung)

    assert repo.eintraege(sitzung.id)[0].shorthand() == "3x15"


def test_letzter_eintrag_ueber_sitzungen(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = ExerciseRepo(con).laden(seed_id("wadenheben"))
    repo.eintrag_anlegen(sitzung, uebung, {"sets": 3, "reps": 12})
    spaeter = Session(subject_id=ich.id, started_at=jetzt() + timedelta(days=1))
    repo.anlegen(spaeter)
    repo.eintrag_anlegen(spaeter, uebung, {"sets": 3, "reps": 20})

    assert repo.letzter_eintrag(ich.id, uebung.id).result["reps"] == 20
    assert repo.letzter_eintrag(ich.id, "gibt-es-nicht") is None


def test_korrektur_ersetzt(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = ExerciseRepo(con).laden(seed_id("wadenheben"))
    alt = repo.eintrag_anlegen(sitzung, uebung, {"sets": 3, "reps": 15})
    neu = repo.eintrag_korrigieren(alt.id, {"sets": 3, "reps": 20})

    assert [e.id for e in repo.eintraege(sitzung.id)] == [neu.id]
    assert [m.value for m in repo.verlauf(ich.id, f"{uebung.id}:reps")] == [20.0]
    assert con.execute("SELECT COUNT(*) FROM session_entry").fetchone()[0] == 2


def test_ohne_chart_metrics_keine_kennzahl(welt) -> None:
    con, repo, ich, sitzung = welt
    uebung = ExerciseRepo(con).laden(seed_id("wadenheben"))
    uebung.result_spec = replace(uebung.result_spec, chart_metrics=[])
    repo.eintrag_anlegen(sitzung, uebung, {"sets": 3, "reps": 15})
    assert con.execute("SELECT COUNT(*) FROM measurement").fetchone()[0] == 0
```

## Zum Nachdenken

**1. Tipper für „3x12".** Chips: zwei Tipps (`3`, `12`) — wenn die Vorbelegung
nicht ohnehin schon stimmt, dann null. Kurzschrift: `3`, Tastaturwechsel, `x`,
Tastaturwechsel, `1`, `2`, „Übernehmen" — sieben. Felder: Feld antippen, `3`,
Feld antippen, `1`, `2` — fünf, und zwei davon treffen kleine Ziele. Das ist
der ganze Grund für die Reihenfolge in Abschnitt 4.

**2. Letzter Eintrag des Plans.** Wenn dieselbe Übung in zwei Plänen mit
verschiedenen Vorgaben steht — etwa Wadenheben 3x15 im Aufbauplan und 2x30 im
Erhaltungsplan —, dann ist „wie zuletzt in *diesem Plan*" die bessere Vorbelegung.
Für Edition A ohne Pläne ist die Übung die richtige Einheit. In Edition B
lohnt sich die Unterscheidung; das Schema trägt sie bereits (`session.plan_id`).

**3. Plan in der Session.** `session.plan_id` ist nur ein Verweis — ändert die
Therapeutin den Plan, zeigt die alte Sitzung auf den neuen Inhalt. Für die
Frage „was war damals verordnet?" bräuchte es eine Kopie wie beim Eintrag.
Wir haben sie weggelassen, weil die Einträge selbst schon festhalten, was
gemacht wurde — die Verordnung dahinter ist in Edition A nicht relevant. In
Edition B wird man das wahrscheinlich nachrüsten müssen; `plan_item.target`
ist der Kandidat für die Kopie.
