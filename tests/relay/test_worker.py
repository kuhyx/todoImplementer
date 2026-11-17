"""Guard 8 (fail closed, visible, retried), serving end to end on the fake RTDB, the heartbeat."""

import asyncio
import threading
from pathlib import Path
from typing import Any, cast

import pytest
from crdt_sync import E2eLockedError
from httpfakes import FakeBackend
from relayfakes import DEV, RIDS, ROOT, answer, board_handlers, req
from rtdb_relay.rtdb import Rtdb
from rtdb_relay.seal import pruned
from rtdb_relay.tests._fake_rtdb import DB, TEST_KEY, FakeRtdb
from todoimpl.credits import marks
from todoimpl.http.routes import Router
from todoimpl.relay import worker
from todoimpl.relay.connect import Endpoint, RelaySetupError
from todoimpl.relay.presence import Heart
from todoimpl.relay.status import NOTIFY, STATUS

PW = "pw"


class StopLoopError(Exception):
    pass


class FakeEndpoint:
    """connect.Endpoint over the fake's transport."""

    def __init__(self, fake: FakeRtdb) -> None:
        self.fake = fake

    def client(self, root: str = "", sealer: Any = None) -> Rtdb:
        async def token() -> str:
            return self.fake.token

        return Rtdb(DB, token, client=self.fake.client(), root=root, sealer=sealer)


class Key:
    master = TEST_KEY


def stopper(delays: list[float], after: int) -> Any:
    async def sleep(seconds: float) -> None:
        delays.append(seconds)
        if len(delays) >= after:
            raise StopLoopError

    return sleep


def test_guard8_no_session_writes_nothing_and_says_why(
    fake: FakeRtdb, router: Router, tmp_path: Path
) -> None:
    def no_session() -> Any:
        raise RelaySetupError("no Firebase sign-in in ~/.config/todoImplementer/firebase_auth.json")

    delays: list[float] = []
    with pytest.raises(StopLoopError):
        asyncio.run(
            worker.run_forever(
                worker.Wiring(router, "b", tmp_path, endpoint=no_session, sleep=stopper(delays, 4))
            )
        )
    assert delays == [5.0, 15.0, 60.0, 60.0]
    assert STATUS.cause is not None
    assert "firebase_auth.json" in STATUS.cause
    assert fake.raw == {}
    alert = marks.active_alert(tmp_path, 100.0)
    assert alert is not None
    assert alert["kind"] == "relay"


