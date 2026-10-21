# Zweckbestimmung und Abgrenzung zum Medizinprodukt

> **Keine Rechtsberatung.** Diese Datei ist eine Arbeitsvorlage und eine
> Entscheidungsgrundlage. Die verbindliche Prüfung gehört zu einem Fachanwalt
> für Medizinrecht bzw. zum Datenschutzbeauftragten.

---

## Warum das ganz am Anfang steht

Ob eine Software ein Medizinprodukt nach der EU-Medizinprodukteverordnung (MDR)
ist, entscheidet **nicht die Technik**, sondern die **Zweckbestimmung des
Herstellers** — und dazu zählen neben der Funktion auch Kennzeichnung,
Gebrauchsanweisung und Werbematerial.

Das heißt: derselbe Code kann Medizinprodukt sein oder nicht, je nachdem, was
man über ihn behauptet. Deshalb muss die Formulierung feststehen, **bevor** eine
Funktion gebaut wird — nicht danach.

Die Konsequenz ist im Code verankert: `core/limits.py` markiert Regeln, die aus
Messwerten eine Handlungsempfehlung ableiten, als `EDITION_B_ONLY`.
`tests/test_core.py::test_pulsregeln_sind_in_edition_a_gesperrt` prüft es.

---

## Edition A („solo") — Fitness und Wohlbefinden

### Zweckbestimmung

> Der Trainingsassistent unterstützt beim eigenständigen Durchführen und
> Dokumentieren von Bewegungsübungen. Er zeichnet selbst eingegebene
> Trainingsdaten sowie Herzfrequenz- und Herzratenvariabilitätsmessungen
> handelsüblicher Sensoren auf und stellt sie im Zeitverlauf dar.
>
> Die App dient dem allgemeinen Wohlbefinden und der Fitness. Sie ist **nicht**
> dazu bestimmt, Krankheiten zu erkennen, zu verhüten, zu überwachen, zu
> behandeln oder zu lindern. Sie stellt keine Diagnose, gibt keine
> Therapieempfehlung und ersetzt keine ärztliche oder therapeutische Beratung.

### Was daraus folgt — verbindlich für die Entwicklung

**Erlaubt:**
- Übungen anzeigen, dokumentieren, Verlauf darstellen
- Herzfrequenz und HRV-Kennzahlen **anzeigen** und über die Zeit auftragen
- Timer und Zähler, die der Nutzer selbst gesetzt hat
- Rohdaten der HRV-Messung sichtbar machen

