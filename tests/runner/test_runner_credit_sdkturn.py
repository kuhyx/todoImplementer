"""sdkturn in-process against the fake `claude_agent_sdk` (tests/shims), which plays the fake claude CLI."""

import json
import runpy
from pathlib import Path
from typing import Any

import pytest
from runnerfakes import Env
from todoimpl.runner import sdkturn


def spec(world: Env, **over: Any) -> str:
    cwd = world.tmp / "abcd1234-0" / "wt"
    cwd.mkdir(parents=True, exist_ok=True)
    base = {
        "prompt": "do it", "model": "sonnet", "cwd": str(cwd), "add_dirs": [str(cwd)],
        "permission_mode": "acceptEdits", "resume": None, "settings": None,
        "allowed_tools": ["Bash(ls:*)"], "disallowed_tools": ["Bash(git push:*)"],
        "setting_sources": ["user", "project", "local"],
    }  # fmt: skip
    return json.dumps({**base, **over})


def lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    return [json.loads(x) for x in capsys.readouterr().out.splitlines()]


def options(world: Env) -> list[dict[str, Any]]:
    log = world.fake / "sdk_options.jsonl"
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]


def test_a_turn_prints_the_cli_stream_and_passes_the_options(
    world: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    world.script("abcd1234", {"_fake": "text", "text": "hi"}, {"_fake": "result", "text": "ok\n\nD: done"})
    assert sdkturn.main([spec(world, resume="sess-9")]) == 0
    out = lines(capsys)
    assert [x["type"] for x in out] == ["system", "assistant", "result"]
    assert out[0]["session_id"] == "sess-9"  # the stream shape is the CLI's own: init first
    assert out[-1]["result"] == "ok\n\nD: done"
    (opt,) = options(world)
    assert opt["model"] == "sonnet"
    assert opt["resume"] == "sess-9"
    assert opt["permission_mode"] == "acceptEdits"
    assert opt["allowed_tools"] == ["Bash(ls:*)"]
    assert opt["disallowed_tools"] == ["Bash(git push:*)"]
    assert opt["setting_sources"] == ["user", "project", "local"]
    assert opt["system_prompt"] == {"type": "preset", "preset": "claude_code"}
    assert opt["prompt"] == "do it"


def test_t1986_mcp_servers_and_strictness_reach_the_sdk_options(
    world: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    world.script("abcd1234", {"_fake": "result", "text": "ok"})
    servers = {"godot-mcp-runtime": {"type": "stdio", "command": "node"}}
    assert sdkturn.main([spec(world, mcp_servers=servers, strict_mcp_config=True)]) == 0
    capsys.readouterr()
    (opt,) = options(world)
    assert opt["mcp_servers"] == servers
    assert opt["strict_mcp_config"] is True


def test_control_traffic_is_not_printed(capsys: pytest.CaptureFixture[str]) -> None:
    seen = sdkturn.Seen()
    sdkturn.record({"type": "control_response", "response": {}}, seen)
    sdkturn.record({"type": "assistant", "session_id": "s1"}, seen)
    sdkturn.record({"type": "user"}, seen)  # no session id: the last one stays
    sdkturn.record({"type": "result", "session_id": "s2"}, seen)
    assert [x["type"] for x in lines(capsys)] == ["assistant", "user", "result"]
    assert (seen.session_id, seen.result) == ("s2", True)


def test_an_sdk_failure_before_any_result_becomes_one_errored_result(
    world: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    world.script("abcd1234", {"_fake": "exit", "code": 2})
    assert sdkturn.main([spec(world)]) == 1
    out = lines(capsys)
    assert out[-1]["type"] == "result"
    assert out[-1]["is_error"] is True
    assert "Agent SDK failed" in out[-1]["result"]
    assert out[-1]["session_id"].startswith("fake-")


def test_an_sdk_failure_after_the_cli_result_adds_no_second_result(
    world: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    world.script(
        "abcd1234",
        {"_fake": "result", "text": "Credit balance is too low", "is_error": True},
        {"_fake": "exit", "code": 1},
    )
    assert sdkturn.main([spec(world)]) == 1
    out = lines(capsys)
    assert [x["type"] for x in out].count("result") == 1


def test_main_reads_argv_when_none_given(
    world: Env, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["sdkturn", spec(world)])
    assert sdkturn.main() == 0
    assert lines(capsys)[-1]["type"] == "result"
    assert Path(sdkturn.__file__).name == "sdkturn.py"


def test_runs_as_main(
    world: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["sdkturn", spec(world)])
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(sdkturn.__file__, run_name="__main__")
    assert stop.value.code == 0
    assert lines(capsys)[-1]["type"] == "result"
