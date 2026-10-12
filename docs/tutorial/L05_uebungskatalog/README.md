# L05 — Übungskatalog

**Ziel:** Du verstehst den Code, der in M2 entstanden ist — und zwar gut genug,
um ihn zu erweitern. Der Katalog kommt aus der Datenbank, hat Suche, Filter,
Detailansicht, Videolinks und eigene Übungen.

Zeit: zwei bis drei Stunden.

Diese Lektion ist anders als L01–L04: Der Code existiert schon. Du liest ihn
entlang dieser Erklärung, probierst die Beispiele aus und baust in der Übung
etwas dazu. Öffne dabei `src/trainingsapp/data/seed.py`,
`data/repositories.py`, `ui/state.py`, `ui/views/katalog.py` und `ui/app.py`.

---

## 1. Der Seed erkennt sich an der ID wieder

Beim ersten Start sollen die mitgelieferten Übungen in die Datenbank. Beim
zweiten Start nicht noch einmal. Und wenn du eine mitgelieferte Übung
umbenennst, darf ein App-Update sie nicht zurücksetzen.

Woran erkennt der Seed, was schon da ist? Das Schema hat keine Spalte dafür,
und die IDs aus `new_id()` sind zufällig. Die Lösung in `data/seed.py`:

```python
SEED_NAMENSRAUM = uuid.UUID("6f1c2b3a-7d4e-4a5b-9c8d-1e2f3a4b5c6d")

def seed_id(key: str) -> str:
    return str(uuid.uuid5(SEED_NAMENSRAUM, key))
```

**UUIDv5** ist eine UUID, die aus einem Namensraum und einem Text berechnet
wird — deterministisch. `seed_id("wadenheben")` ergibt heute, morgen und auf
jedem Gerät dieselbe ID. Damit ist „gibt es die Übung schon?" eine Abfrage auf
den Primärschlüssel:

```python
for uebung in seed_laden(datei):
    if repo.existiert(uebung.id):
        continue            # vorhanden → unangetastet lassen
    repo.speichern(uebung)
```

Nebeneffekt, der später zählt: In Edition B meinen Handy und Praxisserver mit
derselben ID dieselbe Übung. Ohne eine Zeile Abgleichcode.

Der Namensraum darf sich **nie** ändern. Sonst bekäme jede Seed-Übung eine neue
ID und würde beim nächsten Start ein zweites Mal angelegt. Beispiel 1 zeigt
genau das.

`seed_laden()` baut nur Objekte, `seed_einspielen()` schreibt sie. Die
Trennung macht den Katalog testbar, ohne eine Datenbank anzulegen.

---

## 2. Repository: Medien in einer Abfrage

Eine Übung hat null bis viele Videolinks (`exercise_media`). Die naive Lösung
wäre: Übungen laden, dann je Übung die Medien nachladen. Bei 13 Übungen sind
das 14 Abfragen, bei 200 sind es 201. Das Muster heißt **N+1** und ist der
häufigste Grund, warum Listen langsam werden.

`ExerciseRepo._mit_medien()` macht es in einer Abfrage für alle:

```python
ids = [u.id for u in uebungen]
platzhalter = ",".join("?" * len(ids))          # "?,?,?"
for r in self.con.execute(
    f"SELECT * FROM exercise_media WHERE exercise_id IN ({platzhalter}) "
    "ORDER BY exercise_id, sort_order",
    ids,
):
    nach_uebung[r["exercise_id"]].append(Media(...))
```

Das f-String hier ist **kein** Verstoß gegen „immer Platzhalter": Es fügt nur
die richtige Anzahl Fragezeichen ein, die Werte gehen weiterhin als Parameter.

Beim Speichern werden die Medien einer Übung komplett ersetzt — löschen und neu
schreiben, in einer Transaktion (`with transaktion(self.con)`). Ein Abgleich
„welche sind neu, welche weg" wäre mehr Code für keinen messbaren Gewinn bei
einer Handvoll Links.

---

## 3. Suche: Namenstreffer zuerst

```sql
SELECT *, (CASE WHEN name LIKE ? THEN 0 ELSE 1 END) AS rang
FROM exercise
WHERE deleted_at IS NULL AND archived = 0
  AND (name LIKE ? OR description LIKE ?)
ORDER BY rang, name COLLATE NOCASE
```

Drei Dinge:

- **Rang in SQL.** Die Datenbank sortiert, nicht Python. Bei 13 Übungen egal,
  bei 2 000 nicht — und vor allem bleibt die Ansicht frei von Logik.
- **`COLLATE NOCASE`** sortiert „Übung" und „atmung" so, wie ein Mensch es
  erwartet. Ohne das kommen Großbuchstaben vor Kleinbuchstaben.
- **Leere Suche = `alle()`.** Die Ansicht muss nicht zwischen zwei Methoden
  umschalten, je nachdem ob etwas im Suchfeld steht.

