"""Is a repo archived on GitHub? It refuses every push, so its umbrella child is dropped (T1924).

Any failure (no gh, no network, an unknown repo) reads as "not archived": the child then runs as before and a
refused push still reaches kuhy the usual way.
"""

from __future__ import annotations

import subprocess

GH = "gh"
TIMEOUT = 15.0


def archived(repo: str) -> bool:
    """Return True only when `gh api repos/<repo>` answers `.archived` with true."""
    try:
        done = subprocess.run(  # noqa: S603 - fixed tool, the repo name as one argument, no shell
            [GH, "api", f"repos/{repo}", "--jq", ".archived"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return False
    return done.returncode == 0 and done.stdout.strip() == "true"
