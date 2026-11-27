"""Guards 1-7 (DOCS-native-app-relay.md): each refusal happens before the backend is touched."""

import asyncio
import base64
import itertools
from typing import Any

import pytest
from httpfakes import FakeBackend
from relayfakes import DEV, RIDS, ROOT, answer, board_handlers, req, serve_one
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.http import newtask
from todoimpl.http.routes import Router
from todoimpl.relay import donelog
from todoimpl.relay import server as relay_server


def test_guard1_unknown_kind_runs_nothing(fake: FakeRtdb, router: Router, backend: FakeBackend) -> None:
    [result] = answer(fake, board_handlers(router), [req("shell", {"cmd": "rm -rf /"})])
    assert result["code"] == "unknown_kind"
    assert backend.calls == []


@pytest.mark.parametrize(
    "bad",
    [
        req("task_start", {"args": {}}),  # no card
        req("task_start", {"card": "nope", "args": {}}),
        req("task_start", {"card": "abcd1234-0", "args": []}),
        req("task_go", {"card": "abcd1234-0", "args": {}}, dev="pc"),  # device ids are per-install uuids
        req("task_go", {"card": "abcd1234-0", "args": {}}, extra=True),
        {k: v for k, v in req("task_go", {"card": "abcd1234-0", "args": {}}).items() if k != "dev"},
        req("task_go", {"card": "abcd1234-0", "args": {}}, sent_at="now"),
        req("task_go", {"card": "abcd1234-0", "args": {}}, created=True),
        req("task_go", "not an object"),  # type: ignore[arg-type]
        req("task_detail", {"card": "abcd1234-0", "extra": 1}),
        req("merge_merge", {"group": "0123456789ab", "args": {"extra": 1}}),
        req("merge_dismiss", {"group": "XYZ", "args": {}}),
        req("tokens", {"path": "/../etc", "query": ""}),
        req("tokens", {"path": "", "query": "x" * 2001}),
        req("task_shot", {"card": "abcd1234-0", "name": "a.jpg"}),
        req("task_shot", {"card": "abcd1234-0", "name": "a" * 200 + ".png"}),
        req("umbrella_log", {"card": "abcd1234-0", "log": "a/b"}),
        req("live_watch", {"card": 7}),
        req("snapshot_refresh", {"x": 1}),
        req("credits_fallback", {"args": 1}),
    ],
)
def test_guard2_schema_first(
    fake: FakeRtdb, router: Router, backend: FakeBackend, bad: dict[str, Any]
) -> None:
    [result] = answer(fake, board_handlers(router), [bad])
    assert result["ok"] is False
    assert result["code"] == "bad_request"
    assert backend.calls == []


def test_guard2_args_are_checked_by_the_route(fake: FakeRtdb, router: Router, backend: FakeBackend) -> None:
    card = backend.task_id
    results = answer(
        fake,
        board_handlers(router),
        [
            req("task_ship", {"card": card, "args": {"auto_ship": True}}),
            req("task_send", {"card": card, "args": {}}),
        ],
    )
    assert [r["code"] for r in results] == ["bad_request"] * 2
    assert backend.calls == []


def test_guard3_unsealed_request_never_runs(fake: FakeRtdb, router: Router, backend: FakeBackend) -> None:
    async def go() -> dict[str, Any]:
        db = fake.rtdb()
        srv = relay_server.RelayServer(db, "pc", board_handlers(router)(db))
        fake.raw_set(f"{ROOT}/requests/{RIDS[0]}/req", req("task_go", {"card": backend.task_id, "args": {}}))
        result = await serve_one(srv, fake, RIDS[0])
        await db.aclose()
        return result

    assert asyncio.run(go())["code"] == "unsealed"
    assert backend.calls == []


def test_guard4_disabled_action_is_refused_with_its_reason(
    fake: FakeRtdb, router: Router, backend: FakeBackend
) -> None:
    backend.task_data["card"]["actions"][0] = {
        "id": "start",
        "label": "Start",
        "enabled": False,
        "reason": "busy",
    }
    [result] = answer(
        fake, board_handlers(router), [req("task_start", {"card": backend.task_id, "args": {}})]
    )
    assert (result["code"], result["error"]) == ("disabled", "busy")
    assert backend.calls == []


