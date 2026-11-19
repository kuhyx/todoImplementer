# Umbrella notes: many per-repo tasks, one card, an exponential ramp

kuhy's design (2026-11-10). About 56 "Make <app> text-free (textgate-rework)" sections sit in per-repo notes. One
umbrella note collects them; one Opus manager runs free workers for them in rounds that widen 1, 2, 4, 8 while the
free tier proves itself. Code: `server/todoimpl/umbrella/`, `runner/freeworker.py`, `prompts/umbrella.py`,
`board/umbrella.py`. The free tier of single notes is `DOCS-tiers.md`; the tracking view of a run is `DOCS-tracking.md`;
kills, reboots and outages are `DOCS-resilience.md`.

## The note (frozen format)

```
# <title>
Umbrella: per-repo
Tier: cheap
- [ ] kuhyx/<repo> (<source note id8>)
## kuhyx/<repo> (<source note id8>)
<the original section text, with its own `done_check:` and `Scan ...: N items` lines>
```

- Recognised by an `Umbrella: per-repo` line in the header (before the first `## ` heading, outside code fences),
  before the "no repo means Yours" rule. The note has no `repo`; one with a repo works the same.
- Its `## ` sections are the **children**, not items: `split_items` returns ONE item, so the board has one card
  `<note id8>-0`. Only headings shaped `## kuhyx/<repo> (<id8>)` start a child; any other `##` inside a child's text
  stays in that text. Each child's **run id** is `<umbrella id8>-<position + 1>` (`note.Child.cid`, e.g.
  `2d0704cd-7`): its own namespace, so a child never shares a branch (`todo/<run id>`), worktree, gate unit or
  phone lease with a live card of its source note (a merge cuts and renumbers those). The position is the
  section's place in the umbrella note, so sections are never cut from an umbrella. The checkbox is found by its
  label (`note.Child.label`: the source id8, or the card id when two children are sections of one note).
- Children done = ticked header checkbox (`- [x]`). The runner ticks it through the todo app (`update_task` with
  the new body, `TodoClient.tick_child`, one at a time under a lock in `ItemView`) when the child ships. When every
  child is done the note is closed with `close_task` and evidence (`client.close_item` closes an umbrella directly:
  it never marks a `## [x]` section).
- Dropped child = `- [-]` box (T1924): counts as done for closing, is never ticked, never runs, and leaves the
  record, its round and the card's counts; a drive stops its turn and frees its repo. Its section stays, so the
  positional ids of the rest hold. A child whose repo `gh api repos/<r>` reports archived (every push refused) is
  dropped when a round would claim it, once per drive; a gh failure reads as not archived.
- `Tier:` is read (`note.tier`) and shown in the record; every umbrella uses the ramp.
- **Written by "Merge similar tasks"** (`DOCS-merge.md`, `merge/text.py`): the heading label is the source note id8,
  or the card id `<id8>-<n>` when two children are sections of one note (that label is then the child id as it
  stands). A member's `done_check:` line arrives renamed `member done_check:`; inside an umbrella it is the child's
  own check, so both spellings are read.
- **Discovery.** The todo MCP's `list_tasks` and `search_tasks` return repo tasks only (`repoTasksOnly` in the
  todo app); `list_tasks(no_repo: true)` (T2058) lists the repo-less ones, and the board reads both, so a
  repo-less umbrella is listed like any note. `umbrella/registry.py` still adds the open umbrellas named by (1) the merge
  ledger `<run root>/merge.json` `created` (a merged umbrella reaches the board with no step by kuhy) and (2)
  `~/.config/todoImplementer/umbrellas.txt` (`$TODOIMPL_UMBRELLAS`; one id per line, `#` comments) for one made by
  hand. Each is fetched with `get_task`. A note with a repo needs no entry.

## Order and rounds

Children are worked easiest first (`note.ordered`): the smallest `Scan ...: N items` number in the child's text;
children without one come after, shortest text first; file order breaks ties. The order is kept in the run record.

Round width `w` starts at 1. Each round:

