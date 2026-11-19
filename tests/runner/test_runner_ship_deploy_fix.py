"""T2050: a deploy that is red after the push goes to a bounded fix turn before kuhy is paged."""

import pytest
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait, wait_stage
from todoimpl.board.needs import needs
from todoimpl.prompts.standing import DEPLOY
from todoimpl.runner.deploy import DeployFailedError

FIX = reply("could not fix it\n\nD: done")
FAIL_LINE = "FAIL -- app_errors changed after app-errors-v0.1.0: bump its version and release it"


def test_t2050_a_red_deploy_goes_to_a_fix_turn_that_redeploys(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEPLOY_LOG", str(world.tmp / "deploys"))
    monkeypatch.setenv("DEPLOY_EXIT", "3")
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, FIX, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        sched.ship(CARD)
        wait(lambda: state(world).extra.get("deploy_fixes") == 1)
        monkeypatch.setenv("DEPLOY_EXIT", "0")  # what the session's bump and release did
        st = wait_stage(world, sched, "shipped", turns=2)
        prompt = world.calls()[-1]["prompt"]
        assert "pushed, not deployed: deploy failed (exit 3)" in prompt
        assert "shim-deploy-output" in prompt
        assert "bump and tag the changed package, push, redeploy" in prompt
        assert st.extra["deploy_fixes"] == 1
        assert len(client.closed) == 1
        assert len((world.tmp / "deploys").read_text(encoding="utf-8").splitlines()) == 2
    finally:
        sched.close()


def test_t2050_after_the_bound_kuhy_gets_the_card_naming_the_failing_check(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEPLOY_EXIT", "3")
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, FIX, FIX, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        sched.ship(CARD)
        st = wait_stage(world, sched, "failed", turns=3)
        assert (st.error or "").startswith("pushed, not deployed: deploy failed (exit 3)")
        assert len(world.calls()) == 5  # plan, implement, live check, two fix turns
        assert (needs(st).kind, client.closed) == ("run_failed", [])
    finally:
        sched.close()


def test_t2050_the_error_names_the_fail_line_even_when_the_tail_is_long() -> None:
    noise = "\n".join(f"health check line {n}" for n in range(200))
    err = DeployFailedError.build(3, f"{FAIL_LINE}\n{noise}")
    assert FAIL_LINE in err.text
    assert err.text.startswith("pushed, not deployed: deploy failed (exit 3)")
    assert "Fix it yourself: bump and tag the changed package, push, redeploy" in err.output


def test_t2050_the_deploy_standing_prompt_makes_a_bump_and_release_check_the_sessions_job() -> None:
    assert "changed after" in DEPLOY
    assert "bump the version" in DEPLOY
