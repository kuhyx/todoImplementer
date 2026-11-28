"""The peer hub: sends, replies, waits and inboxes, plus `tick`, which delivers, confirms and expires.

A message to a task waits `queued` until `tick` writes it into the task's live session (`pipe.write`) and
the session's stream replays it (`pipe.echoed`): only then is it `delivered`. A landing step holds it
(`live` says `held`); a turn that ends before reading it gets it written again into the next one. A message
to a label waits in that sender's inbox. Undelivered for EXPIRE seconds, or its session gone: `expired`.
Every change is published on the card's bus, so the card shows it at once.
"""

from __future__ import annotations

import re
import secrets
import threading
import uuid
from typing import TYPE_CHECKING, Any

from . import deliver, envelope, limits
from . import token as tokens
from .book import OPEN, Book, view
from .limits import Refusal, Window
from .senders import Sender, Senders

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

CARD_ID = re.compile(r"[A-Za-z0-9]{8}-[0-9]+")
SHORT_ID = re.compile(r"[A-Za-z0-9]{8}")
ENDED = deliver.ENDED


class Hub:
    """All peer state behind one lock; `wait` and `inbox` sleep on its condition."""

    def __init__(  # noqa: PLR0913 - the hub's collaborators, all keyword seams
        self,
        root: Path,
        token: str,
        *,
        clock: Callable[[], float],
        live: Callable[[str], str | None],
        pipe: deliver.Pipe,
        publish: Callable[[str, dict[str, Any]], None],
    ) -> None:
        """Load the stored senders and threads."""
        self._root, self._token, self._clock, self._live = root, token, clock, live
        self._pipe, self._publish = pipe, publish
        self._cv = threading.Condition()
        self._senders = Senders(root, token)
        self._book = Book(root)
        self._rates = Window()

    @property
    def root(self) -> Path:
        """The run root (a board session's run dir is `<root>/<card>`)."""
        return self._root

    def token_ok(self, given: str | None) -> bool:  # noqa: D102
        return tokens.same(given, self._token)

    def card_key(self, card: str) -> str:  # noqa: D102
        return tokens.card_key(self._token, card)

    def task_sender(self, card: str) -> Sender:  # noqa: D102
        return self._senders.task(card)

    def identify(
        self,
        label: str | None = None,
        sender: str | None = None,
        card: str | None = None,
        card_key: str | None = None,
    ) -> Sender:
        """Resolve the caller (Senders.identify)."""
        with self._cv:
            return self._senders.identify(label, sender, card, card_key)

    def _target(self, to: str) -> tuple[str | None, Sender]:
        """(task card or None, recipient) for `to`: a card id, a short id or a label."""
        if CARD_ID.fullmatch(to) or SHORT_ID.fullmatch(to):
            known = [to] if CARD_ID.fullmatch(to) else sorted(p.name for p in self._root.glob(f"{to}-*"))
            known = [card for card in known if (self._root / card).is_dir()]
            if not known:
                msg = f"unknown task {to}"
                raise Refusal(msg, code="not_found")
            live = [card for card in known if self._live(card)]
            if len(live) != 1:
                msg = f"task {to} has no live session" if not live else f"{to} names {len(live)} live tasks"
                raise Refusal(msg, code="disabled")
            return live[0], self._senders.task(live[0])
        found = self._senders.find(to)
        if found is None:
            msg = f"unknown recipient {to}: it never polled its inbox"
            raise Refusal(msg, code="not_found")
        return None, found

    @staticmethod
    def _body(text: str) -> None:
        if not text.strip():
            msg = "the message is empty"
            raise Refusal(msg)
        if len(text.encode()) > limits.MAX_BYTES:
            msg = f"the message is over {limits.MAX_BYTES // 1024} KB"
            raise Refusal(msg)

    def _caps(self, who: Sender, target: Sender, now: float) -> None:
        pending = sum(1 for m in self._book.queued() if m["to_id"] == target.id)
        if pending >= limits.MAX_PENDING:
            msg = f"{target.display} already has {pending} pending messages"
            raise Refusal(msg, limits.PENDING_RETRY, "disabled")
        if (wait := self._rates.retry_after(who.id, now, limits.PER_SENDER)) is not None:
            msg = f"over {limits.PER_SENDER} messages per minute from {who.display}"
            raise Refusal(msg, wait, "disabled")
        if (wait := self._rates.retry_after("*", now, limits.GLOBAL)) is not None:
            msg = f"over {limits.GLOBAL} messages per minute across all senders"
            raise Refusal(msg, wait, "disabled")

    def send(self, who: Sender, to: str, text: str, reply_to: str | None = None) -> dict[str, Any]:
        """File a message for `to`; raise Refusal with the reason (and retry time) when it may not go."""
        self._body(text)
        with self._cv:
            now = self._clock()
            card, target = self._target(to)
            home = card or who.card
            if home is None:
                msg = "a label recipient takes messages from board sessions only"
                raise Refusal(msg)
            hop = 1
            if reply_to:
                parent = self._book.get(reply_to)
                if parent is None:
                    msg = f"unknown message {reply_to}"
                    raise Refusal(msg, code="not_found")
                hop = int(parent["hop"]) + 1
            msg_id = f"{home}.{secrets.token_hex(6)}"
            row: dict[str, Any] = {
                "id": msg_id, "card": home, "to_card": card, "from": who.display, "from_id": who.id,
                "to": target.display, "to_id": target.id, "text": text, "state": OPEN, "reply": None,
                "hop": hop, "reply_to": reply_to or None, "at": now, "delivered_at": None,
                "answered_at": None,
                "reason": None, "uuid": str(uuid.uuid4()), "mark": None,
            }  # fmt: skip
            if hop > limits.MAX_HOPS:
                row |= {"state": "dead_end", "reason": f"over {limits.MAX_HOPS} hops"}
                self._file(row)
                msg = f"the thread is over {limits.MAX_HOPS} hops: a dead end"
                raise Refusal(msg, code="disabled")
            self._caps(who, target, now)
            self._rates.note(who.id, now)
            self._rates.note("*", now)
            self._file(row)
            return view(row)

    def _file(self, row: dict[str, Any]) -> None:
        self._book.add(row)
        self._changed(row)

    def _changed(self, row: dict[str, Any], *, save: bool = False) -> None:
        if save:
            self._book.save(str(row["card"]))
        shown = {
            "type": "activity", "at": self._clock(), "kind": "system", "tool": None,
            "text": f"{row['from']} → {row['to']}: {row['state']}",
        }  # fmt: skip
        self._publish(str(row["card"]), shown)
        # the row itself: the open drawer merges it at once (T2473)
        self._publish(str(row["card"]), {"type": "peer", "message": view(row)})
        self._cv.notify_all()

    def _known(self, msg_id: str) -> dict[str, Any]:
        row = self._book.get(msg_id)
        if row is None:
            msg = f"unknown message {msg_id}"
            raise Refusal(msg, code="not_found")
        return row

    def reply(self, who: Sender, msg_id: str, text: str) -> dict[str, Any]:
        """Answer a message; only its recipient may, once."""
        self._body(text)
        with self._cv:
            row = self._known(msg_id)
            if row["to_id"] != who.id:
                msg = "only the recipient may answer this message"
                raise Refusal(msg, code="forbidden")
            if row["state"] in ENDED:
                msg = f"the message is already {row['state'].replace('_', ' ')}"
                raise Refusal(msg, code="disabled")
            now = self._clock()
            row |= {"state": "answered", "reply": text, "answered_at": now}
            row["delivered_at"] = row["delivered_at"] or now
            self._changed(row, save=True)
            return view(row)

    def get(self, msg_id: str) -> dict[str, Any]:
        """One message as shown."""
        with self._cv:
            return view(self._known(msg_id))

    def wait(self, msg_id: str, timeout: float) -> dict[str, Any]:
        """Wait up to `timeout` s for the message to be answered or to expire; return it as it is then."""
        with self._cv:
            row = self._known(msg_id)
            self._cv.wait_for(lambda: row["state"] in ENDED, timeout)
            return view(row)

    def inbox(self, who: Sender, wait: float) -> list[dict[str, Any]]:
        """Hand `who` its queued messages (now delivered), waiting up to `wait` s for the first."""
        with self._cv:
            self._senders.polled(who)

            def mine() -> list[dict[str, Any]]:
                return [m for m in self._book.queued() if m["to_id"] == who.id and m["to_card"] is None]

            self._cv.wait_for(mine, wait)
            rows, now = mine(), self._clock()
            for row in rows:
                row["state"], row["delivered_at"] = "delivered", now
                self._changed(row, save=True)
            return [{**view(r), "text": envelope.wrap(r["from"], r["id"], r["hop"], r["text"])} for r in rows]

    def thread(self, card: str) -> list[dict[str, Any]]:
        """Return the card's Peer thread."""
        with self._cv:
            return [view(m) for m in self._book.thread(card)]

    def tick(self) -> None:
        """Deliver what can go, confirm what was read, expire what waited too long (deliver.py)."""
        with self._cv:
            deliver.tick(self._book, self._live, self._pipe, self._clock(), self._changed)
