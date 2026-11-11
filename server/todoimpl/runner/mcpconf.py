"""MCP servers of a board turn: none by default, plus the one its repo kind drives (T1986).

Every turn gets `--strict-mcp-config`, so none of kuhy's user, project or plugin MCP servers start (each
session cost ~500 MB of them, x25 sessions). Flutter repos add flutter-web-drive, Godot repos
godot-mcp-runtime. The definition is read from ~/.claude.json (a restored server), else from the
~/.claude/mcp-parked.json copy `mcp_park.sh` keeps; a server kuhy does not have is skipped silently.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from todoimpl.prompts.kind import Kind, detect_kind

KIND_SERVERS: dict[Kind, str] = {Kind.FLUTTER: "flutter-web-drive", Kind.GODOT: "godot-mcp-runtime"}


def _definitions(path: Path) -> dict[str, Any]:
    try:
        found = json.loads(path.read_text(encoding="utf-8")).get("mcpServers", {})
    except OSError, ValueError, AttributeError:
        return {}
    return found if isinstance(found, dict) else {}


def servers(worktree: Path) -> dict[str, dict[str, Any]]:
    """Return the MCP server definitions this worktree's turn starts (usually none)."""
    name = KIND_SERVERS.get(detect_kind(worktree))
    if name is None:
        return {}
    home = Path.home()
    for source in (home / ".claude.json", home / ".claude" / "mcp-parked.json"):
        found = _definitions(source).get(name)
        if isinstance(found, dict):
            return {name: found}
    return {}
