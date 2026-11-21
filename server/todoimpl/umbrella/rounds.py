"""One round of an umbrella: worktrees, one Sonnet manager turn, the server's own checks, then the verdict.

Steps persist in `rec["current"]` (free flags, the manager's verdicts, check results) so a restart resumes the
round at the step it reached instead of redoing the manager turn. The server adjudicates: the width doubles
only when every child was `clean` or `coached` (below the cap), done by a free worker, and green (ramp.ok).
"""

from __future__ import annotations

import contextvars
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl import atomic
from todoimpl.board import state as store
from todoimpl.prompts import coach
from todoimpl.prompts.tier import escalated
from todoimpl.runner import checks, freegate, freeworker, worktree
from todoimpl.runner.files import KilledError, NeedsYouError

from . import bounce, issues, outage, ramp
from .children import fresh_state
from .store import child_dir, children_root
from .view import child_state

if TYPE_CHECKING:
    from .note import Child
    from .run import Umbrella

MAX_CHECKS = 3  # parallel check runs: more would OOM each other inside capped.slice (see gatehost)
APPROACH = (
    "Do the task below in this repo. Work a free model already did is in the worktree (`git diff`): "
    "keep what is sound."
)


def run_round(u: Umbrella, batch: list[str] | None) -> None:
    """Run the round in progress, or start one over `batch` (child ids)."""
    d, rec = u.d, u.rec
    if rec.get("current") is None:
        rec["current"] = {
            "n": len(rec["rounds"]) + 1, "width": rec["width"], "ids": list(batch or []),
            "started": d.ctx.now(), "free": {}, "failed": {}, "verdicts": None, "checks": None,
        }  # fmt: skip
        d.save()
    cur = rec["current"]
    kids = [u.kids[cid] for cid in cur["ids"] if cid in u.kids]  # a dropped child leaves its round (T1924)
    if cur["verdicts"] is None:  # the manager still has to run: it and the workers need the network
        outage.check_network(d)
    _prepare(u, cur, kids)
    live = [k for k in kids if k.cid not in cur["failed"]]
    if cur["verdicts"] is None and live:
        _manage(u, cur, live)
    elif cur["verdicts"] is None:  # every child of the round failed before the manager
        cur["verdicts"] = {}
    if cur["checks"] is None:
        _check(u, cur, live)
    _finish(u, cur, kids)


def _plan(kid: Child) -> str:
    lines = [
        "## Approach",
        APPROACH,
        "",
        kid.text,
        "",
        "## Acceptance criteria",
        "C1. I run the changed thing for real and see the task satisfied.",
    ]
    if kid.done_check:
        lines.append(f"C2. I run `{kid.done_check}` and it passes.")
    return "\n".join(lines) + "\n"


def _write_task(cdir: Path, kid: Child) -> None:
    """Write the worker's task file: the textgate rules first when the child is a textgate rework."""
    text = coach.task_text(kid.text, textgate=coach.is_textgate(kid.text, kid.title))
    scope = (  # T2464: a note saying "everywhere" sent free workers into kuhy's checkouts of other repos
        f"This is one part of a larger note: yours is {kid.repo}. Other repos have their own parts, "
        'so "everywhere" or "every app" above means this repo only; never edit another repo.'
    )
    atomic.write_text(
        cdir / "task.md", f"{text}\n\n{scope}\nWork only in this checkout. Do not run git push.\n"
    )


def _ensure_rules(cdir: Path, kid: Child) -> None:
    """Put the textgate rules on top of a task file written before they existed; a coached file stays."""
    path = cdir / "task.md"
    text = path.read_text(encoding="utf-8")
    if coach.is_textgate(kid.text, kid.title) and coach.TEXTGATE_RULES not in text:
        atomic.write_text(path, f"{coach.TEXTGATE_RULES}\n\n{text}")


def _prepare(u: Umbrella, cur: dict[str, Any], kids: list[Child]) -> None:
    """Give every new child a worktree, its files and the server's verdict on free models."""
    d = u.d
    for kid in kids:
        if kid.cid in cur["free"] or kid.cid in cur["failed"]:
            continue
        cdir = child_dir(u.run_dir, kid.cid)
        st = child_state(u.run_dir, kid.cid) or fresh_state(kid, cur["n"], d.ctx.now(), auto_ship=True)
        try:
            worktree.attach(st, kid.repo, children_root(u.run_dir))
        except NeedsYouError as exc:
            st.extra["failed_stage"], st.error, st.stage = "implement", exc.text, "failed"
            store.save(cdir, st)
            cur["failed"][kid.cid] = exc.text
            continue
        atomic.write_text(cdir / "plan.md", _plan(kid))
        _write_task(cdir, kid)
        verdict = freegate.check(Path(str(st.worktree)))
        if verdict.detail:  # a gateway failure the server saw itself goes to the issue log
            issues.append(
                u.run_dir, d.ctx.now(), kid.repo, "start", verdict.detail,
                "the round waits for the gateway" if verdict.unreachable else "the manager does this child",
            )  # fmt: skip
        if verdict.unreachable:  # nothing answered: wait and retry, do not burn Sonnet on free work
            raise outage.gateway_unreachable(d, verdict.detail)
        outage.gateway_ok(d)
        cur["free"][kid.cid] = verdict.allowed
        st.extra.update(free=verdict.allowed, umbrella_round=cur["n"])
        store.save(cdir, st)
    d.save()


