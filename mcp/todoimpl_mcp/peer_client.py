"""HTTP client of the board's loopback peer endpoint (``POST /api/peer/*``, DOCS-peer.md).

Reads the token from its 0600 file (``$TODOIMPL_PEER_TOKEN_FILE``, else ``$TODOIMPL_HOME/peer.token``) at
every call, never from argv or the environment. A board session's MCP server gets ``$TODOIMPL_PEER_CARD``
and the path of its card key (``$TODOIMPL_PEER_KEY_FILE``) and speaks as ``task:<card>``; any other caller
speaks under a label and keeps the sender id the board gave it on first contact.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

URL_ENV = "TODOIMPL_PEER_URL"
TOKEN_ENV = "TODOIMPL_PEER_TOKEN_FILE"  # noqa: S105 - a variable name, not a secret
CARD_ENV = "TODOIMPL_PEER_CARD"
KEY_ENV = "TODOIMPL_PEER_KEY_FILE"
WAIT_ENV = "TODOIMPL_PEER_MAX_WAIT"  # board sessions: one tool call stays under the board's 60 s line
LABEL_ENV = "TODOIMPL_PEER_LABEL"
DEFAULT_URL = "http://127.0.0.1:8786/api/peer"
HEADER = "X-Todoimpl-Peer-Token"
SLICE = 25.0  # one long-poll request; the server caps it the same
ENDED = ("answered", "expired", "dead_end")
_BAD = re.compile(r"[^A-Za-z0-9_.:/@+-]+")


class PeerError(Exception):
    """The board refused or could not be reached; ``str()`` is the reason."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Keep the retry time the board gave, if any."""
        super().__init__(message if retry_after is None else f"{message} (retry in {retry_after:g} s)")
        self.retry_after = retry_after


def default_label() -> str:
    """``$TODOIMPL_PEER_LABEL``, else the cwd's name made label-safe (never naming kuhy)."""
    given = os.environ.get(LABEL_ENV)
    if given:
        return given
    label = _BAD.sub("-", Path.cwd().name).strip("-")[:64]
    return label if label and "kuhy" not in label.lower() else "session"


def token_file() -> Path:
    """Where the peer token lives."""
    given = os.environ.get(TOKEN_ENV)
    if given:
        return Path(given)
    home = os.environ.get("TODOIMPL_HOME")
    return (Path(home) if home else Path.home() / ".cache" / "todoImplementer") / "peer.token"


def _read(path: Path, what: str) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        msg = f"cannot read the peer {what} {path}: {exc.strerror}"
        raise PeerError(msg) from exc


class Peer:
    """One caller of the endpoint; keeps its sender id between calls."""

    def __init__(self, label: str | None = None, sender: str | None = None) -> None:
        """Speak as `label` (default: `default_label()`), or as the board card named in the environment."""
        self.label = label or default_label()
        self.sender = sender
        self.display = ""
        self.card, self.key = os.environ.get(CARD_ENV), Path(os.environ.get(KEY_ENV, ""))

    def _who(self) -> dict[str, str]:
        if self.card:
            return {"card": self.card, "card_key": _read(self.key, "card key")}
        return {"label": self.label, **({"sender": self.sender} if self.sender else {})}

    def _post(self, route: str, body: dict[str, Any], wait: float = 0.0) -> dict[str, Any]:
        url = urlsplit(os.environ.get(URL_ENV, DEFAULT_URL).rstrip("/"))
        token = _read(token_file(), "token")
        conn = http.client.HTTPConnection(url.hostname or "127.0.0.1", url.port or 80, timeout=wait + 15)
        raw = json.dumps({**self._who(), **body}).encode()
        headers = {"Content-Type": "application/json", HEADER: token}
        try:
            conn.request("POST", f"{url.path}/{route}", body=raw, headers=headers)
            reply = json.loads(conn.getresponse().read() or b"{}")
        except (OSError, ValueError) as exc:
            msg = f"board down at {url.geturl()}: run systemctl --user start todoimplementer ({exc})"
            raise PeerError(msg) from exc
        finally:
            conn.close()
        if not reply.get("ok"):
            raise PeerError(str(reply.get("error", {}).get("message", reply)), reply.get("retry_after"))
        self.sender, self.display = reply.get("sender", self.sender), reply.get("as", self.display)
        return dict(reply)

    def send(self, to: str, text: str, reply_to: str | None = None) -> dict[str, Any]:
        """Send `text` to a task id, short id or label; return the message (its id is for await_reply)."""
        body = {"to": to, "text": text, **({"reply_to": reply_to} if reply_to else {})}
        message: dict[str, Any] = self._post("send", body)["message"]
        return message

    def await_reply(self, msg_id: str, timeout: float = 600.0) -> dict[str, Any]:
        """Wait up to `timeout` s (capped by $TODOIMPL_PEER_MAX_WAIT) for the answer; return the message."""
        cap = os.environ.get(WAIT_ENV)
        left = min(timeout, float(cap)) if cap else timeout
        end = time.monotonic() + left
        while True:
            part = max(min(SLICE, end - time.monotonic()), 0.0)
            message: dict[str, Any] = self._post("await", {"id": msg_id, "timeout": part}, part)["message"]
            if message["state"] in ENDED or time.monotonic() >= end:
                return message

    def inbox(self, wait: float = 0.0) -> list[dict[str, Any]]:
        """Messages sent to this caller (each now delivered), waiting up to `wait` s for the first."""
        part = min(wait, SLICE)
        messages: list[dict[str, Any]] = self._post("inbox", {"wait": part}, part)["messages"]
        return messages

    def reply(self, msg_id: str, text: str) -> dict[str, Any]:
        """Answer a message sent to this caller."""
        message: dict[str, Any] = self._post("reply", {"id": msg_id, "text": text})["message"]
        return message
