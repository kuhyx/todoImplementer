"""Live cost of a credit turn from its stream, before the result event brings the real total.

An assistant event carries the message's `usage`: input and cache tokens are exact from the first event, the
output count is only the first snapshot. So output is the larger of that count and a size estimate from the
blocks (text, tool input, thinking). Each message is priced at the rates of the model it names (`prices`:
Opus 5.5 list prices, Sonnet as calibrated); a message that names none takes the configured credits model, an
unknown model the dearest rates. Against the SDK's own totals of 77 real Sonnet credit turns this ran about
twice too high (median 2.1; 5 turns under 1.0, the worst 0.31), which is the safe side for a brake: it stops a
turn early rather than late (the start gate and the grant margin cover the rare undercount).
"""

from __future__ import annotations

import json
from typing import Any

from . import prices, setting

PER_MTOK = prices.SONNET.per_mtok  # the kinds of usage, in the order priced
CHARS_PER_TOKEN = 3.0
SIGNATURE_CHARS_PER_TOKEN = 6.0  # hidden thinking leaves only a signature; its length tracks the tokens spent
USAGE_FIELDS = {
    "input_tokens": "input",
    "output_tokens": "output",
    "cache_read_input_tokens": "cache_read",
    "cache_creation_input_tokens": "cache_write",
}


def _chars(content: object) -> float:
    """Return the output tokens the content blocks of one assistant event stand for."""
    tokens = 0.0
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            tokens += len(str(block.get("text", ""))) / CHARS_PER_TOKEN
        elif kind == "tool_use":
            tokens += len(json.dumps(block.get("input", {}))) / CHARS_PER_TOKEN
        elif kind == "thinking":
            tokens += len(str(block.get("thinking", ""))) / CHARS_PER_TOKEN
            tokens += len(str(block.get("signature", ""))) / SIGNATURE_CHARS_PER_TOKEN
    return tokens


class Meter:
    """Adds up the list-price cost of the assistant messages of one turn, each message once."""

    def __init__(self) -> None:  # noqa: D107
        self._messages: dict[str, dict[str, float]] = {}
        self._models: dict[str, str] = {}  # message id -> the model the stream names for it
        self._default = setting.model()  # for a message that names none: the model the turn started on

    def feed(self, event: dict[str, Any]) -> bool:
        """Take one stream event; return True when it was an assistant message that changed the cost."""
        message = event.get("message")
        if event.get("type") != "assistant" or not isinstance(message, dict):
            return False
        usage = message.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        msg_id = str(message.get("id"))
        seen = self._messages.setdefault(msg_id, {"blocks": 0.0, **dict.fromkeys(PER_MTOK, 0.0)})
        if isinstance(message.get("model"), str):
            self._models[msg_id] = message["model"]
        seen["blocks"] += _chars(message.get("content"))
        for name, key in USAGE_FIELDS.items():
            value = usage.get(name)
            if isinstance(value, int | float) and not isinstance(value, bool):
                seen[key] = max(seen[key], float(value))
        return True

    def cost(self) -> float:
        """Return the turn's cost so far in dollars: each message at the list prices of its own model."""
        total = 0.0
        for msg_id, seen in self._messages.items():
            per_mtok = prices.rates(self._models.get(msg_id, self._default)).per_mtok
            for key, price in per_mtok.items():
                tokens = max(seen["output"], seen["blocks"]) if key == "output" else seen[key]
                total += tokens * price / 1e6
        return total
