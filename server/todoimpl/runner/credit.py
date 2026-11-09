"""The credit route: one turn through the Claude Agent SDK on the free API credits, model sonnet.

Anthropic covers the Agent SDK (not the `claude` CLI) with the Max plan's API credits, so a credit turn is
`<sdk venv python> -m todoimpl.runner.sdkturn <spec>` under the same turn host as a plan turn. The spec
mirrors the plan argv (`claude.options` builds both): same session policy, tools and deny list.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from todoimpl.apikey import read_key
from todoimpl.credits import sdk

from . import claude
from .files import NeedsYouError
from .launch import SERVER_DIR

if TYPE_CHECKING:
    from pathlib import Path

MODEL = "sonnet"  # every role on credits (decision of kuhy, 2026-11-08)
SETTING_SOURCES = ("user", "project", "local")  # kuhy's full setup, as the CLI loads it
MODULE = "todoimpl.runner.sdkturn"


def build(  # noqa: PLR0913, PLR0917 - same signature as claude.build
    role: str,
    prompt: str,
    worktree: Path,
    resume: str | None = None,
    extra_dirs: tuple[Path, ...] = (),
    allow: tuple[str, ...] = (),
) -> claude.Invocation:
    """Build a credit turn; NeedsYouError when the SDK venv or the key vanished since routing."""
    python, key = sdk.python(), read_key()
    if python is None or key is None:
        msg = f"free API credits cannot run: {sdk.MISSING if python is None else 'no usable API key'}"
        raise NeedsYouError(msg)
    opt = claude.options(role, prompt, worktree, resume, extra_dirs, allow, MODEL)
    spec = {
        "prompt": opt.prompt, "model": opt.model, "cwd": str(opt.cwd), "add_dirs": list(opt.add_dirs),
        "permission_mode": opt.permission_mode, "resume": opt.resume, "settings": opt.settings,
        "allowed_tools": list(opt.allow), "disallowed_tools": list(opt.deny),
        "setting_sources": list(SETTING_SOURCES),
    }  # fmt: skip
    path = os.pathsep.join(p for p in (str(SERVER_DIR), os.environ.get("PYTHONPATH", "")) if p)
    env = {**opt.env, claude.KEY_VAR: key, "PYTHONPATH": path}
    return claude.Invocation(
        (str(python), "-m", MODULE, json.dumps(spec)), env, worktree, opt.notes, "credits"
    )
