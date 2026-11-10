"""Stage handlers: each runs one step and returns the next stage, or None to rest where it is."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.repotask import files
from todoimpl.umbrella.note import is_umbrella
from todoimpl.umbrella.run import run as run_umbrella

from . import phone, tiering
from .checks import SENTENCE_NOTE, discover, record, run_all
from .closing import closing_stage
from .files import NeedsYouError, write_json
from .live import rejudge, settle
from .parsing import parse_criteria, parse_live, parse_questions, parse_self_check
from .ship import CommitRefusedError, ShipPlan, ship
from .worktree import base_ref, repo_dir

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.board.state import SpecQuestion

    from .pipeline import Driver

MAX_CHECK_FIXES = 2
MAX_SHIP_FIXES = 2
MAX_PART_NUDGES = 2


def merge_questions(old: list[SpecQuestion], new: list[SpecQuestion]) -> list[SpecQuestion]:
    """Merge new cards: same id replaces an unanswered card; an answered card's reused id gets a fresh one."""
    merged = list(old)
    for card in new:
        index = next((i for i, q in enumerate(merged) if q.id == card.id), None)
        if index is None:
            merged.append(card)
        elif merged[index].answer is None:
            merged[index] = card
        elif merged[index].title != card.title:
            top = max(int(q.id[1:]) for q in merged)
            merged.append(replace(card, id=f"Q{top + 1}"))
    return merged


def _spec(d: Driver) -> str | None:
    st = d.state
    res = d.turn("spec", "spec")
    st.spec_questions = merge_questions(st.spec_questions, parse_questions(res.text))
    write_json(d.ctx.run_dir / "questions.json", [vars(q) for q in st.spec_questions])
    return "spec_wait"


def _plan(d: Driver) -> str | None:
    res = d.turn("plan", "plan")
    if res.tag in ("Q", "A"):
        return None
    plan = d.ctx.run_dir / "plan.md"
    if not parse_criteria(d.plan_md()) and parse_criteria(res.text):
        plan.write_text(res.text, encoding="utf-8")
    if not parse_criteria(d.plan_md()):
        msg = "plan.md has no `## Acceptance criteria` items: send guidance"
        raise NeedsYouError(msg, "run_failed")
    return "implement"


def _implement(d: Driver) -> str | None:
    if is_umbrella(d.item.body):  # the rounds of an umbrella note (umbrella/run.py)
        return run_umbrella(d)  # type: ignore[arg-type]
    tail = str(d.state.extra.get("failure_tail", ""))
    res = d.turn("implement", "fix" if tail else "implement", failure_tail=tail)
    if tiering.gave_up(d, res):  # the cheap tier hands over: the same stage again, now on Opus
        return "implement"
    d.state.extra.pop("failure_tail", None)
    d.state.self_check = parse_self_check(res.text)
    nxt = d.after_tag(res, "shipping" if d.state.extra.get("reship") else "live_check")
    if nxt == "shipping":
        d.state.extra.pop("reship")
    elif nxt == "live_check":  # new work to check: a new live-check session, seeded from the handoff
        d.state.sessions.pop("live_check", None)
        return _owed(d)
    return nxt


def _owed(d: Driver) -> str:
    """Ask twice when a repo task ends its implement turn with parts unticked, then go on (they stay open)."""
    left = files.unticked(d.ctx.run_dir, d.item)
    nudges = int(d.state.extra.get("part_nudges", 0))
    if not left or nudges >= MAX_PART_NUDGES:
        return "live_check"
    d.state.extra["part_nudges"] = nudges + 1
    d.state.extra["nudge"] = (
        "(runner) Parts not ticked: "
        + "; ".join(f"[{p.key}] {p.title}" for p in left)
        + ". Finish and tick each (see the tick command above), or end with `A:` and say what stops you."
    )
    return "implement"


def _retry(d: Driver, key: str, cap: int, tail: str, stop: NeedsYouError) -> str:
    fixes = int(d.state.extra.get(key, 0))
    if fixes >= cap:
        raise stop
    d.state.extra[key] = fixes + 1
    d.state.extra["failure_tail"] = tail
    return "implement"


