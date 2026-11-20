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
- **Delivery**: once no choice is open, the session gets one `(runner)` message with the answers. A Send to Claude
  note sent before then carries the answered ones (T2275), and the note box stays below the questions (T2273).
- **Rounds** (T2277): state in `asks.json` is per (reply, id). A reply that asks an id again (`logo_pixel` in round two)
  starts it open with a fresh 24 h clock; `store.load(dir, asks)` drops the record of an id whose reply changed and
  adopts a record saved before rounds into the current one.
- **Manual parts on a repo card** (T2114): their asks always show, also beside the run's newest reply. While the
  session has asks of its own (reply, body or Claude's parts), delivery and Take recommended cover only those, so
  kuhy's open manual asks never hold the session back and a click meant for the session never releases his work.

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
never ticks it. It shows the deliverable in its reply and ends `A:` with `choice c<n>: <question> | *approve | change`.
The card waits in Needs you. A `change` or a Send note goes back to the same session, which edits the deliverable and
asks again. `approve` resumes it to do the outward step, such as sending the mail, if the session has the means. Board
sessions have no mail or Gmail tool: they run with `--strict-mcp-config`. Until asks.json holds kuhy's own `approve`
for `c<n>` (an auto-adopted answer does not count), `live.settle` sends the session back once and then raises Needs
you. The run never reaches Checks, never ships partly with a follow-up, and never defers the criterion.

Ids: `[a-z][a-z0-9_-]{0,15}`; a hyphen reads as an underscore (`logo-pick` is `logo_pick`, T2134). A block that still
fails makes the form note above quote the line that broke it and why (`parse.diagnose`).

Pages (T2135, `board/links.py`): what kuhy must look at belongs in the task itself (a `screenshot` ask, a `choice`), never
"open /path". When a Needs-you ask names a page anyway, `needs.links` carries it as an absolute http(s) URL (the ask's own
URLs; a route after a cue verb such as `open /logo-lab` resolves against the first loopback or `*.duckdns.org` URL of the
ask or last reply). The web drawer draws a link glyph per URL, the app a glyph that copies it (no browser dependency).
A route with no known host is not concrete: an `A:` that says it and has no valid ask block goes back to its session
(`runner/linknudge.py`, `link_nudges`, twice per run, cleared by Start, Retry and a note) to put the content in the task.
Nothing records a per-repo base URL; add one before resolving a route without a host in the reply.
