# todoImplementer

Board that plans, implements, reviews, verifies and (on kuhy's click) ships todo-app notes with headless Claude Code
sessions. Spec and decisions: `DOCS-spec.md`. Lessons carried over from the predecessor: `DOCS-lessons.md`. Claude API key lifecycle: `DOCS-apikey.md`. Free API credits, routes, overage guard: `DOCS-credits.md`. Sessions land their own work (grant, backstop, rebase, ship): `DOCS-landing.md`. Model, effort, live-check role, turn limit, retries: `DOCS-turns.md`. Umbrella notes (many per-repo tasks, one card, the exponential ramp, free-worker command, issue log): `DOCS-umbrella.md`.
Cheap tier (Sonnet manager, free models, Opus escalation) and human-made-first order: `DOCS-tiers.md`.
Multi-day survival (kills, reboot, power cut, no internet, gateway down, durable writes, backoff ladder): `DOCS-resilience.md`.
Umbrella tracking view and the free-token strip (gateway quotas, cooldowns, ETA): `DOCS-tracking.md`.
Merging similar tasks (Haiku suggestions, one-click merge, umbrella notes, CLI): `DOCS-merge.md`.
One card, one run per repo (parts, ticks, per-repo lock, section-run transition, note migration CLI): `DOCS-repotask.md`.

## Commands

- run: `./run.sh` (`scripts/deploy.sh`: deps, build, restart, check `/version`; then opens the page)
- test: `make test`
- test-changed: `scripts/test_changed.sh`
- lint: `make lint`
- coverage: `make test`
- coverage-gaps: `coverage-gaps coverage.xml`
- gate: `make fast`

## Rules

- **Done means `make fast` is green** (line cap, private scan, markdown names, regression tags, ruff, mypy strict,
  pytest at 100 % line and branch, web lint and tests once `web/` exists). Run heavy commands through
  `~/.claude/scripts/capped.sh`; every single command stays under 60 s.
- **Restarting or deploying the server (`scripts/deploy.sh`) is always safe while sessions run**: turns are their
  own systemd units and the new server adopts them on start (DOCS-spec.md, "Turns outlive the server").
- **250 lines per file**, code and prose (lockfiles exempt by name). Split by concern.
- **Bugs are regressions first.** A bug gets a row in `tests/regressions/DOCS-*.md` (`| T<N> | what | test |`) and a
  test named `test_t<N>_...` (pytest) or titled `[T<N>] ...` (vitest) that is red before the fix. A pragma or a
  coverage exclusion needs kuhy's OK in the commit message.
- **Hermetic tests.** Temp `HOME` and `$TODOIMPL_HOME`; shims first on `PATH` for `claude` and `git push` (a push
  fails the test); a fake todo MCP. No real todo note, repo, network or `~/.cache` is touched.
- **Contracts.** `contracts/*.schema.json` (2020-12) fix state.json and every `/api` shape; server and web tests
  validate against them; change schema and both sides in one commit. `scripts/contract_lib.py` loads them.
- **One server-computed status per task.** The page never computes status; actions are offered only when they can
  succeed and a disabled one carries its reason. A change shows within 100 ms; a wait of 1 s or more shows a loader
  naming what it waits on.
- **No company identifiers.** `scripts/check_private.py` scans files, paths and the commit message against
  `~/.config/todoImplementer/private-denylist.txt` (outside the repo, mode 0600). Never copy code from the predecessor.
- Markdown: only `README.md`, `CLAUDE*.md`, `DOCS*.md`. Tasks live in the todo app, never in a TODO file.
- Python 3.15.2 (newest stable, enforced by the freshness gate), stdlib only at runtime, uv, exact pins, newest stable. Web: Astro + TypeScript, pnpm only.

## Boundaries

- Always: write the failing check first; run `make fast` before a commit; add `Todo: <id8>` trailers; keep
  the server on 127.0.0.1 with Origin and CSRF checks on every POST.
- Ask first: new dependencies, new endpoints or schema changes, anything that touches `~/src/todo`, the Caddy
  or systemd setup, or a real repo; creating the GitHub repo.
- Never: force-push, edit or commit in kuhy's own checkout working tree (~/src/<repo>), write outside a task's
  worktree and run dir (defaults of a board session, see below), commit `*.zip`, secrets or company identifiers,
  edit the todo app's code (a board session may, in its own worktree), add video recording, remote hosts, meetings or Windows/macOS.
- Session policy (kuhy's call, 2026-11-06): `~/.config/todoImplementer/session-policy.json` (`$TODOIMPL_POLICY`; keys
  `permission_mode`, `add_dirs`, `disable_hooks`, `deny`) can loosen the push and outside-worktree limits for board
  sessions (loose mode, more dirs, hooks off, no deny list) and lifts the auto-allow never-list. See `DOCS-spec.md`,
  "Permission blocks heal themselves". Tests keep the push-refusing shim.
