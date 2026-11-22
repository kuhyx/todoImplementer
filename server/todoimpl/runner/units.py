"""User units that run from a run's worktrees (T2494).

A session starts helpers as transient user units (`systemd-run --user --unit=tutor51-web ...`, a dev server
from its worktree's venv); they outlive the session and kept running after the cleanup deleted their
worktree. `in_worktrees` names the active user services whose `WorkingDirectory` is inside one of the run's
`<run>/wt*` dirs (gone or not); `stop` stops them. A systemctl that is missing or fails only means none:
the disk cleanup goes on.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

ENV = "TODOIMPL_SYSTEMCTL"  # tests point it at a fake
TIMEOUT = 30.0
log = logging.getLogger("todoimpl.runner")


def tool() -> str:
    """Return the systemctl to run."""
    return os.environ.get(ENV) or "systemctl"


def _systemctl(*args: str) -> str | None:
    """Return stdout of `systemctl --user <args>`, None when it is missing or fails."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [tool(), "--user", *args], capture_output=True, text=True, timeout=TIMEOUT, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("systemctl %s: %s", args[0], exc)
        return None
    if proc.returncode != 0:
        log.warning("systemctl %s exited %d: %s", args[0], proc.returncode, proc.stderr.strip())
        return None
    return proc.stdout


def _in_worktree(run: Path, directory: str) -> bool:
    """Tell whether `directory` (its systemd `!-+:` prefix stripped) lies in a `<run>/wt*` dir."""
    path = Path(directory.lstrip("!-+:"))
    if not directory or not path.is_absolute():
        return False
    try:
        first = path.relative_to(run).parts[:1]
    except ValueError:
        return False
    return bool(first) and first[0].startswith("wt")


def in_worktrees(run: Path) -> list[str]:
    """Return the active user services whose WorkingDirectory is in one of `run`'s worktrees."""
    listed = _systemctl(
        "list-units", "--type=service", "--state=active", "--plain", "--no-legend", "--no-pager"
    )
    names = [line.split()[0] for line in (listed or "").splitlines() if line.strip()]
    shown = _systemctl("show", "-p", "Id", "-p", "WorkingDirectory", "--", *names) if names else None
    found: list[str] = []
    for block in (shown or "").split("\n\n"):
        props = dict(line.partition("=")[::2] for line in block.splitlines() if "=" in line)
        if _in_worktree(run, props.get("WorkingDirectory", "")):
            found.append(props["Id"])
    return found


def stop(names: list[str]) -> None:
    """Stop `names` (a transient unit vanishes on stop); a failure is logged, never raised."""
    _systemctl("stop", "--", *names)
