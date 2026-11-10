# Cheap tier and card order

Two board rules that sit beside `DOCS-spec.md`. Code: `server/todoimpl/runner/{tier,tiering,freegate}.py`,
`prompts/tier.py`, `board/badges.py`, `board/board.py` (`build_board`).

## Human-made notes first

The todo MCP reports `created_by` (`kuhy` or `claude`) on `list_tasks`, `get_task` and `search_tasks`. A note
without it (old notes) counts as `kuhy`, and so does any value other than `claude`. `todo_mcp/parse.py` reads the
`created_by:` line of `get_task` (falling back to the older `by:` line) and an optional sixth tab column of the
list lines; `Task`, `Item` and `CardTask` carry it. Inside every board column, kuhy's cards sort above Claude-made
ones, before the Needs-you order (questions, effort, longest waiting). The page renders the server order and never
sorts; the card payload has no `created_by`.

## The cheap tier: Sonnet manager, free models, Opus last

A card is tier `cheap` when its section text (the item body) has a line `Tier: cheap` (case-insensitive) or its
title contains `text-free (textgate-rework)`. The tier is decided once, at the run's first implement-role turn, and
stored in `state.extra.tier` (`cheap` | `normal`); before a run the card derives it from the note.

For a cheap run the **implement role** (the implement and fix stages and the live check, one session) runs on
`sonnet` instead of `opus`. The credit route (`credit.py`) is sonnet for every role anyway.

1. **Free models, only when allowed.** Before each implement or fix turn the server asks `freegate.check`: the
   `claude-free` and `free-llm-check-dir` tools exist, `free-llm-check-dir <worktree>` approves (public repo only:
   free providers log prompts; the check reads the GitHub origin's visibility, so a worktree under `~/.cache`
   passes for a public repo), `~/.config/omniroute/api_key` exists and the gateway (`http://127.0.0.1:20128`,
   `$TODOIMPL_FREE_GATEWAY`) answers `GET /v1/models` within 2 s. The verdict is `state.extra.free_models`.
2. **Allowed:** the prompt gets the manager addendum. Sonnet writes each bounded sub-task to a file and runs it
   through the server's worker command (`python -m todoimpl.runner.freeworker <worktree> <file> <log> --issues
   <run dir> --child <repo>`, never raw `claude-free`: it loads kuhy's `~/.claude` and answers with a grilling
   round instead of editing). The command runs `claude-free` with hooks off and a no-questions preamble, logs to
   `<log>` and exits 0 only when the worktree changed. Sonnet reads each diff, runs the checks itself, repairs
   permission blocks the worker hit, and redoes or finishes what it botched. Every free-model problem goes to
   `<run dir>/free-issues.jsonl` (format and the raw `GET /api/task/<id>/issues` in `DOCS-umbrella.md`); a gateway
   failure the server saw is logged there too.
3. **Not allowed** (private repo, gateway down, tool missing): the addendum says to do the work alone, no
   `claude-free`. The feed names the reason.
4. **Escalation, at most once per run.** A cheap implement turn that ends with a line `ESCALATE: <reason>`, or
   that fails (the existing failure path, which retries on a timer), makes the next implement-role turn run on
   `opus` with the normal prompt plus the reason (`state.extra.escalated`, `escalate_reason`). The session is
   resumed, so Opus sees the work done. After that an `ESCALATE:` line is ignored.

The feed gets a `tier ...` line at each decision and at the escalation. The card shows icon-only badges (tooltip and
aria-label only): a coin (cheap), a gift (free models allowed and not escalated), an up arrow (escalated). Contracts:
`common.schema.json` `tier_badges` on the card, `state.schema.json` `tier`, `free_models`, `escalated`,
`escalate_reason`.

Not covered: a red Checks run (`check_fixes`) does not escalate; only a failed or `ESCALATE:` implement turn does.
