# Planung: Kurse (15.10.2026)

Bens Notiz vom 15.10.2026: Neben Übungen und Plänen eine dritte Kategorie,
**Kurse** — Kapitel, die man von oben nach unten durcharbeitet, mit
Erklärinhalten (Text, Bild, Ton, Video), Freischaltbedingungen („100
Liegestützen, dann das nächste Video“), optional verbundenen Tagesplänen und
Überspringen nur auf Rückfrage. Ein Kurs kann auch ein reines Tutorial sein
(HRV-Messung: was ist das, wie bediene ich die App).

Stand 15.10.2026: **Phasen 0–3 gebaut** (Abschnitt 6). Offene Entscheidungen
stehen im Katalog `docs/offene_fragen.md` (P16–P21), nicht hier.

---

## 1. Begriffe

| Begriff | Bedeutung | Code |
|---|---|---|
| **Kurs** | Name, Beschreibung, Kapitel in fester Reihenfolge, Freischaltmodus `frei`, `rueckfrage` (Vorgabe), `streng`; Herkunft Paket oder eigener | `core/kurse.Kurs`, Tabelle `course` |
| **Kapitel** | Titel, Erklärtext (Markdown), Medien (Video, Bild, **Ton**), 0..n Plan-Vorlagen, eine Bedingung | `Kapitel`, Tabelle `course_chapter` |
| **Bedingung** | Was erfüllt sein muss, damit das nächste Kapitel aufgeht — siehe Abschnitt 3 | `Bedingung`, Spalte `gate_json` |
| **Plan-Vorlage** | Ein Plan, den das Kapitel beim Erreichen als echten Plan anlegt | `PlanVorlage`, Spalte `plans_json` |
| **Fortschritt** | Je Profil und Kapitel: erreicht, abgeschlossen, übersprungen | `Kapitelstand`, Tabelle `course_progress` |

Ein Kapitel ist **erreicht**, sobald man es öffnet (dann entstehen seine Pläne
und die Bedingung zählt ab jetzt); **abgeschlossen** mit „Weiter“. Status je
Kapitel: fertig · übersprungen · aktuell · gesperrt (bei `frei`: offen).

## 2. Pläne im Kurs — Entscheidung

Bens Frage: Wochentage je Planübung (Atmung Mo/Mi/Fr, Kräftigung Di/Do in
*einem* Plan) oder mehrere Pläne? **Gebaut: mehrere Pläne je Kapitel, die
Wochentage bleiben am Plan** (`plan.weekdays_json`, wie bisher).

- „Atmung Mo/Mi/Fr, Kräftigung Di/Do“ = zwei Plan-Vorlagen im Kapitel.
- Beim Erreichen des Kapitels legt die App die Vorlagen als **echte Pläne** an
  (`plan.course_chapter_id` = Herkunft, aktiv, `subject_id` = Profil). Sie
  erscheinen auf „Heute“ an ihren Wochentagen, lassen sich dort üben und in der
  Planverwaltung ändern — es sind gewöhnliche Pläne.
- Beim Abschluss des Kapitels werden sie **deaktiviert, nicht gelöscht**:
  Einträge bleiben, der Plan bleibt wählbar. „Von vorn beginnen“ deaktiviert
  ebenfalls; ein neuer Start aktiviert dieselben Pläne wieder (kein Duplikat).
- Heute, Tagesbilanz, Verlauf, Planblock: **unverändert**. Kein Wochentag je
  Planübung — das bliebe die Alternative (P16), falls Ben sie ausdrücklich will.

## 3. Bedingungen

Alle werden **aus vorhandenen Daten gerechnet** (`core.kurse.bedingung_stand`,
Daten holt `data.kurse.KursRepo.stand`), **ab dem Erreichen des Kapitels**
(P18: oder gesamt?):

| Art | Erfüllt, wenn … | Datenquelle |
|---|---|---|
| `gelesen` | Kapitel geöffnet und „Weiter“ gedrückt | — |
| `summe` | Menge eines Feldes einer Übung ≥ Soll (`reps`, `hold`, …); **Varianten zählen mit** (gleiche Kachel) | `SessionRepo.eintraege_zwischen` + `tagesbilanz.mengen` |
| `tage` | an ≥ Soll Tagen mindestens ein Eintrag einer Übung der Kapitelpläne | dito, Tage gezählt |
| `messung` | eine HRV-Aufzeichnung ≥ Soll Minuten seit Kapitelstart | `HrvRepo.alle` — nur Dauer und Zeitpunkt |

