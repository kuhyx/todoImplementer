"""T2005: a wedged todo MCP must cost one connection, then a ladder, never one socket per poll."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fake_todo_mcp import FakeTodoMcp
from todoimpl.service.cache import TaskCache
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.model import TodoError

POLLS = 6
TIMEOUT = 0.3
NOT_ANSWERING = "todo MCP not answering (timeout)"


class Clock:
    """A settable clock for the backoff gate."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _poll(client: TodoClient) -> str | None:
    """One board poll; returns the error text, None when it worked."""
    try:
        client.list_tasks()
    except TodoError as exc:
        return str(exc)
    return None


def test_t2005_polls_during_one_hang_open_one_connection(fake: FakeTodoMcp) -> None:
    fake.hang()
    client = TodoClient(fake.url, fake.token, TIMEOUT)

    def fetch() -> list[CardTask]:
        client.list_tasks()
        return []

    cache = TaskCache(fetch)
    snaps = [cache.refresh() for _ in range(POLLS)]
    assert fake.connections == 1
    assert {snap.error for snap in snaps} == {NOT_ANSWERING}


def test_t2005_parallel_polls_during_one_hang_open_one_connection(fake: FakeTodoMcp) -> None:
    client = TodoClient(fake.url, fake.token, TIMEOUT)
    client.list_tasks()  # a healthy session first: the hang then hits tools/call
    seen = fake.connections
    fake.hang()
    with ThreadPoolExecutor(POLLS) as pool:
        errors = list(pool.map(lambda _: _poll(client), range(POLLS)))
    assert fake.connections - seen == 1
    assert errors == [NOT_ANSWERING] * POLLS


def test_t2005_cache_refresh_in_flight_is_not_repeated() -> None:
    started, gate = threading.Event(), threading.Event()
    calls: list[int] = []

    def fetch() -> list[CardTask]:
        calls.append(1)
        started.set()
        gate.wait(5)
        return []

    cache = TaskCache(fetch)
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(cache.refresh)
        assert started.wait(5)
        assert [cache.refresh().error for _ in range(POLLS)] == ["notes not loaded yet"] * POLLS
        gate.set()
        assert running.result(5).error is None
    assert calls == [1]


def test_t2005_backs_off_on_the_ladder_then_recovers(fake: FakeTodoMcp) -> None:
    clock = Clock()
    client = TodoClient(fake.url, fake.token, TIMEOUT, clock=clock)
    fake.hang()
    assert _poll(client) == NOT_ANSWERING  # failure 1: next try in 60 s
    fake.release()
    clock.now += 59
    assert _poll(client) == NOT_ANSWERING
    assert fake.connections == 1  # the gate answered, no socket
    fake.hang()
    clock.now += 2
    assert _poll(client) == NOT_ANSWERING  # failure 2: next try in 120 s
    assert fake.connections == 2
    clock.now += 61
    assert _poll(client) == NOT_ANSWERING
    assert fake.connections == 2
    fake.release()
    clock.now += 60
    assert _poll(client) is None  # answers again: the ladder resets
    fake.hang()
    clock.now += 1
    assert _poll(client) == NOT_ANSWERING
    clock.now += 61
    fake.release()
    assert _poll(client) is None


def test_t2005_a_403_after_timeouts_is_not_a_token_verdict(fake: FakeTodoMcp) -> None:
    clock = Clock()
    client = TodoClient(fake.url, fake.token, TIMEOUT, clock=clock)
    fake.hang()
    assert _poll(client) == NOT_ANSWERING
    fake.release()
    clock.now += 61
    fake.fail_next(403)
    assert _poll(client) == "todo MCP not answering (HTTP 403 after timeouts)"


def test_a_403_on_a_healthy_server_still_says_token_rejected(fake: FakeTodoMcp) -> None:
    fake.fail_next(403)
    assert _poll(TodoClient(fake.url, fake.token, TIMEOUT)) == "MCP server answered HTTP 403 (token rejected)"


@pytest.mark.parametrize("status", [500, 502])
def test_server_errors_during_an_outage_back_off_too(fake: FakeTodoMcp, status: int) -> None:
    clock = Clock()
    client = TodoClient(fake.url, fake.token, TIMEOUT, clock=clock)
    fake.hang()
    _poll(client)
    fake.release()
    clock.now += 61
    fake.fail_next(status)
    assert _poll(client) == f"todo MCP not answering (HTTP {status} after timeouts)"
    seen = fake.connections
    assert _poll(client) == f"todo MCP not answering (HTTP {status} after timeouts)"
    assert fake.connections == seen
