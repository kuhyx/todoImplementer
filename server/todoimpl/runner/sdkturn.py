"""One credit turn through the Claude Agent SDK: `python -m todoimpl.runner.sdkturn <spec json>`.

Runs in the SDK's own venv (stdlib + `claude_agent_sdk` only), under the turn host like a plan turn. The SDK
spawns its bundled Claude Code CLI; a transport that wraps the SDK's own prints every raw stream-json
event the CLI emits, so the stream file has exactly the shape `claude -p --output-format stream-json`
writes. The SDK sets its own identity (entrypoint `sdk-py`); nothing here spoofs or hides it. The key
arrives in `ANTHROPIC_API_KEY` from the host's env file and is never printed.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

EVENTS = frozenset({"system", "assistant", "user", "result", "rate_limit_event"})  # not control messages
TRANSPORT = "claude_agent_sdk._internal.transport.subprocess_cli"
FAILED = 1


@dataclass
class Seen:
    """What went to stdout so far: the session and whether the CLI itself reported a result."""

    session_id: str | None = None
    result: bool = False


def emit(obj: dict[str, Any]) -> None:
    """Write one stream-json line and flush: the server tails the file."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def record(raw: dict[str, Any], seen: Seen) -> None:
    """Print an event of the CLI's stream (control traffic is skipped) and remember what it said."""
    if raw.get("type") not in EVENTS:
        return
    emit(raw)
    if isinstance(raw.get("session_id"), str):
        seen.session_id = raw["session_id"]
    seen.result = seen.result or raw["type"] == "result"


def tee(base: type, seen: Seen) -> type:
    """Subclass the SDK's CLI transport so `read_messages` prints each raw event before the SDK parses it."""

    class Tee(base):  # type: ignore[misc]
        def read_messages(self) -> AsyncIterator[dict[str, Any]]:
            return self._tee(super().read_messages())

        @staticmethod
        async def _tee(inner: AsyncIterator[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
            async for raw in inner:
                record(raw, seen)
                yield raw

    return Tee


async def turn(spec: dict[str, Any], seen: Seen) -> None:
    """Run the turn to its end; whatever the CLI prints lands in `seen` and on stdout."""
    sdk = importlib.import_module("claude_agent_sdk")
    base = importlib.import_module(TRANSPORT).SubprocessCLITransport
    options = sdk.ClaudeAgentOptions(
        cwd=spec["cwd"],
        add_dirs=spec["add_dirs"],
        permission_mode=spec["permission_mode"],
        resume=spec["resume"],
        model=spec["model"],
        settings=spec["settings"],
        allowed_tools=spec["allowed_tools"],
        disallowed_tools=spec["disallowed_tools"],
        setting_sources=spec["setting_sources"],
        effort=spec.get("effort"),
        # The SDK sends no Claude Code prompt unless asked; `claude -p` always does.
        system_prompt={"type": "preset", "preset": "claude_code"},
    )
    transport = tee(base, seen)(prompt=spec["prompt"], options=options)
    async for _ in sdk.query(prompt=spec["prompt"], options=options, transport=transport):
        pass


def main(argv: Sequence[str] | None = None) -> int:
    """Run the spec in `argv[0]`; an SDK failure before any result becomes one errored result line."""
    spec = json.loads((sys.argv[1:] if argv is None else argv)[0])
    seen = Seen()
    try:
        asyncio.run(turn(spec, seen))
    except Exception as exc:  # noqa: BLE001 - whatever the SDK raises must still end as a parsable result
        traceback.print_exc()
        if not seen.result:
            emit({
                "type": "result", "subtype": "error_during_execution", "is_error": True,
                "result": f"Agent SDK failed: {exc}", "session_id": seen.session_id,
                "total_cost_usd": 0, "num_turns": 0,
            })  # fmt: skip
        return FAILED
    return 0


if __name__ == "__main__":
    sys.exit(main())