**Rechtlich:** `messung` prüft nur, *dass* gemessen wurde — nie einen Messwert.
Eine Bedingung „RMSSD über 40“ wäre eine Handlungsempfehlung aus Messwerten
(`physiologische_steuerung`, `docs/recht/00_zweckbestimmung.md`) und ist nicht
vorgesehen. Die Kurstexte erklären, sie bewerten nicht.

## 4. Überspringen

- `rueckfrage` (Vorgabe): **eine** Rückfrage — „Noch 60 Wdh. bis ‚Üben‘
  geschafft ist. Trotzdem freischalten?“ Das Kapitel gilt dann als
  **übersprungen** (sichtbar im Kurs), seine Pläne werden deaktiviert, das
  nächste Kapitel ist erreicht. Zweimal fragen (P17)? Bisher nicht.
- `streng`: kein Überspringen — vorbereitet für zugewiesene Kurse
  (Edition B, `ist_aktiv("zugewiesene_kurse")`).
- `frei`: alle Kapitel offen; „Weiter“ ohne erfüllte Bedingung zählt still als
  übersprungen.

## 5. Oberfläche und Verteilung

- Dritter Unterreiter **Übungen | Pläne | Kurse** (`ui/views/uebungen.py`),
  kein runder Knopf (Kurse kommen über Pakete; Editor später). Alternative
  eigener Hauptreiter: P19.
- `ui/views/kurse.py`: Kursliste → Kurs (`/kurse/<id>`, Kapitel mit Status,
  „Kurs beginnen“, Menü „Von vorn beginnen“) → Kapitel
  (`/kurse/<id>/<kapitel>`: Markdown, Medienliste, Pläne mit „Trainieren“,
  Stand mit Balken, „Weiter“ / „Trotzdem freischalten“ / „Nächstes Kapitel“).
- **Inhalte:** Text per `ft.Markdown`; Bild, Ton, Video als Links, die im
  Browser öffnen — wie die Videos der Übungen. Inline-Bilder und ein Tonspieler
  erst nach der vertagten Medienentscheidung (K-F6, P20).
- **Pakete:** Kurse reisen im Paketformat, Feld `kurse[]`, **Formatversion 2**
  (`docs/uebungspakete.md`). Übungen heißen im Kurs wie im Paket (`key`) oder
  per ID. Ein Paket ohne Kurse bleibt Version 1. Import: dieselben Regeln wie
  Übungen; Kapitel-IDs bleiben, darum bleibt der Fortschritt bei einem Update.
  Entfernen nimmt die Kurse aus der Liste, „Wieder installieren“ holt sie aus
  dem Paketstand zurück (`course.package_standard_json`).
- **Erster Kurs:** „HRV-Messung verstehen“ (7 Kapitel: Was ist HRV · Sensor ·
  erste Messung (`messung` 5 min) · Kurve lesen · Notizen · Ruhig atmen (Plan
  Kohärenzatmung, `tage` 3) · Einstellungen) im Paket „Standard“
  (`data/seed/standard.toml`, Abschnitt Kurse). **Abweichung vom Plan:** nicht
  als eigene Paketdatei, weil er so die Atemübung per Schlüssel referenziert und
  viele Tests genau ein mitgeliefertes Paket erwarten. Texte = erster Entwurf (P21).

## 6. Phasen

| Phase | Inhalt | Stand |
|---|---|---|
| 0 | Dokumentation: diese Datei, Katalog P16–P21, Roadmap M12, Datenmodell, Paketformat | gebaut |
| 1 | Kern und Datenbank: `core/kurse.py`, Migration 016, `data/kurse.py`, `plan.course_chapter_id`, Schalter `kurse` | gebaut |
| 2 | Oberfläche: dritter Reiter, Kurs, Kapitel, Weiter/Freischalten, Pläne aus Kapiteln | gebaut |
| 3 | Paketformat v2 mit `kurse[]`, erster Kurs im Standardpaket | gebaut |
| 4 | Kurseditor (eigene Kurse), Inline-Medien und Tonspieler (nach K-F6), Kurszeile auf „Heute“, Export ausgewählter Kurse, Zuweisung in Edition B, Sync des Fortschritts — Stufen und Fragen: `plan_kurseditor.md` (27.10.2026) | offen |

Tests: `tests/test_kurse.py` (Rechnung, Datenbank, Paketformat, Seed),
`tests/test_ui_kurse.py` (Liste, Kurs, Kapitel, Weiter, Freischalten, Plan aus
Kapitel). Noch nicht am Handy geprüft (T13 im Katalog).
