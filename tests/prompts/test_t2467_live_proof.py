"""T2467: the proof round checks only the parts Ship named, and keeps the rest of the checklist."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from todoimpl.prompts import PromptContext, build

if TYPE_CHECKING:
    from pathlib import Path


def test_t2467_the_proof_prompt_checks_only_the_named_parts(ctx: PromptContext, tmp_path: Path) -> None:
    text = build("live_proof", replace(ctx, failure_tail="[k-0] gamma: C2 deferred", run_dir=tmp_path))
    assert text.startswith("override\n")
    assert "[k-0] gamma: C2 deferred" in text
    assert str(tmp_path / "live_check.md") in text
    assert "Live check stage" not in text  # not the whole live check again
    assert "`[~]`" in text  # says a deferred row closes no part
