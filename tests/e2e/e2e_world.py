"""Persisted state and filesystem layout of one e2e run: everything lives under one temp work dir."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIMS = REPO_ROOT / "tests" / "shims"
# Imported before anything that needs todoimpl or fake_todo_mcp, so run_flow.py works without PYTHONPATH.
sys.path[:0] = [str(REPO_ROOT / "server"), str(SHIMS)]
SCRATCH = Path.home() / "data" / "claude-scratch" / "e2e" / "todoImplementer"
POINTER = SCRATCH / "current"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
PYTHON = str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable)
REPO_NAME = "e2e-demo"
REPO_SLUG = f"kuhyx/{REPO_NAME}"
CHECK = "ls hello-*.txt"
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "E2E",
    "GIT_AUTHOR_EMAIL": "e2e@example.invalid",
    "GIT_COMMITTER_NAME": "E2E",
    "GIT_COMMITTER_EMAIL": "e2e@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}

# Seed notes: one note with two `## ` sections (2 cards) and one single note (1 card) = 3 items.
NOTES: list[dict[str, Any]] = [
    {
        "repo": REPO_SLUG,
        "sections": [
            ["add hello file", f"Create hello-<item id>.txt.\ndone_check: {CHECK}"],
            ["add hello twin", f"Create hello-<item id>.txt too.\ndone_check: {CHECK}"],
        ],
    },
    {
        "repo": REPO_SLUG,
        "title": "add hello note",
        "body": "Create hello-<item id>.txt.",
        "done_check": CHECK,
    },
]


@dataclass
class State:
    """Everything a later step needs to know about the earlier ones (JSON in the work dir)."""

    work: str
    real_claude: bool = False
    port: int = 0
    mcp_url: str = ""
    handles: dict[str, str] = field(default_factory=dict)  # name -> "unit:<n>" | "pid:<n>"
    note_ids: list[str] = field(default_factory=list)
    cards: dict[str, str] = field(default_factory=dict)  # card id -> title
    peak: int = 0
    shipped: list[str] = field(default_factory=list)

    @property
    def path(self) -> Path:
        """The work dir."""
        return Path(self.work)

    def notes(self) -> list[dict[str, Any]]:
        """Return the seed notes; the real-claude smoke runs the single note only."""
        return NOTES[1:] if self.real_claude else NOTES


def save(state: State) -> None:
    """Write the state next to the run."""
    (state.path / "e2e_state.json").write_text(json.dumps(asdict(state), indent=1), encoding="utf-8")


def load() -> State | None:
    """Return the state of the run in progress, or None before step 1."""
    if not POINTER.exists():
        return None
    work = Path(POINTER.read_text(encoding="utf-8").strip())
    path = work / "e2e_state.json"
    return State(**json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None


def real_git() -> str:
    """Return the real git binary (the bin/git shim wraps it)."""
    return shutil.which("git") or "/usr/bin/git"


def server_env(state: State) -> dict[str, str]:
    """Return the server environment (and so that of every claude, git and check it spawns)."""
    work = state.path
    env = {
        "HOME": str(Path.home() if state.real_claude else work / "home"),
        "PATH": f"{work / 'bin'}:{os.environ['PATH']}",
        "PYTHONPATH": str(REPO_ROOT / "server"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TODOIMPL_HOME": str(work / "root"),
        "TODOIMPL_SRC": str(work / "src"),
        "TODOIMPL_MCP_URL": state.mcp_url,
        "TODOIMPL_MCP_TOKEN_FILE": str(work / "mcp-token"),
        "TODOIMPL_CAPPED": str(work / "bin" / "capped.sh"),
        "REAL_GIT": real_git(),
        "GIT_PUSH_ALLOW_ROOT": str(work),
        **GIT_IDENTITY,
    }
    if state.real_claude:
        env["TODOIMPL_MODEL"] = "haiku"
    else:
        env["FAKE_CLAUDE_DIR"] = str(work / "fake")
        env["TODOIMPL_TURN_LAUNCH"] = "direct"  # fake turns never go through the user's systemd
        env["TODOIMPL_CLAUDE"] = str(work / "bin" / "claude")
    return env


def write_shims(state: State) -> None:
    """bin/: push-refusing git, pass-through capped.sh and (unless real) the fake claude."""
    shims = {
        "git": f'#!/bin/sh\nexec "{SHIMS / "git_push_refuse"}" "$@"\n',
        "capped.sh": '#!/bin/sh\nexec "$@"\n',
    }
    if not state.real_claude:
        # One script folder per run dir (`fake/runs/<item id>`): the shim keys on the first 8 chars of the
        # run dir name, so the two sections of one note would share scripts and race on popping them.
        fake = state.path / "fake" / "runs"
        shims["claude"] = (
            '#!/bin/sh\nrun=$(basename "$PWD"); [ "$run" = wt ] && run=$(basename "$(dirname "$PWD")")\n'
            f'export FAKE_CLAUDE_DIR="{fake}/$run"; mkdir -p "$FAKE_CLAUDE_DIR"\n'
            f'exec "{PYTHON}" "{SHIMS / "claude"}" "$@"\n'
        )
    for name, text in shims.items():
        target = state.path / "bin" / name
        target.write_text(text, encoding="utf-8")
        target.chmod(0o755)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        [real_git(), *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_IDENTITY},
    )


def make_repo(state: State) -> Path:
    """`<work>/src/e2e-demo` with one commit on main, pushed to the local bare `<work>/remote.git`."""
    work = state.path
    bare = work / "remote.git"
    _git(work, "init", "--bare", "-q", "-b", "main", str(bare))
    repo = work / "src" / REPO_NAME
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("e2e demo\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo
