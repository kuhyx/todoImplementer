"""Create kuhy's new repo for a `new_repo` note: GitHub repo, first commit, clone in ~/src (DOCS-triage.md).

Every outward step is idempotent and written to `<run dir>/newrepo.json` after it succeeds, so a restart or a
Retry never creates a second repo: the name is reserved first, an existing repo counts as created, an existing
`main` counts as pushed, an existing clone counts as cloned. `gh` and `git` go through one injectable runner;
tests shim them (a push to the real GitHub fails in tests).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl import atomic

from . import scaffold
from .repos import OWNER, all_names, run_gh

if TYPE_CHECKING:
    from collections.abc import Callable

    Run = Callable[[list[str], Path | None], str]  # (argv, cwd) -> stdout

FILE = "newrepo.json"
STEPS = ("named", "created", "pushed", "cloned")
TIMEOUT_S = 50.0


class NewRepoError(Exception):
    """A step failed; the text names the command and its stderr tail."""


def run_cmd(argv: list[str], cwd: Path | None = None) -> str:
    """Run `gh` or `git` (the first word) with prompts off; a failure or timeout raises NewRepoError."""
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            argv, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )  # fmt: skip
    except (subprocess.TimeoutExpired, OSError) as exc:
        msg = f"{' '.join(argv[:3])}: {exc}"
        raise NewRepoError(msg) from exc
    if proc.returncode != 0:
        msg = f"{' '.join(argv[:3])} failed: {(proc.stderr or proc.stdout).strip()[-300:]}"
        raise NewRepoError(msg)
    return proc.stdout


def unique_name(wanted: str, taken: set[str], src: Path) -> str:
    """Return `wanted`, or `wanted-2`, `wanted-3`... when a repo (archived too) or ~/src has it."""
    names = {n.lower() for n in taken}
    pick, n = wanted, 1
    while pick.lower() in names or (src / pick).exists():
        n += 1
        pick = f"{wanted}-{n}"
    return pick


def _read(directory: Path) -> dict[str, str]:
    try:
        data = json.loads((directory / FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _mark(directory: Path, state: dict[str, str], step: str) -> None:
    state["step"] = step
    atomic.write_text(directory / FILE, json.dumps(state))


def _exists(run: Run, argv: list[str]) -> bool:
    try:
        return bool(run(argv, None).strip())
    except NewRepoError:
        return False


def _push(run: Run, scratch: Path, name: str, note: str, title: str) -> None:
    """Commit the scaffold in a scratch repo and push it as `main` of the new GitHub repo."""
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    for rel, text in scaffold.files(name, title, note).items():
        (scratch / rel).write_text(text, encoding="utf-8")
    url = f"https://github.com/{OWNER}/{name}"
    for argv in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", f"Scaffold {name}\n\nTodo: {note}"],
        ["git", "remote", "add", "origin", url],
        ["git", "push", "-q", "-u", "origin", "main"],
    ):
        run(argv, scratch)


def provision(  # noqa: PLR0913 - one note's facts, keyword-only
    directory: Path,
    src: Path,
    *,
    note: str,
    title: str,
    name: str,
    public: bool = False,
    run: Run = run_cmd,
    gh: Callable[[list[str]], str] = run_gh,
) -> str:
    """Create `kuhyx/<name>` (private unless asked), push the scaffold, clone to `<src>/<name>`; return it.

    Resumes after the last step that finished. The clone is for kuhy and the runner's worktrees; no session
    edits it.
    """
    state = _read(directory)
    if "name" not in state:  # reserve the name before anything outward
        try:
            taken = set(all_names(gh))
        except (OSError, ValueError) as exc:  # no list, no proof the name is free: fail closed
            msg = f"cannot list kuhyx repos: {exc}"
            raise NewRepoError(msg) from exc
        state = {"name": unique_name(name, taken, src)}
        _mark(directory, state, "named")
    name = state["name"]
    repo, url = f"{OWNER}/{name}", f"https://github.com/{OWNER}/{name}"
    done = STEPS.index(state["step"]) if state.get("step") in STEPS else 0
    if done < STEPS.index("created"):
        if not _exists(run, ["gh", "repo", "view", repo, "--json", "name", "--jq", ".name"]):
            seen = "--public" if public else "--private"
            run(["gh", "repo", "create", repo, seen, "--description", title[:100]], None)
        _mark(directory, state, "created")
    if done < STEPS.index("pushed"):
        if not _exists(run, ["git", "ls-remote", "--heads", url, "main"]):
            _push(run, directory / "scaffold", name, note, title)
        _mark(directory, state, "pushed")
    if done < STEPS.index("cloned"):
        if not (src / name / ".git").exists():
            run(["git", "clone", "-q", url, str(src / name)], None)
        _mark(directory, state, "cloned")
    return repo
