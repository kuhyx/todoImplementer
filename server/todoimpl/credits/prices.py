"""What a credit turn costs per model: the meter's rates per million tokens and the reserve of a running turn.

Rates by model family, matched on the model id (`claude-opus-5-5`, `claude-sonnet-5-5`, the aliases `opus`,
`sonnet`). An id of no known family is priced at the dearest family, so the hard stop never fires late.

Opus rates are Anthropic list prices for Claude Opus 5.5 (claude-api skill models table, cached 2026-11-03):
$4 in, $20 out, cache reads $0.20, cache writes 1.25x input. The Sonnet rates are kept as calibrated against
77 real credit turns (`meter.py`): $3 / $15, above Sonnet 5.5's list $2 / $10, so a Sonnet turn is still
overcounted, the safe side for a brake.

The reserve is what a started credit turn counts for until its live cost passes it (`pacing`). It was $2 for
Sonnet; Opus 5.5 lists at twice Sonnet 5.5 ($20 against $10 per million output tokens): $4. The ledger
of 1920 turns (Sonnet) had median $0.34, p90 $3.06, p99 $15: at Opus prices the p90 is about $6, and the
reserve was never the cap on one turn, the hard stop is.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rates:
    """Dollars per million tokens by usage kind, and the reserve of one running turn."""

    per_mtok: dict[str, float]
    reserve_usd: float


SONNET = Rates({"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75}, 2.0)
OPUS = Rates({"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0}, 4.0)
# Claude Haiku 5.5 list (claude-api skill, cached 2026-11-03): $0.10 in, $0.50 out up to 100K input tokens
# (5x above, which a one-shot never reaches); cache reads 0.1x, writes 1.25x input. Batch one-shots only.
HAIKU = Rates({"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125}, 0.05)
FAMILIES = {"sonnet": SONNET, "opus": OPUS, "haiku": HAIKU}
BATCH_FACTOR = 0.5  # the Message Batches API bills half the list price
DEAREST = OPUS


def rates(model: str) -> Rates:
    """Return the rates of `model`'s family; an unknown model gets the dearest."""
    name = model.lower()
    for family, found in FAMILIES.items():
        if family in name:
            return found
    return DEAREST


def cost(model: str, usage: dict[str, object], factor: float = 1.0) -> float:
    """Return the dollars of an API `usage` object at `model`'s rates times `factor`; bad counts count 0."""
    per = rates(model).per_mtok
    keys = {"input": "input_tokens", "output": "output_tokens", "cache_read": "cache_read_input_tokens"}
    keys["cache_write"] = "cache_creation_input_tokens"
    total = 0.0
    for kind, key in keys.items():
        count = usage.get(key)
        if isinstance(count, int) and not isinstance(count, bool):
            total += count * per[kind] / 1e6
    return total * factor


def reserve(model: str) -> float:
    """Return what a running credit turn on `model` counts for before its live cost passes it."""
    return rates(model).reserve_usd
