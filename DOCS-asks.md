# Asks: what a task wants from kuhy, as buttons in the note

A task that needs kuhy writes one fenced `ask` block in its note (or newest reply), one line per ask:

```
choice c1: <title> | opt | *recommended | opt | risk=reversible
command k1: <exact command>
screenshot s1: <what to check> | shots/<name>.png
```

`server/todoimpl/asks/parse.py` turns it into a schema-checked list (`contracts/ask.schema.json`, `task.ask_items`).
A malformed block (no single `*`, bad id, duplicate id, unknown risk) yields nothing: the card keeps the old free-text ask.

- **Choice**: one button per option, one Take recommended for every open choice, a click shows at once.
- **Command**: exact strings only. Allow-listed (`$TODOIMPL_HOME/cmd-allow.json`) runs; unlisted offers add-and-run;
  the never-add set (`sudo`, `rm -rf`, `pacman`, `chattr`, `poweroff`, `git push --force`, `curl|sh`,
  `textgate approve`) and root commands only get a warning button that copies the text. Runs as kuhy in the task
  worktree, 60 s cap (exit 124), last 50 lines plus exit code saved on the card.
- **Screenshot**: the picture from the run's `shots/` with Approve / Reject; Reject sends the card back to its session.
- **Risk**: a session may tag a choice `reversible`; the fixed rule (`risk.py`: encrypt, migrate, delete, wipe, push,
  root, credentials, money, `rm`, `chattr`...) overrides it to `risky`. Untagged is risky. Only `reversible` choices
  auto-adopt their recommended option after 24 h (`AskService.adopt_due`, 5 min tick); the card shows Undo, and an
  undone choice never auto-adopts again. State lives in `<run dir>/asks.json` (first-seen times, answers, log).
- **Delivery**: once no choice is open, the session gets one `(runner)` message with every answer of its asks, not
  just the last click (T2376). A Send to Claude note sent before then carries the answered ones (T2275), and the
  note box stays below the questions (T2273).
- **Rounds** (T2277): state in `asks.json` is per (reply, id). A reply that asks an id again (`logo_pixel` in round two)
  starts it open with a fresh 24 h clock; `store.load(dir, asks)` drops the record of an id whose reply changed and
  adopts a record saved before rounds into the current one. A choice kuhy answered this cycle keeps his answer when
  asked again (`asks/carry.py`, T2376), unless his option is gone or it was a `change` on an approval; records carry
  their `cycle`. An `A:` that asks only answered choices resumes with his answers (`runner/answered.py`, twice a run).
