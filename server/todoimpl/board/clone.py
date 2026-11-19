"""Clone a note's repo when no checkout exists anywhere (T2079, DOCS-landing.md, "Where a repo lives")."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

GH = "gh"  # the binary; the test suite points it at nothing so no test ever clones
TIMEOUT_S = 900.0  # a big repo over a slow line; the drive waits, the click never does


def src_root() -> Path:
    """Return where new clones go: $TODOIMPL_SRC, else ~/src."""
    return Path(os.environ.get("TODOIMPL_SRC") or Path.home() / "src")


def gh_clone(repo: str, dest: Path) -> None:
    """Run `gh repo clone <owner>/<name> <dest>`; any failure raises OSError naming gh's own words."""
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            [GH, "repo", "clone", repo, str(dest)],
            capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )  # fmt: skip
    except (subprocess.TimeoutExpired, OSError) as exc:
        msg = f"gh repo clone {repo}: {exc}"
        raise OSError(msg) from exc
    if proc.returncode != 0:
        msg = f"gh repo clone {repo} failed: {(proc.stderr or proc.stdout).strip()[-300:]}"
        raise OSError(msg)
