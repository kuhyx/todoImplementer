import pytest
from contract_lib import validate
from runnerfakes import Env, sh
from schedfakes import CARD, IMPL, LIVE_BAD, LIVE_OK, PLAN, boot, reply, wait, wait_stage
from todoimpl.runner.scheduler import RunnerError, needs_spec
from todoimpl.todo_mcp.items import Item


def test_done_check_note_runs_plan_implement_live_checks_to_gate_then_ships(world: Env) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        validate("state", st.to_dict())
        assert st.checks is not None
        assert st.checks["passed"]
        assert st.checks["results"][0]["command"] == "test -f hello.txt"
        assert st.self_check == [{"criterion": "C1", "done": True, "note": "cat shows hi"}]
        assert st.live_check == {"report_md": LIVE_OK[0]["text"], "shots": []}
        assert st.cost_usd == 0.03
        calls = world.calls()
        assert [c["model"] for c in calls] == ["sonnet", "opus", "sonnet"]
        assert all(c["prompt"].startswith("override\n") for c in calls)
        assert calls[2]["resume"] is None  # the live check is a fresh session (T1896)
        assert st.sessions["live_check"]["session_id"] != st.sessions["implement"]["session_id"]
        assert str(world.root / CARD) in calls[0]["argv"]
        assert (world.root / CARD / "plan.md").read_text(encoding="utf-8") == PLAN[0]["text"]
        kinds = {e["kind"] for e in sched.bus.history(CARD, 0)}
        assert {"system", "result"} <= kinds
        sched.ship(CARD)
        st = wait_stage(world, sched, "shipped")
        assert st.ship is not None
        assert client.closed[0][0] == CARD
        assert "live C1: done (ran `cat hello.txt` -> saw hi)" in client.closed[0][1]
        assert "done_check `test -f hello.txt` exit 0" in client.closed[0][1]
        remote = world.tmp / "remotes" / "demo.git"
        assert "Todo: abcd1234" in sh(remote, "git", "log", "-1", "--format=%B", "main")
    finally:
        sched.close()


def test_spec_stage_grills_takes_answers_and_waits_for_spec_ok(world: Env) -> None:
    grill = reply("❓ **Q1** - **Scope**: Which file?\n➡️ hello.txt\n\nQ: answer the card")
    sched, _ = boot(
        world, grill, reply("Nothing open.\n\nD: specced"), PLAN, IMPL, LIVE_OK, body="Make it nicer"
    )
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "spec_wait")
        assert [(q.id, q.recommendation, q.answer) for q in st.spec_questions] == [("Q1", "hello.txt", None)]
        assert not world.calls()[0]["prompt"].startswith("override")
        with pytest.raises(RunnerError, match="still open"):
            sched.spec_ok(CARD)
        with pytest.raises(RunnerError, match="No such question: Q9"):
            sched.spec_answers(CARD, {"Q9": "x"})
        sched.spec_answers(CARD, {"Q1": " hello.txt "})
        st = wait_stage(world, sched, "spec_wait")
        assert st.spec_questions[0].answer == "hello.txt"
        assert world.calls()[1]["resume"] == st.sessions["spec"]["session_id"]
        with pytest.raises(RunnerError, match="only at Ready to ship"):
            sched.ship(CARD)
        sched.spec_ok(CARD)
        st = wait_stage(world, sched, "gate")
        assert "Scope: hello.txt" in world.calls()[2]["prompt"]
        with pytest.raises(RunnerError, match="only while Claude waits"):
            sched.spec_answers(CARD, {"Q1": "x"})
        with pytest.raises(RunnerError, match="Spec OK needs"):
            sched.spec_ok(CARD)
    finally:
        sched.close()


def test_red_checks_get_two_fixes_then_need_you_and_send_reopens(world: Env) -> None:
    turns = [PLAN, IMPL, LIVE_OK, IMPL, LIVE_OK, IMPL, LIVE_OK]
    sched, _ = boot(world, *turns, done_check="test -f nope.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.error == "Checks still red after 2 fix attempts: done_check"
        assert st.checks is not None
        assert not st.checks["passed"]
        fixes = [c["prompt"] for c in world.calls() if "Fix stage" in c["prompt"]]
        assert len(fixes) == 2
        assert "nope.txt" in fixes[0]
        world.script("abcd1234", *IMPL)
        world.script("abcd1234", *LIVE_OK)
        sched.send(CARD, "create nope.txt too")
        wait(lambda: len(world.calls()) == 9)
        assert "create nope.txt too" in world.calls()[7]["prompt"]
        wait_stage(world, sched, "failed")
    finally:
        sched.close()


def test_live_check_not_done_gets_one_fix_then_needs_you(world: Env) -> None:
    report = {
        "_fake": "write",
        "path": f"{world.root / CARD / 'live_check.md'}",
        "text": "- [ ] C1: saw nothing\n",
    }
    sched, _ = boot(
        world,
        *(PLAN, IMPL, (report, *reply("see live_check.md\n\nD: done")), IMPL, LIVE_BAD, IMPL, LIVE_BAD),
        done_check="true",
    )
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.error == "The live check still saw criteria not done: C1"
        assert "saw nothing" in world.calls()[3]["prompt"]
        assert st.live_check is not None
        assert st.live_check["report_md"] == LIVE_BAD[0]["text"]
    finally:
        sched.close()


def test_question_tag_rests_and_send_answers_it(world: Env) -> None:
    turns = [PLAN, reply("Which name?\n\nQ: name?"), IMPL, LIVE_OK, IMPL, LIVE_OK]
    sched, _ = boot(world, *turns, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "implement")
        assert st.last_tag == "Q"
        with pytest.raises(RunnerError, match="empty"):
            sched.send(CARD, "  ")
        sched.send(CARD, "call it hello.txt")
        wait_stage(world, sched, "gate")
        assert "call it hello.txt" in world.calls()[2]["prompt"]
        users = [e["text"] for e in sched.bus.history(CARD, 0) if e["kind"] == "user"]
        assert users == ["call it hello.txt"]
        sched.send(CARD, "also add a newline")
        wait(lambda: len(world.calls()) == 6)
        wait_stage(world, sched, "gate")
        assert "also add a newline" in world.calls()[4]["prompt"]
    finally:
        sched.close()


def test_no_status_tag_is_nudged_twice_then_retried_fresh_then_needs_you(world: Env) -> None:
    tagless = [reply(text) for text in ("done-ish", "still", "hm", "no")]
    sched, _ = boot(world, PLAN, *tagless, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.error is not None
        assert "without a status tag" in st.error
        assert "no status tag line" in world.calls()[2]["prompt"]
    finally:
        sched.close()


def test_needs_spec_reads_markers() -> None:
    def item(body: str, check: str | None = None) -> Item:
        return Item("abcd1234", 0, "t", body, "kuhyx/demo", "todo", check)

    assert needs_spec(item("make it nicer"))
    assert not needs_spec(item("x\ndone: it prints hi"))
    assert not needs_spec(item("x", "true"))
