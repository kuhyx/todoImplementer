"""A result PUT that fails is retried, and a write kind never runs twice for one rid (T2610, T2611)."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from httpfakes import FakeBackend
from relayfakes import RIDS, ROOT, board_handlers, req, serve_one
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.http.routes import Router
from todoimpl.relay import server as relay_server

RID = RIDS[0]
RESULT = ("PUT", f"/requests/{RID}/result")


async def landed(fake: FakeRtdb, within: float = 2.0) -> dict[str, Any] | None:
    """Return the stored result of RID once it appears, or None after `within` seconds."""
    for _ in range(int(within / 0.01)):
        if isinstance(found := fake.get(f"{ROOT}/requests/{RID}/result"), dict):
            return found
        await asyncio.sleep(0.01)
    return None


def test_t2610_failed_result_put_is_retried_while_the_stream_stays_up(
    fake: FakeRtdb, router: Router, backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(relay_server, "RESCAN_S", 0.05, raising=False)

    async def go() -> dict[str, Any] | None:
        db = fake.rtdb()
        srv = relay_server.RelayServer(db, "pc", board_handlers(router)(db))
        fake.fail[RESULT] = 503
        task = asyncio.create_task(srv.run())
        fake.set(f"{ROOT}/requests/{RID}/req", req("task_go", {"card": backend.task_id, "args": {}}))
        for _ in range(200):  # the handler ran and its result PUT was refused
            if RESULT in fake.log:
                break
            await asyncio.sleep(0.01)
        del fake.fail[RESULT]  # RTDB is back; no new event arrives on requests/
        result = await landed(fake)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await db.aclose()
        return result

    result = asyncio.run(go())
    assert result is not None, "the refused result was never written again"
    assert result["ok"] is True
    # the retry is answered from the done-log: the click ran once
    assert [c for c in backend.calls if c[0] == "go"] == [("go", backend.task_id)]


def test_t2611_a_restarted_worker_answers_a_done_rid_without_running_it_again(
    fake: FakeRtdb, router: Router, backend: FakeBackend, tmp_path: Path
) -> None:
    done = tmp_path / "relay" / "done.jsonl"

    async def go() -> dict[str, Any]:
        fake.set(f"{ROOT}/requests/{RID}/req", req("task_go", {"card": backend.task_id, "args": {}}))
        db = fake.rtdb()
        first = relay_server.RelayServer(db, "pc", board_handlers(router)(db), done=done)
        fake.fail[RESULT] = 503
        with pytest.raises(Exception, match="503"):
            await serve_one(first, fake, RID)
        del fake.fail[RESULT]
        again = relay_server.RelayServer(db, "pc", board_handlers(router)(db), done=done)  # a new process
        result = await serve_one(again, fake, RID)
        await db.aclose()
        return result

    result = asyncio.run(go())
    assert result["ok"] is True
    assert [c for c in backend.calls if c[0] == "go"] == [("go", backend.task_id)]
