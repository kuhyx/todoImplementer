"""The Haiku one-shots (merge classifier, lesson drafts) show in the cost totals."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from todoimpl.runner.oneshot import LEDGER
from todoimpl.usage import usage_summary

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

NOW = datetime(2026, 11, 5, 12, 0).timestamp()  # noqa: DTZ001
YESTERDAY = datetime(2026, 11, 4, 12, 0).timestamp()  # noqa: DTZ001


def test_t1894_one_shot_spend_adds_to_the_totals_and_is_named_apart(
    tmp_path: Path,
    write_stream: Callable[..., Path],
    usage_validator: Any,
    result: Callable[..., dict[str, Any]],
) -> None:
    write_stream(tmp_path / "aaaaaaaa-0", "plan", [result(1.0, "s-a")], NOW)
    rows = [{"at": YESTERDAY, "cost_usd": 0.25}, {"at": NOW, "cost_usd": 0.125}]
    (tmp_path / LEDGER).write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = usage_summary(tmp_path, now=NOW)
    usage_validator.validate(out)
    assert out["cost"]["oneshot_usd"] == 0.375
    assert out["cost"]["today_usd"] == 1.125
    assert out["cost"]["total_usd"] == 1.375
    assert [t["id"] for t in out["cost"]["per_task"]] == ["aaaaaaaa-0"]


def test_t1894_without_one_shots_the_cost_block_is_unchanged(tmp_path: Path, usage_validator: Any) -> None:
    out = usage_summary(tmp_path, now=NOW)
    usage_validator.validate(out)
    assert "oneshot_usd" not in out["cost"]
