# Planung: Kurse bearbeiten (27.10.2026)

Bens Auftrag vom 27.10.2026: überlegen, wie man einen Kurs bearbeitet — mit den
bisherigen Bedingungen und allem, was dazugehört; der Kurs wird noch ausgebaut.
Stand: Phase 4 aus `plan_kurse.md` (Kurseditor) ist offen. **Gebaut ist seit heute der
Rückweg aus der App ins TOML** (`trainingsapp-paket uebernehmen`, `uebungspakete.md`):
Übungen und die Pläne, die Kapitel angelegt haben. Dieses Papier ordnet, was ein
Kurseditor darüber hinaus braucht, und hält die Entscheidungen fest, die Ben trifft.

---

## 1. Was ein Kurs ist — und was beim Bearbeiten nicht brechen darf

| Teil | Felder (`core/kurse.py`) | Darf sich ändern? |
|---|---|---|
| Kurs | Name, Beschreibung, Freischaltung (`frei`, `rueckfrage`, `streng`) | ja |
| Kapitel | Titel, Text (Markdown), Medien (Links), Pläne (Vorlagen), Bedingung | ja |
| Reihenfolge der Kapitel | `order` | ja — der Fortschritt hängt an der Kapitel-ID, nicht an der Nummer |
| Kapitel-`key` → ID | `kapitel_id(kurs, key)` | **nie** — daran hängt `course_progress` auf allen Geräten |
| Bedingung | `gelesen` · `summe` (Übung, Feld, Soll) · `tage` (Soll) · `messung` (Minuten) | ja, nur diese vier Arten |

Zwei Regeln gelten für jeden Weg, ob TOML oder App:

- **Bedingungen rechnen aus Einträgen und Messdauer, nie aus Messwerten**
  (`plan_kurse.md` § 3, `docs/recht/00_zweckbestimmung.md`). Ein Editor bietet nur die
  vier Arten an; es gibt keine freie Formel.
- **Erklären, nicht bewerten** (Sprachregelung der Homepage, Zone 3): Kapiteltexte
  laufen durch `pruefen --wortliste`. Das bleibt der Grund, warum Texte am Ende durch das
  Inhalte-Repo gehen — dort läuft die Prüfung vor jeder Veröffentlichung.

## 2. Zwei Arten von Bearbeitung

Ein Kurs besteht aus zwei Hälften, die sich verschieden bearbeiten lassen:

| | Text und Medien | Struktur und Parameter |
|---|---|---|
| Was | Kapiteltexte (Markdown), Titel, Beschreibung, Links | Reihenfolge, Bedingung, Pläne (Wochentage, Übungen, Ziele), Freischaltung |
| Wo heute | TOML im Inhalte-Repo, Editor am Rechner, `git diff` | TOML |
| Wo besser | am Rechner (lange Texte, Wortliste, Versionsgeschichte) | in der App — man sieht die Übungen, Chips und Pläne, wie Nutzer sie sehen |
| Rückweg ins TOML | — (die Datei ist die Quelle) | `uebernehmen` — für Pläne gebaut, für Bedingung und Reihenfolge noch nicht |

Daraus folgt der Vorschlag: **Der Kurseditor in der App bearbeitet zuerst die rechte
Spalte.** Texte bleiben in der Datei. Das ist auch der Grund, warum „Export des Kurses
aus der App“ (Phase 4) nicht der erste Schritt sein muss: Was in der App entsteht, holt
`uebernehmen` aus der Datenbank, und die Datei bleibt die eine Quelle (vgl.
Versionsschutz in `uebungspakete.md`: gleiche Version, sonst nichts).

## 3. Stufen

