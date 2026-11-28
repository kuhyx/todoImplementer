import json
from pathlib import Path

import pytest
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait_stage
from test_runner_permit_flow import MCP_ADD, SUDO
from todoimpl.runner import claude, policy


def write(world: Env, data: object) -> Path:
    path = world.tmp / "session-policy.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _policy_path(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_POLICY", str(world.tmp / "session-policy.json"))


def test_t1640_no_policy_file_keeps_todays_behaviour(world: Env, tmp_path: Path) -> None:
    got = policy.load()
    assert got == policy.Policy()
    assert not got.present
    argv = claude.build("implement", "p", tmp_path).argv
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert argv[-6:] == ("Bash(git push:*)", "Bash(git push *)", *policy.src_deny())
    assert argv[argv.index("--settings") + 1] == policy.turn_settings(hooks_off=False)  # T2444: the Bash cap


def test_t1641_a_valid_policy_loosens_the_session(world: Env, tmp_path: Path) -> None:
    write(
        world,
        {
            "permission_mode": "bypassPermissions",
            "add_dirs": ["~", "/srv/x"],
            "disable_hooks": True,
            "deny": [],
        },
    )
    inv = claude.build("implement", "p", tmp_path, allow=("Bash(ls:*)",))
    argv = inv.argv
    assert argv[argv.index("--permission-mode") + 1] == "bypassPermissions"
    assert argv[argv.index("--add-dir") + 1 : argv.index("--add-dir") + 5] == (
        str(tmp_path),
        str(policy.shrink_dir()),
        str(Path.home()),
        "/srv/x",
    )
    assert argv[argv.index("--allowedTools") + 1] == "Bash(ls:*)"
    assert argv[argv.index("--disallowedTools") + 1 :] == policy.src_deny()  # only kuhy's checkouts (T2515)
    assert argv[argv.index("--settings") + 1] == policy.HOOKS_OFF
    assert inv.notes == ()
    assert policy.load().present


def test_t1642_deny_null_keeps_the_builtin_list_and_classify_stays_read_only(
    world: Env, tmp_path: Path
) -> None:
    write(world, {"deny": None})
    assert claude.build("implement", "p", tmp_path).argv[-6:-4] == ("Bash(git push:*)", "Bash(git push *)")
    write(world, {"deny": ["Bash(rm:*)"]})
    argv = claude.build("classify", "p", tmp_path).argv
    assert argv[-8:-4] == ("Bash(rm:*)", "Edit", "Write", "NotebookEdit")


@pytest.mark.parametrize(
    ("content", "why"),
    [
        ("{nope", "not valid JSON"),
        ("[1]", "not a JSON object"),
        ({"surprise": 1}, "unknown key(s) surprise"),
        ({"permission_mode": ""}, "permission_mode must be a non-empty string"),
        ({"disable_hooks": "yes"}, "disable_hooks must be true or false"),
        ({"add_dirs": "~"}, "add_dirs must be a list of strings"),
        ({"deny": [1]}, "deny must be a list of strings or null"),
    ],
)
def test_t1643_an_invalid_policy_is_ignored_with_a_warning(
    world: Env, tmp_path: Path, content: object, why: str
) -> None:
    write(world, content)
    inv = claude.build("implement", "p", tmp_path)
    assert policy.load().present is False
    assert len(inv.notes) == 1
    assert inv.notes[0].endswith(f"ignored: {why}")
    assert inv.argv[inv.argv.index("--permission-mode") + 1] == "acceptEdits"


def test_t1644_an_unreadable_policy_is_ignored_with_a_warning(world: Env) -> None:
    (world.tmp / "session-policy.json").mkdir()
    assert "ignored" in (policy.load().warning or "")


def test_t1645_policy_present_lifts_the_never_list_and_adds_the_sensitive_file_advice(world: Env) -> None:
    write(world, {"permission_mode": "bypassPermissions", "disable_hooks": True})
    sched, _ = boot(world, PLAN, SUDO, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        calls = world.calls()
        assert "Bash(sudo pacman:*)" in calls[2]["argv"]
        assert "authorized edits of protected files" in calls[1]["prompt"]
        assert "authorized edits of protected files" not in calls[0]["prompt"]
    finally:
        sched.close()


def test_t1646_a_policy_warning_shows_in_the_feed(world: Env) -> None:
    write(world, "{nope")
    sched, _ = boot(world, PLAN, MCP_ADD, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        texts = [e["text"] for e in sched.bus.history(CARD, 0)]
        assert any("session policy" in t and "ignored" in t for t in texts)
    finally:
        sched.close()
