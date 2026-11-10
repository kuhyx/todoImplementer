"""T1910: /api/usage read every stream of every run on each request (340k events, 10 s under load)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl.usage import cost, events, summary, usage_summary

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


def test_t1910_an_unchanged_stream_is_read_once_across_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_stream: Callable[..., Path],
    rate: Callable[..., dict[str, Any]],
    result: Callable[..., dict[str, Any]],
) -> None:
    read: list[Path] = []
    real = events.iter_events

    def counting(path: Path) -> Any:
        read.append(path)
        return real(path)

    monkeypatch.setattr(cost, "iter_events", counting)
    monkeypatch.setattr(summary, "iter_events", counting)
    run = tmp_path / "abcd1234-0"
    write_stream(run, "plan", [rate(), result(0.25, "s-a")])
    first = usage_summary(tmp_path, now=1.0)
    reads = len(read)
    assert reads == 2  # one pass for the costs, one for the rate limits
    assert usage_summary(tmp_path, now=1.0) == first
    assert len(read) == reads
    write_stream(run, "plan", [rate(), result(0.25, "s-a"), result(0.5, "s-b")])
    assert usage_summary(tmp_path, now=1.0)["cost"]["total_usd"] == 0.75  # the file changed: read again
    assert len(read) == reads + 2


def test_the_memo_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events, "MEMO_MAX", 1)
    one, two = tmp_path / "1", tmp_path / "2"
    one.write_text("a")
    two.write_text("b")
    assert events.per_file("t", one, lambda p: p.read_text()) == "a"
    assert events.per_file("t", two, lambda p: p.read_text()) == "b"
    assert len(events._MEMO) == 1
