# Dependabot — was es tut und wie es hier eingestellt ist

Dependabot ist ein Dienst von GitHub, der die Abhängigkeiten eines Repos im
Blick behält. Seit dem 16.10.2026 läuft er auf `trainingsapp` und `hrv-core`.
Er tut drei getrennte Dinge, die man leicht verwechselt:

| Funktion | Was passiert | Wo eingestellt |
|---|---|---|
| **Alerts** | GitHub vergleicht `uv.lock` mit seiner Datenbank bekannter Sicherheitslücken und meldet Treffer unter „Security → Dependabot“. Kein Code wird geändert. | Repo-Einstellung (an) |
| **Sicherheitsupdates** | Für eine gemeldete Lücke öffnet Dependabot von sich aus einen PR, der das betroffene Paket im Lock auf die erste reparierte Version hebt. | Repo-Einstellung (an) |
| **Versionsupdates** | Unabhängig von Lücken: einmal pro Woche ein PR, der veraltete Abhängigkeiten auf den neuesten Stand hebt. | `.github/dependabot.yml` |

Die ersten beiden sind reine Schalter in den Repo-Einstellungen. Das dritte
steuert die Datei im Repo — und nur das dritte erzeugt regelmäßig Arbeit.

## Was ein Dependabot-PR ist

Ein PR von Dependabot ist ein ganz normaler Pull Request, nur dass ihn ein Bot
geschrieben hat. Er ändert genau eine Sache (eine Paketversion in `uv.lock`
oder eine Versionsnummer in einem Workflow), die CI läuft darauf wie auf jedem
anderen PR, und man entscheidet mit dem Merge-Knopf.

Man **muss** keinen annehmen. Nicht gemergte PRs bleiben offen, bis Dependabot
sie beim nächsten Lauf durch neuere ersetzt. Zwei Hinweise helfen beim
Entscheiden:

- **Checks grün?** Die CI prüft Linter, Formatierung, Tests und Doctests ohne
  flet. Rot heißt nicht automatisch „der PR ist schuld“ — am 16.10. waren zwei
  PRs rot, weil ein zeitabhängiger Test unter der Last von vier gleichzeitigen
  Läufen kippte (seitdem lastfest). Im Protokoll steht, welcher Test fiel.
- **Hauptversion gesprungen** (z. B. `actions/checkout` 4 → 7)? Bei den
  GitHub-Actions heißt das fast immer „neue Node-Laufzeit“; auf GitHub-eigenen
  Runnern läuft das ohne Änderung. Bei Python-Paketen lohnt ein Blick in die
  Release-Notizen, die Dependabot in den PR-Text kopiert.

Dependabot pflegt seine PRs selbst: Ändert sich `main`, rebased er sie;
überholt eine neue Version den PR, schließt er ihn und öffnet einen neuen.
Im PR lassen sich Befehle als Kommentar geben, etwa `@dependabot rebase`,
`@dependabot recreate` oder `@dependabot ignore this major version`.

## Wie es hier eingestellt ist

`.github/dependabot.yml` in der trainingsapp:

```yaml
version: 2
updates:
  - package-ecosystem: "uv"           # Python-Pakete über uv.lock
    directory: "/"
    schedule: { interval: "weekly" }
    groups:
      python: { patterns: ["*"] }     # ein PR für alle Python-Pakete
    ignore:
      - dependency-name: "flet*"      # flet wechselt bewusst, nie automatisch
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "weekly" }
    groups:
      actions: { patterns: ["*"] }    # ein PR für alle Actions
```

Drei Entscheidungen stecken darin:

1. **Gebündelt.** Ohne `groups` kommt je Paket ein eigener PR — am ersten Tag
   waren es gleich fünf für die Actions. Mit Gruppen sind es höchstens zwei
   PRs pro Woche: einer für Python, einer für die Actions. Als die Bündelung
   dazukam, hat Dependabot die vier Einzel-PRs von selbst geschlossen und
   durch einen gemeinsamen ersetzt (PR 10).
2. **flet ausgenommen.** `flet`, `flet-charts`, `flet-video`, `flet-map`,
   `flet-geolocator`, `flet-permission-handler` sind in `pyproject.toml`
   auf `1.0.*` festgelegt, und `flet-mcp` muss im Gleichschritt bleiben.
   Ein Flet-Wechsel ist ein bewusster Schritt mit Desktop- und Android-Test
   (CLAUDE.md, „Flet-API nachschlagen“), kein Wochen-PR.
