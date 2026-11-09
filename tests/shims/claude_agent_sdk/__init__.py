"""Fake `claude_agent_sdk` for hermetic tests: the real option names and a `query` that plays the CLI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClaudeAgentOptions:
    """The options the credit turn passes (a subset of the real dataclass)."""

    cwd: str | None = None
    add_dirs: list[str] = field(default_factory=list)
    permission_mode: str | None = None
    resume: str | None = None
    model: str | None = None
    settings: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    setting_sources: list[str] | None = None
    system_prompt: Any = None


async def query(*, prompt: str, options: ClaudeAgentOptions, transport: Any) -> AsyncIterator[dict[str, Any]]:
    """Yield what the transport reads, as the real one does after connecting and sending the prompt."""
    del prompt, options
    async for raw in transport.read_messages():
        yield raw
