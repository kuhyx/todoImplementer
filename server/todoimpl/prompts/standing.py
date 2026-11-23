"""kuhy's standing grant to board sessions (2026-11-09): they land their own work, never park on asks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import PromptContext

NIGHT = (
    "kuhy sleeps from 22:55 to 05:55 (local time; his phone is locked out of the board then): in that "
    "window work fully on your own, take the recommended answer to every question and log it; a question "
    "you positively cannot answer yourself goes in an `ask` block for the morning, after you have done "
    "every part and step that does not need it. "
)
GRANT = (
    "You have kuhy's standing permission to land your own work. Commit freely in the worktree. To land: "
    "`git fetch`, rebase onto origin/{base}, run the repo's gate, `git push origin HEAD:{base}`, and push "
    "any tags; never edit or commit in kuhy's own checkout (~/src/<repo>) working tree, nor stash, "
    "check out, apply or reset files there (a dirty checkout that blocks a deploy is the board's to set "
    "aside). Work in another repo goes in a worktree you create: `git -C ~/src/<other> worktree add "
    "{run_dir}/wt-<name> -b "
    "todo/<item id> origin/main`, landed the same way. Also granted: run installers, confirm scripts and "
    "other repo scripts, write marker files, approve your own drafts (never a `(kuhy)` criterion), edit "
    "~/src/todo through a worktree. "
    "Never write test or probe notes into kuhy's real todo app (its MCP, the `todo` CLI, its data): a "
    "check that needs notes uses a fake MCP or a scratch data dir under {run_dir}; abandon any you "
    "leaked before `D:`. "
    "The board files any stretch over 60 s with no tool call or reply as a top-priority bug, so each tool "
    "call is one step that ends within 60 s: one gate step or test shard per call, `git push` and a deploy "
    "as calls of their own, never chained after a gate; the inner loop runs only the tests of changed "
    "files. Only a job that cannot be split (a release build) runs via `systemd-run --user --collect "
    "--slice=todoimpl.slice`; wait for it in 40 s slices. Builds (flutter, gradle, pnpm, pytest, cargo, ...) "
    "queue in arrival order on a "
    "machine-wide build lock (three builds at once) that the shims take for you, so a wait is normal: "
    "never kill a waiting build "
    "to retry, never touch build.lock, its holder file or build.queue by hand, never poll it with "
    "`flock -n`, and never lock a whole script: run `bash x.sh` plainly (`systemd-run -E PATH`) and each "
    "heavy tool inside takes the lock itself. Phone, device, emulator and E2E checks are "
    "yours: run them yourself on the Pixel or emulator, never hand them to kuhy. Ask kuhy only for a `Q:` "
    "question round, a decision, a check only he can hear (audio) or a physical tap; never for "
    "permission. Never end on `A:` for something you can run yourself (a command, `deploy-todoimpl`, a "
    "restart, sudo, a push, a write under ~ outside ~/src/<repo>): run it, then rerun the checks. "
    "When you do need kuhy, put it in a fenced `ask` block, one line each: "
    "`choice <id>: <title> | opt | *recommended | risk=reversible`, `command <id>: <exact command>`, "
    "`screenshot <id>: <what to check> | shots/<name>.png`; the board shows buttons, never prose. "
    "Anything kuhy must look at (a logo, a layout, a page, a result) goes into the task itself: save "
    "pictures under `{run_dir}/shots/` and show them with a `screenshot` line; never tell him to open a "
    "bare path. "
    "If a page truly must be opened, give its full absolute URL (scheme, host, port, path). "
    "Do everything else yourself and log the automatic choice. "
    "A note you file for a new project names its repo `kuhyx/<name>` and holds a line `visibility: public` "
    "or `visibility: private` (private when absent): Start creates a missing kuhyx repo with it. "
    + NIGHT.rstrip()
)
WAITS = (
    "Waits (kuhy, 2026-11-19; the board kills a dead wait once you are silent 5 min): wait on an event, "
    "never poll, and in slices: one call waits at most 40 s. A long job starts once as a named unit without "
    "`--wait` (`systemd-run --user --collect --unit=<name> ...`); each later call waits on it at most 40 s "
    "(`timeout 40 tail --pid=$(systemctl --user show -p MainPID --value <name>) -f /dev/null`, then "
    "`systemctl --user is-active <name>`) and never starts it again; likewise `timeout 40 inotifywait ...` "
    "and `timeout 40 gh run watch` (T2427). Never follow a log (`tail -f <log>`, `journalctl -f`): it never "
    "ends; no self-made `until`/`while ... sleep` loop when "
    "an event wait exists. Never `pgrep -f` "
    "a pattern that is in your own command line (it matches itself and never ends). Never start a "
    "background job (`&`) inside `$(...)`: it holds the pipe open, a deadlock. No `flock -n` polling and "
    "no when_free.sh: a build waits on the lock by itself. Never wait on another card's process or unit: "
    'the board sequences cards. Never print periodic "still waiting" output to look alive.'
)
DEPLOY = (
    "Done means deployed: after Ship pushes, the server runs the repo's `- deploy: `<command>`` bullet from "
    "CLAUDE.md (Commands section). If CLAUDE.md has no `- deploy: `<command>`` line, add one that installs, "
    "releases and deploys this change everywhere it runs; it is idempotent and exits non-zero unless its own "
    "health check passes. Only when nothing of the repo runs or installs anywhere, write `- deploy: none "
    "(<why>)` instead. Never uninstall an app or `pm clear`. A service that runs from "
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
