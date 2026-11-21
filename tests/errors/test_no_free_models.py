"""Error tickets never run on free models: kuhy, 2026-11-21, "they are too dumb for it" (T2445)."""

from __future__ import annotations

from dataclasses import fields

from todoimpl.errors.gate import Gate
from todoimpl.runner import tier

TICKET = "## Fix kartka: boom\nTier: cheap\nError: boom\nError-Signature: kartka:02b0d43d9f"


def test_t2445_the_start_gate_has_no_free_models_route() -> None:
    assert {f.name for f in fields(Gate)} == {"fetch", "credits"}


def test_t2445_a_card_with_an_error_ticket_is_never_cheap() -> None:
    assert not tier.is_cheap("kuhyx/kartka", TICKET)
    assert not tier.is_cheap("Make it text-free (textgate-rework)", TICKET)
    assert tier.is_cheap("kuhyx/kartka", "## Tidy\nTier: cheap")
