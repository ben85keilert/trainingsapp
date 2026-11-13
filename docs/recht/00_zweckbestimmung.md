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
| Ton „über deinem Zielbereich (150)“ — Bereich selbst gesetzt (Entscheidung C, 7.11.2026) | „Puls zu hoch“, „Grenze“, „Warnung“; der Ablauf hält an oder geht weiter wegen des Pulses |

**Zielbereich-Ton** (Ben, 7.11.2026, Entscheidung **C**): Die Person darf sich in Solo zwei
Pulsgrenzen setzen und bekommt beim Über- bzw. Unterschreiten einen hohen bzw. tiefen Ton —
wie jede Sportuhr. Bedingungen: die Grenzen setzt die Person selbst (ein Vorschlag aus den
Fitness-Zonen ist erlaubt, nie eine „sichere“ Grenze aus Alter oder Messdaten); der Ton ist
Information, keine Steuerung (kein Pausieren, kein „weiter, wenn im Bereich“, kein Eintrag);
Fitness-Sprache („Zielbereich“, „Intensität“, „darüber/darunter“ — nie „Grenze“, „Warnung“,
„Schonung“, „Herz“); im Patientenmodus aus. Damit teilt sich `core/limits.py` künftig in
**Zielbereich-Ton** (Solo erlaubt) und **Steuerung** (`rest_until_hr_below`, Bedingungen aus der
Herzfrequenz — gesperrt, `physiologische_steuerung`). HF-Zonen als **Workout-Bedingung**
(„x Minuten in Zone y“) bleiben Steuerung und damit gesperrt (Variante B abgelehnt).
**Gebaut (7.11.2026, 0.3.61):** Einstellungen → Herzfrequenz „Ton außerhalb des Zielbereichs“
mit oberer und unterer Grenze und zwei Klängen (`HfEinstellungen.ziel_unten_bpm`,
`alarm_klang_tief`), gespielt im Fokus (`components/fokus.py`) und in der Live-Sicht; die
HF-Kachel des Fokus zeigt Zone, Anteil der Reserve und Zeit in der Zone — nur Anzeige.

**Vorschlag nach der Belastung** (Ben, 12.11.2026, `core/anpassung.py`, `docs/plan_kurse.md`
§8): Ein Plan aus einem Kurs oder Paket kann nach dem Workout ein anderes **Zeitziel**
vorschlagen — nach der Anstrengung, die die Person selbst einträgt (Skala 0–10), und nach
einer Regel, die die Autorin des Plans geschrieben hat. Bens Setzung: „Für Änderungen an den
Plänen gilt grundsätzlich, dass die Änderung geklickt werden muss.“ Bedingungen: Grundlage
ist nur die **Selbstauskunft**, nie Puls oder HRV; die App nennt die Regel und deutet die Zahl
nicht („zu schwer“, „überlastet“ kommen nicht vor); geändert wird nur auf Tipp; die
Vorschläge lassen sich abschalten. **Offen** (nicht geprüft, vor einem Patientenmodus zu
klären): Im Patientenmodus darf die App „nicht deuten, warnen oder steuern — auch nicht
lokal“ (Entscheidung 7.11.2026, unten); ob ein Vorschlag nach der Regel der Therapeutin
darunter fällt, ist nicht entschieden — bis dahin gehört er dort ausgeschaltet. Empfehlungen
für **Pulsbereiche aus Messdaten** bleiben, was oben steht: nicht erlaubt in Edition A (ein
Vorschlag aus den Fitness-Zonen ja, nie eine Grenze aus Alter oder Messwerten).

**Tagesfelder** (Ben, 21.10.2026, `docs/plan_tagesfelder.md`): Die Person hält je Tag
selbst Werte fest — frei benannt, etwa Schmerz auf einer Skala, Einnahmen eines
Medikaments, Trinkmenge, Texte zur Ernährung. Das ist Dokumentation wie die Notizen
(„Dokumentieren“ oben ist erlaubt). Für die Entwicklung gilt:

| erlaubt | nicht erlaubt |
|---|---|
| „Ibu 400 × 2 heute“, „400 · 9 Stück in 4 Wochen“ | „Höchstdosis erreicht“, „zu viel Ibuprofen“ |
| „Schmerz Knie 3“, Linie über die Zeit | „Schmerz steigt — Arzt aufsuchen“, Trendpfeil als Urteil |
| Vorschläge zum Anlegen („Schmerz“, „Medikament“) | Erinnerung an Einnahmen, Grenzlinien, Ampelfarben |
| „Blutdruck 128/82 mmHg“, Linie je Teil über die Zeit, Mittel des Tages (Messwert, 28.10.2026) | „Blutdruck erhöht“, Zielbereich, Einordnung nach Leitlinie, Erinnerung ans Messen |

