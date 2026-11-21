"""Who is talking: the board gives every sender an id on first contact and shows it as `<label>#<id4>`.

A sender sends its id back on later calls; an id is bound to its label, so a different label gets a new
one. Two senders with one label get two ids. `task:<card>` senders are never stored: their id derives
from the token, and only a caller holding the card's key (`token.card_key`) may speak as one. A label
recipient must have polled its inbox once, else it counts as unknown.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.runner.files import read_json, write_json

from . import token as tokens
from .envelope import TASK_PREFIX, label_problem
from .limits import Refusal

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class Sender:
    """One sender: its board-given id, its label, whether it ever polled its inbox."""

    id: str
    label: str
    polled: bool = False

    @property
    def display(self) -> str:
        """`<label>#<id4>`, as the card and the envelope show it."""
        return f"{self.label}#{self.id}"

    @property
    def card(self) -> str | None:
        """The card of a board session's sender, None for any other."""
        return self.label.removeprefix(TASK_PREFIX) if self.label.startswith(TASK_PREFIX) else None


class Senders:
    """The registry in `<root>/peer/senders.json`; callers hold the hub's lock."""

    def __init__(self, root: Path, token: str) -> None:
        """Load the stored senders."""
        self._path = root / "peer" / "senders.json"
        self._token = token
        raw = read_json(self._path)
        rows = raw if isinstance(raw, dict) else {}
        self._known = {
            str(k): Sender(str(k), str(v["label"]), bool(v.get("polled")))
            for k, v in rows.items()
            if isinstance(v, dict) and "label" in v
        }

    def _save(self) -> None:
        write_json(self._path, {s.id: {"label": s.label, "polled": s.polled} for s in self._known.values()})

    def task(self, card: str) -> Sender:
        """The sender a board session of `card` speaks as."""
        return Sender(tokens.derive(self._token, f"id:{card}")[:4], f"{TASK_PREFIX}{card}", polled=True)

    def identify(
        self, label: str | None, sender: str | None = None, card: str | None = None, card_key: str | None = None
    ) -> Sender:
        """Resolve a caller; a new label (or a stale id) registers a fresh sender."""
        if card is not None:
            if not tokens.same(card_key, tokens.card_key(self._token, card)):
                msg = "the card key does not match"
                raise Refusal(msg, code="forbidden")
            return self.task(card)
        if not label or (problem := label_problem(label)) is not None:
            raise Refusal(problem if label else "a label is required")
        found = self._known.get(sender or "")
        if found is not None and found.label == label:
            return found
        new = secrets.token_hex(2)
        while new in self._known:
            new = secrets.token_hex(2)  # pragma: no cover - a 1-in-65536 collision
        self._known[new] = Sender(new, label)
        self._save()
        return self._known[new]

    def polled(self, who: Sender) -> None:
        """Note that `who` polled its inbox: it may now be sent to."""
        if who.id in self._known and not self._known[who.id].polled:
            self._known[who.id] = Sender(who.id, who.label, polled=True)
            self._save()

    def find(self, to: str) -> Sender | None:
        """A label recipient by id, `<label>#<id>` or a bare label that is unique; None when unknown."""
        label, _, wanted = to.rpartition("#")
        if wanted in self._known and (not label or self._known[wanted].label == label):
            hit = self._known[wanted]
        else:
            same = [s for s in self._known.values() if s.label == to]
            if len(same) > 1:
                msg = f"label {to} is ambiguous: use <label>#<id>"
                raise Refusal(msg)
            hit = same[0] if same else None
        return hit if hit is not None and hit.polled else None
