"""A note added in the todo app reaches the board in under 5 s (DOCS-server.md, T2057)."""

import time

from servicefakes import Rig
from todoimpl.service import TaskCache, board_fetch, cache
from todoimpl.todo_mcp.client import TodoClient

# The todo MCP reuses a Firebase sync for 2 s and a fetch then takes about 0.6 s; the loop adds its interval.
MCP_FRESHNESS_S = 2.0
FETCH_S = 1.0
BUDGET_S = 5.0


def test_t2057_the_refresh_interval_leaves_room_for_the_mcp_freshness_window_and_a_fetch() -> None:
    assert cache.INTERVAL + FETCH_S <= BUDGET_S - MCP_FRESHNESS_S


def test_t2057_a_note_reaches_the_board_within_one_default_interval(rig: Rig) -> None:
    client = TodoClient(rig.fake.url, rig.fake.token)
    board = TaskCache(board_fetch(client, rig.root))
    board.refresh()
    board.start()
    try:
        card = f"{rig.fake.seed(None, 'brand new idea')[:8]}-0"
        started = time.monotonic()
        while time.monotonic() - started < BUDGET_S and not any(c.id == card for c in board.snapshot().tasks):
            time.sleep(0.02)
        assert any(c.id == card for c in board.snapshot().tasks)
        assert time.monotonic() - started < BUDGET_S - MCP_FRESHNESS_S
    finally:
        board.stop()
