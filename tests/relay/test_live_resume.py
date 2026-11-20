"""A reopened feed mirrors only what is new, in few writes (T2345, T2346)."""

import asyncio
from typing import Any

import pytest
from httpfakes import FakeBackend
from relayfakes import DEV, ROOT
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.http.routes import Router
from todoimpl.relay import live as live_mod
from todoimpl.relay.live import Live


def activity(n: int) -> dict[str, Any]:
    return {"type": "activity", "kind": "text", "text": f"line {n}", "seq": n}


def count_writes(db: Any) -> list[str]:
    """Wrap the db's writes under live/; return the list each one appends its method to."""
    writes: list[str] = []
    for name in ("put", "patch", "delete"):
        real = getattr(db, name)

        async def wrapped(path: str, *args: Any, _real: Any = real, _name: str = name, **kw: Any) -> Any:
            if path.startswith("live/"):
                writes.append(_name)
            return await _real(path, *args, **kw)

        setattr(db, name, wrapped)
    return writes


async def open_once(db: Any, lv: Live, card: str) -> None:
    await lv.watch(DEV, card)
    task = lv.mirrors.get(card)
    if task is not None:
        await asyncio.wait_for(task, 5)
    await lv.watch(DEV, None)


def activities(feed: dict[str, Any]) -> list[int]:
    return [v["seq"] for k, v in sorted(feed.items()) if v.get("type") == "activity"]


@pytest.mark.parametrize("restart", [False, True])
def test_t2345_a_reopen_mirrors_only_new_events(
    fake: FakeRtdb, router: Router, backend: FakeBackend, restart: bool
) -> None:
    """Each open replayed the whole events.jsonl into live/{card}: now only events above the stored ones."""
    backend.events = [activity(n) for n in range(1, 31)]
    card = backend.task_id

    async def go() -> list[str]:
        db = fake.rtdb()
        lv = Live(db, router)
        await open_once(db, lv, card)
        backend.events = [activity(n) for n in range(1, 33)]  # two new lines while closed
        lv = Live(db, router) if restart else lv  # a server restart forgets the in-memory floor
        writes = count_writes(db)
        await open_once(db, lv, card)
        await db.aclose()
        return writes

    writes = asyncio.run(go())
    assert activities(fake.get(f"{ROOT}/live/{card}")) == list(range(1, 33))
    assert writes.count("put") + writes.count("patch") <= 2  # the stage snapshot and the two new lines


def test_t2346_a_long_history_lands_in_one_write_and_keeps_the_cap(
    fake: FakeRtdb, router: Router, backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A burst (the replay of a long run) cost one PUT per event plus one DELETE per trimmed key."""
    monkeypatch.setattr(live_mod, "KEEP", 50)
    backend.events = [activity(n) for n in range(1, 501)]
    card = backend.task_id

    async def go() -> list[str]:
        db = fake.rtdb()
        writes = count_writes(db)
        await open_once(db, Live(db, router), card)
        await db.aclose()
        return writes

    writes = asyncio.run(go())
    feed = fake.get(f"{ROOT}/live/{card}")
    assert len(feed) == 50
    assert activities(feed)[-1] == 500
    assert writes.count("put") + writes.count("patch") + writes.count("delete") <= 5
