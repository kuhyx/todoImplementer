"""The peer client, CLI and MCP tools against a real board server and hub (C1, C2, C10 hermetic)."""

from __future__ import annotations

import asyncio
import json
import runpy
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "peer"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "http"))
from httpfakes import FakeBackend
from peerfakes import CARD, make_world
from todoimpl.http.app import make_server
from todoimpl_mcp import peer_cli, peer_client, peer_server

if TYPE_CHECKING:
    from collections.abc import Iterator

    from peerfakes import World


@pytest.fixture
def board(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    world = make_world(tmp_path)
    (tmp_path / "peer.token").write_text("secret-token\n")
    backend = FakeBackend()
    backend.peer_hub = world.hub  # type: ignore[attr-defined]
    server = make_server(backend, port=0, dist=tmp_path / "dist")
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    monkeypatch.setenv(peer_client.URL_ENV, f"http://127.0.0.1:{server.server_address[1]}/api/peer")
    monkeypatch.setenv(peer_client.TOKEN_ENV, str(tmp_path / "peer.token"))
    for var in (peer_client.CARD_ENV, peer_client.KEY_ENV, peer_client.WAIT_ENV, peer_client.LABEL_ENV):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    yield world
    server.shutdown()
    server.server_close()
    thread.join(5)


def _as_task(world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> peer_client.Peer:
    key = tmp_path / "peer.key"
    key.write_text(world.hub.card_key(CARD) + "\n")
    monkeypatch.setenv(peer_client.CARD_ENV, CARD)
    monkeypatch.setenv(peer_client.KEY_ENV, str(key))
    return peer_client.Peer()


def test_client_send_then_task_replies_then_await(
    board: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    me = peer_client.Peer("leetcode-guard")
    sent = me.send(CARD, "which port?")
    board.hub.tick()
    task = _as_task(board, monkeypatch, tmp_path)
    task.reply(sent["id"], "8790")
    got = me.await_reply(sent["id"], 5)
    assert (got["state"], got["reply"]) == ("answered", "8790")


def test_await_loops_slices_and_gives_up_at_its_timeout(
    board: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(peer_client, "SLICE", 0.05)
    me = peer_client.Peer("a")
    sent = me.send(CARD, "q")
    assert me.await_reply(sent["id"], 0.2)["state"] == "queued"


def test_board_session_waits_at_most_its_cap(board: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(peer_client.WAIT_ENV, "0.1")
    me = peer_client.Peer("a")
    sent = me.send(CARD, "q")
    assert me.await_reply(sent["id"], 600)["state"] == "queued"


def test_task_sends_to_my_label_and_i_answer(
    board: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    me = peer_client.Peer("desk")
    assert me.inbox() == []
    task = _as_task(board, monkeypatch, tmp_path)
    sent = task.send(me.display, "need input")
    got = me.inbox(1)
    assert got[0]["id"] == sent["id"]
    me.reply(sent["id"], "here")
    assert task.await_reply(sent["id"], 1)["reply"] == "here"


def test_refusal_is_a_peer_error_with_retry(board: World) -> None:
    with pytest.raises(peer_client.PeerError, match="unknown task"):
        peer_client.Peer("a").send("zzzz9999-0", "x")
    board.pipe.open.clear()
    for n in range(5):
        peer_client.Peer(f"s{n}").send(CARD, "x")
    with pytest.raises(peer_client.PeerError, match="retry in 5") as caught:
        peer_client.Peer("late").send(CARD, "x")
    assert caught.value.retry_after == 5.0


def test_server_down_and_missing_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(peer_client.URL_ENV, "http://127.0.0.1:9/api/peer")
    monkeypatch.setenv(peer_client.TOKEN_ENV, str(tmp_path / "none"))
    with pytest.raises(peer_client.PeerError, match="token"):
        peer_client.Peer("a").send(CARD, "x")
    (tmp_path / "none").write_text("t")
    with pytest.raises(peer_client.PeerError, match="board down"):
        peer_client.Peer("a").send(CARD, "x")


def test_default_label_comes_from_the_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(peer_client.LABEL_ENV, raising=False)
    (tmp_path / "my repo!").mkdir()
    monkeypatch.chdir(tmp_path / "my repo!")
    assert peer_client.default_label() == "my-repo"
    (tmp_path / "kuhy").mkdir()
    monkeypatch.chdir(tmp_path / "kuhy")
    assert peer_client.default_label() == "session"
    monkeypatch.setenv(peer_client.LABEL_ENV, "named")
    assert peer_client.default_label() == "named"


def test_token_file_default_follows_todoimpl_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(peer_client.TOKEN_ENV, raising=False)
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path))
    assert peer_client.token_file() == tmp_path / "peer.token"
    monkeypatch.delenv("TODOIMPL_HOME")
    assert peer_client.token_file().name == "peer.token"


def _cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, Any]:
    code = peer_cli.main(list(argv))
    out = capsys.readouterr()
    return code, json.loads(out.out) if out.out.strip() else out.err


def test_cli_round_trip_keeps_its_sender(
    board: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, inbox = _cli(capsys, "--label", "desk", "inbox")
    assert (code, inbox) == (0, [])
    code, sent = _cli(capsys, "--label", "desk", "send", CARD, "hi there")
    assert code == 0
    board.hub.tick()
    _as_task(board, monkeypatch, tmp_path).reply(sent["id"], "yo")
    monkeypatch.delenv(peer_client.CARD_ENV)
    code, got = _cli(capsys, "--label", "desk", "await", sent["id"], "--timeout", "2")
    assert (code, got["reply"]) == (0, "yo")
    task_sent = _as_task(board, monkeypatch, tmp_path).send("desk", "q from task")
    monkeypatch.delenv(peer_client.CARD_ENV)
    code, got = _cli(capsys, "--label", "desk", "inbox", "--wait", "1")
    assert got[0]["id"] == task_sent["id"]  # the same sender id as the first call: its inbox
    code, done = _cli(capsys, "--label", "desk", "reply", task_sent["id"], "a")
    assert (code, done["state"]) == (0, "answered")


def test_cli_reads_text_from_stdin_and_reports_refusals(
    board: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("from stdin"))
    code, sent = _cli(capsys, "--label", "a", "send", CARD, "-")
    assert (code, sent["text"]) == (0, "from stdin")
    code, err = _cli(capsys, "--label", "a", "send", "zzzz9999-0", "x")
    assert code == 1
    assert "unknown task" in err


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_cli_module_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["peer_cli", "--help"])
    with pytest.raises(SystemExit):
        runpy.run_module("todoimpl_mcp.peer_cli", run_name="__main__")


def test_mcp_tools(board: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(peer_client.LABEL_ENV, "mcp-desk")
    names = {t.name for t in asyncio.run(peer_server.mcp.list_tools())}
    assert names == {"send_peer", "await_reply", "inbox", "reply_peer"}

    def call(name: str, **args: Any) -> str:
        result = asyncio.run(peer_server.mcp.call_tool(name, args))
        assert isinstance(result, CallToolResult)
        block = result.content[0]
        assert isinstance(block, TextContent)
        return block.text

    peer_server.reset()
    assert json.loads(call("inbox")) == []
    sent = json.loads(call("send_peer", to=CARD, text="hi"))
    board.hub.tick()
    board.hub.reply(board.hub.task_sender(CARD), sent["id"], "ok")
    assert json.loads(call("await_reply", id=sent["id"], timeout=1))["reply"] == "ok"
    assert "unknown message" in call("reply_peer", id="nope", text="x")
    task_msg = board.hub.send(board.hub.task_sender(CARD), "mcp-desk", "q")
    assert json.loads(call("inbox", wait=1))[0]["id"] == task_msg["id"]
    assert json.loads(call("reply_peer", id=task_msg["id"], text="a"))["state"] == "answered"
    assert "unknown task" in call("send_peer", to="zzzz9999-0", text="x", reply_to="")


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_mcp_server_main(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(MCPServer, "run", lambda *_a, **_k: seen.append("run"))
    monkeypatch.setattr(sys, "argv", ["peer_server"])
    runpy.run_module("todoimpl_mcp.peer_server", run_name="__main__")
    assert seen == ["run"]
