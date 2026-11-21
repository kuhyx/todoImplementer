"""CLI over the peer endpoint: ``python -m todoimpl_mcp.peer_cli [--label L] send|await|inbox|reply ...``.

Prints the board's answer as JSON; a refusal goes to stderr with exit 1. The sender id the board gives a
label is kept in ``$XDG_CACHE_HOME/todoimpl-peer/<label>.sender``, so later calls read the same inbox.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from todoimpl_mcp.peer_client import Peer, PeerError, default_label


def _cache(label: str) -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "todoimpl-peer" / f"{label.replace('/', '_')}.sender"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="peer", description="Message board task sessions.")
    parser.add_argument("--label", default=None, help="who you are (default: $TODOIMPL_PEER_LABEL or cwd name)")
    sub = parser.add_subparsers(dest="command", required=True)
    send = sub.add_parser("send")
    send.add_argument("to")
    send.add_argument("text", help="the text, or - for stdin")
    send.add_argument("--reply-to", default=None)
    wait = sub.add_parser("await")
    wait.add_argument("id")
    wait.add_argument("--timeout", type=float, default=600.0)
    box = sub.add_parser("inbox")
    box.add_argument("--wait", type=float, default=0.0)
    reply = sub.add_parser("reply")
    reply.add_argument("id")
    reply.add_argument("text")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one command; 0 on success, 1 on a refusal."""
    args = _parser().parse_args(argv)
    label = args.label or default_label()
    cache = _cache(label)
    sender = cache.read_text(encoding="utf-8").strip() if cache.exists() else None
    peer = Peer(label, sender)
    try:
        match args.command:
            case "send":
                text = sys.stdin.read() if args.text == "-" else args.text
                out: object = peer.send(args.to, text, args.reply_to)
            case "await":
                out = peer.await_reply(args.id, args.timeout)
            case "inbox":
                out = peer.inbox(args.wait)
            case _:
                out = peer.reply(args.id, args.text)
    except PeerError as exc:
        print(exc, file=sys.stderr)
        return 1
    if peer.sender and peer.sender != sender:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(peer.sender + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
