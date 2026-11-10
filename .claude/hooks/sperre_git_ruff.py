#!/usr/bin/env python3
"""PreToolUse-Hook für Bash: sperrt Befehle, die im gemeinsamen Arbeitsbaum fremde Arbeit treffen.

Ben, 10.11.2026 (CLAUDE.md „Parallele Arbeit im selben Baum“): Mehrere Sitzungen arbeiten im
selben Ordner. Gesperrt sind darum

- ``git stash`` (außer ``list``/``show``) — räumt die halbfertige Arbeit der anderen mit weg;
- ``git add -A``/``--all``/``-u``/``.``/``*`` und ``git add <Ordner>``, ``git commit -a`` —
  nehmen fremde Dateien in den Commit;
- ``ruff format`` ohne ``--check``/``--diff`` auf einen Ordner oder ohne Pfad — formatiert
  fremde Dateien um.

Claude Code gibt den Aufruf als JSON auf stdin (``tool_input.command``, ``cwd``); Exit 2 sperrt
den Befehl, der Text auf stderr geht als Begründung an Claude zurück. Nur stdlib.

Nicht dicht: Variablen (``$X``), ``eval``, Skripte und Aliase sieht der Hook nicht — er fängt
Versehen ab, keine Absicht.
"""

from __future__ import annotations

import json
import os
import shlex
import sys

TRENNER = set(";|&()<>\n")
HUELLEN = {"sh", "bash", "zsh", "dash"}
VORSPANN = {"uv", "uvx", "env", "time", "command", "nice", "exec", "sudo", "xargs", "nohup"}
GIT_MIT_WERT = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
RUFF_MIT_WERT = {
    "--config",
    "--line-length",
    "--target-version",
    "--exclude",
    "--extend-exclude",
    "--stdin-filename",
    "--range",
    "--cache-dir",
    "--extension",
}
COMMIT_MIT_WERT = {"-m", "-F", "-C", "-c", "-t", "--message", "--file", "--author", "--date"}
COMMIT_KURZ_MIT_WERT = set("mFCct")


def _teile(befehl: str) -> list[list[str]]:
    """Den Befehl in Teilbefehle zerlegen (an ``;``, ``|``, ``&``, Klammern, Zeilenenden)."""
    lex = shlex.shlex(befehl, posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    teile: list[list[str]] = [[]]
    for wort in lex:
        if wort and set(wort) <= TRENNER:
            teile.append([])
        else:
            teile[-1].append(wort)
    return [t for t in teile if t]


def _name(wort: str) -> str:
    return os.path.basename(wort)


def _ist_ordner(pfad: str, cwd: str) -> bool:
    if pfad in (".", "..", "*") or pfad.endswith("/"):
        return True
    return os.path.isdir(os.path.join(cwd, os.path.expanduser(pfad)))


def _git(rest: list[str], cwd: str) -> str | None:
    i = 0
    while i < len(rest) and rest[i].startswith("-"):
        if rest[i] == "-C" and i + 1 < len(rest):
            cwd = os.path.join(cwd, os.path.expanduser(rest[i + 1]))
        i += 2 if rest[i] in GIT_MIT_WERT else 1
    if i >= len(rest):
        return None
    unter, args = rest[i], rest[i + 1 :]
    if unter == "stash":
        if args and args[0] in ("list", "show"):
            return None
        return (
            "git stash räumt die halbfertige Arbeit anderer Sitzungen mit weg. "
            "Stattdessen: git show HEAD:<datei> oder git worktree."
        )
    if unter == "add":
        nur_pfade = False
        for a in args:
            if a == "--":
                nur_pfade = True
            elif not nur_pfade and a.startswith("-"):
                if a in ("--all", "--update", "--no-ignore-removal") or (
                    not a.startswith("--") and set(a[1:]) & set("Au")
                ):
                    return f"git add {a} nimmt fremde Dateien mit. Die eigenen einzeln nennen."
            elif _ist_ordner(a, cwd):
                return (
                    f"git add auf den Ordner „{a}“ nimmt fremde Dateien mit. "
                    "Die eigenen Dateien einzeln nennen."
                )
        return None
    if unter == "commit":
        j = 0
        while j < len(args):
            a = args[j]
            if a == "--":
                break
            if a == "--all":
                return "git commit --all nimmt fremde Änderungen mit. Erst git add <dateien>."
            if a in COMMIT_MIT_WERT:
                j += 2
                continue
            if a.startswith("-") and not a.startswith("--"):
                for k, z in enumerate(a[1:], start=1):
                    if z == "a":
                        return "git commit -a nimmt fremde Änderungen mit. Erst git add <dateien>."
                    if z in COMMIT_KURZ_MIT_WERT:
                        if k == len(a) - 1:
                            j += 1  # der Wert steht im nächsten Wort
                        break
            j += 1
    return None


def _ruff(rest: list[str], cwd: str) -> str | None:
    if not rest or rest[0] != "format":
        return None
    pfade: list[str] = []
    i = 1
    while i < len(rest):
        a = rest[i]
        if a in ("--check", "--diff", "--help", "-h"):
            return None
        if a in RUFF_MIT_WERT:
            i += 2
            continue
        if a == "-" or not a.startswith("-"):
            pfade.append(a)
        i += 1
    if not pfade:
        return "ruff format ohne Pfad formatiert den ganzen Ordner. Die eigenen Dateien nennen."
    for p in pfade:
        if p != "-" and _ist_ordner(p, cwd):
            return (
                f"ruff format auf den Ordner „{p}“ formatiert fremde Dateien um. "
                "Die eigenen Dateien nennen (ruff format --check . zum Prüfen bleibt frei)."
            )
    return None


def grund(befehl: str, cwd: str = ".", tiefe: int = 0) -> str | None:
    """Warum der Befehl gesperrt ist — ``None``, wenn er laufen darf.

    >>> grund("git stash")[:9]
    'git stash'
    >>> grund("git stash list") is None
    True
    >>> grund("git commit -m 'git add -A ist gesperrt'") is None
    True
    """
    try:
        teile = _teile(befehl)
    except ValueError:  # offene Anführungszeichen — die Shell wird es selbst ablehnen
        return None
    for worte in teile:
        while worte and "=" in worte[0] and not worte[0].startswith("-"):
            worte = worte[1:]  # VAR=wert davor
        if not worte:
            continue
        kopf = _name(worte[0])
        if kopf == "cd" and len(worte) > 1:
            cwd = os.path.join(cwd, os.path.expanduser(worte[1]))
            continue
        if kopf in HUELLEN and "-c" in worte and tiefe < 3:
            stelle = worte.index("-c")
            if stelle + 1 < len(worte) and (g := grund(worte[stelle + 1], cwd, tiefe + 1)):
                return g
            continue
        if kopf not in ("git", "ruff") and kopf not in VORSPANN and not kopf.startswith("python"):
            continue
        for i, wort in enumerate(worte):
            if _name(wort) == "git":
                g = _git(worte[i + 1 :], cwd)
            elif _name(wort) == "ruff":
                g = _ruff(worte[i + 1 :], cwd)
            else:
                continue
            if g:
                return g
            break
    return None


def main() -> int:
    try:
        eingabe = json.load(sys.stdin)
    except ValueError:
        return 0
    if eingabe.get("tool_name", "Bash") != "Bash":
        return 0
    befehl = (eingabe.get("tool_input") or {}).get("command") or ""
    g = grund(befehl, eingabe.get("cwd") or os.getcwd())
    if g:
        print(f"Gesperrt (CLAUDE.md, parallele Arbeit im selben Baum): {g}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
