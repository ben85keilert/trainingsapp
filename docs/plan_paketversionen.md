# Planung: Paketversionen und Updates (17.10.2026)

Bens Notiz vom 17.10.2026: Pakete bekommen Versionen `X.Y.Z`. Ändert sich X, fragt die App
nach und prüft auf Konflikte; Änderungen an Y kommen automatisch; Z sind einfache Änderungen
(andere Kacheln — gemeint sind die Chips —, andere Timer) — „hier kommen nur Änderungen für
Neuinstallationen oder manuelle Updates“. Ausgearbeitet am selben Tag, Entscheidungen in
Abschnitt 8.

Stand 17.10.2026: **geplant; gebaut ist nur Phase 1** (K6, Abschnitt 7). Heute ist
`paket.version` eine ganze Zahl, und jeder Sprung spielt alles ein, je Feld abgeglichen
(`core/pakete.zusammenfuehren`). Im Katalog: A16, offene Punkte P31–P35.

---

## 1. Begriffe

| Begriff | Bedeutung |
|---|---|
| **Version** `major.minor.patch` | Was ein Update auf einem Gerät darf, auf dem das Paket schon ist. Die höchste geänderte Stelle zählt |
| **major** | Etwas fällt weg (Übung, Kurs, Kapitel), oder ein Kurs ändert seinen Ablauf → **Nachfrage** |
| **minor** | Etwas kommt dazu oder wird berichtigt (Texte, Links, Felder der Eingabe) → **automatisch**, danach ein **Hinweis** |
| **patch** | Nur Vorgaben (Chips, Timer, Symbol …) → still; vorhandene Übungen bleiben, wie sie sind |
| **Chips** | Schnellwerte je Feld der Eingabe (`+10` `+15` `+20`), im Plan als Knöpfe; in der Paketdatei `quick` je Feld von `result_spec` (`docs/notation.md`, „Das Plus im Plan“) |
| **Nachfrage** | *Vorher:* Die App wartet auf eine Entscheidung; ohne Antwort ändert sich nichts |
| **Hinweis** | *Nachher:* Die App hat es getan und sagt es; wegtippen genügt |
| **Paketstand** | Je Übung und Kurs, was das Paket festlegt (`package_standard_json`, Migration 015) — die Basis jedes Vergleichs |
| **Feldkonflikt** | Person und Paket haben dasselbe Feld geändert |
| **Strukturkonflikt** | Was wegfällt, wird noch benutzt: Übung in Plänen, mit Einträgen, geändert oder Original einer Variante; Kapitel erreicht oder abgeschlossen |

## 2. Welche Änderung welche Stelle braucht

Übungen — die Felder des Paketstands (`core/pakete.FELDNAMEN`):

| Änderung | Stelle |
|---|---|
| Übung fällt weg; `key` ändert sich (= wegfallen und dazukommen) | major |
| Übung kommt dazu | minor |
| Name, Beschreibung | minor |
| Videos und Links (`media`) | minor |
| Eingabe bekommt andere Felder (`result_spec`: Wiederholungen → Haltezeit) | minor — die Einträge behalten ihre Eingabe von damals (`spec_snapshot_json`) |
| Chips und die übrigen Vorgaben der Eingabe (Startwerte, Grenzen) | patch |
| Ziel (`default_target`), Planparameter (`default_felder`), Timer und Limits (`limit_spec`) | patch |
| Symbol (`icon_key`), Typen, Regionen | patch |
| Variante (`variante_von`, teilt die Kachel im Verlauf) | patch |

Kurse — ein Update ersetzt heute den ganzen Kurs (`kurs_stand`); bearbeiten kann man Kurse
noch nicht:

