"""The `free` route (T2531): a card's turn through `claude-free` (OmniRoute's free models), Claude being out.

kuhy (2026-11-27): public-repo cards only, every role, no Claude manager. The turn is the plan route's own
argv with `claude-free` in front, so streams, sessions, tags and adoption work unchanged; it keeps the free
worker's guarantees (no-questions preamble, `srcwall` read-only checkouts, no push). Free work never ships
by itself: `free_unverified` holds Ship until a Claude live-check turn re-checks it (`freeverify.py`).

`eligible` sits on the engine's queue (under its lock), so it never blocks (`freeok.py`).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board.clone import src_root

from . import claude, freegate, freeok, srcwall
from .freeworker import DENY, PREAMBLE

if TYPE_CHECKING:
    from todoimpl.board.state import RunState

FREE = "free"
MODEL = "free-best"
UNVERIFIED = "free_unverified"
REPORTS = ("plan.md", "live_check.md")  # what a role writes to the run dir, never into the repo
PATHS = "Write every file the task names by absolute path (plan.md, live_check.md) exactly at that path."
# A free implement turn once pushed its commit to main before any Claude check (T2613): the turn loses the
# landing grant, and its git cannot push (the deny list misses `git -C <wt> push`).
NO_LAND = "Never push, tag or deploy: commit in the worktree only; a Claude turn checks and lands free work."
LANDING = re.compile(
    r"You have kuhy's standing permission to land your own work\..*?landed the same way\. ", re.DOTALL
)
REFUSED = "/nonexistent/free-turns-never-push"
PUSH_BLOCK = (
    ("remote.origin.pushurl", REFUSED),
    (f"url.{REFUSED}.pushInsteadOf", "git@github.com:"),
    (f"url.{REFUSED}.pushInsteadOf", "https://github.com/"),
)


def free_bin() -> str:
    """`$TODOIMPL_FREE_CLAUDE`, else `claude-free` on PATH, else ~/.local/bin/claude-free."""
    found = os.environ.get("TODOIMPL_FREE_CLAUDE") or shutil.which(freegate.WORKER)
    return found or str(Path.home() / ".local" / "bin" / freegate.WORKER)


def eligible(st: RunState | None) -> bool:
    """May this run's turns go free: a public repo, no app-error signature, the gateway up."""
    return st is not None and freeok.may_go_free(st.repo, st.note_body)


def build(  # noqa: PLR0913, PLR0917 - same signature as claude.build
    role: str,
    prompt: str,
    worktree: Path,
    resume: str | None = None,
    extra_dirs: tuple[Path, ...] = (),
    allow: tuple[str, ...] = (),
    model: str | None = None,  # noqa: ARG001 - every role runs `free-best`
    effort: str | None = None,
) -> claude.Invocation:
    """Build a free turn: the plan argv on `claude-free`, behind the src wall, told never to ask."""
    task = LANDING.sub(f"{NO_LAND} ", prompt) if LANDING.search(prompt) else f"{prompt}\n{NO_LAND}"
    inv = claude.build(
        role, f"{PREAMBLE} {PATHS}\n\n{task}", worktree, resume, extra_dirs, allow, MODEL, effort
    )
    wall, unguarded = srcwall.wrap(worktree, src_root())
    argv = [*wall, free_bin(), *inv.argv[1:]]  # claude-free checks the repo is public once more itself
    at = argv.index("--disallowedTools") + 1 if "--disallowedTools" in argv else len(argv)
    argv[at:at] = DENY if at < len(argv) else ["--disallowedTools", *DENY]  # one list: never two flags
    notes = (*inv.notes, *((f"free turn without the src wall: {unguarded}",) if unguarded else ()))
    return claude.Invocation(tuple(argv), no_push(inv.env), inv.cwd, notes, route=FREE, peer=inv.peer)


def no_push(env: dict[str, str]) -> dict[str, str]:
    """Add git config by env that sends every push to a missing path, after any config entries already set."""
    out = dict(env)
    start = int(out.get("GIT_CONFIG_COUNT") or 0)
    for i, (key, value) in enumerate(PUSH_BLOCK, start):
        out[f"GIT_CONFIG_KEY_{i}"], out[f"GIT_CONFIG_VALUE_{i}"] = key, value
    out["GIT_CONFIG_COUNT"] = str(start + len(PUSH_BLOCK))
    return out


def banner(route: str, role: str, wanted: str, ran: str) -> str:
    """Return the feed line that opens a turn: which route runs it, and a credit turn's smaller model."""
    if route == FREE:
        return f"turn on free models ({MODEL} through claude-free): the {role} role wants {wanted}"
    if route != "credits":
        return "turn on the plan"
    if ran != wanted:  # every role on credits runs on the `credits_model` setting; the feed says so
        return f"turn on free API credits: the {role} role wants {wanted}, runs on {ran}"
    return "turn on free API credits (Agent SDK)"


def collect(run_dir: Path, worktree: Path) -> list[str]:
    """Move the run-dir reports a free model wrote into the worktree root instead; return their names."""
    moved = []
    for name in REPORTS:
        stray, home = worktree / name, run_dir / name
        if stray.is_file() and not home.exists():
            stray.replace(home)
            moved.append(name)
    return moved


def after_turn(st: RunState, route: str, role: str, *, ok: bool, dirs: tuple[Path, Path]) -> None:
    """Mark the run unverified after a free turn; clear it after a Claude live check that ran to its end.

    `dirs` = (run dir, worktree): a free turn's reports that landed in the worktree move to the run dir.
    """
    if route == FREE:
        st.extra[UNVERIFIED] = True
        collect(*dirs)
    elif role == "live_check" and ok:
        st.extra.pop(UNVERIFIED, None)
