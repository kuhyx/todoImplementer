# Sessions land their own work (kuhy, 2026-11-09)

Board sessions kept parking cards on asks that were only permission ("OK me to commit and push", "press Retry",
"send a `LONG:` turn", "editing main is off-limits"). The decision: a session lands its own work and asks kuhy only
for what he alone can give.

## The grant (`server/todoimpl/prompts/standing.py`, T1862)

Every work-stage prompt (implement, fix, resume, fresh, live_check) carries it:

- Commit freely in the worktree. To land: `git fetch`, rebase onto `origin/<base>`, run the repo's gate,
  `git push origin HEAD:<base>`, push any tags. `<base>` is the repo's default branch (`extra["base_branch"]`).
- Never edit or commit in kuhy's own checkout (`~/src/<repo>`) working tree. Work in another repo goes in a worktree
  the session creates under its run dir (`git -C ~/src/<other> worktree add <run dir>/wt-<name> -b todo/<item id>
  origin/main`), landed the same way. `~/src/todo` is edited the same way.
- Also granted: installers, confirm scripts and other repo scripts, marker files, approving its own drafts.
- Heavy commands still go through `capped.sh`; there is no 60 s limit for a session, long jobs run via
  `systemd-run --user --collect` and the session waits.
- kuhy is asked only for a `Q:` question round, a check only he can see, hear or touch (phone, audio, screen) and
  physical taps.

Sessions need the session policy (`~/.config/todoImplementer/session-policy.json`) to push: without one the built-in
`git push` deny still applies (DOCS-spec.md, "Permission blocks heal themselves").

## Backstop (`runner/grant.py`, T1863)

A turn that ends on `A:` whose concrete ask (`board/ask.py`) matches the permission regex (OK me, approve,
permission, may I, whether to commit|push|merge, press Retry, send a `LONG:`, write ... by hand, run ... yourself,
after the server commits, off-limits ...) resumes the same session once per stage with a fixed `(runner) Granted:`
note and a feed line `auto-granted, the session resumes: <ask>`. The counter is `extra["ask_grants"]`; it clears when
a turn ends on anything but `A:` and on Start/Retry. A second permission ask parks the card as before. Not used in the
spec and plan stages, nor while a phone wait is set. No LLM.

## Rebase on every drive (`runner/worktree.py`, T1864)

`attach` runs at the start of each drive: fetch, then `git rebase --autostash origin/<base>` in a reused worktree,
and `base_sha` is recomputed. Work the session already pushed (HEAD on origin, past the old base) is left alone and
keeps its old base, so the drawer diff still shows it. A conflict is left as git left it (never aborted):
`extra["rebase_conflict"]` makes every prompt carry "the worktree was rebased onto <ref> and has conflicts: resolve
them first" until HEAD contains the ref again. No rebase in the Ship drive or while an adopted turn is still editing
(T1866); Ship refuses a tree with unresolved conflicts instead of committing the markers.

## Ship (`runner/ship.py`, T1865)

A branch the session committed ships as before (squash, rebase, gate, push). A branch with a clean tree whose HEAD is
on origin closes the item with "Pushed by the session: <short shas>." and cleans up; no commit, no checks, and
`state.ship` has no `pushed_at`. Partly pushed work squashes only what origin lacks (the merge base is the last
pushed commit).
