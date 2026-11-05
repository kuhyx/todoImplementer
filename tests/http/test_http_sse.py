"""SSE framing, replay filter, heartbeat and disconnect handling."""

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
from todoimpl.http.sse import KEEPALIVE, frame, stream

SNAPSHOT = {"type": "stage", "stage": "plan"}


def test_frame_with_seq_has_id() -> None:
    out = frame({"type": "activity", "seq": 7, "text": "é"}).decode()
    assert out.startswith("id: 7\nevent: activity\ndata: ")
    assert out.endswith("\n\n")
    assert "é" in out


def test_frame_without_seq_has_no_id() -> None:
    assert frame({"type": "cost", "cost_usd": 1}).decode().startswith("event: cost\ndata: ")


def collect(events: Iterator[dict[str, Any]], last_seq: int = 0, heartbeat: float = 1.0) -> list[bytes]:
    out: list[bytes] = []
    stream(out.append, SNAPSHOT, events, last_seq, heartbeat)
    return out


def test_snapshot_first_then_events_in_order() -> None:
    evs: Iterator[dict[str, Any]] = iter(
        [{"type": "activity", "seq": 1}, {"type": "done", "status": "needs_you"}]
    )
    out = collect(evs)
    assert out[0] == frame(SNAPSHOT)
    assert out[1:] == [frame({"type": "activity", "seq": 1}), frame({"type": "done", "status": "needs_you"})]


def test_replayed_activity_up_to_last_event_id_is_skipped() -> None:
    evs = iter(
        [{"type": "activity", "seq": 2}, {"type": "activity", "seq": 3}, {"type": "cost", "cost_usd": 2}]
    )
    out = collect(evs, last_seq=2)
    assert out[1:] == [frame({"type": "activity", "seq": 3}), frame({"type": "cost", "cost_usd": 2})]


def test_idle_source_gets_keepalive_comments() -> None:
    release = threading.Event()

    def slow() -> Iterator[dict[str, Any]]:
        release.wait(2)
        yield {"type": "done", "status": "done"}

    out: list[bytes] = []

    def write(chunk: bytes) -> None:
        out.append(chunk)
        if chunk == KEEPALIVE and out.count(KEEPALIVE) == 2:
            release.set()

    stream(write, SNAPSHOT, slow(), 0, 0.05)
    assert out.count(KEEPALIVE) >= 2
    assert out[-1] == frame({"type": "done", "status": "done"})


def test_keepalive_is_an_sse_comment() -> None:
    assert KEEPALIVE.startswith(b":")
    assert KEEPALIVE.endswith(b"\n\n")


def test_failing_source_ends_the_stream_quietly() -> None:
    def boom() -> Iterator[dict[str, Any]]:
        yield {"type": "cost", "cost_usd": 1}
        raise RuntimeError("source died")

    out = collect(boom())
    assert out == [frame(SNAPSHOT), frame({"type": "cost", "cost_usd": 1})]


def test_client_disconnect_propagates_and_stops_the_pump() -> None:
    stopped = threading.Event()

    def endless() -> Iterator[dict[str, Any]]:
        try:
            while True:
                yield {"type": "cost", "cost_usd": 1}
                time.sleep(0.01)
        finally:
            stopped.set()

    def write(chunk: bytes) -> None:
        raise BrokenPipeError

    with pytest.raises(BrokenPipeError):
        stream(write, SNAPSHOT, endless(), 0, 0.05)
    assert stopped.wait(2)