def _live_check(d: Driver) -> str | None:
    st, run_dir = d.state, d.ctx.run_dir
    if st.extra.get("resettle"):
        return rejudge(d)
    report_file, shots = run_dir / "live_check.md", run_dir / "shots"
    if not st.extra.get("r_continue"):  # a continued turn keeps the report it already wrote
        report_file.unlink(missing_ok=True)
    shots.mkdir(parents=True, exist_ok=True)
    redo = str(st.extra.pop("live_redo", ""))  # set: ask for the checklist only, verify nothing again
    attached, info = bool(st.extra.get("phone_attached")), st.extra.get("waiting_phone")
    res = d.turn("live_check", "live_check", failure_tail=redo, prompt="live_checklist" if redo else "")
    if phone.hands_nudge(st, res, attached=attached, info=info):
        return "live_check"
    if res.tag in ("Q", "A"):
        return None
    if res.tag == "R":  # background work: continue first; settle's one redo only when this runs out
        if (again := d.r_continue(res)) is not None:
            return again
    else:
        st.extra.pop("r_continues", None)
    if not report_file.exists() and res.tag != "R":
        report_file.write_text(res.text, encoding="utf-8")
    report = report_file.read_text(encoding="utf-8") if report_file.exists() else ""
    st.live_check = {
        "report_md": report,
        "shots": sorted(str(p.relative_to(run_dir)) for p in shots.rglob("*") if p.is_file()),
    }
    return settle(d, report)


def _checks(d: Driver) -> str | None:
    st, wt = d.state, Path(str(d.state.worktree))
    found = discover(wt, d.item.done_check)
    if d.item.done_check and not any(name == "done_check" for name, _ in found):
        d.activity(f"checks: done_check not run, {SENTENCE_NOTE}")
    results, log = run_all(found, wt, d.ctx.run_dir, d.ctx.check_timeout)
    st.checks = record(results, log, d.ctx.now())
    red = [r for r in results if not r.passed]
    d.activity(
        "checks: " + (", ".join(f"{r.name} {'red' if r in red else 'ok'}" for r in results) or "none found")
    )
    if not red:
        st.extra.pop("check_fixes", None)
        child = "umbrella_round" in st.extra  # an umbrella child ships itself when green (T1923)
        st.auto_ship = st.auto_ship or child
        return "shipping" if child or (st.auto_ship and d.item.done_check) else "gate"
    tail = "\n\n".join(f"== {r.name}: {r.command} (exit {r.exit_code})\n{r.tail}" for r in red)
    why = f"Checks still red after {MAX_CHECK_FIXES} fix attempts: {', '.join(r.name for r in red)}"
    return _retry(d, "check_fixes", MAX_CHECK_FIXES, tail, NeedsYouError(why, "checks_failed"))


def _word(row: dict[str, object]) -> str:
    return "deferred" if row["deferred"] else "done" if row["done"] else "not done"


def live_summary(report: str) -> str:
    """One line per criterion of the live check, for the close evidence."""
    rows = parse_live(report)
    return "\n".join(f"live {r['criterion']}: {_word(r)} ({r['note']})" for r in rows)


def _shipping(d: Driver) -> str | None:
    if is_umbrella(d.item.body):  # Ship ships every child at its gate
        return run_umbrella(d)  # type: ignore[arg-type]
    st, wt = d.state, Path(str(d.state.worktree))
    if d.item.parts and not files.ticked(d.ctx.run_dir, d.item):
        msg = "No part is ticked, so Ship would close nothing: tick the finished parts, then ship again"
        raise NeedsYouError(msg, "run_failed")
    live = live_summary(str((st.live_check or {}).get("report_md", "")))
    checks = discover(wt, d.item.done_check)
    plan = ShipPlan(
        repo_dir(d.item.repo), wt, str(st.branch), d.item, checks, d.ctx.run_dir, d.ctx.check_timeout, live,
        str(st.base_sha or ""),
    )  # fmt: skip
    try:
        st.ship = ship(plan, d.ctx.client, d.ctx.now, allow_empty=st.auto_ship)
    except CommitRefusedError as refused:
        fixes = int(st.extra.get("ship_fixes", 0))
        if fixes >= MAX_SHIP_FIXES:
            raise
        st.extra.update(ship_fixes=fixes + 1, failure_tail=refused.output, reship=True)
        return "implement"
    sha = st.ship["commit"]
    if sha:
        st.head_sha = sha
    if sha and "pushed_at" not in st.ship:  # ship() closed it because the session pushed it already (T1865)
        d.activity(f"closed: the session already pushed {sha[:12]}")
        return "shipped"
    d.activity(
        f"shipped {sha[:12]} to origin/{base_ref(plan.repo)[1]}" if sha else "closed with no code change"
    )
    return "shipped"


HANDLERS: dict[str, Callable[[Driver], str | None]] = {
    "spec": _spec,
    "plan": _plan,
    "implement": _implement,
    "live_check": _live_check,
    "checks": _checks,
    "shipping": _shipping,
    "closing": closing_stage,
}
