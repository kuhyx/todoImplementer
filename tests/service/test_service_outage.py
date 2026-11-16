"""T2005: the board names an unreachable todo MCP plainly, once, without the exception type."""

import pytest
from servicefakes import Rig
from todoimpl.http.backend import BackendError
from todoimpl.service.cache import TaskCache
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.model import TodoError, UnreachableError

NOT_ANSWERING = "todo MCP not answering (timeout)"


def _down() -> list[CardTask]:
    raise UnreachableError(NOT_ANSWERING)


def test_t2005_never_loaded_board_says_not_answering(rig: Rig) -> None:
    rig.backend.cache = TaskCache(_down)
    rig.backend.cache.refresh()
    with pytest.raises(BackendError) as err:
        rig.backend.board()
    assert (err.value.code, err.value.message) == ("upstream_unavailable", NOT_ANSWERING)


def test_t2005_stale_board_banner_says_not_answering(rig: Rig) -> None:
    cache = TaskCache(list)
    rig.backend.cache = cache
    cache.refresh()
    cache._fetch = _down
    cache.refresh()
    assert rig.backend.board()["error"] == {"code": "upstream_unavailable", "message": NOT_ANSWERING}


def test_t2005_other_todo_errors_keep_their_type_and_source(rig: Rig) -> None:
    def broken() -> list[CardTask]:
        raise TodoError("bad reply")

    rig.backend.cache = TaskCache(broken)
    rig.backend.cache.refresh()
    with pytest.raises(BackendError, match=r"^todo MCP: TodoError: bad reply$"):
        rig.backend.board()


def test_t2005_a_failed_action_says_not_answering_once(rig: Rig) -> None:
    rig.scheduler.failure = UnreachableError(NOT_ANSWERING)
    with pytest.raises(BackendError) as err:
        rig.backend.ship("t1")
    assert (err.value.code, err.value.message) == ("upstream_unavailable", NOT_ANSWERING)
