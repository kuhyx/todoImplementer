"""Merge N open cards into one note: the single code path under the POST endpoint and the CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from todoimpl.service.cards import card_tasks
from todoimpl.todo_mcp.items import split_items
from todoimpl.todo_mcp.model import TodoError

from .live import live_reason
from .remove import remove_members
from .text import combined_body, fingerprint, umbrella_text

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.service.cards import CardTask
    from todoimpl.todo_mcp.client import TodoClient

    from .store import MergeStore

PRIORITIES = ("low", "medium", "high")
OPEN = ("todo", "in progress")
UPSTREAM = "upstream_unavailable"
MIN_MEMBERS = 2
ID8 = 8


class MergeError(Exception):
    """A refusal; `code` is one of the http error codes (bad_request, disabled, conflict, ...)."""

    def __init__(self, message: str, code: str) -> None:
        """Keep the text the page shows and the code."""
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class MergeResult:
    """The merged note, the members cut out of their notes and those closed in place.

    `new_id` is a card id for kind `repo`, a note id8 for `umbrella`.
    """

    new_id: str
    kind: str
    removed: tuple[str, ...]
    closed: tuple[str, ...]


def repos_of(cards: list[CardTask]) -> set[str]:
    """Return the repos the members name; a note with no repo names none."""
    return {card.repo for card in cards if card.repo}


def _check(cards: list[CardTask], title: str) -> None:
    ids = [card.id for card in cards]
    if not title.strip():
        msg = "the merged note needs a title"
        raise MergeError(msg, "bad_request")
    if len(set(ids)) != len(ids) or len(ids) < MIN_MEMBERS:
        msg = "a merge needs at least two different notes"
        raise MergeError(msg, "bad_request")
    missing = next((card.id for card in cards if not card.repo), None)
    # A repo-less note joins the one repo its partners name (T2093).
    if missing is not None and len(repos_of(cards)) != 1:
        msg = f"{missing} has no repo and the others do not name one repo"
        raise MergeError(msg, "bad_request")


def _still_open(client: TodoClient, card: CardTask) -> bool:
    """Read fresh whether the very section is still there and open; a rerun skips the rest."""
    items = split_items(client.get_task(card.item.note_id))
    index = card.item.index
    return index < len(items) and items[index].title == card.title and items[index].status != "done"


def _locate(client: TodoClient, repo: str, title: str) -> str | None:
    """Return the card id of the open card with this title in the repo, None when there is none."""
    for note in client.list_tasks(repo=repo, full=True):
        found = next((c.id for c in card_tasks(note) if c.title == title and c.status != "done"), None)
        if found is not None:
            return found
    return None


def _create_in_repo(client: TodoClient, repo: str, title: str, cards: list[CardTask]) -> str:
    """Append the combined card to the repo's note; return its card id."""
    if _locate(client, repo, title) is not None:
        msg = f"{repo} already has an open note titled {title!r}"
        raise MergeError(msg, "conflict")
    rank = {name: i for i, name in enumerate(PRIORITIES)}
    top = max((card.priority for card in cards), key=lambda p: rank.get(p, 1))
    client.add_task(repo, title, combined_body(cards), priority=top)
    found = _locate(client, repo, title)
    if found is None:
        msg = f"the combined note {title!r} was added but not found"
        raise MergeError(msg, "internal")
    return found


def _verify_umbrella(client: TodoClient, new_id: str) -> None:
    """Fail closed: no member is touched unless the todo app has the umbrella note."""
    try:
        client.get_task(new_id)
    except TodoError as exc:
        msg = f"umbrella note {new_id} is not in the todo app: {exc}"
        raise MergeError(msg, UPSTREAM) from exc


def _members_left(client: TodoClient, cards: list[CardTask], ref: dict[str, Any] | None) -> list[CardTask]:
    """First run: every member must be open. A rerun: only members still the very section recorded."""
    if ref is None:
        if any(card.status not in OPEN for card in cards):
            msg = "every member must be an open note"
            raise MergeError(msg, "bad_request")
        return cards
    titles = ref["titles"]
    return [c for c in cards if titles.get(c.id) == c.title and c.status != "done" and _still_open(client, c)]


def apply_merge(  # noqa: PLR0913, PLR0917 - the collaborators, all injectable
    client: TodoClient,
    root: Path,
    store: MergeStore,
    cards: list[CardTask],
    title: str,
    create_umbrella: Callable[[str], str],
) -> MergeResult:
    """Create the combined or umbrella note, then take every member out of its note.

    One repo: one new card in that repo's note. Several repos: an umbrella note with no repo (made by
    `create_umbrella`, which returns its full id). The new id and the member titles are stored per group
    fingerprint before any member is touched, so a rerun after a failure finishes the rest instead of making a
    second note, and never touches a section that moved. A member is cut out of its note when that renumbers
    no section that has a run (remove.py); otherwise it is closed in place with `merged into <new id>`.
    """
    _check(cards, title)
    fp = fingerprint(card.id for card in cards)
    ref: dict[str, Any] | None = store.load().created.get(fp)
    todo = _members_left(client, cards, ref)
    if (why := live_reason(root, [card.id for card in todo])) is not None:
        raise MergeError(why, "disabled")
    repos = repos_of(cards)
    kind = "repo" if len(repos) == 1 else "umbrella"
    repo = next(iter(repos))
    if ref is None:
        if kind == "repo":
            made = _create_in_repo(client, repo, title.strip(), cards)
        else:
            made = create_umbrella(umbrella_text(title.strip(), cards))[:ID8]
        fresh: dict[str, Any] = {"id": made, "titles": {card.id: card.title for card in cards}}
        store.update(lambda state: state.created.update({fp: fresh}))
        ref = fresh
    if kind == "umbrella":
        _verify_umbrella(client, ref["id"])
    removed, rest, finished = remove_members(client, root, todo)
    new_id = ref["id"]
    if kind == "repo":  # cutting sections out of the repo's note may have renumbered the new card
        new_id = _locate(client, repo, title.strip()) or new_id
        ref = {**ref, "id": new_id}
        store.update(lambda state: state.created.update({fp: ref}))
    evidence = f"merged into {new_id}"
    for note_id in finished:
        client.close_task(note_id, evidence)
    for card in rest:
        client.close_item(card.item, evidence)
    return MergeResult(new_id, kind, tuple(card.id for card in removed), tuple(card.id for card in rest))
