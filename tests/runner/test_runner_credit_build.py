"""Plan and credit invocations: same options, the key only on the credit route."""

import json
import sys
from pathlib import Path

import pytest
from creditfakes import FAKE_KEY, enable_credits, key_file
from runnerfakes import Env
from todoimpl.runner import claude, credit, launch
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.policy import HOOKS_OFF, src_deny


def test_t1851_plan_env_never_carries_the_api_key(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    inv = claude.build("implement", "go", world.tmp / "abcd1234-0" / "wt")
    assert "ANTHROPIC_API_KEY" not in inv.env
    assert inv.route == "plan"
    assert inv.env["CLAUDE_AUTO_CONTINUE"] == "0"


def test_credit_invocation_mirrors_the_plan_options_and_carries_the_key(
    world: Env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    enable_credits(monkeypatch)
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"permission_mode": "bypassPermissions", "add_dirs": ["/x"], "disable_hooks": True})
    )
    monkeypatch.setenv("TODOIMPL_POLICY", str(policy))
    wt = world.tmp / "abcd1234-0" / "wt"
    run_dir = wt.parent
    plan = claude.build("implement", "go", wt, "sess-1", (run_dir,), ("Bash(ls:*)",))
    cred = credit.build("implement", "go", wt, "sess-1", (run_dir,), ("Bash(ls:*)",))
    assert cred.route == "credits"
    assert cred.argv[:3] == (sys.executable, "-m", "todoimpl.runner.sdkturn")
    spec = json.loads(cred.argv[3])
    assert spec["model"] == "claude-sonnet-5-5"  # the credits_model default, for every role
    assert plan.argv[plan.argv.index("--model") + 1] == "sonnet"
    assert spec["resume"] == "sess-1"
    assert spec["cwd"] == str(wt)
    assert spec["permission_mode"] == "bypassPermissions"
    assert spec["add_dirs"] == [str(wt), str(run_dir), "/x"]
    assert spec["allowed_tools"] == ["Bash(ls:*)"]
    assert spec["disallowed_tools"] == [*claude.DENY_ALWAYS, *src_deny()]  # T2515
    assert spec["settings"] == HOOKS_OFF
    assert spec["setting_sources"] == ["user", "project", "local"]
    assert spec["prompt"] == "go"
    assert cred.env["ANTHROPIC_API_KEY"] == FAKE_KEY
    assert cred.env["CLAUDE_AUTO_CONTINUE"] == "0"
    assert cred.env["PHONE_LEASE_OWNER"] == "todoimpl:abcd1234-0"
    assert cred.env["PYTHONPATH"].startswith(str(launch.SERVER_DIR))
    assert FAKE_KEY not in json.dumps(cred.argv)


def test_credit_turn_without_sdk_or_key_is_needs_you(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    wt = world.tmp / "abcd1234-0" / "wt"
    with pytest.raises(NeedsYouError, match="venv missing"):
        credit.build("plan", "go", wt)
    enable_credits(monkeypatch)
    key_file().write_text("")
    with pytest.raises(NeedsYouError, match="no usable API key"):
        credit.build("plan", "go", wt)