def test_guard8_wrong_password_serves_nothing(
    fake: FakeRtdb, router: Router, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def wrong(raw: Any, secret: str, layout: Any) -> Any:
        raise E2eLockedError("wrong passphrase")

    monkeypatch.setattr(worker, "unlock", wrong)
    fake.set(f"{ROOT}/requests/{RIDS[0]}/req", req("snapshot_refresh", {}))
    delays: list[float] = []
    with pytest.raises(StopLoopError):
        asyncio.run(
            worker.run_forever(
                worker.Wiring(
                    router,
                    "b",
                    tmp_path,
                    endpoint=lambda: FakeEndpoint(fake),  # type: ignore[arg-type,return-value]
                    secret=lambda: "nope",
                    sleep=stopper(delays, 1),
                )
            )
        )
    assert STATUS.cause == "wrong passphrase"
    assert fake.get(f"{ROOT}/requests/{RIDS[0]}/result") is None
    assert fake.get(f"{ROOT}/meta") is None


def test_serves_publishes_and_beats_then_reports_a_failure(
    fake: FakeRtdb, router: Router, backend: FakeBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def right(raw: Any, secret: str, layout: Any) -> Key:
        assert secret == PW
        return Key()

    monkeypatch.setattr(worker, "unlock", right)
    STATUS.fail("stale cause")

    async def go() -> None:
        ready = asyncio.Event()
        task = asyncio.create_task(
            worker.serve(
                cast("Endpoint", FakeEndpoint(fake)),
                "pw",
                worker.Wiring(router, "b9", tmp_path),
                worker="w1",
                ready=ready,
            )
        )
        await asyncio.wait_for(ready.wait(), 5)
        assert STATUS.cause is None
        assert str(NOTIFY.cause).startswith("no Firebase service-account key at ")  # HOME is a scratch dir
        db = FakeEndpoint(fake).client(ROOT, fake.sealer)
        await db.put(f"requests/{RIDS[0]}/req", req("task_detail", {"card": backend.task_id}))
        for _ in range(300):
            if fake.get(f"{ROOT}/requests/{RIDS[0]}/result") and fake.get(f"{ROOT}/snap/board"):
                break
            await asyncio.sleep(0.01)
        await db.aclose()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(go())
    result = fake.get(f"{ROOT}/requests/{RIDS[0]}/result")
    assert result["ok"] is True
    assert result["data"]["card"]["id"] == backend.task_id
    assert fake.get(f"{ROOT}/snap/board") == pruned(backend.board_data)
    beat = fake.get(f"{ROOT}/presence/workers/w1")
    assert (beat["build"], beat["lanes"]) == ("b9", {"read": 0})  # act is null, which RTDB drops


def test_a_ready_relay_that_fails_retries_soon(
    router: Router, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def flaky(*args: Any, ready: asyncio.Event, **kw: Any) -> None:
        ready.set()
        raise ExceptionGroup("tasks", [OSError("network down")])

    monkeypatch.setattr(worker, "serve", flaky)
    delays: list[float] = []
    with pytest.raises(StopLoopError):
        asyncio.run(
            worker.run_forever(
                worker.Wiring(
                    router,
                    "b",
                    tmp_path,
                    endpoint=lambda: None,  # type: ignore[arg-type,return-value]
                    secret=lambda: "pw",
                    sleep=stopper(delays, 2),
                )
            )
        )
    assert delays == [5.0, 5.0]
    assert STATUS.cause == "network down"


def test_cause_of_names_a_silent_error() -> None:
    assert worker.cause_of(ExceptionGroup("g", [ValueError()])) == "ValueError"


def test_notify_test_without_a_key_is_disabled(fake: FakeRtdb, router: Router) -> None:
    fake.set(
        f"{ROOT}/presence/clients/{DEV}",
        {"platform": "android", "app": "1", "build": 1, "seen": 1, "fcm": "token-of-the-test-device-0001"},
    )
    [result] = answer(fake, board_handlers(router), [req("notify_test", {})])
    assert (result["ok"], result["code"]) == (False, "disabled")
    assert NOTIFY.cause == "no Firebase service-account key at test"


def test_start_only_with_the_switch(router: Router, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert worker.start(router, build="b", root=tmp_path, env={}) is None
    ran = threading.Event()

    async def fake_forever(*args: Any, **kw: Any) -> None:
        ran.set()

    monkeypatch.setattr(worker, "run_forever", fake_forever)
    thread = worker.start(router, build="b", root=tmp_path, env={"TODOIMPL_RELAY": "1"})
    assert thread is not None
    thread.join(5)
    assert ran.is_set()


def test_overage_alert_wins_over_the_relay(tmp_path: Path) -> None:
    STATUS.fail("x")
    marks.raise_alert(tmp_path, "money", 200.0)
    assert marks.active_alert(tmp_path, 100.0)["kind"] == "overage"  # type: ignore[index]
    STATUS.ok()
    assert marks.active_alert(tmp_path, 300.0) is None


def test_heart_learns_the_skew(fake: FakeRtdb) -> None:
    clock = [fake.now_ms / 1000 - 2]  # the PC is 2 s behind the server

    async def go() -> int:
        db = fake.rtdb()
        heart = Heart(db, "w1", lambda: {"act": None, "read": 0}, release=("1", "b"), now=lambda: clock[0])
        delays: list[float] = []
        with pytest.raises(StopLoopError):
            await heart.run(sleep=stopper(delays, 1))
        await db.aclose()
        return heart.skew_ms

    assert asyncio.run(go()) == 2000
    assert fake.get(f"{ROOT}/presence/workers/w1")["beat"] == fake.now_ms


def test_local_kinds_refresh_and_watch(fake: FakeRtdb, router: Router, backend: FakeBackend) -> None:
    results = answer(
        fake,
        board_handlers(router),
        [
            req("snapshot_refresh", {}),
            req("live_watch", {"card": backend.task_id}),
            req("live_watch", {"card": None}),
        ],
    )
    assert [r["ok"] for r in results] == [True, True, True]
    assert fake.get(f"{ROOT}/snap/usage") == pruned(backend.usage_data)


def test_heart_ignores_an_answer_without_a_beat() -> None:
    class Db:
        async def put(self, path: str, value: object) -> object:
            return None

    heart = Heart(Db(), "w1", dict, release=("1", "b"))  # type: ignore[arg-type]
    asyncio.run(heart.beat())
    assert heart.skew_ms == 0
