"""T2008: checks that go red after Ship's rebase send the session a bounded fix turn before kuhy is paged."""

from pathlib import Path
from typing import Any

from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, wait_stage
from todoimpl.board.needs import needs

FIX = reply("could not fix it\n\nD: done")


def _check(marker: Path) -> str:
    return f"test -f {marker} || {{ echo marker-missing; false; }}"


def _fixed(marker: Path) -> tuple[dict[str, Any], ...]:
    return ({"_fake": "write", "path": str(marker), "text": "ok\n"}, *reply("fixed it\n\nD: done"))


def test_t2008_checks_red_after_the_rebase_go_to_a_fix_turn_and_ship_again(world: Env) -> None:
    marker = world.tmp / "green"
    marker.write_text("ok\n", encoding="utf-8")
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, _fixed(marker), done_check=_check(marker))
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        marker.unlink()  # what the rebase brought in: the checks are red on the rebased tree
        sched.ship(CARD)
        st = wait_stage(world, sched, "shipped")
        prompt = world.calls()[-1]["prompt"]
        assert "Checks went red after the rebase on origin/main: done_check" in prompt
        assert "marker-missing" in prompt
        assert "fix them yourself" in prompt.lower()
        assert st.extra["ship_fixes"] == 1
        assert len(client.closed) == 1
    finally:
        sched.close()


def test_t2008_after_the_bound_kuhy_gets_the_card_with_the_red_checks(world: Env) -> None:
    marker = world.tmp / "green"
    marker.write_text("ok\n", encoding="utf-8")
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, FIX, FIX, done_check=_check(marker))
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        marker.unlink()
        sched.ship(CARD)
        st = wait_stage(world, sched, "failed", turns=3)
        assert (st.error or "").startswith("Checks went red after the rebase on origin/main: done_check")
        assert len(world.calls()) == 5  # plan, implement, live check, two fix turns
        assert needs(st).kind == "run_failed"
        assert client.closed == []
    finally:
        sched.close()
