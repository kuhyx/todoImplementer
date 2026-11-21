"""Every turn caps one Bash call at 40 s (T2453): a long command hands control back before a stall (T2444).

kuhy's ~/.claude/settings.json sets `BASH_MAX_TIMEOUT_MS` to an hour and settings env beats the process env,
so the cap must travel in `--settings`. At the cap claude moves the command to the background and the model
gets a tool result: the card shows activity instead of going quiet (probed with claude 2.1.330).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from todoimpl.runner import claude, policy

if TYPE_CHECKING:
    from pathlib import Path

    from runnerfakes import Env

CAP = {"BASH_DEFAULT_TIMEOUT_MS": "40000", "BASH_MAX_TIMEOUT_MS": "40000"}


@pytest.fixture(autouse=True)
def _policy_path(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_POLICY", str(world.tmp / "session-policy.json"))


def _settings(argv: tuple[str, ...]) -> dict[str, object]:
    loaded: dict[str, object] = json.loads(argv[argv.index("--settings") + 1])
    return loaded


def test_t2444_a_turn_caps_its_bash_calls(world: Env, tmp_path: Path) -> None:
    assert _settings(claude.build("implement", "p", tmp_path).argv) == {"env": CAP}
    (world.tmp / "session-policy.json").write_text(json.dumps({"disable_hooks": True}), encoding="utf-8")
    assert _settings(claude.build("implement", "p", tmp_path).argv) == {"disableAllHooks": True, "env": CAP}


def test_t2444_the_settings_are_one_json_object() -> None:
    assert json.loads(policy.turn_settings(hooks_off=False)) == {"env": CAP}
    assert json.loads(policy.turn_settings(hooks_off=True)) == {"disableAllHooks": True, "env": CAP}
