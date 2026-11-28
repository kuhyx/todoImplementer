"""kuhy's optional session policy: how loose a board session's permissions are (not an /api shape).

`~/.config/todoImplementer/session-policy.json` (`$TODOIMPL_POLICY` overrides the path), all keys optional:
`permission_mode` (default acceptEdits), `add_dirs` (default none, `~` expanded),
`disable_hooks` (default false), `deny` (deny rules; null or missing = the built-in list, [] = none).
A missing file keeps today's behaviour; an invalid one is ignored with a warning,
so a typo never loosens or breaks a run.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from todoimpl.board.clone import src_root

from .hooks import shrink_read

KEYS = frozenset({"permission_mode", "add_dirs", "disable_hooks", "deny"})
# One Bash call ends at 40 s (claude moves it to the background), so the model gets a result and 20 s to
# answer it before the board's 60 s stall line (T2444, T2453). kuhy's settings.json sets an hour, and settings
# env beats the process env.
BASH_CAP_MS = "40000"
BASH_CAP = {"BASH_DEFAULT_TIMEOUT_MS": BASH_CAP_MS, "BASH_MAX_TIMEOUT_MS": BASH_CAP_MS}


SHRINK_HOOK = Path(__file__).parent / "hooks" / "shrink_read.py"


def shrink_dir() -> Path:
    """Return the cache directory, made if missing; a turn gets it as an add-dir so it may read the copies."""
    found = shrink_read.cache_dir()
    found.mkdir(parents=True, exist_ok=True)
    return found


def shrink_hook() -> dict[str, object]:
    """Return the one hook of a board session: a `Read` of an image over 1000 px gets a shrunk copy."""
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(SHRINK_HOOK))}"
    return {"PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": command}]}]}


def turn_settings(*, hooks_off: bool) -> str:
    """Return a board session's `--settings` JSON: the Bash cap and the image-shrink hook.

    `hooks_off` (the policy's `disable_hooks`) used to add `disableAllHooks`, which would kill the shrink hook
    too. Hooks of kuhy's user settings never load (`--setting-sources project`), so the shrink hook stays
    the only one the board adds either way.
    """
    del hooks_off  # the policy key stays valid; the shrink hook is on in both modes
    return json.dumps({"hooks": shrink_hook(), "env": BASH_CAP}, separators=(",", ":"))


HOOKS_OFF = turn_settings(hooks_off=True)
WRITERS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def src_deny(src: Path | None = None) -> tuple[str, ...]:
    """Return the writer-tool deny rules for kuhy's checkouts under the src root (`//` = absolute, T2464)."""
    root = src or src_root()
    return tuple(f"{tool}(/{root}/**)" for tool in WRITERS)


def src_deny_for(cwd: Path) -> tuple[str, ...]:
    """Return `src_deny()` for every turn, whatever kuhy's policy says (T2515), unless its cwd is there.

    A closing turn's cwd is kuhy's checkout under the src root; it has Edit denied anyway.
    """
    root = src_root()
    return () if cwd.is_relative_to(root) else src_deny(root)


@dataclass(frozen=True)
class Policy:
    """The resolved policy; `present` = kuhy wrote a valid file, which lifts the auto-allow never-list."""

    permission_mode: str = "acceptEdits"
    add_dirs: tuple[str, ...] = ()
    disable_hooks: bool = False
    deny: tuple[str, ...] | None = None
    present: bool = False
    warning: str | None = None


def policy_path() -> Path:
    """`$TODOIMPL_POLICY`, else ~/.config/todoImplementer/session-policy.json."""
    given = os.environ.get("TODOIMPL_POLICY")
    return Path(given) if given else Path.home() / ".config" / "todoImplementer" / "session-policy.json"


def _strings(value: object) -> tuple[str, ...] | None:
    ok = isinstance(value, list) and all(isinstance(v, str) and v for v in value)
    return tuple(value) if ok and isinstance(value, list) else None


def _check(data: dict[str, object]) -> Policy | str:
    """Return the policy, or what is wrong with the file."""
    if unknown := sorted(set(data) - KEYS):
        return f"unknown key(s) {', '.join(unknown)}"
    mode = data.get("permission_mode", "acceptEdits")
    hooks = data.get("disable_hooks", False)
    dirs = _strings(data.get("add_dirs", []))
    deny = data.get("deny")
    deny_rules = _strings(deny) if deny is not None else None
    if not isinstance(mode, str) or not mode:
        return "permission_mode must be a non-empty string"
    if not isinstance(hooks, bool):
        return "disable_hooks must be true or false"
    if dirs is None:
        return "add_dirs must be a list of strings"
    if deny is not None and deny_rules is None:
        return "deny must be a list of strings or null"
    return Policy(mode, tuple(str(Path(d).expanduser()) for d in dirs), hooks, deny_rules, present=True)


def load() -> Policy:
    """Read the policy file; defaults when absent, defaults plus a warning when unreadable or invalid."""
    path = policy_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Policy()
    except OSError as exc:
        return Policy(warning=f"session policy {path} ignored: {exc}")
    try:
        data = json.loads(raw)
    except ValueError:
        return Policy(warning=f"session policy {path} ignored: not valid JSON")
    if not isinstance(data, dict):
        return Policy(warning=f"session policy {path} ignored: not a JSON object")
    checked = _check(data)
    return (
        checked
        if isinstance(checked, Policy)
        else Policy(warning=f"session policy {path} ignored: {checked}")
    )
