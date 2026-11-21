"""Every peer change reaches the open drawer as a `peer` live event with the row (T2473).

The live check measured the Peer row lagging 1-4 s: the hub published only an activity line, so the drawer saw
the new state only on its 5 s detail poll.
"""

from pathlib import Path

from contract_lib import validate
from peerfakes import CARD, make_world


def test_t2473_send_deliver_and_reply_each_publish_the_row(tmp_path: Path) -> None:
    w = make_world(tmp_path)
    sent = w.hub.send(w.hub.identify(label="a"), CARD, "q")
    w.hub.tick()
    task = w.hub.identify(card=CARD, card_key=w.hub.card_key(CARD))
    w.hub.reply(task, sent["id"], "8790")
    rows = [e["message"] for c, e in w.events if e["type"] == "peer" and c == CARD]
    assert [(r["id"], r["state"]) for r in rows] == [
        (sent["id"], "queued"),
        (sent["id"], "delivered"),
        (sent["id"], "answered"),
    ]
    assert rows[-1] == w.hub.get(sent["id"])
    for _, event in w.events:
        validate("live", {**event, "seq": 1} if event["type"] == "activity" else event)
