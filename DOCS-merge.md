# Merge similar tasks

Many open items ask for the same kind of work ("Make <app> text-free (textgate-rework)" in dozens of repos, or two
notes for one thing). The board suggests groups of them, and a click merges a group into one note. Nothing merges
without that click. Contract: `contracts/merge.schema.json`. Code: `server/todoimpl/merge/`, `server/todoimpl/http/merge.py`,
web `components/merge-strip.ts`.

## Members are items

A member is a card (note section) id `<note id8>-<index>`, as everywhere (DOCS-spec.md, "Cards are items"). A note
without sections is one item. Candidates: open (`todo` / `in progress`), with a repo, title not `MANUAL WORK REQUIRED:`.

## Suggestions

- A one-shot Haiku call (`merge/classify.py`): `claude -p --model haiku --output-format json --strict-mcp-config`,
  role `classify` (read-only: `--disallowedTools` Edit/Write/NotebookEdit and git push), prompt starts with `override`,
  `CLAUDE_AUTO_CONTINUE=0`. Input: one line per candidate `id | repo | title | first 300 chars of the body`.
  Output: `{"groups": [{"ids": [...], "title": "...", "reason": "..."}]}`.
- Validated server-side (`parse_groups`): every id is a candidate, at least 2 distinct ids, a note in at most one
  group (a later group that reuses an id is dropped whole), title and reason are non-empty text, reason cut to its
  first line. Anything else is dropped; text that is not that JSON is a failed run.
- When: `MergeService.refresh_if_due()` runs from every `GET /api/merges` and once at server start (`http/main.py`).
  It starts a background thread when the candidate ids differ from the ids of the last run AND 10 minutes passed since
  it. A request never waits on Haiku. A failed run keeps the old groups and retries after 10 minutes.
- Cached in `$TODOIMPL_HOME/merge.json`: `ids`, `at`, `groups`, `dismissed` (group fingerprints), `created`
  (fingerprint to merged note id). A restart with the same ids asks nothing.
- A group id is `sha256(sorted member ids)[:12]`. The view cuts a stored group to the members that are still
  candidates (fewer than 2 left: gone) and hides dismissed fingerprints. A merged group disappears because its
  members are closed.

## Endpoints (not task-scoped; Origin and `X-Todoimpl-Token` checked like every POST)

- GET `/api/merges`: `{suggestions: [{id, title, reason, members: [{id, title, repo}], actions: [merge, dismiss]}]}`,
  biggest group first. `merge` is disabled, with its reason, while a member has a live run.
- POST `/api/merge/<group>/merge` and `/api/merge/<group>/dismiss`, empty body. Answer
  `{ok: true, new_id, suggestions}` (`new_id` null for dismiss) or the usual `{ok: false, error}`: 404 unknown group,
  409 `disabled` (live run) or `conflict` (title taken, another merge running), 502 `upstream_unavailable`.
- Served only when the backend has a `merge_service` attribute (`ServiceBackend` gets it in `build_backend`).

## What a merge does (`merge/apply.py`, one code path for the click and the CLI)

1. Refuse a live run: a member whose `$TODOIMPL_HOME/<card id>/state.json` has a stage outside `spec_wait`, `failed`,
   `paused_limit`, `cancelled`, `shipped` (so `gate`, `shipping`, `paused_retry` count as live). Rechecked on the POST.
2. All members in one repo: `add_task(repo, title = proposed title, priority = highest member)` appends ONE new
   section to the repo's note. Its body is `Tier: cheap` (if any member is cheap-tier, `runner/tier.py`), then each
   member's full text (title, blank line, body) under a `### <id>` heading. Level 3 on purpose: a `## ` line inside it
   would split the new card (`todo_mcp/items.py`). The id is the note id8, or the card id when two members are
   sections of one note. A `done_check:` line of a member is renamed `member done_check:` so the new card does not run
   one member's check; a note-level check not in the body is kept as such a line. An open card with the proposed
   title in that repo is a conflict (the MCP's add is idempotent by title and would reuse it).
3. Members in several repos: an umbrella note with no repo, created by the todo app's own CLI because the MCP's
   `add_task` needs a repo (`merge/umbrella.py`: `$TODOIMPL_TODO_NOTE`, default `dart run bin/todo_note.dart` in
   `$TODOIMPL_TODO_APP`, default `~/src/todo`, `--text <note> --by claude`). Exact format:

```
# <title>
Umbrella: per-repo
Tier: cheap        (any member cheap-tier: a Tier line or a text-free (textgate-rework) title)
- [ ] <repo> (<id>)
## <repo> (<id>)
<the original's full text>
```

   The note is fetched back from the todo app before any member is closed (fail closed). It has no repo, so the MCP
   list does not show it; the umbrella runner and kuhy's todo app do.
4. The new id and the member titles are written to `merge.json` (`created`) BEFORE any member is touched (for an
   umbrella right after the CLI returns, then it is fetched back: a todo app that has not synced yet fails the merge
   but a rerun does not make a second umbrella).
5. Members leave the board (`merge/remove.py`). A member section is CUT out of its source note with `update_task`
   (body without it) so it does not pile up as Done. A card id is `<id8>-<index>`, so a cut renumbers the sections
   after it: a note is cut only when no section at or after its first member has a run dir (any stage, members
   included). Otherwise that note's members are closed in place with `close_item` and evidence `merged into <new id>`
   (a `## [x]` section with a `closed:` line). A note left with no section and no text, or only done sections, is
   closed with `close_task` and that evidence. A whole-note member (no sections) is closed in place. The id of the
   new same-repo card is looked up again after the cuts (it may have moved up) and stored.
6. A rerun after a failure finds the ledger entry, creates nothing, and acts only on members that are still the very
   section recorded (same index and title, still open); ids that now name other sections are skipped.
7. A stored suggestion keeps the member titles Haiku saw; the view drops a member whose id now names another title.

## CLI

`python -m todoimpl.merge --group <id,id,...> --title <text> [--dry-run]` (from `server/`, or with
`PYTHONPATH=server`). A token is `abcd1234-N` (that section) or `abcd1234` (the note's only section; a note with
several is refused, name one). Prints `merged into <id> (repo|umbrella); removed N: ...; closed in place M: ...`; `--dry-run` prints the new
note's text and changes nothing. Exit 1 with the reason on a refusal. Uses `$TODOIMPL_HOME` for the run states.

## UI

`<ti-merges>` above the board, polled every 5 s, hidden when empty. A card: merge glyph, member count, one
row per member (its own title and repo), a merge and a dismiss icon button named by `aria-label`. A
disabled merge keeps the server's reason as its tooltip. A click disables the card's buttons at once; after 1 s a
spinner named `Merging` / `Dismissing` shows. A refusal shakes the card and shows the server's message as a toast.
No words are invented: the proposed title and the reason line are in the API only.

## Tests

`tests/merge/` (chunk `merge` in the Makefile): text, classifier (a `claude` shim on PATH), store, apply against the
fake todo MCP, service, CLI with a shim for the todo CLI, wiring, contract; `tests/http/test_http_merge.py`;
`web/src/components/merge-strip.test.ts` (also checks the Zod mirror against the schema).
