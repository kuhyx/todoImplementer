"""CLI: `python -m todoimpl.merge --group <id,...> --title <text> [--dry-run]`, same path as the click."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from todoimpl.board.state import run_root
from todoimpl.service.cards import card_tasks
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.model import TodoError

from .apply import MergeError, apply_merge, repos_of
from .store import MergeStore
from .text import combined_body, umbrella_text
from .umbrella import create_umbrella

if TYPE_CHECKING:
    from collections.abc import Sequence

    from todoimpl.service.cards import CardTask


def resolve(client: TodoClient, token: str) -> list[CardTask]:
    """`abcd1234-2` is that section; `abcd1234` is the note's only section (more than one is ambiguous)."""
    note_id, _, index = token.partition("-")
    cards = card_tasks(client.get_task(note_id))
    if index:
        if not index.isdigit() or int(index) >= len(cards):
            msg = f"{token}: no such section"
            raise MergeError(msg, "bad_request")
        return [cards[int(index)]]
    if len(cards) != 1:
        msg = f"{token} has {len(cards)} sections: name one as {token}-N"
        raise MergeError(msg, "bad_request")
    return cards


def main(argv: Sequence[str] | None = None) -> int:
    """Merge the named notes into one; `--dry-run` prints the new note's text and changes nothing."""
    parser = argparse.ArgumentParser(prog="python -m todoimpl.merge", description=__doc__)
    parser.add_argument("--group", required=True, help="comma-separated ids: abcd1234-N or abcd1234")
    parser.add_argument("--title", required=True, help="title of the merged note")
    parser.add_argument("--dry-run", action="store_true", help="print the merged note, change nothing")
    args = parser.parse_args(argv)
    try:
        client = TodoClient.from_env()
        cards = [card for token in args.group.split(",") if token for card in resolve(client, token.strip())]
        if args.dry_run:
            same_repo = len(repos_of(cards)) == 1
            print(
                f"# {args.title}\n{combined_body(cards)}" if same_repo else umbrella_text(args.title, cards)
            )
            return 0
        root = run_root()
        done = apply_merge(client, root, MergeStore(root), cards, args.title, create_umbrella)
    except (MergeError, TodoError) as exc:
        print(f"merge: {getattr(exc, 'message', exc)}", file=sys.stderr)
        return 1
    print(
        f"merged into {done.new_id} ({done.kind}); removed {len(done.removed)}: {', '.join(done.removed)}; "
        f"closed in place {len(done.closed)}: {', '.join(done.closed)}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
