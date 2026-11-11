"""kuhy's standing grant to board sessions (2026-11-09): they land their own work, never park on asks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import PromptContext

GRANT = (
    "You have kuhy's standing permission to land your own work. Commit freely in the worktree. To land: "
    "`git fetch`, rebase onto origin/{base}, run the repo's gate, `git push origin HEAD:{base}`, and push "
    "any tags; never edit or commit in kuhy's own checkout (~/src/<repo>) working tree. Work in another "
    "repo goes in a worktree you create: `git -C ~/src/<other> worktree add {run_dir}/wt-<name> -b "
    "todo/<item id> origin/main`, landed the same way. Also granted: run installers, confirm scripts and "
    "other repo scripts, write marker files, approve your own drafts, edit ~/src/todo through a worktree. "
    "Never write test or probe notes into kuhy's real todo app (its MCP, the `todo` CLI, its data): a "
    "check that needs notes uses a fake MCP or a scratch data dir under {run_dir}; abandon any you "
    "leaked before `D:`. "
    "Long jobs run via "
    "`systemd-run --user --collect`; wait for them, no 60 s limit applies. Ask kuhy only for a `Q:` question "
    "round, a check only he can see, hear or touch (phone, audio, screen), or a physical tap; never for "
    "permission."
)
DEPLOY = (
    "Done means deployed: after Ship pushes, the server runs the repo's `- deploy: `<command>`` bullet from "
    "CLAUDE.md (Commands section). If CLAUDE.md has no `- deploy: `<command>`` line, add one that installs, "
    "releases and deploys this change everywhere it runs; it is idempotent and exits non-zero unless its own "
    "health check passes. Never uninstall an app or `pm clear`. A service that runs from "
    "~/src/<repo> updates it with `git -C ~/src/<repo> pull --ff-only` (fails on a dirty tree)."
)
REBASE_NOTE = (
    "(runner) The worktree was rebased onto {ref} and has conflicts: resolve them first (fix the files, "
    "`git add`, `git rebase --continue`), then carry on."
)


def grant(ctx: PromptContext) -> str:
    """Return the standing grant with this run's base branch and run dir filled in."""
    return GRANT.format(base=ctx.base, run_dir=ctx.run_dir)