Beispiel 2 zeigt den Rang an echten Daten.

---

## 4. Die Katalog-Ansicht: Zustand → `zeichnen()`

`ui/views/katalog.py` folgt dem Muster aus L03: Handler ändern den Zustand,
eine Funktion `zeichnen()` leitet die Anzeige daraus ab.

```python
def suchen(e: ft.Event[ft.TextField]) -> None:
    state.suchtext = e.control.value or ""
    zeichnen()
    page.update()
```

Suchtext und Kategoriefilter liegen im `AppState`, nicht in der Ansicht.
Darum ist beides noch da, wenn du auf „Heute" und zurück wechselst — die
Ansicht wird dabei neu gebaut, der Zustand nicht.

### Handler in Schleifen — ohne Lambda

Jeder Listeneintrag braucht einen Handler, der *seine* Übung öffnet. Das ist
die Stelle, an der in L03 Lambdas standen. Hier steht stattdessen eine
**Fabrikfunktion**:

```python
def oeffner(uebung_id: str) -> Callable[[], object]:
    async def handler() -> None:
        await page.push_route(f"/uebung/{uebung_id}")
    return handler

# in der Schleife:
ft.ListTile(title=ft.Text(u.name), on_click=oeffner(u.id))
```

`oeffner(u.id)` wird **sofort** aufgerufen und gibt eine neue Funktion zurück,
die sich genau diese ID gemerkt hat. Dreizehn Aufrufe, dreizehn Funktionen,
dreizehn verschiedene IDs. Mehr ist eine Closure nicht: eine Funktion plus die
Variablen, die sie beim Erzeugen gesehen hat.

Warum nicht `lambda e: page.push_route(f"/uebung/{u.id}")` in der Schleife?
Weil ein Lambda `u` nicht beim Erzeugen liest, sondern beim **Aufruf** — und
dann steht in `u` die letzte Übung der Schleife. Alle dreizehn Einträge
öffnen dieselbe. Beispiel 3 führt das vor, mit beiden Auswegen.

### Handler ohne Parameter

Fällt dir auf, dass `handler()` keinen Parameter `e` hat? Flet erlaubt beides.
Wer das Ereignis nicht braucht, lässt es weg — dann sieht man einer Funktion
sofort an, ob sie etwas vom Control liest. `suchen(e)` braucht den Wert des
Textfelds, `handler()` nicht.

---

## 5. Routen und Dienste in `app.py`

```
/                          Hauptansicht mit vier Reitern
/uebung/neu                neue Übung
/uebung/<id>               Detail
/uebung/<id>/bearbeiten    bearbeiten
/einstellungen             Profile
```

`zeige_route()` zerlegt die Route und baut den **ganzen** Stapel neu:

```python
teile = [t for t in page.route.split("/") if t]   # "/uebung/abc" → ["uebung", "abc"]
if teile[:1] == ["uebung"] and len(teile) >= 2:
    if teile[1] == "neu":
        page.views.append(uebung_bearbeiten(page, state, None))
    elif (uebung := state.uebungen.laden(teile[1])) is not None:
        page.views.append(uebung_detail(page, state, uebung, browser))
        if teile[2:] == ["bearbeiten"]:
            page.views.append(uebung_bearbeiten(page, state, uebung))
```

Eine unbekannte ID führt nicht zum Absturz, sondern zur Hauptansicht —
`laden()` liefert `None`, und der Stapel endet eben früher.

**Dienste.** Einen Link im Browser zu öffnen ist in Flet 1.0 Sache eines
*Service*: ein Control ohne Darstellung, das an der Seite hängen muss.

```python
browser = ft.UrlLauncher()
page.services.append(browser)
# in der Detailansicht:
await browser.launch_url(medium.uri)
```

Der Dienst wird in `main()` einmal angelegt und an die Ansicht durchgereicht,
die ihn braucht. Nicht im `AppState` — der bleibt flet-frei.

**Der runde Knopf** „Neue Übung" gehört nur zum Katalog. Deshalb setzt
`hauptansicht_aktualisieren()` `floating_action_button` je nach Reiter.

---

## 6. Profile und die zweite Migration

Die App kennt Profile (Tabelle `subject`), und sie soll beim Start das zuletzt
aktive laden. Wo merkt man sich das? Nicht im `subject` selbst — „aktiv" ist
keine Eigenschaft der Person, sondern dieses Geräts. Auf einem zweiten Handy
könnte ein anderes Profil aktiv sein.

Dafür gibt es jetzt **Migration 002**:

```sql
CREATE TABLE app_setting (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
```

Das ist die erste Migration nach der ersten — und genau der Fall, für den der
Mechanismus aus L04 gebaut wurde. Was beim Start passiert:

