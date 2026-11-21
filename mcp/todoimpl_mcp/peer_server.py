"""MCP server ``peer``: Claude Code sessions and board task sessions message each other (DOCS-peer.md).

Board turns get it from ``runner/mcpconf.py`` (as their card); interactive sessions from ``~/.claude.json``
(``mcp/setup_mcp.sh``), under ``$TODOIMPL_PEER_LABEL`` or their cwd's name. Every answer is compact JSON;
a refusal is its reason as text.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver import MCPServer

from todoimpl_mcp.peer_client import Peer, PeerError

if TYPE_CHECKING:
    from collections.abc import Callable

logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(asctime)s peer-mcp: %(message)s")
mcp = MCPServer("peer")
_peer: list[Peer] = []


def reset() -> None:
    """Forget the sender id (tests start fresh)."""
    _peer.clear()


def _me() -> Peer:
    if not _peer:
        _peer.append(Peer())
    return _peer[0]


def _answer(call: Callable[[], Any]) -> str:
    try:
        return json.dumps(call(), ensure_ascii=False, separators=(",", ":"))
    except PeerError as exc:
        return str(exc)


@mcp.tool(description="Send text to a running board task (id or short id) or a session label.", structured_output=False)
def send_peer(to: str, text: str, reply_to: str = "") -> str:
    """Send a peer message; reply_to links it to a thread."""
    return _answer(lambda: _me().send(to, text, reply_to or None))


@mcp.tool(description="Wait for the answer to a sent message id (seconds; retry to keep waiting).", structured_output=False)
def await_reply(id: str, timeout: float = 600.0) -> str:  # noqa: A002 - the tool's argument name
    """Wait for a reply."""
    return _answer(lambda: _me().await_reply(id, timeout))


@mcp.tool(description="Peer messages sent to you; wait up to `wait` s for the first.", structured_output=False)
def inbox(wait: float = 0.0) -> str:
    """Fetch the inbox."""
    return _answer(lambda: _me().inbox(wait))


@mcp.tool(description="Answer a peer message sent to you.", structured_output=False)
def reply_peer(id: str, text: str) -> str:  # noqa: A002 - the tool's argument name
    """Reply to a message."""
    return _answer(lambda: _me().reply(id, text))


if __name__ == "__main__":
    mcp.run()