1. The next `w` children get a worktree each, in `<run dir>/children/<child id>/wt` (`runner/worktree.attach`, base
   `origin/main` of `~/src/<repo>`), a server-written `plan.md` (criteria: the task satisfied, the `done_check`
   passes) and a `task.md`. A repo that is not cloned fails that child alone (it counts against doubling).
2. The server asks `freegate.check` per child: public repo, gateway answering, tools present. Anything else = **not
   free**: the manager does that child itself and it never counts as clean. A dead gateway also writes its exact
   error to the issue log.
3. ONE manager turn (role `manager`, model opus, `--effort medium` (`claude.ROLE_EFFORT`), a fresh session per round, cwd the umbrella run dir) gets
   `prompts/umbrella.py`: the children with worktree, task file, worker log and `free: yes|no`. It starts the free
   workers in parallel, watches them, fixes what they hit (permission blocks, broken edits, failing checks), finishes
   or redoes their work, runs each child's checks, and ends with one line per child:
   `CHILD kuhyx/<repo>: clean` | `coached <n>` | `fixed <what>` | `escalate <reason>` (`ramp.parse_verdicts`; a missing line is an
   escalation; a failed manager turn escalates every child of the round).
4. The server runs each non-escalated child's checks itself (`checks.discover` + `run_all`: its `done_check`, `make
   test`, pre-commit), in parallel, right after the manager. These are the round's checks; the child's own Checks
   stage runs again after its live check.
5. **The server adjudicates** (`ramp.ok`, `ramp.next_width`): a child counts when its line is `clean` (first-try free
   success) or `coached <n>` with n below the cap of 3 (free success after coaching: it proves the coached prompt
   works), it was free, and its checks are green. `fixed` (the manager did the edits) never counts. If every child of the round counts, `w` doubles for the next round; otherwise it stays.
6. Each child then goes through its own pipeline in its own thread, while the next round starts: `escalate` -> one
   higher-effort Opus implement attempt (with `prompts/tier.escalated`); red checks -> a fix turn (the usual `check_fixes` path);
   otherwise Live check -> Checks -> Ship: every child ships when its checks pass, with or without a `done_check`
   (kuhy, 2026-11-10: T1923; since 2026-11-19 every card does, T2060), and a child left at its gate by an older server ships on the next drive,
   and so does a child whose Ship a restart cut (T1905, T1988). Children are normal runs of their repo: `Todo: <source
   id8>` trailer, rebase, gate, push, `DOCS-landing.md` rules. They run on the normal tier (`extra.tier = normal`), never the cheap one.

Rounds continue until every child is taken. A plan limit pauses the umbrella like any run (a child that hit the
limit pauses it with the same `resume_at`; a child on a retry timer pauses it on that timer).

## Free workers: one command, hooks off

Raw `claude-free -p <task>` loads kuhy's whole `~/.claude`; its spec gate answered a fully specified task with a
`❓` grilling round and no edit. Workers are therefore started only through
`python -m todoimpl.runner.freeworker <worktree> <prompt file> <log> [--issues <run dir>] [--child kuhyx/<repo>]`
(`freeworker.command()` gives the shell prefix; the prompts name it, never `claude-free`). It runs `claude-free` with
`policy.HOOKS_OFF`, `--permission-mode bypassPermissions`, `--disallowedTools` for `git push`, and the fixed
preamble "You are a non-interactive worker...never ask questions, never run a spec gate". stdout and stderr go to
the log. Success is the **worktree diff**, never the turn's `subtype: success`: exit 0 = the worktree changed, 3 = no
edit, 4 = no `claude-free`, 5 = killed by a signal on all 3 attempts (`DOCS-resilience.md`; each attempt is a line of `<run dir>/free-workers.jsonl`). A turn with no diff and a `❓` round logs `spec-gate grilling instead of work` (phase
`start`). The single-note cheap tier (`prompts/tier.py`) uses the same command.

**Waiting is code.** A worker marks itself beside its log: `<log>.pid` while it runs, `<log>.exit` (its exit code)
when it is over (`runner/workerwait.py`; starting on a log drops an old `.exit`). The manager does not poll with
Bash calls (each was a full model round trip): it runs `<worker command> wait <log> <log> ...` with the Bash tool
timeout at 600000. That blocks in code until every worker has exited or 540 s passed, and prints one line per worker
(`<log>: exit=<code> <last words>`, `running`, `lost` for a worker that died with no exit record, `not started` after 30 s without a pid file), then
`all N workers finished` (exit 0) or `K of N still running: call wait again` (exit 6). The model is called again
only to read a result, diagnose and coach; a coached rerun uses a new log name.

## Coaching: the manager fixes the cause, not the work

kuhy, 2026-11-10: in round 1 of 2d0704cd a free worker read the title "Focus Guard" as a proper noun, answered "no
changes needed" (exit 3), and the manager simply did the rework itself. That teaches the tier nothing. Both
managers (`prompts/umbrella.py`, `prompts/tier.py`; text in `prompts/coach.py`) are told: when a worker fails,
declines, misreads or leaves a bad diff, **DIAGNOSE** why (worker log, `git diff`), fix the cause and run the
freeworker command again: rewrite or clarify the worker prompt, add the missing context (rules of the
`textgate-rework` and `textgate` skills, scan output, exact files and lines, a worked example) or split the task
smaller. Up to 3 coached attempts per child; each is one issue line with phase `prompt` (symptom = what the worker got
wrong, action = what changed in the prompt or context). Only then may the manager finish itself (`fixed`) or
`escalate`. Never the edits first.

- `coached <n>`: the free worker finished after n coached retries. The server warns in the feed when a free child
  is reported `fixed` with fewer than 3 `prompt` lines since the round began (`issues.coaching`).
- **Textgate children carry the rules.** The worker has no skill context, so `task.md` of a child whose text or
  title mentions textgate or text-free starts with `coach.TEXTGATE_RULES` (condensed from the two skills: a name
  shown in the UI is chrome, "proper noun" is no excuse, a scan item the gate still lists must change; only OS-level
  labels keep the app name). The single-note cheap tier gets the same rules in the manager addendum.

## Issue log: everything that goes wrong with the free models

`<run dir>/free-issues.jsonl`, one JSON line per problem:
`{ts, child, phase (start|edit|tool-call|permission|checks|output|prompt|killed), model, symptom (<=500 chars), action, fixed}`.

- The manager is told to append a line for every problem and for every child it reports `fixed` (the worker log
  names the answering model). The server checks after the manager turn: a `fixed` child with no line since the round
  began gets a feed line `<repo>: reported fixed with no line in free-issues.jsonl`.
- The server writes what it sees itself: gateway probe failures (timeout, HTTP code) at round start
  (`freegate.Verdict.detail`), and the worker command's own findings.
- The single-note cheap tier gets the same file in its run dir (the manager addendum names it; a dead gateway is
  logged by `tiering.plan_turn`).
- `GET /api/task/<id>/issues` returns the raw file (`application/x-ndjson`, empty when there is none; 404 for an
  unknown task). The drawer links it and shows the count per child as icon plus number.

## State

- `state.json` of the umbrella (stage `implement` while rounds and child pipelines run, `shipping` on kuhy's Ship,
  `gate` when no child is working and some wait for Ship, `failed` when children need kuhy, `shipped` at the end)
  carries `extra.umbrella` (`state.schema.json`): `width` of the next round, `kids` (id, repo, title, done) in ease
  order, `rounds` (`n`, `width`, `next`, per child `verdict`, `detail`, `free`, `checks`, `ok`) and `current`, the
  round in progress with its saved steps (free flags, verdicts, check results), so a restart resumes at the step it
  reached and never reruns a manager turn that finished.
- Each child is a full run state at `<run dir>/children/<child id>/state.json` (`worktree` in `wt/`, its own streams,
  `live_check.md`, `plan.md`, `task.md`, `worker-<round>.log`). Nesting keeps them out of every `*/state.json`
  glob of the board, recovery and usage. `files.root_of(run_dir)` maps a child dir back to the run root for the
  allow rules, the overage guard and the gate lock.
- Costs: the card shows the umbrella's own cost plus its children's. Child sessions are not attributed per item by
  the token ingest (they sit below the run-dir level it globs).

## The card and the drawer

One card: the usual status (rules unchanged: working, shipping, needs you...). The card's `umbrella` object
(`common.schema.json` `umbrella_counts`): `done`, `running`, `queued`, `failed`, `total`, `width`, `round`,
`issues`. The page shows one icon plus number per non-empty bucket, the next round width and the issue count; no
words (names live in `aria-label` and `title`). The drawer (`umbrella_detail` in the task response) lists the
round widths, marking the rounds that doubled, and a row per child: its own server-computed status icon, repo,
round, verdict icon, free-worker icon, issue count and its error text. Child rows are built from the child run dirs
(`umbrella/view.py`, overlaid on the run by the service) with the same `status.compute` as any card.

## Actions

- **Start / Retry:** Start (no options; the children bring their own `done_check`). Retry on a
  failed umbrella also restarts the failed, cancelled or asking children at the stage they stopped in
  (`extra.retry_children`).
- **Ship** is no click (T2060): every child ships at its gate through the normal Ship path (squash, rebase, gate,
  push, tick). A child that fails there fails the umbrella with "N of M children need you". The umbrella has no
  Ready to ship rest: once every child is done the note closes, else the umbrella pauses or asks.
- **Cancel** stops the manager and every child turn (`children.Fan`, one handle for all) and cancels the umbrella;
  Restart resumes cancelled children.
- **Send** reaches the next manager turn as a note; a child that ends on a `Q:` or `A:` is treated as needing kuhy.

## Children answer to no one (`umbrella/bounce.py`)

- A child whose live check or implement turn ends on `Q:`/`A:` goes back to implement with the reply as its fix
  brief (3 passes, T1952; the counter resets when a live check passes) and rests on kuhy only after that.
- Red checks get 5 fix turns (T1954) and the brief says old red (stale pins, format) is the child's to fix.
- The card text names what each child waits for: its `A:`/`Q:` line, else its error, else its last issue (T1953).
- A child never ships on unpassed checks (T1955): `_shipping` sends it to Checks first, and the umbrella does not
  close while a done child's checks are not green.
- A child's Ship also deploys (`DOCS-landing.md`, "Done means deployed"). A child that is pushed but not deployed
  (its repo declares no `- deploy:` line, or the deploy failed) fails with "pushed, not deployed: ..."; the card lists
  those apart from children that need kuhy ("N of M children need you: ...; K pushed, not deployed: ...", T1967).
  Retry re-ships such a child without pushing again, and a restart mid-deploy resumes it (T1968). Before that, a
  missing line, a red or killed deploy and a killed or red gate step go back to the child's session or rerun by
  themselves, and children that already failed so are revived on server start (`DOCS-landing.md`, "Ship failures
  Claude can fix", T2340-T2344).

## The one exception to one card per repo

kuhy's rule is one card and one run per repo (`DOCS-repotask.md`); the umbrella (cross-repo text-free batch, kuhy's
earlier explicit request) stays, but its children obey the per-repo lock: a child of repo X is not claimed for a
round, and its drive does not start, while X's own task (or another child of X) has an active run, and X's task
waits while a child holds X. A waiting child's row carries `waits_on` (the holder's run id) and reads queued. Free
workers of a round start only for claimed children, so a blocked repo is never edited by a worker.

## Defaults chosen (not in the brief)

- Discovery by the merge ledger plus a registry file (above), because repo-less notes are invisible to the todo MCP.
- Umbrella stage reuses `implement`/`shipping`; no new stage enum.
- Doubling judged on the server's own checks run right after the manager; the child's Checks stage reruns later.
- Children without a `Scan` count sort after those with one.
- No Ship click anywhere: each child ships itself, the umbrella closes when all are done.
- A child's commit carries `Todo: <umbrella id8>` (its run id's note part): the source section was cut by the merge.
- The round's own checks run at most 3 at a time (`rounds.MAX_CHECKS`): parallel `make test` runs OOM each other.
