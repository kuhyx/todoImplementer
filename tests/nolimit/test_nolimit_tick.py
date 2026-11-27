"""The tick visits one repo per call while the trigger holds; the server loop and the CLI around it."""

from __future__ import annotations

import json
import runpy
import sys
import threading
from pathlib import Path

import pytest
from nolimitfakes import kuhy_repo, park
from runnerfakes import Env
from todoimpl.nolimit import status, tick


def up() -> bool:
    return False  # the gateway is down


def test_t2547_one_repo_per_tick_in_a_cycle(world: Env) -> None:
    root = world.root
    kuhy_repo(world, "alpha", test="true")
    kuhy_repo(world, "beta", test="exit 1")
    assert tick.tick(root, gateway_up=up) is None  # nothing limits the plan
    assert status.view(root)["active"] is False
    park(root, "aaaa1111-0")
    assert tick.tick(root, gateway_up=up, push=False) == status.GREEN
    assert tick.tick(root, gateway_up=up, push=False) == status.RED
    assert status.view(root) == {
        "active": True,
        "repo": "beta",
        "result": "red",
        "at": status.view(root)["at"],
    }
    assert tick.tick(root, gateway_up=up, push=False) == status.GREEN  # a new cycle starts with alpha
    assert status.load(root)["cycle"] == ["alpha"]


def test_a_limited_board_with_no_repos_rests(world: Env) -> None:
    park(world.root, "aaaa1111-0")
    assert tick.tick(world.root, gateway_up=up) is None
    assert status.view(world.root) == {"active": True, "repo": None, "result": None, "at": None}


def test_the_loop_ticks_until_stopped_and_survives_a_failed_tick(tmp_path: Path) -> None:
    calls: list[Path] = []
    done = threading.Event()

    def step(root: Path) -> None:
        calls.append(root)
        if len(calls) == 1:
            raise RuntimeError("boom")
        loop.stop()
        done.set()

    loop = tick.Loop(tmp_path, interval=0.01, step=step)
    loop.start()
    assert done.wait(5)
    assert calls == [tmp_path, tmp_path]


def test_the_cli_visits_a_named_repo_without_the_trigger(
    world: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    kuhy_repo(world, test="true")
    assert tick.main(["--repo", "demo", "--once", "--no-push"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["repo"], out["result"]) == ("demo", "green")
    assert out["branch_dir"].endswith("/nolimit/demo")
    assert tick.main(["--repo", "missing", "--once"]) == 1
    assert "no checkout" in json.loads(capsys.readouterr().out)["error"]


def test_the_cli_tick_and_loop_ask_the_trigger(
    world: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert tick.main(["--once"]) == 0
    assert json.loads(capsys.readouterr().out) == {"result": None}
    seen: list[tuple[Path, bool]] = []
    monkeypatch.setattr(tick, "tick", lambda root, push: seen.append((root, push)))
    monkeypatch.setattr(tick.Loop, "run_forever", lambda self: self._step(self.root))
    assert tick.main(["--no-push"]) == 0
    assert seen == [(world.root, False)]


def test_status_ignores_bad_files_and_odd_last_rows(tmp_path: Path) -> None:
    (tmp_path / status.FILE).write_text("[]", encoding="utf-8")
    assert status.view(tmp_path)["active"] is False
    assert status.pick(tmp_path, []) is None
    (tmp_path / status.FILE).write_text(json.dumps({"last": "x"}), encoding="utf-8")
    assert status.view(tmp_path)["repo"] is None
    bad = {"last": {"repo": "a", "result": "weird", "at": 1}, "active": True}
    (tmp_path / status.FILE).write_text(json.dumps(bad), encoding="utf-8")
    assert status.view(tmp_path) == {"active": True, "repo": None, "result": None, "at": None}
    status.set_active(tmp_path, active=True)  # unchanged: not written again
    assert json.loads((tmp_path / status.FILE).read_text(encoding="utf-8")) == bad


def test_the_module_runs_as_a_program(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["tick", "--once"])
    monkeypatch.delitem(sys.modules, "todoimpl.nolimit.tick")
    with pytest.raises(SystemExit) as exited:
        runpy.run_module("todoimpl.nolimit.tick", run_name="__main__")
    assert exited.value.code == 0
