"""Error tickets never run on free models: kuhy, 2026-11-21, "they are too dumb for it" (T2445)."""

from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from todoimpl.errors.gate import Gate
from todoimpl.runner import tier, tiering

if TYPE_CHECKING:
    from todoimpl.runner.pipeline import Driver

TICKET = "## Fix kartka: boom\nTier: cheap\nError: boom\nError-Signature: kartka:02b0d43d9f"


def test_t2445_the_start_gate_has_no_free_models_route() -> None:
    assert {f.name for f in fields(Gate)} == {"fetch", "credits"}


def test_t2445_a_card_with_an_error_ticket_is_never_cheap() -> None:
    assert not tier.is_cheap("kuhyx/kartka", TICKET)
    assert not tier.is_cheap("Make it text-free (textgate-rework)", TICKET)
    assert tier.is_cheap("kuhyx/kartka", "## Tidy\nTier: cheap")


def test_t2445_a_cycle_that_now_holds_a_ticket_drops_a_cheap_tier_it_kept() -> None:
    # a repo card's `tier` stays across cycles: a shipped cheap cycle must not carry it to a ticket
    st = SimpleNamespace(extra={"tier": "cheap", "escalated": True, "escalate_reason": "x"})
    item = SimpleNamespace(title="kuhyx/kartka", body=TICKET, parts=())
    driver = cast("Driver", SimpleNamespace(state=st, item=item, ctx=SimpleNamespace(run_dir=None)))
    assert tiering.plan_turn(driver, tiering.IMPLEMENT) == tiering.Turn()
    assert st.extra["tier"] == "normal"
    assert st.extra["ticket_model"] == "claude-sonnet-5-5"  # an app's ticket runs on Sonnet (T2582)
