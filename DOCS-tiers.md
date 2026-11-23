# Cheap tier and card order

Three board rules that sit beside `DOCS-spec.md`. Code: `server/todoimpl/runner/{tier,tiering,freegate}.py`,
`prompts/tier.py`, `board/badges.py`, `board/board.py` (`build_board`), `runner/{srcwall,srcguard}.py`.

## Human-made notes first

The todo MCP reports `created_by` (`kuhy` or `claude`) on `list_tasks`, `get_task` and `search_tasks`. A note
without it (old notes) counts as `kuhy`, and so does any value other than `claude`. `todo_mcp/parse.py` reads the
`created_by:` line of `get_task` (falling back to the older `by:` line) and an optional sixth tab column of the
list lines; `Task`, `Item` and `CardTask` carry it. Inside every board column, kuhy's cards sort above Claude-made
ones, before the Needs-you order (questions, effort, longest waiting). The page renders the server order and never
sorts; the card payload has no `created_by`.

## The cheap tier: Opus manager, free models, higher effort last

A card is tier `cheap` when its section text (the item body) has a line `Tier: cheap` (case-insensitive) or its
title contains `text-free (textgate-rework)`. A repo card (`DOCS-repotask.md`) is titled after the repo, so the title
of any part the run works counts too (T1999): one cheap part makes the card cheap, as a `Tier:` line in any part did.
A card holding an app error ticket (an `Error-Signature:` line) is never cheap: kuhy keeps error fixes off free
models (2026-11-21, T2445).
The scope is kuhy's, not a default: he asked for free models on the textgate reworks (note 4f77d502, 2026-11-10) and
set Opus medium as the default model (`DOCS-turns.md`); every other card stays `normal`. Measured 2026-11-12: cheap
cards averaged $26 against $14 for normal ones (n = 9 and 62), so widening the tier would not cut spend.
The tier is decided once per cycle, at the first implement-role turn, and
stored in `state.extra.tier` (`cheap` | `normal`); before a run the card derives it from the note. A new repo-card
cycle (`repotask/cycle.py`) clears `tier`, `free_models`, `escalated` and `escalate_reason` (T1999): the card id outlives
its cycles and the parts change.

For a cheap run the **implement role** (the implement and fix stages, one session; the live check is its own
role since T1896) runs on
`opus` at `--effort high` (kuhy, 2026-11-10: the manager is Opus, not Sonnet; high since 2026-11-21, T2476; `runner/tier.py` `MANAGER_*`). The
credit route (`credit.py`) runs the `credits_model` setting (default `claude-opus-5-5`) for every role and passes the effort to the SDK.

1. **Free models, only when allowed.** Before each implement or fix turn the server asks `freegate.check`: the
   `claude-free` and `free-llm-check-dir` tools exist, `free-llm-check-dir <worktree>` approves (public repo only:
   free providers log prompts; the check reads the GitHub origin's visibility, so a worktree under `~/.cache`
   passes for a public repo), `~/.config/omniroute/api_key` exists and the gateway (`http://127.0.0.1:20128`,
   `$TODOIMPL_FREE_GATEWAY`) answers `GET /v1/models` within 2 s. The verdict is `state.extra.free_models`.
