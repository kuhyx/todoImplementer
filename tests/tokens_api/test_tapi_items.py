"""/api/tokens/items: cost per todoImplementer item, repo and stage."""

from __future__ import annotations

import json
import shutil
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
import tokfix_tokens as fx
from todoimpl.tokens_api import db, router

if TYPE_CHECKING:
    from pathlib import Path

RUNS = {  # item dir -> (repo, [(stream file, session id)])
    "abcd1234-0": ("alpha", [("implement-100.stream.jsonl", "s1"), ("plan-90.stream.jsonl", "s2")]),
    "ffff0000-1": ("beta", [("plan-80.stream.jsonl", "other")]),
}


@pytest.fixture
def store(sysroot: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(router, "_now", lambda: fx.T0 + 2 * fx.DAY)
    root = sysroot / "runs"
    monkeypatch.setenv("TODOIMPL_HOME", str(root))
    for item, (repo, streams) in RUNS.items():
        (root / item).mkdir(parents=True)
        (root / item / "state.json").write_text(json.dumps({"repo": repo}), encoding="utf-8")
        for name, sid in streams:
            event = json.dumps({"type": "result", "session_id": sid})
            (root / item / name).write_text(event + "\n", encoding="utf-8")
    return fx.build(sysroot / "home/tester" / db.STORE)


def _get(query: str = "") -> tuple[HTTPStatus, dict[str, Any]]:
    return router.handle("/api/tokens/items", query)


def test_cost_is_grouped_by_item_repo_and_stage(store: Path) -> None:
    status, body = _get()
    assert status == HTTPStatus.OK
    assert body["total_usd"] == pytest.approx(10.0)
    assert [(r["stage"], r["usd"], r["sessions"]) for r in body["stages"]] == [
        ("implement", 6.0, 1),
        ("plan", 4.0, 1),
    ]
    assert body["repos"] == [{"repo": "alpha", "sessions": 2, "calls": 4, "usd": 10.0}]
    assert body["items"][0] == {
        "item": "abcd1234-0",
        "repo": "alpha",
        "stage": "implement",
        "sessions": 1,
        "calls": 3,
        "usd": 6.0,
    }
    assert body["filters"]["scope"] == "all"


def test_window_and_cwd_narrow_the_sessions(store: Path) -> None:
    _, body = _get("cwd=/home/tester/src")
    assert body["total_usd"] == pytest.approx(6.0)
    _, body = _get("from=2026-09-29")
    assert [r["stage"] for r in body["stages"]] == ["plan"]


def test_table_params_apply(store: Path) -> None:
    _, body = _get("t.stages.limit=1")
    assert len(body["stages"]) == 1


def test_sessions_without_a_run_are_ignored(store: Path, sysroot: Path) -> None:
    shutil.rmtree(sysroot / "runs/abcd1234-0")
    _, body = _get()
    assert body["total_usd"] == pytest.approx(0.0)
    assert body["items"] == []


def test_handle_refuses_other_prefixes(store: Path) -> None:
    assert router.handle("/api/tokensX", "")[0] == HTTPStatus.NOT_FOUND
    assert router.handle("/api/tokens", "")[0] == HTTPStatus.OK
    assert router.handle("/api/tokens/", "")[0] == HTTPStatus.OK