| Änderung | Stelle |
|---|---|
| Kurs fällt weg; Kapitel fällt weg, wird dazwischengeschoben oder wandert | major — der Fortschritt hängt am Kapitel, und das erste nicht abgeschlossene ist „aktuell“ (`core/kurse.status`): Ein eingeschobenes Kapitel setzt zurück |
| Bedingung oder Freischaltung ändert sich | major — ändert, was die Person tun muss oder darf |
| Kurs kommt dazu; Kapitel kommt ans Ende | minor |
| Name, Beschreibung; Titel, Text und Medien der Kapitel | minor |
| Plan-Vorlagen | patch — Pläne, die ein Kapitel schon angelegt hat, sind gewöhnliche Pläne und bleiben |

Der Paketkopf (Name, Beschreibung, Neuigkeiten) geht mit jeder Stufe mit. Den Namen nur mit
fester `paket.id` ändern — sonst ist es ein neues Paket (A1).

## 3. Was auf dem Gerät passiert

Paket im Modus „automatisch“ (Vorgabe):

| Stufe | Auf dem Gerät |
|---|---|
| major | **Nicht automatisch.** Nachfrage mit Vorschau wie beim Datei-Import: was dazukommt, was wegfällt und wo es noch benutzt wird (Abschnitt 4). Bis zur Antwort bleibt der alte Stand — auch der minor- und patch-Teil dieses Updates. Wegfallende Übungen fragen wie heute einzeln: übernehmen oder löschen |
| minor | **Automatisch** beim Start, danach ein Hinweis („Standard 1.3.0: 2 neue Übungen, Texte korrigiert“). Felder, die die Person geändert hat, bleiben |
| patch | **Still.** Version und Paketstand werden neu, die Übungen bleiben, wie sie sind. Die Paketansicht zeigt je Übung „neu im Paket: Symbol, Timer“; „Auf Paketstand“ holt es |

Immer:

- Was die Person geändert hat, überschreibt kein Update — nur „Auf Paketstand“ (je Feld, je
  Übung oder „Alle auf Paketstand“).
- patch-Felder ändern sich an vorhandenen Übungen nie von selbst, auch nicht in einem minor-
  oder major-Update. **Eigene Chips bleiben** (Ben, 17.10.2026): Wer an einer Übung Chips
  geändert hat, behält sie bis „Auf Paketstand“ — auch wenn das Paket die Felder der Eingabe
  ändert, für jedes Feld, das es weiter gibt (Abschnitt 4). Ebenso eine selbst gewählte
  Variante.
- Modus „manuell“: nichts automatisch, alles wartet auf den Pfeil (wie heute).
- Mehrere Sprünge auf einmal (1.2.0 → 2.1.3): Die höchste Stelle zählt. Eilige Korrekturen
  darum vorher als eigenes minor-Update veröffentlichen.
- Datei-Import von Hand: Vorschau wie heute, also immer eine Nachfrage.
- Neuinstallation: alles aus der Datei; „Wieder installieren“: alles aus dem Paketstand.

## 4. Konflikte

**Feldkonflikt:** Die Fassung der Person bleibt (wie seit dem 16.10.). Neu: ein **Hinweis**
an der Übung („Das Paket hat eine neue Beschreibung — deine ist geblieben“) statt eines stillen
Verlusts.

**Vergleich in der Übung** (Ben, 17.10.2026): In der Übung — nicht in der Planübung — ein
schneller Vergleich je Feld, Paketstand neben eigener Fassung, mit „übernehmen“ je Feld. Heute
gibt es nur „geändert: Beschreibung, Parameter“ (`abweichungen`) und „Auf Paketstand
zurücksetzen“ für die ganze Übung. Die Anzeige trennt zwei Fälle, die heute beide „geändert“
hießen: **von dir geändert** und **neu im Paket** (ein patch-Feld, das ein Update
zurückgehalten hat). Dafür muss die App sich merken, welche Felder zurückgehalten wurden — der
Paketstand allein sagt es nicht (Migration).

**Hierarchie Paket → Übung → Planübung** (Ben, 17.10.2026): Die Übung übernimmt aus dem
Paketstand, die Planübung aus der Übung („Standard der Übung übernehmen“, `core/standards.py`,
gibt es schon). Die Planübung vergleicht nie direkt mit dem Paket.

