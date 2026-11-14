# Planung: Verweise zwischen Paketen (14.11.2026)

Bens Fragen vom 14.11.2026: „Wie ist es, wenn Kurse Übungen brauchen von zwei verschiedenen
Paketen. Ist das möglich oder stürzt dann der Kurs ab?“ und „Wäre das jetzt ein Fall, wo für
Übungen die Prio 0,1,2 zum Tragen käme? … Wenn man das Paket mit dem Kurs/Planübung
exportiert, wird die Grundübung mitgenommen mit einem Verweis, dass sie von Standard ist?“ —
Anlass: Kurse, die die App erklären, sollen in ein eigenes Paket und brauchen Übungen aus
„Standard“.

**Stand: nichts hiervon ist gebaut.** Dieses Papier hält fest, was heute gilt, schlägt einen
Grundsatz und Stufen vor und sammelt die Fragen, die Ben entscheidet.

---

## 1. Was heute gilt

Geprüft am 14.11.2026 an einer Wegwerf-Datenbank (Paket mit einem Kurs, dessen Kapitelpläne
eine eigene Übung, eine aus „Standard“ und eine fehlende nennen) und am Code.

| Verweis im Kapitelplan | Ergebnis |
|---|---|
| `key` einer Übung **desselben** Pakets | wird zur ID (`core/pakete._vorlage_lesen`) |
| **ID** einer Übung aus einem anderen, installierten Paket | Plan enthält sie, Kapitel läuft |
| ID einer Übung, deren Paket **fehlt** | Plan entsteht **ohne** sie — ohne Meldung (`data/kurse.kapitel_erreichen`: nur vorhandene Übungen; ein leerer Plan entsteht gar nicht) |
| `key` einer Übung aus einem **anderen** Paket | wird nicht aufgelöst, gilt als unbekannte ID — fällt weg wie oben |
| Das andere Paket wird später entfernt | die Übung fällt aus dem Plan; eine Bedingung „Summe“ auf sie bleibt bei 0 — bei Freischaltung „streng“ kommt man an dem Kapitel nicht vorbei |

Nichts davon stürzt ab; es fehlt die Meldung. `trainingsapp-paket pruefen` sieht keinen
dieser Fälle.

Was es schon gibt:

- **Ergänzungen** nennen ein anderes Paket: `uebung = "kniebeuge"`, wahlweise `paket = "…"`
  (Name oder ID, ohne Angabe „Standard“; `core/pakete.ergaenzung_ziel`). Fehlt die Übung,
  wartet die Ergänzung, bis ihr Paket da ist (`docs/uebungspakete.md`, „Ergänzungen“).
- **Zwei Stufen** (P188): Standard und Erweiterung nebeneinander, die eigene Änderung darüber
  (`docs/uebungspakete.md`, „Zwei Stufen, ein Schalter“).
- **Export eines eigenen Pakets** (`data/eigene_pakete.inhalt`): Eine fremde Übung reist nicht
  mit. Ist sie hier verändert, reist der Unterschied als Ergänzung; ist sie unverändert, nennt
  der Plan nur ihre ID.
- **„Kurs neu laden … Fehlendes zurückholen“** holt in Kapitelpläne zurück, was fehlt
  (`KursRepo.kurs_neu_laden`) — ob es eine Übung nachträgt, deren Paket erst später kam, ist
  für diesen Fall nicht ausprobiert.
- Die gebaute JSON trägt in Plänen **IDs**, keine Schlüssel — der Schlüssel wird beim Lesen
  der TOML aufgelöst.

## 2. Grundsatz (Vorschlag)

**Verweis statt Kopie.** Eine Übung gehört zu genau einem Paket; wer sie braucht, nennt sie.

| Was soll anders sein? | Wohin | Wirkt |
|---|---|---|
| Ziel, Felder, Takt, Text oder Medien **nur in diesem Kurs oder Plan** | an die Planübung (`plaene[].uebungen[]`) | nur dort |
| Die Übung soll **überall** etwas dazubekommen (Abschnitt, Video, andere Parameter) | Erweiterung (`[[ergaenzungen]]`, Stufe 1) | im ganzen Katalog — mit Parametern wird sie zur geltenden Stellung |
| Nichts | bloßer Verweis | — |