**Nicht erlaubt in Edition A:**
- Aus Puls oder HRV eine **Handlungsanweisung** ableiten
  („Pause machen", „Belastung reduzieren", „heute nicht trainieren")
- Messwerte als „normal", „auffällig", „zu hoch" o. Ä. **bewerten**
- Erkennung oder Hinweis auf Herzrhythmusstörungen, Erschöpfung, Übertraining
- Grenzwerte als Empfehlung darstellen

Der Unterschied liegt an einer feinen, aber entscheidenden Stelle:

| erlaubt | nicht erlaubt |
|---|---|
| „Puls 132" | „Puls zu hoch — Pause machen" |
| „RMSSD 28 ms" | „Deine Erholung ist unzureichend" |
| „Timer abgelaufen" | „Weiter, dein Puls hat sich erholt" |

**Tagesfelder** (Ben, 21.10.2026, `docs/plan_tagesfelder.md`): Die Person hält je Tag
selbst Werte fest — frei benannt, etwa Schmerz auf einer Skala, Einnahmen eines
Medikaments, Trinkmenge, Texte zur Ernährung. Das ist Dokumentation wie die Notizen
(„Dokumentieren“ oben ist erlaubt). Für die Entwicklung gilt:

| erlaubt | nicht erlaubt |
|---|---|
| „Ibu 400 × 2 heute“, „400 · 9 Stück in 4 Wochen“ | „Höchstdosis erreicht“, „zu viel Ibuprofen“ |
| „Schmerz Knie 3“, Linie über die Zeit | „Schmerz steigt — Arzt aufsuchen“, Trendpfeil als Urteil |
| Vorschläge zum Anlegen („Schmerz“, „Medikament“) | Erinnerung an Einnahmen, Grenzlinien, Ampelfarben |

Die Vorschläge „Schmerz“ und „Medikament“ heißen so, weil die Person ihre Felder selbst
benennt und wählt; die App wertet keinen Wert aus. **Offen** (Katalog P68): ob diese
Vorschläge in der Solo-Edition so bleiben dürfen oder neutral heißen sollen — vor einer
Veröffentlichung im Store mit der Beschreibung dort abgleichen.

### Pflichthinweise in der App

Beim ersten Start und in den Informationen:

> Diese App ist kein Medizinprodukt. Sie unterstützt beim Training und beim
> Dokumentieren, stellt aber keine Diagnose und gibt keine Therapieempfehlung.
> Bei Beschwerden, Schmerzen oder Unsicherheit wende dich an ärztliches oder
> therapeutisches Fachpersonal. Brich das Training bei Schmerzen, Schwindel,
> Atemnot oder Brustenge sofort ab.

---

## Edition B („praxis") — hier wird es ernst

Edition B ist als **Brücke zum Training mit Patienten** gedacht: Der Therapeut
stellt Übungen zusammen, sieht die Entwicklung ein und justiert nach. Das ist
eine therapeutische Verwendung, und damit ändert sich die Bewertung.

### Kriterien, ab denen Edition B in die MDR rutscht

Zu prüfen ist jede einzelne Funktion. Kritisch sind insbesondere:

1. **Automatische Steuerung nach physiologischen Werten** — die Regeln
   `hr_above` und `rest_until_hr_below` steuern das Training anhand des Pulses.
   Eingebettet in einen Behandlungskontext ist das eine medizinische Aussage.
2. **Bewertung von Messwerten** — jede Einordnung als auffällig oder unauffällig.
3. **Therapieanpassung auf Grundlage der App-Daten** — wenn der Therapeut
   Entscheidungen auf die App stützt, wird sie Teil der Behandlung.
4. **Screening-artige Auswertungen** — z. B. Hinweise auf Rhythmusstörungen aus
   den RR-Intervallen.

Zur Einordnung: Eine App, die reine Fitnessdaten aufzeichnet, ist in der Regel
kein Medizinprodukt. Dieselbe App **mit einer Funktion zur Erkennung von
Herzrhythmusstörungen** ist eines.

### Offene Entscheidung — vor dem Bau von Edition B zu klären

Es gibt drei gangbare Wege. Die Wahl bestimmt Aufwand und Zeitplan erheblich:

| Weg | Bedeutung |
|---|---|
| **A — Dokumentationswerkzeug** | Edition B bleibt reines Kommunikations- und Dokumentationsmittel. Der Therapeut entscheidet, die App bewertet nichts. Vermutlich kein Medizinprodukt. **Geringster Aufwand.** |
| **B — Klasse I** | Die App unterstützt die Behandlung, ohne zu diagnostizieren. Selbsterklärung, technische Dokumentation, QM-System nötig. |
| **C — Klasse IIa** | Sobald Entscheidungen zu Diagnose oder Therapie unterstützt werden. Benannte Stelle, klinische Bewertung, laufende Überwachung. **Erheblicher Aufwand.** |

Empfehlung für den Start: **Weg A**, konsequent durchgehalten. Die App liefert
Daten und Kommunikation, jede Bewertung bleibt beim Therapeuten. Sollte später
mehr gewünscht sein, ist der Schritt bewusst zu gehen — nicht versehentlich.

Orientierungshilfe für die Einstufung bietet das BfArM.

---

## Checkliste vor jeder neuen Funktion

- [ ] Trifft die Funktion eine Aussage über den Gesundheitszustand?
- [ ] Leitet sie aus Messwerten eine Handlung ab?
- [ ] Würde ein Nutzer sie als medizinischen Rat verstehen?
- [ ] Passt die Beschreibung noch zur Zweckbestimmung oben?
- [ ] Sind Werbung, Beschreibung im Store und Hilfetexte damit vereinbar?

Ein „ja" bei einer der ersten drei Fragen heißt: Edition B, und die Einstufung
ist neu zu prüfen.
