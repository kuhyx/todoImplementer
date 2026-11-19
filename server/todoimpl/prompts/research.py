"""The prompt of a research card (DOCS-triage.md): read the URLs, report, offer 2-5 actions as choices."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import PromptContext

TEXT = """override
Research note from kuhy: he collected URLs of articles he found interesting. Read them and suggest what to do.
Item: {title}
{body}
{notes}
You have no repo and no worktree. Work in {cwd} and write only the two files named below; change nothing else.
1. Fetch and read every URL in the note (WebFetch, or the web-fetch agent). For a text over about 60 KB use
   `free-llm` (skill offload-free) instead of paging it into context. A URL that fails to load: say so in the
   report, never guess its content.
2. To judge fit, list kuhy's repos (`gh repo list kuhyx --limit 1000`) and read the README of any repo an idea
   could apply to (`~/src/<repo>/README.md`).
3. Write {run_dir}/research.md: per article the key ideas (a few lines), then how they apply to kuhy's repos
   and projects. Short and concrete.
4. Write {run_dir}/research.json: a JSON list of 2 to 5 concrete suggested actions, each
   {{"id": "c1", "title": "<one line: the action and its target>", "repo": "<owner/name of an existing repo>",
   "body": "<what to do, ending with a one-line done condition>"}}. The target is an existing repo, a new repo
   or all repos. For a new repo or all repos set "repo" to null: the board routes a note without a repo.
5. End the reply with one fenced `ask` block, a line per action with the same id as in research.json, and then
   a line `A:`:
```ask
choice c1: <title as in research.json> | Make note | *Skip | risk=reversible
```
   Keep `|` out of the title. Put `*` on `Make note` for an action you recommend. If nothing is worth doing,
   suggest one action anyway or end with `D:` and no ask block: that closes the note.
When kuhy answers you are not resumed: the board makes a todo note for every `Make note` and closes this note.
"""


def research(ctx: PromptContext) -> str:
    """Return the prompt: the item's text, kuhy's notes, and the five steps."""
    notes = "\n".join(f"kuhy's note: {n}" for n in ctx.notes)
    return TEXT.format(title=ctx.title, body=ctx.body, notes=notes, cwd=ctx.worktree, run_dir=ctx.run_dir)