**Eingabe in zwei Teilen abgleichen:** `result_spec` ist heute *ein* Feld des Paketstands
(„Parameter“). Wer Chips geändert hat, bekäme so keine neuen Felder mehr — und neue Felder des
Pakets (minor) nähmen eigene Chips (patch) mit. Darum gleicht die App die Felder selbst
(Schlüssel und Art: minor) und je Feld die Vorgaben mit Chips (patch) getrennt ab.

**Links zusammenführen:** `media` ist heute *ein* Feld — wer selbst einen Link ergänzt hat,
bekommt keinen neuen Link des Pakets mehr. Künftig je Link (nach `uri`): Neue Links des Pakets
kommen dazu, eigene bleiben, ein Link, den das Paket gestrichen und die Person nicht angefasst
hat, geht. „Videolink kommt hinzu“ ist dann kein Konflikt mehr.

**Strukturkonflikt (major):** Die Nachfrage nennt je wegfallender Übung, wo sie noch steckt —
in Plänen („Teil von Plan …“ gibt es beim Entfernen schon), Zahl der Einträge, geändert,
Original von Varianten — und je Kapitel, ob es erreicht oder abgeschlossen ist.

## 5. Format: Zahl und Name

`paket.version` **bleibt eine ganze Zahl.** Apps, die heute Updates prüfen, überspringen einen
Index-Eintrag mit Text-Version still (`core/paketquelle.index_laden`) und lehnen eine solche
Paketdatei ab (`paket_lesen`: „Die Paketversion muss eine ganze Zahl sein.“) — sie bekämen nie
wieder ein Update.

Darum zwei Angaben, wie bei Android `versionCode` und `versionName`:

| Wo | Angabe |
|---|---|
| TOML (von Hand) | `version = "1.3.0"` — `paket_lesen` nimmt Text und Zahl an |
| JSON und Index (`trainingsapp-paket bauen`, `index`) | `version = 10300` (major·10000 + minor·100 + patch; minor und patch bis 99) und `versionsname = "1.3.0"` |
| App | vergleicht die Zahl, zeigt den Namen; eine Zahl ohne Namen wie heute („Version 2“) |

`FORMAT_VERSION` bleibt 2: Ältere Apps übergehen das neue Feld, spielen jedes Update ein wie
bisher (alles, je Feld abgeglichen) und zeigen „Version 10300“. „Standard“ steht heute auf 2;
1.0.0 = 10000 ist größer.

## 6. Wer die Stufe festlegt

Die **App** bestimmt die Stufe aus dem Unterschied zwischen gespeichertem Paketstand und neuer
Datei (Abschnitt 2), nicht aus der Nummer. Eine falsche Nummer richtet so nichts an — etwa ein
Wegfallen, das als patch ausgegeben wird. Die Nummer ist die Zusammenfassung für Menschen und
die Anzeige unter „Updates“.

Das **Werkzeug** hält die Nummer ehrlich: `trainingsapp-paket pruefen --gegen <Index-URL oder
Datei>` vergleicht mit dem veröffentlichten Stand und lehnt eine zu kleine Stufe ab
(„wandsitz fällt weg → mindestens 2.0.0, steht 1.4.0“), eine Änderung ohne Sprung ebenso.
`veroeffentlichen.sh` im Inhalte-Repo ruft das gegen den Index auf dem Server auf. Das ist
zugleich die Prüfung auf umbenannte oder gestrichene keys, die es bisher nicht gibt.

## 7. Voraussetzungen

- **K6 — der Seed setzt die Version zurück** (17.10.2026 nachgestellt): `seed_einspielen` läuft
  bei jedem Start; `_eintragen` schreibt die Seed-Version über die installierte (`COALESCE`),
  und `_planen` markiert Paketübungen, die im Seed fehlen, als entfallen — auch ohne
  `aktualisieren`. Seit „Standard“ 2 auf der Paketquelle liegt (16.10.), setzt jeder Start auf 1
  zurück, und die Quelle spielt 2 wieder ein. Eine Übung, die nur in der Fassung der Quelle
  steht, gälte bei jedem Start als entfallen. Abhilfe: Ist die installierte Version höher als
  die des Seeds, setzt der Seed still aus. Ohne das hielte die neue Logik jeden Start für eine
  Herabstufung (A1: „Downgrade fragt nach“). **Gebaut 17.10.2026** (nach v0.2.2,
  `seed_einspielen`, Test `test_seed_laesst_neuere_installation_stehen`); auf den Geräten erst
  mit dem nächsten Release (T37).
