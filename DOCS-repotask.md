# One card per repo (repo tasks)

kuhy's rule (final, 2026-11-10): "1 repo = 1 todo note. While working on it Claude can split it into smaller parts,
but it should always be one note and one task in todoImplementer, so they do not fight with each other." Before, the
board made one card per `## ` section and the cards of one repo ran in parallel worktrees of the same repo. Code:
`server/todoimpl/repotask/` (parts, files, tick, cycle, prompt, migrate), `service/repocards.py` (grouping),
`runner/repolock.py` (the lock), `board/parts.py` (part states). Contract: `contracts/repotask.schema.json`.

## The card and its id

- Every open note of a repo with a `repo` (umbrellas and repo-less notes stay as they were, below) is grouped by
  `ids.norm(repo)` (case and outer blanks do not matter). All their open sections are the repo's **parts**; a note
  without sections is one part. A section marked `## [x]` is not a part.
- The card id is `<sha1(repo)[:8]>-0` (`ids.repo_card_id`): stable whatever notes the repo has or loses, shaped like
  every card id, so the run dir `<root>/<id>/`, the branch `todo/<id>`, the gate unit and the phone lease need no new
  rules. The card title is the repo name.
- Human parts (`MANUAL WORK REQUIRED:`) never sit on that card (T1980): they get a card of their own, id
  `<sha1(repo)[:8]>-1` (`ids.repo_human_id`), status Yours in Backlog, titled after its first human part. So Claude's
  ticked parts ship to Done while the manual work waits in Backlog.
- Card fields: `priority` = the highest part priority that Claude can work, `status` `in progress` when any note
  is, `body` = the work parts as `### Part <key>: <title>` blocks (level 3 on purpose: a `## ` line would split the
  card), `done_check` = the one check of the work parts or the distinct ones chained `(a) && (b)`.
- `GET /api/board` cards carry `parts` (optional, repo tasks only) and, for a queued card, `waits_on`.

## Parts

A part is `{key, note_id, index, title, body, priority, done_check, human, held}` (`repotask/model.py`); its `key`
is the section card id `<note id8>-<index>`. Order of work: priority (high first), then easiest (the smallest
`Scan ...: N items` number, else the shortest text), then note id and index. The run works them in this order.

| State | Meaning |
|---|---|
| todo | not ticked yet |
| working | the first part still owed while the run works (display only, from the card status) |
| done | ticked in this cycle |
| human | a `MANUAL WORK REQUIRED:` part (title start, exact caps): on the repo's `-1` card, never run or ticked |
| held | an older per-section run still owns the section (below); it has its own card |

A card with parts but none for Claude (the human `-1` card) is **Yours** and its Start is disabled with the MANUAL
reason; its line is the parts' `Needs:` lines (T1951). A repo with only held or human parts has no `-0` card. Part titles are user content; the page adds no words (icon per
state, a number for steps, names in `aria-label` and `title`).

## One run, cycles, ticks

- One run state `<root>/<card id>/state.json` (`extra.repotask`), one worktree, one session at a time. Start builds
  `plan.md` for all work parts together; Spec runs only when no part has a `done_check` or `done:`/`verify:` line.
  The stage machine of DOCS-spec.md is unchanged.
- The server writes `parts.json` at every drive (the parts in work order). Claude ticks with
  `python -m todoimpl.repotask.tick <run dir> done <key>` (the exact command is in every prompt, `repotask/prompt.py`),
  writes steps with `split <key> "step" ...` and ticks them with `step <key> <n>`; the file it writes is
  `parts-done.json`, so server and Claude never write one file. A part with open steps cannot be ticked; a key that is
  not an actionable part of the drive is refused (exit 1).
- A turn that ends the implement stage with `D:` while parts are unticked gets a runner nudge naming them, twice
  (`extra.part_nudges`); after that the run goes on and those parts stay open.
- Ship with no ticked part is refused (Needs you, `run_failed`): it would push and close nothing.
- **Ship closes per part.** `ItemView.close_task(repo card)` closes the section of every ticked part (`## [x]` plus
  a `closed:` line, evidence = live-check summary and check tails); the note closes with its last section. The
  commit has one `Todo: <note id8>` trailer per note that has a ticked part (not per part: a note is the unit in
  the todo app); its subject is the first ticked part's title.
