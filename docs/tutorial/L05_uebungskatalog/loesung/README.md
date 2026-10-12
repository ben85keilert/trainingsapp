# L05 — Lösungen

## Aufgabe 1: Code lesen

**1. Leere Suche.** `suchen()` prüft `if not text.strip(): return self.alle(kategorie)`.
Die Ansicht ruft deshalb immer `suchen(state.suchtext, state.kategorie)` — ob
etwas im Feld steht oder nicht. Ohne diesen Kurzschluss bräuchte `zeichnen()`
eine Verzweigung, und die Logik „leer heißt alle" läge in der Oberfläche statt
im Repository.

**2. Gelöschtes Profil.** Stufe 1 (`gemerkt`) findet die ID in `app_setting`,
aber `profile.laden()` liefert `None` — der Walrus-Ausdruck
`(profil := profile.laden(gemerkt)) is not None` ist falsch. Stufe 2 nimmt das
erste vorhandene Profil. Gibt es keins, legt Stufe 3 „Ich" an. In jedem Fall
wird die Einstellung danach auf das gewählte Profil gesetzt.

**3. Unbekannte Spezifikation.** `_vorlage_von()` findet keine passende
Kurzschrift und gibt `"saetze_wdh"` zurück. Beim Speichern würde die eigene
Spezifikation durch die Vorlage **überschrieben** — ein Datenverlust. Für L06
heißt das: Sobald es eigene Spezifikationen gibt, muss das Formular die
vorhandene Spezifikation unangetastet lassen, wenn der Nutzer die Auswahl nicht
ändert. Eine Option „(eigene)" im Dropdown wäre der einfachste Weg.

**4. Ohne direkten Aufruf** bliebe die Seite leer. `on_route_change` feuert nur,
wenn sich die Route **ändert** — beim Start steht sie schon auf `/`, es gibt
nichts zu ändern. Der direkte Aufruf baut den ersten Stapel.

## Aufgabe 2: `functools.partial`

```python
from functools import partial

def melden_mit_ereignis(n: str, e: ft.Event[ft.Button]) -> None:
    melden(f"D: {n} (geklickt: {e.control.content})")

reihe_d = [ft.Button(n, on_click=partial(melden_mit_ereignis, n)) for n in NAMEN]
```

`partial(f, n)` erzeugt eine Funktion, die beim Aufruf `f(n, …)` ausführt —
die festgelegten Argumente kommen **zuerst**, die beim Aufruf übergebenen
dahinter. Flet ruft den Handler mit einem Argument auf, dem Ereignis. Also
landet es an zweiter Stelle. Stünde `e` vorn, bekäme es den Namen und `n` das
Ereignis.

`partial` ist die dritte saubere Variante neben Default-Argument und
Fabrikfunktion. Im Projekt nehmen wir die Fabrikfunktion, weil man ihr beim
Lesen ansieht, was festgehalten wird, ohne `partial` zu kennen.

## Aufgabe 3: Tags

In `speichern()`, innerhalb der Transaktion nach den Medien:

```python
self.con.execute("DELETE FROM exercise_tag WHERE exercise_id = ?", (uebung.id,))
for name in uebung.tags:
    self.con.execute(
        "INSERT INTO tag (id, name) VALUES (?, ?) ON CONFLICT(name) DO NOTHING",
        (new_id(), name),
    )
    tag_id = self.con.execute("SELECT id FROM tag WHERE name = ?", (name,)).fetchone()["id"]
    self.con.execute(
        "INSERT INTO exercise_tag (exercise_id, tag_id) VALUES (?, ?)",
        (uebung.id, tag_id),
    )
```

`ON CONFLICT(name) DO NOTHING` nutzt die `UNIQUE`-Bedingung auf `tag.name`:
Gibt es den Tag schon, passiert nichts, und die folgende Abfrage holt die
vorhandene ID. So entsteht je Name genau eine Zeile.

Zum Lesen eine Schwester von `_mit_medien()`:

