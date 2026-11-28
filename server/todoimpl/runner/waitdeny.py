"""The calls a board session may not wait with (kuhy, 2026-11-28): `run_job` ends its turn instead (jobs.py).

`rules()` go to `--disallowedTools` (and the SDK's `disallowed_tools`); `is_wait` tells the permission gate
(permissions.py) that such a denial is a hard deny, never a gap to learn an allow rule for or hand to kuhy.
The Read rules are the harness's background-task output path (<tmp>/claude-<uid>/<project>/<session>/tasks/):
under /tmp and under this server's temp dir (kuhy's `TMPDIR` is /var/disktmp). `cat` of such a file through
Bash stays possible.
"""

from __future__ import annotations

import re
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .stream import Denial

BASH_RULES = ("Bash(sleep:*)", "Bash(tail --pid*)", "Bash(inotifywait*)", "Monitor")
WAIT_COMMAND = re.compile(r"(?:^|[\s;&|(])(?:sleep\s|tail\s+--pid|inotifywait\b)")
TASK_OUTPUT = re.compile(r"/claude-[^/]+/.+/tasks/")


def rules() -> tuple[str, ...]:
    """Return the deny rules of a turn launched now."""
    temps = dict.fromkeys(("/tmp", tempfile.gettempdir()))  # noqa: S108 - the harness's default location
    return (*BASH_RULES, *(f"Read(/{tmp}/claude-*/**/tasks/**)" for tmp in temps))


def is_wait(d: Denial) -> bool:
    """Say whether a denial is one of `RULES`: a wait, or a read of a background task's output."""
    if d.tool_name == "Monitor":
        return True
    if d.tool_name == "Bash":
        return WAIT_COMMAND.search(str(d.tool_input.get("command", ""))) is not None
    return d.tool_name == "Read" and TASK_OUTPUT.search(str(d.tool_input.get("file_path", ""))) is not None
