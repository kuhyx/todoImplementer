"""May a cheap turn use the free models? Public repo (`free-llm-check-dir`) and a gateway that answers.

Free providers log prompts, so `claude-free` itself refuses non-public repos; the server asks first so the
manager prompt never promises what the worker cannot do. Every failure is a plain "no": the manager then
does the work itself. Env: `TODOIMPL_FREE_GATEWAY` (default OmniRoute on 127.0.0.1:20128).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

GATEWAY = "http://127.0.0.1:20128"
CHECK_TIMEOUT = 20.0  # a cold `gh repo view` inside free-llm-check-dir may take up to 15 s
PROBE_TIMEOUT = 2.0
WORKER = "claude-free"
CHECKER = "free-llm-check-dir"
_KEY_REL = Path(".config") / "omniroute" / "api_key"


@dataclass(frozen=True)
class Verdict:
    """`allowed` = free models may do the edits; `why` names the first blocker otherwise."""

    allowed: bool
    why: str = ""
    detail: str = ""  # the exact probe error behind a dead gateway, for the free-issue log
    unreachable: bool = False  # nothing answered at all (refused, timed out): the gateway may come back


def _public(checker: str, worktree: Path) -> bool:
    try:
        done = subprocess.run(  # noqa: S603 - fixed tool, one path argument, no shell
            [checker, str(worktree)], capture_output=True, timeout=CHECK_TIMEOUT, check=False
        )
    except OSError, subprocess.SubprocessError:
        return False
    return done.returncode == 0


def base_url() -> str:
    """Return the gateway's base URL: `$TODOIMPL_FREE_GATEWAY` or the local OmniRoute."""
    return os.environ.get("TODOIMPL_FREE_GATEWAY") or GATEWAY


def _gateway_error(key: str) -> tuple[str, bool] | None:
    """Probe the gateway; None when it answers, else (the exact error text, whether nothing answered)."""
    base = base_url()
    request = urllib.request.Request(  # noqa: S310 - loopback gateway URL
        f"{base}/v1/models", headers={"Authorization": f"Bearer {key}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT):  # noqa: S310
            return None
    except urllib.error.HTTPError as exc:
        return f"gateway probe: HTTP {exc.code} from {base}/v1/models", False
    except OSError as exc:  # URLError, timeouts and refused connections are all OSErrors
        return f"gateway probe: {type(exc).__name__}: {exc}"[:500], True


def _key() -> str:
    try:
        return (Path.home() / _KEY_REL).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def check_gateway() -> bool:
    """Say whether the gateway answers with the key on disk (the `free` route's cached probe)."""
    return bool(key := _key()) and _gateway_error(key) is None


def check(worktree: Path) -> Verdict:
    """Return whether the free models are allowed for this worktree right now."""
    checker = shutil.which(CHECKER)
    if checker is None or shutil.which(WORKER) is None:
        return Verdict(allowed=False, why=f"{WORKER} is not installed")
    if not _public(checker, worktree):
        return Verdict(allowed=False, why="the repo is not public")
    if not (key := _key()):
        return Verdict(allowed=False, why="no gateway key")
    if (error := _gateway_error(key)) is not None:
        return Verdict(
            allowed=False, why="the free-model gateway is down", detail=error[0], unreachable=error[1]
        )
    return Verdict(allowed=True)