3. **uv, nicht pip.** Dependabot liest `uv.lock` direkt und hält die Hashes
   darin aktuell; `pyproject.toml` mit seinen Bereichen (`numpy>=2.1`) fasst
   er nur an, wenn ein Bereich die neue Version ausschließt.

hrv-core hat dieselbe Datei ohne den Actions-Teil (dort gibt es keine
Workflows) und ohne flet-Ausnahme.

**Was Dependabot hier nicht sieht:**

- `hrv-core`, `flet-ble`, `flet-ton` — Pfadabhängigkeiten
  (`[tool.uv.sources]`), keine PyPI-Pakete. Sie werden von Hand gepflegt.
- Die Flutter-Seite der Erweiterungen (`erweiterungen/*/src/flutter/*/pubspec.yaml`)
  und was `flet build` an Dart-Paketen zieht. Dafür gäbe es das Ökosystem
  `pub`; bisher nicht eingerichtet, weil diese Stände bewusst mit dem
  Android-Build zusammen gewechselt werden.
- Die Python-Version (`.python-version`) und uv selbst.

## Sicherheitsmeldungen abarbeiten

Eine Meldung nennt Paket, verwundbaren Bereich und die erste reparierte
Version. Der übliche Weg, lokal:

```bash
uv lock --upgrade-package urllib3     # hebt nur dieses Paket im Lock
uv sync --extra desktop
uv run pytest                          # grün? dann committen und pushen
```

Nach dem Push prüft GitHub das Lock erneut; die Meldung schließt sich nach
etwa einer Minute von selbst. Alternativ den Sicherheits-PR von Dependabot
mergen — das ist derselbe Schritt, nur vom Bot ausgeführt.

**Wenn ein anderes Paket die verwundbare Version festhält:** Am 16.10. meldete
hrv-core `setuptools < 83`, gezogen von `neurokit2 0.2.13`, das `setuptools < 82`
verlangt. `uv lock --upgrade-package setuptools` änderte nichts, weil die
Anforderung von neurokit2 gewann. Mit einer Untergrenze zwingt man uv zum
Ausweichen:

```bash
uv lock --upgrade-package 'setuptools>=83'
# → Updated neurokit2 v0.2.13 -> v0.2.12, Removed setuptools
```

uv nahm das ältere neurokit2 ohne setuptools-Pin — zufällig genau der Stand,
gegen den praxis_gui gerechnet hatte. Nicht immer geht es so glatt; dann
bleibt die Wahl zwischen Warten auf das Paket, einem Override in
`[tool.uv]` (`override-dependencies`) oder dem Schließen der Meldung mit
Begründung („betrifft nur die Testgruppe `referenz`, nie die App“).

**Einordnen statt erschrecken.** Viele Meldungen betreffen Code, den die App
nie ausführt: urllib3 und oauthlib am 16.10. kamen über Entwicklungswerkzeuge
ins Lock, nicht in die APK. Gefährlich wird es bei Paketen, die auf dem Handy
laufen (numpy, flet und seine Erweiterungen) oder die Dateien von außen
lesen. Die Spalte „Schwere“ sagt nichts darüber, ob der verwundbare Pfad hier
überhaupt erreichbar ist — das muss man selbst beurteilen.

## Zusammenspiel mit dem Rest

- **Lock ist die Wahrheit.** `uv.lock` legt jede Version und jeden Hash fest;
  Dependabot ändert genau diese Datei. Nach einem Merge lokal `uv sync`, sonst
  läuft die eigene Umgebung mit alten Ständen.
- **APK-Builds** nehmen die Versionen aus `pyproject.toml`, nicht aus
  `uv.lock` (`flet build` installiert selbst). Ein Dependabot-Merge ändert
  die nächste APK darum nur, wenn `pyproject.toml` betroffen ist oder die
  neue Version ohnehin die aktuellste im Bereich ist.
- **Secret-Scanning** ist ein anderer Dienst (sucht nach Tokens in Commits),
  läuft aber unter derselben Überschrift „Code security“. Siehe README,
  „Repo-Einstellungen (Sicherheit)“.
- **Rhythmus:** wöchentlich, montags früh (UTC). Wer das verschieben will,
  setzt `schedule.day` und `schedule.time` in der Datei.
