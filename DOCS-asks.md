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
- **Delivery**: once no choice is open, the session gets one `(runner)` message with the answers.

Endpoints (`http/asks.py`, Origin + CSRF like every POST): `POST /api/task/<id>/ask/<answer|take-recommended|run|undo|approve|reject>`.

Sweep (`python -m todoimpl.asks.sweep report|add|drop-note`): classifies the "MANUAL WORK REQUIRED" sections, appends an
ask block to a card's section through the todo app (card text only), logs each edit on the card.

Bare `A:` (`runner/askform.py`, T2048): a turn that ends on `A:` with no valid `ask` block is not parked as prose. The
runner resumes the session once per stage and twice per run (`extra["ask_forms"]`, `ask_form_total`) with a fixed note:
run any phone, device or E2E check yourself, and write a `choice` per decision or a `command` / `screenshot` for the
exact step kuhy must take. Skipped for `spec`/`plan`, phone waits, error runs and umbrella children. After the budget
the card parks with the old free-text ask.
