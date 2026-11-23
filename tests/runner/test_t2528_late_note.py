"""T2528: a note sent while a card ships reopens it on its session after the ship; a failed ship keeps it."""

from __future__ import annotations

from runnerfakes import Env, FakeClient, make_repo, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait_stage
from todoimpl.board import state as store
from todoimpl.runner import latenote
from todoimpl.runner.files import read_json
from todoimpl.runner.scheduler import Scheduler

NOTE = "remember to ALSO analyze what went well"
IMPL2 = (
    {"_fake": "write", "path": "hello.txt", "text": "hi again\n"},
    {"_fake": "result", "text": "C1: done - cat shows hi again\n\nD: done"},
)


def _to_gate(world: Env) -> tuple[Scheduler, FakeClient]:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, IMPL2, LIVE_OK, done_check="test -f hello.txt")
    sched.start(CARD)
    wait_stage(world, sched, "gate", turns=3)
    st = state(world)
    st.extra["repotask"] = True  # a repo card: the note becomes a part of its repo
    store.save(world.root / CARD, st)
    return sched, client


def test_t2528_a_note_sent_while_shipping_reopens_the_card_on_its_session(world: Env) -> None:
    sched, client = _to_gate(world)
    try:
        session = state(world).sessions["implement"]["session_id"]
        sched.ship(CARD)
        sched.send(CARD, NOTE)  # Shipping: taken, not routed, the ship goes on
        assert read_json(world.root / CARD / "inbox.json") == [NOTE]
        st = wait_stage(world, sched, "gate", turns=4)  # shipped, reopened, implement, live check, checks
        assert client.added == [(st.repo, NOTE, NOTE)]
        assert st.ship is None
        assert st.sessions["implement"]["session_id"] == session
        last = world.calls()[-2]  # the reopened implement turn (the live check came after)
        assert NOTE in last["prompt"]
        assert last["resume"] == session
        assert not (world.root / CARD / latenote.FRESH).exists()
        sched.ship(CARD)
        wait_stage(world, sched, "shipped")
        assert len(client.closed) == 2
    finally:
        sched.close()


def test_t2528_a_failed_ship_keeps_the_note_for_the_retry_turn(world: Env) -> None:
    sched, _ = boot(world)
    try:
        run = world.root / CARD
        st = store.RunState(
            task_id=CARD, stage="failed", error="push refused", repo="kuhyx/demo", session_id="s"
        )
        st.extra.update(failed_stage="shipping", repotask=True)
        store.save(run, st)
        with sched._cv:
            sched.push_note(CARD, NOTE)
            sched.after_drive(CARD)
        assert state(world).stage == "failed"  # no turn by itself: the Retry takes the note
        assert latenote.retry_stage(run, "shipping") == "implement"
        assert latenote.retry_stage(run, "gate") == "implement"
        assert latenote.retry_stage(run, "plan") == "plan"
        (run / "inbox.json").unlink()
        assert latenote.retry_stage(run, "shipping") == "shipping"
    finally:
        sched.close()


def _shipped(world: Env, card: str, *, fresh: bool, repotask: bool = True) -> None:
    st = store.RunState(task_id=card, stage="shipped", repo="kuhyx/demo", session_id="s1", last_tag="D")
    st.extra["repotask"] = repotask
    store.save(world.root / card, st)
    (world.root / card / "inbox.json").write_text(f'["{NOTE}"]', encoding="utf-8")
    if fresh:
        latenote.mark(world.root / card)


def test_t2528_server_start_reopens_only_fresh_notes_of_repo_cards(world: Env) -> None:
    _shipped(world, "abcd1234-0", fresh=True)
    _shipped(world, "abcd1234-1", fresh=False)  # an inbox older than this version: left alone
    _shipped(world, "abcd1234-2", fresh=True, repotask=False)  # no repo card: the note waits for Start
    for broken, text in (("abcd1234-3", "{not json"), ("abcd1234-4", None)):  # unreadable, none: skip
        (world.root / broken).mkdir()
        latenote.mark(world.root / broken)
        if text is not None:
            (world.root / broken / "state.json").write_text(text, encoding="utf-8")
    sched, client = boot(world, reply("D: done"))  # the Scheduler's start-up pass reopens
    try:
        assert store.load(world.root / "abcd1234-1").stage == "shipped"  # type: ignore[union-attr]
        assert store.load(world.root / "abcd1234-2").stage == "shipped"  # type: ignore[union-attr]
        assert read_json(world.root / "abcd1234-2" / "inbox.json") == [NOTE]
        assert [title for _, title, _ in client.added] == [NOTE]
        reopened = store.load(world.root / "abcd1234-0")
        assert reopened is not None
        assert (reopened.stage, reopened.session_id) in (
            ("implement", "s1"),
            ("live_check", "s1"),
            ("checks", "s1"),
        )
    finally:
        sched.close()


def test_t2528_a_refused_part_leaves_the_card_shipped(world: Env) -> None:
    _shipped(world, CARD, fresh=True)
    make_repo(world)
    sched = Scheduler(FakeClient({"abcd1234": task()}, fail_add=1), world.root, check_timeout=20)
    try:
        assert state(world).stage == "shipped"  # the start-up pass tried once
        assert (world.root / CARD / latenote.FRESH).exists()  # the next start tries again
        assert read_json(world.root / CARD / "inbox.json") == [NOTE]
    finally:
        sched.close()
