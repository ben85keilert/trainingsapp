# Rechte der betroffenen Personen

## Umsetzung in der App

| Recht | Artikel | Umsetzung |
|---|---|---|
| Auskunft | 15 | Ansicht „Meine Daten": was ist gespeichert, was wurde übertragen, wer hat zugegriffen |
| Berichtigung | 16 | Einträge korrigieren — als **neuer** Eintrag mit `replaces_entry_id`, die Historie bleibt |
| Löschung | 17 | „Konto und Daten löschen", mit Erklärung, was lokal bleibt |
| Einschränkung | 18 | Freigaben einzeln zurücknehmen |
| Datenübertragbarkeit | 20 | Export im `raw-v1`-Format plus JSON der Trainingsdaten — maschinenlesbar und dokumentiert |
| Widerspruch | 21 | entfällt weitgehend, da auf Einwilligung gestützt |
| Widerruf | 7 Abs. 3 | so einfach wie die Erteilung, ein Schritt aus den Einstellungen |

Fristen: unverzüglich, spätestens **einen Monat** nach Eingang (Art. 12 Abs. 3).

## Export — bereits vorbereitet

Der Export ist keine Zusatzfunktion, sondern fällt an: HRV-Messungen liegen
ohnehin als `raw-v1`-JSON vor (`docs/kompatibilitaet.md`). Das Format ist
offengelegt und wird von einer zweiten Anwendung gelesen — damit erfüllt es die
Anforderung „strukturiert, gängig, maschinenlesbar" belastbar.

## Löschung — was wirklich passiert

| Ort | Wirkung |
|---|---|
| Server | Datensätze werden gelöscht, nicht nur markiert |
| `tombstone` | behält **nur** Kennung und Zeitstempel, damit andere Geräte nachziehen |
| Gerät des Patienten | bleibt erhalten, bis dort selbst gelöscht wird |
| Sicherungen | werden im nächsten Turnus überschrieben — Frist benennen |
| Behandlungsdokumentation | § 630f BGB kann der Löschung vorgehen; dann ist das zu begründen |

Der Unterschied zwischen „von meinem Handy verschwunden" und „aus der Praxis
gelöscht" muss in der Oberfläche klar benannt sein. Sonst entsteht ein falsches
Bild — in beide Richtungen.
