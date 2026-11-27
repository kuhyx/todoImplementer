"""One-shot Haiku calls (merge classifier, lesson drafter): a narrow `claude -p` whose cost is recorded.

Board sessions run with kuhy's whole `~/.claude` (DOCS-spec.md, "Sessions"). A one-shot that reads a prompt
and prints JSON needs none of it: every MCP server, skill, hook and tool description would be paid for on
each call. So it gets no settings sources (no user hooks, plugins, rules or permissions), no MCP servers, no
skills, no tools, low effort, and a scratch working directory where no project CLAUDE.md is found.

claude 2.1.322 prints `--output-format json` as an array of events (system, assistant, result), older builds
as the single result object; both are read. The result's cost and token counts go to
`<root>/oneshot-usage.jsonl`; `usage_summary` adds that spend to the cost totals.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

from .claude import claude_bin

if TYPE_CHECKING:
    from pathlib import Path

LEDGER = "oneshot-usage.jsonl"
SCRATCH = "oneshot"  # cwd of every one-shot, under the run root
NARROW = (
    "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "", "--tools", "",
    "--effort", "low",
)  # fmt: skip
EXCERPT = 200


def argv(model: str, deny: tuple[str, ...] = ()) -> list[str]:
    """Return the command line: print one JSON result, load nothing of the user's setup."""
    out = [claude_bin(), "-p", "--model", model, "--output-format", "json", *NARROW]
    return [*out, "--disallowedTools", ",".join(deny)] if deny else out


def _result(output: str) -> dict[str, Any] | None:
    """Return the result event of claude's JSON output (one object, or an array of events), else None."""
    data = json.loads(output)
    if isinstance(data, list):
        data = next((e for e in reversed(data) if isinstance(e, dict) and e.get("type") == "result"), None)
    return data if isinstance(data, dict) else None


def _record(root: Path, kind: str, model: str, result: dict[str, Any]) -> None:
    raw = result.get("usage")
    usage: dict[str, Any] = raw if isinstance(raw, dict) else {}
    cost = result.get("total_cost_usd")
    row = {
        "at": time.time(), "kind": kind, "model": model,
        "cost_usd": float(cost) if isinstance(cost, int | float) else 0.0,
        "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
        "cache_write_tokens": usage.get("cache_creation_input_tokens", 0),
    }  # fmt: skip
    atomic.append_line(root / LEDGER, json.dumps(row))


def spend(root: Path, since: float) -> float:
    """Return the dollars the ledger holds for calls at or after `since` (epoch); bad lines are skipped."""
    try:
        lines = (root / LEDGER).read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0.0
    total = 0.0
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("at", 0) >= since:
            total += float(row.get("cost_usd", 0.0))
    return total


def run(  # noqa: PLR0913 - one call, keyword-only
    prompt: str,
    *,
    model: str,
    kind: str,
    root: Path,
    timeout: float,
    error: type[Exception],
    deny: tuple[str, ...] = (),
    batch: bool = False,
) -> str:
    """Run the prompt on stdin and return the model's text; raise `error` on any failure.

    `batch`: a background one-shot that may wait: through the Batches API when the credits allow it
    (`batchshot`, T2532), else here.
    """
    if batch:
        from . import batchshot  # noqa: PLC0415 - the credits stack loads only for batch callers

        def plan() -> str:
            return run(prompt, model=model, kind=kind, root=root, timeout=timeout, error=error, deny=deny)

        return batchshot.run(prompt, model=model, kind=kind, root=root, error=error, fallback=plan)
    scratch = root / SCRATCH
    scratch.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CLAUDE_AUTO_CONTINUE": "0"}  # handoff hooks must not spawn sessions
    try:
        proc = subprocess.run(  # noqa: S603 - the argv built above, no shell
            argv(model, deny), input=prompt, capture_output=True, text=True, env=env, cwd=scratch,
            timeout=timeout, check=False,
        )  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        msg = f"claude timed out after {timeout:g}s"
        raise error(msg) from exc
    except OSError as exc:
        msg = f"cannot run claude: {exc}"
        raise error(msg) from exc
    if proc.returncode != 0:
        msg = f"claude exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[-EXCERPT:]}"
        raise error(msg)
    try:
        result = _result(proc.stdout)
    except ValueError as exc:
        msg = f"claude printed non-JSON: {proc.stdout[:EXCERPT]!r}"
        raise error(msg) from exc
    if result is not None:
        _record(root, kind, model, result)
    text = result.get("result") if result is not None else None
    if not isinstance(text, str) or (result or {}).get("is_error"):
        msg = f"claude returned no text: {proc.stdout[:EXCERPT]!r}"
        raise error(msg)
    return text
