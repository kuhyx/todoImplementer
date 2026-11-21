"""[T1986] A board turn starts no user MCP server; only the one its repo kind needs, if kuhy has it."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from creditfakes import enable_credits
from runnerfakes import Env
from todoimpl.runner import claude, credit, mcpconf

FLUTTER = {"type": "stdio", "command": "python3", "args": ["-m", "flutter_web_drive.mcp_server"]}
GODOT = {"type": "stdio", "command": "node", "args": ["godot.js"], "env": {"GODOT_PATH": "/usr/bin/godot"}}
NOISE = {"type": "stdio", "command": "wikikb", "args": []}


def park(world: Env, servers: dict[str, Any]) -> None:
    (world.home / ".claude").mkdir(exist_ok=True)
    (world.home / ".claude" / "mcp-parked.json").write_text(json.dumps({"mcpServers": servers}))


def worktree(world: Env, marker: str | None) -> Path:
    wt = world.tmp / "abcd1234-0" / "wt"
    wt.mkdir(parents=True, exist_ok=True)
    if marker:
        (wt / marker).write_text("x")
    return wt


def config(inv: claude.Invocation) -> dict[str, Any]:
    argv = inv.argv
    assert "--strict-mcp-config" in argv
    found: dict[str, Any] = json.loads(argv[argv.index("--mcp-config") + 1])
    return found


def test_t1986_every_turn_is_strict_and_loads_no_parked_server(world: Env) -> None:
    park(world, {"flutter-web-drive": FLUTTER, "godot-mcp-runtime": GODOT, "wikikb": NOISE, "i3wm": NOISE})
    inv = claude.build("implement", "go", worktree(world, "pyproject.toml"))
    assert config(inv) == {"mcpServers": {}}


def test_t1986_a_flutter_repo_gets_only_flutter_web_drive(world: Env) -> None:
    park(world, {"flutter-web-drive": FLUTTER, "godot-mcp-runtime": GODOT, "wikikb": NOISE})
    assert config(claude.build("live_check", "go", worktree(world, "pubspec.yaml"))) == {
        "mcpServers": {"flutter-web-drive": FLUTTER}
    }


def test_t1986_a_godot_repo_gets_only_godot_mcp_runtime(world: Env) -> None:
    park(world, {"flutter-web-drive": FLUTTER, "godot-mcp-runtime": GODOT})
    assert config(claude.build("implement", "go", worktree(world, "project.godot"))) == {
        "mcpServers": {"godot-mcp-runtime": GODOT}
    }


def test_t1986_a_missing_or_broken_definition_is_skipped_silently(world: Env) -> None:
    wt = worktree(world, "pubspec.yaml")
    assert config(claude.build("implement", "go", wt)) == {"mcpServers": {}}  # no parked file at all
    (world.home / ".claude").mkdir()
    (world.home / ".claude" / "mcp-parked.json").write_text("{not json")
    assert config(claude.build("implement", "go", wt)) == {"mcpServers": {}}
    park(world, {"godot-mcp-runtime": GODOT})  # parked, but not the one a Flutter repo wants
    assert config(claude.build("implement", "go", wt)) == {"mcpServers": {}}
    park(world, {"flutter-web-drive": "not a dict"})
    assert config(claude.build("implement", "go", wt)) == {"mcpServers": {}}


def test_t1986_a_restored_server_in_claude_json_wins_over_the_parked_copy(world: Env) -> None:
    wt = worktree(world, "pubspec.yaml")
    restored = {**FLUTTER, "args": ["restored"]}
    park(world, {"flutter-web-drive": FLUTTER})
    (world.home / ".claude.json").write_text(json.dumps({"mcpServers": {"flutter-web-drive": restored}}))
    assert mcpconf.servers(wt) == {"flutter-web-drive": restored}


def test_t1986_the_credit_route_is_strict_too(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    enable_credits(monkeypatch)
    park(world, {"godot-mcp-runtime": GODOT, "wikikb": NOISE})
    inv = credit.build("implement", "go", worktree(world, "project.godot"))
    spec = json.loads(inv.argv[3])
    assert spec["mcp_servers"] == {"godot-mcp-runtime": GODOT}
    assert spec["strict_mcp_config"] is True
    assert inv.argv[:3] == (sys.executable, "-m", "todoimpl.runner.sdkturn")


def _peer_venv(world: Env) -> Path:
    python = world.home / ".venvs" / "todoimpl-mcp" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    return python


def test_every_board_turn_gets_the_peer_server_by_path_never_by_secret(world: Env) -> None:
    python = _peer_venv(world)
    wt = worktree(world, "pyproject.toml")
    inv = claude.build("implement", "go", wt)
    peer = config(inv)["mcpServers"]["peer"]
    assert peer["command"] == str(python)
    assert peer["args"] == ["-m", "todoimpl_mcp.peer_server"]
    env = peer["env"]
    assert env["TODOIMPL_PEER_CARD"] == "abcd1234-0"
    assert env["TODOIMPL_PEER_MAX_WAIT"] == "40"
    key = Path(env["TODOIMPL_PEER_KEY_FILE"])
    assert key.parent == wt.parent
    assert key.stat().st_mode & 0o777 == 0o600
    secret = key.read_text().strip()
    token = Path(env["TODOIMPL_PEER_TOKEN_FILE"]).read_text().strip()
    assert secret not in " ".join(inv.argv)
    assert token not in " ".join(inv.argv)
    argv = list(inv.argv)
    assert "mcp__peer" in argv[argv.index("--allowedTools") :]
    line = argv[argv.index("--append-system-prompt") + 1]
    assert "not from kuhy" in line
    assert "reply_peer" in line


def test_peer_server_url_follows_the_server_env(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _peer_venv(world)
    monkeypatch.setenv("TODOIMPL_PEER_URL", "http://127.0.0.1:9999/api/peer")
    env = mcpconf.servers(worktree(world, None))["peer"]["env"]
    assert env["TODOIMPL_PEER_URL"] == "http://127.0.0.1:9999/api/peer"


def test_credit_turn_gets_the_peer_line_too(world: Env) -> None:
    _peer_venv(world)
    opt = claude.options("implement", "go", worktree(world, None))
    assert "not from kuhy" in opt.system_append
    assert "mcp__peer" in opt.allow