- **Cycles.** A run that shipped while parts remain (unticked, new, or added by the live-check follow-up) is a
  finished cycle: the card is Backlog again (cost kept), Start begins cycle N+1 (`repotask/cycle.py` clears worktree,
  session, plan, ticks, checks; cost and history stay). It never starts by itself. When no open part is left the
  notes are closed and the card is Done (from the shipped run dir, `ClosedNotes`).
- Cancel stops the run only; it never abandons notes (they hold other parts too).

## The per-repo lock

One run at a time per repo (`runner/repolock.py`, in the Engine, `Ctx.locks`): the repo task, an umbrella child of
that repo and an older section run each hold the repo while they drive. A queued run waits in the queue (status
`queued`) and the card says which run it waits on (`waits_on`, a lock icon with the run id); the wait ends when the
holder's drive ends. Repo spellings are normalised like the card grouping.

- **The umbrella is the one exception to one card per repo** (kuhy's explicit earlier request, note 2d0704cd, the
  cross-repo text-free batch). Its children keep their own run ids `<umbrella id8>-<n>`, worktrees and cards in the
  umbrella's drawer. They obey the lock: a child of repo X is not claimed for a round while X is held, and its drive
  waits at its start; X's own task does not start while a child holds X. Blocked children never block the others
  (`Umbrella.claim` skips them); a row shows `waits_on` and the page draws it queued. A child that never starts
  (missing clone) lets go at once; the drive lets go of all at its end.
- A run whose turn survived a server restart (`turn.pid` recorded) joins the lock without waiting (`force`): it is
  already working, a restart must not strand it. Every other run waits, kuhy's Retry or Send on an older card
  included: two sessions never work on one repo.

## Transition from per-section runs

Existing run dirs `<id8>-<n>` and branches `todo/<id8>-<n>` are never touched or deleted.

- `repotask/legacy.py` (`older`) decides per section card. A run still **working** (stage `spec`, `plan`, `implement`,
  `live_check`, `checks`, `shipping`, or `paused_retry`) or one that waits on a click that only its own card offers
  (`gate`: Ship; `paused_limit`: resumes by itself) is **held**: it keeps its own card with all its actions
  (a Q or A question on a working stage included), and its section is a `held` part of the repo card, left out of the
  repo run's body and plan. A repo with only held parts has no repo card yet.
- A run that has reached a **resting stage** (`failed`, `spec_wait`, `cancelled`) **folds at once**: its card goes,
  its section is an ordinary part, and the repo run's prompt names the old work (`Earlier work on [<key>]: an earlier
  run ended failed (branch todo/<key>, worktree <path>); it said: ...`) so the session reuses it. A `shipped` run
  closed its section already. Nothing is lost: the run dirs, branches and worktrees stay.
- The result: right after a deploy a repo with several runs still working shows those runs' cards; each one folds
  into the repo task as soon as it reaches `failed`, `spec_wait`, `cancelled` or ships (`gate` folds after Ship or
  Cancel). At steady state there is one card per repo.
- No section-level run starts any more: a section without a run has no card of its own (Start on its id is
  `not_found`), so the first run of any section is the repo run. A cancelled section run cannot be restarted.
- Merge suggestions ("Merge similar tasks", DOCS-merge.md) work on the open parts as sections
  (`repocards.section_cards`), unchanged.

## Migration of the notes: `python -m todoimpl.repotask.migrate`

Dry run by default (reads only, prints the plan and counts); `--apply` writes. Needs the todo app (`TodoClient.from_env`).

1. Open notes with a repo, minus umbrellas, are grouped per repo; a repo with more than one note is merged.
2. The **target** is the note with an older run in flight (its section ids must not move), else the one with the
   most sections, else the lowest id. Others are **sources**.
3. A source with an older run still working or at `gate` (the same test as the board's `held`) is skipped until it
   rests (reported, never touched): moving its sections would orphan the run's branch and dir. A run that rests
   already folded, so its note is not blocked; its run dir keeps the old ids (the repo run is told where the work is).
4. Sections move as `## ` sections appended to the target (existing section ids stay); a note without sections
   becomes one section titled by the note; text before the first section becomes a section titled by the note; `## [x]`
   sections are dropped; a note-level `done_check` becomes a `done_check:` line inside its section (also in a target
   that is a whole note or has one section). A `MANUAL WORK REQUIRED:` title is kept (it is a human part). The target
   gets the highest priority of the notes.