- **Manual parts on a repo card** (T2114): their asks always show, also beside the run's newest reply. While the
  session has asks of its own (reply, body or Claude's parts), delivery and Take recommended cover only those, so
  kuhy's open manual asks never hold the session back and a click meant for the session never releases his work.
- **Closed cards** (T2360): a run at `shipped`, `closed` or `done_manually` asks nothing from its reply, so its old asks
  show no buttons, take no click and never auto-adopt; a repo card keeps the asks of its open parts. A repo card's next
  cycle drops the last reply (`repotask/cycle.py`), so the old cycle's asks never steer the new one.

Endpoints (`http/asks.py`, Origin + CSRF like every POST): `POST /api/task/<id>/ask/<answer|take-recommended|run|undo|approve|reject>`.

Sweep (`python -m todoimpl.asks.sweep report|add|drop-note`): classifies the "MANUAL WORK REQUIRED" sections, appends an
ask block to a card's section through the todo app (card text only), logs each edit on the card.

Bare `A:` (`runner/askform.py`, T2048): a turn that ends on `A:` with no valid `ask` block is not parked as prose. The
runner resumes the session once per stage and twice per run (`extra["ask_forms"]`, `ask_form_total`) with a fixed note:
run any phone, device or E2E check yourself, and write a `choice` per decision or a `command` / `screenshot` for the
exact step kuhy must take. Skipped for `spec`/`plan`, phone waits, error runs and umbrella children. After the budget
the card parks with the old free-text ask.

Approval criteria (`runner/approval.py`, T2362): when the item or a spec answer says kuhy judges, approves or reviews a
deliverable (a mail, message, post or design), the plan writes that criterion as `Cn. (kuhy) ...`. The live check
never ticks it. It (or the implement or fix stage) shows the deliverable and ends `A:` with
`choice c<n>: <question> | *approve | change`.
The card waits in Needs you. A `change` or a Send note goes back to the same session, which edits the deliverable and
asks again. `approve` resumes it to do the outward step, such as sending the mail, if the session has the means. Board
sessions have no mail or Gmail tool: they run with `--strict-mcp-config`. Until asks.json holds kuhy's own approve for `c<n>`
(an option starting with `approve`, or a screenshot `c<n>` he approved; for a sole `(kuhy)` criterion, an approve on any
choice; never an auto-adopted answer or one from an earlier cycle), `live.settle` sends the session back
once and then raises Needs you. If he answered `c<n>` with no approve, Needs you says so at once (T2376). The run never reaches Checks, never ships partly with a follow-up, and never defers the criterion.

Phone work is Claude's (`runner/devicework.py`, T2522). A check that needs phone interaction (taps, ratings,
screenshots, timing measured on the device) is never a `(kuhy)` criterion, even when the note says "Check: manual
(needs the phone)": the plan prompt forbids the mark, the implement, fix and live check prompts say to run it on the
session's own phone slot, and `approval.kuhy_ids` drops a marked one unless it is an approval. An `A:` whose ask
block holds such phone work and nothing else but commands the session may run itself (nothing root or in the
never-add set) goes back to the session (`askform.needs_form`) with a note to drive the phone itself, whatever its
`A:` line says. It has its own budget, twice per run (`phone_asks`, cleared by Start, Retry and Ship reruns), so a
block written after the bare-`A:` note still goes back. Past it the ask still never shows to kuhy (T2523,
`devicework.to_claude`): from implement the card goes on to a fresh live check, from the live check its report is
settled by the usual rules (an open phone check gets the fix turn), each next turn carrying the phone note.
When every turn keeps asking and no other criterion was verified, `live.settle` still ends in Needs you. A real
decision, an approval of a deliverable or a root command still reaches kuhy.

The `(kuhy)` mark counts in every head plans write (T2523, `parsing.HEAD`, shared by `approval` and `crithash`):
`C9. (kuhy)`, `- C9. (kuhy)`, `- C9: (kuhy)`, `C9 (kuhy)`, `**C9** (kuhy)`, `C9 [part]: (kuhy)` and
`- C9. (kuhy) [part]:`. Elsewhere in the text it is no mark. Criteria keep their plan position as their id.

The approve is keyed to the criterion's text, not to `plan.md`'s mtime (T2462): on kuhy's click the server stores
`crit`, a hash of the criterion (`runner/crithash.py`: no `Cn` prefix, part tag or `(kuhy)` marker, whitespace
collapsed), and the approve counts while its cycle matches and the criterion still hashes the same. A session that
rewrites the rest of the plan keeps it, and so does a re-wrap. A changed criterion drops the record, so the ask shows
as a button again, and Needs you says `approved before the plan changed; re-approve`. A record with no `crit` (clicked
before T2462, or the plan was unreadable) counts when it is of this cycle and newer than `plan.md`.

Ids: `[a-z][a-z0-9_-]{0,15}`; a hyphen reads as an underscore (`logo-pick` is `logo_pick`, T2134). A block that still
fails makes the form note above quote the line that broke it and why (`parse.diagnose`).

Pages (T2135, `board/links.py`): what kuhy must look at belongs in the task itself (a `screenshot` ask, a `choice`), never
"open /path". When a Needs-you ask names a page anyway, `needs.links` carries it as an absolute http(s) URL (the ask's own
URLs; a route after a cue verb such as `open /logo-lab` resolves against the first loopback or `*.duckdns.org` URL of the
ask or last reply). The web drawer draws a link glyph per URL, the app a glyph that copies it (no browser dependency).
A route with no known host is not concrete: an `A:` that says it and has no valid ask block goes back to its session
(`runner/linknudge.py`, `link_nudges`, twice per run, cleared by Start, Retry and a note) to put the content in the task.
Nothing records a per-repo base URL; add one before resolving a route without a host in the reply.