```python
def _mit_tags(self, uebungen: list[Exercise]) -> list[Exercise]:
    if not uebungen:
        return uebungen
    ids = [u.id for u in uebungen]
    platzhalter = ",".join("?" * len(ids))
    nach_uebung: dict[str, list[str]] = defaultdict(list)
    for r in self.con.execute(
        f"SELECT et.exercise_id, t.name FROM exercise_tag et "
        f"JOIN tag t ON t.id = et.tag_id "
        f"WHERE et.exercise_id IN ({platzhalter}) ORDER BY et.rowid",
        ids,
    ):
        nach_uebung[r["exercise_id"]].append(r["name"])
    for u in uebungen:
        u.tags = nach_uebung.get(u.id, [])
    return uebungen
```

`ORDER BY et.rowid` behält die Reihenfolge des Einfügens — `exercise_tag` hat
keine `sort_order`-Spalte, und für Tags ist das auch nicht nötig.

Aufrufen überall, wo `_mit_medien()` aufgerufen wird:
`return self._mit_tags(self._mit_medien([...]))`.

In der Detailansicht:

```python
_abschnitt("Tags", ft.Row(wrap=True, spacing=6,
    controls=[ft.Chip(label=ft.Text(t)) for t in uebung.tags]))
```

Tests:

```python
def test_tags_speichern_und_laden(repo) -> None:
    u = Exercise(name="A", tags=["Atmung", "HRV"])
    repo.speichern(u)
    assert repo.laden(u.id).tags == ["Atmung", "HRV"]


def test_gleicher_tag_nur_einmal(repo, con) -> None:
    repo.speichern(Exercise(name="A", tags=["HRV"]))
    repo.speichern(Exercise(name="B", tags=["HRV"]))
    assert con.execute("SELECT COUNT(*) FROM tag").fetchone()[0] == 1


def test_tag_entfernen(repo) -> None:
    u = Exercise(name="A", tags=["Atmung", "HRV"])
    repo.speichern(u)
    u.tags = ["HRV"]
    repo.speichern(u)
    assert repo.laden(u.id).tags == ["HRV"]
```

## Aufgabe 4: Archivierte wiederherstellen

`alle(mit_archivierten=True)` liefert **alle** Übungen, archivierte und aktive
gemischt. Für die Liste braucht man nur die archivierten — also entweder in
Python filtern:

```python
archivierte = [u for u in state.uebungen.alle(mit_archivierten=True) if u.archived]
```

oder eine eigene Methode `archivierte()` mit `WHERE archived = 1`. Bei wenigen
Übungen ist der Python-Filter in Ordnung; sauberer ist die Methode, weil die
Ansicht dann wieder keine Logik enthält.

Der Abschnitt in `einstellungen.py` folgt dem Muster der Profilliste:
`ListTile` je Übung, Fabrikfunktion für den Handler, `zeichnen()` nach dem
Wiederherstellen:

```python
def wiederhersteller(uebung_id: str) -> Callable[[], None]:
    def handler() -> None:
        state.uebungen.wiederherstellen(uebung_id)
        zeichnen()
        page.update()
    return handler
```

## Zum Nachdenken

**1. Archiviert und dann aktualisiert.** Die Übung existiert noch (archiviert
ist nicht gelöscht), also legt der Seed sie nicht neu an. Das ist gewollt: Wer
eine Übung bewusst aus dem Katalog genommen hat, will sie nach einem Update
nicht wieder darin sehen. Würde der Seed `archived` prüfen und zurücksetzen,
wäre das genau das Überschreiben, das wir vermeiden wollen.

**2. In Python filtern** lohnt sich, wenn die Daten ohnehin alle geladen sind
und sich oft ändern, wonach gefiltert wird — etwa bei einer Live-Suche über
eine Liste, die schon im Speicher liegt. Hier dagegen kommt bei jedem
Tastendruck eine SQL-Abfrage. Bei 13 Übungen ist das nicht messbar; bei
Tausenden wäre ein einmaliges Laden plus Filter in Python schneller als
Tausende Abfragen. Die Grenze liegt irgendwo bei einigen tausend Einträgen —
für einen Übungskatalog unerreichbar.

**3. Scrollposition.** Technisch möglich, aber: Die Position hängt von der
Fenstergröße ab, von der Liste, vom Filter. Sie zu speichern erzeugt mehr
Sonderfälle als Nutzen. Der `AppState` sollte halten, was fachlich Zustand ist
(Suchtext, Filter, Profil), nicht, was Darstellung ist.