| Stufe | Inhalt | Braucht |
|---|---|---|
| 1 | **Kapitel bearbeiten** in `ui/views/kurse.py`: Bedingung (Art, Übung aus dem Paket, Feld, Soll), Pläne (gibt es schon: Planverwaltung), Kapitel verschieben. Speichert in `course_chapter` (`gate_json`, `order`). `uebernehmen` holt Bedingung und Reihenfolge ins TOML | kein neues Datenmodell; Kapitel-IDs bleiben |
| 2 | **Kurs bearbeiten**: Name, Beschreibung, Freischaltung; Kapitel anlegen und löschen. Neue Kapitel brauchen einen `key` (§ 4, Frage C2) | Paketstand des Kurses (`package_standard_json`) kennt die neuen Kapitel noch nicht — „Auf Paketstand“ nähme sie weg; Regel nötig |
| 3 | **Eigene Kurse** (ohne Paket) und **Export ausgewählter Kurse** im Paketmanager (Format v2 kann `kurse[]` schon) | Export-Dialog um Kurse erweitern; Kapitel-Text auf dem Gerät eingeben — Frage C1 |
| 4 | Texte und Medien in der App, Inline-Bilder, Ton | nach K-F6 (Medienentscheidung), P20 |

Stufe 1 ist klein und passt in den vorhandenen Kapitel-Bildschirm. Stufe 3 ist der
„Kurseditor“ aus `plan_kurse.md` Phase 4.

## 4. Fragen an Ben (vor Stufe 1 klären)

- **C1 — Wo wird Text bearbeitet?** Vorschlag: in der Datei (§ 2). Alternative: Markdown-
  Feld in der App, Desktop-Fenster (`flet run`) reicht, kein Handy-Editor.
- **C2 — Neue Kapitel aus der App:** ein `key` aus dem Titel (`stehen_ueben`; die ID
  ändert sich, wenn der Titel vor dem ersten Übernehmen noch wechselt) oder die ID der
  App ins TOML (`id = "…"`, Format erlaubt es; unlesbar, aber stabil)? Vorschlag: `key`
  aus dem Titel, und `uebernehmen` warnt, wenn ein Kapitel dadurch neu würde.
- **C3 — Bedingung „summe“ über Varianten:** Varianten zählen mit (`plan_kurse.md` § 3).
  Wenn der Editor eine Übung anbietet, zeigt er dann die Variantengruppe oder die eine
  Übung? Hängt an `plan_varianten.md`, dort nachsehen, wenn Stufe 1 gebaut wird.
- **C4 — Was heißt „Kurs ausbauen“?** Mehr Kapitel im HRV-Kurs (dann reicht Stufe 1 plus
  Datei), weitere Kurse im Standardpaket (Datei), oder Kurse von Nutzern (Stufe 3)?
  Danach richtet sich, welche Stufe als erste gebaut wird.

## 5. Zu den Plänen (B) — was offen blieb

`uebernehmen` holt Pläne aus Kurskapiteln zurück. Zwei Dinge kann es nicht, weil das
Format sie nicht kennt:

- **B1 — Eigene Pläne ohne Kapitel** („Daily“ in Bens Testdatenbank). Ein Paket
  beschreibt Übungen und Kurse, nicht Training (`core/pakete.py`, Modulkopf). Sollen
  Pakete trotzdem Pläne mitbringen (`plaene[]` auf oberster Ebene, beim Import je Profil
  angelegt)? Vorschlag: nein — ein Plan, der zu einem Paket gehört, ist ein Kapitelplan
  eines Kurses mit einem Kapitel.
- **B2 — Felder des Plans, die die Vorlage nicht hat:** Timer für alle Übungen,
  „automatisch weiter“, Pause ohne Timer, Chips und Notiz je Planübung. Die Vorlage kennt
  Name, Wochentage, Übungen mit Ziel und Feldern. Ins Format aufnehmen (abwärtskompatibel:
  ältere Apps überlesen unbekannte Felder)? Dann holt `uebernehmen` sie mit.
- **B3 — Umbenannte Pläne:** Die Zuordnung läuft über den Namen in seinem Kapitel. Nach
  einer Umbenennung in der App meldet das Werkzeug „keine Vorlage“. Alternative:
  Zuordnung über die Stelle (der n-te Plan des Kapitels).
