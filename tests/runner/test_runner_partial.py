"""Every turn streams partial messages, so a long answer writes stream lines as it goes (T2452)."""

import json
from pathlib import Path

import pytest
from runnerfakes import Env
from test_runner_credit_sdkturn import options, spec
from todoimpl.runner import claude, sdkturn


def test_t2452_every_turn_streams_partial_messages(world: Env, tmp_path: Path) -> None:
    del world
    argv = claude.build("implement", "go", tmp_path).argv
    assert argv[argv.index("--verbose") + 1] == "--include-partial-messages"


def test_t2452_the_sdk_route_streams_partial_messages_too(world: Env, capsys: pytest.CaptureFixture[str]) -> None:
    world.script("abcd1234", {"_fake": "result", "text": "ok"})
    assert sdkturn.main([spec(world)]) == 0
    capsys.readouterr()
    assert options(world)[0]["include_partial_messages"] is True
