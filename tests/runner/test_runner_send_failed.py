import shutil

from runnerfakes import Env, sh
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait_stage


def test_t2056_send_on_a_failed_run_with_no_session_starts_it_again_with_the_message(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, repo="Sepci0/demo", done_check="true")
    try:
        sched.start(CARD)  # the clone's origin is not Sepci0/demo yet
        st = wait_stage(world, sched, "failed")
        assert st.error is not None
        assert "no local clone" in st.error
        assert not st.sessions
        moved = world.tmp / "remotes" / "Sepci0" / "demo"  # an origin URL that ends in Sepci0/demo
        moved.parent.mkdir()
        shutil.move(world.tmp / "remotes" / "demo.git", moved)
        sh(world.src / "demo", "git", "remote", "set-url", "origin", str(moved))
        sched.send(CARD, "use ~/src/demo")
        st = wait_stage(world, sched, "gate")
        assert st.error is None
        assert "use ~/src/demo" in world.calls()[0]["prompt"]
        users = [e["text"] for e in sched.bus.history(CARD, 0) if e["kind"] == "user"]
        assert users == ["use ~/src/demo"]
    finally:
        sched.close()
