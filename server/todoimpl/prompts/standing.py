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
    "Long jobs run via `systemd-run --user --collect --slice=todoimpl.slice`; wait for them, no 60 s limit "
    "applies. Builds (make, flutter, gradle, pnpm, pytest, cargo, ...) queue on one machine-wide build lock, "
    "so a wait is normal: never kill a waiting build to retry. Phone, device, emulator and E2E checks are "
    "yours: run them yourself on the Pixel or emulator, never hand them to kuhy. Ask kuhy only for a `Q:` "
    "question round, a decision, a check only he can hear (audio) or a physical tap; never for "
    "permission. Never end on `A:` for something you can run yourself (a command, `deploy-todoimpl`, a "
    "restart, sudo, a push, a write under ~ outside ~/src/<repo>): run it, then rerun the checks. "
    "When you do need kuhy, put it in a fenced `ask` block, one line each: "
    "`choice <id>: <title> | opt | *recommended | risk=reversible`, `command <id>: <exact command>`, "
    "`screenshot <id>: <what to check> | shots/<name>.png`; the board shows buttons, never prose. "
    "Do everything else yourself and log the automatic choice."
)
DEPLOY = (
    "Done means deployed: after Ship pushes, the server runs the repo's `- deploy: `<command>`` bullet from "
    "CLAUDE.md (Commands section). If CLAUDE.md has no `- deploy: `<command>`` line, add one that installs, "
    "releases and deploys this change everywhere it runs; it is idempotent and exits non-zero unless its own "
    "health check passes. Never uninstall an app or `pm clear`. A service that runs from "
    "~/src/<repo> updates it with `git -C ~/src/<repo> pull --ff-only` (fails on a dirty tree); a repo "
    "checked out elsewhere (claude-config lives in ~/.claude) pulls in that checkout. "
    'A red deploy comes back to you as a fix turn with its output: a deploy check such as "X changed after '
    '<tag>: bump and release" is yours to fix (bump the version, commit, tag, push the tag, push, redeploy, '
    "read the result), never a reason to end on `A:`."
)
REBASE_NOTE = (
    "(runner) The worktree was rebased onto {ref} and has conflicts: resolve them first (fix the files, "
    "`git add`, `git rebase --continue`), then carry on."
)


def grant(ctx: PromptContext) -> str:
    """Return the standing grant with this run's base branch and run dir filled in."""
    return GRANT.format(base=ctx.base, run_dir=ctx.run_dir)
