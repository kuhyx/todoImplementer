"""Ship leaves the target repo's gate receipt (T1837) and retries a raced push on a rebase (T1838)."""

import pytest
from gatefakes import HOOK, G, gated, ship_plan, steps
from runnerfakes import Env, executable, sh
from todoimpl.runner import ship
from todoimpl.runner.files import NeedsYouError


def test_t1837_ship_runs_the_repos_gate_so_the_pre_push_hook_takes_the_push(world: Env) -> None:
    repo, wt, client = gated(world)
    info = ship.ship(ship_plan(world, repo, wt), client, lambda: 1.0)
    assert sh(world.tmp / "remotes" / "demo.git", "git", "rev-parse", "main").strip() == info["commit"]
    closed = client.closed[0][1]
    assert "gate-one `scripts/check_gate_stamp.sh step one` exit 0" in closed
    assert "gate-two `scripts/check_gate_stamp.sh step two` exit 0" in closed


def test_t1837_a_red_gate_step_stops_the_ship_before_the_push(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt, client = gated(world)
    monkeypatch.setenv("FAIL_STEP", "one")
    with pytest.raises(NeedsYouError, match="gate step one is red") as red:
        ship.ship(ship_plan(world, repo, wt), client, lambda: 1.0)
    assert red.value.kind == "checks_failed"
    assert "step one is red" in str(red.value)
    assert client.closed == []
    assert wt.path.exists()


def test_t1838_a_raced_push_rebases_onto_origin_and_is_gated_again(world: Env) -> None:
    repo, wt, client = gated(world)
    remote = world.tmp / "remotes" / "demo.git"
    other = world.tmp / "other"
    sh(world.tmp, "git", "clone", "-q", str(remote), str(other))
    (other / "theirs.txt").write_text("t\n", encoding="utf-8")
    sh(other, "git", "add", "-A")
    sh(other, "git", "commit", "-q", "-m", "raced upstream")
    flag = world.tmp / "raced"
    executable(
        repo / ".git" / "hooks" / "pre-push",
        f"{HOOK}[ -e {flag} ] || {{ touch {flag}; {G.format(other)} push -q origin HEAD:main; }}\n",
    )
    info = ship.ship(ship_plan(world, repo, wt), client, lambda: 1.0)
    assert sh(remote, "git", "log", "--format=%s", "main").splitlines() == [
        "Add hello file", "raced upstream", "gate", "init",
    ]  # fmt: skip
    assert sh(remote, "git", "rev-parse", "main").strip() == info["commit"]
    assert len(steps(repo)) == 4  # both steps ran on the first tree and again on the rebased one


def test_t1838_a_push_the_hook_refuses_is_not_retried_as_a_race(world: Env) -> None:
    repo, wt, client = gated(world)
    executable(repo / ".git" / "hooks" / "pre-push", "#!/bin/sh\necho hook says no >&2\nexit 1\n")
    with pytest.raises(NeedsYouError, match=r"was refused: .*hook says no"):
        ship.ship(ship_plan(world, repo, wt), client, lambda: 1.0)
    assert client.closed == []


def test_t1838_a_push_that_keeps_losing_the_race_gives_up(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt, client = gated(world)
    monkeypatch.setattr(ship, "PUSH_TRIES", 2)
    remote = world.tmp / "remotes" / "demo.git"
    other = world.tmp / "other"
    sh(world.tmp, "git", "clone", "-q", str(remote), str(other))
    executable(
        repo / ".git" / "hooks" / "pre-push",
        f"{HOOK}echo $$ >> {other}/n.txt && {G.format(other)} add -A && {G.format(other)} commit -q -m again "
        f"&& {G.format(other)} push -q origin HEAD:main\n",
    )
    with pytest.raises(NeedsYouError, match="was refused"):
        ship.ship(ship_plan(world, repo, wt), client, lambda: 1.0)
    assert client.closed == []
