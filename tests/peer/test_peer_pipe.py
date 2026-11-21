"""The real pipe: the turn host feeds claude's stdin from a FIFO, the server writes peer lines into it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from todoimpl.peer.pipe import FIFO, RunPipe
from todoimpl.runner import peerpipe

CARD = "abcd1234-0"
READER = "import sys\nfor line in sys.stdin:\n    print(line.strip(), flush=True)\n"


def test_argv_moves_the_prompt_to_stdin() -> None:
    moved = peerpipe.stdin_argv(["claude", "-p", "do it", "--model", "opus"])
    assert moved is not None
    argv, prompt = moved
    assert prompt == "do it"
    assert argv == ["claude", "-p", "--model", "opus", *peerpipe.FLAGS]
    assert peerpipe.stdin_argv(["claude", "--model", "opus"]) is None
    assert peerpipe.stdin_argv(["claude", "-p"]) is None


def test_host_pipe_feeds_prompt_then_peer_lines_and_closes_on_result(tmp_path: Path) -> None:
    run = tmp_path / CARD
    run.mkdir()
    stream = run / "t1.stream.jsonl"
    pipe = peerpipe.HostPipe.create(run, "the prompt")
    with stream.open("wb") as out:
        proc = subprocess.Popen([sys.executable, "-c", READER], stdin=pipe.stdin, stdout=out)
    pipe.started()
    server = RunPipe(tmp_path)
    pipe.ready.wait(5)
    assert server.is_open(CARD)
    mark = server.write(CARD, {"type": "user", "uuid": "u-1", "message": {"content": "hi"}})
    assert mark is not None
    assert mark[0] == str(stream)
    deadline = 50
    while not server.echoed(CARD, mark, "u-1") and deadline:
        threading.Event().wait(0.1)
        deadline -= 1
    assert server.echoed(CARD, mark, "u-1")
    assert not server.echoed(CARD, mark, "u-2")
    first = json.loads(stream.read_text().splitlines()[0])
    assert first["message"]["content"] == "the prompt"
    with stream.open("ab") as out:
        out.write(b'{"result":"done","type":"result"}\n')
    pipe.watch(stream)
    assert not server.is_open(CARD)
    assert proc.wait(5) == 0  # stdin reached EOF
    pipe.close()  # twice is fine


def test_server_write_without_a_session_gives_none(tmp_path: Path) -> None:
    (tmp_path / CARD).mkdir()
    server = RunPipe(tmp_path)
    assert server.write(CARD, {"uuid": "x"}) is None
    (tmp_path / CARD / FIFO).write_text("a plain file is not a session")
    assert server.write(CARD, {"uuid": "x"}) is None
    assert not server.echoed(CARD, ("missing.jsonl", 0), "x")


def test_fifo_with_no_reader_is_not_written(tmp_path: Path) -> None:
    (tmp_path / CARD).mkdir()
    os.mkfifo(tmp_path / CARD / FIFO)
    assert RunPipe(tmp_path).write(CARD, {"uuid": "x"}) is None


def test_child_that_dies_early_does_not_hang_the_writer(tmp_path: Path) -> None:
    run = tmp_path / CARD
    run.mkdir()
    pipe = peerpipe.HostPipe.create(run, "x" * (1 << 20))  # more than a pipe buffer
    proc = subprocess.Popen([sys.executable, "-c", "pass"], stdin=pipe.stdin)
    pipe.started()
    proc.wait(5)
    pipe.close()
    assert not (run / FIFO).exists()
    assert not (run / peerpipe.NEW).exists()


@pytest.mark.parametrize(
    "line", [b"", b'not json "type":"result"\n', b'["type":"result"]\n', b'{"type":"assistant"}\n']
)
def test_watch_ignores_other_lines(tmp_path: Path, line: bytes) -> None:
    run = tmp_path / CARD
    run.mkdir()
    stream = run / "s.stream.jsonl"
    stream.write_bytes(line)
    pipe = peerpipe.HostPipe.create(run, "p")
    proc = subprocess.Popen([sys.executable, "-c", READER], stdin=pipe.stdin, stdout=subprocess.DEVNULL)
    pipe.started()
    pipe.ready.wait(5)
    pipe.watch(stream)
    pipe.watch(run / "missing.jsonl")
    assert (run / FIFO).exists()
    pipe.close()
    assert proc.wait(5) == 0
