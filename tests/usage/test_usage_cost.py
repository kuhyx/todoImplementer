from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from todoimpl.usage import task_cost
from todoimpl.usage.events import iter_events, stream_files

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def test_task_cost_sums_every_result_event_across_streams(
    tmp_path: Path,
    write_stream: Callable[..., Path],
    rate: Callable[..., dict[str, Any]],
    result: Callable[..., dict[str, Any]],
) -> None:
    write_stream(tmp_path, "plan", [rate(), result(0.25, "s-a"), {"type": "assistant"}, result(0.5, "s-b")])
    write_stream(tmp_path, "implement", [result(1, "s-c")])
    (tmp_path / "state.json").write_text('{"total_cost_usd": 99}')
    assert task_cost(tmp_path) == 1.75


def test_task_cost_ignores_garbage_and_non_numeric_cost(
    tmp_path: Path, write_stream: Callable[..., Path], result: Callable[..., dict[str, Any]]
) -> None:
    write_stream(
        tmp_path,
        "a",
        [
            "",
            "not json",
            "[1, 2]",
            '{"type": "result"}',
            '{"type": "result", "total_cost_usd": "7"}',
            result(0.1),
        ],
    )
    assert task_cost(tmp_path) == 0.1


def test_task_cost_empty_or_missing_dir_is_zero(tmp_path: Path) -> None:
    assert task_cost(tmp_path) == 0.0
    assert task_cost(tmp_path / "nope") == 0.0


def test_iter_events_survives_unreadable_path(tmp_path: Path) -> None:
    bad = tmp_path / "x.stream.jsonl"
    bad.mkdir()
    assert list(iter_events(bad)) == []
    assert stream_files(tmp_path) == [bad]


def test_t401_resumed_session_cost_is_cumulative_not_summed(
    tmp_path: Path, write_stream: Callable[..., Path], result: Callable[..., dict[str, Any]]
) -> None:
    first, resumed = result(0.0130), result(0.0140)
    other = result(0.5, "s-2")
    write_stream(tmp_path, "plan", [first, resumed])
    write_stream(
        tmp_path,
        "implement",
        [other, result(0.75, "s-2"), {"type": "result", "total_cost_usd": 1}],
    )
    assert task_cost(tmp_path) == pytest.approx(0.0140 + 0.75 + 1)