5. Order per source: append, read the target back and check every section arrived (fail closed), then
   `close_task(source, "merged into <target id8>")`. A rerun after a failure finds the sections already there (compared
   without whitespace differences), adds nothing twice and closes the source.
6. A todo note that vanishes between listing and fetching (others write too) is retried.

Dry run on the real todo app (2026-11-10, read only): the first run found 1 repo with more than one note (4 notes,
3 to merge, none skipped); a few minutes later the same run found 0 (someone merged them meanwhile). 18 open repo
notes in 18 repos, 48 open parts. Live board through the new grouping: 58 cards in 27 repos; 7 repos still show more
than one card because 7 older section runs are working or at Ready to ship (they fold as they rest).

## kuhy's own task from the board: `POST /api/new-task`

The toolbar's + opens a dialog: repo (an `<input list>` over the board's repos, free `owner/name` allowed), title,
details and any files (picker with no type filter, multi-select; a camera picker on touch devices; Ctrl+V; drag and
drop). Images show as thumbnails, other files as a file icon and their name; each has a remove button. Caps: 100 MB
per file, 500 MB per task, refused by name before upload (and again by the server). On Create the page sends each
file unchanged to `POST /api/upload` (raw body, name percent-encoded in `X-Todoimpl-Name`; Origin and token checked
before a byte is read; streamed to `$TODOIMPL_HOME/uploads/<id>/`, swept after 24 h; `http/upload.py`,
`newtask/uploads.py`), then posts `{repo, title, body, files: [id]}` (`contracts/requests.schema.json` `new_task`).
The relay's JSON `images: [{data_b64}]` (JPEG, 8 x 6 MB, 40 MB per request) still works. At 640 px or less the dialog
fills the visible viewport (`visualViewport`), the details field grows with its text and Create stays pinned.
Code: `http/newtask.py`, `newtask/service.py`, `newtask/images.py`.

1. A title an open section of that repo already has is refused (`conflict`): two parts nobody could tell apart.
2. The files go to a fresh uuid4 folder: relay pictures as `<n>.jpg`, uploads moved byte-identical to
   `<uuid4>.<ext>` (ext lower-cased, `bin` when unusable, the todo app's own rule) (root `$TODOIMPL_IMAGES_ROOT`, default
   `~/data/cloud/todo-images`, which dufs serves as `https://kuhy-cloud.duckdns.org/todo-images/`), written atomically.
3. `add_task` appends `## title` with the details and one link per file, `![](<dufs url>)` for an image and
   `[name](<dufs url>)` for anything else (the todo app's format), to the repo's open note
   (or creates one). The cache is refreshed at once, so the card is there before the answer.
4. The router then presses that card's Start through the very path of a Start click (`_action`): a new repo card or
   one resting at Backlog starts; a card already at work refuses, and the section is simply a new part, worked by this
   run or the next cycle (as with any part added in the todo app). The answer is `{ok, note, started, task}`; the page opens the card.
   A `MANUAL WORK REQUIRED:` title lands on the repo's `-1` card, whose Start is disabled (`started: false`).

Sessions cannot log in to dufs, so every stage prompt rewrites those links to the local paths and adds one line
asking the session to open each with Read (`prompts/texts.py`, `newtask/images.localize`); this covers files
attached in the todo app too. Each file found on this PC is first copied to `<run dir>/attachments/<folder>/<file>`
and the line names the copy (`images.copy_into`). Every turn gets the images root as an extra `--add-dir` when it exists.

## Defaults chosen (not in the brief)

- Part key = the section card id; `Todo:` trailer per note of the ticked parts (not per part).
- A cycle ends at Ship; the next cycle needs a Start click (no auto-continue).
- Held = a run that is working, at Ready to ship or paused by the plan limit; `failed` and `spec_wait` count as
  resting and fold at once (kuhy's brief: "keep going until they reach a resting stage, then fold"). Nothing is
  cancelled for kuhy.
- Done `## [x]` sections are dropped by the migration (their record stays in the closed note's evidence).
- Several distinct `done_check`s are chained with `&&`; one prose check makes the chain a "sentence" the board does
  not run (the plan criteria cover it).
- The queue order of waiting runs is the queue's (first come, first served); no priority between repos.
