"""Hermetic helpers for runner tests: temp HOME with shims first on PATH, scratch repos, a fake client."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.items import Item, split_items
from todoimpl.todo_mcp.model import Task, TodoError
from todoimpl.umbrella.note import tick

SHIMS = Path(__file__).resolve().parents[1] / "shims"
REAL_GIT = shutil.which("git") or "/usr/bin/git"


@dataclass
class Env:
    """Paths of one hermetic test world."""

    tmp: Path
    home: Path
    bin: Path
    fake: Path
    root: Path
    src: Path

    def script(self, key: str, *lines: dict[str, Any]) -> None:
        """Queue one fake-claude turn for a worktree id8 (or `default`)."""
        folder = self.fake / key
        folder.mkdir(parents=True, exist_ok=True)
        n = len(list(folder.iterdir()))
        body = "".join(json.dumps(line) + "\n" for line in lines)
        (folder / f"{n:03d}.jsonl").write_text(body, encoding="utf-8")

    def calls(self) -> list[dict[str, Any]]:
        """Every fake-claude invocation so far."""
        path = self.fake / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def executable(path: Path, text: str) -> None:
    """Write an executable file."""
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


# `gh api repos/<r> --jq .archived`: true for a repo listed in $FAKE_GH_ARCHIVED; no network ever.
GH_SHIM = '#!/bin/sh\ncase " $FAKE_GH_ARCHIVED " in *" ${2#repos/} "*) echo true ;; *) echo false ;; esac\n'


# The deploy line every demo repo declares (T1960): it logs a line to $DEPLOY_LOG, leaves a file in the tree,
# prints, and exits $DEPLOY_EXIT.
DEPLOY_COMMAND = (
    'echo deployed >> "${DEPLOY_LOG:-/dev/null}"; touch deploy-artifact.txt; '
    'echo shim-deploy-output; exit "${DEPLOY_EXIT:-0}"'
)
CLAUDE_MD = f"# demo\n\n## Commands\n\n- run: `./run.sh`\n- deploy: `{DEPLOY_COMMAND}`\n"
NO_DEPLOY_MD = "# demo\n\n## Commands\n\n- run: `./run.sh`\n"


def git_shim(guard: Path) -> str:
    """Write the `git` on PATH: real git at once, the push guard only when `push` is an argument."""
    return (
        f'#!/bin/sh\nfor a in "$@"; do [ "$a" = push ] && exec "{guard}" "$@"; done\nexec "$REAL_GIT" "$@"\n'
    )


def make_env(tmp: Path) -> tuple[Env, dict[str, str]]:
    """Build the world; return it and the env vars a test must set."""
    world = Env(tmp, tmp / "home", tmp / "bin", tmp / "fake", tmp / "root", tmp / "home" / "src")
    for folder in (world.home, world.bin, world.fake, world.src):
        folder.mkdir(parents=True)
    executable(world.bin / "claude", f'#!/bin/sh\nexec "{sys.executable}" "{SHIMS / "claude"}" "$@"\n')
    executable(world.bin / "git", git_shim(SHIMS / "git_push_refuse"))
    executable(world.bin / "capped.sh", '#!/bin/sh\nexec "$@"\n')
    executable(world.bin / "gh", GH_SHIM)
    executable(world.bin / "systemctl", "#!/bin/sh\nexit 3\n")  # no unit is ever running: never the real one
    (world.tmp / "adb").mkdir()  # no phone attached, and never the real adb (`fake_adb` lists devices)
    executable(
        world.bin / "adb",
        f'#!/bin/sh\nFAKE_ADB_DIR="{world.tmp / "adb"}" exec "{sys.executable}" "{SHIMS / "adb"}" "$@"\n',
    )
    env = {
        "HOME": str(world.home),
        "PATH": f"{world.bin}:{os.environ['PATH']}",
        "REAL_GIT": REAL_GIT,
        "GIT_PUSH_ALLOW_ROOT": str(tmp),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "FAKE_CLAUDE_DIR": str(world.fake),
        "TODOIMPL_HOME": str(world.root),
        "TODOIMPL_CAPPED": str(world.bin / "capped.sh"),
    }
    return world, env


def sh(cwd: Path, *argv: str) -> str:
    """Run a command (shims on PATH) and return stdout; raise on failure."""
    return subprocess.run(argv, cwd=cwd, check=True, capture_output=True, text=True).stdout


def make_repo(world: Env, name: str = "demo", files: dict[str, str] | None = None) -> Path:
    """Make a clone at ~/src/<name> of a local bare remote, one commit on main, CLAUDE.md with a deploy."""
    bare = world.tmp / "remotes" / f"{name}.git"
    bare.mkdir(parents=True)
    sh(bare, "git", "init", "--bare", "-q", "-b", "main")
    repo = world.src / name
    repo.mkdir()
    sh(repo, "git", "init", "-q", "-b", "main")
    for rel, text in {"CLAUDE.md": CLAUDE_MD, **(files or {"README.md": "demo\n"})}.items():
        (repo / rel).write_text(text, encoding="utf-8")
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-q", "-m", "init")
    sh(repo, "git", "remote", "add", "origin", str(bare))
    sh(repo, "git", "push", "-q", "-u", "origin", "main")
    return repo


def task(
    id8: str = "abcd1234",
    *,
    repo: str | None = "kuhyx/demo",
    body: str = "",
    done_check: str | None = None,
    title: str = "Add hello file",
) -> Task:
    """Return a todo note."""
    return Task(id8, title, body, repo, "todo", "medium", done_check)


@dataclass
class FakeClient:
    """Duck-typed service ItemView: card ids `<note id8>-<n>`, get_task and close_task only."""

    tasks: dict[str, Task] = field(default_factory=dict)
    closed: list[tuple[str, str]] = field(default_factory=list)
    fail_close: bool = False
    fail_get: bool = False
    unreachable: int = 0
    fail_add: int = 0
    added: list[tuple[str, str, str]] = field(default_factory=list)
    abandoned: list[str] = field(default_factory=list)
    fail_abandon: bool = False
    fail_tick: bool = False
    ticked: list[str] = field(default_factory=list)

    def get_task(self, card: str) -> CardTask:
        """Return the note section behind a card, or TodoError like the real view."""
        if self.unreachable > 0:
            self.unreachable -= 1
            msg = "cannot reach MCP server at http://127.0.0.1:1: connection refused"
            raise TodoError(msg)
        note, _, index = card.partition("-")
        items = split_items(self.tasks[note]) if note in self.tasks and not self.fail_get else []
        if not index.isdigit() or int(index) >= len(items):
            msg = f"unknown task {card}"
            raise TodoError(msg)
        return CardTask.of(self.tasks[note], items[int(index)])

    def close_task(self, card: str, evidence: str) -> None:
        """Record the close (or fail when asked)."""
        if self.fail_close:
            msg = "close refused"
            raise TodoError(msg)
        self.closed.append((card, evidence))

    def add_task(self, repo: str, title: str, body: str = "") -> Task:
        """Record a follow-up note (or fail when asked) and return it."""
        if self.fail_add:
            self.fail_add -= 1
            msg = "add refused"
            raise TodoError(msg)
        self.added.append((repo, title, body))
        return Task(f"f0llow{len(self.added):02d}", title, body, repo, "todo", "medium", None)

    def abandon(self, card: str) -> bool:
        """Record the abandon (or fail when asked); True like a note with no other open section."""
        if self.fail_abandon:
            msg = "abandon refused"
            raise TodoError(msg)
        self.abandoned.append(card)
        return True

    def tick_child(self, card: str, cid: str, mark: str = "x") -> None:
        """Tick an umbrella child's checkbox in the stored note (or fail when asked)."""
        if self.fail_tick:
            msg = "tick refused"
            raise TodoError(msg)
        note = card.partition("-")[0]
        self.tasks[note] = replace(self.tasks[note], body=tick(self.tasks[note].body, cid, mark))
        self.ticked.append(cid)

    def item(self, id8: str, index: int = 0) -> Item:
        """Return the note's item at index."""
        return self.get_task(f"{id8}-{index}").item