- **K1 — Links ungeprüft:** `_medium` übernimmt jedes Schema. Bevor minor-Updates Links still
  einspielen, nur `https://` zulassen.

## 8. Entscheidungen (Ben, 17.10.2026)

1. **Texte sind minor:** Korrekturen, etwa nach der Sprachregelung, müssen die Geräte erreichen.
2. **Eine neue Übung ist minor:** automatisch, mit Hinweis — kollidieren kann nichts.
3. **„Kacheln“ meinte die Chips** (Begriffe): patch. Eigene Chips bleiben, außer bei „Auf
   Paketstand“.
4. **Feldkonflikt:** Die eigene Fassung bleibt, dazu ein Hinweis; in der Übung ein Vergleich je
   Feld mit „übernehmen“. Hierarchie Paket → Übung → Planübung.
5. **Andere Felder der Eingabe sind minor:** „nicht so wild und individuell“, manche bekommen
   es gar nicht mit — die Einträge behalten ihre Eingabe von damals.

Noch offen (im Katalog, `docs/offene_fragen.md`, P31–P35):

- Name des Feldes für die Textversion (`versionsname`?).
- Variante (`variante_von`) als patch — vorgeschlagen, nicht eigens entschieden.
- Wo der Hinweis nach einem minor-Update steht: Das Label unter dem Zahnrad sagt heute
  „aktualisiert: Standard“ (`AppState.updates_label`) — reicht das, oder dazu die Seite
  „Updates“ und die Übung?
- Freischaltung eines Kurses ändern: immer major, oder nur, wenn sie strenger wird?
- Kapitel ans Ende eines Kurses, den jemand schon abgeschlossen hat: minor (Vorschlag) — der Kurs
  ist dann wieder offen.

## 9. Phasen

| Phase | Inhalt | Stand |
|---|---|---|
| 0 | Diese Datei; Katalog: Entscheidungen, offene Punkte, Arbeit neben A1 | 17.10.2026 (A16, P31–P35) |
| 1 | K6: Seed setzt bei höherer installierter Version aus | gebaut 17.10.2026, nach v0.2.2 — auf den Geräten mit dem nächsten Release |
| 2 | Format: `version` als Text im TOML, Zahl und `versionsname` in JSON und Index (`paket_lesen`, `paket_bauen`, `paket_werkzeug.index`, `core/paketquelle`) | offen |
| 3 | Stufe aus dem Unterschied (`core/pakete`); Verhalten je Stufe bei Import, Quelle und Seed; Eingabe in zwei Teilen und Links je `uri` abgleichen; zurückgehaltene patch-Felder merken (Migration); K1 | offen |
| 4 | Oberfläche: Nachfrage bei major mit Vorschau und Kontext, Hinweis nach minor, Vergleich je Feld in der Übung, „neu im Paket“ neben „von dir geändert“ | offen |
| 5 | Werkzeug: `pruefen --gegen`; im Inhalte-Repo `veroeffentlichen.sh` und Regel 4 seiner CLAUDE.md | offen |

Tests: `tests/test_pakete.py` (Stufe, Abgleich, Links), `tests/test_paketquelle.py` (Zahl und
Name im Index, Verhalten je Stufe), `tests/test_paket_werkzeug.py` (`--gegen`),
`tests/test_kurse.py` (Kapitel ans Ende, dazwischen), `tests/test_ui_pakete.py`. Wenn gebaut:
der Vertrag in `docs/uebungspakete.md` (Abschnitt „Versionen und Updates“) und eine Zeile unter
„Zentrale Entwurfsentscheidungen“ in `CLAUDE.md`.