Darum **nicht** „immer eine Erweiterung mitschicken“: Sie verstellte die Übung auch außerhalb
des Kurses. Und **keine Kopie der Grundübung**: Als eigene Übung stünde sie doppelt im Katalog,
der Verlauf teilte sich, Updates des Grundpakets erreichten sie nicht; mit der ID des Originals
überginge sie der Import ohnehin (Regel „gehört zu einem anderen Paket“). Baut ein Paket auf
einem **privaten** Paket auf, trüge eine Kopie dessen Inhalt offen hinaus.

## 3. Stufen

| Stufe | Inhalt | Format |
|---|---|---|
| V1 | **`paket = "…"` an jedem Übungsverweis** in Plänen, Kapitelplänen, Bedingungen und Blöcken — aufgelöst wie bei Ergänzungen (`ergaenzung_ziel`). In der TOML steht dann `uebung = "kniebeuge", paket = "Standard"` statt einer UUID | keine neue Formatversion: die gebaute JSON trägt IDs wie heute, ältere Apps merken nichts |
| V2 | **`pruefen` meldet unauflösbare Verweise:** Fehler, wenn ein Verweis weder ID noch Schlüssel des eigenen oder eines genannten Pakets ist; liegt das genannte Paket als Datei daneben (`pakete/`), prüft das Werkzeug auch, ob es den Schlüssel dort gibt — sonst Hinweis „nicht prüfbar“ | — |
| V3 | **Voraussetzung im Paketkopf:** `braucht = [{ paket = "Standard", version = 5 }]` — das Werkzeug trägt die Pakete aus den Verweisen selbst ein, die Mindestversion setzt der Autor. Der Import zeigt in der Rückfrage, was fehlt oder zu alt ist | neues Feld im Kopf — Frage F2 |
| V4 | **Sichtbar in der App:** Kapitel und Plan nennen fehlende Übungen mit dem Paket, aus dem sie kämen, statt sie still wegzulassen; kommt das Paket, holt „Fehlendes zurückholen“ sie nach (oder die App von selbst — Frage F3) | — |
| V5 | **Export eigener Pakete** schreibt `braucht` aus den fremden Übungen und ihrer installierten Version | wie V3 |

Reihenfolge: V1 und V2 zuerst — sie brauchen keine Formatänderung und machen ein
Tutorial-Paket in der TOML erst schreibbar. Dann V4, V3, V5.

## 4. Fragen an Ben

- **F1 — Grundsatz:** Verweis statt Kopie, Abweichungen an der Planübung, Erweiterung nur für
  echte Zusätze (§ 2) — so?
- **F2 — `braucht` und ältere Apps:** Ohne neue Formatversion überlesen ältere Apps das Feld
  und verhalten sich wie heute (fehlende Übungen fallen still weg). Mit Formatversion 6 lehnen
  sie das Paket ab („neuer als diese App“). Vorschlag: nicht heben — das Feld ändert nicht, was
  die Datei bedeutet.
- **F3 — Fehlt eine Voraussetzung beim Import:** ablehnen, oder warnen und einspielen?
  Vorschlag: warnen und einspielen (Ergänzungen warten heute schon); offen ist, ob Kapitelpläne
  sich von selbst vervollständigen, wenn das Paket kommt, oder nur über „Fehlendes
  zurückholen“.
- **F4 — Bedingung auf eine fehlende Übung** bei Freischaltung „streng“: Das Kapitel bleibt
  sonst für immer gesperrt. Ausweg „Trotzdem freischalten“ nur in diesem Fall, oder das
  Werkzeug verbietet Bedingungen auf Übungen anderer Pakete?
- **F5 — Tutorial-Paket:** mitgeliefert wie „Standard“ (zweite Datei in `data/seed/`, auch für
  die Web-Fassung) oder aus der Quelle („Neu in den Quellen“)? Zieht der Kurs „HRV-Messung
  verstehen“ um, braucht er seine heutige ID ausdrücklich in der TOML (`id = "…"`) — sonst
  entsteht eine neue, und der Fortschritt bleibt am alten Kurs hängen (nicht ausprobiert).

## 5. Nicht Teil dieses Plans

Pakete per Link in der Web-Fassung (`docs/plan_web.md`, „Was noch fehlt“); Erweiterungen von
Erweiterungen (P188: bewusst nur zwei Stufen).
