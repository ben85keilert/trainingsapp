"""Der Hook `.claude/hooks/sperre_git_ruff.py` (Ben, 10.11.2026).

Mehrere Sitzungen arbeiten im selben Arbeitsbaum; der Hook sperrt, was fremde Arbeit trifft
(`git stash`, `git add -A`, `ruff format` über Ordner). Hier steht, was er sperrt und was nicht.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SKRIPT = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "sperre_git_ruff.py"
_spec = importlib.util.spec_from_file_location("sperre_git_ruff", SKRIPT)
assert _spec is not None and _spec.loader is not None
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


@pytest.fixture
def baum(tmp_path: Path) -> str:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "neben").mkdir()
    return str(tmp_path)


GESPERRT = [
    "git stash",
    "git stash push -m x",
    "git stash pop",
    "git -C ../hrv-core stash",
    "git add -A",
    "git add --all",
    "git add .",
    "git add -u",
    "git add src",
    "git add src/",
    "git add -- src",
    "git commit -a -m x",
    "git commit -am x",
    "git commit --all -m x",
    "ruff format",
    "ruff format .",
    "ruff format src",
    "uv run ruff format src/ tests/",
    "uv run --extra desktop ruff format .",
    "python -m ruff format .",
    "cd src && ruff format .",
    "git status && git add -A && git commit -m x",
    "git status; git stash",
    "git status\ngit add .",
    "sh -c 'git add -A'",
    'bash -c "cd src && git stash"',
    "echo $(git stash)",
    "FOO=1 git add -A",
    "cd neben && git add ..",
]

ERLAUBT = [
    "git status",
    "git stash list",
    "git stash show -p",
    "git add src/a.py",
    "git add -- src/a.py",
    "git add -p src/a.py",
    "git commit -m 'git add -A und git stash sind gesperrt'",
    'git commit -m "x" -m "ruff format ."',
    "git commit -m a",
    "git commit --amend --no-edit",
    "git commit -F nachricht.txt",
    "git log --all --oneline",
    "git diff --stat",
    "ruff format src/a.py",
    "uv run ruff format src/a.py",
    "ruff format --check .",
    "uv run ruff check . && uv run ruff format --check .",
    "ruff format --diff src",
    "ruff check .",
    "echo git stash",
    "grep -rn 'git add -A' docs",
    "uv run pytest -k stash",
    "ls src",
    "git commit -m \"$(cat <<'EOF'\nBetreff: git stash\n\ngit add -A\nEOF\n)\"",
]


@pytest.mark.parametrize("befehl", GESPERRT)
def test_gesperrt(befehl: str, baum: str) -> None:
    assert hook.grund(befehl, baum), befehl


@pytest.mark.parametrize("befehl", ERLAUBT)
def test_erlaubt(befehl: str, baum: str) -> None:
    assert hook.grund(befehl, baum) is None, befehl


def test_als_hook_exit_2_mit_grund(baum: str) -> None:
    """So ruft Claude Code ihn auf: JSON auf stdin, Exit 2 sperrt, stderr nennt den Grund."""

    def lauf(befehl: str) -> subprocess.CompletedProcess[str]:
        eingabe = {"tool_name": "Bash", "tool_input": {"command": befehl}, "cwd": baum}
        return subprocess.run(
            [sys.executable, str(SKRIPT)],
            input=json.dumps(eingabe),
            capture_output=True,
            text=True,
            check=False,
        )

    gesperrt = lauf("git add -A")
    assert gesperrt.returncode == 2 and "einzeln" in gesperrt.stderr
    frei = lauf("git add src/a.py")
    assert frei.returncode == 0 and frei.stderr == ""
    kaputt = subprocess.run(
        [sys.executable, str(SKRIPT)],
        input="kein json",
        capture_output=True,
        text=True,
        check=False,
    )
    assert kaputt.returncode == 0  # ein Fehler des Hooks hält nie die Arbeit auf
