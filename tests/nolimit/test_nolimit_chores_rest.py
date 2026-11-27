"""The other chores: visibility cache (T2589), next-turn context and its prompt line (T2590), the rotation."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from nolimitfakes import card_tree, commit, kuhy_repo
from runnerfakes import Env
from todoimpl.nolimit import chores, context, status, tick, visibility
from todoimpl.prompts import nolimitctx

NOW = 1_800_000_000.0


def always() -> bool:
    return True


def cache_file(world: Env) -> Path:
    return world.home / ".cache" / "omniroute_offload" / "visibility.json"


def fake_check_dir(world: Env) -> None:
    """Install a `free-llm-check-dir` that caches every repo it is given as PUBLIC, now."""
    tool = world.bin / visibility.TOOL
    writer = (
        "import json,pathlib,sys,time,subprocess\n"
        f"p=pathlib.Path({str(cache_file(world))!r}); p.parent.mkdir(parents=True,exist_ok=True)\n"
        "c=json.loads(p.read_text()) if p.exists() else {}\n"
        "c['kuhyx/'+pathlib.Path(sys.argv[1]).name]={'visibility':'PUBLIC','at':time.time()}\n"
        "p.write_text(json.dumps(c))\n"
    )
    (world.tmp / "check_dir.py").write_text(writer, encoding="utf-8")
    tool.write_text(f'#!/bin/sh\nexec python3 {world.tmp / "check_dir.py"} "$@"\n', encoding="utf-8")
    tool.chmod(0o755)


def test_t2589_visibility_refreshes_stale_and_missing_entries_only(world: Env) -> None:
    fake_check_dir(world)
    for name in ("alpha", "beta", "gamma"):
        kuhy_repo(world, name, test="true")
    now = time.time()
    cache_file(world).parent.mkdir(parents=True)
    cache_file(world).write_text(json.dumps({
        "kuhyx/alpha": {"visibility": "PRIVATE", "at": now - 2 * 86400},  # lapsed
        "kuhyx/beta": {"visibility": "PUBLIC", "at": now - 60},  # fresh
    }), encoding="utf-8")  # fmt: skip
    report = visibility.run(always, now)  # never-cached first, then the oldest
    assert report == {"refreshed": ["kuhyx/gamma", "kuhyx/alpha"], "failed": [], "stale_left": 0}
    assert visibility.cache()["kuhyx/gamma"]["visibility"] == "PUBLIC"


def test_t2589_visibility_names_a_missing_tool(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(world.bin))
    assert visibility.run(always, NOW) == {"error": f"{visibility.TOOL} is not on PATH", "refreshed": []}


def test_t2590_context_writes_the_next_turn_file_once_per_head(world: Env) -> None:
    kuhy_repo(world, test="true", test_changed="echo 'FAILED tests/test_a.py::test_x' && exit 1")
    tree = card_tree(world, "cccc0001-0")
    commit(tree, "feature.txt", "half done\n", "half of the feature")
    run_dir = world.root / "cccc0001-0"
    assert nolimitctx.pointer(run_dir) == []
    assert context.run(world.root, always, NOW) == {"cards": {"cccc0001-0": "written"}}
    text = context.path(run_dir).read_text(encoding="utf-8")
    assert "half of the feature" in text
    assert "feature.txt" in text
    assert "## Failing tests" in text
    assert "tests/test_a.py::test_x" in text
    assert context.run(world.root, always, NOW) == {"cards": {"cccc0001-0": "current"}}
    commit(tree, "feature.txt", "done\n", "rest of the feature")
    assert context.run(world.root, always, NOW) == {"cards": {"cccc0001-0": "written"}}
    line = "Precomputed while Claude was out (commits, diff, changed-file tests): read {} first."
    assert nolimitctx.pointer(run_dir) == [line.format(context.path(run_dir))]


def test_t2590_the_rotation_runs_one_chore_per_tick_and_records_it(world: Env) -> None:
    kuhy_repo(world, test="true")
    names = [chores.tick(world.root, always, clock=lambda: NOW)[0] for _ in range(5)]
    assert names == ["prune", "rebase", "context", "visibility", "prune"]
    saved = status.load(world.root)
    assert saved["chore_next"] == "rebase"
    assert saved["chores"]["context"] == {"at": NOW, "report": {"cards": {}}}


def test_t2590_cli_runs_one_chore_now(world: Env, capsys: pytest.CaptureFixture[str]) -> None:
    kuhy_repo(world, test="true")
    assert tick.main(["--chore", "rebase"]) == 0
    assert json.loads(capsys.readouterr().out) == {"chore": "rebase", "report": {"cards": {}}}