Die Vorschläge „Schmerz“ und „Medikament“ heißen so, weil die Person ihre Felder selbst
benennt und wählt; die App wertet keinen Wert aus. Die „von/bis“-Grenzen eines Messworts
(Blutdruck 30–300 mmHg) fangen Tippfehler ab — sie sind keine Grenzwerte und werden nie
als solche benannt oder gefärbt. **Offen** (Katalog P68): ob diese
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
3. **Therapieanpassung als Zweck der App** — wenn die App dafür gebaut und beworben
   wird, dem Therapeuten die Entscheidungsgrundlage zu liefern (Überwachungsfunktion,
   Rückkanal physiologischer Werte „um den Verlauf zu verfolgen“). *Nicht* gemeint
   (präzisiert 7.11.2026): dass eine Therapeutin beurteilt, was die Patientin ihr aus einer
   App zeigt oder schickt — das ist Heilkunde, kein Softwaremerkmal; eine Pulsuhr wird nicht
   zum Medizinprodukt, weil ein Arzt ihren Ausdruck liest (MDCG 2019-11: Speichern,
   Übertragen, Anzeigen ohne Verarbeitung ist keine Medizinprodukte-Software).
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

### Entscheidung 7.11.2026: Weg A (Ben)

Ben: „Weg A nehmen“ — die App als **Hausaufgabenbetreuung** für Patient:innen bleibt
Dokumentations- und Kommunikationswerkzeug. Was die Diskussion ergab, verbindlich:

**Faustregel in drei Sätzen.** (1) *Die App* darf erheben, speichern, zeigen, exportieren und
**Selbstauskünfte und Leistungen** (Einträge, Skalen, Notizen, Fotos) an die Praxis
übertragen. (2) *Die App* darf nicht deuten, warnen oder steuern — im Patientenmodus auch
nicht lokal. (3) *Die Therapeutin* darf alles beurteilen, was die Patientin ihr gibt — im
Gespräch, als Export, über den Rückkanel für Selbstauskünfte — und den Plan danach anpassen.
Physiologische Messwerte kommen über den Weg „die Patientin gibt sie“, nie über eine
eingebaute Überwachungsfunktion.

**Die Grenze des Patientenmodus** (ein Profil, dessen Pläne von der Praxis kommen):

| Funktion | Solo (Fitness) | Patientenmodus (Weg A) | Fließt zur Praxis |
|---|---|---|---|
| Pläne, Kurse, Workouts; Bedingungen Zeit · Wiederholungen · X-in-Y · Freischaltung | ja | ja | **ja** — Einträge, Häkchen, Skalen, Notizen, Fotos (der Übungszettel mit Rückkanal) |
| HF/HRV live und als Kurve, Rohwerte (HF, RR, RMSSD) | ja | ja — Zahlen und Kurven | nein (nur, wenn die Person selbst exportiert und schickt) |
| HF-Zonen anzeigen (HRR %, Zeit in Zone) | ja | ja, als Anzeige | nein |
| Zielbereich-Ton (selbst gesetzt, Entscheidung C) | ja | **nein** | — |
| HF-Zone als Alarm der App oder Workout-Bedingung | nein (Steuerung) | nein | — |
| HRV-Auswertung mit Schwellen und Hinweisen (DFA-α1-Schwellen, Atemlage-Hinweis, HF-Auswertung) | ja, als Fitness-Information formuliert, keine Gesundheitsurteile | **nein** — ausblenden, nur Rohwerte (`config.ist_aktiv("hrv_bewertung")`) | nein |
| Diagnosemodus, Mitschnitt, Export der Messdatei | ja | ja | nur als bewusste Handlung der Person, nicht über die Anbindung |
| „Praxis sieht den Verlauf der Patientin“ als Funktion | — | **nein** | — |

**Die zweite App (Praxisanbindung)** darf Daten übertragen, auch physiologische, unter drei
Bedingungen (MDCG 2019-11: Übertragen ohne Verarbeitung ist keine Medizinprodukte-Software):
(a) **die Person wählt und sendet** — je Sendung sichtbar bestätigt, keine Abos, keine
Hintergrund-Übertragung, keine Anforderung durch die Praxis; (b) **die App deutet nichts** —
Kurven zeichnen und zusammenfassen ja, Schwellen, Ampeln, bewertete Trends nein, auch nicht
auf der Empfängerseite; (c) **was bei der Praxis damit geschieht:** Wer übermittelte
Messdateien dort mit eigener Software durchrechnet (HRV-Kennzahlen) und das in die
Behandlung einfließen lässt, hat Medizinprodukte-Software auf der Praxisseite (Regel 11,
IIa) — für `praxis_gui` kommt dann nur die **Eigenherstellung nach Art. 5 Abs. 5 MDR**
in Frage (nur in der eigenen Praxis, QMS, Begründung, Dokumentation, öffentliche Erklärung)
oder der Verzicht auf die Analyse übermittelter Dateien. Ein Einnahme-**Protokoll**
(„habe genommen“) ist Tagebuch; Erinnerung, Dosierung, Wechselwirkung wären Medizinprodukt.
Empfangenes wird Teil der Patientenakte (§ 630f BGB; Art. 9 DSGVO, Ende-zu-Ende, AVV).
Details: `docs/plan_praxisanbindung.md`.

**Nicht gemeint ist**, dass die Patientin in der Solo-App nicht frei arbeiten dürfte: In Solo
gilt die Wellness-Ausnahme, die Person darf alles sehen. Die Grenze ist, was die App
**behauptet und urteilt** — und im therapeutischen Kontext auch, was sie lokal deutet.

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
