"""One todo note per repo (kuhy's rule): merge a repo's open notes into one.

`python -m todoimpl.repotask.migrate` prints the plan and writes nothing; `--apply` does it. Sections move
as `## ` sections to the end of the repo's target note (no existing section id changes), then the emptied
note is closed with evidence `merged into <target id8>`. A note with an older run in flight is skipped until
the run is shipped or cancelled: moving its sections would orphan the run's branch and dir. DOCS-repotask.md
has the rules.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from todoimpl.board.state import run_root
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.items import sections
from todoimpl.todo_mcp.model import Task, TodoError
from todoimpl.umbrella.note import is_umbrella

from . import legacy
from .ids import norm

PRIORITIES = ("low", "medium", "high")
CHECK = "done_check:"


@dataclass
class RepoPlan:
    """What to do for one repo that has several open notes."""

    repo: str
    target: str
    priority: str
    sources: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _has_check(lines: list[str]) -> bool:
    return any(line.strip().lower().startswith(CHECK) for line in lines)


def _block(title: str, lines: list[str], check: str | None) -> str:
    """One `## ` section; the note-level done_check becomes a line inside it when the section has none."""
    body = list(lines)
    if check and not _has_check(body):
        body.insert(0, f"{CHECK} {check}")
    return "\n".join([f"## {title}", *body]).rstrip()


def blocks(note: Task) -> list[str]:
    """Return the open `## ` sections of a note as text (a note with none is one; so is text before them)."""
    found = sections(note.body)
    if not found:
        return [_block(note.title, note.body.split("\n"), note.done_check)]
    lines = note.body.split("\n")
    preamble = "\n".join(lines[: found[0].heading]).strip()
    check = note.done_check if len(found) == 1 else None
    out = [_block(note.title, preamble.split("\n"), None)] if preamble else []
    return out + [_block(s.title, s.lines, check) for s in found if not s.done]


def target_body(note: Task) -> str:
    """Return the target's body as the merge starts from it: a note without sections becomes section 0."""
    found = sections(note.body)
    if not found:
        return "\n".join(blocks(note))
    if len(found) == 1 and note.done_check and not _has_check(found[0].lines):
        lines = note.body.split("\n")
        lines.insert(found[0].heading + 1, f"{CHECK} {note.done_check}")
        return "\n".join(lines)
    return note.body


def _busy(root: Path, note: Task) -> bool:
    count = max(len(sections(note.body)), 1)
    return any(legacy.in_flight(root, f"{note.id[:8]}-{i}") for i in range(count))


def plan(notes: list[Task], root: Path) -> list[RepoPlan]:
    """Return one plan per repo with more than one open note (umbrellas and repo-less notes never merge)."""
    by_repo: dict[str, list[Task]] = {}
    for note in notes:
        if note.repo and not is_umbrella(note.body):
            by_repo.setdefault(norm(note.repo), []).append(note)
    plans = []
    for group in by_repo.values():
        if len(group) < 2:  # noqa: PLR2004 - one note is already what the rule asks for
            continue
        busy = {note.id[:8] for note in group if _busy(root, note)}
        order = sorted(group, key=lambda n: (n.id[:8] not in busy, -len(sections(n.body)), n.id))
        target, rest = order[0], order[1:]
        top = max((n.priority for n in group), key=lambda p: PRIORITIES.index(p) if p in PRIORITIES else 1)
        found = RepoPlan(target.repo or "", target.id[:8], top)
        for note in rest:
            if note.id[:8] in busy:
                found.skipped[note.id[:8]] = "an older run is still in flight"
            else:
                found.sources.append(note.id[:8])
        plans.append(found)
    return sorted(plans, key=lambda p: p.repo)


def move(client: TodoClient, one: RepoPlan, source_id: str) -> int:
    """Append the source's open sections to the target, check they arrived, close the source."""
    source, target = client.get_task(source_id), client.get_task(one.target)
    moving = [text for text in blocks(source) if _flat(text) not in _flat(target.body)]
    if moving:
        body = "\n\n".join([target_body(target).rstrip(), *moving])
        priority = one.priority if one.priority != target.priority else None
        updated = client.update_task(one.target, body=body, priority=priority)
        missing = [text for text in moving if _flat(text) not in _flat(updated.body)]
        if missing:
            msg = f"{one.target} did not take the sections of {source_id}: nothing was closed"
            raise TodoError(msg)
    client.close_task(source_id, f"merged into {one.target}")
    return len(moving)


def open_notes(client: TodoClient, tries: int = 3) -> list[Task]:
    """List the open notes in full; a note closed between listing and fetch (others write too) is retried."""
    for attempt in range(1, tries + 1):
        try:
            return client.list_tasks(full=True)
        except TodoError:
            if attempt == tries:
                raise
    return []  # pragma: no cover - the loop returns or raises


def render(plans: list[RepoPlan], *, applied: bool) -> list[str]:
    """Return the report lines, ending with the counts."""
    lines = []
    for one in plans:
        lines.append(f"{one.repo}: into {one.target} <- {', '.join(one.sources) or '(none yet)'}")
        lines += [f"  skipped {note}: {why}" for note, why in one.skipped.items()]
    merging = sum(len(one.sources) for one in plans)
    skipped = sum(len(one.skipped) for one in plans)
    verb = "merged" if applied else "would merge"
    lines.append(
        f"repos with more than one note: {len(plans)}; notes {verb}: {merging}; "
        f"skipped (run in flight): {skipped}"
    )
    return lines


def main(argv: list[str] | None = None, client: TodoClient | None = None) -> int:
    """Print the plan; with `--apply` carry it out. Exit 1 when the todo app refuses something."""
    cli = argparse.ArgumentParser(prog="migrate", description="Merge each repo's open notes into one note.")
    cli.add_argument("--apply", action="store_true", help="write the merge; without it nothing is changed")
    cli.add_argument(
        "--root", type=Path, default=None, help="run root holding the older runs (default: the board's)"
    )
    args = cli.parse_args(argv)
    root = args.root or run_root()
    try:
        todo = client or TodoClient.from_env()
        plans = plan(open_notes(todo), root)
        if args.apply:
            for one in plans:
                for source in one.sources:
                    move(todo, one, source)
    except TodoError as exc:
        print(f"todo app: {exc}", file=sys.stderr)
        return 1
    print("\n".join(render(plans, applied=args.apply)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