2. **Allowed:** the prompt gets the manager addendum. Opus writes each bounded sub-task to a file and runs it
   through the server's worker command (`python -m todoimpl.runner.freeworker <worktree> <file> <log> --issues
   <run dir> --child <repo>`, never raw `claude-free`: it loads kuhy's `~/.claude` and answers with a grilling
   round instead of editing). The command runs `claude-free` with hooks off and a no-questions preamble, logs to
   `<log>` and exits 0 only when the worktree changed. Opus reads each diff, runs the checks itself, repairs
   permission blocks the worker hit, and **coaches** a worker that failed, declined or misread: it diagnoses why
   (log, diff), fixes the cause (clearer prompt, missing context such as the textgate rules, a smaller task) and
   reruns the worker, up to 3 coached attempts, each logged with phase `prompt`. Only after that does it finish the
   work itself. Never the edits first (`DOCS-umbrella.md`, "Coaching"). A textgate note gets the rules in the
   addendum. Every free-model problem goes to
   `<run dir>/free-issues.jsonl` (format and the raw `GET /api/task/<id>/issues` in `DOCS-umbrella.md`); a gateway
   failure the server saw is logged there too.
3. **Not allowed** (private repo, gateway down, tool missing): the addendum says to do the work alone, no
   `claude-free`. The feed names the reason.
4. **Escalation, at most once per run.** A cheap implement turn that ends with a line `ESCALATE: <reason>`, or
   that fails (the existing failure path, which retries on a timer), makes the next implement-role turn run at `--effort xhigh`
   (same model, more thought) with the normal prompt plus the reason (`state.extra.escalated`, `escalate_reason`). The session is
   resumed, so it sees the work done. After that an `ESCALATE:` line is ignored.

The feed gets a `tier ...` line at each decision and at the escalation. The card shows icon-only badges (tooltip and
aria-label only): a coin (cheap), a gift (free models allowed and not escalated), an up arrow (escalated). Contracts:
`common.schema.json` `tier_badges` on the card, `state.schema.json` `tier`, `free_models`, `escalated`,
`escalate_reason`.

Not covered: a red Checks run (`check_fixes`) does not escalate; only a failed or `ESCALATE:` implement turn does.

## kuhy's checkouts stay his (T2464, T2515, T2519)

Sessions work in worktrees; kuhy's checkouts under `~/src` (`$TODOIMPL_SRC`) are his. Free models are the
untrusted tier, so their workers get a wall; board turns stay unrestricted (they deploy from `~/src/<repo>`) and
are watched instead. Umbrella 7808ee0a-0 is why: its workers wrote a logo into nine other repos' checkouts, by
`Edit` first (T2464) and later by shell (child -49, repo todoImplementer, into book-guard, dufs-cloud and signal-bot).

- **Writer deny, every turn.** `Edit`/`Write`/`MultiEdit`/`NotebookEdit` are denied under the src root for free
  workers (T2464) and every board turn (T2515, `policy.src_deny_for`), whatever kuhy's policy says: his
  `add_dirs: ["~"]` covers `~/src` and `--add-dir` cannot leave it out. A turn whose cwd is there (closing) skips it.
  The worker's task file names its repo ("everywhere" means that repo) and its prompt names the worktree.
- **The wall, free workers only** (`runner/srcwall.py`). `freeworker` runs `claude-free` under bubblewrap: the
  whole filesystem as it is, the src root mounted read-only, then the worktree and its shared git dir
  (`git rev-parse --git-common-dir`, inside `~/src/<repo>/.git`) writable again, so the worker still commits. No
  network or pid namespace; `--die-with-parent`; a signal still shows as exit 128 + N. No `bwrap`, or one that
  cannot make a namespace (probed once with `bwrap --dev-bind / / -- true`), runs the worker unwalled and logs
  `<src> stays writable (...)` to `free-issues.jsonl`, phase `checkout`.
- **Detection, every turn** (`runner/srcguard.py`). Each board turn and each unwalled worker attempt snapshots
  `git --no-optional-locks status --porcelain -z --untracked-files=all` of every `<src>/*/.git` checkout plus the
  card's own (16 side by side, 10 s cap per repo; a stuck repo is left out) into `<stem>.checkout.json`, with a
  sha256 per dirty file cached by inode, size and mtime. At the end, files dirty afterwards that were clean or held
  other content go to `<run>/checkout-edits.jsonl` (`at`, `stem`, `card`, `checkout`, `files`) and a feed line (a
  worker's to `free-issues.jsonl`): "left edits" for the card's own checkout, "changed while this turn ran" for
  another (it may be kuhy's or a parallel card's edit). A walled worker scans its own checkout only: it cannot write the others. Measured
  2026-11-23 on 98 checkouts under the 10 % CPU cap: 0.34 s cold, 0.11-0.19 s warm, off the request path (the
  card's own thread). A snapshot from before T2519 (one checkout) still counts.
- **Attribution.** `srcguard.attributed` / `owner` tell the stray stash (T2512, T2514) whether edits still sitting
  in a checkout are exactly one card's; an owned stray is set aside at once (T2518). Only rows of the card's own
  repo count (`own: true`): a change a turn saw in another repo may be kuhy's live edit, so it is logged but owned
  by nobody and keeps the 30 min quiet wait. An edit two cards both saw land has no owner either.