def test_guard5_a_replayed_rid_gets_its_first_answer(
    fake: FakeRtdb, router: Router, backend: FakeBackend
) -> None:
    async def go() -> list[dict[str, Any]]:
        db = fake.rtdb()
        srv = relay_server.RelayServer(db, "pc", board_handlers(router)(db))
        fake.set(f"{ROOT}/requests/{RIDS[0]}/req", req("task_go", {"card": backend.task_id, "args": {}}))
        first = await serve_one(srv, fake, RIDS[0])
        fake.raw_set(f"{ROOT}/requests/{RIDS[0]}/result", None)  # the result is gone, the rid comes back
        fake.raw_set(f"{ROOT}/requests/{RIDS[0]}/claim", None)
        second = await serve_one(srv, fake, RIDS[0])
        await db.aclose()
        return [first, second]

    first, second = asyncio.run(go())
    assert first["ok"] is True
    assert second == first
    assert backend.calls == [("go", backend.task_id)]


def test_guard5_an_old_request_expires(fake: FakeRtdb, router: Router, backend: FakeBackend) -> None:
    old = req("task_go", {"card": backend.task_id, "args": {}})
    old["sent_at"] -= 25 * 3600 * 1000
    [result] = answer(fake, board_handlers(router), [old])
    assert result["code"] == "expired"
    assert backend.calls == []


def test_guard6_writes_are_capped_per_minute_reads_are_not(
    fake: FakeRtdb, router: Router, backend: FakeBackend
) -> None:
    writes = [req("task_go", {"card": backend.task_id, "args": {}}) for _ in range(31)]
    reads = [req("task_detail", {"card": backend.task_id}) for _ in range(5)]
    results = answer(fake, board_handlers(router), writes + reads)
    assert [r["ok"] for r in results[:30]] == [True] * 30
    assert (results[30]["code"], results[30]["retry"]) == ("rate_limited", True)
    assert all(r["ok"] for r in results[31:])
    assert len(backend.calls) == 30


def test_guard6_the_cap_frees_after_a_minute(fake: FakeRtdb, router: Router, backend: FakeBackend) -> None:
    ticks = itertools.count(1_000.0, 1.0)  # every clock read is one second later
    writes = [req("task_go", {"card": backend.task_id, "args": {}}, sent_at=1_000_000) for _ in range(31)]
    results = answer(fake, board_handlers(router), writes, now=lambda: next(ticks))
    assert all(r["ok"] for r in results)


def test_guard7_oversized_request_and_answer(fake: FakeRtdb, router: Router, backend: FakeBackend) -> None:
    backend.shots["big.png"] = b"\x89PNG" + b"0" * (4 * 1024 * 1024)
    results = answer(
        fake,
        board_handlers(router),
        [
            req(
                "task_spec_answers",
                {"card": backend.task_id, "args": {"answers": {"Q1": "x" * (300 * 1024)}}},
            ),
            req("task_shot", {"card": backend.task_id, "name": "big.png"}),
        ],
    )
    assert results[0]["code"] == "bad_request"
    assert results[0]["error"] == "request over 256 KB"  # the relay refused it, not the route
    assert results[1]["code"] == "too_large"
    assert [c for c in backend.calls if c[0] == "spec_answers"] == []


def test_t2322_a_send_with_an_inline_image_gets_the_new_task_cap(
    fake: FakeRtdb, router: Router, backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(newtask, "MAX_BODY", 1024 * 1024)  # the 40 MB cap, scaled down
    shot = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * (300 * 1024)).decode()
    args = {"text": "see [Image #1]", "images": [{"data_b64": shot}]}
    sent, big = answer(
        fake,
        board_handlers(router),
        [
            req("task_send", {"card": backend.task_id, "args": args}),
            req("task_send", {"card": backend.task_id, "args": {"text": "x" * 2**21}}),
        ],
    )
    assert sent["ok"], sent
    assert backend.calls[0][:3] == ("send", backend.task_id, "see [Image #1]")
    assert big["error"] == "request over 1024 KB"


def test_device_reaches_the_handler(fake: FakeRtdb) -> None:
    seen: list[str] = []

    async def who(body: dict[str, Any]) -> dict[str, Any]:
        seen.append(relay_server.CURRENT.get()["dev"])
        return {}

    answer(fake, lambda _db: {"snapshot_refresh": who}, [req("snapshot_refresh", {})])
    assert seen == [DEV]


def test_only_the_newest_answers_are_kept(
    fake: FakeRtdb, router: Router, backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(donelog, "KEPT", 1)
    results = answer(fake, board_handlers(router), [req("task_detail", {"card": backend.task_id})] * 2)
    assert all(r["ok"] for r in results)
