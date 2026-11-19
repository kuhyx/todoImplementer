# Notes with no repo: triage (kuhy, 2026-11-19)

A note with no `repo` used to be a Yours card with only Won't do (T2058). That is wrong for a note that asks for a new
app, a change across all repos, or a reading list. Code: `server/todoimpl/triage/`, `board/norepo.py`, `prompts/research.py`.

## The label

`TriageService` (`triage/service.py`, a 5 s loop, never on the board fetch) classifies each open, single-note, repo-less
card without a run with one Haiku call (`classify.py`, the merge classifier's `oneshot.run`, cost kind `triage`). The
prompt carries the title, 1500 characters of the text and kuhy's repo list (`gh repo list kuhyx --limit 1000`, cached
10 min; archived repos left out). The label goes to `<run dir>/triage.json` with a digest of title and body: an edited
note is triaged again, an unchanged one never. A failed call leaves the note untriaged (Yours) and waits 10 min.

| label | meaning | what happens |
|---|---|---|
| `existing_repo` | clearly one repo in the list | `update_task(repo=...)` at once; the note's sections become parts of that repo's one card |
| `all_repos` | one change in many or all repos | at once: the note is rewritten into an umbrella (`Umbrella: per-repo`, DOCS-umbrella.md); children = repos with a local clone where `git grep -F <token>` hits (inside `path` when given; no token = every cloned repo); none found = Yours with `error` on the label. The umbrella is started by kuhy's click like any |
| `new_repo` | asks for a new app, tool, site, game, library | Backlog card with Start; Start creates the repo (below) |
| `research` | mainly URLs or articles | Backlog card with Start; Start runs the research session (below) |
| `manual` | not code (also: an unknown repo or a bad name in the answer) | Yours, only Won't do |

`board/norepo.py` `is_yours` is the one rule: no repo, not an umbrella and no `new_repo` or `research` label. The card
carries `triage` (`task_card.triage`, optional), drawn as an icon with the name only in tooltip and aria-label.
`CardTask.triage` is read from the run dir by the board fetch; the tick also patches the cache snapshot at once (`TaskCache.set_triage`, T2074), because a label is a file and no note change wakes a fetch (about 30 s). A reply with broken JSON but readable fields still counts (T2076).

## New repo

Start on a card labelled `new_repo` (`TriageService.start`, in place of `scheduler.start` for every Start click) runs
`newrepo.provision` off the click. The model never sees a repo before it exists, so the **triage answer picks the
name** (short kebab-case); the repo's own spec session does the real spec. Steps, each written to
`<run dir>/newrepo.json` after it works and skipped when already true: reserve a unique name (against every repo
including archived ones and `~/src/<name>`: `-2`, `-3`...), `gh repo create kuhyx/<name> --private`, commit a scaffold
(README.md, CLAUDE.md with run/test/lint "not chosen yet" and no fake `deploy:` line, .gitignore; trailer
`Todo: <id8>`) in `<run dir>/scaffold` and push it as `main`, `git clone` to `~/src/<name>` (kuhy's copy and the base
of the runner's worktrees; no session edits it). Then `update_task(repo=)` and the repo's card
(`repo_card_id`, a new id: the repo-less card is gone) starts. CLAUDE.md tells the first session to pick the stack from
kuhy's build-* skills. A failed step rests as a failed run on the repo-less card (Needs you with the error); Retry
resumes. A second click while it runs is `conflict`.

## Research

`ResearchDriver` (`triage/research.py`, chosen by `driver_for` from the label): no worktree (cwd `<run dir>/research`),
spec and plan skipped, one Sonnet turn at medium effort (`tiering.plan_turn`). The session reads each URL, writes
`research.md` (shown as the drawer's report) and `research.json` (2 to 5 actions: id, title, repo or null, body with a
done condition) and ends on `A:` with one `choice cN: ... | Make note | *Skip | risk=reversible` per action (an ask
has one answer, so no multi-select; all Skip = nothing to do; the 24 h auto-adopt of DOCS-asks.md applies). When every
choice is resolved the next drive makes no turn: it adds a note per `Make note` (`add_task` for a repo, the todo CLI
`create_umbrella` for none, which triage then routes), records each in `research-done.json` (a retry makes none
twice), closes the note with the ids as evidence, and ends `shipped` (Done). A reply with no choices and `D:` closes
the same way.
