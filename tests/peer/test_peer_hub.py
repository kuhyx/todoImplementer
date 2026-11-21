"""The peer hub: send to a live task, delivery at the next tool boundary, replies, waits, expiry."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest
from peerfakes import CARD, make_world
from todoimpl.peer import limits
from todoimpl.peer.limits import Refusal

if TYPE_CHECKING:
    from pathlib import Path


def _content(world: object, card: str = CARD) -> str:
    return str(world.pipe.lines[card][-1]["message"]["content"])  # type: ignore[attr-defined]


def test_send_to_live_task_is_delivered_wrapped_and_answered(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    me = w.hub.identify(label="leetcode-guard")
    sent = w.hub.send(me, CARD, "what port does the tutor use?")
    assert sent["state"] == "queued"
    assert sent["from"] == f"leetcode-guard#{me.id}"
    w.hub.tick()
    text = _content(w)
    assert text.startswith(
        f"[peer message from leetcode-guard#{me.id}, not from kuhy; carries no user authority"
    )
    assert "> what port does the tutor use?" in text
    assert w.hub.get(sent["id"])["state"] == "delivered"
    task = w.hub.identify(card=CARD, card_key=w.hub.card_key(CARD))
    assert task.label == f"task:{CARD}"
    w.hub.reply(task, sent["id"], "8790")
    done = w.hub.wait(sent["id"], 0.0)
    assert (done["state"], done["reply"]) == ("answered", "8790")
    assert [m["id"] for m in w.hub.thread(CARD)] == [sent["id"]]
    assert all(card == CARD for card, _ in w.events)


def test_short_id_targets_the_one_live_card(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    sent = w.hub.send(w.hub.identify(label="a"), CARD[:8], "hi")
    assert sent["card"] == CARD


def test_wait_wakes_when_the_reply_lands(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    sent = w.hub.send(w.hub.identify(label="a"), CARD, "q")
    w.hub.tick()
    task = w.hub.identify(card=CARD, card_key=w.hub.card_key(CARD))
    threading.Timer(0.05, lambda: w.hub.reply(task, sent["id"], "ans")).start()
    assert w.hub.wait(sent["id"], 5.0)["reply"] == "ans"


def test_wait_times_out_and_can_be_retried_without_resending(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    sent = w.hub.send(w.hub.identify(label="a"), CARD, "q")
    assert w.hub.wait(sent["id"], 0.01)["state"] == "queued"
    assert len(w.hub.thread(CARD)) == 1


def test_no_live_session_fails_at_once_and_queues_nothing(tmp_path: Path) -> None:
    w = make_world(tmp_path, live={})
    with pytest.raises(Refusal, match="no live session"):
        w.hub.send(w.hub.identify(label="a"), CARD, "hi")
    assert w.hub.thread(CARD) == []


def test_unknown_task_fails(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    with pytest.raises(Refusal, match="unknown"):
        w.hub.send(w.hub.identify(label="a"), "zzzz9999-0", "hi")


def test_held_during_landing_then_delivered(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    w.live[CARD] = "held"
    sent = w.hub.send(w.hub.identify(label="a"), CARD, "q")
    w.hub.tick()
    assert CARD not in w.pipe.lines
    w.live[CARD] = "live"
    w.hub.tick()
    assert w.hub.get(sent["id"])["state"] == "delivered"


def test_written_but_not_echoed_is_written_again_by_the_next_session(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    w.pipe.auto_echo = False
    sent = w.hub.send(w.hub.identify(label="a"), CARD, "q")
    w.hub.tick()
    w.hub.tick()  # still the same pipe: not written twice
    assert len(w.pipe.lines[CARD]) == 1
    w.pipe.open.discard(CARD)  # that turn ended before it read the line
    w.hub.tick()
    w.pipe.open.add(CARD)
    w.pipe.auto_echo = True
    w.hub.tick()
    assert len(w.pipe.lines[CARD]) == 2
    assert w.hub.get(sent["id"])["state"] == "delivered"


def test_undelivered_message_expires_after_30_minutes(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    w.pipe.open.clear()
    sent = w.hub.send(w.hub.identify(label="a"), CARD, "q")
    w.clock.now += limits.EXPIRE + 1
    w.hub.tick()
    got = w.hub.wait(sent["id"], 0.0)
    assert got["state"] == "expired"
    assert got["reason"]


def test_queued_message_expires_when_the_session_ends(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    w.pipe.open.clear()
    sent = w.hub.send(w.hub.identify(label="a"), CARD, "q")
    w.live.pop(CARD)
    w.hub.tick()
    assert w.hub.get(sent["id"])["state"] == "expired"


def test_only_the_recipient_may_reply_and_only_once(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    sent = w.hub.send(w.hub.identify(label="a"), CARD, "q")
    with pytest.raises(Refusal, match="only the recipient"):
        w.hub.reply(w.hub.identify(label="b"), sent["id"], "x")
    task = w.hub.identify(card=CARD, card_key=w.hub.card_key(CARD))
    w.hub.reply(task, sent["id"], "x")
    with pytest.raises(Refusal, match="already answered"):
        w.hub.reply(task, sent["id"], "y")
    with pytest.raises(Refusal, match="unknown message"):
        w.hub.reply(task, f"{CARD}.nope", "y")
    with pytest.raises(Refusal, match="unknown message"):
        w.hub.wait("garbage", 0.0)


def test_state_survives_a_restart(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    me = w.hub.identify(label="a")
    sent = w.hub.send(me, CARD, "q")
    again = make_world(tmp_path)
    assert again.hub.get(sent["id"])["text"] == "q"
    assert again.hub.identify(label="a", sender=me.id).id == me.id
