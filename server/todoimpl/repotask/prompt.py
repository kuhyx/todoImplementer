"""The repo task's addendum to every stage prompt: the parts in work order and the command that ticks them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.asks.view import decided

from .tick import command

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.todo_mcp.items import Item


def addendum(item: Item, run_dir: Path) -> str:
    """Return the text for a repo task's item; "" for a section (no parts)."""
    if not item.parts:
        return ""
    tick = command(run_dir)
    work = [part for part in item.parts if part.actionable]
    lines = [
        (
            "Repo task: ONE run, ONE worktree and ONE session for every part below. Work the parts in this "
            "order, one after the other:"
        ),
        *(f"{n}. [{part.key}] {part.title}" for n, part in enumerate(work, 1)),
    ]
    lines += [
        f"[{p.key}] is yours now: kuhy made its MANUAL WORK REQUIRED decisions. Build exactly these, "
        "even where the note recommended otherwise: " + "; ".join(decided(p.body, run_dir))
        for p in work
        if p.manual
    ]
    human = [part for part in item.parts if part.human]
    held = [part for part in item.parts if part.held]
    if human:
        lines.append("Human work, not yours, skip: " + "; ".join(f"[{p.key}] {p.title}" for p in human))
    lines += [
        f"Earlier work on [{p.key}]: {p.prior}. Reuse what is sound instead of starting over."
        for p in work
        if p.prior
    ]
    if held:
        lines.append(
            "Owned by an older run, do not touch: " + "; ".join(f"[{p.key}] {p.title}" for p in held)
        )
    lines.append(
        f"When a part is finished and checked, tick it: `{tick} done <key>`. To split a big part, write the "
        f'steps first: `{tick} split <key> "step one" "step two"`, then `{tick} step <key> <n>` per finished '
        "step. Never end the implement stage with `D:` while a part is unticked: finish it, or say with `A:` "
        "what stops you. Only ticked parts are closed in the todo app when kuhy ships."
    )
    return "\n".join(lines)
