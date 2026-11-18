#!/usr/bin/env bash
# shellcheck disable=SC1111  # „…“ in Meldungen ist gewollt
# Eigener Worktree für große Änderungen (CLAUDE.md, „Große Änderungen im eigenen Worktree“):
# trainingsapp auf einem neuen Zweig ab `main`, hrv-core und hrv-watch daneben auf dem Stand der
# `.ref`-Dateien — so findet `uv` sie als `../hrv-core` und `../hrv-watch`, und ein Testlauf liest
# nie die halbfertige Arbeit einer anderen Sitzung in den lebenden Ordnern mit.
#
#   scripts/worktree.sh anlegen <zweig>     # → ../wt/<zweig>/{trainingsapp,hrv-core,hrv-watch}
#   scripts/worktree.sh entfernen <zweig>   # nur saubere Worktrees; der Zweig nur, wenn gemergt
#
# Alle Pfade absolut: `git -C <repo> worktree add wt/x` legte den Worktree sonst relativ zum Repo
# an, mitten in dessen Arbeitsbaum (18.11.2026).
set -euo pipefail

haupt="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
eltern="$(dirname "$haupt")"
befehl="${1:-}"
zweig="${2:-}"
if [[ -z "$befehl" || -z "$zweig" ]]; then
    grep '^#   scripts/worktree.sh' "${BASH_SOURCE[0]}" | sed 's/^#  //'
    exit 2
fi
if ! git check-ref-format --branch "$zweig" >/dev/null 2>&1; then
    echo "„$zweig“ taugt nicht als Zweigname" >&2
    exit 2
fi
ziel="$eltern/wt/$zweig"

case "$befehl" in
anlegen)
    if [[ -e "$ziel" ]]; then
        echo "$ziel gibt es schon" >&2
        exit 1
    fi
    git -C "$haupt" worktree add -b "$zweig" "$ziel/trainingsapp" main
    git -C "$eltern/hrv-core" worktree add --detach "$ziel/hrv-core" "$(cat "$haupt/hrv-core.ref")"
    git -C "$eltern/hrv-watch" worktree add --detach "$ziel/hrv-watch" "$(cat "$haupt/hrv-watch.ref")"
    (cd "$ziel/trainingsapp" && env -u VIRTUAL_ENV uv sync --all-extras --quiet)
    echo "Fertig: $ziel/trainingsapp (Zweig $zweig ab $(git -C "$haupt" rev-parse --short main))"
    ;;
entfernen)
    # ohne --force: Ungesichertes bleibt stehen, git sagt, was
    git -C "$haupt" worktree remove "$ziel/trainingsapp"
    git -C "$eltern/hrv-core" worktree remove "$ziel/hrv-core"
    git -C "$eltern/hrv-watch" worktree remove "$ziel/hrv-watch"
    rmdir "$ziel" 2>/dev/null || true
    rmdir "$eltern/wt" 2>/dev/null || true
    # -d, nicht -D: ein Zweig, der nicht in main steckt, bleibt
    git -C "$haupt" branch -d "$zweig" || echo "Zweig $zweig bleibt (nicht in main)"
    ;;
*)
    echo "anlegen oder entfernen, nicht „$befehl“" >&2
    exit 2
    ;;
esac