def _brief(u: Umbrella, cur: dict[str, Any], kids: list[Child]) -> str:
    lines = [f"Round {cur['n']}, width {cur['width']}. Worker command: {freeworker.command()}"]
    for kid in kids:
        cdir = child_dir(u.run_dir, kid.cid)
        lines += [
            f"- {kid.repo} (id {kid.key}, {kid.title})",
            f"  worktree: {cdir / 'wt'}",
            f"  task file: {cdir / 'task.md'}",
            f"  worker log: {cdir / f'worker-{cur["n"]}.log'}",
            f"  free: {'yes' if cur['free'][kid.cid] else 'no'}",
            f"  checks: {kid.done_check or '`make test` / pre-commit where the repo has them'}",
        ]
    return "\n".join(lines)


def _manage(u: Umbrella, cur: dict[str, Any], live: list[Child]) -> None:
    """Run the Opus manager over the live children; a failed turn escalates all of them."""
    d = u.d
    for kid in live:  # a round begun before the rules existed gets them now; a coached file keeps its edits
        _ensure_rules(child_dir(u.run_dir, kid.cid), kid)
    d.brief = _brief(u, cur, live)
    d.state.sessions.pop("manager", None)  # a fresh session per manager turn, never a dead one's (an adopted
    # turn does not read it: run_turn follows the recorded turn before it builds a prompt)
    try:
        verdicts = ramp.parse_verdicts(d.turn("manager", "implement", prompt="manager").text, live)
    except KilledError:  # a killed manager is retried (and then asks kuhy), never a reason to spend Opus
        raise
    except NeedsYouError as exc:
        verdicts = ramp.all_escalate(live, exc.text)
    d.state.last_tag = None  # the manager's own tag is not a question for kuhy
    cur["verdicts"] = {cid: {"kind": v.kind, "detail": v.detail} for cid, v in verdicts.items()}
    fixed = [k for k in live if verdicts[k.cid].kind == "fixed"]
    for repo in issues.unlogged(u.run_dir, [k.repo for k in fixed], cur["started"]):
        d.activity(f"{repo}: reported fixed with no line in free-issues.jsonl")
    for kid in fixed:  # a free child the manager finished itself must have been coached first
        done = issues.coaching(u.run_dir, kid.repo, cur["started"])
        if cur["free"][kid.cid] and done < coach.MAX_COACHED:
            d.activity(f"{kid.repo}: reported fixed after {done} of {coach.MAX_COACHED} coaching attempts")
    d.save()


def _check(u: Umbrella, cur: dict[str, Any], live: list[Child]) -> None:
    """Run each non-escalated child's checks (the checks stage's own helpers); red tails wait in the child."""
    d = u.d

    def one(kid: Child) -> tuple[str, bool]:
        cdir = child_dir(u.run_dir, kid.cid)
        st = child_state(u.run_dir, kid.cid)
        assert st is not None  # noqa: S101 - _prepare saved it
        wt = Path(str(st.worktree))
        results, log = checks.run_all(checks.discover(wt, kid.done_check), wt, cdir, d.ctx.check_timeout)
        st.checks = checks.record(results, log, d.ctx.now())
        red = [r for r in results if not r.passed]
        if red:
            st.extra["failure_tail"] = bounce.red_tail(
                st, "\n\n".join(f"== {r.name}: {r.command} (exit {r.exit_code})\n{r.tail}" for r in red)
            )
        store.save(cdir, st)
        return kid.cid, not red

    todo = [k for k in live if cur["verdicts"][k.cid]["kind"] != "escalate"]
    runs = [(contextvars.copy_context(), k) for k in todo]  # copied here: each pool thread keeps the watch
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_CHECKS, len(todo)))) as pool:
        cur["checks"] = dict(pool.map(lambda run: run[0].run(one, run[1]), runs))
    d.save()


def _finish(u: Umbrella, cur: dict[str, Any], kids: list[Child]) -> None:
    """Judge the round, hand each child to its own pipeline, record the round and the next width."""
    d, rec = u.d, u.rec
    oks, rows = [], []
    for kid in kids:
        cid = kid.cid
        if cid in cur["failed"]:
            d.ctx.locks.release(cid)  # this child never starts: its repo is free for others
            rows.append(_row(cid, "escalate", cur["failed"][cid], free=False, green=None, ok=False))
            oks.append(False)
            continue
        verdict = ramp.Verdict(**cur["verdicts"][cid])
        free, green = cur["free"][cid], cur["checks"].get(cid)
        ok = ramp.ok(verdict, free=free, checks=green)
        oks.append(ok)
        rows.append(_row(cid, verdict.kind, verdict.detail, free=free, green=green, ok=ok))
        st = child_state(u.run_dir, cid)
        assert st is not None  # noqa: S101 - _prepare saved it
        st.extra["verdict"] = {"kind": verdict.kind, "detail": verdict.detail}
        if verdict.kind == "escalate":  # the one Opus attempt
            st.extra.setdefault("notes", []).append(escalated(verdict.detail))
            st.stage = "implement"
        elif green is False:
            st.stage, st.extra["check_fixes"] = "implement", 1
        else:
            st.stage = "live_check"
        store.save(child_dir(u.run_dir, cid), st)
        u.pool.start(cid, st)
    width = rec["width"]
    nxt = ramp.next_width(width, oks)
    rec["rounds"].append({
        "n": cur["n"], "width": width, "next": nxt, "children": rows,
        "started": cur["started"], "ended": d.ctx.now(),
    })  # fmt: skip
    rec["width"], rec["current"] = nxt, None
    d.save()


def _row(  # noqa: PLR0913 - one result row
    cid: str, kind: str, detail: str, *, free: bool, green: bool | None, ok: bool
) -> dict[str, Any]:
    return {"id": cid, "verdict": kind, "detail": detail, "free": free, "checks": green, "ok": ok}
