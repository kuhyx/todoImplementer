"""Scratch repos for the no-limit tests: a `kuhyx/<name>` origin that git rewrites to a local bare remote."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from runnerfakes import make_repo, sh
from todoimpl.board.state import RunState

if TYPE_CHECKING:
    from pathlib import Path

    from runnerfakes import Env


def claude_md(**commands: str) -> str:
    """Return a CLAUDE.md whose Commands section holds these bullets (`gate_x` -> `gate-x`)."""
    lines = "".join(f"- {key.replace('_', '-')}: `{cmd}`\n" for key, cmd in commands.items())
    return f"# demo\n\n## Commands\n\n{lines}"


def kuhy_repo(world: Env, name: str = "demo", files: dict[str, str] | None = None, **commands: str) -> Path:
    """Make `~/src/<name>` with origin `https://github.com/kuhyx/<name>`, fetched from a local bare remote."""
    repo = make_repo(world, name, files)
    (repo / "CLAUDE.md").write_text(claude_md(**commands), encoding="utf-8")
    sh(repo, "git", "commit", "-qam", "commands")
    sh(repo, "git", "push", "-q", "origin", "main")
    url = f"https://github.com/kuhyx/{name}"
    sh(repo, "git", "remote", "set-url", "origin", url)
    sh(repo, "git", "config", f"url.{world.tmp / 'remotes' / name}.git.insteadOf", url)
    return repo


def remote_log(world: Env, name: str = "demo") -> list[str]:
    """Return the subjects of the bare remote's main, newest first."""
    bare = world.tmp / "remotes" / f"{name}.git"
    return sh(bare, "git", "log", "--format=%s", "main").split("\n")[:-1]


def park(
    root: Path, card: str, repo: str = "kuhyx/demo", body: str = "", stage: str = "paused_limit"
) -> None:
    """Write a run of `card` resting at `stage`."""
    run = root / card
    run.mkdir(parents=True, exist_ok=True)
    st = RunState(task_id=card, stage=stage, repo=repo, note_body=body)
    (run / "state.json").write_text(json.dumps(st.to_dict()), encoding="utf-8")


def public(home: Path, *repos: str) -> None:
    """Cache `repos` as PUBLIC in the visibility file `free-llm-check-dir` keeps."""
    path = home / ".cache" / "omniroute_offload" / "visibility.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({r: {"visibility": "PUBLIC"} for r in repos}), encoding="utf-8")
