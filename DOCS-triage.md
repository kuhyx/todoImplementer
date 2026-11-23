# Notes with no repo: triage (kuhy, 2026-11-19)

A note with no `repo` used to be a Yours card with only Won't do (T2058). That is wrong for a note that asks for a new
app, a change across all repos, or a reading list. Code: `server/todoimpl/triage/`, `board/norepo.py`, `prompts/research.py`.

A repo-less note also comes from the phone's add task with no repo picked: `new_task` without `repo` adds it through
the todo CLI (`--by kuhy`) and starts nothing; this triage then labels it (T2347).

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
| `research` | mainly URLs or articles; never a note that asks to make something, even when it says "research how" (T2090) | Backlog card with Start; Start runs the research session (below) |
| `manual` | not code (also: an unknown repo or a bad name in the answer) | Yours; Start asks again (below) |

`board/norepo.py` `is_yours` is the one rule: no repo, not an umbrella and no `new_repo` or `research` label. The card
carries `triage` (`task_card.triage`, optional), drawn as an icon with the name only in tooltip and aria-label.
`CardTask.triage` is read from the run dir by the board fetch; the tick also patches the cache snapshot at once (`TaskCache.set_triage`, T2074), because a label is a file and no note change wakes a fetch (about 30 s). A reply with broken JSON but readable fields still counts (T2076).
A `research` label on a note with no URL is asked again once with the mistake named; a second `research` becomes `manual`
(`TriageService._verdict`, T2090).

## New repo

While the repo is made, or a pressed note is triaged, the card is in `TriageService.busy()`: the board shows it
Working with "being created" and one disabled Start, never Backlog (T2529, `board/creating.py`).

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
spec and plan skipped, one turn on the role default, Opus 5.5 at high effort like every card turn (`tiering.plan_turn`, T2476). The session reads each URL, writes
`research.md` (shown as the drawer's report) and `research.json` (2 to 5 actions: id, title, repo or null, body with a
done condition; since T2091 an object `{"deliverable": ..., "actions": [...]}`, a plain list still reads) and ends on `A:` with one `choice cN: ... | Make note | *Skip | risk=reversible` per action (an ask
has one answer, so no multi-select; all Skip = nothing to do; the 24 h auto-adopt of DOCS-asks.md applies). When every
choice is resolved the next drive makes no turn: it adds a note per `Make note` (`add_task` for a repo, the todo CLI
`create_umbrella` for none, which triage then routes), records each in `research-done.json` (a retry makes none
twice), closes the note with the ids as evidence, and ends `shipped` (Done). A reply with no choices and `D:` closes
the same way.

**Deliverable (T2091).** When the note itself asks for something to be made (a logo, a page), the session names it as
`deliverable` and marks the action that makes that very thing `"delivers": true`. The note closes only when a made
note delivers it; otherwise the card rests as a failed run that names the missing deliverable, and the note stays
open (Done manually or Won't do close it by hand).

## Start on any Yours card (T2092, kuhy, 2026-11-19)

kuhy expects to start any note ("no option to start it bro"). A Yours card with no run and no `MANUAL WORK REQUIRED:`
title (`actions._primary`) offers Start, `manual` and untriaged notes included; Won't do and Done manually stay.
`TriageService.start` takes every repo-less card that is no umbrella and not `research` (those start as before) off
the click (`_pressed`, a job; a second click is `conflict`): it classifies the note again with the hint `classify.PRESSED`
("kuhy pressed Start, so this is code work: choose existing_repo, new_repo or all_repos, never manual or research unless
the note is only URLs") and overwrites `triage.json`. Then it routes as usual:

| answer | what Start does |
|---|---|
| `existing_repo` | sets the repo; the note is a part of that repo's card and the card starts (a card at work refuses: the part waits for its next cycle) |
| `new_repo` | `newrepo.provision` and the repo's card starts (above) |
| `all_repos` | the umbrella is made and started; no matching repo is a failure |
| `research` | the research run |
| `manual` | not code after all: the card rests as a failed run `start: still not code: <reason>` (Needs you); Retry asks again |

Any failure rests the same way, on the repo-less card, so nothing is lost silently.

## Merge takes a repo-less note (T2093)

The merge (DOCS-merge.md) used to refuse a member with no repo. One that sits beside members of exactly one repo now
joins that repo's combined card (`merge/apply.py` `repos_of`) and closes in place with `merged into <new id>`; no
repo at all, or a repo-less member beside several repos, is still `bad_request`. A repo-less note is not in the repo
list, so the CLI (`--group <repo section id>,<note id8>`) is the way to name it.