1. `oeffnen()` liest `PRAGMA user_version` → 1 (alte Datenbank) oder 0 (neue).
2. `migrieren()` findet `002_app_setting.sql`, Nummer 2 > 1, spielt sie ein.
3. `PRAGMA user_version = 2`.

Beim nächsten Start: 2 ≤ 2, nichts zu tun. Deine bestehende Datenbank aus L04
hat die Tabelle also einfach dazubekommen — ohne dass du etwas gelöscht hast.
`tests/test_core.py` prüft inzwischen auf Version 2.

`AppState.starten()` fasst den Start zusammen:

```python
con = oeffnen(db_pfad)
neu = seed_einspielen(con)
profil = cls._aktives_profil(profile, einstellungen)
```

`_aktives_profil()` hat drei Stufen: das gemerkte Profil, sonst das erste
vorhandene, sonst ein neues namens „Ich". Die zweite Stufe ist wichtig: Zeigt
die Einstellung auf ein Profil, das es nicht mehr gibt, startet die App
trotzdem. `tests/test_state.py` prüft genau diesen Fall.

Eine Sperre per PIN gibt es in Edition A nicht — `ist_aktiv("profil_sperre")`
ist dort `False`. Die Einstellungsansicht fragt den Schalter trotzdem, damit
Edition B ihn einhängen kann, ohne die Ansicht umzubauen.

---

## 7. Warum Videos nicht ins App-Paket gehören

Google Play deckelt das Basis-APK bei 150 MB. Ein einziges Erklärvideo in
brauchbarer Qualität sind 20–50 MB. Drei Videos, und die App ist nicht mehr
veröffentlichbar.

Deshalb speichert `exercise_media` nur **Verweise**: `source = 'url'` für
Links, `'asset'` für Dinge, die wirklich mit der App kommen (Symbole), `'local'`
für Fotos, die der Nutzer selbst macht. Eine Übung kann mehrere Videos haben —
die Detailansicht zeigt sie als Liste, ein Tipp öffnet den Browser.

Herunterladen zum Offline-Ansehen kommt später (M10). Es hängt davon ab, wo
die Videos liegen: Ein YouTube-Link lässt sich nicht herunterladen, eine
selbst gehostete MP4-Datei schon.

---

## 8. `ListView` statt `Column`

Der Katalog benutzt `ft.ListView`, nicht `ft.Column`. Der Unterschied: Eine
`Column` baut alle Kinder, eine `ListView` nur die sichtbaren und die kurz
davor und danach. Bei 13 Einträgen merkt man nichts. Bei 500 Trainingseinträgen
im Verlauf (L12) entscheidet es, ob die Ansicht flüssig scrollt.

Faustregel: Weiß man die Anzahl nicht, `ListView`.

---

## 9. Beispiele

```bash
uv run python docs/tutorial/L05_uebungskatalog/beispiel_01.py     # UUIDv5 und Seed
uv run python docs/tutorial/L05_uebungskatalog/beispiel_02.py     # Suche mit Rang
uv run flet run docs/tutorial/L05_uebungskatalog/beispiel_03.py   # Handler in Schleifen
```

Die ersten beiden brauchen kein Fenster und laufen in der CI mit.

---

## Stolperfallen

**Deutsche Anführungszeichen in Python-Strings.** Wir schreiben „so" — mit
einem normalen `"` als schließendem Zeichen. In einem Python-String mit
doppelten Anführungszeichen beendet das den String. Innen einfache nehmen:
`'Reiter „Übungen".'`

**`ft.Icons` ist kein Enum mehr, sondern ein Stellvertreter.** `ft.Icons("air")`
und `ft.Icons["AIR"]` scheitern. Was geht: `getattr(ft.Icons, "AIR")`. So macht
es `ui/components/icons.py`, mit Rückfall auf ein Standardsymbol.

**`TextField.error`, nicht `error_text`.** Die Eigenschaft heißt in Flet 1.0
`error`. Ein falscher Name wird stillschweigend ignoriert — der Fehlertext
erscheint einfach nicht. Der UI-Rauchtest fängt das nicht, weil Flet unbekannte
Attribute beim Zuweisen nicht prüft, nur beim Anlegen.

**`page.launch_url` ist veraltet.** Stattdessen `ft.UrlLauncher()` als Dienst
registrieren (Abschnitt 5).

**Chips mit Häkchen.** Ein ausgewählter `Chip` zeigt standardmäßig ein Häkchen.
Für einen Filter wirkt das falsch — `show_checkmark=False`.

**pytest lädt das Flet-Plugin.** `flet` bringt ein pytest-Plugin mit. In einer
Umgebung mit flet läuft deshalb auch `tests/test_ui_smoke.py`; ohne flet (wie in
der CI) wird er per `pytest.importorskip("flet")` übersprungen.

---

## Weiter

→ [Übung](uebung.md) → [Checkliste](checkliste.md) → **L06: Flexible Notation**
